;==============================================================================
; pat_bars.s — Horizontal-bars pattern (mode-aware).
;
; 4bpp (mode 0): 16 stripes × 12 rows × 160 bytes/row. Byte for stripe N is $NN
;                so both pixels in each byte land on palette index N.
; 2bpp (mode 1): 4 stripes × 48 rows × 80 bytes/row. Byte for stripe N packs
;                four pixels of palette index N (0=$00, 1=$55, 2=$AA, 3=$FF).
;
; Both variants render to the FB at virt $2000 (the mode records use the same
; voff1/voff0).
;==============================================================================

;------------------------------------------------------------------------------
; pat_bars_draw — dispatch on TM_BPP and call the appropriate variant.
;
;  Inputs:  X = pointer to active mode record
;  Returns: (none)
;  Side effects: writes FB; clobbers A,B,X,Y,U,CC.
;------------------------------------------------------------------------------
pat_bars_draw
        lda     TM_BPP,x
        cmpa    #4
        beq     pat_bars_4bpp
        cmpa    #2
        beq     pat_bars_2bpp
        rts                     ; unsupported bpp — leave FB alone

;------------------------------------------------------------------------------
; pat_bars_4bpp — 16-stripe bars (mode 0, lifted from WS-A diag_minimal).
;
; 16 stripes; 192/16 = 12 rows per stripe; 160 bytes/row → 1920 bytes/stripe =
; 960 STDs/stripe.
;------------------------------------------------------------------------------
pat_bars_4bpp
        ldx     #FB_VIRT
        ldu     #$0000          ; pixel-pair byte = $NN for stripe N
        clra                    ; stripe counter
bars4_outer
        pshs    a
        ldy     #960            ; 12 rows × 80 STDs/row = 960 STDs per stripe
        tfr     u,d
bars4_inner
        std     ,x++
        leay    -1,y
        bne     bars4_inner
        leau    $1111,u         ; next stripe byte (+$11 in both nibbles)
        puls    a
        inca
        cmpa    #16
        blo     bars4_outer
        rts

;------------------------------------------------------------------------------
; pat_bars_2bpp — 4-stripe bars (mode 1).
;
; 4 stripes; 192/4 = 48 rows per stripe; 80 bytes/row → 3840 bytes/stripe =
; 1920 STDs/stripe. Per-stripe byte values: 0:$00, 1:$55, 2:$AA, 3:$FF.
; Each byte packs four 2-bpp pixels of the same index.
;------------------------------------------------------------------------------
pat_bars_2bpp
        ldx     #FB_VIRT
        ldu     #$0000          ; pixel-quad byte for stripe N
        clra                    ; stripe counter
bars2_outer
        pshs    a
        ldy     #1920           ; 48 rows × 40 STDs/row = 1920 STDs per stripe
        tfr     u,d
bars2_inner
        std     ,x++
        leay    -1,y
        bne     bars2_inner
        leau    $5555,u         ; +$55 per stripe → $00, $55, $AA, $FF
        puls    a
        inca
        cmpa    #4
        blo     bars2_outer
        rts
