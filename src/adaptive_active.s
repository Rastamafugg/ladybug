; Isolated active phase: demo prefix $0300-$038E remains intact.
; DOC-002 source-contract mirror contract check_stage_clear profile=state: Set STAGE_PENDING once when DOTS_LEFT and BONUS_LEFT are both zero.
; DOC-002 source-contract mirror profile state Inputs: Current authoritative gameplay or presentation state; register arguments are named by the routine label and immediate caller
; DOC-002 source-contract mirror profile state Outputs: Updated authoritative state and condition codes used by the immediate caller
; DOC-002 source-contract mirror profile state Clobbers: A, B, D, X, Y, U, and condition codes unless a narrower source-local header is present
; DOC-002 source-contract mirror profile state Reads: Owned direct-page and page-$34 state needed for the operation
; DOC-002 source-contract mirror profile state Writes: Only the owned state fields and render intents required by the operation
; DOC-002 source-contract mirror profile state Side effects: May enqueue rendering work but does not publish FRONT
; DOC-002 source-contract mirror profile state Invariants: Authoritative state changes precede their render intents; framebuffer publication remains IRQ-owned
        pragma 6809
        include "adaptive_interface.inc"
        include "adaptive_reference.inc"
        include "ladybug_audio_symbols.inc"
HISTORY_A equ $BC04
HISTORY_B equ $BC94
STATE equ $BD24
AD_END_TIME equ $BD2E
AD_DUE_TIME equ $BD30
AD_FAULT_BYTE equ $BD3A
AD_COUNT_A_ACTIVE equ $BD38
AD_COUNT_B_ACTIVE equ $BD39
PRES_TIMER equ $00B0
        org $038F
        jmp adaptive_work
        jmp adaptive_tick_binding
        jmp adaptive_global_binding
        jmp adaptive_key_binding
        jmp adaptive_audio_binding
        jmp adaptive_render
        jmp check_stage_clear
check_stage_clear
        tst     STAGE_PENDING
        bne     csc_done
        lda     DOTS_LEFT
        bne     csc_done
        lda     BONUS_LEFT
        bne     csc_done
        inc     STAGE_PENDING
csc_done
        rts
adaptive_work
        clra
        jsr adaptive_audio_binding
        lda PRES_MODE
        cmpa #4
        beq aw_input_done
        jsr read_joystick
aw_input_done
        lda RENDER_FLAGS
        bita #$40
        beq aw_batch
        lda #1
        jsr adaptive_audio_binding
        jsr AD_APPEND_EXEC
        bcs aw_fault
        lda #1
        sta AD_BARRIER_FLAG
        ldd FB_COMMIT_SEQ
        std AD_BARRIER_COMMIT
        bra aw_compose
aw_batch
        ; Reserve a complete four-step batch in both histories. If a retained
        ; owner has more than four records, compose before advancing logic.
        lda AD_COUNT_A_ACTIVE
        cmpa #5
        bhs aw_compose
        lda AD_COUNT_B_ACTIVE
        cmpa #5
        bhs aw_compose
        jsr AD_BATCH_EXEC
        bcc aw_output
aw_compose
        jsr adaptive_render
        bcs aw_fault
        tst AD_END_TIME
        beq aw_output_commit
        ; Static rebuild time is not simulation time; preserve debt/history.
        jsr AD_CLOCK_EXEC
        std AD_LAST_TIME
        std AD_BEGIN_TIME
        std AD_DUE_TIME
        lda #3
        jsr adaptive_audio_binding
        lda #1
        jsr adaptive_audio_binding
aw_output_commit
        lda #2
        jsr adaptive_audio_binding
        lda FB_BACK_ID
        jsr AD_COMPLETE_EXEC
        jsr framebuffer_finish_back
        clr RENDER_FLAGS
        clr RENDER_FLAGS2
        clr RENDER_GATE_ID
        clr RENDER_GATE2_ID
        clr PLAYER_ERASED
        rts
aw_output
        lda #2
        jmp adaptive_audio_binding
aw_fault
        lda #1
        sta AD_FAULT_BYTE
        rts
