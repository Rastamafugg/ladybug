; PERF-004 low-RAM gateway for the generated perimeter-reset program.
; The boot-synthesized payload occupies physical page $20 and returns here before PAR5 is
; restored to the game-state page.  This code must remain within $06B2-$07FF.

        pragma  nodollarlocal,6809
        setdp   $00
        include "ladybug_presentation_symbols.inc"

        org     $06B2

PERIMETER_RESET_HELPER
        pshs    cc
        orcc    #$50
        lda     #$20
        sta     $FFA5
        jsr     $A000
        lda     #$34
        sta     $FFA5
        puls    cc,pc

PERIMETER_RESET_HELPER_END

; Fixed BUG-010 helper ABI. These jumps remain at fixed addresses so the copied
; presentation module does not need a relocation table.
PRESENTATION_HOLD_BEGIN
        bra     presentation_hold_begin_impl
PRESENTATION_HOLD_TICK
        bra     presentation_hold_tick_impl
PRESENTATION_ATTRACT_OVERLAY
        lbra    presentation_attract_overlay_impl

PAR1    equ $FFA1
PAR2    equ $FFA2
PAR3    equ $FFA3
PAR4    equ $FFA4
PAR5    equ $FFA5
FB_FRONT_ID equ $008F
FB_BACK_ID equ $0090
PENDING equ $0091
PRES_TIMER equ $00B0
PRES_ACTOR_PHASE equ $00D3
PRES_HOLD_STATE equ $00D4
PRES_HOLD_CHUNK equ $00D5
PRES_HOLD_SAVED_FRONT equ $00D6
PRES_HOLD_SAVED_BACK equ $00D7
PRES_HOLD_GEN equ $00D8
PRES_HOLD_OWNER equ $00D9
PRES_HOLD_COPY equ $80
PRES_HOLD_PUBLISH equ $81
PRES_HOLD_HYDRATE equ 3
PRES_HOLD_FINAL equ $81
PRES_ACTOR_TABLE equ $B200
PRES_ACTOR_UNDERLAY equ $B000
PRES_DST equ $00AE
PRES_REMAIN equ $00B9
PRES_ACTOR_FRAME equ $00CE
PRES_ACTOR_KIND equ $00D0
PLAYER_FB equ $000B
PLAYER_BG_PTR equ $00A2
PRESENTATION_MODULE_RESTORE_PLAYER equ PRES_MAIN_RESTORE_PLAYER
PRESENTATION_MODULE_CAPTURE_BACK equ PRES_MAIN_FB_CAPTURE
PRESENTATION_MODULE_MAP_BACK equ PRES_MODULE_MAP_BACK

presentation_hold_begin_impl
        tst     PRES_HOLD_STATE
        bne     phb_done
        clr     PRES_HOLD_GEN
        lda     #PRES_HOLD_COPY
        sta     PRES_HOLD_STATE
        clr     PRES_HOLD_CHUNK
        clr     PRES_HOLD_OWNER
phb_done
        rts

presentation_hold_tick_impl
        lda     PRES_HOLD_STATE
        cmpa    #PRES_HOLD_PUBLISH
        beq     pht_publish
pht_copy
        tst     PENDING
        bne     pht_active
        lda     PRES_HOLD_GEN
        cmpa    #30
        bhs     pht_request
        lda     PRES_HOLD_GEN
        bne     pht_copy_do
        tst     PRES_HOLD_OWNER
        bne     pht_copy_do
        lda     FB_FRONT_ID
        sta     PRES_HOLD_SAVED_FRONT
        lda     FB_BACK_ID
        sta     PRES_HOLD_SAVED_BACK
pht_copy_do
        lbsr    hold_copy_chunk
        inc     PRES_HOLD_GEN
        inc     PRES_HOLD_CHUNK
        lda     PRES_HOLD_CHUNK
        cmpa    #8
        blo     pht_active
        clr     PRES_HOLD_CHUNK
        inc     PRES_HOLD_OWNER
        lda     PRES_HOLD_GEN
        cmpa    #30
        blo     pht_active
