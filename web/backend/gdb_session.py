"""Owns the single GDB client connection to one XRoar instance.

The backend is the *only* thing speaking to XRoar's GDB stub. We launch
``m6809-gdb --interpreter=mi`` as a child, then ``-target-select remote
:PORT`` against the XRoar stub. Commands are tokenised; results dispatch back
to ``asyncio.Future``s.

The MI parser here is intentionally minimal — it extracts what the UI needs
(``^done`` payload, ``^error`` message, ``*stopped`` frame address, console
``~"..."`` stream output) and treats everything else as opaque log lines.
"""
from __future__ import annotations
import asyncio
import re
import shlex
from typing import Awaitable, Callable, Optional


GDB_BIN = "/usr/local/bin/m6809-gdb"

# MI record patterns ------------------------------------------------------
_RE_RESULT = re.compile(r'^(\d+)\^(done|running|connected|error|exit)(?:,(.*))?$')
_RE_ASYNC_EXEC = re.compile(r'^\*(stopped|running)(?:,(.*))?$')
_RE_STREAM = re.compile(r'^([~@&])"(.*)"$')   # console / target / log stream
_RE_NOTIFY = re.compile(r'^[=](\S+)(?:,(.*))?$')

_RE_ADDR_IN_STOPPED = re.compile(r'frame=\{[^}]*addr="(0x[0-9a-fA-F]+)"')
_RE_MEM_CONTENTS = re.compile(r'contents="([0-9a-fA-F]+)"')
_RE_BP_NUM = re.compile(r'bkpt=\{[^}]*number="(\d+)"')
_RE_ERROR_MSG = re.compile(r'msg="((?:[^"\\]|\\.)*)"')

# `info registers` console line for m6809-gdb. Output looks like
#   "PC=0x6648 26184\n S=" then "0x1ffe 8190\n U=" etc. — multiple
# registers per stream record, NAME=0xVAL separated by varying whitespace.
_RE_REG_PAIR = re.compile(r'\b([A-Za-z]{1,3})\s*=\s*0x([0-9a-fA-F]+)')


class GdbError(RuntimeError):
    pass


