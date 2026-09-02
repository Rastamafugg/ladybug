; FEAT-006 GMC SN76489 foreground runtime.
; The assembled image is copied to physical page $3D.  The first bounded
; engine section is copied to low RAM $0300 after presentation handoff.
; Command data remains at its absolute page-$3D address.
        pragma  nodollarlocal,6809
        setdp   $00

PAR5        equ $FFA5
GIME_INIT0  equ $FF90
SND_DATA    equ $FF51
PIA1_CRA    equ $FF01
PIA1_CRB    equ $FF03
PIA2_CRB    equ $FF23
AUDIO_PAGE  equ $3D
AUDIO_RAM   equ $0300

AUDIO_Q_HEAD       equ $00EC
AUDIO_Q_TAIL       equ $00ED
AUDIO_Q_COUNT      equ $00EE
AUDIO_Q_OVERFLOW   equ $00EF
AUDIO_INSTALLED    equ $00F0
AUDIO_Q_DATA       equ $00F1
AUDIO_SAVED_ID     equ $00F9
AUDIO_SAVED_PARAM  equ $00FA
AUDIO_WORK_SLOT    equ $00FB
AUDIO_WORK_VOICE   equ $00FC
AUDIO_MIX_COUNT    equ $00FD
AUDIO_BEST_SLOT    equ $00FE
AUDIO_BEST_PRI     equ $00FF

; Slot layout: id, priority, policy, wait, stream pointer, three periods,
; three attenuations, noise control, noise attenuation, padding.
AUDIO_SLOT_BYTES equ 28

        org     $A000

audio_engine_start
        lbra    audio_service_impl
audio_init_entry
        lbra    audio_init_impl
audio_enqueue_entry
        lbra    audio_enqueue_impl

audio_service_impl
        tst     AUDIO_INSTALLED
        beq     audio_service_done
        lda     #AUDIO_PAGE
        sta     PAR5
        lda     #$6C
        sta     GIME_INIT0
        jsr     audio_select_gmc
        jsr     audio_poll_gameplay
        lbsr    audio_process_queue
        lbsr    audio_advance_all
        lbsr    audio_mix
        jsr     audio_mix_write
        lda     #$68
        sta     GIME_INIT0
        lda     #$34
        sta     PAR5
audio_service_done
        rts

audio_init_impl
        clr     AUDIO_INSTALLED
        lda     #AUDIO_PAGE
        sta     PAR5
        lda     #$6C
        sta     GIME_INIT0
        clr     AUDIO_Q_HEAD
        clr     AUDIO_Q_TAIL
        clr     AUDIO_Q_COUNT
        clr     AUDIO_Q_OVERFLOW
        clr     audio_poll_valid
        clr     AUDIO_WORK_SLOT
audio_init_slot_loop
        lbsr    audio_slot_base
        lda     #$FF
        sta     ,x
        clr     1,x
        clr     2,x
        clr     3,x
        lda     #1
        sta     6,x
        clr     7,x
        sta     8,x
        clr     9,x
        sta     10,x
        clr     11,x
        lda     #15
        sta     12,x
        sta     13,x
        sta     14,x
        clr     15,x
        sta     16,x
        inc     AUDIO_WORK_SLOT
        lda     AUDIO_WORK_SLOT
        cmpa    #4
        blo     audio_init_slot_loop
        lbsr    audio_mix_clear
        jsr     audio_mix_write
        lda     #$68
        sta     GIME_INIT0
        lda     #$34
        sta     PAR5
        lda     #6
        clrb
        lbsr    audio_enqueue_impl
        lda     #1
        sta     AUDIO_INSTALLED
        rts

audio_enqueue_impl
        cmpa    #18
        bhs     audio_enqueue_drop
