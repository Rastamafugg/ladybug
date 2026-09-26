from pathlib import Path
import sys
base=Path(__file__).with_name('bug037-audio-fit-20260926.py').read_text().split('\ntry:\n go(ps[')[0]
exec(compile(base,str(__file__),'exec'))
e['phase']='controlled name-event edges and two-owner timer replay';e['success_marker']='one cue per accepted length/END/publication edge, no duplicate on unchanged state'
try:
 go(ps['pft_ready']);assert bankread('audio_engine_start',au['audio_engine_end']-0xa000)==artifact[:au['audio_engine_end']-0xa000]
 write(0xa5,[8]);write(0xcb,[0]);write(0xe2,[0]);write(0xe1,[0]);bankwrite('audio_name_valid',[0]);call('audio_poll_name')
 write(0xcb,[1]);call('audio_poll_name');assert read(0xee)==bytes([1]);assert read(0xf1)==bytes([2]);call('audio_poll_name');assert read(0xee)==bytes([1])
 write(0xcb,[0]);call('audio_poll_name');assert bankread('audio_music_count')==bytes([1]);assert bankread('audio_music_queue')==bytes([9]);call('audio_poll_name');assert bankread('audio_music_count')==bytes([1]);e['accepted_add_clear_and_unchanged_length']=True
 bankwrite('audio_name_length',[7]);write(0xcb,[7]);call('audio_poll_name');assert read(0xee)==bytes([1]);e['full_name_no_length_change_no_cue']=True
 write(0xe2,[1]);call('audio_poll_name');assert bankread('audio_music_count')==bytes([2]);assert bankread('audio_music_queue',2)==bytes([9,8]);call('audio_poll_name');assert bankread('audio_music_count')==bytes([2]);e['END_once']=True
 write(0xe1,[128]);write(0x91,[1]);call('audio_poll_name');assert read(0xee)==bytes([1])
 write(0x91,[0]);call('audio_poll_name');assert read(0xee)==bytes([2]);assert read(0xf3)==bytes([4])
 write(0xe1,[129]);call('audio_poll_name');assert read(0xee)==bytes([2]);e['timer_first_visible_owner_once']=True
 write(0xe1,[4]);call('audio_poll_name');write(0xe1,[128]);call('audio_poll_name');assert read(0xee)==bytes([3]);e['next_timer_box_new_cue']=True
 before=bankread('audio_music_queue',8);result=call('',guard=True);assert result['a']==1 and bankread('audio_music_queue',8)==before;e['name_guard_queries_without_advancing']=True
 e['result']='pass'
except Exception as exc:e['result']='fail';e['failure']=repr(exc)
finally:c.close();m.stop(p);out.write_text(json.dumps(e,indent=2)+'\n')
print(json.dumps(e,indent=2))
if e['result']!='pass':raise SystemExit(1)
