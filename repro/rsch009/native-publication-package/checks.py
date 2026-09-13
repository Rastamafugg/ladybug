"""Reserved Phase B offline checks. Deliberately inert until separately authorized."""
import argparse, json
from pathlib import Path

# Phase B harness policy: install deny-by-default guards before any tested import.
DENIED_APIS = ('subprocess', 'socket', 'signal', 'select', 'ctypes', 'os.kill', 'os.exec', 'serial', 'xroar', 'gdb')
CASES = (
    ('static_frame_hash', 'reconstruct 960 cells and require pinned hash'),
    ('sprite_escape', 'test ordinary zero delta, nonzero FF escape, FF0000 termination, bounds'),
    ('masked_runs', 'test run bit7 and masked value/mask pairs'),
    ('truncation', 'reject truncated RLE, font, descriptor, frame, and saved buffers'),
    ('full_frames', 'compare two 30720-byte frames and four 128-byte buffers exactly'),
    ('deadlines', 'exercise cooperative checkpoints and stage/command cutoffs with fake clock'),
    ('markers', 'reject missing, late, duplicate, and unpaired command markers'),
    ('cleanup', 'validate restoration and owned-group cleanup decisions using in-memory fakes'),
)

def main():
    p = argparse.ArgumentParser(); p.add_argument('--inputs', type=Path, required=True); p.add_argument('--output', type=Path, required=True)
    args = p.parse_args(); data = json.loads(args.inputs.read_text())
    if data.get('execution_approved') is True: raise SystemExit('Phase B requires a distinct approval record')
    raise SystemExit('offline checks not approved; no comparator or check case executed')

if __name__ == '__main__': main()
