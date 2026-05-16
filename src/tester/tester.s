;==============================================================================
; tester.s — Emulator-monitor tester ROM, top-level.
;
; Milestone 1 (this file's current state): boot path, palette + mode setup
; driven by tester_mode_table, draws the bars pattern once, spins. No IRQ,
; no keyboard yet — those land in milestone 2.
;
; See wiki/implementation/emulator-monitor-tester.md for the architect spec.
; Source-of-truth for boot recipe: src/diag_minimal.s (the working 16-stripe
; minimal cart from 2026-05-16).
;
; Operating envelope:
;   - No MMU ($FF90 bit 6 = 0). Virtual = physical $07xxxx.
;   - Cart executes from cart ROM at $C000-$FDFF — no self-copy (works around
;     XRoar's cart-shadow gotcha; see lessons-learned.md).
;   - RW state at virtual $0000-$1FFE, FB at $2000, stack just below FB.
;   - IRQ jump table at $FE00-$FEFF (RAM-backed via Init0 bit 3 = 1).
;==============================================================================

        pragma  nodollarlocal,6809

; --- GIME register equates ---------------------------------------------------
GIME_INIT0   equ $FF90
GIME_VMODE   equ $FF98
GIME_VRES    equ $FF99
GIME_BORDER  equ $FF9A
GIME_VOFF1   equ $FF9D
GIME_VOFF0   equ $FF9E
PAL_BASE     equ $FFB0

FB_VIRT      equ $2000
BLANK_VRES   equ $1F           ; VRES with CRES=11 → forced blank during mode change

; --- DP slot declarations ($02xx) --------------------------------------------
        include "dp.inc"

; --- ROM entry ---------------------------------------------------------------
        org     $C000
        fcc     "DK"            ; cart autostart magic; FIRQ entry at $C002

entry
        orcc    #$50            ; mask IRQ + FIRQ
        lds     #$1FFE          ; stack just below FB

        ; DP = $02 so dp.inc slots resolve short.
        lda     #$02
        tfr     a,dp
        setdp   $02

        ; Init0: CoCo3, MMU off, all ACVC IRQs off, force $FExx jumps.
        lda     #%00001000
        sta     GIME_INIT0

        ; Zero DP state.
        clr     tester_mode_idx
        clr     tester_pattern_idx
        clr     tester_selection_dirty
        ldx     #tester_kbd_prev
        ldb     #10             ; 8 prev + 2 frame_ctr
clr_dp  clr     ,x+
        decb
        bne     clr_dp

        ; Load palette.
        leax    palette_table,pcr
        ldy     #PAL_BASE
        ldb     #16
pal     lda     ,x+
        sta     ,y+
        decb
        bne     pal

        ; Apply mode 0 + pattern 0 (bars).
        jsr     redraw_with_blank

halt    bra     halt

; --- Renderer + dispatch ------------------------------------------------------
        include "render.s"
        include "pat_bars.s"

; --- Mode table ---------------------------------------------------------------
        include "modes.inc"

;==============================================================================
; Palette — 16 distinct 6-bit RGB codes (RGBrgb format).
; Copied from diag_minimal.s; covers bright + dim primaries + greys.
;==============================================================================
palette_table
        fcb     $00     ; 0  black
        fcb     $20     ; 1  bright R
        fcb     $10     ; 2  bright G
        fcb     $08     ; 3  bright B
        fcb     $30     ; 4  bright yellow
        fcb     $18     ; 5  bright cyan
        fcb     $28     ; 6  bright magenta
        fcb     $38     ; 7  bright white-ish
        fcb     $04     ; 8  dim R
        fcb     $02     ; 9  dim G
        fcb     $01     ; 10 dim B
        fcb     $06     ; 11 dim yellow
        fcb     $03     ; 12 dim cyan
        fcb     $05     ; 13 dim magenta
        fcb     $07     ; 14 dark grey
        fcb     $3F     ; 15 full white

        end
