;==============================================================================
; Ladybug — main.s
;==============================================================================
; Phase 4: joystick-driven Lady Bug movement over the authored screen.
;
; Builds on Phase 2.3 (hi-res 320×192×16 + MMU + palette + IRQ tick) by:
;   - Compiling tiled/coco-screen.tmx into a one-byte tile map and a
;     deduplicated packed 4bpp tile atlas before assembly.
;   - Flattening visible Tiled layers and applying horizontal/vertical flips.
;   - blit_tile: 8 rows x 4 bytes, stride 160.
;   - Polling the right joystick through the PIA DAC/comparator path.
;   - Masked 16x16 player frames with background save/restore.
;   - Semantic maze collision and dot removal.
;
; Visible: the authored screen with a moving, maze-constrained Lady Bug.
;==============================================================================

        pragma  nodollarlocal,6809

;------------------------------------------------------------------------------
; DP allocation (page $02)
;------------------------------------------------------------------------------
        setdp   $02

LAST_FRAME    equ $0200         ; last processed Vbord counter low byte
JOY_X         equ $0201         ; right joystick X, 0..63
FRAMES        equ $0202         ; u16 frame counter
JOY_Y         equ $0204         ; right joystick Y, 0..63
JOY_DIR       equ $0205         ; requested direction or $FF
PLAYER_DIR    equ $0206         ; active direction or $FF
PLAYER_FACE   equ $0207         ; last active direction, 0..3
PLAYER_STEP   equ $0208         ; 2-pixel steps since last cell centre, 0..3
PLAYER_CELL_X equ $0209         ; semantic maze column
PLAYER_CELL_Y equ $020A         ; semantic maze row
PLAYER_FB     equ $020B         ; u16 framebuffer pointer at sprite top-left
JOY_DX        equ $020D         ; absolute X displacement from centre
JOY_DY        equ $020E         ; absolute Y displacement from centre
PLAYER_WANT   equ $020F         ; last non-neutral requested direction
TEST_X        equ $0210         ; candidate/draw maze column
TEST_Y        equ $0211         ; candidate/draw maze row
TEST_DIR      equ $0212         ; direction under collision test
GATE_ID       equ $0213         ; active gate index
GATE_X        equ $0214         ; active gate pivot column
GATE_Y        equ $0215         ; active gate pivot row
DRAW_COUNT    equ $0216         ; gate redraw loop counter
DRAW_TILE     equ $0217         ; tile ID for draw_cell_tile

DIR_NORTH     equ 0
DIR_EAST      equ 1
DIR_SOUTH     equ 2
DIR_WEST      equ 3
DIR_NONE      equ $FF

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
MAZE_STATE equ  $A000           ; writable 576-byte maze-cell copy (PAR5)
GATE_STATE equ  $A240           ; rotation state N/W/S/E; parity selects H/V bar
PLAYER_BG  equ  $A300           ; 128-byte saved background under player

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

        clr     GIME_BORDER     ; canonical Black outside the active framebuffer

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

        ; --- Phase 3 authored screen ---
        lbsr    draw_screen

        ; --- Phase 4 state, joystick, and player sprite ---
        lbsr    init_maze_state
        lbsr    init_gate_state
        lbsr    init_joystick
        lbsr    init_player
        lbsr    draw_player

        ; --- Un-blank: 320×192×16 (CRES=10 + HRES=111 → 4bpp on this build) ---
        lda     #$1E
        sta     GIME_VRES

        ; --- IRQ handler at $FEF7 jump-table slot ---
        lda     #$7E            ; JMP extended
        sta     JT_IRQ
        ldd     #irq_handler
        std     JT_IRQ+1

        clr     FRAMES
        clr     FRAMES+1
        clr     LAST_FRAME

        ; --- Enable Vbord ---
        lda     #%00001000
        sta     GIME_IRQEN
        lda     GIME_IRQEN

        andcc   #%11101111      ; unmask IRQ

