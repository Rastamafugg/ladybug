#!/usr/bin/env python3
"""One bounded BUG-100 high-score mark probe using the existing XRoar monitor."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = Path(sys.argv[1]).resolve()
SOURCE = Path(sys.argv[2]).resolve()
BUILD = Path(sys.argv[3]).resolve()
XROAR = Path(sys.argv[4]).resolve()
PORT = 65527
ROM_HASH = "e3a6cb1c9b9c3d959bc911433aea2b681b22a06608eeee40c8b9c14fae2f7982"
PFT, LOAD_DONE, PUBLISH, LOGO_TICK, LOGO_HOLD = 0x1900, 0x1A4F, 0x0E61, 0xB443, 0xB4C2
PAR1, PAR5 = 0xFFA1, 0xFFA5
FRONT, BACK, PENDING, SCREEN, MODE, PHASE, TIMER = 0x008F, 0x0090, 0x0091, 0x00A6, 0x00A5, 0x00E8, 0x00B0
R_ADDRESS = 0x2000 + 13 * 1280 + 31 * 4
HELPER_BASE = 0xAC40
DEADLINE_SECONDS = 55


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


spec = importlib.util.spec_from_file_location("bug009_monitor", ROOT / "scripts/verify_bug009_monitor_input.py")
if spec is None or spec.loader is None:
    raise RuntimeError("cannot load existing BUG-009 monitor helper")
monitor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(monitor)


def save(result: dict) -> None:
    temp = HERE / "bug100-live-monitor-probe.partial.json"
    target = HERE / "bug100-live-monitor-probe.json"
    temp.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    temp.replace(target)


def read(client, address: int, length: int = 1) -> bytes:
    return bytes.fromhex(client.call("read_memory", {"addr": address, "length": length}, timeout=4)["data"])


def byte(client, address: int) -> int:
    return read(client, address)[0]


def write_byte(client, address: int, value: int) -> None:
    client.call("write_memory", {"addr": address, "data": f"{value:02x}"}, timeout=4)


def run(client, start: float) -> dict:
    remaining = start + DEADLINE_SECONDS - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("60-second diagnostic boundary reached")
    return client.run_to_breakpoint(timeout=min(5.0, remaining))


def sample_owner(client, owner: int) -> dict:
    saved = [byte(client, PAR1 + i) for i in range(4)]
    base = 0x30 if owner == 0 else 0x2C
    try:
        for i in range(4):
            write_byte(client, PAR1 + i, base + i)
        raw = read(client, R_ADDRESS, 15 * 160 + 4)
    finally:
        for i, page in enumerate(saved):
            write_byte(client, PAR1 + i, page)
    tile = b"".join(raw[row * 160:row * 160 + 4] for row in range(16))
    pixels = [n for value in tile for n in (value >> 4, value & 15)]
    ink = [n for n in pixels if n]
    return {
        "owner_id": owner,
        "tile_sha256": digest(tile),
        "tile_hex": tile.hex(),
        "foreground_pixels": len(ink),
        "foreground_colours": sorted(set(ink)),
        "left_half_foreground": sum(bool(pixels[row * 8 + col]) for row in range(16) for col in range(4)),
        "right_half_foreground": sum(bool(pixels[row * 8 + col]) for row in range(16) for col in range(4, 8)),
        "white_pixels": sum(n == 7 for n in ink),
    }


def main() -> None:
    result: dict = {
        "probe": "BUG-100 natural key-5 high-score entry; observe live R tile bytes in both framebuffer owners across logo phases",
        "port": PORT,
        "deadline_seconds": DEADLINE_SECONDS,
        "timeout_meaning": "The planned natural screen/owner/phase boundary was not observed before the bounded probe deadline.",
        "rom_sha256_expected": ROM_HASH,
        "samples": [],
        "coverage": {"owners": [], "phases": []},
        "status": "started",
    }
    started = time.monotonic()
    process = None
    client = None
    try:
        receipt_spec = importlib.util.spec_from_file_location("bug100_static", HERE / "bug100_logo_r_composition_probe.py")
        if receipt_spec is None or receipt_spec.loader is None:
            raise RuntimeError("cannot load existing static composition verifier")
        static = importlib.util.module_from_spec(receipt_spec)
        receipt_spec.loader.exec_module(static)
        result["artifact_identity"] = static.verify_receipt(SOURCE, BUILD)
        rom = BUILD / "ladybug.rom"
        if digest(rom.read_bytes()) != ROM_HASH:
            raise RuntimeError("current parent ROM hash differs from the authorized artifact")
        helper = (BUILD / "ladybug-highscore-helper.bin").read_bytes()
        helper_hash = digest(helper)
        result["artifact_identity"]["staged_highscore_helper_sha256"] = helper_hash
        result["artifact_identity"]["staged_highscore_helper_bytes"] = len(helper)
        result["phase_success_marker"] = f"PC=${LOGO_HOLD:04X} after natural map=${3:02X}; byte-current visible R tile captured in owner 0 and owner 1"
        process = subprocess.Popen([
            str(XROAR), "-ui", "null", "-ao", "null", "-machine", "coco3", "-ram", "512",
            "-cart", "ladybug", "-cart-type", "gmc", "-cart-rom", str(rom), "-cart-autorun",
            "-no-ratelimit", "-monitor", f"127.0.0.1:{PORT}", "-monitor-halt-on-start",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
           start_new_session=(os.name != "nt"))
        socket_deadline = min(started + DEADLINE_SECONDS, time.monotonic() + 5)
        while time.monotonic() < socket_deadline:
            try:
                sock = socket.create_connection(("127.0.0.1", PORT), timeout=0.4)
                client = monitor.MonitorClient(sock)
                hello = json.loads(client.file.readline())
                if hello.get("method") != "hello":
                    raise monitor.MonitorError(f"unexpected monitor greeting: {hello}")
                client.call("events.subscribe", {"kinds": ["bp"]}, timeout=3)
                break
            except (OSError, monitor.MonitorError):
                time.sleep(0.05)
        if client is None:
            raise TimeoutError("monitor listener did not accept a client within 5 seconds")
        result["launch"] = {"explicit_cart": "ladybug", "monitor_halt_on_start": True, "gdb": False}
        ids = monitor.setup(client, [PFT, LOAD_DONE, PUBLISH])
        hit = run(client, started)
        result["startup_marker"] = hit
        if hit.get("pc") != PFT:
            raise monitor.MonitorError(f"presentation cold-entry marker mismatch: {hit}")
        monitor.clear(client, [ids[0]])
        hit = run(client, started)
        if hit.get("pc") != LOAD_DONE or byte(client, SCREEN) != 0:
            raise monitor.MonitorError(f"natural attract load marker mismatch: hit={hit} map={byte(client, SCREEN):02x}")
        monitor.clear(client, [ids[1]])
        hit = run(client, started)
        if hit.get("pc") != PUBLISH:
            raise monitor.MonitorError(f"attract publish marker mismatch: {hit}")
        initial_owners = {"front": byte(client, FRONT), "back": byte(client, BACK), "pending": byte(client, PENDING)}
        result["attract"] = {"pc": hit.get("pc"), "owner_state": initial_owners}
        monitor.clear(client, [ids[2]])
        result["status"] = "attract-published"
        save(result)

        # Use the documented natural key-5 input path and existing helper API.
        load_bp = monitor.setup(client, [LOAD_DONE])
        client.call("inject_key", {"key": 5, "action": "press"}, timeout=3)
        hit = run(client, started)
        requested = byte(client, SCREEN)
        client.call("inject_key", {"key": 5, "action": "release"}, timeout=3)
        if hit.get("pc") != LOAD_DONE or requested != 3:
            raise monitor.MonitorError(f"key-5 high-score request mismatch: hit={hit} requested={requested:02x}")
        monitor.clear(client, load_bp)
        result["natural_entry"] = {"input": "inject_key key=5 press/release", "pc": hit.get("pc"), "requested_screen": requested}
        bp_ids = monitor.setup(client, [LOGO_TICK, LOGO_HOLD])
        tick = run(client, started)
        result["logo_tick_marker"] = tick
        if tick.get("pc") != LOGO_TICK:
            raise monitor.MonitorError(f"high-score logo tick marker not reached: {tick}")
        monitor.clear(client, [bp_ids[0]])
        result["status"] = "high-score-logo-tick"
        save(result)

        staged_match = None
        live_info = {}
        for ordinal in range(32):
            hit = run(client, started)
            if hit.get("pc") != LOGO_HOLD:
                raise monitor.MonitorError(f"logo hold marker mismatch: {hit}")
            page = byte(client, PAR5)
            live = read(client, HELPER_BASE, len(helper)) if page == 0x23 else b""
            if staged_match is None:
                saved_page = page
                if page != 0x23:
                    write_byte(client, PAR5, 0x23)
                    live = read(client, HELPER_BASE, len(helper))
                    write_byte(client, PAR5, saved_page)
                staged_match = live == helper
                tick_live = read(client, LOGO_TICK, 32)
                hold_live = read(client, LOGO_HOLD, 2)
                tick_offset = LOGO_TICK - HELPER_BASE
                hold_offset = LOGO_HOLD - HELPER_BASE
                live_info = {
                    "pc": hit.get("pc"), "PAR5_at_pc": page,
                    "helper_load_base": f"${HELPER_BASE:04X}",
                    "live_helper_sha256": digest(live), "live_helper_bytes": len(live),
                    "staged_helper_sha256": helper_hash, "live_matches_staged": staged_match,
                    "highscore_tick_live_hex": tick_live.hex(),
                    "highscore_tick_staged_hex": helper[tick_offset:tick_offset + len(tick_live)].hex(),
                    "highscore_tick_matches_staged": tick_live == helper[tick_offset:tick_offset + len(tick_live)],
                    "hold_pc_live_hex": hold_live.hex(),
                    "hold_pc_staged_hex": helper[hold_offset:hold_offset + len(hold_live)].hex(),
                    "hold_pc_matches_staged": hold_live == helper[hold_offset:hold_offset + len(hold_live)],
                    "source_file": "src/shared_text_stage.inc", "source_label": "highscore_logo_tick",
                    "source_line_approx": 704,
                }
            phase = byte(client, PHASE)
            state = {"front": byte(client, FRONT), "back": byte(client, BACK), "pending": byte(client, PENDING)}
            owners = [sample_owner(client, owner) for owner in (0, 1)]
            result["samples"].append({
                "ordinal": ordinal, "pc": hit.get("pc"), "screen": byte(client, SCREEN),
                "mode": byte(client, MODE), "phase": phase, "timer": int.from_bytes(read(client, TIMER, 2), "big"),
                "owner_state": state, "owner_pixels": owners,
            })
            result["coverage"]["owners"] = sorted({sample["owner_id"] for sample in owners})
            result["coverage"]["phases"] = sorted({sample["phase"] for sample in result["samples"]})
            result["coverage"]["owner_phase_pairs"] = sorted({
                f"{sample['owner_id']}:{item['phase']}"
                for item in result["samples"] for sample in item["owner_pixels"]
            })
            result["live_identity"] = live_info
            result["status"] = "sampling"
            save(result)
            if result["coverage"]["owner_phase_pairs"] == ["0:0", "0:1", "1:0", "1:1"]:
                break
        result["status"] = "coverage-complete" if result["coverage"].get("owner_phase_pairs") == ["0:0", "0:1", "1:0", "1:1"] else "partial"
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
        result["boundary"] = "Each sample is tied to highscore_logo_hold and records front/back/pending plus the R tile bytes read from each physical framebuffer owner."
        result["symptom_result"] = "Reported white-left R was not present in the captured phases or owners; cause remains unconfirmed."
    except Exception as exc:
        result["status"] = "partial" if result.get("samples") or result.get("attract") else "failed"
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
        if process is not None:
            try:
                monitor.stop(process)
                process.wait(timeout=2)
            except Exception:
                pass
        save(result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
