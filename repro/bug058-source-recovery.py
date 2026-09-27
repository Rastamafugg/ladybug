"""Read-only host compression/packing research; no loader or ROM installation."""
from pathlib import Path
import functools
import hashlib
import json
import sys
import types

w, out = map(Path, sys.argv[1:3])
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
aux = bytearray(manifest['aux_runtime']['staged_bytes'])
for seg in base[3]:
    if seg.target == 'presentation_auxiliary':
        aux[seg.target_offset:seg.target_offset + seg.count] = banks[seg.bank][seg.source_offset:seg.source_offset + seg.count]
assert digest(aux) == manifest['aux_runtime']['staged_sha256']
options = [('enemy_page_35', args['enemy_payload'][:8192], 0x35, 0xA000, 'enemy'),
           ('presentation_auxiliary', bytes(aux), 0x23, manifest['aux_runtime']['stage_address'], 'presentation_auxiliary')]
helper = (b / 'cadence-prototype/helper.bin').read_bytes()
source = (w / 'scripts/build_sparse_sprites.py').read_text()
rows = []
for name, raw, page, address, target in options:
    compressed = p.lzss_compress(raw)
    assert p.lzss_decompress(compressed, len(raw)) == raw
    print(name, len(raw), '->', len(compressed), flush=True)
    # Keep audio last. Runtime bootstrap must replace its hard-coded fourth
    # descriptor with a generated offset before this plan is runnable.
    anchor = '    for name, raw, destination_page, destination_address in stream_targets:'
    addition = '''    targets = [t for t in targets if not (t.name == RESEARCH_TARGET and t.page == RESEARCH_PAGE)]
    targets += target_chunks("cadence_page_34", RESEARCH_HELPER, 0x34, 0xBC50)
    stream_targets.insert(len(stream_targets) - 1, (RESEARCH_NAME, RESEARCH_RAW, RESEARCH_PAGE, RESEARCH_ADDRESS))
'''
    assert source.count(anchor) == 1
    modified = source.replace(anchor, addition + anchor, 1)
    module = types.ModuleType('recovery_' + name)
    module.__file__ = str(w / 'scripts/build_sparse_sprites.py')
    sys.modules[module.__name__] = module
    module.__dict__.update(RESEARCH_TARGET=target, RESEARCH_PAGE=page, RESEARCH_HELPER=helper,
                           RESEARCH_NAME=name, RESEARCH_RAW=raw, RESEARCH_ADDRESS=address)
    exec(compile(modified, module.__file__, 'exec'), module.__dict__)
    module.lzss_compress = p.lzss_compress
    packed = module.pack_candidate_banks(**args)
    used = sum(s.count for s in packed[3]) + sum(len(s.compressed) for s in packed[4])
    spare = manifest['gmc']['usable_source_bytes'] - used
    # Reconstruct every planned destination independently from packed source.
    planned_banks = {bank: packed[i] for i, bank in enumerate([0, 2, 3])}
    expanded = {}
    def write(page, address, data):
        for offset, value in enumerate(data):
            key = (page, address + offset)
            assert key not in expanded, ('overlapping destination', key)
            expanded[key] = value
    for s in packed[3]:
        write(s.destination_page, s.destination_address,
              planned_banks[s.bank][s.source_offset:s.source_offset + s.count])
    for s in packed[4]:
        stream = planned_banks[s.bank][s.source_offset:s.source_offset + len(s.compressed)]
        write(s.destination_page, s.destination_address, p.lzss_decompress(stream, len(s.raw)))
    for s in base[3]:
        expected = banks[s.bank][s.source_offset:s.source_offset + s.count]
        assert bytes(expanded[(s.destination_page, s.destination_address + i)] for i in range(s.count)) == expected
    for s in base[4]:
        assert bytes(expanded[(s.destination_page, s.destination_address + i)] for i in range(len(s.raw))) == s.raw
    assert bytes(expanded[(0x34, 0xBC50 + i)] for i in range(len(helper))) == helper
    rows.append(dict(name=name, raw_bytes=len(raw), compressed_bytes=len(compressed),
                     gross_source_saved=len(raw)-len(compressed), raw_sha256=digest(raw),
                     compressed_sha256=digest(compressed), helper_raw_bytes=len(helper),
                     packed_source_used=used, packed_source_spare=spare,
                     raw_descriptors=len(packed[3]), compressed_descriptors=len(packed[4]),
                     descriptor_bytes_in_boot=len(packed[3])*8+len(packed[4])*14+1,
                     host_all_destinations_exact=True, runtime_verified=False))
result = dict(baseline_rom_sha256=digest((b/'ladybug.rom').read_bytes()),
              baseline_pack_exact=True, baseline_source_spare=manifest['gmc']['spare_bytes'],
              source_limit=manifest['gmc']['usable_source_bytes'], options=rows,
              existing_compression_raw_bytes=sum(s['raw_bytes'] for s in manifest['compression']['streams']),
              existing_compression_source_bytes=sum(s['compressed_bytes'] for s in manifest['compression']['streams']),
              scope='Host compression, unchanged-byte destination reconstruction and source packing only. No loader assembly, new ROM, live identity or runtime acceptance.')
out.write_text(json.dumps(result, indent=2)+'\n')
print(json.dumps(result, indent=2), flush=True)
