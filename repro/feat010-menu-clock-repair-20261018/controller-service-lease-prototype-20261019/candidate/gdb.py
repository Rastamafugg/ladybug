"""GDB session management for gdb-mcp.

Each GdbSession owns one GDB subprocess launched with --interpreter=mi2.
Commands are sent as plain GDB CLI text; responses are read until the
(gdb) prompt and converted from MI2 framing into clean human-readable text
before being returned to callers.

MI2 output record types handled:
  ~"..."    console stream  → included in output (GDB's own messages)
  @"..."    target stream   → included in output (inferior stdout/stderr)
  &"..."    log stream      → skipped (command echo)
  ^done     result record   → terminates read loop (no output)
  ^running  result record   → sets waiting_for_stop; suppresses intermediate prompt
  ^exit     result record   → terminates read loop (no output)
  ^error,msg="..."          → formatted as "Error: ..."
  *stopped,...              → formatted as "[Stopped: reason, func, file:line]"
                              clears waiting_for_stop; next (gdb) terminates loop
  =...      notify record   → skipped
  *running  async record    → skipped
"""

import asyncio
import math
import re
import shlex
import signal
import uuid
from collections.abc import Coroutine
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any, Callable, NotRequired, TypedDict


# Matches the GDB/MI prompt line: "(gdb)" or "(gdb) "
_PROMPT_RE = re.compile(r"^\(gdb\)\s*$")

# Matches MI stream records:  ~"content"  @"content"  &"content"
_STREAM_RE = re.compile(r'^([~@&])"(.*)"$')


class GdbError(Exception):
    pass


class OwnedSessionSnapshot(TypedDict):
    owner_id: str
    state: str
    session_id: str | None
    exit_confirmed: bool
    returncode: int | None
    error_code: NotRequired[str]


def _retain_task(
    task_set: set[asyncio.Task], task: asyncio.Task
) -> asyncio.Task:
    task_set.add(task)

    def _finished(done: asyncio.Task) -> None:
        task_set.discard(done)
        if not done.cancelled():
            # A deadline waiter may have stopped observing this task while it
            # continues safely in the background. Retrieve any late exception.
            try:
                done.exception()
            except Exception:
                pass

    task.add_done_callback(_finished)
    return task


async def _await_task_until(task: asyncio.Task, deadline: float):
    """Wait without cancelling work that may still own a process or stream."""
    loop = asyncio.get_running_loop()
    if loop.time() >= deadline:
        raise asyncio.TimeoutError
    if task.done():
        try:
            result = task.result()
        except BaseException:
            if loop.time() >= deadline:
                raise asyncio.TimeoutError
            raise
        if loop.time() >= deadline:
            raise asyncio.TimeoutError
        return result
    remaining = deadline - loop.time()
    if remaining <= 0:
        raise asyncio.TimeoutError
    done, _ = await asyncio.wait({task}, timeout=remaining)
    if task not in done or loop.time() >= deadline:
        raise asyncio.TimeoutError
    try:
        result = task.result()
    except BaseException:
        if loop.time() >= deadline:
            raise asyncio.TimeoutError
        raise
    if loop.time() >= deadline:
        raise asyncio.TimeoutError
    return result


def _ensure_before_deadline(deadline: float) -> None:
    if asyncio.get_running_loop().time() >= deadline:
        raise asyncio.TimeoutError


