"""Cold adaptive driver/real worklist and elapsed audio probe; shared harness."""
from pathlib import Path
import json,sys,time,hashlib
w,out=map(Path,sys.argv[1:3]);sys.path.insert(0,str(w/'scripts'))
import verify_bug011_runtime as r
import verify_bug009_monitor_input as m
b=w/'build';ms=r.symbols(b/'ladybug.map');es=r.symbols(b/'ladybug-enemy-runtime.map');ps=r.symbols(b/'ladybug-presentation-runtime.map');ads=r.symbols(b/'ladybug-audio-runtime.map');act=r.symbols(b/'ladybug-adaptive-active.map')
rom=b/'ladybug.rom';RET=0x18FC
profile_enabled=False
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

def trace_output():
    # Force every shadow dirty, then decode actual writes from the installed
    # API-2 path using SN76489 latch semantics. This is not a listening test.
    apwrite(ads['audio_mix_shadow'],bytes([0x55])*11)
    write(0x1EFC,[RET>>8,RET&255]);write(RET,[0x20,0xFE]);c.call('write_registers',{'pc':0x39B,'s':0x1EFC,'dp':0,'cc':0x50,'a':2})
    ids=m.setup(c,[ads['audio_write'],RET]);writes=[]
    try:
        while True:
            assert time.monotonic()<deadline,'45-second PSG trace deadline'
            c.call('run');hit=c.call('wait_for_stop',{'timeout_ms':10000},timeout=12)
            if hit.get('pc')==RET:break
            assert hit.get('pc')==ads['audio_write'] and read(ads['audio_write'],8)==audio[ads['audio_write']-0xA000:ads['audio_write']-0xA000+8],'PSG writer code identity'
            writes.append(c.call('read_registers')['a'])
    finally:m.clear(c,ids)
    selected=0;decoded=[0,15,0,15,0,15,0,15]
    for value in writes:
        if value&128:selected=(value>>4)&7;decoded[selected]=(decoded[selected]&0x3F0)|(value&15) if not selected&1 else value&15
        elif selected&1:decoded[selected]=value&15
        else:decoded[selected]=(decoded[selected]&15)|((value&63)<<4)
    periods=phys(0x3D,ads['audio_mix_periods'],6);atten=phys(0x3D,ads['audio_mix_atten'],3);noise=phys(0x3D,ads['audio_mix_noise'],2)
    expected=[];shadow=[]
    for i in range(3):
        tone=int.from_bytes(periods[i*2:i*2+2],'little')&1023;expected.extend((tone,atten[i]&15));shadow.extend((0x80+i*32+(tone&15),tone>>4,0x90+i*32+(atten[i]&15)))
    expected.extend((noise[0]&7,noise[1]&15));shadow.extend((0xE0|(noise[0]&7),0xF0|(noise[1]&15)))
    assert decoded==expected and phys(0x3D,ads['audio_mix_shadow'],11)==bytes(shadow) and read(0xFFA5)[0]&63==0x34,'adaptive PSG/shadow output mismatch'
    return {'writes':writes,'decoded_registers':decoded,'shadow':bytes(shadow).hex(),'page34':True}
def profiled_return(stop_pc=None):
    # Entry/return inclusive spans, with child spans subtracted for exclusive
    # costs. Stack-qualified returns handle nested calls without double count.
    groups=[(act,['adaptive_tick_binding','adaptive_audio_binding','adaptive_render','adaptive_global_binding','adaptive_key_binding']),
            (es,['framebuffer_prepare_back','actor_closure_restore','roam_copy_bg_to_fb','roam_update_background','actor_closure_draw','sparse_blit_fb','frame_render_background','colour_prepare_nest','framebuffer_finish_back','compose_enemy_zone','compose_enemy_animation','bnc_copy','draw_enemy_stage','draw_vegetable_stage','copy_native_row']),
            (ms,['sync_entity_cache_colour','render_entity_colour','draw_perimeter_box','draw_entities','erase_entity_footprints','repair_settled_entity_gates'])]
    if stop_pc is None:stop_pc=ms['mainloop']
    entries={sy[n]:n for sy,names in groups for n in names}
    ids={};frames=[];totals={};hits=0
    def bp(a):
        if a not in ids:ids[a]=m.setup(c,[a])[0]
    for a in [stop_pc,*entries]:bp(a)
    try:
        while True:
            assert time.monotonic()<deadline,'45-second profiled phase deadline'
            c.call('run');h=c.call('wait_for_stop',{'timeout_ms':10000},timeout=12);pc=h.get('pc');assert pc in ids,h
            now=c.call('read_cycles')['event_ticks']//8;regs=c.call('read_registers');hits+=1
            while frames and frames[-1]['return']==pc and regs['s']==(frames[-1]['stack']+2)&65535:
                f=frames.pop();span=now-f['start'];row=totals.setdefault(f['name'],{'calls':0,'inclusive':0,'exclusive':0})
                row['calls']+=1;row['inclusive']+=span;row['exclusive']+=span-f['children']
                if frames:frames[-1]['children']+=span
            if pc==stop_pc:
                assert not frames,('unreturned profile frames',frames)
                return totals,hits
            if pc in entries:
                name=entries[pc]
                if frames and frames[-1]['name']==name and frames[-1]['stack']==regs['s']:continue
                ret=int.from_bytes(read(regs['s'],2),'big');bp(ret)
                # Entire immutable resident/enemy/helper and installed active
                # blobs were compared before interpreting these entry labels.
                if name=='adaptive_audio_binding':name+='_'+str(regs['a'])
                if name=='frame_render_background':
                    totals.setdefault('background_requests',[]).append({'flags':read(0x7F,16).hex(),'cell':read(9,2).hex()})
                frames.append({'name':name,'return':ret,'stack':regs['s'],'start':now,'children':0})
    finally:m.clear(c,list(ids.values()))

