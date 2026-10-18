; DOC-002 source-contract mirror contract key_service profile=keybindings: Dispatch physical input, authored menu painting, capture navigation or default initialization.
; DOC-002 source-contract mirror contract key_init profile=keybindings: Restore five gameplay defaults; seed impossible keyboard-column and joystick-direction histories; clear capture and repaint state.
; DOC-002 source-contract mirror contract key_scan profile=keybindings: Sample eight physical columns with KB_ROWS as pre-overwrite history, retain held actions and publish fresh keyboard edges; emit joystick direction edges only for automatic-loop owners and silently refresh its baseline on all other presentation screens, including name entry.
; DOC-002 source-contract mirror contract key_down profile=keybindings: Test one column-times-eight-plus-row physical switch while preserving caller indexes.
; DOC-002 source-contract mirror contract key_capture profile=keybindings: Reject conflicting or ambiguous keys and consume accepted or cancelled capture through release.
; DOC-002 source-contract mirror contract key_tick profile=keybindings: Navigate five gameplay actions and BACK or begin waiting for a replacement switch.
; DOC-002 source-contract mirror contract key_paint profile=keybindings: Repaint all hydrated rows or only the previous and current selected rows for the prepared owner.
; DOC-002 source-contract mirror contract key_waiting profile=keybindings: Report whether the current row owns active capture parentheses.
; DOC-002 source-contract mirror contract key_name profile=keybindings: Resolve a physical switch to its single glyph or descriptive key name.
; DOC-002 source-contract mirror contract key_text profile=keybindings: Paint an authored length-delimited glyph run.
; DOC-002 source-contract mirror contract key_char profile=keybindings: Paint one source glyph through the resident shared mask renderer.
; DOC-002 source-contract mirror profile keybindings Inputs: Physical CoCo switch columns; in INPUT_JOYSTICK builds, raw 0..63 axes from conditional PRES_MAIN_JOY_AXIS on presentation screens, including name entry; session bindings, capture state and prepared menu BACK. B selects scan, paint, menu tick or reset.
; DOC-002 source-contract mirror profile keybindings Outputs: Five held gameplay actions, fresh fixed coin/menu edges, and a fresh automatic-loop wake token from keyboard or cardinal joystick direction; retained bindings or selected menu pixels. No joystick fire-button event is read.
; DOC-002 source-contract mirror profile keybindings Clobbers: A, B, D, X, Y, U and condition codes except source-preserved registers; every stack return is balanced.
; DOC-002 source-contract mirror profile keybindings Reads: PIA keyboard rows and, on presentation screens in joystick builds, the existing raw joystick-axis callback; retired-boot-area bindings/capture state, immutable font masks and authored key-name/menu records.
; DOC-002 source-contract mirror profile keybindings Writes: Unbanked low RAM $0287-$029A, profile-local joystick direction history in the page-$3D keybinding module, and menu-owned edge/selection/dirty bytes; prepared BACK pixels and module-local owner selection cache.
; DOC-002 source-contract mirror profile keybindings Side effects: Capture suppresses global and local consumers through accepted-key release. Joystick sampling normalizes raw axes to one cardinal dead-zone edge without writing JOY/player/name state and restores PIA2 DAC and the established audio_select_gmc PIA selectors. All non-emitting presentation screens, including name entry, refresh direction history silently; only automatic-loop owners publish changed non-neutral directions. Painting calls the resident mask renderer without changing PAR5.
; DOC-002 source-contract mirror profile keybindings Invariants: KB_ROWS at $028E-$0295 is exclusive raw-scan history: key_init seeds impossible $FF before scanning, and key_scan accumulates current-and-not-previous bits before each column overwrite. The joystick callback exists only for INPUT_JOYSTICK=1; cold first sampling seeds direction history without a false edge. During name entry, raw-axis sampling updates only the private baseline, so a held direction through the transition to ranking loading stays suppressed while a newly changed direction wakes the eligible owner; neutral release then repress is a fresh edge. Keyboard builds have no joystick callback reference. Existing page-$3D stream owns code/data at $BA00; caller gateway restores PAR5; bindings reset at startup and never persist to storage.
; @audit {"id":"session-key-state","kind":"scratch","symbol":"KB_BIND","width":20,"mapping":"unbanked-low-ram","phases":["foreground"],"owner":"session keybinding input/capture","initialization":"five editable bytes at $0287-$028B; fixed-menu held state uses reserved $028C; $028D stays reserved; key_init after boot_streams_retired and before startup input; KB_ROWS=$028E-$0295 is seeded to $FF then overwritten by every complete eight-column scan","lifetime":"Boot descriptors retire before initialization. Bindings retain for powered session; raw rows, direction edge history, and capture scratch are reused between scans","clobbers":"Only this component writes $0287-$029A after boot retirement; main.s consumes only the first four movement bits; ACTION is reserved with no normal effect; $028C tracks fixed arrows, Enter and Back across phases; $DF is updated only during local menu screens so name-entry row state remains owned by the name renderer; fixed coin events stay independent; joystick sampling does not write JOY/player state."}
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
PRES_EVENT equ $00A9
PRES_MODE equ $00A5
PRES_SCREEN equ $00A6
MODE_LOAD equ 1
MODE_INSTRUCTIONS equ 3
MODE_DEMO equ 4
MODE_ATTRACT equ 2
MODE_CREDIT equ 5
MODE_GAMEOVER equ 7
MODE_NAME equ 8
PRES_CONTEXT equ $00A7
PIA2_DA equ $FF20
PIA2_CRB equ $FF23
DIR_N equ 0
DIR_E equ 1
DIR_S equ 2
DIR_W equ 3
DIR_NONE equ $FF
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
        ldx #KB_ROWS
        lda #$FF
        ldb #8
