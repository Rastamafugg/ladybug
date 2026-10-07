#!/usr/bin/env python3
"""Install the user-authorized BUG-087 reversal fixture before measurement."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[5]
ADAPTER_PATH = ROOT / "wiki/internal/tickets/evidence/rsch014-ready-087/bug087_ready_adapter.py"
ROUTE_AUDIT_PATH = ROOT / "wiki/internal/tickets/evidence/rsch014-ready-087/audit_reversal_route_reachability.py"
DEFAULT_IDENTITY = ROOT / "wiki/internal/tickets/evidence/rsch014-ready-087/current-root-candidate-ad1-keyboard-identity-163d-20261006.json"
EXPECTED_ROM_SHA256 = "7caa58c1ff1ef84b0b107b4b5cc46850244de1f2729dbc60f3af1f46abfac32e"
PHASE_SECONDS = 45
WARMUP_CALLBACKS = 6
FREEZE_SETUP_TICKS = 8
FIXTURE_CELL = (6, 4)
CONCURRENT_CELL = (2, 12)
REVERSE_CELL = (4, 4)
TARGET_PATH = ((6, 4), (5, 4), (4, 4))
ACTIVE_TYPE = 0x61


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_adapter():
    return load_module("bug087_ready_adapter", ADAPTER_PATH)


def expected_fb(adapter: Any, x: int, y: int) -> int:
    return adapter.ENEMY_FB_ORIGIN + (x - 12) * 4 + (y - 12) * 1280


def owner_tile(adapter: Any, probe: Any, owner: int, pointer: int) -> dict[str, Any]:
    offset = pointer - adapter.VISIBLE_START
    raw = adapter._surface_span(probe, owner, offset, 15 * 160 + 4)
    pixels = b"".join(raw[row * 160:row * 160 + 4] for row in range(16))
    return {"owner": owner, "pointer": f"${pointer:04X}", "pixel_bytes": len(pixels),
            "pixel_sha256": hashlib.sha256(pixels).hexdigest(), "pixel_nonzero": any(pixels)}


def front_identity(adapter: Any, probe: Any) -> dict[str, Any]:
    owner = adapter._logical_read(probe, adapter.FB_FRONT_ID)[0]
    state = probe.call("read_gime_state", None, 2.0)
    voff = int(state["registers"]["FF9D"])
    expected = {0: 0xC0, 1: 0xB0}.get(owner)
    if expected is None or voff != expected:
        raise RuntimeError(f"FRONT owner/GIME Voffset disagree: owner={owner}, FF9D=${voff:02X}")
    return {"front_owner": owner, "gime_ff9d_shadow": voff}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--identity", type=Path, default=DEFAULT_IDENTITY)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--deadline-seconds", type=int, default=PHASE_SECONDS)
    parser.add_argument("--warmup-callbacks", type=int, default=WARMUP_CALLBACKS)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.deadline_seconds != PHASE_SECONDS:
        raise ValueError("fixture setup deadline is exactly 45 seconds")
    if args.warmup_callbacks != WARMUP_CALLBACKS:
        raise ValueError(f"fixture setup warmup is fixed at {WARMUP_CALLBACKS} callbacks")

    adapter = load_adapter()
    route_audit = load_module("audit_reversal_route_reachability", ROUTE_AUDIT_PATH)
    identity_path = args.identity.resolve(strict=True)
    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    identity["build_dir"] = str(args.build_dir.resolve(strict=True))
    adapter.verify_identity(identity)
    if identity.get("side") != "candidate" or identity.get("full_rom_sha256") != EXPECTED_ROM_SHA256:
        raise ValueError("identity is not the approved current candidate ROM")

    started = time.monotonic()
    deadline = started + PHASE_SECONDS
    probe = adapter.RuntimeProbe(args.host, args.port, deadline)
    receipt: dict[str, Any] = {
        "schema": "bug087-deterministic-reversal-fixture-setup-v2",
        "ticket": "BUG-087",
        "phase": "pre-measurement-deterministic-reversal-fixture-setup",
        "authorized_method": "user-authorized correction: coherent direct fixture setup before the measured phase; no game-memory writes or inputs during chooser/movement acceptance",
        "deadline_seconds": PHASE_SECONDS,
        "success_marker": "source/live bytes proved; first two natural Part-7 spawner releases are active; then setup slot0=(6,4), west, substep0, valid pointer and another active legal actor; gate0=0; both owner pixels coherent; six frozen callbacks; measured phase starts with freeze timer 2",
        "timeout_meaning": "fixture setup did not observe two real Part-7 spawner releases and hydrate the fixture within its 45-second phase; no route or gameplay conclusion follows",
        "runtime_launched": False,
        "input_injected": False,
        "measurement_phase_writes": [],
        "rom_sha256": identity["full_rom_sha256"],
        "identity_sha256": hashlib.sha256(identity_path.read_bytes()).hexdigest(),
        "adapter_sha256": hashlib.sha256(ADAPTER_PATH.read_bytes()).hexdigest(),
        "fixture_setup_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "status": "running",
        "direct_setup_writes": [],
    }
    try:
        enemy_symbols = adapter._runtime_symbols(identity, "enemy")
        tick = enemy_symbols["enemy_tick_impl"]
        run_state = probe.call("get_run_state", None, 1.0)
        registers = probe.call("read_registers", None, 1.0)
        bp_id = run_state.get("last_stop_bp_id")
        if (run_state.get("state") != "halted" or run_state.get("last_stop_reason") != "breakpoint" or
                registers.get("pc") != tick or not isinstance(bp_id, int)):
            raise RuntimeError(f"setup must start halted at byte-verified enemy_tick_impl ${tick:04X}: {run_state}, {registers}")
        probe.installed[bp_id] = tick
        proof = adapter._verify_runtime_images(probe, identity, verify_staging=False, require_mapping=True)
        source_live = {
            "enemy_tick_impl": f"${tick:04X}",
            "ecd_choose": f"${enemy_symbols['ecd_choose']:04X}",
            "ecd_blocked": f"${enemy_symbols['ecd_blocked']:04X}",
            "runtime_image_proof": proof,
        }

        gates = adapter._phys_read(probe, adapter.STATE_PAGE * adapter.PAGE_BYTES +
                                   adapter.GATE_STATE - 0xA000, 20)
        gate_states = list(gates)
        legality = {
            "west_legal_at_6_4": route_audit.runtime_legal(6, 4, 3, gate_states),
            "west_legal_at_5_4": route_audit.runtime_legal(5, 4, 3, gate_states),
            "exits_at_4_4": [d for d in range(4) if route_audit.runtime_legal(4, 4, d, gate_states)],
        }
        if gates[0] != 0 or not legality["west_legal_at_6_4"] or not legality["west_legal_at_5_4"] or legality["exits_at_4_4"] != [1]:
            raise RuntimeError(f"live gate/maze state violates approved route: gate0={gates[0]}, route={legality}")

        before = adapter._low_snapshot(probe)
        records_before = adapter._enemy_records(probe)
        release_samples = []
        natural_release_start = {"active": before["enemy_active"],
                                 "released": before["enemy_released"],
                                 "records": records_before}
        while before["enemy_active"] < 2:
            remaining = deadline - time.monotonic()
            if remaining < 2.0:
                raise TimeoutError("two natural Part-7 spawner releases were not observed before fixture deadline")
            marker = probe.run_until_marker(wait_cap_seconds=min(5.0, remaining - 1.0))
            if marker.get("bp_id") != bp_id or marker.get("pc") != tick:
                raise RuntimeError(f"natural release wait expected enemy callback {bp_id} at ${tick:04X}: {marker}")
            before = adapter._low_snapshot(probe)
            records_before = adapter._enemy_records(probe)
            release_samples.append({"callback": len(release_samples) + 1,
                                    "frames": before["frames"],
                                    "enemy_active": before["enemy_active"],
                                    "enemy_released": before["enemy_released"],
                                    "active_slots": [row["slot"] for row in records_before if row["active"]]})
        natural_active = [row for row in records_before if row["active"] and row["direction"] in range(4)]
        if len(natural_active) < 2 or before["enemy_released"] < 2:
            raise RuntimeError(f"spawner counters reached two without two live natural actor records: {before}, {records_before}")
        if before["enemy_active"] != len(natural_active):
            raise RuntimeError(f"natural active count disagrees with actor records: {before}, {records_before}")
        if before["enemy_released"] != 2:
            raise RuntimeError(f"fixture expected the first two natural releases, got released={before['enemy_released']}")
        if (not route_audit.runtime_legal(*CONCURRENT_CELL, 1, gate_states) or
                not route_audit.runtime_legal(CONCURRENT_CELL[0] + 1, CONCURRENT_CELL[1], 1, gate_states)):
            raise RuntimeError(f"fixed concurrent-mover corridor is no longer legal from {CONCURRENT_CELL}")
        concurrent_pointer = expected_fb(adapter, *CONCURRENT_CELL)
        if not adapter.VISIBLE_START <= concurrent_pointer < adapter.VISIBLE_START + adapter.VISIBLE_BYTES:
            raise RuntimeError(f"concurrent-mover pointer ${concurrent_pointer:04X} is outside visible framebuffer")

        fixture_pointer = expected_fb(adapter, *FIXTURE_CELL)
        if not adapter.VISIBLE_START <= fixture_pointer < adapter.VISIBLE_START + adapter.VISIBLE_BYTES:
            raise RuntimeError(f"fixture pointer ${fixture_pointer:04X} is outside visible framebuffer")
        fixture_row = bytes([natural_active[0]["active"], fixture_pointer >> 8, fixture_pointer & 0xFF,
                             0, FIXTURE_CELL[0], FIXTURE_CELL[1], 1, 3])
        concurrent_row = bytes([natural_active[1]["active"], concurrent_pointer >> 8, concurrent_pointer & 0xFF,
                                0, CONCURRENT_CELL[0], CONCURRENT_CELL[1], 1, 1])
        record_address = adapter.STATE_PAGE * adapter.PAGE_BYTES + adapter.ENEMY_TABLE - 0xA000
        freeze_address = adapter.LOW_PAGE * adapter.PAGE_BYTES + adapter.FREEZE_TIMER
        active_count_address = adapter.LOW_PAGE * adapter.PAGE_BYTES + 0x0058
        table_fixture = fixture_row + concurrent_row + bytes(16)
        adapter._phys_write(probe, record_address, table_fixture)
        adapter._phys_write(probe, active_count_address, bytes([2, 2]))
        adapter._phys_write(probe, freeze_address, FREEZE_SETUP_TICKS.to_bytes(2, "big"))
        receipt["direct_setup_writes"] = [
            {"physical_address": f"${record_address:05X}", "value_hex": table_fixture.hex(),
             "meaning": "first two naturally released live actors relocated to valid-pointer fixture cells (6,4) west and (2,12) east; remaining rows cleared"},
            {"physical_address": f"${active_count_address:05X}", "value_hex": "0202",
             "meaning": "active and released enemy counts match the two installed fixture actors"},
            {"physical_address": f"${freeze_address:05X}", "value_hex": FREEZE_SETUP_TICKS.to_bytes(2, "big").hex(),
             "meaning": "hold movement during six pre-measurement owner-hydration callbacks"},
        ]
        if adapter._phys_read(probe, record_address, 32) != table_fixture:
            raise RuntimeError("enemy table fixture write did not read back exactly")
        if adapter._phys_read(probe, active_count_address, 2) != b"\x02\x02":
            raise RuntimeError("active/released fixture counts did not read back exactly")
        if adapter._phys_read(probe, adapter.STATE_PAGE * adapter.PAGE_BYTES +
                              adapter.GATE_STATE - 0xA000, 1)[0] != 0:
            raise RuntimeError("gate0 changed during fixture setup")

        owner_sequence = [front_identity(adapter, probe)["front_owner"]]
        callback_states = []
        for index in range(WARMUP_CALLBACKS):
            remaining = deadline - time.monotonic()
            if remaining < 2.0:
                raise TimeoutError("fixture owner-hydration callback deadline exhausted")
            marker = probe.run_until_marker(wait_cap_seconds=min(6.0, remaining - 1.0))
            if marker.get("bp_id") != bp_id or marker.get("pc") != tick:
                raise RuntimeError(f"fixture hydration expected enemy callback {bp_id} at ${tick:04X}: {marker}")
            state = adapter._low_snapshot(probe)
            records = adapter._enemy_records(probe)
            gates_now = adapter._phys_read(probe, adapter.STATE_PAGE * adapter.PAGE_BYTES +
                                           adapter.GATE_STATE - 0xA000, 1)[0]
            expected_records = (fixture_row.hex(), concurrent_row.hex())
            if tuple(row["bytes_hex"] for row in records[:2]) != expected_records or any(row["active"] for row in records[2:]):
                raise RuntimeError(f"enemy fixture records changed during frozen setup callback {index + 1}")
            if gates_now != 0 or state["freeze_timer"] != FREEZE_SETUP_TICKS - index - 1:
                raise RuntimeError(f"frozen setup boundary differs at callback {index + 1}: gate0={gates_now}, state={state}")
            owner_sequence.append(front_identity(adapter, probe)["front_owner"])
            callback_states.append({"callback": index + 1, "frames": state["frames"],
                                    "fb_sim_seq": state["fb_sim_seq"], "freeze_timer": state["freeze_timer"],
                                    "front_owner": owner_sequence[-1]})

        final_state = adapter._low_snapshot(probe)
        final_records = adapter._enemy_records(probe)
        if final_records[0] != {"slot": 0, "active": ACTIVE_TYPE, "fb": fixture_pointer,
                               "substep": 0, "cell_x": 6, "cell_y": 4, "saved_bg_valid": 1,
                               "direction": 3, "bytes_hex": fixture_row.hex()}:
            raise RuntimeError(f"slot0 fixture differs at measured phase boundary: {final_records[0]}")
        if final_state["freeze_timer"] != 2:
            raise RuntimeError(f"measured phase must start with freeze timer 2, got {final_state['freeze_timer']}")
        if set(owner_sequence) != {0, 1}:
            raise RuntimeError(f"setup did not hydrate both framebuffer owners: {owner_sequence}")
        front_state = front_identity(adapter, probe)
        both_owner_pixels = {"slot0_at_6_4": [owner_tile(adapter, probe, owner, fixture_pointer) for owner in (0, 1)],
                             "slot1_at_2_12": [owner_tile(adapter, probe, owner, concurrent_pointer) for owner in (0, 1)]}
        if not all(row["pixel_nonzero"] for rows in both_owner_pixels.values() for row in rows):
            raise RuntimeError(f"slot0 visible pixels are missing from an owner buffer: {both_owner_pixels}")
        current_front_tile = adapter._front_tile(probe, fixture_pointer)
        if current_front_tile["owner"] != front_state["front_owner"]:
            raise RuntimeError("FRONT owner changed during halted pixel audit")

        receipt.update({
            "status": "pass-fixture-ready-for-measurement",
            "elapsed_seconds": round(time.monotonic() - started, 6),
            "runtime_source_live_proof": source_live,
            "gate_bytes_hex": gates.hex(),
            "maze_legality": legality,
            "initial_state": before,
            "initial_enemy_records": records_before,
            "natural_release_boundary": {"starting_state": natural_release_start,
                                          "callback_samples": release_samples,
                                          "natural_state_before_relocation": before,
                                          "natural_active_records_before_relocation": records_before},
            "fixture_state": final_state,
            "fixture_records": final_records,
            "fixture_active_counts": {"active": final_state["enemy_active"],
                                      "released": final_state["enemy_released"]},
            "fixture_cell_path": [list(cell) for cell in TARGET_PATH],
            "concurrent_actor": final_records[1],
            "owner_hydration_callbacks": callback_states,
            "owner_sequence": owner_sequence,
            "both_owner_pixels_at_fixture": both_owner_pixels,
            "front_pixel_crosscheck": current_front_tile,
            "front_gime_identity": front_state,
            "monitor_audit": probe.audit(),
        })
    except Exception as exc:
        receipt.update({"status": "fail-fixture-setup", "error": f"{type(exc).__name__}: {exc}",
                        "elapsed_seconds": round(time.monotonic() - started, 6),
                        "monitor_audit": probe.audit()})
        raise
    finally:
        probe.close()
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))
    return 0 if receipt.get("status") == "pass-fixture-ready-for-measurement" else 2


if __name__ == "__main__":
    raise SystemExit(main())
