"""Reuse the existing monitor client for BUG-034 input and audio evidence."""
import argparse, json, os, signal, socket, subprocess, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'scripts'))
import verify_bug011_runtime as p
from verify_feat006_complete_runtime import write_png
ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--mode',choices=['keyboard','joystick'],required=True)
ap.add_argument('--artifacts',type=Path,required=True,help='ROM, resident/module binaries and maps saved from the selected complete build')
ap.add_argument('--demo-only',action='store_true')
ap.add_argument('--output',type=Path,default=ROOT/'build/bug034')
ap.add_argument('--pulse-sink',default='bug034_audio')
args=ap.parse_args()
mode=args.mode; variant=args.artifacts.resolve(); out=args.output.resolve(); out.mkdir(parents=True,exist_ok=True)
demo_only=args.demo_only
ms=p.symbols(variant/'ladybug.map'); ps=p.symbols(variant/'ladybug-presentation-runtime.map')
m=p.load_monitor(); port=m.free_port()
proc=subprocess.Popen([str(ROOT/'docs/reference/xroar/src/xroar'),'-ui','null','-ao','pulse',
 '-machine','coco3','-ram','512','-cart-type','gmc','-cart-rom',str(variant/'ladybug.rom'),
 '-cart-autorun','-monitor',f'127.0.0.1:{port}','-monitor-halt-on-start']+(['-no-ratelimit'] if demo_only else []),
 env=dict(os.environ,PULSE_SINK=args.pulse_sink),stdout=open(out/(mode+'-monitor.log'),'w'),stderr=subprocess.STDOUT,start_new_session=True)
e={'mode':mode,'rom_sha256':p.digest((variant/'ladybug.rom').read_bytes()),'transport':'existing monitor emulator-input harness',
   'deadline_seconds':30,'rate_limited':not demo_only,'phases':[],'input':[]}
c=None
def go(label,addr):
    print(label+': deadline=30s',flush=True)
    ids=m.setup(c,[addr]); start=time.monotonic()
    try:
        c.call('run'); hit=c.call('wait_for_stop',{'timeout_ms':30000},timeout=32)
        assert hit['reason']=='breakpoint' and hit['pc']==addr,hit
        e['phases'].append({'label':label,'seconds':round(time.monotonic()-start,3),'pc':addr})
    finally: m.clear(c,ids)
def key(n,down): c.call('inject_key',{'key':n,'action':'press' if down else 'release'})
def identity():
    assert p.read_bytes(c,0xc000,8192)==(variant/'ladybug-runtime.rom').read_bytes()[:8192]
    pres=(variant/'ladybug-presentation-runtime.bin').read_bytes()
    assert p.read_bytes(c,0x1900,len(pres))==pres
    e['resident_presentation_identity']=True
def picture(label):
    frame=p.read_owner(c,p.read_byte(c,0x8f)); write_png(out/(mode+'-'+label+'.png'),frame)
    e[label+'_frame_sha256']=p.digest(frame)
