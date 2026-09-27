"""Same-state BUG-058 selective-vs-full actor composition crossover."""
from pathlib import Path
import hashlib,json,sys,time,traceback
w=Path(sys.argv[1]);out=Path(sys.argv[2]);sys.path.insert(0,str(w/'scripts'))
import verify_bug011_runtime as r,verify_bug009_monitor_input as m
b=w/'build';es=r.symbols(b/'ladybug-enemy-runtime.map');ms=r.symbols(b/'ladybug.map');ps=r.symbols(b/'ladybug-presentation-runtime.map');rom=b/'ladybug.rom'
e={'phase':'credited four-enemy same-state selective versus full composition','deadline_seconds_per_phase':45,'success_marker':'two-selected pose with identical starting RAM/registers and exact full BACK pixels after selective and forced-all composition','timeout_meaning':'required four-enemy worklist or render boundary absent; no visual equivalence inferred','rom_sha256':hashlib.sha256(rom.read_bytes()).hexdigest(),'result':'fail'}
p,c=r.launch_fast(m,Path('/mnt/e/projects/ladybug/docs/reference/xroar/src/xroar'),rom)
def read(a,n=1):return r.read_bytes(c,a,n)
def write(a,v):c.call('write_memory',{'addr':a,'data':bytes(v).hex()})
def phys(a,n):return bytes.fromhex(c.call('read_memory',{'space':'physical','addr':a,'length':n})['data'])
def putphys(a,v):c.call('write_memory',{'space':'physical','addr':a,'data':v.hex()})
def go(a):
 ids=m.setup(c,[a]);c.call('run');h=c.call('wait_for_stop',{'timeout_ms':10000},timeout=12)
 if h.get('pc')!=a:
  c.call('pause');raise AssertionError({'target':hex(a),'stop':h,'registers':c.call('read_registers')})
 m.clear(c,ids)
def key(k,on):c.call('inject_key',{'key':k,'action':'press' if on else 'release'})
def wait(pred,label):
 end=time.monotonic()+45
 while time.monotonic()<end:
  go(ps['pft_ready'])
  if pred():return
 raise TimeoutError(label)
def release():
 regs=c.call('read_registers');stack=read(0x1e00,512);stub=read(0x1800,2)
 write(0x1800,[0x20,0xfe]);write(0x1efc,[0x18,0]);addr=es['enemy_release_impl'];assert read(addr,20)==(b/'ladybug-enemy-runtime.rom').read_bytes()[addr-0x800:addr-0x800+20]
 ids=m.setup(c,[0x1800]);c.call('write_registers',{'pc':addr,'s':0x1efc,'dp':0,'cc':0x50});c.call('run');h=c.call('wait_for_stop',{'timeout_ms':10000},timeout=12);assert h.get('pc')==0x1800,h;m.clear(c,ids)
 write(0x1800,stub);write(0x1e00,stack);c.call('write_registers',{k:regs[k] for k in ('a','b','cc','dp','x','y','u','s','pc')})
try:
 go(ps['pft_ready']);assert read(0x800,len((b/'ladybug-enemy-runtime.rom').read_bytes()))==(b/'ladybug-enemy-runtime.rom').read_bytes()
 key(5,True);wait(lambda:read(0xA5)[0]==5,'credit');key(5,False);key(1,True);wait(lambda:read(0xA5)[0]==6,'game start');key(1,False)
 wait(lambda:read(0xA5)[0]==0 and read(ms['INITIAL_ENTRY_STATE'])[0]==0,'gameplay')
 e['identity']='cold ROM and complete enemy module checked before rendered symbol interpretation'
 write(ms['PLAYER_CELL_X'],[2,2]);write(ms['PLAYER_FB'],(0x2000+(2*8-8)*160+(2+7)*4).to_bytes(2,'big'));write(ms['PLAYER_DIR'],[255])
 for _ in range(2):go(ps['presentation_flow_tick'])
 for count in range(1,5):
  release()
  for _ in range(52):go(ps['presentation_flow_tick'])
 assert read(es['ENEMY_ACTIVE'])[0]==4
 end=time.monotonic()+45
 while time.monotonic()<end:
  go(es['actor_closure_restore'])
  selected=list(read(0xBC31,4));mode=read(0xBC35)[0]
  if mode==1 and sum(selected)==2 and read(es['ENEMY_CAPTURE_DIRTY'])[0]==0:break
  go(ps['presentation_flow_tick'])
 else:raise TimeoutError('two-selected worklist')
 gime=c.call('read_gime_state');assert gime['pars']['task0'][5]&63==0x34
 owner=read(ms['FB_BACK_ID'])[0];assert owner in [0,1]
 start=(0x30-4*owner)*8192;regs=c.call('read_registers');pars=read(0xFFA0,8);pages=[phys(pg*8192,8192) for pg in range(64)]
 e['start']={'owner':owner,'selected':selected,'phase':read(0xBC36)[0],'commit_seq':int.from_bytes(read(ms['FB_COMMIT_SEQ'],2),'big'),'state_sha256':hashlib.sha256(b''.join(pages)).hexdigest()}
 def invoke(force_all):
  for pg,data in enumerate(pages):putphys(pg*8192,data)
  write(0xFFA0,pars);c.call('write_registers',{k:regs[k] for k in ('a','b','cc','dp','x','y','u','s','pc')})
  assert hashlib.sha256(b''.join(phys(pg*8192,8192) for pg in range(64))).hexdigest()==e['start']['state_sha256']
  if force_all:write(0xBC31,[1,1,1,1])
  go(es['framebuffer_finish_back'])
  framebuffer=phys(start,30720)
  return {'pixels':framebuffer,'pixel_sha256':hashlib.sha256(framebuffer).hexdigest(),'logic_sha256':hashlib.sha256(read(es['ENEMY_TABLE'],32)).hexdigest(),'direct_page_scratch_sha256':hashlib.sha256(read(0,32)).hexdigest()}
 selective=invoke(False);forced=invoke(True)
 e['selective']={k:v for k,v in selective.items() if k!='pixels'};e['forced_all']={k:v for k,v in forced.items() if k!='pixels'}
 diff=[i for i,(a,b) in enumerate(zip(selective['pixels'],forced['pixels'])) if a!=b]
 e['pixel_difference_count']=len(diff);e['first_pixel_differences']=diff[:16]
 assert not diff,'selective/four-actor BACK pixels differ'
 assert selective['logic_sha256']==forced['logic_sha256'],'logical enemy records differ'
 e['result']='pass'
except Exception as ex:e.update(failure=repr(ex),traceback=traceback.format_exc())
finally:
 c.close();m.stop(p);out.write_text(json.dumps(e,indent=2)+'\n')
print(json.dumps({k:v for k,v in e.items() if k not in ['traceback']},indent=2))
if e['result']!='pass':raise SystemExit(1)
