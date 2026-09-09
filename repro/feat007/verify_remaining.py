"""Discriminate unresolved dynamic-ID and phase-patch compatibility before sequences."""
from pathlib import Path
import sys,re,json,hashlib,subprocess
ROOT=Path(__file__).resolve().parents[2];BASE=Path(__file__).parent;DYNAMIC='--dynamic' in sys.argv;OUT=BASE/('dynamic' if DYNAMIC else 'retimed')
sys.path.insert(0,str(ROOT/'scripts'))
import benchmark_6309 as b
if DYNAMIC:
    for name,source,defs in [('highscore','demo_runtime.s',dict(HIGHSCORE_TEST_PROFILE=1,HIGHSCORE_PHASE_HELPER=0,COMPLETE_PHASE_AUX=1,HIGHSCORE_PHASE_HELPER_ADDRESS=0xAC40,HIGHSCORE_PHASE_HELPER_RESUME=0xAD00,PRESENTATION_NAME_ENTRY_DATA=0)),('instruction','instruction_runtime.s',dict(HIGHSCORE_TEST_PROFILE=0,PRESENTATION_NAME_ENTRY_DATA=0)),('enemy','enemy_runtime.s',{})]:
        sourcepath=ROOT/'src'/source
        if name=='highscore':
            from retime_helpers import ranking_runtime
            sourcepath=OUT/'highscore.s';sourcepath.write_text(ranking_runtime((ROOT/'src'/source).read_text()))
        if name=='instruction':
            from instruction_retime import transform
            sourcepath=OUT/'instruction.s';sourcepath.write_text(transform((ROOT/'src'/source).read_text()))
        subprocess.run(['lwasm','-9','--format=raw',f'--output={OUT/(name+".bin")}',f'--map={OUT/(name+".map")}','--symbols','-I',str(OUT),*[f'-D{k}={v}' for k,v in defs.items()],str(sourcepath)],check=True)
        if name=='instruction':assert (OUT/'instruction.bin').stat().st_size<=938
main=b.symbols(OUT/'main.map');pres=b.symbols(OUT/'presentation.map');hs=b.symbols(OUT/'highscore.map')
if DYNAMIC:
    subprocess.run(['lwasm','-9','--format=raw',f'--output={OUT/"hold.bin"}',f'--map={OUT/"hold.map"}','--symbols','-I',str(OUT),str(ROOT/'src/perimeter_reset_helper.s')],check=True)
process,client=b.launch(b.load_monitor(),b.DEFAULT_XROAR,OUT/'publication.rom','6809')
def write(a,v):client.call('write_memory',{'addr':a,'data':bytes(v).hex()})
def reach(pc):
    bp=b.set_breakpoint(client,pc)
    try:assert b.run_to_breakpoint(client,10)['pc']==pc
    finally:b.clear_breakpoint(client,bp)
def call(pc,regs={}):
    write(0x1FFC,[0x18,0]);client.call('write_registers',dict(pc=pc,s=0x1FFC,dp=0,cc=0x50,**regs))
    before=b.read_timing(client);reach(0x1800);after=b.read_timing(client)
    assert client.call('read_registers')['s']==0x1FFE
    return after['cpu_cycles']-before['cpu_cycles']
def install(a,path):
    data=path.read_bytes();write(a,data);assert b.read_bytes(client,a,len(data))==data
