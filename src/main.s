;==============================================================================
; Ladybug — main.s
;==============================================================================
; Phase 2.4: render a hand-converted arcade tile to the framebuffer.
;
; Builds on Phase 2.3 (hi-res 320×192×16 + MMU + palette + IRQ tick) by:
;   - Replacing the 16-stripe diagnostic with a black-cleared FB.
;   - Reassigning palette indices 1-3 to a 4-colour sub-palette
;     (0 black / 1 yellow / 2 blue / 3 white) for the tile.
;   - Embedding 32 bytes of 4bpp GIME tile data, hand-converted from
;     arcade char #432 (a dense tile that exercises all four pixvals)
;     in assets/arcade/chars.json. Pixval->palette mapping is identity.
;   - blit_tile: 8 rows x 4 bytes, stride 160.
;   - Rendering the tile at three FB positions to validate the
;     pipeline end-to-end.
;
; Visible: black screen with three identical arcade-char-432 tiles at the
; top of the screen (left / center / right). IRQ tick keeps running.
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
        ; XRoar 1.10 returns bad cartridge-window bytes at $C0D9-$C0DB during
        ; this boot path. Skip that range during copy and keep it as unused
        ; padding below. See lessons-learned.md.
        ldx     #CART_BASE
copyloop
        cmpx    #$C0D8
        beq     copy_around_xroar_bad_window
        ldd     ,x
        std     ,x
        leax    2,x
copy_next
        cmpx    #CART_END
        blo     copyloop
        bra     copy_done

copy_around_xroar_bad_window
        lda     ,x              ; $C0D8 is reliable; $C0D9-$C0DB are not.
        sta     ,x
        leax    4,x
        bra     copy_next

copy_done
        ;----------------------------------------------------------------------
        ; Boot ordering: PARs BEFORE SAM_ALLRAM so par_table reads from ROM.
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

        ; --- All-RAM (now safe; PARs already loaded from ROM) ---
        sta     SAM_ALLRAM

        ; --- Fast clock 1.78 MHz ---
        sta     SAM_FAST

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

        ; --- Clear FB to palette idx 0 (black) ---
        ; 30720 bytes = 15360 STDs.
        ldx     #FB_VIRT
        ldd     #$0000
clr_fb  std     ,x++
        cmpx    #FB_END
        blo     clr_fb

        ; --- Three copies of test tile at top, evenly spaced ---
        ; FB stride 160 B = 320 px (4 bpp). Tile is 4 B = 8 px wide.
        ;   left   col   0  px → FB_VIRT + 0    = $2000
        ;   center col 152 px → FB_VIRT + 76    = $204C
        ;   right  col 312 px → FB_VIRT + 156   = $209C
        ldx     #FB_VIRT
        leay    tile_data,pcr
        lbsr    blit_tile

        ldx     #FB_VIRT+76
        leay    tile_data,pcr
        lbsr    blit_tile

        ldx     #FB_VIRT+156
        leay    tile_data,pcr
        lbsr    blit_tile

        ; --- Un-blank: 320×192×16 (CRES=10 + HRES=111 → 4bpp on this build) ---
        lda     #$1E
        sta     GIME_VRES

        ; Phase 2.4 isolation: halt here so the visible state is just
        ; the 3 tiles on black. The IRQ install + Vbord enable below is
        ; carried over from Phase 2.3 but has not been re-verified against
        ; the new MMU/PAR layout — leaving it disabled until that's done.

        ; --- L4 probe: write sentinel to JT_IRQ, persist readback + marker,
        ;     fall through to phase24_halt for trap-snap capture.
        lda     #$55
        sta     JT_IRQ          ; the suspect store
        lda     JT_IRQ
        sta     $0FFE           ; readback of $FEF7
        lda     #$AA
        sta     $0FFF           ; liveness marker
phase24_halt
        bra     phase24_halt

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
; mainloop — IRQ keeps ticking FRAMES; CPU just spins.
;==============================================================================
        ; XRoar 1.10 returns bad cartridge-window reads at $C0D9-$C0DB. Force
        ; mainloop (and everything that follows) past that range; copy_around_
        ; xroar_bad_window leaves $C0D9-$C0DB uninitialised in RAM, so no live
        ; code or data may occupy it. See lessons-learned.md.
        org     $C0DC

