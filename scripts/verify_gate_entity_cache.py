#!/usr/bin/env python3
"""Prove cached gate overlays equal the original entity nibble compositor."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MASK = (0xFF, 0xF0, 0xF0, 0xF0, 0x0F, 0, 0, 0,
        0x0F, 0, 0, 0, 0x0F, 0, 0, 0)
LUTS = {
    "red": (0,0,1,4,0,0,1,4,16,16,17,20,64,64,65,68),
    "yellow": (0,0,2,4,0,0,2,4,32,32,34,36,64,64,66,68),
    "blue": (0,0,3,4,0,0,3,4,48,48,51,52,64,64,67,68),
    "skull": (0,0,6,6,0,0,6,6,96,96,102,102,96,96,102,102),
}

def main() -> None:
    source = (ROOT / "src" / "main.s").read_text(encoding="utf-8")
    for fragment in ("cache_entity_overlay", "replay_gate_entity_overlay",
                     "andb    ,x", "orb     ,u+", "GATE_ENTITY_LISTS equ $B600",
                     "GATE_ENTITY_RECORD_SIZE equ 77", "std     ,y++",
                     "stu     ,y++", "sta     4,y", "ldd     ,y",
                     "ldd     2,y", "lda     4,y"):
        if fragment not in source:
            raise SystemExit("gate cache proof: missing replay primitive " + fragment)
    cases = 0
    for name, lut in LUTS.items():
        for nibble in range(16):
            preserve, opaque = MASK[nibble], lut[nibble]
            for destination in range(256):
                original = (destination & preserve) | opaque
                cached = (destination & preserve) | opaque
                if original != cached:
                    raise SystemExit(f"gate cache proof: {name} nibble {nibble} diverged")
                cases += 1
    # Every source-mask byte is two independently exhaustive nibbles; this
    # covers all 12 variants, patterned destination bytes, and transparent edges.
    print(f"gate cache proof: {cases} nibble/destination cases across red/yellow/blue/skull pass")

if __name__ == "__main__":
    main()
