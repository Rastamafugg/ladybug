#!/usr/bin/env python3
"""Capture reproducible current-revision performance scenarios in XRoar."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

from patch_snapshot_state import patch_snapshot
from read_snapshot import RAM_MARKER, cpu_to_phys, find_ram


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
ROM = BUILD / "ladybug.rom"
MATERIAL = BUILD / "performance-capture-material.json"
ENEMY_TABLE = BUILD / "four-enemy-delta-enemy-table.bin"
NEST_OFFSET = 0x57EC - 0x2000


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="reuse the existing canonical build outputs",
    )
    parser.add_argument(
        "--gate-only",
        action="store_true",
        help="capture only the hydrated gate diagonal/final sequence",
    )
    parser.add_argument(
        "--bounded-frames", action="store_true",
        help="capture one- and two-frame horizontal snapshots, then stop",
    )
    parser.add_argument(
        "--death-reset-only", action="store_true",
        help="capture only focused A/B death-reset traces, then stop",
    )
    return parser.parse_args()


def symbol(path: Path, name: str) -> int:
    pattern = re.compile(rf"^Symbol: {re.escape(name)} .* = ([0-9A-Fa-f]+)$")
    for line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if match:
            return int(match.group(1), 16)
    raise ValueError(f"{path}: missing symbol {name}")


def xroar_base() -> list[str]:
    executable = shutil.which("xroar")
    if not executable:
        raise SystemExit("capture baseline: xroar is not installed")
    return [
        executable,
        "-ui", "null",
        "-ao", "null",
        "-machine", "coco3",
        "-ram", "512",
        "-cart-type", "gmc",
        "-cart-rom", str(ROM),
        "-no-ratelimit",
    ]


def run_xroar(arguments: list[str], output: Path) -> None:
    with output.open("w", encoding="ascii") as stream:
        result = subprocess.run(
            xroar_base() + arguments,
            cwd=ROOT,
            stdout=stream,
            stderr=subprocess.STDOUT,
            check=False,
        )
    if result.returncode:
        raise SystemExit(
            f"capture baseline: XRoar returned {result.returncode}; see {output}"
        )


def capture_snapshot(output: Path, frame_pc: int, count: int, source: Path | None = None) -> None:
    arguments = []
    if source is None:
        arguments += ["-ram-init", "0", "-cart-autorun"]
    else:
        arguments += ["-load", str(source)]
    arguments += [
        "-trap", f"pc=0x{frame_pc:04x}",
        "-trap-range", str(count),
        "-trap-snap", str(output),
        "-trap-timeout", "1",
    ]
    run_xroar(arguments, BUILD / f"{output.stem}.log")


def capture_trace(snapshot: Path, output: Path, stop_pc: int, intervals: int, timeout: int = 1) -> None:
    # A snapshot is taken at frame_render_impl, after main_render's call site.
    # The first following main_render precedes the next frame-render entry, so
    # N+1 main_render traps are required to close N measured intervals.
    run_xroar(
        [
            "-load", str(snapshot),
            "-trace",
            "-trace-timing",
            "-trap", f"pc=0x{stop_pc:04x}",
            "-trap-range", str(intervals),
            "-trap-no-trace",
            "-trap-timeout", str(timeout),
        ],
        output,
    )
def semantic_bytes(path: Path, data: bytes) -> bytes:
    if path.suffix in (".py", ".s", ".trace"):
        data = data.replace(b"\r\n", b"\n")
    return data


def semantic_sha256(path: Path) -> str:
    data = semantic_bytes(path, path.read_bytes())
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
        raise SystemExit("capture baseline: semantic hash line-ending/mutation contract failed")


def write_capture_material() -> None:
    verify_hash_contract()
    sources = (
        Path("src/main.s"), Path("src/enemy_runtime.s"),
        Path("src/perimeter_reset_helper.s"), Path("scripts/build_sparse_sprites.py"),
        Path("scripts/build_screen.py"),
    )
    traces = sorted(BUILD.glob("perf-*.raw.trace"))
    MATERIAL.write_text(json.dumps({
        "rom_sha256": semantic_sha256(ROM),
        "source_sha256": {path.as_posix(): semantic_sha256(ROOT / path) for path in sources},
        "trace_sha256": {path.name: semantic_sha256(path) for path in traces},
    }, indent=2) + "\n", encoding="ascii")


def write_nest_proof(snapshot: Path, output: Path, framebuffer_base: int) -> None:
    ram = find_ram(snapshot.read_bytes())
    cache_physical = cpu_to_phys(
        symbol(BUILD / "ladybug-enemy-runtime.map", "ENEMY_NEST_CACHE")
    )
    proof = bytearray(ram[cache_physical:cache_physical + 512])
    start = framebuffer_base + NEST_OFFSET
    for row in range(16):
        offset = start + row * 160
        proof.extend(ram[offset:offset + 8])
    output.write_bytes(proof)


COMMON_PATCHES = [
    "0030=7F", "0031=FF",  # keep bonus-colour work outside the sample
    "004A=FF",              # keep perimeter work outside the sample
    "0050=FF",              # keep player animation outside enemy-only cases
    "0055=40",              # keep nest animation outside movement cases
    "0058=04", "0059=04", "005A=02",
    "0060=01", "0061=01", "007F=01", "0080=00", "0087=0A",
    "A908=00", "AA08=00",
    "A92C=00", "A92D=00", "A92E=00", "A92F=00",
    "AA2C=00", "AA2D=00", "AA2E=00", "AA2F=00",
]


def moving_patch(directions: tuple[int, int, int, int]) -> list[str]:
    result = [
        "A473=01", "A47B=01", "A483=01", "A48B=01",
        "0055=40", "0060=00", "0061=00", "0087=00",
    ]
    for address, direction in zip((0xA477, 0xA47F, 0xA487, 0xA48F), directions):
        result.append(f"{address:04X}={direction:02X}")
    return result


def swap_framebuffer_owners(source: Path, target: Path, patches: list[str]) -> None:
    """Create an equivalent logical state with physical A/B ownership reversed."""
    snapshot = bytearray(source.read_bytes())
    start = snapshot.index(RAM_MARKER) + len(RAM_MARKER)
    ram = memoryview(snapshot)[start:start + 0x80000]
    def swap(left: int, right: int, size: int) -> None:
        saved = bytes(ram[left:left + size])
        ram[left:left + size] = ram[right:right + size]
        ram[right:right + size] = saved
    swap(0x60000, 0x58000, 0x8000)  # physical framebuffer A/B pages
    base = 0x34 << 13
    swap(base + 0x900, base + 0xA00, 0x100)  # ownership/pending ledgers
    swap(base + 0x300, base + 0xB00, 0x80)   # player save-under
    swap(base + 0x690, base + 0xB80, 0x200)  # four enemy save-under records
    for assignment in patches:
        address, value = assignment.split("=", 1)
        ram[cpu_to_phys(int(address, 16))] = int(value, 16)
    target.write_bytes(snapshot)


def main() -> None:
    args = parse_args()
    if not args.skip_build:
        subprocess.run([str(ROOT / "scripts" / "build.sh"), "build"], cwd=ROOT, check=True)

    frame_pc = symbol(BUILD / "ladybug-enemy-runtime.map", "frame_render_impl")
    stop_pc = symbol(BUILD / "ladybug.map", "main_render")

    baseline = BUILD / "perf-baseline.sna"
    capture_snapshot(baseline, frame_pc, 20)

    static = BUILD / "perf-four-static.sna"
    patch_snapshot(
        baseline,
        static,
        COMMON_PATCHES + [
            "A477=FF", "A47F=FF", "A487=FF", "A48F=FF",
        ],
        [f"A470={ENEMY_TABLE}"],
    )
    hydrated = BUILD / "perf-four-hydrated.sna"
    capture_snapshot(hydrated, frame_pc, 5, static)

    if args.death_reset_only:
        for owner, front, back in (("a", 1, 0), ("b", 0, 1)):
            death_reset = BUILD / f"perf-death-reset-{owner}.sna"
            patch_snapshot(
                hydrated,
                death_reset,
                [
                    "003A=00", "004D=02", "004E=0D", "0062=02",
                    "0060=01", "0087=08", "007F=80", "0080=00",
                    f"008F={front:02X}", f"0090={back:02X}",
                ],
            )
            capture_trace(
                death_reset,
                BUILD / f"perf-death-reset-{owner}.raw.trace",
                stop_pc,
                2,
            )
        print("performance capture: focused death-reset traces written")
        return

    if args.gate_only:
        gate = BUILD / "perf-gate.sna"
        patch_snapshot(
            hydrated,
            gate,
            moving_patch((1, 1, 3, 3)) + [
                "0018=01", "0019=00",
                "0088=01", "0089=00", "008A=00", "008B=00",
                "008D=00", "008E=00", "A240=01",
            ],
        )
        capture_snapshot(BUILD / "perf-gate-final.sna", frame_pc, 1, gate)
        capture_trace(gate, BUILD / "perf-gate.raw.trace", stop_pc, 4)
        reversed_gate = BUILD / "perf-gate-reversed.sna"
        swap_framebuffer_owners(
            hydrated,
            reversed_gate,
            moving_patch((1, 1, 3, 3)) + [
                "0018=01", "0019=00",
                "0088=01", "0089=00", "008A=00", "008B=00",
                "008D=00", "008E=00", "A240=01",
                "008F=00", "0090=01",
            ],
        )
        capture_trace(reversed_gate, BUILD / "perf-gate-reversed.raw.trace", stop_pc, 4)
        print("performance capture: current-revision gate scenario written to build/")
        return

    horizontal = BUILD / "perf-four-horizontal.sna"
    patch_snapshot(hydrated, horizontal, moving_patch((1, 1, 3, 3)))
    if args.bounded_frames:
        capture_snapshot(BUILD / "perf-bounded-one.sna", stop_pc, 1, horizontal)
        capture_snapshot(BUILD / "perf-bounded-two.sna", stop_pc, 2, horizontal)
        print("performance capture: bounded one/two-frame snapshots written")
        return
    # Capture beyond the requested closed distribution.  XRoar ends tracing at
    # main_render, so the final frame-render tail has no closing boundary and
    # must be discarded by the verifier rather than becoming a favorable or
    # omitted timing observation.
    capture_trace(horizontal, BUILD / "perf-four-horizontal.raw.trace", stop_pc, 14, timeout=5)

    vertical = BUILD / "perf-four-vertical.sna"
    patch_snapshot(hydrated, vertical, moving_patch((0, 0, 2, 2)))
    capture_trace(vertical, BUILD / "perf-four-vertical.raw.trace", stop_pc, 6)
    vertical_a = BUILD / "perf-four-vertical-a.sna"
    patch_snapshot(
        vertical,
        vertical_a,
        ["008F=00", "0090=01"],
    )
    capture_trace(
        vertical_a,
        BUILD / "perf-four-vertical-a.raw.trace",
        stop_pc,
        4,
    )

    capture_trace(baseline, BUILD / "perf-player.raw.trace", stop_pc, 9)

    for owner, front, back in (("a", 0, 1), ("b", 1, 0)):
        animation = BUILD / f"perf-animation-{owner}.sna"
        patch_snapshot(
            hydrated,
            animation,
            moving_patch((1, 1, 3, 3)) + [
                "0055=01", "005A=00",
                "A901=00", "AA01=00",
                f"008F={front:02X}", f"0090={back:02X}",
            ],
        )
        capture_trace(
            animation,
            BUILD / f"perf-animation-{owner}.raw.trace",
            stop_pc,
            4,
        )
        capture_snapshot(
            BUILD / f"perf-animation-{owner}-fast.sna",
            frame_pc,
            2,
            animation,
        )
        write_nest_proof(
            BUILD / f"perf-animation-{owner}-fast.sna",
            BUILD / f"perf-animation-{owner}-fast-proof.bin",
            0x58000 if owner == "a" else 0x60000,
        )
        full_animation = BUILD / f"perf-animation-{owner}-full-source.sna"
        patch_snapshot(
            animation,
            full_animation,
            ["0060=01", "0087=02"],
        )
        capture_snapshot(
            BUILD / f"perf-animation-{owner}-full.sna",
            frame_pc,
            2,
            full_animation,
        )
        write_nest_proof(
            BUILD / f"perf-animation-{owner}-full.sna",
            BUILD / f"perf-animation-{owner}-full-proof.bin",
            0x58000 if owner == "a" else 0x60000,
        )

    popup = BUILD / "perf-popup.sna"
    patch_snapshot(
        hydrated,
        popup,
        ["0051=1E", "0052=02", "0053=05", "0080=01", "0055=40"],
    )
    capture_trace(popup, BUILD / "perf-popup.raw.trace", stop_pc, 5)

    for owner, front, back in (("a", 1, 0), ("b", 0, 1)):
        death = BUILD / f"perf-death-{owner}.sna"
        patch_snapshot(
            hydrated,
            death,
            [
                "003A=00", "004D=02", "004E=0D", "0062=02",
                "0060=00", "0087=00", "007F=80", "0080=00",
                "A901=00", "AA01=00", "A9A8=00", "AAA8=00",
                f"008F={front:02X}", f"0090={back:02X}",
            ],
        )
        capture_trace(
            death,
            BUILD / f"perf-death-{owner}.raw.trace",
            stop_pc,
            2,
        )
        death_reset = BUILD / f"perf-death-reset-{owner}.sna"
        patch_snapshot(
            hydrated,
            death_reset,
            [
                "003A=00", "004D=02", "004E=0D", "0062=02",
                "0060=01", "0087=08", "007F=80", "0080=00",
                f"008F={front:02X}", f"0090={back:02X}",
            ],
        )
        capture_trace(
            death_reset,
            BUILD / f"perf-death-reset-{owner}.raw.trace",
            stop_pc,
            2,
        )

    # Force the conservative discontinuity fallback independently for both
    # owners. These stale prior pointers are compared but never dereferenced;
    # each differs from the current destination by more than a legal strip.
    for owner, front, back in (("a", 1, 0), ("b", 0, 1)):
        discontinuity = BUILD / f"perf-discontinuity-{owner}.sna"
        patch_snapshot(
            hydrated,
            discontinuity,
            moving_patch((1, 1, 3, 3)) + [
                "0061=01", "0087=02",
                "A909=20", "A90A=00", "A911=21", "A912=00",
                "A919=22", "A91A=00", "A921=23", "A922=00",
                "AA09=20", "AA0A=00", "AA11=21", "AA12=00",
                "AA19=22", "AA1A=00", "AA21=23", "AA22=00",
                f"008F={front:02X}", f"0090={back:02X}",
            ],
        )
        capture_trace(
            discontinuity,
            BUILD / f"perf-discontinuity-{owner}.raw.trace",
            stop_pc,
            4,
        )

    gate = BUILD / "perf-gate.sna"
    patch_snapshot(
        hydrated,
        gate,
        moving_patch((1, 1, 3, 3)) + [
            "0018=01", "0019=00",
            "0088=01", "0089=00", "008A=00", "008B=00",
            "008D=00", "008E=00", "A240=01",
        ],
    )
    capture_trace(gate, BUILD / "perf-gate.raw.trace", stop_pc, 4)

    write_capture_material()

    print("performance capture: current-revision scenarios written to build/")


if __name__ == "__main__":
    main()
