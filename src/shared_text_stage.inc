; DOC-002 source-contract mirror contract menu_paint_rows profile=presentation: Draw authored menu labels using green for the selected row and grey for remaining rows.
; BUG-012 release-profile demo route director, copied to low RAM $0300.
; DOC-002 source-contract mirror begins. Canonical definitions:
; wiki/internal/implementation/routine-catalog.html
; DOC-002 source-contract mirror profile presentation Inputs: Presentation state, interval timer, input edges, current map, and the selected auxiliary profile
; DOC-002 source-contract mirror profile presentation Outputs: Updated presentation state and the dispatcher retain/release status when applicable
; DOC-002 source-contract mirror profile presentation Clobbers: A, B, D, X, Y, U, and condition codes unless a narrower source-local header is present
; DOC-002 source-contract mirror profile presentation Reads: Presentation direct-page state, cold payloads, authored map streams, and input state
; DOC-002 source-contract mirror profile presentation Writes: Presentation state, mapped BACK pixels, and presentation-owned persistent metadata
; DOC-002 source-contract mirror profile presentation Side effects: May retain the foreground interval or produce a complete presentation surface
; DOC-002 source-contract mirror profile presentation Invariants: Gameplay mutation begins only after the dispatcher releases the interval; FRONT publication remains IRQ-owned
; DOC-002 source-contract mirror contract demo_runtime_tick profile=presentation: Advance the deterministic release-demo route at eligible semantic cells.
; DOC-002 source-contract mirror contract logo_vbord_clock profile=presentation: Advance the shared attract and high-score logo phase from an IRQ-atomic VBLANK sample.
; DOC-002 source-contract mirror ends.
        pragma  nodollarlocal,6809
        setdp   $00
        include "ladybug_presentation.inc"
        include "ladybug_presentation_symbols.inc"

; Existing always-mapped perimeter return tail: restore game PAR5, then CC/PC.
PRES_GAME_PAGE_RETURN equ $06BE
PAR5    equ $FFA5
PLAYER_DIR equ $0006
PLAYER_FACE equ $0007
PLAYER_STEP equ $0008
PLAYER_FB equ $000B
PLAYER_CELL_X equ $0009
PLAYER_CELL_Y equ $000A
PLAYER_WANT equ $000F
PLAYER_MANUAL equ $0018
PRES_DEMO_ROUTE equ $00DA
PRES_DEMO_LAST_X equ $00DB
PRES_DEMO_LAST_Y equ $00DC
PRES_DEMO_DIR equ $00DD
PRES_NAME_ROW equ $00DF
PRES_NAME_COL equ $00E0
PRES_NAME_REPEAT equ $00E1
PRES_NAME_LAST_DIR equ $00E2
PRES_TICK_PHASE equ $00E1
PRES_NAME_FLAGS equ $00E2
PRES_NAME_TIMER_PHASE equ $00E8
PRES_NAME_TIMER_BOX equ $00E9
PRES_NAME_OWNER equ $00E3
PRES_NAME_PTR equ $00E4
PRES_NAME_TILE equ $00E6
PRES_HS_READY equ $00E7
; High-score test only: demo-route scratch bytes hold the two owner-local
; cursor destinations; the name tile byte holds the latched move direction.
PRES_NAME_PTR_A equ $00DA
PRES_NAME_PTR_B equ $00DC
PRES_NAME_STEPS equ $00DE
PRES_NAME_DIR equ $00E6
PRES_MODE equ $00A5
PRES_SCREEN equ $00A6
PRES_IN equ $00B5
PRES_OUT equ $00B7
PRES_TMP_H equ $00C2
PRES_TMP_M equ $00C3
PRES_TMP_L equ $00C4
PRES_INSERT equ $00C9
PRES_NAME_LEN equ $00CB
PRES_SCORE_H equ $00BF
PRES_SCORE_M equ $00C0
PRES_SCORE_L equ $00C1
PRES_TIMER equ $00B0
PRES_HIGHSCORE_BASE equ $AF84
PRES_PENDING_NAME equ $AFDE
; The page-$23 helper executes through PAR5, so page-$34 score state uses a
; temporary PAR4 alias instead of dereferencing the helper's own window.
PRES_HIGHSCORE_ALIAS equ $8F84
PRES_PENDING_NAME_ALIAS equ $8FDE
PRES_CURSOR_SAVE_A equ $A590
PRES_CURSOR_SAVE_B equ $A610
PRES_NAME_CL equ $FE
PRES_NAME_END equ $FD
PRES_HS_BLACK equ PRESENTATION_NAME_ENTRY_BLACK_TILE
PRESENTATION_GAMEPLAY_TILES equ $E3D0
MODE_LOAD equ 1
MODE_GAMEOVER equ 7
MODE_NAME equ 8
MAP_HIGH_SCORE equ PRESENTATION_MAP_HIGH_SCORE
MAP_ENTER_HIGH_SCORE equ PRESENTATION_MAP_ENTER_HIGH_SCORE
DIR_N equ 0
DIR_E equ 1
DIR_S equ 2
DIR_W equ 3
DIR_NONE equ $FF
FB_BACK_ID equ $0090
FB_PENDING equ $0091
FB_RENDER_ACTIVE equ $0098
PRES_HOLD_STATE equ $00D4
PRES_HOLD_FINAL equ $81
PAR1 equ $FFA1
PAR2 equ $FFA2
PAR3 equ $FFA3
PAR4 equ $FFA4
JOY_DIR equ $0005
FRAMES equ $0002
PRES_MODULE_DRAW equ $0821
PRES_MAIN_PLAYER_DRAW equ $0812
PLAYER_ANIM equ $004F
PLAYER_ANIM_TIMER equ $0050

        ifne    HIGHSCORE_PHASE_HELPER

; Page-$23 high-score helper.  It remains mapped only while the low-RAM
; high-score owner calls it.  All calls that may change PAR5 return through
; presentation_page23_resume in resident code.
SND_DATA equ $FF51

        org     HIGHSCORE_PHASE_HELPER_ADDRESS

highscore_phase_tick
        ; Attract uses the same page-$23 logo strips; decorative actors remain
        ; owned by the low-RAM overlay after this resident-gateway call returns.
        lda     PRES_SCREEN
        cmpa    #PRESENTATION_MAP_ATTRACT
        lbeq    highscore_logo_tick
        lda     PRES_MODE
        cmpa    #5
        lbeq    menu_tick
        cmpa    #MODE_GAMEOVER
        lbeq    highscore_gameover_tick
        tst     PRES_NAME_FLAGS
        lbne    highscore_commit_done
        lda     PRES_TICK_PHASE
        lbmi    highscore_timer_owner
        tsta
        beq     highscore_timer_frame
        dec     PRES_TICK_PHASE
        lda     PRES_TICK_PHASE
        ifeq COMPLETE_PHASE_AUX
        cmpa    #2
        lbeq    highscore_tick_second
        tsta
        bne     highscore_timer_frame
        lda     #$9F
        sta     SND_DATA
        endc
highscore_timer_frame
        inc     PRES_NAME_TIMER_PHASE
        lda     PRES_NAME_TIMER_PHASE
        cmpa    #PRESENTATION_NAME_ENTRY_TIMER_FRAMES
        lblo    highscore_phase_hold
        clr     PRES_NAME_TIMER_PHASE
        lda     PRES_NAME_TIMER_BOX
        cmpa    #PRESENTATION_NAME_ENTRY_TIMER_COUNT
        lbhs    highscore_commit_done
        lda     #$80
        sta     PRES_TICK_PHASE
highscore_timer_prepare
        lda     PRES_NAME_TIMER_BOX
        sta     PRES_TMP_H
        ldd     #highscore_after_prepare
        std     PRES_NAME_PTR
        ldd     #PRES_MAIN_PAGE23_RESUME
        pshs    d
        jmp     PRES_HIGHSCORE_FB_PREPARE

