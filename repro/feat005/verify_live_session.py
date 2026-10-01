"""FEAT-005 rare live stage, input priority, timing and session integration.

All runtime phases have a 40-second marker deadline; timeout fails coverage.
The existing monitor is reused. No emulator/server extension is required.
"""
import json,sys,time,socket
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import verify_bug011_runtime as r
import verify_shared_text as text

build=ROOT/'build';monitor=r.load_monitor()
main=r.symbols(build/'ladybug.map');pres=r.symbols(build/'ladybug-presentation-runtime.map')
report={'status':'FAIL','rom_sha256':r.digest((build/'ladybug.rom').read_bytes()),'checks':[]}
process,client=r.launch_fast(monitor,ROOT/'docs/reference/xroar/src/xroar',build/'ladybug.rom')
read=lambda a:r.read_byte(client,a)
write=lambda a,v:r.write_byte(client,a,v)
ids=monitor.setup(client,[0x1900])

def tick():
    assert client.run_to_breakpoint(timeout=10)['pc']==0x1900

def wait(name,predicate):
    deadline=time.monotonic()+40
    while not predicate():
        assert time.monotonic()<deadline,('phase timeout',name)
        tick()

def keys(scans,action):
    for scan in scans:client.call('inject_key',{'key':scan,'action':action})

def check(name,value=True):
    report['checks'].append({'name':name,'result':value});print(name,flush=True)

def call(name,level):
    regs=client.call('read_registers');write(0x24,level)
    r.write_word(client,regs['s']-2,0x700)
    client.call('write_registers',{'pc':main[name],'s':regs['s']-2,'dp':0,'cc':0x50})
    deadline=time.monotonic()+40
    while True:
        assert time.monotonic()<deadline,('isolated call timeout',name)
        client.call('step_instruction',{'n':1})
        if client.call('wait_for_stop',{'timeout_ms':2000})['pc']==0x700:break
    client.call('write_registers',{key:regs[key] for key in ('a','b','x','y','u','s','pc','cc','dp')})