;==============================================================================
; mainloop — sample every Vbord; advance two pixels every second Vbord.
;==============================================================================
mainloop
        sync
        lda     FRAMES+1
        cmpa    LAST_FRAME
        beq     mainloop
        sta     LAST_FRAME
        lbsr    read_joystick
        lda     LAST_FRAME
        anda    #$01
        bne     mainloop
phase4_before_tick
        lbsr    player_tick
        bra     mainloop

;==============================================================================
; init_maze_state — copy immutable maze cells to writable game-state RAM.
;
; Inputs:
;   None
;
; Returns:
;   X, Y, U, A, CC — undefined
;
; Side effects:
;   Writes 576 bytes at MAZE_STATE.
;==============================================================================
init_maze_state
        leax    maze_cells,pcr
        ldy     #MAZE_STATE
ims_copy
        lda     ,x+
        sta     ,y+
        cmpy    #MAZE_STATE+576
        blo     ims_copy
        rts

;==============================================================================
; init_gate_state
;
; Inputs: none
; Returns: A, B, X, Y, CC undefined
; Side effects: copies 20 captured initial states to GATE_STATE.
;==============================================================================
init_gate_state
        leax    maze_gates,pcr
        ldy     #GATE_STATE
        ldb     #MAZE_GATE_COUNT
igs_loop
        lda     2,x
        sta     ,y+
        leax    3,x
        decb
        bne     igs_loop
        rts

;==============================================================================
; init_joystick — configure the PIAs for right-joystick DAC conversion.
;
; Inputs:
;   None
;
; Returns:
;   A, CC — undefined
;
; Side effects:
;   Configures PIA1 PA as input, PIA1 PB as output, PIA2 PA7-PA2 as DAC
;   output, and selects/enables the right joystick analog multiplexer.
;==============================================================================
init_joystick
        clr     PIA1_CRA        ; select PIA1 PA direction register
        clr     PIA1_DA         ; all PA bits input, including comparator PA7
        clr     PIA1_CRB        ; select PIA1 PB direction register
        lda     #$FF
        sta     PIA1_DB         ; keyboard columns/output side
        lda     #$34            ; data register, static CA2/CB2 output low
        sta     PIA1_CRA
        sta     PIA1_CRB        ; selector 0 = right joystick X

        clr     PIA2_CRA        ; select PIA2 PA direction register
        lda     #$FC
        sta     PIA2_DA         ; PA7-PA2 are the six-bit DAC
        lda     #$04            ; data-register access
        sta     PIA2_CRA
        clr     PIA2_CRB
        lda     #$34            ; static CB2 low enables analog multiplexer
        sta     PIA2_CRB
        lda     #$80            ; centre DAC while idle
        sta     PIA2_DA
        rts

;==============================================================================
; init_player — initialize the player at maze cell (12,18).
;
; Inputs:
;   None
;
; Returns:
;   A, D, CC — undefined
;
; Side effects:
;   Initializes direct-page player state.
;==============================================================================
init_player
        lda     #12
        sta     PLAYER_CELL_X
        lda     #18
        sta     PLAYER_CELL_Y
        clr     PLAYER_DIR      ; initially face and move north
        clr     PLAYER_FACE
        clr     PLAYER_STEP
        lda     #DIR_NONE
        sta     JOY_DIR
        sta     PLAYER_WANT
        ldd     #$75EC          ; FB + 137*160 + 152/2; opaque anchor is (-7,-7)
        std     PLAYER_FB
        rts

;==============================================================================
; read_joystick — sample right X/Y and resolve a four-way requested direction.
;
; Inputs:
;   None
;
; Returns:
;   A, B, CC — undefined
;
; Side effects:
;   Updates JOY_X, JOY_Y, JOY_DX, JOY_DY, and JOY_DIR.
;==============================================================================
read_joystick
        lda     #$34            ; static CA2 low: right X
        sta     PIA1_CRA
        lbsr    joy_read_axis
        stb     JOY_X
        lda     #$3C            ; static CA2 high: right Y
        sta     PIA1_CRA
        lbsr    joy_read_axis
        stb     JOY_Y
        lda     #$80
        sta     PIA2_DA

        lda     JOY_X
        suba    #32
        bpl     rj_x_abs
        nega
