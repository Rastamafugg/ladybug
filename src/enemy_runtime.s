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
        jmp     player_frame_cache_impl
        jmp     enemy_render_impl
        jmp     frame_render_impl
        jmp     framebuffer_init_impl
        jmp     framebuffer_irq_impl

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
PLAYER_BG_VALID equ $006A
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
COLOR_WHITE    equ 6

ENTITY_TABLE   equ $A380
PLAYER_BG      equ $A300
PLAYER_STAGE   equ $A3F0
PLAYER_OLD_STAGE equ $A610      ; upper half of transient enemy staging surface
ENTITY_SKULL   equ 1
ENEMY_TABLE    equ $A470
GATE_STATE     equ $A240
ENEMY_ZONE_BG  equ $A490
ENEMY_ZONE_STAGE equ $A590
ENEMY_BG_BASE  equ $A690
ENEMY_OLD_FB   equ $A890
ENEMY_SPRITE_CACHE equ $1800    ; five 128-byte native record/dormant frames
ENEMY_CACHE_KEYS equ $1A80      ; type/direction/animation key per slot
PLAYER_SPRITE_CACHE equ $1A85   ; active 128-byte native player frame
PLAYER_CACHE_KEY equ $1B05      ; face/animation key for player cache
FB_META_A      equ $A900        ; 256-byte A ownership/damage ledger
FB_META_B      equ $AA00        ; 256-byte B ownership/damage ledger
PLAYER_BG_B    equ $AB00        ; B-side player restoration bytes
ENEMY_BG_B     equ $AB80        ; four B-side enemy restoration buffers
FBM_STATE      equ 0
FBM_DAMAGE     equ 1
FBM_PLAYER_VALID equ 2
FBM_PLAYER_KEY equ 3
FBM_PLAYER_FB  equ 4
FBM_ENEMIES   equ 8
FBM_ENEMY_KEYS equ 40
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
ENEMY_CACHE_FRAME_SIZE equ 128
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

; Record: active, framebuffer pointer, pixel phase, cell x, cell y,
; saved-background valid, selected direction.
enemy_init_impl
        lbsr    reset_enemy_state
        lda     ENEMY_RENDER_FLAGS
        ora     #ERF_INIT|ERF_DIRTY
        sta     ENEMY_RENDER_FLAGS
        rts

reset_enemy_state
        clr     ENEMY_ANIM
        lda     #8
        sta     ENEMY_TIMER
        lbsr    reload_enemy_box_timer
        clr     BOX_INDEX
        clr     BOX_PHASE
        clr     ENEMY_ACTIVE
        clr     ENEMY_RELEASED
        clr     VEG_STATE
        clr     FREEZE_TIMER
        clr     FREEZE_TIMER+1
        clr     ENEMY_NEST_DIRTY
        clr     ENEMY_MOVE
        clr     ENEMY_DEATH_LATCH
        clr     PLAYER_TICK_PENDING
        clr     ENEMY_OLD_VALID
        ldx     #ENEMY_OLD_FB
        clra
        clrb
        std     ,x
        std     2,x
        std     4,x
        std     6,x
        ldx     #ENEMY_TABLE
        ldb     #RECORD_SIZE*4
ei_clear
        clr     ,x+
        decb
        bne     ei_clear
        ldx     #ENEMY_CACHE_KEYS
        ldb     #5
        lda     #$FF
ei_cache_clear
        sta     ,x+
        decb
        bne     ei_cache_clear
        sta     PLAYER_CACHE_KEY
        rts

; Keep death/reset cadence synchronized with the resident perimeter timer.
reload_enemy_box_timer
        ldb     #9
        lda     STAGE
        cmpa    #2
        blo     rebt_store
        subb    #3
        cmpa    #5
        blo     rebt_store
        subb    #3
rebt_store
        stb     BOX_TIMER
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
        lda     #1
        sta     ENEMY_NEST_DIRTY
        lda     ENEMY_RENDER_FLAGS
        ora     #ERF_DIRTY
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
        lda     #1
        sta     ENEMY_NEST_DIRTY
        lda     ENEMY_RENDER_FLAGS
        ora     #ERF_DIRTY
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
        lda     #1
        sta     ENEMY_NEST_DIRTY
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
        bita    #ERF_DIRTY
        beq     eri_done
        ifne    PERSISTENT_FB
        tst     ENEMY_NEST_DIRTY
        beq     eri_finish
        lbsr    compose_enemy_zone
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
        lbsr    actor_closure_restore
        lbsr    framebuffer_queue_damage
        lbsr    framebuffer_project_damage
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
        clr     8,u              ; ENEMY_RENDER_FLAGS belongs to actor closure
        clr     FBM_DAMAGE-FBM_PENDING_INTENTS,u
        lda     ,u
        ora     1,u
        ora     9,u              ; RENDER_GATE_ID
        ora     11,u             ; RENDER_GATE2_ID
        beq     fbqd_done
        inc     FBM_DAMAGE-FBM_PENDING_INTENTS,u
