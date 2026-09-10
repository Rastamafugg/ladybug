#!/usr/bin/env python3
"""Run RSCH-007 exact-production 6309 copy and worklist controls."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/bench/6309_production_hotpaths.s"
MAIN_SOURCE = ROOT / "src/main.s"
ENEMY_SOURCE = ROOT / "src/enemy_runtime.s"
MAIN_MAP = ROOT / "build/ladybug.map"
ENEMY_MAP = ROOT / "build/ladybug-enemy-runtime.map"
ENEMY_LISTING = ROOT / "build/ladybug-enemy-runtime.lst"
PRESENTATION_MAP = ROOT / "build/ladybug-presentation-runtime.map"
PRESENTATION_IMAGE = ROOT / "build/ladybug-presentation-runtime.bin"
PRESENTATION_LISTING = ROOT / "build/ladybug-presentation-runtime.lst"
BOOT_MAP = ROOT / "build/ladybug-gmc-boot.map"
BOOT_IMAGE = ROOT / "build/ladybug-gmc-boot.rom"
BOOT_LISTING = ROOT / "build/ladybug-gmc-boot.lst"
RUNTIME_IMAGE = ROOT / "build/ladybug-runtime.rom"
ENEMY_IMAGE = ROOT / "build/ladybug-enemy-runtime.rom"
SPARSE_LAYOUT = ROOT / "build/ladybug-sparse-layout.json"
PRODUCTION_ROM = ROOT / "build/ladybug.rom"
ENEMY_TABLE = ROOT / "build/four-enemy-delta-enemy-table.bin"
DEFAULT_XROAR = ROOT / "docs/reference/xroar/src/xroar"

COMPLETE_PROFILE = {
    "BUG011_DEVELOPMENT_PROFILE": 1,
    "COMPLETE_PROFILE": 1,
    "HIGHSCORE_TEST_PROFILE": 0,
}
COMPLETE_BUILD_COMMAND = (
    "LADYBUG_PROFILE=complete scripts/build.sh build"
)
PRESENTATION_STATE = {
    "pres_magic": 0x00A4,
    "pres_mode": 0x00A5,
    "pres_screen": 0x00A6,
    "pres_context": 0x00A7,
    "pres_credits": 0x00A8,
    "pres_event": 0x00A9,
}

RESULT_BASE = 0x0200
RESULT_Q = RESULT_BASE + 6
SIGNATURE = b"R7PH"
FB_BACK = 0x2008
FB_FRONT = 0x5008
PLAYER_BG = 0xA300
RING_DATA = 0xA690
FB_SPAN = 15 * 160 + 8
LINEAR_BYTES = 128
FRONT_FAULT = 0x0099
RAM_RING = 0xA898
META_A_RING = 0xA92C
META_B_RING = 0xAA2C
TRACE_RE = re.compile(r"^([0-9a-f]{4})\|.* dt=(\d+)$")

CASES = (
    {
        "name": "player_save",
        "define": "BENCH_PLAYER_SAVE",
        "marker": 1,
        "source": "main",
        "source_start": "\nsave_player\n",
        "source_end": "\n;==============================================================================\n; restore_player",
        "variants": ("baseline", "tfm", "q"),
    },
    {
        "name": "player_restore",
        "define": "BENCH_PLAYER_RESTORE",
        "marker": 2,
        "source": "main",
        "source_start": "\nrestore_player\n",
        "source_end": "\n;==============================================================================\n; draw_screen",
        "variants": ("baseline", "tfm", "q"),
    },
    {
        "name": "roam_capture_full",
        "define": "BENCH_ROAM_CAPTURE_FULL",
        "marker": 3,
        "source": "enemy",
        "source_start": "\nroam_copy_fb_to_bg\n",
        "source_end": "\ndraw_enemy_fb\n",
        "variants": ("baseline", "tfm", "q"),
    },
    {
        "name": "roam_restore_phase0",
        "define": "BENCH_ROAM_RESTORE_PHASE0",
        "marker": 4,
        "source": "enemy",
        "source_start": "\nrcbtf_phase0\n",
        "source_end": "\nrcbtf_phase1\n",
        "variants": ("baseline", "tfm", "q"),
    },
    {
        "name": "roam_restore_phase4",
        "define": "BENCH_ROAM_RESTORE_PHASE4",
        "marker": 5,
        "source": "enemy",
        "source_start": "\nrcbtf_phase4\n",
        "source_end": "\nrcbtf_phase5\n",
        "variants": ("baseline", "q"),
    },
    {
        "name": "roam_restore_odd_phase1",
        "define": "BENCH_ROAM_RESTORE_ODD",
        "marker": 6,
        "source": "enemy",
        "source_start": "\nrcbtf_phase1\n",
        "source_end": "\nrcbtf_phase2\n",
        "variants": ("baseline",),
    },
    {
        "name": "roam_restore_split_phase0",
        "define": "BENCH_ROAM_RESTORE_SPLIT",
        "marker": 7,
        "source": "enemy",
        "source_start": "\nrcbtf_ring_setup\n",
        "source_end": "\nrcbtf_ring_done\n",
        "variants": ("baseline", "tfm", "q"),
    },
    {
        "name": "ring_capture_two_rows_phase0",
        "define": "BENCH_RING_CAPTURE_TWO",
        "marker": 8,
        "source": "enemy",
        "source_start": "\nrub_row_loop\n",
        "source_end": "\n        ifeq    PERSISTENT_FB\nroam_set_prepare_union",
        "variants": ("baseline", "tfm", "q"),
    },
)

COMMON_PATCHES = [
    "0030=7F", "0031=FF", "004A=FF", "0050=FF", "0055=40",
    "0058=04", "0059=04", "005A=02", "0060=01", "0061=01",
    "007F=01", "0080=00", "0087=0A", "A908=00", "AA08=00",
    "A92C=00", "A92D=00", "A92E=00", "A92F=00",
    "AA2C=00", "AA2D=00", "AA2E=00", "AA2F=00",
]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json_atomic(path: Path, value: dict) -> None:
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="ascii", newline="\n") as handle:
        json.dump(value, handle, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


class PrimaryBudgetDepleted(TimeoutError):
    pass


def symbols(path: Path) -> dict[str, int]:
    return {
        name: int(value, 16)
        for name, value in re.findall(
            r"^Symbol: (\w+) .* = ([0-9A-Fa-f]+)$",
            path.read_text(encoding="ascii"), re.MULTILINE,
        )
    }


class ProfileMismatch(RuntimeError):
    def __init__(self, evidence: dict):
        self.evidence = evidence
        super().__init__(
            "runtime artifact is not the complete profile: "
            f"presentation={evidence['presentation_profile']}, "
            f"bootstrap={evidence['bootstrap_profile']}; rebuild with "
            f"{COMPLETE_BUILD_COMMAND}"
        )


def read_client_bytes(client, address: int, length: int) -> bytes:
    result = bytearray()
    while len(result) < length:
        count = min(256, length - len(result))
        result.extend(bytes.fromhex(client.call(
            "read_memory", {"addr": address + len(result), "length": count}
        )["data"]))
    return bytes(result)


def reconstruct_manifest_target(rom: bytes, layout: dict, target: str,
                                expected_length: int) -> bytes:
    result = bytearray(expected_length)
    covered = bytearray(expected_length)
    for segment in layout["gmc"]["segments"]:
        if segment["target"] != target:
            continue
        source = segment["bank"] * 0x4000 + segment["source_offset"]
        destination = segment["target_offset"]
        count = segment["count"]
        if destination < 0 or destination + count > expected_length:
            raise RuntimeError(f"{target}: manifest segment exceeds target")
        result[destination:destination + count] = rom[source:source + count]
        covered[destination:destination + count] = b"\x01" * count
    if not all(covered):
        raise RuntimeError(f"{target}: manifest does not cover assembled module")
    return bytes(result)


def production_provenance(xroar: Path) -> dict:
    presentation_symbols = symbols(PRESENTATION_MAP)
    bootstrap_symbols = symbols(BOOT_MAP)
    presentation_profile = {
        name: presentation_symbols.get(name) for name in COMPLETE_PROFILE
    }
    bootstrap_profile = {
        "HIGHSCORE_TEST_PROFILE": bootstrap_symbols.get("HIGHSCORE_TEST_PROFILE")
    }
    profile_ok = (
        presentation_profile == COMPLETE_PROFILE
        and bootstrap_profile["HIGHSCORE_TEST_PROFILE"]
        == COMPLETE_PROFILE["HIGHSCORE_TEST_PROFILE"]
    )
    profile = {
        "required_profile": "complete",
        "required_tuple": COMPLETE_PROFILE,
        "presentation_profile": presentation_profile,
        "bootstrap_profile": bootstrap_profile,
        "maps_agree_on_highscore_test": (
            presentation_profile["HIGHSCORE_TEST_PROFILE"]
            == bootstrap_profile["HIGHSCORE_TEST_PROFILE"]
        ),
        "profile_pass": profile_ok,
        "complete_build_command": COMPLETE_BUILD_COMMAND,
        "xroar_launched": False,
    }
    if not profile_ok:
        raise ProfileMismatch(profile)

    rom = PRODUCTION_ROM.read_bytes()
    presentation = PRESENTATION_IMAGE.read_bytes()
    enemy = ENEMY_IMAGE.read_bytes()
    boot = BOOT_IMAGE.read_bytes()
    runtime = RUNTIME_IMAGE.read_bytes()
    layout_bytes = SPARSE_LAYOUT.read_bytes()
    layout = json.loads(layout_bytes)
    if len(rom) != 0x10000:
        raise RuntimeError(f"production GMC ROM is {len(rom)} bytes, expected 65536")
    staged_presentation = reconstruct_manifest_target(
        rom, layout, "presentation_module", len(presentation)
    )
    staged_enemy = rom[3 * 0x4000 + 0x0800:3 * 0x4000 + 0x0800 + len(enemy)]
    checks = {
        "manifest_final_rom_hash": (
            layout["gmc"]["final_image_sha256"] == digest(rom)
        ),
        "boot_bank_exact": rom[:0x4000] == boot,
        "resident_bank_exact": rom[0x4000:0x8000] == runtime,
        "presentation_staged_exact": staged_presentation == presentation,
        "enemy_staged_exact": staged_enemy == enemy,
    }
    if not all(checks.values()):
        raise RuntimeError(f"production staged identity mismatch: {checks}")
    return {
        **profile,
        "xroar_sha256": digest(xroar.read_bytes()),
        "source_sha256": {
            "main": digest(MAIN_SOURCE.read_bytes()),
            "presentation": digest((ROOT / "src/presentation_runtime.s").read_bytes()),
            "enemy": digest(ENEMY_SOURCE.read_bytes()),
            "bootstrap": digest((ROOT / "src/gmc_bootstrap.s").read_bytes()),
        },
        "artifact_sha256": {
            "production_rom": digest(rom),
            "boot": digest(boot),
            "resident": digest(runtime),
            "presentation": digest(presentation),
            "enemy": digest(enemy),
            "sparse_layout": digest(layout_bytes),
            "main_map": digest(MAIN_MAP.read_bytes()),
            "presentation_map": digest(PRESENTATION_MAP.read_bytes()),
            "presentation_listing": digest(PRESENTATION_LISTING.read_bytes()),
            "enemy_map": digest(ENEMY_MAP.read_bytes()),
            "boot_map": digest(BOOT_MAP.read_bytes()),
            "boot_listing": digest(BOOT_LISTING.read_bytes()),
        },
        "staged_checks": checks,
        "staged_sha256": {
            "presentation": digest(staged_presentation),
            "enemy": digest(staged_enemy),
        },
    }


def start_screen_calls(listing: Path, start_screen: int) -> dict[int, dict]:
    calls = {}
    pattern = re.compile(
        r"^([0-9A-F]{4})\s+([0-9A-F]+)\s+.*\):([0-9]{5})\s+"
        r".*\b(lbsr|bsr)\s+start_screen\b",
        re.IGNORECASE,
    )
    for line in listing.read_text(encoding="ascii").splitlines():
        match = pattern.match(line)
        if not match:
            continue
        address = int(match.group(1), 16)
        instruction = bytes.fromhex(match.group(2))
        return_address = address + len(instruction)
        displacement = int.from_bytes(
            instruction[1:], "big", signed=True
        )
        target = return_address + displacement
        if target != start_screen:
            raise RuntimeError(
                f"listing call at ${address:04X} targets ${target:04X}, "
                f"not start_screen ${start_screen:04X}"
            )
        calls[return_address] = {
            "call_address": f"{address:04X}",
            "return_address": f"{return_address:04X}",
            "source_line": int(match.group(3)),
            "mnemonic": match.group(4).lower(),
            "instruction_bytes": instruction.hex(),
        }
    if not calls:
        raise RuntimeError("presentation listing contains no start_screen calls")
    return calls


def write_memory(client, address: int, data: bytes) -> None:
    client.call("write_memory", {"addr": address, "data": data.hex()})


def pad_rom(path: Path) -> bytes:
    raw = path.read_bytes()
    if len(raw) > 0x4000:
        raise RuntimeError(f"{path}: ROM exceeds 16 KiB")
    image = raw + b"\xff" * (0x4000 - len(raw))
    path.write_bytes(image)
    return image


def assemble(lwasm: str, directory: Path, case: dict, variant: str,
             isa: str) -> tuple[Path, Path, Path, list[str]]:
    stem = f"{case['name']}-{variant}-{isa}"
    rom = directory / f"{stem}.rom"
    listing = directory / f"{stem}.lst"
    map_path = directory / f"{stem}.map"
    command = [
        lwasm, "-9" if isa == "6809" else "-3", "--format=raw",
        f"--output={rom}", f"--list={listing}", "--symbols",
        f"--map={map_path}", "-D", f"{case['define']}=1",
    ]
    if variant == "tfm":
        command += ["-D", "BENCH_TFM=1"]
    elif variant == "q":
        command += ["-D", "BENCH_Q=1"]
    command.append(str(SOURCE))
    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode:
        detail = (completed.stdout + completed.stderr).strip()
        raise RuntimeError(f"assembly failed for {stem}: {detail}")
    pad_rom(rom)
    return rom, map_path, listing, command


def candidate_rejected_by_6809(lwasm: str, directory: Path,
                               case: dict, variant: str) -> dict:
    output = directory / f"reject-{case['name']}-{variant}.rom"
    command = [
        lwasm, "-9", "--format=raw", f"--output={output}",
        "-D", f"{case['define']}=1", "-D",
        "BENCH_TFM=1" if variant == "tfm" else "BENCH_Q=1",
        str(SOURCE),
    ]
    completed = subprocess.run(command, capture_output=True, text=True)
    return {
        "command": command,
        "returncode": completed.returncode,
        "rejected": completed.returncode != 0,
        "diagnostic": (completed.stdout + completed.stderr).strip(),
    }


def patterned_rows(seed: int) -> list[bytes]:
    return [
        bytes((seed + row * 17 + column * 7) & 0xFF for column in range(8))
        for row in range(16)
    ]


def place_rows(rows: list[bytes], fill: int = 0xCC) -> bytes:
    data = bytearray([fill] * FB_SPAN)
    for row, values in enumerate(rows):
        offset = row * 160
        data[offset:offset + 8] = values
    return bytes(data)


def fixture_for(case_name: str) -> dict[str, bytes | list[bytes]]:
    fb_rows = patterned_rows(0x21)
    linear_rows = patterned_rows(0x83)
    fb = place_rows(fb_rows)
    bg = bytes([0xCC] * LINEAR_BYTES)
    ring = bytes([0xCC] * LINEAR_BYTES)
    if case_name == "player_restore":
        bg = b"".join(linear_rows)
    elif case_name.startswith("roam_restore"):
        ring = b"".join(linear_rows)
    return {
        "fb_rows": fb_rows,
        "linear_rows": linear_rows,
        "fb": fb,
        "front": bytes([0x5A] * FB_SPAN),
        "bg": bg,
        "ring": ring,
    }


def expected_for(case_name: str, fixture: dict) -> dict[str, bytes | int]:
    fb = bytearray(fixture["fb"])
    bg = bytearray(fixture["bg"])
    ring = bytearray(fixture["ring"])
    fb_rows = fixture["fb_rows"]
    linear_rows = fixture["linear_rows"]
    valid = 0
    if case_name == "player_save":
        bg[:] = b"".join(fb_rows)
        valid = 1
    elif case_name == "player_restore":
        fb[:] = place_rows(linear_rows)
    elif case_name == "roam_capture_full":
        ring[:] = b"".join(fb_rows)
    elif case_name in {"roam_restore_phase0", "roam_restore_split_phase0"}:
        rows = linear_rows
        if case_name.endswith("split_phase0"):
            rows = linear_rows[6:] + linear_rows[:6]
        fb[:] = place_rows(rows)
    elif case_name == "roam_restore_phase4":
        fb[:] = place_rows([row[4:] + row[:4] for row in linear_rows])
    elif case_name == "roam_restore_odd_phase1":
        fb[:] = place_rows([row[1:] + row[:1] for row in linear_rows])
    elif case_name == "ring_capture_two_rows_phase0":
        ring[:16] = b"".join(fb_rows[:2])
    else:
        raise RuntimeError(f"unknown case {case_name}")
    return {"fb": bytes(fb), "bg": bytes(bg), "ring": bytes(ring),
            "front": fixture["front"], "valid": valid}


def expected_pointers(case_name: str) -> dict[str, int]:
    if case_name == "player_save":
        return {"x": PLAYER_BG + 128, "u": FB_BACK + 16 * 160}
    if case_name == "player_restore":
        return {"x": FB_BACK + 16 * 160, "u": PLAYER_BG + 128}
    if case_name == "roam_capture_full":
        return {"x": FB_BACK + 16 * 160, "u": RING_DATA + 128, "y": 0}
    if case_name in {
        "roam_restore_phase0", "roam_restore_phase4", "roam_restore_odd_phase1",
    }:
        return {"x": FB_BACK + 16 * 160, "u": RING_DATA + 128}
    if case_name == "roam_restore_split_phase0":
        return {"x": FB_BACK + 16 * 160, "u": RING_DATA + 48}
    if case_name == "ring_capture_two_rows_phase0":
        return {"x": FB_BACK + 2 * 160, "u": FB_BACK + 160 + 8}
    raise RuntimeError(f"unknown case {case_name}")


def run_sample(base, xroar: Path, rom: Path, map_path: Path, case: dict,
               variant: str, cpu: str, timeout: float) -> dict:
    syms = symbols(map_path)
    required = ("entry", "benchmark_start", "case_start", "case_end",
                "benchmark_done")
    missing = [name for name in required if name not in syms]
    if missing:
        raise RuntimeError(f"{case['name']}/{variant}: missing symbols {missing}")
    image = rom.read_bytes()
    start_offset = syms["case_start"] - 0xC000
    end_offset = syms["case_end"] - 0xC000
    instruction_bytes = image[start_offset:end_offset]
    process, client = base.launch(base.load_monitor(), xroar, rom, cpu)
    phase = "entry"
    try:
        entry_id = base.set_breakpoint(client, syms["entry"])
        entry_hit = base.run_to_breakpoint(client, timeout)
        if entry_hit.get("pc") != syms["entry"]:
            raise RuntimeError(f"entry mismatch: {entry_hit}")
        base.clear_breakpoint(client, entry_id)
        identity = base.wait_for_live_identity(
            client, rom, syms["benchmark_start"], 64, timeout
        )
        phase = "case start"
        start_id = base.set_breakpoint(client, syms["case_start"])
        start_hit = base.run_to_breakpoint(client, timeout)
        if start_hit.get("pc") != syms["case_start"]:
            raise RuntimeError(f"start mismatch: {start_hit}")
        marker = base.read_bytes(client, RESULT_BASE, 6)
        if marker[:4] != SIGNATURE or marker[4] != case["marker"]:
            raise RuntimeError(f"marker mismatch: {marker.hex()}")
        fixture = fixture_for(case["name"])
        for address, data in (
            (FB_BACK, fixture["fb"]), (FB_FRONT, fixture["front"]),
            (PLAYER_BG, fixture["bg"]), (RING_DATA, fixture["ring"]),
        ):
            write_memory(client, address, data)
            write_memory(client, address - 1, b"\xA5")
            write_memory(client, address + len(data), b"\x5A")
        begin_registers = client.call("read_registers")
        begin = base.read_timing(client)
        base.clear_breakpoint(client, start_id)
        phase = "case end"
        end_id = base.set_breakpoint(client, syms["case_end"])
        end_hit = base.run_to_breakpoint(client, timeout)
        if end_hit.get("pc") != syms["case_end"]:
            raise RuntimeError(f"end mismatch: {end_hit}")
        end = base.read_timing(client)
        end_registers = client.call("read_registers")
        base.clear_breakpoint(client, end_id)
        expected = expected_for(case["name"], fixture)
        actual = {
            "fb": base.read_bytes(client, FB_BACK, FB_SPAN),
            "front": base.read_bytes(client, FB_FRONT, FB_SPAN),
            "bg": base.read_bytes(client, PLAYER_BG, LINEAR_BYTES),
            "ring": base.read_bytes(client, RING_DATA, LINEAR_BYTES),
        }
        guards = {}
        for name, address, length in (
            ("fb", FB_BACK, FB_SPAN), ("front", FB_FRONT, FB_SPAN),
            ("bg", PLAYER_BG, LINEAR_BYTES), ("ring", RING_DATA, LINEAR_BYTES),
        ):
            guards[name] = {
                "before": base.read_bytes(client, address - 1, 1).hex(),
                "after": base.read_bytes(client, address + length, 1).hex(),
            }
        checks = {
            "framebuffer_exact": actual["fb"] == expected["fb"],
            "front_unchanged": actual["front"] == expected["front"],
            "player_background_exact": actual["bg"] == expected["bg"],
            "ring_exact": actual["ring"] == expected["ring"],
            "guards": all(
                item["before"] == "a5" and item["after"] == "5a"
                for item in guards.values()
            ),
            "player_valid": base.read_bytes(client, 0x006A, 1)[0] == expected["valid"],
            "event_tick_ratio": (
                end["event_ticks"] - begin["event_ticks"]
                == (end["cpu_cycles"] - begin["cpu_cycles"]) * 16
            ),
        }
        required_pointers = expected_pointers(case["name"])
        for register, value in required_pointers.items():
            checks[f"final_{register}"] = end_registers.get(register) == value
        if not all(checks.values()):
            raise RuntimeError(f"correctness failure: {checks}")
        phase = "post-window diagnostics"
        done_id = base.set_breakpoint(client, syms["benchmark_done"])
        done_hit = base.run_to_breakpoint(client, timeout)
        if done_hit.get("pc") != syms["benchmark_done"]:
            raise RuntimeError(f"diagnostic end mismatch: {done_hit}")
        q_diagnostic = base.read_bytes(client, RESULT_Q, 4).hex()
        base.clear_breakpoint(client, done_id)
        return {
            "cpu": cpu,
            "cpu_cycles": end["cpu_cycles"] - begin["cpu_cycles"],
            "event_ticks": end["event_ticks"] - begin["event_ticks"],
            "rom_sha256": digest(image),
            "live_identity": identity,
            "instruction_bytes": instruction_bytes.hex(),
            "marker_addresses": {
                "start": f"{syms['case_start']:04X}",
                "end": f"{syms['case_end']:04X}",
            },
            "start_halt": start_hit,
            "end_halt": end_hit,
            "registers": {"before": begin_registers, "after": end_registers},
            "q_after_window": q_diagnostic if variant != "baseline" else "unobservable/not-touched",
            "md_effect": "unchanged: no LDMD or native-mode entry in measured source",
            "guards": guards,
            "checks": checks,
        }
    except Exception as exc:
        raise RuntimeError(
            f"{case['name']}/{variant}/{cpu} failed in {phase}: {exc}"
        ) from exc
    finally:
        client.close()
        base.stop(process)


def summarize(samples: list[dict]) -> dict:
    cycles = [sample["cpu_cycles"] for sample in samples]
    ticks = [sample["event_ticks"] for sample in samples]
    ordered = sorted(cycles)
    median = ordered[len(ordered) // 2]
    spread = (max(cycles) - min(cycles)) / median if median else 0.0
    return {
        "cycle_samples": cycles,
        "event_tick_samples": ticks,
        "median_cpu_cycles": median,
        "relative_spread": spread,
        "repeatability_pass": spread <= 0.01,
        "sample_checks_pass": all(all(sample["checks"].values()) for sample in samples),
        "representative": samples[0],
    }


def source_contracts() -> dict:
    sources = {
        "main": MAIN_SOURCE.read_text(encoding="utf-8"),
        "enemy": ENEMY_SOURCE.read_text(encoding="utf-8"),
    }
    result = {}
    for case in CASES:
        text = sources[case["source"]]
        start = text.index(case["source_start"])
        end = text.index(case["source_end"], start)
        window = text[start:end]
        result[case["name"]] = {
            "source": str(MAIN_SOURCE if case["source"] == "main" else ENEMY_SOURCE),
            "window_start": case["source_start"].strip(),
            "window_end": case["source_end"].strip(),
            "window_sha256": digest(window.encode("utf-8")),
            "window": window,
        }
    return result


def xroar_gmc(binary: Path, rom: Path) -> list[str]:
    return [
        str(binary), "-ui", "null", "-ao", "null", "-machine", "coco3",
        "-machine-cpu", "6809", "-ram", "512", "-cart-type", "gmc",
        "-cart-rom", str(rom), "-no-ratelimit",
    ]


def run_xroar(command: list[str], output: Path, timeout: float) -> None:
    with output.open("w", encoding="ascii") as stream:
        completed = subprocess.run(
            command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT,
            timeout=timeout, check=False,
        )
    if completed.returncode:
        raise RuntimeError(
            f"XRoar returned {completed.returncode}; see {output}"
        )


def capture_snapshot(binary: Path, rom: Path, output: Path, frame_pc: int,
                     count: int, timeout: float, source: Path | None = None) -> None:
    command = xroar_gmc(binary, rom)
    command += ["-load", str(source)] if source else ["-ram-init", "0", "-cart-autorun"]
    command += [
        "-trap", f"pc=0x{frame_pc:04x}", "-trap-range", str(count),
        "-trap-snap", str(output), "-trap-timeout", "1",
    ]
    run_xroar(command, output.with_suffix(".log"), timeout)
    if not output.is_file():
        raise RuntimeError(f"snapshot success marker missing: {output}")


def capture_trace(binary: Path, rom: Path, snapshot: Path, output: Path,
                  stop_pc: int, timeout: float) -> Path:
    after = output.with_suffix(".sna")
    command = xroar_gmc(binary, rom) + [
        "-load", str(snapshot), "-trace", "-trace-timing",
        "-trap", f"pc=0x{stop_pc:04x}", "-trap-range", "1",
        "-trap-no-trace", "-trap-snap", str(after), "-trap-timeout", "1",
    ]
    run_xroar(command, output, timeout)
    if not after.is_file():
        raise RuntimeError(f"trace completion snapshot missing: {after}")
    return after


def moving_patch(directions: tuple[int, int, int, int]) -> list[str]:
    result = [
        "A473=01", "A47B=01", "A483=01", "A48B=01",
        "0055=40", "0060=00", "0061=00", "0087=00",
    ]
    for address, direction in zip((0xA477, 0xA47F, 0xA487, 0xA48F), directions):
        result.append(f"{address:04X}={direction:02X}")
    return result


def phase_patch(value: int) -> list[str]:
    result = []
    for base in (RAM_RING, META_A_RING, META_B_RING):
        for offset in range(4):
            result.append(f"{base + offset:04X}={value:02X}")
    return result


def trace_profile(path: Path, syms: dict[str, int]) -> dict:
    lines = []
    for line in path.read_text(encoding="ascii", errors="strict").splitlines():
        match = TRACE_RE.match(line)
        if match:
            lines.append((int(match.group(1), 16), int(match.group(2)) // 8, line))
    if not lines:
        raise RuntimeError(f"{path}: no timed trace lines")
    active = sum(cycles for _, cycles, line in lines if "| 13 " not in line)
    counts = {
        name: sum(pc == syms[name] for pc, _, _ in lines)
        for name in (
            "save_player", "restore_player", "roam_copy_bg_to_fb",
            "roam_copy_fb_to_bg", "roam_capture_ring_row",
        )
    }
    return {
        "active_cycles": active,
        "instruction_records": len(lines),
        "call_counts": counts,
        "trace_sha256": digest(path.read_bytes()),
    }


def navigate_production_startup(monitor, client, timeout: float,
                                provenance: dict,
                                absolute_deadline: float | None = None,
                                reserve_seconds: float = 0.0,
                                wait_observer=None) -> dict:
    presentation_syms = symbols(PRESENTATION_MAP)
    enemy_syms = symbols(ENEMY_MAP)
    boot_syms = symbols(BOOT_MAP)
    presentation = PRESENTATION_IMAGE.read_bytes()
    enemy = ENEMY_IMAGE.read_bytes()
    boot = BOOT_IMAGE.read_bytes()
    resident = RUNTIME_IMAGE.read_bytes()
    calls = start_screen_calls(
        PRESENTATION_LISTING, presentation_syms["start_screen"]
    )
    expected_call_lines = {0: 157, 3: 170, 2: 187}
    deadline = (time.monotonic() + timeout
                if absolute_deadline is None else absolute_deadline)
    markers = []

    def remaining(label: str) -> float:
        value = deadline - time.monotonic() - reserve_seconds
        if value <= 0:
            last = markers[-1]["marker"] if markers else "none"
            error_type = PrimaryBudgetDepleted if reserve_seconds else TimeoutError
            raise error_type(
                f"startup deadline expired waiting for {label}; "
                f"last proven marker={last}"
            )
        return value

    def registers() -> dict[str, int]:
        return {
            str(name).lower(): int(value)
            for name, value in client.call("read_registers").items()
        }

    def marker_state(label: str, address: int, hit: dict,
                     extra: dict | None = None) -> dict:
        regs = registers()
        record = {
            "phase": "startup",
            "marker": label,
            "address": f"{address:04X}",
            "pc": f"{int(hit.get('pc', -1)) & 0xFFFF:04X}",
            "halt": hit,
            "registers": regs,
            "presentation_state": {
                name: read_client_bytes(client, state_address, 1)[0]
                for name, state_address in PRESENTATION_STATE.items()
            },
        }
        if extra:
            record.update(extra)
        markers.append(record)
        return record

    def run_to(label: str, address: int) -> tuple[dict, int]:
        ident = client.call(
            "set_breakpoint", {"addr": address, "kind": "exec"}
        )["id"]
        try:
            if wait_observer:
                wait_observer("before", label, address, ident, None)
            hit = client.run_to_breakpoint(remaining(label))
            if wait_observer:
                wait_observer("after", label, address, ident, hit)
            if hit.get("pc") != address:
                raise RuntimeError(f"{label}: expected ${address:04X}, got {hit}")
            return hit, ident
        except Exception:
            try:
                client.call("clear_breakpoint", {"id": ident})
            except Exception:
                pass
            raise

    def finish_breakpoint(ident: int) -> None:
        client.call("clear_breakpoint", {"id": ident})

    def capture_start_screen(expected_request: int) -> dict:
        address = presentation_syms["start_screen"]
        hit, ident = run_to(f"start_screen request {expected_request}", address)
        try:
            regs = registers()
            request = regs["a"]
            stack = read_client_bytes(client, regs["s"], 2)
            return_address = int.from_bytes(stack, "big")
            caller = calls.get(return_address)
            expected_line = expected_call_lines[expected_request]
            if request != expected_request:
                raise RuntimeError(
                    f"start_screen request mismatch: expected {expected_request}, "
                    f"found {request}"
                )
            if caller is None or caller["source_line"] != expected_line:
                raise RuntimeError(
                    f"start_screen caller mismatch for request {request}: "
                    f"return=${return_address:04X}, caller={caller}, "
                    f"expected source line {expected_line}"
                )
            return marker_state(
                f"start_screen_{expected_request}", address, hit,
                {
                    "request": request,
                    "stack_return_bytes": stack.hex(),
                    "caller": caller,
                },
            )
        finally:
            finish_breakpoint(ident)

    boot_entry = boot_syms["boot_entry"]
    ident = client.call(
        "set_breakpoint", {"addr": boot_entry, "kind": "exec"}
    )["id"]
    rejected_entry_aliases = []
    try:
        boot_window = boot[:64]
        resident_window = resident[:64]
        while True:
            if wait_observer:
                wait_observer(
                    "before", "source-aligned boot_entry", boot_entry,
                    ident, None,
                )
            hit = client.run_to_breakpoint(remaining("source-aligned boot_entry"))
            if wait_observer:
                wait_observer(
                    "after", "source-aligned boot_entry", boot_entry,
                    ident, hit,
                )
            if hit.get("pc") != boot_entry:
                raise RuntimeError(f"boot_entry: expected ${boot_entry:04X}, got {hit}")
            live_boot = read_client_bytes(client, 0xC000, 64)
            if live_boot == boot_window:
                entry_identity = "GMC bootstrap bank 0"
                expected_boot = boot_window
                break
            if live_boot == resident_window:
                entry_identity = "resident bank 1 after GMC handoff"
                expected_boot = resident_window
                break
            rejected_entry_aliases.append({
                "reason": "pre-cartridge C002 alias",
                "pc": f"{boot_entry:04X}",
                "live_window_sha256": digest(live_boot),
                "live_window_prefix": live_boot[:16].hex(),
            })
        marker_state("boot_entry", boot_entry, hit, {
            "entry_identity": entry_identity,
            "rejected_entry_aliases": rejected_entry_aliases,
            "live_window_address": "C000",
            "live_window_bytes": 64,
            "live_window_sha256": digest(live_boot),
            "expected_window_sha256": digest(expected_boot),
            "live_window_matches": True,
        })
    finally:
        finish_breakpoint(ident)

    flow = presentation_syms["presentation_flow_tick"]
    hit, ident = run_to("presentation_flow_tick", flow)
    try:
        live_presentation = read_client_bytes(client, 0x1900, len(presentation))
        if live_presentation != presentation:
            raise RuntimeError("live presentation module differs from assembled module")
        marker_state("presentation_flow_tick", flow, hit, {
            "live_window_address": "1900",
            "live_window_bytes": len(presentation),
            "live_window_sha256": digest(live_presentation),
            "expected_window_sha256": digest(presentation),
            "live_window_matches": True,
        })
    finally:
        finish_breakpoint(ident)

    captures = [capture_start_screen(0)]
    client.call("write_memory", {"addr": 0x008F, "data": "00"})
    client.call("write_memory", {"addr": 0x0090, "data": "01"})

    attract = presentation_syms["attract_tick"]
    hit, ident = run_to("attract_tick", attract)
    try:
        marker_state("attract_tick", attract, hit)
    finally:
        finish_breakpoint(ident)
    client.call("inject_key", {"key": 5, "action": "press"})
    try:
        captures.append(capture_start_screen(3))
    finally:
        client.call("inject_key", {"key": 5, "action": "release"})

    credit = presentation_syms["credit_tick"]
    hit, ident = run_to("credit_tick", credit)
    try:
        marker_state("credit_tick", credit, hit)
    finally:
        finish_breakpoint(ident)
    client.call("inject_key", {"key": 1, "action": "press"})
    try:
        captures.append(capture_start_screen(2))
    finally:
        client.call("inject_key", {"key": 1, "action": "release"})

    frame = enemy_syms["frame_render_impl"]
    hit, ident = run_to("frame_render_impl", frame)
    try:
        live_enemy = read_client_bytes(client, 0x0800, len(enemy))
        if live_enemy != enemy:
            raise RuntimeError("live enemy module differs from assembled module")
        marker_state("frame_render_impl", frame, hit, {
            "live_window_address": "0800",
            "live_window_bytes": len(enemy),
            "live_window_sha256": digest(live_enemy),
            "expected_window_sha256": digest(enemy),
            "live_window_matches": True,
        })
    finally:
        finish_breakpoint(ident)

    return {
        "status": "pass",
        "phase": "complete-profile cold startup",
        "deadline_seconds": timeout,
        "timeout_meaning": "the named next startup marker was not observed",
        "xroar_launched": True,
        "profile": {
            "required": provenance["required_profile"],
            "presentation": provenance["presentation_profile"],
            "bootstrap": provenance["bootstrap_profile"],
        },
        "source_staged_checks": provenance["staged_checks"],
        "artifact_sha256": provenance["artifact_sha256"],
        "staged_sha256": provenance["staged_sha256"],
        "markers": markers,
        "screen_requests": [item["request"] for item in captures],
        "screen_callers": [item["caller"] for item in captures],
        "last_proven_marker": "frame_render_impl",
        "probe_count": 1,
        "observation_timeouts": 0,
    }


def startup_only_control(xroar: Path, timeout: float,
                         provenance: dict) -> dict:
    bug014 = load_module(
        "bug026_bug014_runtime",
        ROOT / "scripts/verify_bug014_initial_enemy_release.py",
    )
    monitor = bug014.load_monitor()
    process, client = monitor.launch(xroar, PRODUCTION_ROM, monitor.free_port())
    try:
        return navigate_production_startup(
            monitor, client, timeout, provenance
        )
    finally:
        client.close()
        monitor.stop(process)
        process.wait(timeout=2)


def frame_exit_contract() -> dict:
    enemy_syms = symbols(ENEMY_MAP)
    frame_entry = enemy_syms["frame_render_impl"]
    project_damage = enemy_syms["framebuffer_project_damage"]
    normal_exit = project_damage - 4
    abort_exit = project_damage - 1
    expected = {
        "frame_entry": 0x09D9,
        "normal_exit": 0x0A07,
        "abort_exit": 0x0A0A,
        "project_damage": 0x0A0B,
    }
    actual = {
        "frame_entry": frame_entry,
        "normal_exit": normal_exit,
        "abort_exit": abort_exit,
        "project_damage": project_damage,
    }
    if actual != expected:
        raise RuntimeError(f"frame exit address contract changed: {actual}")
    image = ENEMY_IMAGE.read_bytes()
    source_lines = {}
    listing_lines = {}
    listing = ENEMY_LISTING.read_text(encoding="ascii", errors="strict")
    for name, address, expected_line in (
        ("normal_exit", normal_exit, 616),
        ("abort_exit", abort_exit, 619),
    ):
        byte = image[address - 0x0800]
        if byte != 0x39:
            raise RuntimeError(f"{name} ${address:04X} is ${byte:02X}, not RTS")
        match = re.search(
            rf"^{address:04X}\s+39\s+\([^\n]*\):(\d+)\s+rts\s*$",
            listing, re.MULTILINE | re.IGNORECASE,
        )
        if match is None:
            raise RuntimeError(f"{name} ${address:04X} RTS missing from listing")
        source_line = int(match.group(1))
        if source_line != expected_line:
            raise RuntimeError(
                f"{name} source line is {source_line}, expected {expected_line}"
            )
        source_lines[name] = source_line
        listing_lines[name] = match.group(0)
    if not frame_entry < normal_exit < abort_exit < project_damage:
        raise RuntimeError("frame exit ordering contract failed")
    return {
        "addresses": {name: f"{value:04X}" for name, value in actual.items()},
        "exit_bytes": {"normal_exit": "39", "abort_exit": "39"},
        "source_lines": source_lines,
        "listing_records": listing_lines,
        "enemy_image_sha256": digest(image),
        "enemy_map_sha256": digest(ENEMY_MAP.read_bytes()),
        "enemy_listing_sha256": digest(ENEMY_LISTING.read_bytes()),
        "ordering_pass": True,
    }


def frame_boundary_control(xroar: Path, timeout: float,
                           provenance: dict) -> dict:
    bug014 = load_module(
        "bug027_bug014_runtime",
        ROOT / "scripts/verify_bug014_initial_enemy_release.py",
    )
    monitor = bug014.load_monitor()
    contract = frame_exit_contract()
    enemy_syms = symbols(ENEMY_MAP)
    frame_pc = enemy_syms["frame_render_impl"]
    normal_exit = int(contract["addresses"]["normal_exit"], 16)
    abort_exit = int(contract["addresses"]["abort_exit"], 16)
    routine_names = (
        "save_player", "restore_player", "roam_copy_bg_to_fb",
        "roam_copy_fb_to_bg", "roam_capture_ring_row",
    )
    table = ENEMY_TABLE.read_bytes()
    one_table = table[:8] + bytes(24)
    deadline = time.monotonic() + timeout
    frames = []
    lifecycle = []
    last_marker = "launch"
    timeout_count = 0

    def remaining(label: str) -> float:
        value = deadline - time.monotonic()
        if value <= 0:
            raise TimeoutError(
                f"dual-exit deadline expired waiting for {label}; "
                f"last mapped marker={last_marker}"
            )
        return value

    process, client = monitor.launch(xroar, PRODUCTION_ROM, monitor.free_port())
    try:
        navigation = navigate_production_startup(
            monitor, client, remaining("startup navigation"), provenance
        )
        last_marker = "frame_render_impl"

        def read(address: int, length: int = 1) -> bytes:
            return bytes.fromhex(client.call(
                "read_memory", {"addr": address, "length": length}
            )["data"])

        def write(address: int, data: bytes) -> None:
            client.call("write_memory", {"addr": address, "data": data.hex()})

        def registers() -> dict[str, int]:
            return {
                str(name).lower(): int(value)
                for name, value in client.call("read_registers").items()
            }

        def install(addresses: dict[str, int], phase: str) -> dict[str, int]:
            ids = {
                name: client.call(
                    "set_breakpoint", {"addr": address, "kind": "exec"}
                )["id"]
                for name, address in addresses.items()
            }
            lifecycle.append({
                "phase": phase,
                "action": "set",
                "ids": ids.copy(),
                "addresses": {
                    name: f"{address:04X}" for name, address in addresses.items()
                },
            })
            return ids

        def clear(ids: dict[str, int], phase: str,
                  suppress_failure: bool = False) -> None:
            try:
                monitor.clear(client, list(ids.values()))
                lifecycle.append({
                    "phase": phase, "action": "clear", "ids": ids.copy(),
                    "result": "pass",
                })
            except Exception as exc:
                lifecycle.append({
                    "phase": phase, "action": "clear", "ids": ids.copy(),
                    "result": "failed",
                    "error": f"{type(exc).__name__}: {exc}",
                })
                if not suppress_failure:
                    raise

        def to_frame_start(ordinal: int) -> None:
            nonlocal last_marker
            phase = f"sync_before_frame_{ordinal}"
            ids = install({"frame_entry": frame_pc}, phase)
            try:
                hit = client.run_to_breakpoint(remaining("frame_render_impl"))
                if hit.get("pc") != frame_pc:
                    raise RuntimeError(f"frame entry mismatch: {hit}")
                last_marker = "frame_render_impl"
            finally:
                clear(ids, phase, suppress_failure=sys.exc_info()[0] is not None)

        def prepare_one_actor() -> None:
            write(0xA470, one_table)
            write(0x0058, b"\x01")
            write(0x0059, b"\x01")
            for index in range(4):
                write(0xA477 + index * 8, b"\xFF")
            write(0x007F, b"\x01")
            write(0x0087, b"\x0A")
            write(0x009B, b"\xFF")

        def capture(ordinal: int, sequence: str) -> dict:
            nonlocal last_marker
            phase = f"frame_{ordinal}_{sequence}"
            addresses = {name: enemy_syms[name] for name in routine_names}
            addresses.update({
                "normal_exit": normal_exit,
                "abort_exit": abort_exit,
            })
            ids = install(addresses, phase)
            entry_registers = registers()
            fault_before = read(FRONT_FAULT)[0]
            begin = client.call("read_cycles")
            markers = []
            exit_type = None
            try:
                address_to_name = {
                    address: name for name, address in addresses.items()
                }
                while exit_type is None:
                    hit = client.run_to_breakpoint(remaining("proven frame exit"))
                    pc = hit.get("pc")
                    name = address_to_name.get(pc)
                    if name is None:
                        raise RuntimeError(f"unexpected runtime breakpoint: {hit}")
                    last_marker = name
                    markers.append({
                        "marker": name,
                        "pc": f"{int(pc):04X}",
                        "halt": hit,
                    })
                    if name in {"normal_exit", "abort_exit"}:
                        exit_type = name
                end = client.call("read_cycles")
                exit_registers = registers()
                cpu_cycles = int(end["cpu_cycles"]) - int(begin["cpu_cycles"])
                event_ticks = int(end["event_ticks"]) - int(begin["event_ticks"])
                absolute_pass = (
                    int(begin["event_ticks"]) // 16 == int(begin["cpu_cycles"])
                    and int(end["event_ticks"]) // 16 == int(end["cpu_cycles"])
                )
                if not absolute_pass:
                    raise RuntimeError(
                        f"runtime absolute event/cycle conversion mismatch: "
                        f"begin={begin}, end={end}"
                    )
                fault_after = read(FRONT_FAULT)[0]
                return {
                    "ordinal": ordinal,
                    "sequence": sequence,
                    "entry_registers": entry_registers,
                    "exit_registers": exit_registers,
                    "markers": markers,
                    "last_mapped_marker": last_marker,
                    "exit_type": exit_type,
                    "cycle_begin": begin,
                    "cycle_end": end,
                    "cpu_cycles": cpu_cycles,
                    "event_ticks": event_ticks,
                    "event_tick_delta_residual": event_ticks - cpu_cycles * 16,
                    "event_cycle_absolute_conversion_pass": True,
                    "front_fault_before": fault_before,
                    "front_fault_after": fault_after,
                    "front_write_fault_delta": (fault_after - fault_before) & 0xFF,
                    "deadline_result": "proven exit observed",
                }
            finally:
                clear(ids, phase, suppress_failure=sys.exc_info()[0] is not None)

        frames.append(capture(0, "natural_post_startup"))
        for ordinal in range(1, 5):
            to_frame_start(ordinal)
            prepare_one_actor()
            frames.append(capture(ordinal, "one_roamer_hydration"))
        hydration_aborts = sum(
            frame["exit_type"] == "abort_exit"
            for frame in frames if frame["sequence"] == "one_roamer_hydration"
        )
        return {
            "status": "pass" if hydration_aborts else "cause not confirmed",
            "phase": "complete-profile dual-exit frame control",
            "deadline_seconds": timeout,
            "deadline_result": "completed within shared deadline",
            "timeout_meaning": "neither proven exit followed the last mapped marker",
            "static_exit_contract": contract,
            "startup": navigation,
            "frames": frames,
            "breakpoint_lifecycle": lifecycle,
            "normal_exit_count": sum(
                frame["exit_type"] == "normal_exit" for frame in frames
            ),
            "abort_exit_count": sum(
                frame["exit_type"] == "abort_exit" for frame in frames
            ),
            "hydration_abort_count": hydration_aborts,
            "cause_confirmed": bool(hydration_aborts),
            "last_proven_marker": last_marker,
            "probe_count": 1,
            "observation_timeouts": timeout_count,
        }
    except TimeoutError as exc:
        timeout_count = 1
        return {
            "status": "timeout",
            "phase": "complete-profile dual-exit frame control",
            "deadline_seconds": timeout,
            "deadline_result": str(exc),
            "timeout_meaning": "neither proven exit followed the last mapped marker",
            "static_exit_contract": contract,
            "frames": frames,
            "breakpoint_lifecycle": lifecycle,
            "normal_exit_count": sum(
                frame["exit_type"] == "normal_exit" for frame in frames
            ),
            "abort_exit_count": sum(
                frame["exit_type"] == "abort_exit" for frame in frames
            ),
            "hydration_abort_count": sum(
                frame["exit_type"] == "abort_exit"
                for frame in frames if frame["sequence"] == "one_roamer_hydration"
            ),
            "cause_confirmed": False,
            "last_proven_marker": last_marker,
            "probe_count": 1,
            "observation_timeouts": timeout_count,
        }
    finally:
        client.close()
        monitor.stop(process)
        process.wait(timeout=2)


def frame_timeout_diagnostic(xroar: Path, timeout: float,
                             provenance: dict, output: Path) -> dict:
    bug014 = load_module(
        "bug028_bug014_runtime",
        ROOT / "scripts/verify_bug014_initial_enemy_release.py",
    )
    monitor = bug014.load_monitor()
    contract = frame_exit_contract()
    enemy_syms = symbols(ENEMY_MAP)
    frame_pc = enemy_syms["frame_render_impl"]
    normal_exit = int(contract["addresses"]["normal_exit"], 16)
    abort_exit = int(contract["addresses"]["abort_exit"], 16)
    routine_names = (
        "save_player", "restore_player", "roam_copy_bg_to_fb",
        "roam_copy_fb_to_bg", "roam_capture_ring_row",
    )
    table = ENEMY_TABLE.read_bytes()
    one_table = table[:8] + bytes(24)
    evidence_path = output / "bug028-frame-timeout-diagnostic.json"
    reserve_seconds = 2.0
    started = time.monotonic()
    deadline = started + timeout
    journal = []
    state = {
        "phase": "launch",
        "frame_ordinal": "startup",
        "last_mapped_marker": "none",
        "expected_breakpoints": {},
    }
    evidence = {
        "schema": "ladybug-bug028-frame-timeout-diagnostic-v1",
        "created": time.strftime("%Y-%m-%d", time.gmtime()),
        "status": "in_progress",
        "classification": None,
        "phase_deadline_seconds": timeout,
        "recovery_reserve_seconds": reserve_seconds,
        "timeout_meaning": (
            "the primary did not report the next configured breakpoint before "
            "the reserved recovery boundary"
        ),
        "command_mode": "--frame-timeout-diagnostic-only",
        "runner_sha256": digest(Path(__file__).read_bytes()),
        "production_rom_sha256": digest(PRODUCTION_ROM.read_bytes()),
        "static_exit_contract": contract,
        "profile_provenance": provenance,
        "journal": journal,
        "frames": [],
        "primary_timeouts": 0,
        "observer_timeouts": 0,
        "observer_snapshot": None,
        "capacity_changed": False,
        "full_rsch007_matrix_rerun": False,
    }

    def elapsed_ms() -> int:
        return max(0, round((time.monotonic() - started) * 1000))

    def remaining_ms() -> int:
        return max(0, round((deadline - time.monotonic()) * 1000))

    def persist(operation: str, **extra) -> None:
        record = {
            "sequence": len(journal),
            "operation": operation,
            "phase": state["phase"],
            "frame_ordinal": state["frame_ordinal"],
            "elapsed_ms": elapsed_ms(),
            "remaining_ms": remaining_ms(),
            "recovery_reserve_ms": round(reserve_seconds * 1000),
            "last_mapped_marker": state["last_mapped_marker"],
            "expected_breakpoints": state["expected_breakpoints"],
        }
        record.update(extra)
        journal.append(record)
        evidence["last_state"] = record
        write_json_atomic(evidence_path, evidence)

    def normalize_breakpoints(result: dict) -> list[dict]:
        return sorted(
            ({
                "id": int(item["id"]),
                "addr": f"{int(item['addr']):04X}",
                "kind": item.get("kind", "exec"),
            } for item in result.get("breakpoints", [])),
            key=lambda item: item["id"],
        )

    def expected_records(expected: dict[str, dict]) -> list[dict]:
        return sorted(
            ({
                "id": int(item["id"]),
                "addr": f"{int(item['addr']):04X}",
                "kind": "exec",
            } for item in expected.values()),
            key=lambda item: item["id"],
        )

    def validate_inventory(client, expected: dict[str, dict], label: str) -> list[dict]:
        state["expected_breakpoints"] = {
            name: {"id": item["id"], "addr": f"{item['addr']:04X}"}
            for name, item in expected.items()
        }
        persist("before_list_breakpoints", label=label)
        listed = normalize_breakpoints(client.call("list_breakpoints"))
        wanted = expected_records(expected)
        duplicate_addresses = len({item["addr"] for item in listed}) != len(listed)
        persist(
            "after_list_breakpoints", label=label,
            listed_breakpoints=listed, inventory_matches=(listed == wanted),
            duplicate_addresses=duplicate_addresses,
        )
        if listed != wanted or duplicate_addresses:
            evidence["status"] = "failed"
            evidence["classification"] = "breakpoint_lifecycle_mismatch"
            write_json_atomic(evidence_path, evidence)
            raise RuntimeError(
                f"{label}: breakpoint inventory mismatch: "
                f"expected={wanted}, listed={listed}"
            )
        return listed

    def require_event(hit: dict, expected: dict[str, dict], label: str) -> str:
        pc = int(hit.get("pc", -1))
        bp_id = int(hit.get("bp_id", -1))
        matches = [
            name for name, item in expected.items()
            if item["addr"] == pc and item["id"] == bp_id
        ]
        if len(matches) != 1:
            evidence["status"] = "failed"
            evidence["classification"] = "primary_event_correlation_mismatch"
            persist("breakpoint_event_mismatch", label=label, halt=hit)
            raise RuntimeError(
                f"{label}: breakpoint PC/id mismatch: {hit}, expected={expected}"
            )
        return matches[0]

    port = monitor.free_port()
    process, primary = monitor.launch(xroar, PRODUCTION_ROM, port)
    observer = None
    primary_usable = True
    current_expected: dict[str, dict] = {}
    try:
        persist("primary_connected", monitor_port=port)
        observer_socket = socket.create_connection(
            ("127.0.0.1", port), timeout=reserve_seconds
        )
        observer = monitor.MonitorClient(observer_socket)
        observer.sock.settimeout(reserve_seconds)
        hello_raw = observer.file.readline()
        if not hello_raw:
            raise RuntimeError("observer monitor connection closed before hello")
        hello = json.loads(hello_raw)
        if hello.get("method") != "hello" or hello.get("params", {}).get(
                "run_state") != "halted":
            raise RuntimeError(f"unexpected observer hello: {hello}")
        persist("observer_connected", observer_hello=hello)

        def startup_wait(stage: str, label: str, address: int,
                         ident: int, hit: dict | None) -> None:
            nonlocal current_expected
            state["phase"] = "startup"
            state["frame_ordinal"] = "startup"
            expected = {label: {"id": ident, "addr": address}}
            current_expected = expected
            if stage == "before":
                validate_inventory(primary, expected, label)
                persist(
                    "before_primary_run", label=label,
                    primary_wait_budget_ms=max(
                        0, remaining_ms() - round(reserve_seconds * 1000)
                    ),
                )
            else:
                marker = require_event(hit or {}, expected, label)
                state["last_mapped_marker"] = marker
                persist("after_primary_breakpoint", label=label, halt=hit)

        navigation = navigate_production_startup(
            monitor, primary, timeout, provenance,
            absolute_deadline=deadline,
            reserve_seconds=reserve_seconds,
            wait_observer=startup_wait,
        )
        evidence["startup"] = navigation
        state["last_mapped_marker"] = "frame_render_impl"

        def read(client, address: int, length: int = 1,
                 timeout_value: float | None = None) -> bytes:
            kwargs = {} if timeout_value is None else {"timeout": timeout_value}
            return bytes.fromhex(client.call(
                "read_memory", {"addr": address, "length": length}, **kwargs
            )["data"])

        def write(address: int, data: bytes) -> None:
            primary.call("write_memory", {"addr": address, "data": data.hex()})

        def install(addresses: dict[str, int]) -> dict[str, dict]:
            installed = {}
            for name, address in addresses.items():
                ident = primary.call(
                    "set_breakpoint", {"addr": address, "kind": "exec"}
                )["id"]
                installed[name] = {"id": int(ident), "addr": address}
            return installed

        def clear(installed: dict[str, dict]) -> None:
            monitor.clear(primary, [item["id"] for item in installed.values()])

        def primary_wait(label: str, expected: dict[str, dict]) -> dict:
            nonlocal current_expected, primary_usable
            current_expected = expected
            validate_inventory(primary, expected, label)
            available = deadline - time.monotonic() - reserve_seconds
            persist(
                "before_primary_run", label=label,
                primary_wait_budget_ms=max(0, round(available * 1000)),
            )
            if available <= 0:
                raise PrimaryBudgetDepleted(
                    f"shared phase budget depleted before {label}"
                )
            try:
                hit = primary.run_to_breakpoint(available)
            except (TimeoutError, socket.timeout):
                primary_usable = False
                evidence["primary_timeouts"] += 1
                persist("primary_reserved_boundary", label=label)
                raise
            marker = require_event(hit, expected, label)
            state["last_mapped_marker"] = marker
            persist("after_primary_breakpoint", label=label, halt=hit)
            return hit

        def prepare_one_actor() -> None:
            write(0xA470, one_table)
            write(0x0058, b"\x01")
            write(0x0059, b"\x01")
            for index in range(4):
                write(0xA477 + index * 8, b"\xFF")
            write(0x007F, b"\x01")
            write(0x0087, b"\x0A")
            write(0x009B, b"\xFF")

        def sync_frame(ordinal: int) -> None:
            state["phase"] = "frame_sync"
            state["frame_ordinal"] = ordinal
            installed = install({"frame_entry": frame_pc})
            primary_wait(f"sync frame {ordinal}", installed)
            clear(installed)
            state["last_mapped_marker"] = "frame_render_impl"
            state["expected_breakpoints"] = {}
            persist("frame_entry_synchronized")

        def capture_frame(ordinal: int, sequence: str) -> None:
            state["phase"] = sequence
            state["frame_ordinal"] = ordinal
            addresses = {name: enemy_syms[name] for name in routine_names}
            addresses.update({
                "normal_exit": normal_exit,
                "abort_exit": abort_exit,
            })
            installed = install(addresses)
            markers = []
            while True:
                hit = primary_wait(f"frame {ordinal} marker", installed)
                marker = state["last_mapped_marker"]
                markers.append({"marker": marker, "halt": hit})
                if marker in {"normal_exit", "abort_exit"}:
                    break
            clear(installed)
            state["expected_breakpoints"] = {}
            frame = {
                "ordinal": ordinal,
                "sequence": sequence,
                "markers": markers,
                "exit_type": state["last_mapped_marker"],
                "elapsed_ms": elapsed_ms(),
                "remaining_ms": remaining_ms(),
            }
            evidence["frames"].append(frame)
            persist("frame_exit_retained", frame=frame)

        capture_frame(0, "natural_post_startup")
        for ordinal in range(1, 5):
            sync_frame(ordinal)
            prepare_one_actor()
            capture_frame(ordinal, "one_roamer_hydration")
        evidence["status"] = "failed"
        evidence["classification"] = "not_reproduced"
        persist("diagnostic_sequence_completed_without_timeout")
        return evidence
    except PrimaryBudgetDepleted as exc:
        evidence["status"] = "pass"
        evidence["classification"] = "shared_phase_budget_depleted_before_run"
        evidence["diagnostic_result"] = str(exc)
        persist("classification_complete", error=str(exc))
        return evidence
    except (TimeoutError, socket.timeout) as exc:
        if evidence["primary_timeouts"] == 0:
            evidence["primary_timeouts"] = 1
            persist("primary_reserved_boundary", primary_error=str(exc))
        if observer is None:
            evidence["status"] = "failed"
            evidence["classification"] = "observer_unavailable"
            evidence["diagnostic_result"] = str(exc)
            write_json_atomic(evidence_path, evidence)
            return evidence

        def observer_call(method: str, params: dict | None = None) -> dict:
            available = deadline - time.monotonic()
            if available <= 0:
                raise TimeoutError("no recovery budget remains for observer")
            return observer.call(method, params, timeout=available)

        def observer_read(address: int, length: int) -> bytes:
            return bytes.fromhex(observer_call(
                "read_memory", {"addr": address, "length": length}
            )["data"])

        try:
            persist("before_observer_state", primary_error=str(exc))
            pre_state = observer_call("get_run_state")
            persist("observer_state_before_pause", observer_state=pre_state)
            was_running = pre_state.get("state") == "running"
            if was_running:
                observer_call("pause")
            halted_state = observer_call("get_run_state")
            registers = {
                str(name).lower(): int(value)
                for name, value in observer_call("read_registers").items()
            }
            cycles = observer_call("read_cycles")
            bp_list = normalize_breakpoints(observer_call("list_breakpoints"))
            wanted = expected_records(current_expected)
            stack = observer_read(registers["s"], 8)
            flags = observer_read(0x007F, 27)
            pc = registers["pc"]
            module = "outside_known_runtime"
            expected_bytes = None
            if 0x0800 <= pc < 0x0800 + len(ENEMY_IMAGE.read_bytes()):
                module = "enemy_runtime"
                offset = pc - 0x0800
                expected_bytes = ENEMY_IMAGE.read_bytes()[offset:offset + 8]
            elif 0xC000 <= pc < 0xC000 + len(RUNTIME_IMAGE.read_bytes()):
                module = "resident_runtime"
                offset = pc - 0xC000
                expected_bytes = RUNTIME_IMAGE.read_bytes()[offset:offset + 8]
            elif 0x1900 <= pc < 0x1900 + len(PRESENTATION_IMAGE.read_bytes()):
                module = "presentation_runtime"
                offset = pc - 0x1900
                expected_bytes = PRESENTATION_IMAGE.read_bytes()[offset:offset + 8]
            live = observer_read(pc, 8)
            identity_matches = expected_bytes is not None and live == expected_bytes
            snapshot = {
                "pre_pause_state": pre_state,
                "halted_state": halted_state,
                "pause_issued": was_running,
                "registers": registers,
                "cycles": cycles,
                "stack_bytes": stack.hex(),
                "frame_flags_007f_0099": flags.hex(),
                "front_write_fault": flags[0x0099 - 0x007F],
                "breakpoints": bp_list,
                "expected_breakpoints": wanted,
                "breakpoint_inventory_matches": bp_list == wanted,
                "pc": f"{pc:04X}",
                "mapped_module": module,
                "live_pc_bytes": live.hex(),
                "expected_pc_bytes": (
                    None if expected_bytes is None else expected_bytes.hex()
                ),
                "live_pc_identity_matches": identity_matches,
            }
            evidence["observer_snapshot"] = snapshot
            if not was_running:
                stop_pc = int(pre_state.get("last_stop_pc", -1))
                stop_id = int(pre_state.get("last_stop_bp_id", -1))
                matching = any(
                    item["addr"] == stop_pc and item["id"] == stop_id
                    for item in current_expected.values()
                )
                classification = (
                    "primary_event_delivery_or_correlation_failure"
                    if matching else "unexpected_halt"
                )
            elif bp_list != wanted:
                classification = "breakpoint_lifecycle_mismatch"
            elif not identity_matches:
                classification = "artifact_or_mapping_drift"
            elif module in {"enemy_runtime", "resident_runtime"}:
                classification = "shared_phase_budget_depleted_while_running"
            else:
                classification = (
                    "source_aligned_execution_outside_expected_frame_call_tree"
                )
            evidence["classification"] = classification
            evidence["status"] = (
                "pass" if classification in {
                    "primary_event_delivery_or_correlation_failure",
                    "shared_phase_budget_depleted_while_running",
                } else "failed"
            )
            evidence["diagnostic_result"] = str(exc)
            persist("classification_complete", observer_snapshot=snapshot)
            return evidence
        except (TimeoutError, socket.timeout) as observer_exc:
            evidence["observer_timeouts"] += 1
            evidence["status"] = "failed"
            evidence["classification"] = "observer_timeout"
            evidence["diagnostic_result"] = str(observer_exc)
            write_json_atomic(evidence_path, evidence)
            return evidence
        except Exception as observer_exc:
            evidence["status"] = "failed"
            evidence["classification"] = "observer_failure"
            evidence["diagnostic_result"] = (
                f"{type(observer_exc).__name__}: {observer_exc}"
            )
            write_json_atomic(evidence_path, evidence)
            return evidence
    except Exception as exc:
        evidence["status"] = "failed"
        if evidence["classification"] is None:
            evidence["classification"] = "unexpected_diagnostic_failure"
        evidence["diagnostic_result"] = f"{type(exc).__name__}: {exc}"
        try:
            persist("diagnostic_failure", error=evidence["diagnostic_result"])
        except Exception:
            write_json_atomic(evidence_path, evidence)
        return evidence
    finally:
        if observer is not None:
            try:
                observer.close()
            except Exception:
                pass
        try:
            primary.close()
        except Exception:
            pass
        monitor.stop(process)
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass


def runtime_worklists(xroar: Path, timeout: float, directory: Path,
                      isolated: dict, provenance: dict) -> tuple[dict, dict]:
    bug014 = load_module(
        "rsch007_bug014_runtime", ROOT / "scripts/verify_bug014_initial_enemy_release.py"
    )
    enemy_syms = symbols(ENEMY_MAP)
    main_syms = symbols(MAIN_MAP)
    frame_pc = enemy_syms["frame_render_impl"]
    frame_end = enemy_syms["framebuffer_project_damage"] - 4
    enemy_rom = (ROOT / "build/ladybug-enemy-runtime.rom").read_bytes()
    if enemy_rom[frame_end - 0x0800] != 0x39:
        raise RuntimeError(f"frame end ${frame_end:04X} is not RTS")
    table = ENEMY_TABLE.read_bytes()
    one_table = table[:8] + bytes(24)

    def best(case_name: str) -> tuple[str, int]:
        case_result = isolated[case_name]
        baseline = case_result["variants"]["baseline_6309"]["median_cpu_cycles"]
        choices = {
            name: values["median_cpu_cycles"]
            for name, values in case_result["variants"].items()
            if name not in {"baseline_6309", "baseline_6809"}
        }
        name = min(choices, key=choices.get)
        return name, baseline - choices[name]

    monitor = bug014.load_monitor()
    process, client = monitor.launch(xroar, PRODUCTION_ROM, monitor.free_port())
    current_at_frame = False
    try:
        navigation = navigate_production_startup(
            monitor, client, timeout, provenance
        )
        current_at_frame = True

        def read(address: int, length: int = 1) -> bytes:
            return bytes.fromhex(client.call(
                "read_memory", {"addr": address, "length": length}
            )["data"])

        def write(address: int, data: bytes) -> None:
            client.call("write_memory", {"addr": address, "data": data.hex()})

        def to_frame_start() -> None:
            nonlocal current_at_frame
            if current_at_frame:
                return
            ident = client.call(
                "set_breakpoint", {"addr": frame_pc, "kind": "exec"}
            )["id"]
            hit = client.run_to_breakpoint(timeout)
            client.call("clear_breakpoint", {"id": ident})
            if hit.get("pc") != frame_pc:
                raise RuntimeError(f"frame start mismatch: {hit}")
            current_at_frame = True

        routine_names = (
            "save_player", "restore_player", "roam_copy_bg_to_fb",
            "roam_copy_fb_to_bg", "roam_capture_ring_row",
        )

        def capture_current_frame() -> dict:
            nonlocal current_at_frame
            if not current_at_frame:
                raise RuntimeError("capture requested outside frame boundary")
            fault_before = read(FRONT_FAULT)[0]
            begin = client.call("read_cycles")
            address_to_name = {enemy_syms[name]: name for name in routine_names}
            ids = {
                name: client.call(
                    "set_breakpoint", {"addr": enemy_syms[name], "kind": "exec"}
                )["id"]
                for name in routine_names
            }
            ids["frame_end"] = client.call(
                "set_breakpoint", {"addr": frame_end, "kind": "exec"}
            )["id"]
            counts = {name: 0 for name in routine_names}
            deadline = time.monotonic() + timeout
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("frame worklist did not reach normal RTS")
                hit = client.run_to_breakpoint(remaining)
                pc = hit.get("pc")
                if pc == frame_end:
                    break
                name = address_to_name.get(pc)
                if name is None:
                    raise RuntimeError(f"unexpected runtime breakpoint: {hit}")
                counts[name] += 1
            end = client.call("read_cycles")
            monitor.clear(client, list(ids.values()))
            current_at_frame = False
            cpu_cycles = int(end["cpu_cycles"]) - int(begin["cpu_cycles"])
            event_ticks = int(end["event_ticks"]) - int(begin["event_ticks"])
            begin_conversion = int(begin["event_ticks"]) // 16
            end_conversion = int(end["event_ticks"]) // 16
            if (begin_conversion != int(begin["cpu_cycles"])
                    or end_conversion != int(end["cpu_cycles"])):
                raise RuntimeError(
                    f"runtime absolute event/cycle conversion mismatch: "
                    f"begin={begin}, end={end}"
                )
            return {
                "active_cycles": cpu_cycles,
                "event_ticks": event_ticks,
                "event_tick_delta_residual": event_ticks - cpu_cycles * 16,
                "event_cycle_absolute_conversion_pass": True,
                "call_counts": counts,
                "front_write_fault_delta": (read(FRONT_FAULT)[0] - fault_before) & 0xFF,
            }

        def prepare_actor_count(count: int) -> None:
            write(0xA470, one_table if count == 1 else table)
            write(0x0058, bytes([count]))
            write(0x0059, bytes([count]))
            for index in range(4):
                write(0xA477 + index * 8, b"\xFF")
            write(0x007F, b"\x01")
            write(0x0087, b"\x0A")
            write(0x009B, b"\xFF")

        def hydrate(count: int) -> None:
            prepare_actor_count(count)
            for _ in range(4):
                capture_current_frame()
                to_frame_start()
                prepare_actor_count(count)

        def set_phase(value: int, count: int) -> None:
            write(RAM_RING, bytes([value] * 4))
            write(META_A_RING, bytes([value] * 4))
            write(META_B_RING, bytes([value] * 4))
            back = read(0x0090)[0]
            meta = 0xA900 if back == 0 else 0xAA00
            for index in range(count):
                old = int.from_bytes(read(meta + 8 + index * 8 + 1, 2), "big")
                write(0xA471 + index * 8, old.to_bytes(2, "big"))
                write(0xA476 + index * 8, b"\x01")
                write(meta + 8 + index * 8 + 6, b"\x01")
            write(0x007F, b"\x00")
            write(0x0087, b"\x00")
            write(0x009B, b"\x00")

        def force_vertical(count: int) -> None:
            set_phase(0, count)
            back = read(0x0090)[0]
            meta = 0xA900 if back == 0 else 0xAA00
            for index in range(count):
                old = int.from_bytes(read(meta + 8 + index * 8 + 1, 2), "big")
                write(0xA471 + index * 8, ((old + 320) & 0xFFFF).to_bytes(2, "big"))
                write(0xA477 + index * 8, b"\x02")

        scenarios = []
        hydrate(1)
        set_phase(0, 1)
        scenarios.append((
            "natural_one_roamer", "normal stationary closure",
            "player closure plus one roaming actor", "roam_restore_phase0", None,
            capture_current_frame(), 1,
        ))
        to_frame_start()
        hydrate(4)
        for name, phase, worklist, value, restore_case, vertical in (
            ("natural_four_roamer", "normal stationary closure",
             "player closure plus four roaming actors", 0, "roam_restore_phase0", False),
            ("forced_restore_phase0", "forced retained background",
             "four phase-zero restores", 0, "roam_restore_phase0", False),
            ("forced_restore_phase4", "forced retained background",
             "four phase-four restores", 4, "roam_restore_phase4", False),
            ("forced_split_restore", "forced wrapped row phase",
             "four split phase-zero restores", 0x60,
             "roam_restore_split_phase0", False),
            ("forced_vertical_capture", "forced vertical movement",
             "four two-row captures", 0, "roam_restore_phase0", True),
        ):
            if vertical:
                force_vertical(4)
            else:
                set_phase(value, 4)
            scenarios.append((
                name, phase, worklist, restore_case,
                "ring_capture_two_rows_phase0" if vertical else None,
                capture_current_frame(), 4,
            ))
            to_frame_start()

        result = {}
        for name, phase, worklist, restore_case, capture_case, profile, expected in scenarios:
            savings = 0
            components = []
            for routine, case_name in (
                ("save_player", "player_save"),
                ("restore_player", "player_restore"),
                ("roam_copy_bg_to_fb", restore_case),
                ("roam_copy_fb_to_bg", "roam_capture_full"),
            ):
                calls = profile["call_counts"][routine]
                if calls:
                    candidate, delta = best(case_name)
                    amount = calls * delta
                    savings += amount
                    components.append({
                        "routine": routine, "case": case_name, "calls": calls,
                        "candidate": candidate, "cycles_saved_per_call": delta,
                        "projected_cycles_saved": amount,
                    })
            if capture_case:
                helper_calls = profile["call_counts"]["roam_capture_ring_row"]
                if helper_calls % 2:
                    raise RuntimeError(f"{name}: odd exposed-row helper count {helper_calls}")
                worklists = helper_calls // 2
                candidate, delta = best(capture_case)
                amount = worklists * delta
                savings += amount
                components.append({
                    "routine": "roam_capture_ring_row", "case": capture_case,
                    "calls": helper_calls, "two_row_worklists": worklists,
                    "candidate": candidate, "cycles_saved_per_worklist": delta,
                    "projected_cycles_saved": amount,
                })
            projected = profile["active_cycles"] - savings
            share = savings * 100 / profile["active_cycles"]
            result[name] = {
                "scenario_phase": phase,
                "executed_worklist": worklist,
                "owner": "secondary metadata: live BACK at frame entry",
                "navigation": navigation if name == "natural_one_roamer" else "same live run",
                **profile,
                "projection": {
                    "components": components,
                    "projected_cycles_saved": savings,
                    "projected_active_cycles": projected,
                    "share_percent": share,
                    "margin_to_engineering_27000": 27000 - projected,
                    "margin_to_hardware_29666": 29666 - projected,
                    "passes_materiality": savings >= 1000 and share >= 5.0,
                },
            }
            if profile["call_counts"]["roam_copy_bg_to_fb"] != expected:
                raise RuntimeError(
                    f"{name}: expected {expected} roaming restores, found "
                    f"{profile['call_counts']['roam_copy_bg_to_fb']}"
                )
            if profile["front_write_fault_delta"]:
                raise RuntimeError(f"{name}: FRONT-write fault delta")
        return result, navigation
    finally:
        client.close()
        monitor.stop(process)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lwasm", default="lwasm")
    parser.add_argument("--xroar", type=Path, default=DEFAULT_XROAR)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--runtime-timeout", type=float, default=60.0)
    parser.add_argument("--output", type=Path, default=ROOT / "build/rsch007-6309")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--isolated-only", action="store_true",
        help="retain exact isolated evidence without starting a runtime probe",
    )
    modes.add_argument(
        "--startup-only", action="store_true",
        help="run only the BUG-026 profile and source/staged/live startup gate",
    )
    modes.add_argument(
        "--frame-boundary-only", action="store_true",
        help="run only the BUG-027 dual-exit frame-boundary control",
    )
    modes.add_argument(
        "--frame-timeout-diagnostic-only", action="store_true",
        help="run only the BUG-028 durable frame-timeout discriminator",
    )
    args = parser.parse_args()
    if args.repeats < 3:
        raise SystemExit("repeats must be at least 3")
    if not 0 < args.timeout <= 5:
        raise SystemExit("timeout must be greater than zero and at most 5 seconds")
    if not 0 < args.runtime_timeout <= 60:
        raise SystemExit("runtime timeout must be greater than zero and at most 60 seconds")
    production_paths = (
        MAIN_SOURCE, ENEMY_SOURCE, ROOT / "src/presentation_runtime.s",
        ROOT / "src/gmc_bootstrap.s", MAIN_MAP, ENEMY_MAP, PRESENTATION_MAP,
        PRESENTATION_IMAGE, PRESENTATION_LISTING, BOOT_MAP, BOOT_IMAGE,
        BOOT_LISTING, RUNTIME_IMAGE, ENEMY_IMAGE, SPARSE_LAYOUT,
        PRODUCTION_ROM, ENEMY_LISTING, args.xroar,
    )
    isolated_paths = (SOURCE,) + (() if args.isolated_only else (ENEMY_TABLE,))
    runtime_only = (
        args.startup_only or args.frame_boundary_only
        or args.frame_timeout_diagnostic_only
    )
    for path in production_paths + (() if runtime_only else isolated_paths):
        if not path.is_file():
            raise SystemExit(f"required dependency missing: {path}")

    args.output.mkdir(parents=True, exist_ok=True)
    provenance = None
    if not args.isolated_only:
        try:
            provenance = production_provenance(args.xroar)
        except ProfileMismatch as exc:
            rejection = {
                "schema": "ladybug-bug026-startup-identity-v1",
                "created": "2026-08-30",
                "status": "rejected incompatible profile before XRoar launch",
                "profile": exc.evidence,
                "probe_count": 0,
                "observation_timeouts": 0,
                "error": str(exc),
            }
            rejection_output = args.output / "bug026-startup-identity.json"
            rejection_output.write_text(
                json.dumps(rejection, indent=2) + "\n", encoding="ascii"
            )
            raise SystemExit(str(exc)) from exc
    if args.startup_only:
        assert provenance is not None
        startup = startup_only_control(
            args.xroar, args.runtime_timeout, provenance
        )
        evidence = {
            "schema": "ladybug-bug026-startup-identity-v1",
            "created": "2026-08-30",
            **startup,
        }
        output = args.output / "bug026-startup-identity.json"
        output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="ascii")
        print(f"BUG-026 startup evidence: {output}")
        return
    if args.frame_boundary_only:
        assert provenance is not None
        control = frame_boundary_control(
            args.xroar, args.runtime_timeout, provenance
        )
        evidence = {
            "schema": "ladybug-bug027-frame-boundary-v1",
            "created": "2026-08-30",
            **control,
        }
        output = args.output / "bug027-frame-boundary.json"
        output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="ascii")
        print(f"BUG-027 frame-boundary evidence: {output}")
        if not control["cause_confirmed"]:
            raise SystemExit(
                f"BUG-027 control stopped: {control['status']}; "
                f"last marker={control['last_proven_marker']}"
            )
        return
    if args.frame_timeout_diagnostic_only:
        assert provenance is not None
        diagnostic = frame_timeout_diagnostic(
            args.xroar, args.runtime_timeout, provenance, args.output
        )
        output = args.output / "bug028-frame-timeout-diagnostic.json"
        print(f"BUG-028 frame-timeout evidence: {output}")
        print(f"BUG-028 classification: {diagnostic['classification']}")
        if diagnostic["status"] != "pass":
            raise SystemExit(
                f"BUG-028 diagnostic stopped: {diagnostic['classification']}"
            )
        return

    base = load_module("rsch007_benchmark_base", ROOT / "scripts/benchmark_6309.py")
    contracts = source_contracts()
    isolated = {}
    rejects = []
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="rsch007-") as temporary:
        directory = Path(temporary)
        for case in CASES:
            baseline9, baseline9_map, _, _ = assemble(
                args.lwasm, directory, case, "baseline", "6809"
            )
            baseline3, baseline3_map, _, _ = assemble(
                args.lwasm, directory, case, "baseline", "6309"
            )
            if baseline9.read_bytes() != baseline3.read_bytes():
                raise RuntimeError(f"{case['name']}: portable baseline bytes differ")
            variants = {}
            for key, rom, map_path, cpu in (
                ("baseline_6309", baseline3, baseline3_map, "6309"),
                ("baseline_6809", baseline9, baseline9_map, "6809"),
            ):
                samples = [
                    run_sample(base, args.xroar, rom, map_path, case, "baseline", cpu,
                               args.timeout)
                    for _ in range(args.repeats)
                ]
                variants[key] = summarize(samples)
            for variant in case["variants"]:
                if variant == "baseline":
                    continue
                rejection = candidate_rejected_by_6809(
                    args.lwasm, directory, case, variant
                )
                rejects.append({"case": case["name"], "variant": variant, **rejection})
                if not rejection["rejected"]:
                    raise RuntimeError(
                        f"{case['name']}/{variant}: candidate assembled under -9"
                    )
                rom, map_path, _, _ = assemble(
                    args.lwasm, directory, case, variant, "6309"
                )
                samples = [
                    run_sample(base, args.xroar, rom, map_path, case, variant,
                               "6309", args.timeout)
                    for _ in range(args.repeats)
                ]
                variants[variant] = summarize(samples)
            isolated[case["name"]] = {
                "source_contract": contracts[case["name"]],
                "baseline_6809_6309_byte_identity": True,
                "variants": variants,
            }
        startup = {}
        if args.isolated_only:
            runtime = {}
        else:
            assert provenance is not None
            runtime, startup = runtime_worklists(
                args.xroar, args.runtime_timeout, directory, isolated, provenance
            )

    recommendations = {}
    for name, case in isolated.items():
        baseline = case["variants"]["baseline_6309"]["median_cpu_cycles"]
        candidates = {
            variant: values["median_cpu_cycles"]
            for variant, values in case["variants"].items()
            if variant not in {"baseline_6309", "baseline_6809"}
        }
        if not candidates:
            recommendations[name] = {
                "recommendation": "retain baseline; odd rotation is not directly applicable",
                "baseline_cycles": baseline,
            }
            continue
        best_name = min(candidates, key=candidates.get)
        recommendations[name] = {
            "recommendation": best_name,
            "baseline_cycles": baseline,
            "candidate_cycles": candidates[best_name],
            "cycles_saved": baseline - candidates[best_name],
            "reduction_percent": (baseline - candidates[best_name]) * 100 / baseline,
        }
    material = [
        name for name, item in runtime.items()
        if item["projection"]["passes_materiality"]
    ]
    evidence = {
        "schema": "ladybug-rsch007-production-hotpaths-v1",
        "created": "2026-08-30",
        "source_sha256": digest(SOURCE.read_bytes()),
        "production_source_sha256": {
            "main": digest(MAIN_SOURCE.read_bytes()),
            "enemy_runtime": digest(ENEMY_SOURCE.read_bytes()),
        },
        "production_artifacts": {
            "rom": str(PRODUCTION_ROM), "rom_sha256": digest(PRODUCTION_ROM.read_bytes()),
            "main_map_sha256": digest(MAIN_MAP.read_bytes()),
            "enemy_map_sha256": digest(ENEMY_MAP.read_bytes()),
            "xroar_sha256": digest(args.xroar.read_bytes()),
        },
        "method": {
            "primary_cpu": "6309 emulation mode",
            "portable_control_cpu": "6809",
            "repeats": args.repeats,
            "isolated_deadline_seconds": args.timeout,
            "runtime_deadline_seconds": args.runtime_timeout,
            "event_ticks_per_cpu_cycle": 16,
            "materiality": "at least 1000 cycles and at least 5% of named worklist",
            "probe_count": 0 if args.isolated_only else 1,
            "observation_timeouts": 0,
            "historical_rejected_runtime_paths": (
                [
                    "full-GMC trap did not reach frame_render_impl within 60 seconds",
                    "live-window/request-gated monitor startup did not accept attract within 60 seconds",
                ] if args.isolated_only else []
            ),
        },
        "isolated_cases": isolated,
        "candidate_6809_rejections": rejects,
        "startup_identity": startup,
        "runtime_worklists": runtime,
        "recommendations": recommendations,
        "material_worklists": material,
        "production_follow_up_recommended": bool(material),
        "runtime_status": (
            "not run (--isolated-only); historical runtime investigation remains blocked"
            if args.isolated_only else "complete"
        ),
        "scope": {
            "production_source_changed": False,
            "release_rom_changed": False,
            "xroar_changed": False,
            "native_mode_tested": False,
            "hardware_tested": False,
            "separate_rom_policy_changed": False,
        },
        "elapsed_seconds": time.monotonic() - started,
    }
    output = args.output / "rsch007-production-hotpaths.json"
    output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="ascii")
    if startup:
        startup_output = args.output / "bug026-startup-identity.json"
        startup_output.write_text(json.dumps({
            "schema": "ladybug-bug026-startup-identity-v1",
            "created": "2026-08-30",
            **startup,
        }, indent=2) + "\n", encoding="ascii")
    print(f"RSCH-007 evidence: {output}")
    for name, values in recommendations.items():
        print(f"{name}: {values}")
    for name, values in runtime.items():
        print(f"{name}: {values['projection']}")


if __name__ == "__main__":
    main()
