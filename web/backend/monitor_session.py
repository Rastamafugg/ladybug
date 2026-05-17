"""Owns the single JSON-RPC client connection to one XRoar -monitor stub.

Speaks XRoar's project-private monitor protocol (v0.6.x, plan in
wiki/implementation/xroar-monitor.md). Line-delimited JSON-RPC 2.0 over TCP.

The shape of this class intentionally mirrors the retired GdbSession so
that callers (instance.py, main.py) need only swap the import and the
attribute name. Differences from gdb-stub semantics are documented inline
where they affect callers.
"""
from __future__ import annotations
import asyncio
import json
from typing import Any, Awaitable, Callable, Optional


# 6809 register set the monitor returns. Order matches gdb-stub's old
# read_registers() return value so callers see the same keys.
_REG_KEYS = ("a", "b", "d", "cc", "dp", "x", "y", "u", "s", "pc")


class MonitorError(RuntimeError):
    def __init__(self, message: str, code: Optional[int] = None, data: Any = None):
        super().__init__(message)
        self.code = code
        self.data = data


class MonitorSession:
    def __init__(
        self,
        port: int,
        on_async: Optional[Callable[[str, dict], Awaitable[None]]] = None,
        on_log: Optional[Callable[[str], Awaitable[None]]] = None,
        host: str = "127.0.0.1",
    ):
        self.port = port
        self.host = host
        self.on_async = on_async
        self.on_log = on_log
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._reader_task: Optional[asyncio.Task] = None
        self._halt_watcher_task: Optional[asyncio.Task] = None
        self._next_id = 1
        self._pending: dict[int, asyncio.Future] = {}
        self._hello_fut: Optional[asyncio.Future] = None
        # Single-shot guard so a `bp` event and a `wait_for_stop` return
        # produced by the same halt only fire one on_async("stopped").
        self._halt_cycle: Optional[asyncio.Event] = None

    # ---- lifecycle ----------------------------------------------------

    async def attach(self) -> None:
        loop = asyncio.get_running_loop()
        self._hello_fut = loop.create_future()
        self._reader, self._writer = await asyncio.open_connection(self.host, self.port)
        self._reader_task = asyncio.create_task(self._reader_loop())

        try:
            hello = await asyncio.wait_for(self._hello_fut, timeout=10.0)
        except asyncio.TimeoutError:
            await self.detach()
            raise MonitorError("monitor: no hello within 10s")

        # Subscribe to the events we care about for run-state tracking.
        try:
            await self._call("events.subscribe", {"kinds": ["bp", "reset"]})
        except MonitorError:
            # Older stubs may not have events.subscribe; not fatal for v1
            # callers that only need synchronous commands.
            pass

        # If the stub was launched with -monitor-halt-on-start, the hello
        # already reports halted. Synthesize a `stopped` so instance.py
        # transitions to HALTED without a separate path.
        if hello.get("run_state") == "halted" and self.on_async is not None:
            pc = None
            try:
                regs = await self.read_registers()
                pc = regs.get("pc")
            except Exception:
                pass
            await self.on_async("stopped", {"pc": pc, "reason": "attach"})

    async def detach(self) -> None:
        # Cancel halt watcher first so it doesn't race with socket close.
        if self._halt_watcher_task:
            self._halt_watcher_task.cancel()
            try:
                await self._halt_watcher_task
            except (asyncio.CancelledError, Exception):
                pass
            self._halt_watcher_task = None

        if self._writer is not None:
            try:
                self._writer.close()
                try:
                    await self._writer.wait_closed()
                except Exception:
                    pass
            except Exception:
                pass
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except (asyncio.CancelledError, Exception):
                pass
        self._reader = None
        self._writer = None
        self._reader_task = None
        # Fail any still-pending request futures.
        for fut in list(self._pending.values()):
            if not fut.done():
                fut.set_exception(MonitorError("monitor session closed"))
        self._pending.clear()

    # ---- execution control --------------------------------------------

    async def cont(self) -> None:
        """Resume CPU. Fires on_async('running') immediately; halt watcher
        will fire on_async('stopped') when the CPU next halts (BP, pause,
        watchpoint, etc.)."""
        self._begin_halt_cycle()
        await self._call("run")
        if self.on_async is not None:
            await self.on_async("running", {})
        # Spawn (or replace) the halt watcher. wait_for_stop long-polls
        # server-side and returns as soon as a stop reason exists.
        if self._halt_watcher_task:
            self._halt_watcher_task.cancel()
        self._halt_watcher_task = asyncio.create_task(self._halt_watcher())

    async def step(self) -> None:
        """Single instruction step. The monitor returns immediately; we
        then wait_for_stop to obtain the resulting PC + reason."""
        await self._call("step_instruction", {"n": 1})
        stop = await self._call("wait_for_stop", {"timeout_ms": 5000})
        if self.on_async is not None:
            await self.on_async("stopped", {
                "pc": stop.get("pc"),
                "reason": stop.get("reason", "step"),
            })

    async def interrupt(self) -> None:
        """Halt a running CPU."""
        # Pre-arm the cycle so the halt watcher's eventual wake-up is a no-op.
        self._begin_halt_cycle()
        await self._call("pause")
        # `pause` reply is just {ok}; pull PC via get_run_state.
        pc = None
        try:
            st = await self._call("get_run_state")
            pc = st.get("last_stop_pc")
        except Exception:
            pass
        if self.on_async is not None:
            await self._emit_stopped({"pc": pc, "reason": "pause"})

    # ---- breakpoints --------------------------------------------------

    async def set_breakpoint(self, addr: int) -> str:
        result = await self._call("set_breakpoint", {"addr": addr, "kind": "exec"})
        bp_id = result.get("id")
        if bp_id is None:
            raise MonitorError(f"set_breakpoint returned no id: {result}")
        return str(bp_id)

    async def clear_breakpoint(self, bp_id: str) -> None:
        await self._call("clear_breakpoint", {"id": int(bp_id)})

    async def enable_breakpoint(self, bp_id: str) -> None:
        # Monitor protocol v0.6 has no per-BP enable/disable; deferred.
        raise NotImplementedError("enable_breakpoint: monitor protocol has no per-BP toggle")

    async def disable_breakpoint(self, bp_id: str) -> None:
        raise NotImplementedError("disable_breakpoint: monitor protocol has no per-BP toggle")

    async def list_breakpoints(self) -> list[dict]:
        result = await self._call("list_breakpoints")
        return result.get("breakpoints", [])

    # ---- memory / registers -------------------------------------------

    async def read_memory(self, addr: int, length: int, space: str = "cpu") -> bytes:
        # Plan caps reads at 64 KB. Chunk if the caller asks for more.
        if length <= 0:
            return b""
        chunks: list[bytes] = []
        remaining = length
        cur = addr
        while remaining > 0:
            n = min(remaining, 0xFFFF)
            result = await self._call("read_memory", {
                "addr": cur, "length": n, "space": space,
            })
            data_hex = result.get("data", "")
            chunks.append(bytes.fromhex(data_hex))
            cur += n
            remaining -= n
        return b"".join(chunks)

    async def write_memory(self, addr: int, data: bytes, space: str = "cpu") -> None:
        # Halted-only; server returns target_running error if running.
        await self._call("write_memory", {
            "addr": addr, "space": space, "data": data.hex(),
        })

    async def read_registers(self) -> dict:
        result = await self._call("read_registers")
        return {k: result[k] for k in _REG_KEYS if k in result}

    async def write_registers(self, regs: dict) -> None:
        await self._call("write_registers", regs)

    # ---- GIME state (ready for WS-B; not yet wired by main.py) --------

    async def read_gime_state(self) -> dict:
        return await self._call("read_gime_state")

    # ---- run-state helpers --------------------------------------------

    async def get_run_state(self) -> dict:
        return await self._call("get_run_state")

    async def reset(self, kind: str = "soft") -> None:
        await self._call("reset", {"kind": kind})

    # ---- internals ----------------------------------------------------

    def _begin_halt_cycle(self) -> None:
        # New cycle: clear any previous single-shot guard.
        self._halt_cycle = asyncio.Event()

    async def _emit_stopped(self, info: dict) -> None:
        """Fire on_async('stopped', info) at most once per halt cycle."""
        if self._halt_cycle is None or self._halt_cycle.is_set():
            return
        self._halt_cycle.set()
        if self._halt_watcher_task and not self._halt_watcher_task.done():
            self._halt_watcher_task.cancel()
        if self.on_async is not None:
            await self.on_async("stopped", info)

    async def _halt_watcher(self) -> None:
        """Long-poll wait_for_stop while running. Reports the first stop
        we see. Cooperates with the `bp` event path via _emit_stopped's
        single-shot guard."""
        try:
            while True:
                try:
                    stop = await self._call("wait_for_stop", {"timeout_ms": 30000})
                except MonitorError:
                    return
                reason = stop.get("reason")
                if reason in (None, "timeout"):
                    continue  # nothing happened in 30s; loop
                await self._emit_stopped({
                    "pc": stop.get("pc"),
                    "reason": reason,
                    "bp_id": stop.get("bp_id"),
                })
                return
        except asyncio.CancelledError:
            return

    async def _call(self, method: str, params: Optional[dict] = None,
                    timeout: float = 60.0) -> dict:
        if self._writer is None or self._reader is None:
            raise MonitorError("monitor session not connected")
        loop = asyncio.get_running_loop()
        rid = self._next_id
        self._next_id += 1
        fut: asyncio.Future = loop.create_future()
        self._pending[rid] = fut
        req: dict = {"jsonrpc": "2.0", "id": rid, "method": method}
        if params is not None:
            req["params"] = params
        try:
            self._writer.write((json.dumps(req) + "\n").encode())
            await self._writer.drain()
            return await asyncio.wait_for(fut, timeout=timeout)
        finally:
            self._pending.pop(rid, None)

    async def _reader_loop(self) -> None:
        assert self._reader is not None
        while True:
            try:
                raw = await self._reader.readline()
            except Exception:
                return
            if not raw:
                # Connection closed; fail pending.
                for fut in list(self._pending.values()):
                    if not fut.done():
                        fut.set_exception(MonitorError("monitor: connection closed"))
                self._pending.clear()
                return
            line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
            if not line:
                continue
            try:
                msg = json.loads(line)
            except Exception:
                if self.on_log is not None:
                    await self.on_log("[monitor] non-JSON: " + line)
                continue
            await self._dispatch(msg)

    async def _dispatch(self, msg: dict) -> None:
        if "id" in msg and ("result" in msg or "error" in msg):
            rid = msg["id"]
            fut = self._pending.get(rid)
            if fut is None or fut.done():
                return
            if "error" in msg:
                err = msg["error"] or {}
                fut.set_exception(MonitorError(
                    err.get("message", "monitor error"),
                    code=err.get("code"),
                    data=err.get("data"),
                ))
            else:
                fut.set_result(msg.get("result") or {})
            return

        method = msg.get("method")
        if method == "hello":
            if self._hello_fut is not None and not self._hello_fut.done():
                self._hello_fut.set_result(msg.get("params") or {})
            return
        if method == "goodbye":
            if self.on_log is not None:
                await self.on_log("[monitor] goodbye")
            return

        # Event notification (bp, reset, vbord, etc.)
        params = msg.get("params") or {}
        if method == "bp":
            await self._emit_stopped({
                "pc": params.get("pc"),
                "reason": "breakpoint",
                "bp_id": (str(params["bp_id"]) if "bp_id" in params else None),
            })
            return
        if method == "reset" and self.on_async is not None:
            await self.on_async("reset", params)
            return
        # Unhandled event kinds (vbord, etc.) — log only.
        if self.on_log is not None:
            await self.on_log(f"[monitor] event {method}: {params}")
