; DOC-002 source-contract mirror begins. Canonical definitions:
; wiki/internal/implementation/routine-catalog.html
; DOC-002 source-contract mirror profile render Inputs: A selects SPECIAL and/or EXTRA; B is zero for a whole-row redraw or the changed one-based letter column
; DOC-002 source-contract mirror profile render Outputs: Selected authored word cells are recolored in the prepared BACK framebuffer
; DOC-002 source-contract mirror profile render Clobbers: A, B, X, Y, and condition codes; uses the HUD tile scratch at $0027-$002E
; DOC-002 source-contract mirror profile render Reads: The player-one word bits, current presentation screen, generated HUD field geometry, and generated glyph cell table
; DOC-002 source-contract mirror profile render Writes: Only the selected SPECIAL or EXTRA word cells in BACK
; DOC-002 source-contract mirror profile render Side effects: Calls the resident recolored-map-tile painter while PAR5 maps page $3D
; DOC-002 source-contract mirror profile render Invariants: Caller maps page $3D before entry and restores its prior PAR5 after return; zero column redraws the selected whole word after a reset
; DOC-002 source-contract mirror contract hud_word_paint profile=render: Paint the selected SPECIAL/EXTRA word fully or repaint only the changed letter column.
; DOC-002 source-contract mirror contract dwph_paint_word profile=render: Recolor one generated word row from its owner bits, using the requested single column when nonzero.
; DOC-002 source-contract mirror ends.

        pragma  nodollarlocal,6809
        setdp   $00
        include "ladybug_hud_layout.inc"
        include "ladybug_runtime_symbols.inc"
        include "ladybug_text_colours.inc"

PRES_SCREEN equ $00A6
HUD_P1_SPECIAL_BITS equ $02A6
HUD_P1_EXTRA_BITS equ $02A7
HUD_X equ $0027
HUD_Y equ $0028
HUD_COLOR equ $0029
HUD_BYTE equ $002A
HUD_COUNT equ $002B
HUD_BCD_BYTE equ $002D
HUD_BCD_COUNT equ $002E

        org     $0000

; Runtime entry is fixed at $BF00 in the page-$3D loader stream.
hud_word_paint
        pshs    a,b
        lda     1,s
        bita    #PRESENTATION_HUD_DRAW_SPECIAL
        beq     hwp_extra
        lda     PRES_SCREEN
        cmpa    #PRESENTATION_MAP_INSTRUCTIONS
        beq     hwp_special_inactive
        lda     HUD_P1_SPECIAL_BITS
        bra     hwp_special_ready
hwp_special_inactive
        clra
hwp_special_ready
        sta     HUD_BCD_BYTE
        ldd     #(PRESENTATION_HUD_SPECIAL_PROGRESS_X*256+PRESENTATION_HUD_SPECIAL_PROGRESS_Y)
        std     HUD_X
        lda     #PRESENTATION_HUD_SPECIAL_PROGRESS_WIDTH
        sta     HUD_COUNT
        lda     #TEXT_SPECIAL
        sta     HUD_COLOR
        bsr     dwph_paint_word
hwp_extra
        lda     1,s
        bita    #PRESENTATION_HUD_DRAW_EXTRA
        beq     hwp_done
        lda     PRES_SCREEN
        cmpa    #PRESENTATION_MAP_INSTRUCTIONS
        beq     hwp_extra_inactive
        lda     HUD_P1_EXTRA_BITS
        bra     hwp_extra_ready
hwp_extra_inactive
        clra
hwp_extra_ready
        sta     HUD_BCD_BYTE
        ldd     #(PRESENTATION_HUD_EXTRA_PROGRESS_X*256+PRESENTATION_HUD_EXTRA_PROGRESS_Y)
        std     HUD_X
        lda     #PRESENTATION_HUD_EXTRA_PROGRESS_WIDTH
        sta     HUD_COUNT
        lda     #TEXT_EXTRA
        sta     HUD_COLOR
        bsr     dwph_paint_word
hwp_done
        leas    2,s
        rts

dwph_paint_word
        lda     2,s             ; caller's selected column, zero means full row
        sta     HUD_BYTE
        lda     HUD_COLOR       ; retain active color across tile drawing
        sta     HUD_BCD_COUNT
        lda     #TEXT_INSTRUCTION_MULTIPLIER_INACTIVE
        sta     HUD_COLOR
        lda     HUD_BYTE
        beq     dwph_full_row
        cmpa    HUD_COUNT
        bhi     dwph_paint_done
        deca
        adda    HUD_X
        sta     HUD_X
        lda     HUD_BYTE
        deca
        beq     dwph_selected_bit
dwph_shift_to_column
        lsr     HUD_BCD_BYTE
        deca
        bne     dwph_shift_to_column
dwph_selected_bit
        lsr     HUD_BCD_BYTE
        bcc     dwph_selected_paint
        lda     HUD_BCD_COUNT
        sta     HUD_COLOR
dwph_selected_paint
        jsr     draw_recolored_map_tile
        rts
dwph_full_row
dwph_full_loop
        lsr     HUD_BCD_BYTE
        bcc     dwph_full_inactive
        lda     HUD_BCD_COUNT
        sta     HUD_COLOR
        bra     dwph_full_paint
dwph_full_inactive
        lda     #TEXT_INSTRUCTION_MULTIPLIER_INACTIVE
        sta     HUD_COLOR
dwph_full_paint
        jsr     draw_recolored_map_tile
        inc     HUD_X
        dec     HUD_COUNT
        bne     dwph_full_loop
dwph_paint_done
        rts

hud_word_paint_end
