from pathlib import Path
import sys,time,json,hashlib
root=Path(sys.argv[1]);out=Path(sys.argv[2]);sys.path.insert(0,str(root/'scripts'))
import verify_bug011_runtime as r
import verify_bug009_monitor_input as m
b=root/'build';ms=r.symbols(b/'ladybug.map');ps=r.symbols(b/'ladybug-presentation-runtime.map');es=r.symbols(b/'ladybug-enemy-runtime.map');rom=b/'ladybug.rom';resident=(b/'ladybug-runtime.rom').read_bytes();enemy=(b/'ladybug-enemy-runtime.rom').read_bytes();presentation=(b/'ladybug-presentation-runtime.bin').read_bytes()
au=r.symbols(b/'ladybug-audio-runtime.map');audio=(b/'ladybug-audio-runtime.bin').read_bytes()
e={'rom_sha256':hashlib.sha256(rom.read_bytes()).hexdigest(),'phase':'controlled release-count sweep with real movement/render/audio','deadline_seconds':45,'success_marker':'16 worklists each at zero through four released enemies','timeout_meaning':'named sample boundary absent, not proof of target slowdown','controlled':'player parked at legal maze cell (2,2); existing enemy_release_impl called early; fixture leaves movement/render/collision/audio/clock execution intact; candidate code is identified by ROM hash','clock_units':'event_ticks / 8 at verified fast clock; monitor cpu_cycles incorrectly divides by16','samples':[]}
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
 if '--capture-paths' in sys.argv[3:]:
  for n in ['roam_update_background','rub_full','rub_horizontal','rub_vertical','rub_done','rub_column_done','rcrr_rotated']:
   a=es[n];assert read(a,8)==enemy[a-0x800:a-0x800+8],n;markers[a]=n
 if '--sparse-costs' in sys.argv[3:]:
  for n in ['sparse_blit_fb','sparse_blit_stage','sparse_decode_done']:
   a=es[n];assert read(a,8)==enemy[a-0x800:a-0x800+8],n;markers[a]=n
 audio_markers={}
 for n in ['audio_process_queue','audio_music_dispatch','audio_advance_all','audio_credit_service','audio_mix','audio_mix_write']:
  if n in au:markers[au[n]]=n;audio_markers[au[n]]=n
 write(ms['PLAYER_CELL_X'],[2,2]);write(ms['PLAYER_FB'],(0x2000+8*160+9*4).to_bytes(2,'big'));write(ms['PLAYER_DIR'],[255])
 for count in range(5):
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
     if markers[a] in ['sparse_blit_fb','sparse_blit_stage']:
      row.setdefault('decode_calls',[]).append({'path':markers[a],'entry':t})
     if markers[a]=='sparse_decode_done':
      call=row['decode_calls'][-1];assert 'cycles_to_epilogue' not in call;call['cycles_to_epilogue']=t-call['entry']
     if markers[a]=='roam_update_background':
      regs=c.call('read_registers');work=read(es['ENEMY_WORK'])[0];slot=4-work;mask=1<<slot;dirty=read(es['ENEMY_CAPTURE_DIRTY'])[0];valid=read(es['ENEMY_OLD_VALID'])[0];old=int.from_bytes(read(es['ENEMY_OLD_FB']+2*slot,2),'big');new=int.from_bytes(read(regs['x']+1,2),'big');delta=((new-old+32768)&65535)-32768
      reason='dirty' if dirty&mask else 'invalid' if not valid&mask else 'unchanged' if delta==0 else 'horizontal' if delta in ([-2,-1,1,2] if '--two-step' in sys.argv[3:] else [-1,1]) else 'vertical' if delta in ([-640,-320,320,640] if '--two-step' in sys.argv[3:] else [-320,320]) else 'unsupported-displacement'
      row.setdefault('capture_calls',[]).append({'slot':slot,'dirty_mask':dirty,'valid_mask':valid,'delta':delta,'selected_reason':reason})
     if markers[a] in ['rub_full','rub_horizontal','rub_vertical']:
      observed={'rub_full':'full','rub_horizontal':'horizontal','rub_vertical':'vertical'}[markers[a]];row['capture_calls'][-1]['executed_path']=observed
      why=row['capture_calls'][-1]['selected_reason'];expected=why if why in ['horizontal','vertical'] else 'full';assert observed==expected,(why,observed,'capture classifier disagreement')
     if a==ms['mainloop']:break
    else:raise AssertionError('no worklist end')
   finally:m.clear(c,ids)
   row['cycles']=t;e['samples'].append(row);assert row['active']==count and row['death']==0,('required live count missing',count,row['active'],row['death'])
 e['result']='captured'
except Exception as ex:e['result']='fail';e['failure']=repr(ex)
finally:c.close();m.stop(p);out.write_text(json.dumps(e,indent=2)+'\n')
print(json.dumps({k:v for k,v in e.items() if k!='samples'}))
for count in range(5):
 rows=[x for x in e['samples'] if x['requested_count']==count];print(count,[(x['active'],x['cycles'],x['death']) for x in rows])
if e['result']=='fail':raise SystemExit(1)
