#!/usr/bin/env python3
"""Bounded BUG-087 cold-start mainloop and monitor-lifecycle diagnostic."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import socket
import subprocess
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[5]
EVIDENCE = Path(__file__).resolve().parent
ADAPTER_PATH = EVIDENCE / "bug087_ready_adapter.py"
IDENTITY_PATH = EVIDENCE / "current-root-candidate-ad1-keyboard-identity-163d-20261006.json"
EXPECTED_ROM = "7caa58c1ff1ef84b0b107b4b5cc46850244de1f2729dbc60f3af1f46abfac32e"
DEADLINE_SECONDS = 15
CLIENT_WAIT_SECONDS = 12


def load_adapter():
    spec = importlib.util.spec_from_file_location("bug087_ready_adapter", ADAPTER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load the current BUG-087 adapter")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compact_audit(audit: dict[str, Any]) -> dict[str, Any]:
    """Retain call provenance without duplicating large passing memory reads."""
    rows = []
    for source in audit.get("last_monitor_calls", []):
        row = dict(source)
        envelope = row.get("response_envelope")
        if isinstance(envelope, dict) and isinstance(envelope.get("result"), dict):
            result = dict(envelope["result"])
            data_hex = result.get("data")
            if isinstance(data_hex, str):
                raw = bytes.fromhex(data_hex)
                result["data"] = {"bytes": len(raw), "sha256": digest(raw)}
            envelope = dict(envelope)
            envelope["result"] = result
            row["response_envelope"] = envelope
        rows.append(row)
    return {"monitor_call_count": audit.get("monitor_call_count"),
            "monitor_call_ledger_sha256": audit.get("monitor_call_ledger_sha256"),
            "last_monitor_calls": rows}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=17687)
    parser.add_argument("--out", type=Path,
                        default=EVIDENCE / "bug087-mainloop-lifecycle-20261007.json")
    parser.add_argument("--log", type=Path,
                        default=EVIDENCE / "bug087-mainloop-lifecycle-20261007.log")
    args = parser.parse_args()

    if args.out.exists() or args.log.exists():
        raise FileExistsError("refusing to overwrite a retained lifecycle result or log")
    adapter = load_adapter()
    identity = json.loads(IDENTITY_PATH.read_text(encoding="utf-8"))
    build = Path("/mnt/e/projects/ladybug/build").resolve(strict=True)
    identity["build_dir"] = str(build)
    adapter.verify_identity(identity)
    rom_path = build / "ladybug.rom"
    rom_hash = digest(rom_path.read_bytes())
    if rom_hash != EXPECTED_ROM:
        raise RuntimeError(f"candidate ROM identity changed: {rom_hash}")

    xroar = ROOT / "docs/reference/xroar/src/xroar"
    xroar_hash = digest(xroar.read_bytes())
    with socket.socket() as reserve:
        reserve.bind(("127.0.0.1", args.port))

    started = time.monotonic()
    deadline = started + DEADLINE_SECONDS
    log_file = args.log.open("wb")
    proc: subprocess.Popen[bytes] | None = None
    probe = None
    receipt: dict[str, Any] = {
        "schema": "bug087-mainloop-lifecycle-20261007-v1",
        "ticket": "BUG-087",
        "phase": "cold-candidate-mainloop-lifecycle",
        "candidate_rom_sha256": rom_hash,
        "candidate_identity_sha256": digest(IDENTITY_PATH.read_bytes()),
        "xroar_path": str(xroar),
        "xroar_sha256": xroar_hash,
        "monitor_port": args.port,
        "deadline_seconds": DEADLINE_SECONDS,
        "success_marker": "fresh exact candidate process reaches resident mainloop within 12 seconds; runtime resident bytes match source/build before PC is interpreted; process and monitor remain available for a read-only state query",
        "timeout_meaning": "mainloop marker or response was not observed within this monitor diagnostic; no gameplay or movement-speed conclusion follows",
        "direct_game_memory_writes": False,
        "input_injected": False,
        "status": "running",
    }
    previous_attempt = EVIDENCE / "bug087-mainloop-lifecycle-first-attach-failure-20261007.json"
    if previous_attempt.exists():
        receipt["prior_setup_attempt"] = {
            "receipt": previous_attempt.name,
            "sha256": digest(previous_attempt.read_bytes()),
            "meaning": "client attachment failed before run or breakpoint; setup mechanics were corrected before this diagnostic rerun",
        }
    try:
        command = [str(xroar), "-ui", "null", "-ao", "null", "-machine", "coco3",
                   "-ram", "512", "-cart-type", "gmc", "-cart-rom", str(rom_path),
                   "-cart-autorun", "-monitor", f"127.0.0.1:{args.port}",
                   "-monitor-halt-on-start"]
        proc = subprocess.Popen(command, cwd=ROOT, stdout=log_file, stderr=subprocess.STDOUT)
        receipt["xroar_pid"] = proc.pid
        ready_deadline = min(deadline - 2.0, time.monotonic() + 4.0)
        last_connect_error = None
        while probe is None and time.monotonic() < ready_deadline:
            if proc.poll() is not None:
                raise RuntimeError(f"XRoar exited before monitor readiness with code {proc.returncode}")
            try:
                # Attach with the actual monitor client. A disposable readiness
                # connection can race the XRoar accept loop and is not evidence
                # that the endpoint is ready for the diagnostic client.
                probe = adapter.RuntimeProbe("127.0.0.1", args.port, deadline)
            except (ConnectionRefusedError, TimeoutError, OSError) as exc:
                last_connect_error = f"{type(exc).__name__}: {exc}"
                time.sleep(0.05)
        if probe is None:
            raise TimeoutError(f"fresh candidate monitor client did not attach: {last_connect_error}")
        mainloop = adapter._runtime_symbols(identity, "main")["mainloop"]
        bp_id = probe.set_breakpoint(mainloop)
        run_id = probe.client.next_id
        run_ack = probe.call("run", None, cap=1.0)
        if run_ack.get("ok") is not True:
            raise RuntimeError(f"XRoar did not acknowledge run: {run_ack}")
        wait_id = probe.client.next_id
        if wait_id != run_id + 1:
            raise RuntimeError("mainloop sentinel wait did not immediately follow run")
        wait_cap = min(CLIENT_WAIT_SECONDS, max(0.1, deadline - time.monotonic() - 1.0))
        server_wait_ms = max(1, int((wait_cap - 1.0) * 1000))
        stop = probe.call("wait_for_stop", {"timeout_ms": server_wait_ms}, cap=wait_cap)
        wait_record = probe.last_calls[-1]
        receipt["run_ack"] = run_ack
        receipt["wait_record"] = wait_record

        if stop.get("reason") == "breakpoint":
            # Prove the whole mapped resident image before interpreting the stop PC.
            proof = adapter._verify_runtime_images(
                probe, identity, need_enemy=False, verify_staging=False,
                require_mapping=False)
            pc = stop.get("pc")
            observed_bp = stop.get("bp_id")
            if pc != mainloop or observed_bp != bp_id:
                raise RuntimeError("breakpoint stop did not match the byte-verified resident mainloop")
            logical = adapter._logical_read(probe, mainloop, 8)
            rom = rom_path.read_bytes()
            source_offset = adapter.BANK1_ROM_OFFSET + (mainloop - 0xC000)
            expected = rom[source_offset:source_offset + len(logical)]
            if logical != expected:
                raise RuntimeError("mainloop live instruction bytes differ from the built ROM")
            state = probe.call("get_run_state", None, cap=1.0)
            if state.get("state") != "halted" or state.get("last_stop_reason") != "breakpoint":
                raise RuntimeError(f"mainloop marker did not leave a durable breakpoint stop: {state}")
            receipt.update({"mainloop_pc": f"${pc:04X}", "breakpoint_id": observed_bp,
                            "mainloop_bytes_hex": logical.hex(),
                            "resident_image_proof": proof,
                            "durable_state": state,
                            "status": "pass-mainloop-marker-process-alive"})
        else:
            receipt.update({"status": "fail-mainloop-marker-not-observed", "stop": stop,
                            "interpretation": "monitor wait completed without the resident marker"})

        receipt["process_exit_after_marker"] = proc.poll()
        time.sleep(0.25)
        receipt["process_exit_after_250ms"] = proc.poll()
        receipt["process_alive_after_marker"] = proc.poll() is None
        receipt["elapsed_seconds"] = round(time.monotonic() - started, 6)
        receipt["monitor_audit"] = compact_audit(probe.audit())
    except Exception as exc:
        receipt.update({"status": "fail-diagnostic", "error": f"{type(exc).__name__}: {exc}",
                        "elapsed_seconds": round(time.monotonic() - started, 6)})
        if probe is not None:
            receipt["monitor_audit"] = compact_audit(probe.audit())
    finally:
        if probe is not None:
            probe.close()
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=2.0)
                receipt["owned_process_cleanup"] = "terminated-after-diagnostic"
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=1.0)
                receipt["owned_process_cleanup"] = "killed-after-terminate-timeout"
        if proc is not None:
            receipt["process_returncode_after_cleanup"] = proc.returncode
        log_file.close()
        log_bytes = args.log.read_bytes()
        receipt["xroar_log_sha256"] = digest(log_bytes)
        receipt["xroar_log_tail"] = log_bytes.decode("utf-8", "replace")[-2000:]
        receipt["receipt_created_utc_date"] = "2026-10-07"
        args.out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(receipt, indent=2))
    return 0 if receipt.get("status") == "pass-mainloop-marker-process-alive" else 2


if __name__ == "__main__":
    raise SystemExit(main())
