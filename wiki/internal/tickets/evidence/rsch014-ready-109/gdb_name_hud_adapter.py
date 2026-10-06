"""Reuse the current colour/scratch observer with joint HUD assertions."""
from pathlib import Path
def verify_vegetable_records(records):
 names=('CUCUMBER','EGGPLANT','CARROT','RADISH','PARSLEY','TOMATO','PUMPKIN','BAMBOO SHOOT','JAPANESE RADISH','MUSHROOM','POTATO','ONION','CHINESE CABBAGE','TURNIP','RED PEPPER','CELERY','SWEET POTATO','HORSERADISH')
 assert len(records)==360,'eighteen20-byte records required'
 for index,name in enumerate(names):
  row=records[index*20:(index+1)*20]
  text=''.join(' ' if v==36 else str(v) if v<10 else chr(v+55) for v in row[:16]).strip()
  assert text==name,('vegetable ordering',index+1,text,name)
  assert row[16:]==bytes(int(v) for v in f'{1000+500*index:04d}'),('vegetable value',index+1)
 return 18

base=Path(__file__).with_name('gdb_name_colour_adapter.py');outer=base.read_text()
outer=outer[:outer.index("exec(compile(source,")]
outer=outer.replace("p.add_argument('--short-name-regression'", "p.add_argument('--last-part',type=int,choices=range(1,256),required=True);p.add_argument('--short-name-regression'",1)
outer=outer.replace("choices=('095000','085000','123456','097654')", "choices=('095000','085000','075000','065000','055000','045000','035000','025000','015000','123456','097654')",1)
outer=outer.replace("'set {unsigned char}0x4d=4']", "'set {unsigned char}0x4d=4',f'set {{unsigned char}}0x24={a.last_part}']",1)
outer=outer.replace("rank=1 if a.qualifying_score=='085000' else 0", "rank=max(0,9-int(a.qualifying_score[:2]))",1)
outer=outer.replace('name_tiles(pending_name,6)','name_tiles(pending_name,1)')
exec(compile(outer,str(base)+'[joint-hud-preparation]','exec'))
source=source.replace('name_tiles(pending_name,6)','name_tiles(pending_name,1)').replace('pending-name white cells','pending-name red cells')
sync=r"""  def capture_completed(commands):
   pc=main['mainloop']+5
   guard=' || '.join(f'*(unsigned char*)0x{pc+i:x}!={resident[pc-0xc000+i]}' for i in range(8))
   boundary=['set $capture_start=*(unsigned short*)0x2',f'break *0x{pc:x}', 'condition $bpnum *(unsigned char*)0xa5==8 && *(unsigned char*)0x91==0 && (((*(unsigned short*)0x2)-$capture_start)&65535)>=4','continue','if '+guard,'printf "CURRENT COMPLETED FRAME PC MISMATCH\\n"','quit 1','end','delete breakpoints']
   gdb(boundary+commands)
   report['phases'][-1]['capture_boundary']='Current guarded mainloop+5, four real frames after fixture, pending0; both buffers dumped in same stopped GDB batch. No PC/frame/owner writes.'
"""
source=source.replace("  phase('pending-name-fixture-natural-repaint')",sync+"  phase('pending-name-fixture-natural-repaint')",1)
source=source.replace('while len(owners)<2 or len(frames)<8:', 'while len(owners)<2 or len(frames)<8 or ((int.from_bytes((O/\"dp.bin\").read_bytes()[2:4],\"big\")-int.from_bytes(dp[2:4],\"big\"))&65535)<2*hm[\"PRESENTATION_NAME_ENTRY_TIMER_FRAMES\"]+4:',1)
source=source.replace("  gdb(commands)\n  check('full delivered", "  capture_completed(commands)\n  check('full delivered",1)
source=source.replace("  gdb([command.replace('gap-name-','gap-name-replay-')", "  capture_completed([command.replace('gap-name-','gap-name-replay-')",1)
source=source.replace("   gdb([command.replace('gap-name-','gap-name-short-')", "   capture_completed([command.replace('gap-name-','gap-name-short-')",1)
marker="  report['status']='PASS-NAME-FIELD-COLOURS-AUTHORITY';raise SystemExit(0)"
assert source.count(marker)==1
extra=r"""  phase('current-last-part-vegetable-value-and-rank-owner-fields')
  translation=values((B/'ladybug_stage_glyphs.inc').read_text(),'stage_source_glyphs','no_end')
  def raw_tile(code,pen):
   glyph=translation[code];mask=font[glyph*8:glyph*8+8]
   return bytes((pen if mask[row]&(128>>(col*2)) else 0)*16+(pen if mask[row]&(64>>(col*2)) else 0) for row in range(8) for col in range(4))
  clamp=min(18,max(1,a.last_part));record_offset=hm['stage_panel_records']-0xac40+(clamp-1)*20;points=helper[record_offset+16:record_offset+20]
  check('shown vegetable value record is four decimal digits',len(points)==4 and all(v<10 for v in points))
  part_codes=([36] if a.last_part<100 else [a.last_part//100])+[(a.last_part//10)%10,a.last_part%10]
  labels=((29,24,25),(2,23,13),(3,27,13),(4,29,17),(5,29,17),(6,29,17),(7,29,17),(8,29,17),(9,29,17));ordinal=labels[rank]
  import build_screen as screen
  authored=screen.compile_sprite_codes(ROOT/'assets/arcade/sprites.json',screen.VEGETABLE_CODES)[clamp-1]
  lut_offset=main['sprite_attr0_pairs']-0xc000;pairs=(B/'ladybug-runtime.rom').read_bytes()[lut_offset:lut_offset+16];assert len(pairs)==16
  vegetable=bytes(v for b in authored for v in (pairs[b>>4],pairs[b&15]));assert len(vegetable)==128
  def cell(frame,x,y):return b''.join(frame[(y*8+row)*160+x*4:(y*8+row)*160+x*4+4] for row in range(8))
  coverage=json.loads((B/'ladybug-presentation.json').read_text())['shared_text']['coverage'];eq=next(v for v in coverage if v['screen']=='enter-high-score' and v['x']==34 and v['y']==13);eqmask=bytes.fromhex(eq['mask'])
  equals=bytes((5 if eqmask[row]&(128>>(col*2)) else 0)*16+(5 if eqmask[row]&(64>>(col*2)) else 0) for row in range(8) for col in range(4))
  for owner in (0,1):
   frame=(O/f"{'gap-name-short' if a.short_name_regression else 'gap-name-replay'}-owner-{owner}.bin").read_bytes()
   check('three-position last part owner'+str(owner),[cell(frame,x,11) for x in (37,38,39)]==[raw_tile(v,3) for v in part_codes])
   check('matching vegetable four-digit green value owner'+str(owner),[cell(frame,x,13) for x in range(35,39)]==[raw_tile(v,5) for v in points])
   check('dark-green equals owner'+str(owner),cell(frame,34,13)==equals)
   actual=b''.join(frame[(12*8+row)*160+32*4:(12*8+row)*160+32*4+8] for row in range(16))
   check('authored final-part native vegetable owner'+str(owner),actual==vegetable)
   for row in (12,18):check('ordinal row'+str(row)+' owner'+str(owner),[cell(frame,x,row) for x in (1,2,3)]==[raw_tile(v,1) for v in ordinal])
  report['joint_hud']={'last_part':a.last_part,'shown_vegetable_index':clamp,'points_digits':list(points),'rank_zero_based':rank,'ordinal_raw_codes':list(ordinal),'owners':[0,1],'pending_name':'red1','part':'three positions, leading blank below100 and two digits with leading0','value':'shown vegetable record, green5 includingequals','native_vegetable_sha256':hashlib.sha256(vegetable).hexdigest()}
  report['status']='PASS-CURRENT-JOINT-LAST-PART-VEGETABLE-VALUE-RANK-OWNERS';raise SystemExit(0)
"""
source=source.replace(marker,extra,1)
exec(compile(source,str(base)+'[joint-last-part-fields]','exec'))
