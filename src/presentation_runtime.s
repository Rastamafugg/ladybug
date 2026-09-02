; FEAT-002 low-RAM presentation flow, copied to $1900 during GMC boot.
; DOC-002 source-contract mirror begins. Canonical definitions:
; wiki/internal/implementation/routine-catalog.html
; DOC-002 source-contract mirror profile copy Inputs: Source and destination identities, bounded count or stream metadata, and any required mapped page
; DOC-002 source-contract mirror profile copy Outputs: Copied, decoded, merged, cached, or addressed data plus caller-visible pointer progress
; DOC-002 source-contract mirror profile copy Clobbers: A, B, D, X, Y, U, and condition codes unless a narrower source-local header is present
; DOC-002 source-contract mirror profile copy Reads: The declared source stream, table, framebuffer rows, or metadata record
; DOC-002 source-contract mirror profile copy Writes: Only the declared bounded destination record, cache, row range, or scratch fields
; DOC-002 source-contract mirror profile copy Side effects: May temporarily map PAR5 while moving or decoding data
; DOC-002 source-contract mirror profile copy Invariants: Counts and destination bounds are honored; temporary mappings are restored before returning
; DOC-002 source-contract mirror profile input Inputs: PIA input state, prior sampled state, and axis or key selection
; DOC-002 source-contract mirror profile input Outputs: Normalized input state, edge bits, or axis sample
; DOC-002 source-contract mirror profile input Clobbers: A, B, D, X, Y, U, and condition codes unless a narrower source-local header is present
; DOC-002 source-contract mirror profile input Reads: PIA registers and prior input samples
; DOC-002 source-contract mirror profile input Writes: Owned input state and temporary PIA scan selection
; DOC-002 source-contract mirror profile input Side effects: Temporarily drives keyboard or joystick scan hardware
; DOC-002 source-contract mirror profile input Invariants: PIA control and drive state are restored to the runtime convention before return
; DOC-002 source-contract mirror profile presentation Inputs: Presentation state, interval timer, input edges, current map, and the selected auxiliary profile
; DOC-002 source-contract mirror profile presentation Outputs: Updated presentation state and the dispatcher retain/release status when applicable
; DOC-002 source-contract mirror profile presentation Clobbers: A, B, D, X, Y, U, and condition codes unless a narrower source-local header is present
; DOC-002 source-contract mirror profile presentation Reads: Presentation direct-page state, cold payloads, authored map streams, and input state
; DOC-002 source-contract mirror profile presentation Writes: Presentation state, mapped BACK pixels, and presentation-owned persistent metadata
; DOC-002 source-contract mirror profile presentation Side effects: May retain the foreground interval or produce a complete presentation surface
; DOC-002 source-contract mirror profile presentation Invariants: Gameplay mutation begins only after the dispatcher releases the interval; FRONT publication remains IRQ-owned
; DOC-002 source-contract mirror profile render Inputs: Current render intent, selected actor or tile state, and a valid BACK or staging destination
; DOC-002 source-contract mirror profile render Outputs: Updated destination pixels and any owner-local history required by later restoration
; DOC-002 source-contract mirror profile render Clobbers: A, B, D, X, Y, U, and condition codes unless a narrower source-local header is present
; DOC-002 source-contract mirror profile render Reads: Authoritative gameplay state, immutable art streams, and current owner-local background metadata
; DOC-002 source-contract mirror profile render Writes: BACK or staging pixels, render scratch, and owner-local save-under or damage metadata
; DOC-002 source-contract mirror profile render Side effects: Changes a non-visible composition surface or its metadata
; DOC-002 source-contract mirror profile render Invariants: The routine never selects the visible FRONT surface; temporary PAR5 mappings expire or restore before return
; DOC-002 source-contract mirror contract add_credit profile=presentation: Add credit.
; DOC-002 source-contract mirror contract cold_ptr profile=copy: Resolve a pointer into the currently mapped presentation cold payload.
; DOC-002 source-contract mirror contract cold_read_byte profile=copy: Read one byte from the presentation cold payload while preserving mapping ownership.
; DOC-002 source-contract mirror contract colour_surface profile=render: Apply a generated sparse nibble-colour stream to a selected 16-by-16 presentation surface.
; DOC-002 source-contract mirror contract colour_tile profile=render: Replace every nonzero packed pixel pair in one selected 8-by-8 instruction tile.
; DOC-002 source-contract mirror contract draw_actor_overlay profile=render: Draw the selected presentation actor stream into the current presentation destination.
; DOC-002 source-contract mirror contract draw_cell profile=render: Draw cell.
; DOC-002 source-contract mirror contract draw_coin_slots profile=render: Draw coin slots.
; DOC-002 source-contract mirror contract draw_tile_id profile=render: Draw tile id.
; DOC-002 source-contract mirror contract gameplay_reentry profile=presentation: Restore gameplay mappings and state after presentation releases the interval.
; DOC-002 source-contract mirror contract init_gameplay profile=presentation: Initialize gameplay.
; DOC-002 source-contract mirror contract install_aux_runtime profile=presentation: Install aux runtime.
; DOC-002 source-contract mirror contract map_back profile=copy: Map back.
; DOC-002 source-contract mirror contract presentation_flow_tick profile=presentation: Dispatch the current presentation interval and return retain or release status.
; DOC-002 source-contract mirror contract scan_keys profile=input: Scan keys.
; DOC-002 source-contract mirror contract start_screen profile=presentation: Initialize and draw the requested presentation screen.
; DOC-002 source-contract mirror contract timer profile=presentation: Advance and return the current presentation interval timer.
; DOC-002 source-contract mirror ends.
        pragma  nodollarlocal,6809
        setdp   $00
        include "ladybug_presentation.inc"
        include "ladybug_presentation_symbols.inc"
        include "ladybug_audio_symbols.inc"

PAR1    equ $FFA1
PAR2    equ $FFA2
PAR3    equ $FFA3
PAR4    equ $FFA4
PAR5    equ $FFA5
PIA_DA  equ $FF00
PIA_CRA equ $FF01
PIA_DB  equ $FF02
PIA_CRB equ $FF03
PRESENTATION_MODULE_DRAW equ $0821
PRESENTATION_HOLD_BEGIN equ $06C5
PRESENTATION_HOLD_TICK equ $06C7
PRESENTATION_ATTRACT_OVERLAY equ $06C9
INSTRUCTION_RUNTIME_TICK equ $0300
DEMO_RUNTIME_TICK equ $0300
AUDIO_INIT_EXEC equ $0303
BLIT_TILE equ PRES_MAIN_BLIT_TILE
SPARSE_ENEMY_PAYLOAD_PAGE equ $35
SPARSE_PLAYER_PAYLOAD_PAGE equ $39
SPARSE_ENEMY_INDEX_ADDR equ $A000
SPARSE_PLAYER_INDEX_ADDR equ $A000
PRESENTATION_GAMEPLAY_TILES equ $E3D0
ATTRACT_PLAYER_DST equ $661C
ATTRACT_ENEMY_DST equ $2CA4
PLAYER_FB equ $000B
PLAYER_BG_PTR equ $00A2
PLAYER_BG_VALID equ $006A
PLAYER_BG equ $A300
BACK_ID equ $0090
PENDING equ $0091
ACTIVE  equ $0098
FB_INIT_STATE equ $009A
FB_META_A equ $A900
FB_META_END equ $AB00
ENTITY_TABLE equ $A380
ENTITY_SKULL equ 1
DEATH   equ $004D
DEATH_T equ $003A
STAGE_PENDING equ $0026
JOY_DIR equ $0005
PLAYER_DIR equ $0006
PLAYER_FACE equ $0007
PLAYER_WANT equ $000F
PLAYER_MANUAL equ $0018
PLAYER_STEP equ $0008
PLAYER_CELL_X equ $0009
PLAYER_CELL_Y equ $000A
SCORE   equ $001D
RF_STAGE equ $40
DIR_N   equ 0
DIR_E   equ 1
DIR_S   equ 2
DIR_W   equ 3
DIR_NONE equ $FF

