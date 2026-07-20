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
;   - Transparent 16x16 player frames with background save/restore.
;   - Semantic maze collision and dot removal.
;
; Visible: the authored screen with a moving, maze-constrained Lady Bug.
;==============================================================================

        pragma  nodollarlocal,6809

;------------------------------------------------------------------------------
; DP allocation (page $00)
;------------------------------------------------------------------------------
        setdp   $00

LAST_FRAME    equ $0000         ; last processed Vbord counter low byte
JOY_X         equ $0001         ; right joystick X, 0..63
FRAMES        equ $0002         ; u16 frame counter
JOY_Y         equ $0004         ; right joystick Y, 0..63
JOY_DIR       equ $0005         ; requested direction or $FF
PLAYER_DIR    equ $0006         ; active direction or $FF
PLAYER_FACE   equ $0007         ; last active direction, 0..3
PLAYER_STEP   equ $0008         ; 2-pixel steps since last cell centre, 0..3
PLAYER_CELL_X equ $0009         ; semantic maze column
PLAYER_CELL_Y equ $000A         ; semantic maze row
PLAYER_FB     equ $000B         ; u16 framebuffer pointer at sprite top-left
JOY_DX        equ $000D         ; absolute X displacement from centre
JOY_DY        equ $000E         ; absolute Y displacement from centre
PLAYER_WANT   equ $000F         ; last non-neutral requested direction
TEST_X        equ $0010         ; candidate/draw maze column
TEST_Y        equ $0011         ; candidate/draw maze row
TEST_DIR      equ $0012         ; direction under collision test
GATE_ID       equ $0013         ; active gate index
GATE_X        equ $0014         ; active gate pivot column
GATE_Y        equ $0015         ; active gate pivot row
DRAW_COUNT    equ $0016         ; gate redraw loop counter
DRAW_TILE     equ $0017         ; tile ID for draw_cell_tile
PLAYER_MANUAL equ $0018         ; nonzero after first directional input
GATE_ANIM_ID  equ $0019         ; rotating gate ID+1; zero when idle
GATE_ANIM_STYLE equ $001A       ; 0=slash, 1=backslash
BLIT_ROWS     equ $001B         ; transparent-blit row counter
BLIT_WIDTH    equ $001C         ; transparent-blit bytes per row
SCORE_BCD     equ $001D         ; packed BCD score, six digits
HIGH_BCD      equ $0020         ; packed BCD session high score
LIVES         equ $0023         ; lives remaining
STAGE         equ $0024         ; current stage, 1..255
DOTS_LEFT     equ $0025         ; remaining flowers in this stage
STAGE_PENDING equ $0026         ; nonzero requests a stage transition
HUD_X         equ $0027         ; HUD tile column scratch
HUD_Y         equ $0028         ; HUD tile row scratch
HUD_COLOR     equ $0029         ; palette index for digit rendering
HUD_BYTE      equ $002A         ; packed BCD / mask scratch
HUD_COUNT     equ $002B         ; byte/row loop scratch
HUD_WIDTH     equ $002C         ; packed-byte loop scratch
HUD_BCD_BYTE  equ $002D         ; preserved BCD byte during digit blits
HUD_BCD_COUNT equ $002E         ; packed BCD byte loop
BONUS_COLOR   equ $002F         ; global bonus colour, palette index
BONUS_TIMER   equ $0030         ; u16 frames remaining in current colour
ENTITY_COUNT  equ $0032         ; active entity-table record count
BONUS_LEFT    equ $0033         ; uncollected hearts and letters
RNG_STATE     equ $0034         ; u16 placement LFSR
ENTITY_X      equ $0036         ; entity/draw scratch
ENTITY_Y      equ $0037
ENTITY_TYPE   equ $0038
ENTITY_VARIANT equ $0039
DEATH_TIMER   equ $003A         ; nonzero while rotating death animation runs
MULTIPLIER    equ $003B         ; score multiplier: 1,2,3,5
SPECIAL_BITS equ $003C         ; collected SPECIAL letters, bit per HUD position
EXTRA_BITS   equ $003D         ; collected EXTRA letters, bit per HUD position
ENTITY_PTR   equ $003E         ; u16 current entity record pointer
OBJ_SOURCE   equ $0040         ; u16 object-mask source pointer
OBJ_ROWS     equ $0042
OBJ_BYTES    equ $0043
OBJ_VALUE    equ $0044
OBJ_INDEX    equ $0045
OBJ_PRIMARY  equ $0046
OBJ_ACCENT   equ $0047
ENTITY_WORK  equ $0048         ; entity placement / loop scratch
ENTITY_TOTAL equ $0049         ; total records allocated this stage
BOX_TIMER    equ $004A         ; frames until next perimeter-box update
BOX_INDEX    equ $004B         ; clockwise perimeter position, 0..91
BOX_PHASE    equ $004C         ; 0=White-to-Green, 1=Green-to-White
DEATH_STATE  equ $004D         ; 0=alive, 1=shrink, 2=wings, 3=walk-off
DEATH_FRAME  equ $004E         ; selected curated death frame
PLAYER_ANIM  equ $004F         ; walk animation phase 0,1,2,3
PLAYER_ANIM_TIMER equ $0050    ; Vbord countdown to next player frame
PICKUP_TIMER equ $0051         ; score-sprite hold; zero when inactive
PICKUP_FRAME equ $0052         ; 0=100, 1=300, 2=800
ANGEL_SWING  equ $0053         ; 20-frame eased angel-swoop phase
ENEMY_ANIM   equ $0054         ; first den enemy animation phase
ENEMY_TIMER  equ $0055         ; Vbord countdown to next enemy frame
TURN_SNAP    equ $0056         ; diagonal late-turn updates remaining, 0..3
TURN_OLD     equ $0057         ; direction being corrected during late turn
ENEMY_ACTIVE equ $0058         ; active enemy count, reduced by skull deaths
ENEMY_RELEASED equ $0059       ; total timer releases this stage
VEG_STATE    equ $005A         ; 0=dormant enemy, 1=vegetable, 2=collected
FREEZE_TIMER equ $005B         ; u16 enemy freeze countdown
ENEMY_WORK   equ $005D         ; banked enemy loop scratch
ENEMY_PTR    equ $005E         ; u16 banked enemy record pointer
ENEMY_DEATH_LATCH equ $0062    ; 0=alive, 1=reset pending, 2=reset published
PLAYER_OLD_FB equ $0067        ; framebuffer pointer owned by PLAYER_BG
PLAYER_ERASED equ $0069        ; nonzero after old player background is exposed
PLAYER_BG_VALID equ $006A      ; PLAYER_BG contains restorable pixels
PLAYER_TICK_PENDING equ $006B  ; nonzero when next Vbord must update/render player
BOOT_FLAG    equ $02F0         ; $A5 when GMC bootstrap relocated runtime to RAM

DIR_NORTH     equ 0
DIR_EAST      equ 1
DIR_SOUTH     equ 2
DIR_WEST      equ 3
DIR_NONE      equ $FF
PICKUP_HOLD_FRAMES equ 30      ; measured MAME frames 705-734 inclusive

COLOR_RED         equ 1
COLOR_YELLOW      equ 2
COLOR_LIGHT_GREEN equ 8
COLOR_BLUE        equ 3
COLOR_PINK        equ 4
COLOR_GREEN       equ 5
COLOR_WHITE       equ 6

ENTITY_NONE       equ 0
ENTITY_SKULL      equ 1
ENTITY_HEART      equ 2
ENTITY_LETTER     equ 3

OBJECT_SKULL      equ 0
OBJECT_HEART      equ 1
OBJECT_A          equ 2
OBJECT_C          equ 3
OBJECT_E          equ 4
OBJECT_I          equ 5
OBJECT_L          equ 6
OBJECT_P          equ 7
OBJECT_R          equ 8
OBJECT_S          equ 9
OBJECT_T          equ 10
OBJECT_X          equ 11

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
ENTITY_TABLE equ $A380          ; twelve x/y/type/variant records
PICKUP_BG   equ $A3B0          ; 64-byte background below score popup
PLAYER_STAGE equ $A3F0         ; 128-byte off-screen player composition surface
ENEMY_FB    equ $57EC          ; top-left at lower nest cell (12,12)
ENEMY_TABLE equ $A470          ; four 6-byte active enemy records
ENEMY_ZONE_BG equ $A490        ; 256-byte clean 16-by-32 nest background

