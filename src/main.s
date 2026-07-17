;==============================================================================
; Ladybug — main.s
;==============================================================================
; Phase 2.6: render build-generated arcade text to the framebuffer.
;
; Builds on Phase 2.3 (hi-res 320×192×16 + MMU + palette + IRQ tick) by:
;   - Replacing the 16-stripe diagnostic with a black-cleared FB.
;   - Generating the palette and seven 4bpp GIME glyphs for LADYBUG from
;     assets/arcade/chars.json before assembly.
;   - Rotating the arcade glyphs 90 degrees counter-clockwise so they are
;     upright on the unrotated CoCo 3 framebuffer.
;   - blit_tile: 8 rows x 4 bytes, stride 160.
;   - put_char: row/column character coordinates over blit_tile.
;
; Visible: yellow LADYBUG title centered near the top of a black screen.
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
SAM_ROMRAM equ  $FFDE

JT_IRQ     equ  $FEF7

;------------------------------------------------------------------------------
; Memory map (post-Phase-2.3 with MMU on)
;------------------------------------------------------------------------------
FB_VIRT    equ  $2000           ; virtual base of framebuffer (PAR1)
FB_END     equ  $9800           ; one past last FB byte (192 rows × 160 B)
FB_PHYS    equ  $30             ; physical page 0 of FB

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
        sta     SAM_ROMRAM       ; cart map is selected before clearing TY

        ; --- Execute directly from cartridge ROM ---
        ; Keep TY=0. XRoar discards writes to the selected cartridge window,
        ; so the former same-address self-copy never populated phys $3E-$3F.
        ; PAR6=$3E keeps $C000-$DFFF cartridge-backed after MMU enable while
        ; the framebuffer and writable state use ordinary RAM pages below $3C.

        ; --- Force executive PAR set ($FFA0-$FFA7) to be active ---
        clr     $FF91

        ; --- Set up MMU PARs (executive set) ---
        ; PAR0 ($0000) = phys $38   low RAM (DP, stack)
        ; PAR1 ($2000) = phys $30   FB page 0
        ; PAR2 ($4000) = phys $31   FB page 1
        ; PAR3 ($6000) = phys $32   FB page 2
        ; PAR4 ($8000) = phys $33   FB page 3
        ; PAR5 ($A000) = phys $34   game state (Phase 4+)
        ; PAR6 ($C000) = phys $3E   cartridge code (current 8 K window)
        ; PAR7 ($E000) = phys $3F   cartridge/ROM window + IO + jump table
        leax    par_table,pcr
        ldy     #PAR_EXEC
        ldb     #8
parloop lda     ,x+
        sta     ,y+
        decb
        bne     parloop

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

        ; --- Phase 2 exit text ---
        lbsr    draw_title

        ; --- Un-blank: 320×192×16 (CRES=10 + HRES=111 → 4bpp on this build) ---
        lda     #$1E
        sta     GIME_VRES

        ; Phase 2.6 isolation: halt here so the visible state is just
        ; LADYBUG on black. The IRQ install + Vbord enable below is
        ; carried over from Phase 2.3 but has not been re-verified against
        ; the new MMU/PAR layout — leaving it disabled until that's done.

        ; --- L4 probe: write sentinel to JT_IRQ, persist readback + marker,
        ;     fall through to phase26_halt for trap-snap capture.
        lda     #$55
        sta     JT_IRQ          ; the suspect store
        lda     JT_IRQ
        sta     $0FFE           ; readback of $FEF7
        lda     #$AA
        sta     $0FFF           ; liveness marker
phase26_halt
        bra     phase26_halt

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
        ; XRoar returns bad cartridge-window reads at $C0D9-$C0DB. Emit real
        ; bytes through that range so raw-ROM file offsets stay identical to
        ; assembler addresses; `org` alone changes the map without padding a
        ; raw output file.
        fill    $FF,$C0DC-*

mainloop
        sync
        bra     mainloop

;==============================================================================
; draw_title — render the seven contiguous LADYBUG glyphs.
;
; Inputs:
;   None
;
; Returns:
;   A, B, X, Y, U, D, CC — undefined
;
; Side effects:
;   Writes seven 8x8 glyphs at character row 1, columns 16..22.
;==============================================================================
draw_title
        leay    glyph_l,pcr     ; generated glyph order is L,A,D,Y,B,U,G
        lda     #1
        ldb     #16
        ldu     #7
dt_next
        pshs    d               ; put_char consumes row and column
        lbsr    put_char
        puls    d
        incb
        leau    -1,u            ; LEAU does not update condition codes
        cmpu    #0
        bne     dt_next
        rts

;==============================================================================
; put_char — render one glyph at an 8x8 character coordinate.
;
; Inputs:
;   A — character row, 0..23
;   B — character column, 0..39
;   Y — source glyph data, 32 packed 4bpp bytes
;   U — caller-owned value
;
; Returns:
;   U — preserved
;   A, B, D, X, Y, CC — undefined
;
; Side effects:
;   Writes one 8x8 glyph to the framebuffer.
;==============================================================================
put_char
        pshs    u
        ldx     #FB_VIRT
        tsta
        beq     pc_column
pc_row
        leax    1280,x          ; 8 pixel rows x 160 bytes
        deca
        bne     pc_row
pc_column
        lslb                    ; 8 pixels x 4bpp = 4 bytes
        lslb
        abx
        lbsr    blit_tile
        puls    u,pc

;==============================================================================
; blit_tile — copy an 8x8 tile to a framebuffer byte address.
;
; Inputs:
;   X — destination framebuffer byte address
;   Y — source glyph data, 32 packed 4bpp bytes
;
; Returns:
;   A, B, D, X, Y, U, CC — undefined
;
; Side effects:
;   Writes 8 rows x 4 bytes; advances 156 bytes after each written row.
;==============================================================================
blit_tile
        ; ldd ,y++ clobbers B, so use a Y-vs-sentinel loop instead of decb.
        ; See wiki/internal/implementation/lessons-learned.html
        ; §"LDD ,Y++ clobbers B".
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
; Data tables (read directly from cartridge ROM)
;==============================================================================

;-- PAR values for executive set (PAR0..PAR7) ---------------------------------
par_table
        fcb     $38,$30,$31,$32,$33,$34,$3E,$3F

;-- Build-generated palette and selected character data. ---------------------
;   scripts/build.sh creates build/ladybug_gfx.inc from the authoritative
;   assets/arcade/chars.json before invoking lwasm.
        include "ladybug_gfx.inc"

        end
