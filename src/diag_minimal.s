;==============================================================================
; diag_minimal.s — minimum-viable 320×192×16 hi-res test, built from scratch
;==============================================================================
; Goal: prove the GIME hi-res mode works in isolation, with no MMU and no
; cart self-copy. If this displays 16 distinct horizontal stripes, then the
; Phase 2.x main.s bug is elsewhere (MMU / PAR setup, self-copy, etc).
;
; Setup per "Assembly Language Programming for the CoCo3" Ch. 4:
;   - $FF90 (Init0): bit 7=0 (CoCo3), bit 6=0 (MMU OFF), bit 3=1 (force $FExx).
;   - $FF98 (VMODE): BP=1 (graphics).
;   - $FF99 (VRES): VRES=00, HRES=111, CRES=10  →  320×192×16 (Format C).
;   - $FF9D/$FF9E (VOFF): phys $072000 (= virtual $2000 with MMU OFF; the
;     MMU-off path maps the 64 K virtual range onto the topmost 64 K physical,
;     phys $070000-$07FFFF, so virtual $2000 = phys $072000).
;   - Palette: 16 distinct 6-bit codes covering R/G/B/luma variations.
;   - FB fill: 16 horizontal stripes, each 12 rows tall, filled with byte $NN
;     so both pixels = palette idx N.
;==============================================================================

        pragma  nodollarlocal,6809

GIME_INIT0  equ  $FF90
GIME_VMODE  equ  $FF98
GIME_VRES   equ  $FF99
GIME_BORDER equ  $FF9A
GIME_VOFF1  equ  $FF9D
GIME_VOFF0  equ  $FF9E
PAL_BASE    equ  $FFB0

FB_VIRT     equ  $2000

        org     $C000
        fcc     "DK"            ; cart autostart magic; FIRQ vector → $C002

entry
        orcc    #$50            ; mask IRQ + FIRQ
        lds     #$1FFE          ; stack just below FB

        ; --- Init0: CoCo3 mode, MMU off, all ACVC IRQs off, force $FExx ---
        lda     #%00001000
        sta     GIME_INIT0

        ; --- VMODE: BP=1 (graphics), LPR=000 ---
        lda     #%10000000
        sta     GIME_VMODE

        ; --- VRES: blank screen during setup (CRES=11) ---
        lda     #$1F            ; VRES=00 HRES=111 CRES=11 (BLANKED)
        sta     GIME_VRES

        ; --- Border: bright pink ($28) so FB extent is obvious ---
        lda     #$28
        sta     GIME_BORDER

        ; --- VOFF: FB at phys $072000 (= virtual $2000 with MMU OFF) ---
        ;   $072000 >> 11 = $E4   → bits 18-11 → $FF9D
        ;   $072000 >> 3 & $FF = $00 → bits 10-3 → $FF9E
        lda     #$E4
        sta     GIME_VOFF1
        clr     GIME_VOFF0

        ; --- Load palette ---
        leax    palette_table,pcr
        ldy     #PAL_BASE
        ldb     #16
palloop lda     ,x+
        sta     ,y+
        decb
        bne     palloop

        ; --- Fill FB with 16 horizontal stripes ---
        ;   12 rows × 80 STDs/row = 960 STDs per stripe.
        ;   Stripe N filled with byte $NN (palette idx N in both pixels).
        ldx     #FB_VIRT
        ldu     #$0000
        clra
stripe_outer
        pshs    a
        ldy     #960
        tfr     u,d
inner_str
        std     ,x++
        leay    -1,y
        bne     inner_str
        leau    $1111,u
        puls    a
        inca
        cmpa    #16
        blo     stripe_outer

        ; --- Unblank: CRES=10 (16-color, Format C) ---
        lda     #$1E
        sta     GIME_VRES

halt    bra     halt

;==============================================================================
; Palette — 16 distinct 6-bit codes.
; Indices 0-7 cover the bright primaries + black/white.
; Indices 8-15 cover the dim primaries + greys.
;==============================================================================
palette_table
        fcb     $00     ; 0  black     (RGBrgb = 000 000)
        fcb     $20     ; 1  bright R  (R'      = 100 000)
        fcb     $10     ; 2  bright G  (G'      = 010 000)
        fcb     $08     ; 3  bright B  (B'      = 001 000)
        fcb     $30     ; 4  R'+G'    = yellow
        fcb     $18     ; 5  G'+B'    = cyan
        fcb     $28     ; 6  R'+B'    = magenta
        fcb     $38     ; 7  R'+G'+B' = white-ish (bright only)
        fcb     $04     ; 8  dim R
        fcb     $02     ; 9  dim G
        fcb     $01     ; 10 dim B
        fcb     $06     ; 11 dim yellow
        fcb     $03     ; 12 dim cyan
        fcb     $05     ; 13 dim magenta
        fcb     $07     ; 14 dim white = dark grey
        fcb     $3F     ; 15 full white (all bits set)

        end
