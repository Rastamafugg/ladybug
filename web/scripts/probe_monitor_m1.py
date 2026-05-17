"""Phase 3 M1 verification probe for the XRoar -monitor JSON-RPC stub.

Verifies the M1 scope from wiki/implementation/xroar-monitor.md:

  1. Listener boots on the requested port.
  2. On client connect, a `hello` notification is delivered with
     xroar_version, monitor_protocol_version, machine_name fields.
  3. `-monitor-halt-on-start` initial state == "halted".
  4. `get_run_state` round-trips.
  5. `run` flips state to "running"; `pause` flips it back to "halted".
  6. Unknown methods return JSON-RPC -32601.
  7. Malformed JSON returns -32700, connection survives.
  8. Disconnect-and-reconnect within a single XRoar lifetime works.

Run inside WSL from repo root:
    python3 web/scripts/probe_monitor_m1.py

Sets exit code 0 on pass, 1 on any failure.
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

    async def send_raw(self, raw: bytes) -> None:
        assert self._writer is not None
        self._writer.write(raw)
        await self._writer.drain()


async def wait_for_port(host: str, port: int, timeout: float = 5.0) -> None:
    deadline = asyncio.get_event_loop().time() + timeout
    last_err: Exception | None = None
    while asyncio.get_event_loop().time() < deadline:
        try:
            r, w = await asyncio.open_connection(host, port)
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


def fail(msg: str, ok_box: list) -> None:
    print(f"  FAIL: {msg}")
    ok_box[0] = False


def passed(msg: str) -> None:
    print(f"  OK: {msg}")


async def run() -> int:
    port = pick_port()
    print(f"probe: launching {XROAR_BIN} with -monitor 127.0.0.1:{port} -monitor-halt-on-start")
    if not Path(XROAR_BIN).exists():
        print(f"FAIL: xroar-monitor binary not found at {XROAR_BIN}", file=sys.stderr)
        return 2

    proc = await asyncio.create_subprocess_exec(
        XROAR_BIN,
        "-machine", "coco3", "-ram", "512",
        "-monitor", f"127.0.0.1:{port}",
        "-monitor-halt-on-start",
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    ok_box = [True]
    try:
        await wait_for_port("127.0.0.1", port, timeout=5.0)

        # --- Test 1: connect, receive hello ---
        print("\n== Test 1: hello on connect ==")
        c1 = MonitorClient("127.0.0.1", port)
        await c1.connect()
        hello = await c1.recv_line()
        if hello.get("method") != "hello":
            fail(f"expected method=hello, got {hello}", ok_box)
        else:
            passed("hello received")
        params = hello.get("params", {})
        for key in ("xroar_version", "monitor_protocol_version", "machine_name"):
            if not isinstance(params.get(key), str) or not params[key]:
                fail(f"hello.params.{key} missing or not a string: {params.get(key)!r}", ok_box)
            else:
                passed(f"hello.params.{key} = {params[key]!r}")
        if params.get("run_state") != "halted":
            fail(f"hello run_state should be 'halted', got {params.get('run_state')!r}", ok_box)
        else:
            passed("hello run_state = 'halted' (halt-on-start)")

        # --- Test 2: get_run_state returns halted ---
        print("\n== Test 2: get_run_state == halted ==")
        reply = await c1.call("get_run_state")
        st = reply.get("result", {}).get("state")
        if st != "halted":
            fail(f"expected state=halted, got {reply}", ok_box)
        else:
            passed("state=halted")

        # --- Test 3: run -> running ---
        print("\n== Test 3: run flips to running ==")
        reply = await c1.call("run")
        if not reply.get("result", {}).get("ok"):
            fail(f"run did not return ok: {reply}", ok_box)
        reply = await c1.call("get_run_state")
        st = reply.get("result", {}).get("state")
        if st != "running":
            fail(f"after run, expected state=running, got {st!r}", ok_box)
        else:
            passed("state=running after run")

        # --- Test 4: pause -> halted ---
        print("\n== Test 4: pause flips to halted ==")
        reply = await c1.call("pause")
        if not reply.get("result", {}).get("ok"):
            fail(f"pause did not return ok: {reply}", ok_box)
        reply = await c1.call("get_run_state")
        st = reply.get("result", {}).get("state")
        if st != "halted":
            fail(f"after pause, expected state=halted, got {st!r}", ok_box)
        else:
            passed("state=halted after pause")

        # --- Test 5: unknown method -> -32601 ---
        print("\n== Test 5: unknown method returns -32601 ==")
        reply = await c1.call("no_such_method")
        code = reply.get("error", {}).get("code")
        if code != -32601:
            fail(f"expected -32601, got {reply}", ok_box)
        else:
            passed("unknown method -> -32601")

        # --- Test 6: malformed JSON -> -32700, connection survives ---
        print("\n== Test 6: malformed JSON -> -32700 (connection survives) ==")
        await c1.send_raw(b"{this is not json\n")
        reply = await c1.recv_line()
        code = reply.get("error", {}).get("code")
        if code != -32700:
            fail(f"expected -32700 parse error, got {reply}", ok_box)
        else:
            passed("malformed JSON -> -32700")
        # Verify still usable
        reply = await c1.call("get_run_state")
        if reply.get("result", {}).get("state") not in ("halted", "running"):
            fail(f"connection unusable after parse error: {reply}", ok_box)
        else:
            passed("connection still usable after parse error")

        # --- Test 7: disconnect / reconnect within same XRoar lifetime ---
        print("\n== Test 7: disconnect + reconnect ==")
        await c1.close()
        await asyncio.sleep(0.2)
        c2 = MonitorClient("127.0.0.1", port)
        await c2.connect()
        hello2 = await c2.recv_line()
        if hello2.get("method") != "hello":
            fail(f"reconnect: hello not received, got {hello2}", ok_box)
        else:
            passed("reconnect hello received")
        # State should be preserved across reconnects: still halted from Test 4.
        reply = await c2.call("get_run_state")
        st = reply.get("result", {}).get("state")
        if st != "halted":
            fail(f"state not preserved across reconnect: {st!r}", ok_box)
        else:
            passed("run-state preserved across reconnect (halted)")
        await c2.close()

    finally:
        if proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                proc.kill()

    print()
    if ok_box[0]:
        print("PASS: M1 probe green")
        return 0
    print("FAIL: M1 probe red")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
