#!/usr/bin/env python3
"""Capture and execute the bounded BUG-087 runtime actions.

Preparation commands are offline. The separate live command attaches to an
already running XRoar monitor only after a parent dispatch receipt pins both
current builds, the integrated BUG-086 receipt, this adapter, scenario plan,
fixture, and one 45-second phase. It never launches an emulator.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import socket
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


def project_root(path: Path) -> Path:
    for parent in (path.resolve(), *path.resolve().parents):
        if (parent / "wiki/index.html").is_file() and (parent / "scripts/verify_bug009_monitor_input.py").is_file():
            return parent
    raise RuntimeError(f"cannot find project root above {path}")


ROOT = project_root(Path(__file__))
EVIDENCE = ROOT / "wiki/internal/tickets/evidence/rsch014-ready-087"
PLAN = EVIDENCE / "scenario-plan.json"
SYMBOL_RE = re.compile(r"^Symbol: (\w+) .* = ([0-9A-Fa-f]+)$", re.MULTILINE)
MAPS = {
    "main": "ladybug.map",
    "enemy": "ladybug-enemy-runtime.map",
    "rate": "ladybug-rate-helper.map",
    "e2": "ladybug-enemy-helper-page34.map",
    "active": "ladybug-adaptive-active.map",
    "presentation": "ladybug-presentation-runtime.map",
}
ARTIFACTS = (
    "ladybug.rom",
    "ladybug-runtime.rom",
    "ladybug-enemy-runtime.rom",
    "ladybug-enemy-runtime.lst",
    "ladybug-rate-helper.bin",
    "ladybug-enemy-helper-page34.bin",
    "ladybug-adaptive-banked.bin",
    "ladybug-adaptive-active.bin",
    "ladybug-adaptive-active.s",
    "ladybug-presentation-runtime.bin",
    "source-build-receipt.json",
)
REQUIRED_SYMBOLS = {
    "main": ("mainloop", "ad_dispatch_work", "init_enemy", "enemy_tick", "next_stage",
             "ENEMY_MODULE_INIT", "INITIAL_ENTRY_STATE", "STAGE", "ENEMY_TABLE",
             "ENEMY_ACTIVE", "DEATH_STATE", "FREEZE_TIMER", "ENEMY_MOVE",
             "DOTS_LEFT", "BONUS_LEFT", "STAGE_PENDING"),
    "enemy": ("enemy_tick_impl", "enemy_init_impl", "ecd_blocked", "ecd_choose",
              "ENEMY_TABLE", "ENEMY_ACTIVE", "DEATH_STATE",
              "FREEZE_TIMER", "ENEMY_MOVE"),
    "rate": ("rate_reset", "rate_tick", "rate_select", "rate_enemy_init_shim", "rt_freeze_gate",
             "rt_accumulate", "RATE_TIMER", "RATE_BUCKET", "RATE_FRAC",
             "RATE_ADDEND", "RATE_PHASE", "FREEZE_TIMER", "STAGE"),
    "e2": ("efn_cache_guard", "enemy_page34_end", "ENEMY_MODULE_BUILD_CACHE", "ENEMY_TABLE", "STAGE"),
    "active": ("enemy_tick", "INITIAL_ENTRY_STATE"),
    "presentation": ("presentation_flow_tick", "normal_game", "normal_stage", "credit_tick",
                     "PRES_CREDITS", "PRES_MODE", "PRES_SCREEN", "PRES_EVENT", "PRES_CONTEXT", "PRES_MAGIC",
                     "PRESENTATION_MAP_ATTRACT", "PRESENTATION_MAP_HIGH_SCORE", "PRESENTATION_MAP_LEVEL_START",
                     "INITIAL_ENTRY_STATE", "PLAYER_CELL_X", "PLAYER_CELL_Y", "STAGE_PENDING"),
}
LOCKED_SHA256 = {
    "ladybug-rate-helper.bin": "609e0e8199a17c5d9a6bf35f7a3f0cddeb8ba029bdb5b8fa6bf2eed6b9efc00c",
    "ladybug-enemy-helper-page34.bin": "057e2803eac24aebb1447d43614fd4aaf67518d933f08d3f128627e9aeb26526",
    "ladybug-adaptive-banked.bin": "3827719dd6d237bd994e072748ef9756a2b113872b897ab561574655d8f590ab",
    "ladybug-adaptive-active.s": "5b662e01cb75841eb03790327c2ad12ecb6cbfdcfa5cb871d1f67efd95b78241",
}
PHASES = {
    "active-monitor-sentinel", "matched-displacement", "freeze-saturated-thaw",
    "candidate-horizontal-displacement", "legal-reversal-concurrent-mover",
    "natural-init", "natural-rate-progression",
}
PHASE_DEADLINE_SECONDS = 45
PHASE_DEADLINES = {"active-monitor-sentinel": 15}
MAZE_PATH = ROOT / "assets/arcade/maze.json"
MAZE_SHA256 = "76361237a90a555f2b78731c3975a209f569a53cb04705eb90d0aad427856048"
HORIZONTAL_MIN_RUNWAY_PIXELS = 30
HORIZONTAL_ALIGNMENT_CALLBACK_CAP = 500
PAGE_BYTES = 0x2000
BANK1_ROM_OFFSET = 0x4000
BANK1_USABLE_BYTES = 0x3E00
BANK1_RESIDENT_BYTES = PAGE_BYTES
BANK1_ASSET_BYTES = BANK1_USABLE_BYTES - BANK1_RESIDENT_BYTES
BANK1_RESIDENT_STAGE_PAGE = 0x21
BANK1_ASSET_STAGE_PAGE = 0x22
BANK1_RESIDENT_PAGE = 0x3E
BANK1_ASSET_PAGE = 0x3F
LOW_PAGE = 0x38
STATE_PAGE = 0x34
AUDIO_PAGE = 0x3D
RATE_STATE = 0x029B
FREEZE_TIMER = 0x005B
FRAMES = 0x0002
FB_SIM_SEQ = 0x0094
FB_FRONT_ID = 0x008F
ENEMY_TABLE = 0xA470
GATE_STATE = 0xA240
VISIBLE_START = 0x2000
VISIBLE_BYTES = 30720
ENEMY_FB_ORIGIN = 0x57EC
PHASE_CONTRACTS = {
    "active-monitor-sentinel": {"fixture": "cold-start active monitor wait at the resident mainloop; read-only", "writes": []},
    "matched-displacement": {"fixture": "natural legal straight vertical segment on paired running builds after read-only equality check of the Part-7 spawner reset", "writes": []},
    "candidate-horizontal-displacement": {
        "fixture": "natural candidate Part-7 progression; search up to 500 actual callbacks within the existing 45-second phase for a visible horizontal actor with at least 30 pixels of authored straight route, then measure 24 actual callbacks",
        "maze_json_sha256": MAZE_SHA256, "writes": []},
    "freeze-saturated-thaw": {"fixture": "adapter-pinned rate boundary values plus actual callbacks; enemy and framebuffer ownership untouched", "writes": ["$004D", "$005B", "$029B-$029F"]},
    "legal-reversal-concurrent-mover": {"fixture": "actor 0 arrives west through (6,4)->(5,4)->(4,4), gate 0 remains 0; another existing active actor moves", "writes": []},
    "natural-init": {"fixture": "from cold boot, let the first presentation tick initialize credits and attract before key-5 credit; arm init_enemy before Enter starts Part 1; one DOTS_LEFT=1, BONUS_LEFT=0 fixture and Up cause a real Part-2 handoff",
                     "writes": ["$0025", "$0033"]},
    "natural-rate-progression": {"fixture": "after natural-init stops at Part 2, repeat DOTS_LEFT=1, BONUS_LEFT=0 and Up for each real Part-2-through-Part-6 handoff; verify Part-7 rate and spawner reset at true init, then record the live spawner state at player-entry return at normal_game+1",
                                 "writes": ["$0025", "$0033"]},
}
ACTIVE_PROBES: list["RuntimeProbe"] = []


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_symbols(path: Path) -> dict[str, int]:
    return {name: int(value, 16) for name, value in SYMBOL_RE.findall(
        path.read_text(encoding="utf-8"))}


def resolve_rate_callsite(build_dir: Path, enemy_bytes: bytes,
                          rate_tick: int) -> dict[str, Any]:
    listing = (build_dir / "ladybug-enemy-runtime.lst").read_text(encoding="utf-8")
    matches = re.findall(
        r"^\s*([0-9A-Fa-f]{4})\s+([0-9A-Fa-f]{6})\s+.*\bjsr\s+\$([0-9A-Fa-f]{4})\b",
        listing, re.MULTILINE | re.IGNORECASE)
    matches = [row for row in matches if int(row[2], 16) == rate_tick]
    if len(matches) != 1:
        raise ValueError(f"enemy listing must identify one actual JSR to rate_tick; found {len(matches)}")
    address = int(matches[0][0], 16)
    encoded = bytes.fromhex(matches[0][1])
    offset = address - 0x0800
    if offset < 0 or offset + len(encoded) > len(enemy_bytes):
        raise ValueError(f"rate_tick callsite ${address:04X} is outside the enemy module artifact")
    if enemy_bytes[offset:offset + len(encoded)] != encoded:
        raise ValueError(f"enemy listing/source bytes differ from staged module at ${address:04X}")
    if encoded != bytes([0xBD, rate_tick >> 8, rate_tick & 0xFF]):
        raise ValueError(f"enemy JSR at ${address:04X} does not call the current mapped rate_tick symbol")
    return {"logical_address": f"${address:04X}", "artifact": "ladybug-enemy-runtime.rom",
            "listing": "ladybug-enemy-runtime.lst", "artifact_offset": offset,
            "bytes_hex": encoded.hex(), "target": f"${rate_tick:04X}",
            "status": "exact-artifact-and-listing-match"}


def inspect_build(build_dir: Path, side: str, profile: str, source_revision: str) -> dict[str, Any]:
    build_dir = build_dir.resolve(strict=True)
    artifacts: dict[str, dict[str, str]] = {}
    for name in ARTIFACTS:
        path = build_dir / name
        if path.is_file():
            artifacts[name] = {"path": name, "sha256": sha256(path), "bytes": str(path.stat().st_size)}
    maps: dict[str, dict[str, Any]] = {}
    for role, name in MAPS.items():
        path = build_dir / name
        if not path.is_file():
            if role in ("rate", "e2", "active") and side == "baseline":
                continue
            raise ValueError(f"required {role} map is missing: {path}")
        symbols = read_symbols(path)
        missing = sorted(set(REQUIRED_SYMBOLS[role]) - symbols.keys())
        if missing:
            raise ValueError(f"{role} map missing required symbols: {', '.join(missing)}")
        maps[role] = {"path": name, "sha256": sha256(path),
                      "symbols": {key: symbols[key] for key in REQUIRED_SYMBOLS[role]}}
    rom = build_dir / "ladybug.rom"
    if not rom.is_file():
        raise ValueError(f"full ROM missing: {rom}")
    source_receipt_path = build_dir / "source-build-receipt.json"
    if not source_receipt_path.is_file():
        raise ValueError(f"source build receipt missing: {source_receipt_path}")
    source_receipt = json.loads(source_receipt_path.read_text(encoding="utf-8"))
    if (source_receipt.get("profile") != "complete" or source_receipt.get("state") != "complete" or
            source_receipt.get("revision") != source_revision):
        raise ValueError("source-build-receipt profile/state/revision does not match the assigned complete build")
    if side == "candidate":
        for name, expected in LOCKED_SHA256.items():
            row = artifacts.get(name)
            if row is None:
                raise ValueError(f"candidate required artifact missing: {name}")
            if row["sha256"] != expected:
                raise ValueError(f"candidate {name} hash {row['sha256']} does not match approved prototype {expected}")
    runtime_contracts: dict[str, Any] = {}
    if side == "candidate":
        enemy_image = build_dir / "ladybug-enemy-runtime.rom"
        enemy_bytes = enemy_image.read_bytes()
        runtime_contracts["rate_tick_callsite"] = resolve_rate_callsite(
            build_dir, enemy_bytes, maps["rate"]["symbols"]["rate_tick"])
    return {
        "side": side,
        "profile": profile,
        "source_revision": source_revision,
        "build_dir": str(build_dir),
        "full_rom_sha256": sha256(rom),
        "source_build_revision": source_receipt["revision"],
        "source_build_profile": source_receipt["profile"],
        "source_build_state": source_receipt["state"],
        "artifacts": artifacts,
        "maps": maps,
        "runtime_contracts": runtime_contracts,
    }


def verify_identity(identity: dict[str, Any]) -> None:
    build_dir = Path(identity["build_dir"]).resolve(strict=True)
    if identity.get("schema") != "rsch014-ready-087-build-identity-v1":
        raise ValueError("unsupported build identity schema")
    for name, item in identity["artifacts"].items():
        path = build_dir / item["path"]
        if not path.is_file() or sha256(path) != item["sha256"]:
            raise ValueError(f"artifact identity changed: {path}")
    rom = build_dir / "ladybug.rom"
    if sha256(rom) != identity["full_rom_sha256"]:
        raise ValueError(f"full ROM identity changed: {rom}")
    source_receipt = json.loads((build_dir / "source-build-receipt.json").read_text(encoding="utf-8"))
    if (source_receipt.get("revision") != identity.get("source_revision") or
            source_receipt.get("revision") != identity.get("source_build_revision") or
            source_receipt.get("profile") != identity.get("source_build_profile") or
            source_receipt.get("state") != identity.get("source_build_state") or
            source_receipt.get("profile") != "complete" or source_receipt.get("state") != "complete"):
        raise ValueError("source-build receipt identity differs from captured build metadata")
    for role, item in identity["maps"].items():
        path = build_dir / item["path"]
        if not path.is_file() or sha256(path) != item["sha256"]:
            raise ValueError(f"map identity changed: {path}")
        current = read_symbols(path)
        for name, address in item["symbols"].items():
            if current.get(name) != address:
                raise ValueError(f"symbol identity changed: {role}.{name}")
    if identity["side"] == "candidate":
        contract = identity.get("runtime_contracts", {}).get("rate_tick_callsite")
        if not isinstance(contract, dict):
            raise ValueError("candidate rate_tick callsite contract is missing or differs")
        enemy = (build_dir / "ladybug-enemy-runtime.rom").read_bytes()
        current_callsite = resolve_rate_callsite(
            build_dir, enemy, identity["maps"]["rate"]["symbols"]["rate_tick"])
        if contract != current_callsite:
            raise ValueError("candidate rate_tick source/listing/staged callsite identity differs")


def dependency_status(receipt: dict[str, Any]) -> tuple[bool, str]:
    ticket = str(receipt.get("ticket", receipt.get("id", ""))).upper().replace("-", "")
    status = str(receipt.get("status", "")).lower()
    actual = receipt.get("actualDone") is True or status in {"done", "actualdone", "complete"}
    if ticket not in {"BUG086", "BUG-086"}:
        return False, "dependency receipt does not identify BUG-086"
    if not actual:
        return False, "BUG-086 is not recorded actualDone/Done"
    if not receipt.get("integrated_commit") and not receipt.get("commit"):
        return False, "BUG-086 completion receipt lacks integrated commit identity"
    return True, "BUG-086 completion identity present"


def validate_plan(plan: dict[str, Any]) -> None:
    if plan.get("schema") != "rsch014-ready-087-phase-plan-v1":
        raise ValueError("unsupported phase plan schema")
    phases = plan.get("phases", [])
    expected = {"active-monitor-sentinel", "matched-displacement", "candidate-horizontal-displacement",
                "freeze-saturated-thaw", "legal-reversal-concurrent-mover", "natural-init",
                "natural-rate-progression"}
    if {p.get("id") for p in phases} != expected:
        raise ValueError("phase plan does not contain the required six scenario contracts")
    for phase in phases:
        deadline = phase.get("deadline_seconds")
        if not isinstance(deadline, int) or not 1 <= deadline <= 45:
            raise ValueError(f"{phase.get('id')} deadline must be 1..45 seconds")
        for field in ("success_marker", "timeout_meaning", "required_reads", "source_predecessors"):
            if not phase.get(field):
                raise ValueError(f"{phase.get('id')} lacks {field}")


def cmd_capture(args: argparse.Namespace) -> int:
    identity = inspect_build(Path(args.build_dir), args.side, args.profile, args.source_revision)
    identity["schema"] = "rsch014-ready-087-build-identity-v1"
    identity["profile"] = args.profile
    identity["assignment_baseline_commit"] = (args.assignment_baseline_commit or args.source_revision)
    if args.bug086_receipt:
        receipt_path = Path(args.bug086_receipt).resolve(strict=True)
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        done, note = dependency_status(receipt)
        identity["bug086_dependency"] = {
            "receipt_path": str(receipt_path),
            "receipt_sha256": sha256(receipt_path),
            "actual_done": done,
            "integrated_commit": receipt.get("integrated_commit", receipt.get("commit")),
            "status": note,
        }
    else:
        identity["bug086_dependency"] = {"actual_done": False, "status": "completion receipt not supplied"}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(identity, indent=2) + "\n", encoding="utf-8")
    print(f"CAPTURED side={args.side} rom_sha256={identity['full_rom_sha256']} maps={len(identity['maps'])} artifacts={len(identity['artifacts'])}")
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    validate_plan(plan)
    baseline = json.loads(Path(args.baseline_identity).read_text(encoding="utf-8"))
    candidate = json.loads(Path(args.candidate_identity).read_text(encoding="utf-8"))
    verify_identity(baseline)
    verify_identity(candidate)
    receipt_path = Path(args.bug086_receipt).resolve(strict=True)
    dep = json.loads(receipt_path.read_text(encoding="utf-8"))
    done, dep_note = dependency_status(dep)
    dep_commit = dep.get("integrated_commit", dep.get("commit"))
    dep_hash = sha256(receipt_path)
    paired_receipts_match = all(
        item.get("bug086_dependency", {}).get("actual_done") is True
        and item.get("bug086_dependency", {}).get("integrated_commit") == dep_commit
        and item.get("bug086_dependency", {}).get("receipt_sha256") == dep_hash
        for item in (baseline, candidate)
    )
    paired_source_revisions_match = _paired_source_revision_matches(baseline, candidate)
    expected_baseline_commit = plan["assignment"].get("source_baseline_commit")
    paired_assignment_baseline_matches = _paired_assignment_baseline_matches(
        baseline, candidate, expected_baseline_commit)
    handlers_attached = True
    plan["dispatchable"] = bool(done and paired_receipts_match and paired_source_revisions_match
                                and paired_assignment_baseline_matches and handlers_attached)
    plan["dispatch_gates"] = {
        "BUG086_actualDone": done,
        "both_builds_captured_against_same_receipt": paired_receipts_match,
        "both_builds_share_source_revision": paired_source_revisions_match,
        "both_builds_share_approved_assignment_baseline": paired_assignment_baseline_matches,
        "runtime_action_handlers_attached": handlers_attached,
    }
    plan["dependency"] = {"ticket": "BUG-086", "status": dep_note,
                           "integrated_commit": dep_commit, "receipt_sha256": dep_hash}
    plan["artifacts"] = {"baseline": baseline, "candidate": candidate}
    plan["resolved_phases"] = []
    for phase in plan["phases"]:
        phase_copy = dict(phase)
        phase_copy["resolved_symbols"] = {}
        for side, spec in phase["symbols"].items():
            # The rate map is candidate-only. Its phase role is named "rate",
            # not "candidate", but the symbols are still resolved from the
            # candidate identity because the baseline has no rate module.
            source_identity = candidate if side in {"candidate", "rate", "presentation"} else baseline
            map_role = spec["map"]
            names = spec["names"]
            if map_role not in source_identity["maps"]:
                phase_copy["resolved_symbols"][side] = {"status": "missing-map", "map_role": map_role}
                continue
            values = source_identity["maps"][map_role]["symbols"]
            phase_copy["resolved_symbols"][side] = {name: f"${values[name]:04X}" for name in names}
        plan["resolved_phases"].append(phase_copy)
    output = Path(args.output)
    plan["runtime_handlers"] = {
        "attached": True,
        "entrypoint": "live --phase PHASE; attaches to existing private XRoar monitor and never launches an emulator",
        "phase_deadline_seconds_max": PHASE_DEADLINE_SECONDS,
        "phase_contracts": PHASE_CONTRACTS,
        "runtime_status": "prepared; not run",
    }
    output.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    print(f"PLAN status={'dispatchable' if plan['dispatchable'] else 'dependency-blocked'} phases={len(plan['phases'])} output={output}")
    return 0


def _require_identity_bytes(expected: bytes, live: bytes, label: str) -> None:
    if not expected or live != expected:
        raise ValueError(f"{label} live bytes do not match the pinned build")


def _require_markers(required: set[str], observed: set[str]) -> None:
    missing = sorted(required - observed)
    if missing:
        raise RuntimeError("required marker missing: " + ", ".join(missing))


def _validate_run_ack(result: object) -> dict[str, Any]:
    if not isinstance(result, dict) or result.get("ok") is not True:
        raise ValueError("run acknowledgement must contain ok=true")
    return result


def _validate_call_receipt(receipt: dict[str, Any] | None, method: str,
                           request_id: int, result: dict[str, Any]) -> None:
    envelope = receipt.get("response_envelope") if isinstance(receipt, dict) else None
    if (not isinstance(receipt, dict) or receipt.get("method") != method or
            receipt.get("request_id") != request_id or receipt.get("outcome") != "ok" or
            not isinstance(envelope, dict) or envelope.get("id") != request_id or
            envelope.get("result") != result or "error" in envelope):
        raise ValueError(f"{method} response is missing or mismatched for request {request_id}")


def _validate_wait_sequence(run_request_id: int, wait_request_id: int) -> None:
    if wait_request_id != run_request_id + 1:
        raise ValueError("wait_for_stop must immediately follow the acknowledged run or step call")


def _classify_stop(result: object, installed: dict[int, int]) -> dict[str, Any]:
    if not isinstance(result, dict):
        raise ValueError("wait_for_stop result must be an object")
    if result.get("reason") == "timeout":
        return {"status": "timeout", "marker": False}
    if result.get("reason") != "breakpoint":
        raise ValueError(f"wait_for_stop reason is not breakpoint: {result.get('reason')!r}")
    bp_id, pc = result.get("bp_id"), result.get("pc")
    if not isinstance(bp_id, int) or isinstance(bp_id, bool) or bp_id not in installed:
        raise ValueError(f"breakpoint ID is not acknowledged and installed: {bp_id!r}")
    if not isinstance(pc, int) or isinstance(pc, bool) or installed[bp_id] != pc:
        raise ValueError(f"breakpoint PC does not match its acknowledged address: {pc!r}")
    return {"status": "breakpoint", "marker": True, "bp_id": bp_id, "pc": pc}


def _classify_step_stop(result: object) -> dict[str, Any]:
    if not isinstance(result, dict):
        raise ValueError("wait_for_stop step result must be an object")
    if result.get("reason") == "timeout":
        return {"status": "timeout", "marker": False}
    if result.get("reason") != "step":
        raise ValueError(f"wait_for_stop reason is not step: {result.get('reason')!r}")
    pc = result.get("pc")
    if not isinstance(pc, int) or isinstance(pc, bool) or not 0 <= pc <= 0xFFFF:
        raise ValueError(f"step stop PC is invalid: {pc!r}")
    if "bp_id" in result:
        raise ValueError("step stop must not report a breakpoint ID")
    return {"status": "step", "marker": False, "pc": pc}


class RuntimeProbe:
    """Synchronous monitor adapter using the repository's existing MonitorClient."""

    def __init__(self, host: str, port: int, deadline: float):
        self.deadline = deadline
        self.installed: dict[int, int] = {}
        self.last_stop: dict[str, Any] | None = None
        self.last_marker_event: dict[str, Any] | None = None
        self.calls = 0
        self.call_hash = hashlib.sha256()
        self.last_calls: list[dict[str, Any]] = []
        self.phase_progress: dict[str, Any] | None = None
        self.client = None
        spec = importlib.util.spec_from_file_location(
            "rsch014_bug009_monitor", ROOT / "scripts/verify_bug009_monitor_input.py")
        if spec is None or spec.loader is None:
            raise RuntimeError("cannot load the existing monitor client")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        remaining = self.left(3.0)
        sock = socket.create_connection((host, port), timeout=remaining)
        sock.settimeout(remaining)
        self.client = module.MonitorClient(sock)
        ACTIVE_PROBES.append(self)
        hello = json.loads(self.client.file.readline())
        if hello.get("method") != "hello":
            raise RuntimeError(f"unexpected monitor greeting: {hello}")
        self.greeting = hello
        self.call("events.subscribe", {"kinds": ["bp"]}, 1.0)

    def left(self, cap: float = 2.0) -> float:
        remaining = self.deadline - time.monotonic() - 0.75
        if remaining <= 0.05:
            raise TimeoutError("phase deadline reached before the next monitor action")
        return min(cap, remaining)

    def call(self, method: str, params: dict[str, Any] | None = None,
             cap: float = 2.0) -> dict[str, Any]:
        assert self.client is not None
        request_id = self.client.next_id
        started = time.monotonic()
        received: list[dict[str, Any]] = []
        original_read = self.client._read

        def capture_read(until: float) -> dict[str, Any]:
            message = original_read(until)
            received.append(message)
            return message

        self.client._read = capture_read
        outcome, error, result = "ok", None, None
        try:
            result = self.client.call(method, params, timeout=self.left(cap))
            return result
        except Exception as exc:
            outcome, error = "error", f"{type(exc).__name__}: {exc}"
            raise
        finally:
            self.client._read = original_read
            response = next((row for row in received if row.get("id") == request_id), None)
            record = {"request_id": request_id, "method": method, "params": params,
                      "outcome": outcome, "error": error, "response_envelope": response,
                      "elapsed_seconds": round(time.monotonic() - started, 6)}
            self.calls += 1
            self.call_hash.update(json.dumps(record, sort_keys=True, separators=(",", ":")).encode())
            self.last_calls.append(record)
            self.last_calls = self.last_calls[-8:]

    def set_breakpoint(self, address: int) -> int:
        ack = self.call("set_breakpoint", {"addr": address, "kind": "exec"})
        ident = ack.get("id")
        if (not isinstance(ident, int) or ack.get("addr") != address or
                ack.get("kind") != "exec"):
            raise RuntimeError(f"set_breakpoint acknowledgement differs at ${address:04X}: {ack}")
        self.installed[ident] = address
        return ident

    def clear_breakpoint(self, ident: int) -> None:
        if ident not in self.installed:
            return
        ack = self.call("clear_breakpoint", {"id": ident})
        if ack.get("ok") is not True:
            raise RuntimeError(f"clear_breakpoint acknowledgement differs for {ident}: {ack}")
        del self.installed[ident]

    def _seed_prior_breakpoint(self) -> None:
        if self.last_stop is not None:
            return
        state = self.call("get_run_state", None, 1.0)
        if state.get("state") != "halted" or state.get("last_stop_reason") != "breakpoint":
            return
        pc, bp_id = state.get("last_stop_pc"), state.get("last_stop_bp_id")
        if (not isinstance(pc, int) or isinstance(pc, bool) or not 0 <= pc <= 0xFFFF or
                not isinstance(bp_id, int) or isinstance(bp_id, bool) or bp_id <= 0):
            raise RuntimeError(f"monitor reports an incomplete prior breakpoint stop: {state}")
        self.last_stop = {"status": "breakpoint", "marker": True, "pc": pc, "bp_id": bp_id}

    def run_until_marker(self, wait_cap_seconds: float = 44.0) -> dict[str, Any]:
        assert self.client is not None
        if not self.installed:
            raise RuntimeError("no acknowledged breakpoint is installed")
        # The monitor stop record survives client reconnects. Cold halt-on-start
        # has no last-stop reason, so it remains on the natural boot path.
        self._seed_prior_breakpoint()
        if self.last_stop is not None:
            prior_pc = self.last_stop["pc"]
            step_id = self.client.next_id
            step_result = self.call("step_instruction", {"n": 1}, 1.0)
            _validate_call_receipt(self.last_calls[-1], "step_instruction", step_id, step_result)
            if step_result.get("ok") is not True or step_result.get("n") != 1:
                raise ValueError("single-step acknowledgement must confirm exactly one instruction")
            wait_id = self.client.next_id
            _validate_wait_sequence(step_id, wait_id)
            step_wait_seconds = self.left(2.0)
            step_wait_ms = max(1, int((step_wait_seconds - 0.25) * 1000))
            step_stop = self.call("wait_for_stop", {"timeout_ms": step_wait_ms}, step_wait_seconds)
            _validate_call_receipt(self.last_calls[-1], "wait_for_stop", wait_id, step_stop)
            step_marker = _classify_step_stop(step_stop)
            if step_marker["status"] == "timeout":
                raise TimeoutError("single-step acknowledgement was not followed by a durable step stop")
            if step_marker["pc"] == prior_pc:
                raise RuntimeError(f"single-step did not pass prior marker ${prior_pc:04X}")
            run_state = self.call("get_run_state", None, 1.0)
            if (run_state.get("state") != "halted" or
                    run_state.get("last_stop_reason") != "step" or
                    run_state.get("last_stop_pc") != step_marker["pc"]):
                raise RuntimeError(f"single-step stop is not durably halted: {run_state}")
            regs = self.call("read_registers", None, 1.0)
            if regs.get("pc") != step_marker["pc"]:
                raise RuntimeError("register PC differs from the durable step-stop PC")
            self.last_stop = None
        run_id = self.client.next_id
        run_result = self.call("run", None, 1.0)
        _validate_run_ack(run_result)
        _validate_call_receipt(self.last_calls[-1], "run", run_id, run_result)
        wait_id = self.client.next_id
        _validate_wait_sequence(run_id, wait_id)
        wait_seconds = self.left(wait_cap_seconds)
        server_wait_ms = max(1, int((wait_seconds - 2.0) * 1000))
        wait_result = self.call("wait_for_stop", {"timeout_ms": server_wait_ms}, wait_seconds)
        wait_receipt = dict(self.last_calls[-1])
        _validate_call_receipt(wait_receipt, "wait_for_stop", wait_id, wait_result)
        classification = _classify_stop(wait_result, self.installed)
        self.last_marker_event = {"run_request_id": run_id, "run_acknowledgement": run_result,
                                  "wait_receipt": wait_receipt, "classification": classification}
        if classification["status"] == "timeout":
            raise TimeoutError("wait_for_stop returned reason=timeout; required marker was not observed")
        self.last_stop = classification
        return classification

    def close(self) -> None:
        if self.client is not None:
            self.client.close()
            self.client = None

    def audit(self) -> dict[str, Any]:
        result = {"monitor_call_count": self.calls, "monitor_call_ledger_sha256": self.call_hash.hexdigest(),
                  "last_monitor_calls": self.last_calls, "last_marker_event": self.last_marker_event}
        if self.phase_progress is not None:
            result["phase_progress"] = self.phase_progress
        return result


