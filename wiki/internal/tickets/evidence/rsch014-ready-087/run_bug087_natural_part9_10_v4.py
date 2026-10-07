#!/usr/bin/env python3
"""Run fresh Part-2-to-7 progression, then three bounded legal-dot phases under WSL."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


EVIDENCE = Path(__file__).resolve().parent
RUNNER_PATH = EVIDENCE / "run_bug087_supervised_reversal.py"
SPEC = importlib.util.spec_from_file_location("bug087_runner", RUNNER_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot import the approved BUG-087 supervisor helpers")
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)

IDENTITY = EVIDENCE / "current-root-candidate-ad1-keyboard-identity-frozen3dd-equivalent-163d-20261007.json"
NATURAL_INIT_AUTH = EVIDENCE / "current-root-natural-init-frozen3dd-v2-authorization-20261007.json"
BASE_PROGRESSION_AUTH = EVIDENCE / "current-root-natural-progression-frozen3dd-v2-authorization-20261007.json"
CONTINUATION_SCRIPT = EVIDENCE / "bug087_natural_part9_10_v4.py"
PORT = 18627
PHASE_SECONDS = 45
INIT_NAME = "bug087-natural-part9-10-init-v4-20261007.json"
PROGRESSION_NAME = "bug087-natural-part9-10-progression-v4-20261007.json"
PROGRESSION_AUTH = EVIDENCE / "bug087-natural-part9-10-progression-v4-authorization-20261007.json"
CONTINUATION_AUTH = EVIDENCE / "bug087-natural-part9-10-continuation-v4-authorization-20261007.json"
CONTINUATION_NAME = "bug087-natural-part9-10-reset-v4-20261007.json"
FINAL_NAME = "bug087-supervised-natural-part9-10-v4-20261007.json"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def save_json(path: Path, value: dict[str, Any]) -> str:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite retained evidence: {path}")
    data = (json.dumps(value, indent=2) + "\n").encode("utf-8")
    path.write_bytes(data)
    return sha(data)


def main() -> int:
    outputs = [EVIDENCE / INIT_NAME, EVIDENCE / PROGRESSION_NAME,
               PROGRESSION_AUTH, CONTINUATION_AUTH, EVIDENCE / CONTINUATION_NAME,
               EVIDENCE / FINAL_NAME]
    existing = [str(path) for path in outputs if path.exists()]
    if existing:
        raise FileExistsError("refusing to overwrite retained evidence: " + ", ".join(existing))
    adapter = runner.load_adapter()
    identity = json.loads(IDENTITY.read_text(encoding="utf-8"))
    identity["build_dir"] = str(runner.BUILD.resolve(strict=True))
    adapter.verify_identity(identity)
    identity_hash = sha(IDENTITY.read_bytes())
    runner.check_auth(adapter, NATURAL_INIT_AUTH, identity_hash, "natural-init")
    runner.check_auth(adapter, BASE_PROGRESSION_AUTH, identity_hash, "natural-rate-progression")
    if sha((runner.BUILD / "ladybug.rom").read_bytes()) != runner.ROM_SHA256:
        raise RuntimeError("frozen candidate ROM identity changed")
    with socket.socket() as reserve:
        reserve.bind(("127.0.0.1", PORT))

    receipt: dict[str, Any] = {
        "schema": "bug087-supervised-natural-part9-10-v1",
        "ticket": "BUG-087",
        "candidate_rom_sha256": runner.ROM_SHA256,
        "candidate_identity_sha256": identity_hash,
        "candidate_source_revision": identity["source_revision"],
        "source_equivalence_provenance": identity.get("source_equivalence_provenance"),
        "xroar_path": str(runner.XROAR),
        "xroar_sha256": sha(runner.XROAR.read_bytes()),
        "monitor_port": PORT,
        "per_phase_deadline_seconds": PHASE_SECONDS,
        "method": "fresh natural Part-1 initialization and existing Part-2-to-Part-7 progression, followed by three source-legal Up/final-dot phases through Part 8, 9 and 10 in the same XRoar process; each transition has its own 45-second deadline and starts from a synchronized enemy_tick player-field checkpoint",
        "status": "running",
        "phases": [],
    }
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="bug087-part9-10-") as temp_name:
        temp = Path(temp_name)
        log_path = temp / "xroar.log"
        with log_path.open("wb+") as log_file:
            emulator: subprocess.Popen[bytes] | None = None
            try:
                command = [str(runner.XROAR), "-ui", "null", "-ao", "null", "-machine", "coco3",
                           "-ram", "512", "-cart-type", "gmc", "-cart-rom",
                           str(runner.BUILD / "ladybug.rom"), "-cart-autorun", "-v", "2",
                           "-monitor", f"127.0.0.1:{PORT}", "-monitor-halt-on-start"]
                emulator = subprocess.Popen(command, cwd=runner.ROOT, stdin=subprocess.DEVNULL,
                                            stdout=log_file, stderr=subprocess.STDOUT,
                                            start_new_session=True)
                receipt["emulator_pid"] = emulator.pid
                receipt["emulator_command"] = command
                runner.wait_for_real_monitor(adapter, "127.0.0.1", PORT,
                                             time.monotonic() + 5.0)
                init, init_path = runner.run_live_phase(
                    adapter, emulator, IDENTITY, NATURAL_INIT_AUTH, "natural-init", PORT,
                    INIT_NAME, None, temp)
                receipt["phases"].append({"phase": "natural-init", "receipt": init_path.name,
                                          "sha256": sha(init_path.read_bytes()),
                                          "status": init.get("status"),
                                          "process_alive_after": emulator.poll() is None})
                if init.get("status") != "pass-runtime-marker-set" or emulator.poll() is not None:
                    receipt["status"] = "stop-after-natural-init"
                    return finalize(receipt, emulator, log_file, started)

                prog_auth = json.loads(BASE_PROGRESSION_AUTH.read_text(encoding="utf-8"))
                prog_auth["prerequisite_receipt_sha256"] = sha(init_path.read_bytes())
                prog_auth["basis"] = "Fresh same-process natural-init pass; existing Part-2-to-Part-7 progression method and contract are unchanged."
                prog_auth_hash = save_json(PROGRESSION_AUTH, prog_auth)
                progression, progression_path = runner.run_live_phase(
                    adapter, emulator, IDENTITY, PROGRESSION_AUTH,
                    "natural-rate-progression", PORT, PROGRESSION_NAME, init_path, temp)
                receipt["phases"].append({"phase": "natural-rate-progression",
                                          "receipt": progression_path.name,
                                          "sha256": sha(progression_path.read_bytes()),
                                          "authorization_sha256": prog_auth_hash,
                                          "status": progression.get("status"),
                                          "process_alive_after": emulator.poll() is None})
                if progression.get("status") != "pass-runtime-marker-set" or emulator.poll() is not None:
                    receipt["status"] = "stop-after-part7-progression"
                    return finalize(receipt, emulator, log_file, started)

                receipt["part7_player_entry_boundary"] = progression.get("part7_ready_state")

                continuation_contract = {
                    "fixture": "same fresh Part-7 progression process; at player (12,18), step 0, target (12,17) is source-legal north movement (maze_nav current north bit and target reciprocal south bit); set target MAZE_STATE bit7 preserving low style, DOTS_LEFT=1, BONUS_LEFT=0 during setup; then only actual Up press/release and observe eat_dot, check_stage_clear, next_stage; no STAGE or STAGE_PENDING writes",
                    "named_transition_phases": ["part-7-to-8-final-dot-continuity", "part-8-to-9-final-dot-reset", "part-9-to-10-final-dot-rate-reset"],
                    "deadline_seconds": PHASE_SECONDS,
                    "true_init_markers": ["init_enemy", "rate_enemy_init_shim", "enemy_init_impl", "first_enemy_tick"],
                    "expected_part9_addend": 0,
                    "expected_part10_addend": 0x33,
                    "writes_to_STAGE_or_STAGE_PENDING": False,
                }
                cont_auth = {
                    "schema": "bug087-focused-continuation-authorization-v1",
                    "runtime_authorized": True,
                    "parent_review_status": "parent-reviewed-and-approved",
                    "basis": "Parent direction to extend the existing actual Part-2-to-Part-7 progression through Part-9/10 using the same final-dot fixture and true init marker method; no acceptance, production, or ticket scope change.",
                    "phase": "natural-part9-part10-reset-continuation-v4",
                    "phase_deadline_seconds": PHASE_SECONDS,
                    "identity_sha256": identity_hash,
                    "adapter_sha256": sha(runner.ADAPTER_PATH.read_bytes()),
                    "continuation_script_sha256": sha(CONTINUATION_SCRIPT.read_bytes()),
                    "prerequisite_receipt_sha256": sha(progression_path.read_bytes()),
                    "fixture_contract": continuation_contract,
                    "fixture_contract_sha256": sha(json.dumps(continuation_contract, sort_keys=True,
                                                               separators=(",", ":")).encode()),
                    "writes_to_STAGE_or_STAGE_PENDING": False,
                }
                cont_auth_hash = save_json(CONTINUATION_AUTH, cont_auth)
                child_output = temp / "part9-10.json"
                argv = [sys.executable, str(CONTINUATION_SCRIPT), "--identity", str(IDENTITY),
                        "--build-dir", str(runner.BUILD), "--progression-receipt", str(progression_path),
                        "--authorization", str(CONTINUATION_AUTH), "--host", "127.0.0.1",
                        "--port", str(PORT), "--out", str(child_output)]
                child_watch_limit = 3 * PHASE_SECONDS + 10
                with tempfile.TemporaryFile() as child_log:
                    watch = runner.watch_child(emulator, argv, child_watch_limit, child_log)
                result = json.loads(child_output.read_text(encoding="utf-8")) if child_output.exists() else {
                    "status": "fail-no-receipt", "error": "continuation phase produced no receipt"}
                result = runner.compact_result(result)
                result["process_supervision"] = {"emulator_pid": emulator.pid,
                                                  "emulator_returncode_during_phase": emulator.poll(),
                                                  "emulator_alive_after_phase": emulator.poll() is None,
                                                  "monitor_port": PORT,
                                                  "per_transition_phase_limit_seconds": PHASE_SECONDS,
                                                  "child_watch_limit_seconds": child_watch_limit,
                                                  "child_watch": watch}
                continuation_path = EVIDENCE / CONTINUATION_NAME
                save_json(continuation_path, result)
                receipt["phases"].append({"phase": result.get("phase"),
                                          "receipt": continuation_path.name,
                                          "sha256": sha(continuation_path.read_bytes()),
                                          "authorization_sha256": cont_auth_hash,
                                          "status": result.get("status"),
                                          "process_alive_after": emulator.poll() is None})
                receipt["status"] = ("pass-part9-part10-reset" if
                                     result.get("status") == "pass-runtime-marker-set"
                                     else "part9-part10-incomplete")
            except Exception as exc:
                receipt.update({"status": "fail-supervised-diagnostic",
                                "error": f"{type(exc).__name__}: {exc}"})
            finally:
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
                    receipt["emulator_returncode_after_cleanup"] = emulator.poll()
                log_file.flush()
                log_file.seek(0)
                log_text = log_file.read().decode("utf-8", "replace")
                receipt["xroar_log_tail"] = log_text[-2000:] if receipt.get("status") != "pass-part9-part10-reset" else None
    receipt["elapsed_seconds"] = round(time.monotonic() - started, 6)
    save_json(EVIDENCE / FINAL_NAME, receipt)
    return 0 if receipt.get("status") == "pass-part9-part10-reset" else 2


def finalize(receipt: dict[str, Any], emulator, log_file, started: float) -> int:
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
        receipt["emulator_returncode_after_cleanup"] = emulator.poll()
    log_file.flush()
    log_file.seek(0)
    receipt["xroar_log_tail"] = log_file.read().decode("utf-8", "replace")[-2000:]
    receipt["elapsed_seconds"] = round(time.monotonic() - started, 6)
    save_json(EVIDENCE / FINAL_NAME, receipt)
    return 0 if receipt.get("status") == "pass-part9-part10-reset" else 2


if __name__ == "__main__":
    raise SystemExit(main())
