"""Reuse joint fields for the separate BUG108 prefix, excluding BUG110."""
from pathlib import Path
base=Path(__file__).with_name('gdb_name_hud_adapter.py')
outer=base.read_text();outer=outer[:outer.rindex("exec(compile(source,")]
exec(compile(outer,str(base)+'[108-prefix-preparation]','exec'))
source=source.replace('name_tiles(pending_name,1)','name_tiles(pending_name,6)').replace('pending-name red cells','pending-name white cells')
assert source.count('for row in (12,18):check(')==1
source=source.replace('for row in (12,18):check(','for row in (12,):check(')
source=source.replace("'pending_name':'red1'","'pending_name':'unchanged white6'").replace("'ordinal_raw_codes':list(ordinal),","'ordinal_raw_codes':list(ordinal),'ordinal_rows':[12],'scope':'separate108 prefix,110 excluded',")
source=source.replace('PASS-CURRENT-JOINT-LAST-PART-VEGETABLE-VALUE-RANK-OWNERS','PASS-SEPARATE-108-PLACEMENT-OWNER-FIELDS')
exec(compile(source,str(base)+'[108-prefix]','exec'))
