#!/usr/bin/env python3
"""Verify the rate prototype table and integrated callsites against the Step-D model."""
import argparse
import hashlib
import json
import re
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument('--model', type=Path, required=True)
ap.add_argument('--source', type=Path, required=True)
ap.add_argument('--helper-bin', type=Path, required=True)
ap.add_argument('--helper-map', type=Path, required=True)
ap.add_argument('--enemy-source', type=Path, required=True)
ap.add_argument('--main-source', type=Path, required=True)
ap.add_argument('--output', type=Path, required=True)
a = ap.parse_args()
model_bytes = a.model.read_bytes()
model = json.loads(model_bytes)
source = a.source.read_text(encoding='utf-8')
enemy_source = a.enemy_source.read_text(encoding='utf-8')
main_source = a.main_source.read_text(encoding='utf-8')
binary = a.helper_bin.read_bytes()
map_text = a.helper_map.read_text(encoding='utf-8')

def sha(data):
    return hashlib.sha256(data).hexdigest()

def symbol(name):
    found = re.findall(rf'^Symbol: {re.escape(name)} .* = ([0-9A-Fa-f]+)$', map_text, re.M)
    if len(found) != 1:
        raise SystemExit(f'expected one map symbol {name}, got {len(found)}')
    return int(found[0], 16)

match = re.search(r'(?m)^\s*fcb\s+([0-9, ]+)\s*$', source)
if not match:
    raise SystemExit('rate offset table not found in prototype source')
prototype_offsets = [int(x.strip(), 10) for x in match.group(1).split(',')]
source_offsets = model['source_policy']['part_counter']['offsets_for_counters_0_to_50']
if prototype_offsets != source_offsets[1:18]:
    raise SystemExit(f'prototype offsets are not source counters 1..17: {prototype_offsets}')
if 'active_part_relation' not in model['source_policy']['part_counter'] or 'active part N uses counter N' not in model['source_policy']['part_counter']['active_part_relation']:
    raise SystemExit('Step-D active part/counter identity proof missing')
if 'deca' not in source or 'lda     a,x' not in source or 'cmpa    #18' not in source:
    raise SystemExit('prototype STAGE one-based selection/clamp instructions changed')
if not (0xA3B0 <= symbol('rate_reset') < symbol('rate_module_end') <= 0xA470):
    raise SystemExit('rate module escaped page-$34 fit interval')
if len(binary) != symbol('rate_module_end') - symbol('rate_reset'):
    raise SystemExit('rate binary length differs from map interval')
if sha(a.source.read_bytes()) != '8a5285b7a936d4b25703ba76a2d27680440a425a15ee6c4363b20181568d4c5a':
    raise SystemExit('rate prototype source differs from the retained integrated init-shim candidate')
if sha(binary) != '6b661f29f60e6e9f296da68ae7d50cdc0ed3f9ecd22c2dc9ee80f790e562c83c':
    raise SystemExit('rate helper binary differs from the retained integrated init-shim candidate')
if symbol('rate_tick') != 0xA3C5:
    raise SystemExit('rate_tick entry drifted from the integrated enemy callsite')
if symbol('rate_enemy_init_shim') != 0xA458 or symbol('rate_module_end') != 0xA45E:
    raise SystemExit('page-$34 true-init shim or bounded helper extent changed')
if not re.search(r'(?m)^\s*jsr\s+\$A3C5\s+; page-\$34 rate helper returns due in Z$', enemy_source):
    raise SystemExit('enemy module no longer calls the rate_tick entry verified by the helper map')
if not re.search(r'(?m)^\s*jsr\s+\$A458\s+; page-\$34 rate reset then true init tail-call$', main_source):
    raise SystemExit('resident init wrapper no longer calls the page-$34 true-init shim')
offsets_file = symbol('rate_stage_offsets') - symbol('rate_reset')
if binary[offsets_file:offsets_file + 17] != bytes(prototype_offsets):
    raise SystemExit('assembled rate table bytes differ from prototype source')
for text in ('cmpa    #6', 'cmpa    #12', 'cmpa    #15'):
    if text not in source:
        raise SystemExit(f'candidate rate threshold missing: {text}')

