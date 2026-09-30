#!/usr/bin/env python3
"""Reuse the menu oracle for field-publication timing and pending replay.

Each phase has a 40-second marker deadline. Missing markers fail the probe.
Required response maxima: FRONT <=6 VBlanks, coherent owners <=12.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
path = ROOT / 'scripts/verify_feat005_menus.py'
source = path.read_text()
source = source.replace('import argparse\n', 'import argparse\nimport functools\n', 1)
source = source.replace('ROOT = r.ROOT',
    'shared.p.tileset_ranges = functools.lru_cache(maxsize=None)(shared.p.tileset_ranges)\nROOT = r.ROOT', 1)
source = source.replace(
    'and read(0xD4)==0 and read(0x91)==0)',
    'and read(0xD4)==0 and read(0x91)==0 and (screen not in (3,6,7) or read(0xE1)==0))',
    1)
begin = "        key(0x30,6);options_pixels(0)"
end = "        ids.extend(monitor.setup(client,[0x0700]))"
start = source.index(begin)
finish = source.index(end, start)
sequence = '''
        samples=[]
        def visible_tile(dst):
            owner=read(0x8F)
            saved=[read(0xFFA1+i) for i in range(4)]
            try:
                for i in range(4):write(0xFFA1+i,(0x30 if owner==0 else 0x2C)+i)
                return r.read_tile(client,dst)
            finally:
                for i,v in enumerate(saved):write(0xFFA1+i,v)

        def sample(name,scan,screen,address,value,dst,code,colour=10):
            expected=bytearray(30720);paint(expected,dst,code,colour)
            tile=r.frame_tile(expected,dst)
            begin=r.read_word(client,2);recognized=None;visible=None;loops=0
            first_back=read(0x90)
            client.call('inject_key',{'key':scan,'action':'press'})
            deadline=time.monotonic()+40
            while True:
                assert time.monotonic()<deadline,('phase timeout',name)
                tick();loops+=1
                now=r.read_word(client,2)
                if read(address)==value and recognized is None:recognized=(now-begin)&65535
                if loops==2:client.call('inject_key',{'key':scan,'action':'release'})
                if visible is None and visible_tile(dst)==tile:visible=(r.read_word(client,2)-begin)&65535
                assert read(0xA5)==5 and read(0xD4)==0,('full reload on field edit',name)
                if loops>=3 and read(0x91)==0 and read(0xE1)==0:
                    assert recognized is not None and visible is not None,(name,recognized,visible)
                    result={'phase':name,'worklist':'menu fields / both-owner replay',
                            'first_back_owner':first_back,'recognized_vblanks':recognized,
                            'first_visible_vblanks':visible,
                            'both_owners_ready_vblanks':(r.read_word(client,2)-begin)&65535}
                    samples.append(result);check('latency '+name,result)
                    assert visible<=6 and result['both_owners_ready_vblanks']<=12,result
                    return

        # Natural menu/logo sequencing must reach both initial BACK choices.
        for back in (0,1):
            wait('logo sequence exposes BACK '+str(back),
                 lambda:read(0x90)==back and read(0x91)==0 and read(0xE1)==0)
            for repeat in range(3):
                sample('high-score Down '+str(back)+'/'+str(repeat),0x2C,3,0xE0,1,0x8450,43)
                high_pixels(1)
                sample('high-score Up '+str(back)+'/'+str(repeat),0x2B,3,0xE0,0,0x842C,43)
                high_pixels(0)
        assert {s['first_back_owner'] for s in samples}=={0,1},'missing owner coverage'
        check('natural menu edits interleave with logo and both initial BACK owners')

        # Reverse an edit before its opposite-owner replay: last logical state wins.
        client.call('inject_key',{'key':0x2C,'action':'press'});tick()
        assert read(0xE0)==1 and read(0xE1)!=0
        client.call('inject_key',{'key':0x2C,'action':'release'})
        client.call('inject_key',{'key':0x2B,'action':'press'});tick()
        assert read(0xE0)==0
        client.call('inject_key',{'key':0x2B,'action':'release'});ready(3)
        high_pixels(0);check('rapid opposite selection coalesces during pending replay')

        key(0x30,6);options_pixels(0)
        sample('options lives increment',0x2E,6,0xEA,4,0x4870,4);options_pixels(0)
        sample('options lives decrement',0x2D,6,0xEA,3,0x4870,3);options_pixels(0)
        # Isolate the opposite starting owner through a valid no-change publish.
        # Both owners already match the pixel oracle; no owner IDs are forced.
        initial=read(0x90);write(0xE1,1<<initial);ready(6)
        assert read(0x90)==1-initial
        options_pixels(0)
        sample('options opposite-owner increment',0x2E,6,0xEA,4,0x4870,4);options_pixels(0)
        sample('options opposite-owner decrement',0x2D,6,0xEA,3,0x4870,3);options_pixels(0)
        assert {s['first_back_owner'] for s in samples if s['phase'].startswith('options')}=={0,1}
        pairs=[]
        root=ET.parse(ROOT/'tiled/coco-options-screen.tmx').getroot()
        cells=[shared.p.raw_char_code(root,ROOT/'tiled/coco-options-screen.tmx',int(v))
               for v in root.find("layer[@name='Selected Option']/data").text.strip().split(',')]
        for row in range(24):
            pair=[(i%40,i//40,c) for i,c in enumerate(cells) if c in (43,44) and i//40==row]
            if pair:pairs.extend([pair[i:i+2] for i in range(0,len(pair),2)])
        col,row,_=pairs[1][0];level_dst=0x2000+row*1280+col*4
        back_row,back_lo,_=manifest['menus']['option_rows'][2]
        back_dst=0x2000+back_row*1280+back_lo*4
        _,flat,_=shared.p.flatten_map(ROOT/'tiled/coco-options-screen.tmx')
        back_code=shared.p.raw_char_code(root,ROOT/'tiled/coco-options-screen.tmx',flat[back_row*40+back_lo])
        back_code=back_code if back_code is not None and back_code<=35 else 36
        sample('options select level',0x2C,6,0xE0,1,level_dst,43);options_pixels(1)
        sample('options level increment',0x2E,6,0xEB,2,level_dst+8,2);options_pixels(1)
        sample('options level decrement',0x2D,6,0xEB,1,level_dst+8,1);options_pixels(1)
        sample('options select BACK',0x2C,6,0xE0,2,back_dst,back_code);options_pixels(2)
        sample('options select level again',0x2B,6,0xE0,1,level_dst,43);options_pixels(1)
        sample('options select lives again',0x2B,6,0xE0,0,0x4868,43);options_pixels(0)

        # Existing scanner's hold/opposed/endpoints must remain unchanged.
        client.call('inject_key',{'key':0x2E,'action':'press'})
        for _ in range(20):tick()
        assert read(0xEA)==4
        client.call('inject_key',{'key':0x2E,'action':'release'});tick();ready(6)
        options_pixels(0)
        for scan in (0x2D,0x2E):client.call('inject_key',{'key':scan,'action':'press'})
        for _ in range(8):tick()
        assert read(0xEA)==4
        for scan in (0x2D,0x2E):client.call('inject_key',{'key':scan,'action':'release'})
        tick();check('held and opposed input retains one-action edge contract')
        for value,scan,expected_value in ((1,0x2D,1),(12,0x2E,12)):
            write(0xEA,value);key(scan,6);assert read(0xEA)==expected_value
        key(0x2C,6)
        for value,scan,expected_value in ((1,0x2D,1),(99,0x2E,99)):
            write(0xEB,value);key(scan,6);assert read(0xEB)==expected_value
        check('legal endpoints clamp')
        # Return settings to a naturally published state before leaving.
        write(0xEA,3);write(0xEB,1);write(0xE1,3);ready(6);options_pixels(1)
        key(0x2C,6);options_pixels(2);key(0x30,3);high_pixels(0)
        key(0x2C,3);key(0x30,7)
        row,col=manifest['menus']['credit_back']
        for owner in (0,1):
            frame=r.read_owner(client,owner)
            for i,code in enumerate((11,10,12,20)):
                expected=bytearray(30720);dst=0x2000+row*1280+(col+i)*4
                paint(expected,dst,code,10)
                assert r.frame_tile(frame,dst)==r.frame_tile(expected,dst)
        key(0x30,3);key(0x30,6);key(0x32,3)
        assert read(0xE1)==0
        check('green credits BACK and Enter/Escape transitions retire menu replay')
        report['response_targets_vblanks']={'first_visible':6,'both_owners_ready':12}
        report['measured_maxima_vblanks']={k:max(s[k] for s in samples)
            for k in ('recognized_vblanks','first_visible_vblanks','both_owners_ready_vblanks')}
        report['status']='pass';return
'''
source = source[:start] + sequence + source[finish:]
exec(compile(source, str(path), 'exec'), {'__name__': '__main__', '__file__': str(path)})
