;==============================================================================
; 6309_production_hotpaths.s - RSCH-007 exact production-shape controls.
;
; Assemble one BENCH_* case and at most one BENCH_TFM/BENCH_Q candidate.
; Fixture memory is initialized by the host while execution is stopped at
; benchmark_start.  The measured window starts at case_start and ends before
; case_end.  Common return/diagnostic work is intentionally outside the window.
;==============================================================================

        pragma  nodollarlocal

RESULT_BASE             equ $0200
RESULT_SIGNATURE        equ RESULT_BASE
RESULT_CASE             equ RESULT_BASE+4
RESULT_VARIANT          equ RESULT_BASE+5
RESULT_Q                equ RESULT_BASE+6

PLAYER_FB               equ $000B
PLAYER_BG_VALID         equ $006A
PLAYER_COPY_ROWS        equ $006E
GATE_COPY_ROWS          equ $007A
RING_PHASE              equ $009C
RING_ROW                equ $009D
RING_BASE               equ $009E
PLAYER_BG_PTR           equ $00A2

FB_BACK                 equ $2008
FB_FRONT                equ $5008
PLAYER_BG_A             equ $A300
RING_DATA               equ $A690
ROW_BYTES               equ 8
ROW_SKIP                equ 152
ROW_STRIDE              equ 160
FULL_ROWS               equ 16

        org     $C000
        fcc     "DK"
        jmp     entry

entry
        orcc    #$50
        lds     #$5FFE
        lda     #'R'
        sta     RESULT_SIGNATURE
        lda     #'7'
        sta     RESULT_SIGNATURE+1
        lda     #'P'
        sta     RESULT_SIGNATURE+2
        lda     #'H'
        sta     RESULT_SIGNATURE+3
        IFDEF   BENCH_TFM
        lda     #1
        ELSE
        IFDEF   BENCH_Q
        lda     #2
        ELSE
        clra
        ENDC
        ENDC
        sta     RESULT_VARIANT
        ldd     #FB_BACK
        std     PLAYER_FB
        ldd     #PLAYER_BG_A
        std     PLAYER_BG_PTR
        clr     PLAYER_BG_VALID
        clr     PLAYER_COPY_ROWS
        clr     GATE_COPY_ROWS
        clr     RING_PHASE
        clr     RING_ROW

        IFDEF   BENCH_PLAYER_SAVE
        lda     #1
        sta     RESULT_CASE
        ENDC
        IFDEF   BENCH_PLAYER_RESTORE
        lda     #2
        sta     RESULT_CASE
        ENDC
        IFDEF   BENCH_ROAM_CAPTURE_FULL
        lda     #3
        sta     RESULT_CASE
        ldx     #FB_BACK
        ldu     #RING_DATA
        ENDC
        IFDEF   BENCH_ROAM_RESTORE_PHASE0
        lda     #4
        sta     RESULT_CASE
        ldx     #FB_BACK
        ldu     #RING_DATA
        ENDC
        IFDEF   BENCH_ROAM_RESTORE_PHASE4
        lda     #5
        sta     RESULT_CASE
        ldx     #FB_BACK
        ldu     #RING_DATA
        ENDC
        IFDEF   BENCH_ROAM_RESTORE_ODD
        lda     #6
        sta     RESULT_CASE
        ldx     #FB_BACK
        ldu     #RING_DATA
        ENDC
        IFDEF   BENCH_ROAM_RESTORE_SPLIT
        lda     #7
        sta     RESULT_CASE
        lda     #$60
        sta     RING_PHASE
        ldx     #FB_BACK
        ldu     #RING_DATA
        ENDC
        IFDEF   BENCH_RING_CAPTURE_TWO
        lda     #8
        sta     RESULT_CASE
        ldx     #FB_BACK
        ldu     #RING_DATA
        ENDC

benchmark_start
case_start

; Exact save_player contract: framebuffer source, linear owner-selected target.
        IFDEF   BENCH_PLAYER_SAVE
        ldx     PLAYER_FB
        ldu     PLAYER_BG_PTR
        exg     x,u
        lda     #FULL_ROWS
        sta     PLAYER_COPY_ROWS