highscore_after_prepare
highscore_timer_draw
        lda     PRES_TMP_H
        ldb     #PRESENTATION_NAME_ENTRY_TIMER_RECORD_BYTES
        mul
        ldx     #highscore_timer_records
        leax    d,x
        ldd     ,x
        tfr     d,y
        ldd     #highscore_after_tile
        std     PRES_NAME_PTR
        ldd     #PRES_MAIN_PAGE23_RESUME
        pshs    d
        ldd     2,x
        jmp     PRES_MODULE_DRAW_RAW_TILE

; The reserved continuation interval ends at $AD00. This logo clock occupies
; its fitted 80-byte range without changing the mapped owner or return path.
; Raw lwasm concatenates ORG regions, so retain zero padding before the fixed
; continuation label after the clock.
; Retain elapsed VBLANK time independently of PRES_TIMER, which also drives
; high-score text. $A8FD-$A8FF is the reserved three-byte logo-clock slot.
logo_vbord_clock
        pshs    cc
        orcc    #$10
        lda     PAR4
        pshs    a
        lda     #$34
        sta     PAR4
        ldu     FRAMES
        lda     PRES_SCREEN
        lsla
        ora     #$80
        tfr     a,b
        ldx     #$88FD
        eora    2,x
        anda    #$FE
        bne     logo_vbord_init
logo_vbord_advance
        tfr     u,d
        subd    ,x
        cmpd    #31
        blo     logo_vbord_return
        ldd     ,x
        addd    #31
        std     ,x
        lda     2,x
        eora    #1
        sta     2,x
        bra     logo_vbord_advance
logo_vbord_init
        stu     ,x
        stb     2,x
        lda     #$FF
        sta     $D2
        sta     PRES_NAME_OWNER
logo_vbord_return
        ldb     2,x
        andb    #1
        puls    a
        sta     PAR4
        tfr     b,a
        puls    cc,pc

highscore_phase_helper_gap
        rmb     HIGHSCORE_PHASE_HELPER_RESUME-*
highscore_after_tile
        clra
        rts

; A timer tile is persistent state.  Apply it to the current BACK, allow the
; low-RAM name renderer to close and publish every dynamic layer, wait for the
; IRQ owner swap, then repeat the same one-tile transaction for the other
; owner.  $80 is first-owner published; $81 is second-owner published.
highscore_timer_owner
        inc     PRES_NAME_TIMER_PHASE
        tst     FB_PENDING
        bne     highscore_phase_busy
        cmpa    #$80
        bne     highscore_timer_complete
        inc     PRES_TICK_PHASE
        lbra    highscore_timer_prepare
highscore_timer_complete
        inc     PRES_NAME_TIMER_BOX
        lda     #4
        sta     PRES_TICK_PHASE
        ifeq COMPLETE_PHASE_AUX
        lda     #$86
        sta     SND_DATA
        lda     #$35
        sta     SND_DATA
        lda     #$91
        sta     SND_DATA
        endc
        lda     PRES_NAME_TIMER_BOX
        cmpa    #PRESENTATION_NAME_ENTRY_TIMER_COUNT
        bhs     highscore_commit_done
highscore_phase_hold
        clra
        rts
highscore_phase_busy
        lda     #1
        rts

        ifeq COMPLETE_PHASE_AUX
highscore_tick_second
        lda     #$8A
        sta     SND_DATA
        lda     #$23
        sta     SND_DATA
        lda     #$92
        sta     SND_DATA
        lbra    highscore_timer_frame
        endc

highscore_commit_done
        ifne COMPLETE_PHASE_AUX
        lda     PRES_MODE
        cmpa    #MODE_NAME
        bne     highscore_audio_done
        tst     PRES_NAME_FLAGS
        bne     highscore_audio_query
        lda     #2
        sta     PRES_NAME_FLAGS
highscore_audio_query
        jsr     $02C0
        bne     highscore_phase_busy
highscore_audio_done
        endc
        lbsr    highscore_commit_name
        ldd     #highscore_after_highscore_start
        std     PRES_NAME_PTR
        ldd     #PRES_MAIN_PAGE23_RESUME
        pshs    d
        lda     #MAP_HIGH_SCORE
        jmp     PRES_MODULE_START_SCREEN
highscore_after_highscore_start
        lda     #1
        rts

highscore_gameover_tick
        ldd     PRES_TIMER
        addd    #1
        std     PRES_TIMER
        cmpd    #180
        blo     highscore_phase_hold
        lbsr    highscore_prepare_name
        lda     PRES_INSERT
        cmpa    #$FF
        lbeq    highscore_commit_done
        ldd     #highscore_after_name_start
        std     PRES_NAME_PTR
        ldd     #PRES_MAIN_PAGE23_RESUME
        pshs    d
        lda     #MAP_ENTER_HIGH_SCORE
        jmp     PRES_MODULE_START_SCREEN
highscore_after_name_start
        lda     #1
        rts

highscore_prepare_name
        pshs    cc
        orcc    #$10
        lda     PAR4
        pshs    a
        lda     #$34
        sta     PAR4
        tst     PRES_HS_READY
        bne     highscore_prepare_ready
        ldu     #PRES_HIGHSCORE_ALIAS
        lda     #9
highscore_prepare_row
        sta     ,u+
        clr     ,u+
        clr     ,u+
        pshs    a
        ldx     #highscore_default_name_data
        ldy     #7
highscore_prepare_default
        lda     ,x+
        sta     ,u+
        leay    -1,y
        bne     highscore_prepare_default
        puls    a
        deca
        bne     highscore_prepare_row
        inc     PRES_HS_READY
highscore_prepare_ready
        clr     PRES_NAME_FLAGS
        clr     PRES_TICK_PHASE
        clr     PRES_NAME_TIMER_PHASE
        clr     PRES_NAME_TIMER_BOX
        ldd     $001D           ; actual packed-BCD gameplay score
        std     PRES_SCORE_H
        lda     $001F
        sta     PRES_SCORE_L
        lda     #$FF
        sta     PRES_INSERT
        ldx     #PRES_HIGHSCORE_ALIAS
        clrb
highscore_qualify_loop
        lda     PRES_SCORE_H
        cmpa    ,x
        bhi     highscore_qualify_found
        blo     highscore_qualify_next
        lda     PRES_SCORE_M
        cmpa    1,x
        bhi     highscore_qualify_found
        blo     highscore_qualify_next
        lda     PRES_SCORE_L
        cmpa    2,x
        bhi     highscore_qualify_found
highscore_qualify_next
        leax    10,x
        incb
        cmpb    #9
        blo     highscore_qualify_loop
        bra     highscore_qualify_done
highscore_qualify_found
        stb     PRES_INSERT
highscore_qualify_done
        clr     PRES_NAME_LEN
        lda     #19
        sta     PRES_NAME_COL
        sta     PLAYER_CELL_X
        lda     #22
        sta     PRES_NAME_ROW
        sta     PLAYER_CELL_Y
        lda     #DIR_NONE
        sta     PLAYER_DIR
        sta     PLAYER_WANT
        lda     #DIR_N
        sta     PLAYER_FACE
        clr     PLAYER_ANIM
        clr     PRES_NAME_STEPS
        clr     $56             ; gameplay-compatible late-turn state
        lda     #8
        sta     PLAYER_ANIM_TIMER
        ldx     #PRES_PENDING_NAME_ALIAS
        lda     #PRES_HS_BLACK
        ldb     #7
highscore_prepare_blank
        sta     ,x+
        decb
        bne     highscore_prepare_blank
        puls    a
        sta     PAR4
        puls    cc
        rts

highscore_commit_name
        lda     PRES_INSERT
        cmpa    #$FF
        beq     highscore_commit_return
        pshs    cc
        orcc    #$10
        lda     PAR4
        pshs    a
        lda     #$34
        sta     PAR4
        lda     #7
        sta     PRES_TMP_H
        ldx     #PRES_HIGHSCORE_ALIAS+70
        ldu     #PRES_HIGHSCORE_ALIAS+80
highscore_commit_shift
        lda     PRES_TMP_H
        bmi     highscore_commit_write
        cmpa    PRES_INSERT
        blo     highscore_commit_write
        ldb     #10
highscore_commit_record
        lda     ,x+
        sta     ,u+
        decb
        bne     highscore_commit_record
        leax    -20,x
        leau    -20,u
        dec     PRES_TMP_H
        bra     highscore_commit_shift
