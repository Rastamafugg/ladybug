; GMC bank-3 enemy runtime, copied to low RAM $0800 during boot.
; Entry table offsets are part of the resident/runtime contract.

        pragma  nodollarlocal,6809
        include "ladybug_runtime_symbols.inc"
        org     $0800

PERSISTENT_FB  equ 1

        jmp     enemy_init_impl
        jmp     enemy_tick_impl
        jmp     enemy_release_impl
        jmp     enemy_collect_impl
        jmp     player_compose_impl
        jmp     gate_compose_impl
        jmp     player_draw_impl
        jmp     enemy_render_impl
        jmp     frame_render_impl
        jmp     framebuffer_init_impl
        jmp     framebuffer_irq_impl
        jmp     sparse_blit_fb

ENEMY_ANIM     equ $0054
ENEMY_TIMER    equ $0055
ENEMY_ACTIVE   equ $0058
ENEMY_RELEASED equ $0059
VEG_STATE      equ $005A
FREEZE_TIMER   equ $005B
ENEMY_WORK     equ $005D
ENEMY_PTR      equ $005E
ENEMY_NEST_DIRTY equ $0060
ENEMY_MOVE     equ $0061
ENEMY_DEATH_LATCH equ $0062
ENEMY_ROW      equ $0063
BOX_TIMER      equ $004A
BOX_INDEX      equ $004B
BOX_PHASE      equ $004C
STAGE_COUNT    equ $0064
STAGE_PIXEL    equ $0065
STAGE_SOURCE   equ $0066
PLAYER_BG_VALID equ $006A       ; PLAYER_BG_PTR contains restorable pixels
PLAYER_TICK_PENDING equ $006B
PLAYER_OLD_FB   equ $0067
PLAYER_DX       equ $006C
PLAYER_DY       equ $006D
PLAYER_ROW      equ $006E
GATE_COMPOSE_MODE equ $006F
GATE_RECT_FB    equ $0070
GATE_RECT_WIDTH equ $0072
GATE_RECT_ROWS  equ $0073
GATE_START_X    equ $0074
GATE_START_Y    equ $0075
GATE_END_X      equ $0076
GATE_END_Y      equ $0077
GATE_SHADOW_PAGE equ $0078
GATE_COPY_COUNT equ $0079
GATE_COPY_ROWS  equ $007A
GATE_WORK_ID    equ $007B
ENEMY_CANDIDATE equ $007C
ENEMY_REVERSE   equ $007D
ENEMY_ROAMING   equ $007E
RENDER_FLAGS    equ $007F
RENDER_FLAGS2   equ $0080
RENDER_BOX_INDEX equ $0081
RENDER_BOX_COLOR equ $0082
RENDER_LETTER_X equ $0083
RENDER_LETTER_Y equ $0084
RENDER_LETTER_COLOR equ $0085
ENEMY_OLD_VALID equ $0086
ENEMY_RENDER_FLAGS equ $0087
RENDER_GATE_ID  equ $0088
RENDER_GATE_MODE equ $0089
RENDER_GATE2_ID equ $008A
RENDER_GATE2_MODE equ $008B
RENDER_ZONE_Y   equ $008C
RENDER_GATE_STYLE equ $008D
RENDER_GATE2_STYLE equ $008E
FB_FRONT_ID    equ $008F
FB_BACK_ID     equ $0090
FB_RENDER_PENDING equ $0091
FB_COMMIT_SEQ  equ $0092
FB_SIM_SEQ     equ $0094
FB_MISSED_COMMIT equ $0096
FB_RENDER_ACTIVE equ $0098
FB_WRITE_FRONT_FAULT equ $0099
FB_INIT_STATE  equ $009A
ENEMY_CAPTURE_DIRTY equ $009B
RING_PHASE     equ $009C
RING_ROW       equ $009D
RING_BASE      equ $009E
PLAYER_BG_PTR  equ $00A2        ; selected A/B player save-under buffer
GATE_ID         equ $0013
GATE_X          equ $0014
GATE_Y          equ $0015
GATE_ANIM_ID    equ $0019
TEST_X          equ $0010
TEST_Y          equ $0011
HUD_X           equ $0027
HUD_Y           equ $0028
HUD_COLOR       equ $0029
PLAYER_CELL_X  equ $0009
PLAYER_CELL_Y  equ $000A
PLAYER_FB      equ $000B
PLAYER_DIR     equ $0006
PLAYER_FACE    equ $0007
PLAYER_WANT    equ $000F
PLAYER_ANIM    equ $004F
DEATH_STATE    equ $004D
DEATH_FRAME    equ $004E
PICKUP_TIMER   equ $0051
PLAYER_ERASED equ $0069
SCORE_BCD      equ $001D
HIGH_BCD       equ $0020
STAGE          equ $0024
ENTITY_COUNT   equ $0032
ENTITY_X       equ $0036
ENTITY_Y       equ $0037
RNG_STATE      equ $0034
LAST_FRAME     equ $0000
FRAMES         equ $0002

RF_ENTITIES    equ $08
RF_PLAYER      equ $01
RF_HUD         equ $02
RF_LIVES       equ $04
RF_BOX         equ $10
RF_DOT         equ $20
RF_STAGE       equ $40
RF_DEATH       equ $80
RF2_POPUP      equ $01
RF2_MULTIPLIER equ $02
RF2_LETTER     equ $04
RF2_PERIM_RESET equ $08
ERF_INIT       equ $01
ERF_DIRTY      equ $02
ERF_ZONE_REFRESH equ $04
ERF_NEST       equ $08
ERF_NEST_ANIM  equ $10
COLOR_WHITE    equ 6

ENTITY_TABLE   equ $A380
PLAYER_BG      equ $A300
ACTOR_STAGE    equ $1800        ; always-mapped low-RAM sparse decode surface
PLAYER_STAGE   equ ACTOR_STAGE
PLAYER_OLD_STAGE equ ACTOR_STAGE+128
ENTITY_SKULL   equ 1
ENEMY_TABLE    equ $A470
GATE_STATE     equ $A240
ENEMY_ZONE_BG  equ $A490
ENEMY_NEST_CACHE equ $AD80      ; four native dormant frames, 4 * 128 bytes
ENEMY_ZONE_STAGE equ ACTOR_STAGE
ENEMY_BG_BASE  equ $A690
ENEMY_OLD_FB   equ $A890
ENEMY_BG_RING  equ $A898        ; packed row/column phase for current BACK
FB_META_A      equ $A900        ; 256-byte A ownership/damage ledger
FB_META_B      equ $AA00        ; 256-byte B ownership/damage ledger
PLAYER_BG_B    equ $AB00        ; B-side player restoration bytes
ENEMY_BG_B     equ $AB80        ; four B-side enemy restoration buffers
FBM_STATE      equ 0
FBM_DAMAGE     equ 1
FBM_PLAYER_VALID equ 2
FBM_PLAYER_RESERVED equ 3
FBM_PLAYER_FB  equ 4
FBM_ENEMIES   equ 8
FBM_ENEMY_RESERVED equ 40
FBM_ENEMY_RINGS equ 44
FBM_MAZE_DAMAGE equ 48          ; 72-byte, 576-cell reserved ledger
FBM_GATE_DAMAGE equ 120         ; three-byte, 20-gate reserved ledger
FBM_ENTITY_DAMAGE equ 123       ; twelve-byte record ledger
FBM_PERIM_DAMAGE equ 135        ; twelve-byte, 92-box reserved ledger
FBM_HUD_DAMAGE equ 147
FBM_NEST_DAMAGE equ 149
FBM_PRESENT_DAMAGE equ 150
FBM_PENDING_INTENTS equ 160       ; 18-byte intent block plus dot cell coverage
FBM_VALID      equ $01
FBM_FULL_REBUILD equ $02
ENEMY_ZONE_FB  equ $4DEC
ENEMY_FB       equ $57EC
SPRITE_SOURCE_SIZE equ 64
ENEMY_ZONE_ROWS equ 32
RECORD_SIZE    equ 8
DIR_NONE       equ $FF
GIME_PAR1      equ $FFA1
GIME_PAR5      equ $FFA5
GIME_IRQEN     equ $FF92
GIME_VOFF1     equ $FF9D
        ifne    PERSISTENT_FB
FB_SCRATCH_PAGE0 equ $28
        else
FB_SCRATCH_PAGE0 equ $2C
        endc
FB_B_PAGE0     equ $2C
LIVE_PAGE0     equ $30
SPARSE_ENEMY_INDEX_ADDR equ $0500
SPARSE_PLAYER_INDEX_ADDR equ $0680

; Record: active, framebuffer pointer, pixel phase, cell x, cell y,
; saved-background valid, selected direction.
enemy_init_impl
        lbsr    reset_enemy_state
        lda     ENEMY_RENDER_FLAGS
        ora     #ERF_INIT|ERF_DIRTY
        sta     ENEMY_RENDER_FLAGS
        rts

enemy_release_impl
        tst     DEATH_STATE
        bne     er_done
        lda     ENEMY_ACTIVE
        cmpa    #4
        bhs     er_done
        ldx     #ENEMY_TABLE
        lda     #4
        sta     ENEMY_WORK
er_find
        tst     ,x
        beq     er_use
        leax    RECORD_SIZE,x
        dec     ENEMY_WORK
        bne     er_find
        rts
er_use
        lda     #1
        sta     ,x
        ldd     #ENEMY_FB
        std     1,x
        clr     3,x
        lda     #12
        sta     4,x
        sta     5,x
        clr     6,x
        clr     7,x              ; verified den exit begins North
        inc     ENEMY_ACTIVE
        inc     ENEMY_RELEASED
        inc     ENEMY_NEST_DIRTY
        lda     ENEMY_RENDER_FLAGS
        ora     #ERF_DIRTY|ERF_NEST
        sta     ENEMY_RENDER_FLAGS
        lda     ENEMY_ACTIVE
        cmpa    #4
        bne     er_done
        lda     #1
        sta     VEG_STATE
er_done
        rts

enemy_tick_impl
        lda     ENEMY_RENDER_FLAGS
        bita    #ERF_DIRTY
        bne     et_snapshot_ready
        lbsr    roam_snapshot_old
et_snapshot_ready
        lda     DEATH_STATE
        beq     et_alive
        tst     ENEMY_DEATH_LATCH
        bne     et_death_animate
et_begin_death
        clr     ENEMY_MOVE
        lbsr    reset_enemy_state
        lda     #1
        sta     ENEMY_DEATH_LATCH
        inc     ENEMY_NEST_DIRTY
        lda     ENEMY_RENDER_FLAGS
        ora     #ERF_DIRTY|ERF_NEST
        sta     ENEMY_RENDER_FLAGS
        rts
et_death_animate
        ; Death suppresses releases and active movement, but the newly reset
        ; dormant pattern continues its normal four-frame animation.
        clr     ENEMY_MOVE
        bra     et_animation_timer
et_alive
        clr     ENEMY_DEATH_LATCH
        ; Collision is independent of movement and animation dirtiness. This
        ; keeps enemies stopped at the first decision point collidable.
        ldx     #ENEMY_TABLE
        lda     #4
        sta     ENEMY_WORK
et_contact_scan
        tst     ,x
        beq     et_contact_scan_next
        lbsr    enemy_player_contact
        lbcs    et_player_death
