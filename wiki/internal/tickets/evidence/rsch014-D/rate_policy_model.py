#!/usr/bin/env python3
"""Decode the Lady Bug ROM enemy-movement rate policy; this is not a runtime emulator."""
from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile
import json

ROM = Path('/home/rastamafugg/mame/roms/ladybug.zip')
EXPECTED_ZIP = '2d62b0194495bea6fa765c733a60c431ce685ab1f965a999d463557ef416ddf8'
LAYOUT = [('l1.c4', 0x0000), ('l2.d4', 0x1000), ('l3.e4', 0x2000),
          ('l4.h4', 0x3000), ('l5.j4', 0x4000), ('l6.k4', 0x5000)]
Z80DASM = Path('/tmp/rsch014-D/extracted/usr/bin/z80dasm')
Z80DASM_DEB_SHA256 = 'f5fd556bd9b3b536a57a15736c2e6ab9e68032b015b0c99364976563edb6a643'
MAME_EXE = Path('/usr/games/mame')
EXPECTED_MAME_SHA256 = '7fb5200f8c62d51ef39af168f0965196efbd53cc3d2b759d9db93118114760e4'
HISTORICAL_SAMPLE = Path(__file__).with_name('historical-bug050-part1-enemy-cadence.json')
EXPECTED_SAMPLE_SHA256 = '8675d9149a62c1404108660afe848a0c3374eb1b069d0d8e6d649dcd3c474134'

def rate(code):
    base = code >> 4
    # ROM $40CC-$40F7 adds one of these unsigned 8-bit fractions to $61B5.
    low = code & 0x0f
    fraction = 0x33 if low & 0x02 else 0x80 if low & 0x04 else 0xcc if low & 0x08 else 0
    return {'code': f'0x{code:02x}', 'whole_steps_per_dispatch': base,
            'fraction_byte_per_dispatch': fraction,
            'mean_steps_per_dispatch': round(base + fraction / 256, 9)}

with ZipFile(ROM) as z:
    zip_hash = sha256(ROM.read_bytes()).hexdigest()
    if zip_hash != EXPECTED_ZIP:
        raise SystemExit(f'ROM ZIP hash mismatch: {zip_hash}')
    members = {name: z.read(name) for name, _ in LAYOUT}

program = bytearray(0x6000)
for name, base in LAYOUT:
    if len(members[name]) != 0x1000:
        raise SystemExit(f'unexpected size: {name}')
    program[base:base + 0x1000] = members[name]

def byte_range(start, length):
    return bytes(program[start:start + length])

# Constant gates make this output fail if the selected routine/table bytes change.
required = {
    0x1f26: bytes.fromhex('3a6560cb4f28053a6f6018033a6e60c9'),
    0x33cf: bytes.fromhex('dd216e603a6560fe002005dd34001803dd3401c9'),
    0x35e3: bytes.fromhex('cd261f21aa60fe0230043609180afe0530043606180236037e2377c9'),
    0x407e: bytes.fromhex('3ab461e60fcaa440'),
    0x4224: bytes.fromhex('dd7e00fe02380a280c'),
    0x065f: bytes.fromhex('c33007'),
    0x40f8: bytes.fromhex('cd261f21a60efe33da05413e325f1600195e21d80e3a0290cb4f200321e80e3ab761cb3fcb3fcb3fcb3f83fe1038023e0f5f197e32c361c9'),
}
for address, expected in required.items():
    if byte_range(address, len(expected)) != expected:
        raise SystemExit(f'ROM code mismatch at ${address:04X}')

part_offsets = list(byte_range(0x0ea6, 51))
easy_medium = list(byte_range(0x0ed8, 16))
hard_hardest = list(byte_range(0x0ee8, 16))
if easy_medium != [0x10] * 6 + [0x12] * 6 + [0x15] * 3 + [0x18]:
    raise SystemExit('unexpected $0ED8 table')
if hard_hardest != [0x10] * 3 + [0x12] * 3 + [0x15] * 4 + [0x18] * 5 + [0x20]:
    raise SystemExit('unexpected $0EE8 table')
if part_offsets[50] != 0x10:
    raise SystemExit('unexpected fallback part offset')

