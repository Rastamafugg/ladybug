"""Compare fitted transport build with full-cadence baseline artifacts."""
from pathlib import Path
import sys,json,hashlib,re
fit,base,out=map(Path,sys.argv[1:4]);f=fit/'build';b=base/'build'
sha=lambda x:hashlib.sha256(x).hexdigest()
e={'baseline_revision':'cba520588abf4a8ab32314ec61a16d58b40b7186','baseline_rom_sha256':sha((b/'ladybug.rom').read_bytes()),'rom_sha256':sha((f/'ladybug.rom').read_bytes()),'identity':[]}
for name in ['ladybug-runtime.rom','ladybug-enemy-runtime.rom','ladybug-presentation-runtime.bin','ladybug-audio-runtime.bin','ladybug-enemy-sparse.bin','ladybug-player-sparse.bin','ladybug-gate-transitions.bin','ladybug-presentation-sparse.bin','ladybug-presentation-cold.bin','ladybug-perimeter-reset.bin','ladybug-perimeter-reset-helper.bin','ladybug-instruction-runtime.bin','ladybug-demo-runtime.bin','ladybug-highscore-runtime.bin','ladybug-highscore-helper.bin','ladybug-attract-actor-records.bin','ladybug-attract-actor-underlays.bin','ladybug-presentation-tile-patches.bin']:
 a=(f/name).read_bytes();z=(b/name).read_bytes();assert a==z,name
 e['identity'].append({'artifact':name,'bytes':len(a),'sha256':sha(a),'exact':True})
m=json.loads((f/'ladybug-sparse-layout.json').read_text());old=json.loads((b/'ladybug-sparse-layout.json').read_text());streams=m['compression']['streams']
assert len(streams)==7 and streams[-1]['name']=='audio_page_3d'
e['source_free_bytes']=m['gmc']['spare_bytes'];e['net_recovered_bytes']=e['source_free_bytes']-old['gmc']['spare_bytes'];assert e['net_recovered_bytes']>=16000
text=(f/'ladybug-gmc-boot.map').read_text();symbols={k:int(v,16) for k,v in re.findall(r'^Symbol: (\w+) .* = ([0-9A-Fa-f]+)$',text,re.M)}
e['bootstrap_bytes']=symbols['loader_end']-0xc000;assert e['bootstrap_bytes']<=2048
assert symbols['GMC_LZSS_STREAM_TABLE_BYTES']==99 and symbols['GMC_LZSS_AUDIO_OFFSET']==84
assert symbols['SPARSE_COPY_TABLE_BYTES']<=120
assert symbols['GMC_LZSS_TABLE_RAM']+99==0x2ea
sys.path.insert(0,str(fit/'scripts'))
from build_sparse_sprites import write_loader_include
from types import SimpleNamespace
e['negative_descriptor_checks']=[]
for name,names,expected in [('missing audio',['x'],'unique final'),('audio not last',['audio_page_3d','x'],'unique final'),('eighth descriptor',[str(i) for i in range(7)]+['audio_page_3d'],'exceed phase-owned')]:
 try:write_loader_include(f/'unexpected-loader.inc',[],[SimpleNamespace(name=x) for x in names])
 except ValueError as error:assert expected in str(error);e['negative_descriptor_checks'].append({'case':name,'rejected':True})
 else:raise AssertionError(name)
e['descriptor_bytes']=99;e['copy_table_bytes']=symbols['SPARSE_COPY_TABLE_BYTES'];e['status']='pass';out.write_text(json.dumps(e,indent=2)+'\n');print(json.dumps({k:v for k,v in e.items() if k!='identity'},indent=2))