results=[]
try:
    print('phase=remaining-contracts marker=ready/return-$1800 deadline=10s per call; timeout=marker-not-reached',flush=True)
    reach(b.symbols(OUT/'probe-startup.map')['ready'])
    raw=(OUT/'publication.rom').read_bytes()[:main['asset_end']-0xC000];assert b.read_bytes(client,0xC000,len(raw))==raw
    write(0x1800,[0x20,0xFE]);install(0x1900,OUT/'presentation.bin');install(0x300,OUT/'highscore.bin')
    payload=(OUT/'cold.bin').read_bytes()
    for off in range(0,len(payload),8192):
        write(0xFFA5,[0x3A+off//8192]);part=payload[off:off+8192];write(0xA000,part);assert b.read_bytes(client,0xA000,len(part))==part
    write(0xFFA1,range(0x2C,0x30));write(0xFFA5,[0x34]);write(0xA000,[0]*4096)
    font=(BASE/'fit/asset-text-data.bin').read_bytes()[:328]
    score_ids=b.read_bytes(client,hs['score_glyphs'],10)
    for digits in ((0,)*6,(1,2,3,4,5,6),(9,)*6):
        write(0x2000,[0xA5]*1280);write(0x200,[digits[i]*16+digits[i+1] for i in (0,2,4)]);write(0x29,[6])
        cycles=call(hs['draw_score'],{'x':0x200,'y':0x2000})
        expected=bytearray([0xA5]*1280)
        for n,digit in enumerate(digits):
            for row,bits in enumerate(font[digit*8:digit*8+8]):
                for j in range(4):expected[row*160+n*4+j]=(6 if bits&(128>>(j*2)) else 0)*16+(6 if bits&(64>>(j*2)) else 0)
        actual=b.read_bytes(client,0x2000,1280)
        mismatch=[i for i,(a,v) in enumerate(zip(actual,expected)) if a!=v]
        results.append(dict(scenario='dynamic high-score digits',digits=digits,cycles=cycles,pixel_exact=not mismatch,mismatched_bytes=len(mismatch),old_score_ids=list(score_ids),first_differences=[dict(offset=i,actual=actual[i],expected=expected[i]) for i in mismatch[:8]]))
    # Natural screen-entry code installs its old overlay slots before hydration.
    # Run the actual start_screen with current helper and copied instruction code.
    cmd=['lwasm','-9','--format=raw',f'--output={OUT/"hold.bin"}',f'--map={OUT/"hold.map"}','--symbols','-I',str(OUT),str(ROOT/'src/perimeter_reset_helper.s')]
    subprocess.run(cmd,check=True);install(0x6B2,OUT/'hold.bin')
    write(0xFFA5,[0x23]);install(0xA422,OUT/'instruction.bin')
    patches=(ROOT/'build/ladybug-presentation-tile-patches.bin').read_bytes();write(0xBF80,patches);assert b.read_bytes(client,0xBF80,len(patches))==patches
    for screen in (1,3,4,5):
        write(0xFFA5,[0x3A]);write(0xA000,payload[:8192])
        write(0x90,[0]);write(0xD4,[0]);cycles=call(pres['start_screen'],{'a':screen})
        write(0xFFA5,[0x3A]);actual=b.read_bytes(client,0xA000,174*32);expected=payload[:174*32]
        changed=[i for i,(a,v) in enumerate(zip(actual,expected)) if a!=v]
        results.append(dict(scenario='actual start_screen atlas identity',screen=screen,cycles=cycles,atlas_exact=not changed,changed_bytes=len(changed),changed_graphic_ids=sorted({i//32 for i in changed})))
    for screen in (0,1):
        install(0x300,OUT/'highscore.bin')
        write(0xD4,[0]);cycles=call(pres['start_screen'],{'a':screen})
        code=(OUT/'instruction.bin').read_bytes()
        exact=b.read_bytes(client,0x300,len(code))==code
        results.append(dict(scenario='ranking owner replaced on ordinary instruction/title entry',screen=screen,cycles=cycles,atlas_exact=exact,instruction_bytes_exact=exact))
finally:client.close();b.stop(process)
report=dict(status='remaining compatibility verification FAILED',production_ready=False,results=results,
    natural_sequences='Not accepted: required dynamic text contract and screen-entry atlas identity fail before a valid sequence can be established.',
    unverified=['all final completion-helper timing','natural title/instructions/demo/live sequence','qualifying and nonqualifying game-over/name/ranking sequences','natural hold/input pre-emption','final GMC boot'],
    rom_sha256=hashlib.sha256((OUT/'publication.rom').read_bytes()).hexdigest())
passed=all(r.get('pixel_exact',r.get('atlas_exact',False)) for r in results)
if passed:report['status']='dynamic score and screen-entry atlas compatibility pass';report['natural_sequences']='Entry prerequisites pass; full natural sequence execution still required.'
(OUT/'remaining-verification.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
sys.exit(0 if passed else 2)
