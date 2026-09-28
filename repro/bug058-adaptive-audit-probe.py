"""Adaptive module provenance and alias gates; no artifact mutation."""
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
import copy, hashlib, json, sys, tempfile

root, output = map(Path, sys.argv[1:3])
sys.path.insert(0, str(root / 'scripts'))
from source_reference import provenance
from source_reference.audit import build_audit

build = root / 'build'
config = json.loads((build / 'source-reference-adaptive.json').read_text())
receipt = provenance.validate(root, build, config)
audit = json.loads((build / 'source-reference/ownership.json').read_text())
assert audit['errors'] == [], audit['errors']
expected = {'adaptive-mapped', 'adaptive-banked', 'adaptive-active'}
assert expected <= {m['id'] for m in config['modules']}
records = {r['id']: r for r in audit['records']}
assert all(records[n]['module'] == 'adaptive-banked' for n in
           ('adaptive-history-a', 'adaptive-history-b', 'adaptive-state'))
assert records['adaptive-history-a']['interval'] == [0xBC04, 0xBC93]
assert records['adaptive-history-b']['interval'] == [0xBC94, 0xBD23]
assert records['adaptive-state']['interval'] == [0xBD24, 0xBD43]
assert {r['module'] for r in records['adaptive-state']['references']} == expected

rejections = []
# The first validation hashes every build input. Negative cases mutate only the
# in-memory receipt/config, so reuse that certified input set and artifact digests.
original_digest=provenance.digest
digest_cache={str(path): original_digest(path) for path in [build/name for name in receipt['artifacts']] + [root/name for name in receipt['generated_inputs']]}
def cached_digest(path):
    return digest_cache.get(str(path),original_digest(path))
def reject(label, mutated_config=None, mutated_receipt=None):
    try:
        with patch.object(provenance, 'inputs', return_value=receipt['inputs']), patch.object(provenance, 'digest', side_effect=cached_digest):
            return reject_cached(label, mutated_config, mutated_receipt)
    except ValueError as exc:
        rejections.append({'case': label, 'rejection': str(exc)})
    else:
        raise AssertionError('negative gate accepted: ' + label)
def reject_cached(label, mutated_config, mutated_receipt):
        if mutated_receipt is None:
            provenance.validate(root, build, mutated_config)
        else:
            with patch.object(provenance.json, 'loads', return_value=mutated_receipt):
                provenance.validate(root, build, config)

bad = copy.deepcopy(receipt)
bad['generated_inputs']['build/ladybug-adaptive-active.s'] = '0' * 64
reject('stale generated source hash', mutated_receipt=bad)
bad = copy.deepcopy(receipt)
del bad['generated_inputs']['build/ladybug-adaptive-active.s']
reject('missing pre-assembly source receipt', mutated_receipt=bad)
bad = copy.deepcopy(receipt)
for invocation in bad['invocations']:
    if invocation['output']=='ladybug-adaptive-active.bin':
        invocation['generated_source_sha256_before']='0'*64
reject('generated input and invocation differ', mutated_receipt=bad)
reject('default registry cannot certify adaptive outputs',
       json.loads((root / 'scripts/source_reference.json').read_text()))
bad = copy.deepcopy(config)
bad['modules'] = [m for m in bad['modules'] if m['id'] != 'adaptive-mapped']
reject('missing standalone module registration', bad)

with tempfile.TemporaryDirectory() as temporary:
    fixture = Path(temporary); (fixture / 'scripts').mkdir()
    def alias_case(address):
        declaration = dict(id='state', kind='scratch', symbol='STATE', width=32,
            mapping='page34', phases=['foreground'], owner='scheduler',
            initialization='reset', lifetime='active', clobbers='foreground only',
            aliases=['COUNT'], reference_modules=['core', 'active'])
        def module(name, lines, syms):
            return NS(id=name, source_lines=[NS(file='src/'+name+'.s', number=i+1, text=v)
                for i,v in enumerate(lines)], symbols=[NS(name=n, assembled_address=a)
                for n,a in syms.items()], emitted_spans=[])
        core = module('core', ['; @audit '+json.dumps(declaration), 'STATE equ $1000'],
                      {'STATE':0x1000})
        active = module('active', ['COUNT equ $%04X'%address, '        std COUNT'],
                        {'COUNT':address})
        return build_audit(NS(modules=[core,active],revision='fixture'), fixture,
                           {'required':['state']}, {})
    valid = alias_case(0x1014)
    assert not valid['errors'] and valid['records'][0]['minimum_direct_access_extent'] == 22
    assert any('exceeds extent' in e for e in alias_case(0x101F)['errors'])
    assert any('alias outside' in e for e in alias_case(0x1020)['errors'])

rom_hash = hashlib.sha256((build/'ladybug.rom').read_bytes()).hexdigest()
assert rom_hash == 'df5cff4f67f3a09781cd004585d7d78e7f70cce608206052bb97fb3c9aade7d0'
result = dict(status='pass', build_revision=receipt['revision'], rom_sha256=rom_hash,
    module_count=len(config['modules']), generated_inputs=receipt['generated_inputs'],
    negative_gates=rejections, alias_cases=3, audit_errors=audit['errors'],
    discovery_counts=audit['counts'],
    records=[{k:v for k,v in records[n].items() if k in
        ('id','module','interval','minimum_direct_access_extent','aliases','reference_modules')}
        for n in ('adaptive-history-a','adaptive-history-b','adaptive-state')],
    limitations=['Lexical alias/extent checks do not certify indirect dataflow or runtime lifetimes.',
                 'Default inventory isolation is proved by rejection, not a new nonadaptive ROM build.'])
output.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k not in ('records','generated_inputs','negative_gates')}))