highscore_commit_write
        ldx     #PRES_HIGHSCORE_ALIAS
        ldb     PRES_INSERT
highscore_commit_find
        beq     highscore_commit_score
        leax    10,x
        decb
        bra     highscore_commit_find
highscore_commit_score
        lda     PRES_SCORE_H
        sta     ,x+
        lda     PRES_SCORE_M
        sta     ,x+
        lda     PRES_SCORE_L
        sta     ,x+
        ldu     #PRES_PENDING_NAME_ALIAS
        ldb     #7
highscore_commit_name_loop
        lda     ,u+
        sta     ,x+
        decb
        bne     highscore_commit_name_loop
        puls    a
        sta     PAR4
        puls    cc
highscore_commit_return
        rts

highscore_timer_records
        include "ladybug_presentation_timer_records.inc"

highscore_default_name_data
        fcb     PRESENTATION_HIGHSCORE_DEFAULT_NAME_0
        fcb     PRESENTATION_HIGHSCORE_DEFAULT_NAME_1
        fcb     PRESENTATION_HIGHSCORE_DEFAULT_NAME_2
        fcb     PRESENTATION_HIGHSCORE_DEFAULT_NAME_3
        fcb     PRESENTATION_HIGHSCORE_DEFAULT_NAME_4
        fcb     PRESENTATION_HIGHSCORE_DEFAULT_NAME_5
        fcb     PRESENTATION_HIGHSCORE_DEFAULT_NAME_6

        ifne    PRESENTATION_STAGE_PANEL_ENABLED
        include "ladybug_runtime_symbols.inc"

stage_select
        lda $24
        ldb PRES_SCREEN
        cmpb #PRESENTATION_MAP_ENTER_HIGH_SCORE
        beq stage_selected
        lda #1
        ldb $A7
        beq stage_selected
        lda $EB
        cmpb #2
        bne stage_selected
        lda $24
stage_selected
        sta PRES_TMP_H
        rts
        rmb     $B080-*
; BUG-035: called during hidden level-start hydration, before publication.
; Uses the existing page-$23 helper and resident vegetable sprite/blitter.
stage_panel_draw
        jmp menu_load_finish
stage_panel_slice_entry
        jmp stage_panel_slice
menu_scan_entry
        jmp menu_scan
menu_tick_entry
        jmp menu_tick
stage_panel_slice
        lbsr credit_panel_slice
        ldd $AA
        cmpd #960
        bne stage_panel_regular_slice
        lda PRES_SCREEN
        cmpa #PRESENTATION_MAP_HIGH_SCORE
        bne stage_panel_regular_slice
        clr PRES_NAME_TIMER_PHASE
        clr PRES_NAME_TIMER_BOX
        lbra highscore_logo_tile
stage_panel_regular_slice
        lda PRES_SCREEN
        cmpa #PRESENTATION_MAP_HIGH_SCORE
        lbeq ranking_schedule_tick
        lda PRES_SCREEN
        cmpa #PRESENTATION_MAP_LEVEL_START
        beq stage_name_schedule_ready
        cmpa #PRESENTATION_MAP_ENTER_HIGH_SCORE
        lbne stage_slice_return
        ldd $AA
        cmpd #576
        beq stage_name_schedule_ready
        cmpd #608
        bne stage_slice_return
stage_name_schedule_ready
        ldd $AA
        cmpd #128
        bne stage_score_row_done
        lbsr stage_player_score
stage_score_row_done
        ldd $AA
        leay stage_schedule,pcr
stage_schedule_find
        cmpd ,y
        beq stage_schedule_found
        leay 8,y
        cmpy #stage_schedule_end
        blo stage_schedule_find
        rts
stage_schedule_found
        leay 2,y
        lbsr stage_select
        ldx ,y
        lda 5,y
        sta $29
        lda 2,y
        cmpa #1
        beq stage_slice_part
        pshs x
        ldb 3,y
        stb PRES_TMP_M
        ldb 4,y
        stb PRES_TMP_L
        cmpa #4
        beq stage_slice_luck
        pshs a
        lda PRES_TMP_H
        bne stage_slice_nonzero
        inca
stage_slice_nonzero
        cmpa #18
        bls stage_slice_index
        lda #18
stage_slice_index
        deca
        ldb #20
        mul
        leay stage_panel_records,pcr
        leay d,y
        puls a
        cmpa #3
        bne stage_slice_offset
        leay 16,y
        bra stage_slice_offset
stage_slice_luck
        leay stage_panel_good_luck,pcr
stage_slice_offset
        ldb PRES_TMP_M
        leay b,y
        ldb PRES_TMP_L
        puls x
        lbra stage_panel_text
stage_slice_part
        lbra stage_panel_number
stage_slice_return
        rts
stage_panel_finish
        lda PRES_SCREEN
        cmpa #PRESENTATION_MAP_ENTER_HIGH_SCORE
        beq stage_name_sprite_selected
        cmpa #PRESENTATION_MAP_LEVEL_START
        bne stage_slice_return
        lbsr stage_select
stage_name_sprite_selected
        lda PRES_TMP_H
        bne stage_finish_nonzero
        inca
stage_finish_nonzero
        cmpa #18
        bls stage_finish_index
        lda #18
stage_finish_index
        deca
        ldb #64
        mul
        ldy #vegetable_sprites
        leay d,y
        pshs y
        lda PRES_SCREEN
        cmpa #PRESENTATION_MAP_ENTER_HIGH_SCORE
        beq stage_name_sprite_hud
        ldu #sprite_attr0_pairs
        ldx #$3E40
        jsr blit_packed_sprite
stage_name_sprite_hud
        puls y
        ldu #sprite_attr0_pairs
        ldx #$5C80
        jmp blit_packed_sprite
stage_schedule
        fdb 288
        fdb $3450
        fcb 1,0,3,TEXT_STAGE_PART
        fdb 320
        fdb $434C
        fcb 3,0,4,TEXT_STAGE_BONUS
        fdb 448
        fdb $4D30
        fcb 2,0,4,TEXT_STAGE_NAME
        fdb 480
        fdb $4D40
        fcb 2,4,4,TEXT_STAGE_NAME
        fdb 512
        fdb $4D50
        fcb 2,8,4,TEXT_STAGE_NAME
        fdb 544
        fdb $4D60
        fcb 2,12,4,TEXT_STAGE_NAME
        fdb 576
        fdb $5794
        fcb 1,0,3,TEXT_STAGE_PART
        fdb 608
        fdb $618C
        fcb 3,0,4,TEXT_STAGE_BONUS
        fdb 896
        fdb $8440
        fcb 4,0,3,TEXT_STAGE_GOOD_LUCK
        fdb 928
        fdb $844C
        fcb 4,3,3,TEXT_STAGE_GOOD_LUCK
        fdb 960
        fdb $8458
        fcb 4,6,3,TEXT_STAGE_GOOD_LUCK
stage_schedule_end

stage_panel_number
        lda     PRES_TMP_H
        bne     spn_nonzero
        inca
spn_nonzero
        clrb
spn_hundreds
        cmpa    #100
        blo     spn_hundreds_done
        suba    #100
        incb
        bra     spn_hundreds
spn_hundreds_done
        sta     PRES_TMP_M
        stb     PRES_NAME_REPEAT
        tfr     b,a
        tsta
        bne     spn_hundreds_write
        lda     #36
spn_hundreds_write
        lbsr    stage_panel_char
spn_tens_begin
        lda     PRES_TMP_M
        clrb
spn_tens
        cmpa    #10
        blo     spn_tens_done
        suba    #10
        incb
        bra     spn_tens
spn_tens_done
        sta     PRES_TMP_M
spn_write_tens
        tfr     b,a
        lbsr    stage_panel_char
spn_units
        lda     PRES_TMP_M
        lbra    stage_panel_char

stage_panel_text
        lda     ,y+
        lbsr    stage_panel_char
        decb
        bne     stage_panel_text
        rts