et_contact_scan_next
        leax    RECORD_SIZE,x
        dec     ENEMY_WORK
        bne     et_contact_scan
        ; Advance cheap timers first. Full compositing is required only when
        ; an actor moves, the shared animation changes, or external state
        ; marks the den/vegetable layer dirty.
        clr     ENEMY_MOVE
et_animation_timer
        dec     ENEMY_TIMER
        bne     et_freeze_timer
        lda     #8
        sta     ENEMY_TIMER
        inc     ENEMY_ANIM
        lda     ENEMY_ANIM
        anda    #3
        sta     ENEMY_ANIM
        tst     ENEMY_NEST_DIRTY
        bne     et_freeze_timer
        inc     ENEMY_NEST_DIRTY
        lda     ENEMY_RENDER_FLAGS
        ora     #ERF_NEST_ANIM
        sta     ENEMY_RENDER_FLAGS
et_freeze_timer
        tst     DEATH_STATE
        bne     et_render_test
        ldd     FREEZE_TIMER
        beq     et_find_movement
        subd    #1
        std     FREEZE_TIMER
        bra     et_render_test
et_find_movement
        lda     LAST_FRAME
        anda    #1
        bne     et_render_test
        ldx     #ENEMY_TABLE
        lda     #4
        sta     ENEMY_WORK
et_move_scan
        tst     ,x
        beq     et_move_next
        lda     7,x
        cmpa    #DIR_NONE
        beq     et_move_next
        lda     #1
        sta     ENEMY_MOVE
        bra     et_render_test
et_move_next
        leax    RECORD_SIZE,x
        dec     ENEMY_WORK
        bne     et_move_scan
et_render_test
        tst     ENEMY_NEST_DIRTY
        bne     et_update
        tst     ENEMY_MOVE
        bne     et_update
        rts

et_update
        tst     ENEMY_MOVE
        lbeq    et_compose
        ldx     #ENEMY_TABLE
        lda     #4
        sta     ENEMY_WORK
et_update_loop
        tst     ,x
        beq     et_update_next
        lda     7,x
        beq     et_step_north
        cmpa    #1
        beq     et_step_east
        cmpa    #2
        beq     et_step_south
        ldd     1,x
        subd    #1
        bra     et_store_step
et_step_north
        ldd     1,x
        subd    #320
        bra     et_store_step
et_step_east
        ldd     1,x
        addd    #1
        bra     et_store_step
et_step_south
        ldd     1,x
        addd    #320
et_store_step
        std     1,x
        inc     3,x
        lda     3,x
        cmpa    #4
        blo     et_contact
        clr     3,x
        lda     7,x
        beq     et_arrive_north
        cmpa    #1
        beq     et_arrive_east
        cmpa    #2
        beq     et_arrive_south
        dec     4,x
        bra     et_choose_arrival
et_arrive_north
        dec     5,x
        bra     et_choose_arrival
et_arrive_east
        inc     4,x
        bra     et_choose_arrival
et_arrive_south
        inc     5,x
et_choose_arrival
        lbsr    enemy_choose_direction
        lda     ENEMY_WORK
        pshs    a,x
        lbsr    enemy_skull_test
        puls    a,x
        sta     ENEMY_WORK
        tst     ,x
        beq     et_update_next
et_contact
        bra     et_update_next
et_player_death
        lda     #1
        sta     DEATH_STATE
        lda     #DIR_NONE
        sta     PLAYER_DIR
        sta     PLAYER_WANT
        lbra    et_begin_death
et_update_next
        leax    RECORD_SIZE,x
        dec     ENEMY_WORK
        bne     et_update_loop
et_compose
et_finish
        lda     ENEMY_RENDER_FLAGS
        ora     #ERF_DIRTY
        sta     ENEMY_RENDER_FLAGS
        rts

; Consume gameplay-owned enemy intents after all state mutation for this Vbord.
enemy_render_impl
        lda     ENEMY_RENDER_FLAGS
        bita    #ERF_INIT
        beq     eri_refresh
        lbsr    capture_zone_bg
eri_refresh
        lda     ENEMY_RENDER_FLAGS
        bita    #ERF_ZONE_REFRESH
        beq     eri_dirty
        lda     #12
        sta     ENTITY_X
        lda     RENDER_ZONE_Y
        sta     ENTITY_Y
        jsr     restore_entity_footprint
        lbsr    refresh_zone_bg_footprint
eri_dirty
        lda     ENEMY_RENDER_FLAGS
        bita    #ERF_DIRTY|ERF_NEST|ERF_NEST_ANIM
        beq     eri_done
        ifne    PERSISTENT_FB
        bita    #ERF_NEST_ANIM
        bne     eri_nest_anim
        bita    #ERF_NEST
        beq     eri_finish
        lbsr    compose_enemy_zone
        bra     eri_finish
eri_nest_anim
        lbsr    compose_enemy_animation
eri_finish
        else
        lbsr    roam_prepare_shadow
        tst     ENEMY_NEST_DIRTY
        beq     eri_finish
        lbsr    compose_enemy_zone
eri_finish
        lbsr    roam_finish_shadow
        endc
        clr     ENEMY_NEST_DIRTY
eri_done
        clr     ENEMY_RENDER_FLAGS
        rts

; Single framebuffer owner for the completed Vbord state.
frame_render_impl
        ifne    PERSISTENT_FB
        lbsr    framebuffer_prepare_back
        lbcs    fri_abort
        tst     FB_INIT_STATE
        beq     fri_render
        clr     ENEMY_CAPTURE_DIRTY
        lbsr    actor_closure_restore
        lbsr    framebuffer_queue_damage
        lbsr    framebuffer_project_damage
        lbsr    roam_mark_underlay
        else
        lbsr    framebuffer_begin_fallback
        endc
fri_render
        lbsr    frame_render_pass
        ifne    PERSISTENT_FB
        lbsr    framebuffer_finish_back
        else
        lbsr    framebuffer_finish_fallback
        endc
        clr     RENDER_FLAGS
        clr     RENDER_FLAGS2
        clr     RENDER_GATE_ID
        clr     RENDER_GATE2_ID
        clr     PLAYER_ERASED
        rts
fri_abort
        clr     FB_RENDER_ACTIVE
        rts

; Project one persistent-damage record without consuming the current epoch's
; intents. The record contains exact affected coverage, while each drawing
; routine reads the latest frozen logical state.
framebuffer_project_damage
        lbsr    framebuffer_back_meta
        tst     FBM_DAMAGE,u
        beq     fbpd_done
        ; The current final state fully replaces this owner's queued diagonal
        ; for the same gate.  Do not replay a historical transient immediately
        ; before drawing the authoritative final state.
        tst     RENDER_GATE_MODE
        beq     fbpd_save_current
        lda     RENDER_GATE_ID
        beq     fbpd_save_current
        cmpa    FBM_PENDING_INTENTS+9,u
        bne     fbpd_second_gate
        clr     FBM_PENDING_INTENTS+9,u
        clr     FBM_PENDING_INTENTS+10,u
        clr     FBM_PENDING_INTENTS+13,u
fbpd_second_gate
        cmpa    FBM_PENDING_INTENTS+11,u
        bne     fbpd_save_current
        clr     FBM_PENDING_INTENTS+11,u
        clr     FBM_PENDING_INTENTS+12,u
        clr     FBM_PENDING_INTENTS+14,u
fbpd_save_current
        lda     PLAYER_ERASED
        pshs    a
        clr     PLAYER_ERASED
        ldd     PLAYER_CELL_X
        pshs    d
        ldx     #RENDER_FLAGS
        ldb     #16
fbpd_save
        lda     ,x+
        pshs    a
        decb
        bne     fbpd_save
        leau    FBM_PENDING_INTENTS,u
        ldx     #RENDER_FLAGS
        ldb     #16
fbpd_load
        lda     ,u+
        sta     ,x+
        decb
        bne     fbpd_load
        ldd     ,u
        std     PLAYER_CELL_X
        lbsr    roam_mark_underlay
        lbsr    framebuffer_back_meta
        clr     FBM_DAMAGE,u
        lbsr    frame_render_background
        ldx     #RENDER_GATE2_STYLE
        ldb     #16
fbpd_restore
        puls    a
        sta     ,x
        leax    -1,x
        decb
        bne     fbpd_restore
        puls    d
        std     PLAYER_CELL_X
        puls    a
        sta     PLAYER_ERASED
fbpd_done
        rts

; Queue this epoch's persistent coverage for the buffer not currently being
; rendered. Actor/popup/death state is buffer-local and is excluded here.
framebuffer_queue_damage
        ldu     #FB_META_B
        tst     FB_BACK_ID
        beq     fbqd_meta
        ldu     #FB_META_A
fbqd_meta
        leau    FBM_PENDING_INTENTS,u
        ldx     #RENDER_FLAGS
        ldb     #16
fbqd_copy
        lda     ,x+
        sta     ,u+
        decb
        bne     fbqd_copy
        ldd     PLAYER_CELL_X
        std     ,u
        leau    -16,u
        lda     ,u
        anda    #RF_HUD|RF_LIVES|RF_ENTITIES|RF_BOX|RF_DOT|RF_STAGE
        sta     ,u
        lda     1,u
        anda    #RF2_MULTIPLIER|RF2_LETTER|RF2_PERIM_RESET
        sta     1,u
        lda     ENEMY_RENDER_FLAGS
        anda    #ERF_NEST|ERF_NEST_ANIM
        sta     8,u
        clr     FBM_DAMAGE-FBM_PENDING_INTENTS,u
        lda     ,u
        ora     1,u
        ora     8,u
        ora     9,u              ; RENDER_GATE_ID
        ora     11,u             ; RENDER_GATE2_ID
        beq     fbqd_done
        inc     FBM_DAMAGE-FBM_PENDING_INTENTS,u
fbqd_done
        rts

; Any projected layer that can intersect a roaming footprint invalidates strip
; reuse for this BACK transaction. HUD, lives, and perimeter never intersect.
roam_mark_underlay
        lda     RENDER_FLAGS
        anda    #RF_ENTITIES|RF_DOT|RF_STAGE
        bne     rmu_dirty
        lda     ENEMY_RENDER_FLAGS
        anda    #ERF_INIT|ERF_ZONE_REFRESH|ERF_NEST
        beq     rmu_done
rmu_dirty
        lda     #$FF
        sta     ENEMY_CAPTURE_DIRTY
rmu_done
        rts

frame_render_pass
        lbsr    frame_render_background
        ifne    PERSISTENT_FB
        lbsr    actor_closure_draw
        endc
        rts

; Draw only persistent background state. Damage replay uses this entry so an
; older ledger cannot save or publish actor pixels before closure completes.
frame_render_background
        lda     RENDER_FLAGS
        bita    #RF_STAGE
        lbne    fri_stage_background
        ifeq    PERSISTENT_FB
        lbsr    render_exposed_player
        endc

        lda     RENDER_FLAGS
        bita    #RF_ENTITIES
        beq     fri_dot
        jsr     erase_entity_footprints
        jsr     draw_entities
fri_dot
        lda     RENDER_FLAGS
        bita    #RF_DOT
        beq     fri_hud
        lda     PLAYER_CELL_X
        sta     TEST_X
        lda     PLAYER_CELL_Y
        sta     TEST_Y
        jsr     draw_maze_state_cell
