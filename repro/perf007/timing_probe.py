"""Bounded colour-only worklist attribution using existing snapshot/trace helpers."""
import sys,time,json,hashlib,subprocess,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import capture_performance_baseline as c
import verify_performance_baseline as v
from patch_snapshot_state import patch_snapshot
from read_snapshot import find_ram,cpu_to_phys
OUT=Path(sys.argv[1]).resolve();OUT.mkdir(parents=True,exist_ok=False)
IDENTITY=Path(sys.argv[2]).resolve()
start=time.monotonic()
report={'marker':'perf007_colour_cost_attributed','deadline_seconds':60,'passed':False,'rom_sha256':hashlib.sha256(c.ROM.read_bytes()).hexdigest()}
def run(arguments,output):
    remaining=58-(time.monotonic()-start)
    if remaining<=0:raise TimeoutError('measurement observation boundary')
    with output.open('w') as stream:
        p=subprocess.run(c.xroar_base()+arguments,stdout=stream,stderr=subprocess.STDOUT,timeout=remaining)
    if p.returncode:raise RuntimeError('XRoar capture failed: '+str(output))
c.run_xroar=run
try:
    identity=json.loads(IDENTITY.read_text())
    assert identity['passed'] and identity['rom_sha256']==report['rom_sha256']
    frame=c.symbol(c.BUILD/'ladybug.map','main_game_tick_normal')
    stop=frame
    fresh=OUT/'fresh.sna'
    c.capture_snapshot(fresh,frame,20)
    ram=find_ram(fresh.read_bytes())
    for address,path,size in [(0xc000,c.BUILD/'ladybug-runtime.rom',0x3e00),(0x800,c.BUILD/'ladybug-enemy-runtime.rom',(c.BUILD/'ladybug-enemy-runtime.rom').stat().st_size)]:
        expected=path.read_bytes()[:size]
        actual=bytes(ram[cpu_to_phys(address+i)] for i in range(size))
        assert actual==expected,('fresh snapshot artifact mismatch',path)
    for filename,page in [('ladybug-enemy-sparse.bin',0x35),('ladybug-player-sparse.bin',0x39)]:
        expected=(c.BUILD/filename).read_bytes()
        assert bytes(ram[page*8192:page*8192+len(expected)])==expected,('live sparse asset mismatch',filename)
    main=v.symbols(c.BUILD/'ladybug.map');enemy=v.symbols(c.BUILD/'ladybug-enemy-runtime.map')
    def assignment(label,value,offset=0):
        return f'{int(main.get(label,enemy.get(label)),16)+offset:04X}={value:02X}'
    common=[assignment(label,0) for label in ['RENDER_FLAGS','RENDER_FLAGS2','ENEMY_RENDER_FLAGS','DEATH_STATE','INITIAL_ENTRY_STATE']]
    common += [assignment('FB_META_A',0,int(enemy['FBM_DAMAGE'],16)),assignment('FB_META_B',0,int(enemy['FBM_DAMAGE'],16))]
    results=[]
    report['initial_entity_records_hex']=bytes(ram[cpu_to_phys(0xa380):cpu_to_phys(0xa380)+48]).hex()
    for name,timer in [('unchanged-background',0x7fff),('colour-only-current-and-replay',1)]:
        snap=OUT/(name+'.sna');trace=OUT/(name+'.trace')
        patch_snapshot(fresh,snap,common+[assignment('BONUS_TIMER',timer>>8),assignment('BONUS_TIMER',timer&255,1)])
        c.capture_trace(snap,trace,stop,3)
        sections=v.trace_sections(trace,f'{frame:04x}')
        measured=[]
        entries={k:main[k] for k in ['erase_entity_footprints','repair_settled_entity_gates','draw_entities','draw_entity_object','cache_entity_overlay','bonus_color_tick','sync_entity_cache_colour','render_entity_colour']}
        entries.update({k:enemy[k] for k in ['compose_enemy_zone','rub_full','roam_copy_fb_to_bg','framebuffer_project_damage','framebuffer_finish_back','fbiq_publish','fbiq_missed','fbp_write_front_fault']})
        for index,s in enumerate(sections):
            measured.append({'sequence_index':index,'active_cycles':s['active_cycles'],'sync_wait_cycles':s['sync_wait_cycles'],'entry_counts':{k:s['pcs'].count(a) for k,a in entries.items()}})
        results.append({'scenario':name,'intervals':measured,'trace_sha256':hashlib.sha256(trace.read_bytes()).hexdigest()})
    report['results']=results
    report['coverage_limit']='Candidate identical snapshot starts, normal game tick through next normal game tick including logic/render/readiness/IRQ publication and audio stub; idle SYNC excluded. Not matched baseline; four-roam and conditional-upper fixtures still missing. Forced timer is not natural input evidence.'
    counts=[i['entry_counts'] for i in results[1]['intervals']]
    assert counts and any(x['render_entity_colour'] for x in counts),'colour worklist not observed'
    report['observed_active_max_cycles']=max(i['active_cycles'] for s in results for i in s['intervals'])
    report['hardware_target_cycles']=29666
    report['meets_observed_target']=report['observed_active_max_cycles']<=29666
    report['acceptance_passed']=False
    report['required_missing_cases']=['matched-eight-live-current-replay','matched-four-roam-current-replay','conditional-upper-nest-current-replay']
    report['measurement_completed']=True
    report['passed']=report['acceptance_passed']
except BaseException as exc:
    report['error']=str(exc)
finally:
    report['duration_seconds']=time.monotonic()-start
    (OUT/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report),flush=True)
sys.exit(0 if report.get('acceptance_passed') else 1)
