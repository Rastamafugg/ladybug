"""Verify the authored gameplay equals cell and its generated descriptor."""
import argparse, json, re, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
import build_screen as s


def values(text, label, end):
    section=text.split('\n'+label+'\n', 1)[1].split('\n'+end+'\n', 1)[0]
    return bytes(int(v.strip()[1:], 16) if v.strip().startswith('$') else int(v)
                 for line in section.splitlines() if 'fcb' in line
                 for v in line.split('fcb', 1)[1].split(';')[0].strip().split(','))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--build-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args=parser.parse_args()
    root=ROOT
    manifest=json.loads((args.build_dir/'ladybug-presentation.json').read_text())
    shared=manifest['shared_text']
    shared_text=(args.build_dir/'ladybug_shared_text.inc').read_text()
    screen_text=(args.build_dir/'ladybug_screen.inc').read_text()
    font=values(shared_text, 'font', 'colour_lut')
    descriptors=values(shared_text, 'gameplay_descriptors', 'dynamic_descriptors')
    screen_map=values(screen_text, 'screen_map', 'screen_tiles')
    static_count=int(re.search(r'^SCREEN_TILE_COUNT\s+equ\s+(\d+)$', screen_text, re.M).group(1))
    chars=s.load_chars(root/'assets/arcade/chars.json')
    rows=s.rotate_ccw(chars[42])
    authored_mask=bytes(sum(bool(v) << (7-x) for x,v in enumerate(row)) for row in rows)
    assert authored_mask.hex()=='00007f00007f0000'
    glyph=next(i for i in range(len(font)//8) if font[i*8:(i+1)*8]==authored_mask)
    assert glyph==35
    target=[r for r in shared['coverage'] if r['screen']=='gameplay' and (r['x'],r['y'])==(34,13)]
    assert len(target)==1
    target=target[0];bonus=shared['colour_configuration']['fields']['bonus']
    assert (target['code'],target['glyph'],target['mask'],target['colour'])==(42,35,authored_mask.hex(),bonus)
    cell=13*40+34;ident=screen_map[cell]
    assert ident>=static_count
    descriptor=descriptors[(ident-static_count)*2:(ident-static_count+1)*2]
    assert tuple(descriptor)==(glyph, bonus)
    row13=[r for r in shared['coverage'] if r['screen']=='gameplay' and r['y']==13]
    assert len(row13)==5
    for record in row13:
        if record['x']==34:
            continue
        assert (record['x'],record['code'],record['glyph'],record['mask'],record['colour']) in {
            (35,0,0,'003e634141633e00',0),
            (36,0,0,'003e634141633e00',0),
            (37,0,0,'003e634141633e00',0),
            (38,0,0,'003e634141633e00',0),
        }
        assert screen_map[13*40+record['x']]==82
    report=dict(status='pass', marker='bug042_equals_static_matches_value', runtime_marker='bug042_equals_matches_value',
                runtime_status='not_run', controlled='not-natural', cell=[34,13], code=42,
                glyph=glyph, mask=authored_mask.hex(), colour=bonus, descriptor=list(descriptor),
                map_identifier=ident, static_tiles=static_count, row13_other_cells_unchanged=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output/'summary.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report))


if __name__=='__main__':
    main()
