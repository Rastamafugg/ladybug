#!/usr/bin/env python3
"""Verify complete-profile input ownership, title animation, and terminal flow."""

from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import verify_bug011_runtime as runtime  # noqa: E402

PRES_MAGIC = 0x00A4
PRES_MODE = 0x00A5
PRES_SCREEN = 0x00A6
PRES_CONTEXT = 0x00A7
PRES_CREDITS = 0x00A8
PRES_EVENT = 0x00A9
PRES_TIMER = 0x00B0
PRES_PREV = 0x00B2
PRES_ACTOR_PHASE = 0x00D3
PRES_HOLD_STATE = 0x00D4
PRES_HOLD_OWNER = 0x00D9
PRES_DEMO_DIR = 0x00DD
JOY_DIR = 0x0005
PLAYER_WANT = 0x000F
PLAYER_MANUAL = 0x0018
STAGE = 0x0024
STAGE_PENDING = 0x0026
DEATH_STATE = 0x004D
PENDING = 0x0091
ACTIVE = 0x0098


def symbols(path: Path) -> dict[str, int]:
    return {
        name: int(value, 16)
        for name, value in re.findall(
            r"^Symbol: (\w+) .* = ([0-9A-Fa-f]+)$",
            path.read_text(encoding="ascii"), re.MULTILINE,
        )
    }


def read_byte(client, address: int) -> int:
    return bytes.fromhex(client.call("read_memory", {
        "addr": address, "length": 1,
    })["data"])[0]


def read_word(client, address: int) -> int:
    data = bytes.fromhex(client.call("read_memory", {
        "addr": address, "length": 2,
    })["data"])
    return int.from_bytes(data, "big")


def write_byte(client, address: int, value: int) -> None:
    client.call("write_memory", {"addr": address, "data": f"{value:02x}"})


def write_word(client, address: int, value: int) -> None:
    client.call("write_memory", {
        "addr": address, "data": value.to_bytes(2, "big").hex(),
    })


def check_source() -> None:
    main = (ROOT / "src/main.s").read_text(encoding="utf-8")
    presentation = (ROOT / "src/presentation_runtime.s").read_text(encoding="utf-8")
    scan = presentation[presentation.index("\nscan_keys\n"):presentation.index("\ndraw_actor_overlay\n")]
    if "lda     PIA_DA" not in scan or "anda    #$7F" not in scan:
        raise SystemExit("source: PA7 is not masked before keyboard-edge storage")
    if "cmpa    #MODE_DEMO\n        beq     main_demo_input_owned" not in main:
        raise SystemExit("source: demo input gate is missing")
    if "cmpa    #MODE_DEMO\n        bne     main_render\n        lbsr    next_stage" not in main:
        raise SystemExit("source: live stage transition ownership is missing")
    if "PRES_CONTEXT_NEXT_STAGE equ 2" not in presentation:
        raise SystemExit("source: next-stage context marker is missing")
    if "clr     PRES_CONTEXT\nstart_screen_context_ready" not in presentation:
        raise SystemExit("source: complete attract context reset is missing")
    if "ifne    ATTRACT_OVERLAY_ENABLED" not in presentation:
        raise SystemExit("source: complete title overlay guard is missing")
    ready = presentation[presentation.index("\npft_ready\n"):presentation.index("\npft_mode\n")]
    if "anda    #$06" not in ready or "lbsr    add_credit" not in ready:
        raise SystemExit("source: credit-gated high-score entry is missing")