adaptive_render
        jsr framebuffer_prepare_back
        bcs ar_bad
        lda #1
        sta FB_RENDER_ACTIVE
        clr ENEMY_CAPTURE_DIRTY
        jsr colour_prepare_nest
        jsr actor_closure_restore
        clr AD_END_TIME
        jsr hud_snapshot_capture_player
        lda FB_BACK_ID
        jsr AD_REDUCE_EXEC
        bcs ar_bad
        jsr actor_closure_draw
        andcc #$FE
        rts
ar_bad
        clr FB_RENDER_ACTIVE
        orcc #1
        rts
adaptive_audio_binding
        pshs a
        lda #$3D
        sta $FFA5
        puls a
        jsr AUDIO_ADAPTIVE_EXEC
        pshs a
        lda #$34
        sta $FFA5
        puls a,pc
adaptive_tick_binding
        ; LAST_FRAME is also the enemy movement parity source. Do not alter
        ; the IRQ's FRAMES or framebuffer committed sequence.
        lda AD_SIM_TIME+1
        sta LAST_FRAME
        anda #1
        sta PLAYER_TICK_PENDING
        tst PRES_MODE
        beq atb_live
        ldd PRES_TIMER
        addd #1
        std PRES_TIMER
        cmpd #3600
        bhs atb_demo_end
        jsr $0300
atb_live
        tst INITIAL_ENTRY_STATE
        beq atb_normal
        jsr player_animation_tick
        jsr initial_entry_tick
        ; State release cannot permit normal movement in this same batch.
        bra atb_popup_publish
atb_normal
        jsr finish_gate_animation
        jsr player_animation_tick
        jsr enemy_tick
        tst PICKUP_TIMER
        beq atb_no_popup
        jsr pickup_tick
        tst BONUS_LEFT
        beq atb_popup_publish
        jsr bonus_color_tick
atb_popup_publish
        ; Even timer-to-zero must publish the restored player before catch-up.
        lda #1
        bra atb_done
atb_no_popup
        tst DEATH_STATE
        bne atb_after_player
        tst PLAYER_TICK_PENDING
        beq atb_after_player
        clr PLAYER_TICK_PENDING
        jsr player_tick
        jsr enemy_collect
atb_after_player
        tst DEATH_STATE
        bne atb_after_timers
        tst BONUS_LEFT
        beq atb_bonus_done
        jsr bonus_color_tick
atb_bonus_done
        tst PICKUP_TIMER
        bne atb_after_timers     ; collection onset holds the perimeter too
        jsr perimeter_timer_tick
atb_after_timers
        jsr rng_next
        tst DEATH_STATE
        beq atb_barrier
        jsr death_tick
atb_barrier
        ; Never catch up through a mandatory transient or a static handoff.
        lda INITIAL_ENTRY_STATE
        ora DEATH_STATE
        ora PICKUP_TIMER
        ora STAGE_PENDING
        ora RENDER_GATE_ID
        ora RENDER_GATE2_ID
        beq atb_done
        lda #1
atb_done
        pshs a
        lda #1
        jsr adaptive_audio_binding
        puls a,pc
atb_demo_end
        lda #1
        rts
adaptive_global_binding
        pshs a
        ldd RENDER_FLAGS
        pshs d
        ldb ENEMY_RENDER_FLAGS
        pshs b
        lda 3,s
        cmpa #3
        bne agb_not_stage
        inc AD_END_TIME
        ldb #9
        stb ENEMY_RENDER_FLAGS
agb_not_stage
        ldx #agb_masks
        ldb #3
        mul
        leax d,x
        lda ,x+
        anda RENDER_FLAGS
        sta RENDER_FLAGS
        lda ,x+
        anda RENDER_FLAGS2
        sta RENDER_FLAGS2
        lda ,x
        anda ENEMY_RENDER_FLAGS
        sta ENEMY_RENDER_FLAGS
        clr RENDER_GATE_ID
        clr RENDER_GATE2_ID
        jsr colour_prepare_nest
        jsr roam_mark_underlay
        jsr frame_render_background
        puls b
        stb ENEMY_RENDER_FLAGS
        jsr adaptive_draw_hud_intents
        puls d
        std RENDER_FLAGS
        puls a,pc
