from pathlib import Path
import sys,json,time,hashlib
root=Path(sys.argv[1]).resolve();out=Path(sys.argv[2]);sys.path.insert(0,str(root/'scripts'))
import verify_bug011_runtime as r
import verify_bug009_monitor_input as m
b=root/'build';ps=r.symbols(b/'ladybug-presentation-runtime.map');ms=r.symbols(b/'ladybug.map');au=r.symbols(b/'ladybug-audio-runtime.map');rom=b/'ladybug.rom';audio=(b/'ladybug-audio-runtime.bin').read_bytes();module=(b/'ladybug-presentation-runtime.bin').read_bytes()
e={'rom_sha256':hashlib.sha256(rom.read_bytes()).hexdigest(),'phase_deadline_seconds':45,'success_marker':'Silent natural demo; coin cue; first game start cue; no later-level start cue','timeout_meaning':'Named phase/admission/completion absent','phases':[]}
p,c=r.launch_fast(m,Path('/mnt/e/projects/ladybug/docs/reference/xroar/src/xroar'),rom)
def phys(a,n):return bytes.fromhex(c.call('read_memory',{'space':'physical','addr':a,'length':n})['data'])
def low(a):return phys(0x38*8192+a,1)[0]
def slot(i):return phys(0x3d*8192+au[f'audio_slot{i}']-0xa000,1)[0]
def go(a):
 ids=m.setup(c,[a])
 try:c.call('run');assert c.call('wait_for_stop',{'timeout_ms':10000},timeout=12)['pc']==a
 finally:m.clear(c,ids)
def wait(label,pred):
 end=time.monotonic()+45
 while time.monotonic()<end:
  go(ps['pft_ready'])
  if pred():e['phases'].append({'name':label,'mode':low(0xa5),'slots':[slot(i) for i in range(4)]});return
 raise TimeoutError(label)
def key(k,on):c.call('inject_key',{'key':k,'action':'press' if on else 'release'})
try:
 go(ps['presentation_flow_tick']);assert r.read_bytes(c,0x1900,len(module))==module;assert phys(0x3d*8192,len(audio))==audio
 wait('natural demo',lambda:low(0xa5)==4)
 for i in range(64):
  go(ps['pft_ready']);assert low(0xa5)==4;assert all(slot(j)==255 for j in range(4));assert phys(0x3d*8192+au['audio_mix_atten']-0xa000,3)==bytes([15]*3)
 e['silent_demo_samples']=64
 key(5,True);wait('coin interrupts demo with cue',lambda:low(0xa8)==1 and slot(1)==12);key(5,False)
 wait('credit cue ends on high scores',lambda:low(0xa5)==5 and slot(1)==255 and low(0x91)==0)
 key(1,True);wait('first level',lambda:low(0xa5)==6);key(1,False)
 wait('first game start music',lambda:low(0xa5)==0 and slot(0)==6)
 wait('first music finished and entrant ready',lambda:low(0xa5)==0 and slot(0)==255 and low(0xa0)==0)
 c.call('write_memory',{'space':'physical','addr':0x38*8192+ms['STAGE_PENDING'],'data':'01'})
 wait('forced next-level boundary',lambda:low(0xa5)==6 and low(0xa7)==2)
 wait('later gameplay',lambda:low(0xa5)==0 and low(0xa7)==0)
 for i in range(32):
  go(ps['pft_ready']);assert low(0xa5)==0 and slot(0)!=6
 e['later_level_no_start_samples']=32;e['result']='pass'
except Exception as exc:e['result']='fail';e['failure']=repr(exc)
finally:c.close();m.stop(p);out.write_text(json.dumps(e,indent=2)+'\n')
print(json.dumps(e,indent=2))
if e['result']!='pass':raise SystemExit(1)
