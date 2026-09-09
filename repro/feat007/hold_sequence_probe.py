"""Exercise actual title hold/copy, both hydrations and IRQ publication."""
from pathlib import Path
import sys,json,hashlib
BASE=Path(__file__).parent
sys.argv.append('--dynamic')
if '--production' in sys.argv:
    import subprocess
    ROOT=BASE.parents[1];sys.path.insert(0,str(ROOT/'scripts'))
    import benchmark_6309 as b
    from production_runtime_fixture import prepare
    OUT=prepare(ROOT)
    main=b.symbols(OUT/'main.map');pres=b.symbols(OUT/'presentation.map')
else:
    exec((BASE/'verify_remaining.py').read_text().split('process,client=')[0])
reference='--reference-replay' in sys.argv
if reference:
    source=BASE/'pre-integration-source/instruction_runtime.s' if '--production' in sys.argv else ROOT/'src/instruction_runtime.s'
    includes=ROOT/'build' if '--production' in sys.argv else OUT
    subprocess.run(['lwasm','-9','--format=raw',f'--output={OUT/"instruction-reference.bin"}','-I',str(includes),'-DHIGHSCORE_TEST_PROFILE=0','-DPRESENTATION_NAME_ENTRY_DATA=0',str(source)],check=True)
from gmc_lzss import decompress
enemy=b.symbols(OUT/'enemy.map')
exec('def write(a,v):'+(BASE/'verify_remaining.py').read_text().split('def write(a,v):')[1].split('results=[]')[0])
process,client=b.launch(b.load_monitor(),b.DEFAULT_XROAR,OUT/'publication.rom','6809')
results=[];completed=[]
extended='--extended' in sys.argv
choreography='--choreography' in sys.argv
if choreography:extended=True
try:
    limit=4000 if choreography else 800 if extended else 100
    print(f'phase=title-hold marker=mainloop/return-$1800 deadline=10s per tick, maximum={limit} ticks; timeout=marker or publication sequence incomplete',flush=True)
    reach(b.symbols(OUT/'probe-startup.map')['ready'])
    raw=(OUT/'publication.rom').read_bytes()[:main['asset_end']-0xC000];assert b.read_bytes(client,0xC000,len(raw))==raw
    # Match the existing GMC runtime mapping. ROM mode overrides reads of
    # physical $3C-$3F, including title surfaces borrowed through PAR5.
    write(0xFFA6,[0x3E,0x3F]);write(0xFFDF,[0]);write(0xC000,raw)
    assert b.read_bytes(client,0xC000,len(raw))==raw,'RAM resident/asset identity'
    write(0x1800,[0x20,0xFE]);install(0x800,OUT/'enemy.bin');install(0x1900,OUT/'presentation.bin');install(0x6B2,OUT/'hold.bin')
    payload=(OUT/'cold.bin').read_bytes()
    write(0xFFA5,[0x39]);install(0xA000,ROOT/'build/ladybug-player-sparse.bin')
    for off in range(0,len(payload),8192):
        write(0xFFA5,[0x3A+off//8192]);part=payload[off:off+8192];write(0xA000,part);assert b.read_bytes(client,0xA000,len(part))==part
    write(0xFFA5,[0x23]);install(0xAC40,OUT/'highscore-helper.bin');install(0xA422,OUT/('instruction-reference.bin' if reference else 'instruction.bin'))
    surfaces=decompress((ROOT/'build/ladybug-attract-actor-underlays.bin').read_bytes(),7296)
    actors=(ROOT/'build/ladybug-attract-actor-records.bin').read_bytes()
    write(0xFFA5,[0x3C]);write(0xA000,surfaces);write(0xBC80,actors)
    actual_surfaces=b.read_bytes(client,0xA000,7296);actual_actors=b.read_bytes(client,0xBC80,len(actors))
    assert actual_surfaces==surfaces and actual_actors==actors,dict(surface_differences=[i for i,(a,v) in enumerate(zip(actual_surfaces,surfaces)) if a!=v][:8],actor_actual=actual_actors.hex(),actor_expected=actors.hex())
    write(0xFFA5,[0x34]);write(0xA000,[0]*8192);write(0,[0]*256);write(0x8F,[0,1])
    for owner in (0,1):
        first=0x30-owner*4;write(0xFFA1,range(first,first+4));write(0x2000,[0xA5]*30720)
    from runtime_fixture import initialize_framebuffers
    initialize_framebuffers(write,call,lambda a,n:b.read_bytes(client,a,n),enemy)
    expected=bytearray((OUT/'attract.pixels').read_bytes())
    for actor in range(19):
        dest=int.from_bytes(actors[actor*2:actor*2+2],'big')
        for row in range(16):
            start=dest-0x2000+row*160;expected[start:start+8]=surfaces[actor*128+row*8:actor*128+row*8+8]
    instruction_expected=bytearray((OUT/'instructions.pixels').read_bytes())
    ptr=pres['PRESENTATION_INSTRUCTION_CUCUMBER_STREAM'];dest=pres['PRESENTATION_INSTRUCTION_CUCUMBER_DST']-0x2000
    while True:
        delta=payload[ptr];ptr+=1
        if delta==255:
            delta=int.from_bytes(payload[ptr:ptr+2],'big');ptr+=2
            if delta==0:break
            ptr+=1
        dest+=delta;count=payload[ptr];ptr+=1
        for _ in range(count&127):
            if count&128:
                mask,value=payload[ptr:ptr+2];ptr+=2;instruction_expected[dest]=(instruction_expected[dest]&mask)|value
            else:instruction_expected[dest]=payload[ptr];ptr+=1
            dest+=1
    for tick in range(limit):
        call(enemy['framebuffer_irq_impl'])
        beforestate=b.read_bytes(client,0,256)
        client.call('write_registers',dict(pc=main['mainloop']+1,s=0x1FFE,dp=0,cc=0x50))
        before=b.read_timing(client)
        try:reach(main['mainloop'])
        except Exception as error:
            client.call('pause');regs=client.call('read_registers')
            failure=dict(status='FAIL: foreground return marker missing',tick=tick+1,error=str(error),previous_ticks=results[-3:],before_dp=beforestate.hex(),registers=regs,live_pc_bytes=b.read_bytes(client,regs['pc'],16).hex(),deadline_seconds=10,meaning='Marker not reached; not evidence of a slow routine.')
            (OUT/'instruction-sequence-failure.json').write_text(json.dumps(failure,indent=2)+'\n');print(json.dumps(failure,indent=2),flush=True);raise
        after=b.read_timing(client)
        state=b.read_bytes(client,0,256)
        if '--diagnose' in sys.argv and tick==747:
            changes={}
            for label,address,filename in [('instruction',0x300,'instruction.bin'),('enemy',0x800,'enemy.bin'),('presentation',0x1900,'presentation.bin')]:
                authored=(OUT/filename).read_bytes();live=b.read_bytes(client,address,len(authored));changes[label]=[dict(address=address+i,expected=v,actual=a) for i,(a,v) in enumerate(zip(live,authored)) if a!=v][:16]
            diagnostic=dict(tick=748,cycles=after['cpu_cycles']-before['cpu_cycles'],registers=client.call('read_registers'),dp=state.hex(),code_changes=changes)
            (OUT/'instruction-first-update-diagnostic.json').write_text(json.dumps(diagnostic,indent=2)+'\n');print(json.dumps(diagnostic,indent=2),flush=True)
            break
        phase='entry' if beforestate[0xA4]!=0xA5 else 'hold-copy/publish' if beforestate[0xD4]&128 else 'active' if beforestate[0xA5]!=1 else 'completion' if beforestate[0xAA:0xAC]==bytes([3,192]) else 'map'
        results.append(dict(tick=tick+1,phase=phase,cycles=after['cpu_cycles']-before['cpu_cycles'],screen=state[0xA6],mode=state[0xA5],hold=state[0xD4],hold_owner=state[0xD9],front=state[0x8F],back=state[0x90],pending=state[0x91]))
        if choreography and beforestate[0xA6]==1 and beforestate[0xA5]==3:
            results[-1]['frame_sha256']=hashlib.sha256(b.read_bytes(client,0x2000,30720)).hexdigest()
        assert client.call('read_registers')['s']==0x1FFE
        if phase=='completion':
            saved_mapping=b.read_bytes(client,0xFFA1,5)
            owner=beforestate[0x90]
            first=0x30-owner*4;write(0xFFA1,range(first,first+4));actual=b.read_bytes(client,0x2000,30720)
            target=expected if beforestate[0xA6]==0 else instruction_expected
            differences=[i for i,(a,v) in enumerate(zip(actual,target)) if a!=v]
            write(0xFFA5,[0x3A]);liveatlas=b.read_bytes(client,0xA000,5920)
            completed.append(dict(screen=beforestate[0xA6],owner=owner,pixel_exact=not differences,differing_bytes=len(differences),first_differences=[dict(offset=i,actual=actual[i],expected=target[i]) for i in differences[:16]],atlas_differences=[i for i,(a,v) in enumerate(zip(liveatlas,payload)) if a!=v][:24]))
            write(0xFFA1,saved_mapping)
        if choreography and state[0xA6]==2:
            break
        if not choreography and state[0xA5]==pres['MODE_INSTRUCTIONS' if extended else 'MODE_ATTRACT'] and state[0x91]:
            call(enemy['framebuffer_irq_impl']);final=b.read_bytes(client,0,256)
            assert final[0x91]==0
            break
    if '--diagnose' in sys.argv:sys.exit(0)
    assert len(completed)==(4 if extended else 2),('missing two-owner completion',results[-1])
    assert {c['owner'] for c in completed}=={0,1}
    maximum=max(r['cycles'] for r in results)
    report=dict(status='pass' if maximum<=27000 and all(c['pixel_exact'] for c in completed) else 'FAIL',scenario='runtime initialization to title hold copy, sequential A/B hydration and IRQ publication',max_cycles=maximum,engineering_limit=27000,completed=completed,results=results,production_ready=False,scope='Natural hold sequencing from initialized checkpoint memory, not delivered GMC cold boot.',artifact_sha256={name:hashlib.sha256((OUT/name).read_bytes()).hexdigest() for name in ('publication.rom','presentation.bin','highscore-helper.bin','instruction.bin','enemy.bin','hold.bin','cold.bin')})
    report['extended_title_to_instructions']=extended
    if choreography:
        assert state[0xA6]==2,'instruction-to-level transition missing'
        report['instruction_to_level_reached']=True
        report['active_instruction_ticks']=sum(r['screen']==1 and r['phase']=='active' for r in results)
        report['active_instruction_pixels']='Not yet accepted: completion frames checked; active choreography needs independent replay comparison.'
    if reference:report['reference_replay']=True
    (OUT/('instruction-reference-replay.json' if reference else 'instruction-choreography-verification.json' if choreography else 'title-instructions-verification.json' if extended else 'hold-sequence-verification.json')).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('results','artifact_sha256')},indent=2))
    print('completion worklists',[(r['tick'],r['cycles']) for r in results if r['phase']=='completion'])
finally:client.close();b.stop(process)
sys.exit(0 if report['status']=='pass' else 2)
