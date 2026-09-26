from pathlib import Path
import hashlib,json,sys,time
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'scripts'))
import verify_bug011_runtime as runtime
import verify_bug009_monitor_input as monitor
build=root/'build'; rom=build/'ladybug.rom'
ps=runtime.symbols(build/'ladybug-presentation-runtime.map')
aus=runtime.symbols(build/'ladybug-audio-runtime.map')
audio=(build/'ladybug-audio-runtime.bin').read_bytes()
module=(build/'ladybug-presentation-runtime.bin').read_bytes()
record={'ticket':'BUG-043','rom_sha256':hashlib.sha256(rom.read_bytes()).hexdigest(),'deadline_per_phase_seconds':45,'timeout_meaning':'named state or cue admission/completion not observed within the bounded phase','pending_address':'02DD','gateway_range':'02DE-02EF (18 bytes)','phases':[],'audio_and_key_scan_cycles':[]}
process,client=runtime.launch_fast(monitor,Path('/mnt/e/projects/ladybug/docs/reference/xroar/src/xroar'),rom)
ids=[]
def physical(addr,n):
 return bytes.fromhex(client.call('read_memory',{'space':'physical','addr':addr,'length':n})['data'])
def low(addr,n=1): return physical(0x38*8192+addr,n)
def state():
 return {'mode':low(0xA5)[0],'credits':low(0xA8)[0],'pending':low(0x02DD)[0],'overflow':low(0xEF)[0],'event':low(0xA9)[0],'slots':[physical(0x3D*8192+aus[f'audio_slot{i}']-0xA000,1)[0] for i in range(4)]}
def until(label,predicate):
 deadline=time.monotonic()+45; observations=[]; prior=None; slice_start=None
 while time.monotonic()<deadline:
  hit=client.run_to_breakpoint(min(10,max(.1,deadline-time.monotonic())))
  if hit['pc']==ps['pft_helper_ready']:
   slice_start=client.call('read_cycles')['cpu_cycles']; continue
  assert hit['pc']==ps['pft_ready'],hit
  if slice_start is not None:
   record['audio_and_key_scan_cycles'].append({'phase':label,'cycles':client.call('read_cycles')['cpu_cycles']-slice_start}); slice_start=None
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
 key(5,'press'); until('first accepted credit and cue 12',lambda s:s['credits']==1 and 12 in s['slots'])
 key(5,'release'); until('first cue completes and high score holds',lambda s:s['mode']==5 and 12 not in s['slots'] and s['pending']==0)
 key(5,'press'); key(6,'press')
 until('simultaneous pair counted separately',lambda s:s['credits']==3 and s['pending']==1 and 12 in s['slots'])
 key(5,'release'); key(6,'release')
 until('second simultaneous cue admitted',lambda s:s['credits']==3 and s['pending']==0 and 12 in s['slots'])
 last=until('simultaneous cues finish',lambda s:s['credits']==3 and s['pending']==0 and 12 not in s['slots'])
 assert last['overflow']==0
 record['gateway_still_exact']=low(0x02DE,18)==audio[offset:offset+18]
 assert record['gateway_still_exact']
 # Force the independent FIFO-full boundary at the post-scan input marker.
 key(5,'press');key(6,'press')
 until('two new edges sampled before forced FIFO-full admission',lambda s:s['event']==6)
 client.call('write_memory',{'space':'physical','addr':0x38*8192+0xEC,'data':'00000400'})
 client.call('write_memory',{'space':'physical','addr':0x38*8192+0xF1,'data':'0600060006000600'})
 assert low(0xEE)[0]==4
 until('full FIFO preserves both credit requests',lambda s:s['credits']==5 and s['pending']==1 and 12 in s['slots'])
 key(5,'release');key(6,'release')
 until('full FIFO second credit cue admitted',lambda s:s['credits']==5 and s['pending']==0 and 12 in s['slots'])
 last=until('full FIFO credit pair completes',lambda s:s['mode']==5 and s['pending']==0 and 12 not in s['slots'] and 6 not in s['slots'])
 assert last['overflow']==0
 key(1,'press')
 until('natural player-one start consumes one credit',lambda s:s['credits']==4 and s['mode']==6)
 key(1,'release')
 until('natural level start delivers cue 6',lambda s:s['mode']==0 and 6 in s['slots'])
 until('level-start cue finishes in gameplay',lambda s:s['mode']==0 and 6 not in s['slots'])
 record['gateway_after_gameplay_exact']=low(0x02DE,18)==audio[offset:offset+18]
 assert record['gateway_after_gameplay_exact']
 record['result']='pass'
except Exception as e: record['result']='fail';record['failure']=f'{type(e).__name__}: {e}'
finally:
 client.close();monitor.stop(process)
 (root/'repro/bug043-banked-audio-current-20260926.json').write_text(json.dumps(record,indent=2)+'\n')
print({k:v for k,v in record.items() if k not in ('phases','audio_and_key_scan_cycles')}); print('cycles',len(record['audio_and_key_scan_cycles']),max((v['cycles'] for v in record['audio_and_key_scan_cycles']),default=0))
if record['result']!='pass': raise SystemExit(1)
