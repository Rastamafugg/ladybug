"""Verify BUG-048 instruction credit interruption and credited level palettes."""
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
    "success_marker": "Instruction credit interruption, credited level palette, and following gameplay publication",
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
            "credit_zero_glyph_match": tile(33, 9) == glyph(0, 6),
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


def key(k,on):client.call('inject_key',{'key':k,'action':'press' if on else 'release'})
def tile(frame,x,y):return b''.join(frame[y*1280+x*4+r*160:y*1280+x*4+r*160+4] for r in range(8))
try:
 go('attract_tick_ready');p=(build/'ladybug-presentation-runtime.bin').read_bytes();assert runtime.read_bytes(client,0x1900,len(p))==p
 go('instructions_tick');assert low(0xA5)==b'\x03'
 key(5,True);key(6,True);go('credit_tick');key(5,False);key(6,False)
 assert low(0xA8)==b'\x02';assert low(0xA6)==b'\x03'
 evidence['instruction_credit_preemption']={'credits':2,'screen':3,'pass':True}
 key(1,True);go('start_screen_done');key(1,False)
 assert low(0xA6)==b'\x02' and low(0xA8)==b'\x01'
 go('level_tick')
 if low(0x91)[0]:go('level_tick')
 owner=low(0x8F)[0];frame=runtime.read_owner(client,owner)
 assert tile(frame,33,9)==glyph(1,6),'credit1'
 assert tile(frame,38,11)==glyph(1,3),'PART1'
 assert_record_pixels(default_record,'credited-level',[owner])
 assert set(map(int,cell_pens(frame,18,11)))=={6}
 assert set(map(int,cell_pens(frame,17,17)))=={3,4}
 evidence['credited_level']={'owner':owner,'credit1_white':True,'PART1_blue':True,'TOP_exact':True,'skull6':True,'shell3_4':True}
 go('main_render',main_symbols)
 for _ in range(2):
  go('pft_ready');owner=low(0x8F)[0];frame=runtime.read_owner(client,owner)
  assert tile(frame,33,9)==glyph(1,6)
  assert tile(frame,38,11)==glyph(1,3)
 evidence['following_gameplay_credit_PART']='both publications pass'
 evidence['result']='pass'
except Exception as exc:evidence['result']='fail';evidence['failure']=repr(exc)
finally:
 client.close();monitor.stop(process);(build/'bug048-credited-level.json').write_text(json.dumps(evidence,indent=2)+'\n')
print(evidence)
if evidence['result']!='pass':raise SystemExit(1)
