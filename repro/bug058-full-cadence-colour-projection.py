from pathlib import Path
import json,hashlib,re
root=Path('E:/projects/ladybug');p=root/'repro/bug058-full-cadence-profile-colour-20260927.json';d=json.loads(p.read_text());summary_path=root/'repro/bug058-full-cadence-profile-summary-20260927.json';out=json.loads(summary_path.read_text())
assert d['result']=='captured'
table=[(0xF0 if not i&0x30 else 0)|(0x0F if not i&3 else 0) for i in range(52)]
w=Path('C:/Users/19029/.codex/worktrees/bug-046-word-carryover/ladybug')
map_text=(w/'build/ladybug.map').read_text()
match=re.search(r'Symbol: primary_preserve_table .* = ([0-9A-Fa-f]+)',map_text)
assert match
address=int(match.group(1),16);resident=(w/'build/ladybug-runtime.rom').read_bytes()
assert resident[address-0xC000:address-0xC000+52]==bytes(table)
for value in range(256):
    for colour in [1,2,3]:
        expected=(value&0xCC)|((colour<<4) if value&0x30 else 0)|(colour if value&3 else 0)
        projected=(value&0xCC)|((~table[value&0x33]&255)&(colour*17))
        assert projected==expected
out['component_overlap_note']='Actor restore contains player restore and enemy restore calls. Sprite decode is contained in enemy/player drawing, not an additional independent component.'
out['existing_table_artifact']={'address':address,'bytes':52,'sha256':hashlib.sha256(bytes(table)).hexdigest(),'domain':'A AND $33, maximum51; compiled bytes match declared presence-mask rule. This is an authored/built check, not a live or new-kernel proof.'}
out['colour_trace']={'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size,'worklists':len(d['samples']),'matches_first_profile':True}
out['four_colour_events']=[]
for s in d['samples']:
    if s['requested_count']!=4:continue
    for c in s.get('colour_pair_calls',[]):
        end_name='secc_done' if c['mode']=='rebind' else 'de_colour_done'
        end=next(t for n,t in s['marks'] if n==end_name and t>c['entry'])
        item={'sample':s['index'],'mode':c['mode'],'pairs':c['pairs'],'classes':c['primary_classes'],'elapsed_to_return':end-c['entry']}
        if c['mode']=='rebind':
            counts=c['primary_classes'];item['projected_kernel_saving']=counts['both']*27+counts['high_only']*23+counts['low_only']*7+counts['neither']*3-28
        out['four_colour_events'].append(item)
out['proposals']={'rebind_lookup':{'status':'Proposed architecture; no assembly fit/runtime implementation performed','class':'High-risk: shared sparse cache and scratch/register lifetimes, persistent A/B consumers, hard memory limits','files':['src/main.s','source-contract/ownership mirrors'],'change':'Reuse primary_preserve_table to classify presence of high/low primary colour nibbles. Initialize replicated BONUS_COLOR in OBJ_VALUE and table base in Y once per actual cache rebind; keep OBJ_ACCENT negative and existing iteration. Preserve accent bits with value AND $CC, combine replicated colour through inverse presence mask.','logical_cases_passed':768,'expected_kernel_bytes':[36,18],'expected_added_setup_bytes':16,'expected_net_resident_byte_delta':-2,'estimated_kernel_cycles':{'current_both':67,'current_high_only':63,'current_low_only':47,'current_neither':43,'proposed':40,'extra_setup_per_pass':28},'projected_saving_current_rebind':3689,'baseline_current_rebind_cycles':out['four_colour_events'][0]['elapsed_to_return'],'target':'At least 3000 calibrated cycles saved on matched 207-pair rebinding; no ordinary no-rebind slowdown; exact full cache values, masks, headers, tail bytes and framebuffer pixels; unchanged limits. Not a whole BUG-058 timing pass.','risks':'OBJ_VALUE becomes replicated-colour scratch for the negative pass only; positive replay still owns and rewrites OBJ_VALUE per pair. Y must remain live through the negative loop and IRQ. No new storage, cache format or table/index domain. Flags are undefined at kernel interface but caller-live state must be checked. Assembler relaxation/packing and ownership annotations must verify the projected fit.','order':'Approve local fit, then exhaustive 256 values x3 colours and clobber checks, exact cache/renderer same-state comparisons with both owners and delayed replay, natural demo/game startup, matched colour transition timing, complete build. No source changes before approval.','exclusions':'No recolour scheduling change, new table, raw stream packing change, sprite cadence reduction, loader relocation, missing-gate waiver or production integration.'},'player_restore':{'status':'Separate Proposed local fit; no implementation','class':'High-risk: retained player background and address/pointer equivalence under persistent rendering','files':['src/main.s restore_player'],'change':'Extend existing fixed-offset enemy-store pattern to the full sixteen-row player restore: stores at X+0,+2,+4,+6 and one row advance of160, instead of four X+2 stores and final152. U pull order and validity/counter remain unchanged.','baseline_observed_full_restore_segment_cycles':1209,'projected_saving_per_full_restore':144,'projected_byte_delta':0,'target':'At least140 calibrated cycles saved for full restore; exact128 output bytes and final registers/live flags/pointers; unchanged capacity, owner history, clipped path and gameplay. Full worklists still exceed27000.','order':'Approve independent fit; use exact restored baseline, full/clipped player and both-owner renderer oracle, natural startup and matched four-enemy worklist timings; full build.','risks':'Intermediate X differs during a row; IRQ must preserve interrupted registers and avoid this scratch. Verify source/destination non-aliasing and wrapper side effects.','exclusions':'No player capture change, clipped-loop rewrite, sprite decoding change or skip policy.'}}
out['larger_steady_limits']='Partial decoder commands dominate the measured command count (1553 partial runs across 80 framebuffer sprite calls). A new partial1 fast path is not assumed beneficial: added dispatch can outweigh saved loop control. Phases2/6 retain indirect row dispatch, but no pre-table room remains; local specialization needs a separately proven capacity design. Neither is implemented or accepted.'
out['proposals']['rebind_lookup']['order']='Approval for isolated local fit; complete dependent build before any integrated runtime probe; exhaustive 256 values x3 colours and caller-live state checks; exact whole-cache and both-owner/framebuffer crossovers including delayed replay; natural demo/game startup and matched transition/no-transition timing. No raw module swaps or production integration.'
out['proposals']['player_restore']['order']='Independent fitting approval; complete build first, then exact full/clipped player and both-owner renderer oracle, natural startup and matched four-enemy worklists. No new drawing policy.'
summary_path.write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out['four_colour_events'],indent=2))
