#!/usr/bin/env python3
"""Run fresh natural Part-2 setup and one bounded zero-addend movement check."""

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


RUNNER_PATH = Path(__file__).resolve().parent / "run_bug087_supervised_reversal.py"
SPEC = importlib.util.spec_from_file_location("bug087_runner", RUNNER_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot import the approved BUG-087 supervisor helpers")
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)

EVIDENCE = Path(__file__).resolve().parent
IDENTITY = EVIDENCE / "current-root-candidate-ad1-keyboard-identity-frozen3dd-equivalent-163d-20261007.json"
NATURAL_INIT_AUTH = EVIDENCE / "current-root-natural-init-frozen3dd-v2-authorization-20261007.json"
FIXTURE_SCRIPT = EVIDENCE / "bug087_zero_addend_fixture.py"
PORT = 18512
PHASE_SECONDS = 45
ROM_SHA256 = "7caa58c1ff1ef84b0b107b4b5cc46850244de1f2729dbc60f3af1f46abfac32e"
INIT_OUTPUT_NAME = "bug087-zero-addend-natural-init-v2-20261007.json"
FIXTURE_OUTPUT_NAME = "bug087-zero-addend-part2-measurement-v2-20261007.json"
AUTH_OUTPUT = EVIDENCE / "bug087-zero-addend-v2-authorization-20261007.json"
FINAL_OUTPUT = EVIDENCE / "bug087-supervised-zero-addend-v2-20261007.json"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, value: dict[str, Any]) -> str:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite evidence: {path}")
    data = (json.dumps(value, indent=2) + "\n").encode("utf-8")
    path.write_bytes(data)
    return sha(data)


