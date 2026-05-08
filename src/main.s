;==============================================================================
; Ladybug — main.s
;==============================================================================
; Phase 2.3: bring up hi-res 320×192×16 GIME mode.
;
; Builds on Phase 2.2 (cart self-copy → all-RAM → IRQ tick from RAM) by
; adding:
;   - MMU enabled with Phase-2 PAR layout (PAR0=$38, PAR1-4=$30-$33 for
;     framebuffer, PAR5=$3D, PAR6-7=$3E-$3F for code).
;   - GIME hi-res 320×192×16 (BP=1, HRES=111, CRES=10), framebuffer at
;     physical $30 ($FF9D=$C0, $FF9E=$00).
;   - 16-entry palette: idx 0 = black, idx 1 = white, others arbitrary.
;   - Clear FB to $1111 (palette idx 1 every pixel) using CRES=11 blanking
;     during the clear so we never show garbage on screen.
;   - IRQ tick continues. Mainloop renders FRAMES to FB[0..1] so 4 pixels
;     at top-left flicker through palette indices, proving IRQ + MMU + FB
;     all wired up.
;
; Visible: solid white screen with 4 flickering pixels at top-left.
;==============================================================================

        pragma  nodollarlocal,6809

;------------------------------------------------------------------------------
; DP allocation (page $02)
;------------------------------------------------------------------------------
        setdp   $02

FRAMES  equ     $0202           ; u16 frame counter

;------------------------------------------------------------------------------
; Hardware
;------------------------------------------------------------------------------
PIA1_DA    equ  $FF00
PIA1_CRA   equ  $FF01
PIA1_DB    equ  $FF02
PIA1_CRB   equ  $FF03
PIA2_DA    equ  $FF20
PIA2_CRA   equ  $FF21
PIA2_DB    equ  $FF22
PIA2_CRB   equ  $FF23

GIME_INIT0 equ  $FF90
GIME_IRQEN equ  $FF92
GIME_VMODE equ  $FF98
GIME_VRES  equ  $FF99
GIME_BORDER equ $FF9A
GIME_VOFF1 equ  $FF9D           ; addr bits Y18..Y11
GIME_VOFF0 equ  $FF9E           ; addr bits Y10..Y3
PAR_EXEC   equ  $FFA0           ; PAR0 of executive set ($FFA0..$FFA7)
PAL_BASE   equ  $FFB0

SAM_FAST   equ  $FFD9
SAM_ALLRAM equ  $FFDF

JT_IRQ     equ  $FEF7

;------------------------------------------------------------------------------
; Memory map (post-Phase-2.3 with MMU on)
;------------------------------------------------------------------------------
FB_VIRT    equ  $2000           ; virtual base of framebuffer (PAR1)
FB_END     equ  $9800           ; one past last FB byte (192 rows × 160 B)
FB_PHYS    equ  $30             ; physical page 0 of FB

CART_BASE  equ  $C000
CART_END   equ  $FF00

;==============================================================================
;  Cart ROM
;==============================================================================
        org     $C000

        fcc     "DK"            ; ROM-pack autostart magic; FIRQ -> $C002

;==============================================================================
; entry
;==============================================================================
entry   orcc    #$50            ; mask IRQ + FIRQ
        lds     #$1FFE          ; stack at top of low RAM page

        lda     #$02            ; DP = $02
        tfr     a,dp

        ; --- Quiet legacy PIA interrupts ---
        clra
        sta     PIA1_CRA
        sta     PIA1_CRB
        sta     PIA2_CRA
        sta     PIA2_CRB
        lda     PIA1_DA
        lda     PIA1_DB
        lda     PIA2_DA
        lda     PIA2_DB

        ; --- Init0 — legacy mode, ACVC IRQ on, force $FExx, MMU still off ---
        lda     #%10101000
        sta     GIME_INIT0

        ; --- Cart-to-shadow-RAM self-copy ---
        ldx     #CART_BASE
copyloop
        ldd     ,x
        std     ,x
        leax    2,x
        cmpx    #CART_END
        blo     copyloop

        ; --- All-RAM ---
        sta     SAM_ALLRAM

        ; --- Fast clock 1.78 MHz ---
        sta     SAM_FAST

        ;----------------------------------------------------------------------
        ; Phase 2.3 additions begin here.
        ;----------------------------------------------------------------------

        ; --- Force executive PAR set ($FFA0-$FFA7) to be active ---
        clr     $FF91

        ; --- Set up MMU PARs (executive set) ---
        ; PAR0 ($0000) = phys $38   low RAM (DP, stack)
        ; PAR1 ($2000) = phys $30   FB page 0
        ; PAR2 ($4000) = phys $31   FB page 1
        ; PAR3 ($6000) = phys $32   FB page 2
        ; PAR4 ($8000) = phys $33   FB page 3
        ; PAR5 ($A000) = phys $3D   game state (Phase 4+)
        ; PAR6 ($C000) = phys $3E   code low half
        ; PAR7 ($E000) = phys $3F   code high half + IO + jump table
        leax    par_table,pcr
        ldy     #PAR_EXEC
        ldb     #8
