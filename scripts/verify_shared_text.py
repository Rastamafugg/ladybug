"""Verify production shared-text masks, references and complete static pixels."""
import argparse, hashlib, json, re
import xml.etree.ElementTree as ET
from pathlib import Path
import build_presentation as p
import build_screen as s

def values(text,label,end):
    section=text.split('\n'+label+'\n',1)[1].split('\n'+end+'\n',1)[0]
    return bytes(int(v.strip()[1:],16) if v.strip().startswith('$') else int(v) for line in section.splitlines() if 'fcb' in line for v in line.split('fcb',1)[1].split(';')[0].strip().split(','))

def verify_score_field(placement, generated, cells, expected_colour):
    """Authored digit count and runtime storage capacity are separate contracts."""
    x, y = placement['score_cell']
    width = placement['score_cell_width']
    maximum = placement['score_max_digits']
    draw_x = x + width - maximum
    assert generated['score_cell'] == placement['score_cell']
    assert generated['score_cell_width'] == width
    assert generated['score_max_digits'] == maximum
    assert generated['score_draw_cells'] == maximum  # compatible capacity alias
    assert generated['score_destination'] == 0x2000 + y * 1280 + draw_x * 4
    columns = [column for column in range(x, x + width)
               if ('high-score', column, y) in cells]
    assert columns and len(columns) <= maximum, ('authored score length/capacity', columns, maximum)
    assert columns == list(range(x + width - len(columns), x + width)), ('score alignment/gap', columns)
    authored = [[column, y] for column in columns]
    assert placement['authored_score_cells'] == authored
    assert generated['authored_score_cells'] == authored
    for column in columns:
        record = cells['high-score', column, y]
        assert 0 <= record['code'] <= 9, ('non-digit score text', column, y)
        assert record['colour'] == expected_colour, ('score colour', column, y, record['colour'], expected_colour)


