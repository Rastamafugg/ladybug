; DOC-002 source-contract mirror contract key_service profile=keybindings: Dispatch physical input, authored menu painting, capture navigation or default initialization.
; DOC-002 source-contract mirror contract key_init profile=keybindings: Restore five gameplay defaults; fixed coin/menu keys remain outside the binding table.
; DOC-002 source-contract mirror contract key_scan profile=keybindings: Sample eight physical columns and produce held actions and fresh consumer edges.
; DOC-002 source-contract mirror contract key_down profile=keybindings: Test one column-times-eight-plus-row physical switch while preserving caller indexes.
; DOC-002 source-contract mirror contract key_capture profile=keybindings: Reject conflicting or ambiguous keys and consume accepted or cancelled capture through release.
; DOC-002 source-contract mirror contract key_tick profile=keybindings: Navigate five gameplay actions and BACK or begin waiting for a replacement switch.
; DOC-002 source-contract mirror contract key_paint profile=keybindings: Repaint all hydrated rows or only the previous and current selected rows for the prepared owner.
; DOC-002 source-contract mirror contract key_waiting profile=keybindings: Report whether the current row owns active capture parentheses.
; DOC-002 source-contract mirror contract key_name profile=keybindings: Resolve a physical switch to its single glyph or descriptive key name.
; DOC-002 source-contract mirror contract key_text profile=keybindings: Paint an authored length-delimited glyph run.
; DOC-002 source-contract mirror contract key_char profile=keybindings: Paint one source glyph through the resident shared mask renderer.
; DOC-002 source-contract mirror profile keybindings Inputs: Physical CoCo switch columns, session bindings, capture state and prepared menu BACK; B selects scan, paint, menu tick or reset.
; DOC-002 source-contract mirror profile keybindings Outputs: Five held gameplay actions, fresh fixed coin/menu edges, retained bindings or selected menu pixels; menu tick returns B=$FF to retain or B=6 to return.
; DOC-002 source-contract mirror profile keybindings Clobbers: A, B, D, X, Y, U and condition codes except source-preserved registers; every stack return is balanced.
; DOC-002 source-contract mirror profile keybindings Reads: PIA keyboard rows, retired-boot-area bindings/capture state, immutable font masks and authored key-name/menu records.
; DOC-002 source-contract mirror profile keybindings Writes: Unbanked low RAM $0287-$029A and menu-owned edge/selection/dirty bytes; prepared BACK pixels and module-local owner selection cache.
; DOC-002 source-contract mirror profile keybindings Side effects: Capture suppresses global and local consumers through accepted-key release; painting calls the resident mask renderer without changing PAR5.
; DOC-002 source-contract mirror profile keybindings Invariants: The existing page-$3D stream owns code/data at $BA00; caller gateway restores its PAR5; bindings reset at startup and never persist to storage.
; @audit {"id":"session-key-state","kind":"scratch","symbol":"KB_BIND","width":20,"mapping":"unbanked-low-ram","phases":["foreground"],"owner":"session keybinding input/capture","initialization":"five editable bytes at $0287-$028B; fixed-menu held state uses reserved $028C; $028D stays reserved; key_init after boot_streams_retired and before startup input; key_scan initializes column samples before consumer use","lifetime":"Boot descriptors retire before initialization. Bindings retain for powered session; scan/capture scratch retires before subsequent scan","clobbers":"Only this component writes $0287-$029A after boot retirement; main.s consumes only the first four movement bits; ACTION is reserved with no normal effect; $028C tracks fixed arrows, Enter and Back across phases; $DF is updated only during menu screens so name-entry row state remains owned by the name renderer; fixed coin events stay independent."}
; RSCH-014 C3 prototype extension: fixed menu edges track physical state in all phases.
; Source edit is isolated research, not the approved repair implementation.
; Loaded after the unchanged audio prefix in the existing page-$3D stream.
        pragma 6809
        setdp $00
        ifndef INPUT_JOYSTICK
INPUT_JOYSTICK equ 0
        endc
        include "ladybug_runtime_symbols.inc"
        include "ladybug_presentation_symbols.inc"
KB_BIND equ $0287
KB_ROWS equ $028E
KB_ACTION_COUNT equ 5
KB_MENU_LAST equ 5
KB_MENU_PREV equ $028C
KB_FIXED_ENTER equ 6
KB_FIXED_COIN_5 equ 44
KB_FIXED_COIN_6 equ 52
KB_DOWN equ $0296
KB_PREV equ $0297
KB_STATE equ $0298
KB_CAND equ $0299
KB_WORK equ $029A
        org $BA00
key_service
        tstb
        lbeq key_scan
        cmpb #1
        lbeq key_paint
        cmpb #2
        lbeq key_tick
