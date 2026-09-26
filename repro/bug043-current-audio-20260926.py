from pathlib import Path
import hashlib,json,sys,time
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'scripts'))
import verify_bug011_runtime as runtime
import verify_bug009_monitor_input as monitor
build=root/'build'; rom=build/'ladybug.rom'
ps=runtime.symbols(build/'ladybug-presentation-runtime.map')
aus=runtime.symbols(build/'ladybug-audio-runtime.map')
ms=runtime.symbols(build/'ladybug.map')
audio=(build/'ladybug-audio-runtime.bin').read_bytes()
module=(build/'ladybug-presentation-runtime.bin').read_bytes()
resident=(build/'ladybug-runtime.rom').read_bytes()
record={'rom_sha256':hashlib.sha256(rom.read_bytes()).hexdigest(),'deadline_per_phase_seconds':45,'timeout_meaning':'named state or cue admission/completion not observed within the bounded phase; timeout does not establish slow target execution','phases':[],'demo_service_samples':[]}
process,client=runtime.launch_fast(monitor,Path('/mnt/e/projects/ladybug/docs/reference/xroar/src/xroar'),rom)
ids=[]
def physical(addr,n):
 return bytes.fromhex(client.call('read_memory',{'space':'physical','addr':addr,'length':n})['data'])
def low(addr,n=1): return physical(0x38*8192+addr,n)
def audio_slots():
 result=[]
 for i in range(4):
  offset=aus[f'audio_slot{i}']-0xA000
  data=physical(0x3D*8192+offset,6)
  result.append({'id':data[0],'wait':data[3],'stream':int.from_bytes(data[4:6],'big')})
 return result
def state():
 return {'mode':low(0xA5)[0],'screen':low(0xA6)[0],'credits':low(0xA8)[0],'pending':low(0x02DD)[0],'last_mode':low(0x02DC)[0],'overflow':low(0xEF)[0],'event':low(0xA9)[0],'slots':[slot['id'] for slot in audio_slots()]}
def until(label,predicate):
 deadline=time.monotonic()+45; observations=[]; prior=None
 while time.monotonic()<deadline:
  hit=client.run_to_breakpoint(min(10,max(.1,deadline-time.monotonic())))
  if hit['pc']==ps['pft_helper_ready']:
   continue
  assert hit['pc']==ps['pft_ready'],hit
  s=state()
  if s!=prior: observations.append(s); prior=s
  if predicate(s):
   record['phases'].append({'name':label,'observations':observations,'result':'pass'}); return s
 raise TimeoutError(label)
