"""Phase 3 M4 verification probe for the XRoar -monitor stub.

M4 scope (from wiki/implementation/xroar-monitor.md):

  - set_breakpoint / clear_breakpoint / list_breakpoints (exec)
  - step_instruction(n)
  - wait_for_stop(timeout_ms) long-poll

Headline tests:
  1. At-current-PC BP fires (the gdb-stub failure case from lessons-learned).
  2. step_instruction advances PC; wait_for_stop returns reason='step'.
  3. step_instruction(n) batches n steps -> one stop event.
  4. wait_for_stop with no pending stop times out cleanly.
  5. list_breakpoints reflects set/clear correctly.
  6. set/clear/step while running -> target_running.

Run inside WSL from repo root:
    python3 web/scripts/probe_monitor_m4.py
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
        line = await asyncio.wait_for(self._reader.readline(), timeout=10.0)
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
    raise TimeoutError(f"listener never came up: {last_err}")


async def wait_for_mc3(c: MonitorClient, timeout: float = 5.0) -> bool:
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        rep = await c.call("read_gime_state")
        if rep.get("result", {}).get("mc3"):
            return True
        await asyncio.sleep(0.05)
    return False


def fail(msg: str, box: list) -> None:
    print(f"  FAIL: {msg}")
    box[0] = False


def passed(msg: str) -> None:
    print(f"  OK: {msg}")


async def get_pc(c: MonitorClient) -> int:
    rep = await c.call("read_registers")
    return rep["result"]["pc"]


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
        if hello.get("params", {}).get("monitor_protocol_version") != "0.4.0":
            fail(f"expected protocol 0.4.0, got {hello}", ok)
        else:
            passed("hello.monitor_protocol_version=0.4.0")

        # Let BASIC boot so PC lands somewhere predictable in the ROM.
        await c.call("run")
        if not await wait_for_mc3(c):
            fail("BASIC never set MC3 within 5s", ok)
            return 1
        await c.call("pause")

        # --- Test 1: at-current-PC BP fires (the gdb-stub failure case) ---
        print("\n== Test 1: BP at current PC fires (closes gdb-stub limitation) ==")
        pc0 = await get_pc(c)
        rep = await c.call("set_breakpoint", {"addr": pc0, "kind": "exec"})
        bp_id = rep.get("result", {}).get("id")
        if not bp_id:
            fail(f"set_breakpoint did not return id: {rep}", ok)
            return 1
        passed(f"BP id={bp_id} set at current PC=0x{pc0:04X}")
        await c.call("run")
        rep = await c.call("wait_for_stop", {"timeout_ms": 2000})
        r = rep.get("result", {})
        if r.get("reason") != "breakpoint":
            fail(f"expected reason=breakpoint, got {rep}", ok)
        elif r.get("pc") != pc0:
            fail(f"BP fired at pc=0x{r.get('pc'):04X}, expected 0x{pc0:04X} "
                 f"(if pc advanced, that's the gdb-stub bad behavior)", ok)
        elif r.get("bp_id") != bp_id:
            fail(f"bp_id mismatch: got {r.get('bp_id')}, expected {bp_id}", ok)
        else:
            passed(f"BP fired before instruction executed: pc=0x{pc0:04X} bp_id={bp_id}")

        # --- Test 2: list/clear lifecycle ---
        print("\n== Test 2: list_breakpoints + clear_breakpoint ==")
        rep = await c.call("list_breakpoints")
        lst = rep.get("result", {}).get("breakpoints", [])
        if len(lst) != 1 or lst[0]["id"] != bp_id or lst[0]["addr"] != pc0:
            fail(f"list_breakpoints unexpected: {lst}", ok)
        else:
            passed(f"list has 1 entry: id={bp_id} addr=0x{pc0:04X}")
        rep = await c.call("clear_breakpoint", {"id": bp_id})
        if not rep.get("result", {}).get("ok"):
            fail(f"clear_breakpoint failed: {rep}", ok)
        else:
            passed("clear_breakpoint succeeded")
        rep = await c.call("list_breakpoints")
        if rep["result"]["breakpoints"]:
            fail(f"list should be empty after clear: {rep}", ok)
        else:
            passed("list is empty after clear")
        # Clearing a stale id should error.
        rep = await c.call("clear_breakpoint", {"id": bp_id})
        if rep.get("error", {}).get("code") != -32602:
            fail(f"expected -32602 for cleared id, got {rep}", ok)
        else:
            passed("clearing already-removed id -> -32602")

        # --- Test 3: step_instruction(1) advances PC, wait_for_stop returns 'step' ---
        print("\n== Test 3: step_instruction(1) ==")
        pc1 = await get_pc(c)
        rep = await c.call("step_instruction", {"n": 1})
        if not rep.get("result", {}).get("ok"):
            fail(f"step_instruction(1) rejected: {rep}", ok)
        rep = await c.call("wait_for_stop", {"timeout_ms": 1000})
        r = rep.get("result", {})
        pc2 = await get_pc(c)
        if r.get("reason") != "step":
            fail(f"expected reason=step, got {rep}", ok)
        elif pc2 == pc1:
            fail(f"step did not advance PC (still 0x{pc1:04X})", ok)
        else:
            passed(f"step: PC 0x{pc1:04X} -> 0x{pc2:04X}; wait_for_stop reason=step")

        # --- Test 4: step_instruction(N) batches into one stop event ---
        print("\n== Test 4: step_instruction(5) -> single stop event ==")
        pc_before = await get_pc(c)
        await c.call("step_instruction", {"n": 5})
        rep = await c.call("wait_for_stop", {"timeout_ms": 1000})
        if rep["result"].get("reason") != "step":
            fail(f"step(5) wait_for_stop wrong reason: {rep}", ok)
        else:
            passed(f"step(5) returned single 'step' event")
        pc_after = await get_pc(c)
        if pc_after == pc_before:
            fail(f"step(5) did not advance PC", ok)
        else:
            passed(f"step(5): PC 0x{pc_before:04X} -> 0x{pc_after:04X}")

        # --- Test 5: wait_for_stop times out cleanly when no event ---
        print("\n== Test 5: wait_for_stop timeout ==")
        # Already halted with last_stop populated from Test 4. Resume by 'run',
        # then immediately wait with a short timeout (no BP set => no stop).
        await c.call("run")
        rep = await c.call("wait_for_stop", {"timeout_ms": 200})
        if rep["result"].get("reason") != "timeout":
            fail(f"expected timeout, got {rep}", ok)
        else:
            passed("wait_for_stop returned reason=timeout after 200ms")
        # Now pause so subsequent halted-only ops work.
        await c.call("pause")

        # --- Test 6: halted-only enforcement on mutating BP ops ---
        print("\n== Test 6: set/clear/step rejected while running ==")
        await c.call("run")
        rep = await c.call("set_breakpoint", {"addr": 0x4000})
        if rep.get("error", {}).get("code") != -32001:
            fail(f"set_breakpoint while running should be -32001: {rep}", ok)
        else:
            passed("set_breakpoint while running -> target_running")
        rep = await c.call("clear_breakpoint", {"id": 99})
        if rep.get("error", {}).get("code") != -32001:
            fail(f"clear_breakpoint while running should be -32001: {rep}", ok)
        else:
            passed("clear_breakpoint while running -> target_running")
        rep = await c.call("step_instruction")
        if rep.get("error", {}).get("code") != -32001:
            fail(f"step_instruction while running should be -32001: {rep}", ok)
        else:
            passed("step_instruction while running -> target_running")
        # list_breakpoints should be allowed while running (it's a state read).
        rep = await c.call("list_breakpoints")
        if "result" not in rep:
            fail(f"list_breakpoints while running should succeed: {rep}", ok)
        else:
            passed("list_breakpoints allowed while running")

        # --- Test 7: get_run_state includes last_stop_reason after a stop ---
        print("\n== Test 7: get_run_state includes last_stop_reason ==")
        await c.call("pause")
        rep = await c.call("get_run_state")
        r = rep["result"]
        if r.get("state") != "halted" or r.get("last_stop_reason") != "pause":
            fail(f"expected state=halted, last_stop_reason=pause: {rep}", ok)
        else:
            passed(f"get_run_state: state=halted, last_stop_reason=pause, last_stop_pc=0x{r.get('last_stop_pc', 0):04X}")

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
        print("PASS: M4 probe green")
        return 0
    print("FAIL: M4 probe red")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