ki_rows
        sta ,x+
        decb
        bne ki_rows
        ifne INPUT_JOYSTICK
        lda #$FF
        sta key_joy_last
        endc
        lda #$FF
        sta key_painted_select
        sta key_painted_select+1
        sta key_painted_select+2
        rts
key_defaults
        fcb 27,35,43,51,KB_FIXED_ENTER
key_scan
        ; $D0 belongs to the instruction colour clock off menu screens.
        ; ks_local publishes every menu edge, including zero; capture clears locally.
        clr PRES_EVENT
        ldx #KB_ROWS
        lda #$FE
ks_column
        sta $FF02
        pshs a
        lda $FF00
        coma
        anda #$7F
        pshs a
        lda ,x
        coma
        anda ,s
        beq ks_no_raw_edge
        lda PRES_EVENT
        ora #$80
        sta PRES_EVENT
ks_no_raw_edge
        puls a
        sta ,x+
        puls a
        lsla
        ora #1
        cmpx #KB_ROWS+8
        blo ks_column
        lda #$FF
        sta $FF02
        ifne INPUT_JOYSTICK
        lda PRES_MODE
        cmpa #MODE_INSTRUCTIONS
        beq ks_joy_emit
        cmpa #MODE_DEMO
        beq ks_joy_emit
        cmpa #MODE_ATTRACT
        beq ks_joy_silent
        cmpa #MODE_LOAD
        bne ks_joy_screen
        lda PRES_SCREEN
        cmpa #PRESENTATION_MAP_INSTRUCTIONS
        beq ks_joy_emit
        cmpa #PRESENTATION_MAP_HIGH_SCORE
        beq ks_joy_emit
        cmpa #PRESENTATION_MAP_LEVEL_START
        bne ks_joy_silent
        tst PRES_CONTEXT
        beq ks_joy_emit
        bra ks_joy_silent
