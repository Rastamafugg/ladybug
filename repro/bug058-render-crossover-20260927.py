from pathlib import Path
import sys,time,json,hashlib
root=Path(sys.argv[1]);out=Path(sys.argv[2]);fit=Path(sys.argv[3]);sys.path.insert(0,str(root/'scripts'))
import verify_bug011_runtime as r
import verify_bug009_monitor_input as m
b=root/'build';ms=r.symbols(b/'ladybug.map');ps=r.symbols(b/'ladybug-presentation-runtime.map');es=r.symbols(b/'ladybug-enemy-runtime.map');rom=b/'ladybug.rom';resident=(b/'ladybug-runtime.rom').read_bytes();enemy=(b/'ladybug-enemy-runtime.rom').read_bytes();presentation=(b/'ladybug-presentation-runtime.bin').read_bytes()
au=r.symbols(b/'ladybug-audio-runtime.map');audio=(b/'ladybug-audio-runtime.bin').read_bytes()
e={'rom_sha256':hashlib.sha256(rom.read_bytes()).hexdigest(),'phase':'controlled release-count sweep with real movement/render/audio','deadline_seconds':45,'success_marker':'16 worklists each at zero through three released enemies','timeout_meaning':'named sample boundary absent, not proof of target slowdown','controlled':'early enemy releases; reference ROM boot; candidate enemy module temporarily overlaid for controlled render comparisons; original state restored between calls','clock_units':'event_ticks / 8 at verified fast clock; monitor cpu_cycles incorrectly divides by16','samples':[]}
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
candidate=(fit/'build/bug058-enemy-check.bin').read_bytes();cs=r.symbols(fit/'build/bug058-enemy-check.map')
e.update(phase='controlled same-state render crossover',success_marker='identical framebuffer and bank-$34 data after reference/candidate render calls',candidate_enemy_sha256=hashlib.sha256(candidate).hexdigest());e['cases']=[]
def physical(a,n):return bytes.fromhex(c.call('read_memory',{'space':'physical','addr':a,'length':n})['data'])
def putphysical(a,v):c.call('write_memory',{'space':'physical','addr':a,'data':bytes(v).hex()})
def snapshot():return [physical(pg*8192,8192) for pg in range(64)]
def restore(pages,regs,pars):
 for pg,data in enumerate(pages):putphysical(pg*8192,data)
 write(0xffa0,pars);c.call('write_registers',{k:regs[k] for k in ('a','b','cc','dp','x','y','u','s','pc')})
def invoke(code,entry):
 write(0x800,code);assert read(0x800,len(code))==code
 write(0x1800,[0x20,0xfe]);write(0x1efc,[0x18,0]);c.call('write_registers',{'pc':entry,'s':0x1efc,'dp':0,'cc':0x50})
 t=c.call('read_cycles')['event_ticks'];go(0x1800);cycles=(c.call('read_cycles')['event_ticks']-t)//8
 pixels=b''.join(physical(pg*8192,8192) for pg in range(0x28,0x30));data=physical(0x34*8192,8192)
 return pixels,data,cycles
try:
 go(ps['pft_ready']);assert read(0x1900,len(presentation))==presentation
 key(5,True);wait(lambda:read(0xa5)[0]==5);key(5,False);key(1,True);wait(lambda:read(0xa5)[0]==6);key(1,False)
 wait(lambda:read(0xa5)[0]==0 and read(ms['INITIAL_ENTRY_STATE'])[0]==0)
 for count in range(5):
  deadline=time.monotonic()+45
  if count:release()
  for _ in range(36):go(ps['presentation_flow_tick'])
  for i in range(8):
   assert time.monotonic()<deadline,'crossover phase'
   go(es['frame_render_impl']);regs=c.call('read_registers');pars=read(0xffa0,8);pages=snapshot();owner=read(ms['FB_BACK_ID'])[0];flags=list(read(ms['RENDER_FLAGS'],16));results={}
   for name in (['reference','candidate'] if i%2==0 else ['candidate','reference']):
    restore(pages,regs,pars);results[name]=invoke(enemy if name=='reference' else candidate,es['frame_render_impl'] if name=='reference' else cs['frame_render_impl'])
   assert results['reference'][:2]==results['candidate'][:2],(count,i,'pixel/data mismatch')
   e['cases'].append({'count':count,'index':i,'owner_metadata':owner,'render_intents':flags,'reference_cycles':results['reference'][2],'candidate_cycles':results['candidate'][2],'pixel_sha256':hashlib.sha256(results['candidate'][0]).hexdigest()})
   restore(pages,regs,pars);go(ps['presentation_flow_tick'])
 e['result']='pass'
except Exception as ex:e['result']='fail';e['failure']=repr(ex)
finally:c.close();m.stop(p);out.write_text(json.dumps(e,indent=2)+'\n')
print(json.dumps({k:v for k,v in e.items() if k not in ['cases','samples']}));print('cases',len(e['cases']))
if e['result']!='pass':raise SystemExit(1)
