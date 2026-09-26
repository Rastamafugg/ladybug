from pathlib import Path
import sys
base=Path(__file__).with_name('bug037-audio-fit-20260926.py').read_text().split('\ntry:\n go(ps[')[0]
exec(compile(base,str(__file__),'exec'))
e['phase']='controlled full effect FIFO';e['success_marker']='gate/release/collectibles displace queued pellets; lower tick cannot displace them'
try:
 go(ps['pft_ready']);assert bankread('audio_engine_start',au['audio_engine_end']-0xa000)==artifact[:au['audio_engine_end']-0xa000]
 write(0xec,[0,0,0,0])
 for cue in [3,3,3,3,0,5,1,2]:call('audio_enqueue_impl',cue)
 queued=list(read(0xf1,8)[::2]);e['queued_after_high_events']=queued
 call('audio_enqueue_impl',4);after=list(read(0xf1,8)[::2]);e['queued_after_lower_tick']=after
 if '--expect-fixed' in sys.argv:assert queued==[0,5,1,2] and after==queued
 else:assert queued==[3,3,3,3]
 e['result']='pass';e['interpretation']='priority replacement verified' if '--expect-fixed' in sys.argv else 'higher-priority requests lost behind full pellet FIFO'
except Exception as exc:e['result']='fail';e['failure']=repr(exc)
finally:c.close();m.stop(p);out.write_text(json.dumps(e,indent=2)+'\n')
print(json.dumps(e,indent=2))
if e['result']!='pass':raise SystemExit(1)
