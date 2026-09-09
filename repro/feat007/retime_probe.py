"""Verify retimed map + stage work on both surfaces, with unchanged tick count."""
from pathlib import Path
import sys,json,hashlib
BASE=Path(__file__).parent
for flag in ('--retime','--reuse-streams'):
    if flag not in sys.argv:sys.argv.append(flag)
if '--production' in sys.argv:
    from types import SimpleNamespace
    import shutil
    ROOT=BASE.parents[1];sys.path.insert(0,str(ROOT/'scripts'))
    import benchmark_6309 as b,build_presentation as p
    from production_runtime_fixture import prepare
    OUT=prepare(ROOT);rom=OUT/'publication.rom';raw=(OUT/'main.bin').read_bytes()
    raw=rom.read_bytes()[:len(raw)]
    main=b.symbols(OUT/'main.map');bootmap=b.symbols(OUT/'probe-startup.map')
    link=SimpleNamespace(DYNAMIC=True,modulemap=b.symbols(OUT/'presentation.map'))
    payload=(OUT/'cold.bin').read_bytes();manifest=json.loads((ROOT/'build/ladybug-presentation.json').read_text())
    ns=dict(p=p,offsets=dict(zip(p.MAP_NAMES,manifest['map_stream_offsets'])),frames={name:(OUT/(name+'.pixels')).read_bytes() for name in p.MAP_NAMES})
    shutil.copyfile(BASE/'dynamic/baseline-highscore-helper.bin',OUT/'baseline-highscore-helper.bin')
    schedule={}
else:exec((BASE/'linked_publication.py').read_text().split('process,client=')[0])
process,client=b.launch(b.load_monitor(),b.DEFAULT_XROAR,rom,'6809')
def write(a,v):client.call('write_memory',{'addr':a,'data':bytes(v).hex()})
def reach(pc):
    bp=b.set_breakpoint(client,pc)
    try:assert b.run_to_breakpoint(client,10)['pc']==pc
    finally:b.clear_breakpoint(client,bp)
def call(pc):
    if pc==link.modulemap['presentation_flow_tick']:
        write(main['LAST_FRAME'],[0]);write(main['FRAMES'],[0,1])
        client.call('write_registers',{'pc':main['mainloop']+1,'s':0x1FFE,'dp':0,'cc':0x50})
        before=b.read_timing(client);reach(main['mainloop']);after=b.read_timing(client)
        assert client.call('read_registers')['s']==0x1FFE
        return after['cpu_cycles']-before['cpu_cycles']
    write(0x1FFC,[0x18,0]);client.call('write_registers',{'pc':pc,'s':0x1FFC,'dp':0,'cc':0x50})
    before=b.read_timing(client);reach(0x1800);after=b.read_timing(client)
    assert client.call('read_registers')['s']==0x1FFE
    return after['cpu_cycles']-before['cpu_cycles']
def install_helper(filename):
    write(0xFFA5,[0x23]);code=(OUT/filename).read_bytes();write(0xAC40,code);assert b.read_bytes(client,0xAC40,len(code))==code