audio_enqueue_store
        sta     AUDIO_SAVED_ID
        stb     AUDIO_SAVED_PARAM
        ldb     AUDIO_Q_COUNT
        cmpb    #4
        bhs     audio_enqueue_drop
        ldb     AUDIO_Q_TAIL
        ldx     #AUDIO_Q_DATA
        lda     AUDIO_SAVED_ID
        sta     b,x
        incb
        lda     AUDIO_SAVED_PARAM
        sta     b,x
        lda     AUDIO_Q_TAIL
        adda    #2
        anda    #7
        sta     AUDIO_Q_TAIL
        inc     AUDIO_Q_COUNT
        rts
audio_enqueue_drop
        lda     AUDIO_Q_OVERFLOW
        cmpa    #$FF
        beq     audio_enqueue_done
        inca
        sta     AUDIO_Q_OVERFLOW
audio_enqueue_done
        rts

audio_process_queue
audio_process_next
        tst     AUDIO_Q_COUNT
        beq     audio_process_done
        ldb     AUDIO_Q_HEAD
        ldx     #AUDIO_Q_DATA
        lda     b,x
        sta     AUDIO_SAVED_ID
        incb
        lda     b,x
        sta     AUDIO_SAVED_PARAM
        lda     AUDIO_Q_HEAD
        adda    #2
        anda    #7
        sta     AUDIO_Q_HEAD
        dec     AUDIO_Q_COUNT
        lbsr    audio_admit
        bra     audio_process_next
audio_process_done
        rts

audio_admit
        lda     AUDIO_SAVED_ID
        ldb     #8
        mul
        ldx     #gmc_cue_descriptors
        leax    d,x
        tfr     x,u
        lda     ,x
        sta     audio_scratch
        lda     2,x
        anda    #$80
        beq     audio_admit_effect
        clr     AUDIO_WORK_SLOT
        bra     audio_admit_start
audio_admit_effect
        lda     #1
        sta     AUDIO_WORK_SLOT
audio_find_free
        lbsr    audio_slot_base
        lda     ,x
        cmpa    #$FF
        beq     audio_admit_start
        inc     AUDIO_WORK_SLOT
        lda     AUDIO_WORK_SLOT
        cmpa    #4
        blo     audio_find_free
        lda     #1
        sta     AUDIO_WORK_SLOT
        lda     #$FF
        sta     AUDIO_BEST_PRI
        lda     #$FF
        sta     AUDIO_BEST_SLOT
audio_find_low
        lbsr    audio_slot_base
        lda     ,x
        cmpa    #$FF
        beq     audio_admit_start
        lda     1,x
        cmpa    AUDIO_BEST_PRI
        bhs     audio_find_low_next
        sta     AUDIO_BEST_PRI
        lda     AUDIO_WORK_SLOT
        sta     AUDIO_BEST_SLOT
audio_find_low_next
        inc     AUDIO_WORK_SLOT
        lda     AUDIO_WORK_SLOT
        cmpa    #4
        blo     audio_find_low
        lda     audio_scratch
        lsra
        lsra
        lsra
        lsra
        lsra
        cmpa    AUDIO_BEST_PRI
        bls     audio_admit_drop
        lda     AUDIO_BEST_SLOT
        sta     AUDIO_WORK_SLOT
        bra     audio_admit_start
audio_admit_start
        lda     audio_scratch
        lsra
        lsra
        lsra
        lsra
        lsra
        sta     AUDIO_BEST_PRI
        lbsr    audio_slot_base
        tfr     x,y
        sta     1,y
        lda     ,u
        sta     2,y
        lda     AUDIO_SAVED_ID
        sta     ,y
        clr     3,y
        ldd     4,u
        std     4,y
        lda     #1
        sta     6,y
        clr     7,y
        sta     8,y
        clr     9,y
        sta     10,y
        clr     11,y
        lda     #15
        sta     12,y
        sta     13,y
        sta     14,y
        clr     15,y
        sta     16,y
audio_admit_done
        rts
audio_admit_drop
        lda     AUDIO_Q_OVERFLOW
        cmpa    #$FF
        beq     audio_admit_done
        inca
        sta     AUDIO_Q_OVERFLOW
        rts

audio_slot_base
        ldb     AUDIO_WORK_SLOT
        aslb
        ldx     #audio_slot_base_table
        ldx     b,x
        rts

