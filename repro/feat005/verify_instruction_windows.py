from pathlib import Path
import json,hashlib,sys,time
root=Path(__file__).resolve().parents[2];sys.path.insert(0,str(root/'scripts'))
import verify_bug011_runtime as r
import verify_bug009_monitor_input as m
b=root/'build';rom=b/'ladybug.rom';ps=r.symbols(b/'ladybug-presentation-runtime.map');ins=r.symbols(b/'ladybug-instruction-runtime.map');ms=r.symbols(b/'ladybug.map');resident=(b/'ladybug-runtime.rom').read_bytes();main=ms['mainloop'];ret=main+resident[main-0xC000:main-0xC000+32].index(bytes.fromhex('bd1900'))+3
E={'rom_sha256':hashlib.sha256(rom.read_bytes()).hexdigest(),'deadline_per_window_seconds':40,'success_marker':'complete presentation call/return samples over colour boundaries and longest pickups','timeout_meaning':'named natural window not fully sampled; partial cycles do not pass','windows':[]}
p,c=r.launch_fast(m,Path('/mnt/e/projects/ladybug/docs/reference/xroar/src/xroar'),rom)
def go(a):
 ids=m.setup(c,[a])
 try:assert c.run_to_breakpoint(10)['pc']==a
 finally:m.clear(c,ids)
def low(a,n=1):return bytes.fromhex(c.call('read_memory',{'space':'physical','addr':0x38*8192+a,'length':n})['data'])
try:
 go(ps['instructions_tick']);helper=(b/'ladybug-instruction-runtime.bin').read_bytes();assert r.read_bytes(c,0x300,len(helper))==helper;assert r.read_bytes(c,ret,2)==resident[ret-0xC000:ret-0xC000+2]
 for target in [31,127,1503,1534,1599,1630]:
  deadline=time.monotonic()+40
  ids=m.setup(c,[ins['irt_draw_player']])
  while True:
   assert time.monotonic()<deadline
   assert c.run_to_breakpoint(10)['pc']==ins['irt_draw_player']
   tick=int.from_bytes(low(0xB0,2),'big')
   if tick>=target:break
  m.clear(c,ids);window={'target':target,'samples':[]};E['windows'].append(window)
  for _ in range(6):
   assert time.monotonic()<deadline
   go(ps['presentation_flow_tick']);tick=int.from_bytes(low(0xB0,2),'big');start=c.call('read_cycles')['event_ticks'];go(ret);cycles=(c.call('read_cycles')['event_ticks']-start)//8;window['samples'].append({'timer_before':tick,'cycles':cycles})
  assert [x['timer_before'] for x in window['samples']]==list(range(target,target+6)),window
 maximum=max(x['cycles'] for w in E['windows'] for x in w['samples']);E['maximum_cycles']=maximum;assert maximum<=27000,maximum;E['result']='pass'
except Exception as exc:E['result']='fail';E['failure']=f'{type(exc).__name__}: {exc}'
finally:c.close();m.stop(p);(root/'repro/feat005-instruction-windows-20260930.json').write_text(json.dumps(E,indent=2)+'\n')
print(E)
if E['result']!='pass':raise SystemExit(1)