player_save_row
        IFDEF   BENCH_TFM
        ldw     #ROW_BYTES
        tfm     u+,x+
        ELSE
        IFDEF   BENCH_Q
        ldq     ,u
        stq     ,x
        ldq     4,u
        stq     4,x
        leau    ROW_BYTES,u
        leax    ROW_BYTES,x
        ELSE
        pulu    d,y
        std     ,x++
        sty     ,x++
        pulu    d,y
        std     ,x++
        sty     ,x++
        ENDC
        ENDC
        leau    ROW_SKIP,u
        dec     PLAYER_COPY_ROWS
        bne     player_save_row
        lda     #1
        sta     PLAYER_BG_VALID
        ENDC

; Exact restore_player contract: linear owner-selected source, framebuffer target.
        IFDEF   BENCH_PLAYER_RESTORE
        ldx     PLAYER_FB
        ldu     PLAYER_BG_PTR
        lda     #FULL_ROWS
        sta     PLAYER_COPY_ROWS
player_restore_row
        IFDEF   BENCH_TFM
        ldw     #ROW_BYTES
        tfm     u+,x+
        ELSE
        IFDEF   BENCH_Q
        ldq     ,u
        stq     ,x
        ldq     4,u
        stq     4,x
        leau    ROW_BYTES,u
        leax    ROW_BYTES,x
        ELSE
        pulu    d,y
        std     ,x++
        sty     ,x++
        pulu    d,y
        std     ,x++
        sty     ,x++
        ENDC
        ENDC
        leax    ROW_SKIP,x
        dec     PLAYER_COPY_ROWS
        bne     player_restore_row
        clr     PLAYER_BG_VALID
        ENDC

; Exact roam_copy_fb_to_bg loop: framebuffer source, linear ring target.
        IFDEF   BENCH_ROAM_CAPTURE_FULL
        ldy     #FULL_ROWS
roam_capture_full_row
        IFDEF   BENCH_TFM
        ldw     #ROW_BYTES
        tfm     x+,u+
        ELSE
        IFDEF   BENCH_Q
        ldq     ,x
        stq     ,u
        ldq     4,x
        stq     4,u
        leax    ROW_BYTES,x
        leau    ROW_BYTES,u
        ELSE
        ldd     ,x++
        std     ,u++
        ldd     ,x++
        std     ,u++
        ldd     ,x++
        std     ,u++
        ldd     ,x++
        std     ,u++
        ENDC
        ENDC
        leax    ROW_SKIP,x
        leay    -1,y
        bne     roam_capture_full_row
        ENDC

; Exact phase-zero row loop from persistent roam_copy_bg_to_fb.
        IFDEF   BENCH_ROAM_RESTORE_PHASE0
        lda     #FULL_ROWS
        sta     GATE_COPY_ROWS
roam_restore_phase0_row
        IFDEF   BENCH_TFM
        ldw     #ROW_BYTES
        tfm     u+,x+
        ELSE
        IFDEF   BENCH_Q
        ldq     ,u
        stq     ,x
        ldq     4,u
        stq     4,x
        leau    ROW_BYTES,u
        leax    ROW_BYTES,x
        ELSE
        pulu    d,y
        std     ,x++
        sty     ,x++
        pulu    d,y
        std     ,x++
        sty     ,x++
        ENDC
        ENDC
        leax    ROW_SKIP,x
        dec     GATE_COPY_ROWS
        bne     roam_restore_phase0_row
        ENDC

; Exact phase-four byte order.  Q candidate groups the two contiguous halves.
        IFDEF   BENCH_ROAM_RESTORE_PHASE4
        lda     #FULL_ROWS
        sta     GATE_COPY_ROWS
roam_restore_phase4_row
        IFDEF   BENCH_Q
        ldq     4,u
        stq     ,x
        ldq     ,u
        stq     4,x
        leau    ROW_BYTES,u
        leax    ROW_STRIDE,x
        ELSE
        ldd     4,u
        std     ,x++
        ldd     6,u
        std     ,x++
        ldd     ,u
        std     ,x++
        ldd     2,u
        std     ,x++
        leau    ROW_BYTES,u
        leax    ROW_SKIP,x
        ENDC
        dec     GATE_COPY_ROWS
        bne     roam_restore_phase4_row
        ENDC

