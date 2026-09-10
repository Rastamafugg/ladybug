;==============================================================================
; 6309_benchmark.s — isolated 6809/6309 instruction benchmark ROM.
;
; The source is assembled twice by scripts/benchmark_6309.py:
;   baseline: lwasm -9, only portable 6809 instructions
;   candidate: lwasm -3, selected 6309 instructions under BENCH_CANDIDATE
;
; No Ladybug production ABI, MMU state, framebuffer, or loader is used here.
; Results and fixtures live in ordinary RAM so the monitor can inspect them.
;==============================================================================

        pragma  nodollarlocal

RESULT_BASE             equ $0200
RESULT_VARIANT          equ RESULT_BASE+4
RESULT_COPY_STATUS      equ RESULT_BASE+$10
RESULT_Q_STATUS         equ RESULT_BASE+$11
RESULT_MASK_STATUS      equ RESULT_BASE+$12
RESULT_W_STATUS         equ RESULT_BASE+$13

COPY_SRC                equ $0400
COPY_DST                equ $0500
COPY_LEN                equ 64
Q_SRC                   equ $0600
Q_DST                   equ $0610
MASK_BYTE               equ $0620
MASK_GUARD              equ $0621
W_SRC                   equ $0630
W_DST                   equ $0633
W_GUARD                 equ $0635

        org     $C000
        fcc     "DK"

entry
        orcc    #$50
        lds     #$5FFE
        ldx     #RESULT_BASE
        ldb     #$40
clear_results
        clr     ,x+
        decb
        bne     clear_results

        IFDEF   BENCH_CANDIDATE
        lda     #$C3
        ELSE
        lda     #$B9
        ENDC
        sta     RESULT_VARIANT
        jsr     init_fixtures
        jmp     benchmark_start

; The runner starts its cycle window at each *_start label and ends it at the
; corresponding *_timed_end label. Host-side verification runs at the terminal
; marker so the CPU path under test is not mixed with oracle subroutines.
benchmark_start

case_copy_start
        IFDEF   BENCH_CANDIDATE
        ldx     #COPY_SRC
        ldy     #COPY_DST
        ldw     #COPY_LEN
        tfm     x+,y+
        ELSE
        ldx     #COPY_SRC
        ldy     #COPY_DST
        ldb     #COPY_LEN
copy_loop
        lda     ,x+
        sta     ,y+
        decb
        bne     copy_loop
        ENDC
case_copy_timed_end
        nop

case_q_start
        IFDEF   BENCH_CANDIDATE
        ldq     Q_SRC
        stq     Q_DST
        ELSE
        lda     Q_SRC
        sta     Q_DST
        lda     Q_SRC+1
        sta     Q_DST+1
        lda     Q_SRC+2
        sta     Q_DST+2
        lda     Q_SRC+3
        sta     Q_DST+3
        ENDC
case_q_timed_end
        nop

case_mask_start
        IFDEF   BENCH_CANDIDATE
        oim     #$0F,MASK_BYTE
        ELSE
        lda     MASK_BYTE
        ora     #$0F
        sta     MASK_BYTE
        ENDC
case_mask_timed_end
        nop

case_w_start
        IFDEF   BENCH_CANDIDATE
        ldw     W_SRC
        stw     W_DST
        ELSE
        ldd     W_SRC
        std     W_DST
        ENDC
case_w_timed_end
        nop

benchmark_done
        bra     benchmark_done

;------------------------------------------------------------------------------
; Fixture setup

init_fixtures
        ldx     #COPY_SRC
        lda     #$11
        ldb     #COPY_LEN
init_copy
        sta     ,x+
        adda    #$07
        decb
        bne     init_copy

        lda     #$A5
        sta     COPY_DST-1
        ldx     #COPY_DST
        ldb     #COPY_LEN
fill_copy
        sta     ,x+
        decb
        bne     fill_copy
        lda     #$5A
        sta     COPY_DST+COPY_LEN

        ldd     #$1234
        std     Q_SRC
        ldd     #$5678
        std     Q_SRC+2
        lda     #$CC
        sta     Q_DST-1
        sta     Q_DST+4
        sta     W_DST-1
        sta     W_GUARD

        lda     #$A0
        sta     MASK_BYTE
        lda     #$5A
        sta     MASK_GUARD

        ldd     #$1234
        std     W_SRC
        rts

;------------------------------------------------------------------------------
; Correctness oracles. Zero means pass, one means fail.

verify_copy
        ldx     #COPY_SRC
        ldy     #COPY_DST
        ldb     #COPY_LEN
verify_copy_loop
        lda     ,x+
        cmpa    ,y+
        bne     verify_copy_fail
        decb
        bne     verify_copy_loop
        lda     COPY_DST-1
        cmpa    #$A5
        bne     verify_copy_fail
        lda     COPY_DST+COPY_LEN
        cmpa    #$5A
        bne     verify_copy_fail
        clr     RESULT_COPY_STATUS
        rts
verify_copy_fail
        lda     #$01
        sta     RESULT_COPY_STATUS
        rts

verify_q
        lda     Q_SRC
        cmpa    Q_DST
        bne     verify_q_fail
        lda     Q_SRC+1
        cmpa    Q_DST+1
        bne     verify_q_fail
        lda     Q_SRC+2
        cmpa    Q_DST+2
        bne     verify_q_fail
        lda     Q_SRC+3
        cmpa    Q_DST+3
        bne     verify_q_fail
        lda     Q_DST-1
        cmpa    #$CC
        bne     verify_q_fail
        lda     Q_DST+4
        cmpa    #$CC
        bne     verify_q_fail
        clr     RESULT_Q_STATUS
        rts
verify_q_fail
        lda     #$01
        sta     RESULT_Q_STATUS
        rts

verify_mask
        lda     MASK_BYTE
        cmpa    #$AF
        bne     verify_mask_fail
        lda     MASK_GUARD
        cmpa    #$5A
        bne     verify_mask_fail
        clr     RESULT_MASK_STATUS
        rts
verify_mask_fail
        lda     #$01
        sta     RESULT_MASK_STATUS
        rts

verify_w
        ldd     W_DST
        cmpd    #$1234
        bne     verify_w_fail
        lda     W_DST-1
        cmpa    #$CC
        bne     verify_w_fail
        lda     W_GUARD
        cmpa    #$CC
        bne     verify_w_fail
        clr     RESULT_W_STATUS
        rts
verify_w_fail
        lda     #$01
        sta     RESULT_W_STATUS
        rts

        end
