#!/usr/bin/env python3
"""Run a bounded headless XRoar trace and verify the GMC loader handoff."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path


NATURAL_TRACE_SECONDS = 30
FORCED_GAMEPLAY_SECONDS = 45
FORCED_DEMO_SECONDS = 30
FORCED_GAMEPLAY_MASK = 0x3F


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--xroar", default="/usr/local/bin/xroar")
    parser.add_argument("--gdb", default="m6809-gdb")
    parser.add_argument(
        "--gdb-port",
        type=int,
        default=0,
        help="GDB stub port; choose a free local port when omitted",
    )
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--map", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()

    map_text = args.map.read_text(encoding="utf-8")
    match = re.search(r"^Symbol: mainloop .* = ([0-9A-Fa-f]+)$", map_text, re.M)
    if not match:
        raise SystemExit("gmc proof: mainloop missing from map")
    mainloop = match.group(1).lower()
    rom = args.rom.read_bytes()
    boot = rom[:0x4000]
    manifest = json.loads(args.manifest.read_text(encoding="ascii"))
    manifest_segments = manifest["gmc"]["segments"]
    expected_source_banks = {
        f"{segment['bank']:02x}" for segment in manifest_segments
    }
    digest = lambda data: hashlib.sha256(data).hexdigest()
    if manifest["gmc"]["final_bank0_sha256"] != digest(boot):
        raise SystemExit("gmc proof: final bank-0 hash differs from manifest")
    if manifest["gmc"]["bank1_sha256"] != digest(rom[0x4000:0x8000]):
        raise SystemExit("gmc proof: bank-1 hash differs from manifest")
    if manifest["gmc"]["final_image_sha256"] != digest(rom):
        raise SystemExit("gmc proof: final image hash differs from manifest")
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
    presentation_map = (
        Path(__file__).resolve().parents[1] / "build/ladybug-presentation-runtime.map"
    ).read_text(encoding="utf-8")
    presentation_entry = re.search(
        r"^Symbol: presentation_flow_tick .* = ([0-9A-Fa-f]+)$",
        presentation_map,
        re.MULTILINE,
    )
    if not presentation_entry or presentation_entry.group(1).lower() != "1900":
        raise SystemExit("gmc proof: presentation entry is not assembled at $1900")
    presentation_symbols = {}
    for name in ("demo_force_death",):
        symbol = re.search(
            rf"^Symbol: {name} .* = ([0-9A-Fa-f]+)$",
            presentation_map,
            re.MULTILINE,
        )
        if not symbol:
            raise SystemExit(f"gmc proof: presentation symbol missing: {name}")
        presentation_symbols[name] = symbol.group(1).lower()
    presentation_module = (
        Path(__file__).resolve().parents[1] / "build/ladybug-presentation-runtime.bin"
    ).read_bytes()
    if not presentation_module or presentation_module[0] != 0x17:
        raise SystemExit(
            "gmc proof: presentation module at $1900 does not begin with executable LBSR"
        )
    damage_symbols = {}
    for name in (
        "actor_closure_restore",
        "actor_closure_draw",
        "framebuffer_queue_damage",
        "framebuffer_project_damage",
        "sparse_blit_fb",
        "sparse_blit_stage",
        "fbiq_publish",
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

    natural_command = [
        "timeout", str(NATURAL_TRACE_SECONDS), args.xroar,
        "-ui", "null", "-ao", "null",
        "-machine", "coco3", "-ram", "512",
        "-cart-type", "gmc", "-cart-rom", str(args.rom),
        "-cart-autorun", "-no-ratelimit", "-trace",
    ]
    with tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as trace:
        subprocess.run(
            natural_command,
            stdout=trace,
            stderr=subprocess.STDOUT,
            check=False,
        )
        trace.seek(0)
        natural_text = trace.read()

    sparse_bank_writes = re.findall(
        rf"^{bank_writes[3]}\| b7ff50 .* a=([0-9a-f]{{2}}) ",
        natural_text,
        re.MULTILINE,
    )
    sparse_page_writes = re.findall(
        r"^[0-9a-f]{4}\| b7ffa5 .* a=(35|36|37|39) ",
        natural_text,
        re.MULTILINE,
    )
    low_ram_proof = (
        # XRoar reports registers after STA ,Y+, so Y is one byte beyond
        # the address written on each trace line.
        re.search(r"^[0-9a-f]{4}\| a7a0 .* a=b0 .* y=06b1 ", natural_text, re.MULTILINE)
        and re.search(r"^[0-9a-f]{4}\| a7a0 .* a=0f .* y=06b2 ", natural_text, re.MULTILINE)
    )
    natural_required = {
        "bank 2 signature": f"{bank2_signature}| fcc010" in natural_text and "a=b2 b=02" in natural_text,
        "bank 3 signature": f"{bank3_signature}| fcc010" in natural_text and "a=b3 b=03" in natural_text,
        "bank-3 module selected": f"{bank_writes[2]}| b7ff50" in natural_text,
        "generated sparse source segments selected": (
            len(sparse_bank_writes) == expected_sparse_segments and
            set(sparse_bank_writes) == expected_source_banks
        ),
        "bank-0 overflow source selected": "00" in sparse_bank_writes,
        "bank-0 low-RAM proof copied": bool(low_ram_proof),
        "sparse destination pages selected": set(sparse_page_writes) == {"35", "36", "37", "39"},
        "runtime bank selected": f"{bank_writes[4]}| b7ff50" in natural_text,
        "all-RAM handoff": f"{allram}| b7ffdf" in natural_text,
        "bank-3 module payload": rom[0xC800:0xC80C] != bytes((0xA3,)) * 12,
        "bank-2 sparse payload": rom[0x8020:0x9E00] != bytes((0xA2,)) * 0x1DE0,
        "enemy module entered": "0800| 7e" in natural_text,
        "frame renderer ABI entered": f"0818| {frame_entry.hex()}" in natural_text,
        "central frame renderer entered": f"{frame_target}|" in natural_text,
        "ownership init ABI entered": f"081b| {ownership_entry.hex()}" in natural_text,
        "ownership init entered": f"{ownership_target}| 0f8f" in natural_text,
        "Vbord commit ABI entered": f"081e| {commit_entry.hex()}" in natural_text,
        "Vbord commit handler entered": f"{commit_target}|" in natural_text,
        "runtime main loop": natural_text.count(f"{mainloop}| 13") >= 1,
        "presentation module entered": "1900| 17" in natural_text,
    }
    forced_text = run_forced_gameplay_probe(
        args.xroar,
        args.gdb,
        args.rom,
        args.gdb_port,
        damage_symbols,
        presentation_entry.group(1),
    )
    demo_text = run_forced_demo_death_probe(
        args.xroar,
        args.gdb,
        args.rom,
        args.gdb_port,
        presentation_entry.group(1),
        presentation_symbols,
    )
    forced_required = {
        "damage queue entered": "FORCED_HIT framebuffer_queue_damage" in forced_text,
        "damage projection entered": "FORCED_HIT framebuffer_project_damage" in forced_text,
        "actor closure restore entered": "FORCED_HIT actor_closure_restore" in forced_text,
        "actor closure draw entered": "FORCED_HIT actor_closure_draw" in forced_text,
        "sparse framebuffer decoder entered": "FORCED_HIT sparse_blit_fb" in forced_text,
        "sparse stage decoder entered": "FORCED_HIT sparse_blit_stage" in forced_text,
        "Vbord display owners alternate": "FORCED_COMMIT_ALTERNATES" in forced_text,
        "forced gameplay completion": "FORCED_COMPLETE" in forced_text,
        "forced skull demo death": "DEMO_SKULL_FORCED" in demo_text,
        "forced enemy demo death": "DEMO_ENEMY_FORCED" in demo_text,
    }
    required = {**natural_required, **forced_required}
    failed = [name for name, passed in required.items() if not passed]
    if failed:
        raise SystemExit("gmc proof failed: " + ", ".join(failed))
    print(
        "gmc proof: natural boot/attract flow and forced gameplay phase verified "
        "segmented sparse payload load, bank-3 module, bank-1 load, sparse runtime "
        "decoders, TY=1 handoff, A/B ownership init, actor closure, Vbord commit "
        "entry, and relocated main loop"
    )


def free_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def run_forced_demo_death_probe(
    xroar: str,
    gdb: str,
    rom: Path,
    requested_port: int,
    presentation_entry: str,
    presentation_symbols: dict[str, str],
) -> str:
    """Run two demo cycles, selecting skull then enemy termination."""
    if shutil.which(gdb) is None:
        raise SystemExit(f"gmc proof: GDB executable not found: {gdb}")
    port = requested_port or free_local_port()
    xroar_process = subprocess.Popen(
        [
            xroar,
            "-ui", "null", "-ao", "null",
            "-machine", "coco3", "-ram", "512",
            "-cart-type", "gmc", "-cart-rom", str(rom),
            "-cart-autorun", "-no-ratelimit",
            "-gdb", "-gdb-ip", "127.0.0.1", "-gdb-port", str(port),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(4.0)
        demo_entry = presentation_symbols["demo_force_death"]
        commands = [
            "target remote :%d" % port,
            f"break *0x{presentation_entry}",
            "commands 1",
            "silent",
            "set {unsigned char}0x00a4 = 0xa5",
            "set {unsigned char}0x00a5 = 0x06",
            "set {unsigned char}0x00a7 = 0x00",
            "set {unsigned char}0x00b0 = 0x00",
            "set {unsigned char}0x00b1 = 0xb4",
            "set {unsigned char}0x00d1 = 0x02",
            "set {unsigned char}0x004d = 0x00",
            "disable 1",
            "continue",
            "end",
            "set $demo_mask = 0",
            f"break *0x{demo_entry}",
            "commands 2",
            "silent",
            "if $demo_mask == 0",
            'printf "DEMO_SKULL_FORCED\\n"',
            "set $demo_mask = 1",
            "set {unsigned char}0x00a5 = 0x06",
            "set {unsigned char}0x00a7 = 0x00",
            "set {unsigned char}0x00b0 = 0x00",
            "set {unsigned char}0x00b1 = 0xb4",
            "set {unsigned char}0x00d1 = 0x00",
            "set {unsigned char}0x004d = 0x00",
            "continue",
            "else",
            'printf "DEMO_ENEMY_FORCED\\n"',
            "set $demo_mask = 3",
            "detach",
            "quit",
            "end",
            "end",
            "continue",
        ]
        result = subprocess.run(
            [gdb, "-q"],
            input="\n".join(commands) + "\n",
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=rom.parent.parent,
            timeout=FORCED_DEMO_SECONDS,
            check=False,
        )
        return result.stdout
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout or ""
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
        return output
    finally:
        xroar_process.terminate()
        try:
            xroar_process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            xroar_process.kill()
            xroar_process.wait()


def run_forced_gameplay_probe(
    xroar: str,
    gdb: str,
    rom: Path,
    requested_port: int,
    symbols: dict[str, str],
    presentation_entry: str,
) -> str:
    """Force live gameplay after natural boot and collect required path hits."""
    if shutil.which(gdb) is None:
        raise SystemExit(f"gmc proof: GDB executable not found: {gdb}")
    port = requested_port or free_local_port()
    xroar_process = subprocess.Popen(
        [
            xroar,
            "-ui", "null", "-ao", "null",
            "-machine", "coco3", "-ram", "512",
            "-cart-type", "gmc", "-cart-rom", str(rom),
            "-cart-autorun", "-no-ratelimit",
            "-gdb", "-gdb-ip", "127.0.0.1", "-gdb-port", str(port),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        # The XRoar stub binds during startup. Do not connect-probe it; the
        # documented stub treats a probe connect followed by close as a
        # degraded session. GDB performs the first connection below.
        time.sleep(4.0)
        breakpoint_specs = [
            ("actor_closure_restore", 0x01),
            ("framebuffer_queue_damage", 0x02),
            ("framebuffer_project_damage", 0x04),
            ("sparse_blit_stage", 0x08),
            ("actor_closure_draw", 0x10),
            ("sparse_blit_fb", 0x20),
        ]
        commands = [
            "target remote :%d" % port,
            f"break *0x{presentation_entry}",
            "commands 1",
            "silent",
            "set {unsigned char}0x00a4 = 0xa5",
            "set {unsigned char}0x00a5 = 0x06",
            "set {unsigned char}0x00a7 = 0x01",
            "set {unsigned char}0x00b0 = 0x00",
            "set {unsigned char}0x00b1 = 0xb4",
            "set {unsigned char}0x004d = 0x00",
            "disable 1",
            "continue",
            "end",
            "set $gmc_mask = 0",
            "set $gmc_commit_count = 0",
            "set $gmc_commit_bad = 0",
            "set $gmc_last_owner = 0",
        ]
        for breakpoint_number, (name, bit) in enumerate(breakpoint_specs, start=2):
            commands += [
                f"break *0x{symbols[name]}",
                f"commands {breakpoint_number}",
                "silent",
                f'printf "FORCED_HIT {name}\\n"',
                f"set $gmc_mask = $gmc_mask | {bit}",
                f"disable {breakpoint_number}",
                f"if $gmc_mask == {FORCED_GAMEPLAY_MASK}",
                'printf "FORCED_COMPLETE\\n"',
                "detach",
                "quit",
                "end",
                "continue",
                "end",
            ]
        commit_breakpoint = len(breakpoint_specs) + 2
        completion_breakpoint = commit_breakpoint + 1
        commands += [
            f"break *0x{symbols['fbiq_publish']}",
            f"commands {commit_breakpoint}",
            "silent",
            'printf "FORCED_COMMIT %x\\n", $a',
            "if $gmc_commit_count > 0",
            "if $a == $gmc_last_owner",
            "set $gmc_commit_bad = 1",
            "end",
            "end",
            "set $gmc_last_owner = $a",
            "set $gmc_commit_count = $gmc_commit_count + 1",
            "if $gmc_commit_count >= 4",
            "if $gmc_commit_bad == 0",
            'printf "FORCED_COMMIT_ALTERNATES\\n"',
            "end",
            "end",
            "continue",
            "end",
            f"break *0x{presentation_entry} if $gmc_mask == {FORCED_GAMEPLAY_MASK} && $gmc_commit_count >= 4 && $gmc_commit_bad == 0",
            f"commands {completion_breakpoint}",
            "silent",
            'printf "FORCED_COMPLETE\\n"',
            "detach",
            "quit",
            "end",
        ]
        commands.append("continue")
        result = subprocess.run(
            [gdb, "-q"],
            input="\n".join(commands) + "\n",
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=rom.parent.parent,
            timeout=FORCED_GAMEPLAY_SECONDS,
            check=False,
        )
        return result.stdout
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout or ""
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
        return output
    finally:
        xroar_process.terminate()
        try:
            xroar_process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            xroar_process.kill()
            xroar_process.wait()


if __name__ == "__main__":
    main()
