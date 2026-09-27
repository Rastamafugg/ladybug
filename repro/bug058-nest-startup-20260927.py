from pathlib import Path
import sys,json,time,hashlib
w=Path(sys.argv[1]);out=Path(sys.argv[2]);sys.path.insert(0,str(w/'scripts'))
import verify_bug011_runtime as r
import verify_bug009_monitor_input as m
b=w/'build';es=r.symbols(b/'ladybug-enemy-runtime.map');ms=r.symbols(b/'ladybug.map');ps=r.symbols(b/'ladybug-presentation-runtime.map');code=(b/'ladybug-enemy-runtime.rom').read_bytes();rom=b/'ladybug.rom'
e={'phase':'natural demo and credited startup underlay and published nest','deadline_seconds_per_phase':45,'success_marker':'exact 32-row capture with no outside writes; cached dormant pixels and clean upper nest on A and B in demo and credited startup','timeout_meaning':'required startup or owner publication absent','rom_sha256':hashlib.sha256(rom.read_bytes()).hexdigest(),'checks':[]}
p,c=r.launch_fast(m,Path('/mnt/e/projects/ladybug/docs/reference/xroar/src/xroar'),rom)
def read(a,n=1):return r.read_bytes(c,a,n)
def phys(a,n):return bytes.fromhex(c.call('read_memory',{'space':'physical','addr':a,'length':n})['data'])
def go(a):
 ids=m.setup(c,[a])
 try:
  c.call('run');h=c.call('wait_for_stop',{'timeout_ms':10000},timeout=12);assert h.get('pc')==a,h
 finally:m.clear(c,ids)
def key(k,on):c.call('inject_key',{'key':k,'action':'press' if on else 'release'})
def capture(label):
 go(es['capture_zone_bg']);assert read(0x800,len(code))==code;before=read(0x2000,30720);page=read(0xa000,8192);start=es['ENEMY_ZONE_FB']-0x2000;expected=b''.join(before[start+i*160:start+i*160+8] for i in range(32));go(es['build_enemy_nest_cache']);assert read(0x2000,30720)==before,'capture wrote framebuffer';base=es['ENEMY_ZONE_BG'];assert read(base,256)==expected,'underlay mismatch';after=read(0xa000,8192);off=base-0xa000;assert page[:off]==after[:off] and page[off+256:]==after[off+256:],'capture wrote adjacent state';e['checks'].append({'phase':label,'capture_exact':True,'framebuffer_writes':0,'outside_background_writes':0});return expected
try:
 deadline=time.monotonic()+45;clean=capture('demo');seen=set()
 for label in ['demo','credited']:
  if label=='credited':
   deadline=time.monotonic()+45;key(5,True)
   while True:
    assert time.monotonic()<deadline,'credit phase';go(ps['pft_ready'])
    if read(ms['PRES_MODE'])[0]==5:break
   key(5,False);key(1,True);clean=capture('credited');key(1,False);seen=set()
  deadline=time.monotonic()+45
  while len(seen)<2:
   assert time.monotonic()<deadline,'owner publication';go(ps['pft_ready']);mode=read(ms['PRES_MODE'])[0]
   if mode not in ([4] if label=='demo' else [0,6]):continue
   owner=read(ms['FB_FRONT_ID'])[0];assert owner in [0,1];assert read(es['ENEMY_ACTIVE'])[0]==0,'early nest window missed';fb=phys((0x30-owner*4)*8192,30720);start=es['ENEMY_ZONE_FB']-0x2000;upper=b''.join(fb[start+i*160:start+i*160+8] for i in range(16));start=es['ENEMY_FB']-0x2000;lower=b''.join(fb[start+i*160:start+i*160+8] for i in range(16));cache=phys(0x34*8192+es['ENEMY_NEST_CACHE']-0xa000,512)
   # Loading publishes static frames before the composed nest is available.
   if upper!=clean[:128] or lower not in [cache[i*128:(i+1)*128] for i in range(4)]:continue
   seen.add(owner);e['checks'].append({'phase':label,'owner':owner,'upper_clean':True,'dormant_cache_exact':True,'mode':mode,'pixels_sha256':hashlib.sha256(upper+lower).hexdigest()})
 e['result']='pass'
except Exception as ex:
 import traceback
 e.update(result='fail',failure=repr(ex),traceback=traceback.format_exc())
finally:c.close();m.stop(p);out.write_text(json.dumps(e,indent=2)+'\n')
print(json.dumps(e,indent=2))
if e['result']!='pass':raise SystemExit(1)