audio_advance_all
        clr     AUDIO_WORK_SLOT
audio_advance_next
        lbsr    audio_slot_base
        lda     ,x
        cmpa    #$FF
        beq     audio_advance_skip
        lda     3,x
        beq     audio_advance_stream
        dec     3,x
        bra     audio_advance_skip
audio_advance_stream
        lbsr    audio_advance_slot
audio_advance_skip
        inc     AUDIO_WORK_SLOT
        lda     AUDIO_WORK_SLOT
        cmpa    #4
        blo     audio_advance_next
        rts

audio_advance_slot
        tfr     x,y
        ldx     4,y
audio_command
        lda     ,x+
        lbeq    audio_command_end
        cmpa    #2
        beq     audio_command_wait
        cmpa    #$10
        blo     audio_command_other
        cmpa    #$13
        bhs     audio_command_other
        suba    #$10
        sta     AUDIO_WORK_VOICE
        lsla
        leau    6,y
        leau    a,u
        ldd     ,x++
        std     ,u
        leau    12,y
        lda     AUDIO_WORK_VOICE
        leau    a,u
        lda     ,x+
        sta     ,u
        bra     audio_command
audio_command_other
        cmpa    #$1C
        beq     audio_command_noise
        cmpa    #$1D
        beq     audio_command_noise_volume
        cmpa    #$1E
        beq     audio_command_mute
        bra     audio_command_end
audio_command_noise
        lda     ,x+
        sta     15,y
        lda     ,x+
        sta     16,y
        bra     audio_command
audio_command_noise_volume
        lda     ,x+
        sta     16,y
        bra     audio_command
audio_command_mute
        lda     ,x+
        sta     audio_scratch
        bita    #1
        beq     audio_mute_tone1
        lda     #15
        sta     12,y
audio_mute_tone1
        lda     audio_scratch
        bita    #2
        beq     audio_mute_tone2
        lda     #15
        sta     13,y
audio_mute_tone2
        lda     audio_scratch
        bita    #4
        beq     audio_mute_tone3
        lda     #15
        sta     14,y
audio_mute_tone3
        lda     audio_scratch
        bita    #8
        beq     audio_command
        lda     #15
        sta     16,y
        bra     audio_command
audio_command_wait
        lda     ,x+
        bne     audio_wait_valid
        lda     #1
audio_wait_valid
        sta     3,y
        stx     4,y
        rts
audio_command_end
        lda     #$FF
        sta     ,y
        rts

audio_mix
        lbsr    audio_mix_clear
        lda     #$FF
        sta     AUDIO_BEST_SLOT
        clr     AUDIO_BEST_PRI
        clr     AUDIO_WORK_SLOT
audio_mix_find_exclusive
        lbsr    audio_slot_base
        lda     ,x
        cmpa    #$FF
        beq     audio_mix_exclusive_next
        lda     2,x
        bita    #1
        beq     audio_mix_exclusive_next
        lda     1,x
        cmpa    AUDIO_BEST_PRI
        bls     audio_mix_exclusive_next
        sta     AUDIO_BEST_PRI
        lda     AUDIO_WORK_SLOT
        sta     AUDIO_BEST_SLOT
audio_mix_exclusive_next
        inc     AUDIO_WORK_SLOT
        lda     AUDIO_WORK_SLOT
        cmpa    #4
        blo     audio_mix_find_exclusive
        lda     AUDIO_BEST_SLOT
        cmpa    #$FF
        beq     audio_mix_all_slots
        sta     AUDIO_WORK_SLOT
        lbsr    audio_slot_base
        lbsr    audio_mix_slot
        rts
audio_mix_all_slots
        clr     AUDIO_WORK_SLOT
audio_mix_all_next
        lbsr    audio_slot_base
        lda     ,x
        cmpa    #$FF
        beq     audio_mix_all_skip
        lbsr    audio_mix_slot
