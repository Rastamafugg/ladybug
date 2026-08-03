; PERF-004 low-RAM gateway for the generated perimeter-reset program.
; The payload occupies physical page $3A and returns here before PAR5 is
; restored to the game-state page.  This code must remain within $06B2-$07FF.

        org     $06B2

PERIMETER_RESET_HELPER
        pshs    cc
        orcc    #$50
        lda     #$3A
        sta     $FFA5
        jsr     $A000
        lda     #$34
        sta     $FFA5
        puls    cc,pc

PERIMETER_RESET_HELPER_END