MODE_NORMAL equ 0
MODE_LOAD equ 1
MODE_ATTRACT equ 2
MODE_INSTRUCTIONS equ 3
MODE_DEMO equ 4
MODE_CREDIT equ 5
MODE_LEVEL equ 6
MODE_GAMEOVER equ 7
MODE_NAME equ 8
PRES_CONTEXT_NEXT_STAGE equ 2

        ifne    COMPLETE_PROFILE
ATTRACT_OVERLAY_ENABLED equ 1
        else
        ifeq    BUG011_DEVELOPMENT_PROFILE
ATTRACT_OVERLAY_ENABLED equ 1
        else
ATTRACT_OVERLAY_ENABLED equ 0
        endc
        endc

        org $1900

presentation_flow_tick
        lda     PRES_MAGIC
        cmpa    #$A5
        beq     pft_helper_ready
        lbsr    install_aux_runtime
pft_helper_ready
        ifeq    HIGHSCORE_TEST_PROFILE
        lbsr    scan_keys
        endc
        lda     PRES_MAGIC
        cmpa    #$A5
        beq     pft_ready
        lda     #$A5
        sta     PRES_MAGIC
        clr     PRES_MODE
        clr     PRES_CREDITS
        clr     PRES_CONTEXT
        clr     PRES_DEMO_CAUSE
        clr     PRES_DEMO_ROUTE
        clr     PRES_ACTOR_FRAME
        ifne    HIGHSCORE_TEST_PROFILE
        lda     #PRESENTATION_MAP_ENTER_HIGH_SCORE
        else
        lda     #PRESENTATION_MAP_ATTRACT
        endc
        lbsr    start_screen
        lda     #1
        rts
pft_ready
        ifne    HIGHSCORE_TEST_PROFILE
        lbra    pft_dispatch
        endc
        lda     PRES_EVENT
        anda    #$06
        beq     pft_mode
        lbsr    add_credit
        lda     #PRESENTATION_MAP_HIGH_SCORE
        clr     PENDING
        lbsr    start_screen
        lda     #1
        rts
pft_mode
        lda     PRES_EVENT
        bita    #1
        beq     pft_dispatch
        tst     PRES_CREDITS
        beq     pft_dispatch
        lda     PRES_MODE
        beq     pft_dispatch
        cmpa    #MODE_LEVEL
        beq     pft_dispatch
        dec     PRES_CREDITS
        lda     #1
        sta     PRES_CONTEXT
        lda     #PRESENTATION_MAP_LEVEL_START
        lbsr    start_screen
        lda     #1
        rts
pft_dispatch
        lda     PRES_MODE
        beq     normal_tick
        cmpa    #MODE_LOAD
        lbeq    load_tick
        cmpa    #MODE_ATTRACT
        lbeq    attract_tick
        ifne    BUG011_DEVELOPMENT_PROFILE
        cmpa    #MODE_INSTRUCTIONS
        lbeq    instructions_tick
        endc
        ifne    COMPLETE_PROFILE
        cmpa    #MODE_DEMO
        lbeq    demo_tick
        else
        ifeq    BUG011_DEVELOPMENT_PROFILE
        cmpa    #MODE_DEMO
        lbeq    demo_tick
        endc
        endc
        cmpa    #MODE_CREDIT
        lbeq    credit_tick
        cmpa    #MODE_LEVEL
        lbeq    level_tick
        ifne    HIGHSCORE_TEST_PROFILE
        cmpa    #MODE_GAMEOVER
        lbeq    gameover_tick
        cmpa    #MODE_NAME
        lbeq    name_tick
        lbra    attract_tick
        else
        ifne    BUG011_DEVELOPMENT_PROFILE
        ifne    COMPLETE_PROFILE
        jmp     DEMO_RUNTIME_TICK
        else
        lbra    attract_tick
        endc
        else
        cmpa    #MODE_GAMEOVER
        lbeq    gameover_tick
        lbra    name_tick
        endc
        endc

install_aux_runtime
        ifne    COMPLETE_PROFILE
        bra     install_instruction_runtime
        else
        ifne    BUG011_DEVELOPMENT_PROFILE
        ldx     #PRESENTATION_INSTRUCTION_RUNTIME_ADDRESS
        ldu     #PRESENTATION_INSTRUCTION_RUNTIME_BYTES
        else
        ldx     #PRESENTATION_DEMO_RUNTIME_ADDRESS
        ldu     #PRESENTATION_DEMO_RUNTIME_BYTES
        endc
        lda     #$23
        bra     install_aux_runtime_copy
        endc

        ifne    COMPLETE_PROFILE
install_instruction_runtime
        ldx     #PRESENTATION_INSTRUCTION_RUNTIME_ADDRESS
        ldu     #PRESENTATION_INSTRUCTION_RUNTIME_BYTES
        lda     #$23
        bra     install_aux_runtime_copy

install_demo_runtime
        ldx     #PRESENTATION_DEMO_RUNTIME_ADDRESS
        ldu     #PRESENTATION_DEMO_RUNTIME_BYTES
        lda     #$23
        bra     install_aux_runtime_copy

install_highscore_runtime
        ldx     #PRESENTATION_HIGHSCORE_RUNTIME_ADDRESS
        ldu     #PRESENTATION_HIGHSCORE_RUNTIME_BYTES
        lda     #$23
        endc
install_aux_runtime_copy
        sta     PAR5
        ldy     #$0300
install_aux_runtime_byte
        lda     ,x+
        sta     ,y+
        leau    -1,u
        cmpu    #0
        bne     install_aux_runtime_byte
        lda     #$34
        sta     PAR5
        rts

normal_tick
        lda     DEATH
        cmpa    #4
        bne     normal_stage
        ifne    HIGHSCORE_TEST_PROFILE
        lda     #PRESENTATION_MAP_GAME_OVER
        else
        ifne    BUG011_DEVELOPMENT_PROFILE
        ifne    COMPLETE_PROFILE
        ; Complete installs phase owners before loading the screen selector.
        else
        lda     #PRESENTATION_MAP_ATTRACT
        endc
        else
        lda     #PRESENTATION_MAP_GAME_OVER
        endc
        endc
        ifne    COMPLETE_PROFILE
        jsr     AUDIO_INIT_EXEC
        bsr     install_highscore_runtime
        lda     #PRESENTATION_MAP_GAME_OVER
        endc
        bsr     start_screen
        lda     #1
        rts
