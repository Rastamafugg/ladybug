from pathlib import Path
import sys,time,json,hashlib,socket,os
ROOT=next(p for p in Path(__file__).resolve().parents if (p/'scripts/build.sh').is_file());sys.path.insert(0,str(ROOT/'scripts'))
import verify_bug011_runtime as r
import verify_bug009_monitor_input as m
B=Path(os.environ.get('LADYBUG_TEST_BUILD',str(ROOT/'build')))
class Run:
 def __init__(self):
  self.ms=r.symbols(B/'ladybug.map');self.au=r.symbols(B/'ladybug-audio-runtime.map')
  self.p,self.c=r.launch_fast(m,ROOT/'docs/reference/xroar/src/xroar',B/'ladybug.rom');self.held=None;self.cues=[];self.trace=[];self.capture_audio=False
 def close(self):self.c.close();m.stop(self.p)
 def phys(self,a,n):return bytes.fromhex(self.c.call('read_memory',{'space':'physical','addr':a,'length':n})['data'])
 def put(self,a,b):self.c.call('write_memory',{'space':'physical','addr':a,'data':bytes(b).hex()})
 def low(self,k,n=1):return self.phys(0x38*8192+(self.ms[k] if isinstance(k,str) else k),n)
 def val(self,k):return self.low(k)[0]
 def dp(self,k,b):self.put(0x38*8192+(self.ms[k] if isinstance(k,str) else k),b)
 def go(self,k='mainloop'):
  a=self.ms[k] if isinstance(k,str) else k
  self.trace.append({'request':k,'pc':self.c.call('read_registers')['pc'],'pose':self.pose(),'mode':self.val('PRES_MODE'),'joy':self.val('JOY_DIR'),'popup':self.val('PICKUP_TIMER')})
  ids=m.setup(self.c,[a]+([self.au['audio_enqueue_impl']] if self.capture_audio else []))
  try:
   end=time.monotonic()+10
   while time.monotonic()<end:
    self.c.call('run')
    q=self.c.call('wait_for_stop',{'timeout_ms':10000},timeout=12)
    assert q['reason']=='breakpoint',q
    if q['pc']==a:return
    assert q['pc']==self.au['audio_enqueue_impl'],q
    regs=self.c.call('read_registers')
    if regs['a']==6:self.cues.append({'mode':self.val('PRES_MODE'),'entry':self.val('INITIAL_ENTRY_STATE'),'frame':int.from_bytes(self.low('FRAMES',2),'big')})
   raise TimeoutError('breakpoint callback boundary '+str(k))
  except Exception:
   # Existing private-monitor connection reset: retain stopped CPU/mapping/bytes.
   addr=self.c.sock.getpeername();sock=socket.create_connection(addr,timeout=2)
   other=m.MonitorClient(sock);hello=json.loads(other.file.readline())
   other.call('pause');regs=other.call('read_registers')
   self.trace.append({'timeout_pc':regs,'par':r.read_bytes(other,0xffa0,8).hex(),'live_pc_bytes':r.read_bytes(other,regs['pc'],16).hex()})
   self.c.close();self.c=other
   raise
  finally:m.clear(self.c,ids)
 def wait(self,pred,label):
  end=time.monotonic()+45
  while time.monotonic()<end:
   self.go()
   if pred():return
  raise TimeoutError(label)
 def key(self,d):
  # Gameplay directions N/E/S/W, plus neutral. Existing physical DSCAN keys.
  if self.held is not None:self.c.call('inject_key',{'key':self.held,'action':'release'})
  self.held=None if d is None else (0x2b,0x2e,0x2c,0x2d)[d]
  if self.held is not None:self.c.call('inject_key',{'key':self.held,'action':'press'})
 def start(self):
  self.wait(lambda:self.val('PRES_MODE')==2,'cold attract complete')
  assert r.read_bytes(self.c,0xc000,0x3e00)==(B/'ladybug-runtime.rom').read_bytes()[:0x3e00]
  self.c.call('inject_key',{'key':5,'action':'press'})
  self.wait(lambda:self.val('PRES_MODE')==5 and self.val(0xa8)>0,'credited menu')
  self.c.call('inject_key',{'key':5,'action':'release'})
  for _ in range(5):self.go()
  self.c.call('inject_key',{'key':0x30,'action':'press'})
  self.wait(lambda:self.val('PRES_MODE')==6,'new game screen')
  self.c.call('inject_key',{'key':0x30,'action':'release'})
  self.wait(lambda:self.val('PRES_MODE')==0 and self.val('INITIAL_ENTRY_STATE')==0,'natural life entry complete')
  enemy=(B/'ladybug-enemy-runtime.rom').read_bytes()
  assert self.phys(0x38*8192+0x800,len(enemy))==enemy
  audio=(B/'ladybug-audio-runtime.bin').read_bytes()
  # Code portion excludes initialized mutable audio data.
  engine=self.au['audio_engine_end']-0xa000
  assert self.phys(0x3d*8192,engine)==audio[:engine]
  if 'audio_adaptive_api' in self.au:
   api=self.au['audio_adaptive_api']-0xa000
   end=self.au['audio_adaptive_last']-0xa000
   assert self.phys(0x3d*8192+api,end-api)==audio[api:end]
  if not (B/'ladybug-adaptive-active.bin').exists() and (B/'ladybug-highscore-runtime.bin').exists():
   overlay=(B/'ladybug-highscore-runtime.bin').read_bytes()
   assert self.phys(0x38*8192+0x300,len(overlay))==overlay,'retained nonadaptive overlay identity'
  if (B/'ladybug-rate-helper.bin').exists():
   rate=(B/'ladybug-rate-helper.bin').read_bytes()
   assert self.phys(0x34*8192+0x3b0,len(rate))==rate
  if (B/'ladybug-adaptive-active.bin').exists():
   active=(B/'ladybug-adaptive-active.bin').read_bytes()
   src=self.au['audio_adaptive_stage']-0xa000
   assert self.phys(0x3d*8192+src,len(active))==active
   assert self.phys(0x38*8192+0x38f,len(active))==active
  return {'resident':True,'enemy_destination':True,'audio_destination_code':True}
 def fb(self):
  pages=range(0x30,0x34) if self.val('FB_FRONT_ID')==0 else range(0x2c,0x30)
  return b''.join(self.phys(p*8192,8192) for p in pages)[:30720]
 def pose(self):return list(self.low('PLAYER_CELL_X',2))+[self.val('PLAYER_STEP'),int.from_bytes(self.low('PLAYER_FB',2),'big')]
 def fixture(self,x,y,d,step):
  fb=0x2000+(y*8-7)*160+(x*4+28)+( -320,1,320,-1)[d]*step
  self.dp('PLAYER_CELL_X',[x,y]);self.dp('PLAYER_STEP',[step]);self.dp('PLAYER_FB',fb.to_bytes(2,'big'))
  for k,v in [('PLAYER_DIR',d),('PLAYER_MANUAL',1),('TURN_SNAP',0),('PLAYER_ERASED',1),('PICKUP_TIMER',0),('DEATH_STATE',0)]:self.dp(k,[v])
 def input_entry(self,d):
  self.key(d)
  end=time.monotonic()+45
  while time.monotonic()<end:
   self.go('player_tick')
   if self.val('JOY_DIR')==d and self.val('PLAYER_WANT')==d:return
   self.go('pt_done')
  raise TimeoutError('mapped input/player_tick')
def receipt(out,fn):
 run=Run();report={'rom_sha256':hashlib.sha256((B/'ladybug.rom').read_bytes()).hexdigest(),'deadline_seconds':45,'timeout_meaning':'required execution/publication marker absent; no speed inference'}
 try:report.update(fn(run));report['result']='PASS'
 except Exception as e:report['result']='FAIL';report['failure']=repr(e);report['last_boundaries']=run.trace[-15:]
 finally:
  run.close();dest=ROOT/'repro/bugpass-20261010'/out;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2))
 if report['result']!='PASS':raise SystemExit(1)
