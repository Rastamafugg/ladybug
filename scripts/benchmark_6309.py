#!/usr/bin/env python3
"""Run isolated 6809/6309 correctness and cycle benchmarks through XRoar."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import signal
import socket
import subprocess
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/bench/6309_benchmark.s"
DEFAULT_XROAR = ROOT / "docs/reference/xroar/src/xroar"
RESULT_BASE = 0x0200
RESULT_VARIANT = RESULT_BASE + 4
COPY_SRC = 0x0400
COPY_DST = 0x0500
COPY_LEN = 64
Q_SRC = 0x0600
Q_DST = 0x0610
MASK_BYTE = 0x0620
MASK_GUARD = 0x0621
W_SRC = 0x0630
W_DST = 0x0633
W_GUARD = 0x0635
CASE_LABELS = (
    ("tfm_copy", "case_copy_start", "case_copy_timed_end"),
    ("ldq_stq", "case_q_start", "case_q_timed_end"),
    ("oim_mask", "case_mask_start", "case_mask_timed_end"),
    ("ldw_stw", "case_w_start", "case_w_timed_end"),
)


def load_monitor():
    path = ROOT / "scripts/verify_bug009_monitor_input.py"
    spec = importlib.util.spec_from_file_location("benchmark_monitor", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load monitor client")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def symbols(path: Path) -> dict[str, int]:
    return {
        name: int(value, 16)
        for name, value in re.findall(
            r"^Symbol: (\w+) .* = ([0-9A-Fa-f]+)$",
            path.read_text(encoding="ascii"), re.MULTILINE,
        )
    }


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def stop(process: subprocess.Popen[object]) -> None:
    if process.poll() is not None:
        return
    if os.name != "nt":
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if process.poll() is None:
        process.kill()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass


def launch(monitor, binary: Path, rom: Path, cpu: str):
    port = monitor.free_port()
    machine = "coco3h" if cpu == "6309" else "coco3"
    process = subprocess.Popen(
        [
            str(binary), "-ui", "null", "-ao", "null", "-machine", machine,
            "-machine-cpu", cpu, "-ram", "512", "-run", str(rom),
            "-machine-cart", "romcart",
            "-no-ratelimit", "-monitor", f"127.0.0.1:{port}",
            "-monitor-halt-on-start",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=(os.name != "nt"),
    )
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            sock = socket.create_connection(("127.0.0.1", port), timeout=0.5)
            client = monitor.MonitorClient(sock)
            hello = json.loads(client.file.readline())
            if hello.get("method") != "hello":
                raise monitor.MonitorError(f"unexpected hello: {hello}")
            client.call("events.subscribe", {"kinds": ["bp"]})
            return process, client
        except (OSError, monitor.MonitorError):
            time.sleep(0.05)
    stop(process)
    raise monitor.MonitorError("monitor listener did not accept a client")


def run_to_breakpoint(client, timeout: float) -> dict:
    """Run and poll the monitor's authoritative halted state."""
    client.call("run", timeout=timeout)
    deadline = time.monotonic() + timeout
    while True:
        state = client.call("get_run_state", timeout=min(1.0, timeout))
        if state.get("state") == "halted":
            return {
                "pc": state.get("last_stop_pc"),
                "bp_id": state.get("last_stop_bp_id"),
                "reason": state.get("last_stop_reason"),
            }
        if time.monotonic() >= deadline:
            raise TimeoutError("monitor did not halt before the benchmark deadline")
        time.sleep(0.01)


def read_bytes(client, address: int, length: int) -> bytes:
    return bytes.fromhex(client.call("read_memory", {
        "addr": address, "length": length,
    })["data"])


def set_breakpoint(client, address: int) -> int:
    return int(client.call("set_breakpoint", {
        "addr": address, "kind": "exec",
    })["id"])


def clear_breakpoint(client, ident: int) -> None:
    client.call("clear_breakpoint", {"id": ident})