def key(k,action): client.call('inject_key',{'key':k,'action':action})
try:
 ids=monitor.setup(client,[ps['presentation_flow_tick']]); hit=client.run_to_breakpoint(40)
 assert hit['pc']==ps['presentation_flow_tick']
 record['presentation_live_exact']=runtime.read_bytes(client,0x1900,len(module))==module
 record['staged_audio_exact']=physical(0x3D*8192,len(audio))==audio
 assert record['presentation_live_exact'] and record['staged_audio_exact']
 monitor.clear(client,ids);ids=monitor.setup(client,[ps['pft_ready']])
 until('natural attract',lambda s:s['mode']==2)
 offset=aus['audio_service_gateway_bytes']-0xA000
 record['gateway_exact']=low(0x02DE,18)==audio[offset:offset+18]
 assert record['gateway_exact']

 # Reach demo naturally. Sample shared audio state at successive presentation
 # boundaries; the mainloop tail services audio between these observations.
 until('natural attract-to-demo handoff',lambda s:s['mode']==4)
 main=ms['mainloop']
 call_offset=resident[main-0xC000:main-0xC000+32].index(bytes.fromhex('bd1900'))
 ret=main+call_offset+3
 record['presentation_caller_return_pc']=ret
 record['presentation_caller_return_live_exact']=runtime.read_bytes(client,ret,2)==resident[ret-0xC000:ret-0xC000+2]
 assert record['presentation_caller_return_live_exact']
 demo_deadline=time.monotonic()+45
 for _ in range(12):
  hit=client.run_to_breakpoint(min(10,max(.1,demo_deadline-time.monotonic())))
  if hit['pc']==ps['pft_helper_ready']:
   hit=client.run_to_breakpoint(min(10,max(.1,demo_deadline-time.monotonic())))
  if hit['pc']!=ps['pft_ready']: raise AssertionError(f'demo presentation marker: {hit}')
  sample={'mode':low(0xA5)[0],'last_mode':low(0x02DC)[0],
          'frame':int.from_bytes(low(2,2),'big'),'slots':audio_slots()}
  record['demo_service_samples'].append(sample)
  if time.monotonic()>=demo_deadline: raise TimeoutError('demo cadence sample deadline')
 samples=record['demo_service_samples']
 assert all(s['mode']==4 and s['last_mode']==4 for s in samples)
 assert any(6 in [slot['id'] for slot in s['slots']] for s in samples)
 assert any(a['slots']!=b['slots'] for a,b in zip(samples,samples[1:]))
 frames=[s['frame'] for s in samples]
 assert ((frames[-1]-frames[0])&0xFFFF)>0
 record['demo_service_cadence']='pass: twelve mode-4 caller-return samples show cue 6 and advancing audio-slot state'
 monitor.clear(client,ids);ids=monitor.setup(client,[ps['pft_ready']])

 key(5,'press')
 until('demo credit pre-empts demo',lambda s:s['credits']==1 and s['screen']==3)
 key(5,'release')
 assert state()['mode']==1, 'credit entered high-score loading before load-preemption scenario'
 key(6,'press')
 until('credit edge sampled during high-score load',lambda s:s['mode']==1 and s['credits']==1 and (s['event']&0x06))
 key(6,'release')
 until('loading credit pre-emption accepted',lambda s:s['credits']==2 and s['screen']==3)
 first=until('loading credit cue sequence completes',lambda s:s['mode']==5 and s['credits']==2 and 12 not in s['slots'] and s['pending']==0)
 assert first['overflow']==0

 key(5,'press'); key(6,'press')
 until('simultaneous pair sampled',lambda s:s['credits']==2 and s['event']==6)
 until('simultaneous pair counted separately',lambda s:s['credits']==4 and s['pending']==1 and 12 in s['slots'])
 key(5,'release'); key(6,'release')
 last=until('simultaneous cues finish',lambda s:s['credits']==4 and s['pending']==0 and 12 not in s['slots'])
 assert last['overflow']==0
 record['gateway_still_exact']=low(0x02DE,18)==audio[offset:offset+18]
 assert record['gateway_still_exact']

 # Force the independent FIFO-full boundary at the post-scan input marker.
 key(5,'press');key(6,'press')
 until('two new edges sampled before forced FIFO-full admission',lambda s:s['event']==6 and s['credits']==4)
 client.call('write_memory',{'space':'physical','addr':0x38*8192+0xEC,'data':'00000400'})
 client.call('write_memory',{'space':'physical','addr':0x38*8192+0xF1,'data':'0600060006000600'})
 assert low(0xEE)[0]==4
 until('full FIFO preserves both credit requests',lambda s:s['credits']==6 and s['pending']==1 and 12 in s['slots'])
 key(5,'release');key(6,'release')
 until('full FIFO second credit cue admitted',lambda s:s['credits']==6 and s['pending']==0 and 12 in s['slots'])
 last=until('full FIFO credit pair completes',lambda s:s['mode']==5 and s['pending']==0 and 12 not in s['slots'] and 6 not in s['slots'])
 assert last['overflow']==0
 key(1,'press')
 until('natural player-one start consumes one credit',lambda s:s['credits']==5 and s['mode']==6)
 key(1,'release')
 until('natural level start delivers cue 6',lambda s:s['mode']==0 and 6 in s['slots'])
 until('level-start cue finishes in gameplay',lambda s:s['mode']==0 and 6 not in s['slots'])
 record['gateway_after_gameplay_exact']=low(0x02DE,18)==audio[offset:offset+18]
 assert record['gateway_after_gameplay_exact']

 # Force the rare game-over state from live play, then inject a real credit edge.
 client.call('write_memory',{'space':'physical','addr':0x38*8192+0x004D,'data':'04'})
 await_gameover=until('forced game-over screen published',lambda s:s['screen']==4 and s['mode']==7)
 record['gameover_entry']='forced DEATH_STATE=4 from live play; screen 4/mode 7 observed'
 key(5,'press')
 until('credit pre-empts game-over',lambda s:s['credits']==6 and s['screen']==3)
 key(5,'release')
 last=until('game-over pre-emption cue completes',lambda s:s['mode']==5 and s['pending']==0 and 12 not in s['slots'])
 assert last['overflow']==0
 record['gateway_after_gameover_exact']=low(0x02DE,18)==audio[offset:offset+18]
 assert record['gateway_after_gameover_exact']
 record['result']='pass'
except Exception as e: record['result']='fail';record['failure']=f'{type(e).__name__}: {e}'
finally:
 client.close();monitor.stop(process)
 (build/'bug043-current-audio-20260926.json').write_text(json.dumps(record,indent=2)+'\n')
print({k:v for k,v in record.items() if k not in ('phases','demo_service_samples')})
if record['result']!='pass': raise SystemExit(1)
