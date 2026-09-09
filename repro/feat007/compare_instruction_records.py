from pathlib import Path
import json
import sys,hashlib
p=Path(__file__).parent;r=p.parents[1]
old=json.loads((p/'baseline/build/ladybug-presentation.json').read_text())['instruction_choreography']
new=json.loads((r/'build/ladybug-presentation.json').read_text())['instruction_choreography']
font=(p/'fit/asset-text-data.bin').read_bytes()[:328]
def tile(folder,i):
 d=(p/folder/'descriptors.bin').read_bytes();g,c=d[2*i:2*i+2]
 if not c:return (p/folder/'graphics.bin').read_bytes()[32*g:32*g+32]
 return bytes((c if font[g*8+y]&(128>>(x*2)) else 0)*16+(c if font[g*8+y]&(64>>(x*2)) else 0) for y in range(8) for x in range(4))
for group in ['reward_tile_ids','multiplier_tile_ids','value_tile_ids']:
 for key,ids in old[group].items():
  for a,b in zip(ids,new[group][key]):
   if tile('dynamic',a)!=tile('production',b):print(group,key,a,b)
for i,(a,b) in enumerate(zip(old['events'],new['events'])):
 if a['hud_destination']:
  for key in ['hud_tile_id','hud_tile_2_id']:
   if a[key] and tile('dynamic',a[key])!=tile('production',b[key]):print('event',i,key,a[key],b[key],tile('dynamic',a[key]).hex(),tile('production',b[key]).hex())
sys.path.insert(0,str(r/'scripts'))
import build_presentation as compiler,build_screen as screen
tiles=[];ids={}
authored=compiler.parse_instruction_contract(r/'tiled'/compiler.MAP_FILES['instructions'],screen.load_chars(r/'assets/arcade/chars.json'),screen.load_sprites(r/'assets/arcade/sprites.json'),tiles,ids)
checked=0
for group in ['reward_tile_ids','multiplier_tile_ids','value_tile_ids']:
 for key,values in authored[group].items():
  for source,destination in zip(values,new[group][key]):
   expected=tiles[source]
   if group=='value_tile_ids':expected=bytes((6 if v>>4 else 0)*16+(6 if v&15 else 0) for v in expected)
   assert expected==tile('production',destination),(group,key,source,destination)
   checked+=1
for source,destination in zip(authored['events'],new['events']):
 if source['hud_destination']:
  for key in ['hud_tile_id','hud_tile_2_id']:
   if source[key]:
    assert tiles[source[key]]==tile('production',destination[key]),('event',source['index'],key)
    checked+=1
report=dict(status='pass',authored_dynamic_tiles=checked,source='Current TMX instruction contract and raw arcade character/sprite data, with explicit white point-value override.',historical_reference_limit='Retained checkpoint has invalid gameplay-derived images for life reward and P/A/L HUD event tiles; its replay hashes are not an appearance oracle for those events.',production_cold_sha256=hashlib.sha256((p/'production/cold.bin').read_bytes()).hexdigest())
(p/'production/instruction-authored-data.json').write_text(json.dumps(report,indent=2)+'\n');print(report)
