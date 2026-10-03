#!/usr/bin/env python3
"""Static source, map, and state-model checks for the isolated R10 AD0 candidate."""
import argparse
import hashlib
import json
import re
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument('--artifacts', type=Path, required=True)
ap.add_argument('--model', type=Path, required=True)
ap.add_argument('--output', type=Path, required=True)
a = ap.parse_args()

def sha(data):
    return hashlib.sha256(data).hexdigest()

def require(condition, message):
    if not condition:
        raise SystemExit(message)

root = a.artifacts
def read(name):
    return (root / name).read_bytes()

expected = {
    'ladybug.rom': '3e1d206c05e95a9dc545f744ecc1953b2cbdcbce7854aede2232ae14475b7300',
    'ladybug-sparse-layout.json': 'd76a98ba30149abf7b2cb7066988d940ed458738f39e9ea09d7fcd3c4758d93e',
    'source-build-receipt.json': '8302656b257eed7e6c71637bce6954a363427596262588f1a573d40d2c0a961c',
    'ladybug-rate-helper.bin': '609e0e8199a17c5d9a6bf35f7a3f0cddeb8ba029bdb5b8fa6bf2eed6b9efc00c',
    'ladybug-enemy-helper-page34.bin': '057e2803eac24aebb1447d43614fd4aaf67518d933f08d3f128627e9aeb26526',
    'main.s': '7824c831eff41f263f2f44549875bc09b96cba8babcad1f3193fb4ae4a3ab5bb',
    'enemy_runtime.s': 'ef04cfa9963cff3d1ef3a6b350112dcf6935bc51c21f577f5253c9252662d333',
    'prototype_rate_page34.s': 'ed972b6d29df79559f8f1d76c5f9405eaf42b541ee1e1d687f0b63737a4c6880',
}
for name, digest in expected.items():
    require(sha(read(name)) == digest, f'{name} hash differs from frozen candidate')

artifact_hashes = json.loads(read('artifacts.sha256.json'))
for name, digest in artifact_hashes.items():
    require(sha(read(name)) == digest, f'frozen artifact hash mismatch: {name}')

helper = read('ladybug-rate-helper.bin')
helper_map = read('ladybug-rate-helper.map').decode('utf-8')
helper_lst = read('ladybug-rate-helper.lst').decode('utf-8')
source = read('prototype_rate_page34.s').decode('utf-8')
enemy_source = read('enemy_runtime.s').decode('utf-8')
main_source = read('main.s').decode('utf-8')

def symbol(name):
    found = re.findall(rf'^Symbol: {re.escape(name)} .* = ([0-9A-Fa-f]+)$', helper_map, re.M)
    require(len(found) == 1, f'expected one map symbol {name}, got {len(found)}')
    return int(found[0], 16)

symbols = {name: symbol(name) for name in (
    'rate_reset', 'rate_tick', 'rate_enemy_init_shim', 'rate_module_end', 'rate_stage_offsets')}
require(symbols == {
    'rate_reset': 0xA3B0, 'rate_tick': 0xA3C5,
    'rate_enemy_init_shim': 0xA463, 'rate_module_end': 0xA469,
    'rate_stage_offsets': 0xA452,
}, f'unexpected page-$34 symbols: {symbols}')
require(len(helper) == 185 == symbols['rate_module_end'] - symbols['rate_reset'],
        'rate helper does not occupy 185 mapped bytes')
require(0xA3B0 <= symbols['rate_reset'] < symbols['rate_module_end'] <= 0xA470,
        'rate helper escaped the 192-byte A3B0-A46F extent')

def listing_has(address, mnemonic, operands):
    pattern = rf'(?m)^{address:04X}\s+\S+\s+.*\b{mnemonic}\s+{re.escape(operands)}\s*$'
    return re.search(pattern, helper_lst, re.I) is not None