mainloop
        sync
        bra     mainloop

;==============================================================================
; blit_tile — copy an 8x8 tile (32 bytes, 4bpp packed) to the framebuffer.
;   X = dest FB byte address (top-left of tile)
;   Y = source tile data
; Trashes A, B, D, X, Y. 8 rows x 4 bytes; row stride 160 (FB) - 4 (written) = 156.
;==============================================================================
blit_tile
        ; ldd ,y++ clobbers B, so use a Y-vs-sentinel loop instead of decb.
        ; See lessons-learned.md §"LDD ,Y++ clobbers B".
        leau    32,y            ; sentinel = end of tile data
        pshs    u
btrow   ldd     ,y++
        std     ,x++
        ldd     ,y++
        std     ,x++
        leax    156,x           ; advance to next FB row, same column
        cmpy    ,s
        blo     btrow
        leas    2,s
        rts

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

;-- Palette: 16 entries, GIME 6-bit codes (composite-NTSC empirical). --------
;   Indices 0-3 form the sub-palette for the Phase 2.4 test tile:
;     0 black, 1 yellow, 2 blue, 3 white. Remaining slots unused for now.
palette_table
        fcb     $00             ; 0  black
        fcb     $33             ; 1  yellow
        fcb     $0C             ; 2  blue
        fcb     $3F             ; 3  white
        fcb     $03             ; 4  green-brown (unused)
        fcb     $30             ; 5  white-dup   (unused)
        fcb     $0F             ; 6  forest grn  (unused)
        fcb     $3C             ; 7  baby blue   (unused)
        fcb     $20             ; 8  grey        (unused)
        fcb     $08             ; 9  fuchsia     (unused)
        fcb     $02             ; 10 darker grn  (unused)
        fcb     $22             ; 11 sat lt grn  (unused)
        fcb     $0A             ; 12 purple     (unused)
        fcb     $28             ; 13 pink       (unused)
        fcb     $15             ; 14 orange     (unused)
        fcb     $24             ; 15 orange-yel (unused)

;-- Test tile: arcade chars.json[432] (dense, uses all four pixvals). --------
;   Hand-converted from 8x8 2bpp pixval grid to 4bpp GIME packing
;   (2 px/byte, hi-nibble = leftmost px). Pixval N maps directly to
;   palette idx N — chosen because every idx 0/1/2/3 appears in the tile,
;   so a wrong palette entry is immediately obvious.
;
;   Source pixval rows (from chars.json[432]):
;     3,3,3,3,3,1,3,3
;     3,3,3,1,1,1,3,3
;     3,3,1,1,1,1,1,0
;     3,3,1,1,1,1,1,2
;     3,3,1,1,1,1,1,2
;     3,1,1,1,1,1,2,2
;     3,1,1,1,3,1,2,0
;     3,1,1,3,1,1,2,2
tile_data
        ; arcade chars.json[432], 8×8 2bpp pixvals packed to 4bpp (hi nibble = left px).
        ; Pixval→palette idx is identity: 0=black, 1=yellow, 2=blue, 3=white.
        fcb     $33,$33,$31,$33     ; row 0:  3 3 3 3 3 1 3 3
        fcb     $33,$31,$11,$33     ; row 1:  3 3 3 1 1 1 3 3
        fcb     $33,$11,$11,$10     ; row 2:  3 3 1 1 1 1 1 0
        fcb     $33,$11,$11,$12     ; row 3:  3 3 1 1 1 1 1 2
        fcb     $33,$11,$11,$12     ; row 4:  3 3 1 1 1 1 1 2
        fcb     $31,$11,$11,$22     ; row 5:  3 1 1 1 1 1 2 2
        fcb     $31,$11,$31,$20     ; row 6:  3 1 1 1 3 1 2 0
        fcb     $31,$13,$11,$22     ; row 7:  3 1 1 3 1 1 2 2

        end
