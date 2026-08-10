#!/usr/bin/env python3
"""Capture forced PERF-002 death-reset worklists from one current build."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

from capture_performance_baseline import BUILD, capture_snapshot, capture_trace, patch_snapshot, symbol, swap_framebuffer_owners
from read_snapshot import cpu_to_phys, find_ram

ROOT = Path(__file__).resolve().parents[1]
MAP_SYMBOL_RE = re.compile(r"^Symbol: (\w+) .* = ([0-9A-Fa-f]+)$")


def ownership(path: Path) -> dict[str, int]:
    ram = find_ram(path.read_bytes())
    values = {name: ram[cpu_to_phys(address)] for name, address in {
        "front_id": 0x008F, "back_id": 0x0090, "render_active": 0x0098,
    }.items()}
    values["completed_target_physical"] = 0x60000 if values["front_id"] == 0 else 0x58000
    return values


def material_digest(name: str) -> str:
    """Hash material semantics independent of checkout line endings and paths."""
    path = ROOT / name
    data = path.read_bytes()
    if path.suffix == ".map":
        symbols = []
        for line in data.decode("utf-8").splitlines():
            match = MAP_SYMBOL_RE.match(line)
            if match:
                symbols.append(f"{match.group(1)}={match.group(2).upper()}\n")
        if not symbols:
            raise ValueError(f"{path}: no map symbols for provenance")
        data = "".join(symbols).encode("ascii")
    elif path.suffix in (".py", ".s"):
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def material_hashes() -> dict[str, str]:
    """Bind retained capture metadata to the material capture inputs."""
    names = (
        "src/main.s", "src/enemy_runtime.s", "scripts/capture_death_reset.py",
        "scripts/verify_death_reset.py", "scripts/capture_performance_baseline.py", "build/ladybug.rom",
        "build/ladybug-enemy-runtime.map", "build/ladybug.map",
    )
    return {name: material_digest(name) for name in names}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--case", choices=("zero", "four", "vegetable", "mixed", "generic_control", "structural"))
    parser.add_argument("--prefix", default="perf002")
    args = parser.parse_args()
    if not args.skip_build:
        subprocess.run([str(ROOT / "scripts" / "build.sh"), "build"], cwd=ROOT, check=True)
    boundary_pc = symbol(BUILD / "ladybug.map", "main_render")
    compose_pc = symbol(BUILD / "ladybug-enemy-runtime.map", "compose_enemy_zone")
    base = BUILD / f"{args.prefix}-base.sna"
    attract = BUILD / f"{args.prefix}-attract.sna"
    forced_gameplay = BUILD / f"{args.prefix}-forced-gameplay.sna"
    capture_snapshot(attract, 0x1900, 2)
    patch_snapshot(attract, forced_gameplay, [
        "00A4=A5", "00A5=06", "00A7=01", "00B0=00", "00B1=B4",
        "004D=00",
    ])
    # XRoar 1.10 corrupts the serialized low-RAM page when trap-snap stops
    # inside the $0800 bank-3 module.  Use the resident call boundary instead;
    # it encloses the same complete render transaction and preserves the module.
    capture_snapshot(base, boundary_pc, 1, forced_gameplay)
    common = ["003A=00", "004D=02", "004E=0D", "0062=01", "0060=00", "0087=00", "007F=80", "0080=00"]
    cases = {
        "zero": common + ["A470=00", "A471=00", "A472=00", "A473=00", "A474=00", "A475=00", "A476=00", "A477=00", "A478=00", "A479=00", "A47A=00", "A47B=00", "A47C=00", "A47D=00", "A47E=00", "A47F=00", "A480=00", "A481=00", "A482=00", "A483=00", "A484=00", "A485=00", "A486=00", "A487=00", "A488=00", "A489=00", "A48A=00", "A48B=00", "A48C=00", "A48D=00", "A48E=00", "A48F=00"],
        "four": common,
        "vegetable": common + ["003A=01"],
        "mixed": ["0087=0A", "0060=00"],
        "generic_control": common + ["0062=02", "0087=0A"],
        "structural": ["003A=00", "004D=02", "004E=0D", "0062=02", "0060=00", "0087=12", "007F=80", "0080=00", "A901=00", "AA01=00", "A9A8=00", "AAA8=00"],
    }
    selected = (args.case,) if args.case else tuple(cases)
    for name in selected:
        patches = cases[name]
        for owner, front, back in (("a", 1, 0), ("b", 0, 1)):
            snapshot = BUILD / f"{args.prefix}-{name}-{owner}.sna"
            if owner == "a":
                patch_snapshot(base, snapshot, patches + [f"008F={front:02X}", f"0090={back:02X}"])
            else:
                swap_framebuffer_owners(base, snapshot, patches + [f"008F={front:02X}", f"0090={back:02X}"])
            after = BUILD / f"{args.prefix}-{name}-{owner}-after.sna"
            if name == "mixed":
                # Mixed overlap is a reachability guard, not timing evidence.
                # Avoid multi-megabyte instruction traces through the generic
                # compositor and stop directly at its entry instead.
                capture_snapshot(
                    BUILD / f"{args.prefix}-{name}-{owner}-reached.sna",
                    compose_pc, 1, snapshot,
                )
                after = snapshot
            else:
                # Native reset cases retain eight resident render intervals.
                capture_trace(snapshot, BUILD / f"{args.prefix}-{name}-{owner}.raw.trace", boundary_pc, 8)
                capture_snapshot(after, boundary_pc, 8, snapshot)
            metadata = {
                "schema": 2,
                "scenario": name,
                "requested_start": owner.upper(),
                "measurement_contract": "closed main_render-to-next-main_render active intervals only; trailing trace tail is diagnostic only",
                "before": ownership(snapshot),
                "after": ownership(after),
                "material_sha256": material_hashes(),
            }
            (BUILD / f"{args.prefix}-{name}-{owner}.json").write_text(json.dumps(metadata) + "\n", encoding="ascii")
    print(f"{args.prefix} death-reset captures complete")


if __name__ == "__main__":
    main()
