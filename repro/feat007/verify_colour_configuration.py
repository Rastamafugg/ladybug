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
  assert b['colour']==overrides.get((a['screen'],a['x'],a['y']),a['colour'])
 for key,value in config['fields'].items():assert f'TEXT_{key.upper()} equ {value}\n' in (out/'ladybug_text_colours.inc').read_text()
 report=dict(status='pass',static_screens=7,static_cells=509,unchanged_masks=len(baseline.font),dynamic_fields=len(config['fields']),scope='Authored colour overrides and generated constants; runtime default pixels verified separately.')
 (root/'repro/feat007/production/colour-configuration.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