; DOC-002 source-contract mirror contract stage_player_score profile=presentation: Draw zero for a fresh game or current packed-BCD score during hidden level-start hydration.
stage_player_score
        lda #8
        sta $29
        ldx #$2A84
        ldy #$001D
        ldb #3
stage_player_score_pair
        lda ,y+
        pshs a
        lda $A7
        cmpa #2
        puls a
        beq stage_player_score_actual
        clra
stage_player_score_actual
        pshs a
        lsra
        lsra
        lsra
        lsra
        lbsr stage_panel_char
        puls a
        anda #15
        lbsr stage_panel_char
        decb
        bne stage_player_score_pair
        rts

; A=0..44 authored glyph, X=destination, $29=colour; advance X.
stage_panel_char
        pshs a,b,x,y,u
        leay stage_source_glyphs,pcr
        lda a,y
        jsr PRES_MAIN_SHARED_MASK
        puls a,b,x,y,u
        leax 4,x
        rts
        include "ladybug_stage_glyphs.inc"

stage_panel_good_luck
        fcb     16,24,24,13,36,21,30,12,20
        include "ladybug_stage_panel.inc"
        endc
ranking_schedule_tick
        ldd $AA
        leau ranking_schedule_data,pcr
ranking_schedule_find
        cmpd ,u
        beq ranking_schedule_found
        leau 7,u
        cmpu #ranking_schedule_end
        blo ranking_schedule_find
        rts
ranking_schedule_found
        ldx 2,u
        ldy 4,u
        ldb 6,u
        jmp PRES_RANKING_SLICE
ranking_schedule_data
        fdb 128,$AF84,$2A40
        fcb 1
        fdb 160,$AF84,$2A6C
        fcb 0
        fdb 192,$AF8E,$3440
        fcb 1
        fdb 224,$AF8E,$346C
        fcb 0
        fdb 256,$AF98,$3940
        fcb 1
        fdb 288,$AF98,$396C
        fcb 0
        fdb 320,$AFA2,$3E40
        fcb 1
        fdb 352,$AFA2,$3E6C
        fcb 0
        fdb 384,$AFAC,$4340
        fcb 1
        fdb 416,$AFAC,$436C
        fcb 0
        fdb 448,$AFB6,$4840
        fcb 1
        fdb 480,$AFB6,$486C
        fcb 0
        fdb 512,$AFC0,$4D40
        fcb 1
        fdb 544,$AFC0,$4D6C
        fcb 0
        fdb 576,$AFCA,$5240
        fcb 1
        fdb 608,$AFCA,$526C
        fcb 0
        fdb 704,$AFD4,$5740
        fcb 1
        fdb 736,$AFD4,$576C
        fcb 0
ranking_schedule_end

; BUG-052: redraw only the twelve authored phase-changing logo tiles.
highscore_logo_tick
        lda     PRES_SCREEN
        cmpa    #PRESENTATION_MAP_ATTRACT
        beq     highscore_logo_vbord
        ldd     PRES_TIMER
        addd    #1
        std     PRES_TIMER
highscore_logo_vbord
        lbsr    logo_vbord_clock
        sta     PRES_NAME_TIMER_PHASE
        tst     FB_PENDING
        bne     highscore_logo_hold
        ldb     PRES_NAME_TIMER_PHASE
        ; D3 remains exclusively the decorative actor phase. D2 is logo A;
        ; E3 is logo B only on attract/menu, and is initialized as cursor owner
        ; by update_name_frame before name-phase use. No new DP allocation.
        ldx     #$D2
        lda     FB_BACK_ID
        beq     highscore_logo_cache_ready
        ldx     #PRES_NAME_OWNER
highscore_logo_cache_ready
        cmpb    ,x
        beq     highscore_logo_hold
        stb     ,x
        ldd     #highscore_logo_prepared
        std     PRES_NAME_PTR
        ldd     #PRES_MAIN_PAGE23_RESUME
        pshs    d
        ; Attract owns the instruction overlay, so its high-score low-RAM
        ; callback addresses are invalid. Reuse the existing bank-return tail
        ; and stacked resident continuation; no low-RAM code allocation.
        ldd     #PRES_MAIN_FB_PREPARE
        pshs    cc,d
        orcc    #$50
        jmp     PRES_GAME_PAGE_RETURN
highscore_logo_prepared
        clr     PRES_NAME_TIMER_BOX
highscore_logo_tile
        lda     PRES_NAME_TIMER_BOX
        ldb     #4
        mul
        leax    highscore_logo_records,pcr
        leax    d,x
        ldy     ,x
        lda     PRES_SCREEN
        cmpa    #PRESENTATION_MAP_ATTRACT
        bne     highscore_logo_record_source
        tfr     y,d
        subd    #$1E00
        tfr     d,y
highscore_logo_record_source
        ldd     2,x
        tst     PRES_NAME_TIMER_PHASE
        beq     highscore_logo_source
        addd    #32
highscore_logo_source
        tfr     d,u
        ldd     #highscore_logo_drawn
        std     PRES_NAME_PTR
        ldd     #PRES_MAIN_PAGE23_RESUME
        pshs    d
        tfr     u,d
        jmp     PRES_MODULE_DRAW_RAW_TILE
highscore_logo_drawn
        inc     PRES_NAME_TIMER_BOX
        lda     PRES_NAME_TIMER_BOX
        cmpa    #12
        blo     highscore_logo_tile
        lda     PRES_MODE
        cmpa    #MODE_LOAD
        beq     highscore_logo_loaded
        ldd     #highscore_logo_hold
        std     PRES_NAME_PTR
        ldd     #PRES_MAIN_PAGE23_RESUME
        pshs    d
        ; Attract owns the instruction overlay, so its high-score low-RAM
        ; callback addresses are invalid. Reuse the existing bank-return tail
        ; and stacked resident continuation; no low-RAM code allocation.
        ldd     #PRES_MAIN_FB_FINISH
        pshs    cc,d
        orcc    #$50
        jmp     PRES_GAME_PAGE_RETURN
highscore_logo_hold
        lda     #1
highscore_logo_loaded
        rts
highscore_logo_records
        include "ladybug_highscore_logo.inc"

; BUG-043: publish the authoritative count after its row has been loaded.
credit_panel_slice
        ldd     $AA
        cmpd    #832
        beq     credit_panel_count
        cmpd    #960
        bne     credit_panel_done
        lda     PRES_SCREEN
        cmpa    #PRESENTATION_MAP_HIGH_SCORE
        bne     credit_panel_done
        lda     $A8
        cmpa    #2
        blo     credit_panel_done
        ldx     #$9328
        leay    credit_panel_two_prompt,pcr
        ldb     #20
credit_panel_prompt_loop
        lda     #5
        sta     $29
        lda     ,y+
        cmpa    #2
        bhi     credit_panel_prompt_char
        pshs    a
        lda     #8
        sta     $29
        puls    a
credit_panel_prompt_char
        lbsr    stage_panel_char
        decb
        bne     credit_panel_prompt_loop
credit_panel_done
        rts
credit_panel_count
        lda     PRES_SCREEN
        beq     credit_panel_done
        cmpa    #PRESENTATION_MAP_OPTIONS
        bhs     credit_panel_done
        cmpa    #PRESENTATION_MAP_HIGH_SCORE
        beq     credit_panel_done
        lda     #6
        sta     $29
        ldx     #$4884
        leay    credit_panel_label,pcr
        ldb     #6
        lbsr    stage_panel_text
        ldx     #$4D88
        lda     #36
        lbsr    stage_panel_char
        ldx     #$4D84
        lda     $A8
        cmpa    #10
        blo     credit_panel_unit
        suba    #10
        pshs    a
        lda     #1
        lbsr    stage_panel_char
        puls    a
credit_panel_unit
        lbsr    stage_panel_char
        lbra    top_panel_draw
credit_panel_label
        fcb 12,27,14,13,18,29
credit_panel_two_prompt
        fcb 1,36,24,27,36,2,36,25,21,10,34,14,27,36,11,30,29,29,24,23

; Publish record zero at TOP on instruction and level-start surfaces.
top_panel_draw
        lda     PRES_SCREEN
        cmpa    #PRESENTATION_MAP_GAME_OVER
        beq     top_panel_publish
        deca
        cmpa    #1
        bhi     top_panel_done
