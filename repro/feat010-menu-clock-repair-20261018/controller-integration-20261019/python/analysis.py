"""Attempt-bound offline FEAT-010 source, capture, and trace analysis worker.

The worker accepts one fixed JSON request from one attempt directory. It reads
the pinned source context read-only and uses the copied guard, window adapter,
and observer directly. It starts no subprocess and performs no host or runtime
control. A COMPLETE result means analysis finished; it is not runtime readiness
or product acceptance.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import time
from importlib.machinery import SourceFileLoader


REQUEST_SCHEMA = "ladybug.feat010.python-analysis.request.v1"
RESULT_SCHEMA = "ladybug.feat010.python-analysis.result.v1"
MAX_BUDGET_MS = 60000
SOURCE_ROOT_TEXT = "/mnt/e/projects/ladybug/repro/feat010-menu-clock-repair-20261018"
HERE = Path(__file__).resolve().parent
EVIDENCE_ROOT = (HERE.parent / "evidence").resolve()
OWNER_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
ATTEMPT_ID_RE = OWNER_ID_RE
REQUEST_KEYS = {"schema", "owner_id", "attempt_id", "source_root", "budget_ms"}


class AnalysisInputError(ValueError):
    """The request or attempt-local evidence does not match the fixed contract."""


class AnalysisDeadlineExceeded(TimeoutError):
    """The single local monotonic analysis deadline expired."""


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _elapsed_ms(started):
    return max(0, int((time.monotonic() - started) * 1000))


def _check_deadline(deadline, stage):
    if time.monotonic() >= deadline:
        raise AnalysisDeadlineExceeded("analysis deadline expired during " + stage)


def _exception_record(exc, stage):
    return {"stage": stage, "type": type(exc).__name__,
            "module": type(exc).__module__, "message": str(exc)}


def _record_call(ledger, stage, callable_name, function, *args, **kwargs):
    row = {"stage": stage, "callable": callable_name, "invoked": True,
           "outcome": "running"}
    ledger.append(row)
    try:
        value = function(*args, **kwargs)
    except Exception as exc:
        row["outcome"] = "raised"
        row["error"] = _exception_record(exc, stage)
        raise
    row["outcome"] = "returned"
    return value


def _inside(root, path, label, require_file=False):
    candidate = Path(path)
    if candidate.is_symlink():
        raise AnalysisInputError(label + " must not be a symbolic link")
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise AnalysisInputError(label + " is missing or outside the attempt directory") from exc
    if require_file:
        try:
            mode = resolved.stat().st_mode
        except OSError as exc:
            raise AnalysisInputError(label + " cannot be inspected") from exc
        if not stat.S_ISREG(mode):
            raise AnalysisInputError(label + " is not a regular file")
    return resolved


def _load_request(request_argument, phase_started):
    raw_request = Path(request_argument)
    if raw_request.name != "request.json":
        raise AnalysisInputError("request path must be named request.json")
    lexical_request = Path(os.path.abspath(str(raw_request)))
    try:
        relative = lexical_request.relative_to(EVIDENCE_ROOT)
    except ValueError as exc:
        raise AnalysisInputError("request path is outside the worker evidence root") from exc
    if len(relative.parts) != 2 or relative.parts[1] != "request.json":
        raise AnalysisInputError("request must be directly inside one attempt directory")
    if lexical_request.is_symlink() or lexical_request.parent.is_symlink():
        raise AnalysisInputError("request path and attempt directory must not be symbolic links")
    request_path = lexical_request.resolve(strict=True)
    if request_path != lexical_request:
        raise AnalysisInputError("request path resolves outside its attempt-local spelling")
    if not stat.S_ISREG(request_path.stat().st_mode):
        raise AnalysisInputError("request.json is not a regular file")
    request_bytes = request_path.read_bytes()
    try:
        request = json.loads(request_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AnalysisInputError("request.json is not valid UTF-8 JSON") from exc
    if not isinstance(request, dict) or set(request) != REQUEST_KEYS:
        raise AnalysisInputError("request fields do not match the fixed schema")
    if request.get("schema") != REQUEST_SCHEMA:
        raise AnalysisInputError("request schema mismatch")
    owner_id = request.get("owner_id")
    attempt_id = request.get("attempt_id")
    if not isinstance(owner_id, str) or not OWNER_ID_RE.fullmatch(owner_id):
        raise AnalysisInputError("owner_id is malformed")
    if not isinstance(attempt_id, str) or not ATTEMPT_ID_RE.fullmatch(attempt_id):
        raise AnalysisInputError("attempt_id is malformed")
    if relative.parts[0] != attempt_id:
        raise AnalysisInputError("attempt_id does not match its directory")
    if type(request.get("budget_ms")) is not int or not 1 <= request["budget_ms"] <= MAX_BUDGET_MS:
        raise AnalysisInputError("budget_ms must be an integer from 1 through 60000")
    if request.get("source_root") != SOURCE_ROOT_TEXT:
        raise AnalysisInputError("source_root is not the exact pinned original repro root")
    attempt_root = request_path.parent
    if attempt_root == EVIDENCE_ROOT:
        raise AnalysisInputError("attempt directory is invalid")
    try:
        attempt_root.relative_to(EVIDENCE_ROOT)
    except ValueError as exc:
        raise AnalysisInputError("attempt directory escaped the evidence root") from exc
    if attempt_root == Path(SOURCE_ROOT_TEXT).resolve(strict=True):
        raise AnalysisInputError("attempt output cannot be inside the pinned source root")
    deadline = phase_started + request["budget_ms"] / 1000.0
    return request, request_path, attempt_root, request_bytes, deadline


def _load_modules(attempt_root, ledger, deadline):
    guard_path = HERE / "stutter-runtime-guard.py"
    window_path = HERE / "stutter-trace-window.py"
    observer_path = HERE / "stutter-observer.py"
    for path, name in ((guard_path, "guard"), (window_path, "window"),
                       (observer_path, "observer")):
        _inside(HERE, path, name + " source", require_file=True)
    _check_deadline(deadline, "helper import")
    guard_loader = SourceFileLoader("feat010_guard_actual", str(guard_path))
    guard = _record_call(ledger, "module_import", "guard.SourceFileLoader.load_module",
                         guard_loader.load_module)
    window_loader = SourceFileLoader("feat010_window_actual", str(window_path))
    window = _record_call(ledger, "module_import", "window.SourceFileLoader.load_module",
                          window_loader.load_module)
    observer = getattr(window, "observer", None)
    if observer is None or not callable(getattr(observer, "analyze", None)):
        raise AnalysisInputError("copied window did not load its actual sibling observer")
    _check_deadline(deadline, "helper import")

    source_root = Path(SOURCE_ROOT_TEXT).resolve(strict=True)
    # Rebind only the original source context used by the copied guard's
    # existing validation functions. Captures and dumps remain attempt-local.
    guard.WORK = source_root
    guard.BASE = source_root / "candidate"
    guard.BUILD = guard.BASE / "build"
    guard.READY = source_root / "stutter-runtime-host-preparation-ready.json"
    guard.SOURCE_ID = source_root / "stutter-runtime-proposal-source-identity.json"
    guard.DUMPS = attempt_root / "dumps"
    return guard, window, observer


def _read_attempt_inputs(attempt_root, guard, deadline):
    captures_path = _inside(attempt_root, attempt_root / "captures.json",
                            "captures.json", require_file=True)
    trace_path = _inside(attempt_root, attempt_root / "trace.txt",
                         "trace.txt", require_file=True)
    dump_root = _inside(attempt_root, attempt_root / "dumps", "dumps directory")
    if not dump_root.is_dir():
        raise AnalysisInputError("dumps path is not a directory")

    captures_bytes = captures_path.read_bytes()
    try:
        captures = json.loads(captures_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AnalysisInputError("captures.json is not valid UTF-8 JSON") from exc
    trace_bytes = trace_path.read_bytes()
    try:
        trace_text = trace_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AnalysisInputError("trace.txt is not valid UTF-8") from exc

    dump_provider = {}
    dump_hashes = []
    for checkpoint, name, _address, length in guard.READ_PLAN:
        _check_deadline(deadline, "attempt dump reads")
        filename = "{}-{}.bin".format(checkpoint, name)
        path = _inside(attempt_root, dump_root / filename,
                       "dump " + filename, require_file=True)
        data = path.read_bytes()
        if len(data) != length:
            raise AnalysisInputError("dump {} has length {}, expected {}".format(
                filename, len(data), length))
        dump_provider[(checkpoint, name)] = data
        dump_hashes.append({"checkpoint": checkpoint, "name": name,
                            "length": len(data), "sha256": _sha256(data)})
    _check_deadline(deadline, "attempt input reads")
    return captures, trace_text, dump_provider, {
        "captures_sha256": _sha256(captures_bytes),
        "trace_sha256": _sha256(trace_bytes),
        "dumps": dump_hashes,
    }


def _extract_marker_bytes(guard, observer, dump_provider):
    spans = []
    for checkpoint, name, address, length in guard.READ_PLAN:
        if checkpoint == "B080":
            data = dump_provider[(checkpoint, name)]
            spans.append((address, address + length, data, name))
    marker_bytes = {}
    for name, (pc, opcode, _mnemonic) in observer.MARKERS.items():
        size = len(opcode) // 2
        matches = [(data[pc - start:pc - start + size].hex(), dump_name)
                   for start, end, data, dump_name in spans
                   if start <= pc and pc + size <= end]
        if len(matches) != 1:
            raise AnalysisInputError("B080 destination marker span is ambiguous: " + name)
        actual, _dump_name = matches[0]
        if actual != opcode:
            raise AnalysisInputError("B080 destination marker bytes mismatch: " + name)
        marker_bytes[name] = actual
    return marker_bytes


def _source_hashes():
    sources = {"analysis.py": Path(__file__).resolve(),
               "stutter-runtime-guard.py": HERE / "stutter-runtime-guard.py",
               "stutter-trace-window.py": HERE / "stutter-trace-window.py",
               "stutter-observer.py": HERE / "stutter-observer.py"}
    return {name: _sha256(_inside(HERE, path, name + " source", require_file=True).read_bytes())
            for name, path in sources.items()}


def _window_summary(window_result):
    return {key: value for key, value in window_result.items()
            if key != "normalized_trace"}


def _base_result(request, input_hashes, source_hashes, steps, started, status):
    return {
        "schema": RESULT_SCHEMA,
        "owner_id": request.get("owner_id") if isinstance(request, dict) else None,
        "attempt_id": request.get("attempt_id") if isinstance(request, dict) else None,
        "status": status,
        "budget_ms": request.get("budget_ms") if isinstance(request, dict) else None,
        "elapsed_ms": _elapsed_ms(started),
        "source_root": SOURCE_ROOT_TEXT,
        "source_sha256": source_hashes,
        "input_sha256": input_hashes,
        "steps": steps,
        "runtime_ready": False,
        "host_fps": "UNSUPPORTED",
        "pixel_replay": "UNSUPPORTED_WITHOUT_PIXELS",
    }


def _atomic_publish(attempt_root, result, deadline, started):
    result_path = attempt_root / "result.json"
    temp_path = attempt_root / "result.json.pending"
    if result_path.exists() or result_path.is_symlink():
        raise AnalysisInputError("result.json already exists; refusing overwrite")
    if temp_path.exists() or temp_path.is_symlink():
        raise AnalysisInputError("result.json.pending already exists; refusing overwrite")

    result["deadline"] = {"budget_ms": result.get("budget_ms"),
                          "met_at_pre_publish_check": None}
    result["elapsed_ms"] = _elapsed_ms(started)
    payload = (json.dumps(result, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False) + "\n").encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(str(temp_path), flags, 0o600)
    try:
        with os.fdopen(fd, "wb", closefd=True) as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        met_at_pre_publish_check = time.monotonic() < deadline
        result["deadline"]["met_at_pre_publish_check"] = met_at_pre_publish_check
        if not met_at_pre_publish_check and result["status"] == "COMPLETE":
            # The unpublished temporary file can be rewritten safely. A
            # published result is never changed to repair a late deadline.
            result["status"] = "TIMED_OUT"
            result["error"] = {"stage": "result_publish", "kind": "DEADLINE_EXPIRED",
                               "message": "analysis deadline expired before atomic publish"}
        if not met_at_pre_publish_check:
            result["elapsed_ms"] = _elapsed_ms(started)
            payload = (json.dumps(result, sort_keys=True, separators=(",", ":"),
                                   ensure_ascii=False) + "\n").encode("utf-8")
            with temp_path.open("wb") as output:
                output.write(payload)
                output.flush()
                os.fsync(output.fileno())
        os.link(temp_path, result_path)
        directory_fd = os.open(str(attempt_root), os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temp_path.exists():
            temp_path.unlink()

    elapsed_after_publish = _elapsed_ms(started)
    late = time.monotonic() >= deadline
    if late:
        # Preserve the atomically published evidence. The direct caller must
        # reject admission because this worker returns nonzero after the limit.
        return False, elapsed_after_publish, True
    return result["status"] == "COMPLETE", elapsed_after_publish, False


def analyze_attempt(request_path):
    """Run the actual copied helper path and atomically publish one result."""
    started = time.monotonic()
    ledger = []
    request = None
    attempt_root = None
    deadline = started + MAX_BUDGET_MS / 1000.0
    input_hashes = {}
    source_hashes = {}
    result = None
    try:
        request, _request_file, attempt_root, request_bytes, deadline = _load_request(
            request_path, started)
        input_hashes["request_sha256"] = _sha256(request_bytes)
        _check_deadline(deadline, "request validation")
        guard, window, observer = _load_modules(attempt_root, ledger, deadline)
        source_hashes = _source_hashes()
        captures, trace_text, dump_provider, hashes = _read_attempt_inputs(
            attempt_root, guard, deadline)
        input_hashes.update(hashes)

        _check_deadline(deadline, "source oracle")
        oracle = _record_call(ledger, "source_binding", "guard.load_source_oracle",
                              guard.load_source_oracle)
        _check_deadline(deadline, "capture identity")
        identity_proof = _record_call(ledger, "capture_identity",
                                      "guard.validate_capture_sequence",
                                      guard.validate_capture_sequence,
                                      captures, oracle, dump_provider)
        if identity_proof.get("identity_complete") is not True:
            result = _base_result(request, input_hashes, source_hashes, ledger,
                                  started, "REJECTED")
            result["capture_identity"] = identity_proof
            result["error"] = {"stage": "capture_identity", "kind": "INCOMPLETE_COVERAGE",
                               "message": "copied guard did not prove all six ordered checkpoints"}
            raise _PublishedResult(result)

        marker_bytes = _extract_marker_bytes(guard, observer, dump_provider)
        _check_deadline(deadline, "trace window")
        window_result = _record_call(ledger, "trace_window", "window.adapt_first_window",
                                     window.adapt_first_window, trace_text)
        if window_result.get("kind") != "WINDOW_READY":
            result = _base_result(request, input_hashes, source_hashes, ledger,
                                  started, "REJECTED")
            result["capture_identity"] = identity_proof
            result["marker_bytes"] = marker_bytes
            result["window"] = _window_summary(window_result)
            result["error"] = {"stage": "trace_window", "kind": window_result.get("kind"),
                               "reason": window_result.get("reason")}
            raise _PublishedResult(result)

        normalized_trace = window_result["normalized_trace"]
        if not isinstance(normalized_trace, str):
            raise AnalysisInputError("window helper omitted normalized trace text")
        identity = {
            "receipt_sha256": observer.RECEIPT_SHA256,
            "rom_sha256": observer.ROM_SHA256,
            "profile": observer.PROFILE,
            "runtime_bytes_and_mapping_proved": True,
            "marker_bytes": marker_bytes,
        }
        _check_deadline(deadline, "observer analysis")
        observer_result = _record_call(ledger, "observer", "observer.analyze",
                                       observer.analyze, normalized_trace, identity)
        if not isinstance(observer_result, dict) or observer_result.get("kind") == "SETUP_REJECTED":
            result = _base_result(request, input_hashes, source_hashes, ledger,
                                  started, "REJECTED")
            result["capture_identity"] = identity_proof
            result["marker_bytes"] = marker_bytes
            result["window"] = _window_summary(window_result)
            result["observer"] = observer_result
            result["error"] = {"stage": "observer", "kind": "SETUP_REJECTED",
                               "reason": observer_result.get("reason") if isinstance(observer_result, dict) else
                               "observer returned a non-object result"}
            raise _PublishedResult(result)

        _check_deadline(deadline, "global origin mapping")
        observer_result = _record_call(ledger, "global_origin", "window.add_global_origin",
                                       window.add_global_origin, observer_result, window_result)
        result = _base_result(request, input_hashes, source_hashes, ledger,
                              started, "COMPLETE")
        result.update({
            "capture_identity": identity_proof,
            "marker_bytes": marker_bytes,
            "window": _window_summary(window_result),
            "normalized_trace_sha256": _sha256(normalized_trace.encode("utf-8")),
            "normalized_trace_bytes": len(normalized_trace.encode("utf-8")),
            "observer": observer_result,
        })
        _check_deadline(deadline, "result preparation")
    except _PublishedResult as published:
        result = published.result
    except AnalysisDeadlineExceeded as exc:
        if request is None or attempt_root is None:
            raise
        result = _base_result(request, input_hashes, source_hashes, ledger,
                              started, "TIMED_OUT")
        result["error"] = _exception_record(exc, "analysis")
    except Exception as exc:
        if request is None or attempt_root is None:
            raise
        status = "REJECTED" if isinstance(exc, (AnalysisInputError, ValueError)) else "ERROR"
        result = _base_result(request, input_hashes, source_hashes, ledger,
                              started, status)
        result["error"] = _exception_record(exc, "analysis")

    if attempt_root is None or result is None:
        raise AnalysisInputError("worker could not establish an attempt-bound result")
    admitted, published_elapsed, late = _atomic_publish(attempt_root, result, deadline, started)
    return result, admitted, published_elapsed, late


class _PublishedResult(Exception):
    """Carries a completed helper rejection through common atomic publication."""

    def __init__(self, result):
        super().__init__(result.get("status", "REJECTED"))
        self.result = result


def _emit_worker_error(exc):
    record = _exception_record(exc, "request")
    sys.stderr.write(json.dumps({"schema": RESULT_SCHEMA, "status": "ERROR",
                                 "runtime_ready": False, "error": record},
                                sort_keys=True) + "\n")


def main(argv=None):
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--request", required=True)
    args = parser.parse_args(argv)
    try:
        result, admitted, published_elapsed, late = analyze_attempt(args.request)
    except Exception as exc:
        _emit_worker_error(exc)
        return 2
    if not admitted:
        error = result.get("error", {
            "stage": "worker_exit", "kind": "ANALYSIS_NOT_COMPLETE"})
        if late:
            error = {"stage": "worker_exit", "kind": "DEADLINE_EXPIRED_AFTER_PUBLICATION",
                     "elapsed_ms": published_elapsed, "budget_ms": result.get("budget_ms")}
        sys.stderr.write(json.dumps({"schema": RESULT_SCHEMA,
                                     "owner_id": result.get("owner_id"),
                                     "attempt_id": result.get("attempt_id"),
                                     "status": result.get("status"),
                                     "error": error},
                                    sort_keys=True) + "\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