ENEMY_MODULE_INIT    equ $0800
ENEMY_MODULE_TICK    equ $0803
ENEMY_MODULE_RELEASE equ $0806
ENEMY_MODULE_COLLECT equ $0809
PLAYER_MODULE_COMPOSE equ $080C

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

        clra                    ; DP = $00, shared with bank-3 runtime
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
        lda     BOOT_FLAG
        cmpa    #$A5
        beq     entry_ram_loaded
        sta     SAM_ROMRAM       ; plain-cart fallback selects TY=0
entry_ram_loaded

        ; --- Enter runtime from direct ROM or GMC-loaded RAM ---
        ; Direct fallback keeps TY=0. XRoar discards writes to the selected cartridge window,
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
        lbsr    init_game_state
        lbsr    init_maze_state
        lbsr    init_gate_state
        lbsr    init_joystick
        lbsr    read_joystick
        lda     RNG_STATE+1
        eora    JOY_X
        adda    JOY_Y
        sta     RNG_STATE+1
        lbsr    init_entities
        lbsr    init_player
        lbsr    draw_entities
        lbsr    draw_hud
        lbsr    draw_lives
        lbsr    init_enemy
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
        ; Keep every player restore/mutation/redraw at the front of Vbord.
        ; Logical movement remains 30 Hz, queued by the preceding even frame.
        lbsr    finish_gate_animation
        lbsr    pickup_tick
        lbsr    player_animation_tick
        ; Publish the shared nest first so the player remains the final owner
        ; when the two regions overlap at the vegetable/spawner cell.
        lbsr    enemy_tick
        lda     DEATH_STATE
        bne     main_after_player
        tst     PLAYER_TICK_PENDING
        beq     main_after_player
        clr     PLAYER_TICK_PENDING
        lbsr    player_tick
        lbsr    enemy_collect
main_after_player
        lbsr    read_joystick
        lda     DEATH_STATE
        bne     main_after_timers
        lbsr    bonus_color_tick
        lbsr    perimeter_timer_tick
main_after_timers
        lbsr    rng_next         ; stage placement depends on elapsed play time
        lda     DEATH_STATE
        beq     main_alive
main_death
        ; The perimeter release circuit is reset by the enemy death path and
        ; remains frozen until the replacement player has entered.
        lbsr    death_tick
        bra     mainloop
main_alive
        lda     PICKUP_TIMER
        bne     mainloop
        lda     LAST_FRAME
        anda    #$01
        bne     mainloop
phase4_before_tick
        lda     #1
        sta     PLAYER_TICK_PENDING
        lda     STAGE_PENDING
        beq     mainloop
        lbsr    next_stage
        bra     mainloop

;==============================================================================
; Phase 5 score, HUD, and no-enemy stage state.
;==============================================================================
init_game_state
        clr     SCORE_BCD
        clr     SCORE_BCD+1
        clr     SCORE_BCD+2
        clr     HIGH_BCD
        clr     HIGH_BCD+1
        clr     HIGH_BCD+2
        lda     #3
        sta     LIVES
        lda     #1
        sta     STAGE
        lda     #MAZE_DOT_COUNT
        sta     DOTS_LEFT
        clr     STAGE_PENDING
        clr     SPECIAL_BITS
        clr     EXTRA_BITS
        clr     DEATH_TIMER
        clr     DEATH_STATE
        clr     PLAYER_ANIM
        lda     #8
        sta     PLAYER_ANIM_TIMER
        clr     PLAYER_TICK_PENDING
        clr     PICKUP_TIMER
        clr     ANGEL_SWING
        clr     TURN_SNAP
        lda     #1
        sta     MULTIPLIER
        ldd     #$1D0F
        std     RNG_STATE
        lda     #COLOR_BLUE
        sta     BONUS_COLOR
        ldd     #420
        std     BONUS_TIMER
        lda     #9
        sta     BOX_TIMER
        clr     BOX_INDEX
        clr     BOX_PHASE
        rts

next_stage
        clr     STAGE_PENDING
        inc     STAGE
        bne     ns_stage_valid
        inc     STAGE
ns_stage_valid
        lda     #MAZE_DOT_COUNT
        sta     DOTS_LEFT
        lda     #1
        sta     MULTIPLIER
        lda     #9
        sta     BOX_TIMER
        clr     BOX_INDEX
        clr     BOX_PHASE
        lbsr    draw_screen
        lbsr    init_maze_state
        lbsr    init_gate_state
        lbsr    init_entities
        lbsr    init_player
        lbsr    draw_entities
        lbsr    draw_hud
        lbsr    draw_lives
        lbsr    init_enemy
        lbsr    draw_player
        rts

add_dot_score
        lda     MULTIPLIER
        sta     ENTITY_WORK
ads_ten_loop
        lda     SCORE_BCD+2
        adda    #$10            ; ten points
        daa
        sta     SCORE_BCD+2
        bcc     ads_ten_next
        lda     SCORE_BCD+1
        adca    #0
        daa
        sta     SCORE_BCD+1
        bcc     ads_ten_next
        lda     SCORE_BCD
        adca    #0
        daa
        sta     SCORE_BCD
ads_ten_next
        dec     ENTITY_WORK
        bne     ads_ten_loop
ads_copy_high
        ldd     SCORE_BCD
        std     HIGH_BCD
        lda     SCORE_BCD+2
        sta     HIGH_BCD+2
        lbsr    draw_hud
        rts

add_bonus_score
        lda     BONUS_COLOR
        cmpa    #COLOR_RED
        beq     abs_red
        cmpa    #COLOR_YELLOW
        beq     abs_yellow
        lda     #1
        bra     abs_multiply
abs_yellow
        lda     #3
        bra     abs_multiply
abs_red
        lda     #8
abs_multiply
        ldb     MULTIPLIER
        mul
        stb     ENTITY_WORK
abs_hundred
        lda     SCORE_BCD+1
        adda    #$01
        daa
        sta     SCORE_BCD+1
        bcc     abs_next
        lda     SCORE_BCD
        adca    #0
        daa
        sta     SCORE_BCD
abs_next
        dec     ENTITY_WORK
        bne     abs_hundred
        ldd     SCORE_BCD
        std     HIGH_BCD
        lda     SCORE_BCD+2
        sta     HIGH_BCD+2
        lbsr    draw_hud
        rts

apply_letter_pickup
        lda     BONUS_COLOR
        cmpa    #COLOR_RED
        beq     alp_special
        cmpa    #COLOR_YELLOW
        beq     alp_extra
        rts
alp_special
        lda     ENTITY_VARIANT
        leax    special_letter_bits,pcr
        ldb     a,x
        beq     alp_done
        orb     SPECIAL_BITS
        stb     SPECIAL_BITS
        cmpb    #$7F
        bne     alp_special_draw
        clr     SPECIAL_BITS
        lbsr    add_special_score
        inc     STAGE_PENDING
alp_special_draw
        lda     ENTITY_VARIANT
        leax    special_letter_x,pcr
        ldb     a,x
        stb     HUD_X
        lda     #1
        sta     HUD_Y
        lda     #COLOR_RED
        sta     HUD_COLOR
        lbsr    draw_recolored_map_tile
        rts
alp_extra
        lda     ENTITY_VARIANT
        leax    extra_letter_bits,pcr
        ldb     a,x
        beq     alp_done
        orb     EXTRA_BITS
        stb     EXTRA_BITS
        cmpb    #$1F
        bne     alp_extra_draw
        clr     EXTRA_BITS
        inc     LIVES
        inc     STAGE_PENDING
alp_extra_draw
        lda     ENTITY_VARIANT
        leax    extra_letter_x,pcr
        ldb     a,x
        stb     HUD_X
        lda     #4
        sta     HUD_Y
        lda     #COLOR_YELLOW
        sta     HUD_COLOR
        lbsr    draw_recolored_map_tile
alp_done
        rts

add_special_score
        lda     SCORE_BCD
        adda    #$01            ; CoCo SPECIAL adaptation: 10,000 points
        daa
        sta     SCORE_BCD
        ldd     SCORE_BCD
        std     HIGH_BCD
        lda     SCORE_BCD+2
        sta     HIGH_BCD+2
        lbsr    draw_hud
        rts

draw_multiplier_hud
        lda     MULTIPLIER
        cmpa    #2
        beq     dmh_two
        cmpa    #3
        beq     dmh_three
        lda     #5
        bra     dmh_draw
dmh_two
        lda     #1
        bra     dmh_draw
dmh_three
        lda     #3
