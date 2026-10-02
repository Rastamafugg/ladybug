from pathlib import Path
p=Path('src/enemy_runtime.s')
s=p.read_text()
old='''; Isolated BUG-087 fit candidate. The stage-local rate owner uses unassigned
; direct-page tail bytes; the accumulator is 8.8 source-pixel credit.
ENEMY_RATE_TIMER equ $00DF
ENEMY_RATE_BUCKET equ $00E0
ENEMY_RATE_ACCUM equ $00E1
ENEMY_RATE_ADDEND equ $00E3
ENEMY_RATE_DUE equ $00E5
'''
new='''; Isolated BUG-087 fit candidate. Shared stage-rate owner uses candidate
; direct-page tail bytes; fraction and two-pixel parity are independent state.
ENEMY_RATE_TIMER equ $00DF
ENEMY_RATE_BUCKET equ $00E0
ENEMY_RATE_FRAC_ACCUM equ $00E1
ENEMY_RATE_FRAC_ADDEND equ $00E2
ENEMY_RATE_PHASE equ $00E3
ENEMY_RATE_DUE equ $00E4
'''
assert s.count(old)==1
s=s.replace(old,new)
old='''; Isolated BUG-087 fit candidate, not production source. The rate addends are
; 8.8 pixel credits for one CoCo enemy_tick per arcade enemy dispatcher; that
; conversion remains unproved and must be supplied by arcade_timing_research.
; The shared accumulator mirrors the ROM's one step count applied to all active
; enemies. A two-pixel CoCo quantum is emitted whenever credit reaches $0200.
enemy_rate_reset
        lda     #96             ; source stage-start countdown; conversion gated
        sta     ENEMY_RATE_TIMER
        clr     ENEMY_RATE_BUCKET
        clr     ENEMY_RATE_ACCUM
        clr     ENEMY_RATE_ACCUM+1
        clr     ENEMY_RATE_DUE
        lbsr    enemy_rate_select
        rts

; Called once per admitted enemy simulation tick. The countdown/bucket are
; source-policy state, independent of BOX_TIMER and ENEMY_TIMER. Freeze skips
; spatial publication below but consumes this tick's due quantum.
enemy_rate_tick
        clr     ENEMY_RATE_DUE
        dec     ENEMY_RATE_TIMER
        bne     ert_accumulate
        lda     #60             ; source reload; CoCo/arcade clock mapping gated
        sta     ENEMY_RATE_TIMER
        lda     ENEMY_RATE_BUCKET
        cmpa    #$F0
        bhs     ert_accumulate
        inc     ENEMY_RATE_BUCKET
        lda     ENEMY_RATE_BUCKET
        anda    #$0F
        bne     ert_accumulate
        lbsr    enemy_rate_select
ert_accumulate
        ldd     ENEMY_RATE_ACCUM
        addd    ENEMY_RATE_ADDEND
        cmpd    #$0200
        blo     ert_store
        subd    #$0200
        lda     #1
        sta     ENEMY_RATE_DUE
ert_store
        std     ENEMY_RATE_ACCUM
        rts

; Default Easy/Medium only. STAGE 1-6 share offset 0; later offsets are
; source-derived. The model and later-part raw-frame conversion remain gates.
enemy_rate_select
        lda     STAGE
        cmpa    #7
        blo     ers_part_one_group
        cmpa    #18
        bhs     ers_late_parts
        suba    #7
        ldx     #enemy_rate_stage_offsets
        lda     a,x
        tfr     a,b
        bra     ers_offset_ready
ers_part_one_group
        clrb
        bra     ers_offset_ready
ers_late_parts
        ldb     #15
ers_offset_ready
        lda     ENEMY_RATE_BUCKET
        lsra
        lsra
        lsra
        lsra
        aba
        cmpa    #15
        bls     ers_rate_index_ready
        lda     #15
ers_rate_index_ready
        cmpa    #6
        blo     ers_rate_100
        cmpa    #12
        blo     ers_rate_133
        cmpa    #15
        blo     ers_rate_180
        ldd     #$01CC         ; 1 + 204/256 pixels per source dispatcher
        bra     ers_store
ers_rate_180
        ldd     #$0180         ; 1.5 pixels per source dispatcher
        bra     ers_store
ers_rate_133
        ldd     #$0133         ; 1 + 51/256 pixels per source dispatcher
        bra     ers_store
ers_rate_100
        ldd     #$0100
ers_store
        std     ENEMY_RATE_ADDEND
        rts

enemy_rate_stage_offsets
        fcb     6,8,5,7,9,10,11,8,12,13,14,15
'''
new='''; Isolated BUG-087 fit candidate, not production source. The one-byte fractional
; source-pixel accumulator is parameterized on one admitted enemy tick per
; arcade enemy dispatcher. That conversion remains an external acceptance gate.
; A shared phase preserves the arcade's common step count across active actors;
; each due CoCo move remains a two-pixel quantum.
enemy_rate_reset
        lda     #96             ; source stage-start countdown; conversion gated
        sta     ENEMY_RATE_TIMER
        clr     ENEMY_RATE_BUCKET
        clr     ENEMY_RATE_FRAC_ACCUM
        clr     ENEMY_RATE_PHASE
        clr     ENEMY_RATE_DUE
        lbsr    enemy_rate_select
        rts

; Timer/bucket are independent of BOX_TIMER and ENEMY_TIMER. Each tick adds a
; base source pixel and the selected fraction. The parity bit emits one CoCo
; quantum per two accumulated source pixels; a fractional carry contributes a
; second pixel and therefore always emits one quantum.
enemy_rate_tick
        clr     ENEMY_RATE_DUE
        dec     ENEMY_RATE_TIMER
        bne     ert_accumulate
        lda     #60             ; source reload; CoCo/arcade clock mapping gated
        sta     ENEMY_RATE_TIMER
        inc     ENEMY_RATE_BUCKET
        lda     ENEMY_RATE_BUCKET
        anda    #$0F
        bne     ert_accumulate
        lbsr    enemy_rate_select ert_accumulate
        lda     ENEMY_RATE_FRAC_ACCUM
        adda    ENEMY_RATE_FRAC_ADDEND
        sta     ENEMY_RATE_FRAC_ACCUM
        bcs     ert_extra_pixel
        tst     ENEMY_RATE_PHASE
        beq     ert_base_pixel
        clr     ENEMY_RATE_PHASE
        lda     #1
        sta     ENEMY_RATE_DUE
        rts
ert_base_pixel
        inc     ENEMY_RATE_PHASE
        rts ert_extra_pixel
        lda     #1
        sta     ENEMY_RATE_DUE
        rts

; Default Easy/Medium only. STAGE is one-based, with the arcade's byte-wrap
; counter 0 mapping back to offset 0. Later parts clamp at index 15.
enemy_rate_select
        lda     STAGE
        beq     ers_counter_wrap
        cmpa    #18
        bhs     ers_late_parts
        deca
        ldx     #enemy_rate_stage_offsets
        lda     a,x
        tfr     a,b
        bra     ers_offset_ready
ers_counter_wrap
        clrb
        bra     ers_offset_ready
ers_late_parts
        ldb     #15
ers_offset_ready
        lda     ENEMY_RATE_BUCKET
        lsra
        lsra
        lsra
        lsra
        pshs    b
        adda    ,s+
        cmpa    #15
        bls     ers_rate_index_ready
        lda     #15
ers_rate_index_ready
        cmpa    #6
        blo     ers_rate_100
        cmpa    #12
        blo     ers_rate_133
        cmpa    #15
        blo     ers_rate_150
        lda     #$CC         ; source code $18: 1 + 204/256 pixels
        bra     ers_store
ers_rate_150
        lda     #$80         ; source code $15: 1.5 pixels
        bra     ers_store
ers_rate_133
        lda     #$33         ; source code $12: 1 + 51/256 pixels
        bra     ers_store
ers_rate_100
        clra
ers_store
        sta     ENEMY_RATE_FRAC_ADDEND
        rts

enemy_rate_stage_offsets
        fcb     0,2,4,1,3,5,6,8,5,7,9,10,11,8,12,13,14
'''
assert s.count(old)==1
s=s.replace(old,new)
# Fix two adjacent label separators introduced intentionally as compact text.
s=s.replace('lbsr    enemy_rate_select\\ ert_accumulate','lbsr    enemy_rate_select\nert_accumulate')
s=s.replace('rts\\ ert_extra_pixel','rts\nert_extra_pixel')
p.write_text(s)
