from pathlib import Path
import sys,json,hashlib,time
root=Path(sys.argv[1]).resolve();out=Path(sys.argv[2]);sys.path.insert(0,str(root/'scripts'))
import verify_bug011_runtime as r
import verify_bug009_monitor_input as m
b=root/'build';ps=r.symbols(b/'ladybug-presentation-runtime.map');rom=b/'ladybug.rom';module=(b/'ladybug-presentation-runtime.bin').read_bytes()
e={'expect_blank':'--expect-fixed' in sys.argv,'rom_sha256':hashlib.sha256(rom.read_bytes()).hexdigest(),'phase_deadline_seconds':45,'success_marker':'Both attract and credited high-score HUD regions blank on both published owners, coins and prompts intact','timeout_meaning':'Required phase/publication absent','captures':[]}
p,c=r.launch_fast(m,Path('/mnt/e/projects/ladybug/docs/reference/xroar/src/xroar'),rom)
def phys(a,n):return bytes.fromhex(c.call('read_memory',{'space':'physical','addr':a,'length':n})['data'])
def low(a):return phys(0x38*8192+a,1)[0]
def go(a):
 ids=m.setup(c,[a])
 try:c.call('run');assert c.call('wait_for_stop',{'timeout_ms':10000},timeout=12)['pc']==a
 finally:m.clear(c,ids)
def wait(pred):
 end=time.monotonic()+45
 while time.monotonic()<end:
  go(ps['pft_ready'])
  if pred():return
 raise TimeoutError('phase')
def key(k,on):c.call('inject_key',{'key':k,'action':'press' if on else 'release'})
def capture(label):
 seen=set()
 deadline=time.monotonic()+45
 for _ in range(64):
  assert time.monotonic()<deadline
  go(ps['pft_ready']);owner=low(0x8f)
  if owner in seen:continue
  assert owner in (0,1);seen.add(owner);f=phys((0x30 if owner==0 else 0x2c)*8192,30720)
  def crop(x,y,w,h):return b''.join(f[(y*8+j)*160+x*4:(y*8+j)*160+(x+w)*4] for j in range(h*8))
  hud=crop(33,8,6,2);coins=crop(0,17,9,7)+crop(31,17,9,7);prompt=crop(10,22,20,2)
  e['captures'].append({'phase':label,'owner':owner,'hud_nonzero_bytes':sum(v!=0 for v in hud),'coin_sha256':hashlib.sha256(coins).hexdigest(),'prompt_sha256':hashlib.sha256(prompt).hexdigest()})
  if seen=={0,1}:break
 assert seen=={0,1}
try:
 go(ps['presentation_flow_tick']);assert r.read_bytes(c,0x1900,len(module))==module
 wait(lambda:low(0xa5)==2 and low(0x91)==0);capture('attract')
 for count,k in [(1,5),(2,6)]:
  key(k,True);wait(lambda:low(0xa8)==count);key(k,False);wait(lambda:low(0xa5)==5 and low(0x91)==0);capture('credit'+str(count))
 if '--expect-fixed' in sys.argv:assert all(x['hud_nonzero_bytes']==0 for x in e['captures'])
 if '--baseline' in sys.argv:
  baseline=json.loads(Path(sys.argv[sys.argv.index('--baseline')+1]).read_text())
  for rec in e['captures']:
   if rec['phase']=='attract':continue
   old=next(x for x in baseline['captures'] if x['phase']==rec['phase'] and x['owner']==rec['owner'])
   assert rec['coin_sha256']==old['coin_sha256'] and rec['prompt_sha256']==old['prompt_sha256'],rec
 e['result']='pass'
except Exception as exc:e['result']='fail';e['failure']=repr(exc)
finally:c.close();m.stop(p);out.write_text(json.dumps(e,indent=2)+'\n')
print(json.dumps(e,indent=2))
if e['result']!='pass':raise SystemExit(1)
