#!/usr/bin/env python3
"""Reconcile the RSCH-006 TFM timing boundary through XRoar."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import statistics
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/bench/6309_tfm_timing.s"
MONITOR_SOURCE = ROOT / "docs/reference/xroar/src/monitor.c"
DEFAULT_XROAR = ROOT / "docs/reference/xroar/src/xroar"
RESULT_BASE = 0x0200
TFM_SRC = 0x0800
TFM_DST = 0x1800
TFM_STRIDE = 152
TFM_ROW_BYTES = 8
TFM_GUARD = 0x2200
SIGNATURE = b"R6TF"
CASES = (
    ("boundary", "case_boundary_start", "case_boundary_end"),
    ("fixed_8_byte", "case_fixed_start", "case_fixed_end"),
    ("source_aligned_rows", "case_rows_start", "case_rows_end"),
)


def load_base():
    path = ROOT / "scripts/benchmark_6309.py"
    spec = importlib.util.spec_from_file_location("rsch006_base", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load shared benchmark monitor helpers")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def symbols(path: Path) -> dict[str, int]:
    return {
        name: int(value, 16)
        for name, value in re.findall(
            r"^Symbol: (\w+) .* = ([0-9A-Fa-f]+)$",
            path.read_text(encoding="ascii"), re.MULTILINE,
        )
    }


def assemble(lwasm: str, output_dir: Path, variant: str, isa: str,
             rows: int, candidate: bool) -> tuple[Path, Path, str]:
    rom = output_dir / f"{variant}-{isa}-{rows}.rom"
    listing = output_dir / f"{variant}-{isa}-{rows}.lst"
    map_path = output_dir / f"{variant}-{isa}-{rows}.map"
    command = [
        lwasm, "-3" if isa == "6309" else "-9", "--format=raw",
        f"--output={rom}", f"--list={listing}", "--symbols",
        f"--map={map_path}", "-D", f"BENCH_ROWS={rows}",
    ]
    if candidate:
        command += ["-D", "BENCH_CANDIDATE=1"]
    command.append(str(SOURCE))
    completed = subprocess.run(command, capture_output=True, text=True)
    output = (completed.stdout + completed.stderr).strip()
    if completed.returncode:
        raise RuntimeError(f"assembly failed for {variant}/{isa}/{rows}: {output}")
    raw = rom.read_bytes()
    if len(raw) > 0x4000:
        raise RuntimeError(f"{variant}/{isa}/{rows}: ROM exceeds 16 KiB")
    rom.write_bytes(raw + b"\xff" * (0x4000 - len(raw)))
    return rom, map_path, output


def read(base, client, address: int, length: int) -> bytes:
    return base.read_bytes(client, address, length)


def run_case(base, xroar: Path, rom: Path, map_path: Path, cpu: str,
             rows: int, variant: str, timeout: float) -> dict:
    syms = symbols(map_path)
    required = ["entry", "benchmark_start", "benchmark_done"]
    required.extend(label for _, start, end in CASES for label in (start, end))
    missing = [label for label in required if label not in syms]
    if missing:
        raise RuntimeError(f"{variant}/{cpu}/{rows}: missing symbols {missing}")
    monitor = base.load_monitor()
    process, client = base.launch(monitor, xroar, rom, cpu)
    phase = "startup identity"
    try:
        phase = "entry synchronization"
        entry_id = base.set_breakpoint(client, syms["entry"])
        entry_hit = base.run_to_breakpoint(client, timeout)
        if entry_hit.get("pc") != syms["entry"]:
            raise RuntimeError(f"entry mismatch: {entry_hit}")
        base.clear_breakpoint(client, entry_id)

        phase = "startup identity"
        identity = base.wait_for_live_identity(
            client, rom, syms["benchmark_start"], 64, timeout
        )
        phase = "benchmark start"
        start_id = base.set_breakpoint(client, syms["benchmark_start"])
        hit = base.run_to_breakpoint(client, timeout)
        if hit.get("pc") != syms["benchmark_start"]:
            raise RuntimeError(f"benchmark start mismatch: {hit}")
        marker = read(base, client, RESULT_BASE, 4)
        if marker != SIGNATURE:
            raise RuntimeError(f"marker mismatch: {marker.hex()} != {SIGNATURE.hex()}")
        startup_timing = base.read_timing(client)
        base.clear_breakpoint(client, start_id)

        cases = {}
        for name, start_label, end_label in CASES:
            phase = f"{name}/start"
            if syms[start_label] == syms["benchmark_start"]:
                begin_hit = hit
                begin = startup_timing
            else:
                begin_id = base.set_breakpoint(client, syms[start_label])
                begin_hit = base.run_to_breakpoint(client, timeout)
                if begin_hit.get("pc") != syms[start_label]:
                    raise RuntimeError(f"{name} start mismatch: {begin_hit}")
                begin = base.read_timing(client)
                base.clear_breakpoint(client, begin_id)

            phase = f"{name}/end"
            end_id = base.set_breakpoint(client, syms[end_label])
            end_hit = base.run_to_breakpoint(client, timeout)
            if end_hit.get("pc") != syms[end_label]:
                raise RuntimeError(f"{name} end mismatch: {end_hit}")
            end = base.read_timing(client)
            base.clear_breakpoint(client, end_id)
            event_ticks = end["event_ticks"] - begin["event_ticks"]
            cpu_cycles = end["cpu_cycles"] - begin["cpu_cycles"]
            cases[name] = {
                "event_ticks": event_ticks,
                "cpu_cycles": cpu_cycles,
                "event_tick_cpu_ratio_pass": event_ticks == cpu_cycles * 16,
                "start": begin,
                "end": end,
                "start_halt": begin_hit,
                "end_halt": end_hit,
                "marker_addresses": {
                    "start": f"{syms[start_label]:04X}",
                    "end": f"{syms[end_label]:04X}",
                },
            }

        phase = "benchmark done"
        done_id = base.set_breakpoint(client, syms["benchmark_done"])
        done_hit = base.run_to_breakpoint(client, timeout)
        if done_hit.get("pc") != syms["benchmark_done"]:
            raise RuntimeError(f"benchmark done mismatch: {done_hit}")
        done_timing = base.read_timing(client)
        source_rows = [
            read(base, client, TFM_SRC + row * TFM_STRIDE, TFM_ROW_BYTES)
            for row in range(rows)
        ]
        destination_rows = [
            read(base, client, TFM_DST + row * TFM_STRIDE, TFM_ROW_BYTES)
            for row in range(rows)
        ]
        guard = read(base, client, TFM_GUARD, 1)
        base.clear_breakpoint(client, done_id)
        correctness = {
            "execution_marker": marker == SIGNATURE,
            "source_destination_rows_match": source_rows == destination_rows,
            "guard_preserved": guard == b"\xA5",
            "all_event_tick_ratios": all(
                item["event_tick_cpu_ratio_pass"] for item in cases.values()
            ),
        }
        return {
            "variant": variant,
            "cpu": cpu,
            "rows": rows,
            "rom_sha256": digest(rom.read_bytes()),
            "source_sha256": digest(SOURCE.read_bytes()),
            "startup_identity": identity,
            "entry_halt": entry_hit,
            "benchmark_start": f"{syms['benchmark_start']:04X}",
            "benchmark_done": f"{syms['benchmark_done']:04X}",
            "live_execution_marker": marker.decode("ascii"),
            "startup_timing": startup_timing,
            "done_timing": done_timing,
            "cases": cases,
            "source_rows": [item.hex() for item in source_rows],
            "destination_rows": [item.hex() for item in destination_rows],
            "guard": guard.hex(),
            "correctness": correctness,
        }
    except Exception as exc:
        raise RuntimeError(f"{variant}/{cpu}/{rows} failed in {phase}: {exc}") from exc
    finally:
        client.close()
        base.stop(process)


def summarize(samples: list[dict]) -> dict:
    cycles = [sample["cpu_cycles"] for sample in samples]
    ticks = [sample["event_ticks"] for sample in samples]
    median = statistics.median(cycles)
    return {
        "cpu_cycle_samples": cycles,
        "event_tick_samples": ticks,
        "median_cpu_cycles": median,
        "minimum_cpu_cycles": min(cycles),
        "maximum_cpu_cycles": max(cycles),
        "relative_spread": (max(cycles) - min(cycles)) / median if median else 0,
        "repeatability_pass": len(set(cycles)) == 1 or
        (max(cycles) - min(cycles)) / median <= 0.01,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lwasm", default="lwasm")
    parser.add_argument("--xroar", type=Path, default=DEFAULT_XROAR)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "build/rsch006-tfm")
    parser.add_argument("--rows", type=int, nargs="+", default=[1, 2, 4, 8, 16])
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args()
    if any(row <= 0 or row > 16 for row in args.rows):
        raise SystemExit("rows must be between 1 and 16")
    if args.repeats < 3:
        raise SystemExit("repeats must be at least 3")
    if args.timeout <= 0 or args.timeout > 5:
        raise SystemExit("timeout must be greater than zero and at most 5 seconds")
    for dependency in (SOURCE, MONITOR_SOURCE, args.xroar):
        if not dependency.is_file():
            raise SystemExit(f"required dependency missing: {dependency}")

    base = load_base()
    args.output.mkdir(parents=True, exist_ok=True)
    all_rows = []
    with tempfile.TemporaryDirectory(prefix="rsch006-") as temporary:
        directory = Path(temporary)
        for rows in args.rows:
            baseline_rom, baseline_map, baseline_build = assemble(
                args.lwasm, directory, "baseline", "6809", rows, False
            )
            candidate_rom, candidate_map, candidate_build = assemble(
                args.lwasm, directory, "candidate", "6309", rows, True
            )
            samples = {"baseline": [], "candidate": []}
            failures = []
            for _ in range(args.repeats):
                for name, rom, map_path, cpu in (
                    ("baseline", baseline_rom, baseline_map, "6809"),
                    ("candidate", candidate_rom, candidate_map, "6309"),
                ):
                    try:
                        samples[name].append(run_case(
                            base, args.xroar, rom, map_path, cpu,
                            rows, name, args.timeout
                        ))
                    except Exception as exc:
                        failures.append(str(exc))
            if failures:
                raise SystemExit("RSCH-006 control failure: " + " | ".join(failures))
            summaries = {
                name: {
                    case: summarize([sample["cases"][case] for sample in runs])
                    for case, _, _ in CASES
                }
                for name, runs in samples.items()
            }
            all_rows.append({
                "rows": rows,
                "baseline_6809_candidate_6309_roms_differ":
                    baseline_rom.read_bytes() != candidate_rom.read_bytes(),
                "build_output": {"baseline": baseline_build, "candidate": candidate_build},
                "runs": samples,
                "timing": summaries,
            })

    fixed = [row["timing"]["candidate"]["fixed_8_byte"]["median_cpu_cycles"]
             for row in all_rows]
    baseline_fixed = [row["timing"]["baseline"]["fixed_8_byte"]["median_cpu_cycles"]
                      for row in all_rows]
    candidate_rows = [row["timing"]["candidate"]["source_aligned_rows"]["median_cpu_cycles"]
                      for row in all_rows]
    baseline_rows = [row["timing"]["baseline"]["source_aligned_rows"]["median_cpu_cycles"]
                     for row in all_rows]
    checks = {
        "all_correctness": all(
            all(all(sample["correctness"].values()) for sample in runs)
            for row in all_rows for runs in row["runs"].values()
        ),
        "all_repeatability": all(
            summary["repeatability_pass"]
            for row in all_rows for variant in ("baseline", "candidate")
            for summary in row["timing"][variant].values()
        ),
        "all_marker_ratios": all(
            sample["correctness"]["all_event_tick_ratios"]
            for row in all_rows for runs in row["runs"].values() for sample in runs
        ),
        "fixed_candidate_not_outlier": max(fixed) < 1000,
        "source_aligned_candidate_below_baseline": all(
            candidate < baseline
            for baseline, candidate in zip(baseline_rows, candidate_rows)
        ),
        "source_aligned_series_increases": all(
            right > left for left, right in zip(candidate_rows, candidate_rows[1:])
        ) and all(right > left for left, right in zip(baseline_rows, baseline_rows[1:])),
    }
    first_sample = all_rows[0]["runs"]["candidate"][0]
    evidence = {
        "schema": "ladybug-rsch006-tfm-timing-v1",
        "ticket": "RSCH-006",
        "source": str(SOURCE.relative_to(ROOT)),
        "source_sha256": digest(SOURCE.read_bytes()),
        "monitor_source": str(MONITOR_SOURCE.relative_to(ROOT)),
        "monitor_source_sha256": digest(MONITOR_SOURCE.read_bytes()),
        "xroar": str(args.xroar),
        "xroar_sha256": digest(args.xroar.read_bytes()),
        "timing_source": {
            "method": "read_cycles",
            "response_fields": ["event_ticks", "cpu_cycles"],
            "cpu_cycle_conversion": "event_ticks / 16",
            "delta_rule": "read both fields at each execution marker; subtract endpoint values",
            "provenance_probe": first_sample["startup_timing"],
        },
        "startup_control": {
            "identity": "C000 prefix plus 64-byte benchmark window before first breakpoint",
            "deadline_seconds": args.timeout,
            "stale_window_is_failure": True,
        },
        "marker_controls": {
            "boundary": "single NOP between execution markers",
            "fixed_8_byte": "one 8-byte TFM or equivalent byte-copy window",
            "source_aligned_rows": "8 visible bytes per row plus 152-byte stride",
        },
        "rows": all_rows,
        "summary": {
            "fixed_candidate_medians": fixed,
            "fixed_baseline_medians": baseline_fixed,
            "source_aligned_candidate_medians": candidate_rows,
            "source_aligned_baseline_medians": baseline_rows,
        },
        "checks": checks,
        "interpretation": (
            "The fixed and source-aligned TFM windows are valid only when startup "
            "identity, marker halts, event-tick conversion, correctness, and "
            "repeatability all pass. The prior 364937-cycle baseline is rejected "
            "if the repaired fixed control remains below 1000 cycles."
        ),
    }
    output = args.output / "rsch006-tfm-timing.json"
    output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="ascii")
    if not all(checks.values()):
        raise SystemExit(f"RSCH-006 checks failed: {output}")
    print("RSCH-006 TFM provenance, startup, fixed-boundary, and row controls passed")
    print(f"fixed_candidate_medians={fixed}")
    print(f"source_aligned_candidate_medians={candidate_rows}")
    print(f"evidence={output}")


if __name__ == "__main__":
    main()
