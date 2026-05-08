;==============================================================================
; Ladybug — main.s
;==============================================================================
; Phase 0 POC: minimum cartridge that takes control from BASIC and proves it
; by painting a checkerboard semigraphic block across the top row of the text
; screen, then halting.
;
; No GIME init, no IRQ install, no all-RAM switch. Phase 1 adds those.
;
; Boot handshake (see wiki/platform/cartridge.md):
;   1. Cart at $C000-$FEFF (TY=0).
;   2. Reset → BASIC reset-init runs.
;   3. PIA2 CB1 sees CART low → FIRQ.
;   4. BASIC FIRQ handler reads first two bytes at $C000. If "DK", jumps $C002.
;==============================================================================

        pragma  nodollarlocal,6809

        ORG     $C000

        FCC     "DK"            ; ROM-pack autostart magic

;------------------------------------------------------------------------------
; entry — first instruction the BASIC FIRQ handler dispatches to
;
; Inputs:    none (cold from BASIC reset-init)
; Returns:   does not return; halts in BRA *
;------------------------------------------------------------------------------
entry   ORCC    #$50            ; mask IRQ and FIRQ
        LDS     #$7FFE          ; stack at top of low RAM (well clear of $C000)

        LDX     #$0400          ; CoCo VDG text screen base
        LDA     #$AA            ; semigraphic-4 checkerboard block
fill    STA     ,X+
        CMPX    #$0420          ; one full 32-char row
        BNE     fill

hang    BRA     hang

        END
