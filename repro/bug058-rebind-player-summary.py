from pathlib import Path
import json,statistics,hashlib,collections
root=Path('E:/projects/ladybug');r=root/'repro';w=Path('C:/Users/19029/.codex/worktrees/bug-046-word-carryover/ladybug');b=w/'build'
load=lambda n:json.loads((r/n).read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
oracle=load('bug058-rebind-player-oracle-20260927.json');cross=load('bug058-rebind-crossover-20260927.json');startup=load('bug058-rebind-startup-20260927.json');profile=load('bug058-rebind-profile-20260927.json');before=load('bug058-rebind-profile-before-20260927.json')
assert all(x['result']=='pass' for x in (oracle,cross,startup)) and profile['result']=='captured'
stats=lambda rows:dict(samples=len(rows),minimum=min(rows),mean=statistics.mean(rows),maximum=max(rows))
colour={}
for k,pred in [('both',27),('high_only',23),('low_only',7),('neither',3)]:
 selected=[x for x in oracle['colour_cases'] if ('both' if x['value']&0x30 and x['value']&3 else 'high_only' if x['value']&0x30 else 'low_only' if x['value']&3 else 'neither')==k]
 savings=[x['reference']-x['candidate'] for x in selected];assert set(savings)=={pred}
 colour[k]=dict(cases=len(selected),saving=savings[0],reference_cycles=stats([x['reference'] for x in selected]),candidate_cycles=stats([x['candidate'] for x in selected]))
quiet=[x for x in profile['samples'] if x['requested_count']==4][-16:]
assert len(quiet)==16 and all(x['active']==4 and x['death']==0 and 5 not in x['audio_before']['slots']+x['audio_after']['slots'] and len(x['restore_calls'])==4 and len(x['decode_calls'])==5 for x in quiet)
music=lambda s:5 in s['audio_before']['slots']+s['audio_after']['slots']
summary={'ticket':'BUG-058','scope':'Approved local existing-table cache rebinding and fixed-offset full player restoration; full enemy drawing cadence retained; not production integration or parent timing acceptance.','source_baseline':'codex/bug058-restore 9b3b326','baseline_rom_sha256':before['rom_sha256'],'candidate_rom_sha256':sha(b/'ladybug.rom'),'units':'Calibrated fast CPU cycles = event_ticks/8; timing values are observed minima/means/maxima over bounded fixtures, not worst-case bounds.','phase_deadline_seconds':45,'targets':{'rebind_207_pair_saving':3000,'full_player_restore_saving':140,'overall_worklist':27000},'colour_oracle':{'result':oracle['result'],'cases':len(oracle['colour_cases']),'table_bytes':52,'index_domain':'cached value AND $33; existing table only','classes':colour,'caller_live':'A/B/X/Y/U/S/DP match reference; replicated OBJ_VALUE retained. CC and transient OBJ_PRIMARY are scratch at the caller.'},'player_oracle':{'result':oracle['result'],'full_cases':oracle['player_cases'],'adjacent_visible_cases':oracle['visible_player_cases'],'exact':'128 output bytes, untouched surroundings/source, final registers including CC, zero counters/validity; zero/one/fifteen-row wrappers unchanged.'},'render_crossover':{'result':cross['result'],'cases':len(cross['cases']),'counts':sorted(set(x['count'] for x in cross['cases'])),'owners_secondary':sorted(set(x['owner_metadata'] for x in cross['cases'])),'pixels_and_page34':'Every framebuffer byte and every bank-$34 state/cache/header/mask/tail byte equal from identical starting state; reference/candidate order reversed each case.','cases':cross['cases'],'rebind_passes':cross['rebind_passes']},'natural_startup':startup,'profile':{'result':profile['result'],'worklists':len(profile['samples']),'fixture':'Parked player [2,22], two skull entity records cleared, early existing releases. Real movement/render/audio; not natural moving-player or skull-death acceptance.','counts':{},'four_enemy_phases':{}},'capacity':{'resident_used':8168,'resident_limit':8192,'resident_free':24,'resident_delta':-2,'assets_used':7648,'assets_limit':7680,'enemy_used':4091,'enemy_limit':4096,'presentation_used':1273,'presentation_limit':1280,'copied_audio_used':734,'copied_audio_limit':920,'banked_audio_used':5675,'banked_audio_limit':8192,'cold_used':14362,'cold_limit':16384,'cartridge_source_free':413,'limits_changed':False},'verification_mechanics':['First full build reached ROM generation then rejected non-adjacent table-use annotation and undeclared sequential scratch alias; corrected audit declarations.','Second full build rejected an audit input modified after build began; froze inputs and reran complete build. No rejected runtime result is discarded.'],'retained_trace_receipts':{},'commands':{'build':'scripts/build.sh build','oracle':'python3 repro/bug058-rebind-player-oracle.py WORKTREE OUTPUT_JSON','crossover':'python3 repro/bug058-rebind-crossover-20260927.py WORKTREE OUTPUT_JSON WORKTREE rebind-before rebind-candidate --resident-pair --force-colour --cleared-skulls --park-far --no-live-collectibles --measure-rebind','startup':'python3 repro/bug058-nest-startup-20260927.py WORKTREE OUTPUT_JSON','profile':'python3 repro/bug058-full-cadence-profiler.py WORKTREE OUTPUT_JSON --release-window --renderer-costs --capture-paths --two-step --steady-decode --cleared-skulls --park-far --park-other-corner --four-render-profile --colour-pairs'}}
for n in range(5):summary['profile']['counts'][str(n)]=stats([s['cycles'] for s in profile['samples'] if s['requested_count']==n])
four=[s for s in profile['samples'] if s['requested_count']==4]
for name,rows in [('release_music',[s for s in four if music(s)]),('post_music',quiet)]:
 summary['profile']['four_enemy_phases'][name]=dict(**stats([s['cycles'] for s in rows]),over_target=sum(s['cycles']>27000 for s in rows))
baseline_quiet=[s for s in before['samples'] if s['requested_count']==4 and not music(s)]
summary['profile']['baseline_post_music_incomplete']=stats([s['cycles'] for s in baseline_quiet])
assert before['park_cell']==profile['park_cell']==[2,2] and before['result']=='fail' and before['unindexed_stream_identity']['death_state']==1 and len(baseline_quiet)==11
death_identity={k:v for k,v in before['unindexed_stream_identity'].items() if k!='enemy_table'}
summary['profile']['baseline_comparison_gate']={'result':'fail','missing_quiet_samples':5,'failure':before['failure'],'validated_death_stream':death_identity,'interpretation':'Eleven quiet samples, then confirmed pre-existing death path; no complete aggregate before/after improvement claim. Local causal savings established by same-state renderer crossovers. Raw enemy-table diagnostic read through unverified PAR5 is excluded from interpretation.'}
summary['profile']['fixture']='Parked player [2,2], two skull entity records cleared, early existing releases. Movement/render/audio/collision code unchanged; not natural moving-player or skull-death acceptance.'
summary['profile']['park_cell']=profile['park_cell']
summary['commands']['profile']=summary['commands']['profile'].replace('--park-far --park-other-corner','--park-upper-left')
summary['profile']['matching_ordered_state_samples']=sum(a['requested_count']==z['requested_count'] and a['index']==z['index'] and a['state']==z['state'] for a,z in zip(before['samples'],profile['samples']))
summary['profile']['comparison_limit']='Aggregate profile differences describe bounded observations. Same-state render crossover establishes local causal savings; framebuffer owner does not establish causality.'
summary['profile']['quiet_player_restore_segment']=stats([next(t for k,t in s['marks'] if k=='acr_enemies')-next(t for k,t in s['marks'] if k=='actor_closure_restore') for s in quiet])
summary['colour_oracle']['no_rebind_cases']=oracle['no_rebind_cases']
summary['render_crossover']['complete_rebind_return_boundary']='Complete call includes final five-cycle return; earlier 24111-cycle observation ended before it. Matched complete call is 24116 -> 20427.'
summary['verification_mechanics'].append('First crossover reached its unchanged 45-second count boundary after seven passing cases because it repeated isolated rebind measurement in every case. Removed duplicate measurements: twenty isolated passes remain alongside all forty renderer cases; deterministic rerun passes without changing the deadline.')
summary['verification_mechanics'].append('First aggregate profile at parked [2,22] stopped at four-enemy index52 with pointer $D715 outside the sprite catalogue (built death-frame address). No live stream-byte identity was retained in that failed attempt, so its cause is not established. Reassessed the fixture; added live-byte diagnostics and used legal parked [2,2], completing candidate profile. Baseline upper-left profile fails at four-enemy index93: live death-frame bytes match artifact and DEATH_STATE=1. Eleven baseline quiet samples retained, five missing; aggregate before/after comparison fails. Stopped further fixture probing and reassessed: no production change or corruption established; existing isolated exact-state proof establishes local savings. Movement/collision code was not modified.')
summary['empty_collectible_transition']='439 -> 467 cycles, 28 setup cycles added when no live collectible pairs remain; unchanged-colour and unknown-cache early exits have zero delta.'
for n in ('bug058-rebind-player-oracle-20260927.json','bug058-rebind-crossover-20260927.json','bug058-rebind-crossover-timeout-20260927.json','bug058-rebind-startup-20260927.json','bug058-rebind-profile-20260927.json','bug058-rebind-profile-before-20260927.json','bug058-rebind-profile-fixture-failure-20260927.json','bug058-rebind-player-build-20260927.log'):
 p=r/n;summary['retained_trace_receipts'][n]=dict(sha256=sha(p),bytes=p.stat().st_size)
summary['local_fit_result']='pass';summary['overall_27000_result']='fail';summary['residual']='Natural moving-player four-enemy check remains; BUG-058 stays Proposed and is not Done.'
for case in summary['render_crossover']['cases']:
 case['render_intents_hex']=bytes(case.pop('render_intents')).hex()
 case['pending_intents_before_hex']=bytes(case.pop('pending_intents_before')).hex()
groups={}
for case in summary['render_crossover'].pop('rebind_passes'):
 key=(case['pairs'],case['skipped'])
 if key not in groups:groups[key]={'comparisons':0,'pairs':case['pairs'],'skipped':case['skipped'],'owners_secondary':set(),'counts':set(),'primary_classes':case['primary_classes'],'reference_cycles':case['reference_cycles'],'candidate_cycles':case['candidate_cycles'],'saving':case['saving']}
 group=groups[key];assert all(group[k]==case[k] for k in ('primary_classes','reference_cycles','candidate_cycles','saving'))
 group['comparisons']+=1;group['owners_secondary'].add(case['owner_metadata']);group['counts'].add(case['count'])
for group in groups.values():group['owners_secondary']=sorted(group['owners_secondary']);group['counts']=sorted(group['counts'])
summary['render_crossover']['rebind_groups']=list(groups.values())
previous=r/'bug058-rebind-player-summary-20260927.json'
if previous.exists():
 old=load(previous.name)
 for key in ('fit_commit','ownership_audit'):
  if key in old:summary[key]=old[key]
failures=[]
for name in ('bug058-rebind-profile-fixture-failure-20260927.json','bug058-rebind-profile-before-20260927.json'):
 raw=load(name);failures.append({k:v for k,v in raw.items() if k!='samples'})
 failures[-1]['completed_worklists']=len(raw['samples'])
(r/'bug058-rebind-profile-failures-20260927.json').write_text(json.dumps(failures,indent=2)+'\n')
(r/'bug058-rebind-player-summary-20260927.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps({k:summary[k] for k in ('candidate_rom_sha256','capacity','profile','local_fit_result','overall_27000_result')},indent=2))