try:
    deadline=time.monotonic()+5
    while time.monotonic()<deadline:
        try:
            c=m.MonitorClient(socket.create_connection(('127.0.0.1',port),timeout=.5))
            assert json.loads(c.file.readline())['method']=='hello'; break
        except OSError: time.sleep(.05)
    assert c
    go('cold mainloop',ms['mainloop']); identity()
    go('natural attract',ps['attract_tick_ready']); picture('attract')
    if demo_only:
        print('natural demo phase: deadline=30s',flush=True)
        c.call('run'); deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            state=bytes.fromhex(c.call('read_memory',{'space':'physical','addr':0x38*8192+0xa5,'length':1})['data'])
            if state==bytes([4]): break
            time.sleep(.05)
        e['demo_final_state']=state.hex()
        if state!=bytes([4]):
            e['demo_final_dp']=bytes.fromhex(c.call('read_memory',{'space':'physical','addr':0x38*8192+0x8f,'length':48})['data']).hex()
        assert state==bytes([4]),'demo not reached'
        c.call('pause'); c.call('wait_for_stop',{'timeout_ms':2000},timeout=3)
        payload=(ROOT/'build/ladybug-demo-runtime.bin').read_bytes()
        assert p.read_bytes(c,0x300,len(payload))==payload
        key(0x2e,True); dirs=[]
        ids=m.setup(c,[ms['read_joystick'],ms['main_demo_input_owned']])
        for _ in range(4):
            c.call('run'); hit=c.call('wait_for_stop',{'timeout_ms':30000},timeout=32)
            assert hit['pc']==ms['main_demo_input_owned'],hit
            assert p.read_byte(c,0xa5)==4
            dirs.append(p.read_byte(c,5))
        m.clear(c,ids); key(0x2e,False); picture('demo')
        e['demo_direction_samples']=dirs; e['demo_skips_physical_acquisition']=True
        e['status']='pass'; raise SystemExit(0)
    key(5,True); go('natural credit',ps['credit_tick']); key(5,False); picture('credit')
    key(1,True); go('natural gameplay',ms['main_game_tick']); key(1,False); identity()
    go('first completed gameplay render',ms['main_demo_input_owned'])
    go('first gameplay publication',ms['main_game_tick']); picture('gameplay')
    e['initial_game_state']=p.read_bytes(c,0,32).hex()
    # Same initial gameplay segment in both modes; no forced game state or hot probes.
    wave=out/(mode+'-gameplay.wav')
    cap=subprocess.Popen(['parec','--device='+args.pulse_sink+'.monitor','--file-format=wav','--rate=44100','--channels=1',str(wave)])
    c.call('run'); time.sleep(8); cap.send_signal(signal.SIGINT); cap.wait(timeout=3)
    c.call('pause'); c.call('wait_for_stop',{'timeout_ms':2000},timeout=3)
    e['audio']={'file':wave.name,'seconds':8,'scenario':'first natural gameplay interval; neutral input; no execution breakpoints'}
    if mode=='keyboard':
        cases=[([],255),([0x2b],0),([],255),([0x2e],1),([0x2c],2),([0x2d],3),([],255),
               ([0x2d,0x2e],255),([0x2b,0x2c],255),([0x2b,0x2e],1),([0x2b,0x2d,0x2e],0),([],255)]
    else: cases=[([],255)]
    held=[]
    for keys,expected in cases:
        for k in held: key(k,False)
        for k in keys: key(k,True)
        held=keys
        go('direction '+str(keys),ms['rj_done'])
        state=p.read_bytes(c,0,25); row={'keys':keys,'expected':expected,'actual':state[5],
            'x':state[1],'y':state[4],'credits':p.read_byte(c,0xa8),'mode':p.read_byte(c,0xa5),
            'pia_cra':p.read_byte(c,0xff01),'pia_crb':p.read_byte(c,0xff03),'audio_gate':p.read_byte(c,0xff23)}
        e['input'].append(row); assert row['actual']==expected,row
        assert row['credits']==0 and row['mode']==0,row
        if mode=='keyboard': assert (row['pia_cra']&0x3f,row['pia_crb']&0x3f,row['audio_gate']&0x3f)==(0x34,0x3c,0x3c),row
    # Explicit quiet fixture: retain the production audio service and selector
    # behavior; clear mutable voice slots and stop neutral player movement.
    au=p.symbols(ROOT/'build/ladybug-audio-runtime.map')
    audio=(ROOT/'build/ladybug-audio-runtime.bin').read_bytes()
    engine=au['audio_engine_end']-au['audio_engine_start']
    assert p.read_bytes(c,0x300,engine)==audio[:engine]
    saved=p.read_byte(c,0xffa5); p.write_byte(c,0xffa5,0x3d)
    assert p.read_bytes(c,0xa000,engine)==audio[:engine]
    for n in range(4):
        addr=au['audio_slot'+str(n)]
        p.write_byte(c,addr,255)
        for offset in (12,13,14,16): p.write_byte(c,addr+offset,15)
    p.write_byte(c,au['audio_poll_valid'],0)
    p.write_byte(c,0xffa5,saved)
    for addr,value in [(0xec,0),(0xed,0),(0xee,0),(0x18,1),(0x4a,255)]: p.write_byte(c,addr,value)
    wave=out/(mode+'-quiet.wav')
    c.call('run'); time.sleep(.2)
    cap=subprocess.Popen(['parec','--device='+args.pulse_sink+'.monitor','--file-format=wav','--rate=44100','--channels=1',str(wave)])
    time.sleep(2); cap.send_signal(signal.SIGINT); cap.wait(timeout=3)
    c.call('pause'); c.call('wait_for_stop',{'timeout_ms':2000},timeout=3)
    saved=p.read_byte(c,0xffa5); p.write_byte(c,0xffa5,0x3d)
    e['quiet_slots']=[p.read_bytes(c,au['audio_slot'+str(n)],17).hex() for n in range(4)]
    e['quiet_output_shadow']=p.read_bytes(c,au['audio_mix_shadow'],11).hex()
    p.write_byte(c,0xffa5,saved)
    assert all(bytes.fromhex(s)[0]==255 for s in e['quiet_slots'])
    e['quiet_fixture']='2 seconds: inactive voice slots, neutral manual player, perimeter timer 255, empty event queue, refreshed poll snapshot; production service and polling unchanged'
    # Stable 500 Hz PSG tone separates input modulation from changing game cues.
    saved=p.read_byte(c,0xffa5); p.write_byte(c,0xffa5,0x3d)
    addr=au['audio_slot3']
    for offset,value in [(0,0),(1,255),(2,1),(3,255),(6,250),(7,0),(12,4)]: p.write_byte(c,addr+offset,value)
    p.write_byte(c,au['audio_poll_valid'],0); p.write_byte(c,0xffa5,saved)
    for addr,value in [(0xec,0),(0xed,0),(0xee,0),(0x4a,255)]: p.write_byte(c,addr,value)
    wave=out/(mode+'-tone.wav'); c.call('run'); time.sleep(.2)
    cap=subprocess.Popen(['parec','--device='+args.pulse_sink+'.monitor','--file-format=wav','--rate=44100','--channels=1',str(wave)])
    time.sleep(2); cap.send_signal(signal.SIGINT); cap.wait(timeout=3)
    c.call('pause'); c.call('wait_for_stop',{'timeout_ms':2000},timeout=3)
    saved=p.read_byte(c,0xffa5); p.write_byte(c,0xffa5,0x3d)
    e['tone_slot']=p.read_bytes(c,au['audio_slot3'],17).hex()
    e['tone_output_shadow']=p.read_bytes(c,au['audio_mix_shadow'],11).hex(); p.write_byte(c,0xffa5,saved)
    assert bytes.fromhex(e['tone_slot'])[3]>0
    e['tone_fixture']='2 seconds: slot3 exclusive priority255, one 500 Hz tone, attenuation4, wait255; blocks gameplay cue pre-emption, same production input and audio service'
    if mode=='keyboard':
        # Force only the qualifying terminal condition after the natural gameplay path.
        hs=p.symbols(variant/'ladybug-highscore-runtime.map')
        payload=(variant/'ladybug-highscore-runtime.bin').read_bytes()
        saved=p.read_byte(c,0xffa5); p.write_byte(c,0xffa5,0x23)
        assert p.read_bytes(c,ps['PRESENTATION_HIGHSCORE_RUNTIME_ADDRESS'],len(payload))==payload
        p.write_byte(c,0xffa5,saved)
        c.call('write_memory',{'addr':0x1d,'data':'999999'})
        p.write_byte(c,0x4d,4)
        e['forced_rare_condition']='BCD score 999999 and terminal death; no owner/input/PC injection'
        print('qualifying name phase: deadline=30s',flush=True)
        c.call('run'); deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            state=bytes.fromhex(c.call('read_memory',{'space':'physical','addr':0x38*8192+0xa5,'length':2})['data'])
            if state==bytes([8,5]): break
            time.sleep(.05)
        assert state==bytes([8,5]),state.hex()
        c.call('pause'); c.call('wait_for_stop',{'timeout_ms':2000},timeout=3)
        assert p.read_bytes(c,0x300,len(payload))==payload
        go('qualifying name input',hs['name_joy_ready'])
        e['name_authored_staged_live_identity']=True; picture('name')
        positions=[]
        for code,direction in [(0x2e,1),(0x2c,2),(0x2d,3),(0x2b,0)]:
            key(code,True)
            for _ in range(4):
                go('name direction '+str(direction),hs['name_joy_ready'])
                assert p.read_byte(c,5)==direction
                positions.append(p.read_word(c,0xb))
            key(code,False); go('name release',hs['name_joy_ready'])
            assert p.read_byte(c,5)==255
            pos=p.read_word(c,0xb); go('name stays stopped',hs['name_joy_ready'])
            assert p.read_word(c,0xb)==pos
        e['name_positions']=positions; assert len(set(positions))>1,'no name movement'
        e['name_arrows_and_release']=True
    e['status']='pass'
except Exception as ex:
    e['status']='incomplete'; e['error']=repr(ex); print('ERROR',repr(ex),flush=True)
finally:
    (out/(mode+('-demo' if demo_only else '')+'-monitor-summary.json')).write_text(json.dumps(e,indent=2)+'\n')
    if c: c.close()
    m.stop(proc)
print(json.dumps(e),flush=True)
if e['status']!='pass': sys.exit(1)
