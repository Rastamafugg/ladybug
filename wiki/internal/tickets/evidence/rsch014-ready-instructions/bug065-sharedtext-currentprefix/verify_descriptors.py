import hashlib, json, re
from pathlib import Path
root=Path(__file__).resolve().parents[2]
out=root/'repro'/'bug065-sharedtext-currentprefix'
freeze=json.loads((out/'source-freeze.json').read_text())
baseline=json.loads((out/'pre-change-baseline.json').read_text())
receipt_path=root/'build'/'source-build-receipt.json'
receipt=json.loads(receipt_path.read_text())
def sha(data): return hashlib.sha256(data).hexdigest()
def parse_values(text,label,end):
    section=text.split('\n'+label+'\n',1)[1].split('\n'+end+'\n',1)[0]
    values=[]
    for line in section.splitlines():
        if 'fcb' not in line: continue
        for token in line.split('fcb',1)[1].split(';')[0].split(','):
            token=token.strip()
            if token: values.append(int(token[1:],16) if token.startswith('$') else int(token))
    return bytes(values)
source_hashes=freeze['input_sha256']
candidate_patch=out/'bug065-currentprefix-candidate.patch'
if sha(candidate_patch.read_bytes())!=freeze['candidate_patch_sha256']:
    raise SystemExit('candidate source patch hash differs from the frozen receipt')
current={}
for directory in ('src','scripts','assets','tiled'):
    for path in sorted((root/directory).rglob('*')):
        if path.is_file() and '__pycache__' not in path.parts and path.suffix!='.pyc':
            current[path.relative_to(root).as_posix()]=sha(path.read_bytes())
if current!=source_hashes: raise SystemExit('source/map hashes differ from pre-build freeze')
if receipt.get('state')!='complete' or receipt.get('profile')!='complete' or receipt['inputs']!=source_hashes:
    raise SystemExit('current build receipt does not qualify the frozen complete-profile inputs')
for name,digest in receipt['artifacts'].items():
    path=root/'build'/name
    if not path.is_file() or sha(path.read_bytes())!=digest: raise SystemExit('build output hash mismatch: '+name)
joy={arg.split('=',1)[1] for invocation in receipt['invocations'] for arg in invocation.get('arguments',[]) if arg.startswith('-DINPUT_JOYSTICK=')}
if joy!={'0'}: raise SystemExit(f'build profile does not prove INPUT_JOYSTICK=0: {sorted(joy)}')
manifest=json.loads((root/'build'/'ladybug-presentation.json').read_text())
choreo=manifest['instruction_choreography']
presentation_maps={row['name']:source_hashes['tiled/'+Path(row['path']).name] for row in manifest['maps']}
if len(presentation_maps)!=9: raise SystemExit(f'expected nine frozen presentation maps, found {len(presentation_maps)}')
inc=(root/'build'/'ladybug_shared_text.inc').read_text()
font=parse_values(inc,'font','colour_lut')
descriptor_bytes=parse_values(inc,'dynamic_descriptors','no_end')
if len(descriptor_bytes)%2: raise SystemExit('dynamic descriptor table has an odd byte count')
descriptors=[(descriptor_bytes[i],descriptor_bytes[i+1]) for i in range(0,len(descriptor_bytes),2)]
ids=choreo['multiplier_tile_ids']
expected_ids={'2':[40,41],'3':[40,42],'5':[40,43]}
if ids!=expected_ids: raise SystemExit(f'multiplier tile IDs changed: {ids}')
fields=manifest['shared_text']['colour_configuration']['fields']
if fields['instruction_multiplier']!=3 or fields['instruction_points']!=6:
    raise SystemExit('frozen colour config differs from reviewed blue3/white6 contract')
expected_glyphs={'2':2,'3':3,'5':5}
def render_mask(mask,colour):
    result=bytearray()
    for row in mask:
        for x in range(0,8,2):
            hi=colour if row&(0x80>>x) else 0
            lo=colour if row&(0x80>>(x+1)) else 0
            result.append((hi<<4)|lo)
    return bytes(result)
multiplier_proof={}
for number,pair in ids.items():
    x_id,digit_id=pair
    if descriptors[x_id][1]!=0: raise SystemExit(f'X descriptor {x_id} is not native graphic dispatch')
    glyph,colour=descriptors[digit_id]
    if glyph!=expected_glyphs[number] or colour!=3: raise SystemExit(f'wrong digit tuple for X{number}: id{digit_id}={descriptors[digit_id]}')
    mask=font[glyph*8:(glyph+1)*8]
    pixels=render_mask(mask,colour)
    multiplier_proof[number]={'native_x_descriptor':[descriptors[x_id][0],descriptors[x_id][1]],'digit_tile_id':digit_id,'descriptor_tuple':[glyph,colour],'glyph_mask_hex':mask.hex(),'rendered_digit_sha256':sha(pixels)}
