"""Reuse the monitor runtime harness for isolated approved BUG-058 kernels."""
from pathlib import Path
import sys,json,time,hashlib
w=Path(sys.argv[1]);out=Path(sys.argv[2]);sys.path.insert(0,str(w/'scripts'))
import verify_bug011_runtime as r
import verify_bug009_monitor_input as m
b=w/'build';ms=r.symbols(b/'ladybug.map');oldms=r.symbols(b/'rebind-before-resident.map');ps=r.symbols(b/'ladybug-presentation-runtime.map')
new=(b/'ladybug-runtime.rom').read_bytes();old=(b/'rebind-before-resident.rom').read_bytes();rom=b/'ladybug.rom'
e={'phase':'actual colour and full player restore byte oracle','deadline_per_colour_or_owner':45,'success_marker':'768 exact colour results and two exact full player restores with caller-live proof','timeout_meaning':'helper return absent; not evidence of game slowdown','clock':'event_ticks/8','rom_sha256':hashlib.sha256(rom.read_bytes()).hexdigest(),'colour_cases':[],'player_cases':[]}
p,c=r.launch_fast(m,Path('/mnt/e/projects/ladybug/docs/reference/xroar/src/xroar'),rom)
def read(a,n=1):return r.read_bytes(c,a,n)
def write(a,v):c.call('write_memory',{'addr':a,'data':bytes(v).hex()})
def go(a):
 ids=m.setup(c,[a])
 try:
  c.call('run');h=c.call('wait_for_stop',{'timeout_ms':10000},timeout=12);assert h.get('pc')==a,h
 finally:m.clear(c,ids)
def call(entry,registers):
 write(0x1efc,[0x1b,0]);write(0x1b00,[0x20,0xfe]);c.call('write_registers',dict(pc=entry,s=0x1efc,dp=0,cc=0x50,**registers))
 start=c.call('read_cycles')['event_ticks'];go(0x1b00)
 return (c.call('read_cycles')['event_ticks']-start)//8,c.call('read_registers')