# Every elapsed-time route reaches the freeze gate, including saturated bucket.
for address, mnemonic, operand in [
    (0xA3C5, 'dec', 'RATE_TIMER'), (0xA3C8, 'bne', 'rt_freeze_gate'),
    (0xA3D2, 'cmpa', '#$F0'), (0xA3D4, 'bhs', 'rt_freeze_gate'),
    (0xA3DE, 'bne', 'rt_freeze_gate'), (0xA3E0, 'lbsr', 'rate_select'),
    (0xA3E3, 'ldd', 'FREEZE_TIMER'), (0xA3E5, 'beq', 'rt_accumulate'),
    (0xA3E7, 'subd', '#1'), (0xA3EA, 'std', 'FREEZE_TIMER'),
    (0xA3EC, 'clra', ';'), (0xA3ED, 'rts', ''),
    (0xA3EE, 'lda', 'RATE_FRAC'), (0xA3F1, 'adda', 'RATE_ADDEND'),
]:
    # CLRA has no operand; permit its trailing source comment.
    if mnemonic == 'clra':
        require(re.search(rf'(?m)^{address:04X}\s+\S+\s+.*\bclra\s+;', helper_lst, re.I),
                'frozen return no longer clears A before RTS')
    elif mnemonic == 'rts':
        require(re.search(rf'(?m)^{address:04X}\s+\S+\s+.*\brts\s*$', helper_lst, re.I),
                'frozen path no longer returns before fraction accumulation')
    else:
        require(listing_has(address, mnemonic, operand),
                f'expected machine listing instruction {address:04X} {mnemonic} {operand}')
require(re.search(r'cmpa\s+#\$F0\s*\n\s*bhs\s+rt_freeze_gate', source, re.I),
        'saturated RATE_BUCKET path bypasses freeze gate in source')

require(re.search(r'(?m)^\s*jsr\s+\$A3C5\b', enemy_source) and
        'page-$34 elapsed then freeze gate; due in Z' in enemy_source,
        'enemy runtime call target differs from rate_tick')
require(re.search(r'(?m)^\s*jsr\s+\$A463\b', main_source) and
        'page-$34 rate reset then true init tail-call' in main_source,
        'resident init call target differs from rate_enemy_init_shim')
require(re.search(r'08EE\s+BDA3C5\s+.*jsr\s+\$A3C5', read('ladybug-enemy-runtime.lst').decode('utf-8')),
        'assembled enemy module does not call rate_tick at the expected site')
require(re.search(r'D572\s+BDA463\s+.*jsr\s+\$A463', read('ladybug.lst').decode('utf-8')),
        'assembled resident does not call the true-init shim at the expected site')

# The death-state branch intentionally bypasses the rate helper in this candidate.
tick_start = re.search(r'(?m)^enemy_tick_impl\s*$', enemy_source)
death_gate = re.search(r'(?m)^\s*tst\s+DEATH_STATE\s*\n\s*bne\s+et_render_test\s*$', enemy_source)
tick_call = re.search(r'(?m)^\s*jsr\s+\$A3C5\b', enemy_source)
require(tick_start and death_gate and tick_call and tick_start.start() < death_gate.start() < tick_call.start(),
        'death-state bypass no longer precedes rate_tick')
require(len(re.findall(r'(?m)^\s*jsr\s+\$A3C5\b', enemy_source)) == 1,
        'candidate adds or removes a rate_tick callsite')
require(re.search(r'(?m)^\s*ldd\s+#300\s*\n\s*std\s+FREEZE_TIMER\s*$', enemy_source),
        'existing CoCo 300-count freeze-duration adaptation changed')

# Verify that the array is the source counters 1..17 slice and bytes match.
table = re.search(r'(?m)^\s*fcb\s+([0-9, ]+)\s*$', source)
require(table is not None, 'rate-stage offset table missing')
offsets = [int(x.strip()) for x in table.group(1).split(',')]
model_bytes = a.model.read_bytes()
model = json.loads(model_bytes)
source_offsets = model['source_policy']['part_counter']['offsets_for_counters_0_to_50']
require(offsets == source_offsets[1:18], 'prototype array is not the source index-1..17 slice')
require('active_part_relation' in model['source_policy']['part_counter'] and
        'active part N uses counter N' in model['source_policy']['part_counter']['active_part_relation'],
        'Step-D active-PartN/counterN relation missing')
require('deca' in source and 'lda     a,x' in source and 'cmpa    #18' in source,
        'one-based STAGE-to-array indexing/clamp changed')
table_offset = symbols['rate_stage_offsets'] - symbols['rate_reset']
require(helper[table_offset:table_offset + 17] == bytes(offsets), 'assembled table bytes differ from source')

rate_table = model['source_policy']['rate_tables']['address_0ed8']
schedule = model['schedule']['parts_1_to_50']
require(len(rate_table) == 16 and len(schedule) == 50, 'unexpected Step-D model dimensions')
def threshold_code(index):
    return 0x10 if index < 6 else 0x12 if index < 12 else 0x15 if index < 15 else 0x18