audio_mix_all_skip
        inc     AUDIO_WORK_SLOT
        lda     AUDIO_WORK_SLOT
        cmpa    #4
        blo     audio_mix_all_next
        rts

audio_mix_clear
        ldx     #audio_mix_periods
        ldd     #$0100
        std     ,x
        std     2,x
        std     4,x
        ldx     #audio_mix_atten
        ldd     #$0F0F
        std     ,x
        sta     2,x
        ldx     #audio_mix_noise
        ldd     #$000F
        std     ,x
        clr     AUDIO_MIX_COUNT
        tst     AUDIO_INSTALLED
        bne     audio_mix_clear_done
        ldx     #audio_mix_shadow
        ldb     #11
        lda     #$55
audio_mix_shadow_init
        sta     ,x+
        decb
        bne     audio_mix_shadow_init
audio_mix_clear_done
        rts

audio_mix_slot
        tfr     x,y
        clr     AUDIO_WORK_VOICE
audio_mix_tone_next
        leau    12,y
        ldb     AUDIO_WORK_VOICE
        lda     b,u
        cmpa    #15
        bhs     audio_mix_tone_skip
        lda     AUDIO_MIX_COUNT
        cmpa    #3
        bhs     audio_mix_tone_skip
        sta     audio_scratch
        lsla
        tfr     a,b
        clra
        tfr     d,u
        leax    6,y
        ldb     AUDIO_WORK_VOICE
        aslb
        ldd     b,x
        std     audio_mix_periods,u
        ldb     AUDIO_WORK_VOICE
        leax    12,y
        lda     b,x
        ldx     #audio_mix_atten
        ldb     audio_scratch
        sta     b,x
        inc     AUDIO_MIX_COUNT
audio_mix_tone_skip
        inc     AUDIO_WORK_VOICE
        lda     AUDIO_WORK_VOICE
        cmpa    #3
        blo     audio_mix_tone_next
        lda     16,y
        cmpa    #15
        bhs     audio_mix_slot_done
        ldx     #audio_mix_noise
        lda     15,y
        sta     ,x
        lda     16,y
        sta     1,x
audio_mix_slot_done
        rts

audio_engine_end

; Page-$3D installer. The presentation handoff maps this page and jumps here;
; the routine copies only the bounded engine, restores PAR5, and initializes it.
audio_install_page
        ldx     #$A000
        ldy     #$0300
audio_install_loop
        lda     ,x+
        sta     ,y+
        cmpx    #audio_engine_end
        blo     audio_install_loop
        ; Tail-enter the copied initializer before changing PAR5.  Its RTS
        ; consumes the presentation caller's existing return address after
        ; restoring the normal game-state mapping.
        jmp     $0303

; Semantic event polling runs from mapped page $3D, outside the copied
; foreground engine. It snapshots authoritative gameplay state and enqueues
; one cue per detected transition before the queue is admitted and mixed.
AUDIO_GAME_DOTS     equ $0025
AUDIO_GAME_STAGE    equ $0026
AUDIO_GAME_BONUS    equ $0033
AUDIO_GAME_SPECIAL  equ $003C
AUDIO_GAME_EXTRA    equ $003D
AUDIO_GAME_BOX      equ $004B
AUDIO_GAME_DEATH    equ $004D
AUDIO_GAME_GATE     equ $0019
AUDIO_GAME_RELEASE  equ $0059
AUDIO_GAME_VEG      equ $005A

audio_poll_gameplay
        tst     audio_poll_valid
        bne     audio_poll_scan
        lda     AUDIO_GAME_DOTS
        sta     audio_poll_dots
        lda     AUDIO_GAME_BONUS
        sta     audio_poll_bonus
        lda     AUDIO_GAME_BOX
        sta     audio_poll_box
        lda     AUDIO_GAME_GATE
        sta     audio_poll_gate
        lda     AUDIO_GAME_DEATH
        sta     audio_poll_death
        lda     AUDIO_GAME_VEG
        sta     audio_poll_veg
        lda     AUDIO_GAME_RELEASE
        sta     audio_poll_release
        lda     AUDIO_GAME_SPECIAL
        sta     audio_poll_special
        lda     AUDIO_GAME_EXTRA
        sta     audio_poll_extra
        lda     AUDIO_GAME_STAGE
        sta     audio_poll_stage
        inc     audio_poll_valid
        rts
