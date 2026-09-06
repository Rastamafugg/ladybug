"""Read-only natural credit failure capture; current complete build required."""
import json
import argparse
import time
from pathlib import Path
import verify_bug011_runtime as p
import verify_feat003_highscore_test as v

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'repro/bug032-clean-credit'
OUT.mkdir(parents=True, exist_ok=True)
ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument('--control', action='store_true', help='Halt at attract and watch the first PRES_MAGIC write')
args = ap.parse_args()
sy = p.symbols(ROOT / 'build/ladybug-presentation-runtime.map')
rom = ROOT / 'build/ladybug.rom'
monitor = p.load_monitor()
binary = ROOT / 'docs/reference/xroar/src/xroar'
e = {'rom_sha256': p.digest(rom.read_bytes()), 'tool_sha256': p.digest(binary.read_bytes()),
     'deadline_seconds': 30, 'transitions': [], 'code_writes': 0, 'state_writes': 0}
proc, c = monitor.launch(binary, rom, monitor.free_port())

def phys(addr, length):
    return bytes.fromhex(c.call('read_memory', {'space': 'physical', 'addr': addr, 'length': length})['data'])

def capture(label):
    c.call('pause')
    c.call('wait_for_stop', {'timeout_ms': 2000}, timeout=3)
    regs = c.call('read_registers')
    snap = {'label': label, 'registers': regs, 'gime': c.call('read_gime_state'), 'identity': {}}
    low = phys(0x38*8192, 8192)
    (OUT / (label+'-low.bin')).write_bytes(low)
    snap['low_sha256'] = p.digest(low)
    for name, addr in [('enemy-runtime.rom', 0x800), ('presentation-runtime.bin', 0x1900),
                       ('highscore-runtime.bin', 0x300), ('instruction-runtime.bin', 0x300)]:
        authored = (ROOT / ('build/ladybug-'+name)).read_bytes()
        live = low[addr:addr+len(authored)]
        differences = [addr+i for i, (a,b) in enumerate(zip(authored, live)) if a != b]
        snap['identity'][name] = {'authored_sha256': p.digest(authored), 'live_sha256': p.digest(live),
                                  'different_bytes': len(differences), 'first_differences': differences[:20]}
    for name, symbol in [('highscore', 'PRESENTATION_HIGHSCORE_RUNTIME_ADDRESS')]:
        authored = (ROOT / ('build/ladybug-'+name+'-runtime.bin')).read_bytes()
        staged = phys(0x23*8192+sy[symbol]-0xa000, len(authored))
        snap[name+'_staged_matches'] = authored == staged
    snap['cpu_low_matches_physical'] = p.read_bytes(c, 0, 8192) == low
    pc = regs['pc']
    snap['pc_bytes'] = p.read_bytes(c, pc, 32).hex()
    snap['state_8f_df'] = low[0x8f:0xe0].hex()
    for owner, page in [(0,0x30),(1,0x2c),(2,0x28)]:
        frame = phys(page*8192,30720)
        v.write_frame_png(OUT / (label+f'-owner{owner}.png'), frame)
    e.setdefault('captures', []).append(snap)

def wait(label, predicate):
    print(label+': deadline 30s; timeout means boundary not observed', flush=True)
    deadline = time.monotonic()+30
    prev = None
    while time.monotonic() < deadline:
        state = phys(0x38*8192+0x8f, 0x51)
        signature = tuple(state[i-0x8f] for i in [0xa4,0xa5,0xa6,0xa8,0xd4,0xd9])
        if signature != prev:
            e['transitions'].append({'phase':label,'state':state.hex()})
            prev = signature
        if predicate(state):
            return
        if label != 'boot' and state[0xa5-0x8f] > 8:
            raise AssertionError('invalid mode observed')
        time.sleep(.005)
    raise AssertionError(label+' deadline missed')

try:
    if args.control:
        ids = monitor.setup(c, [sy['load_done_normal']])
        e['publication_stop'] = c.run_to_breakpoint(30)
        monitor.clear(c, ids)
        capture('before-credit')
        c.call('set_watchpoint', {'addr':0xa4,'kind':'w','length':1})
    else:
        c.call('run')
        wait('boot', lambda s: s[0xa5-0x8f] == 2)
    c.call('inject_key', {'key':5,'action':'press'})
    if args.control:
        c.call('run')
        e['stop'] = c.call('wait_for_stop', {'timeout_ms':30000}, timeout=32)
        assert e['stop']['reason'] != 'timeout', 'write watchpoint deadline missed'
        capture('first-write')
    else:
        wait('credit', lambda s: s[0xa5-0x8f] == 5 and s[2] == 0)
        capture('credit')
    e['passed'] = True
except Exception as exc:
    e['error'] = repr(exc)
    capture('failure')
finally:
    (OUT / ('control.json' if args.control else 'natural.json')).write_text(json.dumps(e,indent=2)+'\n')
    c.close()
    p.stop(proc)
print(json.dumps({k:v for k,v in e.items() if k not in ['captures','transitions']}),flush=True)
