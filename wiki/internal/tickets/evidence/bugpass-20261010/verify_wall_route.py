from runtime import *
from collections import deque
def test(q):
 identity=q.start();nav=r.read_bytes(q.c,q.ms['maze_nav'],576)
 before=q.fb();visits=[]
 def walk(goal):
  start=tuple(q.pose()[:2]);todo=deque([start]);paths={start:[]}
  while todo:
   x,y=todo.popleft()
   if (x,y)==goal:break
   for d,(dx,dy) in enumerate(((0,-1),(1,0),(0,1),(-1,0))):
    nx,ny=x+dx,y+dy
    if 0<=nx<24 and 0<=ny<24 and nav[ny*24+nx]&(1<<((d+2)%4)) and (nx,ny) not in paths:
     paths[nx,ny]=paths[x,y]+[(d,(nx,ny))];todo.append((nx,ny))
  assert goal in paths,('route absent',goal)
  for d,target in paths[goal]:
   q.key(d);q.wait(lambda:tuple(q.pose()[:2])==target and q.val('PLAYER_STEP')==0,'wall passage '+str(target));q.key(None);visits.append(target)
 def strip(fb,x):return b''.join(fb[y*160+x//2:y*160+x//2+4] for y in(136,137))
 assert strip(before,104)==b'\0'*8
 adjacent=strip(before,96);assert adjacent==b'D'*8,adjacent.hex()
 walk((6,18));walk((6,14));q.key(None)
 receipts=[]
 for _ in range(8):
  q.go();fb=q.fb();assert strip(fb,104)==b'\0'*8;assert strip(fb,96)==adjacent
  receipts.append({'owner':q.val('FB_FRONT_ID'),'corrected':strip(fb,104).hex(),'adjacent':strip(fb,96).hex()})
 return {'identity':identity,'natural_visits':visits,'target_anchor':[6,18],'northward_exit':[6,14],'post_player_restore':receipts,'adjacent_wall_preserved':True}
receipt('wall-route-current.json',test)
