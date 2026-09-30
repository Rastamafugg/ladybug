#!/usr/bin/env python3
"""Existing actor oracle plus bounded natural eight-actor checks; no forced game state."""
from pathlib import Path
import sys,json,time,hashlib,functools
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'scripts'))
import verify_bug011_runtime as r,verify_bug009_monitor_input as m
from gmc_lzss import decompress
# Reuse the independent raw-pen/transform oracle with the approved actor extension.
source=(ROOT/'scripts/verify_bug010_attract_actors.py').read_text()
source=source.replace('    ([35, 4],','    ([20, 4], 0x3450, [39, 40, 41], [2, 5, 12], 0xC0000000),\n    ([35, 4],')
for old,new in [('7296','7680'),('phase * 19','phase * 20'),('19 x 3','20 x 3'),('!= 44','!= 46'),('0xBC80','0xBE00'),('0xBCA6','0xBE28'),('not 44 bytes','not 46 bytes'),('"lda     #$23", "cmpy    #$9C80"','"lda     #PRESENTATION_ATTRACT_BUNDLE_PAGE", "cmpy    #$9E00"'),('!= 0x23','!= 0x3B'),('staging page $23','staging page $3B'),('seven authored actors','eight authored actors')]:source=source.replace(old,new)
namespace={'__file__':str(ROOT/'scripts/verify_bug010_attract_actors.py'),'__name__':'feat008_oracle'}
exec(compile(source,namespace['__file__'],'exec'),namespace)
namespace['main']()
b=ROOT/'build';rom=b/'ladybug.rom';ps=r.symbols(b/'ladybug-presentation-runtime.map');hs=r.symbols(b/'ladybug.map');layout=json.loads((b/'ladybug-presentation.json').read_text());sparse=json.loads((b/'ladybug-sparse-layout.json').read_text())
surfaces=decompress((b/'ladybug-attract-actor-underlays.bin').read_bytes(),7680);records=(b/'ladybug-attract-actor-records.bin').read_bytes();e={'rom_sha256':r.digest(rom.read_bytes()),'phase_deadline_seconds':40,'timeout_meaning':'named publication/transition boundary not reached; no runtime-speed inference','checks':[]}
p,c=r.launch_fast(m,ROOT/'docs/reference/xroar/src/xroar',rom)
def phys(a,n):return bytes.fromhex(c.call('read_memory',{'space':'physical','addr':a,'length':n})['data'])
def low(a,n=1):return phys(0x38*8192+a,n)
def reach(addr):
 ids=m.setup(c,[addr])
 try:assert c.run_to_breakpoint(40)['pc']==addr
 finally:m.clear(c,ids)
def tick():reach(ps['pft_ready'])
def wait(name,pred):
 print('phase='+name+' deadline=40s timeout=marker-not-reached',flush=True);end=time.monotonic()+40
 while time.monotonic()<end:
  tick()
  if pred():return
 raise TimeoutError(name)
def title_ready():return low(0xA5)[0]==2 and low(0xA6)[0]==0 and low(0xD4)[0]==0 and low(0x8F)[0] in (0,1)
def frame(owner):return phys((0x30 if owner==0 else 0x2C)*8192,30720)
def phases(label,count=80):
 seen=set();changes=[];previous=None;end=time.monotonic()+40
 for i in range(count):
  assert time.monotonic()<end,label
  tick();assert title_ready()
  owner=low(0x8F)[0];assert all(r.digest(frame(o)) in layout['attract_actor_surfaces']['phase_frame_sha256'] for o in (0,1));h=r.digest(frame(owner));assert h in layout['attract_actor_surfaces']['phase_frame_sha256'],(label,i,h)
  phase=layout['attract_actor_surfaces']['phase_frame_sha256'].index(h);seen.add((owner,phase))
  actor_phase=low(0xD3)[0];timer=int.from_bytes(low(0xB0,2),'big')
  if actor_phase!=previous:changes.append({'timer':timer,'phase':actor_phase});previous=actor_phase
 assert {p for o,p in seen}=={0,1,2},seen
 assert all(z['timer']-a['timer']==8 for a,z in zip(changes[1:],changes[2:])),changes
 e['checks'].append({'name':label,'owner_phase_pairs':sorted(seen),'phase_changes':changes});return seen
