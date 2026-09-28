from pathlib import Path
from html.parser import HTMLParser
import re,json
root=Path('E:/projects/ladybug')
pages=['wiki/internal/tickets/bug-058-three-enemy-slowdown.html','wiki/internal/implementation/data-layouts.html','wiki/internal/sources/index.html','wiki/internal/log.html','wiki/internal/tickets/index.html']
ids=['rebind-player-approved-20260927','rebind-player-results-20260927','cache-rebind-lifetime-20260927','bug058-rebind-player-sources-20260927','bug058-rebind-player-log-20260927','bug058-rebind-player-measured-20260927']
class Reader(HTMLParser):
 def __init__(self):super().__init__();self.ids=[]
 def handle_starttag(self,tag,attrs):
  for k,v in attrs:
   if k=='id':self.ids.append(v)
found=[]
for page in pages:
 path=root/page;text=path.read_text(encoding='utf-8');reader=Reader();reader.feed(text)
 for name in ids:
  if name in reader.ids:
   assert reader.ids.count(name)==1,(page,name);found.append(name)
   section=re.search(r'<section id="'+name+r'">.*?</section>',text,re.S).group()
   for href in re.findall(r'href="([^"]+)"',section):
    if '://' in href:continue
    target,_,anchor=href.partition('#');p=(path.parent/target).resolve() if target else path
    assert p.exists(),(page,href)
    if anchor:
     other=Reader();other.feed(p.read_text(encoding='utf-8'));assert anchor in other.ids,(page,href)
assert sorted(found)==sorted(ids),found
d=json.loads((root/'repro/bug058-rebind-player-summary-20260927.json').read_text())
assert len(d['render_crossover']['cases'])==40 and sum(x['comparisons'] for x in d['render_crossover']['rebind_groups'])==20
assert d['ownership_audit']['errors']==[]
assert d['profile']['baseline_comparison_gate']['result']=='fail'
assert d['profile']['four_enemy_phases']['post_music']['over_target']==16
assert d['capacity']['resident_used']==8168 and d['capacity']['cartridge_source_free']==413
print('PASS: six unique new sections, local links/anchors, retained evidence, capacities and unwaived failed gates')
