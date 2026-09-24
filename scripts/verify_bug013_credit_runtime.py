#!/usr/bin/env python3
"""Verify natural BUG-013 credit input, coin footprints, and credit hold."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import verify_bug011_runtime as probe  # noqa: E402
import verify_presentation as presentation  # noqa: E402

PRESENTATION_MAP = ROOT / "build/ladybug-presentation-runtime.map"
MODULE = ROOT / "build/ladybug-presentation-runtime.bin"
COLD = ROOT / "build/ladybug-presentation-cold.bin"
MANIFEST = ROOT / "build/ladybug-presentation.json"
LAYOUT = ROOT / "build/ladybug-sparse-layout.json"
ROM = ROOT / "build/ladybug.rom"
PRES_MODE, PRES_SCREEN, PRES_CREDITS, PRES_EVENT = 0xA5, 0xA6, 0xA8, 0xA9
FB_FRONT, FB_BACK = 0x8F, 0x90
MODE_ATTRACT, MODE_CREDIT = 2, 5
HIGH_SCORE_MAP = 3
FRAME_COUNTER = 0x38 * 8192 + 2


def fail(phase: str, marker: str, detail: str) -> None:
    raise SystemExit(f"phase={phase} marker={marker} failure={detail}")


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def physical(client, address: int, length: int) -> bytes:
    return bytes.fromhex(client.call("read_memory", {
        "space": "physical", "addr": address, "length": length,
    })["data"])


def surface_at(frame: bytes, destination: int) -> bytes:
    offset = destination - 0x2000
    return b"".join(
        frame[offset + row * 160:offset + row * 160 + 8]
        for row in range(16)
    )


def owner_frame(client, owner: int) -> bytes:
    if owner not in (0, 1):
        raise ValueError(f"framebuffer owner id is {owner}, expected 0 or 1")
    base = (0x30 if owner == 0 else 0x2C) * 8192
    return physical(client, base, 30720)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xroar", type=Path,
                        default=Path(os.environ.get(
                            "XROAR_BIN", str(ROOT / "docs/reference/xroar/src/xroar"))))
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "build/bug013-credit-runtime.json")
    args = parser.parse_args()
    if not 0 < args.timeout <= 60:
        fail("configuration", "deadline", "timeout must be in (0, 60] seconds")

    manifest = json.loads(MANIFEST.read_text(encoding="ascii"))
    layout = json.loads(LAYOUT.read_text(encoding="ascii"))
    syms = probe.symbols(PRESENTATION_MAP)
    main_syms = probe.symbols(ROOT / "build/ladybug.map")
    cold = COLD.read_bytes()
    module = MODULE.read_bytes()
    coin = manifest["coin_overlay"]
    table_offset = int(coin["destination_table_offset"])
    stream_offset = int(coin["sparse_offset"])
    destinations = [int.from_bytes(cold[i:i + 2], "big")
                    for i in range(table_offset, table_offset + 24, 2)]
    if destinations != manifest["coin_destinations"]:
        fail("artifact identity", "authored-destination-table",
             "rebased cold table differs from the authored manifest")
    sparse = cold[stream_offset:stream_offset + int(coin["sparse_bytes"])]
    if hash_bytes(sparse) != coin["sparse_sha256"]:
        fail("artifact identity", "authored-sparse-stream", "cold stream hash differs")
    coin_surface, consumed = presentation.decode_sparse_native(sparse, 16, 8)
    if consumed != len(sparse):
        fail("artifact identity", "sparse-terminator",
             f"decoder consumed {consumed}/{len(sparse)} bytes")
    if not manifest.get("complete_profile"):
        fail("artifact identity", "complete-profile", "built manifest is not complete profile")

    evidence: dict[str, object] = {
        "schema": "ladybug-bug013-credit-runtime-v1",
        "rom_sha256": hash_bytes(ROM.read_bytes()),
        "module_sha256": hash_bytes(module),
        "cold_sha256": hash_bytes(cold),
        "coin_sparse_sha256": hash_bytes(sparse),
        "coin_destination_table_sha256": hash_bytes(cold[table_offset:table_offset + 24]),
        "zero_credit_base_frame_sha256": manifest["shared_static_frame_sha256"][HIGH_SCORE_MAP],
        "timeout_seconds": args.timeout,
        "phases": [],
        "counts": [],
    }
    monitor = probe.load_monitor()
    process, client = probe.launch_fast(monitor, args.xroar, ROM)

    def go(label: str, symbol: str) -> dict[str, object]:
        address = syms.get(symbol, main_syms.get(symbol))
        if address is None:
            fail(label, symbol, "symbol is missing from current maps")
        print(f"phase={label} marker={symbol} deadline={args.timeout:g}s", flush=True)
        ids = monitor.setup(client, [address])
        try:
            client.call("run")
            hit = client.call("wait_for_stop", {
                "timeout_ms": int(args.timeout * 1000),
            }, timeout=args.timeout + 2)
            if hit.get("reason") != "breakpoint" or hit.get("pc") != address:
                fail(label, symbol, repr(hit))
        except Exception as exc:
            fail(label, symbol, f"deadline/monitor failure: {exc}")
        finally:
            monitor.clear(client, ids)
        state = {"phase": label, "symbol": symbol, "pc": hit.get("pc"),
                 "mode": probe.read_byte(client, PRES_MODE),
                 "screen": probe.read_byte(client, PRES_SCREEN),
                 "credits": probe.read_byte(client, PRES_CREDITS),
                 "event": probe.read_byte(client, PRES_EVENT)}
        evidence["phases"].append(state)
        print(json.dumps(state), flush=True)
        return state

    def key(number: int, pressed: bool) -> None:
        client.call("inject_key", {
            "key": number, "action": "press" if pressed else "release",
        })

    def check_coin_frame(count: int, label: str) -> None:
        owner = probe.read_byte(client, FB_BACK)
        frame = owner_frame(client, owner)
        actual = [surface_at(frame, destination) for destination in destinations]
        expected = [coin_surface if index < count else bytes(128)
                    for index in range(12)]
        mismatch = [index for index, pair in enumerate(zip(actual, expected))
                    if pair[0] != pair[1]]
        record = {"count": count, "owner": owner,
                  "slot_match": not mismatch, "mismatched_slots": mismatch,
                  "frame_sha256": hash_bytes(frame)}
        evidence["counts"].append(record)
        if mismatch:
            fail(label, f"coin-slots-{count}", json.dumps(record))

    try:
        # Artifact checks prove authored source, packed ROM module, and live runtime identity.
        entry = go("cold entry identity", "presentation_flow_tick")
        if probe.read_bytes(client, 0x1900, len(module)) != module:
            fail("cold entry identity", "live-module-bytes", "live $1900 module differs")
        segment = next((item for item in layout["gmc"]["segments"]
                        if item["target"] == "presentation_module"), None)
        if segment is None:
            fail("artifact identity", "staged-module", "GMC module segment is missing")
        rom_bytes = ROM.read_bytes()
        start = int(segment["bank"]) * 16384 + int(segment["source_offset"])
        if rom_bytes[start:start + len(module)] != module:
            fail("artifact identity", "staged-module", "GMC ROM module segment differs")
        cold_address = int(manifest["cold_page"]) * 8192
        live_table = physical(client, cold_address + table_offset, 24)
        live_sparse = physical(client, cold_address + stream_offset, len(sparse))
        if live_table != cold[table_offset:table_offset + 24] or live_sparse != sparse:
            fail("artifact identity", "live-cold-records",
                 "live cold destination table or sparse stream differs from source")
        evidence["artifact_identity"] = {
            "module_live_exact": True, "module_staged_exact": True,
            "cold_table_live_exact": True, "cold_stream_live_exact": True,
            "cold_page": manifest["cold_page"], "table_offset": table_offset,
            "sparse_offset": stream_offset,
        }

        # Cold natural boot reaches attract with zero credits; a zero-credit start is ignored.
        state = go("natural cold attract", "attract_tick_ready")
        if (state["screen"], state["credits"]) != (0, 0):
            fail("natural cold attract", "screen-0-credits-0", str(state))
        key(1, True)
        go("zero-credit start edge", "pft_ready")
        key(1, False)
        state = go("zero-credit start ignored", "pft_ready")
        if (state["screen"], state["credits"]) != (0, 0):
            fail("zero-credit start ignored", "attract-credits-0", str(state))

        # Natural key 5 opens the credit screen. Held input must not create a second edge.
        key(5, True)
        edge = go("first natural key-5 credit", "pft_ready")
        if not (edge["event"] & 0x06):
            fail("first natural key-5 credit", "credit-edge", str(edge))
        rendered = go("first coin render", "load_done_dynamic_ready")
        if (rendered["screen"], rendered["credits"]) != (HIGH_SCORE_MAP, 1):
            fail("first coin render", "screen-3-credit-1", str(rendered))
        check_coin_frame(1, "first coin render")
        held = go("held key 5", "pft_ready")
        if held["credits"] != 1 or held["event"] & 0x06:
            fail("held key 5", "one-edge-only", str(held))
        key(5, False)
        released = go("key-5 release", "pft_ready")
        if released["credits"] != 1:
            fail("key-5 release", "credit-stable", str(released))

        # Simultaneous 5/6 is one scanned edge and therefore one credit.
        key(5, True)
        key(6, True)
        simultaneous = go("simultaneous 5/6 at one credit", "pft_ready")
        if (simultaneous["event"] & 0x06) != 0x06:
            fail("simultaneous 5/6 at one credit", "both-edge-bits", str(simultaneous))
        rendered = go("render simultaneous 5/6", "load_done_dynamic_ready")
        if rendered["credits"] != 2:
            fail("render simultaneous 5/6", "single-credit-increment", str(rendered))
        check_coin_frame(2, "render simultaneous 5/6")
        evidence["simultaneous_credit_observation"] = {
            "event_mask": simultaneous["event"],
            "credits_before": simultaneous["credits"],
            "credits_after": rendered["credits"],
            "increment": rendered["credits"] - simultaneous["credits"],
            "status": "open BUG-043: simultaneous 5+6 produced one increment; two-edge accounting remains unverified",
        }
        key(5, False)
        key(6, False)
        released = go("release simultaneous 5/6", "pft_ready")
        if released["credits"] != 2:
            fail("release simultaneous 5/6", "credit-stable", str(released))

        # Alternating natural 5/6 edges produce each authored count from 2 through 12.
        for count in range(3, 13):
            number = 6 if count % 2 == 0 else 5
            key(number, True)
            edge = go(f"natural credit {count} edge", "pft_ready")
            if not (edge["event"] & 0x06):
                fail(f"natural credit {count} edge", "credit-edge", str(edge))
            rendered = go(f"render {count} coins", "load_done_dynamic_ready")
            if (rendered["screen"], rendered["credits"]) != (HIGH_SCORE_MAP, count):
                fail(f"render {count} coins", f"screen-3-credit-{count}", str(rendered))
            check_coin_frame(count, f"render {count} coins")
            key(number, False)
            released = go(f"release key {number} at {count}", "pft_ready")
            if released["credits"] != count:
                fail(f"release key {number} at {count}", "credit-stable", str(released))

        # A distinct thirteenth natural key edge preserves twelve slots.
        key(5, True)
        saturated = go("thirteenth credit edge", "pft_ready")
        if not (saturated["event"] & 0x06) or saturated["credits"] != 12:
            fail("thirteenth credit edge", "saturated-12", str(saturated))
        rendered = go("thirteenth-edge saturation", "load_done_dynamic_ready")
        if rendered["credits"] != 12:
            fail("thirteenth-edge saturation", "credit-remains-12", str(rendered))
        check_coin_frame(12, "thirteenth-edge saturation")
        key(5, False)
        released = go("release thirteenth edge", "pft_ready")
        if released["credits"] != 12:
            fail("release thirteenth edge", "credit-stable", str(released))

        # Prove the former 600-frame timeout no longer returns from the credit screen.
        frame_start = int.from_bytes(physical(client, FRAME_COUNTER, 2), "big")
        timer_start = probe.read_word(client, 0xB0)
        hold_deadline = time.monotonic() + args.timeout
        client.call("run")
        frame_end = frame_start
        while time.monotonic() < hold_deadline:
            frame_end = int.from_bytes(physical(client, FRAME_COUNTER, 2), "big")
            if ((frame_end - frame_start) & 0xFFFF) >= 601:
                break
            time.sleep(0.01)
        else:
            fail("credit hold beyond 600 frames", "frame-counter-delta-601",
                 f"timeout after {args.timeout:g}s; delta={(frame_end-frame_start)&0xFFFF}")
        client.call("pause")
        hold = {"phase": "credit hold beyond 600 frames",
                "marker": "frame-counter-delta-601",
                "frames": (frame_end - frame_start) & 0xFFFF,
                "mode": probe.read_byte(client, PRES_MODE),
                "screen": probe.read_byte(client, PRES_SCREEN),
                "credits": probe.read_byte(client, PRES_CREDITS),
                "timer_before": timer_start,
                "timer_after": probe.read_word(client, 0xB0)}
        evidence["hold"] = hold
        if (hold["mode"], hold["screen"], hold["credits"]) != (
                MODE_CREDIT, HIGH_SCORE_MAP, 12):
            fail("credit hold beyond 600 frames", "credit-screen-still-active", str(hold))
        if hold["timer_before"] != hold["timer_after"]:
            fail("credit hold beyond 600 frames", "timer-unchanged", str(hold))

        # Player one consumes one available credit and reaches the game renderer.
        key(1, True)
        start_edge = go("nonzero player-one start edge", "pft_ready")
        if not (start_edge["event"] & 1):
            fail("nonzero player-one start edge", "start-edge", str(start_edge))
        started = go("player-one level-start selection", "start_screen_done")
        if (started["screen"], started["credits"]) != (2, 11):
            fail("player-one level-start selection", "screen-2-credit-11", str(started))
        key(1, False)
        loaded = go("player-one level-start publication", "load_done_dynamic_ready")
        if (loaded["screen"], loaded["credits"]) != (2, 11):
            fail("player-one level-start publication", "screen-2-credit-11", str(loaded))
        game = go("player-one gameplay handoff", "main_render")
        if game["mode"] != 0 or game["credits"] != 11:
            fail("player-one gameplay handoff", "mode-0-credit-11", str(game))
        evidence["start_handoff"] = game
        owners = sorted({int(record["owner"]) for record in evidence["counts"]})
        evidence["framebuffer_owners"] = {
            "coin_render_back_owner_ids": owners,
            "both_owner_ids_observed": owners == [0, 1],
            "reversed_initial_owner_order_tested": False,
        }
        evidence["open_acceptance_gaps"] = [
            "simultaneous 5+6 currently produces one increment; BUG-043 owns two-edge accounting",
            "first key-6 credit from another natural attract phase was not exercised",
            "reversed initial framebuffer owner order was not exercised",
            "coin worklist cycle maxima were not measured",
            "full verify-gmc did not complete because FEAT-007 static verification stalled",
        ]
        evidence["status"] = "focused-checks-pass-with-open-acceptance"
    except BaseException as exc:
        evidence["passed"] = False
        evidence["error"] = repr(exc)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="ascii")
        raise
    finally:
        client.close()
        probe.stop(process)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="ascii")
    print(f"BUG-013 focused runtime checks passed with open gaps: static zero-credit base, "
          f"runtime counts 1-12; "
          f"single-increment simultaneous 5+6 flagged to BUG-043; "
          f"thirteenth-edge saturation; 601-frame hold; player-one handoff; "
          f"evidence={args.output}", flush=True)


if __name__ == "__main__":
    main()
