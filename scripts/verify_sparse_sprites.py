#!/usr/bin/env python3
"""Independently verify sparse sprite payloads and candidate GMC copy records."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from build_screen import (
    compile_attract_extra_enemy_sprites,
    compile_enemy_sprites,
    compile_player_sprites,
)


PAGE_BYTES = 0x2000
WINDOW_BASE = 0xA000
CART_BANK_BYTES = 0x4000
CART_READABLE_BYTES = 0x3E00
BOOT_OVERFLOW_START = 0x0800
BANK2_PAYLOAD_START = 0x0020
LOW_RAM_DESTINATION_PAGE = 0xFF
BOOT_OVERFLOW_PROOF_ADDRESS = 0x06B0
BOOT_OVERFLOW_PROOF = bytes((0xB0, 0x0F))
PEN_MAP = (0x0, 0xC, 0x5, 0x2)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sprites", type=Path, required=True)
    parser.add_argument("--enemy-runtime", type=Path, required=True)
    parser.add_argument("--enemy-payload", type=Path, required=True)
    parser.add_argument("--player-payload", type=Path, required=True)
    parser.add_argument("--gate-payload", type=Path, required=True)
    parser.add_argument("--presentation-payload", type=Path, required=True)
    parser.add_argument("--perimeter-reset-payload", type=Path, required=True)
    parser.add_argument("--perimeter-helper", type=Path, required=True)
    parser.add_argument("--presentation-cold", type=Path, required=True)
    parser.add_argument("--actor-records", type=Path, required=True)
    parser.add_argument("--actor-underlays", type=Path, required=True)
    parser.add_argument("--presentation-module", type=Path, required=True)
    parser.add_argument("--bank0", type=Path, required=True)
    parser.add_argument("--bank2", type=Path, required=True)
    parser.add_argument("--bank3", type=Path, required=True)
    parser.add_argument("--loader", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    return parser.parse_args()


def expected_native(frame: bytes) -> bytes:
    output = bytearray()
    for value in frame:
        pixels = (
            (value >> 6) & 3,
            (value >> 4) & 3,
            (value >> 2) & 3,
            value & 3,
        )
        output.extend((
            (PEN_MAP[pixels[0]] << 4) | PEN_MAP[pixels[1]],
            (PEN_MAP[pixels[2]] << 4) | PEN_MAP[pixels[3]],
        ))
    return bytes(output)


def decode_payload(
        payload: bytes, frames: list[bytes], page_base: int
) -> list[tuple[int, int]]:
    """Decode every indexed stream and return its [start,end) payload range."""
    index_bytes = len(frames) * 3
    if len(payload) < index_bytes:
        raise ValueError("payload is shorter than its frame index")
    ranges = []
    for frame_number, packed_frame in enumerate(frames):
        entry = payload[frame_number * 3:frame_number * 3 + 3]
        page, address = entry[0], (entry[1] << 8) | entry[2]
        if not WINDOW_BASE <= address < WINDOW_BASE + PAGE_BYTES:
            raise ValueError(f"frame {frame_number} has invalid window address")
        offset = (page - page_base) * PAGE_BYTES + address - WINDOW_BASE
        if offset < index_bytes or offset >= len(payload):
            raise ValueError(f"frame {frame_number} points outside its payload")
        cursor = offset
        decoded = bytearray(128)
        background = bytearray(
            ((frame_number * 37 + index * 73 + 0x5A) & 0xFF)
            for index in range(128)
        )
        blended = bytearray(background)
        framebuffer_cursor = 0
        stage_cursor = 0
        occupied = bytearray(128)
        while True:
            if cursor >= len(payload):
                raise ValueError(f"frame {frame_number} stream is truncated")
            token = payload[cursor]
            cursor += 1
            if token == 0xFF:
                if cursor + 2 > len(payload):
                    raise ValueError(f"frame {frame_number} delta escape is truncated")
                framebuffer_delta = (payload[cursor] << 8) | payload[cursor + 1]
                cursor += 2
                if framebuffer_delta == 0:
                    break
                if cursor >= len(payload):
                    raise ValueError(f"frame {frame_number} stage delta is truncated")
                stage_delta = payload[cursor]
                cursor += 1
            else:
                framebuffer_delta = token
                if token < 0x80:
                    stage_delta = token
                elif token <= 167:
                    stage_delta = token - 152
                else:
                    raise ValueError(
                        f"frame {frame_number} has invalid shared delta {token}"
                    )
            framebuffer_cursor += framebuffer_delta
            stage_cursor += stage_delta
            row, column = divmod(stage_cursor, 8)
            if (
                row >= 16 or
                framebuffer_cursor != row * 160 + column
            ):
                raise ValueError(
                    f"frame {frame_number} framebuffer/stage destinations diverge"
                )
            if cursor >= len(payload):
                raise ValueError(f"frame {frame_number} command is truncated")
            control = payload[cursor]
            cursor += 1
            partial = bool(control & 0x80)
            length = control & 0x7F
            if length == 0 or column + length > 8:
                raise ValueError(f"frame {frame_number} has invalid command length")
            for target in range(stage_cursor, stage_cursor + length):
                if occupied[target]:
                    raise ValueError(f"frame {frame_number} writes a byte twice")
                occupied[target] = 1
                if partial:
                    if cursor + 2 > len(payload):
                        raise ValueError(
                            f"frame {frame_number} partial command is truncated"
                        )
                    mask, pixel = payload[cursor:cursor + 2]
                    cursor += 2
                    if mask not in (0x0F, 0xF0):
                        raise ValueError(
                            f"frame {frame_number} has invalid partial mask"
                        )
                    if pixel & mask:
                        raise ValueError(
                            f"frame {frame_number} mask does not cover zero nibble"
                        )
                    decoded[target] = pixel
                    blended[target] = (blended[target] & mask) | pixel
                else:
                    if cursor >= len(payload):
                        raise ValueError(
                            f"frame {frame_number} opaque command is truncated"
                        )
                    pixel = payload[cursor]
                    cursor += 1
                    if not pixel & 0xF0 or not pixel & 0x0F:
                        raise ValueError(
                            f"frame {frame_number} opaque byte is transparent"
                        )
                    decoded[target] = pixel
                    blended[target] = pixel
            framebuffer_cursor += length
            stage_cursor += length
        native = expected_native(packed_frame)
        if decoded != native:
            raise ValueError(f"frame {frame_number} does not decode pixel-exactly")
        expected_blend = bytearray(background)
        for index, pixel in enumerate(native):
            mask = (0xF0 if not pixel & 0xF0 else 0) | (
                0x0F if not pixel & 0x0F else 0
            )
            expected_blend[index] = (expected_blend[index] & mask) | pixel
        if blended != expected_blend:
            raise ValueError(
                f"frame {frame_number} does not preserve transparent background nibbles"
            )
        if offset // PAGE_BYTES != (cursor - 1) // PAGE_BYTES:
            raise ValueError(f"frame {frame_number} crosses a physical page")
        ranges.append((offset, cursor))
    ordered = sorted(ranges)
    for previous, current in zip(ordered, ordered[1:]):
        if previous[1] > current[0]:
            raise ValueError("indexed frame streams overlap")
    return ranges


def parse_loader(path: Path) -> list[dict[str, int]]:
    records = []
    pending: tuple[int, int] | None = None
    for line in path.read_text(encoding="ascii").splitlines():
        match = re.match(r"\s*fcb\s+\$([0-9A-F]{2}),\$([0-9A-F]{2})$", line)
        if match:
            if pending is not None:
                raise ValueError("loader fcb record is missing its fdb")
            pending = tuple(int(value, 16) for value in match.groups())
            continue
        match = re.match(
            r"\s*fdb\s+\$([0-9A-F]{4}),\$([0-9A-F]{4}),\$([0-9A-F]{4})$",
            line,
        )
        if match:
            if pending is None:
                raise ValueError("loader fdb record has no bank/page header")
            source, destination, count = (
                int(value, 16) for value in match.groups()
            )
            records.append({
                "bank": pending[0],
                "destination_page": pending[1],
                "source_address": source,
                "destination_address": destination,
                "count": count,
            })
            pending = None
    if pending is not None:
        raise ValueError("loader ends with an incomplete record")
    return records


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    args = parse_args()
    enemy_frames = compile_enemy_sprites(args.sprites)
    enemy_frames.extend(compile_attract_extra_enemy_sprites(args.sprites))
    player_frames = compile_player_sprites(args.sprites)
    enemy_payload = args.enemy_payload.read_bytes()
    player_payload = args.player_payload.read_bytes()
    gate_payload = args.gate_payload.read_bytes()
    presentation_payload = args.presentation_payload.read_bytes()
    perimeter_reset_payload = args.perimeter_reset_payload.read_bytes()
    perimeter_helper = args.perimeter_helper.read_bytes()
    presentation_cold = args.presentation_cold.read_bytes()
    actor_records = args.actor_records.read_bytes()
    actor_underlays = args.actor_underlays.read_bytes()
    presentation_module = args.presentation_module.read_bytes()
    enemy_ranges = decode_payload(enemy_payload, enemy_frames, 0x35)
    player_ranges = decode_payload(player_payload, player_frames, 0x39)
    bank0 = args.bank0.read_bytes()
    bank2 = args.bank2.read_bytes()
    bank3 = args.bank3.read_bytes()
    if any(len(bank) != CART_BANK_BYTES for bank in (bank0, bank2, bank3)):
        raise SystemExit("sparse proof: candidate GMC banks are not 16 KiB")
    if any(value != 0xFF for value in bank0[:BOOT_OVERFLOW_START]):
        raise SystemExit("sparse proof: bank-0 template enters bootstrap reservation")
    if bank2[0x10:0x12] != bytes((0xB2, 0x02)):
        raise SystemExit("sparse proof: bank-2 signature changed")
    if bank3[0x10:0x12] != bytes((0xB3, 0x03)):
        raise SystemExit("sparse proof: bank-3 signature changed")
    runtime = args.enemy_runtime.read_bytes()
    if bank3[0x800:0x800 + len(runtime)] != runtime:
        raise SystemExit("sparse proof: candidate bank-3 runtime changed")

    manifest = json.loads(args.manifest.read_text(encoding="ascii"))
    if manifest["enemy"]["sha256"] != sha256(enemy_payload):
        raise SystemExit("sparse proof: enemy manifest hash mismatch")
    if manifest["player"]["sha256"] != sha256(player_payload):
        raise SystemExit("sparse proof: player manifest hash mismatch")
    if manifest["gate"]["sha256"] != sha256(gate_payload):
        raise SystemExit("sparse proof: gate manifest hash mismatch")
    if manifest["presentation"]["sha256"] != sha256(presentation_payload):
        raise SystemExit("sparse proof: presentation manifest hash mismatch")
    if manifest["presentation_cold"]["sha256"] != sha256(presentation_cold):
        raise SystemExit("sparse proof: presentation cold manifest hash mismatch")
    if manifest["presentation_module"]["sha256"] != sha256(presentation_module):
        raise SystemExit("sparse proof: presentation module manifest hash mismatch")
    if (
        manifest["perimeter_reset"]["page"] != 0x20 or
        manifest["perimeter_reset"]["address"] != WINDOW_BASE or
        not manifest["perimeter_reset"].get("boot_synthesized") or
        manifest["perimeter_reset"].get("source_bytes") != 0
    ):
        raise SystemExit("sparse proof: perimeter reset is not boot-synthesized at page $20")
    if manifest["gmc"]["bank0_sha256"] != sha256(bank0):
        raise SystemExit("sparse proof: bank-0 manifest hash mismatch")
    if manifest["gmc"]["bank2_sha256"] != sha256(bank2):
        raise SystemExit("sparse proof: bank-2 manifest hash mismatch")
    if manifest["gmc"]["bank3_sha256"] != sha256(bank3):
        raise SystemExit("sparse proof: bank-3 manifest hash mismatch")

    loader = parse_loader(args.loader)
    manifest_segments = manifest["gmc"]["segments"]
    if len(loader) != len(manifest_segments):
        raise SystemExit("sparse proof: loader and manifest segment counts differ")
    reconstructed = {
        "enemy": bytearray(len(enemy_payload)),
        "player": bytearray(len(player_payload)),
        "gate": bytearray(len(gate_payload)),
        "presentation": bytearray(len(presentation_payload)),
        "presentation_cold": bytearray(len(presentation_cold)),
        "presentation_module": bytearray(len(presentation_module)),
        "attract_actor_records": bytearray(len(actor_records)),
        "attract_actor_underlays": bytearray(len(actor_underlays)),
    }
    coverage = {
        "enemy": bytearray(len(enemy_payload)),
        "player": bytearray(len(player_payload)),
        "gate": bytearray(len(gate_payload)),
        "presentation": bytearray(len(presentation_payload)),
        "presentation_cold": bytearray(len(presentation_cold)),
        "presentation_module": bytearray(len(presentation_module)),
        "attract_actor_records": bytearray(len(actor_records)),
        "attract_actor_underlays": bytearray(len(actor_underlays)),
    }
    source_coverage = {
        0: bytearray(CART_READABLE_BYTES),
        2: bytearray(CART_READABLE_BYTES),
        3: bytearray(CART_READABLE_BYTES),
    }
    banks = {0: bank0, 2: bank2, 3: bank3}
    for loader_record, segment in zip(loader, manifest_segments):
        expected_record = {
            key: segment[key]
            for key in (
                "bank", "destination_page", "source_address",
                "destination_address", "count",
            )
        }
        if loader_record != expected_record:
            raise SystemExit("sparse proof: loader record differs from manifest")
        source_offset = segment["source_offset"]
        count = segment["count"]
        if segment["source_address"] != 0xC000 + source_offset:
            raise SystemExit("sparse proof: source CPU address mismatches bank offset")
        if source_offset + count > CART_READABLE_BYTES:
            raise SystemExit("sparse proof: segment enters forced-RAM/I/O offsets")
        if segment["destination_page"] == LOW_RAM_DESTINATION_PAGE:
            if segment["target"] == "presentation_module":
                if not (
                    0x1900 <= segment["destination_address"] and
                    segment["destination_address"] + count <= 0x1E40
                ):
                    raise SystemExit("sparse proof: presentation module is out of range")
            elif not (
                BOOT_OVERFLOW_PROOF_ADDRESS <= segment["destination_address"] and
                segment["destination_address"] + count <= 0x0800
            ):
                raise SystemExit("sparse proof: low-RAM destination is out of range")
        elif not (
            WINDOW_BASE <= segment["destination_address"] and
            segment["destination_address"] + count <= WINDOW_BASE + PAGE_BYTES
        ):
            raise SystemExit("sparse proof: destination segment crosses a PAR page")
        if segment["bank"] in (2, 3) and source_offset <= 0x11 and source_offset + count > 0x10:
            raise SystemExit("sparse proof: segment overlaps a bank signature")
        if segment["bank"] == 0 and source_offset < BOOT_OVERFLOW_START:
            raise SystemExit("sparse proof: segment overlaps bank-0 bootstrap reservation")
        if (
            segment["bank"] == 3 and
            source_offset < 0x1800 and source_offset + count > 0x0800
        ):
            raise SystemExit("sparse proof: segment overlaps bank-3 runtime reserve")
        if any(source_coverage[segment["bank"]][source_offset:source_offset + count]):
            raise SystemExit("sparse proof: loader source intervals overlap")
        source_coverage[segment["bank"]][source_offset:source_offset + count] = (
            b"\x01" * count
        )
        target = segment["target"]
        target_offset = segment["target_offset"]
        if target == "boot_overflow_proof":
            if (
                segment["destination_page"] != LOW_RAM_DESTINATION_PAGE or
                segment["destination_address"] != BOOT_OVERFLOW_PROOF_ADDRESS or
                target_offset != 0 or
                banks[segment["bank"]][source_offset:source_offset + count] != BOOT_OVERFLOW_PROOF
            ):
                raise SystemExit("sparse proof: bank-0 low-RAM proof differs")
            continue
        if target == "perimeter_reset_helper":
            if (
                segment["destination_page"] != LOW_RAM_DESTINATION_PAGE or
                segment["destination_address"] != manifest["perimeter_reset"]["helper_address"] or
                target_offset != 0 or
                banks[segment["bank"]][source_offset:source_offset + count] != perimeter_helper
            ):
                raise SystemExit("sparse proof: perimeter helper differs")
            continue
        if target == "enemy":
            target_page_base = 0x35
            target_address = WINDOW_BASE
        elif target == "player":
            target_page_base = 0x39
            target_address = WINDOW_BASE
        elif target == "gate":
            target_page_base = 0x39
            target_address = manifest["gate"]["address"]
        elif target == "presentation":
            target_page_base = 0x39
            target_address = manifest["presentation"]["address"]
        elif target == "presentation_cold":
            target_page_base = 0x3A
            target_address = manifest["presentation_cold"]["address"]
        elif target == "presentation_module":
            expected_page = LOW_RAM_DESTINATION_PAGE
            expected_address = manifest["presentation_module"]["address"] + target_offset
            source = banks[segment["bank"]][source_offset:source_offset + count]
            destination_end = target_offset + count
            if (
                segment["destination_page"] != expected_page or
                segment["destination_address"] != expected_address
            ):
                raise SystemExit("sparse proof: module destination does not match target offset")
            if destination_end > len(reconstructed[target]):
                raise SystemExit("sparse proof: module segment exceeds payload")
            if any(coverage[target][target_offset:destination_end]):
                raise SystemExit("sparse proof: module target coverage overlaps")
            reconstructed[target][target_offset:destination_end] = source
            coverage[target][target_offset:destination_end] = b"\x01" * count
            continue
        elif target == "attract_actor_records":
            target_page_base = 0x34
            target_address = 0xB200
        elif target == "attract_actor_underlays":
            target_page_base = 0x34
            target_address = 0xB000
        else:
            raise SystemExit(f"sparse proof: unknown loader target {target}")
        absolute_offset = target_address - WINDOW_BASE + target_offset
        expected_page = target_page_base + absolute_offset // PAGE_BYTES
        expected_address = WINDOW_BASE + absolute_offset % PAGE_BYTES
        if (
            segment["destination_page"] != expected_page or
            segment["destination_address"] != expected_address
        ):
            raise SystemExit(f"sparse proof: destination does not match target offset ({target}: {segment['destination_page']:02X}/{segment['destination_address']:04X} != {expected_page:02X}/{expected_address:04X})")
        source = banks[segment["bank"]][source_offset:source_offset + count]
        destination_end = target_offset + count
        if destination_end > len(reconstructed[target]):
            raise SystemExit("sparse proof: target segment exceeds payload")
        if any(coverage[target][target_offset:destination_end]):
            raise SystemExit("sparse proof: target segment coverage overlaps")
        reconstructed[target][target_offset:destination_end] = source
        coverage[target][target_offset:destination_end] = b"\x01" * count
    if (
        not all(coverage["enemy"]) or
        not all(coverage["player"]) or
        not all(coverage["gate"]) or
        not all(coverage["presentation"]) or
            not all(coverage["presentation_cold"]) or
        not all(coverage["presentation_module"])
    ):
        raise SystemExit("sparse proof: loader target coverage has gaps")
    if reconstructed["enemy"] != enemy_payload:
        raise SystemExit("sparse proof: loader does not reconstruct enemy payload")
    if reconstructed["player"] != player_payload:
        raise SystemExit("sparse proof: loader does not reconstruct player payload")
    if reconstructed["gate"] != gate_payload:
        raise SystemExit("sparse proof: loader does not reconstruct gate payload")
    if reconstructed["presentation"] != presentation_payload:
        raise SystemExit("sparse proof: loader does not reconstruct presentation payload")
    if reconstructed["presentation_cold"] != presentation_cold:
        raise SystemExit("sparse proof: loader does not reconstruct presentation cold data")
    if reconstructed["presentation_module"] != presentation_module:
        raise SystemExit("sparse proof: loader does not reconstruct presentation module")
    if reconstructed["attract_actor_records"] != actor_records:
        raise SystemExit("sparse proof: loader does not reconstruct actor records")
    if reconstructed["attract_actor_underlays"] != actor_underlays:
        raise SystemExit("sparse proof: loader does not reconstruct actor underlays")
    expected_usable = (
        (CART_READABLE_BYTES - BANK2_PAYLOAD_START) +
        (CART_READABLE_BYTES - 0x1800) + 0x10 + (0x0800 - 0x12) +
        (CART_READABLE_BYTES - BOOT_OVERFLOW_START)
    )
    if manifest["gmc"]["usable_source_bytes"] != expected_usable:
        raise SystemExit("sparse proof: usable GMC source capacity differs")
    expected_spare = (
        expected_usable - manifest["gmc"]["payload_bytes"] - len(BOOT_OVERFLOW_PROOF)
    )
    if manifest["gmc"]["spare_bytes"] != expected_spare:
        raise SystemExit("sparse proof: total CPU-readable GMC spare capacity differs")

    print(
        f"sparse proof: {len(enemy_ranges)} enemy and {len(player_ranges)} player "
        f"frames decode and blend pixel-exactly; {len(loader)} loader segments reconstruct "
        f"actor, gate, presentation, cold, and module payloads with "
        f"{manifest['gmc']['spare_bytes']} bytes spare"
    )


if __name__ == "__main__":
    main()
