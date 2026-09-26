from pathlib import Path
import sys
root_arg=Path(sys.argv[1]).resolve();output_arg=Path(sys.argv[2]).resolve()
expiry_arg=len(sys.argv)>3 and sys.argv[3]=="expiry"
source=Path(__file__).with_name('bug044-ranking-end-20260926.py').read_text()
source=source.replace('root = Path(__file__).resolve().parents[1]','root = root_arg')
source=source.replace('prefix = source.split',"source=source.replace('root = Path(__file__).resolve().parents[1]', 'root = root_arg')\nprefix = source.split")
source=source.replace('scenario=sys.argv[1] if len(sys.argv)>1 else "rank1"','scenario="rank1"')
hook=r"""
    audio_symbols=runtime.symbols(build/'ladybug-audio-runtime.map')
    audio_artifact=(build/'ladybug-audio-runtime.bin').read_bytes()
    audio_calls=[];audio_outputs=[];name_credit_test={'injected':False,'samples':0}
    native_call=client.call
    audio_hooks=monitor.setup(client,[audio_symbols['audio_enqueue_route'],audio_symbols['audio_mix_write_done']])
    def observed_call(method,params=None,**kwargs):
        result=native_call(method,params,**kwargs)
        if method!='wait_for_stop':return result
        deadline=time.monotonic()+min(40,(params or {}).get('timeout_ms',10000)/1000)
        while result.get('reason')=='breakpoint' and result.get('pc') in (audio_symbols['audio_enqueue_route'],audio_symbols['audio_mix_write_done']):
            pc=result['pc'];assert runtime.read_bytes(client,pc,3)==audio_artifact[pc-0xa000:pc-0xa000+3]
            def audio_bytes(label,n):return physical(0x3d*8192+audio_symbols[label]-0xa000,n)
            if low(0xa5)[0]==8:
                if low(0xe2)[0]==1 and pc==audio_symbols['audio_mix_write_done']:
                    name_credit_test['samples']+=1
                    if not name_credit_test['injected']:
                        name_credit_test.update(injected=True,before=low(0xa8)[0])
                        native_call('inject_key',{'key':5,'action':'press'});native_call('inject_key',{'key':1,'action':'press'})
                    elif name_credit_test['samples']==3:
                        name_credit_test['after']=low(0xa8)[0]
                        assert name_credit_test['after']==name_credit_test['before']+1
                        native_call('inject_key',{'key':5,'action':'release'});native_call('inject_key',{'key':1,'action':'release'})
                if pc==audio_symbols['audio_enqueue_route']:
                    audio_calls.append({'cue':native_call('read_registers')['a'],'length':low(0xcb)[0],'flags':low(0xe2)[0],'timer_phase':low(0xe1)[0],'pending':low(0x91)[0]})
                else:
                    slots=[audio_bytes('audio_slot'+str(i),17) for i in range(4)]
                    active=[x for x in slots if x[0]!=255]
                    exclusive=[x for x in active if x[2]&1]
                    heard=[max(exclusive,key=lambda x:x[1])[0]] if exclusive else [x[0] for x in active if any(a<15 for a in x[12:15]) or x[16]<15]
                    audio_outputs.append({'heard':heard,'mixed':audio_bytes('audio_mix_atten',3).hex(),'shadow':audio_bytes('audio_mix_shadow',11).hex(),'flags':low(0xe2)[0]})
            assert time.monotonic()<deadline,'audio observation boundary timeout'
            native_call('run');result=native_call('wait_for_stop',{'timeout_ms':max(1,int((deadline-time.monotonic())*1000))},timeout=42)
        return result
    client.call=observed_call
"""
source=source.replace('    # Sample complete active name-entry calls with actual keyboard input.',hook+'\n    # Sample complete active name-entry calls with actual keyboard input.')
checks=r"""
    evidence['audio_observed']={'requests':audio_calls,'outputs':audio_outputs[-4:],'sample_count':len(audio_outputs)}
    required=(2,4,9) if expiry_arg else (2,4,9,8)
    requested=[x['cue'] for x in audio_calls]
    heard={cue for x in audio_outputs for cue in x['heard'] if x['mixed']!='0f0f0f'}
    assert all(cue in requested for cue in required),(requested,heard)
    assert all(cue in heard for cue in required),(requested,heard)
    assert requested.count(8)==(0 if expiry_arg else 1),requested
    assert all(x['pending']==0 and x['timer_phase']>=128 for x in audio_calls if x['cue']==4)
    assert all(physical(0x3d*8192+audio_symbols['audio_slot'+str(i)]-0xa000,1)==bytes([255]) for i in range(4))
    if not expiry_arg:
        assert name_credit_test['injected'] and name_credit_test.get('after')==name_credit_test['before']+1
        assert 12 in heard
    evidence['name_credit_start_wait']=name_credit_test
    evidence['audio']={'requests':audio_calls,'heard_cues':sorted(heard),'output_samples':len(audio_outputs),'END_requested_once':not expiry_arg,'timer_expiry_without_END_cue':expiry_arg,'music_complete_before_commit':True,'scope':'Seeded qualifying score, natural death and existing controlled-direction name route; actual mixer/shadow output, not physical listening'}
"""
source=source.replace('    expected_record = bytes.fromhex(score_final)',checks+'\n    expected_record = bytes.fromhex(score_final)')
source=source.replace('(build / f"bug044-ranking-{scenario}-20260926.json").write_text','output_arg.write_text')
source=source.replace('assert runtime.frame_tile(frame,manifest["high_score_table"]["name_destinations"][0]+i*4)==expected_tile(native),("rank-name",owner,i)', 'assert runtime.frame_tile(frame,manifest["high_score_table"]["name_destinations"][0]+i*4)==expected_tile(native),("rank-name",owner,i,runtime.frame_tile(frame,manifest["high_score_table"]["name_destinations"][0]+i*4).hex(),expected_tile(native).hex(),low(0xa5,48).hex(),low(0x8f,10).hex())')
# BUG-051 supersedes the old generic descriptor pen in the first table row.
source=source.replace('expected_tile(native),("rank-name"','bytes((0x10 if v>>4 else 0)+(1 if v&15 else 0) for v in expected_tile(native)),("rank-name"')
source=source.replace('expected_tile(glyphs[digit]),("rank-score"','bytes((0x10 if v>>4 else 0)+(1 if v&15 else 0) for v in expected_tile(glyphs[digit])),("rank-score"')
if expiry_arg:
    expiry_code = r"""
    evidence['commit']['pending_at_END']=physical(pending_physical,7).hex()
    constants=runtime.symbols(build/'ladybug-highscore-helper.map')
    runtime.write_byte(client,0xe9,constants['PRESENTATION_NAME_ENTRY_TIMER_COUNT']-1)
    runtime.write_byte(client,0xe8,constants['PRESENTATION_NAME_ENTRY_TIMER_FRAMES']-1)
    runtime.write_byte(client,0xe1,0)
    runtime.write_byte(client,0x5,255);runtime.write_byte(client,0xf,255)
    monitor.clear(client,name_bp);name_bp=[]
    end_hit=go('highscore_after_highscore_start',helper)
    evidence['forced_timer_expiry']={'last_box':constants['PRESENTATION_NAME_ENTRY_TIMER_COUNT']-1,'flags_after_drain':low(0xe2)[0]}
"""
    source=source.replace('    end_hit = route_to_end(contract["end_cells"][0])',expiry_code)
    source=source.replace('"END_requested": True','"END_requested": False')
source=source.replace('            key(5,True);go("start_screen_done");key(5,False);go("credit_tick")\n            for _ in range(3):go("pft_ready")', '            for _ in range(32):\n                go("pft_ready")\n                if low(0x8F)[0]!=owner and low(0x91)[0]==0:break\n            else:raise AssertionError("alternate high-score publication absent")')
exec(compile(source,str(__file__),'exec'))
