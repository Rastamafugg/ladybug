from pathlib import Path
import sys,time,json,hashlib
root=Path(sys.argv[1]).resolve();out=Path(sys.argv[2]).resolve();sys.path.insert(0,str(root/'scripts'))
import verify_bug011_runtime as r
import verify_bug009_monitor_input as m
import build_screen as screen
b=root/'build';ps=r.symbols(b/'ladybug-presentation-runtime.map');ms=r.symbols(b/'ladybug.map');au=r.symbols(b/'ladybug-audio-runtime.map');rom=b/'ladybug.rom';module=(b/'ladybug-presentation-runtime.bin').read_bytes();audio=(b/'ladybug-audio-runtime.bin').read_bytes();unused=None
e={'rom_sha256':hashlib.sha256(rom.read_bytes()).hexdigest(),'phase_deadline_seconds':45,'success_marker':'Credit edges preserve live game, update both HUDs, mix credit audio and preserve level transitions','timeout_meaning':'Named phase missing within bounded observation; not proof of slowdown','phases':[]}
p,c=r.launch_fast(m,Path('/mnt/e/projects/ladybug/docs/reference/xroar/src/xroar'),rom)
def phys(a,n):return bytes.fromhex(c.call('read_memory',{'space':'physical','addr':a,'length':n})['data'])
def low(a,n=1):return phys(0x38*8192+a,n)
def key(k,a):c.call('inject_key',{'key':k,'action':a})
def go(addr):
 ids=m.setup(c,[addr])
 try:
  c.call('run');h=c.call('wait_for_stop',{'timeout_ms':10000},timeout=12);assert h['pc']==addr,h
 finally:m.clear(c,ids)
def slot(i):return phys(0x3d*8192+au[f'audio_slot{i}']-0xa000,17)
def state():return {'mode':low(0xa5)[0],'screen':low(0xa6)[0],'context':low(0xa7)[0],'credits':low(0xa8)[0],'entry':low(0xa0)[0],'death':low(ms['DEATH_STATE'])[0],'lives':low(ms['LIVES'])[0],'player':low(ms['PLAYER_FB'],2).hex(),'slots':[slot(i)[0] for i in range(4)]}
def wait(label,pred):
 end=time.monotonic()+45
 while time.monotonic()<end:
  go(ps['pft_ready']);s=state()
  if pred(s):e['phases'].append({'name':label,**s});return s
 raise TimeoutError(label)
def crop(owner):
 f=phys((0x30 if owner==0 else 0x2c)*8192,30720);o=9*1280+33*4
 return b''.join(f[o+y*160:o+y*160+8] for y in range(8))
def mixed():
 x=slot(1)
 if x[0]!=12 or x[12]==15:return False
 period=int.from_bytes(x[6:8],'little');expected=bytes((0x80|(period&15),(period>>4)&63,0x90|x[12]))
 return phys(0x3d*8192+au['audio_mix_shadow']-0xa000,3)==expected
