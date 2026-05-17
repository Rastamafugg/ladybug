"""Milestone-1 verification probe for the WS-A tester ROM.

Spins up XRoar with build/tester.rom, halts after boot, and verifies:
  - Palette $FFB0..$FFBF matches the tester palette (boot reached palette load)
  - DP slots $0200..$020C are zero-initialized
  - FB at $2000 shows bar pattern (stripe 0 = $00, stripe 1 = $11, etc.)
  - PC is inside the `halt` self-loop (boot reached the spin)

Run inside WSL from repo root:
    python3 web/scripts/probe_tester_boot.py
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
ROM = REPO_ROOT / "build" / "tester.rom"

EXPECTED_PALETTE = bytes(
    [0x00, 0x20, 0x10, 0x08, 0x30, 0x18, 0x28, 0x38,
     0x04, 0x02, 0x01, 0x06, 0x03, 0x05, 0x07, 0x3F]
)
STRIPE_HEIGHT_ROWS = 12
ROW_BYTES = 160  # 320 px / 2 px-per-byte
STRIPE_BYTES = STRIPE_HEIGHT_ROWS * ROW_BYTES  # = 1920


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
    print(f"probe: launching xroar-monitor with tester.rom on monitor port {port}")
    proc = await asyncio.create_subprocess_exec(
        XROAR_BIN,
        "-machine", "coco3", "-ram", "512",
        "-cart", "ladybug", "-cart-type", "rom",
        "-cart-rom", str(ROM), "-cart-autorun",
        "-tv-input", "rgb",
        "-monitor", f"127.0.0.1:{port}",
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    ok = True
    try:
        await asyncio.sleep(4.0)
        mon = MonitorSession(port)
        await mon.attach()
        try:
            try:
                await mon.interrupt()
                await asyncio.sleep(0.3)
            except MonitorError:
                pass

            regs = await mon.read_registers()
            pc = regs.get("pc", 0)

            palette = await mon.read_memory(0xFFB0, 16)
            dp_slots = await mon.read_memory(0x0200, 13)

            # Check stripe 0 (FB[0..15] should be $00) and stripe 1 (FB[1920..1935] = $11).
            stripe0 = await mon.read_memory(0x2000, 16)
            stripe1 = await mon.read_memory(0x2000 + STRIPE_BYTES, 16)
            stripeF = await mon.read_memory(0x2000 + 15 * STRIPE_BYTES, 16)
        finally:
            await mon.detach()
    finally:
        if proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                proc.kill()

    def check(label: str, got, expected, hexbytes: bool = False) -> None:
        nonlocal ok
        if hexbytes:
            ok_now = got == expected
            print(f"  {label}: {got.hex(' ')}   {'OK' if ok_now else 'EXPECTED ' + expected.hex(' ')}")
        else:
            ok_now = got == expected
            print(f"  {label}: {got!r}   {'OK' if ok_now else f'EXPECTED {expected!r}'}")
        if not ok_now:
            ok = False

    print(f"\n== PC ==\n  pc=0x{pc:04X}  (expect inside halt loop, ~0xC035)")
    if not (0xC033 <= pc <= 0xC040):
        print("  WARN: PC not in expected halt range; boot may not have reached spin")
        ok = False

    print("\n== Palette ==")
    check("$FFB0..$FFBF", palette, EXPECTED_PALETTE, hexbytes=True)

    print("\n== DP slots $0200..$020C (all zero on boot) ==")
    check("13 bytes", dp_slots, bytes(13), hexbytes=True)

    print("\n== Framebuffer bar pattern ==")
    check("stripe 0  @ $2000              ", stripe0, bytes([0x00]) * 16, hexbytes=True)
    check("stripe 1  @ $2000+1920         ", stripe1, bytes([0x11]) * 16, hexbytes=True)
    check("stripe 15 @ $2000+15*1920      ", stripeF, bytes([0xFF]) * 16, hexbytes=True)

    print()
    print("== Verdict ==")
    print("  PASS — boot + mode setup + bars renderer all working." if ok else "  FAIL — see mismatches above.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
