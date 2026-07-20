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

ENEMY_ANIM     equ $0054
ENEMY_TIMER    equ $0055
ENEMY_ACTIVE   equ $0058
ENEMY_RELEASED equ $0059
VEG_STATE      equ $005A
FREEZE_TIMER   equ $005B
ENEMY_WORK     equ $005D
ENEMY_PTR      equ $005E
ENEMY_DIRTY    equ $0060
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

ENTITY_TABLE   equ $A380
PLAYER_BG      equ $A300
PLAYER_STAGE   equ $A3F0
PLAYER_OLD_STAGE equ $A610      ; upper half of transient enemy staging surface
ENTITY_SKULL   equ 1
ENEMY_TABLE    equ $A470
ENEMY_ZONE_BG  equ $A490
ENEMY_ZONE_STAGE equ $A590
ENEMY_ZONE_FB  equ $4DEC
ENEMY_FB       equ $57EC
SPRITE_SOURCE_SIZE equ 64
ENEMY_ZONE_ROWS equ 32
RECORD_SIZE    equ 6
DIR_NONE       equ $FF

; Record: active, framebuffer pointer, pixel phase, cell y, saved-background valid.
enemy_init_impl
        lbsr    capture_zone_bg
        lbsr    reset_enemy_state
        lbsr    compose_enemy_zone
        rts

reset_enemy_state
        clr     ENEMY_ANIM
        lda     #8
        sta     ENEMY_TIMER
        lda     #9
        sta     BOX_TIMER
        clr     BOX_INDEX
        clr     BOX_PHASE
        clr     ENEMY_ACTIVE
        clr     ENEMY_RELEASED
        clr     VEG_STATE
        clr     FREEZE_TIMER
        clr     FREEZE_TIMER+1
        clr     ENEMY_DIRTY
        clr     ENEMY_MOVE
        clr     ENEMY_DEATH_LATCH
        clr     PLAYER_TICK_PENDING
        ldx     #ENEMY_TABLE
        ldb     #RECORD_SIZE*4
ei_clear
        clr     ,x+
        decb
        bne     ei_clear
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
        clr     5,x
        inc     ENEMY_ACTIVE
        inc     ENEMY_RELEASED
        lda     #1
        sta     ENEMY_DIRTY
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
        lbsr    reset_enemy_state
        lda     #1
        sta     ENEMY_DEATH_LATCH
        lda     #1
        sta     ENEMY_DIRTY
        lbsr    compose_enemy_zone
        clr     ENEMY_DIRTY
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
        sta     ENEMY_DIRTY
et_freeze_timer
        tst     DEATH_STATE
        bne     et_render_test
        ldd     FREEZE_TIMER
        beq     et_find_movement
        subd    #1
        std     FREEZE_TIMER
        bra     et_render_test
et_find_movement
        ldx     #ENEMY_TABLE
        lda     #4
        sta     ENEMY_WORK
et_move_scan
        tst     ,x
        beq     et_move_next
        lda     4,x
        cmpa    #10
        bls     et_move_next
        lda     #1
        sta     ENEMY_MOVE
        sta     ENEMY_DIRTY
        bra     et_render_test
et_move_next
        leax    RECORD_SIZE,x
        dec     ENEMY_WORK
        bne     et_move_scan
et_render_test
        tst     ENEMY_DIRTY
        bne     et_update
        rts

et_update
        tst     ENEMY_MOVE
        beq     et_compose
        ldx     #ENEMY_TABLE
        lda     #4
        sta     ENEMY_WORK
et_update_loop
        tst     ,x
        beq     et_update_next
        ; The first AI pass follows the verified den exit north and stops at
        ; its first maze decision. Junction selection is a later MAME pass.
        lda     4,x
        cmpa    #10
        bls     et_contact
        ldd     1,x
        subd    #160
        std     1,x
        inc     3,x
        lda     3,x
        cmpa    #8
        blo     et_contact
        clr     3,x
        dec     4,x
        lda     ENEMY_WORK
        pshs    a,x
        lbsr    enemy_skull_test
        puls    a,x
        sta     ENEMY_WORK
        tst     ,x
        beq     et_update_next
et_contact
        lbsr    enemy_player_contact
        bcc     et_update_next
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
        lbsr    compose_enemy_zone
        clr     ENEMY_DIRTY
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
        sta     ENEMY_DIRTY
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

; Current active enemies occupy the nest's vertical lane. Use the displayed
; 16-by-16 footprints instead of requiring simultaneous cell alignment.
enemy_player_contact
        lda     PLAYER_CELL_X
        cmpa    #11
        blo     epc_clear
        cmpa    #13
        bhi     epc_clear
        ldd     PLAYER_FB
        subd    1,x
        cmpd    #2400
        bge     epc_clear
        cmpd    #-2400
        ble     epc_clear
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
        cmpa    #12
        bne     est_next
        lda     1,u
        ldx     ENEMY_PTR
        cmpa    4,x
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
        clr     ,x
        clr     5,x
        dec     ENEMY_ACTIVE
        clr     VEG_STATE
        lda     #1
        sta     ENEMY_DIRTY
        rts
est_next
        leau    4,u
        dec     ENEMY_WORK
        bne     est_loop
est_done
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
        lda     4,u
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

        lda     PLAYER_FACE
        lsla
        lsla
        adda    PLAYER_ANIM
        ldb     #SPRITE_SOURCE_SIZE
        mul
        ldy     #player_sprites
        leay    d,y
        ldx     #PLAYER_STAGE
        ldu     #sprite_attr0_pairs
        lbsr    blit_stage_sprite

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

draw_enemy_stage
        pshs    x
        lda     ENEMY_ANIM
        ldb     #SPRITE_SOURCE_SIZE
        mul
        ldy     #enemy_sprites
        leay    d,y
        puls    x
        ldu     #sprite_attr0_pairs
        lbsr    blit_stage_sprite
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
