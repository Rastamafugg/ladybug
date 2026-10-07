#!/usr/bin/env python3
"""Run fresh natural entry, Part-7 progression, and one bounded cadence audit."""

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


ROOT = Path(__file__).resolve().parents[5]
EVIDENCE = Path(__file__).resolve().parent
BASE_RUNNER = EVIDENCE / "run_bug087_supervised_reversal.py"
CADENCE_SCRIPT = EVIDENCE / "probe_bug087_spawner_cadence.py"
CADENCE_AUTH = EVIDENCE / "bug087-spawner-cadence-authorization-20261007.json"
PORT = 17689
PHASE_SECONDS = 45
ROM_SHA256 = "7caa58c1ff1ef84b0b107b4b5cc46850244de1f2729dbc60f3af1f46abfac32e"
INIT_NAME = "bug087-supervised-natural-init-spawner-audit-20261007.json"
PROGRESSION_NAME = "bug087-supervised-natural-progression-spawner-audit-20261007.json"
PROGRESSION_AUTH_NAME = "current-root-supervised-natural-progression-spawner-audit-authorization-20261007.json"
CADENCE_NAME = "bug087-spawner-cadence-20261007.json"
SUMMARY_NAME = "bug087-supervised-spawner-audit-20261007.json"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_base_runner():
    spec = importlib.util.spec_from_file_location("bug087_supervised_base", BASE_RUNNER)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load the existing supervised BUG-087 phase runner")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def authorize_cadence(base, identity_hash: str, rom_hash: str, xroar_hash: str) -> dict[str, Any]:
    auth = json.loads(CADENCE_AUTH.read_text(encoding="utf-8"))
    if (auth.get("runtime_authorized") is not True or
            auth.get("parent_review_status") != "parent-reviewed-and-approved" or
            auth.get("phase") != "spawner-timer-reset-cadence" or
            auth.get("phase_deadline_seconds") != PHASE_SECONDS or
            auth.get("rom_sha256") != rom_hash or
            auth.get("xroar_sha256") != xroar_hash or
            auth.get("identity_sha256") != identity_hash or
            auth.get("adapter_sha256") != sha(base.ADAPTER_PATH.read_bytes()) or
            auth.get("probe_sha256") != sha(CADENCE_SCRIPT.read_bytes()) or
            auth.get("supervisor_sha256") != sha(Path(__file__).read_bytes()) or
            auth.get("bug086_receipt_sha256") != sha(base.BUG086_RECEIPT.read_bytes()) or
            auth.get("scenario_plan_sha256") != sha((EVIDENCE / "scenario-plan.json").read_bytes())):
        raise ValueError("parent-reviewed cadence authorization does not match current artifacts")
    return auth


def run_cadence_child(base, emulator, identity_path: Path, port: int,
                      temp: Path) -> tuple[dict[str, Any], Path]:
    output_tmp = temp / "spawner-cadence.json"
    argv = [sys.executable, str(CADENCE_SCRIPT), "--identity", str(identity_path),
            "--build-dir", str(base.BUILD), "--host", "127.0.0.1", "--port", str(port),
            "--deadline-seconds", str(PHASE_SECONDS), "--authorization", str(CADENCE_AUTH),
            "--out", str(output_tmp)]
    with tempfile.TemporaryFile() as output_file:
        child_watch = base.watch_child(emulator, argv, PHASE_SECONDS, output_file)
    result = json.loads(output_tmp.read_text(encoding="utf-8")) if output_tmp.exists() else {
        "schema": "bug087-spawner-cadence-child-v1", "status": "fail-no-receipt"}
    result = base.compact_result(result)
    result["process_supervision"] = {
        "emulator_pid": emulator.pid,
        "emulator_returncode_during_phase": emulator.poll(),
        "emulator_alive_after_phase": emulator.poll() is None,
        "monitor_port": port,
        "phase_limit_seconds": PHASE_SECONDS,
        "child_watch": child_watch,
    }
    out = EVIDENCE / CADENCE_NAME
    base.write_json(out, result)
    return result, out


def finalize(base, receipt: dict[str, Any], emulator, log_file, log_path: Path) -> int:
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
    receipt["elapsed_seconds"] = round(time.monotonic() - started, 6)
    out = EVIDENCE / SUMMARY_NAME
    if out.exists():
        raise FileExistsError(f"refusing to overwrite evidence: {out}")
    out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": receipt["status"], "phases": receipt.get("phases", []),
                      "receipt": str(out)}, indent=2), flush=True)
    return 0 if receipt["status"] == "pass-spawner-cadence-audit" else 2


