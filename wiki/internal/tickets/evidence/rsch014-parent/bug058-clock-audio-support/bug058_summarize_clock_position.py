import hashlib,json
from pathlib import Path
root=Path('/mnt/e/projects/ladybug')
def xy(ptr):return ((ptr-0x2000)%160*2,(ptr-0x2000)//160)
def dist(a,b):
    ax,ay=xy(a);bx,by=xy(b);return abs(ax-bx)+abs(ay-by)
def actors(row,side):
    data=bytes.fromhex(row['enemy_records_'+side]);return [int.from_bytes(data[i+1:i+3],'big') for i in range(0,32,8)]
result={'revision':'accepted BUG111 source, ROM f18bb3e8; optional isolated696-byte clock helper overlay','units':'fast CPU cycles=independent emulator event ticks/8; actor distance=Manhattan origin displacement in pixels (byte x2, raster y1)','limitations':['Source-state origin displacement, not published-pixel acceptance.','Single fixture observations, not whole-game maxima.','Cap deliberately discards overdue simulation time; timers/movement lag real time, audio clock unchanged.','No full candidate profile build or visible audio-backend comparison; no production change.'],'runs':{}}
for name in ('baseline','cap'):
    path=root/f'repro/bug058-clock-position-{name}.json';e=json.loads(path.read_text())
    assert e['status']=='scoped-pass',e
    run={'rom_sha256':e['rom_sha256'],'trace_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'cases':[]}
    for case in e['pickup_gate_cadence']:
        rows=case['worklists'];records=[]
        for i,row in enumerate(rows):
            old=actors(row,'before');new=actors(row,'after')
            item={'index':i,'steps':row['steps'],'raw':row['raw'],'logical_after':row['logical_after'],'debt_after':row['debt_after'],'player_pixels':dist(row['player_fb_before'],row['player_fb_after']),'enemy_pixels':[dist(a,b) for a,b in zip(old,new)],'cycles':row['cycles']}
            if i:
                prev=rows[i-1];item['raw_start_delta']=(row['raw']-prev['raw'])&65535
                item['independent_start_interval_cycles']=(row['independent_event_ticks_before']-prev['independent_event_ticks_before'])/8
            records.append(item)
        peak=max(records,key=lambda x:max([x['player_pixels'],*x['enemy_pixels']]))
        run['cases'].append({'name':case['name'],'worklists':len(rows),'step_values':sorted({r['steps'] for r in rows}),'max_debt':max(r['debt_after'] for r in rows),'max_player_origin_displacement':max(x['player_pixels'] for x in records),'max_each_enemy_origin_displacement':[max(x['enemy_pixels'][j] for x in records) for j in range(4)],'peak_displacement_record':peak,'four_step_records':[x for x in records if x['steps']>=3],'popup_zero_worklist':next((i for i,r in enumerate(rows) if case['name']=='pickup' and r['marker']['pickup_timer']==0),None),'final_popup_timer':rows[-1]['marker'].get('pickup_timer'),'logical_frame_span':(rows[-1]['logical_after']-rows[0]['logical'])&65535,'raw_frame_span':(rows[-1]['raw']-rows[0]['raw'])&65535,'cycle_range':[min(x['cycles'] for x in rows),max(x['cycles'] for x in rows)]})
    result['runs'][name]=run
(root/'repro/bug058-clock-position-summary.json').write_text(json.dumps(result,indent=2)+'\n')
for name,run in result['runs'].items():
    for c in run['cases']:
        print(name,c['name'],'steps',c['step_values'],'debt',c['max_debt'],'player',c['max_player_origin_displacement'],'enemies',c['max_each_enemy_origin_displacement'],'popupzero',c['popup_zero_worklist'],'span raw/logical',c['raw_frame_span'],c['logical_frame_span'])
