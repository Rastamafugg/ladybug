#!/usr/bin/env python3
"""Prove bank-0 overflow packing at the exact usable-source boundary."""

from __future__ import annotations

from build_sparse_sprites import (
    BOOT_OVERFLOW_PROOF,
    BOOT_OVERFLOW_START,
    BANK2_PAYLOAD_START,
    CART_READABLE_BYTES,
    ENEMY_RUNTIME_OFFSET,
    ENEMY_RUNTIME_RESERVED,
    SIGNATURE_OFFSET,
    pack_candidate_banks,
)


def source_capacity() -> int:
    return (
        (CART_READABLE_BYTES - BANK2_PAYLOAD_START)
        + (CART_READABLE_BYTES - ENEMY_RUNTIME_OFFSET - ENEMY_RUNTIME_RESERVED)
        + SIGNATURE_OFFSET
        + (ENEMY_RUNTIME_OFFSET - SIGNATURE_OFFSET - 2)
        + (CART_READABLE_BYTES - BOOT_OVERFLOW_START - len(BOOT_OVERFLOW_PROOF))
    )


def reconstruct(banks: dict[int, bytes], segments, target: str, size: int) -> bytes:
    output = bytearray(size)
    coverage = bytearray(size)
    for segment in segments:
        if segment.target != target:
            continue
        start = segment.target_offset
        end = start + segment.count
        output[start:end] = banks[segment.bank][
            segment.source_offset:segment.source_offset + segment.count
        ]
        coverage[start:end] = b"\x01" * segment.count
    if not all(coverage):
        raise SystemExit("GMC overflow proof: reconstructed target has gaps")
    return bytes(output)


def main() -> None:
    capacity = source_capacity()
    payload = bytes((index * 37 + 11) & 0xFF for index in range(capacity))
    bank0, bank2, bank3, segments = pack_candidate_banks(
        payload, b"", b"", b"", b""
    )
    banks = {0: bank0, 2: bank2, 3: bank3}
    if reconstruct(banks, segments, "enemy", len(payload)) != payload:
        raise SystemExit("GMC overflow proof: exact-boundary reconstruction differs")
    payload_segments = [segment for segment in segments if segment.target == "enemy"]
    if not any(segment.bank == 0 for segment in payload_segments):
        raise SystemExit("GMC overflow proof: exact-boundary case did not spill to bank 0")
    final = payload_segments[-1]
    if final.bank != 0 or final.source_offset + final.count != CART_READABLE_BYTES:
        raise SystemExit("GMC overflow proof: exact-boundary case did not end at $3E00")
    try:
        pack_candidate_banks(payload + b"\x00", b"", b"", b"", b"")
    except ValueError as error:
        if "exceed CPU-readable GMC capacity" not in str(error):
            raise
    else:
        raise SystemExit("GMC overflow proof: one-byte excess did not fail")
    print(
        "GMC overflow proof: exact boundary reconstructs across banks 2/3/0; "
        "one-byte excess fails"
    )


if __name__ == "__main__":
    main()