results=[]
try:
    print('phase=retimed-preparation marker=ready/return-$1800 deadline=10s per call; timeout=marker-not-reached',flush=True)
    reach(bootmap['ready']);assert b.read_bytes(client,0xC000,len(raw))==raw
    write(0x1800,[0x20,0xFE]);module=(OUT/'presentation.bin').read_bytes();write(0x1900,module);assert b.read_bytes(client,0x1900,len(module))==module
    if link.DYNAMIC:
        enemy=b.symbols(OUT/'enemy.map');code=(OUT/'enemy.bin').read_bytes();write(0x800,code);assert b.read_bytes(client,0x800,len(code))==code
    for off in range(0,len(payload),8192):
        write(0xFFA5,[0x3A+off//8192]);part=payload[off:off+8192];write(0xA000,part);assert b.read_bytes(client,0xA000,len(part))==part
    # Source-map worklists all run; stage-dependent slices additionally cover
    # both surfaces, digit widths, first-stage context, clamp and maximum.
    scenarios=[(n,0,1,1) for n in ns['p'].MAP_NAMES if n!='level-start']
    if link.DYNAMIC:scenarios=[s for s in scenarios if s[0]!='high-score'] # Full ranking is covered by sequence_probe.
    scenarios += [('level-start',owner,stage,context) for owner in (0,1) for stage,context in [(1,1),(18,2),(255,2),(0,2)]]
    scenarios += [('level-start',0,stage,context) for stage,context in [(10,2),(99,2),(100,2),(255,1)]]
    for name,owner,stage,context in scenarios:
        first=0x2C+owner*4;write(0xFFA1,range(first,first+4));write(0,[0]*256)
        if link.DYNAMIC:
            from runtime_fixture import initialize_framebuffers
            initialize_framebuffers(write,call,lambda a,n:b.read_bytes(client,a,n),enemy)
            write(0x8F,[1-owner,owner]);first=0x30-owner*4;write(0xFFA1,range(first,first+4))
        write(0xA4,[0xA5,1,ns['p'].MAP_NAMES.index(name),context]);write(0x24,[stage]);write(0xAE,[0x20,0]);write(0x90,[owner]);off=ns['offsets'][name];write(0xB5,[off>>8,off&255])
        if name=='level-start':
            write(0x2000,ns['frames'][name]);install_helper('baseline-highscore-helper.bin')
            call(0xB080);expected=b.read_bytes(client,0x2000,30720)
        else:expected=ns['frames'][name]
        write(0x2000,[0xA5]*30720);install_helper('highscore-helper.bin');ticks=[]
        for tick in range(30):
            ticks.append(call(link.modulemap['presentation_flow_tick']))
            assert b.read_bytes(client,0x91,1)==bytes([0]),('early publication',name,tick)
            assert b.read_bytes(client,0xAA,2)==((tick+1)*32).to_bytes(2,'big')
        final=None
        if name=='level-start':
            final=call(link.modulemap['presentation_flow_tick'])
            assert b.read_bytes(client,0x91,1)==bytes([1])
        actual=b.read_bytes(client,0x2000,30720)
        assert actual==expected,(name,owner,stage,[(i,a,v) for i,(a,v) in enumerate(zip(actual,expected)) if a!=v][:10])
        results.append(dict(screen=name,owner=owner,stage=stage,context=context,map_ticks=30,cycles=ticks,max_map_cycles=max(ticks),completion_cycles=final,pixel_exact=True,early_publication=False))
finally:client.close();b.stop(process)
maximum=max(max(r['cycles']+[r['completion_cycles'] or 0]) for r in results)
report=dict(status='retimed selected publication worklists pass' if maximum<=27000 else 'retiming target missed',engineering_limit=27000,max_cycles=maximum,entry='mainloop after SYNC through presentation_flow_tick including scan_keys and branch back to mainloop',results=results,production_ready=False,unverified=['other screen completion paths','natural hold sequence','IRQ cost (reserved by engineering margin)','final GMC integration'])
report['artifact_sha256']={name:hashlib.sha256((OUT/name).read_bytes()).hexdigest() for name in ('publication.rom','presentation.bin','highscore-helper.bin','cold.bin')}
(OUT/'retiming.json').write_text(json.dumps(report,indent=2)+'\n')
report['rejected_experiments']=[dict(candidate='sliced stage text and unrolled mask only',max_cycles=28391,entry='load_tick only',result='above 27000; added unrolled native presentation copy'),dict(candidate='original linked_publication assertion on sliced level map before completion',result='obsolete pure-map expectation; replaced with final baseline image comparison after scheduled text and completion sprites')]
report['schedule']={str(tick):dict(destination=hex(entry[0]),kind=entry[1],source_offset=entry[2],max_glyphs=entry[3],colour=entry[4]) for tick,entry in schedule.items()}
(OUT/'retiming.json').write_text(json.dumps(report,indent=2)+'\n')
print('maximum',maximum);print([(r['screen'],r['owner'],r['stage'],r['max_map_cycles'],r['completion_cycles']) for r in results])
if maximum>27000:sys.exit(2)
