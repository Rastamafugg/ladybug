"""Compare retained checkpoint results with an exact independently built baseline."""
import argparse,hashlib,json
from pathlib import Path
root=Path(__file__).resolve().parents[2]
parser=argparse.ArgumentParser();parser.add_argument('--baseline',type=Path,required=True)
args=parser.parse_args();baseline=args.baseline
def load(path):return json.loads(path.read_text())
current=root/'repro/feat007/production';old=baseline/'repro/feat007/production'
a=load(current/'instruction-choreography-verification.json')
b=load(old/'instruction-choreography-verification.json')
frames=lambda r:[v['frame_sha256'] for v in r['results'] if 'frame_sha256' in v]
x,y=frames(a),frames(b);assert len(x)==len(y)==1896 and x==y
owners=[]
for owner in (0,1):
    p=(current/f'completion-0-{owner}.pixels').read_bytes()
    q=(old/f'completion-0-{owner}.pixels').read_bytes()
    assert p==q,('attract publication differs',owner)
    owners.append({'owner':owner,'byte_count':len(p),'sha256':hashlib.sha256(p).hexdigest(),'baseline_exact':True})
timing=load(root/'repro/feat005-instruction-windows-20260930.json')
previous=load(baseline/'repro/feat005-instruction-windows-20260930.json')
assert previous['rom_sha256']=='e8fab046d7316c2a52a9fd414a2379e390ece5733302a020c77ad00bfe937cfc'
assert timing['maximum_cycles']==28136 and previous['maximum_cycles']==28091
deltas=[c['cycles']-d['cycles'] for u,v in zip(timing['windows'],previous['windows']) for c,d in zip(u['samples'],v['samples'])]
assert len(deltas)==36 and set(deltas)=={45}
receipt={'status':'pixel compatibility passes; instruction timing fails','rom_sha256':timing['rom_sha256'],'baseline_rom_sha256':previous['rom_sha256'],'instruction_frames':1896,'all_instruction_frames_baseline_exact':True,'instruction_sequence_sha256':hashlib.sha256('\n'.join(x).encode()).hexdigest(),'attract_publications':owners,'natural_instruction_timing':{'current_maximum':28136,'baseline_maximum':28091,'target':27000,'target_met':False,'scanner_overhead_each_sample':45,'samples':36,'units':'fast-clock CPU cycles; event_ticks/8'},'legacy_checkpoint_oracle':{'current_status':a['status'],'baseline_status':b['status'],'current_static_differing_bytes':[c['differing_bytes'] for c in a['completed']],'baseline_static_differing_bytes':[c['differing_bytes'] for c in b['completed']],'accepted_as_current_oracle':False,'meaning':'Historical expected pixels also differ on the exact baseline. Current-vs-baseline byte/hash comparison is the adjacent pixel evidence; natural-ROM checks provide menu/live acceptance.'},'corrected_regression':'New credit-panel screen guard had painted 94 extra yellow bytes on attract. Restored zero-screen skip; both complete 30,720-byte publications now match baseline.'}
(root/'repro/feat005-adjacent-20260930.json').write_text(json.dumps(receipt,indent=2)+'\n')
(root/'repro/feat005-baseline-instruction-windows-20260930.json').write_text(json.dumps(previous,indent=2)+'\n')
print(receipt['status'])