def _close_probe(probe: RuntimeProbe) -> None:
    for ident in list(probe.installed):
        try:
            probe.clear_breakpoint(ident)
        except Exception:
            break
    probe.close()


def _phys_read(probe: RuntimeProbe, address: int, length: int) -> bytes:
    result = probe.call("read_memory", {"space": "physical", "addr": address, "length": length}, 2.0)
    data = bytes.fromhex(result["data"])
    if len(data) != length:
        raise RuntimeError(f"physical read ${address:X}+{length} returned {len(data)} bytes")
    return data


def _phys_write(probe: RuntimeProbe, address: int, data: bytes) -> None:
    result = probe.call("write_memory", {"space": "physical", "addr": address, "data": data.hex()}, 2.0)
    if result.get("ok") is not True:
        raise RuntimeError(f"physical state fixture write at ${address:X} was not acknowledged")


def _inject_key(probe: RuntimeProbe, key: int, action: str) -> dict[str, Any]:
    if not 0 <= key <= 0x3E or action not in {"press", "release"}:
        raise ValueError(f"invalid CoCo key transition: key={key!r}, action={action!r}")
    result = probe.call("inject_key", {"key": key, "action": action}, 1.0)
    if result.get("ok") is not True or result.get("key") != key or result.get("action") != action:
        raise RuntimeError(f"XRoar did not acknowledge key {key:02X} {action}: {result}")
    return result


def _run_exact_marker(probe: RuntimeProbe, ident: int, address: int, name: str,
                      wait_cap_seconds: float = 44.0) -> dict[str, Any]:
    marker = probe.run_until_marker(wait_cap_seconds=wait_cap_seconds)
    if marker.get("bp_id") != ident or marker.get("pc") != address:
        raise RuntimeError(f"{name} marker expected breakpoint {ident} at ${address:04X}, got {marker}")
    return marker


def _logical_read(probe: RuntimeProbe, address: int, length: int = 1) -> bytes:
    result = probe.call("read_memory", {"addr": address, "length": length}, 2.0)
    data = bytes.fromhex(result["data"])
    if len(data) != length:
        raise RuntimeError(f"logical read ${address:04X}+{length} returned {len(data)} bytes")
    return data


def _read_spans(probe: RuntimeProbe, page: int, offset: int, length: int) -> bytes:
    result = bytearray()
    while length:
        room = PAGE_BYTES - offset
        count = min(length, room)
        result.extend(_phys_read(probe, page * PAGE_BYTES + offset, count))
        page += 1
        offset = 0
        length -= count
    return bytes(result)


def _verify_bank1_source_staging(source: bytes, runtime_image: bytes,
                                 staged: bytes) -> dict[str, Any]:
    if len(source) != BANK1_USABLE_BYTES:
        raise ValueError(f"authored bank-1 usable payload is {len(source)} bytes, expected {BANK1_USABLE_BYTES}")
    if len(runtime_image) != PAGE_BYTES * 2:
        raise ValueError(f"bank-1 runtime artifact is {len(runtime_image)} bytes, expected {PAGE_BYTES * 2}")
    if len(staged) != BANK1_USABLE_BYTES:
        raise ValueError(f"bank-1 staging payload is {len(staged)} bytes, expected {BANK1_USABLE_BYTES}")
    _require_identity_bytes(source, runtime_image[:BANK1_USABLE_BYTES],
                           "authored bank-1 payload vs runtime artifact")
    _require_identity_bytes(source, staged, "bank-1 source vs RAM $21/$22 staging")
    return {"bank1_source_sha256": sha256_bytes(source),
            "bank1_staging_sha256": sha256_bytes(staged),
            "bank1_source_matches_runtime_artifact": True,
            "bank1_source_matches_staging": True}


def _verify_bank1_staging_destination(staged: bytes, destination: bytes) -> dict[str, Any]:
    if len(staged) != BANK1_USABLE_BYTES or len(destination) != BANK1_USABLE_BYTES:
        raise ValueError("bank-1 staging and destination comparisons must cover exactly $C000-$FDFF")
    _require_identity_bytes(staged, destination, "RAM $21/$22 staging vs $3E/$3F destination")
    return {"bank1_destination_sha256": sha256_bytes(destination),
            "bank1_staging_matches_destination": True}


def _verify_runtime_images(probe: RuntimeProbe, identity: dict[str, Any],
                           need_enemy: bool = True, require_mapping: bool = True,
                           verify_staging: bool = True) -> dict[str, Any]:
    build = Path(identity["build_dir"])
    rom = (build / "ladybug.rom").read_bytes()
    runtime_image = (build / "ladybug-runtime.rom").read_bytes()
    if len(rom) != 0x10000:
        raise ValueError(f"current full ROM is {len(rom)} bytes, expected 65536")
    source = rom[BANK1_ROM_OFFSET:BANK1_ROM_OFFSET + BANK1_USABLE_BYTES]
    if len(source) != BANK1_USABLE_BYTES:
        raise ValueError("authored bank-1 usable payload is truncated")
    if verify_staging:
        staged = _read_spans(probe, BANK1_RESIDENT_STAGE_PAGE, 0, BANK1_USABLE_BYTES)
        source_proof = _verify_bank1_source_staging(source, runtime_image, staged)
    else:
        if len(runtime_image) != PAGE_BYTES * 2:
            raise ValueError(f"bank-1 runtime artifact is {len(runtime_image)} bytes, expected {PAGE_BYTES * 2}")
        _require_identity_bytes(source, runtime_image[:BANK1_USABLE_BYTES],
                               "authored bank-1 payload vs runtime artifact")
        source_proof = {"bank1_source_sha256": sha256_bytes(source),
                        "bank1_source_matches_runtime_artifact": True}
        staged = b""
    destination = _read_spans(probe, BANK1_RESIDENT_PAGE, 0, BANK1_USABLE_BYTES)
    if verify_staging:
        destination_proof = _verify_bank1_staging_destination(staged, destination)
    else:
        _require_identity_bytes(source, destination, "authored bank-1 payload vs $3E/$3F destination")
        destination_proof = {"bank1_destination_sha256": sha256_bytes(destination),
                             "bank1_source_matches_destination": True}
    par6 = _logical_read(probe, 0xFFA6)[0] & 0x3F
    par7 = _logical_read(probe, 0xFFA7)[0] & 0x3F
    if (par6, par7) != (0x3E, 0x3F):
        raise ValueError(f"resident mapping differs: PAR6={par6:02X}, PAR7={par7:02X}")
    logical = (_logical_read(probe, 0xC000, BANK1_RESIDENT_BYTES) +
                _logical_read(probe, 0xE000, BANK1_ASSET_BYTES))
    _require_identity_bytes(destination, logical, "logical PAR6/PAR7 mapping vs $3E/$3F destination")
    proof: dict[str, Any] = {**source_proof, **destination_proof,
                             "bank1_usable_payload_bytes": BANK1_USABLE_BYTES,
                             "bank1_logical_sha256": sha256_bytes(logical),
                             "bank1_logical_matches_destination": True,
                             "resident_sha256": sha256_bytes(destination[:BANK1_RESIDENT_BYTES]),
                             "resident_matches": True, "PAR6": par6, "PAR7": par7}
    if need_enemy:
        enemy = (build / "ladybug-enemy-runtime.rom").read_bytes()
        live_enemy = _read_spans(probe, LOW_PAGE, 0x0800, len(enemy))
        _require_identity_bytes(enemy, live_enemy, "enemy module")
        proof["enemy_module_sha256"] = sha256_bytes(live_enemy)
        proof["enemy_module_matches"] = True
    if require_mapping:
        proof["PAR0"] = _logical_read(probe, 0xFFA0)[0] & 0x3F
        if proof["PAR0"] != LOW_PAGE:
            raise ValueError(f"active callback mapping differs: PAR0={proof['PAR0']:02X}, expected $38")
    if identity["side"] == "candidate":
        rate = (build / "ladybug-rate-helper.bin").read_bytes()
        e2 = (build / "ladybug-enemy-helper-page34.bin").read_bytes()
        live_rate = _read_spans(probe, STATE_PAGE, 0x03B0, len(rate))
        live_e2 = _read_spans(probe, STATE_PAGE, 0x08A0, len(e2))
        _require_identity_bytes(rate, live_rate, "physical page-$34 rate helper")
        _require_identity_bytes(e2, live_e2, "physical page-$34 E2 helper")
        proof.update({"rate_helper_sha256": sha256_bytes(live_rate), "rate_helper_matches": True,
                      "e2_helper_sha256": sha256_bytes(live_e2), "e2_helper_matches": True})
        if require_mapping:
            proof.update({"PAR0": _logical_read(probe, 0xFFA0)[0] & 0x3F,
                          "PAR5": _logical_read(probe, 0xFFA5)[0] & 0x3F})
        if require_mapping and (proof["PAR0"] != LOW_PAGE or proof["PAR5"] != STATE_PAGE):
            raise ValueError(f"candidate execution mapping differs: PAR0={proof['PAR0']:02X}, PAR5={proof['PAR5']:02X}")
    return proof


def _runtime_symbols(identity: dict[str, Any], role: str) -> dict[str, int]:
    try:
        return {name: int(value) for name, value in identity["maps"][role]["symbols"].items()}
    except KeyError as exc:
        raise ValueError(f"current identity lacks the {role} map needed by this phase") from exc


