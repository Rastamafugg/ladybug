#!/usr/bin/env python3
"""Attribute XRoar trace cycles to dynamically observed call targets."""

from __future__ import annotations

import argparse
import re
from collections import defaultdict
from pathlib import Path


MAP_RE = re.compile(r"^Symbol: (\w+) .* = ([0-9A-Fa-f]+)$")
TRACE_RE = re.compile(
    r"^([0-9a-f]{4})\|\s+[0-9a-f]+\s+(\w+).* dt=(\d+)$"
)


def load_symbols(paths: list[Path]) -> dict[int, str]:
    symbols: dict[int, str] = {}
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            match = MAP_RE.match(line)
            if match:
                symbols.setdefault(int(match.group(2), 16), match.group(1))
    return symbols


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("--map", action="append", type=Path, required=True)
    parser.add_argument("--frame", type=int, default=-1)
    parser.add_argument("--limit", type=int, default=30)
    args = parser.parse_args()

    symbols = load_symbols(args.map)
    records = []
    for line in args.trace.read_text(encoding="ascii").splitlines():
        match = TRACE_RE.match(line)
        if match:
            records.append(
                (int(match.group(1), 16), match.group(2), int(match.group(3)) // 8)
            )
    frame_pc = next(address for address, name in symbols.items() if name == "frame_render_impl")
    if records and records[0][0] == 0:
        records[0] = (frame_pc, records[0][1], records[0][2])
    starts = [index for index, record in enumerate(records) if record[0] == frame_pc]
    frame = args.frame if args.frame >= 0 else len(starts) + args.frame
    start = starts[frame]
    end = starts[frame + 1] if frame + 1 < len(starts) else len(records)

    stack = [("interval", 0)]
    exclusive: dict[str, int] = defaultdict(int)
    inclusive: dict[str, list[int]] = defaultdict(list)
    calls: dict[str, int] = defaultdict(int)
    elapsed = 0
    for index in range(start, end):
        pc, opcode, cycles = records[index]
        if opcode != "SYNC":
            exclusive[stack[-1][0]] += cycles
            elapsed += cycles
        if opcode in {"BSR", "LBSR", "JSR"} and index + 1 < end:
            target = records[index + 1][0]
            name = symbols.get(target, f"${target:04x}")
            stack.append((name, elapsed))
            calls[name] += 1
        elif opcode in {"RTS", "RTI"} and len(stack) > 1:
            name, call_start = stack.pop()
            inclusive[name].append(elapsed - call_start)

    total = sum(exclusive.values())
    print(f"{args.trace}: frame {frame}, {total} active cycles")
    for name, cycles in sorted(exclusive.items(), key=lambda item: item[1], reverse=True)[: args.limit]:
        durations = inclusive[name]
        detail = ""
        if durations:
            detail = f"  inclusive={sum(durations)} [{min(durations)}..{max(durations)}]"
        print(
            f"{cycles:6d}  {cycles * 100 / total:5.1f}%  {calls[name]:3d}  "
            f"{name}{detail}"
        )


if __name__ == "__main__":
    main()
