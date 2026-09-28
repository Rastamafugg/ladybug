"""Cold adaptive driver/real worklist and elapsed audio probe; shared harness."""
from pathlib import Path
import json,sys,time,hashlib
w,out=map(Path,sys.argv[1:3]);sys.path.insert(0,str(w/'scripts'))
import verify_bug011_runtime as r
import verify_bug009_monitor_input as m
b=w/'build';ms=r.symbols(b/'ladybug.map');es=r.symbols(b/'ladybug-enemy-runtime.map');ps=r.symbols(b/'ladybug-presentation-runtime.map');ads=r.symbols(b/'ladybug-audio-runtime.map');act=r.symbols(b/'ladybug-adaptive-active.map')
rom=b/'ladybug.rom';RET=0x18FC
resident=(b/'ladybug-runtime.rom').read_bytes();parser_start=0xC000+resident.index(bytes([0xBD,0x19,0]),ms['mainloop']-0xC000,ms['ad_dispatch_active']-0xC000);started=False
e={'phase':'cold installed adaptive game and real foreground worklist','deadline_seconds':45,'success_marker':'natural publication returns and exact helper/phase code; then elapsed audio returns to $18FC','timeout_meaning':'requested boundary absent, not proof of slowdown','rom_sha256':r.digest(rom.read_bytes()),'cases':[],'status':'incomplete'}
p,c=r.launch_fast(m,Path('/mnt/e/projects/ladybug/docs/reference/xroar/src/xroar'),rom)
deadline=time.monotonic()+45

def read(a,n=1):return r.read_bytes(c,a,n)
def phys(page,a,n):return bytes.fromhex(c.call('read_memory',{'space':'physical','addr':page*8192+a-0xA000,'length':n})['data'])
def write(a,v):c.call('write_memory',{'addr':a,'data':bytes(v).hex()})
def word(a,v):write(a,(v&65535).to_bytes(2,'big'))
def apwrite(a,v):c.call('write_memory',{'space':'physical','addr':0x3D*8192+a-0xA000,'data':bytes(v).hex()})
def go(a):
    assert time.monotonic()<deadline,'45-second phase deadline'
    ids=m.setup(c,[a])
    try:
        c.call('run');h=c.call('wait_for_stop',{'timeout_ms':10000},timeout=12);assert h.get('pc')==a,h
    finally:m.clear(c,ids)
def call(a,value=0):
    write(0x1EFC,[RET>>8,RET&255]);write(RET,[0x20,0xFE]);c.call('write_registers',{'pc':a,'s':0x1EFC,'dp':0,'cc':0x50,'a':value})
    start=c.call('read_cycles')['event_ticks'];go(RET);delta=c.call('read_cycles')['event_ticks']-start;assert delta%8==0
    return delta//8,c.call('read_registers')