dmh_draw
        sta     HUD_X
        lda     #7
        sta     HUD_Y
        lda     #COLOR_BLUE
        sta     HUD_COLOR
        lbsr    draw_recolored_map_tile
        inc     HUD_X
        lbsr    draw_recolored_map_tile
        rts

; Indexed by object-mask number 0..11.
special_letter_bits
        fcb     0,0,$20,$08,$04,$10,$40,$02,0,$01,0,0
special_letter_x
        fcb     0,0,6,4,3,5,7,2,0,1,0,0
extra_letter_bits
        fcb     0,0,$10,0,$01,0,0,0,$08,0,$04,$02
extra_letter_x
        fcb     0,0,5,0,1,0,0,0,4,0,3,2

check_stage_clear
        lda     DOTS_LEFT
        bne     csc_done
        lda     BONUS_LEFT
        bne     csc_done
        inc     STAGE_PENDING
csc_done
        rts

draw_hud
        lda     #2
        sta     HUD_Y
        lda     #COLOR_LIGHT_GREEN
        sta     HUD_COLOR
        ldu     #SCORE_BCD
        lbsr    draw_bcd_line
        lda     #5
        sta     HUD_Y
        lda     #COLOR_RED
        sta     HUD_COLOR
        ldu     #HIGH_BCD
        lbsr    draw_bcd_line
        lda     #38
        sta     HUD_X
        lda     #10
        sta     HUD_Y
        lda     #COLOR_BLUE
        sta     HUD_COLOR
        lda     STAGE
dhu_mod10
        cmpa    #10
        blo     dhu_stage_digit
        suba    #10
        bra     dhu_mod10
dhu_stage_digit
        lbsr    draw_hud_digit
        lbsr    draw_vegetable_hud
        rts

; Display the stage vegetable at HUD columns 32-33, rows 11-12, followed by
; its four-digit 1000..9500 value at columns 35-38 on row 12.
draw_vegetable_hud
        lda     STAGE
        cmpa    #18
        bls     dvh_stage_ok
        lda     #18
dvh_stage_ok
        deca
        sta     ENTITY_WORK
        ldb     #PACKED_SPRITE_SIZE
        mul
        leay    vegetable_sprites,pcr
        leay    d,y
        ldx     #$5780          ; screen column 32, scanline 88
        leau    sprite_attr0_pairs,pcr
        lbsr    blit_packed_sprite

        lda     ENTITY_WORK
        lsla
        leau    vegetable_values,pcr
        leau    a,u
        lda     #35
        sta     HUD_X
        lda     #12
        sta     HUD_Y
        lda     #COLOR_GREEN
        sta     HUD_COLOR
        lda     ,u+
        sta     HUD_BCD_BYTE
        lsra
        lsra
        lsra
        lsra
        lbsr    draw_hud_digit
        inc     HUD_X
        lda     HUD_BCD_BYTE
        anda    #$0F
        lbsr    draw_hud_digit
        inc     HUD_X
        lda     ,u
        sta     HUD_BCD_BYTE
        lsra
        lsra
        lsra
        lsra
        lbsr    draw_hud_digit
        inc     HUD_X
        lda     HUD_BCD_BYTE
        anda    #$0F
        lbsr    draw_hud_digit
        rts

vegetable_values
        fdb     $1000,$1500,$2000,$2500,$3000,$3500
        fdb     $4000,$4500,$5000,$5500,$6000,$6500
        fdb     $7000,$7500,$8000,$8500,$9000,$9500

draw_bcd_line
        lda     #33
        sta     HUD_X
        lda     #3
        sta     HUD_BCD_COUNT
dbl_byte
        lda     ,u+
        sta     HUD_BCD_BYTE
        lsra
        lsra
        lsra
        lsra
        lbsr    draw_hud_digit
        inc     HUD_X
        lda     HUD_BCD_BYTE
        anda    #$0F
        lbsr    draw_hud_digit
        inc     HUD_X
        dec     HUD_BCD_COUNT
        bne     dbl_byte
        rts

; A=digit 0..9. HUD_X/HUD_Y/HUD_COLOR select destination and colour.
draw_hud_digit
        ldb     #HUD_DIGIT_SIZE
        mul
        leay    hud_digit_tiles,pcr
        leay    d,y
        lda     HUD_Y
        ldb     #5
        mul
        tfr     b,a
        clrb
        addd    #FB_VIRT
        tfr     d,x
        clra
        ldb     HUD_X
        lslb
        rola
        lslb
        rola
        leax    d,x             ; HUD columns exceed signed 8-bit A offsets
        lda     #8
        sta     HUD_COUNT
dhd_row
        lda     #4
        sta     HUD_WIDTH
dhd_byte
        lda     ,y+
        sta     HUD_BYTE
        clra
        ldb     HUD_BYTE
        bitb    #$F0
        beq     dhd_low
        lda     HUD_COLOR
        lsla
        lsla
        lsla
        lsla
dhd_low
        bitb    #$0F
        beq     dhd_store
        ora     HUD_COLOR
dhd_store
        sta     ,x+
        dec     HUD_WIDTH
        bne     dhd_byte
        leax    156,x
        dec     HUD_COUNT
        bne     dhd_row
        rts

; Recolour the authored non-Black pixels at HUD_X,HUD_Y with HUD_COLOR.
draw_recolored_map_tile
        lda     HUD_Y
        ldb     #40
        mul
        addb    HUD_X
        adca    #0
        leay    screen_map,pcr
        ldb     d,y
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
        lda     HUD_Y
        ldb     #5
        mul
        tfr     b,a
        clrb
        addd    #FB_VIRT
        tfr     d,x
        clra
        ldb     HUD_X
        lslb
        rola
        lslb
        rola
        leax    d,x
        lda     #8
        sta     HUD_COUNT
drmt_row
        lda     #4
        sta     HUD_WIDTH
drmt_byte
        lda     ,y+
        sta     HUD_BYTE
        clra
        ldb     HUD_BYTE
        bitb    #$F0
        beq     drmt_low
        lda     HUD_COLOR
        lsla
        lsla
        lsla
        lsla
drmt_low
        bitb    #$0F
        beq     drmt_store
        ora     HUD_COLOR
drmt_store
        sta     ,x+
        dec     HUD_WIDTH
        bne     drmt_byte
        leax    156,x
        dec     HUD_COUNT
        bne     drmt_row
        rts

draw_lives
        clr     ENTITY_WORK
dl_marker
        lda     ENTITY_WORK
        lsla
        adda    #33
        sta     HUD_X
        lda     #21
        sta     HUD_Y
        lda     ENTITY_WORK
        cmpa    LIVES
        bhs     dl_erase
        lbsr    draw_life_marker
        bra     dl_next
dl_erase
        lbsr    clear_life_marker
dl_next
        inc     ENTITY_WORK
        lda     ENTITY_WORK
        cmpa    #3
        blo     dl_marker
        rts

clear_life_marker
        lda     HUD_Y
        ldb     #5
        mul
        tfr     b,a
        clrb
        addd    #FB_VIRT
        tfr     d,x
        clra
        ldb     HUD_X
        lslb
        rola
        lslb
        rola
        leax    d,x
        lda     #16
        sta     HUD_COUNT
clm_row
        ldd     #0
        std     ,x++
        std     ,x++
        std     ,x++
        std     ,x++
        leax    152,x
        dec     HUD_COUNT
        bne     clm_row
        rts

draw_life_marker
        lbsr    draw_authored_hud_tile
        inc     HUD_X
        lbsr    draw_authored_hud_tile
        dec     HUD_X
        inc     HUD_Y
        lbsr    draw_authored_hud_tile
        inc     HUD_X
        lbsr    draw_authored_hud_tile
        rts

draw_authored_hud_tile
        lda     HUD_Y
        ldb     #40
        mul
        addb    HUD_X
        adca    #0
        leay    screen_map,pcr
        ldb     d,y
draw_hud_tile
        stb     DRAW_TILE
        lda     HUD_Y
        ldb     #5
        mul
        tfr     b,a
        clrb
        addd    #FB_VIRT
        tfr     d,x
        clra
        ldb     HUD_X
        lslb
        rola
        lslb
        rola
        leax    d,x
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
; Randomized stage objects. Each four-byte record is x,y,type,mask index.
;==============================================================================
init_entities
        clr     ENTITY_TOTAL
        lda     #6
        sta     BONUS_LEFT
        lda     STAGE
        cmpa    #2
        blo     ie_two_skulls
        cmpa    #5
        blo     ie_three_skulls
        cmpa    #9
        blo     ie_four_skulls
        cmpa    #18
        blo     ie_five_skulls
        lda     #6
        bra     ie_place_skulls
