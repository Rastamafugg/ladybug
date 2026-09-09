; Shared masks and typed graphic/text dispatch. Data is generated from authored assets.

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
        tfr x,u
        tfr y,x
        tfr u,y
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
        leax 156,x
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
        leax 156,x
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
        leax 156,x
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
        leax 156,x
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
        leax 156,x
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
        leax 156,x
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
        leax 156,x
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
        leax 156,x
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
        bne colour_skip_3
        ldb #TEXT_RANKING
colour_skip_3
        endc
        ifne TEXT_CONTEXT_COLOURS
        lda $A6
        cmpa #4
        bne colour_skip_4
        ldb #TEXT_GAME_OVER_SCORE
colour_skip_4
        endc
        ifne TEXT_CONTEXT_COLOURS
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
        tfr x,u
        tfr y,x
        tfr u,y
        jmp presentation_fast_blit
