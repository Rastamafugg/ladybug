#!/usr/bin/env python3
"""Copy an XRoar snapshot while patching CPU-visible or physical RAM."""

from __future__ import annotations

import argparse
from pathlib import Path

from read_snapshot import RAM_LEN, RAM_MARKER, cpu_to_phys


def assignment_parts(assignment: str) -> tuple[int, str]:
    raw_address, value = assignment.split("=", 1)
    return int(raw_address, 16), value


def patch_snapshot(
    source: Path,
    target: Path,
    patches: list[str],
    cpu_files: list[str] | None = None,
    phys_files: list[str] | None = None,
) -> None:
    snapshot = bytearray(source.read_bytes())
    marker = snapshot.find(RAM_MARKER)
    if marker < 0:
        raise SystemExit("patch snapshot: RAM marker not found")
    ram_start = marker + len(RAM_MARKER)
    if ram_start + RAM_LEN > len(snapshot):
        raise SystemExit("patch snapshot: RAM payload is truncated")

    def copy_blob(offset: int, path: Path) -> None:
        data = path.read_bytes()
        if not 0 <= offset <= RAM_LEN - len(data):
            raise SystemExit(
                f"patch snapshot: {path} at physical ${offset:05X} exceeds RAM"
            )
        snapshot[ram_start + offset:ram_start + offset + len(data)] = data

    for assignment in cpu_files or []:
        address, raw_path = assignment_parts(assignment)
        copy_blob(cpu_to_phys(address), Path(raw_path))

    for assignment in phys_files or []:
        address, raw_path = assignment_parts(assignment)
        copy_blob(address, Path(raw_path))

    for assignment in patches:
        address, raw_value = assignment_parts(assignment)
        value = int(raw_value, 16)
        if not 0 <= value <= 0xFF:
            raise SystemExit(f"patch snapshot: byte out of range: {assignment}")
        snapshot[ram_start + cpu_to_phys(address)] = value

    target.write_bytes(snapshot)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    parser.add_argument("patch", nargs="*", help="ADDR=BYTE, both hexadecimal")
    parser.add_argument(
        "--cpu-file",
        action="append",
        default=[],
        metavar="ADDR=FILE",
        help="copy FILE to RAM beginning at a CPU-visible hexadecimal address",
    )
    parser.add_argument(
        "--phys-file",
        action="append",
        default=[],
        metavar="ADDR=FILE",
        help="copy FILE to RAM beginning at a physical hexadecimal address",
    )
    args = parser.parse_args()
    patch_snapshot(
        args.source,
        args.target,
        args.patch,
        args.cpu_file,
        args.phys_file,
    )


if __name__ == "__main__":
    main()
