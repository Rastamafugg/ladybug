#!/usr/bin/env python3
"""Fixed, offline FEAT-010 service-lease qualifier supervisor and worker.

This file is source preparation only. The parent-published execution freeze
and host wrapper decide whether a phase may run. There is no general-purpose
test discovery, command execution, or alternate input path here.
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import os
import signal
import subprocess
import sys
import time
import traceback
from pathlib import Path
from types import ModuleType
from typing import Any


ROOT = Path(__file__).resolve().parent
FREEZE_PATH = ROOT / "service-q-freeze.json"
TICKET_PATH = ROOT.parents[2] / "wiki" / "internal" / "tickets" / "feat-010-attract-menu-free-start.html"
INTERPRETER_PATH = "/home/rastamafugg/.local/share/uv/tools/gdb-mcp/bin/python"
INTERPRETER_RESOLVED = "/home/rastamafugg/.local/share/uv/python/cpython-3.12.13-linux-x86_64-gnu/bin/python3.12"
INTERPRETER_SHA256 = "339de109f072e52523066d97a2b3372e358a10cc00c6a9df62c28a6618061900"
INPUT_PATHS = (
    "baseline/gdb.py.txt",
    "baseline/server.py.txt",
    "candidate/gdb.py",
    "candidate/server.py",
    "service-q.py",
    "run-service-q.ps1",
)
ALLOWED_INPUT_PATHS = INPUT_PATHS + ("service-q-freeze.json",)
INSTALLED_SOURCE_PATHS = {
    "gdb.py": "/home/rastamafugg/.local/share/uv/tools/gdb-mcp/lib/python3.12/site-packages/gdb.py",
    "server.py": "/home/rastamafugg/.local/share/uv/tools/gdb-mcp/lib/python3.12/site-packages/server.py",
}
BASELINE_CASES = ("B01", "B02", "B03", "B04")
CANDIDATE_CASES = tuple("C%02d" % number for number in range(1, 17))
PHASE_CASES = {"baseline": BASELINE_CASES, "candidate": CANDIDATE_CASES}
_RETAINED_UNRESOLVED_CHILDREN: list[tuple[subprocess.Popen, dict[str, Any] | None]] = []
_WORKER_CLEANUP_RESERVE_SECONDS = 2.5
_SUBJECT_CALL_LEDGER: list[dict[str, Any]] = []
_SUBJECT_LEDGER_INDEX = 0
_ACTIVE_WORLD: Any = None
EXPECTED_CARDS = {
    "baseline": {
        "B01": "PASS",
        "B02": "BASELINE_DEFECT_DETECTED",
        "B03": "BASELINE_DEFECT_DETECTED",
        "B04": "BASELINE_DEFECT_DETECTED",
    },
    "candidate": {case_id: "PASS" for case_id in CANDIDATE_CASES},
}


class QualificationFailure(Exception):
    def __init__(self, case_id: str, message: str, observed: Any = None):
        super().__init__(message)
        self.case_id = case_id
        self.observed = observed


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _is_hex_digest(value: Any) -> bool:
    return (
        type(value) is str
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _proc_start_ticks(pid: int) -> int:
    raw = Path("/proc", str(pid), "stat").read_text(encoding="ascii")
    close = raw.rfind(")")
    if close < 0:
        raise RuntimeError("proc stat has no closing comm delimiter")
    fields_after_comm = raw[close + 2 :].split()
    if len(fields_after_comm) <= 19:
        raise RuntimeError("proc stat lacks start_ticks")
    return int(fields_after_comm[19])


def _identity(pid: int) -> dict[str, Any]:
    executable = os.path.realpath("/proc/%d/exe" % pid)
    return {
        "pid": pid,
        "start_ticks": _proc_start_ticks(pid),
        "executable": executable,
        "executable_sha256": _sha256(Path(executable)),
    }


def _same_identity(expected: dict[str, Any]) -> bool:
    try:
        actual = _identity(expected["pid"])
    except (OSError, ValueError, KeyError, RuntimeError):
        return False
    return actual == expected


def _json_line(value: Any) -> None:
    sys.stdout.write(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def _strict_object(value: Any, keys: tuple[str, ...], label: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != set(keys):
        raise ValueError(label + " has the wrong object shape")
    return value


def _installed_source_hashes(expected: dict[str, str]) -> dict[str, str]:
    if type(expected) is not dict or set(expected) != set(INSTALLED_SOURCE_PATHS):
        raise ValueError("installed source hash oracle has the wrong fixed set")
    observed: dict[str, str] = {}
    for name, path in INSTALLED_SOURCE_PATHS.items():
        source = Path(path)
        if not source.is_file():
            raise FileNotFoundError("installed source is missing: " + path)
        digest = _sha256(source)
        if not _is_hex_digest(expected[name]) or digest != expected[name]:
            raise ValueError("installed source differs from immutable baseline: " + name)
        observed[name] = digest
    return observed


def _read_freeze(init: dict[str, Any]) -> tuple[dict[str, str], str, dict[str, str]]:
    raw = FREEZE_PATH.read_bytes()
    manifest_digest = hashlib.sha256(raw).hexdigest()
    if manifest_digest != init["manifest_sha256"]:
        raise ValueError("manifest hash differs from host INIT")
    freeze = json.loads(raw.decode("utf-8"))
    if type(freeze) is not dict:
        raise ValueError("freeze root is not an object")
    if freeze.get("source_preparation_gate_execution_authorized") is not True:
        raise ValueError("execution authorization is not published")
    allowed = freeze.get("allowed_input_files")
    if type(allowed) is not list or len(allowed) != len(ALLOWED_INPUT_PATHS) or set(allowed) != set(ALLOWED_INPUT_PATHS):
        raise ValueError("freeze allowed_input_files differs from the exact seven-file set")
    execution = freeze.get("execution_freeze")
    if type(execution) is not dict or execution.get("authorized") is not True:
        raise ValueError("parent execution freeze is absent or unauthorized")
    hashes = execution.get("source_sha256")
    if type(hashes) is not dict or set(hashes) != set(INPUT_PATHS):
        raise ValueError("parent execution freeze has the wrong six-source set")
    for path, digest in hashes.items():
        if not _is_hex_digest(digest):
            raise ValueError("invalid source digest for " + path)
        if _sha256(ROOT / path) != digest:
            raise ValueError("source hash mismatch for " + path)
    card_hash = execution.get("ticket_sha256")
    if not _is_hex_digest(card_hash) or _sha256(TICKET_PATH) != card_hash:
        raise ValueError("ticket hash mismatch")
    if hashes != init["source_sha256"] or card_hash != init["ticket_sha256"]:
        raise ValueError("host INIT differs from parent execution freeze")
    if freeze.get("interpreter", {}).get("sha256") != INTERPRETER_SHA256:
        raise ValueError("freeze interpreter hash differs from the approved pin")
    if not Path(INTERPRETER_PATH).is_file():
        raise ValueError("pinned interpreter path is missing")
    if os.path.realpath(INTERPRETER_PATH) != INTERPRETER_RESOLVED:
        raise ValueError("pinned interpreter resolves to a different executable")
    if _sha256(Path(INTERPRETER_RESOLVED)) != INTERPRETER_SHA256:
        raise ValueError("pinned interpreter executable hash mismatch")
    if os.path.realpath(sys.executable) != INTERPRETER_RESOLVED:
        raise ValueError("supervisor is not running under the pinned interpreter")
    baseline_hashes = freeze.get("baseline_sha256")
    if type(baseline_hashes) is not dict or set(baseline_hashes) != {"baseline/gdb.py.txt", "baseline/server.py.txt"}:
        raise ValueError("freeze baseline source set differs from the fixed archive pair")
    installed_expected = {
        "gdb.py": baseline_hashes["baseline/gdb.py.txt"],
        "server.py": baseline_hashes["baseline/server.py.txt"],
    }
    installed_observed = _installed_source_hashes(installed_expected)
    return hashes, card_hash, installed_observed


def _validate_init(line: str) -> dict[str, Any]:
    message = json.loads(line)
    _strict_object(
        message,
        ("kind", "phase", "nonce", "manifest_sha256", "source_sha256", "ticket_sha256"),
        "INIT",
    )
    if message["kind"] != "INIT":
        raise ValueError("expected INIT")
    if message["phase"] not in PHASE_CASES:
        raise ValueError("unknown fixed phase")
    if type(message["nonce"]) is not str or len(message["nonce"]) != 32 or any(
        char not in "0123456789abcdef" for char in message["nonce"]
    ):
        raise ValueError("invalid phase nonce")
    if not _is_hex_digest(message["manifest_sha256"]):
        raise ValueError("invalid manifest digest")
    if not _is_hex_digest(message["ticket_sha256"]):
        raise ValueError("invalid ticket digest")
    if type(message["source_sha256"]) is not dict or set(message["source_sha256"]) != set(INPUT_PATHS):
        raise ValueError("INIT source set differs from the fixed six-source set")
    if any(not _is_hex_digest(value) for value in message["source_sha256"].values()):
        raise ValueError("INIT includes an invalid source digest")
    return message


def _load_subject(phase: str) -> tuple[ModuleType, ModuleType]:
    import importlib.machinery

    if phase == "baseline":
        gdb_path = ROOT / "baseline" / "gdb.py.txt"
        server_path = ROOT / "baseline" / "server.py.txt"
    else:
        gdb_path = ROOT / "candidate" / "gdb.py"
        server_path = ROOT / "candidate" / "server.py"
    for name in ("gdb", "server"):
        sys.modules.pop(name, None)
    gdb_loader = importlib.machinery.SourceFileLoader("gdb", str(gdb_path))
    gdb_spec = importlib.util.spec_from_loader("gdb", gdb_loader)
    if gdb_spec is None:
        raise ImportError("cannot create isolated GDB module spec")
    gdb_module = importlib.util.module_from_spec(gdb_spec)
    sys.modules["gdb"] = gdb_module
    gdb_loader.exec_module(gdb_module)
    server_loader = importlib.machinery.SourceFileLoader("server", str(server_path))
    server_spec = importlib.util.spec_from_loader("server", server_loader)
    if server_spec is None or server_spec.loader is None:
        raise ImportError("cannot create isolated server module spec")
    server_module = importlib.util.module_from_spec(server_spec)
    sys.modules["server"] = server_module
    server_loader.exec_module(server_module)
    return gdb_module, server_module


class DeniedOperation(RuntimeError):
    pass


class DenyHooks:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self._originals: list[tuple[Any, str, Any]] = []
        self.allowed_factory_calls = 0

    def _deny(self, name: str):
        def denied(*_args: Any, **_kwargs: Any) -> Any:
            self.counts[name] = self.counts.get(name, 0) + 1
            raise DeniedOperation(name)

        return denied

    def patch(self, module: Any, attribute: str, name: str) -> None:
        self._originals.append((module, attribute, getattr(module, attribute)))
        setattr(module, attribute, self._deny(name))

    def restore(self) -> None:
        for module, attribute, original in reversed(self._originals):
            setattr(module, attribute, original)
        self._originals.clear()

    def install(self, factory: Any) -> None:
        import socket
        import subprocess as subprocess_module

        async def allowed_factory(*args: Any, **kwargs: Any) -> Any:
            self.allowed_factory_calls += 1
            return await factory(*args, **kwargs)

        self._originals.append((asyncio, "create_subprocess_exec", asyncio.create_subprocess_exec))
        asyncio.create_subprocess_exec = allowed_factory
        self.patch(asyncio, "create_subprocess_shell", "asyncio.create_subprocess_shell")
        self.patch(subprocess_module, "Popen", "subprocess.Popen")
        for name in ("run", "call", "check_call", "check_output", "getoutput", "getstatusoutput"):
            if hasattr(subprocess_module, name):
                self.patch(subprocess_module, name, "subprocess." + name)
        self.patch(os, "system", "os.system")
        self.patch(os, "popen", "os.popen")
        for name in ("execv", "execve", "execl", "execle", "execlp", "execlpe", "execvp", "execvpe", "fork", "forkpty", "vfork", "posix_spawn", "posix_spawnp"):
            if hasattr(os, name):
                self.patch(os, name, "os." + name)
        for name in ("spawnl", "spawnle", "spawnlp", "spawnlpe", "spawnv", "spawnve", "spawnvp", "spawnvpe"):
            if hasattr(os, name):
                self.patch(os, name, "os." + name)
        for name in ("connect", "connect_ex", "bind", "listen", "sendto", "sendmsg"):
            self.patch(socket.socket, name, "socket." + name)
        for name in ("getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr"):
            self.patch(socket, name, "socket." + name)


class FakeReader:
    def __init__(self) -> None:
        self.lines: asyncio.Queue[bytes] = asyncio.Queue()
        self.lines.put_nowait(b"(gdb)\n")
        self.block = False
        self.release = asyncio.Event()
        self.closed = False

    async def readline(self) -> bytes:
        if self.block:
            await self.release.wait()
        if getattr(self, "delay", 0.0):
            await asyncio.sleep(self.delay)
        if self.closed and self.lines.empty():
            return b""
        return await self.lines.get()

    def feed(self, value: bytes) -> None:
        self.lines.put_nowait(value)

    def eof(self) -> None:
        self.closed = True
        self.lines.put_nowait(b"")


class FakeStdin:
    def __init__(self, process: "FakeProcess") -> None:
        self.process = process
        self.last_write = b""
        self.writes: list[bytes] = []

    def write(self, value: bytes) -> None:
        self.last_write = value
        self.writes.append(value)
        self.process.events.append("write:" + value.decode("utf-8", errors="replace").strip())

    async def drain(self) -> None:
        world = self.process.world
        if world.drain_delay:
            await asyncio.sleep(world.drain_delay)
        if world.block_drain:
            await world.drain_release.wait()
        self.process.drain_calls += 1
        if self.last_write != b"quit\n":
            self.process.setup_count += 1
            if world.setup_error_first and self.process.setup_count == 1:
                self.process.stdout.feed(b'^error,msg="controlled setup failure"\n')
            else:
                self.process.stdout.feed(b"^done\n")
            self.process.stdout.feed(b"(gdb)\n")
        elif self.process.options.get("quit_exits", True):
            self.process.finish(int(self.process.options.get("quit_returncode", 0)))


class FakeProcess:
    def __init__(self, world: "World", options: dict[str, Any]):
        self.world = world
        self.options = options
        self.events: list[str] = ["spawned"]
        self.stdout = FakeReader()
        self.stdin = FakeStdin(self)
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
        self.events.append("terminate")
        if self.options.get("terminate_exits", True):
            self.finish(int(self.options.get("terminate_returncode", -15)))

    def kill(self) -> None:
        self.kill_calls += 1
        self.events.append("kill")
        if self.options.get("kill_exits", True):
            self.finish(int(self.options.get("kill_returncode", -9)))

    def send_signal(self, _sig: int) -> None:
        self.events.append("signal")

    def finish(self, returncode: int) -> None:
        self.returncode = returncode
        self.events.append("exit:" + str(returncode))
        self._exit.set()
        self.stdout.eof()


class World:
    def __init__(self) -> None:
        self.next_options: dict[str, Any] = {}
        self.processes: list[FakeProcess] = []
        self.all_processes: list[FakeProcess] = []
        self.fixture_tasks: set[asyncio.Task] = set()
        self.factory_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        self.total_factory_calls = 0
        self.factory_entered = asyncio.Event()
        self.factory_release = asyncio.Event()
        self.factory_delay = 0.0
        self.banner_delay = 0.0
        self.drain_delay = 0.0
        self.factory_cancel_resistant = False
        self.banner_block = False
        self.block_drain = False
        self.drain_release = asyncio.Event()
        self.setup_error_first = False
        self.denied_unexpected_factory = 0

    async def factory(self, *args: Any, **kwargs: Any) -> FakeProcess:
        self.factory_calls.append((args, kwargs))
        self.total_factory_calls += 1
        valid = (
            len(args) in (3, 4)
            and args[0] == "gdb"
            and args[1] == "--interpreter=mi2"
            and args[2] == "--quiet"
            and (len(args) == 3 or type(args[3]) is str)
            and kwargs.get("stdin") is asyncio.subprocess.PIPE
            and kwargs.get("stdout") is asyncio.subprocess.PIPE
            and kwargs.get("stderr") is asyncio.subprocess.STDOUT
            and set(kwargs) == {"stdin", "stdout", "stderr", "cwd"}
        )
        if not valid:
            self.denied_unexpected_factory += 1
            raise DeniedOperation("unexpected service factory arguments")
        self.factory_entered.set()
        if self.factory_delay:
            try:
                await asyncio.sleep(self.factory_delay)
            except asyncio.CancelledError:
                if not self.factory_cancel_resistant:
                    raise
                await self.factory_release.wait()
        elif self.factory_cancel_resistant:
            await self.factory_release.wait()
        process = FakeProcess(self, self.next_options)
        self.processes.append(process)
        self.all_processes.append(process)
        process.stdout.delay = self.banner_delay
        if self.banner_block:
            process.stdout.block = True
            process.stdout.release = self.factory_release
        return process

    async def reset(self, **options: Any) -> FakeProcess | None:
        self.processes = []
        self.next_options = options
        self.factory_calls.clear()
        self.factory_entered = asyncio.Event()
        self.factory_release = asyncio.Event()
        self.factory_delay = float(options.pop("factory_delay", 0.0))
        self.banner_delay = float(options.pop("banner_delay", 0.0))
        self.drain_delay = float(options.pop("drain_delay", 0.0))
        self.factory_cancel_resistant = bool(options.pop("factory_cancel_resistant", False))
        self.banner_block = bool(options.pop("banner_block", False))
        self.block_drain = bool(options.pop("block_drain", False))
        self.drain_release = asyncio.Event()
        self.setup_error_first = bool(options.pop("setup_error_first", False))
        self.next_options = options
        return None


def _record(case_id: str, status: str, observations: dict[str, Any]) -> dict[str, Any]:
    global _SUBJECT_LEDGER_INDEX
    calls = _SUBJECT_CALL_LEDGER[_SUBJECT_LEDGER_INDEX:]
    _SUBJECT_LEDGER_INDEX = len(_SUBJECT_CALL_LEDGER)
    if not calls:
        raise QualificationFailure(case_id, "no actual subject method invocation was recorded")
    if _ACTIVE_WORLD is not None:
        _check_fixed_spawn(_ACTIVE_WORLD, case_id)
        observations["factory_call_count"] = len(_ACTIVE_WORLD.factory_calls)
        observations["fake_processes"] = [
            {
                "returncode": process.returncode,
                "wait_calls": process.wait_calls,
                "terminate_calls": process.terminate_calls,
                "kill_calls": process.kill_calls,
                "drain_calls": process.drain_calls,
                "writes": [value.decode("utf-8", errors="replace").rstrip("\n") for value in process.stdin.writes],
                "events": list(process.events),
            }
            for process in _ACTIVE_WORLD.processes
        ]
    observations["subject_calls"] = calls
    return {"case_id": case_id, "status": status, "observations": observations}


def _assert_lifecycle(
    case_id: str,
    world: World,
    *,
    spawns: int,
    process: FakeProcess | None = None,
    waits: int | None = None,
    terminates: int = 0,
    kills: int = 0,
) -> None:
    _assert(case_id, len(world.factory_calls) == spawns, "service spawn count differs from the independent case oracle", {"expected": spawns, "actual": len(world.factory_calls)})
    _assert(case_id, len(world.processes) == spawns, "created fake-child count differs from the independent case oracle", {"expected": spawns, "actual": len(world.processes)})
    if process is None:
        return
    _assert(
        case_id,
        process in world.processes
        and (waits is None or process.wait_calls == waits)
        and process.terminate_calls == terminates
        and process.kill_calls == kills,
        "direct-child wait or signal counters differ from the independent case oracle",
        {"expected": {"waits": waits, "terminates": terminates, "kills": kills}, "actual": {"waits": process.wait_calls, "terminates": process.terminate_calls, "kills": process.kill_calls}},
    )


def _instrument_async(owner: Any, method_name: str, ledger_name: str) -> None:
    original = getattr(owner, method_name)
    if not asyncio.iscoroutinefunction(original):
        raise TypeError("subject method is not async: " + ledger_name)

    async def observed(*args: Any, **kwargs: Any) -> Any:
        _SUBJECT_CALL_LEDGER.append({"method": ledger_name, "event": "enter"})
        try:
            result = await original(*args, **kwargs)
        except BaseException as exc:
            _SUBJECT_CALL_LEDGER.append({"method": ledger_name, "event": "raise", "exception_type": type(exc).__name__, "exception": str(exc)})
            raise
        _SUBJECT_CALL_LEDGER.append({"method": ledger_name, "event": "return", "result_type": type(result).__name__})
        return result

    setattr(owner, method_name, observed)


def _instrument_subject(gdb: ModuleType, server: ModuleType) -> None:
    for name in ("create", "start_owned_session", "stop_session_by_owner", "remove"):
        if hasattr(gdb.GdbManager, name):
            _instrument_async(gdb.GdbManager, name, "GdbManager." + name)
    for name in ("send", "_send_until", "close"):
        if hasattr(gdb.GdbSession, name):
            _instrument_async(gdb.GdbSession, name, "GdbSession." + name)
    for name in ("start_session", "stop_session", "exec_command", "start_owned_session", "stop_session_by_owner"):
        if hasattr(server, name):
            _instrument_async(server, name, "server." + name)


def _fixture_task(world: World, coroutine: Any) -> asyncio.Task:
    task = asyncio.create_task(coroutine)
    world.fixture_tasks.add(task)
    return task


async def _cleanup_world(world: World, manager: Any = None) -> None:
    world.factory_release.set()
    world.drain_release.set()
    for process in world.all_processes:
        process.stdout.release.set()
        if process.returncode is None:
            process.finish(0)
    current = asyncio.current_task()
    owned_tasks = set(world.fixture_tasks)
    if manager is not None:
        for lease in getattr(manager, "_owned_leases", {}).values():
            owned_tasks.update(lease.pending_tasks)
            for task in (lease.creation_task, lease.spawn_task, lease.cleanup_task):
                if task is not None:
                    owned_tasks.add(task)
            session = lease.session
            if session is not None:
                owned_tasks.update(getattr(session, "_pending_tasks", set()))
                for task in (getattr(session, "_wait_task", None), getattr(session, "_close_task", None)):
                    if task is not None:
                        owned_tasks.add(task)
        for session in getattr(manager, "_sessions", {}).values():
            owned_tasks.update(getattr(session, "_pending_tasks", set()))
            for task in (getattr(session, "_wait_task", None), getattr(session, "_close_task", None)):
                if task is not None:
                    owned_tasks.add(task)
    pending = {task for task in owned_tasks if task is not current and not task.done()}
    if pending:
        _, pending = await asyncio.wait(pending, timeout=0.5)
    if pending:
        for task in pending:
            task.cancel()
        _, pending = await asyncio.wait(pending, timeout=0.5)
    if pending:
        raise QualificationFailure("FIXTURE_CLEANUP", "controlled subject tasks did not terminate after bounded fixture release", len(pending))


def _snapshot_shape(snapshot: Any) -> bool:
    return (
        type(snapshot) is dict
        and set(snapshot) == {"owner_id", "state", "session_id", "exit_confirmed", "returncode"}
        and type(snapshot["owner_id"]) is str
        and type(snapshot["state"]) is str
        and (snapshot["session_id"] is None or type(snapshot["session_id"]) is str)
        and type(snapshot["exit_confirmed"]) is bool
        and (snapshot["returncode"] is None or type(snapshot["returncode"]) is int)
    )


def _assert(case_id: str, condition: bool, message: str, observed: Any = None) -> None:
    if not condition:
        raise QualificationFailure(case_id, message, observed)


def _check_fixed_spawn(world: World, case_id: str) -> None:
    for args, kwargs in world.factory_calls:
        _assert(
            case_id,
            len(args) in (3, 4)
            and args[:3] == ("gdb", "--interpreter=mi2", "--quiet")
            and kwargs.get("stdin") is asyncio.subprocess.PIPE
            and kwargs.get("stdout") is asyncio.subprocess.PIPE
            and kwargs.get("stderr") is asyncio.subprocess.STDOUT
            and set(kwargs) == {"stdin", "stdout", "stderr", "cwd"},
            "service attempted a non-fixed process launch",
            {"args": list(args), "kwargs_keys": sorted(kwargs)},
        )


def _assert_control_pair(
    case_id: str,
    safe_events: tuple[str, ...],
    broken_events: tuple[str, ...],
    observed_events: tuple[str, ...],
    required: tuple[str, ...],
    forbidden: tuple[str, ...],
    expected_defect: bool,
) -> dict[str, Any]:
    def detects_defect(events: tuple[str, ...]) -> bool:
        return all(item in events for item in required) and all(
            item not in events for item in forbidden
        )

    _assert(case_id, not detects_defect(safe_events), "safe observer control classified as defective", list(safe_events))
    _assert(case_id, detects_defect(broken_events), "broken observer control was not classified as defective", list(broken_events))
    subject_defect = detects_defect(observed_events)
    _assert(case_id, subject_defect is expected_defect, "subject differs from the independently expected classification", {"events": list(observed_events), "expected_defect": expected_defect, "observed_defect": subject_defect})
    return {
        "safe_control": list(safe_events),
        "broken_control": list(broken_events),
        "observed": list(observed_events),
        "safe_rejected_as_defect": False,
        "broken_detected": True,
        "subject_defect_detected": subject_defect,
    }


async def _baseline_cases(world: World, gdb: ModuleType, server: ModuleType) -> list[dict[str, Any]]:
    manager = gdb.GdbManager()
    server.manager = manager
    rows: list[dict[str, Any]] = []

    await world.reset()
    response = await server.start_session()
    sid = response.get("session_id")
    _assert("B01", type(response) is dict and set(response) == {"session_id", "binary"}, "legacy start schema changed", response)
    output = await server.exec_command(sid, "info version")
    stopped = await server.stop_session(sid)
    process = world.processes[-1]
    _assert("B01", type(output) is str and type(stopped) is dict and stopped == {"stopped": True}, "legacy create/send/close did not pass", {"output_type": type(output).__name__, "stop": stopped})
    _assert("B01", manager._sessions == {}, "legacy close lacks normal removal", {"session_count": len(manager._sessions)})
    _assert_lifecycle("B01", world, spawns=1, process=process, waits=1)
    _check_fixed_spawn(world, "B01")
    rows.append(_record("B01", "PASS", {"spawn_count": len(world.factory_calls), "wait_calls": process.wait_calls, "legacy_response_keys": sorted(response), "stopped": stopped["stopped"]}))

    await world.reset(banner_block=True)
    manager = gdb.GdbManager()
    server.manager = manager
    creation = _fixture_task(world, manager.create())
    await world.factory_entered.wait()
    while not world.processes:
        await asyncio.sleep(0)
    process = world.processes[-1]
    process.events.append("banner_wait")
    creation.cancel()
    try:
        await creation
    except asyncio.CancelledError:
        pass
    else:
        raise QualificationFailure("B02", "baseline create caller did not cancel")
    actual = ("spawned", "banner_wait", "cancelled", "not_registered") if process not in [session.process for session in manager._sessions.values()] else ("spawned", "banner_wait", "cancelled", "registered")
    observed = _assert_control_pair(
        "B02",
        ("spawned", "banner_wait", "cancelled", "owned_pending"),
        ("spawned", "banner_wait", "cancelled", "not_registered"),
        actual,
        ("not_registered",),
        (),
        True,
    )
    _assert("B02", len(manager._sessions) == 0 and process.returncode is None, "baseline cancellation unexpectedly retained an addressable owner", {"sessions": len(manager._sessions), "returncode": process.returncode})
    _assert_lifecycle("B02", world, spawns=1, process=process, waits=0)
    rows.append(_record("B02", "BASELINE_DEFECT_DETECTED", {**observed, "live_unregistered_process": True, "session_count": 0}))
    process.finish(0)

    await world.reset(terminate_exits=False, kill_exits=False, quit_exits=False)
    session = await manager.create()
    process = session.process
    await session.close()
    events = tuple(process.events)
    observed = _assert_control_pair(
        "B03",
        ("kill", "wait_after_kill"),
        ("kill",),
        tuple("wait_after_kill" if event == "wait" and index > max((i for i, item in enumerate(events) if item == "kill"), default=-1) else event for index, event in enumerate(events)),
        ("kill",),
        ("wait_after_kill",),
        True,
    )
    _assert("B03", process.returncode is None, "baseline close unexpectedly proved exit before fixture release", {"returncode": process.returncode})
    _assert_lifecycle("B03", world, spawns=1, process=process, waits=2, terminates=1, kills=1)
    rows.append(_record("B03", "BASELINE_DEFECT_DETECTED", {**observed, "kill_calls": 1, "wait_calls_before_fixture_release": 2, "exit_confirmed_by_close": False}))
    process.finish(0)

    await world.reset()
    session = await manager.create()
    sid = session.id
    async def injected_failure() -> None:
        raise RuntimeError("controlled close failure")
    session.close = injected_failure
    try:
        await manager.remove(sid)
    except RuntimeError as exc:
        _assert("B04", str(exc) == "controlled close failure", "wrong injected close error", str(exc))
    else:
        raise QualificationFailure("B04", "baseline remove did not propagate close failure")
    actual_events = ("close_failed", "registry_popped") if sid not in manager._sessions else ("close_failed", "registry_retained")
    observed = _assert_control_pair(
        "B04",
        ("close_failed", "registry_retained"),
        ("close_failed", "registry_popped"),
        actual_events,
        ("registry_popped",),
        (),
        True,
    )
    _assert("B04", sid not in manager._sessions, "baseline remove unexpectedly retained registry on failure", actual_events)
    _assert_lifecycle("B04", world, spawns=1, process=session.process, waits=0)
    rows.append(_record("B04", "BASELINE_DEFECT_DETECTED", {**observed, "registry_count_after_failure": len(manager._sessions)}))
    session.process.finish(0)
    return rows


async def _candidate_cases(world: World, gdb: ModuleType, server: ModuleType) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    manager = gdb.GdbManager()
    server.manager = manager

    await world.reset(factory_delay=0.10)
    before = len(world.processes)
    for owner, budget in (("", 1000), ("invalid-budget", 0)):
        try:
            await server.start_owned_session(owner, budget_ms=budget)
        except Exception:
            pass
        else:
            raise QualificationFailure("C01", "invalid owner/budget was accepted")
    _assert("C01", len(world.processes) == before and len(world.factory_calls) == 0, "invalid request reached the service factory", {"factory_calls": len(world.factory_calls), "created": len(world.processes) - before})
    start = asyncio.create_task(server.start_owned_session("c01-owner", budget_ms=1000))
    await world.factory_entered.wait()
    pre_spawn = manager._owned_leases.get("c01-owner")
    _assert("C01", pre_spawn is not None and pre_spawn.state == "STARTING" and pre_spawn.creation_task is not None and pre_spawn.spawn_task is not None and len(world.processes) == 0, "owner lease was not addressable before factory completion", {"registered": pre_spawn is not None, "state": None if pre_spawn is None else pre_spawn.state, "spawn_count": len(world.processes)})
    first = await start
    _assert("C01", _snapshot_shape(first) and first["owner_id"] == "c01-owner" and first["state"] == "ACTIVE" and first["session_id"] is not None and first["exit_confirmed"] is False and first["returncode"] is None, "valid owned start did not publish a strictly typed active lease", first)
    stopped = await server.stop_session_by_owner("c01-owner", budget_ms=7000)
    _assert("C01", _snapshot_shape(stopped) and stopped["state"] == "EXITED" and stopped["exit_confirmed"] is True and type(stopped["returncode"]) is int and stopped["returncode"] == 0, "owned stop lacked direct-child exit proof", stopped)
    process = manager.get(stopped["session_id"]) if stopped["session_id"] in manager._sessions else world.processes[-1]
    _assert_lifecycle("C01", world, spawns=1, process=process, waits=1)
    _check_fixed_spawn(world, "C01")
    rows.append(_record("C01", "PASS", {"invalid_spawn_delta": 0, "lease_registered_before_factory_completion": True, "active": first["state"], "stopped": stopped["state"], "exit_confirmed": stopped["exit_confirmed"], "returncode": stopped["returncode"], "returncode_type": type(stopped["returncode"]).__name__}))

    await world.reset(factory_cancel_resistant=True)
    owner = "c02-owner"
    ledger_start = len(_SUBJECT_CALL_LEDGER)
    caller_args = ["captured-argument"]
    left = _fixture_task(world, server.start_owned_session(owner, binary="fixture.bin", args=caller_args, budget_ms=1000))
    await world.factory_entered.wait()
    shared_lease = manager._owned_leases[owner]
    shared_creation = shared_lease.creation_task
    caller_args.append("mutated-after-capture")
    _assert("C02", shared_lease.launch == ("fixture.bin", ("captured-argument",), None), "owner lease did not capture a normalized immutable launch tuple", {"launch": shared_lease.launch, "caller_args": caller_args})
    right = _fixture_task(world, server.start_owned_session(owner, binary="fixture.bin", args=["captured-argument"], budget_ms=1000))
    await asyncio.sleep(0)
    _assert("C02", manager._owned_leases[owner] is shared_lease and shared_lease.creation_task is shared_creation and sum(1 for call in _SUBJECT_CALL_LEDGER[ledger_start:] if call.get("method") == "GdbManager.start_owned_session" and call.get("event") == "enter") == 2, "same-owner request did not join the registered creation task", {"creation_task_retained": shared_lease.creation_task is shared_creation, "factory_calls": len(world.factory_calls)})
    world.factory_release.set()
    first, second = await asyncio.gather(left, right)
    _assert("C02", len(world.processes) == 1 and len(world.factory_calls) == 1 and first == second and first["state"] == "ACTIVE", "same owner/launch did not share one lease", {"spawn_count": len(world.processes), "factory_calls": len(world.factory_calls), "first": first, "second": second})
    setup_writes = [value.decode("utf-8", errors="replace").rstrip("\n") for value in world.processes[0].stdin.writes]
    _assert("C02", "set args captured-argument" in setup_writes and shared_lease.launch == ("fixture.bin", ("captured-argument",), None), "startup setup did not preserve the captured launch after caller-list mutation", {"launch": shared_lease.launch, "writes": setup_writes})
    stopped = await server.stop_session_by_owner(owner, budget_ms=7000)
    process = world.processes[-1]
    _assert("C02", stopped["state"] == "EXITED", "shared lease failed to stop", stopped)
    _assert_lifecycle("C02", world, spawns=1, process=process, waits=1)
    rows.append(_record("C02", "PASS", {"spawn_count": 1, "same_snapshot": first == second, "state": stopped["state"], "captured_launch": list(shared_lease.launch), "mutated_caller_args": caller_args, "setup_writes": setup_writes}))

    await world.reset()
    original = await server.start_owned_session("c03-owner", binary="a.bin", budget_ms=1000)
    count_before = len(world.processes)
    conflict = await server.start_owned_session("c03-owner", binary="b.bin", budget_ms=1000)
    current = manager._owned_leases["c03-owner"]
    _assert("C03", conflict["state"] == "OWNER_CONFLICT" and len(world.processes) == count_before and current.launch[0] == "a.bin" and current.state == original["state"], "conflicting launch mutated or respawned lease", {"conflict": conflict, "launch": current.launch, "state": current.state})
    await server.stop_session_by_owner("c03-owner", budget_ms=7000)
    _assert_lifecycle("C03", world, spawns=1, process=world.processes[-1], waits=1)
    rows.append(_record("C03", "PASS", {"conflict_state": conflict["state"], "spawn_delta": len(world.processes) - count_before, "original_launch": "a.bin"}))

    await world.reset()
    tombstone = await server.stop_session_by_owner("c04-owner", budget_ms=1000)
    delayed = await server.start_owned_session("c04-owner", budget_ms=1000)
    _assert("C04", tombstone["state"] == "CANCELLED_BEFORE_START" and delayed["state"] == "CANCELLED_BEFORE_START", "tombstone allowed delayed start", {"stop": tombstone, "start": delayed})
    _assert_lifecycle("C04", world, spawns=0)
    rows.append(_record("C04", "PASS", {"stop_state": tombstone["state"], "delayed_state": delayed["state"], "spawn_count": 0}))

    await world.reset(banner_block=True)
    caller = _fixture_task(world, server.start_owned_session("c05-owner", budget_ms=1000))
    await world.factory_entered.wait()
    lease = manager._owned_leases.get("c05-owner")
    while lease is None or lease.session is None:
        await asyncio.sleep(0)
        lease = manager._owned_leases.get("c05-owner")
    process = lease.session.process
    _assert("C05", process in world.processes and process.stdout.block, "start response was not cancelled after spawn during banner wait", {"spawned": process in world.processes, "banner_blocked": process.stdout.block})
    caller.cancel()
    try:
        await caller
    except asyncio.CancelledError:
        pass
    else:
        raise QualificationFailure("C05", "start response caller did not cancel")
    process.stdout.release.set()
    if lease.creation_task is not None:
        await asyncio.wait({lease.creation_task}, timeout=1.0)
    _assert("C05", lease.session is not None and lease.session_id is not None, "cancelled start lost ownership of completed child", manager._snapshot(lease))
    stopped = await server.stop_session_by_owner("c05-owner", budget_ms=7000)
    _assert("C05", stopped["state"] == "EXITED" and stopped["exit_confirmed"] is True and type(stopped["returncode"]) is int, "cancelled start was not addressable through exit", stopped)
    _assert_lifecycle("C05", world, spawns=1, process=process, waits=1)
    rows.append(_record("C05", "PASS", {"caller_cancelled": True, "session_id_retained": lease.session_id is not None, "state": stopped["state"], "returncode": stopped["returncode"]}))

    await world.reset(banner_block=True)
    start_task = _fixture_task(world, server.start_owned_session("c06-owner", budget_ms=1000))
    await world.factory_entered.wait()
    while not world.processes:
        await asyncio.sleep(0)
    process = world.processes[-1]
    process.stdout.lines = asyncio.Queue()
    process.stdout.eof()
    world.factory_release.set()
    failed = await start_task
    _assert("C06", failed["state"] == "UNRESOLVED" and failed["session_id"] is not None and not failed["exit_confirmed"], "banner failure discarded process ownership", failed)
    stopped = await server.stop_session_by_owner("c06-owner", budget_ms=7000)
    _assert("C06", stopped["state"] == "EXITED" and stopped["exit_confirmed"] and type(stopped["returncode"]) is int, "banner failure child could not be cleaned up", stopped)
    _assert_lifecycle("C06", world, spawns=1, process=process, waits=1)
    rows.append(_record("C06", "PASS", {"startup_state": failed["state"], "session_id_retained": failed["session_id"] is not None, "stop_state": stopped["state"]}))

    await world.reset(setup_error_first=True)
    failed = await server.start_owned_session("c07-owner", budget_ms=1000)
    _assert("C07", failed["state"] != "ACTIVE" and failed["session_id"] is not None, "formatted setup Error published ACTIVE", failed)
    stopped = await server.stop_session_by_owner("c07-owner", budget_ms=7000)
    _assert("C07", stopped["state"] == "EXITED", "setup error child could not be stopped", stopped)
    _assert_lifecycle("C07", world, spawns=1, process=world.processes[-1], waits=1)
    rows.append(_record("C07", "PASS", {"formatted_error_seen": True, "startup_state": failed["state"], "stop_state": stopped["state"]}))

    await world.reset(factory_cancel_resistant=True)
    pending = _fixture_task(world, server.start_owned_session("c08-owner", budget_ms=1000))
    await world.factory_entered.wait()
    lease = manager._owned_leases.get("c08-owner")
    _assert("C08", lease is not None and lease.spawn_task is not None and not lease.spawn_task.done(), "factory was not pending under an addressable owner", {"lease_registered": lease is not None, "spawn_task_pending": lease is not None and lease.spawn_task is not None and not lease.spawn_task.done()})
    pending.cancel()
    try:
        await pending
    except asyncio.CancelledError:
        pass
    else:
        raise QualificationFailure("C08", "caller cancellation did not leave the factory pending")
    unresolved = await server.stop_session_by_owner("c08-owner", budget_ms=40)
    _assert("C08", unresolved["state"] == "UNRESOLVED" and not unresolved["exit_confirmed"] and unresolved["returncode"] is None, "pending factory stop invented exit", unresolved)
    _assert("C08", manager._owned_leases.get("c08-owner") is lease and lease.spawn_task is not None and not lease.spawn_task.done() and lease.creation_task is not None, "cancelled response or short stop lost pending task/lease ownership", {"same_lease": manager._owned_leases.get("c08-owner") is lease, "spawn_task_retained": lease.spawn_task is not None, "creation_task_retained": lease.creation_task is not None})
    world.factory_release.set()
    spawn_task = lease.spawn_task
    if spawn_task is not None:
        done, _ = await asyncio.wait({spawn_task}, timeout=0.5)
        _assert("C08", bool(done) and lease.session is not None, "late factory result lost its owned handle", manager._snapshot(lease))
        closed = await server.stop_session_by_owner("c08-owner", budget_ms=7000)
        _assert("C08", closed["state"] == "EXITED", "late handle was not cleanable", closed)
    else:
        raise QualificationFailure("C08", "pending spawn task was not retained")
    _assert_lifecycle("C08", world, spawns=1, process=world.processes[-1], waits=1)
    rows.append(_record("C08", "PASS", {"caller_cancelled_while_factory_pending": True, "pending_state": unresolved["state"], "late_handle_retained": True, "final_state": closed["state"], "fixture_released": True}))

    await world.reset(factory_delay=0.35, banner_delay=0.35, drain_delay=0.35)
    c09_ledger_start = len(_SUBJECT_CALL_LEDGER)
    start_task = _fixture_task(world, server.start_owned_session("c09-owner", budget_ms=1000))
    await world.factory_entered.wait()
    result = await start_task
    _assert("C09", result["state"] == "UNRESOLVED" and result.get("error_code") in ("START_TIMEOUT", "STARTUP_FAILED") and result["session_id"] is not None, "shared startup deadline did not retain an unresolved spawned child", result)
    lease = manager._owned_leases["c09-owner"]
    process = lease.session.process
    startup_writes = [value.decode("utf-8", errors="replace").rstrip("\n") for value in process.stdin.writes]
    _assert("C09", startup_writes and startup_writes[0] == "set pagination off" and process.setup_count <= 1, "startup did not stop at its first fixed setup stage", {"writes": startup_writes, "setup_count": process.setup_count})
    startup_failures = [event for event in _SUBJECT_CALL_LEDGER[c09_ledger_start:] if event.get("method") == "GdbSession._send_until" and event.get("event") == "raise"]
    _assert("C09", len(startup_failures) == 1 and startup_failures[0].get("exception_type") == "GdbError" and "deadline" in startup_failures[0].get("exception", "").lower(), "startup did not independently record rejection at the shared deadline", startup_failures)
    if lease.session is not None:
        stopped = await server.stop_session_by_owner("c09-owner", budget_ms=7000)
        _assert("C09", stopped["state"] == "EXITED", "deadline-expired startup child could not be closed", stopped)
    _assert_lifecycle("C09", world, spawns=1, process=process, waits=1)
    rows.append(_record("C09", "PASS", {"startup_state": result["state"], "startup_error_code": result.get("error_code"), "factory_delay_ms": 350, "banner_stage_delay_ms": 350, "setup_drain_delay_ms": 350, "response_collection_reached": False, "setup_writes_at_deadline": startup_writes, "deadline_failure": startup_failures[0], "active": False}))

    await world.reset()
    start = await server.start_owned_session("c10-owner", budget_ms=1000)
    session = manager.get(start["session_id"])
    await session._lock.acquire()
    send_task = _fixture_task(world, session.send("blocked-before-write", timeout=1.0))
    try:
        await send_task
    except Exception:
        pass
    else:
        raise QualificationFailure("C10", "lock-blocked send unexpectedly completed")
    finally:
        session._lock.release()
    process = session.process
    _assert("C10", all(write != b"blocked-before-write\n" for write in process.stdin.writes), "send wrote after lock deadline", [write.decode(errors="replace") for write in process.stdin.writes])
    await server.stop_session_by_owner("c10-owner", budget_ms=7000)
    _assert_lifecycle("C10", world, spawns=1, process=process, waits=1)
    rows.append(_record("C10", "PASS", {"command_written": False, "tainted": session._broken}))

    await world.reset()
    start = await server.start_owned_session("c11-owner", budget_ms=1000)
    session = manager.get(start["session_id"])
    world.block_drain = True
    send_task = _fixture_task(world, session.send("stall-drain", timeout=1.0))
    try:
        await send_task
    except Exception:
        pass
    else:
        raise QualificationFailure("C11", "drain-blocked send unexpectedly completed")
    process = session.process
    before = len(process.stdin.writes)
    try:
        await session.send("must-not-follow", timeout=1.0)
    except Exception:
        pass
    else:
        raise QualificationFailure("C11", "tainted session admitted a later command")
    _assert("C11", len(process.stdin.writes) == before and session._broken, "timeout allowed subsequent command I/O", {"writes": len(process.stdin.writes), "before": before, "tainted": session._broken})
    world.drain_release.set()
    stopped = await server.stop_session_by_owner("c11-owner", budget_ms=7000)
    _assert("C11", stopped["state"] == "EXITED", "drain timeout session did not clean up", stopped)
    _assert_lifecycle("C11", world, spawns=1, process=process, waits=1)
    rows.append(_record("C11", "PASS", {"later_command_written": False, "tainted": True, "stop_state": stopped["state"]}))

    await world.reset()
    start = await server.start_owned_session("c12-owner", budget_ms=1000)
    session = manager.get(start["session_id"])
    process = session.process
    process.stdout.block = True
    process.stdout.release = asyncio.Event()
    process.stdin.drain = _delayed_drain(process, 0.40)
    write_count_before = len(process.stdin.writes)
    class DelayedLock:
        def __init__(self, inner: asyncio.Lock):
            self.inner = inner

        async def __aenter__(self) -> None:
            await asyncio.sleep(0.35)
            await self.inner.acquire()

        async def __aexit__(self, *_args: Any) -> None:
            self.inner.release()

    session._lock = DelayedLock(session._lock)
    send_task = _fixture_task(world, session.send("joint-budget", timeout=1.0))
    await asyncio.sleep(1.10)
    process.stdout.release.set()
    send_exception: str | None = None
    try:
        await send_task
    except Exception as exc:
        send_exception = type(exc).__name__ + ": " + str(exc)
    else:
        raise QualificationFailure("C12", "fresh collection allowance accepted a command released before its stage deadline", {"release_after_ms": 1100})
    _assert("C12", type(send_exception) is str and "deadline expired" in send_exception.lower() and session._broken and len(process.stdin.writes) == write_count_before + 1 and process.stdin.writes[-1] == b"joint-budget\n", "joint deadline did not independently reject and taint the single command", {"exception": send_exception, "tainted": session._broken, "writes": len(process.stdin.writes), "prior_writes": write_count_before, "collection_release_ms": 1100})
    process.stdin.drain = _fake_drain(process)
    stopped = await server.stop_session_by_owner("c12-owner", budget_ms=7000)
    _assert("C12", stopped["state"] == "EXITED", "send timeout child was not cleaned up", stopped)
    _assert_lifecycle("C12", world, spawns=1, process=process, waits=1)
    rows.append(_record("C12", "PASS", {"shared_budget_ms": 1000, "lock_delay_ms": 350, "drain_delay_ms": 400, "collection_stall_ms": 350, "collection_release_ms": 1100, "collection_deadline_exceeded": True, "tainted": True, "observed_exception": send_exception}))

    await world.reset(terminate_exits=False, kill_exits=False, quit_exits=False)
    start = await server.start_owned_session("c13-owner", budget_ms=1000)
    session = manager.get(start["session_id"])
    process = session.process
    world.block_drain = True
    removed = _fixture_task(world, manager.remove(session.id))
    try:
        await removed
    except gdb.GdbError:
        pass
    else:
        raise QualificationFailure("C13", "legacy remove reported success without exit proof")
    retained_before_release = session.id in manager._sessions
    exit_before_release = session._exit_confirmed
    returncode_before_release = session._exit_returncode
    _assert("C13", retained_before_release and not exit_before_release and returncode_before_release is None, "stalled close removed or falsely confirmed the child", {"registered": retained_before_release, "exit_confirmed": exit_before_release, "returncode": returncode_before_release})
    _assert_lifecycle("C13", world, spawns=1, process=process, waits=1, terminates=1, kills=1)
    row = _record("C13", "PASS", {"registry_retained_before_fixture_release": retained_before_release, "exit_confirmed_before_fixture_release": exit_before_release, "returncode_before_fixture_release": returncode_before_release, "wait_calls_before_fixture_release": process.wait_calls, "terminate_calls_before_fixture_release": process.terminate_calls, "kill_calls_before_fixture_release": process.kill_calls, "close_budget_ms": 7000, "fixture_release_after_record": True})
    world.drain_release.set()
    process.finish(0)
    if session._wait_task is not None:
        await asyncio.wait({session._wait_task}, timeout=0.5)
    _assert("C13", session._wait_task is None or session._wait_task.done(), "bounded fixture cleanup left its direct wait task pending")
    rows.append(row)

    await world.reset(terminate_exits=False, kill_exits=True, quit_exits=False)
    start = await server.start_owned_session("c14-owner", budget_ms=1000)
    process = manager.get(start["session_id"]).process
    first = await server.stop_session_by_owner("c14-owner", budget_ms=7000)
    kill_count = process.kill_calls
    spawn_count = len(world.processes)
    second = await server.stop_session_by_owner("c14-owner", budget_ms=1000)
    _assert("C14", first["state"] == "EXITED" and first["returncode"] == -9 and first["exit_confirmed"] is True, "exit was not confirmed by final wait after kill", first)
    _assert("C14", process.terminate_calls == 1 and process.kill_calls == 1 and process.wait_calls == 1 and process.events.index("exit:-9") > process.events.index("kill") and second["state"] == "EXITED" and process.kill_calls == kill_count and len(world.processes) == spawn_count, "repeat stop duplicated signals or spawn, or exit was not observed after kill", {"terminate": process.terminate_calls, "kill": process.kill_calls, "wait": process.wait_calls, "events": process.events, "second": second})
    _assert_lifecycle("C14", world, spawns=1, process=process, waits=1, terminates=1, kills=1)
    rows.append(_record("C14", "PASS", {"returncode": first["returncode"], "terminate_calls": process.terminate_calls, "kill_calls": process.kill_calls, "wait_calls": process.wait_calls, "repeat_state": second["state"], "spawn_count": spawn_count}))

    await world.reset(terminate_exits=False, kill_exits=False, quit_exits=False)
    start = await server.start_owned_session("c15-owner", budget_ms=1000)
    lease = manager._owned_leases["c15-owner"]
    process = lease.session.process
    one = _fixture_task(world, server.stop_session_by_owner("c15-owner", budget_ms=7000))
    while lease.cleanup_task is None:
        await asyncio.sleep(0)
    cleanup_task = lease.cleanup_task
    two = _fixture_task(world, server.stop_session_by_owner("c15-owner", budget_ms=7000))
    first, second = await asyncio.gather(one, two)
    _assert("C15", first["state"] == "UNRESOLVED" and second["state"] == "UNRESOLVED" and lease.cleanup_task is cleanup_task and not lease.exit_confirmed and lease.session is not None and lease.session.process is process and process.wait_calls == 1 and process.terminate_calls == 1 and process.kill_calls == 1, "unconfirmed wait lost ownership or duplicated cleanup", {"first": first, "second": second, "wait_calls": process.wait_calls, "terminate_calls": process.terminate_calls, "kill_calls": process.kill_calls, "same_cleanup": lease.cleanup_task is cleanup_task})
    _assert_lifecycle("C15", world, spawns=1, process=process, waits=1, terminates=1, kills=1)
    process.finish(0)
    if lease.session._wait_task is not None:
        await asyncio.wait({lease.session._wait_task}, timeout=0.5)
    rows.append(_record("C15", "PASS", {"first_state": first["state"], "second_state": second["state"], "same_cleanup_task": lease.cleanup_task is cleanup_task, "kill_calls": process.kill_calls, "fixture_released": True}))

    await world.reset(terminate_exits=False, kill_exits=False, quit_exits=False)
    normal = await server.start_session()
    normal_sid = normal["session_id"]
    normal_output = await server.exec_command(normal_sid, "info version")
    normal_stopped = await server.stop_session(normal_sid)
    normal_process = world.processes[-1]
    _assert("C16", type(normal) is dict and set(normal) == {"session_id", "binary"} and type(normal_output) is str and normal_stopped == {"stopped": True}, "normal legacy start/send/stop compatibility changed", {"start": normal, "output_type": type(normal_output).__name__, "stop": normal_stopped})
    _assert("C16", normal_process.wait_calls == 1 and normal_process.terminate_calls == 0 and normal_process.kill_calls == 0 and manager._sessions == {}, "normal legacy close did not use confirmed graceful exit", {"wait_calls": normal_process.wait_calls, "terminate_calls": normal_process.terminate_calls, "kill_calls": normal_process.kill_calls, "sessions": len(manager._sessions)})
    normal_legacy_counts = {"spawn_count": len(world.factory_calls), "wait_calls": normal_process.wait_calls, "terminate_calls": normal_process.terminate_calls, "kill_calls": normal_process.kill_calls}

    await world.reset(terminate_exits=False, kill_exits=False, quit_exits=False)
    legacy = await server.start_session()
    sid = legacy["session_id"]
    _assert("C16", type(legacy) is dict and set(legacy) == {"session_id", "binary"}, "legacy response schema changed", legacy)
    unknown = await server.stop_session("no-such-session")
    _assert("C16", unknown == {"stopped": False}, "unknown-session stop schema changed", unknown)
    process = manager.get(sid).process
    stop_task = _fixture_task(world, server.stop_session(sid))
    try:
        await stop_task
    except gdb.GdbError:
        pass
    else:
        raise QualificationFailure("C16", "unresolved legacy close reported stopped true")
    retained_before_release = sid in manager._sessions
    _assert("C16", retained_before_release and process.returncode is None and process.wait_calls == 1 and process.terminate_calls == 1 and process.kill_calls == 1, "unresolved legacy close removed its session or omitted cleanup/wait observations", {"registered": retained_before_release, "returncode": process.returncode, "wait_calls": process.wait_calls, "terminate_calls": process.terminate_calls, "kill_calls": process.kill_calls})
    _assert_lifecycle("C16", world, spawns=1, process=process, waits=1, terminates=1, kills=1)
    row = _record("C16", "PASS", {"normal_legacy_start_send_stop": True, "normal_legacy_counts": normal_legacy_counts, "legacy_response_keys": sorted(legacy), "unknown_stop": unknown, "unresolved_registry_retained_before_fixture_release": retained_before_release, "unresolved_wait_calls": process.wait_calls, "unresolved_terminate_calls": process.terminate_calls, "unresolved_kill_calls": process.kill_calls, "fixture_release_after_record": True})
    process.finish(0)
    session = manager.get(sid)
    if session._wait_task is not None:
        await asyncio.wait({session._wait_task}, timeout=0.5)
    _assert("C16", session._wait_task is None or session._wait_task.done(), "bounded legacy fixture cleanup left its wait task pending")
    rows.append(row)
    return rows


def _delayed_drain(process: FakeProcess, delay: float):
    async def delayed() -> None:
        await asyncio.sleep(delay)
        process.drain_calls += 1
        process.stdout.feed(b"^done\n")
        process.stdout.feed(b"(gdb)\n")
    return delayed


def _fake_drain(process: FakeProcess):
    async def immediate() -> None:
        process.drain_calls += 1
        if process.stdin.last_write == b"quit\n":
            if process.options.get("quit_exits", True):
                process.finish(int(process.options.get("quit_returncode", 0)))
        else:
            process.stdout.feed(b"^done\n")
            process.stdout.feed(b"(gdb)\n")
    return immediate


def _run_o04(hooks: DenyHooks) -> dict[str, Any]:
    import socket
    import subprocess as subprocess_module

    expected = {
        "subprocess.Popen": lambda: subprocess_module.Popen(["denied-program"]),
        "subprocess.run": lambda: subprocess_module.run(["denied-program"]),
        "os.system": lambda: os.system("denied-program"),
        "socket.connect": lambda: socket.socket().connect(("127.0.0.1", 9)),
        "socket.bind": lambda: socket.socket().bind(("127.0.0.1", 0)),
        "socket.listen": lambda: socket.socket().listen(),
        "socket.sendto": lambda: socket.socket(socket.AF_INET, socket.SOCK_DGRAM).sendto(b"x", ("127.0.0.1", 9)),
        "socket.sendmsg": lambda: socket.socket(socket.AF_INET, socket.SOCK_DGRAM).sendmsg([b"x"], [], 0, ("127.0.0.1", 9)),
        "socket.getaddrinfo": lambda: socket.getaddrinfo("example.invalid", 80),
        "asyncio.create_subprocess_shell": lambda: asyncio.create_subprocess_shell("denied-program"),
    }
    caught: list[str] = []
    for name, operation in expected.items():
        try:
            operation()
        except DeniedOperation:
            caught.append(name)
    exact_counts = {
        "subprocess.Popen": 1,
        "subprocess.run": 1,
        "os.system": 1,
        "socket.connect": 1,
        "socket.bind": 1,
        "socket.listen": 1,
        "socket.sendto": 1,
        "socket.sendmsg": 1,
        "socket.getaddrinfo": 1,
        "asyncio.create_subprocess_shell": 1,
    }
    observed = {key: hooks.counts.get(key, 0) for key in exact_counts}
    if caught != list(expected) or observed != exact_counts:
        raise QualificationFailure("O04", "deny-hook control did not reject every forbidden operation", {"caught": caught, "counts": observed})
    return {"status": "PASS", "denied_counts": observed, "real_calls": 0}


async def _worker_async(config: dict[str, Any]) -> dict[str, Any]:
    global _ACTIVE_WORLD, _SUBJECT_CALL_LEDGER, _SUBJECT_LEDGER_INDEX
    world = World()
    _ACTIVE_WORLD = world
    _SUBJECT_CALL_LEDGER = []
    _SUBJECT_LEDGER_INDEX = 0
    hooks = DenyHooks()
    hooks.install(world.factory)
    server: ModuleType | None = None
    try:
        sys.dont_write_bytecode = True
        gdb, server = _load_subject(config["phase"])
        _instrument_subject(gdb, server)
        if config["phase"] == "baseline":
            cases = await _baseline_cases(world, gdb, server)
        else:
            cases = await _candidate_cases(world, gdb, server)
        o04 = _run_o04(hooks)
        expected_ids = list(PHASE_CASES[config["phase"]])
        expected_statuses = EXPECTED_CARDS[config["phase"]]
        actual_ids = [row.get("case_id") for row in cases]
        if actual_ids != expected_ids:
            raise QualificationFailure("PHASE", "required fixed card set is incomplete or reordered", actual_ids)
        for row in cases:
            if row.get("status") != expected_statuses[row["case_id"]]:
                raise QualificationFailure(row["case_id"], "case result differs from its frozen expected classification", row)
        expected_factory_total = 4 if config["phase"] == "baseline" else 15
        if world.total_factory_calls != expected_factory_total or hooks.allowed_factory_calls != expected_factory_total:
            raise QualificationFailure("PHASE", "service factory total differs from the exact frozen card spawn count", {"expected": expected_factory_total, "world_total": world.total_factory_calls, "hook_total": hooks.allowed_factory_calls})
        _check_fixed_spawn(world, "O04")
        if world.denied_unexpected_factory != 0:
            raise QualificationFailure("O04", "unexpected service factory use was not zero", world.denied_unexpected_factory)
        return {
            "kind": "RESULT",
            "phase": config["phase"],
            "nonce": config["nonce"],
            "manifest_sha256": config["manifest_sha256"],
            "source_sha256": config["source_sha256"],
            "ticket_sha256": config["ticket_sha256"],
            "status": "PASS",
            "cases": cases,
            "o04": o04,
            "factory_calls": hooks.allowed_factory_calls,
            "denied_unexpected_factory": world.denied_unexpected_factory,
            "service_subprocess_calls": hooks.allowed_factory_calls,
        }
    finally:
        try:
            await _cleanup_world(world, getattr(server, "manager", None))
        finally:
            hooks.restore()
            _ACTIVE_WORLD = None


async def _worker(config_line: str) -> int:
    case_id = "SETUP"
    phase = ""
    try:
        config = json.loads(config_line)
        _strict_object(
            config,
            ("kind", "phase", "nonce", "manifest_sha256", "source_sha256", "ticket_sha256", "remaining_ms"),
            "WORKER config",
        )
        if config["kind"] != "WORKER" or config["phase"] not in PHASE_CASES:
            raise ValueError("invalid worker phase")
        if type(config["remaining_ms"]) is not int or config["remaining_ms"] <= 0:
            raise ValueError("invalid relative worker budget")
        phase = config["phase"]
        result_task = asyncio.create_task(_worker_async(config))
        try:
            result = await asyncio.wait_for(result_task, timeout=config["remaining_ms"] / 1000.0)
        except asyncio.TimeoutError as exc:
            raise QualificationFailure("PHASE", "worker exceeded supervisor relative deadline") from exc
        _json_line(result)
        return 0
    except BaseException as exc:
        if isinstance(exc, QualificationFailure):
            case_id = exc.case_id
            observed = exc.observed
        else:
            observed = None
        _json_line({
            "kind": "RESULT",
            "phase": phase,
            "status": "FAIL",
            "failure_case": case_id,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback": traceback.format_exc(limit=8),
            "observed": observed,
        })
        return 1


def _linger() -> int:
    signal.signal(signal.SIGTERM, lambda _signum, _frame: None)
    _json_line({"kind": "LINGER_READY"})
    while True:
        time.sleep(0.1)


def _wait_for_linger_ready(proc: subprocess.Popen, deadline: float) -> bool:
    import select

    if proc.stdout is None:
        return False
    descriptor = proc.stdout.fileno()
    buffered = bytearray()
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        ready, _, _ = select.select([descriptor], [], [], min(0.05, remaining))
        if ready:
            try:
                chunk = os.read(descriptor, 4096)
            except BlockingIOError:
                continue
            if not chunk:
                return False
            buffered.extend(chunk)
            if len(buffered) > 4096:
                return False
            if b"\n" not in buffered:
                continue
            line, trailing = bytes(buffered).split(b"\n", 1)
            if trailing:
                return False
            try:
                value = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return False
            return type(value) is dict and value == {"kind": "LINGER_READY"}
        # poll() is only a scheduling hint. It is never accepted as exit proof.
    return False


def _stop_exact_worker(proc: subprocess.Popen, identity: dict[str, Any] | None, deadline: float) -> dict[str, Any]:
    proof: dict[str, Any] = {
        "identity": identity,
        "wait_confirmed": False,
        "returncode": None,
        "signals": [],
    }
    def wait_for(allowance: float) -> bool:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        try:
            observed = proc.wait(timeout=min(allowance, remaining))
        except subprocess.TimeoutExpired:
            return False
        if type(observed) is int and time.monotonic() < deadline:
            proof["wait_confirmed"] = True
            proof["returncode"] = observed
            return True
        if type(observed) is not int:
            proof["error"] = "Popen.wait returned a non-integer result"
        return False

    if wait_for(0.01):
        return proof
    if time.monotonic() >= deadline:
        proof["error"] = "deadline expired before TERM"
        return proof
    try:
        if identity is not None and _same_identity(identity):
            os.kill(identity["pid"], signal.SIGTERM)
        else:
            # The exact Popen object remains the ownership capability; never
            # signal a PID obtained from an unverified record.
            proc.terminate()
        proof["signals"].append("TERM")
    except ProcessLookupError:
        pass
    except OSError as exc:
        proof["error"] = "TERM failed: " + str(exc)
    if wait_for(0.35):
        return proof
    if time.monotonic() >= deadline:
        proof["error"] = "deadline expired before KILL"
        return proof
    try:
        if identity is not None and _same_identity(identity):
            os.kill(identity["pid"], signal.SIGKILL)
        else:
            proc.kill()
        proof["signals"].append("KILL")
    except ProcessLookupError:
        pass
    except OSError as exc:
        proof["error"] = "KILL failed: " + str(exc)
    if wait_for(0.35):
        return proof
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        proof["error"] = "worker final wait exceeded deadline"
        return proof
    try:
        returncode = proc.wait(timeout=remaining)
        if type(returncode) is int and time.monotonic() < deadline:
            proof["wait_confirmed"] = True
            proof["returncode"] = returncode
        else:
            proof["error"] = "worker final wait result was late or not an integer"
    except subprocess.TimeoutExpired:
        proof["error"] = "worker final wait exceeded deadline"
    return proof


def _run_o03(python: str, script: str, deadline: float) -> dict[str, Any]:
    started = time.monotonic()
    o03_deadline = min(deadline, started + 1.5)
    if o03_deadline - started <= 0:
        raise TimeoutError("no budget remains for O03")
    proc: subprocess.Popen | None = None
    identity: dict[str, Any] | None = None
    cleanup: dict[str, Any] | None = None
    cleanup_started: float | None = None
    try:
        proc = subprocess.Popen(
            [python, "-B", script, "--linger"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(ROOT),
            close_fds=True,
        )
        identity = _identity(proc.pid)
        if identity["executable"] != INTERPRETER_RESOLVED or identity["executable_sha256"] != INTERPRETER_SHA256:
            raise RuntimeError("O03 worker executable does not match interpreter pin")
        readiness_deadline = min(o03_deadline, started + 0.5)
        ready = _wait_for_linger_ready(proc, readiness_deadline)
        cleanup_started = time.monotonic()
        if not ready:
            cleanup = _stop_exact_worker(proc, identity, o03_deadline)
        else:
            cleanup = _stop_exact_worker(proc, identity, o03_deadline)
        success = (
            ready
            and cleanup is not None
            and cleanup["wait_confirmed"] is True
            and type(cleanup["returncode"]) is int
            and cleanup["returncode"] == -signal.SIGKILL
            and cleanup["signals"] == ["TERM", "KILL"]
            and cleanup.get("identity") == identity
        )
        if not (cleanup and cleanup.get("wait_confirmed") is True):
            _RETAINED_UNRESOLVED_CHILDREN.append((proc, identity))
        cleanup_elapsed_ms = int((time.monotonic() - cleanup_started) * 1000)
        return {"status": "PASS" if success else "FAIL", "identity": identity, "cleanup": cleanup, "term_ignored": ready, "phase_elapsed_ms": int((time.monotonic() - started) * 1000), "readiness_deadline_ms": 500, "cleanup_reserve_ms": 1000, "cleanup_elapsed_ms": cleanup_elapsed_ms, "deadline_ms": 1500}
    except BaseException as exc:
        if proc is not None and not (cleanup and cleanup.get("wait_confirmed") is True):
            cleanup = _stop_exact_worker(proc, identity, o03_deadline)
        if proc is not None and not (cleanup and cleanup.get("wait_confirmed") is True):
            _RETAINED_UNRESOLVED_CHILDREN.append((proc, identity))
        cleanup_elapsed_ms = int((time.monotonic() - cleanup_started) * 1000) if cleanup_started is not None else 0
        return {"status": "FAIL", "identity": identity, "cleanup": cleanup, "error_type": type(exc).__name__, "error": str(exc), "phase_elapsed_ms": int((time.monotonic() - started) * 1000), "readiness_deadline_ms": 500, "cleanup_reserve_ms": 1000, "cleanup_elapsed_ms": cleanup_elapsed_ms, "deadline_ms": 1500}
    finally:
        # An unresolved exact Popen handle remains strongly referenced above.
        pass


def _run_worker(config: dict[str, Any], deadline: float) -> dict[str, Any]:
    work_deadline = deadline - _WORKER_CLEANUP_RESERVE_SECONDS
    remaining_ms = int(max(0.0, work_deadline - time.monotonic()) * 1000)
    if remaining_ms <= 0:
        return {"status": "FAIL", "wait_confirmed": False, "error": "no relative budget remains for qualification worker"}
    worker_config = dict(config)
    worker_config["kind"] = "WORKER"
    worker_config["remaining_ms"] = remaining_ms
    proc: subprocess.Popen | None = None
    identity: dict[str, Any] | None = None
    stdout_data = b""
    stderr_data = b""
    outcome: dict[str, Any] | None = None
    wait_confirmed = False
    returncode: int | None = None
    cleanup: dict[str, Any] | None = None
    error: str | None = None
    try:
        proc = subprocess.Popen(
            [sys.executable, "-B", str(Path(__file__).resolve()), "--worker"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(ROOT),
            close_fds=True,
        )
        if proc.stdin is None or proc.stdout is None or proc.stderr is None:
            raise RuntimeError("worker pipes were not created")
        identity = _identity(proc.pid)
        if identity["executable"] != INTERPRETER_RESOLVED or identity["executable_sha256"] != INTERPRETER_SHA256:
            raise RuntimeError("worker executable does not match interpreter pin")
        payload = (json.dumps(worker_config, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        remaining = work_deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(proc.args, 0)
        try:
            stdout_data, stderr_data = proc.communicate(input=payload, timeout=remaining)
        except subprocess.TimeoutExpired as exc:
            if exc.output is not None:
                stdout_data = exc.output if type(exc.output) is bytes else str(exc.output).encode("utf-8", errors="replace")
            if exc.stderr is not None:
                stderr_data = exc.stderr if type(exc.stderr) is bytes else str(exc.stderr).encode("utf-8", errors="replace")
            raise
        wait_remaining = deadline - time.monotonic()
        if wait_remaining <= 0:
            raise subprocess.TimeoutExpired(proc.args, 0)
        returncode = proc.wait(timeout=wait_remaining)
        if type(returncode) is int and time.monotonic() < deadline:
            wait_confirmed = True
        else:
            raise RuntimeError("Popen.wait returned an invalid or late exit observation")
        lines = stdout_data.decode("utf-8", errors="strict").splitlines()
        if len(lines) != 1:
            raise ValueError("worker must emit exactly one JSON result line")
        outcome = json.loads(lines[0])
        if type(outcome) is not dict or outcome.get("kind") != "RESULT":
            raise ValueError("worker result has invalid JSON shape")
        return {
            "status": "PASS" if returncode == 0 and outcome.get("status") == "PASS" else "FAIL",
            "identity": identity,
            "wait_confirmed": True,
            "returncode": returncode,
            "outcome": outcome,
            "stderr": stderr_data.decode("utf-8", errors="replace"),
            "stdout": stdout_data.decode("utf-8", errors="replace"),
        }
    except BaseException as exc:
        error = type(exc).__name__ + ": " + str(exc)
        if isinstance(exc, subprocess.TimeoutExpired):
            if exc.output is not None:
                stdout_data = exc.output if type(exc.output) is bytes else str(exc.output).encode("utf-8", errors="replace")
            if exc.stderr is not None:
                stderr_data = exc.stderr if type(exc.stderr) is bytes else str(exc.stderr).encode("utf-8", errors="replace")
        if proc is not None and not wait_confirmed:
            cleanup = _stop_exact_worker(proc, identity, deadline)
            if cleanup.get("wait_confirmed") is True and type(cleanup.get("returncode")) is int:
                wait_confirmed = True
                returncode = cleanup["returncode"]
                try:
                    rem = deadline - time.monotonic()
                    if rem > 0:
                        more_out, more_err = proc.communicate(timeout=rem)
                        if more_out:
                            stdout_data = more_out
                        if more_err:
                            stderr_data = more_err
                    rem = deadline - time.monotonic()
                    if rem > 0:
                        confirmed = proc.wait(timeout=rem)
                        if type(confirmed) is int and time.monotonic() < deadline:
                            returncode = confirmed
                        else:
                            wait_confirmed = False
                except (subprocess.TimeoutExpired, OSError, ValueError):
                    wait_confirmed = False
            if not wait_confirmed:
                _RETAINED_UNRESOLVED_CHILDREN.append((proc, identity))
        if proc is None:
            return {"status": "FAIL", "wait_confirmed": False, "returncode": None, "error": error, "outcome": None, "stdout": "", "stderr": ""}
        return {
            "status": "FAIL",
            "identity": identity,
            "cleanup": cleanup,
            "wait_confirmed": wait_confirmed,
            "returncode": returncode if wait_confirmed else None,
            "error": error,
            "outcome": outcome,
            "stdout": stdout_data.decode("utf-8", errors="replace"),
            "stderr": stderr_data.decode("utf-8", errors="replace"),
        }


def _supervisor() -> int:
    supervisor_started = time.monotonic()
    supervisor_identity = _identity(os.getpid())
    if supervisor_identity["executable"] != INTERPRETER_RESOLVED or supervisor_identity["executable_sha256"] != INTERPRETER_SHA256:
        _json_line({"kind": "SUPERVISOR_FAIL", "reason": "interpreter identity mismatch"})
        return 2
    init_line = sys.stdin.readline()
    if not init_line:
        return 2
    try:
        init = _validate_init(init_line)
        hashes, ticket_hash, installed_hashes = _read_freeze(init)
    except BaseException as exc:
        _json_line({"kind": "SUPERVISOR_FAIL", "reason": "preflight", "error_type": type(exc).__name__, "error": str(exc), "nonce": None})
        return 2
    ready = {
        "kind": "READY",
        "phase": init["phase"],
        "nonce": init["nonce"],
        "manifest_sha256": init["manifest_sha256"],
        "source_sha256": hashes,
        "ticket_sha256": ticket_hash,
        "installed_source_sha256": installed_hashes,
        "supervisor": supervisor_identity,
        "supervisor_elapsed_ms": int((time.monotonic() - supervisor_started) * 1000),
    }
    _json_line(ready)
    go_line = sys.stdin.readline()
    if not go_line:
        _json_line({"kind": "TERMINAL", "phase": init["phase"], "nonce": init["nonce"], "status": "NO_GO_NO_WORKER", "worker_spawned": False, "supervisor": supervisor_identity, "supervisor_elapsed_ms": int((time.monotonic() - supervisor_started) * 1000)})
        return 0
    try:
        go = json.loads(go_line)
        _strict_object(go, ("kind", "phase", "nonce", "manifest_sha256", "remaining_ms"), "GO")
        if go["kind"] != "GO" or go["phase"] != init["phase"] or go["nonce"] != init["nonce"] or go["manifest_sha256"] != init["manifest_sha256"]:
            raise ValueError("GO binding mismatch")
        if type(go["remaining_ms"]) is not int or go["remaining_ms"] <= 0:
            raise ValueError("GO remaining budget is not a positive integer")
    except BaseException as exc:
        _json_line({"kind": "TERMINAL", "phase": init["phase"], "nonce": init["nonce"], "status": "FAIL", "worker_spawned": False, "error_type": type(exc).__name__, "error": str(exc), "supervisor": supervisor_identity, "supervisor_elapsed_ms": int((time.monotonic() - supervisor_started) * 1000)})
        return 2
    phase_started = time.monotonic()
    deadline = phase_started + go["remaining_ms"] / 1000.0
    o03: dict[str, Any] = {"status": "NOT_APPLICABLE", "worker_spawned": False}
    worker_record: dict[str, Any] | None = None
    try:
        if init["phase"] == "baseline":
            o03 = _run_o03(INTERPRETER_PATH, str(Path(__file__).resolve()), deadline)
            if o03.get("status") != "PASS":
                raise RuntimeError("O03 worker cleanup/reap proof failed")
        if time.monotonic() >= deadline:
            raise TimeoutError("phase deadline expired before qualification worker start")
        worker_record = _run_worker(init, deadline)
        status = "PASS" if worker_record.get("status") == "PASS" else "FAIL"
    except BaseException as exc:
        status = "FAIL"
        worker_record = {
            "status": "FAIL",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback": traceback.format_exc(limit=8),
            "wait_confirmed": False,
        }
    post_hashes: dict[str, Any] = {}
    preservation_failure: str | None = None
    try:
        post_sources = {path: _sha256(ROOT / path) for path in INPUT_PATHS}
        post_ticket = _sha256(TICKET_PATH)
        post_manifest = _sha256(FREEZE_PATH)
        post_installed = _installed_source_hashes(installed_hashes)
        post_interpreter = _sha256(Path(INTERPRETER_RESOLVED))
        post_hashes = {
            "source_sha256": post_sources,
            "ticket_sha256": post_ticket,
            "manifest_sha256": post_manifest,
            "installed_source_sha256": post_installed,
            "interpreter_sha256": post_interpreter,
        }
        if (
            post_sources != hashes
            or post_ticket != ticket_hash
            or post_manifest != init["manifest_sha256"]
            or post_installed != installed_hashes
            or post_interpreter != INTERPRETER_SHA256
        ):
            raise ValueError("source, ticket, manifest, installed service, or interpreter changed during phase")
    except BaseException as exc:
        status = "FAIL"
        preservation_failure = type(exc).__name__ + ": " + str(exc)

    ack = None
    if worker_record is not None and worker_record.get("wait_confirmed") is True:
        identity = worker_record.get("identity")
        returncode = worker_record.get("returncode")
        if type(identity) is dict and type(returncode) is int:
            ack = {
                "pid": identity.get("pid"),
                "start_ticks": identity.get("start_ticks"),
                "executable": identity.get("executable"),
                "executable_sha256": identity.get("executable_sha256"),
                "wait_confirmed": True,
                "returncode": returncode,
            }
    _json_line({
        "kind": "TERMINAL",
        "phase": init["phase"],
        "nonce": init["nonce"],
        "manifest_sha256": init["manifest_sha256"],
        "source_sha256": hashes,
        "ticket_sha256": ticket_hash,
        "status": status,
        "o03": o03,
        "worker": worker_record,
        "worker_ack": ack,
        "ready_supervisor_elapsed_ms": ready["supervisor_elapsed_ms"],
        "supervisor_elapsed_ms": int((time.monotonic() - supervisor_started) * 1000),
        "phase_elapsed_ms": int((time.monotonic() - phase_started) * 1000),
        "installed_source_sha256": installed_hashes,
        "post_hashes": post_hashes,
        "preservation_failure": preservation_failure,
        "supervisor": supervisor_identity,
    })
    return 0 if status == "PASS" and ack is not None else 1


def main(argv: list[str]) -> int:
    if argv == ["--supervisor"]:
        return _supervisor()
    if argv == ["--worker"]:
        line = sys.stdin.readline()
        if not line:
            _json_line({"kind": "RESULT", "phase": "", "status": "FAIL", "failure_case": "SETUP", "error_type": "EOFError", "error": "missing worker config"})
            return 2
        return asyncio.run(_worker(line))
    if argv == ["--linger"]:
        return _linger()
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
