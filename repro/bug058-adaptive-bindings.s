; BUG-058 isolated real-call binding fit; not registered in the game build.
; Reference symbol include is generated from compression6963da7 maps.
; Assembly validates placement only; phase installers/driver remain unbound.
        pragma 6809
        include "adaptive_reference.inc"
AD_SIM equ $BD26
PRES_TIMER equ $00B0

; Copied-engine tail. Live installs must retain this after demo/level owners.
        org $05DE
adaptive_tick_binding
        ; LAST_FRAME is also the enemy movement parity source. Do not alter
        ; the IRQ's FRAMES or framebuffer committed sequence.
        lda AD_SIM+1
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
        bra atb_barrier
atb_normal
        jsr finish_gate_animation
        jsr pickup_tick
        jsr player_animation_tick
        jsr enemy_tick
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
        rts
atb_demo_end
        lda #1
        rts
adaptive_tick_binding_end
; A=action and X=elapsed; always-mapped gateway preserves its return path
; while the banked admission API owns PAR5. Its installer is still unbound.
adaptive_audio_binding
        pshs a
        lda #$3D
        sta $FFA5
        puls a
        jsr $B62B
        pshs a
        lda #$34
        sta $FFA5
        puls a,pc
adaptive_copied_bindings_end

; Old resident mainloop region. The driver is not installed in this fixture.
        org $C0FF
adaptive_input_binding
        lda PRES_MODE
        cmpa #4
        beq aib_done
        jmp read_joystick
aib_done
        rts

adaptive_global_binding
        ldb RENDER_FLAGS
        pshs b
        ldb RENDER_FLAGS2
        pshs b
        ldb ENEMY_RENDER_FLAGS
        pshs b
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
        puls b
        stb RENDER_FLAGS2
        puls b
        stb RENDER_FLAGS
        rts
agb_masks
        fcb $08,$10,$18
        fcb $06,0,0
        fcb 0,$0A,0
        fcb $40,0,0

adaptive_key_binding
        ; Record will be reloaded before the next key and complete caller
        ; intents restored by adaptive_reduce. Copy secondary gate into the
        ; primary lane before suppressing the secondary compositor call.
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
        jmp frame_render_background
akb_masks
        fcb $20,0,$10,0,0,$04,0,0
adaptive_install_bindings
        lda #$3D
        sta $FFA5
        jmp $DFE8
adaptive_resident_bindings_end

; Existing resident tail has24 free bytes. Stage data in the audio page's
; free tail, then copy only after the bootstrap/phase owner has retired.
        org $DFE8
adaptive_install_copy
        ldx #$B6B7
        ldu #$05DE
        ldb #134
aic_copy
        lda ,x+
        sta ,u+
        decb
        bne aic_copy
        lda #$34
        sta $FFA5
        rts
adaptive_install_copy_end
