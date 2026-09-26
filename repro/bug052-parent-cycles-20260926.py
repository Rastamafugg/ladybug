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
  c.call('run');h=c.call('wait_for_stop',{'timeout_ms':10000},timeout=12);assert h.get('reason')=='breakpoint' and h['pc']==address,h
 finally:m.clear(c,ids)
try:
 go(ps['presentation_flow_tick']);assert r.read_bytes(c,0x1900,len(module))==module
 assert r.read_bytes(c,ret,2)==resident[ret-0xC000:ret-0xC000+2]
 go(ps['attract_tick_ready']);c.call('inject_key',{'key':5,'action':'press'});c.call('inject_key',{'key':6,'action':'press'})
 deadline=time.monotonic()+45; holds=0
 for i in range(160):
  assert time.monotonic()<deadline
  go(ps['presentation_flow_tick']);mode=low(0xA5)[0];cell=int.from_bytes(low(0xAA,2),'big');t=c.call('read_cycles')['cpu_cycles'];go(ret);cycles=c.call('read_cycles')['cpu_cycles']-t
  record['samples'].append({'mode_before':mode,'cell_before':cell,'cycles':cycles})
  if i==1:c.call('inject_key',{'key':5,'action':'release'});c.call('inject_key',{'key':6,'action':'release'})
  if mode==5:
   holds+=1
   if holds==24:break
 assert holds==24,('missing held-animation samples',holds)
 record['active_hold_maximum_cycles']=max(v['cycles'] for v in record['samples'] if v['mode_before']==5)
 assert record['active_hold_maximum_cycles']<=27000,record['active_hold_maximum_cycles']
 assert low(0xA8)[0]==2
 owner=low(0x8F)[0];assert owner in (0,1)
 frame=bytes.fromhex(c.call('read_memory',{'space':'physical','addr':(0x30 if owner==0 else 0x2C)*8192,'length':30720})['data'])
 chars=screen.load_chars(root/'assets/arcade/chars.json')
 def glyph(code,colour):
  if code==36:return bytes(32)
  rows=screen.rotate_ccw(chars[code]);return bytes(((colour if row[x] else 0)<<4)|(colour if row[x+1] else 0) for row in rows for x in range(0,8,2))
 def tile(x,y):return b''.join(frame[y*1280+x*4+i*160:y*1280+x*4+i*160+4] for i in range(8))
 assert tile(33,9)==glyph(2,6)
 for i,code in enumerate((1,36,24,27,36,2,36,25,21,10,34,14,27,36,11,30,29,29,24,23)):assert tile(10+i,23)==glyph(code,8 if code in (1,2) else 5),i
 record['two_credit_front_pixels']='pass';record['maximum_presentation_call_cycles']=max(s['cycles'] for s in record['samples']);record['result']='pass'
except Exception as exc:record['result']='fail';record['failure']=f'{type(exc).__name__}: {exc}'
finally:c.close();m.stop(p);(b/'bug052-parent-cycles.json').write_text(json.dumps(record,indent=2)+'\n')
print({k:v for k,v in record.items() if k!='samples'})
if record['result']!='pass':raise SystemExit(1)
