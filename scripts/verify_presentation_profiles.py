#!/usr/bin/env python3
"""Verify complete A/B popup and death presentation profile distributions."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from verify_performance_baseline import measured, symbols, trace_sections


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
TARGET = 27_000


def blocks(path: Path) -> list[tuple[str, str]]:
    result = []
    label = None
    lines: list[str] = []
    for line in path.read_text(encoding="ascii").splitlines():
        if line.startswith("=== ") and line.endswith(" ==="):
            if label is not None:
                result.append((label, "\n".join(lines) + "\n"))
            label = line[4:-4]
            lines = []
        else:
            lines.append(line)
    if label is not None:
        result.append((label, "\n".join(lines) + "\n"))
    return result


def sections_for(text: str, name: str, frame_pc: str) -> list[dict[str, object]]:
    temporary = BUILD / "perf-presentation-verify.tmp.trace"
    temporary.write_text(text, encoding="ascii")
    try:
        return trace_sections(temporary, frame_pc)
    except ValueError as error:
        raise ValueError(f"{name}: {error}") from error
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    frame_pc = symbols(BUILD / "ladybug-enemy-runtime.map")["frame_render_impl"]
    popup = []
    for label, text in blocks(BUILD / "perf-presentation-popup.raw.trace"):
        sections = sections_for(text, label, frame_pc)[-2:]
        for owner, section in zip(("A", "B"), sections):
            item = measured(section, owner)
            item["case"] = label[len("popup:"):]
            popup.append(item)
    death = []
    for label, text in blocks(BUILD / "perf-presentation-death.raw.trace"):
        _, frame, owner = label.split(":")
        item = measured(sections_for(text, label, frame_pc)[0], owner)
        item["frame"] = int(frame)
        death.append(item)
    failures = [item for item in popup + death
                if int(item["active_cycles"]) > TARGET]
    report = {
        "captured": date.today().isoformat(),
        "measurement_contract": (
            "complete frame_render_impl-to-next-render-call active interval; "
            "only identified SYNC waits excluded"
        ),
        "engineering_target_cycles": TARGET,
        "popup": popup,
        "death": death,
        "acceptance": {
            "all_popup_colour_multiplier_owners": not any(
                item in failures for item in popup),
            "all_death_frames_owners": not any(
                item in failures for item in death),
        },
    }
    (BUILD / "performance-presentation.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="ascii")
    popup_max = max(int(item["active_cycles"]) for item in popup)
    death_max = max(int(item["active_cycles"]) for item in death)
    if failures:
        raise SystemExit(
            f"presentation profile: popup max={popup_max}, death max={death_max}; "
            f"{len(failures)} intervals exceed {TARGET}"
        )
    print(f"presentation profile: popup max={popup_max}, death max={death_max}; all A/B cases pass {TARGET}")


if __name__ == "__main__":
    main()
