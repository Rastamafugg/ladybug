"""Cold adaptive driver/real worklist and elapsed audio probe; shared harness."""
from pathlib import Path
import json,sys,time,hashlib
w,out=map(Path,sys.argv[1:3]);sys.path.insert(0,'/mnt/e/projects/ladybug/scripts')
import verify_bug011_runtime as r
import verify_bug009_monitor_input as m
b=Path('/mnt/e/projects/ladybug/build');ms=r.symbols(b/'ladybug.map');es=r.symbols(b/'ladybug-enemy-runtime.map');ps=r.symbols(b/'ladybug-presentation-runtime.map');ads=r.symbols(b/'ladybug-audio-runtime.map');act=r.symbols(b/'ladybug-adaptive-active.map')
rom=b/'ladybug.rom';RET=0x18FC
profile_enabled=False
publish_enabled=False
resident=(b/'ladybug-runtime.rom').read_bytes();parser_start=0xC000+resident.index(bytes([0xBD,0x19,0]),ms['mainloop']-0xC000,ms['ad_dispatch_active']-0xC000);started=False
e={'phase':'cold installed adaptive game and real foreground worklist','deadline_seconds':45,'success_marker':'natural publication returns and exact helper/phase code; then elapsed audio returns to $18FC','timeout_meaning':'requested boundary absent, not proof of slowdown','rom_sha256':r.digest(rom.read_bytes()),'cases':[],'status':'incomplete','profile_spec':{'focus':'controlled three-enemy foreground worklists after natural credited Enter entry','phase_deadline_seconds':45,'audio_backend':'null; CPU cost only, no audible-output claim','profile_method':'existing stack-qualified entry/return observer; per-call inclusive and exclusive spans are fast CPU cycles from event_ticks/8; exclusive subtracts only instrumented children; instrumented sparse-cache replay helper is per entity and records replay mode'}}
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
        c.call('run');h=c.call('wait_for_stop',{'timeout_ms':5000},timeout=6);assert h.get('pc')==a,h
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
            c.call('run');hit=c.call('wait_for_stop',{'timeout_ms':5000},timeout=6)
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
            (es,['framebuffer_prepare_back','actor_closure_restore','roam_copy_bg_to_fb','roam_update_background','rub_full','rub_horizontal','rub_vertical','rub_done','actor_closure_draw','sparse_blit_fb','frame_render_background','colour_prepare_nest','framebuffer_finish_back','compose_enemy_zone','compose_enemy_animation','bnc_copy','draw_enemy_stage','draw_vegetable_stage','copy_native_row']),
            (ms,['sync_entity_cache_colour','render_entity_colour','replay_entity_overlay_common','draw_perimeter_box','draw_entities','erase_entity_footprints','repair_settled_entity_gates']),
            (ads,['audio_adaptive_api','aas_elapsed','aas_admit','aas_output','aas_prime','aas_dirty','audio_process_queue','audio_music_dispatch','audio_poll_gameplay','audio_credit_service','audio_mix','audio_mix_write'])]
    if stop_pc is None:stop_pc=ms['mainloop']
    entries={sy[n]:n for sy,names in groups for n in names}
    ids={};frames=[];totals={};hits=0
    def bp(a):
        if a not in ids:ids[a]=m.setup(c,[a])[0]
    for a in [stop_pc,*entries]:bp(a)
    try:
        while True:
            assert time.monotonic()<deadline,'45-second profiled phase deadline'
            c.call('run');h=c.call('wait_for_stop',{'timeout_ms':5000},timeout=6);pc=h.get('pc');assert pc in ids,h
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
                if name in {'audio_adaptive_api','aas_elapsed','aas_admit','aas_output','aas_prime','aas_dirty','audio_process_queue','audio_music_dispatch','audio_poll_gameplay','audio_credit_service','audio_mix','audio_mix_write'}:
                    assert read(0xFFA5)[0]&63==0x3D,('profiled audio mapping',name,read(0xFFA5)[0])
                    expected=audio[pc-0xA000:pc-0xA000+8]
                    assert len(expected)==8 and phys(0x3D,pc,8)==expected and read(pc,8)==expected,('profiled audio live identity',name,pc)
                if frames and frames[-1]['name']==name and frames[-1]['stack']==regs['s']:continue
                ret=int.from_bytes(read(regs['s'],2),'big');bp(ret)
                # Entire immutable resident/enemy/helper and installed active
                # blobs were compared before interpreting these entry labels.
                if name=='adaptive_audio_binding':name+='_'+str(regs['a'])
                if name=='frame_render_background':
                    totals.setdefault('background_requests',[]).append({'flags':read(0x7F,16).hex(),'cell':read(9,2).hex()})
                if name=='replay_entity_overlay_common':
                    totals.setdefault('cache_replay_entries',[]).append({'mode':read(ms['OBJ_ACCENT'])[0],'entity_work':read(ms['ENTITY_WORK'])[0],'entity_count':read(ms['ENTITY_COUNT'])[0]})
                frames.append({'name':name,'return':ret,'stack':regs['s'],'start':now,'children':0})
    finally:m.clear(c,list(ids.values()))


