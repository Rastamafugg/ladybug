;==============================================================================
; modes.inc — Mode table for the tester ROM.
; Each record: 5 bytes (vmode, vres, border, voff1, voff0).
; v0 has one mode; WS-D expands the matrix.
; Both the table label and TM_* offsets are emitted to build/tester.map.
;==============================================================================

TM_VMODE   equ 0
TM_VRES    equ 1
TM_BORDER  equ 2
TM_VOFF1   equ 3
TM_VOFF0   equ 4
TM_LEN     equ 5

tester_mode_table
        ; Mode 0: 320x192x16 (Format C). BP=1, VRES=00 HRES=111 CRES=10.
        ; FB at virt $2000 → phys $072000 (MMU off, top-64K window).
        fcb     $80     ; vmode
        fcb     $1E     ; vres (final, unblanked)
        fcb     $28     ; border (bright pink)
        fcb     $E4     ; voff1
        fcb     $00     ; voff0

TESTER_MODE_COUNT equ (*-tester_mode_table)/TM_LEN
