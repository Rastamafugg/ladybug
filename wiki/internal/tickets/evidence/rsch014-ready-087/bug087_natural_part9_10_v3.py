#!/usr/bin/env python3
"""Continue a fresh natural Part-7 run through real final-dot Part-9/10 init."""

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
PLAYER_DIR = 0x0006
PLAYER_STEP = 0x0008
PLAYER_CELL_X = 0x0009
PLAYER_CELL_Y = 0x000A
PLAYER_WANT = 0x000F
PLAYER_MANUAL = 0x0018
TURN_SNAP = 0x0056
TARGET_X = 12
TARGET_Y = 17
START_X = 12
START_Y = 18


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


def parse_maze_section(path: Path, name: str) -> list[list[int]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    start = next((index for index, line in enumerate(lines) if line.strip() == name), None)
    if start is None:
        raise ValueError(f"candidate maze source lacks {name}")
    rows: list[list[int]] = []
    for line in lines[start + 1:]:
        stripped = line.strip()
        if not stripped.startswith("fcb"):
            break
        rows.append([int(item.strip().replace("$", ""), 16)
                     for item in stripped[3:].split(",")])
    if len(rows) != 24 or any(len(row) != 24 for row in rows):
        raise ValueError(f"candidate maze {name} is not a 24x24 table")
    return rows


def source_symbol(path: Path, name: str) -> int:
    import re
    matches = re.findall(rf"^Symbol: {re.escape(name)} .* = ([0-9A-Fa-f]+)$",
                         path.read_text(encoding="utf-8"), re.MULTILINE)
    if len(matches) != 1:
        raise ValueError(f"candidate main map does not identify one {name} symbol")
    return int(matches[0], 16)


def player_state(adapter, probe) -> dict[str, int]:
    low = adapter._phys_read(probe, adapter.LOW_PAGE * adapter.PAGE_BYTES, 0x60)
    return {"joy_dir": low[5], "direction": low[PLAYER_DIR], "step": low[PLAYER_STEP],
            "cell_x": low[PLAYER_CELL_X], "cell_y": low[PLAYER_CELL_Y],
            "want": low[PLAYER_WANT], "manual": low[PLAYER_MANUAL],
            "turn_snap": low[TURN_SNAP]}


def stage_player_entry(adapter, probe, stage: int, normal_game_return: int,
                       deadline: float) -> dict[str, Any]:
    bp = probe.set_breakpoint(normal_game_return)
    history = []
    try:
        for _ in range(64):
            remaining = deadline - time.monotonic()
            if remaining <= 0.5:
                raise TimeoutError("Part-7-to-Part-10 continuation exhausted its 45-second phase")
            cap = min(2.0, remaining - 0.25)
            adapter._run_exact_marker(probe, bp, normal_game_return,
                                      f"Part-{stage} normal_game return/player entry", cap)
            state = adapter._low_snapshot(probe)
            player = player_state(adapter, probe)
            row = {"stage": state["stage"], "stage_pending": state["stage_pending"],
                   "initial_entry_state": state["initial_entry_state"], **player}
            history.append(row)
            if state["stage"] != stage:
                raise RuntimeError(f"player entry reached Part {state['stage']}, expected {stage}")
            if (state["initial_entry_state"] == 0 and player["cell_x"] == START_X and
                    player["cell_y"] == START_Y and player["step"] == 0 and
                    state["stage_pending"] == 0):
                return {"state": state, "player_state": player, "dispatch_history": history}
    finally:
        probe.clear_breakpoint(bp)
    raise TimeoutError(f"Part-{stage} legal player-entry fixture point not reached")


def observe_stage_init(adapter, probe, identity: dict[str, Any], stage: int,
                       main: dict[str, int], enemy: dict[str, int], rate: dict[str, int],
                       runtime_image: bytes, enemy_image: bytes, rate_helper: bytes,
                       deadline: float, stage_init_markers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tick = enemy["enemy_tick_impl"]
    points = {"init_enemy": main["init_enemy"],
              "rate_enemy_init_shim": rate["rate_enemy_init_shim"],
              "enemy_init_impl": enemy["enemy_init_impl"],
              "first_enemy_tick": tick}
    ids = {name: probe.set_breakpoint(address) for name, address in points.items()}
    order = ("init_enemy", "rate_enemy_init_shim", "enemy_init_impl", "first_enemy_tick")
    observed = []
    try:
        for name in order:
            remaining = deadline - time.monotonic()
            if remaining <= 0.5:
                raise TimeoutError("Part-7-to-Part-10 continuation exhausted its 45-second phase")
            marker = adapter._run_exact_marker(probe, ids[name], points[name],
                                               f"natural Part-{stage} {name}",
                                               min(12.0, remaining - 0.25))
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
                adapter._require_identity_bytes(rate_helper, live,
                                                f"Part-{stage} page-$34 rate helper")
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
                    sample.update({"rate_reset_matches": True, "expected_addend": expected,
                                   "enemy_module_sha256": sha(live)})
                else:
                    sample["enemy_records"] = adapter._enemy_records(probe)
            probe.clear_breakpoint(ids[name])
            observed.append(sample)
            stage_init_markers.append(sample)
    finally:
        for bp in ids.values():
            if bp in probe.installed:
                probe.clear_breakpoint(bp)
    return observed


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
            auth.get("phase") != "natural-part9-part10-reset-continuation-v3" or
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
        "schema": "bug087-natural-part9-part10-continuation-v3",
        "ticket": "BUG-087",
        "phase": "natural-part9-part10-reset-continuation-v3",
        "phase_deadline_seconds": PHASE_SECONDS,
        "success_marker": "same fresh natural process from Part-7; source-legal Up final-dot movement through Part-8, Part-9 and Part-10; actual eat_dot, check_stage_clear, next_stage and true init markers; Part-9 addend 0 and Part-10 addend $33",
        "timeout_meaning": "one or more actual final-dot transitions or true init markers did not complete within the bounded continuation; no stage-rate conclusion follows for missing markers",
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

        maze_path = Path(identity["build_dir"]) / "ladybug_maze.inc"
        main_map = Path(identity["build_dir"]) / "ladybug.map"
        source_main = adapter.ROOT / "src/main.s"
        cells = parse_maze_section(maze_path, "maze_cells")
        nav = parse_maze_section(maze_path, "maze_nav")
        owners = parse_maze_section(maze_path, "maze_gate_owner")
        offsets = {"start": START_Y * 24 + START_X, "target": TARGET_Y * 24 + TARGET_X}
        if not (nav[START_Y][START_X] & 0x01 and nav[TARGET_Y][TARGET_X] & 0x04):
            raise RuntimeError("source maze does not prove legal north movement and reciprocal target entry")
        if owners[START_Y][START_X] or owners[TARGET_Y][TARGET_X]:
            raise RuntimeError("selected north movement crosses a gate-owned cell")
        if cells[TARGET_Y][TARGET_X] & 0x80:
            raise RuntimeError("selected clean target unexpectedly begins with a source dot")
        symbols = {name: source_symbol(main_map, name)
                   for name in ("eat_dot", "check_stage_clear", "next_stage")}
        code = source_main.read_text(encoding="utf-8")
        for required in ("can_move\n", "leax    maze_nav,pcr", "andb    a,x             ; target must admit the reciprocal direction",
                         "eat_dot\n", "lbsr    check_stage_clear", "check_stage_clear\n",
                         "inc     STAGE_PENDING", "next_stage\n", "clr     STAGE_PENDING"):
            if required not in code:
                raise RuntimeError(f"source acceptance path no longer contains required instruction: {required!r}")
        player_before = player_state(adapter, probe)
        if (player_before["cell_x"], player_before["cell_y"], player_before["step"]) != (START_X, START_Y, 0):
            raise RuntimeError(f"Part-7 player is not at the legal fixture origin: {player_before}")
        if initial["initial_entry_state"] != 0:
            raise RuntimeError(f"Part-7 initial entry has not completed: {initial}")

        runtime_image = (Path(identity["build_dir"]) / "ladybug-runtime.rom").read_bytes()
        enemy_image = (Path(identity["build_dir"]) / "ladybug-enemy-runtime.rom").read_bytes()
        rate_helper = (Path(identity["build_dir"]) / "ladybug-rate-helper.bin").read_bytes()
        presentation_image = (Path(identity["build_dir"]) / "ladybug-presentation-runtime.bin").read_bytes()
        normal_offset = presentation["normal_game"] - 0x1900
        if presentation_image[normal_offset:normal_offset + 2] != b"\x4f\x39":
            raise RuntimeError("normal_game return marker is not the identity-pinned CLRA/RTS boundary")

        for name, address in symbols.items():
            offset = address - 0xC000
            expected = runtime_image[offset:offset + 4]
            live = adapter._logical_read(probe, address, 4)
            adapter._require_identity_bytes(expected, live, f"candidate {name} source/live entry")

        transitions = []
        stage_init_markers = []
        for old_stage in (7, 8, 9):
            if time.monotonic() >= deadline - 2:
                raise TimeoutError("Part-7-to-Part-10 continuation exhausted its 45-second phase")
            before_fixture = adapter._low_snapshot(probe)
            if before_fixture["stage"] != old_stage or before_fixture["stage_pending"] != 0:
                raise RuntimeError(f"Part-{old_stage} final-dot setup is not at an active player stage: {before_fixture}")
            current_player = player_state(adapter, probe)
            if (current_player["cell_x"], current_player["cell_y"], current_player["step"]) != (START_X, START_Y, 0):
                raise RuntimeError(f"Part-{old_stage} player is not at legal north fixture origin: {current_player}")
            maze_phys = adapter.STATE_PAGE * adapter.PAGE_BYTES
            target_before = adapter._phys_read(probe, maze_phys + offsets["target"], 1)[0]
            if (target_before & 0x7F) != cells[TARGET_Y][TARGET_X] or target_before & 0x80:
                raise RuntimeError(f"Part-{old_stage} target maze byte differs from its clean source style: ${target_before:02X}")
            low_phys = adapter.LOW_PAGE * adapter.PAGE_BYTES
            writes = [
                {"symbol": "DOTS_LEFT", "physical_address": low_phys + DOTS_ADDRESS,
                 "before": before_fixture["dots_left"], "after": 1},
                {"symbol": "BONUS_LEFT", "physical_address": low_phys + BONUS_ADDRESS,
                 "before": before_fixture["bonus_left"], "after": 0},
                {"symbol": "MAZE_STATE_TARGET_DOT_BIT", "physical_address": maze_phys + offsets["target"],
                 "before": target_before, "after": target_before | 0x80},
            ]
            adapter._phys_write(probe, low_phys + DOTS_ADDRESS, b"\x01")
            adapter._phys_write(probe, low_phys + BONUS_ADDRESS, b"\x00")
            adapter._phys_write(probe, maze_phys + offsets["target"], bytes([target_before | 0x80]))
            fixture = adapter._low_snapshot(probe)
            if (fixture["stage"] != old_stage or fixture["stage_pending"] != 0 or
                    fixture["dots_left"] != 1 or fixture["bonus_left"] != 0 or
                    adapter._phys_read(probe, maze_phys + offsets["target"], 1)[0] != (target_before | 0x80)):
                raise RuntimeError(f"Part-{old_stage} final-dot fixture readback differs: {fixture}")
            source_live = {"current_player": current_player,
                           "target": {"x": TARGET_X, "y": TARGET_Y,
                                      "offset": offsets["target"], "source_byte": cells[TARGET_Y][TARGET_X],
                                      "source_nav_target": nav[TARGET_Y][TARGET_X],
                                      "source_nav_current": nav[START_Y][START_X],
                                      "source_gate_owner_current": owners[START_Y][START_X],
                                      "source_gate_owner_target": owners[TARGET_Y][TARGET_X],
                                      "live_before_byte": target_before,
                                      "live_fixture_byte": target_before | 0x80},
                           "writes": writes}
            if fixture["stage_pending"] != 0:
                raise RuntimeError("fixture setup must leave STAGE_PENDING unchanged at zero")

            eat_addr = symbols["eat_dot"]
            check_addr = symbols["check_stage_clear"]
            eat_bp = probe.set_breakpoint(eat_addr)
            check_bp = probe.set_breakpoint(check_addr)
            next_bp = probe.set_breakpoint(main["next_stage"])
            press = adapter._inject_key(probe, UP_KEY, "press")
            remaining = deadline - time.monotonic()
            eat_marker = adapter._run_exact_marker(probe, eat_bp, eat_addr,
                                                   f"real Part-{old_stage} eat_dot entry", min(8.0, remaining - 0.5))
            eat_state = adapter._low_snapshot(probe)
            eat_player = player_state(adapter, probe)
            dot_at_eat = adapter._phys_read(probe, maze_phys + offsets["target"], 1)[0]
            if (eat_state["stage"] != old_stage or eat_state["stage_pending"] != 0 or
                    eat_state["dots_left"] != 1 or eat_state["bonus_left"] != 0 or
                    (eat_player["cell_x"], eat_player["cell_y"], eat_player["step"], eat_player["direction"]) !=
                    (TARGET_X, TARGET_Y, 0, 0) or dot_at_eat != (target_before | 0x80)):
                raise RuntimeError(f"actual eat_dot entry does not match legal final-dot precondition: {eat_state}, {eat_player}, ${dot_at_eat:02X}")
            release = adapter._inject_key(probe, UP_KEY, "release")
            remaining = deadline - time.monotonic()
            clear_marker = adapter._run_exact_marker(probe, check_bp, check_addr,
                                                     f"real Part-{old_stage} check_stage_clear entry",
                                                     min(4.0, remaining - 0.5))
            clear_state = adapter._low_snapshot(probe)
            clear_player = player_state(adapter, probe)
            dot_after_eat = adapter._phys_read(probe, maze_phys + offsets["target"], 1)[0]
            if (clear_state["stage"] != old_stage or clear_state["stage_pending"] != 0 or
                    clear_state["dots_left"] != 0 or clear_state["bonus_left"] != 0 or
                    dot_after_eat != (target_before & 0x7F) or
                    (clear_player["cell_x"], clear_player["cell_y"]) != (TARGET_X, TARGET_Y)):
                raise RuntimeError(f"actual eat_dot did not clear the final dot before stage clear: {clear_state}, ${dot_after_eat:02X}")
            remaining = deadline - time.monotonic()
            handoff_marker = adapter._run_exact_marker(probe, next_bp, main["next_stage"],
                                                       f"real Part-{old_stage + 1} next_stage",
                                                       min(8.0, remaining - 0.5))
            handoff = adapter._low_snapshot(probe)
            probe.clear_breakpoint(next_bp)
            probe.clear_breakpoint(eat_bp)
            probe.clear_breakpoint(check_bp)
            if (handoff["stage"] != old_stage or handoff["stage_pending"] != 1 or
                    handoff["dots_left"] != 0 or handoff["bonus_left"] != 0):
                raise RuntimeError(f"real Part-{old_stage}-to-Part-{old_stage + 1} handoff differs: {handoff}")
            target_stage = old_stage + 1
            init_rows = observe_stage_init(adapter, probe, identity, target_stage, main, enemy, rate,
                                           runtime_image, enemy_image, rate_helper, deadline,
                                           stage_init_markers)
            transition = {"from_stage": old_stage, "to_stage": target_stage,
                          "fixture_before_up": fixture,
                          "legal_source_and_live_fixture": source_live,
                          "up_press_ack": press, "up_release_ack": release,
                          "eat_dot_marker_pc": f"${eat_marker['pc']:04X}",
                          "eat_dot_entry": {"state": eat_state, "player": eat_player,
                                            "target_maze_byte_before_clear": dot_at_eat},
                          "check_stage_clear_marker_pc": f"${clear_marker['pc']:04X}",
                          "check_stage_clear_entry": {"state": clear_state, "player": clear_player,
                                                       "target_maze_byte_after_clear": dot_after_eat},
                          "next_stage_marker_pc": f"${handoff_marker['pc']:04X}",
                          "handoff_state": handoff,
                          "init_markers": init_rows}
            if target_stage < 10:
                transition["player_entry"] = stage_player_entry(adapter, probe, target_stage,
                                                                normal_game_return, deadline)
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
                        "source_acceptance_basis": {"main_source_sha256": sha(source_main.read_bytes()),
                                                    "candidate_maze_include_sha256": sha(maze_path.read_bytes()),
                                                    "candidate_main_map_sha256": sha(main_map.read_bytes()),
                                                    "symbols": {name: f"${address:04X}" for name, address in symbols.items()},
                                                    "legal_move": {"origin": [START_X, START_Y],
                                                                   "target": [TARGET_X, TARGET_Y],
                                                                   "origin_north_bit_set": bool(nav[START_Y][START_X] & 1),
                                                                   "target_south_bit_set": bool(nav[TARGET_Y][TARGET_X] & 4),
                                                                   "gate_owner_both_zero": True}},
                        "stage_transitions": transitions,
                        "stage_init_observations": stage_init_markers,
                        "part9_true_init_rate_reset": part9,
                        "part10_true_init_rate_reset": part10,
                        "never_wrote_STAGE_or_STAGE_PENDING": True,
                        "writes_only_during_fixture_setup_per_transition": {"DOTS_LEFT": 1,
                                                                              "BONUS_LEFT": 0,
                                                                              "MAZE_STATE_TARGET_DOT_BIT": 1},
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