from build_screen import compile_player_sprites,compile_enemy_sprites,expand_sprite,PLAYER_PEN_MAP
from build_sparse_sprites import GAMEPLAY_ENEMY_PEN_MAPS
player_templates=[expand_sprite(x,PLAYER_PEN_MAP) for x in compile_player_sprites(w/'assets/arcade/sprites.json')]
enemy_templates=[expand_sprite(x,GAMEPLAY_ENEMY_PEN_MAPS[0]) for x in compile_enemy_sprites(w/'assets/arcade/sprites.json')[:16]]
def opaque_match(frame,pointer,templates):
    offset=pointer-0x2000
    if offset<0 or offset+15*160+8>len(frame):return []
    matches=[]
    for index,sprite in enumerate(templates):
        ok=True
        for y in range(16):
            for x in range(8):
                actual=frame[offset+y*160+x];expected=sprite[y*8+x]
                if expected&240 and actual&240!=expected&240:ok=False;break
                if expected&15 and actual&15!=expected&15:ok=False;break
            if not ok:break
        if ok:matches.append(index)
    return matches
def overlaps(a,b):
    ay,ax=divmod(a-0x2000,160);by,bx=divmod(b-0x2000,160)
    return ax<bx+8 and bx<ax+8 and ay<by+16 and by<ay+16
def published():
    owner=read(0x8F)[0];ledger=phys(0x34,0xA900+owner*256,256)
    frame=r.read_owner(c,owner);actors=[]
    if ledger[2]:actors.append({'name':'player','pointer':int.from_bytes(ledger[4:6],'big')})
    for i in range(4):
        rec=ledger[8+i*8:16+i*8]
        if rec[0]:actors.append({'name':'enemy'+str(i),'pointer':int.from_bytes(rec[1:3],'big'),'roaming':bool(rec[6])})
    for actor in actors:
        actor['overlap']=[x['name'] for x in actors if x is not actor and overlaps(x['pointer'],actor['pointer'])]
        actor['templates']=opaque_match(frame,actor['pointer'],player_templates if actor['name']=='player' else enemy_templates)
        actor['opaque_pixels_match']=bool(actor['templates'])
    return {'owner_secondary':owner,'commit':int.from_bytes(read(0x92,2),'big'),
            'raw':int.from_bytes(read(2,2),'big'),'independent_event_ticks':c.call('read_cycles')['event_ticks'],
            'frame_sha256':r.digest(frame),'actors':actors}

