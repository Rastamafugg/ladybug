#!/usr/bin/env python3
"""Continue a fresh natural Part-7 run through true Part-9 and Part-10 init."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[5]
EVIDENCE = Path(__file__).resolve().parent
ADAPTER_PATH = EVIDENCE / "bug087_ready_adapter.py"
PHASE_SECONDS = 45
DOTS_ADDRESS = 0x0025
BONUS_ADDRESS = 0x0033
UP_KEY = 0x2B


def load_adapter():
    import importlib.util
    spec = importlib.util.spec_from_file_location("bug087_ready_adapter", ADAPTER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load current BUG-087 runtime adapter")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--identity", type=Path, required=True)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--progression-receipt", type=Path, required=True)
    parser.add_argument("--authorization", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    adapter = load_adapter()
    identity_path = args.identity.resolve(strict=True)
    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    identity["build_dir"] = str(args.build_dir.resolve(strict=True))
    adapter.verify_identity(identity)
    prog_path = args.progression_receipt.resolve(strict=True)
    prog = json.loads(prog_path.read_text(encoding="utf-8"))
    auth_path = args.authorization.resolve(strict=True)
    auth = json.loads(auth_path.read_text(encoding="utf-8"))
    identity_hash = sha(identity_path.read_bytes())
    script_hash = sha(Path(__file__).read_bytes())
    if (prog.get("phase") != "natural-rate-progression" or
            prog.get("status") != "pass-runtime-marker-set" or
            prog.get("build_side") != "candidate" or
            prog.get("part7_ready_state", {}).get("stage") != 7 or
            prog.get("never_wrote_STAGE_or_STAGE_PENDING") is not True):
        raise ValueError("fresh natural progression did not stop at the approved Part-7 ready boundary")
    if (auth.get("runtime_authorized") is not True or
            auth.get("parent_review_status") != "parent-reviewed-and-approved" or
            auth.get("phase") != "natural-part9-part10-reset-continuation" or
            auth.get("phase_deadline_seconds") != PHASE_SECONDS or
            auth.get("identity_sha256") != identity_hash or
            auth.get("adapter_sha256") != sha(ADAPTER_PATH.read_bytes()) or
            auth.get("continuation_script_sha256") != script_hash or
            auth.get("prerequisite_receipt_sha256") != sha(prog_path.read_bytes()) or
            auth.get("writes_to_STAGE_or_STAGE_PENDING") is not False):
        raise ValueError("Part-9/10 continuation authorization does not match current evidence")

    started = time.monotonic()
    deadline = started + PHASE_SECONDS
    probe = adapter.RuntimeProbe(args.host, args.port, deadline)
    receipt: dict[str, Any] = {
        "schema": "bug087-natural-part9-part10-continuation-v1",
        "ticket": "BUG-087",
        "phase": "natural-part9-part10-reset-continuation",
        "phase_deadline_seconds": PHASE_SECONDS,
        "success_marker": "same fresh natural process from Part-7; actual Up/final-dot transitions through Part-8, Part-9 and Part-10; exact candidate bytes at true init markers; Part-9 reset addend 0 and Part-10 addend $33",
        "timeout_meaning": "one or more actual stage handoffs or true init markers did not complete within the bounded continuation; no stage-rate conclusion follows for missing markers",
        "runtime_launched": False,
        "measurement_game_memory_writes": [],
        "measurement_input_injections": [],
        "candidate_identity_sha256": identity_hash,
        "candidate_rom_sha256": identity["full_rom_sha256"],
        "adapter_sha256": sha(ADAPTER_PATH.read_bytes()),
        "script_sha256": script_hash,
        "authorization_sha256": sha(auth_path.read_bytes()),
        "prerequisite_receipt_sha256": sha(prog_path.read_bytes()),
        "status": "running",
    }
    try:
        main = adapter._runtime_symbols(identity, "main")
        enemy = adapter._runtime_symbols(identity, "enemy")
        presentation = adapter._runtime_symbols(identity, "presentation")
        rate = adapter._runtime_symbols(identity, "rate")
        tick = enemy["enemy_tick_impl"]
        normal_game_return = presentation["normal_game"] + 1
        run_state = probe.call("get_run_state", None, 1.0)
        regs = probe.call("read_registers", None, 1.0)
        proof = adapter._verify_runtime_images(probe, identity, verify_staging=False,
                                               require_mapping=True)
        if (run_state.get("state") != "halted" or regs.get("pc") != normal_game_return):
            raise RuntimeError(f"continuation must start at the Part-7 player-entry return ${normal_game_return:04X}: {run_state}, {regs}")
        initial = adapter._low_snapshot(probe)
        if (initial["stage"] != 7 or initial["stage_pending"] != 0 or
                initial["rate_addend"] != 0x33 or initial["death_state"] != 0):
            raise RuntimeError(f"natural Part-7 continuation boundary differs: {initial}")

        runtime_image = (Path(identity["build_dir"]) / "ladybug-runtime.rom").read_bytes()
        enemy_image = (Path(identity["build_dir"]) / "ladybug-enemy-runtime.rom").read_bytes()
        rate_helper = (Path(identity["build_dir"]) / "ladybug-rate-helper.bin").read_bytes()
        presentation_image = (Path(identity["build_dir"]) / "ladybug-presentation-runtime.bin").read_bytes()
        normal_offset = presentation["normal_game"] - 0x1900
        if presentation_image[normal_offset:normal_offset + 2] != b"\x4f\x39":
            raise RuntimeError("normal_game return marker is not the identity-pinned CLRA/RTS boundary")

        transitions = []
        stage_init_markers = []

        def wait_for_player_entry(stage: int) -> dict[str, Any]:
            bp = probe.set_breakpoint(normal_game_return)
            history = []
            state = None
            try:
                for _ in range(64):
                    adapter._run_exact_marker(probe, bp, normal_game_return,
                                              f"Part-{stage} normal_game return/player entry", 3.0)
                    state = adapter._low_snapshot(probe)
                    row = {key: state[key] for key in
                           ("initial_entry_state", "player_cell_x", "player_cell_y", "stage", "stage_pending")}
                    history.append(row)
                    if state["stage"] != stage:
                        raise RuntimeError(f"player entry reached Part {state['stage']}, expected {stage}")
                    if (state["initial_entry_state"] == 0 and
                            (state["player_cell_x"], state["player_cell_y"]) == (12, 18) and
                            state["stage_pending"] == 0):
                        return {"state": state, "dispatch_history": history}
            finally:
                probe.clear_breakpoint(bp)
            raise TimeoutError(f"Part-{stage} player entry did not finish within 64 normal_game returns")

        def observe_stage_init(stage: int) -> list[dict[str, Any]]:
            points = {"init_enemy": main["init_enemy"],
                      "rate_enemy_init_shim": rate["rate_enemy_init_shim"],
                      "enemy_init_impl": enemy["enemy_init_impl"],
                      "first_enemy_tick": tick}
            ids = {name: probe.set_breakpoint(address) for name, address in points.items()}
            order = ("init_enemy", "rate_enemy_init_shim", "enemy_init_impl", "first_enemy_tick")
            observed = []
            try:
                for name in order:
                    marker = adapter._run_exact_marker(probe, ids[name], points[name],
                                                       f"natural Part-{stage} {name}", 12.0)
                    state = adapter._low_snapshot(probe)
                    sample: dict[str, Any] = {"marker": name, "pc": f"${marker['pc']:04X}",
                                              "state": state}
                    if name == "init_enemy":
                        offset = points[name] - 0xC000
                        live = adapter._logical_read(probe, points[name], 3)
                        adapter._require_identity_bytes(runtime_image[offset:offset + 3], live,
                                                        f"Part-{stage} resident init entry")
                        if state["stage"] != stage:
                            raise RuntimeError(f"Part-{stage} init entry reports stage {state['stage']}")
                        sample["live_source_bytes_hex"] = live.hex()
                    elif name == "rate_enemy_init_shim":
                        par5 = adapter._logical_read(probe, 0xFFA5)[0] & 0x3F
                        live = adapter._read_spans(probe, adapter.STATE_PAGE, 0x03B0, len(rate_helper))
                        adapter._require_identity_bytes(rate_helper, live, f"Part-{stage} page-$34 rate helper")
                        if par5 != adapter.STATE_PAGE:
                            raise RuntimeError(f"Part-{stage} rate init entered with PAR5=${par5:02X}")
                        sample.update({"PAR5": par5, "rate_helper_sha256": sha(live)})
                    else:
                        if adapter._logical_read(probe, 0xFFA0)[0] & 0x3F != adapter.LOW_PAGE:
                            raise RuntimeError(f"Part-{stage} {name} is not mapped through PAR0 page $38")
                        live = adapter._read_spans(probe, adapter.LOW_PAGE, 0x0800, len(enemy_image))
                        adapter._require_identity_bytes(enemy_image, live, f"Part-{stage} enemy module")
                        if name == "enemy_init_impl":
                            expected = adapter._rate_expected(stage, 0)
                            got = (state["rate_timer"], state["rate_bucket"], state["rate_frac"],
                                   state["rate_phase"], state["rate_addend"])
                            target = (96, 0, 0, 0, expected)
                            if got != target:
                                raise RuntimeError(f"Part-{stage} true-init rate reset differs: {got}, expected {target}")
                            sample.update({"rate_reset_matches": True,
                                           "expected_addend": expected,
                                           "enemy_module_sha256": sha(live)})
                        else:
                            sample["enemy_records"] = adapter._enemy_records(probe)
                    probe.clear_breakpoint(ids[name])
                    observed.append(sample)
                    stage_init_markers.append(sample)
            finally:
                for name, bp in ids.items():
                    if bp in probe.installed:
                        probe.clear_breakpoint(bp)
            return observed

        for old_stage in (7, 8, 9):
            if time.monotonic() >= deadline - 2:
                raise TimeoutError("Part-7-to-Part-10 continuation exhausted its 45-second phase")
            before_fixture = adapter._low_snapshot(probe)
            if before_fixture["stage"] != old_stage or before_fixture["stage_pending"] != 0:
                raise RuntimeError(f"Part-{old_stage} final-dot setup is not at an active player stage: {before_fixture}")
            low_phys = adapter.LOW_PAGE * adapter.PAGE_BYTES
            adapter._phys_write(probe, low_phys + DOTS_ADDRESS, b"\x01")
            adapter._phys_write(probe, low_phys + BONUS_ADDRESS, b"\x00")
            fixture = adapter._low_snapshot(probe)
            if (fixture["stage"] != old_stage or fixture["stage_pending"] != 0 or
                    fixture["dots_left"] != 1 or fixture["bonus_left"] != 0):
                raise RuntimeError(f"Part-{old_stage} final-dot fixture readback differs: {fixture}")
            next_bp = probe.set_breakpoint(main["next_stage"])
            press = adapter._inject_key(probe, UP_KEY, "press")
            marker = adapter._run_exact_marker(probe, next_bp, main["next_stage"],
                                               f"real Part-{old_stage + 1} next_stage", 12.0)
            release = adapter._inject_key(probe, UP_KEY, "release")
            handoff = adapter._low_snapshot(probe)
            probe.clear_breakpoint(next_bp)
            if (handoff["stage"] != old_stage or handoff["stage_pending"] == 0 or
                    handoff["dots_left"] != 0 or handoff["bonus_left"] != 0):
                raise RuntimeError(f"real Part-{old_stage}-to-Part-{old_stage + 1} handoff differs: {handoff}")
            target_stage = old_stage + 1
            init_rows = observe_stage_init(target_stage)
            transition = {"from_stage": old_stage, "to_stage": target_stage,
                          "fixture_before_up": fixture,
                          "writes_only": {"DOTS_LEFT": 1, "BONUS_LEFT": 0},
                          "up_press_ack": press, "up_release_ack": release,
                          "next_stage_marker_pc": f"${marker['pc']:04X}",
                          "handoff_state": handoff,
                          "init_markers": init_rows}
            if target_stage < 10:
                transition["player_entry"] = wait_for_player_entry(target_stage)
            transitions.append(transition)

        part9 = next(row for row in stage_init_markers
                     if row["marker"] == "enemy_init_impl" and row["state"]["stage"] == 9)
        part10 = next(row for row in stage_init_markers
                      if row["marker"] == "enemy_init_impl" and row["state"]["stage"] == 10)
        if (part9.get("expected_addend") != 0x00 or part10.get("expected_addend") != 0x33 or
                not part9.get("rate_reset_matches") or not part10.get("rate_reset_matches")):
            raise RuntimeError("true Part-9/10 init reset markers do not match the approved rate table")
        receipt.update({"status": "pass-runtime-marker-set",
                        "elapsed_seconds": round(time.monotonic() - started, 6),
                        "starting_pc": f"${regs['pc']:04X}" if "regs" in locals() else None,
                        "starting_part7_state": initial,
                        "source_live_identity_proof": proof,
                        "stage_transitions": transitions,
                        "stage_init_observations": stage_init_markers,
                        "part9_true_init_rate_reset": part9,
                        "part10_true_init_rate_reset": part10,
                        "never_wrote_STAGE_or_STAGE_PENDING": True,
                        "writes_only_per_transition": {"DOTS_LEFT": 1, "BONUS_LEFT": 0},
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