def measure():
    global started
    full=started and c.call('read_registers')['pc']!=ms['ad_dispatch_work']
    go(parser_start if full else ms['ad_dispatch_work']);started=True
    before={'raw':int.from_bytes(read(2,2),'big'),'logical':int.from_bytes(read(0xBD26,2),'big'),'debt':int.from_bytes(read(0xBD28,2),'big'),'mode':read(0xA5)[0],'owner':read(0x90)[0],'enemies':read(ms['ENEMY_ACTIVE'])[0],'rate':read(0xBD34)[0],'cycles_scope':'input-parser-through-return' if full else 'active-driver-through-return'}
    start=c.call('read_cycles')['event_ticks'];go(ms['mainloop']);ticks=c.call('read_cycles')['event_ticks']-start
    before.update(cycles=ticks//8,logical_after=int.from_bytes(read(0xBD26,2),'big'),debt_after=int.from_bytes(read(0xBD28,2),'big'),counts=list(read(0xBD38,2)),fault=read(0xBD3A)[0],pending=read(0x91)[0],late=phys(0x3D,ads['audio_adaptive_late'],1)[0]);assert before['fault']==0,before
    return before
try:
    go(ps['attract_tick_ready'])
    assert read(0xC000,0x3E00)==(b/'ladybug-runtime.rom').read_bytes()[:0x3E00],'resident source/live identity'
    enemy=(b/'ladybug-enemy-runtime.rom').read_bytes();assert read(0x800,len(enemy))==enemy,'enemy source/live'
    helper=(b/'ladybug-adaptive-banked.bin').read_bytes();assert phys(0x34,0xBD44,len(helper))==helper,'journal helper source/live'
    audio=(b/'ladybug-audio-runtime.bin').read_bytes();api=audio[ads['audio_adaptive_api']-0xA000:ads['audio_adaptive_last']-0xA000];assert phys(0x3D,ads['audio_adaptive_api'],len(api))==api,'banked adaptive API code source/live'
    stage=(b/'ladybug-adaptive-active.bin').read_bytes();assert phys(0x3D,ads['audio_adaptive_stage'],len(stage))==stage,'active stage source/live'
    e['identity']={'resident':0x3E00,'enemy':len(enemy),'helper':len(helper),'staged_active':len(stage),'banked_audio':len(audio)}
    deadline=time.monotonic()+45
    demo=[]
    for _ in range(8):demo.append(measure())
    assert all(x['mode']==4 for x in demo),demo
    assert read(0x38F,len(stage))==stage,'demo overlay installation'
    assert {x['owner'] for x in demo}=={0,1},'both natural demo owners absent'
    e['cases'].append({'name':'natural cold demo publication','worklists':demo,'pixels_sha256':[r.digest(r.read_owner(c,k)) for k in (0,1)]})
    deadline=time.monotonic()+45
    c.call('inject_key',{'key':5,'action':'press'});go(ps['credit_tick']);c.call('inject_key',{'key':5,'action':'release'})
    c.call('inject_key',{'key':1,'action':'press'});go(ms['ad_dispatch_work']);c.call('inject_key',{'key':1,'action':'release'})
    live=[]
    while read(ms['INITIAL_ENTRY_STATE'])!=b'\0' and len(live)<80:live.append(measure())
    assert len(live)<80,'natural entry marker absent within bounded worklists'
    assert read(0xA5)==b'\0';assert read(0x38F,len(stage))==stage,'credited phase reentry overlay installation'
    deadline=time.monotonic()+45
    for _ in range(8):live.append(measure())
    assert {x['owner'] for x in live}=={0,1};e['cases'].append({'name':'natural credited first entry and steady publication','worklists':live,'pixels_sha256':[r.digest(r.read_owner(c,k)) for k in (0,1)]})
    # One held coin is one edge; a later second press is a second credit.
    deadline=time.monotonic()+45;credit_addr=ps['PRES_CREDITS'];credit_before=read(credit_addr)[0]
    c.call('inject_key',{'key':5,'action':'press'});coin_rows=[measure() for _ in range(3)]
    assert read(credit_addr)[0]==credit_before+1 and read(0xA5)==bytes([0]),'held coin count/active mode regression'
    c.call('inject_key',{'key':5,'action':'release'});measure();c.call('inject_key',{'key':5,'action':'press'});coin_rows.append(measure());c.call('inject_key',{'key':5,'action':'release'});coin_rows.append(measure())
    assert read(credit_addr)[0]==credit_before+2 and read(0xA5)==bytes([0]),'second coin edge lost or interrupted game'
    e['credit_edges']={'initial':credit_before,'final':read(credit_addr)[0],'held_samples':3,'worklists':coin_rows}
    # Bounded controlled release fixture. Save the original foreground PC,
    # stack and stub. The existing release routine alone changes game state.
    def release_one():
        regs=c.call('read_registers');stack=read(0x1E00,512);stub=read(0x1800,2)
        addr=es['enemy_release_impl'];assert read(addr,20)==enemy[addr-0x800:addr-0x800+20]
        write(0x1800,[0x20,0xFE]);write(0x1EFC,[0x18,0])
        c.call('write_registers',{'pc':addr,'s':0x1EFC,'dp':0,'cc':0x50})
        try:go(0x1800)
        finally:
            write(0x1800,stub);write(0x1E00,stack)
            c.call('write_registers',{k:regs[k] for k in ('a','b','cc','dp','x','y','u','s','pc')})
    write(ms['PLAYER_CELL_X'],[22,22]);word(ms['PLAYER_FB'],0x2000+(22*8-8)*160+(22+7)*4);write(ms['PLAYER_DIR'],[255])
    for count in range(1,5):
        deadline=time.monotonic()+45;release_one()
        assert read(ms['ENEMY_ACTIVE'])[0]==count,('controlled release count',count)
        samples=[measure() for _ in range(3)]
        assert all(x['enemies']==count and x['fault']==0 for x in samples)
        e['cases'].append({'name':'controlled enemy release count','count':count,'worklists':samples})
    deadline=time.monotonic()+45
    # Controlled quiet counterpart retains all four actors. Silence admitted
    # voices explicitly rather than waiting long enough for a player death.
    for i in range(4):apwrite(ads['audio_slot0']+i*28,[255])
    apwrite(ads['audio_music_count'],[0]);write(0xEE,[0]);write(0x2ED,[0])
    regs=c.call('read_registers');stack=read(0x1E00,512);stub=read(RET,2);call(0x39B,3);write(0x1E00,stack);write(RET,stub);c.call('write_registers',{k:regs[k] for k in ('a','b','cc','dp','x','y','u','s','pc')})
    quiet=[measure() for _ in range(8)]
    assert all(x['enemies']==4 and x['mode']==0 for x in quiet),'four-enemy quiet fixture lost active population'
    e['cases'].append({'name':'controlled four-enemy quiet worklists','forced_audio_silence':True,'worklists':quiet,'pixels_sha256':[r.digest(r.read_owner(c,k)) for k in (0,1)]})
    # Compare multi-record replay against sequential identical intent packets.
    pages=[0,*range(0x2C,0x35),0x38]
    def snapshot_pages():
        return {page:bytes.fromhex(c.call('read_memory',{'space':'physical','addr':page*8192,'length':8192})['data']) for page in pages}
    def restore_pages(data):
        for page,raw in data.items():c.call('write_memory',{'space':'physical','addr':page*8192,'data':raw.hex()})
        write(0xFFA5,[0x34])
    frozen=snapshot_pages()
    e['journal_boundaries']=[]
    for kind in ('pending','barrier','full-append','coin-seven','coin-eight','four-step-reserve'):
        deadline=time.monotonic()+45;restore_pages(frozen);call(0x9FD)
        write(0x91,[0]);write(0x90,[1-read(0x8F)[0]]);write(0xA5,[0]);write(0xA9,[0]);write(0x7F,bytes(16));word(0xBD24,1000);word(0xBD30,1000);word(0xBD2C,1001);word(2,1001)
        if kind=='pending':
            write(0x91,[1]);before=read(0xBC04,320);cycles,regs=call(0xBD47);assert read(0xBC04,320)==before and regs['cc']&1==0
        elif kind=='barrier':
            write(0xBD37,[1]);write(0xBD32,read(0x92,2));before=read(0xBC04,320);cycles,regs=call(0xBD47);assert read(0xBC04,320)==before and regs['cc']&1==0
        elif kind=='full-append':
            write(0xBD38,[8,4]);before=read(0xBC04,288);cycles,regs=call(0xA03);assert read(0xBC04,288)==before and read(0xBD38,2)==bytes([8,4]) and regs['cc']&1 and read(0xBD3A)==bytes([2])
        else:
            front_id=read(0x8F)[0];owner=read(0x90)[0];commit=read(0x92,2);front=r.read_owner(c,front_id);count=8 if kind=='coin-eight' else 7 if kind=='coin-seven' else 5
            write(0xBD38,[count,count]);write(0xA9,[2 if kind.startswith('coin') else 0]);logical=read(0xBD26,2)
            cycles,regs=call(0x38F)
            assert read(0xBD3A)==bytes([0]) and (read(0x91)==bytes([1]) or read(0x92,2)!=commit),('reserve failed',kind,list(read(0xBD38,3)),list(read(0x8F,10)),read(es['FB_INIT_STATE']).hex())
            assert r.read_owner(c,front_id)==front,'front owner was modified'
            assert read(0xBD26,2)==logical,('simulation advanced before journal drain',kind)
            counts=list(read(0xBD38,2));assert counts[owner]==0 and counts[1-owner]==count
            if kind.startswith('coin'):assert read((0xBC04,0xBC94)[1-owner])[0]&2,'retained credit HUD lost'
        e['journal_boundaries'].append({'name':kind,'cycles':cycles,'counts':list(read(0xBD38,2)),'fault':read(0xBD3A)[0],'pending':read(0x91)[0]})
    restore_pages(frozen)
    e['pixel_cases']=[]
    for owner in (0,1):
        deadline=time.monotonic()+45
        restore_pages(frozen);write(0x91,[0]);write(0x8F,[1-owner]);write(0x90,[owner])
        packets=(bytes([2])+bytes(15),bytes([0,16])+bytes(6)+bytes([8])+bytes(7),bytes([0,2])+bytes(14))
        for packet in packets:
            write(0x7F,packet)
            _,regs=call(0xA03)
            assert regs['cc']&1==0,('append fault',owner,regs)
        counts=list(read(0xBD38,2));assert min(counts)>=3,('multi-record absent',owner,counts)
        write(0x7F,bytes(16))
        _,regs=call(0x39E);assert regs['cc']&1==0 and read(0xBD3A)==b'\0',('render fault',owner,regs)
        actual=r.read_owner(c,owner)
        restore_pages(frozen);write(0x91,[0]);write(0x8F,[1-owner]);write(0x90,[owner]);write(0x7F,bytes(16))
        call(es['framebuffer_prepare_back']);write(es['ENEMY_CAPTURE_DIRTY'],[0]);call(es['colour_prepare_nest']);call(es['actor_closure_restore'])
        for packet in packets:
            write(0x7F,packet);call(es['colour_prepare_nest']);call(es['roam_mark_underlay']);call(es['frame_render_background'])
        write(0x7F,bytes(16));call(es['actor_closure_draw'])
        expected=r.read_owner(c,owner)
        if actual!=expected:
            offsets=[i for i,(x,y) in enumerate(zip(actual,expected)) if x!=y]
            e['pixel_failure']={'owner':owner,'difference_bytes':len(offsets),'rows':sorted(set(i//160 for i in offsets))[:32],'first':[{'offset':i,'row':i//160,'byte_column':i%160,'candidate':actual[i],'redraw':expected[i]} for i in offsets[:20]],'candidate_sha256':r.digest(actual),'sequential_sha256':r.digest(expected)}
            raise AssertionError('multi-record owner pixels differ from sequential replay')
        e['pixel_cases'].append({'owner':owner,'history_counts':counts,'pixels_exact':True,'sha256':r.digest(actual)})
    restore_pages(frozen)
    # Isolated active-page service costs at the observed four-enemy state.
    audio_snapshot=phys(0x3D,0xA000,8192);dp_snapshot=read(0,256)
    e['four_enemy_audio_actions']=[]
    for action in (0,1,2):
        apwrite(0xA000,audio_snapshot);write(0,dp_snapshot)
        cycles,_=call(0x39B,action)
        e['four_enemy_audio_actions'].append({'action':action,'cycles':cycles})
    apwrite(0xA000,audio_snapshot);write(0,dp_snapshot)
    # Retain natural code/state before controlled installed service cases.
    saved_regs=c.call('read_registers');saved_audio=phys(0x3D,0xA000,8192);saved_dp=read(0,256)
    e['audio_cases']=[];deadline=time.monotonic()+45
    for elapsed in (0,1,2,4,255,256):
        apwrite(0xA000,saved_audio);write(0,saved_dp);write(0xA5,[0]);word(2,1000)
        call(0x39B,3)
        # Forced important music note with dwell 9; no newly admitted note
        # can be retroactively expired by the older interval.
        [apwrite(ads['audio_slot0']+i*28,[255]) for i in range(4)];apwrite(ads['audio_music_count'],[0]);write(0xEC,[0,0,0]);write(0xFFA5,[0x3D]);c.call('write_registers',{'b':0});call(ads['audio_enqueue_impl'],6);write(0xFFA5,[0x34]);call(0x39B,1)
        slots=phys(0x3D,ads['audio_slot0'],112);assert slots[0]==6 and slots[3]>0,slots.hex()
        apwrite(ads['audio_slot0']+3,[9]);word(2,1000+elapsed)
        cycles,_=call(0x39B,0);after=phys(0x3D,ads['audio_slot0'],112)
        if elapsed<9:assert after[3]==9-elapsed and after[4:]==slots[4:],(elapsed,after.hex(),slots.hex())
        else:assert after[0]==6 and after[3]>0,'new important note expired before delivery'
        call(0x39B,2);e['audio_cases'].append({'elapsed':elapsed,'cycles':cycles,'wait_after':after[3],'late':phys(0x3D,ads['audio_adaptive_late'],1)[0],'page34_return':read(0xFFA5)[0]&63==0x34})
    # Unsigned raw-clock wrap; inactive voices stay inactive.
    apwrite(0xA000,saved_audio);write(0,saved_dp);word(2,65534);call(0x39B,3);word(2,2);call(0x39B,0);assert phys(0x3D,ads['audio_adaptive_delta'],2)==b'\0\4'
    e['audio_cases'].append({'elapsed':'wrap FFFE->0002','delta':4})
    e['status']='scoped-pass';e['limitations']=['Four-enemy timing fails; full keyed/stage pixel replay, input edges, audio priority/draining, exact PSG trace and natural listening remain open.','Late delivery is recorded; passing bounded note survival does not prove audio cadence fidelity.']
except Exception as exc:e['failure']=repr(exc);raise
finally:
    # Keep complete rare/failing cases and compact the long passing entry.
    for case in e.get('cases',[]):
        rows=case.get('worklists',[])
        if len(rows)>12:
            case['observed_worklists']=len(rows)
            case['observed_cycle_range']=[min(x['cycles'] for x in rows),max(x['cycles'] for x in rows)]
            case['full_rows_sha256']=hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest()
            indexes=sorted(set([0,1,max(range(len(rows)),key=lambda i:rows[i]['cycles']),*range(len(rows)-8,len(rows))]))
            case['retained_indexes']=indexes;case['worklists']=[rows[i] for i in indexes]
    out.write_text(json.dumps(e,indent=2)+'\n');r.stop(p)
