from pathlib import Path
import sys,time,json,hashlib,collections
w=Path(sys.argv[1]);prefix=sys.argv[2];out=Path(sys.argv[3]);sys.path.insert(0,str(w/'scripts'))
import verify_bug011_runtime as r
import verify_bug009_monitor_input as m
b=w/'build';es=r.symbols(b/(prefix+'.map'));ps=r.symbols(b/'ladybug-presentation-runtime.map');code=(b/(prefix+'.bin')).read_bytes();boot=(b/'ladybug-enemy-runtime.rom').read_bytes();rom=b/'ladybug.rom'
e={'phase':'indexed sparse decode cost and independent blend oracle','deadline_seconds_per_family_mode':45,'success_marker':'all 146 indexed frames, 26 shared-consumer streams and 32 synthetic commands decode exactly on two nonzero backgrounds','timeout_meaning':'missing controlled return/phase boundary, not game slowdown','clock':'event_ticks / 8','rom_sha256':hashlib.sha256(rom.read_bytes()).hexdigest(),'enemy_sha256':hashlib.sha256(code).hexdigest(),'cases':[],'histograms':{}}
p,c=r.launch_fast(m,Path('/mnt/e/projects/ladybug/docs/reference/xroar/src/xroar'),rom)
def read(a,n=1):return r.read_bytes(c,a,n)
def write(a,v):c.call('write_memory',{'addr':a,'data':bytes(v).hex()})
def go(a):
 ids=m.setup(c,[a])
 try:
  c.call('run');assert c.call('wait_for_stop',{'timeout_ms':10000},timeout=12)['pc']==a
 finally:m.clear(c,ids)
def decode(data,offset,stage,pattern):
 result=bytearray(pattern);cur=offset;pos=0;hist=collections.Counter()
 while True:
  delta=data[cur];cur+=1
  if delta==255:
   fb=int.from_bytes(data[cur:cur+2],'big');cur+=2
   if not fb:return result,cur,hist
   delta=data[cur] if stage else fb;cur+=1;hist['extended']+=1
  elif stage and delta>=128:delta-=152
  pos+=delta;command=data[cur];cur+=1;n=command&127;assert 1<=n<=8;hist[('partial'if command&128 else 'opaque')+str(n)]+=1
  for i in range(n):
   if command&128:result[pos]=(result[pos]&data[cur])|data[cur+1];cur+=2
   else:result[pos]=data[cur];cur+=1
   pos+=1
