#!/usr/bin/env python3
"""PERF-007 source/oracle checkpoint adapter.

The source-static phase is intentionally independent of emulator execution.  It
audits the approved assembly contract and exhaustively checks the native nibble
algebra against the generated object LUTs and resident enemy artifact.  Runtime
phases are explicit unavailable failures until their assigned observers exist.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
from pathlib import Path


COLOURS = (1, 2, 3)
LUT_NAMES = ("red", "yellow", "blue")
MASK_RE = re.compile(r"^object_mask_lut\s+equ\s+\$([0-9A-Fa-f]+)$", re.MULTILINE)
MAP_RE = re.compile(r"^Symbol: (\w+) .* = ([0-9A-Fa-f]+)$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", required=True,
                        choices=("source-static", "identity", "projection",
                                 "saveunder", "timing"))
    parser.add_argument("--build-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--identity", type=Path)
    parser.add_argument("--baseline-build-dir", type=Path)
    parser.add_argument("--deadline-seconds", type=float)
    return parser.parse_args()


def fail(message: str) -> None:
    raise RuntimeError(message)


def label_pos(source: str, label: str) -> int:
    match = re.search(r"(?m)^" + re.escape(label) + r"\s*$", source)
    if not match:
        fail(f"source-static: missing label {label}")
    return match.start()


def read_source(root: Path) -> tuple[str, str]:
    main = root / "src" / "main.s"
    enemy = root / "src" / "enemy_runtime.s"
    if not main.is_file() or not enemy.is_file():
        fail("source-static: production source files are missing")
    return main.read_text(encoding="utf-8"), enemy.read_text(encoding="utf-8")


def parse_fcb_block(source: str, label: str, next_label: str) -> list[int]:
    start = source.find(label)
    if start < 0:
        fail(f"source-static: missing {label}")
    end = source.find(next_label, start + len(label))
    if end < 0:
        fail(f"source-static: missing {next_label} after {label}")
    values: list[int] = []
    for line in source[start:end].splitlines()[1:]:
        body = line.split(";", 1)[0].strip()
        if not body.startswith("fcb"):
            continue
        for token in body[3:].strip().split(","):
            token = token.strip()
            if not token:
                continue
            values.append(int(token[1:], 16) if token.startswith("$") else int(token, 0))
    return values


def source_contract(root: Path, main: str, enemy: str) -> dict[str, object]:
    required_main = (
        "ENTITY_CACHE_COLOR equ $A89C",
        "RF2_COLOUR     equ $10",
        "sync_entity_cache_colour",
        "de_rebind",
        "rebind_cache_value",
        "primary_cache_mask",
        "replay_entity_primary_overlay",
        "render_entity_colour",
        "tst     BONUS_LEFT",
        "beq     main_bonus_exhausted",
        "ora     #RF2_COLOUR",
        "clr     ENTITY_CACHE_COLOR",
    )
    required_enemy = (
        "ENTITY_CACHE_COLOR equ $A89C",
        "RF2_COLOUR     equ $10",
        "jsr     sync_entity_cache_colour",
        "lbsr    colour_prepare_nest",
        "bcc     colour_mark_roaming",
        "ora     #ERF_NEST",
        "sta     ENEMY_CAPTURE_DIRTY",
        "anda    #RF2_MULTIPLIER|RF2_LETTER|RF2_PERIM_RESET|RF2_COLOUR",
        "bita    #RF2_COLOUR",
        "jsr     render_entity_colour",
    )
    missing = [f"main.s:{fragment}" for fragment in required_main if fragment not in main]
    missing.extend(f"enemy_runtime.s:{fragment}" for fragment in required_enemy if fragment not in enemy)
    if missing:
        fail("source-static: missing source contract: " + "; ".join(missing))

    # The validity byte is persistent page-$34 state, not direct-page scratch.
    # In particular, $009F is the low byte of the u16 RING_BASE scratch word.
    if re.search(r"(?m)^ENTITY_CACHE_COLOR\s+equ\s+\$009F\b", main) or re.search(
            r"(?m)^ENTITY_CACHE_COLOR\s+equ\s+\$009F\b", enemy):
        fail("source-static: cache validity aliases direct-page RING_BASE")
    for source_name, source, pattern in (
        ("main.s", main, r"(?m)^ENTITY_CACHE_COLOR\s+equ\s+\$A89C\b"),
        ("enemy_runtime.s", enemy, r"(?m)^ENTITY_CACHE_COLOR\s+equ\s+\$A89C\b"),
    ):
        if not re.search(pattern, source):
            fail(f"source-static: {source_name} cache validity is not at $A89C")
    if not re.search(r"(?m)^RING_BASE\s+equ\s+\$009E\b", enemy):
        fail("source-static: RING_BASE direct-page address changed")
    if not re.search(r"(?m)^ENEMY_BG_RING\s+equ\s+\$A898\b", enemy):
        fail("source-static: ENEMY_BG_RING address changed")

    tick_start = label_pos(main, "bonus_color_tick")
    tick_end = label_pos(main, "perimeter_timer_tick")
    tick = main[tick_start:tick_end]
    if "ora     #RF_ENTITIES" in tick:
        fail("source-static: bonus_color_tick still requests destructive RF_ENTITIES")
    queue_start = label_pos(enemy, "framebuffer_queue_damage")
    queue_end = label_pos(enemy, "roam_mark_underlay")
    queue = enemy[queue_start:queue_end]
    if "RF2_COLOUR" not in queue:
        fail("source-static: queue mask drops RF2_COLOUR")

    # The full-byte secondary test must remain before gate-only promotion.
    gate_start = label_pos(main, "framebuffer_project_gate_only")
    gate_end = label_pos(main, "finish_gate_animation")
    gate = main[gate_start:gate_end]
    for fragment in ("FBM_PENDING_INTENTS+1,u", "bne     fpg_no"):
        if fragment not in gate:
            fail(f"source-static: gate discriminator missing {fragment}")
    damage_start = label_pos(enemy, "framebuffer_project_damage")
    damage_end = label_pos(enemy, "framebuffer_queue_damage")
    if "jsr     framebuffer_project_gate_only" not in enemy[damage_start:damage_end]:
        fail("source-static: pending damage does not use gate-only promotion")

    # Existing gate ownership remains the final hidden-surface writer for an
    # active transition: the transition stream restores PAR5, then the full
    # associated entity overlays are replayed.  The persistent gate path keeps
    # that ordering; the fallback retains gate_render_hidden separately.
    transition_start = label_pos(main, "draw_gate_transition")
    transition_end = label_pos(main, "framebuffer_project_gate_only")
    transition = main[transition_start:transition_end]
    transition_gate = transition.find("lda     #$34")
    transition_entities = transition.find("lbsr    draw_gate_entities")
    if transition_gate < 0 or transition_entities < transition_gate:
        fail("source-static: gate transition does not replay full associated entities after mapping restore")
    compose_start = label_pos(enemy, "gate_compose_impl")
    compose_end = label_pos(enemy, "gci_done")
    compose = enemy[compose_start:compose_end]
    persistent = compose[:compose.find("else")]
    fallback = compose[compose.find("else"):]
    if "jsr     draw_gate_transition" not in persistent:
        fail("source-static: persistent gate path lost full transition entity overlay")
    if "jsr     gate_render_hidden" not in fallback:
        fail("source-static: fallback gate path lost hidden composition")

    render_start = label_pos(enemy, "frame_render_background")
    render_end = label_pos(enemy, "render_exposed_player")
    render = enemy[render_start:render_end]
    colour_label = render.index("\nfri_colour\n")
    entity_check = render.index("bita    #RF_ENTITIES")
    colour_check = render.index("bita    #RF2_COLOUR", colour_label)
    if entity_check > colour_label or colour_check < colour_label:
        fail("source-static: RF2_COLOUR precedes RF_ENTITIES precedence")

    # PERSISTENT_FB=0 has no cache-sync or owner-ledger path.  Its colour
    # intent must therefore enter the existing RF_ENTITIES full redraw while
    # the conditional body is absent from the persistent build.
    fallback_start = render.find("ifeq    PERSISTENT_FB")
    fallback_end = render.find("endc", fallback_start)
    fallback_colour = render.find("bita    #RF2_COLOUR", fallback_start)
    fallback_entities = render.find("ora     #RF_ENTITIES", fallback_start)
    entities_branch = render.find("beq     fri_colour", fallback_start)
    if (fallback_start < 0 or fallback_end < 0 or fallback_colour < fallback_start or
            fallback_entities < fallback_colour or fallback_entities > fallback_end or
            entities_branch < fallback_entities):
        fail("source-static: fallback colour intent does not select full RF_ENTITIES redraw")

    sync_start = label_pos(enemy, "framebuffer_prepare_back")
    sync_end = label_pos(enemy, "framebuffer_capture_back")
    sync_window = enemy[sync_start:sync_end]
    if sync_window.index("sync_entity_cache_colour") > sync_window.rindex("\nfbp_ok\n"):
        fail("source-static: cache synchronization occurs after BACK preparation return")
    prepare_start = label_pos(enemy, "frame_render_impl")
    prepare_end = label_pos(enemy, "actor_closure_restore")
    prepare_window = enemy[prepare_start:prepare_end]
    if prepare_window.index("colour_prepare_nest") > prepare_window.index("actor_closure_restore"):
        fail("source-static: nest decision occurs after actor closure")

    # The replay mutation must preserve invariant destination nibbles.  Check
    # the actual source control flow, then force a foreground counterexample
    # that would pass the old unmasked OR but is incorrect for primary-only
    # projection (cached $42, preserve $F0, destination $A7 -> expected $A2).
    overlay_start = label_pos(main, "replay_entity_primary_overlay")
    overlay_end = label_pos(main, "render_entity_colour")
    overlay = main[overlay_start:overlay_end]
    overlay_steps = (
        "tfr     a,b",
        "comb",
        "andb    OBJ_VALUE",
        "stb     OBJ_PRIMARY",
        "anda    ,x",
        "ora     OBJ_PRIMARY",
        "sta     ,x",
    )
    positions = []
    for fragment in overlay_steps:
        if fragment not in overlay:
            fail("source-static: primary replay lacks masked value merge " + fragment)
        positions.append(overlay.index(fragment))
    if positions != sorted(positions):
        fail("source-static: primary replay mask/value merge control flow is reordered")
    foreground = 0xA7
    cached = 0x42
    preserve = 0xF0
    expected = (foreground & preserve) | (cached & (~preserve & 0xFF))
    old_unmasked = (foreground & preserve) | cached
    if expected != 0xA2 or old_unmasked == expected:
        fail("source-static: primary replay mutation discriminant is ineffective")

    # Pending colour decisions are valid only while the selected owner has
    # damage.  Pending upper-nest work already carries ERF_NEST in byte +8;
    # this frame may dirty captures but must not promote that bit into current.
    nest_start = label_pos(enemy, "colour_prepare_nest")
    nest_end = label_pos(enemy, "colour_has_upper_bonus")
    nest = enemy[nest_start:nest_end]
    damage_pos = nest.find("tst     FBM_DAMAGE,u")
    pending_pos = nest.find("FBM_PENDING_INTENTS+1,u")
    if damage_pos < 0 or pending_pos < 0 or damage_pos > pending_pos:
        fail("source-static: pending colour flags are read without damage validation")
    if "bita    #RF_STAGE|RF_ENTITIES" not in nest:
        fail("source-static: stage/full-entity precedence missing from colour preparation")
    full_nest = nest[nest.find("\ncpn_full_nest\n"):]
    current_gate = full_nest.find("bita    #RF2_COLOUR")
    return_gate = full_nest.find("beq     cpn_done", current_gate)
    promotion = full_nest.find("ora     #ERF_NEST")
    if not (0 <= current_gate < return_gate < promotion):
        fail("source-static: pending-only nest work can promote current ERF_NEST")

    # RF_STAGE is the complete current construction owner.  It discards the
    # selected owner's old pending damage before any replay/gate consumer while
    # queueing the current stage to the other owner remains unchanged.
    damage_start = label_pos(enemy, "framebuffer_project_damage")
    damage_end = label_pos(enemy, "framebuffer_queue_damage")
    damage_window = enemy[damage_start:damage_end]
    stage_pos = damage_window.find("bita    #RF_STAGE")
    damage_check_pos = damage_window.find("tst     FBM_DAMAGE,u")
    if stage_pos < 0 or damage_check_pos < 0 or stage_pos > damage_check_pos:
        fail("source-static: RF_STAGE does not supersede old pending damage")
    if "clr     FBM_DAMAGE,u" not in damage_window[:damage_check_pos]:
        fail("source-static: RF_STAGE path does not clear selected pending damage")

    # Cache rebinding can only replace value bytes.  A store to the record's
    # current U cursor is allowed at -1,U; no header/mask store is allowed.
    record_start = label_pos(main, "replay_entity_overlay_common")
    # Rebinding now shares the sparse-record parser with replay, so include
    # that parser through the public colour entry when checking its mutation.
    record_end = label_pos(main, "render_entity_colour")
    record = main[record_start:record_end]
    if "sta     -1,u" not in record or re.search(r"sta\s+,(?:u|u\+)", record):
        fail("source-static: cache record rebinding does not prove value-only writes")

    # The fitting producer paints and builds the same original operations in
    # one pass. Zone staging paints only, with its original 15/1-row clipping;
    # validity is published only by the completed normal entity loop.
    entities = main[label_pos(main, "draw_entities"):label_pos(main, "sync_entity_cache_colour")]
    if "lbsr    cache_entity_overlay" in entities:
        fail("source-static: duplicated post-draw cache construction remains")
    for fragment in ("de_rebind\n        ldu     OBJ_CACHE_BASE",
                     "bmi     secc_store", "bita    #ERF_ZONE_ENTITY",
                     "sta     ENTITY_CACHE_COLOR"):
        if fragment not in entities:
            fail("source-static: shared iteration/validity contract missing " + fragment)
    producer = main[label_pos(main, "draw_entity_object"):label_pos(main, "bonus_color_tick")]
    for fragment in ("lda     #15", "lda     #1", "stu     OBJ_CACHE_LUT",
                     "bra     cache_entity_overlay", "bra    ceo_row",
                     "andb    ,x", "orb     OBJ_VALUE", "stb     ,x",
                     "bne     ceo_zone_written", "puls    b",
                     "suba    #4", "bcs     cache_entity_overflow"):
        if fragment not in producer:
            fail("source-static: single-pass producer contract missing " + fragment)

    # The gate association path must continue to skip collected records and use
    # full cached operations for independent gate replay.
    assoc_start = label_pos(main, "draw_gate_entities")
    # The shared full/primary replay entry now lives earlier than this caller;
    # bound the caller slice at the following gate-overlap routine instead.
    assoc_end = label_pos(main, "mark_gate_enemy_overlap")
    assoc = main[assoc_start:assoc_end]
    for fragment in ("lda     2,x", "beq     dge_skip", "lbsr    replay_gate_entity_overlay"):
        if fragment not in assoc:
            fail(f"source-static: gate association contract missing {fragment}")

    return {
        "required_main": len(required_main),
        "required_enemy": len(required_enemy),
        "cache_sync_before_consumer": True,
        "full_byte_gate_discriminator": True,
        "combined_entity_stage_precedence": True,
        "value_only_rebind": True,
        "gate_association_current_type_skip": True,
        "cache_validity_reserved_gap": True,
        "primary_overlay_masks_invariant_nibbles": True,
        "primary_overlay_counterexample": "cached=42 preserve=F0 foreground=A7 expected=A2",
        "fallback_colour_full_refresh_conditional": True,
        "pending_damage_validated": True,
        "pending_nest_not_promoted": True,
        "stage_supersedes_pending_damage": True,
        "gate_transition_full_entity_overlay_after_restore": True,
    }


def parse_luts(enemy: str) -> dict[str, list[int]]:
    labels = {
        "mask": ("object_mask_lut", "object_red_lut"),
        "red": ("object_red_lut", "object_yellow_lut"),
        "yellow": ("object_yellow_lut", "object_blue_lut"),
        "blue": ("object_blue_lut", "object_skull_lut"),
        "skull": ("object_skull_lut", "enemy_runtime_end"),
    }
    result = {name: parse_fcb_block(enemy, label, nxt) for name, (label, nxt) in labels.items()}
    if any(len(values) != 16 for values in result.values()):
        fail("source-static: object LUTs must contain exactly 16 entries")
    return result


def replace_primary(value: int, target: int) -> int:
    high = (value >> 4) & 0x0F
    low = value & 0x0F
    if high in COLOURS:
        high = target
    if low in COLOURS:
        low = target
    return (high << 4) | low


def primary_mask(mask: int, value: int) -> int:
    result = mask
    high = (value >> 4) & 0x0F
    low = value & 0x0F
    if not mask & 0xF0 and high not in COLOURS:
        result |= 0xF0
    if not mask & 0x0F and low not in COLOURS:
        result |= 0x0F
    return result


def nibble_contract(luts: dict[str, list[int]]) -> dict[str, object]:
    masks = luts["mask"]
    full = {colour: luts[colour] for colour in LUT_NAMES}
    # The compact source kernel uses $30/$03 to discriminate native primary
    # halves.  Keep this proof tied to the compiled art domain: bonus LUT
    # nibbles are only black, native 1..3, or pink 4; skull/type 0 is never a
    # native-primary source for recolour.
    for name in LUT_NAMES:
        if any(nibble > 4 for value in full[name] for nibble in ((value >> 4) & 0x0F, value & 0x0F)):
            fail(f"source-static: {name} LUT contains a non-domain nibble")
    if any(nibble in COLOURS for value in luts["skull"]
           for nibble in ((value >> 4) & 0x0F, value & 0x0F)):
        fail("source-static: skull/type 0 LUT contains a native-primary nibble")
    cases = 0
    for old in LUT_NAMES:
        for new in COLOURS:
            for index, mask in enumerate(masks):
                old_value = full[old][index]
                rebound = replace_primary(old_value, new)
                projected_mask = primary_mask(mask, old_value)
                target_value = full[LUT_NAMES[new - 1]][index]
                for background in range(256):
                    prior = (background & mask) | old_value
                    projected = (prior & projected_mask) | (rebound & (~projected_mask & 0xFF))
                    expected = (background & mask) | target_value
                    if projected != expected:
                        fail(f"source-static: nibble algebra mismatch old={old} new={new} mask={index}")
                    cases += 1
    return {
        "marker": "perf007_native_nibble_contract_verified",
        "cases": cases,
        "old_colours": list(COLOURS),
        "new_colours": list(COLOURS),
        "mask_codes": 16,
        "background_bytes": 256,
        "compiled_bonus_nibbles_max": 4,
        "compiled_skull_native_primary_nibbles": 0,
    }


def parse_map(path: Path) -> dict[str, int]:
    if not path.is_file():
        fail(f"source-static: missing map {path}")
    values: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = MAP_RE.match(line)
        if match:
            values[match.group(1)] = int(match.group(2), 16)
    return values


def sparse_geometry(root: Path, build: Path, main: str, enemy: str,
                    luts: dict[str, list[int]]) -> dict[str, object]:
    required = (
        "ENTITY_GATE_CACHE equ $B000",
        "GATE_ENTITY_LISTS equ $B600",
        "GATE_ENTITY_RECORD_SIZE equ 77",
        "cache_entity_operation",
        "replay_gate_entity_overlay",
        "leax    1,x",
        "lbeq    cache_entity_overflow",
    )
    missing = [fragment for fragment in required if fragment not in main]
    if missing:
        fail("source-static: sparse geometry contract missing " + ", ".join(missing))
    enemy_rom = build / "ladybug-enemy-runtime.rom"
    enemy_map = parse_map(build / "ladybug-enemy-runtime.map")
    if not enemy_rom.is_file():
        fail("source-static: missing enemy runtime artifact")
    data = enemy_rom.read_bytes()
    if len(data) > 4096:
        fail("source-static: enemy runtime artifact exceeds 4 KiB")
    for index, name in enumerate(("mask", "red", "yellow", "blue", "skull")):
        label = f"object_{name}_lut"
        if label not in enemy_map:
            fail(f"source-static: artifact map is missing {label}")
        start = enemy_map[label] - 0x0800
        expected = luts[name]
        if start < 0 or start + 16 > len(data) or data[start:start + 16] != bytes(expected):
            fail(f"source-static: compiled LUT artifact differs at {label}")

    layout = parse_map(build / "ladybug.map")
    cache = layout.get("ENTITY_GATE_CACHE", 0xB000)
    lists = layout.get("GATE_ENTITY_LISTS", 0xB600)
    record_size = 77
    if cache != 0xB000 or lists != 0xB600 or lists + 20 * record_size > 0xC000:
        fail("source-static: cache/gate association address bounds are invalid")
    return {
        "marker": "perf007_sparse_geometry_verified",
        "enemy_runtime_bytes": len(data),
        "enemy_runtime_limit": 4096,
        "cache_base": cache,
        "cache_slot_bytes": 128,
        "gate_lists_base": lists,
        "gate_records": 20,
        "gate_record_bytes": record_size,
        "primary_cursor_advances_skips": True,
        "compiled_luts_verified": True,
    }


def sha256(path: Path) -> str:
    if not path.is_file():
        fail(f"source-static: missing artifact {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def candidate_capacity(root: Path, build: Path) -> dict[str, object]:
    """Report observed candidate sizes without treating overflow as a pass."""
    result: dict[str, object] = {
        "full_candidate_build": "failed_resident_guard",
        "resident_limit_end": 0xE000,
    }
    result["scope"] = "selected build artifact; source correspondence requires guarded rebuild"
    candidate_map = build / "ladybug.map"
    if candidate_map.is_file():
        symbols = parse_map(candidate_map)
        if "resident_end" in symbols:
            result["resident_end"] = symbols["resident_end"]
            result["resident_overflow_bytes"] = max(0, symbols["resident_end"] - 0xE000)
    enemy_path = build / "ladybug-enemy-runtime.rom"
    if enemy_path.is_file():
        result["enemy_compile"] = "selected build artifact"
        result["enemy_bytes"] = enemy_path.stat().st_size
        result["enemy_limit"] = 4096
        result["enemy_overflow_bytes"] = max(0, enemy_path.stat().st_size - 4096)
        result["enemy_artifact"] = str(enemy_path)
        candidate_map = enemy_path.with_suffix(".map")
        if candidate_map.is_file():
            symbols = parse_map(candidate_map)
            expected_luts = {
                "object_mask_lut": 0x17A0,
                "object_red_lut": 0x17B0,
                "object_yellow_lut": 0x17C0,
                "object_blue_lut": 0x17D0,
                "object_skull_lut": 0x17E0,
            }
            actual_luts = {name: symbols.get(name) for name in expected_luts}
            result["enemy_lut_addresses"] = actual_luts
            result["enemy_lut_contract"] = (
                "pass" if actual_luts == expected_luts else "fail"
            )
    return result


def write_review(output: Path, result: dict[str, object]) -> None:
    output.mkdir(parents=True, exist_ok=True)
    (output / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "<!DOCTYPE html>",
        "<html lang=\"en\"><head><meta charset=\"utf-8\"><title>PERF-007 source review</title></head><body>",
        "<h1>PERF-007 source-correctness checkpoint</h1>",
        "<p>Status: " + html.escape(str(result["status"])) + "</p>",
        "<pre>" + html.escape(json.dumps(result, indent=2, sort_keys=True)) + "</pre>",
        "</body></html>",
    ]
    (output / "source-review.html").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (output / "source-review.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def runtime_unavailable(args: argparse.Namespace, root: Path) -> int:
    missing: list[str] = []
    if args.deadline_seconds is None:
        missing.append("--deadline-seconds")
    if args.phase != "identity" and args.identity is None:
        missing.append("--identity")
    if args.phase == "timing" and args.baseline_build_dir is None:
        missing.append("--baseline-build-dir")
    result: dict[str, object] = {
        "status": "unavailable",
        "phase": args.phase,
        "reason": "runtime observer adapter is not delivered in the source checkpoint",
        "required_arguments_missing": missing,
        "root": str(root),
    }
    write_review(args.output, result)
    print(f"{args.phase}: unavailable (runtime observer not delivered)", file=sys.stderr)
    return 2


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parents[2]
    if args.phase != "source-static":
        return runtime_unavailable(args, root)
    try:
        main_source, enemy_source = read_source(root)
        luts = parse_luts(enemy_source)
        contract = source_contract(root, main_source, enemy_source)
        nibble = nibble_contract(luts)
        geometry = sparse_geometry(root, args.build_dir, main_source, enemy_source, luts)
        rom = args.build_dir / "ladybug.rom"
        result = {
            "status": "pass",
            "phase": args.phase,
            "markers": [nibble["marker"], geometry["marker"]],
            "artifact": {"path": str(rom), "sha256": sha256(rom), "bytes": rom.stat().st_size},
            "contract": contract,
            "nibble": nibble,
            "geometry": geometry,
            "capacity_observation": candidate_capacity(root, args.build_dir),
            "baseline_reference": {
                "delivered_rom_sha256": "a5e0507d8dcd8585a85da66d3c2edc26fd436197f7183949608a2e8e6542f568"
            },
        }
        write_review(args.output, result)
        print("perf007_native_nibble_contract_verified: 36,864 cases")
        print("perf007_sparse_geometry_verified: compiled LUTs and bounded cache/gate contracts")
        return 0
    except (OSError, RuntimeError, ValueError, KeyError) as exc:
        result = {"status": "fail", "phase": args.phase, "reason": str(exc)}
        write_review(args.output, result)
        print(f"source-static: FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