profiles = {'easy_medium_bit1_set': easy_medium, 'hard_hardest_bit1_clear': hard_hardest}
parts = []
for counter in range(1, 51):
    offset = part_offsets[counter]
    row = {'part': counter, 'part_counter': counter, 'offset': offset,
           'start_rate_index': min(15, offset)}
    for profile, table in profiles.items():
        start_index = min(15, offset)
        prior = table[start_index]
        changes = []
        for elapsed_bucket in range(1, 16):
            index = min(15, offset + elapsed_bucket)
            current = table[index]
            if current != prior:
                target_timer = elapsed_bucket * 16
                loops = 96 + (target_timer - 1) * 60
                changes.append({'elapsed_bucket': elapsed_bucket,
                                'logical_loop_calls_from_stage_init': loops,
                                'rate_code': f'0x{current:02x}'})
                prior = current
        row[profile] = {'start_rate_code': f'0x{table[start_index]:02x}',
                        'changes': changes}
    parts.append(row)

blocks = []
for address, length in [(0x0162, 0x14), (0x065f, 0x03), (0x0730, 0x35), (0x0784, 0x30), (0x1f26, 0x10),
                        (0x33cf, 0x14), (0x35e3, 0x1c), (0x39b1, 0xc8),
                        (0x407e, 0x52), (0x40cc, 0x2c), (0x40f8, 0x38), (0x4224, 0x1d),
                        (0x42ba, 0x136)]:
    blocks.append({'address': f'0x{address:04x}', 'length_bytes': length,
                   'sha256': sha256(byte_range(address, length)).hexdigest()})

tool_hash = sha256(Z80DASM.read_bytes()).hexdigest() if Z80DASM.exists() else None
mame_hash = sha256(MAME_EXE.read_bytes()).hexdigest()
if mame_hash != EXPECTED_MAME_SHA256:
    raise SystemExit(f'MAME executable hash mismatch: {mame_hash}')
sample_hash = sha256(HISTORICAL_SAMPLE.read_bytes()).hexdigest()
if sample_hash != EXPECTED_SAMPLE_SHA256:
    raise SystemExit(f'historical sample hash mismatch: {sample_hash}')