rj_x_abs
        sta     JOY_DX
        lda     JOY_Y
        suba    #32
        bpl     rj_y_abs
        nega
rj_y_abs
        sta     JOY_DY

        lda     #DIR_NONE
        sta     JOY_DIR
        lda     JOY_DX
        cmpa    JOY_DY
        blo     rj_vertical
        cmpa    #8              ; centred dead zone
        bls     rj_done
        lda     JOY_X
        cmpa    #32
        blo     rj_west
        lda     #DIR_EAST
        bra     rj_request
rj_west
        lda     #DIR_WEST
        bra     rj_request
rj_vertical
        lda     JOY_DY
        cmpa    #8
        bls     rj_done
        lda     JOY_Y
        cmpa    #32
        blo     rj_north
        lda     #DIR_SOUTH
        bra     rj_request
rj_north
        lda     #DIR_NORTH
rj_request
        sta     JOY_DIR
        sta     PLAYER_WANT      ; buffer turns across intermediate steps
rj_done
        rts

;==============================================================================
; joy_read_axis — convert the selected analog joystick axis through the DAC.
;
; Inputs:
;   PIA1 CA2/CB2 — selected analog source
;
; Returns:
;   B — position, 0..63
;   A, CC — undefined
;
; Side effects:
;   Sweeps the PIA2 DAC output.
;==============================================================================
joy_read_axis
        clrb
jra_loop
        stb     PIA2_DA
        lda     PIA1_DA
        bpl     jra_done        ; PA7 clear: DAC reached analog voltage
        addb    #4
        bcc     jra_loop
        ldb     #$FC
jra_done
        lsrb
        lsrb
        rts

;==============================================================================
; player_tick — restore, move, collect a dot, and redraw the player.
;
; Inputs:
;   Direct-page player and joystick state
;
; Returns:
;   A, B, D, X, Y, U, CC — undefined
;
; Side effects:
;   Updates player state, framebuffer, saved background, and MAZE_STATE.
;==============================================================================
player_tick
        lbsr    restore_player
        lda     PLAYER_STEP
        bne     pt_advance
        lda     PLAYER_WANT
        cmpa    #DIR_NONE
        beq     pt_check_active
        lbsr    can_move
        bcc     pt_check_active
        lda     PLAYER_WANT
        sta     PLAYER_DIR
        sta     PLAYER_FACE
pt_check_active
        lda     PLAYER_DIR
        cmpa    #DIR_NONE
        beq     pt_draw
        lbsr    can_move
        bcs     pt_advance
        lda     #DIR_NONE
        sta     PLAYER_DIR
        bra     pt_draw

pt_advance
        ldx     PLAYER_FB
        lda     PLAYER_DIR
        beq     pt_north
        cmpa    #DIR_EAST
        beq     pt_east
        cmpa    #DIR_SOUTH
        beq     pt_south
        leax    -1,x
        bra     pt_store_fb
pt_north
        leax    -320,x
        bra     pt_store_fb
pt_east
        leax    1,x
        bra     pt_store_fb
pt_south
        leax    320,x
pt_store_fb
        stx     PLAYER_FB
        inc     PLAYER_STEP
        lda     PLAYER_STEP
        cmpa    #4
        blo     pt_draw
        clr     PLAYER_STEP
        lda     PLAYER_DIR
        beq     pt_cell_north
        cmpa    #DIR_EAST
        beq     pt_cell_east
        cmpa    #DIR_SOUTH
        beq     pt_cell_south
        dec     PLAYER_CELL_X
        bra     pt_arrived
pt_cell_north
        dec     PLAYER_CELL_Y
        bra     pt_arrived
