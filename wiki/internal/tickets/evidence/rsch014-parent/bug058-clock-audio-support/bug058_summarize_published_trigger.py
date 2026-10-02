from pathlib import Path
import json,hashlib
root=Path('/mnt/e/projects/ladybug')
actors=['player',*[f'enemy{i}' for i in range(4)]]
def xy(p):y,x=divmod(p-0x2000,160);return 2*x,y
def distance(a,b):return sum(abs(x-y) for x,y in zip(xy(a),xy(b)))
out={'date':'2026-10-02','units':'Pixel distances are Manhattan net origin displacement between published frames; raw interval is IRQ Vbord count; independent event ticks measure emulator time.',
 'aggregation':'Single controlled streams; reported maxima are observed eligible adjacent-pair maxima, not whole-game bounds.',
 'eligibility':'Both full opaque sprite templates match at ledger origins and neither endpoint overlaps another actor. First placement interval excluded. Hidden or occluded positions are not passing evidence.',
 'runs':{},'limitations':['Null audio backend.','Controlled legal pickup/gate setup and extra enemy releases follow natural cold demo/credited gameplay.','Pickup player is stationary after completion; gate scenario supplies moving-player proof.','Gate scenario leaves two enemy slots occluded; pickup supplies all-four eligible enemy motion evidence.','No physical hardware or all-gameplay-path guarantee.']}
for variant,file in [('baseline','bug058-published-baseline.json'),('full_candidate','bug058-published-full-cap.json')]:
 path=root/'repro'/file;d=json.loads(path.read_text());assert d['status']=='scoped-pass'
 result={'rom_sha256':d['rom_sha256'],'trace_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'identity':d['identity'],'scenarios':[]}
 for case in d['pickup_gate_cadence']:
  rows=case['worklists'];scenario={'name':case['name'],'worklists':len(rows),'max_logical_steps':max(x['steps'] for x in rows),'max_debt_after':max(x['debt_after'] for x in rows),'owner_values':sorted({x['published_front']['owner_secondary'] for x in rows}),'actors':{},'excluded_initial_placement_pairs':1}
  for name in actors:
   pairs=[];missing=0;occluded=0;unmatched=0
   for index,(a,b) in enumerate(zip(rows,rows[1:])):
    if index==0:continue
    pa,pb=a['published_front'],b['published_front']
    aa=next((z for z in pa['actors'] if z['name']==name),None);bb=next((z for z in pb['actors'] if z['name']==name),None)
    if not aa or not bb:missing+=1;continue
    if aa['overlap'] or bb['overlap']:occluded+=1;continue
    if not aa['opaque_pixels_match'] or not bb['opaque_pixels_match']:unmatched+=1;continue
    pair={'index':index,'pixels':distance(aa['pointer'],bb['pointer']),'raw_ticks':(pb['raw']-pa['raw'])&65535,'event_ticks':pb['independent_event_ticks']-pa['independent_event_ticks'],'commit_delta':(pb['commit']-pa['commit'])&65535,'from_pointer':aa['pointer'],'to_pointer':bb['pointer'],'frame_sha256':[pa['frame_sha256'],pb['frame_sha256']]}
    assert pair['commit_delta']==1,'capture skipped a publication'
    pairs.append(pair)
   row={'eligible_pairs':len(pairs),'occluded_pairs':occluded,'unmatched_pairs':unmatched,'missing_pairs':missing,'max_pixels':max([x['pixels'] for x in pairs] or [0]),'travel_pixels':sum(x['pixels'] for x in pairs),'raw_ticks_for_eligible_pairs':sum(x['raw_ticks'] for x in pairs),'peak_pair':max(pairs,key=lambda x:x['pixels']) if pairs else None}
   if variant=='full_candidate':assert all(x['pixels']<=2 for x in pairs),(case['name'],name,row)
   scenario['actors'][name]=row
  result['scenarios'].append(scenario)
 if variant=='baseline':
  pickup,gate=result['scenarios']
  assert all(pickup['actors'][name]['max_pixels']==4 for name in actors[1:])
  assert gate['actors']['player']['max_pixels']==4
 else:
  pickup,gate=result['scenarios']
  assert all(pickup['actors'][name]['eligible_pairs']>=2 and pickup['actors'][name]['max_pixels']<=2 for name in actors[1:])
  assert gate['actors']['player']['eligible_pairs']>=2 and gate['actors']['player']['max_pixels']==2
  assert all(c['max_logical_steps']<=2 and c['max_debt_after']==0 for c in result['scenarios'])
 out['runs'][variant]=result
out['limitations'].append('Baseline and candidate are independently initialized controlled streams, not identical RAM fixtures; logical-total differences illustrate the policy tradeoff and are not matched render-cost or exact wall-time measurements.')
out['verdict']='Scoped current full-candidate published motion preparation passes; clock policy remains unapproved.'
(root/'repro/bug058-published-motion-summary.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:[(c['name'],{a:v['max_pixels'] for a,v in c['actors'].items()}) for c in v['scenarios']] for k,v in out['runs'].items()}))
