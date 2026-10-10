from runtime import *
from collections import deque
from build_screen import compile_player_sprites,compile_enemy_sprites
PLAYER=compile_player_sprites(ROOT/'assets/arcade/sprites.json')
ENEMY=compile_enemy_sprites(ROOT/'assets/arcade/sprites.json')
def matches(fb,p,frames,pens):
 def one(f):
  for y in range(16):
   for x in range(16):
    pen=(f[y*4+x//4]>>(6-2*(x%4)))&3
    if pen:
     off=p-0x2000+y*160+x//2
     if not(0<=off<len(fb)) or (fb[off]>>(4*(1-x%2)))&15!=pens[pen]:return False
  return True
 return any(one(f) for f in frames)
def route(q):
 nav=r.read_bytes(q.c,q.ms['maze_nav'],576);own=r.read_bytes(q.c,q.ms['maze_gate_owner'],576)
 records=q.phys(0x34*8192+0x380,q.val('ENTITY_COUNT')*4)
 types=(2,) if os.environ.get('LADYBUG_PICKUP_TYPE')=='heart' else (2,3)
 goals={(records[i],records[i+1]):i//4 for i in range(0,len(records),4) if records[i+2] in types}
 start=tuple(q.pose()[:2]);todo=deque([start]);paths={start:[]}
 while todo:
  x,y=todo.popleft()
  if (x,y) in goals:return paths[x,y],goals[x,y],records
  for d,(dx,dy) in enumerate(((0,-1),(1,0),(0,1),(-1,0))):
   nx,ny=x+dx,y+dy
   if not(0<=nx<24 and 0<=ny<24):continue
   if nav[ny*24+nx]&(1<<((d+2)%4)) and (nx,ny) not in paths:
    paths[nx,ny]=paths[x,y]+[(d,(nx,ny))];todo.append((nx,ny))
 raise AssertionError('natural collectible route missing')
def rect(fb,p,rows=16,width=8):
 off=p-0x2000
 return b''.join(fb[off+i*160:off+i*160+width] for i in range(rows))
def snapshot(q):
 rec=q.phys(0x34*8192+0x470,32);fb=q.fb()
 face=q.val('PLAYER_FACE');kind=rec[0]>>4;enemyface=rec[7]
 return {'pose':q.pose(),'enemies':list(rec),'box':list(q.low('BOX_TIMER',3)),'popup':q.val('PICKUP_TIMER'),'anim':q.val('ENEMY_ANIM'),'freeze':int.from_bytes(q.low('FREEZE_TIMER',2),'big'),'phase':list(q.low(0x29e,2)),'front':q.val('FB_FRONT_ID'),'pending':q.val('FB_RENDER_PENDING'),'stage':q.val('STAGE'),'stage_pending':q.val('STAGE_PENDING'),'mode':q.val('PRES_MODE'),'frame':int.from_bytes(q.low('FRAMES',2),'big'),'nest_hash':hashlib.sha256(rect(fb,0x4dec,32)).hexdigest(),'enemy_hash':hashlib.sha256(rect(fb,int.from_bytes(rec[1:3],'big'))).hexdigest() if rec[0] else None,'player_hash':hashlib.sha256(rect(fb,q.pose()[3]-800,21)).hexdigest(),'ladybug_matches':matches(fb,q.pose()[3],PLAYER[face*4:face*4+4],(0,12,5,2)),'enemy_matches':matches(fb,int.from_bytes(rec[1:3],'big'),ENEMY[kind*16+enemyface*4:kind*16+enemyface*4+4],(0,9,5,6)) if rec[0] and enemyface<4 else None}
def hold(q,onset,label,roamer=True):
 samples=[onset];end=time.monotonic()+45
 while time.monotonic()<end:
  q.go();s=snapshot(q);samples.append(s)
  assert s['pose']==onset['pose'],(label,'player movement',onset,s)
  assert s['enemies']==onset['enemies'],(label,'enemy movement',onset,s)
  assert s['box']==onset['box'],(label,'box movement',onset,s)
  assert s['mode']==0 and s['stage']==onset['stage'],(label,'early stage handoff',s)
  if s['popup']==0:break
 else:raise TimeoutError(label+' popup timer-to-zero')
 assert len({s['anim'] for s in samples})>=2,'animation counter missing transition'
 assert len({s['nest_hash'] for s in samples})>=2,'visible nest animation missing'
 if roamer:assert len({s['enemy_hash'] for s in samples})>=2,'visible roaming animation missing'
 assert all(s['phase']==onset['phase'] for s in samples),'movement fractional state advanced'
 if (B/'ladybug-adaptive-active.bin').exists():
  assert q.phys(0x34*8192+0x1d28,2)==b'\0\0','popup accumulated scheduler movement debt'
 # Capture restoration without another simulation tick by publication/IRQ boundary.
 q.go(0x1900)             # after IRQ publication, before presentation handoff
 restored=snapshot(q)
 assert restored['ladybug_matches'],(label,'restored Lady Bug pixels missing',restored)
 if roamer:assert any(s['enemy_matches'] for s in samples),'expected opaque roaming sprite missing'
 return {'label':label,'samples':samples,'restored':restored}
def test(q):
 identity=q.start();path,index,records=route(q);visited=[]
 # Natural mapped path, without teleporting player or collectible.
 goal=tuple(records[index*4:index*4+2]);onset_box=None
 for d,target in path:
  if target==goal:
   q.input_entry(d)
   end=time.monotonic()+45
   while q.val('PLAYER_STEP')!=3:
    assert time.monotonic()<end,'collection entry phase deadline'
    q.go('pt_done');q.go('player_tick')
   if os.environ.get('LADYBUG_FINAL_PICKUP')=='1':
    q.dp('DOTS_LEFT',[0]);q.dp('BONUS_LEFT',[1])
   onset_box=list(q.low('BOX_TIMER',3));q.go('pt_done');assert q.val('PICKUP_TIMER')==30
   q.go();assert list(q.low('BOX_TIMER',3))==onset_box,'perimeter moved on collection tick'
  else:
   q.key(d);q.wait(lambda:tuple(q.pose()[:2])==target and q.val('PLAYER_STEP')==0,'natural route cell '+str(target))
  q.key(None);visited.append(target)
  if q.val('PICKUP_TIMER') and target!=goal:q.wait(lambda:q.val('PICKUP_TIMER')==0,'intermediate collectible')
 assert q.val('PICKUP_TIMER')>0,'actual collectible did not create popup'
 natural_onset=snapshot(q)
 # Natural first collectible validates scoring/contact before forced rare cases.
 natural=hold(q,natural_onset,'natural collectible contact/pause/restoration',False)
 if os.environ.get('LADYBUG_FINAL_PICKUP')=='1':
  assert natural_onset['stage_pending']==1 and natural['restored']['stage_pending']==1
  assert natural['restored']['stage']==1 and natural['restored']['mode']==0
  q.wait(lambda:q.val('PRES_MODE')==6,'actual final collection stage panel')
  assert q.val('STAGE')==2
  return {'identity':identity,'natural_route':visited,'collectible_record':list(records[index*4:index*4+4]),'onset_box':onset_box,'holds':[natural],'stage_after':2,'forced_cases':'Only DOTS_LEFT=0 and BONUS_LEFT=1 before actual mapped-input collectible contact; real pickup creates popup and stage pending; no entity/player relocation or direct stage flag.'}
 resume_dir=(path[-1][0]+2)%4  # reverse through the naturally traversed passage
 q.input_entry(resume_dir);before=q.pose()[3];q.go('pt_done');resume_delta=q.pose()[3]-before
 assert resume_delta==(-320,1,320,-1)[resume_dir],'post-popup first step changed'
 q.key(None);q.wait(lambda:q.val('JOY_DIR')==255,'post-popup release')
 # Release an actual enemy through ordinary timer/spawner path, then let it exit.
 q.dp('BOX_TIMER',[1,91]);q.wait(lambda:q.phys(0x34*8192+0x476,1)==b'\x01','ordinary enemy release and roaming exit')
 if 'LADYBUG_POPUP_START_OWNER' in os.environ:
  owner=int(os.environ['LADYBUG_POPUP_START_OWNER']);q.wait(lambda:q.val('FB_FRONT_ID')==owner,'isolated popup starting owner '+str(owner))
 # Preserve actor caches; popup onset is forced only for animation/freeze rare tests.
 q.dp('PICKUP_TIMER',[30]);q.dp('RENDER_FLAGS2',[q.val('RENDER_FLAGS2')|1]);q.dp('ENEMY_TIMER',[1])
 q.dp('BOX_TIMER',[9]);onset=snapshot(q);motion=hold(q,onset,'roaming/nest animation during popup')
 assert motion['samples'][-1]['popup']==0
 # Existing vegetable-freeze clock must continue while popup holds movement.
 q.dp('PICKUP_TIMER',[30]);q.dp('RENDER_FLAGS2',[q.val('RENDER_FLAGS2')|1]);q.dp('FREEZE_TIMER',(120).to_bytes(2,'big'));q.dp('ENEMY_TIMER',[1])
 vegetable=hold(q,snapshot(q),'vegetable freeze overlaps popup')
 assert vegetable['samples'][-1]['freeze']<120
 # Final collectible flag must remain live until the restored-player publication.
 q.dp('PICKUP_TIMER',[30]);q.dp('RENDER_FLAGS2',[q.val('RENDER_FLAGS2')|1]);q.dp('ENEMY_TIMER',[1]);q.dp('STAGE_PENDING',[1]);oldstage=q.val('STAGE')
 final=hold(q,snapshot(q),'final collectible stage pending')
 q.wait(lambda:q.val('PRES_MODE')==6,'stage transition after popup restoration')
 assert q.val('STAGE')==oldstage+1
 return {'identity':identity,'natural_route':visited,'collectible_record':list(records[index*4:index*4+4]),'onset_box':onset_box,'natural_onset':natural_onset,'resume_direction':resume_dir,'resume_delta_bytes':resume_delta,'popup_end_debt_zero':(B/'ladybug-adaptive-active.bin').exists(),'isolated_popup_start_owner':onset['front'],'holds':[natural,motion,vegetable,final],'stage_after':q.val('STAGE'),'cue6_admissions':q.cues,'forced_cases':'ordinary timer wrap forces release; popup timers and final stage flag force rare overlap paths; natural collectible path precedes forcing'}
receipt(os.environ.get('LADYBUG_TEST_OUTPUT','pickup-current.json'),test)
