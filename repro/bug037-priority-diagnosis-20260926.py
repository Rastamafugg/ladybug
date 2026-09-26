from pathlib import Path
import sys,json,hashlib
root=Path(sys.argv[1]).resolve();out=Path(sys.argv[2]);sys.path.insert(0,str(root/'scripts'))
import verify_bug011_runtime as r
import verify_bug009_monitor_input as m
b=root/'build';au=r.symbols(b/'ladybug-audio-runtime.map');artifact=(b/'ladybug-audio-runtime.bin').read_bytes();rom=b/'ladybug.rom'
e={'rom_sha256':hashlib.sha256(rom.read_bytes()).hexdigest(),'phase':'controlled effect-slot order crossover','deadline_seconds':45,'success_marker':'two audio_mix_write boundaries with immutable engine identity and swapped effect positions','timeout_meaning':'named mixer boundary not reached','samples':[]}
p,c=r.launch_fast(m,Path('/mnt/e/projects/ladybug/docs/reference/xroar/src/xroar'),rom)
def go(a):
 ids=m.setup(c,[a])
 try:
  c.call('run');hit=c.call('wait_for_stop',{'timeout_ms':45000},timeout=47);assert hit['pc']==a,hit
 finally:m.clear(c,ids)
def mem(a,n):return bytes.fromhex(c.call('read_memory',{'space':'physical','addr':0x3d*8192+a-0xa000,'length':n})['data'])
def store(a,v):c.call('write_memory',{'space':'physical','addr':0x3d*8192+a-0xa000,'data':bytes(v).hex()})
def slot(cue,periods):
 desc=artifact[au['gmc_cue_descriptors']-0xa000+8*cue:au['gmc_cue_descriptors']-0xa000+8*(cue+1)]
 v=bytearray(28);v[0]=cue;v[1]=desc[0]>>5;v[2]=desc[0];v[12:15]=bytes([0 if i<len(periods) else 15 for i in range(3)]);v[16]=15
 for i,period in enumerate(periods):v[6+2*i:8+2*i]=period.to_bytes(2,'big')
 return v
try:
 low=slot(4,[0x111,0x112,0x113]);high=slot(5,[0x222]);e['fixture']={'low_cue':4,'low_priority':low[1],'high_cue':5,'high_priority':high[1],'note':'controlled valid slot voices; not natural authored cue concurrency'};assert high[1]>low[1]
 for reverse in (False,True):
  go(au['audio_mix']);assert mem(0xa000,au['audio_engine_end']-0xa000)==artifact[:au['audio_engine_end']-0xa000]
  for i in range(4):store(au['audio_slot'+str(i)],[255]+[0]*27)
  store(au['audio_slot1'],high if reverse else low);store(au['audio_slot2'],low if reverse else high)
  go(au['audio_mix_write']);periods=list(mem(au['audio_mix_periods'],6));atten=list(mem(au['audio_mix_atten'],3));decoded=[(periods[i]<<8)|periods[i+1] for i in (0,2,4)]
  e['samples'].append({'higher_priority_slot':1 if reverse else 2,'tone_periods':decoded,'attenuations':atten,'high_voice_present':0x222 in decoded})
 if '--expect-fixed' in sys.argv:
  assert all(x['high_voice_present'] for x in e['samples']);e['result']='pass'
 else:
  assert not e['samples'][0]['high_voice_present'] and e['samples'][1]['high_voice_present'];e['result']='priority inversion reproduced'
except Exception as exc:e['result']='fail';e['failure']=repr(exc)
finally:c.close();m.stop(p);out.write_text(json.dumps(e,indent=2)+'\n')
print(json.dumps(e,indent=2))
if e['result']=='fail':raise SystemExit(1)