def _unescape(s: str) -> str:
    """Unescape GDB MI C-style string escapes (content between outer quotes).

    Handles: simple escapes (\\n \\t \\r \\\\ \\" \\a \\b \\f \\v),
             octal sequences (\\NNN), and hex sequences (\\xNN).
    Unknown escapes are passed through with the backslash preserved.
    """
    _SIMPLE = {
        "n": "\n", "t": "\t", "r": "\r", "\\": "\\", '"': '"',
        "a": "\a", "b": "\b", "f": "\f", "v": "\v",
    }
    result: list[str] = []
    i = 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s):
            c = s[i + 1]
            if c in _SIMPLE:
                result.append(_SIMPLE[c])
                i += 2
            elif c == "x" and i + 3 < len(s) and all(h in "0123456789abcdefABCDEF" for h in s[i+2:i+4]):
                result.append(chr(int(s[i+2:i+4], 16)))
                i += 4
            elif c in "01234567":
                j = i + 1
                while j < min(i + 4, len(s)) and s[j] in "01234567":
                    j += 1
                result.append(chr(int(s[i+1:j], 8)))
                i = j
            else:
                result.append("\\" + c)  # preserve unknown escapes intact
                i += 2
        else:
            result.append(s[i])
            i += 1
    return "".join(result)


def _format_output(lines: list[str]) -> str:
    """Convert raw MI2 output lines into clean human-readable text."""
    parts: list[str] = []
    for line in lines:
        m = _STREAM_RE.match(line)
        if m:
            kind, content = m.group(1), m.group(2)
            if kind in ("~", "@"):           # console + target output → keep
                parts.append(_unescape(content))
            # & (log / command echo) → skip
        elif line.startswith("^error"):
            msg_m = re.search(r'msg="((?:[^"\\]|\\.)*)"', line)
            msg = _unescape(msg_m.group(1)) if msg_m else line
            parts.append(f"Error: {msg}\n")
        elif line.startswith("*stopped"):
            reason_m = re.search(r'reason="([^"]+)"', line)
            func_m   = re.search(r'func="([^"]+)"', line)
            file_m   = re.search(r'file="([^"]+)"', line)
            lineno_m = re.search(r'\bline="([^"]+)"', line)
            info: list[str] = []
            if reason_m: info.append(reason_m.group(1))
            if func_m:   info.append(f"in {func_m.group(1)}")
            if file_m and lineno_m:
                info.append(f"at {file_m.group(1)}:{lineno_m.group(1)}")
            parts.append(f"[Stopped: {', '.join(info)}]\n" if info else f"[{line}]\n")
        elif line and line[0] not in "^*=":
            # Raw text not matching any MI record prefix — pass through.
            # Catches warnings from stderr or other non-MI-framed output
            # (e.g. libthread_db messages, dynamic linker warnings).
            parts.append(line + "\n")
        # ^done, ^running, ^exit, =..., *running → no content, skip
    return "".join(parts)


