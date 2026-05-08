;==============================================================================
; Ladybug — main.s
;==============================================================================
; Phase 1: take control, set DP, go all-RAM + fast clock, install Vbord IRQ at
; 60 Hz, run a frame counter visible on the legacy text screen.
;
; What's still deferred:
;   - GIME hi-res video config        → Phase 2
;   - palette setup                   → Phase 2
;   - tile/sprite renderer            → Phase 3-4
;   - input read                      → Phase 4
;
; Boot handshake — see wiki/platform/cartridge.md.
; Boot init sequence — same page, "What our boot must do".
;==============================================================================

        pragma  nodollarlocal,6809

;------------------------------------------------------------------------------
; Direct-page allocation (page $02)
;------------------------------------------------------------------------------
        setdp   $02

FRAMES  equ     $0202           ; u16 frame counter, IRQ-incremented (BE)

;------------------------------------------------------------------------------
; Hardware register addresses
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

SAM_FAST   equ  $FFD9           ; write-anything = R1 set = 1.78 MHz
SAM_ALLRAM equ  $FFDF           ; write-anything = TY set = all-RAM

JT_IRQ     equ  $FEF7           ; primary jump-table IRQ slot (3 bytes)

SCREEN     equ  $0400           ; legacy VDG text screen base

;------------------------------------------------------------------------------
; Cartridge ROM
;------------------------------------------------------------------------------
        org     $C000

        fcc     "DK"            ; ROM-pack autostart magic; FIRQ handler enters at $C002

;==============================================================================
; entry — first instruction the BASIC FIRQ handler dispatches to
;
; Inputs:    none (cold from BASIC reset-init)
; Returns:   does not return; falls into mainloop
;==============================================================================
entry   orcc    #$50            ; mask IRQ and FIRQ
        lds     #$7FFE          ; stack at top of low RAM, well below $C000

        ; --- DP = $02 ---
        lda     #$02
        tfr     a,dp

        ; --- Quiet legacy PIA interrupts (so only Vbord can fire) ---
        ; Disable IRQ from CA1/CB1 by clearing bit 0 of each control reg,
        ; then read each data port to clear any pending edge flag.
        clra
        sta     PIA1_CRA
        sta     PIA1_CRB
        sta     PIA2_CRA
        sta     PIA2_CRB
        lda     PIA1_DA
        lda     PIA1_DB
        lda     PIA2_DA
        lda     PIA2_DB

        ; --- GIME Init0: legacy VDG path on, force $FExx to phys $3F ---
        ; %10101000 = b7 COCO=1, b6 MMU=0, b5 ACVCIRQ=1, b4 ACVCFIRQ=0,
        ;             b3 force-$FExx=1, b2 SCS=0, b1-b0 ROMmap=00.
        lda     #%10101000
        sta     GIME_INIT0

        ; --- TY = 1: all-RAM mode ---
        sta     SAM_ALLRAM      ; (data byte ignored)

        ; --- R1 = 1: 1.78 MHz ---
        sta     SAM_FAST

        ; --- Install IRQ handler at primary jump-table slot $FEF7 ---
        ; 3-byte slot: opcode $7E (JMP extended) + 16-bit handler address.
        lda     #$7E
        sta     JT_IRQ
        ldd     #irq_handler
        std     JT_IRQ+1

        ; --- Clear initial frame counter ---
        clr     FRAMES
        clr     FRAMES+1

        ; --- Enable Vbord, then ack any pending IRQ ---
        lda     #%00001000      ; b3 Vbord
        sta     GIME_IRQEN
        lda     GIME_IRQEN      ; read = ack

        ; --- Unmask IRQ (keep FIRQ masked — we don't use FIRQ in Phase 1) ---
        andcc   #%11101111

;==============================================================================
; mainloop — display the IRQ-driven frame counter as two screen bytes
;
; $0400 = high byte (advances every 256 frames, ~4.27 s)
; $0401 = low byte  (cycles fast, visible flicker)
;
; Race window is acceptable for Phase 1: occasional torn read shows as a
; one-byte glitch in either column, doesn't change the "is it ticking" signal.
;==============================================================================
mainloop
        lda     FRAMES          ; high
        sta     SCREEN
        lda     FRAMES+1        ; low
        sta     SCREEN+1
        bra     mainloop

;==============================================================================
; irq_handler — Vbord (60 Hz)
;
; Inputs:  none. Entered via IRQ vector → $FEF7 JMP here.
; Returns: rti
; Side effects: increments FRAMES (16-bit big-endian); reads $FF92 to ack.
;==============================================================================
irq_handler
        lda     GIME_IRQEN      ; ack: read $FF92 to clear pending bits
        inc     FRAMES+1
        bne     irq_done
        inc     FRAMES
irq_done
        rti

        end
