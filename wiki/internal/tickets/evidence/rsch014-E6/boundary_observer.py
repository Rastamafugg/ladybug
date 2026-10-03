#!/usr/bin/env python3
"""One bounded BUG-086 first-worklist monitor-boundary diagnostic."""

from __future__ import annotations

import hashlib
import json
import socket
import subprocess
import sys
import time
from pathlib import Path


arguments = sys.argv[1:]
PREFLIGHT_ONLY = bool(arguments and arguments[0] == "--preflight-only")
if PREFLIGHT_ONLY:
    arguments = arguments[1:]
if len(arguments) != 2:
    raise SystemExit("usage: boundary_observer.py [--preflight-only] WORKTREE OUTPUT")
worktree, output = map(Path, arguments)
sys.path.insert(0, str(worktree / "scripts"))
import verify_bug011_runtime as runtime

monitor = runtime.load_monitor()

BUILD = worktree / "build"
ROM = BUILD / "ladybug.rom"
RESIDENT = BUILD / "ladybug-runtime.rom"
ENEMY = BUILD / "ladybug-enemy-runtime.rom"
HELPER = BUILD / "ladybug-enemy-helper-page34.bin"
PRESENTATION = BUILD / "ladybug-presentation-runtime.bin"
ACTIVE = BUILD / "ladybug-adaptive-active.bin"
LAYOUT = BUILD / "ladybug-sparse-layout.json"
XROAR = Path("/mnt/e/projects/ladybug/docs/reference/xroar/src/xroar")
PAGE_BYTES = 0x2000
RET_CAPTURE_RESERVE = 5.0
PRIMARY_WAIT_LIMIT = 40.0
HELPER_ADDRESS = 0xA8A0
HELPER_PAGE = 0x34
ENEMY_WINDOW_START = 0x0800


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest_file(path: Path) -> str:
    return sha(path.read_bytes())


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def normalized_pars(raw: list[int]) -> list[int]:
    return [value & 0x3F for value in raw]