top_panel_publish
        jmp     PRES_MAIN_TOP_HUD
top_panel_done
        rts

; FEAT-005: existing page-$23 owner handles menus. State is direct-page;
; drawing uses the established resident font without remapping PAR5.
MENU_LIVES equ $EA
MENU_LEVEL equ $EB
MENU_SELECT equ $E0
MENU_PREV equ $DF
MENU_EVENT equ $D0
; Menu HOLD only: owner A/B dirty bits. Name entry owns this as repeat state.
MENU_DIRTY equ $E1

menu_scan
        ldb #0
        jmp PRES_MAIN_KEY_SERVICE

menu_tick
        lda     PRES_SCREEN
        cmpa    #8
        bne     menu_original_tick
        ldb     #2
        jsr     PRES_MAIN_KEY_SERVICE
        cmpb    #$FF
        lbeq    menu_idle
        tfr     b,a
        lbra    menu_change
menu_original_tick
        lda     MENU_EVENT
        lbeq    menu_idle
        bita    #32
        lbne    menu_back
        ldb     PRES_SCREEN
        cmpb    #PRESENTATION_MAP_CREDITS
        bne     menu_interactive
        bita    #16
        lbne    menu_back
        lbra    menu_hold
menu_interactive
        bita    #16
        bne     menu_enter
        ; Opposing held inputs cancel, including a newly pressed opposite.
        ldb     MENU_PREV
        andb    #3
        cmpb    #3
        beq     menu_horizontal
        bita    #1
        bne     menu_up
        bita    #2
        bne     menu_down
menu_horizontal
        ldb     PRES_SCREEN
        cmpb    #PRESENTATION_MAP_OPTIONS
        lbne    menu_idle
        ldb     MENU_SELECT
        cmpb    #2
        lbhs    menu_idle
        ldx     #MENU_LIVES
        abx
        ldb     MENU_PREV
        andb    #12
        cmpb    #12
        lbeq    menu_idle
        bita    #4
        bne     menu_decrease
        bita    #8
        beq     menu_idle
        lda     #12
        tst     MENU_SELECT
        beq     menu_maximum
        lda     #99
menu_maximum
        cmpa    ,x
        bls     menu_idle
        inc     ,x
        bra     menu_redraw
menu_decrease
        lda     ,x
        cmpa    #1
        bls     menu_idle
        dec     ,x
        bra     menu_redraw
menu_up
        tst     MENU_SELECT
        beq     menu_idle
        dec     MENU_SELECT
        bra     menu_redraw
menu_down
        ldb     #2
        lda     PRES_SCREEN
        cmpa    #PRESENTATION_MAP_HIGH_SCORE
        beq     menu_last
        ldb     #3
menu_last
        cmpb    MENU_SELECT
        bls     menu_idle
        inc     MENU_SELECT
menu_redraw
        lda     #3
        sta     MENU_DIRTY
        bra     menu_idle
menu_enter
        cmpb    #PRESENTATION_MAP_HIGH_SCORE
        bne     menu_enter_option
        lda     MENU_SELECT
        bne     menu_high_nonstart
        ; Start is available only from this row and consumes one real credit.
        tst     $A8
        beq     menu_idle
        dec     $A8
        lda     #1
        sta     $A7
        lda     #PRESENTATION_MAP_LEVEL_START
        bra     menu_change
menu_high_nonstart
        cmpa    #1
        bne     menu_high_credits
        lda     #PRESENTATION_MAP_OPTIONS
        bra     menu_change
menu_high_credits
        lda     #PRESENTATION_MAP_CREDITS
        bra     menu_change
menu_enter_option
        lda     MENU_SELECT
        cmpa    #2
        bne     menu_enter_back
        lda     #8
        bra     menu_change
menu_enter_back
        cmpa    #3
        bne     menu_idle
menu_back
        lda     #PRESENTATION_MAP_HIGH_SCORE
menu_change
        clr     MENU_SELECT
menu_start
        pshs    a
        ldd     #menu_hold
        std     PRES_NAME_PTR
        puls    a
        ldx     #PRES_MAIN_PAGE23_RESUME
        pshs    x
        jmp     PRES_MODULE_START_SCREEN
menu_idle
        ; Loading still accepts input, but cannot publish a field transaction.
        lda     PRES_MODE
        cmpa    #5
        bne     menu_hold
        tst     MENU_DIRTY
        beq     menu_idle_logo
        tst     FB_PENDING
        bne     menu_hold
        lda     FB_BACK_ID
        inca                    ; owner 0 -> bit 1, owner 1 -> bit 2
        anda    MENU_DIRTY
        beq     menu_hold
        ldd     #menu_updated
        std     PRES_NAME_PTR
        ldd     #PRES_MAIN_PAGE23_RESUME
        pshs    d
        jmp     PRES_HIGHSCORE_FB_PREPARE
menu_updated
        ; Existing callback restored page $23 after preparing game-page state.
        lbsr    menu_load_finish
        lda     FB_BACK_ID
        inca
        coma
        anda    MENU_DIRTY
        sta     MENU_DIRTY
        ldd     #menu_hold
        std     PRES_NAME_PTR
        ldd     #PRES_MAIN_PAGE23_RESUME
        pshs    d
        jmp     PRES_HIGHSCORE_FB_FINISH
menu_idle_logo
        lda     PRES_SCREEN
        cmpa    #PRESENTATION_MAP_HIGH_SCORE
        lbeq    highscore_logo_tick
menu_hold
        lda     #1
        rts

menu_load_finish
        lda     PRES_SCREEN
        cmpa    #8
        bne     menu_load_original
        ldb     #1
        jmp     PRES_MAIN_KEY_SERVICE
menu_load_original
        lda     PRES_SCREEN
        cmpa    #PRESENTATION_MAP_HIGH_SCORE
        beq     menu_paint_high
        cmpa    #PRESENTATION_MAP_OPTIONS
        lbeq    menu_paint_options
        cmpa    #PRESENTATION_MAP_CREDITS
        beq     menu_paint_credits
        jmp     stage_panel_finish
menu_paint_high
        leay    menu_high_score_rows,pcr
        ldb     #3
        lbsr    menu_paint_rows
        tst     $A8
        bne     menu_high_paint_done
        lda     #7
        tst     MENU_SELECT
        bne     menu_high_add_colour
        lda     #10
menu_high_add_colour
        sta     $29
        leay    menu_high_score_add_credits,pcr
        ldx     ,y++
        ldb     ,y+
        lbsr    stage_panel_text
menu_high_paint_done
        rts
menu_paint_credits
        lda     #10
        sta     $29
        leay    menu_credit_back,pcr
        ldx     ,y++
        ldb     ,y+
        lbra    stage_panel_text
menu_paint_rows
        pshs    b
        clr     $D1
menu_label_row
        lda     #7
        ldb     $D1
        cmpb    MENU_SELECT
        bne     menu_label_colour
        lda     #10
menu_label_colour
        sta     $29
        ldx     ,y++
        ldb     ,y+
        lbsr    stage_panel_text
        inc     $D1
        lda     $D1
        cmpa    ,s
        blo     menu_label_row
        puls    b,pc
menu_paint_options
        leay    menu_option_rows,pcr
        ldb     #4
        lbsr    menu_paint_rows
        leay    menu_options_pairs,pcr
        clr     $D1
menu_value_row
        ldb     $D1
        lda     #7
        cmpb    MENU_SELECT
        bne     menu_value_colour
        lda     #10
menu_value_colour
        sta     $29
        ldx     ,y
        leax    4,x
        ldu     #MENU_LIVES
        lda     b,u
        clrb
menu_tens
        cmpa    #10
        blo     menu_digits
        suba    #10
        incb
        bra     menu_tens
menu_digits
        pshs    a
        tfr     b,a
        lbsr    stage_panel_char
        puls    a
        lbsr    stage_panel_char
        lda     $D1
        cmpa    MENU_SELECT
        bne     menu_value_next
        lda     #43
        ldx     ,y
        lbsr    stage_panel_char
        lda     #44
        ldx     2,y
        lbsr    stage_panel_char