fri_hud
        lbsr    enemy_render_impl
        lda     RENDER_FLAGS
        bita    #RF_HUD
        beq     fri_lives
        jsr     draw_hud
fri_lives
        lda     RENDER_FLAGS
        bita    #RF_LIVES
        beq     fri_box
        jsr     draw_lives
fri_box
        lda     RENDER_FLAGS
        bita    #RF_BOX
        beq     fri_secondary
        lda     BOX_INDEX
        pshs    a
        lda     RENDER_BOX_INDEX
        sta     BOX_INDEX
        lda     RENDER_BOX_COLOR
        sta     HUD_COLOR
        jsr     perimeter_box_coordinates
        jsr     draw_perimeter_box
        puls    a
        sta     BOX_INDEX
fri_secondary
        lda     RENDER_FLAGS2
        bita    #RF2_PERIM_RESET
        beq     fri_multiplier
        lbsr    render_perimeter_reset
fri_multiplier
        lda     RENDER_FLAGS2
        bita    #RF2_MULTIPLIER
        beq     fri_letter
        jsr     draw_multiplier_hud
fri_letter
        lda     RENDER_FLAGS2
        bita    #RF2_LETTER
        beq     fri_gate
        lda     RENDER_LETTER_X
        sta     HUD_X
        lda     RENDER_LETTER_Y
        sta     HUD_Y
        lda     RENDER_LETTER_COLOR
        sta     HUD_COLOR
        jsr     draw_recolored_map_tile
fri_gate
        lda     RENDER_GATE_ID
        beq     fri_background_done
        lda     RENDER_GATE_MODE
        sta     GATE_COMPOSE_MODE
        lbsr    gate_compose_impl
        lda     RENDER_GATE2_ID
        beq     fri_background_done
        sta     RENDER_GATE_ID
        lda     RENDER_GATE2_MODE
        sta     RENDER_GATE_MODE
        sta     GATE_COMPOSE_MODE
        lda     RENDER_GATE2_STYLE
        sta     RENDER_GATE_STYLE
        lbsr    gate_compose_impl
fri_background_done
        ifeq    PERSISTENT_FB
        bra     fri_presentation
        else
        rts
        endc

        ifeq    PERSISTENT_FB
fri_presentation
        lda     RENDER_FLAGS2
        bita    #RF2_POPUP
        beq     fri_death
        jsr     save_player
        jsr     draw_score_popup
        bra     fri_done
fri_death
        lda     RENDER_FLAGS
        bita    #RF_DEATH
        beq     fri_player
        lda     DEATH_STATE
        beq     fri_player
        cmpa    #3
        bhs     fri_done
        lda     DEATH_FRAME
        cmpa    #$FF
        beq     fri_done
        jsr     draw_death_frame
        bra     fri_done
fri_player
        lda     RENDER_FLAGS
        bita    #RF_PLAYER
        beq     fri_done
        lda     PICKUP_TIMER
        bne     fri_done
        lda     DEATH_STATE
        bne     fri_done
        tst     PLAYER_ERASED
        bne     fri_player_direct
        lbsr    player_compose_impl
        bra     fri_done
fri_player_direct
        jsr     draw_player
fri_done
        rts
        endc

render_exposed_player
        tst     PLAYER_ERASED
        beq     rep_done
        tst     PLAYER_BG_VALID
        beq     rep_done
        ldd     PLAYER_FB
        pshs    d
        ldd     PLAYER_OLD_FB
        std     PLAYER_FB
        jsr     restore_player
        puls    d
        std     PLAYER_FB
rep_done
        rts

render_perimeter_reset
        lda     BOX_INDEX
        pshs    a
        clr     BOX_INDEX
        lda     #COLOR_WHITE
        sta     HUD_COLOR
rpr_box
        jsr     perimeter_box_coordinates
        jsr     draw_perimeter_box
        inc     BOX_INDEX
        lda     BOX_INDEX
        cmpa    #92
        blo     rpr_box
        puls    a
        sta     BOX_INDEX
        rts

fri_stage_background
        jsr     draw_screen
        jsr     draw_all_gates
        jsr     draw_entities
        jsr     draw_hud
        jsr     draw_word_progress_hud
        jsr     draw_lives
        lbsr    enemy_render_impl
        ifeq    PERSISTENT_FB
        jsr     draw_player
        endc
        rts

        ifne    PERSISTENT_FB
; Conservative transitive overlap closure for the five moving actors.
; Restoring every owned old footprint avoids geometry bookkeeping and ensures
; no destination background is captured until every prior actor is absent.
actor_closure_restore
        tst     PLAYER_BG_VALID
        beq     acr_enemies
        ldd     PLAYER_FB
        pshs    d
        ldd     PLAYER_OLD_FB
        std     PLAYER_FB
        jsr     restore_player
        puls    d
        std     PLAYER_FB
        lda     #1
        sta     PLAYER_ERASED
acr_enemies
        ldx     #ENEMY_TABLE
        lda     #4
        sta     ENEMY_WORK
acr_enemy_loop
        lda     #4
        suba    ENEMY_WORK
        ldy     #roam_slot_masks
        ldb     a,y
        andb    ENEMY_OLD_VALID
        beq     acr_enemy_next
        lbsr    roam_old_slot
        ldd     ,u
        pshs    x
        tfr     d,x
        lbsr    roam_bg_address
        lbsr    roam_copy_bg_to_fb
        puls    x
acr_enemy_next
        leax    RECORD_SIZE,x
        dec     ENEMY_WORK
        bne     acr_enemy_loop
        rts

; Capture every current roaming destination from actor-free BACK, then draw
; enemies and the player presentation in stable painter order.
actor_closure_draw
        ldx     #ENEMY_TABLE
        lda     #4
        sta     ENEMY_WORK
acd_save_loop
        tst     ,x
        beq     acd_save_next
        tst     6,x
        bne     acd_save_actor
        lda     5,x
        cmpa    #10
        bhi     acd_save_next
acd_save_actor
        pshs    x
        lbsr    roam_update_background
        puls    x
        lda     #1
        sta     6,x
acd_save_next
        leax    RECORD_SIZE,x
        dec     ENEMY_WORK
        bne     acd_save_loop

        ldx     #ENEMY_TABLE
        lda     #4
        sta     ENEMY_WORK
acd_draw_loop
        tst     ,x
        beq     acd_draw_next
        tst     6,x
        beq     acd_draw_next
        ldb     7,x
        pshs    x
        ldx     1,x
        lbsr    draw_enemy_fb
        puls    x
acd_draw_next
        leax    RECORD_SIZE,x
        dec     ENEMY_WORK
        bne     acd_draw_loop

        tst     PICKUP_TIMER
        beq     acd_death
acd_popup
        jsr     save_player
        jsr     draw_score_popup
        rts
acd_death
        lda     RENDER_FLAGS
        bita    #RF_DEATH
        beq     acd_player
        lda     DEATH_STATE
        beq     acd_player
        cmpa    #3
        bhs     acd_done
        lda     DEATH_FRAME
        cmpa    #$FF
        beq     acd_done
        jsr     draw_death_frame
        rts
acd_player
        lda     DEATH_STATE
        bne     acd_done
        lda     RENDER_FLAGS
        bita    #RF_PLAYER|RF_STAGE
        bne     acd_draw_player
        tst     PLAYER_ERASED
        beq     acd_done
acd_draw_player
        jsr     draw_player
acd_done
        rts
        endc

; Phase-3 ownership bootstrap. While display output is still blanked, duplicate
; the complete A image into physical pages $2C-$2F, then clone the current
; restoration state and actor metadata. Display commits remain disabled.
framebuffer_init_impl
        clr     FB_FRONT_ID
        lda     #1
        sta     FB_BACK_ID
        clr     FB_RENDER_PENDING
        clr     FB_COMMIT_SEQ
        clr     FB_COMMIT_SEQ+1
        clr     FB_SIM_SEQ
        clr     FB_SIM_SEQ+1
        clr     FB_MISSED_COMMIT
        clr     FB_MISSED_COMMIT+1
        clr     FB_RENDER_ACTIVE
        clr     FB_WRITE_FRONT_FAULT

        lda     #FB_B_PAGE0
        pshs    a
        ldx     #$2000
fbi_page
        lda     ,s
        sta     GIME_PAR5
        ldu     #$A000
        ldy     #4096
fbi_page_word
        ldd     ,x++
        std     ,u++
        leay    -1,y
        bne     fbi_page_word
        inc     ,s
        cmpx    #$A000
        blo     fbi_page
        leas    1,s
        lda     #$34
        sta     GIME_PAR5

        ldx     #PLAYER_BG
        ldu     #PLAYER_BG_B
        ldy     #64
fbi_player_bg
        ldd     ,x++
        std     ,u++
        leay    -1,y
        bne     fbi_player_bg
        ldx     #ENEMY_BG_BASE
        ldu     #ENEMY_BG_B
        ldy     #256
fbi_enemy_bg
        ldd     ,x++
        std     ,u++
        leay    -1,y
        bne     fbi_enemy_bg

        ldx     #FB_META_A
        ldy     #256
        clra
        clrb
fbi_clear_meta
        std     ,x++
        leay    -1,y
        bne     fbi_clear_meta
        lbsr    framebuffer_capture_a
        ldx     #FB_META_A
        ldu     #FB_META_B
        ldy     #128
fbi_copy_meta
        ldd     ,x++
        std     ,u++
        leay    -1,y
        bne     fbi_copy_meta
        lda     #1
        sta     FB_INIT_STATE
        rts

; Map and hydrate the non-scanned owner before any framebuffer write. Actor
; save-under ownership is buffer-local; the logical records remain untouched.
framebuffer_prepare_back
        tst     FB_INIT_STATE
        beq     fbp_ok
        lda     FB_BACK_ID
        cmpa    FB_FRONT_ID
        bne     fbp_owned
        inc     FB_WRITE_FRONT_FAULT
        orcc    #$01
        rts
fbp_owned
        lda     #1
        sta     FB_RENDER_ACTIVE
        lbsr    gate_map_live
        lbsr    framebuffer_back_meta
        lda     FBM_PLAYER_VALID,u
        sta     PLAYER_BG_VALID
        ldd     FBM_PLAYER_FB,u
        std     PLAYER_OLD_FB
        ldx     #PLAYER_BG
        tst     FB_BACK_ID
        beq     fbp_enemies
        ldx     #PLAYER_BG_B
fbp_enemies
        stx     PLAYER_BG_PTR
        leau    FBM_ENEMIES,u
        ldy     #ENEMY_OLD_FB
        clr     ENEMY_OLD_VALID
        ldx     #roam_slot_masks
        clr     ENEMY_WORK
fbp_enemy
        ldd     1,u
        std     ,y++
        tst     6,u
        beq     fbp_enemy_next
        ldb     ENEMY_WORK
        lda     b,x
        ora     ENEMY_OLD_VALID
        sta     ENEMY_OLD_VALID
fbp_enemy_next
        leau    RECORD_SIZE,u
        inc     ENEMY_WORK
        lda     ENEMY_WORK
        cmpa    #4
        blo     fbp_enemy
        leau    4,u
        ldd     ,u
        std     ENEMY_BG_RING
        ldd     2,u
        std     ENEMY_BG_RING+2
