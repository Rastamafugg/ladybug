; BUG-012 release-profile demo route director, copied to low RAM $0300.
        pragma  nodollarlocal,6809
        setdp   $00
        include "ladybug_presentation.inc"
        include "ladybug_presentation_symbols.inc"

PAR5    equ $FFA5
JOY_DIR equ $0005
PLAYER_FACE equ $0007
PLAYER_STEP equ $0008
PLAYER_CELL_X equ $0009
PLAYER_CELL_Y equ $000A
PLAYER_WANT equ $000F
PLAYER_MANUAL equ $0018
PRES_DEMO_ROUTE equ $00DA
PRES_DEMO_LAST_X equ $00DB
PRES_DEMO_LAST_Y equ $00DC
PRES_DEMO_DIR equ $00DD

        org $0300

demo_runtime_tick
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

demo_runtime_end
        end
