;==============================================================================
; pat_check.s — Checkerboard pattern.
;
; Per WS-A architect spec: alternating $01/$10 bytes across each row, with
; the row's byte-order flipped every 8 scanlines. Each byte holds two pixels
; in palette indices 0 and 1; flipping the byte order flips the pixel-pair
; phase, producing visible 8-row × 2-pixel cells useful as a pixel-alignment
; check against the bars pattern.
;==============================================================================

;------------------------------------------------------------------------------
; pat_check_draw — fill FB with the checkerboard pattern.
;
;  Inputs:  (none)
;  Returns: (none)
;  Side effects: writes FB $2000..$97FF; clobbers A,B,X,Y,U,CC.
;------------------------------------------------------------------------------
pat_check_draw
        ldx     #FB_VIRT
        clra                    ; row counter 0..191
chk_row
        ; Strip parity: bit 3 of row → alternate every 8 rows.
        tfr     a,b
        andb    #$08
        beq     chk_a
        ldu     #$1001          ; row pattern B: $10 $01 $10 $01 ...
        bra     chk_emit
chk_a
        ldu     #$0110          ; row pattern A: $01 $10 $01 $10 ...
chk_emit
        pshs    a               ; save row counter
        ldy     #80             ; 160 bytes / row = 80 stds
        tfr     u,d
chk_inner
        std     ,x++
        leay    -1,y
        bne     chk_inner
        puls    a
        inca
        cmpa    #192
        blo     chk_row
        rts
