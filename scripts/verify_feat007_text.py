#!/usr/bin/env python3
"""FEAT-007 production acceptance gates; missing or stale evidence fails."""
import argparse,hashlib,json,re,subprocess,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text())
def symbols(path):return {m[1]:int(m[2],16) for m in re.finditer(r'^Symbol: (\w+) .* = ([0-9a-fA-F]+)$',path.read_text(),re.M)}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase',choices=('checkpoint','static','runtime'),required=True)
    parser.add_argument('--output',type=Path,default=ROOT/'repro/feat007')
    parser.add_argument('--refresh',action='store_true',help='Run the existing production runtime harnesses before checking their evidence')
    args=parser.parse_args();build=ROOT/'build';evidence=args.output/'production'
    manifest=read(build/'ladybug-presentation.json');shared=manifest['shared_text']
    rom_hash=digest(build/'ladybug.rom');report=dict(phase=args.phase,rom_sha256=rom_hash,status='pass')
    if args.phase=='checkpoint':
        mainmap=symbols(build/'ladybug.map')
        sizes={'resident':(mainmap['resident_end']-0xC000,8192),'assets':(mainmap['asset_end']-mainmap['asset_start'],7680),'presentation':((build/'ladybug-presentation-runtime.bin').stat().st_size,1280),'instruction_staging':((build/'ladybug-instruction-runtime.bin').stat().st_size,938),'ranking':((build/'ladybug-highscore-runtime.bin').stat().st_size,920),'cold':((build/'ladybug-presentation-cold.bin').stat().st_size,16384),'graphics':(shared['graphics'],224)}
        assert all(value<=limit for value,limit in sizes.values()),sizes
        assert mainmap['draw_hud_digit']==mainmap['asset_draw_hud_digit']
        assert mainmap['draw_recolored_map_tile']==mainmap['asset_draw_recolored_map_tile']
        assert (build/'ladybug.rom').stat().st_size==65536
        assert digest(build/'ladybug-presentation-cold.bin')==manifest['cold_payload']['sha256']
        report.update(capacity={k:dict(used=v,limit=l,spare=l-v) for k,(v,l) in sizes.items()},font_bytes=shared['font_bytes'],spare_graphic_ids=256-shared['graphics'],gmc_source_spare=read(build/'ladybug-sparse-layout.json')['gmc']['spare_bytes'])
    elif args.phase=='static':
        subprocess.run([sys.executable,str(ROOT/'scripts/verify_shared_text.py'),'--build-dir',str(build)],check=True)
        subprocess.run([sys.executable,str(ROOT/'repro/feat007/verify_colour_configuration.py')],check=True)
        subprocess.run([sys.executable,str(ROOT/'repro/feat007/compare_instruction_records.py')],check=True)
        assert len(shared['coverage'])==509
        assert {r['screen'] for r in shared['coverage']}=={'attract','instructions','level-start','high-score','game-over','enter-high-score','gameplay'}
        assert shared['colour_configuration']==read(ROOT/'assets/arcade/text-colours.json')
        report.update(static=read(build/'shared-text-verification.json'),configuration=read(evidence/'colour-configuration.json'),instruction_data=read(evidence/'instruction-authored-data.json'))
    else:
        commands=[('gmc_boot_probe.py',['--handoffs','--focused'],0),('gmc_boot_probe.py',['--handoffs','--events'],2),('sequence_probe.py',[],0),('sequence_probe.py',['--owner','0','--records','maximum'],0),('sequence_probe.py',['--owner','1','--records','mixed'],0),('hold_sequence_probe.py',['--choreography'],0),('hold_sequence_probe.py',['--choreography','--reference-replay'],2),('name_sequence_probe.py',[],0),('retime_probe.py',[],0)]
        if args.refresh:
            for script,flags,expected in commands:
                print('Running',script,*flags,flush=True)
                log=evidence/(Path(script).stem+'-'+str(commands.index((script,flags,expected)))+'.log')
                with log.open('w') as handle:result=subprocess.run([sys.executable,str(ROOT/'repro/feat007'/script),'--production',*flags],stdout=handle,stderr=subprocess.STDOUT)
                assert result.returncode==expected,(script,flags,result.returncode,expected,str(log))
        focused=read(evidence/'focused-final-verification.json');events=read(evidence/'gmc-event-verification.json')
        assert focused['rom_sha256']==events['rom_sha256']==rom_hash
        assert focused['status']=='pass'
        failures={c['label']:c for c in events['checks'] if not c['exact']}
        assert set(failures)=={'stage9 to10 panel/live HUD','nonqualifying game-over skips name entry'},failures
        stage=failures['stage9 to10 panel/live HUD']
        assert stage['pixel_exact'] and stage['foreground_max']<=614750
        assert failures['nonqualifying game-over skips name entry']['actual_next_screen']==5
        files=['sequence-verification.json','sequence-0-maximum.json','sequence-1-mixed.json','instruction-choreography-verification.json','name-sequence-verification.json','retiming.json']
        summaries=[]
        for filename in files:
            result=read(evidence/filename)
            assert result['status'] in ('pass','retimed selected publication worklists pass'),filename
            for name,value in result.get('artifact_sha256',{}).items():assert digest(evidence/name)==value,(filename,name,'stale evidence')
            summaries.append(dict(file=filename,max_cycles=result.get('max_cycles')))
        current=read(evidence/'instruction-choreography-verification.json');reference=read(evidence/'instruction-reference-replay.json')
        frames=lambda data:[(r['tick'],r['frame_sha256']) for r in data['results'] if 'frame_sha256' in r]
        assert len(frames(current))==1792 and frames(current)==frames(reference)
        report.update(status='pass with approved exceptions',scenarios=summaries,matching_instruction_frames=1792,exceptions=[dict(scope='Stage-transition setup and full gameplay rebuild',measured_max=stage['foreground_max'],target=27000,decision='User accepts current performance; target remains missed.'),dict(scope='BUG-036 name-entry interaction and score-dependent flow',decision='Explicitly deferred and non-blocking; zero score still enters name entry.')])
    args.output.mkdir(parents=True,exist_ok=True)
    report['source_sha256']={str(path.relative_to(ROOT)):digest(path) for path in [ROOT/'scripts/shared_text.py',ROOT/'scripts/build_presentation.py',ROOT/'scripts/build.sh',ROOT/'assets/arcade/text-colours.json',*sorted((ROOT/'src').glob('shared_text*'))]}
    (args.output/f'production-{args.phase}-verdict.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