ie_two_skulls
        lda     #2
        bra     ie_place_skulls
ie_three_skulls
        lda     #3
        bra     ie_place_skulls
ie_four_skulls
        lda     #4
        bra     ie_place_skulls
ie_five_skulls
        lda     #5
ie_place_skulls
        sta     ENTITY_WORK
ie_skull_loop
        lda     #ENTITY_SKULL
        ldb     #OBJECT_SKULL
        lbsr    place_entity
        dec     ENTITY_WORK
        bne     ie_skull_loop

        lda     #3
        sta     ENTITY_WORK
ie_heart_loop
        lda     #ENTITY_HEART
        ldb     #OBJECT_HEART
        lbsr    place_entity
        dec     ENTITY_WORK
        bne     ie_heart_loop

        ; One letter from X/T/R.
        lbsr    rng_next
ie_xtr_mod
        cmpb    #3
        blo     ie_xtr_pick
        subb    #3
        bra     ie_xtr_mod
ie_xtr_pick
        leax    letter_xtr,pcr
        ldb     b,x
        lda     #ENTITY_LETTER
        lbsr    place_entity

        ; One letter from S/P/C/I/L.
        lbsr    rng_next
ie_spcil_mod
        cmpb    #5
        blo     ie_spcil_pick
        subb    #5
        bra     ie_spcil_mod
ie_spcil_pick
        leax    letter_spcil,pcr
        ldb     b,x
        lda     #ENTITY_LETTER
        lbsr    place_entity

        ; One letter from E/A.
        lbsr    rng_next
        andb    #1
        leax    letter_ea,pcr
        ldb     b,x
        lda     #ENTITY_LETTER
        lbsr    place_entity
        lda     ENTITY_TOTAL
        sta     ENTITY_COUNT
        lbsr    erase_entity_footprints
        rts

letter_xtr
        fcb     OBJECT_X,OBJECT_T,OBJECT_R
letter_spcil
        fcb     OBJECT_S,OBJECT_P,OBJECT_C,OBJECT_I,OBJECT_L
letter_ea
        fcb     OBJECT_E,OBJECT_A

; A=entity type, B=object-mask index.
place_entity
        sta     ENTITY_TYPE
        stb     ENTITY_VARIANT
pe_retry
        lbsr    rng_next
pe_reduce
        cmpd    #576
        blo     pe_candidate
        subd    #576
        bra     pe_reduce
pe_candidate
        tfr     d,y
        ldx     #MAZE_STATE
        leax    d,x
        lda     ,x
        bpl     pe_retry
        anda    #$7F
        sta     ,x
        dec     DOTS_LEFT

        clra
        clr     ENTITY_Y
        tfr     y,d
pe_row
        cmpd    #24
        blo     pe_coordinates
        subd    #24
        inc     ENTITY_Y
        bra     pe_row
pe_coordinates
        stb     ENTITY_X
        lda     ENTITY_TOTAL
        ldb     #4
        mul
        ldx     #ENTITY_TABLE
        leax    d,x
        lda     ENTITY_X
        sta     ,x+
        lda     ENTITY_Y
        sta     ,x+
        lda     ENTITY_TYPE
        sta     ,x+
        lda     ENTITY_VARIANT
        sta     ,x
        inc     ENTITY_TOTAL
        rts

rng_next
        ldd     RNG_STATE
        lsra
        rorb
        bcc     rn_store
        eora    #$B4
rn_store
        std     RNG_STATE
        rts

;==============================================================================
; Dynamic object drawing and the MAME-measured global colour cycle.
;==============================================================================
draw_entities
        ldx     #ENTITY_TABLE
        lda     ENTITY_COUNT
        sta     ENTITY_WORK
de_loop
        stx     ENTITY_PTR
        lda     2,x
        beq     de_next
        lda     ,x
        sta     ENTITY_X
        lda     1,x
        sta     ENTITY_Y
        lda     2,x
        sta     ENTITY_TYPE
        lda     3,x
        sta     ENTITY_VARIANT
        lbsr    draw_entity_object
de_next
        ldx     ENTITY_PTR
        leax    4,x
        dec     ENTITY_WORK
        bne     de_loop
        rts

; Placement changes MAZE_STATE before the objects are drawn. Restore each
; 16x16 footprint once so the authored flowers do not show through sprites.
erase_entity_footprints
        ldx     #ENTITY_TABLE
        lda     ENTITY_COUNT
        sta     ENTITY_WORK
eef_loop
        stx     ENTITY_PTR
        lda     ,x
        sta     ENTITY_X
        lda     1,x
        sta     ENTITY_Y
        lbsr    restore_entity_footprint
        ldx     ENTITY_PTR
        leax    4,x
        dec     ENTITY_WORK
        bne     eef_loop
        rts

draw_entity_object
        lda     ENTITY_VARIANT
        ldb     #OBJECT_MASK_SIZE
        mul
        leay    object_masks,pcr
        leay    d,y
        sty     OBJ_SOURCE

        lda     ENTITY_TYPE
        cmpa    #ENTITY_SKULL
        bne     deo_bonus
        lda     #COLOR_YELLOW
        sta     OBJ_PRIMARY
        lda     #COLOR_WHITE
        sta     OBJ_ACCENT
        leau    object_skull_lut,pcr
        bra     deo_destination
deo_bonus
        lda     BONUS_COLOR
        sta     OBJ_PRIMARY
        lda     #COLOR_PINK
        sta     OBJ_ACCENT
        lda     OBJ_PRIMARY
        cmpa    #COLOR_RED
        beq     deo_red
        cmpa    #COLOR_YELLOW
        beq     deo_yellow
        leau    object_blue_lut,pcr
        bra     deo_destination
deo_red
        leau    object_red_lut,pcr
        bra     deo_destination
deo_yellow
        leau    object_yellow_lut,pcr
deo_destination
        lda     ENTITY_Y
        deca
        ldb     #5
        mul
        tfr     b,a
        clrb
        addd    #FB_VIRT
        tfr     d,x
        lda     ENTITY_X
        adda    #7
        lsla
        lsla
        leax    a,x
        lda     #16
        sta     OBJ_ROWS
deo_row
        lda     #4
        sta     OBJ_BYTES
deo_byte
        ldy     OBJ_SOURCE
        lda     ,y+
        sty     OBJ_SOURCE
        sta     OBJ_VALUE
        lsra
        lsra
        lsra
        lsra
        sta     OBJ_INDEX
        leay    object_mask_lut,pcr
        ldb     a,y
        andb    ,x
        orb     a,u
        stb     ,x+
        lda     OBJ_VALUE
        anda    #$0F
        sta     OBJ_INDEX
        ldb     a,y
        andb    ,x
        orb     a,u
        stb     ,x+
        dec     OBJ_BYTES
        bne     deo_byte
        leax    152,x
        dec     OBJ_ROWS
        bne     deo_row
        rts

bonus_color_tick
        lda     LIVES
        beq     bct_done
        ldd     BONUS_TIMER
        subd    #1
        std     BONUS_TIMER
        bne     bct_done
        lda     BONUS_COLOR
        cmpa    #COLOR_BLUE
        beq     bct_to_red
        cmpa    #COLOR_RED
        beq     bct_to_yellow
        lda     #COLOR_BLUE
        sta     BONUS_COLOR
        ldd     #420
        bra     bct_redraw
bct_to_red
        lda     #COLOR_RED
        sta     BONUS_COLOR
        ldd     #30
        bra     bct_redraw
bct_to_yellow
        lda     #COLOR_YELLOW
        sta     BONUS_COLOR
        ldd     #150
bct_redraw
        std     BONUS_TIMER
        lda     PICKUP_TIMER
        bne     bct_popup
        lbsr    restore_player
        lbsr    draw_entities
        lbsr    draw_player
        bra     bct_done
bct_popup
        lbsr    draw_entities
bct_done
        rts

; Advance the 92-box release circuit every nine video frames.  Enemies are
; intentionally absent in Phase 5; the arcade timer remains visible.
perimeter_timer_tick
        dec     BOX_TIMER
        bne     ptt_done
        lda     #9
        sta     BOX_TIMER
        lbsr    perimeter_box_coordinates
        lda     BOX_PHASE
        beq     ptt_green
        lda     #COLOR_WHITE
        bra     ptt_draw
ptt_green
        lda     #5              ; COLOR_GREEN
