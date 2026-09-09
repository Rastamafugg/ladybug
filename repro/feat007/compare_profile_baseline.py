"""Compare a failed alternate module with the preserved pre-integration source."""
from pathlib import Path
import sys,subprocess,json,hashlib
root=Path(__file__).resolve().parents[2];sys.path.insert(0,str(root/'scripts'))
import benchmark_6309 as b
profile=sys.argv[1];folder=root/'build'/('feat007-'+profile)
name='presentation' if profile=='release' else 'demo'
source='presentation_runtime.s' if profile=='release' else 'demo_runtime.s'
artifact=folder/f'ladybug-{name}-runtime.bin';symbols=b.symbols(folder/f'ladybug-{name}-runtime.map')
keys=['BUG011_DEVELOPMENT_PROFILE','COMPLETE_PROFILE','HIGHSCORE_TEST_PROFILE','INPUT_JOYSTICK','PRESENTATION_INSTRUCTION_RUNTIME_ADDRESS','PRESENTATION_INSTRUCTION_RUNTIME_BYTES','PRESENTATION_DEMO_RUNTIME_ADDRESS','PRESENTATION_DEMO_RUNTIME_BYTES','PRESENTATION_HIGHSCORE_RUNTIME_ADDRESS','PRESENTATION_HIGHSCORE_RUNTIME_BYTES','PRESENTATION_TILE_PATCH_STAGE_ADDRESS','PRESENTATION_NAME_ENTRY_DATA','HIGHSCORE_PHASE_HELPER','COMPLETE_PHASE_AUX','HIGHSCORE_PHASE_HELPER_ADDRESS','HIGHSCORE_PHASE_HELPER_RESUME']
out=Path(__file__).parent/'production'/f'{profile}-baseline.bin'
cmd=['lwasm','-9','--format=raw',f'--output={out}','-I',str(folder),'-I',str(root/'src')]+[f'-D{k}={symbols[k]}' for k in keys if k in symbols]+[str(Path(__file__).parent/'pre-integration-source'/source)]
subprocess.run(cmd,check=True)
assert out.read_bytes()==artifact.read_bytes(),'alternate-profile module differs from pre-integration source'
report=dict(profile=profile,status='unchanged pre-existing guard failure',bytes=artifact.stat().st_size,limit=1280 if profile=='release' else 938,byte_exact_to_preintegration=True,sha256=hashlib.sha256(out.read_bytes()).hexdigest())
(out.with_suffix('.json')).write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
