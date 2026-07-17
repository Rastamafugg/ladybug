"""End-to-end regression probe for the Phase 2.4 Ladybug screen.

Verifies that the cartridge reaches ``phase24_halt`` with the expected MMU
map, palette, liveness sentinels, and exact 320x192 framebuffer contents.
Run inside WSL from the repository root:

    python3 web/scripts/probe_ladybug_screen.py
"""
from __future__ import annotations

import asyncio
import os
import re
import socket
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from web.backend.monitor_session import MonitorSession  # noqa: E402


XROAR_BIN = os.environ.get(
    "XROAR_BIN",
    str(REPO_ROOT / "docs" / "reference" / "xroar" / "build" / "xroar-monitor"),
)
ROM = REPO_ROOT / "build" / "ladybug.rom"
MAP = REPO_ROOT / "build" / "ladybug.map"

WIDTH_BYTES = 160
HEIGHT = 192
EXPECTED_PARS = [0x38, 0x30, 0x31, 0x32, 0x33, 0x34, 0x3E, 0x3F]
EXPECTED_PALETTE = [
    0x00, 0x30, 0x08, 0x3F, 0x20, 0x10, 0x18, 0x28,
    0x38, 0x04, 0x02, 0x01, 0x06, 0x03, 0x05, 0x07,
]
TILE = bytes.fromhex(
    "33 33 31 33 33 31 11 33 33 11 11 10 33 11 11 12 "
    "33 11 11 12 31 11 11 22 31 11 31 20 31 13 11 22"
)


def pick_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def map_symbol(name: str) -> int:
    match = re.search(
        rf"^Symbol: {re.escape(name)} .* = ([0-9A-Fa-f]+)$",
        MAP.read_text(),
        re.MULTILINE,
    )
    if match is None:
        raise RuntimeError(f"symbol not found in {MAP}: {name}")
    return int(match.group(1), 16)


def expected_framebuffer() -> bytes:
    expected = bytearray(WIDTH_BYTES * HEIGHT)
    for row in range(8):
        source = TILE[row * 4:(row + 1) * 4]
        for column in (0, 76, 156):
            start = row * WIDTH_BYTES + column
            expected[start:start + 4] = source
    return bytes(expected)


async def run() -> int:
    if not ROM.exists() or not MAP.exists():
        print("FAIL: build/ladybug.rom and build/ladybug.map are required")
        return 2

    port = pick_port()
    proc = await asyncio.create_subprocess_exec(
        XROAR_BIN,
        "-machine", "coco3", "-ram", "512",
        "-cart", "ladybug", "-cart-type", "rom",
        "-cart-rom", str(ROM), "-cart-autorun",
        "-tv-input", "rgb",
        "-monitor", f"127.0.0.1:{port}",
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        await asyncio.sleep(3.0)
        monitor = MonitorSession(port)
        await monitor.attach()
        await monitor.interrupt()
        try:
            regs = await monitor.read_registers()
            sentinels = await monitor.read_memory(0x0FFE, 2)
            gime = await monitor.read_gime_state()
            framebuffer = await monitor.read_memory(
                0x60000, WIDTH_BYTES * HEIGHT, space="physical"
            )
        finally:
            await monitor.detach()
    finally:
        if proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                proc.kill()

    errors: list[str] = []
    expected_pc = map_symbol("phase24_halt")
    if regs.get("pc") != expected_pc:
        errors.append(f"PC=${regs.get('pc', 0):04X}, expected ${expected_pc:04X}")
    if sentinels != bytes.fromhex("55 aa"):
        errors.append(f"sentinels={sentinels.hex()}, expected 55aa")

    gime_regs = gime.get("registers", {})
    if gime_regs.get("FF98") != 0x80 or gime_regs.get("FF99") != 0x1E:
        errors.append(
            f"video mode FF98/FF99={gime_regs.get('FF98')!r}/{gime_regs.get('FF99')!r}"
        )
    if not gime.get("mmuen") or gime.get("ty"):
        errors.append(f"expected MMU enabled with TY=0, got {gime.get('mmuen')=}, {gime.get('ty')=}")
    if gime.get("pars", {}).get("task0") != EXPECTED_PARS:
        errors.append(f"PARs={gime.get('pars', {}).get('task0')}, expected {EXPECTED_PARS}")
    if gime.get("palette") != EXPECTED_PALETTE:
        errors.append(f"palette={gime.get('palette')}, expected {EXPECTED_PALETTE}")
    if framebuffer != expected_framebuffer():
        errors.append("physical framebuffer does not match three-tile reference")

    if errors:
        print("FAIL: Ladybug screen regression")
        for error in errors:
            print(f"  {error}")
        return 1

    print(
        f"PASS: PC=${expected_pc:04X}, sentinels=55aa, MMU/PAR/palette valid, "
        "three-tile framebuffer exact"
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
