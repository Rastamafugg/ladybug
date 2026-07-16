"""End-to-end verification for the 2026-06-11 breakpoint/stepping fixes.

Drives the web backend's REST API the same way the UI does and checks:

  1. Breakpoint add/remove while free-running completes in well under a
     second (was ~30-60 s when the halt watcher's wait_for_stop long-poll
     serialized the monitor connection).
  2. GET /breakpoints reflects emulator truth after add/remove.
  3. Duplicate breakpoint IDs at one address can all be removed, matching
     the source pane's address-to-ID-list behavior.
  4. Interrupt halts promptly and the instance state lands on 'halted'.
  5. The cont() race guard: continuing with a breakpoint at the current
     PC must leave the instance HALTED (bp fires within the round-trip),
     never wedged in RUNNING.

Usage (backend already running on $LADYBUG_WEB_URL or :8766):
    python3 web/scripts/verify_breakpoint_responsiveness.py
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request

BASE = os.environ.get("LADYBUG_WEB_URL", "http://127.0.0.1:8766")
FAILURES: list[str] = []


def req(method: str, path: str, body: dict | None = None, timeout: float = 90.0):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(
        BASE + path, data=data, method=method,
        headers={"content-type": "application/json"} if data else {},
    )
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return json.loads(resp.read() or b"null")


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  {'OK  ' if cond else 'FAIL'} {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(name)


def inst_state(iid: str) -> str:
    for s in req("GET", "/api/instances"):
        if s["id"] == iid:
            return s["state"]
    return "?"


def wait_state(iid: str, want: str, timeout: float = 20.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if inst_state(iid) == want:
            return True
        time.sleep(0.2)
    return False


def main() -> int:
    print(f"target: {BASE}")
    inst = req("POST", "/api/instances",
               {"name": "verify-bp", "rom_path": "build/ladybug.rom"})
    iid = inst["id"]
    print(f"instance {iid} created")
    try:
        check("instance halts on start", wait_state(iid, "halted"))

        regs = req("GET", f"/api/instances/{iid}/registers")
        pc0 = regs["pc"]
        print(f"  pc at attach: 0x{pc0:04X}")

        # ---- 1+2: bp add/remove latency while free-running -------------
        req("POST", f"/api/instances/{iid}/actions/continue")
        check("continue -> running", wait_state(iid, "running", 5.0))

        t0 = time.monotonic()
        bp = req("POST", f"/api/instances/{iid}/breakpoints", {"addr": 0x0021})
        dt_add = time.monotonic() - t0
        check("bp add while running < 2s", dt_add < 2.0, f"{dt_add:.2f}s")

        lst = req("GET", f"/api/instances/{iid}/breakpoints")
        check("bp listed after add",
              any(b["addr"] == 0x0021 for b in lst), json.dumps(lst))

        # _with_paused resumes after the mutation; we should be running.
        check("still running after bp add", wait_state(iid, "running", 5.0))

        t0 = time.monotonic()
        req("DELETE", f"/api/instances/{iid}/breakpoints/{bp['id']}")
        dt_del = time.monotonic() - t0
        check("bp remove while running < 2s", dt_del < 2.0, f"{dt_del:.2f}s")
        lst = req("GET", f"/api/instances/{iid}/breakpoints")
        check("bp list empty after remove", lst == [], json.dumps(lst))

        # Duplicate BPs are legal in the monitor. The source pane groups
        # every ID by address and clears the whole group on a gutter click.
        req("POST", f"/api/instances/{iid}/breakpoints", {"addr": 0x0021})
        req("POST", f"/api/instances/{iid}/breakpoints", {"addr": 0x0021})
        lst = req("GET", f"/api/instances/{iid}/breakpoints")
        duplicates = [b for b in lst if b["addr"] == 0x0021]
        check("duplicate bp IDs retained", len(duplicates) == 2, json.dumps(lst))
        for duplicate in duplicates:
            req("DELETE", f"/api/instances/{iid}/breakpoints/{duplicate['id']}")
        lst = req("GET", f"/api/instances/{iid}/breakpoints")
        check("all duplicate bp IDs removed", lst == [], json.dumps(lst))
        check("still running after duplicate cleanup", wait_state(iid, "running", 5.0))

        # ---- 4: interrupt halts promptly --------------------------------
        t0 = time.monotonic()
        req("POST", f"/api/instances/{iid}/actions/interrupt")
        ok = wait_state(iid, "halted", 5.0)
        check("interrupt -> halted < 5s", ok,
              f"{time.monotonic() - t0:.2f}s")

        # ---- 5: cont() race — bp at current PC --------------------------
        regs = req("GET", f"/api/instances/{iid}/registers")
        pc = regs["pc"]
        bp = req("POST", f"/api/instances/{iid}/breakpoints", {"addr": pc})
        req("POST", f"/api/instances/{iid}/actions/continue")
        # The bp fires within the run round-trip. The old code could emit
        # 'running' after the stop and wedge the state. Give the events a
        # moment, then require HALTED.
        time.sleep(1.5)
        st = inst_state(iid)
        check("continue onto bp-at-PC lands HALTED (race guard)",
              st == "halted", f"state={st}")
        req("DELETE", f"/api/instances/{iid}/breakpoints/{bp['id']}")

        # ---- step sanity -------------------------------------------------
        regs = req("GET", f"/api/instances/{iid}/registers")
        pc_before = regs["pc"]
        r = req("POST", f"/api/instances/{iid}/actions/step")
        regs = req("GET", f"/api/instances/{iid}/registers")
        check("step advances PC", r.get("ok") is True and regs["pc"] != pc_before,
              f"0x{pc_before:04X} -> 0x{regs['pc']:04X}")
        check("halted after step", inst_state(iid) == "halted")
    finally:
        req("DELETE", f"/api/instances/{iid}")
        print(f"instance {iid} deleted")

    print()
    if FAILURES:
        print(f"FAIL: {len(FAILURES)} check(s) failed: {FAILURES}")
        return 1
    print("PASS: breakpoint/stepping responsiveness verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
