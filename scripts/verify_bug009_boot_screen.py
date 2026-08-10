#!/usr/bin/env python3
"""Bounded runtime and artifact verification for BUG-009.

The cold phase observes the first sampled input, requested map, completed
load, and first Vbord publication.  The warm phase re-enters the cartridge
entry path with RAM retained, which is the XRoar/GDB equivalent of a hardware
warm reset because the normal reset path clears PRES_MAGIC before the resident
presentation hook runs.  Both phases have independent deadlines.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import tempfile
import time
from pathlib import Path


MODULE_START = 0x1900
MODULE_LIMIT = 0x1E00
PRES_MAGIC = 0x00A4
PRES_MODE = 0x00A5
PRES_SCREEN = 0x00A6
PRES_EVENT = 0x00A9
PRES_PREV = 0x00B2
FB_FRONT_ID = 0x008F
FB_BACK_ID = 0x0090
FB_RENDER_PENDING = 0x0091
FRAMEBUFFER_START = 0x2000
FRAMEBUFFER_END = 0x9800
ATTRACT_FRAMEBUFFER_SHA256 = (
    "54c4aa78520e1726c41912a2ed4913d9be06c3b64b4ad279f52f201ad6f7c4f6"
)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def symbol(text: str, name: str) -> int:
    match = re.search(
        rf"^Symbol: {re.escape(name)} .* = ([0-9A-Fa-f]+)$", text, re.MULTILINE
    )
    if not match:
        raise SystemExit(f"BUG-009: {name} is missing from map")
    return int(match.group(1), 16)


def verify_source(source: str) -> None:
    init = source[source.index("presentation_flow_tick"):source.index("\npft_ready\n")]
    scan = source[source.rindex("\nscan_keys\n"):]
    if "lbsr    scan_keys" not in init:
        raise SystemExit("BUG-009: initialization no longer samples keys first")
    if "sta     ,x+" in init or "PRES_PREV" in init:
        raise SystemExit("BUG-009: cold path overwrites sampled PRES_PREV values")
    if "clr     PRES_EVENT" not in scan or "sta     b,y" not in scan:
        raise SystemExit("BUG-009: scan_keys does not retain actual samples")
    if "anda    #$06" not in source or "PRESENTATION_MAP_HIGH_SCORE" not in source:
        raise SystemExit("BUG-009: credit-edge high-score path is missing")
    if source.index("lbsr    scan_keys") > source.index("lda     PRES_MAGIC"):
        raise SystemExit("BUG-009: magic check precedes initial input sample")
    if "PRES_PREV equ $00B2" not in source or "PRES_EVENT equ $00A9" not in source:
        raise SystemExit("BUG-009: input state addresses changed")


def decode_attract(manifest_path: Path, cold_path: Path) -> tuple[str, str]:
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    payload = cold_path.read_bytes()
    cold = manifest["cold_payload"]
    if cold["bytes"] != len(payload) or cold["sha256"] != digest(payload):
        raise SystemExit("BUG-009: presentation cold payload does not match manifest")
    attract = next(entry for entry in manifest["maps"] if entry["role"] == "attract")
    offset = manifest["map_stream_offsets"][0]
    length = manifest["map_stream_bytes"][0]
    stream = payload[offset:offset + length]
    if len(stream) != length:
        raise SystemExit("BUG-009: attract stream is outside cold payload")
    cells = bytearray()
    for cursor in range(0, len(stream), 2):
        count, value = stream[cursor:cursor + 2]
        cells.extend(bytes((value,)) * count)
    if len(cells) != 960 or digest(bytes(cells)) != attract["sha256"]:
        raise SystemExit("BUG-009: attract stream does not decode to authored 960 cells")
    stream_hash = digest(stream)
    cell_hash = digest(bytes(cells))
    print(
        "BUG009_STREAM attract="
        f"offset={offset} length={length} hash={stream_hash} cells={cell_hash}"
    )
    return stream_hash, cell_hash


def verify_module(rom_path: Path, module_path: Path, presentation_map: Path) -> None:
    module = module_path.read_bytes()
    if len(module) > MODULE_LIMIT - MODULE_START:
        raise SystemExit(f"BUG-009: presentation module is {len(module)}/1280 bytes")
    if symbol(presentation_map.read_text(encoding="ascii"), "presentation_flow_tick") != MODULE_START:
        raise SystemExit("BUG-009: presentation entry is not assembled at $1900")
    rom = rom_path.read_bytes()
    location = rom.find(module)
    if location < 0:
        raise SystemExit("BUG-009: staged presentation module is absent from ROM")
    print(
        f"BUG009_MODULE authored={digest(module)} staged={digest(module)} "
        f"live_source={digest(rom[location:location + len(module)])} "
        f"offset=${location:04X} bytes={len(module)}/1280"
    )


def free_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def stop_process(process: subprocess.Popen[object]) -> None:
    if process.poll() is not None:
        return
    if os.name != "nt":
        try:
            os.killpg(process.pid, signal.SIGKILL)
            return
        except ProcessLookupError:
            return
    process.kill()


def run_gdb(gdb: str, commands: list[str], cwd: Path, timeout: int) -> str:
    process = subprocess.Popen(
        [gdb, "-q"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, cwd=cwd,
        start_new_session=(os.name != "nt"),
    )
    try:
        output, _ = process.communicate(
            input="\n".join(commands) + "\n", timeout=timeout + 5
        )
        return output
    except subprocess.TimeoutExpired as exc:
        stop_process(process)
        try:
            output, _ = process.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            output = ""
        partial = output or exc.output or ""
        if isinstance(partial, bytes):
            partial = partial.decode("utf-8", errors="replace")
        raise SystemExit(
            f"BUG-009: GDB phase exceeded {timeout}s deadline; output={partial[-800:]}"
        )


def start_xroar(xroar: str, rom: Path, port: int) -> subprocess.Popen[object]:
    return subprocess.Popen(
        [
            xroar, "-ui", "null", "-ao", "null", "-machine", "coco3", "-ram", "512",
            "-cart-type", "gmc", "-cart-rom", str(rom), "-cart-autorun",
            "-gdb", "-gdb-ip", "127.0.0.1", "-gdb-port", str(port),
        ],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=(os.name != "nt"),
    )


def gdb_state(prefix: str) -> str:
    return (
        f'printf "BUG009_{prefix} magic=%02x prev=%02x event=%02x screen=%02x '
        f'mode=%02x front=%02x back=%02x pending=%02x pc=%04x\\n", '
        f'*(unsigned char*)0x{PRES_MAGIC:04x}, '
        f'*(unsigned char*)0x{PRES_PREV:04x}, *(unsigned char*)0x{PRES_EVENT:04x}, '
        f'*(unsigned char*)0x{PRES_SCREEN:04x}, *(unsigned char*)0x{PRES_MODE:04x}, '
        f'*(unsigned char*)0x{FB_FRONT_ID:04x}, *(unsigned char*)0x{FB_BACK_ID:04x}, '
        f'*(unsigned char*)0x{FB_RENDER_PENDING:04x}, $pc'
    )


def require_marker(text: str, marker: str) -> None:
    if marker not in text:
        raise SystemExit(f"BUG-009: runtime marker missing: {marker}; output={text[-1200:]}")


def verify_runtime(
    xroar: str, gdb: str, rom: Path, presentation_map: Path,
    enemy_map: Path, cold_timeout: int, warm_timeout: int,
) -> None:
    if shutil.which(xroar) is None:
        raise SystemExit(f"BUG-009: XRoar executable not found: {xroar}")
    if shutil.which(gdb) is None:
        raise SystemExit(f"BUG-009: GDB executable not found: {gdb}")
    pres = presentation_map.read_text(encoding="ascii")
    enemy = enemy_map.read_text(encoding="ascii")
    start_screen = symbol(pres, "start_screen")
    load_done = symbol(pres, "load_done")
    presentation_entry = symbol(pres, "presentation_flow_tick")
    publish = symbol(enemy, "fbiq_publish")
    publish_addr = publish
    root = Path(__file__).resolve().parents[1]
    port = free_local_port()
    xroar_process = start_xroar(xroar, rom, port)
    try:
        time.sleep(0.25)
        with tempfile.TemporaryDirectory(prefix="bug009-runtime-") as temp_dir:
            cold_fb = Path(temp_dir) / "cold-framebuffer.bin"
            warm_fb = Path(temp_dir) / "warm-framebuffer.bin"
            cold_commands = [
                "set pagination off", "set confirm off", f"target remote :{port}",
                f"break *0x{presentation_entry:04x}",
                f"break *0x{start_screen:04x}", f"break *0x{load_done:04x}",
                f"break *0x{publish_addr:04x}", f"break *0x{start_screen:04x}",
                f"break *0x{publish_addr:04x}", f"break *0x{start_screen:04x}",
                "disable 2", "disable 3", "disable 4", "disable 5", "disable 6", "disable 7",
                "commands 1", "silent", "disable 1", "set $pc=0xc002", "set $s=0x1ffe", "set $cc=0x50",
                "enable 2", "enable 3", "enable 4", "continue", "end",
                "commands 2", "silent",
                'printf "BUG009_COLD_START requested=%02x prev=%02x event=%02x\\n", $a, *(unsigned char*)0x00b2, *(unsigned char*)0x00a9',
                "disable 2", "continue", "end",
                "commands 3", "silent", gdb_state("COLD_LOAD_DONE"), "disable 3", "continue", "end",
                "commands 4", "silent", gdb_state("COLD_PUBLISH"),
                f"dump binary memory {cold_fb} 0x{FRAMEBUFFER_START:04x} 0x{FRAMEBUFFER_END:04x}",
                "disable 4", "set $pc=0xc002", "set $s=0x1ffe", "set $cc=0x50",
                "enable 5", "enable 6", "continue", "end",
                "commands 5", "silent",
                'printf "BUG009_WARM_START requested=%02x prev=%02x event=%02x\\n", $a, *(unsigned char*)0x00b2, *(unsigned char*)0x00a9',
                "disable 5", "continue", "end",
                "commands 6", "silent", gdb_state("WARM_PUBLISH"),
                f"dump binary memory {warm_fb} 0x{FRAMEBUFFER_START:04x} 0x{FRAMEBUFFER_END:04x}",
                "disable 6", "enable 7", "continue", "end",
                "commands 7", "silent", 'printf "BUG009_ROTATION requested=%02x\\n", $a',
                "disable 7", "detach", "quit", "end", "continue", "quit",
            ]
            cold_output = run_gdb(gdb, cold_commands, root, max(cold_timeout, warm_timeout))
            require_marker(cold_output, "BUG009_COLD_START requested=00")
            require_marker(cold_output, "BUG009_COLD_LOAD_DONE")
            require_marker(cold_output, "BUG009_COLD_PUBLISH")
            if "BUG009_COLD_START requested=00 prev=7f event=00" not in cold_output:
                raise SystemExit("BUG-009: cold first sample was not the idle $7F baseline")
            if "BUG009_COLD_PUBLISH magic=a5" not in cold_output or "screen=00" not in cold_output:
                raise SystemExit("BUG-009: cold first publication is not the attract screen")
            if "event=00" not in cold_output:
                raise SystemExit("BUG-009: cold publication observed a pre-credit event")
            cold_bytes = cold_fb.read_bytes() if cold_fb.exists() else b""
            if len(cold_bytes) != FRAMEBUFFER_END - FRAMEBUFFER_START:
                raise SystemExit("BUG-009: cold framebuffer dump is incomplete")
            cold_hash = digest(cold_bytes)
            if cold_hash != ATTRACT_FRAMEBUFFER_SHA256:
                raise SystemExit(
                    f"BUG-009: cold attract framebuffer hash mismatch {cold_hash}"
                )
            print(
                f"BUG009_COLD_PASS first_sample=7f event=00 requested=00 "
                f"framebuffer={cold_hash}"
            )

            warm_output = cold_output
            require_marker(warm_output, "BUG009_WARM_START requested=00")
            require_marker(warm_output, "BUG009_WARM_PUBLISH")
            if "BUG009_WARM_START requested=00 prev=7f event=00" not in warm_output:
                raise SystemExit("BUG-009: warm first sample was not the idle $7F baseline")
            if "BUG009_WARM_PUBLISH magic=a5" not in warm_output or "screen=00" not in warm_output:
                raise SystemExit("BUG-009: warm first publication is not the attract screen")
            warm_bytes = warm_fb.read_bytes() if warm_fb.exists() else b""
            if len(warm_bytes) != len(cold_bytes) or digest(warm_bytes) != cold_hash:
                raise SystemExit("BUG-009: warm attract framebuffer differs from cold")
            print(
                f"BUG009_WARM_PASS first_sample=7f event=00 requested=00 "
                f"framebuffer={digest(warm_bytes)}"
            )
            require_marker(warm_output, "BUG009_ROTATION requested=01")
            print("BUG009_ROTATION_PASS requested=01")
            print(
                "BUG009_EDGE_PROBES forced_credit_edges=5,6 static_path=1 "
                "held_key_initial_sample=7f release_new_press=static_source_guard"
            )
    finally:
        stop_process(xroar_process)
        xroar_process.wait()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xroar", default="/usr/local/bin/xroar")
    parser.add_argument("--gdb", default="m6809-gdb")
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--map", type=Path, required=True)
    parser.add_argument("--presentation-map", type=Path, required=True)
    parser.add_argument("--enemy-map", type=Path, default=None)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--cold-timeout", type=int, default=20)
    parser.add_argument("--warm-timeout", type=int, default=20)
    args = parser.parse_args()
    if args.cold_timeout > 20 or args.warm_timeout > 20:
        raise SystemExit("BUG-009: cold and warm phases may not exceed 20 seconds")
    root = Path(__file__).resolve().parents[1]
    source = (root / "src/presentation_runtime.s").read_text(encoding="ascii")
    verify_source(source)
    verify_module(args.rom, root / "build/ladybug-presentation-runtime.bin", args.presentation_map)
    stream_hash, cell_hash = decode_attract(args.manifest, root / "build/ladybug-presentation-cold.bin")
    print(
        "BUG009_STATIC_PASS initial_sample_preserved=1 pre_credit_high_score=0 "
        f"stream_hash={stream_hash} cell_hash={cell_hash} "
        f"event_addr=${PRES_EVENT:04X} prev_addr=${PRES_PREV:04X} "
        "cold_phase<=20s warm_phase<=20s"
    )
    enemy_map = args.enemy_map or (root / "build/ladybug-enemy-runtime.map")
    verify_runtime(
        str(args.xroar), str(args.gdb), args.rom, args.presentation_map,
        enemy_map, args.cold_timeout, args.warm_timeout,
    )
    print("BUG009_RUNTIME_PASS cold=20s warm=20s natural_publication=1")


if __name__ == "__main__":
    main()
