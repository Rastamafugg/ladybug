from pathlib import Path
import json,hashlib,sys,time
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/'scripts'))
import verify_bug011_runtime as r
import verify_bug009_monitor_input as m
b=root/'build';rom=b/'ladybug.rom';ps=r.symbols(b/'ladybug-presentation-runtime.map');ins=r.symbols(b/'ladybug-instruction-runtime.map');ms=r.symbols(b/'ladybug.map');manifest=json.loads((b/'ladybug-presentation.json').read_text());e={'rom_sha256':hashlib.sha256(rom.read_bytes()).hexdigest(),'deadline_per_phase_seconds':45,'timeout_meaning':'named natural instruction event or credit publication not reached','motion':[],'consumes':[]}
p,c=r.launch_fast(m,Path('/mnt/e/projects/ladybug/docs/reference/xroar/src/xroar'),rom)
def phys(a,n):return bytes.fromhex(c.call('read_memory',{'space':'physical','addr':a,'length':n})['data'])
def low(a,n=1):return phys(0x38*8192+a,n)
def go(addr):
 ids=m.setup(c,[addr])
 try:assert c.run_to_breakpoint(40)['pc']==addr
 finally:m.clear(c,ids)
def state():return {'timer':int.from_bytes(low(0xB0,2),'big'),'phase':low(0xCA)[0],'out':int.from_bytes(low(0xAE,2),'big'),'colour':low(0xCF)[0],'colour_timer':low(0xD0)[0]}
try:
 go(ps['instructions_tick']);helper=(b/'ladybug-instruction-runtime.bin').read_bytes();assert r.read_bytes(c,0x300,len(helper))==helper
 clock=ms['asset_instruction_colour_next'];resident=(b/'ladybug-runtime.rom').read_bytes();assert r.read_bytes(c,clock,39)==resident[clock-0xC000:clock-0xC000+39]
 # Use authored runtime constants rather than guesses for the actor cursor.
 outaddr=ins['PRES_OUT']
 def state():return {'timer':int.from_bytes(low(0xB0,2),'big'),'phase':low(0xCA)[0],'out':int.from_bytes(low(outaddr,2),'big'),'colour':low(0xCF)[0],'colour_timer':low(0xD0)[0]}
 deadline=time.monotonic()+45
 while True:
  assert time.monotonic()<deadline;go(ins['irt_draw_player']);s=state()
  if 120<=s['timer']<=132:e['motion'].append(s)
  if s['timer']==132:break
 deltas=[b['out']-a['out'] for a,b in zip(e['motion'],e['motion'][1:])];assert len(deltas)==12 and deltas==[1,0]*6,deltas
 c.call('inject_key',{'key':5,'action':'press'});go(ps['credit_tick']);c.call('inject_key',{'key':5,'action':'release'});assert low(0xA8)[0]==1;assert low(0xA6)[0]==3;e['credit_during_motion']='pass';e['result']='pass'
except Exception as exc:e['result']='fail';e['failure']=f'{type(exc).__name__}: {exc}'
finally:c.close();m.stop(p);(b/'bug050-fixed-start-preemption.json').write_text(json.dumps(e,indent=2)+'\n')
print(e)
if e['result']!='pass':raise SystemExit(1)
