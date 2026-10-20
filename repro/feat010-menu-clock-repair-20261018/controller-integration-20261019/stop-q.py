#!/usr/bin/env python3
"""Fixed offline SRO-Q/R/C qualifier for the copied FEAT-010 service.

This source is inert unless invoked by the pinned PowerShell wrapper after a
parent-published execution freeze.  It never connects to GDB or launches a
subject service process; the only child process is this file's bounded worker.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import importlib.machinery
import importlib.util
import json
import ntpath
import os
import re
import select
import signal
import subprocess
import sys
import time
import traceback
from pathlib import Path
from types import ModuleType
from typing import Any


ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parents[2]
FREEZE_PATH = ROOT / "integration-freeze.json"
TICKET_PATH = PROJECT_ROOT / "wiki" / "internal" / "tickets" / "feat-010-attract-menu-free-start.html"
TRANSCRIPT_PATH = PROJECT_ROOT / "repro" / "feat010-menu-clock-repair-20261018" / "stutter-runtime-gdb-transcript.json"
QUALIFIED_ROOT = PROJECT_ROOT / "repro" / "feat010-menu-clock-repair-20261018" / "controller-service-lease-c16-fixture-recovery-20261019"
WINDOWS_WORKSPACE_ROOT = "E:\\projects\\ladybug"
WSL_WORKSPACE_ROOT = Path("/mnt/e/projects/ladybug")
PYTHON_PATH = "/home/rastamafugg/.local/share/uv/tools/gdb-mcp/bin/python"
PYTHON_RESOLVED = "/home/rastamafugg/.local/share/uv/python/cpython-3.12.13-linux-x86_64-gnu/bin/python3.12"
PYTHON_SHA256 = "339de109f072e52523066d97a2b3372e358a10cc00c6a9df62c28a6618061900"
WSL_STOPQ_PATH = "/mnt/e/projects/ladybug/repro/feat010-menu-clock-repair-20261018/controller-integration-20261019/stop-q.py"
PINNED_LAUNCH_ARGV = ("wsl.exe", "--exec", PYTHON_PATH, "-B", WSL_STOPQ_PATH, "--supervisor")
TRANSCRIPT_SHA256 = "1617ba0bde61ca2bafe2d4603ae5d8f295c21b8efd3ef921d3f092b7560fef20"
PRODUCER_SHA256 = "5d745ba536497f8621263c5fd259281c2d58a9a28aaf4adc3679f1b50fe7b0bd"
INTERPRETER_EXECUTABLE = "/home/rastamafugg/.local/share/uv/python/cpython-3.12.13-linux-x86_64-gnu/bin/python3.12"

SOURCE_PATHS = (
    "service/gdb.py",
    "service/server.py",
    "stop-q.py",
    "run-integration-q.ps1",
)
FIXTURE_PATHS = (
    "evidence/sro-qualification-case-contract.json",
    "evidence/sro-baseline-independent-fixtures.json",
    "evidence/sro-stop-independent-fixtures.json",
    "evidence/sro-natural-sequence-fixture.json",
    "evidence/sro-producer-literal-fixture.json",
)
READ_INPUT_PATHS = ("stutter-runtime-gdb-transcript.json",)
QUALIFIED_INPUTS = (
    "baseline/gdb.py.txt",
    "baseline/server.py.txt",
    "candidate/gdb.py",
    "candidate/server.py",
    "service-q.py",
    "run-service-q.ps1",
    "service-q-freeze.json",
)
FIXTURE_NAMES = {
    "evidence/sro-qualification-case-contract.json": "case_contract",
    "evidence/sro-baseline-independent-fixtures.json": "baseline",
    "evidence/sro-stop-independent-fixtures.json": "stop",
    "evidence/sro-natural-sequence-fixture.json": "natural",
    "evidence/sro-producer-literal-fixture.json": "producer",
}
PHASES = {
    "stop-observation-admission": {
        "short": "Q", "maximum_ms": 30000,
        "case_ids": ("Q01", "Q02", "Q03", "Q04", "Q05"),
    },
    "stop-observation-reader": {
        "short": "R", "maximum_ms": 60000,
        "case_ids": tuple("R%02d" % value for value in range(1, 17)),
    },
    "stop-observation-compatibility": {
        "short": "C", "maximum_ms": 60000,
        "case_ids": tuple("C%02d" % value for value in range(1, 7)),
    },
}
WORKER_CASE_IDS = {
    "stop-observation-admission": tuple("Q%02d" % value for value in range(1, 6)),
    "stop-observation-reader": tuple("R%02d" % value for value in range(1, 17)),
    "stop-observation-compatibility": tuple("C%02d" % value for value in range(1, 6)),
}
EXPECTED_BY_CASE = {
    "Q01": "ORACLE_DISCRIMINATES",
    "Q02": "REJECT_NATIVE_UNKNOWN_SIGNAL",
    "Q03": "IDENTICAL_SESSION_EVENT_ONLY",
    "Q04": "ADMISSION_EXCLUSIVE_AND_CONTAINED",
    "Q05": "BASELINE_ORACLE_DISCRIMINATES",
    "R01": "VALIDATED_OBSERVATIONS_AND_BOTH_EXITS",
    "R02": "MISSING_CAPABILITY_NOT_SETUP_FAILURE",
    "R03": "EXACT_SINGLE_CALL_TYPED_PAYLOAD",
    "R04": "ONLY_STRICT_BOUND_INTEGER_ZERO_ACCEPTED",
    "R05": "NO_RETROACTIVE_ADMISSION",
    "R06": "NO_FALSE_RESULT_OR_STOP_PROOF",
    "R07": "UNKNOWN_ATTACH_AND_VALID_BREAKPOINT",
    "R08": "NO_VALIDATED_STOP",
    "R09": "NO_VALIDATED_STOP",
    "R10": "VALIDATED_OBSERVATION",
    "R11": "NO_VALIDATED_STOP",
    "R12": "FRESH_CLAIM_ONLY_ZERO_LEGACY_WRITES_ONE_READER",
    "R13": "TAINT_RETAIN_FAILURE_NO_EVICTION",
    "R14": "NO_LATE_ADMISSION_ONE_ENCLOSING_DEADLINE",
    "R15": "OWNER_ADDRESSABLE_INVALIDATED_CLEANUP",
    "R16": "PROCESS_TRUE_READER_FALSE_CLEANUP_FALSE_RETAIN_HANDLE",
    "C01": "UNCHANGED_SCHEMA_INTEGER_WAIT_ZERO_COUNTERS",
    "C02": "RAISE_RETAIN_REGISTRY_NO_FALSE_EXIT",
    "C03": "UNCHANGED_RESPONSE_AND_TIMEOUT_CONTRACT",
    "C04": "SEPARATE_EXITS_NO_REVIVAL_NO_SECOND_READER",
    "C05": "NO_OBSERVER_CREATED",
    "C06": "DIRECT_EXITS_CONFIRMED_NO_REAL_SUBJECT",
}
CASE_SUBCONTROLS = {
    "Q01": ("valid", "owner", "session", "generation", "token", "sequence", "boolean", "mi_error", "current_state", "cause_id", "coherent_copy", "command", "nested_generation", "nested_type", "error_code", "overflow_evidence", "extra_field", "float"),
    "Q02": ("capture_hash", "formatted_attach_is_unknown", "no_native_signal_field"),
    "Q03": ("same_raw_event", "different_hypothetical_cause", "same_event_only_classification"),
    "Q04": ("exclusive_claim", "collision_preserved", "pinned_allowlist", "popen_type_preserved", "popen_denied", "no_real_factory", "changed_argument_rejected", "changed_path_rejected"),
    "Q05": tuple("baseline-" + value for value in ("zero", "connection", "bool", "string", "null", "missing", "nonce", "owner", "session", "generation", "stream", "duplicate", "malformed", "truncated", "python", "api", "mi-error", "token", "invalidated")),
    "R01": ("startup", "claim", "baseline", "attach", "fresh_attach_state", "pre_continue_state", "breakpoint", "continue", "fresh_continue_state", "reader_count", "raw_count", "process_exit", "reader_exit", "no_cause_claim", "exception_before_call_capture_cleanup", "exception_after_call_capture_cleanup", "token_and_prompt_text", "tokenized_error_text", "console_stream_text", "stop_text"),
    "R02": ("historical_source_pin", "missing_claim_api", "missing_exec_api", "missing_stop_api", "not_setup_failure"),
    "R03": ("literal_hash", "empty_connections_once", "one_connection_once", "exact_zero_stdout", "exact_one_stdout", "module_restored", "no_io", "module_replacement_rejected", "module_removal_rejected"),
    "R04": tuple("baseline-control-" + value for value in ("zero", "connection", "bool", "string", "null", "missing", "nonce", "owner", "session", "generation", "stream", "duplicate", "malformed", "truncated", "python", "api", "mi-error", "token", "invalidated")),
    "R05": ("preclaim_user_send", "preclaim_interrupt", "stale_stop", "buffered_output", "no_retroactive_claim"),
    "R06": ("wrong_token", "duplicate_result", "pre_result_prompt", "mi_error", "no_validated_result", "connected_without_separator_valid", "empty_payload_rejected", "oversized_result_protocol_partial"),
    "R07": ("attach_missing_sigint_unknown", "continue_without_signal_valid_breakpoint", "event_only"),
    "R08": ("wrong_breakpoint", "disabled_breakpoint", "missing_breakpoint", "missing_query", "no_continue_write"),
    "R09": ("wrong_hit_number", "wrong_thread", "wrong_pc", "running_state", "unsupported_state", "generation_change"),
    "R10": ("enabled_pre_resume", "expected_disposition", "deleted_after_hit_allowed", "fresh_pc"),
    "R11": ("multiple_stops_ambiguous", "delayed_event_after_invalidation", "wrong_owner_no_write"),
    "R12": ("activity_before_claim", "claim_pending_gate", "postclaim_send_rejected", "postclaim_interrupt_rejected", "repeat_claim", "single_reader", "zero_legacy_delta"),
    "R13": ("record_cap", "byte_cap", "tainted", "first_overflow_retained", "no_eviction"),
    "R14": ("operation_lock", "transaction_lock", "drain", "read", "query", "no_late_admission"),
    "R15": ("lost_claim_reply", "owner_retained", "pending_command_invalidated", "cleanup_confirmed", "late_reply_no_revival"),
    "R16": ("process_exit_true", "reader_exit_false", "cleanup_false", "registry_retained", "later_reader_join"),
    "C01": ("legacy_start_schema", "legacy_send", "legacy_stop_schema", "wait_integer_zero", "no_escalation"),
    "C02": ("legacy_response_schema", "unknown_stop", "unresolved_raises", "registry_retained", "fixture_released"),
    "C03": ("one_command_write", "one_deadline", "timeout_result", "no_late_write"),
    "C04": ("claimed_close_invalidates", "late_reply_rejected", "repeat_stop_idempotent", "one_reader", "separate_exit_truth"),
    "C05": ("prestart_tombstone", "delayed_start_rejected", "zero_factory", "no_observer_reference"),
    "C06": ("worker_wait_confirmed", "worker_exit_zero", "wsl_wait_confirmed", "wsl_exit_zero", "preservation_equal"),
}
_CONTROL_TRACE: dict[str, dict[str, dict[str, Any]]] = {}


class _FixedUUID:
    def __init__(self, value: str) -> None:
        self.hex = value


class _ProtocolReader:
    def __init__(self, helper: ModuleType) -> None:
        self._reader = helper.FakeReader()
        self.process: Any = None
        self._active_readers = 0
        self._max_active_readers = 0
        self._reader_task_ids: set[int] = set()
        self._reader_tasks: dict[int, Any] = {}
        self._reader_roles: dict[str, int] = {}
        self._reader_task_roles: dict[int, str] = {}
        self._active_roles: dict[int, str] = {}
        self._overlaps: list[dict[str, Any]] = []
        self._block_next_observation_read = False
        self._reader_release = asyncio.Event()
        self._reader_release.set()
        self._reader_block_entered = asyncio.Event()

    async def readline(self) -> bytes:
        task = asyncio.current_task()
        task_id = id(task) if task is not None else 0
        session = getattr(self.process, "session", None)
        if session is None:
            role = "startup-legacy"
        elif task is session._observation_task:
            role = "observation"
        elif session._legacy_reader_active:
            role = "legacy"
        else:
            role = "unowned"
        self._reader_task_ids.add(task_id)
        self._reader_task_roles[task_id] = role
        if task is not None:
            self._reader_tasks[task_id] = task
        self._reader_roles[role] = self._reader_roles.get(role, 0) + 1
        if self._active_roles:
            self._overlaps.append({"entering": role, "active": list(self._active_roles.values())})
        self._active_roles[task_id] = role
        self._active_readers += 1
        self._max_active_readers = max(self._max_active_readers, self._active_readers)
        try:
            if role == "observation" and self._block_next_observation_read:
                self._block_next_observation_read = False
                self._reader_release.clear()
                self._reader_block_entered.set()
                await self._reader_release.wait()
            return await self._reader.readline()
        finally:
            self._active_readers -= 1
            self._active_roles.pop(task_id, None)

    def feed(self, value: bytes) -> None:
        if not value:
            return
        lines = value.splitlines(keepends=True)
        if not lines:
            lines = [value]
        for line in lines:
            if line:
                self._reader.feed(line)

    def release_blocked_read(self) -> None:
        self._reader_release.set()

    def eof(self) -> None:
        self._reader.eof()


class _ProtocolProcess:
    def __init__(self, helper: ModuleType, world: "_ProtocolWorld", options: dict[str, Any]) -> None:
        self.world = world
        self.options = options
        self.events = ["spawned"]
        self.stdout = _ProtocolReader(helper)
        self.stdout.process = self
        self.stdin = _ProtocolStdin(self)
        self.stderr = None
        self.returncode: int | None = None
        self.wait_calls = 0
        self.terminate_calls = 0
        self.kill_calls = 0
        self.drain_calls = 0
        self.setup_count = 0
        self._exit = asyncio.Event()

    async def wait(self) -> int | None:
        self.wait_calls += 1
        self.events.append("wait")
        if self.returncode is None:
            await self._exit.wait()
        return self.returncode

    def terminate(self) -> None:
        self.terminate_calls += 1
        self.finish(-15)

    def kill(self) -> None:
        self.kill_calls += 1
        self.finish(-9)

    def send_signal(self, _sig: int) -> None:
        self.events.append("signal")

    def finish(self, code: int) -> None:
        if self.returncode is None:
            self.returncode = code
            self.events.append("exit:" + str(code))
            self._exit.set()
            self.stdout.eof()


class _ProtocolStdin:
    def __init__(self, process: _ProtocolProcess) -> None:
        self.process = process
        self.last_write = b""
        self.writes: list[bytes] = []

    def write(self, value: bytes) -> None:
        self.last_write = value
        self.writes.append(value)
        self.process.events.append("write:" + value.decode("utf-8", errors="replace").rstrip())

    async def drain(self) -> None:
        process = self.process
        process.drain_calls += 1
        raw = self.last_write.decode("ascii", errors="strict").rstrip("\n")
        if raw == "quit":
            process.finish(0)
            return
        token_match = re.match(r"^([0-9]+)(-.*)$", raw)
        if token_match is None:
            process.setup_count += 1
            process.stdout.feed(b"^done\n(gdb)\n")
            return
        token, command = token_match.groups()
        world = process.world
        transaction = next((item for item in world.natural["transactions"] if item.get("token") == token), None)
        kind = transaction.get("kind") if type(transaction) is dict else None
        drain_delay = world.drain_delay_by_kind.get(kind, 0.0)
        if drain_delay > 0:
            await asyncio.sleep(drain_delay)
        delay = world.response_delay_by_kind.get(kind, 0.0)
        if delay > 0:
            async def delayed_response() -> None:
                await asyncio.sleep(delay)
                lease = getattr(world.manager, "_owned_leases", {}).get(world.natural["owner_id"])
                session = lease.session if lease is not None else None
                world.late_replies.append({"kind": kind, "token": token, "invalidated_before_delivery": bool(session and session._observation_invalidated)})
                process.stdout.feed(world.respond(token, command))
            task = asyncio.create_task(delayed_response())
            world.pending_response_tasks.append(task)
            await asyncio.sleep(0)
            return
        process.stdout.feed(world.respond(token, command))


class _ProtocolWorld:
    """Fixed parent-authored MI schedules; never derives expected bytes from the subject."""

    def __init__(self, helper: ModuleType, natural: dict[str, Any], stop: dict[str, Any], baseline_payload: dict[str, Any] | None = None) -> None:
        self.helper = helper
        self.natural = natural
        self.stop = stop
        self.baseline_payload = baseline_payload or {
            "schema": "ladybug.feat010.connection-baseline.v1",
            "owner_id": natural["owner_id"],
            "session_id": natural["session_id"],
            "generation": natural["observation_generation"],
            "nonce": natural["nonce_uuid_hex"],
            "connection_count": 0,
        }
        self.processes: list[_ProtocolProcess] = []
        self.factory_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        self.real_calls = 0
        self.next_options: dict[str, Any] = {}
        self.manager: Any = None
        self.action_count = 0
        self.query_counts: dict[str, int] = {}
        self.baseline_raw_payload: str | None = None
        self.baseline_marker = "~"
        self.baseline_duplicates = 1
        self.baseline_result_class = "done"
        self.baseline_result_token: str | None = None
        self.baseline_error_message: str | None = None
        self.transaction_fault: str | None = None
        self.inject_state_change = False
        self.preclaim_activity: str | None = None
        self.action_mode: dict[str, Any] = {}
        self.breakpoint_body: str | None = None
        self.state_body_override: dict[str, str] = {}
        self.action_events: dict[str, list[str]] = {}
        self.response_delay_by_kind: dict[str, float] = {}
        self.pending_response_tasks: list[asyncio.Task[Any]] = []
        self.inject_state_change_on: set[str] = set()
        self.flood_baseline_records: int = 0
        self.flood_baseline_bytes: int = 0
        self.block_reader_after_claim: bool = False
        self.transaction_fault_by_kind: dict[str, str] = {}
        self.drain_delay_by_kind: dict[str, float] = {}
        self.action_event_delay_by_kind: dict[str, float] = {}
        self.late_action_events: list[dict[str, Any]] = []
        self.late_replies: list[dict[str, Any]] = []

    async def factory(self, *args: Any, **kwargs: Any) -> _ProtocolProcess:
        self.factory_calls.append((args, kwargs))
        if not (
            args[:3] == ("gdb", "--interpreter=mi2", "--quiet")
            and len(args) == 3
            and kwargs.get("stdin") is asyncio.subprocess.PIPE
            and kwargs.get("stdout") is asyncio.subprocess.PIPE
            and kwargs.get("stderr") is asyncio.subprocess.STDOUT
            and set(kwargs) == {"stdin", "stdout", "stderr", "cwd"}
        ):
            self.real_calls += 1
            raise RuntimeError("actual subject requested a non-fixed fake-GDB factory")
        process = _ProtocolProcess(self.helper, self, self.next_options)
        self.processes.append(process)
        return process

    def _thread_body(self, pc: str) -> str:
        source = "attach" if pc == "0x0000c002" else "continuation"
        body = self.stop[source]["raw_state_result_body"]
        original = self.stop[source]["expected_pc"]
        return re.sub(r'addr="0[xX][0-9a-fA-F]+"', 'addr="0x%08x"' % original, body, count=1) if pc == "__fixed__" else re.sub(r'addr="0[xX][0-9a-fA-F]+"', 'addr="%s"' % pc, body, count=1)

    def respond(self, token: str, command: str) -> bytes:
        natural_transactions = self.natural["transactions"]
        transaction = next((item for item in natural_transactions if item.get("token") == token), None)
        if transaction is None:
            raise RuntimeError("subject issued a token outside parent natural sequence: " + token)
        kind = transaction["kind"]
        if kind == "baseline":
            payload = dict(self.baseline_payload)
            stdout = "LB_SRO_BASELINE:" + json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n"
            if self.baseline_raw_payload is not None:
                stdout = "LB_SRO_BASELINE:" + self.baseline_raw_payload + "\n"
            result_token = self.baseline_result_token or token
            streams = (self.baseline_marker + json.dumps(stdout) + "\n") * self.baseline_duplicates
            if self.flood_baseline_records:
                streams = (self.baseline_marker + json.dumps("LB_SRO_BASELINE:{bad}") + "\n") * self.flood_baseline_records
            if self.flood_baseline_bytes:
                streams = self.baseline_marker + json.dumps("X" * self.flood_baseline_bytes) + "\n"
            state_change = '*stopped,reason="signal-received",signal-name="SIGINT",frame={addr="0x0000c002"},thread-id="1",stopped-threads="all"\n' if self.inject_state_change or kind in self.inject_state_change_on else ""
            result_line = result_token + "^" + self.baseline_result_class
            if self.baseline_result_class == "error":
                message = self.baseline_error_message or "controlled unsupported baseline"
                result_line += ",msg=" + json.dumps(message)
            if self.transaction_fault == "pre-result-prompt":
                return (state_change + streams + "(gdb)\n" + result_line + "\n(gdb)\n").encode("ascii")
            if self.transaction_fault == "duplicate-result":
                return (state_change + streams + result_line + "\n" + result_line + "\n(gdb)\n").encode("ascii")
            if self.transaction_fault == "missing-result":
                return (state_change + streams + "(gdb)\n").encode("ascii")
            return (state_change + streams + result_line + "\n(gdb)\n").encode("ascii")
        if kind in ("pre-attach-thread-info",):
            return (token + "^done,threads=[]\n(gdb)\n").encode("ascii")
        if kind in ("post-attach-thread-info", "pre-continue-thread-info"):
            body = self.state_body_override.get(kind, self._thread_body("0x0000c002"))
            event = '*stopped,reason="signal-received",signal-name="SIGINT",frame={addr="0x0000c002"},thread-id="1",stopped-threads="all"\n' if kind in self.inject_state_change_on else ""
            fault = self.transaction_fault_by_kind.get(kind)
            if fault == "missing-result":
                return (event + "(gdb)\n").encode("ascii")
            if fault == "mi-error":
                return (event + token + '^error,msg="controlled query error"\n(gdb)\n').encode("ascii")
            return (event + token + body + "\n(gdb)\n").encode("ascii")
        if kind == "pre-continue-break-list":
            body = self.breakpoint_body or self.stop["continuation"]["raw_breakpoint_result_body"]
            fault = self.transaction_fault_by_kind.get(kind)
            if fault == "missing-result":
                return b"(gdb)\n"
            if fault == "mi-error":
                return (token + '^error,msg="controlled query error"\n(gdb)\n').encode("ascii")
            return (token + body + "\n(gdb)\n").encode("ascii")
        if kind == "post-continue-thread-info":
            body = self.state_body_override.get(kind, self._thread_body("0x00000350"))
            event = '*stopped,reason="signal-received",signal-name="SIGINT",frame={addr="0x0000c002"},thread-id="1",stopped-threads="all"\n' if kind in self.inject_state_change_on else ""
            return (event + token + body + "\n(gdb)\n").encode("ascii")
        if kind == "attach":
            self.action_count += 1
            event = self.action_mode.get("attach_event", self.stop["attach"]["raw_event"])
            result_class = self.action_mode.get("attach_result", "connected")
            events = self.action_events.get("attach", [event] if event else [])
            if self.transaction_fault_by_kind.get("attach") == "empty-result-payload":
                return ("".join(item + "\n" for item in events) + token + "^connected,\n(gdb)\n").encode("ascii")
            return (token + "^" + result_class + "\n" + "".join(item + "\n" for item in events) + "(gdb)\n").encode("ascii")
        if kind == "continue":
            self.action_count += 1
            running = transaction["intermediate_running_event"]
            stop_event = self.action_mode.get("continue_event", self.stop["continuation"]["raw_event"])
            result_class = self.action_mode.get("continue_result", "running")
            events = self.action_events.get("continue", [stop_event] if stop_event else [])
            event_bytes = "".join(item + "\n" for item in events).encode("ascii")
            if result_class == "error":
                return (token + "^error,msg=\"controlled action error\"\n(gdb)\n").encode("ascii")
            event_delay = self.action_event_delay_by_kind.get(kind, 0.0)
            if event_delay > 0 and events:
                process = self.processes[-1]
                async def late_events() -> None:
                    await asyncio.sleep(event_delay)
                    session = getattr(self.manager, "_owned_leases", {}).get(self.natural["owner_id"])
                    observed_session = session.session if session is not None else None
                    self.late_action_events.append({
                        "kind": kind,
                        "events": list(events),
                        "invalidated_before_delivery": bool(observed_session and observed_session._observation_invalidated),
                    })
                    process.stdout.feed(event_bytes + b"(gdb)\n")
                task = asyncio.create_task(late_events())
                self.pending_response_tasks.append(task)
                event_bytes = b""
            return (running + "\n" + token + "^" + result_class + "\n(gdb)\n").encode("ascii") + event_bytes + (b"(gdb)\n" if event_bytes else b"")
        raise RuntimeError("natural schedule contains an unsupported transaction kind: " + kind)


class _ActualLedger:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def wrap_async(self, owner: Any, name: str, label: str) -> None:
        original = getattr(owner, name)
        if not asyncio.iscoroutinefunction(original):
            raise TypeError("actual service method is not async: " + label)

        async def observed(*args: Any, **kwargs: Any) -> Any:
            self.rows.append({"method": label, "event": "enter"})
            try:
                result = await original(*args, **kwargs)
            except BaseException as exc:
                self.rows.append({"method": label, "event": "raise", "exception_type": type(exc).__name__, "error": str(exc)})
                raise
            self.rows.append({"method": label, "event": "return", "result_type": type(result).__name__})
            return result

        setattr(owner, name, observed)


_PHASE_LEDGER: dict[str, Any] = {
    "service_calls": [], "factory_calls": [], "reader_count": 0,
    "raw_record_count": 0, "real_factory_calls": 0,
    "real_gdb_calls": 0, "real_network_calls": 0,
}
_CURRENT_CASE_ID = ""


def _safe_fixture_value(value: Any) -> Any:
    if value is None or type(value) in (str, bool, int, float):
        return value
    if type(value) in (tuple, list):
        return [_safe_fixture_value(item) for item in value]
    if type(value) is dict and all(type(key) is str for key in value):
        return {key: _safe_fixture_value(item) for key, item in value.items()}
    raise TypeError("actual factory ledger contains a non-serializable argument")


def _capture_run(world: Any, service_calls: list[dict[str, Any]], session: Any = None, hooks: Any = None) -> None:
    for item in service_calls:
        _PHASE_LEDGER["service_calls"].append({"case_id": _CURRENT_CASE_ID, **item})
    for args, kwargs in getattr(world, "factory_calls", []):
        _PHASE_LEDGER["factory_calls"].append({
            "case_id": _CURRENT_CASE_ID,
            "argv": _safe_fixture_value(args),
            "kwargs": _safe_fixture_value(kwargs),
        })
    for process in getattr(world, "processes", []):
        reader = getattr(process, "stdout", None)
        roles = getattr(reader, "_reader_task_roles", {})
        _PHASE_LEDGER["reader_count"] += len({task for task, role in roles.items() if role == "observation"})
    if session is not None:
        _PHASE_LEDGER["raw_record_count"] += int(session._observation_record_count)
    denied = getattr(hooks, "counts", {}) if hooks is not None else {}
    process_attempts = sum(
        count for name, count in denied.items()
        if name.startswith(("subprocess.", "asyncio.create_subprocess_shell", "os."))
    )
    network_attempts = sum(count for name, count in denied.items() if name.startswith("socket."))
    nonfixed_factory_calls = int(getattr(world, "real_calls", 0))
    _PHASE_LEDGER["real_factory_calls"] += nonfixed_factory_calls + process_attempts
    _PHASE_LEDGER["real_gdb_calls"] += nonfixed_factory_calls + process_attempts
    _PHASE_LEDGER["real_network_calls"] += network_attempts


def _load_historical_helpers(context: dict[str, Any]) -> ModuleType:
    path = _frozen_path(context["freeze"]["qualified_service_root"]) / "service-q.py"
    expected = context["qualified_sha256"]["service-q.py"]
    if _sha256(path) != expected:
        raise ValueError("historical helper source changed before definition import")
    name = "_ladybug_sro_historical_helper"
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    if spec is None or spec.loader is None:
        raise ImportError("cannot load pinned historical helper definitions")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    loader.exec_module(module)
    if _sha256(path) != expected:
        raise ValueError("historical helper changed during import")
    return module


def _load_actual_service() -> tuple[ModuleType, ModuleType]:
    for name in ("gdb", "server"):
        sys.modules.pop(name, None)
    gdb_path = ROOT / "service" / "gdb.py"
    server_path = ROOT / "service" / "server.py"
    gdb_loader = importlib.machinery.SourceFileLoader("gdb", str(gdb_path))
    gdb_spec = importlib.util.spec_from_loader("gdb", gdb_loader)
    if gdb_spec is None or gdb_spec.loader is None:
        raise ImportError("cannot construct actual candidate GDB module")
    gdb_module = importlib.util.module_from_spec(gdb_spec)
    sys.modules["gdb"] = gdb_module
    gdb_loader.exec_module(gdb_module)
    server_loader = importlib.machinery.SourceFileLoader("server", str(server_path))
    server_spec = importlib.util.spec_from_loader("server", server_loader)
    if server_spec is None or server_spec.loader is None:
        raise ImportError("cannot construct actual candidate service module")
    server_module = importlib.util.module_from_spec(server_spec)
    sys.modules["server"] = server_module
    server_loader.exec_module(server_module)
    return gdb_module, server_module


async def _run_natural_sequence(
    context: dict[str, Any], *, failure_injection: str | None = None,
    diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    helper = _load_historical_helpers(context)
    natural = context["fixture_data"]["natural"]
    stop = context["fixture_data"]["stop"]
    world = _ProtocolWorld(helper, natural, stop)
    hooks = helper.DenyHooks()
    hooks.install(world.factory)
    ledger = _ActualLedger()
    gdb: ModuleType | None = None
    server: ModuleType | None = None
    original_uuid_module: Any = None
    manager: Any = None
    start: Any = None
    claim: Any = None
    attach: Any = None
    continuation: Any = None
    cleanup: Any = None
    session = None
    sid: str | None = None
    primary_exception: BaseException | None = None
    finalization_errors: list[str] = []
    cleanup_attempted = False
    capture_completed = False
    process = None
    try:
        # Denial hooks are active before candidate module source is executed.
        gdb, server = _load_actual_service()
        original_uuid_module = gdb.uuid
        fixed_values = iter((natural["startup_uuid_hex"], natural["nonce_uuid_hex"]))
        gdb.uuid = type("_FixedUuidModule", (), {"uuid4": staticmethod(lambda: _FixedUUID(next(fixed_values)))})
        for owner, methods in (
            (gdb.GdbManager, ("start_owned_session", "claim_observed_session", "exec_owned_session", "stop_session_by_owner", "stop_observed_session")),
            (gdb.GdbSession, ("_baseline_until", "_observation_request_until", "_thread_state_until", "_breakpoint_until", "_owned_exec_operation", "_observation_reader", "stop_observed_until")),
        ):
            for name in methods:
                ledger.wrap_async(owner, name, owner.__name__ + "." + name)
        for name in ("start_owned_session", "claim_observed_session", "exec_owned_session", "stop_session_by_owner", "stop_observed_session"):
            ledger.wrap_async(server, name, "server." + name)
        manager = gdb.GdbManager()
        manager_wrap_original = manager
        server.manager = manager
        world.manager = manager
        if failure_injection == "before-call":
            raise RuntimeError("controlled natural-sequence failure before service call")
        start = await server.start_owned_session(natural["owner_id"], budget_ms=8000)
        sid = start.get("session_id") if type(start) is dict else None
        lease = manager._owned_leases.get(natural["owner_id"])
        session = lease.session if lease is not None else None
        process = session.process if session is not None else (world.processes[-1] if world.processes else None)
        if process is not None:
            process.session = session
        if failure_injection == "after-call":
            async def held_response() -> None:
                await asyncio.Event().wait()
            world.pending_response_tasks.append(asyncio.create_task(held_response()))
            raise RuntimeError("controlled natural-sequence failure after fake service call")
        claim = await server.claim_observed_session(natural["owner_id"], sid, budget_ms=5000)
        attach = await server.exec_owned_session(
            natural["owner_id"], sid, "attach-001", natural["attach_command"],
            budget_ms=7000, stop_expectation="signal",
        )
        continuation = await server.exec_owned_session(
            natural["owner_id"], sid, "continue-001", "continue",
            budget_ms=7000, stop_expectation="breakpoint",
            expected_breakpoint=natural["expected_breakpoint"],
        )
        lease = manager._owned_leases.get(natural["owner_id"])
        session = lease.session if lease is not None else None
        process = session.process if session is not None else None
        cleanup = await server.stop_observed_session(natural["owner_id"], sid, budget_ms=7000)
    except BaseException as exc:
        primary_exception = exc
        raise
    finally:
        try:
            lease = manager._owned_leases.get(natural["owner_id"]) if manager is not None else None
            if lease is not None:
                if session is None:
                    session = lease.session
                if process is None and session is not None:
                    process = session.process
                if cleanup is None and server is not None:
                    cleanup_attempted = True
                    if session is not None and session._observation_task is not None and sid is not None:
                        cleanup = await server.stop_observed_session(natural["owner_id"], sid, budget_ms=7000)
                    else:
                        cleanup = await server.stop_session_by_owner(natural["owner_id"], budget_ms=7000)
            if process is not None and process.returncode is None:
                process.finish(0)
        except BaseException as exc:
            finalization_errors.append("cleanup: " + type(exc).__name__ + ": " + str(exc))
        try:
            if world.pending_response_tasks:
                _done, pending = await asyncio.wait(world.pending_response_tasks, timeout=1.0)
                for task in pending:
                    task.cancel()
                if pending:
                    await asyncio.gather(*pending, return_exceptions=True)
        except BaseException as exc:
            finalization_errors.append("pending-task cleanup: " + type(exc).__name__ + ": " + str(exc))
        try:
            hooks.restore()
        except BaseException as exc:
            finalization_errors.append("hook restore: " + type(exc).__name__ + ": " + str(exc))
        try:
            if gdb is not None and original_uuid_module is not None:
                gdb.uuid = original_uuid_module
        except BaseException as exc:
            finalization_errors.append("UUID restore: " + type(exc).__name__ + ": " + str(exc))
        try:
            _capture_run(world, ledger.rows, session, hooks)
            capture_completed = True
        except BaseException as exc:
            finalization_errors.append("partial evidence capture: " + type(exc).__name__ + ": " + str(exc))
        if diagnostics is not None:
            owner_lease = manager._owned_leases.get(natural["owner_id"]) if manager is not None else None
            pending_count = sum(not task.done() for task in world.pending_response_tasks)
            resources_clear = (
                (process is None or process.returncode is not None)
                and pending_count == 0
                and (owner_lease is None or owner_lease.state in ("EXITED", "CANCELLED_BEFORE_START"))
            )
            diagnostics.update({
                "exception_type": type(primary_exception).__name__ if primary_exception is not None else None,
                "exception_message": str(primary_exception) if primary_exception is not None else None,
                "service_ledger_entries": len(ledger.rows),
                "service_call_entries": sum(item.get("event") == "enter" for item in ledger.rows),
                "cleanup_attempted": cleanup_attempted,
                "cleanup_result": cleanup,
                "pending_tasks_remaining": pending_count,
                "resources_clear": resources_clear,
                "failure_retained": primary_exception is not None and str(primary_exception).startswith("controlled natural-sequence failure"),
                "capture_completed": capture_completed,
                "finalization_errors": list(finalization_errors),
            })
        if primary_exception is None and finalization_errors:
            raise RuntimeError("natural-sequence finalization failed: " + "; ".join(finalization_errors))
    return {
        "start": start,
        "claim": claim,
        "attach": attach,
        "continuation": continuation,
        "cleanup": cleanup,
        "session": session,
        "process": process,
        "world": world,
        "deny_hooks": hooks,
        "actual_method_ledger": ledger.rows,
        "manager": manager_wrap_original,
        "gdb_module": gdb,
    }


def _run_r01(context: dict[str, Any]) -> dict[str, Any]:
    run = asyncio.run(_run_natural_sequence(context))
    natural = context["fixture_data"]["natural"]
    stop = context["fixture_data"]["stop"]
    start, claim, attach = run["start"], run["claim"], run["attach"]
    continuation, cleanup = run["continuation"], run["cleanup"]
    session, process, world = run["session"], run["process"], run["world"]
    _assert("R01", "startup", type(start) is dict and start.get("state") == "ACTIVE" and start.get("owner_id") == natural["owner_id"], "owned startup did not reach ACTIVE", start)
    _assert("R01", "claim", type(claim) is dict and claim.get("state") == "CLAIMED" and claim.get("baseline_validated") is True and claim.get("reader_owner") == "observation", "claim did not transfer the fresh session to observer", claim)
    _assert("R01", "baseline", type(claim.get("baseline")) is dict and claim["baseline"] == world.baseline_payload and claim.get("mi_result", {}).get("class") == "done" and claim.get("mi_result", {}).get("token") == "1", "claim baseline does not match independent owner/session/generation/nonce payload", claim)
    attach_record = attach.get("stop_record") if type(attach) is dict else None
    attach_thread = attach.get("current_state") if type(attach) is dict else None
    _attach_fixture, attach_binding = _owned_exec_oracle_fixture(context, "signal")
    attach_oracle_valid = _oracle_envelope_valid(attach, attach_binding)
    _assert("R01", "attach", type(attach) is dict and attach.get("state") == "VALIDATED_OBSERVATION" and attach.get("mi_result", {}).get("class") == "connected" and attach.get("mi_result", {}).get("token") == "3" and attach_record.get("raw") == stop["attach"]["raw_event"] and attach_oracle_valid, "attach response/event did not match the fixture-bound raw/parsed owned-exec oracle", {"response": attach, "oracle_valid": attach_oracle_valid})
    _assert("R01", "fresh_attach_state", type(attach_thread) is dict and attach_thread.get("thread_id") == stop["thread_id"] and attach_thread.get("thread_state") == "stopped" and int(attach_thread.get("pc", "0"), 16) == stop["attach"]["expected_pc"], "fresh attach thread state differs from parent fixture", attach_thread)
    precontinue = next((call for call in session._observation_call_ledger if call.get("call_id") == "continue-001:state-before"), None) if session is not None else None
    _assert("R01", "pre_continue_state", type(precontinue) is dict and precontinue.get("result", {}).get("class") == "done" and precontinue.get("result", {}).get("token") == "5" and precontinue.get("state_generation_before") == 2, "pre-continue thread query did not bind the expected state generation", precontinue)
    pre_break = next((call for call in session._observation_call_ledger if call.get("call_id") == "continue-001:breakpoint-before"), None) if session is not None else None
    _assert("R01", "breakpoint", type(pre_break) is dict and pre_break.get("result", {}).get("class") == "done" and pre_break.get("result", {}).get("token") == "6" and "BreakpointTable" in pre_break.get("result", {}).get("fields", {}), "pre-resume breakpoint identity was not queried with its own MI token", pre_break)
    cont_record = continuation.get("stop_record") if type(continuation) is dict else None
    _continue_fixture, continue_binding = _owned_exec_oracle_fixture(context, "breakpoint")
    continue_oracle_valid = _oracle_envelope_valid(continuation, continue_binding)
    _assert("R01", "continue", type(continuation) is dict and continuation.get("state") == "VALIDATED_OBSERVATION" and continuation.get("mi_result", {}).get("class") == "running" and continuation.get("mi_result", {}).get("token") == "7" and cont_record.get("raw") == stop["continuation"]["raw_event"] and continue_oracle_valid, "continue response/event did not match the fixture-bound raw/parsed owned-exec oracle", {"response": continuation, "oracle_valid": continue_oracle_valid})
    post_state = continuation.get("current_state") if type(continuation) is dict else None
    _assert("R01", "fresh_continue_state", type(post_state) is dict and post_state.get("thread_id") == stop["thread_id"] and post_state.get("thread_state") == "stopped" and int(post_state.get("pc", "0"), 16) == stop["continuation"]["expected_pc"] and continuation.get("validated_stop", {}).get("observation") == "SESSION_EVENT_ONLY", "fresh continuation PC/thread does not match the independent fixture", post_state)
    reader = process.stdout if process is not None else None
    observer_task_id = id(session._observation_task) if session is not None and session._observation_task is not None else None
    observer_was_measured = reader is not None and observer_task_id in reader._reader_task_ids and reader._reader_tasks.get(observer_task_id) is session._observation_task
    reader_metrics = {
        "max_concurrent_readline": reader._max_active_readers if reader is not None else None,
        "observer_task_id": observer_task_id,
        "observer_task_measured": observer_was_measured,
        "role_readline_calls": dict(reader._reader_roles) if reader is not None else {},
        "overlaps": list(reader._overlaps) if reader is not None else [],
        "legacy_reader_active_after_claim": session._legacy_reader_active if session is not None else None,
        "factory_calls": len(world.factory_calls),
    }
    _assert("R01", "reader_count", session is not None and session._observation_task is not None and observer_was_measured and reader._max_active_readers == 1 and reader._reader_roles.get("observation", 0) > 0 and reader._reader_roles.get("unowned", 0) == 0 and reader._reader_roles.get("legacy", 0) == 0 and not reader._overlaps and not session._legacy_reader_active and world.action_count == 2 and len(world.factory_calls) == 1, "instrumented stdout reader ownership was not exclusive and non-overlapping", reader_metrics)
    _assert("R01", "raw_count", session is not None and session._observation_record_count == natural["expected_raw_record_count"], "raw-record count differs from independent natural schedule", session._observation_record_count if session else None)
    _assert("R01", "process_exit", type(cleanup) is dict and cleanup.get("process_exit_confirmed") is True and cleanup.get("returncode") == 0 and process is not None and process.wait_calls == 1, "direct fake process exit was not confirmed independently", cleanup)
    _assert("R01", "reader_exit", type(cleanup) is dict and cleanup.get("reader_exit_confirmed") is True and cleanup.get("cleanup_complete") is True and session is not None and session._observation_eof, "observer EOF/join was not independently confirmed", cleanup)
    call_ids = [call.get("call_id") for call in session._observation_call_ledger] if session is not None else []
    _assert("R01", "no_cause_claim", type(attach) is dict and type(continuation) is dict and "cause_command_id" not in attach and "cause_command_id" not in continuation and attach.get("stop_observation") == "SESSION_EVENT_ONLY" and continuation.get("stop_observation") == "SESSION_EVENT_ONLY" and call_ids == ["claim:baseline", "attach-001:state-before", "attach-001", "attach-001:state-after", "continue-001:state-before", "continue-001:breakpoint-before", "continue-001", "continue-001:state-after"], "ledger asserts causal attribution or omitted/reordered a fixed transaction", {"call_ids": call_ids})

    def exception_probe(injection: str) -> dict[str, Any]:
        diagnostics: dict[str, Any] = {}
        try:
            asyncio.run(_run_natural_sequence(context, failure_injection=injection, diagnostics=diagnostics))
        except BaseException as exc:
            raised = {"type": type(exc).__name__, "message": str(exc)}
        else:
            raised = None
        claim_diagnostics: dict[str, Any] = {}
        try:
            asyncio.run(_claim_probe_async(context, failure_injection=injection, diagnostics=claim_diagnostics))
        except BaseException as exc:
            claim_raised = {"type": type(exc).__name__, "message": str(exc)}
        else:
            claim_raised = None
        return {"raised": raised, "diagnostics": diagnostics, "claim_raised": claim_raised, "claim_diagnostics": claim_diagnostics}

    before_exception = exception_probe("before-call")
    before_diagnostics = before_exception["diagnostics"]
    before_claim_diagnostics = before_exception["claim_diagnostics"]
    before_cleanup_retained = (before_diagnostics.get("resources_clear") is True
                               and before_diagnostics.get("capture_completed") is True
                               and before_diagnostics.get("finalization_errors") == [])
    before_claim_cleanup_retained = (before_claim_diagnostics.get("resources_clear") is True
                                     and before_claim_diagnostics.get("capture_completed") is True
                                     and before_claim_diagnostics.get("finalization_errors") == [])
    before_expected_exception = {"type": "RuntimeError", "message": "controlled natural-sequence failure before service call"}
    before_expected_entries = context["fixture_data"]["stop"]["recovery_r1"]["exception_capture"]["before_call_service_entries"]
    _assert("R01", "exception_before_call_capture_cleanup", before_exception["raised"] == before_expected_exception and before_diagnostics.get("failure_retained") is True and before_diagnostics.get("service_call_entries") == before_expected_entries and before_cleanup_retained and before_exception["claim_raised"] == before_expected_exception and before_claim_diagnostics.get("failure_retained") is True and before_claim_diagnostics.get("service_call_entries") == before_expected_entries and before_claim_cleanup_retained, "pre-call exception lost its failure or truthful partial capture/cleanup state in a natural or claim probe", before_exception)

    after_exception = exception_probe("after-call")
    after_diagnostics = after_exception["diagnostics"]
    after_cleanup = after_diagnostics.get("cleanup_result")
    after_claim_diagnostics = after_exception["claim_diagnostics"]
    after_cleanup_retained = (after_diagnostics.get("resources_clear") is True
                              and after_diagnostics.get("capture_completed") is True
                              and after_diagnostics.get("finalization_errors") == []
                              and type(after_cleanup) is dict and after_cleanup.get("exit_confirmed") is True)
    after_claim_cleanup_retained = (after_claim_diagnostics.get("resources_clear") is True
                                    and after_claim_diagnostics.get("capture_completed") is True
                                    and after_claim_diagnostics.get("finalization_errors") == []
                                    and after_claim_diagnostics.get("pending_tasks_remaining") == 0
                                    and type(after_claim_diagnostics.get("cleanup_result")) is dict)
    after_expected_exception = {"type": "RuntimeError", "message": "controlled natural-sequence failure after fake service call"}
    after_minimum_entries = context["fixture_data"]["stop"]["recovery_r1"]["exception_capture"]["after_call_minimum_service_entries"]
    _assert("R01", "exception_after_call_capture_cleanup", after_exception["raised"] == after_expected_exception and after_diagnostics.get("failure_retained") is True and after_diagnostics.get("service_call_entries", 0) >= after_minimum_entries and after_diagnostics.get("cleanup_attempted") is True and after_diagnostics.get("pending_tasks_remaining") == 0 and after_cleanup_retained and after_exception["claim_raised"] == after_expected_exception and after_claim_diagnostics.get("failure_retained") is True and after_claim_diagnostics.get("service_call_entries", 0) >= after_minimum_entries and after_claim_cleanup_retained, "post-call exception did not preserve failure, partial ledger and confirmed cleanup in a natural or claim probe", after_exception)

    service_gdb = run["gdb_module"]
    recovery = context["fixture_data"]["stop"]["recovery_r1"]
    display_records = {
        "token_and_prompt": [service_gdb._parse_mi_record(b"1^done\n", 1), service_gdb._parse_mi_record(b"(gdb)\n", 2)],
        "tokenized_error": [service_gdb._parse_mi_record(b'1^error,msg="bad command"\n', 3)],
        "console_stream": [service_gdb._parse_mi_record(b'~"hello\\n"\n', 4)],
        "stop": [service_gdb._parse_mi_record(b'*stopped,reason="signal-received"\n', 5)],
    }
    display_outputs = {name: service_gdb._format_observation_output(records) for name, records in display_records.items()}
    display_expected = {
        "token_and_prompt": recovery["display"]["token_and_prompt"],
        "tokenized_error": recovery["display"]["tokenized_error"],
        "console_stream": recovery["display"]["console_stream"],
        "stop": recovery["display"]["stop"],
    }
    _assert("R01", "token_and_prompt_text", display_outputs["token_and_prompt"] == display_expected["token_and_prompt"], "actual service token/prompt formatting differs from exact independent text", display_outputs["token_and_prompt"])
    _assert("R01", "tokenized_error_text", display_outputs["tokenized_error"] == display_expected["tokenized_error"], "actual service tokenized error formatting differs from exact independent text", display_outputs["tokenized_error"])
    _assert("R01", "console_stream_text", display_outputs["console_stream"] == display_expected["console_stream"], "actual service console stream formatting differs from exact independent text", display_outputs["console_stream"])
    _assert("R01", "stop_text", display_outputs["stop"] == display_expected["stop"], "actual service stop formatting differs from exact independent text", display_outputs["stop"])
    subcontrols = _passed_controls("R01")
    return _case("R01", {"subcontrols": subcontrols, "start": start, "claim": claim, "attach": attach, "continue": continuation, "cleanup": cleanup, "actual_method_ledger": run["actual_method_ledger"], "exception_controls": {"before_call": before_exception, "after_call": after_exception}, "service_display": {"expected": display_expected, "observed": display_outputs}, "factory_calls": len(world.factory_calls), "fixed_fake_factory_calls": run["deny_hooks"].allowed_factory_calls, "real_factory_calls": world.real_calls, "real_gdb_calls": world.real_calls, "reader_metrics": reader_metrics, "raw_record_count": session._observation_record_count if session else None})


async def _claim_probe_async(
    context: dict[str, Any], *, baseline_control: str | None = None, preclaim: str | None = None,
    action_after_claim: bool = False, transaction_fault: str | None = None,
    action_sequence: tuple[dict[str, Any], ...] = (), action_mode: dict[str, Any] | None = None,
    action_events: dict[str, list[str]] | None = None, breakpoint_body: str | None = None,
    state_body_override: dict[str, str] | None = None,
    inject_state_change_on: set[str] | None = None,
    response_delay_by_kind: dict[str, float] | None = None,
    drain_delay_by_kind: dict[str, float] | None = None,
    transaction_fault_by_kind: dict[str, str] | None = None,
    action_event_delay_by_kind: dict[str, float] | None = None,
    flood_baseline_records: int = 0, flood_baseline_bytes: int = 0,
    block_reader_after_claim: bool = False,
    claim_pending_race: bool = False, repeat_claim: bool = False,
    postclaim_legacy_probes: bool = False, stop_budget_ms: int = 7000,
    repeat_stop: bool = False, join_blocked_reader_after_stop: bool = False,
    held_observation_lock: str | None = None,
    stop_during_pending_command: bool = False,
    failure_injection: str | None = None, diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    helper = _load_historical_helpers(context)
    natural = context["fixture_data"]["natural"]
    stop = context["fixture_data"]["stop"]
    world = _ProtocolWorld(helper, natural, stop)
    world.transaction_fault = transaction_fault
    world.action_mode = dict(action_mode or {})
    world.action_events = dict(action_events or {})
    world.breakpoint_body = breakpoint_body
    world.state_body_override = dict(state_body_override or {})
    world.inject_state_change_on = set(inject_state_change_on or ())
    world.response_delay_by_kind = dict(response_delay_by_kind or {})
    world.drain_delay_by_kind = dict(drain_delay_by_kind or {})
    if claim_pending_race:
        world.drain_delay_by_kind.setdefault("baseline", 0.05)
    world.transaction_fault_by_kind = dict(transaction_fault_by_kind or {})
    world.action_event_delay_by_kind = dict(action_event_delay_by_kind or {})
    world.flood_baseline_records = flood_baseline_records
    world.flood_baseline_bytes = flood_baseline_bytes
    if baseline_control is not None:
        _configure_baseline_control(world, context["fixture_data"]["baseline"], baseline_control)
    hooks = helper.DenyHooks()
    hooks.install(world.factory)
    gdb: ModuleType | None = None
    server: ModuleType | None = None
    original_uuid_module: Any = None
    ledger = _ActualLedger()
    manager: Any = None
    started: Any = None
    sid: str | None = None
    claim: Any = None
    action: Any = None
    actions: list[Any] = []
    action_write_deltas: list[int] = []
    legacy_output: Any = None
    preclaim_error: str | None = None
    pending_race: dict[str, Any] = {}
    postclaim_legacy: dict[str, Any] = {}
    replay_claim: Any = None
    repeated_cleanup: Any = None
    later_reader_join = False
    registry_retained_after_first_stop = False
    reader_task_done_at_first_stop: bool | None = None
    reader_eof_at_first_stop: bool | None = None
    stop_during_action_result: Any = None
    cleanup: Any = None
    process = None
    session = None
    start_attempted = False
    primary_exception: BaseException | None = None
    finalization_errors: list[str] = []
    capture_completed = False
    try:
        # Candidate source import is inside the process/network denial scope.
        gdb, server = _load_actual_service()
        original_uuid_module = gdb.uuid
        fixed_values = iter((natural["startup_uuid_hex"], natural["nonce_uuid_hex"]))
        gdb.uuid = type("_FixedUuidModule", (), {"uuid4": staticmethod(lambda: _FixedUUID(next(fixed_values)))})
        for owner, names in (
            (gdb.GdbManager, ("start_owned_session", "claim_observed_session", "stop_session_by_owner", "stop_observed_session")),
            (gdb.GdbSession, ("_baseline_until", "_observation_request_until", "stop_observed_until")),
            (server, ("start_owned_session", "claim_observed_session", "stop_session_by_owner", "stop_observed_session", "exec_command")),
        ):
            for name in names:
                if hasattr(owner, name):
                    ledger.wrap_async(owner, name, getattr(owner, "__name__", "server") + "." + name)
        manager = gdb.GdbManager()
        server.manager = manager
        world.manager = manager
        if failure_injection == "before-call":
            raise RuntimeError("controlled natural-sequence failure before service call")
        start_attempted = True
        started = await server.start_owned_session(natural["owner_id"], budget_ms=8000)
        sid = started.get("session_id") if type(started) is dict else None
        lease = manager._owned_leases.get(natural["owner_id"])
        session = lease.session if lease is not None else None
        process = session.process if session is not None else None
        if process is not None:
            process.session = session
        if failure_injection == "after-call":
            raise RuntimeError("controlled natural-sequence failure after fake service call")
        if preclaim == "send":
            legacy_output = await server.exec_command(sid, "info version", timeout=0.5)
        elif preclaim == "interrupt":
            manager.get(sid).interrupt()
        elif preclaim == "stale-stop":
            process.stdout.feed(stop["attach"]["raw_event"].encode("ascii") + b"\n")
        elif preclaim == "buffered-output":
            process.stdout.feed(b'~"buffered-before-claim\\n"\n')
        if claim_pending_race:
            claim_task = asyncio.create_task(server.claim_observed_session(natural["owner_id"], sid, budget_ms=3000))
            await asyncio.sleep(0)
            pending_race["state"] = session._observation_state if session is not None else None
            pending_race["legacy_writes_before"] = len(process.stdin.writes) if process is not None else None
            try:
                pending_race["send"] = await server.exec_command(sid, "info version", timeout=0.5)
            except BaseException as exc:
                pending_race["send_error"] = type(exc).__name__ + ":" + str(exc)
            try:
                manager.get(sid).interrupt()
                pending_race["interrupt_error"] = None
            except BaseException as exc:
                pending_race["interrupt_error"] = type(exc).__name__ + ":" + str(exc)
            pending_race["legacy_writes_after"] = len(process.stdin.writes) if process is not None else None
            try:
                claim = await claim_task
            except BaseException as exc:
                preclaim_error = type(exc).__name__ + ":" + str(exc)
        else:
            try:
                claim = await server.claim_observed_session(natural["owner_id"], sid, budget_ms=3000)
            except BaseException as exc:
                preclaim_error = type(exc).__name__ + ":" + str(exc)
        if repeat_claim and type(claim) is dict and claim.get("state") == "CLAIMED":
            writes_before_replay = len(process.stdin.writes) if process is not None else 0
            replay_claim = await server.claim_observed_session(natural["owner_id"], sid, budget_ms=3000)
            pending_race["writes_before_replay"] = writes_before_replay
            pending_race["writes_after_replay"] = len(process.stdin.writes) if process is not None else None
            detached: dict[str, Any] = {"first_claim_snapshot": False, "replay_snapshot": False, "journal_unchanged": False, "retained_journal_unchanged": False}
            if (type(replay_claim) is dict and type(claim.get("baseline")) is dict
                    and type(claim.get("call_ledger")) is list
                    and type(replay_claim.get("baseline")) is dict
                    and type(replay_claim.get("call_ledger")) is list):
                original_baseline = json.loads(json.dumps(claim["baseline"], sort_keys=True, separators=(",", ":")))
                original_journal = json.loads(json.dumps(claim["call_ledger"], sort_keys=True, separators=(",", ":")))
                original_retained_journal = json.loads(json.dumps(session._observation_call_ledger, sort_keys=True, separators=(",", ":")))
                original_replay_baseline = json.loads(json.dumps(replay_claim.get("baseline"), sort_keys=True, separators=(",", ":")))
                original_replay_journal = json.loads(json.dumps(replay_claim.get("call_ledger"), sort_keys=True, separators=(",", ":")))
                claim["baseline"]["owner_id"] = "mutated-first-response"
                if claim["call_ledger"]:
                    claim["call_ledger"][0]["call_id"] = "mutated-first-journal"
                detached["first_claim_snapshot"] = claim["baseline"] != original_baseline and claim["call_ledger"] != original_journal
                detached["replay_snapshot"] = replay_claim.get("baseline") == original_replay_baseline and replay_claim.get("call_ledger") == original_replay_journal
                replay_claim["baseline"]["owner_id"] = "mutated-replay-response"
                if replay_claim["call_ledger"]:
                    replay_claim["call_ledger"][0]["call_id"] = "mutated-replay-journal"
                third_claim = await server.claim_observed_session(natural["owner_id"], sid, budget_ms=3000)
                detached["journal_unchanged"] = (
                    type(third_claim) is dict
                    and third_claim.get("baseline") == original_baseline
                    and third_claim.get("call_ledger") == original_journal
                    and third_claim.get("generation") == claim.get("generation")
                    and (len(process.stdin.writes) if process is not None else None) == writes_before_replay
                )
                detached["retained_journal_unchanged"] = session._observation_call_ledger == original_retained_journal
            pending_race["detached_claim_proof"] = detached
        if postclaim_legacy_probes and type(claim) is dict and claim.get("state") == "CLAIMED":
            writes_before_legacy = len(process.stdin.writes) if process is not None else 0
            try:
                postclaim_legacy["send"] = await server.exec_command(sid, "info version", timeout=0.5)
            except BaseException as exc:
                postclaim_legacy["send_error"] = type(exc).__name__ + ":" + str(exc)
            try:
                manager.get(sid).interrupt()
                postclaim_legacy["interrupt_error"] = None
            except BaseException as exc:
                postclaim_legacy["interrupt_error"] = type(exc).__name__ + ":" + str(exc)
            postclaim_legacy["writes_before"] = writes_before_legacy
            postclaim_legacy["writes_after"] = len(process.stdin.writes) if process is not None else None
        if block_reader_after_claim and process is not None and type(claim) is dict and claim.get("state") == "CLAIMED":
            process.stdout._block_next_observation_read = True
            process.stdout._reader.feed(b"(gdb)\n")
            await asyncio.wait_for(process.stdout._reader_block_entered.wait(), timeout=1.0)
        planned_actions = list(action_sequence)
        if action_after_claim and not planned_actions:
            planned_actions = [{"kind": "attach", "command_id": "attach-001", "command": natural["attach_command"], "stop_expectation": "signal", "budget_ms": 1000}]
        if type(claim) is dict and claim.get("state") == "CLAIMED":
            held_lock = None
            if held_observation_lock == "operation":
                held_lock = session._observation_operation_lock
            elif held_observation_lock == "transaction":
                held_lock = session._observation_transaction_lock
            if held_lock is not None:
                await held_lock.acquire()
            try:
                for step_index, step in enumerate(planned_actions):
                    write_count_before = len(process.stdin.writes) if process is not None else 0
                    kind = step.get("kind")
                    command = step.get("command", natural["attach_command"] if kind == "attach" else "continue")
                    expectation = step.get("stop_expectation", "signal" if kind == "attach" else "breakpoint")
                    owner = step.get("owner_id", natural["owner_id"])
                    operation = server.exec_owned_session(
                        owner, sid, step["command_id"], command,
                        budget_ms=step.get("budget_ms", 1000),
                        stop_expectation=expectation,
                        expected_breakpoint=step.get("expected_breakpoint", natural["expected_breakpoint"] if expectation == "breakpoint" else None),
                    )
                    if stop_during_pending_command and step_index == len(planned_actions) - 1:
                        action_task = asyncio.create_task(operation)
                        for _ in range(1000):
                            active = session._observation_active_transaction
                            if type(active) is dict and active.get("call_id") == step["command_id"]:
                                break
                            await asyncio.sleep(0)
                        else:
                            raise QualificationFailure("R15", "pending_command_invalidated", "owned command never reached its actual MI action transaction", category="TIMEOUT")
                        stop_during_action_result = await server.stop_observed_session(natural["owner_id"], sid, budget_ms=1000)
                        try:
                            result = await asyncio.wait_for(action_task, timeout=1.0)
                        except BaseException as exc:
                            result = {"raised": type(exc).__name__, "message": str(exc)}
                    else:
                        try:
                            result = await operation
                        except BaseException as exc:
                            if not step.get("expect_exception", False):
                                raise
                            result = {"raised": type(exc).__name__, "message": str(exc)}
                    actions.append(result)
                    action_write_deltas.append((len(process.stdin.writes) if process is not None else 0) - write_count_before)
            finally:
                if held_lock is not None:
                    held_lock.release()
            action = actions[-1] if actions else None
        if stop_during_pending_command:
            cleanup = stop_during_action_result
            registry_retained_after_first_stop = manager is not None and sid in manager._sessions
            reader_task_done_at_first_stop = session._observation_task.done() if session is not None and session._observation_task is not None else None
            reader_eof_at_first_stop = session._observation_eof if session is not None else None
            if repeat_stop:
                repeated_cleanup = await server.stop_observed_session(natural["owner_id"], sid, budget_ms=stop_budget_ms)
        elif session is not None and session._observation_task is not None:
            cleanup = await server.stop_observed_session(natural["owner_id"], sid, budget_ms=stop_budget_ms)
            registry_retained_after_first_stop = manager is not None and sid in manager._sessions
            reader_task_done_at_first_stop = session._observation_task.done()
            reader_eof_at_first_stop = session._observation_eof
            if repeat_stop:
                repeated_cleanup = await server.stop_observed_session(natural["owner_id"], sid, budget_ms=stop_budget_ms)
            if join_blocked_reader_after_stop and process is not None:
                process.stdout.release_blocked_read()
                try:
                    await asyncio.wait_for(asyncio.shield(session._observation_task), timeout=1.0)
                    later_reader_join = session._observation_task.done() and session._observation_eof
                except asyncio.TimeoutError:
                    later_reader_join = False
        else:
            cleanup = await server.stop_session_by_owner(natural["owner_id"], budget_ms=7000)
    except BaseException as exc:
        primary_exception = exc
        raise
    finally:
        try:
            lease = manager._owned_leases.get(natural["owner_id"]) if manager is not None else None
            if lease is not None:
                if session is None:
                    session = lease.session
                if process is None and session is not None:
                    process = session.process
                if sid is None and session is not None:
                    sid = session.id
            if cleanup is None and server is not None and manager is not None and start_attempted:
                cleanup = await server.stop_session_by_owner(natural["owner_id"], budget_ms=7000)
        except BaseException as exc:
            finalization_errors.append("owned-session cleanup: " + type(exc).__name__ + ": " + str(exc))
        try:
            if process is not None and process.returncode is None:
                process.finish(0)
        except BaseException as exc:
            finalization_errors.append("process finish: " + type(exc).__name__ + ": " + str(exc))
        try:
            if world.pending_response_tasks:
                _done, pending = await asyncio.wait(world.pending_response_tasks, timeout=1.0)
                for task in pending:
                    task.cancel()
                if pending:
                    await asyncio.gather(*pending, return_exceptions=True)
        except BaseException as exc:
            finalization_errors.append("pending-task cleanup: " + type(exc).__name__ + ": " + str(exc))
        try:
            hooks.restore()
        except BaseException as exc:
            finalization_errors.append("hook restore: " + type(exc).__name__ + ": " + str(exc))
        try:
            if gdb is not None and original_uuid_module is not None:
                gdb.uuid = original_uuid_module
        except BaseException as exc:
            finalization_errors.append("UUID restore: " + type(exc).__name__ + ": " + str(exc))
        try:
            _capture_run(world, ledger.rows, session, hooks)
            capture_completed = True
        except BaseException as exc:
            finalization_errors.append("partial evidence capture: " + type(exc).__name__ + ": " + str(exc))
        if diagnostics is not None:
            owner_lease = manager._owned_leases.get(natural["owner_id"]) if manager is not None else None
            pending_count = sum(not task.done() for task in world.pending_response_tasks)
            diagnostics.update({
                "exception_type": type(primary_exception).__name__ if primary_exception is not None else None,
                "exception_message": str(primary_exception) if primary_exception is not None else None,
                "service_ledger_entries": len(ledger.rows),
                "service_call_entries": sum(item.get("event") == "enter" for item in ledger.rows),
                "cleanup_result": cleanup,
                "pending_tasks_remaining": pending_count,
                "resources_clear": (process is None or process.returncode is not None)
                    and pending_count == 0
                    and (owner_lease is None or owner_lease.state in ("EXITED", "CANCELLED_BEFORE_START")),
                "failure_retained": primary_exception is not None and str(primary_exception).startswith("controlled natural-sequence failure"),
                "capture_completed": capture_completed,
                "finalization_errors": list(finalization_errors),
            })
        if primary_exception is None and finalization_errors:
            raise RuntimeError("claim-probe finalization failed: " + "; ".join(finalization_errors))
    return {
        "start": started, "claim": claim, "action": action, "preclaim_error": preclaim_error,
        "actions": actions,
        "action_write_deltas": action_write_deltas,
        "legacy_output": legacy_output, "cleanup": cleanup, "session": session,
        "process": process, "world": world, "hooks": hooks, "ledger": ledger.rows,
        "pending_race": pending_race, "postclaim_legacy": postclaim_legacy,
        "replay_claim": replay_claim, "repeated_cleanup": repeated_cleanup,
        "later_reader_join": later_reader_join,
        "registry_retained_after_first_stop": registry_retained_after_first_stop,
        "reader_task_done_at_first_stop": reader_task_done_at_first_stop,
        "reader_eof_at_first_stop": reader_eof_at_first_stop,
        "stop_during_action": stop_during_action_result,
        "gdb_module": gdb,
        "server_module": server,
    }


def _configure_baseline_control(world: _ProtocolWorld, fixture: dict[str, Any], control_id: str) -> None:
    payload = dict(world.baseline_payload)
    if control_id == "CONNECTION_WITHOUT_THREADS":
        payload["connection_count"] = 1
    elif control_id == "COUNT_BOOLEAN":
        payload["connection_count"] = False
    elif control_id == "COUNT_STRING":
        payload["connection_count"] = "0"
    elif control_id == "COUNT_NULL":
        payload["connection_count"] = None
    elif control_id == "COUNT_MISSING":
        payload.pop("connection_count")
    elif control_id == "STALE_NONCE":
        payload["nonce"] = "stale-baseline-nonce"
    elif control_id == "WRONG_OWNER":
        payload["owner_id"] = "other-owner"
    elif control_id == "WRONG_SESSION":
        payload["session_id"] = "other-session"
    elif control_id == "WRONG_GENERATION":
        payload["generation"] = 2
    elif control_id == "WRONG_STREAM":
        world.baseline_marker = "@"
    elif control_id == "DUPLICATE_PAYLOAD":
        world.baseline_duplicates = 2
    elif control_id == "MALFORMED_JSON":
        world.baseline_raw_payload = "{bad"
    elif control_id == "TRUNCATED_JSON":
        world.baseline_raw_payload = '{"schema":'
    elif control_id == "PYTHON_UNAVAILABLE":
        world.baseline_result_class = "error"
        world.baseline_error_message = "Python support is unavailable"
    elif control_id == "API_UNAVAILABLE":
        world.baseline_result_class = "error"
        world.baseline_error_message = "AttributeError: connections"
    elif control_id == "MI_ERROR":
        world.baseline_result_class = "error"
        world.baseline_error_message = "controlled MI error"
    elif control_id == "WRONG_RESULT_TOKEN":
        world.baseline_result_token = "902"
    elif control_id == "INVALIDATED_GENERATION":
        world.inject_state_change = True
    elif control_id != "BASELINE_ZERO":
        raise ValueError("unknown independent baseline control: " + control_id)
    if control_id not in ("MALFORMED_JSON", "TRUNCATED_JSON"):
        world.baseline_payload = payload


def _load_historical_candidate(context: dict[str, Any]) -> tuple[ModuleType, ModuleType]:
    root = _frozen_path(context["freeze"]["qualified_service_root"])
    modules: list[ModuleType] = []
    for module_name, relative in (("gdb", "candidate/gdb.py"), ("server", "candidate/server.py")):
        path = root / relative
        if _sha256(path) != context["qualified_sha256"][relative]:
            raise ValueError("historical missing-capability source changed: " + relative)
        loader = importlib.machinery.SourceFileLoader(module_name, str(path))
        spec = importlib.util.spec_from_loader(module_name, loader)
        if spec is None or spec.loader is None:
            raise ImportError("cannot load pinned historical candidate source")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        loader.exec_module(module)
        modules.append(module)
    return modules[0], modules[1]


def _run_r02(context: dict[str, Any]) -> dict[str, Any]:
    helper = _load_historical_helpers(context)
    hooks = helper.DenyHooks()
    async def fixed_factory(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("historical capability source must not request a real child")
    hooks.install(fixed_factory)
    try:
        candidate_gdb, candidate_server = _load_historical_candidate(context)
    finally:
        hooks.restore()
    manager = candidate_gdb.GdbManager
    observed = {
        "claim": hasattr(manager, "claim_observed_session") and hasattr(candidate_server, "claim_observed_session"),
        "exec": hasattr(manager, "exec_owned_session") and hasattr(candidate_server, "exec_owned_session"),
        "stop": hasattr(manager, "stop_observed_session") and hasattr(candidate_server, "stop_observed_session"),
    }
    _assert("R02", "historical_source_pin", all(_is_digest(context["qualified_sha256"].get(path)) for path in ("candidate/gdb.py", "candidate/server.py")), "historical f02 pair lacks exact freeze pin", observed)
    _assert("R02", "missing_claim_api", observed["claim"] is False, "historical candidate unexpectedly exposes the approved claim capability", observed)
    _assert("R02", "missing_exec_api", observed["exec"] is False, "historical candidate unexpectedly exposes the approved execution capability", observed)
    _assert("R02", "missing_stop_api", observed["stop"] is False, "historical candidate unexpectedly exposes observed cleanup", observed)
    _assert("R02", "not_setup_failure", candidate_gdb.GdbManager is not None and candidate_server is not None, "historical capability negative did not load its pinned source pair")
    return _case("R02", {"subcontrols": _passed_controls("R02"), "historical_hashes": {path: context["qualified_sha256"][path] for path in ("candidate/gdb.py", "candidate/server.py")}, "capabilities": observed, "denial_counts": hooks.counts, "real_factory_calls": hooks.allowed_factory_calls})


def _snapshot_modules(names: tuple[str, ...]) -> dict[str, tuple[bool, Any]]:
    return {name: (name in sys.modules, sys.modules.get(name)) for name in names}


def _module_snapshot_matches(modules: Any, snapshot: dict[str, tuple[bool, Any]]) -> bool:
    if not isinstance(modules, dict):
        return False
    for name, (was_present, original) in snapshot.items():
        if (name in modules) is not was_present:
            return False
        if was_present and modules.get(name) is not original:
            return False
    return True


def _restore_modules(snapshot: dict[str, tuple[bool, Any]]) -> None:
    for name, (was_present, original) in snapshot.items():
        if was_present:
            sys.modules[name] = original
        else:
            sys.modules.pop(name, None)


def _run_r03(context: dict[str, Any]) -> dict[str, Any]:
    fixture = context["fixture_data"]["producer"]
    original_modules = _snapshot_modules(("gdb", "json", "server"))
    helper = _load_historical_helpers(context)
    hooks = helper.DenyHooks()
    async def denied_factory(*_args: Any, **_kwargs: Any) -> Any:
        raise helper.DeniedOperation("producer fixture forbids process creation")
    hooks.install(denied_factory)
    runs: list[dict[str, Any]] = []
    producer_imports = {"fake_gdb": 0, "real_gdb": 0}
    generated = b""
    candidate_gdb: ModuleType | None = None
    try:
        candidate_gdb, _candidate_server = _load_actual_service()
        producer_args = (fixture["owner_id"], fixture["session_id"], fixture["generation"], fixture["nonce"])
        _PHASE_LEDGER["service_calls"].append({
            "case_id": "R03", "method": "gdb.build_connection_baseline_producer", "event": "enter",
            "argv": _safe_fixture_value(producer_args), "kwargs": {},
        })
        try:
            generated = candidate_gdb.build_connection_baseline_producer(*producer_args)
        except BaseException as exc:
            _PHASE_LEDGER["service_calls"].append({
                "case_id": "R03", "method": "gdb.build_connection_baseline_producer", "event": "raise",
                "exception_type": type(exc).__name__, "error": str(exc)[:2048],
            })
            raise
        frozen_source = fixture["source_ascii"].encode("ascii")
        generated_sha256 = hashlib.sha256(generated).hexdigest() if type(generated) is bytes else None
        generated_length = len(generated) if type(generated) is bytes else None
        _PHASE_LEDGER["service_calls"].append({
            "case_id": "R03", "method": "gdb.build_connection_baseline_producer", "event": "return",
            "result_type": type(generated).__name__, "result_length_bytes": generated_length,
            "result_sha256": generated_sha256,
        })
        literal_matches = (
            type(generated) is bytes
            and generated == frozen_source
            and generated_sha256 == PRODUCER_SHA256
            and hashlib.sha256(frozen_source).hexdigest() == PRODUCER_SHA256
            and fixture["source_sha256"] == PRODUCER_SHA256
        )
        _assert("R03", "literal_hash", literal_matches, "actual copied-service producer bytes differ from the independent literal pin", {
            "result_type": type(generated).__name__, "result_length_bytes": generated_length,
            "result_sha256": generated_sha256, "fixture_sha256": fixture["source_sha256"],
        })
        for count, expected_stdout in ((0, fixture["expected_stdout_zero"]), (1, fixture["expected_stdout_one"])):
            fake_gdb = ModuleType("gdb")
            state = {"calls": 0}
            def connections(count: int = count, state: dict[str, int] = state) -> list[object]:
                state["calls"] += 1
                return [object() for _ in range(count)]
            fake_gdb.connections = connections
            sys.modules["gdb"] = fake_gdb
            captured: list[str] = []
            def restricted_import(name: str, globals: Any = None, locals: Any = None, fromlist: Any = (), level: int = 0) -> Any:
                del globals, locals, fromlist, level
                if name == "gdb":
                    producer_imports["real_gdb" if fake_gdb is candidate_gdb else "fake_gdb"] += 1
                    return fake_gdb
                if name == "json":
                    return json
                raise ImportError("producer import outside exact fixture allowlist")
            def captured_print(value: Any) -> None:
                if type(value) is not str:
                    raise TypeError("producer print payload must be one string")
                captured.append(value + "\n")
            safe_builtins = {"__import__": restricted_import, "len": len, "print": captured_print}
            exec(compile(generated.decode("ascii"), "<actual-service-sro-producer>", "exec"), {"__builtins__": safe_builtins}, {})
            runs.append({"connections": count, "calls": state["calls"], "stdout": "".join(captured), "expected": expected_stdout})
            sys.modules["gdb"] = candidate_gdb
    finally:
        try:
            hooks.restore()
        finally:
            _restore_modules(original_modules)
    _assert("R03", "empty_connections_once", runs[0]["calls"] == 1 and runs[0]["connections"] == 0, "empty fake connections fixture did not call once", runs[0])
    _assert("R03", "one_connection_once", runs[1]["calls"] == 1 and runs[1]["connections"] == 1, "one-connection fake fixture did not call once", runs[1])
    _assert("R03", "exact_zero_stdout", runs[0]["stdout"] == runs[0]["expected"], "producer zero stdout differs from independent expected literal", runs[0])
    _assert("R03", "exact_one_stdout", runs[1]["stdout"] == runs[1]["expected"], "producer one stdout differs from independent expected literal", runs[1])
    restored = _module_snapshot_matches(sys.modules, original_modules)
    _assert("R03", "module_restored", restored, "original gdb/json/server module presence and identities were not restored", {name: (present, id(module) if present else None) for name, (present, module) in original_modules.items()})
    replacement_modules = dict(sys.modules)
    replacement_modules["json"] = ModuleType("json")
    replacement_rejected = not _module_snapshot_matches(replacement_modules, original_modules)
    removed_modules = dict(sys.modules)
    removed_modules.pop("json", None)
    removal_rejected = not _module_snapshot_matches(removed_modules, original_modules)
    denied_counts = dict(hooks.counts)
    process_attempts = sum(count for name, count in denied_counts.items() if name.startswith(("subprocess.", "asyncio.create_subprocess_shell", "os.")))
    network_attempts = sum(count for name, count in denied_counts.items() if name.startswith("socket."))
    _PHASE_LEDGER["real_factory_calls"] += hooks.allowed_factory_calls + process_attempts
    _PHASE_LEDGER["real_gdb_calls"] += producer_imports["real_gdb"] + process_attempts
    _PHASE_LEDGER["real_network_calls"] += network_attempts
    _assert("R03", "no_io", set(("__import__", "len", "print")) == set(safe_builtins) and type(fake_gdb).__name__ == "module" and hooks.allowed_factory_calls == 0 and producer_imports == {"fake_gdb": 2, "real_gdb": 0} and not denied_counts, "producer sandbox used an unexpected built-in, factory or denied operation", {"builtins": sorted(safe_builtins), "factory_calls": hooks.allowed_factory_calls, "producer_imports": producer_imports, "denied_counts": denied_counts})
    _assert("R03", "module_replacement_rejected", replacement_rejected, "module binding oracle admitted a replacement module", {"positive": restored, "negative": _module_snapshot_matches(replacement_modules, original_modules)})
    _assert("R03", "module_removal_rejected", removal_rejected, "module binding oracle admitted a removed module", {"positive": restored, "negative": _module_snapshot_matches(removed_modules, original_modules)})
    return _case("R03", {"subcontrols": _passed_controls("R03"), "source_sha256": generated_sha256, "runs": runs, "real_gdb_calls": producer_imports["real_gdb"], "real_subprocess_calls": process_attempts, "real_network_calls": network_attempts, "denied_counts": denied_counts})


def _baseline_disposition(claim: Any, control_id: str) -> str:
    if type(claim) is not dict:
        return "UNKNOWN_BASELINE"
    if claim.get("state") == "CLAIMED" and claim.get("baseline_validated") is True:
        payload = claim.get("baseline")
        if type(payload) is dict and type(payload.get("connection_count")) is int and payload.get("connection_count") == 0:
            return "ACCEPT_BASELINE"
    error = claim.get("error_code")
    if error == "BASELINE_CONNECTIONS_PRESENT":
        return "REJECT_BASELINE"
    if error in ("BASELINE_CONNECTION_COUNT_NOT_INTEGER", "BASELINE_SCHEMA_FIELDS_INVALID", "BASELINE_JSON_INVALID"):
        return "REJECT_SCHEMA"
    if error == "BASELINE_IDENTITY_MISMATCH":
        return "REJECT_BINDING"
    if error == "BASELINE_STREAM_MISSING_DUPLICATE_OR_WRONG_STREAM":
        if control_id == "DUPLICATE_PAYLOAD":
            calls = claim.get("call_ledger", [])
            records = [record for call in calls if type(call) is dict for record in call.get("records", []) if type(record) is dict and record.get("marker") in ("~", "@", "&") and isinstance(record.get("stream"), str) and any(line.startswith("LB_SRO_BASELINE:") for line in record["stream"].splitlines())]
            if len(records) == 2:
                return "REJECT_AMBIGUOUS"
        return "REJECT_OR_MISSING_PAYLOAD"
    if error == "MI_RESULT_TOKEN_MISMATCH":
        return "REJECT_BINDING"
    if error in ("BASELINE_MI_RESULT_NOT_DONE", "BASELINE_STATE_GENERATION_CHANGED", "BASELINE_STATE_OR_DEADLINE_INVALID"):
        return "UNKNOWN_BASELINE" if error == "BASELINE_MI_RESULT_NOT_DONE" else "REJECT_INVALIDATED"
    return "UNKNOWN_BASELINE"


async def _run_r04_async(context: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    controls = context["fixture_data"]["baseline"]["controls"]
    results: list[dict[str, Any]] = []
    ledgers: list[dict[str, Any]] = []
    for item in controls:
        result = await _claim_probe_async(context, baseline_control=item["id"])
        observed = _baseline_disposition(result["claim"], item["id"])
        expected = item["expected"]
        results.append({"id": item["id"], "expected": expected, "observed": observed, "claim": result["claim"]})
        ledgers.append({"id": item["id"], "actual_method_ledger": result["ledger"], "factory_calls": len(result["world"].factory_calls), "observer_records": result["session"]._observation_record_count if result["session"] is not None else 0})
    return results, ledgers


def _run_r04(context: dict[str, Any]) -> dict[str, Any]:
    results, ledgers = asyncio.run(_run_r04_async(context))
    controls = context["fixture_data"]["baseline"]["controls"]
    subcontrol_by_fixture = {
        "BASELINE_ZERO": "baseline-control-zero", "CONNECTION_WITHOUT_THREADS": "baseline-control-connection",
        "COUNT_BOOLEAN": "baseline-control-bool", "COUNT_STRING": "baseline-control-string", "COUNT_NULL": "baseline-control-null",
        "COUNT_MISSING": "baseline-control-missing", "STALE_NONCE": "baseline-control-nonce", "WRONG_OWNER": "baseline-control-owner",
        "WRONG_SESSION": "baseline-control-session", "WRONG_GENERATION": "baseline-control-generation", "WRONG_STREAM": "baseline-control-stream",
        "DUPLICATE_PAYLOAD": "baseline-control-duplicate", "MALFORMED_JSON": "baseline-control-malformed", "TRUNCATED_JSON": "baseline-control-truncated",
        "PYTHON_UNAVAILABLE": "baseline-control-python", "API_UNAVAILABLE": "baseline-control-api", "MI_ERROR": "baseline-control-mi-error",
        "WRONG_RESULT_TOKEN": "baseline-control-token", "INVALIDATED_GENERATION": "baseline-control-invalidated",
    }
    by_id = {item["id"]: item for item in results}
    for item in controls:
        observed = by_id[item["id"]]["observed"]
        expected = item["expected"]
        condition = observed == expected
        if item["id"] == "CONNECTION_WITHOUT_THREADS":
            condition = condition and by_id[item["id"]]["claim"].get("baseline_validated") is False and by_id[item["id"]]["claim"].get("error_code") == "BASELINE_CONNECTIONS_PRESENT"
        _assert("R04", subcontrol_by_fixture[item["id"]], condition, "actual claim baseline decoder did not match the independent control disposition", by_id[item["id"]])
    return _case("R04", {"subcontrols": _passed_controls("R04"), "controls": results, "actual_method_ledgers": ledgers, "strict_zero_only": by_id["BASELINE_ZERO"]["observed"] == "ACCEPT_BASELINE"})


def _run_r05(context: dict[str, Any]) -> dict[str, Any]:
    send = asyncio.run(_claim_probe_async(context, preclaim="send"))
    interrupt = asyncio.run(_claim_probe_async(context, preclaim="interrupt"))
    stale = asyncio.run(_claim_probe_async(context, preclaim="stale-stop"))
    buffered = asyncio.run(_claim_probe_async(context, preclaim="buffered-output", action_after_claim=True))
    _assert("R05", "preclaim_user_send", "LEGACY_ACTIVITY_PREVENTS_FRESH_CLAIM" in (send["preclaim_error"] or ""), "preclaim legacy send was admitted into the observer generation", send)
    _assert("R05", "preclaim_interrupt", "LEGACY_ACTIVITY_PREVENTS_FRESH_CLAIM" in (interrupt["preclaim_error"] or ""), "preclaim interrupt was admitted into the observer generation", interrupt)
    _assert("R05", "stale_stop", type(stale["claim"]) is dict and stale["claim"].get("state") == "UNKNOWN" and stale["claim"].get("baseline_validated") is False, "pre-fence stop did not invalidate baseline claim", stale["claim"])
    buffered_record = next((record for record in buffered["session"]._observation_records if record.get("raw") == '~"buffered-before-claim\\n"'), None) if buffered["session"] is not None else None
    action = buffered["action"]
    action_call = next((call for call in action.get("call_ledger", []) if call.get("call_id") == "attach-001"), None) if type(action) is dict else None
    _assert("R05", "buffered_output", buffered_record is not None and action_call is not None and buffered_record.get("sequence", 0) < action_call.get("request_sequence", 0) and action.get("stop_record", {}).get("sequence", 0) > action_call.get("request_sequence", 0) and all(item.get("sequence") != buffered_record.get("sequence") for item in buffered["session"]._observation_stops), "buffered pre-fence output was selected as a post-request stop", {"buffered_record": buffered_record, "action": action})
    _assert("R05", "no_retroactive_claim", send["claim"] is None and interrupt["claim"] is None and stale["claim"].get("state") != "CLAIMED" and buffered["claim"].get("state") == "CLAIMED" and buffered["action"].get("state") == "VALIDATED_OBSERVATION", "freshness history was retroactively admitted or the post-fence event was not independently validated", {"send": send["claim"], "interrupt": interrupt["claim"], "stale": stale["claim"], "buffered_action": buffered["action"]})
    return _case("R05", {"subcontrols": _passed_controls("R05"), "send": {"error": send["preclaim_error"], "cleanup": send["cleanup"]}, "interrupt": {"error": interrupt["preclaim_error"], "cleanup": interrupt["cleanup"]}, "stale": {"claim": stale["claim"], "cleanup": stale["cleanup"]}, "buffered": {"claim": buffered["claim"], "action": buffered["action"], "cleanup": buffered["cleanup"]}})


def _run_r06(context: dict[str, Any]) -> dict[str, Any]:
    wrong = asyncio.run(_claim_probe_async(context, baseline_control="WRONG_RESULT_TOKEN"))
    duplicate = asyncio.run(_claim_probe_async(context, transaction_fault="duplicate-result"))
    preprompt = asyncio.run(_claim_probe_async(context, transaction_fault="pre-result-prompt"))
    mi_error = asyncio.run(_claim_probe_async(context, baseline_control="MI_ERROR"))
    missing = asyncio.run(_claim_probe_async(context, transaction_fault="missing-result"))
    malformed_natural = context["fixture_data"]["natural"]
    malformed = asyncio.run(_claim_probe_async(
        context,
        action_sequence=({
            "kind": "attach", "command_id": "attach-001",
            "command": malformed_natural["attach_command"], "stop_expectation": "signal",
            "budget_ms": 1000,
        },),
        transaction_fault_by_kind={"attach": "empty-result-payload"},
    ))
    service_gdb = malformed.get("gdb_module")
    recovery = context["fixture_data"]["stop"]["recovery_r1"]
    mi_fixture = recovery["mi_parser"]
    valid_record = service_gdb._parse_mi_record((mi_fixture["valid"] + "\n").encode("ascii"), 1)
    malformed_record = service_gdb._parse_mi_record((mi_fixture["malformed"] + "\n").encode("ascii"), 2)
    wrong_call = wrong["claim"].get("call_ledger", [])[-1] if type(wrong["claim"]) is dict and wrong["claim"].get("call_ledger") else None
    duplicate_call = duplicate["claim"].get("call_ledger", [])[-1] if type(duplicate["claim"]) is dict and duplicate["claim"].get("call_ledger") else None
    pre_call = preprompt["claim"].get("call_ledger", [])[-1] if type(preprompt["claim"]) is dict and preprompt["claim"].get("call_ledger") else None
    mi_call = mi_error["claim"].get("call_ledger", [])[-1] if type(mi_error["claim"]) is dict and mi_error["claim"].get("call_ledger") else None
    missing_call = missing["claim"].get("call_ledger", [])[-1] if type(missing["claim"]) is dict and missing["claim"].get("call_ledger") else None
    malformed_action = malformed["action"]
    malformed_call = next((item for item in malformed_action.get("call_ledger", []) if type(item) is dict and item.get("call_id") == "attach-001"), None) if type(malformed_action) is dict else None
    malformed_action_record = next((record for record in malformed_call.get("records", []) if type(record) is dict and record.get("parse_error") is not None), None) if type(malformed_call) is dict else None
    malformed_raw_stop = next((record for record in malformed["session"]._observation_stops if type(record) is dict and record.get("raw") == context["fixture_data"]["stop"]["attach"]["raw_event"]), None) if malformed["session"] is not None else None
    malformed_admission = malformed_action.get("state") if type(malformed_action) is dict else "ADMITTED"
    malformed_validated_stop = malformed_action.get("validated_stop") if type(malformed_action) is dict else None
    _assert("R06", "wrong_token", wrong["claim"].get("state") == "UNKNOWN" and wrong["claim"].get("baseline_validated") is False and wrong["claim"].get("error_code") == "MI_RESULT_TOKEN_MISMATCH", "wrong-token MI result did not invalidate claim", wrong["claim"])
    _assert("R06", "duplicate_result", duplicate["claim"].get("state") == "UNKNOWN" and duplicate["claim"].get("baseline_validated") is False and type(duplicate_call) is dict and duplicate_call.get("protocol_error") == "DUPLICATE_MI_RESULT", "duplicate token result was accepted", duplicate["claim"])
    pre_records = pre_call.get("records", []) if type(pre_call) is dict else []
    result_index = next((index for index, record in enumerate(pre_records) if record.get("marker") == "^"), -1)
    prompt_before = any(record.get("kind") == "prompt" for record in pre_records[:result_index])
    prompt_after = any(record.get("kind") == "prompt" for record in pre_records[result_index + 1:])
    _assert("R06", "pre_result_prompt", preprompt["claim"].get("state") == "CLAIMED" and prompt_before and prompt_after and type(pre_call.get("result")) is dict and pre_call["result"].get("token") == "1", "pre-result prompt was mistaken for the matching token result or final prompt", {"claim": preprompt["claim"], "records": pre_records})
    _assert("R06", "mi_error", mi_error["claim"].get("state") == "UNKNOWN" and type(mi_error["claim"].get("mi_error")) is dict and mi_error["claim"]["mi_error"].get("class") == "error" and type(mi_call) is dict, "MI error was converted into baseline or stop proof", mi_error["claim"])
    _assert("R06", "no_validated_result", missing["claim"].get("state") == "UNKNOWN" and missing["claim"].get("baseline_validated") is False and type(missing_call) is dict and missing_call.get("result") is None and "validated_stop" not in missing["claim"] and missing["session"] is not None and not missing["session"]._observation_stops, "missing command result or raw stop was promoted to proof", missing["claim"])
    _assert("R06", "connected_without_separator_valid", valid_record.get("kind") == "mi" and valid_record.get("class") == mi_fixture["valid_class"] and "parse_error" not in valid_record, "valid tokenized MI result was not parsed as the independent class", valid_record)
    _assert("R06", "empty_payload_rejected", malformed_record.get("kind") == "mi" and malformed_record.get("class") == "connected" and malformed_record.get("parse_error") == mi_fixture["malformed_parse_error"] and malformed["claim"].get("state") == "CLAIMED" and malformed["claim"].get("baseline_validated") is True and type(malformed_action) is dict and malformed_action.get("state") == mi_fixture["malformed_admission"] and malformed_action.get("error_code") == "MALFORMED_MI_RESULT" and type(malformed_call) is dict and malformed_call.get("protocol_error") == "MALFORMED_MI_RESULT" and type(malformed_action_record) is dict and malformed_action_record.get("parse_error") == mi_fixture["malformed_parse_error"] and type(malformed_raw_stop) is dict and malformed_admission == mi_fixture["malformed_admission"] and malformed_validated_stop == mi_fixture["malformed_validated_stop"], "empty MI attach result was not rejected despite an otherwise-valid signal event", {"record": malformed_record, "call": malformed_call, "raw_action_record": malformed_action_record, "raw_signal_stop": malformed_raw_stop, "admission": malformed_admission, "validated_stop": malformed_validated_stop, "claim": malformed["claim"], "action": malformed_action})
    overflow_case = recovery["overflow"]["case_input"]
    overflow_source = {
        "kind": "RESULT", "phase": "stop-observation-reader", "nonce": "0" * 32,
        "manifest_sha256": "1" * 64, "ticket_sha256": "2" * 64,
        "source_sha256": {}, "fixture_sha256": {}, "read_inputs_sha256": {},
        "status": "FAIL", "cases": [overflow_case],
        "ledgers": {
            "service_calls": [{"method": "oversize-control", "payload": "x" * 9000} for _ in range(96)],
            "factory_calls": [], "reader_count": 0, "raw_record_count": 0,
            "real_factory_calls": 0, "real_gdb_calls": 0, "real_network_calls": 0,
        },
        "failure": _failure("ASSERTION", None, None, "synthetic oversize-control input"),
    }
    overflow_result, overflow_encoded, overflow_returncode = _encode_worker_result(overflow_source)
    overflow_observed = overflow_result.get("failure", {}).get("observed", {})
    overflow_init = {
        name: overflow_source[name]
        for name in ("phase", "nonce", "manifest_sha256", "ticket_sha256", "source_sha256", "fixture_sha256", "read_inputs_sha256")
    }
    overflow_validated = _validate_worker_result(overflow_result, overflow_init, 1)
    overflow_retained_case = overflow_result.get("cases", [None])[0]
    overflow_case_summary = overflow_observed.get("cases", {})
    overflow_service_summary = overflow_observed.get("service_calls", {})
    _assert("R06", "oversized_result_protocol_partial", len(overflow_encoded) <= PROTOCOL_LINE_LIMIT and overflow_returncode == 1 and overflow_validated.get("status") == recovery["overflow"]["status"] and overflow_result.get("failure", {}).get("category") == recovery["overflow"]["failure_category"] and overflow_observed.get("partial_evidence") is recovery["overflow"]["partial_evidence_required"] and overflow_observed.get("cap_increased") is recovery["overflow"]["cap_increase_allowed"] and overflow_result.get("cases") == [overflow_case] and overflow_retained_case == overflow_case and overflow_retained_case.get("status") == "FAIL" and overflow_retained_case.get("observations", {}).get("fixture_provenance") == overflow_case["observations"]["fixture_provenance"] and overflow_retained_case.get("observations", {}).get("subcontrols") == [] and overflow_case_summary.get("total") == 1 and overflow_case_summary.get("retained") == 1 and overflow_case_summary.get("omitted") == 0 and _is_digest(overflow_case_summary.get("omitted_sha256")) and overflow_service_summary.get("omitted", 0) > 0 and _is_digest(overflow_service_summary.get("omitted_sha256")), "oversized RESULT did not become bounded truthful partial protocol failure with retained synthetic FAIL row", {"encoded_bytes": len(overflow_encoded), "returncode": overflow_returncode, "status": overflow_validated.get("status"), "failure": overflow_result.get("failure"), "retained_case": overflow_retained_case, "retained_service_calls": len(overflow_result.get("ledgers", {}).get("service_calls", []))})

    return _case("R06", {"subcontrols": _passed_controls("R06"), "wrong_token": wrong["claim"], "duplicate_result": duplicate["claim"], "pre_result_prompt": preprompt["claim"], "mi_error": mi_error["claim"], "missing_result": missing["claim"], "malformed_result": malformed["claim"], "mi_parser": {"valid": valid_record, "malformed": malformed_record}, "overflow_fallback": {"encoded_bytes": len(overflow_encoded), "retained_cases": len(overflow_result["cases"]), "retained_service_calls": len(overflow_result["ledgers"]["service_calls"]), "failure": overflow_result["failure"]}})


class QualificationFailure(Exception):
    def __init__(self, case_id: str, subcontrol: str, message: str, observed: Any = None, category: str = "ASSERTION"):
        super().__init__(message)
        self.case_id = case_id
        self.subcontrol = subcontrol
        self.observed = observed
        self.category = category


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _strict_json(data: bytes, label: str) -> Any:
    def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(label + " has duplicate JSON key " + key)
            result[key] = value
        return result

    def reject_constant(value: str) -> Any:
        raise ValueError(label + " contains non-standard JSON constant " + value)

    return json.loads(data.decode("utf-8", errors="strict"), object_pairs_hook=unique_pairs, parse_constant=reject_constant)


def _is_digest(value: Any) -> bool:
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _exact_object(value: Any, keys: tuple[str, ...], label: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != set(keys):
        raise ValueError(label + " has the wrong exact object shape")
    return value


def _frozen_path(raw_path: Any) -> Path:
    if type(raw_path) is not str or not raw_path:
        raise ValueError("frozen path must be a nonempty string")
    drive, _tail = ntpath.splitdrive(raw_path)
    if drive:
        if drive.casefold() != "e:" or not ntpath.isabs(raw_path):
            raise ValueError("frozen Windows path is outside the approved E: workspace")
        root = ntpath.normcase(ntpath.normpath(WINDOWS_WORKSPACE_ROOT))
        normalized = ntpath.normcase(ntpath.normpath(raw_path))
        if normalized != root and not normalized.startswith(root + "\\"):
            raise ValueError("frozen Windows path escapes the approved workspace")
        suffix = ntpath.relpath(raw_path, WINDOWS_WORKSPACE_ROOT)
        translated = WSL_WORKSPACE_ROOT.joinpath(*suffix.replace("\\", "/").split("/"))
    else:
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            raise ValueError("frozen non-Windows path must be absolute")
        translated = candidate
    workspace = PROJECT_ROOT.resolve()
    resolved = translated.resolve()
    if resolved != workspace and workspace not in resolved.parents:
        raise ValueError("frozen path resolves outside the current workspace")
    return resolved


def _read_fixed_inputs(init: dict[str, Any]) -> dict[str, Any]:
    manifest_bytes = FREEZE_PATH.read_bytes()
    manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
    if manifest_sha != init["manifest_sha256"]:
        raise ValueError("freeze manifest differs from host INIT")
    freeze = _strict_json(manifest_bytes, "integration freeze")
    if type(freeze) is not dict or freeze.get("schema") != "ladybug.feat010.controller-integration.freeze.v1":
        raise ValueError("integration freeze schema is invalid")
    if freeze.get("qualification_dispatch_authorized") is not True:
        raise ValueError("parent qualification dispatch is not authorized")
    execution = freeze.get("execution_freeze")
    if type(execution) is not dict or execution.get("authorized") is not True:
        raise ValueError("parent execution freeze is absent or unauthorized")
    sources = execution.get("source_sha256")
    fixtures = execution.get("fixture_sha256")
    read_inputs = execution.get("read_inputs_sha256")
    if type(sources) is not dict or set(sources) != set(SOURCE_PATHS):
        raise ValueError("frozen source set differs from the exact four-path contract")
    if type(fixtures) is not dict or set(fixtures) != set(FIXTURE_PATHS):
        raise ValueError("frozen fixture set differs from the exact five-path contract")
    if type(read_inputs) is not dict or set(read_inputs) != set(READ_INPUT_PATHS):
        raise ValueError("frozen read-only input set differs from the exact transcript pin")
    if any(not _is_digest(value) for value in (*sources.values(), *fixtures.values(), *read_inputs.values())):
        raise ValueError("freeze contains an invalid source, fixture, or read-input digest")
    if sources != init["source_sha256"] or fixtures != init["fixture_sha256"] or read_inputs != init["read_inputs_sha256"]:
        raise ValueError("host INIT source/fixture/read-input maps differ from freeze")
    ticket_sha = execution.get("ticket_sha256")
    if not _is_digest(ticket_sha) or ticket_sha != init["ticket_sha256"] or _sha256(TICKET_PATH) != ticket_sha:
        raise ValueError("canonical FEAT-010 ticket is not bound to INIT")
    if execution.get("phases") != {
        name: {"maximum_ms": phase["maximum_ms"], "attempts": 1, "case_ids": list(phase["case_ids"])}
        for name, phase in PHASES.items()
    }:
        raise ValueError("frozen phase limits/case IDs/attempt counts differ from source contract")
    if execution.get("source_sha256") != init["source_sha256"] or execution.get("fixture_sha256") != init["fixture_sha256"]:
        raise ValueError("source or fixture map is not identical to the parent execution freeze")
    qualified = freeze.get("qualified_seven_inputs_sha256")
    if type(qualified) is not dict or set(qualified) != set(QUALIFIED_INPUTS) or any(not _is_digest(v) for v in qualified.values()):
        raise ValueError("parent qualified historical seven-input pin is invalid")
    qualified_root = _frozen_path(freeze.get("qualified_service_root"))
    if qualified_root != QUALIFIED_ROOT.resolve():
        raise ValueError("qualified historical service root is not the pinned C16 source")
    if type(freeze.get("protected_files_sha256")) is not dict or len(freeze["protected_files_sha256"]) != 199:
        raise ValueError("parent protected source map is not the exact 199-file set")
    if freeze.get("protected_count") != 199:
        raise ValueError("protected source count differs from the fixed 199-file contract")
    environment = freeze.get("python")
    if type(environment) is not dict or environment.get("path") != PYTHON_PATH or environment.get("resolved") != PYTHON_RESOLVED or environment.get("sha256") != PYTHON_SHA256:
        raise ValueError("pinned Python environment differs from the approved interpreter")
    current_sources = {path: _sha256(ROOT / path) for path in SOURCE_PATHS}
    current_fixtures = {path: _sha256(ROOT / path) for path in FIXTURE_PATHS}
    current_read = {READ_INPUT_PATHS[0]: _sha256(TRANSCRIPT_PATH)}
    if current_sources != sources or current_fixtures != fixtures or current_read != read_inputs:
        raise ValueError("source, fixture, or retained transcript hash differs from parent freeze")
    if current_read[READ_INPUT_PATHS[0]] != TRANSCRIPT_SHA256:
        raise ValueError("retained actual unknown-signal transcript differs from its fixed review pin")
    if os.path.realpath(PYTHON_PATH) != PYTHON_RESOLVED or _sha256(Path(PYTHON_RESOLVED)) != PYTHON_SHA256:
        raise ValueError("pinned Python executable path or hash changed")
    if os.path.realpath(sys.executable) != PYTHON_RESOLVED:
        raise ValueError("supervisor is not using the pinned Python interpreter")
    for relative, expected in qualified.items():
        path = qualified_root / relative
        if not path.is_file() or _sha256(path) != expected:
            raise ValueError("qualified historical input changed: " + relative)
    for raw_path, expected in freeze["protected_files_sha256"].items():
        path = _frozen_path(raw_path)
        if not path.is_file() or not _is_digest(expected) or _sha256(path) != expected:
            raise ValueError("protected parent input changed or is missing: " + raw_path)
    fixture_data: dict[str, Any] = {}
    for relative, name in FIXTURE_NAMES.items():
        fixture_data[name] = _strict_json((ROOT / relative).read_bytes(), relative)
    if fixture_data["case_contract"].get("schema") != "ladybug.feat010.sro.case-contract.v1" or fixture_data["case_contract"].get("runtime_authorized") is not False or fixture_data["case_contract"].get("native_evidence") is not False:
        raise ValueError("SRO contract is not the expected source-preparation fixture")
    if fixture_data["producer"].get("source_sha256") != PRODUCER_SHA256 or hashlib.sha256(fixture_data["producer"].get("source_ascii", "").encode("ascii")).hexdigest() != PRODUCER_SHA256:
        raise ValueError("fixed fake-GDB producer literal differs from its independent hash")
    return {
        "freeze": freeze,
        "execution": execution,
        "source_sha256": current_sources,
        "fixture_sha256": current_fixtures,
        "read_inputs_sha256": current_read,
        "ticket_sha256": ticket_sha,
        "manifest_sha256": manifest_sha,
        "qualified_sha256": qualified,
        "fixture_data": fixture_data,
    }


def _preservation_snapshot(context: dict[str, Any]) -> dict[str, Any]:
    source = {path: _sha256(ROOT / path) for path in SOURCE_PATHS}
    fixtures = {path: _sha256(ROOT / path) for path in FIXTURE_PATHS}
    read_inputs = {READ_INPUT_PATHS[0]: _sha256(TRANSCRIPT_PATH)}
    protected = {path: _sha256(_frozen_path(path)) for path in context["freeze"]["protected_files_sha256"]}
    qualified_root = _frozen_path(context["freeze"]["qualified_service_root"])
    qualified = {name: _sha256(qualified_root / name) for name in QUALIFIED_INPUTS}
    return {
        "source_sha256": source,
        "fixture_sha256": fixtures,
        "read_inputs_sha256": read_inputs,
        "ticket_sha256": _sha256(TICKET_PATH),
        "manifest_sha256": _sha256(FREEZE_PATH),
        "protected_files_sha256": protected,
        "qualified_seven_inputs_sha256": qualified,
        "python_sha256": _sha256(Path(PYTHON_RESOLVED)),
    }


def _same_preservation(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return type(left) is dict and type(right) is dict and left == right


def _case(case_id: str, observations: dict[str, Any], status: str = "PASS") -> dict[str, Any]:
    expected_subcontrols = CASE_SUBCONTROLS[case_id]
    controls = observations.get("subcontrols")
    if type(controls) is not list or tuple(item.get("id") for item in controls if type(item) is dict) != expected_subcontrols:
        raise QualificationFailure(case_id, "subcontrol-ledger", "case omitted or reordered an approved subcontrol", controls, category="MISSING_COVERAGE")
    actual = _CONTROL_TRACE.get(case_id, {})
    if set(actual) != set(expected_subcontrols) or len(actual) != len(expected_subcontrols):
        raise QualificationFailure(case_id, "subcontrol-ledger", "required subcontrols were not each executed exactly once", {"expected": expected_subcontrols, "actual": sorted(actual)}, category="MISSING_COVERAGE")
    if any(item.get("status") != "PASS" for item in controls) or any(item.get("condition") is not True for item in actual.values()):
        raise QualificationFailure(case_id, "subcontrol-ledger", "one or more required executed subcontrols failed", controls, category="MISSING_COVERAGE")
    return {"case_id": case_id, "expected": EXPECTED_BY_CASE[case_id], "status": status, "observations": _compact_evidence(observations)}


def _passed_controls(case_id: str, observed: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    trace = _CONTROL_TRACE.get(case_id, {})
    result: list[dict[str, Any]] = []
    for item in CASE_SUBCONTROLS[case_id]:
        record = trace.get(item)
        if record is None:
            raise QualificationFailure(case_id, item, "subcontrol has no executed assertion record", category="MISSING_COVERAGE")
        result.append({"id": item, "status": "PASS" if record["condition"] is True else "FAIL", "observed": record.get("observed", (observed or {}).get(item))})
    return result


def _assert(case_id: str, subcontrol: str, condition: bool, message: str, observed: Any = None) -> None:
    trace = _CONTROL_TRACE.setdefault(case_id, {})
    if subcontrol in trace:
        raise QualificationFailure(case_id, subcontrol, "subcontrol assertion executed more than once", trace[subcontrol], category="MISSING_COVERAGE")
    trace[subcontrol] = {"condition": condition is True, "message": message, "observed": observed}
    if not condition:
        raise QualificationFailure(case_id, subcontrol, message, observed)


def _event_only(event: dict[str, Any], hypothetical_cause: str | None) -> dict[str, Any]:
    del hypothetical_cause
    return {
        "raw": event.get("raw"),
        "sequence": event.get("sequence"),
        "observation": "SESSION_EVENT_ONLY",
    }


def _fixture_mi_record(
    raw: str, *, sequence: int, token: str | None, marker: str | None,
    record_class: str | None, fields: dict[str, Any], binding: dict[str, Any],
    state_generation: int, observation: str | None = None,
) -> dict[str, Any]:
    record = {
        "sequence": sequence, "raw": raw,
        "raw_b64": base64.b64encode((raw + "\n").encode("ascii")).decode("ascii"),
        "kind": "mi", "token": token, "marker": marker, "class": record_class,
        "fields": fields, "owner_id": binding["owner_id"], "session_id": binding["session_id"],
        "observation_generation": binding["observation_generation"], "state_generation": state_generation,
    }
    if observation is not None:
        record["observation"] = observation
    return record


def _fixture_prompt_record(binding: dict[str, Any], sequence: int, state_generation: int) -> dict[str, Any]:
    raw = "(gdb)"
    return {
        "sequence": sequence, "raw": raw,
        "raw_b64": base64.b64encode((raw + "\n").encode("ascii")).decode("ascii"),
        "kind": "prompt", "token": None, "marker": None, "class": None, "fields": {},
        "owner_id": binding["owner_id"], "session_id": binding["session_id"],
        "observation_generation": binding["observation_generation"], "state_generation": state_generation,
    }


def _owned_exec_oracle_fixture(context: dict[str, Any], kind: str) -> tuple[dict[str, Any], dict[str, Any]]:
    stop = context["fixture_data"]["stop"]
    natural = context["fixture_data"]["natural"]
    recovery = stop["recovery_r1"]
    expected = recovery[kind]
    action_kind = "attach" if kind == "signal" else "continue"
    stop_kind = "attach" if kind == "signal" else "continuation"
    state_kind = "post-attach-thread-info" if kind == "signal" else "post-continue-thread-info"
    transactions = {item["kind"]: item for item in natural["transactions"]}
    action = transactions[action_kind]
    state = transactions[state_kind]
    sequence = action["expected_stop_sequence"]
    state_generation_after = action["expected_stop_state_generation"]
    state_generation_before = natural["initial_state_generation"] if kind == "signal" else transactions["attach"]["expected_stop_state_generation"]
    command_id = "attach-001" if kind == "signal" else "continue-001"
    raw_event = stop[stop_kind]["raw_event"]
    state_body = stop[stop_kind]["raw_state_result_body"]
    action_raw = action["token"] + action["body"]
    state_raw = state["token"] + state_body
    action_sequence = sequence - (1 if kind == "signal" else 2)
    state_sequence = sequence + 2
    action_state_generation = state_generation_before + (1 if action.get("intermediate_running_event") else 0)
    binding = {
        "owner_id": natural["owner_id"], "session_id": natural["session_id"],
        "command_id": command_id, "command": expected["command"],
        "token": action["token"], "state_token": state["token"],
        "sequence": sequence, "kind": kind, "raw_event": raw_event,
        "reason": expected["reason"], "thread_id": expected["thread_id"], "pc": expected["pc"],
        "observation_generation": natural["observation_generation"],
        "result_class": expected["result_class"], "signal_name": expected.get("signal_name"),
        "signal_meaning": expected.get("signal_meaning"), "stopped_threads": expected["stopped_threads"],
        "breakpoint_number": expected.get("number"), "breakpoint_disposition": expected.get("disposition"),
        "state_generation_before": state_generation_before, "state_generation_after": state_generation_after,
        "action_state_generation": action_state_generation, "action_sequence": action_sequence,
        "state_sequence": state_sequence, "action_raw": action_raw, "state_raw": state_raw,
        "action_fields": {},
        "mi_command": "-target-select remote 127.0.0.1:65520" if kind == "signal" else "-exec-continue",
        "text": recovery["display"]["stop"] if kind == "signal" else recovery["display"]["token_and_prompt"],
    }
    thread_id, pc = binding["thread_id"], binding["pc"]
    if kind == "signal":
        stop_fields = {
            "reason": binding["reason"], "signal-name": binding["signal_name"],
            "signal-meaning": binding["signal_meaning"], "frame": {"addr": pc},
            "thread-id": thread_id, "stopped-threads": binding["stopped_threads"],
        }
    else:
        stop_fields = {
            "reason": binding["reason"], "disp": binding["breakpoint_disposition"],
            "bkptno": binding["breakpoint_number"], "frame": {"addr": pc},
            "thread-id": thread_id, "stopped-threads": binding["stopped_threads"],
        }
    state_fields = {
        "threads": [{
            "id": thread_id, "target-id": "Thread " + thread_id,
            "frame": {"level": "0", "addr": pc}, "state": "stopped",
        }],
        "current-thread-id": thread_id,
    }
    action_result = _fixture_mi_record(
        action_raw, sequence=action_sequence, token=action["token"], marker="^",
        record_class=expected["result_class"], fields={}, binding=binding,
        state_generation=action_state_generation,
    )
    stop_record = _fixture_mi_record(
        raw_event, sequence=sequence, token=None, marker="*", record_class="stopped",
        fields=stop_fields, binding=binding, state_generation=state_generation_after,
        observation="SESSION_EVENT_ONLY",
    )
    state_result = _fixture_mi_record(
        state_raw, sequence=state_sequence, token=state["token"], marker="^",
        record_class="done", fields=state_fields, binding=binding,
        state_generation=state_generation_after,
    )
    action_prompt_sequence = sequence + 1 if kind == "signal" else action_sequence + 1
    action_prompt = _fixture_prompt_record(
        binding, action_prompt_sequence,
        state_generation_after if kind == "signal" else action_state_generation,
    )
    action_records = [action_result, stop_record, action_prompt] if kind == "signal" else [
        _fixture_mi_record(
            action["intermediate_running_event"], sequence=action_sequence - 1,
            token=None, marker="*", record_class="running", fields={"thread-id": "all"},
            binding=binding, state_generation=action_state_generation,
        ),
        action_result, action_prompt,
    ]
    action_call = {
        "call_id": command_id, "operation_id": command_id, "token": action["token"],
        "mi_command": binding["mi_command"], "request_sequence": action_sequence - (1 if kind == "signal" else 2),
        "observation_generation": binding["observation_generation"],
        "state_generation_before": state_generation_before, "records": action_records,
        "result": action_result, "prompt_sequence": action_prompt_sequence, "protocol_error": None,
    }
    state_prompt = _fixture_prompt_record(binding, state_sequence + 1, state_generation_after)
    state_call = {
        "call_id": command_id + ":state-after", "operation_id": command_id, "token": state["token"],
        "mi_command": "-thread-info", "request_sequence": sequence + 1,
        "observation_generation": binding["observation_generation"],
        "state_generation_before": state_generation_after, "records": [state_result, state_prompt],
        "result": state_result, "prompt_sequence": state_sequence + 1, "protocol_error": None,
    }
    oracle = {
        "schema": "ladybug.feat010.owned-exec.v1", "owner_id": binding["owner_id"],
        "session_id": binding["session_id"], "command_id": command_id,
        "state": "VALIDATED_OBSERVATION", "observation_generation": binding["observation_generation"],
        "state_generation_before": state_generation_before, "state_generation_after": state_generation_after,
        "command": binding["command"], "mi_result": action_result, "mi_error": None,
        "call_ledger": [action_call, state_call], "stop_record": stop_record,
        "text": binding["text"], "stop_observation": "SESSION_EVENT_ONLY",
        "current_state": {"thread_state": "stopped", "thread_id": thread_id, "pc": pc, "mi_result": state_result},
        "validated_stop": {
            "kind": kind, "reason": binding["reason"], "signal_name": binding["signal_name"],
            "breakpoint_number": binding["breakpoint_number"], "pc": pc, "thread_id": thread_id,
            "sequence": sequence, "observation_generation": binding["observation_generation"],
            "state_generation": state_generation_after, "observation": "SESSION_EVENT_ONLY",
        },
        "overflow_evidence": None, "error_code": None,
    }
    binding["stop_fields"] = stop_fields
    binding["state_fields"] = state_fields
    return oracle, binding


def _oracle_envelope_valid(value: Any, binding: dict[str, Any]) -> bool:
    envelope_keys = {
        "schema", "owner_id", "session_id", "command_id", "command", "state",
        "observation_generation", "state_generation_before", "state_generation_after",
        "mi_result", "mi_error", "text", "stop_record", "stop_observation",
        "current_state", "validated_stop", "call_ledger", "overflow_evidence", "error_code",
    }
    record_base = {"sequence", "raw", "raw_b64", "kind", "token", "marker", "class", "fields"}
    record_metadata = {"owner_id", "session_id", "observation_generation", "state_generation"}

    def record_matches(
        record: Any, *, raw: str, token: str | None, marker: str | None,
        record_class: str | None, fields: dict[str, Any], state_generation: int,
        sequence: int | None = None, after_sequence: int | None = None,
        observation: str | None = None,
    ) -> bool:
        expected_keys = record_base | record_metadata | ({"observation"} if observation is not None else set())
        if type(record) is not dict or set(record) != expected_keys:
            return False
        if (type(record.get("sequence")) is not int
                or (sequence is not None and record["sequence"] != sequence)
                or (after_sequence is not None and record["sequence"] <= after_sequence)):
            return False
        if (record.get("raw") != raw
                or record.get("raw_b64") != base64.b64encode((raw + "\n").encode("ascii")).decode("ascii")
                or record.get("kind") != "mi" or record.get("token") != token
                or record.get("marker") != marker or record.get("class") != record_class
                or record.get("fields") != fields):
            return False
        if (record.get("owner_id") != binding["owner_id"]
                or record.get("session_id") != binding["session_id"]
                or type(record.get("observation_generation")) is not int
                or record.get("observation_generation") != binding["observation_generation"]
                or type(record.get("state_generation")) is not int
                or record.get("state_generation") != state_generation):
            return False
        return observation is None or record.get("observation") == observation

    if type(value) is not dict or set(value) != envelope_keys:
        return False
    if (value.get("schema") != "ladybug.feat010.owned-exec.v1"
            or value.get("owner_id") != binding["owner_id"]
            or value.get("session_id") != binding["session_id"]
            or type(value.get("command_id")) is not str
            or value.get("command_id") != binding["command_id"]
            or value.get("command") != binding["command"]
            or value.get("text") != binding["text"]):
        return False
    if (value.get("state") != "VALIDATED_OBSERVATION"
            or type(value.get("observation_generation")) is not int
            or value.get("observation_generation") != binding["observation_generation"]
            or type(value.get("state_generation_before")) is not int
            or value.get("state_generation_before") != binding["state_generation_before"]
            or type(value.get("state_generation_after")) is not int
            or value.get("state_generation_after") != binding["state_generation_after"]
            or value.get("mi_error") is not None or value.get("error_code") is not None
            or value.get("overflow_evidence") is not None
            or value.get("stop_observation") != "SESSION_EVENT_ONLY"):
        return False
    if not record_matches(
        value.get("mi_result"), raw=binding["action_raw"], token=binding["token"],
        marker="^", record_class=binding["result_class"], fields=binding["action_fields"],
        state_generation=binding["action_state_generation"], after_sequence=0,
    ):
        return False
    if value["mi_result"]["sequence"] >= binding["sequence"]:
        return False
    stop_record = value.get("stop_record")
    if not record_matches(
        stop_record, raw=binding["raw_event"], token=None, marker="*", record_class="stopped",
        fields=binding["stop_fields"], state_generation=binding["state_generation_after"],
        sequence=binding["sequence"], observation="SESSION_EVENT_ONLY",
    ):
        return False
    current = value.get("current_state")
    if (type(current) is not dict or set(current) != {"thread_state", "thread_id", "pc", "mi_result"}
            or current.get("thread_state") != "stopped"
            or current.get("thread_id") != binding["thread_id"]
            or current.get("pc") != binding["pc"]):
        return False
    state_fields = binding["state_fields"]
    if not record_matches(
        current.get("mi_result"), raw=binding["state_raw"], token=binding["state_token"],
        marker="^", record_class="done", fields=state_fields,
        state_generation=binding["state_generation_after"], after_sequence=binding["sequence"],
    ):
        return False
    threads = state_fields.get("threads")
    if (type(threads) is not list or len(threads) != 1 or type(threads[0]) is not dict
            or set(threads[0]) != {"id", "target-id", "frame", "state"}
            or threads[0].get("id") != binding["thread_id"]
            or threads[0].get("state") != "stopped"
            or type(threads[0].get("frame")) is not dict
            or set(threads[0]["frame"]) != {"level", "addr"}
            or threads[0]["frame"].get("addr") != binding["pc"]):
        return False
    expected_validated = {
        "kind": binding["kind"], "reason": binding["reason"],
        "signal_name": binding["signal_name"], "breakpoint_number": binding["breakpoint_number"],
        "pc": binding["pc"], "thread_id": binding["thread_id"], "sequence": binding["sequence"],
        "observation_generation": binding["observation_generation"],
        "state_generation": binding["state_generation_after"], "observation": "SESSION_EVENT_ONLY",
    }
    validated_stop = value.get("validated_stop")
    if (type(validated_stop) is not dict or set(validated_stop) != set(expected_validated)
            or any(type(validated_stop.get(name)) is not int for name in ("sequence", "observation_generation", "state_generation"))
            or validated_stop != expected_validated):
        return False
    calls = value.get("call_ledger")
    if type(calls) is not list:
        return False
    state_calls = [call for call in calls if type(call) is dict and call.get("call_id") == binding["command_id"] + ":state-after"]
    action_calls = [call for call in calls if type(call) is dict and call.get("call_id") == binding["command_id"]]
    if len(state_calls) != 1 or len(action_calls) != 1:
        return False

    def call_matches(
        call: dict[str, Any], *, call_id: str, token: str, mi_command: str,
        state_generation_before: int, expected_result: dict[str, Any],
    ) -> bool:
        required = {"call_id", "operation_id", "token", "mi_command", "request_sequence", "observation_generation", "state_generation_before", "records", "result", "prompt_sequence", "protocol_error"}
        records = call.get("records")
        prompt_sequence = call.get("prompt_sequence")
        if (not required.issubset(call)
                or call.get("call_id") != call_id or call.get("operation_id") != binding["command_id"]
                or call.get("token") != token or call.get("mi_command") != mi_command
                or type(call.get("observation_generation")) is not int
                or call.get("observation_generation") != binding["observation_generation"]
                or type(call.get("state_generation_before")) is not int
                or call.get("state_generation_before") != state_generation_before
                or type(call.get("request_sequence")) is not int
                or call.get("request_sequence") >= expected_result["sequence"]
                or type(prompt_sequence) is not int or prompt_sequence <= expected_result["sequence"]
                or call.get("protocol_error") is not None or call.get("result") != expected_result
                or type(records) is not list
                or not any(type(item) is dict and item == expected_result for item in records)
                or not any(type(item) is dict and item.get("kind") == "prompt" and item.get("sequence") == prompt_sequence for item in records)):
            return False
        return True

    if not call_matches(
        action_calls[0], call_id=binding["command_id"], token=binding["token"],
        mi_command=binding["mi_command"], state_generation_before=binding["state_generation_before"],
        expected_result=value["mi_result"],
    ):
        return False
    if not call_matches(
        state_calls[0], call_id=binding["command_id"] + ":state-after", token=binding["state_token"],
        mi_command="-thread-info", state_generation_before=binding["state_generation_after"],
        expected_result=current["mi_result"],
    ):
        return False
    return True


def _q01(context: dict[str, Any]) -> dict[str, Any]:
    baseline, signal_binding = _owned_exec_oracle_fixture(context, "signal")
    breakpoint, breakpoint_binding = _owned_exec_oracle_fixture(context, "breakpoint")
    signal_valid = _oracle_envelope_valid(baseline, signal_binding)
    breakpoint_valid = _oracle_envelope_valid(breakpoint, breakpoint_binding)
    _assert("Q01", "valid", signal_valid and breakpoint_valid, "independent fixture-bound raw signal and breakpoint envelopes did not pass", {"signal": signal_valid, "breakpoint": breakpoint_valid})

    mutations: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    value = json.loads(json.dumps(baseline)); value["owner_id"] = "other-owner"; mutations.append(("owner", value, signal_binding))
    value = json.loads(json.dumps(baseline)); value["session_id"] = "other-session"; mutations.append(("session", value, signal_binding))
    value = json.loads(json.dumps(baseline)); value["observation_generation"] = True; mutations.append(("generation", value, signal_binding))
    value = json.loads(json.dumps(baseline)); value["mi_result"]["token"] = "902"; mutations.append(("token", value, signal_binding))
    value = json.loads(json.dumps(baseline)); value["stop_record"]["sequence"] += 1; mutations.append(("sequence", value, signal_binding))
    value = json.loads(json.dumps(baseline)); value["state_generation_after"] = True; mutations.append(("boolean", value, signal_binding))
    value = json.loads(json.dumps(baseline)); value["mi_error"] = {"class": "error"}; mutations.append(("mi_error", value, signal_binding))
    value = json.loads(json.dumps(baseline)); value["current_state"] = None; mutations.append(("current_state", value, signal_binding))
    value = json.loads(json.dumps(baseline)); value["cause_command_id"] = "attach-001"; mutations.append(("cause_id", value, signal_binding))

    coherent = json.loads(json.dumps(baseline))
    alternate_pc, alternate_thread = "0x0000c003", "2"
    coherent_stop = coherent["stop_record"]
    coherent_stop["fields"].update({"thread-id": alternate_thread, "frame": {"addr": alternate_pc}})
    coherent["current_state"].update({"thread_id": alternate_thread, "pc": alternate_pc})
    coherent_state = coherent["current_state"]["mi_result"]
    coherent_state_raw = coherent_state["raw"].replace('id="1"', 'id="2"').replace("Thread 1", "Thread 2").replace(signal_binding["pc"], alternate_pc)
    coherent_state["raw"] = coherent_state_raw
    coherent_state["raw_b64"] = base64.b64encode((coherent_state_raw + "\n").encode("ascii")).decode("ascii")
    coherent_state["fields"].update({"threads": [{"id": alternate_thread, "target-id": "Thread 2", "frame": {"level": "0", "addr": alternate_pc}, "state": "stopped"}], "current-thread-id": alternate_thread})
    state_call = next(call for call in coherent["call_ledger"] if call["call_id"] == signal_binding["command_id"] + ":state-after")
    state_call["result"] = coherent_state
    state_call["records"] = [coherent_state if item.get("token") == signal_binding["state_token"] and item.get("marker") == "^" else item for item in state_call["records"]]
    action_call = next(call for call in coherent["call_ledger"] if call["call_id"] == signal_binding["command_id"])
    action_call["records"] = [coherent_stop if item.get("sequence") == signal_binding["sequence"] and item.get("marker") == "*" else item for item in action_call["records"]]
    coherent["validated_stop"].update({"thread_id": alternate_thread, "pc": alternate_pc})
    mutations.append(("coherent_copy", coherent, signal_binding))
    value = json.loads(json.dumps(baseline)); value["command"] = "continue"; mutations.append(("command", value, signal_binding))
    value = json.loads(json.dumps(baseline)); value["validated_stop"]["observation_generation"] = signal_binding["observation_generation"] + 1; mutations.append(("nested_generation", value, signal_binding))
    value = json.loads(json.dumps(baseline)); value["validated_stop"]["observation_generation"] = True; mutations.append(("nested_type", value, signal_binding))
    value = json.loads(json.dumps(baseline)); value["error_code"] = "UNEXPECTED_ERROR"; mutations.append(("error_code", value, signal_binding))
    value = json.loads(json.dumps(baseline)); value["overflow_evidence"] = {"overflow": True}; mutations.append(("overflow_evidence", value, signal_binding))
    value = json.loads(json.dumps(baseline)); value["validated_stop"]["unexpected"] = "extra"; mutations.append(("extra_field", value, signal_binding))
    value = json.loads(json.dumps(baseline)); value["stop_record"]["sequence"] = float(value["stop_record"]["sequence"]); mutations.append(("float", value, signal_binding))
    for name, value, expected_binding in mutations:
        _assert("Q01", name, not _oracle_envelope_valid(value, expected_binding), "single or coherent-copy mutation was admitted by independent fixture binding", value)
    return _case("Q01", {"subcontrols": _passed_controls("Q01")})


def _walk_command_outputs(value: Any, expected_command: str, found: list[dict[str, Any]]) -> None:
    if type(value) is dict:
        if value.get("command") == expected_command and type(value.get("output")) is str:
            found.append(value)
        for child in value.values():
            _walk_command_outputs(child, expected_command, found)
    elif type(value) is list:
        for child in value:
            _walk_command_outputs(child, expected_command, found)


def _normalize_legacy_capture(record: Any) -> dict[str, Any] | None:
    if type(record) is not dict or set(record) != {"command", "output", "error"}:
        return None
    if type(record["command"]) is not str or type(record["output"]) is not str or type(record["error"]) is not bool:
        return None
    signal_lines = [line for line in record["output"].splitlines() if "signal" in line.lower()]
    return {
        "command": record["command"],
        "output": record["output"],
        "error": record["error"],
        "native_stop": None,
        "formatted_signal_mentions": signal_lines,
    }


def _captured_signal_admission(normalized: Any) -> str:
    if type(normalized) is not dict or type(normalized.get("native_stop")) is not dict:
        return "UNKNOWN_MISSING_NATIVE_SIGNAL_PROOF"
    stop = normalized["native_stop"]
    fields = stop.get("fields") if type(stop) is dict else None
    if type(fields) is not dict or fields.get("reason") != "signal-received" or fields.get("signal-name") != "SIGINT":
        return "UNKNOWN_MISSING_NATIVE_SIGNAL_PROOF"
    return "NATIVE_SIGNAL_OBSERVED"


def _q02() -> dict[str, Any]:
    capture = _strict_json(TRANSCRIPT_PATH.read_bytes(), "retained GDB transcript")
    found: list[dict[str, Any]] = []
    _walk_command_outputs(capture, "target remote 127.0.0.1:65520", found)
    exact = [item for item in found if item.get("output") == "Remote debugging using 127.0.0.1:65520\n0x0000057c in ?? ()\n[Stopped: in ??]\n"]
    normalized = [_normalize_legacy_capture(item) for item in exact]
    admitted = [_captured_signal_admission(item) for item in normalized]
    _assert("Q02", "capture_hash", _sha256(TRANSCRIPT_PATH) == TRANSCRIPT_SHA256, "retained transcript pin differs")
    _assert("Q02", "formatted_attach_is_unknown", len(exact) == 1 and normalized[0] is not None and normalized[0]["error"] is False and admitted == ["UNKNOWN_MISSING_NATIVE_SIGNAL_PROOF"], "saved formatted attach passed native-stop admission without a raw event", {"found": found, "normalized": normalized, "admission": admitted})
    _assert("Q02", "no_native_signal_field", all(item is not None and item["native_stop"] is None and not item["formatted_signal_mentions"] for item in normalized), "formatted output was upgraded to native signal proof", normalized)
    return _case("Q02", {"subcontrols": _passed_controls("Q02"), "classification": admitted[0], "record_count": len(exact)})


def _q03() -> dict[str, Any]:
    event = {"raw": '*stopped,reason="signal-received",signal-name="SIGINT"', "sequence": 7}
    left_cause = "attach-001"
    right_cause = "continue-999"
    left = _event_only(event, left_cause)
    right = _event_only(event, right_cause)
    _assert("Q03", "same_raw_event", left["raw"] == right["raw"], "hypothetical cause changed raw input")
    _assert("Q03", "different_hypothetical_cause", left_cause != right_cause, "causal negative control is not distinct", {"left": left_cause, "right": right_cause})
    _assert("Q03", "same_event_only_classification", left == right and left["observation"] == "SESSION_EVENT_ONLY" and "cause_command_id" not in left, "indistinguishable stream was assigned a causal command", {"left": left, "right": right})
    return _case("Q03", {"subcontrols": _passed_controls("Q03"), "left": left, "right": right})


def _baseline_oracle(payload: Any, *, marker: str = "~", duplicates: int = 1, result: Any = None, result_token: str = "901", generation_stable: bool = True) -> str:
    if duplicates != 1:
        return "REJECT_AMBIGUOUS"
    if marker != "~" or payload is None:
        return "REJECT_OR_MISSING_PAYLOAD"
    if result_token != "901":
        return "REJECT_BINDING"
    if type(result) is not dict or result.get("class") == "error":
        return "UNKNOWN_BASELINE"
    if result.get("class") != "done":
        return "UNKNOWN_BASELINE"
    if not generation_stable:
        return "REJECT_INVALIDATED"
    if type(payload) is str:
        try:
            payload = _strict_json(payload.encode("utf-8"), "baseline fixture payload")
        except (UnicodeError, ValueError, TypeError):
            return "REJECT_SCHEMA"
    required = {"schema", "owner_id", "session_id", "generation", "nonce", "connection_count"}
    if type(payload) is not dict or set(payload) != required:
        return "REJECT_SCHEMA"
    expected = {"schema": "ladybug.feat010.connection-baseline.v1", "owner_id": "sro-owner", "session_id": "sro-session", "generation": 1, "nonce": "sro-baseline-query-001"}
    if any(type(payload.get(key)) is not type(value) or payload.get(key) != value for key, value in expected.items()):
        return "REJECT_BINDING"
    count = payload.get("connection_count")
    if type(count) is not int:
        return "REJECT_SCHEMA"
    if count != 0:
        return "REJECT_BASELINE"
    return "ACCEPT_BASELINE"


def _q05(fixtures: dict[str, Any]) -> dict[str, Any]:
    spec = fixtures["baseline"]
    expected = spec["expected_payload"]
    expected_ids = tuple(item["id"] for item in spec["controls"])
    fixture_ids_valid = expected_ids == tuple(["BASELINE_ZERO"] + [
        "CONNECTION_WITHOUT_THREADS", "COUNT_BOOLEAN", "COUNT_STRING", "COUNT_NULL", "COUNT_MISSING",
        "STALE_NONCE", "WRONG_OWNER", "WRONG_SESSION", "WRONG_GENERATION", "WRONG_STREAM",
        "DUPLICATE_PAYLOAD", "MALFORMED_JSON", "TRUNCATED_JSON", "PYTHON_UNAVAILABLE", "API_UNAVAILABLE",
        "MI_ERROR", "WRONG_RESULT_TOKEN", "INVALIDATED_GENERATION",
    ])
    mutations: dict[str, tuple[Any, dict[str, Any]]] = {}
    def changed(control: str, key: str, value: Any) -> None:
        payload = dict(expected); payload[key] = value; mutations[control] = (payload, {})
    changed("CONNECTION_WITHOUT_THREADS", "connection_count", 1)
    changed("COUNT_BOOLEAN", "connection_count", False)
    changed("COUNT_STRING", "connection_count", "0")
    changed("COUNT_NULL", "connection_count", None)
    payload = dict(expected); del payload["connection_count"]; mutations["COUNT_MISSING"] = (payload, {})
    changed("STALE_NONCE", "nonce", "sro-baseline-query-old")
    changed("WRONG_OWNER", "owner_id", "other-owner")
    changed("WRONG_SESSION", "session_id", "other-session")
    changed("WRONG_GENERATION", "generation", 2)
    mutations["WRONG_STREAM"] = (dict(expected), {"marker": "@"})
    mutations["DUPLICATE_PAYLOAD"] = (dict(expected), {"duplicates": 2})
    mutations["MALFORMED_JSON"] = ("{bad", {})
    mutations["TRUNCATED_JSON"] = ("{\"schema\":", {})
    mutations["PYTHON_UNAVAILABLE"] = (dict(expected), {"result": {"class": "error"}})
    mutations["API_UNAVAILABLE"] = (dict(expected), {"result": {"class": "error", "msg": "AttributeError"}})
    mutations["MI_ERROR"] = (dict(expected), {"result": {"class": "error"}})
    mutations["WRONG_RESULT_TOKEN"] = (dict(expected), {"result_token": "902"})
    mutations["INVALIDATED_GENERATION"] = (dict(expected), {"generation_stable": False})
    subcontrol_by_fixture = {
        "BASELINE_ZERO": "baseline-zero", "CONNECTION_WITHOUT_THREADS": "baseline-connection",
        "COUNT_BOOLEAN": "baseline-bool", "COUNT_STRING": "baseline-string", "COUNT_NULL": "baseline-null",
        "COUNT_MISSING": "baseline-missing", "STALE_NONCE": "baseline-nonce", "WRONG_OWNER": "baseline-owner",
        "WRONG_SESSION": "baseline-session", "WRONG_GENERATION": "baseline-generation", "WRONG_STREAM": "baseline-stream",
        "DUPLICATE_PAYLOAD": "baseline-duplicate", "MALFORMED_JSON": "baseline-malformed", "TRUNCATED_JSON": "baseline-truncated",
        "PYTHON_UNAVAILABLE": "baseline-python", "API_UNAVAILABLE": "baseline-api", "MI_ERROR": "baseline-mi-error",
        "WRONG_RESULT_TOKEN": "baseline-token", "INVALIDATED_GENERATION": "baseline-invalidated",
    }
    for control in spec["controls"]:
        cid = control["id"]
        if cid == "BASELINE_ZERO":
            observed = _baseline_oracle(dict(expected), result={"class": "done"})
        else:
            payload, options = mutations[cid]
            observed = _baseline_oracle(payload, result=options.pop("result", {"class": "done"}), **options)
        wanted = control["expected"]
        condition = observed == wanted
        if cid == "BASELINE_ZERO":
            condition = condition and observed == "ACCEPT_BASELINE" and fixture_ids_valid
        _assert("Q05", subcontrol_by_fixture[cid], condition, "independent baseline control differs from its expected decoder disposition", {"id": cid, "expected": wanted, "observed": observed})
    controls = _passed_controls("Q05")
    return _case("Q05", {"subcontrols": controls, "fixture_control_ids": list(expected_ids), "strict_zero_only": True, "positive_zero_observed": True})


def _launch_argv_matches(argv: Any) -> bool:
    return type(argv) is list and all(type(item) is str for item in argv) and argv == list(PINNED_LAUNCH_ARGV)


def _q04(context: dict[str, Any], host_claim: dict[str, Any]) -> dict[str, Any]:
    helper = _load_historical_helpers(context)
    hooks = helper.DenyHooks()
    async def fake_factory(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("Q containment oracle must never admit a real factory call")
    hooks.install(fake_factory)
    try:
        denial = hooks.assert_popen_construction_denied("after_import")
    finally:
        hooks.restore()
    _assert("Q04", "exclusive_claim", host_claim.get("exclusive") is True, "host did not create the one-shot phase claim", host_claim)
    _assert("Q04", "collision_preserved", host_claim.get("collision_preserved") is True, "host claim collision bytes were not preserved", host_claim)
    argv = host_claim.get("launch_argv")
    expected_argv = context["fixture_data"]["stop"]["recovery_r1"]["launch_argv"]
    _assert("Q04", "pinned_allowlist", _launch_argv_matches(argv) and argv == expected_argv, "host argv differs from the independently pinned exact WSL launch vector", {"host_claim": host_claim, "fixture_argv": expected_argv})
    _assert("Q04", "popen_type_preserved", hooks.denied_popen_type is not None and issubclass(hooks.denied_popen_type, hooks.original_popen_type), "denied Popen is not type-preserving")
    _assert("Q04", "popen_denied", denial.get("denied") is True and denial.get("real_calls") == 0, "Popen escape denial did not record the exact block", denial)
    _assert("Q04", "no_real_factory", hooks.allowed_factory_calls == 0 and hooks.counts.get("subprocess.Popen") == 1, "containment oracle unexpectedly reached a child factory", hooks.counts)
    changed_argument = list(expected_argv)
    changed_argument[1] = "--shell"
    _assert("Q04", "changed_argument_rejected", not _launch_argv_matches(changed_argument), "changed launch argument was admitted", changed_argument)
    changed_path = list(expected_argv)
    changed_path[4] = WSL_STOPQ_PATH + ".changed"
    _assert("Q04", "changed_path_rejected", not _launch_argv_matches(changed_path), "changed absolute WSL script path was admitted", changed_path)
    observed = {"subcontrols": _passed_controls("Q04"), "denial": denial, "host_claim": host_claim, "old_helper_sha256": context["qualified_sha256"]["service-q.py"]}
    return _case("Q04", observed)


def _run_q(context: dict[str, Any], host_claim: dict[str, Any]) -> list[dict[str, Any]]:
    return [_q01(context), _q02(), _q03(), _q04(context, host_claim), _q05(context["fixture_data"])]


def _natural_action_sequence(context: dict[str, Any], *, continue_budget_ms: int = 1000) -> tuple[dict[str, Any], ...]:
    natural = context["fixture_data"]["natural"]
    return (
        {"kind": "attach", "command_id": "attach-001", "command": natural["attach_command"], "stop_expectation": "signal", "budget_ms": 1000},
        {"kind": "continue", "command_id": "continue-001", "command": "continue", "stop_expectation": "breakpoint", "expected_breakpoint": natural["expected_breakpoint"], "budget_ms": continue_budget_ms},
    )


def _full_probe(context: dict[str, Any], **options: Any) -> dict[str, Any]:
    options.setdefault("action_sequence", _natural_action_sequence(context))
    return asyncio.run(_claim_probe_async(context, **options))


def _action(run: dict[str, Any], index: int) -> Any:
    actions = run.get("actions")
    return actions[index] if type(actions) is list and len(actions) > index else None


def _observation_call_ids(session: Any) -> list[str]:
    return [str(item.get("call_id")) for item in session._observation_call_ledger if type(item) is dict]


def _run_r07(context: dict[str, Any]) -> dict[str, Any]:
    natural, stop = context["fixture_data"]["natural"], context["fixture_data"]["stop"]
    missing_signal = stop["attach"]["raw_event"].replace('signal-name="SIGINT",', '')
    missing = asyncio.run(_claim_probe_async(
        context,
        action_sequence=({"kind": "attach", "command_id": "attach-001", "command": natural["attach_command"], "stop_expectation": "signal", "budget_ms": 1000},),
        action_events={"attach": [missing_signal]},
    ))
    valid = _full_probe(context)
    attach = _action(missing, 0)
    continuation = _action(valid, 1)
    _assert("R07", "attach_missing_sigint_unknown", type(attach) is dict and attach.get("state") == "UNKNOWN" and "signal-name" not in attach.get("stop_record", {}).get("fields", {}) and attach.get("validated_stop") is None, "attach without the native signal-name field was not left unknown", attach)
    _assert("R07", "continue_without_signal_valid_breakpoint", type(continuation) is dict and continuation.get("state") == "VALIDATED_OBSERVATION" and continuation.get("stop_record", {}).get("fields", {}).get("reason") == "breakpoint-hit" and continuation.get("stop_record", {}).get("fields", {}).get("disp") == stop["continuation"]["expected_disposition"], "valid breakpoint stop incorrectly required SIGINT", continuation)
    _assert("R07", "event_only", continuation.get("stop_observation") == "SESSION_EVENT_ONLY" and "cause_command_id" not in continuation and continuation.get("validated_stop", {}).get("observation") == "SESSION_EVENT_ONLY", "event-only classification attributed the event to the command", continuation)
    return _case("R07", {"subcontrols": _passed_controls("R07"), "missing_signal_probe": attach, "valid_breakpoint_probe": continuation, "cleanup": [missing["cleanup"], valid["cleanup"]]})


def _run_r08(context: dict[str, Any]) -> dict[str, Any]:
    stop = context["fixture_data"]["stop"]
    wrong = _full_probe(context, breakpoint_body=stop["continuation"]["raw_breakpoint_result_body"].replace('number="2"', 'number="3"'))
    disabled = _full_probe(context, breakpoint_body=stop["continuation"]["raw_breakpoint_result_body"].replace('enabled="y"', 'enabled="n"'))
    empty = _full_probe(context, breakpoint_body='^done,BreakpointTable={nr_rows="0",body=[]}')
    missing = _full_probe(context, transaction_fault_by_kind={"pre-continue-break-list": "missing-result"})
    results = [_action(run, 1) for run in (wrong, disabled, empty, missing)]
    for label, result in zip(("wrong_breakpoint", "disabled_breakpoint", "missing_breakpoint", "missing_query"), results):
        _assert("R08", label, type(result) is dict and result.get("state") == "UNKNOWN" and result.get("validated_stop") is None, "continuation proceeded without a valid pre-resume breakpoint query", result)
    write_ids = [_observation_call_ids(run["session"]) for run in (wrong, disabled, empty, missing)]
    _assert("R08", "no_continue_write", all("continue-001" not in ids for ids in write_ids) and all(run["world"].action_count == 1 for run in (wrong, disabled, empty, missing)), "continue was written after a wrong, disabled, empty, or missing breakpoint query", {"call_ids": write_ids, "action_counts": [run["world"].action_count for run in (wrong, disabled, empty, missing)]})
    return _case("R08", {"subcontrols": _passed_controls("R08"), "wrong": results[0], "disabled": results[1], "empty": results[2], "missing_query": results[3], "call_ids": write_ids})


def _run_r09(context: dict[str, Any]) -> dict[str, Any]:
    stop = context["fixture_data"]["stop"]
    wrong_number = _full_probe(context, action_events={"continue": [stop["continuation"]["raw_event"].replace('bkptno="2"', 'bkptno="9"')]})
    wrong_thread = _full_probe(context, action_events={"continue": [stop["continuation"]["raw_event"].replace('thread-id="1"', 'thread-id="2"')]})
    wrong_pc = _full_probe(context, action_events={"continue": [stop["continuation"]["raw_event"].replace('addr="0x00000350"', 'addr="0x00000351"')]})
    running_body = stop["continuation"]["raw_state_result_body"].replace('state="stopped"', 'state="running"')
    running = _full_probe(context, state_body_override={"post-continue-thread-info": running_body})
    unsupported_body = stop["continuation"]["raw_state_result_body"].replace('state="stopped"', 'state="exited"')
    unsupported = _full_probe(context, state_body_override={"post-continue-thread-info": unsupported_body})
    changed = _full_probe(context, inject_state_change_on={"post-continue-thread-info"})
    results = [_action(run, 1) for run in (wrong_number, wrong_thread, wrong_pc, running, unsupported, changed)]
    for label, result in zip(("wrong_hit_number", "wrong_thread", "wrong_pc", "running_state", "unsupported_state", "generation_change"), results):
        _assert("R09", label, type(result) is dict and result.get("state") == "UNKNOWN" and result.get("validated_stop") is None, "invalid fresh stop state was admitted", result)
    return _case("R09", {"subcontrols": _passed_controls("R09"), "negative_results": results, "cleanup": [run["cleanup"] for run in (wrong_number, wrong_thread, wrong_pc, running, unsupported, changed)]})


def _run_r10(context: dict[str, Any]) -> dict[str, Any]:
    run = _full_probe(context)
    result = _action(run, 1)
    calls = [call for call in run["session"]._observation_call_ledger if type(call) is dict]
    break_calls = [call for call in calls if call.get("call_id") == "continue-001:breakpoint-before"]
    _assert("R10", "enabled_pre_resume", len(break_calls) == 1 and break_calls[0].get("result", {}).get("fields", {}).get("BreakpointTable", {}).get("body", [])[0].get("value", {}).get("enabled") == "y", "pre-resume query did not prove the enabled expected breakpoint", break_calls)
    _assert("R10", "expected_disposition", len(break_calls) == 1 and break_calls[0].get("result", {}).get("fields", {}).get("BreakpointTable", {}).get("body", [])[0].get("value", {}).get("disp") == "del", "pre-resume query did not bind temporary-breakpoint disposition", break_calls)
    _assert("R10", "deleted_after_hit_allowed", type(result) is dict and result.get("state") == "VALIDATED_OBSERVATION" and result.get("stop_record", {}).get("fields", {}).get("disp") == "del" and len(break_calls) == 1, "temporary breakpoint deletion after the hit was incorrectly required to persist", {"result": result, "breakpoint_calls": len(break_calls)})
    _assert("R10", "fresh_pc", type(result) is dict and result.get("current_state", {}).get("pc") == "0x00000350" and result.get("validated_stop", {}).get("thread_id") == "1", "fresh thread query did not confirm the breakpoint PC and thread", result.get("current_state"))
    return _case("R10", {"subcontrols": _passed_controls("R10"), "result": result, "pre_resume_breakpoint": break_calls[0], "cleanup": run["cleanup"]})


def _run_r11(context: dict[str, Any]) -> dict[str, Any]:
    stop = context["fixture_data"]["stop"]
    event = stop["continuation"]["raw_event"]
    multiple = _full_probe(context, action_events={"continue": [event, event]})
    delayed = _full_probe(
        context,
        action_event_delay_by_kind={"continue": 0.2},
        action_sequence=_natural_action_sequence(context, continue_budget_ms=50),
    )
    foreign = asyncio.run(_claim_probe_async(
        context,
        action_sequence=({"kind": "attach", "command_id": "attach-foreign", "command": context["fixture_data"]["natural"]["attach_command"], "stop_expectation": "signal", "budget_ms": 1000, "owner_id": "other-owner", "expect_exception": True},),
    ))
    multiple_result = _action(multiple, 1)
    delayed_result = _action(delayed, 1)
    late = delayed["world"].late_action_events
    _assert("R11", "multiple_stops_ambiguous", type(multiple_result) is dict and multiple_result.get("state") == "UNKNOWN" and len([record for record in multiple["session"]._observation_stops if record.get("fields", {}).get("reason") == "breakpoint-hit"]) == 2, "multiple candidate stop events were not rejected as ambiguous", multiple_result)
    _assert("R11", "delayed_event_after_invalidation", type(delayed_result) is dict and delayed_result.get("state") == "UNKNOWN" and bool(late) and late[-1].get("invalidated_before_delivery") is True and delayed["session"]._observation_invalidated, "late stop event revived an invalidated observation", {"result": delayed_result, "late_events": late})
    _assert("R11", "wrong_owner_no_write", foreign["actions"][0].get("raised") == "GdbError" and foreign["actions"][0].get("message") == "OWNER_SESSION_MISMATCH_OR_NOT_ACTIVE" and foreign["action_write_deltas"] == [0] and len(foreign["process"].stdin.writes) == 1, "wrong-owner request wrote to the observed GDB stream", {"action": foreign["actions"], "write_deltas": foreign["action_write_deltas"]})
    return _case("R11", {"subcontrols": _passed_controls("R11"), "multiple_stops": multiple_result, "delayed_event": {"result": delayed_result, "late_events": late}, "wrong_owner": foreign["actions"][0], "cleanup": [multiple["cleanup"], delayed["cleanup"], foreign["cleanup"]]})


def _run_r12(context: dict[str, Any]) -> dict[str, Any]:
    natural = context["fixture_data"]["natural"]
    pre_send = asyncio.run(_claim_probe_async(context, preclaim="send"))
    pre_interrupt = asyncio.run(_claim_probe_async(context, preclaim="interrupt"))
    pending = asyncio.run(_claim_probe_async(context, claim_pending_race=True))
    replay = asyncio.run(_claim_probe_async(context, repeat_claim=True, postclaim_legacy_probes=True))
    reader = replay["process"].stdout
    observation_readers = len({task for task, role in reader._reader_task_roles.items() if role == "observation"})
    _assert("R12", "activity_before_claim", pre_send["claim"] is None and pre_interrupt["claim"] is None and "LEGACY_ACTIVITY_PREVENTS_FRESH_CLAIM" in (pre_send["preclaim_error"] or "") and "LEGACY_ACTIVITY_PREVENTS_FRESH_CLAIM" in (pre_interrupt["preclaim_error"] or ""), "legacy activity before claim was admitted into the fresh observer", {"send": pre_send["preclaim_error"], "interrupt": pre_interrupt["preclaim_error"]})
    _assert("R12", "claim_pending_gate", pending["pending_race"].get("state") == "claim-pending" and "GdbError:" in pending["pending_race"].get("send_error", "") and "GdbError:" in pending["pending_race"].get("interrupt_error", "") and pending["pending_race"].get("legacy_writes_before") == pending["pending_race"].get("legacy_writes_after") and pending["claim"].get("state") == "CLAIMED", "synchronous claim-pending transition did not reject both legacy paths before I/O", pending["pending_race"])
    _assert("R12", "postclaim_send_rejected", "GdbError:" in replay["postclaim_legacy"].get("send_error", "") and replay["postclaim_legacy"].get("writes_before") == replay["postclaim_legacy"].get("writes_after"), "post-claim legacy send was not rejected before a stream write", replay["postclaim_legacy"])
    _assert("R12", "postclaim_interrupt_rejected", "GdbError:" in replay["postclaim_legacy"].get("interrupt_error", "") and replay["session"]._legacy_interrupt_history == 0, "post-claim legacy interrupt was not rejected before signaling", replay["postclaim_legacy"])
    detached = replay["pending_race"].get("detached_claim_proof")
    _assert("R12", "repeat_claim", type(replay["replay_claim"]) is dict and replay["replay_claim"].get("generation") == replay["claim"].get("generation") == natural["observation_generation"] and replay["replay_claim"].get("state") == "CLAIMED" and replay["pending_race"].get("writes_before_replay") == replay["pending_race"].get("writes_after_replay") and type(detached) is dict and detached.get("first_claim_snapshot") is True and detached.get("replay_snapshot") is True and detached.get("journal_unchanged") is True and detached.get("retained_journal_unchanged") is True, "identical claim replay changed generation, repeated baseline I/O, or exposed mutable retained proof", {"first_generation": replay["claim"].get("generation"), "replay_generation": replay["replay_claim"].get("generation") if type(replay["replay_claim"]) is dict else None, "writes": {"before": replay["pending_race"].get("writes_before_replay"), "after": replay["pending_race"].get("writes_after_replay")}, "detached": detached})
    _assert("R12", "single_reader", observation_readers == 1 and reader._max_active_readers == 1 and not reader._overlaps and replay["session"]._observation_task is not None, "claim replay created overlapping or duplicate observer readers", {"reader_ids": list(reader._reader_task_ids), "roles": reader._reader_task_roles, "overlaps": reader._overlaps})
    _assert("R12", "zero_legacy_delta", replay["session"]._legacy_send_history == 0 and replay["session"]._legacy_interrupt_history == 0 and replay["postclaim_legacy"].get("writes_before") == replay["postclaim_legacy"].get("writes_after"), "claim replay or rejected legacy calls changed legacy activity state", replay["postclaim_legacy"])
    return _case("R12", {"subcontrols": _passed_controls("R12"), "preclaim": {"send": pre_send["preclaim_error"], "interrupt": pre_interrupt["preclaim_error"]}, "claim_pending": pending["pending_race"], "replay": replay["replay_claim"], "postclaim_legacy": replay["postclaim_legacy"], "reader_ids": list(reader._reader_task_ids), "cleanup": [pre_send["cleanup"], pre_interrupt["cleanup"], pending["cleanup"], replay["cleanup"]]})


def _run_r13(context: dict[str, Any]) -> dict[str, Any]:
    record_limit = asyncio.run(_claim_probe_async(context, flood_baseline_records=8193))
    byte_limit = asyncio.run(_claim_probe_async(context, flood_baseline_bytes=1024 * 1024 + 1))
    record_session, byte_session = record_limit["session"], byte_limit["session"]
    record_overflow = record_session._observation_overflow_evidence if record_session is not None else None
    byte_overflow = byte_session._observation_overflow_evidence if byte_session is not None else None
    _assert("R13", "record_cap", record_session is not None and record_session._observation_record_count > 8192 and type(record_overflow) is dict and record_overflow.get("sequence") == 8193, "record cap did not retain first overflow evidence", {"count": record_session._observation_record_count if record_session else None, "overflow": record_overflow})
    _assert("R13", "byte_cap", byte_session is not None and byte_session._observation_byte_count > 1024 * 1024 and type(byte_overflow) is dict and byte_overflow.get("length", 0) > 1024 * 1024, "byte cap did not retain first over-limit record", {"count": byte_session._observation_byte_count if byte_session else None, "overflow": byte_overflow})
    _assert("R13", "tainted", record_session is not None and byte_session is not None and record_session._observation_tainted and byte_session._observation_tainted and record_session._observation_invalidated is True and byte_session._observation_invalidated is True, "overflow failed to taint and invalidate the observation", {"record": record_session._observation_state if record_session else None, "byte": byte_session._observation_state if byte_session else None})
    _assert("R13", "first_overflow_retained", record_overflow is not None and byte_overflow is not None and record_overflow == record_session._observation_overflow_evidence and byte_overflow == byte_session._observation_overflow_evidence, "first overflow record was overwritten", {"record": record_overflow, "byte": byte_overflow})
    record_first = record_session._observation_records[0] if record_session is not None and record_session._observation_records else None
    _assert("R13", "no_eviction", record_session is not None and byte_session is not None and len(record_session._observation_records) == 8192 and len(byte_session._observation_records) == 0 and type(record_first) is dict and record_first.get("kind") == "mi" and record_first.get("marker") == "~" and record_first.get("sequence") == 1, "bounded raw record retention evicted prior evidence or retained an over-limit first record", {"record_count": len(record_session._observation_records) if record_session else None, "record_first": record_first, "byte_count": len(byte_session._observation_records) if byte_session else None})
    return _case("R13", {"subcontrols": _passed_controls("R13"), "record_overflow": record_overflow, "byte_overflow": byte_overflow, "record_retained": len(record_session._observation_records), "byte_retained": len(byte_session._observation_records), "cleanup": [record_limit["cleanup"], byte_limit["cleanup"]]})


def _run_r14(context: dict[str, Any]) -> dict[str, Any]:
    natural = context["fixture_data"]["natural"]
    attach = ({"kind": "attach", "command_id": "attach-001", "command": natural["attach_command"], "stop_expectation": "signal", "budget_ms": 50},)
    operation_lock = asyncio.run(_claim_probe_async(context, action_sequence=attach, held_observation_lock="operation"))
    transaction_lock = asyncio.run(_claim_probe_async(context, action_sequence=attach, held_observation_lock="transaction"))
    drain = asyncio.run(_claim_probe_async(context, action_sequence=attach, drain_delay_by_kind={"pre-attach-thread-info": 0.2}))
    read = asyncio.run(_claim_probe_async(context, action_sequence=attach, block_reader_after_claim=True, join_blocked_reader_after_stop=True))
    query = asyncio.run(_claim_probe_async(context, action_sequence=attach, response_delay_by_kind={"pre-attach-thread-info": 0.2}))
    results = [run["actions"][0] for run in (operation_lock, transaction_lock, drain, read, query)]
    _assert("R14", "operation_lock", type(results[0]) is dict and results[0].get("state") == "UNKNOWN" and len(operation_lock["process"].stdin.writes) == 1 and operation_lock["process"].stdin.writes[0].startswith(b"1-interpreter-exec console ") and operation_lock["world"].action_count == 0, "operation-lock wait exceeded its one action deadline or wrote an action", {"result": results[0], "write_count": len(operation_lock["process"].stdin.writes), "action_count": operation_lock["world"].action_count})
    _assert("R14", "transaction_lock", type(results[1]) is dict and results[1].get("state") == "UNKNOWN" and len(transaction_lock["process"].stdin.writes) == 1 and transaction_lock["world"].action_count == 0, "transaction-lock wait admitted a late query or action", {"result": results[1], "writes": transaction_lock["process"].stdin.writes})
    _assert("R14", "drain", type(results[2]) is dict and results[2].get("state") == "UNKNOWN" and len(drain["process"].stdin.writes) == 2 and drain["world"].action_count == 0 and drain["session"]._observation_invalidated, "delayed stdin drain exceeded the one query deadline without invalidation", {"result": results[2], "writes": drain["process"].stdin.writes})
    _assert("R14", "read", type(results[3]) is dict and results[3].get("state") == "UNKNOWN" and read["cleanup"].get("cleanup_complete") is False and read["later_reader_join"] is True, "blocked observer read was reported complete before the later bounded join", {"result": results[3], "cleanup": read["cleanup"], "later_join": read["later_reader_join"]})
    _assert("R14", "query", type(results[4]) is dict and results[4].get("state") == "UNKNOWN" and query["session"]._observation_invalidated and query["world"].late_replies and query["world"].late_replies[-1].get("invalidated_before_delivery") is True, "delayed query reply was admitted after its enclosing deadline", {"result": results[4], "late_replies": query["world"].late_replies})
    _assert("R14", "no_late_admission", all(type(result) is dict and result.get("state") == "UNKNOWN" and result.get("validated_stop") is None for result in results) and all(run["world"].action_count == 0 for run in (operation_lock, transaction_lock, drain, read, query)), "a lock, drain, read, or query timeout admitted a late action", {"results": results, "action_counts": [run["world"].action_count for run in (operation_lock, transaction_lock, drain, read, query)]})
    return _case("R14", {"subcontrols": _passed_controls("R14"), "results": results, "cleanup": [run["cleanup"] for run in (operation_lock, transaction_lock, drain, read, query)], "late_replies": query["world"].late_replies})


def _run_r15(context: dict[str, Any]) -> dict[str, Any]:
    lost = asyncio.run(_claim_probe_async(context, transaction_fault="missing-result"))
    pending = _full_probe(context, response_delay_by_kind={"continue": 0.2}, stop_during_pending_command=True)
    result = _action(pending, 1)
    lease = pending["world"].manager._owned_leases.get(context["fixture_data"]["natural"]["owner_id"])
    late_replies = pending["world"].late_replies
    _assert("R15", "lost_claim_reply", type(lost["claim"]) is dict and lost["claim"].get("state") == "UNKNOWN" and lost["claim"].get("baseline_validated") is False and lost["session"]._observation_invalidated, "claim without a matching MI result was not retained as unknown", lost["claim"])
    _assert("R15", "owner_retained", lease is not None and lease.session is pending["session"] and pending["session"]._observation_task is not None, "owner-addressable session or observer handle was lost during stop", {"lease": type(lease).__name__ if lease else None, "session_id": pending["session"].id if pending["session"] else None})
    _assert("R15", "pending_command_invalidated", type(result) is dict and result.get("state") == "UNKNOWN" and pending["session"]._observation_invalidated and pending["session"]._observation_state in ("closed", "stopping", "invalid"), "stop did not invalidate the in-flight owned command", result)
    _assert("R15", "cleanup_confirmed", type(pending["cleanup"]) is dict and pending["cleanup"].get("process_exit_confirmed") is True and pending["cleanup"].get("reader_exit_confirmed") is True and pending["cleanup"].get("cleanup_complete") is True and pending["cleanup"].get("returncode") == 0, "observed stop did not separately confirm process and reader cleanup", pending["cleanup"])
    _assert("R15", "late_reply_no_revival", bool(late_replies) and late_replies[-1].get("invalidated_before_delivery") is True and pending["session"]._observation_invalidated and result.get("state") != "VALIDATED_OBSERVATION", "late owned-command reply revived a stopped observation", {"late_replies": late_replies, "result": result})
    return _case("R15", {"subcontrols": _passed_controls("R15"), "lost_claim": lost["claim"], "pending_command": result, "late_replies": late_replies, "cleanup": {"lost_claim": lost["cleanup"], "pending": pending["cleanup"]}})


def _run_r16(context: dict[str, Any]) -> dict[str, Any]:
    run = asyncio.run(_claim_probe_async(context, block_reader_after_claim=True, stop_budget_ms=100, join_blocked_reader_after_stop=True))
    session, process, cleanup = run["session"], run["process"], run["cleanup"]
    retained = run["registry_retained_after_first_stop"] is True
    _assert("R16", "process_exit_true", type(cleanup) is dict and cleanup.get("process_exit_confirmed") is True and cleanup.get("returncode") == 0 and process is not None and process.wait_calls == 1, "short stop phase did not directly confirm process exit", cleanup)
    _assert("R16", "reader_exit_false", type(cleanup) is dict and cleanup.get("reader_exit_confirmed") is False and session is not None and run["reader_task_done_at_first_stop"] is False and run["reader_eof_at_first_stop"] is False, "blocked reader was reported exited before release", {"cleanup": cleanup, "task_done_at_first_stop": run["reader_task_done_at_first_stop"], "eof_at_first_stop": run["reader_eof_at_first_stop"]})
    _assert("R16", "cleanup_false", type(cleanup) is dict and cleanup.get("cleanup_complete") is False, "cleanup was reported complete while the reader remained blocked", cleanup)
    _assert("R16", "registry_retained", retained and session is not None and session._observation_task is not None and run["reader_task_done_at_first_stop"] is False and run["later_reader_join"] is True, "exit callback removed the direct reader handle before its later join", {"retained_after_stop": retained, "task_done_at_first_stop": run["reader_task_done_at_first_stop"], "later_join": run["later_reader_join"]})
    _assert("R16", "later_reader_join", run["later_reader_join"] is True and session._observation_eof is True and session._observation_task.done(), "reader handle was not directly joined after releasing the controlled block", {"later_join": run["later_reader_join"], "reader_eof": session._observation_eof if session else None})
    return _case("R16", {"subcontrols": _passed_controls("R16"), "first_stop": cleanup, "later_reader_join": run["later_reader_join"], "registry_retained": retained, "process_events": process.events if process else []})


async def _actual_fixture_setup(context: dict[str, Any], *, world_options: dict[str, Any] | None = None) -> dict[str, Any]:
    helper = _load_historical_helpers(context)
    world = helper.World()
    await world.reset(**(world_options or {}))
    hooks = helper.DenyHooks()
    hooks.install(world.factory)
    gdb: ModuleType | None = None
    server: ModuleType | None = None
    original_uuid: Any = None
    ledger = _ActualLedger()
    try:
        # Import the copied subject only after process and network denials are active.
        gdb, server = _load_actual_service()
        original_uuid = gdb.uuid
        for owner, names in (
            (gdb.GdbManager, ("create", "remove", "start_owned_session", "stop_session_by_owner", "claim_observed_session", "exec_owned_session", "stop_observed_session")),
            (gdb.GdbSession, ("send", "_close_until", "_wait_for_direct_child", "_baseline_until", "_observation_reader", "stop_observed_until")),
            (server, ("start_session", "exec_command", "stop_session", "start_owned_session", "stop_session_by_owner", "claim_observed_session", "exec_owned_session", "stop_observed_session")),
        ):
            for name in names:
                if hasattr(owner, name):
                    ledger.wrap_async(owner, name, getattr(owner, "__name__", "server") + "." + name)
        manager = gdb.GdbManager()
        server.manager = manager
        world.manager = manager
        return {"helper": helper, "world": world, "hooks": hooks, "gdb": gdb, "server": server, "manager": manager, "ledger": ledger, "original_uuid": original_uuid}
    except BaseException:
        hooks.restore()
        if gdb is not None and original_uuid is not None:
            gdb.uuid = original_uuid
        raise


async def _actual_fixture_finish(fixture: dict[str, Any], session: Any = None) -> None:
    try:
        world = fixture["world"]
        if session is not None and session.process.returncode is None:
            session.process.finish(0)
        for process in getattr(world, "processes", []):
            if process.returncode is None:
                process.finish(0)
        wait_task = getattr(session, "_wait_task", None) if session is not None else None
        if wait_task is not None and not wait_task.done():
            done, _pending = await asyncio.wait({wait_task}, timeout=1.0)
            if not done:
                raise QualificationFailure(_CURRENT_CASE_ID, CASE_SUBCONTROLS[_CURRENT_CASE_ID][-1], "source-only fixture direct wait did not finish after controlled fake exit", category="CLEANUP")
    finally:
        fixture["hooks"].restore()
        if fixture.get("original_uuid") is not None:
            fixture["gdb"].uuid = fixture["original_uuid"]


def _run_c01(context: dict[str, Any]) -> dict[str, Any]:
    async def run() -> tuple[dict[str, Any], Any, Any, Any, Any, Any]:
        fixture = await _actual_fixture_setup(context)
        session = None
        try:
            server, manager, world = fixture["server"], fixture["manager"], fixture["world"]
            started = await server.start_session()
            sid = started.get("session_id") if type(started) is dict else None
            session = manager.get(sid) if type(sid) is str else None
            output = await server.exec_command(sid, "info version")
            stopped = await server.stop_session(sid)
            process = session.process if session is not None else None
            return fixture, started, output, stopped, process, session
        finally:
            await _actual_fixture_finish(fixture, session)

    fixture, started, output, stopped, process, session = asyncio.run(run())
    _capture_run(fixture["world"], fixture["ledger"].rows, session, fixture["hooks"])
    _assert("C01", "legacy_start_schema", type(started) is dict and set(started) == {"session_id", "binary"} and type(started.get("session_id")) is str, "legacy start response schema changed", started)
    _assert("C01", "legacy_send", type(output) is str, "legacy command response stopped being a string", {"type": type(output).__name__})
    _assert("C01", "legacy_stop_schema", stopped == {"stopped": True}, "graceful legacy stop schema or result changed", stopped)
    _assert("C01", "wait_integer_zero", process is not None and process.wait_calls == 1 and type(process.returncode) is int and process.returncode == 0, "graceful close lacked one direct integer-zero wait", {"wait_calls": process.wait_calls if process else None, "returncode": process.returncode if process else None, "returncode_type": type(process.returncode).__name__ if process else None})
    _assert("C01", "no_escalation", process is not None and process.terminate_calls == 0 and process.kill_calls == 0 and fixture["manager"]._sessions == {}, "normal legacy close escalated or retained a completed session", {"terminate_calls": process.terminate_calls if process else None, "kill_calls": process.kill_calls if process else None, "sessions": len(fixture["manager"]._sessions)})
    return _case("C01", {"subcontrols": _passed_controls("C01"), "start": started, "output_type": type(output).__name__, "stop": stopped, "direct_child": {"wait_calls": process.wait_calls, "returncode": process.returncode, "terminate_calls": process.terminate_calls, "kill_calls": process.kill_calls}, "service_call_count": len(fixture["ledger"].rows)})


def _run_c02(context: dict[str, Any]) -> dict[str, Any]:
    async def run() -> tuple[dict[str, Any], Any, Any, Any, Any, Any, bool, dict[str, Any]]:
        fixture = await _actual_fixture_setup(context, world_options={"terminate_exits": False, "kill_exits": False, "quit_exits": False})
        session = None
        try:
            server, manager = fixture["server"], fixture["manager"]
            started = await server.start_session()
            sid = started.get("session_id") if type(started) is dict else None
            session = manager.get(sid) if type(sid) is str else None
            unknown = await server.stop_session("no-such-session")
            raised: dict[str, str] | None = None
            try:
                await server.stop_session(sid)
            except BaseException as exc:
                if type(exc).__name__ != "GdbError":
                    raise
                raised = {"type": type(exc).__name__, "message": str(exc)}
            process = session.process if session is not None else None
            retained = type(sid) is str and sid in manager._sessions and process is not None and process.returncode is None
            before_release = {"returncode": process.returncode if process is not None else None, "wait_calls": process.wait_calls if process is not None else None, "terminate_calls": process.terminate_calls if process is not None else None, "kill_calls": process.kill_calls if process is not None else None}
            return fixture, started, unknown, raised, process, session, retained, before_release
        finally:
            await _actual_fixture_finish(fixture, session)

    fixture, started, unknown, raised, process, session, retained, before_release = asyncio.run(run())
    _capture_run(fixture["world"], fixture["ledger"].rows, session, fixture["hooks"])
    _assert("C02", "legacy_response_schema", type(started) is dict and set(started) == {"session_id", "binary"}, "legacy response schema changed in the unresolved-stop fixture", started)
    _assert("C02", "unknown_stop", unknown == {"stopped": False}, "unknown legacy session stop schema changed", unknown)
    _assert("C02", "unresolved_raises", type(raised) is dict and raised.get("type") == "GdbError" and "exit" in raised.get("message", "").lower(), "unconfirmed direct-child close did not raise GdbError", raised)
    _assert("C02", "registry_retained", retained and before_release == {"returncode": None, "wait_calls": 1, "terminate_calls": 1, "kill_calls": 1}, "unresolved close removed the session or invented exit", {"retained": retained, "before_fixture_release": before_release})
    _assert("C02", "fixture_released", process is not None and type(process.returncode) is int and process.returncode == 0 and session is not None and (session._wait_task is None or session._wait_task.done()), "fake direct-child wait was not released and joined after retaining the unresolved evidence", {"returncode": process.returncode if process else None, "wait_done": session._wait_task.done() if session and session._wait_task else None})
    return _case("C02", {"subcontrols": _passed_controls("C02"), "start": started, "unknown_stop": unknown, "unresolved_error": raised, "retained_before_release": retained, "direct_child": {"wait_calls": process.wait_calls, "terminate_calls": process.terminate_calls, "kill_calls": process.kill_calls, "returncode_after_release": process.returncode}, "service_call_count": len(fixture["ledger"].rows)})


def _run_c03(context: dict[str, Any]) -> dict[str, Any]:
    async def run() -> tuple[dict[str, Any], Any, Any, Any, Any, Any, Any, int, int, bool, int]:
        fixture = await _actual_fixture_setup(context)
        session = None
        try:
            helper, server, manager = fixture["helper"], fixture["server"], fixture["manager"]
            started = await server.start_session()
            sid = started["session_id"]
            session = manager.get(sid)
            process = session.process
            process.stdout.block = True
            process.stdout.release = asyncio.Event()
            process.stdin.drain = helper._delayed_drain(process, 0.40)
            writes_before = len(process.stdin.writes)
            class DelayedLock:
                def __init__(self, inner: asyncio.Lock):
                    self.inner = inner

                async def __aenter__(self) -> None:
                    await asyncio.sleep(0.35)
                    await self.inner.acquire()

                async def __aexit__(self, *_args: Any) -> None:
                    self.inner.release()

            session._lock = DelayedLock(session._lock)
            started_at = asyncio.get_running_loop().time()
            send_task = asyncio.create_task(session.send("legacy-budget", timeout=1.0))
            await asyncio.sleep(1.10)
            released_at = asyncio.get_running_loop().time()
            done_before_release = send_task.done()
            process.stdout.release.set()
            error: dict[str, str] | None = None
            try:
                await send_task
            except BaseException as exc:
                error = {"type": type(exc).__name__, "message": str(exc)}
            elapsed_ms = int((released_at - started_at) * 1000)
            writes_after = len(process.stdin.writes)
            process.stdin.drain = helper._fake_drain(process)
            second_error: dict[str, str] | None = None
            try:
                await session.send("after-timeout", timeout=1.0)
            except BaseException as exc:
                second_error = {"type": type(exc).__name__, "message": str(exc)}
            writes_after_second = len(process.stdin.writes)
            await server.stop_session(sid)
            return fixture, started, error, second_error, process, session, writes_before, writes_after, writes_after_second, elapsed_ms, done_before_release
        finally:
            process = session.process if session is not None else None
            if process is not None:
                process.stdout.release.set()
                process.stdin.drain = fixture["helper"]._fake_drain(process)
            await _actual_fixture_finish(fixture, session)

    fixture, started, error, second_error, process, session, writes_before, writes_after, writes_after_second, elapsed_ms, done_before_release = asyncio.run(run())
    _capture_run(fixture["world"], fixture["ledger"].rows, session, fixture["hooks"])
    command_writes = [value for value in process.stdin.writes[writes_before:writes_after] if value == b"legacy-budget\n"] if process else []
    _assert("C03", "one_command_write", len(command_writes) == 1 and writes_after - writes_before == 1, "one legacy request did not produce exactly one command write", {"command_write_count": len(command_writes), "write_delta": writes_after - writes_before})
    _assert("C03", "one_deadline", elapsed_ms >= 1000 and done_before_release is True and type(error) is dict and error.get("type") == "GdbError" and "deadline expired" in error.get("message", "").lower(), "lock, drain and read stages did not share the single one-second legacy deadline", {"elapsed_ms": elapsed_ms, "done_before_release": done_before_release, "error": error, "write_delta": writes_after - writes_before})
    _assert("C03", "timeout_result", session is not None and session._broken is True and type(error) is dict, "deadline failure did not taint the legacy session", {"error": error, "broken": session._broken if session else None})
    _assert("C03", "no_late_write", writes_after_second == writes_after and type(second_error) is dict and second_error.get("type") == "GdbError", "timed-out legacy session admitted a later command write", {"writes_after_timeout": writes_after, "writes_after_second": writes_after_second, "second_error": second_error})
    return _case("C03", {"subcontrols": _passed_controls("C03"), "start": started, "first_error": error, "second_error": second_error, "elapsed_ms": elapsed_ms, "done_before_release": done_before_release, "command_write_count": len(command_writes), "direct_child": {"wait_calls": process.wait_calls, "returncode": process.returncode}, "service_call_count": len(fixture["ledger"].rows)})


def _run_c04(context: dict[str, Any]) -> dict[str, Any]:
    natural = context["fixture_data"]["natural"]
    run = asyncio.run(_claim_probe_async(
        context,
        action_sequence=_natural_action_sequence(context, continue_budget_ms=1000),
        response_delay_by_kind={"continue": 0.2},
        stop_during_pending_command=True,
        repeat_stop=True,
    ))
    result = run["actions"][-1] if run["actions"] else run["action"]
    session, process = run["session"], run["process"]
    late = run["world"].late_replies
    _assert("C04", "claimed_close_invalidates", type(run["cleanup"]) is dict and run["cleanup"].get("process_exit_confirmed") is True and run["cleanup"].get("reader_exit_confirmed") is True and session is not None and session._observation_invalidated and session._observation_state in ("stopping", "closed", "invalid"), "observed close failed to invalidate and report both direct exits", {"cleanup": run["cleanup"], "state": session._observation_state if session else None})
    _assert("C04", "late_reply_rejected", type(result) is dict and result.get("state") == "UNKNOWN" and bool(late) and late[-1].get("invalidated_before_delivery") is True and session is not None and session._observation_invalidated, "late command reply was not rejected after observed close", {"result": result, "late_replies": late})
    repeated = run["repeated_cleanup"]
    _assert("C04", "repeat_stop_idempotent", type(repeated) is dict and repeated.get("process_exit_confirmed") is True and repeated.get("reader_exit_confirmed") is True and process is not None and process.wait_calls == 1, "repeated observed close duplicated child wait or lost confirmed state", {"first": run["cleanup"], "second": repeated, "wait_calls": process.wait_calls if process else None})
    reader = process.stdout if process is not None else None
    observation_ids = {task for task, role in reader._reader_task_roles.items() if role == "observation"} if reader is not None else set()
    _assert("C04", "one_reader", len(observation_ids) == 1 and reader is not None and reader._max_active_readers == 1 and not reader._overlaps, "observed close or its replay created a second reader", {"observer_task_ids": sorted(observation_ids), "max_active": reader._max_active_readers if reader else None, "overlaps": reader._overlaps if reader else None})
    _assert("C04", "separate_exit_truth", type(run["cleanup"]) is dict and type(run["cleanup"].get("process_exit_confirmed")) is bool and type(run["cleanup"].get("reader_exit_confirmed")) is bool and type(run["cleanup"].get("cleanup_complete")) is bool and run["cleanup"].get("process_exit_confirmed") is True and run["cleanup"].get("reader_exit_confirmed") is True and run["cleanup"].get("cleanup_complete") is True, "process, reader and aggregate cleanup facts were conflated", run["cleanup"])
    return _case("C04", {"subcontrols": _passed_controls("C04"), "pending_command": result, "late_replies": late, "first_stop": run["cleanup"], "repeat_stop": repeated, "reader_task_ids": sorted(observation_ids), "service_call_count": len(run["ledger"])})


def _run_c05(context: dict[str, Any]) -> dict[str, Any]:
    async def run() -> tuple[dict[str, Any], Any, Any, Any]:
        fixture = await _actual_fixture_setup(context)
        try:
            server, manager, world = fixture["server"], fixture["manager"], fixture["world"]
            owner = "sro-c05-prestart-owner"
            tombstone = await server.stop_session_by_owner(owner, budget_ms=1000)
            delayed = await server.start_owned_session(owner, budget_ms=1000)
            lease = manager._owned_leases.get(owner)
            return fixture, tombstone, delayed, lease
        finally:
            await _actual_fixture_finish(fixture)

    fixture, tombstone, delayed, lease = asyncio.run(run())
    _capture_run(fixture["world"], fixture["ledger"].rows, hooks=fixture["hooks"])
    _assert("C05", "prestart_tombstone", type(tombstone) is dict and tombstone.get("state") == "CANCELLED_BEFORE_START", "owner pre-start stop did not retain the cancellation tombstone", tombstone)
    _assert("C05", "delayed_start_rejected", type(delayed) is dict and delayed.get("state") == "CANCELLED_BEFORE_START", "later owned start escaped the pre-start cancellation tombstone", delayed)
    _assert("C05", "zero_factory", fixture["world"].factory_calls == [] and fixture["world"].processes == [], "cancelled start reached the process factory", {"factory_calls": fixture["world"].factory_calls, "process_count": len(fixture["world"].processes)})
    _assert("C05", "no_observer_reference", lease is not None and lease.session is None and lease.session_id is None and lease.spawn_task is None and lease.creation_task is None and not fixture["manager"]._sessions, "pre-start cancellation retained a child, observer or session reference", {"lease_state": lease.state if lease else None, "session": bool(lease and lease.session), "session_id": lease.session_id if lease else None, "session_count": len(fixture["manager"]._sessions)})
    return _case("C05", {"subcontrols": _passed_controls("C05"), "tombstone": tombstone, "delayed_start": delayed, "process_count": len(fixture["world"].processes), "service_call_count": len(fixture["ledger"].rows)})


PROTOCOL_LINE_LIMIT = 262144
SUPERVISOR_RESERVE_MS = 4000
FAILURE_CATEGORIES = frozenset(("ASSERTION", "SETUP", "TIMEOUT", "CONTAINMENT", "PROTOCOL", "INTERNAL", "MISSING_COVERAGE", "CLEANUP"))


class _ProtocolLineTooLarge(ValueError):
    def __init__(self, encoded: bytes) -> None:
        self.encoded_length = len(encoded)
        self.encoded_sha256 = hashlib.sha256(encoded).hexdigest()
        super().__init__("one JSON protocol record exceeded the fixed line limit")


def _bounded_protocol_value(value: Any, depth: int = 0) -> Any:
    if depth > 32:
        return {"value_truncated": True, "type": type(value).__name__}
    if value is None or type(value) in (bool, int):
        return value
    if type(value) is float:
        if value != value or value in (float("inf"), float("-inf")):
            return {"nonfinite_float": repr(value)}
        return value
    if type(value) is str:
        if len(value.encode("utf-8", errors="replace")) <= 8192:
            return value
        encoded = value.encode("utf-8", errors="replace")
        return {"text_prefix": encoded[:4096].decode("utf-8", errors="ignore"), "text_suffix": encoded[-1024:].decode("utf-8", errors="ignore"), "length_bytes": len(encoded), "sha256": hashlib.sha256(encoded).hexdigest()}
    if type(value) is bytes:
        return {"bytes_prefix_b64": base64.b64encode(value[:256]).decode("ascii"), "length": len(value), "sha256": hashlib.sha256(value).hexdigest()}
    if type(value) in (list, tuple):
        return [_bounded_protocol_value(item, depth + 1) for item in value]
    if type(value) is set:
        return [_bounded_protocol_value(item, depth + 1) for item in sorted(value, key=lambda item: str(item))]
    if type(value) is dict:
        return {str(key): _bounded_protocol_value(item, depth + 1) for key, item in value.items()}
    return {"unsupported_value_type": type(value).__name__}


_RESPONSE_PARENT_KEYS = frozenset(("action", "attach", "baseline", "claim", "continue", "current_state", "pending_command", "result", "start", "stop", "stopped", "unknown_stop"))
_RESPONSE_INDICATORS = frozenset(("baseline_validated", "cleanup_complete", "process_exit_confirmed", "reader_exit_confirmed", "stop_observation", "validated_stop"))
_RESPONSE_SUMMARY_FIELDS = frozenset((
    "baseline", "baseline_validated", "bkptno", "class", "cleanup_complete", "command_id",
    "connection_count", "disp", "error", "error_code", "exit_confirmed", "generation",
    "identity", "kind", "marker", "message", "mi_error", "observation_generation",
    "owner_id", "pc", "process_exit_confirmed", "raw", "raw_record_count", "reader_count",
    "reader_exit_confirmed", "reason", "returncode", "schema", "sequence", "session_id",
    "signal-name", "state", "state_generation_after", "state_generation_before", "status",
    "stop_observation", "stop_record", "stopped", "thread_id", "thread_state", "token",
    "validated_stop", "wait_confirmed",
))


def _compact_evidence(value: Any, parent_key: str = "", depth: int = 0) -> Any:
    if depth > 32:
        return {"value_truncated": True, "type": type(value).__name__}
    if type(value) is dict:
        is_response = parent_key in _RESPONSE_PARENT_KEYS or bool(_RESPONSE_INDICATORS.intersection(value))
        if is_response:
            canonical = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
            selected = {
                str(key): _compact_evidence(value[key], str(key), depth + 1)
                for key in _RESPONSE_SUMMARY_FIELDS if key in value
            }
            return {
                "response_evidence": {
                    "canonical_length_bytes": len(canonical),
                    "canonical_sha256": hashlib.sha256(canonical).hexdigest(),
                    "keys": sorted(str(key) for key in value),
                    "selected": selected,
                }
            }
        return {str(key): _compact_evidence(item, str(key), depth + 1) for key, item in value.items()}
    if type(value) in (list, tuple):
        return [_compact_evidence(item, parent_key, depth + 1) for item in value]
    if type(value) is set:
        return [_compact_evidence(item, parent_key, depth + 1) for item in sorted(value, key=lambda item: str(item))]
    return _bounded_protocol_value(value, depth)


def _protocol_bytes(record: dict[str, Any]) -> bytes:
    encoded = (json.dumps(record, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
    if len(encoded) > PROTOCOL_LINE_LIMIT:
        raise _ProtocolLineTooLarge(encoded)
    return encoded


def _canonical_hash(value: Any) -> tuple[int, str]:
    encoded = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return len(encoded), hashlib.sha256(encoded).hexdigest()


def _fallback_case_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": row["case_id"], "expected": row["expected"], "status": row["status"],
        "observations": _compact_evidence(row["observations"]),
    }


def _protocol_failure_fallback(result: dict[str, Any], original: _ProtocolLineTooLarge) -> dict[str, Any]:
    cases = result.get("cases") if type(result.get("cases")) is list else []
    ledgers = result.get("ledgers") if type(result.get("ledgers")) is dict else _empty_ledgers()
    service_calls = ledgers.get("service_calls") if type(ledgers.get("service_calls")) is list else []
    factory_calls = ledgers.get("factory_calls") if type(ledgers.get("factory_calls")) is list else []
    case_keep, service_keep, factory_keep = len(cases), len(service_calls), len(factory_calls)
    while True:
        omitted_cases = cases[case_keep:]
        omitted_service = service_calls[service_keep:]
        omitted_factory = factory_calls[factory_keep:]
        _case_omitted_bytes, case_omitted_hash = _canonical_hash(omitted_cases)
        _service_omitted_bytes, service_omitted_hash = _canonical_hash(omitted_service)
        _factory_omitted_bytes, factory_omitted_hash = _canonical_hash(omitted_factory)
        observed = {
            "truncated": True,
            "partial_evidence": True,
            "maximum_line_bytes": PROTOCOL_LINE_LIMIT,
            "cap_increased": False,
            "original_result_length_bytes": original.encoded_length,
            "original_result_sha256": original.encoded_sha256,
            "original_status": result.get("status"),
            "prior_failure": _compact_evidence(result.get("failure")),
            "cases": {"total": len(cases), "retained": case_keep, "omitted": len(omitted_cases), "omitted_sha256": case_omitted_hash},
            "service_calls": {"total": len(service_calls), "retained": service_keep, "omitted": len(omitted_service), "omitted_sha256": service_omitted_hash},
            "factory_calls": {"total": len(factory_calls), "retained": factory_keep, "omitted": len(omitted_factory), "omitted_sha256": factory_omitted_hash},
        }
        fallback = {
            "kind": result.get("kind"), "phase": result.get("phase"), "nonce": result.get("nonce"),
            "manifest_sha256": result.get("manifest_sha256"), "ticket_sha256": result.get("ticket_sha256"),
            "source_sha256": result.get("source_sha256"), "fixture_sha256": result.get("fixture_sha256"),
            "read_inputs_sha256": result.get("read_inputs_sha256"), "status": "FAIL",
            "cases": [_fallback_case_row(row) for row in cases[:case_keep]],
            "ledgers": {
                "service_calls": [_compact_evidence(item) for item in service_calls[:service_keep]],
                "factory_calls": [_compact_evidence(item) for item in factory_calls[:factory_keep]],
                **{name: ledgers[name] for name in ("reader_count", "raw_record_count", "real_factory_calls", "real_gdb_calls", "real_network_calls") if name in ledgers},
            },
            "failure": _failure("PROTOCOL", None, None, "worker RESULT exceeded the fixed protocol line limit; retained evidence is partial", observed),
        }
        try:
            _validate_fallback_shape(fallback)
            return fallback
        except _ProtocolLineTooLarge:
            if service_keep:
                service_keep = max(0, service_keep - max(1, service_keep // 4))
            elif factory_keep:
                factory_keep = max(0, factory_keep - max(1, factory_keep // 4))
            elif case_keep:
                case_keep -= 1
            else:
                raise


def _validate_fallback_shape(fallback: dict[str, Any]) -> bytes:
    init = {
        name: fallback[name]
        for name in ("phase", "nonce", "manifest_sha256", "ticket_sha256", "source_sha256", "fixture_sha256", "read_inputs_sha256")
    }
    _validate_worker_result(fallback, init, 1)
    return _protocol_bytes(fallback)


def _encode_worker_result(result: dict[str, Any]) -> tuple[dict[str, Any], bytes, int]:
    try:
        encoded = _protocol_bytes(result)
    except _ProtocolLineTooLarge as too_large:
        fallback = _protocol_failure_fallback(result, too_large)
        return fallback, _protocol_bytes(fallback), 1
    return result, encoded, 0 if result.get("status") == "SUBJECT_COMPLETE" else 1


def _write_protocol(record: dict[str, Any], stream: Any = None) -> None:
    target = stream if stream is not None else sys.stdout
    target.buffer.write(_protocol_bytes(record))
    target.flush()


def _write_bounded_stderr(message: str, maximum: int = 16384) -> None:
    encoded = str(message).encode("utf-8", errors="replace")
    if len(encoded) > maximum:
        encoded = encoded[:maximum] + b"\n<stderr truncated; original bytes=" + str(len(encoded)).encode("ascii") + b">"
    try:
        sys.stderr.buffer.write(encoded + (b"" if encoded.endswith(b"\n") else b"\n"))
        sys.stderr.buffer.flush()
    except BaseException:
        pass


def _read_json_line_before(stream: Any, label: str, deadline: float) -> dict[str, Any]:
    descriptor = stream.fileno()
    raw = bytearray()
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(label + " did not arrive before its absolute local deadline")
        readable, _writable, _exceptional = select.select([descriptor], [], [], remaining)
        if not readable:
            raise TimeoutError(label + " did not arrive before its absolute local deadline")
        chunk = os.read(descriptor, min(4096, PROTOCOL_LINE_LIMIT + 1 - len(raw)))
        if not chunk:
            if not raw:
                raise EOFError(label + " was not received")
            raise ValueError(label + " ended before its newline")
        raw.extend(chunk)
        newline = raw.find(b"\n")
        if newline >= 0:
            if newline != len(raw) - 1:
                raise ValueError(label + " contains trailing bytes after its single record")
            break
        if len(raw) > PROTOCOL_LINE_LIMIT:
            raise ValueError(label + " exceeds the fixed line limit")
    if len(raw) > PROTOCOL_LINE_LIMIT:
        raise ValueError(label + " exceeds the fixed line limit")
    value = _strict_json(bytes(raw[:-1]), label)
    if type(value) is not dict:
        raise ValueError(label + " root must be a JSON object")
    return value


def _require_stdin_eof_before(stream: Any, label: str, deadline: float) -> None:
    descriptor = stream.fileno()
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(label + " did not close before its absolute local deadline")
        readable, _writable, _exceptional = select.select([descriptor], [], [], remaining)
        if not readable:
            raise TimeoutError(label + " did not close before its absolute local deadline")
        trailing = os.read(descriptor, 1)
        if not trailing:
            return
        raise ValueError(label + " contains data after its single fixed protocol record")


def _validate_init(init: Any) -> dict[str, Any]:
    required = ("kind", "phase", "nonce", "manifest_sha256", "ticket_sha256", "source_sha256", "fixture_sha256", "read_inputs_sha256", "host_claim")
    value = _exact_object(init, required, "INIT")
    if value["kind"] != "INIT" or type(value["phase"]) is not str or value["phase"] not in PHASES:
        raise ValueError("INIT kind or phase is invalid")
    if type(value["nonce"]) is not str or re.fullmatch(r"[0-9a-f]{32}", value["nonce"]) is None:
        raise ValueError("INIT nonce must be 32 lowercase hexadecimal characters")
    if not _is_digest(value["manifest_sha256"]) or not _is_digest(value["ticket_sha256"]):
        raise ValueError("INIT manifest or ticket digest is malformed")
    expected_maps = (("source_sha256", SOURCE_PATHS), ("fixture_sha256", FIXTURE_PATHS), ("read_inputs_sha256", READ_INPUT_PATHS))
    for name, expected_paths in expected_maps:
        mapping = value[name]
        if type(mapping) is not dict or set(mapping) != set(expected_paths) or any(not _is_digest(digest) for digest in mapping.values()):
            raise ValueError("INIT " + name + " does not match the fixed path/hash map")
    claim = _exact_object(value["host_claim"], ("exclusive", "collision_preserved", "launch_argv"), "host_claim")
    if claim["exclusive"] is not True or claim["collision_preserved"] is not True or not _launch_argv_matches(claim["launch_argv"]):
        raise ValueError("host launch claim does not match the exact pinned WSL argv")
    return value


def _validate_go(go: Any, init: dict[str, Any]) -> int:
    value = _exact_object(go, ("kind", "phase", "nonce", "manifest_sha256", "remaining_ms"), "GO")
    if value["kind"] != "GO" or value["phase"] != init["phase"] or value["nonce"] != init["nonce"] or value["manifest_sha256"] != init["manifest_sha256"]:
        raise ValueError("GO binding differs from the validated INIT")
    remaining = value["remaining_ms"]
    if type(remaining) is not int or remaining <= 0 or remaining > PHASES[init["phase"]]["maximum_ms"]:
        raise ValueError("GO remaining_ms must be a strict positive bounded integer")
    return remaining


def _failure(category: str, case_id: str | None, subcontrol: str | None, message: str, observed: Any = None) -> dict[str, Any]:
    if category not in FAILURE_CATEGORIES:
        category = "INTERNAL"
    return {"category": category, "case_id": case_id, "subcontrol": subcontrol, "message": str(message)[:2048], "observed": _compact_evidence(observed)}


def _failure_for_exception(exc: BaseException, phase: str, current_case: str | None) -> dict[str, Any]:
    case_id: str | None = None
    subcontrol: str | None = None
    observed: Any = None
    category = "INTERNAL"
    message = str(exc) or type(exc).__name__
    if isinstance(exc, QualificationFailure):
        proposed_case = exc.case_id if exc.case_id in WORKER_CASE_IDS[phase] else current_case
        case_id = proposed_case
        observed = exc.observed
        valid_controls = CASE_SUBCONTROLS.get(proposed_case, ()) if proposed_case is not None else ()
        if exc.subcontrol in valid_controls:
            subcontrol = exc.subcontrol
        elif exc.subcontrol == "subcontrol-ledger" and valid_controls:
            if type(exc.observed) is list:
                for index, expected in enumerate(valid_controls):
                    if index >= len(exc.observed):
                        subcontrol = expected
                        break
                    item = exc.observed[index]
                    if type(item) is not dict or item.get("id") != expected:
                        subcontrol = expected
                        break
                    if item.get("status") != "PASS":
                        subcontrol = expected
                        break
            elif type(exc.observed) is dict and type(exc.observed.get("actual")) is list:
                actual = set(exc.observed["actual"])
                subcontrol = next((item for item in valid_controls if item not in actual), None)
            if subcontrol is None:
                subcontrol = valid_controls[-1]
        elif proposed_case is not None:
            executed = _CONTROL_TRACE.get(proposed_case, {})
            subcontrol = next((item for item in valid_controls if item not in executed), valid_controls[-1] if valid_controls else None)
        category = exc.category if exc.category in FAILURE_CATEGORIES else "INTERNAL"
    elif isinstance(exc, (TimeoutError, asyncio.TimeoutError)):
        category = "TIMEOUT"
        case_id = current_case
        if current_case is not None:
            executed = _CONTROL_TRACE.get(current_case, {})
            subcontrol = next((item for item in CASE_SUBCONTROLS[current_case] if item not in executed), CASE_SUBCONTROLS[current_case][-1])
    elif type(exc).__name__ == "DeniedOperation":
        category = "CONTAINMENT"
        case_id = current_case
        if current_case is not None:
            executed = _CONTROL_TRACE.get(current_case, {})
            subcontrol = next((item for item in CASE_SUBCONTROLS[current_case] if item not in executed), CASE_SUBCONTROLS[current_case][-1])
    elif isinstance(exc, (ImportError, FileNotFoundError, PermissionError)):
        category = "SETUP"
        case_id = current_case
        if current_case is not None:
            executed = _CONTROL_TRACE.get(current_case, {})
            subcontrol = next((item for item in CASE_SUBCONTROLS[current_case] if item not in executed), CASE_SUBCONTROLS[current_case][-1])
    else:
        case_id = current_case
        if current_case is not None:
            executed = _CONTROL_TRACE.get(current_case, {})
            subcontrol = next((item for item in CASE_SUBCONTROLS[current_case] if item not in executed), CASE_SUBCONTROLS[current_case][-1])
            if not executed:
                category = "SETUP"
    return _failure(category, case_id, subcontrol, message, observed)


def _partial_case(case_id: str, failure: dict[str, Any]) -> dict[str, Any]:
    trace = _CONTROL_TRACE.get(case_id, {})
    controls = []
    for control_id in CASE_SUBCONTROLS[case_id]:
        record = trace.get(control_id)
        if record is None:
            break
        controls.append({"id": control_id, "status": "PASS" if record.get("condition") is True else "FAIL", "observed": _compact_evidence(record.get("observed"))})
    return {"case_id": case_id, "expected": EXPECTED_BY_CASE[case_id], "status": "FAIL", "observations": {"subcontrols": controls, "failure": failure}}


def _case_runner(case_id: str, context: dict[str, Any], host_claim: dict[str, Any]) -> dict[str, Any]:
    if case_id == "Q01": return _q01(context)
    if case_id == "Q02": return _q02()
    if case_id == "Q03": return _q03()
    if case_id == "Q04": return _q04(context, host_claim)
    if case_id == "Q05": return _q05(context["fixture_data"])
    runners = {
        "R01": _run_r01, "R02": _run_r02, "R03": _run_r03, "R04": _run_r04,
        "R05": _run_r05, "R06": _run_r06, "R07": _run_r07, "R08": _run_r08,
        "R09": _run_r09, "R10": _run_r10, "R11": _run_r11, "R12": _run_r12,
        "R13": _run_r13, "R14": _run_r14, "R15": _run_r15, "R16": _run_r16,
        "C01": _run_c01, "C02": _run_c02, "C03": _run_c03, "C04": _run_c04, "C05": _run_c05,
    }
    return runners[case_id](context)


def _validate_case_result(row: Any, case_id: str, *, complete: bool) -> None:
    value = _exact_object(row, ("case_id", "expected", "status", "observations"), "case row")
    if value["case_id"] != case_id or value["expected"] != EXPECTED_BY_CASE[case_id] or value["status"] not in ("PASS", "FAIL") or type(value["observations"]) is not dict:
        raise ValueError("case row identity, status, or observation object is invalid")
    if complete and value["status"] != "PASS":
        raise ValueError("complete worker contains a failed case")
    controls = value["observations"].get("subcontrols")
    if controls is None:
        if complete:
            raise ValueError("complete case omitted its executed subcontrols")
        return
    if type(controls) is not list or len(controls) > len(CASE_SUBCONTROLS[case_id]) or (complete and len(controls) != len(CASE_SUBCONTROLS[case_id])):
        raise ValueError("case subcontrol rows have invalid coverage")
    for index, item in enumerate(controls):
        control = _exact_object(item, ("id", "status", "observed"), "subcontrol row")
        if control["id"] != CASE_SUBCONTROLS[case_id][index] or control["status"] not in (("PASS",) if complete else ("PASS", "FAIL")):
            raise ValueError("case subcontrol identity or status differs from executed coverage")


def _validate_ledgers(value: Any) -> dict[str, Any]:
    ledger = _exact_object(value, ("service_calls", "factory_calls", "reader_count", "raw_record_count", "real_factory_calls", "real_gdb_calls", "real_network_calls"), "actual-call ledger")
    if type(ledger["service_calls"]) is not list or type(ledger["factory_calls"]) is not list:
        raise ValueError("actual-call ledgers must be arrays")
    for name in ("reader_count", "raw_record_count", "real_factory_calls", "real_gdb_calls", "real_network_calls"):
        if type(ledger[name]) is not int or ledger[name] < 0:
            raise ValueError("actual-call aggregate is not a strict nonnegative integer: " + name)
    if any(ledger[name] != 0 for name in ("real_factory_calls", "real_gdb_calls", "real_network_calls")):
        raise ValueError("a real child, GDB, or network call was observed")
    return ledger


def _validate_failure_record(value: Any, phase: str) -> dict[str, Any]:
    failure = _exact_object(value, ("category", "case_id", "subcontrol", "message", "observed"), "failure")
    if failure["category"] not in FAILURE_CATEGORIES or type(failure["message"]) is not str:
        raise ValueError("failure category or message is invalid")
    if failure["case_id"] is None:
        if failure["subcontrol"] is not None:
            raise ValueError("failure subcontrol is present without case attribution")
    elif (type(failure["case_id"]) is not str or failure["case_id"] not in WORKER_CASE_IDS[phase]
          or type(failure["subcontrol"]) is not str or failure["subcontrol"] not in CASE_SUBCONTROLS[failure["case_id"]]):
        raise ValueError("failure case/subcontrol attribution is outside the approved phase contract")
    return failure


def _validate_worker_result(value: Any, init: dict[str, Any], worker_budget_ms: int) -> dict[str, Any]:
    result = _exact_object(value, ("kind", "phase", "nonce", "manifest_sha256", "ticket_sha256", "source_sha256", "fixture_sha256", "read_inputs_sha256", "status", "cases", "ledgers", "failure"), "worker RESULT")
    for name in ("phase", "nonce", "manifest_sha256", "ticket_sha256", "source_sha256", "fixture_sha256", "read_inputs_sha256"):
        if result[name] != init[name]:
            raise ValueError("worker result binding differs from host INIT: " + name)
    if result["kind"] != "RESULT" or result["status"] not in ("SUBJECT_COMPLETE", "FAIL") or type(result["cases"]) is not list:
        raise ValueError("worker result kind, status, or case array is invalid")
    cases = result["cases"]
    expected = WORKER_CASE_IDS[init["phase"]]
    if len(cases) > len(expected) or (result["status"] == "SUBJECT_COMPLETE" and len(cases) != len(expected)):
        raise ValueError("worker case count differs from executed phase coverage")
    for index, row in enumerate(cases):
        _validate_case_result(row, expected[index], complete=result["status"] == "SUBJECT_COMPLETE")
    ledger = _validate_ledgers(result["ledgers"])
    if result["status"] == "SUBJECT_COMPLETE":
        if result["failure"] is not None or worker_budget_ms <= 0:
            raise ValueError("complete worker result contains a failure or invalid budget")
    elif result["failure"] is None:
        raise ValueError("failed worker result omitted its structured failure")
    else:
        _validate_failure_record(result["failure"], init["phase"])
    return {**result, "ledgers": ledger}


def _run_worker_cases(context: dict[str, Any], init: dict[str, Any], deadline: float) -> dict[str, Any]:
    global _CURRENT_CASE_ID
    phase = init["phase"]
    cases: list[dict[str, Any]] = []
    failure: dict[str, Any] | None = None
    host_claim = init["host_claim"]
    for case_id in WORKER_CASE_IDS[phase]:
        if time.monotonic() >= deadline:
            failure = _failure("TIMEOUT", None, None, "relative GO budget expired before the next fixed case")
            break
        _CONTROL_TRACE.pop(case_id, None)
        _CURRENT_CASE_ID = case_id
        try:
            row = _case_runner(case_id, context, host_claim)
            _validate_case_result(row, case_id, complete=True)
            cases.append(row)
        except BaseException as exc:
            failure = _failure_for_exception(exc, phase, case_id)
            cases.append(_partial_case(case_id, failure))
            _CURRENT_CASE_ID = ""
            break
    _CURRENT_CASE_ID = ""
    if failure is None and (len(cases) != len(WORKER_CASE_IDS[phase]) or time.monotonic() >= deadline):
        failure = _failure("TIMEOUT", None, None, "fixed case suite did not complete inside the relative GO budget")
    return {"status": "SUBJECT_COMPLETE" if failure is None else "FAIL", "cases": cases, "failure": failure}


def _empty_ledgers() -> dict[str, Any]:
    return {"service_calls": [], "factory_calls": [], "reader_count": 0, "raw_record_count": 0, "real_factory_calls": 0, "real_gdb_calls": 0, "real_network_calls": 0}


def _worker_main() -> int:
    protocol_stdout = sys.stdout
    sys.stdout = sys.stderr
    worker_started_at = time.monotonic()
    try:
        raw = sys.stdin.buffer.read(PROTOCOL_LINE_LIMIT + 1)
        if len(raw) > PROTOCOL_LINE_LIMIT or not raw.endswith(b"\n"):
            raise ValueError("worker configuration must be exactly one bounded JSON line")
        config = _strict_json(raw[:-1], "worker configuration")
        config = _exact_object(config, ("kind", "init", "remaining_ms", "deadline_monotonic", "supervisor_identity"), "worker configuration")
        init = _validate_init(config["init"])
        if (config["kind"] != "WORKER_INIT" or type(config["remaining_ms"]) is not int
                or config["remaining_ms"] <= 0 or config["remaining_ms"] > PHASES[init["phase"]]["maximum_ms"]
                or type(config["deadline_monotonic"]) is not float
                or config["deadline_monotonic"] != config["deadline_monotonic"]
                or config["deadline_monotonic"] in (float("inf"), float("-inf"))):
            raise ValueError("worker configuration kind or remaining_ms is invalid")
        supervisor_identity = _exact_object(config["supervisor_identity"], ("pid", "start_ticks", "executable", "executable_sha256"), "supervisor identity")
        if (type(supervisor_identity["pid"]) is not int or supervisor_identity["pid"] <= 0
                or type(supervisor_identity["start_ticks"]) is not int or supervisor_identity["start_ticks"] <= 0
                or supervisor_identity["executable"] != PYTHON_RESOLVED or supervisor_identity["executable_sha256"] != PYTHON_SHA256):
            raise ValueError("worker configuration supervisor identity is invalid")
        run_deadline = config["deadline_monotonic"]
        if run_deadline <= worker_started_at or run_deadline - worker_started_at > config["remaining_ms"] / 1000.0:
            raise TimeoutError("relative GO budget expired before worker input preflight")
        context = _read_fixed_inputs(init)
        global _PHASE_LEDGER, _CURRENT_CASE_ID
        _PHASE_LEDGER = _empty_ledgers()
        _CURRENT_CASE_ID = ""
        run = _run_worker_cases(context, init, run_deadline)
        result = {
            "kind": "RESULT", "phase": init["phase"], "nonce": init["nonce"],
            "manifest_sha256": init["manifest_sha256"], "ticket_sha256": init["ticket_sha256"],
            "source_sha256": init["source_sha256"], "fixture_sha256": init["fixture_sha256"],
            "read_inputs_sha256": init["read_inputs_sha256"], "status": run["status"],
            "cases": run["cases"], "ledgers": _PHASE_LEDGER, "failure": run["failure"],
        }
        result, encoded, worker_returncode = _encode_worker_result(result)
        protocol_stdout.buffer.write(encoded)
        protocol_stdout.flush()
        return worker_returncode
    except BaseException as exc:
        _write_bounded_stderr(type(exc).__name__ + ": " + str(exc) + "\n" + traceback.format_exc())
        return 2
    finally:
        sys.stdout = protocol_stdout


def _supervisor_main() -> int:
    started_at = time.monotonic()
    proc: subprocess.Popen[bytes] | None = None
    helper: ModuleType | None = None
    init: dict[str, Any] | None = None
    context: dict[str, Any] | None = None
    supervisor_identity: dict[str, Any] | None = None
    worker_identity: dict[str, Any] | None = None
    worker_exit = {"wait_confirmed": False, "returncode": None}
    cases: list[dict[str, Any]] = []
    ledgers = _empty_ledgers()
    failure: dict[str, Any] | None = None
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    go_deadline: float | None = None
    worker_stderr = b""
    cleanup_attempted = False
    cleanup_error: str | None = None
    stage = "INIT"
    containment_failure = False
    terminal_write_attempted = False
    phase_deadline = started_at + 30.0
    try:
        init = _validate_init(_read_json_line_before(sys.stdin.buffer, "INIT", started_at + 30.0))
        phase_deadline = started_at + PHASES[init["phase"]]["maximum_ms"] / 1000.0
        if time.monotonic() >= phase_deadline:
            raise TimeoutError("initial source and identity preflight consumed the entire phase")
        stage = "PREFLIGHT"
        context = _read_fixed_inputs(init)
        stage = "HELPER"
        helper = _load_historical_helpers(context)
        supervisor_identity = helper._identity(os.getpid())
        if supervisor_identity["executable"] != PYTHON_RESOLVED or supervisor_identity["executable_sha256"] != PYTHON_SHA256:
            containment_failure = True
            raise RuntimeError("supervisor process identity does not match the pinned interpreter")
        stage = "PRESERVATION_BEFORE"
        before = _preservation_snapshot(context)
        if time.monotonic() >= phase_deadline:
            raise TimeoutError("fixed preflight exceeded the whole-phase deadline before READY")
        ready = {
            "kind": "READY", "phase": init["phase"], "nonce": init["nonce"],
            "manifest_sha256": init["manifest_sha256"], "ticket_sha256": init["ticket_sha256"],
            "source_sha256": init["source_sha256"], "fixture_sha256": init["fixture_sha256"],
            "read_inputs_sha256": init["read_inputs_sha256"], "supervisor_identity": supervisor_identity,
            "supervisor_elapsed_ms": int((time.monotonic() - started_at) * 1000),
        }
        _write_protocol(ready)
        stage = "GO"
        go = _validate_go(_read_json_line_before(sys.stdin.buffer, "GO", phase_deadline), init)
        go_received_at = time.monotonic()
        go_deadline = min(phase_deadline, go_received_at + go / 1000.0)
        _require_stdin_eof_before(sys.stdin.buffer, "GO stdin", go_deadline)
        worker_deadline = go_deadline - SUPERVISOR_RESERVE_MS / 1000.0
        worker_budget_ms = int((worker_deadline - time.monotonic()) * 1000)
        if worker_budget_ms <= 0:
            raise TimeoutError("GO left no bounded worker budget plus supervisor cleanup/evidence reserve")
        stage = "WORKER_SETUP"
        config = {
            "kind": "WORKER_INIT", "init": init, "remaining_ms": worker_budget_ms,
            "deadline_monotonic": worker_deadline,
            "supervisor_identity": supervisor_identity,
        }
        encoded_config = _protocol_bytes(config)
        worker_path = str(Path(__file__).resolve())
        argv = [sys.executable, "-B", worker_path, "--worker"]
        proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=str(ROOT), close_fds=True)
        worker_identity = helper._identity(proc.pid)
        if worker_identity["executable"] != PYTHON_RESOLVED or worker_identity["executable_sha256"] != PYTHON_SHA256:
            containment_failure = True
            raise RuntimeError("direct worker executable does not match the pinned Python binary")
        if time.monotonic() >= worker_deadline:
            raise TimeoutError("worker setup consumed the fixed worker deadline")
        stage = "WORKER_EXECUTION"
        communicate_deadline = worker_deadline
        if communicate_deadline <= time.monotonic():
            raise TimeoutError("no relative budget remained to communicate with the worker")
        try:
            stdout, worker_stderr = proc.communicate(input=encoded_config, timeout=communicate_deadline - time.monotonic())
        except subprocess.TimeoutExpired as exc:
            stdout = exc.output or b""
            worker_stderr = exc.stderr or b""
            failure = _failure("TIMEOUT", None, None, "fixed worker exceeded its relative phase deadline")
            cleanup_attempted = True
            cleanup_deadline = go_deadline - 2.0
            try:
                cleanup = helper._stop_exact_worker(proc, worker_identity, cleanup_deadline)
            except BaseException as cleanup_exc:
                cleanup_error = type(cleanup_exc).__name__ + ": " + str(cleanup_exc)
                failure = _failure("CLEANUP", None, None, "exact worker cleanup raised: " + cleanup_error)
                raise TimeoutError("exact worker cleanup failed before direct exit confirmation") from cleanup_exc
            if cleanup.get("wait_confirmed") is not True or type(cleanup.get("returncode")) is not int:
                cleanup_error = str(cleanup.get("error", "direct wait was not confirmed"))
                failure = _failure("CLEANUP", None, None, "exact worker cleanup did not confirm direct integer exit: " + cleanup_error, cleanup)
                raise TimeoutError("exact worker cleanup did not confirm direct exit before the GO deadline")
            worker_exit = {"wait_confirmed": True, "returncode": cleanup["returncode"]}
            pipe_drain_deadline = go_deadline - 1.5
            remaining = pipe_drain_deadline - time.monotonic()
            if remaining > 0:
                try:
                    drained_stdout, drained_stderr = proc.communicate(timeout=remaining)
                    stdout = drained_stdout
                    worker_stderr = drained_stderr
                except subprocess.TimeoutExpired:
                    failure = _failure("CLEANUP", None, None, "worker pipes did not drain inside the GO evidence reserve")
                    raise TimeoutError("worker pipe drain exceeded the GO deadline after direct wait")
        else:
            remaining = go_deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("worker communicate consumed the full relative GO budget")
            waited = proc.wait(timeout=remaining)
            if type(waited) is not int or time.monotonic() >= go_deadline:
                raise TimeoutError("direct worker Popen.wait did not return an integer before its deadline")
            worker_exit = {"wait_confirmed": True, "returncode": waited}
        if worker_stderr:
            _write_bounded_stderr(worker_stderr.decode("utf-8", errors="replace"))
        stage = "WORKER_RESULT"
        if failure is None:
            if len(stdout) > PROTOCOL_LINE_LIMIT or not stdout.endswith(b"\n") or stdout.count(b"\n") != 1:
                category = "SETUP" if worker_exit["returncode"] == 2 and not stdout else "PROTOCOL"
                failure = _failure(category, None, None, "worker did not emit exactly one bounded RESULT line", {"worker_returncode": worker_exit["returncode"], "stdout_bytes": len(stdout)})
            else:
                try:
                    result = _strict_json(stdout[:-1], "worker RESULT")
                    result = _validate_worker_result(result, init, worker_budget_ms)
                except Exception as exc:
                    failure = _failure("PROTOCOL", None, None, "worker RESULT failed strict validation: " + str(exc))
                else:
                    cases = result["cases"]
                    ledgers = result["ledgers"]
                    if result["status"] == "SUBJECT_COMPLETE" and worker_exit["returncode"] == 0:
                        failure = None
                    elif result["status"] == "FAIL" and worker_exit["returncode"] != 0:
                        failure = result["failure"]
                    else:
                        failure = _failure("PROTOCOL", None, None, "worker RESULT status and direct exit code disagree", {"result_status": result["status"], "worker_exit": worker_exit})
        stage = "PRESERVATION_AFTER"
        after = _preservation_snapshot(context)
        if not _same_preservation(before, after) and failure is None:
            failure = _failure("CLEANUP", None, None, "supervisor before/after preservation snapshots differ")
        elapsed_ms = int((time.monotonic() - started_at) * 1000)
        if elapsed_ms > PHASES[init["phase"]]["maximum_ms"] or time.monotonic() >= go_deadline:
            failure = failure or _failure("TIMEOUT", None, None, "supervisor phase or relative GO deadline expired before TERMINAL")
            raise TimeoutError("supervisor phase or relative GO deadline expired before TERMINAL")
        terminal = {
            "kind": "TERMINAL", "phase": init["phase"], "nonce": init["nonce"],
            "manifest_sha256": init["manifest_sha256"], "ticket_sha256": init["ticket_sha256"],
            "source_sha256": init["source_sha256"], "fixture_sha256": init["fixture_sha256"],
            "read_inputs_sha256": init["read_inputs_sha256"],
            "status": "SUBJECT_COMPLETE" if failure is None and worker_exit["wait_confirmed"] is True and worker_exit["returncode"] == 0 else "FAIL",
            "phase_elapsed_ms": elapsed_ms, "supervisor_identity": supervisor_identity,
            "worker_identity": worker_identity, "worker_exit": worker_exit, "cases": cases,
            "ledgers": ledgers, "preservation": {"before": before, "after": after}, "failure": failure,
        }
        if terminal["status"] == "SUBJECT_COMPLETE" and (worker_exit["wait_confirmed"] is not True or type(worker_exit["returncode"]) is not int or worker_exit["returncode"] != 0 or failure is not None):
            raise ValueError("host-only completion conditions are not established")
        stage = "TERMINAL_WRITE"
        terminal_write_attempted = True
        _write_protocol(terminal)
        return 0 if terminal["status"] == "SUBJECT_COMPLETE" else 1
    except BaseException as exc:
        if proc is not None and not cleanup_attempted and not worker_exit["wait_confirmed"] and helper is not None and go_deadline is not None and time.monotonic() < go_deadline - 1.5:
            try:
                cleanup_attempted = True
                cleanup = helper._stop_exact_worker(proc, worker_identity, go_deadline - 1.5)
                if cleanup.get("wait_confirmed") is True and type(cleanup.get("returncode")) is int:
                    worker_exit = {"wait_confirmed": True, "returncode": cleanup["returncode"]}
                else:
                    cleanup_error = str(cleanup.get("error", "direct worker exit remained unconfirmed"))
            except BaseException as cleanup_exc:
                cleanup_error = type(cleanup_exc).__name__ + ": " + str(cleanup_exc)
        _write_bounded_stderr(type(exc).__name__ + ": " + str(exc))
        if worker_stderr:
            _write_bounded_stderr(worker_stderr.decode("utf-8", errors="replace"))
        if (terminal_write_attempted or init is None or context is None or supervisor_identity is None
                or worker_identity is None or before is None or go_deadline is None):
            return 2
        if failure is None:
            if cleanup_error is not None or stage == "PRESERVATION_AFTER":
                failure = _failure("CLEANUP", None, None, "supervisor cleanup or preservation failed: " + (cleanup_error or str(exc)))
            elif containment_failure:
                failure = _failure("CONTAINMENT", None, None, str(exc))
            elif isinstance(exc, (TimeoutError, asyncio.TimeoutError, subprocess.TimeoutExpired)):
                failure = _failure("TIMEOUT", None, None, str(exc))
            elif isinstance(exc, (ValueError, EOFError, json.JSONDecodeError)) or stage in ("INIT", "GO", "WORKER_RESULT"):
                failure = _failure("PROTOCOL", None, None, str(exc))
            elif isinstance(exc, (ImportError, FileNotFoundError, PermissionError)) or stage in ("PREFLIGHT", "HELPER", "WORKER_SETUP"):
                failure = _failure("SETUP", None, None, str(exc))
            else:
                failure = _failure("INTERNAL", None, None, str(exc))
        if after is None:
            try:
                after = _preservation_snapshot(context)
            except BaseException as snapshot_exc:
                _write_bounded_stderr("preservation snapshot: " + type(snapshot_exc).__name__ + ": " + str(snapshot_exc))
                return 2
        if time.monotonic() >= go_deadline or int((time.monotonic() - started_at) * 1000) > PHASES[init["phase"]]["maximum_ms"]:
            return 2
        terminal = {
            "kind": "TERMINAL", "phase": init["phase"], "nonce": init["nonce"],
            "manifest_sha256": init["manifest_sha256"], "ticket_sha256": init["ticket_sha256"],
            "source_sha256": init["source_sha256"], "fixture_sha256": init["fixture_sha256"],
            "read_inputs_sha256": init["read_inputs_sha256"], "status": "FAIL",
            "phase_elapsed_ms": int((time.monotonic() - started_at) * 1000),
            "supervisor_identity": supervisor_identity, "worker_identity": worker_identity,
            "worker_exit": worker_exit, "cases": cases, "ledgers": ledgers,
            "preservation": {"before": before, "after": after}, "failure": failure,
        }
        try:
            _validate_failure_record(failure, init["phase"])
            _validate_ledgers(ledgers)
            terminal_write_attempted = True
            _write_protocol(terminal)
            return 1
        except BaseException as terminal_exc:
            _write_bounded_stderr("failed TERMINAL: " + type(terminal_exc).__name__ + ": " + str(terminal_exc))
            return 2


def main() -> int:
    if sys.argv[1:] == ["--supervisor"]:
        return _supervisor_main()
    if sys.argv[1:] == ["--worker"]:
        return _worker_main()
    _write_bounded_stderr("fixed invocation required: --supervisor or private --worker")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
