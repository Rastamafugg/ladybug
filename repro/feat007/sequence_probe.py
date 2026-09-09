"""Actual ranking preparation and IRQ publication, using existing monitor helpers."""
from pathlib import Path
import sys,json,hashlib
import argparse
parser=argparse.ArgumentParser();parser.add_argument('--owner',type=int,choices=(0,1),default=1);parser.add_argument('--records',choices=('default','maximum','mixed'),default='default');parser.add_argument('--dynamic',action='store_true');parser.add_argument('--production',action='store_true');args=parser.parse_args()
BASE=Path(__file__).parent
if '--dynamic' not in sys.argv:sys.argv.append('--dynamic')
if args.production:
    ROOT=BASE.parents[1];sys.path.insert(0,str(ROOT/'scripts'))
    import benchmark_6309 as b
    from production_runtime_fixture import prepare
    OUT=prepare(ROOT)
    main=b.symbols(OUT/'main.map');pres=b.symbols(OUT/'presentation.map');hs=b.symbols(OUT/'highscore.map')
else:exec((BASE/'verify_remaining.py').read_text().split('process,client=')[0])
enemy=b.symbols(OUT/'enemy.map')
helpers=(BASE/'verify_remaining.py').read_text().split('def write(a,v):')[1].split('results=[]')[0]
exec('def write(a,v):'+helpers)
process,client=b.launch(b.load_monitor(),b.DEFAULT_XROAR,OUT/'publication.rom','6809')
results=[]
try:
    print('phase=ranking-preparation marker=mainloop/return-$1800 deadline=10s per tick; timeout=marker-not-reached',flush=True)
    reach(b.symbols(OUT/'probe-startup.map')['ready'])
    raw=(OUT/'publication.rom').read_bytes()[:main['asset_end']-0xC000]
    assert b.read_bytes(client,0xC000,len(raw))==raw
    write(0x1800,[0x20,0xFE]);install(0x800,OUT/'enemy.bin');install(0x1900,OUT/'presentation.bin');install(0x300,OUT/'highscore.bin')
    install(0x6B2,OUT/'hold.bin')
    payload=(OUT/'cold.bin').read_bytes()
    for off in range(0,len(payload),8192):
        write(0xFFA5,[0x3A+off//8192]);part=payload[off:off+8192];write(0xA000,part);assert b.read_bytes(client,0xA000,len(part))==part
    write(0xFFA5,[0x23]);install(0xAC40,OUT/'highscore-helper.bin')
    install(pres['PRESENTATION_HIGHSCORE_RUNTIME_ADDRESS'],OUT/'highscore.bin')
    write(0x300,[0xA5]*(OUT/'highscore.bin').stat().st_size)
    installation_cycles=call(pres['install_highscore_runtime'])
    assert b.read_bytes(client,0x300,(OUT/'highscore.bin').stat().st_size)==(OUT/'highscore.bin').read_bytes()
    assert installation_cycles<27000
    write(0xFFA5,[0x34]);write(0xA000,[0]*8192);write(0,[0]*256)
    from runtime_fixture import initialize_framebuffers
    initialize_framebuffers(write,call,lambda a,n:b.read_bytes(client,a,n),enemy)
    supplied=None
    if args.records!='default':
        supplied=b''.join(bytes([0x99,0x99,0x99]+[44]*7) if args.records=='maximum' else bytes([0x12,0x34,0x56]+[0,44,50,45,0,48,149]) for _ in range(9))
        if args.production:
            glyph=lambda n:hs[f'PRESENTATION_GLYPH_{n}']
            name=[glyph(35)]*7 if args.records=='maximum' else [0,glyph(10),glyph(35),glyph(0),0,glyph(12),glyph(9)]
            supplied=bytes(([0x99]*3 if args.records=='maximum' else [0x12,0x34,0x56])+name)*9
        write(hs['PRES_HIGHSCORE_BASE'],supplied);write(hs['PRES_HS_READY'],[1])
    write(0x8F,[1-args.owner,args.owner]);write(0xA4,[0xA5]);call(pres['start_screen'],{'a':3})
    for tick in range(31):
        call(enemy['framebuffer_irq_impl'])
        client.call('write_registers',dict(pc=main['mainloop']+1,s=0x1FFE,dp=0,cc=0x50))
        before=b.read_timing(client);reach(main['mainloop']);after=b.read_timing(client)
        state=b.read_bytes(client,0x8F,3)
        results.append(dict(tick=tick+1,phase='map' if tick<30 else 'completion',cycles=after['cpu_cycles']-before['cpu_cycles'],front=state[0],back=state[1],pending=state[2]))
        assert state[2]==int(tick==30),('publication ordering',tick,state.hex())
        assert client.call('read_registers')['s']==0x1FFE
    # Compare all final pixels against the static source plus actual default
    # records interpreted independently through the explicit descriptor data.
    write(0xFFA5,[0x34]);records=b.read_bytes(client,hs['PRES_HIGHSCORE_BASE'],90)
    if supplied is not None:assert records==supplied,'pre-existing ranking records changed'
    expected=bytearray((OUT/'high-score.pixels').read_bytes())
    descriptors=(OUT/'descriptors.bin').read_bytes();font=(BASE/'fit/asset-text-data.bin').read_bytes()[:328]
    graphics=(OUT/'graphics.bin').read_bytes();score_ids=b.read_bytes(client,hs['score_glyphs'],10)
    def tile(destination,ident):
        index=256+ident-49 if not args.production and ident in (49,50) else ident
        glyph,colour=descriptors[index*2:index*2+2];assert (glyph,colour)!=(255,255),ident
        for row in range(8):
            pixels=graphics[glyph*32+row*4:glyph*32+row*4+4] if colour==0 else bytes((colour if font[glyph*8+row]&(128>>(j*2)) else 0)*16+(colour if font[glyph*8+row]&(64>>(j*2)) else 0) for j in range(4))
            start=destination-0x2000+row*160;expected[start:start+4]=pixels
    for entry in range(9):
        rec=records[entry*10:entry*10+10];dest=0x2A40 if entry==0 else 0x3440+(entry-1)*1280
        for n,ident in enumerate(rec[3:]):tile(dest+n*4,ident or hs['PRES_HS_BLACK'])
        for n,value in enumerate(rec[:3]):
            tile(dest+44+n*8,score_ids[value>>4]);tile(dest+48+n*8,score_ids[value&15])
    actual=b.read_bytes(client,0x2000,30720)
    differences=[i for i,(a,v) in enumerate(zip(actual,expected)) if a!=v]
    call(enemy['framebuffer_irq_impl']);state=b.read_bytes(client,0x8F,3)
    assert state==bytes([args.owner,1-args.owner,0]),state.hex()
    report=dict(status='pass' if not differences and max(r['cycles'] for r in results)<=27000 else 'FAIL',scenario='actual ranking start_screen, 30 map ticks, completion, IRQ publication',engineering_limit=27000,max_cycles=max(r['cycles'] for r in results),pixel_exact=not differences,mismatched_bytes=len(differences),first_differences=differences[:12],published_front=1,results=results,production_ready=False,scope='Frame-stepped runtime preparation with forced ranking entry; not a GMC boot or complete attract/game-over sequence.',rom_sha256=hashlib.sha256((OUT/'publication.rom').read_bytes()).hexdigest())
    report.update(published_front=args.owner,record_fixture=args.records,installation_cycles=installation_cycles,artifact_sha256={name:hashlib.sha256((OUT/name).read_bytes()).hexdigest() for name in ('publication.rom','presentation.bin','highscore.bin','highscore-helper.bin','cold.bin')})
    (OUT/f'sequence-{args.owner}-{args.records}.json').write_text(json.dumps(report,indent=2)+'\n')
    if args.owner==1 and args.records=='default':(OUT/'sequence-verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='results'},indent=2))
finally:client.close();b.stop(process)
sys.exit(0 if report['status']=='pass' else 2)
