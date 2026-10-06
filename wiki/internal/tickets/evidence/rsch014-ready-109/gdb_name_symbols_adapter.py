from pathlib import Path
base=Path(__file__).resolve().parents[1]/'rsch014-ready-083/gdb_colour_cycle_probe.py'
source=base.read_text()
source=source.replace('p=argparse.ArgumentParser();',"p=argparse.ArgumentParser();p.add_argument('--symbol-edges',action='store_true');",1)
start=source.index(' if a.credit_admission_only:\n');end=source.index(' if a.logo_clock:\n  logo_clock_probe();',start)
branch=r""" if a.credit_admission_only:
  phase('credited-gameplay-before-name-symbols')
  key('5');settled(3);key('Return');await_state('ordinary credited game',lambda q:q['mode']==0 and q['entry']==0 and q['live']==1)
  active_gameplay_identity()
  phase('qualifying-gameover-to-name-symbols')
  report['phases'][-1]['fixture']='Legal BCD score095000 and DEATH_STATE4 after natural credited entry; real qualification/installation/publication. No pending name/length/rank writes.'
  gdb(['set {unsigned char}0x1d=9','set {unsigned char}0x1e=80','set {unsigned char}0x1f=0','set {unsigned char}0x4d=4'])
  await_state('real name screen publication',lambda q:q['mode']==8 and q['screen']==5 and q['pending']==0 and q['transaction']==0)
  low=(B/'ladybug-highscore-runtime.bin').read_bytes();lm=symbols(B/'ladybug-highscore-runtime.map');audio=(B/'ladybug-audio-runtime.bin').read_bytes();am=symbols(B/'ladybug-audio-runtime.map');hm=symbols(B/'ladybug-highscore-helper.map');cold=(B/'ladybug-presentation-cold.bin').read_bytes()
  meta=json.loads((B/'ladybug-presentation.json').read_text())['high_score_name_entry'];nodes=dict(zip(map(tuple,meta['node_cells']),meta['node_tile_ids']))
  mask_offset=hm['PRESENTATION_NAME_ENTRY_FULL_EDGE_MASK_TABLE'];expected=[];samples=[]
  helper=Path(__file__).resolve().with_name('x11_probe_key_edge.py')
  edge=lambda pressed:f'shell python3 {helper} {window} Right {pressed}'
  slots=[am['audio_slot'+str(i)] for i in range(4)]
  def audio_guard(address,length):
   out=[]
   for off,value in enumerate(audio[address-0xa000:address-0xa000+length]):
    out += [f'if *(unsigned char*)0x{address+off:x}!={value}',f'printf "SYMBOL-AUDIO-CODE-MISMATCH addr={address+off:04x} expected={value:02x} actual=%02x PAR5=%02x\\n",*(unsigned char*)0x{address+off:x},*(unsigned char*)0xffa5','quit 1','end']
   return out
  check('enqueue guard ends before mutable dot cache',am['audio_poll_dots']-am['audio_poll_enqueue']==5)
  check('write guard covers complete immutable STA/NOP/RTS body',am['audio_poll_enqueue']-am['audio_write']==8 and audio[am['audio_write']-0xa000:am['audio_poll_enqueue']-0xa000]==bytes.fromhex('b7ff511212121239'))
  def arrive(name,x,action='append'):
   cue={'append':2,'reject':0,'clear':9,'end':8}[action]
   phase('real-bottom-'+name+'-arrival-and-audio')
   check('authored reciprocal east/west legal predecessor',bool(cold[mask_offset+20*24+x-9]&2) and bool(cold[mask_offset+20*24+x-8]&8))
   report['phases'][-1]['fixture']='At byte-identified name_tick move only legal cursor position to west predecessor, zero movement progress/late-turn, neutral direction; actual host Right edge, name_advance and name_cell_arrival append. No name bytes/length, rank, score, frame, owner, clock or PC writes.'
   tick=lm['name_tick'];arrival=lm['name_cell_arrival'];ptr=0x2000+20*1280+(x-1)*4
   commands=[f'break *0x{tick:x}','condition 1 *(unsigned char*)0xa5==8','continue']+live_pc_guard(tick,low,0x300)+[
    'delete breakpoints',f'dump binary memory {O}/{name}-live-low.bin 0x300 0x{0x300+len(low):x}',
    f'set {{unsigned char}}0x9={x-1}','set {unsigned char}0xa=20',f'set {{unsigned short}}0xb={ptr}',f'set {{unsigned char}}0xe0={x-1}','set {unsigned char}0xdf=20','set {unsigned char}0xde=0','set {unsigned char}0x56=0','set {unsigned char}0x6=255','set {unsigned char}0xf=255',
    f'break *0x{arrival:x}',f'condition $bpnum *(unsigned char*)0x9=={x} && *(unsigned char*)0xa==20',edge(1),'continue']+live_pc_guard(arrival,low,0x300)+[
    'delete breakpoints','set $returnpc=*(unsigned short*)$s','tbreak *$returnpc','continue',edge(0),'delete breakpoints',
    f'dump binary memory {O}/{name}-after-arrival-dp.bin 0 0x300','set $n5=*(unsigned char*)0xffa5','set {unsigned char}0xffa5=0x34',f'dump binary memory {O}/{name}-pending.bin 0xafde 0xafe5','set {unsigned char}0xffa5=$n5','set $cue_count=0','set $psg_count=0','set $frame_start=*(unsigned short*)0x2',
    f'break *0x{am["audio_poll_enqueue"]:x}','condition $bpnum (*(unsigned char*)0xffa5 & 63)==0x3d && *(unsigned char*)0xa5==8 && ($a==2 || $a==9 || $a==8)','commands $bpnum','silent']+audio_guard(am['audio_poll_enqueue'],5)+[
    'set $cue_count=$cue_count+1','printf "SYMBOL-CUE=%u LENGTH=%u\\n",$a,*(unsigned char*)0xcb','continue','end',
    f'break *0x{am["audio_write"]:x}','condition $bpnum (*(unsigned char*)0xffa5 & 63)==0x3d && $cue_count>0 && ($a & 0x90)==0x90 && ($a & 15)<15 && ('+' || '.join(f'*(unsigned char*)0x{s:x}=={cue}' for s in slots)+')','commands $bpnum','silent']+audio_guard(am['audio_write'],8)+[
    'set $psg_count=$psg_count+1','printf "SYMBOL-AUDIBLE-PSG=%02x\\n",$a','continue','end',
    f'break *0x{main["mainloop"]+5:x}',f'condition $bpnum *(unsigned char*)0xa5=={5 if action=="end" else 8} && *(unsigned char*)0x91==0 && (((*(unsigned short*)0x2)-$frame_start)&65535)>=24','continue']+live_pc_guard(main['mainloop']+5,resident,0xc000)+[
    'printf "SYMBOL-COUNTS=%u,%u\\n",$cue_count,$psg_count','delete breakpoints',f'dump binary memory {O}/{name}-final-dp.bin 0 0x300']
   raw=gdb(commands);(O/(name+'-trace.log')).write_text(raw)
   check('full live name owner equals current artifact',(O/(name+'-live-low.bin')).read_bytes()==low)
   if action=='append':expected.append(nodes[(x,20)])
   elif action=='clear':expected.pop()
   pending=(O/(name+'-pending.bin')).read_bytes();dp=(O/(name+'-after-arrival-dp.bin')).read_bytes()
   check('real arrival appends exact registered symbol and length',dp[0xcb]==len(expected) and pending==bytes(expected)+bytes([hm['PRESENTATION_NAME_ENTRY_BLACK_TILE']])*(7-len(expected)))
   match=re.search(r'SYMBOL-COUNTS=(\d+),(\d+)',raw);assert match
   cues,psg=map(int,match.groups());check('one action cue or no cue for full rejection',cues==(0 if cue==0 else 1))
   emitted=[int(v) for v in re.findall(r'SYMBOL-CUE=(\d+)',raw)];check('exact action cue ID',emitted==([] if cue==0 else [cue]))
   if cue:check('action cue reaches correlated nonmute PSG output',psg>0)
   samples.append({'symbol':name,'action':action,'descriptor':nodes[(x,20)],'pending_name':pending.hex(),'length':dp[0xcb],'expected_cue':cue,'cue_count':cues,'nonmute_psg_writes_with_expected_cue_active':psg,'raw_trace_sha256':hashlib.sha256(raw.encode()).hexdigest()})
  for name,x in (('dot',15),('space',19),('heart',23)):arrive(name,x)
  phase('symbol-fields-both-natural-owners')
  owners=set();frames=set()
  while len(owners)<2 or len(frames)<8:
   assert time.monotonic()<deadline,'symbol owner replay deadline'
   q=snapshot();check('name stays active during natural replay',q['mode']==8 and q['screen']==5);owners.add(q['front']);frames.add(int.from_bytes((O/'dp.bin').read_bytes()[2:4],'big'));time.sleep(.08)
  sys.path.insert(0,str(ROOT/'scripts'));from verify_shared_text import values
  data=(B/'ladybug_shared_text.inc').read_text();font=values(data,'font','colour_lut');desc=values(data,'dynamic_descriptors','no_end')
  def tile(value,pen):
   if value==0:return bytes(32)
   glyph,colour=desc[value*2:value*2+2]
   if colour==0:
    native=cold[glyph*32:(glyph+1)*32];assert value==nodes[(19,20)] and native==bytes(32);return native
   mask=font[glyph*8:glyph*8+8]
   return bytes((pen if mask[row]&(128>>(col*2)) else 0)*16+(pen if mask[row]&(64>>(col*2)) else 0) for row in range(8) for col in range(4))
  for owner in (0,1):
   frame=front_frame(owner)
   for x,y,pen,label in ((1,19,6,'pending white'),(33,5,1,'first-place TOP red')):
    actual=[b''.join(frame[(y*8+row)*160+(x+col)*4:(y*8+row)*160+(x+col)*4+4] for row in range(8)) for col in range(7)]
    check(label+' exact symbol/blank pixels on owner'+str(owner),actual==[tile(v,pen) for v in expected]+[bytes(32)]*4)
  report['symbol_samples']=samples;report['symbol_owner_replay']={'owners':sorted(owners),'distinct_frames':len(frames),'pending_white_and_top_red':'exact dot/space/authored heart plus four blank cells on both owners'}
  if a.symbol_edges:
   for i in range(4):arrive('fill-dot-'+str(i),15)
   arrive('full-name-reject-dot',15,'reject');arrive('CL',11,'clear');arrive('END',27,'end')
   phase('END-natural-menu-commit-and-symbol-pixels')
   q=settled(3);check('END drains into natural high-score menu',q['mode']==5 and q['screen']==3)
   gdb(['set $commit5=*(unsigned char*)0xffa5','set {unsigned char}0xffa5=0x34',f'dump binary memory {O}/symbol-committed-top.bin 0xaf84 0xaf8e','set {unsigned char}0xffa5=$commit5'])
   record=(O/'symbol-committed-top.bin').read_bytes();check('committed rank-zero score and selected symbol bytes',record==bytes.fromhex('095000')+bytes(expected)+bytes([hm['PRESENTATION_NAME_ENTRY_BLACK_TILE']])*(7-len(expected)))
   for owner in (0,1):
    frame=front_frame(owner);actual=[b''.join(frame[(16+row)*160+(16+col)*4:(16+col)*4+(16+row)*160+4] for row in range(8)) for col in range(7)]
    check('committed menu TOP red symbol pixels owner'+str(owner),actual==[tile(v,1) for v in expected]+[bytes(32)]*(7-len(expected)))
   report['status']='PASS-ACTUAL-SYMBOLS-LIMIT-CL-END-AUDIO-OWNERS';report['limits']=['Legal high-score and cursor predecessors disclosed; no earned full-route claim.'];raise SystemExit(0)
  report['status']='PASS-ACTUAL-THREE-SYMBOLS-AUDIO-AND-OWNER-FIELDS';report['limits']=['Full-seven rejection and CL/END separate follow-up required; no Ready claim.','Stage qualification and movement predecessors are disclosed fixtures, not an earned high score or natural full route.'];raise SystemExit(0)
"""
source=source[:start]+branch+source[end:]
exec(compile(source,str(base)+'[name-symbols-adapter]','exec'))