key_init
        ldx #KB_BIND
        leay key_defaults,pcr
        ldb #KB_ACTION_COUNT
ki_copy
        lda ,y+
        sta ,x+
        decb
        bne ki_copy
        clr KB_DOWN
        clr KB_PREV
        clr KB_MENU_PREV
        clr KB_STATE
        lda #$FF
        sta key_painted_select
        sta key_painted_select+1
        sta key_painted_select+2
        rts
key_defaults
        fcb 27,35,43,51,KB_FIXED_ENTER
key_scan
        clr $D0                   ; discard any menu edge not consumed this scan
        ldx #KB_ROWS
        lda #$FE
ks_column
        sta $FF02
        pshs a
        lda $FF00
        coma
        anda #$7F
        sta ,x+
        puls a
        lsla
        ora #1
        cmpx #KB_ROWS+8
        blo ks_column
        lda #$FF
        sta $FF02
        ifne INPUT_JOYSTICK
        lda #$34
        sta $FF01
        endc
        clr KB_WORK
        lda KB_ROWS+3
        bita #8
        beq ks_menu_down
        inc KB_WORK
ks_menu_down
        lda KB_ROWS+4
        bita #8
        beq ks_menu_left
        lda KB_WORK
        ora #2
        sta KB_WORK
ks_menu_left
        lda KB_ROWS+5
        bita #8
        beq ks_menu_right
        lda KB_WORK
        ora #4
        sta KB_WORK
ks_menu_right
        lda KB_ROWS+6
        bita #8
        beq ks_menu_enter
        lda KB_WORK
        ora #8
        sta KB_WORK
ks_menu_enter
        lda #KB_FIXED_ENTER
        lbsr key_down
        beq ks_menu_back
        lda KB_WORK
        ora #16
        sta KB_WORK
ks_menu_back
        lda #22
        lbsr key_down
        beq ks_menu_sampled
        lda KB_WORK
        ora #32
        sta KB_WORK
ks_menu_sampled
        clr KB_DOWN
        ldx #KB_BIND
        leay key_bits,pcr
        clrb
ks_action
        lda b,x
        lbsr key_down
        beq ks_next
        lda KB_DOWN
        ora b,y
        sta KB_DOWN
ks_next
        incb
        cmpb #KB_ACTION_COUNT
        blo ks_action
        ; Physical 5 and 6 are fixed coin controls, not hidden bindings.
        lda #KB_FIXED_COIN_5
        lbsr key_down
        beq ks_coin_6
        lda KB_DOWN
        ora #32
        sta KB_DOWN
ks_coin_6
        lda #KB_FIXED_COIN_6
        lbsr key_down
        beq ks_edges
        lda KB_DOWN
        ora #64
        sta KB_DOWN
ks_edges
        lda KB_PREV
        coma
        anda KB_DOWN
        pshs a
        lda KB_DOWN
        sta KB_PREV
        clr $A9
        tst KB_STATE
        beq ks_global
        puls a
        clr $D0
        lda KB_WORK
        sta KB_MENU_PREV
        lbra key_capture
ks_global
        puls a
        tfr a,b                  ; preserve fresh key edges while publishing events
        bitb #32
        beq ks_credit_6
        lda $A9
        ora #2
        sta $A9
ks_credit_6
        bitb #64
        beq ks_menu
        lda $A9
        ora #4
        sta $A9
ks_menu
        lda $A6
        cmpa #3
        beq ks_local
        cmpa #6
        blo ks_done
ks_local
        lda KB_MENU_PREV
        coma
        anda KB_WORK
        sta $D0
        lda KB_WORK
        sta KB_MENU_PREV
        sta $DF                   ; local menu held state; screen 5 owns $DF otherwise
        rts
ks_done
        lda KB_WORK
        sta KB_MENU_PREV          ; track inherited holds without clobbering name-entry row
        rts
key_bits
        fcb 1,2,4,8,16,32,64,128
; Physical switch identity is column*8 + row. Z means released.
key_down
        pshs b,x
        tfr a,b
        anda #7
        leax key_bits,pcr
        lda a,x
        pshs a
        lsrb
        lsrb
        lsrb
        ldx #KB_ROWS
        lda b,x
        anda ,s+
        puls b,x,pc
key_capture
        ldb KB_STATE
        cmpb #3
        beq kc_release
        lda #22
        lbsr key_down
        lbne kc_cancel
kc_release
        ldx #KB_ROWS
        clra
kc_held
        ora ,x+
        cmpx #KB_ROWS+8
        blo kc_held
        ldb KB_STATE
        cmpb #2
        beq kc_candidate
        tsta
        bne kc_done
        clra
        cmpb #1
        bne kc_state
        lda #2
