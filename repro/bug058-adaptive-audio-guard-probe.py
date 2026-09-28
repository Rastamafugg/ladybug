"""Exact semantic-event comparison for BUG-058 idle audio admission guard."""
from pathlib import Path
import json,sys,time
w,out=map(Path,sys.argv[1:3]);sys.path.insert(0,str(w/'scripts'))
import verify_bug011_runtime as r
import verify_bug009_monitor_input as m
b=w/'build';ad=r.symbols(b/'ladybug-audio-runtime.map');old=r.symbols(b/'adaptive-prepoll-audio.map');ps=r.symbols(b/'ladybug-presentation-runtime.map');ms=r.symbols(b/'ladybug.map')
rom=b/'ladybug.rom';new_audio=(b/'ladybug-audio-runtime.bin').read_bytes();old_audio=(b/'adaptive-prepoll-audio.bin').read_bytes();api=ad['audio_adaptive_api'];old_end=old['audio_adaptive_last'];assert api==old['audio_adaptive_api']
e={'phase':'controlled exact semantic-audio poll comparison','deadline_seconds':45,'success_marker':'eleven new/old installed API-1 calls return at $18FC with identical semantic state','timeout_meaning':'API return absent, not evidence of game slowness','rom_sha256':r.digest(rom.read_bytes()),'old_rom_sha256':r.digest((b/'adaptive-prepoll.rom').read_bytes()),'cases':[],'status':'incomplete'}
p,c=r.launch_fast(m,Path('/mnt/e/projects/ladybug/docs/reference/xroar/src/xroar'),rom);deadline=time.monotonic()+45

def read(a,n=1):return r.read_bytes(c,a,n)
def write(a,v):c.call('write_memory',{'addr':a,'data':bytes(v).hex()})
def phys(a,n):return bytes.fromhex(c.call('read_memory',{'space':'physical','addr':0x3D*8192+a-0xA000,'length':n})['data'])
def pw(a,v):c.call('write_memory',{'space':'physical','addr':0x3D*8192+a-0xA000,'data':bytes(v).hex()})
def go(a):
 assert time.monotonic()<deadline,'45-second phase deadline'
 ids=m.setup(c,[a])
 try:
  c.call('run');h=c.call('wait_for_stop',{'timeout_ms':10000},timeout=12);assert h.get('pc')==a,h
 finally:m.clear(c,ids)
def call():
 write(0x1EFC,[0x18,0xFC]);write(0x18FC,[0x20,0xFE]);c.call('write_registers',{'pc':0x39B,'s':0x1EFC,'dp':0,'cc':0x50,'a':1})
 start=c.call('read_cycles')['event_ticks'];go(0x18FC);ticks=c.call('read_cycles')['event_ticks']-start;assert ticks%8==0
 assert read(0xFFA5)[0]&63==0x34
 return ticks//8
fields=[('dots',0x25,'audio_poll_dots',20,19),('bonus',0x33,'audio_poll_bonus',20,19),('box',0x4B,'audio_poll_box',0,1),('gate',0x19,'audio_poll_gate',0,1),('death',0x4D,'audio_poll_death',0,1),('vegetable',0x5A,'audio_poll_veg',1,2),('release',0x59,'audio_poll_release',0,1),('special',0x3C,'audio_poll_special',1,0),('extra',0x3D,'audio_poll_extra',1,0),('stage',0x26,'audio_poll_stage',0,1)]
try:
 go(ps['attract_tick_ready']);assert read(0xC000,16)==(b/'ladybug-runtime.rom').read_bytes()[:16]
 go(ms['ad_dispatch_work']);stage=(b/'ladybug-adaptive-active.bin').read_bytes();assert read(0x38F,len(stage))==stage
 assert phys(api,old_end-api)==new_audio[api-0xA000:old_end-0xA000]
 base=phys(0xA000,8192);dp=read(0,256)
 for name,change in [('idle',None)]+[(x[0],x) for x in fields]:
  results=[]
  for candidate in (True,False):
   pw(0xA000,base);write(0,dp);write(0xA5,[0]);write(0x2DC,[0]);write(0xEE,[0]);pw(ad['audio_music_count'],[0]);pw(ad['audio_stop_pending'],[0]);pw(ad['audio_poll_valid'],[1])
   for i in range(4):pw(ad[f'audio_slot{i}'],[255])
   for _,addr,poll,baseline,_ in fields:write(addr,[baseline]);pw(ad[poll],[baseline])
   if change:
    write(change[1],[change[4]])
    if name=='stage':write(0x25,[0]);write(0x33,[0]);pw(ad['audio_poll_dots'],[0]);pw(ad['audio_poll_bonus'],[0])
   if not candidate:pw(api,old_audio[api-0xA000:old_end-0xA000])
   cycles=call()
   state={'slots':phys(ad['audio_slot0'],112).hex(),'poll':phys(ad['audio_poll_dots'],11).hex(),'music':phys(ad['audio_music_count'],1).hex(),'queue':read(0xEC,13).hex(),'stop':phys(ad['audio_stop_pending'],1).hex()}
   results.append((cycles,state))
  assert results[0][1]==results[1][1],(name,results)
  e['cases'].append({'event':name,'new_cycles':results[0][0],'old_cycles':results[1][0],'semantic_state_exact':True})
 e['status']='scoped-pass'
except Exception as exc:e['failure']=repr(exc);raise
finally:
 out.write_text(json.dumps(e,indent=2)+'\n');r.stop(p)