fbp_ok
        andcc   #$FE
        rts

; Capture buffer-local ownership, then publish readiness as one IRQ-masked
; transaction. PLAYER_BG_PTR continues to identify the rendered owner.
framebuffer_finish_back
        tst     FB_INIT_STATE
        beq     fbf_done
        lbsr    framebuffer_capture_back
fbf_ready
        orcc    #$10
        clr     FB_RENDER_ACTIVE
        lda     #1
        sta     FB_RENDER_PENDING
        andcc   #$EF
fbf_done
        rts

framebuffer_back_meta
        ldu     #FB_META_A
        tst     FB_BACK_ID
        beq     fbm_done
        ldu     #FB_META_B
fbm_done
        rts

framebuffer_capture_back
        lbsr    framebuffer_back_meta
        lda     #FBM_VALID
        sta     FBM_STATE,u
        clr     FBM_DAMAGE,u
        lda     PLAYER_BG_VALID
        sta     FBM_PLAYER_VALID,u
        clr     FBM_PLAYER_RESERVED,u
        ldd     PLAYER_FB
        std     FBM_PLAYER_FB,u
        leau    FBM_ENEMIES,u
        ldx     #ENEMY_TABLE
        ldy     #16
fbcb_enemy
        ldd     ,x++
        std     ,u++
        leay    -1,y
        bne     fbcb_enemy
        clra
        clrb
        std     ,u
        std     2,u
        ldd     ENEMY_BG_RING
        std     4,u
        ldd     ENEMY_BG_RING+2
        std     6,u
        rts

; Vbord is the only display-owner commit point. The handler touches only
; always-mapped direct-page state and the display offset register; PAR5 state
; is therefore irrelevant even when sparse decoding is interrupted.
framebuffer_irq_impl
        lda     GIME_IRQEN
        inc     FRAMES+1
        bne     fbiq_ready
        inc     FRAMES
fbiq_ready
        tst     FB_RENDER_PENDING
        beq     fbiq_missed
        lda     #$C0
        tst     FB_BACK_ID
        beq     fbiq_publish
        lda     #$B0
fbiq_publish
        sta     GIME_VOFF1
        lda     FB_FRONT_ID
        ldb     FB_BACK_ID
        stb     FB_FRONT_ID
        sta     FB_BACK_ID
        clr     FB_RENDER_PENDING
        inc     FB_COMMIT_SEQ+1
        bne     fbiq_sim
        inc     FB_COMMIT_SEQ
fbiq_sim
        inc     FB_SIM_SEQ+1
        bne     fbiq_done
        inc     FB_SIM_SEQ
fbiq_done
        rts
fbiq_missed
        tst     FB_RENDER_ACTIVE
        beq     fbiq_done
        inc     FB_MISSED_COMMIT+1
        bne     fbiq_done
        inc     FB_MISSED_COMMIT
        rts

framebuffer_capture_a
        lda     #FBM_VALID
        sta     FB_META_A+FBM_STATE
        clr     FB_META_A+FBM_DAMAGE
        lda     PLAYER_BG_VALID
        sta     FB_META_A+FBM_PLAYER_VALID
        clr     FB_META_A+FBM_PLAYER_RESERVED
        ldd     PLAYER_FB
        std     FB_META_A+FBM_PLAYER_FB
        ldx     #ENEMY_TABLE
        ldu     #FB_META_A+FBM_ENEMIES
        ldy     #16
fbca_enemy
        ldd     ,x++
        std     ,u++
        leay    -1,y
        bne     fbca_enemy
        clra
        clrb
        std     FB_META_A+FBM_ENEMY_RESERVED
        std     FB_META_A+FBM_ENEMY_RESERVED+2
        ldd     ENEMY_BG_RING
        std     FB_META_A+FBM_ENEMY_RINGS
        ldd     ENEMY_BG_RING+2
        std     FB_META_A+FBM_ENEMY_RINGS+2
        rts

        ifeq    PERSISTENT_FB
framebuffer_begin_fallback
        tst     FB_INIT_STATE
        beq     fbb_done
        lda     #FBM_FULL_REBUILD
        sta     FB_META_B+FBM_STATE
fbb_done
        rts

framebuffer_finish_fallback
        tst     FB_INIT_STATE
        beq     fbff_done
        lbsr    framebuffer_capture_a
fbff_done
        rts
        endc

enemy_collect_impl
        lda     VEG_STATE
        cmpa    #1
        bne     ec_done
        lda     PLAYER_CELL_X
        cmpa    #11
        blo     ec_done
        cmpa    #13
        bhi     ec_done
        lda     PLAYER_CELL_Y
        cmpa    #11
        blo     ec_done
        cmpa    #13
        bhi     ec_done
        lda     #2
        sta     VEG_STATE
        inc     ENEMY_NEST_DIRTY
        lda     ENEMY_RENDER_FLAGS
        ora     #ERF_DIRTY|ERF_NEST
        sta     ENEMY_RENDER_FLAGS
        ldd     #300
        std     FREEZE_TIMER
        ; Level-1 cucumber placeholder score: 1,000 points.
        lda     SCORE_BCD+1
        adda    #$10
        daa
        sta     SCORE_BCD+1
        bcc     ec_score_done
        lda     SCORE_BCD
        adca    #0
        daa
        sta     SCORE_BCD
ec_score_done
        ldd     SCORE_BCD
        std     HIGH_BCD
        lda     SCORE_BCD+2
        sta     HIGH_BCD+2
        lda     RENDER_FLAGS
        ora     #$02
        sta     RENDER_FLAGS
ec_done
        rts

; Choose a pseudo-random legal direction at every aligned maze decision.
; Avoid immediate reversal whenever another corridor exists. Gate-owned cells
; are legal only when the current bar orientation exposes a parallel passage.
enemy_choose_direction
        stx     ENEMY_PTR
        lda     7,x
        eora    #2
        sta     ENEMY_REVERSE
        lda     RNG_STATE+1
        adda    ENEMY_WORK
        anda    #3
        sta     ENEMY_CANDIDATE
        lda     #4
        sta     GATE_COPY_COUNT
ecd_scan
        lda     ENEMY_CANDIDATE
        cmpa    ENEMY_REVERSE
        beq     ecd_next
        lbsr    enemy_direction_legal
        bcs     ecd_choose
ecd_next
        inc     ENEMY_CANDIDATE
        lda     ENEMY_CANDIDATE
        anda    #3
        sta     ENEMY_CANDIDATE
        dec     GATE_COPY_COUNT
        bne     ecd_scan
        lda     ENEMY_REVERSE
        sta     ENEMY_CANDIDATE
        lbsr    enemy_direction_legal
        bcc     ecd_blocked
ecd_choose
        ldx     ENEMY_PTR
        lda     ENEMY_CANDIDATE
        sta     7,x
        rts
ecd_blocked
        ldx     ENEMY_PTR
        lda     #DIR_NONE
        sta     7,x
        rts

enemy_direction_legal
        ldx     ENEMY_PTR
        lda     5,x
        cmpa    #11
        blo     edl_slow         ; retain the den-entrance exception
        ldb     #24
        mul
        addb    4,x
        adca    #0
        ldy     #maze_nav
        leay    d,y
        lda     ,y
        bita    #$10
        bne     edl_slow         ; dynamic gate topology needs the full test
        ldy     #enemy_exit_masks
        ldb     ENEMY_CANDIDATE
        anda    b,y
        lbeq    edl_clear
        orcc    #$01
        rts
edl_slow
        lda     4,x
        sta     ENTITY_X
        lda     5,x
        sta     ENTITY_Y
        ldb     ENEMY_CANDIDATE
        beq     edl_north
        cmpb    #1
        beq     edl_east
        cmpb    #2
        beq     edl_south
        dec     ENTITY_X
        bra     edl_bounds
edl_north
        dec     ENTITY_Y
        bra     edl_bounds
edl_east
        inc     ENTITY_X
        bra     edl_bounds
edl_south
        inc     ENTITY_Y
edl_bounds
        lda     ENTITY_X
        cmpa    #24
        lbhs    edl_clear
        lda     ENTITY_Y
        cmpa    #24
        lbhs    edl_clear
        ldx     ENEMY_PTR
        lda     5,x
        cmpa    #10
        bhi     edl_offset
        lda     ENTITY_X
        cmpa    #12
        bne     edl_offset
        lda     ENTITY_Y
        cmpa    #11
        lbeq    edl_clear       ; do not re-enter the den from cell (12,10)
edl_offset
        lda     ENTITY_Y
        ldb     #24
        mul
        addb    ENTITY_X
        adca    #0
        ldy     #maze_gate_owner
        leay    d,y
        lda     ,y
        bne     edl_gate
        leay    maze_nav-maze_gate_owner,y
        ldb     ,y
        ldx     #enemy_entry_masks
        lda     ENEMY_CANDIDATE
        andb    a,x
        beq     edl_clear
        orcc    #$01
        rts
edl_gate
        deca
        sta     GATE_WORK_ID
        ldb     #3
        mul
        ldy     #maze_gates
        leay    d,y
        lda     ,y
        sta     GATE_X
        lda     1,y
        sta     GATE_Y
        ldy     #GATE_STATE
        ldb     GATE_WORK_ID
        lda     b,y
        bita    #1
        bne     edl_vertical_gate
        lda     ENTITY_X
        cmpa    GATE_X
        bne     edl_clear
        lda     ENTITY_Y
        suba    GATE_Y
        beq     edl_clear
        cmpa    #1
        beq     edl_horizontal_dir
        cmpa    #-1
        bne     edl_clear
edl_horizontal_dir
        lda     ENEMY_CANDIDATE
        cmpa    #1
        beq     edl_set
        cmpa    #3
        beq     edl_set
        bra     edl_clear
edl_vertical_gate
        lda     ENTITY_Y
        cmpa    GATE_Y
        bne     edl_clear
        lda     ENTITY_X
        suba    GATE_X
        beq     edl_clear
        cmpa    #1
        beq     edl_vertical_dir
        cmpa    #-1
        bne     edl_clear
edl_vertical_dir
        lda     ENEMY_CANDIDATE
        beq     edl_set
        cmpa    #2
        bne     edl_clear
edl_set
        orcc    #$01
        rts
edl_clear
        andcc   #$FE
        rts

enemy_entry_masks
        fcb     $04,$08,$01,$02
enemy_exit_masks
        fcb     $01,$02,$04,$08

; Compare semantic centres. Adjacent eight-pixel cells still overlap because
; both actors have 16-by-16 footprints.
enemy_player_contact
        lda     PLAYER_CELL_X
        suba    4,x
        bpl     epc_x_positive
        nega
epc_x_positive
        cmpa    #1
        bhi     epc_clear
        lda     PLAYER_CELL_Y
        suba    5,x
        bpl     epc_y_positive
        nega
epc_y_positive
        cmpa    #1
        bhi     epc_clear
        orcc    #$01
        rts
epc_clear
        andcc   #$FE
        rts

; X points at the active record. Only the matching skull record is removed.
enemy_skull_test
        stx     ENEMY_PTR
        ldu     #ENTITY_TABLE
        lda     ENTITY_COUNT
        beq     est_done
        sta     ENEMY_WORK