kc_state
        sta KB_STATE
        tsta
        bne kc_done
        clr $DF
kc_done
        rts
kc_candidate
        lda #$FF
        sta KB_CAND
        clrb
kc_find
        tfr b,a
        lbsr key_down
        beq kc_find_next
        lda KB_CAND
        cmpa #$FF
        bne kc_reject
        stb KB_CAND
kc_find_next
        incb
        cmpb #64
        blo kc_find
        lda KB_CAND
        cmpa #$FF
        beq kc_done
        cmpa #KB_FIXED_COIN_5
        beq kc_reject
        cmpa #KB_FIXED_COIN_6
        beq kc_reject
kc_unique
        ldx #KB_BIND
        clrb
kc_duplicate
        cmpb $E0
        beq kc_unique_next
        lda b,x
        cmpa KB_CAND
        beq kc_reject
kc_unique_next
        incb
        cmpb #KB_ACTION_COUNT
        blo kc_duplicate
        ldb $E0
        lda KB_CAND
        sta b,x
        bra kc_cancel
kc_reject
        lda #1
        sta KB_STATE
        rts
kc_cancel
        lda #3
        sta KB_STATE
        sta $E1
        rts
key_tick
        ldb #$FF
        tst KB_STATE
        bne kt_done
        lda $D0
        bita #32
        bne kt_back
        bita #16
        beq kt_arrow
        lda $E0
        cmpa #KB_MENU_LAST
        beq kt_back
        lda #1
        sta KB_STATE
        bra kt_redraw
kt_arrow
        pshs a
        lda $DF
        anda #3
        cmpa #3
        puls a
        beq kt_done
        bita #1
        beq kt_down
        tst $E0
        beq kt_done
        dec $E0
        bra kt_redraw
kt_down
        bita #2
        beq kt_done
        lda $E0
        cmpa #KB_MENU_LAST
        bhs kt_done
        inc $E0
kt_redraw
        lda #3
        sta $E1
kt_done
        rts
kt_back
        ldb #6
        rts
key_paint
        ldb $90
        leax key_painted_select,pcr
        lda b,x
        ldb $A5
        cmpb #5
        beq kp_cached
        lda #$FF
kp_cached
        sta KB_WORK
        clr $D1
        leay key_label_records,pcr
kp_label
        ldx ,y++
        ldb ,y+
        lda #7
        pshs a
        lda $D1
        cmpa $E0
        bne kp_unselected
        lda #10
        sta ,s
kp_unselected
        puls a
        sta $29
        lda KB_WORK
        cmpa #$FF
        beq kp_draw
        lda $D1
        cmpa $E0
        beq kp_draw
        cmpa KB_WORK
        beq kp_draw
        leay b,y
        bra kp_next
kp_draw
        lbsr key_text
        lda $D1
        cmpa #KB_MENU_LAST
        beq kp_next
        pshs y
        lsla
        leay key_value_destinations,pcr
        ldx a,y
        lda #36
        ldb #14
kp_clear
        lbsr key_char
        decb
        bne kp_clear
        leax -4,x
        ldb $D1
        ldy #KB_BIND
        lda b,y
        lbsr key_name
        tfr b,a
        lsla
        lsla
        nega
        leax a,x
        lbsr key_waiting
        bne kp_name
        leax -4,x
        lda #43
        lbsr key_char
kp_name
        lbsr key_text
        lbsr key_waiting
        bne kp_value_done
        lda #44
        lbsr key_char
kp_value_done
        puls y
kp_next
        inc $D1
        lda $D1
        cmpa #KB_MENU_LAST+1
        lblo kp_label
        ldb $90
        leax key_painted_select,pcr
        lda $E0
        sta b,x
        rts
key_waiting
        lda $D1
        cmpa $E0
        bne kw_done
        lda KB_STATE
        beq kw_no
        cmpa #3
        bne kw_yes
kw_no
        lda #1
        rts
kw_yes
        clra
kw_done
        rts
key_name
        leay key_name_codes,pcr
        lda a,y
        cmpa #36
        bhs kn_named
        sta key_single
        leay key_single,pcr
        ldb #1
        rts
kn_named
        suba #36
        lsla
        leay key_names,pcr
        ldy a,y
        ldb ,y+
        rts
key_text
        lda ,y+
        lbsr key_char
        decb
        bne key_text
        rts
key_char
        pshs a,b,x,y,u
        leay stage_source_glyphs,pcr
        lda a,y
        jsr PRES_MAIN_SHARED_MASK
        puls a,b,x,y,u
        leax 4,x
        rts
        include "ladybug_stage_glyphs.inc"
        include "ladybug_keybinding_records.inc"
key_painted_select
        fcb $FF,$FF,$FF
key_single
        fcb 0
key_runtime_end