normal_stage
        tst     STAGE_PENDING
        beq     normal_start
        jsr     PRES_MAIN_NEXT_STAGE
        ifne    COMPLETE_PROFILE
        lda     #PRES_CONTEXT_NEXT_STAGE
        else
        lda     #1
        endc
        sta     PRES_CONTEXT
        lda     #PRESENTATION_MAP_LEVEL_START
        bsr     start_screen
        lda     #1
        rts
normal_start
        lda     PRES_EVENT
        bita    #1
        beq     normal_game
        tst     PRES_CREDITS
        beq     normal_game
        dec     PRES_CREDITS
        lda     #1
        sta     PRES_CONTEXT
        lda     #PRESENTATION_MAP_LEVEL_START
        bsr     start_screen
        lda     #1
        rts
normal_game
        clra
        rts

start_screen
        sta     PRES_SCREEN
        ifeq    HIGHSCORE_TEST_PROFILE
        ifne    COMPLETE_PROFILE
        cmpa    #PRESENTATION_MAP_ATTRACT
        bne     start_screen_context_ready
        clr     PRES_CONTEXT
start_screen_context_ready
        endc
        ifne    COMPLETE_PROFILE
        jsr     PRES_MAIN_INSTALL_PHASE_TILES
        cmpa    #PRESENTATION_MAP_INSTRUCTIONS
        beq     start_screen_instruction_install
        tsta
        bne     start_screen_no_instruction_install
start_screen_instruction_install
        lbsr    install_instruction_runtime
        lda     PRES_SCREEN
start_screen_no_instruction_install
        endc
        endc
        tfr     a,b
        aslb
        ifne    HIGHSCORE_TEST_PROFILE+COMPLETE_PROFILE
        ldx     #PRES_MAIN_MAP_STREAM_OFFSETS
        else
        leax    map_stream_offsets,pcr
        endc
        ldd     b,x
        std     PRES_IN
        clr     PRES_RUN
        lda     #MODE_LOAD
        sta     PRES_MODE
        clra
        clrb
        std     PRES_CELL
        std     PRES_X
start_screen_map
        ldd     #$2000
        std     PRES_DST
        lbsr    map_back
        lda     PRES_SCREEN
        cmpa    #PRESENTATION_MAP_INSTRUCTIONS
        bls     start_screen_hold
        cmpa    #PRESENTATION_MAP_ENTER_HIGH_SCORE
        bne     start_screen_done
start_screen_hold
        jsr     PRESENTATION_HOLD_BEGIN
start_screen_done
        rts

load_tick
        lda     PRES_HOLD_STATE
        bpl     load_tick_normal
        jsr     PRESENTATION_HOLD_TICK
        rts
load_tick_normal
        lda     #32
        sta     PRES_ROWS
load_cells
        ldd     PRES_CELL
        cmpd    #PRESENTATION_MAP_BYTES
        bhs     load_done
        tst     PRES_RUN
        bne     load_value_ready
        lbsr    cold_read_byte
        sta     PRES_RUN
        lbsr    cold_read_byte
        sta     PRES_VALUE
load_value_ready
        ldb     PRES_VALUE
        lbsr    draw_cell
        dec     PRES_RUN
        inc     PRES_CELL+1
        bne     load_advance
        inc     PRES_CELL
load_advance
        inc     PRES_X
        lda     PRES_X
        cmpa    #40
        blo     load_next
        clr     PRES_X
        inc     PRES_Y
        ldd     PRES_DST
        addd    #1120
        std     PRES_DST
load_next
        dec     PRES_ROWS
        bne     load_cells
        lda     #1
        rts
load_done
        ldb     PRES_SCREEN
        cmpb    #PRESENTATION_MAP_INSTRUCTIONS
        bne     load_done_no_cucumber
        ldd     #PRESENTATION_INSTRUCTION_CUCUMBER_STREAM
        lbsr    cold_ptr
        tfr     x,u
        ldx     #PRESENTATION_INSTRUCTION_CUCUMBER_DST
        jsr     PRESENTATION_MODULE_DRAW
load_done_no_cucumber
        ifeq    BUG011_DEVELOPMENT_PROFILE
        lbsr    draw_coin_slots
        endc
        ifne    HIGHSCORE_TEST_PROFILE
        ldb     PRES_SCREEN
        cmpb    #PRESENTATION_MAP_HIGH_SCORE
        beq     load_done_dynamic_high
        cmpb    #PRESENTATION_MAP_ENTER_HIGH_SCORE
        bne     load_done_dynamic_ready
        jsr     DEMO_RUNTIME_TICK
        bra     load_done_dynamic_ready
load_done_dynamic_high
        ifne    COMPLETE_PROFILE
        lbsr    install_demo_runtime
        endc
        jsr     DEMO_RUNTIME_TICK
load_done_dynamic_ready
        else
        ifne    COMPLETE_PROFILE
        ldb     PRES_SCREEN
        cmpb    #PRESENTATION_MAP_HIGH_SCORE
        blo     load_done_dynamic_ready
        jsr     DEMO_RUNTIME_TICK
load_done_dynamic_ready
        endc
        endc
        lda     PRES_HOLD_STATE
        beq     load_done_publish
        cmpa    #PRES_HOLD_HYDRATE
        bne     load_done_publish
        lda     PRES_SCREEN
        cmpa    #PRESENTATION_MAP_ATTRACT
        bne     load_done_hold_plain
        ifne    ATTRACT_OVERLAY_ENABLED
        lda     #$FF
        sta     PRES_ACTOR_PHASE
        lda     #$34
        sta     PAR5
        jsr     PRESENTATION_ATTRACT_OVERLAY
        bra     load_done_hold_owner
        else
        bra     load_done_hold_plain
        endc
load_done_hold_plain
        lda     #$34
        sta     PAR5
        jsr     PRES_MAIN_FB_CAPTURE
load_done_hold_owner
        tst     PRES_HOLD_OWNER
        bne     load_done_hold_second
        lda     #1
        sta     PRES_HOLD_OWNER
        lda     FB_FRONT_ID
        ldb     FB_BACK_ID
        stb     FB_FRONT_ID
        sta     FB_BACK_ID
        lda     PRES_SCREEN
        lbsr    start_screen
        rts
load_done_hold_second
        orcc    #$10
        lda     FB_FRONT_ID
        ldb     FB_BACK_ID
        stb     FB_FRONT_ID
        sta     FB_BACK_ID
        andcc   #$EF
        jsr     PRES_MAIN_FB_FINISH
        lda     #PRES_HOLD_FINAL
        sta     PRES_HOLD_STATE
load_done_publish
        lda     #$34
        sta     PAR5
        orcc    #$10
        lda     #1
        sta     PENDING
        andcc   #$EF
        ifne    HIGHSCORE_TEST_PROFILE+COMPLETE_PROFILE
        ldx     #PRES_MAIN_SCREEN_MODES
        else
        ldx     #screen_modes
        endc
        ldb     PRES_SCREEN
        lda     b,x
        sta     PRES_MODE
