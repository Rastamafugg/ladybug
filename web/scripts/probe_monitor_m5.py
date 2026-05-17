"""Phase 3 M5 verification probe for the XRoar -monitor stub.

M5 scope (from wiki/implementation/xroar-monitor.md):

  - reset(kind="soft"|"hard") clears BPs, calls machine reset, emits
    async 'reset' event notification.
  - attach() / detach() ceremony, repeatable within one XRoar lifetime.
  - 'goodbye' notification emitted by the server on shutdown.
  - CPU state preserved across detach + reconnect (already verified M1).

Tests:
  1. attach() returns hello-shaped fields; works at any state.
  2. reset(soft) clears BPs, returns ok, emits 'reset' notification.
  3. reset(hard) likewise.
  4. reset while running -> target_running.
  5. detach() returns ok; server closes; reconnect succeeds; state preserved.
  6. 'goodbye' notification arrives when XRoar is terminated.

Run inside WSL from repo root:
    python3 web/scripts/probe_monitor_m5.py
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

    async def recv_line(self, timeout: float = 5.0) -> dict:
        assert self._reader is not None
        line = await asyncio.wait_for(self._reader.readline(), timeout=timeout)
        if not line:
            raise EOFError("monitor closed connection")
        return json.loads(line)

    async def recv_line_optional(self, timeout: float) -> dict | None:
        try:
            return await self.recv_line(timeout=timeout)
        except (asyncio.TimeoutError, EOFError):
            return None

    async def call(self, method: str, params: dict | None = None) -> dict:
        """Send a request and read replies until one with the matching id
        arrives, returning that one. Any prior lines (notifications) are
        discarded by this caller — tests that care about notifications
        should call recv_line directly."""
        assert self._writer is not None
        rid = self._next_id
        self._next_id += 1
        req: dict = {"jsonrpc": "2.0", "id": rid, "method": method}
        if params is not None:
            req["params"] = params
        self._writer.write((json.dumps(req) + "\n").encode())
        await self._writer.drain()
        while True:
            reply = await self.recv_line()
            if reply.get("id") == rid:
                return reply

    async def call_capture_event(self, method: str, params: dict | None,
                                 event_method: str, event_timeout: float = 1.0
                                 ) -> tuple[dict, dict | None]:
        """Send a request and collect both the reply AND a subsequent event
        notification with the named method. Returns (reply, event_or_None)."""
        assert self._writer is not None
        rid = self._next_id
        self._next_id += 1
        req: dict = {"jsonrpc": "2.0", "id": rid, "method": method}
        if params is not None:
            req["params"] = params
        self._writer.write((json.dumps(req) + "\n").encode())
        await self._writer.drain()
        reply: dict | None = None
        evt: dict | None = None
        deadline = asyncio.get_event_loop().time() + event_timeout
        while reply is None or evt is None:
            remaining = max(0.05, deadline - asyncio.get_event_loop().time())
            line = await self.recv_line_optional(remaining)
            if line is None:
                break
            if reply is None and line.get("id") == rid:
                reply = line
                continue
            if evt is None and line.get("method") == event_method:
                evt = line
                continue
        return reply or {}, evt


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
        if hello.get("params", {}).get("monitor_protocol_version") != "0.5.0":
            fail(f"expected protocol 0.5.0, got {hello}", ok)
        else:
            passed("hello.monitor_protocol_version=0.5.0")

        # --- Test 1: attach() ceremony ---
        print("\n== Test 1: attach() ==")
        rep = await c.call("attach")
        r = rep.get("result", {})
        for k in ("monitor_protocol_version", "xroar_version", "machine_name", "run_state"):
            if k not in r:
                fail(f"attach() missing {k!r}: {rep}", ok)
                break
        else:
            passed(f"attach() returned {r}")

        # Boot BASIC so set_breakpoint at current PC has a real instruction.
        await c.call("run")
        await wait_for_mc3(c)
        await c.call("pause")

        # --- Test 2: reset(soft) clears BPs, emits reset event ---
        print("\n== Test 2: reset(soft) clears BPs + emits reset event ==")
        pc0 = (await c.call("read_registers"))["result"]["pc"]
        bp_id = (await c.call("set_breakpoint", {"addr": pc0}))["result"]["id"]
        # Sanity: BP is in the list.
        lst = (await c.call("list_breakpoints"))["result"]["breakpoints"]
        if len(lst) != 1:
            fail(f"BP not registered: {lst}", ok)

        rep, evt = await c.call_capture_event("reset", {"kind": "soft"}, "reset")
        if not rep.get("result", {}).get("ok") or rep["result"].get("kind") != "soft":
            fail(f"reset(soft) reply unexpected: {rep}", ok)
        else:
            passed(f"reset(soft) replied ok")
        if evt is None or evt.get("params", {}).get("kind") != "soft":
            fail(f"reset event missing or wrong kind: {evt}", ok)
        else:
            passed(f"async 'reset' event delivered with kind=soft")
        lst = (await c.call("list_breakpoints"))["result"]["breakpoints"]
        if lst:
            fail(f"BPs should be cleared after reset: {lst}", ok)
        else:
            passed(f"BP table empty after reset (was id={bp_id})")

        # --- Test 3: reset(hard) ---
        print("\n== Test 3: reset(hard) ==")
        await c.call("set_breakpoint", {"addr": 0x4000})
        rep, evt = await c.call_capture_event("reset", {"kind": "hard"}, "reset")
        if rep.get("result", {}).get("kind") != "hard":
            fail(f"reset(hard) reply: {rep}", ok)
        else:
            passed("reset(hard) replied ok")
        if evt is None or evt.get("params", {}).get("kind") != "hard":
            fail(f"reset event for hard: {evt}", ok)
        else:
            passed("async 'reset' event delivered with kind=hard")
        lst = (await c.call("list_breakpoints"))["result"]["breakpoints"]
        if lst:
            fail(f"BPs not cleared after hard reset: {lst}", ok)
        else:
            passed("BP table empty after hard reset")

        # --- Test 4: reset while running -> target_running ---
        print("\n== Test 4: reset while running -> target_running ==")
        await c.call("run")
        rep = await c.call("reset", {"kind": "soft"})
        if rep.get("error", {}).get("code") != -32001:
            fail(f"reset while running should be -32001: {rep}", ok)
        else:
            passed("reset while running -> -32001 target_running")
        await c.call("pause")

        # --- Test 5: detach + reconnect; state preserved ---
        print("\n== Test 5: detach + reconnect ==")
        pc_before = (await c.call("read_registers"))["result"]["pc"]
        rep = await c.call("detach")
        if not rep.get("result", {}).get("ok"):
            fail(f"detach reply: {rep}", ok)
        else:
            passed("detach replied ok")
        await c.close()
        # Reconnect a new client.
        c2 = MonitorClient("127.0.0.1", port)
        await c2.connect()
        hello2 = await c2.recv_line()
        if hello2.get("method") != "hello":
            fail(f"reconnect: no hello: {hello2}", ok)
        else:
            passed("reconnect: hello received")
        # State should still be halted (CPU preserved across detach).
        rep = await c2.call("get_run_state")
        if rep["result"]["state"] != "halted":
            fail(f"CPU not halted after reconnect: {rep}", ok)
        else:
            passed("CPU still halted after reconnect")
        pc_after = (await c2.call("read_registers"))["result"]["pc"]
        # PC should be unchanged (CPU was halted; no instructions executed
        # between detach and reconnect).
        if pc_after != pc_before:
            fail(f"PC changed across detach/reconnect: 0x{pc_before:04X} -> 0x{pc_after:04X}", ok)
        else:
            passed(f"PC preserved across detach/reconnect: 0x{pc_after:04X}")

        # --- Test 6: goodbye on clean shutdown via quit method ---
        print("\n== Test 6: 'goodbye' notification on quit-triggered shutdown ==")
        # Send quit; receive both the quit reply and the goodbye event.
        # quit triggers exit(0) inside XRoar, which runs the atexit chain.
        # SIGTERM/SIGKILL bypass atexit and won't fire goodbye — that's
        # an accepted limitation for v1.
        rep, evt = await c2.call_capture_event("quit", None, "goodbye", event_timeout=2.0)
        if not rep.get("result", {}).get("ok"):
            fail(f"quit did not return ok: {rep}", ok)
        else:
            passed("quit replied ok")
        if evt is None or evt.get("method") != "goodbye":
            fail(f"goodbye not delivered after quit: {evt}", ok)
        else:
            passed(f"goodbye notification received: reason={evt.get('params',{}).get('reason')!r}")
        await c2.close()
    finally:
        if proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                proc.kill()

    print()
    if ok[0]:
        print("PASS: M5 probe green")
        return 0
    print("FAIL: M5 probe red")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
