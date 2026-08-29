#!/usr/bin/env python3
"""Benchmark 6309 candidates against Ladybug renderer-shaped fixtures."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import statistics
import subprocess
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/bench/6309_hotpath_benchmark.s"
SIGNATURE = b"R4HT"
RESULT_BASE = 0x0200
RESULT_VARIANT = RESULT_BASE + 4
TFM_SRC = 0x0800
TFM_DST = 0x1800
TFM_STRIDE = 152
TFM_ROW_BYTES = 8
Q_SRC = 0x2000
Q_DST = 0x3000
Q_STRIDE = 152
Q_ROW_BYTES = 8
OIM_DST = 0x0700
OIM_COUNT = 8
CASE_LABELS = (
    ("tfm_hotpath", "case_tfm_hot_start", "case_tfm_hot_end"),
    ("ldq_stq_hotpath", "case_q_hot_start", "case_q_hot_end"),
    ("oim_hotpath", "case_oim_hot_start", "case_oim_hot_end"),
    ("mixed_transparency_rejection", "case_reject_start", "case_reject_end"),
)


def load_base():
    path = ROOT / "scripts/benchmark_6309.py"
    spec = importlib.util.spec_from_file_location("benchmark_6309_base", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load shared benchmark monitor helpers")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def assemble(base, lwasm: str, output_dir: Path, variant: str, isa: str,
             rows: int, candidate: bool) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
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
    return rom, map_path


def read(base, client, address: int, length: int) -> bytes:
    return base.read_bytes(client, address, length)


def run_until_breakpoint(base, client, timeout: float) -> dict:
    """Use the monitor's halted state while retaining a bounded deadline."""
    return base.run_to_breakpoint(client, timeout)