load_done_normal
        lda     #$FF
        sta     PRES_PHASE
        ldd     #PLAYER_BG
        std     PLAYER_BG_PTR
        clr     PLAYER_BG_VALID
load_timer_reset
        clr     PRES_TIMER
        clr     PRES_TIMER+1
        ifne    HIGHSCORE_TEST_PROFILE
        clr     PRES_NAME_TIMER_PHASE
        clr     PRES_NAME_TIMER_BOX
        endc
        lda     #1
        rts

draw_cell
        ldy     PRES_DST
        lbsr    draw_tile_id
        ldd     PRES_DST
        addd    #4
        std     PRES_DST
        rts

draw_tile_id
        cmpb    #PRESENTATION_GAMEPLAY_TILE_BASE
        blo     draw_cold_tile
        subb    #PRESENTATION_GAMEPLAY_TILE_BASE
        clra
        addd    #PRESENTATION_GAMEPLAY_LOOKUP_OFFSET
        lbsr    cold_ptr
        lda     ,x
        ldb     #32
        mul
        ldu     #PRESENTATION_GAMEPLAY_TILES
        leau    d,u
        tfr     y,x
        tfr     u,y
        jsr     BLIT_TILE
        rts
draw_cold_tile
        tfr     b,a
        ldb     #32
        mul
        addd    #PRESENTATION_TILE_ATLAS_OFFSET
        lbsr    cold_ptr
        tfr     x,u
        tfr     y,x
        tfr     u,y
        jsr     BLIT_TILE
        rts

        ifeq    BUG011_DEVELOPMENT_PROFILE
draw_coin_slots
        ldb     PRES_SCREEN
        cmpb    #PRESENTATION_MAP_HIGH_SCORE
        bne     draw_coins_done
        lda     PRES_CREDITS
        beq     draw_coins_done
        sta     PRES_COIN_COUNT
        ldy     #PRESENTATION_COIN_DST_0
draw_coin_next
        ldb     #PRESENTATION_COIN_TILE
        pshs    y
        lbsr    draw_tile_id
        puls    y
        leay    PRESENTATION_COIN_DST_1-PRESENTATION_COIN_DST_0,y
        dec     PRES_COIN_COUNT
        bne     draw_coin_next
draw_coins_done
        rts
        endc

; Return X as a CPU pointer into the cold physical page selected by D.
cold_ptr
        tfr     d,x
        tfr     a,b
        andb    #$E0
        lsrb
        lsrb
        lsrb
        lsrb
        lsrb
        addb    #PRESENTATION_COLD_PAGE
        stb     PAR5
        tfr     x,d
        anda    #$1F
        adda    #$A0
        tfr     d,x
        rts

cold_read_byte
        ldd     PRES_IN
        addd    #1
        std     PRES_IN
        subd    #1
        lbsr    cold_ptr
        lda     ,x
        rts

map_back
        lda     BACK_ID
        bne     map_b
        lda     #$30
        bra     map_store
map_b
        lda     #$2C
map_store
        sta     PAR1
        inca
        sta     PAR2
        inca
        sta     PAR3
        inca
        sta     PAR4
        lda     #$3A
        sta     PAR5
        rts

hold
        lda     #1
        rts
timer
        ldd     PRES_TIMER
        addd    #1
        std     PRES_TIMER
        rts
attract_tick
        lda     PRES_HOLD_STATE
        cmpa    #PRES_HOLD_FINAL
        bne     attract_tick_prepare
        tst     PENDING
        bne     hold
        clr     PRES_HOLD_STATE
attract_tick_prepare
attract_tick_ready
        lbsr    timer
        ldd     PRES_TIMER
        cmpd    #558
        bhs     attract_next
        ifne    ATTRACT_OVERLAY_ENABLED
        jsr     PRESENTATION_ATTRACT_OVERLAY
        endc
        bra     hold
attract_next
        ifne    BUG011_DEVELOPMENT_PROFILE
        ifne    HIGHSCORE_TEST_PROFILE
        clr     PRES_CONTEXT
        endc
        lda     #PRESENTATION_MAP_INSTRUCTIONS
        ifne    HIGHSCORE_TEST_PROFILE
        lbsr    install_aux_runtime
        endc
        else
        lda     #PRESENTATION_MAP_LEVEL_START
        endc
        lbsr    start_screen
        lda     #1
        rts
        ifne    BUG011_DEVELOPMENT_PROFILE
instructions_tick
        lda     PRES_HOLD_STATE
        cmpa    #PRES_HOLD_FINAL
        bne     instructions_tick_ready
        tst     PENDING
        bne     hold
        clr     PRES_HOLD_STATE
instructions_tick_ready
        lbsr    timer
        jsr     INSTRUCTION_RUNTIME_TICK
instructions_runtime_return
        tsta
        beq     hold
        lda     #PRESENTATION_MAP_LEVEL_START
        lbsr    start_screen
        lda     #1
        rts
        endc
credit_tick
        ifne    HIGHSCORE_TEST_PROFILE
        lda     PRES_SCREEN
        cmpa    #PRESENTATION_MAP_HIGH_SCORE
        lbeq    hold
        endc
        bsr     timer
        cmpd    #600
        blo     hold
        lda     #PRESENTATION_MAP_ATTRACT
        lbsr    start_screen
        lda     #1
        rts
level_tick
        lbsr    timer
        cmpd    #180
        blo     hold
        ifne    COMPLETE_PROFILE
        lda     PRES_CONTEXT
        beq     level_tick_demo_check
        cmpa    #PRES_CONTEXT_NEXT_STAGE
        bne     live_begin
        clr     PRES_CONTEXT
        clr     PRES_MODE
        clra
        rts
level_tick_demo_check
        endc
        tst     PENDING
        ifne    COMPLETE_PROFILE
        lbne    hold
        else
        bne     hold
        endc
        tst     ACTIVE
        ifne    COMPLETE_PROFILE
        lbne    hold
        else
        bne     hold
        endc
        tst     PRES_CONTEXT
        bne     live_begin
        ifne    COMPLETE_PROFILE
        lbsr    init_gameplay
        clr     PRES_TIMER
        clr     PRES_TIMER+1
        clr     PRES_DEMO_ROUTE ; CoCo walk starts after automatic maze entry
        lda     #$FF
        sta     PRES_DEMO_LAST_X
        sta     PRES_DEMO_LAST_Y
        sta     PRES_DEMO_DIR
        lbsr    install_demo_runtime
        lda     #MODE_DEMO
        sta     PRES_MODE
        clra
        rts
        else
        ifne    BUG011_DEVELOPMENT_PROFILE
        lda     #PRESENTATION_MAP_ATTRACT
        lbsr    start_screen
        lda     #1
        rts
        else
        lbsr    init_gameplay
        clr     PRES_TIMER
        clr     PRES_TIMER+1
        clr     PRES_DEMO_ROUTE ; CoCo walk starts after automatic maze entry
        lda     #$FF
        sta     PRES_DEMO_LAST_X
        sta     PRES_DEMO_LAST_Y
        sta     PRES_DEMO_DIR
        lda     #MODE_DEMO
        sta     PRES_MODE
        clra
        rts
        endc
        endc
