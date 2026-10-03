from pathlib import Path
import sys,json,hashlib,copy,shutil,xml.etree.ElementTree as ET
from unittest.mock import patch
r=Path(__file__).resolve().parents[5];sys.path.insert(0,str(r/'scripts'))
import build_screen as bs
import build_presentation as bp
out=r/'repro/bug060-partition';out.mkdir(exist_ok=True)
input_pins=json.loads((r/'wiki/internal/tickets/evidence/rsch014-parent/first-ready-inputs-20261003.json').read_text())['TMX_inputs']
map_names=[Path(n).name for n in input_pins if Path(n).name not in ('coco-options-screen.tmx','black-and-whitte-screen.tmx')]
assert len(map_names)==9
chars=bs.load_chars(r/'assets/arcade/chars.json')
blank=chars[255];assert {p for row in blank for p in row}=={0}
reference=ET.parse(r/'tiled/coco-instructions-screen.tmx').getroot()
border_layer=next(l for l in reference.findall('layer') if l.get('name')=='Arcade Maze Border')
template={i:g for i,g in enumerate(bs.parse_csv(border_layer.find('data'),'border')) if g and (g&bs.GID_MASK)!=8}
assert len(template)==135
border_maps={'coco-screen.tmx':'Maze and Panel Background','coco-level-start-screen.tmx':'Level Start Panel','coco-instructions-screen.tmx':'Arcade Maze Border','coco-enter-high-score-screen.tmx':'Arcade Maze Border','coco-game-over-screen.tmx':'Arcade Maze Border'}
def cells(layer):return bs.parse_csv(layer.find('data'),layer.get('name',''))
def set_cells(layer,data):layer.find('data').text='\n'+',\n'.join(','.join(str(x) for x in data[i:i+40]) for i in range(0,960,40))+'\n'
def raw_frame(path,gameplay):
 if gameplay:
  m,t,*_=bs.compile_screen(path,r/'assets/arcade/maze.json',r/'assets/arcade/chars.json',r/'assets/arcade/sprites.json')
 else:
  t=[];m,_=bp.compile_map(path,chars,t,{})
 return bytes(m),bp.title_framebuffer(bytes(m),t)