def main() -> int:
    base = load_base_runner()
    adapter = base.load_adapter()
    identity_path = base.IDENTITY_PATH
    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    identity["build_dir"] = str(base.BUILD.resolve(strict=True))
    adapter.verify_identity(identity)
    identity_hash = sha(identity_path.read_bytes())
    rom_hash = sha((base.BUILD / "ladybug.rom").read_bytes())
    xroar_hash = sha(base.XROAR.read_bytes())
    if rom_hash != ROM_SHA256:
        raise RuntimeError(f"candidate ROM changed: {rom_hash}")
    base.check_auth(adapter, base.NATURAL_INIT_AUTH, identity_hash, "natural-init")
    authorize_cadence(base, identity_hash, rom_hash, xroar_hash)

    for name in (INIT_NAME, PROGRESSION_NAME, PROGRESSION_AUTH_NAME, CADENCE_NAME, SUMMARY_NAME):
        if (EVIDENCE / name).exists():
            raise FileExistsError(f"refusing to overwrite retained evidence: {name}")
    with socket.socket() as reserve:
        reserve.bind(("127.0.0.1", PORT))

    receipt: dict[str, Any] = {
        "schema": "bug087-supervised-spawner-audit-20261007-v1",
        "ticket": "BUG-087",
        "candidate_rom_sha256": rom_hash,
        "candidate_identity_sha256": identity_hash,
        "adapter_sha256": sha(base.ADAPTER_PATH.read_bytes()),
        "scenario_plan_sha256": sha((EVIDENCE / "scenario-plan.json").read_bytes()),
        "probe_sha256": sha(CADENCE_SCRIPT.read_bytes()),
        "xroar_sha256": xroar_hash,
        "monitor_port": PORT,
        "per_phase_deadline_seconds": PHASE_SECONDS,
        "scope": "fresh owned XRoar, approved natural init and Part-2-to-Part-7 progression, then read-only timer/release/reset marker audit",
        "acceptance_effect": "diagnostic only; no movement, reversal, or arcade-speed acceptance is inferred",
        "phases": [],
        "_started_monotonic": time.monotonic(),
    }
    with tempfile.TemporaryDirectory(prefix="bug087-spawner-audit-") as td:
        temp = Path(td)
        log_path = temp / "xroar.log"
        log_file = log_path.open("wb")
        emulator = None
        try:
            command = [str(base.XROAR), "-ui", "null", "-ao", "null", "-machine", "coco3",
                       "-ram", "512", "-cart-type", "gmc", "-cart-rom",
                       str(base.BUILD / "ladybug.rom"), "-cart-autorun", "-v", "2",
                       "-monitor", f"127.0.0.1:{PORT}", "-monitor-halt-on-start"]
            emulator = subprocess.Popen(command, cwd=ROOT, stdin=subprocess.DEVNULL,
                                        stdout=log_file, stderr=subprocess.STDOUT,
                                        start_new_session=True)
            receipt["emulator_pid"] = emulator.pid
            receipt["emulator_command"] = command
            base.wait_for_real_monitor(adapter, "127.0.0.1", PORT, time.monotonic() + 5.0)
            receipt["listener_ready"] = True

            init_result, init_path = base.run_live_phase(
                adapter, emulator, identity_path, base.NATURAL_INIT_AUTH, "natural-init", PORT,
                INIT_NAME, None, temp)
            receipt["phases"].append({"phase": "natural-init", "status": init_result.get("status"),
                                      "receipt": init_path.name, "sha256": sha(init_path.read_bytes()),
                                      "process_alive_after": emulator.poll() is None})
            if init_result.get("status") != "pass-runtime-marker-set" or emulator.poll() is not None:
                receipt["status"] = "stop-after-natural-init"
                return finalize(base, receipt, emulator, log_file, log_path)

            progression_auth = json.loads(base.NATURAL_PROGRESSION_AUTH.read_text(encoding="utf-8"))
            progression_auth["prerequisite_receipt_sha256"] = sha(init_path.read_bytes())
            progression_auth["basis"] = "Fresh same-process natural-init receipt; approved progression contract is unchanged."
            progression_auth_path = EVIDENCE / PROGRESSION_AUTH_NAME
            base.write_json(progression_auth_path, progression_auth)
            progression_result, progression_path = base.run_live_phase(
                adapter, emulator, identity_path, progression_auth_path,
                "natural-rate-progression", PORT, PROGRESSION_NAME, init_path, temp)
            receipt["phases"].append({"phase": "natural-rate-progression",
                "status": progression_result.get("status"), "receipt": progression_path.name,
                "sha256": sha(progression_path.read_bytes()), "process_alive_after": emulator.poll() is None})
            if progression_result.get("status") != "pass-runtime-marker-set" or emulator.poll() is not None:
                receipt["status"] = "stop-after-natural-progression"
                return finalize(base, receipt, emulator, log_file, log_path)

            callback = base.arm_enemy_callback(adapter, identity, PORT)
            receipt["part7_enemy_callback"] = callback
            cadence_result, cadence_path = run_cadence_child(
                base, emulator, identity_path, PORT, temp)
            receipt["phases"].append({"phase": "spawner-timer-reset-cadence",
                "status": cadence_result.get("status"), "receipt": cadence_path.name,
                "sha256": sha(cadence_path.read_bytes()), "process_alive_after": emulator.poll() is None})
            receipt["status"] = ("pass-spawner-cadence-audit" if
                cadence_result.get("status") == "complete-bounded-observation" and
                emulator.poll() is None and
                cadence_result.get("final_physical_logical_match") is True else
                "incomplete-spawner-cadence-audit")
            return finalize(base, receipt, emulator, log_file, log_path)
        except Exception as exc:
            receipt.update({"status": "fail-supervised-spawner-audit",
                            "error": f"{type(exc).__name__}: {exc}"})
            return finalize(base, receipt, emulator, log_file, log_path)


if __name__ == "__main__":
    raise SystemExit(main())