pt_cell_east
        inc     PLAYER_CELL_X
        bra     pt_arrived
pt_cell_south
        inc     PLAYER_CELL_Y
pt_arrived
        lbsr    eat_dot
pt_draw
        lbsr    draw_player
        rts

;==============================================================================
; player_cell_offset — return row*24+column for the current maze cell.
;
; Inputs:
;   PLAYER_CELL_X, PLAYER_CELL_Y
;
; Returns:
;   D — row-major maze offset, 0..575
;   CC — undefined
;==============================================================================
player_cell_offset
        lda     #24
        ldb     PLAYER_CELL_Y
        mul
        addb    PLAYER_CELL_X
        adca    #0
        rts

;==============================================================================
; can_move — test the current cell's navigation bit for a direction.
;
; Inputs:
;   A — direction, 0=N, 1=E, 2=S, 3=W
;
; Returns:
;   C — set if passable, clear if blocked
;   A, B, D, X, Y, CC — otherwise undefined
;==============================================================================
; Side effects: a legal endpoint push updates GATE_STATE and redraws the gate.
can_move
        sta     TEST_DIR
        lda     PLAYER_CELL_X
        sta     TEST_X
        lda     PLAYER_CELL_Y
        sta     TEST_Y
        ldb     TEST_DIR
        beq     cm_north
        cmpb    #DIR_EAST
        beq     cm_east
        cmpb    #DIR_SOUTH
        beq     cm_south
        dec     TEST_X
        bra     cm_bounds
cm_north
        dec     TEST_Y
        bra     cm_bounds
cm_east
        inc     TEST_X
        bra     cm_bounds
cm_south
        inc     TEST_Y
cm_bounds
        lda     TEST_X
        cmpa    #MAZE_WIDTH
        lbhs    cm_blocked
        lda     TEST_Y
        cmpa    #MAZE_HEIGHT
        lbhs    cm_blocked
        lbsr    test_cell_offset
        leax    maze_gate_owner,pcr
        lda     d,x
        lbeq    cm_regular
        deca
        sta     GATE_ID
        ldb     #3
        mul
        leax    maze_gates,pcr
        leax    d,x
        lda     ,x
        sta     GATE_X
        lda     1,x
        sta     GATE_Y
        ldx     #GATE_STATE
        ldb     GATE_ID
        lda     b,x

        ; Both corridors parallel to the current bar remain open.  The four
        ; states retain rotation direction, but collision depends on parity.
        bita    #1
        bne     cm_check_vertical_passages
        lda     TEST_X
        cmpa    GATE_X
        bne     cm_try_rotate
        lda     GATE_Y
        deca
        cmpa    TEST_Y
        lbeq    cm_pass_horizontal
        adda    #2
        cmpa    TEST_Y
        lbeq    cm_pass_horizontal
        bra     cm_try_rotate
cm_check_vertical_passages
        lda     TEST_Y
        cmpa    GATE_Y
        bne     cm_try_rotate
        lda     GATE_X
        deca
        cmpa    TEST_X
        lbeq    cm_pass_vertical
        adda    #2
        cmpa    TEST_X
        lbeq    cm_pass_vertical
        bra     cm_try_rotate

cm_pass_horizontal
        ldb     TEST_DIR
        cmpb    #DIR_EAST
        lbeq    cm_allowed
        cmpb    #DIR_WEST
        lbeq    cm_allowed
        bra     cm_try_rotate

cm_pass_vertical
        ldb     TEST_DIR
        cmpb    #DIR_NORTH
        lbeq    cm_allowed
        cmpb    #DIR_SOUTH
        lbeq    cm_allowed
        bra     cm_try_rotate

cm_try_rotate
        ; A horizontal bar rotates only when a vertical move pushes an end.
        ldx     #GATE_STATE
        ldb     GATE_ID
        lda     b,x
        bita    #1
        bne     cm_vertical_bar
        ldb     TEST_DIR
        cmpb    #DIR_NORTH
        beq     cm_h_endpoint
        cmpb    #DIR_SOUTH
        bne     cm_blocked
