from pathlib import Path
import hashlib,json
b=Path('/mnt/c/Users/19029/.codex/worktrees/bug-046-word-carryover/ladybug/build');checks={}
for label,file,n in [('resident','ladybug-runtime.rom',0x3e00),('enemy','ladybug-enemy-runtime.rom',4091),('presentation','ladybug-presentation-runtime.bin',1273)]:
 actual=Path('/tmp/ladybug-rebind-live-'+label+'.bin').read_bytes();expected=(b/file).read_bytes()[:n];assert actual==expected,label;checks[label]={'bytes':len(actual),'match':True}
digest=hashlib.sha256((b/'ladybug.rom').read_bytes()).hexdigest();assert digest=='f67c3424b514be57b56b48916b6d87c94c2e7015685513dff5c9371d14a5b981'
e={'phase':'visible natural-play launch','success_marker':'pft_ready $1932 and exact loaded resident/assets, enemy and presentation bytes','deadline_seconds':45,'timeout_meaning':'launch boundary not reached','rom_sha256':digest,'fit_commit':'cba5205','checks':checks,'gdb_session':'b2cb2b50','acceptance':'manual gameplay pending; not a 27000-cycle pass'}
Path('/mnt/e/projects/ladybug/repro/bug058-rebind-launch-20260927.json').write_text(json.dumps(e,indent=2)+'\n');print(json.dumps(e))
