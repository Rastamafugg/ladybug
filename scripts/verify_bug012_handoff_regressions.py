#!/usr/bin/env python3
"""Verify BUG-012 owner-preserving level-start-to-maze handoff in XRoar."""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MONITOR_INPUT = ROOT / "scripts/verify_bug009_monitor_input.py"
MODULE_MAP = ROOT / "build/ladybug-presentation-runtime.map"
MAIN_MAP = ROOT / "build/ladybug.map"
ENEMY_MAP = ROOT / "build/ladybug-enemy-runtime.map"
MODULE = ROOT / "build/ladybug-presentation-runtime.bin"
AUXILIARY = ROOT / "build/ladybug-instruction-runtime.bin"
RUNTIME = ROOT / "build/ladybug-runtime.rom"
LAYOUT = ROOT / "build/ladybug-sparse-layout.json"
MAIN_SOURCE = ROOT / "src/main.s"
PRESENTATION_SOURCE = ROOT / "src/presentation_runtime.s"

FRAMES = 0x0002
PRES_MODE = 0x00A5
PRES_TIMER = 0x00B0
PRES_ROUTE = 0x00B8
RENDER_FLAGS = 0x007F
FB_FRONT = 0x008F
FB_BACK = 0x0090
FB_PENDING = 0x0091
FB_COMMIT_SEQ = 0x0092
FB_SIM_SEQ = 0x0094
FB_MISSED_COMMIT = 0x0096
FB_ACTIVE = 0x0098
FB_WRITE_FRONT_FAULT = 0x0099
FB_META_A = 0xA900
FB_META_BYTES = 0x0200
GIME_VOFF1 = 0xFF9D
FB_BYTES = 0x7800
PAGE_BYTES = 0x2000
FB_A_PAGE = 0x30
FB_B_PAGE = 0x2C
RF_STAGE = 0x40
MODE_LEVEL = 6


def load_monitor():
    spec = importlib.util.spec_from_file_location("bug009_monitor", MONITOR_INPUT)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load monitor client")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def symbols(path: Path) -> dict[str, int]:
    return {
        name: int(value, 16)
        for name, value in re.findall(
            r"^Symbol: (\w+) .* = ([0-9A-Fa-f]+)$",
            path.read_text(encoding="ascii"), re.MULTILINE,
        )
    }


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_bytes(client, address: int, length: int) -> bytes:
    result = client.call("read_memory", {"addr": address, "length": length})
    return bytes.fromhex(result["data"])


def read_physical(client, address: int, length: int) -> bytes:
    result = client.call("read_memory", {
        "space": "physical", "addr": address, "length": length,
    })
    return bytes.fromhex(result["data"])


def write_physical(client, address: int, data: bytes) -> None:
    client.call("write_memory", {
        "space": "physical", "addr": address, "data": data.hex(),
    })


def read_byte(client, address: int) -> int:
    return read_bytes(client, address, 1)[0]


def read_word(client, address: int) -> int:
    return int.from_bytes(read_bytes(client, address, 2), "big")


def write_byte(client, address: int, value: int) -> None:
    client.call("write_memory", {"addr": address, "data": f"{value & 0xFF:02x}"})


def write_zeroes(client, address: int, length: int) -> None:
    client.call("write_memory", {"addr": address, "data": "00" * length})


def framebuffer(client, owner: int) -> bytes:
    page = FB_A_PAGE if owner == 0 else FB_B_PAGE
    return read_physical(client, page * PAGE_BYTES, FB_BYTES)


def gime_voff1(client) -> int:
    return int(client.call("read_gime_state")["registers"]["FF9D"])


