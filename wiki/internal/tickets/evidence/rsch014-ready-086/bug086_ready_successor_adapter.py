#!/usr/bin/env python3
"""Bounded current-candidate BUG-086 succession adapter.

The scenario uses the retained E3 natural-entry/release/skull/deadline path and
the reviewed E6 synchronous run/wait observer. It never defaults to build/ or
the historical 5d963 E2 ROM. Static modes do not import the monitor or start an
emulator; live mode requires a parent-reviewed authorization receipt.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

PAGE_BYTES = 0x2000
PRIMARY_WAIT_LIMIT = 40.0
CAPTURE_RESERVE = 5.0
STOP_WAIT_SOCKET_MARGIN = 0.75
MONITOR_AUDIT: dict[str, object] = {
    "monitor_client_call_count": 0,
    "retained_call_receipts": [],
    "breakpoint_acknowledgements": [],
}
RUN_LEDGER: list[dict[str, object]] = []
INSTALLED_BREAKPOINTS: dict[int, int] = {}
PRIMARY_STREAM_FAILED = False
RUN_EPOCH = 0


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest_file(path: Path) -> str:
    return sha(path.read_bytes())


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[5]


def _platform_path(spec: dict[str, str]) -> Path:
    return Path(spec["windows" if os.name == "nt" else "wsl"])


def _run_git_head(path: Path) -> str:
    executable = shutil.which("git.exe") or shutil.which("git")
    if executable is None:
        raise RuntimeError("git executable is unavailable")
    git_path = str(path)
    if os.name != "nt" and executable.lower().endswith("git.exe"):
        git_path = subprocess.check_output(["wslpath", "-w", str(path)], text=True).strip()
    completed = subprocess.run([executable, "-C", git_path, "rev-parse", "HEAD"],
                               capture_output=True, text=True, timeout=5)
    if completed.returncode != 0:
        raise RuntimeError(f"git rev-parse HEAD failed: {completed.stdout}{completed.stderr}")
    return completed.stdout.strip()


def _write_new_json(path: Path, data: dict) -> None:
    if path.exists():
        raise SystemExit(f"refusing to overwrite existing receipt: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _check_hash(path: Path, expected: str, label: str, failures: list[str]) -> None:
    if not path.is_file():
        failures.append(f"missing {label}: {path}")
        return
    actual = digest_file(path)
    if actual != expected:
        failures.append(f"{label} SHA-256 mismatch: {actual} != {expected}")


def _preflight(worktree: Path, manifest_path: Path) -> dict[str, object]:
    manifest = load_json(manifest_path)
    root = _repo_root()
    failures: list[str] = []
    checks: dict[str, object] = {}
    if manifest.get("schema") != "ladybug-rsch014-ready-086-candidate-manifest-v1":
        failures.append("candidate manifest schema differs")
    checkout = manifest["candidate_source_checkout"]
    try:
        actual_head = _run_git_head(worktree)
        checks["source_checkout_head"] = {
            "actual": actual_head, "expected": checkout["head_commit"],
            "matches": actual_head == checkout["head_commit"],
        }
        if actual_head != checkout["head_commit"]:
            failures.append("candidate source checkout HEAD differs from manifest")
    except Exception as exc:
        failures.append(f"candidate source checkout HEAD check failed: {type(exc).__name__}: {exc}")

    artifact_dir = _platform_path(manifest["artifact_directory"]).resolve()
    artifact_manifest_path = artifact_dir / "artifacts.sha256.json"
    expected = manifest["artifacts"]
    checks["artifact_directory"] = str(artifact_dir)
    _check_hash(artifact_manifest_path, expected["artifact_hash_manifest_sha256"],
                "frozen artifact hash manifest", failures)
    if artifact_manifest_path.is_file():
        artifact_hashes = load_json(artifact_manifest_path)
        checks["frozen_artifact_entry_count"] = len(artifact_hashes)
        if len(artifact_hashes) != 103:
            failures.append(f"frozen artifact manifest entry count differs: {len(artifact_hashes)} != 103")
        for relative, wanted in artifact_hashes.items():
            candidate_path = (artifact_dir / relative).resolve()
            if candidate_path != artifact_dir and artifact_dir not in candidate_path.parents:
                failures.append(f"artifact manifest path escapes candidate directory: {relative}")
                continue
            _check_hash(candidate_path, wanted, f"frozen artifact {relative}", failures)
    file_pins = {
        "ladybug.rom": expected["full_rom_sha256"],
        "ladybug-runtime.rom": expected["runtime_rom_sha256"],
        "source-build-receipt.json": expected["source_build_receipt_sha256"],
        "ladybug-sparse-layout.json": expected["sparse_layout_sha256"],
        "ladybug-enemy-helper-page34.bin": expected["helper_sha256"],
        "ladybug-adaptive-banked.bin": expected["banked_b2_helper_sha256"],
        "ladybug-adaptive-active.s": expected["active_generated_source_sha256"],
        "ladybug-adaptive-active.bin": expected["active_relinked_binary_sha256"],
    }
    for relative, wanted in file_pins.items():
        _check_hash(artifact_dir / relative, wanted, f"candidate artifact {relative}", failures)
    rom_path = artifact_dir / "ladybug.rom"
    rom_hash = digest_file(rom_path) if rom_path.is_file() else None
    if rom_hash == manifest.get("historical_e2_rom_sha256"):
        failures.append("candidate manifest resolves to the historical isolated E2 ROM")
    if rom_hash != expected["full_rom_sha256"]:
        failures.append("candidate ROM does not match the explicit combined-candidate pin")
    checks["candidate_rom"] = {
        "sha256": rom_hash, "expected": expected["full_rom_sha256"],
        "is_historical_e2_rom": rom_hash == manifest.get("historical_e2_rom_sha256"),
        "matches_candidate": rom_hash == expected["full_rom_sha256"],
    }
    receipt_path = artifact_dir / "source-build-receipt.json"
    if receipt_path.is_file():
        receipt = load_json(receipt_path)
        checks["build_receipt"] = {
            "profile": receipt.get("profile"), "revision": receipt.get("revision"),
            "state": receipt.get("state"),
        }
        if receipt.get("profile") != "complete" or receipt.get("revision") != checkout["source_build_receipt_revision"]:
            failures.append("source build receipt profile/revision differs from candidate manifest")

    helper_path = artifact_dir / "ladybug-enemy-helper-page34.bin"
    helper = helper_path.read_bytes() if helper_path.is_file() else b""
    if len(helper) != expected["helper_length"]:
        failures.append(f"candidate E2 helper length differs: {len(helper)} != {expected['helper_length']}")
    layout_path = artifact_dir / "ladybug-sparse-layout.json"
    if layout_path.is_file():
        layout = load_json(layout_path)
        segment = next((item for item in layout.get("gmc", {}).get("segments", [])
                        if item.get("target") == "enemy_helper_page34"), None)
        if segment is None:
            failures.append("candidate sparse layout lacks enemy_helper_page34 segment")
        else:
            bank_path = artifact_dir / f"ladybug-gmc-bank{segment['bank']}-overflow.bin"
            if not bank_path.is_file():
                failures.append(f"candidate staged helper bank is missing: {bank_path}")
            else:
                offset, count = int(segment["source_offset"]), int(segment["count"])
                staged = bank_path.read_bytes()[offset:offset + count]
                checks["helper_stage"] = {
                    "bank": segment["bank"], "source_offset": offset, "count": count,
                    "destination_page": segment["destination_page"],
                    "destination_address": segment["destination_address"],
                    "staged_sha256": sha(staged), "authored_sha256": sha(helper),
                    "matches": staged == helper and count == expected["helper_length"],
                }
                if staged != helper or count != expected["helper_length"]:
                    failures.append("candidate authored/staged E2 helper bytes differ")

    context = manifest["e2_parent_context_patch"]
    context_path = root / context["path"]
    if not context_path.is_file():
        failures.append(f"missing 4d9ce9b E2 context patch: {context_path}")
    elif sha(context_path.read_bytes().replace(b"\r\n", b"\n")) != context["sha256"]:
        failures.append("4d9ce9b E2 context patch LF-normalized SHA-256 mismatch")
    audit_path = root / "wiki/internal/tickets/evidence/rsch014-ready-086/e2-parent-context-audit.json"
    if audit_path.is_file():
        audit = load_json(audit_path)
        checks["e2_context_audit"] = {
            "base_commit": audit.get("base_commit"), "patch_sha256": audit.get("context_patch_sha256"),
            "target_path_count": audit.get("target_path_count"),
            "includes_adaptive_runtime": audit.get("includes_adaptive_runtime"),
            "apply_check": audit.get("apply_check"),
        }
        if (audit.get("base_commit") != manifest.get("parent_ready_head") or
                audit.get("context_patch_sha256") != context["sha256"] or
                audit.get("target_path_count") != 8 or audit.get("includes_adaptive_runtime") is not False):
            failures.append("E2 context audit does not match the eight-path 4d9ce9b ownership patch")
    else:
        failures.append(f"missing E2 context audit: {audit_path}")

    sources = manifest["source_tools"]
    _check_hash(root / sources["retained_e3_observer"], sources["retained_e3_observer_sha256"],
                "retained E3 scenario source", failures)
    e6_source = root / sources["reviewed_e6_wait_stop_v3_observer"]
    if not e6_source.is_file():
        failures.append(f"missing reviewed E6 observer source: {e6_source}")
    elif sha(e6_source.read_bytes().replace(b"\r\n", b"\n")) != sources["reviewed_e6_wait_stop_v3_sha256"]:
        failures.append("reviewed E6 observer LF-normalized source SHA-256 mismatch")
    _check_hash(_platform_path(sources["xroar"]), sources["xroar"]["sha256"], "XRoar binary", failures)
    r10_profile_path = _platform_path(manifest["r10_profile_evidence"])
    _check_hash(r10_profile_path, manifest["r10_profile_evidence"]["sha256"],
                "R10 AD1 keyboard profile receipt", failures)

    support_json: dict[str, dict] = {}
    for item in manifest["supporting_evidence"]:
        support_path = _platform_path(item)
        _check_hash(support_path, item["sha256"], f"supporting evidence {support_path.name}", failures)
        if support_path.is_file():
            support_json[support_path.name] = load_json(support_path)
    b10_summary = support_json.get("summary.json", {})
    b10_review = support_json.get("independent-review.json", {})
    b2_rom = manifest["b2_baseline_reference"]["rom_sha256"]
    if b10_summary.get("tested_artifact", {}).get("rom_sha256") != b2_rom:
        failures.append("B10 reference ROM does not match candidate manifest B2 baseline")
    if b10_review.get("artifact", {}).get("rom_sha256") != b2_rom:
        failures.append("B10 independent review ROM does not match candidate manifest B2 baseline")
    profile_json = load_json(r10_profile_path) if r10_profile_path.is_file() else {}
    r10_capacity = profile_json.get("capacity", {})
    if (r10_capacity.get("E2_enemy_helper", {}).get("sha256") != expected["helper_sha256"] or
            r10_capacity.get("B2_adaptive_banked", {}).get("sha256") != expected["banked_b2_helper_sha256"] or
            r10_capacity.get("active_helper_b2_relink", {}).get("candidate_bytes") != 603):
        failures.append("R10 profile receipt does not carry pinned E2/B2 source/helper identities")
    checks["b2_and_r10_qualification"] = {
        "b10_baseline_rom_sha256": b2_rom,
        "candidate_rom_sha256": rom_hash,
        "candidate_is_not_baseline_rom": rom_hash != b2_rom,
        "e2_helper_sha256": expected["helper_sha256"],
        "b2_banked_helper_sha256": expected["banked_b2_helper_sha256"],
        "active_source_sha256": expected["active_generated_source_sha256"],
        "active_relinked_binary_sha256": expected["active_relinked_binary_sha256"],
        "r10_capacity_receipt_is_static_only": "not arcade cadence acceptance" in profile_json.get("claim", ""),
    }
    if rom_hash == b2_rom:
        failures.append("candidate ROM incorrectly aliases the frozen B2 baseline")

    return {
        "schema": "ladybug-rsch014-ready-086-static-preflight-v1",
        "status": "fail" if failures else "pass-static-only",
        "runtime_launched": False, "runtime_acceptance": False, "runtime_authorized": False,
        "adapter_sha256": digest_file(Path(__file__).resolve()),
        "candidate_manifest_sha256": digest_file(manifest_path),
        "candidate_profile": manifest.get("profile"), "candidate_rom_sha256": rom_hash,
        "checks": checks, "failure_count": len(failures), "failures": failures,
        "limits": [
            "R10 frozen artifacts are corrected fit/source evidence, not 6809 runtime acceptance.",
            "The B10 $2114 ROM is a distinct frozen baseline; the candidate ROM is identified separately.",
            "The 4d9ce9b E2 context patch was audited but not applied to production source or built here.",
            "No emulator, monitor socket, production source, build output, TMX, or acceptance state is modified by preflight.",
        ],
    }


def _validate_run_ack(result: object) -> dict:
    if not isinstance(result, dict) or result.get("ok") is not True:
        raise ValueError("run acknowledgement must contain ok=true")
    return result


def _validate_wait_sequence(run_request_id: object, wait_request_id: object) -> None:
    if (not isinstance(run_request_id, int) or isinstance(run_request_id, bool) or
            not isinstance(wait_request_id, int) or isinstance(wait_request_id, bool) or
            wait_request_id != run_request_id + 1):
        raise ValueError("wait_for_stop must immediately follow the acknowledged run call")


def _validate_call_receipt(receipt: object, method: str, request_id: int, result: dict) -> dict:
    if (not isinstance(receipt, dict) or receipt.get("method") != method or
            receipt.get("request_id") != request_id or receipt.get("outcome") != "ok"):
        raise ValueError(f"{method} call receipt does not match its request ID/outcome")
    envelope = receipt.get("response_envelope")
    if (not isinstance(envelope, dict) or envelope.get("id") != request_id or
            envelope.get("result") != result or "error" in envelope):
        raise ValueError(f"{method} raw response envelope does not match its request/result")
    return envelope


def _classify_stop(result: object, installed: dict[int, int]) -> dict:
    if not isinstance(result, dict):
        raise ValueError("wait_for_stop result must be an object")
    if result.get("reason") == "timeout":
        return {"status": "timeout", "marker": False}
    if result.get("reason") != "breakpoint":
        raise ValueError(f"wait_for_stop reason is not breakpoint: {result.get('reason')!r}")
    bp_id, pc = result.get("bp_id"), result.get("pc")
    if not isinstance(bp_id, int) or isinstance(bp_id, bool) or bp_id not in installed:
        raise ValueError(f"breakpoint ID is not acknowledged and installed: {bp_id!r}")
    if not isinstance(pc, int) or isinstance(pc, bool):
        raise ValueError("breakpoint PC is not an integer")
    expected_pc = installed[bp_id]
    if pc != expected_pc:
        raise ValueError(f"PC 0x{pc:04X} differs from breakpoint {bp_id} address 0x{expected_pc:04X}")
    return {"status": "breakpoint", "marker": True, "bp_id": bp_id, "pc": pc}


def _normal_group_start(part: int) -> int:
    if part < 1 or part > 255:
        raise ValueError(f"stage outside byte range: {part}")
    offset = (part - 1) & 7
    if offset >= 5:
        offset -= 5
    return offset


def _require_identity_bytes(expected: bytes, live: bytes, label: str) -> None:
    if not expected or live != expected:
        raise ValueError(f"{label} live bytes do not match the pinned artifact")


def _require_markers(required: set[str], observed: set[str]) -> None:
    missing = sorted(required - observed)
    if missing:
        raise RuntimeError("required marker missing: " + ", ".join(missing))


def _self_test(output: Path) -> int:
    cases: list[dict[str, object]] = []
    installed = {11: 0x15D5}
    def expect(name: str, action, accept: bool, status: str | None = None) -> None:
        try:
            actual = action()
            passed = accept and (status is None or actual.get("status") == status)
            detail = actual
        except Exception as exc:
            passed, detail = not accept, f"{type(exc).__name__}: {exc}"
        cases.append({"name": name, "expected": "accept" if accept else "reject", "passed": passed, "actual": detail})
    run_receipt = {"method": "run", "request_id": 69, "outcome": "ok", "response_envelope": {"id": 69, "result": {"ok": True}}}
    stop_result = {"reason": "breakpoint", "bp_id": 11, "pc": 0x15D5}
    stop_receipt = {"method": "wait_for_stop", "request_id": 70, "outcome": "ok", "response_envelope": {"id": 70, "result": stop_result}}
    expect("run acknowledgement accepted", lambda: _validate_run_ack({"ok": True}), True)
    expect("false run acknowledgement rejected", lambda: _validate_run_ack({"ok": False}), False)
    expect("adjacent wait request ID accepted", lambda: (_validate_wait_sequence(69, 70) or {"status": "adjacent"}), True, "adjacent")
    expect("nonadjacent wait request rejected", lambda: _validate_wait_sequence(69, 71), False)
    expect("run raw response correlated", lambda: _validate_call_receipt(run_receipt, "run", 69, {"ok": True}), True)
    expect("stale run response ID rejected", lambda: _validate_call_receipt(run_receipt, "run", 68, {"ok": True}), False)
    expect("wait raw response correlated", lambda: (_validate_wait_sequence(69, 70), _validate_call_receipt(stop_receipt, "wait_for_stop", 70, stop_result), {"status": "correlated"})[-1], True, "correlated")
    expect("stale wait response ID rejected", lambda: _validate_call_receipt(stop_receipt, "wait_for_stop", 69, stop_result), False)
    expect("installed ID and exact PC accepted", lambda: _classify_stop(stop_result, installed), True, "breakpoint")
    expect("timeout is not a marker", lambda: _classify_stop({"reason": "timeout"}, installed), True, "timeout")
    expect("stale breakpoint ID rejected", lambda: _classify_stop({"reason": "breakpoint", "bp_id": 9, "pc": 0xA8D2}, installed), False)
    expect("known breakpoint ID at wrong PC rejected", lambda: _classify_stop({"reason": "breakpoint", "bp_id": 11, "pc": 0xA8D2}, installed), False)
    expect("pause is not a marker", lambda: _classify_stop({"reason": "pause", "pc": 0x15D5}, installed), False)
    expect("missing breakpoint ID rejected", lambda: _classify_stop({"reason": "breakpoint", "pc": 0x15D5}, installed), False)
    expect("real timeout remains a failed marker", lambda: (_classify_stop({"reason": "timeout"}, installed), _require_markers({"helper", "front-pixel"}, {"helper"})), False)
    expect("wrong live marker bytes rejected", lambda: (_require_identity_bytes(b"\\x17\\x92\\xfd", b"\\x17\\x92\\xfe", "init callsite") or {"status": "identity-mismatch"}), False)
    expect("stage 9 group starts at type zero", lambda: {"start": _normal_group_start(9)}, True)
    expect("stage 10 group starts at type one", lambda: {"start": _normal_group_start(10)}, True)
    expect("stage 13 group starts at type four", lambda: {"start": _normal_group_start(13)}, True)
    expect("stage 14 wraps group to type zero", lambda: {"start": _normal_group_start(14)}, True)
    expect("missing front replay marker rejected", lambda: _require_markers({"stage-9", "front-pixel", "front-replay"}, {"stage-9", "front-pixel"}), False)
    receipt = {"schema": "ladybug-rsch014-ready-086-adapter-selftest-v2",
               "status": "pass" if all(row["passed"] for row in cases) else "fail",
               "runtime_launched": False, "monitor_imported": False, "cases": cases}
    _write_new_json(output, receipt)
    print(json.dumps({"status": receipt["status"], "case_count": len(cases),
                      "receipt": str(output), "runtime_launched": False}, sort_keys=True))
    return 0 if receipt["status"] == "pass" else 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bounded BUG-086 succession observer using explicit candidate artifacts.")
    sub = parser.add_subparsers(dest="command", required=True)
    test = sub.add_parser("self-test", help="test RPC/stop-marker checks with fake replies; no monitor import")
    test.add_argument("--output", type=Path, required=True)
    preflight = sub.add_parser("preflight", help="verify frozen source/artifact pins offline; no emulator or monitor import")
    preflight.add_argument("--worktree", type=Path, required=True)
    preflight.add_argument("--candidate-manifest", type=Path, required=True)
    preflight.add_argument("--output", type=Path, required=True)
    live = sub.add_parser("live", help="run five separately bounded phases; requires parent dispatch receipt")
    live.add_argument("--worktree", type=Path, required=True)
    live.add_argument("--candidate-manifest", type=Path, required=True)
    live.add_argument("--authorization", type=Path, required=True)
    live.add_argument("--output", type=Path, required=True)
    return parser


ARGS = _parser().parse_args()
ROOT = _repo_root()
if ARGS.command == "self-test":
    raise SystemExit(_self_test(ARGS.output))
if ARGS.command == "preflight":
    preflight_result = _preflight(ARGS.worktree.resolve(), ARGS.candidate_manifest.resolve())
    _write_new_json(ARGS.output, preflight_result)
    print(json.dumps({"status": preflight_result["status"], "failure_count": preflight_result["failure_count"],
                      "receipt": str(ARGS.output), "runtime_launched": False}, sort_keys=True))
    if preflight_result["status"] != "pass-static-only":
        raise SystemExit(2)
else:
    worktree = ARGS.worktree.resolve()
    output = ARGS.output.resolve()
    candidate_manifest_path = ARGS.candidate_manifest.resolve()
    authorization = load_json(ARGS.authorization.resolve())
    adapter_hash = digest_file(Path(__file__).resolve())
    if authorization.get("runtime_authorized") is not True:
        raise SystemExit("runtime not launched: parent dispatch receipt runtime_authorized is not true")
    if authorization.get("parent_review_status") != "parent-reviewed-and-approved":
        raise SystemExit("runtime not launched: parent review status is not approved")
    if authorization.get("candidate_manifest_sha256") != digest_file(candidate_manifest_path):
        raise SystemExit("runtime not launched: candidate manifest SHA-256 differs from parent dispatch receipt")
    if authorization.get("adapter_sha256") != adapter_hash:
        raise SystemExit("runtime not launched: adapter SHA-256 differs from parent dispatch receipt")
    if authorization.get("phase_deadline_seconds") != 45 or authorization.get("phase_count") != 5:
        raise SystemExit("runtime not launched: dispatch receipt does not authorize five 45-second phases")
    if output.exists():
        raise SystemExit(f"runtime not launched: refusing to overwrite existing output {output}")
    gate = _preflight(worktree, candidate_manifest_path)
    if gate["status"] != "pass-static-only":
        raise SystemExit("runtime not launched: candidate offline preflight failed")
    candidate_manifest = load_json(candidate_manifest_path)
    BUILD = _platform_path(candidate_manifest["artifact_directory"]).resolve()
    ROM = BUILD / "ladybug.rom"
    RESIDENT = BUILD / "ladybug-runtime.rom"
    ENEMY = BUILD / "ladybug-enemy-runtime.rom"
    HELPER = BUILD / "ladybug-enemy-helper-page34.bin"
    PRESENTATION = BUILD / "ladybug-presentation-runtime.bin"
    ACTIVE = BUILD / "ladybug-adaptive-active.bin"
    LAYOUT = BUILD / "ladybug-sparse-layout.json"
    MAZE = worktree / "assets/arcade/maze.json"
    XROAR = _platform_path(candidate_manifest["source_tools"]["xroar"])
    RET = 0x18FC
    sys.path.insert(0, str(worktree / "scripts"))
    import verify_bug011_runtime as runtime
    import verify_bug009_monitor_input as monitor

    _original_monitor_call = monitor.MonitorClient.call
    _audited_methods = {"events.subscribe", "get_run_state", "list_breakpoints",
                        "set_breakpoint", "clear_breakpoint", "run", "wait_for_stop"}
    def _audited_monitor_call(self, method: str, params: dict | None = None,
                              timeout: float = 20.0) -> dict:
        request_id = self.next_id
        started = time.monotonic()
        events_before = list(self.events)
        self.events.clear()
        received: list[dict] = []
        original_read = self._read
        def capture_read(deadline: float) -> dict:
            message = original_read(deadline)
            received.append(message)
            return message
        self._read = capture_read
        result = None
        error = None
        outcome = "ok"
        try:
            result = _original_monitor_call(self, method, params, timeout)
            return result
        except Exception as exc:
            outcome = "error"
            error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            self._read = original_read
            events_drained = list(self.events)
            self.events.clear()
            response = next((message for message in received if message.get("id") == request_id), None)
            MONITOR_AUDIT["monitor_client_call_count"] = int(MONITOR_AUDIT["monitor_client_call_count"]) + 1
            if method in _audited_methods or events_before or events_drained:
                receipt = {
                    "request_id": request_id, "method": method, "params": params,
                    "timeout_seconds": timeout, "outcome": outcome, "error": error,
                    "response_envelope": response, "result": result,
                    "events_before_call": events_before,
                    "events_drained_by_MonitorClient_call": events_drained,
                    "elapsed_seconds": round(time.monotonic() - started, 6),
                }
                MONITOR_AUDIT["retained_call_receipts"].append(receipt)
                if method in ("set_breakpoint", "clear_breakpoint"):
                    MONITOR_AUDIT["breakpoint_acknowledgements"].append({
                        "request_id": request_id, "method": method, "params": params,
                        "acknowledged": outcome == "ok", "response_envelope": response,
                        "result": result, "error": error,
                    })
    monitor.MonitorClient.call = _audited_monitor_call

    def _latest_rpc_receipt(method: str, request_id: int) -> dict:
        for receipt in reversed(MONITOR_AUDIT["retained_call_receipts"]):
            if receipt.get("method") == method and receipt.get("request_id") == request_id:
                return receipt
        raise RuntimeError(f"missing retained {method} receipt for request {request_id}")

    def _capture_timeout_snapshot(client, phase_deadline: float) -> dict[str, object]:
        snapshot: dict[str, object] = {}
        for key, method in (("run_state", "get_run_state"), ("breakpoints", "list_breakpoints"),
                            ("subscription_refresh", "events.subscribe")):
            left = phase_deadline - time.monotonic() - CAPTURE_RESERVE
            if left <= 0.05:
                snapshot[f"{key}_error"] = "capture reserve reached"
                continue
            try:
                params = {"kinds": ["bp"]} if method == "events.subscribe" else None
                snapshot[key] = client.call(method, params, timeout=min(0.5, left))
            except Exception as exc:
                snapshot[f"{key}_error"] = f"{type(exc).__name__}: {exc}"
        if isinstance(snapshot.get("subscription_refresh"), dict):
            snapshot["subscriber_dropped_events"] = snapshot["subscription_refresh"].get("dropped_events")
        return snapshot

    def _run_until_stop(client, label: str, phase_deadline: float, timeout: float) -> dict[str, int]:
        global PRIMARY_STREAM_FAILED, RUN_EPOCH
        if not INSTALLED_BREAKPOINTS:
            raise RuntimeError(f"{label}: no acknowledged breakpoint defines an allowed stop")
        started = time.monotonic()
        run_id = client.next_id
        record: dict[str, object] = {
            "label": label, "run_epoch": RUN_EPOCH + 1, "run_request_id": run_id,
            "expected_breakpoints_by_id": {str(k): v for k, v in INSTALLED_BREAKPOINTS.items()},
            "notifications_are_secondary_evidence": True, "acknowledged": False,
        }
        RUN_LEDGER.append(record)
        phase_left = min(phase_deadline - CAPTURE_RESERVE - started, timeout, PRIMARY_WAIT_LIMIT)
        if phase_left <= 0.1:
            raise TimeoutError(f"phase bound reached before {label} run")
        try:
            run_result = client.call("run", timeout=min(1.0, phase_left))
            run_receipt = _latest_rpc_receipt("run", run_id)
            record["run_receipt"] = run_receipt
            _validate_run_ack(run_result)
            _validate_call_receipt(run_receipt, "run", run_id, run_result)
            record["acknowledged"] = True
            record["run_result"] = run_result
            RUN_EPOCH += 1
            record["run_epoch"] = RUN_EPOCH
            wait_id = client.next_id
            _validate_wait_sequence(run_id, wait_id)
            record["wait_for_stop_request_id"] = wait_id
            wait_left = min(phase_deadline - CAPTURE_RESERVE - time.monotonic(),
                            started + phase_left - time.monotonic(), timeout - time.monotonic(), PRIMARY_WAIT_LIMIT)
            if wait_left <= STOP_WAIT_SOCKET_MARGIN + 0.05:
                record["wait_not_sent"] = "less than transport margin remains"
                raise TimeoutError(f"capture reserve reached before {label} wait_for_stop")
            server_timeout_ms = max(1, int((wait_left - STOP_WAIT_SOCKET_MARGIN) * 1000))
            record["server_timeout_ms"] = server_timeout_ms
            stop_result = client.call("wait_for_stop", {"timeout_ms": server_timeout_ms}, timeout=wait_left)
            stop_receipt = _latest_rpc_receipt("wait_for_stop", wait_id)
            record["wait_for_stop_receipt"] = stop_receipt
            record["wait_for_stop_result"] = stop_result
            _validate_call_receipt(stop_receipt, "wait_for_stop", wait_id, stop_result)
            classification = _classify_stop(stop_result, INSTALLED_BREAKPOINTS)
            record["stop_classification"] = classification
            if classification["status"] == "timeout":
                record["timeout_state_snapshot"] = _capture_timeout_snapshot(client, phase_deadline)
                PRIMARY_STREAM_FAILED = True
                raise TimeoutError(f"{label}: wait_for_stop returned reason=timeout")
            record["elapsed_seconds"] = round(time.monotonic() - started, 6)
            record["stop_marker"] = {"run_epoch": RUN_EPOCH, "reason": "breakpoint",
                                     "bp_id": classification["bp_id"], "pc": classification["pc"]}
            return record["stop_marker"]
        except Exception as exc:
            record["failure"] = f"{type(exc).__name__}: {exc}"
            record["elapsed_seconds"] = round(time.monotonic() - started, 6)
            record["primary_stream_reused_after_error"] = False
            if isinstance(exc, (TimeoutError, OSError, ConnectionError)):
                PRIMARY_STREAM_FAILED = True
            raise


def main() -> None:
    main_symbols = runtime.symbols(BUILD / "ladybug.map")
    enemy_symbols = runtime.symbols(BUILD / "ladybug-enemy-runtime.map")
    presentation_symbols = runtime.symbols(BUILD / "ladybug-presentation-runtime.map")
    active_symbols = runtime.symbols(BUILD / "ladybug-adaptive-active.map")
    helper_symbols = runtime.symbols(BUILD / "ladybug-enemy-helper-page34.map")
    receipt = load_json(BUILD / "source-build-receipt.json")
    e2 = load_json(ROOT / "wiki/internal/tickets/evidence/rsch014-E2/current-fit-readiness-20261002.json")
    contract = load_json(ROOT / "wiki/internal/tickets/evidence/rsch014-E3/probe-contract-20261002.json")
    layout = load_json(LAYOUT)

    rom = ROM.read_bytes()
    resident = RESIDENT.read_bytes()
    enemy = ENEMY.read_bytes()
    helper = HELPER.read_bytes()
    presentation = PRESENTATION.read_bytes()
    active = ACTIVE.read_bytes()
    resident_window = 0x3E00
    segment = next(item for item in layout["gmc"]["segments"]
                   if item["target"] == "enemy_helper_page34")
    bank_path = BUILD / f"ladybug-gmc-bank{segment['bank']}-overflow.bin"
    bank = bank_path.read_bytes()
    stage_start = int(segment["source_offset"])
    stage_end = stage_start + int(segment["count"])
    staged_helper = bank[stage_start:stage_end]
    candidate_artifacts = candidate_manifest["artifacts"]
    if (len(helper) != candidate_artifacts["helper_length"] or staged_helper != helper or
            sha(rom) != candidate_artifacts["full_rom_sha256"] or
            digest_file(BUILD / "source-build-receipt.json") != candidate_artifacts["source_build_receipt_sha256"] or
            sha(helper) != candidate_artifacts["helper_sha256"] or
            sha(helper) != e2["helper_layout"]["helper_sha256"]):
        raise RuntimeError("prelaunch exact candidate manifest/authored/staged E2 identity mismatch")
    head = contract["artifact_identity"]["head_commit"]

    e: dict[str, object] = {
        "schema": "ladybug-rsch014-ready-086-succession-adapter-v1",
        "started_on": "2026-10-03",
        "status": "incomplete",
        "phase_deadline_seconds": 45,
        "runtime_observer": "reviewed E6 synchronous run acknowledgement plus wait_for_stop; raw response/event ledger; acknowledged breakpoint IDs",
        "artifact_identity": {
            "worktree": str(worktree), "source_contract_head_commit": head,
            "source_overlay_base_commit": contract["artifact_identity"].get("source_overlay_base"),
            "prototype_patch_sha256": contract["artifact_identity"].get("prototype_patch_sha256"),
            "parent_ready_head": candidate_manifest["parent_ready_head"],
            "candidate_source_checkout_head": candidate_manifest["candidate_source_checkout"]["head_commit"],
            "source_build_receipt_revision": candidate_manifest["candidate_source_checkout"]["source_build_receipt_revision"],
            "candidate_manifest_sha256": digest_file(candidate_manifest_path),
            "candidate_role": candidate_manifest["artifact_role"],
            "candidate_rom_is_historical_e2_rom": sha(rom) == candidate_manifest["historical_e2_rom_sha256"],
            "profile": "AD1 keyboard complete; LADYBUG_ADAPTIVE=1, LADYBUG_INPUT=keyboard",
            "rom_sha256": sha(rom), "source_build_receipt_sha256": digest_file(BUILD / "source-build-receipt.json"),
            "resident_sha256": sha(resident), "enemy_module_sha256": sha(enemy),
            "presentation_sha256": sha(presentation), "active_stage_sha256": sha(active),
            "helper_sha256": sha(helper), "helper_length": len(helper),
            "helper_segment": {
                "bank": segment["bank"], "bank_sha256": sha(bank),
                "source_offset": segment["source_offset"], "staged_sha256": sha(staged_helper),
                "destination_page": segment["destination_page"],
                "destination_address": segment["destination_address"],
                "count": segment["count"], "layout_sha256": digest_file(LAYOUT),
            },
            "resident_map_sha256": digest_file(BUILD / "ladybug.map"),
            "enemy_map_sha256": digest_file(BUILD / "ladybug-enemy-runtime.map"),
            "helper_map_sha256": digest_file(BUILD / "ladybug-enemy-helper-page34.map"),
            "active_map_sha256": digest_file(BUILD / "ladybug-adaptive-active.map"),
            "e2_receipt": "wiki/internal/tickets/evidence/rsch014-E2/current-fit-readiness-20261002.json",
        },
        "phases": [],
        "phase_contract": candidate_manifest["phase_contract"],
        "synchronous_run_stop_ledger": RUN_LEDGER,
        "monitor_audit": MONITOR_AUDIT,
        "claims": {
            "runtime_acceptance": False,
            "integrated_production_acceptance": False,
            "natural_full_maze_progression": False,
            "stage9_precondition": "Actual cold credited gameplay and actual last-bonus collision/popup handoff; then STAGE is forced from the reached next part to 8 and the real next_stage routine initializes Part 9. Parts 2-8 are explicitly skipped.",
            "release_precondition": "The real perimeter_timer_tick routine is reached by its active-game caller; only BOX_TIMER/BOX_INDEX are forced at the byte-verified routine entry to provoke its scheduled release path.",
            "death_precondition": "Two release-created actors from normal Part 9 groups 0 and 1 are inspected at fixture setup, then repositioned to legal one-edge predecessors of two distinct runtime-created Part 9 skulls; player is placed on a distant open cell and held with PLAYER_MANUAL=1 and neutral JOY_DIR.",
        },
        "no_profile_or_bound_changes": True,
    }

    process = None
    client = None
    deadline = 0.0
    current_phase: dict[str, object] | None = None

    def begin_phase(name: str, contract: str) -> None:
        nonlocal deadline, current_phase
        deadline = time.monotonic() + 45.0
        current_phase = {"name": name, "contract": contract, "started_monotonic": time.monotonic(), "status": "running"}
        e["phases"].append(current_phase)

    def check_deadline(marker: str) -> float:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(f"{current_phase['name']}: {marker} not observed or completed by its 45-second deadline")
        return remaining

    def monitor_call(method: str, params: dict | None = None, label: str | None = None) -> dict:
        if PRIMARY_STREAM_FAILED:
            raise RuntimeError("primary monitor stream failed; no further primary request is permitted")
        left = deadline - time.monotonic() - CAPTURE_RESERVE
        if left <= 0.05:
            raise TimeoutError(f"capture reserve reached before {label or method}")
        return client.call(method, params, timeout=min(left, PRIMARY_WAIT_LIMIT))

    def read(address: int, length: int = 1) -> bytes:
        if address < 0xC000 and address + length > 0xA000:
            if address < 0xA000 or address + length > 0xC000:
                raise RuntimeError(f"logical read crosses PAR5 window: ${address:04X}+{length}")
            par5 = bytes.fromhex(monitor_call("read_memory", {"addr": 0xFFA5, "length": 1}, "PAR5 state-window check")["data"])[0]
            if par5 != 0x34:
                raise RuntimeError(f"logical read at ${address:04X} requires PAR5=$34, got ${par5:02X}")
        return bytes.fromhex(monitor_call("read_memory", {"addr": address, "length": length}, f"read ${address:04X}")["data"])

    def read_byte(address: int) -> int:
        return read(address, 1)[0]

    def read_word(address: int) -> int:
        return int.from_bytes(read(address, 2), "big")

    def phys_page(page: int, offset: int, length: int) -> bytes:
        return bytes.fromhex(monitor_call("read_memory", {
            "space": "physical", "addr": page * PAGE_BYTES + offset, "length": length,
        }, f"physical read page ${page:02X}")["data"])

    def phys_window(page: int, address: int, length: int) -> bytes:
        return phys_page(page, address - 0xA000, length)

    def write(address: int, data: bytes) -> None:
        if address < 0xC000 and address + len(data) > 0xA000:
            if address < 0xA000 or address + len(data) > 0xC000:
                raise RuntimeError(f"logical write crosses PAR5 window: ${address:04X}+{len(data)}")
            par5 = bytes.fromhex(monitor_call("read_memory", {"addr": 0xFFA5, "length": 1}, "PAR5 state-window check")["data"])[0]
            if par5 != 0x34:
                raise RuntimeError(f"logical write at ${address:04X} requires PAR5=$34, got ${par5:02X}")
        monitor_call("write_memory", {"addr": address, "data": data.hex()}, f"write ${address:04X}")

    def write_byte(address: int, value: int) -> None:
        write(address, bytes([value & 0xFF]))

    def set_break(address: int) -> int:
        result = monitor_call("set_breakpoint", {"addr": address, "kind": "exec"}, f"set breakpoint ${address:04X}")
        if (not isinstance(result.get("id"), int) or result.get("addr") != address or result.get("kind") != "exec"):
            raise RuntimeError(f"set_breakpoint acknowledgement does not match ${address:04X}: {result}")
        request_id = client.next_id - 1
        _validate_call_receipt(_latest_rpc_receipt("set_breakpoint", request_id), "set_breakpoint", request_id, result)
        INSTALLED_BREAKPOINTS[result["id"]] = address
        return result["id"]

    def clear_break(ident: int) -> None:
        if PRIMARY_STREAM_FAILED:
            return
        result = monitor_call("clear_breakpoint", {"id": ident}, f"clear breakpoint {ident}")
        if result.get("ok") is not True:
            raise RuntimeError(f"clear_breakpoint acknowledgement is not ok for {ident}: {result}")
        request_id = client.next_id - 1
        _validate_call_receipt(_latest_rpc_receipt("clear_breakpoint", request_id), "clear_breakpoint", request_id, result)
        INSTALLED_BREAKPOINTS.pop(ident, None)

    def assert_marker_code(address: int, label: str) -> None:
        if address == RET:
            if read_byte(0xFFA0) != 0x38:
                raise RuntimeError(f"{label}: controlled return/stack PAR0 is not physical page $38")
            if read(RET, 2) != b"\x20\xFE":
                raise RuntimeError(f"{label}: controlled return stub differs from BRA -2")
            return
        images = (
            (0xC000, resident, "resident", None),
            (0x0800, enemy, "enemy module", (0xFFA0, 0x38)),
            (0x1900, presentation, "presentation module", (0xFFA0, 0x38)),
            (0x038F, active, "active stage", (0xFFA0, 0x38)),
            (0xA8A0, helper, "page-$34 helper", (0xFFA5, 0x34)),
        )
        for base, image, name, mapping in images:
            offset = address - base
            if 0 <= offset < len(image):
                if name == "resident":
                    par6 = read_byte(0xFFA6)
                    par7 = read_byte(0xFFA7)
                    if par6 != 0x3E or par7 != 0x3F:
                        raise RuntimeError(f"{label}: resident marker mapping differs: PAR6={par6:02X}, PAR7={par7:02X}")
                if mapping is not None and read_byte(mapping[0]) != mapping[1]:
                    raise RuntimeError(f"{label}: {name} mapping register ${mapping[0]:04X} differs")
                count = min(12, len(image) - offset)
                expected = image[offset:offset + count]
                if read(address, count) != expected:
                    raise RuntimeError(f"{label}: live {name} bytes differ at ${address:04X}")
                return
        raise RuntimeError(f"{label}: no current build image covers marker ${address:04X}")

    def go(address: int, label: str) -> dict[str, int]:
        remaining = check_deadline(label)
        ident = set_break(address)
        try:
            hit = _run_until_stop(client, label, deadline, min(remaining, 12.0))
            if hit.get("pc") != address:
                raise RuntimeError(f"{label}: expected PC ${address:04X}, got {hit}")
            regs = monitor_call("read_registers", label=f"read registers at ${address:04X}")
            if regs.get("pc") != hit.get("pc"):
                raise RuntimeError(f"{label}: live register PC differs from synchronous stop reply: {regs}")
            assert_marker_code(address, label)
            return regs
        finally:
            clear_break(ident)

    def step_past_marker(address: int, label: str) -> int:
        check_deadline(label)
        monitor_call("step_instruction", {"n": 1}, label=label)
        regs = monitor_call("read_registers", label=label + " register read")
        if regs["pc"] == address:
            raise RuntimeError(f"{label}: one instruction did not advance PC ${address:04X}")
        return regs["pc"]

    def assert_resident(address: int, length: int) -> bytes:
        par6 = read_byte(0xFFA6)
        par7 = read_byte(0xFFA7)
        if par6 != 0x3E or par7 != 0x3F:
            raise RuntimeError(f"resident mapping differs at ${address:04X}: PAR6={par6:02X}, PAR7={par7:02X}")
        data = read(address, length)
        expected = resident[address - 0xC000:address - 0xC000 + length]
        if data != expected:
            raise RuntimeError(f"resident live code mismatch at ${address:04X}")
        return data

    def assert_enemy_cpu(address: int, length: int) -> bytes:
        if read_byte(0xFFA0) != 0x38:
            raise RuntimeError(f"enemy module PAR0 is not page $38 at ${address:04X}")
        data = read(address, length)
        expected = enemy[address - 0x0800:address - 0x0800 + length]
        if data != expected:
            raise RuntimeError(f"enemy-module live code mismatch at ${address:04X}")
        return data

    def assert_active_cpu(address: int, length: int) -> bytes:
        if read_byte(0xFFA0) != 0x38:
            raise RuntimeError(f"active-stage PAR0 is not page $38 at ${address:04X}")
        data = read(address, length)
        expected = active[address - 0x038F:address - 0x038F + length]
        if data != expected:
            raise RuntimeError(f"active-stage live code mismatch at ${address:04X}")
        return data

    def assert_helper_mapping() -> dict[str, object]:
        par5 = read_byte(0xFFA5)
        par0 = read_byte(0xFFA0)
        physical = phys_window(0x34, 0xA8A0, len(helper))
        mapped = read(0xA8A0, len(helper))
        if par0 != 0x38 or par5 != 0x34 or physical != helper or mapped != helper:
            raise RuntimeError(f"page-$34 helper delivery/mapping mismatch: PAR0={par0:02X}, PAR5={par5:02X}, physical={sha(physical)}, mapped={sha(mapped)}")
        return {"PAR0": par0, "PAR5": par5, "authored_helper_sha256": sha(helper),
                "staged_helper_sha256": sha(staged_helper),
                "physical_helper_sha256": sha(physical), "mapped_helper_sha256": sha(mapped),
                "all_equal": True}

    def call_from_current_boundary(address: int, label: str) -> None:
        if read_byte(0xFFA0) != 0x38:
            raise RuntimeError(f"{label}: low RAM/stack PAR0 is not physical page $38")
        regs = monitor_call("read_registers", label=label + " initial registers")
        stack_before = read(0x1E00, 0x200)
        stub_before = read(RET, 2)
        stack_floor_guard = bytes([0xA5]) * 16
        try:
            write(0x1FFE, bytes([RET >> 8, RET & 0xFF]))
            write(0x1E00, stack_floor_guard)
            write(RET, b"\x20\xFE")
            monitor_call("write_registers", {
                "pc": address, "s": 0x1FFE, "dp": 0, "cc": 0x50,
                "a": 0, "b": 0, "x": 0, "y": 0, "u": 0,
            }, label=label + " controlled-call registers")
            returned = go(RET, label + " actual routine return")
            if returned["s"] != 0x2000:
                raise RuntimeError(f"{label}: return stack is unbalanced at ${returned['s']:04X}")
            if read(0x1E00, len(stack_floor_guard)) != stack_floor_guard:
                raise RuntimeError(f"{label}: controlled routine crossed the $1E00 stack floor")
        finally:
            try:
                client.call("write_memory", {"addr": RET, "data": stub_before.hex()}, timeout=2.0)
            finally:
                try:
                    client.call("write_memory", {"addr": 0x1E00, "data": stack_before.hex()}, timeout=2.0)
                finally:
                    client.call("write_registers", {key: regs[key] for key in ("a", "b", "cc", "dp", "x", "y", "u", "s", "pc")}, timeout=2.0)

    def worklist(parser_start: int, first_entry: bool = False) -> dict[str, int]:
        pc = monitor_call("read_registers", label="worklist initial registers")["pc"]
        if pc == main_symbols["ad_dispatch_work"]:
            return go(main_symbols["mainloop"], "completed active gameplay worklist")
        if pc == main_symbols["mainloop"]:
            go(parser_start, "presentation/parser entry")
            return go(main_symbols["mainloop"], "completed active gameplay worklist")
        if first_entry:
            go(main_symbols["ad_dispatch_work"], "active gameplay work entry")
            return go(main_symbols["mainloop"], "completed first active gameplay worklist")
        go(main_symbols["ad_dispatch_work"], "active gameplay work entry")
        return go(main_symbols["mainloop"], "completed active gameplay worklist")

    def front_preview_snapshot(label: str) -> dict[str, object]:
        front = read_byte(main_symbols["FB_FRONT_ID"])
        back = read_byte(main_symbols["FB_BACK_ID"])
        pending = read_byte(main_symbols["FB_RENDER_PENDING"])
        gime_offset = read_byte(0xFF9D)
        if front not in (0, 1) or front == back or pending != 0:
            raise RuntimeError(f"{label}: FRONT/BACK publication is incomplete: {front}/{back}, pending={pending}")
        expected_offset = 0xC0 if front == 0 else 0xB0
        if gime_offset != expected_offset or read_byte(0xFF9E) != 0:
            raise RuntimeError(f"{label}: GIME scanout does not identify FRONT owner {front}")
        saved_pars = read(0xFFA1, 4)
        base_page = 0x30 if front == 0 else 0x2C
        try:
            for index in range(4):
                write_byte(0xFFA1 + index, base_page + index)
            surface = read(0x2000, 30720)
        finally:
            write(0xFFA1, saved_pars)
        offset = enemy_symbols["ENEMY_FB"] - 0x2000
        if not 0 <= offset <= len(surface) - 8 - 15 * 160:
            raise RuntimeError(f"{label}: preview pixel anchor is outside the visible FRONT surface")
        pixels = b"".join(surface[offset + row * 160:offset + row * 160 + 8] for row in range(16))
        if not any(pixels):
            raise RuntimeError(f"{label}: preview FRONT pixel marker is empty")
        return {
            "label": label, "FRONT": front, "BACK": back, "FB_PENDING": pending,
            "GIME_VOFF1": gime_offset, "FRAMES": read_word(main_symbols["FRAMES"]),
            "FB_COMMIT_SEQ": read_word(main_symbols["FB_COMMIT_SEQ"]),
            "surface_sha256": sha(surface), "preview_anchor": enemy_symbols["ENEMY_FB"],
            "preview_pixels_sha256": sha(pixels), "preview_pixels_bytes": len(pixels),
        }

    try:
        candidate_rom_sha256 = sha(rom)
        if (receipt.get("profile") != "complete" or
                candidate_rom_sha256 != candidate_artifacts["full_rom_sha256"] or
                candidate_rom_sha256 == candidate_manifest["historical_e2_rom_sha256"]):
            raise RuntimeError("runtime image is not the explicitly pinned combined R10 AD1 candidate")
        process, client = runtime.launch_fast(monitor, XROAR, ROM)
        e["runtime_instance"] = {"pid": process.pid, "monitor_peer": client.sock.getpeername(), "launch_mode": "private, headless, null audio, GMC 512K, no-ratelimit"}

        # Phase 1: reuse the cold coin/credit/start route and settle the real entry marker.
        begin_phase("cold-credited-start", "45 seconds maximum: cold attract, live coin edge, settled credit, Start edge, initial active game entry and exact source/runtime identity.")
        start = presentation_symbols["start_screen"]
        regs = go(start, "cold attract start_screen")
        pc = regs["pc"]
        presentation_site = read(pc, 12)
        if presentation_site != presentation[pc - 0x1900:pc - 0x1900 + len(presentation_site)]:
            raise RuntimeError("cold presentation PC bytes do not match presentation runtime image")
        if regs["a"] != 0:
            raise RuntimeError(f"cold attract request missing: A={regs['a']:02X}")
        live_resident = read(0xC000, resident_window)
        live_enemy = read(0x0800, len(enemy))
        live_presentation = read(0x1900, len(presentation))
        physical_helper = phys_window(0x34, 0xA8A0, len(helper))
        if (read_byte(0xFFA6) != 0x3E or read_byte(0xFFA7) != 0x3F or
                live_resident != resident[:resident_window] or live_enemy != enemy or live_presentation != presentation):
            raise RuntimeError("cold loader-delivered resident/enemy/presentation image differs from current build")
        if physical_helper != helper:
            raise RuntimeError("cold loader-delivered physical page-$34 helper differs from current staged artifact")
        current_phase["identity_proof"] = {
            "resident_live_sha256": sha(live_resident), "resident_expected_sha256": sha(resident[:resident_window]),
            "enemy_live_sha256": sha(live_enemy), "enemy_expected_sha256": sha(enemy),
            "presentation_live_sha256": sha(live_presentation), "presentation_expected_sha256": sha(presentation),
            "helper_physical_sha256": sha(physical_helper), "helper_staged_sha256": sha(staged_helper),
            "cold_PC": pc, "cold_PC_bytes_sha256": sha(presentation_site), "cold_A": regs["a"],
            "all_equal": True,
        }
        go(presentation_symbols["attract_tick"], "live attract tick")
        monitor_call("inject_key", {"key": 5, "action": "press"}, "coin key press")
        regs = go(start, "credit-screen start_screen")
        monitor_call("inject_key", {"key": 5, "action": "release"}, "coin key release")
        if regs["a"] != 3:
            raise RuntimeError(f"coin edge did not request credit screen: A={regs['a']:02X}")
        credits = presentation_symbols["PRES_CREDITS"]
        credit_tick = presentation_symbols["credit_tick"]
        regs = go(credit_tick, "settled-credit tick")
        if read_byte(credits) != 1:
            raise RuntimeError(f"actual coin path did not create one credit: {read_byte(credits)}")
        settled_ticks = 0
        while read_byte(0x00D4) != 0 or read_byte(0x0091) != 0:
            go(credit_tick, "high-score/credit presentation settle tick")
            settled_ticks += 1
            if settled_ticks >= 240:
                raise RuntimeError("high-score/credit handoff did not settle in 240 ticks")
        current_phase["credit_settle"] = {
            "settled_ticks": settled_ticks, "PRES_CREDITS": read_byte(credits),
            "transient_state": read_byte(0x00D4), "FB_PENDING": read_byte(0x0091),
            "PC": monitor_call("read_registers", label="credit-settle PC read")["pc"],
        }
        monitor_call("inject_key", {"key": 1, "action": "press"}, "Start key press")
        dispatch = main_symbols["ad_dispatch_work"]
        dispatch_regs = go(dispatch, "credited-game active dispatcher")
        monitor_call("inject_key", {"key": 1, "action": "release"}, "Start key release")
        current_phase["start_dispatch_state"] = {
            "PC": dispatch_regs["pc"], "A": dispatch_regs["a"],
            "PRES_MODE": read_byte(presentation_symbols["PRES_MODE"]),
            "STAGE": read_byte(main_symbols["STAGE"]), "PRES_CREDITS": read_byte(credits),
            "INITIAL_ENTRY_STATE": read_byte(main_symbols["INITIAL_ENTRY_STATE"]),
            "FB_PENDING": read_byte(0x0091),
        }
        live_stage = read(0x038F, len(active))
        if live_stage != active:
            raise RuntimeError("installed AD1 active stage differs from current active-stage build")
        parser_start = 0xC000 + resident.index(bytes([0xBD, 0x19, 0x00]),
                                               main_symbols["mainloop"] - 0xC000,
                                               main_symbols["ad_dispatch_active"] - 0xC000)
        stage = main_symbols["STAGE"]
        initial_entry = main_symbols["INITIAL_ENTRY_STATE"]
        entry_samples = 0
        while read_byte(initial_entry) != 0:
            worklist(parser_start)
            entry_samples += 1
            if entry_samples > 80:
                raise RuntimeError("natural credited initial-entry marker absent within 80 worklists")
        final_start_state = {
            "PC": monitor_call("read_registers", label="credited-game PC read")["pc"],
            "PRES_MODE": read_byte(presentation_symbols["PRES_MODE"]),
            "STAGE": read_byte(stage), "PRES_CREDITS": read_byte(credits),
            "INITIAL_ENTRY_STATE": read_byte(initial_entry),
            "entry_worklists": entry_samples,
        }
        current_phase["credited_gameplay_postcondition"] = final_start_state
        if final_start_state["PC"] != main_symbols["mainloop"]:
            raise RuntimeError(f"credited start did not stop at the exact resident C116 mainloop marker: {final_start_state}")
        assert_resident(main_symbols["mainloop"], 8)
        # The real credit settle records one credit before Start. Start consumes it;
        # require zero credits after the active-game entry has settled.
        if (final_start_state["PRES_MODE"] != 0 or final_start_state["STAGE"] != 1 or
                final_start_state["PRES_CREDITS"] != 0):
            raise RuntimeError(f"credited active gameplay postcondition differs: {final_start_state}")
        current_phase.update({"status": "pass", "markers": {
            "attract_coin_start": True, "settled_credit_before_start": 1,
            "credits_after_start": 0, "mode": 0,
            "stage": 1, "initial_entry_state": 0, "entry_worklists": entry_samples,
            "resident_C116_PC": final_start_state["PC"],
            "active_stage_live_sha256": sha(live_stage), "parser_start": parser_start,
        }})

        # Phase 2: real legal last-bonus event; then the real Part 9 initializer and natural renderer path.
        begin_phase("last-bonus-to-part9-helper-preview", "45 seconds maximum: force only the legal late-game bonus counters and approach geometry, run the real pickup/popup/handoff, then force STAGE=8 and call real next_stage once. Require natural draw_enemy_stage helper entry and normal Part 9 preview.")
        maze = load_json(MAZE)
        entity_count = read_byte(main_symbols["ENTITY_COUNT"])
        entity_table = main_symbols["ENTITY_TABLE"]
        entity_bytes = read(entity_table, entity_count * 4)
        pickup = None
        for offset in range(0, len(entity_bytes), 4):
            x, y, kind = entity_bytes[offset:offset + 3]
            if kind not in (2, 3):
                continue
            for direction, dx, dy, reverse in ((0, 0, 1, 4), (1, -1, 0, 8), (2, 0, -1, 1), (3, 1, 0, 2)):
                px, py = x + dx, y + dy
                if not (0 <= px < 24 and 0 <= py < 24):
                    continue
                nav_target = maze["maze_nav"][y][x]
                nav_pred = maze["maze_nav"][py][px]
                gates = maze["gate_owner"]
                if (nav_target & reverse and nav_pred & (1 << direction) and
                        gates[y][x] == 0 and gates[py][px] == 0):
                    pickup = {"record": offset // 4, "x": x, "y": y, "kind": kind,
                              "predecessor": [px, py], "direction": direction,
                              "nav_target": nav_target, "nav_predecessor": nav_pred}
                    break
            if pickup:
                break
        if pickup is None:
            raise RuntimeError("no legal ungated last-bonus pickup approach in actual Part 1 entities")
        write_byte(main_symbols["DOTS_LEFT"], 0)
        write_byte(main_symbols["BONUS_LEFT"], 1)
        px, py = pickup["predecessor"]
        direction = pickup["direction"]
        stride = (-320, 1, 320, -1)[direction]
        player_base = 0x2000 + (py * 8 - 8) * 160 + (px + 7) * 4
        write(main_symbols["PLAYER_CELL_X"], bytes([px, py]))
        write_byte(main_symbols["PLAYER_DIR"], direction)
        write_byte(main_symbols["PLAYER_WANT"], direction)
        write_byte(main_symbols["PLAYER_STEP"], 3)
        write(main_symbols["PLAYER_FB"], (player_base + 3 * stride).to_bytes(2, "big"))
        initial_part = read_byte(stage)
        initial_bonus = read_byte(main_symbols["BONUS_LEFT"])
        last_bonus_rows = []
        handoff = None
        for worklist_index in range(58):
            before_part = read_byte(stage)
            worklist(parser_start)
            row = {
                "index": worklist_index,
                "stage": read_byte(stage), "mode": read_byte(presentation_symbols["PRES_MODE"]),
                "bonus_left": read_byte(main_symbols["BONUS_LEFT"]),
                "pickup_timer": read_byte(main_symbols["PICKUP_TIMER"]),
                "entity_type": read_byte(entity_table + pickup["record"] * 4 + 2),
                "fault": read_byte(0xBD3A), "from_stage": before_part,
            }
            last_bonus_rows.append(row)
            if row["fault"] != 0:
                raise RuntimeError(f"last-bonus scheduler fault: {row}")
            if row["mode"] == 1 and row["stage"] == initial_part + 1:
                handoff = row
                break
        if handoff is None:
            raise RuntimeError("actual last-bonus Part handoff marker absent within 58 worklists")
        e["claims"]["actual_last_bonus"] = {
            "forced_precondition": {"initial_part": initial_part, "DOTS_LEFT": 0, "BONUS_LEFT": initial_bonus,
                                    "legal_pickup": pickup, "player_steps_from_contact": 3},
            "handoff": handoff, "worklists": last_bonus_rows,
            "scope": "Real player movement/pickup/popup/next-part handoff under explicit forced late-part counters; no full-maze earning claim.",
        }
        # Complete the presentation handoff to ordinary credited gameplay without forcing mode/state bytes.
        if read_byte(presentation_symbols["PRES_MODE"]) == 1:
            go(main_symbols["ad_dispatch_work"], "post-bonus active dispatcher")
        transition_samples = 0
        while (read_byte(presentation_symbols["PRES_MODE"]) != 0 or read_byte(initial_entry) != 0):
            if transition_samples >= 400:
                raise RuntimeError("post-bonus live mode/entry did not settle within 400 worklists")
            worklist(parser_start)
            transition_samples += 1
        if read_byte(stage) != initial_part + 1:
            raise RuntimeError("post-bonus stage changed before forced Part 9 setup")
        e["claims"]["actual_last_bonus"]["settled_gameplay"] = {
            "mode": read_byte(presentation_symbols["PRES_MODE"]), "stage": read_byte(stage),
            "initial_entry_state": read_byte(initial_entry), "worklists_after_handoff": transition_samples,
        }
        go(main_symbols["mainloop"], "stable boundary before forced Part 9 init")
        assert_resident(main_symbols["next_stage"], 24)
        write_byte(stage, 8)
        call_from_current_boundary(main_symbols["next_stage"], "forced Part 9 next_stage")
        if read_byte(stage) != 9 or read_byte(main_symbols["STAGE_PENDING"]) != 0:
            raise RuntimeError("real next_stage did not initialize forced Part 9")
        count = read_byte(main_symbols["ENTITY_COUNT"])
        entity_bytes_p9 = read(entity_table, count * 4)
        skulls = [{"record": index, "x": entity_bytes_p9[index * 4], "y": entity_bytes_p9[index * 4 + 1],
                   "type": entity_bytes_p9[index * 4 + 2]}
                  for index in range(count) if entity_bytes_p9[index * 4 + 2] == 1]
        if len(skulls) != 5 or read_byte(main_symbols["ENEMY_ACTIVE"]) != 0:
            raise RuntimeError(f"Part 9 real init did not produce five live skulls and dormant enemies: {skulls}")
        # Prove the natural draw_enemy_stage LBSR, its caller, destination mapping, and normal preview.
        expected_call = assert_enemy_cpu(enemy_symbols["draw_enemy_stage"], 3)
        if expected_call != bytes.fromhex("1792fd"):
            raise RuntimeError(f"draw_enemy_stage helper call bytes differ: {expected_call.hex()}")
        helper_call_hits = []
        target_regs = None
        for _ in range(12):
            regs = go(helper_symbols["enemy_frame_number"], "natural enemy_frame_number helper entry")
            helper_proof = assert_helper_mapping()
            pc_bytes = read(regs["pc"], 12)
            expected_bytes = helper[regs["pc"] - 0xA8A0:regs["pc"] - 0xA8A0 + len(pc_bytes)]
            if pc_bytes != expected_bytes:
                raise RuntimeError("live helper entry bytes differ from authored/staged/page-$34 artifact")
            ret = read_word(regs["s"])
            hit_record = {"PC": regs["pc"], "return_address": ret,
                          "helper_PC_bytes_sha256": sha(pc_bytes), "page34": helper_proof}
            helper_call_hits.append(hit_record)
            if ret == enemy_symbols["draw_enemy_stage"] + 3:
                target_regs = regs
                break
            step_past_marker(helper_symbols["enemy_frame_number"], "advance past non-target helper call")
        if target_regs is None:
            raise RuntimeError(f"natural draw_enemy_stage call did not reach helper entry: {helper_call_hits}")
        preview_regs = go(helper_symbols["efn_preview_pack"], "normal Part 9 preview pack")
        preview_bytes = read(preview_regs["pc"], 8)
        preview_expected = helper[preview_regs["pc"] - 0xA8A0:preview_regs["pc"] - 0xA8A0 + len(preview_bytes)]
        preview_pending = read_byte(main_symbols["ENEMY_PENDING_TYPE"])
        preview_cursor = read_byte(main_symbols["ENEMY_NORMAL_CURSOR"])
        if (read_byte(0xFFA5) != 0x34 or preview_bytes != preview_expected or
                preview_regs["a"] != 0 or preview_cursor != 0 or preview_pending != 0xFF or
                read_byte(stage) != 9 or
                read_word(preview_regs["s"]) != helper_symbols["efn_finish"]):
            raise RuntimeError("Part 9 normal preview selector/stack/mapping postcondition differs")
        current_phase.update({"status": "pass", "markers": {
            "part9_stage": read_byte(stage), "part9_live_skull_count": len(skulls),
            "skulls": skulls, "forced_precondition": "stage set to 8, actual next_stage called once; Parts 2-8 skipped",
            "helper_entry_PC": target_regs["pc"], "draw_enemy_stage_return": read_word(target_regs["s"]),
            "draw_enemy_stage_live_call_bytes": expected_call.hex(), "helper_entry_hits": helper_call_hits,
            "preview_PC": preview_regs["pc"], "preview_PC_bytes_sha256": sha(preview_bytes),
            "preview_A_selected_type": preview_regs["a"], "pending_type": preview_pending,
            "normal_cursor": preview_cursor,
            "preview_return_address": read_word(preview_regs["s"]),
            "PAR5": read_byte(0xFFA5), "helper_mapping": helper_proof,
        }})

        # Phase 3: use real perimeter releases, then two actual enemy skull checks in one real enemy tick.
        begin_phase("ordered-part9-types-and-latest-two-skull-override", "45 seconds maximum: prove natural Part 9 previews/releases for logical types 1 through 4, legally position type-3/type-4 records at distinct skull predecessors, then observe one actual gameplay enemy_tick.")
        assert_resident(main_symbols["perimeter_timer_tick"], 16)
        assert_enemy_cpu(enemy_symbols["enemy_release_impl"], 24)
        release_hits = []
        for group_type in range(4):
            preview_regs = go(helper_symbols["efn_preview_pack"], f"natural Part 9 preview before logical type {group_type + 1} release")
            preview_pending = read_byte(main_symbols["ENEMY_PENDING_TYPE"])
            preview_cursor = read_byte(main_symbols["ENEMY_NORMAL_CURSOR"])
            if (preview_regs["a"] != group_type or preview_pending >= 0x80 or preview_cursor != group_type):
                raise RuntimeError(f"ordered normal preview {group_type + 1} differs: A={preview_regs['a']:02X}, pending={preview_pending:02X}, cursor={preview_cursor}")
            timer_regs = go(main_symbols["perimeter_timer_tick"], "real perimeter_timer_tick entry before forced due values")
            timer_pc = timer_regs["pc"]
            timer_bytes = read(timer_pc, 10)
            timer_expected = resident[timer_pc - 0xC000:timer_pc - 0xC000 + len(timer_bytes)]
            if timer_bytes != timer_expected:
                raise RuntimeError("perimeter_timer_tick live code differs from current resident artifact")
            pending_before = read_byte(main_symbols["ENEMY_PENDING_TYPE"])
            cursor_before = read_byte(main_symbols["ENEMY_NORMAL_CURSOR"])
            box_before = [read_byte(main_symbols[name]) for name in ("BOX_TIMER", "BOX_INDEX", "BOX_PHASE")]
            expected_raw = (group_type << 4) | 1
            expected_pending_before = 0xFF if group_type == 0 else (~(((group_type - 1) << 4) | 1) & 0xFF)
            if pending_before != expected_pending_before or cursor_before != group_type:
                raise RuntimeError(f"normal release {group_type} precondition pending/cursor differs: {pending_before:02X}/{cursor_before}")
            write_byte(main_symbols["BOX_TIMER"], 1)
            write_byte(main_symbols["BOX_INDEX"], 91)
            release_regs = go(enemy_symbols["enemy_release_impl"], "scheduled release implementation entry")
            release_code = assert_enemy_cpu(release_regs["pc"], 20)
            if read_byte(0xFFA0) != 0x38:
                raise RuntimeError("enemy module PAR0 does not map page $38 at release implementation")
            # The resident timer path returns through the enemy_release wrapper before the adaptive stage resumes.
            active_return = read_word(release_regs["s"])
            if active_return != main_symbols["enemy_release"] + 3:
                raise RuntimeError(f"release implementation caller is not resident enemy_release wrapper: ${active_return:04X}")
            after_timer = go(active_symbols["atb_after_timers"], "scheduled release returned through active timer path")
            records_now = read(main_symbols["ENEMY_TABLE"], 32)
            row = records_now[group_type * 8:(group_type + 1) * 8]
            raw_type = row[0]
            pending_after = read_byte(main_symbols["ENEMY_PENDING_TYPE"])
            cursor_after = read_byte(main_symbols["ENEMY_NORMAL_CURSOR"])
            box_after = [read_byte(main_symbols[name]) for name in ("BOX_TIMER", "BOX_INDEX", "BOX_PHASE")]
            expected_pending_after = (~expected_raw) & 0xFF
            if (raw_type != expected_raw or read_byte(main_symbols["ENEMY_ACTIVE"]) != group_type + 1 or
                    cursor_after != group_type + 1 or pending_after != expected_pending_after or
                    (pending_after & 0x80) == 0):
                raise RuntimeError(f"real release did not seed normal group type {group_type}: {row.hex()}")
            if box_after != [3, 0, box_before[2] ^ 1]:
                raise RuntimeError(f"scheduled timer reload/index/phase rollover differs: before={box_before}, after={box_after}")
            release_hits.append({"group_type": group_type, "logical_type": group_type + 1,
                                 "preview_A_before_release": preview_regs["a"],
                                 "preview_pending_before_release": preview_pending,
                                 "preview_cursor_before_release": preview_cursor,
                                 "timer_entry": timer_pc, "timer_PC_bytes_sha256": sha(timer_bytes),
                                 "release_impl": release_regs["pc"], "release_code_sha256": sha(release_code),
                                 "release_return": active_return, "record": row.hex(),
                                 "pending_before": pending_before, "pending_after": pending_after,
                                 "active_count": read_byte(main_symbols["ENEMY_ACTIVE"]),
                                 "cursor_before": cursor_before, "normal_cursor": cursor_after,
                                 "box_before": box_before, "box_after": box_after,
                                 "active_return_PC": after_timer["pc"]})
        if len(release_hits) != 4:
            raise RuntimeError("four ordered Part 9 release-created actor records absent")

        # Select two different legal one-edge skull arrivals for released logical types 3 and 4.
        record_targets = []
        used_skull_records: set[int] = set()
        for slot in (2, 3):
            entity_records = read(entity_table, read_byte(main_symbols["ENTITY_COUNT"]) * 4)
            candidates = []
            for offset in range(0, len(entity_records), 4):
                ex, ey, kind = entity_records[offset:offset + 3]
                if kind != 1 or offset // 4 in used_skull_records:
                    continue
                for direction in range(4):
                    dx, dy = ((0, -1), (1, 0), (0, 1), (-1, 0))[direction]
                    tx, ty = ex, ey
                    px, py = tx - dx, ty - dy
                    if not (0 <= px < 24 and 0 <= py < 24):
                        continue
                    nav_from = maze["maze_nav"][py][px]
                    nav_to = maze["maze_nav"][ty][tx]
                    reverse = (direction + 2) & 3
                    if (nav_from & (1 << direction) and nav_to & (1 << reverse) and
                            maze["gate_owner"][py][px] == 0 and maze["gate_owner"][ty][tx] == 0):
                        candidates.append({"actor_slot": slot, "record": offset // 4, "target": [tx, ty],
                                           "predecessor": [px, py], "direction": direction,
                                           "nav_from": nav_from, "nav_to": nav_to})
            if not candidates:
                raise RuntimeError(f"no legal ungated Part 9 skull predecessor for actor slot {slot}")
            target = candidates[0]
            used_skull_records.add(target["record"])
            record_targets.append(target)

        # Find a distant, open, ungated player cell outside both actors' contact neighborhoods.
        actor_cells = [target["predecessor"] for target in record_targets]
        safe_player = None
        for y in range(23, -1, -1):
            for x in range(23, -1, -1):
                if not (maze["maze_nav"][y][x] & 0x0F) or maze["gate_owner"][y][x] != 0:
                    continue
                if all(abs(x - ax) + abs(y - ay) >= 6 for ax, ay in actor_cells):
                    safe_player = [x, y]
                    break
            if safe_player:
                break
        if safe_player is None:
            raise RuntimeError("no distant legal player cell available for forced skull scenario")

        # At a stable mainloop boundary, set only explicit actor/player fixture state.
        go(main_symbols["mainloop"], "stable boundary for legal skull-arrival fixture")
        pre_death_front = front_preview_snapshot("Part 9 normal preview after ordered releases")
        actor_state_before_fixture = []
        if read_byte(main_symbols["ENEMY_ACTIVE"]) != 4:
            raise RuntimeError("all four ordered release-created actors must still be live at the fixture boundary")
        for slot, target in ((item["actor_slot"], item) for item in record_targets):
            px, py = target["predecessor"]
            direction = target["direction"]
            dx = (px - 12) * 4
            dy = (py - 12) * 4 * 320
            center = 0x57EC + dx + dy
            stride = (-320, 1, 320, -1)[direction]
            pointer = center + stride * 3
            tx, ty = target["target"]
            target_center = 0x57EC + (tx - 12) * 4 + (ty - 12) * 4 * 320
            if center + stride * 4 != target_center:
                raise RuntimeError(f"actor fixture geometry does not reach its target: {target}")
            existing = read(main_symbols["ENEMY_TABLE"] + slot * 8, 8)
            expected_kind = (slot << 4) | 1
            if existing[0] != expected_kind:
                raise RuntimeError(f"actor slot {slot} no longer has its release-created type: {existing.hex()}")
            actual_x, actual_y = existing[4], existing[5]
            actual_progress, actual_direction = existing[3], existing[7]
            actual_pointer = (existing[1] << 8) | existing[2]
            if (actual_x >= 24 or actual_y >= 24 or actual_progress >= 4 or
                    actual_direction not in (0, 1, 2, 3, 0xFF) or
                    not 0x2000 <= actual_pointer < 0xA000):
                raise RuntimeError(f"released actor slot {slot} has invalid live position/state at fixture boundary: {existing.hex()}")
            actual_stride = (-320, 1, 320, -1)[actual_direction if actual_direction != 0xFF else 3]
            actual_cell_center = 0x57EC + (actual_x - 12) * 4 + (actual_y - 12) * 4 * 320
            expected_live_pointer = actual_cell_center + actual_stride * actual_progress
            if actual_pointer != expected_live_pointer:
                raise RuntimeError(f"released actor slot {slot} pointer/cell/progress geometry differs: actual=${actual_pointer:04X}, expected=${expected_live_pointer:04X}, record={existing.hex()}")
            actor_state_before_fixture.append({
                "slot": slot, "actor_type": existing[0] >> 4,
                "record": existing.hex(), "cell_xy": [actual_x, actual_y],
                "framebuffer_pointer": actual_pointer, "progress": actual_progress,
                "direction": actual_direction, "geometry_pointer_expected": expected_live_pointer,
            })
            record = bytes([expected_kind, pointer >> 8, pointer & 0xFF, 3, px, py, 0, direction])
            write(main_symbols["ENEMY_TABLE"] + slot * 8, record)
        sx, sy = safe_player
        player_base = 0x2000 + (sy * 8 - 8) * 160 + (sx + 7) * 4
        write(main_symbols["PLAYER_CELL_X"], bytes([sx, sy]))
        write_byte(main_symbols["PLAYER_MANUAL"], 1)
        write_byte(main_symbols["JOY_DIR"], 0xFF)
        write_byte(main_symbols["PLAYER_DIR"], 0xFF)
        write_byte(main_symbols["PLAYER_WANT"], 0xFF)
        write(main_symbols["PLAYER_FB"], player_base.to_bytes(2, "big"))
        write_byte(main_symbols["PLAYER_TICK_PENDING"], 0)
        if read_byte(main_symbols["DEATH_STATE"]) != 0:
            raise RuntimeError("player death already active before forced skull-arrival tick")
        player_before_enemy_tick = [read_byte(main_symbols[name]) for name in ("PLAYER_CELL_X", "PLAYER_CELL_Y")]
        if player_before_enemy_tick != safe_player:
            raise RuntimeError(f"neutral-manual player fixture did not retain its selected cell: {player_before_enemy_tick}")
        before_entities = read(entity_table, read_byte(main_symbols["ENTITY_COUNT"]) * 4)
        before_box = [read_byte(main_symbols[name]) for name in ("BOX_TIMER", "BOX_INDEX", "BOX_PHASE")]

        # Verify source/staged/active mapping before using the adaptive labels for the actual tick.
        active_tick = active_symbols["adaptive_tick_binding"]
        active_after_enemy = active_symbols["atb_after_player"]
        active_call_bytes = assert_active_cpu(active_tick + 0x32, 3)  # JSR enemy_tick in the current active image.
        if (active_call_bytes[0] != 0xBD or
                int.from_bytes(active_call_bytes[1:], "big") != main_symbols["enemy_tick"]):
            raise RuntimeError(f"active main-game enemy_tick call does not target current enemy map symbol: {active_call_bytes.hex()}")
        skull_label = enemy_symbols["est_skull"]
        assert_enemy_cpu(skull_label, 24)
        tick_regs = go(main_symbols["enemy_tick"], "actual active gameplay enemy_tick entry")
        return_pc = read_word(tick_regs["s"])
        if return_pc != active_tick + 0x35:
            raise RuntimeError(f"enemy_tick caller is not current adaptive active game logic: ${return_pc:04X}")
        write_byte(main_symbols["LAST_FRAME"], 0)
        write_byte(main_symbols["ENEMY_TIMER"], 1)
        write_byte(main_symbols["PLAYER_TICK_PENDING"], 0)
        skull_id = set_break(skull_label)
        skull_hits = []
        matching = []
        try:
            for _ in range(80):
                remaining = check_deadline("two actual enemy skull interactions")
                hit = _run_until_stop(client, "two actual enemy skull interactions", deadline, remaining)
                if hit.get("pc") != skull_label:
                    raise RuntimeError(f"skull interaction marker missing: {hit}")
                regs = monitor_call("read_registers", label="read skull-test registers")
                if regs.get("pc") != hit.get("pc"):
                    raise RuntimeError("live est_skull register PC differs from synchronous stop reply")
                pc_bytes = read(skull_label, 16)
                expected_pc_bytes = enemy[skull_label - 0x0800:skull_label - 0x0800 + len(pc_bytes)]
                if pc_bytes != expected_pc_bytes or read_byte(0xFFA0) != 0x38:
                    raise RuntimeError("live est_skull bytes/PAR0 differ from exact enemy-module artifact")
                actor_ptr = read_word(enemy_symbols["ENEMY_PTR"])
                actor = read(actor_ptr, 8)
                entity_ptr = regs["u"]
                entity = read(entity_ptr, 4)
                row = {"PC": regs["pc"], "actor_ptr": actor_ptr, "actor_record": actor.hex(),
                       "entity_ptr": entity_ptr, "entity_record": entity.hex(),
                       "live_PC_bytes_sha256": sha(pc_bytes),
                       "matches": actor[4] == entity[0] and actor[5] == entity[1] and entity[2] == 1}
                skull_hits.append(row)
                if row["matches"]:
                    matching.append({"actor_ptr": actor_ptr, "actor_type": actor[0] >> 4,
                                     "entity_ptr": entity_ptr, "entity_xy": list(entity[:2])})
                if len(matching) == 2:
                    break
                step_past_marker(skull_label, "advance past current skull-test entry")
            else:
                raise RuntimeError("two actual est_skull matching actor/entity entries absent within 80 checks")
        finally:
            clear_break(skull_id)
        post_tick = go(active_after_enemy, "post-enemy tick pre-perimeter state boundary")
        after_entities = read(entity_table, read_byte(main_symbols["ENTITY_COUNT"]) * 4)
        after_box = [read_byte(main_symbols[name]) for name in ("BOX_TIMER", "BOX_INDEX", "BOX_PHASE")]
        player_after_enemy_tick = [read_byte(main_symbols[name]) for name in ("PLAYER_CELL_X", "PLAYER_CELL_Y")]
        if (len(matching) != 2 or matching[0]["actor_ptr"] == matching[1]["actor_ptr"] or
                [item["actor_type"] for item in matching] != [2, 3] or
                read_byte(main_symbols["ENEMY_ACTIVE"]) != 2 or
                read_byte(main_symbols["ENEMY_PENDING_TYPE"]) != 0x30 or
                read_byte(main_symbols["ENEMY_NORMAL_CURSOR"]) != 4 or
                read_byte(main_symbols["DEATH_STATE"]) != 0 or before_box != after_box or
                player_after_enemy_tick != player_before_enemy_tick):
            raise RuntimeError("real two-skull override/pending/box-state postconditions differ")
        cleared_targets = []
        for target in record_targets:
            offset = target["record"] * 4
            before_type = before_entities[offset + 2]
            after_type = after_entities[offset + 2]
            if before_type != 1 or after_type != 0:
                raise RuntimeError(f"target skull entity was not cleared: {target}")
            cleared_targets.append({**target, "before_type": before_type, "after_type": after_type})
        # Complete the real post-death render path, then compare the den preview
        # on FRONT and after one natural owner replay. The pixel anchor is the
        # authored lower-nest framebuffer origin, not a RAM selector marker.
        go(main_symbols["mainloop"], "publish latest-death preview to FRONT")
        death_front = front_preview_snapshot("Part 9 latest type-4 death preview")
        if death_front["preview_pixels_sha256"] == pre_death_front["preview_pixels_sha256"]:
            raise RuntimeError("latest-death preview did not change the actual FRONT den pixels")
        worklist(parser_start)
        replay_front = front_preview_snapshot("Part 9 natural alternate-owner preview replay")
        if (replay_front["preview_pixels_sha256"] != death_front["preview_pixels_sha256"] or
                replay_front["FRONT"] == death_front["FRONT"] or
                replay_front["FB_COMMIT_SEQ"] == death_front["FB_COMMIT_SEQ"]):
            raise RuntimeError("latest-death FRONT pixels did not replay coherently on the alternate owner")
        current_phase.update({"status": "pass", "markers": {
            "normal_releases": release_hits, "legal_skull_targets": cleared_targets,
            "actor_state_at_fixture_boundary": actor_state_before_fixture,
            "safe_stationary_player": safe_player, "player_before_enemy_tick": player_before_enemy_tick,
            "player_after_enemy_tick": player_after_enemy_tick, "enemy_tick_PC": tick_regs["pc"],
            "enemy_tick_return_pc": return_pc, "enemy_tick_call_bytes": active_call_bytes.hex(),
            "actual_skull_test_entries": skull_hits, "matching_entries": matching,
            "post_tick_PC": post_tick["pc"], "box_before_enemy_tick": before_box,
            "box_after_enemy_tick_before_perimeter": after_box,
            "active_enemies_after": read_byte(main_symbols["ENEMY_ACTIVE"]),
            "pending_override": read_byte(main_symbols["ENEMY_PENDING_TYPE"]),
            "normal_cursor": read_byte(main_symbols["ENEMY_NORMAL_CURSOR"]),
            "normal_release_order": [item["logical_type"] for item in release_hits],
            "death_state": read_byte(main_symbols["DEATH_STATE"]),
            "front_preview_pixels": {"before_override": pre_death_front,
                                     "after_latest_type4_death": death_front,
                                     "after_alternate_owner_replay": replay_front},
        }})

        # Phase 4: the real due timer consumes the latest type-4 override, then resumes type 1.
        begin_phase("existing-deadline-type4-replacement-and-type1-resumption", "45 seconds maximum: observe pending type 4, force only BOX_TIMER/BOX_INDEX at verified real perimeter_timer_tick entry, consume the override without moving the cursor, then force the next existing deadline to release normal type 1 into a reused slot.")
        deadline_releases = []
        for expected_group in (3, 0):
            expected_display_type = expected_group + 1
            preview_regs = go(helper_symbols["efn_preview_pack"], f"pending/normal preview before type {expected_display_type} timed release")
            expected_preview_a = expected_group
            expected_preview_pending = 0x30 if expected_group == 3 else 0xCE
            preview_pending = read_byte(main_symbols["ENEMY_PENDING_TYPE"])
            preview_cursor = read_byte(main_symbols["ENEMY_NORMAL_CURSOR"])
            if (preview_regs["a"] != expected_preview_a or preview_pending != expected_preview_pending or preview_cursor != 4):
                raise RuntimeError(f"timed preview type {expected_display_type} differs: A={preview_regs['a']:02X}, pending={preview_pending:02X}, cursor={preview_cursor}")
            timer_regs = go(main_symbols["perimeter_timer_tick"], "real perimeter_timer_tick entry for replacement deadline")
            timer_pc = timer_regs["pc"]
            timer_bytes = read(timer_pc, 12)
            if timer_bytes != resident[timer_pc - 0xC000:timer_pc - 0xC000 + len(timer_bytes)]:
                raise RuntimeError("replacement timer marker bytes differ from resident artifact")
            pending_before = read_byte(main_symbols["ENEMY_PENDING_TYPE"])
            cursor_before = read_byte(main_symbols["ENEMY_NORMAL_CURSOR"])
            expected_pending_before = 0x30 if expected_group == 3 else 0xCE
            if pending_before != expected_pending_before or cursor_before != 4:
                raise RuntimeError(f"pending/cursor changed before group {expected_group} release: {pending_before:02X}/{cursor_before}")
            box_before = [read_byte(main_symbols[name]) for name in ("BOX_TIMER", "BOX_INDEX", "BOX_PHASE")]
            write_byte(main_symbols["BOX_TIMER"], 1)
            write_byte(main_symbols["BOX_INDEX"], 91)
            release_regs = go(enemy_symbols["enemy_release_impl"], "due release implementation")
            release_code = assert_enemy_cpu(release_regs["pc"], 20)
            if read_word(release_regs["s"]) != main_symbols["enemy_release"] + 3:
                raise RuntimeError("timed release did not enter via the resident release wrapper")
            after_timer = go(active_symbols["atb_after_timers"], "timer path return after release")
            records_now = read(main_symbols["ENEMY_TABLE"], 32)
            expected_raw = (expected_group << 4) | 1
            expected_slot = 2 if expected_group == 3 else 3
            new_row = records_now[expected_slot * 8:(expected_slot + 1) * 8]
            if new_row[0] != expected_raw:
                raise RuntimeError(f"timed replacement expected raw group ${expected_raw:02X} in reused slot {expected_slot}, got {new_row.hex()}")
            pending_after = read_byte(main_symbols["ENEMY_PENDING_TYPE"])
            cursor_after = read_byte(main_symbols["ENEMY_NORMAL_CURSOR"])
            box_after = [read_byte(main_symbols[name]) for name in ("BOX_TIMER", "BOX_INDEX", "BOX_PHASE")]
            expected_pending_after = (~expected_raw) & 0xFF
            expected_cursor_after = 4 if expected_group == 3 else 5
            expected_active_after = 3 if expected_group == 3 else 4
            if (pending_after != expected_pending_after or (pending_after & 0x80) == 0 or
                    cursor_after != expected_cursor_after or
                    read_byte(main_symbols["ENEMY_ACTIVE"]) != expected_active_after):
                raise RuntimeError(f"group {expected_group} pending/cursor postcondition differs: {pending_after:02X}/{cursor_after}")
            if box_after != [3, 0, (box_before[2] ^ 1)]:
                raise RuntimeError(f"scheduled timer reload/index/phase rollover differs: before={box_before}, after={box_after}")
            deadline_releases.append({"expected_group": expected_group,
                                      "logical_type": expected_display_type,
                                      "preview_A_before_release": preview_regs["a"],
                                      "preview_pending_before_release": preview_pending,
                                      "preview_cursor_before_release": preview_cursor,
                                      "reused_slot": expected_slot, "timer_entry": timer_pc,
                                      "timer_PC_bytes_sha256": sha(timer_bytes),
                                      "release_impl": release_regs["pc"], "release_code_sha256": sha(release_code),
                                      "record": new_row.hex(), "pending_before": pending_before,
                                      "pending_after": pending_after, "cursor_before": cursor_before,
                                      "cursor_after": cursor_after, "box_before": box_before,
                                      "box_after": box_after, "active_return_PC": after_timer["pc"]})
        current_phase.update({"status": "pass", "markers": {
            "deadline_releases": deadline_releases,
            "replacement_group": deadline_releases[0]["expected_group"],
            "replacement_pending_invalidated": deadline_releases[0]["pending_after"] == 0xCE,
            "cursor_after_replacement": deadline_releases[0]["cursor_after"],
            "normal_successor_group": deadline_releases[1]["expected_group"],
            "normal_successor_pending_invalidated": deadline_releases[1]["pending_after"] == 0xFE,
            "cursor_after_successor": deadline_releases[1]["cursor_after"],
        }})
        # Cover every approved rare group boundary through a disclosed legal
        # stage precondition and the real next_stage routine. Part 9 is repeated
        # after the intervening starts to prove stable FRONT pixel replay.
        begin_phase("group-init-9-10-13-14-front-pixel-replay", "45 seconds maximum: set only the approved predecessor stage byte, call current next_stage once for each of Parts 9, 10, 13 and 14, then repeat Part 9. Require true enemy init reset, real den preview selection, published FRONT pixels and a stable Part 9 preview replay.")
        group_init_rows = []
        previous_commit = read_word(main_symbols["FB_COMMIT_SEQ"])
        for part in (9, 10, 13, 14, 9):
            check_deadline(f"Part {part} real next_stage and FRONT preview")
            go(main_symbols["mainloop"], f"stable boundary before Part {part} initialization")
            next_stage_bytes = assert_resident(main_symbols["next_stage"], 24)
            init_enemy_bytes = assert_resident(main_symbols["init_enemy"], 12)
            enemy_init_bytes = assert_enemy_cpu(enemy_symbols["enemy_init_impl"], 12)
            write_byte(main_symbols["STAGE"], part - 1)
            call_from_current_boundary(main_symbols["next_stage"], f"real Part {part} next_stage initialization")
            if (read_byte(main_symbols["STAGE"]) != part or
                    read_byte(main_symbols["STAGE_PENDING"]) != 0 or
                    read_byte(main_symbols["ENEMY_NORMAL_CURSOR"]) != 0 or
                    read_byte(main_symbols["ENEMY_PENDING_TYPE"]) < 0x80 or
                    read_byte(main_symbols["ENEMY_ACTIVE"]) != 0 or
                    read(main_symbols["ENEMY_TABLE"], 32) != bytes(32)):
                raise RuntimeError(f"Part {part} true enemy initialization did not reset group/cursor/records")
            init_helper_proof = assert_helper_mapping()
            # The next draw_enemy_stage call executes efn_preview_pack through
            # the real renderer. Its A result is the zero-based selected type.
            preview_regs = go(helper_symbols["efn_preview_pack"], f"real Part {part} renderer preview")
            expected_type = _normal_group_start(part)
            if (preview_regs["a"] != expected_type or
                    read_byte(main_symbols["STAGE"]) != part or
                    read_byte(main_symbols["ENEMY_NORMAL_CURSOR"]) != 0 or
                    read_byte(main_symbols["ENEMY_PENDING_TYPE"]) >= 0x80):
                raise RuntimeError(f"Part {part} real preview differs from approved group formula")
            # Complete natural composition through active dispatch and wait for
            # the Vbord-owned FRONT commit before reading its physical owner.
            worklist(parser_start)
            pixels = front_preview_snapshot(f"Part {part} FRONT den preview")
            commit_delta = (int(pixels["FB_COMMIT_SEQ"]) - previous_commit) & 0xFFFF
            if commit_delta == 0 or int(pixels["FRAMES"]) == 0:
                raise RuntimeError(f"Part {part} FRONT publication marker missing")
            previous_commit = int(pixels["FB_COMMIT_SEQ"])
            group_init_rows.append({
                "part": part, "precondition_stage": part - 1,
                "next_stage_entry": main_symbols["next_stage"],
                "next_stage_live_bytes_sha256": sha(next_stage_bytes),
                "init_enemy_entry": main_symbols["init_enemy"],
                "init_enemy_live_bytes_sha256": sha(init_enemy_bytes),
                "enemy_init_impl": enemy_symbols["enemy_init_impl"],
                "enemy_init_live_bytes_sha256": sha(enemy_init_bytes),
                "expected_zero_based_preview_type": expected_type,
                "actual_preview_type": preview_regs["a"],
                "normal_cursor": read_byte(main_symbols["ENEMY_NORMAL_CURSOR"]),
                "pending_type": read_byte(main_symbols["ENEMY_PENDING_TYPE"]),
                "helper_mapping": init_helper_proof,
                "front_pixel_receipt": pixels,
                "front_commit_delta": commit_delta,
                "stage_precondition_disclosure": "STAGE set to part-1; real next_stage called once; preceding maze work skipped",
            })
        if ([row["expected_zero_based_preview_type"] for row in group_init_rows] != [0, 1, 4, 0, 0] or
                group_init_rows[0]["front_pixel_receipt"]["preview_pixels_sha256"] !=
                group_init_rows[-1]["front_pixel_receipt"]["preview_pixels_sha256"] or
                len({row["front_pixel_receipt"]["preview_pixels_sha256"] for row in group_init_rows[:4]}) < 3 or
                len({row["front_pixel_receipt"]["FRONT"] for row in group_init_rows}) < 2):
            raise RuntimeError("Part 9/10/13/14 type pixels or alternating FRONT replay markers differ")
        current_phase.update({"status": "pass", "markers": {
            "group_initializations": group_init_rows,
            "part9_replay_pixel_match": group_init_rows[0]["front_pixel_receipt"]["preview_pixels_sha256"] == group_init_rows[-1]["front_pixel_receipt"]["preview_pixels_sha256"],
            "distinct_group_preview_pixel_count": len({row["front_pixel_receipt"]["preview_pixels_sha256"] for row in group_init_rows[:4]}),
            "front_owners_observed": sorted({row["front_pixel_receipt"]["FRONT"] for row in group_init_rows}),
            "forced_precondition": "Part-1 user route is not claimed; each rare part start uses the approved STAGE=part-1 precondition and actual next_stage/init_enemy path",
        }})
        e["status"] = "bounded-discriminator-pass"
        e["result"] = "The explicitly pinned corrected R10 AD1 keyboard candidate proved the page-$34 helper is reached by the real dormant enemy renderer, Parts 9/10/13/14 initialize the approved group starts through actual next_stage calls, Part 9 den FRONT pixels replay on an alternate owner, ordered Part 9 releases and two actual skull deaths select the latest replacement, and the due timer consumes that override before the normal cursor resumes. This is preparation evidence, not BUG-086 acceptance or a full-maze earning claim."
    except Exception as exc:
        e["failure"] = repr(exc)
        e["failed_phase"] = current_phase.get("name") if current_phase else "prelaunch"
        e["timeout_meaning"] = "The named marker or observer operation did not complete within its bounded probe phase; this is not evidence of slow target code."
        if current_phase is not None:
            current_phase["status"] = "fail"
            current_phase["failure"] = repr(exc)
        raise
    finally:
        if current_phase is not None:
            current_phase["elapsed_seconds"] = round(time.monotonic() - current_phase["started_monotonic"], 3)
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
        if process is not None:
            monitor.stop(process)
            try:
                process.wait(timeout=2)
            except Exception:
                pass
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(e, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": e["status"], "failed_phase": e.get("failed_phase"), "result": e.get("result"),
                          "failure": e.get("failure"), "phases": e["phases"]}, indent=2))


if __name__ == "__main__" and ARGS.command == "live":
    main()
