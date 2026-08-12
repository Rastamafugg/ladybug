; BUG-011 development instruction choreography.  The GMC loader stages this
; image behind the attract bundle in physical page $23; presentation startup
; copies it into boot-only RAM.
        pragma  nodollarlocal,6809
        setdp   $00
        include "ladybug_presentation.inc"
        include "ladybug_presentation_symbols.inc"

PAR5    equ $FFA5
SPARSE_PLAYER_PAYLOAD_PAGE equ $39
SPARSE_PLAYER_INDEX_ADDR equ $A000
PRESENTATION_MODULE_DRAW equ $0821

PRES_DST equ $00AE
PRES_TIMER equ $00B0
PRES_OUT equ $00B7
PRES_PHASE equ $00CA
PRES_ACTOR_FRAME equ $00CE
PRES_HIGHLIGHT equ $00CF
PRES_COLOUR_TIMER equ $00D0
PRES_WORK equ $00D1
PLAYER_FB equ $000B
PLAYER_BG_VALID equ $006A
PLAYER_OLD_FB equ $0067
FB_BACK equ $0090

; Boot scratch is free after handoff.  The development verifier reads this
; compact trace after the uninterrupted choreography reaches its next screen.
IRT_TRACE_MAGIC equ $06AA
IRT_TRACE_COLOURS equ $06AB
IRT_TRACE_CONSUMES equ $06AC
IRT_TRACE_DEATHS equ $06AD
IRT_TRACE_OWNERS equ $06AE
IRT_TRACE_LAST_DEATH equ $06AF
IRT_OWNER_A_PHASE equ $00D2
IRT_OWNER_A_COLOUR equ $00D3
IRT_OWNER_B_PHASE equ $00D6
IRT_OWNER_B_COLOUR equ $00D7

        org     $0300

instruction_runtime_tick
        ldd     PRES_TIMER
        cmpd    #PRESENTATION_INSTRUCTION_NEXT_TICK
        lbhs    irt_complete
        jsr     PRES_MAIN_FB_PREPARE
        bcs     irt_active
        lda     PRES_PHASE
        cmpa    #$FF
        beq     irt_init
        lbsr    restore_actor
        lbsr    sync_persistent_state
        lda     PRES_PHASE
        cmpa    #PRESENTATION_INSTRUCTION_EVENT_COUNT
        lbhs    irt_death

        dec     PRES_COLOUR_TIMER
        bne     irt_event
        lda     #PRESENTATION_INSTRUCTION_COLOUR_DWELL
        sta     PRES_COLOUR_TIMER
        inc     PRES_HIGHLIGHT
        lda     PRES_HIGHLIGHT
        cmpa    #4
        blo     irt_colour_ready
        lda     #1
        sta     PRES_HIGHLIGHT
irt_colour_ready
        inc     IRT_TRACE_COLOURS
        lbsr    recolour_collectibles
        lbsr    draw_value
irt_colour_published

irt_event
        lda     PRES_PHASE
        cmpa    #PRESENTATION_INSTRUCTION_EVENT_COUNT
        lbhs    irt_death
        lbsr    event_ptr_a
        ldd     PRES_TIMER
        cmpd    ,x
        blo     irt_draw_player
        cmpd    2,x
        beq     consume_event
        bhs     irt_draw_player
        ldd     PRES_OUT
        cmpd    4,x
        bhs     irt_draw_player
        addd    #1
        std     PRES_OUT
irt_draw_player
        lbsr    present_player
irt_active
        lbsr    store_owner_state
        lda     #1
        ldb     FB_BACK
        beq     irt_owner_ready
        lsla
irt_owner_ready
        ora     IRT_TRACE_OWNERS
        sta     IRT_TRACE_OWNERS
        jsr     PRES_MAIN_FB_FINISH
        clra
        rts

