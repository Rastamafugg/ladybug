; Shared masks and typed graphic/text dispatch. Data is generated from authored assets.

; Font producer guards the last compact glyph as the blank mask.
asset_part_digits
        pshs    a
        tfr     b,a
        tsta
        bne     asset_part_write
        lda     #((colour_lut-font)/8)-1
asset_part_write
        bsr     asset_draw_hud_digit
        inc     HUD_X
        puls    a
        bra     asset_draw_two_digits

; DOC-002 source-contract mirror contract life_marker_position profile=render: Map reserve slots 0-11 to authored HUD tile roots; write HUD_X and HUD_Y only.
; A = slot0..11; writes only HUD_X/HUD_Y; no live-state mutation.
life_marker_position
        ldb     #21
dl_position_row
        cmpa    #3
        blo     dl_position_column
        suba    #3
        subb    #2
        bra     dl_position_row
dl_position_column
        lsla
        adda    #33
        sta     HUD_X
        stb     HUD_Y
        rts
asset_draw_two_digits
        clrb
asset_number_tens
        cmpa    #10
        blo     asset_number_digits
        suba    #10
        incb
        cmpb    #10
        blo     asset_number_tens
        clrb
        bra     asset_number_tens
asset_number_digits
        pshs    a
        tfr     b,a
        jsr     asset_draw_hud_digit
        inc     HUD_X
        puls    a
        bra     asset_draw_hud_digit

asset_draw_hud_digit
        pshs a
        lda HUD_Y
        ldb #5
        mul
        tfr b,a
        clrb
        addd #FB_VIRT
        tfr d,x
        clra
        ldb HUD_X
        lslb
        lslb
        leax d,x
        puls a
        bra shared_mask
asset_draw_text_at_y
        tfr y,x
        bra shared_mask
asset_draw_recolored_map_tile
        lda HUD_Y
        ldb #8
        mul
        addb HUD_X
        leay hud_glyph_cells,pcr
        lda d,y
        bra asset_draw_hud_digit
presentation_dispatch
        cmpb #174
        blo graphic
        subb #174
        tfr b,a
        bra asset_draw_text_at_y
graphic
        tfr b,a
        ldb #32
        mul
        jsr SHARED_COLD_PTR
        exg x,y
        tfr y,u
        jmp presentation_fast_blit

shared_mask
        pshs u
        ldb #8
        mul
        leay font,pcr
        leay d,y
        lda HUD_COLOR
        ldb #32
        mul
        leau colour_lut,pcr
        leau d,u
        lda #8
        pshs a
shared_mask_row
        lda ,y+
        sta HUD_BYTE
        anda #$F0
        lsra
        lsra
        lsra
        ldd a,u
        std ,x++
        lda HUD_BYTE
        anda #15
        lsla
        ldd a,u
        std ,x++
        ldb #156
        abx
        dec ,s
        bne shared_mask_row
        leas 1,s
        puls u,pc
gameplay_dispatch
        cmpb #SCREEN_TILE_COUNT
        bhs gameplay_text
        tfr b,a
        ldb #32
        mul
        leay screen_tiles,pcr
        leay d,y
        jmp blit_tile
gameplay_text
        subb #SCREEN_TILE_COUNT
        clra
        lslb
        rola
        leay gameplay_descriptors,pcr
        leay d,y
        lda 1,y
        sta HUD_COLOR
        lda ,y
        jmp shared_mask

presentation_fast_blit
        ldd ,y++
        std ,x++
        ldd ,y++
        std ,x++
        leax 156,x
        ldd ,y++
        std ,x++
        ldd ,y++
        std ,x++
        leax 156,x
        ldd ,y++
        std ,x++
        ldd ,y++
        std ,x++
        leax 156,x
        ldd ,y++
        std ,x++
        ldd ,y++
        std ,x++
        leax 156,x
        ldd ,y++
        std ,x++
        ldd ,y++
        std ,x++
        leax 156,x
        ldd ,y++
        std ,x++
        ldd ,y++
        std ,x++
        leax 156,x
        ldd ,y++
        std ,x++
        ldd ,y++
        std ,x++
        leax 156,x
        ldd ,y++
        std ,x++
        ldd ,y++
        std ,x++
        leax 156,x
        rts

dynamic_dispatch
        clra

dynamic_index
        lslb
        rola
        leax dynamic_descriptors,pcr
        leax d,x
        ldb 1,x
        beq dynamic_graphic
        ifne TEXT_CONTEXT_COLOURS
        lda $A6
        cmpa #3
        beq field_colour_ready
        cmpa #5
        bne colour_skip_3
field_colour_ready
        ldb $E8
colour_skip_3
        endc
        ifne TEXT_GAME_OVER_SCORE-6
        lda $A6
        cmpa #4
        bne colour_skip_4
        ldb #TEXT_GAME_OVER_SCORE
colour_skip_4
        endc
        ifne TEXT_NAME-6
        lda $A6
        cmpa #5
        bne colour_skip_5
        ldb #TEXT_NAME
colour_skip_5
        endc
        stb $29
        lda ,x
        tfr y,x
        jmp shared_mask
dynamic_graphic
        lda ,x
        ldb #32
        mul
        jsr SHARED_COLD_PTR
        exg x,y
        tfr y,u
        jmp presentation_fast_blit

; Draw the committed first score and name on the gameplay/demo HUD.
; PAR4 is borrowed for record reads; the framebuffer BACK remains in PAR1-PAR3.
asset_draw_top_hud
        lda $FFA4
        pshs a
        lda #$34
        sta $FFA4
        lda #6
        sta HUD_Y
        lda #TEXT_HIGH_SCORE
        sta HUD_COLOR
        ldu #PRES_HIGHSCORE_BASE-$2000
        jsr draw_bcd_line
        ldx #$3984
        ldb #7
asset_top_name
        lda ,u+
        pshs b,x,u
        tsta
        beq asset_top_blank
        ldb #2
        mul
        leay dynamic_descriptors,pcr
        leay d,y
        tst 1,y
        beq asset_top_blank
        lda ,y
        bra asset_top_glyph
asset_top_blank
        clr HUD_COLOR
        clra
asset_top_glyph
        jsr shared_mask
        lda #TEXT_HIGH_SCORE
        sta HUD_COLOR
        puls b,x,u
        leax 4,x
        decb
        bne asset_top_name
asset_top_done
        puls a
        sta $FFA4
        rts
asset_top_default_name
        fcb PRESENTATION_HIGHSCORE_DEFAULT_NAME_0
        fcb PRESENTATION_HIGHSCORE_DEFAULT_NAME_1
        fcb PRESENTATION_HIGHSCORE_DEFAULT_NAME_2
        fcb PRESENTATION_HIGHSCORE_DEFAULT_NAME_3
        fcb PRESENTATION_HIGHSCORE_DEFAULT_NAME_4
        fcb PRESENTATION_HIGHSCORE_DEFAULT_NAME_5
        fcb PRESENTATION_HIGHSCORE_DEFAULT_NAME_6
