from pathlib import Path
base=Path('/mnt/e/projects/ladybug/wiki/internal/tickets/evidence/rsch014-ready-083/gdb_colour_cycle_probe.py')
source=base.read_text()
source=source.replace('p=argparse.ArgumentParser();',"p=argparse.ArgumentParser();p.add_argument('--succession-releases',action='store_true');p.add_argument('--succession-deaths',action='store_true');p.add_argument('--succession-imminent',action='store_true');",1)
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
  for part in ((9,) if (a.succession_releases or a.succession_deaths) else (9,10,13,14,9)):
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
  if a.succession_releases or a.succession_deaths:
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
  if a.succession_deaths:
   phase('two-real-skull-arrivals-preserve-cursor-deadline')
   report['phases'][-1]['fixture']='Legal one-edge predecessors for release-created types3/4; neutral distant player. No PC, frame clock, type, cursor, pending or deadline writes.'
   tick=main['enemy_tick'];after=am['atb_after_player']
   commands=[f'break *0x{tick:x}','condition 1 (*(unsigned char*)0 & 1)==0 && *(unsigned short*)0x5b==0 && *(unsigned char*)0x4d==0','continue']+live_pc_guard(tick,resident,0xc000)+[
    'delete breakpoints',f'dump binary memory {O}/death-before-dp.bin 0 0x300','set $save5=*(unsigned char*)0xffa5','set {unsigned char}0xffa5=0x34',
    f'dump binary memory {O}/death-before-entities.bin 0xa380 0xa400',f'dump binary memory {O}/death-before-actors.bin 0xa470 0xa490',f'dump binary memory {O}/death-before-state.bin 0xa89d 0xa8a0','set {unsigned char}0xffa5=$save5']
   gdb(commands);dp0=(O/'death-before-dp.bin').read_bytes();actors=(O/'death-before-actors.bin').read_bytes();state0=(O/'death-before-state.bin').read_bytes()
   check('four release-created actors still active before rare path',dp0[0x58]==4 and state0[0]==4)
   sys.path.insert(0,str(base.parent.parent/'rsch014-ready-086'));from bug086_skull_fixture import plan
   maze=json.loads((ROOT/'assets/arcade/maze.json').read_text());entities=(O/'death-before-entities.bin').read_bytes()[:dp0[0x32]*4]
   fixture=plan(maze,entities,actors);report['phases'][-1]['fixture_plan']=fixture
   commands=[f'break *0x{tick:x}','condition 1 (*(unsigned char*)0 & 1)==0 && *(unsigned short*)0x5b==0 && *(unsigned char*)0x4d==0','continue']+live_pc_guard(tick,resident,0xc000)+[
    'delete breakpoints',f'dump binary memory {O}/death-atomic-before-dp.bin 0 0x300','set $save5=*(unsigned char*)0xffa5','set {unsigned char}0xffa5=0x34',f'dump binary memory {O}/death-atomic-before-state.bin 0xa89d 0xa8a0']
   for target in fixture['actors']:
    slot=target['slot']; entity=target['entity_index']; expected=int(target['record'][:2],16)
    commands += [f'if *(unsigned char*)0x{0xa470+slot*8:x} != {expected} || *(unsigned char*)0x{0xa380+entity*4+2:x} != 1','echo STALE-FIXTURE-FAIL\\n','quit 1','end']
   commands += ['if *(unsigned char*)0x58 != 4','echo ACTIVE-PRECONDITION-FAIL\\n','quit 1','end']
   for target in fixture['actors']:
    for off,value in enumerate(bytes.fromhex(target['record'])):commands.append(f'set {{unsigned char}}0x{0xa470+target["slot"]*8+off:x}={value}')
   commands+=['set {unsigned char}0xffa5=$save5']
   if a.succession_imminent:
    commands += ['set {unsigned char}0x4a=1','set {unsigned char}0x4b=91',f'dump binary memory {O}/death-atomic-before-dp.bin 0 0x300']
   sx,sy=fixture['safe_player']
   for addr,value in [(9,sx),(10,sy),(0x18,1),(5,255),(6,255),(15,255),(0x6b,0)]:commands.append(f'set {{unsigned char}}0x{addr:x}={value}')
   commands += [f'set {{unsigned short}}0xb={fixture["player_pointer"]}',f'break *0x{after:x}','continue']+live_pc_guard(after,active,0x38f)+[
    'delete breakpoints',f'dump binary memory {O}/death-after-dp.bin 0 0x300','set $save5=*(unsigned char*)0xffa5','set {unsigned char}0xffa5=0x34',
    f'dump binary memory {O}/death-after-entities.bin 0xa380 0xa400',f'dump binary memory {O}/death-after-actors.bin 0xa470 0xa490',f'dump binary memory {O}/death-after-state.bin 0xa89d 0xa8a0','set {unsigned char}0xffa5=$save5']
   if a.succession_imminent:
    commands += [f'break *0x{am["atb_after_timers"]:x}','continue']+live_pc_guard(am['atb_after_timers'],active,0x38f)+['delete breakpoints',f'dump binary memory {O}/imminent-after-dp.bin 0 0x300','set $save5=*(unsigned char*)0xffa5','set {unsigned char}0xffa5=0x34',f'dump binary memory {O}/imminent-after-actors.bin 0xa470 0xa490',f'dump binary memory {O}/imminent-after-state.bin 0xa89d 0xa8a0','set {unsigned char}0xffa5=$save5']
   gdb(commands);dp0=(O/'death-atomic-before-dp.bin').read_bytes();state0=(O/'death-atomic-before-state.bin').read_bytes();dp1=(O/'death-after-dp.bin').read_bytes();records=(O/'death-after-actors.bin').read_bytes();state1=(O/'death-after-state.bin').read_bytes();ent1=(O/'death-after-entities.bin').read_bytes()
   check('both selected skulls consumed by actual enemy tick',all(ent1[t['entity_index']*4+2]==0 for t in fixture['actors']))
   check('both actors die and latest type4 becomes pending',records[16]==records[24]==0 and dp1[0x58]==2 and state1[1]==3)
   check('normal cursor and all deadline fields unchanged by death',state1[0]==state0[0] and dp1[0x4a:0x4d]==dp0[0x4a:0x4d])
   report['phases'][-1]['before_after']={'state_before':state0.hex(),'state_after':state1.hex(),'deadline_before':list(dp0[0x4a:0x4d]),'deadline_after':list(dp1[0x4a:0x4d])}
   if a.succession_imminent:
    dp2=(O/'imminent-after-dp.bin').read_bytes();actors2=(O/'imminent-after-actors.bin').read_bytes();state2=(O/'imminent-after-state.bin').read_bytes()
    check('imminent actual timer respawns latest type4 after both deaths',actors2[16]==0x31 and actors2[24]==0 and dp2[0x58]==3 and state2[0]==4 and state2[1]==0xce)
    check('imminent existing deadline reload and phase rollover',dp2[0x4a:0x4d]==bytes((3,0,dp0[0x4c]^1)))
    report['phases'][-1]['imminent_after']={'state':state2.hex(),'deadline':list(dp2[0x4a:0x4d]),'active':dp2[0x58]}
    report['status']='PASS-CURRENT-IMMINENT-DEATH-TIMER';raise SystemExit(0)
   phase('latest-replacement-then-normal-succession-on-due-timers')
   report['phases'][-1]['fixture']='At guarded perimeter_timer_tick set only due BOX_TIMER1/BOX_INDEX91. No actor type, pending, cursor, phase, PC or frame-clock writes.'
   results=[]
   for seq,(kind,slot,cursor,active_count) in enumerate(((3,2,4,3),(0,3,5,4))):
    timer=main['perimeter_timer_tick'];release=em['enemy_release_impl']
    commands=[f'break *0x{timer:x}','continue']+live_pc_guard(timer,resident,0xc000)+['delete breakpoints',f'dump binary memory {O}/replacement-{seq}-before-dp.bin 0 0x300','set {unsigned char}0x4a=1','set {unsigned char}0x4b=91',f'break *0x{release:x}','continue']+live_pc_guard(release,enemy,0x800)+['delete breakpoints',f'break *0x{am["atb_after_timers"]:x}','continue']+live_pc_guard(am['atb_after_timers'],active,0x38f)+['delete breakpoints',f'dump binary memory {O}/replacement-{seq}-after-dp.bin 0 0x300','set $save5=*(unsigned char*)0xffa5','set {unsigned char}0xffa5=0x34',f'dump binary memory {O}/replacement-{seq}-records.bin 0xa470 0xa490',f'dump binary memory {O}/replacement-{seq}-state.bin 0xa89d 0xa8a0','set {unsigned char}0xffa5=$save5']
    gdb(commands);before=(O/f'replacement-{seq}-before-dp.bin').read_bytes();dp=(O/f'replacement-{seq}-after-dp.bin').read_bytes();records=(O/f'replacement-{seq}-records.bin').read_bytes();state=(O/f'replacement-{seq}-state.bin').read_bytes();raw=(kind<<4)|1
    check('due replacement/normal type in expected reused slot',records[slot*8]==raw)
    check('replacement preserves cursor then normal successor advances',state[0]==cursor and state[1]==((~raw)&255) and dp[0x58]==active_count)
    check('replacement timer follows existing rollover',dp[0x4a:0x4d]==bytes((3,0,before[0x4c]^1)))
    results.append({'type':kind+1,'slot':slot,'state':state.hex(),'deadline':list(dp[0x4a:0x4d])})
   report['phases'][-1]['results']=results

  report['status']='PASS-CURRENT-GROUP-RESET-SELECTOR';report['limits']=['Initial den FRONT pixels and natural owner replay pass; roaming pixels and death/deadline cases remain separate.','Stage/deadline predecessors are disclosed, not earned multi-level play.'];raise SystemExit(0)
"""
source=source[:start]+branch+source[end:]
exec(compile(source,str(base)+'[succession-group-adapter]','exec'))
