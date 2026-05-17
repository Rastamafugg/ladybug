"""WS-A probe: can XRoar's gdb stub read back the write-only GIME regs?

Spins up an XRoar instance running build/diag.rom (built from
src/diag_minimal.s), waits for it to settle in the `bra halt` self-loop,
then reads $FF98-$FF9E (the question), plus $FFA0-$FFA7 PARs and
$FFB0-$FFBF palette (controls / channel sanity).

Compares observed bytes to the writes diag_minimal performs at boot and
recommends a ReadStrategy: option 1 (direct) if matches, option 2
(program-state) if garbage/inconsistent.

Run inside WSL from repo root:
    python3 web/scripts/probe_gime_readback.py
"""
from __future__ import annotations
import asyncio
import socket
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from web.backend.monitor_session import MonitorSession, MonitorError  # noqa: E402

import os
XROAR_BIN = os.environ.get(
    "XROAR_BIN",
    str(REPO_ROOT / "docs" / "reference" / "xroar" / "build" / "xroar-monitor"),
)
ROM = REPO_ROOT / "build" / "diag.rom"

EXPECTED = {
    0xFF90: 0x08,
    0xFF98: 0x80,
    0xFF99: 0x1E,
    0xFF9A: 0x28,
    0xFF9D: 0xE4,
    0xFF9E: 0x00,
}
EXPECTED_PALETTE = bytes(
    [0x00, 0x20, 0x10, 0x08, 0x30, 0x18, 0x28, 0x38,
     0x04, 0x02, 0x01, 0x06, 0x03, 0x05, 0x07, 0x3F]
)


def pick_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


async def run() -> int:
    if not ROM.exists():
        print(f"FAIL: rom not found: {ROM}", file=sys.stderr)
        return 2
    port = pick_port()
    print(f"probe: launching xroar-monitor on monitor port {port}")
    proc = await asyncio.create_subprocess_exec(
        XROAR_BIN,
        "-machine", "coco3",
        "-ram", "512",
        "-cart", "ladybug",
        "-cart-type", "rom",
        "-cart-rom", str(ROM),
        "-cart-autorun",
        "-tv-input", "rgb",
        "-monitor", f"127.0.0.1:{port}",
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        await asyncio.sleep(4.0)  # boot + autorun
        mon = MonitorSession(port)
        await mon.attach()
        try:
            # diag_minimal halts in `bra halt`. Interrupt to ensure we stop
            # somewhere in that loop with all writes long since committed.
            try:
                await mon.interrupt()
                await asyncio.sleep(0.3)
            except MonitorError:
                pass

            ff90 = (await mon.read_memory(0xFF90, 1))[0]
            ff98_9e = await mon.read_memory(0xFF98, 7)  # $FF98..$FF9E
            ffa0 = await mon.read_memory(0xFFA0, 8)
            ffb0 = await mon.read_memory(0xFFB0, 16)
        finally:
            await mon.detach()
    finally:
        if proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                proc.kill()

    # --- report ---
    print()
    print("== GIME write-only regs ($FF90, $FF98..$FF9E) ==")
    matches = 0
    total = 0
    def show(addr: int, got: int) -> None:
        nonlocal matches, total
        exp = EXPECTED.get(addr)
        if exp is None:
            print(f"  ${addr:04X} = ${got:02X}")
            return
        total += 1
        ok = got == exp
        matches += ok
        print(f"  ${addr:04X} = ${got:02X}   expected ${exp:02X}   {'OK' if ok else 'MISMATCH'}")
    show(0xFF90, ff90)
    for i, b in enumerate(ff98_9e):
        show(0xFF98 + i, b)

    print()
    print("== PARs $FFA0..$FFA7 (MMU off — values uncommitted, just channel sanity) ==")
    print("  " + " ".join(f"{b:02X}" for b in ffa0))

    print()
    print("== Palette $FFB0..$FFBF (control — known-written) ==")
    print("  got      : " + " ".join(f"{b:02X}" for b in ffb0))
    print("  expected : " + " ".join(f"{b:02X}" for b in EXPECTED_PALETTE))
    pal_ok = ffb0 == EXPECTED_PALETTE
    print("  " + ("OK — gdb read transport is sound" if pal_ok else "MISMATCH — channel itself is broken"))

    print()
    print("== Verdict ==")
    if not pal_ok:
        print("  Palette readback failed. Stop and debug the gdb channel before")
        print("  deciding on a write-only-register strategy.")
        return 3
    if matches == total:
        print(f"  Write-only regs: {matches}/{total} match.")
        print("  -> Option 1 (DirectReadStrategy) is viable on XRoar.")
        print("     Note: real hardware still requires option 2 or 3.")
        return 0
    print(f"  Write-only regs: {matches}/{total} match.")
    print("  -> Option 1 NOT viable. Use Option 2 (ProgramStateStrategy):")
    print("     tester ROM exports tester_mode_idx + tester_mode_table; backend reads those.")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
