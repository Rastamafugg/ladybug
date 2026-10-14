#!/usr/bin/env python3
"""Guarded natural-play observer for BUG-058.

Importing this module is offline: the emulator, socket, monitor helpers, and
process launcher are loaded only inside the explicit --natural-gameplay path.
The runtime arm uses read-only monitor calls plus the ticket's bounded natural
key press/release sequence. It never writes guest memory or registers.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve()
ROOT = next(
    (parent for parent in HERE.parents
     if (parent / "wiki/internal/tickets").is_dir()),
    HERE.parents[5],
)
CONTRACT_PATH = HERE.with_name("preparation.json")
MAX_PHASE_SECONDS = 45.0
MAX_STOP_SECONDS = 10.0
EXPECTED_FAST_CYCLES = 27000
PAGE_SIZE = 0x2000
CPU_BANK_START = 0xA000
ACTIVE_ENTRY = 0x038F
ACTIVE_RETURN = 0xC116
ACTIVE_AUDIO_VECTOR = 0x039B
ACTIVE_AUDIO_ENTRY = 0x047C
ACTIVE_AUDIO_RETURN = 0x0488
MAIN_WORKLIST_CALL = 0xC14F
MAIN_WORKLIST_RETURN = 0xC152
ACTIVE_AUDIO_DIRECT_CALLS = {
    0x03A2: {"action": 0, "caller": "adaptive_work"},
    0x03C5: {"action": 1, "caller": "adaptive_work"},
    0x0404: {"action": 3, "caller": "adaptive_work"},
    0x0409: {"action": 1, "caller": "adaptive_work"},
    0x040E: {"action": 2, "caller": "adaptive_work"},
    0x0515: {"action": 1, "caller": "adaptive_tick_binding"},
}
ACTIVE_AUDIO_CALL_WINDOWS = {
    0x03A2: bytes.fromhex("4fbd047c"),
    0x03C5: bytes.fromhex("8601bd047c"),
    0x0404: bytes.fromhex("8603bd047c"),
    0x0409: bytes.fromhex("8601bd047c"),
    0x040E: bytes.fromhex("8602bd047c"),
    0x0515: bytes.fromhex("8601bd047c"),
}
ACTIVE_AUDIO_TAIL_CALL = 0x0426
PRESENTATION_FLOW_TICK = 0x1900
STARTUP_KEY_INIT = 0xDF24
PSG_DATA = 0xFF51
PSG_POST_STORE = 0xA49C
PAR5 = 0xFFA5
PAR0 = 0xFFA0
PAGE_AUDIO = 0x3D
PAGE_GAME = 0x34
ENEMY_TABLE = 0xA470
ENEMY_ACTIVE = 0x0058
ENEMY_RELEASED = 0x0059
PLAYER_FB = 0x000B
PLAYER_DIR = 0x0006
PLAYER_WANT = 0x000F
PLAYER_STEP = 0x0008
PLAYER_CELL_X = 0x0009
PLAYER_CELL_Y = 0x000A
JOY_DIR = 0x0005
PRES_MODE = 0x00A5
PRES_SCREEN = 0x00A6
PRES_CONTEXT = 0x00A7
PRES_CREDITS = 0x00A8
PRES_EVENT = 0x00A9
INITIAL_ENTRY_STATE = 0x00A0
DEATH_STATE = 0x004D
PICKUP_TIMER = 0x0051
ENEMY_ANIM = 0x0054
ENEMY_TIMER = 0x0055
FREEZE_TIMER = 0x005B
PLAYER_TICK_PENDING = 0x006B
RENDER_FLAGS = 0x007F
FB_FRONT_ID = 0x008F
FB_RENDER_PENDING = 0x0091
FB_COMMIT_SEQ = 0x0092
FB_SIM_SEQ = 0x0094
FB_MISSED_COMMIT = 0x0096
FRAMES = 0x0002
VOFF1 = 0xFF9D
SIM_TIME_CPU = 0xBD26
SIM_TIME_PAGE = 0x3D
SIM_TIME_WIDTH = 2
AD_MODE_BYTE = 0xBD40
AUDIO_BUSY = 0x02D4
AUDIO_INSTALLED = 0x00F0
KB_BIND = 0x0287
KB_FIXED_COIN_MATRIX = 44
MATRIX_DEFAULTS = (27, 35, 43, 51, 6)
DIRECTION_NAMES = ("Up", "Down", "Left", "Right")
DIRECTION_VALUES = (0, 2, 3, 1)
FIXED_ALLOWED_KEYS = frozenset((5, 48))
DEFAULT_ALLOWED_KEYS = frozenset((5, 43, 44, 45, 46, 48))
BREAKPOINTS = frozenset((PRESENTATION_FLOW_TICK, ACTIVE_ENTRY, ACTIVE_RETURN,
                         ACTIVE_AUDIO_ENTRY, ACTIVE_AUDIO_RETURN))
MONITOR_METHODS = frozenset({
    "read_cycles", "read_memory", "read_registers", "get_run_state",
    "run", "wait_for_stop", "set_breakpoint", "clear_breakpoint",
    "list_breakpoints", "set_watchpoint", "clear_watchpoint",
    "list_watchpoints", "inject_key",
})
WATCHPOINT_SPEC = {"addr": PSG_DATA, "length": 1, "kind": "w"}
TICK_MASK = (1 << 64) - 1


class ObserverError(RuntimeError):
    """Fail-closed observer or qualification error."""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_digest(path: Path) -> str:
    return digest(path.read_bytes())


def contract() -> dict[str, Any]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def repo_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def require_path(path: Path, label: str) -> Path:
    if not path.is_file():
        raise ObserverError(f"missing required {label}: {path}")
    return path


def checked_pins() -> dict[str, str]:
    contract_hash = file_digest(CONTRACT_PATH)
    spec = contract()
    require_hash_match("observer preparation contract", contract_hash,
                       file_digest(CONTRACT_PATH))
    observed: dict[str, str] = {}
    for group in ("files", "sources"):
        for rel, expected in spec["pins"][group].items():
            path = require_path(ROOT / rel, rel)
            actual = file_digest(path)
            observed[rel] = actual
            require_hash_match(f"pinned {group[:-1]} {rel}", expected, actual)
    receipt_path = require_path(ROOT / "build/source-build-receipt.json",
                                "source-build receipt")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt_inputs = receipt.get("inputs")
    if not isinstance(receipt_inputs, dict):
        raise ObserverError("pinned source-build receipt has no input hash map")
    excluded = set(spec["pins"].get("excluded_source_receipt_inputs", []))
    if not excluded <= set(receipt_inputs):
        raise ObserverError("source receipt no longer contains the explicitly excluded TMX inputs")
    capsule_rel = Path(spec["provenance"]["frozen_source_root"])
    if capsule_rel.is_absolute() or ".." in capsule_rel.parts:
        raise ObserverError("frozen source capsule path escapes the project root")
    capsule_root = ROOT / capsule_rel
    verified_receipt_inputs: dict[str, str] = {}
    verified_capsule_inputs: dict[str, str] = {}
    for rel, expected in receipt_inputs.items():
        relative = Path(rel)
        if relative.is_absolute() or ".." in relative.parts:
            raise ObserverError(f"source receipt input escapes the project root: {rel}")
        if rel in excluded:
            current_path = None
        else:
            current_path = require_path(ROOT / relative, f"source receipt input {rel}")
        capsule_path = require_path(capsule_root / relative,
                                    f"frozen capsule source receipt input {rel}")
        capsule_actual = file_digest(capsule_path)
        require_hash_match(f"frozen capsule source receipt input {rel}",
                           expected, capsule_actual)
        verified_capsule_inputs[rel] = capsule_actual
        if current_path is not None:
            actual = file_digest(current_path)
            require_hash_match(f"source receipt input {rel}", expected, actual)
            verified_receipt_inputs[rel] = actual
    observed["source-receipt-inputs.count"] = str(len(verified_receipt_inputs))
    observed["source-receipt-inputs.sha256"] = digest(
        json.dumps(verified_receipt_inputs, sort_keys=True,
                   separators=(",", ":")).encode()
    )
    observed["frozen-capsule-inputs.count"] = str(len(verified_capsule_inputs))
    observed["frozen-capsule-inputs.sha256"] = digest(
        json.dumps(verified_capsule_inputs, sort_keys=True,
                   separators=(",", ":")).encode()
    )
    observed["preparation.json"] = contract_hash
    return observed


def require_contract_identity(artifacts: dict[str, Any]) -> dict[str, Any]:
    spec = artifacts["spec"]
    require_hash_match("observer preparation contract during capture",
                       artifacts["contract_sha256"], file_digest(CONTRACT_PATH))
    return spec


def parse_map(path: Path) -> dict[str, int]:
    text = require_path(path, "map file").read_text(encoding="utf-8", errors="strict")
    return {
        name.casefold(): int(value, 16)
        for name, value in re.findall(
            r"^Symbol:\s+(\w+)\s+.*?=\s+([0-9A-Fa-f]+)\s*$",
            text, re.MULTILINE,
        )
    }


def require_symbol(symbols: dict[str, int], name: str, expected: int) -> None:
    actual = symbols.get(name.casefold())
    if actual != expected:
        raise ObserverError(
            f"map symbol {name} mismatch: expected ${expected:04X}, "
            f"got {None if actual is None else f'${actual:04X}'}"
        )


def require_hash_match(label: str, expected: str, actual: str) -> None:
    if expected != actual:
        raise ObserverError(f"{label} SHA256 mismatch: expected {expected}, got {actual}")


def require_byte_identity(label: str, *spans: bytes) -> None:
    if len(spans) < 2 or any(span != spans[0] for span in spans[1:]):
        observed = [span.hex() for span in spans]
        raise ObserverError(f"{label} byte identity mismatch: {observed}")


def require_page_owner(label: str, observed: int, expected: int) -> int:
    actual = observed & 0x3F
    if actual != expected:
        raise ObserverError(f"{label} owner mismatch: ${actual:02X} != ${expected:02X}")
    return actual


def validate_phase_limits(phase_seconds: float, stop_seconds: float) -> None:
    if phase_seconds != MAX_PHASE_SECONDS or stop_seconds != MAX_STOP_SECONDS:
        raise ObserverError("approved limits are fixed at phase 45s and stop 10s")


def validate_api_stack(entry_stack: int, return_stack: int) -> None:
    if (not 0 <= int(entry_stack) <= 0xFFFF
            or not 0 <= int(return_stack) <= 0xFFFF):
        raise ObserverError(f"adaptive audio S values must be unsigned 16-bit: {entry_stack}, {return_stack}")
    if int(return_stack) != int(entry_stack):
        raise ObserverError(
            f"adaptive audio API stack ownership changed: ${entry_stack:04X} -> ${return_stack:04X}"
        )


def validate_api_return(entry_stack: int, return_stack: int,
                        expected_pc: int, observed_pc: int) -> None:
    validate_api_stack(entry_stack, return_stack)
    if not 0 <= int(expected_pc) <= 0xFFFF or not 0 <= int(observed_pc) <= 0xFFFF:
        raise ObserverError(
            f"adaptive audio return PCs must be unsigned 16-bit: {expected_pc}, {observed_pc}"
        )
    if int(observed_pc) != int(expected_pc):
        raise ObserverError(
            f"adaptive audio stack return changed: ${expected_pc:04X} -> ${observed_pc:04X}"
        )


def validate_active_span(monitor: Any, artifacts: dict[str, Any],
                         address: int, length: int, label: str) -> bytes:
    """Prove one low-RAM active-driver span against staged, physical, and live bytes."""
    spec = require_contract_identity(artifacts)
    active = artifacts["blobs"]["active"]
    offset = address - ACTIVE_ENTRY
    if offset < 0 or length <= 0 or offset + length > len(active):
        raise ObserverError(f"{label} is outside the copied active-driver module")
    expected = active[offset:offset + length]
    audio = artifacts["blobs"]["audio"]
    stage_offset = spec["symbols"]["copied_adaptive"]["stage_file_offset"] + offset
    staged = audio[stage_offset:stage_offset + length]
    destination_page = spec["symbols"]["copied_adaptive"]["destination_page"]
    physical = monitor.read(destination_page * PAGE_SIZE + address, length, "physical")
    live = monitor.read(address, length, "cpu")
    require_byte_identity(f"{label} source/staged/physical/live",
                          expected, staged, physical, live)
    return live


def qualify_audio_api_physical(monitor: GuardedMonitor,
                               artifacts: dict[str, Any]) -> dict[str, Any]:
    """Qualify the source/map/artifact/physical code range for the banked API."""
    spec = require_contract_identity(artifacts)
    symbols = artifacts["maps"]["audio"]
    start = symbols.get("audio_adaptive_api")
    end = symbols.get("audio_adaptive_last")
    if start != 0xB638 or end != 0xB78D or end <= start:
        raise ObserverError("audio adaptive API source/map range changed")
    audio = artifacts["blobs"]["audio"]
    offset = start - CPU_BANK_START
    expected = audio[offset:offset + end - start]
    physical = monitor.read(PAGE_AUDIO * PAGE_SIZE + offset, len(expected), "physical")
    require_byte_identity("audio adaptive API artifact/physical", expected, physical)
    return {"start": start, "end_exclusive": end,
            "bytes": len(expected), "physical_page": PAGE_AUDIO,
            "artifact_sha256": digest(expected),
            "physical_sha256": digest(physical),
            "source": "src/adaptive_audio_service.s:audio_adaptive_api..audio_adaptive_last"}


def qualify_audio_api_live(monitor: GuardedMonitor,
                           artifacts: dict[str, Any]) -> dict[str, Any]:
    """Qualify the executed API range through PAR5=$3D and the physical page."""
    owner = require_page_owner("adaptive audio return PAR5", monitor.byte(PAR5), PAGE_AUDIO)
    proof = qualify_audio_api_physical(monitor, artifacts)
    expected = artifacts["blobs"]["audio"][
        proof["start"] - CPU_BANK_START:
        proof["end_exclusive"] - CPU_BANK_START
    ]
    before = require_page_owner("adaptive audio return PAR5 before CPU read",
                                monitor.byte(PAR5), PAGE_AUDIO)
    live = monitor.read(proof["start"], proof["bytes"], "cpu")
    after = require_page_owner("adaptive audio return PAR5 after CPU read",
                               monitor.byte(PAR5), PAGE_AUDIO)
    if owner != before or owner != after:
        raise ObserverError("PAR5 changed while qualifying adaptive audio API bytes")
    physical = monitor.read(PAGE_AUDIO * PAGE_SIZE + proof["start"] - CPU_BANK_START,
                            proof["bytes"], "physical")
    require_byte_identity("audio adaptive API artifact/physical/live",
                          expected, physical, live)
    return {**proof, "live_sha256": digest(live), "par5": owner}


def validate_required_coverage(transitions: list[dict[str, Any]],
                               worklists: list[dict[str, Any]],
                               logical_advances: int, timer_edges: int,
                               input_response: bool,
                               front_witness: dict[str, Any] | None) -> None:
    counts = [row.get("count") for row in transitions]
    if counts.count(1) != 1 or counts.count(2) != 1 or counts.count(3) != 1:
        raise ObserverError(f"mandatory ordinary release markers must be exactly [1, 2, 3]: {counts}")
    if [row.get("from") for row in transitions if row.get("count") in (1, 2, 3)] != [0, 1, 2]:
        raise ObserverError("mandatory ordinary release transitions are not consecutive 0-to-1-to-2-to-3")
    recent = worklists[-3:]
    indices = [row.get("index") for row in recent]
    if len(recent) < 3 or any(
        row.get("start", {}).get("enemy_active") != 3
        or row.get("end", {}).get("enemy_active") != 3
        or row.get("start", {}).get("classification") != "regular_controllable"
        or row.get("end", {}).get("classification") != "regular_controllable"
        or not row.get("accounting", {}).get("reconciles")
        for row in recent
    ) or any(right != left + 1 for left, right in zip(indices, indices[1:])):
        raise ObserverError("three consecutive reconciled regular three-enemy worklists are required")
    if logical_advances < 2 or timer_edges < 2:
        raise ObserverError("three-enemy recurrence lacks two distinct simulation and timer/animation edges")
    if not input_response:
        raise ObserverError("source-qualified accepted-input response is missing")
    if not front_witness:
        raise ObserverError("actual FRONT pixel witness tied to accepted input is missing")


def validate_front_witness(before: dict[str, Any] | None,
                           after: dict[str, Any] | None) -> None:
    if not before or not after:
        raise ObserverError("actual FRONT before/after witness is incomplete")
    before_player = before.get("actor_windows", {}).get("player", {})
    after_player = after.get("actor_windows", {}).get("player", {})
    if (before_player.get("pointer") == after_player.get("pointer")
            and before_player.get("sha256") == after_player.get("sha256")):
        raise ObserverError("accepted input did not change the source-qualified player FRONT window")
    if before.get("surface_sha256") == after.get("surface_sha256"):
        raise ObserverError("player-window change lacks a published FRONT surface pixel change")


def matrix_to_dscan(matrix_code: int) -> int:
    """Convert column*8+physical-row bindings into pinned XRoar DSCAN codes."""
    if not 0 <= matrix_code <= 63:
        raise ObserverError(f"project matrix code outside 0..63: {matrix_code}")
    project_column, physical_row = divmod(matrix_code, 8)
    if physical_row == 7:
        raise ObserverError(f"unmapped project matrix row: {matrix_code}")
    dscan_row = 6 if physical_row == 6 else (physical_row + 2) % 6
    return dscan_row * 8 + project_column


def expected_keycodes() -> dict[str, int]:
    source = (ROOT / "src/keybinding_runtime.s").read_text(encoding="utf-8")
    match = re.search(r"(?m)^key_defaults\s*\r?\n\s*fcb\s+([^;\r\n]+)", source)
    if not match:
        raise ObserverError("could not derive key defaults from the pinned source")
    tokens = [part.strip() for part in match.group(1).split(",")]
    if tokens[:4] != ["27", "35", "43", "51"] or len(tokens) != 5:
        raise ObserverError(f"unexpected authored key_defaults: {tokens}")
    matrices = tuple(int(part) if part.isdigit() else 6 for part in tokens)
    if matrices != MATRIX_DEFAULTS:
        raise ObserverError(f"authored defaults changed: {matrices}")
    movement = [matrix_to_dscan(code) for code in matrices[:4]]
    enter = matrix_to_dscan(matrices[4])
    coin = matrix_to_dscan(KB_FIXED_COIN_MATRIX)
    result = {name: movement[index] for index, name in enumerate(DIRECTION_NAMES)}
    result.update({"Enter": enter, "Coin": coin})
    if set(result.values()) != set(DEFAULT_ALLOWED_KEYS):
        raise ObserverError(f"derived DSCAN allowlist mismatch: {result}")
    return result


def live_keycodes(monitor: "GuardedMonitor") -> dict[str, int]:
    matrix = list(monitor.read(KB_BIND, 5))
    if any(code > 63 for code in matrix):
        raise ObserverError(f"live key binding is outside the matrix range: {matrix}")
    if len(set(matrix[:4])) != 4:
        raise ObserverError(f"live movement bindings are not unique: {matrix[:4]}")
    directions = [matrix_to_dscan(code) for code in matrix[:4]]
    enter = matrix_to_dscan(matrix[4])
    coin = matrix_to_dscan(KB_FIXED_COIN_MATRIX)
    result = {name: directions[index]
              for index, name in enumerate(DIRECTION_NAMES)}
    result.update({"Enter": enter, "Coin": coin,
                   "matrix_slots": matrix})
    return result


def parse_cue_stream(source: str, label: str) -> bytes:
    lines = source.splitlines()
    try:
        start = next(i for i, line in enumerate(lines)
                     if re.fullmatch(rf"\s*{re.escape(label)}\s*", line))
    except StopIteration as exc:
        raise ObserverError(f"missing authored audio stream {label}") from exc
    output = bytearray()
    for line in lines[start + 1:]:
        stripped = line.strip()
        if not stripped or stripped.startswith(";"):
            continue
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", stripped):
            break
        if "fcb" not in stripped.lower():
            continue
        data = stripped.split(";", 1)[0].split(None, 1)[1]
        for token in data.split(","):
            token = token.strip()
            if token.startswith("$"):
                output.append(int(token[1:], 16))
            elif token.lower().startswith("0x"):
                output.append(int(token, 16))
            else:
                output.append(int(token, 10))
    if not output or output[-1] != 0:
        raise ObserverError(f"authored stream {label} has no terminal zero")
    return bytes(output)


def validate_artifact_layout() -> dict[str, Any]:
    spec = contract()
    pins = checked_pins()
    contract_hash = file_digest(CONTRACT_PATH)
    require_hash_match("observer preparation contract preflight",
                       pins["preparation.json"], contract_hash)
    paths = {
        "rom": ROOT / "build/ladybug.rom",
        "receipt": ROOT / "build/source-build-receipt.json",
        "main_map": ROOT / "build/ladybug.map",
        "runtime_rom": ROOT / "build/ladybug-runtime.rom",
        "active": ROOT / "build/ladybug-adaptive-active.bin",
        "active_map": ROOT / "build/ladybug-adaptive-active.map",
        "audio": ROOT / "build/ladybug-audio-runtime.bin",
        "audio_map": ROOT / "build/ladybug-audio-runtime.map",
        "enemy_map": ROOT / "build/ladybug-enemy-runtime.map",
        "presentation": ROOT / "build/ladybug-presentation-runtime.bin",
        "presentation_map": ROOT / "build/ladybug-presentation-runtime.map",
        "keybinding_map": ROOT / "build/ladybug-keybinding-runtime.map",
    }
    blobs = {name: require_path(path, name).read_bytes()
             for name, path in paths.items() if name not in ("receipt",)}
    runtime_rom = blobs["runtime_rom"]
    active = blobs["active"]
    audio = blobs["audio"]
    presentation = blobs["presentation"]
    if len(runtime_rom) != 0x4000:
        raise ObserverError(f"runtime component has {len(runtime_rom)} bytes, expected 16384")
    if len(active) != 622:
        raise ObserverError(f"active driver has {len(active)} bytes, expected 622")
    if len(audio) != 0x1A00:
        raise ObserverError(f"audio staged image has {len(audio)} bytes, expected 6656")
    if len(presentation) != 1259:
        raise ObserverError(f"presentation module has {len(presentation)} bytes, expected 1259")
    if runtime_rom[0x0116:0x0117] != b"\x13":
        raise ObserverError("runtime ROM $C116 SYNC marker differs")
    if runtime_rom[0x014F:0x0154] != bytes.fromhex("bd038f20c2"):
        raise ObserverError("runtime ROM $C14F dispatch bytes differ")
    stage_offset = 0xB792 - 0xA000
    if audio[stage_offset:stage_offset + len(active)] != active:
        raise ObserverError("adaptive staged bytes differ from pinned active-driver image")

    main_symbols = parse_map(paths["main_map"])
    active_symbols = parse_map(paths["active_map"])
    audio_symbols = parse_map(paths["audio_map"])
    key_symbols = parse_map(paths["keybinding_map"])
    presentation_symbols = parse_map(paths["presentation_map"])
    enemy_symbols = parse_map(paths["enemy_map"])
    require_symbol(main_symbols, "mainloop", 0xC116)
    require_symbol(main_symbols, "ad_dispatch_work", 0xC14F)
    require_symbol(main_symbols, "presentation_key_service", STARTUP_KEY_INIT)
    require_symbol(key_symbols, "KB_BIND", KB_BIND)
    require_symbol(audio_symbols, "audio_slot0", 0xB5BB)
    require_symbol(audio_symbols, "audio_mix_periods", 0xB62B)
    require_symbol(audio_symbols, "audio_mix_atten", 0xB631)
    require_symbol(audio_symbols, "audio_mix_noise", 0xB634)
    require_symbol(audio_symbols, "audio_mix_shadow", 0xB5CC)
    require_symbol(audio_symbols, "audio_adaptive_api", 0xB638)
    require_symbol(audio_symbols, "audio_adaptive_last", 0xB78D)
    required_audio_symbols = ("audio_music_count", "audio_music_queue",
                              "audio_slot0", "audio_mix_periods",
                              "audio_mix_atten", "audio_mix_noise",
                              "audio_mix_shadow", "gmc_cue_stream_06")
    for symbol in required_audio_symbols:
        if symbol.casefold() not in audio_symbols:
            raise ObserverError(f"audio map lacks required symbol {symbol}")
    for symbols, symbol in (
        (active_symbols, "AD_WORK_EXEC"),
        (active_symbols, "AD_AUDIO_EXEC"),
        (active_symbols, "adaptive_audio_binding"),
        (key_symbols, "key_service"),
        (presentation_symbols, "presentation_flow_tick"),
        (presentation_symbols, "presentation_module_end"),
        (enemy_symbols, "enemy_tick_impl"),
    ):
        if symbol.casefold() not in symbols:
            raise ObserverError(f"module map lacks required symbol {symbol}")
    require_symbol(presentation_symbols, "presentation_flow_tick", PRESENTATION_FLOW_TICK)
    require_symbol(presentation_symbols, "presentation_module_end", 0x1DEB)
    require_symbol(active_symbols, "AD_WORK_EXEC", ACTIVE_ENTRY)
    require_symbol(active_symbols, "AD_AUDIO_EXEC", ACTIVE_AUDIO_VECTOR)
    require_symbol(active_symbols, "adaptive_audio_binding", ACTIVE_AUDIO_ENTRY)
    require_symbol(active_symbols, "adaptive_work", 0x03A1)
    require_symbol(active_symbols, "aw_output", 0x0424)
    require_symbol(active_symbols, "adaptive_tick_binding", 0x0491)
    require_symbol(active_symbols, "adaptive_global_binding", 0x051D)
    require_symbol(key_symbols, "KB_BIND", KB_BIND)
    require_symbol(audio_symbols, "AUDIO_SERVICE_GATEWAY", 0x02DE)
    require_symbol(audio_symbols, "AUDIO_SERVICE_RETURN", 0x02EC)
    require_symbol(audio_symbols, "audio_service_gateway_bytes", 0xA2D7)
    require_symbol(audio_symbols, "audio_service_return_bytes", 0xA2E5)
    require_symbol(audio_symbols, "audio_write", 0xA499)
    for symbol, address in (
        ("audio_write_tone_latch_done", 0xA439),
        ("audio_write_tone_data_done", 0xA454),
        ("audio_write_tone_atten_done", 0xA46D),
        ("audio_write_noise_control_done", 0xA486),
        ("audio_write_noise_atten_done", 0xA492),
    ):
        require_symbol(audio_symbols, symbol, address)

    main_addresses = spec["symbols"]["main"]
    for map_symbols, name, field in (
        (main_symbols, "PRES_MODE", "pres_mode"),
        (main_symbols, "AD_MODE_BYTE", "ad_mode_byte"),
        (main_symbols, "INITIAL_ENTRY_STATE", "initial_entry_state"),
        (main_symbols, "DEATH_STATE", "death_state"),
        (main_symbols, "PICKUP_TIMER", "pickup_timer"),
        (main_symbols, "ENEMY_TIMER", "enemy_timer"),
        (main_symbols, "ENEMY_ANIM", "enemy_anim"),
        (enemy_symbols, "ENEMY_ACTIVE", "enemy_active"),
        (enemy_symbols, "ENEMY_RELEASED", "enemy_released"),
        (enemy_symbols, "ENEMY_TABLE", "enemy_table"),
        (main_symbols, "PLAYER_DIR", "player_dir"),
        (main_symbols, "PLAYER_WANT", "player_want"),
        (main_symbols, "PLAYER_STEP", "player_step"),
        (main_symbols, "PLAYER_CELL_X", "player_cell_x"),
        (main_symbols, "PLAYER_CELL_Y", "player_cell_y"),
        (main_symbols, "JOY_DIR", "joy_dir"),
        (main_symbols, "PLAYER_FB", "player_fb"),
        (main_symbols, "PLAYER_TICK_PENDING", "player_tick_pending"),
        (main_symbols, "RENDER_FLAGS", "render_flags"),
        (main_symbols, "FB_FRONT_ID", "fb_front_id"),
        (main_symbols, "FB_RENDER_PENDING", "fb_render_pending"),
        (main_symbols, "FB_COMMIT_SEQ", "fb_commit_seq"),
        (main_symbols, "FB_SIM_SEQ", "fb_sim_seq"),
        (main_symbols, "FB_MISSED_COMMIT", "fb_missed_commit"),
        (main_symbols, "FRAMES", "frames"),
        (main_symbols, "GIME_PAR5", "par5"),
        (main_symbols, "GIME_VOFF1", "gime_voff1"),
        (audio_symbols, "AUDIO_MUSIC_PUBLISHED_BUSY", "audio_music_published_busy"),
        (main_symbols, "AD_SIM_TIME", "ad_sim_time"),
        (presentation_symbols, "PRES_SCREEN", "pres_screen"),
        (presentation_symbols, "PRES_CONTEXT", "pres_context"),
        (presentation_symbols, "PRES_CREDITS", "pres_credits"),
        (presentation_symbols, "PRES_EVENT", "pres_event"),
    ):
        require_symbol(map_symbols, name, main_addresses[field])
    require_symbol(active_symbols, "AD_SIM_TIME",
                    spec["symbols"]["copied_adaptive"]["sim_time"])
    require_symbol(active_symbols, "AD_MODE_BYTE",
                    spec["symbols"]["copied_adaptive"]["mode_byte"])
    active_base = spec["symbols"]["copied_adaptive"]["work_entry"]
    audio_binding = active_symbols["adaptive_audio_binding"]
    audio_vector_offset = ACTIVE_AUDIO_VECTOR - active_base
    binding_offset = audio_binding - active_base
    return_offset = ACTIVE_AUDIO_RETURN - active_base
    if audio_binding + 12 != spec["symbols"]["copied_adaptive"]["audio_api_return"]:
        raise ObserverError("$0488 audio API return no longer follows the mapped source binding call")
    require_byte_identity(
        "active audio vector/binding source bytes",
        active[audio_vector_offset:audio_vector_offset + 3],
        b"\x7e" + audio_binding.to_bytes(2, "big"),
    )
    require_byte_identity(
        "active audio binding entry-to-return source bytes",
        active[binding_offset:return_offset],
        bytes.fromhex("3402863db7ffa53502bd")
        + audio_symbols["audio_adaptive_api"].to_bytes(2, "big"),
    )
    require_byte_identity(
        "active audio binding return/stack restore bytes",
        active[return_offset:active_symbols["adaptive_tick_binding"] - active_base],
        bytes.fromhex("34028634b7ffa53582"),
    )
    expected_direct_starts = set(ACTIVE_AUDIO_DIRECT_CALLS)
    found_direct_starts = {
        active_base + offset
        for offset in range(max(0, len(active) - 2))
        if active[offset:offset + 3] == bytes.fromhex("bd047c")
    }
    if found_direct_starts != expected_direct_starts:
        raise ObserverError(
            "active audio direct-call inventory changed: "
            f"{sorted(found_direct_starts)} != {sorted(expected_direct_starts)}"
        )
    for address, expected in ACTIVE_AUDIO_CALL_WINDOWS.items():
        offset = address - active_base - (len(expected) - 3)
        require_byte_identity(
            f"active audio direct caller ${address:04X}",
            active[offset:offset + len(expected)], expected,
        )
    tail_calls = {
        active_base + offset
        for offset in range(max(0, len(active) - 2))
        if active[offset:offset + 3] == bytes.fromhex("7e047c")
    }
    if tail_calls != {ACTIVE_AUDIO_VECTOR, ACTIVE_AUDIO_TAIL_CALL}:
        raise ObserverError(
            f"active audio tail-call inventory changed: {sorted(tail_calls)}"
        )
    aw_output_offset = active_symbols["aw_output"] - active_base
    require_byte_identity("aw_output source-proven action/tail call",
                          active[aw_output_offset:aw_output_offset + 5],
                          bytes.fromhex("86027e047c"))

    active_source = (ROOT / "src/adaptive_active.s").read_text(encoding="utf-8")
    direct_source_calls = re.findall(
        r"(?im)^\s*jsr\s+adaptive_audio_binding\s*$", active_source,
    )
    tail_source_calls = re.findall(
        r"(?im)^\s*jmp\s+adaptive_audio_binding\s*$", active_source,
    )
    if len(direct_source_calls) != len(ACTIVE_AUDIO_DIRECT_CALLS):
        raise ObserverError("authored active source direct audio-call count changed")
    if len(tail_source_calls) != 2:
        raise ObserverError("authored active source audio tail-call count changed")
    if not re.search(
        r"(?ims)^adaptive_audio_binding\s*$\s*pshs\s+a\s+lda\s+#\$3d\s+"
        r"sta\s+\$ffa5\s+puls\s+a\s+jsr\s+AUDIO_ADAPTIVE_EXEC\s+"
        r"pshs\s+a\s+lda\s+#\$34\s+sta\s+\$ffa5\s+puls\s+a,pc\s*"
        r"(?=^adaptive_tick_binding\s*$)",
        active_source,
    ):
        raise ObserverError("authored audio binding no longer balances its private A pushes before/after the API")
    if not re.search(
        r"(?ims)^aw_output\s*\n\s*lda\s+#2\s*\n\s*"
        r"jmp\s+adaptive_audio_binding\s*(?=^aw_fault\s*$)",
        active_source,
    ):
        raise ObserverError("authored aw_output action-2 tail call changed")
    audio_service_source = (ROOT / "src/adaptive_audio_service.s").read_text(encoding="utf-8")
    api_source_label = re.search(r"(?m)^audio_adaptive_api\s*$", audio_service_source)
    api_end_source_label = re.search(r"(?m)^audio_adaptive_last\s+rmb\s+2\s*$",
                                     audio_service_source)
    if (api_source_label is None or api_end_source_label is None
            or api_end_source_label.start() <= api_source_label.start()):
        raise ObserverError("authored adaptive audio API range labels changed")

    main_source = (ROOT / "src/main.s").read_text(encoding="utf-8")
    if not re.search(
        r"(?ims)^ad_dispatch_work\s*\n\s*jsr\s+AD_WORK_EXEC\s*\n\s*bra\s+mainloop",
        main_source,
    ):
        raise ObserverError("authored ad_dispatch_work no longer calls the active driver at $C14F")
    install_label = re.search(r"(?m)^adaptive_install_active\s*$", main_source)
    install_end = (re.search(r"(?m)^\s*else\s*$", main_source[install_label.end():])
                   if install_label else None)
    install_body = (main_source[install_label.end():
                                install_label.end() + install_end.start()]
                    if install_label and install_end else "")
    if (not re.search(r"(?is)lda\s+#3\s+jmp\s+AD_AUDIO_EXEC", install_body)
            or len(re.findall(r"(?im)^\s*jmp\s+AD_AUDIO_EXEC\s*$", main_source)) != 1):
        raise ObserverError("$039B vector is not isolated to the mapped active-driver install tail call")
    startup_calls = re.findall(r"(?im)^\s*lbsr\s+presentation_key_service\s*$", main_source)
    if len(startup_calls) != 1 or not re.search(
        r"(?is)ldb\s+#3\s*lbsr\s+presentation_key_service", main_source,
    ):
        raise ObserverError("$DF24 wrapper is not the single startup B=3 defaults initialization call")

    presentation_source = (ROOT / "src/presentation_runtime.s").read_text(encoding="utf-8")
    if not re.search(
        r"(?mi)^\s*org\s+\$1900\s*\r?\n\s*\r?\n\s*presentation_flow_tick\s*$",
        presentation_source,
    ):
        raise ObserverError("authored presentation source no longer places presentation_flow_tick at $1900")
    pft_label = re.search(r"(?m)^presentation_flow_tick\s*$", presentation_source)
    pft_ready = presentation_source.find("pft_ready", pft_label.end()) if pft_label else -1
    if pft_label is None or pft_ready < 0 or not re.search(
        r"(?im)^\s*lbsr\s+scan_keys\s*$",
        presentation_source[pft_label.end():pft_ready],
    ):
        raise ObserverError("$1900 presentation_flow_tick source no longer owns recurring scan_keys input")

    receipt = json.loads(paths["receipt"].read_text(encoding="utf-8"))
    receipt_artifacts = receipt.get("artifacts", {})
    for rel, expected in spec["pins"]["files"].items():
        if rel.startswith("build/") and rel.rsplit("/", 1)[-1] in receipt_artifacts:
            artifact_name = rel.rsplit("/", 1)[-1]
            if receipt_artifacts[artifact_name] != expected:
                raise ObserverError(
                    f"source receipt artifact hash mismatch: {artifact_name}: "
                    f"{receipt_artifacts[artifact_name]} != {expected}"
                )
    receipt_inputs = receipt.get("inputs", {})
    for rel, expected in spec["pins"]["sources"].items():
        if rel in receipt_inputs and receipt_inputs[rel] != expected:
            raise ObserverError(f"source receipt input hash mismatch: {rel}")
    cue_source = (ROOT / "assets/arcade/audio/gmc_sound_data.inc").read_text(encoding="utf-8")
    cue6 = parse_cue_stream(cue_source, "gmc_cue_stream_06")
    cue_address = audio_symbols["gmc_cue_stream_06"]
    if audio[cue_address - 0xA000:cue_address - 0xA000 + len(cue6)] != cue6:
        raise ObserverError("cue-6 bytes differ between authored source and pinned audio image")
    keycodes = expected_keycodes()
    return {
        "pins": pins,
        "spec": spec,
        "contract_sha256": contract_hash,
        "paths": paths,
        "blobs": blobs,
        "maps": {
            "main": main_symbols,
            "active": active_symbols,
            "audio": audio_symbols,
            "enemy": enemy_symbols,
            "presentation": presentation_symbols,
            "keybinding": key_symbols,
        },
        "receipt_revision_metadata": receipt.get("revision", receipt.get("source_revision")),
        "cue6": {"source_bytes": cue6, "address": cue_address,
                 "terminal_zero_address": cue_address + len(cue6) - 1},
        "keycodes": keycodes,
    }


def event_cycles(start: int, end: int) -> int:
    if not 0 <= int(start) <= TICK_MASK or not 0 <= int(end) <= TICK_MASK:
        raise ObserverError(f"event_ticks values must be unsigned 64-bit integers: {start}, {end}")
    ticks = (int(end) - int(start)) & TICK_MASK
    if ticks % 8:
        raise ObserverError(f"event_ticks delta {ticks} is not divisible by 8")
    return ticks // 8


def physical_address(page: int, cpu_address: int) -> int:
    if not 0 <= page < 64:
        raise ObserverError(f"physical page outside six-bit range: ${page:02X}")
    if not 0xA000 <= cpu_address <= 0xBFFF:
        raise ObserverError(f"banked CPU address outside A000-BFFF: ${cpu_address:04X}")
    return page * PAGE_SIZE + cpu_address - CPU_BANK_START


def validate_enemy_records(active_count: int, records: bytes) -> list[dict[str, int]]:
    if active_count not in range(5):
        raise ObserverError(f"ENEMY_ACTIVE is outside the four-slot range: {active_count}")
    if len(records) != 32:
        raise ObserverError(f"enemy table length is {len(records)}, expected 32")
    occupied: list[dict[str, int]] = []
    for slot in range(4):
        row = records[slot * 8:(slot + 1) * 8]
        tag = row[0]
        if tag == 0:
            continue
        kind = tag >> 4
        if tag & 0x0F != 1 or kind not in range(1, 9):
            raise ObserverError(f"enemy slot {slot} has invalid source tag ${tag:02X}")
        pointer = int.from_bytes(row[1:3], "big")
        if not 0x2000 <= pointer < 0x9800:
            raise ObserverError(f"enemy slot {slot} has invalid framebuffer pointer ${pointer:04X}")
        if row[4] >= 24 or row[5] >= 24:
            raise ObserverError(
                f"enemy slot {slot} has out-of-maze cell ({row[4]}, {row[5]})"
            )
        if row[7] not in DIRECTION_VALUES:
            raise ObserverError(f"enemy slot {slot} has invalid direction {row[7]}")
        occupied.append({
            "slot": slot, "kind": kind, "tag": tag,
            "framebuffer": pointer, "cell_x": row[4], "cell_y": row[5],
            "flags": row[6], "direction": row[7],
        })
    if len(occupied) != active_count:
        raise ObserverError(
            f"ENEMY_ACTIVE={active_count} disagrees with {len(occupied)} tagged records"
        )
    return occupied


def validate_reconciliation(outer: int, spans: list[tuple[int, int]]) -> int:
    ordered = sorted(spans)
    used = 0
    previous_end: int | None = None
    for begin, end in ordered:
        if begin < 0 or end < begin:
            raise ObserverError(f"invalid measured span {begin}..{end}")
        if previous_end is not None and begin < previous_end:
            raise ObserverError("overlapping accounting spans")
        used += end - begin
        previous_end = end
    residual = outer - used
    if residual < 0:
        raise ObserverError(f"negative accounting residual {residual}")
    return residual


def classify_pause(entry: int, death: int, pickup: int, freeze: int) -> str:
    del freeze  # Freeze is a separate state flag; it does not redefine controllability.
    if entry or death:
        return "entry_or_death_transition"
    if pickup:
        return "intentional_collectible_pause"
    return "regular_controllable"


class GuardedMonitor:
    """Narrow wrapper: no generic call method is exposed to the runner."""

    def __init__(self, client: Any):
        self._client = client
        self._bps: dict[int, int] = {}
        self._watch_id: int | None = None
        self._input_open = False
        self._allowed_keys = set(FIXED_ALLOWED_KEYS)
        self._held_keys: set[int] = set()
        self.total_stops = 0
        self.stop_counts: dict[str, int] = {}
        self.stop_timeline: list[dict[str, Any]] = []

    def _call(self, method: str, params: dict[str, Any] | None = None,
              timeout: float = MAX_STOP_SECONDS) -> dict[str, Any]:
        if method not in MONITOR_METHODS:
            raise ObserverError(f"denied monitor method: {method}")
        if not 0 < timeout <= MAX_STOP_SECONDS:
            raise ObserverError(f"monitor timeout outside 0..10 seconds: {timeout}")
        if method == "wait_for_stop":
            milliseconds = int((params or {}).get("timeout_ms", 0))
            if not 0 <= milliseconds <= 10000:
                raise ObserverError(f"wait_for_stop timeout outside 0..10000 ms: {milliseconds}")
        return self._client.call(method, params, timeout=timeout)

    def read(self, address: int, length: int = 1, space: str = "cpu") -> bytes:
        if not 0 <= address <= 0xFFFF_FFFF or not 0 <= length <= 0x10000:
            raise ObserverError("invalid read range")
        if space == "cpu":
            if address + length > 0x10000:
                raise ObserverError("CPU read crosses the address-space boundary")
        elif space == "physical":
            allowed = (
                (0x70000, 0x72000),
                (PAGE_GAME * PAGE_SIZE, (PAGE_GAME + 1) * PAGE_SIZE),
                (PAGE_AUDIO * PAGE_SIZE, (PAGE_AUDIO + 1) * PAGE_SIZE),
                (0x58000, 0x58000 + 0x7800),
                (0x60000, 0x60000 + 0x7800),
            )
            if not any(start <= address and address + length <= end
                       for start, end in allowed):
                raise ObserverError(f"physical read outside assigned read windows: {address:#x}+{length}")
        else:
            raise ObserverError(f"unsupported read address space {space}")
        result = self._call("read_memory", {"addr": address, "length": length,
                                             "space": space})
        data = bytes.fromhex(result.get("data", ""))
        if len(data) != length:
            raise ObserverError(f"short {space} read at {address:#x}: {len(data)} != {length}")
        return data

    def byte(self, address: int) -> int:
        return self.read(address)[0]

    def word(self, address: int, space: str = "cpu") -> int:
        return int.from_bytes(self.read(address, 2, space), "big")

    def cycles(self) -> int:
        value = self._call("read_cycles").get("event_ticks")
        if not isinstance(value, int) or value < 0:
            raise ObserverError(f"invalid read_cycles.event_ticks: {value!r}")
        return value

    def registers(self) -> dict[str, int]:
        return self._call("read_registers")

    def set_breakpoint(self, address: int) -> int:
        if address not in BREAKPOINTS or address in self._bps:
            raise ObserverError(f"breakpoint address denied or duplicate: ${address:04X}")
        result = self._call("set_breakpoint", {"addr": address})
        ident = result.get("id")
        if not isinstance(ident, int) or ident <= 0 or result.get("addr") != address:
            raise ObserverError(f"invalid breakpoint registration for ${address:04X}: {result}")
        self._bps[address] = ident
        self._assert_breakpoints()
        return ident

    def clear_breakpoint(self, address: int) -> None:
        ident = self._bps.get(address)
        if ident is None:
            raise ObserverError(f"breakpoint not registered: ${address:04X}")
        self._call("clear_breakpoint", {"id": ident})
        del self._bps[address]
        self._assert_breakpoints()

    def _assert_breakpoints(self) -> None:
        actual = self._call("list_breakpoints").get("breakpoints", [])
        normalized = sorted((int(row["id"]), int(row["addr"])) for row in actual)
        expected = sorted((ident, address) for address, ident in self._bps.items())
        if normalized != expected:
            raise ObserverError(f"registered breakpoint inventory differs: {normalized} != {expected}")
        if any(0xA000 <= address <= 0xBFFF for _, address in normalized):
            raise ObserverError("banked Axxx execution breakpoint is forbidden")

    def set_audio_watchpoint(self) -> int:
        if self._watch_id is not None:
            raise ObserverError("PSG watchpoint already installed")
        self._assert_watchpoint()
        result = self._call("set_watchpoint", WATCHPOINT_SPEC)
        ident = result.get("id")
        if not isinstance(ident, int) or ident <= 0:
            raise ObserverError(f"invalid PSG watchpoint registration: {result}")
        self._watch_id = ident
        self._assert_watchpoint()
        return ident

    def clear_audio_watchpoint(self) -> None:
        if self._watch_id is None:
            raise ObserverError("PSG watchpoint is not installed")
        self._call("clear_watchpoint", {"id": self._watch_id})
        self._watch_id = None
        self._assert_watchpoint()

    def _assert_watchpoint(self) -> None:
        actual = self._call("list_watchpoints").get("watchpoints", [])
        normalized = sorted((int(row["id"]), int(row["addr"]),
                             int(row["length"]), row["kind"]) for row in actual)
        expected = [] if self._watch_id is None else [
            (self._watch_id, PSG_DATA, 1, "w")
        ]
        if normalized != expected:
            raise ObserverError(f"watchpoint inventory differs: {normalized} != {expected}")

    def inject(self, key: int, action: str) -> None:
        if not self._input_open:
            raise ObserverError("key injection outside qualified presentation-flow boundary")
        if key not in self._allowed_keys or action not in ("press", "release"):
            raise ObserverError(f"denied DSCAN input: {key} {action}")
        if action == "press" and key in self._held_keys:
            raise ObserverError(f"duplicate natural key press without an intervening release: {key}")
        if action == "release" and key not in self._held_keys:
            raise ObserverError(f"forced key release without a recorded press: {key}")
        self._call("inject_key", {"key": key, "action": action}, timeout=1.0)
        if action == "press":
            self._held_keys.add(key)
        else:
            self._held_keys.remove(key)

    def configure_input_keys(self, keycodes: dict[str, int]) -> None:
        if self._input_open:
            raise ObserverError("cannot change the DSCAN allowlist inside an input boundary")
        movement_values = [keycodes.get(name) for name in DIRECTION_NAMES]
        movement = set(movement_values)
        enter = keycodes.get("Enter")
        coin = keycodes.get("Coin")
        allowed = movement | {enter, coin}
        if (None in movement_values or len(movement) != 4
                or enter is None or coin is None
                or movement & {enter, coin} or enter == coin
                or not allowed <= set(range(56))):
            raise ObserverError(f"invalid source-derived DSCAN allowlist: {keycodes}")
        if not self._held_keys <= allowed:
            raise ObserverError("live DSCAN allowlist changed while an approved key remains held")
        self._allowed_keys = allowed

    def open_input_boundary(self, stop: dict[str, Any], qualified: bool) -> None:
        ident = self._bps.get(PRESENTATION_FLOW_TICK)
        if (not qualified or self._input_open or ident is None
                or stop.get("pc") != PRESENTATION_FLOW_TICK
                or stop.get("bp_id") != ident):
            raise ObserverError("input boundary must be the exact source-qualified $1900 breakpoint")
        self._input_open = True

    def close_input_boundary(self) -> None:
        if not self._input_open:
            raise ObserverError("no input boundary is open")
        self._input_open = False

    def stop(self, deadline: float, phase: str) -> dict[str, Any]:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ObserverError(f"phase timeout: {phase}; required marker absent")
        timeout = min(MAX_STOP_SECONDS, remaining)
        before = self.cycles()
        self._call("run", timeout=min(timeout, 1.0))
        result = self._call("wait_for_stop", {"timeout_ms": int(timeout * 1000)},
                            timeout=timeout)
        reason = result.get("reason")
        if reason == "timeout":
            raise ObserverError(f"monitor stop timeout in {phase}; marker absent, not a slowdown result")
        if reason != "breakpoint":
            raise ObserverError(f"unexpected stop reason in {phase}: {result}")
        after = self.cycles()
        registers = self.registers()
        halted = self.cycles()
        if after != halted:
            raise ObserverError(f"event_ticks changed while target halted: {after} -> {halted}")
        pc = int(result.get("pc", -1))
        bpid = result.get("bp_id")
        name = f"${pc:04X}:{bpid if bpid is not None else 'watchpoint'}"
        self.total_stops += 1
        self.stop_counts[name] = self.stop_counts.get(name, 0) + 1
        row = {
            "n": self.total_stops, "phase": phase, "reason": reason,
            "pc": pc, "bp_id": bpid, "event_ticks_before_resume": before,
            "event_ticks_after_stop": after, "event_ticks_halted_check": halted,
        }
        self.stop_timeline.append(row)
        return {"pc": pc, "bp_id": bpid, "event_ticks": after,
                "registers": registers, "result": result, "trace": row}


def _runtime_imports() -> tuple[Any, Any]:
    """Import the maintained monitor definitions and fast launcher on demand."""
    import importlib.util

    def load(name: str, path: Path) -> Any:
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            raise ObserverError(f"cannot load approved helper {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    monitor = load("bug009_monitor_for_bug058", ROOT / "scripts/verify_bug009_monitor_input.py")
    launcher = load("bug011_launch_for_bug058", ROOT / "scripts/verify_bug011_runtime.py")
    return monitor, launcher


def symbol_bytes_equal(monitor: GuardedMonitor, address: int,
                       expected: bytes, label: str) -> None:
    actual = monitor.read(address, len(expected), "cpu")
    if actual != expected:
        raise ObserverError(f"live CPU bytes differ at {label} ${address:04X}: {actual.hex()} != {expected.hex()}")


def qualify_main_markers(monitor: GuardedMonitor, artifacts: dict[str, Any]) -> None:
    runtime_rom = artifacts["blobs"]["runtime_rom"]
    symbol_bytes_equal(monitor, 0xC116, runtime_rom[0x0116:0x0117], "mainloop SYNC")
    symbol_bytes_equal(monitor, MAIN_WORKLIST_CALL,
                       runtime_rom[MAIN_WORKLIST_CALL - 0xC000:
                                   MAIN_WORKLIST_CALL - 0xC000 + 5],
                       "ad_dispatch_work")
    require_symbol(artifacts["maps"]["main"], "mainloop", 0xC116)
    require_symbol(artifacts["maps"]["main"], "ad_dispatch_work", MAIN_WORKLIST_CALL)


def qualify_worklist_outer_return(monitor: GuardedMonitor,
                                  artifacts: dict[str, Any],
                                  stack: int) -> int:
    if not 0 <= int(stack) <= 0xFFFF:
        raise ObserverError(f"AD_WORK_EXEC entry S is not unsigned 16-bit: {stack}")
    qualify_main_markers(monitor, artifacts)
    return_pc = monitor.word(int(stack))
    if return_pc != MAIN_WORKLIST_RETURN:
        raise ObserverError(
            f"AD_WORK_EXEC entry stack does not name main-loop return $C152: ${return_pc:04X}"
        )
    return return_pc


def qualify_presentation_boundary(monitor: GuardedMonitor,
                                  artifacts: dict[str, Any]) -> dict[str, Any]:
    """Prove $1900 source, staged module, live mapping, and bytes before classification."""
    spec = require_contract_identity(artifacts)
    address = PRESENTATION_FLOW_TICK
    presentation = artifacts["blobs"]["presentation"]
    symbols = artifacts["maps"]["presentation"]
    require_symbol(symbols, "presentation_flow_tick", address)
    require_symbol(symbols, "presentation_module_end", address + len(presentation))
    source_path = ROOT / "src/presentation_runtime.s"
    if file_digest(source_path) != spec["pins"]["sources"]["src/presentation_runtime.s"]:
        raise ObserverError("presentation source pin changed before $1900 classification")
    expected_hash = spec["pins"]["files"]["build/ladybug-presentation-runtime.bin"]
    if digest(presentation) != expected_hash:
        raise ObserverError("staged presentation module hash differs from the pinned source receipt")

    required_page = spec["symbols"]["presentation"]["physical_page"]
    par0_before = require_page_owner("presentation PAR0", monitor.byte(PAR0), required_page)
    physical = monitor.read(par0_before * PAGE_SIZE + address, len(presentation), "physical")
    live = monitor.read(address, len(presentation), "cpu")
    par0_after = require_page_owner("presentation PAR0 after read", monitor.byte(PAR0), required_page)
    if par0_after != par0_before:
        raise ObserverError(f"PAR0 changed during presentation byte qualification: {par0_before} -> {par0_after}")
    require_byte_identity("presentation source/staged/physical/live",
                          presentation, physical, live)
    return {
        "symbol": "presentation_flow_tick", "cpu_address": address,
        "physical_page": par0_before, "source_sha256": file_digest(source_path),
        "staged_sha256": digest(presentation), "physical_sha256": digest(physical),
        "live_sha256": digest(live), "bytes": len(live),
    }


def qualify_active_driver(monitor: GuardedMonitor,
                          artifacts: dict[str, Any]) -> dict[str, Any]:
    spec = require_contract_identity(artifacts)
    active = artifacts["blobs"]["active"]
    audio = artifacts["blobs"]["audio"]
    stage_offset = 0xB792 - 0xA000
    staged = monitor.read(physical_address(PAGE_AUDIO, 0xB792), len(active), "physical")
    if staged != active or audio[stage_offset:stage_offset + len(active)] != active:
        raise ObserverError("active driver stage bytes do not match pinned source artifact")
    required_page = spec["symbols"]["copied_adaptive"]["destination_page"]
    par0_before = require_page_owner("active-driver PAR0", monitor.byte(PAR0), required_page)
    destination = par0_before * PAGE_SIZE + ACTIVE_ENTRY
    physical_live = monitor.read(destination, len(active), "physical")
    live = monitor.read(ACTIVE_ENTRY, len(active), "cpu")
    par0_after = require_page_owner("active-driver PAR0 after read", monitor.byte(PAR0), required_page)
    if par0_after != par0_before:
        raise ObserverError("PAR0 changed during active-driver byte qualification")
    require_byte_identity("active-driver source/staged", active, staged,
                          audio[stage_offset:stage_offset + len(active)])
    require_byte_identity("active-driver staged/physical/live",
                          staged, physical_live, live)
    return {
        "symbol": "AD_WORK_EXEC copied active driver",
        "cpu_start": ACTIVE_ENTRY,
        "cpu_end_exclusive": ACTIVE_ENTRY + len(active),
        "physical_page": par0_before,
        "bytes": len(active),
        "source_artifact_sha256": digest(active),
        "staged_sha256": digest(staged),
        "physical_sha256": digest(physical_live),
        "live_sha256": digest(live),
    }


def qualify_audio_module(monitor: GuardedMonitor, artifacts: dict[str, Any]) -> None:
    spec = require_contract_identity(artifacts)
    expected = artifacts["blobs"]["audio"]
    physical = monitor.read(PAGE_AUDIO * PAGE_SIZE, len(expected), "physical")
    mutable = spec["machine_bytes"]["audio_module"]["mutable_ranges"]
    immutable_spans: list[tuple[int, int]] = []
    cursor = 0
    for start, length in mutable:
        if start < cursor or length <= 0 or start + length > len(expected):
            raise ObserverError(f"invalid mutable audio range {start}+{length}")
        if cursor < start:
            immutable_spans.append((cursor, start))
        cursor = start + length
    if cursor < len(expected):
        immutable_spans.append((cursor, len(expected)))
    if any(physical[start:end] != expected[start:end] for start, end in immutable_spans):
        raise ObserverError("physical page-$3D audio image differs from pinned audio artifact")
    if monitor.byte(AUDIO_INSTALLED) == 0:
        raise ObserverError("audio runtime is not installed at the natural menu boundary")
    source_start = 0xA2D7 - 0xA000
    gateway = expected[source_start:source_start + 18]
    live_gateway = monitor.read(0x02DE, 18, "cpu")
    require_byte_identity("low-RAM audio gateway/page-$3D source", gateway, live_gateway)
    require_byte_identity("low-RAM audio return bytes",
                          expected[0x2E5:0x2E5 + 4], live_gateway[0x0E:0x12])


def read_audio_snapshot(monitor: GuardedMonitor,
                        maps: dict[str, dict[str, int]]) -> dict[str, Any]:
    symbols = maps["audio"]
    def phys_symbol(name: str, length: int) -> bytes:
        address = symbols[name.casefold()]
        return monitor.read(physical_address(PAGE_AUDIO, address), length, "physical")

    return {
        "published_busy": monitor.byte(AUDIO_BUSY),
        "music_queue_count": phys_symbol("audio_music_count", 1)[0],
        "music_queue": phys_symbol("audio_music_queue", 8).hex(),
        "slot0": phys_symbol("audio_slot0", 28).hex(),
        "periods": phys_symbol("audio_mix_periods", 6).hex(),
        "attenuation": phys_symbol("audio_mix_atten", 3).hex(),
        "noise": phys_symbol("audio_mix_noise", 2).hex(),
        "shadows": phys_symbol("audio_mix_shadow", 11).hex(),
    }


def read_snapshot(monitor: GuardedMonitor, artifacts: dict[str, Any],
                  include_audio: bool = True) -> dict[str, Any]:
    active_count = monitor.byte(ENEMY_ACTIVE)
    records = monitor.read(physical_address(PAGE_GAME, ENEMY_TABLE), 32, "physical")
    enemies = validate_enemy_records(active_count, records)
    sim_time = monitor.word(physical_address(SIM_TIME_PAGE, SIM_TIME_CPU), "physical")
    snapshot = {
        "enemy_active": active_count,
        "enemy_released": monitor.byte(ENEMY_RELEASED),
        "enemy_records": enemies,
        "entry": monitor.byte(INITIAL_ENTRY_STATE),
        "death": monitor.byte(DEATH_STATE),
        "pickup_timer": monitor.byte(PICKUP_TIMER),
        "freeze_timer": monitor.word(FREEZE_TIMER),
        "enemy_timer": monitor.byte(ENEMY_TIMER),
        "enemy_anim": monitor.byte(ENEMY_ANIM),
        "sim_time": sim_time,
        "frames": monitor.word(FRAMES),
        "player_dir": monitor.byte(PLAYER_DIR),
        "player_want": monitor.byte(PLAYER_WANT),
        "player_step": monitor.byte(PLAYER_STEP),
        "player_cell": [monitor.byte(PLAYER_CELL_X), monitor.byte(PLAYER_CELL_Y)],
        "joy_dir": monitor.byte(JOY_DIR),
        "player_fb": monitor.word(PLAYER_FB),
        "player_tick_pending": monitor.byte(PLAYER_TICK_PENDING),
        "render_intents": monitor.read(RENDER_FLAGS, 16).hex(),
        "pres_mode": monitor.byte(PRES_MODE),
        "pres_screen": monitor.byte(PRES_SCREEN),
        "pres_context": monitor.byte(PRES_CONTEXT),
        "pres_credits": monitor.byte(PRES_CREDITS),
        "pres_event": monitor.byte(PRES_EVENT),
        "fb_front": monitor.byte(FB_FRONT_ID),
        "fb_pending": monitor.byte(FB_RENDER_PENDING),
        "fb_commit_seq": monitor.word(FB_COMMIT_SEQ),
        "fb_sim_seq": monitor.word(FB_SIM_SEQ),
        "fb_missed": monitor.word(FB_MISSED_COMMIT),
        "voff1": monitor.byte(VOFF1),
        "classification": classify_pause(
            monitor.byte(INITIAL_ENTRY_STATE), monitor.byte(DEATH_STATE),
            monitor.byte(PICKUP_TIMER), monitor.word(FREEZE_TIMER),
        ),
        "enemy_freeze_active": monitor.word(FREEZE_TIMER) != 0,
        "audio_installed": bool(monitor.byte(AUDIO_INSTALLED)),
    }
    if include_audio and snapshot["audio_installed"]:
        qualify_audio_module(monitor, artifacts)
        snapshot["audio"] = read_audio_snapshot(monitor, artifacts["maps"])
        snapshot["audio_module_qualified"] = True
    else:
        snapshot["audio"] = None
        snapshot["audio_module_qualified"] = False
    return snapshot


def decode_call_target(code: bytes, return_pc: int) -> tuple[int, int] | None:
    """Decode only 6809 BSR/LBSR/extended-JSR immediately before a stacked PC."""
    if len(code) != 3:
        return None
    if code[0] == 0xBD:
        return int.from_bytes(code[1:3], "big"), 3
    if code[0] == 0x8D:
        displacement = code[1] - 256 if code[1] & 0x80 else code[1]
        return (return_pc + displacement) & 0xFFFF, 2
    if code[0] == 0x17:
        displacement = int.from_bytes(code[1:3], "big", signed=True)
        return (return_pc + displacement) & 0xFFFF, 3
    return None


def qualify_audio_api_call(monitor: GuardedMonitor, artifacts: dict[str, Any],
                           registers: dict[str, int],
                           worklist: dict[str, Any]) -> dict[str, Any]:
    """Accept only the pinned direct callers or the aw_output tail-call chain."""
    stack = int(registers["s"])
    if not 0 <= stack <= 0xFFFF:
        raise ObserverError(f"active audio binding S is not unsigned 16-bit: {stack}")
    return_pc = monitor.word(stack)
    action = int(registers["a"]) & 0xFF
    maps = artifacts["maps"]["active"]
    main_symbols = artifacts["maps"]["main"]
    active_page = require_page_owner(
        "adaptive audio caller PAR0",
        monitor.byte(PAR0),
        require_contract_identity(artifacts)["symbols"]["copied_adaptive"]["destination_page"],
    )
    if return_pc == MAIN_WORKLIST_RETURN:
        if stack != int(worklist["entry_stack"]):
            raise ObserverError(
                "aw_output tail call did not preserve the outer AD_WORK_EXEC return stack"
            )
        if action != 2:
            raise ObserverError(f"aw_output tail call has unexpected action {action}, expected 2")
        require_symbol(maps, "aw_output", 0x0424)
        require_symbol(maps, "adaptive_audio_binding", ACTIVE_AUDIO_ENTRY)
        require_symbol(main_symbols, "ad_dispatch_work", MAIN_WORKLIST_CALL)
        bytes_seen = validate_active_span(
            monitor, artifacts, ACTIVE_AUDIO_TAIL_CALL - 2, 5,
            "aw_output action and tail-call bytes",
        )
        if bytes_seen != bytes.fromhex("86027e047c"):
            raise ObserverError("live aw_output does not use the pinned action-2 tail call")
        return {
            "kind": "tail_aw_output",
            "module": "adaptive_work.aw_output",
            "call_start": ACTIVE_AUDIO_TAIL_CALL,
            "call_bytes": bytes_seen[2:].hex(),
            "action_setup_bytes": bytes_seen[:2].hex(),
            "action": action,
            "stack": stack,
            "return_pc": return_pc,
            "outer_call_start": MAIN_WORKLIST_CALL,
            "outer_return_pc": MAIN_WORKLIST_RETURN,
            "outer_entry_stack": int(worklist["entry_stack"]),
            "active_driver_physical_page": active_page,
            "stack_route": "aw_output JMP preserves main JSR AD_WORK_EXEC return word",
        }

    call_start = return_pc - 3
    expected = ACTIVE_AUDIO_DIRECT_CALLS.get(call_start)
    if expected is None or return_pc != call_start + 3:
        raise ObserverError(
            f"adaptive audio entry has an unknown stacked caller ${return_pc:04X}; "
            "aliases are not skipped"
        )
    if action != expected["action"]:
        raise ObserverError(
            f"adaptive audio caller ${call_start:04X} action {action} != "
            f"source value {expected['action']}"
        )
    if expected["caller"] == "adaptive_work":
        caller_start = maps.get("adaptive_work")
        caller_end = maps.get("aw_output")
        expected_start = 0x03A1
        expected_stack = (int(worklist["entry_stack"]) - 2) & 0xFFFF
        if stack != expected_stack:
            raise ObserverError(
                f"{expected['caller']} caller S ${stack:04X} != outer S-2 ${expected_stack:04X}"
            )
        caller_stack = {
            "kind": "single direct JSR return word",
            "outer_entry_stack": int(worklist["entry_stack"]),
            "entry_s_delta": -2,
            "caller_private_pushes": 0,
        }
    elif expected["caller"] == "adaptive_tick_binding":
        caller_start = maps.get("adaptive_tick_binding")
        caller_end = maps.get("adaptive_global_binding")
        expected_start = 0x0491
        saved_a_address = (stack + 2) & 0xFFFF
        saved_a = monitor.byte(saved_a_address)
        if saved_a not in (0, 1):
            raise ObserverError(
                f"adaptive_tick_binding private saved A is not the source-derived 0/1 state: ${saved_a:02X}"
            )
        caller_stack = {
            "kind": "JSR return word above caller PSHS A",
            "private_push_pc": 0x0511,
            "private_saved_a_address": saved_a_address,
            "private_saved_a": saved_a,
        }
    else:
        raise ObserverError(f"unrecognized authored active caller {expected['caller']}")
    if caller_start is None or caller_end is None or not caller_start <= call_start < caller_end:
        raise ObserverError(
            f"audio caller ${call_start:04X} is outside mapped module {expected['caller']}"
        )
    require_symbol(maps, expected["caller"], expected_start)
    instruction = validate_active_span(
        monitor, artifacts, call_start - (len(ACTIVE_AUDIO_CALL_WINDOWS[call_start]) - 3),
        len(ACTIVE_AUDIO_CALL_WINDOWS[call_start]),
        f"{expected['caller']} audio caller ${call_start:04X}",
    )
    if instruction != ACTIVE_AUDIO_CALL_WINDOWS[call_start]:
        raise ObserverError(f"audio caller ${call_start:04X} has unexpected action/call bytes")
    code = instruction[-3:]
    decoded = decode_call_target(code, return_pc)
    if decoded != (ACTIVE_AUDIO_ENTRY, 3):
        raise ObserverError(
            f"active audio callsite ${call_start:04X} does not target $047C: {code.hex()}"
        )
    return {
        "kind": "direct_jsr",
        "module": expected["caller"],
        "call_start": call_start,
        "call_bytes": code.hex(),
        "action_setup_bytes": instruction[:-3].hex(),
        "action": action,
        "stack": stack,
        "return_pc": return_pc,
        "worklist_entry_stack": int(worklist["entry_stack"]),
        "active_driver_physical_page": active_page,
        "caller_stack": caller_stack,
        "stack_route": "exact source/map return word; binding-private A push is already popped before banked JSR",
    }


def writer_category(return_pc: int, value: int) -> str:
    categories = {
        0xA439: "tone_latch",
        0xA454: "tone_period_continuation",
        0xA46D: "tone_attenuation",
        0xA486: "noise_control",
        0xA492: "noise_attenuation",
    }
    name = categories.get(return_pc)
    if name is None:
        raise ObserverError(f"unknown source-qualified PSG writer return ${return_pc:04X}")
    if name == "tone_latch" and (value & 0x80) == 0:
        raise ObserverError(f"PSG latch callsite stored non-latch byte ${value:02X}")
    if name == "tone_period_continuation" and (value & 0x80):
        raise ObserverError(f"PSG continuation callsite stored latch byte ${value:02X}")
    if name == "tone_attenuation" and (value & 0xF0) not in (0x90, 0xB0, 0xD0):
        raise ObserverError(f"PSG attenuation callsite stored wrong register ${value:02X}")
    if name == "noise_control" and (value & 0xF8) != 0xE0:
        raise ObserverError(f"PSG noise-control callsite stored wrong register ${value:02X}")
    if name == "noise_attenuation" and (value & 0xF0) != 0xF0:
        raise ObserverError(f"PSG noise-attenuation callsite stored wrong register ${value:02X}")
    return name


def qualify_psg_stop(monitor: GuardedMonitor, artifacts: dict[str, Any],
                     stop: dict[str, Any]) -> dict[str, Any]:
    if monitor._watch_id is None:
        raise ObserverError("PSG stop occurred without the sole registered watchpoint")
    monitor._assert_watchpoint()
    registers = stop["registers"]
    if stop["pc"] != PSG_POST_STORE or int(registers["pc"]) != PSG_POST_STORE:
        raise ObserverError(f"PSG watchpoint stop has wrong PC: {stop['result']}")
    if stop["bp_id"] not in (None, 0):
        raise ObserverError(f"PSG watchpoint unexpectedly reports execution breakpoint id {stop['bp_id']}")
    page = require_page_owner("PSG PAR5", monitor.byte(PAR5), PAGE_AUDIO)
    audio = artifacts["blobs"]["audio"]
    expected_store = audio[0x499:0x49C]
    if expected_store != bytes.fromhex("b7ff51"):
        raise ObserverError("pinned audio artifact lacks expected STA $FF51 instruction")
    cpu = monitor.read(0xA499, 3)
    physical = monitor.read(physical_address(PAGE_AUDIO, 0xA499), 3, "physical")
    require_byte_identity("PSG source/physical/CPU STA $FF51", expected_store,
                          physical, cpu)
    stack = int(registers["s"])
    return_pc = monitor.word(stack)
    if return_pc not in (0xA439, 0xA454, 0xA46D, 0xA486, 0xA492):
        raise ObserverError(f"PSG writer return not source-qualified: ${return_pc:04X}")
    call_start = return_pc - 2
    call = monitor.read(physical_address(PAGE_AUDIO, call_start), 2, "physical")
    if call[0] != 0x8D:
        raise ObserverError(f"PSG callsite is not BSR: ${call_start:04X} {call.hex()}")
    displacement = call[1] - 256 if call[1] & 0x80 else call[1]
    if ((return_pc + displacement) & 0xFFFF) != 0xA499:
        raise ObserverError(f"PSG BSR at ${call_start:04X} does not target $A499")
    if audio[call_start - 0xA000:call_start - 0xA000 + 2] != call:
        raise ObserverError("PSG dynamic callsite differs from pinned audio artifact")
    value = int(registers["a"]) & 0xFF
    return {"event_ticks": stop["event_ticks"], "pc": stop["pc"],
            "par5": page, "stack": stack, "return_pc": return_pc,
            "value": value, "category": writer_category(return_pc, value)}


def verify_front(monitor: GuardedMonitor, snapshot: dict[str, Any],
                 previous: dict[str, Any] | None) -> dict[str, Any] | None:
    owner = snapshot["fb_front"]
    if owner not in (0, 1):
        raise ObserverError(f"invalid FRONT owner {owner}")
    expected_voff = 0xC0 if owner == 0 else 0xB0
    if snapshot["voff1"] != expected_voff:
        raise ObserverError(
            f"FRONT/VOFF1 disagreement: owner={owner} VOFF1=${snapshot['voff1']:02X}"
        )
    if snapshot["fb_pending"] != 0:
        return None
    if previous is not None:
        if snapshot["fb_missed"] != previous["fb_missed"]:
            raise ObserverError("missed FRONT commit counter changed")
        if snapshot["fb_commit_seq"] == previous["fb_commit_seq"]:
            return None
    base = 0x60000 if owner == 0 else 0x58000
    frame = monitor.read(base, 30720, "physical")
    player_pointer = snapshot["player_fb"]
    actor_pointers = {"player": player_pointer}
    for enemy in snapshot["enemy_records"]:
        actor_pointers[f"enemy{enemy['slot']}"] = enemy["framebuffer"]
    windows: dict[str, dict[str, str]] = {}
    for name, pointer in actor_pointers.items():
        offset = pointer - 0x2000
        if offset < 0 or offset + 15 * 160 + 8 > len(frame):
            raise ObserverError(f"actor pixel window outside FRONT surface: {name} ${pointer:04X}")
        tile = b"".join(frame[offset + row * 160:offset + row * 160 + 8]
                        for row in range(16))
        windows[name] = {"pointer": pointer, "sha256": digest(tile),
                         "bytes_hex": tile.hex()}
    return {
        "owner": owner, "voff1": snapshot["voff1"],
        "commit_seq": snapshot["fb_commit_seq"],
        "sim_seq": snapshot["fb_sim_seq"],
        "missed": snapshot["fb_missed"],
        "surface_sha256": digest(frame), "actor_windows": windows,
    }


def _assert_stop(stop: dict[str, Any], address: int, ident: int) -> None:
    if stop["pc"] != address or stop["bp_id"] != ident:
        raise ObserverError(
            f"marker identity mismatch: wanted id={ident} pc=${address:04X}, "
            f"got id={stop['bp_id']} pc=${stop['pc']:04X}"
        )


class NaturalCapture:
    def __init__(self, monitor: GuardedMonitor, artifacts: dict[str, Any],
                 output: Path, phase_seconds: float, stop_seconds: float,
                 xroar_info: dict[str, Any]):
        validate_phase_limits(phase_seconds, stop_seconds)
        self.monitor = monitor
        self.artifacts = artifacts
        self.output = output
        self.phase_seconds = phase_seconds
        self.stop_seconds = stop_seconds
        self.keycodes = artifacts["keycodes"]
        self.records: list[dict[str, Any]] = []
        self.phase_markers: list[dict[str, Any]] = []
        self.api_open: dict[str, Any] | None = None
        self.current_work: dict[str, Any] | None = None
        self.psg_writes: list[dict[str, Any]] = []
        self.input_events: list[dict[str, Any]] = []
        self.input_mapping: dict[str, Any] = {}
        self.input_accepted = False
        self.input_response = False
        self.input_key: int | None = None
        self.release_pending = False
        self.entry_gate = False
        self.entry_commit: int | None = None
        self.cue6_terminal_seen = False
        self.cue6_transition_seen = False
        self.cue6_mute_seen = False
        self.initial_front: dict[str, Any] | None = None
        self.input_front: dict[str, Any] | None = None
        self.previous_front_state: dict[str, Any] | None = None
        self.last_completed_count = 0
        self.last_completed_released = 0
        self.count_transitions: list[dict[str, Any]] = []
        self.regular_run: list[dict[str, Any]] = []
        self.sim_advances = 0
        self.timer_edges = 0
        self.last_recurrence_snapshot: dict[str, Any] | None = None
        self.release_deadline: float | None = None
        self.release_target = 1
        self.recurring_deadline: float | None = None
        self.capture_worklists = False
        self.four_enemy_run: list[int] = []
        self.pins_after: dict[str, str] | None = None
        self.current_phase = "cold boot and first control"
        self.xroar_info = xroar_info
        self.start_ticks = self.monitor.cycles()
        self.status = "incomplete"

    def save_partial(self, failure: str | None = None) -> None:
        self.output.parent.mkdir(parents=True, exist_ok=True)
        receipt = self.receipt(failure)
        self.output.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")

    def receipt(self, failure: str | None = None) -> dict[str, Any]:
        samples = []
        for row in self.records:
            samples.append(row)
        return {
            "ticket": "BUG-058", "status": self.status,
            "failure": failure,
            "source_revision": "3cba1bfd",
            "artifact_pins_before": self.artifacts["pins"],
            "artifact_pins_after": self.pins_after,
            "receipt_source_revision_metadata": self.artifacts["receipt_revision_metadata"],
            "rom_sha256": self.artifacts["pins"].get("build/ladybug.rom"),
            "xroar": self.xroar_info,
            "clock": {"source": "read_cycles.event_ticks", "divide_by": 8,
                      "target_fast_cycles": EXPECTED_FAST_CYCLES,
                      "observer_overhead_correction": "unavailable unless a naturally equivalent lower-stop worklist exists; no estimate subtracted"},
            "phase_markers": self.phase_markers,
            "count_transitions": self.count_transitions,
            "three_enemy_recurrence": {
                "completed_regular_worklists": len(self.regular_run),
                "logical_advances": self.sim_advances,
                "timer_or_animation_edges": self.timer_edges,
                "accepted_input_response": self.input_response,
                "actual_front_pixel_witness": self.input_front is not None,
                "qualified": (len(self.regular_run) >= 3 and self.sim_advances >= 2
                              and self.timer_edges >= 2 and self.input_response
                              and self.input_front is not None),
            },
            "audio": {
                "cue6_terminal_seen": self.cue6_terminal_seen,
                "cue6_6_to_ff_seen": self.cue6_transition_seen,
                "post_end_mute_write_seen": self.cue6_mute_seen,
                "write_counts": self._psg_counts(),
                "writes": self.psg_writes,
                "causal_claim": "none; audio remains a hypothesis pending reconciled current-artifact evidence",
            },
            "input_events": self.input_events,
            "input_mapping": self.input_mapping,
            "front_before_input": self.initial_front,
            "front_input_witness": self.input_front,
            "worklists": samples,
            "monitor_observation": {
                "total_stops": self.monitor.total_stops,
                "stop_counts": self.monitor.stop_counts,
                "event_ticks_before_after_each_stop": self.monitor.stop_timeline,
            },
            "coverage": {
                "required_release_counts": [x.get("count") for x in self.count_transitions],
                "three_enemy_required": 3,
                "four_enemy": "observed" if any(row.get("end", {}).get("enemy_active") == 4 for row in samples) else "absent",
                "four_enemy_consecutive_worklists": self.four_enemy_run,
                "missing_required_coverage_fails": True,
            },
            "candidate_ranking": "deferred to parent; no unmeasured ranks or savings",
        }

    def _psg_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in self.psg_writes:
            name = row["category"]
            counts[name] = counts.get(name, 0) + 1
        return counts

    def phase_deadline(self, phase: str) -> float:
        self.current_phase = phase
        deadline = time.monotonic() + self.phase_seconds
        return deadline

    def stop(self, deadline: float) -> dict[str, Any]:
        return self.monitor.stop(deadline, self.current_phase)

    def _expected_bp(self, stop: dict[str, Any], address: int) -> int:
        ident = self.monitor._bps.get(address)
        if ident is None:
            raise ObserverError(f"unregistered expected breakpoint ${address:04X}")
        _assert_stop(stop, address, ident)
        return ident

    def _current_audio(self, state: dict[str, Any]) -> None:
        audio = state.get("audio")
        if not audio:
            return
        slot = bytes.fromhex(audio["slot0"])
        pointer = int.from_bytes(slot[4:6], "big")
        cue_end = self.artifacts["cue6"]["terminal_zero_address"]
        if slot[0] == 6 and pointer == cue_end:
            self.cue6_terminal_seen = True
        if self.cue6_terminal_seen and slot[0] == 0xFF:
            self.cue6_transition_seen = True
        attenuation = bytes.fromhex(audio["attenuation"])
        noise = bytes.fromhex(audio["noise"])
        shadows = bytes.fromhex(audio["shadows"])
        mute_state = (attenuation == b"\x0f\x0f\x0f" and noise[1] == 0x0F
                      and shadows[2] & 0x0F == 0x0F
                      and shadows[5] & 0x0F == 0x0F
                      and shadows[8] & 0x0F == 0x0F
                      and shadows[10] & 0x0F == 0x0F
                      and audio["published_busy"] == 0)
        if self.cue6_transition_seen and mute_state:
            self.cue6_mute_seen = True

    def _handle_psg(self, stop: dict[str, Any]) -> None:
        row = qualify_psg_stop(self.monitor, self.artifacts, stop)
        row["worklist_index"] = None if self.current_work is None else self.current_work["index"]
        row["cue6_transition_seen"] = self.cue6_transition_seen
        self.psg_writes.append(row)
        if (self.cue6_transition_seen and row["category"] in
                ("tone_attenuation", "noise_attenuation") and (row["value"] & 0x0F) == 0x0F):
            self.cue6_mute_seen = True

    def _qualify_key_boundary(self, stop: dict[str, Any]) -> dict[str, Any]:
        ident = self._expected_bp(stop, PRESENTATION_FLOW_TICK)
        del ident
        proof = qualify_presentation_boundary(self.monitor, self.artifacts)
        keycodes = live_keycodes(self.monitor)
        expected = expected_keycodes()
        if any(keycodes.get(name) != code for name, code in expected.items()):
            raise ObserverError(f"live key binding slots differ from authored defaults: {keycodes}")
        self.monitor.configure_input_keys(keycodes)
        self.keycodes = keycodes
        self.input_mapping = {
            "matrix_slots": keycodes["matrix_slots"],
            "dscan": {key: value for key, value in keycodes.items()
                      if key != "matrix_slots"},
            "presentation_boundary": proof,
        }
        state = read_snapshot(self.monitor, self.artifacts)
        state["presentation_qualification"] = proof
        return state

    def _inject_at_boundary(self, stop: dict[str, Any], key: int,
                            action: str, label: str) -> None:
        self._qualify_key_boundary(stop)
        self.monitor.open_input_boundary(stop, True)
        try:
            self.monitor.inject(key, action)
        finally:
            self.monitor.close_input_boundary()
        self.input_events.append({"label": label, "key_dscan": key,
                                  "action": action, "input_pc": stop["pc"],
                                  "breakpoint_id": stop["bp_id"],
                                  "event_ticks": stop["event_ticks"]})

    def _leave_input_boundary(self) -> None:
        if PRESENTATION_FLOW_TICK in self.monitor._bps:
            self.monitor.clear_breakpoint(PRESENTATION_FLOW_TICK)
        if ACTIVE_RETURN not in self.monitor._bps:
            self.monitor.set_breakpoint(ACTIVE_RETURN)

    def _next_input_boundary(self, deadline: float) -> tuple[dict[str, Any], dict[str, Any]]:
        if PRESENTATION_FLOW_TICK not in self.monitor._bps:
            self.monitor.set_breakpoint(PRESENTATION_FLOW_TICK)
        if ACTIVE_RETURN not in self.monitor._bps and self.current_work is None:
            self.monitor.set_breakpoint(ACTIVE_RETURN)
        while True:
            stop = self.stop(deadline)
            if stop["pc"] == PRESENTATION_FLOW_TICK:
                self._expected_bp(stop, PRESENTATION_FLOW_TICK)
                if self.current_work is not None:
                    raise ObserverError("presentation-flow boundary interrupted an open AD_WORK_EXEC interval")
                state = self._qualify_key_boundary(stop)
                return stop, state
            if stop["pc"] == PSG_POST_STORE and stop["bp_id"] in (None, 0):
                self._handle_psg(stop)
                continue
            pc = stop["pc"]
            ident = self.monitor._bps.get(pc)
            if ident is None or stop["bp_id"] != ident:
                raise ObserverError(f"unowned stop while waiting for $1900: {stop['result']}")
            if pc == ACTIVE_ENTRY:
                self._begin_worklist(stop)
            elif pc == ACTIVE_AUDIO_ENTRY:
                self._begin_audio_api(stop)
            elif pc == ACTIVE_AUDIO_RETURN:
                self._end_audio_api(stop)
            elif pc == ACTIVE_RETURN:
                if self.current_work is not None:
                    self._end_worklist(stop)
                else:
                    self.monitor.clear_breakpoint(ACTIVE_RETURN)
                    if self.capture_worklists and ACTIVE_ENTRY not in self.monitor._bps:
                        self.monitor.set_breakpoint(ACTIVE_ENTRY)
                if PRESENTATION_FLOW_TICK not in self.monitor._bps:
                    self.monitor.set_breakpoint(PRESENTATION_FLOW_TICK)
            else:
                raise ObserverError(f"unexpected registered stop while waiting for $1900: ${pc:04X}")

    def _wait_target(self, address: int, deadline: float) -> dict[str, Any]:
        if address not in self.monitor._bps:
            self.monitor.set_breakpoint(address)
        while True:
            stop = self.stop(deadline)
            if stop["pc"] == PSG_POST_STORE and stop["bp_id"] in (None, 0):
                self._handle_psg(stop)
                continue
            if stop["pc"] != address:
                registered = self.monitor._bps.get(stop["pc"])
                if registered is None or stop["bp_id"] != registered:
                    raise ObserverError(f"unowned execution stop while waiting for ${address:04X}: {stop['result']}")
                self._handle_marker(stop)
                continue
            ident = self.monitor._bps.get(address)
            if ident is None:
                raise ObserverError(f"expected breakpoint was cleared before hit ${address:04X}")
            _assert_stop(stop, address, ident)
            if address != PRESENTATION_FLOW_TICK:
                self.monitor.clear_breakpoint(address)
            return stop

    def _handle_marker(self, stop: dict[str, Any]) -> None:
        address = stop["pc"]
        if address == PRESENTATION_FLOW_TICK:
            # Key boundaries are consumed only by the sequence owner. A
            # background hit is a hard failure rather than a guessed input.
            raise ObserverError("unexpected keyboard boundary outside the natural-input state machine")
        if address == ACTIVE_ENTRY:
            self._begin_worklist(stop)
            return
        if address == ACTIVE_RETURN:
            self._end_worklist(stop)
            return
        if address == ACTIVE_AUDIO_ENTRY:
            self._begin_audio_api(stop)
            return
        if address == ACTIVE_AUDIO_RETURN:
            self._end_audio_api(stop)
            return
        raise ObserverError(f"unrecognized registered marker ${address:04X}")

    def _begin_audio_api(self, stop: dict[str, Any]) -> None:
        address = ACTIVE_AUDIO_ENTRY
        self._expected_bp(stop, address)
        if self.api_open is not None or self.current_work is None:
            raise ObserverError("nested or out-of-worklist adaptive audio API entry")
        active_image = qualify_active_driver(self.monitor, self.artifacts)
        qualify_main_markers(self.monitor, self.artifacts)
        entry_owner = require_page_owner(
            "adaptive audio binding entry PAR5", self.monitor.byte(PAR5), PAGE_GAME,
        )
        api_image = qualify_audio_api_physical(self.monitor, self.artifacts)
        registers = stop["registers"]
        action = int(registers["a"]) & 0xFF
        if action not in (0, 1, 2, 3):
            raise ObserverError(f"unknown adaptive audio API action {action}")
        caller = qualify_audio_api_call(
            self.monitor, self.artifacts, registers, self.current_work,
        )
        self.monitor.clear_breakpoint(ACTIVE_AUDIO_ENTRY)
        self.monitor.set_breakpoint(ACTIVE_AUDIO_RETURN)
        self.api_open = {"action": action, "entry_ticks": stop["event_ticks"],
                         "stack": int(registers["s"]), "caller": caller,
                         "active_image_at_entry": active_image,
                         "entry_par5": entry_owner,
                         "api_image_at_entry": api_image,
                         "worklist_index": self.current_work["index"]}

    def _end_audio_api(self, stop: dict[str, Any]) -> None:
        self._expected_bp(stop, ACTIVE_AUDIO_RETURN)
        if self.api_open is None:
            raise ObserverError("adaptive audio return lacks a qualified entry")
        active_image = qualify_active_driver(self.monitor, self.artifacts)
        registers = stop["registers"]
        return_pc = self.monitor.word(int(registers["s"]))
        expected_pc = self.api_open["caller"]["return_pc"]
        validate_api_return(self.api_open["stack"], int(registers["s"]),
                            expected_pc, return_pc)
        api_image = qualify_audio_api_live(self.monitor, self.artifacts)
        elapsed = event_cycles(self.api_open["entry_ticks"], stop["event_ticks"])
        self.current_work["audio_api_spans"].append({
            **self.api_open, "return_ticks": stop["event_ticks"],
            "return_pc": return_pc, "return_par5": api_image["par5"],
            "active_image_at_return": active_image,
            "api_image_at_return": api_image,
            "inclusive_cycles": elapsed,
        })
        self.api_open = None
        self.monitor.clear_breakpoint(ACTIVE_AUDIO_RETURN)
        if ACTIVE_AUDIO_ENTRY not in self.monitor._bps:
            self.monitor.set_breakpoint(ACTIVE_AUDIO_ENTRY)

    def _begin_worklist(self, stop: dict[str, Any]) -> None:
        self._expected_bp(stop, ACTIVE_ENTRY)
        if self.current_work is not None:
            raise ObserverError("worklist entry nested before prior return")
        qualify_active_driver(self.monitor, self.artifacts)
        registers = stop["registers"]
        entry_stack = int(registers["s"])
        outer_return_pc = qualify_worklist_outer_return(
            self.monitor, self.artifacts, entry_stack,
        )
        start = read_snapshot(self.monitor, self.artifacts)
        if start["enemy_active"] == 3 and self.recurring_deadline is None:
            self.recurring_deadline = time.monotonic() + self.phase_seconds
            self.current_phase = "three-enemy recurrence"
        self.current_work = {
            "index": len(self.records), "entry_ticks": stop["event_ticks"],
            "start": start, "audio_api_spans": [],
            "entry_stack": entry_stack,
            "outer_return_pc": outer_return_pc,
        }
        self.monitor.clear_breakpoint(ACTIVE_ENTRY)
        self.monitor.set_breakpoint(ACTIVE_RETURN)
        if ACTIVE_AUDIO_ENTRY not in self.monitor._bps:
            self.monitor.set_breakpoint(ACTIVE_AUDIO_ENTRY)

    def _end_worklist(self, stop: dict[str, Any]) -> None:
        self._expected_bp(stop, ACTIVE_RETURN)
        if self.current_work is None:
            raise ObserverError("worklist return lacks a qualified entry")
        if self.api_open is not None:
            raise ObserverError("worklist returned with adaptive audio call still open")
        qualify_active_driver(self.monitor, self.artifacts)
        qualify_main_markers(self.monitor, self.artifacts)
        end = read_snapshot(self.monitor, self.artifacts)
        cycles = event_cycles(self.current_work["entry_ticks"], stop["event_ticks"])
        intervals: list[tuple[int, int]] = []
        span_cycles: list[int] = []
        for span in self.current_work["audio_api_spans"]:
            begin = event_cycles(self.current_work["entry_ticks"], span["entry_ticks"])
            finish = event_cycles(self.current_work["entry_ticks"], span["return_ticks"])
            if finish > cycles:
                raise ObserverError("audio API span extends beyond its AD_WORK_EXEC interval")
            intervals.append((begin, finish))
            span_cycles.append(finish - begin)
        accounting_error: str | None = None
        try:
            residual = validate_reconciliation(cycles, intervals)
            accounting_valid = True
        except ObserverError as exc:
            residual = None
            accounting_valid = False
            accounting_error = str(exc)
        row = {
            **self.current_work,
            "return_ticks": stop["event_ticks"], "end": end,
            "cycles": cycles, "over_target_cycles": max(0, cycles - EXPECTED_FAST_CYCLES),
            "target_pass": cycles <= EXPECTED_FAST_CYCLES,
            "audio_api_inclusive_cycles_by_action": {
                str(action): sum(span["inclusive_cycles"] for span in self.current_work["audio_api_spans"]
                                 if span["action"] == action)
                for action in range(4)
            },
            "accounting": {
                "outer_inclusive_cycles": cycles,
                "qualified_nonoverlapping_audio_api_inclusive_cycles": sum(span_cycles),
                "residual_outside_audio_api_spans_cycles": residual,
                "reconciles": accounting_valid,
                "error": accounting_error,
                "irq_exclusive_cycles": None,
                "irq_exclusive_assignment": "unqualified; remains in the explicit residual unless enclosed by an audio API interval",
                "causal_subsystem_attribution": False,
            },
        }
        self.records.append(row)
        self.current_work = None
        self.monitor.clear_breakpoint(ACTIVE_RETURN)
        self._update_release_and_recurrence(row)
        self._observe_front(row)
        self.phase_markers.append({"phase": self.current_phase,
                                   "marker": "AD_WORK_EXEC return",
                                   "worklist_index": row["index"],
                                   "event_ticks": stop["event_ticks"]})
        if self.capture_worklists:
            if ACTIVE_ENTRY not in self.monitor._bps:
                self.monitor.set_breakpoint(ACTIVE_ENTRY)

    def _update_release_and_recurrence(self, row: dict[str, Any]) -> None:
        start, end = row["start"], row["end"]
        old_count, new_count = start["enemy_active"], end["enemy_active"]
        old_released, new_released = start["enemy_released"], end["enemy_released"]
        if new_count != old_count:
            if new_count != old_count + 1 or new_released != old_released + 1:
                raise ObserverError(
                    f"ordinary enemy release did not increment active/released exactly once: "
                    f"{old_count}/{old_released} -> {new_count}/{new_released}"
                )
            if new_count in (1, 2, 3, 4):
                transition = {"from": old_count, "count": new_count,
                              "released_before": old_released,
                              "released_after": new_released,
                              "worklist_index": row["index"],
                              "tagged_records": end["enemy_records"]}
                if any(item.get("count") == new_count for item in self.count_transitions):
                    raise ObserverError(f"duplicate count-{new_count} transition")
                if new_count <= 3 and old_count != new_count - 1:
                    raise ObserverError("required enemy count transition skipped a population")
                self.count_transitions.append(transition)
                self.phase_markers.append({"phase": f"count {old_count}-to-{new_count}",
                                           "marker": "active/released/tagged-record agreement",
                                           "worklist_index": row["index"]})
                if new_count <= 3:
                    if new_count != self.release_target:
                        raise ObserverError(
                            f"natural release order skipped target {self.release_target}: observed {new_count}"
                        )
                    self.release_target = new_count + 1
                if new_count in (1, 2):
                    self.release_deadline = time.monotonic() + self.phase_seconds
                    self.current_phase = f"count {new_count}-to-{new_count + 1}"
                elif new_count == 3:
                    self.release_deadline = None
                    self.current_phase = "three-enemy recurrence"
            elif new_count > 4:
                raise ObserverError(f"enemy population exceeds four records: {new_count}")
        if new_count < 3:
            if self.release_deadline is not None and time.monotonic() > self.release_deadline:
                raise ObserverError(
                    f"ordinary count {self.release_target - 1}-to-{self.release_target} release deadline expired"
                )
            return
        if self.recurring_deadline is not None and time.monotonic() > self.recurring_deadline:
            raise ObserverError("three-enemy recurrence deadline expired; required edges absent")
        if start["enemy_active"] == 4 and end["enemy_active"] == 4:
            self.four_enemy_run.append(row["index"])
        elif new_count != 4:
            self.four_enemy_run.clear()
        if new_count != 3 or start["enemy_active"] != 3:
            if new_count == 4:
                return
            self.regular_run.clear()
            self.last_recurrence_snapshot = end
            return
        if start["classification"] != "regular_controllable" or end["classification"] != "regular_controllable":
            # The value-sprite pause and entry/death paths are retained in the
            # ledger but do not count as regular controllable recurrence.
            self.regular_run.clear()
            self.last_recurrence_snapshot = end
            return
        self.regular_run.append(row)
        prior = self.last_recurrence_snapshot
        if prior is not None:
            if prior["sim_time"] != end["sim_time"]:
                self.sim_advances += 1
            if (prior["enemy_timer"] != end["enemy_timer"]
                    or prior["enemy_anim"] != end["enemy_anim"]):
                self.timer_edges += 1
        self.last_recurrence_snapshot = end

    def _observe_front(self, row: dict[str, Any]) -> None:
        if self.previous_front_state is None:
            self.previous_front_state = row["end"]
            return
        previous = self.previous_front_state
        current = row["end"]
        if current["fb_commit_seq"] != previous["fb_commit_seq"]:
            pixel = verify_front(self.monitor, current, previous)
            if pixel is not None:
                self.phase_markers.append({"phase": self.current_phase,
                                           "marker": "actual FRONT publication",
                                           "worklist_index": row["index"],
                                           "commit_seq": current["fb_commit_seq"]})
                if self.initial_front is None and not self.entry_gate:
                    self.initial_front = pixel
                if self.input_response and self.input_front is None:
                    before = self.initial_front or {}
                    try:
                        validate_front_witness(before, pixel)
                    except ObserverError:
                        pass
                    else:
                        self.input_front = pixel
        self.previous_front_state = current

    def _audio_terminal_ready(self, state: dict[str, Any]) -> bool:
        if not state.get("audio") or not state.get("audio_module_qualified"):
            return False
        self._current_audio(state)
        return (self.cue6_terminal_seen and self.cue6_transition_seen
                and self.cue6_mute_seen and state["audio"]["published_busy"] == 0)

    def _read_menu_symbols(self) -> dict[str, int]:
        symbols = self.artifacts["maps"]["presentation"]
        wanted = ("PRESENTATION_MAP_ATTRACT", "PRESENTATION_MAP_HIGH_SCORE",
                  "PRESENTATION_MAP_LEVEL_START")
        missing = [name for name in wanted if name.casefold() not in symbols]
        if missing:
            raise ObserverError(f"presentation map lacks natural-menu identities: {missing}")
        return {name: symbols[name.casefold()] for name in wanted}

    def run(self) -> dict[str, Any]:
        symbols = self._read_menu_symbols()
        cold_deadline = self.phase_deadline("cold boot and first control")
        self.monitor.set_breakpoint(PRESENTATION_FLOW_TICK)
        first_ui: dict[str, Any] | None = None
        coin_press: dict[str, Any] | None = None
        coin_release_done = False
        enter_press: dict[str, Any] | None = None
        enter_release_done = False
        credit_before = 0
        enter_event_seen = False
        driver_ready = False

        while not self.entry_gate:
            stop, state = self._next_input_boundary(cold_deadline)
            self._current_audio(state)
            if first_ui is None:
                first_ui = state
                self.entry_commit = state["fb_commit_seq"]
                self.phase_markers.append({
                    "phase": "cold boot and first control",
                    "marker": "source/artifact/physical/live-qualified presentation_flow_tick $1900",
                    "event_ticks": stop["event_ticks"],
                    "mode": state["pres_mode"], "screen": state["pres_screen"],
                    "breakpoint_id": stop["bp_id"],
                    "presentation_qualification": state["presentation_qualification"],
                })

            injected = False
            if (coin_press is None and state["pres_mode"] == 2
                    and state["pres_screen"] == symbols["PRESENTATION_MAP_ATTRACT"]):
                credit_before = state["pres_credits"]
                self._inject_at_boundary(stop, self.keycodes["Coin"], "press", "coin")
                coin_press = {"ticks": stop["event_ticks"], "credits": credit_before}
                injected = True
            elif coin_press is not None and not coin_release_done:
                self._inject_at_boundary(stop, self.keycodes["Coin"], "release", "coin")
                coin_release_done = True
                injected = True

            if not injected and (coin_release_done and state["pres_credits"] > credit_before
                    and state["pres_screen"] == symbols["PRESENTATION_MAP_HIGH_SCORE"]
                    and state["pres_mode"] == 5 and enter_press is None):
                qualify_audio_module(self.monitor, self.artifacts)
                if self.monitor._watch_id is None:
                    self.monitor.set_audio_watchpoint()
                self._inject_at_boundary(stop, self.keycodes["Enter"], "press", "enter")
                enter_press = {"ticks": stop["event_ticks"], "state": state,
                               "event_before": state["pres_event"]}
                injected = True
            elif not injected and enter_press is not None and not enter_release_done:
                self._inject_at_boundary(stop, self.keycodes["Enter"], "release", "enter")
                enter_release_done = True
                injected = True

            if enter_press is not None:
                if (state["pres_event"] & 1 or state["pres_mode"] == 6
                        or (state["pres_mode"] == 0 and state["pres_context"] == 1)):
                    enter_event_seen = True
            if state["pres_mode"] == 0:
                driver_ready = qualify_active_driver_safe(self.monitor, self.artifacts)

            if (driver_ready and enter_event_seen
                    and state["pres_mode"] == 0 and state["pres_screen"] == 2
                    and state["pres_context"] == 1 and state["entry"] == 0
                    and state["death"] == 0 and self._audio_terminal_ready(state)
                    and state["fb_pending"] == 0 and self.entry_commit is not None
                    and state["fb_commit_seq"] != self.entry_commit):
                front = verify_front(self.monitor, state, None)
                if front is not None:
                    self.entry_gate = True
                    self.initial_front = front
                    self.previous_front_state = state
                    self.phase_markers.append({
                        "phase": "cold boot and first control",
                        "marker": "entry0, cue6 terminal/mute/busy0, and actual post-entry FRONT publication",
                        "event_ticks": stop["event_ticks"],
                        "commit_seq": state["fb_commit_seq"],
                        "surface_sha256": front["surface_sha256"],
                    })

            if not self.entry_gate:
                self._leave_input_boundary()

        # The accepted-movement discriminator is part of the same 45-second
        # cold/control phase. Only source-derived bindings are available here.
        baseline = state
        movement_index = 0
        movement_name = "Up"
        movement_key = self.keycodes[movement_name]
        movement_target = DIRECTION_VALUES[movement_index]
        movement_before = baseline
        self.capture_worklists = True
        if ACTIVE_ENTRY not in self.monitor._bps:
            self.monitor.set_breakpoint(ACTIVE_ENTRY)
        self._inject_at_boundary(stop, movement_key, "press", movement_name)
        self.input_key = movement_key
        self.input_events[-1].update({
            "baseline_cell": baseline["player_cell"],
            "direction_value": movement_target,
        })
        self._leave_input_boundary()

        movement_released = False
        self.release_target = 1
        self.release_deadline = time.monotonic() + self.phase_seconds
        self.current_phase = "count 0-to-1"
        while True:
            if self.recurring_deadline is not None:
                wait_deadline = self.recurring_deadline
            elif self.release_deadline is not None:
                wait_deadline = self.release_deadline
            else:
                wait_deadline = cold_deadline
            stop, state = self._next_input_boundary(wait_deadline)
            self._current_audio(state)

            if not movement_released:
                changed = (state["player_cell"] != movement_before["player_cell"]
                           or state["player_step"] != movement_before["player_step"])
                target_state = (state["player_dir"] == movement_target
                                or state["player_want"] == movement_target
                                or state["joy_dir"] == movement_target)
                if changed and target_state:
                    self.input_accepted = True
                    self.input_response = True
                    self.phase_markers.append({
                        "phase": "accepted movement",
                        "marker": "source-derived game input state plus natural cell/step response",
                        "worklist_index": len(self.records) - 1,
                        "cell": state["player_cell"], "step": state["player_step"],
                        "player_dir": state["player_dir"],
                        "player_want": state["player_want"],
                        "joy_dir": state["joy_dir"],
                    })
                    self._inject_at_boundary(stop, movement_key, "release", movement_name)
                    movement_released = True
                    self.current_phase = "count 0-to-1"

            active = state["enemy_active"]
            if state["death"] != 0 and active < 3:
                raise ObserverError("death preceded mandatory natural three-enemy release")
            if (self.release_deadline is not None and active < self.release_target
                    and time.monotonic() > self.release_deadline):
                raise ObserverError(
                    f"required ordinary count {self.release_target - 1}-to-{self.release_target} release absent by 45 seconds"
                )

            required_complete = False
            try:
                validate_required_coverage(
                    self.count_transitions, self.regular_run,
                    self.sim_advances, self.timer_edges,
                    movement_released and self.input_response, self.input_front,
                )
                required_complete = True
            except ObserverError:
                pass
            optional_four_pending = (
                any(row.get("count") == 4 for row in self.count_transitions)
                and len(self.four_enemy_run) < 3
                and self.recurring_deadline is not None
                and time.monotonic() < self.recurring_deadline
            )
            if required_complete and not optional_four_pending:
                self.status = "coverage-ready"
                break
            if self.recurring_deadline is not None and time.monotonic() > self.recurring_deadline:
                if not required_complete:
                    raise ObserverError("required three-enemy recurrence, input, or FRONT witness absent by 45 seconds")
                # The required scenario passed; an optional fourth-enemy
                # sequence that did not fit is retained as partial evidence.
                self.status = "coverage-ready"
                break
            self._leave_input_boundary()

        if self.status != "coverage-ready":
            raise ObserverError("required natural three-enemy coverage incomplete")
        if not self.cue6_terminal_seen or not self.cue6_transition_seen or not self.cue6_mute_seen:
            raise ObserverError("cue-6 terminal, completion, or actual mute evidence is missing")
        if (not self.regular_run or len(self.regular_run) < 3
                or self.sim_advances < 2 or self.timer_edges < 2
                or self.input_front is None):
            raise ObserverError("required three-enemy natural recurrence/input/FRONT coverage is incomplete")
        if self.monitor._held_keys or self.monitor._input_open:
            raise ObserverError("successful capture ended with an outstanding input pulse")
        for address in tuple(self.monitor._bps):
            self.monitor.clear_breakpoint(address)
        if self.monitor._watch_id is not None:
            self.monitor.clear_audio_watchpoint()
        return self.receipt()

def qualify_active_driver_safe(monitor: GuardedMonitor,
                               artifacts: dict[str, Any]) -> bool:
    try:
        qualify_active_driver(monitor, artifacts)
        return True
    except ObserverError as exc:
        # Before the first mode-0 install, the destination is not yet owned.
        # AD_MODE_BYTE distinguishes that startup window from damaged live code.
        if "active-driver staged/physical/live" in str(exc):
            mode_page = require_contract_identity(artifacts)["symbols"]["copied_adaptive"]["mode_page"]
            mode = monitor.read(physical_address(mode_page, AD_MODE_BYTE), 1,
                                "physical")[0]
            if mode == 0xFF:
                return False
        raise


def xroar_fingerprint(binary: Path) -> dict[str, Any]:
    import subprocess

    require_path(binary, "XRoar executable")
    version = subprocess.run(
        [str(binary), "--version"], capture_output=True, text=True,
        timeout=3, check=False,
    )
    output = (version.stdout + version.stderr).strip()
    if version.returncode != 0 or not output:
        raise ObserverError(f"could not obtain XRoar version from {binary}")
    return {"path": str(binary.resolve()), "sha256": file_digest(binary),
            "version_command": "--version", "reported_version": output,
            "monitor_mode": "private JSON-RPC, current source implementation; events.subscribe bp plus wait_for_stop"}


def validate_requested_paths(args: argparse.Namespace,
                             require_output: bool = False) -> None:
    expected = {
        "rom": (ROOT / "build/ladybug.rom").resolve(),
        "receipt": (ROOT / "build/source-build-receipt.json").resolve(),
    }
    if require_output:
        expected["output"] = (ROOT / "repro/bug058-diagnosis-assignment-20261013/natural-three-enemy-summary.json").resolve()
    for name, target in expected.items():
        if repo_path(getattr(args, name)).resolve() != target:
            raise ObserverError(f"--{name} must name the approved {target.relative_to(ROOT.resolve()).as_posix()} path")


def run_natural(args: argparse.Namespace) -> dict[str, Any]:
    # Fail closed before importing any launcher or opening any endpoint.
    validate_requested_paths(args, require_output=True)
    if repo_path(args.output).exists():
        raise ObserverError(f"natural-capture output already exists and will not be overwritten: {args.output}")
    artifacts = validate_artifact_layout()
    binary = repo_path(args.xroar)
    xroar_info = xroar_fingerprint(binary)
    monitor_module, launcher_module = _runtime_imports()
    process = None
    client = None
    output = repo_path(args.output)
    capture: NaturalCapture | None = None
    try:
        process, raw_client = launcher_module.launch_fast(
            monitor_module, binary, repo_path(args.rom)
        )
        client = raw_client
        guarded = GuardedMonitor(client)
        capture = NaturalCapture(
            guarded, artifacts, output, args.phase_deadline_seconds,
            args.stop_timeout_seconds, xroar_info,
        )
        capture.run()
    except Exception as exc:
        if capture is not None:
            capture.status = "incomplete"
            try:
                capture.save_partial(str(exc))
            except Exception:
                pass
        raise
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
        if process is not None:
            try:
                monitor_module.stop(process)
            except Exception:
                pass
    if capture is None:
        raise ObserverError("natural capture did not initialize")
    try:
        pins_after = checked_pins()
        require_byte_identity(
            "artifact pins before/after capture",
            json.dumps(artifacts["pins"], sort_keys=True).encode(),
            json.dumps(pins_after, sort_keys=True).encode(),
        )
    except Exception as exc:
        capture.status = "incomplete"
        capture.pins_after = None
        capture.save_partial(str(exc))
        raise
    capture.pins_after = pins_after
    capture.save_partial()
    return capture.receipt()


def self_test() -> None:
    spec = contract()
    artifacts = validate_artifact_layout()
    assert ACTIVE_AUDIO_ENTRY == 0x047C
    assert ACTIVE_AUDIO_VECTOR == 0x039B and ACTIVE_AUDIO_VECTOR not in BREAKPOINTS
    assert ACTIVE_AUDIO_RETURN in BREAKPOINTS
    assert spec["baseline"]["target_fast_cpu_cycles"] == EXPECTED_FAST_CYCLES
    assert spec["capture"]["deadline_seconds_per_phase"] == 45
    assert spec["capture"]["maximum_wait_for_stop_seconds"] == 10
    validate_api_stack(0x1000, 0x1000)
    validate_api_return(0x1000, 0x1000, 0x03A5, 0x03A5)
    assert [matrix_to_dscan(value) for value in MATRIX_DEFAULTS] == [43, 44, 45, 46, 48]
    assert matrix_to_dscan(KB_FIXED_COIN_MATRIX) == 5
    assert event_cycles(0xFFFFFFFFFFFFFFF0, 0x08) == 3
    assert classify_pause(0, 0, 1, 0) == "intentional_collectible_pause"
    assert classify_pause(0, 0, 0, 5) == "regular_controllable"
    validate_phase_limits(45, 10)
    valid_records = bytes([0x11, 0x57, 0xEC, 0, 12, 12, 0, 0,
                           0x21, 0x57, 0xEC, 0, 13, 12, 0, 0,
                           0x31, 0x57, 0xEC, 0, 14, 12, 0, 0,
                           0, 0, 0, 0, 0, 0, 0, 0])
    assert len(validate_enemy_records(3, valid_records)) == 3
    assert validate_reconciliation(100, [(10, 25), (40, 65)]) == 60
    assert decode_call_target(bytes.fromhex("8d5e00"), 0x0440) == (0x049E, 2)
    assert writer_category(0xA46D, 0x9F) == "tone_attenuation"

    transitions = [{"from": count - 1, "count": count} for count in (1, 2, 3)]
    worklists = [{
        "index": index,
        "start": {"enemy_active": 3, "classification": "regular_controllable"},
        "end": {"enemy_active": 3, "classification": "regular_controllable"},
        "accounting": {"reconciles": True},
    } for index in range(10, 13)]
    front_before = {"surface_sha256": "00", "actor_windows": {
        "player": {"pointer": 0x2100, "sha256": "aa"}}}
    front_after = {"surface_sha256": "11", "actor_windows": {
        "player": {"pointer": 0x2110, "sha256": "aa"}}}
    validate_required_coverage(transitions, worklists, 2, 2, True, front_after)
    validate_front_witness(front_before, front_after)

    class FakeClient:
        def __init__(self):
            self.calls: list[tuple[str, dict[str, Any] | None, float]] = []
            self.breakpoints: list[dict[str, int]] = []
            self.watchpoints: list[dict[str, Any]] = []
            self.next_id = 1
            self.ticks = 0
            self.halted = True
            self.unstable_halt = False
            self.matrix = bytes(MATRIX_DEFAULTS)
            self.inputs: list[tuple[int, str]] = []

        def call(self, method: str, params: dict[str, Any] | None = None,
                 timeout: float = MAX_STOP_SECONDS) -> dict[str, Any]:
            self.calls.append((method, params, timeout))
            params = params or {}
            if method == "set_breakpoint":
                row = {"id": self.next_id, "addr": params["addr"]}
                self.next_id += 1
                self.breakpoints.append(row)
                return {"id": row["id"], "addr": row["addr"]}
            if method == "clear_breakpoint":
                self.breakpoints = [row for row in self.breakpoints
                                    if row["id"] != params["id"]]
                return {"ok": True}
            if method == "list_breakpoints":
                return {"breakpoints": list(self.breakpoints)}
            if method == "set_watchpoint":
                row = {"id": self.next_id, **params}
                self.next_id += 1
                self.watchpoints.append(row)
                return {"id": row["id"]}
            if method == "clear_watchpoint":
                self.watchpoints = [row for row in self.watchpoints
                                    if row["id"] != params["id"]]
                return {"ok": True}
            if method == "list_watchpoints":
                return {"watchpoints": list(self.watchpoints)}
            if method == "inject_key":
                self.inputs.append((params["key"], params["action"]))
                return {"ok": True}
            if method == "read_memory":
                if params["addr"] == KB_BIND and params["length"] == 5:
                    return {"data": self.matrix.hex()}
                return {"data": bytes(params["length"]).hex()}
            if method == "read_cycles":
                value = self.ticks
                if self.unstable_halt and self.halted:
                    self.ticks += 1
                return {"event_ticks": value}
            if method == "run":
                self.ticks += 8
                self.halted = False
                return {"ok": True}
            if method == "wait_for_stop":
                self.halted = True
                ident = self.breakpoints[0]["id"] if self.breakpoints else None
                address = self.breakpoints[0]["addr"] if self.breakpoints else -1
                return {"reason": "breakpoint", "pc": address, "bp_id": ident}
            if method == "read_registers":
                return {"pc": self.breakpoints[0]["addr"] if self.breakpoints else 0}
            raise AssertionError(f"fake client received forbidden/unexpected method: {method}")

    class FakeArtifactMemory:
        def __init__(self, qualified_artifacts: dict[str, Any]):
            self.artifacts = qualified_artifacts
            self.presentation = qualified_artifacts["blobs"]["presentation"]
            self.active = qualified_artifacts["blobs"]["active"]
            self.audio = qualified_artifacts["blobs"]["audio"]
            self.par0 = 0x38
            self.par5 = 0xFD
            self.runtime_rom = qualified_artifacts["blobs"]["runtime_rom"]
            self.audio_installed = 1
            self.mode_byte = 0xFF
            self.corrupt_presentation_cpu = False
            self.corrupt_presentation_physical = False
            self.corrupt_active_destination = False
            self.corrupt_active_cpu = False
            self.corrupt_audio_immutable = False
            self.corrupt_audio_api_physical = False
            self.corrupt_audio_api_cpu = False
            self.corrupt_gateway = False
            self.corrupt_psg_cpu = False
            self.corrupt_psg_callsite = False
            self.stack_return = 0xA46D
            self.stack_private_address = 0x0FFE
            self.stack_private_byte = 1
            self._watch_id = 9
            self.watchpoints = [(9, PSG_DATA, 1, "w")]

        def byte(self, address: int) -> int:
            if address == PAR0:
                return self.par0
            if address == PAR5:
                return self.par5
            if address == AUDIO_INSTALLED:
                return self.audio_installed
            if address == self.stack_private_address:
                return self.stack_private_byte
            raise AssertionError(f"unexpected fake byte read ${address:04X}")

        def word(self, address: int, space: str = "cpu") -> int:
            return self.stack_return

        def _assert_watchpoint(self) -> None:
            expected = [(self._watch_id, PSG_DATA, 1, "w")]
            if self.watchpoints != expected:
                raise ObserverError(f"fake watchpoint inventory differs: {self.watchpoints}")

        def read(self, address: int, length: int = 1, space: str = "cpu") -> bytes:
            segments: list[tuple[int, bytes, str]]
            if space == "cpu":
                segments = [
                    (PRESENTATION_FLOW_TICK, self.presentation, "presentation"),
                    (ACTIVE_ENTRY, self.active, "active"),
                    (0x02DE, self.audio[0x2D7:0x2D7 + 18], "gateway"),
                    (0xA000, self.audio, "audio_cpu"),
                    (0xC000, self.runtime_rom, "runtime_rom"),
                ]
            else:
                segments = [
                    (56 * PAGE_SIZE + PRESENTATION_FLOW_TICK, self.presentation, "presentation_physical"),
                    (56 * PAGE_SIZE + ACTIVE_ENTRY, self.active, "active_destination"),
                    (physical_address(PAGE_GAME, AD_MODE_BYTE), bytes([self.mode_byte]), "mode_byte"),
                    (PAGE_AUDIO * PAGE_SIZE, self.audio, "audio_physical"),
                ]
            for base, data, label in segments:
                if base <= address and address + length <= base + len(data):
                    result = data[address - base:address - base + length]
                    corrupt = ((label == "presentation" and self.corrupt_presentation_cpu)
                               or (label == "presentation_physical" and self.corrupt_presentation_physical)
                               or (label == "active_destination" and self.corrupt_active_destination)
                               or (label == "active" and self.corrupt_active_cpu)
                               or (label == "audio_physical" and self.corrupt_audio_immutable
                                   and address == PAGE_AUDIO * PAGE_SIZE)
                               or (label == "audio_physical" and self.corrupt_audio_api_physical
                                   and address == PAGE_AUDIO * PAGE_SIZE + 0xB638 - CPU_BANK_START)
                               or (label == "audio_cpu" and self.corrupt_audio_api_cpu
                                   and address == 0xB638)
                               or (label == "gateway" and self.corrupt_gateway)
                               or (label == "audio_cpu" and self.corrupt_psg_cpu
                                   and address == 0xA499)
                               or (label == "audio_physical" and self.corrupt_psg_callsite
                                   and address == physical_address(PAGE_AUDIO, 0xA46B)))
                    return bytes([result[0] ^ 1]) + result[1:] if corrupt else result
            raise AssertionError(f"unexpected fake {space} read {address:#x}+{length}")

    rejected = 0

    def rejects(function: Any, *values: Any) -> None:
        nonlocal rejected
        try:
            function(*values)
        except (ObserverError, ValueError):
            rejected += 1
        else:
            raise AssertionError(f"negative self-test unexpectedly passed: {function.__name__}")

    rejects(matrix_to_dscan, 7)
    rejects(matrix_to_dscan, 64)
    rejects(event_cycles, 0, 3)
    rejects(event_cycles, -1, 8)
    rejects(validate_api_stack, 0x1000, 0x1002)
    rejects(validate_api_stack, -1, 0xFFFF)
    rejects(validate_api_return, 0x1000, 0x1002, 0x03A5, 0x03A5)
    rejects(validate_api_return, 0x1000, 0x1000, 0x03A5, 0x03A8)
    rejects(validate_api_return, 0x1000, 0x1000, -1, 0x03A5)
    rejects(physical_address, 64, 0xA000)
    rejects(require_hash_match, "source", "abc", "def")
    rejects(require_byte_identity, "staged/live", b"a", b"b")
    rejects(require_page_owner, "PAR0", 5, 56)
    rejects(validate_phase_limits, 45.1, 10)
    rejects(validate_phase_limits, 45, 10.1)
    rejects(validate_enemy_records, 2, valid_records)
    rejects(validate_enemy_records, 3, bytes([0x12]) + valid_records[1:])
    rejects(validate_enemy_records, 3, valid_records[:7] + bytes([4]) + valid_records[8:])
    rejects(validate_enemy_records, 3, valid_records[:4] + bytes([24]) + valid_records[5:])
    rejects(validate_reconciliation, 10, [(0, 7), (6, 12)])
    rejects(validate_reconciliation, 5, [(0, 7)])
    rejects(writer_category, 0xA46D, 0x87)
    rejects(writer_category, 0xA400, 0x9F)
    rejects(_assert_stop, {"pc": PRESENTATION_FLOW_TICK, "bp_id": 8}, PRESENTATION_FLOW_TICK, 9)
    rejects(_assert_stop, {"pc": ACTIVE_RETURN, "bp_id": 9}, PRESENTATION_FLOW_TICK, 9)
    rejects(validate_front_witness, front_before, front_before)
    rejects(validate_front_witness, front_before, None)
    rejects(validate_required_coverage, transitions[:-1], worklists, 2, 2, True, front_after)
    rejects(validate_required_coverage, transitions + [transitions[0]], worklists, 2, 2, True, front_after)
    rejects(validate_required_coverage, transitions, worklists[:2], 2, 2, True, front_after)
    rejects(validate_required_coverage, transitions, worklists, 1, 2, True, front_after)
    rejects(validate_required_coverage, transitions, worklists, 2, 2, False, front_after)
    rejects(validate_required_coverage, transitions, worklists, 2, 2, True, None)

    # Exact source/staged/physical/live mapping checks operate on synthetic
    # memory only; no emulator process or monitor endpoint exists in this test.
    memory = FakeArtifactMemory(artifacts)
    proof = qualify_presentation_boundary(memory, artifacts)
    assert proof["physical_page"] == 56 and proof["bytes"] == 1259
    wrong_map_artifacts = {**artifacts, "maps": dict(artifacts["maps"])}
    wrong_presentation_map = dict(artifacts["maps"]["presentation"])
    wrong_presentation_map["presentation_flow_tick"] = PRESENTATION_FLOW_TICK + 1
    wrong_map_artifacts["maps"]["presentation"] = wrong_presentation_map
    rejects(qualify_presentation_boundary, memory, wrong_map_artifacts)
    qualify_active_driver(memory, artifacts)
    assert qualify_active_driver_safe(memory, artifacts)
    qualify_audio_module(memory, artifacts)
    memory.par5 = 0xF4
    memory.stack_return = MAIN_WORKLIST_RETURN
    assert qualify_worklist_outer_return(memory, artifacts, 0x1000) == MAIN_WORKLIST_RETURN
    memory.stack_return = 0xC153
    rejects(qualify_worklist_outer_return, memory, artifacts, 0x1000)
    worklist_owner = {"entry_stack": 0x1000}
    memory.stack_return = 0x03A5
    direct_caller = qualify_audio_api_call(
        memory, artifacts, {"s": 0x0FFE, "a": 0}, worklist_owner,
    )
    assert direct_caller["kind"] == "direct_jsr"
    assert direct_caller["module"] == "adaptive_work"
    assert direct_caller["call_start"] == 0x03A2
    assert direct_caller["action"] == 0
    for call_start, expected in ACTIVE_AUDIO_DIRECT_CALLS.items():
        memory.stack_return = call_start + 3
        qualified = qualify_audio_api_call(
            memory, artifacts,
            {"s": 0x0FFE if expected["caller"] == "adaptive_work" else 0x0FFC,
             "a": expected["action"]}, worklist_owner,
        )
        assert qualified["kind"] == "direct_jsr"
        assert qualified["call_start"] == call_start
        assert qualified["module"] == expected["caller"]
        assert qualified["action"] == expected["action"]
    memory.stack_return = 0x03A5
    rejects(qualify_audio_api_call, memory, artifacts,
            {"s": 0x0FFE, "a": 1}, worklist_owner)
    memory.stack_return = 0x0518
    tick_caller = qualify_audio_api_call(
        memory, artifacts, {"s": 0x0FFC, "a": 1}, worklist_owner,
    )
    assert tick_caller["module"] == "adaptive_tick_binding"
    assert tick_caller["caller_stack"]["private_saved_a"] == 1
    memory.stack_return = MAIN_WORKLIST_RETURN
    tail_caller = qualify_audio_api_call(
        memory, artifacts, {"s": 0x1000, "a": 2}, worklist_owner,
    )
    assert tail_caller["kind"] == "tail_aw_output"
    assert tail_caller["outer_return_pc"] == MAIN_WORKLIST_RETURN
    rejects(qualify_audio_api_call, memory, artifacts,
            {"s": 0x1000, "a": 1}, worklist_owner)
    rejects(qualify_audio_api_call, memory, artifacts,
            {"s": 0x1002, "a": 2}, worklist_owner)
    memory.stack_return = 0x0430
    rejects(qualify_audio_api_call, memory, artifacts,
            {"s": 0x0FFE, "a": 2}, worklist_owner)
    api_physical = qualify_audio_api_physical(memory, artifacts)
    assert api_physical["bytes"] == 341 and api_physical["start"] == 0xB638
    memory.par5 = 0xFD
    api_live = qualify_audio_api_live(memory, artifacts)
    assert api_live["par5"] == PAGE_AUDIO
    memory.corrupt_audio_api_cpu = True
    rejects(qualify_audio_api_live, memory, artifacts)
    memory.corrupt_audio_api_cpu = False
    memory.corrupt_audio_api_physical = True
    rejects(qualify_audio_api_physical, memory, artifacts)
    memory.corrupt_audio_api_physical = False
    memory.corrupt_active_cpu = True
    memory.stack_return = 0x03A5
    rejects(qualify_audio_api_call, memory, artifacts,
            {"s": 0x0FFE, "a": 0}, worklist_owner)
    memory.corrupt_active_cpu = False
    memory.par5 = 0xFD
    memory.stack_return = 0xA46D
    psg_stop = {"pc": PSG_POST_STORE, "bp_id": None, "event_ticks": 16,
                "registers": {"pc": PSG_POST_STORE, "s": 0x1000, "a": 0x9F},
                "result": {"reason": "breakpoint"}}
    assert qualify_psg_stop(memory, artifacts, psg_stop)["category"] == "tone_attenuation"
    memory.par5 = 0xFC
    rejects(qualify_psg_stop, memory, artifacts, psg_stop)
    memory.par5 = 0xFD
    wrong_pc = dict(psg_stop, pc=PSG_POST_STORE + 1)
    rejects(qualify_psg_stop, memory, artifacts, wrong_pc)
    memory.stack_return = 0xA400
    rejects(qualify_psg_stop, memory, artifacts, psg_stop)
    memory.stack_return = 0xA46D
    memory.corrupt_psg_callsite = True
    rejects(qualify_psg_stop, memory, artifacts, psg_stop)
    memory.corrupt_psg_callsite = False
    memory.corrupt_psg_cpu = True
    rejects(qualify_psg_stop, memory, artifacts, psg_stop)
    memory.corrupt_psg_cpu = False
    memory.watchpoints.append((10, PSG_DATA, 1, "w"))
    rejects(qualify_psg_stop, memory, artifacts, psg_stop)
    memory.watchpoints = [(9, PSG_DATA, 1, "w")]
    memory.par0 = 0x39
    rejects(qualify_presentation_boundary, memory, artifacts)
    memory.par0 = 0x38
    memory.corrupt_presentation_cpu = True
    rejects(qualify_presentation_boundary, memory, artifacts)
    memory.corrupt_presentation_cpu = False
    memory.corrupt_presentation_physical = True
    rejects(qualify_presentation_boundary, memory, artifacts)
    memory.corrupt_presentation_physical = False
    memory.corrupt_active_destination = True
    assert not qualify_active_driver_safe(memory, artifacts)
    memory.mode_byte = 0
    rejects(qualify_active_driver_safe, memory, artifacts)
    memory.mode_byte = 0xFF
    rejects(qualify_active_driver, memory, artifacts)
    memory.corrupt_active_destination = False
    memory.corrupt_audio_immutable = True
    rejects(qualify_audio_module, memory, artifacts)
    memory.corrupt_audio_immutable = False
    memory.corrupt_gateway = True
    rejects(qualify_audio_module, memory, artifacts)

    client = FakeClient()
    guard = GuardedMonitor(client)
    assert live_keycodes(guard) == {
        **expected_keycodes(), "matrix_slots": list(MATRIX_DEFAULTS),
    }
    client.matrix = bytes([27, 27, 43, 51, 6])
    rejects(live_keycodes, guard)
    client.matrix = bytes([27, 35, 43, 51, 7])
    rejects(live_keycodes, guard)
    client.matrix = bytes(MATRIX_DEFAULTS)
    guard.configure_input_keys(expected_keycodes())
    bpid = guard.set_breakpoint(PRESENTATION_FLOW_TICK)
    boundary = {"pc": PRESENTATION_FLOW_TICK, "bp_id": bpid}
    rejects(guard.open_input_boundary, {"pc": STARTUP_KEY_INIT, "bp_id": bpid}, True)
    rejects(guard.open_input_boundary, {"pc": PRESENTATION_FLOW_TICK, "bp_id": bpid + 1}, True)
    guard.open_input_boundary(boundary, True)
    rejects(guard.inject, 5, "release")
    guard.inject(5, "press")
    rejects(guard.inject, 5, "press")
    rejects(guard.inject, 0xA9, "press")
    rejects(guard.inject, 63, "press")
    rejects(guard.inject, 5, "down")
    guard.close_input_boundary()
    guard.configure_input_keys(expected_keycodes())
    guard.open_input_boundary(boundary, True)
    guard.inject(5, "release")
    guard.close_input_boundary()
    assert client.inputs == [(5, "press"), (5, "release")]
    assert all(method in MONITOR_METHODS for method, _, _ in client.calls)
    rejects(guard._call, "write_memory")
    rejects(guard._call, "write_registers")
    rejects(guard._call, "step_instruction")
    rejects(guard._call, "set_pc")
    rejects(guard._call, "call")
    rejects(guard._call, "wait_for_stop", {"timeout_ms": 10001}, 10)
    watched = guard.set_audio_watchpoint()
    assert watched > 0
    rejects(guard.set_audio_watchpoint)
    guard.clear_audio_watchpoint()
    assert client.watchpoints == []
    stopped = guard.stop(time.monotonic() + 2, "offline fake stop")
    _assert_stop(stopped, PRESENTATION_FLOW_TICK, bpid)
    assert stopped["trace"]["event_ticks_after_stop"] == stopped["trace"]["event_ticks_halted_check"]
    client.unstable_halt = True
    rejects(guard.stop, time.monotonic() + 2, "unstable fake stop")

    # Import in a fresh namespace while socket/process imports are forbidden.
    import builtins
    import importlib.util
    real_import = builtins.__import__

    def offline_import(name: str, globals: Any = None, locals: Any = None,
                       fromlist: Any = (), level: int = 0) -> Any:
        if name.split(".", 1)[0] in {"socket", "subprocess"}:
            raise AssertionError(f"offline import attempted forbidden module: {name}")
        return real_import(name, globals, locals, fromlist, level)

    builtins.__import__ = offline_import
    try:
        import_spec = importlib.util.spec_from_file_location("bug058_offline_import_test", HERE)
        if import_spec is None or import_spec.loader is None:
            raise AssertionError("observer import test could not create a module spec")
        imported = importlib.util.module_from_spec(import_spec)
        import_spec.loader.exec_module(imported)
    finally:
        builtins.__import__ = real_import
    assert not hasattr(imported, "socket") and not hasattr(imported, "subprocess")

    source = HERE.read_text(encoding="utf-8")
    compile(source, str(HERE), "exec", flags=0, dont_inherit=True)
    print(f"BUG058_OBSERVER_SELF_TEST_PASS negatives={rejected} process=0 socket=0 monitor=0 artifact=offline")

def artifact_check(args: argparse.Namespace) -> dict[str, Any]:
    validate_requested_paths(args)
    result = validate_artifact_layout()
    print(json.dumps({
        "status": "artifact-ready",
        "source_revision": "3cba1bfd",
        "receipt_source_revision_metadata": result["receipt_revision_metadata"],
        "pins": result["pins"],
        "keycodes_dscan": result["keycodes"],
        "cue6_terminal_zero_address": result["cue6"]["terminal_zero_address"],
        "processes": 0, "sockets": 0, "monitor_calls": 0,
    }, indent=2))
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--self-test", action="store_true")
    modes.add_argument("--artifact-check", action="store_true")
    modes.add_argument("--natural-gameplay", action="store_true")
    parser.add_argument("--xroar", default="docs/reference/xroar/src/xroar")
    parser.add_argument("--rom", default="build/ladybug.rom")
    parser.add_argument("--receipt", default="build/source-build-receipt.json")
    parser.add_argument("--output", default="repro/bug058-diagnosis-assignment-20261013/natural-three-enemy-summary.json")
    parser.add_argument("--phase-deadline-seconds", type=float, default=45.0)
    parser.add_argument("--stop-timeout-seconds", type=float, default=10.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.self_test:
            self_test()
            return 0
        if args.artifact_check:
            artifact_check(args)
            return 0
        if args.natural_gameplay:
            if args.phase_deadline_seconds != MAX_PHASE_SECONDS:
                raise ObserverError("phase deadline is fixed at 45 seconds")
            if args.stop_timeout_seconds != MAX_STOP_SECONDS:
                raise ObserverError("monitor stop timeout is fixed at 10 seconds")
            result = run_natural(args)
            print(json.dumps({"status": result["status"], "output": str(repo_path(args.output)),
                              "required_count": 3,
                              "worklists": len(result.get("worklists", []))}, indent=2))
            return 0
    except (ObserverError, OSError, ValueError, KeyError, AssertionError) as exc:
        detail = str(exc) or type(exc).__name__
        print(f"BUG058_OBSERVER_FAIL: {detail}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