def main() -> int:
    for path in (EVIDENCE / INIT_OUTPUT_NAME, EVIDENCE / FIXTURE_OUTPUT_NAME,
                 AUTH_OUTPUT, FINAL_OUTPUT):
        if path.exists():
            raise FileExistsError(f"refusing to overwrite retained evidence: {path}")
    adapter = runner.load_adapter()
    identity = json.loads(IDENTITY.read_text(encoding="utf-8"))
    identity["build_dir"] = str(runner.BUILD.resolve(strict=True))
    adapter.verify_identity(identity)
    if sha((runner.BUILD / "ladybug.rom").read_bytes()) != ROM_SHA256:
        raise RuntimeError("frozen candidate ROM identity changed")
    identity_hash = sha(IDENTITY.read_bytes())
    runner.check_auth(adapter, NATURAL_INIT_AUTH, identity_hash, "natural-init")
    with socket.socket() as reserve:
        reserve.bind(("127.0.0.1", PORT))

    receipt: dict[str, Any] = {
        "schema": "bug087-supervised-zero-addend-v1",
        "ticket": "BUG-087",
        "candidate_rom_sha256": ROM_SHA256,
        "candidate_identity_sha256": identity_hash,
        "candidate_source_revision": identity["source_revision"],
        "source_equivalence_provenance": identity.get("source_equivalence_provenance"),
        "xroar_path": str(runner.XROAR),
        "xroar_sha256": sha(runner.XROAR.read_bytes()),
        "monitor_port": PORT,
        "per_phase_deadline_seconds": PHASE_SECONDS,
        "method": "fresh cold-start natural-init phase, followed by coherent legal Part-2 horizontal actor fixture and 24 callback measurement; no measured writes or input",
        "status": "running",
        "phases": [],
    }
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="bug087-zero-addend-") as temp_name:
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
                init_result, init_path = runner.run_live_phase(
                    adapter, emulator, IDENTITY, NATURAL_INIT_AUTH, "natural-init", PORT,
                    INIT_OUTPUT_NAME, None, temp)
                receipt["phases"].append({"phase": "natural-init", "receipt": init_path.name,
                                          "sha256": sha(init_path.read_bytes()),
                                          "status": init_result.get("status"),
                                          "process_alive_after": emulator.poll() is None})
                if init_result.get("status") != "pass-runtime-marker-set" or emulator.poll() is not None:
                    receipt["status"] = "stop-after-natural-init"
                    return write_final(receipt, emulator, log_file, log_path, started)

                fixture_contract = {
                    "fixture": "after fresh natural Part-2 init, one $61 actor at legal horizontal corridor (2,18), east; freeze only for six owner-hydration callbacks",
                    "measurement_callbacks": 24,
                    "measurement_game_memory_writes": 0,
                    "measurement_input_injections": 0,
                    "expected_addend": 0,
                    "expected_movement_admissions": 12,
                    "expected_native_pixels": 24,
                    "pixel_tolerance": 1,
                    "deadline_seconds": PHASE_SECONDS,
                }
                auth = {
                    "schema": "bug087-focused-fixture-authorization-v1",
                    "runtime_authorized": True,
                    "parent_review_status": "parent-reviewed-and-approved",
                    "basis": "Parent direction for the two remaining BUG-087 gaps: use a fresh Part-1 progression and one bounded legal zero-addend axis measurement; preserve the approved movement oracle and no-write/no-input measured phase.",
                    "phase": "legal-part2-zero-addend-horizontal-displacement",
                    "phase_deadline_seconds": PHASE_SECONDS,
                    "identity_sha256": identity_hash,
                    "adapter_sha256": sha(runner.ADAPTER_PATH.read_bytes()),
                    "prerequisite_receipt_sha256": sha(init_path.read_bytes()),
                    "fixture_script_sha256": sha(FIXTURE_SCRIPT.read_bytes()),
                    "fixture_contract": fixture_contract,
                    "fixture_contract_sha256": sha(json.dumps(fixture_contract, sort_keys=True,
                                                               separators=(",", ":")).encode()),
                    "measurement_game_memory_writes": 0,
                    "measurement_input_injections": 0,
                }
                auth_hash = write_json(AUTH_OUTPUT, auth)
                child_output = temp / "zero-addend.json"
                argv = [sys.executable, str(FIXTURE_SCRIPT), "--identity", str(IDENTITY),
                        "--build-dir", str(runner.BUILD), "--natural-init-receipt", str(init_path),
                        "--authorization", str(AUTH_OUTPUT), "--host", "127.0.0.1",
                        "--port", str(PORT), "--out", str(child_output)]
                with tempfile.TemporaryFile() as child_log:
                    watch = runner.watch_child(emulator, argv, PHASE_SECONDS, child_log)
                result = json.loads(child_output.read_text(encoding="utf-8")) if child_output.exists() else {
                    "status": "fail-no-receipt", "error": "focused fixture phase produced no receipt"}
                result = runner.compact_result(result)
                result["authorization_sha256"] = auth_hash
                result["process_supervision"] = {"emulator_pid": emulator.pid,
                                                  "emulator_returncode_during_phase": emulator.poll(),
                                                  "emulator_alive_after_phase": emulator.poll() is None,
                                                  "monitor_port": PORT,
                                                  "phase_limit_seconds": PHASE_SECONDS,
                                                  "child_watch": watch}
                fixture_path = EVIDENCE / FIXTURE_OUTPUT_NAME
                write_json(fixture_path, result)
                receipt["phases"].append({"phase": result.get("phase"),
                                          "receipt": fixture_path.name,
                                          "sha256": sha(fixture_path.read_bytes()),
                                          "authorization_sha256": auth_hash,
                                          "status": result.get("status"),
                                          "process_alive_after": emulator.poll() is None})
                receipt["status"] = ("pass-zero-addend" if
                                     result.get("status") == "pass-runtime-marker-set"
                                     else "zero-addend-incomplete")
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
                receipt["xroar_log_tail"] = log_text[-2000:] if receipt.get("status") != "pass-zero-addend" else None
    receipt["elapsed_seconds"] = round(time.monotonic() - started, 6)
    write_final(receipt)
    return 0 if receipt.get("status") == "pass-zero-addend" else 2


def write_final(receipt: dict[str, Any], emulator=None, log_file=None,
                log_path=None, started=None) -> int:
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
    if log_file is not None:
        log_file.flush()
        log_file.seek(0)
        text = log_file.read().decode("utf-8", "replace")
        receipt["xroar_log_tail"] = text[-2000:]
    if started is not None:
        receipt["elapsed_seconds"] = round(time.monotonic() - started, 6)
    write_json(FINAL_OUTPUT, receipt)
    return 0 if receipt.get("status") == "pass-zero-addend" else 2


if __name__ == "__main__":
    raise SystemExit(main())
