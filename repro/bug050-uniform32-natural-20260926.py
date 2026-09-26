from pathlib import Path
import json,hashlib,sys,time
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/'scripts'))
import verify_bug011_runtime as r
import verify_bug009_monitor_input as m
b=root/'build';rom=b/'ladybug.rom';ps=r.symbols(b/'ladybug-presentation-runtime.map');ins=r.symbols(b/'ladybug-instruction-runtime.map');ms=r.symbols(b/'ladybug.map');manifest=json.loads((b/'ladybug-presentation.json').read_text());e={'rom_sha256':hashlib.sha256(rom.read_bytes()).hexdigest(),'deadline_per_phase_seconds':45,'timeout_meaning':'named natural instruction event or credit publication not reached','motion':[],'consumes':[],'colour_changes':[]}
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

 assert phys(0x23*8192+0x422,len(helper))==helper
 # Use authored runtime constants rather than guesses for the actor cursor.
 outaddr=ins['PRES_OUT']
 def state():return {'timer':int.from_bytes(low(0xB0,2),'big'),'phase':low(0xCA)[0],'out':int.from_bytes(low(outaddr,2),'big'),'colour':low(0xCF)[0],'colour_timer':low(0xD0)[0]}
 deadline=time.monotonic()+45
 while True:
  assert time.monotonic()<deadline;go(ins['irt_draw_player']);s=state()
  if not e['colour_changes'] or e['colour_changes'][-1]['colour']!=s['colour']:e['colour_changes'].append({'timer':s['timer'],'colour':s['colour']})
  if 128<=s['timer']<=140:e['motion'].append(s)
  if s['timer']==140:break
 assert [x['timer'] for x in e['colour_changes'][1:]]==[33,65,97,129],e['colour_changes']
 deltas=[b['out']-a['out'] for a,b in zip(e['motion'],e['motion'][1:])];assert len(deltas)==12 and deltas==[1,0]*6,deltas
 deadline=time.monotonic()+45
 for index in range(16):
  assert time.monotonic()<deadline;go(ins['consume_event']);s=state();assert s['phase']==index,s
  # Event table is mapped in X at this marker; identify goal and scheduled pickup.
  regs=c.call('read_registers');record=r.read_bytes(c,regs['x'],12);assert s['out']==int.from_bytes(record[4:6],'big'),s;assert s['timer']==int.from_bytes(record[2:4],'big'),s
  if index<15:assert s['colour']==(2 if index<5 else 1 if index<12 else 3),s
  e['consumes'].append(s)
 go(ins['death_angel']);e['angel_timer']=int.from_bytes(low(0xB0,2),'big');assert e['angel_timer']==manifest['instruction_choreography']['angel_tick']
 go(ins['irt_complete']);e['complete_timer']=int.from_bytes(low(0xB0,2),'big');assert e['complete_timer']==manifest['instruction_choreography']['next_screen_tick']
 go(ps['level_tick']);e['trace_consumes']=low(0x06AC)[0];assert e['trace_consumes']==16;e['trace_owners']=low(0x06AE)[0];assert e['trace_owners']==3;e['trace_colour_changes']=low(0x06AB)[0];assert e['trace_colour_changes']==(manifest['instruction_choreography']['death_collision_tick']-1)//32;e['result']='pass'
except Exception as exc:e['result']='fail';e['failure']=f'{type(exc).__name__}: {exc}'
finally:c.close();m.stop(p);(b/'bug050-uniform32-natural.json').write_text(json.dumps(e,indent=2)+'\n')
print(e)
if e['result']!='pass':raise SystemExit(1)
