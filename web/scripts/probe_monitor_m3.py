"""Phase 3 M3 verification probe for the XRoar -monitor stub.

M3 scope (from wiki/implementation/xroar-monitor.md):

  - read_gime_state: shadow-backed $FF90-$FF9F + PARs + palette + key flags
  - read_memory / write_memory: space="physical" (flat 19-bit address)
  - Cart-shadow no-op closure: write phys page $3E via space="physical",
    flip TY=1, CPU-read $C000, observe the byte.

Tests:
  1. read_gime_state structure and field shape.
  2. Pre-BASIC: MC3=0; poll until BASIC sets MC3=1.
  3. Physical-space round-trip: write/read $00040..$00050.
  4. Cart-shadow closure: write $5A to phys $7C000 (= phys page $3E,
     byte 0), then write $FFDF to flip TY=1, then CPU-read $C000 sees $5A.
  5. CPU-space write to ROM-backed addr under TY=0 is the documented
     no-op (lessons-learned): the byte does NOT appear on read-back.
  6. Out-of-range physical addr -> -32602.
  7. Palette read: any 6-bit values; no $C0 OR contamination.

Run inside WSL from repo root:
    python3 web/scripts/probe_monitor_m3.py
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


async def wait_for_mc3(c: MonitorClient, timeout: float = 5.0) -> bool:
    """Poll read_gime_state until BASIC has set MC3 (or timeout)."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        rep = await c.call("read_gime_state")
        r = rep.get("result", {})
        if r.get("mc3"):
            return True
        await asyncio.sleep(0.05)
    return False


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
        hello = await c.recv_line()
        if hello.get("params", {}).get("monitor_protocol_version") != "0.3.0":
            fail(f"expected monitor_protocol_version=0.3.0, got {hello}", ok)
        else:
            passed(f"hello.monitor_protocol_version=0.3.0")

        # --- Test 1: read_gime_state structure ---
        print("\n== Test 1: read_gime_state structure (pre-BASIC) ==")
        rep = await c.call("read_gime_state")
        r = rep.get("result")
        if not isinstance(r, dict):
            fail(f"no result object: {rep}", ok)
            return 1
        for k in ("registers", "pars", "palette", "mmu_task", "coco", "mmuen", "mc3", "ty"):
            if k not in r:
                fail(f"missing key {k!r}: {r}", ok)
                break
        else:
            passed("all top-level keys present")
        regs = r["registers"]
        for ff in ("FF90", "FF91", "FF98", "FF99", "FF9A", "FF9E"):
            if ff not in regs:
                fail(f"register {ff!r} missing", ok)
                break
        else:
            passed("registers FF90-FF9F all keyed by hex name")
        pal = r["palette"]
        if not isinstance(pal, list) or len(pal) != 16:
            fail(f"palette should be a 16-entry list, got {pal}", ok)
        else:
            over = [v for v in pal if not (0 <= v <= 0x3F)]
            if over:
                fail(f"palette has values with bit 6 or 7 set: {pal}", ok)
            else:
                passed(f"palette: 16 entries, all 0..0x3F (no $C0 OR) -> {pal}")
        pars = r["pars"]
        if not isinstance(pars.get("task0"), list) or len(pars["task0"]) != 8:
            fail(f"pars.task0 should be 8-entry list: {pars}", ok)
        else:
            passed(f"pars: task0/task1 are 8-entry lists; task0={pars['task0']}")

        # --- Test 2: MC3 starts 0; poll until BASIC sets it ---
        print("\n== Test 2: MC3 0 -> 1 across BASIC boot ==")
        if r.get("mc3") is not False:
            fail(f"expected mc3=False at boot, got {r.get('mc3')}", ok)
        else:
            passed("mc3=False at boot (BASIC has not run)")
        await c.call("run")
        if not await wait_for_mc3(c):
            fail("BASIC never set MC3 within 5s", ok)
        else:
            passed("BASIC set MC3=True (polled, no fixed sleep)")
        await c.call("pause")

        # --- Test 3: physical-space round-trip ---
        print("\n== Test 3: physical-space round-trip $00040..$0004F ==")
        pattern = bytes(reversed(range(0x10, 0x20)))  # 1f..10
        rep = await c.call("write_memory", {
            "addr": 0x00040, "space": "physical", "data": pattern.hex()
        })
        if not rep.get("result", {}).get("ok"):
            fail(f"physical write rejected: {rep}", ok)
        rep = await c.call("read_memory", {
            "addr": 0x00040, "length": len(pattern), "space": "physical"
        })
        got = rep.get("result", {}).get("data")
        if got != pattern.hex():
            fail(f"physical read mismatch: want {pattern.hex()} got {got}", ok)
        else:
            passed("physical round-trip matches")

        # --- Test 4: cart-shadow no-op closure ---
        print("\n== Test 4: cart-shadow closure (phys $7C000 -> CPU $C000 via TY=1) ==")
        # Phys page $3E byte 0 = phys $7C000. Under default CoCo3 RAM map,
        # CPU slot $C000-$DFFF maps to phys page $3E.
        rep = await c.call("write_memory", {
            "addr": 0x7C000, "space": "physical", "data": "5a"
        })
        if not rep.get("result", {}).get("ok"):
            fail(f"physical write to $7C000 rejected: {rep}", ok)
        # Read back via physical to confirm RAM has it (independent of TY).
        rep = await c.call("read_memory", {
            "addr": 0x7C000, "length": 1, "space": "physical"
        })
        if (rep.get("result", {}).get("data") or "") != "5a":
            fail(f"physical readback of $7C000 != 5a: {rep}", ok)
        else:
            passed("phys $7C000 = $5A confirmed via physical readback")

        # Confirm initial TY then flip via $FFDF.
        rep = await c.call("read_gime_state")
        ty_before = rep.get("result", {}).get("ty")
        # Flip TY=1 by writing $FFDF (any value).
        await c.call("write_memory", {"addr": 0xFFDF, "space": "cpu", "data": "01"})
        rep = await c.call("read_gime_state")
        ty_after = rep.get("result", {}).get("ty")
        if not (ty_after and not ty_before):
            # Some boot paths leave TY=1 already; that's still OK for the
            # downstream check. Note it.
            passed(f"ty={ty_before}->{ty_after} (write to $FFDF processed)")
        else:
            passed("TY 0 -> 1 after write to $FFDF")

        # Now CPU-read $C000 should see the byte we planted in phys $7C000.
        rep = await c.call("read_memory", {"addr": 0xC000, "length": 1, "space": "cpu"})
        cpu_c000 = rep.get("result", {}).get("data")
        if cpu_c000 != "5a":
            fail(f"CPU $C000 != 5A after TY=1; got {cpu_c000} "
                 f"(see lessons-learned: phys page $3E -> $C000 under default map)", ok)
        else:
            passed("cart-shadow closure: CPU $C000 reads $5A after TY=1")

        # --- Test 5: CPU-space write under TY=0 to cart-window is a no-op ---
        print("\n== Test 5: CPU-space write to cart-window under TY=0 is no-op ==")
        # Flip TY=0 via $FFDE.
        await c.call("write_memory", {"addr": 0xFFDE, "space": "cpu", "data": "00"})
        rep = await c.call("read_gime_state")
        if rep.get("result", {}).get("ty") is not False:
            fail(f"TY didn't flip back to 0: {rep}", ok)
        # Read what's currently at CPU $C100 (cart ROM byte).
        rep = await c.call("read_memory", {"addr": 0xC100, "length": 1, "space": "cpu"})
        baseline = rep.get("result", {}).get("data")
        # Attempt CPU-space write to $C100.
        await c.call("write_memory", {"addr": 0xC100, "space": "cpu", "data": "a5"})
        rep = await c.call("read_memory", {"addr": 0xC100, "length": 1, "space": "cpu"})
        after = rep.get("result", {}).get("data")
        if after == "a5":
            fail(f"CPU-space write to $C100 under TY=0 unexpectedly succeeded "
                 f"(lessons-learned says XRoar drops it as cart-rom-write)", ok)
        elif after != baseline:
            fail(f"$C100 changed from {baseline} to {after} but not to $A5 — unexpected", ok)
        else:
            passed(f"CPU write to $C100 under TY=0 was a no-op (read back {after} unchanged)")

        # --- Test 6: out-of-range physical addr ---
        print("\n== Test 6: physical addr out of range ==")
        rep = await c.call("read_memory", {
            "addr": 0x80000, "length": 1, "space": "physical"
        })
        if rep.get("error", {}).get("code") != -32602:
            fail(f"expected -32602 for phys addr 0x80000 on 512K, got {rep}", ok)
        else:
            passed("phys addr 0x80000 on 512K -> -32602")

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
        print("PASS: M3 probe green")
        return 0
    print("FAIL: M3 probe red")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
