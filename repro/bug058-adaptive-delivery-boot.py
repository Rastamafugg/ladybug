"""Cold delivery fixture; stop before game entry. Not an adaptive game ROM."""
from pathlib import Path
import sys,json,hashlib,time
w,fit,out=map(Path,sys.argv[1:4]);bindings_mode='--bindings' in sys.argv[4:];sys.path.insert(0,str(w/'scripts'))
import verify_bug011_runtime as r
import verify_bug009_monitor_input as m
b=w/'build';f=fit/'build/adaptive-fit';d=f/('bindings-delivery' if bindings_mode else 'delivery');syms=r.symbols(d/'boot.map');boot=(d/'boot.bin').read_bytes();delta=syms['LOADER_RAM']-syms['loader_start'];rom=d/'boot-only-fixture.rom';layout=json.loads((b/'ladybug-sparse-layout.json').read_text())
e={'phase':'cold transport fixture halted before game entry','deadline_seconds':45,'success_marker':'all expanded baseline destinations, mapped bookkeeping and banked helper exact at $C002 before gameplay','timeout_meaning':'delivery/handoff marker absent; no active adaptive gameplay claim','fixture_rom_sha256':hashlib.sha256(rom.read_bytes()).hexdigest(),'checks':[]}
if bindings_mode:e.update(phase='cold transport and post-retirement binding-copy fixture',success_marker='exact expanded destinations at $C002, then installed binding and page34 return at $18FC without executing game entry')
p,c=r.launch_fast(m,Path('/mnt/e/projects/ladybug/docs/reference/xroar/src/xroar'),rom);deadline=time.monotonic()+45
sha=lambda data:hashlib.sha256(data).hexdigest()
def read(a,n):return r.read_bytes(c,a,n)
def phys(a,n):return bytes.fromhex(c.call('read_memory',{'space':'physical','addr':a,'length':n})['data'])
def go(a):
 assert time.monotonic()<deadline,'45-second fixture deadline'
 ids=m.setup(c,[a])
 try:
  c.call('run');h=c.call('wait_for_stop',{'timeout_ms':10000},timeout=12);assert h.get('pc')==a,h
 finally:m.clear(c,ids)
def loader(name):
 go(syms[name]+delta);off=syms[name]-0xc000
 assert read(syms[name]+delta,8)==boot[off:off+8],('live loader bytes',name)
try:
 go(syms['boot_copy']);assert read(0xc000,len(boot))==boot,'authored cartridge bytes'
 go(syms['LOADER_RAM']);body=boot[syms['loader_start']-0xc000:];assert read(syms['LOADER_RAM'],len(body))==body,'relocated loader'
 loader('boot_streams_retired')
 helper=(f/'banked.bin').read_bytes();mapped=(f/'mapped.bin').read_bytes();enemy=(d/'mapped-enemy.bin').read_bytes()
 assert phys(0x34*8192+0x1d44,len(helper))==helper,'odd-sized helper raw copy'
 assert read(0x9fd,len(mapped))==mapped and read(0x800,len(enemy))==enemy,'mapped payload/source'
 e['checks'].append({'banked_helper_bytes':len(helper),'mapped_bytes':len(mapped),'helper_sha256':sha(helper),'mapped_sha256':sha(mapped),'exact':True})
 for stream in layout['compression']['streams']:
  data=phys(stream['destination_page']*8192+stream['destination_address']-0xa000,stream['raw_bytes']);assert sha(data)==stream['raw_sha256'],stream['name']
  e['checks'].append({'stream':stream['name'],'bytes':len(data),'sha256':sha(data),'exact':True})
 go(0xc002);runtime=((d/'resident-fixture.bin') if bindings_mode else (b/'ladybug-runtime.rom')).read_bytes()[:0x3e00];assert read(0xc000,len(runtime))==runtime,'resident identity'
 assert phys(0x34*8192+0x1d44,len(helper))==helper and read(0x9fd,len(mapped))==mapped
 e['stop_pc']=0xc002;e['result']='pass';e['scope']='No entry execution, bound gameplay callbacks, pixels, input or audio acceptance. Fixture stopped before game entry.'
 if bindings_mode:
  binding_dir=f/'bindings';audio=(binding_dir/'audio.bin').read_bytes();tick=(binding_dir/'tick.bin').read_bytes();rs=r.symbols(binding_dir/'resident.map')
  assert phys(0x3D*8192+0x162B,len(audio)+len(tick))==audio+tick,'staged binding identity'
  assert syms['LOADER_RAM']<=0x5DE<syms['LOADER_RAM']+len(body),'low RAM live-loader overlap must remain explicit'
  assert (read(0xFFA0,1)[0]&0x3F)==0x38,'component low-RAM mapping'
  c.call('write_memory',{'addr':0x18FC,'data':'20fe'});c.call('write_memory',{'addr':0x1EFC,'data':'18fc'});c.call('write_memory',{'addr':0xFFA5,'data':'34'})
  c.call('write_registers',{'pc':rs['adaptive_install_bindings'],'s':0x1EFC,'dp':0,'cc':0x50});go(0x18FC)
  copied=read(0x5DE,len(tick));e['installer_observation']={'copied_sha256':sha(copied),'expected_sha256':sha(tick),'first_difference':next((i for i,(a,b) in enumerate(zip(copied,tick)) if a!=b),None),'copied_prefix':copied[:16].hex(),'expected_prefix':tick[:16].hex(),'par5':read(0xFFA5,1).hex(),'init0':read(0xFF90,1).hex(),'registers':c.call('read_registers')}
  assert read(0x5DE,len(tick))==tick and (read(0xFFA5,1)[0]&0x3F)==0x34,'post-retirement copied binding'
  assert read(0xA000,8192)==phys(0x34*8192,8192),'return mapping by complete page identity'
  e['checks'].append({'post_loader_copy_bytes':len(tick),'staged_bytes':len(audio)+len(tick),'no_live_loader_overwrite':True,'installed_exact':True,'page34_return':True})
  e['game_entry_guard_pc']=0xC002;e['stop_pc']=0x18FC
  e['scope']='Game entry was not executed. One controlled post-retirement installer call passed; no natural phase handoff, driver, adaptive pixels/audio or complete timing acceptance.'
except Exception as ex:e.update(result='fail',failure=repr(ex))
finally:
 c.close();m.stop(p);out.write_text(json.dumps(e,indent=2)+'\n')
print(json.dumps(e,indent=2))
if e['result']!='pass':raise SystemExit(1)