menu_value_next
        leay    4,y
        inc     $D1
        lda     $D1
        cmpa    #2
        blo     menu_value_row
        rts
        include "ladybug_menu_records.inc"
highscore_phase_helper_end

        else

        org $0300

demo_runtime_tick
        ifne    HIGHSCORE_TEST_PROFILE
        lda     PRES_MODE
        cmpa    #MODE_NAME
        lbeq    highscore_name_tick
        cmpa    #MODE_GAMEOVER
        ifne    COMPLETE_PHASE_AUX
        lbeq    highscore_name_tick
        else
        lbeq    prepare_name
        endc
        lda     PRES_SCREEN
        cmpa    #MAP_ENTER_HIGH_SCORE
        lbeq    render_name_screen
        cmpa    #MAP_HIGH_SCORE
        lbeq    render_high_score
        else
        tst     PLAYER_MANUAL
        beq     demo_route_wait_entrance
        lda     PRES_DEMO_DIR
        sta     JOY_DIR
        sta     PLAYER_WANT
demo_route_reasserted
        cmpa    #$FF
        beq     demo_route_aligned
        sta     PLAYER_FACE
        bra     demo_route_aligned
demo_route_wait_entrance
        tst     PLAYER_STEP
        bne     demo_route_done
        lda     PLAYER_CELL_X
        cmpa    #12
        bne     demo_route_done
        lda     PLAYER_CELL_Y
        cmpa    #18
        bne     demo_route_done
        lda     #1
        sta     PLAYER_MANUAL
demo_route_aligned
        tst     PLAYER_STEP
        bne     demo_route_done
        lda     PLAYER_CELL_X
        bita    #1
        bne     demo_route_done
        cmpa    PRES_DEMO_LAST_X
        bne     demo_route_new_cell
        lda     PLAYER_CELL_Y
        bita    #1
        bne     demo_route_done
        cmpa    PRES_DEMO_LAST_Y
        beq     demo_route_done
demo_route_new_cell
        lda     PLAYER_CELL_Y
        bita    #1
        bne     demo_route_done
        ldb     PRES_DEMO_ROUTE
        cmpb    #PRESENTATION_DEMO_ROUTE_ACTIONS
        bhs     demo_route_hold
        clra
        addd    #PRESENTATION_DEMO_ROUTE_OFFSET
        tfr     d,x
        tfr     a,b
        andb    #$E0
        lsrb
        lsrb
        lsrb
        lsrb
        lsrb
        addb    #PRESENTATION_COLD_PAGE
        stb     PAR5
        tfr     x,d
        anda    #$1F
        adda    #$A0
        tfr     d,x
        lda     ,x
        pshs    a
        lda     #$34
        sta     PAR5
        puls    a
        sta     PRES_DEMO_DIR
        lda     PLAYER_CELL_X
        sta     PRES_DEMO_LAST_X
        lda     PLAYER_CELL_Y
        sta     PRES_DEMO_LAST_Y
        lda     PRES_DEMO_DIR
        sta     JOY_DIR
        sta     PLAYER_WANT
        sta     PLAYER_FACE
demo_route_advance
        inc     PRES_DEMO_ROUTE
demo_route_advanced
demo_route_done
        rts
demo_route_hold
        lda     #$FF
        sta     PRES_DEMO_DIR
        sta     JOY_DIR
        sta     PLAYER_WANT
demo_route_held
        rts
        endc
        ifne    HIGHSCORE_TEST_PROFILE
demo_runtime_done
        rts
init_scores
        lda     #$34
        sta     PAR5
        tst     PRES_HS_READY
        bne     init_scores_done
        ldu     #PRES_HIGHSCORE_BASE
        lda     #9
init_scores_row
        sta     ,u+
        clr     ,u+
        clr     ,u+
        pshs    a
        ldx     #highscore_default_name_data
        ldy     #7
init_scores_name
        lda     ,x+
        sta     ,u+
        leay    -1,y
        bne     init_scores_name
        puls    a
        deca
        bne     init_scores_row
        inc     PRES_HS_READY
init_scores_done
        rts

highscore_name_tick
        lda     PRES_HOLD_STATE
        cmpa    #PRES_HOLD_FINAL
        bne     highscore_name_ready
        tst     FB_PENDING
        bne     highscore_name_hold
        clr     PRES_HOLD_STATE
highscore_name_ready
        lda     #$23
        sta     PAR5
        jsr     HIGHSCORE_PHASE_HELPER_ADDRESS
        pshs    a
        lda     #$34
        sta     PAR5
        puls    a
        tsta
        bne     demo_runtime_done
        lda     PRES_MODE
        cmpa    #MODE_GAMEOVER
        beq     highscore_name_hold
        lbsr    name_tick
        lda     #1
        rts
highscore_name_hold
        lda     #1
        rts

        ifeq    COMPLETE_PHASE_AUX
prepare_name
        bsr     init_scores
        clr     PRES_NAME_FLAGS
        clr     PRES_TICK_PHASE
        clr     PRES_NAME_TIMER_PHASE
        clr     PRES_NAME_TIMER_BOX
        ldd     $001D           ; actual packed-BCD gameplay score
        std     PRES_SCORE_H
        lda     $001F
        sta     PRES_SCORE_L
        lda     #$FF
        sta     PRES_INSERT
        ldx     #PRES_HIGHSCORE_ALIAS
        clrb
highscore_qualify_loop
        lda     PRES_SCORE_H
        cmpa    ,x
        bhi     highscore_qualify_found
        blo     highscore_qualify_next
        lda     PRES_SCORE_M
        cmpa    1,x
        bhi     highscore_qualify_found
        blo     highscore_qualify_next
        lda     PRES_SCORE_L
        cmpa    2,x
        bhi     highscore_qualify_found
highscore_qualify_next
        leax    10,x
        incb
        cmpb    #9
        blo     highscore_qualify_loop
        bra     highscore_qualify_done
highscore_qualify_found
        stb     PRES_INSERT
highscore_qualify_done
        clr     PRES_NAME_LEN
        lda     #9
        sta     PRES_NAME_ROW
        lda     #2
        sta     PRES_NAME_COL
        lda     #DIR_NONE
        sta     PLAYER_DIR
        sta     PLAYER_WANT
        lda     #DIR_N
        sta     PLAYER_FACE
        clr     PLAYER_ANIM
        lda     #8
        sta     PLAYER_ANIM_TIMER
        lda     #19
        sta     PLAYER_CELL_X
        sta     PRES_NAME_COL
        lda     #22
        sta     PLAYER_CELL_Y
        sta     PRES_NAME_ROW
        ldx     #PRES_PENDING_NAME
        lda     #PRES_HS_BLACK
        ldb     #PRESENTATION_HIGHSCORE_NAME_BYTES
prepare_name_blank
        sta     ,x+
        decb
        bne     prepare_name_blank
        rts
        endc

        ifne    0
qualify_score
        lbsr    init_scores
        lda     #$FF
        sta     PRES_INSERT
        ldx     #PRES_HIGHSCORE_BASE
        clrb
qualify_loop
        lda     PRES_SCORE_H
        cmpa    ,x
        bhi     qualify_found
        blo     qualify_next
        lda     PRES_SCORE_M
        cmpa    1,x
        bhi     qualify_found
        blo     qualify_next
        lda     PRES_SCORE_L
        cmpa    2,x
        bhi     qualify_found
qualify_next
        leax    10,x
        incb
        cmpb    #9
        blo     qualify_loop
        rts
qualify_found
        stb     PRES_INSERT
        rts
        endc
name_tick
        dec     PLAYER_ANIM_TIMER
        bne     name_animation_ready
        lda     #8
        sta     PLAYER_ANIM_TIMER
        inc     PLAYER_ANIM
        lda     PLAYER_ANIM
        anda    #3
        sta     PLAYER_ANIM
name_animation_ready
        jsr     PRES_MAIN_READ_JOY
