from pathlib import Path
import sys,time,json,hashlib
root=Path(sys.argv[1]);out=Path(sys.argv[2]);sys.path.insert(0,str(root/'scripts'))
import verify_bug011_runtime as r
import verify_bug009_monitor_input as m
b=root/'build';ms=r.symbols(b/'ladybug.map');ps=r.symbols(b/'ladybug-presentation-runtime.map');es=r.symbols(b/'ladybug-enemy-runtime.map');rom=b/'ladybug.rom';resident=(b/'ladybug-runtime.rom').read_bytes();enemy=(b/'ladybug-enemy-runtime.rom').read_bytes();presentation=(b/'ladybug-presentation-runtime.bin').read_bytes()
e={'rom_sha256':hashlib.sha256(rom.read_bytes()).hexdigest(),'phase':'controlled release-count sweep with real movement/render/audio','deadline_seconds':45,'success_marker':'16 worklists each at zero through three released enemies','timeout_meaning':'named sample boundary absent, not proof of target slowdown','controlled':'existing enemy_release_impl called early; no movement, renderer, collision, audio or clock code changed','samples':[]}
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
e={'phase':'fast-clock NOP calibration','deadline_seconds':10,'success_marker':'known NOP steps yield event-tick and reported-cycle deltas','timeout_meaning':'step boundary absent'}
try:
 go(ps['pft_ready']);assert read(0x1900,12)==presentation[:12]
 regs=c.call('read_registers');old=read(0x1800,8);write(0x1800,[0x12]*8);assert read(0x1800,8)==bytes([0x12]*8)
 c.call('write_registers',{'pc':0x1800,'cc':0x50});e['samples']=[]
 for i in range(4):
  before=c.call('read_cycles');c.call('step_instruction');after=c.call('read_cycles');e['samples'].append({'instruction':'NOP','specified_6809_cycles':2,'event_ticks':after['event_ticks']-before['event_ticks'],'reported_cpu_cycles':after['cpu_cycles']-before['cpu_cycles']})
 e['result']='pass'
finally:c.close();m.stop(p);out.write_text(json.dumps(e,indent=2)+'\n')
print(json.dumps(e,indent=2))
