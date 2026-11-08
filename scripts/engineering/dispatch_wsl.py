"""TOOL-019 fixed WSL bootstrap: READY/GO, owned groups, 40/45-second budget."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import time
if __package__:
    from .core import save_new
else:
    from core import save_new

ROOT = Path(__file__).resolve().parents[2]
DESCRIPTION = "repro/engineering/20261107T174853Z-keyboard-adaptive-e330a828efe6/build.json"
ENVIRONMENT = "repro/engineering/20261107T135116Z-doctor-d37896a3c907/environment.json"


def emit(event, **fields):
    print(json.dumps(dict(event=event, **fields), separators=(",", ":")), flush=True)


def fixed_command(operation, evidence):
    if operation == "Tool019Q1":
        return [sys.executable, "-B", str(ROOT/"scripts/test_engineering.py"), "--case", "tool019-q1", "--evidence", str(evidence/"fixtures")]
    if operation == "Tool019ManualDown":
        return [sys.executable, "-B", str(ROOT/"scripts/ladybug.py"), "--runs", str(evidence/"native"), "observe", "--description", str(ROOT/DESCRIPTION), "--environment", str(ROOT/ENVIRONMENT), "--scenario", str(ROOT/"scripts/engineering/scenarios/attract-manual-down.json")]
    raise ValueError("unsupported_operation")


def process_tree(parent):
    """Capture only descendants of our retained PID, including new sessions."""
    records = {}
    for path in Path("/proc").glob("[0-9]*/stat"):
        try:
            text = path.read_text(); fields = text[text.rfind(")")+2:].split()
            records[int(path.parent.name)] = (int(fields[1]), fields[19])
        except (OSError, ValueError, IndexError):
            continue
    owned = {parent}
    changed = True
    while changed:
        previous = len(owned)
        owned.update(pid for pid, (ppid, _) in records.items() if ppid in owned)
        changed = len(owned) != previous
    return {pid: records[pid][1] for pid in owned if pid in records}


def same_process(pid, birth):
    try:
        text = Path("/proc/%d/stat" % pid).read_text(); fields = text[text.rfind(")")+2:].split()
        return fields[19] == birth and fields[0] != "Z"
    except (OSError, IndexError):
        return False


def run_owned(argv, evidence, control, work_seconds=40, grace_seconds=5):
    """No real GDB/XRoar is used by its offline process fixtures."""
    start = time.monotonic(); result = dict(classification="harness_failure", exit_code=None)
    process, owned = None, {}
    with (evidence/"native-output.log").open("xb") as log:
        try:
            process = subprocess.Popen(argv, cwd=ROOT, stdin=subprocess.DEVNULL,
                                       stdout=log, stderr=log, start_new_session=True)
            emit("native_work_start", pid=process.pid)
            owned.update(process_tree(process.pid))
            while True:
                if same_process(process.pid, owned.get(process.pid, "")):
                    for pid, birth in process_tree(process.pid).items():
                        owned.setdefault(pid, birth)
                if control is not None and select.select([control], [], [], 0)[0]:
                    if not os.read(control.fileno(), 1):
                        result["classification"] = "cancelled"; break
                code = process.poll()
                if code is not None:
                    result.update(classification="passed" if code == 0 else "command_failed", exit_code=code)
                    emit("native_work_exit", code=code); break
                if time.monotonic()-start >= work_seconds:
                    result["classification"] = "timeout"; emit("native_work_deadline"); break
                time.sleep(.01)
        finally:
            # Capture identities before parent death; do not signal reused PIDs.
            if process:
                if same_process(process.pid, owned.get(process.pid, "")):
                    for pid, birth in process_tree(process.pid).items():
                        owned.setdefault(pid, birth)
                for pid, birth in reversed(list(owned.items())):
                    if same_process(pid, birth):
                        try: os.kill(pid, signal.SIGKILL)
                        except ProcessLookupError: pass
                try: process.wait(timeout=max(.01, min(.5, start+work_seconds+grace_seconds-time.monotonic())))
                except subprocess.TimeoutExpired: pass
            end = start+work_seconds+grace_seconds-.2
            while any(same_process(pid,birth) for pid,birth in owned.items()) and time.monotonic()<end:
                time.sleep(.01)
            alive = [pid for pid,birth in owned.items() if same_process(pid,birth)]
            if alive: result.update(classification="cleanup_failure", surviving_owned_pids=alive)
            else: emit("owned_children_exited")
    result.update(elapsed_seconds=round(time.monotonic()-start,4), owned_pids=list(owned), children_exited=not alive)
    save_new(evidence/"native-receipt.json", result)
    emit("native_receipt", classification=result["classification"])
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operation", choices=("Tool019Q1","Tool019ManualDown"), required=True)
    parser.add_argument("--evidence",type=Path,required=True)
    args=parser.parse_args()
    evidence=args.evidence.resolve()
    evidence.relative_to((ROOT/"repro").resolve())
    if not evidence.is_dir(): raise ValueError("host_evidence_root_missing")
    command=fixed_command(args.operation,evidence)
    emit("ready")
    # readline only after select: the host can always cancel by closing control.
    if not select.select([sys.stdin],[],[],10)[0]: return 2
    if sys.stdin.buffer.readline().strip()!=b"GO": return 2
    result=run_owned(command,evidence,sys.stdin)
    return 0 if result["classification"]=="passed" else 1

if __name__=="__main__":
    raise SystemExit(main())