irt_init
        lda     #$A5
        sta     IRT_TRACE_MAGIC
        clr     IRT_TRACE_COLOURS
        clr     IRT_TRACE_CONSUMES
        clr     IRT_TRACE_DEATHS
        clr     IRT_TRACE_OWNERS
        lda     #$FF
        sta     IRT_TRACE_LAST_DEATH
        sta     IRT_OWNER_A_PHASE
        sta     IRT_OWNER_A_COLOUR
        sta     IRT_OWNER_B_PHASE
        sta     IRT_OWNER_B_COLOUR
        clr     PRES_PHASE
        lda     #1
        sta     PRES_HIGHLIGHT
        lda     #PRESENTATION_INSTRUCTION_COLOUR_DWELL
        sta     PRES_COLOUR_TIMER
        ldd     #PRESENTATION_INSTRUCTION_ANCHOR_0
        std     PRES_OUT
        clr     PLAYER_BG_VALID
        lbsr    recolour_collectibles
        lbsr    draw_value
        lbsr    present_player
        bra     irt_active

irt_complete
        lda     #1
        rts

; A selects one generated twelve-byte event record; X returns mapped to it.
event_ptr_a
        ldb     #PRESENTATION_INSTRUCTION_EVENT_BYTES
        mul
        addd    #PRESENTATION_INSTRUCTION_EVENT_OFFSET
        jmp     PRES_MODULE_COLD_PTR

consume_event
        lda     10,x
        sta     PRES_WORK
        inc     IRT_TRACE_CONSUMES
        lbsr    restore_actor
        lda     PRES_PHASE
        lbsr    event_ptr_a
        ldd     6,x
        std     PRES_DST
        lbsr    clear_target

        lda     PRES_PHASE
        lbsr    event_ptr_a
        ldy     8,x
        beq     consume_reward
        ldb     11,x
        jsr     PRES_MODULE_DRAW_TILE

consume_reward
        lda     PRES_WORK
        cmpa    #4
        bne     consume_special
        lbsr    draw_life_reward
        ldd     #PRESENTATION_INSTRUCTION_ANCHOR_1
        std     PRES_OUT
        bra     consume_advance
consume_special
        cmpa    #11
        bne     consume_heart
        lbsr    draw_coin_reward
        ldd     #PRESENTATION_INSTRUCTION_ANCHOR_2
        std     PRES_OUT
        bra     consume_advance
consume_heart
        cmpa    #12
        blo     consume_advance
        cmpa    #15
        bhs     consume_advance
        lbsr    draw_multipliers
consume_advance
        inc     PRES_PHASE
        lda     PRES_WORK
        cmpa    #15
        beq     consume_skull
        lbsr    present_player
        lbra    irt_active
consume_skull
        lda     #$FF
        sta     PRES_ACTOR_FRAME
        clrb
        lbsr    present_death
        lbra    irt_active

; Recolour all letter and heart targets. Consumed black cells remain black.
recolour_collectibles
        clr     PRES_WORK
rc_next
        lda     PRES_WORK
        lbsr    event_ptr_a
        ldd     6,x
        tfr     d,x
        jsr     PRES_MODULE_COLOUR_TILE
        inc     PRES_WORK
        lda     PRES_WORK
        cmpa    #15
        blo     rc_next
        rts

; Reconstruct persistent mutations on the currently mapped BACK owner before
; drawing its owner-local actor frame.
sync_persistent_state
        ldx     #IRT_OWNER_A_PHASE
        tst     FB_BACK
        beq     sps_selected
        ldx     #IRT_OWNER_B_PHASE
sps_selected
        lda     PRES_PHASE
        cmpa    ,x
        bne     sps_apply
        lda     PRES_HIGHLIGHT
        cmpa    1,x
        beq     sps_done
sps_apply
        pshs    x
        lbsr    apply_persistent_state
        puls    x
        bra     sps_store

store_owner_state
        ldx     #IRT_OWNER_A_PHASE
        tst     FB_BACK
        beq     sps_store
        ldx     #IRT_OWNER_B_PHASE
sps_store
        lda     PRES_PHASE
        sta     ,x
        lda     PRES_HIGHLIGHT
        sta     1,x
sps_done
        rts

apply_persistent_state
        lda     PRES_HIGHLIGHT
        pshs    a
        lbsr    draw_value
        clr     PRES_WORK
aps_event
        lda     PRES_WORK
        cmpa    PRES_PHASE
        bhs     aps_unconsumed
        lbsr    event_ptr_a
        ldd     6,x
        std     PRES_DST
        lbsr    clear_target
        lda     PRES_WORK
        lbsr    event_ptr_a
        ldy     8,x
        beq     aps_next
        ldb     11,x
        jsr     PRES_MODULE_DRAW_TILE
        bra     aps_next