try:
 go(ps['pft_ready']);assert read(0x800,len(boot))==boot
 write(0x800,code);assert read(0x800,len(code))==code;write(0x1800,[0x20,0xfe])
 for family,count,page in [('enemy',130,0x35),('player',16,0x39)]:
  data=(b/('ladybug-'+family+'-sparse.bin')).read_bytes();physical=bytes.fromhex(c.call('read_memory',{'space':'physical','addr':page*8192,'length':len(data)})['data']);assert physical==data,'installed payload identity'
  for stage in [False,True]:
   deadline=time.monotonic()+45
   for i in range(count):
    pg,hi,lo=data[i*3:i*3+3];addr=hi*256+lo;offset=(pg-page)*8192+addr-0xa000
    for seed in [0x5a,0xc3]:
     assert time.monotonic()<deadline,'family/mode deadline'
     dest=0x4000 if not stage else 0x1900;length=2560 if not stage else 128;pattern=bytes((j*73+seed+i*37)&255 for j in range(length));expected,end,hist=decode(data,offset,stage,pattern)
     write(dest,pattern);write(dest-1,[0x55]);write(dest+length,[0xaa]);write(0xffa5,[pg]);assert read(addr,end-offset)==data[offset:end],'mapped stream identity';write(0x1efc,[0x18,0]);c.call('write_registers',{'pc':es['sparse_blit_stage' if stage else 'sparse_blit_fb'],'s':0x1efc,'dp':0,'cc':0x50,'x':dest,'u':addr})
     start=c.call('read_cycles')['event_ticks'];go(0x1800);cost=(c.call('read_cycles')['event_ticks']-start)//8
     assert read(dest,length)==expected,(family,i,stage,seed,'pixels');assert read(dest-1)[0]==0x55 and read(dest+length)[0]==0xaa,'guard write';assert read(0xa000,64)==bytes.fromhex(c.call('read_memory',{'space':'physical','addr':0x34*8192,'length':64})['data']),'page-$34 mapping not restored'
     e['cases'].append({'family':family,'frame':i,'stage':stage,'seed':seed,'cycles':cost})
     if not stage and seed==0x5a:
      h=e['histograms'].setdefault(family,{});
      for key,n in hist.items():h[key]=h.get(key,0)+n
 # Shared consumers and absent-but-valid run lengths use the same assembled code.
 fixtures=[];payload=(b/'ladybug-presentation-sparse.bin').read_bytes();offset=0
 while offset<len(payload):
  _,end,_=decode(payload,offset,False,bytes(2560));fixtures.append(('presentation',payload[offset:end],False));offset=end
 ms=r.symbols(b/'ladybug.map');resident=(b/'ladybug-runtime.rom').read_bytes()
 for i in range(14):
  off=ms['death_sparse_frame_'+str(i)]-0xc000;_,end,_=decode(resident,off,False,bytes(2560));fixtures.append(('death',resident[off:end],False))
 for stage in [False,True]:
  for partial in [False,True]:
   for n in range(1,9):
    stream=bytes([0,n|(128 if partial else 0)])+(bytes([15,160])*n if partial else bytes(range(1,n+1)))+bytes([255,0,0]);fixtures.append(('synthetic',stream,stage))
 if 'sbf_opaque_table' in es:
  table=es['sbf_opaque_table'];actual=code[table-0x800:table-0x800+8];expected=bytes(es['sbf_opaque'+str(n)]-(table-1) for n in range(1,9));assert actual==expected and max(actual)<128,'signed relative table bounds'
 deadline=time.monotonic()+45;e['shared_cases']=[]
 for i,(family,stream,stage) in enumerate(fixtures):
  for seed in [0x5a,0xc3]:
   assert time.monotonic()<deadline,'shared-consumer deadline'
   dest=0x1900 if stage else 0x4000;length=128 if stage else 2560;pattern=bytes((j*73+seed)&255 for j in range(length));expected,end,_=decode(stream,0,stage,pattern)
   write(dest,pattern);write(dest-1,[0x55]);write(dest+length,[0xaa]);write(0x1a00,stream);assert read(0x1a00,len(stream))==stream;write(0x1efc,[0x18,0]);c.call('write_registers',{'pc':es['sparse_blit_stage' if stage else 'sparse_blit_fb'],'s':0x1efc,'dp':0,'cc':0x50,'x':dest,'u':0x1a00})
   start=c.call('read_cycles')['event_ticks'];go(0x1800);cost=(c.call('read_cycles')['event_ticks']-start)//8
   assert read(dest,length)==expected,(family,i,stage,seed,'shared pixels');assert read(dest-1)[0]==0x55 and read(dest+length)[0]==0xaa,'shared guard';assert read(0xa000,64)==bytes.fromhex(c.call('read_memory',{'space':'physical','addr':0x34*8192,'length':64})['data'])
   e['shared_cases'].append({'family':family,'case':i,'stage':stage,'seed':seed,'cycles':cost})
 e['result']='pass'
except Exception as ex:
 import traceback
 e['result']='fail';e['failure']=repr(ex);e['traceback']=traceback.format_exc()
finally:c.close();m.stop(p);out.write_text(json.dumps(e,indent=2)+'\n')
print(e['result'],len(e['cases']),e.get('failure',''))
if e['result']!='pass':raise SystemExit(1)
