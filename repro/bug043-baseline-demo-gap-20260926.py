from pathlib import Path
import sys,json,hashlib,time
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/'scripts'))
import verify_bug011_runtime as r
import verify_bug009_monitor_input as m
b=root/'build';rom=b/'ladybug.rom';ms=r.symbols(b/'ladybug.map');ps=r.symbols(b/'ladybug-presentation-runtime.map');au=r.symbols(b/'ladybug-audio-runtime.map');resident=(b/'ladybug-runtime.rom').read_bytes();audio=(b/'ladybug-audio-runtime.bin').read_bytes();module=(b/'ladybug-presentation-runtime.bin').read_bytes()
record={'rom_sha256':hashlib.sha256(rom.read_bytes()).hexdigest(),'phase':'unchanged baseline natural demo service-call cadence','deadline_seconds':45,'success_marker':'four mode4 main_entry_audio calls','timeout_meaning':'required baseline marker not observed; no target speed inference','samples':[]}
p,c=r.launch_fast(m,root/'docs/reference/xroar/src/xroar',rom)
def physical(a,n):return bytes.fromhex(c.call('read_memory',{'space':'physical','addr':a,'length':n})['data'])
def low(a,n=1):return physical(0x38*8192+a,n)
try:
 ids=m.setup(c,[ps['presentation_flow_tick']]);h=c.run_to_breakpoint(40);assert h['pc']==ps['presentation_flow_tick'];m.clear(c,ids)
 assert r.read_bytes(c,0x1900,len(module))==module
 target=ms['main_entry_audio'];assert r.read_bytes(c,target,3)==resident[target-0xc000:target-0xc000+3]
 assert physical(0x3d*8192,len(audio))==audio
 record['identity']='presentation, resident caller and staged audio exact'
 ids=m.setup(c,[target]);deadline=time.monotonic()+45
 for i in range(4):
  assert time.monotonic()<deadline
  h=c.run_to_breakpoint(min(10,deadline-time.monotonic()));assert h['pc']==target
  s={'mode':low(0xa5)[0],'frame':int.from_bytes(low(2,2),'big'),'cycles':c.call('read_cycles')['cpu_cycles'],'render_flags':low(0x7f)[0],'init_state':low(0x9a)[0],'slot0':physical(0x3d*8192+au['audio_slot0']-0xa000,6).hex()}
  assert s['mode']==4;record['samples'].append(s)
 record['frame_deltas']=[(b['frame']-a['frame'])&65535 for a,b in zip(record['samples'],record['samples'][1:])];record['result']='pass'
except Exception as e:record['result']='fail';record['failure']=str(e)
finally:c.close();m.stop(p);(b/'bug043-baseline-demo-gap.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record,indent=2))
