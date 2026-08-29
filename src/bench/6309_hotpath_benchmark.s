;==============================================================================
; 6309_hotpath_benchmark.s - source-aligned Ladybug renderer work shapes.
;
; The portable and candidate variants use identical fixtures.  The fixture
; shapes mirror save_player/restore_player and the phase-zero roaming copy:
; eight contiguous bytes per row followed by the production 152-byte stride.
; The LDQ/STQ case mirrors two four-byte pulls/stores per row.  The OIM case
; covers nibble-preserving merges that are safe to express as OR-immediate;
; mixed transparency remains a rejection case in the host oracle.
;==============================================================================

        pragma  nodollarlocal

RESULT_BASE             equ $0200
RESULT_SIGNATURE        equ RESULT_BASE
RESULT_VARIANT          equ RESULT_BASE+4
RESULT_TFM_STATUS       equ RESULT_BASE+$10
RESULT_Q_STATUS         equ RESULT_BASE+$11
RESULT_OIM_STATUS       equ RESULT_BASE+$12
RESULT_REJECT_STATUS    equ RESULT_BASE+$13

TFM_SRC                 equ $0800
TFM_DST                 equ $1800
TFM_ROW_BYTES           equ 8
        IFDEF   BENCH_ROWS
TFM_ROWS                equ BENCH_ROWS
        ELSE
TFM_ROWS                equ 16
        ENDC
TFM_STRIDE               equ 152
TFM_GUARD               equ $2200

Q_SRC                   equ $2000
Q_DST                   equ $3000
Q_ROW_BYTES             equ 8
Q_ROWS                  equ TFM_ROWS
Q_STRIDE                equ 152
Q_GUARD                 equ $3A00

OIM_DST                 equ $0700
OIM_COUNT               equ 8
OIM_GUARD               equ $0710

        org     $C000
        fcc     "DK"
        jmp     entry

entry
        orcc    #$50
        ; Keep the candidate in 6309 emulation mode.  RSCH-003 used this
        ; instruction path successfully; native-mode entry is a separate
        ; XRoar qualification and is not part of the timing window.
        lds     #$5FFE
        IFDEF   BENCH_CANDIDATE
        jmp     init_fixtures
        ELSE
        jsr     init_fixtures
        ENDC
        jmp     benchmark_start

        ; Keep the benchmark entry away from the legacy RSCH-003 addresses.
        ; A stale ROM therefore cannot accidentally satisfy the start marker.
        rmb     $7FB

benchmark_start
        IFDEF   BENCH_CANDIDATE
        lda     #$C3
        ELSE
        lda     #$B9
        ENDC
        sta     RESULT_VARIANT

case_tfm_hot_start
        ldx     #TFM_SRC
        ldy     #TFM_DST
        ldb     #TFM_ROWS
tfm_hot_row
        IFDEF   BENCH_CANDIDATE
        ldw     #TFM_ROW_BYTES
        tfm     x+,y+
        ELSE
        lda     ,x+
        sta     ,y+
        lda     ,x+
        sta     ,y+
        lda     ,x+
        sta     ,y+
        lda     ,x+
        sta     ,y+
        lda     ,x+
        sta     ,y+
        lda     ,x+
        sta     ,y+
        lda     ,x+
        sta     ,y+
        lda     ,x+
        sta     ,y+
        ENDC
        leax    TFM_STRIDE-TFM_ROW_BYTES,x
        leay    TFM_STRIDE-TFM_ROW_BYTES,y
        decb
        bne     tfm_hot_row

case_tfm_hot_end
        nop

case_q_hot_start
        ldx     #Q_SRC
        ldy     #Q_DST
        lda     #Q_ROWS
        sta     RESULT_Q_STATUS
q_hot_row
        IFDEF   BENCH_CANDIDATE
        ldq     ,x
        stq     ,y
        ldq     4,x
        stq     4,y
        ELSE
        lda     ,x
        sta     ,y
        lda     1,x
        sta     1,y
        lda     2,x
        sta     2,y
        lda     3,x
        sta     3,y
        lda     4,x
        sta     4,y
        lda     5,x
        sta     5,y
        lda     6,x
        sta     6,y
        lda     7,x
        sta     7,y
        ENDC
        leax    Q_STRIDE,x
        leay    Q_STRIDE,y
        dec     RESULT_Q_STATUS
        bne     q_hot_row

