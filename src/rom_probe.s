; Minimal cartridge-window read probe.
;
; Purpose:
;   Read $C000-$C0FF before this probe writes to that range, compare each byte
;   with an expected table, and log mismatches in low RAM.
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
        ldy     #expected_c000
        ldu     #mismatch_log

probe_loop
        lda     ,x
        cmpa    ,y
        beq     probe_next

        pshs    a
        tfr     x,d
        sta     ,u+
        stb     ,u+
        lda     ,y
        sta     ,u+
        puls    a
        sta     ,u+
        inc     mismatch_count

probe_next
        leax    1,x
        leay    1,y
        cmpx    #$C100
        blo     probe_loop

probe_done
        bra     probe_done

        org     $C200
expected_c000
        fill    $00,$100

mismatch_count equ $01FF
mismatch_log   equ $0200

        end
