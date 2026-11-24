; FEAT-011 EXTRA and SPECIAL intermission runtime.
; Staged in physical page $24 at $B920 and copied into phase-exclusive low RAM
; $0300-$06A9 when handling complete-profile stage/intermission transitions.
; DOC-002 source-contract mirror begins. Canonical definitions:
; wiki/internal/implementation/routine-catalog.html
; DOC-002 source-contract mirror profile presentation Inputs: Presentation state, interval timer, input edges, current map, and the selected auxiliary profile
; DOC-002 source-contract mirror profile presentation Outputs: Updated presentation state and the dispatcher retain/release status when applicable
; DOC-002 source-contract mirror profile presentation Clobbers: A, B, D, X, Y, U, and condition codes unless a narrower source-local header is present
; DOC-002 source-contract mirror profile presentation Reads: Presentation direct-page state, cold payloads, authored map streams, and input state
; DOC-002 source-contract mirror profile presentation Writes: Presentation state, mapped BACK pixels, and presentation-owned persistent metadata
; DOC-002 source-contract mirror profile presentation Side effects: May retain the foreground interval or produce a complete presentation surface
; DOC-002 source-contract mirror profile presentation Invariants: Gameplay simulation begins only after release; hidden hydration may prepare initial-stage state and hold it unchanged until release; FRONT publication remains IRQ-owned
; DOC-002 source-contract mirror profile render Inputs: Current render intent, selected actor or tile state, and a valid BACK or staging destination
; DOC-002 source-contract mirror profile render Outputs: Updated destination pixels and any owner-local history required by later restoration
; DOC-002 source-contract mirror profile render Clobbers: A, B, D, X, Y, U, and condition codes unless a narrower source-local header is present
; DOC-002 source-contract mirror profile render Reads: Authoritative gameplay state, immutable art streams, and current owner-local background metadata
; DOC-002 source-contract mirror profile render Writes: BACK or staging pixels, render scratch, and owner-local save-under or damage metadata
; DOC-002 source-contract mirror profile render Side effects: Changes a non-visible composition surface or its metadata
; DOC-002 source-contract mirror profile render Invariants: The routine never selects the visible FRONT surface; temporary PAR5 mappings expire or restore before return
; DOC-002 source-contract mirror contract intermission_tick profile=presentation: Advance the non-skippable EXTRA or SPECIAL intermission animation, wait for full route and celebration audio completion, and hand off cleanly to Level Start.
; DOC-002 source-contract mirror contract intermission_stage_entry_low profile=presentation: Restore PAR5 to $34 and either run the plain next-stage handoff or initialize MODE_INTERMISSION from PRES_INTERMISSION.
; DOC-002 source-contract mirror contract im_draw_scene profile=render: Render the 24x24 EVD1 event scene from physical pages $26/$25 into BACK columns 8-31 and restore PAR5 to $34.
; DOC-002 source-contract mirror contract im_draw_sprite profile=render: Save owner-local underlay and draw the animated Lady Bug sparse sprite at the current route coordinate, restoring PAR5 to $34.
; DOC-002 source-contract mirror contract im_load_segment profile=presentation: Read the next (dir, steps) route segment from page $26, chaining from the EXTRA shared route into the selected reserve-slot connector, and restore PAR5 to $34.
; DOC-002 source-contract mirror ends.

        pragma  nodollarlocal,6809
        setdp   $00
        include "ladybug_presentation.inc"
        include "ladybug_presentation_symbols.inc"
        include "ladybug_event_assets.inc"

PAR5                    equ $FFA5
SPARSE_PLAYER_PAGE      equ $39
SPARSE_PLAYER_INDEX     equ $A000
AUDIO_RUNTIME_PAGE      equ $3D
AUDIO_ENQUEUE_EXEC      equ $A006
PRESENTATION_MODULE_DRAW equ $0821

JOY_DIR                 equ $0005
PLAYER_FB               equ $000B
PLAYER_WANT             equ $000F
SCORE_BCD               equ $001D
LIVES                   equ $0023
SPECIAL_BITS            equ $003C
EXTRA_BITS              equ $003D
FB_BACK                 equ $0090
PLAYER_BG_PTR           equ $00A2
PRES_MODE               equ $00A5
PRES_CONTEXT            equ $00A7
PRES_INTERMISSION       equ $00A8
PRES_EVENT              equ $00A9