ks_joy_screen
        lda PRES_MODE
        cmpa #MODE_LEVEL
        bne ks_joy_rank_mode
        lda PRES_SCREEN
        cmpa #PRESENTATION_MAP_INSTRUCTIONS
        beq ks_joy_emit
        cmpa #PRESENTATION_MAP_LEVEL_START
        bne ks_joy_silent
        tst PRES_CONTEXT
        beq ks_joy_emit
        bra ks_joy_silent
ks_joy_rank_mode
        lda PRES_MODE
        cmpa #MODE_CREDIT
        beq ks_joy_credit_screen
        cmpa #MODE_GAMEOVER
        beq ks_joy_silent
        cmpa #MODE_NAME
        lbne ks_joy_done
        ; Keep only the private raw-direction baseline current. Name input
        ; still uses PRES_MAIN_READ_JOY later and receives no wake here.
        bra ks_joy_silent
ks_joy_credit_screen
        lda PRES_SCREEN
        cmpa #PRESENTATION_MAP_HIGH_SCORE
        beq ks_joy_emit
        bra ks_joy_silent
ks_joy_emit
        lda #1
        bra ks_joy_begin
ks_joy_silent
        clra
ks_joy_begin
        pshs a
ks_joy_sample
        ; Reuse the current source comparator callback. This is a raw sample:
        ; unlike read_joystick it does not write JOY_* or PLAYER_* state. The
        ; stack flag permits wake edges only for automatic-loop owners; other
        ; presentation screens refresh the baseline without dispatching input.
        lda #$34
        sta PIA2_CRB
        sta $FF01
        sta $FF03
        jsr PRES_MAIN_JOY_AXIS
        pshs b
        lda #$3C
        sta $FF01
        jsr PRES_MAIN_JOY_AXIS
        pshs b
        lda ,s
        suba #32
        bpl ks_joy_y_abs
        nega
ks_joy_y_abs
        sta KB_WORK
        lda 1,s
        suba #32
        bpl ks_joy_x_abs
        nega
ks_joy_x_abs
        sta KB_CAND
        ; Match read_joystick's dominant-axis rule: horizontal wins X >= Y.
        ; Raw examples: X=32/Y=0 -> N; X=0/Y=32 -> W; X=48/Y=48 -> E.
        lda KB_CAND
        cmpa KB_WORK
        bhs ks_joy_horizontal
        ; The compare leaves X magnitude in A; reload Y for this branch's deadzone.
        lda KB_WORK
        cmpa #8
        bls ks_joy_center
        lda ,s
        cmpa #32
        blo ks_joy_north
        lda #DIR_S
        bra ks_joy_direction
ks_joy_north
        lda #DIR_N
        bra ks_joy_direction
ks_joy_horizontal
        lda KB_CAND
        cmpa #8
        bls ks_joy_center
        lda 1,s
        cmpa #32
        blo ks_joy_west
        lda #DIR_E
        bra ks_joy_direction
ks_joy_west
        lda #DIR_W
        bra ks_joy_direction
ks_joy_center
        lda #DIR_NONE
ks_joy_direction
        leas 2,s
        sta KB_WORK
        lda key_joy_last
        cmpa #$FF
        beq ks_joy_store
        lda KB_WORK
        cmpa key_joy_last
        beq ks_joy_store
        cmpa #DIR_NONE
        beq ks_joy_store
        tst ,s
        beq ks_joy_store
        lda PRES_EVENT
        ora #$80
        sta PRES_EVENT
ks_joy_store
        leas 1,s
        lda KB_WORK
        sta key_joy_last
        lda #$80
        sta PIA2_DA
        ; audio_select_gmc's established runtime selector convention.
        lda #$34
        sta $FF01
        lda #$3C
        sta $FF03
        sta PIA2_CRB
ks_joy_done
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
        tst KB_STATE
        beq ks_global
        puls a
        clr PRES_EVENT
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
        sta $DF                   ; local menu held state; name entry owns $DF otherwise
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
        ifne INPUT_JOYSTICK
key_joy_last
        fcb $FF
        endc
key_single
        fcb 0
key_runtime_end
