import json,sys,collections
from pathlib import Path
w=Path('/mnt/c/Users/19029/.codex/worktrees/bug-046-word-carryover/ladybug');sys.path.insert(0,str(w/'scripts'));import verify_bug011_runtime as r
es=r.symbols(w/'build/ladybug-enemy-runtime.map');ms=r.symbols(w/'build/ladybug.map');d=json.loads(Path('/mnt/e/projects/ladybug/repro/bug058-cadence-state-20260927.json').read_text());old=json.loads(Path('/mnt/e/projects/ladybug/repro/bug058-mask-release-20260927.json').read_text());assert [(s['cycles'],s['state']) for s in d['samples']]==[(s['cycles'],s['state']) for s in old['samples']]
def ptr(rec):return rec[1]*256+rec[2]
def box(fb):
 y,x=divmod(fb-0x2000,160);return (x,y,x+8,y+16)
def union(a,b):return (min(a[0],b[0]),min(a[1],b[1]),max(a[2],b[2]),max(a[3],b[3]))
def overlap(a,b):return a[0]<b[2] and b[0]<a[2] and a[1]<b[3] and b[1]<a[3]
pairing=int(sys.argv[1]) if len(sys.argv)>1 else 0
groups=[([0,1],[2,3]),([0,2],[1,3]),([0,3],[1,2])][pairing]
records=lambda v:[tuple(v[i:i+8]) for i in range(0,32,8)]
owners={};target=None;phase=0;rows=[]
for row in [s for s in d['samples'] if s['requested_count']==4]:
 st=row['cadence_state'];owner=st['back_owner'];logical=records(st['enemies']);prior=owners.get(owner,records(st['owner_enemies']));why=[]
 if target is None or owner not in owners:why.append('initialize')
 if any(not q[0] or not q[6] for q in logical):why.append('nest-or-inactive')
 if target is None:target=list(logical)
 candidate=list(target)
 if phase%2==0:
  for slot in (groups[0] if phase==0 else groups[1]):candidate[slot]=logical[slot]
 pbox=union(box(st['player_fb']),box(st['owner_player_fb']))
 boxes=[union(box(ptr(a)),box(ptr(b))) for a,b in zip(prior,candidate)]+[pbox]
 pairs=[(i,j) for i in range(5) for j in range(i+1,5) if overlap(boxes[i],boxes[j])]
 # Pair overlap is handled by selective transitive closure below.
 for intent in [st['intents'],st['pending']]:
  if intent[0]&(es['RF_ENTITIES']|es['RF_DOT']|es['RF_STAGE']) or intent[1]&es['RF2_COLOUR'] or intent[8]&(es['ERF_INIT']|es['ERF_ZONE_REFRESH']|es['ERF_NEST']|es['ERF_NEST_ANIM']) or intent[9] or intent[11]:why.append('background');break
 if why:
  if 'initialize' in why or 'nest-or-inactive' in why:candidate=list(logical)
  selected=list(range(4))
 else:
  selected=[i for i in range(4) if candidate[i]!=prior[i] or overlap(boxes[i],pbox)]
  while True:
   added=[j for j in range(4) if j not in selected and any(overlap(boxes[i],box(ptr(prior[j]))) for i in selected)]
   if not added:break
   selected+=added
  selected.sort()
 assert all(candidate[i]==prior[i] for i in range(4) if i not in selected),'unpublished pose change'
 assert all(not overlap(boxes[i],box(ptr(prior[j]))) for i in selected for j in range(4) if j not in selected),'missed closure'
 assert logical==records(st['enemies']),'logic mutated'

 target=candidate;owners[owner]=list(candidate);phase=(phase+1)%4
 rows.append({'index':row['index'],'owner':owner,'selected':selected,'fallback':why,'overlaps':pairs})
print('steady',rows[-16:]);print('counts',collections.Counter(len(x['selected']) for x in rows[-16:]));print('reasons',collections.Counter(z for x in rows[-16:] for z in x['fallback']))
Path('/mnt/e/projects/ladybug/repro/bug058-cadence-selective-model-'+str(pairing)+'-20260927.json').write_text(json.dumps({'rom_sha256':d['rom_sha256'],'model':'Selective transitive closure plus global background fallback; exact host AABBs; positions only, animation omitted, therefore optimistic selection count','rows':rows,'steady':rows[-16:]},indent=2)+'\n')