cm_h_endpoint
        lda     TEST_Y
        cmpa    GATE_Y
        bne     cm_blocked
        lda     TEST_X
        cmpa    GATE_X
        blo     cm_set_west
        bhi     cm_set_east
        bra     cm_blocked
cm_set_west
        lda     #1
        bra     cm_rotate
cm_set_east
        lda     #3
        bra     cm_rotate

        ; A vertical bar rotates only when a horizontal move pushes an end.
cm_vertical_bar
        ldb     TEST_DIR
        cmpb    #DIR_EAST
        beq     cm_v_endpoint
        cmpb    #DIR_WEST
        bne     cm_blocked
cm_v_endpoint
        lda     TEST_X
        cmpa    GATE_X
        bne     cm_blocked
        lda     TEST_Y
        cmpa    GATE_Y
        blo     cm_set_north
        bhi     cm_set_south
        bra     cm_blocked
cm_set_north
        clra
        bra     cm_rotate
cm_set_south
        lda     #2
cm_rotate
        ldx     #GATE_STATE
        ldb     GATE_ID
        sta     b,x
        lda     GATE_ID
        lbsr    draw_gate
        bra     cm_allowed

cm_regular
        lbsr    test_cell_offset
        leax    maze_nav,pcr
        ldb     d,x
        leax    cm_entry_masks,pcr
        lda     TEST_DIR
        andb    a,x             ; target must admit the reciprocal direction
        beq     cm_blocked
cm_allowed
        orcc    #$01
        rts
cm_blocked
        andcc   #$FE
        rts

cm_entry_masks
        fcb     $04,$08,$01,$02 ; requested N/E/S/W enters through S/W/N/E

;==============================================================================
; test_cell_offset
;
; Inputs: TEST_X, TEST_Y
; Returns: D = row-major maze offset; CC undefined
;==============================================================================
test_cell_offset
        lda     #24
        ldb     TEST_Y
        mul
        addb    TEST_X
        adca    #0
        rts

;==============================================================================
; draw_gate
;
; Inputs: A = gate ID, 0..19
; Returns: A, B, D, X, Y, U, CC undefined
; Side effects: restores contextual background, overlays this gate, then
;              re-overlays an intersecting neighbouring gate if present.
;==============================================================================
draw_gate
        sta     GATE_ID
        ldb     #3
        mul
        leax    maze_gates,pcr
        leax    d,x
        lda     ,x
        sta     GATE_X
        lda     1,x
        sta     GATE_Y

        lda     GATE_ID
        ldb     #7
        mul
        leau    gate_background_tiles,pcr
        leau    d,u
        leax    gate_cross_offsets,pcr
        lda     #7
        sta     DRAW_COUNT
dg_restore
        lda     GATE_X
        adda    ,x+
        sta     TEST_X
        lda     GATE_Y
        adda    ,x+
        sta     TEST_Y
        ldb     ,u+
        pshs    x,u
        lbsr    draw_cell_tile
        puls    x,u
        dec     DRAW_COUNT
        bne     dg_restore

        lda     GATE_ID
        lbsr    draw_gate_overlay
        leax    gate_redraw_neighbors,pcr
        ldb     GATE_ID
        lda     b,x
        beq     dg_done
        deca
        lbsr    draw_gate_overlay
dg_done
        rts

;==============================================================================
; draw_gate_overlay
;
; Inputs: A = gate ID, 0..19
; Returns: A, B, D, X, Y, U, CC undefined
; Side effects: transparently overlays five active gate-art tiles.
;==============================================================================
draw_gate_overlay
        sta     GATE_ID
        ldb     #3
        mul
        leax    maze_gates,pcr
        leax    d,x
        lda     ,x
        sta     GATE_X
        lda     1,x
        sta     GATE_Y

        ldx     #GATE_STATE
        ldb     GATE_ID
        lda     b,x
        ldb     #15
        mul
        leax    gate_state_tiles,pcr
        leax    d,x
        lda     #5
        sta     DRAW_COUNT
