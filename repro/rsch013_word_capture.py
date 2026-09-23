#!/usr/bin/env python3
"""Verify BUG-046 word-mask publication, rewards, and new-game reset."""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import verify_bug011_runtime as runtime
import verify_bug009_monitor_input as monitor

BUILD = ROOT / "build"
OUT = BUILD / "bug046-word-capture.json"
DEADLINE = 40
PROBE_MARKER_DEADLINE = 10
PROBE_TOTAL_DEADLINE = 30
PROBE_STACK = 0x1FFC
PROBE_RETURN = 0x1800
WORD_MASKS = (0x49, 0x15)  # SPECIAL bits 0/3/6; EXTRA bits 0/2/4.
SPECIAL_ROW, EXTRA_ROW = 1, 4


def changed_pixels(before: bytes, after: bytes) -> int:
    if len(before) != len(after):
        raise ValueError("pixel comparison received different tile sizes")
    return sum(
        ((left >> 4) != (right >> 4)) + ((left & 0x0F) != (right & 0x0F))
        for left, right in zip(before, after)
    )


def main() -> int:
    reward_probe = "--reward-probe" in sys.argv
    rom = BUILD / "ladybug.rom"
    runtime_rom_path = BUILD / "ladybug-runtime.rom"
    presentation_path = BUILD / "ladybug-presentation-runtime.bin"
    evidence: dict[str, object] = {
        "rom_sha256": hashlib.sha256(rom.read_bytes()).hexdigest(),
        "runtime_rom_sha256": hashlib.sha256(runtime_rom_path.read_bytes()).hexdigest(),
        "presentation_sha256": hashlib.sha256(presentation_path.read_bytes()).hexdigest(),
        "deadline_seconds_per_phase": DEADLINE,
        "timeout_meaning": "named phase marker not reached",
        "mode": "corrected-reward-probe" if reward_probe else "full-focused-verification",
        "phases": [],
    }
    runtime_rom = runtime_rom_path.read_bytes()
    presentation = presentation_path.read_bytes()
    xroar = Path(os.environ.get("XROAR_BIN", ROOT / "docs/reference/xroar/src/xroar"))
    if not xroar.is_file():
        raise RuntimeError(f"patched XRoar binary not found: {xroar}; set XROAR_BIN")
    evidence["xroar_binary"] = str(xroar)
    process, client = runtime.launch_fast(monitor, xroar, rom)
    syms = runtime.symbols(BUILD / "ladybug-presentation-runtime.map")
    main_syms = runtime.symbols(BUILD / "ladybug.map")

    def reach(name: str, table: dict[str, int] = syms) -> None:
        address = table[name]
        ids = monitor.setup(client, [address])
        print(
            f"phase={name} marker={address:04x} deadline={DEADLINE}s; "
            "timeout=named-marker-not-reached",
            flush=True,
        )
        try:
            hit = client.run_to_breakpoint(DEADLINE)
            if hit.get("pc") != address:
                raise RuntimeError(f"{name}: unexpected marker result {hit}")
        finally:
            monitor.clear(client, ids)
        evidence["phases"].append(name)

    def live_main_identity(name: str, end_name: str) -> bool:
        start, end = main_syms[name], main_syms[end_name]
        if not (0xC000 <= start < end <= 0x10000):
            raise RuntimeError(f"invalid resident bounds for {name}: {start:04x}-{end:04x}")
        expected = runtime_rom[start - 0xC000:end - 0xC000]
        live = runtime.read_bytes(client, start, len(expected))
        if live != expected:
            raise RuntimeError(f"live {name} bytes differ from the built resident artifact")
        return True

    def word_tiles(owner: int) -> dict[str, bytes]:
        frame = runtime.read_owner(client, owner)
        tiles: dict[str, bytes] = {}
        for row, count in ((SPECIAL_ROW, 7), (EXTRA_ROW, 5)):
            for col in range(1, count + 1):
                address = runtime.VISIBLE_START + row * 8 * 160 + col * 4
                tiles[f"{col},{row}"] = runtime.frame_tile(frame, address)
        return tiles

    def tile_hashes(tiles: dict[str, bytes]) -> dict[str, str]:
        return {key: hashlib.sha256(value).hexdigest()[:16] for key, value in tiles.items()}

    def probe_state() -> dict[str, object]:
        return {
            "registers": client.call("read_registers"),
            "return_word": runtime.read_bytes(client, PROBE_STACK, 2).hex(),
            "special_bits": runtime.read_byte(client, 0x3C),
            "extra_bits": runtime.read_byte(client, 0x3D),
            "score_bcd": runtime.read_bytes(client, 0x1D, 3).hex(),
            "high_bcd": runtime.read_bytes(client, 0x20, 3).hex(),
            "stage": runtime.read_byte(client, 0x24),
            "stage_pending": runtime.read_byte(client, 0x26),
            "lives": runtime.read_byte(client, 0x23),
        }

    def run_probe_markers(markers: list[tuple[str, int]], total_deadline: float) -> None:
        if total_deadline <= time.monotonic():
            raise TimeoutError(f"total {PROBE_TOTAL_DEADLINE}s reward-probe deadline exhausted")
        ids = monitor.setup(client, [address for _, address in markers])
        remaining_ids = list(ids)
        try:
            for (label, address), bp_id in zip(markers, ids):
                remaining = total_deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(f"{label}: total {PROBE_TOTAL_DEADLINE}s reward-probe deadline exhausted")
                timeout = min(PROBE_MARKER_DEADLINE, remaining)
                started = time.monotonic()
                marker: dict[str, object] = {
                    "label": label,
                    "address": f"{address:04x}",
                    "deadline_seconds": round(timeout, 3),
                }
                print(
                    f"phase=reward-probe marker={label}:{address:04x} "
                    f"deadline={timeout:.1f}s; timeout=named-marker-not-observed",
                    flush=True,
                )
                try:
                    client.call("run")
                    hit = client.call("wait_for_stop", {"timeout_ms": int(timeout * 1000)}, timeout=timeout + 1)
                    marker["elapsed_seconds"] = round(time.monotonic() - started, 3)
                    marker["stop"] = hit
                    marker["success"] = hit.get("reason") == "breakpoint" and hit.get("pc") == address
                    if not marker["success"]:
                        client.call("pause")
                        client.call("wait_for_stop", {"timeout_ms": 2000}, timeout=3)
                        marker["timeout_meaning"] = "named marker was not observed in its bound"
                        marker["snapshot"] = probe_state()
                        evidence.setdefault("probe_markers", []).append(marker)
                        raise TimeoutError(f"{label}: marker result {hit}")
                    evidence.setdefault("probe_markers", []).append(marker)
                    monitor.clear(client, [bp_id])
                    remaining_ids.remove(bp_id)
                except Exception as exc:
                    if not marker.get("success") and "snapshot" not in marker:
                        try:
                            client.call("pause")
                            client.call("wait_for_stop", {"timeout_ms": 2000}, timeout=3)
                            marker["snapshot"] = probe_state()
                        except Exception as snapshot_exc:
                            marker["snapshot_error"] = f"{type(snapshot_exc).__name__}: {snapshot_exc}"
                        marker["error"] = f"{type(exc).__name__}: {exc}"
                        marker["timeout_meaning"] = "named marker was not observed in its bound"
                        if marker not in evidence.setdefault("probe_markers", []):
                            evidence["probe_markers"].append(marker)
                    raise
        finally:
            monitor.clear(client, remaining_ids)

    def call_main(name: str, markers: list[tuple[str, int]] | None = None,
                  total_deadline: float | None = None) -> None:
        address = main_syms[name]
        client.call("write_memory", {"addr": PROBE_RETURN, "data": "20fe"})
        runtime.write_word(client, PROBE_STACK, PROBE_RETURN)
        client.call("write_registers", {
            "pc": address, "s": PROBE_STACK, "dp": 0, "cc": 0x50,
        })
        regs = client.call("read_registers")
        if (regs.get("pc"), regs.get("s"), regs.get("dp"), regs.get("cc")) != (
                address, PROBE_STACK, 0, 0x50):
            raise RuntimeError(f"{name}: forced-call register setup mismatch: {regs}")
        if runtime.read_bytes(client, PROBE_STACK, 2) != bytes((PROBE_RETURN >> 8, PROBE_RETURN & 0xFF)):
            raise RuntimeError(f"{name}: fixed return word mismatch")
        marker_list = markers or [(f"{name}-return", PROBE_RETURN)]
        deadline_at = total_deadline or (time.monotonic() + PROBE_TOTAL_DEADLINE)
        run_probe_markers(marker_list, deadline_at)
        evidence["phases"].append(name)

    try:
        reach("presentation_flow_tick")
        evidence["identity"] = {
            "presentation": runtime.read_bytes(client, 0x1900, len(presentation)) == presentation,
            "init_game_state": live_main_identity("init_game_state", "next_stage"),
        }
        if not evidence["identity"]["presentation"]:
            raise RuntimeError("presentation module identity mismatch")
        reach("demo_run")

        # Plant stale partial state before a real credit/start sequence.
        runtime.write_byte(client, 0x3C, WORD_MASKS[0])
        runtime.write_byte(client, 0x3D, WORD_MASKS[1])
        client.call("inject_key", {"key": 5, "action": "press"})
        reach("credit_tick")
        client.call("inject_key", {"key": 5, "action": "release"})
        client.call("inject_key", {"key": 1, "action": "press"})
        reach("normal_game")
        client.call("inject_key", {"key": 1, "action": "release"})
        reset = {
            "stage": runtime.read_byte(client, 0x24),
            "masks": runtime.read_bytes(client, 0x3C, 2).hex(),
            "score_bcd": runtime.read_bytes(client, 0x1D, 3).hex(),
            "lives": runtime.read_byte(client, 0x23),
        }
        if reset != {"stage": 1, "masks": "0000", "score_bcd": "000000", "lives": 3}:
            raise RuntimeError(f"new-game reset mismatch: {reset}")
        live_main_identity("draw_word_progress_hud", "draw_hud")
        evidence["cold_new_game_reset"] = reset

        for _ in range(64):
            if runtime.read_byte(client, 0xA0) == 0:
                break
            reach("normal_game")
        else:
            raise RuntimeError("entry animation did not finish")

        runtime.write_byte(client, 0x3C, WORD_MASKS[0])
        runtime.write_byte(client, 0x3D, WORD_MASKS[1])
        baseline = {owner: word_tiles(owner) for owner in (0, 1)}
        evidence["part1_seeded"] = {
            "stage": runtime.read_byte(client, 0x24),
            "masks": runtime.read_bytes(client, 0x3C, 2).hex(),
            "front": runtime.read_byte(client, runtime.FB_FRONT),
            "owners": {str(owner): tile_hashes(tiles) for owner, tiles in baseline.items()},
        }

        # Preserve the existing credited Part 1-to-2 final-dot route.
        runtime.write_byte(client, 0x25, 1)
        runtime.write_byte(client, 0x33, 0)
        client.call("inject_key", {"key": 0x2B, "action": "press"})
        for _ in range(64):
            reach("normal_stage")
            if runtime.read_byte(client, 0x26):
                break
        else:
            raise RuntimeError("final-dot stage request missing")
        client.call("inject_key", {"key": 0x2B, "action": "release"})
        reach("level_tick")
        if runtime.read_byte(client, 0x91):
            reach("level_tick")
        reach("normal_game")
        for _ in range(3):
            reach("normal_game")

        masks = runtime.read_bytes(client, 0x3C, 2)
        if masks != bytes(WORD_MASKS):
            raise RuntimeError(f"stage handoff changed word masks: {masks.hex()}")
        if runtime.read_byte(client, 0x24) != 2:
            raise RuntimeError("natural Part 1-to-2 handoff did not advance to stage 2")
        after = {owner: word_tiles(owner) for owner in (0, 1)}
        pixel_results: dict[str, object] = {}
        selected_special = {col for col in range(1, 8) if WORD_MASKS[0] & (1 << (col - 1))}
        selected_extra = {col for col in range(1, 6) if WORD_MASKS[1] & (1 << (col - 1))}
        for owner in (0, 1):
            checks: dict[str, dict[str, int | bool]] = {}
            for row, count, selected in (
                (SPECIAL_ROW, 7, selected_special),
                (EXTRA_ROW, 5, selected_extra),
            ):
                for col in range(1, count + 1):
                    key = f"{col},{row}"
                    changed = changed_pixels(baseline[owner][key], after[owner][key])
                    expect_change = col in selected
                    checks[key] = {"changed_pixels": changed, "selected": expect_change}
                    if (expect_change and changed == 0) or (not expect_change and changed != 0):
                        raise RuntimeError(
                            f"owner {owner} tile {key}: expected selected={expect_change}, "
                            f"observed {changed} changed pixels"
                        )
            pixel_results[str(owner)] = {
                "front_at_capture": runtime.read_byte(client, runtime.FB_FRONT),
                "tiles": tile_hashes(after[owner]),
                "pixel_checks": checks,
            }
        evidence["part2_gameplay_published"] = {
            "stage": runtime.read_byte(client, 0x24),
            "masks": masks.hex(),
            "owners": pixel_results,
            "success_marker": "first gameplay publication after Part 2 stage render",
        }

        # Complete SPECIAL through its state routine and verify its existing score and stage request.
        live_main_identity("apply_letter_pickup", "add_special_score")
        live_main_identity("add_special_score", "draw_multiplier_hud")
        runtime.write_byte(client, 0x3C, 0x3F)
        runtime.write_byte(client, 0x3D, 0)
        runtime.write_byte(client, 0x2F, 1)  # COLOR_RED
        runtime.write_byte(client, 0x39, 6)  # missing SPECIAL bit $40
        runtime.write_byte(client, 0x26, 0)
        client.call("write_memory", {"addr": 0x1D, "data": "000000"})
        special_probe_deadline = time.monotonic() + PROBE_TOTAL_DEADLINE
        if reward_probe:
            call_main("apply_letter_pickup", [
                ("add_special_score", main_syms["add_special_score"]),
                ("alp_special_draw", main_syms["alp_special_draw"]),
                ("apply_letter_pickup-return", PROBE_RETURN),
            ], special_probe_deadline)
        else:
            call_main("apply_letter_pickup")
        special = {
            "stage": runtime.read_byte(client, 0x24),
            "stage_pending": runtime.read_byte(client, 0x26),
            "special_bits": runtime.read_byte(client, 0x3C),
            "score_bcd": runtime.read_bytes(client, 0x1D, 3).hex(),
            "high_bcd": runtime.read_bytes(client, 0x20, 3).hex(),
        }
        if special != {
            "stage": 2, "stage_pending": 1, "special_bits": 0,
            "score_bcd": "010000", "high_bcd": "010000",
        }:
            raise RuntimeError(f"SPECIAL completion mismatch: {special}")
        live_main_identity("next_stage", "add_dot_score")
        if reward_probe:
            call_main("next_stage", [("next_stage-return", PROBE_RETURN)], special_probe_deadline)
        else:
            call_main("next_stage")
        if (runtime.read_byte(client, 0x24), runtime.read_byte(client, 0x26),
                runtime.read_byte(client, 0x3C), runtime.read_byte(client, 0x3D)) != (3, 0, 0, 0):
            raise RuntimeError("SPECIAL stage advance changed cleared word masks or stage state")
        evidence["special_reward"] = dict(
            special, stage_after_request=3, mask_after_stage=0,
        )

        # Complete EXTRA and retain its existing one-life reward and stage request.
        runtime.write_byte(client, 0x3C, 0)
        runtime.write_byte(client, 0x3D, 0x0F)
        runtime.write_byte(client, 0x2F, 2)  # COLOR_YELLOW
        runtime.write_byte(client, 0x39, 2)  # missing EXTRA bit $10
        runtime.write_byte(client, 0x23, 3)
        runtime.write_byte(client, 0x26, 0)
        live_main_identity("apply_letter_pickup", "add_special_score")
        live_main_identity("add_special_score", "draw_multiplier_hud")
        if reward_probe:
            call_main("apply_letter_pickup", [
                ("alp_done", main_syms["alp_done"]),
                ("extra_letter-return", PROBE_RETURN),
            ], special_probe_deadline)
        else:
            call_main("apply_letter_pickup")
        extra = {
            "stage": runtime.read_byte(client, 0x24),
            "stage_pending": runtime.read_byte(client, 0x26),
            "extra_bits": runtime.read_byte(client, 0x3D),
            "lives": runtime.read_byte(client, 0x23),
            "score_bcd": runtime.read_bytes(client, 0x1D, 3).hex(),
        }
        if extra != {
            "stage": 3, "stage_pending": 1, "extra_bits": 0,
            "lives": 4, "score_bcd": "010000",
        }:
            raise RuntimeError(f"EXTRA completion mismatch: {extra}")
        live_main_identity("next_stage", "add_dot_score")
        if reward_probe:
            call_main("next_stage", [("extra-next_stage-return", PROBE_RETURN)], special_probe_deadline)
        else:
            call_main("next_stage")
        if (runtime.read_byte(client, 0x24), runtime.read_byte(client, 0x26),
                runtime.read_byte(client, 0x3C), runtime.read_byte(client, 0x3D)) != (4, 0, 0, 0):
            raise RuntimeError("EXTRA stage advance changed cleared word masks or stage state")
        if runtime.read_byte(client, 0x23) != 4:
            raise RuntimeError("EXTRA life reward did not persist through stage advance")
        evidence["extra_reward"] = dict(
            extra, stage_after_request=4, lives_after_stage=4,
        )
        evidence["success_marker"] = "reset, both-owner handoff, and both completed-word rewards passed"

        if reward_probe:
            if time.monotonic() > special_probe_deadline:
                raise TimeoutError("SPECIAL/EXTRA rewards and stage transitions exceeded the 30-second probe bound")
            evidence["reward_probe_status"] = "pass"
            evidence["reward_probe_elapsed_seconds"] = round(PROBE_TOTAL_DEADLINE - (special_probe_deadline - time.monotonic()), 3)
            evidence["success_marker"] = "SPECIAL and EXTRA rewards and stage transitions passed"
    except Exception as exc:
        evidence["failure"] = f"{type(exc).__name__}: {exc}"
    finally:
        client.close()
        monitor.stop(process)
        OUT.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence, indent=2))
    if "failure" in evidence:
        print(f"BUG-046 verification failed; evidence={OUT}", file=sys.stderr)
        return 1
    print(f"BUG-046 verification passed; evidence={OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
