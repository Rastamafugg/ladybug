"""Game-over to name-entry completion using actual timer and hold transitions."""
from pathlib import Path
import sys,json,hashlib
BASE=Path(__file__).parent
sys.argv.append('--dynamic')
production='--production' in sys.argv
if production:
    ROOT=BASE.parents[1];sys.path.insert(0,str(ROOT/'scripts'))
    import benchmark_6309 as b
    from production_runtime_fixture import prepare
    OUT=prepare(ROOT)
    main=b.symbols(OUT/'main.map');pres=b.symbols(OUT/'presentation.map');hs=b.symbols(OUT/'highscore.map')
else:exec((BASE/'verify_remaining.py').read_text().split('process,client=')[0])
enemy=b.symbols(OUT/'enemy.map')
exec('def write(a,v):'+(BASE/'verify_remaining.py').read_text().split('def write(a,v):')[1].split('results=[]')[0])
process,client=b.launch(b.load_monitor(),b.DEFAULT_XROAR,OUT/'publication.rom','6809')
results=[];completed=[]
active='--active' in sys.argv
try:
    print('phase=game-over-to-name marker=mainloop/return-$1800 deadline=10s per tick; maximum=400 ticks; timeout=missing marker/sequence',flush=True)
    reach(b.symbols(OUT/'probe-startup.map')['ready'])
    raw=(OUT/'publication.rom').read_bytes()[:main['asset_end']-0xC000];assert b.read_bytes(client,0xC000,len(raw))==raw
    write(0xFFA6,[0x3E,0x3F]);write(0xFFDF,[0]);write(0xC000,raw);assert b.read_bytes(client,0xC000,len(raw))==raw
    write(0x1800,[0x20,0xFE]);install(0x800,OUT/'enemy.bin');install(0x1900,OUT/'presentation.bin');install(0x6B2,OUT/'hold.bin')
    payload=(OUT/'cold.bin').read_bytes()
    write(0xFFA5,[0x39]);install(0xA000,ROOT/'build/ladybug-player-sparse.bin')
    for off in range(0,len(payload),8192):
        write(0xFFA5,[0x3A+off//8192]);part=payload[off:off+8192];write(0xA000,part);assert b.read_bytes(client,0xA000,len(part))==part
    write(0xFFA5,[0x23]);install(0xAC40,OUT/'highscore-helper.bin');install(pres['PRESENTATION_HIGHSCORE_RUNTIME_ADDRESS'],OUT/'highscore.bin')
    call(pres['install_highscore_runtime']);assert b.read_bytes(client,0x300,(OUT/'highscore.bin').stat().st_size)==(OUT/'highscore.bin').read_bytes()
    write(0xFFA5,[0x34]);write(0xA000,[0]*8192);write(0,[0]*256);write(0x8F,[0,1]);write(0xA4,[0xA5]);write(hs['PRES_SCORE_H'],[0x99,0x99,0x99])
    from runtime_fixture import initialize_framebuffers
    initialize_framebuffers(write,call,lambda a,n:b.read_bytes(client,a,n),enemy)
    call(pres['start_screen'],{'a':4})
    font=(BASE/'fit/asset-text-data.bin').read_bytes()[:328];descriptors=(OUT/'descriptors.bin').read_bytes();graphics=(OUT/'graphics.bin').read_bytes();digits=b.read_bytes(client,hs['score_glyphs'],10)
    def tile(frame,dest,ident):
        ix=256+ident-49 if not production and ident in (49,50) else ident
        glyph,colour=descriptors[ix*2:ix*2+2];assert colour!=255,ident
        for row in range(8):
            pixels=graphics[glyph*32+row*4:glyph*32+row*4+4] if colour==0 else bytes((colour if font[glyph*8+row]&(128>>(j*2)) else 0)*16+(colour if font[glyph*8+row]&(64>>(j*2)) else 0) for j in range(4))
            start=dest-0x2000+row*160;frame[start:start+4]=pixels
    for tick in range(400):
        call(enemy['framebuffer_irq_impl']);old=b.read_bytes(client,0,256)
        client.call('write_registers',dict(pc=main['mainloop']+1,s=0x1FFE,dp=0,cc=0x50));before=b.read_timing(client);reach(main['mainloop']);after=b.read_timing(client);state=b.read_bytes(client,0,256)
        phase='completion' if old[0xA5]==1 and not old[0xD4]&128 and old[0xAA:0xAC]==bytes([3,192]) else 'hold' if old[0xD4]&128 else 'map' if old[0xA5]==1 else 'active'
        results.append(dict(tick=tick+1,screen=old[0xA6],phase=phase,cycles=after['cpu_cycles']-before['cpu_cycles'],mode=state[0xA5],pending=state[0x91]))
        assert client.call('read_registers')['s']==0x1FFE
        if phase=='completion':
            saved_mapping=b.read_bytes(client,0xFFA1,5)
            screen=old[0xA6];expected=bytearray((OUT/('game-over.pixels' if screen==4 else 'enter-high-score.pixels')).read_bytes())
            if screen==5:
                write(0xFFA5,[0x34]);record=b.read_bytes(client,hs['PRES_HIGHSCORE_BASE'],10);pending=b.read_bytes(client,hs['PRES_PENDING_NAME'],7);score=state[0xBF:0xC2];topname=pending if state[0xC9]==0 else record[3:];topscore=score if state[0xC9]==0 else record[:3]
                for values,key in [(pending,'NAME_DST'),(topname,'TOP_NAME_DST')]:
                    for n,ident in enumerate(values):tile(expected,hs['PRESENTATION_NAME_ENTRY_'+key]+n*4,ident or hs['PRES_HS_BLACK'])
                for values,key in [(score,'SCORE_DST'),(topscore,'TOP_RIGHT_DST'),(topscore,'TOP_DST')]:
                    for n,v in enumerate(values):
                        tile(expected,hs['PRESENTATION_NAME_ENTRY_'+key]+n*8,digits[v>>4]);tile(expected,hs['PRESENTATION_NAME_ENTRY_'+key]+n*8+4,digits[v&15])
                player=(ROOT/'build/ladybug-player-sparse.bin').read_bytes()
                frame=state[enemy['PLAYER_FACE']]*4+state[enemy['PLAYER_ANIM']]
                page=player[frame*3];assert page==0x39
                ptr=int.from_bytes(player[frame*3+1:frame*3+3],'big')-0xA000
                dest=hs['PRESENTATION_NAME_ENTRY_CURSOR_DST']-0x2000
                while True:
                    delta=player[ptr];ptr+=1
                    if delta==255:
                        delta=int.from_bytes(player[ptr:ptr+2],'big');ptr+=2
                        if delta==0:break
                        ptr+=1
                    dest+=delta;count=player[ptr];ptr+=1
                    for _ in range(count&127):
                        if count&128:
                            mask,value=player[ptr:ptr+2];ptr+=2;expected[dest]=(expected[dest]&mask)|value
                        else:expected[dest]=player[ptr];ptr+=1
                        dest+=1
            owner=old[0x90];first=0x30-owner*4;write(0xFFA1,range(first,first+4));actual=b.read_bytes(client,0x2000,30720)
            excluded=set()
            diff=[i for i,(a,v) in enumerate(zip(actual,expected)) if a!=v and i not in excluded]
            completed.append(dict(screen=screen,owner=owner,pixels_exact_outside_cursor=not diff,differing_bytes=len(diff),first_differences=diff[:8],excluded_cursor_bytes=len(excluded)))
            write(0xFFA1,saved_mapping)
        if state[0xA5]==8 and state[0x91]:
            call(enemy['framebuffer_irq_impl']);assert b.read_bytes(client,0x91,1)==bytes([0])
            if not active:break
    assert len(completed)==3,('missing completions',completed,results[-1])
    maximum=max(r['cycles'] for r in results)
    report=dict(status='pass' if maximum<=27000 and all(c['pixels_exact_outside_cursor'] for c in completed) else 'FAIL',max_cycles=maximum,engineering_limit=27000,completed=completed,results=results,production_ready=False,scope='Forced qualifying game-over entry followed by actual 180-tick timer and sequential name hold publication; complete pixels include decoded cursor. Full GMC boot not accepted.',artifact_sha256={name:hashlib.sha256((OUT/name).read_bytes()).hexdigest() for name in ('publication.rom','presentation.bin','highscore.bin','highscore-helper.bin','cold.bin')},player_payload_sha256=hashlib.sha256((ROOT/'build/ladybug-player-sparse.bin').read_bytes()).hexdigest())
    report['active_name_ticks']=sum(r['phase']=='active' and r['screen']==5 for r in results)
    (OUT/('name-active-verification.json' if active else 'name-sequence-verification.json')).write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k not in ('results','artifact_sha256')},indent=2));print([(r['tick'],r['phase'],r['cycles']) for r in results if r['phase']=='completion'])
finally:client.close();b.stop(process)
sys.exit(0 if report['status']=='pass' else 2)
