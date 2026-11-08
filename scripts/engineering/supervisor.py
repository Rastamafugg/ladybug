"""One POSIX job owner. Parent EOF, signals and one deadline all clean children."""
from __future__ import annotations

import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import time

from core import save_new


def main():
    spec_path = Path(sys.argv[1]).resolve()
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    root = spec_path.parent
    started = time.monotonic()
    deadline = started + spec["seconds"]
    process = None
    interrupted = []
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda number, frame: interrupted.append(number))
    result = {"schema": 1, "classification": "harness_failure", "exit_code": None}
    try:
        with (root / "output.log").open("xb") as output:
            environment = os.environ.copy()
            environment.update(spec["env"])
            environment["PYTHONDONTWRITEBYTECODE"] = "1"
            process = subprocess.Popen(spec["argv"], cwd=spec["cwd"], env=environment,
                                       stdin=subprocess.DEVNULL, stdout=output, stderr=output,
                                       start_new_session=True)
            result["pid"] = process.pid
            while True:
                if interrupted:
                    result.update(classification="cancelled", reason="supervisor signal")
                    break
                readable, _, _ = select.select([sys.stdin], [], [], 0)
                if readable and not os.read(sys.stdin.fileno(), 1):
                    result.update(classification="cancelled", reason="controller channel closed")
                    break
                if time.monotonic() >= deadline - min(0.5, spec["seconds"] / 4):
                    result.update(classification="timeout", reason="whole-job deadline")
                    break
                code = process.poll()
                if code is not None:
                    result.update(classification="passed" if code == 0 else "command_failed", exit_code=code)
                    break
                time.sleep(min(0.02, max(0, deadline - time.monotonic())))
    except BaseException as error:
        result.update(classification="harness_failure", reason=str(error))
    finally:
        if process is not None:
            # Kill the owned group even if its leader exited, so a child cannot
            # silently outlive a successful or failed parent command.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                result.update(classification="cleanup_failure", reason="owned process did not exit after KILL")
            result["process_exited"] = process.poll() is not None
        result["elapsed_seconds"] = round(time.monotonic() - started, 4)
        save_new(root / "result.json", result)
    return 0 if result["classification"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