def state(client, phase: str) -> dict[str, object]:
    front = read_byte(client, FB_FRONT)
    if front not in (0, 1):
        raise RuntimeError(f"{phase}: invalid FRONT owner {front}")
    return {
        "phase": phase,
        "frames": read_word(client, FRAMES),
        "front": front,
        "back": read_byte(client, FB_BACK),
        "pending": read_byte(client, FB_PENDING),
        "active": read_byte(client, FB_ACTIVE),
        "commit_sequence": read_word(client, FB_COMMIT_SEQ),
        "simulation_sequence": read_word(client, FB_SIM_SEQ),
        "missed_commits": read_word(client, FB_MISSED_COMMIT),
        "front_write_faults": read_byte(client, FB_WRITE_FRONT_FAULT),
        "gime_voff1": gime_voff1(client),
        "physical_front_sha256": digest(framebuffer(client, front)),
    }


def validate_identity(identities: dict[str, dict[str, str]]) -> None:
    for name, values in identities.items():
        if len(set(values.values())) != 1:
            raise RuntimeError(f"artifact identity mismatch for {name}: {values}")


def artifact_identities(client, main: dict[str, int]) -> dict[str, dict[str, str]]:
    layout = json.loads(LAYOUT.read_text(encoding="ascii"))
    final_rom = (ROOT / "build/ladybug.rom").read_bytes()
    runtime = RUNTIME.read_bytes()
    main_start = main["mainloop"]
    main_end = main["init_game_state"]
    authored_main = runtime[main_start - 0xC000:main_end - 0xC000]
    staged_main = final_rom[0x4000 + main_start - 0xC000:
                            0x4000 + main_end - 0xC000]
    module = MODULE.read_bytes()
    module_segment = next(
        segment for segment in layout["gmc"]["segments"]
        if segment["target"] == "presentation_module"
    )
    module_offset = (module_segment["bank"] * 0x4000
                     + module_segment["source_offset"])
    staged_module = final_rom[module_offset:module_offset + module_segment["count"]]
    auxiliary = AUXILIARY.read_bytes()
    aux_info = layout["instruction_runtime"]
    staged_auxiliary = read_physical(
        client,
        aux_info["stage_page"] * PAGE_BYTES
        + aux_info["stage_address"] - 0xA000,
        len(auxiliary),
    )
    identities = {
        "resident_mainloop": {
            "authored": digest(authored_main),
            "staged": digest(staged_main),
            "live": digest(read_bytes(client, main_start, len(authored_main))),
        },
        "presentation_module": {
            "authored": digest(module),
            "staged": digest(staged_module),
            "live": digest(read_bytes(client, 0x1900, len(module))),
        },
        "demo_auxiliary": {
            "authored": digest(auxiliary),
            "staged": digest(staged_auxiliary),
            "live": digest(read_bytes(client, 0x0300, len(auxiliary))),
        },
    }
    validate_identity(identities)
    return identities


def static_contract(main_text: str, presentation_text: str) -> None:
    mainloop = main_text[main_text.index("\nmainloop\n"):
                         main_text.index("\ninit_game_state\n")]
    call = mainloop.index("jsr     $1900")
    active = mainloop.index("sta     FB_RENDER_ACTIVE")
    mutation = mainloop.index("lbsr    finish_gate_animation")
    if not call < active < mutation:
        raise ValueError("ACTIVE does not begin at the gameplay mutation boundary")
    if "FB_RENDER_ACTIVE" in mainloop[mainloop.index("sta     LAST_FRAME"):call]:
        raise ValueError("presentation dispatch remains render-active")
    level = presentation_text[presentation_text.index("\nlevel_tick\n"):
                              presentation_text.index("\ndemo_tick\n")]
    for fragment in (
        "tst     PENDING", "tst     ACTIVE", "lbsr    gameplay_reentry",
        "lda     BACK_ID", "nega", "adda    #$30",
        "ldx     #PAR1", "ldb     #4", "sta     ,x+",
        "ldx     #FB_META_A", "cmpx    #FB_META_END", "std     ,x++",
        "inc     FB_INIT_STATE",
    ):
        if fragment not in level:
            raise ValueError(f"presentation re-entry contract missing {fragment!r}")
    if "jsr     $081B" in level:
        raise ValueError("visible re-entry still calls the cold fixed-owner ABI")
    if "clr     ACTIVE" in presentation_text:
        raise ValueError("presentation still releases gameplay-owned ACTIVE state")
    if "sta     BACK_ID" in level or "clr     BACK_ID" in level:
        raise ValueError("visible re-entry relabels logical owners")
    if level.index("tst     PENDING") > level.index("tst     PRES_CONTEXT"):
        raise ValueError("idle gate follows gameplay selection")
    init_start = level.index("\ninit_gameplay\n")
    init_end = level.index("\n        ifeq", init_start)
    init = level[init_start:init_end]
    if not init.index("lbsr    gameplay_reentry") < init.index("jsr     PRES_MAIN_INIT"):
        raise ValueError("BACK and PAR5 are not selected before shared initialization")
    if "sta     PENDING" in init:
        raise ValueError("visible re-entry publishes before complete composition")