est_loop
        lda     2,u
        cmpa    #ENTITY_SKULL
        beq     est_skull
        tsta
        beq     est_next         ; cleared skulls remain inside the prefix
        rts                      ; randomized skull records are always first
est_skull
        lda     ,u
        ldx     ENEMY_PTR
        cmpa    4,x
        bne     est_next
        lda     1,u
        cmpa    5,x
        bne     est_next
        clr     2,u
        lda     ,u
        sta     ENTITY_X
        lda     1,u
        sta     ENTITY_Y
        sta     RENDER_ZONE_Y
        ldx     ENEMY_PTR
        clr     ,x
        clr     6,x
        dec     ENEMY_ACTIVE
        clr     VEG_STATE
        inc     ENEMY_NEST_DIRTY
        lda     RENDER_FLAGS
        ora     #RF_ENTITIES
        sta     RENDER_FLAGS
        lda     ENEMY_RENDER_FLAGS
        ora     #ERF_DIRTY|ERF_ZONE_REFRESH|ERF_NEST
        sta     ENEMY_RENDER_FLAGS
        rts
est_next
        leau    4,u
        dec     ENEMY_WORK
        bne     est_loop
est_done
        rts

; Snapshot framebuffer ownership before gameplay mutates any enemy record.
; This routine writes state only; the renderer consumes the snapshot later.
roam_snapshot_old
        ldu     #ENEMY_OLD_FB
        clra
        clrb
        std     ,u
        std     2,u
        std     4,u
        std     6,u
        clr     ENEMY_OLD_VALID
        ldx     #ENEMY_TABLE
        lda     #4
        sta     ENEMY_WORK
rsn_loop
        tst     ,x
        beq     rsn_next
        tst     6,x
        bne     rsn_actor
        lda     5,x
        cmpa    #11
        bhi     rsn_next
rsn_actor
        lbsr    roam_old_slot
        ldd     1,x
        std     ,u
        tst     6,x
        beq     rsn_next
        lda     #4
        suba    ENEMY_WORK
        ldy     #roam_slot_masks
        ldb     a,y
        orb     ENEMY_OLD_VALID
        stb     ENEMY_OLD_VALID
rsn_next
        leax    RECORD_SIZE,x
        dec     ENEMY_WORK
        bne     rsn_loop
        rts

roam_slot_masks
        fcb     1,2,4,8

; Import the final old/new unions after gameplay mutation, then remove every
; owned old actor in shadow before capturing any destination background.
        ifeq    PERSISTENT_FB
roam_prepare_shadow
        clr     ENEMY_ROAMING
        ldx     #ENEMY_TABLE
        lda     #4
        sta     ENEMY_WORK
rps_copy_loop
        lbsr    roam_old_slot
        ldd     ,u
        beq     rps_copy_next
        inc     ENEMY_ROAMING
        tst     ,x
        beq     rps_old_only
        lbsr    roam_set_final_union
        bra     rps_copy_region
rps_old_only
        std     GATE_RECT_FB
        lda     #8
        sta     GATE_RECT_WIDTH
        lda     #16
        sta     GATE_RECT_ROWS
rps_copy_region
        pshs    x
        lbsr    gate_region_to_shadow
        puls    x
rps_copy_next
        leax    RECORD_SIZE,x
        dec     ENEMY_WORK
        bne     rps_copy_loop
        tst     ENEMY_ROAMING
        beq     rps_done
        lbsr    gate_map_shadow
        ; A transition seeded from the freshly rebuilt nest can overlap an
        ; established roaming actor. Restore every valid old actor once so
        ; all destination saves observe actor-free pixels.
        ldx     #ENEMY_TABLE
        lda     #4
        sta     ENEMY_WORK
rps_restore_loop
        lda     #4
        suba    ENEMY_WORK
        ldy     #roam_slot_masks
        ldb     a,y
        andb    ENEMY_OLD_VALID
        beq     rps_restore_next
        lbsr    roam_old_slot
        ldd     ,u
        pshs    x
        tfr     d,x
        lbsr    roam_bg_address
        lbsr    roam_copy_bg_to_fb
        puls    x
rps_restore_next
        leax    RECORD_SIZE,x
        dec     ENEMY_WORK
        bne     rps_restore_loop
        lbsr    gate_map_live
rps_done
        rts

; After the nest has been republished, stage any newly transitioned enemy,
; save every clean destination, draw every actor, then publish final unions.
roam_finish_shadow
        tst     ENEMY_ROAMING
        lbeq    rfs_done
        ldx     #ENEMY_TABLE
        lda     #4
        sta     ENEMY_WORK
rfs_seed_loop
        tst     ,x
        beq     rfs_seed_next
        lda     5,x
        cmpa    #10
        bhi     rfs_seed_next
        tst     6,x
        bne     rfs_seed_next
        lbsr    roam_set_final_union
        pshs    x
        lbsr    gate_region_to_shadow
        puls    x
rfs_seed_next
        leax    RECORD_SIZE,x
        dec     ENEMY_WORK
        bne     rfs_seed_loop

        lbsr    gate_map_shadow
        ldx     #ENEMY_TABLE
        lda     #4
        sta     ENEMY_WORK
rfs_save_loop
        tst     ,x
        beq     rfs_save_next
        tst     6,x
        bne     rfs_save_actor
        lda     5,x
        cmpa    #10
        bhi     rfs_save_next
rfs_save_actor
        pshs    x
        ldx     1,x
        lbsr    roam_bg_address
        lbsr    roam_copy_fb_to_bg
        puls    x
        lda     #1
        sta     6,x
rfs_save_next
        leax    RECORD_SIZE,x
        dec     ENEMY_WORK
        bne     rfs_save_loop

        ldx     #ENEMY_TABLE
        lda     #4
        sta     ENEMY_WORK
rfs_draw_loop
        tst     ,x
        beq     rfs_draw_next
        tst     6,x
        beq     rfs_draw_next
        ldb     7,x
        pshs    x
        ldx     1,x
        lbsr    draw_enemy_fb
        puls    x
rfs_draw_next
        leax    RECORD_SIZE,x
        dec     ENEMY_WORK
        bne     rfs_draw_loop
        lbsr    gate_map_live

        ldx     #ENEMY_TABLE
        lda     #4
        sta     ENEMY_WORK
rfs_publish_loop
        lbsr    roam_old_slot
        ldd     ,u
        beq     rfs_publish_next
        lbsr    roam_set_final_union
        pshs    x
        lbsr    gate_region_from_shadow
        puls    x
rfs_publish_next
        leax    RECORD_SIZE,x
        dec     ENEMY_WORK
        bne     rfs_publish_loop
rfs_done
        rts

; Restore and publish every roaming footprint before lifecycle reset clears
; the records. Nest occupants are removed by the normal nest composition.
roam_despawn_all
        lbsr    roam_prepare_shadow
        tst     ENEMY_ROAMING
        beq     rda_done
        ldx     #ENEMY_TABLE
        lda     #4
        sta     ENEMY_WORK
rda_loop
        lbsr    roam_old_slot
        ldd     ,u
        beq     rda_next
        std     GATE_RECT_FB
        lda     #8
        sta     GATE_RECT_WIDTH
        lda     #16
        sta     GATE_RECT_ROWS
        pshs    x
        lbsr    gate_region_from_shadow
        puls    x
rda_next
        leax    RECORD_SIZE,x
        dec     ENEMY_WORK
        bne     rda_loop
rda_done
        rts
        endc

; U returns the old-pointer slot or this record's 128-byte background buffer.
roam_old_slot
        lda     #4
        suba    ENEMY_WORK
        lsla
        ldu     #ENEMY_OLD_FB
        leau    a,u
        rts

roam_bg_address
        lda     #4
        suba    ENEMY_WORK
        ldb     #128
        mul
        tst     FB_BACK_ID
        bne     rba_buffer_b
        addd    #ENEMY_BG_BASE
        bra     rba_done
rba_buffer_b
        addd    #ENEMY_BG_B
rba_done
        tfr     d,u
        rts

        ifne    PERSISTENT_FB
; U returns this actor's packed row/column ring phase.
roam_ring_slot
        lda     #4
        suba    ENEMY_WORK
        ldu     #ENEMY_BG_RING
        leau    a,u
        rts

; Retain an unchanged clean destination, rotate/capture a recognized exposed
; strip, or normalize with a full capture for every conservative fallback.
; Input: X = current enemy record.
roam_update_background
        lda     #4
        suba    ENEMY_WORK
        ldy     #roam_slot_masks
        ldb     a,y
        bitb    ENEMY_CAPTURE_DIRTY
        bne     rub_full
        andb    ENEMY_OLD_VALID
        beq     rub_full
        lbsr    roam_old_slot
        ldd     1,x
        subd    ,u
        beq     rub_done
        cmpd    #1
        beq     rub_right
        cmpd    #-1
        beq     rub_left
        cmpd    #320
        lbeq    rub_down
        cmpd    #-320
        lbeq    rub_up
rub_full
        pshs    x
        lbsr    roam_ring_slot
        clr     ,u
        puls    x
        pshs    x
        ldx     1,x
        lbsr    roam_bg_address
        lbsr    roam_copy_fb_to_bg
        puls    x
rub_done
        rts
rub_right
        lda     #7
        bra     rub_horizontal
rub_left
        clra
rub_horizontal
        sta     RING_ROW        ; exposed framebuffer column
        pshs    x
        lbsr    roam_ring_slot
        lda     ,u
        sta     RING_PHASE
        anda    #7
        sta     GATE_COPY_COUNT ; old column phase
        lda     RING_PHASE
        anda    #$F0
        sta     RING_PHASE
        ldb     GATE_COPY_COUNT
        tst     RING_ROW
        beq     rub_shift_left
        incb
        bra     rub_store_column
rub_shift_left
        decb
rub_store_column
        andb    #7
        orb     RING_PHASE
        stb     ,u
        tst     RING_ROW
        bne     rub_right_slot
        andb    #7
        stb     GATE_COPY_COUNT ; new phase owns the exposed left column
rub_right_slot
        puls    x
        pshs    x
        ldx     1,x
        tst     RING_ROW
        beq     rub_horizontal_fb
        leax    7,x
rub_horizontal_fb
        lbsr    roam_bg_address
        ldb     GATE_COPY_COUNT
        leau    b,u
        lda     RING_PHASE
        lsra
        lsra
        lsra
        lsra
        sta     RING_ROW
        lsla
        lsla
        lsla
        leau    a,u
        ldb     #16
        subb    RING_ROW
rub_column_first
        lda     ,x
        sta     ,u
        leax    160,x
        leau    8,u
        decb
        bne     rub_column_first
        ldb     RING_ROW
        beq     rub_column_done
        leau    -128,u
rub_column_second
        lda     ,x
        sta     ,u
        leax    160,x
        leau    8,u
        decb
        bne     rub_column_second
rub_column_done
        puls    x
        rts

rub_down
        lda     #14
        bra     rub_vertical
rub_up
        clra
