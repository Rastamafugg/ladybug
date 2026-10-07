#!/usr/bin/env python3
"""Verify Part-2 zero-addend movement from a legal pre-measurement fixture."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[5]
EVIDENCE = Path(__file__).resolve().parent
ADAPTER_PATH = EVIDENCE / "bug087_ready_adapter.py"
ROUTE_AUDIT_PATH = EVIDENCE / "audit_reversal_route_reachability.py"
MAZE_PATH = ROOT / "assets/arcade/maze.json"
PHASE_SECONDS = 45
WARMUP_CALLBACKS = 6
SAMPLE_CALLBACKS = 24
ACTIVE_TYPE = 0x61
START_CELL = (2, 18)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def expected_fb(adapter: Any, x: int, y: int) -> int:
    return adapter.ENEMY_FB_ORIGIN + (x - 12) * 4 + (y - 12) * 1280


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--identity", type=Path, required=True)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--natural-init-receipt", type=Path, required=True)
    parser.add_argument("--authorization", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    adapter = load_module("bug087_ready_adapter", ADAPTER_PATH)
    route_audit = load_module("audit_reversal_route_reachability", ROUTE_AUDIT_PATH)
    identity_path = args.identity.resolve(strict=True)
    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    identity["build_dir"] = str(args.build_dir.resolve(strict=True))
    adapter.verify_identity(identity)
    init_path = args.natural_init_receipt.resolve(strict=True)
    init_receipt = json.loads(init_path.read_text(encoding="utf-8"))
    auth_path = args.authorization.resolve(strict=True)
    auth = json.loads(auth_path.read_text(encoding="utf-8"))
    identity_hash = hashlib.sha256(identity_path.read_bytes()).hexdigest()
    adapter_hash = hashlib.sha256(ADAPTER_PATH.read_bytes()).hexdigest()
    if (init_receipt.get("phase") != "natural-init" or
            init_receipt.get("status") != "pass-runtime-marker-set" or
            init_receipt.get("build_side") != "candidate" or
            init_receipt.get("authorization", {}).get("identity_sha256_by_name", {}).get(identity_path.name) !=
            identity_hash):
        raise ValueError("fresh natural-init prerequisite is not a passing Part-2 candidate receipt")
    if (auth.get("runtime_authorized") is not True or
            auth.get("parent_review_status") != "parent-reviewed-and-approved" or
            auth.get("phase") != "legal-part2-zero-addend-horizontal-displacement" or
            auth.get("phase_deadline_seconds") != PHASE_SECONDS or
            auth.get("identity_sha256") != identity_hash or
            auth.get("adapter_sha256") != adapter_hash or
            auth.get("prerequisite_receipt_sha256") != hashlib.sha256(init_path.read_bytes()).hexdigest() or
            auth.get("measurement_game_memory_writes") != 0 or
            auth.get("measurement_input_injections") != 0):
        raise ValueError("zero-addend authorization does not match the current prerequisite and no-write measurement")
    if identity.get("side") != "candidate" or identity.get("full_rom_sha256") != "7caa58c1ff1ef84b0b107b4b5cc46850244de1f2729dbc60f3af1f46abfac32e":
        raise ValueError("identity is not the frozen authorized candidate ROM")

    started = time.monotonic()
    deadline = started + PHASE_SECONDS
    probe = adapter.RuntimeProbe(args.host, args.port, deadline)
    receipt: dict[str, Any] = {
        "schema": "bug087-zero-addend-fixture-measurement-v1",
        "ticket": "BUG-087",
        "phase": "legal-part2-zero-addend-horizontal-displacement",
        "phase_deadline_seconds": PHASE_SECONDS,
        "success_marker": "fresh natural Part-2 first enemy callback; verified candidate bytes; legal visible actor at (2,18) east with addend 0; 24 actual callbacks produce 24 native pixels within one endpoint pixel; no measured-phase writes or input",
        "timeout_meaning": "the legal fixture or complete 24-callback marker set did not finish within 45 seconds; this does not imply a movement result",
        "parent_authorization_basis": auth.get("basis"),
        "runtime_launched": False,
        "input_injected": False,
        "measurement_phase_writes": [],
        "identity_sha256": hashlib.sha256(identity_path.read_bytes()).hexdigest(),
        "rom_sha256": identity["full_rom_sha256"],
        "adapter_sha256": hashlib.sha256(ADAPTER_PATH.read_bytes()).hexdigest(),
        "authorization_sha256": hashlib.sha256(auth_path.read_bytes()).hexdigest(),
        "fixture_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "natural_init_receipt_sha256": hashlib.sha256(init_path.read_bytes()).hexdigest(),
        "status": "running",
    }
    try:
        symbols = adapter._runtime_symbols(identity, "enemy")
        tick = symbols["enemy_tick_impl"]
        run_state = probe.call("get_run_state", None, 1.0)
        registers = probe.call("read_registers", None, 1.0)
        if (run_state.get("state") != "halted" or registers.get("pc") != tick):
            raise RuntimeError(f"natural-init did not leave Part-2 halted at enemy callback ${tick:04X}: {run_state}, {registers}")
        proof = adapter._verify_runtime_images(probe, identity, verify_staging=False, require_mapping=True)
        tick_bp = probe.set_breakpoint(tick)
        start_state = adapter._low_snapshot(probe)
        if (start_state["stage"] != 2 or start_state["stage_pending"] != 0 or
                start_state["death_state"] != 0 or start_state["rate_addend"] != 0 or
                start_state["rate_frac"] != 0 or start_state["rate_phase"] != 0):
            raise RuntimeError(f"natural Part-2 zero-addend boundary differs: {start_state}")

        gates = adapter._phys_read(probe, adapter.STATE_PAGE * adapter.PAGE_BYTES +
                                   adapter.GATE_STATE - 0xA000, 20)
        if not route_audit.runtime_legal(*START_CELL, 1, list(gates)):
            raise RuntimeError(f"eastward fixture at {START_CELL} is not legal in live gate state")
        maze = json.loads(MAZE_PATH.read_text(encoding="utf-8"))
        maze_nav, gate_owner = maze["maze_nav"], maze["gate_owner"]
        pointer = expected_fb(adapter, *START_CELL)
        row = bytes([ACTIVE_TYPE, pointer >> 8, pointer & 0xFF, 0,
                     START_CELL[0], START_CELL[1], 1, 1])
        route = adapter._horizontal_runway_pixels(
            {"direction": 1, "cell_x": START_CELL[0], "cell_y": START_CELL[1], "substep": 0},
            maze_nav, gate_owner)
        if route < 24:
            raise RuntimeError(f"authored east corridor has only {route} pixels from the fixture")

        record_address = adapter.STATE_PAGE * adapter.PAGE_BYTES + adapter.ENEMY_TABLE - 0xA000
        count_address = adapter.LOW_PAGE * adapter.PAGE_BYTES + 0x0058
        freeze_address = adapter.LOW_PAGE * adapter.PAGE_BYTES + adapter.FREEZE_TIMER
        table = row + bytes(24)
        adapter._phys_write(probe, record_address, table)
        adapter._phys_write(probe, count_address, b"\x01\x01")
        adapter._phys_write(probe, freeze_address, (8).to_bytes(2, "big"))
        if adapter._phys_read(probe, record_address, 32) != table:
            raise RuntimeError("zero-addend actor fixture did not read back exactly")

        owner_samples = []
        hydration = []
        for callback in range(WARMUP_CALLBACKS):
            remaining = deadline - time.monotonic()
            if remaining < 2:
                raise TimeoutError("owner-hydration callbacks exhausted the phase deadline")
            marker = probe.run_until_marker(wait_cap_seconds=min(7.0, remaining - 1.0))
            if marker.get("pc") != tick:
                raise RuntimeError(f"owner hydration expected enemy callback ${tick:04X}: {marker}")
            state = adapter._low_snapshot(probe)
            current = adapter._enemy_records(probe)[0]
            if (current["bytes_hex"] != row.hex() or state["rate_addend"] != 0 or
                    state["rate_frac"] != 0 or state["rate_phase"] != 0 or
                    state["freeze_timer"] != 7 - callback):
                raise RuntimeError(f"zero-addend frozen fixture changed before measurement: {state}, {current}")
            pixel = adapter._front_tile(probe, pointer)
            owner_samples.append(pixel["owner"])
            hydration.append({"callback": callback + 1, "frames": state["frames"],
                              "fb_sim_seq": state["fb_sim_seq"], "front_pixel": pixel})
        start_front = adapter._front_tile(probe, pointer)
        start_record = adapter._enemy_records(probe)[0]
        before_measure = adapter._low_snapshot(probe)
        adapter._phys_write(probe, freeze_address, b"\x00\x00")
        pre_measure = adapter._low_snapshot(probe)
        if (pre_measure["stage"] != 2 or pre_measure["rate_addend"] != 0 or
                pre_measure["rate_phase"] != 0 or pre_measure["rate_frac"] != 0 or
                pre_measure["freeze_timer"] != 0 or start_record["bytes_hex"] != row.hex() or
                not start_front["pixel_nonzero"]):
            raise RuntimeError(f"zero-addend measured-phase boundary differs: {pre_measure}, {start_record}")

        rate_tick = adapter._runtime_symbols(identity, "rate")["rate_tick"]
        samples = []
        raw_frames = []
        logical_seq = []
        carries = moves = 0
        last_state, last_record = pre_measure, start_record
        for index in range(SAMPLE_CALLBACKS):
            remaining = deadline - time.monotonic()
            if remaining < 2:
                raise TimeoutError("24 actual zero-addend callbacks did not fit the 45-second phase")
            rate_hit = adapter._candidate_rate_marker(
                probe, rate_tick, identity, wait_cap_seconds=min(8.0, remaining - 1.0))
            probe.clear_breakpoint(rate_hit["breakpoint_id"])
            marker = probe.run_until_marker(wait_cap_seconds=min(8.0, deadline - time.monotonic() - 1.0))
            if marker.get("bp_id") != tick_bp or marker.get("pc") != tick:
                raise RuntimeError(f"sample callback marker differs at {index + 1}: {marker}")
            state = adapter._low_snapshot(probe)
            record = adapter._enemy_records(probe)[0]
            adapter._assert_actor_continuity(start_record, record, "zero-addend candidate")
            delta = record["fb"] - last_record["fb"]
            if (state["stage"] != 2 or state["death_state"] or state["freeze_timer"] or
                    state["rate_addend"] != 0 or state["rate_frac"] != 0 or
                    record["direction"] != 1 or delta not in (0, 1) or
                    not route_audit.runtime_legal(record["cell_x"], record["cell_y"], 1, list(gates))):
                raise RuntimeError(f"zero-addend legal actor state differs at callback {index + 1}: {state}, {record}, delta={delta}")
            moves += int(delta != 0)
            carries += int(state["rate_frac"] < last_state["rate_frac"])
            frame_delta = adapter._counter_delta16(state["frames"], last_state["frames"])
            seq_delta = adapter._counter_delta16(state["fb_sim_seq"], last_state["fb_sim_seq"])
            raw_frames.append(frame_delta)
            logical_seq.append(seq_delta)
            front = adapter._front_tile(probe, record["fb"]) if delta else None
            if front is not None and not front["pixel_nonzero"]:
                raise RuntimeError(f"FRONT pixels empty after movement callback {index + 1}")
            samples.append({"callback": index + 1, "marker_pc": f"${marker['pc']:04X}",
                            "rate_marker_pc": f"${rate_hit['marker']['pc']:04X}",
                            "PAR5": rate_hit["PAR5"], "mapped_rate_bytes_hex": rate_hit["mapped_bytes_hex"],
                            "record": record, "fb_delta": delta,
                            "rate_state": {key: state[key] for key in
                                           ("rate_timer", "rate_bucket", "rate_frac", "rate_phase", "rate_addend")},
                            "FRAMES_delta": frame_delta, "FB_SIM_SEQ_delta": seq_delta,
                            "front_pixel": front})
            last_state, last_record = state, record

        expected_admissions = adapter._movement_admissions(SAMPLE_CALLBACKS, carries, pre_measure["rate_phase"])
        observed_pixels = (last_record["fb"] - start_record["fb"]) * 2
        expected_pixels = expected_admissions * 2
        final_front = adapter._front_tile(probe, last_record["fb"])
        if (carries != 0 or moves != 12 or expected_admissions != 12 or
                abs(observed_pixels - expected_pixels) > 1 or
                sum(raw_frames) == 0 or sum(logical_seq) == 0 or
                not final_front["pixel_nonzero"] or set(owner_samples) != {0, 1}):
            raise RuntimeError(f"zero-addend oracle mismatch: moves={moves}, carries={carries}, observed={observed_pixels}, expected={expected_pixels}")

        receipt.update({
            "status": "pass-runtime-marker-set",
            "elapsed_seconds": round(time.monotonic() - started, 6),
            "runtime_source_live_proof": proof,
            "natural_part2_state": start_state,
            "live_gate_bytes_sha256": hashlib.sha256(gates).hexdigest(),
            "fixture": {"writes": [
                {"physical_address": f"${record_address:05X}", "value_hex": table.hex(),
                 "meaning": "one active $61 actor at legal eastward corridor (2,18), remaining records cleared"},
                {"physical_address": f"${count_address:05X}", "value_hex": "0101",
                 "meaning": "active/released counts match the single actor fixture"},
                {"physical_address": f"${freeze_address:05X}", "value_hex": "0008",
                 "meaning": "freeze only during six pre-measurement owner-hydration callbacks"},
                {"physical_address": f"${freeze_address:05X}", "value_hex": "0000",
                 "meaning": "release fixture freeze at the measurement boundary"}],
                "fixture_state_after_hydration": before_measure,
                "fixture_actor": start_record,
                "legal_corridor_clearance_pixels": route,
                "owner_hydration": hydration,
                "owner_sequence": owner_samples,
                "writes_after_measurement_start": [],
                "inputs_after_measurement_start": []},
            "measurement": {"stage": 2, "axis": "horizontal-east", "callback_count": len(samples),
                "starting_rate_state": {key: pre_measure[key] for key in
                                         ("rate_timer", "rate_bucket", "rate_frac", "rate_phase", "rate_addend")},
                "ending_rate_state": {key: last_state[key] for key in
                                       ("rate_timer", "rate_bucket", "rate_frac", "rate_phase", "rate_addend")},
                "fractional_carries": carries, "movement_admissions": expected_admissions,
                "observed_moving_callbacks": moves,
                "starting_fb": start_record["fb"], "ending_fb": last_record["fb"],
                "observed_pixels": observed_pixels, "expected_pixels": expected_pixels,
                "tolerance_pixels": 1, "FRAMES_delta_total": sum(raw_frames),
                "FB_SIM_SEQ_delta_total": sum(logical_seq),
                "initial_front_pixel": start_front, "final_front_pixel": final_front,
                "samples": samples},
            "monitor_audit": probe.audit()})
    except Exception as exc:
        receipt.update({"status": "fail-runtime-marker", "error": f"{type(exc).__name__}: {exc}",
                        "elapsed_seconds": round(time.monotonic() - started, 6),
                        "monitor_audit": probe.audit()})
        raise
    finally:
        probe.close()
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return 0 if receipt.get("status") == "pass-runtime-marker-set" else 2


if __name__ == "__main__":
    raise SystemExit(main())
