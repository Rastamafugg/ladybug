"""Verify production shared-text masks, references and complete static pixels."""
import argparse, hashlib, json, re
from pathlib import Path
import build_presentation as p
import build_screen as s

def values(text,label,end):
    section=text.split('\n'+label+'\n',1)[1].split('\n'+end+'\n',1)[0]
    return bytes(int(v.strip()[1:],16) if v.strip().startswith('$') else int(v) for line in section.splitlines() if 'fcb' in line for v in line.split('fcb',1)[1].split(';')[0].strip().split(','))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--build-dir',type=Path,required=True);args=parser.parse_args()
    root=Path(__file__).resolve().parents[1];folder=args.build_dir
    manifest_path=folder/'ladybug-presentation.json'
    if not manifest_path.exists():manifest_path=folder/'manifest.json'
    manifest=json.loads(manifest_path.read_text());shared=manifest['shared_text']
    cold_path=folder/'ladybug-presentation-cold.bin'
    if not cold_path.exists():cold_path=folder/'cold.bin'
    cold=cold_path.read_bytes();data=(folder/'ladybug_shared_text.inc').read_text()
    font=values(data,'font','colour_lut');descriptors=values(data,'dynamic_descriptors','no_end')
    masks=[font[i:i+8] for i in range(0,len(font),8)]
    assert len(masks)==shared['font_count'] and len(set(masks))==len(masks)
    assert shared['graphics']<=224 and len(cold)<=16384 and len(descriptors)==512
    # Approved colours are checked independently of presentation_pen_map.
    approved=[]
    for r in shared['coverage']:
        name,x,y=r['screen'],r['x'],r['y'];colour=None
        if name=='attract' and y==15:colour=9
        elif name=='attract' and y==18:colour=2 if r['code']==1 else 6
        elif name=='instructions' and (y==5 and 15<=x<=25 or y==17 and 17<=x<=25 or y==20 and 16<=x<=25):colour=6
        elif name=='level-start' and 8<=x<32:colour={4:3,7:5,9:2,20:1}.get(y)
        if colour is not None:
            overridden=any(run['screen']==name and run['y']==y and run['x']<=x<run['x']+run['width'] for run in shared['colour_configuration']['runs'])
            if not overridden:assert r['colour']==colour,('approved text colour',r,colour)
            approved.append((name,x,y))
    assert len(approved)>50,'approved-colour coverage absent'
    chars=s.load_chars(root/'assets/arcade/chars.json');cases=[]
    for name,start in zip(p.MAP_NAMES,manifest['map_stream_offsets']):
        tiles=[];ids={};mapping,_=p.compile_map(root/'tiled'/p.MAP_FILES[name],chars,tiles,ids,False,True)
        expected=bytearray(p.title_framebuffer(mapping,tiles));actual=bytearray(30720)
        for run in shared['colour_configuration']['runs']:
            if run['screen']!=name:continue
            for x in range(run['x'],run['x']+run['width']):
                for y in range(8):
                    at=run['y']*1280+x*4+y*160
                    record=next(r for r in shared['coverage'] if r['screen']==name and r['x']==x and r['y']==run['y'])
                    bits=bytes.fromhex(record['mask'])[y];c=run['colour']
                    expected[at:at+4]=bytes((c if bits&(128>>(j*2)) else 0)*16+(c if bits&(64>>(j*2)) else 0) for j in range(4))
        ptr=start;cell=0
        while cell<960:
            count,ident=cold[ptr:ptr+2];ptr+=2
            if ident>=174:
                colour=cold[ptr];ptr+=1;glyph=ident-174
                assert glyph<len(masks) and colour<16
                tile=bytes((colour if font[glyph*8+r]&(128>>(j*2)) else 0)*16+(colour if font[glyph*8+r]&(64>>(j*2)) else 0) for r in range(8) for j in range(4))
            else:
                assert ident<shared['static_graphics'];tile=cold[ident*32:(ident+1)*32]
            assert count and cell+count<=960
            for _ in range(count):
                at=(cell//40)*1280+(cell%40)*4
                for row in range(8):actual[at+row*160:at+row*160+4]=tile[row*4:row*4+4]
                cell+=1
        differences=[i for i,(a,v) in enumerate(zip(actual,expected)) if a!=v]
        assert hashlib.sha256(actual).hexdigest()==manifest['shared_static_frame_sha256'][p.MAP_NAMES.index(name)]
        cases.append(dict(screen=name,pixel_exact=not differences,differences=len(differences),first=differences[:12]))
    report=dict(status='pass' if all(c['pixel_exact'] for c in cases) else 'FAIL',cases=cases,font_bytes=len(font),graphics=shared['graphics'],cold_bytes=len(cold),sha256=hashlib.sha256(cold).hexdigest())
    (folder/'shared-text-verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    assert report['status']=='pass',report

if __name__=='__main__':main()