dg_tiles
        lda     GATE_X
        adda    ,x+
        sta     TEST_X
        lda     GATE_Y
        adda    ,x+
        sta     TEST_Y
        ldb     ,x+
        pshs    x
        lbsr    draw_cell_overlay
        puls    x
        dec     DRAW_COUNT
        bne     dg_tiles
        rts

gate_cross_offsets
        fcb     0,-2,0,-1,-2,0,-1,0,0,0,1,0,0,1

;==============================================================================
; draw_cell_tile
;
; Inputs: B = screen tile ID; TEST_X,TEST_Y = semantic maze cell
; Returns: A, B, D, X, Y, U, CC undefined
; Side effects: writes one 8x8 tile to the framebuffer.
;==============================================================================
draw_cell_tile
        stb     DRAW_TILE
        lda     TEST_Y
        ldb     #5
        mul
        tfr     b,a
        clrb
        addd    #FB_VIRT
        tfr     d,x
        lda     TEST_X
        adda    #8
        lsla
        lsla
        leax    a,x
        ldb     DRAW_TILE
        clra
        lslb
        rola
        lslb
        rola
        lslb
        rola
        lslb
        rola
        lslb
        rola
        leay    screen_tiles,pcr
        leay    d,y
        lbsr    blit_tile
        rts

;==============================================================================
; draw_cell_overlay
;
; Inputs: B = transparent gate tile ID; TEST_X,TEST_Y = semantic maze cell
; Returns: A, B, D, X, Y, U, CC undefined
; Side effects: blends one gate-only 8x8 tile into the framebuffer.
;==============================================================================
draw_cell_overlay
        stb     DRAW_TILE
        lda     TEST_Y
        ldb     #5
        mul
        tfr     b,a
        clrb
        addd    #FB_VIRT
        tfr     d,x
        lda     TEST_X
        adda    #8
        lsla
        lsla
        leax    a,x
        ldb     DRAW_TILE
        clra
        lslb
        rola
        lslb
        rola
        lslb
        rola
        lslb
        rola
        lslb
        rola
        leay    screen_tiles,pcr
        leay    d,y
        lbsr    blit_tile_transparent
        rts

;==============================================================================
; eat_dot — clear a newly entered dotted cell and redraw its clean tile.
;
; Inputs:
;   Current player cell and framebuffer pointer
;
; Returns:
;   A, B, D, X, Y, U, CC — undefined
;
; Side effects:
;   Clears bit 7 in MAZE_STATE and updates one framebuffer tile.
;==============================================================================
eat_dot
        lbsr    player_cell_offset
        ldx     #MAZE_STATE
        leax    d,x
        lda     ,x
        bpl     ed_done
        anda    #$7F
        sta     ,x
        ldx     PLAYER_FB
        leax    1124,x          ; cell tile is at row +7, byte +4 in save rect
        ldb     #MAZE_CLEAN_TILE
        clra
        lslb
        rola
        lslb
        rola
        lslb
        rola
        lslb
        rola
        lslb
        rola
        leay    screen_tiles,pcr
        leay    d,y
        lbsr    blit_tile
ed_done
        rts

;==============================================================================
; draw_player — save background and mask-blit the selected player frame.
;
; Inputs:
;   Player position, facing, and animation state
;
; Returns:
;   A, B, D, X, Y, U, CC — undefined
;
; Side effects:
;   Writes PLAYER_BG and the 16x16 framebuffer rectangle.
;==============================================================================
draw_player
        lbsr    save_player
        lda     PLAYER_FACE
        clrb                    ; D = frame index * 256
        leay    player_sprites,pcr
        leay    d,y
        leau    128,y           ; preserve-mask half of frame
        ldx     PLAYER_FB
        lbsr    blit_player_masked
        rts