def _classify_rate_marker(par5: int, live_bytes: bytes, rate_bytes: bytes,
                          audio_bytes: bytes) -> str:
    """Classify the shared logical rate address using its active PAR5 image."""
    if par5 == STATE_PAGE:
        _require_identity_bytes(rate_bytes, live_bytes, "candidate rate_tick mapped code")
        return "rate_tick"
    if par5 == AUDIO_PAGE:
        _require_identity_bytes(audio_bytes, live_bytes, "audio-page alias at rate_tick logical address")
        return "audio_alias"
    raise ValueError(f"rate_tick logical-address breakpoint hit with unexpected PAR5=${par5:02X}")


def _active_task_par5(probe: RuntimeProbe) -> int:
    state = probe.call("read_gime_state", None, 2.0)
    task = state.get("mmu_task")
    pars = state.get("pars", {}).get(f"task{task}")
    if task not in (0, 1) or not isinstance(pars, list) or len(pars) != 8:
        raise RuntimeError(f"GIME shadow lacks the active task PARs: {state}")
    return int(pars[5]) & 0x3F


def _candidate_rate_marker(probe: RuntimeProbe, address: int,
                           identity: dict[str, Any],
                           wait_cap_seconds: float = 44.0) -> dict[str, Any]:
    """Wait for rate_tick, discarding only byte-proven audio-page PC aliases."""
    build = Path(identity["build_dir"])
    symbols = _runtime_symbols(identity, "rate")
    if address != symbols["rate_tick"]:
        raise ValueError(f"requested rate marker ${address:04X} differs from current rate_tick ${symbols['rate_tick']:04X}")
    helper = (build / "ladybug-rate-helper.bin").read_bytes()
    source_receipt = json.loads((build / "source-build-receipt.json").read_text(encoding="utf-8"))
    audio = (build / "ladybug-audio-runtime.bin").read_bytes()
    expected_audio_hash = source_receipt.get("artifacts", {}).get("ladybug-audio-runtime.bin")
    if not isinstance(expected_audio_hash, str) or sha256_bytes(audio) != expected_audio_hash:
        raise ValueError("audio runtime bytes are not pinned by the current source-build receipt")
    rate_offset = address - symbols["rate_reset"]
    audio_offset = address - 0xA000
    marker_bytes = 8
    if rate_offset < 0 or audio_offset < 0:
        raise ValueError("rate/audio marker address precedes its current artifact origin")
    rate_bytes = helper[rate_offset:rate_offset + marker_bytes]
    audio_bytes = audio[audio_offset:audio_offset + marker_bytes]
    if len(rate_bytes) != marker_bytes or len(audio_bytes) != marker_bytes:
        raise ValueError("rate/audio address alias is outside a complete artifact span")
    bp_id = probe.set_breakpoint(address)
    ignored_aliases: list[dict[str, Any]] = []
    try:
        while True:
            marker = probe.run_until_marker(wait_cap_seconds=wait_cap_seconds)
            if marker.get("bp_id") != bp_id or marker.get("pc") != address:
                raise RuntimeError(f"candidate rate breakpoint expected ${address:04X}; got {marker}")
            par5 = _active_task_par5(probe)
            logical = _logical_read(probe, address, marker_bytes)
            classification = _classify_rate_marker(par5, logical, rate_bytes, audio_bytes)
            physical = _phys_read(probe, par5 * PAGE_BYTES + address - 0xA000, marker_bytes)
            expected = rate_bytes if classification == "rate_tick" else audio_bytes
            _require_identity_bytes(expected, physical,
                                    "candidate rate_tick destination" if classification == "rate_tick"
                                    else "audio-page alias destination")
            if classification == "rate_tick":
                return {"marker": marker, "breakpoint_id": bp_id, "PAR5": par5,
                        "mapped_bytes_hex": logical.hex(), "ignored_audio_aliases": ignored_aliases}
            ignored_aliases.append({"pc": f"${address:04X}", "PAR5": par5,
                                    "mapped_bytes_hex": logical.hex(), "bp_id": bp_id})
            probe.clear_breakpoint(bp_id)
            bp_id = probe.set_breakpoint(address)
    except Exception:
        probe.clear_breakpoint(bp_id)
        raise


def _low_snapshot(probe: RuntimeProbe) -> dict[str, Any]:
    low = _phys_read(probe, LOW_PAGE * PAGE_BYTES, 0x300)
    def word(address: int) -> int:
        return int.from_bytes(low[address:address + 2], "big")
    return {"stage": low[0x24], "death_state": low[0x4D], "enemy_active": low[0x58],
            "enemy_released": low[0x59], "box_timer": low[0x4A],
            "box_index": low[0x4B], "box_phase": low[0x4C],
            "enemy_move": low[0x61], "frames": word(FRAMES), "fb_sim_seq": word(FB_SIM_SEQ),
            "dots_left": low[0x25], "stage_pending": low[0x26], "bonus_left": low[0x33],
            "initial_entry_state": low[0xA0], "player_cell_x": low[0x09], "player_cell_y": low[0x0A],
            "freeze_timer": word(FREEZE_TIMER), "rate_timer": low[RATE_STATE],
            "rate_bucket": low[RATE_STATE + 1], "rate_frac": low[RATE_STATE + 2],
            "rate_addend": low[RATE_STATE + 3], "rate_phase": low[RATE_STATE + 4]}


def _enemy_records(probe: RuntimeProbe) -> list[dict[str, Any]]:
    data = _phys_read(probe, STATE_PAGE * PAGE_BYTES + ENEMY_TABLE - 0xA000, 32)
    result = []
    for slot in range(4):
        row = data[slot * 8:(slot + 1) * 8]
        result.append({"slot": slot, "active": row[0], "fb": int.from_bytes(row[1:3], "big"),
                       "substep": row[3], "cell_x": row[4], "cell_y": row[5],
                       "saved_bg_valid": row[6], "direction": row[7], "bytes_hex": row.hex()})
    return result


def _matched_enemy_slots(left_snapshot: dict[str, Any], right_snapshot: dict[str, Any],
                         axis: str) -> list[int]:
    """Find corresponding active actors without comparing measured pose state."""
    allowed = (1, 3) if axis == "horizontal" else (0, 2) if axis == "vertical" else ()
    if not allowed:
        raise ValueError(f"unsupported movement axis: {axis}")
    return [slot for slot in range(4)
            if left_snapshot["records"][slot]["active"] != 0
            and right_snapshot["records"][slot]["active"] != 0
            and left_snapshot["records"][slot]["active"] == right_snapshot["records"][slot]["active"]
            and left_snapshot["records"][slot]["direction"] == right_snapshot["records"][slot]["direction"]
            and left_snapshot["records"][slot]["direction"] in allowed]


def _assert_actor_continuity(start_record: dict[str, Any], current_record: dict[str, Any],
                             side: str) -> None:
    if not current_record["active"] or current_record["active"] != start_record["active"]:
        raise RuntimeError(f"{side} matched actor slot/type changed during displacement sample")


def _horizontal_runway_pixels(record: dict[str, Any], maze_nav: list[list[int]],
                              gate_owner: list[list[int]]) -> int:
    """Return authored straight-route pixels remaining from one live enemy record."""
    direction = record.get("direction")
    x, y = record.get("cell_x"), record.get("cell_y")
    substep = record.get("substep")
    if (direction not in (1, 3) or not isinstance(x, int) or not isinstance(y, int) or
            not isinstance(substep, int) or not 0 <= substep < 4 or y < 11 or
            not 0 <= y < len(maze_nav) or not 0 <= x < len(maze_nav[y])):
        return 0
    height, width = len(maze_nav), len(maze_nav[0])
    step_x = 1 if direction == 1 else -1
    cells = 0
    while 0 <= x < width and 0 <= y < height:
        mask = maze_nav[y][x]
        if gate_owner[y][x] or mask & 0x30 or not mask & (1 << direction):
            break
        cells += 1
        x += step_x
        if not 0 <= x < width:
            break
        next_mask = maze_nav[y][x]
        if gate_owner[y][x] or next_mask & 0x30 or not next_mask & (1 << direction):
            break
    return max(0, cells * 8 - substep * 2)


def _candidate_horizontal_options(snapshot: dict[str, Any], maze_nav: list[list[int]],
                                  gate_owner: list[list[int]]) -> list[dict[str, int]]:
    options = []
    for record in snapshot["records"]:
        if not record["active"]:
            continue
        runway = _horizontal_runway_pixels(record, maze_nav, gate_owner)
        if runway >= HORIZONTAL_MIN_RUNWAY_PIXELS:
            options.append({"slot": record["slot"], "active_type": record["active"],
                            "direction": record["direction"], "runway_pixels": runway})
    return sorted(options, key=lambda row: (-row["runway_pixels"], row["slot"]))


def _counter_delta16(current: int, previous: int) -> int:
    return (current - previous) & 0xFFFF


def _surface_span(probe: RuntimeProbe, owner: int, offset: int, length: int) -> bytes:
    if owner not in (0, 1) or not 0 <= offset < VISIBLE_BYTES or offset + length > VISIBLE_BYTES:
        raise ValueError("front surface span is outside the visible owner aperture")
    first_page = 0x30 if owner == 0 else 0x2C
    result = bytearray()
    while length:
        page_index, page_offset = divmod(offset, PAGE_BYTES)
        count = min(length, PAGE_BYTES - page_offset)
        result.extend(_phys_read(probe, (first_page + page_index) * PAGE_BYTES + page_offset, count))
        offset += count
        length -= count
    return bytes(result)


def _front_tile(probe: RuntimeProbe, pointer: int, width: int = 4, rows: int = 16) -> dict[str, Any]:
    owner = _logical_read(probe, FB_FRONT_ID)[0]
    offset = pointer - VISIBLE_START
    if not 0 <= offset <= VISIBLE_BYTES - (rows - 1) * 160 - width:
        raise ValueError(f"actor pixel pointer ${pointer:04X} is outside visible FRONT")
    # $FF9D is write-only on the CPU bus. The monitor's GIME shadow is the
    # supported readback for the value latched by the framebuffer Vbord IRQ.
    gime_state = probe.call("read_gime_state", None, 2.0)
    voff = int(gime_state["registers"]["FF9D"])
    expected = 0xC0 if owner == 0 else 0xB0 if owner == 1 else None
    if expected is None or voff != expected:
        raise ValueError(f"GIME shadow Voffset {voff:02X} does not identify FRONT owner {owner}")
    region = _surface_span(probe, owner, offset, (rows - 1) * 160 + width)
    pixels = b"".join(region[row * 160:row * 160 + width] for row in range(rows))
    return {"owner": owner, "gime_voff1_shadow": voff, "pointer": pointer, "pixel_bytes": len(pixels),
            "pixel_sha256": hashlib.sha256(pixels).hexdigest(), "pixel_nonzero": any(pixels)}


def _snapshot(probe: RuntimeProbe, pixels: bool = False) -> dict[str, Any]:
    state = _low_snapshot(probe)
    records = _enemy_records(probe)
    result: dict[str, Any] = {"state": state, "records": records}
    if pixels:
        result["front_pixels"] = {str(row["slot"]): _front_tile(probe, row["fb"])
                                   for row in records if row["active"] and VISIBLE_START <= row["fb"] < 0x9800}
    return result


def _reach_verified_marker(probe: RuntimeProbe, address: int,
                           verify_images: Any,
                           wait_cap_seconds: float = 44.0) -> tuple[dict[str, Any], int, dict[str, Any]]:
    """Run naturally to the expected marker before reading copied images/mapping."""
    bp_id = probe.set_breakpoint(address)
    marker = probe.run_until_marker(wait_cap_seconds=wait_cap_seconds)
    if marker.get("bp_id") != bp_id or marker.get("pc") != address:
        observed_pc = marker.get("pc")
        observed = f"${observed_pc:04X}" if isinstance(observed_pc, int) else repr(observed_pc)
        raise RuntimeError(f"verified resident marker expected ${address:04X}, got {observed}")
    proof = verify_images(probe)
    return marker, bp_id, proof


def _live_side(identity: dict[str, Any], side: str, proof: dict[str, Any]) -> dict[str, Any]:
    maps = {role: _runtime_symbols(identity, role) for role in ("main", "enemy")}
    if identity["side"] != side:
        raise ValueError(f"expected {side} identity, received {identity['side']}")
    return {"identity": identity, "proof": proof, "maps": maps}


def _rate_expected(stage: int, bucket: int) -> int:
    offsets = (0, 2, 4, 1, 3, 5, 6, 8, 5, 7, 9, 10, 11, 8, 12, 13, 14)
    offset = 0 if stage == 0 else 15 if stage >= 18 else offsets[stage - 1]
    rate_index = min(15, offset + (bucket >> 4))
    return 0x00 if rate_index < 6 else 0x33 if rate_index < 12 else 0x80 if rate_index < 15 else 0xCC


def _movement_admissions(callbacks: int, carries: int, starting_phase: int) -> int:
    if (not isinstance(callbacks, int) or isinstance(callbacks, bool) or callbacks < 0 or
            not isinstance(carries, int) or isinstance(carries, bool) or not 0 <= carries <= callbacks or
            not isinstance(starting_phase, int) or isinstance(starting_phase, bool) or
            starting_phase not in (0, 1)):
        raise ValueError("movement oracle requires callbacks, valid carries, and phase 0 or 1")
    noncarry_callbacks = callbacks - carries
    return carries + (noncarry_callbacks + starting_phase) // 2


def _paired_source_revision_matches(baseline: dict[str, Any], candidate: dict[str, Any]) -> bool:
    baseline_revision = baseline.get("source_revision")
    candidate_revision = candidate.get("source_revision")
    return (isinstance(baseline_revision, str) and bool(baseline_revision.strip()) and
            isinstance(candidate_revision, str) and bool(candidate_revision.strip()) and
            baseline_revision == candidate_revision)


def _paired_assignment_baseline_matches(baseline: dict[str, Any], candidate: dict[str, Any],
                                        expected: str | None) -> bool:
    if not isinstance(expected, str) or not expected.strip():
        return False
    baseline_commit = baseline.get("assignment_baseline_commit")
    candidate_commit = candidate.get("assignment_baseline_commit")
    return baseline_commit == candidate_commit == expected


def _assert_assignment_baseline_matches(baseline: dict[str, Any], candidate: dict[str, Any],
                                        expected: str | None) -> None:
    if not _paired_assignment_baseline_matches(baseline, candidate, expected):
        raise ValueError("baseline and candidate must match the approved assignment baseline commit")


def _assert_pair_source_revision(baseline: dict[str, Any], candidate: dict[str, Any]) -> None:
    if not _paired_source_revision_matches(baseline, candidate):
        raise ValueError("baseline and candidate source revisions must be the same nonempty integrated revision")


def _assert_identity_pair(baseline: dict[str, Any], candidate: dict[str, Any]) -> None:
    if baseline.get("profile") != candidate.get("profile"):
        raise ValueError("baseline and candidate profiles differ")
    if baseline.get("side") != "baseline" or candidate.get("side") != "candidate":
        raise ValueError("paired identities must be baseline then candidate")
    _assert_pair_source_revision(baseline, candidate)
    expected_baseline_commit = json.loads(PLAN.read_text(encoding="utf-8"))["assignment"].get(
        "source_baseline_commit")
    _assert_assignment_baseline_matches(baseline, candidate, expected_baseline_commit)
    for side in (baseline, candidate):
        verify_identity(side)
        dep = side.get("bug086_dependency", {})
        if dep.get("actual_done") is not True:
            raise ValueError("paired current builds were not captured against BUG-086 actualDone")