rub_vertical
        sta     GATE_COPY_ROWS  ; first exposed framebuffer row
        pshs    x
        lbsr    roam_ring_slot
        lda     ,u
        sta     RING_PHASE
        anda    #$F0
        lsra
        lsra
        lsra
        lsra
        sta     RING_ROW
        lda     RING_PHASE
        anda    #7
        sta     RING_PHASE
        tst     GATE_COPY_ROWS
        beq     rub_shift_up
        lda     RING_ROW        ; down overwrites the old top rows
        sta     GATE_COPY_COUNT
        adda    #2              ; new logical row zero maps old logical row two
        bra     rub_store_row
rub_shift_up
        lda     RING_ROW
        suba    #2
        anda    #15
        sta     GATE_COPY_COUNT ; up overwrites the old bottom rows
rub_store_row
        anda    #15
        sta     RING_ROW        ; new row phase and first physical target
        lsla
        lsla
        lsla
        lsla
        ora     RING_PHASE
        sta     ,u
        lda     GATE_COPY_COUNT
        sta     RING_ROW
        puls    x
        pshs    x
        ldx     1,x
        tst     GATE_COPY_ROWS
        beq     rub_vertical_fb
        leax    2240,x
rub_vertical_fb
        lbsr    roam_bg_address
        stu     RING_BASE
        lda     #2
        sta     GATE_COPY_ROWS
rub_row_loop
        lda     RING_ROW
        ldb     #8
        mul
        addd    RING_BASE
        tfr     d,u
        lbsr    roam_capture_ring_row
        leax    152,x
        inc     RING_ROW
        lda     RING_ROW
        anda    #15
        sta     RING_ROW
        dec     GATE_COPY_ROWS
        bne     rub_row_loop
        puls    x
        rts

; Capture one logical framebuffer row into a column-rotated physical row.
roam_capture_ring_row
        ldb     RING_PHASE
        bne     rcrr_rotated
        ; The dominant phase-zero row is contiguous in both source and ring.
        ; Pull four bytes per instruction and leave X at the next FB byte.
        exg     x,u
        pulu    d,y
        std     ,x++
        sty     ,x++
        pulu    d,y
        std     ,x++
        sty     ,x++
        tfr     u,x
        rts
rcrr_rotated
        lda     #8
        sta     GATE_COPY_COUNT
rcrr_byte
        lda     ,x+
        sta     b,u
        incb
        andb    #7
        dec     GATE_COPY_COUNT
        bne     rcrr_byte
        rts
        endc

        ifeq    PERSISTENT_FB
roam_set_prepare_union
        ldd     1,x
        std     GATE_RECT_FB
        lda     #8
        sta     GATE_RECT_WIDTH
        lda     #16
        sta     GATE_RECT_ROWS
        tst     ENEMY_MOVE
        beq     rspu_done
        lda     7,x
        beq     rspu_north
        cmpa    #1
        beq     rspu_east
        cmpa    #2
        beq     rspu_south
        ldd     GATE_RECT_FB
        subd    #1
        std     GATE_RECT_FB
rspu_east
        inc     GATE_RECT_WIDTH
        rts
rspu_north
        ldd     GATE_RECT_FB
        subd    #320
        std     GATE_RECT_FB
rspu_south
        lda     #18
        sta     GATE_RECT_ROWS
rspu_done
        rts

roam_set_final_union
        lbsr    roam_old_slot
        ldd     ,u
        std     GATE_RECT_FB
        lda     #8
        sta     GATE_RECT_WIDTH
        lda     #16
        sta     GATE_RECT_ROWS
        ldd     1,x
        subd    ,u
        beq     rsfu_done
        cmpd    #1
        beq     rsfu_horizontal
        cmpd    #-1
        beq     rsfu_west
        cmpd    #320
        beq     rsfu_vertical
        ldd     1,x
        std     GATE_RECT_FB
rsfu_vertical
        lda     #18
        sta     GATE_RECT_ROWS
        rts
rsfu_west
        ldd     1,x
        std     GATE_RECT_FB
rsfu_horizontal
        inc     GATE_RECT_WIDTH
rsfu_done
        rts
        endc

roam_copy_bg_to_fb
        ifne    PERSISTENT_FB
        stu     RING_BASE
        lbsr    roam_ring_slot
        lda     ,u
        sta     RING_PHASE
        bita    #$F0
        lbne    rcbtf_ring_setup
        lda     #16
        sta     GATE_COPY_ROWS
        lda     RING_PHASE
        anda    #7
        lsla
        ldu     RING_BASE
        ldy     #rcbtf_fast_table
        ldy     a,y
        jmp     ,y

rcbtf_fast_table
        fdb     rcbtf_phase0_rows,rcbtf_phase1_rows
        fdb     rcbtf_phase2_rows,rcbtf_phase3_rows
        fdb     rcbtf_phase4_rows,rcbtf_phase5_rows
        fdb     rcbtf_phase6_rows,rcbtf_phase7_rows

rcbtf_phase0
rcbtf_phase0_rows
rcbtf_phase0_row
        pulu    d,y
        std     ,x++
        sty     ,x++
        pulu    d,y
        std     ,x++
        sty     ,x++
        leax    152,x
        dec     GATE_COPY_ROWS
        bne     rcbtf_phase0_row
        rts

rcbtf_phase1
rcbtf_phase1_rows
rcbtf_phase1_row
        ldd     1,u
        std     ,x++
        ldd     3,u
        std     ,x++
        ldd     5,u
        std     ,x++
        lda     7,u
        ldb     ,u
        std     ,x++
        leau    8,u
        leax    152,x
        dec     GATE_COPY_ROWS
        bne     rcbtf_phase1_row
        rts

rcbtf_phase2
rcbtf_phase2_rows
rcbtf_phase2_row
        ldd     2,u
        std     ,x++
        ldd     4,u
        std     ,x++
        ldd     6,u
        std     ,x++
        ldd     ,u
        std     ,x++
        leau    8,u
        leax    152,x
        dec     GATE_COPY_ROWS
        bne     rcbtf_phase2_row
        rts

rcbtf_phase3
rcbtf_phase3_rows
rcbtf_phase3_row
        ldd     3,u
        std     ,x++
        ldd     5,u
        std     ,x++
        lda     7,u
        ldb     ,u
        std     ,x++
        ldd     1,u
        std     ,x++
        leau    8,u
        leax    152,x
        dec     GATE_COPY_ROWS
        bne     rcbtf_phase3_row
        rts

rcbtf_phase4
rcbtf_phase4_rows
rcbtf_phase4_row
        ldd     4,u
        std     ,x++
        ldd     6,u
        std     ,x++
        ldd     ,u
        std     ,x++
        ldd     2,u
        std     ,x++
        leau    8,u
        leax    152,x
        dec     GATE_COPY_ROWS
        bne     rcbtf_phase4_row
        rts

rcbtf_phase5
rcbtf_phase5_rows
rcbtf_phase5_row
        ldd     5,u
        std     ,x++
        lda     7,u
        ldb     ,u
        std     ,x++
        ldd     1,u
        std     ,x++
        ldd     3,u
        std     ,x++
        leau    8,u
        leax    152,x
        dec     GATE_COPY_ROWS
        bne     rcbtf_phase5_row
        rts

rcbtf_phase6
rcbtf_phase6_rows
rcbtf_phase6_row
        ldd     6,u
        std     ,x++
        ldd     ,u
        std     ,x++
        ldd     2,u
        std     ,x++
        ldd     4,u
        std     ,x++
        leau    8,u
        leax    152,x
        dec     GATE_COPY_ROWS
        bne     rcbtf_phase6_row
        rts

rcbtf_phase7
rcbtf_phase7_rows
rcbtf_phase7_row
        lda     7,u
        ldb     ,u
        std     ,x++
        ldd     1,u
        std     ,x++
        ldd     3,u
        std     ,x++
        ldd     5,u
        std     ,x++
        leau    8,u
        leax    152,x
        dec     GATE_COPY_ROWS
        bne     rcbtf_phase7_row
        rts

rcbtf_ring_setup
        lda     RING_PHASE
        anda    #$F0
        lsra
        lsra
        lsra
        lsra
        sta     RING_ROW        ; first physical row
        ldb     #8
        mul
        addd    RING_BASE
        tfr     d,u
        lda     RING_PHASE
        anda    #7
        lsla
        ldy     #rcbtf_fast_table
        ldy     a,y
        sty     RING_BASE       ; selected column-phase row copier
        clra
        ldb     #16
        subb    RING_ROW
        stb     GATE_COPY_ROWS
        jsr     [RING_BASE]
        lda     RING_ROW
        beq     rcbtf_ring_done
        leau    -128,u
        tfr     a,b
        stb     GATE_COPY_ROWS
        jsr     [RING_BASE]
rcbtf_ring_done
        rts
        else
        ldy     #16
rcbtf_row
        ldd     ,u++
        std     ,x++
        ldd     ,u++
        std     ,x++
        ldd     ,u++
        std     ,x++
        ldd     ,u++
        std     ,x++
        leax    152,x
        leay    -1,y
        bne     rcbtf_row
        rts
        endc

roam_copy_fb_to_bg
        ldy     #16
rcftb_row
        ldd     ,x++
        std     ,u++
        ldd     ,x++
        std     ,u++
        ldd     ,x++
        std     ,u++
        ldd     ,x++
        std     ,u++
        leax    152,x
        leay    -1,y
        bne     rcftb_row
        rts

draw_enemy_fb
        lbsr    enemy_frame_number
        lbsr    sparse_enemy_stream
        lbsr    sparse_blit_fb
        rts

; Build the complete 16-by-32 nest layer in compact RAM, then publish only
; final pixels to the visible framebuffer. Intermediate restores are never
; visible, including when every active record overlaps.
compose_enemy_zone
        ldx     #ENEMY_ZONE_BG
        ldu     #ENEMY_ZONE_STAGE
        ldy     #128
cez_copy_bg
        ldd     ,x++
        std     ,u++
        leay    -1,y
        bne     cez_copy_bg

        ; Active actors first.
        ldu     #ENEMY_TABLE
        lda     #4
        sta     ENEMY_WORK
cez_active_loop
        tst     ,u
        beq     cez_active_next
        tst     6,u
        bne     cez_active_next
        lda     5,u
        suba    #10
        ldb     #8
        mul
        subb    3,u
        sbca    #0
        lslb
        rola
        lslb
        rola
        lslb
        rola
        addd    #ENEMY_ZONE_STAGE
        tfr     d,x
        ldb     7,u
        pshs    u
        lbsr    draw_enemy_stage
        puls    u
cez_active_next
        leau    RECORD_SIZE,u
        dec     ENEMY_WORK
        bne     cez_active_loop

        ; The vegetable replaces the dormant actor. Keep the nest empty after
        ; collection while all four enemies remain active.
        lda     VEG_STATE
        cmpa    #1
        beq     cez_vegetable
        cmpa    #2
        bne     cez_dormant
        lda     ENEMY_ACTIVE
        cmpa    #4
        beq     cez_commit
cez_dormant
        ldx     #ENEMY_ZONE_STAGE+128
        ldb     #0
        lbsr    draw_enemy_stage
        bra     cez_commit
cez_vegetable
        ldx     #ENEMY_ZONE_STAGE+128
        lbsr    draw_vegetable_stage
cez_commit
        ldx     #ENEMY_ZONE_STAGE
        ldu     #ENEMY_ZONE_FB
        ldy     #ENEMY_ZONE_ROWS
