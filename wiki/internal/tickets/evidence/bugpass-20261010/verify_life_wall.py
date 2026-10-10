from runtime import *
def test(q):
 q.capture_audio=True;identity=q.start();assert len(q.cues)==1,q.cues
 def cue():return q.phys(0x3d*8192+q.au['audio_slot0']-0xa000,1)[0]
 def wall():
  fb=q.fb();pixels=b''.join(fb[y*160+52:y*160+56] for y in(136,137));assert pixels==b'\0'*8,pixels.hex()
  return {'front':q.val('FB_FRONT_ID'),'removed_pixels':16,'region':pixels.hex(),'frame':int.from_bytes(q.low('FRAMES',2),'big')}
 walls=[wall()];tune_states=[]
 q.wait(lambda:cue()==255,'initial tune completion');assert len(q.cues)==1,q.cues
 def contact():
  fb=q.low('PLAYER_FB',2);xy=q.low('PLAYER_CELL_X',2)
  q.put(0x34*8192+0x470,bytes([1,*fb,0,*xy,1,255]))
 contact();q.wait(lambda:q.val('DEATH_STATE')!=0,'real enemy contact')
 q.wait(lambda:q.val('INITIAL_ENTRY_STATE')==4 and q.val('DEATH_STATE')==0,'replacement maze entry')
 assert cue()==6 and len(q.cues)==2,(cue(),q.cues)
 q.wait(lambda:q.val('INITIAL_ENTRY_STATE')==0,'replacement control');walls.append(wall())
 q.wait(lambda:cue()==255,'replacement tune completion');assert len(q.cues)==2
 # Stage alone must not create a new-life tune or consume a reserve.
 lives=q.val('LIVES');q.dp('STAGE_PENDING',[1]);q.wait(lambda:q.val('PRES_MODE')==6,'stage-only panel')
 q.wait(lambda:q.val('PRES_MODE')==0,'stage-only gameplay');assert len(q.cues)==2 and q.val('LIVES')==lives
 walls.append(wall())
 # Final death uses real contact and full death timing; rare reserve state only.
 q.dp('LIVES',[0]);contact();q.wait(lambda:q.val('DEATH_STATE')!=0,'final contact')
 q.wait(lambda:q.val('PRES_MODE')==7,'final game over');assert len(q.cues)==2,q.cues
 return {'identity':identity,'cue6_admissions':q.cues,'initial_and_replacement_tunes_completed':True,'stage_only_admissions':0,'final_death_admissions':0,'wall_live_samples':walls,'natural_path':'cold attract, coin, start, full first/replacement entry and real enemy contacts; stage flag and final reserve forced for rare paths'}
receipt(os.environ.get('LADYBUG_TEST_OUTPUT','life-wall-current.json'),test)