def static_mutation_tests(main_text: str, presentation_text: str) -> list[str]:
    mutations = {
        "active_before_dispatch": (
            main_text.replace(
                "        jsr     $1900\n        bne     mainloop\n        lda     #1\n        sta     FB_RENDER_ACTIVE",
                "        lda     #1\n        sta     FB_RENDER_ACTIVE\n        jsr     $1900\n        bne     mainloop", 1,
            ), presentation_text,
        ),
        "omit_second_ledger": (
            main_text, presentation_text.replace(
                "cmpx    #FB_META_END", "cmpx    #FB_META_A+256", 1
            ),
        ),
        "fixed_owner_relabel": (
            main_text, presentation_text.replace(
                "lbsr    gameplay_reentry",
                "clr     BACK_ID\n        lbsr    gameplay_reentry", 1,
            ),
        ),
        "early_pending_publish": (
            main_text, presentation_text.replace(
                "lbsr    gameplay_reentry",
                "sta     PENDING\n        lbsr    gameplay_reentry", 1,
            ),
        ),
    }
    rejected = []
    for name, (mutated_main, mutated_presentation) in mutations.items():
        try:
            static_contract(mutated_main, mutated_presentation)
        except (ValueError, IndexError):
            rejected.append(name)
        else:
            raise RuntimeError(f"mutation was not rejected: {name}")
    return rejected


def configure_crossover(client, initial_owner: int) -> None:
    front = read_byte(client, FB_FRONT)
    level_start = framebuffer(client, front)
    write_physical(client, FB_A_PAGE * PAGE_BYTES, level_start)
    write_physical(client, FB_B_PAGE * PAGE_BYTES, level_start)
    if framebuffer(client, 0) != level_start or framebuffer(client, 1) != level_start:
        raise RuntimeError("controlled crossover lacks identical level-start A/B pixels")
    write_zeroes(client, 0x007F, 0x10)
    write_zeroes(client, FB_PENDING, 9)
    write_zeroes(client, FB_META_A, FB_META_BYTES)
    write_byte(client, FB_FRONT, initial_owner)
    write_byte(client, FB_BACK, 1 - initial_owner)
    write_byte(client, GIME_VOFF1, 0xC0 if initial_owner == 0 else 0xB0)


def validate_trace(trace: list[dict[str, object]], level_hash: str) -> int:
    if len(trace) < 2:
        raise RuntimeError("missing Vbord coverage")
    changed = [i for i, sample in enumerate(trace)
               if sample["physical_front_sha256"] != level_hash]
    if not changed or changed[0] == 0:
        raise RuntimeError("level-start-to-maze publication boundary missing")
    first_maze = changed[0]
    for previous, current in zip(trace, trace[1:]):
        if ((int(current["frames"]) - int(previous["frames"])) & 0xFFFF) != 1:
            raise RuntimeError("missing Vbord sample")
    for sample in trace[:first_maze]:
        if sample["physical_front_sha256"] != level_hash:
            raise RuntimeError("intermediate composition reached physical FRONT")
    for sample in trace:
        if sample["front_write_faults"] != 0:
            raise RuntimeError("FRONT write fault observed")
        expected_voff = 0xC0 if sample["front"] == 0 else 0xB0
        if sample["gime_voff1"] != expected_voff:
            raise RuntimeError(f"logical/physical owner mismatch: {sample}")
    commit_delta = ((int(trace[first_maze]["commit_sequence"])
                    - int(trace[0]["commit_sequence"])) & 0xFFFF)
    if commit_delta != 1:
        raise RuntimeError(
            "maze did not appear on exactly one publication: "
            f"delta={commit_delta} first_maze={first_maze} "
            f"baseline={trace[0]} maze={trace[first_maze]}"
        )
    return first_maze


