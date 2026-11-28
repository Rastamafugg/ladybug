#!/usr/bin/env python3
"""Run bounded XRoar/GDB boot, natural, forced-gameplay, and demo phases."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import selectors
import signal
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path

from build_loading import compile_loading
from build_presentation import (
    compile_attract_surfaces, compile_map, load_chars, load_text_colours,
    parse_attract_actors, title_framebuffer,
)
from gmc_lzss import decompress as lzss_decompress


BOOT_PHASE_SECONDS = 10
RESIDENT_STARTUP_PHASE_SECONDS = 10
NATURAL_PHASE_SECONDS = 10
FORCED_GAMEPLAY_SECONDS = 20
FORCED_DEMO_SECONDS = 10


class LoadingFirstFrameError(SystemExit):
    """The first native unblank did not occur at the loading draw boundary."""


def map_symbol(map_text: str, name: str) -> str:
    match = re.search(
        rf"^Symbol: {re.escape(name)} .* = ([0-9A-Fa-f]+)$",
        map_text,
        re.M,
    )
    if not match:
        raise SystemExit(f"gmc proof: {name} missing from map")
    return match.group(1).lower()


def exact_payload_match(expected: bytes, actual: bytes) -> bool:
    return len(expected) == len(actual) and expected == actual


def qualify_payload_comparator() -> None:
    fixture = bytes((0x00, 0x55, 0xAA, 0xFF))
    changed = fixture[:-1] + bytes((fixture[-1] ^ 0x01,))
    if not exact_payload_match(fixture, fixture):
        raise SystemExit("gmc auxiliary proof: comparator rejected a matching fixture")
    if exact_payload_match(fixture, changed):
        raise SystemExit("gmc auxiliary proof: comparator accepted a changed fixture")


def reconstruct_auxiliary_stage(rom: bytes, manifest: dict[str, object]) -> bytes:
    layout = manifest.get("aux_runtime", {})
    staged_bytes = layout.get("staged_bytes")
    stage_address = layout.get("stage_address")
    if (
        layout.get("stage_page") != 0x24 or
        layout.get("copy_phase") != "after_staged_audio" or
        stage_address != 0xA422 or
        not isinstance(staged_bytes, int) or staged_bytes <= 0 or
        stage_address + staged_bytes > 0xC000 or
        layout.get("stage_end") != stage_address + staged_bytes
    ):
        raise SystemExit("gmc auxiliary proof: manifest page-$24 extent is invalid")
    expected = bytearray(staged_bytes)
    covered = bytearray(staged_bytes)
    segments = [
        segment for segment in manifest["gmc"]["segments"]
        if segment.get("target") == "presentation_auxiliary"
    ]
    if not segments:
        raise SystemExit("gmc auxiliary proof: manifest has no auxiliary segments")
    for segment in segments:
        offset = segment["target_offset"]
        count = segment["count"]
        start = segment["bank"] * 0x4000 + segment["source_offset"]
        end = start + count
        if (
            segment.get("destination_page") != 0x24 or
            segment.get("destination_address") != stage_address + offset or
            offset < 0 or count <= 0 or offset + count > staged_bytes or
            end > len(rom) or any(covered[offset:offset + count])
        ):
            raise SystemExit("gmc auxiliary proof: manifest auxiliary segment is invalid")
        expected[offset:offset + count] = rom[start:end]
        covered[offset:offset + count] = b"\x01" * count
    result = bytes(expected)
    if (
        not all(covered) or
        hashlib.sha256(result).hexdigest() != layout.get("staged_sha256")
    ):
        raise SystemExit("gmc auxiliary proof: reconstructed page-$24 stage is not exact")
    return result


def auxiliary_runtime_mutable_fields(
    build_dir: Path,
    layout: dict[str, object],
    expected_stage: bytes,
) -> list[dict[str, object]]:
    """Return the attract-root fields initialized in the staged helper."""
    helper_map = (build_dir / "ladybug-highscore-helper.map").read_text(
        encoding="utf-8"
    )
    stage_address = layout["stage_address"]
    fields = []
    for name, width, value_symbol in (
        ("highscore_logo_root_screen", 1, "PRESENTATION_MAP_ATTRACT"),
        ("highscore_logo_root", 2, "PRESENTATION_ATTRACT_LOGO_ROOT"),
    ):
        address = int(map_symbol(helper_map, name), 16)
        offset = address - stage_address
        if offset < 0 or offset + width > len(expected_stage):
            raise SystemExit(
                f"gmc auxiliary proof: mutable field {name} is outside page-$24 stage"
            )
        fields.append({
            "name": name,
            "address": address,
            "offset": offset,
            "initial_bytes": expected_stage[offset:offset + width],
            "expected_runtime_bytes": int(
                map_symbol(helper_map, value_symbol), 16
            ).to_bytes(width, "big"),
        })
    return fields


def verify_loading_trace(
    xroar: str, rom: Path, boot_map: str, enemy_map: str, asset: bytes, timeout: int,
) -> None:
    """Observe the cold cartridge and both hardware publication writes."""
    def boot_pc(name: str) -> int:
        return int(map_symbol(boot_map, name), 16)

    def forced_ram_pc(name: str) -> int:
        return 0xFE00 + boot_pc(name) - boot_pc("boot_loading_irq")

    text_store = boot_pc("boot_loading_text_store")
    unblank = boot_pc("boot_loading_unblank")
    relocate = boot_pc("boot_copy")
    scanout_a = boot_pc("boot_loading_scanout")
    dot_store = forced_ram_pc("boot_loading_dot_store")
    dot_store_bottom = forced_ram_pc("boot_loading_dot_store_bottom")
    dot_clear = forced_ram_pc("boot_loading_dot_clear")
    dot_clear_bottom = forced_ram_pc("boot_loading_dot_clear_bottom")
    save_pars = forced_ram_pc("boot_loading_irq_save_pars")
    restore_pars = forced_ram_pc("boot_loading_irq_restore_pars")
    irq = forced_ram_pc("boot_loading_irq")
    normal_vector = forced_ram_pc("boot_loading_hydrate_done")
    publish = int(map_symbol(enemy_map, "fbiq_publish"), 16)
    watched = {
        f"{pc:04x}|".encode("ascii"): pc
        for pc in (text_store, unblank, relocate, scanout_a, dot_store, dot_store_bottom,
                   dot_clear, dot_clear_bottom, save_pars, restore_pars, irq, normal_vector, publish)
    }
    process = subprocess.Popen(
        [xroar, "-ui", "null", "-ao", "null", "-machine", "coco3",
         "-machine-cpu", "6809", "-ram", "512", "-ram-init", "random",
         "-cart-type", "gmc", "-cart-rom", str(rom), "-cart-autorun",
         "-no-ratelimit", "-trace"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True,
    )
    registers = re.compile(rb" a=([0-9a-f]{2}) b=([0-9a-f]{2}).* x=([0-9a-f]{4}) y=([0-9a-f]{4})")
    blank = 0
    text = []
    dots = []
    flips = []
    transitions = []
    saved_pars = None
    cartridge_started = False
    deadline = time.monotonic() + timeout
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            tail = b""
            while len(flips) < 2 and time.monotonic() < deadline:
                if not selector.select(max(0, deadline - time.monotonic())):
                    break
                chunk = os.read(process.stdout.fileno(), 65536)
                if not chunk:
                    break
                *lines, tail = (tail + chunk).split(b"\n")
                for line in lines:
                    if line.startswith(b"c002|"):
                        cartridge_started = True
                    if not cartridge_started:
                        continue
                    pc = watched.get(line[:5])
                    video_write = line[6:12] == b"b7ff99"
                    if pc is None and not video_write:
                        continue
                    match = registers.search(line)
                    if not match:
                        raise SystemExit(f"gmc loading proof: malformed trace row {line!r}")
                    a, b, x, y = (int(value, 16) for value in match.groups())
                    if video_write and pc != unblank:
                        if a == 0x1E and "unblank" not in transitions:
                            raise LoadingFirstFrameError(
                                "gmc loading proof: first native unblank did not publish Loading"
                            )
                        if "unblank" in transitions:
                            raise SystemExit("gmc loading proof: display mode changed during handoff")
                    if pc == text_store:
                        text.append((y - 2, a, b))
                    elif pc == irq:
                        blank += 1
                    elif pc == dot_store or pc == dot_clear:
                        dots.append((blank, x, a))
                    elif pc == dot_store_bottom or pc == dot_clear_bottom:
                        dots.append((blank, x + 160, b if pc == dot_store_bottom else a))
                    elif pc == save_pars:
                        saved_pars = blank, a, b
                    elif pc == restore_pars:
                        if saved_pars != (blank, a, b):
                            raise SystemExit("gmc loading proof: dot IRQ changed the interrupted PAR2/PAR3")
                        saved_pars = None
                    elif pc == publish:
                        flips.append((blank, a))
                        transitions.append("publish")
                        if len(flips) == 2:
                            break
                    elif pc == scanout_a:
                        if (a, b) != (0xC0, 0):
                            raise SystemExit("gmc loading proof: initial scanout is not A")
                        transitions.append("scanout A")
                    elif pc == unblank:
                        if a != 0x1E:
                            raise SystemExit("gmc loading proof: unexpected unblank mode")
                        transitions.append("unblank")
                    elif pc == relocate and "relocate" not in transitions:
                        transitions.append("relocate")
                    elif pc == normal_vector:
                        transitions.append("retire IRQ")
    finally:
        stop_process(process)
        process.wait()

    expected_text = [
        (0x57E0 + row * 160 + col, *asset[row * 28 + col:row * 28 + col + 2])
        for row in range(6) for col in range(0, 28, 2)
    ]
    if text != expected_text:
        raise LoadingFirstFrameError("gmc loading proof: initial Loading text writes differ")
    if (transitions != ["scanout A", "unblank", "relocate", "publish", "retire IRQ", "publish"]
            or [offset for _, offset in flips] != [0xB0, 0xC0]):
        raise SystemExit(f"gmc loading proof: unexpected scanout handoff {transitions}, {flips}")
    first_commit = flips[0][0]
    expected_dots = []
    for vb in range(15, first_commit, 15):
        index = (vb // 15 - 1) % 8
        columns = range(7) if index == 7 else (index,)
        for col in columns:
            root = 0x5F61 + col * 4
            pens = (0, 0) if index == 7 else asset[168:170]
            expected_dots.extend(((vb, root, pens[0]), (vb, root + 160, pens[1])))
    if not expected_dots or dots != expected_dots:
        raise SystemExit(f"gmc loading proof: dot writes differ from 15-VBORD cadence: {dots}")
    print(f"gmc loading proof: direct A→B at VBORD {first_commit}; "
          f"dot updates at {sorted({vb for vb, _, _ in dots})}; normal IRQ restored for A")


def verify_loading_buffers(xroar: str, gdb: str, rom: Path, timeout: int) -> None:
    """Read both prepared buffers at the cold hydration boundary."""
    root = Path(__file__).resolve().parents[1]
    tmx = root / "tiled/coco-attract-screen.tmx"
    art = root / "assets/arcade"
    tiles = []
    cells, _ = compile_map(tmx, load_chars(art / "chars.json"), tiles, {},
                           False, True, load_text_colours())
    expected = title_framebuffer(cells, tiles)
    actors = parse_attract_actors(tmx)
    sprites = json.loads((art / "sprites.json").read_text())
    surfaces = compile_attract_surfaces(cells, tiles, sprites, actors)
    for actor_index, actor in enumerate(actors):
        root_offset = actor["destination"] - 0x2000
        for row in range(16):
            target = root_offset + row * 160
            source = actor_index * 128 + row * 8
            expected[target:target + 8] = surfaces[source:source + 8]
    # Cold hydration uses the authored base logo and the nine phase-zero
    # actors. The normal Attract ticker starts logo animation after handoff.
    for row, start, end, colour in ((15, 15, 25, 10), (17, 15, 22, 7), (19, 15, 22, 7)):
        pens = bytes(((colour << 4 if b & 0xF0 else 0) |
                      (colour if b & 0x0F else 0)) for b in range(256))
        for raster in range(row * 8, row * 8 + 8):
            first, last = raster * 160 + start * 4, raster * 160 + end * 4
            expected[first:last] = expected[first:last].translate(pens)
    expected_hash = hashlib.sha256(expected).hexdigest()

    port = free_local_port()
    process = start_xroar(
        [xroar, "-ui", "null", "-ao", "null", "-machine", "coco3",
         "-machine-cpu", "6809", "-ram", "512", "-ram-init", "random",
         "-cart-type", "gmc", "-cart-rom", str(rom), "-cart-autorun",
         "-gdb", "-gdb-ip", "127.0.0.1", "-gdb-port", str(port)],
    )
    deadline = time.monotonic() + timeout
    try:
        time.sleep(0.25)
        with tempfile.TemporaryDirectory(prefix="ladybug-loading-") as temp:
            a, b = Path(temp) / "a.bin", Path(temp) / "b.bin"
            commands = ["set pagination off", "set confirm off", "set remote supported-packets-packet off",
                        f"target remote :{port}", "break *0xfe60"]
            for dump in (b, a):
                commands.extend([
                    "continue",
                    'printf "LOADING_ACTIVE %d %d %d\\n", *(unsigned char*)0x008f, '
                    '*(unsigned char*)0x0090, *(unsigned short*)0x00aa',
                    f"dump binary memory {dump} 0x2000 0x9800",
                ])
            commands.extend(("detach", "quit"))
            result = subprocess.run([gdb, "-q"], input="\n".join(commands) + "\n",
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, timeout=max(0, deadline - time.monotonic()))
            if re.findall(r"LOADING_ACTIVE (\d) (\d) (\d+)", result.stdout) != [
                    ("0", "1", "960"), ("1", "0", "960")]:
                raise SystemExit(f"gmc loading proof: missing distinct hydration owners\n{result.stdout}")
            hashes = [hashlib.sha256(dump.read_bytes()).hexdigest() for dump in (b, a) if dump.exists()]
            if hashes != [expected_hash, expected_hash]:
                raise SystemExit(
                    f"gmc loading proof: initial Attract pixels differ: {hashes}, expected {expected_hash}"
                )
    except subprocess.TimeoutExpired as exc:
        activity = (exc.stdout or b"").decode(errors="replace")
        raise SystemExit(f"gmc loading proof: timed out observing cold Attract buffers\n{activity}") from exc
    finally:
        stop_process(process)
        process.wait()
    print(f"gmc loading proof: both 960-cell Attract buffers are pixel-exact ({expected_hash})")


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
    parser.add_argument("--rom", type=Path, default=Path("build/ladybug.rom"))
    parser.add_argument("--map", type=Path, default=Path("build/ladybug.map"))
    parser.add_argument("--manifest", type=Path, default=Path("build/ladybug-sparse-layout.json"))
    parser.add_argument("--identity-output", type=Path)
    parser.add_argument(
        "--loading-only", action="store_true",
        help="check the complete-profile loading asset, dot cadence and Attract handoff",
    )
    parser.add_argument(
        "--loading-baseline", type=Path,
        help="confirm the pre-feature ROM fails the Loading-first assertion",
    )
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
    parser.add_argument(
        "--verify-auxiliary-page",
        action="store_true",
        help=(
            "compare the live page-$24 auxiliary with its reconstructed ROM "
            "source; requires startup-only"
        ),
    )
    args = parser.parse_args()
    if args.verify_auxiliary_page and not args.startup_only:
        parser.error("--verify-auxiliary-page requires --startup-only")

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
    expected_auxiliary = None
    expected_auxiliary_fields = []
    if args.verify_auxiliary_page:
        qualify_payload_comparator()
        expected_auxiliary = reconstruct_auxiliary_stage(rom, manifest)
        expected_auxiliary_fields = auxiliary_runtime_mutable_fields(
            args.rom.parent, manifest["aux_runtime"], expected_auxiliary
        )

    def retain_identity(
        runtime_verified: bool,
        live_audio_exact: bool = False,
        auxiliary_identity: dict[str, object] | None = None,
    ) -> None:
        if args.identity_output is None:
            return
        rows = []
        for stream in manifest.get("compression", {}).get("streams", []):
            bank_base = stream["bank"] * 0x4000
            start = bank_base + stream["source_offset"]
            packed = rom[start:start + stream["compressed_bytes"]]
            expanded = lzss_decompress(packed, stream["raw_bytes"])
            rows.append({
                "name": stream["name"],
                "destination_page": stream["destination_page"],
                "destination_address": stream["destination_address"],
                "destination_end": stream["destination_end"],
                "authored_sha256": stream["raw_sha256"],
                "staged_sha256": hashlib.sha256(packed).hexdigest(),
                "expanded_sha256": hashlib.sha256(expanded).hexdigest(),
                "byte_exact": hashlib.sha256(expanded).hexdigest() == stream["raw_sha256"],
            })
        if not runtime_verified or not rows or not all(row["byte_exact"] for row in rows):
            raise SystemExit("gmc identity proof: loader runtime or stream identity failed")
        if args.verify_auxiliary_page and not (
            auxiliary_identity and
            auxiliary_identity.get("stage_identity_exact") is True
        ):
            raise SystemExit("gmc identity proof: live page-$24 auxiliary state failed")
        evidence = {
            "status": "pass",
            "loader_runtime_verified": True,
            "live_audio_page_3d_exact": live_audio_exact,
            "live_auxiliary_page_24": auxiliary_identity,
            "streams": rows,
        }
        args.identity_output.parent.mkdir(parents=True, exist_ok=True)
        args.identity_output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="ascii")
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
    runtime_role = manifest.get("aux_runtime", {}).get("role", "release")
    development = runtime_role == "development"
    complete = runtime_role == "complete"
    highscore_test = runtime_role == "highscore-test"
    boot_map = (args.rom.parent / "ladybug-gmc-boot.map").read_text(encoding="utf-8")
    if args.loading_only or args.loading_baseline or complete:
        if not complete:
            parser.error("--loading-only requires the complete profile")
        root = Path(__file__).resolve().parents[1]
        expected = compile_loading(root / "tiled/coco-loading-screen.tmx",
                                   root / "assets/arcade/chars.json")
        start = int(map_symbol(boot_map, "boot_loading_asset"), 16) - 0xC000
        end = int(map_symbol(boot_map, "boot_loading_asset_end"), 16) - 0xC000
        def asset_matches(data: bytes) -> bool:
            return len(data) == 186 and data == expected

        saved = boot[start:end]
        altered_palette = saved[:-1] + bytes((saved[-1] ^ 1,)) if saved else saved
        if asset_matches(altered_palette) or asset_matches(saved[:-1]):
            raise SystemExit("gmc loading proof: accepted a malformed asset fixture")
        if not asset_matches(saved):
            raise SystemExit("gmc loading proof: bank-0 asset does not match the TMX and palette")
        print("gmc loading proof: exact 186-byte Bank 0 asset", flush=True)
        if args.loading_baseline:
            try:
                verify_loading_trace(args.xroar, args.loading_baseline, boot_map, enemy_map,
                                     expected, args.loader_timeout)
            except LoadingFirstFrameError as exc:
                if "first native unblank" not in str(exc):
                    raise
                baseline_hash = hashlib.sha256(args.loading_baseline.read_bytes()).hexdigest()
                print(f"gmc loading proof: pre-feature ROM {baseline_hash} rejected at first unblank")
            else:
                raise SystemExit("gmc loading proof: pre-feature ROM passed the new first-frame check")
        verify_loading_trace(args.xroar, args.rom, boot_map, enemy_map, expected, args.loader_timeout)
        verify_loading_buffers(args.xroar, args.gdb, args.rom, args.resident_timeout)
        if args.loading_only:
            return
    presentation_symbols = {}
    if runtime_role == "release":
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
    expected_entry_opcode = 0x96 if complete else (0xB6 if development or highscore_test else 0x17)
    if not presentation_module or presentation_module[0] != expected_entry_opcode:
        raise SystemExit(
            "gmc proof: presentation module at $1900 does not begin with "
            f"the expected profile entry opcode ${expected_entry_opcode:02X}"
        )
    # Queue/project routines belong to the legacy persistent renderer. The
    # adaptive path dispatches through AD_RENDER_EXEC and uses active closure
    # and sparse-decoder entries instead.
    adaptive_rendering = int(map_symbol(enemy_map, "ADAPTIVE_RENDERING"), 16) != 0
    if adaptive_rendering:
        breakpoint_specs = [
            ("actor_closure_restore", 0x01),
            ("sparse_blit_stage", 0x02),
            ("actor_closure_draw", 0x04),
            ("sparse_blit_fb", 0x08),
        ]
    else:
        breakpoint_specs = [
            ("actor_closure_restore", 0x01),
            ("framebuffer_queue_damage", 0x02),
            ("framebuffer_project_damage", 0x04),
            ("sparse_blit_stage", 0x08),
            ("actor_closure_draw", 0x10),
            ("sparse_blit_fb", 0x20),
        ]
    damage_symbols = {
        name: map_symbol(enemy_map, name)
        for name, _bit in breakpoint_specs
    }
    damage_symbols["fbiq_publish"] = map_symbol(enemy_map, "fbiq_publish")
    forced_gameplay_mask = 0
    for _name, bit in breakpoint_specs:
        forced_gameplay_mask |= bit
    if "sta     SAM_FAST" not in main_source or "SAM_FAST   equ  $FFD9" not in main_source:
        raise SystemExit("gmc proof: resident fast-clock selection missing")
    if "sta     SAM_FAST" not in loader_source or "SAM_FAST    equ $FFD9" not in loader_source:
        raise SystemExit("gmc proof: bootstrap fast-clock selection missing")
    if not complete and "jmp     $C002" not in loader_source:
        raise SystemExit("gmc proof: relocated runtime handoff must skip the DK header")
    if "copy_enemy_sparse_index" in loader_source or "copy_player_sparse_index" in loader_source:
        raise SystemExit("gmc proof: sparse indexes must not overwrite the relocated loader")
    if args.verify_auxiliary_page:
        audio_expansion = loader_source.find("lbsr    decompress_staged_audio")
        late_copy = loader_source.find("lbsr    copy_late_sparse_segments")
        routine_start = loader_source.find("\ncopy_late_sparse_segments\n") + 1
        routine_end = loader_source.find("\ndecompress_gmc_streams", routine_start)
        late_routine = loader_source[routine_start:routine_end]
        ordered_steps = (
            "sta     SAM_CART",
            "sta     PAR_EXEC+5",
            "lbsr    copy_sparse_payload",
            "sta     SAM_ALLRAM",
        )
        positions = [late_routine.find(step) for step in ordered_steps]
        if (
            audio_expansion < 0 or late_copy <= audio_expansion or
            routine_start < 0 or routine_end <= routine_start or
            any(position < 0 for position in positions) or
            positions != sorted(positions) or
            "AUXILIARY_STAGE_PAGE equ $24" not in loader_source or
            "SPARSE_COPY_LATE_SELECTOR" not in late_routine
        ):
            raise SystemExit(
                "gmc auxiliary proof: late page-$24 copy order/mapping is invalid"
            )
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
        # GMC's documented primary bank-select register is $FF40.
        cursor = boot.find(bytes((0xB7, 0xFF, 0x40)), cursor)
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
    if complete:
        handoff_offset = int(map_symbol(boot_map, "boot_runtime_handoff"), 16) - 0xC000
        runtime_entry = int(map_symbol(map_text, "startup_gmc_entry"), 16)
    else:
        handoff_offset = boot.find(bytes((0x7E, 0xC0, 0x02)), loader_start)
        runtime_entry = 0xC002
    if handoff_offset < 0 or boot[handoff_offset:handoff_offset + 3] != (
            b"\x7e" + runtime_entry.to_bytes(2, "big")):
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
        (
            xroar_process,
            _port,
            startup_text,
            startup_ready,
            auxiliary_identity,
        ) = run_startup_phases(
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
            complete,
            expected_auxiliary,
            expected_auxiliary_fields,
        )
        try:
            print(startup_text)
            print(phase_summary("startup", startup_text))
            if not startup_ready:
                raise SystemExit("gmc startup diagnosis: resident startup incomplete")
            retain_identity(True, complete, auxiliary_identity)
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
        breakpoint_specs,
        forced_gameplay_mask,
    )
    demo_text = "DEVELOPMENT_PROFILE_DEMO_BYPASSED"
    if runtime_role == "release":
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
        "actor closure restore entered": "FORCED_HIT actor_closure_restore" in forced_text,
        "actor closure draw entered": "FORCED_HIT actor_closure_draw" in forced_text,
        "sparse framebuffer decoder entered": "FORCED_HIT sparse_blit_fb" in forced_text,
        "sparse stage decoder entered": "FORCED_HIT sparse_blit_stage" in forced_text,
        "Vbord commit entered with distinct owners": (
            "FORCED_COMMIT_OWNERS_DISTINCT" in forced_text
        ),
        "forced gameplay completion": "FORCED_COMPLETE" in forced_text,
    }
    if not adaptive_rendering:
        forced_required.update({
            "damage queue entered": "FORCED_HIT framebuffer_queue_damage" in forced_text,
            "damage projection entered": "FORCED_HIT framebuffer_project_damage" in forced_text,
        })
    if runtime_role == "release":
        forced_required.update({
            "forced skull demo death": "DEMO_SKULL_FORCED" in demo_text,
            "forced enemy demo death": "DEMO_ENEMY_FORCED" in demo_text,
            "demo loader handoff": "DEMO_LOADER_HANDOFF" in demo_text,
            "demo resident startup completion": (
                "DEMO_RESIDENT_STARTUP_COMPLETE" in demo_text
            ),
        })
    required = {**natural_required, **forced_required}
    failed = [name for name, passed in required.items() if not passed]
    if failed:
        raise SystemExit(
            "gmc proof failed: " + ", ".join(failed) + "; " +
            phase_summary("natural", natural_text) + "; " +
            phase_summary("forced", forced_text) + "; " +
            phase_summary("demo", demo_text)
        )
    retain_identity(True)
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
            "-machine", "coco3", "-machine-cpu", "6809", "-ram", "512",
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
    verify_audio_page: bool = False,
    expected_auxiliary: bytes | None = None,
    expected_auxiliary_fields: list[dict[str, object]] | None = None,
) -> tuple[subprocess.Popen[object], int, str, bool, dict[str, object] | None]:
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
            "-machine", "coco3", "-machine-cpu", "6809", "-ram", "512",
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
        audio_dump = Path(temp_dir) / "audio-runtime.bin"
        auxiliary_dump = Path(temp_dir) / "auxiliary-page-24.bin"
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
        if verify_audio_page:
            audio_bytes = (rom.parent / "ladybug-audio-runtime.bin").read_bytes()
            resident_commands.extend([
                "set $gmc_saved_par5 = *(unsigned char*)0xffa5",
                "set {unsigned char}0xffa5 = 0x3d",
                f"dump binary memory {audio_dump} 0xa000 0x{0xA000 + len(audio_bytes):04x}",
                "set {unsigned char}0xffa5 = $gmc_saved_par5",
            ])
        if expected_auxiliary is not None:
            resident_commands.extend([
                "set $gmc_saved_par5 = *(unsigned char*)0xffa5",
                "set {unsigned char}0xffa5 = 0x24",
                (
                    f"dump binary memory {auxiliary_dump} 0xa422 "
                    f"0x{0xA422 + len(expected_auxiliary):04x}"
                ),
                "set {unsigned char}0xffa5 = $gmc_saved_par5",
            ])
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
        audio_exact = True
        if verify_audio_page:
            actual_audio = audio_dump.read_bytes() if audio_dump.exists() else b""
            # First presentation dispatch initializes foreground queue/slot
            # state. Compare every immutable byte and exclude only the authored
            # mutable spans, not the containing page or executable regions.
            audio_map = (rom.parent / 'ladybug-audio-runtime.map').read_text()
            mutable = [
                (int(map_symbol(audio_map, 'audio_stop_pending'),16),14),
                (int(map_symbol(audio_map, 'audio_name_valid'),16),4),
                (int(map_symbol(audio_map, 'audio_slot0'),16),125),
            ]
            mutable_offsets={a-0xA000+i for a,n in mutable for i in range(n)}
            audio_exact = len(actual_audio)==len(audio_bytes) and all(
                a==b for i,(a,b) in enumerate(zip(actual_audio,audio_bytes))
                if i not in mutable_offsets)
            resident_text += (
                f"\n{prefix}_AUDIO_PAGE_EXACT\n" if audio_exact else
                f"\n{prefix}_AUDIO_PAGE_MISMATCH expected={len(audio_bytes)} actual={len(actual_audio)}\n"
            )
        auxiliary_identity = None
        if expected_auxiliary is not None:
            actual_auxiliary = (
                auxiliary_dump.read_bytes() if auxiliary_dump.exists() else b""
            )
            mutable_mask = bytearray(len(expected_auxiliary))
            mutable_expectations = {}
            mutable_results = []
            for field in expected_auxiliary_fields or []:
                offset = int(field["offset"])
                initial_bytes = bytes(field["initial_bytes"])
                runtime_bytes = bytes(field["expected_runtime_bytes"])
                end = offset + len(initial_bytes)
                if offset < 0 or end > len(expected_auxiliary):
                    raise SystemExit(
                        "gmc auxiliary proof: mutable field exceeds staged page-$24 bytes"
                    )
                actual_field = actual_auxiliary[offset:end]
                if len(initial_bytes) != len(runtime_bytes):
                    raise SystemExit(
                        "gmc auxiliary proof: mutable field state widths differ"
                    )
                for field_offset, (initial_byte, runtime_byte) in enumerate(
                    zip(initial_bytes, runtime_bytes)
                ):
                    mutable_mask[offset + field_offset] = 1
                    mutable_expectations[offset + field_offset] = (
                        initial_byte,
                        runtime_byte,
                    )
                state = (
                    "staged" if actual_field == initial_bytes else
                    "attract" if actual_field == runtime_bytes else
                    "unexpected"
                )
                mutable_results.append({
                    "name": field["name"],
                    "address": field["address"],
                    "offset": offset,
                    "initial_bytes": initial_bytes.hex(),
                    "expected_runtime_bytes": runtime_bytes.hex(),
                    "live_bytes": actual_field.hex(),
                    "state": state,
                })
            immutable_mismatches = [
                offset for offset, (expected_byte, actual_byte) in enumerate(
                    zip(expected_auxiliary, actual_auxiliary)
                )
                if not mutable_mask[offset] and expected_byte != actual_byte
            ]
            mutable_mismatches = [
                offset + field_offset
                for field, result in zip(
                    expected_auxiliary_fields or [], mutable_results
                )
                if result["state"] == "unexpected"
                for field_offset in range(len(bytes(field["initial_bytes"])))
            ]
            mismatch_offsets = sorted(set(immutable_mismatches + mutable_mismatches))
            auxiliary_exact = (
                len(expected_auxiliary) == len(actual_auxiliary) and
                not mismatch_offsets
            )
            mismatch_count = len(mismatch_offsets) + abs(
                len(expected_auxiliary) - len(actual_auxiliary)
            )
            first_mismatch = (
                f"{mismatch_offsets[0]:04x}" if mismatch_offsets else
                f"{min(len(expected_auxiliary), len(actual_auxiliary)):04x}"
                if len(expected_auxiliary) != len(actual_auxiliary) else "none"
            )
            mismatch_samples = ",".join(
                (
                    f"{offset:04x}:{mutable_expectations[offset][0]:02x}|"
                    f"{mutable_expectations[offset][1]:02x}/"
                    f"{actual_auxiliary[offset]:02x}"
                    if offset in mutable_expectations else
                    f"{offset:04x}:{expected_auxiliary[offset]:02x}/"
                    f"{actual_auxiliary[offset]:02x}"
                )
                for offset in mismatch_offsets[:8]
                if offset < len(actual_auxiliary)
            )
            auxiliary_identity = {
                "physical_page": 0x24,
                "address": 0xA422,
                "expected_bytes": len(expected_auxiliary),
                "live_bytes": len(actual_auxiliary),
                "expected_sha256": hashlib.sha256(expected_auxiliary).hexdigest(),
                "live_sha256": hashlib.sha256(actual_auxiliary).hexdigest(),
                "stage_identity_exact": auxiliary_exact,
                "comparison_rule": "all staged bytes exact; mutable fields must be initial or attract state",
                "mutable_fields": mutable_results,
                "mismatch_bytes": mismatch_count,
                "first_mismatch_offset": first_mismatch,
                "mismatch_samples": mismatch_samples,
            }
            resident_text += (
                f"\n{prefix}_AUXILIARY_PAGE_24_VALID\n" if auxiliary_exact else
                f"\n{prefix}_AUXILIARY_PAGE_24_MISMATCH "
                f"expected={len(expected_auxiliary)} actual={len(actual_auxiliary)} "
                f"diff_bytes={mismatch_count} first_diff_offset={first_mismatch} "
                f"samples={mismatch_samples}\n"
            )
    texts = [loader_text, resident_text]
    return (
        xroar_process,
        port,
        "\n".join(texts),
        f"{prefix}_LOADER_HANDOFF" in loader_text and
        f"{prefix}_RESIDENT_STARTUP_COMPLETE" in resident_text and
        f"{prefix}_BANK1_RAM_EXACT" in resident_text and audio_exact and
        (
            expected_auxiliary is None or
            bool(auxiliary_identity and auxiliary_identity.get("stage_identity_exact"))
        ),
        auxiliary_identity,
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
    (
        xroar_process,
        port,
        startup_text,
        startup_ready,
        _auxiliary_identity,
    ) = run_startup_phases(
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
    (
        xroar_process,
        port,
        startup_text,
        startup_ready,
        _auxiliary_identity,
    ) = run_startup_phases(
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
    breakpoint_specs: list[tuple[str, int]],
    forced_gameplay_mask: int,
) -> str:
    """Run loader, resident-startup, then forced live gameplay markers."""
    (
        xroar_process,
        port,
        startup_text,
        startup_ready,
        _auxiliary_identity,
    ) = run_startup_phases(
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
                f"if $gmc_mask == {forced_gameplay_mask}",
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
            f"break *0x{presentation_entry} if $gmc_mask == {forced_gameplay_mask} && $gmc_commit_count >= 1 && $gmc_commit_bad == 0",
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
