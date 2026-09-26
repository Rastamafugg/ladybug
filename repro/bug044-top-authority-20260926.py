"""Verify BUG-044 committed-record TOP rendering and score authority."""
from pathlib import Path
import hashlib
import json
import re
import sys


root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root / "scripts"), str(root / "repro")]
import verify_bug011_runtime as runtime
import verify_bug009_monitor_input as monitor
from rsch013_colour_animation_capture import cell_pens


build = root / "build"
rom = build / "ladybug.rom"
main_symbols = runtime.symbols(build / "ladybug.map")
presentation_symbols = runtime.symbols(build / "ladybug-presentation-runtime.map")
resident = (build / "ladybug-runtime.rom").read_bytes()
descriptor_offset = main_symbols["dynamic_descriptors"] - 0xC000
font_offset = main_symbols["font"] - 0xC000
colour_offset = main_symbols["colour_lut"] - 0xC000
top_colour = main_symbols["TEXT_HIGH_SCORE"]
presentation_source = (build / "ladybug_presentation.inc").read_text(encoding="ascii")
default_constants = {
    name: int(value, 16)
    for name, value in re.findall(
        r"^(PRESENTATION_HIGHSCORE_DEFAULT_NAME_\d+) equ \$([0-9A-Fa-f]+)$",
        presentation_source,
        re.MULTILINE,
    )
}
default_name = bytes(
    default_constants[f"PRESENTATION_HIGHSCORE_DEFAULT_NAME_{index}"]
    for index in range(7)
)
default_record = bytes.fromhex("090000") + default_name

forced_name = "ACE    "
forced_ids = []
for character in forced_name:
    if character == " ":
        forced_ids.append(0)
        continue
    glyph_code = ord(character) - ord("A") + 10
    forced_ids.append(next(
        index for index in range(184)
        if resident[descriptor_offset + 2 * index] == glyph_code
        and resident[descriptor_offset + 2 * index + 1]
    ))
forced_record = bytes.fromhex("123456") + bytes(forced_ids)

evidence = {
    "rom_sha256": hashlib.sha256(rom.read_bytes()).hexdigest(),
    "phase_deadline_seconds": 40,
    "success_marker": "record-derived TOP pixels match on natural default and forced ACE/123456 publications",
    "timeout_meaning": "named runtime publication marker was not reached within its phase deadline",
    "default_record_expected": default_record.hex(),
    "forced_record": forced_record.hex(),
    "captures": [],
}
process, client = runtime.launch_fast(
    monitor,
    Path("/mnt/e/projects/ladybug/docs/reference/xroar/src/xroar"),
    rom,
)


def go(symbol, symbols=presentation_symbols):
    address = symbols[symbol]
    ids = monitor.setup(client, [address])
    try:
        hit = client.run_to_breakpoint(40)
        assert hit.get("pc") == address, (symbol, hit, hex(address))
    finally:
        monitor.clear(client, ids)


def physical(address, length):
    return bytes.fromhex(client.call("read_memory", {
        "space": "physical", "addr": address, "length": length,
    })["data"])


def low(address, length=1):
    return physical(0x38 * 8192 + address, length)


def glyph(code, colour):
    if code is None:
        return bytes(32)
    lut = colour_offset + colour * 32
    output = bytearray()
    for mask in resident[font_offset + code * 8:font_offset + code * 8 + 8]:
        for nibble in (mask >> 4, mask & 15):
            start = lut + nibble * 2
            output.extend(resident[start:start + 2])
    return bytes(output)


def assert_record_pixels(record, phase, owners):
    assert len(record) == 10, (phase, record.hex())
    expected_name = []
    for native_id in record[3:10]:
        if native_id == 0:
            expected_name.append(glyph(None, top_colour))
            continue
        code = resident[descriptor_offset + 2 * native_id]
        assert resident[descriptor_offset + 2 * native_id + 1] != 0
        expected_name.append(glyph(code, top_colour))
    digits = [digit for value in record[:3] for digit in (value >> 4, value & 15)]
    expected_score = [glyph(digit, top_colour) for digit in digits]
    for owner in owners:
        frame = runtime.read_owner(client, owner)

        def tile(x: int, y: int) -> bytes:
            return b"".join(
                frame[y * 1280 + x * 4 + row * 160:y * 1280 + x * 4 + row * 160 + 4]
                for row in range(8)
            )

        for index, expected in enumerate(expected_name):
            actual = tile(33 + index, 5)
            assert actual == expected, (phase, owner, "name", index, actual.hex())
        for index, expected in enumerate(expected_score):
            actual = tile(33 + index, 6)
            assert actual == expected, (phase, owner, "score", index, actual.hex())
        evidence["captures"].append({
            "phase": phase,
            "owner": owner,
            "record": record.hex(),
            "TOP_exact": True,
            "credit_white": tile(33, 9) == glyph(0, 6),
            "cells": {
                f"{x},{y}": cell_pens(frame, x, y)
                for x, y in [(18, 11), (17, 17), (38, 11), (33, 9)]
            },
        })


