from runtime import *
def test(q):
 identity=q.start();samples=[]
 # Real mapped input; only coherent position/direction is forced at natural call entry.
 for old,want,step in [(0,3,1),(0,3,2),(0,3,3),(2,1,3)]:
  q.input_entry(want);q.fixture(12,16 if old==0 else 15,old,step)
  before=q.pose();ticks=q.c.call('read_cycles')['event_ticks'];q.go('pt_done');after=q.pose()
  cycles=(q.c.call('read_cycles')['event_ticks']-ticks)//8
  assert cycles<=27000,cycles
  assert before==after,(before,after)
  assert q.val('PLAYER_FACE')==want and q.val('TURN_SNAP')==0
  q.go('player_tick');q.go('pt_done');assert q.pose()==before
  q.key(None);q.wait(lambda:q.val('JOY_DIR')==255,'neutral input');assert q.pose()==before
  q.input_entry(old);resume=q.pose();q.go('pt_done')
  delta=q.pose()[3]-resume[3];assert delta==(-320 if old==0 else 320),delta
  samples.append({'old':old,'request':want,'offset_pixels':2*step,'held_pose':before,'resume_delta_bytes':delta,'player_call_cycles':cycles})
 # Six-pixel legal corner, with no gate owner, selected from authored reciprocal nav.
 nav=r.read_bytes(q.c,q.ms['maze_nav'],576)
 owners=r.read_bytes(q.c,q.ms['maze_gate_owner'],576)
 x,y=next((x,y) for y in range(3,22) for x in range(3,21) if nav[(y-1)*24+x]&4 and nav[y*24+x+1]&8 and not owners[(y-1)*24+x] and not owners[y*24+x+1])
 q.input_entry(0);q.fixture(x,y,1,3);q.go('pt_done');assert q.val('TURN_SNAP')==3
 anchor=0x2000+(y*8-7)*160+(x*4+28)
 for _ in range(3):q.go('player_tick');q.go('pt_done')
 assert q.val('TURN_SNAP')==0 and q.pose()[3]==anchor-960,q.pose()
 corner={'cell':[x,y],'admitted_snap_pixels':6,'final_delta_bytes':q.pose()[3]-anchor}
 # Existing horizontal gate end push. Preserve can_move admission/rotation.
 gates=r.read_bytes(q.c,q.ms['maze_gates'],60)
 gx,gy,initial=gates[:3];q.put(0x34*8192+0x240,[0])
 q.input_entry(0);q.fixture(gx-1,gy+1,1,1);q.go('pt_done')
 assert q.val('TURN_SNAP')==1 and q.phys(0x34*8192+0x240,1)==b'\x01'
 return {'identity':identity,'blocked_cases':samples,'legal_corner':corner,'gate_rotation':{'gate':0,'state':1,'admitted':True},'cue6_admissions':q.cues,'natural_path':'cold attract, coin, start, full life entry and real held/released arrow input'}
receipt(os.environ.get('LADYBUG_TEST_OUTPUT','movement-current.json'),test)
