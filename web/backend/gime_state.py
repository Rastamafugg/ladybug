"""Reads XRoar's GIME shadow + builds a VideoState snapshot.

The shape is dictated by what `MonitorSession.read_gime_state` returns
(M3 milestone): a dict with `registers` (keyed by hex name 'FF90' etc),
`pars` (task0/task1, 8 entries each), `palette` (16 entries, raw 6-bit),
plus `mmu_task`, `mmuen`, `mc3`, `ty`, `coco` flags.

WS-B v0 supports a single mode (320x192x16, CRES=10 HRES=111 VRES=00).
`decode_mode` extracts the bit fields per wiki/platform/gime.md L20-22;
unsupported modes still produce a populated `VideoMode` so the caller
can report the rejection reason.

The FB physical base is computed from $FF9D/$FF9E (bits Y18..Y3 of the
hardware video-pointer per gime.md L25-26). The CPU's MMU/PAR state is
irrelevant to this read — the video controller scans physical RAM, and
so do we via the monitor's `space="physical"` path.
"""
from __future__ import annotations
from dataclasses import dataclass

from . import palette as palette_mod
from .monitor_session import MonitorSession


# 320x192x16 — the only mode WS-B v0 renders. Matches WS-A tester ROM.
SUPPORTED_CRES = 0b10
SUPPORTED_HRES = 0b111
SUPPORTED_VRES = 0b00
SUPPORTED_WIDTH = 320
SUPPORTED_HEIGHT = 192
SUPPORTED_BPP = 4
SUPPORTED_BYTES_PER_ROW = 160


@dataclass(frozen=True)
class VideoMode:
    cres: int          # $FF99 b1-b0 — 00=2 / 01=4 / 10=16 colors / 11=reserved
    hres: int          # $FF99 b4-b2 — horizontal resolution code
    vres: int          # $FF99 b6-b5 — 00=192 / 01=200 / 11=225 lines
    bp:   bool         # $FF98 b7    — graphics (True) vs text (False)
    coco: bool         # $FF90 b7    — CoCo-1 legacy VDG path
    width: int         # decoded pixels per row
    height: int        # decoded lines per frame
    bpp: int           # decoded bits per pixel
    bytes_per_row: int # decoded bytes consumed per scan line


@dataclass(frozen=True)
class VideoState:
    mode: VideoMode
    palette_raw: list[int]                       # 16x 6-bit
    palette_rgb: list[tuple[int, int, int]]      # 16x (r,g,b) after RGB-monitor decode
    pars_exec: list[int]
    pars_task: list[int]
    mmu_task: int
    mmuen: bool
    fb_phys_base: int                            # absolute physical address
    source: str                                  # always "monitor.read_gime_state" today


def decode_mode(registers: dict) -> VideoMode:
    """Map the GIME shadow register values to a resolved VideoMode."""
    ff90 = registers.get("FF90", 0)
    ff98 = registers.get("FF98", 0)
    ff99 = registers.get("FF99", 0)

    coco = bool(ff90 & 0x80)
    bp = bool(ff98 & 0x80)
    cres = ff99 & 0x03
    hres = (ff99 >> 2) & 0x07
    vres = (ff99 >> 5) & 0x03

    if (bp and not coco
            and cres == SUPPORTED_CRES
            and hres == SUPPORTED_HRES
            and vres == SUPPORTED_VRES):
        return VideoMode(
            cres=cres, hres=hres, vres=vres, bp=bp, coco=coco,
            width=SUPPORTED_WIDTH,
            height=SUPPORTED_HEIGHT,
            bpp=SUPPORTED_BPP,
            bytes_per_row=SUPPORTED_BYTES_PER_ROW,
        )

    # Unsupported: emit a mode descriptor with zeros for the decoded
    # dimensions so the renderer can produce a placeholder with detail.
    return VideoMode(
        cres=cres, hres=hres, vres=vres, bp=bp, coco=coco,
        width=0, height=0, bpp=0, bytes_per_row=0,
    )


def is_supported(mode: VideoMode) -> bool:
    return mode.width > 0


def fb_phys_base(registers: dict) -> int:
    """Compute the GIME's hardware FB pointer from $FF9D + $FF9E.

    Per gime.md: FF9D supplies Y18..Y11, FF9E supplies Y10..Y3 (8-byte
    aligned). Result is a 19-bit physical address.
    """
    ff9d = registers.get("FF9D", 0)
    ff9e = registers.get("FF9E", 0)
    return ((ff9d & 0xFF) << 11) | ((ff9e & 0xFF) << 3)


async def snapshot(session: MonitorSession) -> VideoState:
    """Read GIME shadow state once and assemble a VideoState."""
    raw = await session.read_gime_state()
    regs = raw.get("registers", {})
    palette_raw = list(raw.get("palette", []))
    pars = raw.get("pars", {}) or {}

    mode = decode_mode(regs)
    palette_rgb = [palette_mod.decode_rgb_monitor(c) for c in palette_raw]

    return VideoState(
        mode=mode,
        palette_raw=palette_raw,
        palette_rgb=palette_rgb,
        pars_exec=list(pars.get("task0", [])),
        pars_task=list(pars.get("task1", [])),
        mmu_task=int(raw.get("mmu_task", 0)),
        mmuen=bool(raw.get("mmuen", False)),
        fb_phys_base=fb_phys_base(regs),
        source="monitor.read_gime_state",
    )
