from pathlib import Path
import sys,json,time,hashlib,collections
w=Path(sys.argv[1]);prefix=sys.argv[2];out=Path(sys.argv[3]);sys.path.insert(0,str(w/'scripts'))
import verify_bug011_runtime as r
import verify_bug009_monitor_input as m
b=w/'build';es=r.symbols(b/(prefix+'.map'));ps=r.symbols(b/'ladybug-presentation-runtime.map');code=(b/(prefix+'.bin')).read_bytes();bootcode=(b/'ladybug-enemy-runtime.rom').read_bytes();rom=b/'ladybug.rom'
e={'phase':'capture cost sweep with independent decoded-background oracle','deadline_seconds_per_row_phase':45,'success_marker':'all clean selected/full pairs and dirty/invalid fallbacks return exact background','timeout_meaning':'probe boundary or deadline missing, not proof of game slowdown','clock':'event_ticks / 8','rom_sha256':hashlib.sha256(rom.read_bytes()).hexdigest(),'enemy_sha256':hashlib.sha256(code).hexdigest(),'groups':{},'cases':0}
p,c=r.launch_fast(m,Path('/mnt/e/projects/ladybug/docs/reference/xroar/src/xroar'),rom)
def read(a,n=1):return r.read_bytes(c,a,n)
def write(a,v):c.call('write_memory',{'addr':a,'data':bytes(v).hex()})
def go(a):
 ids=m.setup(c,[a])
 try:
  c.call('run');assert c.call('wait_for_stop',{'timeout_ms':10000},timeout=12)['pc']==a
 finally:m.clear(c,ids)
def invoke():
 write(0x1efc,[0x18,0]);c.call('write_registers',{'pc':es['roam_update_background'],'s':0x1efc,'dp':0,'cc':0x50,'x':es['ENEMY_TABLE']});t=c.call('read_cycles')['event_ticks'];go(0x1800);return (c.call('read_cycles')['event_ticks']-t)//8
try:
 go(ps['pft_ready']);assert read(0x800,len(bootcode))==bootcode
 write(0xffa5,[0x34]);write(0x800,code);assert read(0x800,len(code))==code;write(0x1800,[0x20,0xfe])
 pattern=bytes((i*37+(i//160)*13+(i//7))&255 for i in range(30720));write(0x2000,pattern);old=0x5000
 for owner in [0,1]:
  write(es['FB_BACK_ID'],[owner]);base=es['ENEMY_BG_BASE'] if owner==0 else es['ENEMY_BG_B']
  for rp in range(16):
   deadline=time.monotonic()+45
   for cp in range(8):
    buf=bytearray(128)
    for row in range(16):
     for col in range(8):buf[((row+rp)%16)*8+(col+cp)%8]=pattern[old-0x2000+row*160+col]
    for delta in [0,1,-1,2,-2,320,-320,640,-640,319,-321]:
     for policy in ['selected','forced-full']:
      assert time.monotonic()<deadline,'row phase deadline'
      write(base,buf);write(es['ENEMY_BG_RING'],[(rp<<4)|cp]);write(es['ENEMY_OLD_FB'],old.to_bytes(2,'big'));write(es['ENEMY_OLD_VALID'],[1]);write(es['ENEMY_CAPTURE_DIRTY'],[int(policy=='forced-full')]);write(es['ENEMY_WORK'],[4]);record=bytes([1])+(old+delta).to_bytes(2,'big')+bytes(5);write(es['ENEMY_TABLE'],record)
      cycles=invoke();assert read(es['ENEMY_TABLE'],8)==record,'record changed';assert c.call('read_registers')['x']==es['ENEMY_TABLE'],'X not preserved'
      phase=read(es['ENEMY_BG_RING'])[0];got=read(base,128);rr=phase>>4;cc=phase&7
      decoded=bytes(got[((row+rr)%16)*8+(col+cc)%8] for row in range(16) for col in range(8));expected=bytes(pattern[old+delta-0x2000+row*160+col] for row in range(16) for col in range(8));assert decoded==expected,(owner,rp,cp,delta,policy,'pixels')
      key=str(delta)+':'+str(cp)+':'+policy;v=e['groups'].setdefault(key,{'min':cycles,'max':cycles,'sum':0,'count':0});v['min']=min(v['min'],cycles);v['max']=max(v['max'],cycles);v['sum']+=cycles;v['count']+=1;e['cases']+=1
 # Force stale and absent backgrounds for each actor-slot mask; no skip path may retain poison.
 for slot in range(4):
  for valid,dirty in [(0,0),(1<<slot,1<<slot)]:
   base=es['ENEMY_BG_B']+128*slot;write(base,bytes([0xEE])*128);write(es['ENEMY_BG_RING']+slot,[0xF7]);write(es['ENEMY_OLD_FB']+2*slot,old.to_bytes(2,'big'));write(es['ENEMY_OLD_VALID'],[valid]);write(es['ENEMY_CAPTURE_DIRTY'],[dirty]);write(es['ENEMY_WORK'],[4-slot]);write(es['ENEMY_TABLE'],bytes([1])+old.to_bytes(2,'big')+bytes(5));invoke();assert read(base,128)==bytes(pattern[old-0x2000+row*160+col] for row in range(16) for col in range(8));assert read(es['ENEMY_BG_RING']+slot)[0]==0;e['cases']+=1
 e['result']='pass'
except Exception as ex:e['result']='fail';e['failure']=repr(ex)
finally:c.close();m.stop(p);out.write_text(json.dumps(e,indent=2)+'\n')
print(e['result'],e['cases'],e.get('failure',''))
if e['result']!='pass':raise SystemExit(1)
