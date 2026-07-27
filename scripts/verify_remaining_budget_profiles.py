#!/usr/bin/env python3
"""Extract and verify the remaining controlled strict-budget profiles."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
HARDWARE_BUDGET = 29_666
TRACE_RE = re.compile(r"^[0-9a-f]{4}\|.* dt=(\d+)$")

SCENARIOS = {
    "animation": {
        "label": "movement plus animation",
        "sequence": "A current nest animation; B projected nest replay",
        "owners": ("A", "B"),
        "event_entry": "13b6",
        "event_return": "0a16",
        "event_label": "nest composition",
        "sparse_draws": 5,
    },
    "gate": {
        "label": "gate diagonal transition",
        "sequence": "A diagonal frame; B projected diagonal plus final gate frame",
        "owners": ("A", "B"),
        "event_entry": "159d",
        "event_return": "0b8e",
        "event_label": "gate composition",
        "sparse_draws": 5,
    },
    "pickup": {
        "label": "blue x5 pickup popup",
        "sequence": "persistent popup presentation on both owners",
        "owners": ("A", "B"),
        "event_entry": "cfc7",
        "event_return": "0c81",
        "event_label": "popup drawing",
        "sparse_draws": 4,
    },
    "death": {
        "label": "death angel frame",
        "sequence": "persistent angel presentation on both owners",
        "owners": ("A", "B"),
        "event_entry": "d10f",
        "event_return": "0c99",
        "event_label": "death-frame drawing",
        "sparse_draws": 4,
    },
}


def trace_lines(path: Path) -> list[list[str]]:
    lines = []
    for line in path.read_text(encoding="ascii", errors="strict").splitlines():
        if TRACE_RE.match(line):
            lines.append(line)
    starts = [index for index, line in enumerate(lines) if line.startswith("0a1b|")]
    expected = len(SCENARIOS) * 2
    if len(starts) != expected:
        raise ValueError(f"{path}: expected {expected} controlled frame starts")
    starts.append(len(lines))
    return [lines[starts[index]:starts[index + 1]] for index in range(expected)]


def split_trace(
    sections: list[list[str]],
    owners: tuple[str, str],
    stem: str,
    pair_index: int,
) -> dict[str, list[str]]:
    result = {}
    pair = sections[pair_index * 2:pair_index * 2 + 2]
    for owner, section in zip(owners, pair):
        section[0] = re.sub(r"dt=\d+$", "dt=72", section[0])
        output = BUILD / f"remaining-{stem}-owner-{owner.lower()}.trace"
        output.write_text("\n".join(section) + "\n", encoding="ascii")
        result[owner] = section
    return result


def segment_cycles(lines: list[str], entry: str, return_pc: str) -> tuple[int, int, int]:
    pcs = [line[:4] for line in lines]
    entries = [index for index, pc in enumerate(pcs) if pc == entry]
    if not entries:
        raise ValueError(f"{entry}: event entry not reached")
    instructions = 0
    cycles = 0
    for entry_index in entries:
        start = entry_index - 1
        end = next(index for index in range(entry_index + 1, len(pcs))
                   if pcs[index] == return_pc)
        instructions += end - start
        cycles += sum(
            int(TRACE_RE.match(line).group(1)) // 8
            for line in lines[start:end]
        )
    return instructions, cycles, len(entries)


def profile(lines: list[str], scenario: dict[str, object]) -> dict[str, object]:
    cycles = [int(TRACE_RE.match(line).group(1)) // 8 for line in lines]
    # Trace was enabled while stopped on frame_render_impl. XRoar's first dt
    # includes the preceding trace-disabled interval; the LBSR itself is 9 cycles.
    cycles[0] = 9
    sync_indexes = {index for index, line in enumerate(lines) if "| 13 " in line}
    elapsed = sum(cycles)
    sync = sum(cycles[index] for index in sync_indexes)
    active = elapsed - sync
    event_instructions, event_cycles, event_executions = segment_cycles(
        lines,
        str(scenario["event_entry"]),
        str(scenario["event_return"]),
    )
    sparse_draws = sum(line.startswith("164c|") for line in lines)
    if sparse_draws != scenario["sparse_draws"]:
        raise ValueError(
            f"{scenario['label']}: expected {scenario['sparse_draws']} sparse draws, "
            f"found {sparse_draws}"
        )
    return {
        "instructions": len(lines),
        "active_instructions": len(lines) - len(sync_indexes),
        "elapsed_cycles": elapsed,
        "sync_wait_cycles": sync,
        "active_cycles": active,
        "budget_margin_cycles": HARDWARE_BUDGET - active,
        "passes_strict_budget": active < HARDWARE_BUDGET,
        "event_path": {
            "name": scenario["event_label"],
            "executions": event_executions,
            "instructions": event_instructions,
            "cycles": event_cycles,
            "active_share_percent": round(event_cycles * 100 / active, 1),
        },
        "sparse_actor_draws": sparse_draws,
    }


def main() -> None:
    report = {
        "captured": "2026-07-26",
        "hardware_budget_cycles": HARDWARE_BUDGET,
        "method": (
            "controlled frame_render_impl injection with explicit A/B actor metadata; "
            "trace begins at frame_render_impl and ends at the next invocation"
        ),
        "scenarios": {},
    }
    raw_path = BUILD / "remaining-paths.raw.trace"
    all_sections = trace_lines(raw_path) if raw_path.exists() else None
    for pair_index, (stem, scenario) in enumerate(SCENARIOS.items()):
        if all_sections is not None:
            scenario_sections = split_trace(
                all_sections,
                scenario["owners"],
                stem,
                pair_index,
            )
        else:
            scenario_sections = {}
            for owner in scenario["owners"]:
                output = BUILD / f"remaining-{stem}-owner-{owner.lower()}.trace"
                section = [
                    line
                    for line in output.read_text(encoding="ascii").splitlines()
                    if TRACE_RE.match(line)
                ]
                section[0] = re.sub(r"dt=\d+$", "dt=72", section[0])
                output.write_text("\n".join(section) + "\n", encoding="ascii")
                scenario_sections[owner] = section
        owner_profiles = {
            owner: profile(lines, scenario)
            for owner, lines in scenario_sections.items()
        }
        report["scenarios"][stem] = {
            "label": scenario["label"],
            "sequence": scenario["sequence"],
            "owners": owner_profiles,
        }

    report_path = BUILD / "remaining-budget-profile.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="ascii")
    for stem, scenario in report["scenarios"].items():
        summary = ", ".join(
            f"{owner} {values['active_cycles']} "
            f"({'pass' if values['passes_strict_budget'] else 'fail'})"
            for owner, values in scenario["owners"].items()
        )
        print(f"{stem}: {summary}")


if __name__ == "__main__":
    main()