name_joy_ready
        lda     JOY_DIR
        cmpa    #DIR_NONE
        beq     name_idle
        sta     PLAYER_WANT
        lda     FRAMES+1
        lsra
        bcs     name_idle
        ldx     #name_can_move
        jsr     PRES_MAIN_NAME_LATE_TURN
        tsta
        bne     name_idle
        tst     PRES_NAME_STEPS
        beq     name_move_start
        lda     PLAYER_WANT
        eora    #2
        cmpa    PLAYER_DIR
        bne     name_move_active
        ; Reverse relative to the old target, preserving the physical position.
        lda     #4
        suba    PRES_NAME_STEPS
        sta     PRES_NAME_STEPS
        lda     PLAYER_DIR
        beq     name_reverse_n
        cmpa    #DIR_E
        beq     name_reverse_e
        cmpa    #DIR_S
        beq     name_reverse_s
        dec     PLAYER_CELL_X
        dec     PRES_NAME_COL
        bra     name_reverse_done
name_reverse_n
        dec     PLAYER_CELL_Y
        dec     PRES_NAME_ROW
        bra     name_reverse_done
name_reverse_e
        inc     PLAYER_CELL_X
        inc     PRES_NAME_COL
        bra     name_reverse_done
name_reverse_s
        inc     PLAYER_CELL_Y
        inc     PRES_NAME_ROW
name_reverse_done
        lda     PLAYER_WANT
        sta     PLAYER_DIR
        sta     PLAYER_FACE
        bra     name_move_active
name_move_start
        lda     PLAYER_WANT
        cmpa    #DIR_NONE
        beq     name_idle
        bsr     name_can_move
        beq     name_idle
        lda     PLAYER_WANT
        sta     PLAYER_DIR
        sta     PLAYER_FACE
        lda     #4
        sta     PRES_NAME_STEPS
name_move_active
        bsr     name_advance
        rts
name_idle
        lbsr    update_name_frame
name_idle_done
        clra
        rts

name_advance
        ldx     PLAYER_FB
        lda     PLAYER_DIR
        cmpa    #DIR_N
        beq     name_step_n
        cmpa    #DIR_E
        beq     name_step_e
        cmpa    #DIR_S
        beq     name_step_s
        leax    -1,x
        bra     name_step_store
name_step_n
        leax    -320,x
        bra     name_step_store
name_step_e
        leax    1,x
        bra     name_step_store
name_step_s
        leax    320,x
name_step_store
        stx     PLAYER_FB
        dec     PRES_NAME_STEPS
        bne     name_cursor_redraw
        lda     PLAYER_DIR
        cmpa    #DIR_N
        bne     move_s
        dec     PRES_NAME_ROW
        dec     PLAYER_CELL_Y
        bra     move_node
move_s
        cmpa    #DIR_S
        bne     move_w
        inc     PRES_NAME_ROW
        inc     PLAYER_CELL_Y
        bra     move_node
move_w
        cmpa    #DIR_W
        bne     move_e
        dec     PRES_NAME_COL
        dec     PLAYER_CELL_X
        bra     move_node
move_e
        inc     PRES_NAME_COL
        inc     PLAYER_CELL_X
        bra     move_node
name_cursor_redraw
        lbsr    update_name_frame
        clra
        rts
move_node
        bsr     name_cell_arrival
        tsta
        bne     move_end
        lbsr    update_name_frame
        clra
        rts
move_end
        lbsr    update_name_frame
        lda     #1
        rts

name_can_move
        sta     PRES_NAME_TILE
        lda     PLAYER_CELL_Y
        ldb     #24
        mul
        addb    PLAYER_CELL_X
        adca    #0
        subd    #8
        addd    #PRESENTATION_NAME_ENTRY_FULL_EDGE_MASK_TABLE
        jsr     PRES_MODULE_COLD_PTR
        ldb     ,x
        lda     #$34
        sta     PAR5
        lda     PRES_NAME_TILE
        cmpa    #DIR_N
        beq     name_can_n
        cmpa    #DIR_E
        beq     name_can_e
        cmpa    #DIR_S
        beq     name_can_s
        bitb    #8
        bra     name_can_result
name_can_n
        bitb    #1
        bra     name_can_result
name_can_e
        bitb    #2
        bra     name_can_result
name_can_s
        bitb    #4
name_can_result
        beq     name_can_blocked
        lda     #1
        rts
name_can_blocked
        clra
        rts

name_cell_arrival
        ldd     #PRESENTATION_NAME_ENTRY_ACTION_TABLE
        jsr     PRES_MODULE_COLD_PTR
        ldb     #PRESENTATION_NAME_ENTRY_ACTION_BYTES/3
name_action_loop
        ; The generated action table is local to the 24-cell maze window;
        ; player coordinates remain screen-space columns 8..31.
        lda     PLAYER_CELL_X
        suba    #8
        cmpa    ,x
        bne     name_action_next
        lda     PLAYER_CELL_Y
        cmpa    1,x
        bne     name_action_next
        lda     2,x
        sta     PRES_NAME_TILE
        cmpa    #PRES_NAME_END
        beq     name_action_end
        lda     #$34
        sta     PAR5
        lda     PRES_NAME_TILE
        cmpa    #PRES_NAME_CL
        beq     name_action_cl
        lda     PRES_NAME_LEN
        cmpa    #7
        bhs     name_action_done
        tfr     a,b
        ldx     #PRES_PENDING_NAME
        abx
        lda     PRES_NAME_TILE
        sta     ,x
        inc     PRES_NAME_LEN
        bra     name_action_done
name_action_cl
        tst     PRES_NAME_LEN
        beq     name_action_done
        dec     PRES_NAME_LEN
        ldx     #PRES_PENDING_NAME
        lda     PRES_NAME_LEN
        tfr     a,b
        abx
        ldb     #PRES_HS_BLACK
        stb     ,x
name_action_done
        clra
        rts
name_action_next
        leax    3,x
        decb
        bne     name_action_loop
        clra
        rts
name_action_end
        inc     PRES_NAME_FLAGS
        clra
        rts

        ifne    0
commit_name
        lda     PRES_INSERT
        cmpa    #$FF
        beq     commit_done
        sta     PRES_TMP_H
        ldx     #PRES_HIGHSCORE_BASE+70
        ldu     #PRES_HIGHSCORE_BASE+80
commit_shift
        lda     PRES_TMP_H
        cmpa    PRES_INSERT
        blo     commit_write
        ldb     #10
commit_record
        lda     ,x+
        sta     ,u+
        decb
        bne     commit_record
        leax    -20,x
        leau    -20,u
        dec     PRES_TMP_H
        bra     commit_shift
commit_write
        ldx     #PRES_HIGHSCORE_BASE
        ldb     PRES_INSERT
commit_find
        beq     commit_score
        leax    10,x
        decb
        bra     commit_find
commit_score
        lda     PRES_SCORE_H
        sta     ,x+
        lda     PRES_SCORE_M
        sta     ,x+
        lda     PRES_SCORE_L
        sta     ,x+
        ldu     #PRES_PENDING_NAME
        ldb     #7
commit_name_loop
        lda     ,u+
        sta     ,x+
        decb
        bne     commit_name_loop
commit_done
        rts
        endc
render_name_screen
        clr     PRES_NAME_STEPS
        ifeq    COMPLETE_PHASE_AUX
        lbsr    prepare_name
        endc
        jsr     PRES_MODULE_MAP_BACK
        bsr     draw_name_fields
        bsr     draw_entry_scores
        lbsr    capture_initial
        lbsr    draw_cursor
        rts

draw_name_fields
        ldx     #PRES_PENDING_NAME
        ldy     #PRESENTATION_NAME_ENTRY_NAME_DST
        lbsr    draw_record_name
        lda     PRES_INSERT
        bne     entry_name_top_old
        ldx     #PRES_PENDING_NAME
        bra     entry_name_top_draw
entry_name_top_old
        ldx     #PRES_HIGHSCORE_BASE+3
entry_name_top_draw
        ldy     #PRESENTATION_NAME_ENTRY_TOP_NAME_DST
        lbsr    draw_record_name
draw_name_done
        rts

