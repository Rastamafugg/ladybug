#!/usr/bin/env python3
"""Verify BUG-006 respawn publication to both framebuffer owners."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
sys.path.insert(0, str(ROOT / "scripts"))

from capture_performance_baseline import (  # noqa: E402
    capture_snapshot,
    swap_framebuffer_owners,
    symbol,
)
from patch_snapshot_state import patch_snapshot  # noqa: E402
from read_snapshot import cpu_to_phys, find_ram  # noqa: E402


def source_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except subprocess.CalledProcessError:
        owner = ROOT.parent / "ladybug"
        return subprocess.check_output(
            ["git", "-C", str(owner), "rev-parse", "HEAD"], text=True,
            stderr=subprocess.DEVNULL,
        ).strip()


def player_region(ram: bytes, framebuffer_base: int) -> bytes:
    pointer = int.from_bytes(ram[cpu_to_phys(0x000B):cpu_to_phys(0x000B) + 2], "big")
    offset = pointer - 0x2000
    if not 0 <= offset <= 0x8600:
        raise ValueError(f"invalid player framebuffer pointer ${pointer:04X}")
    result = bytearray()
    for row in range(16):
        start = framebuffer_base + offset + row * 160
        result.extend(ram[start:start + 4])
    return bytes(result)


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()[:16]


def respawn_patches() -> list[str]:
    return [
        "0023=02",  # one life remains after the forced reset
        "003A=00", "004D=03", "004E=00", "0051=00",
        "0069=00", "006A=00",
        "007F=00", "0080=00", "0087=00",
        "0088=00", "0089=00", "008A=00", "008B=00",
        "008D=00", "008E=00",
        "A901=00", "AA01=00", "A902=00", "AA02=00",
    ]


def sample(snapshot: Path) -> dict[str, object]:
    ram = find_ram(snapshot.read_bytes())
    player_a = player_region(ram, 0x60000)
    player_b = player_region(ram, 0x58000)
    return {
        "death_state": ram[cpu_to_phys(0x004D)],
        "lives": ram[cpu_to_phys(0x0023)],
        "front_owner": ram[cpu_to_phys(0x008F)],
        "back_owner": ram[cpu_to_phys(0x0090)],
        "player_valid_a": ram[cpu_to_phys(0xA902)],
        "player_valid_b": ram[cpu_to_phys(0xAA02)],
        "player_hash_a": digest(player_a),
        "player_hash_b": digest(player_b),
    }


def main() -> None:
    base = BUILD / "perf-baseline.sna"
    rom = BUILD / "ladybug.rom"
    if not base.exists() or not rom.exists():
        raise SystemExit("BUG-006 verifier: run capture_performance_baseline.py --skip-build first")

    finish_pc = symbol(BUILD / "ladybug-enemy-runtime.map", "framebuffer_finish_back")
    cases: list[dict[str, object]] = []

    with tempfile.TemporaryDirectory(prefix="ladybug-bug006-") as directory:
        directory = Path(directory)
        for orientation, reversed_start in (("normal", False), ("reversed", True)):
            source = directory / f"{orientation}-respawn-source.sna"
            if reversed_start:
                swapped = directory / f"{orientation}-swapped.sna"
                swap_framebuffer_owners(base, swapped, ["008F=00", "0090=01"])
                patch_snapshot(swapped, source, respawn_patches())
            else:
                patch_snapshot(base, source, respawn_patches())

            output = directory / f"{orientation}-after-12-finishes.sna"
            capture_snapshot(output, finish_pc, 12, source)
            final_sample = sample(output)
            case_pass = (
                final_sample["death_state"] == 0
                and final_sample["lives"] == 1
                and final_sample["player_valid_a"] == 1
                and final_sample["player_valid_b"] == 1
                and final_sample["player_hash_a"] == final_sample["player_hash_b"]
            )
            cases.append({
                "orientation": orientation,
                "start_front_owner": sample(source)["front_owner"],
                "start_back_owner": sample(source)["back_owner"],
                "natural_finish_boundaries": 12,
                "required_steady_boundaries": 8,
                "final_sample": final_sample,
                "pass": case_pass,
            })

    report = {
        "source_commit": source_commit(),
        "scenario": "forced death-state blank to replacement player with alternating frame boundaries",
        "required_steady_samples": 8,
        "cases": cases,
        "pass": len(cases) == 2 and all(case["pass"] for case in cases),
    }
    output = BUILD / "bug-006-respawn-player.json"
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="ascii")
    print(json.dumps(report, indent=2))
    if not report["pass"]:
        raise SystemExit("BUG-006 verifier: failure")


if __name__ == "__main__":
    main()