def read_logo_layout(root, screen):
    path = root / 'tiled' / p.MAP_FILES[screen]
    tiled = ET.parse(path).getroot()
    width, height = int(tiled.attrib['width']), int(tiled.attrib['height'])
    assert (width, height) == (40, 24), ('logo map dimensions', screen, width, height)
    layers = []
    for name in ('Logo Frame 1', 'Logo Frame 2'):
        layer = next((item for item in tiled.findall('layer') if item.get('name') == name), None)
        assert layer is not None, ('missing authored logo layer', screen, name)
        values = [int(value.strip()) for value in (layer.findtext('data') or '').split(',')]
        assert len(values) == width * height, ('logo layer cell count', screen, name)
        layers.append({
            (index % width, index // width): gid
            for index, gid in enumerate(values) if gid & s.GID_MASK
        })
    cells = [cell for layer in layers for cell in layer]
    assert cells, ('empty logo layers', screen)
    root_cell = (min(x for x, _ in cells) // 2 * 2,
                 min(y for _, y in cells) // 2 * 2)
    rx, ry = root_cell
    relative_layers = tuple(
        tuple(sorted((x - rx, y - ry, gid) for (x, y), gid in layer.items()))
        for layer in layers
    )
    return root_cell, relative_layers

def read_logo_base_cells(root, screen):
    path = root / 'tiled' / p.MAP_FILES[screen]
    tiled = ET.parse(path).getroot()
    width, height = int(tiled.attrib['width']), int(tiled.attrib['height'])
    name = 'Logo Base' if screen == 'high-score' else 'Attract Title and Prompts'
    layer = next(
        (item for item in tiled.findall('layer') if item.get('name') == name), None
    )
    assert layer is not None, ('missing static logo layer', screen, name)
    values = [int(value.strip()) for value in (layer.findtext('data') or '').split(',')]
    assert len(values) == width * height, ('static logo layer cell count', screen)
    return {(index % width, index // width): gid & s.GID_MASK
            for index, gid in enumerate(values) if gid & s.GID_MASK}

def packed_colours(tile):
    return {colour for value in tile for colour in (value >> 4, value & 0x0F)}

def verify_highscore_logo(root, manifest, cold, chars):
    attract_root, attract_layout = read_logo_layout(root, 'attract')
    highscore_root, highscore_layout = read_logo_layout(root, 'high-score')
    base_cells = {screen: read_logo_base_cells(root, screen)
                  for screen in ('attract', 'high-score')}
    assert attract_layout == highscore_layout, 'Attract/High Score authored logo layouts differ'
    relative_cells = sorted(
        {(x, y) for frame in highscore_layout for x, y, _gid in frame},
        key=lambda cell: (cell[1], cell[0]),
    )
    assert len(relative_cells) == 12, ('expected twelve authored logo cells', relative_cells)
    highscore_cells = [(highscore_root[0] + x, highscore_root[1] + y)
                       for x, y in relative_cells]
    highscore_root_destination = p.framebuffer_destination(highscore_root)
    attract_root_destination = p.framebuffer_destination(attract_root)
    relative_offsets = [p.framebuffer_destination(cell) - highscore_root_destination
                        for cell in highscore_cells]
    attract_destinations = [p.framebuffer_destination((attract_root[0] + x,
                                                        attract_root[1] + y))
                            for x, y in relative_cells]
    assert [attract_root_destination + offset for offset in relative_offsets] == attract_destinations
    colour_config = p.load_text_colours(root / 'assets/arcade/text-colours.json')
    tiles, tile_ids = [], {}
    highscore_map = root / 'tiled' / p.MAP_FILES['high-score']
    mapping, _ = p.compile_map(highscore_map, chars, tiles, tile_ids,
                               False, True, colour_config)
    frames = p.compile_logo_frames(p.title_framebuffer(mapping, tiles),
                                   'high-score', colour_config)[1]
    # Both frames begin with the static map. A Frame 2 tile only animates if
    # its compiled pixels differ from the corresponding Frame 1 pixels.
    attract_tiles, attract_tile_ids = [], {}
    attract_mapping, _ = p.compile_map(
        root / 'tiled' / p.MAP_FILES['attract'], chars,
        attract_tiles, attract_tile_ids, False, True, colour_config)
    attract_frames = p.compile_logo_frames(
        p.title_framebuffer(attract_mapping, attract_tiles),
        'attract', colour_config)[1]
    frame2_relative = {(x, y) for x, y, _gid in highscore_layout[1]}
    for purpose in ('y-descender', 'g-descender'):
        groups = [group for group in colour_config['logo_groups']
                  if group['screen'] == 'high-score' and group['purpose'] == purpose]
        assert len(groups) == 1, ('missing or duplicate logo group', purpose)
        targets = {(x - highscore_root[0], y - highscore_root[1])
                   for x, y in groups[0]['cells']
                   if (x - highscore_root[0], y - highscore_root[1]) in frame2_relative}
        assert targets, ('no authored Frame 2 descender cells', purpose)
        for screen, screen_root, screen_frames in (
                ('high-score', highscore_root, frames),
                ('attract', attract_root, attract_frames)):
            for dx, dy in targets:
                x, y = screen_root[0] + dx, screen_root[1] + dy
                offset = y * 1280 + x * 4
                pixels = [b''.join(frame[offset + row * 160:offset + row * 160 + 4]
                                   for row in range(8)) for frame in screen_frames]
                colour = int(groups[0]['colour'])
                assert base_cells[screen].get((x, y), 0), (
                    'logo base layer is empty under an animated descender',
                    screen, purpose, (x, y))
                assert colour in packed_colours(pixels[0]), (
                    'logo base phase lacks its authored colour',
                    screen, purpose, (x, y))
                assert colour in packed_colours(pixels[1]), (
                    'logo animation phase lacks its authored base colour',
                    screen, purpose, (x, y))
                assert p.WHITE in packed_colours(pixels[1]), (
                    'logo animation phase lost its white accent',
                    screen, purpose, (x, y))
                assert pixels[0] != pixels[1], (
                    'logo descender frames have identical pixels', screen, purpose, (x, y))
    expected_data = bytearray()
    for x, y in highscore_cells:
        offset = y * 1280 + x * 4
        for frame in frames:
            expected_data.extend(b''.join(
                frame[offset + row * 160:offset + row * 160 + 4]
                for row in range(8)
            ))
    expected_data = bytes(expected_data)
    metadata = manifest['highscore_logo']
    base = metadata.get('base_payload_bytes')
    assert type(base) is int and 0 <= base <= len(cold), ('invalid logo payload base', base)
    data_offset = ((base + p.TILE_BYTES - 1) // p.TILE_BYTES) * p.TILE_BYTES
    if data_offset % p.PAGE_BYTES + len(expected_data) > p.PAGE_BYTES:
        data_offset = (data_offset // p.PAGE_BYTES + 1) * p.PAGE_BYTES
    roots = {
        'attract': {'cell': list(attract_root), 'destination': attract_root_destination},
        'high-score': {'cell': list(highscore_root), 'destination': highscore_root_destination},
    }
    expected_records = [[offset] for offset in relative_offsets]
    assert metadata.get('source_map') == 'high-score'
    assert metadata.get('roots') == roots
    assert metadata.get('relative_offsets') == relative_offsets
    assert metadata.get('records') == expected_records
    assert metadata.get('authored_cells') == [list(cell) for cell in highscore_cells]
    assert metadata.get('cells') == 12
    assert metadata.get('data_offset') == data_offset
    assert metadata.get('data_bytes') == len(expected_data) == 12 * 2 * p.TILE_BYTES
    assert metadata.get('data_stride') == 2 * p.TILE_BYTES
    assert metadata.get('frame_bytes') == p.TILE_BYTES
    assert data_offset % p.TILE_BYTES == 0
    assert data_offset % p.PAGE_BYTES + len(expected_data) <= p.PAGE_BYTES
    assert data_offset + len(expected_data) == len(cold)
    assert cold[data_offset:] == expected_data
    assert manifest['cold_payload']['bytes'] == len(cold)
    assert manifest['cold_payload']['sha256'] == hashlib.sha256(cold).hexdigest()
    assert metadata.get('appended_bytes') == len(cold) - base
    return {'cells': 12, 'data_bytes': len(expected_data),
            'data_offset': data_offset, 'page_safe': True}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--build-dir',type=Path,required=True);args=parser.parse_args()
    root=Path(__file__).resolve().parents[1];folder=args.build_dir
    gameplay_map=root/'tiled/coco-screen.tmx'
    gameplay_root=ET.parse(gameplay_map).getroot();gameplay_cells=[0]*960
    for layer in gameplay_root.findall('layer'):
        if layer.get('visible','1')=='0':continue
        for i,gid in enumerate(s.parse_csv(layer.find('data'),layer.get('name',''))):
            if gid&s.GID_MASK:gameplay_cells[i]=gid
    gameplay_equals=[(i%40,i//40) for i,gid in enumerate(gameplay_cells)
                     if p.raw_char_code(gameplay_root,gameplay_map,gid&s.GID_MASK)==42]
    assert len(gameplay_equals)==1,('expected one gameplay bonus equals cell',gameplay_equals)
    bonus_cell=gameplay_equals[0]
    manifest_path=folder/'ladybug-presentation.json'
    if not manifest_path.exists():manifest_path=folder/'manifest.json'
    manifest=json.loads(manifest_path.read_text());shared=manifest['shared_text']
    cold_path=folder/'ladybug-presentation-cold.bin'
    if not cold_path.exists():cold_path=folder/'cold.bin'
    cold=cold_path.read_bytes();data=(folder/'ladybug_shared_text.inc').read_text()
    highscore_logo=verify_highscore_logo(root,manifest,cold,p.load_chars(root/'assets/arcade/chars.json'))
    font=values(data,'font','colour_lut');descriptors=values(data,'dynamic_descriptors','no_end')
    masks=[font[i:i+8] for i in range(0,len(font),8)]
    assert len(masks)==shared['font_count'] and len(set(masks))==len(masks)
    assert shared['graphics']<=224 and len(cold)<=16384 and len(descriptors)==2*shared['descriptor_count']
    # Approved colours are checked independently of presentation_pen_map.
    approved=[]
    for r in shared['coverage']:
        name,x,y=r['screen'],r['x'],r['y'];colour=None
        if name=='gameplay' and (x,y)==bonus_cell:
            assert (r['code'],r['mask'])==(42,'00007f00007f0000')
            assert masks[r['glyph']]==bytes.fromhex(r['mask'])
            colour=shared['colour_configuration']['fields']['bonus']
        elif name=='attract' and y==15:colour=9
        elif name=='attract' and y==18:colour=2 if r['code']==1 else 6
        elif name=='instructions' and (y==5 and 15<=x<=25 or y==17 and 17<=x<=25 or y==20 and 16<=x<=25):colour=6
        elif name=='level-start' and 8<=x<32:colour={4:3,7:5,9:2,20:1}.get(y)
        if colour is not None:
            overridden=any(run['screen']==name and run['y']==y and run['x']<=x<run['x']+run['width'] for run in shared['colour_configuration']['runs'])
            if not overridden:assert r['colour']==colour,('approved text colour',r,colour)
            approved.append((name,x,y))
    assert len(approved)>50,'approved-colour coverage absent'
    equals=[r for r in shared['coverage'] if r['screen']=='gameplay' and (r['x'],r['y'])==bonus_cell]
    assert len(equals)==1 and equals[0]['colour']==shared['colour_configuration']['fields']['bonus']
    chars=s.load_chars(root/'assets/arcade/chars.json');cases=[]
    colour_config=p.load_text_colours(root/'assets/arcade/text-colours.json')
    high_score_layout=p.parse_high_score_layout(
        root/'tiled/coco-high-score-screen.tmx',colour_config)
    high_score_cells={(r['screen'],r['x'],r['y']):r for r in shared['coverage']}
    generated_layout=manifest['high_score_table']['placements']
    assert len(generated_layout)==len(high_score_layout),(
        'high-score generated layout count',len(generated_layout),len(high_score_layout))
    for placement,generated in zip(high_score_layout,generated_layout):
        expected_colour=1 if placement['record_index']==0 else 7
        name_x,name_y=placement['name_cell']
        for column in range(name_x,name_x+placement['name_cell_width']):
            record=high_score_cells.get(('high-score',column,name_y))
            assert record is not None,(
                'high-score authored text coverage',placement,'name_cell',column,name_y)
            assert record['colour']==expected_colour,(
                'high-score rank colour',placement,'name_cell',column,name_y,
                record['colour'],expected_colour)
        verify_score_field(placement,generated,high_score_cells,expected_colour)
    for name,start in zip(p.MAP_NAMES,manifest['map_stream_offsets']):
        tiles=[];ids={};mapping,_=p.compile_map(root/'tiled'/p.MAP_FILES[name],chars,tiles,ids,False,True,colour_config)
        expected=bytearray(p.title_framebuffer(mapping,tiles))
        seed=bytearray((i*37+11)&255 for i in range(30720)) if name=='game-over' else bytearray(30720)
        actual=seed.copy()
        for run in shared['colour_configuration']['runs']:
            if run['screen']!=name:continue
            for x in range(run['x'],run['x']+run['width']):
                for y in range(8):
                    at=run['y']*1280+x*4+y*160
                    record=next(r for r in shared['coverage'] if r['screen']==name and r['x']==x and r['y']==run['y'])
                    bits=bytes.fromhex(record['mask'])[y];c=run['colour']
                    expected[at:at+4]=bytes((c if bits&(128>>(j*2)) else 0)*16+(c if bits&(64>>(j*2)) else 0) for j in range(4))
        if name=='high-score':
            # Recolour the native authored pixels, independently of the shared
            # font mask records used by the typed-text renderer.
            for (x,y),colour in p.high_score_field_colour_cells(root/'tiled/coco-high-score-screen.tmx',colour_config).items():
                for row in range(8):
                    at=y*1280+x*4+row*160
                    expected[at:at+4]=bytes((colour if b>>4 else 0)*16+(colour if b&15 else 0) for b in expected[at:at+4])
        ptr=start;cell=0
        while cell<960:
            count,ident=cold[ptr:ptr+2];ptr+=2
            if ident==255:
                colour=cold[ptr];ptr+=1
                assert name=='game-over' and colour==0
                tile=None
            elif ident>=174:
                colour=cold[ptr];ptr+=1;glyph=ident-174
                assert glyph<len(masks) and colour<16
                tile=bytes((colour if font[glyph*8+r]&(128>>(j*2)) else 0)*16+(colour if font[glyph*8+r]&(64>>(j*2)) else 0) for r in range(8) for j in range(4))
            else:
                assert ident<shared['static_graphics'];tile=cold[ident*32:(ident+1)*32]
            assert count and cell+count<=960
            for _ in range(count):
                at=(cell//40)*1280+(cell%40)*4
                preserved=name=='game-over' and (cell%40<=8 or cell%40>=31 or cell//40 in (0,23))
                assert (tile is None)==preserved,('game-over no-write mask',cell,ident)
                for row in range(8):
                    if preserved:expected[at+row*160:at+row*160+4]=seed[at+row*160:at+row*160+4]
                    else:actual[at+row*160:at+row*160+4]=tile[row*4:row*4+4]
                cell+=1
        differences=[i for i,(a,v) in enumerate(zip(actual,expected)) if a!=v]
        if name!='game-over':
            assert hashlib.sha256(actual).hexdigest()==manifest['shared_static_frame_sha256'][p.MAP_NAMES.index(name)]
        cases.append(dict(screen=name,pixel_exact=not differences,differences=len(differences),first=differences[:12]))
    report=dict(status='pass' if all(c['pixel_exact'] for c in cases) else 'FAIL',cases=cases,font_bytes=len(font),graphics=shared['graphics'],cold_bytes=len(cold),sha256=hashlib.sha256(cold).hexdigest(),highscore_logo=highscore_logo)
    (folder/'shared-text-verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    assert report['status']=='pass',report

if __name__=='__main__':main()
