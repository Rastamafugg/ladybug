;==============================================================================
; 6309_tfm_timing.s - RSCH-006 TFM boundary and source-aligned controls.
;
; Baseline builds use the 6809 byte-copy sequence. Candidate builds use the
; HD6309 TFM instruction. The measured windows deliberately retain the same
; marker shape and row/stride setup so the host can compare marker deltas,
; event ticks, and reported CPU cycles without changing the XRoar contract.
;==============================================================================

        pragma  nodollarlocal

RESULT_BASE             equ $0200
RESULT_SIGNATURE        equ RESULT_BASE
RESULT_VARIANT          equ RESULT_BASE+4
RESULT_ROWS             equ RESULT_BASE+5

TFM_SRC                 equ $0800
TFM_DST                 equ $1800
TFM_ROW_BYTES           equ 8
        IFDEF   BENCH_ROWS
TFM_ROWS                equ BENCH_ROWS
        ELSE
TFM_ROWS                equ 1
        ENDC
TFM_STRIDE              equ 152
TFM_GUARD               equ $2200

        org     $C000
        fcc     "DK"
        jmp     entry

entry
        orcc    #$50
        lds     #$5FFE
        lda     #'R'
        sta     RESULT_SIGNATURE
        lda     #'6'
        sta     RESULT_SIGNATURE+1
        lda     #'T'
        sta     RESULT_SIGNATURE+2
        lda     #'F'
        sta     RESULT_SIGNATURE+3
        IFDEF   BENCH_CANDIDATE
        lda     #$C3
        ELSE
        lda     #$B9
        ENDC
        sta     RESULT_VARIANT
        lda     #TFM_ROWS
        sta     RESULT_ROWS
        jsr     init_fixtures
        jmp     benchmark_start

benchmark_start

; The NOP window establishes the marker and breakpoint measurement floor.
case_boundary_start
        nop
case_boundary_end
        nop

; One fixed 8-byte transfer. This is the direct control for the original TFM
; outlier and keeps setup identical across baseline and candidate builds.
case_fixed_start
        ldx     #TFM_SRC
        ldy     #TFM_DST
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
case_fixed_end
        nop

; The source-aligned window models the eight visible bytes in each Ladybug
; row, followed by the 152-byte outer stride.
case_rows_start
        ldx     #TFM_SRC
        ldy     #TFM_DST
        ldb     #TFM_ROWS
tfm_row
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
        bne     tfm_row
case_rows_end
        nop

benchmark_done
        bra     benchmark_done

init_fixtures
        ldx     #TFM_SRC
        ldy     #TFM_DST
        lda     #$21
        ldb     #TFM_ROWS
fill_rows
        pshs    b
        ldb     #TFM_ROW_BYTES
fill_row
        sta     ,x+
        adda    #$13
        decb
        bne     fill_row
        puls    b
        leax    TFM_STRIDE-TFM_ROW_BYTES,x
        leay    TFM_STRIDE-TFM_ROW_BYTES,y
        decb
        bne     fill_rows
        lda     #$A5
        sta     TFM_GUARD
        rts

        end
