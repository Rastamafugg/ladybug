;==============================================================================
; 6309_ldq_stq_timing.s - RSCH-005 single-window LDQ/STQ controls.
;
; Assemble exactly one BENCH_* case per ROM.  Setup and fixture initialization
; occur before benchmark_start/case_start.  The measured window contains no
; loop and has one start and one end marker.
;==============================================================================

        pragma  nodollarlocal

RESULT_BASE             equ $0200
RESULT_SIGNATURE        equ RESULT_BASE
RESULT_CASE             equ RESULT_BASE+4

Q_SRC                   equ $2000
Q_DST                   equ $3000
Q_GUARD                 equ $3A00

        org     $C000
        fcc     "DK"
        jmp     entry

entry
        orcc    #$50
        lds     #$5FFE

        lda     #'R'
        sta     RESULT_SIGNATURE
        lda     #'5'
        sta     RESULT_SIGNATURE+1
        lda     #'Q'
        sta     RESULT_SIGNATURE+2
        lda     #'T'
        sta     RESULT_SIGNATURE+3

        lda     #$12
        sta     Q_SRC
        lda     #$34
        sta     Q_SRC+1
        lda     #$56
        sta     Q_SRC+2
        lda     #$78
        sta     Q_SRC+3

        lda     #$CC
        sta     Q_DST
        sta     Q_DST+1
        sta     Q_DST+2
        sta     Q_DST+3
        lda     #$5A
        sta     Q_GUARD

        IFDEF  BENCH_BOUNDARY
        lda     #0
        sta     RESULT_CASE
        ENDC
        IFDEF  BENCH_LDQ
        lda     #1
        sta     RESULT_CASE
        ldx     #Q_SRC
        ENDC
        IFDEF  BENCH_STQ
        lda     #2
        sta     RESULT_CASE
        ldy     #Q_DST
        ldq     Q_SRC
        ENDC
        IFDEF  BENCH_PAIR
        lda     #3
        sta     RESULT_CASE
        ldx     #Q_SRC
        ldy     #Q_DST
        ENDC
        IFDEF  BENCH_BYTE
        lda     #4
        sta     RESULT_CASE
        ldx     #Q_SRC
        ldy     #Q_DST
        ENDC

benchmark_start
case_start
        IFDEF  BENCH_BOUNDARY
        nop
        ENDC
        IFDEF  BENCH_LDQ
        ldq     ,x
        ENDC
        IFDEF  BENCH_STQ
        stq     ,y
        ENDC
        IFDEF  BENCH_PAIR
        ldq     ,x
        stq     ,y
        ENDC
        IFDEF  BENCH_BYTE
        lda     ,x
        sta     ,y
        lda     1,x
        sta     1,y
        lda     2,x
        sta     2,y
        lda     3,x
        sta     3,y
        ENDC
case_end
benchmark_done
        bra     benchmark_done

        end
