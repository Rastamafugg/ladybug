#!/usr/bin/env python3
"""Observe the two approved FEAT-011 E-pickup fixtures through XRoar monitor.

This is a focused observer, not a game-state setup tool. It may inject normal
keyboard input and read memory/registers, but it never writes guest memory or
registers. Source-dependent event/route/return labels are supplied from the
candidate's linker map and remain subject to source review before dispatch.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shlex
import socket
import struct
import subprocess
import sys
import threading
import time
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MONITOR_SOURCE = ROOT / "scripts/verify_bug009_monitor_input.py"

# Source-derived direct-page and published-audio fields.
PLAYER_CELL_X = 0x0009
LIVES = 0x0023
BONUS_COLOR = 0x002F
BONUS_TIMER = 0x0030
SPECIAL_BITS = 0x003C
EXTRA_BITS = 0x003D
INITIAL_ENTRY_STATE = 0x00A0
PRES_MODE = 0x00A5
EVENT_KIND = 0x00A8
AUDIO_MUSIC_PUBLISHED_BUSY = 0x02D4
FB_FRONT_ID = 0x008F
FB_COMMIT_SEQ = 0x0092

MODE_NORMAL = 0
MODE_ATTRACT = 2
MODE_INSTRUCTIONS = 3
COLOR_RED = 1
COLOR_YELLOW = 2
MAX_RESERVE_LIVES = 12
START_SCAN = 0x30  # CoCo Enter; project Start/Return input.
LEFT_SCAN = 0x2D

FRAME_BYTES = 30_720  # 320x192, 4bpp, 160 bytes per row.
FRAME_PAGE_BYTES = 0x2000
FRAME_PAGE_BASES = {0: 0x30, 1: 0x2C}
MAX_LOG_BYTES = 1_048_576
CLEANUP_RESERVE_SECONDS = 5.0
MAX_TIMEOUT_SECONDS = 60.0
MAX_FRAME_FILES = 3

EXPECTED = {
    "special-e": {
        "event_kind": 2,
        "cue": 11,
        "color": COLOR_RED,
        "special_before": 0x7B,
        "special_after_pickup": 0x7F,
        "extra_before": 0,
        "extra_after_pickup": 0,
        "life_delta": 0,
    },
    "extra-e": {
        "event_kind": 1,
        "cue": 10,
        "color": COLOR_YELLOW,
        "special_before": 0,
        "special_after_pickup": 0,
        "extra_before": 0x1E,
        "extra_after_pickup": 0x1F,
        "life_delta": 1,
    },
}


class ObserverError(RuntimeError):
    def __init__(self, category: str, phase: str, message: str):
        super().__init__(message)
        self.category = category
        self.phase = phase


class BoundedCapture:
    """Drain XRoar output continuously while retaining at most one MiB."""

    def __init__(self, stream):
        self.stream = stream
        self.data = bytearray()
        self.total_bytes = 0
        self.error: str | None = None
        self.thread = threading.Thread(target=self._drain, daemon=True)
        self.thread.start()

    def _drain(self) -> None:
        try:
            while True:
                chunk = self.stream.read(8192)
                if not chunk:
                    return
                self.total_bytes += len(chunk)
                remaining = MAX_LOG_BYTES - len(self.data)
                if remaining > 0:
                    self.data.extend(chunk[:remaining])
        except (OSError, ValueError) as exc:
            self.error = str(exc)

    def finish(self, timeout: float) -> bool:
        self.thread.join(max(0.0, timeout))
        return not self.thread.is_alive()


def load_monitor_module():
    spec = importlib.util.spec_from_file_location("feat011_bug009_monitor", MONITOR_SOURCE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load existing monitor client: {MONITOR_SOURCE}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def under(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False


def parse_symbols(path: Path) -> dict[str, list[int]]:
    found: dict[str, list[int]] = {}
    for name, value in re.findall(
        r"^Symbol: (\w+) .* = ([0-9A-Fa-f]+)$",
        path.read_text(encoding="utf-8"), re.MULTILINE,
    ):
        found.setdefault(name, []).append(int(value, 16))
    return found


def prepare_evidence_dir(args: argparse.Namespace) -> Path:
    fixture_root = (ROOT / "repro/feat011-candidate/fixtures" / args.scenario).resolve()
    evidence_dir = args.evidence_dir.resolve()
    if not under(evidence_dir, fixture_root) or evidence_dir.parent != fixture_root:
        raise ValueError("evidence directory must be directly under the named fixture root")
    if not re.fullmatch(r"attempt-[0-9]{2}", evidence_dir.name):
        raise ValueError("evidence directory name must use attempt-NN")
    evidence_dir.mkdir(parents=False, exist_ok=False)
    command = [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]]
    command_text = subprocess.list2cmdline(command) if os.name == "nt" else shlex.join(command)
    (evidence_dir / "command.txt").write_text(command_text + "\n", encoding="utf-8")
    return evidence_dir


def preflight(args: argparse.Namespace, evidence_dir: Path) -> dict[str, Any]:
    if not 0 < args.timeout <= MAX_TIMEOUT_SECONDS:
        raise ValueError(f"--timeout must be greater than 0 and no more than {MAX_TIMEOUT_SECONDS:g}s")
    if args.timeout <= CLEANUP_RESERVE_SECONDS:
        raise ValueError(f"--timeout must leave at least {CLEANUP_RESERVE_SECONDS:g}s for cleanup and evidence")

    fixture_root = (ROOT / "repro/feat011-candidate/fixtures" / args.scenario).resolve()
    expected_rom = (fixture_root / "root/build/ladybug.rom").resolve()
    rom = args.rom.resolve(strict=True)
    if rom != expected_rom:
        raise ValueError(f"ROM must be the isolated {args.scenario} fixture image: {expected_rom}")
    xroar = args.xroar.resolve(strict=True)
    symbol_map = args.symbol_map.resolve(strict=True)
    if not xroar.is_file() or not rom.is_file() or not symbol_map.is_file():
        raise ValueError("XRoar, fixture ROM, and linker map must be files")
    if symbol_map.parent != rom.parent:
        raise ValueError("linker map must be beside the fixture ROM in its isolated build root")

    required_names = {
        "frame_publish": "fbf_ready",
        "cue_enqueue": "audio_enqueue_route",
        "event_start": args.event_start_symbol,
        "route_complete": args.route_complete_symbol,
        "normal_return": args.return_symbol,
    }
    for binding, name in required_names.items():
        if not re.fullmatch(r"[A-Za-z_]\w*", name):
            raise ValueError(f"{binding} symbol is not a valid linker label: {name!r}")
    symbols = parse_symbols(symbol_map)
    missing = [
        f"{binding}={name}"
        for binding, name in required_names.items()
        if len(symbols.get(name, [])) != 1
    ]
    if missing:
        raise ValueError("linker map must contain each required source binding exactly once: " + ", ".join(missing))
    addresses = {binding: symbols[name][0] for binding, name in required_names.items()}
    if len(set(addresses.values())) != len(addresses):
        raise ValueError("required source breakpoint bindings must resolve to distinct addresses")

    return {
        "fixture_root": fixture_root,
        "rom": rom,
        "xroar": xroar,
        "symbol_map": symbol_map,
        "evidence_dir": evidence_dir,
        "symbols": addresses,
        "symbol_names": required_names,
        "expected": EXPECTED[args.scenario],
    }


def png_chunk(kind: bytes, data: bytes) -> bytes:
    payload = kind + data
    return struct.pack(">I", len(data)) + payload + struct.pack(">I", zlib.crc32(payload) & 0xFFFFFFFF)


def write_frame_png(path: Path, frame: bytes) -> str:
    # Match the project's established framebuffer-to-PNG conversion.
    sys.path.insert(0, str(ROOT / "scripts"))
    from build_screen import PALETTE, gime_rgb

    palette = [gime_rgb(value) for value in PALETTE]
    rows = bytearray()
    for y in range(192):
        rows.append(0)
        for value in frame[y * 160:(y + 1) * 160]:
            for index in (value >> 4, value & 0x0F):
                rows.extend(palette[index])
    image = (
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", struct.pack(">IIBBBBB", 320, 192, 8, 2, 0, 0, 0))
        + png_chunk(b"IDAT", zlib.compress(bytes(rows), 1))
        + png_chunk(b"IEND", b"")
    )
    path.write_bytes(image)
    return hashlib.sha256(image).hexdigest()


def remaining(deadline: float, phase: str) -> float:
    value = deadline - time.monotonic()
    if value <= 0:
        raise ObserverError("missing_coverage", phase, "whole-phase work deadline expired")
    return value


def rpc(client, method: str, params: dict[str, Any] | None, deadline: float, phase: str) -> dict[str, Any]:
    return client.call(method, params, timeout=remaining(deadline, phase))


def read_bytes(client, address: int, length: int, deadline: float, phase: str) -> bytes:
    result = rpc(client, "read_memory", {"addr": address, "length": length}, deadline, phase)
    data = bytes.fromhex(result["data"])
    if len(data) != length:
        raise ObserverError("setup_observer_failure", phase, f"short monitor read at ${address:04X}")
    return data


def read_byte(client, address: int, deadline: float, phase: str) -> int:
    return read_bytes(client, address, 1, deadline, phase)[0]


def read_word(client, address: int, deadline: float, phase: str) -> int:
    return int.from_bytes(read_bytes(client, address, 2, deadline, phase), "big")


def read_physical_bytes(client, address: int, length: int, deadline: float, phase: str) -> bytes:
    result = rpc(
        client, "read_memory",
        {"space": "physical", "addr": address, "length": length},
        deadline, phase,
    )
    data = bytes.fromhex(result["data"])
    if len(data) != length:
        raise ObserverError("setup_observer_failure", phase, f"short physical-memory read at ${address:X}")
    return data


def state_snapshot(client, deadline: float, phase: str) -> dict[str, int]:
    cell = read_bytes(client, PLAYER_CELL_X, 2, deadline, phase)
    masks = read_bytes(client, SPECIAL_BITS, 2, deadline, phase)
    timer = read_bytes(client, BONUS_TIMER, 2, deadline, phase)
    return {
        "player_cell_x": cell[0], "player_cell_y": cell[1],
        "lives": read_byte(client, LIVES, deadline, phase),
        "bonus_color": read_byte(client, BONUS_COLOR, deadline, phase),
        "bonus_timer": int.from_bytes(timer, "big"),
        "special_bits": masks[0], "extra_bits": masks[1],
        "initial_entry_state": read_byte(client, INITIAL_ENTRY_STATE, deadline, phase),
        "presentation_mode": read_byte(client, PRES_MODE, deadline, phase),
        "event_kind": read_byte(client, EVENT_KIND, deadline, phase),
    }


def read_frame(client, deadline: float, phase: str) -> tuple[bytes, int, int]:
    owner = read_byte(client, FB_FRONT_ID, deadline, phase)
    if owner not in FRAME_PAGE_BASES:
        raise ObserverError("setup_observer_failure", phase, f"invalid published framebuffer owner {owner}")
    sequence = read_word(client, FB_COMMIT_SEQ, deadline, phase)
    physical_start = FRAME_PAGE_BASES[owner] * FRAME_PAGE_BYTES
    frame = read_physical_bytes(client, physical_start, FRAME_BYTES, deadline, phase)
    if len(frame) != FRAME_BYTES:
        raise ObserverError("setup_observer_failure", phase, "framebuffer size mismatch")
    return frame, owner, sequence


def add_log(result: dict[str, Any], label: str, started: float, **fields: Any) -> None:
    events = result["events"]
    if len(events) == 4096:
        events.pop(0)
        result["discarded_event_count"] = result.get("discarded_event_count", 0) + 1
    events.append({
        "elapsed_seconds": round(time.monotonic() - started, 4),
        "event": label,
        **fields,
    })


def inject(client, key: int, action: str, deadline: float, phase: str) -> None:
    rpc(client, "inject_key", {"key": key, "action": action}, deadline, phase)


def launch(binary: Path, rom: Path, monitor):
    port = monitor.free_port()
    command = [
        str(binary), "-ui", "null", "-ao", "null", "-machine", "coco3",
        "-ram", "512", "-cart-type", "gmc", "-cart-rom", str(rom),
        "-cart-autorun", "-monitor", f"127.0.0.1:{port}", "-monitor-halt-on-start",
    ]
    process = subprocess.Popen(
        command, cwd=ROOT, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, bufsize=0,
    )
    return process, command, port


def connect_monitor(monitor, process, port: int, deadline: float):
    sock = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise ObserverError("setup_observer_failure", "monitor_connect", f"XRoar exited during monitor startup: {process.returncode}")
        try:
            sock = socket.create_connection(("127.0.0.1", port), timeout=min(0.5, remaining(deadline, "monitor_connect")))
            sock.settimeout(min(0.5, remaining(deadline, "monitor_hello")))
            client = monitor.MonitorClient(sock)
            hello = json.loads(client.file.readline())
            if hello.get("method") != "hello":
                raise ObserverError("setup_observer_failure", "monitor_hello", f"unexpected monitor greeting: {hello}")
            rpc(client, "events.subscribe", {"kinds": ["bp"]}, deadline, "monitor_subscribe")
            return client
        except ObserverError:
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
            raise
        except (OSError, json.JSONDecodeError, monitor.MonitorError):
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
            time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))
    raise ObserverError("setup_observer_failure", "monitor_connect", "monitor listener did not accept a client")


def setup_breakpoints(client, symbols: dict[str, int], deadline: float) -> list[int]:
    breakpoint_ids: list[int] = []
    for name, address in symbols.items():
        response = rpc(client, "set_breakpoint", {"addr": address, "kind": "exec"}, deadline, "breakpoint_setup")
        breakpoint_ids.append(int(response["id"]))
    return breakpoint_ids


def clear_breakpoints(client, breakpoint_ids: list[int], deadline: float) -> None:
    for ident in breakpoint_ids:
        rpc(client, "clear_breakpoint", {"id": ident}, deadline, "breakpoint_cleanup")


def run_observer(args: argparse.Namespace, inputs: dict[str, Any]) -> dict[str, Any]:
    evidence_dir: Path = inputs["evidence_dir"]

    result: dict[str, Any] = {
        "schema": "feat011-intermission-observer-v1",
        "ticket": "FEAT-011",
        "scenario": args.scenario,
        "observer_status": "not_started",
        "manual_review_status": "pending",
        "score_source": "displayed frames only; no score RAM read",
        "frame_files": [],
        "events": [],
        "cue_calls_after_left": [],
        "cue_call_counts_after_left": {},
        "cue_call_history_discarded": 0,
        "music_busy_transitions": [],
        "breakpoint_hits": {},
        "cleanup": {"requested": False, "confirmed": False},
        "identity": {
            "rom_path": str(inputs["rom"]),
            "rom_sha256": digest_file(inputs["rom"]),
            "xroar_path": str(inputs["xroar"]),
            "xroar_sha256": digest_file(inputs["xroar"]),
            "symbol_map_path": str(inputs["symbol_map"]),
            "symbol_map_sha256": digest_file(inputs["symbol_map"]),
            "observer_path": str(Path(__file__).resolve()),
            "observer_sha256": digest_file(Path(__file__).resolve()),
            "breakpoint_symbols": inputs["symbol_names"],
            "breakpoint_addresses": {key: f"${value:04X}" for key, value in inputs["symbols"].items()},
        },
        "bounds": {
            "whole_phase_max_seconds": args.timeout,
            "cleanup_and_evidence_reserve_seconds": CLEANUP_RESERVE_SECONDS,
            "max_frame_files": MAX_FRAME_FILES,
            "max_xroar_log_bytes_retained": MAX_LOG_BYTES,
        },
    }
    monitor = None
    process = client = capture = None
    breakpoints: list[int] = []
    pressed: set[int] = set()
    started = time.monotonic()
    event_seen = False
    phase_start = None
    total_deadline = None
    work_deadline = None
    log_lines: list[str] = []

    try:
        # Start immediately before launch. Reserve the final five seconds for
        # owned-process cleanup and the small evidence files.
        monitor = load_monitor_module()
        phase_start = time.monotonic()
        total_deadline = phase_start + args.timeout
        work_deadline = total_deadline - CLEANUP_RESERVE_SECONDS
        process, child_command, port = launch(inputs["xroar"], inputs["rom"], monitor)
        capture = BoundedCapture(process.stdout)
        client = connect_monitor(monitor, process, port, work_deadline)
        result["process"] = {"pid": process.pid, "argv": child_command}
        add_log(result, "xroar_started", started, pid=process.pid)
        breakpoints = setup_breakpoints(client, inputs["symbols"], work_deadline)

        expected = inputs["expected"]
        address_names = {value: key for key, value in inputs["symbols"].items()}
        route_complete = False
        return_seen = False
        left_started = False
        fixture_waiting_for_pre_frame = False
        start_tapped_modes: set[int] = set()
        release_next_publish: set[int] = set()
        before_frame_commit_baseline: int | None = None
        input_control_commit_baseline: int | None = None
        event_commit_baseline: int | None = None
        return_commit_baseline: int | None = None
        last_observed_publish_sequence: int | None = None
        before_state: dict[str, int] | None = None
        event_state: dict[str, int] | None = None
        return_state: dict[str, int] | None = None
        before_frame_saved = False
        event_frame_pending = False
        return_frame_pending = False
        event_frame_saved = False
        return_frame_saved = False
        busy_seen = False
        idle_after_busy = False
        previous_busy: int | None = None
        event_started_at: float | None = None
        route_completed_at: float | None = None
        intermission_publish_count = 0
        input_control_sampled = False
        calls_after_left: list[int] = result["cue_calls_after_left"]
        cue_counts: dict[int, int] = {}
        hits: dict[str, int] = result["breakpoint_hits"]

        while time.monotonic() < work_deadline:
            if process.poll() is not None:
                category = "setup_observer_failure" if not event_seen else "missing_coverage"
                raise ObserverError(category, "xroar_process", f"XRoar exited unexpectedly: {process.returncode}")
            try:
                hit = client.run_to_breakpoint(timeout=remaining(work_deadline, "runtime_observation"))
            except (OSError, json.JSONDecodeError, monitor.MonitorError, TimeoutError) as exc:
                category = "setup_observer_failure" if not event_seen else "missing_coverage"
                raise ObserverError(category, "runtime_observation", str(exc)) from exc
            pc = hit.get("pc")
            if not isinstance(pc, int) or pc not in address_names:
                category = "setup_observer_failure" if not event_seen else "missing_coverage"
                raise ObserverError(category, "runtime_observation", f"unexpected breakpoint stop: {hit}")
            name = address_names[pc]
            hits[name] = hits.get(name, 0) + 1
            add_log(result, "breakpoint", started, name=name, pc=f"${pc:04X}")

            if name == "cue_enqueue":
                registers = rpc(client, "read_registers", None, work_deadline, "cue_observation")
                cue_id = int(registers["a"])
                if left_started:
                    cue_counts[cue_id] = cue_counts.get(cue_id, 0) + 1
                    if len(calls_after_left) < 256:
                        calls_after_left.append(cue_id)
                    else:
                        result["cue_call_history_discarded"] += 1
                    result["cue_call_counts_after_left"] = {str(key): value for key, value in cue_counts.items()}
                    add_log(result, "cue_enqueue_after_left", started, cue_id=cue_id)
                continue

            if name == "event_start":
                if not left_started:
                    raise ObserverError("setup_observer_failure", "event_start", "event-start breakpoint occurred before the controlled E pickup")
                if event_seen:
                    raise ObserverError("product_assertion_failure", "event_start", "the same intermission event started more than once")
                event_state = state_snapshot(client, work_deadline, "event_start")
                if event_state["event_kind"] != expected["event_kind"]:
                    raise ObserverError("product_assertion_failure", "event_start", f"event kind {event_state['event_kind']} does not match {args.scenario}")
                expected_mask = expected.get("special_after_pickup", expected.get("extra_after_pickup"))
                observed_mask = event_state["special_bits"] if args.scenario == "special-e" else event_state["extra_bits"]
                if observed_mask != expected_mask:
                    raise ObserverError("product_assertion_failure", "event_start", f"letter mask {observed_mask:02X} does not match {expected_mask:02X}")
                other_mask = event_state["extra_bits"] if args.scenario == "special-e" else event_state["special_bits"]
                expected_other_mask = expected["extra_after_pickup"] if args.scenario == "special-e" else expected["special_after_pickup"]
                if other_mask != expected_other_mask:
                    raise ObserverError("product_assertion_failure", "event_start", f"other event mask {other_mask:02X} does not match {expected_other_mask:02X}")
                if event_state["bonus_color"] != expected["color"]:
                    raise ObserverError("product_assertion_failure", "event_start", f"bonus color {event_state['bonus_color']} does not match expected {expected['color']}")
                if before_state is None or event_state["lives"] != before_state["lives"]:
                    raise ObserverError("product_assertion_failure", "event_start", "reserve count changed before the intermission reward")
                event_seen = True
                event_started_at = time.monotonic()
                input_control_commit_baseline = read_word(
                    client, FB_COMMIT_SEQ, work_deadline, "intermission_input_control"
                )
                event_commit_baseline = input_control_commit_baseline
                last_observed_publish_sequence = input_control_commit_baseline
                event_frame_pending = True
                add_log(result, "event_confirmed", started, state=event_state)
                # Adversarial stimulus is ordinary keyboard input, not a state write.
                if LEFT_SCAN in pressed:
                    inject(client, LEFT_SCAN, "release", work_deadline, "pickup_key_release")
                    pressed.discard(LEFT_SCAN)
                for key in (LEFT_SCAN, START_SCAN):
                    inject(client, key, "press", work_deadline, "intermission_input_control")
                    pressed.add(key)
                    release_next_publish.add(key)
                continue

            if name == "route_complete":
                if not event_seen:
                    raise ObserverError("setup_observer_failure", "route_complete", "route-complete binding occurred before the E event")
                if route_complete:
                    raise ObserverError("product_assertion_failure", "route_complete", "the same intermission route completed more than once")
                route_complete = True
                route_completed_at = time.monotonic()
                if not input_control_sampled:
                    raise ObserverError("missing_coverage", "intermission_input_control", "the ordinary direction/Start stimulus was not carried through a published frame")
                add_log(result, "route_complete", started)
                continue

            if name == "normal_return":
                if not event_seen:
                    raise ObserverError("setup_observer_failure", "normal_return", "normal-return binding occurred before the E event")
                if return_seen:
                    raise ObserverError("product_assertion_failure", "normal_return", "the intermission returned to normal gameplay more than once")
                return_seen = True
                return_state = state_snapshot(client, work_deadline, "normal_return")
                if not route_complete:
                    raise ObserverError("product_assertion_failure", "normal_return", "normal gameplay returned before the route-complete binding")
                observed_event_cues = {cue: cue_counts.get(cue, 0) for cue in (10, 11)}
                if observed_event_cues != {10: 1 if expected["cue"] == 10 else 0, 11: 1 if expected["cue"] == 11 else 0}:
                    raise ObserverError("product_assertion_failure", "cue_selection", f"expected only cue {expected['cue']} once before return, observed counts {observed_event_cues}")
                if not busy_seen:
                    raise ObserverError("missing_coverage", "cue_completion", "published cue-busy state was not observed")
                busy_at_return = read_byte(client, AUDIO_MUSIC_PUBLISHED_BUSY, work_deadline, "normal_return")
                if busy_at_return == 0 and busy_seen:
                    if not result["music_busy_transitions"] or result["music_busy_transitions"][-1]["busy"] != 0:
                        result["music_busy_transitions"].append({
                            "elapsed_seconds": round(time.monotonic() - started, 4),
                            "busy": 0,
                            "observed_at": "normal_return",
                        })
                    idle_after_busy = True
                elif busy_at_return != 0:
                    raise ObserverError("product_assertion_failure", "normal_return", "normal gameplay returned while the published music state was still busy")
                if not idle_after_busy:
                    raise ObserverError("product_assertion_failure", "normal_return", "normal gameplay returned before the published music state became idle")
                if not event_frame_saved:
                    raise ObserverError("missing_coverage", "event_frame", "route completed without a captured published intermission frame")
                if return_state["presentation_mode"] != MODE_NORMAL or return_state["event_kind"] != 0:
                    raise ObserverError("product_assertion_failure", "normal_return", f"return binding did not show cleared event state in normal mode: {return_state}")
                return_commit_baseline = read_word(
                    client, FB_COMMIT_SEQ, work_deadline, "normal_return"
                )
                return_frame_pending = True
                add_log(result, "normal_return", started, state=return_state)
                continue

            # Only fbf_ready is allowed to read/capture the published display.
            if not event_seen:
                snapshot = {
                    "presentation_mode": read_byte(client, PRES_MODE, work_deadline, "gameplay_entry"),
                    "initial_entry_state": read_byte(client, INITIAL_ENTRY_STATE, work_deadline, "gameplay_entry"),
                    "player_cell": list(read_bytes(client, PLAYER_CELL_X, 2, work_deadline, "gameplay_entry")),
                }
                if release_next_publish:
                    for key in sorted(release_next_publish):
                        inject(client, key, "release", work_deadline, "input_release")
                        pressed.discard(key)
                    release_next_publish.clear()
                if (snapshot["presentation_mode"] in (MODE_ATTRACT, MODE_INSTRUCTIONS)
                        and snapshot["presentation_mode"] not in start_tapped_modes):
                    inject(client, START_SCAN, "press", work_deadline, "normal_start_input")
                    pressed.add(START_SCAN)
                    release_next_publish.add(START_SCAN)
                    start_tapped_modes.add(snapshot["presentation_mode"])
                    add_log(
                        result, "normal_start_input", started,
                        scan_code=START_SCAN,
                        presentation_mode=snapshot["presentation_mode"],
                    )
                if fixture_waiting_for_pre_frame:
                    publish_sequence = read_word(
                        client, FB_COMMIT_SEQ, work_deadline, "before_pickup_publication"
                    )
                    if (before_frame_commit_baseline is not None
                            and ((publish_sequence - before_frame_commit_baseline) & 0xFFFF) > 0):
                        frame, front_owner, publish_sequence = read_frame(
                            client, work_deadline, "before_pickup_frame"
                        )
                        frame_name = "before-pickup.png"
                        frame_hash = write_frame_png(evidence_dir / frame_name, frame)
                        result["frame_files"].append({
                            "name": frame_name, "sha256": frame_hash,
                            "front_owner": front_owner, "publish_sequence": publish_sequence,
                            "purpose": "published visible score and fixture before pickup; manual reading",
                        })
                        before_frame_saved = True
                        fixture_waiting_for_pre_frame = False
                        left_started = True
                        inject(client, LEFT_SCAN, "press", work_deadline, "normal_left_input")
                        pressed.add(LEFT_SCAN)
                        add_log(result, "gameplay_fixture_ready", started, state=before_state, scan_code=LEFT_SCAN)
                    continue
                if (snapshot["presentation_mode"] == MODE_NORMAL
                        and snapshot["initial_entry_state"] == 0
                        and snapshot["player_cell"] == [12, 18]
                        and not left_started):
                    before_state = state_snapshot(client, work_deadline, "fixture_precondition")
                    if (before_state["special_bits"] != expected["special_before"]
                            or before_state["extra_bits"] != expected["extra_before"]
                            or before_state["bonus_color"] != expected["color"]
                            or before_state["lives"] >= MAX_RESERVE_LIVES):
                        raise ObserverError("setup_observer_failure", "fixture_precondition", f"fixture state does not match {args.scenario}: {before_state}")
                    before_frame_commit_baseline = read_word(
                        client, FB_COMMIT_SEQ, work_deadline, "before_pickup_publication"
                    )
                    fixture_waiting_for_pre_frame = True
                    add_log(result, "gameplay_fixture_ready", started, state=before_state)
                elif left_started:
                    observed_event = read_byte(client, EVENT_KIND, work_deadline, "event_wait")
                    if observed_event not in (0, expected["event_kind"]):
                        raise ObserverError("product_assertion_failure", "event_wait", f"E pickup selected event {observed_event}, expected {expected['event_kind']}")
                continue

            # Read only the published physical FRONT owner. A fbf_ready hit
            # marks BACK pending; FB_COMMIT_SEQ advances after the IRQ publishes it.
            publish_sequence = read_word(client, FB_COMMIT_SEQ, work_deadline, "frame_publication")
            if last_observed_publish_sequence is not None:
                published_delta = (publish_sequence - last_observed_publish_sequence) & 0xFFFF
                if not route_complete:
                    intermission_publish_count += published_delta
                last_observed_publish_sequence = publish_sequence
            busy = read_byte(client, AUDIO_MUSIC_PUBLISHED_BUSY, work_deadline, "cue_completion")
            if previous_busy is None or busy != previous_busy:
                result["music_busy_transitions"].append({
                    "elapsed_seconds": round(time.monotonic() - started, 4),
                    "busy": busy,
                })
                previous_busy = busy
            if busy:
                busy_seen = True
            elif busy_seen:
                idle_after_busy = True

            if (release_next_publish and event_seen
                    and input_control_commit_baseline is not None
                    and ((publish_sequence - input_control_commit_baseline) & 0xFFFF) > 0):
                for key in sorted(release_next_publish):
                    inject(client, key, "release", work_deadline, "intermission_input_release")
                    pressed.discard(key)
                release_next_publish.clear()
                input_control_sampled = True

            if (event_frame_pending and not event_frame_saved
                    and event_commit_baseline is not None
                    and ((publish_sequence - event_commit_baseline) & 0xFFFF) > 0):
                frame, front_owner, publish_sequence = read_frame(
                    client, work_deadline, "event_frame"
                )
                frame_name = "event.png"
                frame_hash = write_frame_png(evidence_dir / frame_name, frame)
                result["frame_files"].append({
                    "name": frame_name, "sha256": frame_hash,
                    "front_owner": front_owner, "publish_sequence": publish_sequence,
                    "purpose": "published event display after E pickup; manual visual review",
                })
                event_frame_saved = True
                event_frame_pending = False
            if (return_frame_pending and return_commit_baseline is not None
                    and ((publish_sequence - return_commit_baseline) & 0xFFFF) > 0):
                return_state = state_snapshot(client, work_deadline, "return_frame")
                frame, front_owner, publish_sequence = read_frame(
                    client, work_deadline, "return_frame"
                )
                frame_name = "return.png"
                frame_hash = write_frame_png(evidence_dir / frame_name, frame)
                result["frame_files"].append({
                    "name": frame_name, "sha256": frame_hash,
                    "front_owner": front_owner, "publish_sequence": publish_sequence,
                    "purpose": "published returned gameplay and displayed score; manual reading",
                })
                return_frame_saved = True
                return_frame_pending = False
                break

        if not event_seen:
            raise ObserverError("setup_observer_failure", "event_start", "E pickup and event-start binding were not reached before the work deadline")
        if not route_complete or not return_seen:
            raise ObserverError("missing_coverage", "normal_return", "required route-complete or normal-return binding was not reached")
        if not before_frame_saved or not event_frame_saved or not return_frame_saved:
            raise ObserverError("missing_coverage", "frame_capture", "one or more of the three approved frames was not captured")

        expected_cue = expected["cue"]
        observed_event_cues = {cue: cue_counts.get(cue, 0) for cue in (10, 11)}
        if observed_event_cues != {10: 1 if expected_cue == 10 else 0, 11: 1 if expected_cue == 11 else 0}:
            raise ObserverError("product_assertion_failure", "cue_selection", f"expected only cue {expected_cue} once after E pickup, observed counts {observed_event_cues}")
        if not busy_seen or not idle_after_busy:
            raise ObserverError("missing_coverage", "cue_completion", "published cue busy-to-idle transition was not observed")
        busy_values = [item["busy"] for item in result["music_busy_transitions"]]
        if busy_values.count(1) != 1 or busy_values[-1] != 0:
            raise ObserverError("product_assertion_failure", "cue_completion", f"expected one busy interval ending idle, observed {busy_values}")
        if return_state is None or before_state is None:
            raise ObserverError("missing_coverage", "return_frame", "fixture state snapshots are incomplete")
        if return_state["lives"] - before_state["lives"] != expected["life_delta"]:
            raise ObserverError("product_assertion_failure", "reward", f"reserve-life delta {return_state['lives'] - before_state['lives']} does not match {expected['life_delta']}")
        result["observer_status"] = "pass"
        result["manual_review_status"] = "pending: inspect displayed score and event/marker frames"
        result["automated_oracle"] = {
            "event_kind": expected["event_kind"],
            "cue_id_exactly_once": expected_cue,
            "music_busy_to_idle_observed": True,
            "route_complete_before_return": True,
            "life_delta": expected["life_delta"],
            "score_ram_read": False,
            "intermission_start_and_direction_stimulus": [START_SCAN, LEFT_SCAN],
            "input_control_sampled_at_published_frame": input_control_sampled,
            "intermission_published_frames_before_route_complete": intermission_publish_count,
            "event_to_route_complete_seconds": round(route_completed_at - event_started_at, 4) if route_completed_at is not None and event_started_at is not None else None,
        }
        add_log(result, "observer_assertions_pass", started)
    except ObserverError as exc:
        category = exc.category
        if category == "missing_coverage" and not event_seen:
            category = "setup_observer_failure"
        result["observer_status"] = category
        result["failure"] = {"phase": exc.phase, "detail": str(exc)}
        add_log(result, "observer_failure", started, category=category, phase=exc.phase, detail=str(exc))
    except Exception as exc:
        outcome_error = ObserverError("setup_observer_failure", "observer_exception", f"{type(exc).__name__}: {exc}")
        result["observer_status"] = outcome_error.category
        result["failure"] = {"phase": outcome_error.phase, "detail": str(outcome_error)}
        add_log(result, "observer_failure", started, category=outcome_error.category, phase=outcome_error.phase, detail=str(outcome_error))
    finally:
        if client is not None:
            # Release only keys this process injected; no guest-state or register writes.
            for key in sorted(pressed):
                try:
                    if work_deadline is not None and time.monotonic() < work_deadline:
                        inject(client, key, "release", work_deadline, "cleanup_input_release")
                except Exception as exc:
                    result["cleanup"]["input_release_error"] = str(exc)
            try:
                if breakpoints and work_deadline is not None and time.monotonic() < work_deadline:
                    clear_breakpoints(client, breakpoints, work_deadline)
            except Exception as exc:
                result["cleanup"]["breakpoint_clear_error"] = str(exc)
            try:
                client.close()
            except Exception as exc:
                result["cleanup"]["monitor_close_error"] = str(exc)

        if process is not None:
            result["cleanup"]["requested"] = True
            result["cleanup"]["pid"] = process.pid
            try:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=min(1.25, max(0.05, (total_deadline or time.monotonic()) - time.monotonic())))
                    except subprocess.TimeoutExpired:
                        process.kill()
                    process.wait(timeout=min(1.25, max(0.05, (total_deadline or time.monotonic()) - time.monotonic())))
                result["cleanup"]["exit_code"] = process.poll()
                result["cleanup"]["confirmed"] = process.poll() is not None
            except Exception as exc:
                result["cleanup"]["error"] = f"{type(exc).__name__}: {exc}"
            if not result["cleanup"]["confirmed"]:
                result["observer_status"] = "setup_observer_failure"
                result["failure"] = {"phase": "cleanup", "detail": "owned XRoar process exit was not confirmed"}
        if capture is not None:
            remaining_join = max(0.0, min(0.5, (total_deadline or time.monotonic()) - time.monotonic()))
            joined = capture.finish(remaining_join)
            result["xroar_output"] = {
                "bytes_observed": capture.total_bytes,
                "bytes_retained": len(capture.data),
                "truncated": capture.total_bytes > len(capture.data),
                "reader_stopped": joined,
                "reader_error": capture.error,
            }
            if capture.data:
                log_lines.append(capture.data.decode("utf-8", errors="replace"))
            if not joined:
                result["observer_status"] = "setup_observer_failure"
                result["failure"] = {"phase": "cleanup", "detail": "XRoar output reader did not reach EOF after owned process exit"}

        cleanup_errors = {
            key: result["cleanup"][key]
            for key in ("input_release_error", "breakpoint_clear_error", "monitor_close_error", "error")
            if key in result["cleanup"]
        }
        if capture is not None and capture.error is not None:
            cleanup_errors["output_reader_error"] = capture.error
        if cleanup_errors and result["observer_status"] == "pass":
            result["observer_status"] = "setup_observer_failure"
            result["failure"] = {
                "phase": "cleanup",
                "detail": f"observer cleanup reported errors: {cleanup_errors}",
            }

    if phase_start is not None:
        result["duration_seconds"] = round(time.monotonic() - phase_start, 4)
        result["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        if total_deadline is not None and time.monotonic() > total_deadline:
            result["observer_status"] = "missing_coverage"
            result["failure"] = {
                "phase": "whole_phase_deadline",
                "detail": f"{args.timeout:g}-second XRoar-to-result-and-cleanup maximum exceeded",
            }
    result["cleanup"].setdefault("confirmed", process is None)
    result["event_history_retained"] = len(result["events"])
    log_header = [
        f"scenario={args.scenario}",
        f"observer_status={result['observer_status']}",
        f"duration_seconds={result.get('duration_seconds', 'not-started')}",
        "milestones=" + json.dumps(result["events"], sort_keys=True),
    ]
    if capture is not None:
        log_header += ["--- XRoar output (bounded capture) ---", *log_lines]
    (evidence_dir / "runtime.log").write_text("\n".join(log_header) + "\n", encoding="utf-8")
    (evidence_dir / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xroar", type=Path, required=True)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--symbol-map", type=Path, required=True)
    parser.add_argument("--scenario", choices=tuple(EXPECTED), required=True)
    parser.add_argument("--event-start-symbol", required=True)
    parser.add_argument("--route-complete-symbol", required=True)
    parser.add_argument("--return-symbol", required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=MAX_TIMEOUT_SECONDS)
    args = parser.parse_args()
    try:
        evidence_dir = prepare_evidence_dir(args)
    except Exception as exc:
        parser.error(f"evidence path is unsafe or unavailable: {exc}")
    try:
        inputs = preflight(args, evidence_dir)
    except Exception as exc:
        result = {
            "schema": "feat011-intermission-observer-v1",
            "ticket": "FEAT-011",
            "scenario": args.scenario,
            "observer_status": "setup_observer_failure",
            "manual_review_status": "pending",
            "score_source": "displayed frames only; no score RAM read",
            "failure": {"phase": "preflight", "detail": f"{type(exc).__name__}: {exc}"},
            "process": None,
            "cleanup": {"requested": False, "confirmed": True},
            "frame_files": [],
            "duration_seconds": 0.0,
        }
        (evidence_dir / "runtime.log").write_text(
            f"scenario={args.scenario}\nobserver_status=setup_observer_failure\npreflight={type(exc).__name__}: {exc}\n",
            encoding="utf-8",
        )
        (evidence_dir / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"scenario": args.scenario, "observer_status": result["observer_status"], "evidence_dir": str(evidence_dir)}, sort_keys=True))
        return 1
    result = run_observer(args, inputs)
    print(json.dumps({
        "scenario": args.scenario,
        "observer_status": result["observer_status"],
        "manual_review_status": result["manual_review_status"],
        "duration_seconds": result.get("duration_seconds"),
        "evidence_dir": str(inputs["evidence_dir"]),
    }, sort_keys=True))
    return 0 if result["observer_status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
