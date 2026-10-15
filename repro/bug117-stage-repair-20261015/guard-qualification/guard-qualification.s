; Offline 6809 assembler qualification fixture for the approved BUG117 guard.
; Compile with -DGUARD_VARIANT=0 (approved), 1 (absent), 2 (manual-only),
; or 3 (inverted branch). This is not a runtime emulator or project build.
        org     $C000
INITIAL_ENTRY_STATE equ $00A0
JOY_DIR     equ $0005
PLAYER_DIR  equ $0006
PLAYER_FACE equ $0007
PLAYER_WANT equ $000F
PLAYER_MANUAL equ $0018

rj_request
        tst     INITIAL_ENTRY_STATE
        bne     rj_done
        ifeq    GUARD_VARIANT
        ldb     PLAYER_MANUAL
        orb     PLAYER_DIR
        beq     rj_done
        else
        ifeq    GUARD_VARIANT-1
        ; Variant 1: guard absent (known defect control).
        else
        ifeq    GUARD_VARIANT-2
        ; Variant 2: wrong manual-only guard; rejects manual=0, DIR_NONE name input.
        ldb     PLAYER_MANUAL
        beq     rj_done
        else
        ; Variant 3: wrong branch polarity; admits auto-entry, rejects manual north.
        ldb     PLAYER_MANUAL
        orb     PLAYER_DIR
        bne     rj_done
        endc
        endc
        endc
        sta     JOY_DIR
        sta     PLAYER_WANT
        sta     PLAYER_FACE
        lda     #1
        sta     PLAYER_MANUAL
rj_done
        rts
