#!/usr/bin/env python3
"""Isolate the RSCH-004 XRoar LDQ/STQ timing outlier."""

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
SOURCE = ROOT / "src/bench/6309_ldq_stq_timing.s"
HOTPATH_SOURCE = ROOT / "src/bench/6309_hotpath_benchmark.s"
BASE_RUNNER = ROOT / "scripts/benchmark_6309.py"
HOTPATH_RUNNER = ROOT / "scripts/benchmark_6309_hotpaths.py"
DEFAULT_XROAR = ROOT / "docs/reference/xroar/src/xroar"
HD6309_SOURCE = ROOT / "docs/reference/xroar/src/mc6809/hd6309.c"
MONITOR_SOURCE = ROOT / "docs/reference/xroar/src/monitor.c"
SIGNATURE = b"R5QT"
RESULT_BASE = 0x0200
RESULT_CASE = RESULT_BASE + 4
Q_SRC = 0x2000
Q_DST = 0x3000
Q_GUARD = 0x3A00
Q_VALUE = bytes.fromhex("12345678")
Q_UNTOUCHED = bytes.fromhex("cccccccc")

CASES = (
    {
        "name": "boundary",
        "define": "BENCH_BOUNDARY=1",
        "isa": "6309",
        "cpu": "6309",
        "case_marker": 0,
        "instruction_count": 1,
        "expected_destination": Q_UNTOUCHED,
    },
    {
        "name": "ldq_only",
        "define": "BENCH_LDQ=1",
        "isa": "6309",
        "cpu": "6309",
        "case_marker": 1,
        "instruction_count": 1,
        "expected_destination": Q_UNTOUCHED,
    },
    {
        "name": "stq_only",
        "define": "BENCH_STQ=1",
        "isa": "6309",
        "cpu": "6309",
        "case_marker": 2,
        "instruction_count": 1,
        "expected_destination": Q_VALUE,
    },
    {
        "name": "ldq_stq_pair",
        "define": "BENCH_PAIR=1",
        "isa": "6309",
        "cpu": "6309",
        "case_marker": 3,
        "instruction_count": 2,
        "expected_destination": Q_VALUE,
    },
    {
        "name": "byte_equivalent_6309",
        "define": "BENCH_BYTE=1",
        "isa": "6309",
        "cpu": "6309",
        "case_marker": 4,
        "instruction_count": 8,
        "expected_destination": Q_VALUE,
    },
    {
        "name": "byte_equivalent_6809",
        "define": "BENCH_BYTE=1",
        "isa": "6809",
        "cpu": "6809",
        "case_marker": 4,
        "instruction_count": 8,
        "expected_destination": Q_VALUE,
    },
)


def load_base():
    spec = importlib.util.spec_from_file_location("rsch005_benchmark_base", BASE_RUNNER)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load shared benchmark monitor helpers")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def assemble(lwasm: str, directory: Path, case: dict) -> tuple[Path, Path]:
    name = case["name"]
    rom = directory / f"{name}.rom"
    listing = directory / f"{name}.lst"
    map_path = directory / f"{name}.map"
    command = [
        lwasm,
        "-3" if case["isa"] == "6309" else "-9",
        "--format=raw",
        f"--output={rom}",
        f"--list={listing}",
        "--symbols",
        f"--map={map_path}",
        "-D",
        case["define"],
        str(SOURCE),
    ]
    completed = subprocess.run(command, capture_output=True, text=True)
    output = (completed.stdout + completed.stderr).strip()
    if completed.returncode:
        raise RuntimeError(f"assembly failed for {name}: {output}")
    raw = rom.read_bytes()
    if len(raw) > 0x4000:
        raise RuntimeError(f"{name}: ROM exceeds 16 KiB")
    rom.write_bytes(raw + b"\xff" * (0x4000 - len(raw)))
    return rom, map_path


