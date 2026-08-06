#!/usr/bin/env python3
"""Verify skull collectibles remain outside the bonus-colour palette path."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "src/main.s").read_text(encoding="utf-8")


def main() -> int:
    draw_start = SOURCE.index("\ndraw_entity_object\n") + 1
    draw = SOURCE[draw_start : SOURCE.index("\n; Store the original", draw_start)]
    skull = draw[draw.index("cmpa    #ENTITY_SKULL") : draw.index("\ndeo_bonus\n")]
    skull_code = "\n".join(line.split(";", 1)[0] for line in skull.splitlines())
    if "lda     #COLOR_YELLOW" not in skull_code or "lda     #COLOR_WHITE" not in skull_code:
        raise SystemExit("BUG-004 skull branch does not select fixed white colours")
    if "leau    object_skull_lut,pcr" not in skull_code:
        raise SystemExit("BUG-004 skull branch does not select the static skull LUT")
    if "BONUS_COLOR" in skull_code:
        raise SystemExit("BUG-004 skull branch reads BONUS_COLOR")

    lut = SOURCE[SOURCE.index("object_skull_lut\n") : SOURCE.index("\n;==============================================================================", SOURCE.index("object_skull_lut\n"))]
    if "fcb     $00,$00,$06,$06" not in lut or "fcb     $60,$60,$66,$66" not in lut:
        raise SystemExit("BUG-004 skull LUT is not the fixed white mapping")

    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    report = {
        "source_commit": commit,
        "skull_palette": ["COLOR_YELLOW", "COLOR_WHITE"],
        "skull_lut": "object_skull_lut",
        "bonus_color_read_in_skull_branch": False,
        "executable_change_required": False,
        "pass": True,
    }
    output = ROOT / "build" / "bug-004-skull-colour-cycle.json"
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("BUG-004 skull colour cycle: fixed-white LUT invariant passes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
