"""Adapt retained shared observers to explicitly selected build artifacts."""
from pathlib import Path
import argparse, json, re, shutil

p=argparse.ArgumentParser()
p.add_argument('--repository',type=Path,required=True)
p.add_argument('--baseline-build',type=Path,required=True)
p.add_argument('--candidate-build',type=Path,required=True)
p.add_argument('--output-dir',type=Path,required=True)
a=p.parse_args(); repo=a.repository.resolve(); out=a.output_dir.resolve()
ev=repo/'wiki/internal/tickets/evidence/rsch014-parent'
support=ev/'bug058-clock-audio-support'; perf=ev/'perf008-probe-support'
scratch=out/'generator-work'; generated=scratch/'repro'
generated.mkdir(parents=True,exist_ok=True)
shutil.copy2(perf/'rsch014_current_triggers_settled.py',generated/'rsch014_current_triggers_settled.py')

def generate(path):
 s=path.read_text()
 s,n=re.subn(r"root=Path\('/mnt/e/projects/ladybug'\)",lambda m:'root=Path('+repr(str(scratch))+')',s,count=1)
 assert n==1,path
 exec(compile(s,str(path),'exec'),{'__name__':'__main__','__file__':str(path)})

generate(support/'bug058_make_clock_position_probe.py')
s=(generated/'bug058_clock_position_probe.py').read_text()
s,n=re.subn(r"^b=w/'build';ms=", "b=w/'repro/perf008-execution/default-build';ms=",s,count=1,flags=re.M)
assert n==1
(generated/'bug058_clock_position_perf008.py').write_text(s)
generate(support/'bug058_make_published_trigger.py')
generate(perf/'perf008_make_last_bonus.py')
shutil.copy2(generated/'perf008_last_bonus.py',generated/'perf008_integrated_last_bonus.py')
generate(support/'bug087_make_transition_probe.py')

def adapt(s,build):
 build=build.resolve(); assert (build/'ladybug.rom').is_file(),build
 s,n=re.subn(r'^b=.*?;ms=',lambda m:'b=Path('+repr(str(build))+');ms=',s,count=1,flags=re.M)
 assert n==1
 s=s.replace('/mnt/e/projects/ladybug/scripts',str(repo/'scripts'))
 s=s.replace('/mnt/e/projects/ladybug/docs/reference/xroar/src/xroar',str(repo/'docs/reference/xroar/src/xroar'))
 s=s.replace("w,out=map(Path,sys.argv[1:3]);", "assert not {'--two-step-cap-fit','--clock-cap'} & set(sys.argv[3:]),'full artifact required; overlay flags forbidden'\nw,out=map(Path,sys.argv[1:3]);",1)
 compile(s,'adapted observer','exec')
 return s

for variant,build in [('baseline',a.baseline_build),('candidate',a.candidate_build)]:
 s=(generated/'bug058_published_trigger.py').read_text()
 (out/f'published-{variant}.py').write_text(adapt(s,build))

# This criterion proves the clock across a real next-part phase. It deliberately
# does not substitute for BUG-087's distinct four-enemy rate/pixel criterion.
s=(generated/'bug087_transition_probe.py').read_text()
split=s.index("    e['part2_initialization']")
head,tail=s[:split],s[split:]
old="roaming=all(table[i] and table[i+6] for i in range(0,32,8))"
assert tail.count(old)==1
tail=tail.replace(old,"alive=[i for i in range(0,32,8) if table[i]]\n        roaming=bool(alive) and all(table[i+6] for i in alive)",1)
s=head+tail
s=s.replace("assert row['mode']==0 and row['enemies']==4 and row['part_after']==2 and row['fault']==0", "assert row['mode']==0 and 0<=row['enemies']<=4 and row['part_after']==2 and row['fault']==0\n        assert row['steps']<=2 and row['debt_after']==0,'approved clock bound exceeded'\n        row['alive_slots_before']=[i//8 for i in alive]",1)
s=s.replace('eight Part2 four-roaming worklists absent','eight Part2 current-population quiet clock worklists absent',1)
s=s.replace("e['part2_roaming']=rows", "e['part2_clock_steady']=rows",1)
s=s.replace('require8 consecutive transient-free/debt-free two-tick worklists','require8 consecutive current-population transient-free/debt-free two-tick worklists; no four-enemy rate acceptance',1)
assert 'current-population quiet clock' in s and 'approved clock bound exceeded' in s
(out/'next-part-candidate.py').write_text(adapt(s,a.candidate_build))
s=(support/'bug058_current_bookkeeping.py').read_text()
s=s.replace("sys.path.insert(0,'/mnt/e/projects/ladybug/scripts')",'sys.path.insert(0,'+repr(str(repo/'scripts'))+')',1)
s=s.replace("root=Path('/mnt/e/projects/ladybug');b=root/'worktrees/perf008-readiness/repro/perf008-execution/default-build'",'root=Path('+repr(str(out))+');b=Path('+repr(str(a.candidate_build.resolve()))+')',1)
s=s.replace("banked=(root/'repro/bug058-catchup-banked-fit.bin').read_bytes()","banked=(b/'ladybug-adaptive-banked.bin').read_bytes()",1)
s=s.replace("root/'docs/reference/xroar/src/xroar'",'Path('+repr(str(repo/'docs/reference/xroar/src/xroar'))+')',1)
compile(s,'assigned bookkeeping observer','exec')
(out/'repro').mkdir(exist_ok=True)
(out/'bookkeeping-candidate.py').write_text(s)
(out/'adapter-receipt.json').write_text(json.dumps({'baseline_build':str(a.baseline_build.resolve()),'candidate_build':str(a.candidate_build.resolve()),'generated':['published-baseline.py','published-candidate.py','next-part-candidate.py'],'overlay_flags':'forbidden','phase_criterion':'clock bound/current live population; separate four-enemy rate test remains strict'},indent=2)+'\n')
print('Explicit artifact adapters generated; syntax passed; no emulator launched.')