def trace_mutation_tests(trace: list[dict[str, object]], level_hash: str,
                         first_maze: int) -> list[str]:
    intermediate = copy.deepcopy(trace)
    intermediate[max(1, first_maze - 1)]["physical_front_sha256"] = "00" * 32
    missing = copy.deepcopy(trace)
    if len(missing) > 2:
        del missing[1]
    else:
        missing[1]["frames"] = int(missing[0]["frames"]) + 2
    rejected = []
    for name, mutation in (("intermediate_front_hash", intermediate),
                           ("missing_vbord", missing)):
        try:
            validate_trace(mutation, level_hash)
        except RuntimeError:
            rejected.append(name)
        else:
            raise RuntimeError(f"trace mutation was not rejected: {name}")
    return rejected


def run_handoff(monitor, args, module: dict[str, int], main: dict[str, int],
                enemy: dict[str, int]) -> dict[str, object]:
    process, client = monitor.launch(args.xroar, args.rom, monitor.free_port())
    ids: list[int] = []
    try:
        start_id, init_id = monitor.setup(
            client, [module["start_screen"], module["init_gameplay"]]
        )
        ids.extend((start_id, init_id))
        requests = []
        identities = None
        for _ in range(16):
            hit = client.run_to_breakpoint(args.timeout)
            if hit.get("pc") == module["start_screen"]:
                if identities is None:
                    identities = artifact_identities(client, main)
                requests.append(int(client.call("read_registers")["a"]))
                continue
            if hit.get("pc") == module["init_gameplay"]:
                break
            raise RuntimeError(f"unexpected navigation marker: {hit}")
        else:
            raise RuntimeError("gameplay initialization boundary was not observed")
        monitor.clear(client, ids)
        ids.clear()
        if not requests or requests[0] != 0 or requests[-1] != 2 or 1 in requests:
            raise RuntimeError(f"natural attract/level-start sequence missing: {requests}")
        if read_byte(client, FB_ACTIVE) != 0:
            raise RuntimeError("presentation callback entered gameplay initialization ACTIVE")
        if args.initial_owner is not None:
            configure_crossover(client, args.initial_owner)
        baseline = state(client, "last_complete_level_start")
        level_hash = str(baseline["physical_front_sha256"])
        level_pixels = framebuffer(client, int(baseline["front"]))
        trace = [baseline]
        client.call("step_instruction", {"n": 1})
        hit = client.call(
            "wait_for_stop", {"timeout_ms": int(args.timeout * 1000)},
            timeout=args.timeout + 1,
        )
        if hit.get("reason") != "step" or hit.get("pc") != module["gameplay_reentry"]:
            raise RuntimeError(f"presentation re-entry step boundary missing: {hit}")
        helper_seen = True
        if read_byte(client, FB_ACTIVE) != 0:
            raise RuntimeError("presentation re-entry is incorrectly ACTIVE")
        gameplay_id, vb_id = monitor.setup(
            client, [main["main_game_tick"], enemy["fbiq_done"]]
        )
        ids.extend((gameplay_id, vb_id))
        render_id = None
        gameplay_seen = render_seen = ledgers_cleared = False
        for _ in range(96):
            hit = client.run_to_breakpoint(args.timeout)
            pc = hit.get("pc")
            if pc == main["main_game_tick"]:
                gameplay_seen = True
                if read_byte(client, FB_ACTIVE) != 1:
                    raise RuntimeError("gameplay mutation began without ACTIVE")
                monitor.clear(client, [gameplay_id])
                ids.remove(gameplay_id)
                render_id = monitor.setup(client, [main["render_frame"]])[0]
                ids.append(render_id)
                continue
            if render_id is not None and pc == main["render_frame"]:
                render_seen = True
                ledgers_cleared = not any(read_bytes(client, FB_META_A, FB_META_BYTES))
                if not ledgers_cleared:
                    raise RuntimeError("both ownership ledgers were not invalidated")
                if not read_byte(client, RENDER_FLAGS) & RF_STAGE:
                    raise RuntimeError("first gameplay render lacks RF_STAGE")
                monitor.clear(client, [render_id])
                ids.remove(render_id)
                render_id = None
                continue
            if pc != enemy["fbiq_done"]:
                raise RuntimeError(f"unexpected handoff marker: {hit}")
            sample = state(client, "stage_composition_vbord")
            trace.append(sample)
            if sample["physical_front_sha256"] != level_hash:
                current_pixels = framebuffer(client, int(sample["front"]))
                changed_offsets = [
                    index for index, (before, after) in enumerate(
                        zip(level_pixels, current_pixels)
                    ) if before != after
                ]
                sample["difference_bytes"] = len(changed_offsets)
                sample["first_difference_offsets"] = changed_offsets[:32]
                break
        else:
            raise RuntimeError("first maze commit was not observed within 96 Vbords")
        first_maze = validate_trace(trace, level_hash)
        maze_hash = str(trace[first_maze]["physical_front_sha256"])
        if args.expected_first_maze_sha256 and maze_hash != args.expected_first_maze_sha256:
            raise RuntimeError(
                f"first maze hash {maze_hash} differs from oracle "
                f"{args.expected_first_maze_sha256}"
            )
        if not (helper_seen and gameplay_seen and render_seen and ledgers_cleared):
            raise RuntimeError("required ownership boundaries were not all observed")
        return {
            "screen_requests": requests,
            "identities": identities,
            "initial_owner": args.initial_owner,
            "level_start_sha256": level_hash,
            "first_maze_sha256": maze_hash,
            "first_maze_trace_index": first_maze,
            "composition_vbords": first_maze,
            "commit_delta": ((int(trace[first_maze]["commit_sequence"])
                              - int(trace[0]["commit_sequence"])) & 0xFFFF),
            "missed_commit_delta": ((int(trace[first_maze]["missed_commits"])
                                     - int(trace[0]["missed_commits"])) & 0xFFFF),
            "route_index_at_commit": read_byte(client, PRES_ROUTE),
            "ledgers_cleared_before_render": ledgers_cleared,
            "trace": trace,
            "trace_mutations_rejected": trace_mutation_tests(
                trace, level_hash, first_maze
            ),
        }
    finally:
        if ids:
            try:
                monitor.clear(client, ids)
            except Exception:
                pass
        client.close()
        monitor.stop(process)
        process.wait(timeout=2)