live_begin
        lbsr    init_gameplay
        clr     PRES_MODE
        clra
        rts
init_gameplay
        lbsr    gameplay_reentry
        jsr     PRES_MAIN_INIT
        jsr     PRES_MAIN_MAZE
        jsr     PRES_MAIN_GATES
        jsr     PRES_MAIN_ENTITIES
        jsr     PRES_MAIN_PLAYER
        jsr     PRES_MAIN_ENEMY
        inc     FB_INIT_STATE   ; shared initialization clears this ownership flag
        lda     #RF_STAGE       ; replace the presentation map on both A/B owners
        sta     $007F
        rts

gameplay_reentry
        lda     #$34            ; shared initializers write game-state through PAR5
        sta     PAR5
        lda     BACK_ID         ; owner 0 -> $30; owner 1 -> $2C
        nega
        lsla
        lsla
        adda    #$30
        ldx     #PAR1
        ldb     #4
gameplay_reentry_map_page
        sta     ,x+
        inca
        decb
        bne     gameplay_reentry_map_page
        ldx     #FB_META_A      ; invalidate both 256-byte A/B ledgers
        clra
        clrb
gameplay_reentry_clear
        std     ,x++
        cmpx    #FB_META_END
        blo     gameplay_reentry_clear
        lda     #AUDIO_RUNTIME_PAGE
        sta     PAR5
        jsr     AUDIO_INSTALL_EXEC
        rts

        ifne    HIGHSCORE_TEST_PROFILE
demo_tick
        lbra    hold
gameover_tick
        lbra    hold
name_tick
        lbsr    timer
        inc     PRES_NAME_TIMER_PHASE
        lda     PRES_NAME_TIMER_PHASE
        cmpa    #PRESENTATION_NAME_ENTRY_TIMER_FRAMES
        blo     name_input
        clr     PRES_NAME_TIMER_PHASE
        lda     PRES_NAME_TIMER_BOX
        lbsr    name_timer_draw
        inc     PRES_NAME_TIMER_BOX
        lda     PRES_NAME_TIMER_BOX
        cmpa    #PRESENTATION_NAME_ENTRY_TIMER_COUNT
        bhs     name_timeout
name_input
        jsr     DEMO_RUNTIME_TICK
        tsta
        beq     name_hold
name_timeout
        lbsr    module_commit_name
        clr     PRES_HOLD_STATE
        lda     #PRESENTATION_MAP_HIGH_SCORE
        clr     PENDING
        lbsr    start_screen
        lda     #1
        rts
name_hold
        lbra    hold

name_timer_draw
        sta     PRES_TMP_H
        lda     FB_BACK_ID
        jsr     PRES_MAIN_FB_PREPARE
name_timer_next
        lda     PRES_TMP_H
        ldb     #PRESENTATION_NAME_ENTRY_TIMER_RECORD_BYTES
        mul
        addd    #PRESENTATION_NAME_ENTRY_TIMER_TABLE
        lbsr    cold_ptr
        ldd     ,x
        tfr     d,y
        ldb     3,x
        lbsr    draw_tile_id
        dec     PRES_TMP_H
        bpl     name_timer_next
        lda     #$34
        sta     PAR5
        rts
        else
        ifne    COMPLETE_PROFILE
demo_tick
        lda     DEATH
        beq     demo_run
        cmpa    #3
        bne     demo_death_tick
        tst     DEATH_T
        beq     demo_death_done
demo_death_tick
        jsr     PRES_MAIN_DEATH
        jsr     PRES_MAIN_RENDER
        lbra    hold
demo_death_done
        lda     #PRESENTATION_MAP_ATTRACT
        lbsr    start_screen
        lda     #1
        rts
demo_run
        lbsr    timer
        jsr     DEMO_RUNTIME_TICK
        ldd     PRES_TIMER
        cmpd    #3600
        blo     demo_return
        lda     #PRESENTATION_MAP_ATTRACT
        lbsr    start_screen
        lda     #1
        rts
demo_return
        clra
        rts
        else
        ifeq    BUG011_DEVELOPMENT_PROFILE
demo_tick
        lda     DEATH
        beq     demo_run
        cmpa    #3
        bne     demo_death_tick
        tst     DEATH_T
        beq     demo_death_done ; first complete death ends the demo before respawn
demo_death_tick
        jsr     PRES_MAIN_DEATH
        jsr     PRES_MAIN_RENDER
        lbra    hold
demo_death_done
        lda     #PRESENTATION_MAP_ATTRACT
        lbsr    start_screen
        lda     #1
        rts
demo_run
        lbsr    timer
        jsr     DEMO_RUNTIME_TICK
        ldd     PRES_TIMER
        cmpd    #3600
        blo     demo_return
        lda     #PRESENTATION_MAP_ATTRACT
        lbsr    start_screen
        lda     #1
        rts
demo_return
        clra
        rts
gameover_tick
        lbsr    timer
        cmpd    #180
        lblo    hold
        lda     #PRESENTATION_MAP_ENTER_HIGH_SCORE
        lbsr    start_screen
        lda     #1
        rts

name_tick
        lda     PRES_EVENT
        bita    #1
        lbeq    hold
        lda     #PRESENTATION_MAP_ATTRACT
        lbsr    start_screen
        lda     #1
        rts
        endc
        endc
        endc
add_credit
        lda     PRES_CREDITS
        cmpa    #PRESENTATION_COIN_SLOT_COUNT
        bhs     add_coin
        inca
        sta     PRES_CREDITS
add_coin
        rts

        ifne    0
init_high_scores
        lda     #$34
        sta     PAR5
        ldx     #PRESENTATION_HIGHSCORE_BASE
        ldu     #90
        clra
init_high_scores_loop
        sta     ,x+
        leau    -1,u
        bne     init_high_scores_loop
        rts

prepare_name_entry
        ldx     #SCORE
        ldu     #PRES_SCORE_H
        ldb     #3
prepare_name_score
        lda     ,x+
        sta     ,u+
        decb
        bne     prepare_name_score
        clr     PRES_NAME_LEN
        lda     #8
        sta     PRES_NAME_ROW
        lda     #2
        sta     PRES_NAME_COL
        lda     #DIR_NONE
        sta     PRES_NAME_LAST_DIR
        clr     PRES_NAME_REPEAT
        rts

qualify_score
        lda     #$FF
        sta     PRES_INSERT
        lda     #$34
        sta     PAR5
        ldx     #PRESENTATION_HIGHSCORE_BASE
        clrb
qualify_next
        lda     PRES_SCORE_H
        cmpa    ,x
        bhi     qualify_found
        blo     qualify_advance
        lda     PRES_SCORE_M
        cmpa    1,x
        bhi     qualify_found
        blo     qualify_advance
        lda     PRES_SCORE_L
        cmpa    2,x
        bhi     qualify_found
qualify_advance
        leax    10,x
        incb
        cmpb    #PRESENTATION_HIGHSCORE_COUNT
        blo     qualify_next
        rts
qualify_found
        stb     PRES_INSERT
        rts