def _phase_matched(args: argparse.Namespace, deadline: float) -> dict[str, Any]:
    if args.axis != "vertical":
        raise ValueError("paired matched-displacement is vertical only; horizontal uses the approved candidate-only phase")
    baseline = json.loads(Path(args.baseline_identity).read_text(encoding="utf-8"))
    candidate = json.loads(Path(args.candidate_identity).read_text(encoding="utf-8"))
    _assert_identity_pair(baseline, candidate)
    probes: list[RuntimeProbe] = []
    try:
        left = RuntimeProbe(args.baseline_host, args.baseline_port, deadline)
        probes.append(left)
        right = RuntimeProbe(args.candidate_host, args.candidate_port, deadline)
        probes.append(right)
        left.phase_progress = {"phase": "matched-displacement", "side": "baseline"}
        right.phase_progress = {"phase": "matched-displacement", "side": "candidate"}
        # Both processes must have completed natural-init plus real progression
        # through the Part-7 reset, then stop at an enemy callback before sampling.
        right_enemy = _runtime_symbols(candidate, "enemy")
        tick_r = right_enemy["enemy_tick_impl"]
        first_r, id_r, right_proof = _reach_verified_marker(
            right, tick_r, lambda active: _verify_runtime_images(
                active, candidate, verify_staging=False, require_mapping=True))
        right_side = _live_side(candidate, "candidate", right_proof)
        left_enemy = _runtime_symbols(baseline, "enemy")
        tick_l = left_enemy["enemy_tick_impl"]
        first_l, id_l, left_proof = _reach_verified_marker(
            left, tick_l, lambda active: _verify_runtime_images(
                active, baseline, need_enemy=True, verify_staging=False, require_mapping=True))
        left_side = _live_side(baseline, "baseline", left_proof)
        rate_tick = _runtime_symbols(candidate, "rate")["rate_tick"]
        _require_markers({"baseline-enemy-callback", "candidate-enemy-callback"},
                         {"baseline-enemy-callback" if first_l["pc"] == tick_l else "",
                          "candidate-enemy-callback" if first_r["pc"] == tick_r else ""})
        snap_l, snap_r = _snapshot(left, pixels=False), _snapshot(right, pixels=False)
        def checkpoint(snapshot: dict[str, Any]) -> dict[str, int]:
            return {key: snapshot["state"][key] for key in
                    ("stage", "box_index", "box_timer", "box_phase", "enemy_released", "enemy_active",
                     "frames", "fb_sim_seq", "rate_timer", "rate_bucket", "rate_frac", "rate_addend", "rate_phase")}
        left.phase_progress["first_enemy_callback"] = checkpoint(snap_l)
        right.phase_progress["first_enemy_callback"] = checkpoint(snap_r)
        if snap_l["state"]["stage"] != snap_r["state"]["stage"]:
            raise RuntimeError("paired natural-progression processes are on different active parts")
        if snap_l["state"]["stage"] != 7:
            raise RuntimeError(f"paired movement requires the naturally reached Part-7 start; got Part {snap_l['state']['stage']}")
        spawner_keys = ("box_index", "box_timer", "box_phase", "enemy_released", "enemy_active")
        spawner_l = {key: snap_l["state"][key] for key in spawner_keys}
        spawner_r = {key: snap_r["state"][key] for key in spawner_keys}
        if spawner_l != spawner_r:
            raise RuntimeError(f"paired Part-7 spawner checkpoints differ: baseline={spawner_l}, candidate={spawner_r}")
        expected_part7_addend = _rate_expected(7, 0)
        if snap_r["state"]["rate_addend"] != expected_part7_addend or expected_part7_addend == 0:
            raise RuntimeError(f"candidate is not at the approved Part-7 rate reset: {snap_r['state']}")

        # Advance the two naturally progressed Part-7 builds in equal callback
        # counts until a corresponding active actor reaches a legal straight segment.
        # Position and substep are measured state and must not be equality gates.
        # No actor, stage, or rate state is written.
        alignment_callbacks = 0
        alignment_rate_aliases: list[dict[str, Any]] = []
        common = _matched_enemy_slots(snap_l, snap_r, args.axis)
        while not common or snap_r["state"]["rate_addend"] == 0:
            if time.monotonic() >= deadline - 2.0:
                raise TimeoutError("paired Part-7 progression did not produce a same-part, same-actor legal start before the matched-sample deadline")
            mark_l = left.run_until_marker()
            rate_hit = _candidate_rate_marker(right, rate_tick, candidate)
            mark_r = rate_hit["marker"]
            rate_bp = rate_hit["breakpoint_id"]
            if mark_l["pc"] != tick_l:
                raise RuntimeError("paired alignment stopped outside the baseline enemy callback")
            alignment_rate_aliases.extend(rate_hit["ignored_audio_aliases"])
            right.clear_breakpoint(rate_bp)
            mark_r = right.run_until_marker()
            if mark_r["pc"] != tick_r:
                raise RuntimeError("candidate rate_tick did not return to the paired enemy callback")
            snap_l, snap_r = _snapshot(left, pixels=False), _snapshot(right, pixels=False)
            if snap_l["state"]["stage"] != snap_r["state"]["stage"]:
                raise RuntimeError("paired natural Part-7 builds advanced to different parts during alignment")
            alignment_callbacks += 1
            common = _matched_enemy_slots(snap_l, snap_r, args.axis)
            left.phase_progress["last_alignment"] = {
                "callbacks": alignment_callbacks, "state": checkpoint(snap_l),
                "matched_slots": common}
            right.phase_progress["last_alignment"] = {
                "callbacks": alignment_callbacks, "state": checkpoint(snap_r),
                "matched_slots": common}
        if not common:
            raise RuntimeError(f"missing matched active {args.axis} actor in the two live builds")
        slot = common[0]
        actor_start_l = snap_l["records"][slot]
        actor_start_r = snap_r["records"][slot]
        start_direction = actor_start_r["direction"]
        pointer_start_l = snap_l["records"][slot]["fb"]
        pointer_start_r = snap_r["records"][slot]["fb"]
        snap_l["front_pixels"] = {str(slot): _front_tile(left, pointer_start_l)}
        snap_r["front_pixels"] = {str(slot): _front_tile(right, pointer_start_r)}
        if (not snap_l["front_pixels"].get(str(slot), {}).get("pixel_nonzero") or
                not snap_r["front_pixels"].get(str(slot), {}).get("pixel_nonzero")):
            raise RuntimeError("matched active actor FRONT pixel marker is empty")
        start_state_l, start_state_r = snap_l["state"], snap_r["state"]
        if start_state_l["stage"] != start_state_r["stage"]:
            raise RuntimeError("paired builds are on different active parts")
        candidate_addend = start_state_r["rate_addend"]
        if candidate_addend == 0:
            raise RuntimeError("candidate movement sample begins at the zero fractional rate")
        samples: list[dict[str, Any]] = []
        moves_l = moves_r = carries = 0
        last_l, last_r = snap_l, snap_r
        segments = 0
        signed_candidate_delta = 0
        signed_baseline_delta = 0
        raw_vbord_deltas: list[dict[str, int]] = []
        logical_seq_deltas: list[dict[str, int]] = []
        rate_markers: list[dict[str, Any]] = []
        for _ in range(36):
            if time.monotonic() >= deadline - 1.0:
                raise TimeoutError("matched-displacement callback marker did not satisfy its success rule within 45 seconds")
            mark_l = left.run_until_marker()
            rate_hit = _candidate_rate_marker(right, rate_tick, candidate)
            mark_r = rate_hit["marker"]
            rate_bp = rate_hit["breakpoint_id"]
            if mark_l["pc"] != tick_l:
                raise RuntimeError("paired baseline stopped outside the enemy callback")
            rate_markers.append({"pc": f"${mark_r['pc']:04X}", "PAR5": rate_hit["PAR5"],
                                 "mapped_bytes_hex": rate_hit["mapped_bytes_hex"],
                                 "ignored_audio_aliases": rate_hit["ignored_audio_aliases"],
                                 "callback": len(rate_markers) + 1})
            right.clear_breakpoint(rate_bp)
            mark_r = right.run_until_marker()
            if mark_r["pc"] != tick_r:
                raise RuntimeError("candidate rate_tick did not return to the next actual enemy callback")
            now_l, now_r = _snapshot(left, pixels=True), _snapshot(right, pixels=True)
            rec_l, rec_r = now_l["records"][slot], now_r["records"][slot]
            _assert_actor_continuity(actor_start_l, rec_l, "baseline")
            _assert_actor_continuity(actor_start_r, rec_r, "candidate")
            if now_l["state"]["death_state"] or now_r["state"]["death_state"]:
                raise RuntimeError("player death/reset invalidated the matched displacement sample")
            if (rec_l["direction"] != rec_r["direction"] or
                    rec_l["direction"] != start_direction or
                    rec_l["direction"] not in ((1, 3) if args.axis == "horizontal" else (0, 2))):
                break
            if now_l["state"]["stage"] != start_state_l["stage"] or now_r["state"]["stage"] != start_state_r["stage"]:
                raise RuntimeError("active part changed during the matched segment")
            d_l, d_r = rec_l["fb"] - last_l["records"][slot]["fb"], rec_r["fb"] - last_r["records"][slot]["fb"]
            if args.axis == "horizontal":
                direction_sign = 1 if rec_r["direction"] == 1 else -1
                ok_l, ok_r = d_l == 0 or d_l * direction_sign > 0, d_r == 0 or d_r * direction_sign > 0
                pix_l, pix_r = abs(d_l) * 2, abs(d_r) * 2
            else:
                direction_sign = 1 if rec_r["direction"] == 2 else -1
                ok_l, ok_r = d_l == 0 or d_l * direction_sign > 0, d_r == 0 or d_r * direction_sign > 0
                if d_l % 160 or d_r % 160:
                    raise RuntimeError("vertical framebuffer displacement is not scanline aligned")
                pix_l, pix_r = abs(d_l) // 160, abs(d_r) // 160
            if not ok_l or not ok_r:
                raise RuntimeError("active actor moved opposite the matched straight route")
            moves_l += int(d_l != 0)
            moves_r += int(d_r != 0)
            signed_baseline_delta += pix_l
            signed_candidate_delta += pix_r
            frame_delta_l = _counter_delta16(now_l["state"]["frames"], last_l["state"]["frames"])
            frame_delta_r = _counter_delta16(now_r["state"]["frames"], last_r["state"]["frames"])
            seq_delta_l = _counter_delta16(now_l["state"]["fb_sim_seq"], last_l["state"]["fb_sim_seq"])
            seq_delta_r = _counter_delta16(now_r["state"]["fb_sim_seq"], last_r["state"]["fb_sim_seq"])
            raw_vbord_deltas.append({"baseline": frame_delta_l, "candidate": frame_delta_r})
            logical_seq_deltas.append({"baseline": seq_delta_l, "candidate": seq_delta_r})
            old_frac, new_frac = last_r["state"]["rate_frac"], now_r["state"]["rate_frac"]
            carries += int(new_frac < old_frac)
            samples.append({"callback": len(samples) + 1, "baseline_direction": rec_l["direction"],
                            "candidate_direction": rec_r["direction"], "baseline_fb_delta": d_l,
                            "candidate_fb_delta": d_r, "baseline_FRAMES": now_l["state"]["frames"],
                            "candidate_FRAMES": now_r["state"]["frames"],
                            "baseline_FB_SIM_SEQ": now_l["state"]["fb_sim_seq"],
                            "candidate_FB_SIM_SEQ": now_r["state"]["fb_sim_seq"],
                            "candidate_RATE": {key: now_r["state"][key] for key in
                                               ("rate_timer", "rate_bucket", "rate_frac", "rate_addend", "rate_phase")},
                            "baseline_front_pixel_sha256": now_l["front_pixels"].get(str(slot), {}).get("pixel_sha256"),
                            "candidate_front_pixel_sha256": now_r["front_pixels"].get(str(slot), {}).get("pixel_sha256")})
            segments += 1
            last_l, last_r = now_l, now_r
            # Preserve the full bounded straight-segment sample. The first
            # candidate no-movement callback can occur inside the same VBL
            # batch as the preceding movement, so stopping there can leave
            # the raw FRAMES window at zero even though callback sampling is
            # valid. The callback cap and route/death guards remain unchanged.
        n = len(samples)
        raw_vbord_totals = {
            "baseline": sum(row["baseline"] for row in raw_vbord_deltas),
            "candidate": sum(row["candidate"] for row in raw_vbord_deltas),
        }
        if n and (raw_vbord_totals["baseline"] == 0 or raw_vbord_totals["candidate"] == 0):
            raise RuntimeError(
                "raw FRAMES Vbord counters did not advance across the matched sample window: "
                f"callbacks={n}, totals={raw_vbord_totals}, "
                f"baseline={start_state_l['frames']}->{last_l['state']['frames']}, "
                f"candidate={start_state_r['frames']}->{last_r['state']['frames']}"
            )
        sample_progress = {
            "callbacks": n,
            "candidate_rate_start_fraction": start_state_r["rate_frac"],
            "candidate_rate_start_phase": start_state_r["rate_phase"],
            "candidate_rate_addend": candidate_addend,
            "fractional_carries": carries,
            "candidate_observed_pixels": signed_candidate_delta,
            "raw_vbord_totals": raw_vbord_totals,
        }
        left.phase_progress["matched_sample"] = {"side": "baseline", **sample_progress}
        right.phase_progress["matched_sample"] = {"side": "candidate", **sample_progress}
        _require_markers({"same-actor", "zero-rate-interval", "nonzero-rate-movement",
                          "raw-vbord", "front-actor-pixels"},
                         {"same-actor", "zero-rate-interval" if any(row["candidate_fb_delta"] == 0 for row in samples) else "",
                          "nonzero-rate-movement" if moves_r else "", "raw-vbord" if samples and
                          all("candidate_FRAMES" in row for row in samples) else "",
                          "actual-rate-tick" if len(rate_markers) == n else "",
                          "front-actor-pixels" if samples and any(row["candidate_front_pixel_sha256"] for row in samples) else ""})
        candidate_start_phase = start_state_r["rate_phase"]
        admissions = _movement_admissions(n, carries, candidate_start_phase)
        candidate_observed_pixels = signed_candidate_delta
        if abs(candidate_observed_pixels - admissions * 2) > 1:
            raise RuntimeError(
                f"candidate rate oracle differs: observed={candidate_observed_pixels}px "
                f"expected={admissions * 2}px tolerance=1px callbacks={n} carries={carries} "
                f"starting_phase={candidate_start_phase} starting_fraction={start_state_r['rate_frac']}"
            )
        return {"status": "pass-runtime-marker-set", "phase": "matched-displacement", "axis": args.axis,
                "alignment_callbacks": alignment_callbacks,
                "alignment_audio_aliases": alignment_rate_aliases,
                "callback_count": n, "same_actor_slot": slot, "active_part": start_state_r["stage"],
                "candidate_rate_start": candidate_addend,
                "candidate_rate_start_phase": candidate_start_phase,
                "fractional_carries": carries,
                "policy_admissions": admissions, "candidate_observed_pixels": candidate_observed_pixels,
                "candidate_expected_pixels": admissions * 2, "pixel_tolerance": 1,
                "baseline_observed_pixels": signed_baseline_delta, "baseline_move_count": moves_l,
                "candidate_move_count": moves_r, "raw_vbord_counts": {
                    "baseline_start": start_state_l["frames"], "baseline_end": last_l["state"]["frames"],
                    "candidate_start": start_state_r["frames"], "candidate_end": last_r["state"]["frames"]},
                "raw_vbord_totals": raw_vbord_totals,
                "logical_fb_seq_counts": {"baseline_start": start_state_l["fb_sim_seq"],
                    "baseline_end": last_l["state"]["fb_sim_seq"], "candidate_start": start_state_r["fb_sim_seq"],
                    "candidate_end": last_r["state"]["fb_sim_seq"]},
                "raw_vbord_deltas_by_callback": raw_vbord_deltas,
                "fb_sim_seq_deltas_by_callback": logical_seq_deltas,
                "actual_rate_tick_markers": rate_markers,
                "samples": samples, "identity": {"baseline": left_side["proof"], "candidate": right_side["proof"]},
                "monitor_audit": {"baseline": left.audit(), "candidate": right.audit()}}
    finally:
        for probe in probes:
            _close_probe(probe)


def _phase_candidate_horizontal(args: argparse.Namespace, deadline: float) -> dict[str, Any]:
    candidate = json.loads(Path(args.identity).read_text(encoding="utf-8"))
    verify_identity(candidate)
    if candidate.get("side") != "candidate":
        raise ValueError("candidate-horizontal-displacement requires the candidate identity")
    if sha256(MAZE_PATH) != MAZE_SHA256:
        raise ValueError("authored maze navigation identity changed")
    maze = json.loads(MAZE_PATH.read_text(encoding="utf-8"))
    maze_nav, gate_owner = maze.get("maze_nav"), maze.get("gate_owner")
    if (not isinstance(maze_nav, list) or len(maze_nav) != 24 or
            not isinstance(gate_owner, list) or len(gate_owner) != 24 or
            any(not isinstance(row, list) or len(row) != 24 for row in maze_nav + gate_owner)):
        raise ValueError("authored maze navigation dimensions differ from the pinned 24x24 contract")
    prerequisite = json.loads(Path(args.prerequisite_receipt).read_text(encoding="utf-8"))
    ready_state = prerequisite.get("part7_ready_state", {})
    if (prerequisite.get("phase") != "natural-rate-progression" or
            prerequisite.get("status") != "pass-runtime-marker-set" or
            prerequisite.get("build_side") != "candidate" or ready_state.get("stage") != 7 or
            ready_state.get("rate_addend") != 0x33):
        raise ValueError("candidate Part-7 natural-progression prerequisite is missing or mismatched")

    probe = RuntimeProbe(args.host, args.port, deadline)
    try:
        probe.phase_progress = {"phase": "candidate-horizontal-displacement", "side": "candidate"}
        enemy = _runtime_symbols(candidate, "enemy")
        tick = enemy["enemy_tick_impl"]
        marker, breakpoint_id, proof = _reach_verified_marker(
            probe, tick, lambda active: _verify_runtime_images(
                active, candidate, need_enemy=True, verify_staging=False, require_mapping=True))
        side = _live_side(candidate, "candidate", proof)
        image_verified = all(proof.get(key) is True for key in
                             ("resident_matches", "enemy_module_matches",
                              "rate_helper_matches", "e2_helper_matches")) and \
                         proof.get("PAR0") == LOW_PAGE and proof.get("PAR5") == STATE_PAGE
        _require_markers({"candidate-enemy-callback", "candidate-live-image"},
                         {"candidate-enemy-callback" if marker["pc"] == tick else "",
                          "candidate-live-image" if image_verified else ""})
        rate_tick = _runtime_symbols(candidate, "rate")["rate_tick"]
        snapshot = _snapshot(probe, pixels=False)
        state = snapshot["state"]
        if state["stage"] != 7 or state["rate_addend"] != 0x33:
            raise RuntimeError(f"candidate is not in natural Part-7 addend-$33 play: {state}")

        def advance_callback() -> tuple[dict[str, Any], dict[str, Any]]:
            hit = _candidate_rate_marker(probe, rate_tick, candidate)
            rate_bp = hit["breakpoint_id"]
            probe.clear_breakpoint(rate_bp)
            next_marker = probe.run_until_marker()
            if next_marker["pc"] != tick:
                raise RuntimeError("candidate-only sample stopped outside the actual enemy callback")
            return _snapshot(probe, pixels=False), hit

        alignment_callbacks = 0
        selected: tuple[dict[str, int], dict[str, Any]] | None = None
        while alignment_callbacks <= HORIZONTAL_ALIGNMENT_CALLBACK_CAP:
            state = snapshot["state"]
            if state["stage"] != 7 or state["rate_addend"] != 0x33:
                raise RuntimeError("candidate left the approved Part-7 addend-$33 window before sampling")
            if state["death_state"] or state["freeze_timer"]:
                raise RuntimeError("candidate death or freeze state invalidated horizontal sample setup")
            options = _candidate_horizontal_options(snapshot, maze_nav, gate_owner)
            visible_options = []
            for option in options:
                record = snapshot["records"][option["slot"]]
                visible = VISIBLE_START <= record["fb"] < 0x9800
                visible_options.append({**option, "visible": visible,
                                        "cell": [record["cell_x"], record["cell_y"]],
                                        "substep": record["substep"]})
            probe.phase_progress["alignment"] = {
                "callbacks": alignment_callbacks,
                "stage": state["stage"], "rate_addend": state["rate_addend"],
                "rate_phase": state["rate_phase"], "rate_frac": state["rate_frac"],
                "death_state": state["death_state"], "freeze_timer": state["freeze_timer"],
                "box_index": state["box_index"], "box_timer": state["box_timer"],
                "enemy_released": state["enemy_released"], "enemy_active": state["enemy_active"],
                "visible_route_options": visible_options,
            }
            if state["rate_phase"] == 0:
                for option in visible_options:
                    if not option["visible"]:
                        continue
                    record = snapshot["records"][option["slot"]]
                    front = _front_tile(probe, record["fb"])
                    if front["pixel_nonzero"]:
                        selected = (option, front)
                        break
            if selected:
                break
            if (alignment_callbacks == HORIZONTAL_ALIGNMENT_CALLBACK_CAP or
                    time.monotonic() >= deadline - 2.0):
                probe.phase_progress["alignment"]["stop_reason"] = (
                    "callback_cap" if alignment_callbacks == HORIZONTAL_ALIGNMENT_CALLBACK_CAP
                    else "phase_deadline")
                raise TimeoutError(
                    "no visible Part-7 horizontal actor with 30px of authored straight route "
                    f"reached phase zero after {alignment_callbacks} search callbacks")
            snapshot, _ = advance_callback()
            alignment_callbacks += 1

        option, start_front = selected
        slot = option["slot"]
        actor_start = snapshot["records"][slot]
        start_state = snapshot["state"]
        if start_state["rate_phase"] != 0 or start_state["rate_addend"] != 0x33:
            raise RuntimeError("candidate horizontal sample did not begin at Part-7 addend $33, phase zero")
        if _horizontal_runway_pixels(actor_start, maze_nav, gate_owner) < HORIZONTAL_MIN_RUNWAY_PIXELS:
            raise RuntimeError("selected candidate actor no longer has the approved straight-route clearance")

        samples: list[dict[str, Any]] = []
        carries = moved_callbacks = 0
        signed_pixel_delta = 0
        raw_vbord_deltas: list[int] = []
        logical_seq_deltas: list[int] = []
        rate_markers: list[dict[str, Any]] = []
        first_move_front: dict[str, Any] | None = None
        last = snapshot
        for index in range(24):
            if time.monotonic() >= deadline - 1.0:
                raise TimeoutError("candidate horizontal 24-callback marker set did not finish within its 45-second phase")
            now, rate_hit = advance_callback()
            rate_markers.append({"pc": f"${rate_hit['marker']['pc']:04X}",
                                 "PAR5": rate_hit["PAR5"],
                                 "mapped_bytes_hex": rate_hit["mapped_bytes_hex"],
                                 "ignored_audio_aliases": rate_hit["ignored_audio_aliases"],
                                 "callback": index + 1})
            state_now, record = now["state"], now["records"][slot]
            _assert_actor_continuity(actor_start, record, "candidate")
            if state_now["death_state"] or state_now["freeze_timer"]:
                raise RuntimeError(f"candidate death/freeze invalidated horizontal sample at callback {index + 1}")
            if state_now["stage"] != 7 or state_now["rate_addend"] != 0x33:
                raise RuntimeError(f"candidate Part-7 addend changed during horizontal sample at callback {index + 1}")
            if record["direction"] != actor_start["direction"]:
                raise RuntimeError(f"candidate actor turned before callback {index + 1} of the straight sample")
            delta_fb = record["fb"] - last["records"][slot]["fb"]
            direction_sign = 1 if actor_start["direction"] == 1 else -1
            if delta_fb not in (0, direction_sign):
                raise RuntimeError(f"candidate actor moved outside the expected horizontal step at callback {index + 1}: {delta_fb}")
            pixel_delta = abs(delta_fb) * 2
            signed_pixel_delta += pixel_delta
            moved_callbacks += int(delta_fb != 0)
            old_fraction, new_fraction = last["state"]["rate_frac"], state_now["rate_frac"]
            carries += int(new_fraction < old_fraction)
            frame_delta = _counter_delta16(state_now["frames"], last["state"]["frames"])
            seq_delta = _counter_delta16(state_now["fb_sim_seq"], last["state"]["fb_sim_seq"])
            raw_vbord_deltas.append(frame_delta)
            logical_seq_deltas.append(seq_delta)
            front = _front_tile(probe, record["fb"]) if delta_fb else None
            if front and not front["pixel_nonzero"]:
                raise RuntimeError(f"candidate actor FRONT pixels disappeared at callback {index + 1}")
            if front and first_move_front is None:
                first_move_front = front
            samples.append({"callback": index + 1, "slot": slot,
                            "actor_type": record["active"], "direction": record["direction"],
                            "cell_x": record["cell_x"], "cell_y": record["cell_y"],
                            "substep": record["substep"], "fb": record["fb"],
                            "fb_delta": delta_fb, "pixel_delta": pixel_delta,
                            "rate_state": {key: state_now[key] for key in
                                           ("rate_timer", "rate_bucket", "rate_frac", "rate_addend", "rate_phase")},
                            "FRAMES": state_now["frames"], "FRAMES_delta": frame_delta,
                            "FB_SIM_SEQ": state_now["fb_sim_seq"], "FB_SIM_SEQ_delta": seq_delta,
                            "all_enemy_records": now["records"], "front_pixels": front})
            last = now

        expected_carries = (4, 5)
        if carries not in expected_carries:
            raise RuntimeError(f"candidate Part-7 $33 sample carry count {carries} is outside expected {expected_carries}")
        admissions = _movement_admissions(24, carries, start_state["rate_phase"])
        expected_pixels = admissions * 2
        if signed_pixel_delta != expected_pixels or abs(signed_pixel_delta - 28) > 1:
            raise RuntimeError(f"candidate rate oracle differs: observed={signed_pixel_delta}px expected={expected_pixels}px tolerance=1px")
        if moved_callbacks != admissions:
            raise RuntimeError(f"candidate movement callbacks {moved_callbacks} differ from {admissions} policy admissions")
        if moved_callbacks == 24 or moved_callbacks == 0:
            raise RuntimeError("candidate sample did not observe both zero-movement and movement callbacks")
        if sum(raw_vbord_deltas) == 0 or sum(logical_seq_deltas) == 0:
            raise RuntimeError("candidate raw FRAMES or FB_SIM_SEQ did not advance during the actual-callback sample")
        final_front = _front_tile(probe, last["records"][slot]["fb"])
        if not final_front["pixel_nonzero"]:
            raise RuntimeError("candidate actor FRONT pixels are empty at the sample endpoint")
        _require_markers({"candidate-actor", "straight-route", "zero-rate-interval",
                          "nonzero-rate-movement", "actual-rate-tick", "raw-vbord",
                          "logical-simulation-sequence", "front-actor-pixels"},
                         {"candidate-actor", "straight-route",
                          "zero-rate-interval" if moved_callbacks < 24 else "",
                          "nonzero-rate-movement" if moved_callbacks else "",
                          "actual-rate-tick" if len(rate_markers) == 24 else "",
                          "raw-vbord" if sum(raw_vbord_deltas) else "",
                          "logical-simulation-sequence" if sum(logical_seq_deltas) else "",
                          "front-actor-pixels" if start_front["pixel_nonzero"] and final_front["pixel_nonzero"] else ""})
        return {"status": "pass-runtime-marker-set", "phase": "candidate-horizontal-displacement",
                "build_side": "candidate", "active_part": 7, "callback_count": len(samples),
                "alignment_callbacks": alignment_callbacks, "actor_slot": slot,
                "actor_type": actor_start["active"], "direction": actor_start["direction"],
                "start_cell": [actor_start["cell_x"], actor_start["cell_y"]],
                "start_substep": actor_start["substep"],
                "authored_straight_route_clearance_pixels": option["runway_pixels"],
                "maze_json_sha256": MAZE_SHA256,
                "candidate_rate_start": start_state["rate_addend"],
                "candidate_rate_start_phase": start_state["rate_phase"],
                "candidate_rate_start_fraction": start_state["rate_frac"],
                "fractional_carries": carries, "policy_admissions": admissions,
                "candidate_observed_pixels": signed_pixel_delta,
                "candidate_expected_pixels": expected_pixels, "pixel_tolerance": 1,
                "movement_callbacks": moved_callbacks,
                "raw_FRAMES_start": snapshot["state"]["frames"],
                "raw_FRAMES_end": last["state"]["frames"],
                "raw_FRAMES_total": sum(raw_vbord_deltas),
                "FB_SIM_SEQ_start": snapshot["state"]["fb_sim_seq"],
                "FB_SIM_SEQ_end": last["state"]["fb_sim_seq"],
                "FB_SIM_SEQ_total": sum(logical_seq_deltas),
                "start_enemy_records": snapshot["records"],
                "front_pixels": {"start": start_front, "first_movement": first_move_front,
                                 "end": final_front},
                "actual_rate_tick_markers": rate_markers, "samples": samples,
                "identity": side["proof"], "monitor_audit": probe.audit(),
                "baseline_comparison": "not measured; baseline 24px remains a formula reference only"}
    finally:
        _close_probe(probe)


