#!/usr/bin/env python3
"""Offline BUG-117 observer preparation and fixture-write safety gate.

No emulator, monitor, build, or target is started by import, --help,
--prepare-only, or --self-test. Live observation remains deliberately gated
until the parent accepts the exact current-build runtime adapter.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCENARIOS = ("natural", "front-first", "music-first", "prior-music")
PHASE_SECONDS = 45
STOP_WAIT_SECONDS = 10
TIMER_ADDRESS = 0x003A
TIMER_VALUES = {"front-first": 0, "music-first": 255, "prior-music": 0}
ROOT = next((p for p in Path(__file__).resolve().parents if (p / "scripts/build.sh").is_file()), None)


class GuardFailure(RuntimeError):
    pass


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_symbols(path: Path) -> dict[str, int]:
    return {name: int(value, 16) for name, value in re.findall(
        r"^Symbol: (\w+) .* = ([0-9A-Fa-f]+)$", path.read_text(encoding="utf-8"), re.M)}


def stream_terminal(image: bytes, start: int, limit: int) -> dict[str, Any]:
    """Decode linked commands to the emitted zero-command boundary."""
    pos = start
    commands = 0
    while pos < limit:
        op = image[pos]
        if op == 0:
            return {"terminator_offset": pos, "terminal_next_offset": pos + 1,
                    "command_count": commands, "terminator": op}
        if op == 2:
            size = 2
        elif 0x10 <= op <= 0x12:
            size = 4
        elif op == 0x1C:
            size = 3
        elif op in (0x1D, 0x1E):
            size = 2
        else:
            raise GuardFailure(f"unsupported audio command ${op:02X} at image offset ${pos:04X}")
        if pos + size > limit:
            raise GuardFailure("audio command extends past the linked audio image")
        pos += size
        commands += 1
    raise GuardFailure("linked stream has no emitted zero-command terminator")


def require_snapshot(scenario: str, s: dict[str, Any]) -> int:
    """Return the sole approved value, or deny on any absent/false guard."""
    if scenario == "natural":
        raise GuardFailure("natural scenario is strictly no-write")
    if scenario not in TIMER_VALUES:
        raise GuardFailure(f"unknown fixture scenario {scenario!r}")
    common = {
        "timer_map_qualified": True,
        "timer_address": TIMER_ADDRESS,
        "source_map_bytes_qualified": True,
        "render_pending": 0,
        "owner_a_player_valid": 0,
        "owner_b_player_valid": 0,
        "cue_published_busy": 1,
        "cue_actual_output_proven": True,
        "actual_psg_writes_match_mix": True,
    }
    if scenario in ("front-first", "music-first"):
        common.update({
            "entry_state": 3,
            "death_state": 0,
            "player_x": 320,
            "cue_active_id": 6,
            "slot0_id": 6,
            "slot0_policy": 0xB3,
            "slot0_priority": 5,
            "best_slot": 0,
            "best_priority": 5,
            "cue6_selected_voice_mask": 0x07,
            "higher_priority_exclusive_source": False,
        })
        if scenario == "front-first":
            common.update({"cue_dwell_cadence_viable": True})
    else:
        common.update({
            "entry_state": 0,
            "death_state": 3,
            "death_timer": 37,
            "genuine_enemy_contact_proven": True,
            "cue_active_id": 13,
            "slot0_id": 13,
            "slot0_policy": 0xD3,
            "slot0_priority": 6,
            "best_slot": 0,
            "best_priority": 6,
            "cue13_selected_voice_mask": 0x03,
            "higher_priority_exclusive_source": False,
            "cue13_actual_output_proven": True,
            "cue13_published_busy": 1,
        })
    missing = [k for k in common if k not in s]
    if missing:
        raise GuardFailure("missing guards: " + ", ".join(missing))
    wrong = [(k, s[k], v) for k, v in common.items() if s[k] != v]
    if wrong:
        raise GuardFailure("guard mismatch: " + repr(wrong))
    if scenario == "front-first" and (type(s.get("remaining_pad")) is not int or s["remaining_pad"] <= 0):
        raise GuardFailure("front-first requires a measured positive numeric remaining pad")
    if scenario == "prior-music" and (type(s.get("lives")) is not int or s["lives"] <= 0):
        raise GuardFailure("prior-music requires a measured positive numeric reserve")
    if scenario in ("front-first", "music-first"):
        count = s.get("cue6_selected_audible_voice_count")
        if type(count) is not int or count < 1:
            raise GuardFailure("cue6 must contribute at least one selected audible voice")
    if scenario == "prior-music":
        count = s.get("cue13_selected_audible_voice_count")
        if type(count) is not int or count < 1:
            raise GuardFailure("cue13 must contribute at least one selected audible voice")
    return TIMER_VALUES[scenario]


@dataclass(frozen=True)
class Permit:
    scenario: str
    address: int
    value: int


class FixtureWriter:
    """Single-attempt writer; reserves its one write before the monitor call."""
    def __init__(self, scenario: str, timer_address: int):
        self.scenario = scenario
        self.timer_address = timer_address
        self.attempts = 0
        self._permit: Permit | None = None

    def authorize(self, snapshot: dict[str, Any]) -> Permit:
        if self._permit is not None:
            raise GuardFailure("fixture already authorized; use a fresh monitor run")
        value = require_snapshot(self.scenario, snapshot)
        self._permit = Permit(self.scenario, TIMER_ADDRESS, value)
        return self._permit

    def write(self, client: Any, permit: Permit, address: int, value: int) -> None:
        if self.scenario == "natural":
            raise GuardFailure("natural scenario forbids target writes")
        if not isinstance(permit, Permit) or permit is not self._permit:
            raise GuardFailure("fixture permit does not match this scenario")
        if self.timer_address != TIMER_ADDRESS or address != TIMER_ADDRESS or permit.address != TIMER_ADDRESS:
            raise GuardFailure("the only permitted target is map-resolved DEATH_TIMER $003A")
        if value != permit.value or value != TIMER_VALUES[self.scenario]:
            raise GuardFailure("fixture value is outside the approved scenario value")
        if self.attempts:
            raise GuardFailure("fixture write budget already consumed")
        self.attempts += 1
        client.call("write_memory", {"addr": TIMER_ADDRESS, "data": f"{value:02x}"})


REQUIRED_PROOFS = (
    "first_cue6_owned_psg_transaction",
    "first_post_psg_busy_one",
    "cue6_terminal_stream_end_owned",
    "terminal_actual_psg_mute_transaction",
    "terminal_post_psg_busy_zero",
    "final_pose_in_front_after_irq_commit",
    "release_after_audio_and_front_commit",
    "no_same_batch_player_or_enemy_mutation",
)


def acceptance_status(events: dict[str, Any]) -> dict[str, Any]:
    missing = [name for name in REQUIRED_PROOFS if events.get(name) is not True]
    return {"status": "INCOMPLETE" if missing else "OBSERVATIONS_PRESENT",
            "missing_proofs": missing,
            "pass": not missing}


def prepare(build: Path) -> dict[str, Any]:
    build = build.resolve(strict=True)
    names = ("ladybug.rom", "ladybug-runtime.rom", "ladybug.map",
             "ladybug-audio-runtime.bin", "ladybug-audio-runtime.map",
             "ladybug-enemy-runtime.rom", "ladybug-enemy-runtime.map")
    files = {name: build / name for name in names}
    missing = [str(p) for p in files.values() if not p.is_file()]
    if missing:
        raise GuardFailure("candidate build is incomplete: " + ", ".join(missing))
    main, audio, enemy = (read_symbols(files[n]) for n in
                          ("ladybug.map", "ladybug-audio-runtime.map", "ladybug-enemy-runtime.map"))
    required = {
        "main": ("DEATH_TIMER", "DEATH_STATE", "INITIAL_ENTRY_STATE", "PLAYER_CELL_X",
                 "FB_RENDER_PENDING", "FB_COMMIT_SEQ", "FB_FRONT_ID", "PLAYER_FB",
                 "FB_META_A", "FB_META_B"),
        "audio": ("audio_slot0", "audio_mix_periods", "audio_mix_atten", "audio_mix_noise",
                  "audio_mix_shadow", "AUDIO_BEST_SLOT", "AUDIO_BEST_PRI",
                  "AUDIO_MUSIC_PUBLISHED_BUSY", "audio_mix_write", "audio_mix_write_done",
                  "audio_write", "audio_command_end", "gmc_cue_descriptors",
                  "gmc_cue_stream_06", "gmc_cue_stream_13", "gmc_sound_data_end"),
        "enemy": ("fbiq_publish",),
    }
    maps = {"main": main, "audio": audio, "enemy": enemy}
    absent = [f"{domain}.{symbol}" for domain, symbols in required.items()
              for symbol in symbols if symbol not in maps[domain]]
    if absent:
        raise GuardFailure("required map symbols absent: " + ", ".join(absent))
    if main["DEATH_TIMER"] != TIMER_ADDRESS:
        raise GuardFailure(f"DEATH_TIMER map resolves to ${main['DEATH_TIMER']:04X}, not $003A")
    audio_bin = files["ladybug-audio-runtime.bin"].read_bytes()
    source_dir = build.parent / "src"
    sources = {name: source_dir / name for name in
               ("main.s", "audio_runtime.s", "enemy_runtime.s")}
    if any(not p.is_file() for p in sources.values()):
        raise GuardFailure("candidate source audit files are missing beside the build")
    source_text = {name: re.sub(r"\s+", " ", re.sub(r";[^\n]*", " ", p.read_text(encoding="utf-8")))
                   for name, p in sources.items()}
    source_assertions = {
        "main.s": (r"DEATH_TIMER\s+equ\s+\$003A", r"iet_final_wait"),
        "audio_runtime.s": (r"lda\s+,u\s+sta\s+2,y", r"lda\s+2,x\s+bita\s+#1",
                             r"audio_mix_write_done\s+jsr\s+audio_music_busy\s+sta\s+AUDIO_MUSIC_PUBLISHED_BUSY",
                             r"audio_write\s+sta\s+SND_DATA",
                             r"audio_command_end\s+lda\s+#\$FF\s+sta\s+,y\s+rts"),
        "enemy_runtime.s": (r"fbiq_publish\s+sta\s+GIME_VOFF1", r"inc\s+FB_COMMIT_SEQ\+1"),
    }
    checked_source_patterns = {}
    for name, patterns in source_assertions.items():
        for pattern in patterns:
            if not re.search(pattern, source_text[name], re.I):
                raise GuardFailure(f"candidate source invariant missing: {name}: {pattern}")
        checked_source_patterns[name] = {"sha256": sha(sources[name].read_bytes()),
                                         "patterns_checked": list(patterns)}
    desc_index = audio["gmc_cue_descriptors"] - 0xA000 + 6 * 8
    cue6_desc = audio_bin[desc_index:desc_index + 8]
    if len(cue6_desc) != 8 or cue6_desc[0] != 0xB3 or (cue6_desc[0] >> 5) != 5:
        raise GuardFailure("linked cue-6 descriptor does not prove exclusive policy $B3 / priority 5")
    cue6_ptr = int.from_bytes(cue6_desc[4:6], "big")
    if cue6_ptr != audio["gmc_cue_stream_06"] or cue6_desc[6] != 0x07:
        raise GuardFailure("cue-6 linked descriptor pointer/voice mask disagrees with map")
    cue6_end = stream_terminal(audio_bin, cue6_ptr - 0xA000,
                               audio["gmc_sound_data_end"] - 0xA000)
    cue13_desc_index = desc_index + (13 - 6) * 8
    cue13_desc = audio_bin[cue13_desc_index:cue13_desc_index + 8]
    if (len(cue13_desc) != 8 or cue13_desc[0] != 0xD3 or
            int.from_bytes(cue13_desc[4:6], "big") != audio["gmc_cue_stream_13"]):
        raise GuardFailure("linked cue-13 descriptor does not prove exclusive cue-13 routing")
    cue13_end = stream_terminal(audio_bin, audio["gmc_cue_stream_13"] - 0xA000,
                                audio["gmc_sound_data_end"] - 0xA000)
    if audio["audio_mix_write_done"] + 6 > audio["audio_write"]:
        raise GuardFailure("audio post-publication marker ordering is inconsistent with map")
    identity = {name: {"bytes": p.stat().st_size, "sha256": sha(p.read_bytes())}
                for name, p in files.items()}
    return {
        "candidate_build": str(build), "files": identity,
        "candidate_sources": checked_source_patterns,
        "mapped_symbols": {d: {s: maps[d][s] for s in symbols}
                           for d, symbols in required.items()},
        "cue_descriptors": {"cue6_hex": cue6_desc.hex(), "cue6_policy": "exclusive, $B3, priority 5, voice mask $07",
                             "cue13_hex": cue13_desc.hex(), "cue13_policy": "exclusive, $D3, priority 6"},
        "emitted_stream_boundaries": {
            "cue6": {**cue6_end, "stream_start": audio["gmc_cue_stream_06"],
                     "terminator_address": 0xA000 + cue6_end["terminator_offset"],
                     "terminal_x_expected": 0xA000 + cue6_end["terminal_next_offset"]},
            "cue13": {**cue13_end, "stream_start": audio["gmc_cue_stream_13"],
                      "terminator_address": 0xA000 + cue13_end["terminator_offset"],
                      "terminal_x_expected": 0xA000 + cue13_end["terminal_next_offset"]}},
        "timer_write_policy": "one map-resolved $003A write per fresh forced run; natural is no-write",
        "runtime_probe_performed": False,
        "runtime_ready": False,
        "blocked_observable": (
            "The guarded offline preparation and write permit are implemented; the live event loop that "
            "qualifies actual $FF51 stores, terminal stream-end continuity, post-PSG busy publication, "
            "IRQ/FRONT pixel identity, and release ordering is not yet implemented. No runtime pass is asserted."),
    }


def _good(scenario: str) -> dict[str, Any]:
    if scenario in ("front-first", "music-first"):
        d = {"timer_map_qualified": True, "timer_address": TIMER_ADDRESS,
             "source_map_bytes_qualified": True, "render_pending": 0,
             "owner_a_player_valid": 0, "owner_b_player_valid": 0,
             "cue_published_busy": 1, "cue_actual_output_proven": True,
             "actual_psg_writes_match_mix": True, "entry_state": 3,
             "death_state": 0, "player_x": 320, "cue_active_id": 6,
             "slot0_id": 6, "slot0_policy": 0xB3, "slot0_priority": 5,
             "best_slot": 0, "best_priority": 5, "cue6_selected_voice_mask": 7,
             "cue6_selected_audible_voice_count": 1,
             "higher_priority_exclusive_source": False}
        if scenario == "front-first":
            d.update(remaining_pad=1, cue_dwell_cadence_viable=True)
        return d
    return {"timer_map_qualified": True, "timer_address": TIMER_ADDRESS,
            "source_map_bytes_qualified": True, "render_pending": 0,
            "owner_a_player_valid": 0, "owner_b_player_valid": 0,
            "cue_published_busy": 1, "cue_actual_output_proven": True,
            "actual_psg_writes_match_mix": True, "entry_state": 0,
            "death_state": 3, "death_timer": 37, "lives": 1,
            "genuine_enemy_contact_proven": True, "cue_active_id": 13,
            "slot0_id": 13, "slot0_policy": 0xD3, "slot0_priority": 6,
            "best_slot": 0, "best_priority": 6, "cue13_selected_voice_mask": 3,
            "cue13_selected_audible_voice_count": 1,
            "higher_priority_exclusive_source": False,
            "cue13_actual_output_proven": True, "cue13_published_busy": 1}


def self_test() -> dict[str, Any]:
    tested = 0
    for scenario in SCENARIOS:
        good = _good(scenario) if scenario != "natural" else {}
        if scenario == "natural":
            try:
                require_snapshot(scenario, good)
            except GuardFailure:
                tested += 1
                continue
            raise AssertionError("natural scenario unexpectedly received a write permit")
        gate = FixtureWriter(scenario, TIMER_ADDRESS)
        permit = gate.authorize(good)
        assert permit.value == TIMER_VALUES[scenario]
        tested += 1
        if scenario == "front-first":
            bad = dict(good, remaining_pad=0)
            try: require_snapshot(scenario, bad)
            except GuardFailure: tested += 1
            else: raise AssertionError("front-first accepted zero remaining pad")
            bad = dict(good); bad.pop("remaining_pad")
            try: require_snapshot(scenario, bad)
            except GuardFailure: tested += 1
            else: raise AssertionError("front-first accepted a missing remaining-pad observation")
        if scenario == "prior-music":
            bad = dict(good, lives=0)
            try: require_snapshot(scenario, bad)
            except GuardFailure: tested += 1
            else: raise AssertionError("prior-music accepted an empty reserve")
            bad = dict(good); bad.pop("lives")
            try: require_snapshot(scenario, bad)
            except GuardFailure: tested += 1
            else: raise AssertionError("prior-music accepted a missing reserve observation")
        if scenario in ("front-first", "music-first"):
            bad = dict(good, cue6_selected_audible_voice_count=0)
            try: require_snapshot(scenario, bad)
            except GuardFailure: tested += 1
            else: raise AssertionError("fixture accepted cue6 with no selected audible voice")
            bad = dict(good); bad.pop("cue6_selected_audible_voice_count")
            try: require_snapshot(scenario, bad)
            except GuardFailure: tested += 1
            else: raise AssertionError("fixture accepted a missing audible-voice observation")
        if scenario == "prior-music":
            bad = dict(good, cue13_selected_audible_voice_count=0)
            try: require_snapshot(scenario, bad)
            except GuardFailure: tested += 1
            else: raise AssertionError("prior-music accepted cue13 with no selected audible voice")
            bad = dict(good); bad.pop("cue13_selected_audible_voice_count")
            try: require_snapshot(scenario, bad)
            except GuardFailure: tested += 1
            else: raise AssertionError("prior-music accepted missing cue13 audible-voice evidence")
        for key in tuple(good):
            if key in ("remaining_pad", "lives", "cue6_selected_audible_voice_count",
                       "cue13_selected_audible_voice_count"):
                continue
            bad = dict(good)
            del bad[key]
            try:
                require_snapshot(scenario, bad)
            except GuardFailure:
                tested += 1
            else:
                raise AssertionError(f"{scenario}: missing guard {key} was accepted")
            bad = dict(good)
            bad[key] = False if good[key] is True else (good[key] + 1 if isinstance(good[key], int) and not isinstance(good[key], bool) else "wrong")
            try:
                require_snapshot(scenario, bad)
            except GuardFailure:
                tested += 1
            else:
                raise AssertionError(f"{scenario}: invalid guard {key} was accepted")

    class FakeClient:
        def __init__(self): self.calls = []
        def call(self, method: str, params: dict[str, Any]): self.calls.append((method, params)); return {}

    for scenario in TIMER_VALUES:
        fake = FakeClient()
        gate = FixtureWriter(scenario, TIMER_ADDRESS)
        permit = gate.authorize(_good(scenario))
        gate.write(fake, permit, TIMER_ADDRESS, permit.value)
        assert fake.calls == [("write_memory", {"addr": TIMER_ADDRESS, "data": f"{permit.value:02x}"})]
        try: gate.write(fake, permit, TIMER_ADDRESS, permit.value)
        except GuardFailure: tested += 1
        else: raise AssertionError("writer allowed the approved timer write more than once")
        for addr, val in ((0x003B, permit.value), (TIMER_ADDRESS, permit.value ^ 1)):
            try: gate.write(fake, permit, addr, val)
            except GuardFailure: tested += 1
            else: raise AssertionError("writer accepted an unapproved target/value or second write")
        assert len(fake.calls) == 1
        tested += 1
    for scenario in SCENARIOS:
        state = acceptance_status({})
        assert state["pass"] is False and len(state["missing_proofs"]) == len(REQUIRED_PROOFS)
        tested += 1
    return {"self_test": "PASS", "negative_checks": tested,
            "target_write_calls": "fake client only; exactly one $003A approved write tested per fixture",
            "emulator_launches": 0, "target_writes": 0}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-build", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--scenario", choices=SCENARIOS)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        print(json.dumps(self_test(), indent=2))
        return 0
    if not args.prepare_only:
        print(json.dumps({"status": "BLOCKED", "runtime_ready": False,
                          "reason": "live runtime event loop is not implemented; no monitor or emulator launched"}, indent=2))
        return 2
    if args.candidate_build is None or args.output_dir is None or args.scenario is None:
        parser.error("--prepare-only requires --candidate-build, --output-dir, and --scenario")
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = prepare(args.candidate_build)
    report.update({
        "scenario": args.scenario,
        "prepared_at": "pre-runtime; no emulator launch and no target writes",
        "output_dir": str(output),
        "deadlines_seconds": {"each_phase": PHASE_SECONDS, "monitor_stop_wait_max": STOP_WAIT_SECONDS},
        "exact_runtime_command_shape": (
            "python runtime-observer-20261012.py --candidate-build <integrated-build> "
            "--output-dir <fresh-scenario-dir> --scenario <natural|front-first|music-first|prior-music>"),
        "acceptance_proofs_required": list(REQUIRED_PROOFS),
    })
    report_path = output / f"bug117-{args.scenario}-preparation.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PREPARED_WITH_BLOCKER", "report": str(report_path),
                      "runtime_ready": False, "blocked_observable": report["blocked_observable"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
