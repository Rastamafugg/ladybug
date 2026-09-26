"""Credit/start normally, seed a boundary score, then let natural dot awards cross TOP."""
from pathlib import Path
source=Path(__file__).with_name('bug044-top-authority-20260926.py').read_text()
# Reuse the existing pixel oracle and monitor helpers, without its scenario.
exec(compile(source.split('\ntry:\n    go("attract_tick_ready")')[0],str(__file__),'exec'))
evidence['scenario']='Natural credit/start and dot-award dispatch with seeded near-TOP score'
evidence['success_marker']='credited 1ST crosses 90000 through natural dot awards; committed TOP pixels stay fixed on both owners'
def go(symbol,symbols=presentation_symbols):
 evidence['phase']=symbol
 print('phase='+symbol+' deadline=40s marker='+hex(symbols[symbol]),flush=True)
 ids=monitor.setup(client,[symbols[symbol]])
 try:
  client.call('run');hit=client.call('wait_for_stop',{'timeout_ms':40000},timeout=42)
  assert hit.get('reason')=='breakpoint' and hit.get('pc')==symbols[symbol],hit
 finally:monitor.clear(client,ids)
def key(k,on):client.call('inject_key',{'key':k,'action':'press' if on else 'release'})
try:
 go('attract_tick_ready')
 assert runtime.read_bytes(client,0x1900,len((build/'ladybug-presentation-runtime.bin').read_bytes()))==(build/'ladybug-presentation-runtime.bin').read_bytes()
 key(5,True);go('credit_tick');key(5,False)
 assert low(0xA8)==b'\x01'
 key(1,True);go('start_screen_done');key(1,False)
 assert low(0xA6)==b'\x02' and low(0xA8)==b'\x00'
 key(0x2B,True) # Existing XRoar CoCo scan code for the gameplay up arrow.
 go('add_dot_score',main_symbols)
 assert low(0xA5)==b'\x00'
 assert_live_resident('add_dot_score',48)
 record=physical(0x34*8192+0xF84,10)
 assert record==default_record
 client.call('write_memory',{'space':'physical','addr':0x38*8192+0x1D,'data':'089990'})
 evidence['seed']={'score':'089990','point':'first naturally reached add_dot_score after credited start','record0':record.hex()}
 go('add_dot_score',main_symbols)
 assert low(0x1D,3)==bytes.fromhex('090000'),low(0x1D,3).hex()
 go('mainloop',main_symbols)
 assert low(0x1D,3)==bytes.fromhex('090010'),low(0x1D,3).hex()
 assert physical(0x34*8192+0xF84,10)==record
 score_owners=set()
 for _ in range(2):
  go('pft_ready')
  owner=low(0x8F)[0]
  assert_record_pixels(record,'credited-natural-awards-above-TOP',[owner])
  frame=runtime.read_owner(client,owner)
  for i,digit in enumerate((0,9,0,0,1,0)):
   offset=2*1280+(33+i)*4
   tile=b''.join(frame[offset+j*160:offset+j*160+4] for j in range(8))
   assert tile==glyph(digit,main_symbols['TEXT_SCORE']),('1ST',owner,i,tile.hex())
  score_owners.add(owner)
 assert score_owners=={0,1},score_owners
 evidence['1ST_90010_pixels_owners']=sorted(score_owners)
 evidence['final_score']=low(0x1D,3).hex()
 evidence['record_unchanged']=physical(0x34*8192+0xF84,10)==record
 evidence['result']='pass'
except Exception as exc:
 evidence['result']='fail';evidence['failure']=f'{type(exc).__name__}: {exc}'
 try:
  client.call('pause');evidence['failure_state']={'regs':client.call('read_registers'),'low':low(0,0xA9).hex()}
 except Exception:pass
finally:
 client.close();monitor.stop(process)
 (build/'bug044-credited-crossing.json').write_text(json.dumps(evidence,indent=2)+'\n')
print(json.dumps(evidence,indent=2))
if evidence['result']!='pass':raise SystemExit(1)