def run_idle_gate(monitor, args, module: dict[str, int], main: dict[str, int],
                  address: int, name: str) -> dict[str, object]:
    process, client = monitor.launch(args.xroar, args.rom, monitor.free_port())
    ids: list[int] = []
    try:
        start_id, level_id = monitor.setup(
            client, [module["start_screen"], module["level_tick"]]
        )
        ids.extend((start_id, level_id))
        for _ in range(16):
            hit = client.run_to_breakpoint(args.timeout)
            if hit.get("pc") == module["start_screen"]:
                continue
            if hit.get("pc") == module["level_tick"]:
                break
            raise RuntimeError(f"{name}: unexpected navigation marker {hit}")
        else:
            raise RuntimeError(f"{name}: level deadline boundary not observed")
        if read_byte(client, FB_ACTIVE) != 0:
            raise RuntimeError(f"{name}: presentation callback entry is ACTIVE")
        write_byte(client, PRES_TIMER, 0)
        write_byte(client, PRES_TIMER + 1, 179)
        write_byte(client, address, 1)
        monitor.clear(client, ids)
        ids.clear()
        for _ in range(32):
            client.call("step_instruction", {"n": 1})
            hit = client.call(
                "wait_for_stop", {"timeout_ms": int(args.timeout * 1000)},
                timeout=args.timeout + 1,
            )
            pc = hit.get("pc")
            if pc == module["init_gameplay"]:
                raise RuntimeError(f"{name}: gameplay initialized while busy: {hit}")
            if pc == main["mainloop"]:
                break
        else:
            raise RuntimeError(f"{name}: held callback did not return to mainloop")
        held = {
            "mode": read_byte(client, PRES_MODE),
            "timer": read_word(client, PRES_TIMER),
            "pending": read_byte(client, FB_PENDING),
            "active": read_byte(client, FB_ACTIVE),
        }
        if held["mode"] != MODE_LEVEL or held[name] != 1:
            raise RuntimeError(f"{name}: busy state was not retained: {held}")
        write_byte(client, address, 0)
        init_id = monitor.setup(client, [module["init_gameplay"]])[0]
        ids.append(init_id)
        hit = client.run_to_breakpoint(args.timeout)
        if hit.get("pc") != module["init_gameplay"]:
            raise RuntimeError(f"{name}: gameplay did not resume after idle: {hit}")
        return {
            "scenario": f"forced_{name}_at_level_deadline",
            "success_marker": f"init_gameplay=${module['init_gameplay']:04X}",
            "deadline_seconds": args.timeout,
            "timeout_meaning": "the held callback or resumed gameplay boundary was not observed",
            "held": held,
            "resumed": {
                "mode": read_byte(client, PRES_MODE),
                "pending": read_byte(client, FB_PENDING),
                "active": read_byte(client, FB_ACTIVE),
            },
        }
    finally:
        if ids:
            try:
                monitor.clear(client, ids)
            except Exception:
                pass
        client.close()
        monitor.stop(process)
        process.wait(timeout=2)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xroar", type=Path, required=True)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--initial-owner", type=int, choices=(0, 1))
    parser.add_argument("--expected-first-maze-sha256")
    args = parser.parse_args()

    main_syms = symbols(MAIN_MAP)
    module_syms = symbols(MODULE_MAP)
    enemy_syms = symbols(ENEMY_MAP)
    main_text = MAIN_SOURCE.read_text(encoding="utf-8")
    presentation_text = PRESENTATION_SOURCE.read_text(encoding="utf-8")
    static_contract(main_text, presentation_text)
    static_rejected = static_mutation_tests(main_text, presentation_text)
    monitor = load_monitor()
    handoff = run_handoff(monitor, args, module_syms, main_syms, enemy_syms)
    pending = run_idle_gate(
        monitor, args, module_syms, main_syms, FB_PENDING, "pending"
    )
    active = run_idle_gate(
        monitor, args, module_syms, main_syms, FB_ACTIVE, "active"
    )
    pending_path = args.output.with_name(args.output.stem + "-rare-pending.json")
    active_path = args.output.with_name(args.output.stem + "-rare-active.json")
    pending_path.write_text(json.dumps(pending, indent=2) + "\n", encoding="ascii")
    active_path.write_text(json.dumps(active, indent=2) + "\n", encoding="ascii")
    evidence = {
        "schema": "ladybug-bug012-handoff-regressions-v2",
        "rom_sha256": digest(args.rom.read_bytes()),
        "phase_deadline_seconds": args.timeout,
        "timeout_meaning": "the named ownership or Vbord boundary was not observed",
        "static_mutations_rejected": static_rejected,
        "handoff": handoff,
        "rare_paths": {
            "pending": pending,
            "active": active,
            "pending_output": str(pending_path),
            "active_output": str(active_path),
        },
        "counter_semantics": (
            "FB_MISSED_COMMIT counts gameplay mutation/render intervals only; "
            "presentation-callback IRQs are excluded by the corrected ACTIVE boundary"
        ),
    }
    args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="ascii")
    print(
        "BUG-012 clean handoff passes: level start remains physical FRONT through "
        f"{handoff['composition_vbords']} Vbords; one complete maze commit; "
        "pending/ACTIVE deadline holds and mutation checks pass"
    )


if __name__ == "__main__":
    main()
