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
try:
 go(ps['presentation_flow_tick']);assert r.read_bytes(c,0x1900,len(module))==module;assert phys(0x3d*8192,len(audio))==audio
 call=ms['main_entry_audio'];assert r.read_bytes(c,call,3)==resident[call-0xc000:call-0xc000+3]
 go(call);assert low(0xa5)[0]==4;off=au['audio_service_gateway_bytes']-0xa000;assert low(0x2de,18)==audio[off:off+18];record['identity']='source/staged/live presentation, caller, audio, gateway exact'
 key(5,'press');until('credit cue admitted during exclusive level cue',lambda s:s['credits']==1 and 12 in s['slots'] and 6 in s['slots']);key(5,'release')
 samples=[];deadline=time.monotonic()+45
 while time.monotonic()<deadline:
  st=state();st['best_mix_slot']=low(0xfe)[0];st['slot0_policy']=phys(0x3d*8192+au['audio_slot0']-0xa000+2,1)[0];samples.append(st)
  if 12 not in st['slots']:break
  go(ps['pft_ready'])
 assert samples[-1]['slots'][0]==6 and 12 not in samples[-1]['slots']
 active=[s for s in samples if 12 in s['slots']]
 assert active and all(s['best_mix_slot']==0 and s['slot0_policy']&1 for s in active)
 record['credit_active_samples']=len(active);record['all_credit_samples_select_exclusive_slot0']=True;record['first']=samples[0];record['last']=samples[-1];record['result']='reproduced: credit cue completes internally while excluded from mix'
except Exception as e:record['result']='fail';record['failure']=f'{type(e).__name__}: {e}'
finally:c.close();m.stop(p);(b/'bug043-credit-mix-gap.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record,indent=2))
if 'failure' in record:raise SystemExit(1)