result = {
    'schema': 'rsch014-d-arcade-rate-policy-v1',
    'identity': {'driver': 'ladybug', 'mame': '0.220 (unknown)',
                 'mame_executable_sha256': mame_hash,
                 'maincpu_rom_zip_sha256': zip_hash,
                 'maincpu_mapping': [{'member': name, 'base': f'0x{base:04x}',
                                      'length_bytes': len(members[name]),
                                      'sha256': sha256(members[name]).hexdigest()}
                                     for name, base in LAYOUT],
                 'disassembler': {'name': 'z80dasm', 'version': '1.1.5',
                                  'ubuntu_focal_deb_sha256': Z80DASM_DEB_SHA256,
                                  'extracted_executable_sha256': tool_hash}},
    'source_blocks_sha256': blocks,
    'source_policy': {
        'part_counter': {'storage': ['$606E', '$606F'], 'active_player_selector': '$6065',
                         'initial_value': 0, 'increment_routine': '$33CF',
                         'increment_call_sites': ['$04D9', '$0662'],
                         'byte_wrap': 'increment has no cap; values 0x33..0xFF take the constant offset 0x10 path, then the byte wraps to 0x00',
                         'offset_table_address': '$0EA6', 'offsets_for_counters_0_to_50': part_offsets,
                         'active_part_relation': 'First start increments reset counter 0 to 1 at address 0x04D9; later transitions increment at 0x0662. Selector 0x1F26 returns the active-player counter unchanged; 0x40F8 indexes 0x0EA6 with that value. Thus active part N uses counter N before byte wrap.',
                         'counter_51_to_255_offset': 16,
                         'counter_wrap': 'Arcade byte 0xFF increment wraps to 0x00; this ROM behavior is separate from CoCo STAGE rollover.'},
        'difficulty': {'read_port': '$9002 / DSW0', 'selector_bit': 1,
                       'mame_default': '0x03 Easy; current ladybug.cfg contains no DIP override',
                       'bit1_set': 'Easy and Medium use $0ED8',
                       'bit1_clear': 'Hard and Hardest use $0EE8'},
        'rate_tables': {'address_0ed8': [rate(x) for x in easy_medium],
                        'address_0ee8': [rate(x) for x in hard_hardest]},
        'rate_index': 'min(15, part_offset + ($61B7 >> 4))',
        'time_state': {'$61B5': '8-bit fractional movement accumulator; reset to 0 during stage initialization',
                       '$61B6': 'initialized to 0x60 (96 logical-loop calls); on zero reloaded to 0x3C (60)',
                       '$61B7': 'initialized to 0; incremented whenever $61B6 wraps; high nibble is elapsed bucket; saturates at 0xF0 and does not increment further',
                       'first_elapsed_bucket_1': 996,
                       'later_bucket_spacing': 960,
                       'saturation': '0xF0 reached at 14436 logical-loop calls from stage initialization; then elapsed bucket remains 15',
                       'stage_entry': 'stage-transition JP 0x065F targets setup 0x0730; setup calls 0x35E3 and initializes 0x61B6/0x61B7/0x61B8/0x61B5; main loop 0x0784 calls 0x407E at 0x07A9',
                       'unit': 'logical gameplay-loop calls, not assumed raw VBlanks'},
        'movement': {'dispatcher': '$407E, called at $07A9 after $61E1 gate',
                     'rate_code': '$40F8 writes $61C3 from part offset + elapsed bucket',
                     'fractional_step_count': '$40CC-$40F7 converts rate code into one shared integer step count per dispatcher using $61B5; each active enemy repeats $42BA movement until the same count is consumed',
                     'coordinate_step': '$4224 increments/decrements one coordinate unit; the MAME record-to-screen mapping in BUG-050 is one visible pixel per unit'},
        'independent_border_timer': {'routine': '$35E3', 'parts_1': 9, 'parts_2_to_4': 6,
                                     'part_5_and_later': 3, 'unit': 'border-box ticks'},
        'post_vegetable': 'No post-vegetable variable or branch is read by the rate selector; tracked rate-state writes are stage initialization, elapsed timer, and fractional accumulation only.'
    },
    'schedule': {'parts_1_to_50': parts,
                 'parts_51_to_255': 'counter >= 0x33 clamps lookup to table index 50, offset 0x10; incrementing 0xFF wraps to 0x00 and therefore uses table entry 0',
                 'part_1_default_profile': {'stage_start': rate(easy_medium[0]),
                                            'first_rate_change': 'elapsed bucket 6; $61B7 reaches 0x60 after 5796 logical loop calls'},
                 'part_1_hard_profile': {'stage_start': rate(hard_hardest[0]),
                                         'first_rate_change': 'elapsed bucket 3; $61B7 reaches 0x30 after 2916 logical loop calls'}},
    'runtime_anchor': {'evidence': 'historical-bug050-part1-enemy-cadence.json',
                   'historical': True,
                       'evidence_sha256': sample_hash,
                       'MAME_endpoint_frames': [1504, 1528],
                       'endpoint_frame_intervals': 24, 'part': 1,
                       'record_y': ['0x9E', '0xB6'],
                       'visible_pixel_delta': 24,
                       'pose_dwell_frames': 8,
                   'complete_pose_hold_start_frames': [1505, 1513, 1521],
                       'limit': 'Single historical Part-1 movement sample only; no later-stage raw-frame schedule and no proof whether pose selection is clock- or distance-driven.'},    'limits': ['ROM static policy is confirmed for the hashed local ROM; actual live cabinet DIP is not known.',
               'The logical loop polls active-high $9001 bit 7; only the cited Part-1 sample directly measures movement per MAME frame. Static evidence does not prove a strict one-loop-per-VBlank mapping.',
               'This is a deterministic source decoder, not a CoCo runtime measurement or production prototype.']
}
out = Path(__file__).with_name('rate-policy-model.json')
out.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'output': out.name, 'zip_sha256': zip_hash,
                  'parts_in_source_offset_table': len(part_offsets),
                  'easy_medium_table': [f'0x{x:02x}' for x in easy_medium],
                  'hard_hardest_table': [f'0x{x:02x}' for x in hard_hardest],
                  'part1_first_easy_threshold_loop_calls': 5796,
                  'part1_first_hard_threshold_loop_calls': 2916}, indent=2))