parloop lda     ,x+
        sta     ,y+
        decb
        bne     parloop

        ; --- Set up display (still blanked via CRES=11) ---
        lda     #%10000000      ; BP=1 (graphics)
        sta     GIME_VMODE

        lda     #$1F            ; VRES=00 HRES=111 CRES=11 (BLANKED)
        sta     GIME_VRES

        lda     #$28            ; bright border (empirically "pink") so a black
        sta     GIME_BORDER     ;   stripe 0 is visually distinct from the border

        ; FB at phys $30 → physical address $060000.
        ;   Y18=1, Y17=1, Y16..Y3 = 0
        ;   V1 ($FF9D) = Y18..Y11 = %11000000 = $C0
        ;   V0 ($FF9E) = Y10..Y3  = $00
        lda     #$C0
        sta     GIME_VOFF1
        clr     GIME_VOFF0

        ; --- Init0 — turn on MMU + switch to hi-res. Display still blanked. ---
        ; %01101000 = COCO=0 MMU=1 ACVCIRQ=1 ACVCFIRQ=0 force-$FExx=1 SCS=0 ROMmap=00
        lda     #%01101000
        sta     GIME_INIT0

        ; --- Load palette (16 entries) ---
        leax    palette_table,pcr
        ldy     #PAL_BASE
        ldb     #16
palloop lda     ,x+
        sta     ,y+
        decb
        bne     palloop

        ; --- Diagnostic: 16-stripe palette test ---
        ; 192 rows / 16 stripes = 12 rows per stripe.
        ; Each stripe spans full 320 px width (160 bytes/row, 80 STDs/row).
        ; Per stripe: 12 × 80 = 960 STDs.
        ;
        ; Stripe N is filled with byte $NN, so both pixels in every byte
        ; show palette index N. Top stripe = idx 0, bottom = idx 15.
        ldx     #FB_VIRT        ; FB write pointer
        ldu     #$0000          ; current pattern (idx N in both nibbles, both bytes)
        clra                    ; outer stripe counter (0-15)
stripe_outer
        pshs    a
        ldy     #960
        tfr     u,d
inner_str
        std     ,x++
        leay    -1,y
        bne     inner_str
        leau    $1111,u         ; next palette index
        puls    a
        inca
        cmpa    #16
        blo     stripe_outer

        ; --- Un-blank: CRES=10 (16-color) ---
        lda     #$1E
        sta     GIME_VRES

        ; --- IRQ handler at $FEF7 jump-table slot ---
        lda     #$7E            ; JMP extended
        sta     JT_IRQ
        ldd     #irq_handler
        std     JT_IRQ+1

        clr     FRAMES
        clr     FRAMES+1

        ; --- Enable Vbord ---
        lda     #%00001000
        sta     GIME_IRQEN
        lda     GIME_IRQEN

        andcc   #%11101111      ; unmask IRQ

;==============================================================================
; mainloop — paint a 32-pixel-wide × 12-row block at row 96 with FRAMES.
; This is the IRQ-tick indicator: 16 bytes per row × 12 rows = 192 bytes,
; updated every iteration to FRAMES low byte = visible flicker if both the
; mainloop runs and IRQ ticks.
;==============================================================================
TICKER     equ  FB_VIRT+96*160          ; row 96
TICKER_END equ  TICKER+12*160

mainloop
        ldx     #TICKER
        lda     FRAMES+1                ; cycles every 256 frames (~4.3 s)
fill_tick
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+
        sta     ,x+                     ; 16 bytes = 32 pixels per row
        cmpx    #TICKER_END
        blo     fill_tick
        bra     mainloop

;==============================================================================
; irq_handler — Vbord (60 Hz)
;==============================================================================
irq_handler
        lda     GIME_IRQEN
        inc     FRAMES+1
        bne     irq_done
        inc     FRAMES
irq_done
        rti

;==============================================================================
; Data tables (in cart ROM, copied to RAM by the boot self-copy)
;==============================================================================

;-- PAR values for executive set (PAR0..PAR7) ---------------------------------
par_table
        fcb     $38,$30,$31,$32,$33,$3D,$3E,$3F

;-- Palette: 16 entries, RGB 6-bit codes (RGBrgb). ----------------------------
;   Index 0 = black, 1 = white. Others picked for visual variety so the
;   FRAMES-driven flicker hits distinguishable colours.
palette_table
        fcb     $00             ; 0  black
        fcb     $3F             ; 1  white
        fcb     $30             ; 2  bright red
        fcb     $0C             ; 3  bright green
        fcb     $03             ; 4  bright blue
        fcb     $33             ; 5  bright yellow
        fcb     $0F             ; 6  bright cyan
        fcb     $3C             ; 7  bright magenta
        fcb     $20             ; 8  dim red
        fcb     $08             ; 9  dim green
        fcb     $02             ; 10 dim blue
        fcb     $22             ; 11 dim yellow
        fcb     $0A             ; 12 dim cyan
        fcb     $28             ; 13 dim magenta
        fcb     $15             ; 14 mid-grey
        fcb     $24             ; 15 brown-ish

        end