audio_poll_scan
        lda     AUDIO_GAME_DOTS
        cmpa    audio_poll_dots
        bhs     audio_poll_dots_saved
        lda     #3
        jsr     audio_poll_enqueue
audio_poll_dots_saved
        lda     AUDIO_GAME_DOTS
        sta     audio_poll_dots

        lda     AUDIO_GAME_BONUS
        cmpa    audio_poll_bonus
        bhs     audio_poll_bonus_saved
        lda     #2
        jsr     audio_poll_enqueue
audio_poll_bonus_saved
        lda     AUDIO_GAME_BONUS
        sta     audio_poll_bonus

        lda     AUDIO_GAME_BOX
        cmpa    audio_poll_box
        beq     audio_poll_box_saved
        lda     AUDIO_GAME_DEATH
        bne     audio_poll_box_saved
        lda     #4
        jsr     audio_poll_enqueue
audio_poll_box_saved
        lda     AUDIO_GAME_BOX
        sta     audio_poll_box

        lda     AUDIO_GAME_GATE
        beq     audio_poll_gate_saved
        tst     audio_poll_gate
        bne     audio_poll_gate_saved
        lda     #0
        jsr     audio_poll_enqueue
audio_poll_gate_saved
        lda     AUDIO_GAME_GATE
        sta     audio_poll_gate

        lda     AUDIO_GAME_VEG
        cmpa    #2
        bne     audio_poll_veg_saved
        lda     audio_poll_veg
        cmpa    #1
        bne     audio_poll_veg_saved
        lda     #1
        jsr     audio_poll_enqueue
audio_poll_veg_saved
        lda     AUDIO_GAME_VEG
        sta     audio_poll_veg

        lda     AUDIO_GAME_RELEASE
        cmpa    audio_poll_release
        bls     audio_poll_release_saved
        lda     #5
        jsr     audio_poll_enqueue
audio_poll_release_saved
        lda     AUDIO_GAME_RELEASE
        sta     audio_poll_release

        lda     AUDIO_GAME_SPECIAL
        bne     audio_poll_special_saved
        tst     audio_poll_special
        beq     audio_poll_special_saved
        lda     #11
        jsr     audio_poll_enqueue
audio_poll_special_saved
        lda     AUDIO_GAME_SPECIAL
        sta     audio_poll_special

        lda     AUDIO_GAME_EXTRA
        bne     audio_poll_extra_saved
        tst     audio_poll_extra
        beq     audio_poll_extra_saved
        lda     #10
        jsr     audio_poll_enqueue
audio_poll_extra_saved
        lda     AUDIO_GAME_EXTRA
        sta     audio_poll_extra

        lda     AUDIO_GAME_STAGE
        bne     audio_poll_stage_pending
        bra     audio_poll_stage_saved
audio_poll_stage_pending
        tst     audio_poll_stage
        bne     audio_poll_stage_saved
        lda     AUDIO_GAME_DOTS
        bne     audio_poll_stage_saved
        lda     AUDIO_GAME_BONUS
        bne     audio_poll_stage_saved
        lda     #9
        jsr     audio_poll_enqueue
audio_poll_stage_saved
        lda     AUDIO_GAME_STAGE
        sta     audio_poll_stage

        lda     AUDIO_GAME_DEATH
        bne     audio_poll_death_pending
        bra     audio_poll_death_saved
audio_poll_death_pending
        tst     audio_poll_death
        bne     audio_poll_death_saved
        lda     #13
        jsr     audio_poll_enqueue
audio_poll_death_saved
        lda     AUDIO_GAME_DEATH
        sta     audio_poll_death
        rts

