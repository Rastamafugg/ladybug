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
    args = parser.parse_args()
    if not args.skip_build:
        subprocess.run([str(ROOT / "scripts" / "build.sh"), "build"], cwd=ROOT, check=True)
    frame_pc = symbol(BUILD / "ladybug-enemy-runtime.map", "frame_render_impl")
    render_pc = symbol(BUILD / "ladybug-enemy-runtime.map", "death_reset_ready")
    stop_pc = symbol(BUILD / "ladybug.map", "main_render")
    base = BUILD / "perf002-base.sna"
    capture_snapshot(base, frame_pc, 4)
    common = ["003A=00", "004D=02", "004E=0D", "0062=00", "0060=00", "0087=00", "007F=80", "0080=00"]
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
            snapshot = BUILD / f"perf002-{name}-{owner}.sna"
            if owner == "a":
                patch_snapshot(base, snapshot, patches + [f"008F={front:02X}", f"0090={back:02X}"])
            else:
                swap_framebuffer_owners(base, snapshot, patches + [f"008F={front:02X}", f"0090={back:02X}"])
            ready = BUILD / f"perf002-{name}-{owner}-ready.sna"
            capture_snapshot(ready, render_pc, 1, snapshot)
            ready_state = ownership(ready)
            ready_ram = find_ram(ready.read_bytes())
            if name not in ("mixed", "structural") and (ready_ram[cpu_to_phys(0x0062)] != 1 or ready_ram[cpu_to_phys(0x0087)] & 0x12 != 0x12):
                raise SystemExit(f"reset-ready state missing for {name}/{owner}")
            # Request eight main-render boundaries.  The verifier treats only the
            # seven frame_render_impl-to-frame_render_impl intervals as evidence;
            # any trace tail is diagnostic and is rejected for timing purposes.
            capture_trace(snapshot, BUILD / f"perf002-{name}-{owner}.raw.trace", frame_pc, 8, timeout=20)
            # main_render is reached only after the preceding frame transaction
            # has returned; frame_render_impl itself is an entry boundary.
            capture_snapshot(BUILD / f"perf002-{name}-{owner}-after.sna", stop_pc, 2, snapshot)
            metadata = {
                "schema": 2,
                "scenario": name,
                "requested_start": owner.upper(),
                "measurement_contract": "closed frame_render_impl-to-next-frame_render_impl active intervals only; trailing trace tail is diagnostic only",
                "before": ownership(snapshot),
                "after": ownership(BUILD / f"perf002-{name}-{owner}-after.sna"),
                "material_sha256": material_hashes(),
            }
            (BUILD / f"perf002-{name}-{owner}.json").write_text(json.dumps(metadata) + "\n", encoding="ascii")
    print("PERF-002 death-reset captures complete")


if __name__ == "__main__":
    main()
