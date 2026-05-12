; Minimal cartridge-window read probe.
;
; Purpose:
;   Read $C000-$FEFF before this probe writes to that range, compare each byte
;   after the executing probe code with the expected ROM fill pattern, and log
;   mismatches in low RAM.
;
; Output:
;   $01FF = mismatch count
;   $0200 onward = records of 4 bytes each:
;       address high, address low, expected byte, actual byte

        org     $C000

        fcc     "DK"
entry   orcc    #$50
        lds     #$1FFE

        clr     mismatch_count

        ldx     #$C000
        ldu     #mismatch_log

probe_loop
        lda     ,x
        cmpx    #probe_code_end
        blo     probe_next
        cmpx    #probe_ff_start
        blo     expect_zero

expect_ff
        cmpa    #$FF
        beq     probe_next
        ldb     #$FF
        stb     expected_byte
        bra     log_mismatch

expect_zero
        tsta
        beq     probe_next
        clr     expected_byte

log_mismatch
        pshs    a
        tfr     x,d
        sta     ,u+
        stb     ,u+
        lda     expected_byte
        sta     ,u+
        puls    a
        sta     ,u+
        inc     mismatch_count

probe_next
        leax    1,x

        cmpx    #$FF00
        blo     probe_loop

probe_done
        bra     probe_done
probe_code_end

        fill    $00,$100
probe_ff_start

expected_byte  equ $01FE
mismatch_count equ $01FF
mismatch_log   equ $0200

        end
