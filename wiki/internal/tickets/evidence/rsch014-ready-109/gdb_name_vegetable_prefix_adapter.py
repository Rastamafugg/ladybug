"""Reuse joint HUD assertions for the separate BUG105/106 prefix."""
from pathlib import Path
base=Path(__file__).with_name('gdb_name_hud_adapter.py')
source=base.read_text()
source=source[:source.rindex("exec(compile(source,")]
exec(compile(source,str(base)+'[105-106-prefix-preparation]','exec'))
source=source.replace('name_tiles(pending_name,1)','name_tiles(pending_name,6)').replace('pending-name red cells','pending-name white cells')
line="   for row in (12,18):check('ordinal row'+str(row)+' owner'+str(owner),[cell(frame,x,row) for x in (1,2,3)]==[raw_tile(v,1) for v in ordinal])"
assert source.count(line)==1
source=source.replace(line,'')
source=source.replace("'pending_name':'red1'","'pending_name':'unchanged white6'").replace("'ordinal_raw_codes':list(ordinal),","'scope':'separate104-105-106 prefix,108/110 excluded',")
source=source.replace('PASS-CURRENT-JOINT-LAST-PART-VEGETABLE-VALUE-RANK-OWNERS','PASS-SEPARATE-105-106-VEGETABLE-VALUE-OWNERS')
exec(compile(source,str(base)+'[105-106-prefix]','exec'))
