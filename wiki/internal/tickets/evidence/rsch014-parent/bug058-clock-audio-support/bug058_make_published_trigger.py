from pathlib import Path
root=Path('/mnt/e/projects/ladybug')
s=(root/'repro/bug058_clock_position_perf008.py').read_text()
helpers='''
from build_screen import compile_player_sprites,compile_enemy_sprites,expand_sprite,PLAYER_PEN_MAP
from build_sparse_sprites import GAMEPLAY_ENEMY_PEN_MAPS
player_templates=[expand_sprite(x,PLAYER_PEN_MAP) for x in compile_player_sprites(w/'assets/arcade/sprites.json')]
enemy_templates=[expand_sprite(x,GAMEPLAY_ENEMY_PEN_MAPS[0]) for x in compile_enemy_sprites(w/'assets/arcade/sprites.json')[:16]]
def opaque_match(frame,pointer,templates):
    offset=pointer-0x2000
    if offset<0 or offset+15*160+8>len(frame):return []
    matches=[]
    for index,sprite in enumerate(templates):
        ok=True
        for y in range(16):
            for x in range(8):
                actual=frame[offset+y*160+x];expected=sprite[y*8+x]
                if expected&240 and actual&240!=expected&240:ok=False;break
                if expected&15 and actual&15!=expected&15:ok=False;break
            if not ok:break
        if ok:matches.append(index)
    return matches
def overlaps(a,b):
    ay,ax=divmod(a-0x2000,160);by,bx=divmod(b-0x2000,160)
    return ax<bx+8 and bx<ax+8 and ay<by+16 and by<ay+16
def published():
    owner=read(0x8F)[0];ledger=phys(0x34,0xA900+owner*256,256)
    frame=r.read_owner(c,owner);actors=[]
    if ledger[2]:actors.append({'name':'player','pointer':int.from_bytes(ledger[4:6],'big')})
    for i in range(4):
        rec=ledger[8+i*8:16+i*8]
        if rec[0]:actors.append({'name':'enemy'+str(i),'pointer':int.from_bytes(rec[1:3],'big'),'roaming':bool(rec[6])})
    for actor in actors:
        actor['overlap']=[x['name'] for x in actors if x is not actor and overlaps(x['pointer'],actor['pointer'])]
        actor['templates']=opaque_match(frame,actor['pointer'],player_templates if actor['name']=='player' else enemy_templates)
        actor['opaque_pixels_match']=bool(actor['templates'])
    return {'owner_secondary':owner,'commit':int.from_bytes(read(0x92,2),'big'),
            'raw':int.from_bytes(read(2,2),'big'),'independent_event_ticks':c.call('read_cycles')['event_ticks'],
            'frame_sha256':r.digest(frame),'actors':actors}
'''
s=s.replace('def measure():',helpers+'\ndef measure():',1)
s=s.replace("    before['enemy_records_before']=read(es['ENEMY_TABLE'],32).hex()", "    before['enemy_records_before']=read(es['ENEMY_TABLE'],32).hex()\n    if publish_enabled:before['published_front']=published()",1)
s=s.replace('profile_enabled=False\nresident=', 'profile_enabled=False\npublish_enabled=False\nresident=',1)
s=s.replace("            for index in range(58 if name=='pickup' else 12):", "            publish_enabled=True\n            for index in range(58 if name=='pickup' else 12):",1)
s=s.replace("            e['pickup_gate_cadence'].append", "            publish_enabled=False\n            e['pickup_gate_cadence'].append",1)
assert "if publish_enabled" in s and 'publish_enabled=True' in s
(root/'repro/bug058_published_trigger.py').write_text(s)
full=s.replace("b=w/'repro/perf008-execution/default-build';ms=", "b=Path('/mnt/e/projects/ladybug/repro/bug058-cap-current/build');ms=",1)
(root/'repro/bug058_published_trigger_full_cap.py').write_text(full)