cez_commit_row
        ldd     ,x++
        std     ,u++
        ldd     ,x++
        std     ,u++
        ldd     ,x++
        std     ,u++
        ldd     ,x++
        std     ,u++
        leau    152,u
        leay    -1,y
        bne     cez_commit_row
        rts

; Animation-only nest damage may update the dormant rectangle directly in
; hidden BACK. Structural changes and nest-owned active overlap retain the
; complete 16-by-32 compositor above.
compose_enemy_animation
        lda     VEG_STATE
        bne     cea_done
        lda     ENEMY_ANIM
        ldb     #128
        mul
        addd    #ENEMY_NEST_CACHE
        tfr     d,x
        ldu     #ENEMY_FB
        ldy     #16
        lbra    cez_commit_row
cea_done
        rts

; Build the clean new player rectangle from the old save-under plus newly
; exposed edge pixels. Publish the complete new sprite before erasing only the
; old strips it no longer covers, so scanout never sees a player-free frame.
player_compose_impl
        ldx     PLAYER_BG_PTR
        ldu     #PLAYER_OLD_STAGE
        ldy     #64
pci_copy_old
        ldd     ,x++
        std     ,u++
        leay    -1,y
        bne     pci_copy_old
        ldd     PLAYER_FB
        subd    PLAYER_OLD_FB
        cmpd    #160
        bge     pci_down
        cmpd    #-160
        ble     pci_up
        stb     PLAYER_DX
        clr     PLAYER_DY
        bra     pci_build
pci_down
        subd    #320
        stb     PLAYER_DX
        lda     #2
        sta     PLAYER_DY
        bra     pci_build
pci_up
        addd    #320
        stb     PLAYER_DX
        lda     #-2
        sta     PLAYER_DY

pci_build
        ldx     PLAYER_FB
        ldy     #PLAYER_STAGE
        clr     PLAYER_ROW
pci_row
        lda     PLAYER_ROW
        adda    PLAYER_DY
        bmi     pci_visible_row
        cmpa    #16
        bhs     pci_visible_row
        ldb     #8
        mul
        ldu     #PLAYER_OLD_STAGE
        leau    d,u
        lda     PLAYER_DX
        beq     pci_old_full
        bmi     pci_old_left

        ; New rectangle is one byte right: old columns 1..7 plus exposed 7.
        ldd     1,u
        std     ,y++
        ldd     3,u
        std     ,y++
        ldd     5,u
        std     ,y++
        lda     7,u
        sta     ,y+
        lda     7,x
        sta     ,y+
        bra     pci_next_row
pci_old_left
        ; New rectangle is one byte left: exposed 0 plus old columns 0..6.
        lda     ,x
        sta     ,y+
        ldd     ,u
        std     ,y++
        ldd     2,u
        std     ,y++
        ldd     4,u
        std     ,y++
        lda     6,u
        sta     ,y+
        bra     pci_next_row
pci_old_full
        ldd     ,u
        std     ,y++
        ldd     2,u
        std     ,y++
        ldd     4,u
        std     ,y++
        ldd     6,u
        std     ,y++
        bra     pci_next_row
pci_visible_row
        ldd     ,x
        std     ,y++
        ldd     2,x
        std     ,y++
        ldd     4,x
        std     ,y++
        ldd     6,x
        std     ,y++
pci_next_row
        leax    160,x
        inc     PLAYER_ROW
        lda     PLAYER_ROW
        cmpa    #16
        blo     pci_row

        ; Preserve the clean result before overlaying the selected frame.
        ldx     #PLAYER_STAGE
        ldu     PLAYER_BG_PTR
        ldy     #64
pci_save_loop
        ldd     ,x++
        std     ,u++
        leay    -1,y
        bne     pci_save_loop
        lda     #1
        sta     PLAYER_BG_VALID

        lda     PLAYER_FACE
        lsla
        lsla
        adda    PLAYER_ANIM
        lbsr    sparse_player_stream
        ldx     #PLAYER_STAGE
        lbsr    sparse_blit_stage

        ; Commit the final new rectangle before removing old-only strips.
        ldx     #PLAYER_STAGE
        ldu     PLAYER_FB
        lda     #16
        sta     PLAYER_ROW
pci_commit_row
        ldd     ,x++
        std     ,u++
        ldd     ,x++
        std     ,u++
        ldd     ,x++
        std     ,u++
        ldd     ,x++
        std     ,u++
        leau    152,u
        dec     PLAYER_ROW
        bne     pci_commit_row

        lda     PLAYER_DY
        beq     pci_horizontal_strip
        bmi     pci_restore_bottom
        ldx     PLAYER_OLD_FB
        ldu     #PLAYER_OLD_STAGE
        lbsr    copy_two_fb_rows
        bra     pci_horizontal_strip
pci_restore_bottom
        ldx     PLAYER_OLD_FB
        leax    2240,x
        ldu     #PLAYER_OLD_STAGE+112
        lbsr    copy_two_fb_rows

pci_horizontal_strip
        lda     PLAYER_DX
        beq     pci_done
        ldx     PLAYER_OLD_FB
        ldu     #PLAYER_OLD_STAGE
        ldb     #16
        tsta
        bmi     pci_restore_right
pci_restore_left_loop
        lda     ,u
        sta     ,x
        leax    160,x
        leau    8,u
        decb
        bne     pci_restore_left_loop
        bra     pci_done
pci_restore_right
        lda     7,u
        sta     7,x
        leax    160,x
        leau    8,u
        decb
        bne     pci_restore_right
pci_done
        rts

copy_two_fb_rows
        ldy     #2
ctfr_row
        ldd     ,u++
        std     ,x++
        ldd     ,u++
        std     ,x++
        ldd     ,u++
        std     ,x++
        ldd     ,u++
        std     ,x++
        leax    152,x
        leay    -1,y
        bne     ctfr_row
        rts

; Render a gate transition against hidden physical framebuffer pages $2C-$2F.
; The GIME continues scanning live pages $30-$33. Only the exact gate union and
; player footprint are copied in and published; all resident drawing code runs
; unchanged through the temporary PAR1-PAR4 mapping.
gate_compose_impl
        lda     RENDER_GATE_ID
        beq     gci_done
        ifne    PERSISTENT_FB
        tst     GATE_COMPOSE_MODE
        bne     gci_final
        jsr     draw_gate_transition
        bra     gci_mark_overlap
gci_final
        jsr     restore_gate_diagonal_dots
        jsr     draw_gate_transition
gci_mark_overlap
        jsr     mark_gate_enemy_overlap
        else
        deca
        sta     GATE_WORK_ID
        sta     GATE_ID
        lbsr    gate_compute_region
        lbsr    gate_region_to_shadow
        lbsr    gate_set_player_region
        lbsr    gate_region_to_shadow
        lbsr    gate_map_shadow
        jsr     gate_render_hidden
        lbsr    gate_map_live
        lda     GATE_WORK_ID
        sta     GATE_ID
        lbsr    gate_compute_region
        lbsr    gate_region_from_shadow
        lbsr    gate_set_player_region
        lbsr    gate_region_from_shadow
        endc
gci_done
        lda     #$34
        sta     GIME_PAR5
        rts

        ifeq    PERSISTENT_FB
gate_compute_region
        lda     GATE_WORK_ID
        ldb     #3
        mul
        ldx     #maze_gates
        leax    d,x
        lda     ,x
        sta     GATE_X
        suba    #2
        sta     GATE_START_X
        lda     GATE_X
        inca
        sta     GATE_END_X
        lda     1,x
        sta     GATE_Y
        suba    #2
        sta     GATE_START_Y
        lda     GATE_Y
        inca
        sta     GATE_END_Y

        ldx     #gate_redraw_neighbors
        ldb     GATE_WORK_ID
        lda     b,x
        beq     gcr_dimensions
        deca
        ldb     #3
        mul
        ldx     #maze_gates
        leax    d,x
        lda     ,x
        suba    #2
        cmpa    GATE_START_X
        bhs     gcr_neighbor_end_x
        sta     GATE_START_X
gcr_neighbor_end_x
        lda     ,x
        inca
        cmpa    GATE_END_X
        bls     gcr_neighbor_start_y
        sta     GATE_END_X
gcr_neighbor_start_y
        lda     1,x
        suba    #2
        cmpa    GATE_START_Y
        bhs     gcr_neighbor_end_y
        sta     GATE_START_Y
gcr_neighbor_end_y
        lda     1,x
        inca
        cmpa    GATE_END_Y
        bls     gcr_dimensions
        sta     GATE_END_Y

gcr_dimensions
        lda     GATE_END_X
        suba    GATE_START_X
        inca
        lsla
        lsla
        sta     GATE_RECT_WIDTH
        lda     GATE_END_Y
        suba    GATE_START_Y
        inca
        lsla
        lsla
        lsla
        sta     GATE_RECT_ROWS

        lda     GATE_START_Y
        ldb     #5
        mul
        tfr     b,a
        clrb
        addd    #$2000
        std     GATE_RECT_FB
        lda     GATE_START_X
        adda    #8
        lsla
        lsla
        tfr     a,b
        clra
        addd    GATE_RECT_FB
        std     GATE_RECT_FB
        rts

gate_set_player_region
        ldd     PLAYER_FB
        std     GATE_RECT_FB
        lda     #8
        sta     GATE_RECT_WIDTH
        lda     #16
        sta     GATE_RECT_ROWS
        rts

gate_map_shadow
        lda     #FB_SCRATCH_PAGE0
        sta     GIME_PAR1
        inca
        sta     GIME_PAR1+1
        inca
        sta     GIME_PAR1+2
        inca
        sta     GIME_PAR1+3
        rts
        endc

gate_map_live
        lda     #LIVE_PAGE0
        ifne    PERSISTENT_FB
        tst     FB_INIT_STATE
        beq     gml_map
        tst     FB_BACK_ID
        beq     gml_map
        lda     #FB_B_PAGE0
gml_map
        endc
        sta     GIME_PAR1
        inca
        sta     GIME_PAR1+1
        inca
        sta     GIME_PAR1+2
        inca
        sta     GIME_PAR1+3
        rts

; X is a live framebuffer address. Map the corresponding shadow physical page
; at $A000 and return U at the identical offset inside that page.
        ifeq    PERSISTENT_FB
gate_map_shadow_window
        tfr     x,d
        cmpa    #$40
        blo     gmsw_page0
        cmpa    #$60
        blo     gmsw_page1
        cmpa    #$80
        blo     gmsw_page2
        lda     #FB_SCRATCH_PAGE0+3
        bra     gmsw_map
gmsw_page0
        lda     #FB_SCRATCH_PAGE0
        bra     gmsw_map
gmsw_page1
        lda     #FB_SCRATCH_PAGE0+1
        bra     gmsw_map
gmsw_page2
        lda     #FB_SCRATCH_PAGE0+2
gmsw_map
        sta     GATE_SHADOW_PAGE
        sta     GIME_PAR5
        tfr     x,d
        anda    #$1F
        addd    #$A000
        tfr     d,u
        rts

gate_region_to_shadow
        ldx     GATE_RECT_FB
        lda     GATE_RECT_ROWS
        sta     GATE_COPY_ROWS
        lbsr    gate_map_shadow_window
