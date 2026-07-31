#!/usr/bin/env python3
"""Capture every popup combination and death frame on both framebuffer owners."""

from pathlib import Path

from capture_performance_baseline import (
    BUILD, COMMON_PATCHES, ENEMY_TABLE, capture_snapshot, capture_trace,
    patch_snapshot, symbol,
)


def append_trace(output: Path, label: str, trace: Path) -> None:
    with output.open("a", encoding="ascii") as destination:
        destination.write(f"=== {label} ===\n")
        destination.write(trace.read_text(encoding="ascii"))


def main() -> None:
    frame_pc = symbol(BUILD / "ladybug-enemy-runtime.map", "frame_render_impl")
    stop_pc = symbol(BUILD / "ladybug.map", "main_render")
    baseline = BUILD / "perf-presentation-baseline.sna"
    capture_snapshot(baseline, frame_pc, 20)
    static = BUILD / "perf-presentation-static.sna"
    patch_snapshot(
        baseline, static,
        COMMON_PATCHES + ["A477=FF", "A47F=FF", "A487=FF", "A48F=FF"],
        [f"A470={ENEMY_TABLE}"],
    )
    hydrated = BUILD / "perf-presentation-hydrated.sna"
    capture_snapshot(hydrated, frame_pc, 5, static)

    popup_output = BUILD / "perf-presentation-popup.raw.trace"
    popup_output.write_text("", encoding="ascii")
    colour_frames = ((1, 2, "red"), (2, 1, "yellow"), (3, 0, "blue"))
    for colour, frame, colour_name in colour_frames:
        for multiplier in (1, 2, 3, 5):
            snapshot = BUILD / "perf-presentation-case.sna"
            patch_snapshot(hydrated, snapshot, [
                f"002F={colour:02X}", "0051=1E", f"0052={frame:02X}",
                f"0053={multiplier:02X}", "0060=00", "0087=00",
                "007F=00", "0080=01", "A901=00", "AA01=00",
                "A9A8=00", "AAA8=00",
            ])
            trace = BUILD / "perf-presentation-case.raw.trace"
            capture_trace(snapshot, trace, stop_pc, 4)
            append_trace(popup_output, f"popup:{colour_name}:x{multiplier}", trace)

    death_output = BUILD / "perf-presentation-death.raw.trace"
    death_output.write_text("", encoding="ascii")
    timers = [0] + [29 + (index - 1) * 5 for index in range(1, 13)]
    for frame in range(14):
        for owner, front, back in (("A", 1, 0), ("B", 0, 1)):
            snapshot = BUILD / "perf-presentation-case.sna"
            state = 2 if frame == 13 else 1
            timer = 0 if frame == 13 else timers[frame]
            patch_snapshot(hydrated, snapshot, [
                f"003A={timer:02X}", f"004D={state:02X}",
                f"004E={frame:02X}", "0062=02", "0060=00", "0087=00",
                "007F=80", "0080=00", "A901=00", "AA01=00",
                "A9A8=00", "AAA8=00", f"008F={front:02X}",
                f"0090={back:02X}",
            ])
            trace = BUILD / "perf-presentation-case.raw.trace"
            capture_trace(snapshot, trace, stop_pc, 1)
            append_trace(death_output, f"death:{frame}:{owner}", trace)

    print("presentation capture: 12 popup combinations and 14 death frames on A/B written")


if __name__ == "__main__":
    main()
