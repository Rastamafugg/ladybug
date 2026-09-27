from pathlib import Path
import sys,time,json,hashlib
root=Path(sys.argv[1]);out=Path(sys.argv[2]);fit=Path(sys.argv[3]);sys.path.insert(0,str(root/'scripts'))
import verify_bug011_runtime as r
import verify_bug009_monitor_input as m
reference_prefix=sys.argv[4] if len(sys.argv)>4 else None
candidate_prefix=sys.argv[5] if len(sys.argv)>5 else 'bug058-enemy-check'
b=root/'build';ms=r.symbols(b/'ladybug.map');ps=r.symbols(b/'ladybug-presentation-runtime.map');es=r.symbols(b/((reference_prefix+'.map') if reference_prefix else 'ladybug-enemy-runtime.map'));rom=b/'ladybug.rom';resident=(b/'ladybug-runtime.rom').read_bytes();enemy=(b/((reference_prefix+'.bin') if reference_prefix else 'ladybug-enemy-runtime.rom')).read_bytes();boot_enemy=(b/'ladybug-enemy-runtime.rom').read_bytes();presentation=(b/'ladybug-presentation-runtime.bin').read_bytes()
au=r.symbols(b/'ladybug-audio-runtime.map');audio=(b/'ladybug-audio-runtime.bin').read_bytes()
if '--reference-boot' in sys.argv[6:]:
 assert reference_prefix,'reference prefix required'
 rom=b/(reference_prefix+'.rom');boot_enemy=enemy
e={'rom_sha256':hashlib.sha256(rom.read_bytes()).hexdigest(),'phase':'controlled release-count sweep with real movement/render/audio','deadline_seconds':45,'success_marker':'16 worklists each at zero through three released enemies','timeout_meaning':'named sample boundary absent, not proof of target slowdown','controlled':'early enemy releases; current ROM boot with parked player and asserted live counts; reference/candidate enemy modules temporarily overlaid for controlled render comparisons; original state restored between calls','clock_units':'event_ticks / 8 at verified fast clock; monitor cpu_cycles incorrectly divides by16','samples':[]}
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
perimeter_only='--perimeter-only' in sys.argv[6:]
oldresident=(b/'perimeter-before-ladybug-runtime.rom').read_bytes() if perimeter_only else None
if perimeter_only:
 off=ms['draw_perimeter_box']-0xc000
 assert resident[:off]==oldresident[:off] and resident[off+88:]==oldresident[off+88:]
candidate=(fit/'build'/(candidate_prefix+'.bin')).read_bytes();cs=r.symbols(fit/'build'/(candidate_prefix+'.map'))
e.update(phase='controlled same-state render crossover',success_marker='identical framebuffer and equivalent bank-$34 state under the explicitly selected oracle',candidate_enemy_sha256=hashlib.sha256(candidate).hexdigest());e['perimeter_only']=perimeter_only;e['reference_resident_sha256']=hashlib.sha256(oldresident).hexdigest() if perimeter_only else None;e['cases']=[];e['state_oracle']='decoded audited rings; all other state exact' if '--logical-rings' in sys.argv[6:] else 'all state exact'
def physical(a,n):return bytes.fromhex(c.call('read_memory',{'space':'physical','addr':a,'length':n})['data'])
def putphysical(a,v):c.call('write_memory',{'space':'physical','addr':a,'data':bytes(v).hex()})
def snapshot():return [physical(pg*8192,8192) for pg in range(64)]
def restore(pages,regs,pars):
 for pg,data in enumerate(pages):putphysical(pg*8192,data)
 write(0xffa0,pars);c.call('write_registers',{k:regs[k] for k in ('a','b','cc','dp','x','y','u','s','pc')})
def logical_rings(data,owner):
 # Normalize only the eight audited 128-byte rings and their phase bytes.
 result=bytearray(data)
 for meta,base in [(es['FB_META_A'],es['ENEMY_BG_BASE']),(es['FB_META_B'],es['ENEMY_BG_B'])]:
  phases=meta-0xa000+es['FBM_ENEMY_RINGS']
  for slot in range(4):
   phase=data[phases+slot];assert not phase&8,'reserved ring bit set'
   off=base-0xa000+128*slot;buf=data[off:off+128];rp=phase>>4;cp=phase&7
   result[off:off+128]=bytes(buf[((row+rp)%16)*8+(col+cp)%8] for row in range(16) for col in range(8));result[phases+slot]=0
 current=es['ENEMY_BG_RING']-0xa000;meta=(es['FB_META_A'] if owner==0 else es['FB_META_B'])-0xa000+es['FBM_ENEMY_RINGS']
 assert data[current:current+4]==data[meta:meta+4],'live/published phase mismatch'
 result[current:current+4]=bytes(4)
 return bytes(result)
