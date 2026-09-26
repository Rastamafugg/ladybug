from pathlib import Path
import hashlib,json,sys
root=Path(__file__).resolve().parents[1];sys.path[:0]=[str(root/'scripts'),str(root/'repro')]
import verify_bug011_runtime as r
import verify_bug009_monitor_input as m
import build_screen as screen
from rsch013_colour_animation_capture import cell_pens
b=root/'build';rom=b/'ladybug.rom';ms=r.symbols(b/'ladybug.map');ps=r.symbols(b/'ladybug-presentation-runtime.map');resident=(b/'ladybug-runtime.rom').read_bytes();chars=screen.load_chars(root/'assets/arcade/chars.json');desc=ms['dynamic_descriptors']-0xC000
name='ACE    ';ids=[]
for ch in name:
 if ch==' ':ids.append(0);continue
 code=ord(ch)-ord('A')+10
 ids.append(next(i for i in range(184) if resident[desc+2*i]==code and resident[desc+2*i+1]))
record=bytes.fromhex('123456')+bytes(ids)
e={'rom_sha256':hashlib.sha256(rom.read_bytes()).hexdigest(),'phase_deadline_seconds':40,'success_marker':'exact committed ACE/123456 TOP pixels on instruction, level and demo publications','timeout_meaning':'named publication marker not reached','forced_record':record.hex(),'captures':[]}
p,c=r.launch_fast(m,Path('/mnt/e/projects/ladybug/docs/reference/xroar/src/xroar'),rom)
def go(symbol,table=ps):
 address=table[symbol];bp=m.setup(c,[address])
 try:assert c.run_to_breakpoint(40)['pc']==address
 finally:m.clear(c,bp)
def physical(addr,n):return bytes.fromhex(c.call('read_memory',{'space':'physical','addr':addr,'length':n})['data'])
def low(a,n=1):return physical(0x38*8192+a,n)
def glyph(code,colour):
 if code is None:return bytes(32)
 rows=screen.rotate_ccw(chars[code]);return bytes(((colour if row[x] else 0)<<4)|(colour if row[x+1] else 0) for row in rows for x in range(0,8,2))
def capture(phase,owners):
 for owner in owners:
  frame=r.read_owner(c,owner)
  def tile(x,y):return b''.join(frame[y*1280+x*4+i*160:y*1280+x*4+i*160+4] for i in range(8))
  for i,ch in enumerate(name):assert tile(33+i,5)==glyph(None if ch==' ' else ord(ch)-55,1),(phase,owner,'name',i,tile(33+i,5).hex())
  for i,ch in enumerate('123456'):assert tile(33+i,6)==glyph(int(ch),1),(phase,owner,'score',i)
  e['captures'].append({'phase':phase,'owner':owner,'TOP_exact':True,'credit_white':tile(33,9)==glyph(0,6),'cells':{f'{x},{y}':cell_pens(frame,x,y) for x,y in [(18,11),(17,17),(38,11),(33,9)]}})
try:
 go('attract_tick_ready');assert r.read_bytes(c,0x1900,len((b/'ladybug-presentation-runtime.bin').read_bytes()))==(b/'ladybug-presentation-runtime.bin').read_bytes()
 a=ms['asset_draw_top_hud'];assert r.read_bytes(c,a,100)==resident[a-0xC000:a-0xC000+100]
 c.call('write_memory',{'space':'physical','addr':0x34*8192+0xF84,'data':record.hex()});c.call('write_memory',{'space':'physical','addr':0x38*8192+0xE7,'data':'01'})
 go('instructions_tick');capture('instructions',[0,1])
 go('level_tick');
 if low(0x91)[0]:go('level_tick')
 capture('level-start',[low(0x8F)[0]])
 go('main_render',ms)
 for _ in range(2):go('pft_ready');capture('demo',[low(0x8F)[0]])
 assert physical(0x34*8192+0xF84,10)==record
 e['result']='pass'
except Exception as exc:e['result']='fail';e['failure']=f'{type(exc).__name__}: {exc}'
finally:c.close();m.stop(p);(b/'bug044-shared-top.json').write_text(json.dumps(e,indent=2)+'\n')
print(e)
if e['result']!='pass':raise SystemExit(1)
