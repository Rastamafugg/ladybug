from pathlib import Path
import hashlib
base=Path(__file__).resolve().parents[1]/'rsch014-ready-083/gdb_colour_cycle_probe.py'
source=base.read_text()
source=source.replace('p=argparse.ArgumentParser();',"p=argparse.ArgumentParser();p.add_argument('--gap-expect',choices=('baseline','blank'),required=True);p.add_argument('--qualifying-score',choices=('095000','085000'),required=True);",1)
start=source.index(' if a.credit_admission_only:\n');end=source.index(' if a.logo_clock:\n  logo_clock_probe();',start)
branch=r""" if a.credit_admission_only:
  phase('credited-menu-before-gap-reproduction')
  key('5',states=(1,));q=settled(3);key('5',states=(0,));check('natural menu admitted one credit',q['credits']==1)
  phase('credited-gameplay-before-qualifying-death')
  key('Return');await_state('ordinary credited entry',lambda q:q['mode']==0 and q['entry']==0 and q['live']==1)
  active_gameplay_identity()
  phase('qualifying-gameover-to-name-gap')
  score=bytes(int(a.qualifying_score[i:i+2],16) for i in (0,2,4))
  report['phases'][-1]['fixture']='Set only legal six-digit BCD SCORE='+a.qualifying_score+' and DEATH_STATE4 after natural credited entry; real game-over qualification, name installation and publication. No insertion rank, pending score, frame or cursor writes.'
  gdb([f'set {{unsigned char}}0x{0x1d+i:x}={v}' for i,v in enumerate(score)]+['set {unsigned char}0x4d=4'])
  await_state('published name screen',lambda q:q['mode']==8 and q['screen']==5 and q['pending']==0 and q['transaction']==0)
  low=(B/'ladybug-highscore-runtime.bin').read_bytes();helper=(B/'ladybug-highscore-helper.bin').read_bytes()
  commands=[f'dump binary memory {O}/gap-name-low.bin 0x300 0x{0x300+len(low):x}',
   'set $saved5=*(unsigned char*)0xffa5','set {unsigned char}0xffa5=0x23',f'dump binary memory {O}/gap-name-helper.bin 0xac40 0x{0xac40+len(helper):x}','set {unsigned char}0xffa5=$saved5',f'dump binary memory {O}/gap-name-dp.bin 0 0x300']
  for owner in (0,1):
   for i in range(4):commands += [f'set $p{i}=*(unsigned char*)0x{0xffa1+i:x}',f'set {{unsigned char}}0x{0xffa1+i:x}={0x30+i if owner==0 else 0x2c+i}']
   commands += [f'dump binary memory {O}/gap-name-owner-{owner}.bin 0x2000 0x9800']
   commands += [f'set {{unsigned char}}0x{0xffa1+i:x}=$p{i}' for i in range(4)]
  gdb(commands)
  check('full delivered low name owner equals current artifact',(O/'gap-name-low.bin').read_bytes()==low)
  check('full delivered mapped name owner equals current artifact',(O/'gap-name-helper.bin').read_bytes()==helper)
  dp=(O/'gap-name-dp.bin').read_bytes();rank=0 if a.qualifying_score=='095000' else 1
  check('actual ranking and pending score match fixture',dp[0xc9]==rank and dp[0xbf:0xc2]==score)
  sys.path.insert(0,str(ROOT/'scripts'));from verify_shared_text import values
  data=(B/'ladybug_shared_text.inc').read_text();font=values(data,'font','colour_lut');descriptors=values(data,'dynamic_descriptors','no_end')
  glyphs={digit:symbols(B/'ladybug-highscore-helper.map')['PRESENTATION_GLYPH_'+str(digit)] for digit in range(10)}
  check('all ten numeric glyph descriptors available',set(glyphs)==set(range(10)))
  def tile(digit):
   glyph,colour=descriptors[glyphs[digit]*2:glyphs[digit]*2+2];assert colour>0;mask=font[glyph*8:glyph*8+8]
   return bytes((colour if mask[row]&(128>>(col*2)) else 0)*16+(colour if mask[row]&(64>>(col*2)) else 0) for row in range(8) for col in range(4))
  def cells(frame,x,y):return [b''.join(frame[(y*8+row)*160+(x+col)*4:(y*8+row)*160+(x+col)*4+4] for row in range(8)) for col in range(6)]
  top='090000';expected_gap=[tile(int(d)) for d in top] if a.gap_expect=='baseline' else [bytes(32)]*6
  def verify_fields(prefix):
   for owner in (0,1):
    frame=(O/f'{prefix}-owner-{owner}.bin').read_bytes()
    check(prefix+' gap cells match '+a.gap_expect+' on owner'+str(owner),cells(frame,1,13)==expected_gap)
    check(prefix+' player score unchanged on owner'+str(owner),cells(frame,33,2)==[tile(int(d)) for d in a.qualifying_score])
    check(prefix+' top-right score unchanged on owner'+str(owner),cells(frame,33,6)==[tile(int(d)) for d in top])
  verify_fields('gap-name')
  phase('natural-name-owner-replay')
  owners=set();frames=set()
  while len(owners)<2 or len(frames)<8:
   assert time.monotonic()<deadline,'natural name replay deadline'
   q=snapshot();check('name mode remains active during replay',q['mode']==8 and q['screen']==5)
   owners.add(q['front']);frames.add(int.from_bytes((O/'dp.bin').read_bytes()[2:4],'big'));time.sleep(.08)
  check('natural replay publishes both FRONT owners',owners=={0,1})
  gdb([command.replace('gap-name-','gap-name-replay-') for command in commands])
  verify_fields('gap-name-replay')
  report['phases'][-1]['front_owners']=sorted(owners);report['phases'][-1]['distinct_frame_samples']=len(frames)
  report['phases'][-1]['rank']=rank;report['phases'][-1]['gap_value']=top if a.gap_expect=='baseline' else 'blank';report['phases'][-1]['pending_score']=a.qualifying_score
  report['status']='PASS-GAP-'+a.gap_expect.upper();raise SystemExit(0)
"""
source=source[:start]+branch+source[end:]
exec(compile(source,str(base)+'[gap-adapter]','exec'))