receipt={'ticket':'BUG-060','base_layer_name':'Background','border_layer_name':'Arcade Maze Border','scope':'read-only preparation; candidate XML only in ignored repro; no root TMX changes','border_template_source':'current instructions Arcade Maze Border plus visual art review,135 exact coordinate/GID/flag matches on all five bordered maps','blank_source':'chars_raw2bpp GID8=>raw code255; all64 source pixels are0; only uniform static character tile across nine maps','maps':{},'compiler_contract_gap':'BUG-059 exact static layer tuples reject new Background, and gameplay/level-start need separated Arcade Maze Border. Approved BUG-060 compiler-edit exception applies to this proved schema gap.'}
for f in (r/'tiled').glob('*.tsx'):shutil.copyfile(f,out/f.name)
for filename in map_names:
 p=r/'tiled'/filename;raw=p.read_bytes();assert hashlib.sha256(raw).hexdigest()==input_pins['tiled/'+filename];root=ET.fromstring(raw);gameplay=filename=='coco-screen.tmx';role='gameplay' if gameplay else bp.screen_role(root,p);key='options' if role=='keybind-options' else role
 contract=copy.deepcopy(bp.PRESENTATION_LAYER_CONTRACTS)
 names=({'Maze and Panel Background','HUD Placeholders'} if gameplay else set(contract[key]['static']))
 before_map,before_frame=raw_frame(p,gameplay)
 owned=[];newid=max(int(l.get('id','0')) for l in root.findall('layer'))+1
 bg=ET.Element('layer',{'id':str(newid),'name':'Background','width':'40','height':'24'});ET.SubElement(bg,'data',{'encoding':'csv'});set_cells(bg,[8]*960);newid+=1
 root.insert(list(root).index(root.find('layer')),bg)
 border=None
 if filename in border_maps:
  original=next(l for l in root.findall('layer') if l.get('name')==border_maps[filename]);values=cells(original)
  assert all(values[i]==g for i,g in template.items())
  if original.get('name')=='Arcade Maze Border':border=original
  else:
   border=ET.Element('layer',{'id':str(newid),'name':'Arcade Maze Border','width':'40','height':'24'});ET.SubElement(border,'data',{'encoding':'csv'});set_cells(border,[0]*960);newid+=1
   root.insert(list(root).index(bg)+1,border)
  bvals=cells(border)
  for i,g in template.items():
   owned.append({'cell':[i%40,i//40],'gid_with_flags':g,'old_owner':original.get('name'),'new_owner':'Arcade Maze Border','role':'maze-border'})
   values[i]=0;bvals[i]=g
  if original is not border:set_cells(original,values)
  set_cells(border,bvals)
 for l in root.findall('layer'):
  name=l.get('name')
  if name not in names:continue
  vals=cells(l)
  for i,g in enumerate(vals):
   if (g&bs.GID_MASK)==8:
    owned.append({'cell':[i%40,i//40],'gid_with_flags':g,'old_owner':name,'new_owner':'Background','role':'blank-background'})
    vals[i]=0
  set_cells(l,vals)
 root.set('nextlayerid',str(newid))
 candidate=out/filename;ET.ElementTree(root).write(candidate,encoding='utf-8',xml_declaration=True)
 if not gameplay:
  contract[key]['static']=('Background',)+tuple(contract[key]['static'])
  if filename=='coco-level-start-screen.tmx':contract[key]['static']=('Background','Arcade Maze Border','Level Start Panel','CoCo Side HUD')
 with patch.dict(bp.PRESENTATION_LAYER_CONTRACTS,contract):
  after_map,after_frame=raw_frame(candidate,gameplay)
 assert before_map==after_map and before_frame==after_frame
 # Full cell ownership is represented compactly as exact layer/GID tuples.
 table=[]
 static_names=names|{'Background'}|({'Arcade Maze Border'} if border is not None else set())
 layer_values={l.get('name'):cells(l) for l in root.findall('layer')}
 layer_names=[l.get('name') for l in root.findall('layer') if l.get('name') in static_names]
 for i in range(960):
  stack=[{'layer':name,'gid_with_flags':values[i]} for name,values in layer_values.items() if values[i]]
  visual=[q for q in stack if q['layer'] in static_names]
  assert visual and visual[0]['layer']=='Background'
  assert all((q['gid_with_flags']&bs.GID_MASK)!=8 for q in visual[1:])
  if border is not None:assert next((q['gid_with_flags'] for q in visual if q['layer']=='Arcade Maze Border'),0)==template.get(i,0)
  table.append(layer_names.index(visual[-1]['layer']))
 receipt['maps'][filename]={'input_sha256':hashlib.sha256(raw).hexdigest(),'candidate_sha256':hashlib.sha256(candidate.read_bytes()).hexdigest(),'compiled_map_sha256':hashlib.sha256(before_map).hexdigest(),'packed_pen_sha256':hashlib.sha256(before_frame).hexdigest(),'composed_gid_and_frame_equal':True,'border_cells':135 if border is not None else 0,'blank_moves':sum(x['role']=='blank-background' for x in owned),'candidate_static_layers':layer_names,'final_static_owner_grid':table,'preserved_nonstatic_layers':{n:hashlib.sha256(json.dumps(v,separators=(',',':')).encode()).hexdigest() for n,v in layer_values.items() if n not in static_names}}
receipt['border_template']=[[i%40,i//40,g] for i,g in sorted(template.items())]
receipt['ownership_encoding']='Each row-major grid has960 indices into candidate_static_layers. Background contains960 GID8 blank records; only the exact135 coordinate/GID/flag template owns border art. Original nonblank nonborder records retain their existing layer, coordinate, GID and flags. Nonstatic layers are untouched.'
receipt['options_schema_constraint']='coco-keybind-options-screen.tmx and unchanged coco-options-screen.tmx share the options role. Add Background only to the exact keybinding-map schema; unchanged options and black-and-whitte inputs stay read-only. Do not make Background generically optional or weaken unknown-layer checks.'
assert all(hashlib.sha256((r/n).read_bytes()).hexdigest()==v for n,v in input_pins.items())
(out/'partition-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps({'maps':len(receipt['maps']),'all_gid_and_frame_equal':True,'bordered_maps':len(border_maps),'border_cells_per_map':135,'input_mutations':0}))
