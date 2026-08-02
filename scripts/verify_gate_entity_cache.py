#!/usr/bin/env python3
"""Independently prove the bounded sparse gate-entity cache is exact.

This verifier deliberately does not derive replay pairs from a post-draw image.
It parses the generated object masks and the assembler's mask/colour LUTs,
models the original 128 destination writes, separately builds sparse runs, and
then replays those runs onto unrelated patterned destinations.
"""

from __future__ import annotations

import re
from pathlib import Path

from read_snapshot import cpu_to_phys, find_ram


ROOT = Path(__file__).resolve().parents[1]
RECORD_BYTES = 128


def bytes_after(path: Path, label: str, count: int) -> bytes:
    text = path.read_text(encoding="utf-8")
    match = re.search(rf"(?m)^{re.escape(label)}\s*$", text)
    if not match:
        raise ValueError(f"{label}: label missing")
    part = text[match.end() :]
    values: list[int] = []
    for line in part.splitlines():
        if re.match(r"^[A-Za-z_]\w*$", line) and values:
            break
        if "fcb" in line:
            values.extend(
                int(value.strip().replace("$", "0x"), 0)
                for value in line.split("fcb", 1)[1].split(",")
            )
        if len(values) >= count:
            return bytes(values[:count])
    raise ValueError(f"{label}: truncated")


def original_renderer(mask: bytes, lut: bytes, destination: bytearray) -> bytearray:
    """Model draw_entity_object's 128 original destination operations."""
    out = bytearray(destination)
    for source_index, packed in enumerate(mask):
        row, source_column = divmod(source_index, 4)
        for shift, column in ((4, source_column * 2), (0, source_column * 2 + 1)):
            nibble = (packed >> shift) & 15
            pos = row * 160 + column
            out[pos] = (out[pos] & MASK_LUT[nibble]) | lut[nibble]
    return out


def sparse_builder(mask: bytes, lut: bytes) -> bytes:
    """Build the runtime cache format independently from original operations."""
    runs: list[list[tuple[int, int, int]]] = []
    previous_position: int | None = None
    for source_index, packed in enumerate(mask):
        row, source_column = divmod(source_index, 4)
        for shift, column in ((4, source_column * 2), (0, source_column * 2 + 1)):
            nibble = (packed >> shift) & 15
            preserve = MASK_LUT[nibble]
            if preserve == 0xFF:
                previous_position = None
                continue
            position = row * 160 + column
            pair = (position, preserve, lut[nibble])
            if previous_position is not None and position == previous_position + 1:
                runs[-1].append(pair)
            else:
                runs.append([pair])
            previous_position = position

    encoded = bytearray([len(runs)])
    cursor = 0
    for run in runs:
        if run[0][0] // 160 != run[-1][0] // 160:
            raise ValueError("cache run crosses a framebuffer row")
        delta = run[0][0] - cursor
        if 0 <= delta < 0xFF:
            encoded.append(delta)
        else:
            encoded.extend((0xFF, delta >> 8, delta & 0xFF))
        encoded.append(len(run))
        for _, preserve, value in run:
            encoded.extend((preserve, value))
        cursor = run[-1][0] + 1
    if len(encoded) > RECORD_BYTES:
        raise ValueError(f"cache overflow: {len(encoded)} bytes")
    return bytes(encoded)


def sparse_replay(cache: bytes, destination: bytearray) -> bytearray:
    """Model replay_gate_entity_overlay without calling the original renderer."""
    out = bytearray(destination)
    offset = 0
    cursor = 0
    runs = cache[offset]
    offset += 1
    for _ in range(runs):
        delta = cache[offset]
        offset += 1
        if delta == 0xFF:
            delta = (cache[offset] << 8) | cache[offset + 1]
            offset += 2
        cursor += delta
        length = cache[offset]
        offset += 1
        if not length:
            raise ValueError("zero-length sparse run")
        for _ in range(length):
            preserve, value = cache[offset], cache[offset + 1]
            offset += 2
            out[cursor] = (out[cursor] & preserve) | value
            cursor += 1
    return out


