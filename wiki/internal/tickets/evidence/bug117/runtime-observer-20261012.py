#!/usr/bin/env python3
"""BUG-117 observer preparation and guarded runtime capture.

Import, --help, --prepare-only, and --self-test never start an emulator,
monitor, build, or target. Live capture is implemented but requires an explicit
--run-live plus a complete adaptive source-build receipt and parent-accepted
GDB-MCP delivery qualification receipt for the exact candidate artifacts.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import socket
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCENARIOS = ("natural", "front-first", "music-first", "prior-music")
PHASE_SECONDS = 45
STOP_WAIT_SECONDS = 10
GAMEPLAY_WORKLIST_CYCLE_TARGET = 27000
HISTORICAL_GAMEPLAY_WORKLIST_CYCLES = {
    "ordinary_north": 42541,
    "one_roamer_plus_popup_nest": 54539,
}
TIMER_ADDRESS = 0x003A
TIMER_VALUES = {"front-first": 0, "music-first": 255, "prior-music": 0}
COIN5_MATRIX_KEY = 44
COIN5_DSCAN_KEY = 5
ENTRY_SOUTH_BINDING_INDEX = 1
ENTRY_EAST_DIRECTION = 1
ENTRY_NORTH_DIRECTION = 0
ROOT = next((p for p in Path(__file__).resolve().parents if (p / "scripts/build.sh").is_file()), None)
MONITOR_TEMPLATE = (ROOT / "scripts/verify_bug009_monitor_input.py") if ROOT else None
MONITOR_SOURCE = (ROOT / "docs/reference/xroar/src/monitor.c") if ROOT else None
PLAYER_ART = (ROOT / "assets/arcade/sprites.json") if ROOT else None
VISIBLE_BASE = 0x2000
VISIBLE_BYTES = 30720
PHYSICAL_PAGE_BYTES = 0x2000
RESIDENT_IMAGE_BASE = 0xC000
RESIDENT_IMAGE_BYTES = 0x4000
PAR_BASE = 0xFFA0
PAR5 = 0xFFA5
SND_DATA = 0xFF51
FB_FRONT_ID = 0x008F
FB_BACK_ID = 0x0090
FB_RENDER_PENDING = 0x0091
FB_COMMIT_SEQ = 0x0092
INITIAL_ENTRY_STATE = 0x00A0
PRES_CREDITS_ADDRESS = 0x00A8
MODE_ATTRACT = 2
DEATH_STATE = 0x004D
PLAYER_FB = 0x000B
PLAYER_FACE = 0x0007
PLAYER_ANIM = 0x004F
PLAYER_BG_PTR = 0x00A2
PLAYER_BG_VALID = 0x006A
PLAYER_CELL_X = 0x0009
PLAYER_CELL_Y = 0x000A
PLAYER_STEP = 0x0008
MUSIC_BUSY = 0x02D4
AUDIO_Q_COUNT = 0x00EE
AUDIO_CREDIT_PENDING = 0x02DD
WATCHED_PHASES = {
    "initial-entry": 45,
    "natural-contact-search": 45,
    "death-animation-blank": 45,
    "fixture-boundary": 45,
    "audio-cue6": 45,
    "audio-terminal": 45,
    "cue13-normal-drain": 45,
    "replacement-entry": 45,
    "irq-front-release": 45,
}
LIVE_CAPTURE_IMPLEMENTED = True


class GuardFailure(RuntimeError):
    pass


class QualificationFailure(GuardFailure):
    """Fail closed while retaining byte and stopped-monitor evidence."""
    def __init__(self, message: str, failure_context: dict[str, Any]):
        super().__init__(message)
        self.failure_context = failure_context


def monitor_call(client: Any, method: str, params: dict[str, Any] | None = None,
                 maximum: float = STOP_WAIT_SECONDS) -> dict[str, Any]:
    """Cap live RPC work by the active phase deadline when called during dispatch."""
    deadline = getattr(client, "_bug117_phase_deadline", None)
    timeout = maximum
    if deadline is not None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise GuardFailure(f"phase deadline expired before monitor {method} call")
        timeout = min(maximum, remaining)
    if not 0 < timeout <= STOP_WAIT_SECONDS:
        raise GuardFailure("monitor RPC timeout exceeds the approved 10-second bound")
    return client.call(method, params, timeout=timeout)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_safe(value: Any) -> Any:
    """Copy diagnostic values into a bounded JSON-compatible representation."""
    if isinstance(value, bytes):
        return {"hex": value.hex(), "length": len(value)}
    if isinstance(value, bytearray):
        data = bytes(value)
        return {"hex": data.hex(), "length": len(data)}
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [json_safe(item) for item in value]
    if value is None or type(value) in (bool, int, float, str):
        return value
    return repr(value)


def read_symbols(path: Path) -> dict[str, int]:
    return {name: int(value, 16) for name, value in re.findall(
        r"^Symbol: (\w+) .* = ([0-9A-Fa-f]+)$", path.read_text(encoding="utf-8"), re.M)}


def _asm_code_line(line: str) -> str:
    return line.split(";", 1)[0].strip()


def _asm_immediate_a(line: str) -> int | None:
    match = re.fullmatch(r"lda\s+#\$([0-9A-Fa-f]{1,2})", _asm_code_line(line), re.I)
    return int(match.group(1), 16) if match else None


def derive_bootstrap_reset_qualification(build: Path, packaged_rom: bytes) -> dict[str, Any]:
    """Bind boot reset-store spans to current source, build receipt, staged bank, and package."""
    build = build.resolve(strict=True)
    source_path = build.parent / "src" / "gmc_bootstrap.s"
    receipt_path = build / "source-build-receipt.json"
    boot_path = build / "ladybug-gmc-boot.rom"
    map_path = build / "ladybug-gmc-boot.map"
    listing_path = build / "ladybug-gmc-boot.lst"
    if not all(path.is_file() for path in (source_path, receipt_path, boot_path, map_path, listing_path)):
        raise GuardFailure("current bootstrap source, receipt, staged image, map, or listing is missing")
    source_bytes = source_path.read_bytes()
    source_text = source_bytes.decode("utf-8")
    source_lines = source_text.splitlines()
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    source_name = "src/gmc_bootstrap.s"
    receipt_inputs = {str(key).replace("\\", "/"): value
                      for key, value in receipt.get("inputs", {}).items()}
    source_sha = sha(source_bytes)
    if receipt.get("state") != "complete" or receipt_inputs.get(source_name) != source_sha:
        raise GuardFailure("bootstrap source bytes do not match the complete source-build receipt")
    invocations = [item for item in receipt.get("invocations", [])
                   if str(item.get("source", "")).replace("\\", "/") == source_name and
                   Path(str(item.get("output", ""))).name.startswith("ladybug-gmc-boot.rom")]
    if len(invocations) != 1:
        raise GuardFailure("source receipt must contain exactly one current bootstrap assembly invocation")
    invocation = invocations[0]
    artifacts = receipt.get("artifacts", {})
    boot_image = boot_path.read_bytes()
    artifact_hashes: dict[str, str] = {}
    for path in (boot_path, map_path, listing_path):
        name = path.name
        expected_hash = artifacts.get(name) if isinstance(artifacts, dict) else None
        actual_hash = sha(path.read_bytes())
        if not isinstance(expected_hash, str) or expected_hash != actual_hash:
            raise GuardFailure(f"staged bootstrap {name} differs from the complete source receipt")
        artifact_hashes[name] = actual_hash
    if len(boot_image) != RESIDENT_IMAGE_BYTES or len(packaged_rom) < RESIDENT_IMAGE_BYTES:
        raise GuardFailure("staged bootstrap or packaged ROM bank has an invalid size")
    origins = [int(match.group(1), 16) for line in source_lines
               if (match := re.fullmatch(r"\s*org\s+\$([0-9A-Fa-f]{4})\s*", _asm_code_line(line), re.I))]
    if len(origins) != 1:
        raise GuardFailure("bootstrap source must have one explicit origin")
    origin = origins[0]
    boot_map = read_symbols(map_path)
    if "loader_end" not in boot_map or boot_map["loader_end"] <= origin:
        raise GuardFailure("bootstrap map lacks a valid loader_end raw-image boundary")
    raw_length = boot_map["loader_end"] - origin
    if raw_length > len(boot_image) or sha(boot_image[:raw_length]) != invocation.get("assembled_sha256"):
        raise GuardFailure("map-derived staged bootstrap prefix differs from its assembly invocation")
    packaged_boot_bank = packaged_rom[:RESIDENT_IMAGE_BYTES]
    packaged_boot_prefix = packaged_rom[:raw_length]
    if packaged_boot_prefix != boot_image[:raw_length]:
        raise GuardFailure("packaged ROM bank zero raw bootstrap prefix differs from the staged bootstrap")

    # The listing is the emitted address/byte authority for each source line.
    listed: dict[int, tuple[int, bytes, str]] = {}
    for line in listing_path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^\s*([0-9A-Fa-f]{4})\s+([0-9A-Fa-f]+)\s+\(c/gmc_bootstrap\.s\):(\d+)\s*(.*)$", line)
        if match:
            listed[int(match.group(3))] = (int(match.group(1), 16),
                bytes.fromhex(match.group(2)), match.group(4).strip())

    par_exec = boot_map.get("PAR_EXEC")
    if type(par_exec) is not int or par_exec + 6 > 0xFFFF:
        raise GuardFailure("bootstrap map lacks a valid PAR_EXEC mapping symbol")
    page_setup: dict[int, tuple[int, int, int, int]] = {}
    for line_index, line in enumerate(source_lines):
        code = _asm_code_line(line)
        match = re.fullmatch(r"sta\s+PAR_EXEC\+([56])", code, re.I)
        if not match or int(match.group(1)) in page_setup:
            continue
        page_index = int(match.group(1))
        previous_line = next((index for index in range(line_index - 1, -1, -1)
                              if _asm_code_line(source_lines[index])), None)
        previous = (_asm_immediate_a(source_lines[previous_line])
                    if previous_line is not None else None)
        load_line = previous_line if previous is not None else None
        if (previous is None and page_index == 6 and previous_line is not None and
                re.fullmatch(r"sta\s+PAR_EXEC\+5", _asm_code_line(source_lines[previous_line]), re.I) and
                5 in page_setup):
            _, previous, load_line, _ = page_setup[5]
        listed_store = listed.get(line_index + 1)
        if (previous is None or listed_store is None or
                listed_store[1] != bytes((0xB7, (par_exec + page_index) >> 8,
                                          (par_exec + page_index) & 0xFF))):
            raise GuardFailure(f"bootstrap PAR_EXEC+{page_index} setup is malformed or disagrees with its map")
        store_pc = listed_store[0]
        if load_line is None or _asm_immediate_a(source_lines[load_line]) != previous:
            raise GuardFailure("bootstrap PAR page immediate is not the preceding executable instruction")
        listed_load = listed.get(load_line + 1)
        if (listed_load is None or listed_load[1] != bytes((0x86, previous)) or
                listed_load[0] + len(listed_load[1]) != store_pc):
            if not (page_index == 6 and previous_line is not None and
                    re.fullmatch(r"sta\s+PAR_EXEC\+5", _asm_code_line(source_lines[previous_line]), re.I) and
                    listed.get(previous_line + 1) is not None and
                    listed[previous_line + 1][0] + len(listed[previous_line + 1][1]) == store_pc):
                raise GuardFailure("bootstrap PAR page load bytes disagree with the source listing")
        page_setup[page_index] = (line_index + 1, previous, load_line, store_pc)
    if 5 not in page_setup or 6 not in page_setup or page_setup[5][1] != page_setup[6][1]:
        raise GuardFailure("bootstrap does not establish matching PAR_EXEC+5/+6 pages")
    expected_page = page_setup[6][1]
    page_register = par_exec + 6

    reset_stores: list[dict[str, Any]] = []
    reset_source_indices: list[int] = []
    for line_index, line in enumerate(source_lines):
        if not re.fullmatch(r"sta\s+\$FF51", _asm_code_line(line), re.I):
            continue
        previous_line = next((index for index in range(line_index - 1, -1, -1)
                              if _asm_code_line(source_lines[index])), None)
        value = _asm_immediate_a(source_lines[previous_line]) if previous_line is not None else None
        listed_load = listed.get(previous_line + 1) if previous_line is not None else None
        listed_store = listed.get(line_index + 1)
        if (value is None or listed_load is None or listed_store is None or
                listed_load[1] != bytes((0x86, value)) or
                listed_store[1] != b"\xB7\xFF\x51" or
                listed_load[0] + 2 != listed_store[0]):
            raise GuardFailure("bootstrap reset SND_DATA source/listing sequence is malformed")
        load_pc, store_pc = listed_load[0], listed_store[0]
        post_pc = store_pc + len(listed_store[1])
        span = boot_image[load_pc - origin:post_pc - origin]
        packaged_span = packaged_rom[load_pc - origin:post_pc - origin]
        post_pc_span = boot_image[post_pc - origin:post_pc - origin + 3]
        packaged_post_pc_span = packaged_rom[post_pc - origin:post_pc - origin + 3]
        expected_span = listed_load[1] + listed_store[1]
        if (load_pc < origin or post_pc > boot_map["loader_end"] or
                span != expected_span or packaged_span != span or
                len(span) != 5 or len(post_pc_span) != 3 or
                packaged_post_pc_span != post_pc_span or
                post_pc + len(post_pc_span) > boot_map["loader_end"]):
            raise GuardFailure("bootstrap reset SND_DATA span differs from staged or packaged raw bytes")
        reset_stores.append({
            "sequence": len(reset_stores), "source_load_line": previous_line + 1,
            "source_store_line": line_index + 1, "load_pc": load_pc,
            "store_pc": store_pc, "post_store_pc": post_pc, "value": value,
            "span_hex": span.hex(), "span_sha256": sha(span),
            "post_pc_span_hex": post_pc_span.hex(),
            "post_pc_span_sha256": sha(post_pc_span),
        })
        reset_source_indices.append(line_index)
    if (not reset_stores or page_setup[6][0] - 1 >= reset_source_indices[0] or
            len(reset_stores) != len(reset_source_indices)):
        raise GuardFailure("bootstrap reset stores are absent or precede PAR_EXEC+6 mapping setup")
    return {
        "source": source_name, "source_sha256": source_sha,
        "source_receipt_sha256": sha(receipt_path.read_bytes()),
        "assembly_sha256": invocation.get("assembled_sha256"),
        "raw_length": raw_length, "raw_prefix_sha256": sha(boot_image[:raw_length]),
        "origin": origin, "loader_end": boot_map["loader_end"],
        "staged_boot_sha256": sha(boot_image),
        "packaged_bank0_sha256": sha(packaged_boot_bank),
        "packaged_raw_prefix_sha256": sha(packaged_boot_prefix),
        "packaged_raw_prefix_match": True,
        "receipt_artifact_sha256": artifact_hashes,
        "page_register": page_register, "expected_page": expected_page,
        "page_setup_source_lines": {"PAR_EXEC+5": page_setup[5][0],
                                     "PAR_EXEC+6": page_setup[6][0]},
        "reset_stores": reset_stores,
    }


def stream_terminal(image: bytes, start: int, limit: int) -> dict[str, Any]:
    """Decode linked commands to the emitted zero-command boundary."""
    pos = start
    commands = 0
    while pos < limit:
        op = image[pos]
        if op == 0:
            return {"terminator_offset": pos, "terminal_next_offset": pos + 1,
                    "command_count": commands, "terminator": op}
        if op == 2:
            size = 2
        elif 0x10 <= op <= 0x12:
            size = 4
        elif op == 0x1C:
            size = 3
        elif op in (0x1D, 0x1E):
            size = 2
        else:
            raise GuardFailure(f"unsupported audio command ${op:02X} at image offset ${pos:04X}")
        if pos + size > limit:
            raise GuardFailure("audio command extends past the linked audio image")
        pos += size
        commands += 1
    raise GuardFailure("linked stream has no emitted zero-command terminator")


@dataclass(frozen=True)
class PSGStore:
    kind: str
    channel: int | None
    value: int
    selected_slot: int | None = None
    source_voice: int | None = None


def mix_exclusive_slot(slots: list[dict[str, Any]], expected_id: int) -> dict[str, Any]:
    """Reconstruct exclusive selection and physical voices from live slot bytes."""
    if len(slots) != 4:
        raise GuardFailure("mixer snapshot must contain all four physical slots")
    exclusive = [s for s in slots if s["id"] != 0xFF and (s["policy"] & 1)]
    if not exclusive:
        raise GuardFailure("no active exclusive music source owns this mix")
    selected = sorted(exclusive, key=lambda s: (-s["priority"], s["index"]))[0]
    if selected["id"] != expected_id or selected["index"] != 0:
        raise GuardFailure("expected cue is not the mixer-selected slot-0 source")
    if selected["priority"] != (selected["policy"] >> 5):
        raise GuardFailure("selected slot priority disagrees with its descriptor policy")
    # audio_mix_clear writes raw bytes 01 00; as a little-endian period this is 1.
    periods = [1, 1, 1]
    attenuation = [15, 15, 15]
    channel_sources: list[dict[str, int]] = []
    out_channel = 0
    for voice in range(3):
        source_atten = selected["attenuation"][voice]
        if source_atten >= 15 or out_channel >= 3:
            continue
        periods[out_channel] = selected["periods"][voice]
        attenuation[out_channel] = source_atten
        channel_sources.append({"channel": out_channel, "slot": selected["index"], "voice": voice})
        out_channel += 1
    noise = [0, 15]
    if selected["noise_attenuation"] < 15 and noise[1] >= 15:
        noise = [selected["noise"], selected["noise_attenuation"]]
    return {"selected": selected, "periods": periods, "attenuation": attenuation,
            "noise": noise, "channel_sources": channel_sources,
            "audible_voice_count": sum(v < 15 for v in selected["attenuation"])}


def expected_psg_transaction(period_bytes: bytes, attenuation: bytes,
                             noise: bytes, shadow: bytes,
                             channel_sources: list[dict[str, int]]) -> list[PSGStore]:
    """Model audio_mix_write's actual ordered SND_DATA stores, including muted latches."""
    if len(period_bytes) != 6 or len(attenuation) != 3 or len(noise) != 2 or len(shadow) != 11:
        raise GuardFailure("PSG mixer snapshot has an unexpected byte width")
    by_channel = {x["channel"]: x for x in channel_sources}
    stores: list[PSGStore] = []
    for ch in range(3):
        lo, hi = period_bytes[ch * 2:ch * 2 + 2]
        source = by_channel.get(ch)
        stores.append(PSGStore("tone-latch", ch, 0x80 | (ch << 5) | (lo & 0x0F),
                               source["slot"] if source else None,
                               source["voice"] if source else None))
        # audio_mix_write loads the low byte into A and the high byte into B.
        data = ((hi << 4) | (lo >> 4)) & 0x3F
        if data != shadow[ch * 3 + 1]:
            stores.append(PSGStore("period-data", ch, data,
                                   source["slot"] if source else None,
                                   source["voice"] if source else None))
        volume = 0x90 | (ch << 5) | attenuation[ch]
        if volume != shadow[ch * 3 + 2]:
            stores.append(PSGStore("attenuation", ch, volume,
                                   source["slot"] if source else None,
                                   source["voice"] if source else None))
    noise_control = noise[0] | 0xE0
    if noise_control != shadow[9]:
        stores.append(PSGStore("noise-control", None, noise_control))
    noise_volume = noise[1] | 0xF0
    if noise_volume != shadow[10]:
        stores.append(PSGStore("noise-attenuation", None, noise_volume))
    return stores


def prove_audible_psg_source(model: dict[str, Any], observed: list[PSGStore]) -> dict[str, Any]:
    """Require a selected-source data/attenuation write, never a tone latch alone."""
    sources = {x["channel"]: x for x in model["channel_sources"]}
    proven = [s for s in observed if s.kind in ("period-data", "attenuation") and
              s.channel in sources and s.selected_slot == 0 and
              s.source_voice == sources[s.channel]["voice"]]
    if not proven:
        raise GuardFailure("actual PSG transaction has no selected audible cue voice data/attenuation store")
    return {"store_count": len(observed), "audible_store_count": len(proven),
            "audible_channels": sorted({s.channel for s in proven if s.channel is not None})}


def bug011_image_api() -> Any:
    """Load the maintained BUG-011 sprite conversion/blend oracle without running it."""
    if ROOT is None:
        raise GuardFailure("project root is unavailable for the maintained pixel oracle")
    scripts_dir = str(ROOT / "scripts")
    added = scripts_dir not in sys.path
    if added:
        sys.path.insert(0, scripts_dir)
    try:
        path = ROOT / "scripts/verify_bug011_rendering.py"
        spec = importlib.util.spec_from_file_location("bug117_bug011_rendering_model", path)
        if spec is None or spec.loader is None:
            raise GuardFailure("cannot load the maintained BUG-011 pixel oracle")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        if added:
            sys.path.remove(scripts_dir)


def classify_post_store(pc: int, a: int, par5: int, live_instruction: bytes,
                        expected_pc: int) -> dict[str, int]:
    """Reject non-STA/watchpoint stops; live opcode bytes decide the post-store PC."""
    if pc != expected_pc:
        raise GuardFailure(f"unexpected SND_DATA watch stop PC ${pc:04X}, expected ${expected_pc:04X}")
    if live_instruction != b"\xB7\xFF\x51":
        raise GuardFailure("live stop-PC-3 bytes are not the expected emitted STA $FF51")
    if par5 & 0x3F != 0x3D:
        raise GuardFailure("PSG store stop is not in the live audio page $3D")
    if type(a) is not int or not 0 <= a <= 0xFF:
        raise GuardFailure("live A register is absent or outside one byte")
    return {"pc": pc, "value": a, "par5": par5}


def player_expected_rect(background: bytes, packed_sprite: bytes) -> bytes:
    """Apply the BUG-011 native-frame/transparency rules to one 8x16 player rect."""
    if len(background) != 128:
        raise GuardFailure("player background must be a complete 8x16 saved-under")
    if len(packed_sprite) != 64:
        raise GuardFailure("authored player frame must be 16x16 packed 2bpp")
    oracle = bug011_image_api()
    start = oracle.runtime.VISIBLE_START
    frame = oracle.native_frame(packed_sprite)
    if len(frame) != 128:
        raise GuardFailure("BUG-011 native-frame conversion returned an unexpected size")
    target = bytearray(VISIBLE_BYTES)
    for row in range(16):
        target[row * 160:row * 160 + 8] = background[row * 8:row * 8 + 8]
    oracle.blend_frame(target, start, frame)
    return oracle.frame_rect(bytes(target), start)


def compare_opaque_player_pixels(expected: bytes, actual: bytes, packed_sprite: bytes,
                                 visible_width_bytes: int = 8) -> dict[str, int]:
    """Compare opaque pixels inside the clipped visible row width only."""
    if len(expected) != 128 or len(actual) != 128 or len(packed_sprite) != 64:
        raise GuardFailure("player pixel comparison requires complete 8x16 rectangles")
    if type(visible_width_bytes) is not int or not 1 <= visible_width_bytes <= 8:
        raise GuardFailure("player pixel comparison has an invalid visible row width")
    native = bug011_image_api().native_frame(packed_sprite)
    compared = mismatches = 0
    for index, (want, got, art) in enumerate(zip(expected, actual, native)):
        if index % 8 >= visible_width_bytes:
            continue
        for shift in (4, 0):
            if (art >> shift) & 0x0F:
                compared += 1
                if ((want >> shift) & 0x0F) != ((got >> shift) & 0x0F):
                    mismatches += 1
    if mismatches:
        raise GuardFailure(f"front player sprite differs at {mismatches}/{compared} opaque pixels")
    return {"opaque_pixels_compared": compared, "mismatches": mismatches,
            "visible_width_bytes": visible_width_bytes,
            "visible_width_pixels": visible_width_bytes * 2}


def visible_rect_matches_background(actual: bytes, background: bytes,
                                    visible_width_bytes: int) -> bool:
    """Compare only framebuffer bytes that belong to the visible clipped rows."""
    if len(actual) != 128 or len(background) != 128 or not 1 <= visible_width_bytes <= 8:
        raise GuardFailure("clipped background comparison requires two 8x16 rectangles")
    return all(actual[row * 8:row * 8 + visible_width_bytes] ==
               background[row * 8:row * 8 + visible_width_bytes] for row in range(16))


def requires_visible_front_pose(entry_state: int) -> bool:
    """State 3 retires the actor; every other observed entry state remains visible."""
    return entry_state != 3


def missing_visible_front_pose_failure(entry_state: int,
                                      pose: dict[str, Any] | None) -> bool:
    return pose is None and requires_visible_front_pose(entry_state)


def validate_offscreen_owner_retirement(state: dict[str, Any], entry: dict[str, Any],
                                        visible: dict[str, Any], actual: bytes) -> dict[str, Any]:
    """Prove one FRONT owner's prior entry pose was restored to its saved-under pixels."""
    generation = entry.get("index")
    if type(generation) is not int or generation < 1:
        raise GuardFailure("offscreen restoration lacks an entry generation")
    if state.get("entry") != 3 or state.get("death") != 0:
        raise GuardFailure("offscreen restoration was observed outside live entry state 3")
    start_fb, marker_x = entry.get("entry_start_fb"), entry.get("marker_x")
    x = entry_row_x(state.get("player_fb"), start_fb, marker_x)
    if x != 320:
        raise GuardFailure("offscreen restoration is not at row-derived x=320")
    owner = state.get("front")
    if type(owner) is not int or owner not in (0, 1):
        raise GuardFailure("offscreen restoration has no qualified FRONT owner")
    valid_field = "valid_a" if owner == 0 else "valid_b"
    if type(state.get(valid_field)) is not int or state[valid_field] != 0:
        raise GuardFailure("offscreen FRONT owner still publishes valid player metadata")
    if not isinstance(visible, dict):
        raise GuardFailure("offscreen owner lacks a last-visible saved-under snapshot")
    if (visible.get("entry_generation") != generation or visible.get("owner") != owner or
            type(visible.get("pointer")) is not int):
        raise GuardFailure("offscreen saved-under snapshot belongs to another entry or owner")
    pointer = visible["pointer"]
    width = visible.get("visible_width_bytes")
    if type(width) is not int or width != visible_row_width_bytes(pointer):
        raise GuardFailure("offscreen saved-under snapshot has an invalid clipped row width")
    saved_actual = visible.get("actual")
    background = visible.get("background")
    if (type(saved_actual) is not bytes or len(saved_actual) != 128 or
            type(background) is not bytes or len(background) != 128 or
            type(actual) is not bytes or len(actual) != 128):
        raise GuardFailure("offscreen saved-under comparison lacks complete 8x16 pixel records")
    if not visible_rect_matches_background(actual, background, width):
        raise GuardFailure("offscreen FRONT pixels differ from that owner's last saved-under image")
    return {"status": "RESTORED", "entry_generation": generation, "owner": owner,
        "pointer": pointer, "visible_width_bytes": width,
        "last_visible_actual_sha256": sha(saved_actual),
        "saved_under_sha256": sha(background), "restored_front_rect_sha256": sha(actual),
        "restored_pixels_match_saved_under": True}


def offscreen_maze_entry_gate(entry: dict[str, Any], ordinal: int) -> dict[str, Any]:
    """Require both owner restorations from this entry before state 4 is first observed."""
    generation = entry.get("index")
    tracking = entry.get("offscreen_retirement")
    retired = tracking.get("retired_by_owner") if isinstance(tracking, dict) else None
    retired = retired if isinstance(retired, dict) else {}
    accepted: dict[str, Any] = {}
    failures: list[str] = []
    if type(generation) is not int or generation < 1 or type(ordinal) is not int:
        failures.append("invalid-entry-generation-or-maze-entry-ordinal")
    for owner in (0, 1):
        proof = retired.get(owner)
        if (not isinstance(proof, dict) or proof.get("status") != "RESTORED" or
                proof.get("entry_generation") != generation or proof.get("owner") != owner or
                type(proof.get("event_ordinal")) is not int or proof["event_ordinal"] >= ordinal):
            failures.append(f"owner-{owner}-restoration-proof-missing-or-not-before-state4")
        else:
            accepted[str(owner)] = proof["event_ordinal"]
    return {"pass": not failures, "entry_generation": generation,
        "first_state4_ordinal": ordinal, "owner_restoration_ordinals": accepted,
        "failures": failures}


def visible_row_width_bytes(pointer: int) -> int:
    if type(pointer) is not int or not VISIBLE_BASE <= pointer < VISIBLE_BASE + VISIBLE_BYTES:
        raise GuardFailure("player framebuffer pointer is outside the visible image")
    return min(8, 160 - ((pointer - VISIBLE_BASE) % 160))


def verify_candidate_player_art(build: Path) -> dict[str, Any]:
    """Bind authored player frames to the candidate's indexed sparse payload bytes."""
    if ROOT is None or PLAYER_ART is None:
        raise GuardFailure("player art compiler/source is unavailable from this workspace")
    receipt_path = build / "source-build-receipt.json"
    layout_path = build / "ladybug-sparse-layout.json"
    sparse_path = build / "ladybug-player-sparse.bin"
    if not receipt_path.is_file() or not layout_path.is_file() or not sparse_path.is_file():
        raise GuardFailure("candidate lacks sprite source receipt, sparse layout, or player payload")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    inputs = {str(k).replace("\\", "/"): v for k, v in receipt.get("inputs", {}).items()}
    sparse = json.loads(layout_path.read_text(encoding="utf-8"))
    art_hash = sha(PLAYER_ART.read_bytes())
    if inputs.get("assets/arcade/sprites.json") != art_hash:
        raise GuardFailure("candidate build receipt does not bind the current authored player sprite source")
    script_inputs = {name: (ROOT / name) for name in
                     ("scripts/build_screen.py", "scripts/build_sparse_sprites.py")}
    for name, path in script_inputs.items():
        if inputs.get(name) != sha(path.read_bytes()):
            raise GuardFailure(f"candidate build receipt does not bind the player frame compiler {name}")
    scripts_dir = str(ROOT / "scripts")
    added = scripts_dir not in sys.path
    if added:
        sys.path.insert(0, scripts_dir)
    try:
        screen = importlib.import_module("build_screen")
        sparse_builder = importlib.import_module("build_sparse_sprites")
        frames = screen.compile_player_sprites(PLAYER_ART)
        payload = sparse_path.read_bytes()
        player = sparse.get("player", {})
        index = player.get("index", [])
        if len(frames) != 16 or player.get("frames") != len(frames) or len(index) != len(frames):
            raise GuardFailure("candidate player index does not contain all sixteen authored poses")
        if player.get("sha256") != sha(payload) or player.get("bytes") != len(payload):
            raise GuardFailure("candidate player sparse payload differs from its generated layout identity")
        pen_map = tuple(sparse_builder.PLAYER_PEN_MAP)
        for frame_index, (frame, entry) in enumerate(zip(frames, index)):
            expected = sparse_builder.encode_sparse_frame(frame, pen_map)
            start, length = entry.get("payload_offset"), entry.get("length")
            if type(start) is not int or type(length) is not int or payload[start:start + length] != expected:
                raise GuardFailure(f"candidate player frame {frame_index} differs from authored compiled art")
        return {"frame_count": len(frames), "art_source_sha256": art_hash,
                "player_sparse_sha256": sha(payload), "player_layout_sha256": sha(layout_path.read_bytes()),
                "build_screen_sha256": sha(script_inputs["scripts/build_screen.py"].read_bytes()),
                "sparse_encoder_sha256": sha(script_inputs["scripts/build_sparse_sprites.py"].read_bytes()),
                "all_frame_payloads_match": True}
    finally:
        if added:
            sys.path.remove(scripts_dir)


def validate_layout_final_image_identity(layout: dict[str, Any], rom_sha256: str) -> None:
    """Require the sparse layout's final-image identity to match the current ROM."""
    gmc = layout.get("gmc") if isinstance(layout, dict) else None
    if not isinstance(gmc, dict) or gmc.get("final_image_sha256") != rom_sha256:
        raise GuardFailure("sparse layout final-image identity differs from the current ROM")


def candidate_player_frame(build: Path, face: int, animation: int) -> tuple[bytes, dict[str, Any]]:
    """Return one authored packed 16x16 frame after candidate index/payload identity checks."""
    if type(face) is not int or not 0 <= face < 4 or type(animation) is not int or not 0 <= animation < 4:
        raise GuardFailure("live player pose face/animation values must each be in range 0..3")
    verify_candidate_player_art(build)
    scripts_dir = str(ROOT / "scripts")
    added = scripts_dir not in sys.path
    if added:
        sys.path.insert(0, scripts_dir)
    try:
        screen = importlib.import_module("build_screen")
        frame_index = face * 4 + animation
        frame = screen.compile_player_sprites(PLAYER_ART)[frame_index]
        return frame, {"frame_index": frame_index, "face": face, "animation": animation,
                       "candidate_art_identity_qualified": True}
    finally:
        if added:
            sys.path.remove(scripts_dir)


def candidate_player_frame_table(build: Path) -> tuple[tuple[bytes, ...], dict[str, Any]]:
    """Verify art/payload identity once, then compile the sixteen live pose choices."""
    identity = verify_candidate_player_art(build)
    scripts_dir = str(ROOT / "scripts")
    added = scripts_dir not in sys.path
    if added:
        sys.path.insert(0, scripts_dir)
    try:
        screen = importlib.import_module("build_screen")
        frames = tuple(screen.compile_player_sprites(PLAYER_ART))
        if len(frames) != 16:
            raise GuardFailure("candidate player compiler did not produce sixteen face/animation poses")
        return frames, identity
    finally:
        if added:
            sys.path.remove(scripts_dir)


def model_exclusive_mix(slots: list[dict[str, Any]], expected_id: int) -> dict[str, Any]:
    """Return expected mixer buffers from the selected exclusive slot and source voices."""
    model = mix_exclusive_slot(slots, expected_id)
    period_bytes = b"".join(int(p).to_bytes(2, "little") for p in model["periods"])
    attenuation = bytes(model["attenuation"])
    noise = bytes(model["noise"])
    return {**model, "period_bytes": period_bytes, "attenuation_bytes": attenuation,
            "noise_bytes": noise}


def model_quiet_mix(shadow: bytes) -> dict[str, Any]:
    """Model the source-defined no-active-slot mixer clear and mute stores."""
    if len(shadow) != 11:
        raise GuardFailure("quiet mixer shadow must contain eleven PSG latch bytes")
    return {"selected": None, "periods": [1, 1, 1], "attenuation": [15, 15, 15],
            "noise": [0, 15], "channel_sources": [], "audible_voice_count": 0,
            "period_bytes": b"\x01\x00" * 3, "attenuation_bytes": b"\x0F" * 3,
            "noise_bytes": b"\x00\x0F", "shadow": shadow}


def validate_quiet_terminal(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Require empty queue occupancy, inactive slots, and actual quiet mixer state."""
    if any(slot.get("id") != 0xFF for slot in snapshot.get("slots", [])):
        raise GuardFailure("terminal mute service has an active or competing audio slot")
    if len(snapshot.get("slots", [])) != 4:
        raise GuardFailure("terminal mute snapshot omits one or more physical audio slots")
    music_queue = snapshot.get("music_queue")
    if type(music_queue) is not bytes or len(music_queue) != 8:
        raise GuardFailure("terminal mute snapshot music queue must be exactly eight bytes")
    counts = {name: snapshot.get(name) for name in (
        "music_count", "effect_queue_count", "credit_pending", "mix_count")}
    if any(type(value) is not int or not 0 <= value <= 0xFF
           for value in counts.values()):
        raise GuardFailure("terminal mute snapshot has malformed queue or mixer counts")
    if counts["music_count"] > len(music_queue):
        raise GuardFailure("terminal music count exceeds the eight-byte queue capacity")
    if any(value != 0 for value in counts.values()):
        raise GuardFailure("terminal mute service has queued music, effects, credits, or mixer work")
    if (snapshot.get("mix_period_bytes") != b"\x01\x00" * 3 or
            snapshot.get("mix_attenuation") != b"\x0F" * 3 or
            snapshot.get("mix_noise") != b"\x00\x0F"):
        raise GuardFailure("terminal service buffers differ from audio_mix_clear's raw quiet defaults")
    return {"all_slots_clear": True, "all_queues_idle": True,
            "music_queue_active_count": counts["music_count"],
            "music_queue_capacity": len(music_queue),
            "inactive_music_queue_tail_hex": music_queue[counts["music_count"]:].hex(),
            "quiet_period_bytes": snapshot["mix_period_bytes"].hex(),
            "quiet_attenuation": snapshot["mix_attenuation"].hex(),
            "quiet_noise": snapshot["mix_noise"].hex()}


def model_from_audio_slot(raw: bytes, index: int) -> dict[str, Any]:
    if len(raw) != 28:
        raise GuardFailure(f"audio slot {index} must be the complete 28-byte slot")
    return {"index": index, "id": raw[0], "priority": raw[1], "policy": raw[2],
            "wait": raw[3], "stream_pointer": int.from_bytes(raw[4:6], "big"),
            "periods": [int.from_bytes(raw[6 + i * 2:8 + i * 2], "little") for i in range(3)],
            "attenuation": list(raw[12:15]), "noise": raw[15], "noise_attenuation": raw[16],
            "shadow": bytes(raw[17:28])}


def verify_stop_opcode(pc: int, opcode_bytes: bytes, expected: bytes,
                       label: str) -> int:
    """Return instruction end only when the candidate's emitted bytes match."""
    if opcode_bytes != expected:
        raise GuardFailure(f"live {label} instruction bytes {opcode_bytes.hex()} != {expected.hex()}")
    return pc + len(opcode_bytes)


def qualify_irq_commit_stop(marker: dict[str, Any], pc: int, dp: int,
                            live_opcode: bytes) -> dict[str, Any]:
    """Qualify the actual post-INC stop, including direct-page addressing semantics."""
    if pc != marker.get("end_pc"):
        raise GuardFailure(f"IRQ commit stop PC ${pc:04X} is not emitted instruction end ${marker.get('end_pc', 0):04X}")
    expected = bytes.fromhex(marker.get("opcode_bytes", ""))
    if not expected or live_opcode != expected:
        raise GuardFailure("live IRQ INC opcode bytes differ from the emitted candidate instruction")
    required_dp = marker.get("required_dp")
    if required_dp is not None and dp != required_dp:
        raise GuardFailure(f"direct INC $93 requires DP=${required_dp:02X}; live DP=${dp:02X}")
    return {"pc": pc, "dp": dp, "encoding": marker["encoding"],
            "opcode_bytes": live_opcode.hex(), "post_instruction": True}


def post_busy_marker(audio_image: bytes, audio_map: dict[str, int]) -> int:
    """Derive the after-store marker from the actual linked JSR/STA byte sequence."""
    start = audio_map["audio_mix_write_done"] - 0xA000
    code = audio_image[start:start + 6]
    busy_routine = audio_map.get("audio_music_busy")
    if (len(code) != 6 or code[0] != 0xBD or
            int.from_bytes(code[1:3], "big") != busy_routine or
            code[3:6] != b"\xB7\x02\xD4"):
        raise GuardFailure("linked post-PSG busy sequence is not JSR + STA $02D4")
    return audio_map["audio_mix_write_done"] + len(code)


def audio_bus_write_marker(audio_image: bytes, audio_map: dict[str, int]) -> dict[str, Any]:
    """Derive the write watchpoint's post-STA stop PC from the linked routine bytes."""
    address = audio_map["audio_write"]
    offset = address - 0xA000
    opcode = audio_image[offset:offset + 3]
    if opcode != b"\xB7\xFF\x51":
        raise GuardFailure("linked audio_write does not begin with emitted STA $FF51")
    return {"instruction_pc": address, "stop_pc": address + len(opcode),
            "opcode_bytes": opcode.hex(), "stop_pc_derived_from_emitted_bytes": True}


def irq_commit_marker(enemy_image: bytes, enemy_map: dict[str, int]) -> dict[str, Any]:
    """Find the emitted direct/extended INC and report its derived stop PC."""
    start = enemy_map["fbiq_publish"] - 0x0800
    span = enemy_image[start:start + 64]
    base = enemy_map["fbiq_publish"]
    direct = [i for i in range(len(span) - 1) if span[i:i + 2] == b"\x0C\x93"]
    extended = [i for i in range(len(span) - 2) if span[i:i + 3] == b"\x7C\x00\x93"]
    candidates = [(i, "direct", 2, 0) for i in direct]
    candidates += [(i, "extended", 3, None) for i in extended]
    if len(candidates) != 1:
        raise GuardFailure("emitted IRQ region has no unique INC of FB_COMMIT_SEQ+1")
    offset, encoding, length, required_dp = candidates[0]
    return {"pc": base + offset, "end_pc": base + offset + length,
            "encoding": encoding, "required_dp": required_dp,
            "opcode_bytes": span[offset:offset + length].hex()}


def require_snapshot(scenario: str, s: dict[str, Any]) -> int:
    """Return the sole approved value, or deny on any absent/false guard."""
    if scenario == "natural":
        raise GuardFailure("natural scenario is strictly no-write")
    if scenario not in TIMER_VALUES:
        raise GuardFailure(f"unknown fixture scenario {scenario!r}")
    common = {
        "timer_map_qualified": True,
        "timer_address": TIMER_ADDRESS,
        "source_map_bytes_qualified": True,
        "render_pending": 0,
        "owner_a_player_valid": 0,
        "owner_b_player_valid": 0,
        "cue_published_busy": 1,
        "cue_actual_output_proven": True,
        "actual_psg_writes_match_mix": True,
    }
    if scenario in ("front-first", "music-first"):
        common.update({
            "entry_state": 3,
            "death_state": 0,
            "marker_x": 264,
            "lives": 0,
            "player_x": 320,
            "cue_active_id": 6,
            "slot0_id": 6,
            "slot0_policy": 0xB3,
            "slot0_priority": 5,
            "best_slot": 0,
            "best_priority": 5,
            "cue6_selected_voice_mask": 0x07,
            "higher_priority_exclusive_source": False,
        })
        if scenario == "front-first":
            common.update({"cue_dwell_cadence_viable": True})
    else:
        common.update({
            "entry_state": 0,
            "death_state": 3,
            "death_timer": 37,
            "genuine_enemy_contact_proven": True,
            "cue_active_id": 13,
            "slot0_id": 13,
            "slot0_policy": 0xD3,
            "slot0_priority": 6,
            "best_slot": 0,
            "best_priority": 6,
            "cue13_selected_voice_mask": 0x03,
            "higher_priority_exclusive_source": False,
            "cue13_actual_output_proven": True,
            "cue13_published_busy": 1,
        })
    missing = [k for k in common if k not in s]
    if missing:
        raise GuardFailure("missing guards: " + ", ".join(missing))
    wrong_types = [k for k, expected in common.items()
                   if ((type(expected) is int and type(s[k]) is not int) or
                       (type(expected) is bool and type(s[k]) is not bool))]
    if wrong_types:
        raise GuardFailure("numeric guards must be measured integer bytes/addresses: " +
                           ", ".join(wrong_types))
    wrong = [(k, s[k], v) for k, v in common.items() if s[k] != v]
    if wrong:
        raise GuardFailure("guard mismatch: " + repr(wrong))
    if scenario == "front-first" and (type(s.get("remaining_pad")) is not int or s["remaining_pad"] <= 0):
        raise GuardFailure("front-first requires a measured positive numeric remaining pad")
    if scenario == "prior-music" and (type(s.get("lives")) is not int or s["lives"] <= 0):
        raise GuardFailure("prior-music requires a measured positive numeric reserve")
    if scenario in ("front-first", "music-first"):
        count = s.get("cue6_selected_audible_voice_count")
        if type(count) is not int or count < 1:
            raise GuardFailure("cue6 must contribute at least one selected audible voice")
    if scenario == "prior-music":
        count = s.get("cue13_selected_audible_voice_count")
        if type(count) is not int or count < 1:
            raise GuardFailure("cue13 must contribute at least one selected audible voice")
    return TIMER_VALUES[scenario]


class FixtureWriter:
    """Revalidate the current stopped target, then issue its sole approved write."""
    def __init__(self, scenario: str, timer_address: int):
        self.scenario = scenario
        self.timer_address = timer_address
        self.attempts = 0

    def write_from_paused_stop(self, client: Any, expected_pc: int,
                               snapshot_reader: Any) -> dict[str, Any]:
        """Recapture every guard, then recheck the same halted PC immediately before one write."""
        if self.scenario == "natural":
            raise GuardFailure("natural scenario forbids target writes")
        if not callable(snapshot_reader):
            raise GuardFailure("live fixture write requires a current-stop guard reader")
        if self.timer_address != TIMER_ADDRESS:
            raise GuardFailure("the only permitted target is map-resolved DEATH_TIMER $003A")
        if self.attempts:
            raise GuardFailure("fixture write budget already consumed")
        snapshot = snapshot_reader(client)
        if not isinstance(snapshot, dict):
            raise GuardFailure("current-stop guard reader did not return a fresh snapshot")
        value = require_snapshot(self.scenario, snapshot)
        require_current_paused_stop(client, expected_pc)
        self.attempts = 1
        monitor_call(client, "write_memory", {"addr": TIMER_ADDRESS, "data": f"{value:02x}"})
        return {"scenario": self.scenario, "address": TIMER_ADDRESS,
                "value": value, "fresh_snapshot": True, "attempts": self.attempts}


REQUIRED_PROOFS = (
    "first_cue6_owned_psg_transaction",
    "first_post_psg_busy_one",
    "cue6_terminal_stream_end_owned",
    "terminal_actual_psg_mute_transaction",
    "terminal_post_psg_busy_zero",
    "final_pose_in_front_after_irq_commit",
    "release_after_audio_and_front_commit",
    "no_same_batch_player_or_enemy_mutation",
)
LIFECYCLE_EVENTS = ("death_state_1", "death_state_2", "death_blank_timer37",
                    "cue13_published_idle", "replacement_entry_seed", "replacement_cue6_output")


class ProofLedger:
    """Validate independently ordered audio/FRONT branches and their release join."""
    DEPENDENCIES = {
        "first_cue6_owned_psg_transaction": (),
        "first_post_psg_busy_one": ("first_cue6_owned_psg_transaction",),
        "cue6_terminal_stream_end_owned": ("first_post_psg_busy_one",),
        "terminal_actual_psg_mute_transaction": ("cue6_terminal_stream_end_owned",),
        "terminal_post_psg_busy_zero": ("terminal_actual_psg_mute_transaction",),
        "final_pose_in_front_after_irq_commit": (),
        "release_after_audio_and_front_commit": (
            "terminal_post_psg_busy_zero", "final_pose_in_front_after_irq_commit"),
        "no_same_batch_player_or_enemy_mutation": ("release_after_audio_and_front_commit",),
    }

    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def record(self, name: str, evidence: dict[str, Any]) -> None:
        if name not in REQUIRED_PROOFS:
            raise GuardFailure(f"unknown acceptance proof {name!r}")
        if any(item["name"] == name for item in self.records):
            raise GuardFailure(f"acceptance proof {name} was recorded more than once")
        ordinal = evidence.get("event_ordinal")
        if type(ordinal) is not int or ordinal < 1:
            raise GuardFailure(f"proof {name} requires a positive observed event_ordinal")
        if any(item["event_ordinal"] == ordinal for item in self.records):
            raise GuardFailure(f"proof {name} reuses an event_ordinal")
        self._validate(name, evidence)
        self.records.append({"name": name, **evidence})

    @staticmethod
    def _validate(name: str, e: dict[str, Any]) -> None:
        checks: dict[str, tuple[tuple[str, Any], ...]] = {
            "first_cue6_owned_psg_transaction": (("selected_id", 6), ("slot", 0),
                ("policy", 0xB3), ("best_slot", 0), ("best_priority", 5), ("mix_match", True)),
            "first_post_psg_busy_one": (("busy", 1), ("derived_marker", True),
                ("busy_read_after_psg", True)),
            "cue6_terminal_stream_end_owned": (("slot_id", 6), ("x_matches_emitted_end", True),
                ("terminator_byte", 0), ("stream_decoder_matches_emitted_bytes", True)),
            "terminal_actual_psg_mute_transaction": (("slot_clear_observed", True),
                ("all_mix_stores_match", True), ("quiet_state_verified", True)),
            "terminal_post_psg_busy_zero": (("busy", 0), ("all_slots_queues_credit_idle", True),
                ("busy_read_after_psg", True)),
            "final_pose_in_front_after_irq_commit": (("irq_commit_observed", True),
                ("front_pixels_match_opaque_player", True), ("live_code_span_qualified", True),
                ("irq_live_opcode_match", True), ("front_mapping_qualified", True),
                ("same_stop_busy_sample", True)),
            "release_after_audio_and_front_commit": (("busy_zero_precedes_release", True),
                ("front_commit_precedes_release", True)),
            "no_same_batch_player_or_enemy_mutation": (("player_unchanged", True),
                ("enemy_unchanged", True)),
        }
        missing = [key for key, _ in checks[name] if key not in e]
        if missing:
            raise GuardFailure(f"proof {name} lacks observed fields {missing}")
        wrong = [(key, e[key], want) for key, want in checks[name] if e[key] != want]
        if wrong:
            raise GuardFailure(f"proof {name} evidence mismatch: {wrong}")
        if name == "first_cue6_owned_psg_transaction":
            if type(e.get("audible_store_count")) is not int or e["audible_store_count"] < 1:
                raise GuardFailure("cue6 evidence requires at least one actual selected-source data/attenuation store")
        if name == "terminal_actual_psg_mute_transaction":
            if type(e.get("actual_mute_attenuation_stores")) is not int or e["actual_mute_attenuation_stores"] < 1:
                raise GuardFailure("terminal proof requires actual muted attenuation stores")
            if type(e.get("actual_store_count")) is not int or e["actual_store_count"] < 3:
                raise GuardFailure("terminal proof requires the actual complete PSG transaction store count")
        if name == "final_pose_in_front_after_irq_commit":
            if type(e.get("opaque_pixels_compared")) is not int or e["opaque_pixels_compared"] <= 0:
                raise GuardFailure("final-maze FRONT proof requires visible opaque pixels")
            if type(e.get("visible_width_bytes")) is not int or e["visible_width_bytes"] != 8:
                raise GuardFailure("final-maze FRONT proof requires the complete 16-pixel pose width")
            if type(e.get("published_music_busy")) is not int or e["published_music_busy"] not in (0, 1):
                raise GuardFailure("front-pose proof requires the same-stop published music-busy byte")
            if type(e.get("irq_commit_end_pc")) is not int or e["irq_commit_end_pc"] <= 0:
                raise GuardFailure("front-pose proof requires the emitted IRQ commit instruction end PC")
            if (type(e.get("irq_commit_event_ordinal")) is not int or
                    e["irq_commit_event_ordinal"] != e["event_ordinal"]):
                raise GuardFailure("front-pose proof ordinal must be the qualified IRQ-commit stop")
            if type(e.get("front_owner_voff1_shadow")) is not int:
                raise GuardFailure("front-pose proof requires the monitor's VOFF1 shadow")
            if e.get("front_owner_voff1_shadow") != (0xC0 if e.get("front_id") == 0 else 0xB0):
                raise GuardFailure("front-pose VOFF1 shadow does not identify its owner")
            if e.get("front_owner_voff2_shadow") != 0:
                raise GuardFailure("front-pose proof requires VOFF2=$00")
            if e.get("front_physical_base") != (0x60000 if e.get("front_id") == 0 else 0x58000):
                raise GuardFailure("front-pose GIME shadows do not select the owner's framebuffer base")
            if type(e.get("front_id")) is not int or not 0 <= e["front_id"] <= 3:
                raise GuardFailure("front-pose proof requires the published front owner id")

    def _order_failures(self) -> list[str]:
        by_name = {item["name"]: item for item in self.records}
        failures = []
        for name, dependencies in self.DEPENDENCIES.items():
            record = by_name.get(name)
            if record is None:
                continue
            for dependency in dependencies:
                required = by_name.get(dependency)
                if required is None:
                    failures.append(f"{name} lacks prerequisite {dependency}")
                elif required["event_ordinal"] >= record["event_ordinal"]:
                    failures.append(f"{dependency} does not precede {name}")
        return failures

    def status(self) -> dict[str, Any]:
        present = {item["name"] for item in self.records}
        missing = [name for name in REQUIRED_PROOFS if name not in present]
        order_failures = self._order_failures()
        return {"status": "INCOMPLETE" if missing or order_failures else "OBSERVATIONS_PRESENT",
                "missing_proofs": missing, "order_failures": order_failures,
                "pass": not missing and not order_failures,
                "proof_records": sorted(self.records, key=lambda item: item["event_ordinal"])}


def acceptance_status(ledger: ProofLedger | Any) -> dict[str, Any]:
    if not isinstance(ledger, ProofLedger):
        ledger = ProofLedger()
    return ledger.status()


class LifecycleOrder:
    """Track death visual and cue-13 drain branches before replacement entry."""
    DEPENDENCIES = {
        "death_state_1": (),
        "death_state_2": ("death_state_1",),
        "death_blank_timer37": ("death_state_2",),
        "cue13_published_idle": (),
        "replacement_entry_seed": ("death_blank_timer37", "cue13_published_idle"),
        "replacement_cue6_output": ("replacement_entry_seed",),
    }

    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def record(self, name: str, observed: dict[str, Any]) -> None:
        if name not in LIFECYCLE_EVENTS:
            raise GuardFailure(f"unknown life-cycle event {name!r}")
        if any(item["name"] == name for item in self.records):
            raise GuardFailure(f"life-cycle event {name} was duplicated")
        ordinal = observed.get("event_ordinal")
        if type(ordinal) is not int or ordinal < 1:
            raise GuardFailure(f"life-cycle event {name} requires a positive observed event_ordinal")
        if any(item["event_ordinal"] == ordinal for item in self.records):
            raise GuardFailure(f"life-cycle event {name} reuses an event_ordinal")
        required: dict[str, dict[str, Any]] = {
            "death_state_1": {"death_state": 1, "genuine_contact_live_bytes": True},
            "death_state_2": {"death_state": 2, "genuine_contact_live_bytes": True},
            "death_blank_timer37": {"death_state": 3, "death_timer": 37,
                                     "entry_state": 0, "source_bytes_match": True,
                                     "death_blank_front_commit_observed": True,
                                     "death_blank_pixels_match_oracle": True,
                                     "death_blank_irq_commit_observed": True,
                                     "death_blank_live_code_span_qualified": True,
                                     "death_blank_front_mapping_qualified": True},
            "cue13_published_idle": {"cue13_actual_output": True, "published_busy": 0,
                                      "normal_drain": True,
                                      "cue13_emitted_end_observed": True,
                                      "actual_terminal_mute_observed": True},
            "replacement_entry_seed": {"prior_death_blank_observed": True,
                                       "prior_cue13_idle_observed": True, "entry_state": 2},
            "replacement_cue6_output": {"entry_seed_precedes_cue6": True, "selected_id": 6},
        }
        want = required[name]
        missing = [k for k in want if k not in observed]
        if missing:
            raise GuardFailure(f"life-cycle event {name} lacks live observations {missing}")
        bad = [(k, observed[k], v) for k, v in want.items() if observed[k] != v]
        if bad:
            raise GuardFailure(f"life-cycle event {name} does not meet its observed contract: {bad}")
        if name == "replacement_cue6_output" and (
                type(observed.get("audible_store_count")) is not int or observed["audible_store_count"] < 1):
            raise GuardFailure("replacement cue6 requires an actual selected-source audible store")
        if name == "death_blank_timer37" and (
                type(observed.get("death_blank_opaque_pixels_compared")) is not int or
                observed["death_blank_opaque_pixels_compared"] <= 0):
            raise GuardFailure("death blank proof requires an actual pixel-oracle comparison")
        self.records.append({"name": name, **observed})

    def _order_failures(self) -> list[str]:
        by_name = {item["name"]: item for item in self.records}
        failures = []
        for name, dependencies in self.DEPENDENCIES.items():
            record = by_name.get(name)
            if record is None:
                continue
            for dependency in dependencies:
                required = by_name.get(dependency)
                if required is None:
                    failures.append(f"{name} lacks prerequisite {dependency}")
                elif required["event_ordinal"] >= record["event_ordinal"]:
                    failures.append(f"{dependency} does not precede {name}")
        return failures

    def status(self) -> dict[str, Any]:
        present = {item["name"] for item in self.records}
        missing = [name for name in LIFECYCLE_EVENTS if name not in present]
        order_failures = self._order_failures()
        return {"status": "INCOMPLETE" if missing or order_failures else "ORDER_OBSERVED",
                "missing_events": missing, "order_failures": order_failures,
                "pass": not missing and not order_failures,
                "events": sorted(self.records, key=lambda item: item["event_ordinal"])}


def fixture_order_status(scenario: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    """Require the requested observable FRONT/audio completion order for an order fixture."""
    if scenario not in ("front-first", "music-first"):
        raise GuardFailure("fixture order comparison applies only to forced order scenarios")
    by_name = {record.get("name"): record for record in records}
    front = by_name.get("final_pose_in_front_after_irq_commit")
    idle = by_name.get("terminal_post_psg_busy_zero")
    missing = [name for name, record in (("final_pose_in_front_after_irq_commit", front),
                                          ("terminal_post_psg_busy_zero", idle))
               if record is None]
    if missing:
        return {"pass": False, "status": "MISSING_EVIDENCE", "missing": missing}
    front_ordinal = front.get("irq_commit_event_ordinal")
    front_record_ordinal = front.get("event_ordinal")
    idle_ordinal = idle.get("event_ordinal")
    front_busy = front.get("published_music_busy")
    if (type(front_ordinal) is not int or type(front_record_ordinal) is not int or
            front_record_ordinal != front_ordinal or
            front.get("same_stop_busy_sample") is not True or
            type(idle_ordinal) is not int or
            type(front_busy) is not int or front_busy not in (0, 1)):
        return {"pass": False, "status": "INVALID_EVIDENCE",
                "front_irq_commit_ordinal": front_ordinal,
                "front_record_ordinal": front_record_ordinal,
                "same_stop_busy_sample": front.get("same_stop_busy_sample"),
                "terminal_busy_zero_ordinal": idle_ordinal,
                "published_music_busy_at_front": front_busy}
    if scenario == "front-first":
        passed = front_ordinal < idle_ordinal and front_busy == 1
        expected = "final FRONT pose before terminal busy-zero while published busy remains one"
    else:
        passed = idle_ordinal < front_ordinal and front_busy == 0
        expected = "terminal busy-zero before final FRONT pose while published busy is zero"
    if (passed and (front.get("entry_marker_x") != 264 or
                    front.get("entry_seed_lives") != 0 or
                    front.get("visible_width_bytes") != 8 or
                    type(front.get("opaque_pixels_compared")) is not int or
                    front.get("opaque_pixels_compared", 0) <= 0)):
        passed = False
    return {"pass": passed, "status": "ORDER_OBSERVED" if passed else "ORDER_MISMATCH",
            "expected": expected, "front_ordinal": front_ordinal,
            "front_record_ordinal": front_record_ordinal,
            "terminal_busy_zero_ordinal": idle_ordinal,
            "published_music_busy_at_front": front_busy}


def prepare(build: Path) -> dict[str, Any]:
    build = build.resolve(strict=True)
    names = ("ladybug.rom", "ladybug-runtime.rom", "ladybug.map", "ladybug-sparse-layout.json",
             "ladybug-player-sparse.bin",
             "ladybug-audio-runtime.bin", "ladybug-audio-runtime.map",
             "ladybug-enemy-runtime.rom", "ladybug-enemy-runtime.map",
             "ladybug-presentation-runtime.bin", "ladybug-presentation-runtime.map")
    files = {name: build / name for name in names}
    missing = [str(p) for p in files.values() if not p.is_file()]
    if missing:
        raise GuardFailure("candidate build is incomplete: " + ", ".join(missing))
    rom_bytes = files["ladybug.rom"].read_bytes()
    bootstrap_reset = derive_bootstrap_reset_qualification(build, rom_bytes)
    layout = json.loads(files["ladybug-sparse-layout.json"].read_text(encoding="utf-8"))
    validate_layout_final_image_identity(layout, sha(rom_bytes))
    main, audio, enemy, presentation = (read_symbols(files[n]) for n in
        ("ladybug.map", "ladybug-audio-runtime.map", "ladybug-enemy-runtime.map",
         "ladybug-presentation-runtime.map"))
    required = {
        "main": ("DEATH_TIMER", "DEATH_STATE", "INITIAL_ENTRY_STATE", "PLAYER_CELL_X",
                 "PLAYER_CELL_Y", "PLAYER_STEP", "PLAYER_DIR", "PLAYER_FACE", "PLAYER_ANIM",
                 "PLAYER_TICK_PENDING", "PLAYER_BG_PTR",
                 "PLAYER_BG_VALID", "FB_RENDER_PENDING", "FB_COMMIT_SEQ", "FB_FRONT_ID", "PLAYER_FB",
                 "FB_META_A", "FB_META_B", "FBM_PLAYER_VALID",
                 "FRAMES", "LIVES", "PRES_MODE", "ENEMY_TABLE",
                 "asset_end",
                 "marker_entry_begin", "iet_offscreen", "iet_maze_entry", "iet_final_wait",
                 "mainloop"),
        "audio": ("audio_slot0", "audio_slot1", "audio_slot2", "audio_slot3",
                  "audio_music_count", "audio_music_queue", "audio_mix_order", "AUDIO_MIX_COUNT",
                  "AUDIO_Q_COUNT", "AUDIO_CREDIT_PENDING", "audio_mix_periods", "audio_mix_atten", "audio_mix_noise",
                  "audio_mix_shadow", "AUDIO_BEST_SLOT", "AUDIO_BEST_PRI",
                  "AUDIO_MUSIC_PUBLISHED_BUSY", "audio_mix_write", "audio_mix_write_done",
                  "audio_write", "audio_music_busy", "audio_command_end", "gmc_cue_descriptors",
                  "gmc_cue_stream_06", "gmc_cue_stream_13", "gmc_sound_data_end"),
        "enemy": ("framebuffer_irq_impl", "fbiq_publish", "fbiq_done", "et_player_death",
                  "FBM_PLAYER_FB"),
        "presentation": ("presentation_flow_tick", "add_credit", "pft_ready",
                         "pft_single_credit", "PRES_MAGIC", "PRES_CREDITS", "PRES_EVENT",
                         "MODE_ATTRACT"),
    }
    maps = {"main": main, "audio": audio, "enemy": enemy, "presentation": presentation}
    absent = [f"{domain}.{symbol}" for domain, symbols in required.items()
              for symbol in symbols if symbol not in maps[domain]]
    if absent:
        raise GuardFailure("required map symbols absent: " + ", ".join(absent))
    if main["DEATH_TIMER"] != TIMER_ADDRESS:
        raise GuardFailure(f"DEATH_TIMER map resolves to ${main['DEATH_TIMER']:04X}, not $003A")
    if (presentation["presentation_flow_tick"] != 0x1900 or
            presentation["PRES_CREDITS"] != PRES_CREDITS_ADDRESS or
            presentation["PRES_EVENT"] != 0x00A9 or presentation["MODE_ATTRACT"] != MODE_ATTRACT):
        raise GuardFailure("presentation map disagrees with the source-qualified cold-credit state")
    audio_bin = files["ladybug-audio-runtime.bin"].read_bytes()
    source_dir = build.parent / "src"
    sources = {name: source_dir / name for name in
               ("main.s", "audio_runtime.s", "enemy_runtime.s", "keybinding_runtime.s",
                "presentation_runtime.s")}
    if any(not p.is_file() for p in sources.values()):
        raise GuardFailure("candidate source audit files are missing beside the build")
    source_text = {name: re.sub(r"\s+", " ", re.sub(r";[^\n]*", " ", p.read_text(encoding="utf-8")))
                   for name, p in sources.items()}
    source_assertions = {
        "main.s": (r"DEATH_TIMER\s+equ\s+\$003A", r"iet_final_wait"),
        "audio_runtime.s": (r"lda\s+,u\s+sta\s+2,y", r"lda\s+2,x\s+bita\s+#1",
                             r"audio_mix_write_done\s+jsr\s+audio_music_busy\s+sta\s+AUDIO_MUSIC_PUBLISHED_BUSY",
                             r"audio_write\s+sta\s+SND_DATA",
                             r"audio_command_end\s+lda\s+#\$FF\s+sta\s+,y\s+rts"),
        "enemy_runtime.s": (r"fbiq_publish\s+sta\s+GIME_VOFF1", r"inc\s+FB_COMMIT_SEQ\+1"),
        "keybinding_runtime.s": (r"KB_BIND\s+equ\s+\$0287", r"INPUT_JOYSTICK\s+equ\s+0",
                                 r"KB_FIXED_COIN_5\s+equ\s+44"),
        "presentation_runtime.s": (r"org\s+\$1900", r"PRES_CREDITS\s+equ\s+\$00A8",
                                   r"PRES_MAGIC\s+equ\s+\$00A4", r"PRES_EVENT\s+equ\s+\$00A9",
                                   r"MODE_ATTRACT\s+equ\s+2",
                                   r"pft_single_credit\s+bsr\s+add_credit"),
    }
    checked_source_patterns = {}
    for name, patterns in source_assertions.items():
        for pattern in patterns:
            if not re.search(pattern, source_text[name], re.I):
                raise GuardFailure(f"candidate source invariant missing: {name}: {pattern}")
        checked_source_patterns[name] = {"sha256": sha(sources[name].read_bytes()),
                                         "patterns_checked": list(patterns)}
    desc_index = audio["gmc_cue_descriptors"] - 0xA000 + 6 * 8
    cue6_desc = audio_bin[desc_index:desc_index + 8]
    if len(cue6_desc) != 8 or cue6_desc[0] != 0xB3 or (cue6_desc[0] >> 5) != 5:
        raise GuardFailure("linked cue-6 descriptor does not prove exclusive policy $B3 / priority 5")
    cue6_ptr = int.from_bytes(cue6_desc[4:6], "big")
    if cue6_ptr != audio["gmc_cue_stream_06"] or cue6_desc[6] != 0x07:
        raise GuardFailure("cue-6 linked descriptor pointer/voice mask disagrees with map")
    cue6_end = stream_terminal(audio_bin, cue6_ptr - 0xA000,
                               audio["gmc_sound_data_end"] - 0xA000)
    cue13_desc_index = desc_index + (13 - 6) * 8
    cue13_desc = audio_bin[cue13_desc_index:cue13_desc_index + 8]
    if (len(cue13_desc) != 8 or cue13_desc[0] != 0xD3 or
            int.from_bytes(cue13_desc[4:6], "big") != audio["gmc_cue_stream_13"]):
        raise GuardFailure("linked cue-13 descriptor does not prove exclusive cue-13 routing")
    cue13_end = stream_terminal(audio_bin, audio["gmc_cue_stream_13"] - 0xA000,
                                audio["gmc_sound_data_end"] - 0xA000)
    if audio["audio_mix_write_done"] + 6 > audio["audio_write"]:
        raise GuardFailure("audio post-publication marker ordering is inconsistent with map")
    enemy_image = files["ladybug-enemy-runtime.rom"].read_bytes()
    irq_marker = irq_commit_marker(enemy_image, enemy)
    post_busy_pc = post_busy_marker(audio_bin, audio)
    bus_marker = audio_bus_write_marker(audio_bin, audio)
    player_art = verify_candidate_player_art(build)
    identity = {name: {"bytes": p.stat().st_size, "sha256": sha(p.read_bytes())}
                for name, p in files.items()}
    return {
        "candidate_build": str(build), "files": identity,
        "candidate_sources": checked_source_patterns,
        "mapped_symbols": {d: {s: maps[d][s] for s in symbols}
                           for d, symbols in required.items()},
        "cue_descriptors": {"cue6_hex": cue6_desc.hex(), "cue6_policy": "exclusive, $B3, priority 5, voice mask $07",
                             "cue13_hex": cue13_desc.hex(), "cue13_policy": "exclusive, $D3, priority 6"},
        "emitted_stream_boundaries": {
            "cue6": {**cue6_end, "stream_start": audio["gmc_cue_stream_06"],
                     "terminator_address": 0xA000 + cue6_end["terminator_offset"],
                     "terminal_x_expected": 0xA000 + cue6_end["terminal_next_offset"]},
            "cue13": {**cue13_end, "stream_start": audio["gmc_cue_stream_13"],
                      "terminator_address": 0xA000 + cue13_end["terminator_offset"],
                      "terminal_x_expected": 0xA000 + cue13_end["terminal_next_offset"]}},
        "irq_commit_instruction": irq_marker,
        "audio_bus_store": bus_marker,
        "bootstrap_reset_qualification": bootstrap_reset,
        "post_psg_busy_marker": {"pc": post_busy_pc,
            "derived_from_linked_jsr_and_sta": True},
        "player_art_identity": player_art,
        "observer_adapter": {
            "implemented": LIVE_CAPTURE_IMPLEMENTED,
            "monitor_controls": ["events.subscribe", "set_breakpoint", "set_watchpoint",
                "run", "read_registers", "wait_for_stop", "pause", "read_memory",
                "get_run_state", "inject_key", "single guarded write_memory for forced fixtures"],
            "offline_only_in_this_preparation": True,
            "live_invocation_requires": ["complete adaptive keyboard source-build receipt",
                "parent-accepted GDB-MCP delivery receipt", "fresh output directory",
                "explicit scenario and XRoar binary"],
            "event_capture": ["source/staged/live bootstrap reset-store spans and PAR mapping before resident/runtime events",
                "source/staged/live bytes and PAR", "selected cue PSG stores",
                "emitted END and terminal slot-clear/mute/busy tail", "post-instruction IRQ sequence commit",
                "physical FRONT pixels against candidate player frames", "same-stop fixture guard recapture"],
            "natural_route": "ordinary keyboard-only search at accepted gameplay centers; absent genuine contacts time out and fail",
            "natural_held_input_challenge": (
                "At first state 2 of each natural initial/replacement entry, hold the live South binding translated from $0287 matrix identity to DSCAN. "
                "Audit all automatic logical poses, direction/facing, and actual FRONT poses through states 2/3/4. "
                "Release only in final state-4 wait after the entry's terminal post-PSG busy-zero and IRQ-committed final FRONT proofs. "
                "Require three entry witnesses and zero target RAM writes; forced fixtures do not run this challenge."),
            "bootstrap_reset_stores": (
                "Derive each watched SND_DATA reset immediate, store span, and post-store PC from the current complete source receipt, bootstrap source/listing/map, staged image, and packaged bank zero. "
                "At each ordered no-breakpoint-ID stop, require halted get_run_state at the exact PC, expected accumulator value, PAR_EXEC+6 mapping, and equal staged/CPU/physical bytes before runtime event classification."),
        },
        "timer_write_policy": "one map-resolved $003A write per fresh forced run; natural is no-write",
        "runtime_probe_performed": False,
        "runtime_ready": False,
        "observer_model_corrections": {
            "resident_image_receipt": (
                "The main runtime receipt assembles the raw resident prefix ending at map asset_end. "
                "Compare that prefix hash to the invocation hash, compare the full 16 KiB staged image hash to the receipt artifact hash, "
                "and require the remaining staged bytes to be FF."),
            "source_receipt_layout_split": (
                "The source-build receipt contains ten strict artifact hashes and omits sparse-layout by design. "
                "Bind the current sparse-layout final_image_sha256 to the current ROM and player payload, then require the parent delivery receipt to match all eleven current artifact hashes including layout."),
            "psg_period_data": "raw low/high bytes AD 02 produce latch 8D and data 2A",
            "quiet_default": "audio_mix_clear raw 01 00 is little-endian period 1",
            "irq_commit": (
                f"candidate-emitted {irq_marker['encoding']} INC $93 at ${irq_marker['pc']:04X} "
                f"ends at ${irq_marker['end_pc']:04X}; " +
                (f"requires DP=${irq_marker['required_dp']:02X}" if irq_marker["required_dp"] is not None
                 else "extended form has no direct-page requirement")),
            "proof_order": "audio and FRONT are independent branches; release joins busy-zero and final FRONT",
            "replacement_order": "actual death-blank FRONT proof and cue13 normal drain both precede replacement entry",
            "cue6_wait_service": "tone-latch-only actual batches are accepted after onset; onset needs selected-source data/attenuation output",
            "selected_voice_minimum": "at least one selected audible cue voice; no fixed count of three",
            "natural_held_south_challenge": (
                "Natural only: hold the live South DSCAN binding from first state 2 of each initial/replacement entry through states 2/3/4. "
                "Verify every programmed logical 2-pixel pose and actual FRONT pose without changing automatic direction/facing, link press/release events to that entry's live matrix binding, "
                "and require three witnesses plus zero target RAM writes. Release only at state-4 final wait after actual terminal post-PSG busy-zero and IRQ-committed final FRONT. "
                "The source may combine 318-to-320 and state-2-to-state-3 in one callback; the row-derived final walkout pose can first appear in state 3. Forced fixtures are challenge-free."),
            "bootstrap_reset_separation": (
                "The four authored reset attenuation stores are a separate ordered bootstrap event stream, not owned runtime PSG cue output. Unknown, malformed, reordered, remapped, wrong-value, or byte-mismatched watchpoint events fail closed."),
        },
        "gameplay_worklist_timing": {
            "target_cycles_max_per_required_worklist": GAMEPLAY_WORKLIST_CYCLE_TARGET,
            "historical_production_observations": HISTORICAL_GAMEPLAY_WORKLIST_CYCLES,
            "observer_preparation_measurement": "not measured; separate from runtime observer readiness",
        },
        "blocked_observable": (
            "The live event adapter is implemented behind --run-live, but this preparation step captures no runtime scenario and claims no natural held-input witness. "
            "Live execution requires the exact complete adaptive keyboard build receipt, parent-accepted GDB-MCP delivery receipt, fresh output directory, and explicit scenario/XRoar binary. "
            "Natural cold start and two genuine enemy-contact replacements use ordinary keyboard inputs only; missing required events or held-pose coverage fail closed within named deadlines. "
            "Offline fakes are not runtime acceptance evidence; parent source/control review and runtime evidence audit remain required."),
    }


def require_adaptive_keyboard_profile(build: Path) -> dict[str, Any]:
    """Reject isolated/nonadaptive receipts before process creation."""
    receipt_path = build / "source-build-receipt.json"
    if not receipt_path.is_file():
        raise GuardFailure("live run requires a complete source-build-receipt.json")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("state") != "complete" or receipt.get("profile") != "complete":
        raise GuardFailure("live run requires a completed complete-profile source receipt")
    invocations = [x for x in receipt.get("invocations", [])
                   if x.get("source", "").replace("\\", "/") == "src/main.s" and
                   Path(str(x.get("output", ""))).name == "ladybug-runtime.rom"]
    if not invocations:
        raise GuardFailure("receipt has no main runtime assembly invocation")
    final = invocations[-1]
    arguments = final.get("arguments", [])
    if "-DADAPTIVE_RENDERING=1" not in arguments:
        raise GuardFailure("live acceptance requires the adaptive main runtime profile")
    if "-DINPUT_JOYSTICK=0" not in arguments:
        raise GuardFailure("live acceptance requires the keyboard input profile")
    if "-DCOMPLETE_PROFILE=1" not in arguments:
        raise GuardFailure("live acceptance requires the complete keyboard build invocation")
    staged_path = build / "ladybug-runtime.rom"
    if not staged_path.is_file():
        raise GuardFailure("staged resident image is missing")
    staged = staged_path.read_bytes()
    artifacts = receipt.get("artifacts", {})
    main_symbols = read_symbols(build / "ladybug.map")
    resident_qualification = qualify_staged_resident_image(
        main_symbols.get("asset_end"), staged, final.get("assembled_sha256"),
        artifacts.get("ladybug-runtime.rom") if isinstance(artifacts, dict) else None)
    candidate_artifact_hashes = {}
    for name in SOURCE_RECEIPT_HASH_FILES:
        artifact = build / name
        candidate_artifact_hashes[name] = sha(artifact.read_bytes()) if artifact.is_file() else None
    validate_source_receipt_artifact_hashes(artifacts, candidate_artifact_hashes)
    source_inputs = {str(k).replace("\\", "/"): v for k, v in receipt.get("inputs", {}).items()}
    source_hashes = {}
    for name in ("main.s", "audio_runtime.s", "enemy_runtime.s", "keybinding_runtime.s",
                 "presentation_runtime.s"):
        source = build.parent / "src" / name
        if not source.is_file():
            raise GuardFailure(f"complete-profile source {name} is unavailable beside the candidate build")
        source_hash = sha(source.read_bytes())
        if source_inputs.get(f"src/{name}") != source_hash:
            raise GuardFailure(f"candidate {name} source hash is not the one captured by the build receipt")
        source_hashes[name] = source_hash
    return {"receipt": str(receipt_path), "receipt_sha256": sha(receipt_path.read_bytes()),
            "profile": "complete / adaptive / keyboard", "invocation": final,
            "staged_resident_sha256": resident_qualification["staged_sha256"],
            "resident_image_qualification": resident_qualification,
            "source_hashes": source_hashes}


DELIVERY_RECEIPT_SCHEMA = "ladybug.gdb-mcp-delivery-qualification.v1"
DELIVERY_HASH_FILES = ("ladybug.rom", "ladybug-runtime.rom", "ladybug.map",
                       "ladybug-audio-runtime.bin", "ladybug-audio-runtime.map",
                       "ladybug-enemy-runtime.rom", "ladybug-enemy-runtime.map",
                       "ladybug-presentation-runtime.bin", "ladybug-presentation-runtime.map",
                       "ladybug-player-sparse.bin", "ladybug-sparse-layout.json")
SOURCE_RECEIPT_HASH_FILES = tuple(name for name in DELIVERY_HASH_FILES
                                  if name != "ladybug-sparse-layout.json")


def qualify_staged_resident_image(asset_end: int | None, staged: bytes,
                                  assembled_sha256: Any,
                                  receipt_artifact_sha256: Any) -> dict[str, Any]:
    """Bind the raw assembled prefix, map-derived padding boundary, and full staged artifact."""
    if (type(asset_end) is not int or not RESIDENT_IMAGE_BASE < asset_end <=
            RESIDENT_IMAGE_BASE + RESIDENT_IMAGE_BYTES):
        raise GuardFailure("resident asset_end map symbol is outside the staged image")
    raw_length = asset_end - RESIDENT_IMAGE_BASE
    if len(staged) != RESIDENT_IMAGE_BYTES or not 0 < raw_length <= len(staged):
        raise GuardFailure("staged resident image size or map-derived raw length is invalid")
    raw_sha256 = sha(staged[:raw_length])
    if not isinstance(assembled_sha256, str) or raw_sha256 != assembled_sha256:
        raise GuardFailure("map-derived staged resident prefix differs from its assembly invocation")
    staged_sha256 = sha(staged)
    if not isinstance(receipt_artifact_sha256, str) or staged_sha256 != receipt_artifact_sha256:
        raise GuardFailure("full staged resident image differs from its source receipt artifact")
    if staged[raw_length:] != b"\xFF" * (len(staged) - raw_length):
        raise GuardFailure("staged resident image has non-FF bytes after mapped asset_end")
    return {"asset_end": asset_end, "raw_length": raw_length,
            "raw_prefix_sha256": raw_sha256, "assembled_sha256": assembled_sha256,
            "staged_sha256": staged_sha256,
            "padding_bytes": len(staged) - raw_length, "padding_byte": "FF"}


def validate_source_receipt_artifact_hashes(receipt_artifacts: Any,
                                            candidate_hashes: dict[str, Any]) -> None:
    """Check the ten source-receipt artifacts; sparse-layout identity is checked separately."""
    if not isinstance(receipt_artifacts, dict):
        raise GuardFailure("complete source receipt has no artifact hash table")
    missing = [name for name in SOURCE_RECEIPT_HASH_FILES
               if not isinstance(receipt_artifacts.get(name), str) or
               not isinstance(candidate_hashes.get(name), str)]
    if missing:
        raise GuardFailure("source receipt or candidate is missing required artifacts: " + ", ".join(missing))
    mismatched = [name for name in SOURCE_RECEIPT_HASH_FILES
                  if receipt_artifacts[name] != candidate_hashes[name]]
    if mismatched:
        raise GuardFailure("candidate artifacts differ from the complete source-build receipt: " +
                           ", ".join(mismatched))


def validate_delivery_receipt(receipt: dict[str, Any], preparation: dict[str, Any]) -> dict[str, Any]:
    """Require an explicit parent-accepted GDB-MCP copy/map qualification receipt."""
    if receipt.get("schema") != DELIVERY_RECEIPT_SCHEMA or receipt.get("status") != "parent-accepted":
        raise GuardFailure("live run requires a parent-accepted GDB-MCP delivery qualification receipt")
    hashes = receipt.get("artifact_sha256")
    if not isinstance(hashes, dict):
        raise GuardFailure("delivery receipt has no artifact_sha256 table")
    expected = {name: preparation.get("files", {}).get(name, {}).get("sha256")
                for name in DELIVERY_HASH_FILES}
    absent = [name for name, value in expected.items() if not value]
    if absent:
        raise GuardFailure("candidate identity lacks required delivery artifacts: " + ", ".join(absent))
    mismatched = [name for name, value in expected.items() if hashes.get(name) != value]
    if mismatched:
        raise GuardFailure("GDB-MCP delivery receipt artifact hashes differ: " + ", ".join(mismatched))
    for field in ("source_to_staged_bytes_match", "staged_sparse_copy_identity",
                  "destination_live_bytes_match", "live_par_mapping_qualified"):
        if receipt.get(field) is not True:
            raise GuardFailure(f"delivery receipt lacks required qualification {field}")
    return {"schema": DELIVERY_RECEIPT_SCHEMA, "status": "parent-accepted",
            "receipt_sha256": sha(json.dumps(receipt, sort_keys=True).encode()),
            "artifact_sha256": expected, "mapping_and_copy_qualified": True,
            "source_to_staged_bytes_match": True, "staged_sparse_copy_identity": True,
            "destination_live_bytes_match": True, "live_par_mapping_qualified": True}


def monitor_api() -> Any:
    """Import the maintained protocol/control definitions without calling launch()."""
    if MONITOR_TEMPLATE is None or not MONITOR_TEMPLATE.is_file():
        raise GuardFailure("maintained BUG-009 monitor client template is unavailable")
    name = "bug117_guarded_monitor_template"
    spec = importlib.util.spec_from_file_location(name, MONITOR_TEMPLATE)
    if spec is None or spec.loader is None:
        raise GuardFailure("cannot load maintained monitor client template")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def monitor_bytes(client: Any, address: int, length: int, space: str = "cpu") -> bytes:
    if space not in ("cpu", "physical") or type(address) is not int or type(length) is not int or length < 0:
        raise GuardFailure("invalid read-only monitor byte request")
    result = monitor_call(client, "read_memory", {"addr": address, "length": length, "space": space})
    data = bytes.fromhex(result.get("data", ""))
    if len(data) != length or result.get("space", space) != space:
        raise GuardFailure("monitor returned an incomplete or wrong-space byte read")
    return data


def monitor_word(client: Any, address: int) -> int:
    return int.from_bytes(monitor_bytes(client, address, 2), "big")


def physical_page_read(client: Any, page: int, offset: int, length: int) -> bytes:
    if not 0 <= page < 64 or offset < 0 or length < 0 or offset + length > PHYSICAL_PAGE_BYTES:
        raise GuardFailure("physical page read crosses an 8-KiB bank or 512-KiB RAM")
    return monitor_bytes(client, page * PHYSICAL_PAGE_BYTES + offset, length, "physical")


def byte_evidence(data: bytes) -> dict[str, Any]:
    return {"length": len(data), "hex": data.hex(), "sha256": sha(data)}


def live_span_mismatch_context(client: Any, cpu_address: int, expected: bytes,
                               staged: bytes, physical: bytes, page_register: int,
                               raw_par: int, mapped_page: int, cpu_window: int,
                               stop_context: dict[str, Any] | None) -> dict[str, Any]:
    """Retain numeric stop, mapping, byte, and halted-state facts before symbol use."""
    context: dict[str, Any] = {
        "kind": "live-physical-byte-mismatch",
        "interpretation_order": "numeric stopped PC and caller/candidate/CPU/physical bytes retained before observer marker-label interpretation",
        "stop": stop_context,
        "span": {
            "cpu_address": cpu_address, "cpu_address_hex": f"${cpu_address:04X}",
            "length": len(expected), "cpu_window": cpu_window,
            "cpu_window_end_exclusive": cpu_window + PHYSICAL_PAGE_BYTES,
            "page_register_address": page_register,
            "page_register_address_hex": f"${page_register:04X}",
            "expected_page": mapped_page, "expected_page_hex": f"${mapped_page:02X}",
            "physical_page": mapped_page,
            "physical_offset": cpu_address - cpu_window,
            "physical_address": mapped_page * PHYSICAL_PAGE_BYTES + cpu_address - cpu_window,
        },
        "mapping": {"par_raw": raw_par, "par_raw_hex": f"${raw_par:02X}",
            "par_mask": 0x3F, "par_masked": raw_par & 0x3F,
            "par_masked_hex": f"${raw_par & 0x3F:02X}",
            "expected_page": mapped_page},
        "bytes": {"caller_expected": byte_evidence(expected),
            "candidate_staged": byte_evidence(staged),
            "live_physical": byte_evidence(physical)},
        "stopped_status": {"state": "not-read", "read_error": None},
    }
    try:
        cpu_live = monitor_bytes(client, cpu_address, len(expected))
        context["bytes"]["live_cpu_window"] = byte_evidence(cpu_live)
    except Exception as exc:
        context["bytes"]["live_cpu_window_read_error"] = f"{type(exc).__name__}: {exc}"
    try:
        status = monitor_call(client, "get_run_state", maximum=2.0)
        context["stopped_status"] = {"state": status.get("state"),
            "last_stop_reason": status.get("last_stop_reason"),
            "last_stop_pc": status.get("last_stop_pc"),
            "last_stop_bp_id": status.get("last_stop_bp_id"),
            "run_state_reply": status, "read_error": None}
    except Exception as exc:
        context["stopped_status"] = {"state": "unavailable",
            "read_error": f"{type(exc).__name__}: {exc}"}
    return context


def require_current_paused_stop(client: Any, expected_pc: int) -> dict[str, int]:
    """Prove the target is still halted at the exact event before fresh guard reads."""
    status = monitor_call(client, "get_run_state")
    regs = monitor_call(client, "read_registers")
    if (status.get("state") != "halted" or status.get("last_stop_reason") != "breakpoint" or
            status.get("last_stop_pc") != expected_pc or regs.get("pc") != expected_pc):
        raise GuardFailure("fresh fixture read is not at the same paused monitor stop")
    return regs


def matrix_binding_to_dscan(matrix_key: int) -> int:
    """Translate CoCo column*8+row identity to XRoar's CoCo DSCAN identity."""
    if type(matrix_key) is not int or not 0 <= matrix_key < 64:
        raise GuardFailure("live keyboard matrix binding is outside the eight-column table")
    column, physical_row = divmod(matrix_key, 8)
    if physical_row == 7:
        raise GuardFailure("live keyboard matrix binding names an absent CoCo row")
    scan_row = 6 if physical_row == 6 else (physical_row + 2) % 6
    dscan = scan_row * 8 + column
    if not 0 <= dscan < 0x3F:
        raise GuardFailure("live keyboard matrix binding has no XRoar CoCo scan code")
    return dscan


def framebuffer_row_x(pointer: int) -> int:
    if type(pointer) is not int or not VISIBLE_BASE <= pointer < VISIBLE_BASE + VISIBLE_BYTES:
        raise GuardFailure("player framebuffer pointer is outside the visible image")
    return ((pointer - VISIBLE_BASE) % 160) * 2


def entry_row_x(pointer: int, entry_start_fb: int, marker_x: int) -> int:
    """Recover the walkout x position from its known start row, including x=320."""
    if type(marker_x) is not int or marker_x < 0 or marker_x > 318 or marker_x % 2:
        raise GuardFailure("entry marker x is not an even visible pixel coordinate")
    if type(pointer) is not int or type(entry_start_fb) is not int:
        raise GuardFailure("entry framebuffer pointer is not an integer")
    row_base = entry_start_fb - marker_x // 2
    byte_column = pointer - row_base
    if not 0 <= byte_column <= 160:
        raise GuardFailure("walkout pointer escaped its marker row before x=320")
    return byte_column * 2


def natural_held_input_status(entries: list[dict[str, Any]],
                              input_events: list[dict[str, Any]],
                              target_memory_write_count: int) -> dict[str, Any]:
    """Require one complete held-South witness and press/release pair per natural life."""
    by_generation = {entry.get("index"): entry.get("held_input_challenge")
                     for entry in entries if isinstance(entry.get("held_input_challenge"), dict)}
    challenge_events = [event for event in input_events if event.get("reason") in (
        "natural-entry-held-south-isolation", "natural-entry-audio-and-final-front-release")]
    event_sequences = {
        generation: [event for event in challenge_events
                     if event.get("entry_generation") == generation]
        for generation in (1, 2, 3)}
    def event_pair_matches_witness(generation: int, events: list[dict[str, Any]]) -> bool:
        witness = by_generation.get(generation)
        if not isinstance(witness, dict) or len(events) != 2:
            return False
        matrix_key = witness.get("matrix_key")
        try:
            expected_dscan = matrix_binding_to_dscan(matrix_key)
        except GuardFailure:
            return False
        return (witness.get("dscan_key") == expected_dscan and
            events[0].get("key") == expected_dscan and events[1].get("key") == expected_dscan and
            events[0].get("matrix_key") == matrix_key and events[1].get("matrix_key") == matrix_key and
            events[0].get("ordinal") == witness.get("press_ordinal") and
            events[1].get("ordinal") == witness.get("release_ordinal"))
    event_pairs_valid = all(
        len(events) == 2 and [event.get("action") for event in events] == ["press", "release"] and
        all(event.get("direction") == "south" and event.get("key_namespace") == "DSCAN" and
            event.get("target_memory_write") is False for event in events) and
        events[0].get("key") == events[1].get("key") and
        event_pair_matches_witness(generation, events)
        for generation, events in event_sequences.items()) and len(challenge_events) == 6
    witnesses_valid = len(entries) == 3 and all(
        isinstance(by_generation.get(generation), dict) and
        by_generation[generation].get("entry_generation") == generation and
        by_generation[generation].get("pass") is True and
        by_generation[generation].get("release_ordinal") is not None and
        by_generation[generation].get("press_ordinal", 0) <
            by_generation[generation].get("release_ordinal", 0)
        for generation in (1, 2, 3))
    no_target_writes = (target_memory_write_count == 0 and all(
        event.get("target_memory_write") is False for event in input_events))
    return {"required_witness_count": 3, "witness_count": len(by_generation),
        "pass_count": sum(item.get("pass") is True for item in by_generation.values()),
        "event_pairs_valid": event_pairs_valid,
        "target_memory_write_count": target_memory_write_count,
        "no_target_memory_writes": no_target_writes,
        "pass": witnesses_valid and event_pairs_valid and no_target_writes}


def fixture_audio_page(client: Any, stop_pc: int, mainloop_pc: int) -> int:
    """Allow physical audio-page reads only at the mapped resident fixture stop."""
    if stop_pc != mainloop_pc:
        raise GuardFailure("physical fixture audio reads are restricted to the resident mainloop stop")
    par5 = monitor_bytes(client, PAR5, 1)[0] & 0x3F
    if par5 != 0x34:
        raise GuardFailure(f"fixture mainloop requires restored PAR5=$34, observed ${par5:02X}")
    return 0x3D


def qualify_live_span(client: Any, cpu_address: int, expected: bytes, page_register: int,
                      mapped_page: int, cpu_window: int, linked_origin: int,
                      linked_image: bytes, delivery: dict[str, Any],
                      stop_context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Compare receipt-qualified source/staged identity and live physical bytes at a stop."""
    if (delivery.get("schema") != DELIVERY_RECEIPT_SCHEMA or
            delivery.get("status") != "parent-accepted" or
            not all(delivery.get(k) is True for k in (
                "source_to_staged_bytes_match", "staged_sparse_copy_identity",
                "destination_live_bytes_match", "live_par_mapping_qualified"))):
        raise GuardFailure("live code interpretation requires parent-accepted source/staged/delivery qualification")
    if (cpu_address < cpu_window or cpu_address + len(expected) > cpu_window + PHYSICAL_PAGE_BYTES or
            mapped_page >= 64):
        raise GuardFailure("live code span is outside its qualified 8-KiB mapping window")
    raw_par = monitor_bytes(client, page_register, 1)[0]
    live_map = raw_par & 0x3F
    if live_map != mapped_page:
        raise GuardFailure(f"live PAR ${page_register:04X} page ${live_map:02X} != expected ${mapped_page:02X}")
    image_offset = cpu_address - linked_origin
    staged = linked_image[image_offset:image_offset + len(expected)]
    if staged != expected:
        raise GuardFailure("caller expected bytes differ from candidate staged image")
    physical = physical_page_read(client, mapped_page, cpu_address - cpu_window, len(expected))
    if physical != staged:
        context = live_span_mismatch_context(client, cpu_address, expected, staged,
            physical, page_register, raw_par, mapped_page, cpu_window, stop_context)
        raise QualificationFailure("live physical module bytes differ from staged candidate bytes", context)
    return {"cpu_address": cpu_address, "page_register": page_register,
            "mapped_page": mapped_page, "length": len(expected),
            "sha256": sha(physical), "source_staged_live_match": True}


def live_audio_snapshot(client: Any, symbols: dict[str, int], page: int = 0x3D) -> dict[str, Any]:
    def audio_read(address: int, length: int) -> bytes:
        if not 0xA000 <= address < 0xC000 or address + length > 0xC000:
            raise GuardFailure("audio symbol is outside the page-$3D window")
        return physical_page_read(client, page, address - 0xA000, length)
    slots = [model_from_audio_slot(audio_read(symbols[f"audio_slot{i}"], 28), i)
             for i in range(4)]
    return {"slots": slots,
            "best_slot": monitor_bytes(client, symbols["AUDIO_BEST_SLOT"], 1)[0],
            "best_priority": monitor_bytes(client, symbols["AUDIO_BEST_PRI"], 1)[0],
            "mix_period_bytes": audio_read(symbols["audio_mix_periods"], 6),
            "mix_attenuation": audio_read(symbols["audio_mix_atten"], 3),
            "mix_noise": audio_read(symbols["audio_mix_noise"], 2),
            "mix_shadow": audio_read(symbols["audio_mix_shadow"], 11),
            "mix_order": audio_read(symbols["audio_mix_order"], 4),
            "mix_count": monitor_bytes(client, symbols["AUDIO_MIX_COUNT"], 1)[0],
            "music_count": audio_read(symbols["audio_music_count"], 1)[0],
            "music_queue": audio_read(symbols["audio_music_queue"], 8),
            "effect_queue_count": monitor_bytes(client, symbols["AUDIO_Q_COUNT"], 1)[0],
            "credit_pending": monitor_bytes(client, symbols["AUDIO_CREDIT_PENDING"], 1)[0],
            "published_busy": monitor_bytes(client, symbols["AUDIO_MUSIC_PUBLISHED_BUSY"], 1)[0]}


def verify_live_music_mix(snapshot: dict[str, Any], cue_id: int,
                          expected_policy: int, expected_priority: int) -> dict[str, Any]:
    model = model_exclusive_mix(snapshot["slots"], cue_id)
    selected = model["selected"]
    if selected["policy"] != expected_policy or selected["priority"] != expected_priority:
        raise GuardFailure("selected cue descriptor policy/priority differs from the approved route")
    if snapshot["best_slot"] != 0 or snapshot["best_priority"] != expected_priority:
        raise GuardFailure("live AUDIO_BEST_SLOT/PRI does not select cue slot zero")
    if snapshot["mix_period_bytes"] != model["period_bytes"]:
        raise GuardFailure("live mixed tone periods do not match selected cue voices")
    if snapshot["mix_attenuation"] != model["attenuation_bytes"]:
        raise GuardFailure("live mixed attenuation does not match selected cue voices")
    if snapshot["mix_noise"] != model["noise_bytes"]:
        raise GuardFailure("live mixed noise state does not match selected cue source")
    if model["audible_voice_count"] < 1 or not model["channel_sources"]:
        raise GuardFailure("selected cue has no audible tone channel in this mixer service")
    model["mix_match"] = True
    return model


class PSGTransaction:
    """Enforce exact live-store order between audio_mix_write and its post-PSG label."""
    def __init__(self, model: dict[str, Any], snapshot: dict[str, Any], require_audible: bool = False):
        self.model = model
        self.before = snapshot
        self.require_audible = require_audible
        self.expected = expected_psg_transaction(snapshot["mix_period_bytes"],
            snapshot["mix_attenuation"], snapshot["mix_noise"], snapshot["mix_shadow"],
            model["channel_sources"])
        self.observed: list[PSGStore] = []

    def store(self, a: int) -> None:
        i = len(self.observed)
        if i >= len(self.expected):
            raise GuardFailure("unexpected extra SND_DATA store inside audio_mix_write")
        expected = self.expected[i]
        if a != expected.value:
            raise GuardFailure(f"SND_DATA A=${a:02X} differs from modeled {expected.kind} ${expected.value:02X}")
        self.observed.append(expected)

    def finish(self) -> dict[str, Any]:
        if self.observed != self.expected:
            raise GuardFailure(f"actual PSG store sequence ended {len(self.observed)}/{len(self.expected)} stores")
        audible = (prove_audible_psg_source(self.model, self.observed)
                   if self.require_audible else {"audible_store_count": 0, "audible_channels": []})
        muted = sum(s.kind == "attenuation" and (s.value & 0x0F) == 15 for s in self.observed)
        return {"actual_store_count": len(self.observed), "modeled_store_count": len(self.expected),
                "audible_store_count": audible["audible_store_count"],
                "audible_channels": audible["audible_channels"],
                "actual_mute_attenuation_stores": muted,
                "all_mix_stores_match": True}


def stream_waits_remaining(image: bytes, stream_start: int, terminator: int,
                           pointer: int, current_wait: int) -> dict[str, int]:
    """Decode remaining authored waits from a live slot cursor and dwell byte."""
    if type(current_wait) is not int or not 0 <= current_wait <= 0xFF:
        raise GuardFailure("live stream dwell is not an unsigned byte")
    boundaries = {stream_start}
    pos = stream_start
    waits = 0
    while pos <= terminator:
        op = image[pos]
        if op == 0:
            if pos != terminator:
                raise GuardFailure("decoded stream terminator differs from the candidate boundary")
            boundaries.add(pos + 1)
            break
        if op == 2:
            size = 2
            ticks = image[pos + 1] or 1
            waits += ticks
        elif 0x10 <= op <= 0x12:
            size = 4
        elif op == 0x1C:
            size = 3
        elif op in (0x1D, 0x1E):
            size = 2
        else:
            raise GuardFailure(f"unsupported stream command ${op:02X} at ${pos:04X}")
        if pos + size > terminator:
            raise GuardFailure("stream command overlaps its emitted terminator")
        pos += size
        boundaries.add(pos)
    if pointer not in boundaries or not stream_start <= pointer <= terminator + 1:
        raise GuardFailure("live slot cursor is not an emitted cue command boundary")
    future_waits = 0
    pos = pointer
    while pos < terminator:
        op = image[pos]
        if op == 2:
            future_waits += image[pos + 1] or 1
            pos += 2
        elif 0x10 <= op <= 0x12:
            pos += 4
        elif op == 0x1C:
            pos += 3
        elif op in (0x1D, 0x1E):
            pos += 2
        else:
            raise GuardFailure(f"unsupported future stream command ${op:02X} at ${pos:04X}")
    return {"current_wait_ticks": current_wait, "future_wait_ticks": future_waits,
            "remaining_audio_ticks": current_wait + future_waits}


@dataclass(frozen=True)
class MonitorStop:
    phase: str
    pc: int
    bp_id: int | None
    registers: dict[str, int]
    ordinal: int
    observed_monotonic: float


class BoundedMonitorEventPump:
    """Run only to subscribed monitor stops; each wait and phase is bounded."""
    def __init__(self, client: Any, clock: Any = time.monotonic,
                 stop_wait_seconds: int = STOP_WAIT_SECONDS):
        if not 1 <= stop_wait_seconds <= STOP_WAIT_SECONDS:
            raise GuardFailure("monitor stop wait exceeds the approved 10-second bound")
        self.client = client
        self.clock = clock
        self.stop_wait_seconds = stop_wait_seconds
        self.ordinal = 0
        self.timeout_records: list[dict[str, Any]] = []
        self.consecutive_timeouts = 0

    def _timeout(self, phase: str, wait: float, reason: str) -> None:
        self.timeout_records.append({"phase": phase, "wait_seconds": wait, "reason": reason})
        self.consecutive_timeouts += 1

    def next_stop(self, phase: str, deadline: float) -> MonitorStop | None:
        remaining = deadline - self.clock()
        if remaining <= 0:
            return None
        wait = min(float(self.stop_wait_seconds), remaining)
        client_events = getattr(self.client, "events", None)
        event_offset = len(client_events) if isinstance(client_events, list) else 0
        state: dict[str, Any] = {}
        run_deadline_remaining = deadline - self.clock()
        if run_deadline_remaining <= 0:
            self._timeout(phase, wait, "phase-deadline-before-run")
            return None
        try:
            self.client.call("run", timeout=min(self.stop_wait_seconds, run_deadline_remaining))
            remaining = deadline - self.clock()
            if remaining > 0:
                bounded_wait = min(float(self.stop_wait_seconds), remaining)
                state = self.client.call("wait_for_stop",
                    {"timeout_ms": max(0, int(bounded_wait * 1000))}, timeout=bounded_wait)
        except (TimeoutError, socket.timeout):
            # Recheck a stop that raced the bounded synchronous monitor wait.
            state = {}
        if state.get("reason") == "breakpoint" and type(state.get("pc")) is int:
            hit = {"pc": state.get("pc"), "bp_id": state.get("bp_id"),
                   "reason": state.get("reason")}
        else:
            remaining = deadline - self.clock()
            if remaining <= 0:
                self._timeout(phase, wait, "phase-deadline-before-stop-recheck")
                return None
            state = self.client.call("wait_for_stop", {"timeout_ms": 0},
                                     timeout=min(self.stop_wait_seconds, remaining))
            if state.get("reason") == "breakpoint" and type(state.get("pc")) is int:
                hit = {"pc": state.get("pc"), "bp_id": state.get("bp_id"),
                       "reason": state.get("reason")}
            else:
                remaining = deadline - self.clock()
                if remaining <= 0:
                    self._timeout(phase, wait, "phase-deadline-before-pause-recheck")
                    return None
                self.client.call("pause", timeout=min(self.stop_wait_seconds, remaining))
                current_events = getattr(self.client, "events", None)
                raced = current_events[event_offset:] if isinstance(current_events, list) else []
                bp = next((item for item in reversed(raced) if item.get("method") == "bp" and
                           type(item.get("params", {}).get("pc")) is int), None)
                if bp is not None:
                    hit = {**bp["params"], "reason": "breakpoint"}
                else:
                    self._timeout(phase, wait, "no-stop-before-bounded-wait")
                    return None
        if not isinstance(hit, dict) or type(hit.get("pc")) is not int:
            raise GuardFailure(f"monitor stop for {phase} lacks an actual integer PC")
        remaining = deadline - self.clock()
        if remaining <= 0:
            self._timeout(phase, wait, "phase-deadline-before-register-read")
            return None
        regs = self.client.call("read_registers", timeout=min(self.stop_wait_seconds, remaining))
        if type(regs.get("pc")) is not int or regs["pc"] != hit["pc"]:
            raise GuardFailure("monitor event PC differs from the stopped 6809 PC")
        self.consecutive_timeouts = 0
        self.ordinal += 1
        return MonitorStop(phase, hit["pc"], hit.get("bp_id"), regs,
                           self.ordinal, self.clock())


class InputOnlySearch:
    """Pulse only existing keyboard bindings at stopped, live gameplay centers."""
    def __init__(self, client: Any, bindings: bytes):
        if len(bindings) != 5:
            raise GuardFailure("live keyboard binding table is incomplete")
        if len(set(bindings)) != 5:
            raise GuardFailure("live gameplay/enter bindings are not unique")
        self.client = client
        self.matrix_bindings = bindings
        self.bindings = bytes(matrix_binding_to_dscan(value) for value in bindings)
        self.direction = 0
        self.held: int | None = None
        self.held_matrix: int | None = None
        self.origin: tuple[int, int] | None = None
        self.last_pose: tuple[int, int, int] | None = None
        self.age_stops = 0
        self.actions: list[dict[str, Any]] = []

    def _inject(self, key: int, matrix_key: int | None, action: str,
                ordinal: int, reason: str) -> None:
        monitor_call(self.client, "inject_key", {"key": key, "action": action})
        self.actions.append({"key": key, "key_namespace": "DSCAN", "matrix_key": matrix_key,
                             "action": action, "stop_ordinal": ordinal,
                             "reason": reason, "direction_index": self.direction,
                             "no_progress_stops": self.age_stops,
                             "target_memory_write": False})

    def release(self, ordinal: int, reason: str) -> None:
        if self.held is not None:
            self._inject(self.held, self.held_matrix, "release", ordinal, reason)
            self.held = None
            self.held_matrix = None
            self.origin = None
            self.last_pose = None
            self.age_stops = 0

    def at_gameplay_center(self, ordinal: int, entry: int, death: int,
                           step: int, cell_x: int, cell_y: int) -> None:
        if entry != 0 or death != 0:
            self.release(ordinal, "entry-or-death-isolation")
            return
        if self.held is not None:
            pose = (cell_x, cell_y, step)
            if pose != self.last_pose:
                self.last_pose = pose
                self.origin = (cell_x, cell_y)
                self.age_stops = 0
                return
            self.age_stops += 1
            if step == 0 and self.age_stops >= 8:
                self.release(ordinal, "source-qualified-observed-no-progress-route-retry")
                self.direction = (self.direction + 1) % 4
            else:
                return
        if step != 0:
            return
        matrix_key = self.matrix_bindings[self.direction]
        key = self.bindings[self.direction]
        self.held = key
        self.held_matrix = matrix_key
        self.origin = (cell_x, cell_y)
        self.last_pose = (cell_x, cell_y, step)
        self.age_stops = 0
        self._inject(key, matrix_key, "press", ordinal, "hold-until-source-qualified-progress-or-blockage")


def decode_contact_search_state(low: bytes, symbols: dict[str, int]) -> dict[str, int]:
    """Decode route and enemy/timer state from an already-read low-RAM snapshot."""
    if not isinstance(low, bytes) or len(low) < 0x0300:
        raise GuardFailure("contact search requires the complete cached $0000-$02FF low-RAM snapshot")
    def byte(name: str) -> int:
        return low[symbols[name]]

    freeze_address = symbols["FREEZE_TIMER"]
    if freeze_address < 0 or freeze_address + 2 > len(low):
        raise GuardFailure("cached FREEZE_TIMER word is outside the low-RAM snapshot")
    return {
        "player_dir": byte("PLAYER_DIR"),
        "player_want": byte("PLAYER_WANT"),
        "box_timer": byte("BOX_TIMER"),
        "enemy_timer": byte("ENEMY_TIMER"),
        "enemy_active": byte("ENEMY_ACTIVE"),
        "enemy_released": byte("ENEMY_RELEASED"),
        "freeze_timer": int.from_bytes(low[freeze_address:freeze_address + 2], "big"),
    }


class LiveRuntimeObserver:
    """Bounded live event pump using only the maintained monitor controls."""
    def __init__(self, client: Any, build: Path, scenario: str,
                 preparation: dict[str, Any], delivery: dict[str, Any]):
        self.client = client
        self.build = build.resolve(strict=True)
        self.scenario = scenario
        self.preparation = preparation
        self.delivery = delivery
        self.pump = BoundedMonitorEventPump(client)
        self.main = read_symbols(build / "ladybug.map")
        self.audio = read_symbols(build / "ladybug-audio-runtime.map")
        self.enemy = read_symbols(build / "ladybug-enemy-runtime.map")
        self.main_image = (build / "ladybug-runtime.rom").read_bytes()
        self.audio_image = (build / "ladybug-audio-runtime.bin").read_bytes()
        self.enemy_image = (build / "ladybug-enemy-runtime.rom").read_bytes()
        self.presentation_image = (build / "ladybug-presentation-runtime.bin").read_bytes()
        self.presentation = read_symbols(build / "ladybug-presentation-runtime.map")
        self.bootstrap_image = (build / "ladybug-gmc-boot.rom").read_bytes()
        self.bootstrap_reset = preparation["bootstrap_reset_qualification"]
        self.bootstrap_reset_index = 0
        self.bootstrap_reset_events: list[dict[str, Any]] = []
        self.player_frame_table, self.player_art_identity = candidate_player_frame_table(build)
        self.irq_marker = preparation["irq_commit_instruction"]
        self.bus_marker = preparation["audio_bus_store"]
        self.post_busy_pc = preparation["post_psg_busy_marker"]["pc"]
        self.boundaries = preparation["emitted_stream_boundaries"]
        self.labels: dict[int, str] = {}
        self.bp_ids: dict[int, int] = {}
        self.watch_id: int | None = None
        self.events: list[dict[str, Any]] = []
        self.phases: list[dict[str, Any]] = []
        self.errors: list[str] = []
        self.failure_context: dict[str, Any] | None = None
        self.current_stop_context: dict[str, Any] | None = None
        self.last_runtime_state: dict[str, Any] | None = None
        self.last_runtime_state_stop: dict[str, Any] | None = None
        self.contact_search_timeout_context: dict[str, Any] | None = None
        self.input_events: list[dict[str, Any]] = []
        self.pressed: set[int] = set()
        self.bindings: bytes | None = None
        self.search: InputOnlySearch | None = None
        self.start_state = "coin-not-sent"
        self.cold_credited_start = False
        self.credit_baseline: int | None = None
        self.credit_call: dict[str, Any] | None = None
        self.credit_evidence: dict[str, Any] | None = None
        self.entry_count = 0
        self.entries: list[dict[str, Any]] = []
        self.current_entry: dict[str, Any] | None = None
        self.pending_entry_seed: dict[str, Any] | None = None
        self.proofs: dict[int, ProofLedger] = {}
        self.lifecycle: LifecycleOrder | None = None
        self.lifecycle_records: list[LifecycleOrder] = []
        self.previous_death: tuple[int, int] | None = None
        self.contact_count = 0
        self.contacts: list[dict[str, Any]] = []
        self.entry_contact_violation = False
        self.cue_output = {6: False, 13: False}
        self.cue_stream_active = {6: False, 13: False}
        self.cue_entry_owner: dict[int, int | None] = {}
        self.cue_start_ordinal: dict[int, int] = {}
        self.lifecycle_cue13_output = False
        self.cue_terminal: dict[int, dict[str, Any]] = {}
        self.quiet_tail: dict[int, dict[str, Any]] = {}
        self.pending_terminal_cues: set[int] = set()
        self.quiet_first_proofs: list[dict[str, Any]] = []
        self.quiet_refresh_records: list[dict[str, Any]] = []
        self.latest_mix: dict[int, dict[str, Any]] = {}
        self.active_tx: dict[str, Any] | None = None
        self.irq_before: dict[str, Any] | None = None
        self.irq_inc: dict[str, Any] | None = None
        self.fixture = None if scenario == "natural" else FixtureWriter(scenario, TIMER_ADDRESS)
        self.fixture_result: dict[str, Any] | None = None
        self.write_count = 0
        self.frames_at_cue6: int | None = None
        self.cue6_services = 0
        self.dwell_checks: list[dict[str, Any]] = []
        self.pose_hashes: list[str] = []
        self.last_pose: dict[str, Any] | None = None
        self.owner_history: dict[tuple[int, int], dict[str, Any]] = {}
        self.offscreen_owner_snapshots: dict[tuple[int, int], dict[str, Any]] = {}
        self.release_snapshot: dict[str, Any] | None = None
        self._previous_state: dict[str, Any] | None = None
        if self.main.get("DEATH_TIMER") != TIMER_ADDRESS:
            raise GuardFailure("candidate DEATH_TIMER map no longer resolves to $003A")

    def install(self) -> None:
        monitor_call(self.client, "events.subscribe", {"kinds": ["bp"]})
        wanted = {
            "marker_entry_begin": self.main["marker_entry_begin"],
            "iet_offscreen": self.main["iet_offscreen"],
            "iet_maze_entry": self.main["iet_maze_entry"],
            "iet_final_wait": self.main["iet_final_wait"],
            "mainloop": self.main["mainloop"],
            "add_credit": self.presentation["add_credit"],
            "audio_mix_write": self.audio["audio_mix_write"],
            "audio_command_end": self.audio["audio_command_end"],
            "post_psg_busy": self.post_busy_pc,
            "et_player_death": self.enemy["et_player_death"],
            "fbiq_publish": self.enemy["fbiq_publish"],
            "irq_commit_instruction_end": self.irq_marker["end_pc"],
            "fbiq_done": self.enemy["fbiq_done"],
        }
        for label, address in wanted.items():
            if address in self.labels:
                self.labels[address] += "+" + label
                continue
            result = monitor_call(self.client, "set_breakpoint", {"addr": address, "kind": "exec"})
            ident = result.get("id")
            if type(ident) is not int or ident < 1:
                raise GuardFailure(f"monitor did not install breakpoint {label}")
            self.labels[address] = label
            self.bp_ids[address] = ident
        watch = monitor_call(self.client, "set_watchpoint",
                             {"addr": SND_DATA, "length": 1, "kind": "w"})
        if type(watch.get("id")) is not int or watch["id"] < 1:
            raise GuardFailure("monitor did not install the SND_DATA write watchpoint")
        self.watch_id = watch["id"]

    def _resident_code(self, pc: int, size: int = 3) -> dict[str, Any]:
        if 0xC000 <= pc < 0xE000:
            reg, page, window = 0xFFA6, 0x3E, 0xC000
        elif 0xE000 <= pc <= 0xFFFF:
            reg, page, window = 0xFFA7, 0x3F, 0xE000
        else:
            raise GuardFailure(f"unexpected resident PC ${pc:04X}")
        offset = pc - 0xC000
        expected = self.main_image[offset:offset + size]
        if len(expected) != size:
            raise GuardFailure("resident marker span exceeds the staged image")
        return qualify_live_span(self.client, pc, expected, reg, page,
                                 window, 0xC000, self.main_image, self.delivery,
                                 self.current_stop_context)

    def _audio_code(self, pc: int, size: int = 3) -> dict[str, Any]:
        offset = pc - 0xA000
        expected = self.audio_image[offset:offset + size]
        if offset < 0 or len(expected) != size:
            raise GuardFailure("audio marker span exceeds the staged image")
        return qualify_live_span(self.client, pc, expected, PAR5, 0x3D,
                                 0xA000, 0xA000, self.audio_image, self.delivery,
                                 self.current_stop_context)

    def _enemy_code(self, pc: int, size: int = 3) -> dict[str, Any]:
        if not 0x0800 <= pc < 0x0800 + len(self.enemy_image):
            raise GuardFailure(f"PC ${pc:04X} is outside the copied enemy module")
        par0 = monitor_bytes(self.client, 0xFFA0, 1)[0] & 0x3F
        if par0 != 0x38:
            raise GuardFailure(f"enemy module requires PAR0=$38; live PAR0=${par0:02X}")
        offset = pc - 0x0800
        expected = self.enemy_image[offset:offset + size]
        live = physical_page_read(self.client, 0x38, pc & 0x1FFF, size)
        if len(expected) != size or live != expected:
            raise GuardFailure("live copied enemy-module bytes differ from the candidate")
        return {"cpu_address": pc, "mapped_page": 0x38, "page_register": 0xFFA0,
                "length": size, "sha256": sha(live), "source_staged_live_match": True}

    def _presentation_code(self, pc: int, size: int = 3) -> dict[str, Any]:
        origin = self.presentation["presentation_flow_tick"]
        offset = pc - origin
        expected = self.presentation_image[offset:offset + size]
        if offset < 0 or len(expected) != size:
            raise GuardFailure("presentation marker span exceeds its staged low-RAM image")
        live = monitor_bytes(self.client, pc, size)
        if live != expected:
            raise GuardFailure("live low-RAM presentation bytes differ from the staged candidate")
        return {"cpu_address": pc, "module_origin": origin, "length": size,
                "sha256": sha(live), "source_staged_live_match": True,
                "low_ram_copy_qualified": True}

    def _qualify_bootstrap_reset(self, stop: MonitorStop,
                                 expected: dict[str, Any]) -> dict[str, Any]:
        """Qualify a watched reset attenuation store before any runtime marker routing."""
        origin = self.bootstrap_reset["origin"]
        page_register = self.bootstrap_reset["page_register"]
        expected_page = self.bootstrap_reset["expected_page"]
        staged = bytes.fromhex(expected["span_hex"])
        post_pc_staged = bytes.fromhex(expected["post_pc_span_hex"])
        offset = expected["load_pc"] - origin
        staged_image_span = self.bootstrap_image[offset:offset + len(staged)]
        post_pc_offset = expected["post_store_pc"] - origin
        staged_post_pc = self.bootstrap_image[post_pc_offset:post_pc_offset + len(post_pc_staged)]
        context: dict[str, Any] = {
            "kind": "bootstrap-reset-store-qualification",
            "stop": self.current_stop_context,
            "expected": {**expected, "span": byte_evidence(staged),
                         "page_register": page_register, "expected_page": expected_page},
            "stopped_status": {"state": "not-read", "read_error": None},
            "mapping": {"expected_page": expected_page, "raw": None, "masked": None},
            "bytes": {"candidate_staged": byte_evidence(staged),
                      "packaged_staged": byte_evidence(staged_image_span),
                      "post_pc_expected": byte_evidence(post_pc_staged),
                      "post_pc_staged": byte_evidence(staged_post_pc)},
        }
        try:
            state = monitor_call(self.client, "get_run_state", maximum=2.0)
            context["stopped_status"] = {"state": state.get("state"),
                "last_stop_reason": state.get("last_stop_reason"),
                "last_stop_pc": state.get("last_stop_pc"),
                "last_stop_bp_id": state.get("last_stop_bp_id"),
                "reply": state, "read_error": None}
        except Exception as exc:
            context["stopped_status"] = {"state": "unavailable",
                "read_error": f"{type(exc).__name__}: {exc}"}
            raise QualificationFailure("bootstrap stop state is unavailable", context) from exc
        try:
            raw_par = monitor_bytes(self.client, page_register, 1)[0]
            context["mapping"].update({"raw": raw_par, "raw_hex": f"${raw_par:02X}",
                "masked": raw_par & 0x3F, "masked_hex": f"${raw_par & 0x3F:02X}",
                "mask": 0x3F})
            cpu_live = monitor_bytes(self.client, expected["load_pc"], len(staged))
            context["bytes"]["live_cpu"] = byte_evidence(cpu_live)
            cpu_post_pc = monitor_bytes(self.client, expected["post_store_pc"], len(post_pc_staged))
            context["bytes"]["live_cpu_at_post_pc"] = byte_evidence(cpu_post_pc)
            physical_page = raw_par & 0x3F
            physical_offset = expected["load_pc"] - origin
            physical_address = physical_page * PHYSICAL_PAGE_BYTES + physical_offset
            physical_live = physical_page_read(self.client, physical_page,
                physical_offset, len(staged))
            physical_post_offset = expected["post_store_pc"] - origin
            physical_post_live = physical_page_read(self.client, physical_page,
                physical_post_offset, len(post_pc_staged))
            context["span"] = {"cpu_address": expected["load_pc"],
                "cpu_window": origin, "physical_page": physical_page,
                "physical_offset": physical_offset, "physical_address": physical_address,
                "length": len(staged), "stopped_pc": expected["post_store_pc"],
                "stopped_pc_physical_address": (physical_page * PHYSICAL_PAGE_BYTES +
                    physical_post_offset), "stopped_pc_length": len(post_pc_staged)}
            context["bytes"]["live_physical"] = byte_evidence(physical_live)
            context["bytes"]["live_physical_at_post_pc"] = byte_evidence(physical_post_live)
        except Exception as exc:
            context["read_error"] = f"{type(exc).__name__}: {exc}"
            raise QualificationFailure("bootstrap source/staged/live evidence read failed", context) from exc

        valid_stop = (
            state.get("state") == "halted" and
            state.get("last_stop_reason") == "breakpoint" and
            state.get("last_stop_pc") == expected["post_store_pc"] and
            state.get("last_stop_bp_id", 0) in (None, 0) and
            stop.bp_id in (None, 0) and stop.pc == expected["post_store_pc"] and
            stop.registers.get("pc") == expected["post_store_pc"] and
            stop.registers.get("a") == expected["value"])
        if not valid_stop:
            raise QualificationFailure("bootstrap reset stop PC, watchpoint identity, status, or value is invalid",
                                        context)
        if context["mapping"].get("masked") != expected_page:
            raise QualificationFailure("bootstrap PAR_EXEC+6 mapping differs from the source-derived page",
                                        context)
        if (len(staged_image_span) != len(staged) or staged_image_span != staged or
                len(staged_post_pc) != len(post_pc_staged) or staged_post_pc != post_pc_staged or
                context["bytes"].get("live_cpu", {}).get("hex") != staged.hex() or
                context["bytes"].get("live_physical", {}).get("hex") != staged.hex() or
                context["bytes"].get("live_cpu_at_post_pc", {}).get("hex") != post_pc_staged.hex() or
                context["bytes"].get("live_physical_at_post_pc", {}).get("hex") != post_pc_staged.hex()):
            raise QualificationFailure("bootstrap reset source/staged/CPU/physical bytes differ", context)
        return {"module": "bootstrap-reset", "sequence": expected["sequence"],
            "source_line": expected["source_store_line"],
            "load_pc": expected["load_pc"], "store_pc": expected["store_pc"],
            "post_store_pc": expected["post_store_pc"], "value": expected["value"],
            "page_register": page_register, "mapped_page": expected_page,
            "span_hex": staged.hex(), "source_staged_live_match": True,
            "post_pc_span_hex": post_pc_staged.hex(),
            "live_cpu_span_hex": context["bytes"]["live_cpu"]["hex"],
            "live_physical_span_hex": context["bytes"]["live_physical"]["hex"],
            "live_cpu_at_post_pc_hex": context["bytes"]["live_cpu_at_post_pc"]["hex"],
            "live_physical_at_post_pc_hex": context["bytes"]["live_physical_at_post_pc"]["hex"],
            "par_raw": context["mapping"]["raw"],
            "live_cpu_sha256": context["bytes"]["live_cpu"]["sha256"],
            "live_physical_sha256": context["bytes"]["live_physical"]["sha256"],
            "live_cpu_at_post_pc_sha256": context["bytes"]["live_cpu_at_post_pc"]["sha256"],
            "live_physical_at_post_pc_sha256": context["bytes"]["live_physical_at_post_pc"]["sha256"],
            "get_run_state": {key: context["stopped_status"].get(key)
                for key in ("state", "last_stop_reason", "last_stop_pc", "last_stop_bp_id")},
            "get_run_state_qualified": True}

    def _qualify(self, stop: MonitorStop) -> dict[str, Any]:
        pc = stop.pc
        reset_stores = self.bootstrap_reset["reset_stores"]
        if stop.bp_id in (None, 0):
            matching = [item for item in reset_stores if item["post_store_pc"] == pc]
            if matching:
                expected = reset_stores[self.bootstrap_reset_index] if self.bootstrap_reset_index < len(reset_stores) else None
                if expected is None or expected["post_store_pc"] != pc:
                    raise QualificationFailure("bootstrap reset watchpoint is duplicate or out of source order",
                        {"kind": "bootstrap-reset-order-failure", "stop": self.current_stop_context,
                         "next_expected_sequence": self.bootstrap_reset_index,
                         "observed_post_store_pc": pc})
                if stop.phase != "initial-entry":
                    raise QualificationFailure("bootstrap reset watchpoint occurred outside initial-entry phase",
                        {"kind": "bootstrap-reset-phase-failure", "stop": self.current_stop_context,
                         "expected_phase": "initial-entry"})
                qualification = self._qualify_bootstrap_reset(stop, expected)
                self.bootstrap_reset_index += 1
                return qualification
            if pc != self.bus_marker["stop_pc"]:
                try:
                    state = monitor_call(self.client, "get_run_state", maximum=2.0)
                except Exception as exc:
                    state = {"read_error": f"{type(exc).__name__}: {exc}"}
                raise QualificationFailure("unknown watched stop is not an authored bootstrap reset or runtime PSG store",
                    {"kind": "unknown-watchpoint-stop", "stop": self.current_stop_context,
                     "get_run_state": state, "next_expected_bootstrap_sequence": self.bootstrap_reset_index})
            if self.bootstrap_reset_index != len(reset_stores):
                raise QualificationFailure("runtime PSG stop arrived before bootstrap reset qualification completed",
                    {"kind": "bootstrap-reset-incomplete-before-runtime", "stop": self.current_stop_context,
                     "observed_reset_count": self.bootstrap_reset_index,
                     "required_reset_count": len(reset_stores)})
        elif self.bootstrap_reset_index != len(reset_stores):
            raise QualificationFailure("runtime execution breakpoint arrived before bootstrap reset qualification completed",
                {"kind": "bootstrap-reset-incomplete-before-runtime", "stop": self.current_stop_context,
                 "observed_reset_count": self.bootstrap_reset_index,
                 "required_reset_count": len(reset_stores)})
        if pc == self.bus_marker["stop_pc"]:
            par5 = monitor_bytes(self.client, PAR5, 1)[0]
            code = self._audio_code(self.bus_marker["instruction_pc"], 3)
            proof = classify_post_store(pc, stop.registers.get("a"), par5,
                bytes.fromhex(self.bus_marker["opcode_bytes"]), self.bus_marker["stop_pc"])
            return {"module": "audio", **code, **proof}
        if pc == self.irq_marker["end_pc"]:
            size = len(bytes.fromhex(self.irq_marker["opcode_bytes"]))
            code = self._enemy_code(self.irq_marker["pc"], size)
            marker = qualify_irq_commit_stop(self.irq_marker, pc, stop.registers.get("dp"),
                bytes.fromhex(self.irq_marker["opcode_bytes"]))
            return {"module": "enemy", **code, **marker}
        if pc == self.post_busy_pc:
            start = self.audio["audio_mix_write_done"]
            code = self._audio_code(start, 6)
            expected = (b"\xBD" + self.audio["audio_music_busy"].to_bytes(2, "big") + b"\xB7\x02\xD4")
            if self.audio_image[start - 0xA000:start - 0xA000 + 6] != expected:
                raise GuardFailure("post-PSG busy marker is not the emitted JSR+STA sequence")
            if pc != start + len(expected):
                raise GuardFailure("post-PSG stop PC is not derived from emitted bytes")
            return {"module": "audio", **code, "pc": pc, "derived_from_emitted_bytes": True}
        if 0xA000 <= pc < 0xC000:
            return {"module": "audio", **self._audio_code(pc)}
        origin = self.presentation["presentation_flow_tick"]
        if origin <= pc < origin + len(self.presentation_image):
            return {"module": "presentation", **self._presentation_code(pc)}
        if 0x0800 <= pc < 0x0800 + len(self.enemy_image):
            return {"module": "enemy", **self._enemy_code(pc)}
        return {"module": "resident", **self._resident_code(pc)}

    def _state(self) -> dict[str, Any]:
        low = monitor_bytes(self.client, 0, 0x0300)
        def byte(name: str) -> int:
            return low[self.main[name]]
        def word(name: str) -> int:
            addr = self.main[name]
            return int.from_bytes(low[addr:addr + 2], "big")
        metas = physical_page_read(self.client, 0x34, 0x0900, 0x0200)
        meta_a, meta_b = metas[:0x100], metas[0x100:]
        enemy_raw = physical_page_read(self.client, 0x34, self.main["ENEMY_TABLE"] - 0xA000, 32)
        return {"low": low, "meta_a": meta_a, "meta_b": meta_b, "enemy_raw": enemy_raw,
            **decode_contact_search_state(low, self.main),
            "entry": byte("INITIAL_ENTRY_STATE"), "death": byte("DEATH_STATE"),
            "timer": byte("DEATH_TIMER"), "lives": byte("LIVES"),
            "pending": byte("FB_RENDER_PENDING"), "front": byte("FB_FRONT_ID"),
            "back": byte("FB_BACK_ID"), "commit_seq": word("FB_COMMIT_SEQ"),
            "frames": word("FRAMES"), "player_fb": word("PLAYER_FB"),
            "cell_x": byte("PLAYER_CELL_X"), "cell_y": byte("PLAYER_CELL_Y"),
            "step": byte("PLAYER_STEP"), "dir": byte("PLAYER_DIR"),
            "face": byte("PLAYER_FACE"), "tick_pending": byte("PLAYER_TICK_PENDING"),
            "anim": byte("PLAYER_ANIM"), "mode": byte("PRES_MODE"),
            "presentation_magic": low[0x00A4], "credits": low[PRES_CREDITS_ADDRESS],
            "presentation_event": low[0x00A9],
            "valid_a": meta_a[2], "valid_b": meta_b[2],
            "meta_fb_a": int.from_bytes(meta_a[4:6], "big"),
            "meta_fb_b": int.from_bytes(meta_b[4:6], "big"),
            "enemy_sha256": sha(enemy_raw)}

    def _audio_snapshot(self) -> dict[str, Any]:
        page = monitor_bytes(self.client, PAR5, 1)[0] & 0x3F
        if page != 0x3D:
            raise GuardFailure(f"live PAR5 page ${page:02X} does not map candidate audio page $3D")
        return live_audio_snapshot(self.client, self.audio, page)

    def _validate_terminal_snapshot(self, stop: MonitorStop,
                                    qualification: dict[str, Any],
                                    snapshot: dict[str, Any]) -> dict[str, Any]:
        try:
            return validate_quiet_terminal(snapshot)
        except GuardFailure as exc:
            def byte_field(name: str) -> dict[str, Any]:
                value = snapshot.get(name)
                if not isinstance(value, (bytes, bytearray)):
                    return {"available": False, "observed_type": type(value).__name__}
                data = bytes(value)
                return {"hex": data.hex(), "length": len(data)}

            counts = {name: snapshot.get(name) for name in (
                "music_count", "effect_queue_count", "credit_pending", "mix_count",
                "published_busy")}
            audio = {
                "slots": json_safe(snapshot.get("slots")),
                "counts": json_safe(counts),
                "music_queue": byte_field("music_queue"),
                "mixer": {
                    "periods": byte_field("mix_period_bytes"),
                    "attenuation": byte_field("mix_attenuation"),
                    "noise": byte_field("mix_noise"),
                    "shadow": byte_field("mix_shadow"),
                    "order": byte_field("mix_order"),
                    "best_slot": snapshot.get("best_slot"),
                    "best_priority": snapshot.get("best_priority"),
                },
            }
            context: dict[str, Any] = {
                "kind": "terminal-audio-guard-failure",
                "error": f"{type(exc).__name__}: {exc}",
                "stop": json_safe(self.current_stop_context or {
                    "phase": stop.phase, "pc": stop.pc, "pc_hex": f"${stop.pc:04X}",
                    "bp_id": stop.bp_id, "ordinal": stop.ordinal}),
                "qualification": json_safe(qualification),
                "audio_snapshot": audio,
                "stopped_status": {"state": "unavailable", "read_error": None},
            }
            try:
                status = monitor_call(self.client, "get_run_state", maximum=2.0)
                if not isinstance(status, dict):
                    raise GuardFailure("get_run_state returned a non-object terminal status")
                context["stopped_status"] = {
                    "state": status.get("state"),
                    "last_stop_reason": status.get("last_stop_reason"),
                    "last_stop_pc": status.get("last_stop_pc"),
                    "last_stop_bp_id": status.get("last_stop_bp_id"),
                    "reply": json_safe(status), "read_error": None,
                }
            except Exception as status_exc:
                context["stopped_status"] = {
                    "state": "unavailable",
                    "read_error": f"{type(status_exc).__name__}: {status_exc}",
                }
            self.failure_context = context
            exc.failure_context = context
            raise

    def _record(self, stop: MonitorStop, label: str, qualification: dict[str, Any], **fields: Any) -> None:
        self.events.append({"phase": stop.phase, "ordinal": stop.ordinal, "label": label,
            "pc": stop.pc, "qualified": qualification.get("source_staged_live_match") is True,
            "qualification": qualification, **fields})

    def _press(self, key: int, action: str, stop: MonitorStop, reason: str,
               matrix_key: int | None = None) -> None:
        monitor_call(self.client, "inject_key", {"key": key, "action": action})
        if action == "press":
            self.pressed.add(key)
        else:
            self.pressed.discard(key)
        self.input_events.append({"key": key, "key_namespace": "DSCAN", "matrix_key": matrix_key,
            "action": action, "ordinal": stop.ordinal,
            "reason": reason, "target_memory_write": False})

    def _begin_entry_input_challenge(self, stop: MonitorStop,
                                     state: dict[str, Any]) -> None:
        """Hold the live South binding through one natural automatic entry."""
        entry = self.current_entry
        if entry is None or getattr(self, "scenario", None) != "natural":
            return
        if (self.bindings is None or len(self.bindings) != 5 or
                self.search is None or entry.get("marker_x") not in (296, 280, 264)):
            raise GuardFailure("natural entry lacks its live five-key binding and seeded marker")
        if self.search.held is not None:
            self.search.release(stop.ordinal, "natural-entry-adversarial-input-begins")
        if self.pressed:
            raise GuardFailure("natural entry reached state 2 with an unrelated DSCAN key still held")
        matrix_key = self.bindings[ENTRY_SOUTH_BINDING_INDEX]
        key = matrix_binding_to_dscan(matrix_key)
        other_bindings = tuple(value for index, value in enumerate(self.search.bindings)
                               if index != ENTRY_SOUTH_BINDING_INDEX)
        if key == COIN5_DSCAN_KEY or key in other_bindings:
            raise GuardFailure("natural South challenge collides with an active control binding")
        witness = {
            "status": "HOLDING",
            "entry_generation": entry["index"],
            "direction": "south",
            "matrix_binding_index": ENTRY_SOUTH_BINDING_INDEX,
            "matrix_key": matrix_key,
            "key_namespace": "DSCAN",
            "dscan_key": key,
            "press_ordinal": stop.ordinal,
            "press_frame": state["frames"],
            "press_monotonic": stop.observed_monotonic,
            "release_ordinal": None,
            "release_frame": None,
            "release_monotonic": None,
            "held_states_observed": [],
            "state_sample_counts": {"2": 0, "3": 0, "4": 0},
            "logical_pose_changes": [],
            "front_pose_positions": [],
            "front_pose_ordinals": [],
            "walkout_last_x": entry["marker_x"],
            "maze_start_fb": None,
            "maze_last_fb": None,
            "maze_last_step": None,
            "maze_last_cell_y": None,
            "walkout_steps": 0,
            "maze_steps": 0,
            "valid": True,
            "pass": False,
            "release_requires": ["cue6 terminal post-PSG busy zero", "actual final IRQ FRONT proof",
                                 "state 4 final wait before entry state clear"],
            "movement_contract": {
                "state2": "automatic East; row-derived x advances exactly two pixels to 320",
                "state3": "offscreen at row-derived x=320 until owner histories retire",
                "state4": "automatic North from cell_y=22 to 18; each accepted 2-pixel pose advances PLAYER_FB by -320",
                "held_direction": "South DSCAN binding must not alter automatic direction, facing, or any logical 2-pixel pose"
            }
        }
        entry["held_input_challenge"] = witness
        self._press(key, "press", stop, "natural-entry-held-south-isolation", matrix_key=matrix_key)
        self.input_events[-1]["direction"] = "south"
        self.input_events[-1]["entry_generation"] = entry["index"]

    def _observe_entry_input_challenge(self, stop: MonitorStop,
                                       state: dict[str, Any], source: str) -> None:
        entry = self.current_entry
        witness = entry.get("held_input_challenge") if entry is not None else None
        if (getattr(self, "scenario", None) != "natural" or not isinstance(witness, dict) or
                witness.get("release_ordinal") is not None):
            return
        key = witness["dscan_key"]
        if self.pressed != {key} or (self.search is not None and self.search.held is not None):
            witness["valid"] = False
            self.errors.append("natural-entry-held-direction-was-missing-or-mixed-with-another-input")
        if state["death"] != 0 or state["lives"] != entry.get("seed_lives"):
            witness["valid"] = False
            self.errors.append("natural-entry-held-direction-crossed-death-or-life-count-change")
        entry_state = state["entry"]
        if entry_state not in (2, 3, 4):
            witness["valid"] = False
            self.errors.append("natural-entry-held-direction-was-not-released-before-entry-state-clear")
            return
        state_key = str(entry_state)
        witness["state_sample_counts"][state_key] += 1
        if entry_state not in witness["held_states_observed"]:
            witness["held_states_observed"].append(entry_state)
        signature: tuple[int, ...]
        pose: dict[str, Any]
        if entry_state in (2, 3):
            x = entry_row_x(state["player_fb"], entry["entry_start_fb"], entry["marker_x"])
            if x < entry["marker_x"] or x > 320 or x % 2:
                witness["valid"] = False
                self.errors.append("held-input walkout escaped its even-pixel marker row")
            if state["face"] != ENTRY_EAST_DIRECTION or state["dir"] != ENTRY_EAST_DIRECTION:
                witness["valid"] = False
                self.errors.append("South input changed automatic East walkout direction or facing")
            if entry_state == 2:
                previous_x = witness["walkout_last_x"]
                if x < previous_x or (x != previous_x and x - previous_x != 2):
                    witness["valid"] = False
                    self.errors.append("held-input walkout skipped or reversed a programmed 2-pixel pose")
                if x != previous_x:
                    witness["walkout_steps"] += 1
                    witness["walkout_last_x"] = x
                if x == 320:
                    witness["walkout_reached_x320"] = True
            else:
                previous_x = witness["walkout_last_x"]
                if x != 320:
                    witness["valid"] = False
                    self.errors.append("held-input offscreen phase is not row-derived x=320")
                if previous_x == 318 and x == 320:
                    # iet_walkout increments PLAYER_FB and changes state to 3 in
                    # the same callback, so the first observable state 3 owns
                    # the final 318-to-320 programmed pose.
                    witness["walkout_steps"] += 1
                    witness["walkout_last_x"] = 320
                    witness["walkout_reached_x320"] = True
                elif previous_x != 320:
                    witness["valid"] = False
                    self.errors.append("held-input offscreen transition skipped the final 2-pixel pose")
            signature = (entry_state, x, state["face"], state["dir"])
            pose = {"entry_state": entry_state, "x": x, "player_fb": state["player_fb"],
                    "face": state["face"], "dir": state["dir"]}
        else:
            face = state["face"]
            direction = state["dir"]
            if face != ENTRY_NORTH_DIRECTION or direction != ENTRY_NORTH_DIRECTION:
                witness["valid"] = False
                self.errors.append("South input changed automatic North maze-entry direction or facing")
            if witness["maze_start_fb"] is None:
                if state["cell_y"] != 22 or state["step"] != 0:
                    witness["valid"] = False
                    self.errors.append("held-input maze entry did not begin at authored cell_y=22, step=0")
                witness["maze_start_fb"] = state["player_fb"]
                witness["maze_last_fb"] = state["player_fb"]
                witness["maze_last_step"] = state["step"]
                witness["maze_last_cell_y"] = state["cell_y"]
            else:
                delta = state["player_fb"] - witness["maze_last_fb"]
                if delta not in (0, -320):
                    witness["valid"] = False
                    self.errors.append("held-input maze entry skipped or reversed a programmed 2-pixel pose")
                if delta == 0:
                    if (state["step"] != witness["maze_last_step"] or
                            state["cell_y"] != witness["maze_last_cell_y"]):
                        witness["valid"] = False
                        self.errors.append("held-input maze logical cell changed without a 2-pixel pose")
                else:
                    prior_step = witness["maze_last_step"]
                    expected_step = (prior_step + 1) & 3
                    expected_cell_y = witness["maze_last_cell_y"] - (1 if prior_step == 3 else 0)
                    if state["step"] != expected_step or state["cell_y"] != expected_cell_y:
                        witness["valid"] = False
                        self.errors.append("held-input maze pose step/cell cadence differs from authored four-step cells")
                    witness["maze_steps"] += 1
                    witness["maze_last_fb"] = state["player_fb"]
                    witness["maze_last_step"] = state["step"]
                    witness["maze_last_cell_y"] = state["cell_y"]
            signature = (entry_state, state["player_fb"], state["cell_y"], state["step"], face, direction)
            pose = {"entry_state": entry_state, "player_fb": state["player_fb"],
                    "cell_y": state["cell_y"], "step": state["step"],
                    "face": face, "dir": direction}
        witness.setdefault("observation_count", 0)
        witness["observation_count"] += 1
        witness["last_observation"] = {"ordinal": stop.ordinal, "frame": state["frames"],
            "source": source, "entry_state": entry_state, "player_fb": state["player_fb"],
            "face": state["face"], "dir": state["dir"], "held_dscan": key}
        previous = witness.get("last_logical_pose")
        if signature != previous:
            witness["logical_pose_changes"].append({"ordinal": stop.ordinal, "frame": state["frames"],
                "source": source, **pose})
            witness["last_logical_pose"] = signature

    def _record_challenge_front_pose(self, stop: MonitorStop,
                                     state: dict[str, Any], pose: dict[str, Any] | None) -> None:
        entry = self.current_entry
        witness = entry.get("held_input_challenge") if entry is not None else None
        if (getattr(self, "scenario", None) != "natural" or not isinstance(witness, dict) or
                witness.get("release_ordinal") is not None or pose is None or
                state["entry"] not in (2, 4)):
            return
        if state["entry"] == 2:
            x = entry_row_x(state["player_fb"], entry["entry_start_fb"], entry["marker_x"])
            if x >= 320:
                return
            position = (state["entry"], x, state["face"], state["anim"])
        else:
            position = (state["entry"], state["player_fb"], state["face"], state["anim"])
        witness["front_pose_positions"].append(list(position))
        witness["front_pose_ordinals"].append(stop.ordinal)
        if (pose.get("entry") != state["entry"] or pose.get("player_fb") != state["player_fb"] or
                pose.get("face") != state["face"] or pose.get("animation") != state["anim"] or
                pose.get("candidate_art_identity_qualified") is not True):
            witness["valid"] = False
            self.errors.append("actual FRONT challenge pose differs from the live logical or candidate-art pose")
        if (self.pressed != {witness["dscan_key"]} or
                (self.search is not None and self.search.held is not None)):
            witness["valid"] = False
            self.errors.append("actual FRONT pose was published without the designated held South DSCAN")

    def _release_entry_input_challenge(self, stop: MonitorStop, state: dict[str, Any],
                                       *, audio_idle: bool, front_proof: bool) -> bool:
        entry = self.current_entry
        witness = entry.get("held_input_challenge") if entry is not None else None
        if getattr(self, "scenario", None) != "natural":
            return True
        if not isinstance(witness, dict) or witness.get("release_ordinal") is not None:
            self.errors.append("natural entry final wait lacks one active held-direction challenge")
            return False
        ledger = self.proofs.get(entry["index"])
        records = ledger.records if ledger is not None else []
        terminal_record = next((r for r in records
                                if r["name"] == "terminal_post_psg_busy_zero"), None)
        front_record = next((r for r in records
                             if r["name"] == "final_pose_in_front_after_irq_commit"), None)
        terminal_ordinal = terminal_record.get("event_ordinal") if terminal_record else None
        front_ordinal = front_record.get("irq_commit_event_ordinal") if front_record else None
        proofs_precede_release = (
            type(terminal_ordinal) is int and terminal_ordinal < stop.ordinal and
            type(front_ordinal) is int and front_ordinal < stop.ordinal)
        if not (audio_idle and front_proof and proofs_precede_release and
                state["entry"] == 4 and state["cell_y"] == 18):
            return False
        expected_walkout = (320 - entry["marker_x"]) // 2
        expected_front_x = list(range(entry["marker_x"], 320, 2))
        expected_front_maze = [witness["maze_start_fb"] - step * 320
                                for step in range(17)] if witness["maze_start_fb"] is not None else []
        actual_front_x = sorted({p[1] for p in witness["front_pose_positions"] if p[0] == 2})
        actual_front_maze = sorted({p[1] for p in witness["front_pose_positions"] if p[0] == 4}, reverse=True)
        observed_walkout_x = [p["x"] for p in witness["logical_pose_changes"]
                              if p["entry_state"] in (2, 3)]
        expected_walkout_x = list(range(entry["marker_x"], 321, 2))
        observed_maze_poses = [(p["player_fb"], p["cell_y"], p["step"])
                               for p in witness["logical_pose_changes"] if p["entry_state"] == 4]
        expected_maze_poses = [
            (witness["maze_start_fb"] - n * 320, 22 - n // 4, n % 4)
            for n in range(17)] if witness["maze_start_fb"] is not None else []
        passed = (witness["valid"] is True and witness["dscan_key"] in self.pressed and
            set(witness["held_states_observed"]) == {2, 3, 4} and
            witness.get("walkout_reached_x320") is True and
            witness["walkout_steps"] == expected_walkout and
            observed_walkout_x == expected_walkout_x and
            witness["maze_start_fb"] is not None and witness["maze_steps"] == 16 and
            witness["maze_last_cell_y"] == 18 and witness["maze_last_step"] == 0 and
            observed_maze_poses == expected_maze_poses and
            actual_front_x == expected_front_x and actual_front_maze == expected_front_maze)
        self._press(witness["dscan_key"], "release", stop,
                    "natural-entry-audio-and-final-front-release", matrix_key=witness["matrix_key"])
        self.input_events[-1]["direction"] = "south"
        self.input_events[-1]["entry_generation"] = entry["index"]
        witness["release_ordinal"] = stop.ordinal
        witness["release_frame"] = state["frames"]
        witness["release_monotonic"] = stop.observed_monotonic
        witness["release_join"] = {"terminal_audio_idle": audio_idle,
            "terminal_busy_zero_event_ordinal": terminal_ordinal,
            "actual_final_front_proof": front_proof,
            "actual_final_front_commit_event_ordinal": front_ordinal,
            "release_stop_pc": stop.pc, "entry_state": state["entry"],
            "cell_y": state["cell_y"], "before_entry_state_clear": True}
        witness["expected_walkout_steps"] = expected_walkout
        witness["expected_front_walkout_x"] = expected_front_x
        witness["expected_maze_steps"] = 16
        witness["expected_front_maze_player_fb"] = expected_front_maze
        witness["observed_front_walkout_x"] = actual_front_x
        witness["observed_front_maze_player_fb"] = actual_front_maze
        witness["observed_walkout_logical_x"] = observed_walkout_x
        witness["expected_walkout_logical_x"] = expected_walkout_x
        witness["observed_maze_logical_poses"] = [list(pose) for pose in observed_maze_poses]
        witness["expected_maze_logical_poses"] = [list(pose) for pose in expected_maze_poses]
        witness["pass"] = passed
        witness["status"] = "HELD_DIRECTION_ISOLATED" if passed else "HELD_DIRECTION_ISOLATION_FAILED"
        entry["held_input_challenge_pass"] = passed
        if not passed:
            self.errors.append("natural held South challenge missed entry state, 2-pixel cadence, facing, or FRONT pose coverage")
        return passed

    def _start_inputs(self, stop: MonitorStop, state: dict[str, Any]) -> None:
        if self.cold_credited_start:
            return
        if self.start_state == "coin-not-sent":
            if state["mode"] != MODE_ATTRACT:
                return
            if (state["presentation_magic"] != 0xA5 or state["credits"] != 0 or
                    state["presentation_event"] != 0):
                self.errors.append("cold-attract-credit-state-is-not-clean-and-source-qualified")
                self.start_state = "start-failed"
                return
            self.credit_baseline = state["credits"]
            self.bindings = monitor_bytes(self.client, 0x0287, 5)
            self.search = InputOnlySearch(self.client, self.bindings)
            self._press(COIN5_DSCAN_KEY, "press", stop, "cold-credit-5",
                        matrix_key=COIN5_MATRIX_KEY)
            self.start_state = "coin-held"
            return
        elif self.start_state == "coin-held":
            if self.credit_evidence is None:
                return
            self._press(COIN5_DSCAN_KEY, "release", stop, "cold-credit-confirmed-release",
                        matrix_key=COIN5_MATRIX_KEY)
            self.start_state = "coin-released"
            return
        elif self.start_state == "coin-released":
            if self.credit_evidence is None:
                return
            assert self.bindings is not None
            enter_matrix = self.bindings[4]
            self._press(matrix_binding_to_dscan(enter_matrix), "press", stop,
                        "cold-game-start-enter", matrix_key=enter_matrix)
            self.start_state = "enter-held"
            return
        elif (self.start_state == "enter-held" and state["mode"] == 0 and
              self.credit_baseline is not None and state["credits"] == self.credit_baseline):
            assert self.bindings is not None
            enter_matrix = self.bindings[4]
            self._press(matrix_binding_to_dscan(enter_matrix), "release", stop,
                        "gameplay-input-isolation", matrix_key=enter_matrix)
            self.start_state = "started"
            self.cold_credited_start = True
            self.credit_evidence["consumed_credit_count"] = state["credits"]
            self.credit_evidence["start_observed_ordinal"] = stop.ordinal

    def _presentation_credit_add(self, stop: MonitorStop,
                                 qualification: dict[str, Any]) -> None:
        state = self._state()
        if (self.credit_baseline is None or self.start_state not in ("coin-held", "coin-released") or
                state["mode"] != MODE_ATTRACT or state["credits"] != self.credit_baseline or
                COIN5_DSCAN_KEY not in self.pressed or self.credit_call is not None or self.credit_evidence is not None):
            raise GuardFailure("live add_credit call lacks the single cold-attract coin-5 input context")
        self.credit_call = {"before": state["credits"], "call_ordinal": stop.ordinal,
            "call_pc": stop.pc, "fixed_coin_matrix_key": COIN5_MATRIX_KEY,
            "fixed_coin_dscan_key": COIN5_DSCAN_KEY,
            "presentation_code_qualified": qualification.get("source_staged_live_match") is True}
        self._record(stop, "source-qualified-add-credit-call", qualification,
            credits_before=state["credits"], fixed_coin_matrix_key=COIN5_MATRIX_KEY,
            fixed_coin_dscan_key=COIN5_DSCAN_KEY)

    def _confirm_start_credit(self, stop: MonitorStop,
                              qualification: dict[str, Any], state: dict[str, Any]) -> None:
        if self.credit_call is None:
            return
        before = self.credit_call["before"]
        if state["credits"] != before + 1:
            if state["credits"] != before:
                self.errors.append("presentation-credit-count-did-not-increment-exactly-once")
                self.credit_call = None
            return
        self.credit_evidence = {**self.credit_call, "after_add": state["credits"],
            "add_observed_ordinal": stop.ordinal, "cold_mode": MODE_ATTRACT,
            "one_credit_added": True}
        self.credit_call = None
        self._record(stop, "cold-credit-added-once", qualification,
            credits_before=before, credits_after=state["credits"],
            add_credit_call_ordinal=self.credit_evidence["call_ordinal"])

    def _audio_start(self, stop: MonitorStop, qualification: dict[str, Any]) -> None:
        if self.active_tx is not None:
            raise GuardFailure("mixer started a second PSG batch before its busy publication")
        snapshot = self._audio_snapshot()
        slot0 = snapshot["slots"][0]
        cue = slot0["id"]
        if cue in (6, 13):
            policy, priority = (0xB3, 5) if cue == 6 else (0xD3, 6)
            model = verify_live_music_mix(snapshot, cue, policy, priority)
            start, terminator = self.boundaries[f"cue{cue}"]["stream_start"], self.boundaries[f"cue{cue}"]["terminator_address"]
            if not start <= slot0["stream_pointer"] <= terminator + 1:
                raise GuardFailure(f"cue{cue} live slot pointer escaped its emitted stream")
            if not self.cue_stream_active[cue]:
                if cue in self.pending_terminal_cues:
                    raise GuardFailure("new cue generation began before its pending terminal handoff closed")
                self.cue_entry_owner[cue] = self.current_entry["index"] if self.current_entry else None
                self.cue_start_ordinal[cue] = stop.ordinal
                self.cue_output[cue] = False
                self.cue_terminal.pop(cue, None)
                self.quiet_tail.pop(cue, None)
                self.cue_stream_active[cue] = True
                if cue == 13:
                    cue_state = self._state()
                    if self.lifecycle is None or cue_state["entry"] != 0:
                        self.errors.append("cue13-admission-without-genuine-gameplay-contact-context")
                        if self.current_entry is not None:
                            self.entry_contact_violation = True
            if cue == 6:
                state = self._state()
                self.cue6_services += 1
                if self.frames_at_cue6 is None:
                    self.frames_at_cue6 = state["frames"]
                if self.current_entry is not None and state["entry"] == 2:
                    self._confirm_entry_state(stop, qualification, state)
            self._record(stop, "selected-cue-mix-start", qualification, cue_id=cue,
                         slot_pointer=slot0["stream_pointer"], wait=slot0["wait"],
                         audible_voice_count=model["audible_voice_count"])
            self.active_tx = {"cue": cue, "quiet": False, "snapshot": snapshot,
                "model": model, "transaction": PSGTransaction(model, snapshot),
                "first_store": None, "first_audible": None, "first_audible_frame": None,
                "audible_count": 0, "mute_store": None,
                "entry": self.cue_entry_owner.get(cue)}
            return
        if self.pending_terminal_cues:
            cue = max(self.pending_terminal_cues,
                      key=lambda k: self.cue_terminal.get(k, {}).get("ordinal", -1))
            terminal = self.cue_terminal.get(cue)
            start_ordinal = self.cue_start_ordinal.get(cue)
            entry = self.cue_entry_owner.get(cue)
            if (not isinstance(terminal, dict) or type(start_ordinal) is not int or
                    terminal.get("cue_id") != cue or
                    terminal.get("start_ordinal") != start_ordinal or
                    terminal.get("entry") != entry or
                    type(terminal.get("ordinal")) is not int or
                    terminal["ordinal"] <= start_ordinal or
                    terminal["ordinal"] >= stop.ordinal or self.cue_stream_active.get(cue)):
                raise GuardFailure("terminal quiet candidate does not match its emitted cue generation")
            identity = {"cue_id": cue, "start_ordinal": start_ordinal, "entry": entry,
                        "end_ordinal": terminal["ordinal"]}
            first_proof = self.quiet_tail.get(cue)
            if first_proof is None:
                quiet_kind = "first-terminal"
            else:
                first_identity = first_proof.get("stream_identity")
                first_busy_zero = first_proof.get("busy_zero_ordinal")
                if (first_identity != identity or
                        first_proof.get("actual_mute_attenuation_stores", 0) < 1 or
                        type(first_proof.get("mute_store_ordinal")) is not int or
                        type(first_busy_zero) is not int or first_busy_zero >= stop.ordinal):
                    raise GuardFailure("quiet refresh lacks an earlier same-generation mute and busy-zero proof")
                quiet_kind = "refresh"
            quiet = self._validate_terminal_snapshot(stop, qualification, snapshot)
            model = model_quiet_mix(snapshot["mix_shadow"])
            self._record(stop, "terminal-quiet-mix-start", qualification,
                         quiet_kind=quiet_kind, stream_identity=identity, **quiet)
            self.active_tx = {"cue": None, "quiet_cue": cue, "quiet": True, "snapshot": snapshot,
                "model": model, "transaction": PSGTransaction(model, snapshot),
                "first_store": None, "first_audible": None, "mute_store": None,
                "entry": entry, "quiet_kind": quiet_kind,
                "stream_identity": identity, "quiet_start_ordinal": stop.ordinal}
            return
        self._record(stop, "unrelated-mix-start", qualification, slot0_id=cue)

    def _psg_store(self, stop: MonitorStop, qualification: dict[str, Any]) -> None:
        if self.active_tx is None:
            self._record(stop, "unrelated-snd-data-store", qualification,
                         value=qualification.get("value"), transaction_context="no-cue6-or-cue13-batch")
            return
        value = qualification.get("value")
        if type(value) is not int:
            raise GuardFailure("SND_DATA watchpoint did not provide the actual A value")
        tx = self.active_tx
        tx["transaction"].store(value)
        store = tx["transaction"].observed[-1]
        if tx["first_store"] is None:
            tx["first_store"] = stop.ordinal
        if not tx["quiet"] and store.selected_slot == 0 and store.kind in ("period-data", "attenuation"):
            if tx["first_audible"] is None:
                tx["first_audible"] = stop.ordinal
                tx["first_audible_frame"] = monitor_word(self.client, self.main["FRAMES"])
            tx["audible_count"] += 1
        if store.kind == "attenuation" and (store.value & 15) == 15:
            tx["mute_store"] = stop.ordinal
        self._record(stop, "actual-snd-data-store", qualification,
            value=value, kind=store.kind, channel=store.channel,
            selected_slot=store.selected_slot, source_voice=store.source_voice,
            transaction_index=len(tx["transaction"].observed))

    def _record_cue13_idle(self, stop: MonitorStop, qualification: dict[str, Any],
                           busy: int, snapshot: dict[str, Any]) -> None:
        if (busy != 0 or self.lifecycle is None or not self.lifecycle_cue13_output or
                13 not in self.cue_terminal or 13 not in self.quiet_tail):
            return
        if any(item["name"] == "cue13_published_idle" for item in self.lifecycle.records):
            return
        quiet = self._validate_terminal_snapshot(stop, qualification, snapshot)
        self.lifecycle.record("cue13_published_idle", {
            "cue13_actual_output": True, "published_busy": 0, "normal_drain": True,
            "cue13_emitted_end_observed": True, "actual_terminal_mute_observed": True,
            "event_ordinal": stop.ordinal})
        self._record(stop, "cue13-published-idle", qualification, busy=busy, **quiet)

    def _busy_publication(self, stop: MonitorStop, qualification: dict[str, Any]) -> None:
        busy = monitor_bytes(self.client, self.audio["AUDIO_MUSIC_PUBLISHED_BUSY"], 1)[0]
        if self.active_tx is None:
            self._record(stop, "busy-publication-without-open-mix", qualification, busy=busy)
            return
        tx = self.active_tx
        result = tx["transaction"].finish()
        result["mix_match"] = True
        result["cue_id"] = tx["cue"]
        self.latest_mix[tx["cue"] or 0] = {**result, "event_ordinal": stop.ordinal}
        self._record(stop, "post-psg-busy-publication", qualification, busy=busy,
                     mix_result=result)
        if tx["quiet"]:
            cue = tx["quiet_cue"]
            mute_count = result["actual_mute_attenuation_stores"]
            quiet = self._validate_terminal_snapshot(stop, qualification, tx["snapshot"])
            if result["audible_store_count"] != 0:
                raise GuardFailure("terminal quiet service contains audible PSG stores")
            if busy != 0:
                raise GuardFailure("terminal quiet service did not publish busy zero")
            snapshot = self._audio_snapshot()
            post_quiet = self._validate_terminal_snapshot(stop, qualification, snapshot)
            identity = tx["stream_identity"]
            terminal = self.cue_terminal.get(cue)
            if (terminal is None or identity != {
                    "cue_id": cue, "start_ordinal": terminal.get("start_ordinal"),
                    "entry": terminal.get("entry"), "end_ordinal": terminal.get("ordinal")}):
                raise GuardFailure("terminal quiet service lost its emitted cue-generation identity")
            if tx["quiet_kind"] == "first-terminal":
                if mute_count < 1 or tx["mute_store"] is None:
                    raise GuardFailure("first terminal quiet service lacks an actual mute attenuation store")
                if cue in self.quiet_tail:
                    raise GuardFailure("first terminal quiet proof would overwrite an existing generation proof")
                first_proof = {**result, **quiet,
                    "stream_identity": identity,
                    "emitted_end_ordinal": terminal["ordinal"],
                    "quiet_start_ordinal": tx["quiet_start_ordinal"],
                    "mute_store_ordinal": tx["mute_store"],
                    "busy_zero_ordinal": stop.ordinal,
                    "post_busy_quiet": post_quiet,
                    "proof_kind": "first-terminal-mute-and-busy-zero",
                    "event_ordinal": tx["mute_store"]}
                self.quiet_tail[cue] = first_proof
                self.quiet_first_proofs.append(first_proof)
                if cue == 6 and tx["entry"] in self.proofs:
                    ledger = self.proofs[tx["entry"]]
                    if not any(r["name"] == "terminal_actual_psg_mute_transaction"
                               for r in ledger.records):
                        ledger.record("terminal_actual_psg_mute_transaction", {
                            "slot_clear_observed": True, "all_mix_stores_match": True,
                            "quiet_state_verified": True,
                            "actual_mute_attenuation_stores": mute_count,
                            "actual_store_count": result["actual_store_count"],
                            "event_ordinal": tx["mute_store"]})
            elif tx["quiet_kind"] == "refresh":
                first_proof = self.quiet_tail.get(cue)
                if (not isinstance(first_proof, dict) or
                        first_proof.get("stream_identity") != identity or
                        first_proof.get("actual_mute_attenuation_stores", 0) < 1 or
                        type(first_proof.get("mute_store_ordinal")) is not int or
                        type(first_proof.get("busy_zero_ordinal")) is not int or
                        first_proof["busy_zero_ordinal"] >= tx["quiet_start_ordinal"]):
                    raise GuardFailure("quiet refresh lacks its immutable earlier terminal proof")
                self.quiet_refresh_records.append({**result, **quiet,
                    "stream_identity": identity,
                    "first_terminal_mute_ordinal": first_proof["mute_store_ordinal"],
                    "first_terminal_busy_zero_ordinal": first_proof["busy_zero_ordinal"],
                    "quiet_start_ordinal": tx["quiet_start_ordinal"],
                    "busy_zero_ordinal": stop.ordinal,
                    "post_busy_quiet": post_quiet,
                    "proof_kind": "same-generation-shadow-refresh",
                    "event_ordinal": stop.ordinal})
            else:
                raise GuardFailure("terminal quiet service has an unknown proof phase")
            if cue == 6 and tx["entry"] in self.proofs:
                ledger = self.proofs[tx["entry"]]
                if not any(r["name"] == "terminal_post_psg_busy_zero" for r in ledger.records):
                    if not self._validate_terminal_snapshot(stop, qualification, snapshot):
                        raise GuardFailure("terminal busy zero lacks all-slot/all-queue idle state")
                    ledger.record("terminal_post_psg_busy_zero", {
                        "busy": 0, "all_slots_queues_credit_idle": True,
                        "busy_read_after_psg": True, "event_ordinal": stop.ordinal})
            self._record_cue13_idle(stop, qualification, busy, snapshot)
        else:
            cue = tx["cue"]
            if cue not in (6, 13):
                raise GuardFailure("mixer transaction has no cue identity")
            if tx["first_audible"] is not None:
                self.cue_output[cue] = True
                if cue == 13 and self.lifecycle is not None:
                    self.lifecycle_cue13_output = True
                if cue == 6 and tx["entry"] in self.proofs:
                    ledger = self.proofs[tx["entry"]]
                    if not any(r["name"] == "first_cue6_owned_psg_transaction" for r in ledger.records):
                        ledger.record("first_cue6_owned_psg_transaction", {
                            "selected_id": 6, "slot": 0, "policy": 0xB3,
                            "best_slot": 0, "best_priority": 5, "mix_match": True,
                            "audible_store_count": tx["audible_count"],
                            "event_ordinal": tx["first_audible"]})
                    owner_entry = next((entry for entry in self.entries
                                        if entry["index"] == tx["entry"]), None)
                    if owner_entry is not None and owner_entry.get("cue6_first_frame") is None:
                        owner_entry["cue6_first_frame"] = tx["first_audible_frame"]
                        owner_entry["cue6_first_output_ordinal"] = tx["first_audible"]
                        if (self.lifecycle is not None and owner_entry.get("seed_verified") and
                                not any(x["name"] == "replacement_cue6_output"
                                        for x in self.lifecycle.records)):
                            self.lifecycle.record("replacement_cue6_output", {
                                "entry_seed_precedes_cue6": tx["first_audible"] >
                                    owner_entry["state2_ordinal"],
                                "selected_id": 6, "audible_store_count": tx["audible_count"],
                                "event_ordinal": tx["first_audible"]})
                self._record(stop, "cue-owned-audible-output", qualification,
                             cue_id=cue, entry_generation=tx["entry"],
                             first_audible_store_ordinal=tx["first_audible"])
            if cue == 6 and busy == 1 and self.cue_output[6] and tx["entry"] in self.proofs:
                ledger = self.proofs[tx["entry"]]
                if not any(r["name"] == "first_post_psg_busy_one" for r in ledger.records):
                    ledger.record("first_post_psg_busy_one", {"busy": 1, "derived_marker": True,
                        "busy_read_after_psg": True, "event_ordinal": stop.ordinal})
            if cue == 13 and busy == 0:
                self._record_cue13_idle(stop, qualification, busy, self._audio_snapshot())
        self.active_tx = None

    def _audio_end(self, stop: MonitorStop, qualification: dict[str, Any]) -> None:
        regs = stop.registers
        snapshot = self._audio_snapshot()
        slot = next((i for i in range(4) if regs.get("y") == self.audio[f"audio_slot{i}"]), None)
        if slot is None:
            raise GuardFailure("audio END stop Y is not one of the four emitted slots")
        cue = snapshot["slots"][slot]["id"]
        if cue not in (6, 13):
            self._record(stop, "unrelated-audio-end", qualification, slot=slot, cue_id=cue)
            return
        boundary = self.boundaries[f"cue{cue}"]
        if regs.get("x") != boundary["terminal_x_expected"]:
            raise GuardFailure(f"cue{cue} END X is not the decoded terminator+1")
        if self.audio_image[boundary["terminator_address"] - 0xA000] != 0:
            raise GuardFailure("emitted cue stream terminator is not zero")
        start_ordinal = self.cue_start_ordinal.get(cue)
        if (not self.cue_stream_active.get(cue) or type(start_ordinal) is not int or
                start_ordinal >= stop.ordinal):
            raise GuardFailure("owned audio END lacks a current active cue-generation start")
        entry = self.cue_entry_owner.get(cue)
        self.cue_terminal[cue] = {"cue_id": cue, "slot": slot,
            "x": regs["x"], "ordinal": stop.ordinal,
            "start_ordinal": start_ordinal, "entry": entry,
            "stream_decoder_matches": True}
        self.pending_terminal_cues.add(cue)
        self.cue_stream_active[cue] = False
        self._record(stop, "owned-emitted-stream-end", qualification,
                     cue_id=cue, slot=slot, x=regs["x"],
                     terminator=0, decoder_matches=True)
        if cue == 6 and self.cue_output[6]:
            entry_index = self.cue_entry_owner.get(6)
            ledger = self.proofs.get(entry_index) if entry_index is not None else None
            if ledger is not None and not any(r["name"] == "cue6_terminal_stream_end_owned"
                                              for r in ledger.records):
                ledger.record("cue6_terminal_stream_end_owned", {
                    "slot_id": 6, "x_matches_emitted_end": True, "terminator_byte": 0,
                    "stream_decoder_matches_emitted_bytes": True, "event_ordinal": stop.ordinal})

    def _irq_start(self, stop: MonitorStop, qualification: dict[str, Any]) -> None:
        state = self._state()
        self.irq_before = {"seq": state["commit_seq"], "back": state["back"],
                           "pending": state["pending"], "state": state}
        self.irq_inc = None
        self._record(stop, "irq-publication-start", qualification,
                     pending=state["pending"], back=state["back"], seq=state["commit_seq"])

    def _irq_instruction(self, stop: MonitorStop, qualification: dict[str, Any]) -> None:
        if self.irq_before is None:
            raise GuardFailure("IRQ INC stop lacks its actual publication-start event")
        self.irq_inc = {"pc": stop.pc, "ordinal": stop.ordinal}
        self._record(stop, "irq-commit-inc-qualified", qualification,
                     dp=stop.registers["dp"], end_pc=stop.pc)

    def _front_mapping(self, owner: int) -> dict[str, int | bool]:
        if owner not in (0, 1):
            raise GuardFailure("FRONT owner is outside the two framebuffer owners")
        gime_state = monitor_call(self.client, "read_gime_state")
        registers = gime_state.get("registers")
        if not isinstance(registers, dict):
            raise GuardFailure("monitor GIME state lacks the write-only register shadow")
        voff1, voff2 = registers.get("FF9D"), registers.get("FF9E")
        if (type(voff1) is not int or not 0 <= voff1 <= 0xFF or
                type(voff2) is not int or not 0 <= voff2 <= 0xFF):
            raise GuardFailure("monitor GIME state lacks byte-valued VOFF1/VOFF2 shadows")
        expected_voff1 = 0xC0 if owner == 0 else 0xB0
        expected_base = 0x60000 if owner == 0 else 0x58000
        physical_base = (voff1 << 11) | (voff2 << 3)
        if voff1 != expected_voff1 or voff2 != 0 or physical_base != expected_base:
            raise GuardFailure(
                f"FRONT owner GIME shadow ${voff1:02X}/${voff2:02X} selects "
                f"${physical_base:05X}, expected ${expected_base:05X}")
        return {"front_owner_voff1_shadow": voff1,
                "front_owner_voff2_shadow": voff2,
                "front_physical_base": physical_base,
                "front_mapping_qualified": True}

    def _front_rect(self, owner: int, pointer: int,
                    mapping: dict[str, int | bool] | None = None) -> bytes:
        if owner not in (0, 1) or not VISIBLE_BASE <= pointer < VISIBLE_BASE + VISIBLE_BYTES:
            raise GuardFailure("front owner or player pointer is outside the A/B framebuffer")
        linear = pointer - VISIBLE_BASE
        visible_width = visible_row_width_bytes(pointer)
        if linear // 160 + 16 > 192:
            raise GuardFailure("front player rectangle crosses the framebuffer boundary")
        mapping = self._front_mapping(owner) if mapping is None else mapping
        expected_voff1 = 0xC0 if owner == 0 else 0xB0
        expected_base = 0x60000 if owner == 0 else 0x58000
        if (mapping.get("front_mapping_qualified") is not True or
                mapping.get("front_owner_voff1_shadow") != expected_voff1 or
                mapping.get("front_owner_voff2_shadow") != 0 or
                mapping.get("front_physical_base") != expected_base):
            raise GuardFailure("FRONT rectangle read lacks qualified GIME shadow evidence")
        page0 = 0x30 if owner == 0 else 0x2C
        result = bytearray()
        for row in range(16):
            offset = linear + row * 160
            row_bytes = physical_page_read(self.client, page0 + (offset >> 13),
                                           offset & 0x1FFF, visible_width)
            result.extend(row_bytes)
            result.extend(bytes(8 - visible_width))
        return bytes(result)

    def _front_pose(self, stop: MonitorStop, qualification: dict[str, Any],
                    state: dict[str, Any]) -> dict[str, Any] | None:
        owner = state["front"]
        valid = state["valid_a"] if owner == 0 else state["valid_b"] if owner == 1 else 0
        published_fb = state["meta_fb_a"] if owner == 0 else state["meta_fb_b"] if owner == 1 else 0
        if not valid or published_fb != state["player_fb"]:
            return None
        mapping = self._front_mapping(owner)
        visible_width = visible_row_width_bytes(state["player_fb"])
        actual = self._front_rect(owner, state["player_fb"], mapping)
        frame_index = state["face"] * 4 + state["anim"]
        if not 0 <= frame_index < len(self.player_frame_table):
            raise GuardFailure("live player frame index escaped the compiled candidate pose table")
        packed = self.player_frame_table[frame_index]
        art = {"frame_index": frame_index, "face": state["face"],
               "animation": state["anim"], "candidate_art_identity_qualified": True,
               "candidate_art_sha256": self.player_art_identity["art_source_sha256"]}
        expected = bug011_image_api().native_frame(packed)
        pixels = compare_opaque_player_pixels(expected, actual, packed, visible_width)
        record = {"ordinal": stop.ordinal, "frame": state["frames"], "owner": owner,
            "player_fb": state["player_fb"], "entry": state["entry"],
            "death": state["death"], "cell_x": state["cell_x"], "cell_y": state["cell_y"],
            "step": state["step"], "commit_seq": state["commit_seq"],
            **art, **pixels, "front_rect_sha256": sha(actual),
            **mapping, "clipped_logical_pose": visible_width < 8,
            "front_pixel_presence_proven": pixels["opaque_pixels_compared"] > 0,
            "irq_commit_end_pc": self.irq_marker["end_pc"]}
        bg_base = 0xA300 if owner == 0 else 0xAB00
        background = physical_page_read(self.client, 0x34, bg_base - 0xA000, 128)
        self.owner_history[(owner, state["player_fb"])] = {
            "actual": actual, "background": background, "sprite": packed,
            "face": state["face"], "animation": state["anim"],
            "frame": state["frames"], "owner": owner, "pointer": state["player_fb"],
            "visible_width_bytes": visible_width}
        self.pose_hashes.append(record["front_rect_sha256"])
        self.last_pose = record
        self._record(stop, "actual-front-player-pose", qualification, **record)
        if self.current_entry is not None:
            self.current_entry["pose_count"] += 1
            if state["entry"] == 2:
                tracking = self.current_entry.get("offscreen_retirement")
                if (not isinstance(tracking, dict) or
                        tracking.get("entry_generation") != self.current_entry.get("index")):
                    tracking = {"entry_generation": self.current_entry["index"],
                        "last_visible_by_owner": {}, "retired_by_owner": {},
                        "state3_observations": [], "maze_entry_gate": None}
                    self.current_entry["offscreen_retirement"] = tracking
                try:
                    row_x = entry_row_x(state["player_fb"],
                        self.current_entry["entry_start_fb"], self.current_entry["marker_x"])
                    if row_x >= 320:
                        raise GuardFailure("state-2 FRONT pose is not before the offscreen boundary")
                    snapshot = {
                        "entry_generation": self.current_entry["index"], "owner": owner,
                        "pointer": state["player_fb"], "actual": actual,
                        "background": background, "visible_width_bytes": visible_width,
                        "event_ordinal": stop.ordinal, "frame": state["frames"],
                        "actual_sha256": sha(actual), "saved_under_sha256": sha(background)}
                    self.offscreen_owner_snapshots[(self.current_entry["index"], owner)] = snapshot
                    tracking["last_visible_by_owner"][str(owner)] = {
                        "entry_generation": self.current_entry["index"], "owner": owner,
                        "pointer": state["player_fb"], "visible_width_bytes": visible_width,
                        "event_ordinal": stop.ordinal, "frame": state["frames"],
                        "actual_sha256": snapshot["actual_sha256"],
                        "saved_under_sha256": snapshot["saved_under_sha256"]}
                except GuardFailure as exc:
                    tracking.setdefault("errors", []).append(str(exc))
                    self.errors.append("state2-owner-last-visible-snapshot-invalid")
            if state["entry"] == 4 and self.current_entry.get("first_maze_visible_frame") is None:
                self.current_entry["first_maze_visible_frame"] = state["frames"]
        return record

    def _offscreen_owner_retirement(self, stop: MonitorStop,
                                    qualification: dict[str, Any],
                                    state: dict[str, Any]) -> bool:
        entry = self.current_entry
        if entry is None:
            return False
        tracking = entry.get("offscreen_retirement")
        if (not isinstance(tracking, dict) or
                tracking.get("entry_generation") != entry.get("index")):
            tracking = {"entry_generation": entry.get("index"),
                "last_visible_by_owner": {}, "retired_by_owner": {},
                "state3_observations": [], "maze_entry_gate": None}
            entry["offscreen_retirement"] = tracking
        event: dict[str, Any] = {"entry_generation": entry.get("index"),
            "event_ordinal": stop.ordinal, "front_owner": state.get("front"),
            "entry_state": state.get("entry"), "death_state": state.get("death")}
        try:
            if state.get("entry") != 3 or state.get("death") != 0:
                raise GuardFailure("offscreen owner retirement requires live entry state 3")
            x = entry_row_x(state.get("player_fb"), entry.get("entry_start_fb"),
                            entry.get("marker_x"))
            event["row_derived_x"] = x
            if x != 320:
                raise GuardFailure("offscreen owner retirement is not at row-derived x=320")
            owner = state.get("front")
            if type(owner) is not int or owner not in (0, 1):
                raise GuardFailure("offscreen owner retirement lacks a qualified FRONT owner")
            valid_field = "valid_a" if owner == 0 else "valid_b"
            published_field = "meta_fb_a" if owner == 0 else "meta_fb_b"
            valid = state.get(valid_field)
            event["front_player_valid"] = valid
            event["published_player_fb"] = state.get(published_field)
            retired = tracking["retired_by_owner"]
            if type(valid) is not int:
                raise GuardFailure("offscreen FRONT player-valid metadata is malformed")
            if valid != 0 and owner in retired:
                raise GuardFailure("offscreen FRONT metadata became valid again after retirement")
            visible = self.offscreen_owner_snapshots.get((entry.get("index"), owner))
            if not isinstance(visible, dict):
                raise GuardFailure("offscreen FRONT owner has no last-visible state-2 saved-under snapshot")
            summary = tracking["last_visible_by_owner"].get(str(owner))
            if (not isinstance(summary, dict) or
                    summary.get("entry_generation") != entry.get("index") or
                    summary.get("owner") != owner or
                    summary.get("pointer") != visible.get("pointer") or
                    summary.get("event_ordinal") != visible.get("event_ordinal") or
                    summary.get("actual_sha256") != visible.get("actual_sha256") or
                    summary.get("saved_under_sha256") != visible.get("saved_under_sha256")):
                raise GuardFailure("offscreen private pixel snapshot differs from retained entry evidence")
            mapping = self._front_mapping(owner)
            actual = self._front_rect(owner, visible["pointer"], mapping)
            proof = validate_offscreen_owner_retirement(state, entry, visible, actual)
            proof["event_ordinal"] = stop.ordinal
            proof["front_mapping_qualified"] = True
            proof["front_owner_voff1_shadow"] = mapping["front_owner_voff1_shadow"]
            proof["front_owner_voff2_shadow"] = mapping["front_owner_voff2_shadow"]
            proof["front_physical_base"] = mapping["front_physical_base"]
            retired[owner] = proof
            event.update(proof)
            tracking["state3_observations"].append(event)
            self._record(stop, "offscreen-owner-saved-under-restored", qualification, **event)
            return True
        except GuardFailure as exc:
            event["status"] = "REJECTED"
            event["reason"] = str(exc)
            tracking.setdefault("errors", []).append({"event_ordinal": stop.ordinal,
                                                        "reason": str(exc)})
            tracking["state3_observations"].append(event)
            if not tracking.get("failure_reported"):
                self.errors.append("offscreen-owner-saved-under-restoration-proof-failed")
                tracking["failure_reported"] = True
            self._record(stop, "offscreen-owner-restoration-rejected", qualification, **event)
            return False

    def _guard_first_maze_entry(self, stop: MonitorStop,
                                qualification: dict[str, Any],
                                state: dict[str, Any]) -> None:
        entry = self.current_entry
        if entry is None or state.get("entry") != 4:
            return
        tracking = entry.get("offscreen_retirement")
        if (not isinstance(tracking, dict) or
                tracking.get("entry_generation") != entry.get("index")):
            tracking = {"entry_generation": entry.get("index"),
                "last_visible_by_owner": {}, "retired_by_owner": {},
                "state3_observations": [], "maze_entry_gate": None}
            entry["offscreen_retirement"] = tracking
        if tracking.get("maze_entry_gate") is not None:
            return
        gate = offscreen_maze_entry_gate(entry, stop.ordinal)
        tracking["maze_entry_gate"] = gate
        if not gate["pass"]:
            self.errors.append("maze-entry-published-before-both-owner-restoration-proofs")
        self._record(stop, "maze-entry-offscreen-restoration-gate", qualification,
            **gate, observation_source="first-state-4-observation")

    def _irq_done(self, stop: MonitorStop, qualification: dict[str, Any]) -> None:
        if self.irq_before is None or self.irq_inc is None:
            self._record(stop, "irq-done-without-qualified-commit", qualification)
            return
        state = self._state()
        expected = (self.irq_before["seq"] + 1) & 0xFFFF
        if (self.irq_before["pending"] != 1 or state["pending"] != 0 or
                state["commit_seq"] != expected or state["front"] != self.irq_before["back"]):
            raise GuardFailure("IRQ completion did not commit the pending FRONT owner and sequence")
        self._record(stop, "irq-front-commit-complete", qualification,
            seq_before=self.irq_before["seq"], seq_after=state["commit_seq"],
            front_id=state["front"], irq_commit_end_pc=self.irq_inc["pc"])
        if self.current_entry is not None and state["entry"] == 4:
            self._guard_first_maze_entry(stop, qualification, state)
        if self.current_entry is not None and state["entry"] == 3:
            self._offscreen_owner_retirement(stop, qualification, state)
        elif state["death"] == 0 and self.current_entry is not None:
            pose = self._front_pose(stop, qualification, state)
            self._record_challenge_front_pose(stop, state, pose)
            if missing_visible_front_pose_failure(state["entry"], pose):
                self.errors.append("live-player-front-pose-missing-at-irq-commit")
            elif state["entry"] == 4 and state["cell_y"] == 18:
                if pose["visible_width_bytes"] != 8 or pose["opaque_pixels_compared"] <= 0:
                    self.errors.append("final-maze-front-pose-is-clipped-or-has-no-visible-opaque-pixels")
                else:
                    ledger = self.proofs[self.current_entry["index"]]
                    if not any(r["name"] == "final_pose_in_front_after_irq_commit"
                               for r in ledger.records):
                        busy = monitor_bytes(self.client,
                            self.audio["AUDIO_MUSIC_PUBLISHED_BUSY"], 1)[0]
                        ledger.record("final_pose_in_front_after_irq_commit", {
                            "irq_commit_observed": True,
                            "front_pixels_match_opaque_player": True,
                            "live_code_span_qualified": True,
                            "irq_live_opcode_match": True,
                            "front_mapping_qualified": True,
                            "same_stop_busy_sample": True,
                            "opaque_pixels_compared": pose["opaque_pixels_compared"],
                            "visible_width_bytes": pose["visible_width_bytes"],
                            "front_id": pose["owner"],
                            "front_owner_voff1_shadow": pose["front_owner_voff1_shadow"],
                            "front_owner_voff2_shadow": pose["front_owner_voff2_shadow"],
                            "front_physical_base": pose["front_physical_base"],
                            "entry_marker_x": self.current_entry["marker_x"],
                            "entry_seed_lives": self.current_entry["seed_lives"],
                            "player_fb": state["player_fb"],
                            "published_music_busy": busy,
                            "irq_commit_event_ordinal": stop.ordinal,
                            "irq_commit_end_pc": self.irq_marker["end_pc"],
                            "event_ordinal": stop.ordinal})
        if state["death"] == 3 and state["timer"] == 37 and self.lifecycle is not None:
            owner = state["front"]
            prior = self.owner_history.get((owner, state["player_fb"]))
            if prior is not None:
                blank = self._front_rect(owner, state["player_fb"])
                if visible_rect_matches_background(blank, prior["background"],
                                                    prior["visible_width_bytes"]):
                    native = bug011_image_api().native_frame(prior["sprite"])
                    opaque = sum(bool((byte >> shift) & 0x0F)
                                 for byte in native for shift in (4, 0))
                    self.lifecycle.record("death_blank_timer37", {
                        "death_state": 3, "death_timer": 37, "entry_state": 0,
                        "source_bytes_match": True, "death_blank_front_commit_observed": True,
                        "death_blank_pixels_match_oracle": True, "death_blank_irq_commit_observed": True,
                        "death_blank_live_code_span_qualified": True,
                        "death_blank_front_mapping_qualified": True,
                        "death_blank_opaque_pixels_compared": opaque,
                        "event_ordinal": stop.ordinal})
                    self._record(stop, "death-blank-front-oracle", qualification,
                        compared_opaque_pixels=opaque, front_rect_sha256=sha(blank),
                        saved_under_sha256=sha(prior["background"]))
        self.irq_before = None
        self.irq_inc = None

    def _entry_seed(self, stop: MonitorStop, qualification: dict[str, Any]) -> None:
        state = self._state()
        if self.current_entry is None or self.current_entry.get("released"):
            self.entry_count += 1
            self.current_entry = {"index": self.entry_count, "cue6_first_frame": None,
                "first_maze_visible_frame": None, "marker_x": None, "pose_count": 0,
                "seed_ordinal": stop.ordinal,
                "offscreen_retirement": {"entry_generation": self.entry_count,
                    "last_visible_by_owner": {}, "retired_by_owner": {},
                    "state3_observations": [], "maze_entry_gate": None}}
            self.proofs[self.entry_count] = ProofLedger()
            self.entries.append(self.current_entry)
        entry = self.current_entry
        entry["marker_call_ordinal"] = stop.ordinal
        entry["lives_before_marker_body"] = state["lives"]
        self.pending_entry_seed = {"ordinal": stop.ordinal, "lives": state["lives"]}
        self._record(stop, "entry-marker-call", qualification, entry_generation=entry["index"],
            lives=state["lives"], player_fb=state["player_fb"],
            entry_state_before_marker_body=state["entry"])

    def _confirm_entry_state(self, stop: MonitorStop, qualification: dict[str, Any],
                             state: dict[str, Any]) -> None:
        if self.current_entry is None or state["entry"] != 2 or self.current_entry.get("seed_verified"):
            return
        isolated = not self.pressed and not (self.search and self.search.held is not None)
        if not isolated:
            self.errors.append("held-input-present-at-observed-entry-state2")
        if self.search is not None:
            self.search.release(stop.ordinal, "entry-state2-input-isolation")
        for key in list(self.pressed):
            self._press(key, "release", stop, "entry-state2-input-isolation")
        entry = self.current_entry
        entry["seed_verified"] = True
        entry["state2_ordinal"] = stop.ordinal
        entry["seed_ordinal"] = stop.ordinal
        entry["seed_lives"] = state["lives"]
        entry["seed_frame"] = state["frames"]
        entry["seed_death_timer"] = state["timer"]
        entry["entry_start_fb"] = state["player_fb"]
        entry["marker_x"] = framebuffer_row_x(state["player_fb"])
        entry["offscreen_retirement"] = {"entry_generation": entry["index"],
            "last_visible_by_owner": {}, "retired_by_owner": {},
            "state3_observations": [], "maze_entry_gate": None}
        entry["marker_x_matches_life_slot"] = (
                entry["marker_x"] == (33 + 2 * state["lives"]) * 8)
        entry["input_isolated_at_seed"] = isolated
        if self.lifecycle is not None and self.contact_count:
            contact = self.contacts[-1]
            consumed_once = state["lives"] == contact["lives"] - 1
            if not consumed_once:
                self.errors.append("reserve-count-at-replacement-entry-is-not-one")
            entry["reserve_decrement_exactly_once"] = consumed_once
            self.lifecycle.record("replacement_entry_seed", {
                "prior_death_blank_observed": any(r["name"] == "death_blank_timer37"
                    for r in self.lifecycle.records),
                "prior_cue13_idle_observed": any(r["name"] == "cue13_published_idle"
                    for r in self.lifecycle.records), "entry_state": 2,
                "event_ordinal": stop.ordinal})
            # LifecycleOrder.record validates both death blank and cue13 idle
            # dependencies before the cue13 terminal candidate is retired.
            self.pending_terminal_cues.discard(13)
        self._record(stop, "entry-state2-observed", qualification,
            entry_generation=entry["index"], lives=state["lives"],
            player_fb=state["player_fb"], input_isolated=isolated)
        if getattr(self, "scenario", None) == "natural":
            self._begin_entry_input_challenge(stop, state)

    def _enemy_contact(self, stop: MonitorStop, qualification: dict[str, Any]) -> None:
        state = self._state()
        genuine = state["entry"] == 0 and state["death"] == 0
        if genuine:
            self.contact_count += 1
            self.contacts.append({"ordinal": stop.ordinal, "lives": state["lives"],
                "entry": state["entry"], "death": state["death"], "frame": state["frames"],
                "enemy_snapshot_sha256": state["enemy_sha256"], "source_staged_live_match": True})
            self.lifecycle = LifecycleOrder()
            self.lifecycle_records.append(self.lifecycle)
            self.lifecycle_cue13_output = False
            self.pending_terminal_cues.discard(13)
            self.cue_terminal.pop(13, None)
            self.quiet_tail.pop(13, None)
        else:
            self.entry_contact_violation = True
            self.errors.append("enemy-contact-was-observed-during-entry-or-death")
        if self.search is not None:
            self.search.release(stop.ordinal, "enemy-contact-input-isolation")
        self._record(stop, "genuine-enemy-contact" if genuine else "entry-contact-violation",
            qualification, genuine=genuine, lives=state["lives"], entry=state["entry"],
            death=state["death"], frame=state["frames"])

    def _mainloop(self, stop: MonitorStop, qualification: dict[str, Any]) -> None:
        state = self._state()
        self.last_runtime_state = state
        self.last_runtime_state_stop = dict(getattr(self, "current_stop_context", None) or {
            "phase": stop.phase, "phase_deadline_seconds": PHASE_SECONDS,
            "pc": stop.pc, "bp_id": stop.bp_id, "ordinal": stop.ordinal})
        if self.current_entry is not None and state["entry"] == 4:
            self._guard_first_maze_entry(stop, qualification, state)
        self._record(stop, "mainloop", qualification, entry=state["entry"], death=state["death"],
            timer=state["timer"], lives=state["lives"], player_fb=state["player_fb"],
            cell=[state["cell_x"], state["cell_y"]], step=state["step"],
            pending=state["pending"], front=state["front"], commit_seq=state["commit_seq"],
            frames=state["frames"], mode=state["mode"])
        self._start_inputs(stop, state)
        self._confirm_start_credit(stop, qualification, state)
        if self.current_entry is not None and state["entry"] == 2:
            self._confirm_entry_state(stop, qualification, state)
        if self.current_entry is not None and getattr(self, "scenario", None) == "natural":
            self._observe_entry_input_challenge(stop, state, "mainloop")
        if self.current_entry is not None and state["entry"] == 3:
            if self.current_entry.get("offscreen_remaining_death_timer") is None:
                self.current_entry["offscreen_remaining_death_timer"] = state["timer"]
            actual_x = entry_row_x(state["player_fb"],
                self.current_entry.get("entry_start_fb", -99999),
                self.current_entry.get("marker_x", -1))
            self.current_entry["offscreen_x_pixels"] = actual_x
            self.current_entry["offscreen_x320"] = actual_x == 320
        if self.current_entry is not None and state["entry"] != 0 and state["death"] != 0:
            self.errors.append("death-state-entered-during-life-entry")
            self.entry_contact_violation = True
        if self.lifecycle is not None:
            previous = self._previous_state
            if state["entry"] == 0 and state["death"] == 1 and (previous is None or previous["death"] != 1):
                self.lifecycle.record("death_state_1", {"death_state": 1,
                    "genuine_contact_live_bytes": True, "event_ordinal": stop.ordinal})
            if state["entry"] == 0 and state["death"] == 2 and (previous is None or previous["death"] != 2):
                self.lifecycle.record("death_state_2", {"death_state": 2,
                    "genuine_contact_live_bytes": True, "event_ordinal": stop.ordinal})
            if state["death"] == 3 and state["timer"] == 37 and (
                    previous is None or previous["death"] != 3):
                self._record(stop, "death-blank-boundary", qualification,
                    timer=37, lives=state["lives"], entry=state["entry"])
        if self.release_snapshot is not None:
            same_player = (state["player_fb"], state["cell_x"], state["cell_y"],
                state["step"], state["face"], state["anim"]) == self.release_snapshot["player"]
            same_enemy = state["enemy_raw"] == self.release_snapshot["enemy_raw"]
            if same_player and same_enemy and self.current_entry is not None:
                ledger = self.proofs[self.current_entry["index"]]
                if not any(r["name"] == "no_same_batch_player_or_enemy_mutation" for r in ledger.records):
                    ledger.record("no_same_batch_player_or_enemy_mutation", {
                        "player_unchanged": True, "enemy_unchanged": True,
                        "event_ordinal": stop.ordinal})
            else:
                self.errors.append("player-or-enemy-mutated-after-entry-release")
            self.release_snapshot = None
        if self.search is not None and self.cold_credited_start:
            contact_target = 2 if self.scenario == "natural" else 1
            if self.scenario in ("front-first", "music-first"):
                contact_target = 2
            if self.contact_count < contact_target:
                self.search.at_gameplay_center(stop.ordinal, state["entry"], state["death"],
                    state["step"], state["cell_x"], state["cell_y"])
            else:
                self.search.release(stop.ordinal, "approved-contact-target-reached")
        if state["death"] != 0 and self.search is not None:
            self.search.release(stop.ordinal, "death-input-isolation")
        if self.fixture is not None and self.fixture_result is None:
            self._maybe_write_fixture(stop, state, qualification)
        self._previous_state = state

    def _natural_contact_search_context(self, phase: dict[str, Any]) -> dict[str, Any]:
        """Project the last cached search state without issuing monitor reads."""
        state = getattr(self, "last_runtime_state", None)
        last_state: dict[str, Any] | None = None
        if isinstance(state, dict):
            fields = ("entry", "death", "timer", "lives", "frames", "player_fb",
                      "cell_x", "cell_y", "step", "dir", "want", "player_dir",
                      "player_want", "box_timer", "enemy_timer", "enemy_active",
                      "enemy_released", "freeze_timer", "enemy_sha256")
            last_state = {key: state[key] for key in fields if key in state}
            enemy_raw = state.get("enemy_raw")
            if isinstance(enemy_raw, (bytes, bytearray)):
                enemy_bytes = bytes(enemy_raw)
                last_state["enemy_raw"] = {"hex": enemy_bytes.hex(),
                    "length": len(enemy_bytes), "sha256": sha(enemy_bytes)}
        search = getattr(self, "search", None)
        actions = list(getattr(search, "actions", [])) if search is not None else []
        entries = list(getattr(self, "entries", []))[-3:]
        entry_fields = ("index", "seed_ordinal", "marker_call_ordinal", "state2_ordinal",
            "lives_before_marker_body", "seed_lives", "seed_frame", "seed_death_timer",
            "entry_start_fb", "marker_x", "marker_x_matches_life_slot", "seed_verified",
            "input_isolated_at_seed", "reserve_decrement_exactly_once", "released",
            "first_maze_visible_frame", "cue6_first_frame", "pose_count",
            "offscreen_remaining_death_timer", "offscreen_x_pixels", "offscreen_x320")

        def entry_summary(entry: Any) -> Any:
            if not isinstance(entry, dict):
                return json_safe(entry)
            summary = {key: entry[key] for key in entry_fields if key in entry}
            witness = entry.get("held_input_challenge")
            if isinstance(witness, dict):
                witness_fields = ("entry_generation", "matrix_key", "dscan_key", "press_ordinal",
                    "release_ordinal", "valid", "pass", "held_states_observed",
                    "state_sample_counts", "walkout_steps", "walkout_last_x",
                    "walkout_reached_x320", "maze_steps", "maze_last_cell_y",
                    "maze_last_step", "observation_count", "last_observation")
                summary["held_input_challenge"] = {
                    key: witness[key] for key in witness_fields if key in witness}
                for list_key in ("logical_pose_changes", "front_pose_positions", "front_pose_ordinals"):
                    if list_key in witness:
                        values = witness[list_key]
                        summary["held_input_challenge"][list_key + "_count"] = len(values)
                        summary["held_input_challenge"][list_key + "_tail"] = values[-8:]
            retirement = entry.get("offscreen_retirement")
            if isinstance(retirement, dict):
                summary["offscreen_retirement"] = {
                    "entry_generation": retirement.get("entry_generation"),
                    "last_visible_owners": sorted(str(x) for x in retirement.get("last_visible_by_owner", {})),
                    "retired_owners": sorted(str(x) for x in retirement.get("retired_by_owner", {})),
                    "state3_observation_count": len(retirement.get("state3_observations", [])),
                    "state3_observations_tail": retirement.get("state3_observations", [])[-4:],
                    "maze_entry_gate": retirement.get("maze_entry_gate"),
                }
            return json_safe(summary)

        proofs = getattr(self, "proofs", {})
        ledgers = {str(index): acceptance_status(ledger)
                   for index, ledger in proofs.items() if isinstance(ledger, ProofLedger)}
        lifecycle_records = getattr(self, "lifecycle_records", [])
        if not lifecycle_records and getattr(self, "lifecycle", None) is not None:
            lifecycle_records = [self.lifecycle]
        return {
            "kind": "natural-contact-search-timeout-context",
            "cached_only_no_monitor_reread": True,
            "no_progress_cause": "not_inferred_from_player_pose_alone",
            "phase": json_safe(phase),
            "last_stop": json_safe(getattr(self, "last_runtime_state_stop", None) or
                                    getattr(self, "current_stop_context", None)),
            "last_low_ram_state": json_safe(last_state),
            "input_only_search": {
                "direction_index": getattr(search, "direction", None),
                "held_dscan": getattr(search, "held", None),
                "held_matrix_key": getattr(search, "held_matrix", None),
                "origin_cell": json_safe(getattr(search, "origin", None)),
                "no_progress_stops": getattr(search, "age_stops", None),
                "action_count": len(actions), "action_tail_limit": 64,
                "actions_tail": json_safe(actions[-64:]),
            },
            "input_event_count": len(getattr(self, "input_events", [])),
            "input_events_tail_limit": 64,
            "input_events_tail": json_safe(list(getattr(self, "input_events", []))[-64:]),
            "contact_count": getattr(self, "contact_count", None),
            "contacts_tail": json_safe(list(getattr(self, "contacts", []))[-3:]),
            "entries": [entry_summary(entry) for entry in entries],
            "current_entry": entry_summary(getattr(self, "current_entry", None)),
            "proof_ledgers": json_safe(ledgers),
            "lifecycle_ledgers": json_safe([record.status() for record in lifecycle_records]),
            "target_memory_write_count": getattr(self, "write_count", None),
        }

    def _fixture_snapshot(self, stop: MonitorStop, qualification: dict[str, Any]) -> dict[str, Any]:
        require_current_paused_stop(self.client, stop.pc)
        current_qualification = self._qualify(stop)
        state = self._state()
        page = fixture_audio_page(self.client, stop.pc, self.main["mainloop"])
        audio = live_audio_snapshot(self.client, self.audio, page)
        cue = 6 if self.scenario in ("front-first", "music-first") else 13
        slot0 = audio["slots"][0]
        selected = None
        try:
            selected = verify_live_music_mix(audio, cue, 0xB3 if cue == 6 else 0xD3,
                                              5 if cue == 6 else 6)
        except GuardFailure:
            pass
        priority = 5 if cue == 6 else 6
        latest = self.latest_mix.get(cue)
        transaction_current = bool(latest and latest.get("mix_match") is True and
            latest.get("event_ordinal", 0) > self.cue_start_ordinal.get(cue, 1 << 60))
        if cue == 6 and self.current_entry is not None:
            transaction_current = (transaction_current and
                self.cue_entry_owner.get(cue) == self.current_entry["index"])
        higher = any(s["id"] != 0xFF and s["policy"] & 1 and s["priority"] > priority
                     for s in audio["slots"])
        snapshot: dict[str, Any] = {
            "timer_map_qualified": self.main["DEATH_TIMER"] == TIMER_ADDRESS,
            "timer_address": self.main["DEATH_TIMER"],
            "source_map_bytes_qualified": current_qualification.get("source_staged_live_match") is True,
            "render_pending": state["pending"], "owner_a_player_valid": state["valid_a"],
            "owner_b_player_valid": state["valid_b"], "cue_published_busy": audio["published_busy"],
            "cue_actual_output_proven": self.cue_output[cue],
            "actual_psg_writes_match_mix": transaction_current,
            "marker_x": self.current_entry.get("marker_x", -1) if self.current_entry else -1,
            "entry_state": state["entry"], "death_state": state["death"],
            "player_x": (entry_row_x(state["player_fb"],
                self.current_entry.get("entry_start_fb", -99999),
                self.current_entry.get("marker_x", -1))
                if self.current_entry and state["entry"] == 3 else -1),
            "cue_active_id": slot0["id"], "slot0_id": slot0["id"],
            "slot0_policy": slot0["policy"], "slot0_priority": slot0["priority"],
            "best_slot": audio["best_slot"], "best_priority": audio["best_priority"],
            "higher_priority_exclusive_source": higher,
            "genuine_enemy_contact_proven": bool(self.contacts) and not self.entry_contact_violation,
            "death_timer": state["timer"], "lives": state["lives"],
            "cue13_actual_output_proven": self.cue_output[13],
            "cue13_published_busy": audio["published_busy"],
            "live_stop_pc": stop.pc, "live_stop_ordinal": stop.ordinal,
            "fresh_same_stop_requalification": True}
        if selected is not None:
            key = "cue6" if cue == 6 else "cue13"
            snapshot[f"{key}_selected_voice_mask"] = 0x07 if cue == 6 else 0x03
            snapshot[f"{key}_selected_audible_voice_count"] = selected["audible_voice_count"]
        if cue == 6:
            start, terminator = self.boundaries["cue6"]["stream_start"], self.boundaries["cue6"]["terminator_address"]
            remaining = stream_waits_remaining(self.audio_image, start - 0xA000,
                terminator - 0xA000, slot0["stream_pointer"] - 0xA000, slot0["wait"])
            now = state["frames"]
            elapsed = ((now - self.frames_at_cue6) & 0xFFFF) if self.frames_at_cue6 is not None else 0
            needed_vblanks = 33
            estimated_ticks = ((needed_vblanks * self.cue6_services + elapsed - 1) // elapsed
                               if elapsed and self.cue6_services else 0)
            viable = state["timer"] > 0 and estimated_ticks > 0 and remaining["remaining_audio_ticks"] > estimated_ticks
            snapshot["remaining_pad"] = state["timer"]
            snapshot["cue_dwell_cadence_viable"] = viable
            self.dwell_checks.append({**remaining, "elapsed_vblanks": elapsed,
                "observed_selected_audio_services": self.cue6_services,
                "required_future_vblanks": needed_vblanks,
                "estimated_future_audio_ticks": estimated_ticks,
                "predicted_front_before_cue_idle": viable})
        return snapshot

    def _maybe_write_fixture(self, stop: MonitorStop, state: dict[str, Any],
                             qualification: dict[str, Any]) -> None:
        assert self.fixture is not None
        if state["mode"] != 0:
            return
        if self.scenario in ("front-first", "music-first"):
            if (state["entry"] != 3 or state["death"] != 0 or self.current_entry is None or
                    self.current_entry.get("marker_x") != 264 or state["lives"] != 0):
                return
            actual_x = entry_row_x(state["player_fb"],
                self.current_entry.get("entry_start_fb", -99999),
                self.current_entry.get("marker_x", -1))
            self.current_entry["offscreen_x_pixels"] = actual_x
            self.current_entry["offscreen_x320"] = actual_x == 320
            if actual_x != 320:
                self.errors.append("walkout-entry-state3-did-not-reach-row-derived-x320")
                return
        else:
            if (state["death"] != 3 or state["timer"] != 37 or state["entry"] != 0 or
                    self._previous_state is None or self._previous_state["death"] != 2):
                return
        try:
            result = self.fixture.write_from_paused_stop(self.client, stop.pc,
                lambda client: self._fixture_snapshot(stop, qualification))
        except GuardFailure as exc:
            self._record(stop, "fixture-guard-denied", qualification,
                         reason=str(exc), entry=state["entry"], death=state["death"], timer=state["timer"])
            return
        self.write_count += 1
        self.fixture_result = result
        self._record(stop, "approved-death-timer-write", qualification,
                     address=TIMER_ADDRESS, value=result["value"], write_count=self.write_count,
                     fresh_same_stop=True)

    def _final_entry_wait(self, stop: MonitorStop, qualification: dict[str, Any]) -> None:
        state = self._state()
        if self.current_entry is None or state["entry"] != 4 or state["cell_y"] != 18:
            self._record(stop, "unexpected-final-entry-wait-state", qualification,
                         entry=state["entry"], cell_y=state["cell_y"])
            return
        ledger = self.proofs[self.current_entry["index"]]
        busy = monitor_bytes(self.client, self.audio["AUDIO_MUSIC_PUBLISHED_BUSY"], 1)[0]
        front_proof = next((r for r in ledger.records
                            if r["name"] == "final_pose_in_front_after_irq_commit"), None)
        if front_proof is None:
            self._record(stop, "final-front-pose-missing-at-qualified-irq-commit", qualification)
            return
        if (front_proof["entry_marker_x"] != self.current_entry.get("marker_x") or
                front_proof["entry_seed_lives"] != self.current_entry.get("seed_lives")):
            raise GuardFailure("final FRONT IRQ proof belongs to a different seeded entry")
        audio_idle = busy == 0 and any(
            r["name"] == "terminal_post_psg_busy_zero" for r in ledger.records)
        if audio_idle and not any(
                r["name"] == "release_after_audio_and_front_commit" for r in ledger.records):
            held_input_pass = None
            if getattr(self, "scenario", None) == "natural":
                held_input_pass = self._release_entry_input_challenge(
                    stop, state, audio_idle=audio_idle, front_proof=True)
            ledger.record("release_after_audio_and_front_commit", {
                "busy_zero_precedes_release": True, "front_commit_precedes_release": True,
                "front_commit_event_ordinal": front_proof["irq_commit_event_ordinal"],
                "held_input_challenge_pass": held_input_pass,
                "event_ordinal": stop.ordinal})
            self.release_snapshot = {"player": (state["player_fb"], state["cell_x"],
                state["cell_y"], state["step"], state["face"], state["anim"]),
                "enemy_raw": state["enemy_raw"]}
            self.current_entry["released"] = True
            if self.cue_entry_owner.get(6) == self.current_entry["index"]:
                self.pending_terminal_cues.discard(6)
            self._record(stop, "entry-release-join", qualification, busy=busy,
                         final_front_pose=True,
                         front_commit_event_ordinal=front_proof["irq_commit_event_ordinal"],
                         terminal_audio_idle=True)

    def _dispatch(self, stop: MonitorStop) -> None:
        phase_deadline = getattr(self.client, "_bug117_phase_deadline", None)
        stop_context = {"phase": stop.phase, "phase_deadline_seconds": PHASE_SECONDS,
            "phase_deadline_monotonic": phase_deadline,
            "phase_remaining_seconds_at_dispatch": (max(0.0, phase_deadline - time.monotonic())
                if isinstance(phase_deadline, (float, int)) else None),
            "pc": stop.pc, "pc_hex": f"${stop.pc:04X}", "bp_id": stop.bp_id,
            "ordinal": stop.ordinal, "observed_monotonic": stop.observed_monotonic,
            "registers_at_stop": dict(stop.registers)}
        self.current_stop_context = stop_context
        try:
            self._dispatch_qualified(stop)
        except Exception as exc:
            context = getattr(exc, "failure_context", None)
            self.failure_context = (context if isinstance(context, dict) else {
                "kind": "observer-dispatch-failure", "stop": stop_context})
            if "stop" not in self.failure_context or self.failure_context.get("stop") is None:
                self.failure_context["stop"] = stop_context
            self.failure_context["error"] = f"{type(exc).__name__}: {exc}"
            if (getattr(self, "scenario", None) == "natural" and
                    stop_context["phase"] == "natural-contact-search"):
                self.failure_context["natural_contact_search"] = self._natural_contact_search_context({
                    "name": stop_context["phase"], "status": "dispatch-failure",
                    "deadline_seconds": PHASE_SECONDS})
            raise

    def _dispatch_qualified(self, stop: MonitorStop) -> None:
        qualification = self._qualify(stop)
        label = self.labels.get(stop.pc)
        if qualification.get("module") == "bootstrap-reset":
            self.bootstrap_reset_events.append({**qualification,
                "event_ordinal": stop.ordinal, "phase": stop.phase,
                "stop_pc": stop.pc, "breakpoint_id": stop.bp_id,
                "stop_context": self.current_stop_context})
            return
        if label is None and stop.pc == self.bus_marker["stop_pc"]:
            label = "SND_DATA"
        if label is None:
            raise GuardFailure(f"qualified stop PC ${stop.pc:04X} has no registered observer label")
        if stop.bp_id is not None and stop.pc in self.bp_ids and stop.bp_id != self.bp_ids[stop.pc]:
            raise GuardFailure(f"monitor breakpoint id at ${stop.pc:04X} differs from the installed marker")
        if label == "SND_DATA":
            self._psg_store(stop, qualification)
        elif label == "audio_mix_write":
            self._audio_start(stop, qualification)
        elif label == "audio_command_end":
            self._audio_end(stop, qualification)
        elif label == "post_psg_busy":
            self._busy_publication(stop, qualification)
        elif label == "fbiq_publish":
            self._irq_start(stop, qualification)
        elif label == "irq_commit_instruction_end":
            self._irq_instruction(stop, qualification)
        elif label == "fbiq_done":
            self._irq_done(stop, qualification)
        elif label == "et_player_death":
            self._enemy_contact(stop, qualification)
        elif label == "add_credit":
            self._presentation_credit_add(stop, qualification)
        elif label == "marker_entry_begin":
            self._entry_seed(stop, qualification)
        elif label == "iet_final_wait":
            self._final_entry_wait(stop, qualification)
        elif label == "iet_maze_entry":
            state = self._state()
            self._guard_first_maze_entry(stop, qualification, state)
            self._record(stop, label, qualification, entry=state["entry"],
                         death=state["death"], timer=state["timer"], frames=state["frames"])
        elif label == "mainloop":
            self._mainloop(stop, qualification)
        else:
            state = self._state()
            self._record(stop, label, qualification, entry=state["entry"],
                         death=state["death"], timer=state["timer"], frames=state["frames"])

    def _phase(self, name: str, predicate: Any) -> bool:
        started = time.monotonic()
        deadline = started + PHASE_SECONDS
        ordinal_before = self.pump.ordinal
        while time.monotonic() < deadline:
            stop = self.pump.next_stop(name, deadline)
            if stop is None:
                if self.pump.consecutive_timeouts >= 2:
                    phase = {"name": name, "status": "aborted-after-two-consecutive-observation-timeouts",
                        "deadline_seconds": PHASE_SECONDS, "stops": self.pump.ordinal - ordinal_before,
                        "observation_timeouts": self.pump.consecutive_timeouts,
                        "timeout_meaning": "the required event was not observed across two bounded waits; stop and reassess"}
                    self.phases.append(phase)
                    if name == "natural-contact-search" and self.scenario == "natural":
                        self.contact_search_timeout_context = self._natural_contact_search_context(phase)
                    return False
                continue
            self.client._bug117_phase_deadline = deadline
            try:
                self._dispatch(stop)
            finally:
                del self.client._bug117_phase_deadline
            if time.monotonic() >= deadline:
                phase = {"name": name, "status": "dispatch-reached-phase-deadline",
                    "deadline_seconds": PHASE_SECONDS, "stops": self.pump.ordinal - ordinal_before,
                    "timeout_meaning": "monitor event processing exhausted the named phase deadline"}
                self.phases.append(phase)
                if name == "natural-contact-search" and self.scenario == "natural":
                    self.contact_search_timeout_context = self._natural_contact_search_context(phase)
                return False
            if predicate():
                self.phases.append({"name": name, "status": "marker-observed",
                    "deadline_seconds": PHASE_SECONDS, "stops": self.pump.ordinal - ordinal_before,
                    "success_marker": "live event predicate"})
                return True
        phase = {"name": name, "status": "missing-marker-timeout",
            "deadline_seconds": PHASE_SECONDS, "stops": self.pump.ordinal - ordinal_before,
            "timeout_meaning": "required event was absent within the named phase"}
        self.phases.append(phase)
        if name == "natural-contact-search" and self.scenario == "natural":
            self.contact_search_timeout_context = self._natural_contact_search_context(phase)
        return False

    def _phase_initial(self, require_visible: bool) -> bool:
        def ready() -> bool:
            if self.current_entry is None or not self.cue_output[6]:
                return False
            if require_visible:
                return self.current_entry.get("first_maze_visible_frame") is not None
            return True
        return self._phase("initial-entry", lambda: self.cold_credited_start and ready())

    def _phase_fixture(self) -> bool:
        return self._phase("fixture-boundary", lambda: self.fixture_result is not None)

    def _phase_natural_contact(self, target: int) -> bool:
        return self._phase("natural-contact-search", lambda: self.contact_count >= target)

    def _phase_death_blank(self) -> bool:
        return self._phase("death-animation-blank", lambda: self.lifecycle is not None and
            any(r["name"] == "death_blank_timer37" for r in self.lifecycle.records))

    def _phase_cue13_idle(self) -> bool:
        return self._phase("cue13-normal-drain", lambda: self.lifecycle is not None and
            any(r["name"] == "cue13_published_idle" for r in self.lifecycle.records))

    def _phase_replacement(self, index: int) -> bool:
        return self._phase("replacement-entry", lambda: self.current_entry is not None and
            self.current_entry["index"] == index and self.current_entry.get("first_maze_visible_frame") is not None)

    def _phase_audio_and_release(self) -> bool:
        if not self._phase("audio-cue6", lambda: self.cue_output[6]):
            return False
        if not self._phase("audio-terminal", lambda: any(
                r["name"] == "terminal_post_psg_busy_zero"
                for ledger in self.proofs.values() for r in ledger.records)):
            return False
        return self._phase("irq-front-release", lambda: self.current_entry is not None and
            any(r["name"] == "release_after_audio_and_front_commit"
                for r in self.proofs[self.current_entry["index"]].records))

    def _run_phases(self) -> bool:
        if self.scenario in ("front-first", "music-first"):
            if not self._phase_initial(require_visible=True):
                return False
            for contact, entry_index in ((1, 2), (2, 3)):
                if not self._phase_natural_contact(contact):
                    return False
                if not self._phase_death_blank() or not self._phase_cue13_idle():
                    return False
                if not self._phase_replacement(entry_index):
                    return False
            if not self._phase_fixture():
                return False
            return self._phase_audio_and_release()
        if not self._phase_initial(require_visible=True):
            return False
        if self.scenario == "prior-music":
            if not self._phase_natural_contact(1) or not self._phase_fixture():
                return False
            if not self._phase_cue13_idle() or not self._phase_replacement(self.entry_count + 1):
                return False
            return self._phase_audio_and_release()
        for contact in (1, 2):
            if not self._phase_natural_contact(contact):
                return False
            if not self._phase_death_blank() or not self._phase_cue13_idle():
                return False
            if not self._phase_replacement(self.entry_count + 1):
                return False
        return self._phase_audio_and_release()

    def run(self) -> dict[str, Any]:
        self.install()
        success = self._run_phases()
        expected_reset_count = len(self.bootstrap_reset["reset_stores"])
        bootstrap_reset_status = {
            "expected_store_count": expected_reset_count,
            "observed_store_count": len(self.bootstrap_reset_events),
            "ordered_sequences": [event.get("sequence") for event in self.bootstrap_reset_events],
            "all_source_staged_live_match": all(
                event.get("source_staged_live_match") is True for event in self.bootstrap_reset_events),
            "pass": (len(self.bootstrap_reset_events) == expected_reset_count and
                     [event.get("sequence") for event in self.bootstrap_reset_events] ==
                     list(range(expected_reset_count)) and
                     all(event.get("source_staged_live_match") is True
                         for event in self.bootstrap_reset_events)),
        }
        success = success and bootstrap_reset_status["pass"]
        proof_status = {str(k): acceptance_status(v) for k, v in self.proofs.items()}
        lifecycle_status = [x.status() for x in self.lifecycle_records]
        relative = [((entry["first_maze_visible_frame"] - entry["cue6_first_frame"]) & 0xFFFF)
                    for entry in self.entries if entry.get("first_maze_visible_frame") is not None and
                    entry.get("cue6_first_frame") is not None]
        equal_relative = len(relative) >= 3 and len(set(relative)) == 1
        marker_columns = [entry.get("marker_x") for entry in self.entries]
        offscreen_remainders = [entry.get("offscreen_remaining_death_timer") for entry in self.entries]
        all_ledgers_pass = bool(proof_status) and all(x["pass"] for x in proof_status.values())
        all_lifecycles_pass = bool(lifecycle_status) and all(x["pass"] for x in lifecycle_status)
        fixture_order = None
        if self.scenario in ("front-first", "music-first"):
            target_ledger = (self.proofs.get(self.current_entry["index"])
                             if self.current_entry is not None else None)
            fixture_order = fixture_order_status(
                self.scenario, target_ledger.records if target_ledger is not None else [])
        held_input_status = (natural_held_input_status(
            self.entries, self.input_events, self.write_count) if self.scenario == "natural" else {
                "required_witness_count": 0,
                "witness_count": sum(isinstance(entry.get("held_input_challenge"), dict)
                                      for entry in self.entries),
                "pass_count": sum(entry.get("held_input_challenge", {}).get("pass") is True
                                  for entry in self.entries),
                "event_pairs_valid": None, "target_memory_write_count": self.write_count,
                "no_target_memory_writes": self.write_count == 0, "pass": None})
        if self.scenario == "natural":
            success = (success and len(self.entries) == 3 and self.contact_count == 2 and equal_relative and
                self.credit_evidence is not None and
                self.credit_evidence.get("one_credit_added") is True and
                self.credit_evidence.get("presentation_code_qualified") is True and
                self.credit_evidence.get("before") == 0 and self.credit_evidence.get("after_add") == 1 and
                self.credit_evidence.get("consumed_credit_count") == 0 and
                marker_columns[:3] == [296, 280, 264] and
                all(entry.get("marker_x_matches_life_slot") is True for entry in self.entries[:3]) and
                all(entry.get("offscreen_x320") is True and
                    entry.get("offscreen_x_pixels") == 320 for entry in self.entries[:3]) and
                all(entry.get("seed_death_timer") == 80 for entry in self.entries[:3]) and
                sorted(offscreen_remainders[:3]) == [52, 60, 68] and
                all(entry.get("seed_verified") is True and entry.get("released") is True and
                    entry.get("input_isolated_at_seed") is True for entry in self.entries[:3]) and
                held_input_status["pass"] is True and
                all_ledgers_pass and all_lifecycles_pass and not self.errors and
                not self.entry_contact_violation)
        elif self.scenario == "prior-music":
            success = (success and self.fixture_result is not None and all_lifecycles_pass and
                       all_ledgers_pass and not self.errors and not self.entry_contact_violation)
        else:
            success = (success and self.fixture_result is not None and all_ledgers_pass and
                all_lifecycles_pass and not self.errors and not self.entry_contact_violation and
                fixture_order is not None and fixture_order["pass"])
        if self.write_count > (0 if self.scenario == "natural" else 1):
            raise GuardFailure("live run exceeded the approved single $003A write budget")
        return {"scenario": self.scenario,
            "status": "SCENARIO_ACCEPTANCE_OBSERVED" if success else "INCOMPLETE_FAIL_CLOSED",
            "scenario_acceptance_observed": bool(success),
            "runtime_ready": False,
            "runtime_ready_reason": "parent must aggregate all required scenario artifacts and audit the evidence",
            "candidate_files": self.preparation["files"],
            "delivery_qualification": self.delivery, "cold_credited_start": self.cold_credited_start,
            "bootstrap_reset_qualification": {**bootstrap_reset_status,
                "source_staged_identity": self.bootstrap_reset,
                "events": self.bootstrap_reset_events,
                "classification": "bootstrap reset attenuation; excluded from runtime cue-owned PSG events"},
            "fixture": self.fixture_result, "target_write_count": self.write_count,
            "contacts": self.contacts, "contact_count": self.contact_count,
            "entries": self.entries, "marker_columns": [x.get("marker_x") for x in self.entries],
            "held_input_challenges": {**held_input_status,
                "scenario_scope": "natural only; forced fixture routes do not run this challenge",
                "witnesses": [entry.get("held_input_challenge") for entry in self.entries
                              if isinstance(entry.get("held_input_challenge"), dict)]},
            "offscreen_remaining_death_timer": offscreen_remainders,
            "seed_death_timer": [x.get("seed_death_timer") for x in self.entries],
            "cue_relative_first_maze_visibility_frames": relative,
            "equal_relative_visibility_all_three_entries": equal_relative,
            "forced_completion_order": fixture_order,
            "events": self.events,
            "cue_output_proven": self.cue_output, "cue_terminal": self.cue_terminal,
            "pending_terminal_cues": sorted(self.pending_terminal_cues),
            "quiet_tail": self.quiet_tail,
            "quiet_first_proofs": self.quiet_first_proofs,
            "quiet_refresh_records": self.quiet_refresh_records,
            "dwell_cadence_checks": self.dwell_checks,
            "proof_ledgers": proof_status, "lifecycle_ledgers": lifecycle_status,
            "front_pose_count": len(self.pose_hashes), "front_pose_sha256": self.pose_hashes,
            "phases": self.phases, "input_events": self.input_events,
            "natural_contact_search_context": self.contact_search_timeout_context,
            "cold_credit_evidence": self.credit_evidence,
            "monitor_stop_timeouts": self.pump.timeout_records, "errors": self.errors,
            "entry_contact_violation": self.entry_contact_violation,
            "emulator_launches": 1, "target_writes": self.write_count,
            "target_memory_write_count": self.write_count,
            "timing": {"phase_deadline_seconds": PHASE_SECONDS,
                "stop_wait_max_seconds": STOP_WAIT_SECONDS,
                "gameplay_worklist_target_cycles_max": GAMEPLAY_WORKLIST_CYCLE_TARGET,
                "gameplay_worklist_measured": False}}

    def release_inputs(self) -> None:
        ordinal = max(1, self.pump.ordinal)
        if self.search is not None:
            self.search.release(ordinal, "observer-shutdown")
        for key in list(self.pressed):
            monitor_call(self.client, "inject_key", {"key": key, "action": "release"})
            self.input_events.append({"key": key, "action": "release", "ordinal": ordinal,
                "reason": "observer-shutdown", "target_memory_write": False})
            self.pressed.discard(key)


def run_live_capture(binary: Path, build: Path, output: Path, scenario: str,
                     preparation: dict[str, Any], profile: dict[str, Any],
                     delivery: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Launch only after all gates; record fail-closed output for each bounded run."""
    output.mkdir(parents=True, exist_ok=True)
    api = monitor_api()
    process = None
    client = None
    observer = None
    result: dict[str, Any]
    exit_code = 2
    try:
        process, client = api.launch(binary.resolve(strict=True),
            (build.resolve(strict=True) / "ladybug.rom"), api.free_port())
        observer = LiveRuntimeObserver(client, build, scenario, preparation, delivery)
        result = observer.run()
        result["scenario_acceptance_observed"] = result.get("scenario_acceptance_observed") is True
        if result["scenario_acceptance_observed"]:
            exit_code = 0
    except Exception as exc:
        result = {"scenario": scenario, "status": "INCOMPLETE_FAIL_CLOSED",
            "scenario_acceptance_observed": False, "runtime_ready": False,
            "runtime_ready_reason": "parent aggregation and evidence audit are still required",
            "error": f"{type(exc).__name__}: {exc}", "emulator_launches": int(process is not None),
            "target_write_count": observer.write_count if observer is not None else 0,
            "target_writes": observer.write_count if observer is not None else 0,
            "events": observer.events if observer is not None else [],
            "phases": observer.phases if observer is not None else [],
            "errors": observer.errors if observer is not None else [str(exc)]}
        result["bootstrap_reset_events"] = (
            observer.bootstrap_reset_events if observer is not None else [])
        if observer is not None and observer.failure_context is not None:
            result["failure_context"] = observer.failure_context
        elif isinstance(getattr(exc, "failure_context", None), dict):
            result["failure_context"] = exc.failure_context
        if observer is not None and observer.contact_search_timeout_context is not None:
            result["natural_contact_search_context"] = observer.contact_search_timeout_context
    finally:
        if observer is not None and client is not None:
            try:
                client.call("pause", timeout=STOP_WAIT_SECONDS)
            except Exception:
                pass
            try:
                observer.release_inputs()
            except Exception as exc:
                result.setdefault("cleanup_errors", []).append(f"input-release: {exc}")
        if client is not None:
            try:
                client.close()
            except Exception as exc:
                result.setdefault("cleanup_errors", []).append(f"monitor-close: {exc}")
        if process is not None:
            api.stop(process)
            try:
                process.wait(timeout=2)
            except Exception as exc:
                result.setdefault("cleanup_errors", []).append(f"xroar-stop: {exc}")
    if result.get("cleanup_errors"):
        result["status"] = "INCOMPLETE_FAIL_CLOSED"
        result["scenario_acceptance_observed"] = False
        result["runtime_ready"] = False
        exit_code = 2
    result["qualified_profile"] = profile
    result["delivery_qualification"] = delivery
    result["preparation"] = preparation
    result["emulator_launches"] = int(process is not None)
    report_path = output / f"bug117-{scenario}-runtime.json"
    report_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return {"status": result.get("status"), "report": str(report_path),
            "runtime_ready": False,
            "scenario_acceptance_observed": result.get("scenario_acceptance_observed") is True,
            "emulator_launches": result["emulator_launches"],
            "target_writes": result.get("target_write_count", 0)}, exit_code


def _good(scenario: str) -> dict[str, Any]:
    if scenario in ("front-first", "music-first"):
        d = {"timer_map_qualified": True, "timer_address": TIMER_ADDRESS,
             "source_map_bytes_qualified": True, "render_pending": 0,
             "owner_a_player_valid": 0, "owner_b_player_valid": 0,
             "cue_published_busy": 1, "cue_actual_output_proven": True,
             "actual_psg_writes_match_mix": True, "entry_state": 3,
             "death_state": 0, "marker_x": 264, "lives": 0,
             "player_x": 320, "cue_active_id": 6,
             "slot0_id": 6, "slot0_policy": 0xB3, "slot0_priority": 5,
             "best_slot": 0, "best_priority": 5, "cue6_selected_voice_mask": 7,
             "cue6_selected_audible_voice_count": 1,
             "higher_priority_exclusive_source": False}
        if scenario == "front-first":
            d.update(remaining_pad=1, cue_dwell_cadence_viable=True)
        return d
    return {"timer_map_qualified": True, "timer_address": TIMER_ADDRESS,
            "source_map_bytes_qualified": True, "render_pending": 0,
            "owner_a_player_valid": 0, "owner_b_player_valid": 0,
            "cue_published_busy": 1, "cue_actual_output_proven": True,
            "actual_psg_writes_match_mix": True, "entry_state": 0,
            "death_state": 3, "death_timer": 37, "lives": 1,
            "genuine_enemy_contact_proven": True, "cue_active_id": 13,
            "slot0_id": 13, "slot0_policy": 0xD3, "slot0_priority": 6,
            "best_slot": 0, "best_priority": 6, "cue13_selected_voice_mask": 3,
            "cue13_selected_audible_voice_count": 1,
            "higher_priority_exclusive_source": False,
            "cue13_actual_output_proven": True, "cue13_published_busy": 1}


def self_test() -> dict[str, Any]:
    tested = 0
    raw_length = 0xFDEF - RESIDENT_IMAGE_BASE
    raw_fixture = bytes((index * 37 + 11) & 0xFF for index in range(raw_length))
    staged_fixture = raw_fixture + b"\xFF" * (RESIDENT_IMAGE_BYTES - raw_length)
    resident = qualify_staged_resident_image(0xFDEF, staged_fixture, sha(raw_fixture),
                                              sha(staged_fixture))
    assert resident["raw_length"] == raw_length and resident["padding_bytes"] == 529
    tested += 1
    try:
        qualify_staged_resident_image(0xFDEF, staged_fixture, "0" * 64, sha(staged_fixture))
    except GuardFailure:
        tested += 1
    else:
        raise AssertionError("wrong raw assembled-prefix hash passed resident qualification")
    try:
        qualify_staged_resident_image(0xFDEF, staged_fixture, sha(raw_fixture), "0" * 64)
    except GuardFailure:
        tested += 1
    else:
        raise AssertionError("wrong full staged artifact hash passed resident qualification")
    non_ff_padding = bytearray(staged_fixture)
    non_ff_padding[raw_length] = 0
    try:
        qualify_staged_resident_image(0xFDEF, bytes(non_ff_padding), sha(raw_fixture),
                                      sha(bytes(non_ff_padding)))
    except GuardFailure:
        tested += 1
    else:
        raise AssertionError("non-FF resident image padding passed qualification")
    try:
        qualify_staged_resident_image(0xBFFF, staged_fixture, sha(raw_fixture), sha(staged_fixture))
    except GuardFailure:
        tested += 1
    else:
        raise AssertionError("invalid map-derived resident asset_end passed qualification")
    artifact_hashes = {name: sha(name.encode("ascii")) for name in SOURCE_RECEIPT_HASH_FILES}
    validate_source_receipt_artifact_hashes(artifact_hashes, artifact_hashes)
    missing_artifact_hashes = dict(artifact_hashes)
    del missing_artifact_hashes["ladybug-audio-runtime.bin"]
    try:
        validate_source_receipt_artifact_hashes(artifact_hashes, missing_artifact_hashes)
    except GuardFailure:
        tested += 1
    else:
        raise AssertionError("source receipt gate accepted a missing non-resident artifact")
    valid_layout = {"gmc": {"final_image_sha256": "a" * 64}}
    validate_layout_final_image_identity(valid_layout, "a" * 64)
    try:
        validate_layout_final_image_identity(valid_layout, "b" * 64)
    except GuardFailure:
        tested += 1
    else:
        raise AssertionError("sparse layout accepted a different final ROM identity")
    if ROOT is not None and (ROOT / "build/source-build-receipt.json").is_file():
        current_profile = require_adaptive_keyboard_profile(ROOT / "build")
        assert current_profile["profile"] == "complete / adaptive / keyboard"
        qualification = current_profile["resident_image_qualification"]
        assert (qualification["raw_prefix_sha256"] == current_profile["invocation"]["assembled_sha256"] and
                qualification["staged_sha256"] == current_profile["staged_resident_sha256"] and
                qualification["padding_byte"] == "FF")
        tested += 1

    class FakePumpClient:
        def __init__(self, hit: dict[str, Any] | None = None, wait: dict[str, Any] | None = None):
            self.hit = hit
            self.wait_result = wait or hit or {"reason": "timeout"}
            self.events: list[dict[str, Any]] = []
            self.calls: list[tuple[str, dict[str, Any] | None]] = []
            self.timeouts: list[float] = []
            self.register_pc = 0x1234
        def call(self, method: str, params: dict[str, Any] | None = None, timeout: float = 20.0):
            self.calls.append((method, params))
            self.timeouts.append(timeout)
            assert 0 < timeout <= STOP_WAIT_SECONDS
            if method == "run": return {}
            if method == "read_registers":
                return {"pc": self.register_pc, "dp": 0}
            if method == "wait_for_stop":
                return self.wait_result
            if method == "pause":
                return {"state": "halted"}
            raise AssertionError(f"unexpected fake monitor method {method}")
    fake_clock = lambda: 1.0
    pump_client = FakePumpClient({"pc": 0x1234, "bp_id": 9, "reason": "breakpoint"})
    pumped = BoundedMonitorEventPump(pump_client, clock=fake_clock).next_stop("fake-phase", 5.0)
    assert pumped is not None and pumped.pc == 0x1234 and pumped.bp_id == 9
    assert [method for method, _ in pump_client.calls] == ["run", "wait_for_stop", "read_registers"]
    assert all(timeout <= STOP_WAIT_SECONDS for timeout in pump_client.timeouts)
    tested += 1
    raced_client = FakePumpClient(wait={"reason": "breakpoint", "pc": 0x1234, "bp_id": 0})
    raced = BoundedMonitorEventPump(raced_client, clock=fake_clock).next_stop("watch-race", 5.0)
    assert raced is not None and raced.pc == 0x1234 and raced.bp_id == 0
    tested += 1
    class PauseRaceClient(FakePumpClient):
        def call(self, method: str, params: dict[str, Any] | None = None, timeout: float = 20.0):
            result = super().call(method, params, timeout)
            if method == "pause":
                self.events.append({"method": "bp", "params": {"pc": 0x1234, "bp_id": 0}})
            return result
    pause_race_client = PauseRaceClient()
    pause_race = BoundedMonitorEventPump(pause_race_client, clock=fake_clock).next_stop(
        "pause-notification-race", 5.0)
    assert pause_race is not None and pause_race.pc == 0x1234
    tested += 1
    class NotificationBeforeAckClient(FakePumpClient):
        def call(self, method: str, params: dict[str, Any] | None = None, timeout: float = 20.0):
            result = super().call(method, params, timeout)
            if method == "run":
                self.events.append({"method": "bp", "params": {"pc": 0x1234, "bp_id": 7}})
            return result
    ack_race_client = NotificationBeforeAckClient(wait={"reason": "timeout"})
    ack_race = BoundedMonitorEventPump(ack_race_client, clock=fake_clock).next_stop(
        "breakpoint-before-run-ack", 5.0)
    assert ack_race is not None and ack_race.pc == 0x1234 and ack_race.bp_id == 7
    assert ack_race_client.calls[-1][0] == "read_registers"
    tested += 1
    timeout_client = FakePumpClient()
    timeout_pump = BoundedMonitorEventPump(timeout_client, clock=fake_clock)
    assert timeout_pump.next_stop("missing-event", 5.0) is None
    assert timeout_pump.timeout_records[0]["reason"] == "no-stop-before-bounded-wait"
    assert any(method == "pause" for method, _ in timeout_client.calls)
    tested += 1
    timeout_observer = object.__new__(LiveRuntimeObserver)
    timeout_observer.pump = BoundedMonitorEventPump(FakePumpClient())
    timeout_observer.phases = []
    timeout_observer._dispatch = lambda *args: (_ for _ in ()).throw(
        AssertionError("timeout-only phase unexpectedly dispatched a stop"))
    assert timeout_observer._phase("two-timeout-stop", lambda: False) is False
    assert timeout_observer.phases[0]["status"] == "aborted-after-two-consecutive-observation-timeouts"
    assert len(timeout_observer.pump.timeout_records) == 2
    tested += 1
    mismatch_client = FakePumpClient({"pc": 0x1234, "bp_id": 1, "reason": "breakpoint"})
    mismatch_client.register_pc = 0x5678
    try:
        BoundedMonitorEventPump(mismatch_client, clock=fake_clock).next_stop("wrong-pc", 5.0)
    except GuardFailure:
        tested += 1
    else:
        raise AssertionError("monitor event PC mismatch passed the live stop pump")
    try:
        BoundedMonitorEventPump(FakePumpClient(), clock=fake_clock,
                               stop_wait_seconds=STOP_WAIT_SECONDS + 1)
    except GuardFailure:
        tested += 1
    else:
        raise AssertionError("monitor pump accepted a stop wait above ten seconds")

    class FakeInputClient:
        def __init__(self): self.calls: list[tuple[str, dict[str, Any]]] = []
        def call(self, method: str, params: dict[str, Any], timeout: float = 20.0):
            self.calls.append((method, params))
            return {}
    input_client = FakeInputClient()
    canonical_matrix = bytes((27, 35, 43, 51, 6))
    search = InputOnlySearch(input_client, canonical_matrix)
    assert search.bindings == bytes((43, 44, 45, 46, 48))
    assert matrix_binding_to_dscan(COIN5_MATRIX_KEY) == COIN5_DSCAN_KEY
    tested += 1

    search_symbols = {"PLAYER_DIR": 0x06, "PLAYER_WANT": 0x0F,
        "BOX_TIMER": 0x4A, "ENEMY_TIMER": 0x55, "ENEMY_ACTIVE": 0x58,
        "ENEMY_RELEASED": 0x59, "FREEZE_TIMER": 0x5B}
    low_snapshot = bytearray(0x300)
    for name, value in (("PLAYER_DIR", 3), ("PLAYER_WANT", 2), ("BOX_TIMER", 7),
                        ("ENEMY_TIMER", 19), ("ENEMY_ACTIVE", 4), ("ENEMY_RELEASED", 11)):
        low_snapshot[search_symbols[name]] = value
    low_snapshot[0x5B:0x5D] = bytes.fromhex("1234")
    search_state = decode_contact_search_state(bytes(low_snapshot), search_symbols)
    assert search_state == {"player_dir": 3, "player_want": 2, "box_timer": 7,
        "enemy_timer": 19, "enemy_active": 4, "enemy_released": 11,
        "freeze_timer": 0x1234}
    tested += 1
    try:
        decode_contact_search_state(bytes(0x100), search_symbols)
    except GuardFailure as exc:
        assert "complete cached" in str(exc)
        tested += 1
    else:
        raise AssertionError("contact search decoded an incomplete low-RAM snapshot")

    search.at_gameplay_center(1, 0, 0, 0, 5, 7)
    assert search.held == 43 and input_client.calls == [("inject_key", {"key": 43, "action": "press"})]
    search.at_gameplay_center(2, 2, 0, 0, 5, 7)
    assert search.held is None and [x[1]["action"] for x in input_client.calls] == ["press", "release"]
    assert all(x[1]["key"] == 43 for x in input_client.calls)
    assert all(method == "inject_key" for method, _ in input_client.calls)
    assert all(not event["target_memory_write"] for event in search.actions)
    assert all(event["key_namespace"] == "DSCAN" for event in search.actions)
    tested += 1

    waypoint_client = FakeInputClient()
    waypoint_search = InputOnlySearch(waypoint_client, canonical_matrix)
    waypoint_search.at_gameplay_center(10, 0, 0, 0, 12, 18)
    for ordinal, step, cell_y in ((11, 1, 18), (12, 2, 18), (13, 3, 18), (14, 0, 17)):
        waypoint_search.at_gameplay_center(ordinal, 0, 0, step, 12, cell_y)
    assert waypoint_search.held == 43 and waypoint_search.direction == 0
    assert [(params["key"], params["action"]) for _, params in waypoint_client.calls] == [(43, "press")]
    assert waypoint_search.origin == (12, 17) and waypoint_search.age_stops == 0
    for ordinal in range(15, 23):
        waypoint_search.at_gameplay_center(ordinal, 0, 0, 0, 12, 17)
    assert waypoint_search.held == 44 and waypoint_search.direction == 1
    assert [(params["key"], params["action"]) for _, params in waypoint_client.calls] == [
        (43, "press"), (43, "release"), (44, "press")]
    assert waypoint_search.actions[-2]["reason"] == "source-qualified-observed-no-progress-route-retry"
    assert waypoint_search.actions[-2]["no_progress_stops"] == 8
    assert waypoint_search.actions[-1]["direction_index"] == 1
    noncenter_client = FakeInputClient()
    noncenter_search = InputOnlySearch(noncenter_client, canonical_matrix)
    noncenter_search.at_gameplay_center(24, 0, 0, 0, 12, 18)
    noncenter_search.at_gameplay_center(25, 0, 0, 1, 12, 18)
    for ordinal in range(26, 35):
        noncenter_search.at_gameplay_center(ordinal, 0, 0, 1, 12, 18)
    assert noncenter_search.held == 43 and noncenter_search.direction == 0
    assert [params["action"] for _, params in noncenter_client.calls] == ["press"]
    tested += 1

    isolation_client = FakeInputClient()
    isolation_search = InputOnlySearch(isolation_client, canonical_matrix)
    isolation_search.at_gameplay_center(30, 0, 0, 0, 5, 7)
    for ordinal in range(31, 39):
        isolation_search.at_gameplay_center(ordinal, 0, 0, 0, 5, 7)
    assert isolation_search.held == 44 and isolation_search.direction == 1
    isolation_search.at_gameplay_center(39, 0, 1, 0, 5, 7)
    assert isolation_search.held is None and isolation_search.direction == 1
    assert [params["action"] for _, params in isolation_client.calls] == [
        "press", "release", "press", "release"]
    assert not any(action.get("target_memory_write") for action in isolation_search.actions)
    tested += 1

    context_observer = object.__new__(LiveRuntimeObserver)
    context_observer.scenario = "natural"
    context_observer.last_runtime_state = {
        "entry": 0, "death": 0, "timer": 80, "lives": 3, "frames": 0x1234,
        "player_fb": 0x123456, "cell_x": 12, "cell_y": 18, "step": 0,
        "dir": 1, "want": 1, "player_dir": 1, "player_want": 1,
        "box_timer": 5, "enemy_timer": 23, "enemy_active": 2,
        "enemy_released": 4, "freeze_timer": 0x0102,
        "enemy_raw": bytes(range(32)), "enemy_sha256": sha(bytes(range(32))),
    }
    context_observer.last_runtime_state_stop = {"phase": "natural-contact-search",
        "phase_deadline_seconds": PHASE_SECONDS, "pc": 0xC101, "bp_id": 7, "ordinal": 900}
    context_observer.current_stop_context = dict(context_observer.last_runtime_state_stop)
    context_observer.search = InputOnlySearch(FakeInputClient(), canonical_matrix)
    context_observer.search.actions = [{"ordinal": i, "action": "press" if i % 2 == 0 else "release",
        "target_memory_write": False} for i in range(70)]
    context_observer.input_events = [{"ordinal": i, "target_memory_write": False} for i in range(70)]
    context_observer.entries = [{"index": 1, "held_input_challenge": {"valid": True}}]
    context_observer.current_entry = context_observer.entries[0]
    context_observer.proofs = {1: ProofLedger()}
    context_observer.lifecycle_records = []
    context_observer.lifecycle = None
    context_observer.contact_count = 0
    context_observer.contacts = []
    context_observer.write_count = 0
    context_summary = context_observer._natural_contact_search_context({
        "name": "natural-contact-search", "status": "missing-marker-timeout",
        "deadline_seconds": PHASE_SECONDS, "timeout_meaning": "contact absent"})
    assert context_summary["cached_only_no_monitor_reread"] is True
    assert context_summary["no_progress_cause"] == "not_inferred_from_player_pose_alone"
    assert context_summary["last_stop"]["ordinal"] == 900
    assert context_summary["last_low_ram_state"]["player_want"] == 1
    assert context_summary["last_low_ram_state"]["box_timer"] == 5
    assert context_summary["last_low_ram_state"]["enemy_timer"] == 23
    assert context_summary["last_low_ram_state"]["enemy_active"] == 2
    assert context_summary["last_low_ram_state"]["enemy_released"] == 4
    assert context_summary["last_low_ram_state"]["freeze_timer"] == 0x0102
    assert context_summary["last_low_ram_state"]["enemy_raw"]["hex"] == bytes(range(32)).hex()
    assert len(context_summary["input_only_search"]["actions_tail"]) == 64
    assert len(context_summary["input_events_tail"]) == 64
    assert context_summary["entries"][0]["index"] == 1
    assert "1" in context_summary["proof_ledgers"]
    assert context_summary["target_memory_write_count"] == 0
    assert json.loads(json.dumps(context_summary)) == context_summary
    assert context_observer.search.client.calls == []
    tested += 1

    class FakeSearchTimeoutPump:
        def __init__(self):
            self.consecutive_timeouts = 2
            self.ordinal = 900
        def next_stop(self, phase: str, deadline: float):
            assert phase == "natural-contact-search"
            return None

    timeout_observer = object.__new__(LiveRuntimeObserver)
    timeout_observer.__dict__.update(context_observer.__dict__)
    timeout_observer.pump = FakeSearchTimeoutPump()
    timeout_observer.phases = []
    timeout_observer.contact_search_timeout_context = None
    assert timeout_observer._phase("natural-contact-search", lambda: False) is False
    timeout_context = timeout_observer.contact_search_timeout_context
    assert timeout_context["phase"]["status"] == "aborted-after-two-consecutive-observation-timeouts"
    assert timeout_context["cached_only_no_monitor_reread"] is True
    assert timeout_observer.pump.ordinal == 900
    assert json.loads(json.dumps(timeout_context)) == timeout_context
    assert timeout_observer.search.client.calls == []
    tested += 1

    class FakeChallengeClient(FakeInputClient):
        def call(self, method: str, params: dict[str, Any], timeout: float = 20.0):
            self.calls.append((method, params))
            if method == "read_memory" and params["addr"] == 0x02D4:
                return {"data": "00", "space": "cpu"}
            return {}

    def fake_held_entry(generation: int, marker_x: int, *, include_state3: bool = True,
                        omit_front: tuple[int, int] | None = None,
                        mutate_front: tuple[int, int] | None = None) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
        client = FakeChallengeClient()
        observer = object.__new__(LiveRuntimeObserver)
        observer.client = client
        observer.scenario = "natural"
        observer.current_entry = {"index": generation, "marker_x": None,
            "pose_count": 0, "first_maze_visible_frame": None}
        observer.errors = []
        observer.input_events = []
        observer.pressed = set()
        observer.bindings = canonical_matrix
        observer.search = InputOnlySearch(client, canonical_matrix)
        observer.lifecycle = None
        observer.contact_count = 0
        observer.cue_entry_owner = {6: generation}
        observer.pending_terminal_cues = {6}
        first_terminal_record = {"stream_identity": {"cue_id": 6,
            "start_ordinal": generation * 100 - 10, "entry": generation,
            "end_ordinal": generation * 100 - 5}, "actual_mute_attenuation_stores": 3,
            "mute_store_ordinal": generation * 100 - 3,
            "busy_zero_ordinal": generation * 100 - 1}
        observer.cue_terminal = {6: {"cue_id": 6, "start_ordinal": generation * 100 - 10,
            "entry": generation, "ordinal": generation * 100 - 5}}
        observer.quiet_tail = {6: first_terminal_record}
        observer.quiet_first_proofs = [first_terminal_record]
        observer.quiet_refresh_records = []
        observer._record = lambda *args, **kwargs: None
        lives = 3 - generation
        start_fb = VISIBLE_BASE + 10 * 160 + marker_x // 2
        state = {"entry": 2, "death": 0, "lives": lives, "timer": 80,
            "frames": 100 + generation, "player_fb": start_fb,
            "cell_x": 4, "cell_y": 22, "step": 0, "face": 1, "dir": 1, "anim": 0}
        start_stop = MonitorStop("fake-entry-state2", 0xC000, 1,
                                 {"pc": 0xC000}, generation * 100, 100.0 + generation)
        observer._confirm_entry_state(start_stop, {}, state)
        key = matrix_binding_to_dscan(canonical_matrix[ENTRY_SOUTH_BINDING_INDEX])
        assert observer.current_entry["held_input_challenge"]["dscan_key"] == key == 44
        assert observer.pressed == {key}
        assert observer.input_events[0]["action"] == "press"
        assert observer.input_events[0]["matrix_key"] == canonical_matrix[ENTRY_SOUTH_BINDING_INDEX]

        def observe(sample: dict[str, Any], ordinal: int) -> MonitorStop:
            stop = MonitorStop("fake-held-entry", 0xC000, 1, {"pc": 0xC000},
                               ordinal, 200.0 + ordinal)
            observer._observe_entry_input_challenge(stop, sample, "fake-mainloop")
            return stop

        def front(sample: dict[str, Any], ordinal: int, *, wrong: bool = False) -> None:
            stop = MonitorStop("fake-held-front", 0xC000, 1, {"pc": 0xC000},
                               ordinal, 300.0 + ordinal)
            pose = {"entry": sample["entry"], "player_fb": sample["player_fb"],
                "face": sample["face"], "animation": sample["anim"],
                "candidate_art_identity_qualified": True}
            if wrong:
                pose["face"] = (sample["face"] + 1) & 3
            observer._record_challenge_front_pose(stop, sample, pose)

        ordinal = generation * 100 + 1
        for x in range(marker_x, 320, 2):
            walk = dict(state, player_fb=start_fb + (x - marker_x) // 2,
                        frames=state["frames"] + ordinal)
            stop = observe(walk, ordinal)
            front_missing = omit_front == (2, x)
            front_wrong = mutate_front == (2, x)
            if not front_missing:
                front(walk, ordinal, wrong=front_wrong)
            ordinal += 1
        if include_state3:
            offscreen = dict(state, entry=3, player_fb=start_fb + (320 - marker_x) // 2,
                             frames=state["frames"] + ordinal)
            observe(offscreen, ordinal)
            observe(dict(offscreen), ordinal + 1)
            ordinal += 2
        maze_fb = VISIBLE_BASE + 50 * 160 + 70
        for n in range(17):
            maze = {"entry": 4, "death": 0, "lives": lives, "frames": state["frames"] + ordinal,
                "player_fb": maze_fb - n * 320, "cell_x": 4, "cell_y": 22 - n // 4,
                "step": n % 4, "face": 0, "dir": 0, "anim": 0}
            observe(maze, ordinal)
            front_missing = omit_front == (4, n)
            front_wrong = mutate_front == (4, n)
            if not front_missing:
                front(maze, ordinal, wrong=front_wrong)
            ordinal += 1
        final_state = {"entry": 4, "death": 0, "lives": lives, "frames": state["frames"] + ordinal,
            "player_fb": maze_fb - 16 * 320, "cell_x": 4, "cell_y": 18,
            "step": 0, "face": 0, "anim": 0, "enemy_raw": b"same"}
        observer.audio = {"AUDIO_MUSIC_PUBLISHED_BUSY": 0x02D4}
        observer.proofs = {generation: ProofLedger()}
        observer.proofs[generation].record("terminal_post_psg_busy_zero", {
            "busy": 0, "all_slots_queues_credit_idle": True,
            "busy_read_after_psg": True, "event_ordinal": generation * 1000 + 1})
        observer.proofs[generation].record("final_pose_in_front_after_irq_commit", {
            "irq_commit_observed": True, "front_pixels_match_opaque_player": True,
            "live_code_span_qualified": True, "irq_live_opcode_match": True,
            "front_mapping_qualified": True, "same_stop_busy_sample": True,
            "opaque_pixels_compared": 72, "visible_width_bytes": 8,
            "published_music_busy": 0, "irq_commit_end_pc": 0x0EDB,
            "front_id": 1, "front_owner_voff1_shadow": 0xB0,
            "front_owner_voff2_shadow": 0, "front_physical_base": 0x58000,
            "entry_marker_x": marker_x, "entry_seed_lives": lives,
            "irq_commit_event_ordinal": generation * 1000 + 2,
            "event_ordinal": generation * 1000 + 2})
        observer._state = lambda: final_state
        observer.release_snapshot = None
        observer._record = lambda *args, **kwargs: None
        final_stop = MonitorStop("fake-final-wait", 0xC000, 1, {"pc": 0xC000},
                                 generation * 1000 + 3, 900.0 + generation)
        assert not observer._release_entry_input_challenge(
            final_stop, final_state, audio_idle=False, front_proof=True)
        assert not observer._release_entry_input_challenge(
            final_stop, final_state, audio_idle=True, front_proof=False)
        assert observer.pressed == {key}
        observer._final_entry_wait(final_stop, {})
        witness = observer.current_entry["held_input_challenge"]
        assert observer.current_entry["released"] is True
        assert witness["release_ordinal"] == final_stop.ordinal
        assert observer.proofs[generation].records[-1]["name"] == "release_after_audio_and_front_commit"
        assert observer.pressed == set()
        assert 6 not in observer.pending_terminal_cues
        assert observer.quiet_tail[6] is first_terminal_record
        assert observer.quiet_first_proofs == [first_terminal_record]
        return observer.current_entry, observer.input_events, observer.errors

    held_entries = []
    held_events = []
    held_errors: list[str] = []
    for generation, marker_x in enumerate((296, 280, 264), 1):
        entry, events, errors = fake_held_entry(generation, marker_x)
        assert entry["held_input_challenge"]["pass"] is True and not errors
        held_entries.append(entry)
        held_events.extend(events)
        held_errors.extend(errors)
    held_status = natural_held_input_status(held_entries, held_events, 0)
    assert held_status["pass"] and held_status["witness_count"] == 3
    assert held_status["target_memory_write_count"] == 0
    assert not natural_held_input_status(held_entries[:2], held_events, 0)["pass"]
    assert not natural_held_input_status(held_entries, held_events, 1)["pass"]
    wrong_challenge_key_events = [dict(event) for event in held_events]
    wrong_challenge_key_events[0]["key"] = 43
    assert not natural_held_input_status(held_entries, wrong_challenge_key_events, 0)["pass"]
    tested += 5

    missing_state3_entry, _, missing_state3_errors = fake_held_entry(1, 296, include_state3=False)
    assert missing_state3_entry["held_input_challenge"]["pass"] is False and missing_state3_errors
    tested += 1
    mutated_front_entry, _, mutated_front_errors = fake_held_entry(1, 296, mutate_front=(4, 5))
    assert mutated_front_entry["held_input_challenge"]["pass"] is False and mutated_front_errors
    tested += 1
    missing_front_entry, _, missing_front_errors = fake_held_entry(1, 296, omit_front=(4, 7))
    assert missing_front_entry["held_input_challenge"]["pass"] is False
    assert missing_front_entry["held_input_challenge"]["observed_front_maze_player_fb"] != \
        missing_front_entry["held_input_challenge"]["expected_front_maze_player_fb"]
    tested += 1

    offscreen_generation = 7
    offscreen_row = VISIBLE_BASE + 30 * 160
    offscreen_entry = {"index": offscreen_generation,
        "entry_start_fb": offscreen_row + 296 // 2, "marker_x": 296}
    offscreen_state = {"entry": 3, "death": 0, "player_fb": offscreen_row + 160,
        "front": 0, "valid_a": 0, "valid_b": 1}
    saved_under = bytes([0xA5]) * 128
    last_visible = {"entry_generation": offscreen_generation, "owner": 0,
        "pointer": offscreen_row + 159, "actual": bytes([0x5A]) * 128,
        "background": saved_under, "visible_width_bytes": 1, "event_ordinal": 10}
    restored = validate_offscreen_owner_retirement(
        offscreen_state, offscreen_entry, last_visible, saved_under)
    assert restored["status"] == "RESTORED"
    assert restored["restored_pixels_match_saved_under"] is True
    tested += 1

    for changed_state in (
            dict(offscreen_state, entry=2),
            dict(offscreen_state, player_fb=offscreen_row + 159),
            dict(offscreen_state, valid_a=1)):
        try:
            validate_offscreen_owner_retirement(changed_state, offscreen_entry,
                                                last_visible, saved_under)
        except GuardFailure:
            pass
        else:
            raise AssertionError("offscreen state, x, or valid-metadata negative was accepted")
    tested += 3

    try:
        validate_offscreen_owner_retirement(offscreen_state, offscreen_entry, None, saved_under)
    except GuardFailure:
        pass
    else:
        raise AssertionError("missing owner snapshot was accepted")
    tested += 1

    mismatched_underlay = bytearray(saved_under)
    mismatched_underlay[0] ^= 0x01
    try:
        validate_offscreen_owner_retirement(offscreen_state, offscreen_entry,
                                            last_visible, bytes(mismatched_underlay))
    except GuardFailure:
        pass
    else:
        raise AssertionError("mismatched restored underlay was accepted")
    tested += 1

    owner_a_proof = {"status": "RESTORED", "entry_generation": offscreen_generation,
        "owner": 0, "event_ordinal": 20}
    owner_b_proof = {"status": "RESTORED", "entry_generation": offscreen_generation,
        "owner": 1, "event_ordinal": 21}
    gated_entry = {"index": offscreen_generation, "offscreen_retirement": {
        "entry_generation": offscreen_generation,
        "retired_by_owner": {0: owner_a_proof, 1: owner_b_proof}}}
    assert offscreen_maze_entry_gate(gated_entry, 30)["pass"] is True
    premature_entry = {"index": offscreen_generation, "offscreen_retirement": {
        "entry_generation": offscreen_generation, "retired_by_owner": {0: owner_a_proof}}}
    assert offscreen_maze_entry_gate(premature_entry, 30)["pass"] is False
    assert offscreen_maze_entry_gate(gated_entry, 20)["pass"] is False
    tested += 3

    serializable_offscreen_entry = {"index": offscreen_generation,
        "offscreen_retirement": {"entry_generation": offscreen_generation,
            "last_visible_by_owner": {"0": {"entry_generation": offscreen_generation,
                "owner": 0, "pointer": offscreen_row + 159, "visible_width_bytes": 1,
                "event_ordinal": 10, "actual_sha256": sha(bytes([0x5A]) * 128),
                "saved_under_sha256": sha(saved_under)}},
            "retired_by_owner": {"0": owner_a_proof, "1": owner_b_proof},
            "state3_observations": [], "maze_entry_gate": offscreen_maze_entry_gate(
                gated_entry, 30)}}
    json.dumps({"entries": [serializable_offscreen_entry],
                "offscreen_owner_snapshots": {"generation_owner": "private bytes omitted"}},
               allow_nan=False)
    tested += 1

    offscreen_fake = object.__new__(LiveRuntimeObserver)
    offscreen_fake.current_entry = {"index": offscreen_generation,
        "entry_start_fb": offscreen_entry["entry_start_fb"], "marker_x": 296,
        "offscreen_retirement": {"entry_generation": offscreen_generation,
            "last_visible_by_owner": {}, "retired_by_owner": {},
            "state3_observations": [], "maze_entry_gate": None}}
    offscreen_fake.offscreen_owner_snapshots = {}
    offscreen_fake.errors = []
    offscreen_fake.recorded_events = []
    offscreen_fake._record = lambda stop, label, qualification, **fields: \
        offscreen_fake.recorded_events.append({"label": label, **fields})
    owner_bases = (0x60000, 0x58000)
    owner_pixels = {0: bytes([0xA1]) * 128, 1: bytes([0xB2]) * 128}
    def fake_front_mapping(owner: int) -> dict[str, Any]:
        return {"front_owner_voff1_shadow": 0xC0 if owner == 0 else 0xB0,
            "front_owner_voff2_shadow": 0, "front_physical_base": owner_bases[owner]}
    offscreen_fake._front_mapping = fake_front_mapping
    offscreen_fake._front_rect = lambda owner, pointer, mapping: owner_pixels[owner]
    for owner in (0, 1):
        pointer = offscreen_row + (159 if owner == 0 else 158)
        width = visible_row_width_bytes(pointer)
        visible = {"entry_generation": offscreen_generation, "owner": owner,
            "pointer": pointer, "actual": bytes([owner + 0x31]) * 128,
            "background": owner_pixels[owner], "visible_width_bytes": width,
            "event_ordinal": 10 + owner, "actual_sha256": sha(bytes([owner + 0x31]) * 128),
            "saved_under_sha256": sha(owner_pixels[owner])}
        offscreen_fake.offscreen_owner_snapshots[(offscreen_generation, owner)] = visible
        offscreen_fake.current_entry["offscreen_retirement"]["last_visible_by_owner"][str(owner)] = {
            "entry_generation": offscreen_generation, "owner": owner, "pointer": pointer,
            "visible_width_bytes": width, "event_ordinal": 10 + owner,
            "actual_sha256": visible["actual_sha256"],
            "saved_under_sha256": visible["saved_under_sha256"]}
        owner_state = {"entry": 3, "death": 0, "player_fb": offscreen_row + 160,
            "front": owner, "valid_a": 0, "valid_b": 0,
            "meta_fb_a": pointer if owner == 0 else 0,
            "meta_fb_b": pointer if owner == 1 else 0}
        owner_stop = MonitorStop("fake-offscreen-retirement", 0xC000, 1,
            {"pc": 0xC000}, 20 + owner, 800.0 + owner)
        assert offscreen_fake._offscreen_owner_retirement(owner_stop, {}, owner_state)
    maze_gate_stop = MonitorStop("fake-first-maze", 0xC000, 2,
        {"pc": 0xC000}, 30, 900.0)
    offscreen_fake._guard_first_maze_entry(maze_gate_stop, {}, {"entry": 4})
    assert offscreen_fake.current_entry["offscreen_retirement"]["maze_entry_gate"]["pass"]
    assert offscreen_fake.errors == []
    json.dumps({"entries": [offscreen_fake.current_entry]}, allow_nan=False)
    tested += 1

    assert missing_visible_front_pose_failure(2, None)
    assert missing_visible_front_pose_failure(4, None)
    assert not missing_visible_front_pose_failure(3, None)
    tested += 3

    forced_entry_observer = object.__new__(LiveRuntimeObserver)
    forced_entry_observer.scenario = "front-first"
    forced_entry_observer.current_entry = {"index": 1, "pose_count": 0}
    forced_entry_observer.errors = []
    forced_entry_observer.input_events = []
    forced_entry_observer.pressed = set()
    forced_entry_observer.search = None
    forced_entry_observer.lifecycle = None
    forced_entry_observer.contact_count = 0
    forced_entry_observer._record = lambda *args, **kwargs: None
    forced_entry_observer._confirm_entry_state(
        MonitorStop("fixture-entry-state2", 0xC000, 1, {"pc": 0xC000}, 1, 1.0), {},
        {"entry": 2, "lives": 2, "frames": 1, "timer": 80,
         "player_fb": VISIBLE_BASE + 10 * 160 + 148})
    assert "held_input_challenge" not in forced_entry_observer.current_entry
    assert not forced_entry_observer.input_events
    tested += 1

    credit_client = FakeInputClient()
    credit_observer = object.__new__(LiveRuntimeObserver)
    credit_observer.client = credit_client
    credit_observer.credit_baseline = 0
    credit_observer.credit_call = None
    credit_observer.credit_evidence = None
    credit_observer.start_state = "coin-held"
    credit_observer.pressed = set()
    credit_observer.bindings = canonical_matrix
    credit_observer.search = None
    credit_observer.input_events = []
    credit_observer.cold_credited_start = False
    credit_observer._state = lambda: {"mode": MODE_ATTRACT, "credits": 0}
    credit_observer._record = lambda *args, **kwargs: None
    credit_stop = MonitorStop("credit-fake", 0x195F, 3, {"pc": 0x195F}, 1, 1.0)
    credit_observer._press(COIN5_DSCAN_KEY, "press", credit_stop,
                           "cold-credit-5", matrix_key=COIN5_MATRIX_KEY)
    credit_observer._start_inputs(credit_stop, {"mode": MODE_ATTRACT, "credits": 0})
    assert credit_observer.start_state == "coin-held" and [
        (call[1]["key"], call[1]["action"]) for call in credit_client.calls] == [(5, "press")]
    credit_observer._presentation_credit_add(credit_stop,
        {"source_staged_live_match": True})
    credit_observer._confirm_start_credit(
        MonitorStop("credit-confirm", 0xC000, 1, {"pc": 0xC000}, 2, 2.0),
        {"source_staged_live_match": True}, {"credits": 1})
    assert credit_observer.credit_evidence["after_add"] == 1
    credit_observer._start_inputs(
        MonitorStop("enter", 0xC000, 1, {"pc": 0xC000}, 3, 3.0),
        {"mode": MODE_ATTRACT, "credits": 1})
    assert credit_observer.start_state == "coin-released"
    credit_observer._start_inputs(
        MonitorStop("enter-press", 0xC000, 1, {"pc": 0xC000}, 4, 4.0),
        {"mode": MODE_ATTRACT, "credits": 1})
    assert credit_observer.start_state == "enter-held"
    credit_observer._start_inputs(
        MonitorStop("start", 0xC000, 1, {"pc": 0xC000}, 5, 5.0),
        {"mode": 0, "credits": 0})
    assert credit_observer.cold_credited_start
    assert credit_observer.credit_evidence["consumed_credit_count"] == 0
    assert [(x[1]["key"], x[1]["action"]) for x in credit_client.calls] == [
        (5, "press"), (5, "release"), (48, "press"), (48, "release")]
    assert all(method == "inject_key" for method, _ in credit_client.calls)
    tested += 1
    try:
        credit_observer._presentation_credit_add(
            MonitorStop("duplicate-credit", 0x195F, 3, {"pc": 0x195F}, 5, 5.0),
            {"source_staged_live_match": True})
    except GuardFailure:
        tested += 1
    else:
        raise AssertionError("cold-credit gate accepted a duplicate source call")

    for scenario in SCENARIOS:
        good = _good(scenario) if scenario != "natural" else {}
        if scenario == "natural":
            try:
                require_snapshot(scenario, good)
            except GuardFailure:
                tested += 1
                continue
            raise AssertionError("natural scenario unexpectedly received a write permit")
        assert require_snapshot(scenario, good) == TIMER_VALUES[scenario]
        tested += 1
        if scenario == "front-first":
            bad = dict(good, remaining_pad=0)
            try: require_snapshot(scenario, bad)
            except GuardFailure: tested += 1
            else: raise AssertionError("front-first accepted zero remaining pad")
            bad = dict(good); bad.pop("remaining_pad")
            try: require_snapshot(scenario, bad)
            except GuardFailure: tested += 1
            else: raise AssertionError("front-first accepted a missing remaining-pad observation")
        if scenario == "prior-music":
            bad = dict(good, lives=0)
            try: require_snapshot(scenario, bad)
            except GuardFailure: tested += 1
            else: raise AssertionError("prior-music accepted an empty reserve")
            bad = dict(good); bad.pop("lives")
            try: require_snapshot(scenario, bad)
            except GuardFailure: tested += 1
            else: raise AssertionError("prior-music accepted a missing reserve observation")
        if scenario in ("front-first", "music-first"):
            bad = dict(good, cue6_selected_audible_voice_count=0)
            try: require_snapshot(scenario, bad)
            except GuardFailure: tested += 1
            else: raise AssertionError("fixture accepted cue6 with no selected audible voice")
            bad = dict(good); bad.pop("cue6_selected_audible_voice_count")
            try: require_snapshot(scenario, bad)
            except GuardFailure: tested += 1
            else: raise AssertionError("fixture accepted a missing audible-voice observation")
        if scenario == "prior-music":
            bad = dict(good, cue13_selected_audible_voice_count=0)
            try: require_snapshot(scenario, bad)
            except GuardFailure: tested += 1
            else: raise AssertionError("prior-music accepted cue13 with no selected audible voice")
            bad = dict(good); bad.pop("cue13_selected_audible_voice_count")
            try: require_snapshot(scenario, bad)
            except GuardFailure: tested += 1
            else: raise AssertionError("prior-music accepted missing cue13 audible-voice evidence")
        for key in tuple(good):
            if key in ("remaining_pad", "lives", "cue6_selected_audible_voice_count",
                       "cue13_selected_audible_voice_count"):
                continue
            bad = dict(good)
            del bad[key]
            try:
                require_snapshot(scenario, bad)
            except GuardFailure:
                tested += 1
            else:
                raise AssertionError(f"{scenario}: missing guard {key} was accepted")
            bad = dict(good)
            bad[key] = False if good[key] is True else (good[key] + 1 if isinstance(good[key], int) and not isinstance(good[key], bool) else "wrong")
            try:
                require_snapshot(scenario, bad)
            except GuardFailure:
                tested += 1
            else:
                raise AssertionError(f"{scenario}: invalid guard {key} was accepted")
            if type(good[key]) is int:
                bad = dict(good, **{key: bool(good[key])})
                try:
                    require_snapshot(scenario, bad)
                except GuardFailure:
                    tested += 1
                else:
                    raise AssertionError(f"{scenario}: boolean value passed numeric guard {key}")

    class FakeClient:
        def __init__(self, pc: int = 0xC16E):
            self.calls: list[tuple[str, dict[str, Any] | None]] = []
            self.timeouts: list[float] = []
            self.pc = pc
            self.state = "halted"
        def call(self, method: str, params: dict[str, Any] | None = None,
                 timeout: float = 20.0):
            self.calls.append((method, params))
            self.timeouts.append(timeout)
            if method == "get_run_state": return {"state": self.state,
                "last_stop_reason": "breakpoint", "last_stop_pc": self.pc}
            if method == "read_registers": return {"pc": self.pc}
            if method == "read_memory": return {"data": "34", "space": "cpu"}
            return {}

    deadline_client = FakeClient()
    deadline_client._bug117_phase_deadline = time.monotonic() + 0.2
    monitor_call(deadline_client, "get_run_state")
    assert 0 < deadline_client.timeouts[-1] <= 0.2
    deadline_client._bug117_phase_deadline = time.monotonic() - 1
    deadline_call_count = len(deadline_client.calls)
    try: monitor_call(deadline_client, "get_run_state")
    except GuardFailure:
        assert len(deadline_client.calls) == deadline_call_count
        tested += 1
    else: raise AssertionError("monitor RPC started after its active phase deadline")

    for scenario in TIMER_VALUES:
        fake = FakeClient()
        gate = FixtureWriter(scenario, TIMER_ADDRESS)
        reads = []
        fresh = gate.write_from_paused_stop(fake, fake.pc,
            lambda client: reads.append(client) or _good(scenario))
        expected = TIMER_VALUES[scenario]
        assert fresh == {"scenario": scenario, "address": TIMER_ADDRESS,
            "value": expected, "fresh_snapshot": True, "attempts": 1}
        assert reads == [fake] and fake.calls[-3:] == [
            ("get_run_state", None), ("read_registers", None),
            ("write_memory", {"addr": TIMER_ADDRESS, "data": f"{expected:02x}"})]
        call_count = len(fake.calls)
        try:
            gate.write_from_paused_stop(fake, fake.pc, lambda _: _good(scenario))
        except GuardFailure:
            assert len(fake.calls) == call_count
            tested += 1
        else:
            raise AssertionError("writer allowed the approved timer write more than once")
        tested += 1

    blocked_client = FakeClient()
    blocked_writer = FixtureWriter("music-first", TIMER_ADDRESS)
    bad_snapshot = dict(_good("music-first"), player_x=319)
    try:
        blocked_writer.write_from_paused_stop(blocked_client, blocked_client.pc,
            lambda _: bad_snapshot)
    except GuardFailure:
        assert not blocked_client.calls
        tested += 1
    else:
        raise AssertionError("fresh-stop timer writer accepted drifted player position")

    moved_client = FakeClient()
    moved_writer = FixtureWriter("music-first", TIMER_ADDRESS)
    def move_during_guard_capture(client: FakeClient) -> dict[str, Any]:
        client.pc += 1
        return _good("music-first")
    try:
        moved_writer.write_from_paused_stop(moved_client, moved_client.pc,
            move_during_guard_capture)
    except GuardFailure:
        assert [method for method, _ in moved_client.calls] == ["get_run_state", "read_registers"]
        tested += 1
    else:
        raise AssertionError("writer accepted a changed PC after guard recapture")

    for marker_x in range(296, 320, 2):
        travel_bytes = (320 - marker_x) // 2
        row_start = VISIBLE_BASE + 20 * 160 + marker_x // 2
        assert framebuffer_row_x(row_start) == marker_x
        assert entry_row_x(row_start + travel_bytes, row_start, marker_x) == 320
        tested += 1

    packed_opaque_clip = bytes([0x55]) * 64
    native_opaque_clip = bug011_image_api().native_frame(packed_opaque_clip)
    clipped_actual = b"".join(native_opaque_clip[row * 8:row * 8 + 1] + b"\xFF" * 7
                               for row in range(16))
    clipped_compare = compare_opaque_player_pixels(
        native_opaque_clip, clipped_actual, packed_opaque_clip, 1)
    assert clipped_compare["visible_width_bytes"] == 1
    assert clipped_compare["opaque_pixels_compared"] == 32
    transparent_clip = compare_opaque_player_pixels(bytes(128), bytes([0xFF]) * 128,
                                                       bytes(64), 1)
    assert transparent_clip["opaque_pixels_compared"] == 0
    assert transparent_clip["visible_width_pixels"] == 2
    tested += 2

    class FrontReadClient:
        def __init__(self, voff1: int, voff2: int = 0):
            self.voff1, self.voff2 = voff1, voff2
            self.calls: list[tuple[str, dict[str, Any] | None]] = []
        def call(self, method: str, params: dict[str, Any] | None = None,
                 timeout: float = 20.0):
            self.calls.append((method, params))
            if method == "read_gime_state":
                return {"registers": {"FF9D": self.voff1, "FF9E": self.voff2}}
            if method == "read_memory" and params["space"] == "physical":
                return {"data": "a5" * params["length"], "space": "physical"}
            raise AssertionError(f"unexpected FRONT reader call {method} {params}")

    front_reader = object.__new__(LiveRuntimeObserver)
    front_pointer = VISIBLE_BASE + 20 * 160 + 159
    for owner, voff1, expected_base in ((0, 0xC0, 0x60000), (1, 0xB0, 0x58000)):
        front_client = FrontReadClient(voff1)
        front_reader.client = front_client
        mapping = front_reader._front_mapping(owner)
        clipped_rect = front_reader._front_rect(owner, front_pointer, mapping)
        assert mapping["front_physical_base"] == expected_base
        assert mapping["front_owner_voff2_shadow"] == 0
        assert len(clipped_rect) == 128
        assert all(clipped_rect[row * 8:row * 8 + 2] == b"\xA5\x00"
                   for row in range(16))
        assert [method for method, _ in front_client.calls].count("read_gime_state") == 1
        assert all(params is None or params.get("space") == "physical"
                   for method, params in front_client.calls if method == "read_memory")
        tested += 1
    wrong_voff2_client = FrontReadClient(0xB0, 0x08)
    front_reader.client = wrong_voff2_client
    try:
        front_reader._front_rect(1, front_pointer)
    except GuardFailure:
        assert [method for method, _ in wrong_voff2_client.calls] == ["read_gime_state"]
        tested += 1
    else:
        raise AssertionError("FRONT observer accepted a nonzero VOFF2 shadow")

    row_start = VISIBLE_BASE + 20 * 160 + 264 // 2
    mainloop_observer = object.__new__(LiveRuntimeObserver)
    mainloop_observer.current_entry = {"entry_start_fb": row_start, "marker_x": 264}
    mainloop_observer._state = lambda: {"entry": 3, "death": 0, "timer": 68,
        "lives": 0, "player_fb": row_start + 27, "cell_x": 0, "cell_y": 0,
        "step": 0, "pending": 0, "front": 0, "commit_seq": 0, "frames": 0,
        "mode": 0}
    mainloop_observer._record = lambda *args, **kwargs: None
    mainloop_observer._start_inputs = lambda *args: None
    mainloop_observer._confirm_start_credit = lambda *args: None
    mainloop_observer.cold_credited_start = True
    mainloop_observer.lifecycle = None
    mainloop_observer._previous_state = None
    mainloop_observer.release_snapshot = None
    mainloop_observer.search = None
    mainloop_observer.fixture = None
    mainloop_observer.errors = []
    mainloop_observer.entry_contact_violation = False
    mainloop_observer._mainloop(
        MonitorStop("row-derived-entry", 0xC16E, 1, {"pc": 0xC16E}, 1, 1.0), {})
    assert mainloop_observer.current_entry["offscreen_x_pixels"] == 318
    assert mainloop_observer.current_entry["offscreen_x320"] is False
    mainloop_observer._state = lambda: {"entry": 3, "death": 0, "timer": 68,
        "lives": 0, "player_fb": row_start + 28, "cell_x": 0, "cell_y": 0,
        "step": 0, "pending": 0, "front": 0, "commit_seq": 0, "frames": 0,
        "mode": 0}
    mainloop_observer._mainloop(
        MonitorStop("row-derived-entry", 0xC16E, 1, {"pc": 0xC16E}, 2, 2.0), {})
    assert mainloop_observer.current_entry["offscreen_x_pixels"] == 320
    assert mainloop_observer.current_entry["offscreen_x320"] is True
    tested += 1

    class PageClient:
        def __init__(self, page: int): self.page = page
        def call(self, method: str, params: dict[str, Any], timeout: float = 20.0):
            assert method == "read_memory" and params == {"addr": PAR5, "length": 1, "space": "cpu"}
            return {"data": f"{self.page:02x}", "space": "cpu"}
    assert fixture_audio_page(PageClient(0x34), 0xC16E, 0xC16E) == 0x3D
    tested += 1
    for client, stop_pc, mainloop_pc in (
            (PageClient(0x3D), 0xC16E, 0xC16E), (PageClient(0x34), 0xC16F, 0xC16E)):
        try: fixture_audio_page(client, stop_pc, mainloop_pc)
        except GuardFailure: tested += 1
        else: raise AssertionError("fixture audio read accepted a wrong mainloop mapping/PC")

    fixture_client = FakeClient()
    fixture_observer = object.__new__(LiveRuntimeObserver)
    fixture_observer.client = fixture_client
    fixture_observer.main = {"mainloop": fixture_client.pc, "DEATH_TIMER": TIMER_ADDRESS}
    fixture_observer.scenario = "prior-music"
    fixture_observer._qualify = lambda _: {"source_staged_live_match": True}
    fixture_state = {"pending": 0, "valid_a": 0, "valid_b": 0,
        "entry": 0, "death": 3, "timer": 37, "lives": 1,
        "credits": 0, "mode": 0, "player_fb": VISIBLE_BASE,
        "frames": 0}
    fixture_observer._state = lambda: fixture_state
    fixture_observer.audio = {}
    fixture_observer.cue_output = {6: False, 13: True}
    fixture_observer.contacts = [{"ordinal": 1}]
    fixture_observer.entry_contact_violation = False
    fixture_observer.latest_mix = {}
    fixture_observer.cue_start_ordinal = {}
    fixture_observer.current_entry = None
    fixture_observer.boundaries = {}
    fixture_observer.frames_at_cue6 = None
    fixture_observer.cue6_services = 0
    fixture_observer.dwell_checks = []
    saved_live_audio_snapshot = globals()["live_audio_snapshot"]
    fixture_audio_pages = []
    def fake_live_audio_snapshot(client: Any, symbols: dict[str, int], page: int) -> dict[str, Any]:
        fixture_audio_pages.append(page)
        return {"slots": [{"id": 0xFF, "policy": 0, "priority": 0}] * 4,
                "published_busy": 1, "best_slot": 0xFF, "best_priority": 0}
    globals()["live_audio_snapshot"] = fake_live_audio_snapshot
    fixture_observer._audio_snapshot = lambda: (_ for _ in ()).throw(
        AssertionError("mainloop fixture path used the audio-PC mapping reader"))
    try:
        mainloop_fixture = fixture_observer._fixture_snapshot(
            MonitorStop("fixture", fixture_client.pc, 1, {"pc": fixture_client.pc}, 1, 1.0), {})
    finally:
        globals()["live_audio_snapshot"] = saved_live_audio_snapshot
    assert fixture_audio_pages == [0x3D] and mainloop_fixture["live_stop_pc"] == fixture_client.pc
    tested += 1

    gate_client = FakeClient()
    gate_observer = object.__new__(LiveRuntimeObserver)
    gate_observer.client = gate_client
    gate_observer.scenario = "music-first"
    gate_observer.current_entry = {"entry_start_fb": row_start, "marker_x": 264}
    gate_observer.fixture = FixtureWriter("music-first", TIMER_ADDRESS)
    gate_observer.fixture_result = None
    gate_observer.write_count = 0
    gate_observer.errors = []
    gate_observer._record = lambda *args, **kwargs: None
    gate_observer._fixture_snapshot = lambda stop, qualification: {
        **_good("music-first"), "marker_x": gate_observer.current_entry["marker_x"],
        "lives": gate_state["lives"],
        "player_x": entry_row_x(gate_state["player_fb"], row_start, 264)}
    gate_stop = MonitorStop("third-life-fixture", gate_client.pc, 1,
                            {"pc": gate_client.pc}, 1, 1.0)
    gate_state = {"mode": 0, "entry": 3, "death": 0, "lives": 1,
                  "player_fb": row_start + 28, "timer": 60}
    gate_observer._maybe_write_fixture(gate_stop, gate_state, {})
    assert gate_observer.write_count == 0 and not gate_client.calls
    gate_state["lives"] = 0
    gate_observer._maybe_write_fixture(gate_stop, gate_state, {})
    assert gate_observer.write_count == 1 and gate_observer.fixture_result["value"] == 255
    assert [method for method, _ in gate_client.calls][-1] == "write_memory"
    tested += 1
    for scenario in SCENARIOS:
        state = acceptance_status({name: True for name in REQUIRED_PROOFS})
        assert state["pass"] is False and len(state["missing_proofs"]) == len(REQUIRED_PROOFS)
        tested += 1

    source = {"index": 0, "id": 6, "priority": 5, "policy": 0xB3,
              "periods": [0x02AD, 0x0456, 0x0789], "attenuation": [2, 15, 15],
              "noise": 0, "noise_attenuation": 15}
    slots = [source] + [{"index": i, "id": 0xFF, "priority": 0, "policy": 0,
                         "periods": [1] * 3, "attenuation": [15] * 3,
                         "noise": 0, "noise_attenuation": 15} for i in range(1, 4)]
    mix = model_exclusive_mix(slots, 6)
    assert mix["channel_sources"] == [{"channel": 0, "slot": 0, "voice": 0}]
    assert mix["period_bytes"][:2] == b"\xAD\x02"
    test_stores = expected_psg_transaction(mix["period_bytes"], mix["attenuation_bytes"],
        mix["noise_bytes"], b"\xFF" * 11, mix["channel_sources"])
    period = next(store for store in test_stores if store.kind == "period-data" and store.channel == 0)
    latch = next(store for store in test_stores if store.kind == "tone-latch" and store.channel == 0)
    assert (latch.value, period.value) == (0x8D, 0x2A)
    raw_slot = bytearray(28)
    raw_slot[0:3] = b"\x06\x05\xB3"
    raw_slot[6:8] = b"\xAD\x02"
    assert model_from_audio_slot(bytes(raw_slot), 0)["periods"][0] == 0x02AD
    tested += 1

    snapshot = {"mix_period_bytes": mix["period_bytes"],
                "mix_attenuation": mix["attenuation_bytes"], "mix_noise": mix["noise_bytes"],
                "mix_shadow": b"\x55" * 11}
    onset = PSGTransaction(mix, snapshot, require_audible=True)
    for store in onset.expected:
        onset.store(store.value)
    observed = onset.finish()
    assert observed["all_mix_stores_match"] and observed["audible_store_count"] >= 1
    unchanged_shadow = bytearray(11)
    for channel in range(3):
        lo, hi = mix["period_bytes"][channel * 2:channel * 2 + 2]
        unchanged_shadow[channel * 3 + 1] = ((hi << 4) | (lo >> 4)) & 0x3F
        unchanged_shadow[channel * 3 + 2] = 0x90 | (channel << 5) | mix["attenuation"][channel]
    unchanged_shadow[9] = mix["noise"][0] | 0xE0
    unchanged_shadow[10] = mix["noise"][1] | 0xF0
    wait_snapshot = {**snapshot, "mix_shadow": bytes(unchanged_shadow)}
    wait_only = PSGTransaction(mix, wait_snapshot)
    for store in wait_only.expected:
        wait_only.store(store.value)
    assert wait_only.finish()["audible_store_count"] == 0
    assert all(store.kind == "tone-latch" for store in wait_only.expected)
    tested += 2
    try:
        prove_audible_psg_source(mix, [s for s in onset.expected if s.kind == "tone-latch"])
    except GuardFailure:
        tested += 1
    else:
        raise AssertionError("muted-tone latch alone was accepted as cue audio")
    try:
        classify_post_store(0xA499, 0x90, 0x3D, b"\x97\xFF\x51", 0xA499)
    except GuardFailure:
        tested += 1
    else:
        raise AssertionError("non-STA opcode was accepted as a PSG store")
    assert classify_post_store(0xA499, 0x90, 0x3D, b"\xB7\xFF\x51", 0xA499)["value"] == 0x90
    assert post_busy_marker(bytes([0xBD, 0xA0, 0x00, 0xB7, 0x02, 0xD4]),
                            {"audio_mix_write_done": 0xA000, "audio_music_busy": 0xA000}) == 0xA006
    assert audio_bus_write_marker(b"\x00" * 0x499 + b"\xB7\xFF\x51",
                                  {"audio_write": 0xA499})["stop_pc"] == 0xA49C
    tested += 1
    tested += 2

    art = bytes([0x1B]) * 64
    rect = player_expected_rect(bytes([0x77]) * 128, art)
    assert compare_opaque_player_pixels(rect, rect, art)["opaque_pixels_compared"] > 0
    changed = bytearray(rect)
    changed[1] ^= 0x10
    try: compare_opaque_player_pixels(rect, bytes(changed), art)
    except GuardFailure: tested += 1
    else: raise AssertionError("opaque FRONT pixel mismatch was accepted")

    if ROOT:
        pinned = ROOT / "repro/bug122-parent/luna117-approved-fit-20261011/build"
        if pinned.is_dir():
            enemy_image = (pinned / "ladybug-enemy-runtime.rom").read_bytes()
            enemy_map = read_symbols(pinned / "ladybug-enemy-runtime.map")
            marker = irq_commit_marker(enemy_image, enemy_map)
            assert marker == {"pc": 0x0ED9, "end_pc": 0x0EDB, "encoding": "direct",
                              "required_dp": 0, "opcode_bytes": "0c93"}
            assert qualify_irq_commit_stop(marker, 0x0EDB, 0, b"\x0C\x93")["post_instruction"]
            try:
                qualify_irq_commit_stop(marker, 0x0EDB, 1, b"\x0C\x93")
            except GuardFailure:
                tested += 1
            else:
                raise AssertionError("direct IRQ INC accepted a nonzero DP")
            audio_map = read_symbols(pinned / "ladybug-audio-runtime.map")
            audio_image = (pinned / "ladybug-audio-runtime.bin").read_bytes()
            assert post_busy_marker(audio_image, audio_map) == 0xA498
            assert audio_bus_write_marker(audio_image, audio_map)["stop_pc"] == 0xA49C
            candidate_prep = prepare(pinned)
            required_hashes = {name: candidate_prep["files"][name]["sha256"]
                               for name in DELIVERY_HASH_FILES}
            receipt = {"schema": DELIVERY_RECEIPT_SCHEMA, "status": "parent-accepted",
                "artifact_sha256": required_hashes, "source_to_staged_bytes_match": True,
                "staged_sparse_copy_identity": True, "destination_live_bytes_match": True,
                "live_par_mapping_qualified": True}
            delivery = validate_delivery_receipt(receipt, candidate_prep)
            assert delivery["mapping_and_copy_qualified"]
            current_build = ROOT / "build"
            current_boot_prep = prepare(current_build)
            current_required_hashes = {name: current_boot_prep["files"][name]["sha256"]
                                       for name in DELIVERY_HASH_FILES}
            current_receipt = {"schema": DELIVERY_RECEIPT_SCHEMA, "status": "parent-accepted",
                "artifact_sha256": current_required_hashes, "source_to_staged_bytes_match": True,
                "staged_sparse_copy_identity": True, "destination_live_bytes_match": True,
                "live_par_mapping_qualified": True}
            current_delivery = validate_delivery_receipt(current_receipt, current_boot_prep)
            bootstrap = current_boot_prep["bootstrap_reset_qualification"]

            class FakeBootstrapClient:
                def __init__(self, *, corrupt_cpu=False, corrupt_physical=False,
                             corrupt_cpu_post=False, corrupt_physical_post=False,
                             wrong_page=False):
                    self.corrupt_cpu = corrupt_cpu
                    self.corrupt_physical = corrupt_physical
                    self.corrupt_cpu_post = corrupt_cpu_post
                    self.corrupt_physical_post = corrupt_physical_post
                    self.wrong_page = wrong_page
                    self.current: dict[str, Any] | None = None
                    self.write_count = 0
                def call(self, method: str, params: dict[str, Any] | None = None,
                         timeout: float = 20.0):
                    if method == "get_run_state":
                        return {"state": "halted", "last_stop_reason": "breakpoint",
                            "last_stop_pc": self.current["post_store_pc"],
                            "last_stop_bp_id": 0}
                    if method != "read_memory":
                        if method == "write_memory": self.write_count += 1
                        raise AssertionError(f"unexpected bootstrap fake RPC {method}")
                    address, length = params["addr"], params["length"]
                    space = params.get("space", "cpu")
                    if space == "cpu" and address == bootstrap["page_register"]:
                        page = bootstrap["expected_page"] ^ (1 if self.wrong_page else 0)
                        data = bytes((0x80 | page,))
                    elif (space == "cpu" and bootstrap["origin"] <= address and
                          address + length <= bootstrap["loader_end"]):
                        offset = address - bootstrap["origin"]
                        data = bytearray((current_build / "ladybug-gmc-boot.rom").read_bytes()[
                            offset:offset + length])
                        if data and (self.corrupt_cpu or
                                (self.corrupt_cpu_post and address == self.current["post_store_pc"])):
                            data[0] ^= 1
                        data = bytes(data)
                    elif space == "physical":
                        page = address // PHYSICAL_PAGE_BYTES
                        offset = address % PHYSICAL_PAGE_BYTES
                        data = bytearray((current_build / "ladybug-gmc-boot.rom").read_bytes()[
                            offset:offset + length] if page == bootstrap["expected_page"] else bytes(length))
                        if data and (self.corrupt_physical or
                                (self.corrupt_physical_post and
                                 offset == self.current["post_store_pc"] - bootstrap["origin"])):
                            data[0] ^= 1
                        data = bytes(data)
                    else:
                        raise AssertionError(f"unexpected bootstrap fake read {space} ${address:04X}")
                    return {"data": data.hex(), "space": space}

            bootstrap_observer = LiveRuntimeObserver(FakeBootstrapClient(), current_build,
                "natural", current_boot_prep, current_delivery)
            for expected_store in bootstrap["reset_stores"]:
                bootstrap_observer.client.current = expected_store
                bootstrap_observer._dispatch(MonitorStop("initial-entry",
                    expected_store["post_store_pc"], None,
                    {"pc": expected_store["post_store_pc"], "a": expected_store["value"]},
                    expected_store["sequence"] + 1, time.monotonic()))
            assert len(bootstrap_observer.bootstrap_reset_events) == len(bootstrap["reset_stores"])
            assert bootstrap_observer.events == [] and bootstrap_observer.write_count == 0
            assert all(event["source_staged_live_match"] is True
                       for event in bootstrap_observer.bootstrap_reset_events)
            assert all(event["get_run_state"]["last_stop_pc"] == event["post_store_pc"]
                       for event in bootstrap_observer.bootstrap_reset_events)
            assert all(event["live_cpu_at_post_pc_sha256"] ==
                       sha(bytes.fromhex(event["post_pc_span_hex"]))
                       for event in bootstrap_observer.bootstrap_reset_events)
            assert bootstrap_observer.bootstrap_reset_events[0]["live_cpu_at_post_pc_hex"] == "86bfb7"
            tested += 1

            def reject_bootstrap_fake(client: Any, store_index: int,
                                      *, value_delta: int = 0, wrong_order: bool = False,
                                      require_mapping_context: bool = False) -> dict[str, Any]:
                observer = LiveRuntimeObserver(client, current_build, "natural",
                    current_boot_prep, current_delivery)
                expected_store = bootstrap["reset_stores"][store_index]
                if wrong_order:
                    expected_store = bootstrap["reset_stores"][store_index + 1]
                client.current = expected_store
                try:
                    observer._dispatch(MonitorStop("initial-entry", expected_store["post_store_pc"],
                        None, {"pc": expected_store["post_store_pc"],
                               "a": expected_store["value"] ^ value_delta},
                        expected_store["sequence"] + 1, time.monotonic()))
                except GuardFailure:
                    assert observer.bootstrap_reset_events == [] and observer.events == []
                    assert observer.write_count == 0 and client.write_count == 0
                    assert observer.failure_context is not None
                    if require_mapping_context:
                        assert observer.failure_context["mapping"]["masked"] != bootstrap["expected_page"]
                    return observer.failure_context
                raise AssertionError("invalid bootstrap watchpoint event passed qualification")

            byte_context = reject_bootstrap_fake(FakeBootstrapClient(corrupt_physical=True), 0)
            assert byte_context["kind"] == "bootstrap-reset-store-qualification"
            assert byte_context["bytes"]["live_physical"]["hex"] != bootstrap["reset_stores"][0]["span_hex"]
            tested += 1
            cpu_context = reject_bootstrap_fake(FakeBootstrapClient(corrupt_cpu=True), 0)
            assert cpu_context["bytes"]["live_cpu"]["hex"] != bootstrap["reset_stores"][0]["span_hex"]
            tested += 1
            post_cpu_context = reject_bootstrap_fake(FakeBootstrapClient(corrupt_cpu_post=True), 0)
            assert post_cpu_context["bytes"]["live_cpu_at_post_pc"]["hex"] != bootstrap["reset_stores"][0]["post_pc_span_hex"]
            tested += 1
            post_physical_context = reject_bootstrap_fake(
                FakeBootstrapClient(corrupt_physical_post=True), 0)
            assert post_physical_context["bytes"]["live_physical_at_post_pc"]["hex"] != bootstrap["reset_stores"][0]["post_pc_span_hex"]
            tested += 1
            value_context = reject_bootstrap_fake(FakeBootstrapClient(), 0, value_delta=1)
            assert "value is invalid" in value_context["error"]
            tested += 1
            order_context = reject_bootstrap_fake(FakeBootstrapClient(), 0, wrong_order=True)
            assert order_context["kind"] == "bootstrap-reset-order-failure"
            tested += 1
            mapping_context = reject_bootstrap_fake(FakeBootstrapClient(wrong_page=True), 0,
                                                     require_mapping_context=True)
            assert "mapping differs" in mapping_context["error"]
            tested += 1
            unknown_observer = LiveRuntimeObserver(FakeBootstrapClient(), current_build,
                "natural", current_boot_prep, current_delivery)
            unknown_pc = bootstrap["origin"] + 0x2A
            unknown_observer.client.current = bootstrap["reset_stores"][0]
            try:
                unknown_observer._dispatch(MonitorStop("initial-entry", unknown_pc, None,
                    {"pc": unknown_pc, "a": 0}, 1, time.monotonic()))
            except GuardFailure:
                assert unknown_observer.failure_context["kind"] == "unknown-watchpoint-stop"
                assert unknown_observer.bootstrap_reset_events == [] and unknown_observer.events == []
                tested += 1
            else:
                raise AssertionError("unknown bootstrap watchpoint stop was accepted")

            class FakeMemoryClient:
                def __init__(self, corrupt=False): self.corrupt = corrupt
                def call(self, method, params, timeout=20.0):
                    assert method == "read_memory"
                    space, address = params.get("space", "cpu"), params["addr"]
                    length = params["length"]
                    if space == "cpu" and address == PAR5:
                        data = b"\x3D"
                    elif space == "physical":
                        offset = address - 0x3D * PHYSICAL_PAGE_BYTES
                        data = bytearray(audio_image[offset:offset + length])
                        if self.corrupt and data:
                            data[0] ^= 1
                        data = bytes(data)
                    else:
                        raise AssertionError("unexpected fake memory read")
                    return {"data": data.hex(), "space": space}
            bus_bytes = audio_image[audio_map["audio_write"] - 0xA000:
                                    audio_map["audio_write"] - 0xA000 + 3]
            span = qualify_live_span(FakeMemoryClient(), audio_map["audio_write"], bus_bytes,
                PAR5, 0x3D, 0xA000, 0xA000, audio_image, delivery)
            assert span["source_staged_live_match"]
            try:
                qualify_live_span(FakeMemoryClient(corrupt=True), audio_map["audio_write"], bus_bytes,
                    PAR5, 0x3D, 0xA000, 0xA000, audio_image, delivery)
            except GuardFailure:
                tested += 1
            else:
                raise AssertionError("mismatched live physical instruction bytes passed qualification")
            class FakeResidentMismatchClient:
                def __init__(self, pc: int, expected: bytes):
                    self.pc = pc
                    self.expected = expected
                    self._bug117_phase_deadline = time.monotonic() + PHASE_SECONDS
                def call(self, method: str, params: dict[str, Any] | None = None,
                         timeout: float = 20.0):
                    if method == "get_run_state":
                        return {"state": "halted", "last_stop_reason": "breakpoint",
                            "last_stop_pc": self.pc, "last_stop_bp_id": 17}
                    if method != "read_memory":
                        raise AssertionError(f"unexpected mismatch-context RPC {method}")
                    address = params["addr"]
                    length = params["length"]
                    space = params.get("space", "cpu")
                    if space == "cpu" and address == 0xFFA6:
                        data = b"\xBE"
                    elif space == "cpu" and address == self.pc:
                        data = self.expected[:length]
                    elif space == "physical":
                        assert address == 0x3E * PHYSICAL_PAGE_BYTES + self.pc - 0xC000
                        data = bytearray(self.expected[:length])
                        if data:
                            data[0] ^= 1
                        data = bytes(data)
                    else:
                        raise AssertionError(f"unexpected mismatch-context read {space} ${address:04X}")
                    return {"data": data.hex(), "space": space}
            mismatch_pc = read_symbols(pinned / "ladybug.map")["marker_entry_begin"]
            mismatch_expected = (pinned / "ladybug-runtime.rom").read_bytes()[
                mismatch_pc - 0xC000:mismatch_pc - 0xC000 + 3]
            mismatch_client = FakeResidentMismatchClient(mismatch_pc, mismatch_expected)
            mismatch_observer = LiveRuntimeObserver(mismatch_client, pinned, "natural",
                                                     candidate_prep, delivery)
            # This focused mismatch probe starts at a resident stop; bootstrap coverage is
            # exercised end-to-end above with current-receipt bootstrap bytes.
            mismatch_observer.bootstrap_reset_index = len(
                mismatch_observer.bootstrap_reset["reset_stores"])
            mismatch_observer.labels[mismatch_pc] = "marker_entry_begin"
            mismatch_observer.bp_ids[mismatch_pc] = 17
            mismatch_stop = MonitorStop("initial-entry", mismatch_pc, 17,
                {"pc": mismatch_pc, "dp": 0, "a": 0}, 23, time.monotonic())
            try:
                mismatch_observer._dispatch(mismatch_stop)
            except GuardFailure:
                context = mismatch_observer.failure_context
                assert context is not None and mismatch_observer.events == []
                assert mismatch_observer.write_count == 0
                assert json.loads(json.dumps(context)) == context
                assert context["kind"] == "live-physical-byte-mismatch"
                assert context["stop"]["phase"] == "initial-entry"
                assert context["stop"]["pc"] == mismatch_pc
                assert context["stop"]["bp_id"] == 17 and context["stop"]["ordinal"] == 23
                assert context["stop"]["phase_deadline_seconds"] == PHASE_SECONDS
                assert context["mapping"]["par_raw"] == 0xBE
                assert context["mapping"]["par_masked"] == 0x3E
                assert context["span"]["cpu_window"] == 0xC000
                assert context["span"]["physical_page"] == 0x3E
                assert context["span"]["physical_address"] == (
                    0x3E * PHYSICAL_PAGE_BYTES + mismatch_pc - 0xC000)
                assert context["bytes"]["caller_expected"]["hex"] == mismatch_expected.hex()
                assert context["bytes"]["candidate_staged"]["hex"] == mismatch_expected.hex()
                assert context["bytes"]["live_cpu_window"]["hex"] == mismatch_expected.hex()
                assert context["bytes"]["live_physical"]["hex"] != mismatch_expected.hex()
                assert context["stopped_status"]["state"] == "halted"
                assert context["stopped_status"]["last_stop_pc"] == mismatch_pc
                assert context["error"] == (
                    "QualificationFailure: live physical module bytes differ from staged candidate bytes")
                tested += 1
            else:
                raise AssertionError("resident physical mismatch passed or failed to retain context")
            try:
                validate_delivery_receipt({**receipt, "status": "unaccepted"}, candidate_prep)
            except GuardFailure:
                tested += 1
            else:
                raise AssertionError("unaccepted GDB delivery receipt passed the gate")
            wrong_hashes = dict(required_hashes, **{"ladybug.rom": "0" * 64})
            try:
                validate_delivery_receipt({**receipt, "artifact_sha256": wrong_hashes}, candidate_prep)
            except GuardFailure:
                tested += 1
            else:
                raise AssertionError("mismatched GDB delivery ROM hash passed the gate")
            for field in ("source_to_staged_bytes_match", "staged_sparse_copy_identity",
                          "destination_live_bytes_match", "live_par_mapping_qualified"):
                try:
                    validate_delivery_receipt({**receipt, field: False}, candidate_prep)
                except GuardFailure:
                    tested += 1
                else:
                    raise AssertionError(f"GDB delivery gate accepted missing qualification {field}")
            try:
                require_adaptive_keyboard_profile(pinned)
            except GuardFailure:
                tested += 1
            else:
                raise AssertionError("nonadaptive accepted-fit profile passed the live profile gate")
            tested += 1

    quiet_snapshot = {"slots": [{"id": 0xFF} for _ in range(4)], "music_count": 0,
        "music_queue": bytes(8), "effect_queue_count": 0, "credit_pending": 0,
        "mix_count": 0, "mix_period_bytes": b"\x01\x00" * 3,
        "mix_attenuation": b"\x0F" * 3, "mix_noise": b"\x00\x0F"}
    quiet_model = model_quiet_mix(b"\x55" * 11)
    assert quiet_model["period_bytes"] == b"\x01\x00" * 3
    quiet_transaction = PSGTransaction(quiet_model, {"mix_period_bytes": quiet_model["period_bytes"],
        "mix_attenuation": quiet_model["attenuation_bytes"], "mix_noise": quiet_model["noise_bytes"],
        "mix_shadow": b"\x55" * 11})
    for store in quiet_transaction.expected:
        quiet_transaction.store(store.value)
    assert quiet_transaction.finish()["actual_mute_attenuation_stores"] == 3
    assert validate_quiet_terminal(quiet_snapshot)["all_slots_clear"]
    try:
        validate_quiet_terminal({**quiet_snapshot, "slots": [{"id": 6}] + [{"id": 0xFF}] * 3})
    except GuardFailure:
        tested += 1
    else:
        raise AssertionError("terminal pure-mute proof accepted a competing active slot")
    tested += 1
    retired_tail_snapshot = {**quiet_snapshot,
        "music_queue": bytes.fromhex("0600000000000000")}
    retired_tail_result = validate_quiet_terminal(retired_tail_snapshot)
    assert retired_tail_result["all_queues_idle"] is True
    assert retired_tail_result["music_queue_active_count"] == 0
    assert retired_tail_result["music_queue_capacity"] == 8
    assert retired_tail_result["inactive_music_queue_tail_hex"] == "0600000000000000"
    tested += 1
    for invalid_snapshot, description in (
            ({**retired_tail_snapshot, "music_count": 1}, "active music occupancy"),
            ({**retired_tail_snapshot, "music_queue": b"\x06"}, "short queue storage"),
            ({**retired_tail_snapshot, "music_queue": "0600000000000000"}, "non-byte queue storage"),
            ({**retired_tail_snapshot, "music_count": 9}, "count beyond queue capacity"),
            ({**retired_tail_snapshot, "music_count": False}, "boolean music count"),
            ({**retired_tail_snapshot, "effect_queue_count": 1}, "active effect occupancy")):
        try:
            validate_quiet_terminal(invalid_snapshot)
        except GuardFailure:
            tested += 1
        else:
            raise AssertionError(f"terminal occupancy guard accepted {description}")

    class FakeTerminalContextClient:
        def __init__(self, pc: int):
            self.pc = pc
            self.calls: list[tuple[str, dict[str, Any] | None]] = []
        def call(self, method: str, params: dict[str, Any] | None = None,
                 timeout: float = 20.0):
            self.calls.append((method, params))
            if method != "get_run_state":
                raise AssertionError(f"terminal failure retention made unexpected RPC {method}")
            return {"state": "halted", "last_stop_reason": "breakpoint",
                "last_stop_pc": self.pc, "last_stop_bp_id": 71}

    terminal_pc = 0xA432
    terminal_client = FakeTerminalContextClient(terminal_pc)
    terminal_observer = object.__new__(LiveRuntimeObserver)
    terminal_observer.client = terminal_client
    terminal_observer.labels = {terminal_pc: "audio_mix_write"}
    terminal_observer.bp_ids = {}
    terminal_observer.bus_marker = {"stop_pc": terminal_pc + 1}
    terminal_observer.active_tx = None
    terminal_observer.cue_terminal = {6: {"cue_id": 6, "start_ordinal": 50,
        "entry": 2, "ordinal": 90}}
    terminal_observer.cue_start_ordinal = {6: 50}
    terminal_observer.cue_entry_owner = {6: 2}
    terminal_observer.cue_stream_active = {6: False, 13: False}
    terminal_observer.pending_terminal_cues = {6}
    terminal_observer.quiet_tail = {}
    terminal_observer.quiet_first_proofs = []
    terminal_observer.quiet_refresh_records = []
    terminal_observer.failure_context = None
    terminal_observer.current_stop_context = None
    terminal_observer.events = []
    terminal_slots = [{"index": i, "id": 0xFF, "priority": 0,
        "periods": [1, 1, 1], "attenuation": [15, 15, 15],
        "shadow": bytes([0xA0 + i]) * 11} for i in range(4)]
    terminal_bad_snapshot = {"slots": terminal_slots, "music_count": 1,
        "music_queue": bytes.fromhex("0102030405060708"), "effect_queue_count": 2,
        "credit_pending": 3, "mix_count": 4, "published_busy": 1,
        "mix_period_bytes": bytes.fromhex("34127856bc9a"),
        "mix_attenuation": bytes.fromhex("010203"),
        "mix_noise": bytes.fromhex("0405"),
        "mix_shadow": bytes(range(11)), "mix_order": bytes.fromhex("01020304"),
        "best_slot": 2, "best_priority": 6}
    terminal_observer._qualify = lambda stop: {
        "source_staged_live_match": True, "module": "audio",
        "instruction_bytes": bytes.fromhex("b7ff51")}
    terminal_observer._audio_snapshot = lambda: terminal_bad_snapshot
    terminal_stop = MonitorStop("audio-terminal", terminal_pc, 71,
        {"pc": terminal_pc, "a": 6}, 91, time.monotonic())
    try:
        terminal_observer._dispatch(terminal_stop)
    except GuardFailure as exc:
        assert "queued music, effects, credits, or mixer work" in str(exc)
    else:
        raise AssertionError("terminal guard accepted queued work while retaining failure context")
    terminal_context = terminal_observer.failure_context
    assert terminal_context is not None
    assert terminal_context["kind"] == "terminal-audio-guard-failure"
    assert terminal_context["stop"]["phase"] == "audio-terminal"
    assert terminal_context["stop"]["pc"] == terminal_pc
    assert terminal_context["stop"]["bp_id"] == 71
    assert terminal_context["stop"]["ordinal"] == 91
    assert terminal_context["stop"]["phase_deadline_seconds"] == PHASE_SECONDS
    assert terminal_context["stopped_status"]["state"] == "halted"
    assert terminal_context["stopped_status"]["last_stop_pc"] == terminal_pc
    assert terminal_context["audio_snapshot"]["counts"] == {
        "music_count": 1, "effect_queue_count": 2, "credit_pending": 3,
        "mix_count": 4, "published_busy": 1}
    assert terminal_context["audio_snapshot"]["music_queue"] == {
        "hex": "0102030405060708", "length": 8}
    assert terminal_context["audio_snapshot"]["mixer"]["periods"]["hex"] == "34127856bc9a"
    assert terminal_context["audio_snapshot"]["mixer"]["attenuation"]["hex"] == "010203"
    assert terminal_context["audio_snapshot"]["mixer"]["noise"]["hex"] == "0405"
    assert terminal_context["audio_snapshot"]["mixer"]["shadow"]["hex"] == bytes(range(11)).hex()
    assert terminal_context["audio_snapshot"]["slots"][3]["shadow"] == {
        "hex": (bytes([0xA3]) * 11).hex(), "length": 11}
    assert [method for method, _ in terminal_client.calls] == ["get_run_state"]
    assert terminal_observer.events == []
    assert json.loads(json.dumps(terminal_context)) == terminal_context
    tested += 1

    class FakeQuietClient:
        def __init__(self):
            self.busy = 0
            self.calls: list[str] = []
        def call(self, method: str, params: dict[str, Any] | None = None,
                 timeout: float = 20.0):
            self.calls.append(method)
            if method == "read_memory":
                assert params == {"addr": 0x02D4, "length": 1, "space": "cpu"}
                return {"data": f"{self.busy:02x}", "space": "cpu"}
            if method == "get_run_state":
                return {"state": "halted", "last_stop_reason": "breakpoint"}
            raise AssertionError(f"quiet terminal fake received unexpected RPC {method}")

    quiet_final_shadow = bytes.fromhex("81009fa100bfc100dfe0ff")
    quiet_initial_shadow = bytes.fromhex("810100a10100c10100e0ff")

    def quiet_snapshot(shadow: bytes, *, effect_count: int = 0,
                       active_slot: bool = False) -> dict[str, Any]:
        slots = [{"index": i, "id": 0xFF, "priority": 0} for i in range(4)]
        if active_slot:
            slots[2]["id"] = 3
        return {"slots": slots, "music_count": 0,
            "music_queue": bytes(8), "effect_queue_count": effect_count,
            "credit_pending": 0, "mix_count": 0, "published_busy": 1,
            "mix_period_bytes": b"\x01\x00" * 3,
            "mix_attenuation": b"\x0F" * 3, "mix_noise": b"\x00\x0F",
            "mix_shadow": shadow, "mix_order": bytes(4),
            "best_slot": 0xFF, "best_priority": 0}

    def make_quiet_observer(*, entry: int = 17, shadow: bytes = bytes(11),
                            effect_count: int = 0, active_slot: bool = False
                            ) -> tuple[LiveRuntimeObserver, dict[str, Any]]:
        observer = object.__new__(LiveRuntimeObserver)
        observer.client = FakeQuietClient()
        observer.audio = {"AUDIO_MUSIC_PUBLISHED_BUSY": 0x02D4, "audio_slot0": 0x2200}
        observer.boundaries = {"cue6": {"stream_start": 0xA100,
            "terminator_address": 0xA106, "terminal_x_expected": 0xA107}}
        observer.audio_image = bytearray(0x2000)
        observer.audio_image[0xA106 - 0xA000] = 0
        observer.events = []
        observer.errors = []
        observer.current_stop_context = None
        observer.failure_context = None
        observer.active_tx = None
        observer.cue_output = {6: False, 13: False}
        observer.cue_stream_active = {6: True, 13: False}
        observer.cue_entry_owner = {6: entry}
        observer.cue_start_ordinal = {6: 100}
        observer.cue_terminal = {}
        observer.quiet_tail = {}
        observer.pending_terminal_cues = set()
        observer.quiet_first_proofs = []
        observer.quiet_refresh_records = []
        observer.latest_mix = {}
        observer.proofs = {}
        observer.lifecycle = None
        observer.lifecycle_cue13_output = False
        observer.current_entry = {"index": entry, "released": False}
        observer.scenario = "fixture"
        observer.contact_count = 0
        snapshot = quiet_snapshot(shadow, effect_count=effect_count, active_slot=active_slot)
        end_snapshot = quiet_snapshot(shadow)
        end_snapshot["slots"][0]["id"] = 6
        observer._audio_snapshot = lambda: end_snapshot
        end_stop = MonitorStop("fake-cue-end", 0xA400, 1,
            {"pc": 0xA400, "y": 0x2200, "x": 0xA107}, 105, 100.0)
        observer._audio_end(end_stop, {"source_staged_live_match": True})
        observer._audio_snapshot = lambda: snapshot
        return observer, snapshot

    def service_quiet(observer: LiveRuntimeObserver, snapshot: dict[str, Any],
                      start_ordinal: int, busy_ordinal: int, *,
                      target_shadow: bytes | None = None,
                      audible_override: bool = False) -> list[PSGStore]:
        start_stop = MonitorStop("fake-quiet-service", 0xA430, 2,
            {"pc": 0xA430}, start_ordinal, 100.0 + start_ordinal)
        observer._audio_start(start_stop, {"source_staged_live_match": True})
        tx = observer.active_tx
        assert tx is not None and tx["quiet"] is True
        expected = list(tx["transaction"].expected)
        for offset, store in enumerate(expected, 1):
            observer._psg_store(MonitorStop("fake-quiet-service", 0xA432, 3,
                {"pc": 0xA432}, start_ordinal + offset, 100.0 + start_ordinal + offset),
                {"source_staged_live_match": True, "value": store.value})
        if target_shadow is not None:
            snapshot["mix_shadow"] = target_shadow
        if audible_override:
            tx["transaction"].finish = lambda: {
                "actual_store_count": len(expected), "modeled_store_count": len(expected),
                "audible_store_count": 1, "audible_channels": [0],
                "actual_mute_attenuation_stores": sum(
                    store.kind == "attenuation" and (store.value & 15) == 15 for store in expected),
                "all_mix_stores_match": True}
        observer._busy_publication(MonitorStop("fake-quiet-service", 0xA438, 4,
            {"pc": 0xA438}, busy_ordinal, 100.0 + busy_ordinal),
            {"source_staged_live_match": True})
        return expected

    quiet_observer, quiet_state = make_quiet_observer(shadow=quiet_initial_shadow)
    first_stores = service_quiet(quiet_observer, quiet_state, 120, 140,
                                 target_shadow=quiet_final_shadow)
    assert len(first_stores) == 9
    assert sum(store.kind == "attenuation" and (store.value & 15) == 15
               for store in first_stores) == 3
    assert quiet_observer.quiet_tail[6]["proof_kind"] == "first-terminal-mute-and-busy-zero"
    first_proof = quiet_observer.quiet_tail[6]
    assert first_proof["stream_identity"] == {"cue_id": 6, "start_ordinal": 100,
        "entry": 17, "end_ordinal": 105}
    assert first_proof["actual_mute_attenuation_stores"] >= 1
    assert first_proof["busy_zero_ordinal"] == 140
    assert quiet_observer.pending_terminal_cues == {6}
    refresh_stores = service_quiet(quiet_observer, quiet_state, 150, 160)
    assert [store.kind for store in refresh_stores] == ["tone-latch"] * 3
    assert len(refresh_stores) == 3
    assert first_proof["actual_mute_attenuation_stores"] >= 1
    assert quiet_observer.quiet_tail[6] is first_proof
    assert len(quiet_observer.quiet_first_proofs) == 1
    assert quiet_observer.quiet_refresh_records[0]["proof_kind"] == "same-generation-shadow-refresh"
    assert quiet_observer.quiet_refresh_records[0]["actual_mute_attenuation_stores"] == 0
    assert quiet_observer.quiet_refresh_records[0]["busy_zero_ordinal"] == 160
    json.dumps({"quiet_tail": quiet_observer.quiet_tail,
        "first": quiet_observer.quiet_first_proofs,
        "refreshes": quiet_observer.quiet_refresh_records}, allow_nan=False)
    tested += 1

    no_first_mute, no_first_mute_state = make_quiet_observer(shadow=quiet_final_shadow)
    no_first_mute._audio_start(MonitorStop("fake-first-no-mute", 0xA430, 2,
        {"pc": 0xA430}, 120, 120.0), {"source_staged_live_match": True})
    no_mute_tx = no_first_mute.active_tx
    assert no_mute_tx is not None
    for offset, store in enumerate(no_mute_tx["transaction"].expected, 1):
        no_first_mute._psg_store(MonitorStop("fake-first-no-mute", 0xA432, 3,
            {"pc": 0xA432}, 120 + offset, 120.0 + offset),
            {"source_staged_live_match": True, "value": store.value})
    try:
        no_first_mute._busy_publication(MonitorStop("fake-first-no-mute", 0xA438, 4,
            {"pc": 0xA438}, 140, 140.0), {"source_staged_live_match": True})
    except GuardFailure as exc:
        assert "lacks an actual mute attenuation store" in str(exc)
        tested += 1
    else:
        raise AssertionError("first terminal quiet service passed without an actual mute store")

    def expect_refresh_start_failure(observer: LiveRuntimeObserver,
                                     expected_text: str) -> None:
        try:
            observer._audio_start(MonitorStop("fake-invalid-refresh", 0xA430, 2,
                {"pc": 0xA430}, 150, 150.0), {"source_staged_live_match": True})
        except GuardFailure as exc:
            assert expected_text in str(exc)
        else:
            raise AssertionError(f"invalid quiet refresh passed: {expected_text}")

    missing_busy, missing_busy_state = make_quiet_observer()
    service_quiet(missing_busy, missing_busy_state, 120, 140,
                  target_shadow=quiet_final_shadow)
    missing_busy.quiet_tail[6]["busy_zero_ordinal"] = None
    expect_refresh_start_failure(missing_busy, "earlier same-generation mute and busy-zero proof")
    tested += 1

    wrong_generation, wrong_generation_state = make_quiet_observer()
    service_quiet(wrong_generation, wrong_generation_state, 120, 140,
                  target_shadow=quiet_final_shadow)
    wrong_generation.cue_start_ordinal[6] = 101
    expect_refresh_start_failure(wrong_generation, "does not match its emitted cue generation")
    tested += 1

    wrong_entry, wrong_entry_state = make_quiet_observer()
    service_quiet(wrong_entry, wrong_entry_state, 120, 140,
                  target_shadow=quiet_final_shadow)
    wrong_entry.cue_entry_owner[6] = 18
    expect_refresh_start_failure(wrong_entry, "does not match its emitted cue generation")
    tested += 1

    occupied, occupied_state = make_quiet_observer(effect_count=1)
    try:
        occupied._audio_start(MonitorStop("fake-occupied-terminal", 0xA430, 2,
            {"pc": 0xA430}, 120, 120.0), {"source_staged_live_match": True})
    except GuardFailure as exc:
        assert "queued music, effects, credits, or mixer work" in str(exc)
        tested += 1
    else:
        raise AssertionError("terminal quiet service accepted an active effect queue")

    active_slot, active_slot_state = make_quiet_observer(active_slot=True)
    try:
        active_slot._audio_start(MonitorStop("fake-active-slot-terminal", 0xA430, 2,
            {"pc": 0xA430}, 120, 120.0), {"source_staged_live_match": True})
    except GuardFailure as exc:
        assert "active or competing audio slot" in str(exc)
        tested += 1
    else:
        raise AssertionError("terminal quiet service accepted an active audio slot")

    mismatch, mismatch_state = make_quiet_observer()
    service_quiet(mismatch, mismatch_state, 120, 140,
                  target_shadow=quiet_final_shadow)
    mismatch._audio_start(MonitorStop("fake-mismatched-refresh", 0xA430, 2,
        {"pc": 0xA430}, 150, 150.0), {"source_staged_live_match": True})
    mismatch_store = mismatch.active_tx["transaction"].expected[0]
    try:
        mismatch._psg_store(MonitorStop("fake-mismatched-refresh", 0xA432, 3,
            {"pc": 0xA432}, 151, 151.0),
            {"source_staged_live_match": True, "value": mismatch_store.value ^ 1})
    except GuardFailure as exc:
        assert "differs from modeled" in str(exc)
        tested += 1
    else:
        raise AssertionError("quiet refresh accepted an actual PSG store that differs from its model")

    audible, audible_state = make_quiet_observer()
    service_quiet(audible, audible_state, 120, 140,
                  target_shadow=quiet_final_shadow)
    try:
        service_quiet(audible, audible_state, 150, 160, audible_override=True)
    except GuardFailure as exc:
        assert "contains audible PSG stores" in str(exc)
        tested += 1
    else:
        raise AssertionError("same-generation quiet refresh accepted an audible PSG transaction")

    busy_one, busy_one_state = make_quiet_observer()
    busy_one.client.busy = 1
    try:
        service_quiet(busy_one, busy_one_state, 120, 140,
                      target_shadow=quiet_final_shadow)
    except GuardFailure as exc:
        assert "did not publish busy zero" in str(exc)
        assert 6 not in busy_one.quiet_tail
        tested += 1
    else:
        raise AssertionError("first terminal quiet service passed with busy one")

    busy_refresh, busy_refresh_state = make_quiet_observer()
    service_quiet(busy_refresh, busy_refresh_state, 120, 140,
                  target_shadow=quiet_final_shadow)
    busy_refresh.client.busy = 1
    try:
        service_quiet(busy_refresh, busy_refresh_state, 150, 160)
    except GuardFailure as exc:
        assert "did not publish busy zero" in str(exc)
        assert len(busy_refresh.quiet_refresh_records) == 0
        assert busy_refresh.quiet_tail[6]["busy_zero_ordinal"] == 140
        tested += 1
    else:
        raise AssertionError("quiet refresh passed with busy one or replaced the first proof")

    active_mix_snapshot = quiet_snapshot(quiet_final_shadow)
    active_mix_snapshot["slots"][0].update({"id": 6, "policy": 0xB3,
        "priority": 5, "wait": 0, "stream_pointer": 0xA100,
        "periods": [1, 1, 1], "attenuation": [0, 0, 0],
        "noise": 0, "noise_attenuation": 15})
    active_mix_snapshot["best_slot"] = 0
    active_mix_snapshot["best_priority"] = 5
    active_mix_snapshot["mix_period_bytes"] = b"\x01\x00" * 3
    active_mix_snapshot["mix_attenuation"] = b"\x0F" * 3
    active_mix_snapshot["mix_noise"] = b"\x00\x0F"

    blocked_new_generation, _ = make_quiet_observer()
    blocked_new_generation._audio_snapshot = lambda: active_mix_snapshot
    blocked_new_generation._state = lambda: {"frames": 1, "entry": 0}
    blocked_new_generation.cue6_services = 0
    blocked_new_generation.frames_at_cue6 = None
    prior_verify_live_music_mix = globals()["verify_live_music_mix"]
    globals()["verify_live_music_mix"] = lambda snapshot, cue, policy, priority: {
        "audible_voice_count": 1, "channel_sources": []}
    try:
        try:
            blocked_new_generation._audio_start(MonitorStop("fake-next-cue-before-release",
                0xA430, 2, {"pc": 0xA430}, 200, 200.0),
                {"source_staged_live_match": True})
        except GuardFailure as exc:
            assert "before its pending terminal handoff closed" in str(exc)
            tested += 1
        else:
            raise AssertionError("new cue6 generation began before terminal release")

        released_new_generation, released_state = make_quiet_observer()
        service_quiet(released_new_generation, released_state, 120, 140,
                      target_shadow=quiet_final_shadow)
        released_new_generation.pending_terminal_cues.discard(6)
        released_new_generation.current_entry = None
        released_new_generation._audio_snapshot = lambda: active_mix_snapshot
        released_new_generation._state = lambda: {"frames": 2, "entry": 0}
        released_new_generation.cue6_services = 0
        released_new_generation.frames_at_cue6 = None
        released_new_generation._audio_start(MonitorStop("fake-next-cue-after-release",
            0xA430, 2, {"pc": 0xA430}, 200, 200.0),
            {"source_staged_live_match": True})
        assert released_new_generation.cue_stream_active[6] is True
        assert released_new_generation.cue_start_ordinal[6] == 200
        assert released_new_generation.cue_entry_owner[6] is None
        assert 6 not in released_new_generation.cue_terminal
        assert 6 not in released_new_generation.quiet_tail
        assert len(released_new_generation.quiet_first_proofs) == 1
        tested += 1
    finally:
        globals()["verify_live_music_mix"] = prior_verify_live_music_mix

    def make_replacement_seed_observer(*, include_cue13_idle: bool
                                       ) -> LiveRuntimeObserver:
        lifecycle = LifecycleOrder()
        lifecycle.record("death_state_1", {"death_state": 1,
            "genuine_contact_live_bytes": True, "event_ordinal": 10})
        lifecycle.record("death_state_2", {"death_state": 2,
            "genuine_contact_live_bytes": True, "event_ordinal": 15})
        lifecycle.record("death_blank_timer37", {
            "death_state": 3, "death_timer": 37, "entry_state": 0,
            "source_bytes_match": True, "death_blank_front_commit_observed": True,
            "death_blank_pixels_match_oracle": True, "death_blank_irq_commit_observed": True,
            "death_blank_live_code_span_qualified": True,
            "death_blank_front_mapping_qualified": True,
            "death_blank_opaque_pixels_compared": 72, "event_ordinal": 20})
        if include_cue13_idle:
            lifecycle.record("cue13_published_idle", {"cue13_actual_output": True,
                "published_busy": 0, "normal_drain": True,
                "cue13_emitted_end_observed": True,
                "actual_terminal_mute_observed": True, "event_ordinal": 25})
        observer = object.__new__(LiveRuntimeObserver)
        observer.current_entry = {"index": 2, "seed_verified": False}
        observer.pressed = set()
        observer.search = None
        observer.scenario = "front-first"
        observer.contact_count = 1
        observer.contacts = [{"lives": 3}]
        observer.lifecycle = lifecycle
        observer.pending_terminal_cues = {13}
        observer.errors = []
        observer._record = lambda *args, **kwargs: None
        return observer

    replacement_join, replacement_state = make_replacement_seed_observer(
        include_cue13_idle=True), {"entry": 2, "lives": 2, "frames": 30,
            "timer": 80, "player_fb": VISIBLE_BASE + 10 * 160 + 132}
    replacement_join._confirm_entry_state(MonitorStop("fake-replacement-seed",
        0xC000, 1, {"pc": 0xC000}, 30, 30.0), {}, replacement_state)
    assert 13 not in replacement_join.pending_terminal_cues
    assert replacement_join.lifecycle.records[-1]["name"] == "replacement_entry_seed"
    assert replacement_join.lifecycle.records[-1]["prior_cue13_idle_observed"] is True
    tested += 1

    missing_replacement_join, missing_replacement_state = make_replacement_seed_observer(
        include_cue13_idle=False), {"entry": 2, "lives": 2, "frames": 30,
            "timer": 80, "player_fb": VISIBLE_BASE + 10 * 160 + 132}
    try:
        missing_replacement_join._confirm_entry_state(MonitorStop("fake-replacement-seed-missing-idle",
            0xC000, 1, {"pc": 0xC000}, 30, 30.0), {}, missing_replacement_state)
    except GuardFailure as exc:
        assert "dependency" in str(exc) or "prior_cue13_idle_observed" in str(exc)
        assert missing_replacement_join.pending_terminal_cues == {13}
        tested += 1
    else:
        raise AssertionError("cue13 candidate retired without a validated replacement lifecycle join")

    death_blank = {"death_state": 3, "death_timer": 37, "entry_state": 0,
                   "source_bytes_match": True, "death_blank_front_commit_observed": True,
                   "death_blank_pixels_match_oracle": True, "death_blank_irq_commit_observed": True,
                   "death_blank_live_code_span_qualified": True,
                   "death_blank_front_mapping_qualified": True,
                   "death_blank_opaque_pixels_compared": 72}
    death_events = {
        "death_state_1": {"death_state": 1, "genuine_contact_live_bytes": True, "event_ordinal": 10},
        "death_state_2": {"death_state": 2, "genuine_contact_live_bytes": True, "event_ordinal": 15},
        "death_blank_timer37": {**death_blank, "event_ordinal": 20},
        "cue13_published_idle": {"cue13_actual_output": True, "published_busy": 0,
            "normal_drain": True, "cue13_emitted_end_observed": True,
            "actual_terminal_mute_observed": True, "event_ordinal": 25},
        "replacement_entry_seed": {"prior_death_blank_observed": True,
            "prior_cue13_idle_observed": True, "entry_state": 2, "event_ordinal": 30},
        "replacement_cue6_output": {"entry_seed_precedes_cue6": True, "selected_id": 6,
            "audible_store_count": 1, "event_ordinal": 35},
    }
    for cue_first in (False, True):
        lifecycle = LifecycleOrder()
        events = dict(death_events)
        if cue_first:
            events["cue13_published_idle"] = {**events["cue13_published_idle"], "event_ordinal": 12}
        for name in ("death_state_1", "death_state_2", "death_blank_timer37",
                     "cue13_published_idle", "replacement_entry_seed", "replacement_cue6_output"):
            lifecycle.record(name, events[name])
        assert lifecycle.status()["pass"]
        tested += 1
    incomplete = LifecycleOrder()
    incomplete.record("death_blank_timer37", {**death_blank, "event_ordinal": 20})
    assert not incomplete.status()["pass"] and incomplete.status()["order_failures"]
    tested += 1

    proof_evidence = {
        "first_cue6_owned_psg_transaction": {"selected_id": 6, "slot": 0, "policy": 0xB3,
            "best_slot": 0, "best_priority": 5, "mix_match": True,
            "audible_store_count": 1, "event_ordinal": 10},
        "first_post_psg_busy_one": {"busy": 1, "derived_marker": True,
            "busy_read_after_psg": True, "event_ordinal": 12},
        "cue6_terminal_stream_end_owned": {"slot_id": 6, "x_matches_emitted_end": True,
            "terminator_byte": 0, "stream_decoder_matches_emitted_bytes": True,
            "event_ordinal": 14},
        "terminal_actual_psg_mute_transaction": {"slot_clear_observed": True,
            "all_mix_stores_match": True, "quiet_state_verified": True,
            "actual_mute_attenuation_stores": 3, "actual_store_count": 11, "event_ordinal": 16},
        "terminal_post_psg_busy_zero": {"busy": 0, "all_slots_queues_credit_idle": True,
            "busy_read_after_psg": True, "event_ordinal": 18},
        "final_pose_in_front_after_irq_commit": {"irq_commit_observed": True,
            "front_pixels_match_opaque_player": True, "live_code_span_qualified": True,
            "irq_live_opcode_match": True, "front_mapping_qualified": True,
            "same_stop_busy_sample": True,
            "opaque_pixels_compared": 72, "front_id": 1,
            "visible_width_bytes": 8, "front_owner_voff1_shadow": 0xB0,
            "front_owner_voff2_shadow": 0, "front_physical_base": 0x58000,
            "entry_marker_x": 264, "entry_seed_lives": 0,
            "irq_commit_end_pc": 0xEDB, "published_music_busy": 1,
            "irq_commit_event_ordinal": 8, "event_ordinal": 8},
        "release_after_audio_and_front_commit": {"busy_zero_precedes_release": True,
            "front_commit_precedes_release": True, "event_ordinal": 20},
        "no_same_batch_player_or_enemy_mutation": {"player_unchanged": True,
            "enemy_unchanged": True, "event_ordinal": 21},
    }
    front_order = fixture_order_status("front-first", [
        {"name": "final_pose_in_front_after_irq_commit", "event_ordinal": 8,
         "irq_commit_event_ordinal": 8, "same_stop_busy_sample": True,
         "published_music_busy": 1, "entry_marker_x": 264, "entry_seed_lives": 0,
         "visible_width_bytes": 8, "opaque_pixels_compared": 72},
        {"name": "terminal_post_psg_busy_zero", "event_ordinal": 18}])
    assert front_order["pass"]
    wrong_front_order = fixture_order_status("front-first", [
        {"name": "final_pose_in_front_after_irq_commit", "event_ordinal": 18,
         "irq_commit_event_ordinal": 18, "same_stop_busy_sample": True,
         "published_music_busy": 0, "entry_marker_x": 264, "entry_seed_lives": 0,
         "visible_width_bytes": 8, "opaque_pixels_compared": 72},
        {"name": "terminal_post_psg_busy_zero", "event_ordinal": 8}])
    assert not wrong_front_order["pass"]
    music_order = fixture_order_status("music-first", [
        {"name": "final_pose_in_front_after_irq_commit", "event_ordinal": 18,
         "irq_commit_event_ordinal": 18, "same_stop_busy_sample": True,
         "published_music_busy": 0, "entry_marker_x": 264, "entry_seed_lives": 0,
         "visible_width_bytes": 8, "opaque_pixels_compared": 72},
        {"name": "terminal_post_psg_busy_zero", "event_ordinal": 8}])
    assert music_order["pass"]
    wrong_music_busy = fixture_order_status("music-first", [
        {"name": "final_pose_in_front_after_irq_commit", "event_ordinal": 18,
         "irq_commit_event_ordinal": 18, "same_stop_busy_sample": True,
         "published_music_busy": 1, "entry_marker_x": 264, "entry_seed_lives": 0,
         "visible_width_bytes": 8, "opaque_pixels_compared": 72},
        {"name": "terminal_post_psg_busy_zero", "event_ordinal": 8}])
    assert not wrong_music_busy["pass"]
    late_wait_proxy = fixture_order_status("front-first", [
        {"name": "final_pose_in_front_after_irq_commit", "event_ordinal": 20,
         "irq_commit_event_ordinal": 8, "same_stop_busy_sample": True,
         "published_music_busy": 1, "entry_marker_x": 264, "entry_seed_lives": 0,
         "visible_width_bytes": 8, "opaque_pixels_compared": 72},
        {"name": "terminal_post_psg_busy_zero", "event_ordinal": 18}])
    assert not late_wait_proxy["pass"] and late_wait_proxy["status"] == "INVALID_EVIDENCE"
    tested += 5
    for front_first in (True, False):
        ledger = ProofLedger()
        order = list(REQUIRED_PROOFS)
        if front_first:
            order.remove("final_pose_in_front_after_irq_commit")
            order.insert(0, "final_pose_in_front_after_irq_commit")
        for name in order:
            ledger.record(name, proof_evidence[name])
        assert ledger.status()["pass"]
        tested += 1

    class BusySequenceClient(FakeClient):
        def __init__(self):
            super().__init__()
            self.busy_values = [1, 0]
        def call(self, method: str, params: dict[str, Any] | None = None,
                 timeout: float = 20.0):
            if method == "read_memory" and params and params["addr"] == 0x02D4:
                value = self.busy_values.pop(0)
                self.calls.append((method, params))
                self.timeouts.append(timeout)
                return {"data": f"{value:02x}", "space": "cpu"}
            return super().call(method, params, timeout)

    commit_observer = object.__new__(LiveRuntimeObserver)
    commit_observer.client = BusySequenceClient()
    commit_observer.audio = {"AUDIO_MUSIC_PUBLISHED_BUSY": 0x02D4}
    commit_observer.irq_marker = {"end_pc": 0x0EDB}
    commit_observer.irq_before = {"seq": 3, "pending": 1, "back": 1}
    commit_observer.irq_inc = {"pc": 0x0EDB, "ordinal": 7}
    commit_observer.current_entry = {"index": 0, "marker_x": 264, "seed_lives": 0}
    commit_observer.cue_entry_owner = {6: 0}
    commit_observer.pending_terminal_cues = {6}
    commit_observer.quiet_tail = {6: {"proof_kind": "first-terminal-mute-and-busy-zero"}}
    commit_observer.quiet_first_proofs = [commit_observer.quiet_tail[6]]
    commit_observer.proofs = {0: ProofLedger()}
    commit_observer.errors = []
    commit_observer.lifecycle = None
    commit_observer.release_snapshot = None
    commit_observer._record = lambda *args, **kwargs: None
    commit_state = {"pending": 0, "commit_seq": 4, "front": 1, "death": 0,
        "entry": 4, "cell_y": 18, "player_fb": VISIBLE_BASE + 20 * 160 + 10,
        "cell_x": 1, "step": 2, "face": 0, "anim": 1, "enemy_raw": b"same"}
    commit_observer._state = lambda: commit_state
    qualified_pose = {"owner": 1, "opaque_pixels_compared": 72,
        "visible_width_bytes": 8, "front_owner_voff1_shadow": 0xB0,
        "front_owner_voff2_shadow": 0, "front_physical_base": 0x58000}
    commit_observer._front_pose = lambda *args: qualified_pose
    commit_stop = MonitorStop("irq-front-commit-complete", 0x0F00, 1,
                              {"pc": 0x0F00}, 8, 8.0)
    commit_observer._irq_done(commit_stop, {"source_staged_live_match": True})
    committed_pose = commit_observer.proofs[0].records[0]
    assert committed_pose["irq_commit_event_ordinal"] == 8
    assert committed_pose["event_ordinal"] == 8
    assert committed_pose["published_music_busy"] == 1
    assert committed_pose["same_stop_busy_sample"] is True
    commit_observer.proofs[0].record("terminal_post_psg_busy_zero", {
        "busy": 0, "all_slots_queues_credit_idle": True,
        "busy_read_after_psg": True, "event_ordinal": 18})
    commit_observer._front_pose = lambda *args: (_ for _ in ()).throw(
        AssertionError("final wait re-read/proxied the IRQ-commit FRONT proof"))
    commit_observer._final_entry_wait(
        MonitorStop("iet-final-wait", 0xC000, 1, {"pc": 0xC000}, 25, 25.0), {})
    assert commit_observer.proofs[0].records[0] == committed_pose
    assert len(commit_observer.proofs[0].records) == 3
    assert commit_observer.proofs[0].records[-1]["name"] == "release_after_audio_and_front_commit"
    assert commit_observer.proofs[0].records[-1]["event_ordinal"] == 25
    assert commit_observer.pending_terminal_cues == set()
    assert commit_observer.quiet_tail[6] is commit_observer.quiet_first_proofs[0]
    tested += 1

    bad_ledger = ProofLedger()
    bad_ledger.record("first_cue6_owned_psg_transaction", proof_evidence["first_cue6_owned_psg_transaction"])
    bad_ledger.record("first_post_psg_busy_one", proof_evidence["first_post_psg_busy_one"])
    bad_ledger.record("cue6_terminal_stream_end_owned", proof_evidence["cue6_terminal_stream_end_owned"])
    bad_ledger.record("terminal_actual_psg_mute_transaction", proof_evidence["terminal_actual_psg_mute_transaction"])
    bad_ledger.record("terminal_post_psg_busy_zero", proof_evidence["terminal_post_psg_busy_zero"])
    bad_ledger.record("release_after_audio_and_front_commit", proof_evidence["release_after_audio_and_front_commit"])
    assert not bad_ledger.status()["pass"] and bad_ledger.status()["order_failures"]
    tested += 1

    return {"self_test": "PASS", "negative_checks": tested,
             "model_checks": "bounded monitor event pump and timeout races, receipt-derived ordered bootstrap reset stores with separate runtime PSG classification, exact get_run_state stop identity and source/staged/CPU/physical bytes at both the executed store span and stopped post-PC, wrong bootstrap bytes/value/mapping/order and unknown-watchpoint negatives, raw-prefix/full-staged resident receipt plus sparse-layout ROM identity gates, input-only route retains direction across changed cell/step poses and rotates only after eight identical source-qualified step-0 no-progress samples, immediate entry/death isolation without direction rotation, cached low-RAM player direction/want and box/enemy/freeze timer decoding with truncated-snapshot rejection, natural contact timeout retains JSON-safe enemy bytes/input tails/entries/proof ledgers without monitor rereads and with bounded lists, three-entry natural held-South challenge with complete state2/state3/state4 pose and FRONT coverage plus missing-state/frame negatives, generation-scoped state3 A/B saved-under restoration with row-derived x320, invalid FRONT metadata, clipped pixel match and first-state4 gate negatives, state2/state4 missing-visible-pose failures, report JSON serialization, no target RAM writes, one source-qualified cold credit and consumed start, candidate-emitted IRQ marker/DP, raw PSG period encoding, selected-source onset versus latch-only WAIT, source-count-authoritative terminal music occupancy with exact eight-byte type/capacity and active/malformed negatives, fail-closed terminal-audio snapshot retention through the real dispatch handler with one halted-state query and no memory rereads, complete audio/FRONT DAG in both orders, death-blank/cue13 completion in both orders, VOFF1/VOFF2 GIME shadow mapping, clipped edge-pose pixels with transparent clipping, IRQ-commit ordinal and same-stop busy proof",
            "target_write_calls": "fake client only; exactly one $003A approved write tested per fixture",
            "emulator_launches": 0, "target_writes": 0}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-build", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--scenario", choices=SCENARIOS)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--run-live", action="store_true")
    parser.add_argument("--xroar-binary", type=Path)
    parser.add_argument("--delivery-receipt", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        print(json.dumps(self_test(), indent=2))
        return 0
    if args.run_live:
        if args.prepare_only:
            parser.error("--run-live and --prepare-only are mutually exclusive")
        if args.candidate_build is None or args.output_dir is None or args.scenario is None:
            parser.error("--run-live requires --candidate-build, --output-dir, and --scenario")
        if args.xroar_binary is None or args.delivery_receipt is None:
            parser.error("--run-live requires --xroar-binary and --delivery-receipt")
        if not args.xroar_binary.is_file():
            raise GuardFailure("the requested XRoar binary does not exist")
        if not args.delivery_receipt.is_file():
            raise GuardFailure("--run-live requires a parent-accepted GDB-MCP delivery receipt")
        output = args.output_dir.resolve()
        if output.exists() and any(output.iterdir()):
            raise GuardFailure("--run-live requires a fresh, empty scenario output directory")
        report = prepare(args.candidate_build)
        adaptive = require_adaptive_keyboard_profile(args.candidate_build)
        receipt = json.loads(args.delivery_receipt.read_text(encoding="utf-8"))
        delivery = validate_delivery_receipt(receipt, report)
        if not LIVE_CAPTURE_IMPLEMENTED:
            print(json.dumps({"status": "BLOCKED", "runtime_ready": False,
                "qualified_profile": adaptive, "delivery_qualification": delivery,
                "reason": "live event adapter is incomplete: no target process was launched",
                "emulator_launches": 0, "target_writes": 0}, indent=2))
            return 2
        summary, exit_code = run_live_capture(args.xroar_binary, args.candidate_build,
            output, args.scenario, report, adaptive, delivery)
        print(json.dumps(summary, indent=2))
        return exit_code
    if not args.prepare_only:
        parser.print_help()
        return 2
    if args.candidate_build is None or args.output_dir is None or args.scenario is None:
        parser.error("--prepare-only requires --candidate-build, --output-dir, and --scenario")
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = prepare(args.candidate_build)
    report.update({
        "scenario": args.scenario,
        "prepared_at": "pre-runtime; no emulator launch and no target writes",
        "output_dir": str(output),
        "deadlines_seconds": {"each_named_phase": PHASE_SECONDS,
            "monitor_stop_wait_max": STOP_WAIT_SECONDS,
            "phase_names": WATCHED_PHASES},
        "gameplay_worklist_cycle_target_max": GAMEPLAY_WORKLIST_CYCLE_TARGET,
        "exact_runtime_command_shape": (
            "python runtime-observer-20261012.py --candidate-build <integrated-build> "
            "--output-dir <fresh-scenario-dir> --scenario <natural|front-first|music-first|prior-music> "
            "--run-live --xroar-binary <patched-xroar> --delivery-receipt <parent-accepted-gdb-mcp.json>"),
        "acceptance_proofs_required": list(REQUIRED_PROOFS),
    })
    report_path = output / f"bug117-{args.scenario}-preparation.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PREPARED_WITH_BLOCKER", "report": str(report_path),
                      "runtime_ready": False, "blocked_observable": report["blocked_observable"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
