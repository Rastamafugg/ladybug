from pathlib import Path
import sys
base=Path(__file__).with_name('bug037-audio-fit-20260926.py').read_text().split('\ntry:\n go(ps[')[0]
exec(compile(base,str(__file__),'exec'))
e['phase']='all sounded cue wait boundaries';e['success_marker']='runtime stream pointer changes at each encoded wait boundary and ends at authored duration';e['cues']=[]
try:
 go(ps['pft_ready']);assert bankread('audio_engine_start',au['audio_engine_end']-0xa000)==artifact[:au['audio_engine_end']-0xa000]
 for cue in range(16):
  for i in range(4):bankwrite('audio_slot'+str(i),[255])
  write(0xf9,[cue]);call('audio_admit')
  idx=next(i for i in range(4) if bankread('audio_slot'+str(i))[0]==cue);label='audio_slot'+str(idx)
  pointer=int.from_bytes(bankread(label,6)[4:6],'big');start_ptr=pointer;tick=0;expected=[]
  while True:
   cmd=artifact[pointer-0xa000];pointer+=1
   if cmd==0:break
   if cmd==2:
    wait=max(1,artifact[pointer-0xa000]);pointer+=1;expected.append((tick,pointer,wait));tick+=wait
   else:pointer+={16:3,17:3,18:3,28:2,29:1,30:1}[cmd]
  end_tick=tick;observed=[];previous=None;deadline=time.monotonic()+45
  for tick in range(end_tick+len(expected)+3):
   assert time.monotonic()<deadline,'cue phase deadline'
   call('audio_advance_all');state=bankread(label,6)
   if state[0]==255:
    actual_end=tick;break
   pointer=int.from_bytes(state[4:6],'big')
   if pointer!=previous:observed.append((tick,pointer,state[3]));previous=pointer
  else:raise AssertionError('stream did not finish')
  row={'cue':cue,'wait_boundaries':len(expected),'expected_end_tick':end_tick,'actual_end_tick':actual_end,'boundaries_match':observed==expected};e['cues'].append(row)
  if observed!=expected or actual_end!=end_tick:
   e['expected_boundaries']=expected;e['observed_boundaries']=observed;raise AssertionError(row)
 e['result']='pass'
except Exception as exc:e['result']='fail';e['failure']=repr(exc)
finally:c.close();m.stop(p);out.write_text(json.dumps(e,indent=2)+'\n')
print(json.dumps(e,indent=2))
if e['result']!='pass':raise SystemExit(1)
