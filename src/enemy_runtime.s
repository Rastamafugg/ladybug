; GMC bank-3 enemy runtime, copied to low RAM $0800 during boot.
; Entry table offsets are part of the resident/runtime contract.

        pragma  nodollarlocal,6809
        include "ladybug_runtime_symbols.inc"
        org     $0800

        jmp     enemy_init_impl
        jmp     enemy_tick_impl
        jmp     enemy_release_impl
        jmp     enemy_collect_impl
        jmp     player_compose_impl
        jmp     gate_compose_impl
        jmp     player_frame_cache_impl

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
GATE_ID         equ $0013
GATE_X          equ $0014
GATE_Y          equ $0015
GATE_ANIM_ID    equ $0019
PLAYER_CELL_X  equ $0009
PLAYER_CELL_Y  equ $000A
PLAYER_FB      equ $000B
PLAYER_DIR     equ $0006
PLAYER_FACE    equ $0007
PLAYER_WANT    equ $000F
PLAYER_ANIM    equ $004F
DEATH_STATE    equ $004D
SCORE_BCD      equ $001D
HIGH_BCD       equ $0020
STAGE          equ $0024
ENTITY_COUNT   equ $0032
ENTITY_X       equ $0036
ENTITY_Y       equ $0037
RNG_STATE      equ $0034
LAST_FRAME     equ $0000

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
ENEMY_ZONE_FB  equ $4DEC
ENEMY_FB       equ $57EC
SPRITE_SOURCE_SIZE equ 64
ENEMY_CACHE_FRAME_SIZE equ 128
ENEMY_ZONE_ROWS equ 32
RECORD_SIZE    equ 8
DIR_NONE       equ $FF
GIME_PAR1      equ $FFA1
GIME_PAR5      equ $FFA5
SHADOW_PAGE0   equ $2C
LIVE_PAGE0     equ $30

; Record: active, framebuffer pointer, pixel phase, cell x, cell y,
; saved-background valid, selected direction.
enemy_init_impl
        lbsr    capture_zone_bg
        lbsr    reset_enemy_state
        lbsr    compose_enemy_zone
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
        lda     ENEMY_ACTIVE
        cmpa    #4
        bne     er_done
        lda     #1
        sta     VEG_STATE
er_done
        rts

enemy_tick_impl
        lda     DEATH_STATE
        beq     et_alive
        tst     ENEMY_DEATH_LATCH
        bne     et_death_animate
et_begin_death
        tst     PLAYER_BG_VALID
        beq     et_death_player_clear
        jsr     restore_player
et_death_player_clear
        clr     ENEMY_MOVE
        lbsr    roam_despawn_all
        lbsr    reset_enemy_state
        lda     #1
        sta     ENEMY_DEATH_LATCH
        lda     #1
        sta     ENEMY_NEST_DIRTY
        lbsr    compose_enemy_zone
        clr     ENEMY_NEST_DIRTY
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
        lbsr    roam_prepare_shadow
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
        tst     ENEMY_NEST_DIRTY
        beq     et_finish
        lbsr    compose_enemy_zone
et_finish
        lbsr    roam_finish_shadow
        clr     ENEMY_NEST_DIRTY
        rts

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
        jsr     draw_hud
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
        pshs    u
        jsr     restore_entity_footprint
        puls    u
        lbsr    refresh_zone_bg_footprint
        ldx     ENEMY_PTR
        ldd     1,x
        std     GATE_RECT_FB
        lda     #8
        sta     GATE_RECT_WIDTH
        lda     #16
        sta     GATE_RECT_ROWS
        pshs    x
        lbsr    gate_region_to_shadow
        puls    x
        clr     ,x
        clr     6,x
        dec     ENEMY_ACTIVE
        clr     VEG_STATE
        lda     #1
        sta     ENEMY_NEST_DIRTY
        rts
est_next
        leau    4,u
        dec     ENEMY_WORK
        bne     est_loop
est_done
        rts

; Prepare all old/new roaming unions in the hidden framebuffer, then remove
; every old enemy there before any destination background is captured.
roam_prepare_shadow
        clr     ENEMY_ROAMING
        ldu     #ENEMY_OLD_FB
        clra
        clrb
        std     ,u
        std     2,u
        std     4,u
        std     6,u
        ldx     #ENEMY_TABLE
        lda     #4
        sta     ENEMY_WORK
rps_copy_loop
        tst     ,x
        beq     rps_copy_next
        tst     6,x
        bne     rps_copy_actor
        lda     5,x
        cmpa    #11
        bhi     rps_copy_next
rps_copy_actor
        inc     ENEMY_ROAMING
        lbsr    roam_old_slot
        ldd     1,x
        std     ,u
        lbsr    roam_set_prepare_union
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
        tst     ,x
        beq     rps_restore_next
        tst     6,x
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
        addd    #ENEMY_BG_BASE
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
        lda     GATE_ANIM_ID
        beq     gci_done
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
        lda     #SHADOW_PAGE0
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
        lda     #SHADOW_PAGE0+3
        bra     gmsw_map
gmsw_page0
        lda     #SHADOW_PAGE0
        bra     gmsw_map
gmsw_page1
        lda     #SHADOW_PAGE0+1
        bra     gmsw_map
gmsw_page2
        lda     #SHADOW_PAGE0+2
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