def run_once(base, xroar: Path, rom: Path, map_path: Path,
             case: dict, timeout: float) -> dict:
    syms = base.symbols(map_path)
    required = ("benchmark_start", "case_start", "case_end", "benchmark_done")
    missing = [name for name in required if name not in syms]
    if missing:
        raise RuntimeError(f"{case['name']}: missing symbols {missing}")
    if syms["case_start"] != syms["benchmark_start"]:
        raise RuntimeError(f"{case['name']}: start labels diverge")
    if syms["case_end"] != syms["benchmark_done"]:
        raise RuntimeError(f"{case['name']}: end labels diverge")

    monitor = base.load_monitor()
    process, client = base.launch(monitor, xroar, rom, case["cpu"])
    phase = "authored/staged/live identity"
    try:
        image = rom.read_bytes()
        start = syms["case_start"]
        end = syms["case_end"]
        authored_window = image[start - 0xC000:end - 0xC000]
        if not authored_window:
            raise RuntimeError(f"{case['name']}: empty measured window")
        live_prefix = base.read_bytes(client, 0xC000, 32)
        live_window = base.read_bytes(client, start, len(authored_window))
        if live_prefix != image[:32] or live_window != authored_window:
            raise RuntimeError(
                f"{case['name']}: live identity mismatch "
                f"prefix={live_prefix.hex()} window={live_window.hex()}"
            )

        phase = "start marker"
        start_id = base.set_breakpoint(client, start)
        start_hit = base.run_to_breakpoint(client, timeout)
        if (start_hit.get("pc") != start or
                start_hit.get("bp_id") != start_id or
                start_hit.get("reason") != "breakpoint"):
            raise RuntimeError(f"{case['name']}: invalid start halt {start_hit}")
        signature = base.read_bytes(client, RESULT_BASE, len(SIGNATURE))
        case_marker = base.read_bytes(client, RESULT_CASE, 1)[0]
        if signature != SIGNATURE or case_marker != case["case_marker"]:
            raise RuntimeError(
                f"{case['name']}: marker mismatch "
                f"signature={signature.hex()} case={case_marker}"
            )
        start_timing = base.read_timing(client)
        base.clear_breakpoint(client, start_id)

        phase = "end marker"
        end_id = base.set_breakpoint(client, end)
        end_hit = base.run_to_breakpoint(client, timeout)
        if (end_hit.get("pc") != end or
                end_hit.get("bp_id") != end_id or
                end_hit.get("reason") != "breakpoint"):
            raise RuntimeError(f"{case['name']}: invalid end halt {end_hit}")
        end_timing = base.read_timing(client)
        registers = client.call("read_registers", timeout=1.0)
        source = base.read_bytes(client, Q_SRC, 4)
        destination = base.read_bytes(client, Q_DST, 4)
        guard = base.read_bytes(client, Q_GUARD, 1)
        base.clear_breakpoint(client, end_id)

        cpu_cycles = end_timing["cpu_cycles"] - start_timing["cpu_cycles"]
        event_ticks = end_timing["event_ticks"] - start_timing["event_ticks"]
        checks = {
            "source_preserved": source == Q_VALUE,
            "destination": destination == case["expected_destination"],
            "guard": guard == b"\x5a",
            "live_window": live_window == authored_window,
            "start_halt_reason": start_hit.get("reason") == "breakpoint",
            "end_halt_reason": end_hit.get("reason") == "breakpoint",
            "event_tick_ratio": event_ticks == cpu_cycles * 16,
        }
        if case["name"] == "ldq_only":
            checks["ldq_d_register"] = registers.get("d") == 0x1234
            checks["ldq_b_register"] = registers.get("b") == 0x34
        if not all(checks.values()):
            raise RuntimeError(f"{case['name']}: correctness failure {checks}")
        return {
            "cpu_cycles": cpu_cycles,
            "event_ticks": event_ticks,
            "start_timing": start_timing,
            "end_timing": end_timing,
            "start_halt": start_hit,
            "end_halt": end_hit,
            "registers": registers,
            "source": source.hex(),
            "destination": destination.hex(),
            "guard": guard.hex(),
            "instruction_bytes": authored_window.hex(),
            "instruction_count": case["instruction_count"],
            "live_prefix": live_prefix.hex(),
            "live_window": live_window.hex(),
            "live_window_matches": live_window == authored_window,
            "rom_sha256": digest(image),
            "checks": checks,
        }
    except Exception as exc:
        raise RuntimeError(f"{case['name']} failed in {phase}: {exc}") from exc
    finally:
        try:
            client.close()
        finally:
            base.stop(process)


