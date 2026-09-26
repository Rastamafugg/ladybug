from pathlib import Path
import json,hashlib,time,sys
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/'scripts'))
import verify_bug011_runtime as r
import verify_bug009_monitor_input as m
import build_screen as screen
b=root/'build';rom=b/'ladybug.rom';ps=r.symbols(b/'ladybug-presentation-runtime.map');ms=r.symbols(b/'ladybug.map');au=r.symbols(b/'ladybug-audio-runtime.map');module=(b/'ladybug-presentation-runtime.bin').read_bytes();audio=(b/'ladybug-audio-runtime.bin').read_bytes();resident=(b/'ladybug-runtime.rom').read_bytes()
record={'rom_sha256':hashlib.sha256(rom.read_bytes()).hexdigest(),'phase_deadline_seconds':45,'timeout_meaning':'named state/publication not observed; not target speed evidence','phases':[]}
p,c=r.launch_fast(m,Path('/mnt/e/projects/ladybug/docs/reference/xroar/src/xroar'),rom)
def phys(a,n):return bytes.fromhex(c.call('read_memory',{'space':'physical','addr':a,'length':n})['data'])
def low(a,n=1):return phys(0x38*8192+a,n)
def go(address):
 ids=m.setup(c,[address])
 try:
  h=c.run_to_breakpoint(10);assert h['pc']==address
 finally:m.clear(c,ids)
def key(k,action):c.call('inject_key',{'key':k,'action':action})
def state():return {'mode':low(0xa5)[0],'screen':low(0xa6)[0],'credits':low(0xa8)[0],'pending':low(0x2dd)[0],'overflow':low(0xef)[0],'slots':[phys(0x3d*8192+au[f'audio_slot{i}']-0xa000,1)[0] for i in range(4)]}
def until(label,pred,address=None):
 deadline=time.monotonic()+45
 while time.monotonic()<deadline:
  go(address or ps['pft_ready']);s=state()
  if pred(s):record['phases'].append({'name':label,**s});return
 raise TimeoutError(label)
def checkfront(count):
 go(ps['credit_tick']);go(ps['credit_tick']);owner=low(0x8f)[0];frame=phys((0x30 if owner==0 else 0x2c)*8192,30720)
 chars=screen.load_chars(root/'assets/arcade/chars.json')
 def glyph(code,pen):
  if code==36:return bytes(32)
  return bytes(((pen if row[x] else 0)<<4)|(pen if row[x+1] else 0) for row in screen.rotate_ccw(chars[code]) for x in range(0,8,2))
 def tile(x,y):return b''.join(frame[y*1280+x*4+i*160:y*1280+x*4+i*160+4] for i in range(8))
 assert tile(33,9)==glyph(count,6)
 for i,code in enumerate((1,36,24,27,36,2,36,25,21,10,34,14,27,36,11,30,29,29,24,23)):assert tile(10+i,23)==glyph(code,8 if code in (1,2) else 5)
 record['phases'].append({'name':'published count and two-player prompt pixels','count':count,'owner':owner,'frame_sha256':hashlib.sha256(frame).hexdigest()})
def slot(i):return phys(0x3d*8192+au[f'audio_slot{i}']-0xa000,17)
def credit_mixed():
 x=slot(1)
 if x[0]!=12 or x[12]==15:return False
 assert slot(0)[0]==255
 assert phys(0x3d*8192+au['audio_mix_periods']-0xa000,2)==x[6:8]
 assert phys(0x3d*8192+au['audio_mix_atten']-0xa000,1)==x[12:13]
 period=int.from_bytes(x[6:8],'little');expected=bytes((0x80|(period&15),(period>>4)&63,0x90|x[12]))
 assert phys(0x3d*8192+au['audio_mix_shadow']-0xa000,3)==expected
 return True
def drain_credit(label,require_other=False):
 deadline=time.monotonic()+45;heard=0;other=0;active=False
 while time.monotonic()<deadline:
  x=slot(1)
  if x[0]==12:
   active=True
   if credit_mixed():heard+=1;other+=int(slot(2)[0]!=255 or slot(3)[0]!=255)
  if active and x[0]!=12:break
  go(ps['pft_ready'])
 assert active and slot(1)[0]!=12 and heard>0
 if require_other:assert other>0
 record['phases'].append({'name':label,'mixed_credit_samples':heard,'mixed_with_other_effect_samples':other})
try:
 go(ps['presentation_flow_tick']);assert r.read_bytes(c,0x1900,len(module))==module;assert phys(0x3d*8192,len(audio))==audio
 call=ms['main_entry_audio'];assert r.read_bytes(c,call,3)==resident[call-0xc000:call-0xc000+3]
 go(call);assert low(0xa5)[0]==4;off=au['audio_service_gateway_bytes']-0xa000;assert low(0x2de,18)==audio[off:off+18]
 key(5,'press');until('credit during demo music stays pending',lambda s:s['credits']==1 and s['pending']==1 and s['slots'][0]==6);key(5,'release')
 held=0;deadline=time.monotonic()+45
 while slot(0)[0]!=255:
  assert time.monotonic()<deadline;assert low(0x2dd)[0]==1 and slot(1)[0]!=12;held+=1;go(ps['pft_ready'])
 record['phases'].append({'name':'music owns mixer without consuming pending credit','samples':held})
 drain_credit('deferred credit mixed to completion')
 # Force three nonexclusive effects, then accept a second real credit edge.
 c.call('write_memory',{'space':'physical','addr':0x38*8192+0xec,'data':'00000300'})
 c.call('write_memory',{'space':'physical','addr':0x38*8192+0xf1,'data':'0000010002000000'})
 key(6,'press');until('second accepted credit',lambda s:s['credits']==2);key(6,'release')
 drain_credit('credit has a voice before competing nonexclusive effects',True)
 # Force newly arriving music while a third naturally admitted credit is playing.
 key(5,'press');until('third credit active',lambda s:s['credits']==3 and s['slots'][1]==12);key(5,'release')
 until('third credit reaches audible data',lambda s:slot(1)[0]==12 and slot(1)[12]<15)
 before=slot(1)[3:6]
 c.call('write_memory',{'space':'physical','addr':0x38*8192+0xec,'data':'00000100'})
 c.call('write_memory',{'space':'physical','addr':0x38*8192+0xf1,'data':'0600'})
 go(ps['pft_ready']);assert slot(0)[0]==6
 paused=0;deadline=time.monotonic()+45
 while slot(0)[0]!=255:
  assert time.monotonic()<deadline;assert slot(1)[0]==12 and slot(1)[3:6]==before;paused+=1;go(ps['pft_ready'])
 record['phases'].append({'name':'active credit wait and stream preserved under later music','paused_samples':paused})
 drain_credit('interrupted credit resumes mixing and completes')
 assert low(0xef)[0]==0 and low(0x2dd)[0]==0;assert low(0x2de,18)==audio[off:off+18]
 record['identity']='source/staged/live presentation, caller, audio and gateway exact';record['result']='pass'
except Exception as e:record['result']='fail';record['failure']=f'{type(e).__name__}: {e}'
finally:c.close();m.stop(p);(b/'bug043-credit-mix-fit.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record,indent=2))
if record['result']!='pass':raise SystemExit(1)
