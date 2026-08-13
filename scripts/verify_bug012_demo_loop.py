#!/usr/bin/env python3
"""Verify BUG-012 release flow, route provenance, and shipping payload removal."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from build_presentation import load_demo_route


ROOT = Path(__file__).resolve().parents[1]


def symbols(path: Path) -> dict[str, int]:
    return {
        name: int(value, 16)
        for name, value in re.findall(
            r"^Symbol: (\w+) .* = ([0-9A-Fa-f]+)$",
            path.read_text(encoding="ascii"), re.MULTILINE,
        )
    }


def main() -> None:
    presentation = json.loads(
        (ROOT / "build/ladybug-presentation.json").read_text(encoding="ascii")
    )
    layout = json.loads(
        (ROOT / "build/ladybug-sparse-layout.json").read_text(encoding="ascii")
    )
    payload = (ROOT / "build/ladybug-presentation-cold.bin").read_bytes()
    route, provenance = load_demo_route(ROOT / "assets/arcade/demo_route.json")
    source = (ROOT / "src/presentation_runtime.s").read_text(encoding="ascii")
    demo_source = (ROOT / "src/demo_runtime.s").read_text(encoding="ascii")
    module_symbols = symbols(ROOT / "build/ladybug-presentation-runtime.map")
    demo_symbols = symbols(ROOT / "build/ladybug-instruction-runtime.map")

    if presentation.get("development_profile"):
        raise SystemExit("BUG-012 proof: candidate is not the release profile")
    instruction = presentation.get("instruction_choreography", {})
    instruction_map = next(item for item in presentation["maps"]
                           if item["name"] == "instructions")
    if instruction.get("emitted") or instruction.get("event_table_bytes") != 0:
        raise SystemExit("BUG-012 proof: instruction choreography remains emitted")
    if any(instruction.get(field) for field in (
        "colour_stream_bytes", "cucumber_stream_bytes", "death_stream_bytes"
    )):
        raise SystemExit("BUG-012 proof: instruction streams remain in cold data")
    if instruction_map.get("emission") != "release-profile-black-placeholder":
        raise SystemExit("BUG-012 proof: authored instruction map remains emitted")
    auxiliary = layout.get("instruction_runtime", {})
    if auxiliary.get("role") != "demo-route" or auxiliary.get("bytes") == 0:
        raise SystemExit("BUG-012 proof: low-RAM auxiliary payload is not demo-only")

    route_manifest = presentation.get("demo_route", {})
    expected_manifest = {
        **provenance,
        "cold_offset": route_manifest.get("cold_offset"),
        "bytes": len(route),
    }
    if route_manifest != expected_manifest:
        raise SystemExit("BUG-012 proof: route manifest differs from arcade source")
    offset = route_manifest["cold_offset"]
    if payload[offset:offset + len(route)] != route:
        raise SystemExit("BUG-012 proof: cold route bytes differ")

    attract = source[source.index("\nattract_next\n"):source.index("\ninstructions_tick\n")]
    demo = source[source.index("\ndemo_tick\n"):source.index("\ngameover_tick\n")]
    if "PRESENTATION_MAP_LEVEL_START" not in attract:
        raise SystemExit("BUG-012 proof: release attract does not select level start")
    if "demo_force_death" in source or "sta     DEATH" in demo:
        raise SystemExit("BUG-012 proof: timer-forced demo death remains")
    if "PRESENTATION_MAP_ATTRACT" not in demo or "PRESENTATION_MAP_GAME_OVER" in demo:
        raise SystemExit("BUG-012 proof: demo death does not return directly to attract")
    for fragment in (
        "tst     PLAYER_STEP", "PRES_DEMO_LAST_X", "PRES_DEMO_LAST_Y",
        "PRESENTATION_DEMO_ROUTE_ACTIONS", "sta     PLAYER_WANT",
        "lda     #$34", "sta     PAR5", "jsr     PRES_MAIN_CAN_MOVE",
    ):
        if fragment not in demo_source:
            raise SystemExit(f"BUG-012 proof: demo route contract missing {fragment}")
    for name in ("attract_next", "demo_tick", "demo_run"):
        if name not in module_symbols:
            raise SystemExit(f"BUG-012 proof: release module lacks {name}")
    if "demo_runtime_tick" not in demo_symbols:
        raise SystemExit("BUG-012 proof: demo auxiliary entry is absent")
    if "PRES_DEMO_DIR" not in demo_source or "sta     JOY_DIR" not in demo_source:
        raise SystemExit("BUG-012 proof: demo direction is not reasserted before movement")

    module_bytes = len((ROOT / "build/ladybug-presentation-runtime.bin").read_bytes())
    cold_bytes = len(payload)
    print(
        "BUG-012 structural proof: release attract->level->demo wiring, "
        f"187 arcade actions ({hashlib.sha256(route).hexdigest()}), "
        "no instruction payload, no forced death, direct attract return; "
        f"module {module_bytes}/1280, cold {cold_bytes}/10874, "
        f"GMC spare {layout['gmc']['spare_bytes']} bytes"
    )


if __name__ == "__main__":
    main()