name_input_tick
        jsr     PRES_MAIN_READ_JOY
        lda     JOY_DIR
        cmpa    #DIR_NONE
        beq     name_input_none
        cmpa    PRES_NAME_LAST_DIR
        bne     name_input_move
        dec     PRES_NAME_REPEAT
        bne     name_input_none
name_input_move
        sta     PRES_NAME_LAST_DIR
        lda     #6
        sta     PRES_NAME_REPEAT
        lbsr    name_move
        tsta
        rts
name_input_none
        clra
        rts

name_move
        lda     JOY_DIR
        cmpa    #DIR_N
        bne     name_move_south
        tst     PRES_NAME_ROW
        beq     name_moved
        dec     PRES_NAME_ROW
        bra     name_moved
name_move_south
        cmpa    #DIR_S
        bne     name_move_west
        lda     PRES_NAME_ROW
        cmpa    #8
        bhs     name_moved
        inc     PRES_NAME_ROW
        bra     name_moved
name_move_west
        cmpa    #DIR_W
        bne     name_move_east
        tst     PRES_NAME_COL
        beq     name_moved
        dec     PRES_NAME_COL
        bra     name_moved
name_move_east
        lda     PRES_NAME_COL
        cmpa    #4
        bhs     name_moved
        inc     PRES_NAME_COL
name_moved
        lda     PRES_NAME_ROW
        ldb     #5
        mul
        addb    PRES_NAME_COL
        tfr     d,x
        leax    PRESENTATION_NAME_ENTRY_NODE_TILES,pcr
        abx
        ldb     ,x
        cmpb    #PRES_NAME_END
        beq     name_end
        cmpb    #PRES_NAME_CL
        beq     name_delete
        cmpb    #PRES_NAME_END
        bhs     name_redraw
        lda     PRES_NAME_LEN
        cmpa    #PRESENTATION_HIGHSCORE_NAME_BYTES
        bhs     name_redraw
        stb     PRES_NAME_TILE
        tfr     a,b
        ldx     #PRESENTATION_PENDING_NAME
        abx
        lda     PRES_NAME_TILE
        sta     ,x
        inc     PRES_NAME_LEN
        bra     name_redraw
name_delete
        tst     PRES_NAME_LEN
        beq     name_redraw
        dec     PRES_NAME_LEN
        ldx     #PRESENTATION_PENDING_NAME
        lda     PRES_NAME_LEN
        leax    a,x
        ldb     #PRESENTATION_NAME_ENTRY_BLACK_TILE
        stb     ,x
name_redraw
        lbsr    name_update_frame
        clra
        rts
name_end
        lda     #1
        rts

commit_name
        lda     PRES_INSERT
        cmpa    #$FF
        beq     commit_done
        sta     PRES_TMP_H
        lda     #$34
        sta     PAR5
        ldx     #PRESENTATION_HIGHSCORE_BASE+70
        ldu     #PRESENTATION_HIGHSCORE_BASE+80
commit_shift
        lda     PRES_TMP_H
        cmpa    PRES_INSERT
        blo     commit_write
        ldb     #10
commit_record
        lda     ,x+
        sta     ,u+
        decb
        bne     commit_record
        leax    -20,x
        leau    -20,u
        dec     PRES_TMP_H
        bra     commit_shift
commit_write
        ldx     #PRESENTATION_HIGHSCORE_BASE
        ldb     PRES_INSERT
        beq     commit_write_score
commit_find
        leax    10,x
        decb
        bne     commit_find
commit_write_score
        lda     PRES_SCORE_H
        sta     ,x+
        lda     PRES_SCORE_M
        sta     ,x+
        lda     PRES_SCORE_L
        sta     ,x+
        ldu     #PRESENTATION_PENDING_NAME
        ldb     #PRESENTATION_HIGHSCORE_NAME_BYTES
commit_write_name
        lda     ,u+
        sta     ,x+
        decb
        bne     commit_write_name
commit_done
        rts

draw_name_screen
        lbsr    map_back
        lbsr    draw_name_fields
        lbsr    draw_entry_scores
        lbsr    name_capture_initial
        lbsr    name_draw_cursor
        lda     #$34
        sta     PAR5
        rts

draw_name_fields
        ldy     #PRESENTATION_NAME_ENTRY_NAME_DST
        ldb     #PRESENTATION_NAME_ENTRY_BLACK_TILE
        lda     #PRESENTATION_HIGHSCORE_NAME_BYTES
draw_name_clear
        pshs    a,y
        lbsr    draw_tile_id
        puls    a,y
        leay    4,y
        deca
        bne     draw_name_clear
        ldx     #PRESENTATION_PENDING_NAME
        ldy     #PRESENTATION_NAME_ENTRY_NAME_DST
        lda     PRES_NAME_LEN
        beq     draw_name_done
draw_name_chars
        ldb     ,x+
        pshs    a,x,y
        lbsr    draw_tile_id
        puls    a,x,y
        leay    4,y
        deca
        bne     draw_name_chars
draw_name_done
        rts

draw_entry_scores
        ldx     #PRES_SCORE_H
        ldy     #PRESENTATION_NAME_ENTRY_SCORE_DST
        lbsr    draw_score
        lda     #$34
        sta     PAR5
        ldx     #PRESENTATION_HIGHSCORE_BASE
        ldd     ,x
        std     PRES_TMP_H
        ldd     2,x
        std     PRES_TMP_L
        ldx     #PRES_TMP_H
        ldy     #PRESENTATION_NAME_ENTRY_TOP_DST
        lbsr    draw_score
        rts

draw_high_score_screen
        lda     #$34
        sta     PAR5
        ldx     #PRESENTATION_HIGHSCORE_BASE
        ldu     #PRESENTATION_HIGHSCORE_TOP_NAME_DST
        ldy     #PRESENTATION_HIGHSCORE_TOP_SCORE_DST
        lbsr    draw_high_score_entry
        leau    PRESENTATION_HIGHSCORE_ENTRY_NAME_DST-PRESENTATION_HIGHSCORE_TOP_NAME_DST,u
        leay    PRESENTATION_HIGHSCORE_ENTRY_SCORE_DST-PRESENTATION_HIGHSCORE_TOP_SCORE_DST-24,y
        ldb     #PRESENTATION_HIGHSCORE_COUNT-1
draw_high_score_rows
        lbsr    draw_high_score_entry
        leau    1280,u
        leay    1256,y
        decb
        bne     draw_high_score_rows
        rts

draw_high_score_entry
        stx     PRES_NAME_PTR
        pshs    y
        tfr     u,y
        ldx     PRES_NAME_PTR
        leax    3,x
        lbsr    draw_name_record
        puls    y
        ldx     PRES_NAME_PTR
        lbsr    draw_score
        leax    7,x
        rts

draw_name_record
        ldb     #PRESENTATION_HIGHSCORE_NAME_BYTES
draw_name_record_loop
        lda     ,x+
        pshs    b,x,y
        tsta
        bne     draw_name_record_tile
        ldb     #PRESENTATION_NAME_ENTRY_BLACK_TILE
        bra     draw_name_record_draw
draw_name_record_tile
        tfr     a,b
draw_name_record_draw
        lbsr    draw_tile_id
        puls    b,x,y
        leay    4,y
        decb
        bne     draw_name_record_loop
        rts

