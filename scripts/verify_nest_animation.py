#!/usr/bin/env python3
"""Prove animation-only nest publication matches the full compositor."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"


def proof(path: Path) -> tuple[list[bytes], bytes]:
    data = path.read_bytes()
    if len(data) != 640:
        raise SystemExit(f"nest animation proof: {path} has invalid length")
    return ([data[index * 128:(index + 1) * 128] for index in range(4)], data[512:])


def main() -> None:
    compared = 0
    for owner in ("a", "b"):
        fast_frames, fast_rect = proof(
            BUILD / f"perf-animation-{owner}-fast-proof.bin"
        )
        full_frames, full_rect = proof(
            BUILD / f"perf-animation-{owner}-full-proof.bin"
        )
        if fast_frames != full_frames:
            raise SystemExit("nest animation proof: cache changed between scenarios")
        if fast_rect not in fast_frames or full_rect not in fast_frames:
            raise SystemExit(
                f"nest animation proof: owner {owner.upper()} published an uncached rectangle"
            )
        compared += 2
    print(
        "nest animation proof: fast and full paths published generated "
        f"pixel-exact cache frames in {compared} owner snapshots"
    )


if __name__ == "__main__":
    main()