fraction_by_code = {int(row['code'], 16): row['fraction_byte_per_dispatch'] for row in rate_table}
cells = threshold_sets = 0
for stage, row in enumerate(schedule, 1):
    offset = offsets[stage - 1] if stage <= 17 else 15
    require(row['part_counter'] == stage and min(15, offset) == min(15, row['offset']),
            f'active part/counter mismatch at {stage}')
    model_changes = {entry['elapsed_bucket'] for entry in row['easy_medium_bit1_set']['changes']}
    candidate_changes = set()
    prior = None
    for bucket in range(16):
        index = min(15, offset + bucket)
        code = threshold_code(index)
        expected_row = rate_table[index]
        require(code == int(expected_row['code'], 16) and
                fraction_by_code[code] == expected_row['fraction_byte_per_dispatch'],
                f'rate policy mismatch at active part {stage}, bucket {bucket}')
        if prior is not None and prior != code:
            candidate_changes.add(bucket)
        prior = code
        cells += 1
    require(candidate_changes == model_changes, f'threshold set mismatch at active part {stage}')
    threshold_sets += 1
late_cells = 0
for stage in range(51, 256):
    for bucket in range(16):
        code = threshold_code(min(15, 15 + bucket))
        expected_row = rate_table[min(15, 16 + bucket)]
        require(code == int(expected_row['code'], 16) and
                fraction_by_code[code] == expected_row['fraction_byte_per_dispatch'],
                f'late-part mapping mismatch at part {stage}, bucket {bucket}')
        late_cells += 1

# Small model of the assembled rate_tick control flow, not an emulator test.
def selected_addend(stage, bucket):
    offset = offsets[stage - 1] if stage <= 17 else 15
    index = min(15, offset + (bucket >> 4))
    return 0 if index < 6 else 0x33 if index < 12 else 0x80 if index < 15 else 0xCC

def tick(timer, bucket, frac, addend, phase, freeze, stage=1):
    timer = (timer - 1) & 0xFF
    if timer == 0:
        timer = 60
        if bucket < 0xF0:
            bucket += 1
            if bucket & 0x0F == 0:
                addend = selected_addend(stage, bucket)
    if freeze:
        return timer, bucket, frac, addend, phase, freeze - 1, False
    total = frac + addend
    frac = total & 0xFF
    if total > 0xFF:
        return timer, bucket, frac, addend, phase, freeze, True
    if phase:
        return timer, bucket, frac, addend, 0, freeze, True
    return timer, bucket, frac, addend, 1, freeze, False

cases = []
for name, timer, freeze in [('bucket_f0_expiry', 1, 2), ('bucket_f0_nonexpiry', 2, 1)]:
    before = (timer, 0xF0, 0x71, 0xCC, 1, freeze)
    after = tick(*before)
    require(after[2] == before[2] and after[4] == before[4] and after[5] == freeze - 1 and not after[6],
            f'{name} changed fraction/phase or failed to decrement freeze once')
    require(after[0] == (60 if timer == 1 else timer - 1) and after[1] == 0xF0,
            f'{name} failed elapsed/saturation transition')
    cases.append({'case': name, 'result': 'PASS: elapsed timer advances; frozen fraction/phase hold; freeze decrements once'})

# Bucket rollover selects a new rate before the same call reaches the freeze gate.
selection_cases = []
for name, bucket, stage in [
    ('bucket_0f_to_10_stage1_frozen', 0x0F, 1),
    ('bucket_0f_to_10_stage17_frozen', 0x0F, 17),
    ('bucket_ef_to_f0_stage1_frozen', 0xEF, 1),
    ('bucket_ef_to_f0_stage17_frozen', 0xEF, 17),
]:
    before = (1, bucket, 0x99, 0xCC if stage == 1 and bucket == 0x0F else 0, 1, 2)
    after = tick(*before, stage=stage)
    require(after[0] == 60 and after[1] == bucket + 1 and
            after[2] == before[2] and after[4] == before[4] and
            after[5] == 1 and not after[6], f'{name} bypassed freeze after selector update')
    require(after[3] == selected_addend(stage, bucket + 1), f'{name} did not use the selected stage offset')
    selection_cases.append({'case': name, 'stage_offset': offsets[stage - 1],
                            'selected_addend': f"${after[3]:02X}",
                            'result': 'PASS: bucket selector updates before gate; freeze still decrements and fraction/phase hold'})
cases.extend(selection_cases)