def invoke(code,entry,resident_code=None):
 if resident_code is not None:
  write(ms['draw_perimeter_box'],resident_code[off:off+88]);assert read(ms['draw_perimeter_box'],88)==resident_code[off:off+88]
 write(0x800,code);assert read(0x800,len(code))==code
 write(0x1800,[0x20,0xfe]);write(0x1efc,[0x18,0]);c.call('write_registers',{'pc':entry,'s':0x1efc,'dp':0,'cc':0x50})
 t=c.call('read_cycles')['event_ticks'];go(0x1800);cycles=(c.call('read_cycles')['event_ticks']-t)//8
 pixels=b''.join(physical(pg*8192,8192) for pg in range(0x2c,0x34));data=physical(0x34*8192,8192)
 return pixels,data,cycles
try:
 go(ps['pft_ready']);assert read(0x1900,len(presentation))==presentation,'boot presentation/artifact identity';assert read(0x800,len(boot_enemy))==boot_enemy,'boot enemy/artifact identity'
 key(5,True);wait(lambda:read(0xa5)[0]==5);key(5,False);key(1,True);wait(lambda:read(0xa5)[0]==6);key(1,False)
 wait(lambda:read(0xa5)[0]==0 and read(ms['INITIAL_ENTRY_STATE'])[0]==0)
 if '--cleared-skulls' in sys.argv:
  removed=[]
  for slot in range(read(es['ENTITY_COUNT'])[0]):
   address=es['ENTITY_TABLE']+slot*4
   if read(address+2)[0]==es['ENTITY_SKULL']:
    removed.append(list(read(address,4)));write(address+2,[0])
  e['controlled_cleared_skulls']=removed
 park=22 if '--park-far' in sys.argv else 2
 write(ms['PLAYER_CELL_X'],[park,park]);write(ms['PLAYER_FB'],(0x2000+(park*8-8)*160+(park+7)*4).to_bytes(2,'big'));write(ms['PLAYER_DIR'],[255]);e['park_cell']=[park,park]
 for count in range(3 if '--through-two' in sys.argv[6:] else 5):
  deadline=time.monotonic()+45
  if count:release()
  for _ in range(36):go(ps['presentation_flow_tick'])
  for i in range(8):
   assert time.monotonic()<deadline,'crossover phase'
   go(es['frame_render_impl']);assert read(0x58)[0]==count and read(ms['DEATH_STATE'])[0]==0,('missing live count',count);regs=c.call('read_registers');pars=read(0xffa0,8);pages=snapshot();owner=read(ms['FB_BACK_ID'])[0];flags=list(read(ms['RENDER_FLAGS'],16));results={}
   for name in (['reference','candidate'] if i%2==0 else ['candidate','reference']):
    restore(pages,regs,pars);results[name]=invoke(enemy if name=='reference' else candidate,es['frame_render_impl'] if name=='reference' else cs['frame_render_impl'],(oldresident if name=='reference' else resident) if perimeter_only else None)
   raw_differences=[j for j,(a,b) in enumerate(zip(results['reference'][1],results['candidate'][1])) if a!=b]
   assert results['reference'][0]==results['candidate'][0],(count,i,'framebuffer pixels mismatch')
   if '--logical-rings' in sys.argv[6:]:
    assert logical_rings(results['reference'][1],owner)==logical_rings(results['candidate'][1],owner),(count,i,'logical background or other state mismatch',raw_differences[:24])
   else:assert results['reference'][1]==results['candidate'][1],(count,i,'raw state mismatch',raw_differences[:24])
   e['cases'].append({'count':count,'active_count':read(0x58)[0],'index':i,'owner_metadata':owner,'render_intents':flags,'raw_state_difference_bytes':len(raw_differences),'reference_cycles':results['reference'][2],'candidate_cycles':results['candidate'][2],'pixel_sha256':hashlib.sha256(results['candidate'][0]).hexdigest()})
   restore(pages,regs,pars);go(ps['presentation_flow_tick'])
 e['result']='pass'
except Exception as ex:
 import traceback
 e['result']='fail';e['failure']=repr(ex);e['traceback']=traceback.format_exc()
finally:c.close();m.stop(p);out.write_text(json.dumps(e,indent=2)+'\n')
print(json.dumps({k:v for k,v in e.items() if k not in ['cases','samples']}));print('cases',len(e['cases']))
if e['result']!='pass':raise SystemExit(1)
