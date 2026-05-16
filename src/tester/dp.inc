;==============================================================================
; dp.inc — Direct Page slot layout for the tester ROM.
; DP page = $02. All labels exported to build/tester.map so the web app
; (Option-2 ProgramStateStrategy) can read mode/pattern state by symbol.
;==============================================================================

        org     $0200
tester_mode_idx         rmb 1   ; current mode (index into tester_mode_table)
tester_pattern_idx      rmb 1   ; current pattern (index into pattern_jump_table)
tester_selection_dirty  rmb 1   ; ISR sets, mainloop clears + redraws
tester_kbd_prev         rmb 8   ; per-column DRA snapshot for edge detection
tester_frame_ctr        rmb 2   ; 60 Hz tick, debug
