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

; PERF-003 clean one-byte horizontal movement. X is the old framebuffer
; pointer and U is its circular save-under ring. Restore the old exposed
; column, capture the new exposed column, and rotate the ring phase.
ROAM_COMBINED_RIGHT
        clr     $007A
        ldb     $009C
        andb    #7
        bra     roam_combined
ROAM_COMBINED_LEFT
        inc     $007A
        ldb     $009C
        andb    #7
        addb    #7
        andb    #7
roam_combined
        stb     $0079
        pshs    x
        leay    b,u
        tst     $007A
        beq     rcr_restore
        leax    7,x
rcr_restore
        lda     $009C
        lsra
        lsra
        lsra
        lsra
        sta     $009D
        ldb     #16
        subb    $009D
rcr_old_first
        lda     ,y
        sta     ,x
        leax    160,x
        leay    8,y
        decb
        bne     rcr_old_first
        lda     $009D
        beq     rcr_old_done
        leay    -128,y
        tfr     a,b
rcr_old_second
        lda     ,y
        sta     ,x
        leax    160,x
        leay    8,y
        decb
        bne     rcr_old_second
rcr_old_done
        puls    x
        tst     $007A
        beq     rcr_capture_right
        leax    -1,x
        bra     rcr_capture
rcr_capture_right
        leax    8,x
rcr_capture
        ldb     $0079
        leay    b,u
        ldb     #16
        subb    $009D
rcr_new_first
        lda     ,x
        sta     ,y
        leax    160,x
        leay    8,y
        decb
        bne     rcr_new_first
        lda     $009D
        beq     rcr_new_done
        leay    -128,y
        tfr     a,b
rcr_new_second
        lda     ,x
        sta     ,y
        leax    160,x
        leay    8,y
        decb
        bne     rcr_new_second
rcr_new_done
        lda     $009C
        anda    #$F0
        sta     $009D
        ldb     $0079
        tst     $007A
        bne     rcr_left_phase
        incb
        andb    #7
rcr_left_phase
        orb     $009D
        stb     $009C
        rts

SPARSE_BLIT_STAGE_HELPER
sbs_delta
        ldb     ,u+
        cmpb    #$FF
        beq     sbs_extended
        bitb    #$80
        beq     sbs_add_delta
        subb    #152
sbs_add_delta
        abx
sbs_command
        ldb     ,u+
        bmi     sbs_partial
sbs_opaque_byte
        lda     ,u+
        sta     ,x+
        decb
        bne     sbs_opaque_byte
        bra     sbs_delta
sbs_partial
        andb    #$7F
sbs_partial_byte
        lda     ,u+
        anda    ,x
        ora     ,u+
        sta     ,x+
        decb
        bne     sbs_partial_byte
        bra     sbs_delta
sbs_extended
        ldd     ,u++
        beq     sparse_decode_done
        ldb     ,u+
        abx
        bra     sbs_command
sparse_decode_done
        lda     #$34
        sta     $FFA5
        rts

SPARSE_ENEMY_STREAM_HELPER
        ldb     #3
        mul
        ldu     #$0500
        leau    d,u
        lda     ,u
        tfr     a,b
        andb    #$3F
        stb     $FFA5
        ldu     1,u
        rts

SPARSE_PLAYER_STREAM_HELPER
        ldb     #3
        mul
        ldu     #$0680
        leau    d,u
        lda     ,u
        sta     $FFA5
        ldu     1,u
        rts

ROAM_CAPTURE_FULL_HELPER
        ldy     #8
roam_capture_two_rows
        ldd     ,x++
        std     ,u++
        ldd     ,x++
        std     ,u++
        ldd     ,x++
        std     ,u++
        ldd     ,x++
        std     ,u++
        leax    152,x
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
        bne     roam_capture_two_rows
        rts
