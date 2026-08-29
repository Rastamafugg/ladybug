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
; DOC-002 source-contract mirror ends.
        pragma  nodollarlocal,6809
        setdp   $00
        include "ladybug_presentation.inc"
        include "ladybug_presentation_symbols.inc"

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
PRES_HIGHSCORE_BASE equ $AF84
PRES_PENDING_NAME equ $AFDE
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
FB_RENDER_ACTIVE equ $0098
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

        org $0300

demo_runtime_tick
        ifne    HIGHSCORE_TEST_PROFILE
        lda     PRES_MODE
        cmpa    #MODE_NAME
        lbeq    name_tick
        cmpa    #MODE_GAMEOVER
        lbeq    prepare_name
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

prepare_name
        lbsr    init_scores
        lda     #$09
        sta     PRES_SCORE_H
        lda     #$50
        sta     PRES_SCORE_M
        clr     PRES_SCORE_L
        clr     PRES_INSERT
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
        jsr     PRES_MAIN_READ_JOY
name_joy_ready
        lda     JOY_DIR
        cmpa    #DIR_NONE
        beq     name_idle
        lda     FRAMES+1
        lsra
        bcs     name_idle
        tst     PRES_NAME_STEPS
        bne     name_move_active
        lda     PLAYER_WANT
        cmpa    #DIR_NONE
        beq     name_idle
        lbsr    name_can_move
        beq     name_idle
        lda     PLAYER_WANT
        sta     PLAYER_DIR
        sta     PLAYER_FACE
        lda     #4
        sta     PRES_NAME_STEPS
name_move_active
        lbsr    name_advance
        rts
name_idle
        tst     FB_RENDER_ACTIVE
        beq     name_idle_done
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
        lbsr    name_cell_arrival
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
        lda     #1
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
        lbsr    prepare_name
        jsr     PRES_MODULE_MAP_BACK
        lbsr    draw_name_fields
        lbsr    draw_entry_scores
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
        lbsr    draw_score
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
        lbsr    draw_high_score_screen
        rts

draw_high_score_screen
        ldx     #PRES_HIGHSCORE_BASE
        ldu     #PRESENTATION_HIGHSCORE_TOP_NAME_DST
        lbsr    draw_high_score_entry
        leau    PRESENTATION_HIGHSCORE_ENTRY_NAME_DST-PRESENTATION_HIGHSCORE_TOP_NAME_DST,u
        ldb     #PRESENTATION_HIGHSCORE_COUNT-1
draw_high_score_rows
        pshs    b
        lbsr    draw_high_score_entry
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
        lbsr    draw_record_name
        puls    u
        pshs    u
        tfr     u,y
        leay    PRESENTATION_HIGHSCORE_TOP_SCORE_DST-PRESENTATION_HIGHSCORE_TOP_NAME_DST,y
        ldx     PRES_NAME_PTR
        lbsr    draw_score
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
        lbsr    draw_digit
        lda     PRES_TMP_L
        anda    #$0F
        lbsr    draw_digit
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
        lbsr    capture_cursor
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
        lbsr    restore_cursor
        lbsr    draw_name_fields
        lbsr    capture_owner
        lbsr    draw_cursor
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
        lbsr    capture_cursor
        rts
capture_a
        ldu     #PRES_CURSOR_SAVE_A
        ldx     PLAYER_FB
        stx     PRES_NAME_PTR_A
        lbsr    capture_cursor
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
        end
