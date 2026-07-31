#!/usr/bin/env python3
"""Verify every sparse popup and death presentation stream pixel-exactly."""

from __future__ import annotations

import re
from pathlib import Path

from build_screen import (
    BLACK, WHITE, MULTIPLIER_CHAR_CODES, SCORE_CODES,
    compile_death_sprites, compile_sprite_codes, expand_sprite,
    load_chars, pack_tile, recolor, rotate_ccw,
)


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
SPRITES = ROOT / "assets/arcade/sprites.json"
CHARS = ROOT / "assets/arcade/chars.json"
MAP_RE = re.compile(r"^Symbol: (\w+) .* = ([0-9A-Fa-f]+)$")


def decode(stream: bytes, rows: int, width: int) -> tuple[bytes, int]:
    background = bytearray((index * 73 + 0x5A) & 0xFF
                           for index in range(rows * width))
    output = bytearray(background)
    cursor = 0
    destination = 0
    while True:
        token = stream[cursor]
        cursor += 1
        if token == 0xFF:
            delta = (stream[cursor] << 8) | stream[cursor + 1]
            cursor += 2
            if delta == 0:
                return bytes(output), cursor
            cursor += 1
        else:
            delta = token
        destination += delta
        control = stream[cursor]
        cursor += 1
        partial = bool(control & 0x80)
        count = control & 0x7F
        row, column = divmod(destination, 160)
        if row >= rows or column + count > width:
            raise ValueError("presentation stream writes outside its footprint")
        target = row * width + column
        for index in range(count):
            if partial:
                mask, pixel = stream[cursor:cursor + 2]
                cursor += 2
                output[target + index] = (output[target + index] & mask) | pixel
            else:
                output[target + index] = stream[cursor]
                cursor += 1
        destination += count


def expected_blend(native: bytes) -> bytes:
    output = bytearray((index * 73 + 0x5A) & 0xFF
                       for index in range(len(native)))
    for index, pixel in enumerate(native):
        mask = (0xF0 if not pixel & 0xF0 else 0) | (
            0x0F if not pixel & 0x0F else 0)
        output[index] = (output[index] & mask) | pixel
    return bytes(output)


def verify_sequence(payload: bytes, expected: list[tuple[bytes, int, int]],
                    label: str) -> int:
    offset = 0
    for index, (native, rows, width) in enumerate(expected):
        decoded, count = decode(payload[offset:], rows, width)
        if decoded != expected_blend(native):
            raise SystemExit(f"presentation proof: {label} {index} differs")
        offset += count
    return offset


def symbols() -> dict[str, int]:
    result = {}
    for line in (BUILD / "ladybug.map").read_text(encoding="utf-8").splitlines():
        match = MAP_RE.match(line)
        if match:
            result[match.group(1)] = int(match.group(2), 16)
    return result


def main() -> None:
    score = compile_sprite_codes(SPRITES, SCORE_CODES)
    popup_expected = [
        (expand_sprite(frame, pen_map), 16, 8)
        for pen_map in ((0, 1, 5, 6), (0, 2, 5, 6), (0, 3, 5, 6))
        for frame in score
    ]
    chars = load_chars(CHARS)
    multiplier_expected = [
        (pack_tile(recolor(rotate_ccw(chars[code]),
                           (BLACK, WHITE, WHITE, WHITE))), 8, 4)
        for code in MULTIPLIER_CHAR_CODES
    ]
    payload = (BUILD / "ladybug-presentation-sparse.bin").read_bytes()
    used = verify_sequence(payload, popup_expected, "popup")
    used += verify_sequence(payload[used:], multiplier_expected, "multiplier")
    if used != len(payload):
        raise SystemExit("presentation proof: unverified expansion payload remains")

    death = compile_death_sprites(SPRITES)
    death_expected = [
        (expand_sprite(frame, (0, 1 if index < 7 else 6,
                               1 if index < 7 else 6,
                               1 if index < 7 else 6)), 16, 8)
        for index, frame in enumerate(death)
    ]
    sym = symbols()
    rom = (BUILD / "ladybug-runtime.rom").read_bytes()
    for index, expected in enumerate(death_expected):
        start = sym[f"death_sparse_frame_{index}"] - 0xC000
        decoded, _ = decode(rom[start:], 16, 8)
        if decoded != expected_blend(expected[0]):
            raise SystemExit(f"presentation proof: death frame {index} differs")

    source = (ROOT / "src/main.s").read_text(encoding="utf-8")
    runtime = (ROOT / "src/enemy_runtime.s").read_text(encoding="utf-8")
    for fragment in (
        "PRESENTATION_MODULE_DRAW equ $0821",
        "lda     #PRESENTATION_PAYLOAD_PAGE",
        "jsr     PRESENTATION_MODULE_DRAW",
    ):
        if fragment not in source:
            raise SystemExit("presentation proof: missing runtime contract: " + fragment)
    if "jmp     sparse_blit_fb" not in runtime.split("ENEMY_ANIM", 1)[0]:
        raise SystemExit("presentation proof: fixed sparse ABI entry is missing")
    print("presentation proof: 9 colour/score, 3 multiplier, and 14 death streams blend pixel-exactly with PAR5-restoring sparse decode")


if __name__ == "__main__":
    main()
