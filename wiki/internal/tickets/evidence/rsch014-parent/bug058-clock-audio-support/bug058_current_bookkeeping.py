"""Reuse bookkeeping harness pattern on current core; synthetic callbacks only."""
import sys,json,time
from pathlib import Path
sys.path.insert(0,'/mnt/e/projects/ladybug/scripts')
import verify_bug011_runtime as r
import verify_bug009_monitor_input as m
root=Path('/mnt/e/projects/ladybug');b=root/'worktrees/perf008-readiness/repro/perf008-execution/default-build'
ms=r.symbols(b/'ladybug.map');mapped=(b/'ladybug-adaptive-mapped.bin').read_bytes()
banked=(root/'repro/bug058-catchup-banked-fit.bin').read_bytes();S=0xBD24;RET=0x18FC
assert len(mapped)==198 and len(banked)==696
e={'phase':'isolated current fitted clock core with synthetic tick callback','deadline_seconds':45,
 'success_marker':'component calls return to $18FC with asserted clock, barrier and history state',
 'timeout_meaning':'component marker absent, not gameplay slowdown','rom_sha256':r.digest((b/'ladybug.rom').read_bytes()),
 'mapped_sha256':r.digest(mapped),'banked_sha256':r.digest(banked),'cases':[],
 'limitations':['Synthetic callbacks; no published pixels, movement, audio or full candidate ROM acceptance.'],'status':'incomplete'}
p,c=r.launch_fast(m,root/'docs/reference/xroar/src/xroar',b/'ladybug.rom');deadline=time.monotonic()+45
def read(a,n=1):return r.read_bytes(c,a,n)
def write(a,v):c.call('write_memory',{'addr':a,'data':bytes(v).hex()})
def word(a,v):write(a,(v&65535).to_bytes(2,'big'))
def call(a):
 assert time.monotonic()<deadline,'45-second phase deadline'
 if a==0xBD47:write(S+8,read(2,2)) # Active driver owns AD_BEGIN snapshot.
 write(0x1EFC,[RET>>8,RET&255]);c.call('write_registers',{'pc':a,'s':0x1EFC,'dp':0,'cc':0x50})
 ids=m.setup(c,[RET]);start=c.call('read_cycles')['event_ticks']
 try:
  c.call('run');h=c.call('wait_for_stop',{'timeout_ms':5000},timeout=6);assert h.get('pc')==RET,h
 finally:m.clear(c,ids)
 delta=c.call('read_cycles')['event_ticks']-start;assert delta%8==0
 return delta//8,c.call('read_registers')
def reset(raw=1000,callback=b'\x4f\x39'):
 word(2,raw);write(0x91,[0]);word(0x92,0);write(0xA5,[0]);write(0x392,callback);call(0xBD44)
def state():return {'sim':int.from_bytes(read(S+2,2),'big'),'debt':int.from_bytes(read(S+4,2),'big'),'counts':list(read(S+20,2)),'barrier':read(S+19)[0],'fault':read(S+22)[0]}
try:
 ids=m.setup(c,[ms['mainloop']]);c.call('run');h=c.call('wait_for_stop',{'timeout_ms':10000},timeout=12);m.clear(c,ids)
 assert h.get('pc')==ms['mainloop'],h
 runtime=(b/'ladybug-runtime.rom').read_bytes();a=ms['mainloop'];assert read(a,16)==runtime[a-0xC000:a-0xC000+16]
 write(0xFFA5,[0x34]);write(0x9FD,mapped);write(0xBD44,banked);write(RET,[0x20,0xFE])
 assert read(0x9FD,198)==mapped and read(0xBD44,696)==banked
 e['identity']={'resident_marker_equal':True,'explicitly_staged_mapped_equal':True,'explicitly_staged_candidate_equal':True,'tick_callback_address':0x392}
 for elapsed in range(9):
  reset();word(2,1000+elapsed);cycles,regs=call(0xBD47);s=state();expected=min(elapsed,2)
  assert s['sim']==expected and s['counts']==[expected]*2 and s['debt']==0 and not s['fault'],s
  e['cases'].append({'name':'nominal or late elapsed batch','elapsed_raw_ticks':elapsed,'cycles':cycles,**s})
 reset();word(2,1002);write(0x91,[1]);before=read(0xBC04,288);_,regs=call(0xBD47)
 assert read(0xBC04,288)==before and state()['counts']==[0,0] and not regs['cc']&1
 write(0x91,[0]);call(0xBD47);assert state()['sim']==2
 e['cases'].append({'name':'pending publication blocks then admits two ticks',**state()})
 reset(0xFFFF);word(2,1);call(0xBD47);assert state()['sim']==2 and state()['debt']==0
 e['cases'].append({'name':'16-bit clock wrap',**state()})
 reset();word(S+4,0xFFFE);word(2,1005);call(0xBD47);assert state()['fault']&1 and state()['counts']==[0,0]
 call(0xBD47);assert state()['counts']==[0,0]
 e['cases'].append({'name':'debt overflow fails closed',**state()})
 reset();write(S+20,[8,8]);before=read(0xBC04,288);_,regs=call(0xBD4A)
 assert regs['cc']&1 and read(0xBC04,288)==before and state()['counts']==[8,8]
 e['cases'].append({'name':'full journal refuses ninth record',**state()})
 for name,stub in [('transient barrier',bytes.fromhex('860139')),('phase transition',bytes.fromhex('860197a54f39'))]:
  reset(callback=stub);word(2,1004);call(0xBD47);assert state()['sim']==1 and state()['debt']==0 and state()['barrier']==1
  call(0xBD47);assert state()['sim']==1
  word(0x92,1);word(2,1005);call(0xBD47);assert state()['sim']==2 and state()['debt']==0
  e['cases'].append({'name':name+' waits for commit then resumes',**state()})
 e['status']='scoped-pass'
except Exception as exc:e['failure']=repr(exc);raise
finally:
 r.stop(p);(root/'repro/bug058-current-bookkeeping.json').write_text(json.dumps(e,indent=2)+'\n')
