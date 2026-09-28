; Isolated BUG-058 audio admission split, not a delivered audio owner.
; This safe subset rejects elapsed >1 without mutating audio state. It does
; not solve note delivery across a blocking two/four-refresh renderer.
        pragma 6809
        include "adaptive_audio_reference.inc"
        org $B62B
; A=0 advance existing voices by X elapsed ticks (0/1 only); A=1 sample
; semantic transitions once and prime newly admitted slots without aging
; existing waits; A=2 mix/output current slots. Return A=1 means unsupported
; elapsed service, caller must not retire its raw audio timestamp.
adaptive_audio_api
        tsta
        beq aaa_elapsed
        cmpa #1
        beq aaa_admit
        cmpa #2
        beq aaa_output
aaa_reject
        lda #1
        rts
aaa_elapsed
        cmpx #1
        bhi aaa_reject
        beq aaa_one
        bra aaa_ok
aaa_one
        jsr audio_advance_all
        bra aaa_ok
aaa_admit
        lda PRES_MODE
        ldb AUDIO_LAST_MODE
        sta AUDIO_LAST_MODE
        cmpb #6
        bne aaa_poll
        tsta
        bne aaa_poll
        lda $00A7
        cmpa #1
        bne aaa_poll
        lda #6
        clrb
        jsr audio_enqueue_impl
aaa_poll
        tst PRES_MODE
        bne aaa_silent_demo
        jsr audio_poll_gameplay
        jsr audio_process_queue
        jsr audio_music_dispatch
        bra aaa_prime
aaa_silent_demo
        clr audio_poll_valid
        bra aaa_ok
aaa_output
        jsr audio_credit_service
        jsr aaa_prime
        lda #$6C
        sta $FF90
        jsr audio_select_gmc
        jsr audio_mix
        jsr audio_mix_write
        lda #$68
        sta $FF90
aaa_ok
        clra
        rts
; A newly admitted slot has wait0 and its stream pointer at the first
; command. Decode that first note once; never decrement an old slot's wait.
aaa_prime
        clr AUDIO_WORK_SLOT
aaa_slot
        jsr audio_slot_base
        lda ,x
        cmpa #$FF
        beq aaa_next
        cmpa #12
        bne aaa_wait
        lda audio_slot0
        cmpa #$FF
        bne aaa_next
aaa_wait
        tst 3,x
        bne aaa_next
        jsr audio_advance_slot
aaa_next
        inc AUDIO_WORK_SLOT
        lda AUDIO_WORK_SLOT
        cmpa #4
        blo aaa_slot
        rts
adaptive_audio_api_end
