"""Bounded cold-boot identity and descriptor-to-audio-guard lifetime probe."""
from pathlib import Path
import hashlib
import json
import sys
import time
import traceback

w, out = map(Path, sys.argv[1:3])
sys.path.insert(0, str(w/'scripts'))
import verify_bug011_runtime as r
import verify_bug009_monitor_input as m
b = Path(sys.argv[3]) if len(sys.argv) > 3 else w/'build'
bs = r.symbols(b/'ladybug-gmc-boot.map')
au = r.symbols(b/'ladybug-audio-runtime.map')
ms = r.symbols(b/'ladybug.map')
ps = r.symbols(b/'ladybug-presentation-runtime.map')
boot = (b/'ladybug-gmc-boot.rom').read_bytes()[:bs['loader_end']-0xC000]
audio = (b/'ladybug-audio-runtime.bin').read_bytes()
layout = json.loads((b/'ladybug-sparse-layout.json').read_text())
rom = (b/'ladybug.rom').read_bytes()
delta = bs['LOADER_RAM'] - bs['loader_start']
digest = lambda data: hashlib.sha256(data).hexdigest()
e = dict(rom_sha256=digest(rom), result='fail', deadline_seconds_per_phase=45,
         success_marker='Exact relocated loader, all five expanded streams, runtime modules, descriptor retirement then exact audio guard',
         timeout_meaning='Required boot/guard boundary absent; not evidence of gameplay slowdown', checks=[])
p, c = r.launch_fast(m, Path('/mnt/e/projects/ladybug/docs/reference/xroar/src/xroar'), b/'ladybug.rom')
deadline = time.monotonic()+45


def read(a, n):
    return r.read_bytes(c, a, n)


def physical(a, n):
    return bytes.fromhex(c.call('read_memory', {'space':'physical','addr':a,'length':n})['data'])


def go(address):
    assert time.monotonic() < deadline, 'phase deadline'
    ids = m.setup(c, [address])
    try:
        c.call('run')
        hit = c.call('wait_for_stop', {'timeout_ms':10000}, timeout=12)
        assert hit.get('pc') == address, hit
    finally:
        m.clear(c, ids)


def loader(label):
    address = bs[label]+delta
    go(address)
    assert read(address, 8) == boot[bs[label]-0xC000:bs[label]-0xC000+8], ('live loader bytes',label)


def record(label, data):
    e['checks'].append(dict(check=label, bytes=len(data), sha256=digest(data)))


try:
    go(bs['boot_entry'])
    initial = read(0xC000, len(boot))
    if initial != boot:
        e['initial_boot_read'] = dict(first_differences=[
            [i, a, b] for i, (a, b) in enumerate(zip(initial, boot)) if a != b][:12],
            live_prefix=initial[:32].hex(), artifact_prefix=boot[:32].hex())
    # BASIC autorun can enter with TY=1. The bootstrap explicitly exposes
    # cartridge ROM before boot_copy; verify the source under that mapping.
    go(bs['boot_copy'])
    assert read(0xC000, len(boot)) == boot, 'authored cartridge bootstrap identity after SAM_CART'
    go(bs['LOADER_RAM'])
    body = boot[bs['loader_start']-0xC000:bs['loader_end']-0xC000]
    assert read(bs['LOADER_RAM'], len(body)) == body, 'relocated loader identity'
    record('authored/relocated loader exact', body)
    loader('copy_enemy_runtime')
    table = boot[bs['gmc_lzss_stream_table']-0xC000:bs['gmc_lzss_stream_end']-0xC000+1]
    assert len(table) == 71
    assert read(bs['GMC_LZSS_TABLE_RAM'], len(table)) == table
    record('five live descriptors copied before source overwrite', table)
    loader('copy_sparse_table')
    audio_stream = layout['compression']['streams'][-1]
    assert audio_stream['name'] == 'audio_page_3d'
    staged = physical(0x24*8192, audio_stream['compressed_bytes'])
    assert digest(staged) == audio_stream['compressed_sha256']
    record('compressed audio staged before all-RAM', staged)
    for stream in layout['compression']['streams']:
        loader('dgs_flags')
        regs = c.call('read_registers')
        gime = c.call('read_gime_state')
        page = gime['pars']['task0'][5] & 63
        e['checks'].append(dict(check='destination mapping '+stream['name'],
                               cpu_register_read=read(0xFFA5,1)[0], actual_page=page,
                               expected_page=stream['destination_page']))
        assert page == stream['destination_page']
        assert regs['y'] == stream['destination_address']
        compressed = read(regs['u'], stream['compressed_bytes'])
        assert digest(compressed) == stream['compressed_sha256'], stream['name']
        loader('dgs_stream_done')
        address = stream['destination_page']*8192+stream['destination_address']-0xA000
        expanded = physical(address, stream['raw_bytes'])
        assert digest(expanded) == stream['raw_sha256'], stream['name']
        record('compressed source/expanded destination: '+stream['name'], expanded)
    loader('boot_streams_retired')
    retired_overlap = read(0x02C0, 20)
    record('descriptor overlap at retirement', retired_overlap)
    go(0xC002)
    for address, name in [(0xC000,'ladybug-runtime.rom'), (0x0800,'ladybug-enemy-runtime.rom'),
                          (0x1900,'ladybug-presentation-runtime.bin')]:
        expected = (b/name).read_bytes()
        if address == 0xC000:
            expected = expected[:0x3E00]  # forced RAM/I/O is not cartridge data
        assert read(address,len(expected)) == expected, name
        record('cold handoff: '+name, expected)
    helper = (b/'ladybug-cadence-runtime.bin').read_bytes()
    assert physical(0x34*8192+0x1C50,len(helper)) == helper
    record('raw helper destination exact before runtime handoff',helper)
    enemy = (b/'ladybug-enemy-sparse.bin').read_bytes()
    assert physical(0x35*8192,len(enemy)) == enemy
    record('all enemy pages/indexes intact at handoff',enemy)
    deadline = time.monotonic()+45
    init = 0x0300+au['audio_guard_copy']-0xA000
    go(init)
    engine = audio[:au['audio_engine_end']-0xA000]
    assert read(0x0300,len(engine)) == engine, 'copied engine identity before guard installation'
    assert c.call('read_gime_state')['pars']['task0'][5] & 63 == 0x3D
    assert read(0x02C0,20) == retired_overlap, 'overlap changed before guard installation'
    guard = audio[au['audio_guard_bytes']-0xA000:au['audio_guard_end']-0xA000]
    go(0x0300+au['audio_init_slot_loop']-0xA000)
    assert read(0x02C0,len(guard)) == guard
    record('guard installed only after boot retirement',guard)
    go(ps['pft_ready'])
    assert read(0x1900,len((b/'ladybug-presentation-runtime.bin').read_bytes())) == (b/'ladybug-presentation-runtime.bin').read_bytes()
    assert read(0x02C0,len(guard)) == guard
    e['presentation_mode'] = read(ms['PRES_MODE'],1)[0]
    e['result'] = 'pass'
except Exception as ex:
    e.update(failure=repr(ex), traceback=traceback.format_exc())
finally:
    c.close()
    m.stop(p)
    out.write_text(json.dumps(e,indent=2)+'\n')
print(json.dumps(e,indent=2))
if e['result'] != 'pass':
    raise SystemExit(1)
