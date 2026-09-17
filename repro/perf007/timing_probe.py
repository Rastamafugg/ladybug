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
    identity=json.loads((ROOT/'repro/perf007/identity-002/result.json').read_text())
    assert identity['passed'] and identity['rom_sha256']==report['rom_sha256']
    frame=c.symbol(c.BUILD/'ladybug-enemy-runtime.map','frame_render_impl')
    stop=c.symbol(c.BUILD/'ladybug.map','main_render')
    fresh=OUT/'fresh.sna'
    c.capture_snapshot(fresh,frame,20)
    ram=find_ram(fresh.read_bytes())
    for address,path,size in [(0xc000,c.BUILD/'ladybug-runtime.rom',0x3e00),(0x800,c.BUILD/'ladybug-enemy-runtime.rom',4080)]:
        expected=path.read_bytes()[:size]
        actual=bytes(ram[cpu_to_phys(address+i)] for i in range(size))
        assert actual==expected,('fresh snapshot artifact mismatch',path)
    main=v.symbols(c.BUILD/'ladybug.map');enemy=v.symbols(c.BUILD/'ladybug-enemy-runtime.map')
    common=['0030=7F','0031=FF','007F=00','0080=00','0087=00','0088=00','008A=00','008C=00','008D=00','008E=00','A901=00','AA01=00']
    results=[]
    for name,flag in [('unchanged-background',0),('colour-only-current-and-replay',int(main['RF_ENTITIES'],16))]:
        snap=OUT/(name+'.sna');trace=OUT/(name+'.trace')
        patch_snapshot(fresh,snap,common+[f'007F={flag:02X}'])
        c.capture_trace(snap,trace,stop,3)
        sections=v.trace_sections(trace,f'{frame:04x}')
        measured=[]
        entries={k:main[k] for k in ['erase_entity_footprints','repair_settled_entity_gates','draw_entities','draw_entity_object','cache_entity_overlay']}
        entries.update({k:enemy[k] for k in ['compose_enemy_zone','rub_full','roam_copy_fb_to_bg','framebuffer_project_damage']})
        for index,s in enumerate(sections):
            measured.append({'sequence_index':index,'active_cycles':s['active_cycles'],'sync_wait_cycles':s['sync_wait_cycles'],'entry_counts':{k:s['pcs'].count(a) for k,a in entries.items()}})
        results.append({'scenario':name,'intervals':measured,'trace_sha256':hashlib.sha256(trace.read_bytes()).hexdigest()})
    report['results']=results
    report['coverage_limit']='Controlled identical snapshot starts; active render-to-next-main_render intervals only. No component inclusive costs or natural occurrence/publication cadence claim.'
    counts=[i['entry_counts'] for i in results[1]['intervals']]
    assert counts and any(x['erase_entity_footprints'] for x in counts),'colour worklist not observed'
    report['passed']=True
except BaseException as exc:
    report['error']=str(exc)
finally:
    report['duration_seconds']=time.monotonic()-start
    (OUT/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report),flush=True)