class GdbSession:
    def __init__(
        self,
        gdb_port: int,
        on_async: Optional[Callable[[str, dict], Awaitable[None]]] = None,
        on_log: Optional[Callable[[str], Awaitable[None]]] = None,
    ):
        self.gdb_port = gdb_port
        self.on_async = on_async
        self.on_log = on_log
        self._proc: Optional[asyncio.subprocess.Process] = None
        self._reader_task: Optional[asyncio.Task] = None
        self._token = 0
        self._pending: dict = {}
        self._console_buf: list = []
        self._capture_console = False
        self._stopped_waiters: list = []

    # ---- lifecycle ----------------------------------------------------

    async def attach(self) -> None:
        # Spawn gdb idle, then send `target remote` as a plain CLI line
        # (no MI wrapping). XRoar 1.10's stub answers vMustReplyEmpty with
        # the literal "timeout", which gdb maps to a fatal MI error if the
        # connect was issued via -ex or -interpreter-exec. The raw stdin CLI
        # path tolerates the bogus reply. Attach success is signalled by the
        # *stopped event the stub emits when the target halts on connect.
        self._proc = await asyncio.create_subprocess_exec(
            GDB_BIN, "--interpreter=mi", "--quiet", "-nx",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        self._reader_task = asyncio.create_task(self._reader_loop())

        loop = asyncio.get_running_loop()
        stopped: asyncio.Future = loop.create_future()
        self._stopped_waiters.append(stopped)
        try:
            line = f"target remote 127.0.0.1:{self.gdb_port}\n".encode()
            self._proc.stdin.write(line)
            await self._proc.stdin.drain()
            await asyncio.wait_for(stopped, timeout=60.0)
        except asyncio.TimeoutError:
            raise GdbError("target remote: no *stopped within 60s")
        finally:
            if stopped in self._stopped_waiters:
                self._stopped_waiters.remove(stopped)

    async def detach(self) -> None:
        if self._proc and self._proc.returncode is None:
            try:
                self._proc.stdin.write(b"-gdb-exit\n")
                await self._proc.stdin.drain()
            except Exception:
                pass
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                self._proc.terminate()
                try:
                    await asyncio.wait_for(self._proc.wait(), timeout=1.0)
                except asyncio.TimeoutError:
                    self._proc.kill()
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except (asyncio.CancelledError, Exception):
                pass
        self._proc = None
        self._reader_task = None
        # Fail any still-pending futures.
        for fut in list(self._pending.values()):
            if not fut.done():
                fut.set_exception(GdbError("gdb session closed"))
        self._pending.clear()

    # ---- public commands ---------------------------------------------

    async def cont(self) -> None:
        await self._cmd("-exec-continue")

    async def step(self) -> None:
        await self._cmd("-exec-step-instruction")

    async def interrupt(self) -> None:
        await self._cmd("-exec-interrupt")

    async def set_breakpoint(self, addr: int) -> str:
        result = await self._cmd(f"-break-insert *0x{addr:04x}")
        m = _RE_BP_NUM.search(result.get("payload", ""))
        if not m:
            raise GdbError(f"could not parse breakpoint number from: {result}")
        return m.group(1)

    async def clear_breakpoint(self, bp_id: str) -> None:
        await self._cmd(f"-break-delete {bp_id}")

    async def disable_breakpoint(self, bp_id: str) -> None:
        await self._cmd(f"-break-disable {bp_id}")

    async def enable_breakpoint(self, bp_id: str) -> None:
        await self._cmd(f"-break-enable {bp_id}")

    async def read_memory(self, addr: int, length: int) -> bytes:
        result = await self._cmd(f"-data-read-memory-bytes 0x{addr:04x} {length}")
        m = _RE_MEM_CONTENTS.search(result.get("payload", ""))
        if not m:
            raise GdbError(f"no memory contents in response: {result}")
        return bytes.fromhex(m.group(1))

    async def read_registers(self) -> dict:
        # Tunnel through console "info registers". m6809-gdb prints the
        # documented registers then ^errors out with "Register 12 is not
        # available" (it knows 13 registers, only 12 are exposed by the
        # stub). The accumulated console output is still valid — keep it.
        self._console_buf.clear()
        self._capture_console = True
        try:
            try:
                await self._cmd('-interpreter-exec console "info registers"')
            except GdbError:
                pass  # trailing error is expected — registers already streamed
        finally:
            self._capture_console = False

        # m6809-gdb often splits a single "NAME=0xVAL" pair across two MI
        # stream records (NAME= ends one record, 0xVAL starts the next),
        # so we have to scan the joined text, not each record in isolation.
        text = "".join(self._console_buf)
        regs: dict = {}
        for m in _RE_REG_PAIR.finditer(text):
            regs[m.group(1).lower()] = int(m.group(2), 16)
        return regs

    # ---- internals ---------------------------------------------------

    async def _cmd(self, mi_cmd: str, timeout: float = 5.0) -> dict:
        if not self._proc or self._proc.returncode is not None:
            raise GdbError("gdb not running")
        self._token += 1
        token = self._token
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        self._pending[token] = fut
        line = f"{token}{mi_cmd}\n".encode()
        self._proc.stdin.write(line)
        await self._proc.stdin.drain()
        try:
            result = await asyncio.wait_for(fut, timeout=timeout)
        finally:
            self._pending.pop(token, None)
        if result.get("class") == "error":
            m = _RE_ERROR_MSG.search(result.get("payload", "") or "")
            raise GdbError(m.group(1) if m else result.get("payload", "gdb error"))
        return result

    async def _reader_loop(self) -> None:
        assert self._proc and self._proc.stdout
        while True:
            raw = await self._proc.stdout.readline()
            if not raw:
                return
            line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
            if not line or line == "(gdb)":
                continue
            await self._dispatch(line)

    async def _dispatch(self, line: str) -> None:
        # Result record (synchronous reply)
        m = _RE_RESULT.match(line)
        if m:
            token = int(m.group(1))
            cls = m.group(2)
            payload = m.group(3) or ""
            fut = self._pending.get(token)
            if fut and not fut.done():
                fut.set_result({"class": cls, "payload": payload})
            return

        # Async exec record: *stopped, *running
        m = _RE_ASYNC_EXEC.match(line)
        if m:
            cls = m.group(1)
            payload = m.group(2) or ""
            info: dict = {"raw": payload}
            if cls == "stopped":
                am = _RE_ADDR_IN_STOPPED.search(payload)
                if am:
                    info["pc"] = int(am.group(1), 16)
                # Wake any attach()-style waiter.
                for fut in list(self._stopped_waiters):
                    if not fut.done():
                        fut.set_result(info)
            if self.on_async:
                await self.on_async(cls, info)
            return

        # Stream record
        m = _RE_STREAM.match(line)
        if m:
            kind, content = m.group(1), _unescape(m.group(2))
            if kind == "~" and self._capture_console:
                self._console_buf.append(content)
            if self.on_log:
                await self.on_log(content)
            return

        # Notify / unrecognised — forward as log if hook present.
        if self.on_log:
            await self.on_log(line)


def _unescape(s: str) -> str:
    return (s.replace(r'\n', '\n')
             .replace(r'\t', '\t')
             .replace(r'\"', '"')
             .replace(r'\\', '\\'))