@dataclass
class GdbSession:
    id: str
    process: asyncio.subprocess.Process
    kind: str = "gdb"  # "gdb" or "rr-replay"
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    _broken: bool = field(default=False, repr=False)
    _pending_tasks: set[asyncio.Task] = field(default_factory=set, repr=False)
    _wait_task: asyncio.Task | None = field(default=None, repr=False)
    _close_task: asyncio.Task | None = field(default=None, repr=False)
    _exit_callback: Callable[["GdbSession", int], None] | None = field(
        default=None, repr=False
    )
    _exit_confirmed: bool = field(default=False, repr=False)
    _exit_returncode: int | None = field(default=None, repr=False)
    _quit_attempted: bool = field(default=False, repr=False)
    _terminate_attempted: bool = field(default=False, repr=False)
    _kill_attempted: bool = field(default=False, repr=False)
    _closing: bool = field(default=False, repr=False)

    async def send(self, cmd: str, timeout: float = 30.0) -> str:
        """Send one command under a single monotonic deadline."""
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
            raise GdbError("timeout must be a finite positive number")
        try:
            timeout_seconds = float(timeout)
        except (OverflowError, ValueError) as exc:
            raise GdbError("timeout must be a finite positive number") from exc
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise GdbError("timeout must be a finite positive number")
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        return await self._send_until(cmd, deadline)

    async def _send_until(self, cmd: str, deadline: float) -> str:
        if self._closing or self._exit_confirmed:
            raise GdbError("Session is closing or has exited")
        if self._broken:
            raise GdbError(
                "Session is tainted by a previous timeout and cannot be used; "
                "call stop_session and start a new one"
            )
        if "\n" in cmd:
            raise GdbError(
                "Command contains embedded newlines; "
                "use batch_commands to send multiple commands"
            )
        task = _retain_task(
            self._pending_tasks,
            asyncio.create_task(self._send_operation(cmd, deadline)),
        )
        try:
            return await _await_task_until(task, deadline)
        except asyncio.TimeoutError as exc:
            self._broken = True
            raise GdbError(f"Command deadline expired: {cmd!r}") from exc
        except asyncio.CancelledError:
            self._broken = True
            raise

    def _check_send_admission(self, deadline: float) -> None:
        if self._closing or self._exit_confirmed:
            raise GdbError("Session is closing or has exited")
        if self._broken:
            raise GdbError("Session is tainted and cannot admit another command")
        _ensure_before_deadline(deadline)

    async def _send_operation(self, cmd: str, deadline: float) -> str:
        lines: list[str] = []
        self._check_send_admission(deadline)
        async with self._lock:
            self._check_send_admission(deadline)
            self.process.stdin.write((cmd + "\n").encode())
            self._check_send_admission(deadline)
            await self.process.stdin.drain()
            self._check_send_admission(deadline)

            # MI2 execution commands may emit an intermediate prompt after
            # ^running and a final prompt after *stopped.
            waiting_for_stop = False
            while True:
                self._check_send_admission(deadline)
                raw = await self.process.stdout.readline()
                self._check_send_admission(deadline)
                if not raw:
                    raise GdbError("GDB process exited unexpectedly")
                line = raw.decode(errors="replace").rstrip("\n")
                if _PROMPT_RE.match(line):
                    if not waiting_for_stop:
                        return _format_output(lines)
                    # Keep reading after the intermediate (gdb) prompt.
                else:
                    lines.append(line)
                    if line.startswith("^running"):
                        waiting_for_stop = True
                    elif line.startswith("*stopped"):
                        waiting_for_stop = False
    def interrupt(self) -> None:
        """Send SIGINT to interrupt a running inferior.

        This does NOT acquire the session lock, so it can be called while
        a run/continue command is blocking.  The SIGINT causes GDB to stop
        the inferior and emit a *stopped record, which unblocks the pending
        send() call.
        """
        if self.process.returncode is None:
            self.process.send_signal(signal.SIGINT)

    async def close(self, *, budget_ms: int | float = 7000) -> int | None:
        """Close using one deadline and return only a confirmed child exit."""
        deadline = self._deadline_from_budget(budget_ms)
        return await self._close_until(deadline)

    @staticmethod
    def _deadline_from_budget(budget_ms: int | float) -> float:
        if isinstance(budget_ms, bool) or not isinstance(budget_ms, (int, float)):
            raise GdbError("budget_ms must be a finite positive number")
        try:
            budget_value = float(budget_ms)
        except (OverflowError, ValueError) as exc:
            raise GdbError("budget_ms must be a finite positive number") from exc
        if not math.isfinite(budget_value) or budget_value <= 0:
            raise GdbError("budget_ms must be a finite positive number")
        return asyncio.get_running_loop().time() + budget_value / 1000.0

    async def _close_until(self, deadline: float) -> int | None:
        self._closing = True
        if self._exit_confirmed:
            return self._exit_returncode
        task = self._close_task
        if task is None or task.done():
            task = _retain_task(
                self._pending_tasks,
                asyncio.create_task(self._close_work(deadline)),
            )
            self._close_task = task
        try:
            result = await _await_task_until(task, deadline)
        except asyncio.TimeoutError:
            return self._exit_returncode if self._exit_confirmed else None
        except asyncio.CancelledError:
            # Keep the close task and its one-shot signal state addressable.
            raise
        except Exception:
            return None
        return result if type(result) is int else None

    async def _quit_and_drain(self, deadline: float) -> None:
        _ensure_before_deadline(deadline)
        self.process.stdin.write(b"quit\n")
        _ensure_before_deadline(deadline)
        await self.process.stdin.drain()
        _ensure_before_deadline(deadline)

    async def _wait_for_child_until(self, deadline: float) -> bool:
        if self._exit_confirmed:
            return True
        if self._wait_task is None or self._wait_task.done():
            if self._wait_task is not None:
                try:
                    prior = self._wait_task.result()
                except BaseException:
                    prior = None
                if type(prior) is int:
                    return self._exit_confirmed
            self._wait_task = _retain_task(
                self._pending_tasks,
                asyncio.create_task(self._wait_for_direct_child()),
            )
        try:
            await _await_task_until(self._wait_task, deadline)
        except asyncio.TimeoutError:
            return self._exit_confirmed
        except Exception:
            return self._exit_confirmed
        return self._exit_confirmed

    async def _wait_for_direct_child(self) -> int | None:
        returncode = await self.process.wait()
        if type(returncode) is int:
            self._exit_confirmed = True
            self._closing = True
            self._exit_returncode = returncode
            if self._exit_callback is not None:
                self._exit_callback(self, returncode)
            return returncode
        return None

    async def _close_work(self, deadline: float) -> int | None:
        if self._exit_confirmed:
            return self._exit_returncode

        _ensure_before_deadline(deadline)

        if not self._quit_attempted:
            _ensure_before_deadline(deadline)
            self._quit_attempted = True
            now = asyncio.get_running_loop().time()
            quit_deadline = min(deadline, now + min(0.25, (deadline - now) / 8.0))
            try:
                await _run_until(
                    lambda: self._quit_and_drain(quit_deadline),
                    quit_deadline,
                    self._pending_tasks,
                )
            except asyncio.TimeoutError:
                # A stalled drain must not consume the time reserved for
                # direct-child wait, terminate, kill, and final wait.
                pass
            except Exception:
                # A failed quit write still leaves direct-child escalation
                # available under the same enclosing deadline.
                pass

        if self._exit_confirmed:
            return self._exit_returncode
        now = asyncio.get_running_loop().time()
        graceful_deadline = min(
            deadline, now + min(3.0, (deadline - now) / 3.0)
        )
        if not await self._wait_for_child_until(graceful_deadline):
            if asyncio.get_running_loop().time() >= deadline:
                return None

        if not self._exit_confirmed:
            if not self._terminate_attempted:
                if asyncio.get_running_loop().time() >= deadline:
                    return None
                self._terminate_attempted = True
                try:
                    self.process.terminate()
                except Exception:
                    pass
            now = asyncio.get_running_loop().time()
            terminate_deadline = min(
                deadline, now + min(2.0, (deadline - now) / 2.0)
            )
            if not await self._wait_for_child_until(
                terminate_deadline
            ) and asyncio.get_running_loop().time() >= deadline:
                return None

        if not self._exit_confirmed:
            if not self._kill_attempted:
                if asyncio.get_running_loop().time() >= deadline:
                    return None
                self._kill_attempted = True
                try:
                    self.process.kill()
                except Exception:
                    pass
            await self._wait_for_child_until(deadline)

        return self._exit_returncode if self._exit_confirmed else None

