"""Controlled real-call comparisons using the shared monitor harness.
This is not an installed adaptive game or natural adaptive acceptance.
"""
from pathlib import Path
import hashlib,json,sys,time
ref,fit,out=map(Path,sys.argv[1:4]);sys.path.insert(0,str(ref/'scripts'))
import verify_bug011_runtime as r
import verify_bug009_monitor_input as m
b=ref/'build';d=fit/'build/adaptive-fit/bindings';ms=r.symbols(b/'ladybug.map');es=r.symbols(b/'ladybug-enemy-runtime.map');ps=r.symbols(b/'ladybug-presentation-runtime.map');ts=r.symbols(d/'tick.map');rs=r.symbols(d/'resident.map')
tick=(d/'tick.bin').read_bytes();resident=(d/'resident.bin').read_bytes();audio=(d/'audio.bin').read_bytes();ads=r.symbols(b/'ladybug-audio-runtime.map');RET=0x18FC
e={'phase':'controlled real-call simulation and background bindings','deadline_seconds':45,'success_marker':'return to $18FC or original logic/render boundary with exact compared state/pixels','timeout_meaning':'component boundary absent; no complete adaptive timing inference','reference_rom_sha256':r.digest((b/'ladybug.rom').read_bytes()),'cases':[],'scope':'No driver installation, adaptive natural play, whole-image sequence, phase installer or elapsed audio acceptance.'}
p,c=r.launch_fast(m,Path('/mnt/e/projects/ladybug/docs/reference/xroar/src/xroar'),b/'ladybug.rom');deadline=time.monotonic()+45
def read(a,n=1):return r.read_bytes(c,a,n)
def write(a,v):c.call('write_memory',{'addr':a,'data':bytes(v).hex()})
def word(a,v):write(a,v.to_bytes(2,'big'))
def go(a):
    assert time.monotonic()<deadline,'45-second probe deadline'
    ids=m.setup(c,[a])
    try:
        c.call('run');h=c.call('wait_for_stop',{'timeout_ms':10000},timeout=12);assert h.get('pc')==a,h
    finally:m.clear(c,ids)
def call(a,value=0,marker=RET,elapsed=0):
    write(0x1EFC,[RET>>8,RET&255]);write(RET,[0x20,0xFE])
    c.call('write_registers',{'pc':a,'s':0x1EFC,'dp':0,'cc':0x50,'a':value,'x':elapsed})
    start=c.call('read_cycles')['event_ticks'];go(marker)
    delta=c.call('read_cycles')['event_ticks']-start;assert delta%8==0
    return delta//8,c.call('read_registers')
def snapshot():
    return {page:bytes.fromhex(c.call('read_memory',{'space':'physical','addr':page*8192,'length':8192})['data']) for page in [*range(0x2C,0x35),0x38]}
def restore(s):
    for page,data in s.items():c.call('write_memory',{'space':'physical','addr':page*8192,'data':data.hex()})
    write(0xFFA5,[0x34])