grts_row
        lda     GATE_RECT_WIDTH
        sta     GATE_COPY_COUNT
grts_byte
        lda     ,x+
        sta     ,u+
        cmpu    #$C000
        bne     grts_byte_done
        inc     GATE_SHADOW_PAGE
        lda     GATE_SHADOW_PAGE
        sta     GIME_PAR5
        ldu     #$A000
grts_byte_done
        dec     GATE_COPY_COUNT
        bne     grts_byte
        dec     GATE_COPY_ROWS
        beq     grts_done
        ldb     #160
        subb    GATE_RECT_WIDTH
        abx
        clra
        leau    d,u
        cmpu    #$C000
        blo     grts_row
        leau    -$2000,u
        inc     GATE_SHADOW_PAGE
        lda     GATE_SHADOW_PAGE
        sta     GIME_PAR5
        bra     grts_row
grts_done
        lda     #$34
        sta     GIME_PAR5
        rts

gate_region_from_shadow
        ldx     GATE_RECT_FB
        lda     GATE_RECT_ROWS
        sta     GATE_COPY_ROWS
        lbsr    gate_map_shadow_window
grfs_row
        lda     GATE_RECT_WIDTH
        sta     GATE_COPY_COUNT
grfs_byte
        lda     ,u+
        sta     ,x+
        cmpu    #$C000
        bne     grfs_byte_done
        inc     GATE_SHADOW_PAGE
        lda     GATE_SHADOW_PAGE
        sta     GIME_PAR5
        ldu     #$A000
grfs_byte_done
        dec     GATE_COPY_COUNT
        bne     grfs_byte
        dec     GATE_COPY_ROWS
        beq     grfs_done
        ldb     #160
        subb    GATE_RECT_WIDTH
        abx
        clra
        leau    d,u
        cmpu    #$C000
        blo     grfs_row
        leau    -$2000,u
        inc     GATE_SHADOW_PAGE
        lda     GATE_SHADOW_PAGE
        sta     GIME_PAR5
        bra     grfs_row
grfs_done
        lda     #$34
        sta     GIME_PAR5
        rts
        endc

draw_enemy_stage
        lbsr    enemy_frame_number
        lbsr    sparse_enemy_stream
        lbsr    sparse_blit_stage
        rts

; Return the indexed sparse frame number in A. B is N/E/S/W. Parts 1-8 use
; one type each; later parts rotate four adjacent types across active records.
enemy_frame_number
        cmpb    #4
        blo     efn_direction_ready
        clrb
efn_direction_ready
        stb     STAGE_SOURCE
        lda     #4
        suba    ENEMY_WORK
        cmpa    #4
        bls     efn_slot_ready
        lda     #4
efn_slot_ready
        sta     STAGE_COUNT
        lda     STAGE
        cmpa    #9
        blo     efn_type_ready
        deca
        anda    #7
        cmpa    #5
        blo     efn_offset_ready
        suba    #5
efn_offset_ready
        sta     STAGE_PIXEL
        lda     #4
        suba    ENEMY_WORK
        cmpa    #4
        blo     efn_record_ready
        clra
efn_record_ready
        adda    STAGE_PIXEL
        inca
efn_type_ready
        deca
        lsla
        lsla
        adda    STAGE_SOURCE
        lsla
        lsla
        ora     ENEMY_ANIM
        rts

; player_draw_impl: draw the selected player stream into BACK.
;
; Inputs:
;   PLAYER_FACE - direction 0..3
;   PLAYER_ANIM - animation phase 0..3
;   X - destination framebuffer address
;
; Returns:
;   A, B, X, Y, U, CC - undefined
;
; Side effects:
;   Temporarily maps PAR5 to the indexed player stream and restores page $34.
player_draw_impl
        lda     PLAYER_FACE
        lsla
        lsla
        adda    PLAYER_ANIM
        lbsr    sparse_player_stream
        lbsr    sparse_blit_fb
        rts

; Resolve A's always-mapped enemy index entry and map its stream page.
sparse_enemy_stream
        ldb     #3
        mul
        ldu     #SPARSE_ENEMY_INDEX_ADDR
        leau    d,u
        lda     ,u
        sta     GIME_PAR5
        ldu     1,u
        rts

; Resolve A's always-mapped player index entry and map its stream page.
sparse_player_stream
        ldb     #3
        mul
        ldu     #SPARSE_PLAYER_INDEX_ADDR
        leau    d,u
        lda     ,u
        sta     GIME_PAR5
        ldu     1,u
        rts

; Decode shared destination deltas into the mapped BACK framebuffer.
sparse_blit_fb
        bra     sbf_delta
sbf_partial
        andb    #$7F
sbf_partial_byte
        lda     ,u+
        anda    ,x
        ora     ,u+
        sta     ,x+
        decb
        bne     sbf_partial_byte
sbf_delta
        ldb     ,u+
        cmpb    #$FF
        beq     sbf_extended
        abx
sbf_command
        ldb     ,u+
        bmi     sbf_partial
        cmpb    #5
        beq     sbf_opaque5
        cmpb    #4
        blo     sbf_opaque_small
        beq     sbf_opaque4
        cmpb    #6
        beq     sbf_opaque6
sbf_opaque_byte
        lda     ,u+
        sta     ,x+
        decb
        bne     sbf_opaque_byte
        bra     sbf_delta
sbf_opaque_small
        cmpb    #2
        beq     sbf_opaque2
        blo     sbf_opaque1
        bra     sbf_opaque3
sbf_opaque5
        pulu    d,y
        std     ,x++
        sty     ,x++
sbf_opaque1
        lda     ,u+
        sta     ,x+
        bra     sbf_delta
sbf_opaque3
        ldd     ,u++
        std     ,x++
        bra     sbf_opaque1
sbf_opaque6
        pulu    d,y
        std     ,x++
        sty     ,x++
        ldd     ,u++
        std     ,x++
        bra     sbf_delta
sbf_opaque4
        pulu    d,y
        std     ,x++
        sty     ,x++
        bra     sbf_delta
sbf_opaque2
        ldd     ,u++
        std     ,x++
        bra     sbf_delta
sbf_extended
        ldd     ,u++
        beq     sparse_decode_done
        leax    d,x
        leau    1,u
        bra     sbf_command

sparse_decode_done
        lda     #$34
        sta     GIME_PAR5
        rts

; Decode shared destination deltas into the 8-byte-wide actor stage.
sparse_blit_stage
sbs_delta
        ldb     ,u+
        cmpb    #$FF
        beq     sbs_extended
        bitb    #$80
        beq     sbs_add_delta
        subb    #152
sbs_add_delta
        abx
sbs_command
        ldb     ,u+
        bmi     sbs_partial
sbs_opaque_byte
        lda     ,u+
        sta     ,x+
        decb
        bne     sbs_opaque_byte
        bra     sbs_delta
sbs_partial
        andb    #$7F
sbs_partial_byte
        lda     ,u+
        anda    ,x
        ora     ,u+
        sta     ,x+
        decb
        bne     sbs_partial_byte
        bra     sbs_delta
sbs_extended
        ldd     ,u++
        beq     sparse_decode_done
        ldb     ,u+
        abx
        bra     sbs_command

draw_vegetable_stage
        pshs    x
        lda     STAGE
        beq     dvs_first
        deca
        cmpa    #18
        blo     dvs_indexed
        lda     #17
dvs_indexed
        ldb     #SPRITE_SOURCE_SIZE
        mul
        ldy     #vegetable_sprites
        leay    d,y
        bra     dvs_draw
dvs_first
        ldy     #vegetable_sprites
dvs_draw
        puls    x
        ldu     #sprite_attr0_pairs
        lbsr    blit_stage_sprite
        rts

; Expand one 64-byte 2bpp source into a compact 128-byte 4bpp surface.
blit_stage_sprite
        lda     #SPRITE_SOURCE_SIZE
        sta     STAGE_COUNT
bss_source
        lda     ,y+
        sta     STAGE_SOURCE
        lsra
        lsra
        lsra
        lsra
        lda     a,u
        lbsr    merge_stage_pixel
        lda     STAGE_SOURCE
        anda    #$0F
        lda     a,u
        lbsr    merge_stage_pixel
        dec     STAGE_COUNT
        bne     bss_source
        rts

merge_stage_pixel
        sta     STAGE_PIXEL
        clrb
        bita    #$F0
        bne     msp_high
        orb     #$F0
msp_high
        bita    #$0F
        bne     msp_low
        orb     #$0F
msp_low
        andb    ,x
        orb     STAGE_PIXEL
        stb     ,x+
        rts

capture_zone_bg
        ldx     #ENEMY_ZONE_FB
        ldu     #ENEMY_ZONE_BG
        ldy     #ENEMY_ZONE_ROWS
czb_row
        ldd     ,x++
        std     ,u++
        ldd     ,x++
        std     ,u++
        ldd     ,x++
        std     ,u++
        ldd     ,x++
        std     ,u++
        leax    152,x
        leay    -1,y
        bne     czb_row
        lbsr    build_enemy_nest_cache
        rts

; Expand the four stage-selected dormant frames once when the authoritative
; nest background is captured. Animation frames then publish one native
; 16-by-16 rectangle without sparse decoding or a 16-by-32 rebuild.
build_enemy_nest_cache
        lda     ENEMY_ANIM
        pshs    a
        clr     ENEMY_ANIM
        clr     ENEMY_WORK
        ldu     #ENEMY_NEST_CACHE
benc_frame
        pshs    u
        ldx     #ENEMY_ZONE_BG+128
        ldu     #ENEMY_ZONE_STAGE
        lbsr    copy_nest_128
        ldx     #ENEMY_ZONE_STAGE
        ldb     #0
        lbsr    draw_enemy_stage
        puls    u
        ldx     #ENEMY_ZONE_STAGE
        lbsr    copy_nest_128
        inc     ENEMY_ANIM
        lda     ENEMY_ANIM
        cmpa    #4
        blo     benc_frame
        puls    a
        sta     ENEMY_ANIM
        rts

copy_nest_128
        ldy     #64
bnc_copy
        ldd     ,x++
        std     ,u++
        leay    -1,y
        bne     bnc_copy
        rts

; A removed skull redraws one 16-by-16 clean footprint. Copy that footprint
; into the authoritative compact nest background before recompositing actors.
refresh_zone_bg_footprint
        lda     ENTITY_X
        cmpa    #12
        bne     rzbf_done
        lda     ENTITY_Y
        cmpa    #10
        blo     rzbf_done
        cmpa    #13
        bhs     rzbf_done
        suba    #10
        ldb     #8
        mul
        stb     ENEMY_ROW
        lda     #160
        ldb     ENEMY_ROW
        mul
        addd    #ENEMY_ZONE_FB
        tfr     d,x
        ldb     ENEMY_ROW
        clra
        lslb
        rola
        lslb
        rola
        lslb
        rola
        addd    #ENEMY_ZONE_BG
        tfr     d,u
        ldy     #16
rzbf_row
        ldd     ,x++
        std     ,u++
        ldd     ,x++
        std     ,u++
        ldd     ,x++
        std     ,u++
        ldd     ,x++
        std     ,u++
        leax    152,x
        leay    -1,y
        bne     rzbf_row
rzbf_done
        rts

enemy_runtime_end
        end