def runtime_snapshot_proof(masks: bytes, luts: dict[str, bytes]) -> str:
    """Prove the emulator-built B000-B5FF records equal independently built runs."""
    snapshot = ROOT / "build" / "perf-baseline.sna"
    if not snapshot.exists():
        return "runtime snapshot absent"
    ram = find_ram(snapshot.read_bytes())
    entity_count = ram[cpu_to_phys(0x0032)]
    bonus_colour = ram[cpu_to_phys(0x002F)]
    colour_lut = {1: luts["red"], 2: luts["yellow"], 3: luts["blue"]}.get(
        bonus_colour, luts["blue"]
    )
    cache_phys = cpu_to_phys(0xB000)
    table_phys = cpu_to_phys(0xA380)
    if not 1 <= entity_count <= 12:
        raise ValueError(f"runtime cache proof: invalid entity count {entity_count}")
    for slot in range(entity_count):
        entity = ram[table_phys + slot * 4:table_phys + slot * 4 + 4]
        entity_type, variant = entity[2], entity[3]
        lut = luts["skull"] if entity_type == 1 else colour_lut
        expected = sparse_builder(masks[variant * 64:(variant + 1) * 64], lut)
        record = bytes(ram[cache_phys + slot * 128:cache_phys + (slot + 1) * 128])
        if record[:len(expected)] != expected:
            mismatch = next(
                offset for offset, (left, right) in enumerate(zip(record, expected))
                if left != right
            )
            raise ValueError(
                f"runtime cache proof: slot {slot} record differs at {mismatch}: "
                f"actual={record[mismatch]:02x} expected={expected[mismatch]:02x}; "
                f"variant={variant} type={entity_type} colour={bonus_colour}; "
                f"actual={record[:24].hex()} expected={expected[:24].hex()}"
            )

    lists_phys = cpu_to_phys(0xB600)
    gates = bytes_after(ROOT / "build" / "ladybug_maze.inc", "maze_gates", 60)
    neighbours = bytes_after(ROOT / "build" / "ladybug_screen.inc", "gate_redraw_neighbors", 20)
    for gate in range(20):
        record = ram[lists_phys + gate * 77:lists_phys + (gate + 1) * 77]
        gx, gy = gates[gate * 3], gates[gate * 3 + 1]
        start_x, end_x, start_y, end_y = gx - 2, gx + 1, gy - 2, gy + 1
        neighbour = neighbours[gate]
        if neighbour:
            nx, ny = gates[(neighbour - 1) * 3], gates[(neighbour - 1) * 3 + 1]
            start_x, end_x = min(start_x, nx - 2), max(end_x, nx + 1)
            start_y, end_y = min(start_y, ny - 2), max(end_y, ny + 1)
        if tuple(record[:4]) != (start_x, start_y, end_x, end_y):
            raise ValueError(f"runtime cache proof: gate {gate} bounds differ")
        expected_slots = []
        for slot in range(entity_count):
            ex, ey = ram[table_phys + slot * 4], ram[table_phys + slot * 4 + 1]
            if ex >= start_x and ex - 1 <= end_x and ey >= start_y and ey - 1 <= end_y:
                expected_slots.append(slot)
        count = record[4]
        if count != len(expected_slots):
            raise ValueError(f"runtime cache proof: gate {gate} count differs")
        for index, slot in enumerate(expected_slots):
            entry = 5 + index * 6
            entity_ptr = int.from_bytes(record[entry:entry + 2], "big")
            cache_ptr = int.from_bytes(record[entry + 2:entry + 4], "big")
            fb_ptr = int.from_bytes(record[entry + 4:entry + 6], "big")
            ex, ey = ram[table_phys + slot * 4], ram[table_phys + slot * 4 + 1]
            expected_fb = 0x2000 + (ey - 1) * 160 + (ex + 7) * 4
            if entity_ptr != 0xA380 + slot * 4 or cache_ptr != 0xB000 + slot * 128 or fb_ptr != expected_fb:
                raise ValueError(f"runtime cache proof: gate {gate} association differs")
    return (
        f"runtime snapshot: {entity_count} emitted cache records and 20 association records exact "
        f"({12 - entity_count} unused cache slots)"
    )