def read_timing(client) -> dict[str, int]:
    """Read the external timing contract and reject partial responses."""
    timing = client.call("read_cycles")
    try:
        event_ticks = int(timing["event_ticks"])
        cpu_cycles = int(timing["cpu_cycles"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError(
            "XRoar read_cycles must return integer event_ticks and cpu_cycles"
        ) from exc
    if event_ticks < 0 or cpu_cycles < 0:
        raise RuntimeError(f"XRoar returned negative timing: {timing}")
    return {"event_ticks": event_ticks, "cpu_cycles": cpu_cycles}


def wait_for_live_identity(client, rom: Path, window_address: int,
                           window_length: int, timeout: float) -> dict:
    """Wait for the cart image to become observable before timing it."""
    image = rom.read_bytes()
    expected_prefix = image[:32]
    window_offset = window_address - 0xC000
    if window_offset < 0 or window_offset + window_length > len(image):
        raise RuntimeError(
            f"identity window outside ROM: address={window_address:04x} "
            f"length={window_length} image={len(image)}"
        )
    expected_window = image[window_offset:window_offset + window_length]
    deadline = time.monotonic() + timeout
    attempts = 0
    live_prefix = b""
    live_window = b""
    while True:
        attempts += 1
        live_prefix = read_bytes(client, 0xC000, len(expected_prefix))
        live_window = read_bytes(client, window_address, window_length)
        if live_prefix == expected_prefix and live_window == expected_window:
            return {
                "attempts": attempts,
                "deadline_seconds": timeout,
                "live_prefix": live_prefix.hex(),
                "live_window": live_window.hex(),
                "expected_prefix": expected_prefix.hex(),
                "expected_window": expected_window.hex(),
                "matches": True,
            }
        if time.monotonic() >= deadline:
            raise RuntimeError(
                f"live ROM identity mismatch after {attempts} attempts "
                f"prefix={live_prefix.hex()} window={live_window.hex()}"
            )
        time.sleep(0.05)


def execute_variant(monitor, xroar: Path, rom: Path, map_path: Path,
                    variant: str, cpu: str, timeout: float) -> dict:
    syms = symbols(map_path)
    required = ["benchmark_start", "benchmark_done"]
    required.extend(label for _, start, end in CASE_LABELS for label in (start, end))
    missing = [label for label in required if label not in syms]
    if missing:
        raise RuntimeError(f"{variant}/{cpu}: missing symbols {missing}")
    process, client = launch(monitor, xroar, rom, cpu)
    phase = "benchmark_start"
    try:
        start_id = set_breakpoint(client, syms["benchmark_start"])
        hit = run_to_breakpoint(client, timeout)
        if hit.get("pc") != syms["benchmark_start"]:
            raise RuntimeError(f"{variant}/{cpu}: benchmark start PC {hit}")
        identity = wait_for_live_identity(
            client, rom, syms["benchmark_start"], 64, timeout
        )
        live_rom = read_bytes(client, 0xC000, rom.stat().st_size)
        live_rom_sha256 = digest(live_rom)
        expected_rom_sha256 = digest(rom.read_bytes())
        if live_rom_sha256 != expected_rom_sha256:
            raise RuntimeError(
                f"{variant}/{cpu}: live ROM identity mismatch "
                f"{live_rom_sha256} != {expected_rom_sha256}; "
                f"live_prefix={live_rom[:32].hex()} expected_prefix={rom.read_bytes()[:32].hex()}"
            )
        start_timing = read_timing(client)
        clear_breakpoint(client, start_id)

        cases: dict[str, dict[str, object]] = {}
        for name, start_label, end_label in CASE_LABELS:
            phase = f"{name}/start"
            if start_label == "case_copy_start":
                begin_timing = start_timing
            else:
                begin_id = set_breakpoint(client, syms[start_label])
                hit = run_to_breakpoint(client, timeout)
                if hit.get("pc") != syms[start_label]:
                    raise RuntimeError(f"{variant}/{cpu}/{name}: start PC {hit}")
                begin_timing = read_timing(client)
                clear_breakpoint(client, begin_id)
            phase = f"{name}/end"
            end_id = set_breakpoint(client, syms[end_label])
            hit = run_to_breakpoint(client, timeout)
            if hit.get("pc") != syms[end_label]:
                raise RuntimeError(f"{variant}/{cpu}/{name}: end PC {hit}")
            end_timing = read_timing(client)
            clear_breakpoint(client, end_id)
            cases[name] = {
                "cycles": end_timing["cpu_cycles"] - begin_timing["cpu_cycles"],
                "event_ticks": end_timing["event_ticks"] - begin_timing["event_ticks"],
                "start_timing": begin_timing,
                "end_timing": end_timing,
            }

        phase = "benchmark_done"
        done_id = set_breakpoint(client, syms["benchmark_done"])
        hit = run_to_breakpoint(client, timeout)
        if hit.get("pc") != syms["benchmark_done"]:
            raise RuntimeError(f"{variant}/{cpu}: benchmark done PC {hit}")
        done_timing = read_timing(client)
        copy_source = read_bytes(client, COPY_SRC, COPY_LEN)
        copy_destination = read_bytes(client, COPY_DST, COPY_LEN)
        copy_guards = bytes((read_bytes(client, COPY_DST - 1, 1)[0],
                             read_bytes(client, COPY_DST + COPY_LEN, 1)[0]))
        q_source = read_bytes(client, Q_SRC, 4)
        q_destination = read_bytes(client, Q_DST, 4)
        q_guards = bytes((read_bytes(client, Q_DST - 1, 1)[0],
                          read_bytes(client, Q_DST + 4, 1)[0]))
        mask = read_bytes(client, MASK_BYTE, 2)
        w_source = read_bytes(client, W_SRC, 2)
        w_destination = read_bytes(client, W_DST, 2)
        w_guards = bytes((read_bytes(client, W_DST - 1, 1)[0],
                          read_bytes(client, W_GUARD, 1)[0]))
        result = {
            "variant": variant,
            "cpu": cpu,
            "rom_sha256": digest(rom.read_bytes()),
            "variant_marker": f"{read_bytes(client, RESULT_VARIANT, 1)[0]:02x}",
            "start_timing": start_timing,
            "done_timing": done_timing,
            "total_cycles": done_timing["cpu_cycles"] - start_timing["cpu_cycles"],
            "total_event_ticks": done_timing["event_ticks"] - start_timing["event_ticks"],
            "live_rom_sha256": live_rom_sha256,
            "live_rom_matches": live_rom_sha256 == expected_rom_sha256,
            "startup_identity": identity,
            "cases": cases,
            "fixtures": {
                "copy_source_sha256": digest(copy_source),
                "copy_destination_sha256": digest(copy_destination),
                "copy_expected_sha256": digest(bytes(
                    (0x11 + 0x07 * index) & 0xFF for index in range(COPY_LEN)
                )),
                "copy_guards": copy_guards.hex(),
                "q_source": q_source.hex(),
                "q_destination": q_destination.hex(),
                "q_guards": q_guards.hex(),
                "mask_and_guard": mask.hex(),
                "w_source": w_source.hex(),
                "w_destination": w_destination.hex(),
                "w_guards": w_guards.hex(),
            },
        }
        result["correctness"] = correctness(result)
        clear_breakpoint(client, done_id)
        return result
    except Exception as exc:
        raise RuntimeError(f"{variant}/{cpu} failed in {phase}: {exc}") from exc
    finally:
        try:
            client.close()
        finally:
            stop(process)


def correctness(result: dict) -> dict[str, bool]:
    expected_copy = bytes((0x11 + 0x07 * index) & 0xFF for index in range(COPY_LEN))
    fixtures = result["fixtures"]
    assert isinstance(fixtures, dict)
    return {
        "tfm_copy": fixtures["copy_source_sha256"] == digest(expected_copy) and
        fixtures["copy_destination_sha256"] == digest(expected_copy) and
        fixtures["copy_guards"] == "a55a",
        "ldq_stq": fixtures["q_source"] == fixtures["q_destination"] == "12345678" and
        fixtures["q_guards"] == "cccc",
        "oim_mask": fixtures["mask_and_guard"] == "af5a",
        "ldw_stw": fixtures["w_source"] == fixtures["w_destination"] == "1234" and
        fixtures["w_guards"] == "cccc",
    }


def assemble(lwasm: str, output_dir: Path, variant: str, isa: str,
             candidate_define: bool) -> tuple[Path, Path, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rom = output_dir / f"{variant}-{isa}.rom"
    listing = output_dir / f"{variant}-{isa}.lst"
    map_path = output_dir / f"{variant}-{isa}.map"
    command = [
        lwasm, "-3" if isa == "6309" else "-9", "--format=raw",
        f"--output={rom}", f"--list={listing}", "--symbols",
        f"--map={map_path}",
    ]
    if candidate_define:
        command.append("-D")
        command.append("BENCH_CANDIDATE=1")
    command.append(str(SOURCE))
    completed = subprocess.run(command, capture_output=True, text=True)
    output = (completed.stdout + completed.stderr).strip()
    if completed.returncode:
        raise RuntimeError(
            f"assembly failed for {variant}/{isa} ({completed.returncode}): {output}"
        )
    data = rom.read_bytes()
    if len(data) > 0x4000:
        raise RuntimeError(f"{variant}/{isa}: ROM is {len(data)} bytes, exceeds 16 KiB cart")
    rom.write_bytes(data + b"\xff" * (0x4000 - len(data)))
    return rom, map_path, output


def rejected_candidate_6809(lwasm: str, output_dir: Path) -> dict:
    rom = output_dir / "candidate-6809-rejection.rom"
    listing = output_dir / "candidate-6809-rejection.lst"
    map_path = output_dir / "candidate-6809-rejection.map"
    command = [
        lwasm, "-9", "--format=raw", f"--output={rom}",
        f"--list={listing}", "--symbols", f"--map={map_path}",
        "-D", "BENCH_CANDIDATE=1", str(SOURCE),
    ]
    completed = subprocess.run(command, capture_output=True, text=True)
    output = (completed.stdout + completed.stderr).strip()
    return {
        "name": "candidate-6309-under-6809-assembler",
        "assembled": completed.returncode == 0,
        "reason": "expected assembler rejection for 6309-only opcodes",
        "diagnostic": output[-1000:],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xroar", type=Path, default=DEFAULT_XROAR)
    parser.add_argument("--lwasm", default="lwasm")
    parser.add_argument("--output", type=Path,
                        default=ROOT / "build/rsch003-6309")
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args()
    if not SOURCE.is_file():
        raise SystemExit(f"benchmark source missing: {SOURCE}")
    args.output.mkdir(parents=True, exist_ok=True)
    baseline_6809, baseline_6809_map, _ = assemble(
        args.lwasm, args.output, "baseline", "6809", False
    )
    baseline_6309, baseline_6309_map, _ = assemble(
        args.lwasm, args.output, "baseline", "6309", False
    )
    candidate_6309, candidate_6309_map, _ = assemble(
        args.lwasm, args.output, "candidate", "6309", True
    )
    monitor = load_monitor()
    runs = [
        execute_variant(monitor, args.xroar, baseline_6809, baseline_6809_map,
                        "baseline", "6809", args.timeout),
        execute_variant(monitor, args.xroar, baseline_6309, baseline_6309_map,
                        "baseline", "6309", args.timeout),
        execute_variant(monitor, args.xroar, candidate_6309, candidate_6309_map,
                        "candidate", "6309", args.timeout),
    ]
    baseline_6809_bytes = baseline_6809.read_bytes()
    baseline_6309_bytes = baseline_6309.read_bytes()
    candidate_run = next(item for item in runs if item["variant"] == "candidate")
    baseline_6309_run = next(
        item for item in runs
        if item["variant"] == "baseline" and item["cpu"] == "6309"
    )
    comparisons = {}
    for name, _, _ in CASE_LABELS:
        baseline_cycles = baseline_6309_run["cases"][name]["cycles"]
        candidate_cycles = candidate_run["cases"][name]["cycles"]
        comparisons[name] = {
            "baseline_6309_cycles": baseline_cycles,
            "candidate_6309_cycles": candidate_cycles,
            "delta_cycles": candidate_cycles - baseline_cycles,
            "percent_delta": round(
                (candidate_cycles - baseline_cycles) * 100 / baseline_cycles, 2
            ),
            "correctness": candidate_run["correctness"][name],
        }
    evidence = {
        "schema": "ladybug-rsch003-6309-benchmark-v2",
        "source": str(SOURCE.relative_to(ROOT)),
        "source_sha256": digest(SOURCE.read_bytes()),
        "xroar": str(args.xroar),
        "lwasm": args.lwasm,
        "deadline_seconds_per_marker": args.timeout,
        "runs": runs,
        "comparisons": comparisons,
        "compatibility": {
            "baseline_6809_vs_baseline_6309_byte_identical":
                baseline_6809_bytes == baseline_6309_bytes,
            "candidate_6809_rejection": rejected_candidate_6809(
                args.lwasm, args.output
            ),
        },
        "rejected": [
            {
                "name": "tfm_strided_framebuffer_rows",
                "reason": "TFM cannot express the 156-byte row stride without copying intervening bytes; use a row loop or a separate representation benchmark.",
            },
            {
                "name": "tfm_par5_remap_boundary",
                "reason": "A single TFM cannot preserve Ladybug's PAR5 mapping contract across an 8 KiB physical-page transition; the loader/MMU path requires explicit remap and restore measurement.",
            },
        ],
    }
    output_path = args.output / "rsch003-6309-benchmark.json"
    output_path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="ascii")
    all_correct = all(
        all(item["correctness"].values()) for item in runs
    )
    candidate_rejected = not evidence["compatibility"]["candidate_6809_rejection"]["assembled"]
    if not all_correct or not candidate_rejected:
        raise SystemExit(f"benchmark correctness/compatibility failure: {output_path}")
    print("RSCH-003 6309 benchmark: baseline 6809/6309 and candidate 6309 passed")
    print(f"evidence={output_path}")


if __name__ == "__main__":
    main()