pht_request
        orcc    #$10
        lda     #2
        sta     FB_BACK_ID
        lda     #1
        sta     PENDING
        lda     #PRES_HOLD_PUBLISH
        sta     PRES_HOLD_STATE
        andcc   #$EF
pht_active
        rts
pht_publish
        dec     PRES_HOLD_OWNER
        beq     pht_cancel_final
        tst     PENDING
        bne     pht_active
        orcc    #$10
        lda     PRES_HOLD_SAVED_FRONT
        sta     FB_FRONT_ID
        lda     PRES_HOLD_SAVED_BACK
        sta     FB_BACK_ID
        clr     PRES_HOLD_OWNER
        lda     #PRES_HOLD_HYDRATE
        sta     PRES_HOLD_STATE
        andcc   #$EF
        rts
pht_cancel_final
        orcc    #$10
        clr     PENDING
        lda     #PRES_HOLD_HYDRATE
        sta     PRES_HOLD_STATE
        clr     PRES_HOLD_OWNER
        andcc   #$EF
        rts
; Copy one 1 KiB visible chunk. The source page is selected through PAR1 and the
; corresponding compatibility page through PAR5. The normal BACK mapping is restored
; before returning to the presentation module.
hold_copy_chunk
        lda     PRES_HOLD_CHUNK
        lsla
        lsla
        clrb
        tfr     d,y
        ldb     PRES_HOLD_OWNER
        ldx     #hold_source_pages
        lda     b,x
        tst     PRES_HOLD_SAVED_FRONT
        bne     hold_source_page
        adda    #4
hold_source_page
        sta     PAR1
        ldx     #hold_destination_pages
        lda     b,x
        sta     PAR5
        ldx     #$2000
        tfr     y,d
        leax    d,x
        ldu     #$A000
        leau    d,u
        ldy     #512
hold_copy_word
        ldd     ,x++
        std     ,u++
        leay    -1,y
        bne     hold_copy_word
        jsr     PRESENTATION_MODULE_MAP_BACK
        rts

presentation_attract_overlay_impl
        lbsr    presentation_attract_phase
        cmpa    PRES_ACTOR_PHASE
        beq     pao_done
        sta     PRES_ACTOR_PHASE
        jsr     PRES_MAIN_FB_PREPARE
        lda     #$34
        sta     PAR5
        clr     PRES_ACTOR_KIND
pao_pass
        ldx     #PRES_ACTOR_TABLE
        ldu     #PRES_ACTOR_UNDERLAY
        lda     #4
        sta     PRES_REMAIN
pao_restore
        pshs    x
        ldd     ,x
        tst     PRES_ACTOR_KIND
        bne     pao_draw_actor
        stu     PLAYER_BG_PTR
        std     PLAYER_FB
        jsr     PRESENTATION_MODULE_RESTORE_PLAYER
        bra     pao_next
pao_draw_actor
        std     PRES_DST
        leax    2,x
        ldb     PRES_ACTOR_PHASE
        abx
        lda     ,x
        sta     PRES_ACTOR_FRAME
        jsr     PRES_MODULE_DRAW_ACTOR
pao_next
        puls    x
        leax    6,x
        leau    128,u
        dec     PRES_REMAIN
        bne     pao_restore
        tst     PRES_ACTOR_KIND
        bne     pao_after_pass
        lda     #1
        sta     PRES_ACTOR_KIND
        bra     pao_pass
pao_after_pass
        lda     PRES_HOLD_STATE
        cmpa    #PRES_HOLD_HYDRATE
        beq     pao_capture
        jmp     PRES_MAIN_FB_FINISH
pao_done
        rts
pao_capture
        jmp     PRESENTATION_MODULE_CAPTURE_BACK

presentation_attract_phase
        ldd     PRES_TIMER
        subd    #6
        blo     presentation_phase_zero
        tfr     b,a
        lsra
        lsra
        lsra
        anda    #3
        inca
        rts
presentation_phase_zero
        clra
        rts

hold_source_pages
        fcb     $2C,$2D,$2E,$2F
hold_destination_pages
        fcb     $28,$29,$2A,$2B

PERIMETER_PRESENTATION_HELPER_END
