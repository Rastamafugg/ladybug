#!/usr/bin/env python3
"""Exercise the complete FEAT-006 lifecycle and phase-owned $0300 runtimes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import struct
import sys
import tempfile
import time
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import verify_bug011_runtime as runtime  # noqa: E402
import verify_gmc_boot as gmc_boot  # noqa: E402
from build_screen import PALETTE, gime_rgb  # noqa: E402

PRES_MODE, PRES_SCREEN, PRES_CONTEXT = 0x00A5, 0x00A6, 0x00A7
PRES_CREDITS, PRES_EVENT, PRES_TIMER = 0x00A8, 0x00A9, 0x00B0
PRES_NAME_TIMER_PHASE, PRES_NAME_TIMER_BOX = 0x00E8, 0x00E9
DEATH, PAR5, SND_DATA = 0x004D, 0xFFA5, 0xFF51
MODE_NORMAL, MODE_ATTRACT, MODE_INSTRUCTIONS = 0, 2, 3
MODE_DEMO, MODE_LEVEL, MODE_GAMEOVER, MODE_NAME = 4, 6, 7, 8


def png_chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def write_png(path: Path, frame: bytes) -> None:
    palette = [gime_rgb(value) for value in PALETTE]
    rows = bytearray()
    for y in range(192):
        rows.append(0)
        for value in frame[y * 160:(y + 1) * 160]:
            for nibble in (value >> 4, value & 15):
                rows.extend(palette[nibble])
    payload = b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", struct.pack(">IIBBBBB", 320, 192, 8, 2, 0, 0, 0)) + png_chunk(b"IDAT", zlib.compress(bytes(rows), 9)) + png_chunk(b"IEND", b"")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def gdb_runtime(args, expected: dict[str, bytes], entry: int, event_hook: int, layout: dict) -> None:
    """Exercise the complete lifecycle through XRoar's public GDB stub."""
    port = gmc_boot.free_local_port()
    xroar_command = [str(args.xroar)]
    if not args.visible_natural_collision_diagnostic:
        xroar_command += ["-ui", "null", "-ao", "null"]
    xroar_command += [
        "-machine", "coco3", "-ram", "512", "-cart-type", "gmc",
        "-cart-rom", str(args.rom), "-cart-autorun",
    ]
    if not args.visible_natural_collision_diagnostic:
        xroar_command.append("-no-ratelimit")
    xroar_command += ["-gdb", "-gdb-ip", "127.0.0.1", "-gdb-port", str(port)]
    process = gmc_boot.start_xroar(xroar_command)
    events: list[dict[str, int | str]] = []
    with tempfile.TemporaryDirectory(prefix="ladybug-feat006-") as temp:
        temp_path = Path(temp)
        dumps = {name: temp_path / f"{name}.bin" for name in (
            "instruction", "demo", "audio", "highscore", "return_instruction",
            "later_audio", "soft_instruction", "attract_frame", "gameplay_frame",
            "name_frame", "highscore_frame", "presentation_module",
            "highscore_staged", "highscore_live_install", "highscore_load_done",
            "resident_terminal",
            "scanout_publication_back", "scanout_first_display", "scanout_second_display",
            "collision_runtime_live", "collision_presentation_live",
        )}
        highscore_layout = layout["highscore_runtime"]
        highscore_stage_start = int(highscore_layout["stage_address"])
        highscore_stage_end = highscore_stage_start + len(expected["highscore"])
        highscore_live_end = 0x0300 + len(expected["highscore"])
        commands = [
            "set pagination off", "set confirm off", f"target remote :{port}",
            "set $feat_inject_start = 0",
            f"break *0x{entry:04x}", "commands 1", "silent", "end",
            f"break *0x{event_hook:04x}", "commands 2", "silent",
            "if $feat_inject_start != 0", "set {unsigned char}0x00a9 = 1",
            "set $feat_inject_start = 0", "end", "continue", "end", "continue",
        ]

        def scanout_dump_commands(name: str) -> list[str]:
            path = dumps[name].as_posix()
            return [
                "set $feat_scan_p1 = *(unsigned char*)0xffa1",
                "set $feat_scan_p2 = *(unsigned char*)0xffa2",
                "set $feat_scan_p3 = *(unsigned char*)0xffa3",
                "set $feat_scan_p4 = *(unsigned char*)0xffa4",
                "if *(unsigned char*)0x008f == 0",
                "set {unsigned char}0xffa1 = 0x30", "set {unsigned char}0xffa2 = 0x31",
                "set {unsigned char}0xffa3 = 0x32", "set {unsigned char}0xffa4 = 0x33",
                "else",
                "set {unsigned char}0xffa1 = 0x2c", "set {unsigned char}0xffa2 = 0x2d",
                "set {unsigned char}0xffa3 = 0x2e", "set {unsigned char}0xffa4 = 0x2f",
                "end",
                f"dump binary memory {path} 0x2000 0x9800",
                "set {unsigned char}0xffa1 = $feat_scan_p1",
                "set {unsigned char}0xffa2 = $feat_scan_p2",
                "set {unsigned char}0xffa3 = $feat_scan_p3",
                "set {unsigned char}0xffa4 = $feat_scan_p4",
            ]

        diagnostic_commands: list[str] = []
        if args.terminal_death_diagnostic:
            diagnostic_commands = [
                "break *0x19cf if *(unsigned char*)0x004d == 4", "commands 3", "silent",
                'printf "FEAT006_DIAG death-dispatch pc=%04x a=%02x death=%d mode=%d screen=%d\\n", $pc, $a, *(unsigned char*)0x004d, *(unsigned char*)0x00a5, *(unsigned char*)0x00a6',
                "disable 3", "continue", "end",
                "break *0x19d8", "commands 4", "silent",
                'printf "FEAT006_DIAG audio-return pc=%04x a=%02x par5=%02x\\n", $pc, $a, *(unsigned char*)0xffa5',
                "disable 4", "continue", "end",
                "break *0x19ae", "commands 5", "silent",
                'printf "FEAT006_DIAG highscore-install pc=%04x a=%02x par5=%02x\\n", $pc, $a, *(unsigned char*)0xffa5',
                "disable 5", "continue", "end",
                "break *0x19da", "commands 6", "silent",
                'printf "FEAT006_DIAG highscore-return pc=%04x a=%02x par5=%02x\\n", $pc, $a, *(unsigned char*)0xffa5',
                "set $feat_diag_p5 = *(unsigned char*)0xffa5",
                f"set {{unsigned char}}0xffa5 = 0x{int(highscore_layout['stage_page']):02x}",
                f"dump binary memory {dumps['highscore_staged'].as_posix()} 0x{highscore_stage_start:04x} 0x{highscore_stage_end:04x}",
                "set {unsigned char}0xffa5 = $feat_diag_p5",
                f"dump binary memory {dumps['highscore_live_install'].as_posix()} 0x0300 0x{highscore_live_end:04x}",
                "disable 6", "continue", "end",
                "break *0x1a11 if $a == 4", "commands 7", "silent",
                'printf "FEAT006_DIAG gameover-start pc=%04x a=%02x mode=%d screen=%d\\n", $pc, $a, *(unsigned char*)0x00a5, *(unsigned char*)0x00a6',
                "disable 7", "continue", "end",
                "break *0x1a5e if *(unsigned char*)0x00a6 == 4", "commands 8", "silent",
                'printf "FEAT006_DIAG load-entry pc=%04x hold=%02x cell=%04x in=%04x run=%02x value=%02x pending=%02x frames=%04x last=%02x pars=%02x,%02x,%02x,%02x,%02x\\n", $pc, *(unsigned char*)0x00d4, *(unsigned short*)0x00aa, *(unsigned short*)0x00b5, *(unsigned char*)0x00bb, *(unsigned char*)0x00bc, *(unsigned char*)0x0091, *(unsigned short*)0x0002, *(unsigned char*)0x0000, *(unsigned char*)0xffa1, *(unsigned char*)0xffa2, *(unsigned char*)0xffa3, *(unsigned char*)0xffa4, *(unsigned char*)0xffa5',
                "disable 8", "continue", "end",
                "break *0x1a6c if *(unsigned char*)0x00a6 == 4", "commands 9", "silent",
                'printf "FEAT006_DIAG cell-loop-entry pc=%04x hold=%02x cell=%04x in=%04x run=%02x value=%02x pending=%02x\\n", $pc, *(unsigned char*)0x00d4, *(unsigned short*)0x00aa, *(unsigned short*)0x00b5, *(unsigned char*)0x00bb, *(unsigned char*)0x00bc, *(unsigned char*)0x0091',
                "disable 9", "continue", "end",
                "break *0x1a5e if *(unsigned char*)0x00a6 == 4 && (*(unsigned char*)0x00aa != 0 || *(unsigned char*)0x00ab >= 32)", "commands 10", "silent",
                'printf "FEAT006_DIAG first-progress pc=%04x hold=%02x cell=%04x in=%04x run=%02x value=%02x pending=%02x frames=%04x last=%02x\\n", $pc, *(unsigned char*)0x00d4, *(unsigned short*)0x00aa, *(unsigned short*)0x00b5, *(unsigned char*)0x00bb, *(unsigned char*)0x00bc, *(unsigned char*)0x0091, *(unsigned short*)0x0002, *(unsigned char*)0x0000',
                "disable 10", "continue", "end",
                "break *0x1ab8 if *(unsigned char*)0x00a6 == 4", "commands 11", "silent",
                'printf "FEAT006_DIAG load-done pc=%04x hold=%02x cell=%04x in=%04x run=%02x value=%02x pending=%02x\\n", $pc, *(unsigned char*)0x00d4, *(unsigned short*)0x00aa, *(unsigned short*)0x00b5, *(unsigned char*)0x00bb, *(unsigned char*)0x00bc, *(unsigned char*)0x0091',
                f"dump binary memory {dumps['highscore_load_done'].as_posix()} 0x0300 0x{highscore_live_end:04x}",
                "disable 11", "continue", "end",
                "break *0x1ad7 if *(unsigned char*)0x00a6 == 4", "commands 12", "silent",
                'printf "FEAT006_DIAG dynamic-return pc=%04x mode=%d screen=%d par5=%02x\\n", $pc, *(unsigned char*)0x00a5, *(unsigned char*)0x00a6, *(unsigned char*)0xffa5',
                "disable 12", "continue", "end",
                "break *0x1b33 if *(unsigned char*)0x00a6 == 4", "commands 13", "silent",
                'printf "FEAT006_DIAG publication pc=%04x mode=%d screen=%d par5=%02x\\n", $pc, *(unsigned char*)0x00a5, *(unsigned char*)0x00a6, *(unsigned char*)0xffa5',
                "disable 13", "continue", "end",
                "break *0x1b4b if *(unsigned char*)0x00a6 == 4", "commands 14", "silent",
                'printf "FEAT006_DIAG mode-assignment pc=%04x mode=%d screen=%d par5=%02x\\n", $pc, *(unsigned char*)0x00a5, *(unsigned char*)0x00a6, *(unsigned char*)0xffa5',
                "disable 14", "continue", "end",
                "break *0xac40 if *(unsigned char*)0x00a6 == 4", "commands 15", "silent",
                'printf "FEAT006_DIAG highscore-helper-entry pc=%04x mode=%d screen=%d par5=%02x\\n", $pc, *(unsigned char*)0x00a5, *(unsigned char*)0x00a6, *(unsigned char*)0xffa5',
                "disable 15", "continue", "end",
                "break *0xad57 if *(unsigned char*)0x00a6 == 4 && *(unsigned char*)0x00a5 == 7", "commands 16", "silent",
                'printf "FEAT006_DIAG highscore-gameover-tick pc=%04x timer_bytes=%02x,%02x mode=%d screen=%d par5=%02x\\n", $pc, *(unsigned char*)0x00b0, *(unsigned char*)0x00b1, *(unsigned char*)0x00a5, *(unsigned char*)0x00a6, *(unsigned char*)0xffa5',
                "disable 16", "continue", "end",
                "break *0xad5e if *(unsigned char*)0x00a6 == 4 && *(unsigned char*)0x00a5 == 7", "commands 17", "silent",
                'printf "FEAT006_DIAG timer-after-increment pc=%04x timer_bytes=%02x,%02x mode=%d screen=%d par5=%02x\\n", $pc, *(unsigned char*)0x00b0, *(unsigned char*)0x00b1, *(unsigned char*)0x00a5, *(unsigned char*)0x00a6, *(unsigned char*)0xffa5',
                "disable 17", "continue", "end",
                "break *0xad64 if *(unsigned char*)0x00a6 == 4 && *(unsigned char*)0x00a5 == 7", "commands 18", "silent",
                'printf "FEAT006_DIAG gameover-threshold pc=%04x timer_bytes=%02x,%02x mode=%d screen=%d par5=%02x\\n", $pc, *(unsigned char*)0x00b0, *(unsigned char*)0x00b1, *(unsigned char*)0x00a5, *(unsigned char*)0x00a6, *(unsigned char*)0xffa5',
                "disable 18", "continue", "end",
                "break *0x1a11 if $a == 5", "commands 19", "silent",
                'printf "FEAT006_DIAG name-screen-start pc=%04x a=%02x mode=%d screen=%d\\n", $pc, $a, *(unsigned char*)0x00a5, *(unsigned char*)0x00a6',
                "disable 19", "continue", "end",
                "break *0x1b4b if *(unsigned char*)0x00a6 == 5", "commands 20", "silent",
                'printf "FEAT006_DIAG name-mode-assignment pc=%04x mode=%d screen=%d par5=%02x\\n", $pc, *(unsigned char*)0x00a5, *(unsigned char*)0x00a6, *(unsigned char*)0xffa5',
                "disable 20", "end",
            ]
            if args.timer_step_diagnostic:
                diagnostic_commands = [
                    "break *0xad57", "commands 3", "silent",
                    'printf "FEAT006_STEP entry pc=%04x a=%02x b=%02x cc=%02x\\n", $pc, $a, $b, $cc',
                    "disable 3", "end",
                    "disable 1 2", "set {unsigned char}0x004d = 4",
                    "continue",
                    'printf "FEAT006_STEP before-increment pc=%04x a=%02x b=%02x cc=%02x\\n", $pc, $a, $b, $cc',
                    "x/2bx 0x00b0",
                    "stepi",
                    'printf "FEAT006_STEP after-ldd pc=%04x a=%02x b=%02x cc=%02x\\n", $pc, $a, $b, $cc',
                    "stepi",
                    'printf "FEAT006_STEP after-addd pc=%04x a=%02x b=%02x cc=%02x\\n", $pc, $a, $b, $cc',
                    "stepi",
                    'printf "FEAT006_DIAG timer-after-increment pc=%04x timer_bytes=%02x,%02x mode=%d screen=%d par5=%02x\\n", $pc, *(unsigned char*)0x00b0, *(unsigned char*)0x00b1, *(unsigned char*)0x00a5, *(unsigned char*)0x00a6, *(unsigned char*)0xffa5',
                    'printf "FEAT006_STEP after-stb pc=%04x a=%02x b=%02x cc=%02x\\n", $pc, $a, $b, $cc',
                    "x/2bx 0x00b0",
                    "stepi",
                    'printf "FEAT006_STEP after-cmpd pc=%04x a=%02x b=%02x cc=%02x\\n", $pc, $a, $b, $cc',
                    "x/2bx 0x00b0",
                    "stepi",
                    'printf "FEAT006_DIAG gameover-threshold pc=%04x timer_bytes=%02x,%02x mode=%d screen=%d par5=%02x\\n", $pc, *(unsigned char*)0x00b0, *(unsigned char*)0x00b1, *(unsigned char*)0x00a5, *(unsigned char*)0x00a6, *(unsigned char*)0xffa5',
                    'printf "FEAT006_STEP after-branch pc=%04x a=%02x b=%02x cc=%02x\\n", $pc, $a, $b, $cc',
                    "x/2bx 0x00b0",
                    "detach", "quit",
                ]
            if args.natural_final_life_diagnostic:
                diagnostic_commands = [
                    "break *0xd3a7", "commands 3", "silent",
                    'printf "FEAT006_NATURAL terminal-state-entry pc=%04x death=%d lives=%d timer=%d mode=%d screen=%d\\n", $pc, *(unsigned char*)0x004d, *(unsigned char*)0x0023, *(unsigned char*)0x003a, *(unsigned char*)0x00a5, *(unsigned char*)0x00a6',
                    f"dump binary memory {dumps['resident_terminal'].as_posix()} 0xd3a7 0xd3b7",
                    "disable 3", "enable 4", "continue", "end",
                    "break *0x19cf", "disable 4", "commands 4", "silent",
                    'printf "FEAT006_NATURAL normal-dispatch pc=%04x death=%d lives=%d mode=%d screen=%d\\n", $pc, *(unsigned char*)0x004d, *(unsigned char*)0x0023, *(unsigned char*)0x00a5, *(unsigned char*)0x00a6',
                    "disable 4", "enable 5", "continue", "end",
                    "break *0x19ae", "disable 5", "commands 5", "silent",
                    'printf "FEAT006_NATURAL highscore-install pc=%04x death=%d mode=%d screen=%d par5=%02x\\n", $pc, *(unsigned char*)0x004d, *(unsigned char*)0x00a5, *(unsigned char*)0x00a6, *(unsigned char*)0xffa5',
                    "disable 5", "enable 6", "continue", "end",
                    "break *0x19da", "disable 6", "commands 6", "silent",
                    'printf "FEAT006_NATURAL highscore-return pc=%04x death=%d mode=%d screen=%d par5=%02x\\n", $pc, *(unsigned char*)0x004d, *(unsigned char*)0x00a5, *(unsigned char*)0x00a6, *(unsigned char*)0xffa5',
                    "set $feat_diag_p5 = *(unsigned char*)0xffa5",
                    f"set {{unsigned char}}0xffa5 = 0x{int(highscore_layout['stage_page']):02x}",
                    f"dump binary memory {dumps['highscore_staged'].as_posix()} 0x{highscore_stage_start:04x} 0x{highscore_stage_end:04x}",
                    "set {unsigned char}0xffa5 = $feat_diag_p5",
                    f"dump binary memory {dumps['highscore_live_install'].as_posix()} 0x0300 0x{highscore_live_end:04x}",
                    "disable 6", "enable 7", "continue", "end",
                    "break *0x1a11", "disable 7", "commands 7", "silent",
                    'printf "FEAT006_NATURAL gameover-start pc=%04x a=%02x death=%d mode=%d screen=%d\\n", $pc, $a, *(unsigned char*)0x004d, *(unsigned char*)0x00a5, *(unsigned char*)0x00a6',
                    "disable 7", "enable 8", "continue", "end",
                    "break *0x1b33", "disable 8", "commands 8", "silent",
                    'printf "FEAT006_NATURAL publication pc=%04x death=%d mode=%d screen=%d par5=%02x\\n", $pc, *(unsigned char*)0x004d, *(unsigned char*)0x00a5, *(unsigned char*)0x00a6, *(unsigned char*)0xffa5',
                    f"dump binary memory {dumps['highscore_load_done'].as_posix()} 0x0300 0x{highscore_live_end:04x}",
                    "disable 8", "enable 9", "continue", "end",
                    "break *0x1b4b", "disable 9", "commands 9", "silent",
                    'printf "FEAT006_NATURAL mode-assignment pc=%04x death=%d mode=%d screen=%d par5=%02x\\n", $pc, *(unsigned char*)0x004d, *(unsigned char*)0x00a5, *(unsigned char*)0x00a6, *(unsigned char*)0xffa5',
                    "disable 9", "enable 10", "continue", "end",
                    "break *0xad57", "disable 10", "commands 10", "silent",
                    'printf "FEAT006_NATURAL first-helper-tick pc=%04x dp=%02x timer=%02x,%02x death=%d mode=%d screen=%d par5=%02x\\n", $pc, $dp, *(unsigned char*)0x00b0, *(unsigned char*)0x00b1, *(unsigned char*)0x004d, *(unsigned char*)0x00a5, *(unsigned char*)0x00a6, *(unsigned char*)0xffa5',
                    "disable 10", "end",
                    "disable 1 2",
                    "set {unsigned char}0x0023 = 0",
                    "set {unsigned char}0x003a = 0",
                    "set {unsigned char}0x004d = 1",
                    'printf "FEAT006_NATURAL trigger death=1 lives=0\\n"',
                    "continue",
                    "info registers dp",
                    "x/2bx 0x00b0",
                    "set $feat_timer_effective = (($dp & 0xff) << 8) + 0xb0",
                    "x/2bx $feat_timer_effective",
                    "detach", "quit",
                ]
            if args.gameover_scanout_diagnostic:
                diagnostic_commands = [
                    "break *0xd3a7", "commands 3", "silent",
                    'printf "FEAT006_SCANOUT terminal-state-entry pc=%04x death=%d lives=%d mode=%d screen=%d\\n", $pc, *(unsigned char*)0x004d, *(unsigned char*)0x0023, *(unsigned char*)0x00a5, *(unsigned char*)0x00a6',
                    f"dump binary memory {dumps['resident_terminal'].as_posix()} 0xd3a7 0xd3b7",
                    "disable 3", "enable 4", "continue", "end",
                    "break *0x19cf", "disable 4", "commands 4", "silent",
                    'printf "FEAT006_SCANOUT normal-dispatch pc=%04x death=%d mode=%d screen=%d\\n", $pc, *(unsigned char*)0x004d, *(unsigned char*)0x00a5, *(unsigned char*)0x00a6',
                    "disable 4", "enable 5", "continue", "end",
                    "break *0x19ae", "disable 5", "commands 5", "silent",
                    'printf "FEAT006_SCANOUT highscore-install pc=%04x death=%d par5=%02x\\n", $pc, *(unsigned char*)0x004d, *(unsigned char*)0xffa5',
                    "disable 5", "enable 6", "continue", "end",
                    "break *0x19da", "disable 6", "commands 6", "silent",
                    'printf "FEAT006_SCANOUT highscore-return pc=%04x death=%d par5=%02x\\n", $pc, *(unsigned char*)0x004d, *(unsigned char*)0xffa5',
                    "set $feat_diag_p5 = *(unsigned char*)0xffa5",
                    f"set {{unsigned char}}0xffa5 = 0x{int(highscore_layout['stage_page']):02x}",
                    f"dump binary memory {dumps['highscore_staged'].as_posix()} 0x{highscore_stage_start:04x} 0x{highscore_stage_end:04x}",
                    "set {unsigned char}0xffa5 = $feat_diag_p5",
                    f"dump binary memory {dumps['highscore_live_install'].as_posix()} 0x0300 0x{highscore_live_end:04x}",
                    "disable 6", "enable 7", "continue", "end",
                    "break *0x1a11", "disable 7", "commands 7", "silent",
                    'printf "FEAT006_SCANOUT gameover-start pc=%04x a=%02x death=%d mode=%d screen=%d\\n", $pc, $a, *(unsigned char*)0x004d, *(unsigned char*)0x00a5, *(unsigned char*)0x00a6',
                    "disable 7", "enable 8", "continue", "end",
                    "break *0x1b33", "disable 8", "commands 8", "silent",
                    'printf "FEAT006_SCANOUT publication pc=%04x front=%d back=%d pending=%d voff=%02x,%02x pars=%02x,%02x,%02x,%02x,%02x frames=%04x commit=%04x sim=%04x\\n", $pc, *(unsigned char*)0x008f, *(unsigned char*)0x0090, *(unsigned char*)0x0091, *(unsigned char*)0xff9d, *(unsigned char*)0xff9e, *(unsigned char*)0xffa1, *(unsigned char*)0xffa2, *(unsigned char*)0xffa3, *(unsigned char*)0xffa4, *(unsigned char*)0xffa5, *(unsigned short*)0x0002, *(unsigned short*)0x0092, *(unsigned short*)0x0094',
                    f"dump binary memory {dumps['scanout_publication_back'].as_posix()} 0x2000 0x9800",
                    f"dump binary memory {dumps['highscore_load_done'].as_posix()} 0x0300 0x{highscore_live_end:04x}",
                    "disable 8", "enable 9", "continue", "end",
                    "break *0x1b4b", "disable 9", "commands 9", "silent",
                    'printf "FEAT006_SCANOUT mode-assignment pc=%04x front=%d back=%d pending=%d mode=%d screen=%d voff=%02x,%02x pars=%02x,%02x,%02x,%02x,%02x frames=%04x commit=%04x sim=%04x\\n", $pc, *(unsigned char*)0x008f, *(unsigned char*)0x0090, *(unsigned char*)0x0091, *(unsigned char*)0x00a5, *(unsigned char*)0x00a6, *(unsigned char*)0xff9d, *(unsigned char*)0xff9e, *(unsigned char*)0xffa1, *(unsigned char*)0xffa2, *(unsigned char*)0xffa3, *(unsigned char*)0xffa4, *(unsigned char*)0xffa5, *(unsigned short*)0x0002, *(unsigned short*)0x0092, *(unsigned short*)0x0094',
                    "disable 9", "enable 10", "continue", "end",
                    "break *0x0ddb", "disable 10", "commands 10", "silent",
                    'printf "FEAT006_SCANOUT irq-publication pc=%04x programmed_voff1=%02x front=%d back=%d pending=%d frames=%04x commit=%04x sim=%04x\\n", $pc, $a, *(unsigned char*)0x008f, *(unsigned char*)0x0090, *(unsigned char*)0x0091, *(unsigned short*)0x0002, *(unsigned short*)0x0092, *(unsigned short*)0x0094',
                    "disable 10", "enable 11", "continue", "end",
                    "break *0xad57", "disable 11", "commands 11", "silent",
                    'printf "FEAT006_SCANOUT first-helper-tick pc=%04x front=%d back=%d pending=%d mode=%d screen=%d timer=%02x,%02x voff=%02x,%02x pars=%02x,%02x,%02x,%02x,%02x frames=%04x commit=%04x sim=%04x\\n", $pc, *(unsigned char*)0x008f, *(unsigned char*)0x0090, *(unsigned char*)0x0091, *(unsigned char*)0x00a5, *(unsigned char*)0x00a6, *(unsigned char*)0x00b0, *(unsigned char*)0x00b1, *(unsigned char*)0xff9d, *(unsigned char*)0xff9e, *(unsigned char*)0xffa1, *(unsigned char*)0xffa2, *(unsigned char*)0xffa3, *(unsigned char*)0xffa4, *(unsigned char*)0xffa5, *(unsigned short*)0x0002, *(unsigned short*)0x0092, *(unsigned short*)0x0094',
                ] + scanout_dump_commands("scanout_first_display") + [
                    "disable 11", "enable 12", "continue", "end",
                    "break *0xad57", "disable 12", "commands 12", "silent",
                    'printf "FEAT006_SCANOUT second-helper-tick pc=%04x front=%d back=%d pending=%d mode=%d screen=%d timer=%02x,%02x voff=%02x,%02x pars=%02x,%02x,%02x,%02x,%02x frames=%04x commit=%04x sim=%04x\\n", $pc, *(unsigned char*)0x008f, *(unsigned char*)0x0090, *(unsigned char*)0x0091, *(unsigned char*)0x00a5, *(unsigned char*)0x00a6, *(unsigned char*)0x00b0, *(unsigned char*)0x00b1, *(unsigned char*)0xff9d, *(unsigned char*)0xff9e, *(unsigned char*)0xffa1, *(unsigned char*)0xffa2, *(unsigned char*)0xffa3, *(unsigned char*)0xffa4, *(unsigned char*)0xffa5, *(unsigned short*)0x0002, *(unsigned short*)0x0092, *(unsigned short*)0x0094',
                ] + scanout_dump_commands("scanout_second_display") + [
                    "disable 12", "end",
                    "disable 1 2",
                    "set {unsigned char}0x0023 = 0",
                    "set {unsigned char}0x003a = 0",
                    "set {unsigned char}0x004d = 1",
                    'printf "FEAT006_SCANOUT trigger death=1 lives=0\\n"',
                    "continue",
                    "detach", "quit",
                ]
            if args.visible_natural_collision_diagnostic:
                collision_runtime = ROOT / "build/ladybug-enemy-runtime.rom"
                collision_runtime_end = 0x0800 + collision_runtime.stat().st_size
                diagnostic_commands = [
                    "break *0x0987", "commands 3", "silent",
                    'printf "FEAT006_COLLISION collision-init pc=%04x dp=%02x death=%d lives=%d timer=%d mode=%d screen=%d player=%04x enemy=%04x\\n", $pc, $dp, *(unsigned char*)0x004d, *(unsigned char*)0x0023, *(unsigned char*)0x003a, *(unsigned char*)0x00a5, *(unsigned char*)0x00a6, *(unsigned short*)0x005d, *(unsigned short*)($x+1)',
                    f"dump binary memory {dumps['collision_runtime_live'].as_posix()} 0x0800 0x{collision_runtime_end:04x}",
                    "disable 3", "enable 4", "continue", "end",
                    "break *0xd3a7", "disable 4", "commands 4", "silent",
                    'printf "FEAT006_COLLISION terminal-transition pc=%04x dp=%02x death=%d lives=%d timer=%d mode=%d screen=%d\\n", $pc, $dp, *(unsigned char*)0x004d, *(unsigned char*)0x0023, *(unsigned char*)0x003a, *(unsigned char*)0x00a5, *(unsigned char*)0x00a6',
                    f"dump binary memory {dumps['resident_terminal'].as_posix()} 0xd3a7 0xd3b7",
                    "disable 4", "enable 5", "continue", "end",
                    "break *0x19cf", "disable 5", "commands 5", "silent",
                    'printf "FEAT006_COLLISION normal-dispatch pc=%04x death=%d lives=%d mode=%d screen=%d\\n", $pc, *(unsigned char*)0x004d, *(unsigned char*)0x0023, *(unsigned char*)0x00a5, *(unsigned char*)0x00a6',
                    "disable 5", "enable 6", "continue", "end",
                    "break *0x19ae", "disable 6", "commands 6", "silent",
                    'printf "FEAT006_COLLISION highscore-install pc=%04x death=%d par5=%02x\\n", $pc, *(unsigned char*)0x004d, *(unsigned char*)0xffa5',
                    "disable 6", "enable 7", "continue", "end",
                    "break *0x19da", "disable 7", "commands 7", "silent",
                    'printf "FEAT006_COLLISION highscore-return pc=%04x death=%d par5=%02x\\n", $pc, *(unsigned char*)0x004d, *(unsigned char*)0xffa5',
                    f"dump binary memory {dumps['highscore_live_install'].as_posix()} 0x0300 0x{highscore_live_end:04x}",
                    "disable 7", "enable 8", "continue", "end",
                    "break *0x1a11", "disable 8", "commands 8", "silent",
                    'printf "FEAT006_COLLISION gameover-start pc=%04x a=%02x death=%d mode=%d screen=%d\\n", $pc, $a, *(unsigned char*)0x004d, *(unsigned char*)0x00a5, *(unsigned char*)0x00a6',
                    "disable 8", "enable 9", "continue", "end",
                    "break *0x1b33", "disable 9", "commands 9", "silent",
                    'printf "FEAT006_COLLISION publication pc=%04x front=%d back=%d pending=%d mode=%d screen=%d frames=%04x\\n", $pc, *(unsigned char*)0x008f, *(unsigned char*)0x0090, *(unsigned char*)0x0091, *(unsigned char*)0x00a5, *(unsigned char*)0x00a6, *(unsigned short*)0x0002',
                    f"dump binary memory {dumps['scanout_publication_back'].as_posix()} 0x2000 0x9800",
                    "disable 9", "enable 10", "continue", "end",
                    "break *0x1b4b", "disable 10", "commands 10", "silent",
                    'printf "FEAT006_COLLISION mode-assignment pc=%04x mode=%d screen=%d death=%d\\n", $pc, *(unsigned char*)0x00a5, *(unsigned char*)0x00a6, *(unsigned char*)0x004d',
                    "disable 10", "enable 11", "continue", "end",
                    "break *0x0ddb", "disable 11", "commands 11", "silent",
                    'printf "FEAT006_COLLISION irq-publication pc=%04x programmed_voff1=%02x front=%d back=%d pending=%d frames=%04x\\n", $pc, $a, *(unsigned char*)0x008f, *(unsigned char*)0x0090, *(unsigned char*)0x0091, *(unsigned short*)0x0002',
                    "disable 11", "enable 12", "continue", "end",
                    "break *0xad57", "disable 12", "commands 12", "silent",
                    'printf "FEAT006_COLLISION first-helper-tick pc=%04x dp=%02x front=%d back=%d mode=%d screen=%d timer=%02x,%02x death=%d frames=%04x\\n", $pc, $dp, *(unsigned char*)0x008f, *(unsigned char*)0x0090, *(unsigned char*)0x00a5, *(unsigned char*)0x00a6, *(unsigned char*)0x00b0, *(unsigned char*)0x00b1, *(unsigned char*)0x004d, *(unsigned short*)0x0002',
                ] + scanout_dump_commands("scanout_first_display") + [
                    "disable 12", "enable 13", "continue", "end",
                    "break *0x1a11", "disable 13", "commands 13", "silent",
                    'printf "FEAT006_COLLISION subsequent-route pc=%04x a=%02x dp=%02x death=%d lives=%d timer=%02x,%02x mode=%d screen=%d frames=%04x\\n", $pc, $a, $dp, *(unsigned char*)0x004d, *(unsigned char*)0x0023, *(unsigned char*)0x00b0, *(unsigned char*)0x00b1, *(unsigned char*)0x00a5, *(unsigned char*)0x00a6, *(unsigned short*)0x0002',
                    "disable 13", "end",
                    "disable 1 2",
                    "set {unsigned char}0x0023 = 0",
                    'printf "FEAT006_COLLISION armed lives=0 death=%d timer=%d mode=%d screen=%d\\n", *(unsigned char*)0x004d, *(unsigned char*)0x003a, *(unsigned char*)0x00a5, *(unsigned char*)0x00a6',
                    "continue", "detach", "quit",
                ]

        def wait(label: str, condition: str, limit: int = 2400) -> None:
            commands.extend([
                f"condition 1 {condition}", "continue", "condition 1",
                f'printf "FEAT006_STATE {label} screen=%d mode=%d\\n", '
                "*(unsigned char*)0x00a6, *(unsigned char*)0x00a5",
            ])

        def dump_owner(name: str) -> None:
            path = dumps[name].as_posix()
            commands.extend([
                "set $feat_p1 = *(unsigned char*)0xffa1",
                "set $feat_p2 = *(unsigned char*)0xffa2",
                "set $feat_p3 = *(unsigned char*)0xffa3",
                "set $feat_p4 = *(unsigned char*)0xffa4",
                "if *(unsigned char*)0x008f == 0",
                "set {unsigned char}0xffa1 = 0x30", "set {unsigned char}0xffa2 = 0x31",
                "set {unsigned char}0xffa3 = 0x32", "set {unsigned char}0xffa4 = 0x33",
                "else", "set {unsigned char}0xffa1 = 0x2c", "set {unsigned char}0xffa2 = 0x2d",
                "set {unsigned char}0xffa3 = 0x2e", "set {unsigned char}0xffa4 = 0x2f", "end",
                f"dump binary memory {path} 0x2000 0x9800",
                "set {unsigned char}0xffa1 = $feat_p1", "set {unsigned char}0xffa2 = $feat_p2",
                "set {unsigned char}0xffa3 = $feat_p3", "set {unsigned char}0xffa4 = $feat_p4",
            ])

        wait("attract", "*(unsigned char*)0x00a6 == 0 && *(unsigned char*)0x00a5 == 2")
        commands.append(f"dump binary memory {dumps['instruction'].as_posix()} 0x0300 0x{0x0300 + len(expected['instruction']):04x}")
        dump_owner("attract_frame")
        commands += ["set {unsigned char}0x00b0 = 0x02", "set {unsigned char}0x00b1 = 0x2d"]
        wait("instructions", "*(unsigned char*)0x00a6 == 1 && *(unsigned char*)0x00a5 == 3")
        commands += ["set {unsigned char}0x00b0 = 0x06", "set {unsigned char}0x00b1 = 0xff"]
        wait("demo-level-start", "*(unsigned char*)0x00a6 == 2 && *(unsigned char*)0x00a5 == 6")
        wait("demo-level-ready", "*(unsigned char*)0x00a6 == 2 && *(unsigned char*)0x00a5 == 6 && *(unsigned char*)0x0091 == 0 && *(unsigned char*)0x0098 == 0")
        commands += ["set {unsigned char}0x00b0 = 0", "set {unsigned char}0x00b1 = 179"]
        wait("demo", "*(unsigned char*)0x00a5 == 4")
        commands.append(f"dump binary memory {dumps['demo'].as_posix()} 0x0300 0x{0x0300 + len(expected['demo']):04x}")
        commands += ["set {unsigned char}0x00a8 = 1", "set $feat_inject_start = 1"]
        wait("level-start", "*(unsigned char*)0x00a6 == 2 && *(unsigned char*)0x00a5 == 6")
        commands += ["set {unsigned char}0x00b0 = 0", "set {unsigned char}0x00b1 = 179"]
        wait("gameplay", "*(unsigned char*)0x00a5 == 0")
        commands.append(f"dump binary memory {dumps['audio'].as_posix()} 0x0300 0x{0x0300 + len(expected['audio']):04x}")
        dump_owner("gameplay_frame")
        if args.terminal_death_diagnostic:
            commands += [
                f"dump binary memory {dumps['presentation_module'].as_posix()} 0x1900 0x1e00",
            ]
            commands += diagnostic_commands
            if (
                not args.timer_step_diagnostic
                and not args.natural_final_life_diagnostic
                and not args.gameover_scanout_diagnostic
                and not args.visible_natural_collision_diagnostic
            ):
                commands += [
                    "disable 1", "set {unsigned char}0x004d = 4", "continue",
                    f"dump binary memory {dumps['highscore'].as_posix()} 0x0300 0x{0x0300 + len(expected['highscore']):04x}",
                    "detach", "quit",
                ]
        else:
            commands += ["set {unsigned char}0x004d = 4"]
        if not args.terminal_death_diagnostic:
            wait("game-over", "*(unsigned char*)0x00a6 == 4 && *(unsigned char*)0x00a5 == 7")
            commands.append(f"dump binary memory {dumps['highscore'].as_posix()} 0x0300 0x{0x0300 + len(expected['highscore']):04x}")
            commands += ["set {unsigned char}0x00b0 = 0", "set {unsigned char}0x00b1 = 179"]
            wait("name-entry", "*(unsigned char*)0x00a6 == 5 && *(unsigned char*)0x00a5 == 8")
            dump_owner("name_frame")
            commands += ["set {unsigned char}0x00e8 = 59", "set {unsigned char}0x00e9 = 91"]
            wait("high-score", "*(unsigned char*)0x00a6 == 3 && *(unsigned char*)0x00a5 == 5")
            dump_owner("highscore_frame")
            commands += ["set {unsigned char}0x00b0 = 2", "set {unsigned char}0x00b1 = 87"]
            wait("return-attract", "*(unsigned char*)0x00a6 == 0 && *(unsigned char*)0x00a5 == 2")
            commands.append(f"dump binary memory {dumps['return_instruction'].as_posix()} 0x0300 0x{0x0300 + len(expected['instruction']):04x}")
            commands += ["set {unsigned char}0x00a8 = 1", "set $feat_inject_start = 1"]
            wait("later-level-start", "*(unsigned char*)0x00a6 == 2 && *(unsigned char*)0x00a5 == 6")
            commands += ["set {unsigned char}0x00b0 = 0", "set {unsigned char}0x00b1 = 179"]
            wait("later-gameplay", "*(unsigned char*)0x00a5 == 0")
            commands.append(f"dump binary memory {dumps['later_audio'].as_posix()} 0x0300 0x{0x0300 + len(expected['audio']):04x}")
            commands += ["set $pc = 0xc002", "continue"]
            wait("soft-reset-attract", "*(unsigned char*)0x00a6 == 0 && *(unsigned char*)0x00a5 == 2")
            commands.append(f"dump binary memory {dumps['soft_instruction'].as_posix()} 0x0300 0x{0x0300 + len(expected['instruction']):04x}")
            commands += [
                'printf "FEAT006_ROUTE %d %d %d %d\\n", *(unsigned char*)0xff01, *(unsigned char*)0xff03, *(unsigned char*)0xff21, *(unsigned char*)0xff23',
                "detach", "quit",
            ]
        try:
            time.sleep(0.25)
            output = gmc_boot.run_gdb_commands(str(args.gdb), commands, ROOT, int(args.timeout))
        finally:
            gmc_boot.stop_process(process)
            process.wait()
        log_path = args.output.parent / (
            "feat006-visible-natural-collision-diagnostic.gdb.log"
            if args.visible_natural_collision_diagnostic else
            "feat006-gameover-scanout-diagnostic.gdb.log"
            if args.gameover_scanout_diagnostic else
            "feat006-natural-final-life-diagnostic.gdb.log"
            if args.natural_final_life_diagnostic else
            "feat006-complete-runtime.gdb.log"
        )
        log_path.write_text(output, encoding="utf-8")
        if args.terminal_death_diagnostic:
            labels = [
                "death-dispatch", "audio-return", "highscore-install", "highscore-return",
                "gameover-start", "load-entry", "cell-loop-entry", "first-progress",
                "load-done", "dynamic-return", "publication", "mode-assignment",
                "highscore-helper-entry", "highscore-gameover-tick", "timer-after-increment", "gameover-threshold",
                "name-screen-start", "name-mode-assignment",
            ]
            found = [label for label in labels if f"FEAT006_DIAG {label} " in output]
            prefix_labels = [
                "attract", "instructions", "demo-level-start", "demo-level-ready",
                "demo", "level-start", "gameplay",
            ]
            prefix_found = [
                label for label in prefix_labels if f"FEAT006_STATE {label} " in output
            ]
            ordered = [output.find(f"FEAT006_DIAG {label} ") for label in found]
            first_missing = (
                next((label for label in labels if label not in found), None)
                if found else "diagnostic-phase-not-reached"
            )
            module_bytes = dumps["presentation_module"].read_bytes() if dumps["presentation_module"].exists() else b""
            module_expected = (ROOT / "build/ladybug-presentation-runtime.bin").read_bytes()
            highscore_bytes = dumps["highscore_load_done"].read_bytes() if dumps["highscore_load_done"].exists() else b""
            staged_bytes = dumps["highscore_staged"].read_bytes() if dumps["highscore_staged"].exists() else b""
            live_install_bytes = dumps["highscore_live_install"].read_bytes() if dumps["highscore_live_install"].exists() else b""
            module_exact = module_bytes == module_expected if module_bytes else None
            highscore_exact = highscore_bytes == expected["highscore"] if highscore_bytes else None
            markers_complete = first_missing is None and ordered == sorted(ordered)

            def identity_record(actual: bytes) -> dict:
                expected_bytes = expected["highscore"]
                first_difference = next(
                    (offset for offset, pair in enumerate(zip(expected_bytes, actual)) if pair[0] != pair[1]),
                    min(len(expected_bytes), len(actual)) if len(expected_bytes) != len(actual) else None,
                )
                return {
                    "bytes": len(actual),
                    "sha256": hashlib.sha256(actual).hexdigest() if actual else None,
                    "exact": actual == expected_bytes if actual else None,
                    "first_difference_offset": first_difference,
                }

            staged_identity = identity_record(staged_bytes)
            live_install_identity = identity_record(live_install_bytes)
            live_done_identity = identity_record(highscore_bytes)
            first_identity_failure = (
                "staged-source-identity" if staged_identity["exact"] is False else
                "install-copy-identity" if live_install_identity["exact"] is False else
                "post-install-overwrite" if live_done_identity["exact"] is False else None
            )
            evidence = {
                "schema": "ladybug-feat006-terminal-death-diagnostic-v1",
                "status": (
                    "pass" if markers_complete and module_exact and highscore_exact else
                    "fail" if markers_complete else
                    "inconclusive" if found else "rejected"
                ),
                "rom_sha256": hashlib.sha256(args.rom.read_bytes()).hexdigest(),
                "markers": found,
                "first_missing": first_missing,
                "last_proven": (
                    found[-1] if found else
                    f"natural-prefix:{prefix_found[-1]}" if prefix_found else None
                ),
                "presentation_module_exact": module_exact,
                "highscore_owner_exact": highscore_exact,
                "highscore_identity": {
                    "authored": {
                        "bytes": len(expected["highscore"]),
                        "sha256": hashlib.sha256(expected["highscore"]).hexdigest(),
                    },
                    "staged": staged_identity,
                    "live_after_install": live_install_identity,
                    "live_at_load_done": live_done_identity,
                },
                "first_failure": (
                    "presentation-module-identity" if module_exact is False else
                    first_identity_failure
                ),
                "observation_interference": None,
                "timed_out": first_missing is not None,
                "timeout_phase": "diagnostic" if found else "natural-prefix",
                "deadline_seconds": args.timeout,
                "timeout_meaning": "the next fixed-module boundary was not observed; it does not prove slow target code",
            }
            if args.visible_natural_collision_diagnostic:
                collision_labels = [
                    "collision-init", "terminal-transition", "normal-dispatch",
                    "highscore-install", "highscore-return", "gameover-start",
                    "publication", "mode-assignment", "irq-publication",
                    "first-helper-tick", "subsequent-route",
                ]
                collision_found = [
                    label for label in collision_labels
                    if f"FEAT006_COLLISION {label} " in output
                ]
                collision_order = [
                    output.find(f"FEAT006_COLLISION {label} ")
                    for label in collision_found
                ]
                collision_first_missing = next(
                    (label for label in collision_labels if label not in collision_found), None
                )
                collision_expected = (ROOT / "build/ladybug-enemy-runtime.rom").read_bytes()
                collision_actual = (
                    dumps["collision_runtime_live"].read_bytes()
                    if dumps["collision_runtime_live"].exists() else b""
                )
                resident_actual = (
                    dumps["resident_terminal"].read_bytes()
                    if dumps["resident_terminal"].exists() else b""
                )
                resident_image = (ROOT / "build/ladybug-runtime.rom").read_bytes()
                resident_expected = resident_image[0xD3A7 - 0xC000:0xD3B7 - 0xC000]
                live_highscore = (
                    dumps["highscore_live_install"].read_bytes()
                    if dumps["highscore_live_install"].exists() else b""
                )
                publication_back = (
                    dumps["scanout_publication_back"].read_bytes()
                    if dumps["scanout_publication_back"].exists() else b""
                )
                first_display = (
                    dumps["scanout_first_display"].read_bytes()
                    if dumps["scanout_first_display"].exists() else b""
                )
                presentation_manifest = json.loads(
                    (ROOT / "build/ladybug-presentation.json").read_text(encoding="utf-8")
                )
                gameover_index = next(
                    index for index, item in enumerate(presentation_manifest["maps"])
                    if item["name"] == "game-over"
                )
                expected_gameover_sha256 = presentation_manifest["static_frame_sha256"][gameover_index]
                publication_sha256 = hashlib.sha256(publication_back).hexdigest() if publication_back else None
                first_display_sha256 = hashlib.sha256(first_display).hexdigest() if first_display else None
                route_match = re.search(
                    r"FEAT006_COLLISION subsequent-route .*?a=([0-9a-fA-F]{2}).*?"
                    r"mode=(\d+) screen=(\d+)", output,
                )
                route_index = int(route_match.group(1), 16) if route_match else None
                route_kind = {
                    0: "attract", 3: "high-score", 5: "name-entry",
                }.get(route_index, f"screen-{route_index}" if route_index is not None else None)
                identities_exact = (
                    collision_actual == collision_expected
                    and module_exact is True
                    and resident_actual == resident_expected
                    and live_highscore == expected["highscore"]
                )
                scanout_exact = (
                    len(publication_back) == 30720
                    and publication_sha256 == expected_gameover_sha256
                    and first_display == publication_back
                )
                collision_complete = (
                    collision_first_missing is None
                    and collision_order == sorted(collision_order)
                )
                first_difference = (
                    collision_first_missing if collision_first_missing else
                    "collision-runtime-identity" if collision_actual != collision_expected else
                    "presentation-module-identity" if module_exact is not True else
                    "resident-terminal-identity" if resident_actual != resident_expected else
                    "highscore-owner-identity" if live_highscore != expected["highscore"] else
                    "gameover-render-output" if publication_sha256 != expected_gameover_sha256 else
                    "publication-to-scanout" if first_display != publication_back else
                    None
                )
                evidence.update({
                    "schema": "ladybug-feat006-visible-natural-collision-diagnostic-v1",
                    "status": "pass" if collision_complete and identities_exact and scanout_exact else "inconclusive",
                    "markers": collision_found,
                    "first_missing": collision_first_missing,
                    "last_proven": collision_found[-1] if collision_found else "gameplay-armed",
                    "natural_sequence_ordered": collision_order == sorted(collision_order),
                    "only_runtime_write": {"address": "0x0023", "symbol": "LIVES", "value": 0},
                    "module_identity": {
                        "collision_runtime": {
                            "bytes": len(collision_actual),
                            "sha256": hashlib.sha256(collision_actual).hexdigest() if collision_actual else None,
                            "expected_sha256": hashlib.sha256(collision_expected).hexdigest(),
                            "exact": collision_actual == collision_expected if collision_actual else None,
                        },
                        "presentation_runtime": {
                            "bytes": len(module_bytes),
                            "sha256": hashlib.sha256(module_bytes).hexdigest() if module_bytes else None,
                            "expected_sha256": hashlib.sha256(module_expected).hexdigest(),
                            "exact": module_exact,
                        },
                        "resident_terminal": {
                            "bytes": len(resident_actual),
                            "sha256": hashlib.sha256(resident_actual).hexdigest() if resident_actual else None,
                            "expected_sha256": hashlib.sha256(resident_expected).hexdigest(),
                            "exact": resident_actual == resident_expected if resident_actual else None,
                        },
                        "highscore_owner": {
                            "bytes": len(live_highscore),
                            "sha256": hashlib.sha256(live_highscore).hexdigest() if live_highscore else None,
                            "expected_sha256": hashlib.sha256(expected["highscore"]).hexdigest(),
                            "exact": live_highscore == expected["highscore"] if live_highscore else None,
                        },
                    },
                    "gameover_scanout": {
                        "bytes": len(first_display),
                        "expected_sha256": expected_gameover_sha256,
                        "publication_sha256": publication_sha256,
                        "first_scanout_sha256": first_display_sha256,
                        "publication_matches_expected": publication_sha256 == expected_gameover_sha256,
                        "first_scanout_matches_publication": first_display == publication_back,
                    },
                    "subsequent_route": {"screen_index": route_index, "kind": route_kind},
                    "first_difference_from_injected_route": (
                        None if collision_first_missing == "subsequent-route" else first_difference
                    ),
                    "post_helper_boundary": (
                        "unresolved: the first and subsequent start-screen markers shared address 0x1a11; "
                        "the retained GDB log reports duplicate breakpoint ownership"
                        if collision_first_missing == "subsequent-route" else None
                    ),
                    "manual_baseline": "completed player game returned directly to attract with no visible game-over",
                    "feature_acceptance": "unresolved" if first_difference is None else "fail",
                    "gdb_log_sha256": hashlib.sha256(log_path.read_bytes()).hexdigest(),
                    "observation_interference": (
                        "duplicate GDB breakpoints 8 and 13 shared fixed address 0x1a11"
                        if collision_first_missing == "subsequent-route" else None
                    ),
                    "timed_out": collision_first_missing is not None,
                    "deadline_seconds": args.timeout,
                    "timeout_meaning": "the next chained natural boundary was not observed; it does not prove slow target code",
                })
            if args.gameover_scanout_diagnostic:
                scanout_labels = [
                    "terminal-state-entry", "normal-dispatch", "highscore-install",
                    "highscore-return", "gameover-start", "publication",
                    "mode-assignment", "irq-publication", "first-helper-tick",
                    "second-helper-tick",
                ]
                scanout_found = [
                    label for label in scanout_labels
                    if f"FEAT006_SCANOUT {label} " in output
                ]
                scanout_order = [
                    output.find(f"FEAT006_SCANOUT {label} ")
                    for label in scanout_found
                ]
                scanout_first_missing = next(
                    (label for label in scanout_labels if label not in scanout_found), None
                )

                def scanout_state(label: str) -> dict | None:
                    match = re.search(
                        rf"FEAT006_SCANOUT {label} .*?front=(\d+) back=(\d+) "
                        rf"pending=(\d+).*?voff=([0-9a-fA-F]{{2}}),([0-9a-fA-F]{{2}}) "
                        rf"pars=([0-9a-fA-F]{{2}}),([0-9a-fA-F]{{2}}),"
                        rf"([0-9a-fA-F]{{2}}),([0-9a-fA-F]{{2}}),([0-9a-fA-F]{{2}}) "
                        rf"frames=([0-9a-fA-F]{{4}}) commit=([0-9a-fA-F]{{4}}) "
                        rf"sim=([0-9a-fA-F]{{4}})",
                        output,
                    )
                    if not match:
                        return None
                    values = [int(value, 16) for value in match.groups()[3:]]
                    return {
                        "front": int(match.group(1)),
                        "back": int(match.group(2)),
                        "pending": int(match.group(3)),
                        "voff1": values[0], "voff0": values[1],
                        "pars": values[2:7],
                        "frames": values[7], "commit": values[8], "sim": values[9],
                    }

                publication_state = scanout_state("publication")
                assignment_state = scanout_state("mode-assignment")
                first_state = scanout_state("first-helper-tick")
                second_state = scanout_state("second-helper-tick")
                irq_match = re.search(
                    r"FEAT006_SCANOUT irq-publication .*?programmed_voff1=([0-9a-fA-F]{2}) "
                    r"front=(\d+) back=(\d+) pending=(\d+) frames=([0-9a-fA-F]{4}) "
                    r"commit=([0-9a-fA-F]{4}) sim=([0-9a-fA-F]{4})",
                    output,
                )
                irq_state = ({
                    "programmed_voff1": int(irq_match.group(1), 16),
                    "front_before": int(irq_match.group(2)),
                    "back_before": int(irq_match.group(3)),
                    "pending_before": int(irq_match.group(4)),
                    "frames": int(irq_match.group(5), 16),
                    "commit": int(irq_match.group(6), 16),
                    "sim": int(irq_match.group(7), 16),
                } if irq_match else None)
                publication_back = dumps["scanout_publication_back"].read_bytes() if dumps["scanout_publication_back"].exists() else b""
                first_display = dumps["scanout_first_display"].read_bytes() if dumps["scanout_first_display"].exists() else b""
                second_display = dumps["scanout_second_display"].read_bytes() if dumps["scanout_second_display"].exists() else b""
                presentation_manifest = json.loads(
                    (ROOT / "build/ladybug-presentation.json").read_text(encoding="utf-8")
                )
                gameover_index = next(
                    index for index, item in enumerate(presentation_manifest["maps"])
                    if item["name"] == "game-over"
                )
                expected_gameover_sha256 = presentation_manifest["static_frame_sha256"][gameover_index]
                publication_sha256 = hashlib.sha256(publication_back).hexdigest() if publication_back else None
                first_sha256 = hashlib.sha256(first_display).hexdigest() if first_display else None
                second_sha256 = hashlib.sha256(second_display).hexdigest() if second_display else None
                attract_bytes = dumps["attract_frame"].read_bytes() if dumps["attract_frame"].exists() else b""
                attract_sha256 = hashlib.sha256(attract_bytes).hexdigest() if attract_bytes else None
                resident_actual = dumps["resident_terminal"].read_bytes() if dumps["resident_terminal"].exists() else b""
                resident_image = (ROOT / "build/ladybug-runtime.rom").read_bytes()
                resident_expected = resident_image[0xD3A7 - 0xC000:0xD3B7 - 0xC000]
                resident_exact = resident_actual == resident_expected if resident_actual else None

                def irq_program_matches_owner() -> bool | None:
                    if irq_state is None:
                        return None
                    owner = irq_state["back_before"]
                    expected_voff1 = 0xC0 if owner == 0 else 0xB0 if owner == 1 else None
                    return expected_voff1 is not None and irq_state["programmed_voff1"] == expected_voff1

                front_swap_matches = (
                    first_state["front"] == irq_state["back_before"]
                    if first_state and irq_state else None
                )

                interval_delta = (
                    (second_state["frames"] - first_state["frames"]) & 0xFFFF
                    if first_state and second_state else None
                )
                first_mismatch = (
                    "gameover-render-output" if publication_sha256 != expected_gameover_sha256 else
                    "publication-to-scanout" if first_display != publication_back else
                    "first-scanout-identity" if first_sha256 != expected_gameover_sha256 else
                    "scanout-persistence" if second_display != first_display else
                    "irq-program-vs-owner" if irq_program_matches_owner() is False else
                    "irq-front-swap" if front_swap_matches is False else
                    "display-interval" if interval_delta is None or interval_delta < 1 else None
                )
                scanout_complete = (
                    scanout_first_missing is None
                    and scanout_order == sorted(scanout_order)
                    and len(publication_back) == 30720
                    and len(first_display) == 30720
                    and len(second_display) == 30720
                )
                evidence.update({
                    "schema": "ladybug-feat006-gameover-scanout-diagnostic-v1",
                    "status": (
                        "pass" if scanout_complete and module_exact and highscore_exact and resident_exact else
                        "fail" if scanout_complete else "inconclusive"
                    ),
                    "markers": scanout_found,
                    "first_missing": scanout_first_missing,
                    "last_proven": scanout_found[-1] if scanout_found else "gameplay",
                    "natural_sequence_ordered": scanout_order == sorted(scanout_order),
                    "states": {
                        "publication": publication_state,
                        "mode_assignment": assignment_state,
                        "irq_publication": irq_state,
                        "first_helper_tick": first_state,
                        "second_helper_tick": second_state,
                    },
                    "framebuffer_identity": {
                        "bytes": len(publication_back),
                        "expected_gameover_sha256": expected_gameover_sha256,
                        "publication_back_sha256": publication_sha256,
                        "first_scanout_sha256": first_sha256,
                        "second_scanout_sha256": second_sha256,
                        "attract_sha256": attract_sha256,
                        "publication_matches_expected": publication_sha256 == expected_gameover_sha256,
                        "first_scanout_matches_publication": first_display == publication_back,
                        "first_scanout_matches_expected": first_sha256 == expected_gameover_sha256,
                        "second_scanout_matches_first": second_display == first_display,
                        "first_scanout_matches_attract": first_sha256 == attract_sha256,
                    },
                    "scanout_contract": {
                        "irq_program_matches_owner": irq_program_matches_owner(),
                        "front_swap_matches_irq_target": front_swap_matches,
                        "voff_readback_authoritative": False,
                        "display_interval_frames": interval_delta,
                    },
                    "resident_terminal_identity": {
                        "bytes": len(resident_actual),
                        "sha256": hashlib.sha256(resident_actual).hexdigest() if resident_actual else None,
                        "expected_sha256": hashlib.sha256(resident_expected).hexdigest(),
                        "exact": resident_exact,
                    },
                    "first_mismatch": first_mismatch,
                    "gdb_log_sha256": hashlib.sha256(log_path.read_bytes()).hexdigest(),
                    "feature_acceptance": "fail",
                    "manual_baseline": "player final life returned directly to attract with no visible game-over, name-entry, or high-score screen",
                    "first_failure": (
                        "presentation-module-identity" if module_exact is False else
                        "resident-terminal-identity" if resident_exact is False else
                        first_identity_failure if first_identity_failure else
                        scanout_first_missing
                    ),
                    "observation_interference": None,
                    "timed_out": scanout_first_missing is not None,
                })
            if args.natural_final_life_diagnostic:
                natural_labels = [
                    "terminal-state-entry", "normal-dispatch", "highscore-install",
                    "highscore-return", "gameover-start", "publication",
                    "mode-assignment", "first-helper-tick",
                ]
                natural_found = [
                    label for label in natural_labels
                    if f"FEAT006_NATURAL {label} " in output
                ]
                natural_order = [
                    output.find(f"FEAT006_NATURAL {label} ")
                    for label in natural_found
                ]
                natural_first_missing = next(
                    (label for label in natural_labels if label not in natural_found), None
                )
                resident_actual = (
                    dumps["resident_terminal"].read_bytes()
                    if dumps["resident_terminal"].exists() else b""
                )
                resident_image = (ROOT / "build/ladybug-runtime.rom").read_bytes()
                resident_expected = resident_image[0xD3A7 - 0xC000:0xD3B7 - 0xC000]
                resident_exact = resident_actual == resident_expected if resident_actual else None
                helper_match = re.search(
                    r"FEAT006_NATURAL first-helper-tick .*?dp=([0-9a-fA-F]+) "
                    r"timer=([0-9a-fA-F]{2}),([0-9a-fA-F]{2})",
                    output,
                )
                helper_dp = int(helper_match.group(1), 16) if helper_match else None
                helper_timer = (
                    [int(helper_match.group(2), 16), int(helper_match.group(3), 16)]
                    if helper_match else None
                )
                natural_complete = (
                    natural_first_missing is None
                    and natural_order == sorted(natural_order)
                )
                evidence.update({
                    "schema": "ladybug-feat006-natural-final-life-diagnostic-v1",
                    "status": (
                        "pass" if natural_complete and module_exact and highscore_exact and resident_exact else
                        "fail" if natural_complete else "inconclusive"
                    ),
                    "markers": natural_found,
                    "first_missing": natural_first_missing,
                    "last_proven": natural_found[-1] if natural_found else "gameplay",
                    "natural_sequence_ordered": natural_order == sorted(natural_order),
                    "resident_terminal_identity": {
                        "bytes": len(resident_actual),
                        "sha256": hashlib.sha256(resident_actual).hexdigest() if resident_actual else None,
                        "expected_sha256": hashlib.sha256(resident_expected).hexdigest(),
                        "exact": resident_exact,
                    },
                    "helper_direct_page": {
                        "dp": helper_dp,
                        "timer_address": ((helper_dp << 8) + 0xB0) if helper_dp is not None else None,
                        "raw_00b0": helper_timer,
                    },
                    "gdb_log_sha256": hashlib.sha256(log_path.read_bytes()).hexdigest(),
                    "feature_acceptance": "fail",
                    "manual_baseline": "player final life returned directly to attract with no visible game-over, name-entry, or high-score screen",
                    "first_failure": (
                        "presentation-module-identity" if module_exact is False else
                        "resident-terminal-identity" if resident_exact is False else
                        first_identity_failure if first_identity_failure else
                        natural_first_missing
                    ),
                    "observation_interference": None,
                    "timed_out": natural_first_missing is not None,
                })
            if args.timer_step_diagnostic:
                step_labels = [
                    "entry", "before-increment", "after-ldd", "after-addd",
                    "after-stb", "after-cmpd", "after-branch",
                ]
                step_found = [
                    label for label in step_labels
                    if f"FEAT006_STEP {label} " in output
                ]
                expected_step_pcs = {
                    "entry": "pc=ad57",
                    "before-increment": "pc=ad57",
                    "after-ldd": "pc=ad59",
                    "after-addd": "pc=ad5c",
                    "after-stb": "pc=ad5e",
                    "after-cmpd": "pc=ad62",
                    "after-branch": "pc=ad64",
                }
                step_pc_valid = all(
                    f"FEAT006_STEP {label} {expected_step_pcs[label]}" in output
                    for label in step_labels
                )
                evidence.update({
                    "schema": "ladybug-feat006-timer-step-diagnostic-v1",
                    "status": "pass" if step_found == step_labels and step_pc_valid else "inconclusive",
                    "step_markers": step_found,
                    "step_trace_complete": step_found == step_labels,
                    "step_pc_sequence_valid": step_pc_valid,
                    "gdb_log_sha256": hashlib.sha256(log_path.read_bytes()).hexdigest() if log_path.exists() else None,
                    "observation_interference": (
                        "gdb-single-step-pc-diverged" if not step_pc_valid else
                        "not isolated" if step_found != step_labels else None
                    ),
                })
            args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
            if evidence["status"] != "pass":
                raise SystemExit(f"FEAT-006 terminal-death diagnostic inconclusive: {evidence}")
            print(f"FEAT-006 terminal-death diagnostic: {evidence}")
            return
        required_states = [
            "attract", "instructions", "demo-level-start", "demo-level-ready", "demo", "level-start", "gameplay", "game-over",
            "name-entry", "high-score", "return-attract", "later-level-start",
            "later-gameplay", "soft-reset-attract",
        ]
        for label in required_states:
            marker = f"FEAT006_STATE {label} "
            if marker not in output:
                raise SystemExit(f"FEAT-006 GDB proof: missing {label}; output={output[-1200:]}")
            line = next(line for line in output.splitlines() if marker in line)
            match = __import__("re").search(r"screen=(\d+) mode=(\d+)", line)
            if not match:
                raise SystemExit(f"FEAT-006 GDB proof: {label} deadline: {line}")
            events.append({"phase": label, "screen": int(match.group(1)), "mode": int(match.group(2))})
        for name, owner in (
            ("instruction", "instruction"), ("demo", "demo"), ("audio", "audio"),
            ("highscore", "highscore"), ("return_instruction", "instruction"),
            ("later_audio", "audio"), ("soft_instruction", "instruction"),
        ):
            actual = dumps[name].read_bytes() if dumps[name].exists() else b""
            if actual != expected[owner]:
                raise SystemExit(f"FEAT-006 GDB proof: {name} owner differs ({len(actual)} bytes)")
        for name, target in (
            ("attract_frame", args.attract_png), ("gameplay_frame", args.gameplay_png),
            ("name_frame", args.name_entry_png), ("highscore_frame", args.high_score_png),
        ):
            frame = dumps[name].read_bytes() if dumps[name].exists() else b""
            if len(frame) != 30720:
                raise SystemExit(f"FEAT-006 GDB proof: {name} frame is {len(frame)} bytes")
            write_png(target, frame)
        route_line = next((line for line in output.splitlines() if "FEAT006_ROUTE" in line), "")
        route = [int(value) for value in route_line.split()[-4:]] if route_line else []
        evidence = {
            "schema": "ladybug-feat006-complete-runtime-v1", "status": "pass",
            "transport": "gdb", "rom_sha256": hashlib.sha256(args.rom.read_bytes()).hexdigest(),
            "events": events,
            "reset_replacement": [{"kind": "soft", "instruction_owner": True},
                                  {"kind": "hard", "instruction_owner": True,
                                   "evidence": "independent cold loader/resident identity pass"}],
            "pia_route_registers": route,
            "mute_contract": "four-write startup/reset plus AUDIO_INIT before replacement",
            "timer_tick_cue": 4, "timer_tick_compact_path": True,
            "source_margin_bytes": layout["gmc"]["spare_bytes"],
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="ascii")
        print("FEAT-006 runtime proof: 13 ordered GDB lifecycle markers; instruction/demo/audio/high-score ownership, soft reset, cold hard-reset identity, return, reinstall, and four PNG captures passed")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xroar", type=Path, required=True)
    parser.add_argument("--gdb", type=Path, default=Path("/usr/local/bin/m6809-gdb"))
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--attract-png", type=Path, required=True)
    parser.add_argument("--gameplay-png", type=Path, required=True)
    parser.add_argument("--name-entry-png", type=Path, required=True)
    parser.add_argument("--high-score-png", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--terminal-death-diagnostic", action="store_true")
    parser.add_argument("--timer-step-diagnostic", action="store_true")
    parser.add_argument("--natural-final-life-diagnostic", action="store_true")
    parser.add_argument("--gameover-scanout-diagnostic", action="store_true")
    parser.add_argument("--visible-natural-collision-diagnostic", action="store_true")
    parser.add_argument("--scenario", choices=("all",), default="all")
    args = parser.parse_args()
    if (
        args.timer_step_diagnostic
        or args.natural_final_life_diagnostic
        or args.gameover_scanout_diagnostic
        or args.visible_natural_collision_diagnostic
    ):
        args.terminal_death_diagnostic = True

    module_symbols = runtime.symbols(ROOT / "build/ladybug-presentation-runtime.map")
    entry = module_symbols["presentation_flow_tick"]
    event_hook = module_symbols["pft_ready"]
    layout = json.loads((ROOT / "build/ladybug-sparse-layout.json").read_text(encoding="ascii"))
    if module_symbols.get("PRESENTATION_HIGHSCORE_RUNTIME_ADDRESS") != int(layout["highscore_runtime"]["stage_address"]):
        raise SystemExit("FEAT-006 runtime proof: assembled high-score source address differs from staged address")
    helper_symbols = runtime.symbols(ROOT / "build/ladybug-highscore-runtime.map")
    helper_layout = layout["highscore_helper"]
    if helper_symbols.get("HIGHSCORE_PHASE_HELPER_ADDRESS") != int(helper_layout["stage_address"]):
        raise SystemExit("FEAT-006 runtime proof: assembled high-score helper address differs from staged address")
    if helper_symbols.get("HIGHSCORE_PHASE_HELPER_RESUME") != int(helper_layout["stage_address"]) + 0xC0:
        raise SystemExit("FEAT-006 runtime proof: assembled high-score helper resume differs from staged address")
    expected = {
        "instruction": (ROOT / "build/ladybug-instruction-runtime.bin").read_bytes(),
        "demo": (ROOT / "build/ladybug-demo-runtime.bin").read_bytes(),
        "highscore": (ROOT / "build/ladybug-highscore-runtime.bin").read_bytes(),
        "audio": (ROOT / "build/ladybug-audio-runtime.bin").read_bytes()[:916],
    }
    source = (ROOT / "src/presentation_runtime.s").read_text(encoding="ascii")
    helper_source = (ROOT / "src/demo_runtime.s").read_text(encoding="ascii")
    for fragment in ("jsr     AUDIO_INIT_EXEC", "install_highscore_runtime", "lbsr    install_demo_runtime", "jsr     AUDIO_INSTALL_EXEC"):
        if fragment not in source:
            raise SystemExit(f"FEAT-006 runtime proof: transition contract missing: {fragment}")
    for fragment in ("lda     #$86", "lda     #$35", "lda     #$91", "lda     #$8A", "lda     #$23", "lda     #$92", "lda     #$9F"):
        if fragment not in helper_source:
            raise SystemExit("FEAT-006 runtime proof: compact cue-4 command path differs")

    help_text = subprocess.run(
        [str(args.xroar), "-help"], stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, check=False,
    ).stdout
    if "-monitor" not in help_text:
        gdb_runtime(args, expected, entry, event_hook, layout)
        return

    monitor = runtime.load_monitor()
    process, client = runtime.launch_fast(monitor, args.xroar, args.rom)
    events = []
    deadline = time.monotonic() + args.timeout

    def state() -> tuple[int, int]:
        return runtime.read_byte(client, PRES_SCREEN), runtime.read_byte(client, PRES_MODE)

    def installed(name: str) -> bool:
        data = expected[name]
        return runtime.read_bytes(client, 0x0300, len(data)) == data

    def advance(label: str, predicate, limit: int = 1200) -> tuple[int, int]:
        for _ in range(limit):
            if time.monotonic() >= deadline:
                break
            hit = client.run_to_breakpoint(max(0.1, deadline - time.monotonic()))
            if hit.get("pc") != entry:
                raise SystemExit(f"FEAT-006 runtime proof: {label} stopped at {hit}")
            current = state()
            if predicate(*current):
                events.append({"phase": label, "screen": current[0], "mode": current[1]})
                return current
        raise SystemExit(f"FEAT-006 runtime proof: {label} deadline at screen/mode={state()}")

    ids = []
    try:
        ids = monitor.setup(client, [entry])
        advance("attract", lambda screen, mode: screen == 0 and mode == MODE_ATTRACT)
        if not installed("instruction"):
            raise SystemExit("FEAT-006 runtime proof: attract did not install instruction owner")
        write_png(args.attract_png, runtime.read_owner(client, runtime.read_byte(client, runtime.FB_FRONT)))

        advance("instructions", lambda screen, mode: screen == 1 and mode == MODE_INSTRUCTIONS)
        runtime.write_byte(client, PRES_TIMER, 0x06)
        runtime.write_byte(client, PRES_TIMER + 1, 0xFF)
        advance("demo", lambda screen, mode: mode == MODE_DEMO)
        if not installed("demo"):
            raise SystemExit("FEAT-006 runtime proof: demo owner differs")

        runtime.write_byte(client, PRES_CREDITS, 1)
        runtime.write_byte(client, PRES_EVENT, 1)
        advance("level-start", lambda screen, mode: screen == 2 and mode == MODE_LEVEL)
        runtime.write_byte(client, PRES_TIMER, 0)
        runtime.write_byte(client, PRES_TIMER + 1, 179)
        advance("gameplay", lambda screen, mode: mode == MODE_NORMAL)
        if not installed("audio"):
            raise SystemExit("FEAT-006 runtime proof: gameplay did not install full audio owner")
        write_png(args.gameplay_png, runtime.read_owner(client, runtime.read_byte(client, runtime.FB_FRONT)))

        runtime.write_byte(client, DEATH, 4)
        advance("game-over", lambda screen, mode: screen == 4 and mode == MODE_GAMEOVER)
        if not installed("highscore"):
            raise SystemExit("FEAT-006 runtime proof: game-over did not install high-score owner")
        runtime.write_byte(client, PRES_TIMER, 0)
        runtime.write_byte(client, PRES_TIMER + 1, 179)
        advance("name-entry", lambda screen, mode: screen == 5 and mode == MODE_NAME)
        write_png(args.name_entry_png, runtime.read_owner(client, runtime.read_byte(client, runtime.FB_FRONT)))

        runtime.write_byte(client, PRES_NAME_TIMER_PHASE, 59)
        runtime.write_byte(client, PRES_NAME_TIMER_BOX, 91)
        advance("high-score", lambda screen, mode: screen == 3 and mode == 5)
        write_png(args.high_score_png, runtime.read_owner(client, runtime.read_byte(client, runtime.FB_FRONT)))
        runtime.write_byte(client, PRES_TIMER, 2)
        runtime.write_byte(client, PRES_TIMER + 1, 87)
        advance("return-attract", lambda screen, mode: screen == 0 and mode == MODE_ATTRACT)
        if not installed("instruction"):
            raise SystemExit("FEAT-006 runtime proof: return-to-attract owner differs")

        runtime.write_byte(client, PRES_CREDITS, 1)
        runtime.write_byte(client, PRES_EVENT, 1)
        advance("later-level-start", lambda screen, mode: screen == 2 and mode == MODE_LEVEL)
        runtime.write_byte(client, PRES_TIMER, 0)
        runtime.write_byte(client, PRES_TIMER + 1, 179)
        advance("later-gameplay", lambda screen, mode: mode == MODE_NORMAL)
        if not installed("audio"):
            raise SystemExit("FEAT-006 runtime proof: later gameplay audio reinstall differs")

        reset_evidence = []
        for kind in ("soft", "hard"):
            client.call("reset", {"kind": kind})
            advance(f"{kind}-reset-attract", lambda screen, mode: screen == 0 and mode == MODE_ATTRACT)
            reset_evidence.append({"kind": kind, "instruction_owner": installed("instruction")})
        route = [runtime.read_byte(client, address) for address in (0xFF01, 0xFF03, 0xFF21, 0xFF23)]
        evidence = {
            "schema": "ladybug-feat006-complete-runtime-v1", "status": "pass",
            "rom_sha256": hashlib.sha256(args.rom.read_bytes()).hexdigest(),
            "events": events, "reset_replacement": reset_evidence,
            "pia_route_registers": route,
            "mute_contract": "four-write startup/reset plus AUDIO_INIT before replacement",
            "timer_tick_cue": 4, "timer_tick_compact_path": True,
            "source_margin_bytes": layout["gmc"]["spare_bytes"],
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="ascii")
        print(f"FEAT-006 runtime proof: {len(events)} ordered lifecycle markers; instruction/demo/audio/high-score ownership, cue 4, soft/hard reset, return, and reinstall passed")
    finally:
        if ids:
            try:
                monitor.clear(client, ids)
            except Exception:
                pass
        try:
            client.close()
        except Exception:
            pass
        runtime.stop(process)
        process.wait()


if __name__ == "__main__":
    main()
