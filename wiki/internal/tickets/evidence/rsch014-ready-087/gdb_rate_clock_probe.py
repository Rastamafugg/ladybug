"""Reuse the GDB/X11 core for actual enemy-callback clock boundary probes.

This prepares the freeze/death scenario only. It does not replace physical
displacement, legal reversal, natural initialization, or cost acceptance.
"""
from pathlib import Path
base=Path(__file__).resolve().parents[1]/'rsch014-ready-083/gdb_colour_cycle_probe.py'
source=base.read_text()
source=source.replace("p=argparse.ArgumentParser();","p=argparse.ArgumentParser();p.add_argument('--rate-stage',type=int,choices=(1,17),required=True);p.add_argument('--full-freeze',action='store_true');p.add_argument('--natural-reset',action='store_true');p.add_argument('--movement',action='store_true');",1)
source=source.replace("xlib=c.CDLL('libX11.so.6');", "assert a.credit_admission_only,'rate probe requires --credit-admission-only'\nassert all((B/name).is_file() for name in ('ladybug-enemy-runtime.rom','ladybug-enemy-runtime.map','ladybug-rate-helper.bin','ladybug-rate-helper.map')),'required current artifacts missing before launch'\nxlib=c.CDLL('libX11.so.6');",1)
start=source.index(' if a.credit_admission_only:\n')
end=source.index(' if a.logo_clock:\n  logo_clock_probe();',start)
branch=r''' if a.credit_admission_only:
  phase('current-rate-credited-gameplay')
  key('5');settled(3)
  gdb([f'set {{unsigned char}}0xeb={a.rate_stage}'])
  report['phases'][-1]['fixture']='Seed legal next-game part setting before Enter; real credited level-start and gameplay. No direct STAGE write.'
  if a.natural_reset:
   import threading
   phase('current-natural-credited-rate-reset')
   initial_enemy=(B/'ladybug-enemy-runtime.rom').read_bytes();initial_rate=(B/'ladybug-rate-helper.bin').read_bytes()
   def enter_after_break_arm():
    time.sleep(0.5);key('Return')
   entering=threading.Thread(target=enter_after_break_arm);entering.start()
   try:
    gdb([f'break *0x{main["init_enemy"]:x}','continue']+live_pc_guard(main['init_enemy'],resident,0xc000)+[f'dump binary memory {O}/natural-init-mapping.bin 0xffa0 0xffa8',f'dump binary memory {O}/natural-init-helper-destination.bin 0xa3b0 0xa469','delete breakpoints','tbreak *0xa463','continue']+live_pc_guard(0xa459,initial_rate,0xa3b0)+['delete breakpoints','tbreak *0x0800','continue']+live_pc_guard(0x0800,initial_enemy,0x0800)+[f'dump binary memory {O}/natural-rate-init.bin 0 0x300','delete breakpoints'])
   finally:entering.join(timeout=1)
   natural=(O/'natural-rate-init.bin').read_bytes()
   initial_offsets=(0,2,4,1,3,5,6,8,5,7,9,10,11,8,12,13,14);offset=initial_offsets[a.rate_stage-1]
   addend=0 if offset<6 else 0x33 if offset<12 else 0x80 if offset<15 else 0xcc
   check('natural credited stage initializes exact rate state before enemy init',natural[0x24]==a.rate_stage and list(natural[0x29b:0x2a0])==[96,0,0,addend,0])
   report['natural_reset']={'stage':a.rate_stage,'rate_state':list(natural[0x29b:0x2a0]),'fixture':'Only legal next-game part option; real Enter and shim, no rate/actor/frame/PC/stack writes.'}
  else:key('Return')
  await_state('ordinary credited entry',lambda q:q['mode']==0 and q['entry']==0 and q['live']==1)
  active_gameplay_identity()
  enemy=symbols(B/'ladybug-enemy-runtime.map');rate=symbols(B/'ladybug-rate-helper.map')
  enemy_bytes=(B/'ladybug-enemy-runtime.rom').read_bytes();rate_bytes=(B/'ladybug-rate-helper.bin').read_bytes()
  check('approved185-byte helper identity',len(rate_bytes)==185 and hashlib.sha256(rate_bytes).hexdigest()=='609e0e8199a17c5d9a6bf35f7a3f0cddeb8ba029bdb5b8fa6bf2eed6b9efc00c')
  tick=enemy['enemy_tick_impl'];call=enemy['et_find_movement'];render=enemy['et_render_test']
  check('compiled current call targets fixed helper',enemy_bytes[call-0x800:call-0x800+3]==bytes.fromhex('bda3c5'))
  check('compiled init targets reset/tail shim',resident[main['init_enemy']-0xc000:main['init_enemy']-0xc000+3]in (bytes.fromhex('bda463'),bytes.fromhex('7ea463')))
  phase('current-live-helper-and-active-enemy-predecessor')
  raw=gdb([f'break *0x{tick:x}','condition $bpnum *(unsigned char*)0x58>0 && *(unsigned char*)0x4d==0 && *(unsigned char*)0xa5==0','continue']+live_pc_guard(tick,enemy_bytes,0x800)+['delete breakpoints','if (*(unsigned char*)0xffa5&63)!=0x34','quit 1','end',f'dump binary memory {O}/rate-live.bin 0xa3b0 0xa469',f'dump binary memory {O}/rate-predecessor-dp.bin 0 0x300'])
  check('live immutable helper equals current authored/staged helper',(O/'rate-live.bin').read_bytes()==rate_bytes)
  dp=(O/'rate-predecessor-dp.bin').read_bytes();check('real selected part and active enemy reached',dp[0x24]==a.rate_stage and dp[0x58]>0)
  offsets=(0,2,4,1,3,5,6,8,5,7,9,10,11,8,12,13,14)
  def selected(bucket):
   value=min(15,offsets[a.rate_stage-1]+(bucket>>4))
   return 0 if value<6 else 0x33 if value<12 else 0x80 if value<15 else 0xcc
  if a.movement:
   phase('current-rate12-consecutive-physical-record-callbacks')
   commands=[f'break *0x{tick:x}','continue']+live_pc_guard(tick,enemy_bytes,0x800)+['delete breakpoints']
   for number in range(12):
    commands += ['set $movement_s=$s','set $movement_caller=*(unsigned short*)$s',f'dump binary memory {O}/movement-{number}-before.bin 0xa470 0xa490',f'dump binary memory {O}/movement-{number}-state.bin 0 0x300',f'tbreak *0x{call+3:x}','continue']+live_pc_guard(call+3,enemy_bytes,0x800)+[f'printf "MOVEMENT_DUE_{number}=%u\\n",($cc&4)==0','tbreak *$movement_caller','continue','if $s!=$movement_s+2','quit 1','end',f'dump binary memory {O}/movement-{number}-after.bin 0xa470 0xa490']
    if number<11:commands += [f'tbreak *0x{tick:x}','continue']
   raw=gdb(commands);movement=[]
   for number in range(12):
    before=(O/f'movement-{number}-before.bin').read_bytes();after=(O/f'movement-{number}-after.bin').read_bytes();state=(O/f'movement-{number}-state.bin').read_bytes();due=int(re.search(f'MOVEMENT_DUE_{number}=(\d+)',raw).group(1))
    check('movement sample is ordinary unfrozen credited gameplay',state[0x4d]==0 and int.from_bytes(state[0x5b:0x5d],'big')==0 and state[0xa5]==0 and state[0xa7]==1)
    actors=[]
    for slot in range(4):
     previous=before[slot*8:slot*8+8];current=after[slot*8:slot*8+8]
     if not previous[0]:continue
     check('existing actor survives isolated movement callback',current[0]==previous[0])
     direction=previous[7];expected_step=(-320,1,320,-1)[direction] if direction<4 and due else 0
     expected_pointer=(int.from_bytes(previous[1:3],'big')+expected_step)&65535
     check('actual native origin takes exactly one two-pixel step per admitted callback',int.from_bytes(current[1:3],'big')==expected_pointer)
     actors.append({'slot':slot,'direction_before':direction,'packed_pointer_step':expected_step,'native_pixels':2 if expected_step else 0})
    check('movement callback has a real active actor',bool(actors))
    movement.append({'callback':number,'admitted':due,'actors':actors})
   report['movement']={'consecutive_callbacks':12,'samples':movement,'fixture':'No rate,actor,frame,PC or stack writes. Actual record origins; published FRONT replay is separate.'}
  if a.full_freeze:
   phase('current-rate-full300-freeze')
   commands=[f'break *0x{tick:x}','continue']+live_pc_guard(tick,enemy_bytes,0x800)+['delete breakpoints','set {unsigned short}0x5b=300','set {unsigned char}0x29b=96','set {unsigned char}0x29c=0','set {unsigned char}0x29d=90',f'set {{unsigned char}}0x29e={selected(0)}','set {unsigned char}0x29f=1',f'dump binary memory {O}/full-freeze-before.bin 0xa470 0xa490',f'break *0x{tick:x}','condition $bpnum *(unsigned short*)0x5b==0','continue']+live_pc_guard(tick,enemy_bytes,0x800)+[f'dump binary memory {O}/full-freeze-after.bin 0xa470 0xa490',f'dump binary memory {O}/full-freeze-dp.bin 0 0x300','delete breakpoints']
   gdb(commands)
   frozen=(O/'full-freeze-dp.bin').read_bytes()
   check('no death/reset substitutes for freeze expiry',frozen[0x4d]==0)
   before_records=(O/'full-freeze-before.bin').read_bytes();after_records=(O/'full-freeze-after.bin').read_bytes();spawned=[]
   for slot in range(4):
    previous=before_records[slot*8:slot*8+8];current=after_records[slot*8:slot*8+8]
    if previous[0] or not current[0]:check('frozen existing or empty record unchanged',current==previous)
    else:
     check('new frozen release stays at authored den origin',current[0]&15==1 and int.from_bytes(current[1:3],'big')==enemy['ENEMY_FB'] and list(current[3:])==[0,12,12,0,0])
     spawned.append(slot)
   check('all300 actual callbacks hold existing enemy origins including final thaw',all(before_records[i:i+8]==after_records[i:i+8] for i in range(0,32,8) if before_records[i]))
   check('300 callbacks advance elapsed timer and bucket while fraction phase hold',list(frozen[0x29b:0x2a0])==[36,4,90,selected(0),1])
   report['full_freeze']={'callbacks':300,'elapsed_timer':36,'elapsed_bucket':4,'fraction':90,'phase':1,'freeze_after':0,'existing_records_held':True,'new_frozen_den_slots':spawned,'fixture':'Only legal freeze/rate boundary state; actual enemy callbacks, no actor/frame/PC/stack writes. Pixel-origin replay separate.'}
  cases=[('rollover-frozen',2,1,15,0x5a,0xcc,1,0),('saturation-rollover-frozen',2,1,239,0xa5,0xcc,1,0),('saturated-expiry',2,1,240,0x6b,0xcc,1,0),('saturated-nonexpiry',2,2,240,0x6b,0xcc,1,0),('thaw-one-to-zero',1,2,4,0x40,0x33,1,0),('no-carry-first-phase',0,2,4,0,0,0,0),('no-carry-second-phase',0,2,4,0,0,1,0),('fractional-carry',0,2,4,0xf0,0x33,1,0),('death-bypass',2,1,15,0x40,0x33,1,1)]
  samples=[]
  for name,freeze,timer,bucket,frac,addend,alternating,death in cases:
   phase('current-rate-'+name)
   commands=[f'break *0x{tick:x}','continue']+live_pc_guard(tick,enemy_bytes,0x800)+['delete breakpoints','set $rate_s=$s','set $rate_caller=*(unsigned short*)$s',f'set {{unsigned short}}0x5b={freeze}',f'set {{unsigned char}}0x4d={death}']
   commands += [f'set {{unsigned char}}0x{0x29b+i:x}={value}' for i,value in enumerate((timer,bucket,frac,addend,alternating))]
   commands += [f'dump binary memory {O}/rate-before-table.bin 0xa470 0xa490']
   if not death:
    commands += [f'tbreak *0x{call+3:x}','continue']+live_pc_guard(call+3,enemy_bytes,0x800)+['printf "RATE_DUE=%u\\n",($cc&4)==0']
   # First death callback returns via existing reset; do not wait for render on a later callback.
   commands += ['tbreak *$rate_caller','continue','if $s!=$rate_s+2','quit 1','end',f'dump binary memory {O}/rate-after-dp.bin 0 0x300',f'dump binary memory {O}/rate-after-table.bin 0xa470 0xa490','delete breakpoints']
   raw=gdb(commands);after=(O/'rate-after-dp.bin').read_bytes()
   expected=[timer,bucket,frac,addend,alternating];due=None
   if not death:
    expected[0]=timer-1
    if timer==1:
     expected[0]=60;expected[1]=min(240,bucket+1)
     if bucket<240 and expected[1]&15==0:expected[3]=selected(expected[1])
    if not freeze:
     total=frac+expected[3];expected[2]=total&255
     if total>255:due=1
     else:due=alternating;expected[4]=1-alternating
    else:due=0
   check('actual callback rate state matches source boundary',list(after[0x29b:0x2a0])==expected)
   check('actual callback freeze duration and thaw match',int.from_bytes(after[0x5b:0x5d],'big')==(0 if death else max(0,freeze-1)))
   if due is not None:check('actual helper return admission matches',int(re.search(r'RATE_DUE=(\d+)',raw).group(1))==due)
   if freeze and not death:check('actual full enemy callback holds all records',(O/'rate-before-table.bin').read_bytes()==(O/'rate-after-table.bin').read_bytes())
   report['phases'][-1]['fixture']='Only approved legal rate boundary bytes029B..029F, freeze duration005B and death004D at a guarded real callback. No enemy/frame/owner/PC/stack writes.'
   samples.append({'case':name,'rate_after':expected,'due':due,'freeze_after':int.from_bytes(after[0x5b:0x5d],'big'),'records_held':True if freeze and not death else ('existing first-death reset' if death else 'separate displacement case required')})
  report['rate_clock']={'stage':a.rate_stage,'samples':samples,'remaining':'Pixel-origin freeze replay, physical movement/cadence, legal reversal, next-part initialization and matched cost scenarios remain separate requirements.'}
  report['status']='PASS-CURRENT-RATE-BOUNDARIES-NOT-FULL-ACCEPTANCE';raise SystemExit(0)
'''
source=source[:start]+branch+source[end:]
exec(compile(source,str(base)+'[current-rate-clock]','exec'))
