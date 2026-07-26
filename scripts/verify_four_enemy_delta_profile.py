#!/usr/bin/env python3
"""Verify the controlled destination-delta four-enemy profile and image."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from PIL import Image

from build_screen import PALETTE, compile_enemy_sprites, compile_player_sprites, gime_rgb
from build_sparse_sprites import expand_native_frame


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
FB_BASE = 0x2000
FB_BYTES = 160 * 192
HARDWARE_BUDGET = 29_666
ENEMY_POINTERS = (0x2FCE, 0x2FEE, 0x6FCA, 0x6FEA)
ENEMY_FRAMES = (5, 5, 13, 13)
ENEMY_DIRECTIONS = (1, 1, 3, 3)
PLAYER_POINTER = 0x4E8C
PLAYER_FRAME = 3


def trace_profile(path: Path) -> dict[str, object]:
    lines = path.read_text(encoding="ascii").splitlines()
    cycles = []
    pcs = []
    for line in lines:
        match = re.search(r" dt=(\d+)$", line)
        if not match or int(match.group(1)) % 8:
            raise ValueError(f"{path}: invalid timed trace line")
        cycles.append(int(match.group(1)) // 8)
        pcs.append(line[:4])

    marked: set[int] = set()

    def segments(entry: str, return_pc: str) -> list[tuple[int, int]]:
        result = []
        for start in (i for i, pc in enumerate(pcs) if pc == entry):
            begin = start - 1
            end = next(
                i for i in range(start + 1, len(pcs)) if pcs[i] == return_pc
            )
            if any(index in marked for index in range(begin, end)):
                raise ValueError(f"{path}: overlapping attribution at {entry}")
            marked.update(range(begin, end))
            result.append((end - begin, sum(cycles[begin:end])))
        return result

    def aggregate(items: list[tuple[int, int]]) -> tuple[int, int]:
        return sum(item[0] for item in items), sum(item[1] for item in items)

    restore = aggregate(segments("0be7", "0a2b"))
    strip = aggregate(segments("109e", "0c45"))
    enemy_draw = aggregate(segments("13a6", "0c69"))
    enemy_logic = aggregate(segments("d206", "c102"))

    player_start = [i for i, pc in enumerate(pcs) if pc == "0c69"][-1]
    player_end = next(
        i for i in range(player_start + 1, len(pcs)) if pcs[i] == "0b05"
    )
    if any(index in marked for index in range(player_start, player_end)):
        raise ValueError(f"{path}: player attribution overlaps another path")
    marked.update(range(player_start, player_end))
    player = (
        player_end - player_start,
        sum(cycles[player_start:player_end]),
    )

    sync_indexes = {
        index for index, line in enumerate(lines) if "| 13 " in line
    }
    elapsed_cycles = sum(cycles)
    sync_cycles = sum(cycles[index] for index in sync_indexes)
    active_indexes = set(range(len(lines))) - sync_indexes
    active_cycles = elapsed_cycles - sync_cycles
    other_indexes = active_indexes - marked
    other = (
        len(other_indexes),
        sum(cycles[index] for index in other_indexes),
    )

    decoder_segments = []
    for start in (i for i, pc in enumerate(pcs) if pc == "163c"):
        end = next(
            i for i in range(start, len(pcs)) if pcs[i] == "16aa"
        ) + 1
        decoder_segments.append((end - start, sum(cycles[start:end])))
    if len(decoder_segments) != 5:
        raise ValueError(f"{path}: expected four enemy and one player decode")

    paths = (
        ("circular save-under restore", restore),
        ("segmented horizontal strip capture", strip),
        ("four sparse enemy draws", enemy_draw),
        ("player restoration and sparse draw", player),
        ("enemy logic", enemy_logic),
        ("ownership, IRQ, and remaining orchestration", other),
    )
    if sum(item[1][1] for item in paths) != active_cycles:
        raise ValueError(f"{path}: path attribution does not cover active cycles")

    return {
        "instructions": len(lines),
        "active_instructions": len(active_indexes),
        "elapsed_cycles": elapsed_cycles,
        "sync_wait_cycles": sync_cycles,
        "active_cycles": active_cycles,
        "budget_margin_cycles": HARDWARE_BUDGET - active_cycles,
        "budget_multiple": round(active_cycles / HARDWARE_BUDGET, 3),
        "enemy_decoder_body_cycles": sum(item[1] for item in decoder_segments[:4]),
        "player_decoder_body_cycles": decoder_segments[-1][1],
        "paths": [
            {
                "name": name,
                "instructions": values[0],
                "cycles": values[1],
                "share_percent": round(values[1] * 100 / active_cycles, 1),
            }
            for name, values in paths
        ],
    }


def framebuffer_rect(framebuffer: bytes, pointer: int) -> bytes:
    offset = pointer - FB_BASE
    return b"".join(
        framebuffer[offset + row * 160:offset + row * 160 + 8]
        for row in range(16)
    )


def blend_frame(framebuffer: bytearray, pointer: int, native: bytes) -> None:
    offset = pointer - FB_BASE
    for row in range(16):
        for column in range(8):
            pixel = native[row * 8 + column]
            mask = (0xF0 if not pixel & 0xF0 else 0) | (
                0x0F if not pixel & 0x0F else 0
            )
            target = offset + row * 160 + column
            framebuffer[target] = (framebuffer[target] & mask) | pixel


def changed_outside(before: bytes, after: bytes, pointers: tuple[int, ...]) -> int:
    allowed = {
        pointer - FB_BASE + row * 160 + column
        for pointer in pointers
        for row in range(16)
        for column in range(8)
    }
    return sum(
        first != second and index not in allowed
        for index, (first, second) in enumerate(zip(before, after))
    )


def render_png(framebuffer: bytes, path: Path) -> None:
    palette = [gime_rgb(value) for value in PALETTE]
    image = Image.new("RGB", (320, 192))
    pixels = image.load()
    for y in range(192):
        for byte_x, value in enumerate(framebuffer[y * 160:(y + 1) * 160]):
            pixels[byte_x * 2, y] = palette[value >> 4]
            pixels[byte_x * 2 + 1, y] = palette[value & 0x0F]
    image.save(path)


def main() -> None:
    clean = (BUILD / "four-enemy-delta-clean.bin").read_bytes()
    enemies = (BUILD / "four-enemy-delta-enemies.bin").read_bytes()
    final = (BUILD / "four-enemy-delta-framebuffer.bin").read_bytes()
    saveunder = (BUILD / "four-enemy-delta-saveunder.bin").read_bytes()
    ring = (BUILD / "four-enemy-delta-ring.bin").read_bytes()
    player_saveunder = (
        BUILD / "four-enemy-delta-player-saveunder.bin"
    ).read_bytes()
    enemy_table = (BUILD / "four-enemy-delta-enemy-table.bin").read_bytes()
    if any(len(data) != FB_BYTES for data in (clean, enemies, final)):
        raise SystemExit("four-enemy proof: framebuffer dump has invalid length")
    if len(saveunder) != 512 or len(ring) != 4 or len(enemy_table) != 32:
        raise SystemExit("four-enemy proof: actor ownership dump has invalid length")

    enemy_sources = compile_enemy_sprites(ROOT / "assets/arcade/sprites.json")
    player_sources = compile_player_sprites(ROOT / "assets/arcade/sprites.json")
    expected_enemies = bytearray(clean)
    for pointer, frame in zip(ENEMY_POINTERS, ENEMY_FRAMES):
        blend_frame(
            expected_enemies,
            pointer,
            expand_native_frame(enemy_sources[frame]),
        )
    if enemies != expected_enemies:
        raise SystemExit("four-enemy proof: live enemy framebuffer differs")

    expected_final = bytearray(expected_enemies)
    blend_frame(
        expected_final,
        PLAYER_POINTER,
        expand_native_frame(player_sources[PLAYER_FRAME]),
    )
    if final != expected_final:
        raise SystemExit("four-enemy proof: live final framebuffer differs")

    actor_proof = []
    for slot, (pointer, frame, phase) in enumerate(
        zip(ENEMY_POINTERS, ENEMY_FRAMES, ring)
    ):
        row_phase = phase >> 4
        column_phase = phase & 7
        physical = saveunder[slot * 128:(slot + 1) * 128]
        logical = bytes(
            physical[((row + row_phase) & 15) * 8 + ((column + column_phase) & 7)]
            for row in range(16)
            for column in range(8)
        )
        clean_rect = framebuffer_rect(clean, pointer)
        if logical != clean_rect:
            raise SystemExit(f"four-enemy proof: slot {slot} save-under differs")
        record = enemy_table[slot * 8:(slot + 1) * 8]
        if int.from_bytes(record[1:3], "big") != pointer:
            raise SystemExit(f"four-enemy proof: slot {slot} pointer differs")
        if record[7] != ENEMY_DIRECTIONS[slot]:
            raise SystemExit(f"four-enemy proof: slot {slot} direction differs")
        actor_proof.append({
            "slot": slot,
            "pointer_hex": f"{pointer:04X}",
            "frame": frame,
            "direction": ENEMY_DIRECTIONS[slot],
            "ring_phase_hex": f"{phase:02X}",
            "framebuffer_match": 128,
            "saveunder_match": 128,
        })

    if player_saveunder != framebuffer_rect(clean, PLAYER_POINTER):
        raise SystemExit("four-enemy proof: selected player save-under differs")
    enemy_outside = changed_outside(clean, enemies, ENEMY_POINTERS)
    player_outside = changed_outside(enemies, final, (PLAYER_POINTER,))
    if enemy_outside or player_outside:
        raise SystemExit("four-enemy proof: actor write escaped its footprint")

    owner_a = trace_profile(BUILD / "four-enemy-delta-owner-a.trace")
    owner_b = trace_profile(BUILD / "four-enemy-delta-owner-b.trace")
    if min(
        owner_a["budget_margin_cycles"], owner_b["budget_margin_cycles"]
    ) <= 0:
        raise SystemExit("four-enemy proof: strict cycle budget failed")

    image_path = BUILD / "four-enemy-delta-framebuffer.png"
    render_png(final, image_path)
    report = {
        "captured": "2026-07-26",
        "scenario": {
            "active_enemies": 4,
            "movement": ["east", "east", "west", "west"],
            "enemy_frames": list(ENEMY_FRAMES),
            "format": "shared destination-delta sparse streams",
            "strip_capture": "segmented horizontal tail/head",
            "index_mapping": "mirrored $0500/$0680; one payload map per draw",
        },
        "hardware_budget_cycles": HARDWARE_BUDGET,
        "owners": {"A": owner_a, "B": owner_b},
        "live_framebuffer_proof": {
            "actors": actor_proof,
            "enemy_framebuffer_match": 512,
            "enemy_framebuffer_total": 512,
            "saveunder_match": 512,
            "saveunder_total": 512,
            "enemy_changes_outside_footprints": enemy_outside,
            "player_pointer_hex": f"{PLAYER_POINTER:04X}",
            "player_frame": PLAYER_FRAME,
            "player_framebuffer_match": 128,
            "player_saveunder_match": 128,
            "player_changes_outside_footprint": player_outside,
            "framebuffer_sha256": hashlib.sha256(final).hexdigest(),
        },
        "artifacts": {
            "owner_a_trace": "build/four-enemy-delta-owner-a.trace",
            "owner_b_trace": "build/four-enemy-delta-owner-b.trace",
            "clean": "build/four-enemy-delta-clean.bin",
            "enemies": "build/four-enemy-delta-enemies.bin",
            "framebuffer": "build/four-enemy-delta-framebuffer.bin",
            "saveunder": "build/four-enemy-delta-saveunder.bin",
            "ring": "build/four-enemy-delta-ring.bin",
            "image": "build/four-enemy-delta-framebuffer.png",
        },
    }
    report_path = BUILD / "four-enemy-delta-profile.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="ascii")
    print(
        "four-enemy proof: "
        f"A {owner_a['active_cycles']} cycles, "
        f"B {owner_b['active_cycles']} cycles; "
        "512/512 enemies, 512/512 save-under, 128/128 player; "
        f"sha256 {report['live_framebuffer_proof']['framebuffer_sha256']}"
    )


if __name__ == "__main__":
    main()
