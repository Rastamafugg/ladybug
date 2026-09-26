"""Sample natural demo foreground work on the current complete ROM."""
from pathlib import Path
import hashlib, json, sys, time
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'scripts'))
import verify_bug011_runtime as r
import verify_bug009_monitor_input as m
b=root/'build'; rom=b/'ladybug.rom'; resident=(b/'ladybug-runtime.rom').read_bytes()
s=r.symbols(b/'ladybug.map')
enemy=(b/'ladybug-enemy-runtime.rom').read_bytes()
es=r.symbols(b/'ladybug-enemy-runtime.map'); stage=es['fri_stage_background']
e={'rom_sha256':hashlib.sha256(rom.read_bytes()).hexdigest(),'phase':'natural demo normal gameplay foreground','deadline_seconds':45,'success_marker':'120 complete main_game_tick_normal to mainloop worklists','timeout_meaning':'sample window incomplete; no target-speed inference','target_cycles':27000,'samples':[]}
p,c=r.launch_fast(m,Path('/mnt/e/projects/ladybug/docs/reference/xroar/src/xroar'),rom)
def go(addr):
 ids=m.setup(c,[addr])
 try:
  c.call('run'); hit=c.call('wait_for_stop',{'timeout_ms':10000},timeout=12)
  assert hit.get('pc')==addr and hit.get('reason')=='breakpoint',hit
 finally:m.clear(c,ids)
try:
 go(s['main_game_tick_normal'])
 for label in ('main_game_tick_normal','mainloop'):
  a=s[label]; assert r.read_bytes(c,a,16)==resident[a-0xC000:a-0xC000+16],label
 deadline=time.monotonic()+45
 for i in range(120):
  assert time.monotonic()<deadline
  if i:go(s['main_game_tick_normal'])
  owner=r.read_byte(c,0x90); start=c.call('read_cycles')['cpu_cycles']
  ids=m.setup(c,[s['mainloop'],stage]); stage_count=0
  try:
   for _ in range(4):
    c.call('run'); hit=c.call('wait_for_stop',{'timeout_ms':10000},timeout=12)
    assert hit.get('reason')=='breakpoint',hit
    if hit['pc']==s['mainloop']:break
    assert hit['pc']==stage,hit
    assert r.read_bytes(c,stage,16)==enemy[stage-0x800:stage-0x800+16]
    stage_count+=1
   else:raise AssertionError('foreground return absent')
  finally:m.clear(c,ids)
  elapsed=c.call('read_cycles')['cpu_cycles']-start
  e['samples'].append({'index':i,'back_owner':owner,'stage_rebuild_calls':stage_count,'cycles':elapsed})
 e['maximum_cycles']=max(x['cycles'] for x in e['samples'])
 e['steady_maximum_cycles']=max(x['cycles'] for x in e['samples'] if not x['stage_rebuild_calls'])
 e['stage_maximum_cycles']=max(x['cycles'] for x in e['samples'] if x['stage_rebuild_calls'])
 e['steady_target_pass']=e['steady_maximum_cycles']<=27000
 e['all_worklists_target_pass']=e['maximum_cycles']<=27000
 e['result']='pass' if e['all_worklists_target_pass'] else 'target_missed'
except Exception as exc:e['result']='fail';e['failure']=f'{type(exc).__name__}: {exc}'
finally:c.close();m.stop(p);(b/'bug044-foreground-cycles.json').write_text(json.dumps(e,indent=2)+'\n')
print({k:v for k,v in e.items() if k!='samples'})
if e['result']!='pass':raise SystemExit(1)