agb_masks
        fcb $08,$10,$18
        fcb $06,0,0
        fcb 0,$0A,0
        fcb $40,0,$FF

adaptive_key_binding
        ; Record will be reloaded before the next key and complete caller
        ; intents restored by adaptive_reduce. Copy secondary gate into the
        ; primary lane before suppressing the secondary compositor call.
        tfr a,b
        pshs b
        lda RENDER_FLAGS
        pshs a
        lda RENDER_FLAGS2
        pshs a
        lda 2,s
        tfr a,b
        cmpa #4
        bne akb_primary
        ldd RENDER_GATE2_ID
        std RENDER_GATE_ID
        lda RENDER_GATE2_STYLE
        sta RENDER_GATE_STYLE
        ldb #3
akb_primary
        cmpb #3
        beq akb_gate
        clr RENDER_GATE_ID
akb_gate
        clr RENDER_GATE2_ID
        ldx #akb_masks
        lslb
        abx
        ldd ,x
        std RENDER_FLAGS
        clr ENEMY_RENDER_FLAGS
        jsr roam_mark_underlay
        lda RENDER_FLAGS
        cmpa #RF_DOT
        bne akb_finish
        bsr pickup_key_prepare
akb_finish
        jsr frame_render_background
        jsr adaptive_draw_hud_intents
        puls a
        sta RENDER_FLAGS2
        puls a
        sta RENDER_FLAGS
        puls b
        rts

; Repaint only shared HUD groups named by the restored gameplay render intents.
; The player snapshot was captured once before AD_REDUCE_EXEC.
adaptive_draw_hud_intents
        lda RENDER_FLAGS
        anda #RF_HUD|RF_LIVES
        lsra
        pshs a
        lda RENDER_FLAGS2
        bita #RF2_MULTIPLIER
        beq adhi_letter
        lda ,s
        ora #PRESENTATION_HUD_DRAW_MULTIPLIER
        sta ,s
adhi_letter
        lda RENDER_FLAGS2
        bita #RF2_LETTER
        beq adhi_dispatch
        lda RENDER_LETTER_Y
        cmpa #PRESENTATION_HUD_SPECIAL_PROGRESS_Y
        beq adhi_special
        cmpa #PRESENTATION_HUD_EXTRA_PROGRESS_Y
        bne adhi_dispatch
        lda ,s
        ora #PRESENTATION_HUD_DRAW_EXTRA
        sta ,s
        bra adhi_dispatch
adhi_special
        lda ,s
        ora #PRESENTATION_HUD_DRAW_SPECIAL
        sta ,s
adhi_dispatch
        lda ,s+
        beq adhi_done
        clrb
        jsr draw_shared_hud
adhi_done
        rts
akb_masks
        fcb $20,0,$10,0,0,$04,0,0

; PERF-008 keyed pickup footprint, gate-intersection, and nest repair.
pickup_key_prepare
        jsr pickup_prepare_removed
        beq pk_done
        clr GATE_COPY_COUNT
pk_gate
        lda GATE_COPY_COUNT
        ldb #GATE_ENTITY_RECORD_SIZE
        mul
        addd #GATE_ENTITY_LISTS
        tfr d,y
        lda PLAYER_CELL_X
        cmpa ,y
        blo pk_gate_next
        deca
        cmpa 2,y
        bhi pk_gate_next
        lda PLAYER_CELL_Y
        cmpa 1,y
        blo pk_gate_next
        deca
        cmpa 3,y
        bhi pk_gate_next
        lda GATE_COPY_COUNT
        inca
        cmpa GATE_ANIM_ID
        beq pk_gate_next
        sta RENDER_GATE_ID
        deca
        jsr draw_gate
        jsr draw_gate_entities
pk_gate_next
        inc GATE_COPY_COUNT
        lda GATE_COPY_COUNT
        cmpa #MAZE_GATE_COUNT
        blo pk_gate
        clr RENDER_GATE_ID
        clr RENDER_FLAGS
        jsr pickup_prepare_nest
        bne pk_done
        andb #$FB
        cmpb #10
        bne pk_done
        lda #8
        sta ENEMY_RENDER_FLAGS
pk_done
        rts
adaptive_active_end