AUDIO_MUSIC_BUSY        equ $02D4
IM_SAVE_A               equ $A300
IM_SAVE_B               equ $AB00
IM_SPECIAL_COIN_FB      equ $2A28       ; coin 16x16 root at (10,2) = (80,16) px

MODE_INTERMISSION       equ 9
PRES_CONTEXT_NEXT_STAGE equ 2

        ; Verify generated marker-derived Part Vegetable destinations match
        ; the shared HUD vegetable destination rendered by draw_shared_hud.
        ifne    FEAT011_SPECIAL_VEGETABLE_DST-PRESENTATION_HUD_VEGETABLE_ICON_DST
        error   "SPECIAL Part Vegetable marker destination diverges from shared HUD"
        endc
        ifne    FEAT011_EXTRA_VEGETABLE_DST-PRESENTATION_HUD_VEGETABLE_ICON_DST
        error   "EXTRA Part Vegetable marker destination diverges from shared HUD"
        endc

        org     $0300

intermission_tick
        lbra    im_tick
intermission_stage_entry_low
        lbra    im_stage_entry

; ------------------------------------------------------------------------------
; Entry from page-$24 copy stub: PAR5 is still $24 on arrival; restore $34 first.
; ------------------------------------------------------------------------------
im_stage_entry
        lda     #$34
        sta     PAR5
        lda     <PRES_INTERMISSION
        bne     im_begin_intermission
        ; Plain stage clear (no EXTRA/SPECIAL intermission).
        ; Map hidden BACK before next_stage so erase_entity_footprints never writes FRONT.
        jsr     PRES_MODULE_MAP_BACK
        lda     #$34
        sta     PAR5
        jsr     PRES_MAIN_NEXT_STAGE
        lda     #PRES_CONTEXT_NEXT_STAGE
        sta     <PRES_CONTEXT
        lda     #PRESENTATION_MAP_LEVEL_START
        jsr     PRES_MODULE_START_SCREEN
        lda     #1
        rts

im_begin_intermission
        sta     im_kind
        lda     #MODE_INTERMISSION
        sta     <PRES_MODE
        clr     <PRES_EVENT
        clr     im_init_mask
        clr     im_final_mask
        clr     im_route_done
        clr     im_parity
        clr     im_anim_tick
        clr     im_valid_a
        clr     im_valid_b
        clr     im_extra_phase
        clr     im_audio_started
        lda     #30
        sta     im_dwell

        ; Clear the completed word bits now that PRES_MODE == MODE_INTERMISSION
        ; so audio_poll_gameplay cannot fire Cue 10/11 before the animation starts.
        lda     im_kind
        cmpa    #1
        beq     im_clr_extra_bits
        clr     <SPECIAL_BITS
        bra     im_bits_cleared
im_clr_extra_bits
        clr     <EXTRA_BITS
im_bits_cleared

        ; Compute EXTRA reserve target slot = min(pre-award LIVES, 11).
        ; LIVES is incremented upon Lady Bug arrival at the reserve slot.
        lda     <LIVES
        cmpa    #11
        bls     im_slot_ok
        lda     #11
im_slot_ok
        sta     im_extra_slot

        ; Load route start (top-left x,y) and first segment from page $26.
        lda     #EVENT_DATA_PAGE
        sta     PAR5
        lda     im_kind
        cmpa    #1
        beq     im_select_extra
        ldx     #EVENT_SPECIAL_ROUTE_ADDR
        bra     im_route_selected
im_select_extra
        lda     #1
        sta     im_extra_phase
        ldx     #EVENT_EXTRA_SHARED_ROUTE_ADDR
im_route_selected
        ldd     ,x++
        std     im_pos_x
        ldd     ,x++
        std     im_pos_y
        stx     im_seg_ptr
        lda     #$34
        sta     PAR5
        lbsr    im_load_segment

        ; Capture pre-award HUD snapshot (score and lives update on arrival).
        jsr     PRES_MAIN_HUD_CAPTURE_PLAYER
        lda     #1
        rts

