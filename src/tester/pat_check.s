;==============================================================================
; pat_check.s — Checkerboard pattern (mode-aware).
;
; The cell granularity differs by bpp because pixel-per-byte differs:
;   4bpp: byte holds 2 pixels → alternating bytes $01/$10 within a row give
;         2-pixel cells; row order flips every 8 lines → 2×8 cell.
;   2bpp: byte holds 4 pixels → packing two pixels of color 0 then two of
;         color 1 yields the cell within one byte. Adjacent bytes use the same
;         packing for cell alignment; the row alternates between byte $05
;         (0,0,1,1 left→right) and $50 (1,1,0,0) every 8 lines → 2×8 cell.
;==============================================================================

;------------------------------------------------------------------------------
; pat_check_draw — dispatch on TM_BPP.
;
;  Inputs:  X = pointer to active mode record
;  Returns: (none)
;  Side effects: writes FB; clobbers A,B,X,Y,U,CC.
;------------------------------------------------------------------------------
pat_check_draw
        lda     TM_BPP,x
        cmpa    #4
        beq     pat_check_4bpp
        cmpa    #2
        beq     pat_check_2bpp
        rts

;------------------------------------------------------------------------------
; pat_check_4bpp — checker variant for mode 0 (320x192x16, lifted from WS-A).
;------------------------------------------------------------------------------
pat_check_4bpp
        ldx     #FB_VIRT
        clra                    ; row counter 0..191
chk4_row
        ; Strip parity: bit 3 of row → alternate every 8 rows.
        tfr     a,b
        andb    #$08
        beq     chk4_a
        ldu     #$1001          ; row pattern B: $10 $01 $10 $01 ...
        bra     chk4_emit
chk4_a
        ldu     #$0110          ; row pattern A: $01 $10 $01 $10 ...
chk4_emit
        pshs    a               ; save row counter
        ldy     #80             ; 160 bytes / row = 80 STDs
        tfr     u,d
chk4_inner
        std     ,x++
        leay    -1,y
        bne     chk4_inner
        puls    a
        inca
        cmpa    #192
        blo     chk4_row
        rts

;------------------------------------------------------------------------------
; pat_check_2bpp — checker variant for mode 1 (320x192x4).
;
; Row pattern A (rows where bit 3 of row counter == 0): byte $05 throughout.
;   $05 = 0b00000101 → pixels (left→right) 0,0,1,1. Cell pair per byte.
; Row pattern B (rows where bit 3 of row counter == 1): byte $50 throughout.
;   $50 = 0b01010000 → pixels (left→right) 1,1,0,0. Inverted cell pair.
; 80 bytes/row = 40 STDs/row × 192 rows.
;------------------------------------------------------------------------------
pat_check_2bpp
        ldx     #FB_VIRT
        clra
chk2_row
        tfr     a,b
        andb    #$08
        beq     chk2_a
        ldu     #$5050          ; row pattern B
        bra     chk2_emit
chk2_a
        ldu     #$0505          ; row pattern A
chk2_emit
        pshs    a
        ldy     #40             ; 80 bytes / row = 40 STDs
        tfr     u,d
chk2_inner
        std     ,x++
        leay    -1,y
        bne     chk2_inner
        puls    a
        inca
        cmpa    #192
        blo     chk2_row
        rts
