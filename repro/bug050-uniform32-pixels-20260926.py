from pathlib import Path
import sys,json,hashlib,time
root=Path(__file__).resolve().parents[1];sys.path[:0]=[str(root/'scripts'),str(root/'repro')]
import verify_bug011_runtime as r
import verify_bug009_monitor_input as m
from rsch013_colour_animation_capture import cell_pens,save_png
b=root/'build';rom=b/'ladybug.rom';ps=r.symbols(b/'ladybug-presentation-runtime.map');e={'rom_sha256':hashlib.sha256(rom.read_bytes()).hexdigest(),'deadline_seconds':45,'success_marker':'yellow and blue target pixels on both published framebuffer owners','timeout_meaning':'natural visible colour-owner coverage missing','captures':[]}
p,c=r.launch_fast(m,Path('/mnt/e/projects/ladybug/docs/reference/xroar/src/xroar'),rom)
def low(a,n=1):return bytes.fromhex(c.call('read_memory',{'space':'physical','addr':0x38*8192+a,'length':n})['data'])
try:
 ids=m.setup(c,[ps['instructions_tick']]);assert c.run_to_breakpoint(40)['pc']==ps['instructions_tick'];m.clear(c,ids)
 helper=(b/'ladybug-instruction-runtime.bin').read_bytes();assert r.read_bytes(c,0x300,len(helper))==helper
 ids=m.setup(c,[ps['pft_ready']]);deadline=time.monotonic()+45;seen=set()
 while len(seen)<4:
  assert time.monotonic()<deadline;assert c.run_to_breakpoint(10)['pc']==ps['pft_ready'];tick=int.from_bytes(low(0xB0,2),'big')
  if not (35<=tick<=38 or 67<=tick<=70):continue
  colour=2 if tick<60 else 3;owner=low(0x8F)[0];key=(colour,owner)
  if key in seen:continue
  frame=r.read_owner(c,owner);pens={int(k) for y in (7,8) for x in (13,14) for k in cell_pens(frame,x,y)};assert pens=={colour},(tick,owner,pens)
  crop=b''.join(frame[(7*8+row)*160+13*4:(7*8+row)*160+13*4+8] for row in range(16));e['captures'].append({'timer':tick,'owner':owner,'pens':sorted(pens),'crop_sha256':hashlib.sha256(crop).hexdigest()});seen.add(key)
 for colour in (2,3):assert len({x['crop_sha256'] for x in e['captures'] if colour in x['pens']})==1
 save_png(frame,b/'bug050-uniform32-instructions.png');e['result']='pass'
except Exception as exc:e['result']='fail';e['failure']=f'{type(exc).__name__}: {exc}'
finally:c.close();m.stop(p);(b/'bug050-uniform32-pixels.json').write_text(json.dumps(e,indent=2)+'\n')
print(e)
if e['result']!='pass':raise SystemExit(1)