;==============================================================================
; save_player — save the 16x16 framebuffer rectangle under the player.
;
; Inputs:
;   PLAYER_FB
;
; Returns:
;   D, X, Y, U, CC — undefined
;
; Side effects:
;   Writes 128 bytes at PLAYER_BG.
;==============================================================================
save_player
        ldx     PLAYER_FB
        ldu     #PLAYER_BG
        ldy     #16
sp_row
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
        bne     sp_row
        rts

;==============================================================================
; restore_player — restore the saved 16x16 player background.
;
; Inputs:
;   PLAYER_FB, PLAYER_BG
;
; Returns:
;   D, X, Y, U, CC — undefined
;
; Side effects:
;   Writes the prior 16x16 rectangle to the framebuffer.
;==============================================================================
restore_player
        ldx     PLAYER_FB
        ldu     #PLAYER_BG
        ldy     #16
rp_row
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
        bne     rp_row
        rts

;==============================================================================
; blit_player_masked — transparent 16x16 packed-nibble sprite blit.
;
; Inputs:
;   X — framebuffer destination
;   Y — 128 packed pixel bytes
;   U — 128 preserve-mask bytes ($F nibble preserves destination)
;
; Returns:
;   A, X, Y, U, CC — undefined
;
; Side effects:
;   Blends a 16x16 sprite into the framebuffer.
;==============================================================================
blit_player_masked
        lda     #16
        pshs    a
bpm_row
        lda     #8
        pshs    a
bpm_byte
        lda     ,x
        anda    ,u+
        ora     ,y+
        sta     ,x+
        dec     ,s
        bne     bpm_byte
        leas    1,s
        leax    152,x
        dec     ,s
        bne     bpm_row
        leas    1,s
        rts

;==============================================================================
; draw_screen — render the compiled 40x24 tile map.
;
; Inputs:
;   None
;
; Returns:
;   A, B, X, Y, U, D, CC — undefined
;
; Side effects:
;   Writes 960 8x8 tiles in row-major order to the framebuffer.
;==============================================================================
draw_screen
        leau    screen_map,pcr
        ldx     #FB_VIRT
        lda     #SCREEN_HEIGHT
ds_row
        pshs    a
        lda     #SCREEN_WIDTH
ds_column
        pshs    a,x
        ldb     ,u+
        clra
        lslb
        rola
        lslb
        rola
        lslb
        rola
        lslb
        rola
        lslb
        rola
        leay    screen_tiles,pcr
        leay    d,y
        lbsr    blit_tile
        puls    a,x
        leax    4,x
        deca
        bne     ds_column
        puls    a
        leax    1120,x
        deca
        bne     ds_row
        rts

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
        pshs    u
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
        puls    u,pc

;==============================================================================
; blit_tile_transparent — overlay nonzero packed nibbles from an 8x8 tile.
;
; Inputs:
;   X — destination framebuffer byte address
;   Y — source glyph data, 32 packed 4bpp bytes; colour 0 is transparent
;
; Returns: A, B, X, Y, CC undefined
; Side effects: blends 8 rows x 4 bytes into the framebuffer.
;==============================================================================
blit_tile_transparent
        lda     #8
        pshs    a
btt_row
        lda     #4
        pshs    a
btt_byte
        lda     ,y+
        clrb
        bita    #$F0
        bne     btt_high_opaque
        orb     #$F0
btt_high_opaque
        bita    #$0F
        bne     btt_low_opaque
        orb     #$0F
btt_low_opaque
        andb    ,x
        pshs    b
        ora     ,s+
        sta     ,x+
        dec     ,s
        bne     btt_byte
        leas    1,s
        leax    156,x
        dec     ,s
        bne     btt_row
        leas    1,s
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

;-- Build-generated palette, screen map, and packed tile atlas. --------------
;   scripts/build.sh compiles tiled/coco-screen.tmx with arcade character data
;   before invoking lwasm.
        include "ladybug_screen.inc"
        include "ladybug_maze.inc"

        end
