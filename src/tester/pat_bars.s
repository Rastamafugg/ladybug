;==============================================================================
; pat_bars.s — Horizontal 16-color bars pattern.
;
; Lifted from src/diag_minimal.s. 16 stripes × 12 rows, each row 160 bytes
; (320 px / 2 px-per-byte). Stripe N is filled with byte $NN so both pixels
; land on palette index N.
;==============================================================================

;------------------------------------------------------------------------------
; pat_bars_draw — fill the framebuffer with 16 horizontal bars.
;
;  Inputs:  (none)
;  Returns: (none)
;  Side effects: writes FB at $2000..$97FF; clobbers A,B,X,Y,U,CC.
;------------------------------------------------------------------------------
pat_bars_draw
        ldx     #FB_VIRT
        ldu     #$0000          ; pixel-pair byte = $NN for stripe N
        clra                    ; stripe counter
bars_outer
        pshs    a
        ldy     #960            ; 12 rows × 80 STDs/row = 960 STDs per stripe
        tfr     u,d
bars_inner
        std     ,x++
        leay    -1,y
        bne     bars_inner
        leau    $1111,u         ; next stripe byte ($11 increment in both nibbles)
        puls    a
        inca
        cmpa    #16
        blo     bars_outer
        rts
