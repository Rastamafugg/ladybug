"""Reuse joint HUD capture for the separately fitted BUG104 prefix."""
from pathlib import Path
base=Path(__file__).with_name('gdb_name_hud_adapter.py')
exec(compile(base.read_text().split('extra=r"""')[0],str(base)+'[104-preparation]','exec'))
source=source.replace('name_tiles(pending_name,1)','name_tiles(pending_name,6)').replace('pending-name red cells','pending-name white cells')
extra=r"""  phase('104-separate-prefix-last-part-field')
  translation=values((B/'ladybug_stage_glyphs.inc').read_text(),'stage_source_glyphs','no_end')
  codes=([36] if a.last_part<100 else [a.last_part//100])+[(a.last_part//10)%10,a.last_part%10]
  expected=[]
  for code in codes:
   glyph=translation[code];mask=font[glyph*8:glyph*8+8]
   expected.append(bytes((3 if mask[y]&(128>>(j*2)) else 0)*16+(3 if mask[y]&(64>>(j*2)) else 0) for y in range(8) for j in range(4)))
  for owner in (0,1):
   frame=(O/f'gap-name-replay-owner-{owner}.bin').read_bytes()
   actual=[b''.join(frame[(11*8+y)*160+x*4:(11*8+y)*160+x*4+4] for y in range(8)) for x in (37,38,39)]
   check('104 actual final part owner'+str(owner),actual==expected)
  report['part_prefix']={'last_part':a.last_part,'codes':codes,'owners':[0,1],'rank':rank,'scope':'104-only stage source plus integrated107 generator prerequisite;105/106/108/110 unimplemented'}
  report['status']='PASS-104-SEPARATE-PREFIX-LAST-PART-OWNERS';raise SystemExit(0)
"""
source=source.replace(marker,extra,1)
exec(compile(source,str(base)+'[104-prefix]','exec'))