try:
    tick()
    assert r.read_bytes(client,0xC000,8192)==(build/'ladybug-runtime.rom').read_bytes()[:8192]
    code=(build/'ladybug-presentation-runtime.bin').read_bytes()
    assert r.read_bytes(client,0x1900,len(code))==code
    wait('published cold attract',lambda:read(0xA5)==2 and read(0xD4)==0 and read(0x91)==0)
    keys([5],'press');tick();keys([5],'release')
    wait('published credited high scores',lambda:read(0xA5)==5 and read(0xD4)==0 and read(0x91)==0)
    write(0xEA,12);write(0xEB,99)
    keys([1,0x30],'press')
    for _ in range(4):tick()
    keys([1,0x30],'release')
    assert read(0xA6)==2 and read(0xA8)==0
    wait('configured live first entrant completed',lambda:read(0xA5)==0 and read(0xA0)==0)
    assert (read(0x23),read(0x24),read(0x49),read(0x58))==(11,99,12,0)
    check('natural stage 99: start overrides Enter, credit consumed once, eleven reserves and twelve entities')
    font=text.values((build/'ladybug_shared_text.inc').read_text(),'font','colour_lut')
    colour=json.loads((ROOT/'assets/arcade/text-colours.json').read_text())['fields']['part']
    frame=r.read_owner(client,read(0x8F))
    expected=bytes((colour if font[9*8+y]&(128>>(j*2)) else 0)*16+(colour if font[9*8+y]&(64>>(j*2)) else 0) for y in range(8) for j in range(4))
    for col in (37,38):assert r.frame_tile(frame,0x2000+11*1280+col*4)==expected
    check('published two-digit level HUD is 99')
    keys([0x30,0x32],'press')
    for _ in range(8):tick()
    keys([0x30,0x32],'release');tick()
    assert read(0xA5)==0 and read(0xA6)==2
    check('menu Enter/Break cannot interrupt active gameplay')
    monitor.clear(client,ids)
    assert r.read_bytes(client,main['mainloop'],1)==b'\x13'
    ids=monitor.setup(client,[main['mainloop'],main['mainloop']+1])
    hit=client.run_to_breakpoint(timeout=10)
    assert hit['pc']==main['mainloop']
    samples=[]
    for _ in range(16):
        assert client.run_to_breakpoint(timeout=10)['pc']==main['mainloop']+1
        start=client.call('read_cycles')['event_ticks']
        flags=[read(a) for a in (0x7F,0x80,0x87)]
        owner=read(0x90)
        assert client.run_to_breakpoint(timeout=10)['pc']==main['mainloop']
        elapsed=(client.call('read_cycles')['event_ticks']-start)//8
        samples.append({'cycles':elapsed,'render_intents':flags,'back_owner':owner})
    monitor.clear(client,ids)
    maximum=max(sample['cycles'] for sample in samples)
    report['active_gameplay_timing']={'phase':'steady live stage 99, no released enemies','samples':samples,'maximum':maximum,'target':27000,'target_met':maximum<=27000,'units':'1.79 MHz CPU cycles; event ticks / 8; SYNC wait excluded; IRQ included'}
    check('sixteen natural foreground timing samples',maximum)
    # Force only the rare last-life boundary, then let the normal dispatcher
    # complete game-over, name timeout and returned attract in natural order.
    write(0x23,0);write(0x4D,3);write(0x3A,0)
    ids=monitor.setup(client,[pres['start_screen']])
    transitions=[];deadline=time.monotonic()+40
    while True:
        assert time.monotonic()<deadline,'terminal session timeout'
        assert client.run_to_breakpoint(timeout=10)['pc']==pres['start_screen']
        destination=client.call('read_registers')['a'];transitions.append(destination)
        report['terminal_transitions']=list(transitions)
        assert (read(0xEA),read(0xEB))==(12,99)
        if destination==3:break
        assert len(transitions)<5,transitions
    assert transitions==[4,3],transitions
    check('last-life boundary naturally completes game-over/name/high-scores with settings retained',transitions)
    monitor.clear(client,ids);ids=monitor.setup(client,[0x1900])
    wait('returned high scores published',lambda:read(0xA5)==5 and read(0xD4)==0 and read(0x91)==0)
    keys([5],'press');tick();keys([5],'release')
    wait('second credited high scores',lambda:read(0xA5)==5 and read(0xD4)==0 and read(0x91)==0)
    keys([1],'press');tick();keys([1],'release')
    wait('second configured live entrant completed',lambda:read(0xA5)==0 and read(0xA0)==0)
    client.call('write_memory',{'addr':main['SCORE_BCD'],'data':'100000'})
    write(0x23,0);write(0x4D,3);write(0x3A,0)
    monitor.clear(client,ids);ids=monitor.setup(client,[pres['start_screen']])
    qualified=[];deadline=time.monotonic()+40
    while True:
        assert time.monotonic()<deadline,'qualified session timeout'
        assert client.run_to_breakpoint(timeout=10)['pc']==pres['start_screen']
        destination=client.call('read_registers')['a'];qualified.append(destination)
        report['qualified_terminal_transitions']=list(qualified)
        assert (read(0xEA),read(0xEB))==(12,99)
        if destination==3:break
        assert len(qualified)<5,qualified
    assert qualified==[4,5,3],qualified
    check('qualified score naturally completes name timeout and preserves session settings',qualified)
    # Isolated CPU calls follow all natural sequence checks. The authored
    # vegetable table has eighteen entries; 18 and 99 must render identically.
    call('draw_vegetable_hud',18);eighteen=r.read_bytes(client,0x2000,30720)
    call('draw_vegetable_hud',99);ninety_nine=r.read_bytes(client,0x2000,30720)
    assert eighteen==ninety_nine
    check('vegetable HUD clamps level 99 to the existing level-18 entry')
    report['status']='pass' if maximum<=27000 else 'functional pass; active gameplay timing target missed'
except Exception as error:
    report['error']=str(error)
    # A timed-out buffered monitor stream cannot be reused. A fresh connection
    # pauses this owned emulator and retains the exact last unproven boundary.
    try:
        diagnostic=monitor.MonitorClient(socket.create_connection(client.sock.getpeername(),timeout=3))
        diagnostic.file.readline()
        diagnostic.call('pause',timeout=3)
        regs=diagnostic.call('read_registers',timeout=3)
        par=r.read_byte(diagnostic,0xFFA5)&63;pc=regs['pc']
        live=r.read_bytes(diagnostic,pc,16)
        authored=None
        if 0xC000<=pc<0xDFEA:authored=(build/'ladybug-runtime.rom').read_bytes()[pc-0xC000:pc-0xC000+16]
        elif 0x1900<=pc<0x1DF0:authored=(build/'ladybug-presentation-runtime.bin').read_bytes()[pc-0x1900:pc-0x1900+16]
        elif par==0x3D and 0xA000<=pc<0xB5A0:authored=(build/'ladybug-audio-runtime.bin').read_bytes()[pc-0xA000:pc-0xA000+16]
        report['failure_boundary']={'registers':regs,'par5':par,'live_pc_bytes':live.hex(),'authored_pc_bytes':authored.hex() if authored else None,'byte_identity':live==authored if authored else 'unmapped in retained code domains','direct_page':r.read_bytes(diagnostic,0,256).hex(),'audio_state_02dc':r.read_bytes(diagnostic,0x2DC,4).hex()}
        diagnostic.close()
    except Exception as capture_error:report['failure_capture_error']=str(capture_error)
    raise
finally:
    (ROOT/'repro/feat005-live-session-20260930.json').write_text(json.dumps(report,indent=2)+'\n')
    client.close();monitor.stop(process)
if report['status']!='pass':sys.exit(2)