try:
 go(ps['presentation_flow_tick']);assert r.read_bytes(c,0x1900,len(module))==module;assert phys(0x3d*8192,len(audio))==audio;e['identity']='presentation live and staged audio exact'
 wait('attract',lambda s:s['mode']==2)
 key(5,'press');wait('idle credit opens scores',lambda s:s['credits']==1 and s['screen']==3);key(5,'release')
 wait('scores published',lambda s:s['mode']==5 and low(0x91)[0]==0)
 key(1,'press');wait('credited level',lambda s:s['mode']==6);key(1,'release')
 key(6,'press');wait('credit during level stays level',lambda s:s['credits']==1 and s['mode']==6 and s['screen']==2);key(6,'release')
 wait('entered gameplay',lambda s:s['mode']==0 and s['entry']==0 and s['slots'][0]==255)
 key(0x2b,'press');wait('moving game',lambda s:low(ms['PLAYER_STEP'])[0]>0)
 before=state();key(5,'press');wait('5 in gameplay',lambda s:s['credits']==2);assert state()['mode']==0
 seen=set();mix=0;end=time.monotonic()+45;positions=set()
 for i in range(18):
  assert time.monotonic()<end;go(ps['pft_ready']);s=state();assert s['mode']==0 and s['credits']==2;s2=low(0x8f)[0];seen.add(s2);positions.add(s['player']);mix+=int(mixed());assert s['lives']==before['lives']
 key(5,'release');key(0x2b,'release');assert len(positions)>1;assert seen=={0,1};assert mix>0
 e['held_key_frames']=18;e['moving_positions']=len(positions);e['credit_mix_samples']=mix
 # Compare counter pixels to the built native digit font, including both buffers.
 resident=(b/'ladybug-runtime.rom').read_bytes();font=ms['font']-0xc000;lut=ms['colour_lut']-0xc000+6*32
 def glyph(code):
  data=bytearray()
  for mask in resident[font+code*8:font+code*8+8]:
   for n in (mask>>4,mask&15):data.extend(resident[lut+n*2:lut+n*2+2])
  return bytes(data)
 for owner in (0,1):
  observed=crop(owner);assert b''.join(observed[y*8:y*8+4] for y in range(8))==glyph(2),(owner,observed.hex())
 e['both_counter_pixels']='2 white exact'
 go(ps['pft_ready']);key(5,'press');key(6,'press');wait('simultaneous pair in gameplay',lambda s:s['credits']==4);assert state()['mode']==0;key(5,'release');key(6,'release');go(ps['pft_ready'])
 key(6,'press')
 samples=[]
 for i in range(8):
  go(ps['presentation_flow_tick']);start=c.call('read_cycles')['cpu_cycles'];before_tick=state();go(ms['mainloop']);elapsed=c.call('read_cycles')['cpu_cycles']-start
  samples.append({'index':i,'cycles':elapsed,'mode':before_tick['mode'],'back_owner':low(0x90)[0]})
  if i==1:key(6,'release')
 assert all(v['mode']==0 for v in samples),samples
 e['credit_worklist_samples']=samples;e['maximum_sampled_cycles']=max(v['cycles'] for v in samples);assert e['maximum_sampled_cycles']<=27000
 assert state()['credits']==5,state()
 for owner in (0,1):
  observed=crop(owner);assert b''.join(observed[y*8:y*8+4] for y in range(8))==glyph(5),('second credit HUD',owner,observed.hex())
 e['second_counter_pixels']='5 white exact on both owners'
 # Rare phase boundary: force only the existing stage-pending input, then use real credit edges.
 go(ps['pft_ready']);c.call('write_memory',{'space':'physical','addr':0x38*8192+ms['STAGE_PENDING'],'data':'01'})
 wait('next-stage hold',lambda s:s['mode']==6 and s['context']==2)
 count=state()['credits'];key(5,'press');wait('next-stage credit preserves hold',lambda s:s['credits']==count+1 and s['mode']==6 and s['screen']==2);key(5,'release')
 wait('next-stage gameplay',lambda s:s['mode']==0 and s['context']==0)
 count=state()['credits'];key(6,'press');wait('credit after next-stage context clear',lambda s:s['credits']==count+1);assert state()['mode']==0;key(6,'release')
 # Terminal death is still allowed to hand off; credit must not substitute high scores.
 go(ps['presentation_flow_tick']);count=state()['credits'];c.call('write_memory',{'space':'physical','addr':0x38*8192+ms['DEATH_STATE'],'data':'04'})
 key(5,'press');wait('terminal death retains game-over destination',lambda s:s['screen']==4 and s['credits']==count+1);key(5,'release')
 e['forced_boundary_coverage']='stage pending -> credited level -> cleared context gameplay; terminal death -> game over'
 e['result']='pass'
except Exception as exc:e['result']='fail';e['failure']=f'{type(exc).__name__}: {exc}'
finally:c.close();m.stop(p);out.write_text(json.dumps(e,indent=2)+'\n')
print(json.dumps(e,indent=2))
if e['result']!='pass':raise SystemExit(1)