def run_case(base, xroar: Path, rom: Path, map_path: Path, cpu: str,
             rows: int, variant: str, timeout: float) -> dict:
    syms = base.symbols(map_path)
    required = ["benchmark_start", "benchmark_done"]
    required.extend(label for _, start, end in CASE_LABELS for label in (start, end))
    missing = [name for name in required if name not in syms]
    if missing:
        raise RuntimeError(f"{variant}/{cpu}/{rows}: missing symbols {missing}")

    monitor = base.load_monitor()
    process, client = base.launch(monitor, xroar, rom, cpu)
    try:
        rom_image = rom.read_bytes()
        expected_window = rom_image[syms["benchmark_start"] - 0xC000:
                                    syms["benchmark_start"] - 0xC000 + 64]
        identity_deadline = time.monotonic() + timeout
        live_prefix = b""
        live_window = b""
        while time.monotonic() < identity_deadline:
            live_prefix = read(base, client, 0xC000, 32)
            live_window = read(base, client, syms["benchmark_start"], 64)
            if live_prefix == rom_image[:32] and live_window == expected_window:
                break
            time.sleep(0.05)
        if live_prefix != rom_image[:32] or live_window != expected_window:
            raise RuntimeError(
                f"live ROM identity mismatch prefix={live_prefix.hex()} "
                f"window={live_window.hex()}"
            )
        start_id = base.set_breakpoint(client, syms["benchmark_start"])
        try:
            hit = run_until_breakpoint(base, client, timeout)
        except TimeoutError as exc:
            state = client.call("get_run_state", timeout=1.0)
            registers = client.call("read_registers", timeout=1.0)
            raise RuntimeError(
                f"benchmark start timeout state={state} registers={registers}"
            ) from exc
        if hit.get("pc") != syms["benchmark_start"]:
            raise RuntimeError(f"benchmark start mismatch: {hit}")
        marker = read(base, client, RESULT_BASE, 4)
        if marker != SIGNATURE:
            raise RuntimeError(
                f"live benchmark marker mismatch: {marker.hex()} != {SIGNATURE.hex()}"
            )
        start_timing = base.read_timing(client)
        base.clear_breakpoint(client, start_id)

        cases = {}
        for name, start_label, end_label in CASE_LABELS:
            begin_id = base.set_breakpoint(client, syms[start_label])
            hit = run_until_breakpoint(base, client, timeout)
            if hit.get("pc") != syms[start_label]:
                raise RuntimeError(f"{name} start mismatch: {hit}")
            begin = base.read_timing(client)
            base.clear_breakpoint(client, begin_id)
            end_id = base.set_breakpoint(client, syms[end_label])
            hit = run_until_breakpoint(base, client, timeout)
            if hit.get("pc") != syms[end_label]:
                raise RuntimeError(f"{name} end mismatch: {hit}")
            end = base.read_timing(client)
            base.clear_breakpoint(client, end_id)
            cases[name] = {
                "cpu_cycles": end["cpu_cycles"] - begin["cpu_cycles"],
                "event_ticks": end["event_ticks"] - begin["event_ticks"],
                "start": begin,
                "end": end,
            }

        done_id = base.set_breakpoint(client, syms["benchmark_done"])
        hit = run_until_breakpoint(base, client, timeout)
        if hit.get("pc") != syms["benchmark_done"]:
            raise RuntimeError(f"benchmark done mismatch: {hit}")
        done = base.read_timing(client)
        tfm_rows = [
            (read(base, client, TFM_SRC + row * TFM_STRIDE, TFM_ROW_BYTES),
             read(base, client, TFM_DST + row * TFM_STRIDE, TFM_ROW_BYTES))
            for row in range(rows)
        ]
        q_rows = [
            (read(base, client, Q_SRC + row * Q_STRIDE, Q_ROW_BYTES),
             read(base, client, Q_DST + row * Q_STRIDE, Q_ROW_BYTES))
            for row in range(rows)
        ]
        oim = read(base, client, OIM_DST, OIM_COUNT)
        variant_marker = read(base, client, RESULT_VARIANT, 1)[0]
        base.clear_breakpoint(client, done_id)
        expected_oim = bytes(0xAF if index % 2 == 0 else 0xFA
                             for index in range(OIM_COUNT))
        tfm_guard = read(base, client, 0x2200, 1)
        q_guard = read(base, client, 0x3A00, 1)
        oim_guard = read(base, client, 0x0710, 1)
        correctness = {
            "execution_marker": marker == SIGNATURE,
            "tfm_rows": all(src == dst for src, dst in tfm_rows),
            "tfm_guard": tfm_guard == b"\xA5",
            "tfm_guard_byte": tfm_guard.hex(),
            "ldq_stq_rows": all(src == dst for src, dst in q_rows),
            "ldq_stq_guard": q_guard == b"\x5A",
            "ldq_stq_guard_byte": q_guard.hex(),
            "oim_masks": oim == expected_oim,
            "oim_bytes": oim.hex(),
            "oim_guard": oim_guard == b"\x5A",
            "oim_guard_byte": oim_guard.hex(),
            "mixed_transparency_rejected": read(base, client, RESULT_BASE + 0x13, 1) == b"\x00",
        }
        return {
            "variant": variant,
            "cpu": cpu,
            "rows": rows,
            "rom_sha256": digest(rom.read_bytes()),
            "live_rom_prefix": live_prefix.hex(),
            "live_benchmark_window": live_window.hex(),
            "live_window_matches": live_window == expected_window,
            "source_sha256": digest(SOURCE.read_bytes()),
            "benchmark_start": f"{syms['benchmark_start']:04X}",
            "live_execution_marker": marker.decode("ascii"),
            "variant_marker": f"{variant_marker:02x}",
            "start_timing": start_timing,
            "done_timing": done,
            "cases": cases,
            "total_cpu_cycles": done["cpu_cycles"] - start_timing["cpu_cycles"],
            "total_event_ticks": done["event_ticks"] - start_timing["event_ticks"],
            "correctness": correctness,
        }
    finally:
        client.close()
        base.stop(process)