ptt_draw
        sta     HUD_COLOR
        lbsr    draw_perimeter_box
        inc     BOX_INDEX
        lda     BOX_INDEX
        cmpa    #92
        blo     ptt_done
        clr     BOX_INDEX
        lda     BOX_PHASE
        eora    #1
        sta     BOX_PHASE
        lbsr    enemy_release
ptt_done
        rts

; Publish the reset timer state immediately. State reset alone leaves the old
; Green progress visible until the new circuit eventually reaches each tile.
reset_perimeter_visual
        clr     BOX_INDEX
        lda     #COLOR_WHITE
        sta     HUD_COLOR
rpv_box
        lbsr    perimeter_box_coordinates
        lbsr    draw_perimeter_box
        inc     BOX_INDEX
        lda     BOX_INDEX
        cmpa    #92
        blo     rpv_box
        clr     BOX_INDEX
        rts

; Index 0 is the thirteenth top box from the left.  Continue clockwise.
perimeter_box_coordinates
        lda     BOX_INDEX
        cmpa    #12
        bhs     pbc_right
        adda    #12
        sta     TEST_X
        clr     TEST_Y
        rts
pbc_right
        suba    #12
        cmpa    #23
        bhs     pbc_bottom
        sta     TEST_Y
        inc     TEST_Y
        lda     #23
        sta     TEST_X
        rts
pbc_bottom
        suba    #23
        cmpa    #23
        bhs     pbc_left
        nega
        adda    #22
        sta     TEST_X
        lda     #23
        sta     TEST_Y
        rts
pbc_left
        suba    #23
        cmpa    #22
        bhs     pbc_top_left
        nega
        adda    #22
        sta     TEST_Y
        clr     TEST_X
        rts
pbc_top_left
        suba    #22
        sta     TEST_X
        clr     TEST_Y
        rts

; Redraw an authored perimeter tile, replacing White pixels only.  Pink inner
; borders and Black separators remain unchanged.
draw_perimeter_box
        lda     TEST_Y
        ldb     #40
        mul
        addb    TEST_X
        adca    #0
        addd    #8
        leay    screen_map,pcr
        ldb     d,y
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
        lda     #8
        sta     HUD_COUNT
dpb_row
        lda     #4
        sta     HUD_WIDTH
dpb_byte
        lda     ,y+
        sta     HUD_BYTE
        anda    #$F0
        cmpa    #$60
        bne     dpb_low
        lda     HUD_COLOR
        lsla
        lsla
        lsla
        lsla
        sta     OBJ_VALUE
        lda     HUD_BYTE
        anda    #$0F
        ora     OBJ_VALUE
        sta     HUD_BYTE
dpb_low
        lda     HUD_BYTE
        anda    #$0F
        cmpa    #COLOR_WHITE
        bne     dpb_store
        lda     HUD_BYTE
        anda    #$F0
        ora     HUD_COLOR
        sta     HUD_BYTE
dpb_store
        lda     HUD_BYTE
        sta     ,x+
        dec     HUD_WIDTH
        bne     dpb_byte
        leax    156,x
        dec     HUD_COUNT
        bne     dpb_row
        rts

object_mask_lut
        fcb     $FF,$F0,$F0,$F0,$0F,$00,$00,$00
        fcb     $0F,$00,$00,$00,$0F,$00,$00,$00
object_red_lut
        fcb     $00,$00,$01,$04,$00,$00,$01,$04
        fcb     $10,$10,$11,$14,$40,$40,$41,$44
object_yellow_lut
        fcb     $00,$00,$02,$04,$00,$00,$02,$04
        fcb     $20,$20,$22,$24,$40,$40,$42,$44
object_blue_lut
        fcb     $00,$00,$03,$04,$00,$00,$03,$04
        fcb     $30,$30,$33,$34,$40,$40,$43,$44
object_skull_lut
        fcb     $00,$00,$06,$06,$00,$00,$06,$06
        fcb     $60,$60,$66,$66,$60,$60,$66,$66

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
        lda     #22
        sta     PLAYER_CELL_Y
        clr     PLAYER_DIR      ; initially face and move north
        clr     PLAYER_FACE
        clr     PLAYER_STEP
        clr     TURN_SNAP
        lda     #DIR_NONE
        sta     JOY_DIR
        sta     PLAYER_WANT
        clr     PLAYER_MANUAL
        clr     GATE_ANIM_ID
        ldd     #$89EC          ; final anchor $75EC plus 32 entrance pixels
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
        sta     PLAYER_FACE      ; facing follows live input even when blocked
        lda     #1
        sta     PLAYER_MANUAL
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
        ldd     PLAYER_FB
        std     PLAYER_OLD_FB
        clr     PLAYER_ERASED
pt_alive
        lda     PLAYER_MANUAL
        beq     pt_input_active  ; preserve automatic entrance movement
        lda     JOY_DIR
        cmpa    #DIR_NONE
        lbeq    pt_draw          ; neutral stops immediately without losing buffered turn
pt_input_active
        lda     TURN_SNAP
        lbne    pt_snap_advance
        lda     PLAYER_STEP
        lbeq    pt_at_center
        lda     PLAYER_MANUAL
        lbeq    pt_advance       ; preserve the automatic entrance movement
        lda     PLAYER_WANT      ; arcade request persists through neutral input
        cmpa    PLAYER_DIR
        lbeq    pt_advance
        eora    #2              ; opposite directions differ by bit 1
        cmpa    PLAYER_DIR
        bne     pt_try_late_turn
        lda     PLAYER_WANT
        sta     PLAYER_FACE
        lda     #4
        suba    PLAYER_STEP
        sta     PLAYER_STEP
        lda     PLAYER_DIR      ; rebase against the old direction's target
        beq     pt_rebase_north
        cmpa    #DIR_EAST
        beq     pt_rebase_east
        cmpa    #DIR_SOUTH
        beq     pt_rebase_south
        dec     PLAYER_CELL_X
        bra     pt_reversed
pt_rebase_north
        dec     PLAYER_CELL_Y
        bra     pt_reversed
pt_rebase_east
        inc     PLAYER_CELL_X
        bra     pt_reversed
pt_rebase_south
        inc     PLAYER_CELL_Y
pt_reversed
        lda     PLAYER_WANT
        sta     PLAYER_DIR
        lbra    pt_advance
pt_try_late_turn
        lda     PLAYER_WANT
        lbsr    can_move         ; test from the last aligned cell; may turn gate
        bcs     pt_begin_late_turn
        lda     PLAYER_STEP
        cmpa    #3              ; next junction is 2 pixels past sprite midpoint
        lbne    pt_advance       ; retain request while approaching its junction
        lda     PLAYER_DIR      ; probe requested passage from the upcoming cell
        beq     pt_probe_north
        cmpa    #DIR_EAST
        beq     pt_probe_east
        cmpa    #DIR_SOUTH
        beq     pt_probe_south
        dec     PLAYER_CELL_X
        bra     pt_probe_turn
pt_probe_north
        dec     PLAYER_CELL_Y
        bra     pt_probe_turn
pt_probe_east
        inc     PLAYER_CELL_X
        bra     pt_probe_turn
pt_probe_south
        inc     PLAYER_CELL_Y
pt_probe_turn
        lda     PLAYER_WANT
        lbsr    can_move         ; legal gate push occurs at the approached junction
        lda     PLAYER_DIR      ; restore last aligned cell before normal arrival
        beq     pt_unprobe_north
        cmpa    #DIR_EAST
        beq     pt_unprobe_east
        cmpa    #DIR_SOUTH
        beq     pt_unprobe_south
        inc     PLAYER_CELL_X
        bra     pt_unprobe_done
pt_unprobe_north
        inc     PLAYER_CELL_Y
        bra     pt_unprobe_done
pt_unprobe_east
        dec     PLAYER_CELL_X
        bra     pt_unprobe_done
pt_unprobe_south
        dec     PLAYER_CELL_Y
pt_unprobe_done
        lbra    pt_advance       ; arrive at centre, then retry buffered request
pt_begin_late_turn
        lda     PLAYER_DIR
        sta     TURN_OLD
        lda     PLAYER_STEP
        sta     TURN_SNAP
        clr     PLAYER_STEP
        lda     PLAYER_WANT
        sta     PLAYER_DIR
        sta     PLAYER_FACE
        lbra    pt_draw          ; arcade shows the new face before diagonal snap
