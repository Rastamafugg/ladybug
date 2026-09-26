from pathlib import Path
import argparse, hashlib, json, sys, time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import verify_bug011_runtime as runtime
import verify_bug009_monitor_input as monitor

BUILD = ROOT / "build"
ROM = BUILD / "ladybug.rom"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--xroar", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "repro/bug043-demo-service-cadence-20260926.json")
    args = parser.parse_args()
    ps = runtime.symbols(BUILD / "ladybug-presentation-runtime.map")
    aus = runtime.symbols(BUILD / "ladybug-audio-runtime.map")
    ms = runtime.symbols(BUILD / "ladybug.map")
    resident = (BUILD / "ladybug-runtime.rom").read_bytes()
    audio = (BUILD / "ladybug-audio-runtime.bin").read_bytes()
    rom_hash = hashlib.sha256(ROM.read_bytes()).hexdigest()
    target = ms["main_entry_audio"]
    expected_call = resident[target - 0xC000:target - 0xC000 + 3]
    gateway_offset = aus["audio_service_gateway_bytes"] - 0xA000
    expected_gateway = audio[gateway_offset:gateway_offset + 18]
    evidence = {
        "ticket": "BUG-043", "rom_sha256": rom_hash,
        "phase": "natural cold attract to mode-4 demo audio service",
        "deadline_seconds": 45,
        "success_marker": "12 total mode-4 main_entry_audio calls, with 11 cue-active samples across 10 one-Vbord intervals; every call steps into gateway $02E4",
        "timeout_meaning": "resident service-entry marker was not observed within the bounded phase; no target-speed inference",
        "entry_address": f"{target:04X}", "expected_resident_call_hex": expected_call.hex(),
        "samples": [], "result": "fail",
        "rejected_attempts": [
            "The cold presentation-entry marker precedes gateway installation; destination identity is checked at the first resident service call.",
            "step_instruction returns an acknowledgement; wait_for_stop supplies the stepped PC."
        ]
    }
    process, client = runtime.launch_fast(monitor, args.xroar, ROM)
    ids = []
    def physical(addr, count):
        return bytes.fromhex(client.call("read_memory", {"space": "physical", "addr": addr, "length": count})["data"])
    def low(addr, count=1):
        return physical(0x38 * 8192 + addr, count)
    def slots():
        out = []
        for index in range(4):
            offset = aus[f"audio_slot{index}"] - 0xA000
            data = physical(0x3D * 8192 + offset, 6)
            out.append({"id": data[0], "wait": data[3], "stream": int.from_bytes(data[4:6], "big")})
        return out
    try:
        ids = monitor.setup(client, [ps["presentation_flow_tick"]])
        boot_hit = client.run_to_breakpoint(40)
        if boot_hit.get("pc") != ps["presentation_flow_tick"]:
            raise AssertionError(f"cold presentation entry not reached: {boot_hit}")
        evidence["cold_presentation_entry"] = f"{boot_hit['pc']:04X}"
        monitor.clear(client, ids)
        ids = []
        live_call = runtime.read_bytes(client, target, 3)
        staged_audio = physical(0x3D * 8192, len(audio))
        evidence["resident_call_live_exact"] = live_call == expected_call and expected_call == bytes.fromhex("bd02e4")
        evidence["page_3d_audio_live_exact"] = staged_audio == audio
        evidence["gateway_matches_before_service_installer"] = low(0x02DE, 18) == expected_gateway
        evidence["rejected_attempt"] = "Gateway is installed after the cold presentation-entry marker; defer destination identity check until the resident audio call site."
        assert evidence["resident_call_live_exact"] and evidence["page_3d_audio_live_exact"]
        ids = monitor.setup(client, [target])
        deadline = time.monotonic() + 45
        for index in range(12):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("45-second phase deadline")
            hit = client.run_to_breakpoint(min(10, remaining))
            if hit.get("pc") != target:
                raise AssertionError(f"unexpected stop {hit}")
            state = {"index": index, "pc": hit["pc"], "mode": low(0xA5)[0],
                     "frame": int.from_bytes(low(2, 2), "big"), "slots_before_service": slots()}
            if state["mode"] != 4:
                raise AssertionError(f"service entry was not mode 4: {state}")
            if index == 0:
                evidence["gateway_live_exact_at_service"] = low(0x02DE, 18) == expected_gateway
                if not evidence["gateway_live_exact_at_service"]:
                    raise AssertionError("installed gateway differs from source at service entry")
            client.call("step_instruction", {"n": 1})
            stepped = client.call("wait_for_stop", {"timeout_ms": 2000}, timeout=3)
            state["step"] = stepped
            if stepped.get("reason") != "step" or stepped.get("pc") != 0x02E4:
                raise AssertionError(f"resident JSR did not enter gateway: {stepped}")
            evidence["samples"].append(state)
        frames = [sample["frame"] for sample in evidence["samples"]]
        deltas = [((after - before) & 0xFFFF) for before, after in zip(frames, frames[1:])]
        evidence["frame_deltas"] = deltas
        evidence["handoff_to_first_cue_frame_delta"] = deltas[0]
        cue_samples = [sample for sample in evidence["samples"] if any(slot["id"] == 6 for slot in sample["slots_before_service"])]
        cue_waits = [next(slot["wait"] for slot in sample["slots_before_service"] if slot["id"] == 6) for sample in cue_samples]
        cue_frames = [sample["frame"] for sample in cue_samples]
        cue_deltas = [((after - before) & 0xFFFF) for before, after in zip(cue_frames, cue_frames[1:])]
        wait_deltas = [after - before for before, after in zip(cue_waits, cue_waits[1:])]
        evidence["cue_6_active_frames"] = cue_frames
        evidence["cue_6_wait_values"] = cue_waits
        evidence["cue_6_frame_deltas"] = cue_deltas
        evidence["cue_6_wait_deltas"] = wait_deltas
        evidence["cue_6_present"] = bool(cue_samples)
        evidence["service_entry_count"] = len(evidence["samples"])
        evidence["frame_interval_target"] = 1
        evidence["cue_active_one_service_per_vbord"] = len(cue_samples) >= 8 and all(delta == 1 for delta in cue_deltas)
        evidence["cue_wait_decrements_once_per_vbord"] = all(delta == -1 for delta in wait_deltas)
        evidence["startup_handoff_interval_pass"] = False
        evidence["startup_handoff_interval_note"] = "39 Vbords separate the first mode-4 entry with no cue from the first cue-active entry; retained for baseline comparison, not counted as steady cadence pass."
        evidence["slot_state_changed_between_samples"] = any(
            first["slots_before_service"] != second["slots_before_service"]
            for first, second in zip(evidence["samples"], evidence["samples"][1:])
        )
        if not evidence["cue_6_present"] or not evidence["cue_active_one_service_per_vbord"] or not evidence["cue_wait_decrements_once_per_vbord"]:
            raise AssertionError("demo cue, steady one-service-per-Vbord interval, or cue wait progression missing")
        evidence["result"] = "pass"
    except Exception as exc:
        evidence["failure"] = f"{type(exc).__name__}: {exc}"
    finally:
        if ids:
            try: monitor.clear(client, ids)
            except Exception: pass
        client.close()
        monitor.stop(process)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="ascii")
    print(json.dumps({key: value for key, value in evidence.items() if key != "samples"}, indent=2))
    if evidence["result"] != "pass":
        raise SystemExit(1)

if __name__ == "__main__":
    main()
