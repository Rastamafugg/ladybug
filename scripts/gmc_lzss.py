#!/usr/bin/env python3
"""Shared bounded GMC launch-stream LZSS codec.

Flag bits are consumed least-significant bit first. One selects a literal;
zero selects a two-byte match containing a 12-bit backward distance and a
four-bit length minus three. The declared expanded length terminates a stream.
"""

from __future__ import annotations

WINDOW = 4095
MIN_MATCH = 3
MAX_MATCH = 18


def compress(data: bytes) -> bytes:
    """Return the minimum-byte parse for the bounded GMC LZSS format."""
    matches: list[dict[int, int]] = []
    for cursor in range(len(data)):
        offsets: dict[int, int] = {}
        for candidate in range(max(0, cursor - WINDOW), cursor):
            length = 0
            distance = cursor - candidate
            while (
                length < MAX_MATCH
                and cursor + length < len(data)
                and data[candidate + length % distance] == data[cursor + length]
            ):
                length += 1
            for matched in range(MIN_MATCH, length + 1):
                offsets.setdefault(matched, distance)
        matches.append(offsets)

    infinity = len(data) * 3 + 1
    costs = [[infinity] * 8 for _ in range(len(data) + 1)]
    choices: list[list[tuple[int, int] | None]] = [
        [None] * 8 for _ in range(len(data))
    ]
    costs[-1] = [0] * 8
    for cursor in range(len(data) - 1, -1, -1):
        for slot in range(8):
            group_byte = 1 if slot == 0 else 0
            next_slot = (slot + 1) % 8
            best_cost = group_byte + 1 + costs[cursor + 1][next_slot]
            best_choice = (1, 0)
            for length, distance in matches[cursor].items():
                cost = group_byte + 2 + costs[cursor + length][next_slot]
                if cost < best_cost or (
                    cost == best_cost and length > best_choice[0]
                ):
                    best_cost = cost
                    best_choice = (length, distance)
            costs[cursor][slot] = best_cost
            choices[cursor][slot] = best_choice

    output = bytearray()
    cursor = 0
    while cursor < len(data):
        flag_offset = len(output)
        output.append(0)
        flags = 0
        for bit in range(8):
            if cursor >= len(data):
                break
            choice = choices[cursor][bit]
            if choice is None:
                raise AssertionError("missing LZSS parse choice")
            length, distance = choice
            if length >= MIN_MATCH:
                output.extend(
                    ((distance << 4) | (length - MIN_MATCH)).to_bytes(2, "big")
                )
                cursor += length
            else:
                flags |= 1 << bit
                output.append(data[cursor])
                cursor += 1
        output[flag_offset] = flags
    if len(output) != costs[0][0]:
        raise AssertionError("LZSS parse size differs from optimum")
    return bytes(output)


def decompress(stream: bytes, expanded_length: int) -> bytes:
    """Expand one exact stream and reject truncation, overrun, or trailing data."""
    if expanded_length < 0:
        raise ValueError("expanded length must be non-negative")
    output = bytearray()
    cursor = 0
    while len(output) < expanded_length:
        if cursor >= len(stream):
            raise ValueError("truncated LZSS flag byte")
        flags = stream[cursor]
        cursor += 1
        for bit in range(8):
            if len(output) >= expanded_length:
                break
            if flags & (1 << bit):
                if cursor >= len(stream):
                    raise ValueError("truncated LZSS literal")
                output.append(stream[cursor])
                cursor += 1
                continue
            if cursor + 2 > len(stream):
                raise ValueError("truncated LZSS match")
            token = int.from_bytes(stream[cursor:cursor + 2], "big")
            cursor += 2
            distance = token >> 4
            length = (token & 0x0F) + MIN_MATCH
            if distance == 0 or distance > len(output):
                raise ValueError("invalid LZSS backward distance")
            if len(output) + length > expanded_length:
                raise ValueError("LZSS match overruns declared destination")
            for _ in range(length):
                output.append(output[-distance])
    if cursor != len(stream):
        raise ValueError("LZSS stream has trailing bytes")
    return bytes(output)
