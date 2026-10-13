#!/usr/bin/env python3
"""Bounded, input-only natural BUG-123 level-transition reproduction."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
ROM_SHA = "283084f3571a3bb25cce4452ef79ece11a3ed5b4085e6f3a3931bacfa7f6c0a5"
PINS = {
    "build/ladybug.map": "2f2ab6975570db160ee2412049dc8228cd553fa4652cb0437ff8d638afcab42c",
    "build/ladybug-presentation-runtime.map": "ccb47e9520decbf2e27694f73047e7771d7c6f0aca30c24aab47ff43be486d09",
    "build/ladybug-enemy-runtime.map": "38977a0ea13bbeb01231443966107ac257130757092c23a4f9bfd17059e433f9",
    "build/ladybug-runtime.rom": "16af307da88b0bab6f38bb00be77bdaf0ddd87e7f588cc4b42f84c390a2cf653",
    "build/ladybug-enemy-runtime.rom": "ad6db3b864a0c41427e18db7e6ea90ecd2df1310e70080969c2a3914b6781d50",
    "build/ladybug-presentation-runtime.bin": "2ab84326f49de26172b9e60809671d4904d2fadc00d25aed6a3f6763a6d0463b",
    "build/ladybug-rate-helper.bin": "c90d80a2989e46c05dfeacd20a8a183a065b0348f914b5a876d149aae320d4dc",
    "docs/reference/xroar/src/dkbd.c": "4bf65e9dffa12a6ed555ed985a66d66790257f7cc0cf3cc75dbb31f2e6d64ace",
    "docs/reference/xroar/src/dkbd.h": "84e27da9398e9e0e12942810b94a8163f861d518168dec01ae72fc7e695284ce",
    "assets/arcade/sprites.json": "af2adb1a494b6a641deb38931ee93220b9638ffca4d42e8e37d7d8683945e42d",
}
ACCEPTANCE_ARTIFACTS = set(PINS) | {"build/ladybug.rom", "build/ladybug-rate-helper.map"}
MOVES = ((0, -1), (1, 0), (0, 1), (-1, 0))
ACTION_FOR_DIR = (0, 3, 1, 2)  # N,E,S,W -> live binding slots
NAMES = ("N", "E", "S", "W")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def symbols(path: Path) -> dict[str, int]:
    return {name: int(value, 16) for name, value in re.findall(
        r"^Symbol: (\w+) .* = ([0-9A-Fa-f]+)$", path.read_text(encoding="utf-8"), re.M)}


def pinned_inputs() -> dict[str, str]:
    actual = {}
    for relative, expected in PINS.items():
        data = (ROOT / relative).read_bytes()
        actual[relative] = digest(data)
        if expected and actual[relative] != expected:
            raise RuntimeError(f"pinned artifact changed: {relative} {actual[relative]}")
    rom = digest((ROOT / "build/ladybug.rom").read_bytes())
    if rom != ROM_SHA:
        raise RuntimeError(f"delivery ROM changed: {rom}")
    actual["build/ladybug.rom"] = rom
    return actual


def acceptance_inputs(manifest: Path) -> dict[str, str]:
    expected = json.loads(manifest.read_text(encoding="utf-8"))
    if not isinstance(expected, dict) or set(expected) != ACCEPTANCE_ARTIFACTS:
        raise RuntimeError(f"acceptance manifest must pin exactly: {sorted(ACCEPTANCE_ARTIFACTS)}")
    actual = {}
    for relative, pinned in expected.items():
        actual[relative] = digest((ROOT / relative).read_bytes())
        if (not isinstance(pinned, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", pinned)
                or actual[relative] != pinned.lower()):
            raise RuntimeError(f"invalid or mismatched acceptance SHA-256 before launch: {relative} {actual[relative]}")
    return actual


def dscan_to_matrix(scan: int) -> int:
    """CoCo 3 mapping from dkbd.c; project identity is col*8+row."""
    col, row = scan & 7, (scan >> 3) & 7
    if row != 6:
        row = (row + 4) % 6
    return col * 8 + row


def matrix_to_dscan(matrix: int) -> int:
    matches = [scan for scan in range(64) if dscan_to_matrix(scan) == matrix]
    if not matches:
        raise RuntimeError(f"no DSCAN for project matrix key {matrix}")
    return matches[0]


def self_check(manifest: Path | None = None) -> dict:
    hashes = acceptance_inputs(manifest) if manifest else pinned_inputs()
    expected = [43, 44, 45, 46, 48]
    actual = [matrix_to_dscan(k) for k in (27, 35, 43, 51, 6)]
    if actual != expected or matrix_to_dscan(44) != 5:
        raise RuntimeError(f"DSCAN conversion mismatch: {actual}")
    return {"offline_only": True, "target_writes": 0, "pinned_sha256": hashes,
            "default_binding_dscans": actual, "fixed_coin_dscan": 5,
            "runtime_started": False}


def can_move(maze: dict, states: list[int], x: int, y: int, direction: int) -> bool:
    """Mirror cm_admit_from_test; state mutation models a legal endpoint push."""
    dx, dy = MOVES[direction]
    tx, ty = x + dx, y + dy
    if not (0 <= tx < 24 and 0 <= ty < 24):
        return False
    owner = maze["owner"][ty * 24 + tx]
    if not owner:
        return bool(maze["nav"][ty * 24 + tx] & (4, 8, 1, 2)[direction])
    gi = owner - 1
    gx, gy = maze["gates"][gi]
    state = states[gi]
    if not state & 1:
        if tx == gx and abs(ty - gy) == 1 and direction in (1, 3):
            return True
    elif ty == gy and abs(tx - gx) == 1 and direction in (0, 2):
        return True
    if not state & 1:
        if direction not in (0, 2) or ty != gy or tx == gx:
            return False
        states[gi] = 1 if tx < gx else 3
        return True
    if direction not in (1, 3) or tx != gx or ty == gy:
        return False
    states[gi] = 0 if ty < gy else 2
    return True


def route_first(maze: dict, x: int, y: int, states: list[int], dots: bytes,
                bonus: set[tuple[int, int]],
                blocked: set[tuple[int, int]]) -> tuple[int | None, tuple[int, int] | None]:
    todo = deque([((x, y), None)])
    seen = {(x, y)}
    examined = 0
    while todo:
        (cx, cy), first = todo.popleft()
        examined += 1
        if examined > 12000:
            return None, None
        if dots[cy * 24 + cx] & 0x80 or (cx, cy) in bonus:
            return first, (cx, cy)
        for d, (dx, dy) in enumerate(MOVES):
            nx, ny = cx + dx, cy + dy
            if (nx, ny) in blocked:
                continue
            # Search is location-bounded. Gates are evaluated by the exact
            # admission rules against the latest live state; replan after one
            # center so any actual endpoint rotation becomes authoritative.
            next_states = list(states)
            if not can_move(maze, next_states, cx, cy, d):
                continue
            state = (nx, ny)
            if state not in seen:
                seen.add(state)
                todo.append((state, d if first is None else first))
    return None, None


def run(xroar: Path, output: Path, acceptance_manifest: Path | None = None,
        scenario: str = "level2") -> dict:
    acceptance = acceptance_manifest is not None
    pins = acceptance_inputs(acceptance_manifest) if acceptance else pinned_inputs()
    rom_sha = pins["build/ladybug.rom"] if acceptance else ROM_SHA
    sys.path.insert(0, str(ROOT / "scripts"))
    import verify_bug009_monitor_input as monitor
    from verify_bug011_runtime import launch_fast

    main = symbols(ROOT / "build/ladybug.map")
    pres = symbols(ROOT / "build/ladybug-presentation-runtime.map")
    enemy = symbols(ROOT / "build/ladybug-enemy-runtime.map")
    rate = symbols(ROOT / "build/ladybug-rate-helper.map") if acceptance else {}
    pft, tick = pres["pft_dispatch"], main["player_tick"]
    publish, next_stage = enemy["fbiq_done"], main["next_stage"]
    result = {"rom_sha256": rom_sha, "pinned_sha256": pins, "target_writes": 0,
              "runtime_started": True, "phases": [], "accepted_front": None}
    process = client = None
    bps: list[int] = []
    held_scan: int | None = None
    frames = None
    started = time.monotonic()

    def read(addr: int, size: int, physical: bool = False) -> bytes:
        args = {"addr": addr, "length": size}
        if physical:
            args["space"] = "physical"
        return bytes.fromhex(client.call("read_memory", args, timeout=10)["data"])

    def dp() -> bytes:
        return read(0, 256)

    def entities_now(state: bytes) -> list[dict[str, int]]:
        count = state[0x32]
        if count > 12:
            raise RuntimeError(f"entity count exceeds twelve-record table: {count}")
        raw = read(0xA380, count * 4)
        return [{"x": raw[i * 4], "y": raw[i * 4 + 1],
                 "type": raw[i * 4 + 2], "variant": raw[i * 4 + 3]}
                for i in range(count)]

    def release_direction() -> None:
        nonlocal held_scan
        if held_scan is not None:
            client.call("inject_key", {"key": held_scan, "action": "release"}, timeout=10)
            held_scan = None

    def setpoints(*addresses: int) -> None:
        nonlocal bps
        for ident in bps:
            client.call("clear_breakpoint", {"id": ident}, timeout=10)
        bps = [client.call("set_breakpoint", {"addr": a, "kind": "exec"}, timeout=10)["id"]
               for a in addresses]

    def hit(deadline: float, allowed: set[int] | None = None) -> int:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("phase deadline reached")
        stop = client.run_to_breakpoint(min(10, remaining))
        pc = stop.get("pc")
        if allowed is not None and pc not in allowed:
            raise RuntimeError(f"unexpected breakpoint stop: {stop}")
        return pc

    def phase(name: str, begin: float, extra: dict | None = None) -> None:
        entry = {"name": name, "elapsed_seconds": round(time.monotonic() - begin, 3),
                 "deadline_seconds": 45}
        if extra:
            entry.update(extra)
        result["phases"].append(entry)

    def capture_front(draw_state: bytes, label: str, deadline: float) -> dict:
        nonlocal frames
        back = draw_state[0x90]
        seq = int.from_bytes(draw_state[0x92:0x94], "big")
        setpoints(publish)
        while True:
            hit(deadline, {publish})
            published = dp()
            if (published[0x91] == 0 and published[0x8F] == back
                    and int.from_bytes(published[0x92:0x94], "big") != seq):
                break
        front = published[0x8F]
        page = 0x30 if front == 0 else 0x2C
        captured_frame = read(page * 8192, 0x7800, True)
        output.parent.mkdir(parents=True, exist_ok=True)
        frame_path = output.with_suffix(".front.bin" if label == "initial" else f".{label}.front.bin")
        frame_path.write_bytes(captured_frame)
        if frames is None:
            from build_screen import compile_player_sprites
            frames = compile_player_sprites(ROOT / "assets/arcade/sprites.json")
        frame_index = (draw_state[7] & 3) * 4 + (draw_state[0x4F] & 3)
        sprite = frames[frame_index]
        colors = (0, 12, 5, 2)
        opaque = []
        for sy in range(16):
            for sx in range(16):
                packed = sprite[sy * 4 + sx // 4]
                pen = (packed >> (6 - 2 * (sx & 3))) & 3
                if pen:
                    opaque.append((sx, sy, colors[pen]))
        if not opaque:
            raise RuntimeError(f"compiled player frame has no opaque pixels for {label}")
        def compare(anchor_x: int, anchor_y: int) -> tuple[int, int]:
            matched = 0
            for sx, sy, color in opaque:
                px, py = anchor_x + sx, anchor_y + sy
                if 0 <= px < 320 and 0 <= py < 192:
                    byte = captured_frame[py * 160 + px // 2]
                    actual = (byte >> 4) & 15 if px % 2 == 0 else byte & 15
                    matched += actual == color
            return matched, len(opaque)
        logical = (152 + 8 * (draw_state[9] - 12), 169 + 8 * (draw_state[10] - 22))
        pointer = int.from_bytes(draw_state[11:13], "big") - 0x2000
        ptr_anchor = ((pointer % 160) * 2, pointer // 160) if 0 <= pointer < 0x7800 else (-1, -1)
        pointer_match, logical_match = compare(*ptr_anchor), compare(*logical)
        return {"owner": front, "commit": int.from_bytes(published[0x92:0x94], "big"),
            "back_at_draw": back, "commit_at_draw": seq,
            "player_fb": hex(int.from_bytes(draw_state[11:13], "big")),
            "cell": [draw_state[9], draw_state[10]], "step": draw_state[8],
            "face": draw_state[7], "anim": draw_state[0x4F],
            "frame_index": frame_index, "frame_sha256": digest(captured_frame),
            "frame_file": str(frame_path), "logical_anchor": list(logical),
            "pointer_anchor": list(ptr_anchor),
            "offset_from_logical_pixels": [ptr_anchor[0] - logical[0], ptr_anchor[1] - logical[1]],
            "opaque_pixels": len(opaque), "pointer_opaque_matches": list(pointer_match),
            "logical_opaque_matches": list(logical_match),
            "mask_displacement_confirmed": (pointer_match[0] == len(opaque)
                                              and logical_match[0] < len(opaque))}

    def require_aligned_front(label: str, captured: dict) -> None:
        total = captured["opaque_pixels"]
        if (captured["offset_from_logical_pixels"] != [0, 0]
                or captured["logical_opaque_matches"] != [total, total]):
            raise RuntimeError(f"{label} FRONT missed 0/0 and 100% authored opaque match: {captured}")

    try:
        process, client = launch_fast(monitor, xroar, ROOT / "build/ladybug.rom")
        d0 = started + 45
        setpoints(pft)
        while True:
            hit(d0, {pft})
            if read(0xA4, 5)[:2] == b"\xA5\x02":
                break
        comparisons = {}
        for name, address, rel, n, physical in (
            ("resident", 0xC000, "build/ladybug-runtime.rom", 8192, False),
            ("enemy", 0x0800, "build/ladybug-enemy-runtime.rom", 4091, False),
            ("presentation", 0x1900, "build/ladybug-presentation-runtime.bin", None, False),
            ("rate", 0x34 * 8192 + 0x3B0, "build/ladybug-rate-helper.bin", 191, True),
        ):
            data = (ROOT / rel).read_bytes()
            comparisons[name] = read(address, len(data) if n is None else n, physical) == data[:n]
        if not all(comparisons.values()):
            raise RuntimeError(f"live module qualification failed: {comparisons}")
        result["live_modules_match"] = comparisons
        bindings = list(read(0x0287, 5))
        result["bindings_matrix"] = bindings
        directions = [matrix_to_dscan(k) for k in bindings[:4]]
        enter = matrix_to_dscan(bindings[4])
        result["bindings_dscan"] = {"N": directions[0], "S": directions[1],
                                     "W": directions[2], "E": directions[3], "Enter": enter}
        if acceptance and scenario == "demo":
            demo_begin = time.monotonic()
            demo_deadline = demo_begin + 45
            def demo_pose(cell: list[int]) -> bytes:
                setpoints(main["draw_player"])
                while time.monotonic() < demo_deadline:
                    hit(demo_deadline, {main["draw_player"]})
                    candidate = dp()
                    if (candidate[0xA5] == 4 and candidate[0xA0] == 0
                            and [candidate[9], candidate[10]] == cell and candidate[8] == 0):
                        return candidate
                raise TimeoutError(f"natural demo did not draw aligned cell {cell} within 45 seconds")
            initial_demo = demo_pose([12, 22])
            result["demo_initial_front"] = capture_front(initial_demo, "initial", demo_deadline)
            require_aligned_front("natural demo initial", result["demo_initial_front"])
            moved_demo = demo_pose([12, 21])
            result["demo_moved_front"] = capture_front(moved_demo, "demo-moved", demo_deadline)
            require_aligned_front("natural demo moved", result["demo_moved_front"])
            phase("natural attract demo initial and moved poses with matching FRONT commits", demo_begin)
            result["acceptance_pass"] = True
            return result
        # Fixed coin is project matrix 44 and therefore DSCAN 5, never numeric 44.
        credit_before = read(0xA8, 1)[0]
        if credit_before != 0:
            raise RuntimeError(f"cold credit count was not zero: {credit_before}")
        client.call("inject_key", {"key": 5, "action": "press"}, timeout=10)
        while read(0xA8, 1)[0] == credit_before:
            hit(d0, {pft})
        credit_after = read(0xA8, 1)[0]
        client.call("inject_key", {"key": 5, "action": "release"}, timeout=10)
        if credit_after != 1:
            raise RuntimeError(f"fixed coin did not produce credit 0->1: {credit_before}->{credit_after}")
        client.call("inject_key", {"key": enter, "action": "press"}, timeout=10)
        while True:
            hit(d0, {pft})
            ctx = read(0xA4, 5)
            if ctx[1] == 1 and ctx[3] == 1 and ctx[4] == 0:
                break
        client.call("inject_key", {"key": enter, "action": "release"}, timeout=10)
        phase("cold credit and consumed start", started,
              {"credit": read(0xA8, 1)[0], "context": list(read(0xA4, 5))})

        t0 = time.monotonic()
        setpoints(tick)
        while True:
            hit(t0 + 45, {tick})
            d = dp()
            if (d[0x24] == 1 and d[0xA5] == 0 and d[9:11] == bytes((12, 18))
                    and d[8] == 0
                    and int.from_bytes(d[11:13], "big") == 0x75EC
                    and d[0xA0] == 0):
                break
        before = (d[0x90], int.from_bytes(d[0x92:0x94], "big"))
        setpoints(publish)
        while True:
            hit(t0 + 45, {publish})
            d = dp()
            if d[0x8F] == before[0] and d[0x91] == 0 and int.from_bytes(d[0x92:0x94], "big") != before[1]:
                break
        result["first_level"] = {"stage": d[0x24], "cell": [d[9], d[10]], "step": d[8],
                                 "player_fb": hex(int.from_bytes(d[11:13], "big")),
                                 "front": d[0x8F], "commit": int.from_bytes(d[0x92:0x94], "big")}
        if acceptance:
            setpoints(main["draw_player"])
            while True:
                hit(t0 + 45, {main["draw_player"]})
                first_level_draw = dp()
                if (first_level_draw[0x24] == 1 and first_level_draw[0xA5] == 0
                        and first_level_draw[0xA0] == 0 and first_level_draw[8] == 0
                        and first_level_draw[9:11] == bytes((12, 18))
                        and int.from_bytes(first_level_draw[11:13], "big") == 0x75EC):
                    break
            result["first_level_front"] = capture_front(first_level_draw, "first-level", t0 + 45)
            require_aligned_front("credited first-level", result["first_level_front"])
        phase("first-level correct FRONT baseline", t0, result["first_level"])

        par5 = read(0xFFA5, 1)[0]
        if par5 & 0x3F != 0x34:
            raise RuntimeError(f"gameplay PAR5 page mismatch: {par5:02x}")
        nav = read(main["maze_nav"], 576)
        owner = read(main["maze_gate_owner"], 576)
        gate_raw = read(main["maze_gates"], 60)
        maze = {"nav": nav, "owner": owner,
                "gates": [(gate_raw[i * 3], gate_raw[i * 3 + 1]) for i in range(20)]}
        result["route_source"] = {"nav_sha256": digest(nav), "owner_sha256": digest(owner),
                                  "gate_sha256": digest(gate_raw), "live_arrays": True}
        route_start = time.monotonic()
        deadline = route_start + 45
        setpoints(tick, next_stage)
        start_lives, start_dots, start_bonus = d[0x23], d[0x25], d[0x33]
        progress = []
        transition = False
        at_tick = False
        while time.monotonic() < deadline:
            pc = tick if at_tick else hit(deadline, {tick, next_stage})
            at_tick = False
            if pc == next_stage:
                d = dp()
                if d[0x25] != 0 or d[0x33] != 0 or d[0x26] == 0:
                    result["route_failure"] = "next_stage reached before both counters cleared"
                    break
                release_direction()
                transition = True
                result["natural_next_stage"] = {
                    "pc": hex(pc), "stage": d[0x24], "dots_left": d[0x25],
                    "bonus_remaining": d[0x33], "stage_pending": d[0x26],
                    "cell": [d[9], d[10]], "player_fb": hex(int.from_bytes(d[11:13], "big")),
                }
                break

            d = dp()
            x, y, step = d[9], d[10], d[8]
            if d[0x25] == 0 and d[0x33] == 0 and d[0x24] == 1 and d[0xA5] == 0:
                release_direction()
                result["natural_clear_wait"] = {
                    "marker": "paused player_tick with zero dots and bonus, stage 1, mode 0",
                    "cell": [x, y], "step": step, "lives": d[0x23],
                    "dots_left": d[0x25], "bonus_remaining": d[0x33],
                    "stage_pending_before_handoff": d[0x26],
                    "player_fb": hex(int.from_bytes(d[11:13], "big")),
                    "entities": entities_now(d),
                }
                setpoints(next_stage)
                try:
                    pc = hit(deadline, {next_stage})
                except TimeoutError:
                    result["route_failure"] = "natural next_stage handoff timed out at 45-second deadline"
                    break
                d = dp()
                if d[0x25] != 0 or d[0x33] != 0 or d[0x26] == 0:
                    result["route_failure"] = "natural next_stage marker lacked zero counters and pending transition"
                    break
                transition = True
                result["natural_next_stage"] = {
                    "pc": hex(pc), "stage": d[0x24], "dots_left": d[0x25],
                    "bonus_remaining": d[0x33], "stage_pending": d[0x26],
                    "cell": [d[9], d[10]], "player_fb": hex(int.from_bytes(d[11:13], "big")),
                }
                break
            if step != 0:
                continue

            par5 = read(0xFFA5, 1)[0]
            if par5 & 0x3F != 0x34:
                raise RuntimeError(f"gameplay PAR5 changed: {par5:02x}")
            live_states = list(read(main["GATE_STATE"], 20))
            dots = read(main["MAZE_STATE"], 576)
            enemies = read(main["ENEMY_TABLE"], 32)
            entities = entities_now(d)
            entity_count = len(entities)
            bonus_cells = {(e["x"], e["y"]) for e in entities if e["type"] in (2, 3)}
            skull_cells = {(e["x"], e["y"]) for e in entities if e["type"] == 1}
            blocked_enemies = {
                (row[4], row[5]) for i in range(4)
                if (row := enemies[i * 8:i * 8 + 8])[0] and row[6]
            }
            direction, target = route_first(
                maze, x, y, live_states, dots, bonus_cells, blocked_enemies | skull_cells
            )
            if direction is None:
                direction, target = route_first(
                    maze, x, y, live_states, dots, bonus_cells, skull_cells
                )
            if direction is None and target == (x, y):
                # Let the normal player tick process a pickup already underfoot.
                pc = hit(deadline, {tick, next_stage})
                if pc == next_stage:
                    d = dp()
                    if d[0x25] == 0 and d[0x33] == 0 and d[0x26] != 0:
                        release_direction()
                        transition = True
                        result["natural_next_stage"] = {
                            "pc": hex(pc), "stage": d[0x24], "dots_left": d[0x25],
                            "bonus_remaining": d[0x33], "stage_pending": d[0x26],
                            "cell": [d[9], d[10]],
                            "player_fb": hex(int.from_bytes(d[11:13], "big")),
                        }
                        break
                    result["route_failure"] = "next_stage reached before both counters cleared"
                    break
                at_tick = True
                continue
            if direction is None:
                result["route_failure"] = "no live-nav path to an uncollected dot or heart/letter"
                snapshot = dp()
                result["route_failure_snapshot"] = {
                    "dp_hex": snapshot.hex(), "dots_left": snapshot[0x25],
                    "bonus_remaining": snapshot[0x33], "stage": snapshot[0x24],
                    "mode": snapshot[0xA5], "stage_pending": snapshot[0x26],
                    "entry": snapshot[0xA0], "lives": snapshot[0x23],
                    "cell": [snapshot[9], snapshot[10]], "step": snapshot[8],
                    "player_fb": hex(int.from_bytes(snapshot[11:13], "big")),
                    "par5_normalized": read(0xFFA5, 1)[0] & 0x3F,
                    "entity_count": entity_count, "entities": entities,
                    "bonus_cells": sorted([list(cell) for cell in bonus_cells]),
                    "skull_cells": sorted([list(cell) for cell in skull_cells]),
                }
                break

            scan = matrix_to_dscan(bindings[ACTION_FOR_DIR[direction]])
            old_cell, old_dots, old_bonus, old_lives = (x, y), d[0x25], d[0x33], d[0x23]
            if held_scan != scan:
                if held_scan is not None:
                    client.call("inject_key", {"key": held_scan, "action": "release"}, timeout=10)
                client.call("inject_key", {"key": scan, "action": "press"}, timeout=10)
                held_scan = scan
            moved = False
            for _ in range(12):
                if time.monotonic() >= deadline:
                    result["route_failure"] = "45-second natural-clear deadline during movement"
                    break
                pc = hit(deadline, {tick, next_stage})
                if pc == next_stage:
                    d = dp()
                    if d[0x25] != 0 or d[0x33] != 0 or d[0x26] == 0:
                        result["route_failure"] = "next_stage reached before both counters cleared"
                        break
                    release_direction()
                    transition = True
                    break
                d = dp()
                if (d[9], d[10]) != old_cell and d[8] == 0:
                    moved, at_tick = True, True
                    break
            if transition:
                result["natural_next_stage"] = {
                    "pc": hex(next_stage), "stage": d[0x24], "dots_left": d[0x25],
                    "bonus_remaining": d[0x33], "stage_pending": d[0x26],
                    "cell": [d[9], d[10]], "player_fb": hex(int.from_bytes(d[11:13], "big")),
                }
                break
            if result.get("route_failure") == "45-second natural-clear deadline during movement":
                break
            if not moved:
                release_direction()
                result["route_failure"] = f"no cell arrival from {old_cell} toward {NAMES[direction]} within 12 ticks"
                break
            if (d[0x25] < old_dots or d[0x33] < old_bonus or d[0x23] != old_lives
                    or len(progress) == 0 or (d[9], d[10]) != old_cell):
                progress.append({
                    "cell": [d[9], d[10]], "dots_left": d[0x25],
                    "bonus_remaining": d[0x33], "lives": d[0x23],
                    "target": list(target or ()), "direction": NAMES[direction],
                    "entity_count": len(entities_now(d)), "entities": entities_now(d),
                })

        final_dp = dp()
        final_entities = entities_now(final_dp)
        result["natural_clear_attempt"] = {
            "reached_next_stage": transition,
            "elapsed_seconds": round(time.monotonic() - route_start, 3),
            "deadline_seconds": 45, "start_dots": start_dots,
            "remaining_dots": final_dp[0x25],
            "start_bonus_remaining": start_bonus,
            "remaining_bonus": final_dp[0x33], "start_lives": start_lives,
            "end_lives": final_dp[0x23], "final_entity_count": len(final_entities),
            "final_entities": final_entities, "progress": progress[-40:],
        }
        if acceptance and not transition:
            raise TimeoutError("45-second natural level-1 clear did not reach next_stage")
        if not transition and "route_failure" not in result:
            result["route_failure"] = "45-second natural-clear deadline reached"

        if transition:
            transition_begin = time.monotonic()
            transition_deadline = transition_begin + 45
            setpoints(0xCB04)
            hit(transition_deadline, {0xCB04})
            d = dp()
            if read(0xFFA5, 1)[0] & 0x3F != 0x34:
                raise RuntimeError("post-init_player PAR5 did not map physical page 34")
            resident = (ROOT / "build/ladybug-runtime.rom").read_bytes()
            expected_post_init = resident[0xCB04 - 0xC000:0xCB04 - 0xC000 + 4]
            live_post_init = read(0xCB04, 4)
            if live_post_init != expected_post_init:
                raise RuntimeError("post-init_player PC bytes differ from pinned resident artifact")
            result["next_stage_seed"] = {"pc": "0xCB04", "player_fb": hex(int.from_bytes(d[11:13], "big")),
                                         "cell": [d[9], d[10]], "par5": read(0xFFA5, 1)[0],
                                         "live_bytes": live_post_init.hex()}
            # Follow the natural return/caller path; do not force PC or wait
            # for a presumed helper breakpoint.
            setpoints()
            remaining_bps = client.call("list_breakpoints", timeout=5).get("breakpoints", [])
            if remaining_bps:
                raise RuntimeError(f"unexpected breakpoints before instruction trace: {remaining_bps}")
            resident_image = (ROOT / "build/ladybug-runtime.rom").read_bytes()
            enemy_image = (ROOT / "build/ladybug-enemy-runtime.rom").read_bytes()
            rate_image = (ROOT / "build/ladybug-rate-helper.bin").read_bytes()
            main_symbols = sorted((address, name) for name, address in main.items())
            enemy_symbols = sorted((address, name) for name, address in enemy.items())

            def symbol_at(address: int) -> str:
                if 0xA3B0 <= address < 0xA3B0 + len(rate_image):
                    return f"rate_helper+0x{address - 0xA3B0:03x}"
                table = main_symbols if 0xC000 <= address < 0xE000 else []
                if 0x0800 <= address < 0x0800 + len(enemy_image):
                    table = enemy_symbols
                prior = [(value, name) for value, name in table if value <= address]
                return prior[-1][1] if prior else "unlabeled"

            trace = []
            trace_stop = "instruction-bound-192" if acceptance else "instruction-bound-64"
            caller_return = None
            if acceptance:
                init_addr = main["init_enemy"]
                shim_addr = rate["rate_enemy_init_shim"]
                reset_addr = rate["rate_reset"]
                api_addr = main["ENEMY_MODULE_INIT"]
                enemy_init_addr = enemy["enemy_init_impl"]
                seed_fb = int.from_bytes(d[11:13], "big")
            trace_record = result["init_enemy_trace"] = {
                "method": "step_instruction n=1 then wait_for_stop",
                "max_instructions": 192 if acceptance else 64,
                "stop": trace_stop, "instruction_samples": trace,
            }
            for _ in range(192 if acceptance else 64):
                remaining = transition_deadline - time.monotonic()
                if remaining <= 0:
                    trace_stop = "45-second-transition-deadline"
                    break
                regs_before = client.call("read_registers", timeout=min(2, remaining))
                pc_before = int(regs_before["pc"])
                dp_before = dp()
                par_before = read(0xFFA0, 6)
                live_before = read(pc_before, 6)
                expected_before = physical_before = None
                code_owner, module_match = "unmapped", None
                par5_normalized = par_before[5] & 0x3F
                if 0xC000 <= pc_before < 0xE000:
                    code_owner = "resident"
                    offset = pc_before - 0xC000
                    expected_before = resident_image[offset:offset + len(live_before)]
                    module_match = live_before == expected_before
                elif 0x0800 <= pc_before < 0x0800 + len(enemy_image):
                    code_owner = "enemy"
                    offset = pc_before - 0x0800
                    expected_before = enemy_image[offset:offset + len(live_before)]
                    module_match = live_before == expected_before
                elif 0xA3B0 <= pc_before < 0xA3B0 + len(rate_image):
                    code_owner = "rate-page34"
                    physical_addr = 0x34 * 8192 + (pc_before - 0xA000)
                    physical_before = read(physical_addr, 6, True)
                    expected_before = rate_image[pc_before - 0xA3B0:pc_before - 0xA3B0 + 6]
                    module_match = (par5_normalized == 0x34
                                    and live_before[:len(expected_before)] == expected_before
                                    and physical_before[:len(expected_before)] == expected_before)

                if module_match is False:
                    trace.append({"pc_before": hex(pc_before), "dp_register": regs_before.get("dp"),
                                  "stage": dp_before[0x24], "mode": dp_before[0xA5],
                                  "par_before": par_before.hex(), "code_owner": code_owner,
                                  "symbol": symbol_at(pc_before), "live_before": live_before.hex(),
                                  "expected_before": expected_before.hex() if expected_before is not None else None,
                                  "physical_before": physical_before.hex() if physical_before is not None else None,
                                  "module_match": False, "stop": "failed-before-execution"})
                    result["init_enemy_trace"] = {
                        "method": "step_instruction n=1 then wait_for_stop",
                        "max_instructions": 192 if acceptance else 64, "stop": "module-qualification-failed",
                        "instruction_samples": trace,
                    }
                    raise RuntimeError(f"live executable bytes failed artifact qualification before step at {pc_before:04x}")

                if acceptance:
                    if pc_before == init_addr:
                        target = int.from_bytes(live_before[1:3], "big")
                        if live_before[0] != 0x7E or target != shim_addr:
                            raise RuntimeError(f"qualified init_enemy JMP missed mapped shim: {live_before[:3].hex()}")
                    if 0xC000 <= pc_before < 0xE000 and live_before[0] == 0x17:
                        target = (pc_before + 3 + int.from_bytes(live_before[1:3], "big", signed=True)) & 0xFFFF
                        if target == init_addr:
                            if caller_return is not None:
                                raise RuntimeError("multiple resident calls to init_enemy appeared in natural handoff")
                            caller_return = pc_before + 3
                    if pc_before == shim_addr:
                        target = (pc_before + 3 + int.from_bytes(live_before[1:3], "big", signed=True)) & 0xFFFF
                        if live_before[0] != 0x17 or target != reset_addr:
                            raise RuntimeError(f"qualified shim did not call mapped rate_reset: {live_before[:3].hex()}")
                        shim_jump = rate_image[shim_addr - rate["rate_reset"] + 3:shim_addr - rate["rate_reset"] + 6]
                        jump_target = int.from_bytes(shim_jump[1:3], "big")
                        if shim_jump[0] != 0x7E or jump_target != api_addr:
                            raise RuntimeError(f"mapped shim tail target missed enemy API entry: {shim_jump.hex()}")
                    if pc_before == api_addr and (live_before[0] != 0x7E
                                                   or int.from_bytes(live_before[1:3], "big") != enemy_init_addr):
                        raise RuntimeError(f"qualified enemy API entry missed mapped initializer: {live_before[:3].hex()}")

                ack = client.call("step_instruction", {"n": 1}, timeout=min(2, remaining))
                if not ack.get("ok") or ack.get("n") != 1:
                    trace_stop = f"step-rejected:{ack}"
                    break
                stop = client.call("wait_for_stop", {"timeout_ms": min(1000, max(1, int(remaining * 1000)))},
                                   timeout=min(2, remaining))
                if stop.get("reason") == "timeout":
                    trace.append({"pc_before": hex(pc_before), "reason": "wait-for-stop-timeout",
                                  "dp_register": regs_before.get("dp"), "par_before": par_before.hex(),
                                  "code_owner": code_owner, "symbol": symbol_at(pc_before),
                                  "par5_normalized": par5_normalized,
                                  "live_before": live_before.hex(),
                                  "expected_before": expected_before.hex() if expected_before is not None else None,
                                  "physical_before": physical_before.hex() if physical_before is not None else None,
                                  "module_match": module_match})
                    trace_stop = "step-stop-timeout"
                    break
                regs_after = client.call("read_registers", timeout=min(2, remaining))
                pc_after = int(regs_after["pc"])
                if stop.get("reason") != "step" or int(stop.get("pc", -1)) != pc_after:
                    trace_stop = f"non-step-stop:{stop}"
                dp_after = dp()
                par_after = read(0xFFA0, 6)
                trace.append({
                    "stop_reason": stop.get("reason"), "pc_before": hex(pc_before), "pc_after": hex(pc_after),
                    "symbol_before": symbol_at(pc_before), "symbol_after": symbol_at(pc_after),
                    "registers_before": regs_before, "registers_after": regs_after,
                    "stage_before_after": [dp_before[0x24], dp_after[0x24]],
                    "mode_before_after": [dp_before[0xA5], dp_after[0xA5]],
                    "cell_before_after": [[dp_before[9], dp_before[10]], [dp_after[9], dp_after[10]]],
                    "step_before_after": [dp_before[8], dp_after[8]],
                    "player_fb_before_after": [hex(int.from_bytes(dp_before[11:13], "big")),
                                                hex(int.from_bytes(dp_after[11:13], "big"))],
                    "par_before_after": [par_before.hex(), par_after.hex()],
                    "par5_normalized_before_after": [par5_normalized, par_after[5] & 0x3F],
                    "code_owner": code_owner, "live_before": live_before.hex(),
                    "expected_before": expected_before.hex() if expected_before is not None else None,
                    "physical_before": physical_before.hex() if physical_before is not None else None,
                    "module_match": module_match,
                })
                if trace_stop.startswith("non-step-stop"):
                    break
                if acceptance and int.from_bytes(dp_after[11:13], "big") != seed_fb:
                    raise RuntimeError(f"PLAYER_FB seed changed during init_enemy handoff: {seed_fb:04x}->{int.from_bytes(dp_after[11:13], 'big'):04x}")
                if acceptance and caller_return is not None and pc_after == caller_return:
                    seen_pcs = {int(row[key], 16) for row in trace for key in ("pc_before", "pc_after")}
                    required_pcs = {init_addr, shim_addr, reset_addr, shim_addr + 3, api_addr, enemy_init_addr}
                    if not required_pcs.issubset(seen_pcs):
                        raise RuntimeError("qualified handoff path was incomplete before resident caller return")
                    return_expected = resident_image[caller_return - 0xC000:caller_return - 0xC000 + 6]
                    if read(caller_return, 6) != return_expected:
                        raise RuntimeError("map-derived resident caller return bytes failed artifact qualification")
                    result["init_enemy_handoff"] = {
                        "player_fb_seed": hex(seed_fb),
                        "caller_return_pc": hex(caller_return),
                        "player_fb_at_return": hex(int.from_bytes(dp_after[11:13], "big")),
                    }
                    trace_stop = "reached-map-derived-resident-caller-return"
                    break
                if not acceptance and pc_after == 0xA467:
                    trace_stop = "reached-post-ASL-boundary-A467"
                    break
            trace_record.update({
                "stop": trace_stop,
                "helper_dec_instruction_seen": any(row.get("pc_before") == "0xa463" for row in trace),
                "helper_asl_instruction_seen": any(row.get("pc_before") == "0xa465" for row in trace),
            })
            draw = main["draw_player"]
            setpoints(draw)
            while True:
                hit(transition_deadline, {draw})
                d = dp()
                if d[0x24] == 2 and d[0xA5] == 0 and d[0xA0] == 0 and d[8] == 0:
                    break
            result["accepted_front"] = capture_front(d, "initial", transition_deadline)
            if acceptance:
                require_aligned_front("natural level-2 initial", result["accepted_front"])

            # One ordinary north input captures a moving pose at the next
            # aligned cell, under the same 45-second transition deadline.
            first_cell = [d[9], d[10]]
            if first_cell != [12, 22]:
                raise RuntimeError(f"expected initial level-2 aligned cell [12, 22], got {first_cell}")
            target_cell = [12, 21]
            setpoints(draw)
            north_scan = directions[0]
            client.call("inject_key", {"key": north_scan, "action": "press"}, timeout=10)
            held_scan = north_scan
            moving_draw = None
            while time.monotonic() < transition_deadline:
                hit(transition_deadline, {draw})
                candidate = dp()
                if (candidate[0x24] == 2 and candidate[0xA5] == 0 and candidate[0xA0] == 0
                        and [candidate[9], candidate[10]] == target_cell and candidate[8] == 0):
                    moving_draw = candidate
                    break
            release_direction()
            if moving_draw is None:
                raise TimeoutError("no aligned north-movement draw at level-2 cell [12, 21] before transition deadline")
            result["north_movement_front"] = capture_front(moving_draw, "north", transition_deadline)
            if acceptance:
                require_aligned_front("natural level-2 moved", result["north_movement_front"])
            phase("natural next-stage initial and moving poses with matching FRONT commits", transition_begin,
                  {"elapsed_seconds": round(time.monotonic() - transition_begin, 3), "deadline_seconds": 45})
            if acceptance:
                if result.get("init_enemy_trace", {}).get("stop") != "reached-map-derived-resident-caller-return":
                    raise RuntimeError("positive acceptance did not reach the mapped resident caller return")
                result["acceptance_pass"] = True
    except Exception as exc:
        if "trace_record" in locals():
            trace_record["stop"] = trace_stop
        result["failure"] = {"type": type(exc).__name__, "detail": str(exc)}
        raise
    finally:
        if held_scan is not None and client:
            try:
                client.call("inject_key", {"key": held_scan, "action": "release"}, timeout=2)
            except Exception:
                pass
        if bps and client:
            for ident in bps:
                try:
                    client.call("clear_breakpoint", {"id": ident}, timeout=2)
                except Exception:
                    pass
        if client:
            client.close()
        if process:
            monitor.stop(process)
            process.wait(timeout=2)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result), flush=True)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare-only", action="store_true")
    mode.add_argument("--run", action="store_true")
    mode.add_argument("--acceptance", action="store_true")
    parser.add_argument("--acceptance-manifest", type=Path)
    parser.add_argument("--scenario", choices=("level2", "demo"), default="level2")
    parser.add_argument("--xroar", type=Path, default=ROOT / "docs/reference/xroar/src/xroar")
    parser.add_argument("--output", type=Path, default=ROOT / "repro/bug123-runtime-20261012/runtime-reproduction-run.json")
    args = parser.parse_args()
    if args.prepare_only:
        print(json.dumps(self_check(args.acceptance_manifest), indent=2))
    elif args.acceptance:
        if not args.acceptance_manifest:
            parser.error("--acceptance requires --acceptance-manifest")
        run(args.xroar, args.output, args.acceptance_manifest, args.scenario)
    else:
        if args.acceptance_manifest or args.scenario != "level2":
            parser.error("--acceptance-manifest and non-default --scenario require --acceptance")
        run(args.xroar, args.output)


if __name__ == "__main__":
    main()
