import json
from pathlib import Path
r=json.loads(Path('repro/bug050-half-rate-window-audit-20260925.json').read_text())
rows=[]
for e in r['events']:
 t=e['current_motion_tick']; q,off=divmod(t-1,90);colour,within=divmod(off,30);motion=1+q*96+colour*32+within
 first=motion+(motion%2==0);pickup=first+2*(e['distance_packed_bytes']-1)+1
 expected=2 if e['index']<5 else 1 if e['index']<12 else 3
 observed=((pickup-1)//32)%3+1
 rows.append({'index':e['index'],'name':e['name'],'old_start':t,'new_start':motion,'new_pickup':pickup,'distance_pixels':2*e['distance_packed_bytes'],'expected_colour':expected if e['index']<15 else None,'pickup_colour':observed,'pass':e['index']==15 or observed==expected,'frames_from_start_through_pickup':pickup-motion+1})
assert all(x['pass'] for x in rows)
fixed=[e['name'] for e in r['events'][:15] if ((e['earliest_full_arrival_consume_tick']-1)//32)%3+1 != (2 if e['index']<5 else 1 if e['index']<12 else 3)]
receipt={'kind':'deterministic schedule calculation, not a current-ROM runtime test','baseline':'bug050-half-rate-window-audit-20260925.json; preserved authored colour-cycle index and within-colour movement offset','uniform_dwell_frames':32,'full_cycle_frames':96,'colour_sensitive_events_passed':15,'skull_collision_not_colour_sensitive':True,'fixed_absolute_timestamp_colour_mismatches':fixed,'events':rows}
Path('build/bug050-uniform32-audit.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt,indent=2))