; ------------------------------------------------------------------------------
; Per-Vbord tick while PRES_MODE == MODE_INTERMISSION (9).
; ------------------------------------------------------------------------------
im_tick
        clr     <PRES_EVENT             ; non-skippable: discard menu/start edges
        tst     im_route_done
        beq     im_render_frame
        lda     im_final_mask
        cmpa    #3
        bne     im_render_frame
        ; Both buffers show final arrived state; wait for arrival dwell and audio.
        tst     im_dwell
        beq     im_wait_audio
        dec     im_dwell
        bra     im_hold
im_wait_audio
        tst     AUDIO_MUSIC_BUSY
        bne     im_hold
        ; Clean exit: map hidden BACK before next_stage so erase_entity_footprints
        ; never writes to the visible FRONT intermission surface during Level Start load.
        jsr     PRES_MODULE_MAP_BACK
        lda     #$34
        sta     PAR5
        lda     im_kind
        cmpa    #2
        bne     im_next_stage
        jsr     PRES_MAIN_CHECK_SPECIAL_BONUS_LIFE
im_next_stage
        clr     <PRES_INTERMISSION
        clr     <PRES_EVENT
        lda     #$FF
        sta     <JOY_DIR
        sta     <PLAYER_WANT
        jsr     PRES_MAIN_NEXT_STAGE
        jsr     PRES_MAIN_HUD_CAPTURE_PLAYER
        lda     #PRES_CONTEXT_NEXT_STAGE
        sta     <PRES_CONTEXT
        lda     #PRESENTATION_MAP_LEVEL_START
        jsr     PRES_MODULE_START_SCREEN
im_hold
        lda     #1
        rts

im_render_frame
        jsr     PRES_MAIN_FB_PREPARE
        bcs     im_hold

        ; Compute current owner mask bit (1 for A, 2 for B).
        lda     #1
        tst     <FB_BACK
        beq     im_owner_bit_ok
        lda     #2
im_owner_bit_ok
        sta     im_cur_bit

        ; Step 1: Initialize static event scene + shared HUD once per buffer.
        bita    im_init_mask
        bne     im_scene_ready
        ora     im_init_mask
        sta     im_init_mask
        lbsr    im_draw_scene
        lda     #PRESENTATION_HUD_DRAW_ALL
        clrb
        jsr     PRES_MAIN_SHARED_HUD
        ; Clear this owner's stale underlay flag after full scene paint.
        tst     <FB_BACK
        bne     im_clr_b
        clr     im_valid_a
        bra     im_after_restore
im_clr_b
        clr     im_valid_b
        bra     im_after_restore

im_scene_ready
        ; Step 2: Restore this owner's prior Lady Bug underlay if valid.
        lda     #$34
        sta     PAR5
        tst     <FB_BACK
        bne     im_restore_b
        tst     im_valid_a
        beq     im_after_restore
        ldd     im_old_fb_a
        std     <PLAYER_FB
        ldx     #IM_SAVE_A
        stx     <PLAYER_BG_PTR
        jsr     PRES_MAIN_RESTORE_PLAYER
        clr     im_valid_a
        bra     im_after_restore
im_restore_b
        tst     im_valid_b
        beq     im_after_restore
        ldd     im_old_fb_b
        std     <PLAYER_FB
        ldx     #IM_SAVE_B
        stx     <PLAYER_BG_PTR
        jsr     PRES_MAIN_RESTORE_PLAYER
        clr     im_valid_b

im_after_restore
        ; Step 3: Advance route once both buffers are initialized.
        lda     im_init_mask
        cmpa    #3
        lbne    im_draw_current
        tst     im_route_done
        lbne    im_check_final_hud
        inc     im_parity
        lda     im_parity
        bita    #1
        lbeq    im_draw_current         ; 2 px every 2nd Vbord = 1 px/frame

        ; Start Cue 10 (EXTRA) or Cue 11 (SPECIAL) once Lady Bug begins moving onscreen.
        tst     im_audio_started
        bne     im_audio_ready
        tst     im_pos_y
        bmi     im_audio_ready
        lda     #1
        sta     im_audio_started
        lda     #AUDIO_RUNTIME_PAGE
        sta     PAR5
        lda     #10
        ldb     im_kind
        cmpb    #1
        beq     im_enqueue_cue
        lda     #11
im_enqueue_cue
        clrb
        jsr     AUDIO_ENQUEUE_EXEC
        lda     #$34
        sta     PAR5
