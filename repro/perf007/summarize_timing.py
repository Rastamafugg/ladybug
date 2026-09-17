"""Offline attribution of bounded captures; explicit instruction-length call boundaries."""
import sys,re,json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
folder=Path(sys.argv[1]);report=json.loads((folder/'result.json').read_text())
def symbols(path):return {k:int(v,16) for k,v in re.findall(r'^Symbol: (\S+) .* = ([0-9A-Fa-f]+)$',path.read_text(),re.M)}
main=symbols(ROOT/'build/ladybug.map');enemy=symbols(ROOT/'build/ladybug-enemy-runtime.map')
entries={k:main[k] for k in ['erase_entity_footprints','repair_settled_entity_gates','draw_entities','draw_entity_object','cache_entity_overlay']}
entries.update({k:enemy[k] for k in ['compose_enemy_zone','roam_update_background','roam_copy_fb_to_bg','actor_closure_restore','actor_closure_draw']})
regex=re.compile(r'^([0-9a-f]{4})\| ([0-9a-f]+)\s+(\S+).* dt=(\d+)$')
for scenario in report['results']:
 rows=[]
 for line in (folder/(scenario['scenario']+'.trace')).read_text().splitlines():
  m=regex.match(line)
  if m:rows.append([int(m[1],16),len(m[2])//2,m[3],int(m[4])//8])
 if rows and rows[0][0]==0:rows[0][0]=enemy['frame_render_impl']
 starts=[i for i,x in enumerate(rows) if x[0]==enemy['frame_render_impl']]
 for n,interval in enumerate(scenario['intervals']):
  lo=starts[n];hi=starts[n+1] if n+1<len(starts) else len(rows)
  part=rows[lo:hi];pc=[x[0] for x in part];cost=[x[3] for x in part]
  attribution={}
  for name,address in entries.items():
   spans=[];unresolved=0
   for i,x in enumerate(part):
    if x[0]!=address:continue
    if i==0 or part[i-1][2] not in ('LBSR','BSR','JSR'):unresolved+=1;continue
    ret=part[i-1][0]+part[i-1][1]
    try:end=pc.index(ret,i+1)
    except ValueError:unresolved+=1;continue
    spans.append(sum(cost[i-1:end]))
   attribution[name]={'bounded_calls':len(spans),'inclusive_cycles':sum(spans),'call_cycles':spans,'unresolved_entries':unresolved}
  interval['routine_attribution']=attribution
  interval['missed_commit_entries']=pc.count(enemy['fbiq_missed'])
  interval['front_write_fault_entries']=pc.count(enemy['fbp_write_front_fault'])
report['attribution_rule']='Inclusive call costs include call instruction and nested work; do not sum nested routines. Return address decoded from actual trace instruction byte length. Unresolved entries not assigned cycles.'
report['fixture_roaming_capture_coverage']='No rub_full or roam_copy_fb_to_bg entries observed; four-enemy recapture cost not measured.'
report['hardware_target_cycles']=29666
report['observed_active_max_cycles']=max(i['active_cycles'] for s in report['results'] for i in s['intervals'])
report['meets_active_interval_target']=report['observed_active_max_cycles']<=29666
(folder/'attribution.json').write_text(json.dumps(report,indent=2)+'\n')
for scenario in report['results']:
 for i in scenario['intervals'][:2]:
  print(scenario['scenario'],i['sequence_index'],i['active_cycles'],{k:v['inclusive_cycles'] for k,v in i['routine_attribution'].items()},'missed',i['missed_commit_entries'])
