; FEAT-002 low-RAM presentation flow, copied to $1900 during GMC boot.
        pragma  nodollarlocal,6809
        setdp   $00
        include "ladybug_presentation.inc"
        include "ladybug_presentation_symbols.inc"

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

        org $1900

presentation_flow_tick
        lda     PRES_MAGIC
        cmpa    #$A5
        beq     pft_helper_ready
        lbsr    install_aux_runtime
pft_helper_ready
        lbsr    scan_keys
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
        lda     #PRESENTATION_MAP_ATTRACT
        lbsr    start_screen
        lda     #1
        rts
pft_ready
        lda     PRES_EVENT
        anda    #$06
        beq     pft_mode
        lbsr    add_credit
        lda     #PRESENTATION_MAP_HIGH_SCORE
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
        ifeq    BUG011_DEVELOPMENT_PROFILE
        cmpa    #MODE_DEMO
        lbeq    demo_tick
        endc
        cmpa    #MODE_CREDIT
        lbeq    credit_tick
        cmpa    #MODE_LEVEL
        lbeq    level_tick
        ifne    BUG011_DEVELOPMENT_PROFILE
        lbra    attract_tick
        else
        cmpa    #MODE_GAMEOVER
        lbeq    gameover_tick
        lbra    name_tick
        endc

install_aux_runtime
        lda     #$23
        sta     PAR5
        ldx     #$A422
        ldy     #$0300
        ldu     #PRESENTATION_AUX_RUNTIME_BYTES
install_aux_runtime_byte
        lda     ,x+
        sta     ,y+
        leau    -1,u
        bne     install_aux_runtime_byte
        lda     #$34
        sta     PAR5
        rts

normal_tick
        lda     DEATH
        cmpa    #4
        bne     normal_stage
        ifne    BUG011_DEVELOPMENT_PROFILE
        lda     #PRESENTATION_MAP_ATTRACT
        else
        lda     #PRESENTATION_MAP_GAME_OVER
        endc
        lbsr    start_screen
        lda     #1
        rts
normal_stage
        tst     STAGE_PENDING
        beq     normal_start
        jsr     PRES_MAIN_NEXT_STAGE
        lda     #1
        sta     PRES_CONTEXT
        lda     #PRESENTATION_MAP_LEVEL_START
        lbsr    start_screen
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
        lbsr    start_screen
        lda     #1
        rts
normal_game
        clra
        rts

start_screen
        sta     PRES_SCREEN
        tfr     a,b
        aslb
        leax    map_stream_offsets,pcr
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
        cmpa    #PRESENTATION_MAP_ATTRACT
        beq     start_screen_hold
        cmpa    #PRESENTATION_MAP_INSTRUCTIONS
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
        clr     ACTIVE
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
        lda     PRES_HOLD_STATE
        beq     load_done_publish
        cmpa    #PRES_HOLD_HYDRATE
        bne     load_done_publish
        lda     PRES_SCREEN
        cmpa    #PRESENTATION_MAP_ATTRACT
        bne     load_done_hold_plain
        ifeq    BUG011_DEVELOPMENT_PROFILE
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
        ldx     #screen_modes
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
        clr     ACTIVE
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
        ifeq    BUG011_DEVELOPMENT_PROFILE
        jsr     PRESENTATION_ATTRACT_OVERLAY
        endc
        bra     hold
attract_next
        ifne    BUG011_DEVELOPMENT_PROFILE
        lda     #PRESENTATION_MAP_INSTRUCTIONS
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
        lbsr    timer
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
        tst     PRES_CONTEXT
        bne     live_begin
        ifne    BUG011_DEVELOPMENT_PROFILE
        lda     #PRESENTATION_MAP_ATTRACT
        lbsr    start_screen
        lda     #1
        rts
        else
        lbsr    init_gameplay
        clr     PRES_TIMER
        clr     PRES_TIMER+1
        lda     #1              ; arcade entry 0 is neutral during maze entry
        sta     PRES_DEMO_ROUTE
        lda     #$FF
        sta     PRES_DEMO_LAST_X
        sta     PRES_DEMO_LAST_Y
        sta     PRES_DEMO_DIR
        lda     #MODE_DEMO
        sta     PRES_MODE
        clra
        rts
        endc
live_begin
        lbsr    init_gameplay
        clr     PRES_MODE
        clra
        rts
init_gameplay
        jsr     PRES_MAIN_INIT
        jsr     PRES_MAIN_MAZE
        jsr     PRES_MAIN_GATES
        jsr     PRES_MAIN_ENTITIES
        jsr     PRES_MAIN_PLAYER
        jsr     PRES_MAIN_ENEMY
        jsr     $081B
        jsr     $0806
        lda     #RF_STAGE       ; replace the presentation map on both A/B owners
        sta     $007F
        rts
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
add_credit
        lda     PRES_CREDITS
        cmpa    #PRESENTATION_COIN_SLOT_COUNT
        bhs     add_coin
        inca
        sta     PRES_CREDITS
add_coin
        rts

scan_keys
        clr     PRES_EVENT
        ldy     #PRES_PREV
        leax    scan_drives,pcr
        leau    scan_bits,pcr
        ldb     #0
scan_loop
        lda     b,x
        sta     PIA_DB
        lda     PIA_DA
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
        sta     PIA_CRB
        rts

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

        ifeq    BUG011_DEVELOPMENT_PROFILE
instruction_phase_rows
instruction_phase_colors
        fcb     1,2,3,1,2,3
instruction_phase_starts
        fdb     $3940,$4834,$5234,$7540,$7F34,$8434
        endc

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
PRES_RUN equ $00BB
PRES_VALUE equ $00BC
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

presentation_module_end
        end
