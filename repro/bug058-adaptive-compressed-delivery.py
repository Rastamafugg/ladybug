"""Pack an isolated boot-only fixture; no production ROM installation.

Run under the project's WSL build environment with arguments:
compression_reference_checkout adaptive_fit_checkout output_receipt.json.
The fixture must halt before game entry because real callbacks are unbound.
"""
from pathlib import Path
import functools
import hashlib
import json
import sys
import types

w, fit, out = map(Path, sys.argv[1:4])
bindings_mode='--bindings' in sys.argv[4:]
b = w / 'build'
sys.path.insert(0, str(w / 'scripts'))
import build_sparse_sprites as p
p.lzss_compress = functools.lru_cache(maxsize=None)(p.lzss_compress)
digest = lambda data: hashlib.sha256(data).hexdigest()
manifest = json.loads((b / 'ladybug-sparse-layout.json').read_text())
names = {
    'enemy_payload': 'ladybug-enemy-sparse.bin', 'player_payload': 'ladybug-player-sparse.bin',
    'gate_payload': 'ladybug-gate-transitions.bin', 'presentation_payload': 'ladybug-presentation-sparse.bin',
    'enemy_runtime': 'ladybug-enemy-runtime.rom', 'presentation_cold': 'ladybug-presentation-cold.bin',
    'presentation_module': 'ladybug-presentation-runtime.bin', 'perimeter_payload': 'ladybug-perimeter-reset.bin',
    'perimeter_helper': 'ladybug-perimeter-reset-helper.bin', 'instruction_runtime': 'ladybug-instruction-runtime.bin',
    'demo_runtime': 'ladybug-demo-runtime.bin', 'actor_records': 'ladybug-attract-actor-records.bin',
    'actor_underlays': 'ladybug-attract-actor-underlays.bin', 'audio_runtime': 'ladybug-audio-runtime.bin',
    'tile_patches': 'ladybug-presentation-tile-patches.bin', 'highscore_runtime': 'ladybug-highscore-runtime.bin',
    'highscore_helper': 'ladybug-highscore-helper.bin',
}
args = {k: (b / v).read_bytes() for k, v in names.items()}
args.update(aux_runtime_role='complete', include_streams=True)
base = p.pack_candidate_banks(**args)
banks = {bank: base[i] for i, bank in enumerate([0, 2, 3])}
for i, name in enumerate(['ladybug-gmc-bank0-overflow.bin', 'ladybug-sparse-bank2.bin', 'ladybug-sparse-bank3.bin']):
    assert base[i] == (b / name).read_bytes()
print('baseline pack identity passed', flush=True)
helper=(fit/'build/adaptive-fit/banked.bin').read_bytes()
mapped=(fit/'build/adaptive-fit/mapped.bin').read_bytes()
bindings=fit/'build/adaptive-fit/bindings'
if bindings_mode:
    tick=(bindings/'tick.bin').read_bytes();resident_binding=(bindings/'resident.bin').read_bytes();installer=(bindings/'installer.bin').read_bytes();audio_api=(bindings/'audio.bin').read_bytes()
    assert len(tick)==134 and len(audio_api)==140 and len(resident_binding)<=145 and len(installer)<=24
    # No raw low-RAM target: $05DE overlaps the live relocated bootstrap.
    # Stage the binding in the existing audio stream for post-loader copy.
    args['audio_runtime']+=audio_api+tick
assert len(helper)<=698 and len(mapped)<=220
patched=bytearray(args['enemy_runtime']);mapped_offset=0x09FD-0x0800
patched[mapped_offset:mapped_offset+220]=mapped+bytes([0x12])*(220-len(mapped))
args['enemy_runtime']=bytes(patched)
source=(w/'scripts/build_sparse_sprites.py').read_text()
anchor='    for name, raw, destination_page, destination_address in stream_targets:'
addition='    targets += target_chunks("adaptive_helper", RESEARCH_HELPER, 0x34, 0xBD44)\n'
assert source.count(anchor)==1
module=types.ModuleType('adaptive_delivery');module.__file__=str(w/'scripts/build_sparse_sprites.py');sys.modules[module.__name__]=module;module.__dict__['RESEARCH_HELPER']=helper
exec(compile(source.replace(anchor,addition+anchor,1),module.__file__,'exec'),module.__dict__)
module.lzss_compress=p.lzss_compress
packed=module.pack_candidate_banks(**args);planned_banks={bank:packed[i] for i,bank in enumerate([0,2,3])}
expanded={}
def write(page,address,data):
 for i,value in enumerate(data):
  key=(page,address+i);assert key not in expanded,('overlap',key);expanded[key]=value
for v in packed[3]:write(v.destination_page,v.destination_address,planned_banks[v.bank][v.source_offset:v.source_offset+v.count])
for v in packed[4]:
 stream=planned_banks[v.bank][v.source_offset:v.source_offset+len(v.compressed)]
 write(v.destination_page,v.destination_address,p.lzss_decompress(stream,len(v.raw)))