im_audio_ready

        ; Advance one 2-pixel step along im_dir.
        lda     im_dir
        beq     im_step_n
        cmpa    #1
        beq     im_step_e
        cmpa    #2
        beq     im_step_s
        ; DIR_W
        ldd     im_pos_x
        subd    #2
        std     im_pos_x
        bra     im_step_done
im_step_n
        ldd     im_pos_y
        subd    #2
        std     im_pos_y
        bra     im_step_done
im_step_e
        ldd     im_pos_x
        addd    #2
        std     im_pos_x
        bra     im_step_done
im_step_s
        ldd     im_pos_y
        addd    #2
        std     im_pos_y
im_step_done
        inc     im_anim_tick
        dec     im_steps
        bne     im_draw_current
        lbsr    im_load_segment
        tst     im_route_done
        beq     im_draw_current
        ; Route just completed: apply the arrival reward before refreshing HUD.
        lda     im_kind
        cmpa    #1
        beq     im_award_extra
        ; SPECIAL arrival: award 100,000 BCD points when Lady Bug overlaps coin.
        lda     <SCORE_BCD
        adda    #$10
        daa
        sta     <SCORE_BCD
        bra     im_award_capture
im_award_extra
        ; EXTRA arrival: saturate reserve lives at 255 before replacing sprite.
        lda     <LIVES
        cmpa    #$FF
        bhs     im_award_capture
        inc     <LIVES
im_award_capture
        jsr     PRES_MAIN_HUD_CAPTURE_PLAYER

im_check_final_hud
        ; Apply arrival visual update once on each A/B buffer.
        lda     im_cur_bit
        bita    im_final_mask
        bne     im_draw_current
        ora     im_final_mask
        sta     im_final_mask
        lda     im_kind
        cmpa    #1
        beq     im_final_extra
        ; SPECIAL: update P1 score HUD and despawn the 16x16 coin at (80,16).
        lda     #PRESENTATION_HUD_DRAW_PRIMARY
        clrb
        jsr     PRES_MAIN_SHARED_HUD
        ldx     #IM_SPECIAL_COIN_FB
        lda     #16
        sta     im_row_cnt
        ldd     #0
im_clear_coin_row
        std     ,x
        std     2,x
        std     4,x
        std     6,x
        leax    160,x
        dec     im_row_cnt
        bne     im_clear_coin_row
        bra     im_draw_current
im_final_extra
        ; EXTRA: paint permanent 16x16 reserve marker in place of moving sprite.
        lda     #PRESENTATION_HUD_DRAW_LIVES
        clrb
        jsr     PRES_MAIN_SHARED_HUD

im_draw_current
        ; Step 4: Draw Lady Bug if onscreen, except after EXTRA settles into HUD.
        tst     im_route_done
        beq     idc_check_y
        lda     im_kind
        cmpa    #1
        beq     im_finish_frame
idc_check_y
        tst     im_pos_y
        bmi     im_finish_frame
        lbsr    im_draw_sprite
im_finish_frame
        lda     #$34
        sta     PAR5
        jsr     PRES_MAIN_FB_FINISH
        lda     #1
        rts

; ------------------------------------------------------------------------------
; im_load_segment: read next (dir, steps) from page $26, chaining EXTRA connector.
; ------------------------------------------------------------------------------
im_load_segment
        lda     #EVENT_DATA_PAGE
        sta     PAR5
        ldx     im_seg_ptr
        lda     ,x+
        cmpa    #$FF
        bne     ils_store
        tst     im_extra_phase
        beq     ils_route_end
        clr     im_extra_phase
        lda     im_extra_slot
        ldb     #EVENT_EXTRA_CONNECTOR_STRIDE
        mul
        addd    #EVENT_EXTRA_CONNECTORS_ADDR
        tfr     d,x
        lda     ,x+
        cmpa    #$FF
        beq     ils_route_end
ils_store
        sta     im_dir
        ldb     ,x+
        stb     im_steps
        stx     im_seg_ptr
        lda     #$34
        sta     PAR5
        rts
ils_route_end
        lda     #1
        sta     im_route_done
        lda     #$34
        sta     PAR5
        rts