pt_at_center
        lda     PLAYER_MANUAL
        bne     pt_choose_direction
        lda     PLAYER_CELL_X
        cmpa    #12
        bne     pt_choose_direction
        lda     PLAYER_CELL_Y
        cmpa    #18
        bne     pt_choose_direction
        lda     #DIR_NONE
        sta     PLAYER_DIR
        sta     PLAYER_WANT
        lbra    pt_draw
pt_choose_direction
        lda     PLAYER_WANT
        cmpa    #DIR_NONE
        beq     pt_check_active
        lbsr    can_move
        bcc     pt_blocked_request
        lda     PLAYER_WANT
        sta     PLAYER_DIR
        sta     PLAYER_FACE
        bra     pt_check_active
pt_blocked_request
        lda     #DIR_NONE
        sta     PLAYER_DIR
        lbra    pt_draw
pt_check_active
        lda     PLAYER_DIR
        cmpa    #DIR_NONE
        lbeq    pt_draw
        lbsr    can_move
        bcs     pt_advance
        lda     #DIR_NONE
        sta     PLAYER_DIR
        lbra    pt_draw

pt_snap_advance
        ldx     PLAYER_FB
        lda     TURN_OLD
        beq     pt_snap_from_north
        cmpa    #DIR_EAST
        beq     pt_snap_from_east
        cmpa    #DIR_SOUTH
        beq     pt_snap_from_south
        leax    1,x              ; reverse old West movement
        bra     pt_snap_new_axis
pt_snap_from_north
        leax    320,x
        bra     pt_snap_new_axis
pt_snap_from_east
        leax    -1,x
        bra     pt_snap_new_axis
pt_snap_from_south
        leax    -320,x
pt_snap_new_axis
        lda     PLAYER_DIR
        beq     pt_snap_north
        cmpa    #DIR_EAST
        beq     pt_snap_east
        cmpa    #DIR_SOUTH
        beq     pt_snap_south
        leax    -1,x
        bra     pt_snap_store
pt_snap_north
        leax    -320,x
        bra     pt_snap_store
pt_snap_east
        leax    1,x
        bra     pt_snap_store
pt_snap_south
        leax    320,x
pt_snap_store
        stx     PLAYER_FB
        inc     PLAYER_STEP
        dec     TURN_SNAP
        lbra    pt_draw

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
        lbsr    check_entity_pickup
        lda     DEATH_STATE
        bne     pt_draw
        lbsr    eat_dot
pt_draw
        lda     DEATH_STATE
        bne     pt_done
        lda     PICKUP_TIMER
        bne     pt_done
        tst     PLAYER_ERASED
        bne     pt_draw_direct
        jsr     PLAYER_MODULE_COMPOSE
        bra     pt_done
pt_draw_direct
        lbsr    draw_player
pt_done
        rts

; Restore the old player rectangle only when another renderer must mutate the
; maze beneath it during this tick. Ordinary movement remains off-screen.
expose_player_background
        tst     PLAYER_ERASED
        bne     epb_done
        inc     PLAYER_ERASED
        ldd     PLAYER_FB
        pshs    d
        ldd     PLAYER_OLD_FB
        std     PLAYER_FB
        lbsr    restore_player
        puls    d
        std     PLAYER_FB
epb_done
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
        lbne    cm_blocked
cm_h_endpoint
        lda     TEST_Y
        cmpa    GATE_Y
        lbne    cm_blocked
        lda     TEST_X
        cmpa    GATE_X
        blo     cm_set_west
        bhi     cm_set_east
        bra     cm_blocked
cm_set_west
        clr     GATE_ANIM_STYLE
        ldb     TEST_DIR
        cmpb    #DIR_NORTH
        bne     cm_west_style_done
        inc     GATE_ANIM_STYLE
cm_west_style_done
        lda     #1
        bra     cm_rotate
cm_set_east
        clr     GATE_ANIM_STYLE
        ldb     TEST_DIR
        cmpb    #DIR_SOUTH
        bne     cm_east_style_done
        inc     GATE_ANIM_STYLE
cm_east_style_done
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
        clr     GATE_ANIM_STYLE
        ldb     TEST_DIR
        cmpb    #DIR_WEST
        bne     cm_north_style_done
        inc     GATE_ANIM_STYLE
cm_north_style_done
        clra
        bra     cm_rotate
cm_set_south
        clr     GATE_ANIM_STYLE
        ldb     TEST_DIR
        cmpb    #DIR_EAST
        bne     cm_south_style_done
        inc     GATE_ANIM_STYLE
cm_south_style_done
        lda     #2
cm_rotate
        pshs    a
        lbsr    expose_player_background
        puls    a
        ldx     #GATE_STATE
        ldb     GATE_ID
        sta     b,x
        lda     GATE_ID
        inca
        sta     GATE_ANIM_ID
        deca
        lbsr    draw_gate_diagonal
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
        lbsr    restore_gate_background
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

; Restore the seven contextual cells without drawing dynamic gate art.
restore_gate_background
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

; Draw one arcade diagonal intermediate over a gate-free background.
draw_gate_diagonal
        lbsr    restore_gate_background
        ldd     GATE_X
        pshs    d
        leax    gate_redraw_neighbors,pcr
        ldb     GATE_ID
        lda     b,x
        beq     dgd_no_neighbor
        deca
        lbsr    draw_gate_overlay
dgd_no_neighbor
        puls    d
        std     GATE_X
        lda     GATE_ANIM_ID
        deca
        sta     GATE_ID
        lda     GATE_ANIM_STYLE
        ldb     #21
        mul
        leax    gate_diagonal_tiles,pcr
        leax    d,x
        lda     #7
        sta     DRAW_COUNT
dgd_tile
        lda     GATE_X
        adda    ,x+
        sta     TEST_X
        lda     GATE_Y
        adda    ,x+
        sta     TEST_Y
        ldb     ,x+
        pshs    x
        lbsr    draw_cell_tile
        puls    x
        dec     DRAW_COUNT
        bne     dgd_tile
        lbsr    draw_entities
        rts

; Complete the pending one-Vbord diagonal frame before this frame's movement.
finish_gate_animation
        lda     GATE_ANIM_ID
        beq     fga_done
        lbsr    restore_player
        lbsr    restore_gate_diagonal_dots
        lda     GATE_ANIM_ID
        deca
        lbsr    draw_gate
        clr     GATE_ANIM_ID
        lbsr    draw_entities
        lbsr    draw_player
fga_done
        rts

; Restore the two dot cells overwritten by the selected diagonal style.
restore_gate_diagonal_dots
        lda     GATE_ANIM_ID
        deca
        ldb     #3
        mul
        leax    maze_gates,pcr
        leax    d,x
        ldd     ,x
        std     GATE_X
        lda     GATE_ANIM_STYLE
        lsla
        lsla
        leax    gate_diagonal_dot_offsets,pcr
        leax    a,x
        lda     #2
        sta     DRAW_COUNT
rgdd_cell
        lda     GATE_X
        adda    ,x+
        sta     TEST_X
        lda     GATE_Y
        adda    ,x+
        sta     TEST_Y
        pshs    x
        lbsr    test_cell_offset
        ldx     #MAZE_STATE
        lda     d,x
        bpl     rgdd_clean
        ldb     #MAZE_DOT_TILE
        bra     rgdd_draw
rgdd_clean
        ldb     #MAZE_CLEAN_TILE
rgdd_draw
        lbsr    draw_cell_tile
        puls    x
        dec     DRAW_COUNT
        bne     rgdd_cell
        rts

gate_cross_offsets
        fcb     0,-2,0,-1,-2,0,-1,0,0,0,1,0,0,1
gate_diagonal_dot_offsets
        fcb     1,-1,-1,1,-1,-1,1,1

;==============================================================================
; Object collision, pickup, death, and state-preserving respawn.
;==============================================================================
check_entity_pickup
        ldx     #ENTITY_TABLE
        lda     ENTITY_COUNT
        sta     ENTITY_WORK
cep_loop
        stx     ENTITY_PTR
        lda     2,x
        lbeq    cep_next
        lda     ,x
        cmpa    PLAYER_CELL_X
        lbne    cep_next
        lda     1,x
        cmpa    PLAYER_CELL_Y
        lbne    cep_next
        lda     2,x
        sta     ENTITY_TYPE
        lda     3,x
        sta     ENTITY_VARIANT
        lda     ,x
        sta     ENTITY_X
        lda     1,x
        sta     ENTITY_Y
        lbsr    expose_player_background
        ldx     ENTITY_PTR
        lda     ENTITY_TYPE
        cmpa    #ENTITY_SKULL
        beq     cep_skull
        clr     2,x
        lbsr    restore_entity_footprint
        dec     BONUS_LEFT
        lbsr    add_bonus_score
        lda     ENTITY_TYPE
        cmpa    #ENTITY_HEART
        bne     cep_letter
        lda     BONUS_COLOR
        cmpa    #COLOR_BLUE
        bne     cep_check_clear
        lda     MULTIPLIER
        cmpa    #5
        beq     cep_check_clear
        cmpa    #3
        beq     cep_multiplier_five
        inca
        sta     MULTIPLIER
        lbsr    draw_multiplier_hud
        bra     cep_check_clear
