from pathlib import Path
import sys,json,hashlib,time
root=Path(sys.argv[1]).resolve();out=Path(sys.argv[2]);sys.path.insert(0,str(root/'scripts'))
import verify_bug011_runtime as r
import verify_bug009_monitor_input as m
b=root/'build';au=r.symbols(b/'ladybug-audio-runtime.map');ps=r.symbols(b/'ladybug-presentation-runtime.map');artifact=(b/'ladybug-audio-runtime.bin').read_bytes();rom=b/'ladybug.rom'
e={'rom_sha256':hashlib.sha256(rom.read_bytes()).hexdigest(),'phase':'controlled music admission, priority, duplicate and retained-boundary fixture','phase_deadline_seconds':45,'clock_units':'event_ticks / 8 at verified fast clock','success_marker':'independent music queue, nonpreemptible active cue, priority ordering and guarded completion','timeout_meaning':'named return/stream completion absent; not proof of slow runtime'}
p,c=r.launch_fast(m,Path('/mnt/e/projects/ladybug/docs/reference/xroar/src/xroar'),rom)
def go(a):
 ids=m.setup(c,[a])
 try:c.call('run');assert c.call('wait_for_stop',{'timeout_ms':10000},timeout=12)['pc']==a
 finally:m.clear(c,ids)
def read(a,n=1):return bytes.fromhex(c.call('read_memory',{'addr':a,'length':n})['data'])
def write(a,v):c.call('write_memory',{'addr':a,'data':bytes(v).hex()})
def bankread(name,n=1):
 a=0x3d*8192+au[name]-0xa000
 return bytes.fromhex(c.call('read_memory',{'space':'physical','addr':a,'length':n})['data'])
def bankwrite(name,v):c.call('write_memory',{'space':'physical','addr':0x3d*8192+au[name]-0xa000,'data':bytes(v).hex()})
def call(name,a=0,guard=False):
 regs=c.call('read_registers');stack=read(0x1e00,512);stub=read(0x1800,2);par=read(0xffa5)
 write(0x1800,[0x20,0xfe]);write(0x1efc,[0x18,0]);write(0xffa5,[0x34 if guard else 0x3d])
 addr=0x2c0 if guard else au[name]
 if not guard:assert read(addr,3)==artifact[addr-0xa000:addr-0xa000+3]
 ids=m.setup(c,[0x1800]);start=time.monotonic()
 try:
  c.call('write_registers',{'pc':addr,'a':a,'b':0,'s':0x1efc,'dp':0,'cc':0x50});cycle_start=(c.call('read_cycles')['event_ticks']//8);c.call('run');hit=c.call('wait_for_stop',{'timeout_ms':10000},timeout=12);assert hit['pc']==0x1800
  result=c.call('read_registers');result['_cycles']=(c.call('read_cycles')['event_ticks']//8)-cycle_start;mapping=read(0xffa5)[0]
 finally:
  m.clear(c,ids);write(0xffa5,par);write(0x1800,stub);write(0x1e00,stack);c.call('write_registers',{k:regs[k] for k in ('a','b','cc','dp','x','y','u','s','pc')})
 if guard:assert mapping==0x34
 return result
try:
 go(ps['pft_ready']);assert bankread('audio_engine_start',au['audio_engine_end']-0xa000)==artifact[:au['audio_engine_end']-0xa000]
 assert read(0x2c0,20)==artifact[au['audio_guard_bytes']-0xa000:au['audio_guard_end']-0xa000]
 call('audio_enqueue_impl',16)
 for _ in range(4):call('audio_enqueue_impl',3)
 assert read(0xee)==bytes([4])
 for cue in (6,9,13,10,8,7,11,14,9,13):call('audio_enqueue_impl',cue)
 assert bankread('audio_music_count')==bytes([8]);e['full_effect_fifo_music_count']=8
 order=[]
 for _ in range(8):
  call('audio_music_dispatch');order.append(bankread('audio_slot0')[0]);bankwrite('audio_slot0',[255])
 assert order==[13,10,11,14,6,9,8,7],order;e['music_order']=order
 call('audio_enqueue_impl',16);call('audio_enqueue_impl',6);call('audio_music_dispatch');call('audio_advance_all');before=bankread('audio_slot0',17)
 for cue in (6,9,13,9):call('audio_enqueue_impl',cue)
 call('audio_music_dispatch');assert bankread('audio_slot0',17)==before;assert bankread('audio_music_count')==bytes([2]);e['active_music_unchanged']=True
 call('audio_enqueue_impl',16);assert bankread('audio_slot0',17)==before;assert bankread('audio_music_count')==bytes([2]);e['system_stop_preserves_music']=True
 bankwrite('audio_slot0',[255]);bankwrite('audio_music_count',[0]);call('audio_music_dispatch');assert bankread('audio_stop_pending')==bytes([0]);assert read(0xee)==bytes([0]);e['deferred_stop_completes']=True
 call('audio_enqueue_impl',9);call('audio_music_dispatch')
 write(0xa5,[0]);write(0x26,[1]);write(0x4d,[0]);bankwrite('audio_poll_valid',[0]);start=time.monotonic();results=[];guard_cycles=[]
 while time.monotonic()-start<45:
  result=call('',guard=True);results.append(result['a']);guard_cycles.append(result['_cycles'])
  if result['a']==0:break
 else:raise TimeoutError('guarded stream completion')
 assert len(results)>2 and all(x==1 for x in results[:-1]);assert bankread('audio_slot0')==bytes([255]);e['guard_service_calls']=len(results)-1;e['guard_releases_once_empty']=True;e['maximum_guard_call_cycles']=max(guard_cycles);assert max(guard_cycles)<=27000
 call('audio_enqueue_impl',9);call('audio_music_dispatch');call('audio_advance_all');assert bankread('audio_slot0')==bytes([9])
 c.call('reset',{'kind':'soft'});go(ps['pft_ready']);assert bankread('audio_music_count')==bytes([0]);assert all(bankread('audio_slot'+str(i))==bytes([255]) for i in range(4));assert bankread('audio_mix_atten',3)==bytes([15,15,15]);e['reset_during_pending_music_silences']=True
 e['result']='pass'
except Exception as exc:e['result']='fail';e['failure']=repr(exc)
finally:c.close();m.stop(p);out.write_text(json.dumps(e,indent=2)+'\n')
print(json.dumps(e,indent=2))
if e['result']!='pass':raise SystemExit(1)