main = ROOT / "src" / "main.s"
screen = ROOT / "build" / "ladybug_screen.inc"
MASK_LUT = bytes_after(main, "object_mask_lut", 16)
LUTS = {
    name: bytes_after(main, f"object_{name}_lut", 16)
    for name in ("red", "yellow", "blue", "skull")
}
MASKS = bytes_after(screen, "object_masks", 12 * 64)
source = main.read_text(encoding="utf-8")
for required in (
    "OBJ_CACHE_BASE", "OBJ_CACHE_CURSOR", "OBJ_CACHE_LUT", "OBJ_CACHE_REMAIN",
    "OBJ_CACHE_RUN_LENGTH equ $007A", "cache_entity_overflow", "suba    #4",
    "replay_gate_entity_overlay",
):
    if required not in source:
        raise SystemExit(f"gate cache proof: missing exact sparse-cache guard {required}")
if "OBJ_CACHE_RUN_LENGTH equ $0048" in source or "OBJ_ACCENT" in source[source.index("\ncache_entity_overlay"):source.index("\nbonus_color_tick")]:
    raise SystemExit("gate cache proof: cache scratch overlaps entity work or accent state")
draw_entities = source[source.index("\ndraw_entities\n"):source.index("\nerase_entity_footprints\n")]
gate_lists = source[source.index("\nbuild_gate_entity_lists\n"):source.index("\ndraw_gate_entities\n")]
if "addd    #128" not in draw_entities or gate_lists.count("lslb") < 7:
    raise SystemExit("gate cache proof: cache stride or association pointer is not slot*128")
cache_bases = [0xB000 + slot * 0x80 for slot in range(12)]
if cache_bases[-1] != 0xB580 or cache_bases[0] != 0xB000:
    raise SystemExit("gate cache proof: cache base arithmetic changed")

patterns = [
    bytearray((index * 17 + 3) & 255 for index in range(16 * 160)),
    bytearray((index * 37 + 19) & 255 for index in range(16 * 160)),
    bytearray(([0x55, 0xAA] * (16 * 80))),
]
cases = 0
largest = 0
for variant in range(12):
    mask = MASKS[variant * 64 : (variant + 1) * 64]
    for lut in LUTS.values():
        cache = sparse_builder(mask, lut)
        largest = max(largest, len(cache))
        for original_destination in patterns:
            expected = original_renderer(mask, lut, original_destination)
            for replay_destination in patterns:
                # Gate pixels must not influence opaque source pixels, while
                # preserved source pixels must retain the replay destination.
                actual = sparse_replay(cache, replay_destination)
                expected_replay = original_renderer(mask, lut, replay_destination)
                if actual != expected_replay:
                    mismatch = next(
                        index for index, (left, right) in enumerate(zip(actual, expected_replay))
                        if left != right
                    )
                    raise SystemExit(
                        f"gate cache proof: sparse replay diverged variant={variant} "
                        f"lut={lut.hex()} destination={mismatch} "
                        f"actual={actual[mismatch]:02x} expected={expected_replay[mismatch]:02x}"
                    )
                if expected == actual and original_destination != replay_destination:
                    raise SystemExit("gate cache proof: patterned-destination coverage failed")
                cases += 1

# Mutation proof: corrupting a stored opaque value must change a replay result.
cache = bytearray(sparse_builder(MASKS[:64], LUTS["red"]))
cache[-1] ^= 1
if sparse_replay(cache, patterns[1]) == original_renderer(MASKS[:64], LUTS["red"], patterns[1]):
    raise SystemExit("gate cache proof: mutation self-test did not fail")
print(
    f"gate cache proof: {cases} exact variant/LUT/pattern cases pass; "
    f"largest record {largest}/128 bytes; cache bases "
    + ",".join(f"{base:04X}" for base in cache_bases)
)
print("gate cache proof: " + runtime_snapshot_proof(MASKS, LUTS))