; The GMC and right joystick share the analog selector controls. Gameplay
; sampling leaves the analog master disabled; select the GMC before semantic
; polling so the break-before-make window remains bounded to input acquisition.
audio_select_gmc
        lda     #$34
        sta     PIA1_CRA
        lda     #$3C
        sta     PIA1_CRB
        sta     PIA2_CRB
        rts

; The stream stores each 10-bit period little-endian. Repack it into the
; SN76489 latch nibble and bits-4..9 continuation byte used by the proven
; keyboard cue tester. Keep the physical-channel loop in direct-page state;
; LDD owns B and must never also own the loop counter.
audio_mix_write
        ldx     #audio_mix_periods
        ldy     #audio_mix_atten
        ldu     #audio_mix_shadow
        clr     AUDIO_WORK_VOICE
audio_write_tone
        ldd     ,x++
        sta     audio_scratch+1
        lda     AUDIO_WORK_VOICE
        lsla
        lsla
        lsla
        lsla
        lsla
        adda    #$80
        sta     audio_scratch
        lda     audio_scratch+1
        anda    #$0F
        ora     audio_scratch
        cmpa    ,u
        beq     audio_write_tone_latch_done
        sta     ,u
        bsr     audio_write
audio_write_tone_latch_done
        lslb
        lslb
        lslb
        lslb
        stb     audio_scratch
        lda     audio_scratch+1
        lsra
        lsra
        lsra
        lsra
        ora     audio_scratch
        anda    #$3F
        cmpa    1,u
        beq     audio_write_tone_data_done
        sta     1,u
        bsr     audio_write
audio_write_tone_data_done
        lda     ,y+
        sta     audio_scratch+1
        lda     AUDIO_WORK_VOICE
        lsla
        lsla
        lsla
        lsla
        lsla
        adda    #$90
        ora     audio_scratch+1
        cmpa    2,u
        beq     audio_write_tone_atten_done
        sta     2,u
        bsr     audio_write
audio_write_tone_atten_done
        leau    3,u
        inc     AUDIO_WORK_VOICE
        lda     AUDIO_WORK_VOICE
        cmpa    #3
        blo     audio_write_tone
        ldx     #audio_mix_noise
        lda     ,x
        ora     #$E0
        cmpa    ,u
        beq     audio_write_noise_control_done
        sta     ,u
        bsr     audio_write
audio_write_noise_control_done
        lda     1,x
        ora     #$F0
        cmpa    1,u
        beq     audio_write_noise_atten_done
        sta     1,u
        bsr     audio_write
audio_write_noise_atten_done
audio_mix_write_done
        rts

; XRoar's GMC SN76489 accepts a write only after 32 reference-clock cycles.
; Four NOPs plus BSR/RTS overhead preserve the tester-proven minimum spacing.
audio_write
        sta     SND_DATA
        nop
        nop
        nop
        nop
        rts
audio_poll_enqueue
        clrb
        jsr     $0306
        rts

audio_poll_dots
        fcb     0
audio_poll_bonus
        fcb     0
audio_poll_box
        fcb     0
audio_poll_gate
        fcb     0
audio_poll_death
        fcb     0
audio_poll_veg
        fcb     0
audio_poll_release
        fcb     0
audio_poll_special
        fcb     0
audio_poll_extra
        fcb     0
audio_poll_stage
        fcb     0
audio_poll_valid
        fcb     0

        include "gmc_sound_data.inc"

audio_slot_base_table
        fdb     audio_slot0,audio_slot1,audio_slot2,audio_slot3

audio_slot0
        rmb     AUDIO_SLOT_BYTES
audio_slot1
        rmb     AUDIO_SLOT_BYTES
audio_slot2
        rmb     AUDIO_SLOT_BYTES
audio_slot3
        rmb     AUDIO_SLOT_BYTES

audio_mix_periods
        rmb     6
audio_mix_atten
        rmb     3
audio_mix_noise
        rmb     2
audio_scratch
        rmb     2

; Eleven output shadows reuse the padding in the first 28-byte slot record:
; three bytes per tone register triplet and two noise registers.
audio_mix_shadow equ audio_slot0+17

        end