def _require_aggregate_vbord_progress(deltas: list[int]) -> int:
    if not deltas:
        raise RuntimeError("raw Vbord frame marker has no samples across the freeze window")
    total = sum(deltas)
    if total == 0:
        raise RuntimeError("raw Vbord frame marker did not advance across the complete freeze window")
    return total


def _phase_freeze(args: argparse.Namespace, deadline: float) -> dict[str, Any]:
    identity = json.loads(Path(args.identity).read_text(encoding="utf-8"))
    verify_identity(identity)
    if identity["side"] != "candidate":
        raise ValueError("freeze-saturated-thaw requires the candidate identity")
    tick = _runtime_symbols(identity, "enemy")["enemy_tick_impl"]
    probe = RuntimeProbe(args.host, args.port, deadline)
    try:
        first, bp_id, proof = _reach_verified_marker(
            probe, tick,
            lambda active: _verify_runtime_images(active, identity, verify_staging=False))
        side = _live_side(identity, "candidate", proof)
        baseline = _snapshot(probe, pixels=True)
        active_slots = [row["slot"] for row in baseline["records"] if row["active"] and row["direction"] in range(4)]
        if not active_slots:
            raise RuntimeError("no active legal-direction enemy exists for freeze/movement contrast")
        write_log: list[dict[str, Any]] = []

        def fixture(freeze: int, timer: int, bucket: int, frac: int, addend: int, phase: int) -> None:
            if not 0 <= freeze <= 0xFFFF or any(not 0 <= value <= 0xFF for value in
                    (timer, bucket, frac, addend, phase)):
                raise ValueError("rate fixture contains an out-of-byte-range value")
            freeze_bytes = freeze.to_bytes(2, "big")
            rate_bytes = bytes([timer, bucket, frac, addend, phase])
            _phys_write(probe, LOW_PAGE * PAGE_BYTES + FREEZE_TIMER, freeze_bytes)
            _phys_write(probe, LOW_PAGE * PAGE_BYTES + RATE_STATE, rate_bytes)
            write_log.extend([{"address": f"${FREEZE_TIMER:04X}", "value_hex": freeze_bytes.hex()},
                              {"address": f"${RATE_STATE:04X}", "value_hex": rate_bytes.hex()}])

        def callback() -> dict[str, Any]:
            marker = probe.run_until_marker()
            if marker["pc"] != tick:
                raise RuntimeError("actual enemy callback marker stopped at the wrong address")
            return _snapshot(probe)

        checks: list[dict[str, Any]] = []
        cases = (("bucket-0f-to-10", 2, 1, 0x0F, 0x5A, 0xCC, 1, 0x10),
                 ("bucket-ef-to-f0", 2, 1, 0xEF, 0xA5, 0xCC, 1, 0xF0),
                 ("saturated-expiry", 2, 1, 0xF0, 0x6B, 0xCC, 1, 0xF0),
                 ("saturated-nonexpiry", 2, 2, 0xF0, 0x6B, 0xCC, 1, 0xF0))
        for name, freeze, timer, bucket, frac, addend, phase, expected_bucket in cases:
            before = _snapshot(probe)
            fixture(freeze, timer, bucket, frac, addend, phase)
            before = _snapshot(probe)
            after = callback()
            required_timer = 60 if timer == 1 else timer - 1
            if (after["state"]["rate_bucket"] != expected_bucket or
                    after["state"]["rate_timer"] != required_timer or
                    after["state"]["freeze_timer"] != freeze - 1 or
                    after["state"]["rate_frac"] != frac or after["state"]["rate_phase"] != phase or
                    after["records"] != before["records"]):
                raise RuntimeError(f"{name}: real callback state differed from frozen boundary expectation")
            checks.append({"case": name, "before": before["state"], "after": after["state"],
                           "actual_callback_pc": f"${tick:04X}", "records_held": True})
        fixture(300, 96, 0xF0, 0, 0xCC, 0)
        full_start = _snapshot(probe, pixels=True)
        if full_start["state"]["freeze_timer"] != 300:
            raise RuntimeError("full freeze fixture was not installed")
        previous = full_start
        trace = hashlib.sha256()
        frame_deltas: list[int] = []
        sim_deltas: list[int] = []
        for index in range(1, 301):
            current = callback()
            state = current["state"]
            if state["freeze_timer"] != 300 - index:
                raise RuntimeError(f"real freeze countdown skipped at callback {index}: {state['freeze_timer']}")
            if state["rate_frac"] != 0 or state["rate_phase"] != 0:
                raise RuntimeError(f"fractional movement state changed while frozen at callback {index}")
            if current["records"] != full_start["records"]:
                raise RuntimeError(f"enemy origin/table changed while frozen at callback {index}")
            frame_delta = (state["frames"] - previous["state"]["frames"]) & 0xFFFF
            sim_delta = (state["fb_sim_seq"] - previous["state"]["fb_sim_seq"]) & 0xFFFF
            frame_deltas.append(frame_delta)
            sim_deltas.append(sim_delta)
            trace.update(f"{index}:{state['frames']}:{state['fb_sim_seq']}:{state['freeze_timer']};".encode())
            previous = current
        raw_vbord_total = _require_aggregate_vbord_progress(frame_deltas)
        full_end = _snapshot(probe, pixels=True)
        if full_end["state"]["freeze_timer"] != 0 or full_end["records"] != full_start["records"]:
            raise RuntimeError("FREEZE_TIMER 1->0 callback did not hold all enemy origins")
        initial_pixels = full_start["front_pixels"]
        thaw_pixels = full_end["front_pixels"]
        if any(initial_pixels.get(key, {}).get("pixel_sha256") != thaw_pixels.get(key, {}).get("pixel_sha256")
               for key in initial_pixels):
            raise RuntimeError("front-buffer enemy origin pixels changed during the full freeze")
        after_thaw: list[dict[str, Any]] = []
        last = full_end
        for _ in range(8):
            current = callback()
            after_thaw.append(current)
            if any(a["fb"] != b["fb"] for a, b in zip(last["records"], current["records"])):
                break
            last = current
        thaw_moved = any(a["fb"] != b["fb"] for a, b in zip(full_end["records"], after_thaw[-1]["records"])) if after_thaw else False
        if not thaw_moved:
            raise RuntimeError("actual post-thaw enemy callback movement marker was not observed")
        movement_pixels = _snapshot(probe, pixels=True)
        rate_before_death = {key: movement_pixels["state"][key] for key in
                             ("rate_timer", "rate_bucket", "rate_frac", "rate_addend", "rate_phase")}
        _phys_write(probe, LOW_PAGE * PAGE_BYTES + 0x004D, b"\x01")
        write_log.append({"address": "$004D", "value_hex": "01"})
        death_bypass = callback()
        rate_after_death = {key: death_bypass["state"][key] for key in rate_before_death}
        if death_bypass["state"]["death_state"] == 0 or rate_after_death != rate_before_death:
            raise RuntimeError("real death-path callback did not bypass the rate clock")
        return {"status": "pass-runtime-marker-set", "phase": "freeze-saturated-thaw",
                "fixture": PHASE_CONTRACTS["freeze-saturated-thaw"], "direct_state_writes": write_log,
                "boundary_checks": checks, "full_freeze_callbacks": 300,
                "freeze_start": full_start["state"], "freeze_end": full_end["state"],
                "zero_to_nonzero_pixels": {"before": initial_pixels, "after_thaw": movement_pixels["front_pixels"]},
                "thaw_callback_count": len(after_thaw), "thaw_movement_observed": thaw_moved,
                "death_bypass": {"actual_enemy_tick_pc": f"${tick:04X}", "state": death_bypass["state"],
                                 "rate_state_unchanged": True},
                "raw_vbord_delta_min": min(frame_deltas), "raw_vbord_delta_max": max(frame_deltas),
                "raw_vbord_delta_total": raw_vbord_total,
                "fb_sim_seq_delta_min": min(sim_deltas), "fb_sim_seq_delta_max": max(sim_deltas),
                "300_callback_trace_sha256": trace.hexdigest(), "identity": side["proof"],
                "monitor_audit": probe.audit()}
    finally:
        _close_probe(probe)


def _phase_reversal(args: argparse.Namespace, deadline: float) -> dict[str, Any]:
    identity = json.loads(Path(args.identity).read_text(encoding="utf-8"))
    verify_identity(identity)
    if identity["side"] != "candidate":
        raise ValueError("legal-reversal-concurrent-mover requires the candidate identity")
    enemy = _runtime_symbols(identity, "enemy")
    tick = enemy["enemy_tick_impl"]
    choose = enemy.get("ecd_choose")
    blocked = enemy.get("ecd_blocked")
    if choose is None or blocked is None:
        raise ValueError("current enemy map does not resolve both legal chooser outcomes")
    probe = RuntimeProbe(args.host, args.port, deadline)
    try:
        first, tick_bp, proof = _reach_verified_marker(
            probe, tick,
            lambda active: _verify_runtime_images(active, identity, verify_staging=False))
        side = _live_side(identity, "candidate", proof)
        ids = {"tick": tick_bp, "choose": probe.set_breakpoint(choose),
               "blocked": probe.set_breakpoint(blocked)}
        initial = _snapshot(probe, pixels=True)
        gates = _phys_read(probe, STATE_PAGE * PAGE_BYTES + GATE_STATE - 0xA000, 20)
        actor = initial["records"][0]
        others = [row for row in initial["records"][1:] if row["active"] and row["direction"] in range(4)]
        if gates[0] != 0:
            raise RuntimeError(f"legal-reversal fixture gate 0 must remain 0; got {gates[0]}")
        if (not actor["active"] or (actor["cell_x"], actor["cell_y"], actor["direction"]) != (6, 4, 3)):
            raise RuntimeError("missing legal actor fixture: slot 0 must start westbound at cell (6,4)")
        expected_actor_fb = ENEMY_FB_ORIGIN + (6 - 12) * 4 + (4 - 12) * 1280
        if actor["fb"] != expected_actor_fb or actor["substep"] != 0:
            raise RuntimeError("legal actor framebuffer pointer/substep does not match the (6,4) arrival fixture")
        if not others:
            raise RuntimeError("missing concurrent mover fixture: another active actor with a legal direction is required")
        observed: set[str] = {"actual-enemy-callback", "initial-actor-6-4", "gate0-zero"}
        cells = [(actor["cell_x"], actor["cell_y"])]
        current = initial
        chooser_event = None
        other_moved = False
        reverse_callback_other_moved = False
        pending_reverse_other_ptrs: dict[int, int] | None = None
        final = None
        while time.monotonic() < deadline - 1.0:
            mark = probe.run_until_marker()
            snapshot = _snapshot(probe, pixels=True)
            if _phys_read(probe, STATE_PAGE * PAGE_BYTES + GATE_STATE - 0xA000, 1)[0] != 0:
                raise RuntimeError("gate 0 changed during the legal-reversal route")
            if mark["pc"] == tick:
                cell = (snapshot["records"][0]["cell_x"], snapshot["records"][0]["cell_y"])
                if cell != cells[-1]:
                    cells.append(cell)
                if (snapshot["records"][0]["cell_x"], snapshot["records"][0]["cell_y"]) == (4, 4):
                    observed.add("actor-reached-4-4")
                other_moved = other_moved or any(snapshot["records"][slot]["fb"] != current["records"][slot]["fb"]
                                                 for slot in range(1, 4) if snapshot["records"][slot]["active"])
                if pending_reverse_other_ptrs is not None:
                    reverse_callback_other_moved = any(
                        snapshot["records"][slot]["active"] and
                        snapshot["records"][slot]["fb"] != pointer
                        for slot, pointer in pending_reverse_other_ptrs.items())
                    pending_reverse_other_ptrs = None
                if snapshot["records"][0]["direction"] == 1 and "actor-reached-4-4" in observed:
                    final = snapshot
                    break
                current = snapshot
                continue
            if mark["pc"] == blocked:
                direct = _phys_read(probe, LOW_PAGE * PAGE_BYTES, 0x100)
                enemy_ptr = int.from_bytes(direct[0x5E:0x60], "big")
                record = _enemy_records(probe)[0]
                if enemy_ptr == ENEMY_TABLE and (record["cell_x"], record["cell_y"], record["direction"]) == (4, 4, 3):
                    raise RuntimeError("actual callback reached ecd_blocked for the actor's legal east reverse")
                observed.add("other-actor-blocked-marker-recorded")
                current = snapshot
                continue
            if mark["pc"] == choose:
                direct = _phys_read(probe, LOW_PAGE * PAGE_BYTES, 0x100)
                enemy_ptr = int.from_bytes(direct[0x5E:0x60], "big")
                candidate = direct[0x7C]
                record = _enemy_records(probe)[0]
                gate_at_choice = _phys_read(probe, STATE_PAGE * PAGE_BYTES + GATE_STATE - 0xA000, 1)[0]
                if enemy_ptr == ENEMY_TABLE and (record["cell_x"], record["cell_y"], record["direction"]) == (4, 4, 3):
                    if candidate != 1 or gate_at_choice != 0:
                        raise RuntimeError(f"actual reverse chooser differs: candidate={candidate}, gate0={gate_at_choice}")
                    chooser_event = {"pc": f"${choose:04X}", "active_record_pointer": f"${enemy_ptr:04X}",
                                     "incoming_cell": [4, 4], "incoming_direction": 3,
                                     "selected_candidate": candidate, "gate0": gate_at_choice}
                    pending_reverse_other_ptrs = {row["slot"]: row["fb"] for row in
                                                   _enemy_records(probe)[1:] if row["active"]}
                    observed.add("legal-east-reverse-selected")
                current = snapshot
                continue
        if final is None:
            raise TimeoutError("legal east reverse and concurrent mover marker were not observed within 45 seconds")
        if [6, 5, 4] != [x for x, y in cells if y == 4][:3]:
            raise RuntimeError(f"legal arrival path differs from (6,4)->(5,4)->(4,4): {cells}")
        if chooser_event is None:
            raise RuntimeError("legal east reverse chooser marker missing")
        expected_reverse_fb = ENEMY_FB_ORIGIN + (4 - 12) * 4 + (4 - 12) * 1280
        if final["records"][0]["fb"] != expected_reverse_fb or final["records"][0]["substep"] != 0:
            raise RuntimeError("post-reverse actor framebuffer pointer does not match cell (4,4)")
        if not other_moved or not reverse_callback_other_moved:
            raise RuntimeError("no other actor moved during the same real enemy callback sequence")
        if final["records"][0]["direction"] != 1 or final["records"][0]["cell_x"] != 4:
            raise RuntimeError("incoming west actor did not retain legal east reverse at cell (4,4)")
        _require_markers({"actual-enemy-callback", "legal-east-reverse-selected", "concurrent-other-actor-moved",
                          "front-actor-pixels", "gate0-zero"},
                         observed | ({"concurrent-other-actor-moved"} if other_moved else set()) |
                         ({"front-actor-pixels"} if initial["front_pixels"] and final["front_pixels"] else set()))
        return {"status": "pass-runtime-marker-set", "phase": "legal-reversal-concurrent-mover",
                "fixture": PHASE_CONTRACTS["legal-reversal-concurrent-mover"],
                "gate_state_first20_hex": gates.hex(), "gate0": 0, "actor_cell_history": cells,
                "chooser_event": chooser_event, "other_actor_moved_in_callback_sequence": other_moved,
                "other_actor_moved_during_reverse_callback": reverse_callback_other_moved,
                "initial_front_pixels": initial["front_pixels"], "final_front_pixels": final["front_pixels"],
                "breakpoint_ids": ids, "identity": side["proof"], "monitor_audit": probe.audit()}
    finally:
        _close_probe(probe)


