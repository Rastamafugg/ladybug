#!/usr/bin/env python3
"""Build indexed sparse 4bpp actor streams and a candidate GMC loader layout."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from build_screen import (
    compile_attract_extra_enemy_sprites,
    compile_enemy_sprites,
    compile_player_sprites,
    compile_screen,
)


PAGE_BYTES = 0x2000
CART_BANK_BYTES = 0x4000
CART_CPU_BASE = 0xC000
CART_READABLE_BYTES = 0x3E00
BOOT_OVERFLOW_START = 0x0800
BANK2_PAYLOAD_START = 0x0020
WINDOW_BASE = 0xA000
ENEMY_PAGE_BASE = 0x35
ENEMY_PAGE_COUNT = 3
PLAYER_PAGE_BASE = 0x39
PLAYER_PAGE_COUNT = 1
ENEMY_RUNTIME_OFFSET = 0x0800
ENEMY_RUNTIME_RESERVED = 0x1000
SIGNATURE_OFFSET = 0x0010
PEN_MAP = (0x0, 0xC, 0x5, 0x2)
EXPECTED_ENEMY_BYTES = 23_005
EXPECTED_PLAYER_BYTES = 2_294
EXPECTED_GATE_BYTES = 832
EXPECTED_PRESENTATION_BYTES = 896
# Indexes remain at the start of their already-loaded sparse pages.  The
# former low-RAM mirrors overlapped the relocated GMC loader as that loader
# grew to carry the generated perimeter reset.
SPARSE_INDEX_ADDRESS = WINDOW_BASE
LOW_RAM_DESTINATION_PAGE = 0xFF
BOOT_OVERFLOW_PROOF_ADDRESS = 0x06B0
BOOT_OVERFLOW_PROOF = bytes((0xB0, 0x0F))
GATE_PAYLOAD_ADDRESS = WINDOW_BASE + EXPECTED_PLAYER_BYTES
PRESENTATION_PAYLOAD_ADDRESS = GATE_PAYLOAD_ADDRESS + EXPECTED_GATE_BYTES
PERIMETER_RESET_PAGE = 0x20
PERIMETER_RESET_ADDRESS = WINDOW_BASE
PERIMETER_RESET_HELPER_ADDRESS = 0x06B2
PERIMETER_RESET_HELPER_LIMIT = 0x0800


@dataclass(frozen=True)
class TargetChunk:
    name: str
    data: bytes
    payload_offset: int
    page: int
    address: int


@dataclass(frozen=True)
class SourceInterval:
    bank: int
    start: int
    end: int


@dataclass(frozen=True)
class CopySegment:
    bank: int
    source_offset: int
    destination_page: int
    destination_address: int
    count: int
    target: str
    target_offset: int

    @property
    def source_address(self) -> int:
        return CART_CPU_BASE + self.source_offset


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sprites", type=Path, required=True)
    parser.add_argument("--enemy-runtime", type=Path, required=True)
    parser.add_argument("--enemy-output", type=Path, required=True)
    parser.add_argument("--player-output", type=Path, required=True)
    parser.add_argument("--gate-input", type=Path, required=True)
    parser.add_argument("--presentation-input", type=Path, required=True)
    parser.add_argument("--perimeter-map", type=Path, required=True)
    parser.add_argument("--perimeter-maze", type=Path, required=True)
    parser.add_argument("--perimeter-chars", type=Path, required=True)
    parser.add_argument("--perimeter-reset-output", type=Path, required=True)
    parser.add_argument("--perimeter-helper", type=Path, required=True)
    parser.add_argument("--presentation-cold", type=Path, required=True)
    parser.add_argument("--actor-records", type=Path, required=True)
    parser.add_argument("--actor-underlays", type=Path, required=True)
    parser.add_argument("--presentation-module", type=Path, required=True)
    parser.add_argument("--bank2-output", type=Path, required=True)
    parser.add_argument("--bank3-output", type=Path, required=True)
    parser.add_argument("--bank0-output", type=Path, required=True)
    parser.add_argument("--loader-output", type=Path, required=True)
    parser.add_argument("--manifest-output", type=Path, required=True)
    return parser.parse_args()


def expand_native_frame(frame: bytes) -> bytes:
    """Expand a packed 2bpp 16x16 frame to native 4bpp bytes."""
    if len(frame) != 64:
        raise ValueError(f"packed frame is {len(frame)} bytes; expected 64")
    native = bytearray()
    for value in frame:
        pixels = (
            (value >> 6) & 0x03,
            (value >> 4) & 0x03,
            (value >> 2) & 0x03,
            value & 0x03,
        )
        native.extend((
            (PEN_MAP[pixels[0]] << 4) | PEN_MAP[pixels[1]],
            (PEN_MAP[pixels[2]] << 4) | PEN_MAP[pixels[3]],
        ))
    return bytes(native)


def encode_sparse_frame(frame: bytes) -> bytes:
    """Encode one frame as shared framebuffer/stage destination deltas."""
    native = expand_native_frame(frame)
    stream = bytearray()
    framebuffer_cursor = 0
    stage_cursor = 0
    for row_index in range(16):
        row = native[row_index * 8:(row_index + 1) * 8]
        column = 0
        while column < 8:
            value = row[column]
            if value == 0:
                column += 1
                continue
            opaque = bool(value & 0xF0) and bool(value & 0x0F)
            start = column
            values = bytearray()
            while column < 8:
                value = row[column]
                value_opaque = bool(value & 0xF0) and bool(value & 0x0F)
                if value == 0 or value_opaque != opaque:
                    break
                values.append(value)
                column += 1
            framebuffer_target = row_index * 160 + start
            stage_target = row_index * 8 + start
            framebuffer_delta = framebuffer_target - framebuffer_cursor
            stage_delta = stage_target - stage_cursor
            if (
                framebuffer_delta < 0 or stage_delta < 0 or
                framebuffer_delta > 0xFFFF or stage_delta > 0xFF
            ):
                raise ValueError("sparse destination delta exceeds its encoding")
            shared_delta = (
                (framebuffer_delta < 0x80 and stage_delta == framebuffer_delta) or
                (
                    152 <= framebuffer_delta <= 167 and
                    stage_delta == framebuffer_delta - 152
                )
            )
            if shared_delta:
                stream.append(framebuffer_delta)
            else:
                stream.extend((
                    0xFF,
                    framebuffer_delta >> 8,
                    framebuffer_delta & 0xFF,
                    stage_delta,
                ))
            stream.append(len(values) | (0 if opaque else 0x80))
            if opaque:
                stream.extend(values)
            else:
                for value in values:
                    mask = 0
                    if not value & 0xF0:
                        mask |= 0xF0
                    if not value & 0x0F:
                        mask |= 0x0F
                    stream.extend((mask, value))
            framebuffer_cursor = framebuffer_target + len(values)
            stage_cursor = stage_target + len(values)
    stream.extend((0xFF, 0, 0))
    return bytes(stream)


def pack_indexed_frames(
        frames: list[bytes], page_base: int, page_count: int
) -> tuple[bytes, list[dict[str, int]], int]:
    """Pack an index followed by streams, padding before page crossings."""
    index_bytes = len(frames) * 3
    payload = bytearray(b"\x00" * index_bytes)
    index: list[dict[str, int]] = []
    padding = 0
    for frame_number, packed_frame in enumerate(frames):
        stream = encode_sparse_frame(packed_frame)
        page_offset = len(payload) % PAGE_BYTES
        if page_offset + len(stream) > PAGE_BYTES:
            pad = PAGE_BYTES - page_offset
            payload.extend(b"\xFF" * pad)
            padding += pad
        offset = len(payload)
        page = page_base + offset // PAGE_BYTES
        address = WINDOW_BASE + offset % PAGE_BYTES
        if page >= page_base + page_count:
            raise ValueError(
                f"frame {frame_number} exceeds physical pages "
                f"${page_base:02X}-${page_base + page_count - 1:02X}"
            )
        entry = bytes((page, address >> 8, address & 0xFF))
        payload[frame_number * 3:frame_number * 3 + 3] = entry
        index.append({
            "frame": frame_number,
            "page": page,
            "address": address,
            "length": len(stream),
            "payload_offset": offset,
        })
        payload.extend(stream)
    return bytes(payload), index, padding


def target_chunks(
    name: str, payload: bytes, page_base: int, address: int = WINDOW_BASE
) -> list[TargetChunk]:
    chunks = []
    payload_offset = 0
    current_page = page_base
    current_address = address
    while payload_offset < len(payload):
        count = min(
            len(payload) - payload_offset,
            WINDOW_BASE + PAGE_BYTES - current_address,
        )
        part = payload[payload_offset:payload_offset + count]
        chunks.append(TargetChunk(
            name=name,
            data=part,
            payload_offset=payload_offset,
            page=current_page,
            address=current_address,
        ))
        payload_offset += count
        current_page += 1
        current_address = WINDOW_BASE
    return chunks


def perimeter_coordinates(box: int) -> tuple[int, int]:
    """Match main.s perimeter_box_coordinates for the complete 92-box ring."""
    if not 0 <= box < 92:
        raise ValueError("perimeter box is outside 0..91")
    if box < 12:
        return box + 12, 0
    if box < 35:
        return 23, box - 11
    if box < 58:
        return 22 - (box - 35), 23
    if box < 80:
        return 0, 22 - (box - 58)
    return box - 80, 0


def compile_perimeter_reset_payload(
        screen_map: list[int], tiles: list[bytes]
) -> bytes:
    """Generate the independent oracle for the boot-synthesized reset program."""
    patch: dict[int, int] = {}
    for box in range(92):
        cell_x, cell_y = perimeter_coordinates(box)
        tile = tiles[screen_map[cell_y * 40 + cell_x + 8]]
        # Map rows advance by five pixels. Rows 5-7 are obscured by the next
        # authored map row except at the bottom edge.
        for row in range(8 if cell_y == 23 else 5):
            offset = (cell_y * 5 + row) * 160 + (cell_x + 8) * 4
            for column, value in enumerate(tile[row * 4:(row + 1) * 4]):
                # The authored Green ring maps pen 6 to pen 5. Only bytes
                # containing pen 6 change when the reset publishes White.
                if value >> 4 == 6 or value & 0x0F == 6:
                    patch[0x2000 + offset + column] = value
    if not patch:
        raise ValueError("perimeter reset patch is empty")
    payload = bytearray()
    for address, value in patch.items():
        payload.extend((0x86, value, 0xB7, address >> 8, address & 0xFF))
    payload.append(0x39)       # RTS to the low-RAM PAR5-restoring gateway.
    if len(payload) > PAGE_BYTES:
        raise ValueError(
            f"perimeter reset payload is {len(payload)} bytes; exceeds one page"
        )
    return bytes(payload)


def pack_candidate_banks(
        enemy_payload: bytes, player_payload: bytes, gate_payload: bytes,
        presentation_payload: bytes,
        enemy_runtime: bytes, presentation_cold: bytes = b"",
        presentation_module: bytes = b"", perimeter_payload: bytes = b"",
        perimeter_helper: bytes = b"", actor_records: bytes = b"",
        actor_underlays: bytes = b""
) -> tuple[bytes, bytes, bytes, list[CopySegment]]:
    """Place target bytes in CPU-readable GMC intervals and build copy records."""
    if len(enemy_runtime) > ENEMY_RUNTIME_RESERVED:
        raise ValueError(
            f"enemy runtime is {len(enemy_runtime)} bytes; "
            f"reserved size is {ENEMY_RUNTIME_RESERVED}"
        )

    banks = {
        0: bytearray(b"\xFF" * CART_BANK_BYTES),
        2: bytearray(b"\xA2" * CART_BANK_BYTES),
        3: bytearray(b"\xA3" * CART_BANK_BYTES),
    }
    banks[2][SIGNATURE_OFFSET:SIGNATURE_OFFSET + 2] = bytes((0xB2, 0x02))
    banks[3][SIGNATURE_OFFSET:SIGNATURE_OFFSET + 2] = bytes((0xB3, 0x03))
    runtime_end = ENEMY_RUNTIME_OFFSET + len(enemy_runtime)
    banks[3][ENEMY_RUNTIME_OFFSET:runtime_end] = enemy_runtime
    helper_source_offset = BOOT_OVERFLOW_START + len(BOOT_OVERFLOW_PROOF)
    helper_source_end = helper_source_offset + len(perimeter_helper)
    if helper_source_end > CART_READABLE_BYTES:
        raise ValueError("perimeter reset payload exceeds bank-0 overflow source")
    helper_end = PERIMETER_RESET_HELPER_ADDRESS + len(perimeter_helper)
    if helper_end > PERIMETER_RESET_HELPER_LIMIT:
        raise ValueError("perimeter helper exceeds $06B2-$07FF allocation")

    sources = [
        SourceInterval(2, BANK2_PAYLOAD_START, CART_READABLE_BYTES),
        SourceInterval(
            3,
            ENEMY_RUNTIME_OFFSET + ENEMY_RUNTIME_RESERVED,
            CART_READABLE_BYTES,
        ),
        SourceInterval(3, 0x0000, SIGNATURE_OFFSET),
        SourceInterval(3, SIGNATURE_OFFSET + 2, ENEMY_RUNTIME_OFFSET),
        SourceInterval(0, helper_source_end,
                       CART_READABLE_BYTES),
    ]
    targets = (
        target_chunks("enemy", enemy_payload, ENEMY_PAGE_BASE) +
        target_chunks("player", player_payload, PLAYER_PAGE_BASE) +
        target_chunks(
            "gate", gate_payload, PLAYER_PAGE_BASE, GATE_PAYLOAD_ADDRESS
        ) +
        target_chunks("presentation", presentation_payload, PLAYER_PAGE_BASE,
                      PRESENTATION_PAYLOAD_ADDRESS) +
        target_chunks("presentation_cold", presentation_cold, 0x3A,
                      WINDOW_BASE) +
        target_chunks("attract_actor_bundle", actor_underlays + actor_records,
                      0x23, 0xA000) +
        target_chunks("presentation_module", presentation_module, 0xFF,
                      0x1900)
    )

    banks[0][BOOT_OVERFLOW_START:
             BOOT_OVERFLOW_START + len(BOOT_OVERFLOW_PROOF)] = BOOT_OVERFLOW_PROOF
    banks[0][helper_source_offset:helper_source_end] = perimeter_helper
    segments: list[CopySegment] = [CopySegment(
        bank=0,
        source_offset=BOOT_OVERFLOW_START,
        destination_page=LOW_RAM_DESTINATION_PAGE,
        destination_address=BOOT_OVERFLOW_PROOF_ADDRESS,
        count=len(BOOT_OVERFLOW_PROOF),
        target="boot_overflow_proof",
        target_offset=0,
    ), CopySegment(
        bank=0,
        source_offset=helper_source_offset,
        destination_page=LOW_RAM_DESTINATION_PAGE,
        destination_address=PERIMETER_RESET_HELPER_ADDRESS,
        count=len(perimeter_helper),
        target="perimeter_reset_helper",
        target_offset=0,
    )]
    source_index = 0
    source_cursor = sources[0].start
    for target in targets:
        target_cursor = 0
        while target_cursor < len(target.data):
            if source_index >= len(sources):
                raise ValueError("sparse payloads exceed CPU-readable GMC capacity")
            source = sources[source_index]
            available = source.end - source_cursor
            if available == 0:
                source_index += 1
                if source_index < len(sources):
                    source_cursor = sources[source_index].start
                continue
            count = min(available, len(target.data) - target_cursor)
            banks[source.bank][source_cursor:source_cursor + count] = (
                target.data[target_cursor:target_cursor + count]
            )
            segments.append(CopySegment(
                bank=source.bank,
                source_offset=source_cursor,
                destination_page=target.page,
                destination_address=target.address + target_cursor,
                count=count,
                target=target.name,
                target_offset=target.payload_offset + target_cursor,
            ))
            source_cursor += count
            target_cursor += count

    for segment in segments:
        if segment.source_offset + segment.count > CART_READABLE_BYTES:
            raise ValueError("loader segment enters forced-RAM/I/O cart offsets")
        if segment.destination_page == LOW_RAM_DESTINATION_PAGE:
            if segment.target == "presentation_module":
                if not (
                    0x1900 <= segment.destination_address and
                    segment.destination_address + segment.count <= 0x1E40
                ):
                    raise ValueError("presentation module exceeds low-RAM reservation")
            elif not (
                BOOT_OVERFLOW_PROOF_ADDRESS <= segment.destination_address and
                segment.destination_address + segment.count <= 0x0800
            ):
                raise ValueError("low-RAM loader segment exceeds overflow destination")
        elif not (
            WINDOW_BASE <= segment.destination_address and
            segment.destination_address + segment.count <= WINDOW_BASE + PAGE_BYTES
        ):
            raise ValueError("loader segment crosses its PAR5 destination page")
        if segment.bank == 0 and segment.source_offset < BOOT_OVERFLOW_START:
            raise ValueError("bank-0 loader segment overlaps bootstrap reservation")
        if (
            segment.bank == 3 and
            segment.source_offset < ENEMY_RUNTIME_OFFSET + ENEMY_RUNTIME_RESERVED and
            segment.source_offset + segment.count > ENEMY_RUNTIME_OFFSET
        ):
            raise ValueError("loader segment overlaps the bank-3 runtime reservation")
        if (
            segment.source_offset <= SIGNATURE_OFFSET + 1 and
            segment.source_offset + segment.count > SIGNATURE_OFFSET
        ):
            raise ValueError("loader segment overlaps a bank signature")

    return bytes(banks[0]), bytes(banks[2]), bytes(banks[3]), segments


def write_loader_include(path: Path, segments: list[CopySegment]) -> None:
    lines = [
        "; Generated by scripts/build_sparse_sprites.py; do not edit.",
        f"SPARSE_ENEMY_PAYLOAD_PAGE equ ${ENEMY_PAGE_BASE:02X}",
        f"SPARSE_PLAYER_PAYLOAD_PAGE equ ${PLAYER_PAGE_BASE:02X}",
        f"GATE_TRANSITION_PAYLOAD_ADDR equ ${GATE_PAYLOAD_ADDRESS:04X}",
        f"PRESENTATION_PAYLOAD_ADDR equ ${PRESENTATION_PAYLOAD_ADDRESS:04X}",
        f"SPARSE_ENEMY_INDEX_ADDR equ ${SPARSE_INDEX_ADDRESS:04X}",
        f"SPARSE_PLAYER_INDEX_ADDR equ ${SPARSE_INDEX_ADDRESS:04X}",
        "SPARSE_ENEMY_INDEX_BYTES equ 390",
        "SPARSE_PLAYER_INDEX_BYTES equ 48",
        "SPARSE_COPY_SEGMENT_BYTES equ 8",
        f"SPARSE_COPY_SEGMENT_COUNT equ {len(segments)}",
        "",
        "; bank, destination page, source CPU address, destination window, count",
        "sparse_copy_table",
    ]
    for segment in segments:
        lines.extend((
            f"        ; {segment.target}+${segment.target_offset:04X}",
            f"        fcb     ${segment.bank:02X},${segment.destination_page:02X}",
            f"        fdb     ${segment.source_address:04X},"
            f"${segment.destination_address:04X},${segment.count:04X}",
        ))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="ascii")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    args = parse_args()
    enemy_frames = compile_enemy_sprites(args.sprites)
    enemy_frames.extend(compile_attract_extra_enemy_sprites(args.sprites))
    player_frames = compile_player_sprites(args.sprites)
    enemy_payload, enemy_index, enemy_padding = pack_indexed_frames(
        enemy_frames, ENEMY_PAGE_BASE, ENEMY_PAGE_COUNT
    )
    player_payload, player_index, player_padding = pack_indexed_frames(
        player_frames, PLAYER_PAGE_BASE, PLAYER_PAGE_COUNT
    )
    gate_payload = args.gate_input.read_bytes()
    presentation_payload = args.presentation_input.read_bytes()
    screen_map, tiles, *_ = compile_screen(
        args.perimeter_map, args.perimeter_maze, args.perimeter_chars,
        args.sprites,
    )
    perimeter_payload = compile_perimeter_reset_payload(screen_map, tiles)
    perimeter_helper = args.perimeter_helper.read_bytes()
    if len(enemy_payload) != EXPECTED_ENEMY_BYTES:
        raise SystemExit(
            f"sparse: enemy payload is {len(enemy_payload)} bytes; "
            f"review expected {EXPECTED_ENEMY_BYTES}"
        )
    if len(player_payload) != EXPECTED_PLAYER_BYTES:
        raise SystemExit(
            f"sparse: player payload is {len(player_payload)} bytes; "
            f"review expected {EXPECTED_PLAYER_BYTES}"
        )
    if len(gate_payload) != EXPECTED_GATE_BYTES:
        raise SystemExit(
            f"sparse: gate payload is {len(gate_payload)} bytes; "
            f"review expected {EXPECTED_GATE_BYTES}"
        )
    if len(presentation_payload) != EXPECTED_PRESENTATION_BYTES:
        raise SystemExit(
            f"sparse: presentation payload is {len(presentation_payload)} bytes; "
            f"review expected {EXPECTED_PRESENTATION_BYTES}"
        )

    enemy_runtime = args.enemy_runtime.read_bytes()
    presentation_cold = args.presentation_cold.read_bytes()
    actor_records = args.actor_records.read_bytes()
    actor_underlays = args.actor_underlays.read_bytes()
    presentation_module = args.presentation_module.read_bytes()
    bank0, bank2, bank3, segments = pack_candidate_banks(
        enemy_payload, player_payload, gate_payload, presentation_payload,
        enemy_runtime, presentation_cold, presentation_module,
        perimeter_payload, perimeter_helper, actor_records, actor_underlays
    )
    outputs = (
        (args.enemy_output, enemy_payload),
        (args.player_output, player_payload),
        (args.perimeter_reset_output, perimeter_payload),
        (args.bank0_output, bank0),
        (args.bank2_output, bank2),
        (args.bank3_output, bank3),
    )
    for path, data in outputs:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    write_loader_include(args.loader_output, segments)

    proof_bytes = len(BOOT_OVERFLOW_PROOF)
    used_payload_source_bytes = sum(
        segment.count for segment in segments
        if segment.target != "boot_overflow_proof"
    )
    bank0_used_bytes = sum(
        segment.count for segment in segments if segment.bank == 0
    )
    usable_expansion_bytes = (
        (CART_READABLE_BYTES - BANK2_PAYLOAD_START) +
        (CART_READABLE_BYTES - ENEMY_RUNTIME_OFFSET - ENEMY_RUNTIME_RESERVED) +
        SIGNATURE_OFFSET + (ENEMY_RUNTIME_OFFSET - SIGNATURE_OFFSET - 2) +
        (CART_READABLE_BYTES - BOOT_OVERFLOW_START)
    )
    manifest = {
        "format": {
            "end": [0xFF, 0, 0],
            "shared_delta": "fb delta; values 128..167 map to stage delta minus 152",
            "extended_delta": [0xFF, "fb_delta_hi", "fb_delta_lo", "stage_delta"],
            "opaque": ["destination_delta", "length", "pixels"],
            "partial": ["destination_delta", "0x80|length", "mask_pixel_pairs"],
            "index_entry": ["physical_page", "window_address_hi", "window_address_lo"],
            "enemy_index_source": SPARSE_INDEX_ADDRESS,
            "player_index_source": SPARSE_INDEX_ADDRESS,
            "window_base": WINDOW_BASE,
            "page_bytes": PAGE_BYTES,
        },
        "enemy": {
            "frames": len(enemy_frames),
            "bytes": len(enemy_payload),
            "index_bytes": len(enemy_frames) * 3,
            "padding_bytes": enemy_padding,
            "page_base": ENEMY_PAGE_BASE,
            "page_count": ENEMY_PAGE_COUNT,
            "sha256": digest(enemy_payload),
            "index": enemy_index,
        },
        "player": {
            "frames": len(player_frames),
            "bytes": len(player_payload),
            "index_bytes": len(player_frames) * 3,
            "padding_bytes": player_padding,
            "page_base": PLAYER_PAGE_BASE,
            "page_count": PLAYER_PAGE_COUNT,
            "sha256": digest(player_payload),
            "index": player_index,
        },
        "gate": {
            "streams": 6,
            "bytes": len(gate_payload),
            "page": PLAYER_PAGE_BASE,
            "address": GATE_PAYLOAD_ADDRESS,
            "sha256": digest(gate_payload),
        },
        "presentation": {
            "bytes": len(presentation_payload),
            "page": PLAYER_PAGE_BASE,
            "address": PRESENTATION_PAYLOAD_ADDRESS,
            "sha256": digest(presentation_payload),
        },
        "perimeter_reset": {
            "bytes": len(perimeter_payload),
            "page": PERIMETER_RESET_PAGE,
            "address": PERIMETER_RESET_ADDRESS,
            "boot_synthesized": True,
            "source_bytes": 0,
            "sha256": digest(perimeter_payload),
            "helper_address": PERIMETER_RESET_HELPER_ADDRESS,
            "helper_bytes": len(perimeter_helper),
            "helper_sha256": digest(perimeter_helper),
            "semantic": "boot-synthesized native $2000-relative stores matching complete Green-to-White 92-box reset",
        },
        "presentation_cold": {
            "bytes": len(presentation_cold),
            "page": 0x3A,
            "page_count": 4,
            "address": WINDOW_BASE,
            "sha256": digest(presentation_cold),
        },
        "presentation_module": {
            "bytes": len(presentation_module),
            "page": LOW_RAM_DESTINATION_PAGE,
            "address": 0x1900,
            "sha256": digest(presentation_module),
        },
        "gmc": {
            "readable_bytes_per_bank": CART_READABLE_BYTES,
            "boot_overflow_start": BOOT_OVERFLOW_START,
            "boot_overflow_end": CART_READABLE_BYTES,
            "boot_overflow_proof_address": BOOT_OVERFLOW_PROOF_ADDRESS,
            "boot_overflow_proof_bytes": proof_bytes,
            "boot_overflow_used_bytes": bank0_used_bytes,
            "boot_overflow_spare_bytes": (
                CART_READABLE_BYTES - BOOT_OVERFLOW_START - bank0_used_bytes
            ),
            "enemy_runtime_reserved": ENEMY_RUNTIME_RESERVED,
            "payload_bytes": used_payload_source_bytes,
            "source_bytes_including_proof": used_payload_source_bytes + proof_bytes,
            "usable_source_bytes": usable_expansion_bytes,
            "spare_bytes": (
                usable_expansion_bytes - used_payload_source_bytes - proof_bytes
            ),
            "bank0_sha256": digest(bank0),
            "bank2_sha256": digest(bank2),
            "bank3_sha256": digest(bank3),
            "segments": [
                {
                    "bank": segment.bank,
                    "source_offset": segment.source_offset,
                    "source_address": segment.source_address,
                    "destination_page": segment.destination_page,
                    "destination_address": segment.destination_address,
                    "count": segment.count,
                    "target": segment.target,
                    "target_offset": segment.target_offset,
                }
                for segment in segments
            ],
        },
    }
    args.manifest_output.parent.mkdir(parents=True, exist_ok=True)
    args.manifest_output.write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="ascii"
    )
    print(
        f"sparse: enemy {len(enemy_payload)}/{ENEMY_PAGE_COUNT * PAGE_BYTES}, "
        f"player {len(player_payload)}/{PLAYER_PAGE_COUNT * PAGE_BYTES}, "
        f"gate {len(gate_payload)} bytes, "
        f"presentation {len(presentation_payload)} bytes, "
        f"perimeter reset {len(perimeter_payload)} bytes, "
        f"{len(segments)} loader segments, "
        f"{manifest['gmc']['spare_bytes']} CPU-readable GMC bytes spare"
    )


if __name__ == "__main__":
    main()
