#!/usr/bin/env python3
"""Verify and summarize current-revision complete-frame performance traces."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import date
from pathlib import Path

from read_snapshot import find_ram


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
HARDWARE_BUDGET = 29_666
ENGINEERING_TARGET = 27_000
TRACE_RE = re.compile(r"^[0-9a-f]{4}\|.* dt=(\d+)$")
MAP_RE = re.compile(r"^Symbol: (\w+) .* = ([0-9A-Fa-f]+)$")


def symbols(path: Path) -> dict[str, str]:
    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = MAP_RE.match(line)
        if match:
            result[match.group(1)] = match.group(2).lower().zfill(4)
    return result


def trace_sections(path: Path, frame_pc: str) -> list[dict[str, object]]:
    lines = [
        line
        for line in path.read_text(encoding="ascii", errors="strict").splitlines()
        if TRACE_RE.match(line)
    ]
    # XRoar 1.10 reports the first restored-snapshot instruction at PC $0000,
    # while decoding and executing the saved frame_render_impl instruction.
    if lines and lines[0].startswith("0000|"):
        lines[0] = frame_pc + lines[0][4:]
    starts = [index for index, line in enumerate(lines) if line.startswith(frame_pc + "|")]
    if not starts:
        raise ValueError(f"{path}: frame_render_impl was not traced")
    sections = []
    # A measured interval must have both frame-render boundaries.  The trailing
    # trace tail is diagnostic only and must never become timing evidence.
    for position, start in enumerate(starts[:-1]):
        end = starts[position + 1]
        section = lines[start:end]
        cycles = [int(TRACE_RE.match(line).group(1)) // 8 for line in section]
        cycles[0] = 9
        sync = sum(cycle for cycle, line in zip(cycles, section) if "| 13 " in line)
        sections.append(
            {
                "instructions": len(section),
                "active_cycles": sum(cycles) - sync,
                "sync_wait_cycles": sync,
                "pcs": [line[:4] for line in section],
            }
        )
    return sections


def measured(section: dict[str, object], owner: str) -> dict[str, object]:
    active = int(section["active_cycles"])
    return {
        "owner": owner,
        "instructions": section["instructions"],
        "active_cycles": active,
        "hardware_margin_cycles": HARDWARE_BUDGET - active,
        "engineering_margin_cycles": ENGINEERING_TARGET - active,
        "passes_hardware_budget": active < HARDWARE_BUDGET,
        "passes_engineering_target": active <= ENGINEERING_TARGET,
    }


def alternating_sections(path: Path, frame_pc: str, initial_back: int) -> list[dict[str, object]]:
    result = []
    for index, section in enumerate(trace_sections(path, frame_pc)):
        interval = measured(
            section,
            "A" if (initial_back + index) % 2 == 0 else "B",
        )
        interval["pcs"] = section["pcs"]
        result.append(interval)
    return result


def without_pcs(value: dict[str, object]) -> dict[str, object]:
    return {key: item for key, item in value.items() if key != "pcs"}


def semantic_bytes(path: Path, data: bytes) -> bytes:
    if path.suffix in (".py", ".s", ".trace"):
        data = data.replace(b"\r\n", b"\n")
    return data


def hash_file(path: Path) -> str:
    """Hash source semantics independently of checkout line endings and paths."""
    data = semantic_bytes(path, path.read_bytes())
    if path.suffix == ".map":
        values = []
        for line in data.decode("utf-8").splitlines():
            match = MAP_RE.match(line)
            if match:
                values.append(f"{match.group(1)}={match.group(2).upper()}\n")
        if not values:
            raise ValueError(f"{path}: no symbols for semantic provenance")
        data = "".join(values).encode("ascii")
    return hashlib.sha256(data).hexdigest()


def verify_hash_contract() -> None:
    lf = hashlib.sha256(b"line\nnext\n").hexdigest()
    crlf = hashlib.sha256(b"line\r\nnext\r\n".replace(b"\r\n", b"\n")).hexdigest()
    changed = hashlib.sha256(b"line\nother\n").hexdigest()
    trace_path = Path("sample.trace")
    trace_lf = hashlib.sha256(semantic_bytes(trace_path, b"pc dt=8\n")).hexdigest()
    trace_crlf = hashlib.sha256(
        semantic_bytes(trace_path, b"pc dt=8\r\n")
    ).hexdigest()
    trace_changed = hashlib.sha256(
        semantic_bytes(trace_path, b"pc dt=16\n")
    ).hexdigest()
    if (
        lf != crlf or lf == changed or
        trace_lf != trace_crlf or trace_lf == trace_changed or
        Path("src/main.s").as_posix() != "src/main.s"
    ):
        raise ValueError("performance semantic hash line-ending/mutation contract failed")


def verify_capture_material() -> None:
    verify_hash_contract()
    material_path = BUILD / "performance-capture-material.json"
    if not material_path.is_file():
        raise ValueError("performance traces have no capture-material manifest")
    material = json.loads(material_path.read_text(encoding="ascii"))
    sources = (
        Path("src/main.s"), Path("src/enemy_runtime.s"),
        Path("src/perimeter_reset_helper.s"), Path("scripts/build_sparse_sprites.py"),
        Path("scripts/build_screen.py"),
    )
    if material.get("source_sha256") != {
        path.as_posix(): hash_file(ROOT / path) for path in sources
    }:
        raise ValueError("performance traces are stale for current material source")
    if material.get("rom_sha256") != hash_file(BUILD / "ladybug.rom"):
        raise ValueError("performance traces are stale for the current cartridge image")
    if material.get("trace_sha256") != {
        path.name: hash_file(path) for path in sorted(BUILD.glob("perf-*.raw.trace"))
    }:
        raise ValueError("performance trace hashes differ from capture material")


def main() -> None:
    verify_capture_material()
    enemy_symbols = symbols(BUILD / "ladybug-enemy-runtime.map")
    frame_pc = enemy_symbols["frame_render_impl"]
    required = {
        "rub_horizontal",
        "ROAM_COMBINED_RIGHT",
        "ROAM_COMBINED_LEFT",
        "rub_vertical",
        "rub_full",
        "compose_enemy_zone",
        "compose_enemy_animation",
        "gate_compose_impl",
        "fbiq_missed",
        "fbp_write_front_fault",
    }
    missing = required - enemy_symbols.keys()
    if missing:
        raise ValueError("missing baseline symbols: " + ", ".join(sorted(missing)))

    horizontal = alternating_sections(
        BUILD / "perf-four-horizontal.raw.trace", frame_pc, 0
    )
    if len(horizontal) < 8:
        raise ValueError(
            "horizontal capture lacks eight complete frame-render intervals; "
            "recapture rather than omitting a closed observation"
        )
    for interval in horizontal:
        pcs = interval["pcs"]
        interval["horizontal_captures"] = pcs.count(enemy_symbols["rub_horizontal"])
        interval["combined_horizontal"] = (
            pcs.count(enemy_symbols["ROAM_COMBINED_RIGHT"])
            + pcs.count(enemy_symbols["ROAM_COMBINED_LEFT"])
        )
        interval["full_captures"] = pcs.count(enemy_symbols["rub_full"])

    vertical = alternating_sections(BUILD / "perf-four-vertical.raw.trace", frame_pc, 0)
    vertical += alternating_sections(
        BUILD / "perf-four-vertical-a.raw.trace", frame_pc, 1
    )
    for interval in vertical:
        pcs = interval["pcs"]
        interval["vertical_captures"] = pcs.count(enemy_symbols["rub_vertical"])
        interval["full_captures"] = pcs.count(enemy_symbols["rub_full"])

    player = alternating_sections(BUILD / "perf-player.raw.trace", frame_pc, 0)
    animation = []
    animation_replay = {}
    for owner, initial_back in (("A", 1), ("B", 0)):
        intervals = alternating_sections(
            BUILD / f"perf-animation-{owner.lower()}.raw.trace",
            frame_pc,
            initial_back,
        )
        matches = [
            interval
            for interval in intervals
            if interval["pcs"].count(enemy_symbols["compose_enemy_animation"])
        ]
        other = "B" if owner == "A" else "A"
        owners = [interval["owner"] for interval in matches]
        if len(matches) != 2 or owners != [owner, other]:
            raise ValueError(
                f"animation trace did not prove natural {owner}/{other} replay: {owners}"
            )
        if any(interval["pcs"].count(enemy_symbols["compose_enemy_animation"]) != 1
               for interval in matches):
            raise ValueError("animation replay did not use exactly one bounded composition")
        animation_replay[owner] = owners
        if owner == "A":
            animation.extend(matches)
    popup = alternating_sections(BUILD / "perf-popup.raw.trace", frame_pc, 0)[-2:]
    death = []
    death_reset = []
    for owner in ("A", "B"):
        for target, stem in ((death, "death"), (death_reset, "death-reset")):
            section = trace_sections(
                BUILD / f"perf-{stem}-{owner.lower()}.raw.trace", frame_pc
            )[0]
            interval = measured(section, owner)
            interval["pcs"] = section["pcs"]
            target.append(interval)
    discontinuity_by_owner = {}
    for stem, initial_back in (("a", 0), ("b", 1)):
        intervals = alternating_sections(
            BUILD / f"perf-discontinuity-{stem}.raw.trace", frame_pc, initial_back
        )
        for interval in intervals:
            interval["full_captures"] = interval["pcs"].count(
                enemy_symbols["rub_full"]
            )
            if interval["full_captures"] == 4:
                discontinuity_by_owner.setdefault(interval["owner"], interval)
    if set(discontinuity_by_owner) != {"A", "B"}:
        raise ValueError(
            "forced discontinuity did not execute four full captures on both owners: "
            + repr({owner: item["full_captures"] for owner, item in discontinuity_by_owner.items()})
        )
    discontinuities = [discontinuity_by_owner[owner] for owner in ("A", "B")]
    gate = alternating_sections(BUILD / "perf-gate.raw.trace", frame_pc, 0)[:2]
    for interval in gate:
        interval["gate_compositions"] = interval["pcs"].count(
            enemy_symbols["gate_compose_impl"]
        )

    horizontal_movement = [
        interval
        for interval in horizontal
        if (
            interval["horizontal_captures"] == 4
            or interval["combined_horizontal"] == 4
        ) and interval["full_captures"] == 0
    ]
    vertical_movement = [
        interval
        for interval in vertical
        if interval["vertical_captures"] == 4 and interval["full_captures"] == 0
    ]
    all_intervals = (
        player + horizontal_movement + vertical_movement + discontinuities
        + animation + popup + death + death_reset + gate
    )
    write_front_fault_events = sum(
        interval.get("pcs", []).count(enemy_symbols["fbp_write_front_fault"])
        for interval in all_intervals
    )
    missed_commit_events = sum(
        interval.get("pcs", []).count(enemy_symbols["fbiq_missed"])
        for interval in all_intervals
    )
    if write_front_fault_events:
        raise ValueError(f"captured {write_front_fault_events} write-to-front faults")

    hydrated_ram = find_ram((BUILD / "perf-four-hydrated.sna").read_bytes())
    framebuffer_a = hydrated_ram[0x60000:0x60000 + 30_720]
    framebuffer_b = hydrated_ram[0x58000:0x58000 + 30_720]
    if framebuffer_a != framebuffer_b:
        raise ValueError("hydrated A/B framebuffers did not converge byte-exactly")
    convergence_sha256 = hashlib.sha256(framebuffer_a).hexdigest()

    layout = json.loads((BUILD / "ladybug-sparse-layout.json").read_text(encoding="ascii"))
    capacity = {
        "resident_used": int(symbols(BUILD / "ladybug.map")["resident_end"], 16) - 0xC000,
        "resident_limit": 8192,
        "assets_used": int(symbols(BUILD / "ladybug.map")["asset_end"], 16) - 0xE000,
        "assets_limit": 7680,
        "bank3_used": (BUILD / "ladybug-enemy-runtime.rom").stat().st_size,
        "bank3_limit": 4096,
        "direct_page_spare": 95,
        "stack_spare": 1791,
        "expansion_payload_spare": layout["gmc"]["spare_bytes"],
    }
    if any(capacity[used] > capacity[limit] for used, limit in (
        ("resident_used", "resident_limit"),
        ("assets_used", "assets_limit"),
        ("bank3_used", "bank3_limit"),
    )):
        raise ValueError(f"capacity limit exceeded: {capacity}")

    report = {
        "captured": date.today().isoformat(),
        "source_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "source_sha256": {
            path.as_posix(): hash_file(ROOT / path)
            for path in (
                Path("src/main.s"),
                Path("src/enemy_runtime.s"),
                Path("scripts/build_screen.py"),
                Path("scripts/build_sparse_sprites.py"),
            )
        },
        "measurement_contract": (
            "complete frame_render_impl-to-next-render-call active interval; "
            "only identified SYNC waits excluded"
        ),
        "hardware_budget_cycles": HARDWARE_BUDGET,
        "engineering_target_cycles": ENGINEERING_TARGET,
        "capacity": capacity,
        "diagnostics": {
            "write_front_fault_events": write_front_fault_events,
            "missed_commit_events": missed_commit_events,
            "animation_replay": animation_replay,
            "hydrated_ab_convergence_sha256": convergence_sha256,
        },
        "scenarios": {
            "player": [without_pcs(item) for item in player],
            "horizontal_four_enemy": [without_pcs(item) for item in horizontal_movement],
            "vertical_four_enemy": [without_pcs(item) for item in vertical_movement],
            "movement_discontinuity": [without_pcs(item) for item in discontinuities],
            "movement_plus_nest_animation": [without_pcs(item) for item in animation],
            "blue_x5_popup": [without_pcs(item) for item in popup],
            "death_angel": [without_pcs(item) for item in death],
            "death_reset_with_nest": [without_pcs(item) for item in death_reset],
            "gate_diagonal_final": [without_pcs(item) for item in gate],
        },
        "acceptance": {
            "current_revision_complete_frame_evidence": True,
            "forced_discontinuity_present_for_both_owners": len(discontinuities) == 2,
            "natural_animation_replay_verified": animation_replay == {
                "A": ["A", "B"], "B": ["B", "A"]
            },
            "zero_write_to_front_faults": write_front_fault_events == 0,
            "zero_missed_commit_events": missed_commit_events == 0,
            "exact_hydrated_ab_convergence": True,
            "all_sampled_paths_below_hardware_budget": all(
                int(item["active_cycles"]) < HARDWARE_BUDGET for item in all_intervals
            ),
            "all_sampled_paths_at_engineering_target": all(
                int(item["active_cycles"]) <= ENGINEERING_TARGET for item in all_intervals
            ),
        },
        "artifacts": {
            "horizontal": "build/perf-four-horizontal.raw.trace",
            "vertical": [
                "build/perf-four-vertical.raw.trace",
                "build/perf-four-vertical-a.raw.trace",
            ],
            "player": "build/perf-player.raw.trace",
            "animation": [
                "build/perf-animation-a.raw.trace",
                "build/perf-animation-b.raw.trace",
            ],
            "animation_pixel_proof": [
                "build/perf-animation-a-fast-proof.bin",
                "build/perf-animation-a-full-proof.bin",
                "build/perf-animation-b-fast-proof.bin",
                "build/perf-animation-b-full-proof.bin",
            ],
            "popup": "build/perf-popup.raw.trace",
            "death": [
                "build/perf-death-a.raw.trace",
                "build/perf-death-b.raw.trace",
            ],
            "discontinuity": [
                "build/perf-discontinuity-a.raw.trace",
                "build/perf-discontinuity-b.raw.trace",
            ],
            "death_reset_with_nest": [
                "build/perf-death-reset-a.raw.trace",
                "build/perf-death-reset-b.raw.trace",
            ],
            "gate": "build/perf-gate.raw.trace",
        },
    }

    output = BUILD / "performance-baseline.json"
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="ascii")
    summary = {
        name: max(item["active_cycles"] for item in values)
        for name, values in report["scenarios"].items()
        if values
    }
    print("performance baseline: " + ", ".join(f"{k}={v}" for k, v in summary.items()))


if __name__ == "__main__":
    main()
