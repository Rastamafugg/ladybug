; Approved BUG-087 current-prefix preparation, not integrated production.
; Called only while PAR5 maps physical page$34; low029B..029F belongs to
; this clock only after bootstrap descriptor retirement.
; DOC-002 source-contract mirror profile state Inputs: Current authoritative gameplay or presentation state; register arguments are named by the routine label and immediate caller
; DOC-002 source-contract mirror profile state Outputs: Updated authoritative state and condition codes used by the immediate caller
; DOC-002 source-contract mirror profile state Clobbers: A, B, D, X, Y, U, and condition codes unless a narrower source-local header is present
; DOC-002 source-contract mirror profile state Reads: Owned direct-page and page-$34 state needed for the operation
; DOC-002 source-contract mirror profile state Writes: Only the owned state fields and render intents required by the operation
; DOC-002 source-contract mirror profile state Side effects: May enqueue rendering work but does not publish FRONT
; DOC-002 source-contract mirror profile state Invariants: Authoritative state changes precede their render intents; framebuffer publication remains IRQ-owned
; DOC-002 source-contract mirror contract rate_reset profile=state: Reset retired bootstrap rate state for the current part.
; DOC-002 source-contract mirror contract rate_tick profile=state: Advance elapsed time before the preserved freeze and shared movement admission gate.
; DOC-002 source-contract mirror contract rate_select profile=state: Select the approved arcade default part and saturated elapsed fractional addend.
; DOC-002 source-contract mirror contract rate_enemy_init_shim profile=state: Reset rate state then tail-call the true enemy initializer without resident growth.
        setdp   $00
STAGE           equ     $0024
FREEZE_TIMER    equ     $005B
RATE_TIMER      equ     $029B
RATE_BUCKET     equ     $029C
RATE_FRAC       equ     $029D
RATE_ADDEND     equ     $029E
RATE_PHASE      equ     $029F

        org     $A3B0

rate_reset
        lda     #96
        sta     RATE_TIMER
        clr     RATE_BUCKET
        clr     RATE_FRAC
        clr     RATE_ADDEND
        clr     RATE_PHASE
        lbsr    rate_select
        rts

rate_tick
        dec     RATE_TIMER
        bne     rt_freeze_gate
        lda     #60
        sta     RATE_TIMER
        lda     RATE_BUCKET
        cmpa    #$F0
        bhs     rt_freeze_gate
        inc     RATE_BUCKET
        lda     RATE_BUCKET
        anda    #$0F
        bne     rt_freeze_gate
        lbsr    rate_select
rt_freeze_gate
        ldd     FREEZE_TIMER
        beq     rt_accumulate
        subd    #1
        std     FREEZE_TIMER
        clra                    ; frozen calls advance elapsed time only, not frac/phase
        rts
rt_accumulate
        lda     RATE_FRAC
        adda    RATE_ADDEND
        sta     RATE_FRAC
        bcs     rt_fraction_extra
        tst     RATE_PHASE
        beq     rt_base_pixel
        clr     RATE_PHASE
        lda     #1
        rts
rt_base_pixel
        inc     RATE_PHASE
        clra
        rts
rt_fraction_extra
        lda     #1
        rts

; Source-policy selector for default Easy/Medium. STAGE is CoCo's one-based
; stage number; source-to-CoCo elapsed and dispatcher conversion is not set.
rate_select
        lda     STAGE
        beq     rs_counter_wrap
        cmpa    #18
        bhs     rs_late_parts
        deca
        leax    rate_stage_offsets,pcr
        lda     a,x
        tfr     a,b
        bra     rs_offset_ready
rs_counter_wrap
        clrb
        bra     rs_offset_ready
rs_late_parts
        ldb     #15
rs_offset_ready
        lda     RATE_BUCKET
        lsra
        lsra
        lsra
        lsra
        pshs    b
        adda    ,s+
        cmpa    #15
        bls     rs_rate_ready
        lda     #15
rs_rate_ready
        cmpa    #6
        blo     rs_rate_100
        cmpa    #12
        blo     rs_rate_120
        cmpa    #15
        blo     rs_rate_150
        lda     #$CC
        bra     rs_store_addend
rs_rate_150
        lda     #$80
        bra     rs_store_addend
rs_rate_120
        lda     #$33
        bra     rs_store_addend
rs_rate_100
        clra
rs_store_addend
        sta     RATE_ADDEND
        rts

rate_stage_offsets
        fcb     0,2,4,1,3,5,6,8,5,7,9,10,11,8,12,13,14

; Keep the hot rate_tick entry at $A3C5; init resets then tail-calls true init.
rate_enemy_init_shim
        lbsr    rate_reset
        jmp     $0800
rate_module_end