draw_entry_scores
        ldx     #PRES_SCORE_H
        ldy     #PRESENTATION_NAME_ENTRY_SCORE_DST
        lbsr    draw_score
        lda     PRES_INSERT
        bne     entry_top_old
        ldx     #PRES_SCORE_H
        bra     entry_top_right
entry_top_old
        ldx     #PRES_HIGHSCORE_BASE
entry_top_right
        ldy     #PRESENTATION_NAME_ENTRY_TOP_RIGHT_DST
        bsr     draw_score
        lda     PRES_INSERT
        bne     entry_top_left_old
        ldx     #PRES_SCORE_H
        bra     entry_top_left
entry_top_left_old
        ldx     #PRES_HIGHSCORE_BASE
entry_top_left
        ldy     #PRESENTATION_NAME_ENTRY_TOP_DST
        lbsr    draw_score
        rts

render_high_score
        jsr     PRES_MODULE_MAP_BACK
        lbsr    init_scores
        bsr     draw_high_score_screen
        rts

draw_high_score_screen
        ldx     #PRES_HIGHSCORE_BASE
        ldu     #PRESENTATION_HIGHSCORE_TOP_NAME_DST
        bsr     draw_high_score_entry
        leau    PRESENTATION_HIGHSCORE_ENTRY_NAME_DST-PRESENTATION_HIGHSCORE_TOP_NAME_DST,u
        ldb     #PRESENTATION_HIGHSCORE_COUNT-1
draw_high_score_rows
        pshs    b
        bsr     draw_high_score_entry
        puls    b
        leau    1280,u
        decb
        bne     draw_high_score_rows
        rts

draw_high_score_entry
        stx     PRES_NAME_PTR
        pshs    u
        tfr     u,y
        ldx     PRES_NAME_PTR
        leax    3,x
        bsr     draw_record_name
        puls    u
        pshs    u
        tfr     u,y
        leay    PRESENTATION_HIGHSCORE_TOP_SCORE_DST-PRESENTATION_HIGHSCORE_TOP_NAME_DST,y
        ldx     PRES_NAME_PTR
        bsr     draw_score
        puls    u
        leax    7,x
        rts

draw_record_name
        ldb     #PRESENTATION_HIGHSCORE_NAME_BYTES
record_name_loop
        lda     #$34
        sta     PAR5
        lda     ,x+
        pshs    b,x,y
        tsta
        bne     record_name_tile
        ldb     #PRES_HS_BLACK
        bra     record_name_draw
record_name_tile
        tfr     a,b
record_name_draw
        jsr     PRES_MODULE_DRAW_TILE
        puls    b,x,y
        leay    4,y
        decb
        bne     record_name_loop
        rts

draw_score
        lda     #3
        sta     PRES_TMP_H
score_byte
        lda     #$34
        sta     PAR5
        lda     ,x+
        sta     PRES_TMP_L
        lsra
        lsra
        lsra
        lsra
        anda    #$0F
        bsr     draw_digit
        lda     PRES_TMP_L
        anda    #$0F
        bsr     draw_digit
        dec     PRES_TMP_H
        bne     score_byte
        rts
draw_digit
        tfr     a,b
        ldu     #score_glyphs
        leau    b,u
        ldb     ,u
        pshs    x,y
        jsr     PRES_MODULE_DRAW_TILE
        puls    x,y
        leay    4,y
        rts

capture_initial
        lda     #$34
        sta     PAR5
        ldx     #PRESENTATION_NAME_ENTRY_CURSOR_DST
        stx     PLAYER_FB
        stx     PRES_NAME_PTR_A
        stx     PRES_NAME_PTR_B
        ldu     #PRES_CURSOR_SAVE_A
        bsr     capture_cursor
        ldx     #PRES_CURSOR_SAVE_A
        ldu     #PRES_CURSOR_SAVE_B
        ldy     #64
capture_copy
        ldd     ,x++
        std     ,u++
        leay    -1,y
        bne     capture_copy
        rts

update_name_frame
        lda     FB_BACK_ID
        sta     PRES_NAME_OWNER
        lda     #$34
        sta     PAR5
        jsr     PRES_MAIN_FB_PREPARE
        jsr     PRES_MODULE_MAP_BACK
        bsr     restore_cursor
        lbsr    draw_name_fields
        bsr     capture_owner
        bsr     draw_cursor
        lda     #$34
        sta     PAR5
        jmp     PRES_MAIN_FB_FINISH

capture_cursor
        ldy     #16
capture_row
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
        bne     capture_row
        rts

restore_cursor
        lda     #$34
        sta     PAR5
        lda     PRES_NAME_OWNER
        beq     restore_a
        ldu     #PRES_CURSOR_SAVE_B
        ldx     PRES_NAME_PTR_B
        bra     restore_ready
restore_a
        ldu     #PRES_CURSOR_SAVE_A
        ldx     PRES_NAME_PTR_A
restore_ready
        ldy     #16
restore_row
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
        bne     restore_row
        rts

capture_owner
        lda     #$34
        sta     PAR5
        lda     PRES_NAME_OWNER
        beq     capture_a
        ldu     #PRES_CURSOR_SAVE_B
        ldx     PLAYER_FB
        stx     PRES_NAME_PTR_B
        bsr     capture_cursor
        rts
capture_a
        ldu     #PRES_CURSOR_SAVE_A
        ldx     PLAYER_FB
        stx     PRES_NAME_PTR_A
        bsr     capture_cursor
        rts

draw_cursor
        ldx     PLAYER_FB
        jmp     PRES_MAIN_PLAYER_DRAW

score_glyphs
        fcb     PRESENTATION_GLYPH_0,PRESENTATION_GLYPH_1
        fcb     PRESENTATION_GLYPH_2,PRESENTATION_GLYPH_3
        fcb     PRESENTATION_GLYPH_4,PRESENTATION_GLYPH_5
        fcb     PRESENTATION_GLYPH_6,PRESENTATION_GLYPH_7
        fcb     PRESENTATION_GLYPH_8,PRESENTATION_GLYPH_9

highscore_default_name_data
        fcb     PRESENTATION_HIGHSCORE_DEFAULT_NAME_0
        fcb     PRESENTATION_HIGHSCORE_DEFAULT_NAME_1
        fcb     PRESENTATION_HIGHSCORE_DEFAULT_NAME_2
        fcb     PRESENTATION_HIGHSCORE_DEFAULT_NAME_3
        fcb     PRESENTATION_HIGHSCORE_DEFAULT_NAME_4
        fcb     PRESENTATION_HIGHSCORE_DEFAULT_NAME_5
        fcb     PRESENTATION_HIGHSCORE_DEFAULT_NAME_6

        ifne    0
draw_tile
        cmpb    #PRESENTATION_GAMEPLAY_TILE_BASE
        blo     draw_cold
        subb    #PRESENTATION_GAMEPLAY_TILE_BASE
        clra
        addd    #PRESENTATION_GAMEPLAY_LOOKUP_OFFSET
        lbsr    cold_ptr
        lda     ,x
        ldb     #32
        mul
        ldu     #PRESENTATION_GAMEPLAY_TILES
        leau    d,u
        tfr     y,x
        tfr     u,y
        jmp     PRES_MAIN_BLIT_TILE
draw_cold
        tfr     b,a
        ldb     #32
        mul
        addd    #PRESENTATION_TILE_ATLAS_OFFSET
        lbsr    cold_ptr
        tfr     x,u
        tfr     y,x
        tfr     u,y
        jmp     PRES_MAIN_BLIT_TILE

cold_ptr
        tfr     d,x
        tfr     a,b
        andb    #$E0
        lsrb
        lsrb
        lsrb
        lsrb
        lsrb
        addb    #PRESENTATION_COLD_PAGE
        stb     PAR5
        tfr     x,d
        anda    #$1F
        adda    #$A0
        tfr     d,x
        rts

map_back
        lda     FB_BACK_ID
        bne     map_back_b
        lda     #$30
        bra     map_back_set
map_back_b
        lda     #$2C
map_back_set
        sta     PAR1
        inca
        sta     PAR2
        inca
        sta     PAR3
        inca
        sta     PAR4
        lda     #$3A
        sta     PAR5
        rts
        endc

        endc
demo_runtime_end
        endc

