"""Assembly/packing gate only. Never installs or launches the experimental ROM.

Run under WSL with the isolated candidate path and a receipt output path.
Uses current built artifacts; validates baseline pack identity before extending
the existing packer with one optional page-$34 stream (or raw copy alternative).
"""
from pathlib import Path
import hashlib
import difflib
import functools
import json
import re
import subprocess
import sys
import types

w = Path(sys.argv[1]).resolve()
out = Path(sys.argv[2]).resolve()
root = Path(__file__).resolve().parent
build = w / 'build'
scratch = build / 'cadence-prototype'
scratch.mkdir(exist_ok=True)
helper_source = root / 'bug058-cadence-prototype.s'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def symbols(path):
    return {a: int(b, 16) for a, b in re.findall(
        r'^Symbol: (\S+) .* = ([0-9A-Fa-f]+)$', path.read_text(), re.M)}


def asm(source, name, main=False):
    defines = ['-DBUG011_DEVELOPMENT_PROFILE=1', '-DCOMPLETE_PROFILE=1',
               '-DHIGHSCORE_TEST_PROFILE=0', '-DHIGHSCORE_PHASE_HELPER=0',
               '-DPRESENTATION_NAME_ENTRY_DATA=0', '-DINPUT_JOYSTICK=0'] if main else []
    subprocess.run(['lwasm', '-9', '--format=raw'] + defines + [
        '--output=' + str(scratch / (name + '.bin')),
        '--map=' + str(scratch / (name + '.map')),
        '-I', str(scratch), '-I', str(build), '-I', str(w / 'src'), str(source)],
        cwd=w, check=True)
    return symbols(scratch / (name + '.map'))


def imports(ms, es):
    merged = dict(ms, **es)
    # The new entry aliases are defined by the helper itself, not imports.
    merged = {k: v for k, v in merged.items() if not k.startswith('cadence_')}
    (scratch / 'cadence-imports.inc').write_text(''.join(
        f'{k} equ ${v:04X}\n' for k, v in sorted(merged.items())))


def replace_once(source, old, new):
    assert source.count(old) == 1, old
    return source.replace(old, new, 1)


ms = symbols(build / 'ladybug.map')
es = symbols(build / 'ladybug-enemy-runtime.map')
imports(ms, es)
hs = asm(helper_source, 'helper')

main = (w / 'src/main.s').read_text()
main = replace_once(main, '\nasset_end\n', '''
cadence_slot_selected
        ldb     ENEMY_WORK
        ldy     #$BC30
        lda     b,y
        rts
asset_end
''')
(scratch / 'main.s').write_text(main)
ms = asm(scratch / 'main.s', 'main', True)

enemy = (w / 'src/enemy_runtime.s').read_text()
a = enemy.index('\nframebuffer_capture_back\n')
z = enemy.index('\n; Vbord is the only', a)
enemy = enemy[:a] + '\nframebuffer_capture_back\n        jmp cadence_publish\n' + enemy[z:]
enemy = replace_once(enemy, '''        bcs    fri_abort
        tst     FB_INIT_STATE''', '''        bcs    fri_abort
        clr     ENEMY_CAPTURE_DIRTY
        jsr     cadence_plan
        tst     FB_INIT_STATE''')
enemy = replace_once(enemy, '''        clr     ENEMY_CAPTURE_DIRTY
        lbsr    colour_prepare_nest''', '''        lbsr    colour_prepare_nest''')
enemy = replace_once(enemy, '''        lbsr    framebuffer_capture_a
        ldx     #FB_META_A''', '''        jsr     cadence_reset
        lbsr    framebuffer_capture_a
        ldx     #FB_META_A''')
for loop, nxt in [('acr_enemy_loop', 'acr_enemy_next'), ('acd_save_loop', 'acd_save_next'),
                  ('acd_draw_loop', 'acd_draw_next')]:
    enemy = replace_once(enemy, '\n' + loop + '\n', '\n' + loop + '\n        jsr cadence_slot_selected\n        beq ' + nxt + '\n')
enemy = replace_once(enemy, '        sta     6,x\nacd_save_next', '''        sta     6,x
        ldb     #4
        subb    ENEMY_WORK
        lslb
        lslb
        lslb
        ldy     #ENEMY_TABLE
        leay    b,y
        sta     6,y
acd_save_next''')
a = enemy.index('\nactor_closure_restore\n')
z = enemy.index('\nframebuffer_init_impl\n', a)
part = enemy[a:z].replace('ldx     #ENEMY_TABLE', 'ldx     #$BC04')
part = replace_once(part, '''        ldb     7,x
        pshs    x
        ldx     1,x
        lbsr    draw_enemy_fb''', '''        ldb     ENEMY_WORK
        decb
        ldy     #$BC24
        lda     b,y
        pshs    x
        ldx     1,x
        lbsr    draw_enemy_cached_frame''')
enemy = enemy[:a] + part + enemy[z:]
enemy = replace_once(enemy, 'draw_enemy_fb\n        lbsr    enemy_frame_number\n',
                     'draw_enemy_fb\n        lbsr    enemy_frame_number\ndraw_enemy_cached_frame\n')

# Regenerate imports from final maps and link until all imported addresses and
# helper bytes stabilize. No production generated symbols are overwritten.
previous = None
for iteration in range(4):
    entries = ''.join(f'{k} equ ${hs[k]:04X}\n' for k in
                      ['cadence_publish', 'cadence_plan', 'cadence_reset'])
    entries += f'cadence_slot_selected equ ${ms["cadence_slot_selected"]:04X}\n'
    (scratch / 'enemy.s').write_text(entries + enemy)
    es = asm(scratch / 'enemy.s', 'enemy')
    imports(ms, es)
    hs = asm(helper_source, 'helper')
    data = (scratch / 'helper.bin').read_bytes()
    identity = (data, (scratch / 'enemy.bin').read_bytes())
    if identity == previous:
        break
    previous = identity
