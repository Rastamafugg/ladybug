#!/usr/bin/env python3
"""Verify BUG-005 gate replay after a nearby collectible colour redraw."""

from __future__ import annotations

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
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except subprocess.CalledProcessError:
        # WSL cannot resolve Git-for-Windows worktree pointers.  The fallback
        # is only for this clean verification worktree and reads the owning
        # repository's current revision.
        owner = ROOT.parent / "ladybug"
        return subprocess.check_output(
            ["git", "-C", str(owner), "rev-parse", "HEAD"], text=True
        ).strip()


def gate_records() -> list[tuple[int, int, int]]:
    text = (BUILD / "ladybug_maze.inc").read_text(encoding="utf-8")
    values: list[int] = []
    for line in text.split("\nmaze_gates\n", 1)[1].splitlines():
        if "fcb" not in line:
            break
        values.extend(
            int(item.strip().replace("$", "0x"), 0)
            for item in line.split("fcb", 1)[1].split(",")
        )
    return [tuple(values[index:index + 3]) for index in range(0, 60, 3)]


def gate_region(ram: bytes, gx: int, gy: int, base: int) -> bytes:
    result = bytearray()
    for cell_y in range(max(0, gy - 2), min(24, gy + 3)):
        for cell_x in range(max(0, gx - 2), min(24, gx + 3)):
            start = cell_y * 8 * 160 + (cell_x + 8) * 4
            for row in range(8):
                result.extend(ram[base + start + row * 160:base + start + row * 160 + 4])
    return bytes(result)


def gate_cell(ram: bytes, gx: int, gy: int, base: int) -> bytes:
    start = gy * 8 * 160 + (gx + 8) * 4
    result = bytearray()
    for row in range(8):
        result.extend(ram[base + start + row * 160:base + start + row * 160 + 4])
    return bytes(result)


def pending_patches(meta_prefix: str, colour: bool) -> list[str]:
    return [
        # Keep one harmless HUD intent in the control so queue_damage marks
        # the pending ledger; the colour case adds the entity redraw intent.
        "0018=01", "0019=00", "007F=0A" if colour else "007F=02",
        "0088=00", "0089=00", "008A=00", "008B=00",
        "008D=00", "008E=00", "A240=01",
        f"{meta_prefix}01=01",
        f"{meta_prefix}A0=00", f"{meta_prefix}A1=00",
        f"{meta_prefix}A8=00", f"{meta_prefix}A9=01",
        f"{meta_prefix}AA=01", f"{meta_prefix}AB=00",
        f"{meta_prefix}AC=00", f"{meta_prefix}AD=00",
        f"{meta_prefix}AE=00",
    ]


def authoritative_patches(meta_prefix: str) -> list[str]:
    return [
        "0018=01", "0019=00", "007F=0A",
        "0088=01", "0089=01", "008A=00", "008B=00",
        "008D=00", "008E=00", "A240=01",
        f"{meta_prefix}01=00",
        *[f"{meta_prefix}{offset:02X}=00" for offset in range(0xA0, 0xB2)],
    ]