cep_multiplier_five
        lda     #5
        sta     MULTIPLIER
        lbsr    draw_multiplier_hud
        bra     cep_check_clear
cep_letter
        lbsr    apply_letter_pickup
cep_check_clear
        lbsr    begin_score_popup
        lbsr    check_stage_clear
        rts
cep_skull
        ldx     #ENTITY_TABLE
        lda     ENTITY_COUNT
        sta     ENTITY_WORK
cep_skull_loop
        lda     2,x
        cmpa    #ENTITY_SKULL
        bne     cep_skull_next
        lda     ,x
        sta     ENTITY_X
        lda     1,x
        sta     ENTITY_Y
        clr     2,x
        pshs    x
        lbsr    restore_entity_footprint
        puls    x
cep_skull_next
        leax    4,x
        dec     ENTITY_WORK
        bne     cep_skull_loop
        lbsr    draw_entities
        clr     DEATH_TIMER
        lda     #1
        sta     DEATH_STATE
        lda     #DIR_NONE
        sta     PLAYER_DIR
        sta     PLAYER_WANT
        lbsr    enemy_tick
        rts

; Replace the player with the collected colour's score graphic for the exact
; 30-frame MAME hold. The Vbord countdown is independent of joystick input.
; Movement pauses, so the existing player background remains authoritative.
begin_score_popup
        lda     BONUS_COLOR
        cmpa    #COLOR_BLUE
        beq     bsp_blue
        cmpa    #COLOR_YELLOW
        beq     bsp_yellow
        lda     #2              ; Red 800 frame
        bra     bsp_frame
bsp_blue
        clra                    ; Blue 100 frame
        bra     bsp_frame
bsp_yellow
        lda     #1              ; Yellow 300 frame
bsp_frame
        sta     PICKUP_FRAME
        lda     #PICKUP_HOLD_FRAMES
        sta     PICKUP_TIMER
        lbsr    save_player
        lbsr    save_pickup_lower
        lbsr    draw_score_popup
        rts

pickup_tick
        lda     PICKUP_TIMER
        beq     put_done
        dec     PICKUP_TIMER
        bne     put_done
        lbsr    restore_player
        lbsr    restore_pickup_lower
        lbsr    draw_player
put_done
        rts

draw_score_popup
        lda     PICKUP_FRAME
        ldb     #PACKED_SPRITE_SIZE
        mul
        leay    score_sprites,pcr
        leay    d,y
        ldx     PLAYER_FB
        lda     BONUS_COLOR
        cmpa    #COLOR_BLUE
        beq     dsp_blue
        cmpa    #COLOR_YELLOW
        beq     dsp_yellow
        leau    sprite_score_red_pairs,pcr
        bra     dsp_draw
dsp_blue
        leau    sprite_score_blue_pairs,pcr
        bra     dsp_draw
dsp_yellow
        leau    sprite_score_yellow_pairs,pcr
dsp_draw
        lbsr    blit_packed_sprite
        lbsr    draw_popup_multiplier
        rts

draw_popup_multiplier
        lda     MULTIPLIER
        cmpa    #1
        beq     dpm_done
        cmpa    #2
        beq     dpm_two
        cmpa    #3
        beq     dpm_three
        lda     #2
        bra     dpm_select
dpm_two
        clra
        bra     dpm_select
dpm_three
        lda     #1
dpm_select
        ldb     #PICKUP_MULTIPLIER_SIZE
        mul
        leay    pickup_multiplier_graphics,pcr
        leay    d,y
        ldx     PLAYER_FB
        leax    2562,x           ; centre one 8px arcade tile under 16px score
        lda     #8
        ldb     #4
        lbsr    blit_transparent
dpm_done
        rts

save_pickup_lower
        ldx     PLAYER_FB
        leax    2560,x
        ldu     #PICKUP_BG
        lda     #8
        sta     HUD_COUNT
spl_row
        ldd     ,x++
        std     ,u++
        ldd     ,x++
        std     ,u++
        ldd     ,x++
        std     ,u++
        ldd     ,x++
        std     ,u++
        leax    152,x
        dec     HUD_COUNT
        bne     spl_row
        rts

restore_pickup_lower
        ldx     PLAYER_FB
        leax    2560,x
        ldu     #PICKUP_BG
        lda     #8
        sta     HUD_COUNT
rpl_row
        ldd     ,u++
        std     ,x++
        ldd     ,u++
        std     ,x++
        ldd     ,u++
        std     ,x++
        ldd     ,u++
        std     ,x++
        leax    152,x
        dec     HUD_COUNT
        bne     rpl_row
        rts

; User-directed death sequence: R6C7 down through R0C7, R5C10 down
; through R0C10, then the final R7C11 angel swoops upward.
; The requested CoCo transition then walks a normal Lady Bug down the entrance
; before the replacement walks in from below.
death_tick
        tst     PLAYER_BG_VALID
        beq     dt_background_clear
        lbsr    restore_player
dt_background_clear
        lda     DEATH_STATE
        cmpa    #1
        beq     dt_shrink
        cmpa    #2
        beq     dt_wings
        cmpa    #3
        lbeq    dt_walkoff
        rts                     ; state 4: terminal game-over hold
dt_shrink
        lda     DEATH_TIMER
        cmpa    #30
        blo     dt_first_circle
        suba    #30
        ldb     #1
dt_shrink_divide
        cmpa    #5
        blo     dt_shrink_frame
        suba    #5
        incb
        bra     dt_shrink_divide
dt_shrink_frame
        stb     DEATH_FRAME
        bra     dt_shrink_draw
dt_first_circle
        clr     DEATH_FRAME
dt_shrink_draw
        lbsr    draw_death_frame
        inc     DEATH_TIMER
        lda     DEATH_TIMER
        cmpa    #90             ; first frame 30, next twelve 5 each
        lblo    dt_done
        lda     #2
        sta     DEATH_STATE
        clr     DEATH_TIMER
        clr     ANGEL_SWING
        rts
dt_wings
        ldx     PLAYER_FB
        cmpx    #FB_VIRT+160
        bls     dt_finish_wings
        leax    -160,x
        lda     ANGEL_SWING
        leay    angel_swing_deltas,pcr
        ldb     a,y
        beq     dt_swing_store
        bmi     dt_swing_left
        leax    1,x
        bra     dt_swing_store
dt_swing_left
        leax    -1,x
dt_swing_store
        stx     PLAYER_FB
        inc     ANGEL_SWING
        lda     ANGEL_SWING
        cmpa    #20
        blo     dt_swing_phase_ok
        clr     ANGEL_SWING
dt_swing_phase_ok
        lda     #DEATH_ANGEL_FRAME
        sta     DEATH_FRAME
        lbsr    draw_death_frame
        inc     DEATH_TIMER
        lda     DEATH_TIMER
        cmpa    #144
        blo     dt_done
dt_finish_wings
        lbsr    restore_player
        lda     LIVES
        beq     dt_game_over
        deca
        lsla
        adda    #33
        sta     HUD_X
        lda     #21
        sta     HUD_Y
        lbsr    clear_life_marker
        lda     #3
        sta     DEATH_STATE
        lda     #24
        sta     DEATH_TIMER
        lda     #DIR_SOUTH
        sta     PLAYER_FACE
        sta     PLAYER_DIR
        clr     PLAYER_ANIM
        lda     #8
        sta     PLAYER_ANIM_TIMER
        lda     HUD_Y
        ldb     #5
        mul
        tfr     b,a
        clrb
        addd    #FB_VIRT
        tfr     d,x
        clra
        ldb     HUD_X
        lslb
        rola
        lslb
        rola
        leax    d,x
        stx     PLAYER_FB
        lbsr    draw_player
        rts
dt_walkoff
        ldx     PLAYER_FB
        leax    160,x
        stx     PLAYER_FB
        dec     DEATH_TIMER
        beq     dt_finish_walkoff
        lbsr    draw_player
        rts
