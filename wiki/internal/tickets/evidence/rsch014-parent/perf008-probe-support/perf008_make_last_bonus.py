from pathlib import Path
root=Path('/mnt/e/projects/ladybug')
s=(root/'repro/rsch014_current_triggers_settled.py').read_text()
s=s.replace("for name in ('pickup','gate rotation'):","for name in ('pickup',):")
s=s.replace("                place(px,py,direction,3)","                e['initial_part']=read(ms['STAGE'])[0]\n                place(px,py,direction,3)")
s=s.replace("                place(px,py,direction,3)","                write(ms['DOTS_LEFT'],[0]);write(ms['BONUS_LEFT'],[1])\n                place(px,py,direction,3)")
s=s.replace("                assert row['mode']==0 and row['enemies']==4 and row['fault']==0,'event fixture left active four-enemy phase'", "                assert row['fault']==0,'last-bonus scheduler fault'\n                if read(0xA5)==bytes([1]) and read(ms['STAGE'])[0]==e['initial_part']+1:break")
cleanup=s.rfind('        reset_event()')
assert cleanup>=0
s=s[:cleanup]+s[cleanup:].replace('        reset_event()','        # Preserve final handoff state for the acceptance assertion.',1)
s=s.replace("    e['status']='scoped-pass'", "    e['last_bonus_handoff']={'mode':read(0xA5)[0],'screen':read(0xA6)[0],'part':read(ms['STAGE'])[0],'bonus_left_reinitialized':read(ms['BONUS_LEFT'])[0],'stage_pending':read(ms['STAGE_PENDING'])[0]}\n    assert read(ms['STAGE'])[0]==e['initial_part']+1 and read(0xA5)==bytes([1]) and read(ms['STAGE_PENDING'])==b'\\0',e['last_bonus_handoff']\n    e['status']='scoped-pass'")
s=s.replace("'C3 reference ROM; current enemy/render binary differs.'", "'Candidate guarded ROM; forced last-bonus precondition, real collision/popup/handoff; stage dominance pixels covered separately.'")
(root/'repro/perf008_last_bonus.py').write_text(s)