def measure():
    global started
    full=started and c.call('read_registers')['pc']!=ms['ad_dispatch_work']
    go(parser_start if full else ms['ad_dispatch_work']);started=True
    before={'raw':int.from_bytes(read(2,2),'big'),'logical':int.from_bytes(read(0xBD26,2),'big'),'debt':int.from_bytes(read(0xBD28,2),'big'),'mode':read(0xA5)[0],'owner':read(0x90)[0],'enemies':read(ms['ENEMY_ACTIVE'])[0],'rate':read(0xBD34)[0],'cycles_scope':'input-parser-through-return' if full else 'active-driver-through-return'}
    start=c.call('read_cycles')['event_ticks']
    before['independent_event_ticks_before']=start
    before['player_fb_before']=int.from_bytes(read(ms['PLAYER_FB'],2),'big')
    before['enemy_records_before']=read(es['ENEMY_TABLE'],32).hex()
    if publish_enabled:before['published_front']=published()
    detail,hits=profiled_return() if profile_enabled else (None,None)
    if not profile_enabled:go(ms['mainloop'])
    ticks=c.call('read_cycles')['event_ticks']-start
    before.update(cycles=ticks//8,logical_after=int.from_bytes(read(0xBD26,2),'big'),debt_after=int.from_bytes(read(0xBD28,2),'big'),counts=list(read(0xBD38,2)),fault=read(0xBD3A)[0],pending=read(0x91)[0],late=phys(0x3D,ads['audio_adaptive_late'],1)[0]);assert before['fault']==0,before
    before['independent_event_ticks_after']=c.call('read_cycles')['event_ticks']
    before['player_fb_after']=int.from_bytes(read(ms['PLAYER_FB'],2),'big')
    before['enemy_records_after']=read(es['ENEMY_TABLE'],32).hex()
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
    audio_profile_names=['audio_adaptive_api','aas_elapsed','aas_admit','aas_output','aas_prime','aas_dirty','audio_process_queue','audio_music_dispatch','audio_poll_gameplay','audio_credit_service','audio_mix','audio_mix_write']
    profiled_audio=[]
    for n in audio_profile_names:
        a=ads[n];expected=audio[a-0xA000:a-0xA000+8]
        assert len(expected)==8 and phys(0x3D,a,8)==expected,('staged audio identity',n)
        profiled_audio.append({'name':n,'address':a,'bytes':expected.hex()})
    e['profiled_audio_entries']=profiled_audio
    e['identity']={'resident':0x3E00,'enemy':len(enemy),'helper':len(helper),'staged_active':len(stage),'banked_audio':len(audio),'profiled_audio_entries':len(profiled_audio)}
    if '--two-step-cap-fit' in sys.argv[3:]:
        early_fitted=(Path(__file__).parent/'bug058-catchup-banked-fit.bin').read_bytes()
        c.call('write_memory',{'space':'physical','addr':0x34*8192+0xBD44-0xA000,'data':early_fitted.hex()})
        assert phys(0x34,0xBD44,len(early_fitted))==early_fitted,'pre-demo fitted helper delivery'
        e['early_cap_overlay']={'bytes':len(early_fitted),'sha256':r.digest(early_fitted),'phase':'after exact cold-ROM installation proof, before natural demo/credited gameplay'}
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
    settled=0
    while read(0xD4)!=bytes([0]) or read(0x91)!=bytes([0]):
        go(ps['credit_tick']);settled+=1;assert settled<240,'settled highscore marker absent'
    e['highscore_settle_ticks']=settled
    ph=(b/'ladybug-perimeter-reset-helper.bin').read_bytes();assert read(0x6B2,len(ph))==ph,'settled helper differs';e['settled_helper_exact']=True
    c.call('inject_key',{'key':0x30,'action':'press'});go(ms['ad_dispatch_work']);c.call('inject_key',{'key':0x30,'action':'release'})
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
        profile_enabled='--profile-three' in sys.argv[3:] and count==3
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
            assert len(fitted)<=698 and phys(0x34,0xBD44,len(fitted))==fitted,'fitted helper identity after natural routes'
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
            publish_enabled=True
            for index in range(58 if name=='pickup' else 12):
                profile_enabled=index<2 or (name=='gate rotation' and index in (7,8))
                row=measure();row['steps']=(row['logical_after']-row['logical'])&65535
                row['marker']=marker();rows.append(row)
                changed=(row['marker']['bonus_left']<before if name=='pickup' else row['marker']['gate_state']!=before)
                if changed and event_at is None:event_at=index
                assert row['mode']==0 and row['enemies']==4 and row['fault']==0,'event fixture left active four-enemy phase'
            assert event_at is not None,(name,'real event marker absent')
            profile_enabled=False
            publish_enabled=False
            e['pickup_gate_cadence'].append({'name':name,'setup':pickup if name=='pickup' else {'gate_id':0,'pivot':gate['pivot'],'from':[gx-1,gy+1],'direction':0},'event_worklist':event_at,'worklists':rows,'deadline_seconds':45})
        reset_event()
    e['status']='scoped-pass'
    e['limitations']=['Accepted guard ROM f18bb3e8; optional byte-proven cap helper research overlay from before natural demo/credited entry.','Controlled legal pickup/gate preconditions and controlled releases after natural credited entry; no natural earning claim.','Null audio backend; no visible audio crossover.','No production changes or whole-game maxima.']
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