draw_score
        stx     PRES_NAME_PTR
        lda     #3
        sta     PRES_DIGIT
draw_score_byte
        ldx     PRES_NAME_PTR
        lda     ,x+
        stx     PRES_NAME_PTR
        sta     PRES_VALUE
        lsra
        lsra
        lsra
        lsra
        anda    #$0F
        lbsr    draw_score_digit
        lda     PRES_VALUE
        anda    #$0F
        lbsr    draw_score_digit
        dec     PRES_DIGIT
        bne     draw_score_byte
        rts
draw_score_digit
        tfr     a,b
        ldx     #score_glyphs
        abx
        ldb     ,x
        pshs    y
        lbsr    draw_tile_id
        puls    y
        leay    4,y
        rts

name_capture_initial
        lda     #$34
        sta     PAR5
        ldx     #PRESENTATION_NAME_ENTRY_CURSOR_DST
        ldu     #PRES_CURSOR_SAVE_A
        lbsr    cursor_capture
        ldx     #PRES_CURSOR_SAVE_A
        ldu     #PRES_CURSOR_SAVE_B
        ldy     #64
name_copy_save
        ldd     ,x++
        std     ,u++
        leay    -1,y
        bne     name_copy_save
        rts

name_update_frame
        lda     FB_BACK_ID
        sta     PRES_NAME_OWNER
        lda     #$34
        sta     PAR5
        jsr     PRES_MAIN_FB_PREPARE
        lbsr    map_back
        lbsr    cursor_restore
        lbsr    draw_name_fields
        lbsr    name_capture_owner
        lbsr    name_draw_cursor
        lda     #$34
        sta     PAR5
        jmp     PRES_MAIN_FB_FINISH

cursor_capture
        ldy     #16
cursor_capture_row
        ldd     ,x++
        std     ,u++
        ldd     ,x++
        std     ,u++
        ldd     ,x++
        std     ,u++
        ldd     ,x++
        std     ,u++
        leax    152,x
        leay    -1,y
        bne     cursor_capture_row
        rts

cursor_restore
        lda     PRES_NAME_OWNER
        beq     cursor_restore_a
        ldu     #PRES_CURSOR_SAVE_B
        bra     cursor_restore_ready
cursor_restore_a
        ldu     #PRES_CURSOR_SAVE_A
cursor_restore_ready
        ldx     #PRESENTATION_NAME_ENTRY_CURSOR_DST
        ldy     #16
cursor_restore_row
        ldd     ,u++
        std     ,x++
        ldd     ,u++
        std     ,x++
        ldd     ,u++
        std     ,x++
        ldd     ,u++
        std     ,x++
        leax    152,x
        leay    -1,y
        bne     cursor_restore_row
        rts

name_capture_owner
        lda     PRES_NAME_OWNER
        beq     name_capture_a
        ldu     #PRES_CURSOR_SAVE_B
        bra     name_capture_ready
name_capture_a
        ldu     #PRES_CURSOR_SAVE_A
name_capture_ready
        ldx     #PRESENTATION_NAME_ENTRY_CURSOR_DST
        lbsr    cursor_capture
        rts

name_draw_cursor
        lda     PRES_NAME_ROW
        ldb     #5
        mul
        addb    PRES_NAME_COL
        lslb
        ldx     #PRESENTATION_NAME_ENTRY_NODE_DESTINATIONS
        abx
        ldd     ,x
        tfr     d,x
        pshs    x
        ldd     #PRESENTATION_NAME_ENTRY_CURSOR_OFFSET
        lbsr    cold_ptr
        tfr     x,u
        puls    x
        jsr     PRESENTATION_MODULE_DRAW
        rts

score_glyphs
        fcb     PRESENTATION_GLYPH_0,PRESENTATION_GLYPH_1
        fcb     PRESENTATION_GLYPH_2,PRESENTATION_GLYPH_3
        fcb     PRESENTATION_GLYPH_4,PRESENTATION_GLYPH_5
        fcb     PRESENTATION_GLYPH_6,PRESENTATION_GLYPH_7
        fcb     PRESENTATION_GLYPH_8,PRESENTATION_GLYPH_9

        endc

        ifne    HIGHSCORE_TEST_PROFILE
module_qualify_score
        lda     #$FF
        sta     PRES_INSERT
        ldx     #PRESENTATION_HIGHSCORE_BASE
        clrb
module_qualify_loop
        ldd     PRES_SCORE_H
        cmpd    ,x
        bhi     module_qualify_found
        blo     module_qualify_next
        lda     PRES_SCORE_L
        cmpa    2,x
        bhi     module_qualify_found
module_qualify_next
        leax    10,x
        incb
        cmpb    #PRESENTATION_HIGHSCORE_COUNT
        blo     module_qualify_loop
        rts
module_qualify_found
        stb     PRES_INSERT
        rts

module_commit_name
        ldx     #PRESENTATION_HIGHSCORE_BASE+80
        ldu     #PRESENTATION_HIGHSCORE_BASE+90
        ldb     #PRESENTATION_HIGHSCORE_COUNT-1
        subb    PRES_INSERT
        beq     module_commit_write
        lda     #PRESENTATION_HIGHSCORE_RECORD_BYTES
        mul
        tfr     d,y
module_commit_shift
        lda     ,-x
        sta     ,-u
        leay    -1,y
        bne     module_commit_shift
module_commit_write
        ldx     #PRESENTATION_HIGHSCORE_BASE
        ldb     PRES_INSERT
module_commit_find
        beq     module_commit_score
        leax    10,x
        decb
        bra     module_commit_find
module_commit_score
        ldd     PRES_SCORE_H
        std     ,x++
        lda     PRES_SCORE_L
        sta     ,x+
        ldu     #PRESENTATION_PENDING_NAME
        ldd     ,u++
        std     ,x++
        ldb     #5
module_commit_name_loop
        lda     ,u+
        sta     ,x+
        decb
        bne     module_commit_name_loop
module_commit_done
        rts
        endc

scan_keys
        clr     PRES_EVENT
        ldy     #PRES_PREV
        ifne    HIGHSCORE_TEST_PROFILE+COMPLETE_PROFILE
        ldx     #PRES_MAIN_SCAN_DRIVES
        ldu     #PRES_MAIN_SCAN_BITS
        clrb
        else
        leax    scan_drives,pcr
        leau    scan_bits,pcr
        ldb     #0
        endc
scan_loop
        lda     b,x
        sta     PIA_DB
        lda     PIA_DA
        ifne    COMPLETE_PROFILE
        anda    #$7F            ; PA7 is joystick comparator, not a key row
        endc
        pshs    a
        coma
        anda    b,y
        beq     scan_next
        lda     PRES_EVENT
        ora     b,u
        sta     PRES_EVENT
scan_next
        puls    a
        sta     b,y
        incb
        cmpb    #3
        blo     scan_loop
        lda     #$FF
        sta     PIA_DB
        lda     #$34
        sta     PIA_CRA
        ifne    COMPLETE_PROFILE
        nop                     ; gameplay input owns the joystick selector
        nop
        nop
        else
        sta     PIA_CRB
        endc
        rts
        ifne    HIGHSCORE_TEST_PROFILE
