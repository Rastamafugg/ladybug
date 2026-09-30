; Included at end of banked audio runtime. Foreground only; active game/demo.
; A=0 elapsed existing notes; 1 semantic admission; 2 audible publication;
; 3 rebase after static work/phase entry. Newly decoded notes are admitted
; now, never through elapsed time before they were decoded/published.
audio_adaptive_api
        tsta
        beq aas_elapsed
        cmpa #1
        lbeq aas_admit
        cmpa #2
        lbeq aas_output
        cmpa #3
        beq aas_rebase
        lda #1
        rts
aas_clock
        pshs cc
        orcc #$10
        ldd $0002
        puls cc,pc
aas_rebase
        bsr aas_clock
        std audio_adaptive_last
        clr audio_adaptive_late
        clra
        rts
aas_elapsed
        bsr aas_clock
        pshs d
        subd audio_adaptive_last
        std audio_adaptive_delta
        puls d
        std audio_adaptive_last
        ldd audio_adaptive_delta
        lbeq aas_ok
        clr AUDIO_WORK_SLOT
aas_elapsed_slot
        jsr audio_slot_base
        lda ,x
        cmpa #$FF
        beq aas_elapsed_next
        cmpa #12
        bne aas_elapsed_wait
        lda audio_slot0
        cmpa #$FF
        bne aas_elapsed_next
aas_elapsed_wait
        ldd audio_adaptive_delta
        tsta
        bne aas_elapsed_due
        cmpb 3,x
        bhs aas_elapsed_due
        negb
        addb 3,x
        stb 3,x
        bra aas_elapsed_next
aas_elapsed_due
        ; At most one note boundary per voice per audible publication.
        ; Its encoded dwell starts now. Record late delivery instead of
        ; silently expiring later important notes in the unserviced interval.
        clra
        ldb 3,x
        cmpd audio_adaptive_delta
        beq aas_due_on_time
        lda #1
        sta audio_adaptive_late
aas_due_on_time
        clr 3,x
        jsr audio_advance_slot
aas_elapsed_next
        inc AUDIO_WORK_SLOT
        lda AUDIO_WORK_SLOT
        cmpa #4
        blo aas_elapsed_slot
        bra aas_ok
aas_admit
        lda PRES_MODE
        ldb AUDIO_LAST_MODE
        sta AUDIO_LAST_MODE
        cmpb #6
        bne aas_poll
        tsta
        bne aas_poll
        lda $00A7
        cmpa #1
        bne aas_poll
        lda #6
        clrb
        jsr audio_enqueue_impl
aas_poll
        tst PRES_MODE
        bne aas_demo
        jsr aas_dirty
        bcc aas_ok
        jsr audio_poll_gameplay
        jsr audio_process_queue
        jsr audio_music_dispatch
        bra aas_prime
aas_demo
        clr audio_poll_valid
        bra aas_ok
aas_output
        jsr audio_credit_service
        jsr aas_prime
        lda #$6C
        sta GIME_INIT0
        jsr audio_select_gmc
        jsr audio_mix
        jsr audio_mix_write
        lda #$68
        sta GIME_INIT0
aas_ok
        clra
        rts
aas_prime
        clr AUDIO_WORK_SLOT
aas_prime_slot
        jsr audio_slot_base
        lda ,x
        cmpa #$FF
        beq aas_prime_next
        cmpa #12
        bne aas_prime_wait
        lda audio_slot0
        cmpa #$FF
        bne aas_prime_next
aas_prime_wait
        tst 3,x
        bne aas_prime_next
        jsr audio_advance_slot
aas_prime_next
        inc AUDIO_WORK_SLOT
        lda AUDIO_WORK_SLOT
        cmpa #4
        blo aas_prime_slot
        rts
; Exact-change guard for the existing ten semantic poll fields. Queue and
; deferred-stop work still run even when no gameplay counter changed.
aas_dirty
        tst audio_poll_valid
        beq aas_dirty_yes
        tst AUDIO_Q_COUNT
        bne aas_dirty_yes
        tst audio_music_count
        bne aas_dirty_yes
        tst audio_stop_pending
        bne aas_dirty_yes
        lda AUDIO_GAME_DOTS
        cmpa audio_poll_dots
        lbne aas_dirty_yes
        lda AUDIO_GAME_BONUS
        cmpa audio_poll_bonus
        lbne aas_dirty_yes
        lda AUDIO_GAME_BOX
        cmpa audio_poll_box
        lbne aas_dirty_yes
        lda AUDIO_GAME_GATE
        cmpa audio_poll_gate
        lbne aas_dirty_yes
        lda AUDIO_GAME_DEATH
        cmpa audio_poll_death
        lbne aas_dirty_yes
        lda AUDIO_GAME_VEG
        cmpa audio_poll_veg
        lbne aas_dirty_yes
        lda AUDIO_GAME_RELEASE
        cmpa audio_poll_release
        lbne aas_dirty_yes
        lda AUDIO_GAME_SPECIAL
        cmpa audio_poll_special
        lbne aas_dirty_yes
        lda AUDIO_GAME_EXTRA
        cmpa audio_poll_extra
        lbne aas_dirty_yes
        lda AUDIO_GAME_STAGE
        cmpa audio_poll_stage
        lbne aas_dirty_yes
        andcc #$FE
        rts
aas_dirty_yes
        orcc #1
        rts

; @audit {"id":"adaptive-audio-clock","kind":"scratch","symbol":"audio_adaptive_last","width":2,"mapping":"physical-page-3D","phases":["foreground"],"owner":"adaptive foreground audio service","lifetime":"Raw snapshot retained between services; delta initialized before each elapsed scan; late flag retained until explicit rebase.","initialization":"aas_rebase initializes last and late; aas_elapsed initializes delta before any consumer","clobbers":"API advances only pre-existing voices; new admissions are primed separately and never aged through older elapsed ticks."}
audio_adaptive_last rmb 2
; @audit {"id":"adaptive-audio-delta","kind":"scratch","symbol":"audio_adaptive_delta","width":2,"mapping":"physical-page-3D","phases":["foreground"],"owner":"adaptive foreground audio service","lifetime":"Bounded elapsed VBlank count for one API call only.","initialization":"aas_elapsed writes delta before scanning slots","clobbers":"No decoder retains the value after the call."}
audio_adaptive_delta rmb 2
; @audit {"id":"adaptive-audio-late","kind":"scratch","symbol":"audio_adaptive_late","width":1,"mapping":"physical-page-3D","phases":["foreground"],"owner":"adaptive foreground audio service","lifetime":"Retained missed-deadline marker until explicit phase rebase.","initialization":"aas_rebase clears it","clobbers":"Overdue existing-note service sets it; no acceptance may treat a set flag as on-time delivery."}
audio_adaptive_late fcb 0
audio_adaptive_stage
        includebin "ladybug-adaptive-active.bin"
audio_adaptive_stage_end
