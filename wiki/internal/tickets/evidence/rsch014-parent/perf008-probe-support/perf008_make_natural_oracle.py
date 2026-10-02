from pathlib import Path
root=Path('/mnt/e/projects/ladybug')
s=(root/'repro/rsch014_current_triggers_settled.py').read_text()
s=s.replace('profile_enabled=False\nresident=', 'profile_enabled=False\noracle_enabled=False\nresident=',1)
s=s.replace("    if not profile_enabled:go(ms['mainloop'])",'''    if not profile_enabled:
        if oracle_enabled:
            go(act['adaptive_render'])
            entry=c.call('read_registers');saved=snapshot_pages()
            return_pc=int.from_bytes(read(entry['s'],2),'big')
            helper=act['pickup_key_prepare'];original=read(helper,5)
            assert original==stage[helper-0x38F:helper-0x38F+5],'key helper identity'
            # Full background oracle preserves RF_DOT as well as rebuilding
            # entities, so ordinary dot keys in the same history remain valid.
            write(helper,[0x86,0x28,0x97,0x7F,0x39])
            c.call('write_registers',{'cc':entry['cc']|0x50});go(return_pc)
            owner=read(0x90)[0];full=r.read_owner(c,owner)
            restore_pages(saved);write(helper,original)
            c.call('write_registers',{k:entry[k] for k in ('a','b','dp','x','y','u','s','pc')})
            c.call('write_registers',{'cc':entry['cc']|0x50});go(return_pc)
            selected=r.read_owner(c,owner)
            diffs=[j for j,(a,z) in enumerate(zip(full,selected)) if a!=z]
            result={'phase':'actual gameplay simulation followed by render','logical':before['logical'],'owner_secondary':owner,'matching_bytes':30720-len(diffs),'first_differences':diffs[:16],'full_sha256':r.digest(full),'selective_sha256':r.digest(selected)}
            e.setdefault('natural_render_oracles',[]).append(result)
            assert not diffs,result
            regs=c.call('read_registers');c.call('write_registers',{'cc':(regs['cc']&~0x50)|(entry['cc']&0x50)})
        go(ms['mainloop'])''')
s=s.replace("                profile_enabled=index<2 or (name=='gate rotation' and index in (7,8))", "                profile_enabled=False\n                oracle_enabled=name=='pickup' and index<58")
s=s.replace("'C3 reference ROM; current enemy/render binary differs.'", "'Research candidate at guarded source 03f5b69; oracle passes advance emulator time, so cycle/debt rows are not performance measurements.'")
s=s.replace("    e['status']='scoped-pass'", "    assert len(e.get('natural_render_oracles',[]))==58,'58 real trigger/history/popup oracle frames required'\n    e['status']='scoped-pass'")
(root/'repro/perf008_natural_oracle.py').write_text(s)
