from pathlib import Path
import sys,json,time,hashlib,itertools
w=Path(sys.argv[1]);out=Path(sys.argv[2]);sys.path.insert(0,str(w/'scripts'))
import verify_bug011_runtime as r
import verify_bug009_monitor_input as m
b=w/'build';es=r.symbols(b/'ladybug-enemy-runtime.map');au=r.symbols(b/'ladybug-audio-runtime.map');ps=r.symbols(b/'ladybug-presentation-runtime.map');enemy=(b/'ladybug-enemy-runtime.rom').read_bytes();audio=(b/'ladybug-audio-runtime.bin').read_bytes();rom=b/'ladybug.rom'
e={'rom_sha256':hashlib.sha256(rom.read_bytes()).hexdigest(),'phase_deadline_seconds':45,'phase':'isolated mixer ordering and owner-local ring update equivalence','success_marker':'all selected mixer outputs and decoded ring pixels equal independent expected values','timeout_meaning':'missing controlled return or phase deadline, not target slowdown'}
p,c=r.launch_fast(m,Path('/mnt/e/projects/ladybug/docs/reference/xroar/src/xroar'),rom)
def read(a,n=1):return r.read_bytes(c,a,n)
def write(a,v):c.call('write_memory',{'addr':a,'data':bytes(v).hex()})
def go(a):
 ids=m.setup(c,[a])
 try:c.call('run');assert c.call('wait_for_stop',{'timeout_ms':10000},timeout=12)['pc']==a
 finally:m.clear(c,ids)
def call(addr,**regs):
 write(0x1efc,[0x18,0]);c.call('write_registers',dict(pc=addr,s=0x1efc,dp=0,cc=0x50,**regs));t=c.call('read_cycles')['event_ticks'];go(0x1800);return (c.call('read_cycles')['event_ticks']-t)//8
try:
 go(ps['pft_ready']);write(0x1800,[0x20,0xfe]);write(0xffa5,[0x3d]);assert read(au['audio_mix'],au['audio_guard_bytes']-au['audio_mix'])==audio[au['audio_mix']-0xa000:au['audio_guard_bytes']-0xa000]
 write(au['AUDIO_INSTALLED'],[1]);mixcycles=[];mixcount=0
 # Exhaustive priorities including inactive, equal-priority ties and all slots.
 for first in range(-1,8):
  deadline=time.monotonic()+45
  for rest in itertools.product(range(-1,8),repeat=3):
   assert time.monotonic()<deadline,'mixer phase'
   priorities=(first,)+rest
   for i,pri in enumerate(priorities):
    data=bytearray(17);data[0]=255 if pri<0 else i;data[1]=max(0,pri);data[6:12]=bytes([0,i+1,0,i+5,0,i+9]);data[12:15]=bytes([i+1,15,15]);data[15:17]=bytes([i,5+i]);write(au['audio_slot'+str(i)],data)
   mixcycles.append(call(au['audio_mix']))
   order=sorted((i for i in range(4) if priorities[i]>=0),key=lambda i:(-priorities[i],i))
   expected=[1,0,1,0,1,0];att=[15]*3
   for j,i in enumerate(order[:3]):expected[2*j:2*j+2]=[0,i+1];att[j]=i+1
   assert read(au['audio_mix_periods'],6)==bytes(expected),(priorities,'periods')
   assert read(au['audio_mix_atten'],3)==bytes(att),(priorities,'atten')
   assert read(au['audio_mix_noise'],2)==(bytes([order[0],5+order[0]]) if order else bytes([0,15])),(priorities,'noise')
   mixcount+=1
 e['mixer_cases']=mixcount;e['mixer_max_cycles']=max(mixcycles)
 # Mix multi-voice and exclusive slots; compare the unchanged priority contract.
 for exclusive in [False,True]:
  for order in itertools.permutations(range(4)):
   for i in range(4):
    data=bytearray(17);data[0]=i;data[1]=order[i]+1;data[2]=int(exclusive);data[6:12]=bytes([0,i+1,0,i+5,0,i+9]);data[12:15]=bytes([i+1]*3);data[15:17]=bytes([i,5+i]);write(au['audio_slot'+str(i)],data)
   call(au['audio_mix']);best=order.index(3)
   assert read(au['audio_mix_periods'],6)==bytes([0,best+1,0,best+5,0,best+9])
 e['multi_voice_exclusive_cases']=48
 write(0xffa5,[0x34]);assert read(0x800,len(enemy))==enemy
 pattern=bytes((i*37+(i//160)*13+(i//7))&255 for i in range(30720));write(0x2000,pattern)
 old=0x5000;ringcount=0;maxcycles=0
 for owner in [0,1]:
  write(es['FB_BACK_ID'],[owner]);base=es['ENEMY_BG_BASE'] if owner==0 else es['ENEMY_BG_B']
  for rp in range(16):
   deadline=time.monotonic()+45
   for cp in range(8):
    for delta in [0,1,-1,2,-2,320,-320,640,-640,319,-321]:
     assert time.monotonic()<deadline,'ring phase'
     buf=bytearray(128)
     for row in range(16):
      for col in range(8):buf[((row+rp)%16)*8+(col+cp)%8]=pattern[old-0x2000+row*160+col]
     write(base,buf);write(es['ENEMY_BG_RING'],[(rp<<4)|cp]);write(es['ENEMY_OLD_FB'],old.to_bytes(2,'big'));write(es['ENEMY_OLD_VALID'],[1]);write(es['ENEMY_CAPTURE_DIRTY'],[0]);write(es['ENEMY_WORK'],[4]);write(es['ENEMY_TABLE'],bytes([1])+(old+delta).to_bytes(2,'big')+bytes(5))
     maxcycles=max(maxcycles,call(es['roam_update_background'],x=es['ENEMY_TABLE']))
     assert read(es['ENEMY_TABLE']+1,2)==(old+delta).to_bytes(2,'big'),'record not restored'
     phase=read(es['ENEMY_BG_RING'])[0];got=read(base,128);rr=phase>>4;cc=phase&7
     decoded=bytes(got[((row+rr)%16)*8+(col+cc)%8] for row in range(16) for col in range(8))
     expected=bytes(pattern[old+delta-0x2000+row*160+col] for row in range(16) for col in range(8))
     assert decoded==expected,(owner,rp,cp,delta,'ring pixels')
     ringcount+=1
 e['ring_cases']=ringcount;e['ring_max_cycles']=maxcycles;e['result']='pass'
except Exception as ex:e['result']='fail';e['failure']=repr(ex)
finally:c.close();m.stop(p);out.write_text(json.dumps(e,indent=2)+'\n')
print(json.dumps(e,indent=2))
if e['result']!='pass':raise SystemExit(1)
