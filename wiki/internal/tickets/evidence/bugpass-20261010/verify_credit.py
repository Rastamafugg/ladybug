from runtime import *
def test(q):
 q.capture_audio=True;identity=q.start()
 def voices():return list(q.phys(0x3d*8192+q.au['audio_slot0']-0xa000,112)[::28])
 q.wait(lambda:voices()[0]==255,'initial tune complete before coin control')
 before=q.val(0xa8);q.c.call('inject_key',{'key':5,'action':'press'})
 q.wait(lambda:q.val(0xa8)==before+1,'live coin admitted')
 q.c.call('inject_key',{'key':5,'action':'release'})
 q.wait(lambda:12 in voices(),'credit voice12 sounded');active=voices()
 q.wait(lambda:12 not in voices(),'credit voice12 completed')
 assert len(q.cues)==1,q.cues
 return {'identity':identity,'credits_before':before,'credits_after':q.val(0xa8),'active_voice_ids':active,'credit_cue_completed':True,'extra_life_music_admissions':0,'initial_cue6_admissions':q.cues}
receipt(os.environ.get('LADYBUG_TEST_OUTPUT','credit-current.json'),test)
