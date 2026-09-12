"""Prepared, not runtime-validated. Refuses launch without a reviewed approval file."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def persist(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    with temporary.open('w') as f:
        json.dump(value, f, indent=2)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())
    os.replace(temporary, path)
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)

def events(path):
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            pass  # Interrupted partial tail remains retained on disk.
    return rows

def alive(pgid):
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False

def terminate(pgid, sig):
    try:
        os.killpg(pgid, sig)
    except ProcessLookupError:
        pass

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--approval', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if os.name != 'posix':
        raise SystemExit('Linux/WSL required; no process started')
    approval = json.loads(args.approval.read_text())
    mf = HERE / 'inputs.json'
    manifest = json.loads(mf.read_text())
    required = ('approved_by', 'approved_at', 'scope', 'budget', 'reviewed_package_sha256')
    if not approval.get('execution_approved') or not all(approval.get(k) for k in required):
        raise SystemExit('Explicit scope, budget and reviewed package approval missing')
    if approval['scope'] != 'boot-code-identity-only':
        raise SystemExit('Wrong approved scope')
    budget = approval['budget']
    if not isinstance(budget, dict) or not all(budget.get(k) for k in
            ('ceiling', 'unit', 'accounting_method', 'closure_reserve', 'approved_text')):
        raise SystemExit('Explicit spending bound, accounting method and closure reserve required')
    package = {n: sha(HERE / n) for n in ('inputs.json', 'probe.gdb', 'supervisor.py')}
    if approval['reviewed_package_sha256'] != package:
        raise SystemExit('Package changed since review')
    for entry in manifest['inputs']:
        if sha(ROOT / entry['path']) != entry['sha256']:
            raise SystemExit('Input changed: ' + entry['path'])
    c = manifest['comparison']
    runtime = (ROOT / 'build/ladybug-runtime.rom').read_bytes()
    if (c['absolute_start'], c['absolute_end_exclusive'], c['file_offset'], c['length']) != (0xc0e3, 0xc0f9, 0xe3, 22):
        raise SystemExit('Unexpected comparison contract')
    if bytes.fromhex(c['expected_hex']) != runtime[0xe3:0xf9]:
        raise SystemExit('Expected bytes do not match pinned binary')
    # Only reserve/test bind availability; never probe-connect to the stub.
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1', 65520))
    gdb = Path('/usr/local/bin/m6809-gdb')
    xroar = Path('/usr/local/bin/xroar')
    for exe in (gdb, xroar):
        if not exe.is_file() or not os.access(exe, os.X_OK):
            raise SystemExit('Required executable unavailable: ' + str(exe))
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    commands = [[str(xroar), '-ui', 'null', '-ao', 'null', '-machine', 'coco3',
                 '-ram', '512', '-cart-type', 'gmc', '-cart-rom', str(ROOT / 'build/ladybug.rom'),
                 '-cart-autorun', '-gdb', '-gdb-ip', '127.0.0.1', '-gdb-port', '65520'],
                [str(gdb), '--nx', '--quiet', '--batch', '-x', str(HERE / 'probe.gdb')]]
    state = dict(status='started', attempted=0, successful=0, commands=commands,
                 package=package, approval=approval, inputs=manifest,
                 tools={str(p): sha(p) for p in (gdb, xroar)}, processes=[])
    persist(out / 'status.json', state)
    children, handles = [], []
    started = time.monotonic()  # Includes launch, attach, capture, shutdown.
    state['monotonic_start'] = started
    state['hard_deadline'] = started + 60
    persist(out / 'status.json', state)
    def interrupted(signum, frame):
        raise InterruptedError('Supervisor signal ' + str(signum))
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    try:
        for ix, cmd in enumerate(commands):
            if time.monotonic() >= started + 50:
                raise TimeoutError('Observation allowance exhausted')
            handle = (out / ('xroar.log' if ix == 0 else 'gdb.log')).open('xb', buffering=0)
            handles.append(handle)
            env = dict(os.environ, RSCH009_OUTPUT=str(out), RSCH009_MANIFEST=str(mf))
            process = subprocess.Popen(cmd, stdout=handle, stderr=subprocess.STDOUT,
                                       start_new_session=True, env=env)
            children.append(process)
            state['attempted'] = 1
            state['processes'].append(dict(pid=process.pid, pgid=process.pid, command=cmd))
            persist(out / 'status.json', state)
            if ix == 0:
                # Check listening PID through ss, not a connection to the GDB stub.
                ready_until = min(started + 4, started + 50)
                while time.monotonic() < ready_until:
                    if process.poll() is not None:
                        raise RuntimeError('XRoar exited before attach')
                    listing = subprocess.run(['ss', '-H', '-ltnp', 'sport', '=', ':65520'],
                                             capture_output=True, text=True, timeout=0.5)
                    if f'pid={process.pid},' in listing.stdout:
                        break
                    time.sleep(0.05)
                else:
                    raise TimeoutError('Owned listener not confirmed within four seconds')
        while children[-1].poll() is None:
            now = time.monotonic()
            rows = events(out / 'events.jsonl')
            if any(r['event'] == 'gdb_capture_finished' for r in rows):
                break
            pending = next((r for r in reversed(rows) if r['event'] == 'command_start'), None)
            last_end = max((r['monotonic'] for r in rows if r['event'] == 'command_end'), default=0)
            if now >= started + 50:
                raise TimeoutError('Whole observation deadline; ten seconds reserved for cleanup')
            if pending and pending['monotonic'] > last_end:
                cap = 15 if pending['stage'] == 'continue' else 10
                if now - pending['monotonic'] >= cap:
                    raise TimeoutError('Command timeout: ' + pending['stage'])
            time.sleep(0.05)
        rows = events(out / 'events.jsonl')
        comparison = next((r for r in rows if r['event'] == 'comparison'), None)
        state['capture_passed'] = bool(comparison and comparison['passed'])
        state['gdb_capture_finished'] = any(r['event'] == 'gdb_capture_finished' for r in rows)
        if any(r['event'] == 'failure' for r in rows):
            state['error'] = 'GDB command/capture failure; see events.jsonl'
    except BaseException as exc:
        state['error'] = str(exc)
    finally:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        for p in children:
            if alive(p.pid):
                terminate(p.pid, signal.SIGTERM)
        until = min(time.monotonic() + 2, started + 57)
        while time.monotonic() < until and any(p.poll() is None for p in children):
            time.sleep(0.05)
        for p in children:
            if alive(p.pid):
                terminate(p.pid, signal.SIGKILL)
            try:
                p.wait(timeout=max(0.01, min(0.5, started + 59 - time.monotonic())))
            except subprocess.TimeoutExpired:
                pass
        state['cleanup'] = [dict(pid=p.pid, exit=p.poll(), group_alive=alive(p.pid)) for p in children]
        state['gdb_exit'] = children[-1].poll() if len(children) == 2 else None
        for f in handles:
            os.fsync(f.fileno())
            f.close()
        state['elapsed_seconds'] = time.monotonic() - started
        clean = all(not r['group_alive'] and r['exit'] is not None for r in state['cleanup'])
        passed = state.get('capture_passed', False) and state.get('gdb_capture_finished', False)
        passed = passed and clean and state['elapsed_seconds'] <= 60 and 'error' not in state
        state.update(status='pass' if passed else 'fail', successful=int(passed))
        persist(out / 'status.json', state)
    return 0 if state['status'] == 'pass' else 1

if __name__ == '__main__':
    raise SystemExit(main())
