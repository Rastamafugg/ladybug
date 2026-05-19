;==============================================================================
; modes.inc — Mode table for the tester ROM.
;
; Each record is 8 bytes: the five GIME register values that redraw_with_blank
; writes during a mode switch, plus three derived-geometry fields that pattern
; handlers consume so each pattern can size its draw loop + choose its pixel
; packing from the active mode alone.
;
; All exported symbols (tester_mode_table, TM_*, TESTER_MODE_COUNT) land in
; build/tester.map so the web app's Option-2 ProgramStateStrategy and the
; user-region symbol-mode resolver can address them by name.
;
; WS-D v0: adds mode 1 (320x192x4). Future modes (mono, text, 640-wide) plug
; into the same record format; no schema changes anticipated until HE-256 modes
; arrive, at which point TM_BPR may need to widen to 2 bytes.
;==============================================================================

TM_VMODE   equ 0      ; $FF98 — BP/MOCH/LPR bits
TM_VRES    equ 1      ; $FF99 — VRES/HRES/CRES bits, final post-unblank value
TM_BORDER  equ 2      ; $FF9A — 6-bit border color
TM_VOFF1   equ 3      ; $FF9D — FB physical addr Y18..Y11
TM_VOFF0   equ 4      ; $FF9E — FB physical addr Y10..Y3
TM_BPR     equ 5      ; bytes per row (u8; HE-256 modes will need widening)
TM_LINES   equ 6      ; lines per frame
TM_BPP     equ 7      ; bits per pixel: 1, 2, or 4
TM_LEN     equ 8

tester_mode_table
        ; --- Mode 0: 320x192x16 (Format C) ----------------------------------
        ; BP=1, VRES=00 HRES=111 CRES=10 → $FF99 = $1E
        ; FB at virt $2000 → phys $072000 (MMU off, top-64K window).
        fcb     $80     ; vmode
        fcb     $1E     ; vres (final, unblanked)
        fcb     $28     ; border (bright pink)
        fcb     $E4     ; voff1
        fcb     $00     ; voff0
        fcb     160     ; bpr  (320 px / 2 px-per-byte)
        fcb     192     ; lines
        fcb     4       ; bpp

        ; --- Mode 1: 320x192x4 ----------------------------------------------
        ; BP=1, VRES=00 HRES=111 CRES=01 → $FF99 = $1D
        ; Same FB phys base; FB total halved to 15,360 bytes.
        fcb     $80     ; vmode
        fcb     $1D     ; vres
        fcb     $28     ; border
        fcb     $E4     ; voff1
        fcb     $00     ; voff0
        fcb     80      ; bpr  (320 px / 4 px-per-byte)
        fcb     192     ; lines
        fcb     2       ; bpp

TESTER_MODE_COUNT equ (*-tester_mode_table)/TM_LEN