def main() -> int:
    preflight_path = worktree / "wiki/internal/tickets/evidence/rsch014-E6/preflight-20261003.json"
    preflight = load_json(preflight_path)
    evidence: dict[str, object] = {
        "schema": "ladybug-rsch014-e6-bug086-helper-caller-boundary-v1",
        "date": "2026-10-03",
        "status": "incomplete",
        "phase": {
            "name": "cold-credited-start-to-first-active-worklist",
            "deadline_seconds": 45,
            "primary_wait_max_seconds": PRIMARY_WAIT_LIMIT,
            "capture_cleanup_reserve_seconds": RET_CAPTURE_RESERVE,
            "success_marker": "all 87 helper bytes match authored, staged, physical, and PAR5-mapped images at helper entry; the source-proven caller and return match the built enemy image; resident $C116 is then reached with live bytes matching the built artifact",
            "timeout_meaning": "The observer did not establish the helper entry, its source-proven return, or resident $C116 inside this 45-second phase. Timeout is not evidence of target slowness or a game defect.",
        },
        "preflight_receipt": str(preflight_path.relative_to(worktree)).replace("\\", "/"),
        "runtime_instance": {},
        "observations": [],
        "run_requests": [],
        "claims": {
            "natural_full_maze_progression": False,
            "parts_2_through_8_skipped": False,
            "gameplay_acceptance": False,
            "source_or_profile_changes": False,
        },
    }
    process = None
    client = None
    secondary = None
    deadline = 0.0
    phase_started = 0.0
    fatal: str | None = None
    primary_timed_out = False
    secondary_capture_deadline: float | None = None

    def remaining_for_primary(label: str) -> float:
        left = deadline - time.monotonic() - RET_CAPTURE_RESERVE
        if left <= 0.05:
            raise TimeoutError(f"capture reserve reached before {label}")
        return left

    def monitor_call(method: str, params: dict | None = None, label: str | None = None,
                     client_override=None, max_timeout: float | None = None) -> dict:
        target = client if client_override is None else client_override
        left = remaining_for_primary(label or method) if client_override is None else deadline - time.monotonic()
        if target is secondary and secondary_capture_deadline is not None:
            left = min(left, secondary_capture_deadline - time.monotonic())
        if max_timeout is not None:
            left = min(left, max_timeout)
        if left <= 0.05:
            raise TimeoutError(f"phase deadline reached before {label or method}")
        return target.call(method, params, timeout=left)

    def read(address: int, length: int = 1, target=None) -> bytes:
        raw = monitor_call("read_memory", {"addr": address, "length": length},
                           f"read logical ${address:04X}+{length}", target)
        return bytes.fromhex(raw["data"])

    def read_byte(address: int, target=None) -> int:
        return read(address, 1, target)[0]

    def read_phys(page: int, offset: int, length: int, target=None) -> bytes:
        raw = monitor_call("read_memory", {
            "space": "physical", "addr": page * PAGE_BYTES + offset, "length": length,
        }, f"read physical page ${page:02X}+${offset:04X}", target)
        return bytes.fromhex(raw["data"])

    def read_regs(target=None) -> dict:
        return monitor_call("read_registers", label="read CPU registers", client_override=target)

    def read_pars(target=None) -> list[int]:
        return list(read(0xFFA0, 8, target))

    def set_break(address: int) -> int:
        return monitor_call("set_breakpoint", {"addr": address, "kind": "exec"},
                            f"set breakpoint ${address:04X}")["id"]

    def clear_break(ident: int) -> None:
        monitor_call("clear_breakpoint", {"id": ident}, f"clear breakpoint {ident}", max_timeout=1.0)

    def run_until_breakpoint(label: str, timeout: float, expected: int | None = None) -> dict:
        ident = client.next_id
        client.next_id += 1
        started = time.monotonic()
        req = {"jsonrpc": "2.0", "id": ident, "method": "run"}
        client.file.write((json.dumps(req) + "\n").encode())
        client.file.flush()
        run_record = {
            "label": label, "request_id": ident, "sent": True,
            "started_after_phase_seconds": round(started - phase_started, 6),
            "timeout_seconds": round(timeout, 6), "acknowledged": False,
            "breakpoint_hit": False, "events_before_ack": [], "other_events": [],
        }
        evidence["run_requests"].append(run_record)
        end = min(deadline - RET_CAPTURE_RESERVE, started + timeout)
        hit = None
        try:
            while time.monotonic() < end:
                message = client._read(end)
                if message.get("id") == ident:
                    if "error" in message:
                        run_record["error"] = message["error"]
                        raise RuntimeError(f"run request rejected: {message['error']}")
                    run_record["acknowledged"] = True
                    run_record["ack_result"] = message.get("result", {})
                elif message.get("method") == "bp":
                    params = message.get("params", {})
                    entry = {"params": params, "after_ack": run_record["acknowledged"]}
                    if run_record["acknowledged"]:
                        hit = params
                        run_record["breakpoint_hit"] = True
                        run_record["breakpoint_event"] = entry
                    else:
                        run_record["events_before_ack"].append(entry)
                        hit = params
                else:
                    run_record["other_events"].append(message)
                    client.events.append(message)
                if run_record["acknowledged"] and hit is not None:
                    if expected is not None and hit.get("pc") != expected:
                        run_record["expected_pc"] = expected
                        run_record["unexpected_pc"] = hit.get("pc")
                        raise RuntimeError(f"{label}: expected PC ${expected:04X}, got {hit}")
                    run_record["elapsed_seconds"] = round(time.monotonic() - started, 6)
                    return hit
        except (TimeoutError, socket.timeout) as exc:
            run_record["elapsed_seconds"] = round(time.monotonic() - started, 6)
            run_record["timeout"] = f"{type(exc).__name__}: no acknowledged breakpoint event before this wait bound"
            raise TimeoutError(f"{label}: breakpoint not observed before bounded wait ended") from exc
        run_record["elapsed_seconds"] = round(time.monotonic() - started, 6)
        run_record["timeout"] = "no acknowledged breakpoint event before this wait bound"
        raise TimeoutError(f"{label}: breakpoint not observed before bounded wait ended")

    def go(address: int, label: str) -> dict:
        nonlocal primary_timed_out
        ident = set_break(address)
        try:
            hit = run_until_breakpoint(label, min(12.0, remaining_for_primary(label)), address)
            regs = read_regs()
            obs = {"label": label, "hit": hit, "registers": regs}
            evidence["observations"].append(obs)
            return regs
        except (TimeoutError, socket.timeout, OSError):
            primary_timed_out = True
            raise
        finally:
            if not primary_timed_out:
                clear_break(ident)

    def helper_proof(helper: bytes, staged_helper: bytes, target=None,
                     gime_state: dict | None = None) -> dict[str, object]:
        pars_raw = read_pars(target)
        pars = normalized_pars(pars_raw)
        gime = gime_state
        if gime is None and target is None:
            gime = monitor_call("read_gime_state", label="read structured GIME PAR state",
                                max_timeout=0.7)
        gime = gime or {}
        task0_pars = gime.get("pars", {}).get("task0")
        structured_matches = isinstance(task0_pars, list) and task0_pars == pars
        physical = read_phys(HELPER_PAGE, 0x08A0, len(helper), target)
        mapped = read(HELPER_ADDRESS, len(helper), target) if pars[5] == HELPER_PAGE else b""
        return {
            "PAR0_7_raw": pars_raw, "PAR0_7_low6": pars,
            "PAR0_7_structured_task0": task0_pars,
            "raw_mask3F_matches_structured": structured_matches,
            "length": len(helper), "authored_helper_sha256": sha(helper),
            "staged_helper_sha256": sha(staged_helper), "authored_equals_staged": staged_helper == helper,
            "physical_page34_sha256": sha(physical),
            "mapped_page34_sha256": sha(mapped) if mapped else None,
            "physical_equals_authored": physical == helper,
            "mapped_equals_authored": mapped == helper if mapped else False,
            "mapping_valid": (len(helper) == 87 and staged_helper == helper and structured_matches and
                              pars[5] == HELPER_PAGE and physical == helper and mapped == helper),
        }

    def active_stage_proof(active: bytes, target=None) -> dict[str, object]:
        pars_raw = read_pars(target)
        pars = normalized_pars(pars_raw)
        staged = read_phys(0x3D, 0x17A5, len(active), target)
        destination = read(0x038F, len(active), target) if pars[0] == 0x38 else b""
        return {
            "stage_physical_page": 0x3D, "stage_window_address": 0xB7A5,
            "destination_address": 0x038F, "PAR0_7_raw": pars_raw,
            "PAR0_7_low6": pars, "destination_PAR0": pars[0],
            "source_active_sha256": sha(active), "staged_active_sha256": sha(staged),
            "destination_active_sha256": sha(destination) if destination else None,
            "staged_equals_source": staged == active,
            "destination_equals_source": destination == active if destination else False,
            "staged_equals_destination": staged == destination if destination else False,
            "mapping_valid": pars[0] == 0x38 and staged == active and destination == active,
        }

    def code_proof(label: str, pc: int, regs: dict, pars: list[int], resident: bytes,
                   presentation: bytes, active: bytes, helper: bytes) -> dict[str, object]:
        pars_low6 = normalized_pars(pars)
        data = b""
        expected = b""
        mapping = "unresolved"
        if 0xC000 <= pc < 0xC000 + len(resident):
            mapping = "resident-PAR6/7"
            data = read(pc, min(12, 0xC000 + len(resident) - pc))
            expected = resident[pc - 0xC000:pc - 0xC000 + len(data)]
            valid = pars_low6[6] == 0x3E and pars_low6[7] == 0x3F
        elif 0x1900 <= pc < 0x1900 + len(presentation):
            mapping = "presentation-PAR0"
            data = read(pc, min(12, 0x1900 + len(presentation) - pc))
            expected = presentation[pc - 0x1900:pc - 0x1900 + len(data)]
            valid = pars_low6[0] == 0x38
        elif 0x038F <= pc < 0x038F + len(active):
            mapping = "adaptive-active-PAR0"
            data = read(pc, min(12, 0x038F + len(active) - pc))
            expected = active[pc - 0x038F:pc - 0x038F + len(data)]
            valid = pars_low6[0] == 0x38
        elif 0xA8A0 <= pc < 0xA8A0 + len(helper):
            mapping = "page34-helper-PAR5"
            data = read(pc, min(12, 0xA8A0 + len(helper) - pc))
            expected = helper[pc - 0xA8A0:pc - 0xA8A0 + len(data)]
            valid = pars_low6[5] == HELPER_PAGE
        else:
            valid = False
        return {
            "label": label, "pc": pc, "mapping_candidate": mapping,
            "register_PC": regs.get("pc"), "PAR0_7_raw": pars, "PAR0_7_low6": pars_low6,
            "live_bytes_sha256": sha(data) if data else None,
            "expected_bytes_sha256": sha(expected) if expected else None,
            "live_equals_expected": bool(data) and data == expected,
            "mapping_matches_expected": bool(valid),
            "symbol_interpretation_allowed": bool(data) and data == expected and bool(valid),
        }

    def capture_secondary(reason: str) -> dict[str, object]:
        nonlocal secondary_capture_deadline
        capture: dict[str, object] = {"reason": reason}
        capture_deadline = min(deadline - 1.5, time.monotonic() + 3.2)
        secondary_capture_deadline = capture_deadline
        left = max(0.05, capture_deadline - time.monotonic())
        try:
            capture["pause"] = monitor_call("pause", client_override=secondary,
                                             max_timeout=min(0.8, left))
        except Exception as exc:
            capture["pause_error"] = f"{type(exc).__name__}: {exc}"
        left = max(0.05, capture_deadline - time.monotonic())
        try:
            capture["run_state"] = monitor_call("get_run_state", client_override=secondary,
                                                 max_timeout=min(0.5, left))
        except Exception as exc:
            capture["run_state_error"] = f"{type(exc).__name__}: {exc}"
        left = max(0.05, capture_deadline - time.monotonic())
        try:
            capture["registers"] = read_regs(secondary)
        except Exception as exc:
            capture["registers_error"] = f"{type(exc).__name__}: {exc}"
        left = max(0.05, capture_deadline - time.monotonic())
        try:
            capture["gime_state"] = monitor_call("read_gime_state", client_override=secondary,
                                                  max_timeout=min(0.5, left))
        except Exception as exc:
            capture["gime_state_error"] = f"{type(exc).__name__}: {exc}"
        left = max(0.05, capture_deadline - time.monotonic())
        try:
            pars_raw = read_pars(secondary)
            capture["PAR0_7_raw"] = pars_raw
            capture["PAR0_7_low6"] = normalized_pars(pars_raw)
            regs = capture.get("registers", {})
            pc = regs.get("pc") if isinstance(regs, dict) else None
            if isinstance(pc, int):
                capture["live_PC_bytes"] = read(pc, 12, secondary).hex()
                capture["live_PC_bytes_sha256"] = sha(bytes.fromhex(capture["live_PC_bytes"]))
            capture["helper_proof"] = helper_proof(
                helper, staged_helper, secondary, capture.get("gime_state"))
            if isinstance(regs, dict) and isinstance(regs.get("s"), int):
                capture["stack_at_S"] = read(regs["s"], 4, secondary).hex()
        except Exception as exc:
            capture["PAR_PC_read_error"] = f"{type(exc).__name__}: {exc}"
        capture["process_poll"] = process.poll() if process is not None else None
        return capture

    try:
        observer_receipt = preflight.get("observer", {})
        if observer_receipt.get("ast") != "pass; ast.parse only, no import or execution":
            raise RuntimeError("preflight AST-only parse receipt is absent")
        if observer_receipt.get("sha256") != digest_file(Path(__file__)):
            raise RuntimeError("observer bytes differ from E6 prelaunch AST/hash receipt")
        git_path = subprocess.check_output(["which", "git.exe"], text=True).strip()
        windows_worktree = subprocess.check_output(
            ["wslpath", "-m", str(worktree)], text=True).strip()
        current_head = subprocess.check_output(
            [git_path, "-C", windows_worktree, "rev-parse", "HEAD"], text=True).strip()
        if preflight.get("worktree_head") != current_head:
            raise RuntimeError("worktree HEAD differs from E6 source/build identity receipt")
        for relative_path, expected_hash in preflight.get("pinned_files", {}).items():
            if digest_file(worktree / relative_path) != expected_hash:
                raise RuntimeError(f"pinned source/build input changed before launch: {relative_path}")
        control = preflight.get("private_control", {})
        launcher_path = worktree / "scripts/verify_bug011_runtime.py"
        monitor_path = worktree / "scripts/verify_bug009_monitor_input.py"
        launcher_source = launcher_path.read_text(encoding="utf-8")
        monitor_source = monitor_path.read_text(encoding="utf-8")
        launcher_hash = digest_file(launcher_path)
        monitor_hash = digest_file(monitor_path)
        if (control.get("launcher_sha256") != launcher_hash or
                control.get("monitor_client_sha256") != monitor_hash):
            raise RuntimeError("private monitor launcher/client hashes differ from E6 receipt")
        for token in (
                "port = monitor.free_port()", '"-ui", "null", "-ao", "null"',
                '"-machine", "coco3",', '"-ram", "512", "-cart-type", "gmc"',
                '"-monitor", f"127.0.0.1:{port}"', '"-monitor-halt-on-start"',
                'socket.create_connection(("127.0.0.1", port'):
            if token not in launcher_source:
                raise RuntimeError(f"private XRoar control contract is missing: {token}")
        for token in ("def free_port()", 'sock.bind(("127.0.0.1", 0))',
                      "class MonitorClient"):
            if token not in monitor_source:
                raise RuntimeError(f"private monitor client contract is missing: {token}")
        if "runtime.launch_fast(monitor, XROAR, ROM)" not in Path(__file__).read_text(encoding="utf-8"):
            raise RuntimeError("E6 observer no longer invokes the pinned private XRoar launcher")
        evidence["private_control_identity"] = {
            "launcher": "scripts/verify_bug011_runtime.py", "launcher_sha256": launcher_hash,
            "monitor_client": "scripts/verify_bug009_monitor_input.py",
            "monitor_client_sha256": monitor_hash, "monitor_endpoint": "127.0.0.1",
            "ephemeral_port_source": "monitor.free_port()", "contract_static_check": "pass",
        }
        if output.exists():
            raise RuntimeError(f"refusing to overwrite output path: {output}")
        runtime_output = worktree / "wiki/internal/tickets/evidence/rsch014-E6/runtime-result-20261003.json"
        if PREFLIGHT_ONLY and runtime_output.exists():
            raise RuntimeError(f"runtime result path is not absent: {runtime_output}")

        main_symbols = runtime.symbols(BUILD / "ladybug.map")
        enemy_symbols = runtime.symbols(BUILD / "ladybug-enemy-runtime.map")
        presentation_symbols = runtime.symbols(BUILD / "ladybug-presentation-runtime.map")
        active_symbols = runtime.symbols(BUILD / "ladybug-adaptive-active.map")
        helper_symbols = runtime.symbols(BUILD / "ladybug-enemy-helper-page34.map")
        receipt = load_json(BUILD / "source-build-receipt.json")
        layout = load_json(LAYOUT)
        rom = ROM.read_bytes()
        resident = RESIDENT.read_bytes()
        enemy = ENEMY.read_bytes()
        helper = HELPER.read_bytes()
        presentation = PRESENTATION.read_bytes()
        active = ACTIVE.read_bytes()
        segment = next(item for item in layout["gmc"]["segments"]
                       if item["target"] == "enemy_helper_page34")
        bank = (BUILD / f"ladybug-gmc-bank{segment['bank']}-overflow.bin").read_bytes()
        helper_start = int(segment["source_offset"])
        staged_helper = bank[helper_start:helper_start + int(segment["count"])]
        if len(helper) != 87 or staged_helper != helper:
            raise RuntimeError("authored and staged helper must be the same exact 87 bytes")
        runtime_artifacts = {
            "rom_sha256": sha(rom),
            "build_receipt_sha256": digest_file(BUILD / "source-build-receipt.json"),
            "resident_sha256": sha(resident), "enemy_sha256": sha(enemy),
            "presentation_sha256": sha(presentation), "active_sha256": sha(active),
            "helper_sha256": sha(helper), "staged_helper_sha256": sha(staged_helper),
            "layout_sha256": digest_file(LAYOUT),
            "active_map_sha256": digest_file(BUILD / "ladybug-adaptive-active.map"),
            "main_map_sha256": digest_file(BUILD / "ladybug.map"),
            "xroar_sha256": digest_file(XROAR),
        }
        if (receipt.get("profile") != "complete" or
                sha(rom) != "5d96372e03e6b78670c531f754b36c40a6ea73388cbb822869b41eb149a15458" or
                sha(helper) != "057e2803eac24aebb1447d43614fd4aaf67518d933f08d3f128627e9aeb26526" or
                sha(active) != "8add5b4086f00509e654d3bb47e82ab6a692178b390a73b16f06d46f715971d9" or
                digest_file(XROAR) != preflight["candidate"]["xroar_sha256"] or
                staged_helper != helper):
            raise RuntimeError("exact retained ROM/helper/active/staged-helper identity check failed")
        if (active_symbols.get("adaptive_tick_binding") != 0x0491 or
                helper_symbols.get("enemy_frame_number") != 0xA8D2 or
                helper_symbols.get("efn_cache_guard") != 0xA8A0):
            raise RuntimeError("build map marker addresses differ from reviewed source")
        caller_contracts = []
        for label, source_line in (("draw_enemy_fb", 2618), ("draw_enemy_stage", 3327)):
            caller_pc = enemy_symbols[label]
            caller_offset = caller_pc - ENEMY_WINDOW_START
            call_bytes = enemy[caller_offset:caller_offset + 3]
            if len(call_bytes) != 3 or call_bytes[0] != 0x17:
                raise RuntimeError(f"{label} is not a three-byte LBSR in the current enemy artifact")
            displacement = int.from_bytes(call_bytes[1:3], "big", signed=True)
            return_pc = caller_pc + 3
            target_pc = (return_pc + displacement) & 0xFFFF
            if target_pc != helper_symbols["enemy_frame_number"]:
                raise RuntimeError(f"{label} LBSR does not target mapped enemy_frame_number")
            caller_contracts.append({
                "caller": label, "caller_pc": caller_pc, "caller_bytes": call_bytes.hex(),
                "return_pc": return_pc, "target_pc": target_pc, "source_line": source_line,
            })
        evidence["caller_contracts"] = caller_contracts
        evidence["artifact_identity"] = {
            "worktree": str(worktree), "head": preflight["worktree_head"],
            "rom_expected_sha256": "5d96372e03e6b78670c531f754b36c40a6ea73388cbb822869b41eb149a15458",
            "helper_expected_sha256": "057e2803eac24aebb1447d43614fd4aaf67518d933f08d3f128627e9aeb26526",
            "active_expected_sha256": "8add5b4086f00509e654d3bb47e82ab6a692178b390a73b16f06d46f715971d9",
            "files": runtime_artifacts,
            "helper_staging": {"bank": segment["bank"], "source_offset": helper_start,
                               "destination_page": segment["destination_page"],
                               "destination_address": segment["destination_address"],
                               "count": len(staged_helper), "staged_equals_authored": staged_helper == helper},
            "active_staging_contract": {
                "source_binary": "build/ladybug-adaptive-active.bin",
                "stage_address": 0xB7A5, "stage_physical_page": 0x3D,
                "stage_physical_offset": 0x17A5, "destination_address": 0x038F,
                "length": len(active), "destination_PAR0_required": 0x38,
                "sourcebuild_stage_symbol": "AUDIO_ADAPTIVE_STAGE=$B7A5",
                "sourcebuild_length_symbol": "AUDIO_ADAPTIVE_CODE_BYTES=$025B",
                "mainloop_installer": "src/main.s::adaptive_install_active reads PAR5=$3D, copies AUDIO_ADAPTIVE_STAGE to $038F, restores PAR5=$34",
            },
        }
        evidence["marker_contract"] = {
            "start_dispatch": {"pc": main_symbols["ad_dispatch_work"], "expected": "$C14F"},
            "first_worklist": {"pc": main_symbols["mainloop"], "expected": "$C116"},
            "adaptive_tick_binding": {"pc": active_symbols["adaptive_tick_binding"],
                                       "active_offset": active_symbols["adaptive_tick_binding"] - 0x038F,
                                       "mapping": "PAR0=$38; staged and destination active image byte match required"},
            "enemy_frame_number": {"pc": helper_symbols["enemy_frame_number"],
                                   "mapping": "PAR5=$34; physical and mapped helper image byte match required"},
            "efn_cache_guard": {"pc": helper_symbols["efn_cache_guard"],
                                "source_callsite": "src/enemy_runtime.s::compose_enemy_animation calls efn_cache_guard after efn_preview",
                                "absence_is_not_failure": True},
            "other_known_frontiers": {"enemy_tick": main_symbols.get("enemy_tick"),
                                      "atb_after_player": active_symbols.get("atb_after_player"),
                                      "absence_during_initial_entry_is_not_failure": True},
        }

        if PREFLIGHT_ONLY:
            evidence["phase"]["status"] = "offline-launch-guard-pass-no-runtime-launched"
            evidence["offline_launch_guard"] = {
                "observer_ast_hash": "pass", "windows_git_head": current_head,
                "pinned_files_verified": len(preflight.get("pinned_files", {})),
                "private_control_contract": "pass", "candidate_and_staging_guards": "pass",
                "source_proven_callers": len(caller_contracts),
                "offline_output_path_absent": True,
                "runtime_result_output_path_absent": not runtime_output.exists(),
                "emulator_or_monitor_launched": False,
            }
            print(json.dumps({"status": evidence["phase"]["status"],
                              "result": str(output), "runtime_launched": False}, sort_keys=True))
            return 0

        process, client = runtime.launch_fast(monitor, XROAR, ROM)
        phase_started = time.monotonic()
        deadline = phase_started + 45.0
        evidence["phase"]["started_monotonic"] = phase_started
        evidence["runtime_instance"] = {
            "pid": process.pid, "monitor_peer": client.sock.getpeername(),
            "launch": "private isolated XRoar, null UI/audio, CoCo3 GMC 512K, -no-ratelimit",
            "secondary_preopened_before_phase_wait": False,
        }
        second_sock = socket.create_connection(client.sock.getpeername(), timeout=1.0)
        secondary = monitor.MonitorClient(second_sock)
        hello = json.loads(secondary.file.readline())
        if hello.get("method") != "hello":
            raise RuntimeError(f"secondary monitor hello mismatch: {hello}")
        evidence["runtime_instance"]["secondary_preopened_before_phase_wait"] = True
        evidence["runtime_instance"]["secondary_hello"] = hello
        evidence["runtime_instance"]["secondary_has_breakpoint_subscription"] = False
        evidence["runtime_instance"]["secondary_initial_state"] = monitor_call(
            "get_run_state", client_override=secondary, max_timeout=0.7)

        # Reproduce the approved cold coin/credit/Start route without changing game state directly.
        start = presentation_symbols["start_screen"]
        regs = go(start, "cold attract start_screen")
        if regs.get("pc") != start or regs.get("a") != 0:
            raise RuntimeError(f"cold attract marker mismatch: {regs}")
        go(presentation_symbols["attract_tick"], "live attract tick")
        monitor_call("inject_key", {"key": 5, "action": "press"}, "coin key press")
        regs = go(start, "credit-screen start_screen")
        monitor_call("inject_key", {"key": 5, "action": "release"}, "coin key release")
        if regs.get("a") != 3:
            raise RuntimeError(f"coin edge did not request credit screen: A={regs.get('a')}")
        credits = presentation_symbols["PRES_CREDITS"]
        credit_tick = presentation_symbols["credit_tick"]
        go(credit_tick, "settled-credit tick")
        if read_byte(credits) != 1:
            raise RuntimeError("actual coin path did not create one credit")
        settled_ticks = 0
        while read_byte(0x00D4) != 0 or read_byte(0x0091) != 0:
            go(credit_tick, "high-score/credit presentation settle tick")
            settled_ticks += 1
            if settled_ticks >= 240:
                raise RuntimeError("high-score/credit handoff did not settle in 240 ticks")
        evidence["cold_route"] = {
            "settled_credit_before_start": read_byte(credits),
            "settled_ticks": settled_ticks,
            "transient_state": read_byte(0x00D4), "FB_PENDING": read_byte(0x0091),
        }
        monitor_call("inject_key", {"key": 1, "action": "press"}, "Start key press")
        dispatch = main_symbols["ad_dispatch_work"]
        regs = go(dispatch, "credited-game active dispatcher")
        monitor_call("inject_key", {"key": 1, "action": "release"}, "Start key release")
        dispatch_state = {
            "PC": regs.get("pc"), "PRES_MODE": read_byte(presentation_symbols["PRES_MODE"]),
            "STAGE": read_byte(main_symbols["STAGE"]), "PRES_CREDITS": read_byte(credits),
            "INITIAL_ENTRY_STATE": read_byte(main_symbols["INITIAL_ENTRY_STATE"]),
            "FB_PENDING": read_byte(0x0091),
        }
        if dispatch_state != {"PC": dispatch, "PRES_MODE": 0, "STAGE": 1,
                              "PRES_CREDITS": 0, "INITIAL_ENTRY_STATE": 1, "FB_PENDING": 0}:
            raise RuntimeError(f"credited-game start dispatcher state differs: {dispatch_state}")
        pars = read_pars()
        live_resident = read(0xC000, min(0x3E00, len(resident)))
        live_enemy = read(0x0800, len(enemy))
        live_presentation = read(0x1900, len(presentation))
        active_proof = active_stage_proof(active)
        helper_proof_state = helper_proof(helper, staged_helper)
        pars_low6 = normalized_pars(pars)
        if (pars_low6[6] != 0x3E or pars_low6[7] != 0x3F or
                live_resident != resident[:len(live_resident)] or
                pars_low6[0] != 0x38 or live_enemy != enemy or live_presentation != presentation or
                not active_proof["mapping_valid"] or not helper_proof_state["mapping_valid"]):
            raise RuntimeError("C14F resident/module/helper/active source-stage-destination byte proof failed")
        evidence["C14F_boundary"] = {
            "registers": regs, "state": dispatch_state,
            "PAR0_7_raw": pars, "PAR0_7_low6": pars_low6,
            "resident_live_sha256": sha(live_resident), "resident_expected_sha256": sha(resident[:len(live_resident)]),
            "enemy_live_sha256": sha(live_enemy), "enemy_expected_sha256": sha(enemy),
            "presentation_live_sha256": sha(live_presentation), "presentation_expected_sha256": sha(presentation),
            "active_stage_proof": active_proof, "helper_proof": helper_proof_state,
            "all_pre-run_identity_checks_pass": True,
        }

        breakpoints: dict[str, int] = {}
        targets = {
            "adaptive_tick_binding": active_symbols["adaptive_tick_binding"],
            "efn_cache_guard": HELPER_ADDRESS,
            "enemy_frame_number": helper_symbols["enemy_frame_number"],
            "first_active_worklist": main_symbols["mainloop"],
        }
        for label, address in targets.items():
            breakpoints[label] = set_break(address)
        evidence["breakpoint_ids"] = breakpoints
        wait_started = time.monotonic()
        wait_deadline = min(deadline - RET_CAPTURE_RESERVE, wait_started + PRIMARY_WAIT_LIMIT)
        seen: set[str] = set()
        first_frontier = None
        while time.monotonic() < wait_deadline:
            remaining = wait_deadline - time.monotonic()
            try:
                hit = run_until_breakpoint("first active-worklist frontier", remaining)
            except TimeoutError as exc:
                primary_timed_out = True
                evidence["phase"]["primary_wait_timeout"] = f"{type(exc).__name__}: {exc}"
                break
            pc = hit.get("pc")
            label = next((name for name, addr in targets.items() if addr == pc and name not in seen), None)
            if label is None:
                evidence["phase"]["unexpected_breakpoint"] = hit
                raise RuntimeError(f"unclassified configured breakpoint hit: {hit}")
            if first_frontier is None:
                first_frontier = label
            seen.add(label)
            regs = read_regs()
            marker_pars = read_pars()
            code = code_proof(label, pc, regs, marker_pars, resident, presentation, active, helper)
            if label == "adaptive_tick_binding":
                code["active_stage_proof_at_C14F"] = active_proof
                if not code["symbol_interpretation_allowed"] or not active_proof["mapping_valid"]:
                    raise RuntimeError("adaptive_tick_binding marker lacks source/staged/destination identity")
            elif label in ("efn_cache_guard", "enemy_frame_number"):
                state = helper_proof(helper, staged_helper)
                code["helper_proof_at_marker"] = state
                if not code["symbol_interpretation_allowed"] or not state["mapping_valid"]:
                    raise RuntimeError(f"{label} marker lacks helper physical/mapped identity")
                if label == "enemy_frame_number":
                    entry_s = regs.get("s")
                    if not isinstance(entry_s, int):
                        raise RuntimeError("enemy_frame_number entry lacks a system-stack pointer")
                    stack_window = read(entry_s, 8)
                    stack_top = stack_window[:2]
                    decoded = {
                        "big": int.from_bytes(stack_top, "big"),
                        "little": int.from_bytes(stack_top, "little"),
                    }
                    returns = {item["return_pc"]: item for item in caller_contracts}
                    candidates = [(order, value) for order, value in decoded.items() if value in returns]
                    if len(candidates) != 1:
                        raise RuntimeError(f"helper stack does not name one source-proven caller: {decoded}")
                    byte_order, return_pc = candidates[0]
                    caller = returns[return_pc]
                    caller_offset = caller["caller_pc"] - ENEMY_WINDOW_START
                    caller_live = read(caller["caller_pc"], 3)
                    if (normalized_pars(marker_pars)[0] != 0x38 or
                            caller_live != enemy[caller_offset:caller_offset + 3]):
                        raise RuntimeError("source-proven helper caller bytes or PAR0 identity differ")
                    evidence["helper_entry"] = {
                        "PC": pc, "S": entry_s, "stack_top_hex": stack_top.hex(),
                        "stack_window_hex": stack_window.hex(),
                        "stack_byte_order": byte_order, "caller": caller["caller"],
                        "caller_pc": caller["caller_pc"], "caller_bytes": caller_live.hex(),
                        "return_pc": return_pc, "target_pc": caller["target_pc"],
                        "helper_proof": state,
                    }
                    return_bp = set_break(return_pc)
                    clear_break(breakpoints[label])
                    breakpoints.pop(label)
                    return_hit = run_until_breakpoint("source-proven helper caller return",
                                                      min(12.0, remaining_for_primary("helper return")),
                                                      return_pc)
                    return_regs = read_regs()
                    return_pars_raw = read_pars()
                    return_code = read(return_pc, 3)
                    return_offset = return_pc - ENEMY_WINDOW_START
                    if (return_regs.get("s") != entry_s + 2 or
                            normalized_pars(return_pars_raw)[0] != 0x38 or
                            return_code != enemy[return_offset:return_offset + 3]):
                        raise RuntimeError("helper return stack or live return bytes differ from source artifact")
                    evidence["helper_return"] = {
                        "hit": return_hit, "registers": return_regs,
                        "PAR0_7_raw": return_pars_raw,
                        "PAR0_7_low6": normalized_pars(return_pars_raw),
                        "live_bytes": return_code.hex(), "artifact_bytes_match": True,
                        "stack_advanced_by_two": True, "source_proven_return_pc": return_pc,
                    }
            elif label == "first_active_worklist":
                if not code["symbol_interpretation_allowed"]:
                    raise RuntimeError("first active-worklist PC lacks resident mapping/byte identity")
                if not evidence.get("helper_entry") or not evidence.get("helper_return"):
                    raise RuntimeError("$C116 arrived without source-proven helper entry and return")
            evidence["observations"].append({
                "label": label, "hit": hit, "registers": regs,
                "PAR0_7_raw": marker_pars, "PAR0_7_low6": normalized_pars(marker_pars),
                "code_identity": code,
                "elapsed_after_phase_seconds": round(time.monotonic() - phase_started, 6),
            })
            if label in breakpoints:
                clear_break(breakpoints[label])
            if label == "first_active_worklist":
                evidence["phase"]["status"] = "pass-helper-caller-return-and-first-worklist-marker"
                break
        else:
            primary_timed_out = True
            evidence["phase"]["primary_wait_timeout"] = "40-second/phase-bound wait ended without first-worklist marker"

        evidence["phase"]["first_frontier"] = first_frontier
        evidence["phase"]["observed_frontiers"] = sorted(seen)
        evidence["phase"]["primary_wait_elapsed_seconds"] = round(time.monotonic() - wait_started, 6)
        if evidence["phase"].get("status") != "pass-helper-caller-return-and-first-worklist-marker":
            evidence["phase"]["status"] = "observation-timeout-or-marker-absent"
            evidence["timeout_capture"] = capture_secondary("primary marker absent or primary socket timed out")
        evidence["claims"]["parts_2_through_8_skipped"] = True
        evidence["claims"]["natural_full_maze_progression"] = False
        evidence["claims"]["gameplay_acceptance"] = False
    except Exception as exc:
        fatal = f"{type(exc).__name__}: {exc}"
        evidence["failure"] = fatal
        if process is not None and secondary is not None and deadline and time.monotonic() < deadline:
            evidence["failure_capture"] = capture_secondary("bounded diagnostic failed before marker completion")
        if evidence.get("phase", {}).get("status") == "incomplete":
            evidence["phase"]["status"] = "rejected-before-or-during-marker-probe"
    finally:
        if process is not None:
            try:
                runtime.stop(process)
            except Exception as exc:
                evidence["cleanup_error"] = f"{type(exc).__name__}: {exc}"
            try:
                left = max(0.1, deadline - time.monotonic()) if deadline else 1.0
                process.wait(timeout=min(0.8, left))
            except Exception:
                try:
                    process.kill()
                    process.wait(timeout=0.5)
                except Exception as exc:
                    evidence["process_cleanup_error"] = f"{type(exc).__name__}: {exc}"
        for target in (client, secondary):
            if target is not None:
                try:
                    target.close()
                except Exception as exc:
                    evidence.setdefault("socket_cleanup_errors", []).append(f"{type(exc).__name__}: {exc}")
        if phase_started:
            evidence["phase"]["elapsed_seconds_including_cleanup"] = round(time.monotonic() - phase_started, 6)
            evidence["phase"]["deadline_respected"] = evidence["phase"]["elapsed_seconds_including_cleanup"] <= 45.0
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(json.dumps({
        "status": evidence.get("phase", {}).get("status"),
        "failure": fatal,
        "result": str(output),
        "phase_seconds": evidence.get("phase", {}).get("elapsed_seconds_including_cleanup"),
        "first_frontier": evidence.get("phase", {}).get("first_frontier"),
        "frontiers": evidence.get("phase", {}).get("observed_frontiers"),
    }, sort_keys=True))
    return 1 if fatal else 0


if __name__ == "__main__":
    raise SystemExit(main())