def summarize(samples: list[dict]) -> dict:
    cycles = [sample["cpu_cycles"] for sample in samples]
    ticks = [sample["event_ticks"] for sample in samples]
    median = statistics.median(cycles)
    spread = (max(cycles) - min(cycles)) / median if median else 0.0
    return {
        "cpu_cycle_samples": cycles,
        "event_tick_samples": ticks,
        "median_cpu_cycles": median,
        "minimum_cpu_cycles": min(cycles),
        "maximum_cpu_cycles": max(cycles),
        "relative_spread": spread,
        "repeatability_pass": len(set(cycles)) == 1 or spread <= 0.01,
    }


def original_loop_evidence() -> dict:
    source = HOTPATH_SOURCE.read_text(encoding="ascii")
    match = re.search(
        r"case_q_hot_start(?P<body>.*?)case_q_hot_end", source, re.DOTALL
    )
    if match is None:
        raise RuntimeError("cannot locate RSCH-004 LDQ/STQ hot-path window")
    body = match.group("body")
    uses_direct_memory_counter = (
        "lda     #Q_ROWS" in body and
        "sta     RESULT_Q_STATUS" in body
    )
    decrements_direct_memory = "dec     RESULT_Q_STATUS" in body
    branches_on_direct_memory = (
        "dec     RESULT_Q_STATUS" in body and
        "bne     q_hot_row" in body
    )
    no_decb_in_hot_window = "decb" not in body
    return {
        "uses_b_as_row_counter": "ldb     #Q_ROWS" in body,
        "loads_q_before_decb": body.find("ldq     ,x") < body.find("decb"),
        "second_ldq_before_decb": body.find("ldq     4,x") < body.find("decb"),
        "decrements_b": "decb" in body,
        "uses_direct_memory_counter": uses_direct_memory_counter,
        "decrements_direct_memory": decrements_direct_memory,
        "branches_on_direct_memory": branches_on_direct_memory,
        "no_decb_in_hot_window": no_decb_in_hot_window,
        "first_row_source_bytes": "31425364758697a8",
        "b_after_second_ldq": "86",
        "b_after_decb": "85",
        "explanation": (
            "Q contains D:W, and D contains A:B. The second LDQ loads B from "
            "source byte 5, so DECB decrements copied data instead of Q_ROWS."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lwasm", default="lwasm")
    parser.add_argument("--xroar", type=Path, default=DEFAULT_XROAR)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "build/rsch005-6309")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args()
    if args.repeats < 3:
        raise SystemExit("repeats must be at least 3")
    if args.timeout <= 0 or args.timeout > 5:
        raise SystemExit("timeout must be greater than zero and at most 5 seconds")
    for dependency in (
        SOURCE, HOTPATH_SOURCE, BASE_RUNNER, HOTPATH_RUNNER,
        args.xroar, HD6309_SOURCE, MONITOR_SOURCE,
    ):
        if not dependency.is_file():
            raise SystemExit(f"required dependency missing: {dependency}")

    base = load_base()
    case_results = {}
    with tempfile.TemporaryDirectory(prefix="rsch005-") as temporary:
        directory = Path(temporary)
        for case in CASES:
            rom, map_path = assemble(args.lwasm, directory, case)
            samples = [
                run_once(base, args.xroar, rom, map_path, case, args.timeout)
                for _ in range(args.repeats)
            ]
            case_results[case["name"]] = {
                "isa": case["isa"],
                "cpu": case["cpu"],
                "instruction_count": case["instruction_count"],
                "samples": samples,
                "timing": summarize(samples),
            }

    source_evidence = original_loop_evidence()
    primary = {
        name: case_results[name]["timing"]["median_cpu_cycles"]
        for name in (
            "boundary", "ldq_only", "stq_only", "ldq_stq_pair",
            "byte_equivalent_6309",
        )
    }
    aligned_controls_pass = all(
        result["timing"]["repeatability_pass"] and
        all(all(sample["checks"].values()) for sample in result["samples"])
        for result in case_results.values()
    )
    historical_loop_source_proof = all(
        source_evidence[key]
        for key in (
            "uses_b_as_row_counter", "loads_q_before_decb",
            "second_ldq_before_decb", "decrements_b",
        )
    )
    repaired_loop_source_proof = all(
        source_evidence[key]
        for key in (
            "uses_direct_memory_counter", "decrements_direct_memory",
            "branches_on_direct_memory", "no_decb_in_hot_window",
        )
    )
    loop_source_proof = historical_loop_source_proof or repaired_loop_source_proof
    ldq_b_proof = all(
        sample["registers"].get("b") == 0x34
        for sample in case_results["ldq_only"]["samples"]
    )
    pair_not_outlier = primary["ldq_stq_pair"] < 100
    cause_confirmed = (
        aligned_controls_pass and loop_source_proof and ldq_b_proof and
        pair_not_outlier
    )
    evidence = {
        "schema": "ladybug-rsch005-ldq-stq-timing-v1",
        "probe_count": 1,
        "observation_tool_timeouts": 0,
        "source": str(SOURCE.relative_to(ROOT)),
        "source_sha256": digest(SOURCE.read_bytes()),
        "hotpath_source": str(HOTPATH_SOURCE.relative_to(ROOT)),
        "hotpath_source_sha256": digest(HOTPATH_SOURCE.read_bytes()),
        "base_runner_sha256": digest(BASE_RUNNER.read_bytes()),
        "hotpath_runner_sha256": digest(HOTPATH_RUNNER.read_bytes()),
        "xroar": str(args.xroar),
        "xroar_sha256": digest(args.xroar.read_bytes()),
        "hd6309_source_sha256": digest(HD6309_SOURCE.read_bytes()),
        "monitor_source_sha256": digest(MONITOR_SOURCE.read_bytes()),
        "deadline_seconds_per_marker": args.timeout,
        "repeats": args.repeats,
        "fixture": {
            "cpu_mode": "6309 emulation mode",
            "source": "2000",
            "destination": "3000",
            "guard": "3A00",
            "source_value": Q_VALUE.hex(),
        },
        "cases": case_results,
        "diagnosis": {
            "rsch004_observation": {
                "one_row_cpu_cycles": 11119,
                "sixteen_row_cpu_cycles": 11119,
                "status": "invalidated as instruction-cost evidence",
            },
            "median_cpu_cycles": primary,
            "original_loop": source_evidence,
            "source_proof": {
                "historical_pre_repair": historical_loop_source_proof,
                "current_repaired_loop": repaired_loop_source_proof,
            },
            "aligned_controls_pass": aligned_controls_pass,
            "ldq_b_register_proof": ldq_b_proof,
            "single_pair_below_100_cycles": pair_not_outlier,
            "cause_confirmed": cause_confirmed,
            "cause": (
                "RSCH-004 stored Q_ROWS in B, then LDQ overwrote D/B before "
                "DECB; the loop decremented copied source data instead of the "
                "row counter. The 11,119-cycle value measured unintended extra "
                "iterations, not one or two LDQ/STQ pairs."
                if cause_confirmed else
                "aligned controls did not fully discriminate the cause"
            ),
            "source_proof_revision": (
                "current BUG-024 direct-memory counter"
                if repaired_loop_source_proof else "historical B/DECB loop"
            ),
            "slope_probe_required": not cause_confirmed,
        },
        "scope": {
            "production_changed": False,
            "xroar_changed": False,
            "native_mode_tested": False,
            "odd_address_tested": False,
        },
    }
    args.output.mkdir(parents=True, exist_ok=True)
    output = args.output / "rsch005-ldq-stq-timing.json"
    output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="ascii")
    if not aligned_controls_pass:
        raise SystemExit(f"RSCH-005 aligned control failure: {output}")
    if not cause_confirmed:
        raise SystemExit(f"RSCH-005 cause unresolved; slope probe required: {output}")
    print("RSCH-005 aligned controls passed; slope probe not required")
    print(f"cause={evidence['diagnosis']['cause']}")
    print(f"evidence={output}")


if __name__ == "__main__":
    main()
