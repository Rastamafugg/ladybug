from pathlib import Path

root = Path('/mnt/e/projects/ladybug')
source = (root/'repro/rsch014_current_triggers_settled.py').read_text()
start = source.index("    if '--pickup-gate-cadence'")
end = source.index("    e['status']='scoped-pass'", start)
probe = '''    # Reuse cold entry, exact-delivery, four-roaming and snapshot machinery.
    # Compare the actual reducer + closure with a full-entity oracle callback.
    # Each pair starts from identical physical RAM, metadata and journal bytes.
    bs=r.symbols(b/'ladybug-adaptive-banked.map')
    helper_entry=act['pickup_key_prepare']
    helper_original=read(helper_entry,5)
    helper_full=bytes([0x86,8,0x97,0x7F,0x39])
    e['oracle_definition']='Same candidate ROM and actual reducer/actor closure; replace only pickup_key_prepare with LDA #RF_ENTITIES / STA RENDER_FLAGS / RTS in the oracle pass. IRQ-masked component transactions, not timing evidence.'
    e['oracle_patch']={'address':helper_entry,'original':helper_original.hex(),'replacement':helper_full.hex()}
    e['pixel_cases']=[]
    table=read(ms['ENTITY_TABLE'],read(ms['ENTITY_COUNT'])[0]*4)
    eligible=[i for i in range(len(table)//4) if table[i*4+2] in (2,3)]
    assert len(eligible)>=2,'two distinct ordinary records required'
    def key(cell,colour=False):
        packet=bytearray(18);packet[0]=0x20;packet[1]=16 if colour else 0;packet[16:18]=bytes(cell)
        return bytes(packet)
    def records(items):
        write(0xBC04,bytes(288));write(0xBD38,[0,0])
        for owner in (0,1):
            write(0xBC04+owner*144,b''.join(items));write(0xBD38+owner,[len(items)])
    def reset(owner):
        restore_pages(frozen);write(helper_entry,helper_original)
        write(0x8F,[1-owner,owner,0]);write(0x7F,bytes(16))
    def remove(i):
        write(ms['ENTITY_TABLE']+i*4+2,[0])
        return tuple(read(ms['ENTITY_TABLE']+i*4,2))
    def render(oracle):
        write(helper_entry,helper_full if oracle else helper_original)
        assert read(helper_entry,5)==(helper_full if oracle else helper_original),'oracle or candidate live bytes'
        cycles,regs=call(act['adaptive_render'])
        assert not regs['cc']&1,'component render refused'
        owner=read(0x90)[0]
        call(bs['adaptive_complete'],owner)
        pixels=r.read_owner(c,owner)
        call(es['framebuffer_finish_back'])
        assert read(0x91)==bytes([1]) or read(0x8F)[0]==owner,'neither armed nor naturally published'
        return pixels,cycles
    def pair(name,owner,setup,items=None):
        global deadline
        deadline=time.monotonic()+45;reset(owner)
        packets=setup()
        if packets is not None:records(packets)
        before=snapshot_pages()
        full,full_cycles=render(True)
        restore_pages(before);write(helper_entry,helper_original)
        selected,selected_cycles=render(False)
        diffs=[i for i,(a,z) in enumerate(zip(full,selected)) if a!=z]
        row={'scenario':name,'owner_secondary':owner,'matching_bytes':30720-len(diffs),'full_sha256':r.digest(full),'selective_sha256':r.digest(selected),'first_differences':diffs[:16],'component_cycles_full':full_cycles,'component_cycles_selective':selected_cycles}
        e['pixel_cases'].append(row)
        assert not diffs,row
        assert read(0xBD38+owner)==b'\\0','completed history not retired'
        return selected
    for owner in (0,1):
        for i in eligible:
            pair('ordinary removal with four roaming sprites',owner,lambda i=i:[key(remove(i))])
        pair('same-cell later dot supersedes removal',owner,lambda:[key(remove(eligible[0]))]*2)
        pair('distinct retained removals',owner,lambda:[key(remove(i)) for i in eligible[:2]])
        def coloured():
            cell=remove(eligible[0]);old=read(ms['BONUS_COLOR'])[0]
            write(ms['BONUS_COLOR'],[1 if old!=1 else 2]);return [key(cell,True)]
        pair('global colour then keyed removal',owner,coloured)
        for target in ((12,10),(12,14)):
            def nest(target=target):
                i=eligible[0]
                call(es['framebuffer_prepare_back']);call(es['actor_closure_restore'])
                write(ms['ENTITY_X'],table[i*4:i*4+2]);call(ms['restore_entity_footprint'])
                write(ms['ENTITY_TABLE']+i*4,target);call(ms['build_gate_entity_lists'])
                write(0x7F,[8]);call(es['frame_render_background']);call(es['actor_closure_draw'])
                call(es['framebuffer_capture_back']);write(0x7F,bytes(16))
                return [key(remove(i))]
            pair('structural nest removal '+str(target),owner,nest)
        reset(owner)
        unions=read(ms['GATE_ENTITY_LISTS'],20*77)
        overlap=None
        for i in eligible:
            x,y=table[i*4:i*4+2]
            for gate_id in range(20):
                row=unions[gate_id*77:(gate_id+1)*77]
                if x>=row[0] and x-1<=row[2] and y>=row[1] and y-1<=row[3]:
                    survivors=[]
                    for j in range(row[4]):
                        pointer=int.from_bytes(row[5+j*6:7+j*6],'big')
                        k=(pointer-ms['ENTITY_TABLE'])//4
                        if 0<=k<len(table)//4 and k!=i and table[k*4+2]:survivors.append(k)
                    if survivors:overlap=(i,gate_id,survivors);break
            if overlap:break
        forced=overlap is None
        if forced:overlap=(eligible[0],0,[eligible[1]])
        e['forced_gate_fixture']={'removed_index':overlap[0],'gate_id':overlap[1],'survivors':overlap[2]}
        def gate_fixture():
            if forced:
                call(es['framebuffer_prepare_back']);call(es['actor_closure_restore'])
                for i,target in zip(eligible[:2],((4,2),(6,2))):
                    write(ms['ENTITY_X'],table[i*4:i*4+2]);call(ms['restore_entity_footprint'])
                    write(ms['ENTITY_TABLE']+i*4,target)
                call(ms['build_gate_entity_lists'])
                association=read(ms['GATE_ENTITY_LISTS'],77)
                indices=[(int.from_bytes(association[5+j*6:7+j*6],'big')-ms['ENTITY_TABLE'])//4 for j in range(association[4])]
                assert all(i in indices for i in eligible[:2]),('forced gate association absent',indices)
                write(0x7F,[8]);call(es['frame_render_background']);call(es['actor_closure_draw'])
                call(es['framebuffer_capture_back']);write(0x7F,bytes(16))
            return remove(overlap[0])
        pair('gate visual-neighbour union with surviving collectible',owner,lambda:[key(gate_fixture())])
        def animated():
            i,gate_id,_=overlap
            cell=gate_fixture()
            write(ms['GATE_ANIM_ID'],[gate_id+1]);write(ms['GATE_ANIM_STYLE'],[0])
            row=bytearray(key(cell));row[9]=gate_id+1;row[10]=0;row[14]=0
            return [bytes(row)]
        pair('pending diagonal gate callback after removal',owner,animated)
        def deferred_final():
            diagonal=animated()[0];records([diagonal])
            call(act['adaptive_render']);call(es['framebuffer_capture_back'])
            write(0x7F,bytes(16));call(ms['finish_gate_animation'])
            assert read(ms['GATE_ANIM_ID'])==b'\\0' and read(ms['RENDER_GATE_MODE'])==b'\\1','final gate transition absent'
            packet=bytearray(read(0x7F,16)+read(9,2));packet[0]|=0x20
            packet[16:18]=diagonal[16:18]
            return [diagonal,bytes(packet)]
        pair('retained removal plus deferred final gate transition',owner,deferred_final)
        def skull():
            count=0
            for i in range(len(table)//4):
                if table[i*4+2]==1:remove(i);count+=1
            assert count,'skull batch absent'
            row=bytearray(18);row[0]=8;return [bytes(row)]
        pair('skull batch full fallback',owner,skull)
        def stage():
            cell=remove(eligible[0]);row=bytearray(18);row[0]=64
            return [key(cell),bytes(row)]
        pair('stage supersedes retained removal',owner,stage)
    # Actual journals retain the other history across natural owner switches.
    # This is a controlled intent sequence, not a claim of naturally earned keys.
    for first in (0,1):
        deadline=time.monotonic()+45;reset(first);records([])
        for step,i in enumerate((eligible[0],None,eligible[1],None)):
            if i is not None:
                cell=remove(i)
                for owner in (0,1):
                    count=read(0xBD38+owner)[0]
                    write(0xBC04+owner*144+count*18,key(cell));write(0xBD38+owner,[count+1])
            owner=read(0x90)[0];before=snapshot_pages()
            full,_=render(True);restore_pages(before);write(helper_entry,helper_original)
            selected,_=render(False)
            assert full==selected,('alternating sequence',first,step)
            e['pixel_cases'].append({'scenario':'alternating retained history and later actor recapture','first_owner_secondary':first,'step':step,'owner_secondary':owner,'matching_bytes':30720,'sha256':r.digest(selected)})
            if read(0x91)==bytes([1]):call(es['framebuffer_irq_impl'])
            assert read(0x90)[0]==1-owner and read(0x91)==b'\\0','natural publication owner switch absent'
    write(helper_entry,helper_original)
    e['required_scenarios_present']=['ordinary moving actors','same-cell revisit','distinct removal','colour/key','skull fallback','stage supersession','alternating retained histories']
'''
source = source[:start]+probe+source[end:]
source=source.replace("'C3 reference ROM; current enemy/render binary differs.'", "'Research candidate full ROM at guarded source 03f5b69; selective source unapproved.'")
(root/'repro/perf008_publication_probe.py').write_text(source)
