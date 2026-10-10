from runtime import *
def test(q):
 identity=q.start();samples=[]
 active=(B/'ladybug-adaptive-active.bin').read_bytes()
 assert q.phys(0x38*8192+0x38f,len(active))==active
 def measured(label,n=12):
  for _ in range(n):
   q.go('AD_WORK_EXEC')
   before={'popup':q.val('PICKUP_TIMER'),'anim':q.val('ENEMY_ANIM'),'enemy_timer':q.val('ENEMY_TIMER'),'owner':q.val('FB_BACK_ID'),'pose':q.pose(),'frame':int.from_bytes(q.low('FRAMES',2),'big')}
   ticks=q.c.call('read_cycles')['event_ticks'];q.go()
   cycles=(q.c.call('read_cycles')['event_ticks']-ticks)//8
   samples.append({'phase':label,'before':before,'cycles':cycles,'anim_after':q.val('ENEMY_ANIM'),'pending_after':q.val('FB_RENDER_PENDING')})
 q.key(0);measured('ordinary north input',12)
 q.key(None);q.wait(lambda:q.val('JOY_DIR')==255,'neutral input')
 q.dp('BOX_TIMER',[1,91]);q.wait(lambda:q.phys(0x34*8192+0x476,1)==b'\x01','ordinary enemy release/exit')
 q.dp('PICKUP_TIMER',[30]);q.dp('RENDER_FLAGS2',[q.val('RENDER_FLAGS2')|1]);q.dp('ENEMY_TIMER',[1])
 measured('one roaming enemy plus popup and nest animation',32)
 maxima={s['phase']:max(x['cycles'] for x in samples if x['phase']==s['phase']) for s in samples}
 return {'identity':identity,'clock_unit':'raw event_ticks/8, current fast-CPU calibration','measurement':'AD_WORK_EXEC entry to mainloop return; sampled maxima, includes interrupts during work, excludes prior SYNC','samples':samples,'maxima':maxima,'target_cycles':27000,'target_met':all(v<=27000 for v in maxima.values())}
receipt(os.environ.get('LADYBUG_TEST_OUTPUT','worklists-current.json'),test)
