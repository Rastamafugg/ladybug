#!/usr/bin/env python3
"""Count live enemy/timer/release/reset entries on the pinned BUG-087 candidate."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[5]
EVIDENCE = Path(__file__).resolve().parent
ADAPTER_PATH = EVIDENCE / "bug087_ready_adapter.py"
AUTH_PATH = EVIDENCE / "bug087-spawner-cadence-authorization-20261007.json"
IDENTITY_PATH = EVIDENCE / "current-root-candidate-ad1-keyboard-identity-163d-20261006.json"
EXPECTED_ROM_SHA256 = "7caa58c1ff1ef84b0b107b4b5cc46850244de1f2729dbc60f3af1f46abfac32e"
EXPECTED_PHASE = "spawner-timer-reset-cadence"
PHASE_SECONDS = 45
PAGE_BYTES = 0x2000
LOW_PAGE = 0x38


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_adapter():
    spec = importlib.util.spec_from_file_location("bug087_ready_adapter", ADAPTER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load the existing BUG-087 runtime adapter")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_pinned_map(adapter: Any, identity: dict[str, Any], role: str) -> dict[str, int]:
    entry = identity["maps"][role]
    path = Path(identity["build_dir"]) / entry["path"]
    raw = path.read_bytes()
    if sha(raw) != entry["sha256"]:
        raise ValueError(f"{role} map differs from the byte-pinned identity")
    text = raw.decode("utf-8")
    symbols = {name: int(value, 16) for name, value in adapter.SYMBOL_RE.findall(text)}
    return symbols


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--identity", type=Path, default=IDENTITY_PATH)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--deadline-seconds", type=int, default=PHASE_SECONDS)
    parser.add_argument("--authorization", type=Path, default=AUTH_PATH)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.deadline_seconds != PHASE_SECONDS:
        raise ValueError("the diagnostic phase deadline is fixed at 45 seconds")

    adapter = load_adapter()
    identity_path = args.identity.resolve(strict=True)
    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    identity["build_dir"] = str(args.build_dir.resolve(strict=True))
    adapter.verify_identity(identity)
    if identity.get("side") != "candidate" or identity.get("full_rom_sha256") != EXPECTED_ROM_SHA256:
        raise ValueError("identity is not the authorized current candidate ROM")
    auth_path = args.authorization.resolve(strict=True)
    auth = json.loads(auth_path.read_text(encoding="utf-8"))
    if (auth.get("runtime_authorized") is not True or
            auth.get("parent_review_status") != "parent-reviewed-and-approved" or
            auth.get("phase") != EXPECTED_PHASE or
            auth.get("phase_deadline_seconds") != PHASE_SECONDS or
            auth.get("adapter_sha256") != sha(ADAPTER_PATH.read_bytes()) or
            auth.get("probe_sha256") != sha(Path(__file__).read_bytes()) or
            auth.get("scenario_plan_sha256") != sha((EVIDENCE / "scenario-plan.json").read_bytes()) or
            auth.get("identity_sha256") != sha(identity_path.read_bytes())):
        raise ValueError("diagnostic authorization does not match current artifacts")

    deadline = time.monotonic() + args.deadline_seconds
    started = time.monotonic()
    probe = adapter.RuntimeProbe(args.host, args.port, deadline)
    receipt: dict[str, Any] = {
        "schema": "bug087-spawner-cadence-diagnostic-20261007-v1",
        "ticket": "BUG-087",
        "phase": EXPECTED_PHASE,
        "phase_deadline_seconds": args.deadline_seconds,
        "success_marker": "within 45 seconds, observe at least 300 enemy_tick_impl and 300 perimeter_timer_tick entries, with physical/logical direct-page samples equal; count release/reset markers separately",
        "timeout_meaning": "fewer than 300 paired entry classes or a missing marker means incomplete diagnostic evidence; it does not prove route unreachability or a speed result",
        "direct_game_memory_writes": False,
        "input_injected": False,
        "rom_sha256": identity["full_rom_sha256"],
        "identity_sha256": sha(identity_path.read_bytes()),
        "adapter_sha256": sha(ADAPTER_PATH.read_bytes()),
        "probe_sha256": sha(Path(__file__).read_bytes()),
        "scenario_plan_sha256": sha((EVIDENCE / "scenario-plan.json").read_bytes()),
        "authorization_sha256": sha(auth_path.read_bytes()),
        "status": "running",
        "entry_counts": {"enemy_tick_impl": 0, "perimeter_timer_tick": 0,
                          "enemy_release_impl": 0, "reset_enemy_state": 0},
        "event_transitions": [],
        "periodic_timer_samples": [],
    }
    try:
        run_state = probe.call("get_run_state", None, 1.0)
        if run_state.get("state") != "halted" or run_state.get("last_stop_reason") != "breakpoint":
            raise RuntimeError(f"candidate is not halted at the retained enemy callback: {run_state}")
        registers = probe.call("read_registers", None, 1.0)
        main = read_pinned_map(adapter, identity, "main")
        enemy = read_pinned_map(adapter, identity, "enemy")
        expected_tick = enemy["enemy_tick_impl"]
        bp_id = run_state.get("last_stop_bp_id")
        if registers.get("pc") != expected_tick or not isinstance(bp_id, int):
            raise RuntimeError("initial stop is not the verified enemy_tick_impl entry")
        if registers.get("dp") != 0:
            raise RuntimeError(f"initial enemy callback DP differs from zero: {registers.get('dp')!r}")
        probe.installed[bp_id] = expected_tick
        proof = adapter._verify_runtime_images(probe, identity, verify_staging=False,
                                               require_mapping=True)
        targets = {"enemy_tick_impl": expected_tick,
                   "perimeter_timer_tick": main["perimeter_timer_tick"],
                   "enemy_release_impl": enemy["enemy_release_impl"],
                   "reset_enemy_state": main["reset_enemy_state"]}
        breakpoint_ids = {bp_id: "enemy_tick_impl"}
        for name in ("perimeter_timer_tick", "enemy_release_impl", "reset_enemy_state"):
            ident = probe.set_breakpoint(targets[name])
            breakpoint_ids[ident] = name
        snapshot = adapter._low_snapshot(probe)
        low_page = adapter._phys_read(probe, LOW_PAGE * PAGE_BYTES + 0x4A, 0x10)
        logical = adapter._logical_read(probe, 0x004A, 0x10)
        par0 = adapter._logical_read(probe, 0xFFA0)[0] & 0x3F
        if par0 != LOW_PAGE or low_page != logical:
            raise RuntimeError("physical direct-page snapshot differs from logical PAR0 read")
        receipt.update({"runtime_image_proof": proof, "initial_state": snapshot,
                        "initial_direct_page_hex": low_page.hex(), "initial_PAR0": par0,
                        "initial_DP": registers.get("dp"),
                        "breakpoints": {name: {"pc": f"${address:04X}",
                                                "id": next(k for k, v in breakpoint_ids.items()
                                                           if v == name)}
                                        for name, address in targets.items()}})

        previous = None
        timer_count = 0
        while time.monotonic() < deadline - 3.0:
            marker = probe.run_until_marker(wait_cap_seconds=42.0)
            name = breakpoint_ids.get(marker.get("bp_id"))
            if name is None or marker.get("pc") != targets[name]:
                raise RuntimeError(f"unexpected marker during cadence observation: {marker}")
            receipt["entry_counts"][name] += 1
            if name == "perimeter_timer_tick":
                timer_count += 1
                live_registers = probe.call("read_registers", None, 1.0)
                if live_registers.get("dp") != 0:
                    raise RuntimeError(f"timer entry DP differs from zero: {live_registers.get('dp')!r}")
                raw = adapter._phys_read(probe, LOW_PAGE * PAGE_BYTES + 0x4A, 0x10)
                state = adapter._low_snapshot(probe)
                if timer_count == 1 or timer_count % 128 == 0:
                    logical_state = adapter._logical_read(probe, 0x004A, 0x10)
                    par0_now = adapter._logical_read(probe, 0xFFA0)[0] & 0x3F
                    if (par0_now != LOW_PAGE or logical_state != raw or
                            live_registers.get("dp") != 0):
                        raise RuntimeError("sampled physical/logical direct-page state diverged")
                    receipt["periodic_timer_samples"].append({
                        "timer_entry": timer_count, "state": state,
                        "direct_page_hex": raw.hex(), "PAR0": par0_now,
                        "DP": live_registers.get("dp")})
                if previous is not None:
                    if state["death_state"] != previous["death_state"]:
                        receipt["event_transitions"].append({"at_timer_entry": timer_count,
                            "kind": "death-state-change", "from": previous["death_state"],
                            "to": state["death_state"], "box_index": state["box_index"],
                            "enemy_active": state["enemy_active"],
                            "enemy_released": state["enemy_released"]})
                    if state["box_index"] < previous["box_index"]:
                        receipt["event_transitions"].append({"at_timer_entry": timer_count,
                            "kind": "box-index-rewind-or-wrap",
                            "from": previous["box_index"], "to": state["box_index"],
                            "death_state": state["death_state"],
                            "enemy_active": state["enemy_active"],
                            "enemy_released": state["enemy_released"]})
                    if (state["enemy_active"], state["enemy_released"]) != (
                            previous["enemy_active"], previous["enemy_released"]):
                        receipt["event_transitions"].append({"at_timer_entry": timer_count,
                            "kind": "enemy-population-change",
                            "active_from": previous["enemy_active"],
                            "active_to": state["enemy_active"],
                            "released_from": previous["enemy_released"],
                            "released_to": state["enemy_released"],
                            "box_index": state["box_index"],
                            "death_state": state["death_state"]})
                previous = state
            elif name in ("enemy_release_impl", "reset_enemy_state"):
                live_registers = probe.call("read_registers", None, 1.0)
                if live_registers.get("dp") != 0:
                    raise RuntimeError(f"{name} entry DP differs from zero: {live_registers.get('dp')!r}")
                state = adapter._low_snapshot(probe)
                records = adapter._enemy_records(probe)
                receipt["event_transitions"].append({"at_timer_entry": timer_count,
                    "kind": name, "state": state, "enemy_records": records})

        receipt["status"] = ("complete-bounded-observation"
            if receipt["entry_counts"]["enemy_tick_impl"] >= 300 and
               receipt["entry_counts"]["perimeter_timer_tick"] >= 300
            else "incomplete-insufficient-markers")
        receipt["elapsed_seconds"] = round(time.monotonic() - started, 6)
        receipt["phase_deadline_met"] = receipt["elapsed_seconds"] <= args.deadline_seconds
        receipt["final_state"] = adapter._low_snapshot(probe)
        final_raw = adapter._phys_read(probe, LOW_PAGE * PAGE_BYTES + 0x4A, 0x10)
        final_logical = adapter._logical_read(probe, 0x004A, 0x10)
        receipt["final_direct_page_hex"] = final_raw.hex()
        receipt["final_PAR0"] = adapter._logical_read(probe, 0xFFA0)[0] & 0x3F
        receipt["final_DP"] = probe.call("read_registers", None, 1.0).get("dp")
        receipt["final_physical_logical_match"] = final_raw == final_logical
        if receipt["final_PAR0"] != LOW_PAGE or receipt["final_DP"] != 0:
            raise RuntimeError("final diagnostic mapping or direct-page register differs")
        receipt["monitor_audit"] = probe.audit()
        receipt["timeout_meaning"] = "phase ended at its 45-second observation boundary; missing transitions remain inconclusive"
    except Exception as exc:
        receipt.update({"status": "fail-diagnostic", "error": f"{type(exc).__name__}: {exc}",
                        "elapsed_seconds": round(time.monotonic() - started, 6),
                        "monitor_audit": probe.audit()})
        raise
    finally:
        probe.close()
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))
    return 0 if receipt.get("status") == "complete-bounded-observation" else 2


if __name__ == "__main__":
    raise SystemExit(main())