for v in base[3]:
 expected=banks[v.bank][v.source_offset:v.source_offset+v.count]
 assert bytes(expanded[(v.destination_page,v.destination_address+i)] for i in range(v.count))==expected
for v in base[4]:assert bytes(expanded[(v.destination_page,v.destination_address+i)] for i in range(len(v.raw)))==v.raw
assert bytes(expanded[(0x34,0xBD44+i)] for i in range(len(helper)))==helper
assert planned_banks[3][0x800:0x800+len(patched)]==patched
output=fit/'build/adaptive-fit'/('bindings-delivery' if bindings_mode else 'delivery');output.mkdir(parents=True,exist_ok=True)
module.write_loader_include(output/'ladybug-sparse-loader.inc',packed[3],packed[4])
(output/'ladybug-perimeter-boot.inc').write_bytes((b/'ladybug-perimeter-boot.inc').read_bytes())
import subprocess,re
subprocess.run(['lwasm','-9','--format=raw','-DHIGHSCORE_TEST_PROFILE=0','--output='+str(output/'boot.bin'),'--map='+str(output/'boot.map'),'--list='+str(output/'boot.lst'),'-I',str(output),'-I',str(b),'-I',str(w/'src'),str(w/'src/gmc_bootstrap.s')],check=True)
syms={k:int(v,16) for k,v in re.findall(r'^Symbol: (\w+) .* = ([0-9A-Fa-f]+)$',(output/'boot.map').read_text(),re.M)}
used=sum(v.count for v in packed[3])+sum(len(v.compressed) for v in packed[4]);spare=manifest['gmc']['usable_source_bytes']-used
assert spare>=0 and len(packed[3])*8<=120 and syms['loader_end']<=0xC800 and syms['GMC_LZSS_STREAM_TABLE_BYTES']==99
boot=bytearray((output/'boot.bin').read_bytes());boot.extend(bytes([255])*(16384-len(boot)))
for v in packed[3]:
 if v.bank==0:
  start=v.source_offset;end=start+v.count;assert start>=0x800 and end<=0x3e00 and all(x==255 for x in boot[start:end]);boot[start:end]=planned_banks[0][start:end]
assert not any(v.bank==0 for v in packed[4]),'fixture merger needs explicit compressed-bank0 ownership'
resident_image=bytearray((b/'ladybug-runtime.rom').read_bytes())
if bindings_mode:
    resident_image[0xFF:0xFF+145]=resident_binding+bytes([0x12])*(145-len(resident_binding))
    resident_image[0x1FE8:0x1FE8+len(installer)]=installer
fixture=bytes(boot)+bytes(resident_image)+planned_banks[2]+planned_banks[3];assert len(fixture)==65536
(output/'boot-only-fixture.rom').write_bytes(fixture);(output/'mapped-enemy.bin').write_bytes(patched)
result={'phase':'host packing and loader assembly with unbound game callbacks','reference_rom_sha256':digest((b/'ladybug.rom').read_bytes()),'banked_helper_bytes':len(helper),'mapped_replacement_bytes':len(mapped),'state_bytes':320,'source_spare':spare,'source_limit':manifest['gmc']['usable_source_bytes'],'copy_table_bytes':len(packed[3])*8,'compressed_descriptors':len(packed[4]),'descriptor_bytes':99,'bootstrap_bytes':syms['loader_end']-0xC000,'audio_offset':syms['GMC_LZSS_AUDIO_OFFSET'],'helper_sha256':digest(helper),'mapped_sha256':digest(mapped),'bootstrap_sha256':digest((output/'boot.bin').read_bytes()),'boot_only_fixture_sha256':digest(fixture),'helper_segments':[{'bank':v.bank,'source_offset':v.source_offset,'destination_page':v.destination_page,'destination_address':v.destination_address,'count':v.count} for v in packed[3] if v.target=='adaptive_helper'],'all_baseline_destinations_exact':True,'mapped_enemy_source_exact':True,'status':'pass','limits':'Host-only exact delivery of bookkeeping payload; real game/input/render/audio bridges, live installation and complete-worklist timing remain unverified. No adaptive ROM launched.'}
out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if bindings_mode:
    (output/'resident-fixture.bin').write_bytes(resident_image)
    result['phase']='host packing with real-call binding components; driver and multi-refresh audio absent'
    result['binding_delivery']={'copied_bytes':len(tick),'copied_address':0x5DE,'staged_address':0xB6B7,'audio_api_bytes':len(audio_api),'audio_runtime_bytes':len(args['audio_runtime']),'resident_region_bytes':len(resident_binding),'resident_tail_bytes':len(installer),'resident_free':24-len(installer),'low_ram_boot_copy':False,'post_loader_installer_required':True}
    result['limits']='Bindings staged in existing audio page. Main driver and complete publication/audio semantics remain unbound. Fixture must stop before game entry.'
    out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result['binding_delivery'],indent=2))
