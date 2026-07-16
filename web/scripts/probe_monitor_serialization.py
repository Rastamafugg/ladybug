"""Discriminating probe: does the monitor stub serialize requests behind a
pending wait_for_stop long-poll?

Hypothesis (from reading monitor.c handle_connection): the per-client worker
is a strict read_line -> dispatch -> reply loop, so a wait_for_stop long-poll
blocks ALL subsequent requests on that connection until it returns. The web
backend's MonitorSession assumes pipelining (it issues wait_for_stop from a
halt-watcher task concurrently with UI-driven calls), which would explain the
reported symptom: while free-running, breakpoint clicks stall ~30 s and then
"catch up".

Test A — pipelining: with the CPU free-running (no BP), send
    wait_for_stop(timeout_ms=8000), then 0.3 s later get_run_state.
    Serialized: get_run_state reply arrives ~8 s after it was sent.
    Pipelined:  get_run_state reply arrives in milliseconds.

Test B — pause starvation: send wait_for_stop(timeout_ms=8000), then 0.3 s
    later pause. Serialized: pause cannot be processed until the long-poll
    times out, so wait_for_stop returns reason="timeout" (the pause that
    would have satisfied it is stuck in the socket buffer) and the pause
    reply lands ~8 s late. This is the exact shape of the web-app hang.

Run inside WSL from repo root:
    python3 web/scripts/probe_monitor_serialization.py
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import time
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


class RawClient:
    """Send/receive decoupled so we can have several requests in flight."""

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._next_id = 1
        self._buffered_replies: dict[int, tuple[dict, float]] = {}

    async def connect(self) -> None:
        self._reader, self._writer = await asyncio.open_connection(self.host, self.port)

    async def close(self) -> None:
        if self._writer is not None:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:
                pass

    async def send(self, method: str, params: dict | None = None) -> int:
        assert self._writer is not None
        rid = self._next_id
        self._next_id += 1
        req: dict = {"jsonrpc": "2.0", "id": rid, "method": method}
        if params is not None:
            req["params"] = params
        self._writer.write((json.dumps(req) + "\n").encode())
        await self._writer.drain()
        return rid

    async def recv(self, timeout: float = 20.0) -> dict:
        assert self._reader is not None
        line = await asyncio.wait_for(self._reader.readline(), timeout=timeout)
        if not line:
            raise EOFError("monitor closed connection")
        return json.loads(line)

    async def recv_reply(self, rid: int, timeout: float = 20.0) -> tuple[dict, float]:
        """Skip event notifications; return (reply-for-rid, monotonic-arrival)."""
        buffered = self._buffered_replies.pop(rid, None)
        if buffered is not None:
            return buffered
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            msg = await self.recv(timeout=max(0.1, remaining))
            arrived = time.monotonic()
            if msg.get("id") == rid:
                return msg, arrived
            other_id = msg.get("id")
            if other_id is not None:
                # Several requests may be in flight. Preserve replies for
                # their eventual waiter instead of discarding them as events.
                self._buffered_replies[other_id] = (msg, arrived)
            else:
                print(f"    (skipping notification: {msg.get('method', msg)})")

    async def call(self, method: str, params: dict | None = None) -> dict:
        rid = await self.send(method, params)
        reply, _ = await self.recv_reply(rid)
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


async def run() -> int:
    if not Path(XROAR_BIN).exists():
        print(f"FAIL: xroar-monitor binary not found at {XROAR_BIN}", file=sys.stderr)
        return 2
    port = pick_port()
    print(f"probe: launching xroar-monitor on 127.0.0.1:{port}")
    proc = await asyncio.create_subprocess_exec(
        XROAR_BIN,
        "-machine", "coco3", "-ram", "512",
        "-monitor", f"127.0.0.1:{port}",
        "-monitor-halt-on-start",
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    serialized = None
    try:
        await wait_for_port("127.0.0.1", port)
        c = RawClient("127.0.0.1", port)
        await c.connect()
        hello = await c.recv()
        print(f"  hello: {hello.get('params', {})}")

        # Free-run with no breakpoints — nothing will stop the CPU.
        await c.call("run")

        # ---- Test A: is get_run_state served while wait_for_stop pends? ----
        print("\n== Test A: get_run_state behind a pending wait_for_stop(8000) ==")
        wid = await c.send("wait_for_stop", {"timeout_ms": 8000})
        await asyncio.sleep(0.3)
        t_sent = time.monotonic()
        gid = await c.send("get_run_state")
        g_reply, t_g = await c.recv_reply(gid)  # skips/even reports w reply if first
        dt = t_g - t_sent
        print(f"  get_run_state replied in {dt:.2f}s: {g_reply.get('result')}")
        if dt > 5.0:
            serialized = True
            print("  => SERIALIZED: reply stalled behind the long-poll")
        else:
            serialized = False
            print("  => PIPELINED: reply served while long-poll pending")
        # Drain the wait_for_stop reply if it hasn't arrived yet.
        try:
            w_reply, _ = await c.recv_reply(wid, timeout=12.0)
            print(f"  wait_for_stop eventually returned: {w_reply.get('result')}")
        except (asyncio.TimeoutError, EOFError):
            print("  wait_for_stop reply never seen (unexpected)")

        # ---- Test B: pause starvation (the web-app hang shape) ----
        print("\n== Test B: pause sent 0.3s after wait_for_stop(8000) ==")
        st = await c.call("get_run_state")
        print(f"  run_state before: {st.get('result')}")
        wid = await c.send("wait_for_stop", {"timeout_ms": 8000})
        await asyncio.sleep(0.3)
        t_sent = time.monotonic()
        pid = await c.send("pause")
        # Replies must arrive in server-processing order; collect both.
        first, t_first = await c.recv_reply(wid, timeout=12.0)
        print(f"  wait_for_stop returned after {t_first - t_sent + 0.3:.2f}s: {first.get('result')}")
        p_reply, t_p = await c.recv_reply(pid, timeout=12.0)
        print(f"  pause replied {t_p - t_sent:.2f}s after being sent: {p_reply.get('result')}")
        if (t_p - t_sent) > 5.0 and first.get("result", {}).get("reason") == "timeout":
            print("  => CONFIRMED: pause starved behind its own long-poll;")
            print("     wait_for_stop timed out instead of seeing the pause.")
        st = await c.call("get_run_state")
        print(f"  run_state after: {st.get('result')}")

        await c.close()
    finally:
        if proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                proc.kill()

    print()
    if serialized is True:
        print("RESULT: monitor stub SERIALIZES requests per connection.")
        print("        MonitorSession's concurrent wait_for_stop watcher is unsound.")
        return 0
    if serialized is False:
        print("RESULT: monitor stub pipelines; serialization hypothesis REJECTED.")
        return 0
    print("RESULT: inconclusive")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
