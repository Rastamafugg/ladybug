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
    "source-build-receipt.json",
)
REQUIRED_SYMBOLS = {
    "main": ("mainloop", "ad_dispatch_work", "init_enemy", "enemy_tick", "next_stage",
             "ENEMY_MODULE_INIT", "INITIAL_ENTRY_STATE", "STAGE", "ENEMY_TABLE",
             "ENEMY_ACTIVE", "DEATH_STATE", "FREEZE_TIMER", "ENEMY_MOVE"),
    "enemy": ("enemy_tick_impl", "enemy_init_impl", "ecd_blocked", "ecd_choose",
              "ENEMY_TABLE", "ENEMY_ACTIVE", "DEATH_STATE",
              "FREEZE_TIMER", "ENEMY_MOVE"),
    "rate": ("rate_reset", "rate_tick", "rate_select", "rate_enemy_init_shim", "rt_freeze_gate",
             "rt_accumulate", "RATE_TIMER", "RATE_BUCKET", "RATE_FRAC",
             "RATE_ADDEND", "RATE_PHASE", "FREEZE_TIMER", "STAGE"),
    "e2": ("efn_cache_guard", "enemy_page34_end", "ENEMY_MODULE_BUILD_CACHE", "ENEMY_TABLE", "STAGE"),
    "active": ("enemy_tick", "INITIAL_ENTRY_STATE"),
}
LOCKED_SHA256 = {
    "ladybug-rate-helper.bin": "609e0e8199a17c5d9a6bf35f7a3f0cddeb8ba029bdb5b8fa6bf2eed6b9efc00c",
    "ladybug-enemy-helper-page34.bin": "057e2803eac24aebb1447d43614fd4aaf67518d933f08d3f128627e9aeb26526",
    "ladybug-adaptive-banked.bin": "3827719dd6d237bd994e072748ef9756a2b113872b897ab561574655d8f590ab",
    "ladybug-adaptive-active.s": "5b662e01cb75841eb03790327c2ad12ecb6cbfdcfa5cb871d1f67efd95b78241",
}
PHASES = {
    "matched-displacement", "freeze-saturated-thaw", "legal-reversal-concurrent-mover", "natural-init",
}
PHASE_DEADLINE_SECONDS = 45
PAGE_BYTES = 0x2000
LOW_PAGE = 0x38
STATE_PAGE = 0x34
RATE_STATE = 0x029B
FREEZE_TIMER = 0x005B
FRAMES = 0x0002
FB_SIM_SEQ = 0x0094
FB_FRONT_ID = 0x008F
GIME_VOFF1 = 0xFF9D
ENEMY_TABLE = 0xA470
GATE_STATE = 0xA240
VISIBLE_START = 0x2000
VISIBLE_BYTES = 30720
ENEMY_FB_ORIGIN = 0x57EC
PHASE_CONTRACTS = {
    "matched-displacement": {"fixture": "natural legal straight segment on paired running builds", "writes": []},
    "freeze-saturated-thaw": {"fixture": "adapter-pinned rate boundary values plus actual callbacks; enemy and framebuffer ownership untouched", "writes": ["$004D", "$005B", "$029B-$029F"]},
    "legal-reversal-concurrent-mover": {"fixture": "actor 0 arrives west through (6,4)->(5,4)->(4,4), gate 0 remains 0; another existing active actor moves", "writes": []},
    "natural-init": {"fixture": "natural next_stage/init transition", "writes": []},
}
ACTIVE_PROBES: list["RuntimeProbe"] = []


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
    expected = {"matched-displacement", "freeze-saturated-thaw", "legal-reversal-concurrent-mover", "natural-init"}
    if {p.get("id") for p in phases} != expected:
        raise ValueError("phase plan must contain exactly the four assigned scenarios")
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
    identity["assignment_baseline_commit"] = "4d9ce9b521eaeae0b71a17c6a1f6516bd4503b32"
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
    handlers_attached = True
    plan["dispatchable"] = bool(done and paired_receipts_match and handlers_attached)
    plan["dispatch_gates"] = {
        "BUG086_actualDone": done,
        "both_builds_captured_against_same_receipt": paired_receipts_match,
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
            source_identity = candidate if side == "candidate" else baseline
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
    print(f"PLAN status={'dispatchable' if plan['dispatchable'] else 'dependency-blocked'} phases=4 output={output}")
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
        raise ValueError("wait_for_stop must immediately follow the acknowledged run call")


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


class RuntimeProbe:
    """Synchronous monitor adapter using the repository's existing MonitorClient."""

    def __init__(self, host: str, port: int, deadline: float):
        self.deadline = deadline
        self.installed: dict[int, int] = {}
        self.last_stop: dict[str, Any] | None = None
        self.calls = 0
        self.call_hash = hashlib.sha256()
        self.last_calls: list[dict[str, Any]] = []
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

    def run_until_marker(self) -> dict[str, Any]:
        assert self.client is not None
        if not self.installed:
            raise RuntimeError("no acknowledged breakpoint is installed")
        if self.last_stop is not None:
            prior_pc = self.last_stop["pc"]
            self.call("step_instruction", {"n": 1}, 1.0)
            regs = self.call("read_registers", None, 1.0)
            if regs.get("pc") == prior_pc:
                raise RuntimeError(f"single-step did not pass prior marker ${prior_pc:04X}")
        run_id = self.client.next_id
        run_result = self.call("run", None, 1.0)
        _validate_run_ack(run_result)
        _validate_call_receipt(self.last_calls[-1], "run", run_id, run_result)
        wait_id = self.client.next_id
        _validate_wait_sequence(run_id, wait_id)
        wait_seconds = self.left(40.0)
        wait_result = self.call("wait_for_stop", {
            "timeout_ms": max(1, int((wait_seconds - 0.25) * 1000))}, wait_seconds)
        _validate_call_receipt(self.last_calls[-1], "wait_for_stop", wait_id, wait_result)
        classification = _classify_stop(wait_result, self.installed)
        if classification["status"] == "timeout":
            raise TimeoutError("wait_for_stop returned reason=timeout; required marker was not observed")
        self.last_stop = classification
        return classification

    def close(self) -> None:
        if self.client is not None:
            self.client.close()
            self.client = None

    def audit(self) -> dict[str, Any]:
        return {"monitor_call_count": self.calls, "monitor_call_ledger_sha256": self.call_hash.hexdigest(),
                "last_monitor_calls": self.last_calls}


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


def _verify_runtime_images(probe: RuntimeProbe, identity: dict[str, Any],
                           need_enemy: bool = True, require_mapping: bool = True) -> dict[str, Any]:
    build = Path(identity["build_dir"])
    resident = (build / "ladybug-runtime.rom").read_bytes()
    live_resident = _read_spans(probe, 0x3E, 0, len(resident))
    _require_identity_bytes(resident, live_resident, "resident runtime")
    par6 = _logical_read(probe, 0xFFA6)[0] & 0x3F
    par7 = _logical_read(probe, 0xFFA7)[0] & 0x3F
    if (par6, par7) != (0x3E, 0x3F):
        raise ValueError(f"resident mapping differs: PAR6={par6:02X}, PAR7={par7:02X}")
    proof: dict[str, Any] = {"resident_sha256": sha256(live_resident), "resident_matches": True,
                             "PAR6": par6, "PAR7": par7}
    if need_enemy:
        enemy = (build / "ladybug-enemy-runtime.rom").read_bytes()
        live_enemy = _read_spans(probe, LOW_PAGE, 0x0800, len(enemy))
        _require_identity_bytes(enemy, live_enemy, "enemy module")
        proof["enemy_module_sha256"] = sha256(live_enemy)
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
        proof.update({"rate_helper_sha256": sha256(live_rate), "rate_helper_matches": True,
                      "e2_helper_sha256": sha256(live_e2), "e2_helper_matches": True})
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


def _low_snapshot(probe: RuntimeProbe) -> dict[str, Any]:
    low = _phys_read(probe, LOW_PAGE * PAGE_BYTES, 0x300)
    def word(address: int) -> int:
        return int.from_bytes(low[address:address + 2], "big")
    return {"stage": low[0x24], "death_state": low[0x4D], "enemy_active": low[0x58],
            "enemy_move": low[0x61], "frames": word(FRAMES), "fb_sim_seq": word(FB_SIM_SEQ),
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
    voff = _logical_read(probe, GIME_VOFF1)[0]
    expected = 0xC0 if owner == 0 else 0xB0 if owner == 1 else None
    if expected is None or voff != expected:
        raise ValueError(f"GIME Voffset {voff:02X} does not identify FRONT owner {owner}")
    region = _surface_span(probe, owner, offset, (rows - 1) * 160 + width)
    pixels = b"".join(region[row * 160:row * 160 + width] for row in range(rows))
    return {"owner": owner, "gime_voff1": voff, "pointer": pointer, "pixel_bytes": len(pixels),
            "pixel_sha256": hashlib.sha256(pixels).hexdigest(), "pixel_nonzero": any(pixels)}


def _snapshot(probe: RuntimeProbe, pixels: bool = False) -> dict[str, Any]:
    state = _low_snapshot(probe)
    records = _enemy_records(probe)
    result: dict[str, Any] = {"state": state, "records": records}
    if pixels:
        result["front_pixels"] = {str(row["slot"]): _front_tile(probe, row["fb"])
                                   for row in records if row["active"] and VISIBLE_START <= row["fb"] < 0x9800}
    return result


def _live_side(probe: RuntimeProbe, identity: dict[str, Any], side: str,
               need_enemy: bool = True, require_mapping: bool = True) -> dict[str, Any]:
    proof = _verify_runtime_images(probe, identity, need_enemy, require_mapping)
    maps = {role: _runtime_symbols(identity, role) for role in ("main", "enemy")}
    if identity["side"] != side:
        raise ValueError(f"expected {side} identity, received {identity['side']}")
    return {"identity": identity, "proof": proof, "maps": maps}


def _rate_expected(stage: int, bucket: int) -> int:
    offsets = (0, 2, 4, 1, 3, 5, 6, 8, 5, 7, 9, 10, 11, 8, 12, 13, 14)
    offset = 0 if stage == 0 else 15 if stage >= 18 else offsets[stage - 1]
    rate_index = min(15, offset + (bucket >> 4))
    return 0x00 if rate_index < 6 else 0x33 if rate_index < 12 else 0x80 if rate_index < 15 else 0xCC


def _assert_identity_pair(baseline: dict[str, Any], candidate: dict[str, Any]) -> None:
    if baseline.get("profile") != candidate.get("profile"):
        raise ValueError("baseline and candidate profiles differ")
    if baseline.get("side") != "baseline" or candidate.get("side") != "candidate":
        raise ValueError("paired identities must be baseline then candidate")
    for side in (baseline, candidate):
        verify_identity(side)
        dep = side.get("bug086_dependency", {})
        if dep.get("actual_done") is not True:
            raise ValueError("paired current builds were not captured against BUG-086 actualDone")


def _phase_matched(args: argparse.Namespace, deadline: float) -> dict[str, Any]:
    baseline = json.loads(Path(args.baseline_identity).read_text(encoding="utf-8"))
    candidate = json.loads(Path(args.candidate_identity).read_text(encoding="utf-8"))
    _assert_identity_pair(baseline, candidate)
    probes: list[RuntimeProbe] = []
    try:
        left = RuntimeProbe(args.baseline_host, args.baseline_port, deadline)
        probes.append(left)
        right = RuntimeProbe(args.candidate_host, args.candidate_port, deadline)
        probes.append(right)
        left_side = _live_side(left, baseline, "baseline")
        right_side = _live_side(right, candidate, "candidate")
        tick_l = left_side["maps"]["enemy"]["enemy_tick_impl"]
        tick_r = right_side["maps"]["enemy"]["enemy_tick_impl"]
        rate_tick = _runtime_symbols(candidate, "rate")["rate_tick"]
        id_l, id_r = left.set_breakpoint(tick_l), right.set_breakpoint(tick_r)
        rate_bp = right.set_breakpoint(rate_tick)
        first_l, first_r = left.run_until_marker(), right.run_until_marker()
        _require_markers({"baseline-enemy-callback", "candidate-enemy-callback"},
                         {"baseline-enemy-callback" if first_l["pc"] == tick_l else "",
                          "candidate-enemy-callback" if first_r["pc"] == tick_r else ""})
        snap_l, snap_r = _snapshot(left, pixels=True), _snapshot(right, pixels=True)
        common = [i for i in range(4)
                  if snap_l["records"][i]["active"] and snap_r["records"][i]["active"]
                  and snap_l["records"][i]["bytes_hex"] == snap_r["records"][i]["bytes_hex"]
                  and snap_l["records"][i]["direction"] in (1, 3) if args.axis == "horizontal"]
        if args.axis == "vertical":
            common = [i for i in range(4)
                      if snap_l["records"][i]["active"] and snap_r["records"][i]["active"]
                      and snap_l["records"][i]["bytes_hex"] == snap_r["records"][i]["bytes_hex"]
                      and snap_l["records"][i]["direction"] in (0, 2)]
        if not common:
            raise RuntimeError(f"missing matched active {args.axis} actor in the two live builds")
        slot = common[0]
        if (not snap_l["front_pixels"].get(str(slot), {}).get("pixel_nonzero") or
                not snap_r["front_pixels"].get(str(slot), {}).get("pixel_nonzero")):
            raise RuntimeError("matched active actor FRONT pixel marker is empty")
        pointer_start_l = snap_l["records"][slot]["fb"]
        pointer_start_r = snap_r["records"][slot]["fb"]
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
            mark_l, mark_r = left.run_until_marker(), right.run_until_marker()
            if mark_l["pc"] != tick_l or mark_r["pc"] != rate_tick:
                raise RuntimeError("paired enemy callback or candidate rate_tick marker stopped at the wrong PC")
            par5 = _logical_read(right, 0xFFA5)[0] & 0x3F
            if par5 != STATE_PAGE:
                raise RuntimeError(f"actual candidate rate_tick marker has PAR5=${par5:02X}, expected $34")
            rate_markers.append({"pc": f"${mark_r['pc']:04X}", "PAR5": par5,
                                 "callback": len(rate_markers) + 1})
            mark_r = right.run_until_marker()
            if mark_r["pc"] != tick_r:
                raise RuntimeError("candidate rate_tick did not return to the next actual enemy callback")
            now_l, now_r = _snapshot(left, pixels=True), _snapshot(right, pixels=True)
            rec_l, rec_r = now_l["records"][slot], now_r["records"][slot]
            if rec_l["direction"] != rec_r["direction"] or rec_l["direction"] not in ((1, 3) if args.axis == "horizontal" else (0, 2)):
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
            frame_delta_l = (now_l["state"]["frames"] - last_l["state"]["frames"]) & 0xFFFF
            frame_delta_r = (now_r["state"]["frames"] - last_r["state"]["frames"]) & 0xFFFF
            seq_delta_l = (now_l["state"]["fb_sim_seq"] - last_l["state"]["fb_sim_seq"]) & 0xFFFF
            seq_delta_r = (now_r["state"]["fb_sim_seq"] - last_r["state"]["fb_sim_seq"]) & 0xFFFF
            if frame_delta_l == 0 or frame_delta_r == 0:
                raise RuntimeError("raw FRAMES Vbord count did not advance during a matched enemy callback")
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
            if moves_l and moves_r and any(row["candidate_fb_delta"] == 0 for row in samples):
                break
        n = len(samples)
        _require_markers({"same-actor", "zero-rate-interval", "nonzero-rate-movement",
                          "raw-vbord", "front-actor-pixels"},
                         {"same-actor", "zero-rate-interval" if any(row["candidate_fb_delta"] == 0 for row in samples) else "",
                          "nonzero-rate-movement" if moves_r else "", "raw-vbord" if samples and
                          all("candidate_FRAMES" in row for row in samples) else "",
                          "actual-rate-tick" if len(rate_markers) == n else "",
                          "front-actor-pixels" if samples and any(row["candidate_front_pixel_sha256"] for row in samples) else ""})
        admissions = carries + (n - carries) // 2
        candidate_observed_pixels = signed_candidate_delta
        if abs(candidate_observed_pixels - admissions * 2) > 1:
            raise RuntimeError(f"candidate rate oracle differs: observed={candidate_observed_pixels}px expected={admissions * 2}px tolerance=1px")
        return {"status": "pass-runtime-marker-set", "phase": "matched-displacement", "axis": args.axis,
                "callback_count": n, "same_actor_slot": slot, "active_part": start_state_r["stage"],
                "candidate_rate_start": candidate_addend, "fractional_carries": carries,
                "policy_admissions": admissions, "candidate_observed_pixels": candidate_observed_pixels,
                "candidate_expected_pixels": admissions * 2, "pixel_tolerance": 1,
                "baseline_observed_pixels": signed_baseline_delta, "baseline_move_count": moves_l,
                "candidate_move_count": moves_r, "raw_vbord_counts": {
                    "baseline_start": start_state_l["frames"], "baseline_end": last_l["state"]["frames"],
                    "candidate_start": start_state_r["frames"], "candidate_end": last_r["state"]["frames"]},
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


def _phase_freeze(args: argparse.Namespace, deadline: float) -> dict[str, Any]:
    identity = json.loads(Path(args.identity).read_text(encoding="utf-8"))
    verify_identity(identity)
    probe = RuntimeProbe(args.host, args.port, deadline)
    try:
        side = _live_side(probe, identity, "candidate")
        enemy = side["maps"]["enemy"]
        tick = enemy["enemy_tick_impl"]
        if identity["side"] != "candidate":
            raise ValueError("freeze-saturated-thaw requires the candidate identity")
        bp_id = probe.set_breakpoint(tick)
        first = probe.run_until_marker()
        if first["pc"] != tick:
            raise RuntimeError("actual enemy callback marker missing before freeze fixture")
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
            if frame_delta == 0:
                raise RuntimeError(f"raw Vbord frame marker did not advance during callback {index}")
            frame_deltas.append(frame_delta)
            sim_deltas.append(sim_delta)
            trace.update(f"{index}:{state['frames']}:{state['fb_sim_seq']}:{state['freeze_timer']};".encode())
            previous = current
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
                "fb_sim_seq_delta_min": min(sim_deltas), "fb_sim_seq_delta_max": max(sim_deltas),
                "300_callback_trace_sha256": trace.hexdigest(), "identity": side["proof"],
                "monitor_audit": probe.audit()}
    finally:
        _close_probe(probe)


def _phase_reversal(args: argparse.Namespace, deadline: float) -> dict[str, Any]:
    identity = json.loads(Path(args.identity).read_text(encoding="utf-8"))
    verify_identity(identity)
    probe = RuntimeProbe(args.host, args.port, deadline)
    try:
        side = _live_side(probe, identity, "candidate")
        enemy = side["maps"]["enemy"]
        tick = enemy["enemy_tick_impl"]
        choose = enemy.get("ecd_choose")
        blocked = enemy.get("ecd_blocked")
        if choose is None or blocked is None:
            raise ValueError("current enemy map does not resolve both legal chooser outcomes")
        ids = {"tick": probe.set_breakpoint(tick), "choose": probe.set_breakpoint(choose),
               "blocked": probe.set_breakpoint(blocked)}
        first = probe.run_until_marker()
        if first["pc"] != tick:
            raise RuntimeError("actual enemy callback marker missing before legal-reversal route")
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
        observed: set[str] = {"initial-actor-6-4", "gate-0-remains-zero"}
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
        side = _live_side(probe, identity, "candidate", need_enemy=False, require_mapping=False)
        main, enemy = side["maps"]["main"], side["maps"]["enemy"]
        next_stage, init_entry = main["next_stage"], main["init_enemy"]
        shim = _runtime_symbols(identity, "rate")["rate_enemy_init_shim"]
        enemy_init, first_tick = enemy["enemy_init_impl"], enemy["enemy_tick_impl"]
        points = {"next_stage": next_stage, "init_enemy": init_entry,
                  "rate_enemy_init_shim": shim, "enemy_init_impl": enemy_init,
                  "first_enemy_tick": first_tick}
        ids = {name: probe.set_breakpoint(address) for name, address in points.items()}
        observed: list[dict[str, Any]] = []
        order = ("next_stage", "init_enemy", "rate_enemy_init_shim", "enemy_init_impl", "first_enemy_tick")
        for expected in order:
            mark = probe.run_until_marker()
            if mark["pc"] in range(0x0800, 0x0800 + 0x2000):
                if _logical_read(probe, 0xFFA0)[0] & 0x3F != LOW_PAGE:
                    raise RuntimeError("enemy callback marker is not mapped through PAR0 page $38")
                expected_enemy = (Path(identity["build_dir"]) / "ladybug-enemy-runtime.rom").read_bytes()
                live_enemy = _read_spans(probe, LOW_PAGE, 0x0800, len(expected_enemy))
                _require_identity_bytes(expected_enemy, live_enemy, "live enemy module before marker interpretation")
            hit_name = next((name for name, ident in ids.items() if ident == mark["bp_id"]), None)
            if hit_name != expected or mark["pc"] != points[expected]:
                raise RuntimeError(f"natural-init marker order expected {expected}, got {hit_name} at ${mark['pc']:04X}")
            state = _low_snapshot(probe)
            sample: dict[str, Any] = {"marker": expected, "pc": f"${mark['pc']:04X}", "state": state}
            if expected == "init_enemy":
                expected_call = (Path(identity["build_dir"]) / "ladybug-runtime.rom").read_bytes()[init_entry - 0xC000:init_entry - 0xC000 + 3]
                live_call = _logical_read(probe, init_entry, 3)
                _require_identity_bytes(expected_call, live_call, "resident init callsite")
                sample["init_callsite_hex"] = live_call.hex()
            elif expected == "rate_enemy_init_shim":
                par5 = _logical_read(probe, 0xFFA5)[0] & 0x3F
                expected_rate = (Path(identity["build_dir"]) / "ladybug-rate-helper.bin").read_bytes()
                live_rate = _read_spans(probe, STATE_PAGE, 0x03B0, len(expected_rate))
                _require_identity_bytes(expected_rate, live_rate, "rate shim code")
                if par5 != STATE_PAGE:
                    raise RuntimeError(f"natural shim entered with PAR5=${par5:02X}, expected $34")
                sample.update({"PAR5": par5, "rate_helper_sha256": sha256(live_rate)})
            elif expected == "enemy_init_impl":
                expected_enemy = (Path(identity["build_dir"]) / "ladybug-enemy-runtime.rom").read_bytes()
                live_enemy = _read_spans(probe, LOW_PAGE, 0x0800, len(expected_enemy))
                _require_identity_bytes(expected_enemy, live_enemy, "staged enemy module at true-init entry")
                bucket = state["rate_bucket"]
                expected_addend = _rate_expected(state["stage"], bucket)
                if (state["rate_timer"], bucket, state["rate_frac"], state["rate_phase"], state["rate_addend"]) != (96, 0, 0, 0, expected_addend):
                    raise RuntimeError(f"real shim reset state differs at true init: {state}")
                sample["enemy_module_sha256"] = sha256(live_enemy)
                sample["rate_reset_matches"] = True
            elif expected == "first_enemy_tick":
                sample["records"] = _enemy_records(probe)
                if _logical_read(probe, 0xFFA0)[0] & 0x3F != LOW_PAGE:
                    raise RuntimeError("first actual enemy tick is not executing from mapped low page $38")
            observed.append(sample)
        return {"status": "pass-runtime-marker-set", "phase": "natural-init",
                "natural_transition_markers": observed, "no_forced_stage_or_init_writes": True,
                "identity": side["proof"], "monitor_audit": probe.audit()}
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
    if auth.get("phase") != args.phase or auth.get("phase_deadline_seconds") != PHASE_DEADLINE_SECONDS:
        raise ValueError("runtime not started: dispatch receipt does not authorize this exact 45-second phase")
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
    fixture_hash = hashlib.sha256(json.dumps(PHASE_CONTRACTS[args.phase], sort_keys=True,
                                              separators=(",", ":")).encode()).hexdigest()
    if auth.get("fixture_contract_sha256") != fixture_hash:
        raise ValueError("runtime not started: fixture contract differs from parent-reviewed dispatch receipt")
    return {"authorization_sha256": sha256(auth_path), "BUG086_receipt_sha256": dep_hash,
            "identity_sha256_by_name": identity_hashes, "adapter_sha256": adapter_hash,
            "scenario_plan_sha256": sha256(PLAN), "fixture_contract_sha256": fixture_hash,
            "dispatch": auth}


def cmd_live(args: argparse.Namespace) -> int:
    ACTIVE_PROBES.clear()
    output = Path(args.output).resolve()
    identity_paths = ([Path(args.baseline_identity).resolve(strict=True),
                       Path(args.candidate_identity).resolve(strict=True)]
                      if args.phase == "matched-displacement" else [Path(args.identity).resolve(strict=True)])
    auth = authorize_dispatch(args, identity_paths, output)
    deadline = time.monotonic() + PHASE_DEADLINE_SECONDS
    started = time.monotonic()
    try:
        if args.phase == "matched-displacement":
            result = _phase_matched(args, deadline)
        elif args.phase == "freeze-saturated-thaw":
            result = _phase_freeze(args, deadline)
        elif args.phase == "legal-reversal-concurrent-mover":
            result = _phase_reversal(args, deadline)
        elif args.phase == "natural-init":
            result = _phase_natural_init(args, deadline)
        else:
            raise ValueError(f"unsupported phase: {args.phase}")
        result["phase_elapsed_seconds"] = round(time.monotonic() - started, 6)
        result["phase_deadline_seconds"] = PHASE_DEADLINE_SECONDS
        result["phase_deadline_met"] = result["phase_elapsed_seconds"] <= PHASE_DEADLINE_SECONDS
        result["runtime_launched"] = False
        result["emulator_attached"] = True
        result["runtime_acceptance"] = False
        result["authorization"] = {key: value for key, value in auth.items() if key != "dispatch"}
        if not result["phase_deadline_met"]:
            result["status"] = "fail-deadline"
    except Exception as exc:
        result = {"schema": "rsch014-ready-087-live-phase-v1", "status": "fail-runtime-marker",
                  "phase": args.phase, "phase_deadline_seconds": PHASE_DEADLINE_SECONDS,
                  "phase_elapsed_seconds": round(time.monotonic() - started, 6),
                  "timeout_meaning": next(row["timeout_meaning"] for row in
                      json.loads(PLAN.read_text(encoding="utf-8"))["phases"] if row["id"] == args.phase),
                  "error": f"{type(exc).__name__}: {exc}", "runtime_launched": False,
                  "emulator_attached": bool(ACTIVE_PROBES), "runtime_acceptance": False,
                  "monitor_audit": [probe.audit() for probe in ACTIVE_PROBES],
                  "authorization": {key: value for key, value in auth.items() if key != "dispatch"}}
        if isinstance(exc, TimeoutError) and result["phase_elapsed_seconds"] <= PHASE_DEADLINE_SECONDS:
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
    expect("missing scenario marker rejected", lambda: _require_markers({"callback", "front-pixel"}, {"callback"}), False)
    expect("wrong live bytes rejected", lambda: _require_identity_bytes(b"\xBD\xA3\xC5", b"\xBD\xA3\xC4", "rate callsite"), False)
    expect("matching live bytes accepted", lambda: _require_identity_bytes(b"\xBD\xA3\xC5", b"\xBD\xA3\xC5", "rate callsite"), True)
    expect("45-second deadline accepted", lambda: validate_plan(plan), True)
    if not all(case["passed"] for case in cases):
        raise AssertionError(json.dumps(cases, indent=2))
    # Fractional carry arithmetic: two-pixel source step; one-pixel endpoint tolerance.
    for n in range(1, 33):
        for carries in range(n + 1):
            admissions = carries + (n - carries) // 2
            pixels = 2 * admissions
            assert abs(pixels - (n + carries)) <= 1
    assert all(p["deadline_seconds"] <= 45 for p in plan["phases"])
    print(f"SELFTEST PASS plan_schema=1 phases=4 guard_cases={len(cases)} arithmetic_cases=560 runtime=not-run")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)
    capture = sub.add_parser("capture", help="hash a current assigned build and resolve its maps")
    capture.add_argument("--side", choices=("baseline", "candidate"), required=True)
    capture.add_argument("--profile", choices=("complete-ad1-keyboard", "complete-ad1-joystick"), required=True)
    capture.add_argument("--build-dir", required=True)
    capture.add_argument("--source-revision", required=True,
                         help="integrated source commit or exact dispatch revision supplied by owner")
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
    live.add_argument("--axis", choices=("horizontal", "vertical"), default="horizontal")
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
                missing = [name for name in ("identity", "port") if getattr(args, name) is None]
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
