from pathlib import Path
import json,statistics,collections,hashlib
root=Path('E:/projects/ladybug');p=root/'repro/bug058-full-cadence-profile-matched-20260927.json';d=json.loads(p.read_text());old=json.loads((root/'repro/bug058-mask-release-20260927.json').read_text())
assert d['result']=='captured'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
stats=lambda a:dict(samples=len(a),minimum=min(a),mean=statistics.mean(a),maximum=max(a)) if a else None
def has_music(s):return 5 in s['audio_before']['slots']+s['audio_after']['slots']
four=[s for s in d['samples'] if s['requested_count']==4];quiet=four[-16:]
assert len(quiet)==16 and all(not has_music(s) and s['active']==4 and s['death']==0 and len(s['restore_calls'])==4 and len(s['decode_calls'])==5 for s in quiet)
out={'ticket':'BUG-058','source_revision':'codex/bug058-restore 9b3b326','rom_sha256':d['rom_sha256'],'scope':'Read-only profiling, all four enemies restored/captured/drawn each worklist. Parked player at [2,22]; two skull entity records cleared; release routine called early. Not natural moving-player or skull-death acceptance.','units':'Calibrated elapsed fast cycles: event_ticks / 8. Means/minima/maxima are bounded observations, not worst-case bounds. Owner recorded only as secondary metadata.','target':27000,'trace_sha256':sha(p),'trace_bytes':p.stat().st_size,'worklists':len(d['samples']),'counts':{},'four_enemy_phases':{},'quiet_components':{},'restore_phases':{},'decoder_mix':{},'captured_paths':{},'historical_comparison':{},'mechanic_failures':['Old harness assumed active count equals saved-background restore count on newly released actors; fixed to count old-valid slots.','WSL Python lacks int.bit_count; replaced with bin(...).count.','First fixture allowed enemy skull death; corrected to established cleared-skull fixture.','First far-corner selection was [22,22], reached player contact and an unsupported death stream; corrected to established [2,22] fixture.','Stage decoder symbol aliases an internal delta loop; do not interpret each stop there as a new decoder call. Unique framebuffer entry is used for final mix.']}
for n in range(5):out['counts'][str(n)]=stats([s['cycles'] for s in d['samples'] if s['requested_count']==n])
for name,rows in [('release_music',[s for s in four if has_music(s)]),('post_music',quiet)]:
    out['four_enemy_phases'][name]={**stats([s['cycles'] for s in rows]),'over_target':sum(s['cycles']>27000 for s in rows)}
for s in quiet:
    first=lambda n:next(v for k,v in s['marks'] if k==n)
    components={'preparation':first('actor_closure_restore')-first('framebuffer_prepare_back'),'actor_restore':first('framebuffer_queue_damage')-first('actor_closure_restore'),'player_restore':first('acr_enemies')-first('actor_closure_restore'),'enemy_restore_calls':sum(c['cycles_to_caller_next'] for c in s['restore_calls']),'capture':first('acd_draw_loop')-first('acd_save_loop'),'enemy_draw':first('acd_death')-first('acd_draw_loop'),'player_draw':first('framebuffer_finish_back')-first('acd_normal_player'),'background':sum(c['cycles_to_return'] for c in s['background_calls']),'audio_tail':first('mainloop')-first('main_entry_audio'),'sprite_decode':sum(c['cycles_to_epilogue'] for c in s['decode_calls'])}
    for k,v in components.items():out['quiet_components'].setdefault(k,[]).append(v)
    for c in s['restore_calls']:
        key=str(c['column_phase']);out['restore_phases'].setdefault(key,[]).append(c['cycles_to_caller_next'])
    for c in s.get('capture_calls',[]):out['captured_paths'][c['executed_path'] if 'executed_path' in c else c['selected_reason']]=out['captured_paths'].get(c['executed_path'] if 'executed_path' in c else c['selected_reason'],0)+1
    for c in s['decode_calls']:
        for k,v in c['mix'].items():out['decoder_mix'][k]=out['decoder_mix'].get(k,0)+v
out['quiet_components']={k:stats(v) for k,v in out['quiet_components'].items()}
out['restore_phases']={k:stats(v) for k,v in out['restore_phases'].items()}
comparable=list(zip(old['samples'],d['samples']));out['historical_comparison']={'same_sample_count':len(old['samples'])==len(d['samples']),'matching_count_index_state_totals':sum((a['requested_count'],a['index'],a['state'],a['cycles'])==(b['requested_count'],b['index'],b['state'],b['cycles']) for a,b in comparable),'pairs':len(comparable),'limit':'No speedup experiment; restored ROM is unchanged. Instrumentation may expose a different boundary; compare observations without owner attribution.'}
out['quiet_failing_rows']=[{'index':s['index'],'owner_secondary':s['front'],'cycles':s['cycles'],'background_cycles':sum(c['cycles_to_return'] for c in s['background_calls']),'restore_phases':[c['column_phase'] for c in s['restore_calls']]} for s in quiet]
(root/'repro/bug058-full-cadence-profile-summary-20260927.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k not in ['quiet_failing_rows','mechanic_failures']},indent=2))