def _phase_natural_init(args: argparse.Namespace, deadline: float) -> dict[str, Any]:
    identity = json.loads(Path(args.identity).read_text(encoding="utf-8"))
    verify_identity(identity)
    probe = RuntimeProbe(args.host, args.port, deadline)
    try:
        main_symbols = _runtime_symbols(identity, "main")
        presentation_symbols = _runtime_symbols(identity, "presentation")
        mainloop = main_symbols["mainloop"]
        flow = presentation_symbols["presentation_flow_tick"]
        proof_marker, mainloop_bp, proof = _reach_verified_marker(
            probe, mainloop,
            lambda active: _verify_runtime_images(active, identity, need_enemy=False,
                                                  require_mapping=False))
        probe.clear_breakpoint(mainloop_bp)

        flow_bp = probe.set_breakpoint(flow)
        cold_flow_marker = _run_exact_marker(probe, flow_bp, flow,
                                             "cold initialization presentation_flow_tick", 12.0)
        build = Path(identity["build_dir"])
        presentation = (build / "ladybug-presentation-runtime.bin").read_bytes()
        live_presentation = _logical_read(probe, 0x1900, len(presentation))
        _require_identity_bytes(presentation, live_presentation, "presentation flow module at its live marker")
        initialized_flow_marker = _run_exact_marker(
            probe, flow_bp, flow, "post-initialization presentation_flow_tick", 12.0)
        initial_credit = _phys_read(probe, LOW_PAGE * PAGE_BYTES + presentation_symbols["PRES_CREDITS"], 1)[0]
        initial_screen = _phys_read(probe, LOW_PAGE * PAGE_BYTES + presentation_symbols["PRES_SCREEN"], 1)[0]
        initial_magic = _phys_read(probe, LOW_PAGE * PAGE_BYTES + presentation_symbols["PRES_MAGIC"], 1)[0]
        if (initial_credit != 0 or
                initial_screen != presentation_symbols["PRESENTATION_MAP_ATTRACT"] or
                initial_magic != 0xA5):
            raise RuntimeError(
                "first cold presentation tick did not initialize a zero-credit attract state: "
                f"credits={initial_credit}, screen={initial_screen}, magic={initial_magic:02X}")

        credit_ack = _inject_key(probe, 5, "press")
        credit_marker = _run_exact_marker(probe, flow_bp, flow, "credited presentation_flow_tick", 12.0)
        credits_after_coin = _phys_read(probe, LOW_PAGE * PAGE_BYTES + presentation_symbols["PRES_CREDITS"], 1)[0]
        screen_after_coin = _phys_read(probe, LOW_PAGE * PAGE_BYTES + presentation_symbols["PRES_SCREEN"], 1)[0]
        credit_release = _inject_key(probe, 5, "release")
        if credits_after_coin != 1 or screen_after_coin != presentation_symbols["PRESENTATION_MAP_HIGH_SCORE"]:
            raise RuntimeError(f"natural key-5 credit did not open credited high-score menu: credits={credits_after_coin}, screen={screen_after_coin}")

        probe.clear_breakpoint(flow_bp)

        rate = (_runtime_symbols(identity, "rate")
                if identity.get("side") == "candidate" else {})
        enemy = _runtime_symbols(identity, "enemy")
        init_entry = main_symbols["init_enemy"]
        shim = rate.get("rate_enemy_init_shim")
        enemy_init, first_tick = enemy["enemy_init_impl"], enemy["enemy_tick_impl"]

        def observe_init_sequence(expected_stage: int, prefix: str,
                                  first_marker: dict[str, Any] | None = None,
                                  first_bp: int | None = None) -> list[dict[str, Any]]:
            points = {"init_enemy": init_entry, "enemy_init_impl": enemy_init,
                      "first_enemy_tick": first_tick}
            if shim is not None:
                points["rate_enemy_init_shim"] = shim
            ids = {name: (first_bp if name == "init_enemy" and first_bp is not None
                          else probe.set_breakpoint(address))
                   for name, address in points.items()}
            observed: list[dict[str, Any]] = []
            sequence = ["init_enemy"]
            if shim is not None:
                sequence.append("rate_enemy_init_shim")
            sequence.extend(("enemy_init_impl", "first_enemy_tick"))
            for name in sequence:
                mark = (first_marker if name == "init_enemy" and first_marker is not None else
                        _run_exact_marker(probe, ids[name], points[name], f"{prefix} {name}", 12.0))
                assert mark is not None
                if name in {"enemy_init_impl", "first_enemy_tick"}:
                    if _logical_read(probe, 0xFFA0)[0] & 0x3F != LOW_PAGE:
                        raise RuntimeError(f"{prefix} {name} is not mapped through PAR0 page $38")
                    expected_enemy = (build / "ladybug-enemy-runtime.rom").read_bytes()
                    live_enemy = _read_spans(probe, LOW_PAGE, 0x0800, len(expected_enemy))
                    _require_identity_bytes(expected_enemy, live_enemy, f"{prefix} enemy module before marker interpretation")
                state = _low_snapshot(probe)
                sample: dict[str, Any] = {"marker": name, "pc": f"${mark['pc']:04X}", "state": state}
                if name == "init_enemy":
                    runtime_image = (build / "ladybug-runtime.rom").read_bytes()
                    expected_entry = runtime_image[init_entry - 0xC000:init_entry - 0xC000 + 3]
                    live_entry = _logical_read(probe, init_entry, 3)
                    _require_identity_bytes(expected_entry, live_entry, f"{prefix} resident init entry")
                    if state["stage"] != expected_stage:
                        raise RuntimeError(f"{prefix} init_enemy stage={state['stage']}, expected {expected_stage}")
                    sample["init_entry_hex"] = live_entry.hex()
                elif name == "rate_enemy_init_shim":
                    par5 = _logical_read(probe, 0xFFA5)[0] & 0x3F
                    expected_rate = (build / "ladybug-rate-helper.bin").read_bytes()
                    live_rate = _read_spans(probe, STATE_PAGE, 0x03B0, len(expected_rate))
                    _require_identity_bytes(expected_rate, live_rate, f"{prefix} page-$34 rate shim")
                    if par5 != STATE_PAGE:
                        raise RuntimeError(f"{prefix} rate shim entered with PAR5=${par5:02X}, expected $34")
                    sample.update({"PAR5": par5, "rate_helper_sha256": sha256_bytes(live_rate)})
                elif name == "enemy_init_impl":
                    sample.update({"enemy_module_sha256": sha256_bytes(live_enemy),
                                   "enemy_module_matches": True})
                    if identity.get("side") == "candidate":
                        bucket = state["rate_bucket"]
                        expected_addend = _rate_expected(state["stage"], bucket)
                        observed_rate = (state["rate_timer"], bucket, state["rate_frac"],
                                         state["rate_phase"], state["rate_addend"])
                        expected_rate = (96, 0, 0, 0, expected_addend)
                        if observed_rate != expected_rate:
                            raise RuntimeError(f"{prefix} rate reset differs at true init: {state}")
                        sample["rate_reset_matches"] = True
                else:
                    sample["records"] = _enemy_records(probe)
                probe.clear_breakpoint(ids[name])
                observed.append(sample)
            return observed

        init_start_bp = probe.set_breakpoint(init_entry)
        enter_ack = _inject_key(probe, 0x30, "press")
        enter_marker = _run_exact_marker(probe, init_start_bp, init_entry,
                                         "natural Part-1 init_enemy after Enter", 12.0)
        credits_after_start = _phys_read(probe, LOW_PAGE * PAGE_BYTES + presentation_symbols["PRES_CREDITS"], 1)[0]
        screen_after_start = _phys_read(probe, LOW_PAGE * PAGE_BYTES + presentation_symbols["PRES_SCREEN"], 1)[0]
        enter_release = _inject_key(probe, 0x30, "release")
        if (credits_after_start != 0 or
                screen_after_start != presentation_symbols["PRESENTATION_MAP_LEVEL_START"]):
            raise RuntimeError(f"Enter did not consume the credit into Part-1 level start: credits={credits_after_start}, screen={screen_after_start}")
        part1_markers = observe_init_sequence(1, "natural Part-1 entry",
                                             first_marker=enter_marker, first_bp=init_start_bp)

        normal_game = presentation_symbols["normal_game"]
        normal_game_bp = probe.set_breakpoint(normal_game)
        entry_history: list[dict[str, int]] = []
        for _ in range(64):
            _run_exact_marker(probe, normal_game_bp, normal_game, "player-entry gameplay dispatch", 3.0)
            state = _low_snapshot(probe)
            entry_history.append({key: state[key] for key in
                                  ("initial_entry_state", "player_cell_x", "player_cell_y")})
            if state["initial_entry_state"] == 0:
                break
        else:
            raise RuntimeError("natural player entry did not finish within 64 gameplay dispatches")
        if (state["player_cell_x"], state["player_cell_y"]) != (12, 18):
            raise RuntimeError(f"natural player entry ended at {(state['player_cell_x'], state['player_cell_y'])}, expected (12, 18)")
        probe.clear_breakpoint(normal_game_bp)

        before_fixture = _low_snapshot(probe)
        if before_fixture["stage"] != 1 or before_fixture["stage_pending"] != 0:
            raise RuntimeError(f"final-dot precondition is not active Part 1: {before_fixture}")
        _phys_write(probe, LOW_PAGE * PAGE_BYTES + 0x25, b"\x01")
        _phys_write(probe, LOW_PAGE * PAGE_BYTES + 0x33, b"\x00")
        fixture_state = _low_snapshot(probe)
        if fixture_state["dots_left"] != 1 or fixture_state["bonus_left"] != 0:
            raise RuntimeError(f"final-dot counter fixture readback differs: {fixture_state}")
        next_stage = main_symbols["next_stage"]
        next_stage_bp = probe.set_breakpoint(next_stage)
        up_ack = _inject_key(probe, 0x2B, "press")
        stage2_marker = _run_exact_marker(probe, next_stage_bp, next_stage,
                                          "real Part-2 next_stage after final dot", 12.0)
        up_release = _inject_key(probe, 0x2B, "release")
        stage2_pre = _low_snapshot(probe)
        if (stage2_pre["stage"] != 1 or stage2_pre["stage_pending"] == 0 or
                stage2_pre["dots_left"] != 0 or stage2_pre["bonus_left"] != 0):
            raise RuntimeError(f"real Part-2 transition did not follow the final dot: {stage2_pre}")
        probe.clear_breakpoint(next_stage_bp)
        part2_markers = observe_init_sequence(2, "natural Part-2 transition")

        return {"status": "pass-runtime-marker-set", "phase": "natural-init",
                "build_side": identity["side"],
                "cold_mainloop_marker": {"pc": f"${proof_marker['pc']:04X}", "identity": proof},
                "presentation_identity_sha256": sha256_bytes(live_presentation),
                "natural_credit_and_start": {
                    "credit_key": {"key": 5, "press_ack": credit_ack, "release_ack": credit_release,
                                   "credits_before": initial_credit, "credits_after": credits_after_coin,
                                   "screen_after": screen_after_coin},
                    "start_key": {"key": 0x30, "press_ack": enter_ack, "release_ack": enter_release,
                                  "credits_after": credits_after_start, "screen_after": screen_after_start,
                                  "init_enemy_marker": enter_marker},
                    "credits_before": initial_credit, "screen_before": initial_screen,
                    "magic_after_cold_init": initial_magic,
                    "presentation_markers": [cold_flow_marker, initialized_flow_marker, credit_marker]},
                "part1_natural_init_markers": part1_markers,
                "natural_player_entry_dispatches": entry_history,
                "final_dot_fixture": {"before": before_fixture, "readback": fixture_state,
                                      "writes_only": {"DOTS_LEFT": 1, "BONUS_LEFT": 0},
                                      "up_key": {"key": 0x2B, "press_ack": up_ack,
                                                 "release_ack": up_release},
                                      "next_stage_marker": stage2_marker,
                                      "before_next_stage_body": stage2_pre,
                                      "earned_maze_progression_skipped": True},
                "part2_natural_init_markers": part2_markers,
                "no_stage_pending_or_init_writes": True,
                "identity": proof, "monitor_audit": probe.audit()}
    finally:
        _close_probe(probe)


def _phase_natural_rate_progression(args: argparse.Namespace, deadline: float) -> dict[str, Any]:
    identity_path = Path(args.identity).resolve(strict=True)
    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    verify_identity(identity)
    side = identity.get("side")
    if side not in {"baseline", "candidate"}:
        raise ValueError("natural-rate-progression requires a baseline or candidate identity")
    probe = RuntimeProbe(args.host, args.port, deadline)
    try:
        build = Path(identity["build_dir"])
        main_symbols = _runtime_symbols(identity, "main")
        presentation_symbols = _runtime_symbols(identity, "presentation")
        enemy_symbols = _runtime_symbols(identity, "enemy")
        rate_symbols = (_runtime_symbols(identity, "rate") if side == "candidate" else {})
        tick = enemy_symbols["enemy_tick_impl"]
        marker, tick_bp, proof = _reach_verified_marker(
            probe, tick,
            lambda active: _verify_runtime_images(active, identity, need_enemy=True,
                                                  verify_staging=False, require_mapping=True))
        probe.clear_breakpoint(tick_bp)
        start_state = _low_snapshot(probe)
        if start_state["stage"] != 2:
            raise RuntimeError(f"natural-rate-progression requires the approved Part-2 stop; got stage {start_state['stage']}")

        expected_presentation = (build / "ladybug-presentation-runtime.bin").read_bytes()
        live_presentation = _logical_read(probe, 0x1900, len(expected_presentation))
        _require_identity_bytes(expected_presentation, live_presentation,
                                "presentation module before normal_game marker use")
        normal_game = presentation_symbols["normal_game"]
        normal_game_return = normal_game + 1
        normal_game_offset = normal_game - 0x1900
        if (normal_game_offset < 0 or normal_game_offset + 2 > len(expected_presentation) or
                expected_presentation[normal_game_offset:normal_game_offset + 2] != b"\x4F\x39"):
            raise RuntimeError("normal_game source bytes do not match the expected CLRA/RTS entry")
        live_entry_bytes = _logical_read(probe, normal_game, 2)
        _require_identity_bytes(expected_presentation[normal_game_offset:normal_game_offset + 2],
                                live_entry_bytes, "normal_game entry before player-entry marker use")
        if live_entry_bytes[1] != 0x39:
            raise RuntimeError("normal_game return marker is not an identity-verified RTS")
        next_stage = main_symbols["next_stage"]
        init_entry = main_symbols["init_enemy"]
        enemy_init, first_tick = enemy_symbols["enemy_init_impl"], tick
        rate_shim = rate_symbols.get("rate_enemy_init_shim")
        rate_helper = ((build / "ladybug-rate-helper.bin").read_bytes() if side == "candidate" else b"")
        enemy_module = (build / "ladybug-enemy-runtime.rom").read_bytes()
        runtime_image = (build / "ladybug-runtime.rom").read_bytes()

        transitions: list[dict[str, Any]] = []
        init_markers: list[dict[str, Any]] = []
        entry_history: list[dict[str, int]] = []
        stage_init_observations: list[dict[str, Any]] = []
        probe.phase_progress = {"starting_stage": 2, "current_stage": 2,
                                "completed_transitions": transitions,
                                "stage_init_observations": stage_init_observations,
                                "current_player_entry_samples": entry_history}

        def wait_for_player_entry(stage: int) -> tuple[dict[str, Any], list[dict[str, int]]]:
            # Break at the identity-verified RTS after normal_game's CLRA. Stepping
            # over RTS returns to the caller, unlike stopping repeatedly on CLRA.
            entry_bp = probe.set_breakpoint(normal_game_return)
            history: list[dict[str, int]] = []
            state: dict[str, Any] | None = None
            for _ in range(64):
                _run_exact_marker(probe, entry_bp, normal_game_return,
                                  f"Part-{stage} normal_game return/player-entry dispatch", 3.0)
                state = _low_snapshot(probe)
                row = {key: state[key] for key in
                       ("initial_entry_state", "player_cell_x", "player_cell_y", "stage", "stage_pending")}
                history.append(row)
                probe.phase_progress.update({"current_stage": stage,
                                             "current_player_entry_samples": history,
                                             "last_player_entry_state": row})
                if state["stage"] != stage:
                    raise RuntimeError(f"player-entry dispatch reached stage {state['stage']}, expected {stage}")
                if (state["initial_entry_state"] == 0 and
                        (state["player_cell_x"], state["player_cell_y"]) == (12, 18) and
                        state["stage_pending"] == 0):
                    break
            else:
                raise TimeoutError(f"Part-{stage} player entry did not complete within 64 normal_game dispatches")
            assert state is not None
            probe.clear_breakpoint(entry_bp)
            probe.phase_progress.update({"current_player_entry_samples": history,
                                         "player_entry_complete": True})
            return state, history

        def observe_stage_init(stage: int) -> list[dict[str, Any]]:
            points = {"init_enemy": init_entry, "enemy_init_impl": enemy_init,
                      "first_enemy_tick": first_tick}
            if rate_shim is not None:
                points["rate_enemy_init_shim"] = rate_shim
            ids = {name: probe.set_breakpoint(address) for name, address in points.items()}
            order = ["init_enemy"]
            if rate_shim is not None:
                order.append("rate_enemy_init_shim")
            order.extend(("enemy_init_impl", "first_enemy_tick"))
            observed: list[dict[str, Any]] = []
            for name in order:
                mark = _run_exact_marker(probe, ids[name], points[name],
                                         f"natural Part-{stage} {name}", 12.0)
                sample: dict[str, Any] = {"marker": name, "pc": f"${mark['pc']:04X}",
                                          "state": _low_snapshot(probe)}
                if name == "init_enemy":
                    expected_entry = runtime_image[init_entry - 0xC000:init_entry - 0xC000 + 3]
                    live_entry = _logical_read(probe, init_entry, 3)
                    _require_identity_bytes(expected_entry, live_entry,
                                            f"Part-{stage} resident init entry")
                    if sample["state"]["stage"] != stage:
                        raise RuntimeError(f"Part-{stage} init marker reports stage {sample['state']['stage']}")
                elif name == "rate_enemy_init_shim":
                    par5 = _logical_read(probe, 0xFFA5)[0] & 0x3F
                    live_rate = _read_spans(probe, STATE_PAGE, 0x03B0, len(rate_helper))
                    _require_identity_bytes(rate_helper, live_rate, f"Part-{stage} page-$34 rate shim")
                    if par5 != STATE_PAGE:
                        raise RuntimeError(f"Part-{stage} rate shim entered with PAR5=${par5:02X}, expected $34")
                    sample.update({"PAR5": par5, "rate_helper_sha256": sha256_bytes(live_rate)})
                else:
                    if _logical_read(probe, 0xFFA0)[0] & 0x3F != LOW_PAGE:
                        raise RuntimeError(f"Part-{stage} {name} is not mapped through PAR0 page $38")
                    live_enemy = _read_spans(probe, LOW_PAGE, 0x0800, len(enemy_module))
                    _require_identity_bytes(enemy_module, live_enemy, f"Part-{stage} enemy module")
                    if name == "enemy_init_impl" and stage == 7:
                        expected_spawner = {"box_index": 0, "box_timer": 3,
                                            "enemy_active": 0, "enemy_released": 0}
                        observed_spawner = {key: sample["state"][key]
                                            for key in expected_spawner}
                        if observed_spawner != expected_spawner:
                            raise RuntimeError(
                                f"natural Part-7 spawner reset differs: {observed_spawner}; "
                                f"expected {expected_spawner}")
                        sample["spawner_reset_matches"] = True
                    if name == "enemy_init_impl" and side == "candidate":
                        state = sample["state"]
                        expected_addend = _rate_expected(stage, state["rate_bucket"])
                        observed_rate = (state["rate_timer"], state["rate_bucket"],
                                         state["rate_frac"], state["rate_phase"], state["rate_addend"])
                        expected_rate = (96, 0, 0, 0, expected_addend)
                        if observed_rate != expected_rate:
                            raise RuntimeError(f"Part-{stage} rate reset mismatch: {state}")
                        sample["rate_reset_matches"] = True
                    if name == "first_enemy_tick":
                        sample["records"] = _enemy_records(probe)
                probe.clear_breakpoint(ids[name])
                observed.append(sample)
                stage_init_observations.append(sample)
                probe.phase_progress.update({"stage_init_marker": name,
                                             "stage_init_marker_state": sample["state"],
                                             "stage_init_observations": stage_init_observations})
            return observed

        for stage in range(2, 7):
            state, history = wait_for_player_entry(stage)
            entry_history.extend(history)
            if state["stage_pending"] != 0:
                raise RuntimeError(f"Part-{stage} final-dot fixture requires STAGE_PENDING=0")
            _phys_write(probe, LOW_PAGE * PAGE_BYTES + 0x25, b"\x01")
            _phys_write(probe, LOW_PAGE * PAGE_BYTES + 0x33, b"\x00")
            fixture_state = _low_snapshot(probe)
            probe.phase_progress.update({"final_dot_fixture_stage": stage,
                                         "final_dot_fixture_state": fixture_state,
                                         "writes_only": {"DOTS_LEFT": 1, "BONUS_LEFT": 0}})
            if (fixture_state["stage"] != stage or fixture_state["stage_pending"] != 0 or
                    fixture_state["dots_left"] != 1 or fixture_state["bonus_left"] != 0):
                raise RuntimeError(f"Part-{stage} final-dot fixture readback differs: {fixture_state}")
            next_bp = probe.set_breakpoint(next_stage)
            up_press = _inject_key(probe, 0x2B, "press")
            next_marker = _run_exact_marker(probe, next_bp, next_stage,
                                            f"real Part-{stage + 1} next_stage after final dot", 12.0)
            up_release = _inject_key(probe, 0x2B, "release")
            handoff_state = _low_snapshot(probe)
            probe.phase_progress.update({"next_stage_marker_pc": f"${next_marker['pc']:04X}",
                                         "handoff_state": handoff_state})
            if (handoff_state["stage"] != stage or handoff_state["stage_pending"] == 0 or
                    handoff_state["dots_left"] != 0 or handoff_state["bonus_left"] != 0):
                raise RuntimeError(f"Part-{stage}-to-{stage + 1} handoff state differs: {handoff_state}")
            probe.clear_breakpoint(next_bp)
            observed = observe_stage_init(stage + 1)
            init_markers.extend(observed)
            transitions.append({"from_stage": stage, "to_stage": stage + 1,
                                "player_entry_history": history,
                                "fixture_before_up": fixture_state,
                                "writes_only": {"DOTS_LEFT": 1, "BONUS_LEFT": 0},
                                "up_key": {"press_ack": up_press, "release_ack": up_release},
                                "next_stage_pc": f"${next_marker['pc']:04X}",
                                "handoff_state": handoff_state,
                                "init_markers": observed})
            probe.phase_progress.update({"completed_transitions": transitions,
                                         "current_stage": stage + 1,
                                         "current_transition": None,
                                         "current_player_entry_samples": [],
                                         "player_entry_complete": False,
                                         "latest_stage_init_markers": [m["marker"] for m in observed]})

        probe.phase_progress.update({"current_stage": 7, "current_transition": None})
        target_state, target_entry = wait_for_player_entry(7)
        entry_history.extend(target_entry)
        part7_reset = next((sample for sample in reversed(init_markers)
                            if sample["marker"] == "enemy_init_impl" and
                            sample["state"]["stage"] == 7), None)
        if side == "candidate":
            expected_addend = _rate_expected(7, 0)
            if part7_reset is None:
                raise RuntimeError("Part-7 true enemy-init rate-reset marker was not retained")
            reset_state = part7_reset["state"]
            observed_reset = (reset_state["rate_timer"], reset_state["rate_bucket"],
                              reset_state["rate_frac"], reset_state["rate_phase"],
                              reset_state["rate_addend"])
            expected_reset = (96, 0, 0, 0, expected_addend)
            if expected_addend == 0 or observed_reset != expected_reset or not part7_reset.get("rate_reset_matches"):
                raise RuntimeError(f"Part-7 true init rate reset differs: {observed_reset}, expected {expected_reset}")
            if target_state["stage"] != 7 or target_state["rate_addend"] != expected_addend:
                raise RuntimeError(f"Part-7 player-entry state lost the nonzero reset addend: {target_state}")
        observed_spawner = {key: target_state[key] for key in
                            ("box_index", "box_timer", "box_phase", "enemy_active", "enemy_released")}
        probe.phase_progress.update({"current_stage": 7, "player_entry_complete": True,
                                     "part7_true_init_rate_reset": (part7_reset if side == "candidate" else None),
                                     "part7_ready": True,
                                     "part7_ready_spawner_checkpoint": observed_spawner})
        return {"status": "pass-runtime-marker-set", "phase": "natural-rate-progression",
                "build_side": side, "target_stage": 7,
                "target_stage_first_nonzero_addend": (_rate_expected(7, 0) if side == "candidate" else None),
                "starting_part2_marker": {"pc": f"${marker['pc']:04X}", "state": start_state,
                                          "identity": proof},
                "stage_transitions": transitions,
                "stage_init_markers": init_markers,
                "player_entry_history": entry_history,
                "part7_rate_reset_at_true_enemy_init": (part7_reset if side == "candidate" else None),
                "part7_ready_state": target_state,
                "writes_only_per_transition": {"DOTS_LEFT": 1, "BONUS_LEFT": 0},
                "never_wrote_STAGE_or_STAGE_PENDING": True,
                "monitor_audit": probe.audit()}
    finally:
        _close_probe(probe)