def boot(monitor, binary: Path, rom: Path, syms: dict[str, int]):
    process, client = runtime.launch_fast(monitor, binary, rom)
    entry_id = monitor.setup(client, [syms["presentation_flow_tick"]])[0]
    hit = client.run_to_breakpoint(30)
    if hit.get("pc") != syms["presentation_flow_tick"]:
        client.close()
        monitor.stop(process)
        raise SystemExit(f"phase=boot marker=presentation_flow_tick failure={hit}")
    monitor.clear(client, [entry_id])
    dispatch_id = monitor.setup(client, [syms["pft_dispatch"]])[0]
    hit = client.run_to_breakpoint(30)
    if hit.get("pc") != syms["pft_dispatch"]:
        client.close()
        monitor.stop(process)
        raise SystemExit(f"phase=boot marker=pft_dispatch failure={hit}")
    monitor.clear(client, [dispatch_id])
    write_byte(client, PRES_MAGIC, 0xA5)
    for offset in range(3):
        write_byte(client, PRES_PREV + offset, 0x7F)
    write_byte(client, PRES_HOLD_STATE, 0)
    write_byte(client, PRES_HOLD_OWNER, 0)
    return process, client


def title_case(monitor, binary: Path, rom: Path, syms: dict[str, int]) -> None:
    process, client = runtime.launch_fast(monitor, binary, rom)
    try:
        bp = monitor.setup(client, [syms["attract_tick"]])[0]
        phases: list[int] = []
        for _ in range(16):
            hit = client.run_to_breakpoint(30)
            if hit.get("pc") != syms["attract_tick"]:
                raise SystemExit(f"phase=title marker=attract_tick failure={hit}")
            phases.append(read_byte(client, PRES_ACTOR_PHASE))
        monitor.clear(client, [bp])
        if phases[0] == 0xFF or len(set(phases)) < 2:
            raise SystemExit(f"phase=title marker=actor-phase failure=phases={phases}")
        print(f"title: actor phases {phases[0]}->{phases[-1]}")
    finally:
        client.close()
        monitor.stop(process)


def stage_case(monitor, binary: Path, rom: Path, syms: dict[str, int]) -> None:
    process, client = boot(monitor, binary, rom, syms)
    ids: list[int] = []
    try:
        for address, value in ((PRES_MODE, 0), (PRES_CONTEXT, 1),
                               (PRES_EVENT, 0), (DEATH_STATE, 0),
                               (PENDING, 0), (ACTIVE, 0), (STAGE, 1),
                               (STAGE_PENDING, 1)):
            write_byte(client, address, value)
        start_id = monitor.setup(client, [syms["start_screen"]])[0]
        ids.append(start_id)
        hit = client.run_to_breakpoint(30)
        if hit.get("pc") != syms["start_screen"]:
            raise SystemExit(f"phase=stage-clear marker=start_screen failure={hit}")
        requested = int(client.call("read_registers")["a"])
        stage = read_byte(client, STAGE)
        pending = read_byte(client, STAGE_PENDING)
        context = read_byte(client, PRES_CONTEXT)
        if (requested, stage, pending, context) != (2, 2, 0, 2):
            raise SystemExit(
                "phase=stage-clear marker=part-2-request "
                f"failure=map={requested} stage={stage} pending={pending} context={context}"
            )
        monitor.clear(client, ids)
        ids.clear()
        level_id = monitor.setup(client, [syms["level_tick"]])[0]
        ids.append(level_id)
        hit = client.run_to_breakpoint(30)
        if hit.get("pc") != syms["level_tick"]:
            raise SystemExit(f"phase=stage-clear marker=level_tick failure={hit}")
        if read_byte(client, STAGE) != 2 or read_byte(client, PRES_CONTEXT) != 2:
            raise SystemExit(
                "phase=stage-clear marker=stage-preservation "
                f"failure=stage={read_byte(client, STAGE)} context={read_byte(client, PRES_CONTEXT)}"
            )
        monitor.clear(client, ids)
        ids.clear()
        post_id = monitor.setup(client, [syms["main_after_timers"]])[0]
        ids.append(post_id)
        hit = client.run_to_breakpoint(30)
        if hit.get("pc") != syms["main_after_timers"]:
            raise SystemExit(f"phase=stage-clear marker=post-level-main failure={hit}")
        if read_byte(client, STAGE) != 2 or read_byte(client, PRES_MODE) != 0:
            raise SystemExit(
                "phase=stage-clear marker=live-part-2-state "
                f"failure=stage={read_byte(client, STAGE)} mode={read_byte(client, PRES_MODE)}"
            )
        print("stage-clear: Part 2 reached level start and preserved live state")
    finally:
        if ids:
            monitor.clear(client, ids)
        client.close()
        monitor.stop(process)