def measure():
    global started
    full=started and c.call('read_registers')['pc']!=ms['ad_dispatch_work']
    go(parser_start if full else ms['ad_dispatch_work']);started=True
    before={'raw':int.from_bytes(read(2,2),'big'),'logical':int.from_bytes(read(0xBD26,2),'big'),'debt':int.from_bytes(read(0xBD28,2),'big'),'mode':read(0xA5)[0],'owner':read(0x90)[0],'enemies':read(ms['ENEMY_ACTIVE'])[0],'rate':read(0xBD34)[0],'cycles_scope':'input-parser-through-return' if full else 'active-driver-through-return'}
    start=c.call('read_cycles')['event_ticks']
    detail,hits=profiled_return() if profile_enabled else (None,None)
    if not profile_enabled:go(ms['mainloop'])
    ticks=c.call('read_cycles')['event_ticks']-start
    before.update(cycles=ticks//8,logical_after=int.from_bytes(read(0xBD26,2),'big'),debt_after=int.from_bytes(read(0xBD28,2),'big'),counts=list(read(0xBD38,2)),fault=read(0xBD3A)[0],pending=read(0x91)[0],late=phys(0x3D,ads['audio_adaptive_late'],1)[0]);assert before['fault']==0,before
    if detail is not None:
        before.update(profile=detail,enemy_records=read(es['ENEMY_TABLE'],32).hex(),breakpoint_hits=hits,intents_after=read(0x7F,16).hex(),colour=read(ms['BONUS_COLOR'])[0])
    return before
try:
    go(ps['attract_tick_ready'])
    assert read(0xC000,0x3E00)==(b/'ladybug-runtime.rom').read_bytes()[:0x3E00],'resident source/live identity'
    enemy=(b/'ladybug-enemy-runtime.rom').read_bytes();assert read(0x800,len(enemy))==enemy,'enemy source/live'
    helper=(b/'ladybug-adaptive-banked.bin').read_bytes();assert phys(0x34,0xBD44,len(helper))==helper,'journal helper source/live'
    audio=(b/'ladybug-audio-runtime.bin').read_bytes();api=audio[ads['audio_adaptive_api']-0xA000:ads['audio_adaptive_last']-0xA000];assert phys(0x3D,ads['audio_adaptive_api'],len(api))==api,'banked adaptive API code source/live'
    stage=(b/'ladybug-adaptive-active.bin').read_bytes();assert phys(0x3D,ads['audio_adaptive_stage'],len(stage))==stage,'active stage source/live'
    e['identity']={'resident':0x3E00,'enemy':len(enemy),'helper':len(helper),'staged_active':len(stage),'banked_audio':len(audio)}
    layout=json.loads((b/'ladybug-sparse-layout.json').read_text())
    if 'vegetable' in layout:
        prefix=b''.join((b/name).read_bytes() for name in ('ladybug-player-sparse.bin','ladybug-gate-transitions.bin','ladybug-presentation-sparse.bin'))
        vegetable=(b/'ladybug-vegetable-sparse.bin').read_bytes()
        assert len(prefix)==0xFB6 and phys(0x39,0xA000,len(prefix)+len(vegetable))==prefix+vegetable,'page39 prefix and appended vegetable cold delivery'
        e['identity']['vegetable_streams']=len(vegetable)
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
        profile_enabled='--profile' in sys.argv[3:] and count==4
        samples=[measure() for _ in range(3)]
        assert all(x['enemies']==count and x['fault']==0 for x in samples)
        e['cases'].append({'name':'controlled enemy release count','count':count,'worklists':samples})
    deadline=time.monotonic()+45
    # Controlled quiet counterpart retains all four actors. Silence admitted
    # voices explicitly rather than waiting long enough for a player death.
    for i in range(4):apwrite(ads['audio_slot0']+i*28,[255])
    apwrite(ads['audio_music_count'],[0]);write(ads['AUDIO_Q_COUNT'],[0]);write(ads['AUDIO_CREDIT_PENDING'],[0])
    regs=c.call('read_registers');stack=read(0x1E00,512);stub=read(RET,2);call(0x39B,3);write(0x1E00,stack);write(RET,stub);c.call('write_registers',{k:regs[k] for k in ('a','b','cc','dp','x','y','u','s','pc')})
    quiet=[measure() for _ in range(8)]
    assert all(x['enemies']==4 and x['mode']==0 for x in quiet),'four-enemy quiet fixture lost active population'
    e['cases'].append({'name':'controlled four-enemy quiet worklists','forced_audio_silence':True,'worklists':quiet,'pixels_sha256':[r.digest(r.read_owner(c,k)) for k in (0,1)]})
    # A distinct steady phase requires every actor to have entered roaming ownership.
    deadline=time.monotonic()+45;steady=[];settled=0
    gateway=audio[ads['audio_service_gateway_bytes']-0xA000:ads['audio_service_gateway_bytes']-0xA000+18]
    assert read(ads['AUDIO_SERVICE_GATEWAY'],18)==gateway,'quiet fixture modified gateway'
    for _ in range(32):
        table=read(es['ENEMY_TABLE'],32)
        roaming=all(table[i] and table[i+6] for i in range(0,32,8))
        row=measure();settled+=1
        assert row['enemies']==4 and row['mode']==0,'steady fixture lost actors/phase'
        if roaming:steady.append(row)
        if len(steady)>=8:break
    assert len(steady)==8,'eight four-roaming worklists absent within 32 samples'
    e['cases'].append({'name':'controlled steady four-roaming worklists','settling_worklists':settled,'worklists':steady,'forced_prior_audio_silence':True})
    profile_enabled=False
    # Compare multi-record replay against sequential identical intent packets.
    pages=[0,*range(0x2C,0x35),0x38,0x3D]
    def snapshot_pages():
        return {page:bytes.fromhex(c.call('read_memory',{'space':'physical','addr':page*8192,'length':8192})['data']) for page in pages}
    def restore_pages(data):
        for page,raw in data.items():c.call('write_memory',{'space':'physical','addr':page*8192,'data':raw.hex()})
        write(0xFFA5,[0x34])
    frozen=snapshot_pages();natural_regs=c.call('read_registers')
    if '--pickup-gate-cadence' in sys.argv[3:]:
        # Enter real player_tick with a bounded, legal event precondition.  The
        # ensuing worklists include simulation, rendering, input and audio.
        maze=json.loads((w/'assets/arcade/maze.json').read_text())
        fitted=(Path(__file__).parent/'bug058-catchup-banked-fit.bin').read_bytes() if '--two-step-cap-fit' in sys.argv[3:] else None
        if fitted:
            assert len(fitted)<=698 and phys(0x34,0xBD44,len(helper))==helper,'fitted helper baseline identity'
            e['two_step_cap_fit']={'banked_bytes':len(fitted),'limit':698,'helper_sha256':r.digest(fitted),'delivery':'controlled physical-page-34 overlay after original ROM identity; no built ROM alteration'}
        def reset_event():
            restore_pages(frozen)
            if fitted:
                c.call('write_memory',{'space':'physical','addr':0x34*8192+0xBD44-0xA000,'data':fitted.hex()})
                assert phys(0x34,0xBD44,len(fitted))==fitted,'fitted helper live identity'
            c.call('write_registers',{k:natural_regs[k] for k in ('a','b','cc','dp','x','y','u','s','pc')})
            write(ms['PLAYER_MANUAL'],[0]);write(ms['TURN_SNAP'],[0])
        def place(x,y,direction,steps):
            stride=(-320,1,320,-1)[direction]
            base=0x2000+(y*8-8)*160+(x+7)*4
            write(ms['PLAYER_CELL_X'],[x,y]);write(ms['PLAYER_DIR'],[direction]);write(ms['PLAYER_WANT'],[direction]);write(ms['PLAYER_STEP'],[steps])
            word(ms['PLAYER_FB'],base+steps*stride)
        entities=read(ms['ENTITY_TABLE'],read(ms['ENTITY_COUNT'])[0]*4)
        pickup=None
        for i in range(0,len(entities),4):
            x,y,kind=entities[i:i+3]
            if kind not in (2,3):continue
            for direction,dx,dy,reverse in ((0,0,1,4),(1,-1,0,8),(2,0,-1,1),(3,1,0,2)):
                px,py=x+dx,y+dy
                if 0<=px<24 and 0<=py<24 and maze['maze_nav'][y][x]&reverse and maze['maze_nav'][py][px]&(1<<direction):
                    pickup=(i//4,x,y,kind,px,py,direction);break
            if pickup:break
        assert pickup,'legal pickup approach absent'
        e['pickup_gate_cadence']=[]
        deadline=time.monotonic()+45;reset_event()
        quiet_rows=[]
        for _ in range(12):
            row=measure();row['steps']=(row['logical_after']-row['logical'])&65535;quiet_rows.append(row)
        assert all(row['steps']==2 and row['enemies']==4 and row['mode']==0 and row['fault']==0 for row in quiet_rows),'quiet two-step control failed'
        e['pickup_gate_quiet_control']={'worklists':quiet_rows,'both_owners':{row['owner'] for row in quiet_rows}=={0,1},'pixels_sha256':[r.digest(r.read_owner(c,k)) for k in (0,1)]}
        for name in ('pickup','gate rotation'):
            deadline=time.monotonic()+45;reset_event()
            if name=='pickup':
                idx,x,y,kind,px,py,direction=pickup
                place(px,py,direction,3)
                before=read(ms['BONUS_LEFT'])[0]
                def marker():return {'bonus_left':read(ms['BONUS_LEFT'])[0],'pickup_timer':read(ms['PICKUP_TIMER'])[0],'entity_type':read(ms['ENTITY_TABLE']+idx*4+2)[0]}
            else:
                gate=maze['gates'][0];gx,gy=gate['pivot']
                assert maze['gate_owner'][gy][gx-1]==1 and not read(ms['GATE_STATE'])[0]
                place(gx-1,gy+1,0,0)
                before=read(ms['GATE_STATE'])[0]
                def marker():return {'gate_state':read(ms['GATE_STATE'])[0],'gate_animation':read(ms['GATE_ANIM_ID'])[0]}
            rows=[];event_at=None
            for index in range(58 if name=='pickup' else 12):
                profile_enabled=index<2 or (name=='gate rotation' and index in (7,8))
                row=measure();row['steps']=(row['logical_after']-row['logical'])&65535
                row['marker']=marker();rows.append(row)
                changed=(row['marker']['bonus_left']<before if name=='pickup' else row['marker']['gate_state']!=before)
                if changed and event_at is None:event_at=index
                assert row['mode']==0 and row['enemies']==4 and row['fault']==0,'event fixture left active four-enemy phase'
            assert event_at is not None,(name,'real event marker absent')
            profile_enabled=False
            e['pickup_gate_cadence'].append({'name':name,'setup':pickup if name=='pickup' else {'gate_id':0,'pivot':gate['pivot'],'from':[gx-1,gy+1],'direction':0},'event_worklist':event_at,'worklists':rows,'deadline_seconds':45})
        reset_event()
    if '--cadence-effects' in sys.argv[3:]:
        # Separate the audio path from the already-measured colour event.
        # Direct cue insertion changes no gameplay state or framebuffer intent.
        e['cadence_effects']=[]
        for name,cue in (('release effect',5),('music cue',9)):
            restore_pages(frozen);c.call('write_registers',{k:natural_regs[k] for k in ('a','b','cc','dp','x','y','u','s','pc')})
            deadline=time.monotonic()+45
            write(0xFFA5,[0x3D]);call(ads['audio_enqueue_impl'],cue);write(0xFFA5,[0x34])
            c.call('write_registers',{k:natural_regs[k] for k in ('a','b','cc','dp','x','y','u','s','pc')})
            rows=[];heard=False
            for _ in range(12):
                row=measure();row['steps']=(row['logical_after']-row['logical'])&65535
                row['slots']=list(phys(0x3D,ads['audio_slot0'],112)[::28]);rows.append(row)
                heard |= cue in row['slots']
                assert row['enemies']==4 and row['mode']==0 and row['fault']==0,'cue fixture left active four-enemy phase'
            assert heard,('cue not admitted',name)
            e['cadence_effects'].append({'name':name,'cue':cue,'cue_admitted':heard,'worklists':rows,'deadline_seconds':45})
        restore_pages(frozen);c.call('write_registers',{k:natural_regs[k] for k in ('a','b','cc','dp','x','y','u','s','pc')})
    if '--sustained-timing' in sys.argv[3:]:
        # A longer real foreground sequence from the proved four-roaming
        # fixture. Preserve its pixels, stack and histories for later gates.
        deadline=time.monotonic()+45;rows=[];profile_enabled=False
        for index in range(64):
            row=measure();row.update(death=read(ms['DEATH_STATE'])[0],roaming=all(read(es['ENEMY_TABLE']+i+6)[0] for i in range(0,32,8)))
            rows.append(row)
            if row['enemies']!=4 or row['mode']!=0 or row['death'] or not row['roaming']:break
        e['sustained_timing']={'scope':'real foreground continuation from controlled four-roaming quiet fixture; player parked at legal22,22 and prior audio explicitly silenced',
            'required_worklists':64,'observed_worklists':len(rows),'sequence_complete':len(rows)==64 and all(row['enemies']==4 and row['mode']==0 and not row['death'] and row['roaming'] for row in rows),
            'deadline_seconds':45,'target_cycles':27000,'cycle_range':[min(row['cycles'] for row in rows),max(row['cycles'] for row in rows)],
            'timing_pass':all(row['cycles']<=27000 for row in rows),'worklists':rows,'both_owners':{row['owner'] for row in rows}=={0,1}}
        restore_pages(frozen);c.call('write_registers',{k:natural_regs[k] for k in ('a','b','cc','dp','x','y','u','s','pc')})
        # Force only clock debt/due state. The installed scheduler and actual
        # logic must execute four steps; transient barriers remain effective.
        deadline=time.monotonic()+45;word(0xBD28,4);word(0xBD30,int.from_bytes(read(2,2),'big'))
        profile_enabled=True;row=measure();profile_enabled=False
        steps=(row['logical_after']-row['logical'])&65535
        e['four_step_timing']={'scope':'forced scheduler debt; real parser, simulation, audio and composition; a barrier may shorten this worklist',
            'executed_steps':steps,'four_step_marker':steps==4,'target_cycles':27000,'timing_pass':row['cycles']<=27000,'worklist':row,'deadline_seconds':45}
        restore_pages(frozen);c.call('write_registers',{k:natural_regs[k] for k in ('a','b','cc','dp','x','y','u','s','pc')})
        deadline=time.monotonic()+45;colour_before=read(ms['BONUS_COLOR'])[0]
        assert read(ms['BONUS_LEFT'])[0]>0,'colour boundary fixture has no remaining collectibles'
        word(ms['BONUS_TIMER'],1);colour_rows=[]
        for index in range(12):
            profile_enabled=index<2;row=measure();row.update(colour=read(ms['BONUS_COLOR'])[0],death=read(ms['DEATH_STATE'])[0]);colour_rows.append(row)
            assert row['enemies']==4 and row['mode']==0 and row['fault']==0 and not row['death'],'colour-boundary continuation lost active fixture'
        profile_enabled=False
        assert colour_rows[0]['colour']!=colour_before and {row['owner'] for row in colour_rows}=={0,1},'colour boundary or alternating history marker absent'
        e['colour_boundary_timing']={'scope':'force only the existing bonus timer to1; actual colour tick, two retained histories and12 foreground worklists',
            'deadline_seconds':45,'target_cycles':27000,'colour_before':colour_before,
            'cycle_range':[min(row['cycles'] for row in colour_rows),max(row['cycles'] for row in colour_rows)],
            'timing_pass':all(row['cycles']<=27000 for row in colour_rows),'worklists':colour_rows,'both_owners':True}
        restore_pages(frozen);c.call('write_registers',{k:natural_regs[k] for k in ('a','b','cc','dp','x','y','u','s','pc')})
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
    def packet(flags=0,flags2=0,box=(0,0),letter=(0,0,0),gates=(0,0,0,0,0,0)):
        return bytes([flags,flags2,*box,*letter,0,0,*gates[:4],0,*gates[4:]])
    scenarios={
        'one gate diagonal then final':[(packet(gates=(1,0,0,0,0,0)),(22,22)),(packet(gates=(1,1,0,0,0,0)),(22,22))],
        'HUD/colour/nest/multiplier':[(packet(2), (22,22)),(packet(0,16), (22,22)),(packet(0,2), (22,22))],
        'distinct/repeated keyed coverage':[(packet(0x30,4,(5,6),(1,2,3),(1,1,2,1,0,1)),(2,4)),(packet(0x30,4,(6,5),(2,2,1),(2,0,1,0,0,1)),(4,4)),(packet(0x30,4,(5,5),(1,2,1),(1,1,2,1,0,1)),(2,4))],
        'perimeter reset dominates old boxes':[(packet(0x10,0,(5,6)),(22,22)),(packet(0,8),(22,22)),(packet(0x10,0,(6,5)),(22,22))],
        'stage dominates preceding coverage':[(packet(0x30,4,(5,6),(1,2,3),(1,1,2,1,0,1)),(2,4)),(packet(0x40),(22,22))]}
    scenarios['legal cross-slot gate transitions']=[(packet(gates=(1,0,0,0,0,0)),(22,22)),(packet(gates=(1,1,2,0,0,0)),(22,22)),(packet(gates=(2,1,0,0,0,0)),(22,22))]
    mixed=scenarios.pop('distinct/repeated keyed coverage')
    for class_name,mask1,mask2,gates in [('dots',0x20,0,False),('timer boxes',0x10,0,False),('letters',0,4,False),('gates',0,0,True)]:
        isolated=[]
        for intent,cell in mixed:
            v=bytearray(intent);v[0]&=mask1;v[1]&=mask2
            if not gates:v[9]=v[11]=0
            isolated.append((bytes(v),cell))
        if not gates:scenarios[class_name+' distinct/repeated keys']=isolated
    scenarios['mixed keyed coverage']=[(bytes(v[:9])+bytes(7),cell) for v,cell in mixed]
    for scenario,records in scenarios.items():
      for owner in (0,1):
        deadline=time.monotonic()+45;restore_pages(frozen);call(0x9FD);write(0x91,[0]);write(0x8F,[1-owner]);write(0x90,[owner])
        front=r.read_owner(c,1-owner)
        if scenario in ('one gate diagonal then final','legal cross-slot gate transitions'):
            n=2 if scenario=='legal cross-slot gate transitions' else 1
            write(es['GATE_STATE'],bytes(v^1 for v in read(es['GATE_STATE'],n)))
        for intent,cell in records:
            write(0x7F,intent);write(9,cell);_,regs=call(0xA03);assert regs['cc']&1==0,('append fault',scenario,owner)
        counts=list(read(0xBD38,2));assert counts==[len(records)]*2
        write(0x7F,bytes(16));render_detail=None
        if '--sustained-timing' in sys.argv[3:] and owner==0 and scenario in ('HUD/colour/nest/multiplier','legal cross-slot gate transitions','mixed keyed coverage'):
            write(0x1EFC,[RET>>8,RET&255]);write(RET,[0x20,0xFE]);c.call('write_registers',{'pc':0x39E,'s':0x1EFC,'dp':0,'cc':0x50,'a':0})
            start=c.call('read_cycles')['event_ticks'];render_detail,hits=profiled_return(RET)
            render_cycles=(c.call('read_cycles')['event_ticks']-start)//8;regs=c.call('read_registers')
        else:render_cycles,regs=call(0x39E)
        assert regs['cc']&1==0 and read(0xBD3A)==bytes([0])
        actual=r.read_owner(c,owner);assert r.read_owner(c,1-owner)==front,('front changed',scenario,owner)
        restore_pages(frozen);write(0x91,[0]);write(0x8F,[1-owner]);write(0x90,[owner]);write(0x7F,bytes(16))
        call(es['framebuffer_prepare_back']);write(es['ENEMY_CAPTURE_DIRTY'],[0]);call(es['colour_prepare_nest']);call(es['actor_closure_restore'])
        if scenario in ('one gate diagonal then final','legal cross-slot gate transitions'):
            n=2 if scenario=='legal cross-slot gate transitions' else 1
            write(es['GATE_STATE'],bytes(v^1 for v in read(es['GATE_STATE'],n)))
        for intent,cell in records:
            write(0x7F,intent);write(9,cell)
            if intent[0]&0x40:write(es['ENEMY_RENDER_FLAGS'],[9])
            call(es['colour_prepare_nest']);call(es['roam_mark_underlay']);call(es['frame_render_background'])
        write(0x7F,bytes(16));call(es['actor_closure_draw']);expected=r.read_owner(c,owner)
        if actual!=expected:
            offsets=[i for i,(x,y) in enumerate(zip(actual,expected)) if x!=y]
            e['pixel_failure']={'scenario':scenario,'owner':owner,'difference_bytes':len(offsets),'rows':sorted(set(i//160 for i in offsets))[:32],'first':[{'offset':i,'candidate':actual[i],'sequential':expected[i]} for i in offsets[:20]],'candidate_sha256':r.digest(actual),'sequential_sha256':r.digest(expected)}
            raise AssertionError('multi-record pixels differ from sequential replay')
        e['pixel_cases'].append({'scenario':scenario,'owner':owner,'history_counts':counts,'render_only_cycles':render_cycles,'render_profile':render_detail,'pixels_exact':True,'sha256':r.digest(actual)})
    restore_pages(frozen)
    e['installed_input_overlay_cases']=[]
    deadline=time.monotonic()+45;restore_pages(frozen);call(0x9FD)
    write(0x91,[0]);write(0xA5,[0]);write(0xA9,[0]);write(0x7F,bytes(16));word(2,1000);word(0xBD24,1000);word(0xBD2C,1000);word(0xBD30,1002);write(5,[255])
    c.call('inject_key',{'key':0x2E,'action':'press'});call(0x38F);call(0x38F)
    assert read(5)==bytes([1]) and read(0xBD26,2)==bytes(2),'held right not sampled independently of simulation'
    c.call('inject_key',{'key':0x2E,'action':'release'});call(0x38F);assert read(5)==bytes([255]),'released direction not sampled'
    write(0xA5,[4]);write(5,[0]);c.call('inject_key',{'key':0x2E,'action':'press'});call(0x38F);assert read(5)==bytes([0]),'demo consumed physical input';c.call('inject_key',{'key':0x2E,'action':'release'})
    e['installed_input_overlay_cases'].append({'name':'held/released acquisition before simulation due; demo input exclusion','pass':True,'logical_steps':0})
    for overlay in ('instruction','highscore'):
        deadline=time.monotonic()+45;restore_pages(frozen)
        blob=(b/f'ladybug-{overlay}-runtime.bin').read_bytes();front_id=read(0x8F)[0];front=r.read_owner(c,front_id)
        write(0x300,blob);assert read(0x38F,len(stage))!=stage,'overlay did not displace active driver'
        call(ms['adaptive_install_active']);assert read(0x38F,len(stage))==stage and read(0x300,0x8F)==blob[:0x8F],'reentry copy mismatch'
        call(0x9FD);assert read(0xBD38,2)==bytes(2) and read(0xFFA5)[0]&63==0x34 and r.read_owner(c,front_id)==front
        e['installed_input_overlay_cases'].append({'name':overlay+' overlay to active installer/reset','overlay_bytes':len(blob),'active_bytes':len(stage),'front_unchanged':True,'controlled_not_natural_flow':True})
    restore_pages(frozen)
    if '--drain-probe' in sys.argv[3:]:
        deadline=time.monotonic()+45
        for i in range(4):apwrite(ads['audio_slot0']+i*28,[255])
        apwrite(ads['audio_music_count'],[0]);apwrite(ads['audio_stop_pending'],[0]);write(ads['AUDIO_Q_HEAD'],bytes(4));write(ads['AUDIO_CREDIT_PENDING'],[0]);write(0xA5,[0]);write(ms['DEATH_STATE'],[0]);write(ms['STAGE_PENDING'],[1]);word(2,1000);call(0x39B,3)
        write(0xFFA5,[0x3D]);c.call('write_registers',{'b':0});call(ads['audio_enqueue_impl'],9);write(0xFFA5,[0x34])
        observed=[]
        for tick in (1001,1002,1003):
            word(2,tick);cycles,regs=call(ads['AUDIO_GUARD_RAM']);observed.append({'tick':tick,'cycles':cycles,'busy':regs['a'],'music_count':phys(0x3D,ads['audio_music_count'],1)[0],'slot0':phys(0x3D,ads['audio_slot0'],1)[0],'page34':read(0xFFA5)[0]&63==0x34})
        e['audio_drain_admission']=observed
        assert any(row['slot0']==9 for row in observed),'active boundary guard never admits pending music'
        completion=[]
        for tick in range(1004,1260):
            assert time.monotonic()<deadline,'45-second queued music drain deadline'
            word(2,tick);cycles,regs=call(ads['AUDIO_GUARD_RAM']);completion.append((regs['a'],cycles))
            assert read(0xFFA5)[0]&63==0x34,'drain mapping not restored'
            if regs['a']==0:break
        assert completion[-1][0]==0 and all(x[0]==1 for x in completion[:-1]),'queued music failed bounded completion'
        assert phys(0x3D,ads['audio_slot0'],112)[::28]==bytes([255]*4) and phys(0x3D,ads['audio_music_count'],1)==bytes([0]),'guard released with active audio'
        e['audio_drain_completion']={'calls':len(completion),'maximum_cycles':max(x[1] for x in completion),'releases_only_when_empty':True,'page34':True}
        # Full low-priority effect FIFO must admit important replacements.
        write(ads['AUDIO_Q_HEAD'],bytes(4));write(0xFFA5,[0x3D])
        for cue in (3,3,3,3,0,5,1,2):c.call('write_registers',{'b':0});call(ads['audio_enqueue_impl'],cue)
        high=list(read(ads['AUDIO_Q_DATA'],8)[::2]);c.call('write_registers',{'b':0});call(ads['audio_enqueue_impl'],4);low=list(read(ads['AUDIO_Q_DATA'],8)[::2]);write(0xFFA5,[0x34])
        assert high==[0,5,1,2] and low==high,'important effect priority regression'
        word(2,1300);cycles,regs=call(ads['AUDIO_GUARD_RAM']);slots=phys(0x3D,ads['audio_slot0'],112)
        assert any(slots[i] in (0,5,1,2) and slots[i+3]>0 for i in range(28,112,28)) and read(ads['AUDIO_Q_COUNT'])==bytes([0]),'drain did not admit queued effects'
        e['audio_priority_drain']={'important_fifo':high,'lower_tick_fifo':low,'effects_admitted_with_positive_wait':True,'guard_cycles':cycles}
        for i in range(4):apwrite(ads['audio_slot0']+i*28,[255])
        apwrite(ads['audio_music_count'],[0]);write(ads['AUDIO_Q_HEAD'],bytes(4));write(ads['AUDIO_CREDIT_PENDING'],[0])
        word(2,1500);call(0x39B,3);write(0xFFA5,[0x3D]);c.call('write_registers',{'b':0});call(ads['audio_enqueue_impl'],9);write(0xFFA5,[0x34]);write(ads['AUDIO_CREDIT_PENDING'],[1])
        deadline=time.monotonic()+45;parked=0;delivered=0
        for tick in range(1501,1800):
            word(2,tick);call(ads['AUDIO_GUARD_RAM']);slots=phys(0x3D,ads['audio_slot0'],112)
            if slots[0]!=255:
                assert read(ads['AUDIO_CREDIT_PENDING'])==bytes([1]) and slots[28]!=12,'credit consumed behind active music';parked+=1
            if slots[28]==12:
                assert slots[0]==255 and slots[31]>0 and read(ads['AUDIO_CREDIT_PENDING'])==bytes([0]),'credit admission/wait failure';delivered+=1
                period=phys(0x3D,ads['audio_mix_periods'],2);atten=phys(0x3D,ads['audio_mix_atten'],1)
                assert period==slots[34:36] and atten==slots[40:41],'credit not selected into mixer'
            if delivered and slots[28]!=12:break
        assert parked and delivered and slots[28]!=12,'parked credit never delivered/completed'
        e['audio_credit_parking']={'music_owned_calls':parked,'credit_mixed_calls':delivered,'completed':True,'mapping_restored':read(0xFFA5)[0]&63==0x34}

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
        trace=trace_output() if '--psg-trace' in sys.argv[3:] else None
        if trace is None:call(0x39B,2)
        e['audio_cases'].append({'elapsed':elapsed,'cycles':cycles,'wait_after':after[3],'late':phys(0x3D,ads['audio_adaptive_late'],1)[0],'page34_return':read(0xFFA5)[0]&63==0x34,'psg_trace':trace})
    # Unsigned raw-clock wrap; inactive voices stay inactive.
    apwrite(0xA000,saved_audio);write(0,saved_dp);word(2,65534);call(0x39B,3);word(2,2);call(0x39B,0);assert phys(0x3D,ads['audio_adaptive_delta'],2)==b'\0\4'
    wrap_trace=trace_output() if '--psg-trace' in sys.argv[3:] else None
    e['audio_cases'].append({'elapsed':'wrap FFFE->0002','delta':4,'psg_trace':wrap_trace})
    if '--vegetable-cost' in sys.argv[3:]:
        import build_screen as screen
        import build_sparse_sprites as sparse
        deadline=time.monotonic()+45
        frames=screen.compile_sprite_codes(w/'assets/arcade/sprites.json',screen.VEGETABLE_CODES)
        pair=resident[ms['sprite_attr0_pairs']-0xC000:ms['sprite_attr0_pairs']-0xC000+16];pen=tuple(pair[i]&15 for i in range(4));e['vegetable_stage_costs']=[]
        for frame,raw in enumerate(frames):
            costs=[]
            for background in (bytes(128),bytes([0x55])*128,bytes((i*19+7)&255 for i in range(128))):
                write(0xFFA5,[0x34]);write(ms['STAGE'],[frame+1]);write(0x1800,background);c.call('write_registers',{'x':0x1800,'y':ms['vegetable_sprites']+frame*64,'u':ms['sprite_attr0_pairs']});old_cost,_=call(es['blit_stage_sprite']);expected=read(0x1800,128)
                write(0x1800,background);c.call('write_registers',{'x':0x1800});new_cost,_=call(es['draw_vegetable_stage']);actual=read(0x1800,128)
                assert actual==expected and read(0xFFA5)[0]&63==0x34,('vegetable stage pixels/mapping',frame)
                assert new_cost<=3000,('vegetable selector cycle target',frame,new_cost)
                costs.append({'legacy':old_cost,'decoder':new_cost,'saved':old_cost-new_cost})
            e['vegetable_stage_costs'].append({'stage':frame+1,'stream_bytes':layout['vegetable']['index'][frame]['bytes'],'backgrounds_exact':3,'costs':costs})
        e['vegetable_selector_bounds']=[]
        for number,frame in ((0,0),(19,17),(255,17)):
            background=bytes([0x55])*128;write(0xFFA5,[0x34]);write(0x1800,background);c.call('write_registers',{'x':0x1800,'y':ms['vegetable_sprites']+frame*64,'u':ms['sprite_attr0_pairs']});call(es['blit_stage_sprite']);expected=read(0x1800,128)
            write(ms['STAGE'],[number]);write(0x1800,background);c.call('write_registers',{'x':0x1800});cycles,_=call(es['draw_vegetable_stage']);assert read(0x1800,128)==expected and read(0xFFA5)[0]&63==0x34,('vegetable clamp',number)
            assert cycles<=3000,('vegetable clamp cycle target',number,cycles)
            e['vegetable_selector_bounds'].append({'stage':number,'frame':frame,'cycles':cycles,'pixels_exact':True,'page34':True})
        e['vegetable_cost_scope']='Installed selector plus decoder, compared with existing raw painter without legacy selector overhead; cold index/stream delivery proved. All 18 images x3 backgrounds and bounds 0/19/255 exact.'
    if '--life-reentry' in sys.argv[3:]:
        # Force only the already-defined terminal blank boundary; resume the
        # actual foreground stack rather than invoking a simulated tick.
        restore_pages(frozen);c.call('write_registers',{k:natural_regs[k] for k in ('a','b','cc','dp','x','y','u','s','pc')})
        write(ms['DEATH_STATE'],[3]);write(ms['DEATH_TIMER'],[0]);write(ms['LIVES'],[1])
        deadline=time.monotonic()+45;rows=[]
        for _ in range(80):
            row=measure();row.update(death=read(ms['DEATH_STATE'])[0],lives=read(ms['LIVES'])[0],player_cell=read(ms['PLAYER_CELL_X'],2).hex(),player_fb=read(ms['PLAYER_FB'],2).hex());rows.append(row)
            assert row['mode']==0 and row['fault']==0,'life reentry left active mode or faulted'
            if row['death']==0 and row['lives']==0 and int.from_bytes(read(ms['PLAYER_FB'],2),'big')==0x75EC:break
        assert rows[-1]['player_fb']=='75ec' and rows[-1]['death']==0 and rows[-1]['lives']==0,'life replacement entrance marker missing within 80 worklists'
        assert read(0x38F,len(stage))==stage and {x['owner'] for x in rows}=={0,1},'life replacement code/owner sequence'
        e['life_reentry']={'scope':'forced terminal blank boundary, real foreground continuation through replacement entrance','worklists':rows,'both_owners':True,'active_code_exact':True,'deadline_seconds':45}
        if '--natural-turn' in sys.argv[3:]:
            # Maze navigation at the actual entrance (12,18) has N/W exits.
            # Hold north for one partial-cell step, then request west early.
            nav=json.loads((w/'assets/arcade/maze.json').read_text())['maze_nav'];assert nav[18][12]&9==9
            deadline=time.monotonic()+45;control=[]
            def movement_sample():
                row=measure();row.update(direction=read(ms['PLAYER_DIR'])[0],step=read(ms['PLAYER_STEP'])[0],snap=read(ms['TURN_SNAP'])[0],cell=read(ms['PLAYER_CELL_X'],2).hex(),fb=read(ms['PLAYER_FB'],2).hex());control.append(row);return row
            c.call('inject_key',{'key':0x2B,'action':'press'})
            for _ in range(12):
                row=movement_sample()
                if row['step']==1:break
            assert row['direction']==0 and row['step']==1,'natural held north partial-step marker absent'
            c.call('inject_key',{'key':0x2B,'action':'release'});c.call('inject_key',{'key':0x2D,'action':'press'})
            for _ in range(8):
                row=movement_sample()
                if row['snap']:break
            assert row['direction']==3 and row['snap']==1,'natural early-west snap marker absent'
            for _ in range(4):row=movement_sample()
            assert row['direction']==3 and row['snap']==0,'natural corner failed alignment completion'
            c.call('inject_key',{'key':0x2D,'action':'release'});anchor=read(ms['PLAYER_FB'],2)
            for _ in range(3):movement_sample()
            assert read(ms['PLAYER_FB'],2)==anchor and read(5)==bytes([255]),'neutral input failed to stop player'
            e['natural_directional_control']={'scope':'real input/parser/simulation/publication after forced life boundary; held north, early west and neutral stop','worklists':control,'both_owners':{x['owner'] for x in control}=={0,1},'pixels_sha256':[r.digest(r.read_owner(c,k)) for k in (0,1)]}
        if '--phase-handoffs' in sys.argv[3:]:
            # Both transitions use the authored dispatcher and loaders.
            # Only end-of-level/death and static dwell boundaries are forced.
            e['phase_handoffs']=[]
            def phase_until(label,predicate,limit=700):
                global deadline
                deadline=time.monotonic()+45;changes=[];previous=None
                for index in range(limit):
                    go(parser_start);go(ms['mainloop'])
                    state={'mode':read(0xA5)[0],'screen':read(0xA6)[0],'stage':read(ms['STAGE'])[0],'owner':read(0x8F)[0]}
                    if state!=previous:changes.append(state);previous=state
                    if predicate(state):
                        e['phase_handoffs'].append({'name':label,'samples':index+1,'changes':changes,'deadline_seconds':45});return
                raise AssertionError(label+' marker absent within bounded dispatcher samples')
            write(ms['STAGE_PENDING'],[1])
            phase_until('real next-stage dispatcher reaches level-start screen',lambda s:s['mode']==6 and s['stage']==2)
            word(ps['PRES_TIMER'],179)
            phase_until('level-start returns to installed adaptive gameplay',lambda s:s['mode']==0 and s['stage']==2)
            assert read(0x38F,len(stage))==stage,'stage handoff active installation'
            stage_rows=[measure() for _ in range(8)]
            assert {x['owner'] for x in stage_rows}=={0,1} and all(x['fault']==0 for x in stage_rows),'stage history/publication sequence'
            write(ms['SCORE_BCD'],bytes.fromhex('095000'));write(ms['DEATH_STATE'],[4]);write(ms['LIVES'],[0])
            phase_until('real terminal dispatcher reaches game-over screen',lambda s:s['mode']==7)
            highscore=(b/'ladybug-highscore-runtime.bin').read_bytes();assert read(0x300,len(highscore))==highscore,'game-over phase overlay identity'
            word(ps['PRES_TIMER'],179)
            phase_until('game-over dispatcher reaches name screen',lambda s:s['mode']==8)
            assert read(0x300,len(highscore))==highscore,'name overlay identity'
            hs=r.symbols(b/'ladybug-highscore-runtime.map')
            write(hs['PRES_NAME_FLAGS'],[1])
            phase_until('name completion drains and publishes high scores',lambda s:s['mode']==5)
            c.call('inject_key',{'key':5,'action':'press'});go(parser_start);go(ms['mainloop']);c.call('inject_key',{'key':5,'action':'release'})
            c.call('inject_key',{'key':1,'action':'press'});go(parser_start);go(ms['mainloop']);c.call('inject_key',{'key':1,'action':'release'})
            phase_until('new credited game restores adaptive overlay after name screen',lambda s:s['mode']==6)
            word(ps['PRES_TIMER'],179)
            phase_until('credited reentry returns to adaptive gameplay',lambda s:s['mode']==0)
            assert read(0x38F,len(stage))==stage,'name-to-game active installation'
            phase_until('credited entrance completes before full death fixture',lambda s:s['mode']==0 and read(ms['INITIAL_ENTRY_STATE'])==bytes([0]))
            write(ms['LIVES'],[1]);write(ms['DEATH_STATE'],[1]);write(ms['DEATH_TIMER'],[0]);write(ms['DEATH_FRAME'],[0]);write(ms['PLAYER_DIR'],[255]);write(ms['PLAYER_WANT'],[255])
            deadline=time.monotonic()+45;death_states=set();owners=set();samples=0;frames={}
            for samples in range(700):
                go(parser_start);go(ms['mainloop']);death=read(ms['DEATH_STATE'])[0];death_states.add(death);owners.add(read(0x8F)[0])
                if death not in frames:frames[death]=r.digest(r.read_owner(c,read(0x8F)[0]))
                assert read(0xA5)==bytes([0]) and read(0xBD3A)==bytes([0]),'full death continuation left gameplay or faulted'
                if death==0 and read(ms['LIVES'])==bytes([0]) and read(ms['PLAYER_FB'],2)==bytes.fromhex('75ec'):break
            assert death_states=={0,1,2,3} and owners=={0,1} and samples<699,'full shrink/wings/blank/replacement marker missing'
            e['full_death_continuation']={'scope':'forced valid death-start state, real foreground through full shrink/wings/blank and replacement entrance','samples':samples+1,'states':sorted(death_states),'both_owners':True,'first_phase_frame_sha256':frames,'pixel_fidelity_not_an_oracle':True}
    e['status']='functional-pass-timing-fail' if '--sustained-timing' in sys.argv[3:] else 'scoped-pass'
    e['limitations']=['Original27000-cycle timing still fails; full timing acceptance and exact audio cadence fidelity remain open; audit registration must be checked separately. User overall natural behavior was accepted for3e732c4, without specified per-scenario coverage.','Boundary-forced life/stage/name scenarios exercise the real dispatcher and owners; they are not naturally earned level completion or enemy collision.']
    if '--natural-turn' not in sys.argv[3:]:e['limitations'].append('Natural directional turning not requested in this run.')
    if '--phase-handoffs' not in sys.argv[3:]:e['limitations'].append('Real stage/name/full-death handoffs not requested in this run.')
    if '--psg-trace' not in sys.argv[3:]:e['limitations'].append('Installed adaptive PSG trace not requested in this run.')
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
