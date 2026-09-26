from pathlib import Path
import hashlib,json,sys,time,gzip
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/'scripts'))
import verify_bug011_runtime as runtime
import verify_bug009_monitor_input as monitor
b=root/'build';ps=runtime.symbols(b/'ladybug-presentation-runtime.map');rom=b/'ladybug.rom';module=(b/'ladybug-presentation-runtime.bin').read_bytes();helper=(b/'ladybug-highscore-helper.bin').read_bytes();aux=(b/'ladybug-highscore-runtime.bin').read_bytes();cold=(b/'ladybug-presentation-cold.bin').read_bytes();manifest=json.loads((b/'ladybug-presentation.json').read_text());records=manifest['highscore_logo']['records'];masked={dest-0x2000+row*160+i for dest,*_ in records for row in range(8) for i in range(4)}
e={'rom_sha256':hashlib.sha256(rom.read_bytes()).hexdigest(),'phase_deadline_seconds':45,'timeout_meaning':'natural screen/phase publication not observed; not proof of slow execution','captures':[],'success_marker':'Both logo phases on both owners, first frame zero, eight-frame cadence, unchanged non-logo pixels and credit phase interruption'}
proc,c=runtime.launch_fast(monitor,Path('/mnt/e/projects/ladybug/docs/reference/xroar/src/xroar'),rom)
def phys(a,n):return bytes.fromhex(c.call('read_memory',{'space':'physical','addr':a,'length':n})['data'])
def low(a,n=1):return phys(0x38*8192+a,n)
def runstop(deadline):
 c.call('run');return c.call('wait_for_stop',{'timeout_ms':int(deadline*1000)},timeout=deadline+2)

def step():
 hit=runstop(10);assert hit['pc']==ps['pft_ready'];return low(0xA5)[0]
def wait(label,pred):
 deadline=time.monotonic()+45
 while time.monotonic()<deadline:
  mode=step()
  if pred(mode):return
 raise TimeoutError(label)
def baseline_hash(count):
 frame=gzip.decompress((root/f'repro/bug052-baseline-{count}-20260926.bin.gz').read_bytes())
 return hashlib.sha256(bytes(v for i,v in enumerate(frame) if i not in masked)).hexdigest()

def capture():
 owner=low(0x8F)[0];assert owner in (0,1),owner
 frame=phys((0x30 if owner==0 else 0x2C)*8192,30720)
 matches=[]
 for phase in (0,1):
  matches.append(all(b''.join(frame[dest-0x2000+row*160:dest-0x2000+row*160+4] for row in range(8))==cold[rec[phase+1]:rec[phase+1]+32] for rec in records for dest in [rec[0]]))
 stable=bytes(v for i,v in enumerate(frame) if i not in masked)
 record={'owner':owner,'timer':int.from_bytes(low(0xB0,2),'big'),'phase_matches':matches,'nonlogo_sha256':hashlib.sha256(stable).hexdigest(),'frame_sha256':hashlib.sha256(frame).hexdigest()}
 return record
try:
 ids=monitor.setup(c,[ps['presentation_flow_tick']]);hit=runstop(40);assert hit['pc']==ps['presentation_flow_tick'];assert runtime.read_bytes(c,0x1900,len(module))==module
 e['presentation_live_exact']=True
 assert phys(0x23*8192+0xC40,len(helper))==helper;e['helper_live_exact']=True
 monitor.clear(c,ids);ids=monitor.setup(c,[ps['pft_ready']])
 wait('attract',lambda m:m==2)
 c.call('inject_key',{'key':5,'action':'press'});wait('credit accepted',lambda m:low(0xA8)[0]==1);c.call('inject_key',{'key':5,'action':'release'})
 wait('first high score',lambda m:m==5 and low(0x91)[0]==0 and low(0x8F)[0]<2)
 assert low(0x300,len(aux))==aux;e['aux_live_exact']=True
 first=capture();assert first['nonlogo_sha256']==baseline_hash(1),('non-logo changed from BUG-051',first);assert first['phase_matches'][0],('first frame must be zero',first);e['first']=first;seen=set();deadline=time.monotonic()+45;changes=[];last_phase=None
 for tick in range(64):
  assert time.monotonic()<deadline
  step();item=capture()
  assert any(item['phase_matches']),item
  assert item['nonlogo_sha256']==first['nonlogo_sha256'],item
  phase=item['phase_matches'].index(True);key=(item['owner'],phase)
  if phase!=last_phase:changes.append({'timer':item['timer'],'phase':phase});last_phase=phase
  if key not in seen:e['captures'].append(item);seen.add(key)
 assert seen=={(0,0),(0,1),(1,0),(1,1)},seen
 e['phase_changes']=changes
 assert all(changes[i]['timer']-changes[i-1]['timer']==8 for i in range(2,len(changes))),changes
 while (int.from_bytes(low(0xB0,2),'big')-5)%8:step()
 c.call('inject_key',{'key':6,'action':'press'})
 wait('credit edge at next logo phase',lambda m:low(0xA8)[0]==2)
 c.call('inject_key',{'key':6,'action':'release'})
 wait('second credit fully published',lambda m:m==5 and low(0x91)[0]==0 and low(0x8F)[0]<2)
 baseline=capture();assert baseline['nonlogo_sha256']==baseline_hash(2),('second credit non-logo changed from BUG-051',baseline);assert baseline['phase_matches'][0],baseline
 e['credit_preemption_first']=baseline;second_seen=set();deadline=time.monotonic()+45
 for tick in range(32):
  assert time.monotonic()<deadline
  step();item=capture();assert any(item['phase_matches']),item
  assert item['nonlogo_sha256']==baseline['nonlogo_sha256'],item
  second_seen.add((item['owner'],item['phase_matches'].index(True)))
 assert second_seen=={(0,0),(0,1),(1,0),(1,1)},second_seen
 e['credit_phase_preemption']='pass'
 e['owner_phase_coverage']='pass';e['nonlogo_unchanged']='pass'
 c.call('inject_key',{'key':1,'action':'press'})
 wait('credited start from animated high score',lambda m:m==ps['MODE_LEVEL'] and low(0xA6)[0]==2 and low(0xA8)[0]==1)
 c.call('inject_key',{'key':1,'action':'release'})
 wait('gameplay after animated high score',lambda m:m==0)
 e['credited_start_after_animation']='pass';e['result']='pass'
except Exception as exc:e['result']='fail';e['failure']=f'{type(exc).__name__}: {exc}'
finally:
 c.close();monitor.stop(proc);(b/'bug052-logo-parent.json').write_text(json.dumps(e,indent=2)+'\n')
print(json.dumps(e,indent=2))
if e['result']!='pass':raise SystemExit(1)
