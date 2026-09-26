from pathlib import Path
import sys,time,json,hashlib
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/'scripts'))
import verify_bug011_runtime as runtime
import verify_bug009_monitor_input as monitor
b=root/'build';ps=runtime.symbols(b/'ladybug-presentation-runtime.map');rom=b/'ladybug.rom';module=(b/'ladybug-presentation-runtime.bin').read_bytes()
e={'rom_sha256':hashlib.sha256(rom.read_bytes()).hexdigest(),'phase_deadline_seconds':45,'success_marker':'Natural credited gameplay followed by credit edge and observed mode transition','timeout_meaning':'Named phase marker absent within observation bound; not a performance conclusion'}
proc,c=runtime.launch_fast(monitor,Path('/mnt/e/projects/ladybug/docs/reference/xroar/src/xroar'),rom)
def low(a,n=1):return bytes.fromhex(c.call('read_memory',{'space':'physical','addr':0x38*8192+a,'length':n})['data'])
def go():
 c.call('run');return c.call('wait_for_stop',{'timeout_ms':10000},timeout=12)
def wait(label,pred):
 end=time.monotonic()+45
 while time.monotonic()<end:
  hit=go();assert hit['pc']==ps['pft_ready'],hit
  if pred():return
 raise TimeoutError(label)
def key(k,a):c.call('inject_key',{'key':k,'action':a})
try:
 ids=monitor.setup(c,[ps['presentation_flow_tick']]);assert go()['pc']==ps['presentation_flow_tick'];assert runtime.read_bytes(c,0x1900,len(module))==module;e['live_module_exact']=True
 monitor.clear(c,ids);ids=monitor.setup(c,[ps['pft_ready']])
 wait('attract',lambda:low(0xA5)[0]==2)
 key(5,'press');wait('credit',lambda:low(0xA8)[0]==1);key(5,'release')
 wait('high score',lambda:low(0xA5)[0]==5 and low(0x91)[0]==0)
 key(1,'press');wait('level',lambda:low(0xA5)[0]==ps['MODE_LEVEL']);key(1,'release')
 wait('gameplay',lambda:low(0xA5)[0]==0)
 e['before']={'mode':low(0xA5)[0],'credits':low(0xA8)[0]}
 key(6,'press');wait('gameplay credit accepted',lambda:low(0xA8)[0]==1);key(6,'release')
 e['after_edge']={'mode':low(0xA5)[0],'screen':low(0xA6)[0],'credits':low(0xA8)[0]}
 wait('high score after gameplay credit',lambda:low(0xA5)[0]==5 and low(0x91)[0]==0)
 e['after_publication']={'mode':low(0xA5)[0],'screen':low(0xA6)[0],'credits':low(0xA8)[0]};e['result']='reported interruption reproduced'
except Exception as exc:e['result']='probe failed';e['error']=str(exc)
finally:
 c.close();monitor.stop(proc);(root/'repro/bug043-active-credit-diagnosis-20260926.json').write_text(json.dumps(e,indent=2)+'\n')
print(json.dumps(e,indent=2))