aps_unconsumed
        lda     ,s
        sta     PRES_HIGHLIGHT
        lda     PRES_WORK
        lbsr    event_ptr_a
        ldd     6,x
        tfr     d,x
        jsr     PRES_MODULE_COLOUR_TILE
aps_next
        inc     PRES_WORK
        lda     PRES_WORK
        cmpa    #15
        blo     aps_event
        lda     PRES_PHASE
        cmpa    #5
        blo     aps_done
        lbsr    draw_life_reward
        lda     PRES_PHASE
        cmpa    #12
        blo     aps_done
        lbsr    draw_coin_reward
        lda     PRES_PHASE
        cmpa    #13
        blo     aps_done
        suba    #1
        cmpa    #14
        bls     aps_multiplier_ready
        lda     #14
aps_multiplier_ready
        sta     PRES_WORK
        lbsr    draw_multipliers
aps_done
        puls    a
        sta     PRES_HIGHLIGHT
        rts

clear_target
        ldx     PRES_DST
        ldy     #8
        clra
        clrb
ct_row
        std     ,x
        std     2,x
        leax    160,x
        leay    -1,y
        bne     ct_row
        rts

clear_consumed_targets
        clr     PRES_WORK
cct_next
        lda     PRES_WORK
        lbsr    event_ptr_a
        ldd     6,x
        std     PRES_DST
        bsr     clear_target
        inc     PRES_WORK
        lda     PRES_WORK
        cmpa    #PRESENTATION_INSTRUCTION_EVENT_COUNT
        blo     cct_next
        rts

draw_value
        lda     PRES_HIGHLIGHT
        cmpa    #1
        beq     dv_red
        cmpa    #2
        beq     dv_yellow
        ldb     #PRESENTATION_INSTRUCTION_VALUE_BLUE_0
        lda     #PRESENTATION_INSTRUCTION_VALUE_BLUE_1
        ldx     #PRESENTATION_INSTRUCTION_VALUE_BLUE_2
        bra     draw_value_tiles
dv_yellow
        ldb     #PRESENTATION_INSTRUCTION_VALUE_YELLOW_0
        lda     #PRESENTATION_INSTRUCTION_VALUE_YELLOW_1
        ldx     #PRESENTATION_INSTRUCTION_VALUE_YELLOW_2
        bra     draw_value_tiles
dv_red
        ldb     #PRESENTATION_INSTRUCTION_VALUE_RED_0
        lda     #PRESENTATION_INSTRUCTION_VALUE_RED_1
        ldx     #PRESENTATION_INSTRUCTION_VALUE_RED_2
draw_value_tiles
        pshs    a,x
        ldy     #PRESENTATION_INSTRUCTION_VALUE_DST
        jsr     PRES_MODULE_DRAW_TILE
        puls    a,x
        pshs    x
        tfr     a,b
        ldy     #PRESENTATION_INSTRUCTION_VALUE_DST+4
        jsr     PRES_MODULE_DRAW_TILE
        puls    x
        tfr     x,d
        ldy     #PRESENTATION_INSTRUCTION_VALUE_DST+8
        jmp     PRES_MODULE_DRAW_TILE

draw_life_reward
        ldx     #life_tiles
        ldy     #PRESENTATION_INSTRUCTION_LIFE_DST
        bra     draw_reward
draw_coin_reward
        ldx     #coin_tiles
        ldy     #PRESENTATION_INSTRUCTION_COIN_DST
draw_reward
        ldb     ,x+
        pshs    x,y
        jsr     PRES_MODULE_DRAW_TILE
        puls    x,y
        leay    4,y
        ldb     ,x+
        pshs    x,y
        jsr     PRES_MODULE_DRAW_TILE
        puls    x,y
        leay    1276,y
        ldb     ,x+
        pshs    x,y
        jsr     PRES_MODULE_DRAW_TILE
        puls    x,y
        leay    4,y
        ldb     ,x
        jmp     PRES_MODULE_DRAW_TILE

