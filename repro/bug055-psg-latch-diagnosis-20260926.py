from pathlib import Path
import sys,json,hashlib,time
root=Path(sys.argv[1]).resolve();out=Path(sys.argv[2]);sys.path.insert(0,str(root/'scripts'))
import verify_bug011_runtime as r
import verify_bug009_monitor_input as m
b=root/'build';au=r.symbols(b/'ladybug-audio-runtime.map');audio=(b/'ladybug-audio-runtime.bin').read_bytes();rom=b/'ladybug.rom'
e={'rom_sha256':hashlib.sha256(rom.read_bytes()).hexdigest(),'phase':'controlled mixer-output frames in normal audio service','deadline_seconds':45,'success_marker':'four audio_mix_write returns with actual CPU PSG-write arguments','timeout_meaning':'mixer write/return boundary not reached','frames':[]}
p,c=r.launch_fast(m,Path('/mnt/e/projects/ladybug/docs/reference/xroar/src/xroar'),rom)
def phys(a,n):return bytes.fromhex(c.call('read_memory',{'space':'physical','addr':a,'length':n})['data'])
def store(sym,data):c.call('write_memory',{'space':'physical','addr':0x3d*8192+au[sym]-0xa000,'data':data.hex()})
def run():c.call('run');return c.call('wait_for_stop',{'timeout_ms':10000},timeout=12)
def go(a):
 ids=m.setup(c,[a])
 try:assert run()['pc']==a
 finally:m.clear(c,ids)
regs=[0,15,0,15,0,15,0,15];selected=0
try:
 for frame in range(4):
  go(au['audio_mix_write']);assert r.read_bytes(c,au['audio_mix_write'],12)==audio[au['audio_mix_write']-0xa000:au['audio_mix_write']-0xa000+12]
  assert phys(0x3d*8192,au['audio_engine_end']-0xa000)==audio[:au['audio_engine_end']-0xa000]
  store('audio_mix_periods',bytes.fromhex('110101000100' if frame==0 else '110201000100' if frame==1 else '010001000100'))
  store('audio_mix_atten',bytes([0 if frame<2 else 15,15,15]));store('audio_mix_noise',bytes([0,15]))
  if frame==0:store('audio_mix_shadow',bytes([0x55]*11))
  ids=m.setup(c,[au['audio_write'],au['audio_mix_write_done']]);writes=[];end=time.monotonic()+45
  try:
   while time.monotonic()<end:
    hit=run()
    if hit['pc']==au['audio_mix_write_done']:break
    assert hit['pc']==au['audio_write'];writes.append(c.call('read_registers')['a'])
   else:raise TimeoutError('write sequence')
  finally:m.clear(c,ids)
  for value in writes:
   if value&128:selected=(value>>4)&7;regs[selected]=((regs[selected]&0x3f0)|(value&15)) if not selected&1 else value&15
   elif selected&1:regs[selected]=value&15
   else:regs[selected]=(regs[selected]&15)|((value&63)<<4)
  e['frames'].append({'frame':frame,'writes':writes,'decoded_psg_registers':regs.copy(),'selected_register':selected,'intended_noise_attenuation':15,'output_shadow':phys(0x3d*8192+au['audio_mix_shadow']-0xa000,11).hex()})
 e['stale_noise_reproduced']=e['frames'][-1]['decoded_psg_registers'][7]!=15 and not e['frames'][-1]['writes']
 e['decoder_source']='docs/reference/xroar/src/sn76489.c: sn76489_write; data bytes use prior selected register'
 e['result']='pass';e['interpretation']='Actual CPU writes decoded with emulator register semantics; not a natural audio capture or proof of every reported sustained tone.'
except Exception as exc:e['result']='fail';e['failure']=repr(exc)
finally:c.close();m.stop(p);out.write_text(json.dumps(e,indent=2)+'\n')
print(json.dumps(e,indent=2))
if e['result']!='pass':raise SystemExit(1)
