"""BUG-051 semantic palettes, natural credit redraw, and ranked-name clearing."""
from pathlib import Path
import sys,gzip
source=Path(__file__).with_name('bug044-top-authority-20260926.py').read_text()
exec(compile(source.split('\ntry:\n    go("attract_tick_ready")')[0],str(__file__),'exec'))
baseline='--baseline' in sys.argv
evidence['success_marker']='Natural credit1/2 palettes, non-target pixels unchanged, exact ranked records, changed TOP and blank-name replay'
evidence['baseline_rom_sha256']='302f2faaab8790b94aa09f40368acf5fc58807ea8afd0d858aff0087165c7420'
stage_glyphs=[int(v) for line in (build/'ladybug_stage_glyphs.inc').read_text().splitlines() if 'fcb' in line for v in line.split('fcb',1)[1].split(',')]
roles=json.loads((root/'repro/bug051-semantic-cells-20260924.json').read_text())
rows=roles['dynamic_table']['record_rows']
def go(symbol,symbols=presentation_symbols):
 ids=monitor.setup(client,[symbols[symbol]])
 try:
  client.call('run');h=client.call('wait_for_stop',{'timeout_ms':40000},timeout=42)
  assert h.get('reason')=='breakpoint' and h.get('pc')==symbols[symbol],(symbol,h)
 finally:monitor.clear(client,ids)
def key(k,on):client.call('inject_key',{'key':k,'action':'press' if on else 'release'})
def tile(f,x,y):return b''.join(f[y*1280+x*4+r*160:y*1280+x*4+r*160+4] for r in range(8))
def pens(data):return {v for b in data for v in (b>>4,b&15) if v}
def capture(count):
 go('start_screen_done');go('credit_tick');assert low(0xA6)==b'\x03' and low(0xA8)[0]==count,('credit publication',count,low(0xA6).hex(),low(0xA8).hex())
 owner=low(0x8F)[0];frame=runtime.read_owner(client,owner)
 if baseline:
  (build/f'bug051-baseline-{count}.bin').write_bytes(frame)
  return
 targets=set();summary={}
 for name,role in roles['static_roles'].items():
  cells=[(x,y) for y,a,z in role['spans_y_xfirst_xlast'] for x in range(a,z+1)]
  targets.update(cells)
  if count>=2 and name.startswith('first_prompt'):continue
  observed=pens(b''.join(tile(frame,x,y) for x,y in cells));assert observed=={role['target_pen']},(count,name,observed)
  summary[name]=sorted(observed)
 targets.update((x,23) for x in range(10,30))
 if count>=2:
  prompt=[1,36,24,27,36,2,36,25,21,10,34,14,27,36,11,30,29,29,24,23]
  for i,code in enumerate(prompt):assert tile(frame,10+i,23)==glyph(stage_glyphs[code],8 if code<=2 else 5),(count,'two-player prompt',i)
 records=physical(0x34*8192+0xF84,90)
 for rank,y in enumerate(rows):
  rec=records[rank*10:rank*10+10];color=1 if rank==0 else 7
  for i,n in enumerate(rec[3:]):
   code=None if n==0 else resident[descriptor_offset+n*2]
   assert tile(frame,16+i,y)==glyph(code,color),(count,'rank name',rank,i)
   targets.add((16+i,y))
  for i,d in enumerate([d for b in rec[:3] for d in (b>>4,b&15)]):
   assert tile(frame,27+i,y)==glyph(d,color),(count,'rank score',rank,i)
   targets.add((27+i,y))
 assert tile(frame,33,9)==glyph(count,6),(count,'credit')
 if count<=2:
  old=gzip.decompress((root/f'repro/bug051-baseline-{count}-20260926.bin.gz').read_bytes())
  wrong=[(x,y) for y in range(24) for x in range(40) if (x,y) not in targets and tile(frame,x,y)!=tile(old,x,y)]
  assert not wrong,('non-target cells',count,wrong)
 evidence['captures'].append({'credits':count,'owner':owner,'frame_sha256':hashlib.sha256(frame).hexdigest(),'semantic_palette':summary,'rank_pixels_exact':True,'record0':records[:10].hex(),'non_target_comparison':'pass' if count<=2 else 'fixture'})
try:
 go('attract_tick_ready');p=(build/'ladybug-presentation-runtime.bin').read_bytes();assert runtime.read_bytes(client,0x1900,len(p))==p
 for count in range(1,3 if baseline else 6):
  if count==3:client.call('write_memory',{'space':'physical','addr':0x34*8192+0xF84,'data':forced_record.hex()})
  if count==4:client.call('write_memory',{'space':'physical','addr':0x34*8192+0xF87,'data':'00'*7})
  key(5,True);capture(count);key(5,False);go('pft_ready')
 evidence['result']='pass';evidence['baseline']=baseline
except Exception as exc:evidence['result']='fail';evidence['failure']=repr(exc)
finally:
 client.close();monitor.stop(process);(build/('bug051-baseline.json' if baseline else 'bug051-palette-parent.json')).write_text(json.dumps(evidence,indent=2)+'\n')
print(json.dumps(evidence,indent=2))
if evidence['result']!='pass':raise SystemExit(1)
