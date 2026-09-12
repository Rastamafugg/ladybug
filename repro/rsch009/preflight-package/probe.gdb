set pagination off
set confirm off
set remotetimeout 10
python
import gdb, hashlib, json, os, time
from pathlib import Path
out = Path(os.environ['RSCH009_OUTPUT'])
manifest = json.loads(Path(os.environ['RSCH009_MANIFEST']).read_text())
def record(event, **fields):
    with (out / 'events.jsonl').open('a') as f:
        f.write(json.dumps(dict(event=event, monotonic=time.monotonic(), **fields)) + '\n')
        f.flush()
        os.fsync(f.fileno())
    fd = os.open(out, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
def command(stage, text):
    record('command_start', stage=stage, command=text)
    result = gdb.execute(text, to_string=True)
    record('command_end', stage=stage, output=result)
    return result
try:
    command('setup', 'set architecture m6809')
    command('attach', 'target remote 127.0.0.1:65520')
    record('command_start', stage='breakpoint', command='break *0xc0e3')
    bp = gdb.Breakpoint('*0xc0e3')
    record('command_end', stage='breakpoint', number=bp.number)
    command('continue', 'continue')
    record('command_start', stage='stop_pc', command="parse_and_eval('$pc')")
    pc = int(gdb.parse_and_eval('$pc'))
    record('command_end', stage='stop_pc', pc=pc)
    record('stop', pc=pc)
    if pc != 0xc0e3:
        raise RuntimeError('Unexpected stop; no code-identity inference permitted')
    record('command_start', stage='remove_breakpoint', command='bp.delete(); bp.is_valid()')
    bp.delete()
    if bp.is_valid():
        raise RuntimeError('Breakpoint removal not confirmed')
    record('command_end', stage='remove_breakpoint', valid=False)
    record('command_start', stage='removed_pc', command="parse_and_eval('$pc')")
    pc_removed = int(gdb.parse_and_eval('$pc'))
    record('command_end', stage='removed_pc', pc=pc_removed)
    record('breakpoint_removed', pc=pc_removed)
    if pc_removed != pc:
        raise RuntimeError('PC changed during breakpoint removal')
    # Read only code, never the forced-RAM or I/O tail of the ROM window.
    record('command_start', stage='capture', command='read_memory(0xc0e3,22)')
    raw = bytes(gdb.selected_inferior().read_memory(0xc0e3, 22))
    with (out / 'mainloop.bin').open('xb') as f:
        f.write(raw)
        f.flush()
        os.fsync(f.fileno())
    record('command_end', stage='capture', bytes=len(raw))
    expected = bytes.fromhex(manifest['comparison']['expected_hex'])
    differences = [dict(offset=i, address=0xc0e3+i, expected=a, actual=b)
                   for i, (a, b) in enumerate(zip(expected, raw)) if a != b]
    record('command_start', stage='capture_pc', command="parse_and_eval('$pc')")
    pc_after = int(gdb.parse_and_eval('$pc'))
    record('command_end', stage='capture_pc', pc=pc_after)
    record('comparison', passed=(raw == expected and pc_after == pc),
           sha256=hashlib.sha256(raw).hexdigest(), pc_after=pc_after,
           differences=differences, bytes=len(raw))
except BaseException as exc:
    record('failure', error=str(exc))
finally:
    # Do not detach/resume. The supervisor terminates the owned process groups.
    record('gdb_capture_finished')
    while True:
        time.sleep(0.1)
end
