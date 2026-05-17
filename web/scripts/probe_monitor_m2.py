"""Phase 3 M2 verification probe for the XRoar -monitor stub.

M2 scope (from wiki/implementation/xroar-monitor.md):

  - read_memory / write_memory (CPU space)
  - read_registers / write_registers
  - Halted-only enforcement on writes -> JSON-RPC error 'target_running'

Tests:
  1. read_memory + write_memory round-trip in $FE00-$FEFF (RAM-under-MC3
     window — works under XRoar's bus model).
  2. read_registers returns plausible values; D matches (A<<8|B).
  3. write_memory while running -> target_running error.
  4. write_registers while running -> target_running error.
  5. After pause, write_registers succeeds and read-back confirms.
  6. Read length cap: length > 65536 -> -32602.
  7. Invalid space ('physical' in M2) -> -32602.

Run inside WSL from repo root:
    python3 web/scripts/probe_monitor_m2.py
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

XROAR_BIN = os.environ.get(
    "XROAR_BIN",
    str(REPO_ROOT / "docs" / "reference" / "xroar" / "build" / "xroar-monitor"),
)


def pick_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class MonitorClient:
    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._next_id = 1

    async def connect(self) -> None:
        self._reader, self._writer = await asyncio.open_connection(self.host, self.port)

    async def close(self) -> None:
        if self._writer is not None:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:
                pass

    async def recv_line(self) -> dict:
        assert self._reader is not None
        line = await asyncio.wait_for(self._reader.readline(), timeout=5.0)
        if not line:
            raise EOFError("monitor closed connection")
        return json.loads(line)

    async def call(self, method: str, params: dict | None = None) -> dict:
        assert self._writer is not None
        rid = self._next_id
        self._next_id += 1
        req: dict = {"jsonrpc": "2.0", "id": rid, "method": method}
        if params is not None:
            req["params"] = params
        self._writer.write((json.dumps(req) + "\n").encode())
        await self._writer.drain()
        reply = await self.recv_line()
        assert reply.get("id") == rid, f"id mismatch: {reply}"
        return reply


async def wait_for_port(host: str, port: int, timeout: float = 5.0) -> None:
    deadline = asyncio.get_event_loop().time() + timeout
    last_err: Exception | None = None
    while asyncio.get_event_loop().time() < deadline:
        try:
            _, w = await asyncio.open_connection(host, port)
            w.close()
            try:
                await w.wait_closed()
            except Exception:
                pass
            return
        except Exception as e:
            last_err = e
            await asyncio.sleep(0.05)
    raise TimeoutError(f"listener never came up on {host}:{port}: {last_err}")


def fail(msg: str, box: list) -> None:
    print(f"  FAIL: {msg}")
    box[0] = False


def passed(msg: str) -> None:
    print(f"  OK: {msg}")


async def run() -> int:
    if not Path(XROAR_BIN).exists():
        print(f"FAIL: xroar-monitor binary not found at {XROAR_BIN}", file=sys.stderr)
        return 2
    port = pick_port()
    print(f"probe: launching {XROAR_BIN} with -monitor 127.0.0.1:{port} -monitor-halt-on-start")
    proc = await asyncio.create_subprocess_exec(
        XROAR_BIN,
        "-machine", "coco3", "-ram", "512",
        "-monitor", f"127.0.0.1:{port}",
        "-monitor-halt-on-start",
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    ok = [True]
    try:
        await wait_for_port("127.0.0.1", port, timeout=5.0)
        c = MonitorClient("127.0.0.1", port)
        await c.connect()
        _ = await c.recv_line()  # hello

        # $FE00-$FEFF is RAM only when MC3 is set, which Color BASIC does
        # during its early init. Let BASIC run briefly so GIME is configured,
        # then pause for the deterministic tests.
        await c.call("run")
        await asyncio.sleep(2.0)
        await c.call("pause")

        # --- Test 1: write_memory + read_memory round-trip in $FE00-$FEFF ---
        print("\n== Test 1: memory round-trip in $FE00-$FEFF ==")
        pattern = bytes(range(0, 256))  # 00..FF
        hex_in = pattern.hex()
        rep = await c.call("write_memory", {"addr": 0xFE00, "space": "cpu", "data": hex_in})
        if not rep.get("result", {}).get("ok") or rep["result"].get("written") != 256:
            fail(f"write_memory did not report ok+written=256: {rep}", ok)
        else:
            passed("write_memory wrote 256 bytes")
        rep = await c.call("read_memory", {"addr": 0xFE00, "length": 256, "space": "cpu"})
        data_hex = rep.get("result", {}).get("data")
        if data_hex != hex_in:
            fail(f"read_memory mismatch (first 16 written={pattern[:16].hex()}, first 16 read={bytes.fromhex(data_hex or '')[:16].hex() if data_hex else None})", ok)
        else:
            passed("read_memory matches written pattern bit-for-bit")

        # --- Test 2: read_registers returns plausible values ---
        print("\n== Test 2: read_registers ==")
        rep = await c.call("read_registers")
        r = rep.get("result", {})
        for k in ("a", "b", "d", "cc", "dp", "x", "y", "u", "s", "pc"):
            if not isinstance(r.get(k), int):
                fail(f"register {k!r} missing or not int: {r}", ok)
                break
        else:
            passed(f"all 10 registers present: pc=0x{r['pc']:04X} cc=0x{r['cc']:02X}")
        if r.get("d") != ((r["a"] << 8) | r["b"]):
            fail(f"D={r.get('d')} != (A<<8|B)={(r['a']<<8)|r['b']}", ok)
        else:
            passed(f"D=0x{r['d']:04X} == (A<<8|B)")

        # --- Test 3: writes while running -> target_running ---
        print("\n== Test 3: writes while running -> target_running ==")
        await c.call("run")
        rep = await c.call("write_memory", {"addr": 0xFE10, "space": "cpu", "data": "5a"})
        err = rep.get("error", {})
        if err.get("code") != -32001 or err.get("message") != "target_running":
            fail(f"expected target_running -32001, got {rep}", ok)
        else:
            passed("write_memory while running -> target_running -32001")

        rep = await c.call("write_registers", {"a": 0x42})
        err = rep.get("error", {})
        if err.get("code") != -32001 or err.get("message") != "target_running":
            fail(f"expected target_running -32001, got {rep}", ok)
        else:
            passed("write_registers while running -> target_running -32001")

        # Reads must still work while running.
        rep = await c.call("read_memory", {"addr": 0xFE00, "length": 1, "space": "cpu"})
        if "result" not in rep:
            fail(f"read_memory while running should succeed, got {rep}", ok)
        else:
            passed("read_memory permitted while running")
        rep = await c.call("read_registers")
        if "result" not in rep:
            fail(f"read_registers while running should succeed, got {rep}", ok)
        else:
            passed("read_registers permitted while running")

        # --- Test 4: pause then write_registers + read-back ---
        print("\n== Test 4: write_registers (halted) round-trip ==")
        await c.call("pause")
        rep = await c.call("write_registers", {"a": 0x5A, "b": 0xA5, "x": 0x1234, "pc": 0xABCD})
        if not rep.get("result", {}).get("ok"):
            fail(f"write_registers should succeed when halted: {rep}", ok)
        rep = await c.call("read_registers")
        r = rep.get("result", {})
        for k, want in (("a", 0x5A), ("b", 0xA5), ("x", 0x1234), ("pc", 0xABCD), ("d", 0x5AA5)):
            if r.get(k) != want:
                fail(f"register {k!r}: want 0x{want:X}, got {r.get(k)}", ok)
                break
        else:
            passed("a=0x5A b=0xA5 x=0x1234 pc=0xABCD d=0x5AA5 all round-tripped")

        # --- Test 5: read length cap -> -32602 ---
        print("\n== Test 5: read length cap ==")
        rep = await c.call("read_memory", {"addr": 0, "length": 65537, "space": "cpu"})
        if rep.get("error", {}).get("code") != -32602:
            fail(f"expected -32602 for oversize read, got {rep}", ok)
        else:
            passed("length=65537 -> -32602")

        # --- Test 6: unsupported space (physical) -> -32602 in M2 ---
        print("\n== Test 6: space='physical' rejected in M2 ==")
        rep = await c.call("read_memory", {"addr": 0, "length": 1, "space": "physical"})
        if rep.get("error", {}).get("code") != -32602:
            fail(f"expected -32602 for space=physical, got {rep}", ok)
        else:
            passed("space=physical -> -32602 (deferred to M3)")

        # --- Test 7: addr range guard ---
        print("\n== Test 7: addr range guard ==")
        rep = await c.call("read_memory", {"addr": 0x10000, "length": 1, "space": "cpu"})
        if rep.get("error", {}).get("code") != -32602:
            fail(f"expected -32602 for addr=0x10000, got {rep}", ok)
        else:
            passed("addr=0x10000 -> -32602")

        await c.close()
    finally:
        if proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                proc.kill()

    print()
    if ok[0]:
        print("PASS: M2 probe green")
        return 0
    print("FAIL: M2 probe red")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
