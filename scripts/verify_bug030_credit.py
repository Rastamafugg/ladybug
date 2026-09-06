"""BUG-030 acceptance using natural input, current symbols, and pixel oracles."""
import argparse
from functools import lru_cache
import json
from pathlib import Path
import time

import verify_bug011_runtime as p
import verify_feat003_highscore_test as v

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--scenario', choices=['loading', 'settled', 'instructions', 'demo', 'clean'], required=True)
    args = ap.parse_args()
    sy = p.symbols(ROOT / 'build/ladybug-presentation-runtime.map')
    ms = p.symbols(ROOT / 'build/ladybug.map')
    manifest = json.loads((ROOT / 'build/ladybug-presentation.json').read_text())
    assert manifest['complete_profile']
    high = (ROOT / 'build/ladybug-highscore-runtime.bin').read_bytes()
    instr = (ROOT / 'build/ladybug-instruction-runtime.bin').read_bytes()
    enemy = (ROOT / 'build/ladybug-enemy-runtime.rom').read_bytes()
    pres = (ROOT / 'build/ladybug-presentation-runtime.bin').read_bytes()
    rom = ROOT / 'build/ladybug.rom'
    out = ROOT / f'build/bug030-{args.scenario}.json'
    evidence = {'scenario': args.scenario, 'rom_sha256': p.digest(rom.read_bytes()),
                'deadline_seconds': 30, 'phases': [], 'code_writes': 0, 'state_writes': 0}
    monitor = p.load_monitor()
    binary = ROOT / 'docs/reference/xroar/src/xroar'
    proc, c = (monitor.launch(binary, rom, monitor.free_port()) if args.scenario == 'clean'
               else p.launch_fast(monitor, binary, rom))

    def phys(addr, size):
        return bytes.fromhex(c.call('read_memory', {'space': 'physical', 'addr': addr, 'length': size})['data'])

    def check_code():
        assert p.read_bytes(c, 0x800, len(enemy)) == enemy, 'enemy code corrupted'
        assert p.read_bytes(c, 0x1900, len(pres)) == pres, 'presentation code corrupted'

    def go(label, targets):
        targets = [sy[x] if isinstance(x, str) else x for x in targets]
        print(f'{label}: markers={targets}, deadline=30s', flush=True)
        ids = monitor.setup(c, targets)
        try:
            hit = c.run_to_breakpoint(30)
            assert hit['pc'] in targets, hit
            evidence['phases'].append({'label': label, 'pc': hit['pc'], 'mode': p.read_byte(c, 0xa5),
                                      'screen': p.read_byte(c, 0xa6), 'credits': p.read_byte(c, 0xa8)})
            return hit['pc']
        finally:
            monitor.clear(c, ids)

    def key(k, down):
        c.call('inject_key', {'key': k, 'action': 'press' if down else 'release'})

    def high_pixels(both=False):
        original = v.expected_tile
        patches = (ROOT / 'build/ladybug-presentation-tile-patches.bin').read_bytes()
        cold = (ROOT / 'build/ladybug-presentation-cold.bin').read_bytes()
        slots = manifest['phase_tile_overlay']['slot_ids']

        @lru_cache(None)
        def tile(tile_id):
            if tile_id in slots:
                off = 64 + slots.index(tile_id) * 32
                return patches[off:off+32]
            if tile_id < manifest['gameplay_tile_base']:
                # Complete stores an unpacked atlas; the reused oracle is for highscore-test.
                off = manifest['tile_atlas_offset'] + tile_id * 32
                return cold[off:off+32]
            return original(manifest, tile_id)

        v.expected_tile = lambda m, t: tile(t)
        try:
            expected = bytearray(v.expected_map_frame(manifest, 3))
            table = phys(0x34 * 8192 + 0xf84, 90)
            glyphs = v.constants(v.INCLUDE)
            def draw(dst, tile_id):
                data = tile(tile_id)
                for row in range(8):
                    off = dst - 0x2000 + row * 160
                    expected[off:off+4] = data[row*4:row*4+4]
            for i in range(9):
                record = table[i*10:(i+1)*10]
                for j, digit in enumerate(v.bcd_digits(record[:3])):
                    draw(manifest['high_score_table']['score_destinations'][i]+j*4, glyphs[f'PRESENTATION_GLYPH_{digit}'])
                for j, ch in enumerate(record[3:]):
                    draw(manifest['high_score_table']['name_destinations'][i]+j*4, ch or manifest['black_tile'])
            owners = [0, 1] if both else [p.read_byte(c, 0x8f)]
            captures = []
            for owner in owners:
                actual = phys((0x30 if owner == 0 else 0x2c)*8192, 30720)
                diff = sum(a != b for a, b in zip(actual, expected))
                v.write_frame_png(ROOT / f'build/bug030-{args.scenario}-owner{owner}.png', actual)
                captures.append({'owner': owner, 'sha256': p.digest(actual), 'pixel_byte_differences': diff})
                assert diff == 0, captures[-1]
            evidence.setdefault('pixels', []).extend(captures)
        finally:
            v.expected_tile = original

    def credit(k, count, both=False, release=True):
        key(k, True)
        go('natural credit edge', ['pft_ready'])
        assert p.read_byte(c, 0xa9) & 6
        if release:
            key(k, False)
        call = sy['load_done_dynamic_ready'] - 3
        calls = 0
        for _ in range(3):
            pc = go('credit render/publication', [call, 'credit_tick'])
            check_code()
            assert p.read_byte(c, 0xA8) == count
            if pc == sy['credit_tick']:
                break
            calls += 1
            assert p.read_bytes(c, call, 3) == bytes.fromhex('bd0300')
            assert p.read_bytes(c, 0x300, len(high)) == high, 'wrong installed owner'
        else:
            raise AssertionError('credit screen not reached')
        assert calls == (2 if both else 1), calls
        evidence.setdefault('render_calls', []).append(calls)
        high_pixels(both)

    def wait_state(label, predicate):
        print(label + ': natural run, deadline=30s', flush=True)
        deadline = time.monotonic()+30
        while time.monotonic() < deadline:
            # CPU-space monitor reads call the emulated bus; never poll it while running.
            state = phys(0x38*8192 + 0x8f, 28)
            if predicate(state):
                evidence['phases'].append({'label': label, 'state': state.hex()})
                return
            time.sleep(.005)
        evidence['last_polled_state'] = state.hex()
        raise AssertionError(label + ': state not observed before deadline')

    try:
        if args.scenario == 'clean':
            c.call('run')
            wait_state('unbroken cold attract', lambda s: s[0xa5-0x8f] == 2)
            key(5, True)
            wait_state('unbroken credit', lambda s: s[0xa5-0x8f] == 5 and s[2] == 0)
            key(5, False)
            c.call('pause')
            check_code()
            high_pixels()
            c.call('run')
            key(1, True)
            wait_state('unbroken start accepted', lambda s: s[0xa5-0x8f] == 6 and s[0xa8-0x8f] == 0)
            key(1, False)
            wait_state('unbroken active gameplay', lambda s: s[0xa5-0x8f] == 0)
            frame_start = int.from_bytes(phys(0x38*8192+2, 2), 'big')
            wait_state('unbroken gameplay publication', lambda s: s[0xa5-0x8f] == 0 and ((int.from_bytes(phys(0x38*8192+2, 2), 'big')-frame_start)&65535) >= 3)
            c.call('pause')
            check_code()
            front = p.read_byte(c, 0x8f)
            v.write_frame_png(ROOT / 'build/bug030-clean-gameplay.png', phys((0x30 if front == 0 else 0x2c)*8192, 30720))
        else:
            go('cold entry identity', ['presentation_flow_tick'])
            check_code()
            assert phys(0x23*8192 + sy['PRESENTATION_HIGHSCORE_RUNTIME_ADDRESS']-0xa000, len(high)) == high
            target = {'loading': 'start_screen_done', 'settled': 'attract_tick_ready',
                      'instructions': 'instructions_tick_ready', 'demo': 'demo_tick'}[args.scenario]
            go('natural initial phase', [target])
            if args.scenario != 'demo':
                assert p.read_bytes(c, 0x300, len(instr)) == instr
            credit(6 if args.scenario == 'instructions' else 5, 1,
                   both=args.scenario=='loading', release=args.scenario!='settled')
            if args.scenario == 'settled':
                go('held key unchanged', ['pft_ready'])
                assert p.read_byte(c, 0xa9) & 6 == 0 and p.read_byte(c, 0xa8) == 1
                key(5, False)
                go('key released', ['pft_ready'])
                for n in range(2, 11):
                    credit(5, min(n, 9))
                go('natural return to attract', ['attract_tick_ready'])
                go('natural restored instructions', ['instructions_tick_ready'])
                assert p.read_bytes(c, 0x300, len(instr)) == instr
                check_code()
            if args.scenario == 'demo':
                key(1, True)
                go('natural start edge', ['pft_ready'])
                assert p.read_byte(c, 0xa9) & 1
                key(1, False)
                go('natural gameplay first frame', [ms['main_render']])
                assert p.read_byte(c, 0xa5) == 0 and p.read_byte(c, 0xa8) == 0
                engine = (ROOT / 'build/ladybug-audio-runtime.bin').read_bytes()
                assert p.read_bytes(c, 0x300, 32) == engine[:32]
                go('completed first gameplay render', [ms['main_demo_input_owned']])
                go('next gameplay interval', [ms['main_render']])
                front = p.read_byte(c, 0x8f)
                v.write_frame_png(ROOT / 'build/bug030-demo-gameplay.png', phys((0x30 if front == 0 else 0x2c)*8192, 30720))
                check_code()
        evidence['passed'] = True
    except Exception as exc:
        evidence['error'] = repr(exc)
        if args.scenario == 'clean':
            c.call('pause')
            evidence['failure_registers'] = c.call('read_registers')
        print('FAIL: ' + repr(exc), flush=True)
    finally:
        out.write_text(json.dumps(evidence, indent=2)+'\n')
        c.close()
        p.stop(proc)
    if not evidence.get('passed'):
        raise SystemExit(1)
    print('PASS ' + args.scenario, flush=True)


if __name__ == '__main__':
    main()
