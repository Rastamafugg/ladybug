#!/usr/bin/env python3
"""Bound the credited live-start handoff and record sparse destinations."""

from __future__ import annotations

import argparse
import os
import re
import signal
import shutil
import subprocess
from pathlib import Path

import verify_gmc_boot as gmc


DEFAULT_TIMEOUT = 20
PRES_READY = "1932"
PRES_MODE = "1944"
PRES_EVENT = 0x00A9
PRES_CREDITS = 0x00A8
ENTITY_COUNT = 0x0032
STAGE_DESTINATION = 0x1800


def bounded_gdb(gdb: str, commands: list[str], cwd: Path, timeout: int) -> str:
    process = subprocess.Popen(
        [gdb, "-q"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=cwd,
        start_new_session=(os.name != "nt"),
    )
    try:
        output, _ = process.communicate(
            input="\n".join(commands) + "\n", timeout=timeout
        )
        return output
    except subprocess.TimeoutExpired as exc:
        if os.name != "nt":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        else:
            process.kill()
        output, _ = process.communicate(timeout=5)
        partial = output or exc.output or ""
        if isinstance(partial, bytes):
            partial = partial.decode("utf-8", errors="replace")
        return partial + "\nBUG008_TIMEOUT\n"


def symbol(map_text: str, name: str) -> str:
    return gmc.map_symbol(map_text, name)


def handoff_address(rom: bytes) -> str:
    jump = rom.find(bytes((0x7E, 0x03, 0x00)))
    if jump < 0:
        raise SystemExit("BUG-008: relocated-loader jump missing")
    loader_start = jump + 3
    offset = rom.find(bytes((0x7E, 0xC0, 0x02)), loader_start)
    if offset < 0:
        raise SystemExit("BUG-008: relocated runtime handoff missing")
    return f"{0x0300 + offset - loader_start:04x}"


def trace_commands(port: int, presentation: dict[str, str], enemy: dict[str, str]) -> list[str]:
    stage = enemy["sparse_blit_stage"]
    framebuffer = enemy["sparse_blit_fb"]
    publish = enemy["fbiq_publish"]
    frame = enemy["frame_render_impl"]
    return [
        "set pagination off",
        "set confirm off",
        f"target remote :{port}",
        f"set $bug008_stage_count = 0",
        f"set $bug008_fb_count = 0",
        f"set $bug008_publish_count = 0",
        f"set $bug008_frame_count = 0",
        f"break *0x{presentation['pft_ready']}",
        "commands 1",
        "silent",
        f"set {{unsigned char}}0x{PRES_EVENT:04x} = 0x02",
        "printf \"BUG008_CREDIT_EVENT event=%02x\\n\", *(unsigned char*)0x00a9",
        "disable 1",
        "continue",
        "end",
        f"break *0x{presentation['pft_mode']}",
        "commands 2",
        "silent",
        f"set {{unsigned char}}0x{PRES_CREDITS:04x} = 0x01",
        f"set {{unsigned char}}0x{PRES_EVENT:04x} = 0x01",
        "printf \"BUG008_START_EVENT credits=%02x event=%02x\\n\", *(unsigned char*)0x00a8, *(unsigned char*)0x00a9",
        "disable 2",
        "continue",
        "end",
        f"break *0x{stage}",
        "commands 3",
        "silent",
        "if $bug008_stage_count == 0",
        f"printf \"BUG008_ENEMY_STAGE x=%04x entity=%02x dp=%02x\\n\", $x, *(unsigned char*)0x{ENTITY_COUNT:04x}, $dp",
        "else",
        f"printf \"BUG008_PLAYER_STAGE x=%04x entity=%02x dp=%02x\\n\", $x, *(unsigned char*)0x{ENTITY_COUNT:04x}, $dp",
        "end",
        "set $bug008_stage_count = $bug008_stage_count + 1",
        "if $bug008_stage_count >= 2",
        "disable 3",
        "end",
        "continue",
        "end",
        f"break *0x{framebuffer}",
        "commands 4",
        "silent",
        "if $bug008_fb_count == 0",
        f"printf \"BUG008_ENEMY_FB x=%04x entity=%02x dp=%02x\\n\", $x, *(unsigned char*)0x{ENTITY_COUNT:04x}, $dp",
        "else",
        f"printf \"BUG008_PLAYER_FB x=%04x entity=%02x dp=%02x\\n\", $x, *(unsigned char*)0x{ENTITY_COUNT:04x}, $dp",
        "end",
        "set $bug008_fb_count = $bug008_fb_count + 1",
        "if $bug008_fb_count >= 2",
        "disable 4",
        "end",
        "continue",
        "end",
        f"break *0x{publish}",
        "commands 5",
        "silent",
        f"printf \"BUG008_PUBLISH front=%02x back=%02x pending=%02x fault=%02x s=%04x\\n\", *(unsigned char*)0x008f, *(unsigned char*)0x0090, *(unsigned char*)0x0091, *(unsigned char*)0x0099, $s",
        "set $bug008_publish_count = $bug008_publish_count + 1",
        "if $bug008_stage_count >= 2 && $bug008_fb_count >= 2",
        "printf \"BUG008_COMPLETE\\n\"",
        "disable 5",
        "detach",
        "quit",
        "end",
        "continue",
        "end",
        f"break *0x{frame}",
        "commands 6",
        "silent",
        "set $bug008_frame_count = $bug008_frame_count + 1",
        "if $bug008_frame_count > 1",
        "printf \"BUG008_FRAME_ENTRY count=%d s=%04x entity=%02x\\n\", $bug008_frame_count, $s, *(unsigned char*)0x0032",
        "end",
        "continue",
        "end",
        "continue",
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--map", type=Path, required=True)
    parser.add_argument("--enemy-map", type=Path, required=True)
    parser.add_argument("--presentation-map", type=Path, required=True)
    parser.add_argument("--xroar", default="/usr/local/bin/xroar")
    parser.add_argument("--gdb", default="m6809-gdb")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument("--loader-timeout", type=int, default=10)
    parser.add_argument("--resident-timeout", type=int, default=10)
    args = parser.parse_args()

    if shutil.which(args.gdb) is None:
        raise SystemExit(f"BUG-008: GDB executable not found: {args.gdb}")
    root = Path(__file__).resolve().parents[1]
    main_map = args.map.read_text(encoding="utf-8")
    enemy_map = args.enemy_map.read_text(encoding="utf-8")
    presentation_map = args.presentation_map.read_text(encoding="utf-8")
    presentation = {
        name: symbol(presentation_map, name)
        for name in ("pft_ready", "pft_mode")
    }
    enemy = {
        name: symbol(enemy_map, name)
        for name in (
            "sparse_blit_stage",
            "sparse_blit_fb",
            "fbiq_publish",
            "frame_render_impl",
        )
    }
    source = (root / "src/enemy_runtime.s").read_text(encoding="utf-8")
    for label in ("sparse_enemy_stream", "sparse_player_stream"):
        body = source.split(label, 1)[1].split("\n\n", 1)[0]
        if "tfr     d,x" in body or "tfr     x,d" in body:
            raise SystemExit(f"BUG-008: {label} still overwrites caller X")

    startup_symbols = {
        name: symbol(main_map, name)
        for name in (
            "startup_par_setup_entry",
            "startup_init1_complete",
            "startup_par_table_ready",
            "startup_par_register_base",
            "startup_par_count_ready",
            "startup_par_write_complete",
            "startup_par_setup_complete",
            "startup_video_setup_entry",
            "startup_mmu_enable",
            "startup_mmu_enabled",
            "startup_palette_entry",
            "startup_palette_complete",
            "startup_clear_entry",
            "startup_clear_complete",
            "startup_fb_init_entry",
            "startup_complete",
        )
    }
    rom = args.rom.read_bytes()
    handoff = handoff_address(rom[:0x4000])
    process, port, startup_text, ready = gmc.run_startup_phases(
        args.xroar,
        args.gdb,
        args.rom,
        0,
        handoff,
        "BUG008",
        startup_symbols,
        args.loader_timeout,
        args.resident_timeout,
    )
    try:
        if not ready:
            print(startup_text)
            raise SystemExit("BUG-008: loader/resident startup did not reach handoff")
        runtime_text = bounded_gdb(
            args.gdb,
            trace_commands(port, presentation, enemy),
            root,
            args.timeout,
        )
        output = startup_text + "\n" + runtime_text
        print(output)
        required = (
            "BUG008_CREDIT_EVENT",
            "BUG008_START_EVENT",
            "BUG008_ENEMY_STAGE",
            "BUG008_PLAYER_STAGE",
            "BUG008_ENEMY_FB",
            "BUG008_PLAYER_FB",
            "BUG008_PUBLISH",
            "BUG008_COMPLETE",
        )
        missing = [marker for marker in required if marker not in output]
        if missing:
            raise SystemExit("BUG-008: missing markers: " + ", ".join(missing))
        for label in ("ENEMY_STAGE", "PLAYER_STAGE"):
            match = re.search(rf"BUG008_{label} x=([0-9a-fA-F]+) entity=([0-9a-fA-F]+)", output)
            if not match or not STAGE_DESTINATION <= int(match.group(1), 16) < STAGE_DESTINATION + 0x80:
                raise SystemExit(f"BUG-008: {label} destination or trace is invalid")
            if int(match.group(2), 16) != 8:
                raise SystemExit(f"BUG-008: {label} changed ENTITY_COUNT")
        for label in ("ENEMY_FB", "PLAYER_FB"):
            match = re.search(rf"BUG008_{label} x=([0-9a-fA-F]+) entity=([0-9a-fA-F]+)", output)
            if not match or not 0x4000 <= int(match.group(1), 16) < 0xC000:
                raise SystemExit(f"BUG-008: {label} destination is outside framebuffer range")
            if int(match.group(2), 16) != 8:
                raise SystemExit(f"BUG-008: {label} changed ENTITY_COUNT")
        for match in re.finditer(r"BUG008_PUBLISH .* fault=([0-9a-fA-F]+)", output):
            if int(match.group(1), 16) != 0:
                raise SystemExit("BUG-008: front-write fault was reported")
        print("BUG-008 focused live-start proof: PASS")
    finally:
        gmc.stop_process(process)
        process.wait()


if __name__ == "__main__":
    main()