def _phase_active_monitor_sentinel(args: argparse.Namespace, deadline: float) -> dict[str, Any]:
    identity = json.loads(Path(args.identity).read_text(encoding="utf-8"))
    verify_identity(identity)
    probe = RuntimeProbe(args.host, args.port, deadline)
    try:
        mainloop = _runtime_symbols(identity, "main")["mainloop"]
        marker, bp_id, proof = _reach_verified_marker(
            probe, mainloop,
            lambda active: _verify_runtime_images(active, identity, need_enemy=False,
                                                  require_mapping=False),
            wait_cap_seconds=12.0)
        return {"status": "pass-runtime-marker-set", "phase": "active-monitor-sentinel",
                "marker": "mainloop", "pc": f"${marker['pc']:04X}", "breakpoint_id": bp_id,
                "identity": proof, "monitor_audit": probe.audit()}
    finally:
        _close_probe(probe)


def authorize_dispatch(args: argparse.Namespace, identity_paths: list[Path], output: Path) -> dict[str, Any]:
    if output.exists():
        raise ValueError(f"refusing to overwrite existing runtime receipt: {output}")
    auth_path = Path(args.authorization).resolve(strict=True)
    auth = json.loads(auth_path.read_text(encoding="utf-8"))
    adapter_hash = sha256(Path(__file__).resolve())
    if auth.get("runtime_authorized") is not True:
        raise ValueError("runtime not started: dispatch receipt lacks runtime_authorized=true")
    if auth.get("parent_review_status") != "parent-reviewed-and-approved":
        raise ValueError("runtime not started: dispatch receipt is not parent-reviewed-and-approved")
    if auth.get("adapter_sha256") != adapter_hash:
        raise ValueError("runtime not started: dispatch receipt adapter SHA-256 differs")
    if auth.get("scenario_plan_sha256") != sha256(PLAN):
        raise ValueError("runtime not started: dispatch receipt scenario-plan SHA-256 differs")
    phase_deadline = PHASE_DEADLINES.get(args.phase, PHASE_DEADLINE_SECONDS)
    if auth.get("phase") != args.phase or auth.get("phase_deadline_seconds") != phase_deadline:
        raise ValueError(f"runtime not started: dispatch receipt does not authorize this exact {phase_deadline}-second phase")
    if args.phase not in auth.get("authorized_phases", []):
        raise ValueError("runtime not started: phase is not listed in authorized_phases")
    dep_path = Path(args.bug086_receipt).resolve(strict=True)
    dep = json.loads(dep_path.read_text(encoding="utf-8"))
    done, note = dependency_status(dep)
    if not done:
        raise ValueError(f"runtime not started: BUG-086 dependency is not actualDone: {note}")
    dep_hash = sha256(dep_path)
    if auth.get("bug086_receipt_sha256") != dep_hash:
        raise ValueError("runtime not started: BUG-086 receipt hash differs from dispatch receipt")
    identity_hashes: dict[str, str] = {}
    for path in identity_paths:
        identity = json.loads(path.read_text(encoding="utf-8"))
        verify_identity(identity)
        if identity.get("bug086_dependency", {}).get("actual_done") is not True:
            raise ValueError(f"runtime not started: {path} was not captured against BUG-086 actualDone")
        if identity["bug086_dependency"].get("receipt_sha256") != dep_hash:
            raise ValueError(f"runtime not started: {path} names a different BUG-086 receipt")
        identity_hashes[path.name] = sha256(path)
    if auth.get("identity_sha256_by_name") != identity_hashes:
        raise ValueError("runtime not started: current build identity hashes differ from dispatch receipt")
    prerequisite_hash = None
    if args.phase in {"natural-rate-progression", "candidate-horizontal-displacement"}:
        expected_phase = ("natural-init" if args.phase == "natural-rate-progression"
                          else "natural-rate-progression")
        if not args.prerequisite_receipt:
            raise ValueError(f"runtime not started: {args.phase} requires its passing {expected_phase} receipt")
        prerequisite_path = Path(args.prerequisite_receipt).resolve(strict=True)
        prerequisite = json.loads(prerequisite_path.read_text(encoding="utf-8"))
        if prerequisite.get("phase") != expected_phase or prerequisite.get("status") != "pass-runtime-marker-set":
            raise ValueError(f"runtime not started: prerequisite is not a passing {expected_phase} receipt")
        identity = json.loads(identity_paths[0].read_text(encoding="utf-8"))
        if prerequisite.get("build_side") != identity.get("side"):
            raise ValueError("runtime not started: prerequisite receipt belongs to a different build side")
        prior_auth = prerequisite.get("authorization", {})
        if (prior_auth.get("adapter_sha256") != adapter_hash or
                prior_auth.get("scenario_plan_sha256") != sha256(PLAN) or
                prior_auth.get("BUG086_receipt_sha256") != dep_hash or
                prior_auth.get("identity_sha256_by_name") != identity_hashes):
            raise ValueError(f"runtime not started: prerequisite {expected_phase} receipt is not pinned to the current plan and identity")
        if args.phase == "natural-rate-progression":
            markers = prerequisite.get("part2_natural_init_markers", [])
            if (not markers or markers[-1].get("marker") != "first_enemy_tick" or
                    markers[-1].get("state", {}).get("stage") != 2):
                raise ValueError("runtime not started: prerequisite natural-init did not stop at the Part-2 first enemy callback")
        else:
            ready_state = prerequisite.get("part7_ready_state", {})
            if (identity.get("side") != "candidate" or ready_state.get("stage") != 7 or
                    ready_state.get("rate_addend") != 0x33 or
                    prerequisite.get("never_wrote_STAGE_or_STAGE_PENDING") is not True):
                raise ValueError("runtime not started: prerequisite does not prove natural candidate Part-7 addend-$33 progression")
        prerequisite_hash = sha256(prerequisite_path)
        if auth.get("prerequisite_receipt_sha256") != prerequisite_hash:
            raise ValueError("runtime not started: prerequisite receipt hash differs from dispatch receipt")
    fixture_hash = hashlib.sha256(json.dumps(PHASE_CONTRACTS[args.phase], sort_keys=True,
                                              separators=(",", ":")).encode()).hexdigest()
    if auth.get("fixture_contract_sha256") != fixture_hash:
        raise ValueError("runtime not started: fixture contract differs from parent-reviewed dispatch receipt")
    return {"authorization_sha256": sha256(auth_path), "BUG086_receipt_sha256": dep_hash,
            "identity_sha256_by_name": identity_hashes, "adapter_sha256": adapter_hash,
            "scenario_plan_sha256": sha256(PLAN), "fixture_contract_sha256": fixture_hash,
            "prerequisite_receipt_sha256": prerequisite_hash,
            "dispatch": auth}


def cmd_live(args: argparse.Namespace) -> int:
    ACTIVE_PROBES.clear()
    output = Path(args.output).resolve()
    identity_paths = ([Path(args.baseline_identity).resolve(strict=True),
                       Path(args.candidate_identity).resolve(strict=True)]
                      if args.phase == "matched-displacement" else [Path(args.identity).resolve(strict=True)])
    auth = authorize_dispatch(args, identity_paths, output)
    phase_deadline = PHASE_DEADLINES.get(args.phase, PHASE_DEADLINE_SECONDS)
    deadline = time.monotonic() + phase_deadline
    started = time.monotonic()
    try:
        if args.phase == "active-monitor-sentinel":
            result = _phase_active_monitor_sentinel(args, deadline)
        elif args.phase == "matched-displacement":
            result = _phase_matched(args, deadline)
        elif args.phase == "candidate-horizontal-displacement":
            result = _phase_candidate_horizontal(args, deadline)
        elif args.phase == "freeze-saturated-thaw":
            result = _phase_freeze(args, deadline)
        elif args.phase == "legal-reversal-concurrent-mover":
            result = _phase_reversal(args, deadline)
        elif args.phase == "natural-init":
            result = _phase_natural_init(args, deadline)
        elif args.phase == "natural-rate-progression":
            result = _phase_natural_rate_progression(args, deadline)
        else:
            raise ValueError(f"unsupported phase: {args.phase}")
        result["phase_elapsed_seconds"] = round(time.monotonic() - started, 6)
        result["phase_deadline_seconds"] = phase_deadline
        result["phase_deadline_met"] = result["phase_elapsed_seconds"] <= phase_deadline
        result["runtime_launched"] = False
        result["emulator_attached"] = True
        result["runtime_acceptance"] = False
        result["authorization"] = {key: value for key, value in auth.items() if key != "dispatch"}
        if not result["phase_deadline_met"]:
            result["status"] = "fail-deadline"
    except Exception as exc:
        result = {"schema": "rsch014-ready-087-live-phase-v1", "status": "fail-runtime-marker",
                  "phase": args.phase, "phase_deadline_seconds": phase_deadline,
                  "phase_elapsed_seconds": round(time.monotonic() - started, 6),
                  "timeout_meaning": next(row["timeout_meaning"] for row in
                      json.loads(PLAN.read_text(encoding="utf-8"))["phases"] if row["id"] == args.phase),
                  "error": f"{type(exc).__name__}: {exc}", "runtime_launched": False,
                  "emulator_attached": bool(ACTIVE_PROBES), "runtime_acceptance": False,
                  "monitor_audit": [probe.audit() for probe in ACTIVE_PROBES],
                  "authorization": {key: value for key, value in auth.items() if key != "dispatch"}}
        if isinstance(exc, TimeoutError) and result["phase_elapsed_seconds"] <= phase_deadline:
            result["status"] = "fail-timeout"
    result["schema"] = "rsch014-ready-087-live-phase-v1"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"LIVE_PHASE status={result['status']} phase={args.phase} elapsed={result['phase_elapsed_seconds']:.3f}s output={output}")
    return 0 if result["status"] == "pass-runtime-marker-set" else 2


