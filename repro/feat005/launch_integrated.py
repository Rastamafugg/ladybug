import argparse,hashlib,json,re,subprocess,time,os
from pathlib import Path
root=Path(__file__).resolve().parents[2];b=root/'build';out=b/'feat005-main-launch';out.mkdir(exist_ok=True)
rom=b/'ladybug.rom'
parser=argparse.ArgumentParser()
parser.add_argument('--receipt',type=Path,default=root/'repro/feat005-main-natural-launch-20260930.json')
args=parser.parse_args()
def syms(p):return {k:int(v,16) for k,v in re.findall(r'^Symbol: (\w+) .* = ([0-9A-Fa-f]+)$',p.read_text(),re.M)}
main=syms(b/'ladybug.map');pres=syms(b/'ladybug-presentation-runtime.map')
assert not subprocess.run(['ss','-H','-ltn','sport','=','65520'],capture_output=True,text=True).stdout.strip(), 'launch port occupied'
log=(out/'xroar.log').open('wb',buffering=0)
x=subprocess.Popen(['/usr/local/bin/xroar','-machine','coco3','-ram','512','-cart-type','gmc','-cart-rom',str(rom),'-cart-autorun','-ao','pulse','-ao-rate','44100','-ao-buffer-ms','100','-gdb','-gdb-ip','127.0.0.1','-gdb-port','65520'],stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
print('phase=visible cold launch marker=mainloop/attract_tick deadline=45s; timeout=launch boundary failure',flush=True)
try:
 deadline=time.monotonic()+3
 while time.monotonic()<deadline:
  if x.poll() is not None:raise RuntimeError('XRoar exited')
  listing=subprocess.run(['ss','-H','-ltnp','sport','=','65520'],capture_output=True,text=True,timeout=1).stdout
  if f'pid={x.pid},' in listing:break
  time.sleep(.05)
 else:raise TimeoutError('owned GDB listener missing')
 specs=[('resident',0xC000,'ladybug-runtime.rom',0x3E00),('enemy',0x0800,'ladybug-enemy-runtime.rom',None),('presentation',0x1900,'ladybug-presentation-runtime.bin',None)]
 lines=['set pagination off','set confirm off','set remotetimeout 3','set architecture m6809','target remote 127.0.0.1:65520',f'break *0x{main["mainloop"]:x}','continue','delete breakpoints']
 for name,addr,file,limit in specs:
  data=(b/file).read_bytes();data=data[:limit] if limit else data
  lines.append(f'dump binary memory {out/name}.bin 0x{addr:x} 0x{addr+len(data):x}')
 lines.extend([f'break *0x{pres["attract_tick"]:x}','continue','delete breakpoints',f'dump binary memory {out}/dp.bin 0 0x100','detach','quit'])
 (out/'launch.gdb').write_text('\n'.join(lines)+'\n')
 g=subprocess.run(['/usr/local/bin/m6809-gdb','-q','-nx','-batch','-x',str(out/'launch.gdb')],capture_output=True,text=True,timeout=40)
 (out/'gdb.log').write_text(g.stdout+g.stderr);assert g.returncode==0,g.stdout+g.stderr
 identities=[]
 for name,addr,file,limit in specs:
  data=(b/file).read_bytes();data=data[:limit] if limit else data
  assert (out/(name+'.bin')).read_bytes()==data,name+' live identity'
  identities.append({'name':name,'bytes':len(data),'exact':True})
 dp=(out/'dp.bin').read_bytes();assert dp[0xA6]==0 and dp[0xA5]==2,(dp[0xA5],dp[0xA6])
 receipt={'status':'launched for user test','date':'2026-09-30','branch':'codex/feat005-menu','main_revision':'95ef83ef834742cf7068147b35587d00037502d3','rom_sha256':hashlib.sha256(rom.read_bytes()).hexdigest(),'adaptive_enabled':True,'xroar_pid':x.pid,'gdb_port':65520,'audio':{'backend':'pulse','rate':44100,'buffer_ms':100},'live_identity':identities,'natural_state':{'presentation_mode':dp[0xA5],'screen':dp[0xA6],'frame_counter':int.from_bytes(dp[2:4],'big')},'debugger_detached':True,'forced_input':False,'remaining':'BUG-058 timing acceptance and user lower-maze confirmation remain open'}
 args.receipt.write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt),flush=True)
except:
 x.terminate();raise
