#!/usr/bin/env python3
"""Verify BUG-011 generated choreography and development runtime wiring."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRESENTATION = ROOT / "build/ladybug-presentation.json"
LAYOUT = ROOT / "build/ladybug-sparse-layout.json"
HELPER = ROOT / "build/ladybug-instruction-runtime.bin"
HELPER_MAP = ROOT / "build/ladybug-instruction-runtime.map"
MODULE = ROOT / "build/ladybug-presentation-runtime.bin"
MODULE_SOURCE = ROOT / "src/presentation_runtime.s"
HELPER_SOURCE = ROOT / "src/instruction_runtime.s"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def symbols(path: Path) -> dict[str, int]:
    return {
        name: int(value, 16)
        for name, value in re.findall(
            r"^Symbol: (\w+) .* = ([0-9A-Fa-f]+)$",
            path.read_text(encoding="utf-8"), re.MULTILINE,
        )
    }


def main() -> None:
    presentation = json.loads(PRESENTATION.read_text(encoding="ascii"))
    layout = json.loads(LAYOUT.read_text(encoding="ascii"))
    choreography = presentation["instruction_choreography"]
    events = choreography["events"]
    helper = HELPER.read_bytes()
    module = MODULE.read_bytes()
    helper_symbols = symbols(HELPER_MAP)

    names = [event["name"] for event in events]
    expected_names = list("EXTRA") + list("SPECIAL") + [
        "heart_x2", "heart_x3", "heart_x5", "skull",
    ]
    if names != expected_names:
        raise SystemExit(f"BUG-011 proof: event order differs: {names}")
    if choreography["colour_dwell_frames"] != 30:
        raise SystemExit("BUG-011 proof: colour dwell is not 30 frames")
    if (
        choreography["death_collision_tick"] != 1632 or
        choreography["angel_tick"] != 1727 or
        choreography["next_screen_tick"] != 1792
    ):
        raise SystemExit("BUG-011 proof: death/angel/handoff timing differs")
    expected_goals = [
        0x4334, 0x433C, 0x4344, 0x434C, 0x4354,
        0x5234, 0x523C, 0x5244, 0x524C, 0x5254, 0x525C, 0x5264,
        0x6134, 0x6144, 0x6154, 0x6170,
    ]
    for event, expected_goal in zip(events, expected_goals):
        if event["motion_tick"] >= event["consume_tick"]:
            raise SystemExit(f"BUG-011 proof: nonpositive motion interval for {event['name']}")
        if event["goal_destination"] != expected_goal:
            raise SystemExit(f"BUG-011 proof: authored actor stop differs for {event['name']}")
    aligned = (0, 5, 12, 13, 14)
    if [events[index]["motion_tick"] for index in aligned] != [
        121, 631, 1321, 1411, 1501,
    ]:
        raise SystemExit("BUG-011 proof: row trigger-colour motion edges differ")
    for index, trigger in ((0, 2), (5, 1), (12, 3), (13, 3), (14, 3)):
        tick = events[index]["motion_tick"]
        colour = ((tick - 1) % 90) // 30 + 1
        if colour != trigger or (tick - 1) % 30:
            raise SystemExit("BUG-011 proof: first row movement is off its colour edge")
    if (events[5]["motion_tick"] - events[4]["consume_tick"] < 90 or
            events[12]["motion_tick"] - events[11]["consume_tick"] < 90):
        raise SystemExit("BUG-011 proof: row 2/3 full-cycle waits are too short")
    if choreography["anchors"] != [0x4328, 0x5228, 0x6128]:
        raise SystemExit("BUG-011 proof: actor baseline conversion differs")
    if choreography["angel_destination"] != 0x6170:
        raise SystemExit("BUG-011 proof: authored angel destination differs")
    if choreography["angel_source_code"] != 88:
        raise SystemExit("BUG-011 proof: authored wings marker resolves incorrectly")
    if (choreography["cucumber_destination"] != 0x5C80 or
            choreography["cucumber_source_code"] != 64):
        raise SystemExit("BUG-011 proof: authored cucumber marker resolves incorrectly")
    if any(event["hud_destination"] == 0 for event in events[:15]):
        raise SystemExit("BUG-011 proof: a collectible lacks its HUD destination")
    if events[-1]["hud_destination"] != 0:
        raise SystemExit("BUG-011 proof: skull unexpectedly has a HUD destination")
    if any(event["hud_tile_2_id"] for event in events[:12]):
        raise SystemExit("BUG-011 proof: a letter has an unexpected second HUD tile")
    if any(not event["hud_tile_2_id"] for event in events[12:15]):
        raise SystemExit("BUG-011 proof: a multiplier lacks its second HUD tile")
    for offset, length in zip(
        choreography["colour_stream_offsets"],
        choreography["colour_stream_bytes"],
    ):
        if offset % 0x2000 + length > 0x2000:
            raise SystemExit("BUG-011 proof: a colour stream crosses a cold page")

    runtime = layout["instruction_runtime"]
    if runtime != {
        **runtime,
        "bytes": len(helper),
        "staged_bytes": 0x3AA,
        "stage_page": 0x23,
        "stage_address": 0xA422,
        "destination_address": 0x0300,
        "destination_end": 0x06AA,
        "sha256": digest(helper),
        "staged_sha256": digest(helper.ljust(0x3AA, b"\x00")),
    }:
        raise SystemExit("BUG-011 proof: instruction runtime manifest differs")
    if len(helper) > 0x3AA:
        raise SystemExit("BUG-011 proof: instruction runtime exceeds loader RAM")
    if helper_symbols.get("instruction_runtime_tick") != 0x0300:
        raise SystemExit("BUG-011 proof: instruction runtime entry is not $0300")
    if helper_symbols.get("instruction_runtime_end", 0) > 0x06AA:
        raise SystemExit("BUG-011 proof: instruction runtime crosses $06AA")
    if len(module) > 1280:
        raise SystemExit("BUG-011 proof: presentation director crosses $1E00")

    module_source = MODULE_SOURCE.read_text(encoding="ascii")
    helper_source = HELPER_SOURCE.read_text(encoding="ascii")
    for fragment in (
        "install_instruction_runtime", "lda     #$23", "ldx     #$A422", "ldy     #$0300",
        "cmpy    #$06AA", "jsr     INSTRUCTION_RUNTIME_TICK",
        "LADYBUG_PROFILE", "BUG011_DEVELOPMENT_PROFILE",
    ):
        source = module_source if fragment != "LADYBUG_PROFILE" else (
            ROOT / "scripts/build.sh"
        ).read_text(encoding="utf-8")
        if fragment not in source:
            raise SystemExit(f"BUG-011 proof: missing development wiring {fragment}")
    for fragment in (
        "recolour_collectibles", "draw_value", "draw_life_reward",
        "draw_coin_reward", "draw_multipliers", "present_player",
        "present_death", "PRESENTATION_INSTRUCTION_DEATH_POINTERS",
    ):
        if fragment not in helper_source:
            raise SystemExit(f"BUG-011 proof: missing runtime operation {fragment}")

    if not re.search(
        r"start_screen_map.*?cmpa\s+#PRESENTATION_MAP_ATTRACT.*?"
        r"cmpa\s+#PRESENTATION_MAP_INSTRUCTIONS.*?"
        r"jsr\s+PRESENTATION_HOLD_BEGIN",
        module_source, re.DOTALL,
    ):
        raise SystemExit(
            "BUG-011 proof: instruction load does not hydrate both framebuffer owners"
        )
    if not re.search(
        r"instructions_tick\s+lda\s+PRES_HOLD_STATE\s+"
        r"cmpa\s+#PRES_HOLD_FINAL.*?clr\s+PRES_HOLD_STATE",
        module_source, re.DOTALL,
    ):
        raise SystemExit(
            "BUG-011 proof: instruction mode does not release completed hydration"
        )
    if not re.search(
        r"present_player.*?anda\s+#3\s+adda\s+#4\s+"
        r"sta\s+PRES_ACTOR_FRAME",
        helper_source, re.DOTALL,
    ):
        raise SystemExit("BUG-011 proof: instruction player is not east-facing")
    for routine, end in (("present_player", "irt_death"),
                         ("present_death", "death_frame_published")):
        body = helper_source[
            helper_source.index(f"\n{routine}\n"):
            helper_source.index(f"\n{end}\n")
        ]
        if not re.search(
            r"ldd\s+PRES_OUT\s+std\s+PLAYER_FB\s+"
            r"jsr\s+PRES_MAIN_SAVE_PLAYER", body,
        ):
            raise SystemExit(
                f"BUG-011 proof: {routine} save-under differs from draw destination"
            )
        if "subd    #160" in body:
            raise SystemExit(
                f"BUG-011 proof: {routine} retains displaced save-under"
            )
    init_body = helper_source[
        helper_source.index("\nirt_init\n"):
        helper_source.index("\nirt_complete\n")
    ]
    if "PLAYER_BG_PTR" in init_body:
        raise SystemExit(
            "BUG-011 proof: initialization overrides owner-selected save-under"
        )
    restore_body = helper_source[
        helper_source.index("\nrestore_actor\n"):
        helper_source.index("\npresent_player\n")
    ]
    if not re.search(r"lda\s+#\$34\s+sta\s+PAR5", restore_body):
        raise SystemExit(
            "BUG-011 proof: actor save-under does not restore page-34 state"
        )

    colour = 1
    transitions = {}
    for tick in range(1, choreography["death_collision_tick"] + 1):
        if tick > 1 and (tick - 1) % choreography["colour_dwell_frames"] == 0:
            colour = colour % 3 + 1
            transitions[tick] = colour
    triggers = {event["consume_tick"]: event["name"] for event in events}
    if len(triggers) != 16:
        raise SystemExit("BUG-011 proof: consume ticks are not unique")
    death_indices = [0] * 30 + [index for index in range(1, 14) for _ in range(5)]
    if len(death_indices) != choreography["angel_tick"] - choreography["death_collision_tick"]:
        raise SystemExit("BUG-011 proof: death surface schedule is incomplete")

    print(
        "BUG-011 proof: 16 generated events, 30-frame colour clock, "
        "life/coin/X2-X3-X5 outcomes, 30+13x5 death schedule, held angel, "
        "east player, exact save-under, dual-owner instruction hydration, "
        f"helper {len(helper)}/938, director {len(module)}/1280, "
        f"GMC spare {layout['gmc']['spare_bytes']}"
    )



def current_row_entry():
    import argparse, subprocess, sys
    parser=argparse.ArgumentParser(description="Current-profile approved BUG-067 row-entry contract")
    parser.add_argument('--current-row-entry',action='store_true')
    parser.add_argument('--build-dir',type=Path,default=ROOT/'build')
    parser.add_argument('--mode',choices=('baseline','no-row-wait'),default='no-row-wait')
    parser.add_argument('--baseline-manifest',type=Path,required=True)
    parser.add_argument('--static-only',action='store_true')
    parser.add_argument('--adapter',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    manifest=json.loads((args.build_dir/'ladybug-presentation.json').read_text())
    baseline=json.loads(args.baseline_manifest.read_text())
    current=manifest['instruction_choreography'];prior=baseline['instruction_choreography']
    target_motion=(129,227,323,419,515,577,675,771,867,963,1059,1155,1217,1313,1409,1489)
    target_consume=(152,242,338,434,530,600,690,786,882,978,1074,1170,1240,1344,1440,1544)
    old_motion=(129,227,323,419,515,673,771,867,963,1059,1155,1251,1409,1505,1601,1681)
    old_consume=(152,242,338,434,530,696,786,882,978,1074,1170,1266,1432,1536,1632,1736)
    expected_names=list('EXTRA')+list('SPECIAL')+['heart_x2','heart_x3','heart_x5','skull']
    assert len(current['events'])==len(prior['events'])==16
    assert [event['name'] for event in current['events']]==expected_names
    assert [event['motion_tick'] for event in prior['events']]==list(old_motion)
    assert [event['consume_tick'] for event in prior['events']]==list(old_consume)
    motion,consume=(old_motion,old_consume) if args.mode=='baseline' else (target_motion,target_consume)
    assert current['colour_dwell_frames']==prior['colour_dwell_frames']==32
    for i,(event,previous) in enumerate(zip(current['events'],prior['events'])):
        assert event['motion_tick']==motion[i] and event['consume_tick']==consume[i]
        assert all(event[k]==previous[k] for k in previous if k not in ('motion_tick','consume_tick'))
        assert consume[i]>motion[i]
        if i<15: assert ((consume[i]-1)//32)%3+1==(2 if i<5 else 1 if i<12 else 3)
    for i,colour in ((0,2),(5,1),(12,3),(13,3),(14,3)):
        assert (motion[i]-1)%32==0 and ((motion[i]-1)//32)%3+1==colour
    gaps=[motion[i]-consume[i-1] for i in (5,12)]
    assert gaps==([143,143] if args.mode=='baseline' else [47,47])
    assert [consume[i]-consume[i-1] for i in (5,12)]==([166,166] if args.mode=='baseline' else [70,70])
    assert current['next_screen_tick']==(1896 if args.mode=='baseline' else 1704)
    # Ending phases must follow the moved skull without indexing beyond death art.
    assert current['death_collision_tick']==consume[-1]
    assert current['angel_tick']-current['death_collision_tick']==95
    assert current['next_screen_tick']-current['angel_tick']==65
    count=len(current['death_stream_offsets'])
    assert count==15
    death=current['death_collision_tick'];angel=current['angel_tick']
    indices=[0 if tick<death+30 else 1+(tick-death-30)//5 for tick in range(death,angel)]
    assert min(indices)==0 and max(indices)==count-2
    assert all(0<=index<count for index in indices)
    for name in ('anchors','colour_stream_bytes','colour_stream_offsets','multiplier_destinations'):
        assert current[name]==prior[name]
    proof={'status':'PASS-STATIC','mode':args.mode,'units':'generated schedule ticks, not arcade display frames','first_motion_ticks':[motion[i] for i in (0,5,12)],'later_row_motion_gaps':gaps,'next_screen_tick':current['next_screen_tick'],'events_checked':16,'unchanged_other_event_fields':True,'ending_intervals':[95,65],'death_indices_before_angel':[min(indices),max(indices)],'death_table_count':count,'manifest_sha256':digest((args.build_dir/'ladybug-presentation.json').read_bytes()),'baseline_manifest_sha256':digest(args.baseline_manifest.read_bytes())}
    if not args.static_only:
        assert args.adapter and args.adapter.is_file(),'current GDB adapter required'
        assert args.build_dir.resolve()==(ROOT/'build').resolve(),'runtime requires this worktree complete build'
        assert not args.output.exists(),'fresh runtime output required'
        sha=digest((ROOT/'build/ladybug.rom').read_bytes())
        subprocess.run([sys.executable,str(args.adapter),'--worktree',str(ROOT),'--rom-sha256',sha,'--instructions-row-entry','--output',str(args.output)],check=True)
        live=json.loads(args.output.read_text());assert live['status']=='PASS' and live['rom_sha256']==sha
        proof['status']='PASS-STATIC-AND-NATURAL';proof['runtime_receipt_sha256']=digest(args.output.read_bytes())
        live['static_contract']=proof;args.output.write_text(json.dumps(live,indent=2)+'\n')
    else:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        assert not args.output.exists(),'fresh static output required'
        args.output.write_text(json.dumps(proof,indent=2)+'\n')
    print(json.dumps(proof))

if __name__ == "__main__":
    import sys
    if '--current-row-entry' in sys.argv:
        current_row_entry()
    else:
        main()
