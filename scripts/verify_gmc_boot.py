#!/usr/bin/env python3
"""Run a bounded headless XRoar trace and verify the GMC loader handoff."""

from __future__ import annotations

import argparse
import re
import subprocess
import tempfile
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--xroar", default="/usr/local/bin/xroar")
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--map", type=Path, required=True)
    args = parser.parse_args()

    map_text = args.map.read_text(encoding="utf-8")
    match = re.search(r"^Symbol: mainloop .* = ([0-9A-Fa-f]+)$", map_text, re.M)
    if not match:
        raise SystemExit("gmc proof: mainloop missing from map")
    mainloop = match.group(1).lower()
    rom = args.rom.read_bytes()
    boot = rom[:0x4000]
    main_source = (Path(__file__).resolve().parents[1] / "src/main.s").read_text(
        encoding="utf-8"
    )
    loader_source = (Path(__file__).resolve().parents[1] / "src/gmc_bootstrap.s").read_text(
        encoding="utf-8"
    )
    loader_include = (
        Path(__file__).resolve().parents[1] / "build/ladybug-sparse-loader.inc"
    ).read_text(encoding="ascii")
    segment_match = re.search(
        r"^SPARSE_COPY_SEGMENT_COUNT equ ([0-9]+)$", loader_include, re.MULTILINE
    )
    if not segment_match:
        raise SystemExit("gmc proof: generated sparse segment count is missing")
    expected_sparse_segments = int(segment_match.group(1))
    enemy_map = (
        Path(__file__).resolve().parents[1] / "build/ladybug-enemy-runtime.map"
    ).read_text(encoding="utf-8")
    damage_symbols = {}
    for name in (
        "actor_closure_restore",
        "actor_closure_draw",
        "framebuffer_queue_damage",
        "framebuffer_project_damage",
        "sparse_blit_fb",
        "sparse_blit_stage",
    ):
        symbol = re.search(
            rf"^Symbol: {name} .* = ([0-9A-Fa-f]+)$", enemy_map, re.MULTILINE
        )
        if not symbol:
            raise SystemExit(f"gmc proof: {name} missing from enemy map")
        damage_symbols[name] = symbol.group(1).lower()
    if "sta     SAM_FAST" not in main_source or "SAM_FAST   equ  $FFD9" not in main_source:
        raise SystemExit("gmc proof: resident fast-clock selection missing")
    if "sta     SAM_FAST" not in loader_source or "SAM_FAST    equ $FFD9" not in loader_source:
        raise SystemExit("gmc proof: bootstrap fast-clock selection missing")
    resident_copy = loader_source[loader_source.index("; Bank 1 contains"):
                                  loader_source.index("copy_resident\n")]
    if "lda     #$3E\n        sta     PAR_EXEC+5" not in resident_copy:
        raise SystemExit("gmc proof: resident copy does not restore PAR5 to physical page $3E")
    if bytes((0xB7, 0xFF, 0xD9)) not in boot:
        raise SystemExit("gmc proof: assembled bootstrap fast-clock write missing")
    if bytes((0xB7, 0xFF, 0xD9)) not in rom[0x4000:0x8000]:
        raise SystemExit("gmc proof: assembled resident fast-clock write missing")
    jump = boot.find(bytes((0x7E, 0x03, 0x00)))
    if jump < 0:
        raise SystemExit("gmc proof: relocated-loader jump missing")
    loader_start = jump + 3

    def relocated_pc(opcode: bytes, occurrence: int = 0) -> str:
        positions = []
        cursor = loader_start
        while True:
            cursor = boot.find(opcode, cursor)
            if cursor < 0:
                break
            positions.append(cursor)
            cursor += 1
        if occurrence >= len(positions):
            raise SystemExit(f"gmc proof: loader opcode {opcode.hex()} missing")
        return f"{0x0300 + positions[occurrence] - loader_start:04x}"

    bank_writes = []
    cursor = loader_start
    while True:
        cursor = boot.find(bytes((0xB7, 0xFF, 0x50)), cursor)
        if cursor < 0:
            break
        bank_writes.append(f"{0x0300 + cursor - loader_start:04x}")
        cursor += 1
    if len(bank_writes) < 5:
        raise SystemExit("gmc proof: expected five loader bank writes")
    bank2_signature = relocated_pc(bytes((0xFC, 0xC0, 0x10)), 0)
    bank3_signature = relocated_pc(bytes((0xFC, 0xC0, 0x10)), 1)
    allram = relocated_pc(bytes((0xB7, 0xFF, 0xDF)))
    frame_entry = rom[0xC818:0xC81B]
    if len(frame_entry) != 3 or frame_entry[0] != 0x7E:
        raise SystemExit("gmc proof: frame renderer ABI jump missing")
    frame_target = f"{int.from_bytes(frame_entry[1:], 'big'):04x}"
    ownership_entry = rom[0xC81B:0xC81E]
    if len(ownership_entry) != 3 or ownership_entry[0] != 0x7E:
        raise SystemExit("gmc proof: framebuffer ownership-init ABI jump missing")
    ownership_target = f"{int.from_bytes(ownership_entry[1:], 'big'):04x}"
    commit_entry = rom[0xC81E:0xC821]
    if len(commit_entry) != 3 or commit_entry[0] != 0x7E:
        raise SystemExit("gmc proof: framebuffer Vbord-commit ABI jump missing")
    commit_target = f"{int.from_bytes(commit_entry[1:], 'big'):04x}"

    command = [
        "timeout", "4", args.xroar,
        "-ui", "null", "-ao", "null",
        "-machine", "coco3", "-ram", "512",
        "-cart-type", "gmc", "-cart-rom", str(args.rom),
        "-cart-autorun", "-no-ratelimit", "-trace",
    ]
    with tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as trace:
        subprocess.run(command, stdout=trace, stderr=subprocess.STDOUT, check=False)
        trace.seek(0)
        text = trace.read()

    sparse_bank_writes = re.findall(
        rf"^{bank_writes[3]}\| b7ff50 .* a=([0-9a-f]{{2}}) ",
        text,
        re.MULTILINE,
    )
    sparse_page_writes = re.findall(
        r"^[0-9a-f]{4}\| b7ffa5 .* a=(35|36|37|39) ",
        text,
        re.MULTILINE,
    )
    commit_writes = [
        int(value, 16)
        for pc, value in re.findall(
            r"^([0-9a-f]{4})\| b7ff9d .* a=([0-9a-f]{2}) ",
            text,
            re.MULTILINE,
        )
        if 0x0800 <= int(pc, 16) < 0x1800
    ]
    commit_alternates = (
        len(commit_writes) >= 4
        and set(commit_writes) == {0xB0, 0xC0}
        and all(a != b for a, b in zip(commit_writes, commit_writes[1:]))
    )
    required = {
        "bank 2 signature": f"{bank2_signature}| fcc010" in text and "a=b2 b=02" in text,
        "bank 3 signature": f"{bank3_signature}| fcc010" in text and "a=b3 b=03" in text,
        "bank-3 module selected": f"{bank_writes[2]}| b7ff50" in text,
        "generated sparse source segments selected": (
            len(sparse_bank_writes) == expected_sparse_segments and
            set(sparse_bank_writes) == {"02", "03"}
        ),
        "sparse destination pages selected": set(sparse_page_writes) == {"35", "36", "37", "39"},
        "runtime bank selected": f"{bank_writes[4]}| b7ff50" in text,
        "all-RAM handoff": f"{allram}| b7ffdf" in text,
        "bank-3 module payload": rom[0xC800:0xC80C] != bytes((0xA3,)) * 12,
        "bank-2 sparse payload": rom[0x8020:0x9E00] != bytes((0xA2,)) * 0x1DE0,
        "enemy module entered": "0800| 7e" in text,
        "frame renderer ABI entered": f"0818| {frame_entry.hex()}" in text,
        "central frame renderer entered": f"{frame_target}|" in text,
        "ownership init ABI entered": f"081b| {ownership_entry.hex()}" in text,
        "ownership init entered": f"{ownership_target}| 0f8f" in text,
        "Vbord commit ABI entered": f"081e| {commit_entry.hex()}" in text,
        "Vbord commit handler entered": f"{commit_target}|" in text,
        "Vbord display owners alternate": commit_alternates,
        "damage queue entered": f"{damage_symbols['framebuffer_queue_damage']}|" in text,
        "damage projection entered": f"{damage_symbols['framebuffer_project_damage']}|" in text,
        "actor closure restore entered": f"{damage_symbols['actor_closure_restore']}|" in text,
        "actor closure draw entered": f"{damage_symbols['actor_closure_draw']}|" in text,
        "sparse framebuffer decoder entered": f"{damage_symbols['sparse_blit_fb']}|" in text,
        "sparse stage decoder entered": f"{damage_symbols['sparse_blit_stage']}|" in text,
        "runtime main loop": text.count(f"{mainloop}| 13") >= 1,
    }
    failed = [name for name, passed in required.items() if not passed]
    if failed:
        raise SystemExit("gmc proof failed: " + ", ".join(failed))
    print("gmc proof: segmented sparse payload load, bank-3 module, bank-1 load, sparse runtime decoders, TY=1 handoff, A/B ownership init, actor closure, Vbord commit entry, and relocated main loop verified")


if __name__ == "__main__":
    main()
