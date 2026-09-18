"""Reproduce BUG-029 wrong-owner corruption; --control replaces only the owner.

Use --loading for the failing natural key-5 edge during initial attract loading.
This diagnostic does not implement or verify a production fix.
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import verify_bug011_runtime as p

sy = p.symbols(ROOT / 'build/ladybug-presentation-runtime.map')
monitor = p.load_monitor()
control = '--control' in sys.argv
loading = '--loading' in sys.argv
out = ROOT / ('build/bug029-' + ('loading-' if loading else '') + ('control.json' if control else 'baseline.json'))
e = {'control': control, 'rom_sha256': p.digest((ROOT / 'build/ladybug.rom').read_bytes()),
     'phase_deadline_seconds': 30, 'phases': [], 'timeout_meaning': 'required marker not observed'}
proc, c = p.launch_fast(monitor, ROOT / 'docs/reference/xroar/src/xroar', ROOT / 'build/ladybug.rom')

def go(phase, addresses):
    print('phase=' + phase + ' markers=' + repr(addresses) + ' deadline=30s', flush=True)
    ids = monitor.setup(c, addresses)
    started = time.monotonic()
    try:
        hit = c.run_to_breakpoint(30)
        assert hit['pc'] in addresses, hit
        rec = {'phase': phase, 'hit': hit, 'seconds': time.monotonic() - started,
               'registers': c.call('read_registers'), 'dp': p.read_bytes(c, 0x8f, 80).hex()}
        e['phases'].append(rec)
        print(json.dumps(rec), flush=True)
        return hit['pc']
    finally:
        monitor.clear(c, ids)

def identity(name, addr, data):
    live = p.read_bytes(c, addr, len(data))
    result = {'name': name, 'address': addr, 'bytes': len(data), 'sha256': p.digest(live), 'matches': live == data}
    e.setdefault('identities', []).append(result)
    assert live == data, result

def step():
    c.call('step_instruction', {'n': 1})
    stop = c.call('wait_for_stop', {'timeout_ms': 2000}, timeout=3)
    assert stop['reason'] != 'timeout', stop
    return stop

try:
    go('cold presentation', [sy['presentation_flow_tick']])
    identity('presentation', 0x1900, (ROOT / 'build/ladybug-presentation-runtime.bin').read_bytes())
    enemy = (ROOT / 'build/ladybug-enemy-runtime.rom').read_bytes()
    identity('resident RAM enemy module', 0x800, enemy)
    payloads = {}
    saved = p.read_byte(c, 0xffa5)
    p.write_byte(c, 0xffa5, 0x23)
    for name in ('instruction', 'highscore'):
        data = (ROOT / f'build/ladybug-{name}-runtime.bin').read_bytes()
        payloads[name] = data
        identity('staged ' + name, sy[f'PRESENTATION_{name.upper()}_RUNTIME_ADDRESS'], data)
    p.write_byte(c, 0xffa5, saved)
    go('attract load initialized' if loading else 'settled attract', [sy['start_screen_done'] if loading else sy['attract_tick_ready']])
    identity('installed instruction', 0x300, payloads['instruction'])
    e['visible_owner'] = p.read_byte(c, 0x8f)
    e['visible_sha256'] = p.digest(p.read_owner(c, e['visible_owner']))
    c.call('inject_key', {'key': 5, 'action': 'press'})
    go('physical credit edge', [sy['pft_ready']])
    assert p.read_byte(c, 0xa9) & 6
    c.call('inject_key', {'key': 5, 'action': 'release'})
    call = sy['load_done_dynamic_ready'] - 3
    go('highscore dynamic call', [call])
    identity('call instruction', call, bytes.fromhex('bd0300'))
    identity('RAM code immediately before wrong-owner call', 0x800, enemy)
    assert p.read_byte(c, 0xa6) == 3 and p.read_byte(c, 0xa8) == 1
    identity('wrong installed instruction owner at highscore call', 0x300, payloads['instruction'])
    e['mapping'] = p.read_bytes(c, 0xffa0, 8).hex()
    if control:
        c.call('write_memory', {'addr': 0x300, 'data': payloads['highscore'].hex()})
        identity('control installed highscore owner', 0x300, payloads['highscore'])
    stop = step()
    e['call_step'] = {'stop': stop, 'registers': c.call('read_registers')}
    print(json.dumps(e['call_step']), flush=True)
    assert stop['pc'] == 0x300, stop
    started = time.monotonic()
    e['trace'] = []
    for n in range(30000):
        regs = c.call('read_registers')
        pc = regs['pc']
        e['trace'].append({'regs': regs, 'bytes': p.read_bytes(c, pc, 6).hex()})
        if pc == sy['load_done_dynamic_ready']:
            e['result'] = 'dynamic return'
            break
        if time.monotonic() - started > 25:
            e['result'] = 'bounded step count reached'
            break
        step()
    e.setdefault('result', '30000 steps reached')
    e['final'] = {'registers': c.call('read_registers'), 'dp': p.read_bytes(c, 0x8f, 80).hex(),
                  'instruction_intact': p.read_bytes(c, 0x300, len(payloads['instruction'])) == payloads['instruction']}
    live_enemy = p.read_bytes(c, 0x800, len(enemy))
    e['ram_code_changes'] = [{'addr': 0x800+i, 'expected': old, 'live': new}
                             for i, (old, new) in enumerate(zip(enemy, live_enemy)) if old != new]
    print('RAM code changes=' + json.dumps(e['ram_code_changes'][:20]), flush=True)
    e['steps'] = len(e['trace'])
    e['trace'] = e['trace'][:40] + e['trace'][-80:]
    print(json.dumps({'result': e['result'], 'steps': e['steps'], 'final': e['final']}), flush=True)
    if loading and e['result'] == 'dynamic return' and not e['ram_code_changes']:
        step()
        next_pc = go('second hydrated load or credit tick', [call, sy['credit_tick']])
        e['second_boundary'] = next_pc
        if next_pc == call:
            step()
            started = time.monotonic()
            tail = []
            for n in range(30000):
                regs = c.call('read_registers')
                pc = regs['pc']
                tail.append({'regs': regs, 'bytes': p.read_bytes(c, pc, 6).hex()})
                tail = tail[-80:]
                if pc == sy['load_done_dynamic_ready']:
                    e['second_result'] = 'dynamic return'
                    break
                if time.monotonic() - started > 25:
                    e['second_result'] = 'bounded trace deadline'
                    break
                step()
            e['second_steps'] = n + 1
            e['second_trace'] = tail
            e['second_ram_code_unchanged'] = p.read_bytes(c, 0x800, len(enemy)) == enemy
            e.setdefault('second_result', '30000 steps reached')
            print(json.dumps({'second_result': e['second_result'], 'steps': n + 1, 'final': c.call('read_registers')}), flush=True)
except Exception as exc:
    e['error'] = repr(exc)
    print('ERROR ' + repr(exc), flush=True)
finally:
    out.write_text(json.dumps(e, indent=2) + '\n')
    c.close()
    p.stop(proc)
print(str(out), flush=True)
if 'error' in e:
    raise SystemExit(1)