; Odd phase-one is the explicit non-applicable control.
        IFDEF   BENCH_ROAM_RESTORE_ODD
        lda     #FULL_ROWS
        sta     GATE_COPY_ROWS
roam_restore_odd_row
        ldd     1,u
        std     ,x++
        ldd     3,u
        std     ,x++
        ldd     5,u
        std     ,x++
        lda     7,u
        ldb     ,u
        std     ,x++
        leau    ROW_BYTES,u
        leax    ROW_SKIP,x
        dec     GATE_COPY_ROWS
        bne     roam_restore_odd_row
        ENDC

; Row-phase six forces the production two-segment phase-zero restore shape.
        IFDEF   BENCH_ROAM_RESTORE_SPLIT
        stu     RING_BASE
        lda     RING_PHASE
        anda    #$F0
        lsra
        lsra
        lsra
        lsra
        sta     RING_ROW
        ldb     #ROW_BYTES
        mul
        addd    RING_BASE
        tfr     d,u
        clra
        ldb     #FULL_ROWS
        subb    RING_ROW
        stb     GATE_COPY_ROWS
        bsr     split_restore_rows
        lda     RING_ROW
        beq     split_restore_done
        leau    -128,u
        tfr     a,b
        stb     GATE_COPY_ROWS
        bsr     split_restore_rows
split_restore_done
        ENDC

; Two phase-zero exposed rows, including helper call and required returned X.
        IFDEF   BENCH_RING_CAPTURE_TWO
        stu     RING_BASE
        clr     RING_ROW
        lda     #2
        sta     GATE_COPY_ROWS
ring_capture_outer
        pshs    x
        lda     RING_ROW
        ldb     #ROW_BYTES
        mul
        addd    RING_BASE
        tfr     d,u
        puls    x
        bsr     ring_capture_phase0
        leax    ROW_SKIP,x
        inc     RING_ROW
        lda     RING_ROW
        anda    #15
        sta     RING_ROW
        dec     GATE_COPY_ROWS
        bne     ring_capture_outer
        ENDC

case_end
        nop
        IFDEF   BENCH_TFM
        stq     RESULT_Q
        ENDC
        IFDEF   BENCH_Q
        stq     RESULT_Q
        ENDC
benchmark_done
        bra     benchmark_done

        IFDEF   BENCH_ROAM_RESTORE_SPLIT
split_restore_rows
split_restore_row
        IFDEF   BENCH_TFM
        ldw     #ROW_BYTES
        tfm     u+,x+
        ELSE
        IFDEF   BENCH_Q
        ldq     ,u
        stq     ,x
        ldq     4,u
        stq     4,x
        leau    ROW_BYTES,u
        leax    ROW_BYTES,x
        ELSE
        pulu    d,y
        std     ,x++
        sty     ,x++
        pulu    d,y
        std     ,x++
        sty     ,x++
        ENDC
        ENDC
        leax    ROW_SKIP,x
        dec     GATE_COPY_ROWS
        bne     split_restore_row
        rts
        ENDC

        IFDEF   BENCH_RING_CAPTURE_TWO
ring_capture_phase0
        ldb     RING_PHASE
        bne     ring_capture_bad_phase
        exg     x,u
        IFDEF   BENCH_TFM
        ldw     #ROW_BYTES
        tfm     u+,x+
        ELSE
        IFDEF   BENCH_Q
        ldq     ,u
        stq     ,x
        ldq     4,u
        stq     4,x
        leau    ROW_BYTES,u
        leax    ROW_BYTES,x
        ELSE
        pulu    d,y
        std     ,x++
        sty     ,x++
        pulu    d,y
        std     ,x++
        sty     ,x++
        ENDC
        ENDC
        tfr     u,x
        rts
ring_capture_bad_phase
        rts
        ENDC

        end