try:
 reach(ps['presentation_flow_tick'])
 assert r.read_bytes(c,0xC000,15872)==(b/'ladybug-runtime.rom').read_bytes()[:15872]
 assert low(0x1900,(b/'ladybug-presentation-runtime.bin').stat().st_size)==(b/'ladybug-presentation-runtime.bin').read_bytes()
 assert low(0x06B2,(b/'ladybug-perimeter-reset-helper.bin').stat().st_size)==(b/'ladybug-perimeter-reset-helper.bin').read_bytes()
 assert phys(0x23*8192+0xC40,(b/'ladybug-highscore-helper.bin').stat().st_size)==(b/'ladybug-highscore-helper.bin').read_bytes()
 bundle=[x for x in sparse['gmc']['segments'] if x['target']=='attract_actor_bundle'];raw=(b/'ladybug-attract-actor-underlays.bin').read_bytes()+records
 for x in bundle:
  off=x['target_offset'];at=x['destination_page']*8192+x['destination_address']-0xA000
  assert phys(at,x['count'])==raw[off:off+x['count']]
 assert phys(0x3C*8192,7680)==surfaces;assert phys(0x3C*8192+7680,46)==records
 e['checks'].append({'name':'authored staged copied and expanded byte identities','result':'pass'})
 wait('cold attract published',title_ready);pairs=phases('cold natural attract phases')
 resident=(b/'ladybug-runtime.rom').read_bytes();main=hs['mainloop'];call=resident[main-0xC000:main-0xC000+32].index(bytes.fromhex('bd1900'));ret=main+call+3
 assert r.read_bytes(c,ret,2)==resident[ret-0xC000:ret-0xC000+2]
 samples=[];end=time.monotonic()+40
 for i in range(40):
  assert time.monotonic()<end,'attract input-through-return cycle boundary'
  reach(ps['presentation_flow_tick']);regs=c.call('read_registers');actual_ret=r.read_word(c,regs['s']);assert actual_ret==ret,(hex(ret),hex(actual_ret),regs);before=low(0xD3)[0];start=c.call('read_cycles')['cpu_cycles'];reach(ret);cost=c.call('read_cycles')['cpu_cycles']-start
  samples.append({'worklist':'phase copy' if low(0xD3)[0]!=before else 'unchanged phase','cycles':cost})
 e['timing']={kind:{'count':len([x for x in samples if x['worklist']==kind]),'maximum_cycles':max(x['cycles'] for x in samples if x['worklist']==kind)} for kind in ('phase copy','unchanged phase')}
 # Invalidate only the phase cache to repaint/publish through the real owner path.
 # This performs a no-change publication without forcing FRONT/BACK identities.
 r.write_byte(c,0xD3,255);tick();tick()
 pairs|=phases('isolated opposite-owner sequence');assert pairs=={(o,p) for o in (0,1) for p in range(3)},pairs
 # Skip to natural screen transitions, then catch the next attract publication.
 reach(ps['instructions_tick'])
 print('phase=natural-attract-return marker=attract_tick deadline=40s timeout=marker-not-reached',flush=True);reach(ps['attract_tick']);wait('returned attract publication',title_ready);phases('natural return phases and both owners',48)
 c.call('inject_key',{'key':5,'action':'press'})
 wait('credit interruption',lambda:low(0xA8)[0]==1)
 c.call('inject_key',{'key':5,'action':'release'})
 wait('high score publication',lambda:low(0xA6)[0]==3 and low(0xA5)[0]==5 and low(0xD4)[0]==0 and low(0x91)[0]==0 and low(0xE1)[0]==0)
 c.call('inject_key',{'key':1,'action':'press'})
 wait('credited start',lambda:low(0xA6)[0]==2 and low(0xA8)[0]==0)
 c.call('inject_key',{'key':1,'action':'release'})
 e['checks'].append({'name':'credit and start pre-emption','result':'pass'});e['status']='pass'
except BaseException as exc:e['status']='fail';e['failure']=repr(exc);raise
finally:
 c.close();m.stop(p);(ROOT/'repro/feat008-verification-20260930.json').write_text(json.dumps(e,indent=2)+'\n')
print(json.dumps(e),flush=True)
