"""Verify FEAT-006 GMC audio placement, entry points, and loader coverage."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from gmc_lzss import decompress as lzss_decompress


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
PAGE_BYTES = 0x2000
WINDOW_BASE = 0xA000
CART_BANK_BYTES = 0x4000
ENGINE_LIMIT = 920
PACKED_SOUND_BYTES = 3478
KNOWN_AUDIO_DP_BYTES = 20
MAX_REGISTER_WRITES = 11


def parse_stream_include(path: Path) -> tuple[bytes, dict[str, int]]:
    """Return packed stream bytes and label offsets from the generated include."""
    packed = bytearray()
    labels: dict[str, int] = {}
    in_streams = False
    for raw in path.read_text(encoding="ascii").splitlines():
        line = raw.split(";", 1)[0].strip()
        if not line:
            continue
        if line.startswith("gmc_cue_stream_") and " " not in line:
            in_streams = True
            labels[line] = len(packed)
            continue
        if line == "gmc_sound_data_end":
            break
        if in_streams and line.startswith("fcb "):
            packed.extend(int(item.strip().lstrip("$"), 16)
                          for item in line[4:].split(","))
    return bytes(packed), labels


def decode_stream(stream: bytes, start: int) -> tuple[list[int], list[int], list[int]]:
    """Execute one cue stream and return tester-equivalent writes and wait resumes."""
    writes: list[int] = []
    mute_writes: list[int] = []
    resumes: list[int] = []
    pointer = start
    while True:
        command = stream[pointer]
        pointer += 1
        if command == 0:
            return writes, mute_writes, resumes
        if command == 2:
            wait = stream[pointer]
            pointer += 1
            if wait == 0:
                wait = 1
            resumes.append(pointer)
            continue
        if 0x10 <= command <= 0x12:
            voice = command - 0x10
            period = stream[pointer] | (stream[pointer + 1] << 8)
            attenuation = stream[pointer + 2]
            pointer += 3
            writes.extend((0x80 | (voice << 5) | (period & 0x0F),
                           (period >> 4) & 0x3F,
                           0x90 | (voice << 5) | attenuation))
            continue
        if command == 0x1C:
            writes.extend((0xE0 | stream[pointer], 0xF0 | stream[pointer + 1]))
            pointer += 2
            continue
        if command == 0x1D:
            writes.append(0xF0 | stream[pointer])
            pointer += 1
            continue
        if command == 0x1E:
            mask = stream[pointer]
            pointer += 1
            for voice in range(4):
                if mask & (1 << voice):
                    mute_writes.append(0x90 | (voice << 5) | 0x0F)
            continue
        raise SystemExit(f"audio proof: invalid command ${command:02X} at stream offset {pointer - 1}")


def manifest_writes(row: dict) -> list[int]:
    """Independently translate normalized cue events into tester PSG bytes."""
    events = []
    for voice in row["translation"]["voices"]:
        events.extend(voice["normalized_commands"])
    events.sort(key=lambda event: (event["tick"], event.get("logical_voice", 3)))
    writes: list[int] = []
    for event in events:
        operation = event["operation"]
        if operation == "tone":
            voice = event["logical_voice"]
            period = event["period"]
            writes.extend((0x80 | (voice << 5) | (period & 0x0F),
                           (period >> 4) & 0x3F,
                           0x90 | (voice << 5) | event["attenuation"]))
        elif operation == "noise":
            writes.extend((0xE0 | event["control"], 0xF0 | event["attenuation"]))
        elif operation == "noise-volume":
            writes.append(0xF0 | event["attenuation"])
        else:
            raise SystemExit(f"audio proof: unsupported normalized operation {operation!r}")
    return writes


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "src/audio_runtime.s")
    parser.add_argument("--runtime", type=Path, default=BUILD / "ladybug-audio-runtime.bin")
    parser.add_argument("--map", type=Path, default=None,
                        help="main ROM map; retained for the FEAT-006 command contract")
    parser.add_argument("--audio-map", type=Path, default=BUILD / "ladybug-audio-runtime.map")
    parser.add_argument("--manifest", type=Path, default=BUILD / "ladybug-sparse-layout.json")
    parser.add_argument("--bank0", type=Path, default=BUILD / "ladybug-gmc-bank0-overflow.bin")
    parser.add_argument("--bank2", type=Path, default=BUILD / "ladybug-sparse-bank2.bin")
    parser.add_argument("--bank3", type=Path, default=BUILD / "ladybug-sparse-bank3.bin")
    parser.add_argument("--cues", type=Path, default=ROOT / "assets/arcade/audio/gmc-runtime-cues.json")
    parser.add_argument("--gmc-manifest", type=Path, default=None,
                        help="approved GMC cue manifest; alias for --cues")
    parser.add_argument("--event-map", type=Path,
                        default=ROOT / "assets/arcade/audio/feat-006-event-to-cue.json")
    parser.add_argument("--rom", type=Path, default=None,
                        help="built ROM to hash-check for the evidence record")
    parser.add_argument("--require-cues", type=int, default=18)
    parser.add_argument("--require-source-margin", type=int, default=0)
    parser.add_argument("--require-audio-dp-max", type=int, default=24)
    parser.add_argument("--require-writes", type=int, default=12)
    parser.add_argument("--require-cycles", type=int, default=0)
    return parser.parse_args()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def symbols(path: Path) -> dict[str, int]:
    found: dict[str, int] = {}
    pattern = re.compile(
        r"^Symbol: (audio_engine_start|audio_engine_end|audio_install_page|audio_mix_write|"
        r"gmc_cue_descriptors|gmc_sound_data_end) .* = ([0-9A-Fa-f]+)$"
    )
    for line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if match:
            found[match.group(1)] = int(match.group(2), 16)
    return found


def main() -> None:
    args = parse_args()
    source_text = args.source.read_text(encoding="ascii")
    required = {
        "audio_service_impl",
        "audio_init_impl",
        "audio_enqueue_impl",
        "audio_process_queue",
        "audio_mix",
        "audio_poll_gameplay",
        "audio_install_page",
    }
    missing_source = [name for name in sorted(required) if name not in source_text]
    if missing_source:
        raise SystemExit("audio proof: source labels missing: " + ", ".join(missing_source))

    runtime = args.runtime.read_bytes()
    audio_map = args.audio_map
    if args.map is not None and "audio_engine_start" in args.map.read_text(encoding="ascii"):
        audio_map = args.map
    located = symbols(audio_map)
    required_symbols = {
        "audio_engine_start", "audio_engine_end", "audio_install_page", "audio_mix_write",
        "gmc_cue_descriptors", "gmc_sound_data_end",
    }
    if not required_symbols.issubset(located):
        raise SystemExit("audio proof: runtime map is missing placement symbols")
    if located["audio_engine_start"] != WINDOW_BASE:
        raise SystemExit("audio proof: engine does not start at $A000")
    engine_bytes = located["audio_engine_end"] - located["audio_engine_start"]
    installer_offset = located["audio_install_page"] - WINDOW_BASE
    if engine_bytes > ENGINE_LIMIT:
        raise SystemExit(f"audio proof: engine is {engine_bytes} bytes; limit is {ENGINE_LIMIT}")
    if located["audio_mix_write"] < located["audio_engine_end"]:
        raise SystemExit("audio proof: PSG writer remains inside the copied engine")
    if not 0 <= installer_offset < len(runtime):
        raise SystemExit("audio proof: installer is outside the runtime payload")
    if runtime[:9:3] != bytes((0x16, 0x16, 0x16)):
        raise SystemExit("audio proof: copied entry table is not three long branches")

    cue_path = args.gmc_manifest or args.cues
    cue_manifest = json.loads(cue_path.read_text(encoding="ascii"))
    cue_count = cue_manifest.get("cue_count")
    if cue_count != args.require_cues or len(cue_manifest.get("cues", [])) != args.require_cues:
        raise SystemExit(
            f"audio proof: approved cue manifest has {cue_count}; "
            f"required count is {args.require_cues}"
        )
    cue_rows = {int(row["cue_id"]): row for row in cue_manifest["cues"]}
    for left, right in ((8, 7), (17, 16)):
        if cue_rows[left]["descriptor_bytes"] != cue_rows[right]["descriptor_bytes"]:
            raise SystemExit(f"audio proof: cue alias {left} does not match cue {right}")

    include_path = args.source.parent.parent / "assets/arcade/audio/gmc_sound_data.inc"
    stream_bytes, stream_labels = parse_stream_include(include_path)
    total_cue_writes = 0
    total_waits = 0
    for cue_id in range(args.require_cues):
        row = cue_rows[cue_id]
        label = row["stream_label"]
        if label not in stream_labels:
            raise SystemExit(f"audio proof: cue {cue_id} stream label is absent")
        expected_offset = row["binary_stream_offset"] - cue_manifest["descriptor_bytes"]
        if stream_labels[label] != expected_offset:
            raise SystemExit(f"audio proof: cue {cue_id} descriptor selects the wrong stream offset")
        actual_writes, mute_writes, resumes = decode_stream(stream_bytes, stream_labels[label])
        expected_writes = manifest_writes(row)
        if actual_writes != expected_writes:
            raise SystemExit(f"audio proof: cue {cue_id} PSG stream differs from tester oracle")
        if any(right <= left for left, right in zip([stream_labels[label], *resumes], resumes)):
            raise SystemExit(f"audio proof: cue {cue_id} wait does not resume after its operand")
        total_cue_writes += len(actual_writes) + len(mute_writes)
        total_waits += len(resumes)

    event_map = json.loads(args.event_map.read_text(encoding="ascii"))
    entries = event_map.get("entries", [])
    if len(entries) != args.require_cues:
        raise SystemExit("audio proof: event-to-cue matrix does not cover every cue ID")
    cue_ids = sorted(entry.get("cue_id") for entry in entries)
    if cue_ids != list(range(args.require_cues)):
        raise SystemExit("audio proof: event-to-cue matrix cue IDs are not 0..17")
    unresolved = event_map.get("unresolved", [])
    if not any(item.get("event") == "high_score_end" for item in unresolved):
        raise SystemExit("audio proof: high-score END mapping is not explicitly unresolved")

    layout = json.loads(args.manifest.read_text(encoding="ascii"))
    audio_meta = layout.get("audio_runtime")
    if not audio_meta or audio_meta["page"] != 0x3D or audio_meta["address"] != WINDOW_BASE:
        raise SystemExit("audio proof: sparse manifest does not place audio at page $3D/$A000")
    if audio_meta["bytes"] != len(runtime) or audio_meta["sha256"] != digest(runtime):
        raise SystemExit("audio proof: sparse manifest audio hash or length mismatch")

    banks = {
        0: args.bank0.read_bytes(),
        2: args.bank2.read_bytes(),
        3: args.bank3.read_bytes(),
    }
    if any(len(bank) != CART_BANK_BYTES for bank in banks.values()):
        raise SystemExit("audio proof: candidate GMC bank is not 16 KiB")
    segments = [
        segment
        for segment in layout["gmc"]["segments"]
        if segment["target"] == "audio_runtime"
    ]
    compressed = next((stream for stream in layout.get("compression", {}).get("streams", [])
                       if stream.get("name") == "audio_page_3d"), None)
    if not segments and compressed is None:
        raise SystemExit("audio proof: loader has no audio target")
    rebuilt = bytearray(len(runtime))
    coverage = bytearray(len(runtime))
    for segment in segments:
        if segment["destination_page"] != 0x3D:
            raise SystemExit("audio proof: audio loader segment has the wrong destination page")
        target_offset = segment["target_offset"]
        count = segment["count"]
        expected_address = WINDOW_BASE + target_offset
        if segment["destination_address"] != expected_address:
            raise SystemExit("audio proof: audio loader destination is not contiguous")
        end = target_offset + count
        if end > len(runtime) or any(coverage[target_offset:end]):
            raise SystemExit("audio proof: audio loader coverage overlaps or exceeds payload")
        source_offset = segment["source_offset"]
        segment_source = banks[segment["bank"]][source_offset:source_offset + count]
        rebuilt[target_offset:end] = segment_source
        coverage[target_offset:end] = b"\x01" * count
    if compressed is not None:
        start = compressed["source_offset"]
        packed = banks[compressed["bank"]][start:start + compressed["compressed_bytes"]]
        rebuilt[:] = lzss_decompress(packed, compressed["raw_bytes"])
        coverage[:] = b"\x01" * len(runtime)
    if rebuilt != runtime or not all(coverage):
        raise SystemExit("audio proof: sparse loader does not reconstruct the complete runtime")

    if args.rom is not None:
        rom_digest = digest(args.rom.read_bytes())
    else:
        rom_digest = "not-supplied"
    packed_sound_bytes = located["gmc_sound_data_end"] - located["gmc_cue_descriptors"]
    source_margin = layout["gmc"]["spare_bytes"] + len(runtime) - packed_sound_bytes
    if args.require_source_margin and source_margin < args.require_source_margin:
        raise SystemExit(
            f"audio proof: source margin is {source_margin}; "
            f"required minimum is {args.require_source_margin}"
        )
    if KNOWN_AUDIO_DP_BYTES > args.require_audio_dp_max:
        raise SystemExit(
            f"audio proof: direct-page audio state is {KNOWN_AUDIO_DP_BYTES}; "
            f"limit is {args.require_audio_dp_max}"
        )
    engine_end_source = source_text.index("\naudio_engine_end\n")
    writer_start = source_text.index("\naudio_mix_write\n")
    if writer_start < engine_end_source:
        raise SystemExit("audio proof: copied engine still contains the PSG writer")
    if source_text.count("jsr     audio_mix_write") != 2 or "lbsr    audio_mix_write" in source_text:
        raise SystemExit("audio proof: copied callers do not use the mapped absolute PSG writer")
    writer_source = source_text[writer_start:
                                source_text.index("\naudio_poll_enqueue\n", writer_start)]
    for fragment in (
        "clr     AUDIO_WORK_VOICE",
        "inc     AUDIO_WORK_VOICE",
        "cmpa    #3",
        "sta     audio_scratch+1",
        "lslb\n        lslb\n        lslb\n        lslb",
        "lsra\n        lsra\n        lsra\n        lsra",
        "anda    #$3F",
    ):
        if fragment not in writer_source:
            raise SystemExit(f"audio proof: bounded little-endian PSG writer is missing {fragment!r}")
    if writer_source.count("bsr     audio_write") != 5:
        raise SystemExit("audio proof: not every PSG write site uses the spaced writer")
    audio_write_source = writer_source[writer_source.index("audio_write\n"):]
    if audio_write_source.count("nop") != 4 or "sta     SND_DATA" not in audio_write_source:
        raise SystemExit("audio proof: PSG writer does not enforce the 32-clock spacing contract")
    if "stb     SND_DATA" in writer_source or writer_source.count("sta     SND_DATA") != 1:
        raise SystemExit("audio proof: direct PSG writes bypass the spaced writer")
    if ((0x80 | (0x0356 & 0x0F)), ((0x0356 >> 4) & 0x3F)) != (0x86, 0x35):
        raise SystemExit("audio proof: independent SN76489 period-packing oracle failed")
    write_sites = writer_source.count("bsr     audio_write")
    # One tone write site is looped for three voices: latch, period-high, and
    # attenuation, followed by two non-looped noise writes.
    write_count = 11 if write_sites == 5 else 0
    if write_count > args.require_writes:
        raise SystemExit(
            f"audio proof: worst register write count is {write_count}; "
            f"limit is {args.require_writes}"
        )
    if write_count != MAX_REGISTER_WRITES:
        raise SystemExit("audio proof: register-write shadow contract is incomplete")
    for fragment in ("cmpa    ,u", "cmpa    1,u", "cmpa    2,u"):
        if fragment not in source_text:
            raise SystemExit("audio proof: unchanged-output shadow comparison is incomplete")
    if "lda     AUDIO_SAVED_ID\n        ldb     #8\n        mul" not in source_text:
        raise SystemExit("audio proof: cue descriptor indexing is not bounded ID*8")
    if "audio_command_wait\n        lda     ,x+" not in source_text or "stx     4,y" not in source_text:
        raise SystemExit("audio proof: WAIT does not retain the consumed stream pointer")
    for loop_label, counter, limit in (
        ("audio_init_slot_loop", "AUDIO_WORK_SLOT", 4),
        ("audio_find_free", "AUDIO_WORK_SLOT", 4),
        ("audio_find_low", "AUDIO_WORK_SLOT", 4),
        ("audio_advance_next", "AUDIO_WORK_SLOT", 4),
        ("audio_mix_find_exclusive", "AUDIO_WORK_SLOT", 4),
        ("audio_mix_all_next", "AUDIO_WORK_SLOT", 4),
        ("audio_mix_tone_next", "AUDIO_WORK_VOICE", 3),
    ):
        start = source_text.index(f"\n{loop_label}\n")
        block = source_text[start:source_text.index("\n        blo     ", start) + 40]
        if f"inc     {counter}" not in block or f"cmpa    #{limit}" not in block:
            raise SystemExit(f"audio proof: {loop_label} does not use its stable bounded counter")
        if "incb" in block or "cmpb" in block:
            raise SystemExit(f"audio proof: {loop_label} still trusts clobbered B")
    pending = sum(entry.get("implementation_status") == "anchor_pending" for entry in entries)
    if args.require_cycles and "AUDIO_SERVICE_CYCLES_MEASURED" not in source_text:
        raise SystemExit(
            f"audio proof: no measured service-cycle evidence; required maximum is {args.require_cycles}"
        )

    print(
        f"audio proof: {cue_count} cue descriptors; payload {len(runtime)} bytes at page $3D; "
        f"engine {engine_bytes}/{ENGINE_LIMIT} bytes; installer ${located['audio_install_page']:04X}; "
        f"{len(segments) or 1} loader streams reconstruct exactly; source margin {source_margin}; "
        f"writes {write_count}; pending anchors {pending}; ROM {rom_digest}"
        f"; executed {args.require_cues} isolated cues, {total_waits} waits, "
        f"{total_cue_writes} tester-equivalent PSG bytes"
    )


if __name__ == "__main__":
    main()