fbqd_done
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
        jsr     draw_entities
        jsr     draw_hud
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
        ldx     1,x
        lbsr    roam_bg_address
        lbsr    roam_copy_fb_to_bg
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
        tst     FB_BACK_ID
        beq     fbp_enemies
        lbsr    framebuffer_swap_player_bg
fbp_enemies
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
fbp_ok
        andcc   #$FE
        rts

; Capture buffer-local ownership, restore the A-side player save-under when B
; was rendered, then publish readiness as one IRQ-masked transaction.
framebuffer_finish_back
        tst     FB_INIT_STATE
        beq     fbf_done
        lbsr    framebuffer_capture_back
        tst     FB_BACK_ID
        beq     fbf_ready
        lbsr    framebuffer_swap_player_bg
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

framebuffer_swap_player_bg
        ldx     #PLAYER_BG
        ldu     #PLAYER_BG_B
        ldy     #128
fbsp_loop
        lda     ,x
        ldb     ,u
        stb     ,x+
        sta     ,u+
        leay    -1,y
        bne     fbsp_loop
        rts

framebuffer_capture_back
        lbsr    framebuffer_back_meta
        lda     #FBM_VALID
        sta     FBM_STATE,u
        clr     FBM_DAMAGE,u
        lda     PLAYER_BG_VALID
        sta     FBM_PLAYER_VALID,u
        lda     PLAYER_CACHE_KEY
        sta     FBM_PLAYER_KEY,u
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
        ldd     ENEMY_CACHE_KEYS
        std     ,u
        ldd     ENEMY_CACHE_KEYS+2
        std     2,u
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
        lda     PLAYER_CACHE_KEY
        sta     FB_META_A+FBM_PLAYER_KEY
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
        ldd     ENEMY_CACHE_KEYS
        std     FB_META_A+FBM_ENEMY_KEYS
        ldd     ENEMY_CACHE_KEYS+2
        std     FB_META_A+FBM_ENEMY_KEYS+2
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
        lda     #1
        sta     ENEMY_NEST_DIRTY
        lda     ENEMY_RENDER_FLAGS
        ora     #ERF_DIRTY
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
        bne     est_next
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
        lda     #1
        sta     ENEMY_NEST_DIRTY
        lda     RENDER_FLAGS
        ora     #RF_ENTITIES
        sta     RENDER_FLAGS
        lda     ENEMY_RENDER_FLAGS
        ora     #ERF_DIRTY|ERF_ZONE_REFRESH
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

roam_copy_bg_to_fb
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
        pshs    x
        lbsr    enemy_sprite_cache
        puls    x
        lbsr    blit_enemy_fb
        rts

; blit_enemy_fb: merge one cached native enemy frame into the framebuffer.
;
; Inputs:
;   X - destination framebuffer address
;   Y - 128-byte native 4bpp frame
;
; Returns:
;   A, B, X, Y, CC - undefined
;
; Side effects:
;   Source-zero nibbles preserve the destination.
blit_enemy_fb
        lda     #16
        sta     STAGE_COUNT
bef_row
        lda     #8
        sta     STAGE_PIXEL
bef_byte
        lda     ,y+
        sta     STAGE_SOURCE
        clrb
        bita    #$F0
        bne     bef_high
        orb     #$F0
bef_high
        bita    #$0F
        bne     bef_low
        orb     #$0F
bef_low
        andb    ,x
        orb     STAGE_SOURCE
        stb     ,x+
        dec     STAGE_PIXEL
        bne     bef_byte
        leax    152,x
        dec     STAGE_COUNT
        bne     bef_row
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

        ; The vegetable replaces the dormant actor. A collected vegetable
        ; returns the nest to the dormant pattern until the count drops.
        lda     VEG_STATE
        cmpa    #1
        beq     cez_vegetable
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

; Build the clean new player rectangle from the old save-under plus newly
; exposed edge pixels. Publish the complete new sprite before erasing only the
; old strips it no longer covers, so scanout never sees a player-free frame.
player_compose_impl
        ldx     #PLAYER_BG
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
        ldu     #PLAYER_BG
        ldy     #64
pci_save_loop
        ldd     ,x++
        std     ,u++
        leay    -1,y
        bne     pci_save_loop
        lda     #1
        sta     PLAYER_BG_VALID

        lbsr    player_frame_cache_impl
        ldx     #PLAYER_STAGE
        lbsr    blit_enemy_stage

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
        lda     RENDER_GATE_ID
        deca
        jsr     draw_gate_diagonal
        bra     gci_done
gci_final
        jsr     restore_gate_diagonal_dots
        lda     RENDER_GATE_ID
        deca
        jsr     draw_gate
        jsr     draw_entities
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

