from pathlib import Path
import sys
source_path = Path('repro/feat007/gmc_boot_probe.py').resolve()
sys.path.insert(0, str(source_path.parent))
source = source_path.read_text()
needle = "        client.call('inject_key',dict(key=5,action='press'))"
probe = r"""
        print('phase=natural-demo-multiplier marker=mainloop with MULTIPLIER in {2,3,5} deadline=40s; timeout=demo pickup not observed',flush=True)
        deadline=b.time.monotonic()+40
        demo_frames=0
        natural_demo=None
        while b.time.monotonic()<deadline:
            bp=b.set_breakpoint(client,main['mainloop'])
            try:
                hit=b.run_to_breakpoint(client,10)
                assert hit['pc']==main['mainloop'],hit
            finally:
                client.call('pause');b.clear_breakpoint(client,bp)
            demo_frames+=1
            if demo_frames%8:continue
            multiplier=b.read_bytes(client,main['MULTIPLIER'],1)[0]
            route=b.read_bytes(client,0xDA,1)[0]
            if multiplier not in (2,3,5):continue
            for _ in range(4):
                bp=b.set_breakpoint(client,main['mainloop'])
                try:
                    hit=b.run_to_breakpoint(client,10)
                    assert hit['pc']==main['mainloop'],hit
                finally:
                    client.call('pause');b.clear_breakpoint(client,bp)
            xpos={2:1,3:3,5:5}[multiplier]
            owner=b.read_bytes(client,main['FB_FRONT_ID'],1)[0]&1
            saved=b.read_bytes(client,0xFFA1,5)
            try:
                first=0x30-owner*4
                client.call('write_memory',dict(addr=0xFFA1,data=bytes(range(first,first+4)).hex()))
                pixels=b.read_bytes(client,0x2000,30720)
            finally:
                client.call('write_memory',dict(addr=0xFFA1,data=saved.hex()))
            native=bytes.fromhex('0000000000000000000300030000303000000300000030300003000300000000')
            font=(OUT.parent/'fit/asset-text-data.bin').read_bytes()[:328]
            glyph_cells=(OUT.parent/'fit/asset-text-data.bin').read_bytes()[840:904]
            digit=glyph_cells[56+xpos+1]
            expected=bytes((main['COLOR_BLUE'] if font[digit*8+r]&(128>>(j*2)) else 0)*16+(main['COLOR_BLUE'] if font[digit*8+r]&(64>>(j*2)) else 0) for r in range(8) for j in range(4))
            cell=lambda x: b''.join(pixels[(7*8+r)*160+x*4:(7*8+r)*160+x*4+4] for r in range(8))
            x_exact=cell(xpos)==native
            digit_exact=cell(xpos+1)==expected
            natural_demo=dict(exact=x_exact and digit_exact,multiplier=multiplier,route_index=route,frames=demo_frames,front_owner=owner,x_cell=xpos,x_exact=x_exact,digit_glyph=digit,digit_exact=digit_exact)
            break
        if natural_demo is None:
            natural_demo=dict(exact=False,multiplier=None,route_index=b.read_bytes(client,0xDA,1)[0],frames=demo_frames,timeout_meaning='natural demo pickup not observed within 40s')
        checks.append(dict(label='natural demo multiplier pickup',**natural_demo))
        (OUT/'bug053-natural-demo-check.json').write_text(json.dumps(natural_demo,indent=2)+'\n')
        assert natural_demo['exact'],natural_demo
"""
if source.count(needle) != 1:
    raise SystemExit('expected one demo credit handoff injection point')
source = source.replace(needle, probe + '\n' + needle)
exec(compile(source, str(source_path), 'exec'), {'__name__':'__main__','__file__':str(source_path)})
