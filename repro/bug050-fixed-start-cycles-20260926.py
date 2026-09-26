from pathlib import Path
import json,hashlib,sys,time
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/'scripts'))
import verify_bug011_runtime as r
import verify_bug009_monitor_input as m
b=root/'build';rom=b/'ladybug.rom';ps=r.symbols(b/'ladybug-presentation-runtime.map');ins=r.symbols(b/'ladybug-instruction-runtime.map');ms=r.symbols(b/'ladybug.map');resident=(b/'ladybug-runtime.rom').read_bytes();main=ms['mainloop'];ret=main+resident[main-0xC000:main-0xC000+32].index(bytes.fromhex('bd1900'))+3;e={'rom_sha256':hashlib.sha256(rom.read_bytes()).hexdigest(),'phase_deadline_seconds':45,'timeout_meaning':'instruction call/return sample deadline, no speed inference','samples':[]}
p,c=r.launch_fast(m,Path('/mnt/e/projects/ladybug/docs/reference/xroar/src/xroar'),rom)
def go(a):
 ids=m.setup(c,[a])
 try:assert c.run_to_breakpoint(10)['pc']==a
 finally:m.clear(c,ids)
def low(a,n=1):return bytes.fromhex(c.call('read_memory',{'space':'physical','addr':0x38*8192+a,'length':n})['data'])
try:
 go(ps['instructions_tick']);helper=(b/'ladybug-instruction-runtime.bin').read_bytes();assert r.read_bytes(c,0x300,len(helper))==helper
 for _ in range(13):go(ins['consume_event'])
 deadline=time.monotonic()+45
 for i in range(210):
  assert time.monotonic()<deadline
  go(ps['presentation_flow_tick']);tick=int.from_bytes(low(0xB0,2),'big');phase=low(0xCA)[0];start=c.call('read_cycles')['cpu_cycles'];go(ret);cycles=c.call('read_cycles')['cpu_cycles']-start;e['samples'].append({'timer':tick,'phase':phase,'cycles':cycles})
  if tick>=1534:break
 assert e['samples'][-1]['timer']>=1534
 e['maximum_instruction_cycles']=max(s['cycles'] for s in e['samples']);e['result']='pass' if e['maximum_instruction_cycles']<=27000 else 'target_missed'
except Exception as exc:e['result']='fail';e['failure']=f'{type(exc).__name__}: {exc}'
finally:c.close();m.stop(p);(b/'bug050-fixed-start-cycles.json').write_text(json.dumps(e,indent=2)+'\n')
print({k:v for k,v in e.items() if k!='samples'})
if e['result']!='pass':raise SystemExit(1)
