#!/usr/bin/env python3
"""Run bounded XRoar/GDB boot, natural, forced-gameplay, and demo phases."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path


BOOT_PHASE_SECONDS = 10
RESIDENT_STARTUP_PHASE_SECONDS = 10
NATURAL_PHASE_SECONDS = 10
FORCED_GAMEPLAY_SECONDS = 20
FORCED_DEMO_SECONDS = 10
FORCED_GAMEPLAY_MASK = 0x3F


def map_symbol(map_text: str, name: str) -> str:
    match = re.search(
        rf"^Symbol: {re.escape(name)} .* = ([0-9A-Fa-f]+)$",
        map_text,
        re.M,
    )
    if not match:
        raise SystemExit(f"gmc proof: {name} missing from map")
    return match.group(1).lower()


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
    parser.add_argument(
        "--loader-timeout", "--boot-timeout", dest="loader_timeout",
        type=int, default=BOOT_PHASE_SECONDS,
        help="loader-to-handoff deadline in seconds",
    )
    parser.add_argument(
        "--resident-timeout", type=int, default=RESIDENT_STARTUP_PHASE_SECONDS,
        help="handoff-to-resident-startup deadline in seconds",
    )
    parser.add_argument("--natural-timeout", type=int, default=NATURAL_PHASE_SECONDS)
    parser.add_argument("--forced-timeout", type=int, default=FORCED_GAMEPLAY_SECONDS)
    parser.add_argument("--demo-timeout", type=int, default=FORCED_DEMO_SECONDS)
    parser.add_argument(
        "--startup-only",
        action="store_true",
        help="run one bounded loader/resident startup diagnosis and stop",
    )
    parser.add_argument(
        "--startup-snapshot",
        action="store_true",
        help="capture CPU registers at PAR setup markers; implies startup-only",
    )
    args = parser.parse_args()

    map_text = args.map.read_text(encoding="utf-8")
    mainloop = map_symbol(map_text, "mainloop")
    startup_symbols = {
        name: map_symbol(map_text, name)
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
    for name in ("demo_force_death", "demo_force_enemy_death"):
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
    if "jmp     $C002" not in loader_source:
        raise SystemExit("gmc proof: relocated runtime handoff must skip the DK header")
    if "copy_enemy_sparse_index" in loader_source or "copy_player_sparse_index" in loader_source:
        raise SystemExit("gmc proof: sparse indexes must not overwrite the relocated loader")
    if "RESIDENT_STAGE_PAGE equ $21" not in loader_source:
        raise SystemExit("gmc proof: resident staging page is not $21")
    if "ASSET_STAGE_PAGE equ $22" not in loader_source:
        raise SystemExit("gmc proof: asset staging page is not $22")
    if loader_source.index("sta     SAM_ALLRAM") > loader_source.index(
        "copy_staged_resident"
    ):
        raise SystemExit("gmc proof: resident publication precedes all-RAM")
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
    bank_write_positions = []
    cursor = loader_start
    while True:
        cursor = boot.find(bytes((0xB7, 0xFF, 0x50)), cursor)
        if cursor < 0:
            break
        bank_write_positions.append(0x0300 + cursor - loader_start)
        cursor += 1
    bank_writes = [f"{position:04x}" for position in bank_write_positions]
    if len(bank_writes) < 5:
        raise SystemExit("gmc proof: expected five loader bank writes")
    bank2_signature = relocated_pc(bytes((0xFC, 0xC0, 0x10)), 0)
    bank3_signature = relocated_pc(bytes((0xFC, 0xC0, 0x10)), 1)
    allram = relocated_pc(bytes((0xB7, 0xFF, 0xDF)))
    handoff_offset = boot.find(bytes((0x7E, 0xC0, 0x02)), loader_start)
    if handoff_offset < 0:
        raise SystemExit("gmc proof: relocated runtime handoff opcode missing")
    handoff = f"{0x0300 + handoff_offset - loader_start:04x}"
    par5_positions = []
    cursor = loader_start
    while True:
        cursor = boot.find(bytes((0xB7, 0xFF, 0xA5)), cursor)
        if cursor < 0:
            break
        par5_positions.append(f"{0x0300 + cursor - loader_start:04x}")
        cursor += 1
    sparse_store_offset = boot.find(bytes((0xED, 0xA1)),
                                     loader_start + bank_write_positions[3] - 0x0300 + 1)
    if sparse_store_offset < 0:
        raise SystemExit("gmc proof: sparse-copy store opcode missing")
    sparse_store = f"{0x0300 + sparse_store_offset - loader_start:04x}"
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

    if args.startup_only or args.startup_snapshot:
        xroar_process, _port, startup_text, startup_ready = run_startup_phases(
            args.xroar,
            args.gdb,
            args.rom,
            args.gdb_port,
            handoff,
            "STARTUP",
            startup_symbols,
            args.loader_timeout,
            args.resident_timeout,
            args.startup_snapshot,
        )
        try:
            print(startup_text)
            print(phase_summary("startup", startup_text))
            if not startup_ready:
                raise SystemExit("gmc startup diagnosis: resident startup incomplete")
            print("gmc startup diagnosis: resident startup completed")
            return
        finally:
            stop_process(xroar_process)
            xroar_process.wait()

    print("gmc phase: natural boot and attract", flush=True)
    natural_text = run_natural_phase(
        args.xroar,
        args.gdb,
        args.rom,
        args.gdb_port,
        handoff,
        startup_symbols,
        bank_writes,
        bank2_signature,
        bank3_signature,
        allram,
        par5_positions,
        sparse_store,
        frame_target,
        ownership_target,
        commit_target,
        mainloop,
        args.loader_timeout,
        args.resident_timeout,
        args.natural_timeout,
    )
    natural_required = {
        "loader handoff": "NATURAL_LOADER_HANDOFF" in natural_text,
        "resident startup completion": (
            "NATURAL_RESIDENT_STARTUP_COMPLETE" in natural_text
        ),
        "bank-1 RAM exact": "NATURAL_BANK1_RAM_EXACT" in natural_text,
        "bank-3 module payload": rom[0xC800:0xC80C] != bytes((0xA3,)) * 12,
        "bank-2 sparse payload": rom[0x8020:0x9E00] != bytes((0xA2,)) * 0x1DE0,
        "runtime main loop": "NATURAL_MAINLOOP" in natural_text,
        "presentation module entered": "NATURAL_PRESENTATION" in natural_text,
    }
    print("gmc phase: forced gameplay", flush=True)
    forced_text = run_forced_gameplay_probe(
        args.xroar,
        args.gdb,
        args.rom,
        args.gdb_port,
        damage_symbols,
        presentation_entry.group(1),
        handoff,
        startup_symbols,
        args.loader_timeout,
        args.resident_timeout,
        args.forced_timeout,
    )
    print("gmc phase: forced demo deaths", flush=True)
    demo_text = run_forced_demo_death_probe(
        args.xroar,
        args.gdb,
        args.rom,
        args.gdb_port,
        presentation_entry.group(1),
        presentation_symbols,
        handoff,
        startup_symbols,
        args.loader_timeout,
        args.resident_timeout,
        args.demo_timeout,
    )
    forced_required = {
        "forced loader handoff": "FORCED_LOADER_HANDOFF" in forced_text,
        "forced resident startup completion": (
            "FORCED_RESIDENT_STARTUP_COMPLETE" in forced_text
        ),
        "damage queue entered": "FORCED_HIT framebuffer_queue_damage" in forced_text,
        "damage projection entered": "FORCED_HIT framebuffer_project_damage" in forced_text,
        "actor closure restore entered": "FORCED_HIT actor_closure_restore" in forced_text,
        "actor closure draw entered": "FORCED_HIT actor_closure_draw" in forced_text,
        "sparse framebuffer decoder entered": "FORCED_HIT sparse_blit_fb" in forced_text,
        "sparse stage decoder entered": "FORCED_HIT sparse_blit_stage" in forced_text,
        "Vbord commit entered with distinct owners": (
            "FORCED_COMMIT_OWNERS_DISTINCT" in forced_text
        ),
        "forced gameplay completion": "FORCED_COMPLETE" in forced_text,
        "forced skull demo death": "DEMO_SKULL_FORCED" in demo_text,
        "forced enemy demo death": "DEMO_ENEMY_FORCED" in demo_text,
        "demo loader handoff": "DEMO_LOADER_HANDOFF" in demo_text,
        "demo resident startup completion": (
            "DEMO_RESIDENT_STARTUP_COMPLETE" in demo_text
        ),
    }
    required = {**natural_required, **forced_required}
    failed = [name for name, passed in required.items() if not passed]
    if failed:
        raise SystemExit(
            "gmc proof failed: " + ", ".join(failed) + "; " +
            phase_summary("natural", natural_text) + "; " +
            phase_summary("forced", forced_text) + "; " +
            phase_summary("demo", demo_text)
        )
    print(
        "gmc proof: natural boot/attract flow and forced gameplay phase verified "
        "segmented sparse payload load, bank-3 module, bank-1 load, sparse runtime "
        "decoders, TY=1 handoff, A/B ownership init, actor closure, Vbord commit "
        "entry, and relocated main loop"
    )


def add_gdb_breakpoint(
    commands: list[str],
    number: int,
    address: str,
    body: list[str],
    keep_enabled: bool = False,
) -> int:
    commands.extend([
        f"break *0x{address}",
        f"commands {number}",
        "silent",
        *body,
    ])
    if not keep_enabled:
        commands.append(f"disable {number}")
    commands.extend(["continue", "end"])
    return number + 1


def phase_summary(name: str, output: str) -> str:
    markers = sorted({
        line.strip()
        for line in output.splitlines()
        if line.strip().startswith(("STARTUP_", "NATURAL_", "FORCED_", "DEMO_"))
    })
    return f"{name} markers=[{','.join(markers) if markers else 'none'}]"


def run_gdb_commands(
    gdb: str,
    commands: list[str],
    cwd: Path,
    timeout: int,
) -> str:
    """Run one GDB phase and guarantee child cleanup at its deadline."""
    input_text = "\n".join(commands) + "\n"
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
        output, _ = process.communicate(input=input_text, timeout=timeout + 15)
        return output
    except subprocess.TimeoutExpired as exc:
        stop_process(process)
        try:
            output, _ = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            output = ""
        partial = output or exc.output or ""
        if isinstance(partial, bytes):
            partial = partial.decode("utf-8", errors="replace")
        return partial


def stop_process(process: subprocess.Popen[object]) -> None:
    """Terminate a phase process and its POSIX process group."""
    if process.poll() is not None:
        return
    if os.name != "nt":
        try:
            os.killpg(process.pid, signal.SIGKILL)
            return
        except ProcessLookupError:
            return
    process.kill()


def start_xroar(
    command: list[str],
) -> subprocess.Popen[object]:
    return subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=(os.name != "nt"),
    )


def trace_loader_handoff(
    xroar: str, rom: Path, handoff: str, timeout: int, prefix: str
) -> str:
    """Observe the one-shot low-RAM handoff without racing GDB attachment."""
    process = subprocess.Popen(
        [
            xroar,
            "-ui", "null", "-ao", "null",
            "-machine", "coco3", "-ram", "512",
            "-cart-type", "gmc", "-cart-rom", str(rom),
            "-cart-autorun", "-no-ratelimit", "-trace",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=(os.name != "nt"),
    )
    deadline = time.monotonic() + timeout
    target = f"{handoff.lower()}|"
    try:
        while time.monotonic() < deadline:
            line = process.stdout.readline() if process.stdout else ""
            if line.lower().startswith(target):
                return f"{prefix}_BOOT_COMPLETE\n{prefix}_LOADER_HANDOFF\n"
            if not line and process.poll() is not None:
                break
        return ""
    finally:
        stop_process(process)
        process.wait()


def run_startup_phases(
    xroar: str,
    gdb: str,
    rom: Path,
    requested_port: int,
    handoff: str,
    prefix: str,
    startup_symbols: dict[str, str],
    loader_timeout: int,
    resident_timeout: int,
    startup_snapshot: bool = False,
) -> tuple[subprocess.Popen[object], int, str, bool]:
    """Run separately bounded loader-trace and resident-runtime phases."""
    if shutil.which(gdb) is None:
        raise SystemExit(f"gmc proof: GDB executable not found: {gdb}")
    loader_text = trace_loader_handoff(
        xroar, rom, handoff, loader_timeout, prefix
    )
    port = requested_port or free_local_port()
    xroar_process = start_xroar(
        [
            xroar,
            "-ui", "null", "-ao", "null",
            "-machine", "coco3", "-ram", "512",
            "-cart-type", "gmc", "-cart-rom", str(rom),
            "-cart-autorun", "-no-ratelimit",
            "-gdb", "-gdb-ip", "127.0.0.1", "-gdb-port", str(port),
        ],
    )
    # The resident proof targets the repeating presentation entry, avoiding
    # races against one-shot startup addresses while retaining a hard deadline.
    time.sleep(0.25)
    with tempfile.TemporaryDirectory(prefix="ladybug-gmc-") as temp_dir:
        bank1_dump = Path(temp_dir) / "bank1-runtime.bin"
        resident_commands = [
            "set pagination off",
            "set confirm off",
            "target remote :%d" % port,
            "break *0x1900",
            "continue",
            f'printf "{prefix}_RESIDENT_ENTRY\\n"',
            f'printf "{prefix}_RESIDENT_STARTUP_COMPLETE\\n"',
        ]
        if startup_snapshot:
            resident_commands.append(
                f'printf "{prefix}_RUNTIME_SNAPSHOT pc=%04x a=%02x b=%02x x=%04x y=%04x s=%04x dp=%02x cc=%02x\\n", $pc, $a, $b, $x, $y, $s, $dp, $cc'
            )
        resident_commands.extend([
            (
                f"dump binary memory {bank1_dump} "
                "0xc000 0xfe00"
            ),
            "detach",
            "quit",
        ])
        resident_text = run_gdb_commands(
            gdb, resident_commands, rom.parent.parent, resident_timeout
        )
        expected_bank1 = rom.read_bytes()[0x4000:0x7E00]
        actual_bank1 = bank1_dump.read_bytes() if bank1_dump.exists() else b""
        if actual_bank1 == expected_bank1:
            resident_text += f"\n{prefix}_BANK1_RAM_EXACT\n"
        else:
            resident_text += (
                f"\n{prefix}_BANK1_RAM_MISMATCH "
                f"expected={len(expected_bank1)} actual={len(actual_bank1)}\n"
            )
    texts = [loader_text, resident_text]
    return (
        xroar_process,
        port,
        "\n".join(texts),
        f"{prefix}_LOADER_HANDOFF" in loader_text and
        f"{prefix}_RESIDENT_STARTUP_COMPLETE" in resident_text and
        f"{prefix}_BANK1_RAM_EXACT" in resident_text,
    )


def run_natural_phase(
    xroar: str,
    gdb: str,
    rom: Path,
    requested_port: int,
    handoff: str,
    startup_symbols: dict[str, str],
    bank_writes: list[str],
    bank2_signature: str,
    bank3_signature: str,
    allram: str,
    par5_positions: list[str],
    sparse_store: str,
    frame_target: str,
    ownership_target: str,
    commit_target: str,
    mainloop: str,
    loader_timeout: int,
    resident_timeout: int,
    natural_timeout: int,
) -> str:
    """Run loader, resident-startup, then natural runtime markers."""
    xroar_process, port, startup_text, startup_ready = run_startup_phases(
        xroar,
        gdb,
        rom,
        requested_port,
        handoff,
        "NATURAL",
        startup_symbols,
        loader_timeout,
        resident_timeout,
    )
    try:
        if not startup_ready:
            return startup_text
        commands = [
            "set pagination off",
            "set confirm off",
            "target remote :%d" % port,
            f"break *0x{mainloop}",
            "continue",
            'printf "NATURAL_MAINLOOP\\n"',
            "disable 1",
            "break *0x1900",
            "continue",
            'printf "NATURAL_PRESENTATION\\n"',
            "detach",
            "quit",
        ]
        runtime_text = run_gdb_commands(
            gdb,
            commands,
            rom.parent.parent,
            natural_timeout,
        )
        return startup_text + "\n" + runtime_text
    finally:
        stop_process(xroar_process)
        xroar_process.wait()


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
    handoff: str,
    startup_symbols: dict[str, str],
    loader_timeout: int,
    resident_timeout: int,
    demo_timeout: int,
) -> str:
    """Run loader, resident-startup, then two demo death cycles."""
    xroar_process, port, startup_text, startup_ready = run_startup_phases(
        xroar,
        gdb,
        rom,
        requested_port,
        handoff,
        "DEMO",
        startup_symbols,
        loader_timeout,
        resident_timeout,
    )
    try:
        if not startup_ready:
            return startup_text
        demo_entry = presentation_symbols["demo_force_death"]
        enemy_entry = presentation_symbols["demo_force_enemy_death"]
        commands = [
            "set pagination off",
            "set confirm off",
            "target remote :%d" % port,
            f"break *0x{presentation_entry}",
            "continue",
            "disable 1",
            "set {unsigned char}0x00d1 = 0x02",
            "set {unsigned char}0x004d = 0x00",
            f"break *0x{enemy_entry}",
            f"jump *0x{demo_entry}",
            'printf "DEMO_SKULL_FORCED\\n"',
            "set {unsigned char}0x00d1 = 0x00",
            "set {unsigned char}0x004d = 0x00",
            f"set $pc = 0x{demo_entry}",
            "continue",
            'printf "DEMO_ENEMY_FORCED\\n"',
            "detach",
            "quit",
        ]
        runtime_text = run_gdb_commands(
            gdb,
            commands,
            rom.parent.parent,
            demo_timeout,
        )
        return startup_text + "\n" + runtime_text
    finally:
        stop_process(xroar_process)
        xroar_process.wait()


def run_forced_gameplay_probe(
    xroar: str,
    gdb: str,
    rom: Path,
    requested_port: int,
    symbols: dict[str, str],
    presentation_entry: str,
    handoff: str,
    startup_symbols: dict[str, str],
    loader_timeout: int,
    resident_timeout: int,
    forced_timeout: int,
) -> str:
    """Run loader, resident-startup, then forced live gameplay markers."""
    xroar_process, port, startup_text, startup_ready = run_startup_phases(
        xroar,
        gdb,
        rom,
        requested_port,
        handoff,
        "FORCED",
        startup_symbols,
        loader_timeout,
        resident_timeout,
    )
    try:
        if not startup_ready:
            return startup_text
        breakpoint_specs = [
            ("actor_closure_restore", 0x01),
            ("framebuffer_queue_damage", 0x02),
            ("framebuffer_project_damage", 0x04),
            ("sparse_blit_stage", 0x08),
            ("actor_closure_draw", 0x10),
            ("sparse_blit_fb", 0x20),
        ]
        commands = [
            "set pagination off",
            "set confirm off",
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
                'printf "FORCED_WORKLIST_COMPLETE\\n"',
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
            'printf "FORCED_COMMIT front=%d back=%d\\n", *(unsigned char*)0x008f, *(unsigned char*)0x0090',
            "if $gmc_commit_count > 0",
            "if *(unsigned char*)0x0090 == $gmc_last_owner",
            "set $gmc_commit_bad = 1",
            "end",
            "end",
            "if *(unsigned char*)0x008f == *(unsigned char*)0x0090",
            "set $gmc_commit_bad = 1",
            "end",
            "set $gmc_last_owner = *(unsigned char*)0x0090",
            "set $gmc_commit_count = $gmc_commit_count + 1",
            "if $gmc_commit_count >= 1",
            "if $gmc_commit_bad == 0",
            'printf "FORCED_COMMIT_OWNERS_DISTINCT\\n"',
            "end",
            "end",
            "continue",
            "end",
            f"break *0x{presentation_entry} if $gmc_mask == {FORCED_GAMEPLAY_MASK} && $gmc_commit_count >= 1 && $gmc_commit_bad == 0",
            f"commands {completion_breakpoint}",
            "silent",
            'printf "FORCED_COMPLETE\\n"',
            "detach",
            "quit",
            "end",
        ]
        commands.append("continue")
        runtime_text = run_gdb_commands(
            gdb,
            commands,
            rom.parent.parent,
            forced_timeout,
        )
        return startup_text + "\n" + runtime_text
    finally:
        stop_process(xroar_process)
        xroar_process.wait()


if __name__ == "__main__":
    main()