value_ids={ident for group in choreo['value_tile_ids'].values() for ident in group}
digit_ids={pair[1] for pair in ids.values()}
if value_ids & digit_ids: raise SystemExit(f'multiplier digits alias ordinary value tile descriptors: {sorted(value_ids & digit_ids)}')
point_descriptors={str(ident):list(descriptors[ident]) for ident in sorted(value_ids)}
if any(pair[1]!=fields['instruction_points'] for pair in point_descriptors.values()):
    raise SystemExit('ordinary value tile descriptor colour differs from instruction_points')
# The event dispatcher already assigns non-multiplier HUD digits by their typed fields.
non_multiplier_event_fields=[]
for event in choreo['events']:
    if not event['hud_destination']: continue
    field='instruction_extra' if event['index']<5 else 'instruction_special' if event['index']<12 else 'instruction_multiplier'
    for key in ('hud_tile_id','hud_tile_2_id'):
        ident=event[key]
        if ident and descriptors[ident][1]:
            if descriptors[ident][1]!=fields[field]: raise SystemExit(f'event {event["index"]} {key} colour mismatch')
            if field!='instruction_multiplier': non_multiplier_event_fields.append({'event':event['index'],'tile_id':ident,'field':field,'colour':descriptors[ident][1]})
shared_check=json.loads((root/'build'/'shared-text-verification.json').read_text())
if shared_check.get('status')!='pass' or len(shared_check['cases'])!=9 or any(not case['pixel_exact'] for case in shared_check['cases']):
    raise SystemExit('full static SharedText checker is not all-pass')
static_proof=json.loads((out/'static-candidate.json').read_text())
if static_proof.get('status')!='PASS-STATIC-CANDIDATE' or static_proof.get('ordinary_value_tiles_byte_identical') is not True:
    raise SystemExit('BUG065 independent static-mask verification did not pass')
symbols_text=(root/'build'/'ladybug_presentation_symbols.inc').read_text()
symbols={name:re.search(rf'^{name} equ \$([0-9A-F]+)$',symbols_text,re.M).group(1) for name in ('PRES_MAIN_DYNAMIC_TEXT','PRES_MODULE_DRAW_TILE')}
if symbols!={'PRES_MAIN_DYNAMIC_TEXT':'FC9D','PRES_MODULE_DRAW_TILE':'FC9D'}:
    raise SystemExit(f'instruction dynamic dispatch address changed: {symbols}')
dispatcher=(root/'src'/'shared_text_runtime.inc').read_text()
instruction_runtime=(root/'src'/'instruction_runtime.s').read_text()
if 'dynamic_dispatch' not in dispatcher or 'leax dynamic_descriptors,pcr' not in dispatcher or 'jmp shared_mask' not in dispatcher:
    raise SystemExit('current SharedText descriptor/mask dispatch source changed')
if 'draw_multiplier_pair' not in instruction_runtime or 'multiplier_tiles' not in instruction_runtime:
    raise SystemExit('current instruction multiplier draw source changed')
old_probe=json.loads((root/'repro'/'bug065-current-blue-currentprefix.json').read_text())
old_frame=(root/'repro'/'ready-menu-gdb'/'multiplier-front.bin').read_bytes()
if old_probe.get('status')!='FAIL' or old_probe.get('rom_sha256')!=baseline['artifact_sha256']['ladybug.rom'] or len(old_frame)!=30720:
    raise SystemExit('prior failed runtime evidence does not match its recorded pre-fix artifact')
def frame_cell(frame,col,row):
    start=row*8*160+col*4
    return b''.join(frame[start+y*160:start+y*160+4] for y in range(8))
