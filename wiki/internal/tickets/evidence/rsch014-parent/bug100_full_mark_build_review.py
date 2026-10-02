from pathlib import Path
import json,sys,importlib.util,hashlib
r=Path('/mnt/e/projects/ladybug');base=r/'worktrees/menu-name-prep';w=r/'worktrees/rsch014-full-r-prototype';b=w/'build'
path=r/'wiki/internal/tickets/evidence/rsch014-A3/bug100_logo_r_composition_probe.py';sp=importlib.util.spec_from_file_location('a',path);a=importlib.util.module_from_spec(sp);sp.loader.exec_module(a)
rec=json.loads((b/'source-build-receipt.json').read_text());a.EXPECTED_ROM=hashlib.sha256((b/'ladybug.rom').read_bytes()).hexdigest();a.EXPECTED_REVISION=rec['revision'];identity=a.verify_receipt(w,b)
def frames(build):
 m=json.loads((build/'ladybug-presentation.json').read_text());cold=(build/'ladybug-presentation-cold.bin').read_bytes();font=a.include_bytes((build/'ladybug_shared_text.inc').read_text(),'font','colour_lut');idx=[x['name'] for x in m['maps']].index('high-score');f=a.decode_static_frame(cold,m,font,idx);out=[f]
 for phase in (0,1):
  c=bytearray(f)
  for dest,p0,p1 in m['highscore_logo']['records']: a.overlay_tile(c,dest,cold[(p0,p1)[phase]:(p0,p1)[phase]+32])
  out.append(c)
 return out
old=frames(base/'build');new=frames(b);reports=[]
for phase,(before,after) in enumerate(zip(old,new)):
 diffs=[]
 for i,(aa,bb) in enumerate(zip(before,after)):
  for shift in (4,0):
   x=(i%160)*2+(shift==0);y=i//160
   if ((aa>>shift)&15)!=((bb>>shift)&15):diffs.append((x,y,(aa>>shift)&15,(bb>>shift)&15))
 pixels=[v for col in (30,31) for row in a.region_pixels(after,col,13) for v in row if v]
 assert len(diffs)==19 and all(240<=x<248 and 104<=y<120 and aa==6 and bb==1 for x,y,aa,bb in diffs)
 assert len(pixels)==44 and set(pixels)=={1}
 reports.append({'phase':['static','logo0','logo1'][phase],'red':44,'white':0,'changed_pixels':19,'outside_mark_changes':0,'frame_sha256':hashlib.sha256(after).hexdigest()})
# Compiler's development test-profile precedes and is excluded from the new rule.
sys.path.insert(0,str(w/'scripts'));import build_presentation as p
assert p.presentation_pen_map('high-score',30,13,'High Score Table and Branding',241,True)==p.presentation_pen_map('high-score',31,13,'High Score Table and Branding',103,True)
out={'date':'2026-10-02','identity':identity,'command':'LADYBUG_PROFILE=complete LADYBUG_INPUT=keyboard LADYBUG_CPU=6809 LADYBUG_ADAPTIVE=1 bash scripts/build.sh build','build_exit_code':0,'worktree':str(w),'branch':'codex/rsch014-full-r-prototype','baseline_rom_sha256':'e3a6cb1c9b9c3d959bc911433aea2b681b22a06608eeee40c8b9c14fae2f7982','phases':reports,'test_profile_palette_preserved':True,'capacity':{'resident':{'bytes':8137,'limit':8192,'free':55},'assets':{'bytes':7618,'limit':7680,'free':62,'baseline_free':58},'presentation':{'bytes':1264,'limit':1280,'free':16},'high_score_runtime':{'bytes':899,'limit':938,'free':39},'helper':{'bytes':331,'limit':334,'free':3},'page3d':{'bytes':6565,'limit':8192,'free':1627}},'limits':'Isolated uncommitted compiler prototype; no production change or repaired live route acceptance.'}
(r/'wiki/internal/tickets/evidence/rsch014-parent/bug100-full-mark-build.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))

