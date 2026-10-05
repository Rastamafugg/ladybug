"""Legal arrival fixtures for current GDB adapter; never writes PC or clocks."""
def plan(maze,entities,actors):
 assert len(actors)==32 and len(entities)%4==0
 targets=[];used=set()
 for slot in (2,3):
  assert actors[slot*8]==(slot<<4)|1,'release-created actor type missing'
  candidates=[]
  for off in range(0,len(entities),4):
   tx,ty,kind=entities[off:off+3]
   if kind!=1 or off//4 in used:continue
   for direction,(dx,dy) in enumerate(((0,-1),(1,0),(0,1),(-1,0))):
    px,py=tx-dx,ty-dy
    if not(0<=px<24 and 0<=py<24 and 0<=tx<24 and 0<=ty<24):continue
    nav=maze['maze_nav'];gates=maze['gate_owner']
    if not(nav[py][px]&(1<<direction) and nav[ty][tx]&(1<<((direction+2)&3)) and gates[py][px]==gates[ty][tx]==0):continue
    center=0x57ec+(px-12)*4+(py-12)*4*320
    stride=(-320,1,320,-1)[direction];pointer=center+3*stride
    assert pointer+stride==0x57ec+(tx-12)*4+(ty-12)*4*320
    assert 0x2000<=pointer<0x9800
    candidates.append({'slot':slot,'entity_index':off//4,'target':[tx,ty],'predecessor':[px,py],'record':bytes(((slot<<4)|1,pointer>>8,pointer&255,3,px,py,0,direction)).hex()})
  assert candidates,'no distinct ungated runtime skull arrival'
  targets.append(candidates[0]);used.add(candidates[0]['entity_index'])
 safe=None
 for y in range(23,-1,-1):
  for x in range(23,-1,-1):
   if maze['maze_nav'][y][x]&15 and maze['gate_owner'][y][x]==0 and all(abs(x-p['predecessor'][0])+abs(y-p['predecessor'][1])>=6 for p in targets):
    safe=[x,y];break
  if safe:break
 assert safe,'safe neutral player cell unavailable'
 sx,sy=safe;pointer=0x2000+(sy*8-8)*160+(sx+7)*4
 return {'actors':targets,'safe_player':safe,'player_pointer':pointer,'limits':'Legal one-edge rare-path setup; not a natural earned skull approach. Preserve release-created actor type and all cursor/pending/deadline/clock values.'}
