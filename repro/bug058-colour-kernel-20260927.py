from pathlib import Path
import sys,json,time,hashlib
w=Path(sys.argv[1]);out=Path(sys.argv[2]);sys.path.insert(0,str(w/'scripts'))
import verify_bug011_runtime as r
import verify_bug009_monitor_input as m
b=w/'build';ms=r.symbols(b/'ladybug.map');oldms=r.symbols(b/'colour-before-resident.map');ps=r.symbols(b/'ladybug-presentation-runtime.map')
new=(b/'ladybug-runtime.rom').read_bytes();old=(b/'colour-before-resident.rom').read_bytes();rom=b/'ladybug.rom'
e={'phase':'isolated colour helper byte oracle','deadline_per_mode_colour_or_mask':45,'success_marker':'1792 byte-oracle cases, exact values/registers/scratch and positive savings','timeout_meaning':'missing helper return, not proof of game slowdown','rom_sha256':hashlib.sha256(rom.read_bytes()).hexdigest(),'cases':[]}
p,c=r.launch_fast(m,Path('/mnt/e/projects/ladybug/docs/reference/xroar/src/xroar'),rom)
def read(a,n=1):return r.read_bytes(c,a,n)
def write(a,v):c.call('write_memory',{'addr':a,'data':bytes(v).hex()})
def go(a):
 ids=m.setup(c,[a])
 try:
  c.call('run');h=c.call('wait_for_stop',{'timeout_ms':10000},timeout=12);assert h.get('pc')==a,h
 finally:m.clear(c,ids)
try:
 go(ps['pft_ready']);assert read(0xc000,0x3e00)==new[:0x3e00]
 for mode in ['rebind','primary']:
  for parameter in ([1,2,3] if mode=='rebind' else [0,15,240,255]):
   deadline=time.monotonic()+45
   for value in range(256):
    assert time.monotonic()<deadline,'phase deadline'
    results={}
    for name,code,symbols in [('reference',old,oldms),('candidate',new,ms)]:
     base=symbols['rebind_cache_value'];end=symbols['replay_gate_entity_overlay'];chunk=code[base-0xc000:end-0xc000];assert len(chunk)<256
     write(0x1800,chunk);assert read(0x1800,len(chunk))==chunk
     colour=parameter if mode=='rebind' else 2;mask=parameter if mode=='primary' else 0x5a
     write(ms['BONUS_COLOR'],[colour]);write(ms['OBJ_ACCENT'],[128 if mode=='rebind' else 1]);write(ms['OBJ_PRIMARY'],[0x69]);write(ms['OBJ_VALUE'],[0x96]);write(0x1b00,[0x20,0xfe]);write(0x1efc,[0x1b,0])
     entry=symbols['rebind_cache_value' if mode=='rebind' else 'primary_cache_mask']-base+0x1800
     c.call('write_registers',{'pc':entry,'s':0x1efc,'dp':0,'cc':0x51,'a':value,'b':mask,'x':0x4321,'y':0x5678,'u':0x6543})
     start=c.call('read_cycles')['event_ticks'];go(0x1b00);elapsed=(c.call('read_cycles')['event_ticks']-start)//8;regs=c.call('read_registers')
     expected=((value&0xcc)|(colour<<4 if value&0x30 else 0)|(colour if value&3 else 0)) if mode=='rebind' else mask|(0xf0 if not value&0x30 else 0)|(15 if not value&3 else 0)
     assert regs['a']==expected,(mode,parameter,value,name,regs['a'],expected)
     result={k:regs[k] for k in ['a','b','x','y','u','s','dp','cc']};result['scratch']=list(read(ms['OBJ_PRIMARY']))+list(read(ms['OBJ_VALUE']));results[name]=(elapsed,result)
    assert results['reference'][1]==results['candidate'][1],(mode,parameter,value,results)
    e['cases'].append({'mode':mode,'parameter':parameter,'value':value,'reference':results['reference'][0],'candidate':results['candidate'][0]})
 e['result']='pass'
except Exception as ex:e['result']='fail';e['failure']=repr(ex)
finally:c.close();m.stop(p);out.write_text(json.dumps(e,indent=2)+'\n')
print(e['result'],e.get('failure',''),len(e['cases']))
if e['result']!='pass':raise SystemExit(1)
