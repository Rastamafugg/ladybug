;==============================================================================
; input.s — Keyboard scan + edge-detect dispatch.
;
; Called from the Vbord ISR each frame. Scans all 8 PIA1 columns into a
; local cur[] buffer, compares each key_table entry's (col, row_bit) against
; tester_kbd_prev[col] -> cur[col] for a high-to-low transition (new press),
; and dispatches the matching handler. Updates tester_kbd_prev[] at the end
; so the next scan sees this frame as the baseline.
;
; Assumes PIA1 was left by the BASIC reset-init in keyboard-ready state:
; DRB ($FF02) output (column drive), DRA ($FF00) input (rows), CRA/CRB
; configured for direct data-register access. diag_minimal made the same
; assumption successfully under cart-autorun.
;==============================================================================

PIA1_DRA  equ $FF00
PIA1_DRB  equ $FF02

; key_table record layout: { col_idx, row_mask, handler_addr }
KCOL  equ 0
KROW  equ 1
KHND  equ 2
K_LEN equ 4

;------------------------------------------------------------------------------
; kbd_scan_and_dispatch — called from Vbord ISR.
;
;  Inputs:  tester_kbd_prev[0..7]
;  Returns: (none)
;  Side effects: PIA1_DRB written 8x; tester_kbd_prev updated; handlers
;                may set tester_selection_dirty + tester_mode_idx +
;                tester_pattern_idx. Uses 8 bytes of stack.
;------------------------------------------------------------------------------
kbd_scan_and_dispatch
        leas    -8,s            ; cur[0..7] on stack
        tfr     s,u             ; U = &cur[0]

        ; --- scan all 8 columns into cur[] ---
        clrb
        leax    col_drive_table,pcr
ksd_scan
        lda     b,x             ; A = ~(1<<col)
        sta     PIA1_DRB
        lda     PIA1_DRA        ; rows for this column
        sta     b,u
        incb
        cmpb    #8
        blo     ksd_scan

        ; --- dispatch: for each key_table entry, look for a new-press edge ---
        leax    key_table,pcr
        ldb     #N_KEYS
ksd_disp
        tstb
        beq     ksd_update_prev
        pshs    b               ; save remaining entry count

        ldb     KCOL,x          ; col index
        lda     b,u             ; cur[col]
        coma                    ; A = ~cur[col]
        sta     ksc_scratch     ; stash
        ldb     KCOL,x          ; reload col
        leay    tester_kbd_prev,pcr
        lda     b,y             ; A = prev[col]
        anda    ksc_scratch     ; A = edge mask (high→low bits)
        anda    KROW,x          ; isolate this entry's row bit
        beq     ksd_no_press
        jsr     [KHND,x]
ksd_no_press
        puls    b               ; restore entry count
        leax    K_LEN,x
        decb
        bra     ksd_disp

        ; --- copy cur[] back to tester_kbd_prev[] ---
ksd_update_prev
        tfr     u,x             ; X = &cur[0]
        leay    tester_kbd_prev,pcr
        ldb     #8
ksd_copy
        lda     ,x+
        sta     ,y+
        decb
        bne     ksd_copy

        leas    8,s             ; release cur buffer
        rts

;------------------------------------------------------------------------------
; Column-drive lookup: ~(1<<col) for col 0..7.
;------------------------------------------------------------------------------
col_drive_table
        fcb     $FE             ; col 0
        fcb     $FD             ; col 1
        fcb     $FB             ; col 2
        fcb     $F7             ; col 3
        fcb     $EF             ; col 4
        fcb     $DF             ; col 5
        fcb     $BF             ; col 6
        fcb     $7F             ; col 7

;==============================================================================
; Key handlers — set tester_*_idx, raise dirty flag, return.
;==============================================================================

key_mode0
        clr     tester_mode_idx
        inc     tester_selection_dirty
        rts

key_pat_bars
        clr     tester_pattern_idx
        inc     tester_selection_dirty
        rts

key_pat_check
        lda     #1
        sta     tester_pattern_idx
        inc     tester_selection_dirty
        rts

;==============================================================================
; key_table — (col, row_bit, handler) records.
; v0 bindings per WS-A spec:
;   '1' (col 1, row bit PA4=$10) → select mode 0
;   'B' (col 2, row bit PA0=$01) → select pattern 0 (bars)
;   'C' (col 3, row bit PA0=$01) → select pattern 1 (checkerboard)
;==============================================================================
key_table
        fcb     1               ; '1' — col 1
        fcb     $10             ;       row bit PA4
        fdb     key_mode0
        fcb     2               ; 'B' — col 2
        fcb     $01             ;       row bit PA0
        fdb     key_pat_bars
        fcb     3               ; 'C' — col 3
        fcb     $01             ;       row bit PA0
        fdb     key_pat_check
key_table_end

N_KEYS equ (key_table_end-key_table)/K_LEN
