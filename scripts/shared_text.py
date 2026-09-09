"""Shared 1-bit font and typed text records compiled from authored TMX/characters."""
import hashlib
import json
import re
from pathlib import Path
import xml.etree.ElementTree as ET

import build_screen as s


def emit(label, data):
    return '\n'+label+'\n'+''.join('        fcb '+','.join(str(v) for v in data[i:i+32])+'\n' for i in range(0,len(data),32))


class SharedText:
    def __init__(self, args, p):
        self.args, self.p = args, p
        config_path=getattr(args,'text_colours',None) or Path(__file__).resolve().parents[1]/'assets/arcade/text-colours.json'
        self.colours=json.loads(config_path.read_text())
        required={'score','high_score','part','bonus','special','extra','multiplier','instruction_points','instruction_special','instruction_extra','instruction_multiplier','stage_part','stage_bonus','stage_name','stage_good_luck','ranking','name','game_over_score'}
        if set(self.colours['fields'])!=required:raise ValueError('text colour fields must match the documented contract')
        if any(type(v) is not int or not 1<=v<=15 for v in self.colours['fields'].values()):raise ValueError('dynamic text colours must be palette indices 1..15')
        chars=s.load_chars(args.chars)
        self.font=[];self.records=[]
        def mask(rows):return bytes(sum(bool(v)<<(7-x) for x,v in enumerate(row)) for row in rows)
        for code in range(36):
            value=mask(s.rotate_ccw(chars[code]))
            if value not in self.font:self.font.append(value)
        text_codes=set(range(41))|set(range(42,46))
        paths=[(name,args.tiled_dir/p.MAP_FILES[name]) for name in p.MAP_NAMES]+[('gameplay',args.gameplay_map)]
        for name,path in paths:
            if name=='gameplay':
                root=ET.parse(path).getroot();flat=[0]*960;sources=['']*960
                for layer in root.findall('layer'):
                    if layer.get('visible','1')=='0':continue
                    for i,gid in enumerate(s.parse_csv(layer.find('data'),layer.get('name',''))):
                        if gid&p.GID_MASK:flat[i]=gid;sources[i]=layer.get('name','')
            else:root,flat,sources=p.flatten_map(path)
            for i,gid in enumerate(flat):
                code=p.raw_char_code(root,path,gid&p.GID_MASK)
                if code not in text_codes:continue
                x,y=i%40,i//40
                rows=s.transform(s.rotate_ccw(chars[code]),bool(gid&p.FLIP_H),bool(gid&p.FLIP_V))
                value=mask(rows)
                if value not in self.font:self.font.append(value)
                if name=='gameplay':
                    if x<8 and y<9:colour=(1,2,3)[y//3] if y%3!=1 or x==0 else 7
                    elif x>=32:colour={1:8,2:8,4:1,5:1,7:6,8:6,10:3,11:3,12:5}.get(y,0)
                    else:raise ValueError(('unexpected gameplay text',x,y))
                else:
                    pens=p.presentation_pen_map(name,x,y,sources[i],code,False)
                    colours={pens[v] for row in rows for v in row if v}
                    if len(colours)!=1:raise ValueError(('text is not monochrome',name,x,y))
                    colour=colours.pop()
                self.records.append(dict(screen=name,x=x,y=y,code=code,glyph=self.font.index(value),colour=colour,mask=value.hex()))
        if bytes(8) not in self.font:self.font.append(bytes(8))
        if len(self.font)>82:raise ValueError('shared font exceeds one-byte static encoding')
        self.cells={(r['screen'],r['y']*40+r['x']):r for r in self.records}
        self.overridden=set()
        for run in self.colours['runs']:
            if not (0<=run['colour']<=15 and 0<=run['x']<40 and 0<=run['y']<24 and 1<=run['width']<=40-run['x']):raise ValueError(('invalid text run',run))
            for x in range(run['x'],run['x']+run['width']):
                key=(run['screen'],run['y']*40+x)
                if key not in self.cells:raise ValueError(('colour override is not a text cell',key))
                self.cells[key]['colour']=run['colour']
                self.overridden.add(key)
        contexts=int(any(self.colours['fields'][k]!=6 for k in ('instruction_points','ranking','name','game_over_score')))
        (args.output.parent/'ladybug_text_colours.inc').write_text(''.join(f'TEXT_{k.upper()} equ {v}\n' for k,v in self.colours['fields'].items())+f'TEXT_CONTEXT_COLOURS equ {contexts}\n')

    def separate_static(self,maps,tiles,tile_ids):
        self.visual_maps=[list(m) for m in maps];self.visual_tiles=list(tiles)
        blank=self.p.register_tile(bytes(32),tiles,tile_ids)
        return [[blank if (name,i) in self.cells else v for i,v in enumerate(mapping)] for name,mapping in zip(self.p.MAP_NAMES,maps)]

    def gameplay(self):
        a=self.args
        mapping,tiles,states,diagonals,backgrounds,*_=s.compile_screen(a.gameplay_map,a.gameplay_maze,a.gameplay_chars,a.gameplay_sprites)
        cells={i:r for (screen,i),r in self.cells.items() if screen=='gameplay'}
        protected={t for i,t in enumerate(mapping) if i not in cells}
        for groups in (states,diagonals):
            for group in groups:
                for record in group:protected.add(record[2])
        for group in backgrounds:protected.update(group)
        removed={mapping[i] for i in cells}-protected
        kept=[i for i in range(len(tiles)) if i not in removed];descriptors=[];newmap=[]
        for i,t in enumerate(mapping):
            if i in cells:
                r=cells[i];d=(r['glyph'],r['colour'])
                if d not in descriptors:descriptors.append(d)
                newmap.append(len(kept)+descriptors.index(d))
            else:newmap.append(kept.index(t))
        if max(newmap)>255:raise ValueError('gameplay typed map exceeds byte namespace')
        path=a.output.parent/'ladybug_screen.inc';text=path.read_text()
        def replace(label,end,body):
            nonlocal text
            start=text.index('\n'+label+'\n');stop=text.index('\n'+end+'\n',start)
            text=text[:start]+body+text[stop:]
        replace('screen_map','screen_tiles',emit('screen_map',newmap))
        replace('screen_tiles','gate_state_tiles',emit('screen_tiles',b''.join(tiles[i] for i in kept)))
        replace('hud_digit_tiles','object_masks','')
        for label,end,stride in [('gate_state_tiles','gate_diagonal_tiles',3),('gate_diagonal_tiles','gate_background_index',3),('gate_background_tiles','gate_redraw_neighbors',1)]:
            start=text.index('\n'+label+'\n');stop=text.index('\n'+end+'\n',start)
            values=[int(v,16) for line in text[start:stop].splitlines() if 'fcb' in line for v in re.findall(r'\$([0-9A-Fa-f]{2})',line.split(';')[0])]
            for i in range(stride-1,len(values),stride):values[i]=kept.index(values[i])
            replace(label,end,emit(label,values))
        for key in ('MAZE_CLEAN_TILE','MAZE_DOT_TILE'):
            text=re.sub(r'('+key+r'\s+equ\s+)(\d+)',lambda m:m[1]+str(kept.index(int(m[2]))),text)
        text=re.sub(r'(SCREEN_TILE_COUNT\s+equ\s+)\d+',lambda m:m[1]+str(len(kept)),text)
        path.write_text(text)
        hud=bytearray(64)
        for i,r in cells.items():
            if r['x']<8 and r['y']<8:hud[r['y']*8+r['x']]=r['glyph']
        lut=bytes(v for c in range(16) for n in range(16) for v in (((c if n&8 else 0)<<4)|(c if n&4 else 0),((c if n&2 else 0)<<4)|(c if n&1 else 0)))
        return emit('font',b''.join(self.font))+emit('colour_lut',lut)+emit('hud_glyph_cells',hud)+emit('gameplay_descriptors',bytes(v for d in descriptors for v in d)),len(kept)

    def finish(self,manifest,tiles,cold,instruction_source):
        graphics=sorted({self.visual_tiles[t] for name,mapping in zip(self.p.MAP_NAMES,self.visual_maps) for i,t in enumerate(mapping) if (name,i) not in self.cells})
        static_count=len(graphics)
        if static_count>174:raise ValueError('static graphics exceed text threshold174')
        descriptors=[]
        for tile in tiles:
            colours={v for byte in tile for v in (byte>>4,byte&15)}-{0}
            mask=bytes(sum(bool(tile[row*4+x//2]>>(4 if x%2==0 else 0)&15)<<(7-x) for x in range(8)) for row in range(8))
            if len(colours)==1 and mask in self.font:descriptors.append((self.font.index(mask),colours.pop()))
            else:
                if tile not in graphics:graphics.append(tile)
                descriptors.append((graphics.index(tile),0))
        for ids in manifest['instruction_choreography']['value_tile_ids'].values():
            for ident in ids:descriptors[ident]=(descriptors[ident][0],self.colours['fields']['instruction_points'])
        for event in manifest['instruction_choreography']['events']:
            if not event['hud_destination']:continue
            field='instruction_extra' if event['index']<5 else 'instruction_special' if event['index']<12 else 'instruction_multiplier'
            for key in ('hud_tile_id','hud_tile_2_id'):
                ident=event[key]
                if ident and descriptors[ident][1]:
                    descriptors[ident]=(descriptors[ident][0],self.colours['fields'][field])
        for ids in manifest['instruction_choreography']['multiplier_tile_ids'].values():
            for ident in ids:
                if descriptors[ident][1]:descriptors[ident]=(descriptors[ident][0],self.colours['fields']['instruction_points'])
        if len(graphics)>224 or len(descriptors)>256:raise ValueError('shared graphic/descriptor capacity exceeded')
        streams=[]
        for name,mapping in zip(self.p.MAP_NAMES,self.visual_maps):
            items=[]
            for i,t in enumerate(mapping):
                r=self.cells.get((name,i))
                visible_text=r and (any(self.visual_tiles[t]) or (name,i) in self.overridden and r['colour'] and any(self.font[r['glyph']]))
                items.append((174+r['glyph'],r['colour']) if visible_text else (graphics.index(self.visual_tiles[t]),))
            out=bytearray();i=0
            while i<len(items):
                n=1
                while i+n<len(items) and items[i+n]==items[i] and n<255:n+=1
                out.extend((n,*items[i]));i+=n
            streams.append(out)
        inst=manifest['instruction_choreography'];names=manifest['high_score_name_entry']
        old=inst['event_table_offset'];payload=bytearray(b''.join(graphics));offsets=[]
        for stream in streams:offsets.append(len(payload));payload.extend(stream)
        # Preserve all auxiliary records in their existing second-page owner.
        if len(payload)<8192:payload.extend(bytes(8192-len(payload)))
        delta=len(payload)-old;payload.extend(cold[old:])
        for offset,count,stride,field in [(inst['colour_pointer_offset'],len(inst['colour_stream_offsets']),2,0),(inst['death_pointer_offset'],len(inst['death_stream_offsets']),2,0),(names['timer_table_offset'],names['timer_box_count'],4,2)]:
            for i in range(count):
                at=offset+delta+i*stride+field;v=int.from_bytes(payload[at:at+2],'big');payload[at:at+2]=(v+delta).to_bytes(2,'big')
        grouped=[]
        for index,offset in enumerate(inst['colour_stream_offsets']):
            ptr=offset+delta;count=payload[ptr];ptr+=1
            destination=inst['events'][index]['target_destination'] if index<15 else 0x7F34
            groups={1:[],2:[],3:[]}
            for _ in range(count):
                step=payload[ptr];ptr+=1
                if step==255:step=int.from_bytes(payload[ptr:ptr+2],'big');ptr+=2
                destination+=step;selector=payload[ptr];ptr+=1;groups[selector].append(destination)
            start=len(payload)
            for selector in (1,2,3):
                payload.append(len(groups[selector]))
                for address in groups[selector]:payload.extend(address.to_bytes(2,'big'))
            at=inst['colour_pointer_offset']+delta+index*2;payload[at:at+2]=start.to_bytes(2,'big');grouped.append(start)
        if len(payload)>16384:raise ValueError(('shared cold capacity',len(payload)))
        inc=self.args.include_output.read_text()
        symbols=['PRESENTATION_INSTRUCTION_EVENT_OFFSET','PRESENTATION_INSTRUCTION_COLOUR_POINTERS','PRESENTATION_INSTRUCTION_CUCUMBER_STREAM','PRESENTATION_INSTRUCTION_DEATH_POINTERS','PRESENTATION_NAME_ENTRY_CURSOR_OFFSET','PRESENTATION_DEMO_ROUTE_OFFSET','PRESENTATION_NAME_ENTRY_TIMER_TABLE','PRESENTATION_NAME_ENTRY_EDGE_MASK_TABLE','PRESENTATION_NAME_ENTRY_FULL_EDGE_MASK_TABLE','PRESENTATION_NAME_ENTRY_ACTION_TABLE']
        for symbol in symbols:
            inc,n=re.subn(r'('+symbol+r' equ \$)([0-9A-F]+)',lambda m:m[1]+f'{int(m[2],16)+delta:04X}',inc)
            if n!=1:raise ValueError(('missing cold symbol',symbol))
        inc+='\nSHARED_TEXT_BASE equ 174\n'
        inc=re.sub(r'(PRESENTATION_COLD_SIZE equ )\d+',lambda m:m[1]+str(len(payload)),inc)
        for i,(offset,stream) in enumerate(zip(offsets,streams)):
            inc=re.sub(rf'(PRESENTATION_MAP_STREAM_{i} equ )\$[0-9A-F]+',lambda m:m[1]+f'${offset:04X}',inc)
            inc=re.sub(rf'(PRESENTATION_MAP_STREAM_{i}_BYTES equ )\d+',lambda m:m[1]+str(len(stream)),inc)
        self.args.include_output.write_text(inc)
        timer_start=names['timer_table_offset']+delta
        self.args.timer_record_output.write_text(emit('',payload[timer_start:timer_start+names['timer_box_count']*4]))
        asset_data,gameplay_count=self.gameplay()
        asset_data+=emit('dynamic_descriptors',bytes(v for d in descriptors for v in d)+bytes([255,255])*(256-len(descriptors)))
        (self.args.output.parent/'ladybug_shared_text.inc').write_text(asset_data)
        chars=s.load_chars(self.args.chars)
        translation=[]
        for code in range(37):
            mask=bytes(8) if code==36 else bytes(sum(bool(v)<<(7-x) for x,v in enumerate(row)) for row in s.rotate_ccw(chars[code]))
            translation.append(self.font.index(mask))
        (self.args.output.parent/'ladybug_stage_glyphs.inc').write_text(emit('stage_source_glyphs',translation))
        stage=self.args.output.parent/'ladybug_stage_panel.inc'
        stage.write_text(stage.read_text().split('\nstage_panel_font\n')[0]+'\n')
        self.args.output.write_bytes(payload)
        manifest['map_stream_offsets']=offsets
        manifest['shared_text']=dict(font_count=len(self.font),font_bytes=len(self.font)*8,graphics=len(graphics),static_graphics=static_count,gameplay_graphics=gameplay_count,descriptors=len(descriptors),text_base=174,cold_delta=delta,grouped_colour_offsets=grouped,coverage=self.records)
        manifest['cold_payload']=dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest())
        manifest['map_stream_bytes']=[len(x) for x in streams]
        manifest['map_stream_total_bytes']=sum(map(len,streams))
        manifest['shared_text']['colour_configuration']=self.colours
        legacy_keys=('tile_atlas_compressed_bytes','tile_atlas_expanded_bytes','cold_only_tile_count','gameplay_tile_base','gameplay_lookup_offset','gameplay_lookup_bytes','gameplay_tile_count','static_frame_sha256')
        manifest['native_intermediate']={key:manifest.pop(key) for key in legacy_keys}
        manifest.update(tile_atlas_compressed_bytes=len(graphics)*32,tile_atlas_expanded_bytes=len(graphics)*32,cold_only_tile_count=len(graphics),gameplay_tile_count=gameplay_count)
        manifest['shared_text']['descriptor_count']=len(descriptors)
        manifest['shared_text']['encoding']='Static RLE: count, graphic ID below174; or count,174+glyph,colour. Dynamic IDs index typed descriptors; colour0 selects graphics.'
        for obj in (inst,names):
            for key,value in list(obj.items()):
                if key.endswith('_offset') and isinstance(value,int):obj[key]=value+delta
                elif key.endswith('_offsets') and isinstance(value,list):obj[key]=[v+delta for v in value]
        inst['reference_colour_stream_offsets']=inst['colour_stream_offsets']
        inst['colour_stream_offsets']=grouped
        manifest['demo_route']['cold_offset']+=delta
        manifest['shared_static_frame_sha256']=[]
        manifest['static_frame_sha256']=[]
        for name,mapping in zip(self.p.MAP_NAMES,self.visual_maps):
            frame=bytearray(self.p.title_framebuffer(mapping,self.visual_tiles))
            for (screen,cell),record in self.cells.items():
                if screen!=name:continue
                if not any(self.visual_tiles[mapping[cell]]) and (screen,cell) not in self.overridden:continue
                for row,bits in enumerate(bytes.fromhex(record['mask'])):
                    at=cell//40*1280+cell%40*4+row*160;c=record['colour']
                    frame[at:at+4]=bytes((c if bits&(128>>(j*2)) else 0)*16+(c if bits&(64>>(j*2)) else 0) for j in range(4))
            manifest['shared_static_frame_sha256'].append(hashlib.sha256(frame).hexdigest())
            if name=='instructions':self.p.blend_native_surface(frame,instruction_source['cucumber_destination'],instruction_source['cucumber_native'])
            manifest['static_frame_sha256'].append(hashlib.sha256(frame).hexdigest())
        self.args.manifest_output.write_text(json.dumps(manifest,indent=2)+'\n')
