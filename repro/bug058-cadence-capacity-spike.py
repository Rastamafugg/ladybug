from pathlib import Path
import subprocess,re,json
w=Path('/mnt/c/Users/19029/.codex/worktrees/bug-046-word-carryover/ladybug');b=w/'build/cadence-capacity';b.mkdir(exist_ok=True);r=Path('/mnt/e/projects/ladybug')
s=(w/'src/main.s').read_text();s=s.replace('\nresident_end\n','\ncadence_slot_selected\n        ldb     ENEMY_WORK\n        ldy     #$BC30\n        lda     b,y\n        rts\nresident_end\n',1);(b/'main.s').write_text(s)
s=(w/'src/enemy_runtime.s').read_text();a=s.index('\nframebuffer_capture_back\n');z=s.index('\n; Vbord is the only',a);old=s[a:z];s=s[:a]+'\nframebuffer_capture_back\n        jmp     $BC50\n\n'+s[z:]
s=s.replace('actor_closure_restore\n','actor_closure_restore\n        jsr     $BD00          ; proposed planner entry; not implemented by this sizing spike\n',1)
s=s.replace('acr_enemy_loop\n','acr_enemy_loop\n        jsr     $DFEA\n        beq     acr_enemy_next\n',1)
s=s.replace('acd_save_loop\n','acd_save_loop\n        jsr     $DFEA\n        beq     acd_save_next\n',1)
s=s.replace('acd_draw_loop\n','acd_draw_loop\n        jsr     $DFEA\n        beq     acd_draw_next\n',1)
# Current roaming save/capture receives the projection record, but validity still updates the logical record.
s=s.replace('        sta     6,x\nacd_save_next','        sta     6,x\n        ldb     #4\n        subb    ENEMY_WORK\n        lslb\n        lslb\n        lslb\n        ldy     #ENEMY_TABLE\n        leay    b,y\n        sta     6,y\nacd_save_next',1)
start=s.index('\nactor_closure_restore\n');end=s.index('\nframebuffer_init_impl\n',start);part=s[start:end].replace('ldx     #ENEMY_TABLE','ldx     #$BC04')
part=part.replace('        ldb     7,x\n        pshs    x\n        ldx     1,x\n        lbsr    draw_enemy_fb','        ldb     ENEMY_WORK\n        decb\n        ldy     #$BC24\n        lda     b,y\n        pshs    x\n        ldx     1,x\n        lbsr    draw_enemy_cached_frame',1)
s=s[:start]+part+s[end:];s=s.replace('draw_enemy_fb\n        lbsr    enemy_frame_number\n','draw_enemy_fb\n        lbsr    enemy_frame_number\ndraw_enemy_cached_frame\n',1);(b/'enemy.s').write_text(s)
for name,defines in [('main',['-DBUG011_DEVELOPMENT_PROFILE=1','-DCOMPLETE_PROFILE=1','-DHIGHSCORE_TEST_PROFILE=0','-DHIGHSCORE_PHASE_HELPER=0','-DPRESENTATION_NAME_ENTRY_DATA=0','-DINPUT_JOYSTICK=0']),('enemy',[])]:
 cmd=['lwasm','-9','--format=raw']+defines+['--output='+str(b/(name+'.bin')),'--map='+str(b/(name+'.map')),'-I',str(w/'build'),'-I',str(w/'src'),str(b/(name+'.s'))];subprocess.run(cmd,cwd=w,check=True)
 print(name,len((b/(name+'.bin')).read_bytes()),[x for x in (b/(name+'.map')).read_text().splitlines() if re.search(r'(cadence_slot_selected|resident_end|enemy_runtime_end|roam_reverse_masks) ',x)])
# Preserve the sizing-only source, explicitly not a runnable candidate.
(r/'repro/bug058-cadence-capacity-20260927.json').write_text(json.dumps({'status':'Call-site sizing spike only; planner and relocated publisher bodies not linked. Not a ROM and not a complete fit.','state_bytes':76,'state_range':['BC04','BC4F'],'proposed_executable_range':['BC50','BFFD'],'executable_bytes_available':942,'proposed_publisher_entry':'BC50','proposed_planner_entry':'BD00','resident_helper_bytes':9,'resident_used':8179,'resident_limit':8192,'enemy_artifact_bytes':len((b/'enemy.bin').read_bytes()),'cartridge_source_free':413,'relocated_publisher_old_bytes':61,'relocated_publisher_gateway_bytes':3,'new_low_module_net_bytes':-18,'runtime_changed':False},indent=2)+'\n')