def pixels():return [r.read_owner(c,k) for k in (0,1)]
try:
    go(ps['attract_tick_ready']);assert read(0xC000,15872)==(b/'ladybug-runtime.rom').read_bytes()[:15872]
    assert read(0x800,4091)==(b/'ladybug-enemy-runtime.rom').read_bytes()
    assert read(0x1900,1273)==(b/'ladybug-presentation-runtime.bin').read_bytes()
    c.call('inject_key',{'key':5,'action':'press'});go(ps['credit_tick']);c.call('inject_key',{'key':5,'action':'release'})
    c.call('inject_key',{'key':1,'action':'press'});go(ms['main_game_tick']);c.call('inject_key',{'key':1,'action':'release'})
    while read(ms['INITIAL_ENTRY_STATE'])!=b'\0':go(ms['main_game_tick'])
    assert read(0xA5)==b'\0';write(0x05DE,tick);assert read(0x05DE,len(tick))==tick
    e['authored_loaded_identity']={'resident':15872,'enemy':4091,'presentation':1273,'tick_binding':len(tick)}
    base=snapshot();base_pixels=pixels()
    for first,count in [(1,1),(2,2),(1,4)]:
        results=[]
        for candidate in (False,True):
            restore(base);observed=[]
            for index in range(first,first+count):
                write(0x7F,bytes(16));write(0x94,[0,1]);write(0,[index&255]);write(0x6B,[index&1]);word(0xBD26,index)
                cycles,regs=call(ts['adaptive_tick_binding'] if candidate else ms['main_game_tick'],marker=RET if candidate else ms['main_render'])
                assert pixels()==base_pixels,'logic wrote framebuffer'
                observed.append({'cycles':cycles,'barrier':regs['a'] if candidate else None})
            results.append((read(0,256),read(0xA000,0x1C04),observed))
        assert results[0][:2]==results[1][:2],('production state differs',first,count)
        assert read(0xFFA5)==b'\x34'
        e['cases'].append({'name':'credited real logic comparison','first_logical_phase':first&1,'steps':count,'exact_dp_and_game_state':True,'zero_framebuffer_changes':True,'original_cycles':[v['cycles'] for v in results[0][2]],'binding_cycles':[v['cycles'] for v in results[1][2]]})
    # Forced barriers cover distinct transient/phase guards, never substitute
    # for natural visibility or the missing driver and reset ordering.
    for symbol,value in [('INITIAL_ENTRY_STATE',1),('PICKUP_TIMER',2),('STAGE_PENDING',1),('DEATH_STATE',4),('RENDER_GATE_ID',1)]:
        restore(base);write(ms[symbol],[value]);write(0x94,[0,1]);word(0xBD26,2)
        if symbol=='INITIAL_ENTRY_STATE':write(0x7F,[0x40])
        if symbol=='RENDER_GATE_ID':write(ms['GATE_ANIM_ID'],[1])
        _,regs=call(ts['adaptive_tick_binding']);assert regs['a']==1,(symbol,regs)
        e['cases'].append({'name':'forced publication barrier','state':symbol,'barrier':True})
    # Class dispatch compares one-record background composition, with the
    # same prepared actor-free owner. It is not a multi-record image replay.
    restore(base);old_loop=read(0xC0FF,145);write(0xC0FF,resident);assert read(0xC0FF,len(resident))==resident
    e['resident_binding_identity']=len(resident)
    for owner in (0,1):
        for name,packet,classes in [
            ('HUD/lives',bytes([6])+bytes(15),[('global',1)]),
            ('dot and timer box',bytes([0x30,0,5,6])+bytes(12),[('key',0),('key',1)]),
            ('letter and multiplier',bytes([0,6,0,0,1,2,3])+bytes(9),[('global',2),('key',2)]),
            ('primary and secondary gates',bytes([0,0,0,0,0,0,0,0,0,1,1,2,1,0,0,1]),[('key',3),('key',4)])]:
            restore(base);write(0x8F,[1-owner]);write(0x90,[owner]);write(0x91,[0]);write(0x7F,bytes(16))
            call(es['framebuffer_prepare_back']);call(es['actor_closure_restore']);clean=snapshot()
            pair=[]
            for candidate in (False,True):
                restore(clean);write(0x7F,packet);word(9,0x0204)
                if candidate:
                    for kind,k in classes:
                        if kind=='key':write(0x7F,packet)
                        call(rs['adaptive_global_binding'] if kind=='global' else rs['adaptive_key_binding'],k)
                else:call(es['frame_render_background'])
                pair.append(pixels())
            assert pair[0]==pair[1],('background pixel mismatch',owner,name)
            assert read(0xFFA5)==b'\x34'
            e['cases'].append({'name':'one-record real background comparison','worklist':name,'owner_secondary_metadata':owner,'both_surfaces_exact':True,'front_unchanged':pair[1][1-owner]==base_pixels[1-owner]})
            assert pair[1][1-owner]==base_pixels[1-owner]
    # Held-direction acquisition belongs to the foreground sample, not to
    # adaptive_tick_binding. Demo must not consume physical arrow input.
    restore(base);c.call('inject_key',{'key':0x2E,'action':'press'})
    call(rs['adaptive_input_binding']);assert read(5)==b'\1';credits=read(0xA8)
    word(0xBD26,1);call(ts['adaptive_tick_binding']);word(0xBD26,2);call(ts['adaptive_tick_binding'])
    assert read(0xA8)==credits
    write(0xA5,[4]);write(5,[0]);call(rs['adaptive_input_binding']);assert read(5)==b'\0'
    c.call('inject_key',{'key':0x2E,'action':'release'})
    e['cases'].append({'name':'held input sampled outside logic; demo excludes physical direction','credited_direction':1,'demo_direction_preserved':0,'credits_unchanged':True})
    # Route decisions and its timer move into the logical callback. The old
    # presentation calls must be removed before this can be installed.
    write(0xC0FF,old_loop)
    for first,count in [(1,2),(2,4)]:
        pair=[]
        for candidate in (False,True):
            restore(base);write(0x300,(b/'ladybug-demo-runtime.bin').read_bytes());write(0xA5,[4]);write(0x18,[0]);write(0xD8,[255,255,0,255]);word(0xB0,10)
            for index in range(first,first+count):
                write(0x7F,bytes(16));write(0x94,[0,1]);write(0,[index&255]);write(0x6B,[index&1]);word(0xBD26,index)
                if candidate:call(ts['adaptive_tick_binding'])
                else:
                    word(0xB0,int.from_bytes(read(0xB0,2),'big')+1);call(0x300);call(ms['main_game_tick'],marker=ms['main_render'])
            pair.append((read(0,256),read(0xA000,0x1C04),pixels()))
        assert pair[0]==pair[1],('demo logical binding mismatch',first,count)
        e['cases'].append({'name':'real demo route and logical timer comparison','first_logical_phase':first&1,'steps':count,'exact_state_and_pixels':True,'caller_migration_not_installed':True})
    restore(base);write(0xA5,[4]);word(0xB0,3599);before=read(9,4);_,regs=call(ts['adaptive_tick_binding']);assert regs['a']==1 and read(9,4)==before and read(0xB0,2)==bytes([14,16])
    e['cases'].append({'name':'demo logical timeout publication guard','barrier':True,'player_position_unchanged':True})
    # The new API is injected into the existing audio page's unused tail.
    # It primes new notes separately; it is NOT an elapsed >1 solution.
    restore(base);c.call('write_memory',{'space':'physical','addr':0x3D*8192+0x162B,'data':audio.hex()})
    def audread(a,n):return bytes.fromhex(c.call('read_memory',{'space':'physical','addr':0x3D*8192+a-0xA000,'length':n})['data'])
    # Production audio embeds mutable tables between functions. Prove every
    # immutable byte while explicitly excluding authored state declarations.
    mutable=[(ads['audio_poll_dots'],ads['audio_poll_valid']+1),(ads['audio_stop_pending'],ads['audio_mix_order']+4),(ads['audio_name_valid'],ads['audio_name_timer']+1),(ads['audio_slot0'],0xB62B)]
    live=audread(0xA000,5675);authored=(b/'ladybug-audio-runtime.bin').read_bytes()
    assert all(live[i]==authored[i] for i in range(5675) if not any(lo<=0xA000+i<hi for lo,hi in mutable)),'immutable audio identity'
    assert audread(0xB62B,len(audio))==audio
    e['audio_identity']={'immutable_bytes':5675-sum(hi-lo for lo,hi in mutable),'excluded_mutable_intervals':mutable,'api_bytes':len(audio)}
    # $0300 is a phase overlay, not a permanently installed initializer.
    # Enter the actual banked installer; it copies and tail-calls its engine
    # with PAR5 $3D, then returns through always-mapped RAM with PAR5 $34.
    write(0xFFA5,[0x3D]);call(ads['audio_install_page']);assert read(0xFFA5)==b'\x34'
    assert read(0x300,734)==(b/'ladybug-audio-runtime.bin').read_bytes()[:734],'installed copied engine identity'
    audio_base=snapshot();audio_state=audread(0xA000,8192)
    def reset_audio():
        restore(audio_base);c.call('write_memory',{'space':'physical','addr':0x3D*8192,'data':audio_state.hex()})
    def acall(action,elapsed=0):
        cycles,regs=call(ts['adaptive_audio_binding'],action,elapsed=elapsed);assert read(0xFFA5)==b'\x34';return cycles,regs
    acall(1);write(0x25,[max(0,read(0x25)[0]-1)]);acall(1);slots=audread(ads['audio_slot0'],112)
    assert 3 in slots[::28] and any(slots[i]==3 and slots[i+3]>0 for i in range(0,112,28)),slots.hex()
    acall(1);assert audread(ads['audio_slot0'],112)==slots,'resampling aged or duplicated cue'
    acall(0,0);assert audread(ads['audio_slot0'],112)==slots
    for elapsed in (2,4):
        before=audread(0xA000,8192);_,regs=acall(0,elapsed);assert regs['a']==1 and audread(0xA000,8192)==before
    e['cases'].append({'name':'audio event admission without aging and explicit elapsed gap refusal','new_pellet_note_primed':True,'repeated_sampling_exact':True,'unsupported_elapsed':[2,4],'unsupported_elapsed_mutation':False,'full_adaptive_audio_pass':False})
    before=audread(0xA000,8192);write(0xFFA5,[0x3D]);call(ads['audio_advance_all']);expected=audread(ads['audio_slot0'],112);write(0xFFA5,[0x34])
    c.call('write_memory',{'space':'physical','addr':0x3D*8192,'data':before.hex()});acall(0,1);assert audread(ads['audio_slot0'],112)==expected
    e['cases'].append({'name':'audio one-tick advance matches production slots','exact':True,'page34_return':True})
    for context in (1,2):
        reset_audio();write(0x2DC,[6]);write(0xA7,[context]);acall(1);slots=audread(ads['audio_slot0'],112)
        e['last_start_observation']={'context':context,'mode':read(0xA5).hex(),'last_mode':read(0x2DC).hex(),'slots':slots.hex(),'music_count':audread(ads['audio_music_count'],1).hex()}
        assert (slots[0]==6)==(context==1),e['last_start_observation']
        before=slots;acall(1);after=audread(ads['audio_slot0'],112)
        assert after==before,{'context':context,'before':before.hex(),'after':after.hex()}
        e['cases'].append({'name':'start music mode admission','context':context,'first_level_only':True,'repeat_does_not_age':True})
    reset_audio();write(0xA5,[4]);write(0x2DD,[2]);write(0x25,[1]);acall(1);assert audread(ads['audio_slot0'],112)[::28]==bytes([255]*4)
    acall(2);slots=audread(ads['audio_slot0'],112);assert slots[28]==12 and slots[31]>0 and read(0x2DD)==b'\1'
    e['cases'].append({'name':'demo silence with one admitted credit cue','demo_game_audio_silent':True,'credit_note_primed':True,'remaining_pending_credit':1,'audible_check_not_performed':True})
    e['result']='pass: controlled real-call comparisons and safe audio subset only; multi-refresh audio unresolved'
except BaseException as ex:
    e['result']='fail';e['failure']=repr(ex);raise
finally:
    out.write_text(json.dumps(e,indent=2)+'\n');c.close();m.stop(p)
