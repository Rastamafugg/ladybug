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
from gmc_lzss import decompress as lzss_decompress


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
PAGE_BYTES = 0x2000
WINDOW_BASE = 0xA000
CART_BANK_BYTES = 0x4000
CART_READABLE_BYTES = 0x3E00
BOOT_OVERFLOW_START = 0x0800
BANK2_PAYLOAD_START = 0x0020
LOW_RAM_DESTINATION_PAGE = 0xFF
BOOT_OVERFLOW_PROOF_ADDRESS = 0x06B0
BOOT_OVERFLOW_PROOF = bytes((0xB0, 0x0F))
SPARSE_COPY_TABLE_RAM = 0x0200
INSTRUCTION_RUNTIME_PAGE = 0x23
INSTRUCTION_RUNTIME_ADDRESS = 0xA422
INSTRUCTION_RUNTIME_BYTES = 0x3AA
HIGHSCORE_RUNTIME_ADDRESS = 0xA880
HIGHSCORE_PHASE_HELPER_ADDRESS = 0xAC40
LEGACY_PEN_MAP = (0x0, 0xC, 0x5, 0x2)
PART_ONE_PEN_MAP = (0x0, 0x9, 0x5, 0x6)
GAMEPLAY_ENEMY_PEN_MAPS = (
    PART_ONE_PEN_MAP,
    LEGACY_PEN_MAP,
    LEGACY_PEN_MAP,
    LEGACY_PEN_MAP,
    LEGACY_PEN_MAP,
    LEGACY_PEN_MAP,
    LEGACY_PEN_MAP,
    LEGACY_PEN_MAP,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sprites", type=Path, default=ROOT / "assets/arcade/sprites.json")
    parser.add_argument("--enemy-runtime", type=Path, default=BUILD / "ladybug-enemy-runtime.rom")
    parser.add_argument("--enemy-payload", type=Path, default=BUILD / "ladybug-enemy-sparse.bin")
    parser.add_argument("--player-payload", type=Path, default=BUILD / "ladybug-player-sparse.bin")
    parser.add_argument("--gate-payload", type=Path, default=BUILD / "ladybug-gate-transitions.bin")
    parser.add_argument("--presentation-payload", type=Path, default=BUILD / "ladybug-presentation-sparse.bin")
    parser.add_argument("--perimeter-reset-payload", type=Path, default=BUILD / "ladybug-perimeter-reset.bin")
    parser.add_argument("--perimeter-helper", type=Path, default=BUILD / "ladybug-perimeter-reset-helper.bin")
    parser.add_argument("--presentation-cold", type=Path, default=BUILD / "ladybug-presentation-cold.bin")
    parser.add_argument("--actor-records", type=Path, default=BUILD / "ladybug-attract-actor-records.bin")
    parser.add_argument("--actor-underlays", type=Path, default=BUILD / "ladybug-attract-actor-underlays.bin")
    parser.add_argument("--presentation-module", type=Path, default=BUILD / "ladybug-presentation-runtime.bin")
    parser.add_argument("--instruction-runtime", type=Path, default=BUILD / "ladybug-instruction-runtime.bin")
    parser.add_argument("--demo-runtime", type=Path, default=BUILD / "ladybug-demo-runtime.bin")
    parser.add_argument("--highscore-runtime", type=Path, default=BUILD / "ladybug-highscore-runtime.bin")
    parser.add_argument("--highscore-helper", type=Path, default=BUILD / "ladybug-highscore-helper.bin")
    parser.add_argument("--audio-runtime", type=Path, default=BUILD / "ladybug-audio-runtime.bin")
    parser.add_argument("--tile-patches", type=Path, default=BUILD / "ladybug-presentation-tile-patches.bin")
    parser.add_argument(
        "--aux-runtime-role",
        choices=("highscore-test", "development", "release", "complete"),
        default="release",
    )
    parser.add_argument("--bank0", type=Path, default=BUILD / "ladybug-gmc-bank0-overflow.bin")
    parser.add_argument("--bank2", type=Path, default=BUILD / "ladybug-sparse-bank2.bin")
    parser.add_argument("--bank3", type=Path, default=BUILD / "ladybug-sparse-bank3.bin")
    parser.add_argument("--loader", type=Path, default=BUILD / "ladybug-sparse-loader.inc")
    parser.add_argument("--manifest", type=Path, default=BUILD / "ladybug-sparse-layout.json")
    return parser.parse_args()


def expected_native(frame: bytes, pen_map: tuple[int, int, int, int]) -> bytes:
    output = bytearray()
    for value in frame:
        pixels = (
            (value >> 6) & 3,
            (value >> 4) & 3,
            (value >> 2) & 3,
            value & 3,
        )
        output.extend((
            (pen_map[pixels[0]] << 4) | pen_map[pixels[1]],
            (pen_map[pixels[2]] << 4) | pen_map[pixels[3]],
        ))
    return bytes(output)


def decode_payload(
        payload: bytes, frames: list[bytes], pen_maps: list[tuple[int, int, int, int]],
        page_base: int
) -> list[tuple[int, int]]:
    """Decode every indexed stream and return its [start,end) payload range."""
    if len(frames) != len(pen_maps):
        raise ValueError("each frame requires one explicit verifier pen map")
    index_bytes = len(frames) * 3
    if len(payload) < index_bytes:
        raise ValueError("payload is shorter than its frame index")
    ranges = []
    for frame_number, (packed_frame, pen_map) in enumerate(zip(frames, pen_maps)):
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
        native = expected_native(packed_frame, pen_map)
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
        if line.strip() == "gmc_lzss_stream_table":
            break
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
    enemy_pen_maps = [
        pen_map
        for pen_map in GAMEPLAY_ENEMY_PEN_MAPS
        for _ in range(16)
    ] + [LEGACY_PEN_MAP] * 2
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
    instruction_runtime = args.instruction_runtime.read_bytes()
    demo_runtime = args.demo_runtime.read_bytes()
    highscore_runtime = args.highscore_runtime.read_bytes()
    highscore_helper = args.highscore_helper.read_bytes()
    audio_runtime = args.audio_runtime.read_bytes()
    tile_patches = args.tile_patches.read_bytes()
    if len(highscore_runtime) > 0x398:
        raise SystemExit("sparse proof: high-score runtime exceeds $0300-$0697")
    if args.aux_runtime_role == "development":
        aux_runtime_stage = instruction_runtime
    elif args.aux_runtime_role == "complete":
        highscore_offset = HIGHSCORE_RUNTIME_ADDRESS - INSTRUCTION_RUNTIME_ADDRESS
        helper_offset = HIGHSCORE_PHASE_HELPER_ADDRESS - INSTRUCTION_RUNTIME_ADDRESS
        prefix = instruction_runtime + demo_runtime
        if len(prefix) > highscore_offset:
            raise SystemExit("sparse proof: complete demo overlaps high-score runtime")
        prefix = prefix.ljust(highscore_offset, b"\x00") + highscore_runtime
        if len(prefix) > helper_offset:
            raise SystemExit("sparse proof: high-score runtime overlaps helper")
        aux_runtime_stage = prefix.ljust(helper_offset, b"\x00") + highscore_helper
    else:
        aux_runtime_stage = demo_runtime
    enemy_ranges = decode_payload(enemy_payload, enemy_frames, enemy_pen_maps, 0x35)
    player_ranges = decode_payload(
        player_payload, player_frames, [LEGACY_PEN_MAP] * len(player_frames), 0x39
    )
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
    palette_families = manifest["enemy"].get("palette_families", [])
    expected_family_maps = [list(value) for value in GAMEPLAY_ENEMY_PEN_MAPS]
    if (
        len(palette_families) != 9 or
        [item["pen_map"] for item in palette_families[:8]] != expected_family_maps or
        palette_families[8]["pen_map"] != list(LEGACY_PEN_MAP) or
        (palette_families[8]["frame_first"], palette_families[8]["frame_last"]) !=
            (128, 129)
    ):
        raise SystemExit("sparse proof: explicit enemy-family palette provenance differs")
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
    if manifest["audio_runtime"]["sha256"] != sha256(audio_runtime):
        raise SystemExit("sparse proof: audio runtime manifest hash mismatch")
    if (
        manifest["audio_runtime"]["page"] != 0x3D or
        manifest["audio_runtime"]["address"] != WINDOW_BASE
    ):
        raise SystemExit("sparse proof: audio runtime is not placed at page $3D")
    if manifest["aux_runtime"]["role"] != args.aux_runtime_role:
        raise SystemExit("sparse proof: auxiliary runtime profile mismatch")
    if manifest["aux_runtime"]["staged_sha256"] != sha256(aux_runtime_stage):
        raise SystemExit("sparse proof: auxiliary runtime staged hash mismatch")
    if manifest["highscore_helper"]["sha256"] != sha256(highscore_helper):
        raise SystemExit("sparse proof: high-score helper manifest hash mismatch")
    if manifest["highscore_runtime"]["sha256"] != sha256(highscore_runtime):
        raise SystemExit("sparse proof: high-score runtime manifest hash mismatch")
    if args.aux_runtime_role in ("development", "complete") and manifest.get("instruction_runtime", {}).get("sha256") != sha256(instruction_runtime):
        raise SystemExit("sparse proof: instruction runtime manifest hash mismatch")
    if args.aux_runtime_role in ("release", "complete") and manifest.get("demo_runtime", {}).get("sha256") != sha256(demo_runtime):
        raise SystemExit("sparse proof: demo runtime manifest hash mismatch")
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
    if manifest["gmc"].get("sparse_copy_table_ram") != SPARSE_COPY_TABLE_RAM:
        raise SystemExit("sparse proof: sparse table RAM address differs")
    low_ram = []
    for segment in manifest_segments:
        if segment["destination_page"] != LOW_RAM_DESTINATION_PAGE:
            continue
        start = segment["destination_address"]
        end = start + segment["count"]
        low_ram.append((segment["target"], start, end))
    table_end = (
        SPARSE_COPY_TABLE_RAM +
        manifest["gmc"].get("sparse_copy_table_bytes", 0)
    )
    low_ram.append(("active sparse copy table", SPARSE_COPY_TABLE_RAM, table_end))
    for index, left in enumerate(low_ram):
        for right in low_ram[index + 1:]:
            if left[2] > right[1] and right[2] > left[1]:
                raise SystemExit(
                    "sparse proof: low-RAM destination overlap: "
                    f"{left[0]} and {right[0]}"
                )
    if len(loader) != len(manifest_segments):
        raise SystemExit("sparse proof: loader and manifest segment counts differ")
    reconstructed = {
        "enemy": bytearray(len(enemy_payload)),
        "player": bytearray(len(player_payload)),
        "gate": bytearray(len(gate_payload)),
        "presentation": bytearray(len(presentation_payload)),
        "presentation_cold": bytearray(len(presentation_cold)),
        "presentation_module": bytearray(len(presentation_module)),
        "audio_runtime": bytearray(len(audio_runtime)),
        "attract_actor_bundle": bytearray(
            len(actor_underlays) + len(actor_records) + len(aux_runtime_stage)
        ),
        "phase_tile_patches": bytearray(len(tile_patches)),
    }
    coverage = {
        "enemy": bytearray(len(enemy_payload)),
        "player": bytearray(len(player_payload)),
        "gate": bytearray(len(gate_payload)),
        "presentation": bytearray(len(presentation_payload)),
        "presentation_cold": bytearray(len(presentation_cold)),
        "presentation_module": bytearray(len(presentation_module)),
        "audio_runtime": bytearray(len(audio_runtime)),
        "attract_actor_bundle": bytearray(
            len(actor_underlays) + len(actor_records) + len(aux_runtime_stage)
        ),
        "phase_tile_patches": bytearray(len(tile_patches)),
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
        elif target == "audio_runtime":
            target_page_base = 0x3D
            target_address = WINDOW_BASE
        elif target == "attract_actor_bundle":
            target_page_base = 0x23
            target_address = 0xA000
        elif target == "phase_tile_patches":
            target_page_base = 0x23
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

    expected_streams = {
        "page39", "presentation_page_3a", "audio_page_3d"
    }
    if len(presentation_cold) > PAGE_BYTES:
        expected_streams.add("presentation_page_3b")
    streams = manifest.get("compression", {}).get("streams", [])
    if {stream["name"] for stream in streams} != expected_streams:
        raise SystemExit("sparse proof: compressed stream set differs")
    for stream in streams:
        bank = stream["bank"]
        source_offset = stream["source_offset"]
        compressed_bytes = stream["compressed_bytes"]
        raw_bytes = stream["raw_bytes"]
        if source_offset + compressed_bytes > CART_READABLE_BYTES:
            raise SystemExit("sparse proof: compressed source exceeds readable cart")
        if any(source_coverage[bank][source_offset:source_offset + compressed_bytes]):
            raise SystemExit("sparse proof: compressed and copied sources overlap")
        source_coverage[bank][source_offset:source_offset + compressed_bytes] = (
            b"\x01" * compressed_bytes
        )
        compressed = banks[bank][source_offset:source_offset + compressed_bytes]
        if sha256(compressed) != stream["compressed_sha256"]:
            raise SystemExit("sparse proof: compressed stream hash differs")
        raw = lzss_decompress(compressed, raw_bytes)
        if sha256(raw) != stream["raw_sha256"]:
            raise SystemExit("sparse proof: expanded stream hash differs")
        name = stream["name"]
        if name == "page39":
            boundaries = (
                ("player", 0, len(player_payload)),
                ("gate", len(player_payload), len(player_payload) + len(gate_payload)),
                ("presentation", len(player_payload) + len(gate_payload), len(raw)),
            )
            for target, start, end in boundaries:
                reconstructed[target][:] = raw[start:end]
                coverage[target][:] = b"\x01" * len(reconstructed[target])
        elif name.startswith("presentation_page_"):
            offset = (stream["destination_page"] - 0x3A) * PAGE_BYTES
            end = offset + len(raw)
            reconstructed["presentation_cold"][offset:end] = raw
            coverage["presentation_cold"][offset:end] = b"\x01" * len(raw)
        elif name == "audio_page_3d":
            reconstructed["audio_runtime"][:] = raw
            coverage["audio_runtime"][:] = b"\x01" * len(raw)
    if (
        not all(coverage["enemy"]) or
        not all(coverage["player"]) or
        not all(coverage["gate"]) or
        not all(coverage["presentation"]) or
        not all(coverage["presentation_cold"]) or
        not all(coverage["presentation_module"]) or
        not all(coverage["audio_runtime"]) or
        not all(coverage["attract_actor_bundle"]) or
        not all(coverage["phase_tile_patches"])
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
    if reconstructed["audio_runtime"] != audio_runtime:
        raise SystemExit("sparse proof: loader does not reconstruct audio runtime")
    if reconstructed["attract_actor_bundle"] != (
        actor_underlays + actor_records + aux_runtime_stage
    ):
        raise SystemExit("sparse proof: loader does not reconstruct actor bundle")
    if reconstructed["phase_tile_patches"] != tile_patches:
        raise SystemExit("sparse proof: loader does not reconstruct phase tile patches")
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
        f"actor, gate, presentation, cold, module, audio, and auxiliary payloads with "
        f"{manifest['gmc']['spare_bytes']} bytes spare"
    )


if __name__ == "__main__":
    main()
