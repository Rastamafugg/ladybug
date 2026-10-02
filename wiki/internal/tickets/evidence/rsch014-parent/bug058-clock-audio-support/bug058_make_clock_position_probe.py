from pathlib import Path
root=Path('/mnt/e/projects/ladybug')
s=(root/'repro/rsch014_current_triggers_settled.py').read_text()
s=s.replace("    start=c.call('read_cycles')['event_ticks']\n    detail,hits=", "    start=c.call('read_cycles')['event_ticks']\n    before['independent_event_ticks_before']=start\n    before['player_fb_before']=int.from_bytes(read(ms['PLAYER_FB'],2),'big')\n    before['enemy_records_before']=read(es['ENEMY_TABLE'],32).hex()\n    detail,hits=",1)
s=s.replace("    if detail is not None:\n        before.update", "    before['independent_event_ticks_after']=c.call('read_cycles')['event_ticks']\n    before['player_fb_after']=int.from_bytes(read(ms['PLAYER_FB'],2),'big')\n    before['enemy_records_after']=read(es['ENEMY_TABLE'],32).hex()\n    if detail is not None:\n        before.update",1)
needle="    layout=json.loads((b/'ladybug-sparse-layout.json').read_text())"
insert="""    if '--two-step-cap-fit' in sys.argv[3:]:
        early_fitted=(Path(__file__).parent/'bug058-catchup-banked-fit.bin').read_bytes()
        c.call('write_memory',{'space':'physical','addr':0x34*8192+0xBD44-0xA000,'data':early_fitted.hex()})
        assert phys(0x34,0xBD44,len(early_fitted))==early_fitted,'pre-demo fitted helper delivery'
        e['early_cap_overlay']={'bytes':len(early_fitted),'sha256':r.digest(early_fitted),'phase':'after exact cold-ROM installation proof, before natural demo/credited gameplay'}
"""
assert s.count(needle)==1
s=s.replace(needle,insert+needle)
s=s.replace("assert len(fitted)<=698 and phys(0x34,0xBD44,len(helper))==helper,'fitted helper baseline identity'", "assert len(fitted)<=698 and phys(0x34,0xBD44,len(fitted))==fitted,'fitted helper identity after natural routes'")
s=s.replace("'C3 reference ROM; current enemy/render binary differs.'", "'Accepted guard ROM f18bb3e8; optional byte-proven cap helper research overlay from before natural demo/credited entry.'")
(root/'repro/bug058_clock_position_probe.py').write_text(s)
