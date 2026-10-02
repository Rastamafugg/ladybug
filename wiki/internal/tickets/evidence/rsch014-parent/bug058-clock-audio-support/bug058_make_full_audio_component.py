from pathlib import Path
root=Path('/mnt/e/projects/ladybug')
s=(root/'repro/rsch014_current_audio_controls.py').read_text()
a=s.index("    if '--cadence-effects'")
z=s.index("    e['status']='scoped-pass'",a)
body='''    if '--full-audio-component' in sys.argv[3:]:
        e['full_audio_components']=[]
        # Synthetic service timing: real installed API/code, IRQ masked;
        # advance only the raw audio clock by exactly two frame units.
        # No actor/render execution or backend-wall-time claim.
        for name,cue in (('gate effect',0),('vegetable pickup effect',1),('collectible pickup effect',2),('release effect',5),('stage-clear music',9)):
            deadline=time.monotonic()+45
            restore_pages(frozen)
            c.call('write_registers',{k:natural_regs[k] for k in ('a','b','cc','dp','x','y','u','s','pc')})
            write(0xFFA5,[0x3D]);enqueue_cost,_=call(ads['audio_enqueue_impl'],cue);write(0xFFA5,[0x34])
            call(0x39B,3)
            rows=[];heard=False
            for index in range(384):
                now=(int.from_bytes(read(2,2),'big')+2)&65535;word(2,now)
                costs=[call(0x39B,mode)[0] for mode in (0,1,2)]
                slots=list(phys(0x3D,ads['audio_slot0'],112)[::28])
                heard|=cue in slots
                queue=read(ads['AUDIO_Q_COUNT'])[0];music=phys(0x3D,ads['audio_music_count'],1)[0]
                rows.append({'index':index,'clock':now,'costs_elapsed_admit_output':costs,'total_cycles':sum(costs),'slots':slots,'queue':queue,'music':music,'late':phys(0x3D,ads['audio_adaptive_late'],1)[0]})
                if heard and cue not in slots and queue==0 and music==0:break
            case={'name':name,'cue':cue,'enqueue_cycles':enqueue_cost,'steps':len(rows),'raw_frame_units':2*len(rows),'admitted':heard,'drained':heard and cue not in slots and queue==0 and music==0,'total_cost_range':[min(x['total_cycles'] for x in rows),max(x['total_cycles'] for x in rows)],'component_maxima':[max(x['costs_elapsed_admit_output'][j] for x in rows) for j in range(3)],'rows_sha256':r.digest(json.dumps(rows,sort_keys=True).encode()),'retained_rows':[rows[0],max(rows,key=lambda x:x['total_cycles']),rows[-1]],'deadline_seconds':45,'success_marker':'cue admitted then absent and queues empty','timeout_meaning':'complete encoded cue boundary not observed; not proof of slow code'}
            e['full_audio_components'].append(case)
            assert heard and case['drained'] and index<383,('full component drain absent',name,case)
        restore_pages(frozen)
'''
s=s[:a]+body+s[z:]
s=s.replace("e['limitations']=['Current root ROM b452, receipt fe160; no runtime code overlay.'", "e['limitations']=['Accepted BUG111 guard ROM f18bb3e8; byte-proven installed real code, no runtime code overlay.', 'Full-cue component is synthetic IRQ-masked 2-frame audio-clock advances; no foreground actor/render or host/backend-wall-time attribution.'")
(root/'repro/bug058_full_audio_component.py').write_text(s)
