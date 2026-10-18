"""Focused A1-S/A1-P decoder for the compiled Attract admission helper."""
from __future__ import annotations

import re


HELPER_BASE = 0x06B2
EXPECTED_HELPER_BYTES = 334


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def parse_symbols(map_text: str) -> dict[str, int]:
    symbols: dict[str, int] = {}
    for line in map_text.splitlines():
        match = re.match(r"^Symbol: (\S+)\s+.* = ([0-9A-Fa-f]+)$", line)
        if match:
            name, value = match.group(1), int(match.group(2), 16)
            require(name not in symbols, f"helper map symbol {name} is ambiguous")
            symbols[name] = value
    return symbols


def parse_listing(listing: str) -> list[tuple[int, bytes, str]]:
    result: list[tuple[int, bytes, str]] = []
    for line in listing.splitlines():
        match = re.match(r"^\s*([0-9A-Fa-f]{4})\s+([0-9A-Fa-f]{2,8})\s+\([^)]*\):\d+\s+(.*?)\s*$", line)
        if match:
            statement = re.sub(r"\s+", " ", match.group(3).strip().lower())
            result.append((int(match.group(1), 16), bytes.fromhex(match.group(2)), statement))
    return result


def _symbol(symbols: dict[str, int], name: str) -> int:
    require(name in symbols, f"compiled helper map symbol {name} is missing")
    return symbols[name]


def _row(rows: list[tuple[int, bytes, str]], address: int, statement: str) -> bytes:
    wanted = re.sub(r"\s+", " ", statement.strip().lower())
    matches = [code for pc, code, text in rows if pc == address and text == wanted]
    require(len(matches) == 1, f"compiled listing lacks unique {statement!r} at ${address:04X}")
    return matches[0]


def _branch_target(rows: list[tuple[int, bytes, str]], address: int, opcode: int) -> int:
    matches = [code for pc, code, _ in rows if pc == address]
    require(len(matches) == 1 and len(matches[0]) == 2 and matches[0][0] == opcode,
            f"short branch opcode/bytes invalid at ${address:04X}")
    displacement = matches[0][1]
    if displacement & 0x80:
        displacement -= 0x100
    return address + 2 + displacement


def _match_image(image: bytes, address: int, code: bytes, description: str) -> None:
    offset = address - HELPER_BASE
    require(0 <= offset <= len(image) - len(code), f"{description} lies outside packaged helper bytes")
    require(image[offset:offset + len(code)] == code,
            f"listing bytes for {description} disagree with packaged helper at ${address:04X}")