def assert_live_resident(symbol, length):
    address = main_symbols[symbol]
    expected = resident[address - 0xC000:address - 0xC000 + length]
    actual = physical(0x3E * 8192 + address - 0xC000, length)
    assert actual == expected, (symbol, address, actual.hex(), expected.hex())
    logical = bytes.fromhex(client.call("read_memory", {
        "addr": address, "length": length,
    })["data"])
    assert logical == expected, (symbol, address, logical.hex(), expected.hex())


def call_resident(symbol, deadline=10):
    address = main_symbols[symbol]
    assert_live_resident(symbol, 16)
    saved_regs=client.call("read_registers")
    saved_stub=runtime.read_bytes(client,0x1800,2)
    saved_stack=runtime.read_bytes(client,0x1E00,512)
    client.call("write_memory", {"addr":0x1800,"data":"20fe"})
    client.call("write_memory", {"addr":0x1EFC,"data":"1800"})
    ids=monitor.setup(client,[0x1800])
    try:
        client.call("write_registers",{"pc":address,"s":0x1EFC,"dp":0,"cc":0x50})
        regs=client.call("read_registers")
        assert (regs['pc'],regs['s'],regs['dp'],regs['cc'])==(address,0x1EFC,0,0x50)
        client.call("run")
        hit=client.call("wait_for_stop",{"timeout_ms":int(deadline*1000)},timeout=deadline+2)
        assert hit.get("pc")==0x1800 and hit.get("reason")=="breakpoint",(symbol,hit)
    finally:
        monitor.clear(client,ids)
    client.call("write_memory",{"addr":0x1800,"data":saved_stub.hex()})
    client.call("write_memory",{"addr":0x1E00,"data":saved_stack.hex()})
    client.call("write_registers",{k:saved_regs[k] for k in ('a','b','cc','dp','x','y','u','s','pc')})


try:
    go("attract_tick_ready")
    presentation = (build / "ladybug-presentation-runtime.bin").read_bytes()
    assert runtime.read_bytes(client, 0x1900, len(presentation)) == presentation
    assert_live_resident("startup_seed_ready", 48)
    assert_live_resident("asset_draw_top_hud", 80)

    initial_record = physical(0x34 * 8192 + 0xF84, 10)
    assert initial_record == default_record, initial_record.hex()
    assert low(0xE7) == b"\x00", low(0xE7).hex()
    go("instructions_tick")
    assert_record_pixels(initial_record, "cold-default-instructions", [0, 1])
    assert physical(0x34 * 8192 + 0xF84, 10) == initial_record

    assert_live_resident("add_special_score", 32)
    client.call("write_memory", {
        "space": "physical", "addr": 0x38 * 8192 + 0x1D, "data": "089990",
    })
    client.call("write_memory", {
        "space": "physical", "addr": 0x38 * 8192 + 0x20, "data": "aabbcc",
    })
    evidence["controlled_score_crossing"] = {
        "deadline_seconds": 10,
        "success_marker": "add_special_score returns at $1800 with SCORE_BCD=099990 and TOP unchanged",
        "timeout_meaning": "controlled return marker was not reached within 10 seconds",
        "status": "running",
    }
    call_resident("add_special_score")
    assert low(0x1D, 3) == bytes.fromhex("099990"), low(0x1D, 3).hex()
    assert low(0x20, 3) == bytes.fromhex("aabbcc"), low(0x20, 3).hex()
    assert physical(0x34 * 8192 + 0xF84, 10) == initial_record
    call_resident("asset_draw_top_hud")
    back_owner = low(0x90)[0]
    assert_record_pixels(initial_record, "controlled-score-crossing-top", [back_owner])
    evidence["controlled_score_crossing"].update({
        "status": "pass",
        "score_before": "089990",
        "score_after": low(0x1D, 3).hex(),
        "record0_after": physical(0x34 * 8192 + 0xF84, 10).hex(),
        "back_owner": back_owner,
        "HIGH_BCD_sentinel_after": low(0x20, 3).hex(),
    })

    client.call("write_memory", {
        "space": "physical", "addr": 0x34 * 8192 + 0xF84,
        "data": forced_record.hex(),
    })
    client.call("write_memory", {
        "space": "physical", "addr": 0x38 * 8192 + 0xE7, "data": "01",
    })
    go("level_tick")
    if low(0x91)[0]:
        go("level_tick")
    assert_record_pixels(forced_record, "level-start", [low(0x8F)[0]])
    go("main_render", main_symbols)
    for _ in range(2):
        go("pft_ready")
        assert_record_pixels(forced_record, "demo", [low(0x8F)[0]])
    assert physical(0x34 * 8192 + 0xF84, 10) == forced_record
    evidence["result"] = "pass"
except Exception as exc:
    evidence["result"] = "fail"
    evidence["failure"] = f"{type(exc).__name__}: {exc}"
    if evidence.get("controlled_score_crossing", {}).get("status") == "running":
        evidence["controlled_score_crossing"].update({
            "status": "fail",
            "failure": evidence["failure"],
        })
finally:
    client.close()
    monitor.stop(process)
    (build / "bug044-top-authority-corrected.json").write_text(
        json.dumps(evidence, indent=2) + "\n", encoding="ascii"
    )
print(json.dumps(evidence, indent=2))
if evidence["result"] != "pass":
    raise SystemExit(1)