@dataclass
class _ServiceLease:
    owner_id: str
    launch: tuple[str | None, tuple[str, ...] | None, str | None] | None
    state: str
    startup_deadline: float | None = None
    session: GdbSession | None = None
    session_id: str | None = None
    creation_task: asyncio.Task | None = None
    spawn_task: asyncio.Task | None = None
    cleanup_task: asyncio.Task | None = None
    pending_tasks: set[asyncio.Task] = field(default_factory=set, repr=False)
    stop_requested: bool = False
    exit_confirmed: bool = False
    returncode: int | None = None
    error_code: str | None = None


async def _run_until(
    operation_factory: Callable[[], Coroutine[Any, Any, Any]],
    deadline: float,
    task_set: set[asyncio.Task],
):
    _ensure_before_deadline(deadline)
    operation = operation_factory()
    try:
        task = _retain_task(task_set, asyncio.create_task(operation))
    except BaseException:
        operation.close()
        raise
    return await _await_task_until(task, deadline)


class GdbManager:
    def __init__(self) -> None:
        self._sessions: dict[str, GdbSession] = {}
        self._owned_leases: dict[str, _ServiceLease] = {}

    @staticmethod
    def _owned_deadline(budget_ms: int | float) -> float:
        return GdbSession._deadline_from_budget(budget_ms)

    @staticmethod
    def _capture_launch(
        binary: str | None,
        args: list[str] | None,
        cwd: str | None,
    ) -> tuple[str | None, tuple[str, ...] | None, str | None]:
        if binary is not None and not isinstance(binary, str):
            raise GdbError("binary must be a string or None")
        if cwd is not None and not isinstance(cwd, str):
            raise GdbError("cwd must be a string or None")
        if args is not None and (
            not isinstance(args, list)
            or any(not isinstance(arg, str) for arg in args)
        ):
            raise GdbError("args must be a list of strings or None")
        effective_args = tuple(args) if binary and args else None
        return binary, effective_args, cwd

    @staticmethod
    def _snapshot(lease: _ServiceLease) -> OwnedSessionSnapshot:
        if lease.session is not None and lease.session._exit_confirmed:
            lease.state = "EXITED"
            lease.exit_confirmed = True
            lease.returncode = lease.session._exit_returncode
            lease.error_code = None
        result: OwnedSessionSnapshot = {
            "owner_id": lease.owner_id,
            "state": lease.state,
            "session_id": lease.session_id,
            "exit_confirmed": lease.exit_confirmed,
            "returncode": lease.returncode,
        }
        if lease.error_code is not None:
            result["error_code"] = lease.error_code
        return result

    @staticmethod
    def _validate_owner(owner_id: str) -> None:
        if not isinstance(owner_id, str) or owner_id == "":
            raise GdbError("owner_id must be a nonempty string")

    def _session_exit_confirmed(self, session: GdbSession, returncode: int) -> None:
        if type(returncode) is not int:
            return
        if self._sessions.get(session.id) is session:
            self._sessions.pop(session.id, None)
        for lease in self._owned_leases.values():
            if lease.session is session:
                lease.state = "EXITED"
                lease.exit_confirmed = True
                lease.returncode = returncode
                lease.error_code = None

    def _register_gdb_process(
        self, process: asyncio.subprocess.Process, lease: _ServiceLease | None = None
    ) -> GdbSession:
        session = GdbSession(id=uuid.uuid4().hex[:8], process=process, kind="gdb")
        session._exit_callback = self._session_exit_confirmed
        self._sessions[session.id] = session
        if lease is not None:
            lease.session = session
            lease.session_id = session.id
        return session

    async def _spawn_gdb_session(
        self,
        binary: str | None,
        cwd: str | None,
        deadline: float | None = None,
        lease: _ServiceLease | None = None,
    ) -> GdbSession:
        if deadline is not None:
            _ensure_before_deadline(deadline)
        cmd = ["gdb", "--interpreter=mi2", "--quiet"]
        if binary:
            cmd.append(binary)
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=cwd,
        )
        # Registration is intentionally allowed after the deadline: the late
        # factory result is still the only addressable handle to this child.
        return self._register_gdb_process(process, lease)

    async def _initialize_gdb_session(
        self,
        session: GdbSession,
        binary: str | None,
        args: tuple[str, ...] | None,
        deadline: float | None = None,
        pending_tasks: set[asyncio.Task] | None = None,
        admission: Callable[[], None] | None = None,
    ) -> None:
        task_set = pending_tasks if pending_tasks is not None else session._pending_tasks
        if admission is not None:
            admission()
        banner_deadline = (
            deadline
            if deadline is not None
            else asyncio.get_running_loop().time() + 15.0
        )
        try:
            await _run_until(
                lambda: _drain_to_prompt(
                    session.process.stdout, deadline=banner_deadline
                ),
                banner_deadline,
                task_set,
            )
        except asyncio.TimeoutError as exc:
            raise GdbError("GDB failed to start before its banner deadline") from exc
        if admission is not None:
            admission()

        setup_commands = [
            "set pagination off",
            "set confirm off",
            "set breakpoint pending on",
        ]
        if binary and args:
            setup_commands.append(
                "set args " + " ".join(shlex.quote(arg) for arg in args)
            )
        for setup_cmd in setup_commands:
            if admission is not None:
                admission()
            if deadline is None:
                response = await session.send(setup_cmd)
            else:
                response = await session._send_until(setup_cmd, deadline)
            if admission is not None:
                admission()
            if any(line.startswith("Error: ") for line in response.splitlines()):
                raise GdbError(f"GDB setup command failed: {setup_cmd!r}")

    async def create(
        self,
        binary: str | None = None,
        args: list[str] | None = None,
        cwd: str | None = None,
    ) -> GdbSession:
        """Spawn a new GDB process and return a ready, hardened GdbSession."""
        launch = self._capture_launch(binary, args, cwd)
        session = await self._spawn_gdb_session(binary, cwd)
        await self._initialize_gdb_session(session, binary, launch[1])
        return session

    async def start_owned_session(
        self,
        owner_id: str,
        binary: str | None = None,
        args: list[str] | None = None,
        cwd: str | None = None,
        *,
        budget_ms: int | float,
    ) -> OwnedSessionSnapshot:
        self._validate_owner(owner_id)
        deadline = self._owned_deadline(budget_ms)
        launch = self._capture_launch(binary, args, cwd)
        existing = self._owned_leases.get(owner_id)
        if existing is not None:
            if existing.state == "CANCELLED_BEFORE_START":
                return self._snapshot(existing)
            if existing.launch != launch:
                # This is a response-only conflict. The stored lease and its
                # launch tuple remain unchanged.
                return {
                    "owner_id": owner_id,
                    "state": "OWNER_CONFLICT",
                    "session_id": None,
                    "exit_confirmed": False,
                    "returncode": None,
                    "error_code": "OWNER_CONFLICT",
                }
            self._snapshot(existing)
            task = existing.creation_task
            if task is not None and not task.done():
                try:
                    await _await_task_until(task, min(deadline, existing.startup_deadline or deadline))
                except asyncio.TimeoutError:
                    pass
            return self._snapshot(existing)

        lease = _ServiceLease(
            owner_id=owner_id,
            launch=launch,
            state="STARTING",
            startup_deadline=deadline,
        )
        # The caller-known token and creation task are registered before the
        # first spawn await. Cancellation of this request cannot cancel either.
        self._owned_leases[owner_id] = lease
        lease.creation_task = _retain_task(
            lease.pending_tasks,
            asyncio.create_task(self._create_owned(lease, deadline)),
        )
        try:
            await _await_task_until(lease.creation_task, deadline)
        except asyncio.TimeoutError:
            if lease.state == "STARTING":
                lease.state = "UNRESOLVED"
                lease.error_code = "START_TIMEOUT"
        return self._snapshot(lease)

    async def _create_owned(
        self, lease: _ServiceLease, deadline: float
    ) -> OwnedSessionSnapshot:
        if lease.stop_requested:
            lease.state = "CANCELLED_BEFORE_START"
            lease.error_code = "CANCELLED_BEFORE_START"
            return self._snapshot(lease)
        if lease.launch is None:
            lease.state = "UNRESOLVED"
            lease.error_code = "INVALID_LAUNCH"
            return self._snapshot(lease)

        binary, args, cwd = lease.launch
        try:
            _ensure_before_deadline(deadline)
            lease.spawn_task = _retain_task(
                lease.pending_tasks,
                asyncio.create_task(
                    self._spawn_gdb_session(
                        binary, cwd, deadline=deadline, lease=lease
                    )
                ),
            )
            session = await _await_task_until(lease.spawn_task, deadline)
        except asyncio.TimeoutError:
            if not lease.stop_requested:
                lease.state = "UNRESOLVED"
                lease.error_code = "START_TIMEOUT"
            return self._snapshot(lease)
        except asyncio.CancelledError:
            if not lease.stop_requested:
                lease.state = "UNRESOLVED"
                lease.error_code = "START_CANCELLED"
            return self._snapshot(lease)
        except Exception:
            # A factory exception is not independent proof that no child was
            # created. Retain the lease as unresolved for later stop attempts.
            if not lease.stop_requested:
                lease.state = "UNRESOLVED"
                lease.error_code = "SPAWN_UNCONFIRMED"
            return self._snapshot(lease)

        if lease.stop_requested:
            return self._snapshot(lease)

        def _startup_admission() -> None:
            _ensure_before_deadline(deadline)
            if lease.stop_requested:
                raise GdbError("Owned startup stop requested")

        try:
            _startup_admission()
            await self._initialize_gdb_session(
                session,
                binary,
                args,
                deadline,
                lease.pending_tasks,
                admission=_startup_admission,
            )
            _ensure_before_deadline(deadline)
        except asyncio.TimeoutError:
            if not lease.stop_requested:
                lease.state = "UNRESOLVED"
                lease.error_code = "START_TIMEOUT"
            return self._snapshot(lease)
        except asyncio.CancelledError:
            if not lease.stop_requested:
                lease.state = "UNRESOLVED"
                lease.error_code = "START_CANCELLED"
            return self._snapshot(lease)
        except Exception:
            if not lease.stop_requested:
                lease.state = "UNRESOLVED"
                lease.error_code = "STARTUP_FAILED"
            return self._snapshot(lease)

        if lease.stop_requested:
            return self._snapshot(lease)
        try:
            _ensure_before_deadline(deadline)
        except asyncio.TimeoutError:
            lease.state = "UNRESOLVED"
            lease.error_code = "START_TIMEOUT"
            return self._snapshot(lease)
        lease.state = "ACTIVE"
        lease.error_code = None
        return self._snapshot(lease)

    async def stop_session_by_owner(
        self, owner_id: str, *, budget_ms: int | float
    ) -> OwnedSessionSnapshot:
        self._validate_owner(owner_id)
        deadline = self._owned_deadline(budget_ms)
        lease = self._owned_leases.get(owner_id)
        if lease is None:
            lease = _ServiceLease(
                owner_id=owner_id,
                launch=None,
                state="CANCELLED_BEFORE_START",
                error_code="CANCELLED_BEFORE_START",
            )
            self._owned_leases[owner_id] = lease
            return self._snapshot(lease)

        self._snapshot(lease)
        if lease.state in ("EXITED", "CANCELLED_BEFORE_START"):
            return self._snapshot(lease)
        lease.stop_requested = True
        lease.state = "STOP_REQUESTED"
        lease.error_code = "STOP_REQUESTED"
        if lease.session is not None:
            lease.session._closing = True

        task = lease.cleanup_task
        if task is None or task.done():
            task = _retain_task(
                lease.pending_tasks,
                asyncio.create_task(self._stop_owned_until(lease, deadline)),
            )
            lease.cleanup_task = task
        try:
            await _await_task_until(task, deadline)
        except asyncio.TimeoutError:
            if not lease.exit_confirmed and lease.state != "CANCELLED_BEFORE_START":
                lease.state = "UNRESOLVED"
                lease.error_code = "STOP_TIMEOUT"
        return self._snapshot(lease)

    async def _stop_owned_until(
        self, lease: _ServiceLease, deadline: float
    ) -> OwnedSessionSnapshot:
        if lease.state == "CANCELLED_BEFORE_START":
            return self._snapshot(lease)
        if lease.state == "EXITED":
            return self._snapshot(lease)

        session = lease.session
        if session is None and lease.spawn_task is not None:
            try:
                session = await _await_task_until(lease.spawn_task, deadline)
            except asyncio.TimeoutError:
                lease.state = "UNRESOLVED"
                lease.error_code = "STOP_TIMEOUT"
                return self._snapshot(lease)
            except Exception:
                lease.state = "UNRESOLVED"
                lease.error_code = "SPAWN_UNCONFIRMED"
                return self._snapshot(lease)

        if session is None:
            if lease.spawn_task is None:
                # No spawn task was admitted, so the stop is a proved
                # pre-start cancellation and requires no child-exit claim.
                lease.state = "CANCELLED_BEFORE_START"
                lease.exit_confirmed = False
                lease.returncode = None
                lease.error_code = "CANCELLED_BEFORE_START"
            else:
                lease.state = "UNRESOLVED"
                lease.error_code = "NO_SESSION_HANDLE"
            return self._snapshot(lease)

        session._closing = True
        if asyncio.get_running_loop().time() >= deadline:
            lease.state = "UNRESOLVED"
            lease.error_code = "STOP_TIMEOUT"
            return self._snapshot(lease)
        returncode = await session._close_until(deadline)
        if type(returncode) is int:
            lease.state = "EXITED"
            lease.exit_confirmed = True
            lease.returncode = returncode
            lease.error_code = None
        else:
            lease.state = "UNRESOLVED"
            lease.error_code = "EXIT_UNCONFIRMED"
        return self._snapshot(lease)

    async def create_replay(
        self,
        trace_dir: str | None = None,
        cwd: str | None = None,
    ) -> GdbSession:
        """Start an rr replay session and return a ready GdbSession.

        trace_dir: rr trace directory to replay; omit to replay the latest recording.
        rr execs gdb directly, so the MI2 protocol works identically to a normal session.
        """
        cmd = ["rr", "replay"]
        if trace_dir:
            cmd.append(trace_dir)
        cmd += ["--", "--interpreter=mi2", "--quiet"]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=cwd,
        )

        try:
            await asyncio.wait_for(_drain_to_prompt(process.stdout), timeout=15.0)
        except asyncio.TimeoutError:
            process.kill()
            raise GdbError("rr replay failed to start (no prompt within 15 s)")

        session = GdbSession(id=uuid.uuid4().hex[:8], process=process, kind="rr-replay")

        for setup_cmd in (
            "set pagination off",
            "set confirm off",
            "set breakpoint pending on",
        ):
            await session.send(setup_cmd)

        self._sessions[session.id] = session
        return session

    def get(self, session_id: str) -> GdbSession:
        s = self._sessions.get(session_id)
        if s is None:
            raise GdbError(f"No session with id {session_id!r}")
        return s

    async def remove(self, session_id: str) -> bool:
        s = self._sessions.get(session_id)
        if s is None:
            return False
        s._exit_callback = self._session_exit_confirmed
        deadline = GdbSession._deadline_from_budget(7000)
        returncode = await s._close_until(deadline)
        if type(returncode) is not int:
            raise GdbError(
                f"Session {session_id!r} exit was not confirmed; ownership retained"
            )
        if self._sessions.get(session_id) is s:
            self._sessions.pop(session_id, None)
        return True

    async def close_all(self) -> None:
        """Close all active sessions (used on server shutdown)."""
        for sid in list(self._sessions):
            await self.remove(sid)

    def list_all(self) -> list[dict]:
        return [
            {
                "id": s.id,
                "kind": s.kind,
                "alive": s.process.returncode is None,
            }
            for s in self._sessions.values()
        ]

async def _drain_to_prompt(
    stdout: asyncio.StreamReader, deadline: float | None = None
) -> None:
    """Read and discard GDB output lines until the first (gdb) prompt."""
    while True:
        if deadline is not None:
            _ensure_before_deadline(deadline)
        raw = await stdout.readline()
        if deadline is not None:
            _ensure_before_deadline(deadline)
        if not raw:
            raise GdbError("GDB exited before showing the initial prompt")
        line = raw.decode(errors="replace").rstrip("\n")
        if _PROMPT_RE.match(line):
            return