def cell_details(frame,col,row):
    packed=frame_cell(frame,col,row)
    pens=set();mask=[]
    for y in range(8):
        bits=0
        for x in range(8):
            byte=packed[y*4+x//2]
            pen=(byte>>4)&15 if x%2==0 else byte&15
            if pen:
                pens.add(pen);bits|=0x80>>x
        mask.append(bits)
    return {'sha256':sha(packed),'nonzero_pens':sorted(pens),'mask_hex':bytes(mask).hex(),'packed_bytes':len(packed)}
failed_numeral=cell_details(old_frame,28,17)
baseline_white_mask=font[2*8:3*8]
blue_digit=render_mask(baseline_white_mask,3)
if failed_numeral['nonzero_pens']!=[6] or failed_numeral['mask_hex']!=baseline_white_mask.hex():
    raise SystemExit(f'failed X2 numeral is not white glyph 2: {failed_numeral}')
if failed_numeral['sha256']!='66bc8d0039c9ce4213b529da99cc34cb391d02f24f2f5aca03e39ff5eb87cd8f':
    raise SystemExit('failed X2 numeral bytes differ from retained white2 oracle')
blue_difference_count=sum(a!=b for a,b in zip(frame_cell(old_frame,28,17),blue_digit))
if blue_difference_count!=16: raise SystemExit(f'expected 16 differing packed bytes versus blue2, got {blue_difference_count}')
failed_x=cell_details(old_frame,27,17)
failure_evidence={'source_rom_sha256':old_probe['rom_sha256'],'probe_json_sha256':sha((root/'repro'/'bug065-current-blue-currentprefix.json').read_bytes()),'whole_frame_sha256':sha(old_frame),'boundary_capture_sha256':sha((root/'repro'/'ready-menu-gdb'/'multiplier-boundary.bin').read_bytes()),'phase_results':[{'name':phase['name'],'elapsed_seconds':phase['elapsed_seconds'],'deadline_seconds':phase['deadline_seconds'],'result':'PASS' if phase['name']!='natural-instruction-X2-both-publications' else 'FAIL-AT-FIRST-NATURAL-PUBLICATION'} for phase in old_probe['phases']],'failure':'natural X2 row0 owner0 numeral pen3; X at col27,row17 is blue, numeral at col28,row17 is white pen6','x_cell':failed_x,'numeral_cell':failed_numeral,'numeral_shape_matches_glyph2':True,'different_packed_bytes_vs_blue2':blue_difference_count,'corrected_candidate_runtime_tested':False,'rejected_raw_atlas_interpretation':'Withdrawn: raw cold-atlas graphic IDs do not share the dynamic descriptor namespace; ID41 is resolved through dynamic_descriptors and the generated font mask.'}
rom=(root/'build'/'ladybug.rom').read_bytes();cold=(root/'build'/'ladybug-presentation-cold.bin').read_bytes()
report={'status':'PASS-CURRENT-PREFIX-SHAREDTEXT-DESCRIPTORS','head':freeze['head'],'profile':'complete keyboard','emitted_INPUT_JOYSTICK':'0','source_inputs_frozen':len(source_hashes),'presentation_map_input_sha256':presentation_maps,'source_sha256':{name:source_hashes[name] for name in ('scripts/build_presentation.py','scripts/shared_text.py','scripts/verify_bug035_presentation.py','scripts/build.sh','assets/arcade/text-colours.json','src/instruction_runtime.s','src/shared_text_runtime.inc')},'candidate_patch_sha256':freeze['candidate_patch_sha256'],'build_receipt_sha256':sha(receipt_path.read_bytes()),'rom_sha256':sha(rom),'rom_bytes':len(rom),'cold_sha256':sha(cold),'cold_bytes':len(cold),'dispatch_symbols':symbols,'dynamic_descriptor_table_sha256':sha(descriptor_bytes),'multiplier_tile_ids':ids,'fields':{'instruction_multiplier':fields['instruction_multiplier'],'instruction_points':fields['instruction_points']},'multiplier_descriptor_masks':multiplier_proof,'ordinary_value_descriptor_ids':sorted(value_ids),'ordinary_value_descriptors':point_descriptors,'ordinary_value_descriptors_keep_instruction_points':True,'ordinary_value_digit_ids_disjoint_from_multiplier_digit_ids':True,'non_multiplier_event_field_descriptors_preserved':non_multiplier_event_fields,'shared_text_static_screens':shared_check,'static_candidate_proof':static_proof,'baseline_before_fix':{'build_receipt_sha256':baseline['receipt_sha256'],'rom_sha256':baseline['artifact_sha256']['ladybug.rom'],'cold_sha256':baseline['cold_sha256'],'selected_multiplier_descriptors':baseline['baseline_selected_multiplier_descriptors']},'historical_runtime_failure':failure_evidence,'runtime_claimed':False}
(out/'descriptor-proof.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
print(json.dumps({k:report[k] for k in ('status','head','emitted_INPUT_JOYSTICK','source_inputs_frozen','source_sha256','build_receipt_sha256','rom_sha256','rom_bytes','cold_sha256','cold_bytes','multiplier_descriptor_masks','ordinary_value_descriptor_ids','ordinary_value_descriptors_keep_instruction_points','runtime_claimed')},indent=2))
