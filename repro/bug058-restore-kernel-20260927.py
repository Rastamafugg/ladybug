from pathlib import Path
import sys,time,json,hashlib
ref=Path(sys.argv[1]); fit=Path(sys.argv[2]); out=Path(sys.argv[3]);sys.path.insert(0,str(ref/'scripts'))
import verify_bug011_runtime as r
import verify_bug009_monitor_input as m
es=r.symbols(ref/'build/ladybug-enemy-runtime.map');cs=r.symbols(fit/'build/bug058-enemy-check.map');ps=r.symbols(ref/'build/ladybug-presentation-runtime.map')
original=(ref/'build/ladybug-enemy-runtime.rom').read_bytes();candidate=(fit/'build/bug058-enemy-check.bin').read_bytes();rom=ref/'build/ladybug.rom'
e={'phase':'isolated full restore, every ring phase and owner','deadline_seconds_per_owner':45,'success_marker':'256 exact reference/candidate restores with independent pixel oracle','timeout_meaning':'probe boundary missing, not evidence of slow game','clock':'event_ticks / 8','reference_rom_sha256':hashlib.sha256(rom.read_bytes()).hexdigest(),'candidate_enemy_sha256':hashlib.sha256(candidate).hexdigest(),'cases':[]}
p,c=r.launch_fast(m,Path('/mnt/e/projects/ladybug/docs/reference/xroar/src/xroar'),rom)
def read(a,n=1):return r.read_bytes(c,a,n)
def write(a,v):c.call('write_memory',{'addr':a,'data':bytes(v).hex()})
def go(a):
 ids=m.setup(c,[a])
 try:
  c.call('run');assert c.call('wait_for_stop',{'timeout_ms':10000},timeout=12)['pc']==a
 finally:m.clear(c,ids)
try:
 go(ps['pft_ready']);assert read(0x800,len(original))==original
 write(0xffa5,[0x34]);write(0x1800,[0x20,0xfe]);dest=0x4000
 background=bytes((i*37+i//8*11)&255 for i in range(128));screen=bytes([0xA5])*2560
 for owner in [0,1]:
  deadline=time.monotonic()+45
  for rp in range(16):
   for cp in range(8):
    assert time.monotonic()<deadline,'owner deadline'
    results={}
    for name,code,sym in [('reference',original,es),('candidate',candidate,cs)]:
     write(0x800,code);assert read(0x800,len(code))==code
     write(sym['FB_BACK_ID'],[owner]);write(sym['ENEMY_WORK'],[4]);base=sym['ENEMY_BG_BASE'] if owner==0 else sym['ENEMY_BG_B']
     write(base,background);write(sym['ENEMY_BG_RING'],[(rp<<4)|cp]);write(dest,screen);write(0x1efc,[0x18,0]);c.call('write_registers',{'pc':sym['roam_copy_bg_to_fb'],'s':0x1efc,'dp':0,'cc':0x50,'x':dest,'u':base,'a':0x33,'b':0x55,'y':0x1234})
     start=c.call('read_cycles')['event_ticks'];go(0x1800);cycles=(c.call('read_cycles')['event_ticks']-start)//8
     got=read(dest,len(screen));expected=bytearray(screen)
     for row in range(16):
      for col in range(8):expected[row*160+col]=background[((row+rp)%16)*8+(col+cp)%8]
     assert got==expected,(name,owner,rp,cp,'pixels')
     assert read(base,128)==background,(name,'save-under modified')
     regs=c.call('read_registers')
     if cp:regs['y']='row-dispatch-'+str(cp) if regs['y']==sym['rcbtf_phase'+str(cp)+'_rows'] else regs['y']
     results[name]={'cycles':cycles,'registers':{k:regs[k] for k in ['a','b','x','y','u','s','dp']}}
    assert results['reference']['registers']==results['candidate']['registers'],(owner,rp,cp,results)
    e['cases'].append({'owner':owner,'row_phase':rp,'column_phase':cp,**results})
 e['result']='pass'
except Exception as ex:e['result']='fail';e['failure']=repr(ex)
finally:c.close();m.stop(p);out.write_text(json.dumps(e,indent=2)+'\n')
print(e['result'],e.get('failure',''),len(e['cases']))
if e['result']!='pass':raise SystemExit(1)
