"""Natural credit/start/release smoke using existing input and runtime harnesses."""
from pathlib import Path
import sys,time,json,hashlib
w,out=map(Path,sys.argv[1:3]);sys.path.insert(0,str(w/'scripts'))
import verify_bug011_runtime as r
import verify_bug009_monitor_input as m
b=w/'build';ps=r.symbols(b/'ladybug-presentation-runtime.map');ms=r.symbols(b/'ladybug.map');es=r.symbols(b/'ladybug-enemy-runtime.map');au=r.symbols(b/'ladybug-audio-runtime.map')
e={'rom_sha256':hashlib.sha256((b/'ladybug.rom').read_bytes()).hexdigest(),'phase':'natural credit cue and first enemy release','deadline_seconds_per_phase':45,'success_marker':'credit cue 12 and release cue 5 reach live slots with non-silent mixer after natural coin/start input','timeout_meaning':'required natural cue or release not observed; no forced state fallback','listening':'automated admission/mixer evidence; human audible acceptance not claimed','checks':[]}
p,c=r.launch_fast(m,Path('/mnt/e/projects/ladybug/docs/reference/xroar/src/xroar'),b/'ladybug.rom')
def read(a,n=1):return r.read_bytes(c,a,n)
def phys(a,n):return bytes.fromhex(c.call('read_memory',{'space':'physical','addr':a,'length':n})['data'])
def bank(name,n):return phys(0x3d*8192+au[name]-0xa000,n)
def key(k,on):c.call('inject_key',{'key':k,'action':'press' if on else 'release'})
def frame():
 ids=m.setup(c,[ps['pft_ready']])
 try:
  c.call('run');h=c.call('wait_for_stop',{'timeout_ms':10000},timeout=12);assert h.get('pc')==ps['pft_ready'],h
 finally:m.clear(c,ids)
 assert read(ps['pft_ready'],8)==(b/'ladybug-presentation-runtime.bin').read_bytes()[ps['pft_ready']-0x1900:ps['pft_ready']-0x1900+8]
 return read(ms['PRES_MODE'])[0]
def sounds():return [bank('audio_slot'+str(i),1)[0] for i in range(4)],list(bank('audio_mix_atten',3))
try:
 frame();key(5,True);deadline=time.monotonic()+45;observed=False
 while time.monotonic()<deadline:
  mode=frame();slots,atten=sounds()
  if 12 in slots and min(atten)<15:observed=True;break
 assert observed,'credit cue absent'
 key(5,False);e['checks'].append({'natural_credit_cue':12,'slots':slots,'attenuation':atten,'mode':mode})
 deadline=time.monotonic()+45
 while mode!=5:
  assert time.monotonic()<deadline,'high-score entry absent';mode=frame()
 key(1,True);deadline=time.monotonic()+45;started=False
 while time.monotonic()<deadline:
  mode=frame()
  if mode in (0,6):started=True;break
 assert started,'credited start absent'
 key(1,False);observed=False;deadline=time.monotonic()+45;maximum=0
 while time.monotonic()<deadline:
  mode=frame();active=read(es['ENEMY_ACTIVE'])[0];maximum=max(maximum,active);slots,atten=sounds()
  if mode==0 and active>=1 and 5 in slots and min(atten)<15:observed=True;break
 assert observed,('natural release cue absent',mode,maximum,slots)
 e['checks'].append({'natural_release_cue':5,'active_enemies':active,'slots':slots,'attenuation':atten,'mode':mode});e['result']='pass'
except Exception as ex:
 e.update(result='fail',failure=repr(ex))
finally:
 c.close();m.stop(p);out.write_text(json.dumps(e,indent=2)+'\n')
print(json.dumps(e,indent=2))
if e['result']!='pass':raise SystemExit(1)
