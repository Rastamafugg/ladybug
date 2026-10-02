from pathlib import Path
root=Path('/mnt/e/projects/ladybug');s=(root/'repro/perf008_integrated_last_bonus.py').read_text()
s=s.replace("b=w/'build';ms=", "b=w/'repro/perf008-execution/default-build';ms=",1)
s=s.replace("    start=c.call('read_cycles')['event_ticks']\n    detail,hits=", "    start=c.call('read_cycles')['event_ticks']\n    before['enemy_records_before']=read(es['ENEMY_TABLE'],32).hex()\n    before['part_before']=read(ms['STAGE'])[0]\n    detail,hits=",1)
s=s.replace('    if detail is not None:\n        before.update', "    before['enemy_records_after']=read(es['ENEMY_TABLE'],32).hex()\n    before['part_after']=read(ms['STAGE'])[0]\n    if detail is not None:\n        before.update",1)
s=s.replace("    before['part_after']=read(ms['STAGE'])[0]", "    before['part_after']=read(ms['STAGE'])[0]\n    before['transients_after']={name:read(ms[name])[0] for name in ('INITIAL_ENTRY_STATE','DEATH_STATE','PICKUP_TIMER','STAGE_PENDING','RENDER_GATE_ID','RENDER_GATE2_ID')}",1)
insert='''
    # Real level load/intro/installation follows the forced final-bonus trigger.
    # Do not claim that all Part1 flowers were naturally earned.
    profile_enabled=False;deadline=time.monotonic()+45
    intro=[]
    for index in range(400):
        row=measure();intro.append(row)
        if read(0xA5)==b'\\0' and read(ms['INITIAL_ENTRY_STATE'])==b'\\0':break
    assert len(intro)<400 and read(ms['STAGE'])[0]==2,'bounded Part2 gameplay marker absent'
    assert read(0x38F,len(stage))==stage,'Part2 relocated active identity'
    assert read(0x800,len(enemy))==enemy,'Part2 enemy destination identity'
    assert phys(0x34,0xBD44,len(helper))==helper,'Part2 clock helper identity'
    e['part2_initialization']={'worklists':len(intro),'part':2,'mode':read(0xA5)[0],'enemy_active_initial':read(ms['ENEMY_ACTIVE'])[0],
       'active_enemy_helper_identity':True,'natural_code_after_controlled_last_bonus':True}
    write(ms['PLAYER_CELL_X'],[22,22]);word(ms['PLAYER_FB'],0x2000+(22*8-8)*160+(22+7)*4);write(ms['PLAYER_DIR'],[255])
    write(ms['PLAYER_WANT'],[255]);write(ms['PLAYER_STEP'],[0]);write(ms['PLAYER_MANUAL'],[1])
    deadline=time.monotonic()+45
    while read(ms['ENEMY_ACTIVE'])[0]<4:
        release_one();[measure() for _ in range(3)]
    for i in range(4):apwrite(ads['audio_slot0']+i*28,[255])
    apwrite(ads['audio_music_count'],[0]);write(ads['AUDIO_Q_COUNT'],[0]);write(ads['AUDIO_CREDIT_PENDING'],[0])
    rows=[];settling=[]
    for index in range(96):
        table=read(es['ENEMY_TABLE'],32)
        roaming=all(table[i] and table[i+6] for i in range(0,32,8))
        row=measure();row['steps']=(row['logical_after']-row['logical'])&65535
        e['part2_last_row']=row
        assert row['mode']==0 and row['enemies']==4 and row['part_after']==2 and row['fault']==0
        settling.append(row)
        if roaming and not any(row['transients_after'].values()) and row['steps']==2 and row['debt_after']==0:rows.append(row)
        else:rows=[]
        if len(rows)==8:break
    assert len(rows)==8,'eight Part2 four-roaming worklists absent'
    e['part2_roaming']=rows
    e['part2_settling']={'worklists':len(settling),'step_values':sorted({x['steps'] for x in settling}),'transient_values':{name:sorted({x['transients_after'][name] for x in settling}) for name in settling[0]['transients_after']},'quiet_control':'player direction/want invalid255, step0, manual1; require8 consecutive transient-free/debt-free two-tick worklists'}
'''
needle="    e['status']='scoped-pass'"
assert s.count(needle)==1;s=s.replace(needle,insert+'\n'+needle)
(root/'repro/bug087_transition_probe.py').write_text(s)
