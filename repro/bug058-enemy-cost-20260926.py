from pathlib import Path
import sys,time,json,hashlib
root=Path(sys.argv[1]);out=Path(sys.argv[2]);sys.path.insert(0,str(root/'scripts'))
import verify_bug011_runtime as r
import verify_bug009_monitor_input as m
b=root/'build';ms=r.symbols(b/'ladybug.map');ps=r.symbols(b/'ladybug-presentation-runtime.map');es=r.symbols(b/'ladybug-enemy-runtime.map');rom=b/'ladybug.rom';resident=(b/'ladybug-runtime.rom').read_bytes();enemy=(b/'ladybug-enemy-runtime.rom').read_bytes();presentation=(b/'ladybug-presentation-runtime.bin').read_bytes()
au=r.symbols(b/'ladybug-audio-runtime.map');audio=(b/'ladybug-audio-runtime.bin').read_bytes()
e={'rom_sha256':hashlib.sha256(rom.read_bytes()).hexdigest(),'phase':'controlled release-count sweep with real movement/render/audio','deadline_seconds':45,'success_marker':'16 worklists each at zero through three released enemies','timeout_meaning':'named sample boundary absent, not proof of target slowdown','controlled':'existing enemy_release_impl called early; no movement, renderer, collision, audio or clock code changed','clock_units':'event_ticks / 8 at verified fast clock; monitor cpu_cycles incorrectly divides by16','samples':[]}
p,c=r.launch_fast(m,Path('/mnt/e/projects/ladybug/docs/reference/xroar/src/xroar'),rom)
def read(a,n=1):return r.read_bytes(c,a,n)
def write(a,v):c.call('write_memory',{'addr':a,'data':bytes(v).hex()})
def go(a):
 ids=m.setup(c,[a])
 try:
  c.call('run');h=c.call('wait_for_stop',{'timeout_ms':10000},timeout=12);assert h.get('pc')==a,h
 finally:m.clear(c,ids)
def key(k,on):c.call('inject_key',{'key':k,'action':'press' if on else 'release'})
def wait(pred):
 end=time.monotonic()+45
 while time.monotonic()<end:
  go(ps['pft_ready'])
  if pred():return
 raise TimeoutError('start gameplay')
def release():
 regs=c.call('read_registers');stack=read(0x1e00,512);stub=read(0x1800,2)
 write(0x1800,[0x20,0xfe]);write(0x1efc,[0x18,0]);addr=es['enemy_release_impl'];assert read(addr,20)==enemy[addr-0x800:addr-0x800+20]
 ids=m.setup(c,[0x1800])
 try:
  c.call('write_registers',{'pc':addr,'s':0x1efc,'dp':0,'cc':0x50});c.call('run');h=c.call('wait_for_stop',{'timeout_ms':10000},timeout=12);assert h.get('pc')==0x1800,h
 finally:
  m.clear(c,ids);write(0x1800,stub);write(0x1e00,stack);c.call('write_registers',{k:regs[k] for k in ('a','b','cc','dp','x','y','u','s','pc')})
try:
 go(ps['pft_ready']);assert read(0x1900,len(presentation))==presentation
 key(5,True);wait(lambda:read(0xa5)[0]==5);key(5,False);key(1,True);wait(lambda:read(0xa5)[0]==6);key(1,False)
 wait(lambda:read(0xa5)[0]==0 and read(ms['INITIAL_ENTRY_STATE'])[0]==0)
 for label in ['main_game_tick_normal','enemy_tick','main_after_player','main_render','main_entry_audio','mainloop']:
  a=ms[label];assert read(a,12)==resident[a-0xc000:a-0xc000+12],label
 assert read(0x800,96)==enemy[:96]
 e['identity']='live presentation/resident phase prologues, enemy entry table and release destination match artifacts'
 markers={ms[n]:n for n in ['main_game_tick_normal','enemy_tick','main_after_player','main_render','main_entry_audio','mainloop']}
 for n in ['framebuffer_prepare_back','actor_closure_restore','framebuffer_queue_damage','framebuffer_project_damage','roam_mark_underlay','frame_render_background','actor_closure_draw','framebuffer_finish_back','acd_save_loop','acd_draw_loop','acd_death','acd_normal_player']:
  a=es[n];assert read(a,8)==enemy[a-0x800:a-0x800+8],n;markers[a]=n
 audio_markers={}
 for n in ['audio_process_queue','audio_music_dispatch','audio_advance_all','audio_credit_service','audio_mix','audio_mix_write']:
  if n in au:markers[au[n]]=n;audio_markers[au[n]]=n
 for count in range(4):
  deadline=time.monotonic()+45
  if count:release()
  for settle in range(36 if count else 2):go(ps['presentation_flow_tick'])
  for i in range(16):
   assert time.monotonic()<deadline,'count phase deadline'
   go(ps['presentation_flow_tick']);start=c.call('read_cycles')['event_ticks'];state=list(read(0x54,12));row={'requested_count':count,'index':i,'active':read(0x58)[0],'death':read(ms['DEATH_STATE'])[0],'front':read(0x8f)[0],'state':state,'event_start':start,'vbord':int.from_bytes(read(ms['FRAMES'],2),'big'),'missed_commit':int.from_bytes(read(ms['FB_MISSED_COMMIT'],2),'big'),'marks':[]};ids=m.setup(c,list(markers))
   try:
    for k in range(96):
     c.call('run');h=c.call('wait_for_stop',{'timeout_ms':10000},timeout=12);a=h.get('pc');assert a in markers,h
     if a in audio_markers:assert read(a,8)==audio[a-0xa000:a-0xa000+8],audio_markers[a]
     t=(c.call('read_cycles')['event_ticks']-start)//8;row['marks'].append([markers[a],t])
     if a==ms['mainloop']:break
    else:raise AssertionError('no worklist end')
   finally:m.clear(c,ids)
   row['cycles']=t;e['samples'].append(row)
 e['result']='captured'
except Exception as ex:e['result']='fail';e['failure']=repr(ex)
finally:c.close();m.stop(p);out.write_text(json.dumps(e,indent=2)+'\n')
print(json.dumps({k:v for k,v in e.items() if k!='samples'}))
for count in range(4):
 rows=[x for x in e['samples'] if x['requested_count']==count];print(count,[(x['active'],x['cycles'],x['death']) for x in rows])
if e['result']=='fail':raise SystemExit(1)