dt_finish_walkoff
        lda     LIVES
        beq     dt_game_over
        dec     LIVES
        lbsr    draw_lives
        lbsr    init_player
        clr     DEATH_STATE
        lbsr    draw_player
        rts
dt_game_over
        lda     #4
        sta     DEATH_STATE
        lda     #DIR_NONE
        sta     PLAYER_DIR
        sta     PLAYER_WANT
        clr     PLAYER_TICK_PENDING
        clr     PLAYER_BG_VALID
dt_done
        rts

draw_death_frame
        lbsr    save_player
        lda     DEATH_FRAME
        ldb     #PACKED_SPRITE_SIZE
        mul
        leay    death_sprites,pcr
        leay    d,y
        ldx     PLAYER_FB
        lda     DEATH_FRAME
        cmpa    #DEATH_WING_FIRST
        bhs     ddf_white
        leau    sprite_red_pairs,pcr
        bra     ddf_draw
ddf_white
        leau    sprite_white_pairs,pcr
ddf_draw
        lbsr    blit_packed_sprite
        rts

; Smooth 20-frame lateral cycle: ease to +8 pixels, cross to -8, return.
angel_swing_deltas
        fcb     1,1,1,1,0,0,-1,-1,-1,-1
        fcb     -1,-1,-1,-1,0,0,1,1,1,1
cep_next
        ldx     ENTITY_PTR
        leax    4,x
        dec     ENTITY_WORK
        lbne    cep_loop
        rts

restore_entity_footprint
        lda     ENTITY_X
        deca
        sta     TEST_X
        lda     ENTITY_Y
        deca
        sta     TEST_Y
        lbsr    draw_maze_state_cell
        inc     TEST_X
        lbsr    draw_maze_state_cell
        dec     TEST_X
        inc     TEST_Y
        lbsr    draw_maze_state_cell
        inc     TEST_X
        lbsr    draw_maze_state_cell
        rts

draw_maze_state_cell
        lbsr    test_cell_offset
        ldx     #MAZE_STATE
        lda     d,x
        bmi     dmsc_dot
        ; Recover this cell's authored screen tile unless it was a consumed dot.
        lda     TEST_Y
        ldb     #40
        mul
        addb    TEST_X
        adca    #0
        addd    #8
        leax    screen_map,pcr
        ldb     d,x
        cmpb    #MAZE_DOT_TILE
        bne     dmsc_draw
        ldb     #MAZE_CLEAN_TILE
        bra     dmsc_draw
dmsc_dot
        ldb     #MAZE_DOT_TILE
dmsc_draw
        lbsr    draw_cell_tile
        rts

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
        lda     #8
        ldb     #4
        lbsr    blit_transparent
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
        pshs    x
        lbsr    expose_player_background
        puls    x
        lda     ,x
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
        lbsr    add_dot_score
        dec     DOTS_LEFT
        lbsr    check_stage_clear
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
        lsla
        lsla
        adda    PLAYER_ANIM
dp_frame
        ldb     #PACKED_SPRITE_SIZE
        mul
        leay    player_sprites,pcr
        leay    d,y
        ldx     PLAYER_FB
        leau    sprite_attr0_pairs,pcr
        lbsr    blit_packed_sprite
        rts

player_animation_tick
        lda     PICKUP_TIMER
        bne     pat_done
        lda     DEATH_STATE
        beq     pat_count
        cmpa    #3
        bne     pat_done
pat_count
        dec     PLAYER_ANIM_TIMER
        bne     pat_done
        lda     #8
        sta     PLAYER_ANIM_TIMER
        inc     PLAYER_ANIM
        lda     PLAYER_ANIM
        anda    #3
        sta     PLAYER_ANIM
pat_done
        rts

; Bank 3 is copied to $0800 by the GMC bootstrap. Fixed entry points keep the
; resident cartridge image independent of bank-3 link addresses.
init_enemy
        jsr     ENEMY_MODULE_INIT
        rts

enemy_tick
        jsr     ENEMY_MODULE_TICK
        lda     ENEMY_DEATH_LATCH
        cmpa    #1
        bne     etw_done
        inca
        sta     ENEMY_DEATH_LATCH
        lbsr    reset_perimeter_visual
etw_done
        rts

enemy_release
        jsr     ENEMY_MODULE_RELEASE
        rts

enemy_collect
        jsr     ENEMY_MODULE_COLLECT
        rts

; Expand one 16x16 native 2bpp sprite. U selects a 16-byte table mapping
; each two-pixel source nibble to one packed GIME 4bpp destination byte.
blit_packed_sprite
        lda     #16
        sta     BLIT_ROWS
bps_row
        lda     #4
        sta     BLIT_WIDTH
bps_byte
        lda     ,y+
        sta     OBJ_VALUE
        lsra
        lsra
        lsra
        lsra
        lda     a,u
        lbsr    merge_sprite_byte
        lda     OBJ_VALUE
        anda    #$0F
        lda     a,u
        lbsr    merge_sprite_byte
        dec     BLIT_WIDTH
        bne     bps_byte
        leax    152,x
        dec     BLIT_ROWS
        bne     bps_row
        rts

; Merge packed source A at X, preserving destination nibbles where source=0.
merge_sprite_byte
        sta     HUD_BYTE
        clrb
        bita    #$F0
        bne     msb_high
        orb     #$F0
msb_high
        bita    #$0F
        bne     msb_low
        orb     #$0F
msb_low
        andb    ,x
        orb     HUD_BYTE
        stb     ,x+
        rts

sprite_attr0_pairs
        fcb     $00,$0C,$05,$02,$C0,$CC,$C5,$C2
        fcb     $50,$5C,$55,$52,$20,$2C,$25,$22
sprite_red_pairs
        fcb     $00,$01,$01,$01,$10,$11,$11,$11
        fcb     $10,$11,$11,$11,$10,$11,$11,$11
sprite_yellow_pairs
        fcb     $00,$02,$02,$02,$20,$22,$22,$22
        fcb     $20,$22,$22,$22,$20,$22,$22,$22
sprite_blue_pairs
        fcb     $00,$03,$03,$03,$30,$33,$33,$33
        fcb     $30,$33,$33,$33,$30,$33,$33,$33
sprite_white_pairs
        fcb     $00,$06,$06,$06,$60,$66,$66,$66
        fcb     $60,$66,$66,$66,$60,$66,$66,$66
; Set-B score palettes preserve the graphic's colored body, Green details,
; and White digits instead of collapsing all nonzero pens into one shape.
sprite_score_red_pairs
        fcb     $00,$01,$05,$06,$10,$11,$15,$16
        fcb     $50,$51,$55,$56,$60,$61,$65,$66
sprite_score_yellow_pairs
        fcb     $00,$02,$05,$06,$20,$22,$25,$26
        fcb     $50,$52,$55,$56,$60,$62,$65,$66
sprite_score_blue_pairs
        fcb     $00,$03,$05,$06,$30,$33,$35,$36
        fcb     $50,$53,$55,$56,$60,$63,$65,$66

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
        lda     #1
        sta     PLAYER_BG_VALID
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
        clr     PLAYER_BG_VALID
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
; blit_transparent — overlay nonzero packed nibbles from a rectangle.
;
; Inputs:
;   A — source row count
;   B — packed bytes per row (4 for tiles, 8 for player frames)
;   X — destination framebuffer byte address
;   Y — packed 4bpp source data; colour 0 is transparent
;
; Returns: A, B, X, Y, CC undefined
; Side effects: blends the requested rectangle into the framebuffer.
;==============================================================================
blit_transparent
        sta     BLIT_ROWS
        stb     BLIT_WIDTH
btt_row
        lda     BLIT_WIDTH
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
        lda     BLIT_WIDTH
        cmpa    #4
        beq     btt_tile_row
        leax    152,x
        bra     btt_next_row
btt_tile_row
        leax    156,x
btt_next_row
        dec     BLIT_ROWS
        bne     btt_row
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

; Curated animation frames occupy resident ROM because the immutable asset
; window is at its guard limit.
        include "ladybug_resident.inc"

resident_end

; Immutable cartridge data occupies the upper ROM region.  Keep executable
; code and hot constants below $E000; scripts/build.sh enforces both limits.
        align   $2000,$FF
asset_start

;-- Build-generated palette, screen map, and packed tile atlas. --------------
;   scripts/build.sh compiles tiled/coco-screen.tmx with arcade character data
;   before invoking lwasm.
        include "ladybug_screen.inc"
        include "ladybug_maze.inc"

asset_end

        end