def repeated_demo_case(monitor, binary: Path, rom: Path, syms: dict[str, int]) -> None:
    process, client = boot(monitor, binary, rom, syms)
    ids: list[int] = []
    try:
        for address, value in ((PRES_MODE, 0), (PRES_CONTEXT, 1),
                               (PRES_EVENT, 0), (DEATH_STATE, 4)):
            write_byte(client, address, value)
        entry_id = monitor.setup(client, [syms["presentation_flow_tick"]])[0]
        ids.append(entry_id)
        hit = client.run_to_breakpoint(30)
        if hit.get("pc") != syms["presentation_flow_tick"]:
            raise SystemExit(f"phase=repeat-demo marker=presentation_flow_tick failure={hit}")
        monitor.clear(client, ids)
        ids.clear()
        load_id = monitor.setup(client, [syms["load_done"]])[0]
        ids.append(load_id)
        hit = client.run_to_breakpoint(30)
        if hit.get("pc") != syms["load_done"]:
            raise SystemExit(f"phase=repeat-demo marker=load_done failure={hit}")
        if read_byte(client, PRES_CONTEXT) != 0:
            raise SystemExit(
                f"phase=repeat-demo marker=attract-context-reset failure=context={read_byte(client, PRES_CONTEXT)}"
            )
        monitor.clear(client, ids)
        ids.clear()
        for address, value in ((PRES_MODE, 6), (PRES_CONTEXT, 0),
                               (PRES_EVENT, 0), (DEATH_STATE, 0),
                               (PENDING, 0), (ACTIVE, 0)):
            write_byte(client, address, value)
        write_word(client, PRES_TIMER, 180)
        level_id = monitor.setup(client, [syms["level_tick"]])[0]
        ids.append(level_id)
        hit = client.run_to_breakpoint(30)
        if hit.get("pc") != syms["level_tick"]:
            raise SystemExit(f"phase=repeat-demo marker=level_tick failure={hit}")
        monitor.clear(client, ids)
        ids.clear()
        tick_id = monitor.setup(client, [syms["main_after_timers"]])[0]
        ids.append(tick_id)
        sample = None
        for _ in range(48):
            hit = client.run_to_breakpoint(10)
            if hit.get("pc") != syms["main_after_timers"]:
                raise SystemExit(f"phase=repeat-demo marker=main_after_timers failure={hit}")
            direction = read_byte(client, PRES_DEMO_DIR)
            if read_byte(client, PRES_MODE) == 4 and direction != 0xFF:
                sample = (direction, read_byte(client, JOY_DIR),
                          read_byte(client, PLAYER_WANT))
                break
        if sample is None or sample[1] != sample[0] or sample[2] != sample[0]:
            raise SystemExit(f"phase=repeat-demo marker=route-owner failure=sample={sample}")
        print(f"repeat-demo: attract reset context and re-entered autonomous route={sample[0]}")
    finally:
        if ids:
            monitor.clear(client, ids)
        client.close()
        monitor.stop(process)