draw_enemy_stage
        pshs    x
        lbsr    enemy_sprite_cache
        puls    x
        lbsr    blit_enemy_stage
        rts

; Return a low-RAM cached frame in Y. B is N/E/S/W. Parts 1-8 use one
; type each; later parts rotate four adjacent types across active records.
enemy_sprite_cache
        cmpb    #4
        blo     esc_direction_ready
        clrb
esc_direction_ready
        stb     STAGE_SOURCE
        lda     #4
        suba    ENEMY_WORK
        cmpa    #4
        bls     esc_slot_ready
        lda     #4
esc_slot_ready
        sta     STAGE_COUNT
        lda     STAGE
        cmpa    #9
        blo     esc_type_ready
        deca
        anda    #7
        cmpa    #5
        blo     esc_offset_ready
        suba    #5
esc_offset_ready
        sta     STAGE_PIXEL
        lda     #4
        suba    ENEMY_WORK
        cmpa    #4
        blo     esc_record_ready
        clra
esc_record_ready
        adda    STAGE_PIXEL
        inca
esc_type_ready
        deca
        lsla
        lsla
        adda    STAGE_SOURCE
        sta     STAGE_PIXEL
        lsla
        lsla
        ora     ENEMY_ANIM
        sta     STAGE_PIXEL

        ldx     #ENEMY_CACHE_KEYS
        ldb     STAGE_COUNT
        lda     b,x
        cmpa    STAGE_PIXEL
        beq     esc_cached
        lda     STAGE_PIXEL
        sta     b,x
        lsra
        lsra
        adda    #$A0
        sta     STAGE_PIXEL
        lda     ENEMY_ANIM
        ldb     #SPRITE_SOURCE_SIZE
        mul
        adda    STAGE_PIXEL
        tfr     d,y

        lda     STAGE_COUNT
        ldb     #ENEMY_CACHE_FRAME_SIZE
        mul
        addd    #ENEMY_SPRITE_CACHE
        tfr     d,x
        lda     #$35
        sta     GIME_PAR5
        ldu     #sprite_attr0_pairs
        ldb     #SPRITE_SOURCE_SIZE
esc_expand
        lda     ,y+
        sta     STAGE_SOURCE
        lsra
        lsra
        lsra
        lsra
        lda     a,u
        sta     ,x+
        lda     STAGE_SOURCE
        anda    #$0F
        lda     a,u
        sta     ,x+
        decb
        bne     esc_expand
        lda     #$34
        sta     GIME_PAR5
esc_cached
        lda     STAGE_COUNT
        ldb     #ENEMY_CACHE_FRAME_SIZE
        mul
        addd    #ENEMY_SPRITE_CACHE
        tfr     d,y
        rts

; player_frame_cache_impl: return the selected native 4bpp player frame.
;
; Inputs:
;   PLAYER_FACE - direction 0..3
;   PLAYER_ANIM - animation phase 0..3
;
; Returns:
;   Y - 128-byte native 4bpp player frame
;   A, B, X, U, CC - undefined
;
; Side effects:
;   Expands the packed source only when the face/animation key changes.
player_frame_cache_impl
        lda     PLAYER_FACE
        lsla
        lsla
        adda    PLAYER_ANIM
        cmpa    PLAYER_CACHE_KEY
        beq     pfc_cached
        sta     PLAYER_CACHE_KEY
        ldb     #SPRITE_SOURCE_SIZE
        mul
        ldy     #player_sprites
        leay    d,y
        ldx     #PLAYER_SPRITE_CACHE
        ldu     #sprite_attr0_pairs
        ldb     #SPRITE_SOURCE_SIZE
pfc_expand
        lda     ,y+
        sta     STAGE_SOURCE
        lsra
        lsra
        lsra
        lsra
        lda     a,u
        sta     ,x+
        lda     STAGE_SOURCE
        anda    #$0F
        lda     a,u
        sta     ,x+
        decb
        bne     pfc_expand
pfc_cached
        ldy     #PLAYER_SPRITE_CACHE
        rts

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

; blit_enemy_stage: merge one cached native enemy frame into compact staging.
;
; Inputs:
;   X - destination compact-stage address
;   Y - 128-byte native 4bpp frame
;
; Returns:
;   A, B, X, Y, CC - undefined
;
; Side effects:
;   Source-zero nibbles preserve the destination.
blit_enemy_stage
        lda     #ENEMY_CACHE_FRAME_SIZE
        sta     STAGE_COUNT
bes_byte
        lda     ,y+
        sta     STAGE_SOURCE
        clrb
        bita    #$F0
        bne     bes_high
        orb     #$F0
bes_high
        bita    #$0F
        bne     bes_low
        orb     #$0F
bes_low
        andb    ,x
        orb     STAGE_SOURCE
        stb     ,x+
        dec     STAGE_COUNT
        bne     bes_byte
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
