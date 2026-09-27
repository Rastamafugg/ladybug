from pathlib import Path
import sys,time,json,hashlib
w=Path(sys.argv[1]);out=Path(sys.argv[2]);sys.path.insert(0,str(w/'scripts'))
import verify_bug011_runtime as r
import verify_bug009_monitor_input as m
b=w/'build';es=r.symbols(b/'ladybug-enemy-runtime.map');code=(b/'ladybug-enemy-runtime.rom').read_bytes();rom=b/'ladybug.rom'
e={'phase':'natural startup nest capture and controlled caller-contract discrimination','deadline_seconds':45,'success_marker':'natural copy entry captured; four variants returned and compared to independent 32-row oracle','timeout_meaning':'missing startup/copy return boundary, not gameplay slowdown','rom_sha256':hashlib.sha256(rom.read_bytes()).hexdigest(),'variants':{}}
p,c=r.launch_fast(m,Path('/mnt/e/projects/ladybug/docs/reference/xroar/src/xroar'),rom)
def read(a,n=1):return r.read_bytes(c,a,n)
def write(a,v):c.call('write_memory',{'addr':a,'data':bytes(v).hex()})
def phys(a,n):return bytes.fromhex(c.call('read_memory',{'space':'physical','addr':a,'length':n})['data'])
def go(a):
 ids=m.setup(c,[a])
 try:
  c.call('run');h=c.call('wait_for_stop',{'timeout_ms':10000},timeout=12);assert h.get('pc')==a,h
 finally:m.clear(c,ids)
try:
 deadline=time.monotonic()+45;go(es['capture_zone_bg']);assert read(0x800,len(code))==code,'installed enemy identity';go(es['copy_fb_rows']);regs=c.call('read_registers');e['natural_entry']={k:regs[k] for k in ['pc','x','u','y','s']};e['natural_entry']['ENEMY_ROW']=read(es['ENEMY_ROW'])[0]
 pars=read(0xffa0,8);pages=[phys(pg*8192,8192) for pg in range(64)];expected=b''.join(read(es['ENEMY_ZONE_FB']+row*160,8) for row in range(32));fb_before=read(0x2000,30720);bg_before=read(es['ENEMY_ZONE_BG'],256)
 for swap,count in [(False,False),(True,False),(False,True),(True,True)]:
  assert time.monotonic()<deadline,'probe deadline'
  for pg,data in enumerate(pages):c.call('write_memory',{'space':'physical','addr':pg*8192,'data':data.hex()})
  write(0xffa0,pars);write(0x1800,[0x20,0xfe]);write(0x1efc,[0x18,0]);rr={k:regs[k] for k in ['a','b','cc','dp','x','y','u','pc']};rr.update(s=0x1efc,cc=0x50)
  if swap:rr.update(x=regs['u'],u=regs['x'])
  if count:write(es['ENEMY_ROW'],[32])
  c.call('write_registers',rr);go(0x1800);fb=read(0x2000,30720);bg=read(es['ENEMY_ZONE_BG'],256);changed=[i for i,(a,z) in enumerate(zip(fb_before,fb)) if a!=z];post=phys(0x34*8192,8192);before=pages[0x34];bo=es['ENEMY_ZONE_BG']-0xa000;outside=[i for i,(a,z) in enumerate(zip(before,post)) if a!=z and not bo<=i<bo+256]
  name=('swapped' if swap else 'original')+('_count32' if count else '_stale_count');e['variants'][name]={'background_exact':bg==expected,'framebuffer_changed_bytes':len(changed),'framebuffer_changed_rows':sorted(set(i//160 for i in changed)),'outside_background_page34_changes':len(outside),'first_changed_virtual_addresses':[hex(0x2000+i) for i in changed[:16]],'background_sha256':hashlib.sha256(bg).hexdigest()}
 assert e['variants']['swapped_count32']['background_exact'] and e['variants']['swapped_count32']['framebuffer_changed_bytes']==0 and e['variants']['swapped_count32']['outside_background_page34_changes']==0,'corrected caller contract oracle'
 e['result']='diagnosed'
except Exception as ex:
 import traceback
 e.update(result='fail',failure=repr(ex),traceback=traceback.format_exc())
finally:c.close();m.stop(p);out.write_text(json.dumps(e,indent=2)+'\n')
print(json.dumps(e,indent=2))
if e['result']!='diagnosed':raise SystemExit(1)