def compare_case(
    source: Path,
    result: Path,
    reference_a: bytes,
    reference_b: bytes,
    reference_cell_a: bytes,
    reference_cell_b: bytes,
    frame_pc: int,
    gx: int,
    gy: int,
    reference_owner: int,
) -> dict[str, int]:
    capture_snapshot(result, frame_pc, 8, source)
    ram = find_ram(result.read_bytes())
    a = gate_region(ram, gx, gy, 0x60000)
    b = gate_region(ram, gx, gy, 0x58000)
    cell_a = gate_cell(ram, gx, gy, 0x60000)
    cell_b = gate_cell(ram, gx, gy, 0x58000)
    observed_owner = ram[cpu_to_phys(0x0090)]
    target_difference = (
        sum(left != right for left, right in zip(a, reference_a))
        if observed_owner == 0 else
        sum(left != right for left, right in zip(b, reference_b))
    )
    return {
        "owner_a_difference": sum(left != right for left, right in zip(a, reference_a)),
        "owner_b_difference": sum(left != right for left, right in zip(b, reference_b)),
        "owner_cross_difference": sum(left != right for left, right in zip(a, b)),
        "gate_cell_difference": (
            sum(left != right for left, right in zip(cell_a, reference_cell_a))
            if reference_owner == 0 else
            sum(left != right for left, right in zip(cell_b, reference_cell_b))
        ),
        "gate_cell_diff_indices": [
            index for index, (left, right) in enumerate(
                zip(cell_a, reference_cell_a) if reference_owner == 0
                else zip(cell_b, reference_cell_b)
            ) if left != right
        ],
        "reference_back_owner": reference_owner,
        "observed_back_owner": observed_owner,
        "owner_phase_match": int(observed_owner == reference_owner),
        "target_owner_difference": target_difference,
    }


def main() -> None:
    base = BUILD / "perf-gate.sna"
    rom = BUILD / "ladybug.rom"
    if not base.exists() or not rom.exists():
        raise SystemExit("BUG-005 verifier: run capture_performance_baseline.py --skip-build --gate-only first")

    frame_pc = symbol(BUILD / "ladybug-enemy-runtime.map", "framebuffer_finish_back")
    gx, gy, _ = gate_records()[0]
    cases: list[dict[str, object]] = []

    with tempfile.TemporaryDirectory(prefix="ladybug-bug005-") as directory:
        directory = Path(directory)
        for orientation, reversed_start in (("normal", False), ("reversed", True)):
            if reversed_start:
                prepared = directory / f"{orientation}-base.sna"
                swap_framebuffer_owners(base, prepared, ["008F=00", "0090=01"])
                meta_prefix = "AA"
            else:
                prepared = base
                meta_prefix = "A9"

            reference_source = directory / f"{orientation}-reference.sna"
            colour_source = directory / f"{orientation}-colour.sna"
            reference_result = directory / f"{orientation}-reference-result.sna"
            colour_result = directory / f"{orientation}-colour-result.sna"
            patch_snapshot(prepared, reference_source, authoritative_patches(meta_prefix))
            patch_snapshot(prepared, colour_source, pending_patches(meta_prefix, True))

            capture_snapshot(reference_result, frame_pc, 8, reference_source)
            reference_ram = find_ram(reference_result.read_bytes())
            reference_a = gate_region(reference_ram, gx, gy, 0x60000)
            reference_b = gate_region(reference_ram, gx, gy, 0x58000)
            reference_cell_a = gate_cell(reference_ram, gx, gy, 0x60000)
            reference_cell_b = gate_cell(reference_ram, gx, gy, 0x58000)
            reference_owner = reference_ram[cpu_to_phys(0x0090)]

            result = compare_case(
                colour_source,
                colour_result,
                reference_a,
                reference_b,
                reference_cell_a,
                reference_cell_b,
                frame_pc,
                gx,
                gy,
                reference_owner,
            )
            result.update({"orientation": orientation, "gate": 0, "x": gx, "y": gy})
            cases.append(result)

    failures = [case for case in cases if not case["owner_phase_match"] or case["gate_cell_difference"]]
    report = {
        "source_commit": source_commit(),
        "scenario": "pending final gate plus nearby collectible colour redraw",
        "gate": {"id": 0, "x": gx, "y": gy},
        "cases": cases,
        "target_owner_rule": "compare the live FB_BACK_ID owner immediately before framebuffer publication",
        "required_case_count": 2,
        "pass": len(cases) == 2 and not failures,
    }
    output = BUILD / "bug-005-gate-colour-replay.json"
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="ascii")
    print(json.dumps(report, indent=2))
    if not report["pass"]:
        raise SystemExit("BUG-005 verifier: failure")


if __name__ == "__main__":
    main()
