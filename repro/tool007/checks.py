from pathlib import Path
import sys,json,dataclasses,tempfile,subprocess,os,hashlib
sys.path.insert(0,str(Path('scripts').resolve()))
from source_reference.normalize import build_project_reference
from source_reference.audit import build_audit
from source_reference.render import render_project
from source_reference.coverage import evaluate_coverage
root=Path('.').resolve(); cfg=json.loads((root/'scripts/source_reference.json').read_text());receipt=json.loads((root/'build/source-build-receipt.json').read_text())
project=build_project_reference(cfg,root,root/'build'); assert not project.ownership_audit['errors']
audio=next(m for m in project.modules if m.id=='audio-runtime')
assert not any(s.name=='audio_adaptive_api' for s in audio.symbols)
negative=dataclasses.replace(audio,symbols=audio.symbols+(dataclasses.replace(audio.symbols[0],name='audio_adaptive_api',assembled_address=0xB800),))
negative_project=dataclasses.replace(project,modules=tuple(negative if m.id==audio.id else m for m in project.modules))
errors=build_audit(negative_project,root,cfg['ownership_audit'],receipt)['errors']
assert len(errors)==3 and all('audio_adaptive_' in e for e in errors),errors
with tempfile.TemporaryDirectory() as temp:
 out=Path(temp);stale=['module-adaptive-active.html','module-adaptive-banked.html','module-adaptive-mapped.html']
 for name in stale:(out/name).write_text('stale')
 (out/'bystander.html').write_text('retain')
 coverage=evaluate_coverage(project,cfg['coverage']);render_project(project,coverage,out)
 assert not any((out/n).exists() for n in stale)
 assert (out/'bystander.html').read_text()=='retain'
prefix=(root/'scripts/build.sh').read_text().split('guard_layout()')[0]
selection=[]
for profile,override,expected in [('complete',None,'1'),('complete','0','0'),('complete','1','1'),('release',None,'0'),('development',None,'0'),('highscore-test',None,'0')]:
 env=dict(os.environ);env.pop('LADYBUG_ADAPTIVE',None);env['LADYBUG_PROFILE']=profile
 if override is not None:env['LADYBUG_ADAPTIVE']=override
 with tempfile.NamedTemporaryFile(mode='w',suffix='.sh') as script:
  script.write(prefix+'printf "%s" "$ADAPTIVE_RENDERING"');script.flush()
  actual=subprocess.check_output(['bash',script.name],env=env,text=True).strip()
 assert actual==expected,(profile,actual)
 selection.append({'profile':profile,'override':override,'adaptive':actual})
e={'revision':receipt['revision'],'nonadaptive_ownership_errors':project.ownership_audit['errors'],'active_api_missing_state_errors':errors,'stale_pages_removed':stale,'bystander_retained':True,'selection':selection,'nonadaptive_rom_sha256':hashlib.sha256((root/'build/ladybug.rom').read_bytes()).hexdigest()}
assert e['nonadaptive_rom_sha256']=='53cc72d4b2837b340864052ed67fbcadaf82af37b123f90f83c1930ce58b6e0a'
(root/'repro/tool007/focused-checks-20261001.json').write_text(json.dumps(e,indent=2)+'\n');print(json.dumps(e))
