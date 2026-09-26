from pathlib import Path
import hashlib,json,sys,time
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/'scripts'))
import verify_bug011_runtime as r
import verify_bug009_monitor_input as m
import build_screen as screen
b=root/'build';ps=r.symbols(b/'ladybug-presentation-runtime.map');ms=r.symbols(b/'ladybug.map');rom=b/'ladybug.rom';module=(b/'ladybug-presentation-runtime.bin').read_bytes();resident=(b/'ladybug-runtime.rom').read_bytes();main=ms['mainloop'];op=resident[main-0xC000:main-0xC000+32].index(bytes.fromhex('bd1900'));ret=main+op+3
record={'rom_sha256':hashlib.sha256(rom.read_bytes()).hexdigest(),'phase_deadline_seconds':45,'timeout_meaning':'presentation call/return marker not observed; no speed inference','samples':[]}
p,c=r.launch_fast(m,Path('/mnt/e/projects/ladybug/docs/reference/xroar/src/xroar'),rom)
def low(a,n=1):return bytes.fromhex(c.call('read_memory',{'space':'physical','addr':0x38*8192+a,'length':n})['data'])
def go(address):
 ids=m.setup(c,[address])
 try:
  h=c.run_to_breakpoint(10);assert h['pc']==address,h
 finally:m.clear(c,ids)
try:
 go(ps['presentation_flow_tick']);assert r.read_bytes(c,0x1900,len(module))==module
 assert r.read_bytes(c,ret,2)==resident[ret-0xC000:ret-0xC000+2]
 go(ps['attract_next'])
 assert low(0xA6)[0]==0
 deadline=time.monotonic()+45; holds=0
 for i in range(112):
  assert time.monotonic()<deadline
  go(ps['presentation_flow_tick']);mode=low(0xA5)[0];cell=int.from_bytes(low(0xAA,2),'big');t=c.call('read_cycles')['cpu_cycles'];go(ret);cycles=c.call('read_cycles')['cpu_cycles']-t
  record['samples'].append({'mode_before':mode,'cell_before':cell,'cycles':cycles})

  if mode==3:
   holds+=1
   if holds==2:break
 record['maximum_presentation_call_cycles']=max(s['cycles'] for s in record['samples']);record['result']='pass'
except Exception as exc:record['result']='fail';record['failure']=f'{type(exc).__name__}: {exc}'
finally:c.close();m.stop(p);(b/'bug048-instruction-load-cycles.json').write_text(json.dumps(record,indent=2)+'\n')
print({k:v for k,v in record.items() if k!='samples'})
if record['result']!='pass':raise SystemExit(1)