draw_multipliers
        lda     PRES_WORK
        suba    #12
        lsla
        leax    multiplier_tiles,pcr
        leax    a,x
        pshs    x
        ldy     #PRESENTATION_INSTRUCTION_MULTIPLIER_0
        bsr     draw_multiplier_pair
        puls    x
        ldy     #PRESENTATION_INSTRUCTION_MULTIPLIER_1
draw_multiplier_pair
        pshs    x,y
        ldb     ,x
        jsr     PRES_MODULE_DRAW_TILE
        puls    x,y
        leay    4,y
        ldb     1,x
        jmp     PRES_MODULE_DRAW_TILE

restore_actor
        lda     #$34
        sta     PAR5
        tst     PLAYER_BG_VALID
        beq     restore_done
        ldd     PLAYER_OLD_FB
        std     PLAYER_FB
        jsr     PRES_MAIN_RESTORE_PLAYER
restore_done
        rts

present_player
        bsr     restore_actor
        ldd     PRES_OUT
        std     PLAYER_FB
        jsr     PRES_MAIN_SAVE_PLAYER
player_underlay_saved
        lda     PRES_TIMER+1
        lsra
        lsra
        lsra
        anda    #3
        adda    #4
        sta     PRES_ACTOR_FRAME
        lda     #SPARSE_PLAYER_PAYLOAD_PAGE
        sta     PAR5
        lda     PRES_ACTOR_FRAME
        ldb     #3
        mul
        ldx     #SPARSE_PLAYER_INDEX_ADDR
        leax    d,x
        ldu     1,x
        lda     ,x
        sta     PAR5
        ldx     PRES_OUT
        jsr     PRESENTATION_MODULE_DRAW
        rts

irt_death
        ldd     PRES_TIMER
        cmpd    #PRESENTATION_INSTRUCTION_ANGEL_TICK
        bhs     death_angel
        subd    #PRESENTATION_INSTRUCTION_DEATH_TICK+30
        blo     death_impact
        clr     PRES_WORK
        inc     PRES_WORK
death_divide
        cmpd    #5
        blo     death_index_ready
        subd    #5
        inc     PRES_WORK
        bra     death_divide
death_impact
        clr     PRES_WORK
death_index_ready
        ldb     PRES_WORK
        bsr     present_death
        lbra    irt_active
death_angel
        ldb     #PRESENTATION_INSTRUCTION_DEATH_COUNT-1
        bsr     present_death
        lbra    irt_active

present_death
        stb     PRES_ACTOR_FRAME
        cmpb    IRT_TRACE_LAST_DEATH
        beq     death_traced
        stb     IRT_TRACE_LAST_DEATH
        inc     IRT_TRACE_DEATHS
death_traced
        lbsr    restore_actor
        lbsr    clear_consumed_targets
        ldd     PRES_OUT
        std     PLAYER_FB
        jsr     PRES_MAIN_SAVE_PLAYER
        lda     PRES_ACTOR_FRAME
        ldb     #2
        mul
        addd    #PRESENTATION_INSTRUCTION_DEATH_POINTERS
        jsr     PRES_MODULE_COLD_PTR
        ldd     ,x
        jsr     PRES_MODULE_COLD_PTR
        tfr     x,u
        ldx     PRES_OUT
        jsr     PRESENTATION_MODULE_DRAW
death_frame_published
death_drawn
        rts

life_tiles
        fcb     PRESENTATION_INSTRUCTION_LIFE_0,PRESENTATION_INSTRUCTION_LIFE_1
        fcb     PRESENTATION_INSTRUCTION_LIFE_2,PRESENTATION_INSTRUCTION_LIFE_3
coin_tiles
        fcb     PRESENTATION_INSTRUCTION_COIN_0,PRESENTATION_INSTRUCTION_COIN_1
        fcb     PRESENTATION_INSTRUCTION_COIN_2,PRESENTATION_INSTRUCTION_COIN_3
multiplier_tiles
        fcb     PRESENTATION_INSTRUCTION_X2_0,PRESENTATION_INSTRUCTION_X2_1
        fcb     PRESENTATION_INSTRUCTION_X3_0,PRESENTATION_INSTRUCTION_X3_1
        fcb     PRESENTATION_INSTRUCTION_X5_0,PRESENTATION_INSTRUCTION_X5_1

instruction_runtime_end
        end