case_q_hot_end
        nop

case_oim_hot_start
        ldx     #OIM_DST
        IFDEF   BENCH_CANDIDATE
        oim     #$0F,0,x
        oim     #$F0,1,x
        oim     #$0F,2,x
        oim     #$F0,3,x
        oim     #$0F,4,x
        oim     #$F0,5,x
        oim     #$0F,6,x
        oim     #$F0,7,x
        ELSE
        lda     0,x
        ora     #$0F
        sta     0,x
        lda     1,x
        ora     #$F0
        sta     1,x
        lda     2,x
        ora     #$0F
        sta     2,x
        lda     3,x
        ora     #$F0
        sta     3,x
        lda     4,x
        ora     #$0F
        sta     4,x
        lda     5,x
        ora     #$F0
        sta     5,x
        lda     6,x
        ora     #$0F
        sta     6,x
        lda     7,x
        ora     #$F0
        sta     7,x
        lda     0,x
        ora     #$0F
        sta     0,x
        lda     1,x
        ora     #$F0
        sta     1,x
        lda     2,x
        ora     #$0F
        sta     2,x
        lda     3,x
        ora     #$F0
        sta     3,x
        lda     4,x
        ora     #$0F
        sta     4,x
        lda     5,x
        ora     #$F0
        sta     5,x
        lda     6,x
        ora     #$0F
        sta     6,x
        lda     7,x
        ora     #$F0
        sta     7,x
        ENDC

case_oim_hot_end
        nop

case_reject_start
        ; Mixed transparency requires opposite-nibble preservation and is not
        ; an OIM candidate.  This status is a fixture contract, not a speed
        ; result.
        clr     RESULT_REJECT_STATUS
case_reject_end
        nop

benchmark_done
        bra     benchmark_done

;------------------------------------------------------------------------------

init_fixtures
        lda     #'R'
        sta     RESULT_SIGNATURE
        lda     #'4'
        sta     RESULT_SIGNATURE+1
        lda     #'H'
        sta     RESULT_SIGNATURE+2
        lda     #'T'
        sta     RESULT_SIGNATURE+3

        IFDEF   BENCH_CANDIDATE
        lda     #$C3
        ELSE
        lda     #$B9
        ENDC
        sta     RESULT_VARIANT

        ldx     #TFM_SRC
        ldy     #TFM_DST
        lda     #TFM_ROWS
        sta     RESULT_TFM_STATUS
        lda     #$21
fill_tfm_rows
        ldb     #TFM_ROW_BYTES
fill_tfm_row
        sta     ,x+
        adda    #$13
        decb
        bne     fill_tfm_row
        leax    TFM_STRIDE-TFM_ROW_BYTES,x
        leay    TFM_STRIDE-TFM_ROW_BYTES,y
        dec     RESULT_TFM_STATUS
        bne     fill_tfm_rows
        lda     #$A5
        sta     TFM_GUARD

        ldx     #Q_SRC
        ldy     #Q_DST
        lda     #Q_ROWS
        sta     RESULT_Q_STATUS
        lda     #$31
fill_q_rows
        ldb     #Q_ROW_BYTES
fill_q_row
        sta     ,x+
        adda    #$11
        decb
        bne     fill_q_row
        leax    Q_STRIDE-Q_ROW_BYTES,x
        leay    Q_STRIDE-Q_ROW_BYTES,y
        dec     RESULT_Q_STATUS
        bne     fill_q_rows
        lda     #$5A
        sta     Q_GUARD

        ldx     #OIM_DST
        ldb     #OIM_COUNT
        lda     #$A0
fill_oim
        sta     ,x+
        eora    #$AA
        decb
        bne     fill_oim
        lda     #$5A
        sta     OIM_GUARD
        clr     RESULT_TFM_STATUS
        clr     RESULT_Q_STATUS
        clr     RESULT_OIM_STATUS
        clr     RESULT_REJECT_STATUS
        IFDEF   BENCH_CANDIDATE
        lda     #$A5
        sta     TFM_GUARD
        jmp     benchmark_start
        ELSE
        rts
        ENDC

        end