# Saturated thaw 1->0 returns without motion; the following callback gets one addend only.
before = (2, 0xF0, 0xF0, 0x20, 1, 1)
thaw = tick(*before)
require(thaw == (1, 0xF0, 0xF0, 0x20, 1, 0, False), 'freeze 1->0 callback moved before thaw')
carry = tick(*thaw[:5], thaw[5])
require(carry == (60, 0xF0, 0x10, 0x20, 1, 0, True), 'first thaw callback carry result differs')
no_carry_before = (3, 0xF0, 1, 0x20, 0, 0)
no_carry = tick(*no_carry_before)
require(no_carry == (2, 0xF0, 0x21, 0x20, 1, 0, False), 'first thaw callback no-carry result differs')
cases.extend([
    {'case': 'thaw_1_to_0', 'result': 'PASS: thawing callback returns without movement; next callback applies one addend'},
    {'case': 'thaw_fraction_carry', 'result': 'PASS: one addend carries; phase stays unchanged; due=1'},
    {'case': 'thaw_fraction_no_carry', 'result': 'PASS: one addend does not carry; phase advances once; due=0'},
    {'case': 'death_state_bypass', 'result': 'PASS: source branch precedes rate_tick; static control-flow check only'},
])

manifest = json.loads(read('ladybug-sparse-layout.json'))
segments = manifest['gmc']['segments']
def segment(target):
    matches = [s for s in segments if s['target'] == target]
    require(len(matches) == 1, f'expected one sparse segment for {target}')
    return matches[0]
rate_segment = segment('rate_helper')
e2_segment = segment('enemy_helper_page34')
presentation_segments = [s for s in segments if s['target'] == 'presentation_auxiliary']
require(rate_segment['destination_page'] == 0x34 and rate_segment['destination_address'] == 0xA3B0 and rate_segment['count'] == 185,
        'rate helper sparse destination differs')
require(e2_segment['destination_page'] == 0x34 and e2_segment['destination_address'] == 0xA8A0 and e2_segment['count'] == 87,
        'E2 helper sparse destination/hash contract differs')
require(any(s['destination_page'] == 0x23 and s['destination_address'] == 0xA422 for s in presentation_segments),
        'presentation source page 23 / A422 segment not distinguished from page 34')

result = {
    'schema': 'rsch014-r10-freeze-order-static-v1',
    'profile': 'complete AD0 keyboard only',
    'result': 'PASS: frozen source/map/listing/model checks; not runtime or cadence acceptance',
    'model_sha256': sha(model_bytes),
    'frozen_hashes': {name: sha(read(name)) for name in expected},
    'rate_helper': {'start': '$A3B0', 'tick': '$A3C5', 'init_shim': '$A463', 'end_exclusive': '$A469', 'bytes': len(helper), 'extent': 192, 'free': 192 - len(helper)},
    'call_sites': {'enemy': 'enemy module $08EE bytes BDA3C5 -> page-$34 rate_tick $A3C5', 'init': 'resident $D572 bytes BDA463 -> rate_enemy_init_shim $A463'},
    'source_policy_table_only': {'part_bucket_cells': cells, 'part_threshold_sets': threshold_sets, 'late_part_cells': late_cells, 'part_slice': 'source counters 1..17, array index STAGE-1; stage 18+ clamps to offset 15'},
    'state_machine_cases': cases,
    'state_model_stage_coverage': 'Stage offsets are applied from the exact source table for the explicit stage 1 and stage 17 rollover cases; this is not an exhaustive stage runtime model.',
    'page_identity': {'rate_helper': 'physical page $34 -> $A3B0', 'E2_helper': 'physical page $34 -> $A8A0, exact 87-byte hash retained', 'presentation_auxiliary': 'physical page $23 -> $A422'},
    'freeze_duration': 'Existing CoCo LDD #300 / STD FREEZE_TIMER adaptation retained unchanged; no duration-policy change is included.',
    'adaptive_helper_contract': {'required_for_AD1_profiles': '696/698 bytes, SHA-256 3827719dd6d237bd994e072748ef9756a2b113872b897ab561574655d8f590ab', 'AD0_keyboard_profile': 'adaptive helper not present; contract not reverified by this profile'},
    'behavior_limits': ['No per-actor elapsed debt is modeled or added.', 'DEATH_STATE bypass is source/control-flow only.', 'Arcade logical-loop cadence to CoCo rate_tick calls is uncalibrated.', 'No emulator or native-hardware execution was performed.'],
}
a.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result, indent=2))