draw_actor_overlay
        rts
colour_tile equ draw_actor_overlay
colour_surface equ draw_actor_overlay
        else
draw_actor_overlay
        ldb     PRES_ACTOR_FRAME
        lda     #SPARSE_ENEMY_PAYLOAD_PAGE
        sta     PAR5
        lda     #3
        mul
        ldx     #SPARSE_ENEMY_INDEX_ADDR
actor_index_ready
        leax    d,x
        ldu     1,x
        lda     ,x
        sta     PAR5
        ldx     PRES_DST
        jsr     PRESENTATION_MODULE_DRAW
        rts

; Recolour each nonzero packed pixel pair in the selected instruction cell.
colour_tile
        lda     #8
        sta     PRES_RUN
colour_tile_row
        ldb     #4
colour_tile_byte
        lda     ,x
        beq     colour_tile_skip
        lda     PRES_HIGHLIGHT
        lsla
        lsla
        lsla
        lsla
        adda    PRES_HIGHLIGHT
        sta     ,x
colour_tile_skip
        leax    1,x
        decb
        bne     colour_tile_byte
        leax    156,x
        dec     PRES_RUN
        bne     colour_tile_row
        rts

; U selects a generated {count, delta, nibble-selector} stream and X selects
; its 16x16 destination. Selectors 1/2/3 replace low/high/both nibbles.
colour_surface
        ldb     ,u+
        stb     PRES_RUN
colour_surface_next
        ldb     ,u+
        cmpb    #$FF
        beq     colour_surface_extended
        abx
        bra     colour_surface_selector
colour_surface_extended
        ldd     ,u++
        leax    d,x
colour_surface_selector
        lda     ,u+
        cmpa    #3
        beq     colour_surface_both
        cmpa    #2
        beq     colour_surface_high
        lda     ,x
        anda    #$F0
        ora     PRES_HIGHLIGHT
        sta     ,x
        bra     colour_surface_advance
colour_surface_high
        lda     PRES_HIGHLIGHT
        lsla
        lsla
        lsla
        lsla
        sta     PRES_VALUE
        lda     ,x
        anda    #$0F
        ora     PRES_VALUE
        sta     ,x
        bra     colour_surface_advance
colour_surface_both
        lda     PRES_HIGHLIGHT
        lsla
        lsla
        lsla
        lsla
        adda    PRES_HIGHLIGHT
        sta     ,x
colour_surface_advance
        dec     PRES_RUN
        bne     colour_surface_next
        rts
        endc

        ifeq    BUG011_DEVELOPMENT_PROFILE
instruction_phase_rows
instruction_phase_colors
        fcb     1,2,3,1,2,3
instruction_phase_starts
        fdb     $3940,$4834,$5234,$7540,$7F34,$8434
        endc

        ifeq    HIGHSCORE_TEST_PROFILE+COMPLETE_PROFILE
map_stream_offsets
        fdb PRESENTATION_MAP_STREAM_0
        fdb PRESENTATION_MAP_STREAM_1
        fdb PRESENTATION_MAP_STREAM_2
        fdb PRESENTATION_MAP_STREAM_3
        fdb PRESENTATION_MAP_STREAM_4
        fdb PRESENTATION_MAP_STREAM_5
screen_modes
        ifne    BUG011_DEVELOPMENT_PROFILE
        fcb MODE_ATTRACT,MODE_INSTRUCTIONS,MODE_LEVEL,MODE_CREDIT,MODE_GAMEOVER,MODE_NAME
        else
        fcb MODE_ATTRACT,MODE_LEVEL,MODE_LEVEL,MODE_CREDIT,MODE_GAMEOVER,MODE_NAME
        endc
scan_drives
        fcb $FD,$DF,$BF
scan_bits
        fcb $01,$02,$04
        endc

PRES_MAGIC equ $00A4
PRES_MODE equ $00A5
PRES_SCREEN equ $00A6
PRES_CONTEXT equ $00A7
PRES_CREDITS equ $00A8
PRES_EVENT equ $00A9
PRES_CELL equ $00AA
PRES_X equ $00AC
PRES_Y equ $00AD
PRES_DST equ $00AE
PRES_WORK equ $00D1
PRES_TIMER equ $00B0
PRES_PREV equ $00B2
PRES_IN equ $00B5
PRES_OUT equ $00B7
PRES_REMAIN equ $00B9
        ifne    HIGHSCORE_TEST_PROFILE
PRES_RUN equ $00EA
PRES_VALUE equ $00EB
        else
PRES_RUN equ $00BB
PRES_VALUE equ $00BC
        endc
PRES_MAPS equ $00BD
PRES_COIN_COUNT equ $00BE
PRES_SCORE_H equ $00BF
PRES_SCORE_M equ $00C0
PRES_SCORE_L equ $00C1
PRES_TMP_H equ $00C2
PRES_TMP_M equ $00C3
PRES_TMP_L equ $00C4
PRES_DIGIT equ $00C5
PRES_ROWS equ $00C6
PRES_INSERT equ $00C9
PRES_PHASE equ $00CA
PRES_NAME_LEN equ $00CB
PRES_ACTOR_X equ $00CC
PRES_ACTOR_Y equ $00CD
PRES_ACTOR_FRAME equ $00CE
PRES_HIGHLIGHT equ $00CF
PRES_ACTOR_KIND equ $00D0
PRES_DEMO_CAUSE equ $00D1
PRES_PREP_STATE equ $00D2
PRES_ACTOR_PHASE equ $00D3
PRES_HOLD_STATE equ $00D4
PRES_HOLD_CHUNK equ $00D5
PRES_HOLD_SAVED_FRONT equ $00D6
PRES_HOLD_SAVED_BACK equ $00D7
PRES_HOLD_GEN equ $00D8
PRES_HOLD_OWNER equ $00D9
PRES_DEMO_ROUTE equ $00DA
PRES_DEMO_LAST_X equ $00DB
PRES_DEMO_LAST_Y equ $00DC
PRES_DEMO_DIR equ $00DD
PRES_DEMO_NEXT equ $00DE
PRES_HOLD_COPY equ $80
PRES_HOLD_PUBLISH equ $81
PRES_HOLD_HYDRATE equ 3
PRES_HOLD_FINAL equ $81
FB_FRONT_ID equ $008F
FB_BACK_ID equ $0090
PRESENTATION_PENDING_NAME equ $AFDE
PRES_NAME_ROW equ $00DF
PRES_NAME_COL equ $00E0
PRES_NAME_REPEAT equ $00E1
PRES_NAME_LAST_DIR equ $00E2
PRES_NAME_OWNER equ $00E3
PRES_NAME_PTR equ $00E4
PRES_NAME_TILE equ $00E6
PRES_NAME_FLAGS equ $00E7
PRES_NAME_TIMER_PHASE equ $00E8
PRES_NAME_TIMER_BOX equ $00E9
PRES_CURSOR_SAVE_A equ $A590
PRES_CURSOR_SAVE_B equ $A610
PRES_NAME_CL equ $FE
PRES_NAME_END equ $FD

presentation_module_end
        end
