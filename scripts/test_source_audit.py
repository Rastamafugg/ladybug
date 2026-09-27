"""DOC-010 focused risks; no emulator or game-state mutation required."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace as NS
import tempfile
import unittest
from source_reference.audit import access, overlap_errors, build_audit
from source_reference.provenance import inputs, validate, digest

class OperandTests(unittest.TestCase):
    def test_width_and_address(self):
        self.assertEqual(access('        ldx #RING_BASE', 'RING_BASE')['width'], 0)
        self.assertEqual(access('        std RING_BASE', 'RING_BASE')['width'], 2)
        self.assertEqual(access('        sta RING_BASE+1', 'RING_BASE')['offset'], 1)
        self.assertEqual(access('        ldb RING_BASE', 'RING_BASE')['width'], 1)
        self.assertEqual(access('        lda [RING_BASE]', 'RING_BASE')['access'], 'unresolved-indirect')
        self.assertEqual(access('        lda RING_BASE,x', 'RING_BASE')['offset'], None)
        self.assertEqual(access('        fdb RING_BASE', 'RING_BASE')['access'], 'expression')
        self.assertEqual(access('        clr RING_BASE', 'RING_BASE')['access'], 'write')
    def test_collision_and_permitted_sharing(self):
        a=dict(id='pointer', address=0x9e,width=2,mapping='DP',phases=['render'])
        b=dict(id='colour', address=0x9f,width=1,mapping='DP',phases=['render'])
        self.assertTrue(overlap_errors([a,b]))
        self.assertFalse(overlap_errors([a,dict(b,mapping='page34')]))
        self.assertFalse(overlap_errors([a,dict(b,phases=['boot'])]))
        self.assertFalse(overlap_errors([dict(a,alias_group='union',alias_reason='Sequential exclusive operations'),dict(b,alias_group='union',alias_reason='Sequential exclusive operations')]))
        self.assertTrue(overlap_errors([dict(a,alias_group='union'),dict(b,alias_group='union')]))

class ContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name); (self.root/'scripts').mkdir()
        (self.root/'scripts/generator.py').write_text('# @audit-producer '+json.dumps(dict(id='generator',symbols=['INDEX'],function='generate'))+'\ndef generate(): pass\n')
        (self.root/'scripts/check.py').write_text('# existing verifier\n')
        self.record=dict(id='index',kind='index',symbol='INDEX',producer='generator',domain='Graphic ID',encoding='byte',bounds=[0,255])
        self.lines=['; @audit '+json.dumps(self.record),'INDEX equ 131','; @audit-use '+json.dumps(dict(id='index',symbol='INDEX')),'        ldb #INDEX','entry','        rts']
    def audit(self, lines=None, value=131, required=None):
        lines=lines or self.lines
        source=[NS(file='src/fixture.s',number=i,text=text) for i,text in enumerate(lines,1)]
        symbols=[NS(name='INDEX',assembled_address=value),NS(name='entry',assembled_address=0x1000)]
        module=NS(id='fixture',source_lines=source,symbols=symbols,emitted_spans=[])
        project=NS(modules=[module],revision='fixture')
        return build_audit(project,self.root,{'required':required or ['index']},{})
    def test_good_index_and_shifted_lines(self):
        a=self.audit(); self.assertEqual(a['errors'],[])
        b=self.audit(['; inserted line']+self.lines,value=132)
        self.assertEqual(b['errors'],[])
        self.assertEqual(b['records'][0]['definition']['line'],a['records'][0]['definition']['line']+1)
        self.assertEqual(b['records'][0]['address'],132)
    def test_literal_index_rejected(self):
        lines=list(self.lines); lines[3]='        ldb #161'
        self.assertTrue(any('obsolete' in e for e in self.audit(lines)['errors']))
    def test_bounds_rejected(self):
        self.assertTrue(any('bounds' in e for e in self.audit(value=256)['errors']))
    def test_missing_producer(self):
        (self.root/'scripts/generator.py').write_text('')
        self.assertTrue(any('producer' in e for e in self.audit()['errors']))
    def test_missing_consumer_annotation(self):
        self.assertTrue(any('missing declared index consumer' in e for e in self.audit(self.lines[:2]+self.lines[3:])['errors']))
    def test_missing_producer_function(self):
        p=self.root/'scripts/generator.py'
        p.write_text(p.read_text().replace('def generate()', 'def renamed()'))
        self.assertTrue(any('producer function' in e for e in self.audit()['errors']))
    def test_wrong_producer_symbol(self):
        p=self.root/'scripts/generator.py'
        p.write_text(p.read_text().replace('INDEX', 'OTHER'))
        self.assertTrue(any('does not declare symbol' in e for e in self.audit()['errors']))
    def test_duplicate_identity(self):
        self.assertTrue(any('duplicat' in e for e in self.audit([self.lines[0]]+self.lines)['errors']))
    def test_generated_mirror_mismatch(self):
        record=dict(self.record,mirrors=[['INDEX','entry']])
        self.assertTrue(any('mirror mismatch' in e for e in self.audit(['; @audit '+json.dumps(record)]+self.lines[1:])['errors']))
    def test_scratch_allocation_and_access_extent(self):
        record=dict(id='scratch',kind='scratch',symbol='entry',width=2,mapping='DP',phases=['render'],owner='renderer',initialization='before use',lifetime='call',clobbers='D')
        lines=['; @audit '+json.dumps(record),'entry','        rmb 2','        std entry']
        self.assertEqual(self.audit(lines,required=['scratch'])['errors'],[])
        self.assertTrue(any('exceeds extent' in e for e in self.audit(lines+['        std entry+1'],required=['scratch'])['errors']))
        lines[2]='        rmb 1'
        self.assertTrue(any('differs from allocation' in e for e in self.audit(lines,required=['scratch'])['errors']))
    def test_missing_required_record(self):
        self.assertTrue(any('required ownership' in e for e in self.audit(self.lines[1:])['errors']))
    def test_background_links_and_contract(self):
        record=dict(id='background',kind='background',symbol='entry',owner='BACK',extent='128 bytes',clean_source='actor-free BACK',capture=['entry'],restore=['entry'],draw=['entry'],validity=['entry'],invalidation=['entry'],publication=['entry'],order='restore capture draw publish',overlap='closure',verifier=['scripts/check.py'])
        lines=['; @audit '+json.dumps(record), 'entry','        rts']
        self.assertEqual(self.audit(lines,required=['background'])['errors'],[])
        record['invalidation']=['missing']
        self.assertTrue(any('dangling' in e for e in self.audit(['; @audit '+json.dumps(record)]+lines[1:],required=['background'])['errors']))
        record.pop('invalidation')
        self.assertTrue(any('missing background' in e for e in self.audit(['; @audit '+json.dumps(record)]+lines[1:],required=['background'])['errors']))

class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name); self.build=self.root/'build'; self.build.mkdir()
        (self.root/'src').mkdir(); (self.root/'src/a.s').write_text('        rts\n')
        (self.build/'a.bin').write_bytes(b'\x39')
        (self.build/'a.lst').write_text('listing fixture')
        (self.build/'a.map').write_text('map fixture')
        self.module=dict(source='src/a.s',output='a.bin',listing='a.lst',map='a.map')
        self.receipt=dict(state='complete',profile='complete',inputs=inputs(self.root),artifacts={name:digest(self.build/name) for name in ('a.bin','a.lst','a.map')},invocations=[self.module])
        self.config={'modules':[dict(source='src/a.s',binary='a.bin',listing='a.lst',map='a.map')]}
    def write(self):
        (self.build/'source-build-receipt.json').write_text(json.dumps(self.receipt))
    def test_no_receipt(self):
        with self.assertRaisesRegex(ValueError,'missing build'): validate(self.root,self.build,self.config)
    def test_unchanged(self):
        self.write(); validate(self.root,self.build,self.config)
    def test_stale_source_not_recertified(self):
        self.write(); (self.root/'src/a.s').write_text('; changed\n        rts\n')
        with self.assertRaisesRegex(ValueError,'stale build inputs'): validate(self.root,self.build,self.config)
    def test_changed_artifact(self):
        self.write(); (self.build/'a.bin').write_bytes(b'\x12')
        with self.assertRaisesRegex(ValueError,'stale build artifact'): validate(self.root,self.build,self.config)
    def test_unregistered_module(self):
        self.receipt['invocations'].append(dict(self.module,output='b.bin')); self.write()
        with self.assertRaisesRegex(ValueError,'inventory mismatch'): validate(self.root,self.build,self.config)
    def test_wrong_profile_mapping(self):
        self.receipt['invocations'][0]['source']='src/b.s'; self.write()
        with self.assertRaisesRegex(ValueError,'identity mismatch'): validate(self.root,self.build,self.config)
    def test_wrong_conditional_profile(self):
        self.config['modules'][0]['defines']={'HELPER':1}
        self.receipt['invocations'][0]['arguments']=['-DHELPER=0']; self.write()
        with self.assertRaisesRegex(ValueError,'profile mismatch'): validate(self.root,self.build,self.config)
    def test_missing_output_hash(self):
        del self.receipt['artifacts']['a.map']; self.write()
        with self.assertRaisesRegex(ValueError,'missing required artifact provenance'): validate(self.root,self.build,self.config)
    def test_interrupted(self):
        self.receipt['state']='building'; self.write()
        with self.assertRaisesRegex(ValueError,'incomplete'): validate(self.root,self.build,self.config)

if __name__=='__main__': unittest.main()
