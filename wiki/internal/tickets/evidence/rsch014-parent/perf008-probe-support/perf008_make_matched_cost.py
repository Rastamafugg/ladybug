from pathlib import Path
root=Path('/mnt/e/projects/ladybug')
s=(root/'repro/rsch014_current_triggers_settled.py').read_text()
needle="    frozen=snapshot_pages();natural_regs=c.call('read_registers')"
patch='''    frozen=snapshot_pages();natural_regs=c.call('read_registers')
    e['matched_fixture_sha256']=r.digest(b''.join(frozen[k] for k in sorted(frozen)))
    e['matched_fixture_registers']=natural_regs
    if '--full-pickup-oracle' in sys.argv[3:]:
        start=ms['check_entity_pickup']-0xC000;end=ms['cep_skull']-0xC000
        offset=resident.index(bytes([0x8A,0x20,0x97,0x7F]),start,end)
        assert read(0xC000+offset,4)==resident[offset:offset+4],'ordinary pickup source/live opcode identity'
        write(0xC000+offset+1,[8])
        assert read(0xC000+offset,4)==bytes([0x8A,8,0x97,0x7F]),'full pickup intent live override'
        e['full_pickup_override']={'address':0xC000+offset+1,'from':32,'to':8,'scope':'Controlled single immediate-byte replacement after cold exact delivery; original full-layer history flag, same candidate ROM and initial fixture.'}
'''
assert needle in s;s=s.replace(needle,patch)
s=s.replace("'C3 reference ROM; current enemy/render binary differs.'", "'Guarded candidate ROM, source 03f5b69 plus isolated selective research; controlled baseline differs only in ordinary-pickup intent immediate after exact delivery.'")
(root/'repro/perf008_matched_cost.py').write_text(s)
