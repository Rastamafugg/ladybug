from pathlib import Path
import sys,time,json,hashlib,collections
w=Path(sys.argv[1]);out=Path(sys.argv[2]);sys.path.insert(0,str(w/'scripts'))
import verify_bug011_runtime as r
import verify_bug009_monitor_input as m
b=w/'build';ms=r.symbols(b/'ladybug.map');oldms=r.symbols(b/'perimeter-before-ladybug.map');ps=r.symbols(b/'ladybug-presentation-runtime.map')
new=(b/'ladybug-runtime.rom').read_bytes();old=(b/'perimeter-before-ladybug-runtime.rom').read_bytes();addr=ms['draw_perimeter_box'];off=addr-0xc000
assert addr==oldms['draw_perimeter_box'] and len(new)==len(old)
assert new[:off]==old[:off] and new[off+88:]==old[off+88:],'only the 88-byte routine may change'
e={'phase':'perimeter independent pixel oracle and reference/candidate timing','deadline_seconds_per_family':45,'success_marker':'all perimeter indices, all colours, zero/one-match cases pass on both selected buffers','timeout_meaning':'controlled return or family deadline missing, not game slowdown','clock':'event_ticks / 8','rom_sha256':hashlib.sha256((b/'ladybug.rom').read_bytes()).hexdigest(),'reference_runtime_sha256':hashlib.sha256(old).hexdigest(),'candidate_runtime_sha256':hashlib.sha256(new).hexdigest(),'routine_bytes':88,'cases':[]}
p,c=r.launch_fast(m,Path('/mnt/e/projects/ladybug/docs/reference/xroar/src/xroar'),b/'ladybug.rom')
def read(a,n=1):return r.read_bytes(c,a,n)
def write(a,v):c.call('write_memory',{'addr':a,'data':bytes(v).hex()})
def go(a):
 ids=m.setup(c,[a])
 try:
  c.call('run');assert c.call('wait_for_stop',{'timeout_ms':10000},timeout=12)['pc']==a
 finally:m.clear(c,ids)
def xy(i):
 if i<12:return i+12,0
 if i<35:return 23,i-11
 if i<58:return 57-i,23
 if i<80:return 0,80-i
 return i-80,0
try:
 go(ps['pft_ready']);live=read(0xc000,len(new));assert live[:8180]==new[:8180],('installed resident identity',[(hex(0xc000+i),a,z) for i,(a,z) in enumerate(zip(live,new)) if a!=z][:12]);assert live[8192:8192+7596]==new[8192:8192+7596],'installed asset identity'
 write(0x1800,[0x20,0xfe]);pattern=bytes((i*73+0x5a)&255 for i in range(32768))
 families=[('positions',[(i,col,i%2,None) for i in range(92) for col in [5,6]]),('colours',[(i,col,col%2,None) for i in [0,12,35,58,80] for col in range(16)]),('synthetic',[(0,col,owner,bytes([0x16]*32) if n==0 else bytes([0x66])+bytes([0x16]*31)) for n in [0,1] for col in [0,5,6,15] for owner in [0,1]])]
 for family,fixtures in families:
  deadline=time.monotonic()+45
  for i,col,owner,fixture in fixtures:
   assert time.monotonic()<deadline,'family deadline'
   x,y=xy(i);tile=new[ms['screen_map']-0xc000+y*40+x+8];src=ms['screen_tiles']+tile*32;data=fixture if fixture is not None else new[src-0xc000:src-0xc000+32];assert len(data)==32
   expected=bytearray(pattern);dest=y*1280+(x+8)*4
   for j,v in enumerate(data):expected[dest+(j//4)*160+j%4]=((col if v>>4==6 else v>>4)<<4)|(col if v&15==6 else v&15)
   results={};write(0xffa1,range(0x30-owner*4,0x34-owner*4))
   for name,code,syms in [('reference',old,oldms),('candidate',new,ms)]:
    write(addr,code[off:off+88]);assert read(addr,88)==code[off:off+88]
    write(0x2000,pattern);write(ms['TEST_X'],[x,y]);write(ms['HUD_COLOR'],[col]);write(ms['OBJ_VALUE'],[0xab]);write(0x1efc,[0x18,0]);c.call('write_registers',{'pc':addr,'s':0x1efc,'dp':0,'cc':0x50})
    start=c.call('read_cycles')['event_ticks']
    if fixture is not None:
     go(syms['dpb_row']);write(0x1a00,data);c.call('write_registers',{'y':0x1a00})
    go(0x1800);cycles=(c.call('read_cycles')['event_ticks']-start)//8
    assert read(0x2000,32768)==expected,(family,i,col,owner,name,'pixel oracle')
    results[name]=cycles
    assert read(ms['HUD_COLOR'])[0]==col,'input colour altered'
    assert read(ms['OBJ_VALUE'])[0]==(col*16 if name=='candidate' or any(v>>4==6 for v in data) else 0xab),'scratch contract'
   e['cases'].append({'family':family,'index':i,'colour':col,'owner_metadata':owner,'high_white':sum(v>>4==6 for v in data),'reference_cycles':results['reference'],'candidate_cycles':results['candidate'],'saved':results['reference']-results['candidate']})
 e['result']='pass'
except Exception as ex:
 import traceback
 e.update(result='fail',failure=repr(ex),traceback=traceback.format_exc())
finally:c.close();m.stop(p);out.write_text(json.dumps(e,indent=2)+'\n')
print(e['result'],len(e['cases']),e.get('failure',''));print(dict(collections.Counter((v['high_white'],v['saved']) for v in e['cases'])))
if e['result']!='pass':raise SystemExit(1)