rate_table = model['source_policy']['rate_tables']['address_0ed8']
schedule = model['schedule']['parts_1_to_50']
if len(rate_table) != 16 or len(schedule) != 50:
    raise SystemExit('unexpected Step-D table/schedule dimensions')
threshold_code = lambda index: 0x10 if index < 6 else 0x12 if index < 12 else 0x15 if index < 15 else 0x18
fraction_by_code = {int(row['code'], 16): row['fraction_byte_per_dispatch'] for row in rate_table}
checks = 0
threshold_checks = 0
for stage, row in enumerate(schedule, 1):
    candidate_offset = prototype_offsets[stage - 1] if stage <= 17 else 15
    if min(15, candidate_offset) != min(15, row['offset']) or row['part_counter'] != stage:
        raise SystemExit(f'part mapping mismatch at stage {stage}: candidate={candidate_offset}, model={row}')
    changes = set(item['elapsed_bucket'] for item in row['easy_medium_bit1_set']['changes'])
    actual_changes = set()
    prior = None
    for bucket in range(16):
        index = min(15, candidate_offset + bucket)
        candidate_code = threshold_code(index)
        expected = rate_table[index]
        if candidate_code != int(expected['code'], 16):
            raise SystemExit(f'rate code mismatch at part {stage}, elapsed bucket {bucket}')
        if fraction_by_code[candidate_code] != expected['fraction_byte_per_dispatch']:
            raise SystemExit(f'fraction mismatch at part {stage}, elapsed bucket {bucket}')
        if prior is not None and prior != candidate_code:
            actual_changes.add(bucket)
        prior = candidate_code
        checks += 1
    if actual_changes != changes:
        raise SystemExit(f'elapsed threshold mismatch at part {stage}: candidate={sorted(actual_changes)}, model={sorted(changes)}')
    threshold_checks += 1
late_checks = 0
for stage in range(51, 256):
    for bucket in range(16):
        candidate_code = threshold_code(min(15, 15 + bucket))
        expected = rate_table[min(15, 16 + bucket)]
        if candidate_code != int(expected['code'], 16) or fraction_by_code[candidate_code] != expected['fraction_byte_per_dispatch']:
            raise SystemExit(f'late-part source clamp differs at stage {stage}, bucket {bucket}')
        late_checks += 1

result = {
    'schema': 'rsch014-r10-rate-policy-fit-v1',
    'result': 'PASS: rate-selection table equivalence only; cadence/freeze behavior remain unaccepted',
    'model_sha256': sha(model_bytes),
    'arcade_rom_zip_sha256': model['identity']['maincpu_rom_zip_sha256'],
    'prototype_source_sha256': sha(a.source.read_bytes()),
    'helper_binary_sha256': sha(binary),
    'integrated_entries': {'rate_tick': f"${symbol('rate_tick'):04X}", 'rate_enemy_init_shim': f"${symbol('rate_enemy_init_shim'):04X}", 'rate_module_end': f"${symbol('rate_module_end'):04X}"},
    'source_callsite_check': 'PASS: enemy runtime JSR target agrees with rate_tick map symbol; init wrapper calls true-init shim',
    'part_slice': {'source_counters': '1..17', 'prototype_array_index': 'STAGE-1', 'stage_1_offset': prototype_offsets[0], 'stage_17_offset': prototype_offsets[-1], 'stage_18_and_later_effective_offset': 15},
    'tested_cells': checks,
    'tested_part_threshold_sets': threshold_checks,
    'tested_late_part_cells': late_checks,
    'late_offset_equivalence': {'candidate_offset': 15, 'source_offset': 16, 'effective_rate_index_after_source_clamp': 15},
    'candidate_elapsed_periods': 'unmapped: helper invokes its timer after CoCo freeze gate and no arcade-loop-to-CoCo-tick conversion is calibrated',
    'source_time_basis': model['source_policy']['time_state']['unit'],
    'source_bucket_1_calls': model['source_policy']['time_state']['first_elapsed_bucket_1'],
    'source_later_bucket_spacing': model['source_policy']['time_state']['later_bucket_spacing'],
    'source_freeze_rule': 'elapsed timer always advances before freeze gate; dispatcher/fractional accumulator is skipped while frozen'
}
a.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result, indent=2))
