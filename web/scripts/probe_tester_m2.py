"""Milestone-2 verification probe for the WS-A tester ROM.

XRoar's gdb stub is hostile to mid-run inspection: -exec-interrupt is not
honored while running, and breakpoints at addresses other than the
attach-halt PC don't seem to fire reliably. So this probe only does a single
attach + state read.

Verifies (post-boot, after 4 seconds of free-run):
  - Palette is loaded correctly.
  - Bars pattern is rendered to FB.
  - Vbord ISR is firing: frame_ctr > 0.
  - kbd_scan_and_dispatch ran: tester_kbd_prev is populated (not all zero).

The mainloop dirty-flag → redraw path is NOT verified here — see
src/tester/tester.s mainloop and render.s redraw_with_blank for the code
that handles it. Real-keyboard interaction in the web-app UI is the user
acceptance test for that path.

Run inside WSL from repo root:
    python3 web/scripts/probe_tester_m2.py
"""
from __future__ import annotations
import asyncio
import socket
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from web.backend.gdb_session import GdbSession  # noqa: E402

XROAR_BIN = "/usr/local/bin/xroar"
ROM = REPO_ROOT / "build" / "tester.rom"

ADDR_PATTERN_IDX     = 0x0201
ADDR_SELECTION_DIRTY = 0x0202
ADDR_KBD_PREV        = 0x0203
ADDR_FRAME_CTR       = 0x020B

ROW_BYTES = 160
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
    print(f"probe: launching xroar with tester.rom on gdb port {port}")
    proc = await asyncio.create_subprocess_exec(
        XROAR_BIN,
        "-machine", "coco3", "-ram", "512",
        "-cart", "ladybug", "-cart-type", "rom",
        "-cart-rom", str(ROM), "-cart-autorun",
        "-tv-input", "rgb",
        "-gdb", "-gdb-ip", "127.0.0.1", "-gdb-port", str(port),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    ok = True
    try:
        await asyncio.sleep(4.0)
        gdb = GdbSession(port)
        await gdb.attach()
        try:
            regs = await gdb.read_registers()
            pc = regs.get("pc", 0)
            cc = regs.get("cc", 0)
            fc = int.from_bytes(await gdb.read_memory(ADDR_FRAME_CTR, 2), "big")
            pat = (await gdb.read_memory(ADDR_PATTERN_IDX, 1))[0]
            dirty = (await gdb.read_memory(ADDR_SELECTION_DIRTY, 1))[0]
            kbd_prev = await gdb.read_memory(ADDR_KBD_PREV, 8)
            palette = await gdb.read_memory(0xFFB0, 16)
            stripe0 = await gdb.read_memory(0x2000, 16)
            stripe1 = await gdb.read_memory(0x2000 + 12 * ROW_BYTES, 16)
            irq_jmp = await gdb.read_memory(0xFEF7, 3)
            # diagnostic: PIA state + col_drive_table sanity
            pia_regs = await gdb.read_memory(0xFF00, 4)
            col_drive = await gdb.read_memory(0xC11B, 8)
        finally:
            await gdb.detach()
    finally:
        if proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                proc.kill()

    print(f"\n== CPU state ==")
    print(f"  pc=0x{pc:04X}  cc=0x{cc:02X}  (CC.I={'set' if cc & 0x10 else 'clear'})")

    print(f"\n== Mode/pattern state ==")
    print(f"  pattern_idx={pat}  dirty={dirty}  frame_ctr={fc}")
    if fc < 1:
        print("  FAIL: frame_ctr is zero — Vbord IRQ never fired in 4s")
        ok = False
    else:
        print(f"  OK: frame_ctr={fc} (~{fc/4:.0f} Hz over 4s; nominal 60 Hz, lower means cont halts contributed)")

    print(f"\n== IRQ vector at $FEF7 ==")
    print(f"  bytes: {irq_jmp.hex(' ')}  (expect 7E XX XX = JMP vbord_isr)")
    if irq_jmp[0] != 0x7E:
        print(f"  FAIL: $FEF7 should be 0x7E (JMP opcode)")
        ok = False
    else:
        target = (irq_jmp[1] << 8) | irq_jmp[2]
        print(f"  JMP target: 0x{target:04X}  (vbord_isr should be at 0xC070 per tester.map)")
        if target != 0xC070:
            print(f"  FAIL: ISR vector points to wrong addr")
            ok = False
        else:
            print("  OK: ISR vector installed correctly")

    print(f"\n== Palette ==")
    # GIME palette regs are 6-bit; upper 2 bits indeterminate on read. Mask them.
    palette_masked = bytes(b & 0x3F for b in palette)
    if palette_masked == EXPECTED_PALETTE:
        print(f"  OK: {palette.hex(' ')}  (masked: {palette_masked.hex(' ')})")
    else:
        print(f"  FAIL: got (masked) {palette_masked.hex(' ')}")
        print(f"        expected     {EXPECTED_PALETTE.hex(' ')}")
        ok = False

    print(f"\n== Framebuffer (bars) ==")
    print(f"  stripe 0 @ $2000: {stripe0.hex(' ')}  (expect 00*16)")
    print(f"  stripe 1 @ +1920: {stripe1.hex(' ')}  (expect 11*16)")
    if stripe0 != bytes(16) or stripe1 != bytes([0x11]) * 16:
        print("  FAIL: bars FB not as expected")
        ok = False
    else:
        print("  OK: bars pattern rendered")

    print(f"\n== PIA1 state ==")
    print(f"  $FF00 DRA={pia_regs[0]:02X}  $FF01 CRA={pia_regs[1]:02X}  $FF02 DRB={pia_regs[2]:02X}  $FF03 CRB={pia_regs[3]:02X}")
    print(f"  CRA b2 (data mode)={'1' if pia_regs[1] & 4 else '0'}   CRB b2 (data mode)={'1' if pia_regs[3] & 4 else '0'}")

    print(f"\n== col_drive_table @ $C11B (cart-ROM sanity) ==")
    print(f"  got:      {col_drive.hex(' ')}")
    print(f"  expected: fe fd fb f7 ef df bf 7f")
    if col_drive != bytes([0xFE, 0xFD, 0xFB, 0xF7, 0xEF, 0xDF, 0xBF, 0x7F]):
        print("  FAIL: col_drive_table contents wrong — cart-ROM read corruption?")
        ok = False

    print(f"\n== Keyboard scan ==")
    print(f"  tester_kbd_prev: {kbd_prev.hex(' ')}")
    if all(b == 0 for b in kbd_prev):
        print("  FAIL: kbd_prev is all zero — kbd_scan_and_dispatch not running")
        ok = False
    else:
        print("  OK: kbd_scan ran and populated tester_kbd_prev")
        non_idle = [(i, b) for i, b in enumerate(kbd_prev) if (b | 0x80) != 0xFF]
        if non_idle:
            print(f"  NOTE: some columns are non-idle even with no key pressed: {non_idle}")
            print(f"        kbd-scan needs review (probably PIA settle timing or init quirk)")

    print()
    print("== Verdict ==")
    print("  PASS — milestone 2 boot/IRQ/scan verified." if ok else "  FAIL — see above.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
