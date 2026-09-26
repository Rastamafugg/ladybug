"""Natural BUG-049 final gameplay to both game-over publications."""
from pathlib import Path
import time, sys
output=Path(sys.argv[2]).resolve()
sys.path.insert(0,str(Path(__file__).parent))
source=Path(__file__).with_name('bug044-top-authority-20260926.py').read_text().replace('root = Path(__file__).resolve().parents[1]', 'root = Path(sys.argv[1]).resolve()')
exec(compile(source.split('\ntry:\n    go("attract_tick_ready")')[0],str(__file__),'exec'))
import build_presentation as compiler
import build_screen

def go(symbol,symbols=presentation_symbols):
 print('phase='+symbol+' deadline=40s',flush=True)
 evidence['phase']=symbol
 ids=monitor.setup(client,[symbols[symbol]])
 try:
  client.call('run');hit=client.call('wait_for_stop',{'timeout_ms':40000},timeout=42)
  assert hit.get('reason')=='breakpoint' and hit.get('pc')==symbols[symbol],hit
 finally:monitor.clear(client,ids)
def key(k,on):client.call('inject_key',{'key':k,'action':'press' if on else 'release'})
def tile(f,x,y):return b''.join(f[y*1280+x*4+r*160:y*1280+x*4+r*160+4] for r in range(8))
def preserved(x,y):return x<=8 or x>=31 or y in (0,23)
evidence['success_marker']='Natural terminal dispatch; both game-over publications preserve final HUD/perimeter and exactly clear/redraw authored interior; next screen reached'
evidence['scenario']='Natural two-credit Player1 entry, natural dot pickup and unseeded terminal death'
try:
 go('attract_tick_ready');p=(build/'ladybug-presentation-runtime.bin').read_bytes();assert runtime.read_bytes(client,0x1900,len(p))==p
 key(5,True);key(6,True);go('credit_tick');key(5,False);key(6,False)
 assert low(0xA8)==b'\x02'
 key(1,True);go('start_screen_done');key(1,False)
 key(0x2B,True);go('add_dot_score',main_symbols);key(0x2B,False)
 assert_live_resident('death_tick',24)
 go('dt_game_over',main_symbols)
 last={o:runtime.read_owner(client,o) for o in (0,1)}
 evidence['last_game']={str(o):hashlib.sha256(f).hexdigest() for o,f in last.items()}
 go('start_screen_done');assert low(0xA6)==b'\x04'
 go('load_done_hold_second')
 # The second completed owner is hydrated, but publication must still execute.
 hs=runtime.symbols(build/'ladybug-highscore-helper.map')
 go('highscore_gameover_tick',hs);go('highscore_gameover_tick',hs)
 helper=(build/'ladybug-highscore-helper.bin').read_bytes();assert runtime.read_bytes(client,hs['highscore_phase_tick'],len(helper))==helper
 assert low(0xA6)==b'\x04'
 chars=build_screen.load_chars(root/'assets/arcade/chars.json');tiles=[];ids={}
 mapping,_=compiler.compile_map(root/'tiled'/compiler.MAP_FILES['game-over'],chars,tiles,ids,False,True)
 authored=compiler.title_framebuffer(mapping,tiles)
 rows=[]
 for o in (0,1):
  frame=runtime.read_owner(client,o)
  changed=[(x,y) for y in range(24) for x in range(40) if preserved(x,y) and tile(frame,x,y)!=tile(last[o],x,y)]
  wrong=[(x,y) for y in range(24) for x in range(40) if not preserved(x,y) and tile(frame,x,y)!=tile(authored,x,y)]
  assert not changed,('preserved cells',o,changed)
  assert not wrong,('authored interior',o,wrong)
  probes={'top':[(x,1) for x in range(9,31)],'left':[(9,y) for y in range(2,23)],'right':[(31,y) for y in range(2,23)],'bottom':[(x,23) for x in range(9,31)],'text':[(x,11) for x in (15,16,17,18,20,21,22,23)]}
  colours={k:sorted({v for x,y in coords for byte in tile(frame,x,y) for v in (byte>>4,byte&15) if v}) for k,coords in probes.items()}
  evidence.setdefault('semantic_colours',[]).append({'owner':o,**colours})
  if '--expect-fixed' in sys.argv:
   assert colours['top']==[4] and colours['left']==[4] and colours['text']==[1],colours
  assert tile(frame,33,9)==glyph(1,6),'credit1 white'
  rows.append({'owner':o,'frame_sha256':hashlib.sha256(frame).hexdigest(),'preserved_differences':0,'interior_differences':0,'credit1_white':True})
 evidence['gameover_publications']=rows
 go('start_screen_done');evidence['next_screen']=low(0xA6)[0];assert evidence['next_screen']!=4
 evidence['result']='pass'
except Exception as exc:evidence['result']='fail';evidence['failure']=repr(exc)
finally:
 client.close();monitor.stop(process);output.write_text(json.dumps(evidence,indent=2)+'\n')
print(json.dumps(evidence,indent=2))
if evidence['result']!='pass':raise SystemExit(1)
