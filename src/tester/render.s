;==============================================================================
; render.s — pattern dispatch and the mode-change redraw sequence.
;==============================================================================

;------------------------------------------------------------------------------
; redraw_with_blank — apply current mode + pattern.
; Blanks via CRES=11, reprograms mode regs from tester_mode_table[idx], draws
; the current pattern, then unblanks by writing the mode's real VRES byte.
;
;  Inputs:
;       tester_mode_idx     - mode table index
;       tester_pattern_idx  - pattern jump table index
;  Returns: (none)
;  Side effects: writes $FF98/$FF99/$FF9A/$FF9D/$FF9E; rewrites FB.
;------------------------------------------------------------------------------
redraw_with_blank
        lda     #BLANK_VRES
        sta     GIME_VRES

        ldb     tester_mode_idx
        lda     #TM_LEN
        mul                     ; D = idx * TM_LEN
        leax    tester_mode_table,pcr
        leax    d,x

        lda     TM_VMODE,x
        sta     GIME_VMODE
        lda     TM_BORDER,x
        sta     GIME_BORDER
        lda     TM_VOFF1,x
        sta     GIME_VOFF1
        lda     TM_VOFF0,x
        sta     GIME_VOFF0

        ; Stash final-VRES across the draw call; renderers clobber freely.
        lda     TM_VRES,x
        pshs    a
        jsr     draw_current_pattern
        puls    a
        sta     GIME_VRES
        rts

;------------------------------------------------------------------------------
; draw_current_pattern — dispatch to renderer via pattern_jump_table.
;
;  Inputs:  tester_pattern_idx
;  Returns: (none)
;  Side effects: renderer-defined.
;------------------------------------------------------------------------------
draw_current_pattern
        ldb     tester_pattern_idx
        aslb                    ; byte → word offset
        leax    pattern_jump_table,pcr
        jsr     [b,x]
        rts

pattern_jump_table
        fdb     pat_bars_draw
        ; WS-A milestone 2 adds: fdb pat_check_draw
