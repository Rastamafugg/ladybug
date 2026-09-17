"""Check data-only colour changes retain every shared mask and cell identity."""
from pathlib import Path
from types import SimpleNamespace
import json,sys,tempfile
root=Path(__file__).resolve().parents[2];sys.path.insert(0,str(root/'scripts'))
import shared_text,build_presentation as p
with tempfile.TemporaryDirectory() as temp:
 out=Path(temp)
 args=SimpleNamespace(chars=root/'assets/arcade/chars.json',tiled_dir=root/'tiled',gameplay_map=root/'tiled/coco-screen.tmx',output=out/'cold.bin')
 baseline=shared_text.SharedText(args,p)
 config=json.loads((root/'assets/arcade/text-colours.json').read_text())
 chosen=[next(r for r in baseline.records if r['screen']==screen and any(bytes.fromhex(r['mask']))) for screen in [*p.MAP_NAMES,'gameplay']]
 config['runs']=[dict(screen=r['screen'],x=r['x'],y=r['y'],width=1,colour=(r['colour']+1)%16) for r in chosen]
 config['fields']={k:v%15+1 for k,v in config['fields'].items()}
 args.text_colours=out/'colours.json';args.text_colours.write_text(json.dumps(config))
 variant=shared_text.SharedText(args,p)
 assert variant.font==baseline.font
 assert len(variant.records)==len(baseline.records)==509
 overrides={(r['screen'],r['x'],r['y']):r['colour'] for r in config['runs']}
 for a,b in zip(baseline.records,variant.records):
  assert {k:v for k,v in a.items() if k!='colour'}=={k:v for k,v in b.items() if k!='colour'}
  key=(a['screen'],a['x'],a['y'])
  expected=config['fields']['bonus'] if key==('gameplay',34,13) else overrides.get(key,a['colour'])
  assert b['colour']==expected
 for key,value in config['fields'].items():assert f'TEXT_{key.upper()} equ {value}\n' in (out/'ladybug_text_colours.inc').read_text()
 equals_key=('gameplay',34,13)
 equals=[r for r in baseline.records if (r['screen'],r['x'],r['y'])==equals_key][0]
 alternate=json.loads((root/'assets/arcade/text-colours.json').read_text())
 alternate['fields']['bonus']=11
 alternate['runs']=[]
 args.text_colours=out/'alternate.json';args.text_colours.write_text(json.dumps(alternate))
 changed=shared_text.SharedText(args,p)
 assert [r for r in changed.records if (r['screen'],r['x'],r['y'])==equals_key][0]['colour']==11
 alternate['runs']=[dict(screen='gameplay',x=34,y=13,width=1,colour=11)]
 args.text_colours=out/'matching.json';args.text_colours.write_text(json.dumps(alternate))
 matching=shared_text.SharedText(args,p)
 assert [r for r in matching.records if (r['screen'],r['x'],r['y'])==equals_key][0]['colour']==11
 alternate['runs']=[dict(screen='gameplay',x=34,y=13,width=1,colour=10)]
 args.text_colours=out/'conflicting.json';args.text_colours.write_text(json.dumps(alternate))
 try:shared_text.SharedText(args,p)
 except ValueError as error:assert 'gameplay equals colour override conflicts with fields.bonus' in str(error)
 else:raise AssertionError('conflicting gameplay equals override was accepted')
 report=dict(status='pass',static_screens=7,static_cells=509,unchanged_masks=len(baseline.font),dynamic_fields=len(config['fields']),equals_default=equals['colour'],equals_alternate=11,matching_override=True,conflicting_override_rejected=True,scope='Authored colour overrides and generated constants; gameplay equals inherits fields.bonus and rejects conflicting overrides.')
 (root/'repro/feat007/production/colour-configuration.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