def timing_summary(samples: list[dict]) -> dict:
    values = [sample["cpu_cycles"] for sample in samples]
    ticks = [sample["event_ticks"] for sample in samples]
    median = statistics.median(values)
    spread = (max(values) - min(values)) / median if median else 1.0
    return {
        "samples": values,
        "event_tick_samples": ticks,
        "median_cpu_cycles": median,
        "min_cpu_cycles": min(values),
        "max_cpu_cycles": max(values),
        "relative_spread": spread,
        "repeatability_pass": spread <= 0.01 or len(set(values)) == 1,
    }


def row_scaling_summary(all_runs: list[dict], variant: str) -> dict:
    rows = [run["rows"] for run in all_runs]
    summaries = [run["timing"][variant]["ldq_stq_hotpath"]
                 for run in all_runs]
    medians = [summary["median_cpu_cycles"] for summary in summaries]
    if len(rows) < 2 or any(summary.get("status") == "invalid"
                            for summary in summaries):
        raise RuntimeError(f"{variant}: incomplete LDQ/STQ row series")
    if any(right <= left for left, right in zip(medians, medians[1:])):
        raise RuntimeError(f"{variant}: LDQ/STQ medians do not increase: {medians}")
    slopes = [(right - left) / (right_rows - left_rows)
              for left, right, left_rows, right_rows in zip(
                  medians, medians[1:], rows, rows[1:])]
    if max(slopes) - min(slopes) > 1:
        raise RuntimeError(f"{variant}: LDQ/STQ row slopes do not agree: {slopes}")
    return {"rows": rows, "median_cpu_cycles": medians, "per_row_slopes": slopes,
            "normalized_slope_spread": max(slopes) - min(slopes)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lwasm", default="lwasm")
    parser.add_argument("--xroar", type=Path,
                        default=ROOT / "docs/reference/xroar/src/xroar")
    parser.add_argument("--output", type=Path,
                        default=ROOT / "build/rsch004-6309")
    parser.add_argument("--rows", type=int, nargs="+", default=[1, 2, 4, 8, 16])
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--skip-candidate", action="store_true")
    args = parser.parse_args()
    if any(rows <= 0 or rows > 16 for rows in args.rows):
        raise SystemExit("rows must be between 1 and 16")
    if args.repeats < 2:
        raise SystemExit("repeats must be at least 2")

    base = load_base()
    all_runs = []
    for rows in args.rows:
        baseline_rom, baseline_map = assemble(
            base, args.lwasm, args.output, "baseline", "6809", rows, False)
        baseline_6309_rom, _ = assemble(
            base, args.lwasm, args.output, "baseline", "6309", rows, False)
        candidate_rom, candidate_map = assemble(
            base, args.lwasm, args.output, "candidate", "6309", rows, True)
        baseline_bytes = baseline_rom.read_bytes()
        candidate_bytes = candidate_rom.read_bytes()
        row_runs = []
        for _ in range(args.repeats):
            run = {}
            for name, rom, map_path, cpu, candidate in (
                ("baseline", baseline_rom, baseline_map, "6809", False),
                ("candidate", candidate_rom, candidate_map, "6309", True),
            ):
                if name == "candidate" and args.skip_candidate:
                    run[name] = {"status": "skipped", "reason": "explicit QA baseline-only run"}
                    continue
                try:
                    run[name] = run_case(base, args.xroar, rom, map_path, cpu,
                                         rows, name, args.timeout)
                except Exception as exc:
                    run[name] = {"status": "invalid", "error": str(exc)}
            row_runs.append(run)

        def valid_samples(name: str, case: str) -> list[dict]:
            return [run[name]["cases"][case] for run in row_runs
                    if "cases" in run[name]]

        all_runs.append({
            "rows": rows,
            "baseline_6809_vs_6309_byte_identical":
                baseline_bytes == baseline_6309_rom.read_bytes(),
            "runs": row_runs,
            "timing": {
                name: {
                    case: timing_summary(valid_samples(name, case))
                    if valid_samples(name, case) else {"status": "invalid"}
                    for case, _, _ in CASE_LABELS
                }
                for name in ("baseline", "candidate")
            },
        })

    evidence = {
        "schema": "ladybug-rsch004-6309-hotpath-v1",
        "source": str(SOURCE),
        "source_sha256": digest(SOURCE.read_bytes()),
        "xroar": str(args.xroar),
        "xroar_sha256": digest(args.xroar.read_bytes()),
        "timing_contract": {
            "boundaries": "single start/end execution markers per named case",
            "event_ticks": "XRoar event-tick delta",
            "cpu_cycles": "XRoar reported CPU-cycle delta",
            "validity": "repeat samples identical or within 1% relative spread",
            "live_identity": "C000 prefix and benchmark window before breakpoint timing, then self-authored R4HT marker",
        },
        "static_model": {
            "tfm": {"portable_byte_transfers_per_row": 8, "candidate_tfm_ops_per_row": 1},
            "ldq_stq": {"portable_byte_transfers_per_row": 8, "candidate_q_ops_per_row": 2},
            "oim": {"portable_memory_rmw_ops": OIM_COUNT,
                    "candidate_oim_ops": OIM_COUNT},
            "stride_bytes": 152,
        },
        "runs": all_runs,
        "row_scaling": {},
        "recommendations": {
            "tfm": "candidate for a separate production design only if frame-worklist translation remains favorable",
            "ldq_stq": "candidate for a separate production design after alignment and register-clobber review",
            "oim": "candidate only for nibble-compatible merges; retain merge_sprite_byte for mixed transparency",
        },
    }
    output = args.output / "rsch004-6309-hotpath.json"
    args.output.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="ascii")
    if any(not run["baseline_6809_vs_6309_byte_identical"] for run in all_runs):
        raise SystemExit(f"baseline/candidate ROM identity failure: {output}")
    if any("cases" not in item["baseline"] or
           ("cases" not in item["candidate"] and not args.skip_candidate)
           for run in all_runs for item in run["runs"]):
        raise SystemExit(f"candidate or baseline timing invalid: {output}")
    if any(not item[variant]["correctness"][key]
           for run in all_runs for item in run["runs"]
           for variant in (("baseline", "candidate")
                           if not args.skip_candidate else ("baseline",))
           for key, value in item[variant]["correctness"].items()
           if isinstance(value, bool) and not value):
        raise SystemExit(f"hot-path correctness failure: {output}")
    if any(not summary["repeatability_pass"]
           for run in all_runs
           for variant in (("baseline", "candidate")
                           if not args.skip_candidate else ("baseline",))
           for summary in run["timing"][variant].values()
           if "repeatability_pass" in summary and
           not summary["repeatability_pass"]):
        raise SystemExit(f"timing repeatability failure: {output}")
    for variant in ("baseline", "candidate"):
        try:
            evidence["row_scaling"][variant] = row_scaling_summary(all_runs, variant)
        except RuntimeError as exc:
            raise SystemExit(f"LDQ/STQ scaling failure: {exc}; {output}") from exc
    baseline_medians = evidence["row_scaling"]["baseline"]["median_cpu_cycles"]
    candidate_medians = evidence["row_scaling"]["candidate"]["median_cpu_cycles"]
    if any(candidate >= baseline
           for baseline, candidate in zip(baseline_medians, candidate_medians)):
        raise SystemExit(
            f"LDQ/STQ candidate is not below baseline: "
            f"baseline={baseline_medians} candidate={candidate_medians}; {output}"
        )
    output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="ascii")
    print(f"RSCH-004 hot-path benchmark passed: {output}")


if __name__ == "__main__":
    main()