else:
    raise AssertionError('generated helper/import link did not converge')

sys.path.insert(0, str(w / 'scripts'))
import build_sparse_sprites as original
original.lzss_compress = functools.lru_cache(maxsize=None)(original.lzss_compress)

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
args = {k: (build / v).read_bytes() for k, v in names.items()}
args.update(aux_runtime_role='complete', include_streams=True)
baseline = original.pack_candidate_banks(**args)
for i, name in enumerate(['ladybug-gmc-bank0-overflow.bin', 'ladybug-sparse-bank2.bin', 'ladybug-sparse-bank3.bin']):
    assert baseline[i] == (build / name).read_bytes(), 'baseline pack identity: ' + name

compressed = original.lzss_compress(data)
assert original.lzss_decompress(compressed, len(data)) == data
args['enemy_runtime'] = (scratch / 'enemy.bin').read_bytes()
packer_source = (w / 'scripts/build_sparse_sprites.py').read_text()
results = {}
for mode in ('compressed', 'raw'):
    changed = replace_once(packer_source, '        include_streams: bool = False,',
                           '        cadence_runtime: bytes = b"",\n        include_streams: bool = False,')
    if mode == 'compressed':
        changed = replace_once(changed, '    for name, raw, destination_page, destination_address in stream_targets:',
                               '    stream_targets.append(("cadence_page_34", cadence_runtime, 0x34, 0xBC50))\n'
                               '    for name, raw, destination_page, destination_address in stream_targets:')
    else:
        changed = replace_once(changed, '    for target in targets:',
                               '    targets += target_chunks("cadence_page_34", cadence_runtime, 0x34, 0xBC50)\n'
                               '    for target in targets:')
    # Preserve the exact packer extension for review, without installing it.
    (scratch / ('packer-' + mode + '.py')).write_text(changed)
    (scratch / ('packer-' + mode + '.patch')).write_text(''.join(difflib.unified_diff(
        packer_source.splitlines(True), changed.splitlines(True),
        fromfile='a/scripts/build_sparse_sprites.py', tofile='b/scripts/build_sparse_sprites.py')))
    module = types.ModuleType('cadence_packer_' + mode)
    module.__file__ = str(w / 'scripts/build_sparse_sprites.py')
    sys.modules[module.__name__] = module
    exec(compile(changed, module.__file__, 'exec'), module.__dict__)
    module.lzss_compress = original.lzss_compress
    try:
        packed = module.pack_candidate_banks(**args, cadence_runtime=data)
        results[mode] = {'fits': True, 'segments': len(packed[3]), 'streams': len(packed[4])}
    except ValueError as error:
        results[mode] = {'fits': False, 'error': str(error)}

layout = json.loads((build / 'ladybug-sparse-layout.json').read_text())
free = layout['gmc']['spare_bytes']
assert layout['gmc']['final_image_sha256'] == sha((build / 'ladybug.rom').read_bytes())
native = (scratch / 'enemy.bin').read_bytes()[es['copy_native_row'] - 0x0800:][:17]
# Four LDD ,X++ / STD ,U++ pairs and RTS occupy 17 bytes; guard the measured
# fixed-table padding against either code-body changes or accidental overlap.
assert native == bytes.fromhex('ec81edc1ec81edc1ec81edc1ec81edc139')
assert es['copy_native_row'] + len(native) <= 0x17A0
result = {
    'status': 'Assembly/packing gate only. No experimental ROM installed or run.',
    'baseline_rom_sha256': sha((build / 'ladybug.rom').read_bytes()),
    'source_sha256': sha(helper_source.read_bytes()),
    'helper_sha256': sha(data), 'helper_bytes': len(data), 'helper_limit': 942,
    'helper_start': hs['cadence_publish'], 'helper_end': hs['cadence_end'],
    'compressed_bytes': len(compressed), 'compressed_sha256': sha(compressed),
    'compression_round_trip': True, 'baseline_three_bank_pack_identity': True,
    'cartridge_source_free': free, 'source_gap_compressed': len(compressed) - free,
    'source_gap_raw': len(data) - free,
    'state_bytes': 76, 'resident_bytes': ms['resident_end'] - 0xC000, 'resident_limit': 8192,
    'assets_bytes': ms['asset_end'] - 0xE000, 'assets_limit': 7680,
    'enemy_bytes': len((scratch / 'enemy.bin').read_bytes()), 'enemy_limit': 4096,
    'enemy_end': es['enemy_runtime_end'], 'enemy_fixed_tables': 0x17A0,
    'enemy_pre_table_free': 0x17A0 - es['copy_native_row'] - len(native),
    'helper_ram_free': 942 - len(data),
    'cartridge_source_limit': layout['gmc']['usable_source_bytes'],
    'cartridge_source_baseline_used': layout['gmc']['source_bytes_including_proof'],
    'linked_enemy_sha256': sha((scratch / 'enemy.bin').read_bytes()),
    'linked_resident_sha256': sha((scratch / 'main.bin').read_bytes()),
    'link_convergence_passes': iteration + 1,
    'packing': results,
    'runtime_verification': 'NOT RUN: cartridge capacity is a prerequisite. No timing or pixel pass claimed.',
    'unchanged_payload_hashes': {k: sha((build / v).read_bytes()) for k, v in names.items()},
}
out.write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({k: v for k, v in result.items() if k != 'unchanged_payload_hashes'}, indent=2))
