#!/usr/bin/env python3
"""Independently prove cached gate entity replay equals the normal compositor."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]

def bytes_after(path, label, count):
    text = path.read_text(encoding="utf-8")
    part = text[text.index(label) + len(label):]
    values = []
    for line in part.splitlines():
        if re.match(r"^[A-Za-z_]\w*$", line) and values:
            break
        if "fcb" in line:
            values += [int(x.strip().replace("$", "0x"), 0)
                       for x in line.split("fcb", 1)[1].split(",")]
        if len(values) >= count:
            return values[:count]
    raise ValueError(label + " truncated")

def draw(mask_bytes, lut, background):
    out = bytearray(background)
    for i, source in enumerate(mask_bytes):
        for shift, index in ((4, 0), (0, 1)):
            nibble = (source >> shift) & 15
            pos = i * 2 + index
            out[pos] = (out[pos] & mask_lut[nibble]) | lut[nibble]
    return out

def cache_from_postdraw(mask_bytes, lut, postdraw):
    # Independently derive assembly cache pairs from post-draw pixels and masks.
    pairs = bytearray()
    for i, source in enumerate(mask_bytes):
        for shift, index in ((4, 0), (0, 1)):
            nibble = (source >> shift) & 15
            pairs += bytes((mask_lut[nibble], postdraw[i * 2 + index] & ~mask_lut[nibble]))
    return pairs

def replay(pairs, gate):
    out = bytearray(gate)
    for i in range(128):
        out[i] = (out[i] & pairs[i * 2]) | pairs[i * 2 + 1]
    return out

main = ROOT / "src" / "main.s"
screen = ROOT / "build" / "ladybug_screen.inc"
mask_lut = bytes_after(main, "object_mask_lut", 16)
luts = {name: bytes_after(main, "object_" + name + "_lut", 16)
        for name in ("red", "yellow", "blue", "skull")}
masks = bytes_after(screen, "object_masks", 12 * 64)
if len(masks) != 768 or "GATE_ENTITY_RECORD_SIZE equ 77" not in main.read_text(encoding="utf-8"):
    raise SystemExit("gate cache proof: variant or 77-byte association record missing")
patterns = [bytes(range(128)), bytes((i * 37 + 19) & 255 for i in range(128)), bytes([0x55, 0xAA]) * 64]
cases = 0
for variant in range(12):
    source = masks[variant * 64:(variant + 1) * 64]
    for lut in luts.values():
        for background in patterns:
            post = draw(source, lut, background)
            cache = cache_from_postdraw(source, lut, post)
            for gate in patterns:
                if replay(cache, gate) != draw(source, lut, gate):
                    raise SystemExit("gate cache proof: replay diverged")
                cases += 1
# Mutation self-test: a corrupted cached value must be detected.
source, lut, background, gate = masks[:64], luts["red"], patterns[0], patterns[1]
bad = cache_from_postdraw(source, lut, draw(source, lut, background)); bad[1] ^= 1
if replay(bad, gate) == draw(source, lut, gate):
    raise SystemExit("gate cache proof: mutation self-test did not fail")
print(f"gate cache proof: {cases} variant/colour/background/gate cases plus mutation self-test pass")