def self_test() -> None:
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    validate_plan(plan)
    cases: list[dict[str, Any]] = []

    def expect(name: str, action, accept: bool) -> None:
        try:
            action()
            passed = accept
            detail = "accepted"
        except Exception as exc:
            passed = not accept
            detail = f"{type(exc).__name__}: {exc}"
        cases.append({"name": name, "passed": passed, "expected": "accept" if accept else "reject",
                      "actual": detail})

    installed = {11: 0x15D5}
    good_stop = {"reason": "breakpoint", "bp_id": 11, "pc": 0x15D5}
    good_receipt = {"method": "run", "request_id": 69, "outcome": "ok",
                    "response_envelope": {"id": 69, "result": {"ok": True}}}
    expect("run acknowledgement accepted", lambda: _validate_run_ack({"ok": True}), True)
    expect("run acknowledgement missing marker rejected", lambda: _validate_run_ack({}), False)
    expect("adjacent run-wait IDs accepted", lambda: _validate_wait_sequence(69, 70), True)
    expect("stale run-wait ID rejected", lambda: _validate_wait_sequence(69, 71), False)
    expect("correlated run response accepted", lambda: _validate_call_receipt(good_receipt, "run", 69, {"ok": True}), True)
    expect("wrong live response identity rejected", lambda: _validate_call_receipt(good_receipt, "run", 68, {"ok": True}), False)
    expect("exact marker ID and PC accepted", lambda: _classify_stop(good_stop, installed), True)
    expect("wrong marker ID rejected", lambda: _classify_stop({"reason": "breakpoint", "bp_id": 9, "pc": 0x15D5}, installed), False)
    expect("wrong marker PC rejected", lambda: _classify_stop({"reason": "breakpoint", "bp_id": 11, "pc": 0x15D6}, installed), False)
    expect("timeout is not a marker", lambda: (_classify_stop({"reason": "timeout"}, installed),
                                                  _require_markers({"enemy-callback"}, set())), False)
    expect("durable step stop accepts exact reason and PC",
           lambda: _classify_step_stop({"reason": "step", "pc": 0x15D6})["pc"] == 0x15D6, True)
    expect("breakpoint is not accepted as a completed single step",
           lambda: _classify_step_stop({"reason": "breakpoint", "pc": 0x15D6, "bp_id": 11}), False)
    expect("step timeout is not accepted as a halted state",
           lambda: _classify_step_stop({"reason": "timeout"})["status"] == "timeout", True)
    expect("missing scenario marker rejected", lambda: _require_markers({"callback", "front-pixel"}, {"callback"}), False)
    expect("wrong live bytes rejected", lambda: _require_identity_bytes(b"\xBD\xA3\xC5", b"\xBD\xA3\xC4", "rate callsite"), False)
    expect("matching live bytes accepted", lambda: _require_identity_bytes(b"\xBD\xA3\xC5", b"\xBD\xA3\xC5", "rate callsite"), True)
    expect("zero per-callback frame deltas are valid when the full window advances",
           lambda: _require_aggregate_vbord_progress([0, 2, 0, 2]) == 4, True)
    expect("a freeze window with no raw frame progress is rejected",
           lambda: _require_aggregate_vbord_progress([0, 0]), False)
    actor_start = {"active": 0x61, "direction": 0, "fb": 0x4000, "substep": 0,
                   "cell_x": 12, "cell_y": 12}

    def actor_match_case(candidate_record: dict[str, Any], expected_slots: list[int]) -> None:
        empty = {"active": 0, "direction": 0, "fb": 0, "substep": 0, "cell_x": 0, "cell_y": 0}
        left = {"records": [actor_start, empty, empty, empty]}
        right = {"records": [candidate_record, empty, empty, empty]}
        actual = _matched_enemy_slots(left, right, "vertical")
        if actual != expected_slots:
            raise AssertionError(f"matched slots {actual} != expected {expected_slots}")

    expect("same active slot/type matches despite cell, position and substep changes",
           lambda: actor_match_case({**actor_start, "fb": 0x40A0, "substep": 1,
                                     "cell_x": 13}, [0]), True)
    expect("different active actor type does not match",
           lambda: actor_match_case({**actor_start, "active": 0x62}, []), True)
    expect("different direction does not match",
           lambda: actor_match_case({**actor_start, "direction": 2}, []), True)
    expect("unsupported movement axis is rejected",
           lambda: _matched_enemy_slots({"records": [actor_start] * 4},
                                        {"records": [actor_start] * 4}, "diagonal"), False)
    expect("same slot/type remains continuous while measured pose changes",
           lambda: _assert_actor_continuity(actor_start, {**actor_start, "fb": 0x40A0,
                                                           "substep": 1, "cell_x": 13}, "candidate"), True)
    expect("inactive matched slot rejects continuity",
           lambda: _assert_actor_continuity(actor_start, {**actor_start, "active": 0}, "candidate"), False)
    expect("replaced actor type rejects continuity",
           lambda: _assert_actor_continuity(actor_start, {**actor_start, "active": 0x62}, "candidate"), False)
    nav_test = [[0] * 24 for _ in range(24)]
    gates_test = [[0] * 24 for _ in range(24)]
    for x in range(2, 6):
        nav_test[12][x] = 0x02
    east_record = {"active": 0x61, "direction": 1, "cell_x": 2, "cell_y": 12, "substep": 1}
    expect("four-cell east route supplies exactly 30px after substep offset",
           lambda: _horizontal_runway_pixels(east_record, nav_test, gates_test) == 30, True)
    expect("horizontal route below the 30px minimum is rejected",
           lambda: _horizontal_runway_pixels({**east_record, "substep": 2}, nav_test, gates_test) <
                   HORIZONTAL_MIN_RUNWAY_PIXELS, True)
    expect("gate-owned target terminates authored straight route",
           lambda: _horizontal_runway_pixels(east_record, nav_test,
                                             [[1 if (x, y) == (4, 12) else 0 for x in range(24)]
                                              for y in range(24)]) == 16, True)
    expect("den-exception rows are excluded from static route proof",
           lambda: _horizontal_runway_pixels({**east_record, "cell_y": 10}, nav_test, gates_test) == 0, True)
    def assert_counter_delta(current: int, previous: int, expected: int) -> None:
        actual = _counter_delta16(current, previous)
        if actual != expected:
            raise AssertionError(f"16-bit counter delta {actual} != expected {expected}")

    expect("raw Vbord counter may remain unchanged for one enemy callback",
           lambda: assert_counter_delta(0x1234, 0x1234, 0), True)
    expect("raw Vbord counter delta handles 16-bit wrap",
           lambda: assert_counter_delta(1, 0xFFFF, 2), True)
    rate_code = bytes.fromhex("7a029b2619863cb7")
    audio_code = bytes.fromhex("260a7da4af270586")
    expect("page34 rate marker requires exact helper bytes",
           lambda: _classify_rate_marker(STATE_PAGE, rate_code, rate_code, audio_code) == "rate_tick", True)
    expect("page3d logical collision is classified as audio alias",
           lambda: _classify_rate_marker(AUDIO_PAGE, audio_code, rate_code, audio_code) == "audio_alias", True)
    expect("page34 audio bytes rejected as rate marker",
           lambda: _classify_rate_marker(STATE_PAGE, audio_code, rate_code, audio_code), False)
    expect("page3d rate bytes rejected as audio alias",
           lambda: _classify_rate_marker(AUDIO_PAGE, rate_code, rate_code, audio_code), False)
    expect("unknown PAR5 at shared logical address rejected",
           lambda: _classify_rate_marker(0x35, rate_code, rate_code, audio_code), False)
    expect("movement oracle matches phase-zero policy",
           lambda: _movement_admissions(36, 7, 0) == 21, True)
    expect("movement oracle preserves phase one across carries",
           lambda: _movement_admissions(36, 7, 1) == 22, True)
    expect("movement oracle rejects invalid phase",
           lambda: _movement_admissions(36, 7, 2), False)

    def rate_marker_alias_replay() -> bool:
        address = 0xA010
        helper = bytes(range(16)) + rate_code + bytes(range(24))
        audio = bytes(16) + audio_code + bytes(range(24))
        events = [
            {"page": AUDIO_PAGE, "code": audio_code},
            {"page": STATE_PAGE, "code": rate_code},
        ]

        class FakeRateMarkerProbe:
            def __init__(self):
                self.event_index = 0
                self.next_id = 1
                self.installed: dict[int, int] = {}
                self.cleared: list[int] = []

            def set_breakpoint(self, pc: int) -> int:
                ident = self.next_id
                self.next_id += 1
                self.installed[ident] = pc
                return ident

            def clear_breakpoint(self, ident: int) -> None:
                self.cleared.append(ident)
                self.installed.pop(ident)

            def run_until_marker(self, wait_cap_seconds: float = 44.0):
                event = events[self.event_index]
                self.event_index += 1
                ident, pc = next(iter(self.installed.items()))
                return {"bp_id": ident, "pc": pc, "status": "breakpoint", "marker": True}

            def call(self, method: str, params: dict[str, Any] | None = None, cap: float = 2.0):
                event = events[self.event_index - 1]
                if method == "read_gime_state":
                    pars = [0] * 8
                    pars[5] = event["page"]
                    return {"mmu_task": 0, "pars": {"task0": pars}}
                if method == "read_memory":
                    if params.get("space") == "physical":
                        expected_address = event["page"] * PAGE_BYTES + address - 0xA000
                        if params["addr"] != expected_address:
                            raise AssertionError("physical marker read used the wrong PAR5 page")
                    if params["length"] != len(event["code"]):
                        raise AssertionError("marker read used the wrong byte span")
                    return {"data": event["code"].hex()}
                raise AssertionError(f"unexpected marker replay call {method}")

        with tempfile.TemporaryDirectory() as temp_dir:
            build = Path(temp_dir)
            (build / "ladybug-rate-helper.bin").write_bytes(helper)
            (build / "ladybug-audio-runtime.bin").write_bytes(audio)
            (build / "source-build-receipt.json").write_text(json.dumps({
                "artifacts": {"ladybug-audio-runtime.bin": sha256_bytes(audio)}}), encoding="utf-8")
            identity = {"build_dir": str(build), "maps": {"rate": {"symbols": {
                "rate_reset": 0xA000, "rate_tick": address}}}}
            fake = FakeRateMarkerProbe()
            hit = _candidate_rate_marker(fake, address, identity)
            return (hit["PAR5"] == STATE_PAGE and hit["mapped_bytes_hex"] == rate_code.hex()
                    and len(hit["ignored_audio_aliases"]) == 1
                    and hit["ignored_audio_aliases"][0]["PAR5"] == AUDIO_PAGE
                    and fake.cleared == [1] and fake.installed == {2: address})

    expect("byte-proven audio alias is skipped before the true rate marker",
           lambda: rate_marker_alias_replay(), True)
    expect("45-second deadline accepted", lambda: validate_plan(plan), True)
    paired_base = {"source_revision": "integrated-commit-abc", "side": "baseline", "profile": "complete-ad1-keyboard",
                   "assignment_baseline_commit": "approved-base-commit"}
    paired_candidate = {"source_revision": "integrated-commit-abc", "side": "candidate", "profile": "complete-ad1-keyboard",
                        "assignment_baseline_commit": "approved-base-commit"}
    mismatched_candidate = {**paired_candidate, "source_revision": "different-commit-def"}
    missing_revision_candidate = {**paired_candidate, "source_revision": ""}
    whitespace_revision_candidate = {**paired_candidate, "source_revision": "   "}
    expect("paired identities with same source revision accepted",
           lambda: _assert_pair_source_revision(paired_base, paired_candidate), True)
    expect("paired identities with different source revisions rejected",
           lambda: _assert_pair_source_revision(paired_base, mismatched_candidate), False)
    expect("paired identity missing source revision rejected",
           lambda: _assert_pair_source_revision(paired_base, missing_revision_candidate), False)
    expect("paired identity blank source revision rejected",
           lambda: _assert_pair_source_revision(paired_base, whitespace_revision_candidate), False)
    expect("paired identities share approved assignment baseline",
           lambda: _assert_assignment_baseline_matches(
               paired_base, paired_candidate, "approved-base-commit"), True)
    expect("paired identities reject changed assignment baseline",
           lambda: _assert_assignment_baseline_matches(
               paired_base, {**paired_candidate, "assignment_baseline_commit": "other-base"},
               "approved-base-commit"), False)
    if not all(case["passed"] for case in cases):
        raise AssertionError(json.dumps(cases, indent=2))
    # Fractional carry arithmetic: two-pixel source step; one-pixel endpoint tolerance.
    for n in range(1, 33):
        for carries in range(n + 1):
            for starting_phase in (0, 1):
                admissions = _movement_admissions(n, carries, starting_phase)
                pixels = 2 * admissions
                assert abs(pixels - (n + carries)) <= 1
    assert all(p["deadline_seconds"] <= 45 for p in plan["phases"])
    focused = _focused_publication_tests()
    step_handoff = _single_step_handoff_test()
    print(f"SELFTEST PASS plan_schema=1 phases={len(plan['phases'])} guard_cases={len(cases)} arithmetic_cases=560 runtime=not-run")
    print(f"FOCUSED_STARTUP PASS cases={focused} source_stage_destination=checked cold_start_order=checked runtime=not-run")
    print(f"STEP_HANDOFF PASS cases={step_handoff} durable_step_stop=checked halted_before_read=checked")


def _focused_publication_tests() -> int:
    payload = bytes((i * 37 + 11) & 0xFF for i in range(BANK1_USABLE_BYTES))
    runtime_image = payload + bytes([0xFF]) * (PAGE_BYTES * 2 - BANK1_USABLE_BYTES)
    changed_stage = bytearray(payload)
    changed_stage[0x123] ^= 1
    changed_destination = bytearray(payload)
    changed_destination[0x234] ^= 1

    def run_probe(state: dict[str, Any]):
        class FakeClient:
            next_id = 1

        probe = object.__new__(RuntimeProbe)
        probe.client = FakeClient()
        probe.deadline = time.monotonic() + 10.0
        probe.installed = {1: 0xC456}
        probe.last_stop = None
        probe.last_calls = []
        calls: list[str] = []
        run_state_reads = 0

        def call(method: str, params: Any = None, cap: float = 2.0):
            nonlocal run_state_reads
            request_id = probe.client.next_id
            probe.client.next_id += 1
            calls.append(method)
            if method == "get_run_state":
                run_state_reads += 1
                result = (state if run_state_reads == 1 else
                          {"state": "halted", "last_stop_reason": "step", "last_stop_pc": 0xC124})
            elif method == "step_instruction":
                result = {"ok": True, "n": 1}
            elif method == "read_registers":
                result = {"pc": 0xC124}
            elif method == "run":
                result = {"ok": True}
            elif method == "wait_for_stop":
                result = ({"reason": "step", "pc": 0xC124}
                          if params == {"timeout_ms": 1750} else
                          {"reason": "breakpoint", "bp_id": 1, "pc": 0xC456})
            else:
                raise AssertionError(f"unexpected monitor method {method}")
            probe.last_calls.append({"request_id": request_id, "method": method, "outcome": "ok",
                                     "response_envelope": {"id": request_id, "result": result}})
            return result

        probe.call = call
        return probe.run_until_marker(), calls

    cases: list[tuple[str, Any, bool]] = [
        ("exact source-stage-destination accepted",
         lambda: (_verify_bank1_source_staging(payload, runtime_image, payload),
                  _verify_bank1_staging_destination(payload, payload)), True),
        ("runtime artifact mismatch rejected",
         lambda: _verify_bank1_source_staging(payload, bytes([0x00]) + runtime_image[1:], payload), False),
        ("staging mismatch rejected",
         lambda: _verify_bank1_source_staging(payload, runtime_image, bytes(changed_stage)), False),
        ("destination mismatch rejected",
         lambda: _verify_bank1_staging_destination(payload, bytes(changed_destination)), False),
        ("short destination rejected",
         lambda: _verify_bank1_staging_destination(payload, payload[:-1]), False),
        ("cold halt-on-start has no prior stop to step",
         lambda: run_probe({"state": "halted"})[1] ==
                 ["get_run_state", "run", "wait_for_stop"], True),
        ("warm prior breakpoint steps past its PC before running",
         lambda: run_probe({"state": "halted", "last_stop_reason": "breakpoint",
                            "last_stop_pc": 0xC123, "last_stop_bp_id": 9})[1] ==
                 ["get_run_state", "step_instruction", "wait_for_stop", "get_run_state",
                  "read_registers", "run", "wait_for_stop"], True),
        ("incomplete prior breakpoint record rejected",
         lambda: run_probe({"state": "halted", "last_stop_reason": "breakpoint",
                            "last_stop_pc": 0xC123}), False),
    ]
    passed = 0
    failures = []
    for name, action, accept in cases:
        try:
            action()
            ok = accept
            detail = "accepted"
        except Exception as exc:
            ok = not accept
            detail = f"{type(exc).__name__}: {exc}"
        if ok:
            passed += 1
        else:
            failures.append({"name": name, "expected": "accept" if accept else "reject", "actual": detail})

    events: list[str] = []

    class FakeProbe:
        halted = True

        def set_breakpoint(self, address: int) -> int:
            events.append(f"breakpoint:${address:04X}")
            return 7

        def run_until_marker(self, wait_cap_seconds: float = 44.0) -> dict[str, int]:
            self.halted = False
            events.append("natural-run")
            return {"bp_id": 7, "pc": 0xC123}

    def verify_after_run(probe: FakeProbe) -> dict[str, bool]:
        if probe.halted:
            raise AssertionError("resident image verification ran before cold startup")
        events.append("source-stage-destination-and-mapping-read")
        return {"verified": True}

    try:
        _reach_verified_marker(FakeProbe(), 0xC123, verify_after_run)
        expected_events = ["breakpoint:$C123", "natural-run", "source-stage-destination-and-mapping-read"]
        if events != expected_events:
            raise AssertionError(f"resident startup verification order differs: {events}")
        passed += 1
    except Exception as exc:
        failures.append({"name": "cold-start precedes resident reads", "actual": f"{type(exc).__name__}: {exc}"})

    rejected_events: list[str] = []

    class WrongMarkerProbe:
        def set_breakpoint(self, address: int) -> int:
            rejected_events.append(f"breakpoint:${address:04X}")
            return 8

        def run_until_marker(self, wait_cap_seconds: float = 44.0) -> dict[str, int]:
            rejected_events.append("natural-run")
            return {"bp_id": 8, "pc": 0xC124}

    def verify_after_wrong_marker(_probe) -> dict[str, bool]:
        rejected_events.append("unexpected-resident-read")
        return {"verified": True}

    try:
        _reach_verified_marker(WrongMarkerProbe(), 0xC123, verify_after_wrong_marker)
        raise AssertionError("wrong marker was accepted")
    except RuntimeError:
        if rejected_events != ["breakpoint:$C123", "natural-run"]:
            failures.append({"name": "wrong marker rejected before resident reads",
                             "actual": f"unexpected event order: {rejected_events}"})
        else:
            passed += 1
    if failures:
        raise AssertionError(json.dumps(failures, indent=2))
    return passed


def _single_step_handoff_test() -> int:
    probe = object.__new__(RuntimeProbe)

    class FakeClient:
        next_id = 1

    probe.client = FakeClient()
    probe.deadline = time.monotonic() + 10.0
    probe.installed = {9: 0xC456}
    probe.last_stop = None
    probe.last_marker_event = None
    probe.calls = 0
    probe.call_hash = hashlib.sha256()
    probe.last_calls = []
    probe.phase_progress = None
    events: list[str] = []

    def fake_call(method: str, params: dict[str, Any] | None = None,
                  cap: float = 2.0) -> dict[str, Any]:
        request_id = probe.client.next_id
        probe.client.next_id += 1
        events.append(method)
        if method == "get_run_state":
            result = ({"state": "halted", "last_stop_reason": "breakpoint",
                       "last_stop_pc": 0xC123, "last_stop_bp_id": 7}
                      if probe.last_stop is None else
                      {"state": "halted", "last_stop_reason": "step",
                       "last_stop_pc": 0xC124})
        elif method == "step_instruction":
            result = {"ok": True, "n": 1}
        elif method == "wait_for_stop" and params == {"timeout_ms": 1750}:
            result = {"reason": "step", "pc": 0xC124}
        elif method == "read_registers":
            result = {"pc": 0xC124}
        elif method == "run":
            result = {"ok": True}
        elif method == "wait_for_stop":
            result = {"reason": "breakpoint", "bp_id": 9, "pc": 0xC456}
        else:
            raise AssertionError(f"unexpected monitor method {method}: {params}")
        probe.last_calls.append({"request_id": request_id, "method": method, "outcome": "ok",
                                 "response_envelope": {"id": request_id, "result": result}})
        return result

    probe.call = fake_call
    marker = probe.run_until_marker()
    expected = ["get_run_state", "step_instruction", "wait_for_stop", "get_run_state",
                "read_registers", "run", "wait_for_stop"]
    if events != expected or marker != {"status": "breakpoint", "marker": True,
                                       "bp_id": 9, "pc": 0xC456}:
        raise AssertionError(f"single-step stop ordering or next marker differs: {events}, {marker}")
    return 1


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)
    capture = sub.add_parser("capture", help="hash a current assigned build and resolve its maps")
    capture.add_argument("--side", choices=("baseline", "candidate"), required=True)
    capture.add_argument("--profile", choices=("complete-ad1-keyboard", "complete-ad1-joystick"), required=True)
    capture.add_argument("--build-dir", required=True)
    capture.add_argument("--source-revision", required=True,
                         help="integrated source commit or exact dispatch revision supplied by owner")
    capture.add_argument("--assignment-baseline-commit",
                         help="approved baseline commit for the comparison; defaults to --source-revision")
    capture.add_argument("--bug086-receipt",
                         help="actual BUG-086 completion receipt; required for a future dispatchable identity")
    capture.add_argument("--output", required=True)
    capture.set_defaults(func=cmd_capture)
    phase = sub.add_parser("plan", help="verify paired current artifacts and emit resolved phase plan")
    phase.add_argument("--baseline-identity", required=True)
    phase.add_argument("--candidate-identity", required=True)
    phase.add_argument("--bug086-receipt", required=True)
    phase.add_argument("--output", required=True)
    phase.set_defaults(func=cmd_plan)
    live = sub.add_parser("live", help="execute one separately bounded phase by attaching to existing monitor(s)")
    live.add_argument("--phase", choices=sorted(PHASES), required=True)
    live.add_argument("--authorization", required=True)
    live.add_argument("--bug086-receipt", required=True)
    live.add_argument("--prerequisite-receipt")
    live.add_argument("--output", required=True)
    live.add_argument("--identity")
    live.add_argument("--host", default="127.0.0.1")
    live.add_argument("--port", type=int)
    live.add_argument("--baseline-identity")
    live.add_argument("--candidate-identity")
    live.add_argument("--baseline-host", default="127.0.0.1")
    live.add_argument("--baseline-port", type=int)
    live.add_argument("--candidate-host", default="127.0.0.1")
    live.add_argument("--candidate-port", type=int)
    live.add_argument("--axis", choices=("horizontal", "vertical"), default="vertical")
    live.set_defaults(func=cmd_live)
    sub.add_parser("self-test", help="validate marker refusals, identity guards, static plan and oracle; no monitor import").set_defaults(
        func=lambda _args: (self_test() or 0))
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "live":
            if args.phase == "matched-displacement":
                required = ("baseline_identity", "candidate_identity", "baseline_port", "candidate_port")
                missing = [name for name in required if getattr(args, name) is None]
                if not missing and (args.baseline_host, args.baseline_port) == (args.candidate_host, args.candidate_port):
                    raise ValueError("matched-displacement requires two distinct already-running monitor endpoints")
            else:
                required = ["identity", "port"]
                if args.phase in {"natural-rate-progression", "candidate-horizontal-displacement"}:
                    required.append("prerequisite_receipt")
                missing = [name for name in required if getattr(args, name) is None]
            if missing:
                raise ValueError("live command is missing phase arguments: " + ", ".join(missing))
            if any(not isinstance(port, int) or not 1 <= port <= 65535 for port in
                   ([args.baseline_port, args.candidate_port] if args.phase == "matched-displacement" else [args.port])):
                raise ValueError("monitor ports must be in the range 1..65535")
        return int(args.func(args))
    except (OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