def verify_helper_contract(
    image: bytes,
    symbols: dict[str, int],
    rows: list[tuple[int, bytes, str]],
) -> dict[str, int | str]:
    """Decode the approved guard, BSR, phase returns and cap from one image/map/listing set."""
    overlay = _symbol(symbols, "presentation_attract_overlay_impl")
    helper_start = _symbol(symbols, "PERIMETER_RESET_HELPER")
    phase = _symbol(symbols, "presentation_attract_phase")
    done = _symbol(symbols, "pao_done")
    phase_change = _symbol(symbols, "pao_phase_change")
    pending = _symbol(symbols, "PENDING")
    actor_phase = _symbol(symbols, "PRES_ACTOR_PHASE")
    prepare = _symbol(symbols, "PRES_MAIN_FB_PREPARE")
    end = _symbol(symbols, "PERIMETER_PRESENTATION_HELPER_END")
    phase_zero = _symbol(symbols, "presentation_phase_zero")
    hold_source = _symbol(symbols, "hold_source_pages")
    require(helper_start == HELPER_BASE, "compiled helper map start differs from the approved $06B2 base")

    # Check this first so the frozen 331-byte negative image fails specifically for
    # the absent admission guard, before the final helper-size assertion.
    tst = phase_change - 4
    guard_offset = tst - HELPER_BASE
    guard_bytes = image[guard_offset:guard_offset + 2] if guard_offset >= 0 else b""
    require(guard_bytes == bytes((0x0D, pending & 0xFF)),
            f"TST PENDING admission guard is absent at ${tst:04X}")
    require(_row(rows, tst, "tst PENDING") == guard_bytes,
            f"compiled listing does not identify TST PENDING at ${tst:04X}")

    require(len(image) == EXPECTED_HELPER_BYTES,
            f"compiled helper is {len(image)}/{EXPECTED_HELPER_BYTES} bytes")
    require(end == HELPER_BASE + len(image), "helper end symbol does not equal the exact packaged image end")

    call = overlay
    compare = overlay + 2
    equal = overlay + 4
    bne = tst + 2
    store = phase_change
    prepare_call = phase_change + 2
    require(tst == equal + 2 and store == bne + 2,
            "TST/BNE guard is not contiguous after BEQ and directly before the phase-cache store")

    call_code = _row(rows, call, "bsr presentation_attract_phase")
    compare_code = _row(rows, compare, "cmpa PRES_ACTOR_PHASE")
    equal_code = _row(rows, equal, "beq pao_done")
    bne_code = _row(rows, bne, "bne pao_done")
    store_code = _row(rows, store, "sta PRES_ACTOR_PHASE")
    prepare_code = _row(rows, prepare_call, "jsr PRES_MAIN_FB_PREPARE")
    for address, code, description in (
        (call, call_code, "phase BSR"), (compare, compare_code, "phase compare"),
        (equal, equal_code, "equal-phase branch"), (tst, guard_bytes, "admission TST"),
        (bne, bne_code, "admission BNE"), (store, store_code, "phase-cache store"),
        (prepare_call, prepare_code, "framebuffer prepare JSR"),
    ):
        _match_image(image, address, code, description)

    require(len(call_code) == 2 and call_code[0] == 0x8D and call + 2 == compare,
            "phase call is not a short BSR returning to the phase-compare continuation")
    bsr_displacement = call_code[1] - 0x100 if call_code[1] & 0x80 else call_code[1]
    require(call + 2 + bsr_displacement == phase and -128 <= bsr_displacement <= 127,
            "compiled BSR target/range does not match presentation_attract_phase")
    require(compare_code == bytes((0x91, actor_phase & 0xFF)),
            "compiled phase-compare operand does not match PRES_ACTOR_PHASE")
    require(equal_code[0] == 0x27 and _branch_target(rows, equal, 0x27) == done,
            "compiled BEQ does not reach the map-qualified pao_done label")
    require(bne_code[0] == 0x26 and _branch_target(rows, bne, 0x26) == done,
            "compiled BNE does not reach the map-qualified pao_done label")
    require(store_code == bytes((0x97, actor_phase & 0xFF)),
            "compiled cache-store operand does not match PRES_ACTOR_PHASE")
    require(prepare_code == bytes((0xBD, prepare >> 8, prepare & 0xFF)),
            "compiled JSR target does not match PRES_MAIN_FB_PREPARE")

    done_code = _row(rows, done, "rts")
    _match_image(image, done, done_code, "pao_done RTS")
    require(done_code == b"\x39", "guard destination is not a byte-qualified RTS")
    normal_returns = [(pc, code) for pc, code, statement in rows
                      if phase <= pc < phase_zero and statement == "rts"]
    zero_returns = [(pc, code) for pc, code, statement in rows
                    if phase_zero <= pc < hold_source and statement == "rts"]
    require(len(normal_returns) == len(zero_returns) == 1
            and normal_returns[0][1] == zero_returns[0][1] == b"\x39",
            "normal and zero phase paths do not each contain one RTS")
    for address, code, description in (
        (normal_returns[0][0], normal_returns[0][1], "normal phase RTS"),
        (zero_returns[0][0], zero_returns[0][1], "zero phase RTS"),
    ):
        _match_image(image, address, code, description)

    return {
        "helper_bytes": len(image), "helper_end": end,
        "overlay": overlay, "bsr": call, "bsr_target": phase,
        "bsr_return": call + 2, "compare": compare,
        "guard_tst": tst, "guard_bne": bne, "pao_done": done,
        "phase_change": phase_change, "prepare_call": prepare_call,
        "prepare_target": prepare, "normal_phase_rts": normal_returns[0][0],
        "zero_phase_rts": zero_returns[0][0],
    }