try:
 go(ps['pft_ready']);assert read(0xc000,0x3e00)==new[:0x3e00]
 table=ms['primary_preserve_table'];expected_table=bytes((0xf0 if not i&0x30 else 0)|(15 if not i&3 else 0) for i in range(52))
 assert read(table,52)==expected_table==new[table-0xc000:table-0xc000+52]
 for colour in (1,2,3):
  deadline=time.monotonic()+45
  for value in range(256):
   assert time.monotonic()<deadline,'colour deadline'
   results={}
   for name,code,sym in [('reference',old,oldms),('candidate',new,ms)]:
    base=sym['rebind_cache_value'];chunk=code[base-0xc000:sym['primary_cache_mask']-0xc000]
    write(0x1800,chunk);assert read(0x1800,len(chunk))==chunk
    write(ms['BONUS_COLOR'],[colour]);write(ms['OBJ_PRIMARY'],[0x69]);write(ms['OBJ_VALUE'],[colour*17])
    cycles,regs=call(0x1800,dict(a=value,b=0x5a,x=0x4321,y=table,u=0x6543))
    expected=(value&0xcc)|(colour<<4 if value&0x30 else 0)|(colour if value&3 else 0)
    assert regs['a']==expected,(name,colour,value,regs['a'],expected)
    assert read(ms['OBJ_VALUE'])[0]==colour*17
    results[name]={'cycles':cycles,'live':{k:regs[k] for k in ('a','b','x','y','u','s','dp')}}
   assert results['reference']['live']==results['candidate']['live'],results
   e['colour_cases'].append(dict(colour=colour,value=value,reference=results['reference']['cycles'],candidate=results['candidate']['cycles']))
 e['no_rebind_cases']=[]
 write(0xffa5,[0x34])
 for cached,colour in ((0,1),(2,2)):
  results={}
  for name,code,sym in [('reference',old,oldms),('candidate',new,ms)]:
   base=sym['sync_entity_cache_colour'];chunk=code[base-0xc000:sym['rebind_cache_value']-0xc000]
   write(0x1800,chunk);assert read(0x1800,len(chunk))==chunk
   write(sym['ENTITY_CACHE_COLOR'],[cached]);write(sym['BONUS_COLOR'],[colour]);write(sym['OBJ_VALUE'],[0x96])
   cycles,regs=call(0x1800,dict(a=0x33,b=0x55,x=0x4321,y=0x5678,u=0x6543))
   assert read(sym['OBJ_VALUE'])[0]==0x96 and read(sym['ENTITY_CACHE_COLOR'])[0]==cached
   results[name]={'cycles':cycles,'live':{k:regs[k] for k in ('a','b','x','y','u','s','dp','cc')}}
  assert results['reference']==results['candidate'],results
  e['no_rebind_cases'].append(dict(cached=cached,colour=colour,cycles=results['candidate']['cycles'],saving=0))
 background=bytes((i*37+i//8*11)&255 for i in range(128));screen=bytes([0xa5])*2560
 for owner in (0,1):
  deadline=time.monotonic()+45;write(0xffa1,range(0x30-owner*4,0x34-owner*4));write(0xffa5,[0x34]);results={}
  for name,code,sym in [('reference',old,oldms),('candidate',new,ms)]:
   assert time.monotonic()<deadline,'player owner deadline'
   base=sym['restore_player'];chunk=code[base-0xc000:sym['draw_screen']-0xc000];write(0x1800,chunk);assert read(0x1800,len(chunk))==chunk
   write(sym['PLAYER_BG_PTR'],[0xa0,0]);write(0xa000,background);write(sym['PLAYER_FB'],[0x40,0]);write(sym['PLAYER_BG_VALID'],[1]);write(0x4000,screen)
   cycles,regs=call(0x1800,dict(a=0x33,b=0x55,x=0x4321,y=0x5678,u=0x6543))
   expected=bytearray(screen)
   for row in range(16):expected[row*160:row*160+8]=background[row*8:row*8+8]
   assert read(0x4000,len(screen))==expected and read(0xa000,128)==background
   assert read(sym['PLAYER_BG_VALID'])[0]==0 and read(sym['PLAYER_COPY_ROWS'])[0]==0
   results[name]={'cycles':cycles,'live':{k:regs[k] for k in ('a','b','x','y','u','s','dp','cc')}}
  assert results['reference']['live']==results['candidate']['live']
  saving=results['reference']['cycles']-results['candidate']['cycles'];assert saving>=140,saving
  e['player_cases'].append(dict(owner_metadata=owner,reference=results['reference']['cycles'],candidate=results['candidate']['cycles'],saving=saving))
 # Adjacent clipped/zero-visible paths keep their exact wrapper behavior.
 es=r.symbols(b/'ladybug-enemy-runtime.map');oes=r.symbols(b/'rebind-before.map')
 enemy=(b/'ladybug-enemy-runtime.rom').read_bytes();oldenemy=(b/'rebind-before.bin').read_bytes()
 e['visible_player_cases']=[]
 for owner,rows in ((0,0),(1,1),(0,15),(1,16)):
  results={};deadline=time.monotonic()+45
  write(0xffa1,range(0x30-owner*4,0x34-owner*4))
  for name,code,sym,ec,ems in [('reference',old,oldms,oldenemy,oes),('candidate',new,ms,enemy,es)]:
   assert time.monotonic()<deadline,'visible-player deadline'
   write(0xc000,code[:0x3e00]);assert read(0xc000,0x3e00)==code[:0x3e00]
   write(0x800,ec);assert read(0x800,len(ec))==ec
   write(sym['PLAYER_BG_PTR'],[0xa0,0]);write(0xa000,background);write(sym['PLAYER_FB'],[0x40,0]);write(sym['PLAYER_BG_VALID'],[1]);write(ems['PLAYER_VISIBLE_ROWS'],[rows]);write(0x4000,screen)
   cycles,regs=call(ems['restore_player_visible'],dict(a=0x33,b=0x55,x=0x4321,y=0x5678,u=0x6543))
   expected=bytearray(screen)
   for row in range(rows):expected[row*160:row*160+8]=background[row*8:row*8+8]
   assert read(0x4000,len(screen))==expected and read(0xa000,128)==background
   assert read(sym['PLAYER_BG_VALID'])[0]==0
   results[name]={'cycles':cycles,'live':{k:regs[k] for k in ('a','b','x','y','u','s','dp','cc')}}
  assert results['reference']['live']==results['candidate']['live']
  saving=results['reference']['cycles']-results['candidate']['cycles'];assert saving==(144 if rows==16 else 0)
  e['visible_player_cases'].append(dict(owner_metadata=owner,rows=rows,saving=saving))
 assert len(e['colour_cases'])==768 and len(e['player_cases'])==2 and len(e['visible_player_cases'])==4
 e['result']='pass'
except Exception as ex:e['result']='fail';e['failure']=repr(ex)
finally:c.close();m.stop(p);out.write_text(json.dumps(e,indent=2)+'\n')
print(e['result'],e.get('failure',''),len(e['colour_cases']),e['player_cases'])
if e['result']!='pass':raise SystemExit(1)
