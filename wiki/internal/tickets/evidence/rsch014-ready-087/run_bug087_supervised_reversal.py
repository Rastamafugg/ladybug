#!/usr/bin/env python3
"""Run approved BUG-087 reversal phases under one owned XRoar process."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[5]
EVIDENCE = Path(__file__).resolve().parent
ADAPTER_PATH = EVIDENCE / "bug087_ready_adapter.py"
IDENTITY_PATH = EVIDENCE / "current-root-candidate-ad1-keyboard-identity-frozen3dd-equivalent-163d-20261007.json"
NATURAL_INIT_AUTH = EVIDENCE / "current-root-natural-init-frozen3dd-v2-authorization-20261007.json"
NATURAL_PROGRESSION_AUTH = EVIDENCE / "current-root-natural-progression-frozen3dd-v2-authorization-20261007.json"
REVERSAL_AUTH = EVIDENCE / "current-root-legal-reversal-frozen3dd-v2-authorization-20261007.json"
FIXTURE_SCRIPT = EVIDENCE / "bug087_reversal_fixture_setup.py"
BUG086_RECEIPT = EVIDENCE / "bug086-completion-receipt-20261006.json"
XROAR = ROOT / "docs/reference/xroar/src/xroar"
BUILD = ROOT / "worktrees/bug087-root3dd-refresh/build"
PORT = 18407
PHASE_SECONDS = 45
ROM_SHA256 = "7caa58c1ff1ef84b0b107b4b5cc46850244de1f2729dbc60f3af1f46abfac32e"
FINAL_RECEIPT = EVIDENCE / "bug087-supervised-reversal-frozen3dd-v2-20261007.json"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_adapter():
    spec = importlib.util.spec_from_file_location("bug087_ready_adapter", ADAPTER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load the current BUG-087 adapter")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def compact_audit(value: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for item in value.get("last_monitor_calls", []):
        row = dict(item)
        env = row.get("response_envelope")
        if isinstance(env, dict) and isinstance(env.get("result"), dict):
            result = dict(env["result"])
            data_hex = result.get("data")
            if isinstance(data_hex, str):
                raw = bytes.fromhex(data_hex)
                result["data"] = {"bytes": len(raw), "sha256": sha(raw)}
            env = dict(env)
            env["result"] = result
            row["response_envelope"] = env
        rows.append(row)
    return {"monitor_call_count": value.get("monitor_call_count"),
            "monitor_call_ledger_sha256": value.get("monitor_call_ledger_sha256"),
            "last_monitor_calls": rows}


def compact_result(result: dict[str, Any]) -> dict[str, Any]:
    if isinstance(result.get("monitor_audit"), dict):
        result["monitor_audit"] = compact_audit(result["monitor_audit"])
    if isinstance(result.get("monitor_audit"), list):
        result["monitor_audit"] = [compact_audit(row) for row in result["monitor_audit"]]
    return result


def write_json(path: Path, value: dict[str, Any]) -> str:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite evidence: {path}")
    data = (json.dumps(value, indent=2) + "\n").encode("utf-8")
    path.write_bytes(data)
    return sha(data)


def check_auth(adapter, auth_path: Path, identity_hash: str, phase: str) -> dict[str, Any]:
    auth = json.loads(auth_path.read_text(encoding="utf-8"))
    if (auth.get("runtime_authorized") is not True or
            auth.get("parent_review_status") != "parent-reviewed-and-approved" or
            auth.get("phase") != phase or auth.get("phase_deadline_seconds") != PHASE_SECONDS or
            auth.get("adapter_sha256") != sha(ADAPTER_PATH.read_bytes()) or
            auth.get("scenario_plan_sha256") != sha((EVIDENCE / "scenario-plan.json").read_bytes()) or
            auth.get("bug086_receipt_sha256") != sha(BUG086_RECEIPT.read_bytes()) or
            auth.get("identity_sha256_by_name", {}).get(IDENTITY_PATH.name) != identity_hash):
        raise ValueError(f"authorization does not match current {phase} artifacts: {auth_path.name}")
    return auth


def wait_for_real_monitor(adapter, host: str, port: int, deadline: float) -> None:
    last_error = None
    while time.monotonic() < deadline:
        try:
            probe = adapter.RuntimeProbe(host, port, deadline)
            probe.close()
            return
        except (OSError, TimeoutError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            time.sleep(0.05)
    raise TimeoutError(f"real monitor client did not attach before phase start: {last_error}")


def inspect_live_state(adapter, host: str, port: int) -> dict[str, Any]:
    deadline = time.monotonic() + 3.0
    try:
        probe = adapter.RuntimeProbe(host, port, deadline)
        try:
            state = probe.call("get_run_state", None, 1.0)
            return {"status": "read-only-state-received", "state": state,
                    "monitor_call_ledger_sha256": probe.audit()["monitor_call_ledger_sha256"]}
        finally:
            probe.close()
    except Exception as exc:
        return {"status": "monitor-unavailable", "error": f"{type(exc).__name__}: {exc}"}


def watch_child(emulator: subprocess.Popen[bytes], argv: list[str], phase_limit: float,
                output_file: Any) -> dict[str, Any]:
    started = time.monotonic()
    child = subprocess.Popen(argv, cwd=ROOT, stdin=subprocess.DEVNULL,
                             stdout=output_file, stderr=subprocess.STDOUT,
                             start_new_session=True)
    stop_reason = "completed"
    while child.poll() is None:
        if emulator.poll() is not None:
            stop_reason = "emulator-exited-during-phase"
            child.terminate()
            break
        if time.monotonic() - started > phase_limit + 3.0:
            stop_reason = "helper-exceeded-phase-bound"
            child.terminate()
            break
        time.sleep(0.1)
    try:
        child.wait(timeout=2.0)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait(timeout=1.0)
        stop_reason = "helper-killed-after-terminate-timeout"
    elapsed = round(time.monotonic() - started, 6)
    output_file.flush()
    output_file.seek(0)
    text = output_file.read().decode("utf-8", "replace")
    return {"child_pid": child.pid, "child_returncode": child.returncode,
            "watch_status": stop_reason, "elapsed_seconds": elapsed,
            "stdout_stderr_tail": text[-3000:]}


def run_live_phase(adapter, emulator, identity_path: Path, auth_path: Path,
                   phase: str, port: int, output_name: str,
                   prerequisite_path: Path | None, temp: Path) -> tuple[dict[str, Any], Path]:
    output_tmp = temp / f"{phase}.json"
    argv = [sys.executable, str(ADAPTER_PATH), "live", "--phase", phase,
            "--authorization", str(auth_path), "--bug086-receipt", str(BUG086_RECEIPT),
            "--output", str(output_tmp), "--identity", str(identity_path), "--port", str(port)]
    if prerequisite_path is not None:
        argv.extend(["--prerequisite-receipt", str(prerequisite_path)])
    with tempfile.TemporaryFile() as output_file:
        child_watch = watch_child(emulator, argv, PHASE_SECONDS, output_file)
    result = json.loads(output_tmp.read_text(encoding="utf-8")) if output_tmp.exists() else {
        "schema": "bug087-supervised-child-v1", "status": "fail-no-receipt"}
    result = compact_result(result)
    result["process_supervision"] = {
        "emulator_pid": emulator.pid,
        "emulator_returncode_during_phase": emulator.poll(),
        "emulator_alive_after_phase": emulator.poll() is None,
        "monitor_port": port,
        "phase_limit_seconds": PHASE_SECONDS,
        "child_watch": child_watch,
    }
    out = EVIDENCE / output_name
    write_json(out, result)
    return result, out


def run_fixture_setup(adapter, emulator, identity_path: Path, port: int,
                      output_name: str, temp: Path) -> tuple[dict[str, Any], Path]:
    output_tmp = temp / "reversal-fixture.json"
    argv = [sys.executable, str(FIXTURE_SCRIPT), "--identity", str(identity_path),
            "--build-dir", str(BUILD), "--host", "127.0.0.1", "--port", str(port),
            "--deadline-seconds", str(PHASE_SECONDS), "--warmup-callbacks", "6",
            "--out", str(output_tmp)]
    with tempfile.TemporaryFile() as output_file:
        child_watch = watch_child(emulator, argv, PHASE_SECONDS, output_file)
    result = json.loads(output_tmp.read_text(encoding="utf-8")) if output_tmp.exists() else {
        "schema": "bug087-supervised-fixture-v1", "status": "fail-no-receipt"}
    result = compact_result(result)
    result["process_supervision"] = {
        "emulator_pid": emulator.pid,
        "emulator_returncode_during_phase": emulator.poll(),
        "emulator_alive_after_phase": emulator.poll() is None,
        "monitor_port": port,
        "phase_limit_seconds": PHASE_SECONDS,
        "child_watch": child_watch,
    }
    out = EVIDENCE / output_name
    write_json(out, result)
    return result, out


def arm_enemy_callback(adapter, identity: dict[str, Any], port: int) -> dict[str, Any]:
    deadline = time.monotonic() + 12.0
    probe = adapter.RuntimeProbe("127.0.0.1", port, deadline)
    try:
        state = probe.call("get_run_state", None, 1.0)
        if state.get("state") != "halted":
            raise RuntimeError(f"Part-7 progression did not leave a halted target: {state}")
        tick = adapter._runtime_symbols(identity, "enemy")["enemy_tick_impl"]
        bp_id = probe.set_breakpoint(tick)
        marker = probe.run_until_marker(wait_cap_seconds=10.0)
        # Establish source/runtime/destination identity before interpreting PC.
        proof = adapter._verify_runtime_images(probe, identity, verify_staging=False,
                                               require_mapping=True)
        if marker.get("pc") != tick or marker.get("bp_id") != bp_id:
            raise RuntimeError(f"enemy callback marker differs after byte proof: {marker}")
        record = {"status": "pass-byte-verified-enemy-callback",
                  "marker_pc": f"${tick:04X}", "breakpoint_id": bp_id,
                  "identity_proof": proof, "monitor_audit": compact_audit(probe.audit())}
        return record
    finally:
        # Keep the acknowledged callback breakpoint installed for the next phase.
        probe.close()


def main() -> int:
    if FINAL_RECEIPT.exists():
        raise FileExistsError(f"refusing to overwrite {FINAL_RECEIPT}")
    adapter = load_adapter()
    identity = json.loads(IDENTITY_PATH.read_text(encoding="utf-8"))
    identity["build_dir"] = str(BUILD.resolve(strict=True))
    adapter.verify_identity(identity)
    identity_hash = sha(IDENTITY_PATH.read_bytes())
    candidate_rom = BUILD / "ladybug.rom"
    rom_hash = sha(candidate_rom.read_bytes())
    xroar_hash = sha(XROAR.read_bytes())
    if rom_hash != ROM_SHA256:
        raise RuntimeError(f"candidate ROM changed: {rom_hash}")
    for path, phase in ((NATURAL_INIT_AUTH, "natural-init"),
                        (NATURAL_PROGRESSION_AUTH, "natural-rate-progression"),
                        (REVERSAL_AUTH, "legal-reversal-concurrent-mover")):
        check_auth(adapter, path, identity_hash, phase)
    reversal_auth = json.loads(REVERSAL_AUTH.read_text(encoding="utf-8"))
    setup_auth = reversal_auth.get("authorized_pre_measurement_fixture_setup", {})
    if (setup_auth.get("script_sha256") != sha(FIXTURE_SCRIPT.read_bytes()) or
            setup_auth.get("direct_setup_writes_allowed") is not True or
            setup_auth.get("measurement_game_memory_writes") != 0 or
            setup_auth.get("measurement_input_injections") != 0):
        raise ValueError("reversal authorization does not pin the approved pre-measurement setup and no-write measurement contract")
    phase_plan = json.loads((EVIDENCE / "scenario-plan.json").read_text(encoding="utf-8"))
    for phase in ("natural-init", "natural-rate-progression", "legal-reversal-concurrent-mover"):
        row = next(x for x in phase_plan["phases"] if x["id"] == phase)
        if row.get("deadline_seconds") != PHASE_SECONDS:
            raise ValueError(f"current plan deadline changed for {phase}")
    expected_outputs = [FINAL_RECEIPT,
                        EVIDENCE / "bug087-supervised-natural-init-frozen3dd-v2-20261007.json",
                        EVIDENCE / "bug087-supervised-natural-progression-frozen3dd-v2-20261007.json",
                        EVIDENCE / "bug087-deterministic-reversal-fixture-setup-frozen3dd-v2-20261007.json",
                        EVIDENCE / "bug087-deterministic-legal-reversal-frozen3dd-v2-20261007.json",
                        EVIDENCE / "current-root-supervised-natural-progression-frozen3dd-v2-authorization-20261007.json"]
    existing = [str(path) for path in expected_outputs if path.exists()]
    if existing:
        raise FileExistsError("refusing to overwrite retained supervised evidence: " + ", ".join(existing))

    with socket.socket() as reserve:
        reserve.bind(("127.0.0.1", PORT))

    receipt: dict[str, Any] = {
        "schema": "bug087-supervised-reversal-diagnostic-20261007-v2",
        "ticket": "BUG-087",
        "candidate_rom_sha256": rom_hash,
        "candidate_identity_sha256": identity_hash,
        "candidate_source_revision": identity["source_revision"],
        "candidate_source_build_receipt": identity["artifacts"]["source-build-receipt.json"],
        "source_equivalence_provenance": identity.get("source_equivalence_provenance"),
        "adapter_sha256": sha(ADAPTER_PATH.read_bytes()),
        "scenario_plan_sha256": sha((EVIDENCE / "scenario-plan.json").read_bytes()),
        "xroar_path": str(XROAR),
        "xroar_sha256": xroar_hash,
        "monitor_port": PORT,
        "per_phase_deadline_seconds": PHASE_SECONDS,
        "process_supervision": "one owned XRoar Popen; helper child, PID, returncode, and log state observed throughout each phase",
        "success_marker": "each bounded phase receipt completes or fails with process exit/listener state captured; reversal requires slot0 at (6,4) westbound, gate0=0, another active mover, then observed legal east reverse with concurrent movement",
        "timeout_meaning": "a phase timeout is observer/process diagnostic evidence only; it does not prove route unreachability or a game-speed result",
        "direct_writes_scope": "natural init uses approved key inputs; progression uses only approved DOTS_LEFT=1 and BONUS_LEFT=0 final-dot fixtures; user-authorized reversal fixture writes occur only before measurement, followed by six frozen owner-hydration callbacks; actual chooser/movement phase has no direct game-memory writes or input",
        "rejected_experiment_handling": "the corrected endpoint audit invalidated the prior RNG trajectory inference; no stochastic or RNG search is repeated",
        "status": "running",
        "phases": [],
        "_started_monotonic": time.monotonic(),
    }

    with tempfile.TemporaryDirectory(prefix="bug087-supervised-") as td:
        temp = Path(td)
        log_path = temp / "xroar.log"
        log_file = log_path.open("wb")
        emulator: subprocess.Popen[bytes] | None = None
        try:
            command = [str(XROAR), "-ui", "null", "-ao", "null", "-machine", "coco3",
                       "-ram", "512", "-cart-type", "gmc", "-cart-rom", str(candidate_rom),
                       "-cart-autorun", "-v", "2", "-monitor", f"127.0.0.1:{PORT}",
                       "-monitor-halt-on-start"]
            emulator = subprocess.Popen(command, cwd=ROOT, stdin=subprocess.DEVNULL,
                                        stdout=log_file, stderr=subprocess.STDOUT,
                                        start_new_session=True)
            receipt["emulator_pid"] = emulator.pid
            receipt["emulator_command"] = command
            wait_for_real_monitor(adapter, "127.0.0.1", PORT, time.monotonic() + 5.0)
            receipt["listener_ready"] = True
            print(f"SUPERVISED XRoar pid={emulator.pid} listener={PORT} ROM={rom_hash[:12]}", flush=True)

            init_result, init_path = run_live_phase(
                adapter, emulator, IDENTITY_PATH, NATURAL_INIT_AUTH, "natural-init", PORT,
                "bug087-supervised-natural-init-frozen3dd-v2-20261007.json", None, temp)
            receipt["phases"].append({"phase": "natural-init", "receipt": init_path.name,
                                      "sha256": sha(init_path.read_bytes()),
                                      "status": init_result.get("status"),
                                      "process_alive_after": emulator.poll() is None})
            print(f"SUPERVISED natural-init={init_result.get('status')} alive={emulator.poll() is None}", flush=True)
            if init_result.get("status") != "pass-runtime-marker-set" or emulator.poll() is not None:
                receipt["status"] = "stop-after-natural-init"
                return finalize(receipt, emulator, log_file, log_path)

            progression_auth = json.loads(NATURAL_PROGRESSION_AUTH.read_text(encoding="utf-8"))
            progression_auth["prerequisite_receipt_sha256"] = sha(init_path.read_bytes())
            progression_auth["basis"] = ("Parent-reviewed fresh same-process natural-init receipt; "
                                          "the approved Part-2-to-Part-7 contract is unchanged.")
            progression_auth_path = EVIDENCE / "current-root-supervised-natural-progression-frozen3dd-v2-authorization-20261007.json"
            write_json(progression_auth_path, progression_auth)
            prog_result, prog_path = run_live_phase(
                adapter, emulator, IDENTITY_PATH, progression_auth_path,
                "natural-rate-progression", PORT,
                "bug087-supervised-natural-progression-frozen3dd-v2-20261007.json", init_path, temp)
            receipt["phases"].append({"phase": "natural-rate-progression", "receipt": prog_path.name,
                                      "sha256": sha(prog_path.read_bytes()),
                                      "status": prog_result.get("status"),
                                      "process_alive_after": emulator.poll() is None})
            print(f"SUPERVISED progression={prog_result.get('status')} alive={emulator.poll() is None}", flush=True)
            if prog_result.get("status") != "pass-runtime-marker-set" or emulator.poll() is not None:
                receipt["status"] = "stop-after-natural-progression"
                return finalize(receipt, emulator, log_file, log_path)

            callback = arm_enemy_callback(adapter, identity, PORT)
            receipt["part7_enemy_callback"] = callback
            print("SUPERVISED verified Part-7 enemy callback ready", flush=True)
            if emulator.poll() is not None:
                receipt["status"] = "fail-emulator-exited-before-reversal-setup"
                return finalize(receipt, emulator, log_file, log_path)

            setup_result, setup_path = run_fixture_setup(
                adapter, emulator, IDENTITY_PATH, PORT,
                "bug087-deterministic-reversal-fixture-setup-frozen3dd-v2-20261007.json", temp)
            receipt["phases"].append({"phase": "reversal-fixture-setup", "receipt": setup_path.name,
                                      "sha256": sha(setup_path.read_bytes()),
                                      "status": setup_result.get("status"),
                                      "process_alive_after": emulator.poll() is None,
                                      "monitor_state_after": inspect_live_state(adapter, "127.0.0.1", PORT)
                                      if emulator.poll() is None else None})
            print(f"SUPERVISED fixture={setup_result.get('status')} alive={emulator.poll() is None}", flush=True)
            if setup_result.get("status") != "pass-fixture-ready-for-measurement" or emulator.poll() is not None:
                receipt["status"] = "stop-after-reversal-fixture-setup"
                return finalize(receipt, emulator, log_file, log_path)

            reversal_result, reversal_path = run_live_phase(
                adapter, emulator, IDENTITY_PATH, REVERSAL_AUTH, "legal-reversal-concurrent-mover", PORT,
                "bug087-deterministic-legal-reversal-frozen3dd-v2-20261007.json", None, temp)
            receipt["phases"].append({"phase": "legal-reversal-concurrent-mover",
                                      "receipt": reversal_path.name,
                                      "sha256": sha(reversal_path.read_bytes()),
                                      "status": reversal_result.get("status"),
                                      "process_alive_after": emulator.poll() is None,
                                      "monitor_state_after": inspect_live_state(adapter, "127.0.0.1", PORT)
                                      if emulator.poll() is None else None})
            receipt["status"] = ("pass-legal-reversal" if
                                 reversal_result.get("status") == "pass-runtime-marker-set"
                                 else "legal-reversal-incomplete")
            return finalize(receipt, emulator, log_file, log_path)
        except Exception as exc:
            receipt.update({"status": "fail-supervised-diagnostic",
                            "error": f"{type(exc).__name__}: {exc}"})
            return finalize(receipt, emulator, log_file, log_path)


def finalize(receipt: dict[str, Any], emulator: subprocess.Popen[bytes] | None,
             log_file: Any, log_path: Path) -> int:
    started = receipt.pop("_started_monotonic", time.monotonic())
    if emulator is not None:
        receipt["emulator_returncode_before_cleanup"] = emulator.poll()
        receipt["emulator_alive_before_cleanup"] = emulator.poll() is None
        if emulator.poll() is None:
            emulator.terminate()
            try:
                emulator.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                emulator.kill()
                emulator.wait(timeout=1.0)
        receipt["owned_emulator_returncode_after_cleanup"] = emulator.returncode
    log_file.flush()
    log_file.close()
    raw = log_path.read_bytes() if log_path.exists() else b""
    receipt["xroar_log_bytes"] = len(raw)
    receipt["xroar_log_sha256"] = sha(raw)
    receipt["xroar_log_tail"] = raw.decode("utf-8", "replace")[-6000:]
    receipt["log_retention"] = "only byte count, hash, and final 6000 characters retained"
    receipt["elapsed_seconds"] = round(time.monotonic() - started, 6)
    FINAL_RECEIPT.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": receipt["status"], "emulator_pid": receipt.get("emulator_pid"),
                      "phases": receipt.get("phases", []),
                      "alive_before_cleanup": receipt.get("emulator_alive_before_cleanup"),
                      "xroar_log_bytes": receipt.get("xroar_log_bytes"),
                      "receipt": str(FINAL_RECEIPT)}, indent=2), flush=True)
    return 0 if receipt["status"] == "pass-legal-reversal" else 2


if __name__ == "__main__":
    raise SystemExit(main())