; ------------------------------------------------------------------------------
; im_draw_scene: draw 24x24 CoCo Event Scene from pages $26/$25 into BACK.
; ------------------------------------------------------------------------------
im_draw_scene
        lda     im_kind
        cmpa    #1
        beq     ids_extra
        ldx     #EVENT_SPECIAL_MAP_ADDR
        bra     ids_start
ids_extra
        ldx     #EVENT_EXTRA_MAP_ADDR
ids_start
        stx     im_map_ptr
        ldy     #$2020                  ; row 0, col 8 ($2000 + 8*4)
        lda     #24
        sta     im_row_cnt
ids_row_loop
        lda     #24
        sta     im_col_cnt
        sty     im_row_fb
ids_col_loop
        lda     #EVENT_DATA_PAGE
        sta     PAR5
        ldx     im_map_ptr
        lda     ,x+
        stx     im_map_ptr
        ldb     #32
        mul
        addd    #EVENT_ATLAS_ADDR
        tfr     d,x
        lda     #EVENT_ATLAS_PAGE
        sta     PAR5
        ; Blit 8x8 tile (8 rows x 4 bytes) from X to BACK Y.
        pshs    y
        ldb     #8
ids_tile_row
        ldu     ,x++
        stu     ,y
        ldu     ,x++
        stu     2,y
        leay    160,y
        decb
        bne     ids_tile_row
        puls    y
        leay    4,y
        dec     im_col_cnt
        bne     ids_col_loop
        ldd     im_row_fb
        addd    #1280                   ; next tile row (8 * 160)
        tfr     d,y
        dec     im_row_cnt
        bne     ids_row_loop
        lda     #$34
        sta     PAR5
        rts

; ------------------------------------------------------------------------------
; im_draw_sprite: save owner underlay and draw animated Lady Bug at (x, y).
; ------------------------------------------------------------------------------
im_draw_sprite
        lda     #$34
        sta     PAR5
        lda     im_pos_y+1
        ldb     #160
        mul
        addd    #$2000
        std     im_fb_dst
        ldd     im_pos_x
        lsra
        rorb
        clra
        addd    im_fb_dst
        std     im_fb_dst
        std     <PLAYER_FB

        tst     <FB_BACK
        bne     idsp_save_b
        std     im_old_fb_a
        ldx     #IM_SAVE_A
        stx     <PLAYER_BG_PTR
        jsr     PRES_MAIN_SAVE_PLAYER
        lda     #1
        sta     im_valid_a
        bra     idsp_blit
idsp_save_b
        std     im_old_fb_b
        ldx     #IM_SAVE_B
        stx     <PLAYER_BG_PTR
        jsr     PRES_MAIN_SAVE_PLAYER
        lda     #1
        sta     im_valid_b

idsp_blit
        ; Sparse frame index = im_dir * 4 + ((im_anim_tick >> 2) & 3).
        lda     im_anim_tick
        lsra
        lsra
        anda    #3
        ldb     im_dir
        lslb
        lslb
        pshs    b
        adda    ,s+
        ldb     #3
        mul
        tfr     d,x
        lda     #SPARSE_PLAYER_PAGE
        sta     PAR5
        leax    SPARSE_PLAYER_INDEX,x
        ldu     1,x
        lda     ,x
        sta     PAR5
        ldx     im_fb_dst
        jsr     PRESENTATION_MODULE_DRAW
        lda     #$34
        sta     PAR5
        rts

; ------------------------------------------------------------------------------
; Local RAM state inside $0300-$06A9 (phase-exclusive).
; ------------------------------------------------------------------------------
im_kind         fcb     0
im_init_mask    fcb     0
im_final_mask   fcb     0
im_cur_bit      fcb     0
im_route_done   fcb     0
im_parity       fcb     0
im_anim_tick    fcb     0
im_extra_phase  fcb     0
im_extra_slot   fcb     0
im_dir          fcb     0
im_steps        fcb     0
im_row_cnt      fcb     0
im_col_cnt      fcb     0
im_valid_a      fcb     0
im_valid_b      fcb     0
im_dwell        fcb     0
im_audio_started fcb    0
im_pos_x        fdb     0
im_pos_y        fdb     0
im_seg_ptr      fdb     0
im_map_ptr      fdb     0
im_row_fb       fdb     0
im_fb_dst       fdb     0
im_old_fb_a     fdb     0
im_old_fb_b     fdb     0
intermission_runtime_end
