from pathlib import Path
import importlib.util,json,hashlib
root=Path(__file__).resolve().parents[5]
candidate=root/'worktrees/rsch014-full-r-prototype'
def module(path,name):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
decoder=module(root/'wiki/internal/tickets/evidence/rsch014-A3/bug100_logo_r_composition_probe.py','decoder')
def inputs(base):
 b=base/'build';m=json.loads((b/'ladybug-presentation.json').read_text());cold=(b/'ladybug-presentation-cold.bin').read_bytes()
 assert hashlib.sha256(cold).hexdigest()==m['cold_payload']['sha256']
 f=decoder.include_bytes((b/'ladybug_shared_text.inc').read_text(),'font','colour_lut')
 return m,cold,f
old,new=inputs(root),inputs(candidate)
oracle=json.loads((root/'wiki/internal/tickets/evidence/rsch014-ready-100/current-mark-oracle.json').read_text())
def pixels(frame):return [p for v in frame for p in (v>>4,v&15)]
def crop(frame):
 return b''.join(frame[(104+r)*160+120:(104+r)*160+128] for r in range(16)).hex()
reports=[]
for i,record in enumerate(old[0]['maps']):
 assert record['name']==new[0]['maps'][i]['name']
 a=decoder.decode_static_frame(old[1],old[0],old[2],i)
 b=decoder.decode_static_frame(new[1],new[0],new[2],i)
 phases=(-1,0,1) if record['name']=='high-score' else (-1,)
 for phase in phases:
  aa,bb=bytearray(a),bytearray(b)
  if phase>=0:
   for params,frame in ((old,aa),(new,bb)):
    for dest,p0,p1 in params[0]['highscore_logo']['records']:
     ptr=(p0,p1)[phase];decoder.overlay_tile(frame,dest,params[1][ptr:ptr+32])
  changed=[(index%320,index//320,x,y) for index,(x,y) in enumerate(zip(pixels(aa),pixels(bb))) if x!=y]
  if record['name']=='high-score':
   assert len(changed)==19
   assert all(240<=x<248 and 104<=y<120 and before==6 and after==1 for x,y,before,after in changed)
   assert crop(aa)==oracle['baseline_crop_hex'] and crop(bb)==oracle['target_crop_hex']
  else:assert not changed,(record['name'],len(changed))
  reports.append({'screen':record['name'],'phase':'static' if phase<0 else phase,'changed_pixels':len(changed),'outside_mark_changes':0})
# The excluded high-score test profile and adjacent palette cells must remain identical.
import sys
sys.path.insert(0,str(root/'scripts'))
original=module(root/'scripts/build_presentation.py','original');proposed=module(candidate/'scripts/build_presentation.py','proposed')
for test in (False,True):
 for y in range(24):
  for x in range(40):
   args=('high-score',x,y,'High Score Table and Branding',97,test)
   a=original.presentation_pen_map(*args);b=proposed.presentation_pen_map(*args)
   if not test and (x,y) in ((30,13),(31,13),(30,14),(31,14)):continue
   assert a==b,(args,a,b)
runtime=json.loads((root/'repro/bug100-current-repaired-two-route.json').read_text())
baseline=json.loads((root/'repro/bug100-current-two-route-baseline.json').read_text())
def routes(result):
 return [{'name':p['name'],'foreground':p['trademark_foreground'],'crop_sha256':p['trademark_crop_sha256'],'elapsed_seconds':p['elapsed_seconds']} for p in result['phases'] if 'trademark_foreground' in p]
out={'status':'PASS','source_revision':'14e3043 with preserved user TMX','prototype_only':True,'baseline_rom_sha256':baseline['rom_sha256'],'candidate_rom_sha256':runtime['rom_sha256'],'baseline_routes':routes(baseline),'candidate_routes':routes(runtime),'static_and_deferred_checks':reports,'excluded_test_profile_unchanged':True,'capacity':{'resident_bytes':8137,'resident_limit':8192,'resident_free':55,'assets_bytes':7659,'assets_limit':7680,'assets_free':21,'presentation_bytes':1266,'presentation_limit':1280,'presentation_free':14},'limitations':['Final gameplay death/qualifying score and name END are disclosed fixtures; preceding maze and END traversal are not asserted.','Root production is unchanged; implementation and combined integration remain required.']}
target=root/'wiki/internal/tickets/evidence/rsch014-ready-100/current-complete-readiness-summary.json';target.write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out,indent=2))
