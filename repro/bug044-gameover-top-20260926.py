"""Check game-over TOP after changing the committed record during credited play."""
from pathlib import Path
import time
source=Path(__file__).with_name('bug044-top-authority-20260926.py').read_text()
exec(compile(source.split('\ntry:\n    go("attract_tick_ready")')[0],str(__file__),'exec'))
hs=runtime.symbols(build/'ladybug-highscore-helper.map')
def go(symbol,symbols=presentation_symbols):
 evidence['phase']=symbol
 print('phase='+symbol+' deadline=40s',flush=True)
 ids=monitor.setup(client,[symbols[symbol]])
 try:
  client.call('run');h=client.call('wait_for_stop',{'timeout_ms':40000},timeout=42)
  assert h.get('reason')=='breakpoint' and h.get('pc')==symbols[symbol],h
 finally:monitor.clear(client,ids)
def key(k,on):client.call('inject_key',{'key':k,'action':'press' if on else 'release'})
evidence['scenario']='Seed committed ACE/123456 during credited play, allow natural final death, inspect game-over TOP'
try:
 go('attract_tick_ready')
 assert runtime.read_bytes(client,0x1900,len((build/'ladybug-presentation-runtime.bin').read_bytes()))==(build/'ladybug-presentation-runtime.bin').read_bytes()
 key(5,True);go('credit_tick');key(5,False)
 key(1,True);go('start_screen_done');key(1,False)
 key(0x2B,True);go('add_dot_score',main_symbols);key(0x2B,False)
 assert_live_resident('add_dot_score',48)
 client.call('write_memory',{'space':'physical','addr':0x34*8192+0xF84,'data':forced_record.hex()})
 client.call('write_memory',{'space':'physical','addr':0x38*8192+0xE7,'data':'01'})
 go('start_screen_done')
 assert low(0xA6)==b'\x04',('next screen is not game-over',low(0xA6).hex())
 main=main_symbols['mainloop'];offset=resident[main-0xC000:main-0xC000+32].index(bytes.fromhex('bd1900'))
 return_pc=main+offset+3
 assert_live_resident('mainloop',32)
 samples=[];deadline=time.monotonic()+40;holds=0
 for _ in range(160):
  assert time.monotonic()<deadline,'game-over publication window incomplete'
  go('presentation_flow_tick');mode=low(0xA5)[0]
  start=client.call('read_cycles')['cpu_cycles'];go('return',{'return':return_pc})
  samples.append({'mode_before':mode,'cycles':client.call('read_cycles')['cpu_cycles']-start})
  if mode==7:
   holds+=1
   if holds==2:break
 assert holds==2,'game-over hold not reached'
 evidence['loading_timing']={'sample_count':len(samples),'maximum_cycles':max(x['cycles'] for x in samples),'target_cycles':27000}
 evidence['loading_timing']['target_pass']=evidence['loading_timing']['maximum_cycles']<=27000
 evidence['loading_timing']['acceptance']='Static construction: retain any overrun as technical debt per user decision; not a BUG-044 blocker'
 go('highscore_gameover_tick',hs)
 assert low(0xA5)==b'\x07' and low(0xA6)==b'\x04'
 helper=(build/'ladybug-highscore-helper.bin').read_bytes()
 assert runtime.read_bytes(client,hs['highscore_phase_tick'],len(helper))==helper
 assert physical(0x34*8192+0xF84,10)==forced_record
 evidence['record0']=forced_record.hex();evidence['front_owner']=low(0x8F)[0]
 assert_record_pixels(forced_record,'natural-game-over-with-changed-record',[low(0x8F)[0]])
 evidence['result']='pass'
except Exception as exc:evidence['result']='fail';evidence['failure']=f'{type(exc).__name__}: {exc}'
finally:
 client.close();monitor.stop(process)
 (build/'bug044-gameover-top.json').write_text(json.dumps(evidence,indent=2)+'\n')
print(json.dumps(evidence,indent=2))
if evidence['result']!='pass':raise SystemExit(1)