def demo_case(monitor, binary: Path, rom: Path, syms: dict[str, int]) -> None:
    process, client = boot(monitor, binary, rom, syms)
    ids: list[int] = []
    try:
        for address, value in ((PRES_MODE, 6), (PRES_CONTEXT, 0),
                               (PRES_EVENT, 0), (DEATH_STATE, 0),
                               (PENDING, 0), (ACTIVE, 0)):
            write_byte(client, address, value)
        write_word(client, PRES_TIMER, 180)
        if read_byte(client, PRES_MODE) != 6:
            raise SystemExit(f"phase=demo-setup marker=mode-write failure=mode={read_byte(client, PRES_MODE)}")
        entry_id = monitor.setup(client, [syms["presentation_flow_tick"]])[0]
        hit = client.run_to_breakpoint(30)
        if hit.get("pc") != syms["presentation_flow_tick"]:
            raise SystemExit(f"phase=demo-setup marker=presentation_flow_tick failure={hit}")
        monitor.clear(client, [entry_id])
        level_id = monitor.setup(client, [syms["level_tick"]])[0]
        ids.append(level_id)
        hit = client.run_to_breakpoint(30)
        if hit.get("pc") != syms["level_tick"]:
            raise SystemExit(f"phase=demo-setup marker=level_tick failure={hit}")
        monitor.clear(client, ids)
        ids.clear()
        tick_id = monitor.setup(client, [syms["main_after_timers"]])[0]
        ids.append(tick_id)
        sample = None
        for _ in range(48):
            hit = client.run_to_breakpoint(10)
            if hit.get("pc") != syms["main_after_timers"]:
                raise SystemExit(f"phase=demo marker=main_after_timers failure={hit}")
            direction = read_byte(client, PRES_DEMO_DIR)
            if read_byte(client, PRES_MODE) == 4 and direction != 0xFF:
                sample = (direction, read_byte(client, JOY_DIR),
                          read_byte(client, PLAYER_WANT),
                          read_byte(client, PLAYER_MANUAL))
                break
        if sample is None or sample[1] != sample[0] or sample[2] != sample[0]:
            raise SystemExit(f"phase=demo marker=route-owner failure=sample={sample}")
        print(f"demo: autonomous direction={sample[0]} joy={sample[1]} want={sample[2]} manual={sample[3]}")
    finally:
        if ids:
            monitor.clear(client, ids)
        client.close()
        monitor.stop(process)


def gameover_case(monitor, binary: Path, rom: Path, syms: dict[str, int]) -> None:
    process, client = boot(monitor, binary, rom, syms)
    try:
        write_byte(client, PRES_MODE, 0)
        write_byte(client, PRES_CONTEXT, 1)
        write_byte(client, PRES_EVENT, 0)
        write_byte(client, DEATH_STATE, 4)
        entry_bp = monitor.setup(client, [syms["presentation_flow_tick"]])[0]
        hit = client.run_to_breakpoint(30)
        if hit.get("pc") != syms["presentation_flow_tick"]:
            raise SystemExit(f"phase=game-over marker=presentation_flow_tick failure={hit}")
        monitor.clear(client, [entry_bp])
        bp = monitor.setup(client, [syms["start_screen"]])[0]
        hit = client.run_to_breakpoint(30)
        if hit.get("pc") != syms["start_screen"]:
            raise SystemExit(f"phase=game-over marker=start_screen failure={hit}")
        requested = int(client.call("read_registers")["a"])
        if requested != 0:
            raise SystemExit(f"phase=game-over marker=attract-map failure=map={requested}")
        monitor.clear(client, [bp])
        print("game-over: complete profile returned to attract")
    finally:
        client.close()
        monitor.stop(process)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xroar", type=Path, required=True)
    parser.add_argument("--rom", type=Path, default=ROOT / "build/ladybug.rom")
    parser.add_argument("--scenario", choices=("all", "title", "stage", "demo", "repeat-demo", "gameover"), default="all")
    args = parser.parse_args()
    check_source()
    syms = symbols(ROOT / "build/ladybug-presentation-runtime.map")
    syms.update(symbols(ROOT / "build/ladybug.map"))
    monitor = runtime.load_monitor()
    if args.scenario in ("all", "title"):
        title_case(monitor, args.xroar, args.rom, syms)
    if args.scenario in ("all", "stage"):
        stage_case(monitor, args.xroar, args.rom, syms)
    if args.scenario in ("all", "demo"):
        demo_case(monitor, args.xroar, args.rom, syms)
    if args.scenario in ("all", "repeat-demo"):
        repeated_demo_case(monitor, args.xroar, args.rom, syms)
    if args.scenario in ("all", "gameover"):
        gameover_case(monitor, args.xroar, args.rom, syms)
    print("BUG-015/022 complete runtime: pass")


if __name__ == "__main__":
    main()
