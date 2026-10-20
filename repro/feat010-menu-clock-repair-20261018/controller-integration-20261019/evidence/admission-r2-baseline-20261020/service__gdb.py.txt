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
import base64
import hashlib
import json
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
_OBSERVATION_RECORD_LIMIT = 8192
_OBSERVATION_BYTE_LIMIT = 1024 * 1024
_BASELINE_PREFIX = "LB_SRO_BASELINE:"
_BASELINE_SCHEMA = "ladybug.feat010.connection-baseline.v1"
_OBSERVATION_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")


class _MiParser:
    """Small strict parser for the MI values used by observation mode."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.pos = 0

    def _peek(self) -> str:
        return self.text[self.pos] if self.pos < len(self.text) else ""

    def _take(self, expected: str) -> None:
        if self._peek() != expected:
            raise ValueError(f"expected {expected!r} at offset {self.pos}")
        self.pos += 1

    def _identifier(self) -> str:
        start = self.pos
        while self._peek() and re.match(r"[A-Za-z0-9_-]", self._peek()):
            self.pos += 1
        if self.pos == start:
            raise ValueError(f"expected MI identifier at offset {self.pos}")
        return self.text[start:self.pos]

    def _string(self) -> str:
        self._take('"')
        start = self.pos
        escaped = False
        while self.pos < len(self.text):
            char = self.text[self.pos]
            if char == '"' and not escaped:
                content = self.text[start:self.pos]
                self.pos += 1
                return _unescape(content)
            if char == "\\" and not escaped:
                escaped = True
            else:
                escaped = False
            self.pos += 1
        raise ValueError("unterminated MI string")

    def _has_pair(self) -> bool:
        match = re.match(r"[A-Za-z0-9_-]+=", self.text[self.pos:])
        return match is not None

    def _pair(self) -> tuple[str, Any]:
        key = self._identifier()
        self._take("=")
        return key, self._value()

    def _fields(self, end: str) -> dict[str, Any]:
        fields: dict[str, Any] = {}
        while self._peek() != end:
            key, value = self._pair()
            if key in fields:
                raise ValueError(f"duplicate MI field {key!r}")
            fields[key] = value
            if self._peek() == ",":
                self.pos += 1
                if self._peek() == end:
                    raise ValueError(f"trailing delimiter before {end!r}")
                continue
            if self._peek() != end:
                raise ValueError(f"expected {end!r} at offset {self.pos}")
        return fields

    def _value(self) -> Any:
        char = self._peek()
        if char == '"':
            return self._string()
        if char == "{":
            self.pos += 1
            fields = self._fields("}")
            self._take("}")
            return fields
        if char == "[":
            self.pos += 1
            values: list[Any] = []
            while self._peek() != "]":
                if self._has_pair():
                    key, value = self._pair()
                    values.append({"_mi_key": key, "value": value})
                else:
                    values.append(self._value())
                if self._peek() == ",":
                    self.pos += 1
                    if self._peek() == "]":
                        raise ValueError("trailing delimiter before list end")
                elif self._peek() != "]":
                    raise ValueError(f"expected list delimiter at offset {self.pos}")
            self._take("]")
            return values
        raise ValueError(f"unsupported unquoted MI value at offset {self.pos}")

    def parse_fields(self) -> dict[str, Any]:
        fields: dict[str, Any] = {}
        while self.pos < len(self.text):
            key, value = self._pair()
            if key in fields:
                raise ValueError(f"duplicate MI field {key!r}")
            fields[key] = value
            if self.pos == len(self.text):
                break
            self._take(",")
            if self.pos == len(self.text):
                raise ValueError("trailing delimiter after MI result field")
        return fields

    def parse_stream(self) -> str:
        value = self._string()
        if self.pos != len(self.text):
            raise ValueError("trailing bytes after MI stream string")
        return value


def _parse_mi_record(raw: bytes, sequence: int) -> dict[str, Any]:
    line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
    record: dict[str, Any] = {
        "sequence": sequence,
        "raw": line,
        "raw_b64": base64.b64encode(raw).decode("ascii"),
        "kind": "raw",
        "token": None,
        "marker": None,
        "class": None,
        "fields": {},
    }
    if _PROMPT_RE.match(line):
        record["kind"] = "prompt"
        return record

    pos = 0
    while pos < len(line) and line[pos].isdigit():
        pos += 1
    token_text = line[:pos]
    if pos >= len(line) or line[pos] not in "^*+=~@&":
        return record
    marker = line[pos]
    rest = line[pos + 1:]
    record.update({"kind": "mi", "token": token_text or None, "marker": marker})
    try:
        if marker in "~@&":
            record["stream"] = _MiParser(rest).parse_stream()
            return record
        result_class, separator, payload = rest.partition(",")
        if not re.fullmatch(r"[A-Za-z0-9_-]+", result_class):
            raise ValueError("missing MI record class")
        record["class"] = result_class
        if separator:
            if not payload:
                raise ValueError("empty MI result payload after delimiter")
            record["fields"] = _MiParser(payload).parse_fields()
    except ValueError as exc:
        record["parse_error"] = str(exc)
    return record


def build_connection_baseline_producer(
    owner_id: str, session_id: str, generation: int, nonce: str
) -> bytes:
    """Return the fixed, ASCII-only GDB-Python body used for baseline proof."""
    for label, value in (("owner_id", owner_id), ("session_id", session_id), ("nonce", nonce)):
        if not isinstance(value, str) or not _OBSERVATION_ID_RE.fullmatch(value):
            raise GdbError(f"{label} must be validated ASCII identity data")
    if type(generation) is not int or generation <= 0:
        raise GdbError("generation must be a positive strict integer")
    literals = [
        json.dumps(value, ensure_ascii=True, separators=(",", ":"))
        for value in (_BASELINE_SCHEMA, owner_id, session_id, nonce)
    ]
    source = (
        "import gdb,json\n"
        "_lb_sro_connections = gdb.connections()\n"
        "_lb_sro_payload = {"
        f"'schema':{literals[0]},'owner_id':{literals[1]},"
        f"'session_id':{literals[2]},'generation':{generation},"
        f"'nonce':{literals[3]},'connection_count':len(_lb_sro_connections)"
        "}\n"
        f"print({_BASELINE_PREFIX!r} + json.dumps(_lb_sro_payload, separators=(',', ':'), sort_keys=True))\n"
    )
    return source.encode("ascii")


def _mi_quote(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r") + '"'


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


def _format_observation_output(records: list[dict[str, Any]]) -> str:
    """Format parsed observation records without exposing MI framing tokens."""
    lines: list[str] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        if record.get("kind") == "prompt":
            continue
        raw = record.get("raw")
        if not isinstance(raw, str):
            continue
        token = record.get("token")
        if (
            record.get("kind") == "mi"
            and isinstance(token, str)
            and raw.startswith(token)
        ):
            raw = raw[len(token):]
        lines.append(raw)
    return _format_output(lines)


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
    _owned_active: bool = field(default=False, repr=False)
    _legacy_send_history: int = field(default=0, repr=False)
    _legacy_interrupt_history: int = field(default=0, repr=False)
    _legacy_reader_active: bool = field(default=False, repr=False)
    _observation_state: str = field(default="legacy", repr=False)
    _observation_owner_id: str | None = field(default=None, repr=False)
    _observation_generation: int = field(default=0, repr=False)
    _state_generation: int = field(default=0, repr=False)
    _observation_nonce: str | None = field(default=None, repr=False)
    _observation_claim_ack: dict[str, Any] | None = field(default=None, repr=False)
    _observation_task: asyncio.Task | None = field(default=None, repr=False)
    _observation_eof: bool = field(default=False, repr=False)
    _observation_reader_error: str | None = field(default=None, repr=False)
    _observation_invalidated: bool = field(default=False, repr=False)
    _observation_tainted: bool = field(default=False, repr=False)
    _observation_records: list[dict[str, Any]] = field(default_factory=list, repr=False)
    _observation_stops: list[dict[str, Any]] = field(default_factory=list, repr=False)
    _observation_record_count: int = field(default=0, repr=False)
    _observation_byte_count: int = field(default=0, repr=False)
    _observation_overflow_evidence: dict[str, Any] | None = field(default=None, repr=False)
    _observation_sequence: int = field(default=0, repr=False)
    _observation_event: asyncio.Event = field(default_factory=asyncio.Event, repr=False)
    _observation_transaction_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    _observation_operation_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    _observation_active_operation_id: str | None = field(default=None, repr=False)
    _observation_active_transaction: dict[str, Any] | None = field(default=None, repr=False)
    _observation_next_token: int = field(default=1, repr=False)
    _observation_used_command_ids: set[str] = field(default_factory=set, repr=False)
    _observation_call_ledger: list[dict[str, Any]] = field(default_factory=list, repr=False)
    _observation_exit_callback: Callable[["GdbSession"], None] | None = field(default=None, repr=False)

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
        if self._owned_active:
            if self._observation_state != "legacy":
                raise GdbError("Legacy commands are disabled for an observed session")
            self._legacy_send_history += 1
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
            self._legacy_reader_active = True
            try:
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
            finally:
                self._legacy_reader_active = False

    def _mark_observation_invalid(self, code: str) -> None:
        self._observation_invalidated = True
        if self._observation_state not in ("stopping", "closed"):
            self._observation_state = "invalid"
        txn = self._observation_active_transaction
        if txn is not None and txn.get("protocol_error") is None:
            txn["protocol_error"] = code
        self._observation_event.set()

    def _append_observation_record(self, raw: bytes) -> None:
        self._observation_sequence += 1
        self._observation_record_count += 1
        self._observation_byte_count += len(raw)
        if (
            self._observation_record_count > _OBSERVATION_RECORD_LIMIT
            or self._observation_byte_count > _OBSERVATION_BYTE_LIMIT
        ):
            if self._observation_overflow_evidence is None:
                excerpt = raw[:256]
                self._observation_overflow_evidence = {
                    "sequence": self._observation_sequence,
                    "owner_id": self._observation_owner_id,
                    "session_id": self.id,
                    "observation_generation": self._observation_generation,
                    "state_generation": self._state_generation,
                    "length": len(raw),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "excerpt_b64": base64.b64encode(excerpt).decode("ascii"),
                }
            self._observation_tainted = True
            self._mark_observation_invalid("OBSERVER_CAP_EXCEEDED")
            return

        record = _parse_mi_record(raw, self._observation_sequence)
        record.update({
            "owner_id": self._observation_owner_id,
            "session_id": self.id,
            "observation_generation": self._observation_generation,
            "state_generation": self._state_generation,
        })
        if record.get("marker") in ("*", "="):
            record_class = record.get("class") or ""
            if record.get("marker") == "*" or record_class.startswith(("thread-", "thread-group-")):
                self._state_generation += 1
                record["state_generation"] = self._state_generation
        if record.get("marker") == "*" and record.get("class") == "stopped":
            record["observation"] = "SESSION_EVENT_ONLY"
            self._observation_stops.append(record)

        self._observation_records.append(record)
        txn = self._observation_active_transaction
        if txn is not None:
            txn["records"].append(record)
            if record.get("kind") == "prompt":
                if txn.get("result") is not None:
                    txn["prompt_sequence"] = record["sequence"]
            elif record.get("marker") == "^":
                if record.get("parse_error"):
                    txn["protocol_error"] = "MALFORMED_MI_RESULT"
                elif record.get("token") != txn.get("token"):
                    txn["protocol_error"] = "MI_RESULT_TOKEN_MISMATCH"
                elif txn.get("result") is not None:
                    txn["protocol_error"] = "DUPLICATE_MI_RESULT"
                else:
                    txn["result"] = record
            elif record.get("parse_error") and record.get("marker") in ("*", "="):
                if record.get("class") == "stopped":
                    txn["protocol_error"] = "MALFORMED_STOP_RECORD"
        elif record.get("marker") == "^" and self._observation_state not in ("stopping", "closed"):
            self._mark_observation_invalid("UNMATCHED_MI_RESULT")
        self._observation_event.set()

    async def _observation_reader(self) -> None:
        reached_eof = False
        try:
            while True:
                raw = await self.process.stdout.readline()
                if not raw:
                    reached_eof = True
                    return
                self._append_observation_record(raw)
        except asyncio.CancelledError:
            self._observation_reader_error = "READER_CANCELLED"
            raise
        except Exception as exc:
            self._observation_reader_error = f"{type(exc).__name__}: {exc}"
            self._mark_observation_invalid("READER_FAILED")
        finally:
            self._observation_eof = reached_eof
            if self._observation_state not in ("stopping", "closed"):
                if reached_eof:
                    self._mark_observation_invalid("OBSERVER_EOF")
                elif self._observation_reader_error is not None:
                    self._mark_observation_invalid("OBSERVER_READER_FAILED")
            self._observation_event.set()
            if self._observation_exit_callback is not None:
                self._observation_exit_callback(self)

    def _start_observation_reader(self) -> None:
        if self._observation_task is not None:
            raise GdbError("Observation reader ownership was already transferred")
        if self._legacy_reader_active:
            raise GdbError("Legacy stdout reader is still active")
        if self.process.returncode is not None or self._exit_confirmed:
            raise GdbError("GDB process exited before observation claim")
        task = asyncio.create_task(self._observation_reader())
        self._observation_task = _retain_task(self._pending_tasks, task)

    async def _wait_observation_change(self, deadline: float) -> None:
        _ensure_before_deadline(deadline)
        self._observation_event.clear()
        if asyncio.get_running_loop().time() >= deadline:
            raise asyncio.TimeoutError
        await asyncio.wait_for(
            self._observation_event.wait(),
            timeout=max(0.0, deadline - asyncio.get_running_loop().time()),
        )
        _ensure_before_deadline(deadline)

    async def _observation_request_until(
        self, mi_command: str, call_id: str, deadline: float
    ) -> dict[str, Any]:
        if self._observation_task is None or self._observation_state not in ("claim-pending", "claimed"):
            raise GdbError("Observation reader is not admitted")
        if self._observation_invalidated or self._observation_tainted:
            raise GdbError("Observation is invalidated or tainted")
        remaining = max(0.0, deadline - asyncio.get_running_loop().time())
        await asyncio.wait_for(self._observation_transaction_lock.acquire(), remaining)
        try:
            _ensure_before_deadline(deadline)
            if (
                self._observation_state not in ("claim-pending", "claimed")
                or self._observation_invalidated
                or self._observation_tainted
            ):
                raise GdbError("Observation was invalidated before transaction write")
            if self._observation_active_transaction is not None:
                raise GdbError("An observation transaction is already active")
            token = str(self._observation_next_token)
            self._observation_next_token += 1
            transaction: dict[str, Any] = {
                "call_id": call_id,
                "operation_id": self._observation_active_operation_id,
                "token": token,
                "mi_command": mi_command,
                "request_sequence": self._observation_sequence,
                "observation_generation": self._observation_generation,
                "state_generation_before": self._state_generation,
                "records": [],
                "result": None,
                "prompt_sequence": None,
                "protocol_error": None,
            }
            self._observation_call_ledger.append(transaction)
            self._observation_active_transaction = transaction
            try:
                _ensure_before_deadline(deadline)
                self.process.stdin.write(f"{token}{mi_command}\n".encode("ascii"))
                await asyncio.wait_for(
                    self.process.stdin.drain(),
                    timeout=max(0.0, deadline - asyncio.get_running_loop().time()),
                )
                while transaction["result"] is None or transaction["prompt_sequence"] is None:
                    if transaction["protocol_error"] is not None:
                        raise GdbError(transaction["protocol_error"])
                    if self._observation_invalidated or self._observation_tainted:
                        raise GdbError("Observation was invalidated during transaction")
                    if self._observation_reader_error is not None:
                        raise GdbError("OBSERVER_READER_FAILED")
                    if self._observation_eof:
                        raise GdbError("OBSERVER_EOF_BEFORE_REPLY")
                    await self._wait_observation_change(deadline)
                _ensure_before_deadline(deadline)
                if self._observation_invalidated or self._observation_tainted:
                    raise GdbError("Observation was invalidated before transaction completion")
                if self._observation_reader_error is not None or self._observation_eof:
                    raise GdbError("OBSERVER_TERMINATED_BEFORE_TRANSACTION_COMPLETION")
                if transaction["protocol_error"] is not None:
                    raise GdbError(transaction["protocol_error"])
                return transaction
            except asyncio.TimeoutError:
                transaction["error_code"] = "DEADLINE_EXPIRED"
                self._mark_observation_invalid("DEADLINE_EXPIRED")
                raise
            except asyncio.CancelledError:
                transaction["error_code"] = "REQUEST_CANCELLED"
                self._mark_observation_invalid("REQUEST_CANCELLED")
                raise
            except Exception as exc:
                transaction["error_code"] = str(exc)
                self._mark_observation_invalid("OBSERVATION_TRANSACTION_FAILED")
                raise
            finally:
                if self._observation_active_transaction is transaction:
                    self._observation_active_transaction = None
        finally:
            self._observation_transaction_lock.release()

    async def _baseline_until(self, deadline: float) -> dict[str, Any]:
        generation = self._observation_generation
        nonce = self._observation_nonce
        if self._observation_owner_id is None or nonce is None:
            raise GdbError("Baseline identities are unavailable")
        body = build_connection_baseline_producer(
            self._observation_owner_id, self.id, generation, nonce
        ).decode("ascii")
        python_literal = json.dumps(body, ensure_ascii=True, separators=(",", ":"))
        console_command = f"python exec({python_literal})"
        mi_command = "-interpreter-exec console " + _mi_quote(console_command)
        txn = await self._observation_request_until(mi_command, "claim:baseline", deadline)
        result = txn.get("result")
        if not isinstance(result, dict) or result.get("class") != "done":
            raise GdbError("BASELINE_MI_RESULT_NOT_DONE")
        if self._state_generation != txn["state_generation_before"]:
            raise GdbError("BASELINE_STATE_GENERATION_CHANGED")

        payload_records: list[tuple[str, str]] = []
        for record in txn["records"]:
            if record.get("kind") != "mi" or record.get("marker") not in ("~", "@", "&"):
                continue
            stream = record.get("stream")
            if not isinstance(stream, str):
                continue
            for line in stream.splitlines():
                if line.startswith(_BASELINE_PREFIX):
                    payload_records.append((record["marker"], line[len(_BASELINE_PREFIX):]))
        if len(payload_records) != 1 or payload_records[0][0] != "~":
            raise GdbError("BASELINE_STREAM_MISSING_DUPLICATE_OR_WRONG_STREAM")
        try:
            def _unique_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
                values: dict[str, Any] = {}
                for key, value in pairs:
                    if key in values:
                        raise ValueError(f"duplicate JSON key {key!r}")
                    values[key] = value
                return values

            payload = json.loads(
                payload_records[0][1], object_pairs_hook=_unique_json_keys
            )
        except (TypeError, ValueError) as exc:
            raise GdbError("BASELINE_JSON_INVALID") from exc
        expected_keys = {
            "schema", "owner_id", "session_id", "generation", "nonce", "connection_count"
        }
        if not isinstance(payload, dict) or set(payload) != expected_keys:
            raise GdbError("BASELINE_SCHEMA_FIELDS_INVALID")
        expected = {
            "schema": _BASELINE_SCHEMA,
            "owner_id": self._observation_owner_id,
            "session_id": self.id,
            "generation": generation,
            "nonce": nonce,
        }
        for key, value in expected.items():
            if type(payload.get(key)) is not type(value) or payload.get(key) != value:
                raise GdbError("BASELINE_IDENTITY_MISMATCH")
        count = payload.get("connection_count")
        if type(count) is not int:
            raise GdbError("BASELINE_CONNECTION_COUNT_NOT_INTEGER")
        if count != 0:
            raise GdbError("BASELINE_CONNECTIONS_PRESENT")
        if self._state_generation != generation or asyncio.get_running_loop().time() >= deadline:
            raise GdbError("BASELINE_STATE_OR_DEADLINE_INVALID")
        return {
            "payload": payload,
            "mi_result": result,
            "call": txn,
            "producer_body": body,
        }

    async def _thread_state_until(
        self, call_id: str, deadline: float
    ) -> dict[str, Any]:
        txn = await self._observation_request_until("-thread-info", call_id, deadline)
        result = txn.get("result")
        if not isinstance(result, dict) or result.get("class") != "done":
            raise GdbError("THREAD_INFO_RESULT_NOT_DONE")
        fields = result.get("fields")
        threads_value = fields.get("threads") if isinstance(fields, dict) else None
        if not isinstance(threads_value, list):
            raise GdbError("THREAD_INFO_THREADS_MISSING")
        current_thread_id = fields.get("current-thread-id") if isinstance(fields, dict) else None
        if current_thread_id is not None and not isinstance(current_thread_id, str):
            raise GdbError("THREAD_INFO_CURRENT_ID_INVALID")
        threads: list[dict[str, Any]] = []
        for item in threads_value:
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                threads.append(item)
            elif (
                isinstance(item, dict)
                and item.get("_mi_key") == "thread"
                and isinstance(item.get("value"), dict)
                and isinstance(item["value"].get("id"), str)
            ):
                threads.append(item["value"])
            else:
                raise GdbError("THREAD_INFO_ENTRY_INVALID")
        if self._state_generation != txn["state_generation_before"]:
            raise GdbError("THREAD_INFO_GENERATION_CHANGED")
        return {
            "threads": threads,
            "current_thread_id": current_thread_id,
            "observation_generation": self._observation_generation,
            "state_generation": self._state_generation,
            "mi_result": result,
            "call": txn,
        }

    async def _breakpoint_until(
        self,
        expected: dict[str, str],
        call_id: str,
        deadline: float,
    ) -> dict[str, Any]:
        txn = await self._observation_request_until("-break-list", call_id, deadline)
        result = txn.get("result")
        if not isinstance(result, dict) or result.get("class") != "done":
            raise GdbError("BREAK_LIST_RESULT_NOT_DONE")
        fields = result.get("fields")
        table = fields.get("BreakpointTable") if isinstance(fields, dict) else None
        body = table.get("body") if isinstance(table, dict) else None
        if not isinstance(body, list):
            raise GdbError("BREAK_LIST_BODY_MISSING")
        matches: list[dict[str, Any]] = []
        for item in body:
            if not isinstance(item, dict):
                raise GdbError("BREAK_LIST_ENTRY_INVALID")
            breakpoint = item.get("value") if item.get("_mi_key") == "bkpt" else item
            if not isinstance(breakpoint, dict):
                raise GdbError("BREAK_LIST_ENTRY_INVALID")
            if breakpoint.get("number") == expected["number"]:
                matches.append(breakpoint)
        if len(matches) != 1:
            raise GdbError("EXPECTED_BREAKPOINT_NOT_UNIQUE")
        actual = matches[0]
        if (
            actual.get("enabled") != "y"
            or self._normalize_pc(actual.get("addr"))
            != self._normalize_pc(expected["address"])
            or actual.get("disp") != expected["disposition"]
        ):
            raise GdbError("EXPECTED_BREAKPOINT_IDENTITY_MISMATCH")
        if self._state_generation != txn["state_generation_before"]:
            raise GdbError("BREAK_LIST_GENERATION_CHANGED")
        return {"breakpoint": actual, "mi_result": result, "call": txn}

    async def _wait_stop_after_until(
        self, sequence: int, deadline: float
    ) -> dict[str, Any]:
        while True:
            if self._observation_invalidated or self._observation_tainted:
                raise GdbError("OBSERVATION_INVALIDATED_WHILE_WAITING_FOR_STOP")
            candidates = [
                record for record in self._observation_stops
                if record.get("sequence", 0) > sequence
            ]
            if candidates:
                if len(candidates) != 1:
                    raise GdbError("MULTIPLE_STOP_RECORDS_AMBIGUOUS")
                stop_record = candidates[0]
                stop_sequence = stop_record["sequence"]
                if any(
                    record.get("kind") == "prompt"
                    and record.get("sequence", 0) > stop_sequence
                    for record in self._observation_records
                ):
                    if stop_record.get("parse_error"):
                        raise GdbError("STOP_RECORD_PARSE_FAILED")
                    return stop_record
            if self._observation_eof:
                raise GdbError("OBSERVER_EOF_BEFORE_STOP")
            await self._wait_observation_change(deadline)

    @staticmethod
    def _normalize_pc(value: Any) -> int | None:
        if not isinstance(value, str) or not re.fullmatch(r"0[xX][0-9a-fA-F]+", value):
            return None
        try:
            return int(value, 16)
        except ValueError:
            return None

    async def _owned_exec_operation(
        self,
        command_id: str,
        command: str,
        stop_expectation: str,
        expected_breakpoint: dict[str, str] | None,
        deadline: float,
    ) -> dict[str, Any]:
        actions = {"continue": "-exec-continue"}
        attach_command = "target remote 127.0.0.1:65520"
        is_attach = command == attach_command
        if command not in actions and not is_attach:
            raise GdbError("OWNED_COMMAND_NOT_ALLOWED")
        wait_remaining = max(0.0, deadline - asyncio.get_running_loop().time())
        await asyncio.wait_for(self._observation_operation_lock.acquire(), wait_remaining)
        ledger_start = len(self._observation_call_ledger)
        self._observation_active_operation_id = command_id
        try:
            if self._observation_state != "claimed" or self._observation_invalidated:
                raise GdbError("OBSERVATION_NOT_CLAIMED")
            if self._observation_tainted or self._observation_task is None:
                raise GdbError("OBSERVATION_READER_UNAVAILABLE")
            before = await self._thread_state_until(f"{command_id}:state-before", deadline)
            if is_attach:
                if before["threads"] or before.get("current_thread_id") is not None:
                    raise GdbError("ATTACH_REQUIRES_NO_EXISTING_THREAD")
            elif (
                len(before["threads"]) != 1
                or before["threads"][0].get("state") != "stopped"
                or before.get("current_thread_id") != before["threads"][0].get("id")
                or self._normalize_pc(
                    before["threads"][0].get("frame", {}).get("addr")
                    if isinstance(before["threads"][0].get("frame"), dict)
                    else None
                ) is None
            ):
                raise GdbError("CONTINUE_REQUIRES_ONE_STOPPED_THREAD_WITH_PC")

            if stop_expectation == "breakpoint":
                if expected_breakpoint is None:
                    raise GdbError("EXPECTED_BREAKPOINT_REQUIRED")
                await self._breakpoint_until(
                    expected_breakpoint, f"{command_id}:breakpoint-before", deadline
                )
            elif expected_breakpoint is not None:
                raise GdbError("UNEXPECTED_BREAKPOINT_POLICY")

            mi_command = (
                "-target-select remote 127.0.0.1:65520"
                if is_attach
                else actions[command]
            )
            action_txn = await self._observation_request_until(mi_command, command_id, deadline)
            result = action_txn.get("result")
            if not isinstance(result, dict):
                raise GdbError("OWNED_COMMAND_RESULT_MISSING")
            output: dict[str, Any] = {
                "schema": "ladybug.feat010.owned-exec.v1",
                "owner_id": self._observation_owner_id,
                "session_id": self.id,
                "command_id": command_id,
                "command": command,
                "state": "UNKNOWN",
                "observation_generation": self._observation_generation,
                "state_generation_before": before["state_generation"],
                "state_generation_after": self._state_generation,
                "mi_result": result,
                "mi_error": result if result.get("class") == "error" else None,
                "text": _format_observation_output(action_txn["records"]),
                "stop_record": None,
                "stop_observation": None,
                "validated_stop": None,
                "current_state": None,
                "call_ledger": self._observation_call_ledger[ledger_start:],
                "overflow_evidence": self._observation_overflow_evidence,
                "error_code": None,
            }
            valid_action_result = (
                result.get("class") == "connected"
                if is_attach
                else result.get("class") == "running"
            )
            if not valid_action_result:
                output["state"] = "REJECTED"
                output["error_code"] = "OWNED_COMMAND_DID_NOT_RESUME"
                return output

            if is_attach and stop_expectation == "none":
                output["state"] = "RESULT_ONLY"
                return output
            stop_record = await self._wait_stop_after_until(
                action_txn["request_sequence"], deadline
            )
            output["stop_record"] = stop_record
            output["stop_observation"] = "SESSION_EVENT_ONLY"
            output["state_generation_after"] = self._state_generation
            if stop_expectation == "none":
                output["state"] = "OBSERVED"
                return output

            stop_fields = stop_record.get("fields")
            if not isinstance(stop_fields, dict):
                raise GdbError("STOP_RECORD_FIELDS_MISSING")
            if stop_expectation == "signal":
                if (
                    stop_fields.get("reason") != "signal-received"
                    or stop_fields.get("signal-name") != "SIGINT"
                ):
                    raise GdbError("EXPECTED_SIGINT_STOP_NOT_OBSERVED")
            elif stop_expectation == "breakpoint":
                frame = stop_fields.get("frame")
                if not isinstance(frame, dict):
                    raise GdbError("BREAKPOINT_STOP_FRAME_MISSING")
                if (
                    stop_fields.get("reason") != "breakpoint-hit"
                    or stop_fields.get("bkptno") != expected_breakpoint["number"]
                    or stop_fields.get("disp") != expected_breakpoint["disposition"]
                    or self._normalize_pc(frame.get("addr"))
                    != self._normalize_pc(expected_breakpoint["address"])
                ):
                    raise GdbError("EXPECTED_BREAKPOINT_STOP_NOT_OBSERVED")
            else:
                raise GdbError("STOP_EXPECTATION_INVALID")

            stop_frame = stop_fields.get("frame")
            stop_thread_id = stop_fields.get("thread-id")
            stop_pc = stop_frame.get("addr") if isinstance(stop_frame, dict) else None
            stop_pc_value = self._normalize_pc(stop_pc)
            if not isinstance(stop_thread_id, str) or stop_pc_value is None:
                raise GdbError("STOP_THREAD_OR_PC_MISSING")
            if self._state_generation != stop_record.get("state_generation"):
                raise GdbError("STATE_CHANGED_AFTER_STOP_RECORD")

            current = await self._thread_state_until(f"{command_id}:state-after", deadline)
            if (
                current["state_generation"] != stop_record.get("state_generation")
                or current["state_generation"] != self._state_generation
            ):
                raise GdbError("STATE_CHANGED_BETWEEN_STOP_AND_QUERY")
            if len(current["threads"]) != 1 or current["threads"][0].get("state") != "stopped":
                raise GdbError("POST_STOP_THREAD_STATE_INVALID")
            thread = current["threads"][0]
            frame = thread.get("frame")
            pc_text = frame.get("addr") if isinstance(frame, dict) else None
            pc = self._normalize_pc(pc_text)
            if pc is None:
                raise GdbError("POST_STOP_PC_INVALID")
            if (
                thread.get("id") != stop_thread_id
                or current.get("current_thread_id") != stop_thread_id
                or pc != stop_pc_value
            ):
                raise GdbError("STOP_RECORD_THREAD_OR_PC_MISMATCH")
            if stop_expectation == "breakpoint" and pc != self._normalize_pc(expected_breakpoint["address"]):
                raise GdbError("POST_STOP_PC_MISMATCH")
            if current["state_generation"] != self._state_generation:
                raise GdbError("POST_STOP_GENERATION_CHANGED")
            output["state"] = "VALIDATED_OBSERVATION"
            output["state_generation_after"] = current["state_generation"]
            output["current_state"] = {
                "thread_id": thread.get("id"),
                "thread_state": thread.get("state"),
                "pc": pc_text,
                "mi_result": current["mi_result"],
            }
            output["validated_stop"] = {
                "kind": stop_expectation,
                "reason": stop_fields.get("reason"),
                "signal_name": stop_fields.get("signal-name"),
                "breakpoint_number": stop_fields.get("bkptno"),
                "pc": pc_text,
                "thread_id": thread.get("id"),
                "sequence": stop_record.get("sequence"),
                "observation_generation": stop_record.get("observation_generation"),
                "state_generation": stop_record.get("state_generation"),
                "observation": "SESSION_EVENT_ONLY",
            }
            output["call_ledger"] = self._observation_call_ledger[ledger_start:]
            return output
        finally:
            if self._observation_active_operation_id == command_id:
                self._observation_active_operation_id = None
            self._observation_operation_lock.release()

    async def exec_owned_session(
        self,
        owner_id: str,
        command_id: str,
        command: str,
        stop_expectation: str,
        expected_breakpoint: dict[str, str] | None,
        budget_ms: int | float,
    ) -> dict[str, Any]:
        GdbManager._validate_owner(owner_id)
        if self._observation_owner_id != owner_id:
            raise GdbError("OWNER_SESSION_MISMATCH")
        if not isinstance(command_id, str) or not _OBSERVATION_ID_RE.fullmatch(command_id):
            raise GdbError("command_id must be validated ASCII identity data")
        if command_id in self._observation_used_command_ids:
            raise GdbError("COMMAND_ID_REUSED")
        if command not in {"target remote 127.0.0.1:65520", "continue"}:
            raise GdbError("OWNED_COMMAND_NOT_ALLOWED")
        if stop_expectation not in ("none", "signal", "breakpoint"):
            raise GdbError("stop_expectation must be none, signal, or breakpoint")
        is_attach = command == "target remote 127.0.0.1:65520"
        if (is_attach and stop_expectation == "breakpoint") or (
            not is_attach and stop_expectation == "signal"
        ):
            raise GdbError("stop_expectation does not match the approved action")
        if stop_expectation == "breakpoint":
            if (
                not isinstance(expected_breakpoint, dict)
                or set(expected_breakpoint) != {"number", "address", "disposition"}
                or any(not isinstance(expected_breakpoint.get(key), str) for key in ("number", "address", "disposition"))
                or not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", expected_breakpoint["number"])
                or self._normalize_pc(expected_breakpoint["address"]) is None
                or expected_breakpoint["disposition"] not in ("keep", "del")
            ):
                raise GdbError("expected_breakpoint requires number, address, and keep/del disposition")
        elif expected_breakpoint is not None:
            raise GdbError("expected_breakpoint is only valid for breakpoint expectation")
        if self._observation_state != "claimed" or self._observation_invalidated:
            raise GdbError("OBSERVATION_NOT_CLAIMED")
        deadline = self._deadline_from_budget(budget_ms)
        ledger_start = len(self._observation_call_ledger)
        self._observation_used_command_ids.add(command_id)

        def _failure_result(error_code: str) -> dict[str, Any]:
            ledger = [
                item for item in self._observation_call_ledger
                if item.get("operation_id") == command_id
            ]
            action = next(
                (item for item in ledger if item.get("call_id") == command_id), None
            )
            result = action.get("result") if isinstance(action, dict) else None
            records = action.get("records", []) if isinstance(action, dict) else []
            stop_candidates = [
                record for record in self._observation_stops
                if isinstance(action, dict)
                and record.get("sequence", 0) > action.get("request_sequence", 0)
            ]
            return {
                "schema": "ladybug.feat010.owned-exec.v1",
                "owner_id": owner_id,
                "session_id": self.id,
                "command_id": command_id,
                "command": command,
                "state": "UNKNOWN",
                "observation_generation": self._observation_generation,
                "mi_result": result,
                "mi_error": result if isinstance(result, dict) and result.get("class") == "error" else None,
                "text": _format_observation_output(records),
                "stop_record": stop_candidates[0] if len(stop_candidates) == 1 else None,
                "stop_observation": "SESSION_EVENT_ONLY" if stop_candidates else None,
                "validated_stop": None,
                "call_ledger": ledger,
                "error_code": error_code,
            }

        task = _retain_task(
            self._pending_tasks,
            asyncio.create_task(
                self._owned_exec_operation(
                    command_id, command, stop_expectation, expected_breakpoint, deadline
                )
            ),
        )
        try:
            result = await _await_task_until(task, deadline)
            _ensure_before_deadline(deadline)
            return result
        except asyncio.TimeoutError:
            self._mark_observation_invalid("OWNED_EXEC_DEADLINE_EXPIRED")
            return _failure_result("OWNED_EXEC_DEADLINE_EXPIRED")
        except asyncio.CancelledError:
            self._mark_observation_invalid("OWNED_EXEC_CANCELLED")
            raise
        except Exception as exc:
            self._mark_observation_invalid("OWNED_EXEC_FAILED")
            return _failure_result(str(exc))

    async def stop_observed_until(self, deadline: float) -> dict[str, Any]:
        if self._observation_task is None:
            raise GdbError("Session has no observation reader")
        self._mark_observation_invalid("OBSERVATION_STOP_REQUESTED")
        if self._observation_state != "closed":
            self._observation_state = "stopping"
        returncode = await self._close_until(deadline)
        process_exit_confirmed = type(returncode) is int and self._exit_confirmed
        task = self._observation_task
        if task is not None and not task.done() and asyncio.get_running_loop().time() < deadline:
            try:
                await _await_task_until(task, deadline)
            except asyncio.TimeoutError:
                pass
            except Exception:
                pass
        reader_exit_confirmed = bool(task is not None and task.done() and self._observation_eof)
        cleanup_complete = (
            process_exit_confirmed
            and reader_exit_confirmed
            and asyncio.get_running_loop().time() < deadline
        )
        if cleanup_complete:
            self._observation_state = "closed"
        if self._observation_exit_callback is not None:
            self._observation_exit_callback(self)
        return {
            "process_exit_confirmed": process_exit_confirmed,
            "returncode": self._exit_returncode if process_exit_confirmed else None,
            "reader_exit_confirmed": reader_exit_confirmed,
            "cleanup_complete": cleanup_complete,
            "reader_error": self._observation_reader_error,
            "overflow_evidence": self._observation_overflow_evidence,
        }

    def interrupt(self) -> None:
        """Send SIGINT to interrupt a running inferior.

        This does NOT acquire the session lock, so it can be called while
        a run/continue command is blocking.  The SIGINT causes GDB to stop
        the inferior and emit a *stopped record, which unblocks the pending
        send() call.
        """
        if self._owned_active:
            if self._observation_state != "legacy":
                raise GdbError("Legacy interrupt is disabled for an observed session")
            self._legacy_interrupt_history += 1
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
        if self._observation_state in ("claim-pending", "claimed"):
            self._mark_observation_invalid("SESSION_CLOSE_REQUESTED")
            self._observation_state = "stopping"
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
    def _copy_observation_claim_response(
        response: dict[str, Any],
    ) -> dict[str, Any]:
        def copy_value(value: Any) -> Any:
            if isinstance(value, dict):
                return {key: copy_value(item) for key, item in value.items()}
            if isinstance(value, list):
                return [copy_value(item) for item in value]
            if isinstance(value, tuple):
                return tuple(copy_value(item) for item in value)
            return value

        return {key: copy_value(value) for key, value in response.items()}

    def _observation_claim_reader_is_live(
        self,
        lease: _ServiceLease,
        session: GdbSession,
        owner_id: str,
        session_id: str,
    ) -> bool:
        reader = session._observation_task
        return (
            lease.owner_id == owner_id
            and lease.state == "ACTIVE"
            and not lease.stop_requested
            and lease.session is session
            and lease.session_id == session_id
            and self._sessions.get(session_id) is session
            and session.id == session_id
            and session._owned_active
            and not session._closing
            and not session._exit_confirmed
            and session.process.returncode is None
            and session._observation_owner_id == owner_id
            and session._observation_state in ("claim-pending", "claimed")
            and reader is not None
            and not reader.done()
            and not session._observation_invalidated
            and not session._observation_tainted
            and not session._observation_eof
            and session._observation_reader_error is None
        )

    @staticmethod
    def _validate_owner(owner_id: str) -> None:
        if not isinstance(owner_id, str) or owner_id == "":
            raise GdbError("owner_id must be a nonempty string")

    def _session_exit_confirmed(self, session: GdbSession, returncode: int) -> None:
        if type(returncode) is not int:
            return
        reader_pending = session._observation_task is not None and not session._observation_eof
        if not reader_pending and self._sessions.get(session.id) is session:
            self._sessions.pop(session.id, None)
        for lease in self._owned_leases.values():
            if lease.session is session:
                lease.state = "EXITED"
                lease.exit_confirmed = True
                lease.returncode = returncode
                lease.error_code = None

    def _session_observation_reader_exited(self, session: GdbSession) -> None:
        if (
            session._exit_confirmed
            and session._observation_eof
            and self._sessions.get(session.id) is session
        ):
            self._sessions.pop(session.id, None)

    def _register_gdb_process(
        self, process: asyncio.subprocess.Process, lease: _ServiceLease | None = None
    ) -> GdbSession:
        session = GdbSession(id=uuid.uuid4().hex[:8], process=process, kind="gdb")
        session._exit_callback = self._session_exit_confirmed
        session._observation_exit_callback = self._session_observation_reader_exited
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
        session._owned_active = True
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
        if lease.session is not None and lease.session._observation_task is not None:
            lease.session._mark_observation_invalid("EMERGENCY_OWNER_STOP")
            if lease.session._observation_state != "closed":
                lease.session._observation_state = "stopping"
        observer_pending = (
            lease.session is not None
            and lease.session._observation_task is not None
            and not lease.session._observation_eof
        )
        if lease.state in ("EXITED", "CANCELLED_BEFORE_START") and not observer_pending:
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

    def _observation_session(
        self, owner_id: str, session_id: str, *, require_active: bool = True
    ) -> tuple[_ServiceLease, GdbSession]:
        self._validate_owner(owner_id)
        if not isinstance(session_id, str) or not session_id:
            raise GdbError("session_id must be a nonempty string")
        lease = self._owned_leases.get(owner_id)
        if (
            lease is None
            or (require_active and lease.state != "ACTIVE")
            or lease.session is None
            or lease.session_id != session_id
            or lease.session.id != session_id
        ):
            raise GdbError("OWNER_SESSION_MISMATCH_OR_NOT_ACTIVE")
        return lease, lease.session

    async def claim_observed_session(
        self, owner_id: str, session_id: str, *, budget_ms: int | float
    ) -> dict[str, Any]:
        lease, session = self._observation_session(owner_id, session_id)
        if not _OBSERVATION_ID_RE.fullmatch(owner_id) or not _OBSERVATION_ID_RE.fullmatch(session_id):
            raise GdbError("owner_id and session_id must be validated ASCII identity data")
        deadline = self._owned_deadline(budget_ms)
        if not session._owned_active or lease.state != "ACTIVE":
            raise GdbError("OWNED_STARTUP_NOT_COMPLETE")
        if session._observation_state != "legacy":
            if (
                session._observation_state not in ("claim-pending", "claimed")
                or not self._observation_claim_reader_is_live(
                    lease, session, owner_id, session_id
                )
            ):
                raise GdbError("OBSERVATION_CLAIM_IS_SINGLE_USE")
            _ensure_before_deadline(deadline)
            if session._observation_state == "claim-pending":
                call = (
                    session._observation_active_transaction
                    if isinstance(session._observation_active_transaction, dict)
                    and session._observation_active_transaction.get("call_id")
                    == "claim:baseline"
                    else None
                )
                result = call.get("result") if isinstance(call, dict) else None
                pending_response = {
                    "schema": "ladybug.feat010.observed-claim.v1",
                    "owner_id": owner_id,
                    "session_id": session_id,
                    "state": "UNKNOWN",
                    "baseline_validated": False,
                    "reader_owner": "observation",
                    "generation": session._observation_generation,
                    "observation_generation": session._observation_generation,
                    "state_generation": session._state_generation,
                    "nonce": session._observation_nonce,
                    "baseline": None,
                    "mi_result": result,
                    "mi_error": (
                        result
                        if isinstance(result, dict)
                        and result.get("class") == "error"
                        else None
                    ),
                    "call_ledger": [call] if call is not None else [],
                    "raw_records": (
                        call.get("records", []) if isinstance(call, dict) else []
                    ),
                    "overflow_evidence": session._observation_overflow_evidence,
                    "error_code": "CLAIM_BASELINE_PENDING",
                }
                pending_result = self._copy_observation_claim_response(
                    pending_response
                )
                _ensure_before_deadline(deadline)
                return pending_result

            acknowledgement = session._observation_claim_ack
            if (
                not isinstance(acknowledgement, dict)
                or acknowledgement.get("schema")
                != "ladybug.feat010.observed-claim.v1"
                or acknowledgement.get("owner_id") != owner_id
                or acknowledgement.get("session_id") != session_id
                or acknowledgement.get("state") != "CLAIMED"
                or acknowledgement.get("baseline_validated") is not True
                or acknowledgement.get("reader_owner") != "observation"
                or acknowledgement.get("generation")
                != session._observation_generation
                or acknowledgement.get("observation_generation")
                != session._observation_generation
                or acknowledgement.get("nonce") != session._observation_nonce
            ):
                raise GdbError("OBSERVATION_CLAIM_IS_SINGLE_USE")
            _ensure_before_deadline(deadline)
            replayed_acknowledgement = self._copy_observation_claim_response(
                acknowledgement
            )
            _ensure_before_deadline(deadline)
            return replayed_acknowledgement
        if (
            session._legacy_send_history != 0
            or session._legacy_interrupt_history != 0
            or session._legacy_reader_active
        ):
            raise GdbError("LEGACY_ACTIVITY_PREVENTS_FRESH_CLAIM")

        # This transition is synchronous and occurs before the first await.
        session._observation_state = "claim-pending"
        session._observation_owner_id = owner_id
        session._observation_generation = 1
        session._state_generation = 1
        session._observation_nonce = uuid.uuid4().hex
        session._observation_invalidated = False
        try:
            session._start_observation_reader()
        except Exception as exc:
            session._mark_observation_invalid("READER_HANDOFF_FAILED")
            return {
                "schema": "ladybug.feat010.observed-claim.v1",
                "owner_id": owner_id,
                "session_id": session_id,
                "state": "UNKNOWN",
                "baseline_validated": False,
                "reader_owner": "observation",
                "generation": session._observation_generation,
                "observation_generation": session._observation_generation,
                "state_generation": session._state_generation,
                "nonce": session._observation_nonce,
                "call_ledger": [],
                "raw_records": [],
                "overflow_evidence": session._observation_overflow_evidence,
                "mi_result": None,
                "mi_error": None,
                "error_code": str(exc),
            }

        try:
            baseline = await session._baseline_until(deadline)
            _ensure_before_deadline(deadline)
            if (
                lease.state != "ACTIVE"
                or not session._owned_active
                or session._closing
                or session._exit_confirmed
                or session._observation_state != "claim-pending"
                or session._observation_invalidated
            ):
                raise GdbError("CLAIM_INVALIDATED_BEFORE_ADMISSION")
            if session._state_generation != session._observation_generation:
                raise GdbError("BASELINE_STATE_GENERATION_CHANGED")
            session._observation_state = "claimed"
            call = baseline["call"]
            result = baseline["mi_result"]
            acknowledgement = {
                "schema": "ladybug.feat010.observed-claim.v1",
                "owner_id": owner_id,
                "session_id": session_id,
                "state": "CLAIMED",
                "baseline_validated": True,
                "reader_owner": "observation",
                "generation": session._observation_generation,
                "observation_generation": session._observation_generation,
                "state_generation": session._state_generation,
                "nonce": session._observation_nonce,
                "producer_body_ascii": baseline["producer_body"],
                "baseline": baseline["payload"],
                "mi_result": result,
                "mi_error": None,
                "call_ledger": [call],
                "raw_records": call["records"],
                "overflow_evidence": session._observation_overflow_evidence,
                "error_code": None,
            }
            retained_acknowledgement = self._copy_observation_claim_response(
                acknowledgement
            )
            returned_acknowledgement = self._copy_observation_claim_response(
                acknowledgement
            )
            _ensure_before_deadline(deadline)
            session._observation_claim_ack = retained_acknowledgement
            return returned_acknowledgement
        except asyncio.CancelledError:
            session._mark_observation_invalid("CLAIM_CANCELLED")
            raise
        except Exception as exc:
            session._mark_observation_invalid("BASELINE_NOT_VALIDATED")
            call = session._observation_call_ledger[-1] if session._observation_call_ledger else None
            result = call.get("result") if isinstance(call, dict) else None
            return {
                "schema": "ladybug.feat010.observed-claim.v1",
                "owner_id": owner_id,
                "session_id": session_id,
                "state": "UNKNOWN",
                "baseline_validated": False,
                "reader_owner": "observation",
                "generation": session._observation_generation,
                "observation_generation": session._observation_generation,
                "state_generation": session._state_generation,
                "nonce": session._observation_nonce,
                "producer_body_ascii": (
                    build_connection_baseline_producer(
                        owner_id, session_id, session._observation_generation,
                        session._observation_nonce or "invalid",
                    ).decode("ascii")
                ),
                "baseline": None,
                "mi_result": result,
                "mi_error": result if isinstance(result, dict) and result.get("class") == "error" else None,
                "call_ledger": [call] if call is not None else [],
                "raw_records": call.get("records", []) if isinstance(call, dict) else [],
                "overflow_evidence": session._observation_overflow_evidence,
                "error_code": str(exc),
            }

    async def exec_owned_session(
        self,
        owner_id: str,
        session_id: str,
        command_id: str,
        command: str,
        *,
        budget_ms: int | float,
        stop_expectation: str = "none",
        expected_breakpoint: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        _, session = self._observation_session(owner_id, session_id)
        return await session.exec_owned_session(
            owner_id,
            command_id,
            command,
            stop_expectation,
            expected_breakpoint,
            budget_ms,
        )

    async def stop_observed_session(
        self, owner_id: str, session_id: str, *, budget_ms: int | float = 7000
    ) -> dict[str, Any]:
        _, session = self._observation_session(owner_id, session_id, require_active=False)
        if session._observation_task is None:
            raise GdbError("OBSERVATION_READER_NOT_STARTED")
        if isinstance(budget_ms, bool) or not isinstance(budget_ms, int) or not 1 <= budget_ms <= 7000:
            raise GdbError("budget_ms must be an integer from 1 through 7000")
        deadline = self._owned_deadline(budget_ms)
        result = await session.stop_observed_until(deadline)
        return {
            "schema": "ladybug.feat010.stop-observed.v1",
            "owner_id": owner_id,
            "session_id": session_id,
            "state": "CLEANUP_COMPLETE" if result["cleanup_complete"] else "UNRESOLVED",
            **result,
        }

    async def _stop_owned_until(
        self, lease: _ServiceLease, deadline: float
    ) -> OwnedSessionSnapshot:
        if lease.state == "CANCELLED_BEFORE_START":
            return self._snapshot(lease)
        if lease.state == "EXITED" and not (
            lease.session is not None
            and lease.session._observation_task is not None
            and not lease.session._observation_eof
        ):
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
        if session._observation_task is not None:
            cleanup = await session.stop_observed_until(deadline)
            returncode = cleanup["returncode"] if cleanup["process_exit_confirmed"] else None
        else:
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
        if s._observation_task is not None:
            cleanup = await s.stop_observed_until(deadline)
            if not cleanup["cleanup_complete"]:
                raise GdbError(
                    f"Session {session_id!r} observation cleanup was not confirmed; ownership retained"
                )
            returncode = cleanup["returncode"]
        else:
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
