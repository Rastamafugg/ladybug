from pathlib import Path
base=Path('/mnt/e/projects/ladybug/wiki/internal/tickets/evidence/rsch014-ready-083/gdb_colour_cycle_probe.py')
source=base.read_text()
source=source.replace('p=argparse.ArgumentParser();',"p=argparse.ArgumentParser();p.add_argument('--succession-releases',action='store_true');",1)
start=source.index(' if a.credit_admission_only:\n');end=source.index(' if a.logo_clock:\n  logo_clock_probe();',start)
branch=r""" if a.credit_admission_only:
  phase('credited-menu-to-gameplay-before-succession')
  key('5');settled(3);key('Return');await_state('ordinary credited gameplay',lambda q:q['mode']==0 and q['entry']==0 and q['live']==1)
  active_gameplay_identity()
  enemy=(B/'ladybug-enemy-runtime.rom').read_bytes();helper=(B/'ladybug-enemy-helper-page34.bin').read_bytes();em=symbols(B/'ladybug-enemy-runtime.map');hm=symbols(B/'ladybug-enemy-helper-page34.map')
  sys.path.insert(0,str(ROOT/'scripts'));from build_screen import compile_enemy_sprites
  from build_sparse_sprites import expand_native_frame,GAMEPLAY_ENEMY_PEN_MAPS
  authored_frames=compile_enemy_sprites(ROOT/'assets/arcade/sprites.json')
  def preview_pixels(part,group):
   phase('actual-front-den-pixels-and-replay-part-'+str(part));fronts=set();samples=[]
   expected=[expand_native_frame(authored_frames[group*16+pose],GAMEPLAY_ENEMY_PEN_MAPS[group]) for pose in range(4)]
   while len(fronts)<2:
    assert time.monotonic()<deadline,'FRONT den replay deadline'
    entry=main['mainloop']
    commands=[f'break *0x{entry:x}','condition 1 *(unsigned char*)0xa5==0 && *(unsigned char*)0x91==0 && *(unsigned char*)0x58==0','continue']+live_pc_guard(entry,resident,0xc000)+[
     'delete breakpoints',f'dump binary memory {O}/preview-part-{part}-dp.bin 0 0x300',
     'set $fbbase=0x30-4*(*(unsigned char*)0x8f)']
    for i in range(4):commands += [f'set $saved{i}=*(unsigned char*)0x{0xffa1+i:x}',f'set {{unsigned char}}0x{0xffa1+i:x}=$fbbase+{i}']
    commands += [f'dump binary memory {O}/preview-part-{part}-frame.bin 0x2000 0x9800']
    commands += [f'set {{unsigned char}}0x{0xffa1+i:x}=$saved{i}' for i in range(4)]
    gdb(commands);dp=(O/f'preview-part-{part}-dp.bin').read_bytes();frame=(O/f'preview-part-{part}-frame.bin').read_bytes();owner=dp[0x8f]
    check('published FRONT belongs to expected ordinary part',dp[0x24]==part and dp[0xa5]==0 and dp[0x91]==0 and owner in (0,1))
    offset=em['ENEMY_FB']-0x2000;actual=b''.join(frame[offset+row*160:offset+row*160+8] for row in range(16));matches=[]
    for pose,native in enumerate(expected):
     opaque=[(idx,shift,(byte>>shift)&15) for idx,byte in enumerate(native) for shift in (4,0) if (byte>>shift)&15]
     if all((actual[idx]>>shift)&15==pen for idx,shift,pen in opaque):matches.append({'pose':pose,'opaque_pixels':len(opaque)})
    check('actual FRONT den pixels match authored selected enemy type',bool(matches))
    samples.append({'front':owner,'frames':int.from_bytes(dp[2:4],'big'),'selected_type':group+1,'matching_poses':matches,'crop_sha256':hashlib.sha256(actual).hexdigest()});fronts.add(owner)
   report['phases'][-1]['samples']=samples;report['phases'][-1]['qualification']='Atomically captured actual FRONT, stopped identified mainloop, no actors released; exact nontransparent authored north sprite pixels, both natural FRONT histories. No forced framebuffer or owner writes.'
  for part in ((9,) if a.succession_releases else (9,10,13,14,9)):
   phase('real-stage-init-reset-part-'+str(part))
   report['phases'][-1]['fixture']='At byte-identified resident mainloop set only legal STAGE predecessor and STAGE_PENDING; natural presentation next_stage and enemy_init_impl. No PC, rank, actor, framebuffer or clock writes.'
   reset=main['reset_enemy_state'];entry=main['mainloop']
   commands=[f'break *0x{entry:x}','continue']+live_pc_guard(entry,resident,0xc000)+['delete breakpoints',f'set {{unsigned char}}0x24={part-1}','set {unsigned char}0x26=1',f'break *0x{reset:x}','continue']+live_pc_guard(reset,resident,0xc000)+[
    'delete breakpoints',f'dump binary memory {O}/group-{part}-enemy.bin 0x800 0x{0x800+len(enemy):x}',
    'printf "RESET_CALLER=%04x PAR0=%02x PAR5=%02x\\n",*(unsigned short*)$s,*(unsigned char*)0xffa0,*(unsigned char*)0xffa5',
    'set $returnpc=*(unsigned short*)$s','tbreak *$returnpc','continue',
    f'dump binary memory {O}/group-{part}-dp.bin 0 0x300',
    'set $save5=*(unsigned char*)0xffa5','set {unsigned char}0xffa5=0x34',
    f'dump binary memory {O}/group-{part}-state.bin 0xa890 0xa900',
    f'dump binary memory {O}/group-{part}-records.bin 0xa470 0xa490',
    f'dump binary memory {O}/group-{part}-helper.bin 0xa8a0 0x{0xa8a0+len(helper):x}',
    'set {unsigned char}0xffa5=$save5']
   raw=gdb(commands);(O/f'group-{part}-reset.log').write_text(raw)
   check('full delivered enemy module matches current artifact',(O/f'group-{part}-enemy.bin').read_bytes()==enemy)
   check('full delivered page34 helper matches current artifact',(O/f'group-{part}-helper.bin').read_bytes()==helper)
   match=re.search(r'RESET_CALLER=([0-9a-fA-F]+) PAR0=([0-9a-fA-F]+) PAR5=([0-9a-fA-F]+)',raw)
   check('reset comes from true enemy_init_impl',bool(match) and int(match.group(1),16)==em['enemy_init_impl']+3)
   check('reset helper uses authored page34 mapping',int(match.group(2),16)&63==0x38 and int(match.group(3),16)&63==0x34)
   dp=(O/f'group-{part}-dp.bin').read_bytes();state=(O/f'group-{part}-state.bin').read_bytes();records=(O/f'group-{part}-records.bin').read_bytes()
   check('real next_stage installs intended part',dp[0x24]==part)
   check('all eight packed-reset fields are zero',all(dp[a]==0 for a in (0x4b,0x4c,0x58,0x59,0x5b,0x5c,0x60,0x61)))
   check('new succession state reset matches approved contract',state[13:16]==bytes((0,255,255)))
   check('real reset clears every actor record',records==bytes(32))
   check('old framebuffer pointers and restoration rings clear',state[:12]==bytes(12))
   phase('natural-stage-play-and-preview-part-'+str(part))
   await_state('ordinary gameplay after actual part handoff, next-stage context consumed',lambda q:q['mode']==0 and q['entry']==0 and q['live']==0)
   pc=hm['efn_preview_pack']
   commands=[f'break *0x{pc:x}','condition 1 (*(unsigned char*)0xffa5 & 63)==0x34','continue']+live_pc_guard(pc,helper,0xa8a0)+[
    'delete breakpoints','printf "GROUP_PREVIEW A=%02x CURSOR=%02x PENDING=%02x\\n",$a,*(unsigned char*)0xa89d,*(unsigned char*)0xa89e',
    f'dump binary memory {O}/group-{part}-preview-dp.bin 0 0x300']
   raw=gdb(commands);match=re.search(r'GROUP_PREVIEW A=([0-9a-fA-F]+) CURSOR=([0-9a-fA-F]+) PENDING=([0-9a-fA-F]+)',raw)
   check('real native preview selector marker reached',bool(match))
   offset=(part-1)&7;offset=offset-5 if offset>=5 else offset
   check('group preview base equals approved arcade formula',int(match.group(1),16)==offset)
   check('first preview retains zero normal cursor and no override',int(match.group(2),16)==0 and int(match.group(3),16)&128!=0)
   report['phases'][-1]['part']=part;report['phases'][-1]['expected_group']=[offset+i+1 for i in range(4)]
   preview_pixels(part,offset)
  if a.succession_releases:
   active=(B/'ladybug-adaptive-active.bin').read_bytes();am=symbols(B/'ladybug-adaptive-active.map')
   phase('four-ordered-real-timer-releases-part9');report['phases'][-1]['fixture']='Force only due BOX_TIMER1/BOX_INDEX91 at identified real perimeter_timer_tick entry; natural release wrapper, module and active-stage continuation. No actor type/cursor/pending/PC writes.'
   releases=[]
   for kind in range(4):
    timer=main['perimeter_timer_tick'];release=em['enemy_release_impl'];after=am['atb_after_timers']
    commands=[f'break *0x{timer:x}','continue']+live_pc_guard(timer,resident,0xc000)+['delete breakpoints',f'dump binary memory {O}/release-{kind}-before-dp.bin 0 0x300',
     'set {unsigned char}0x4a=1','set {unsigned char}0x4b=91',f'break *0x{release:x}','continue']+live_pc_guard(release,enemy,0x800)+[
     'delete breakpoints',f'break *0x{after:x}','continue']+live_pc_guard(after,active,0x38f)+[
     'delete breakpoints',f'dump binary memory {O}/release-{kind}-after-dp.bin 0 0x300',
     'set $save5=*(unsigned char*)0xffa5','set {unsigned char}0xffa5=0x34',
     f'dump binary memory {O}/release-{kind}-records.bin 0xa470 0xa490',f'dump binary memory {O}/release-{kind}-state.bin 0xa89d 0xa8a0','set {unsigned char}0xffa5=$save5']
    gdb(commands);before=(O/f'release-{kind}-before-dp.bin').read_bytes();dp=(O/f'release-{kind}-after-dp.bin').read_bytes();records=(O/f'release-{kind}-records.bin').read_bytes();state=(O/f'release-{kind}-state.bin').read_bytes()
    raw=(kind<<4)|1;check('real release stores ordered type in expected empty slot',records[kind*8]==raw)
    check('ordered normal cursor and negative pending complement match',state[0]==kind+1 and state[1]==((~raw)&255))
    check('active and total release counts grow naturally',dp[0x58]==kind+1 and dp[0x59]==kind+1)
    check('existing timer deadline rolls over normally',dp[0x4a:0x4d]==bytes((3,0,before[0x4c]^1)))
    releases.append({'type':kind+1,'slot':kind,'record':records[kind*8:kind*8+8].hex(),'cursor':state[0],'pending':state[1],'timer_after':list(dp[0x4a:0x4d])})
   report['phases'][-1]['releases']=releases
  phase('authored-roaming-front-pixels-both-natural-owners')
  report['phases'][-1]['fixture']='Separated legal reciprocal ungated edge starts for the four release-created types. Neutral distant legal player. Preserve types, cursor/pending/deadline/frame/owners; only actor legal position/progress/direction and capture validity are initialized. Actual movement/render and natural owner publication follow.'
  entry=main['enemy_tick']
  cmds=[f'break *0x{entry:x}','condition 1 (*(unsigned char*)0 & 1)==0 && *(unsigned char*)0x4d==0','continue']+live_pc_guard(entry,resident,0xc000)+['delete breakpoints','set $save5=*(unsigned char*)0xffa5','set {unsigned char}0xffa5=0x34',f'dump binary memory {O}/roam-fixture-entities.bin 0xa380 0xa400','set {unsigned char}0xffa5=$save5']
  gdb(cmds);entity=(O/'roam-fixture-entities.bin').read_bytes();skulls={(entity[i],entity[i+1]) for i in range(0,len(entity),4) if entity[i+2]==1};maze=json.loads((ROOT/'assets/arcade/maze.json').read_text());nav=maze['maze_nav'];gates=maze['gate_owner'];points=[]
  for y in range(12,22):
   for x in range(2,22):
    if gates[y][x] or (x,y) in skulls or abs(x-22)+abs(y-22)<8:continue
    if any(abs(x-q['x'])+abs(y-q['y'])<6 for q in points):continue
    for direction,(dx,dy) in enumerate(((0,-1),(1,0),(0,1),(-1,0))):
     nx,ny=x+dx,y+dy
     if not(0<=nx<24 and 0<=ny<24) or gates[ny][nx] or (nx,ny) in skulls:continue
     if nav[y][x]&(1<<direction) and nav[ny][nx]&(1<<((direction+2)&3)):
      points.append({'x':x,'y':y,'direction':direction});break
    if len(points)==4:break
   if len(points)==4:break
  assert len(points)==4,'four separated legal roaming edges unavailable'
  report['phases'][-1]['fixture_points']=points
  commands=[f'break *0x{entry:x}','condition 1 (*(unsigned char*)0 & 1)==0 && *(unsigned char*)0x4d==0','continue']+live_pc_guard(entry,resident,0xc000)+['delete breakpoints','set $save5=*(unsigned char*)0xffa5','set {unsigned char}0xffa5=0x34']
  for slot,q in enumerate(points):
   ptr=0x57ec+(q['x']-12)*4+(q['y']-12)*1280
   commands += [f'if *(unsigned char*)0x{0xa470+slot*8:x} != {(slot<<4)|1}','echo RELEASE-TYPE-PRECONDITION-FAIL\\n','quit 1','end']
   for off,value in enumerate(bytes((ptr>>8,ptr&255,0,q['x'],q['y'],0,q['direction'])),1):commands.append(f'set {{unsigned char}}0x{0xa470+slot*8+off:x}={value}')
  commands += ['set {unsigned char}0xffa5=$save5','set {unsigned char}0x9=22','set {unsigned char}0xa=22','set {unsigned short}0xb=35188','set {unsigned char}0x18=1','set {unsigned char}0x5=255','set {unsigned char}0x6=255','set {unsigned char}0xf=255']
  gdb(commands)
  seen=set();samples=[];report['phases'][-1]['samples']=samples
  while len(seen)<8:
   assert time.monotonic()<deadline,'required roaming type/owner samples not all reached'
   entry=main['mainloop']
   commands=[f'break *0x{entry:x}','condition 1 *(unsigned char*)0xa5==0 && *(unsigned char*)0x91==0','continue']+live_pc_guard(entry,resident,0xc000)+['delete breakpoints',f'dump binary memory {O}/roam-dp.bin 0 0x300','set $owner=*(unsigned char*)0x8f','set $save5=*(unsigned char*)0xffa5','set {unsigned char}0xffa5=0x34','set $meta=0xa900+0x100*$owner',f'dump binary memory {O}/roam-ledger.bin $meta $meta+0x100','set {unsigned char}0xffa5=$save5']
   for i in range(4):commands += [f'set $p{i}=*(unsigned char*)0x{0xffa1+i:x}',f'set {{unsigned char}}0x{0xffa1+i:x}=0x30-4*$owner+{i}']
   commands += [f'dump binary memory {O}/roam-front.bin 0x2000 0x9800']
   commands += [f'set {{unsigned char}}0x{0xffa1+i:x}=$p{i}' for i in range(4)]
   gdb(commands);dp=(O/'roam-dp.bin').read_bytes();ledger=(O/'roam-ledger.bin').read_bytes();frame=(O/'roam-front.bin').read_bytes();owner=dp[0x8f]
   check('actual FRONT ledger valid in ordinary part9 four-enemy gameplay',owner in (0,1) and ledger[0]&1 and dp[0xa5]==0 and dp[0x91]==0 and dp[0x24]==9 and dp[0x58]==4 and dp[0x4d]==0)
   records=[ledger[8+slot*8:16+slot*8] for slot in range(4)]
   def rect(ptr):
    off=ptr-0x2000;return (off%160,off//160)
   def overlaps(a,b):return abs(a[0]-b[0])<8 and abs(a[1]-b[1])<16
   for slot,record in enumerate(records):
    if not record[0] or not record[6]:continue
    kind=record[0]>>4;ptr=int.from_bytes(record[1:3],'big');direction=record[7];xy=rect(ptr)
    if (kind,owner) in seen or ptr==em['ENEMY_FB']:continue
    check('published roaming type and direction within authored range',kind in range(4) and direction in range(4))
    if any(other[0] and other[6] and overlaps(xy,rect(int.from_bytes(other[1:3],'big'))) for other in records[slot+1:]):continue
    if ledger[2] and overlaps(xy,rect(int.from_bytes(ledger[4:6],'big'))):continue
    off=ptr-0x2000
    check('unoccluded roaming crop within framebuffer',off>=0 and xy[0]<=152 and xy[1]<=176)
    actual=b''.join(frame[off+row*160:off+row*160+8] for row in range(16));matches=[]
    for pose in range(4):
     native=expand_native_frame(authored_frames[kind*16+direction*4+pose],GAMEPLAY_ENEMY_PEN_MAPS[kind]);opaque=[(i,shift,(v>>shift)&15) for i,v in enumerate(native) for shift in (4,0) if (v>>shift)&15]
     if all((actual[i]>>shift)&15==pen for i,shift,pen in opaque):matches.append(pose)
    check('unoccluded actual FRONT roaming pixels equal authored type',bool(matches))
    seen.add((kind,owner));samples.append({'type':kind+1,'owner':owner,'slot':slot,'direction':direction,'ptr':ptr,'poses':matches,'crop_sha256':hashlib.sha256(actual).hexdigest()})
   time.sleep(.1)
  report['phases'][-1]['samples']=samples;report['phases'][-1]['qualification']='Actual FRONT and matching page34 owner ledger captured in one guarded stop; all four type/owner pairs required. Exact opaque authored pixels; overlapping higher slots/player excluded geometrically. No actor/frame/owner writes.'
  report['status']='PASS-CURRENT-GROUP-RESET-SELECTOR';report['limits']=['Initial den FRONT pixels and natural owner replay pass; roaming pixels and death/deadline cases remain separate.','Stage/deadline predecessors are disclosed, not earned multi-level play.'];raise SystemExit(0)
"""
source=source[:start]+branch+source[end:]
exec(compile(source,str(base)+'[succession-group-adapter]','exec'))
