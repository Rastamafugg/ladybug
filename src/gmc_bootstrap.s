; DOC-002 source-contract mirror contract decompress_presentation_atlas profile=boot: Decompress the presentation atlas for its runtime destination.
; DOC-002 source-contract mirror contract decompress_gmc_streams profile=boot: Decompress gmc streams.
; DOC-002 source-contract mirror contract decompress_staged_audio profile=boot: Decompress staged audio.
; DOC-002 source-contract mirror contract copy_late_sparse_segments profile=boot: After audio consumes page $24 staging, briefly reselect GMC ROM, copy only delayed auxiliary records to physical page $24, then restore all-RAM.
; DOC-002 source-contract mirror contract copy_sparse_payload profile=boot: Copy one already-selected sparse descriptor payload and return with the table pointer advanced.
; DOC-002 source-contract mirror contract dgs_descriptor profile=boot: Decode one staged compressed-stream descriptor.
; Ladybug GMC bank loader. Bank 0 executes here, then this routine runs from
; low RAM while selecting bank 1 and copying the runtime into physical RAM.
; DOC-002 source-contract mirror begins. Canonical definitions:
; wiki/internal/implementation/routine-catalog.html
; DOC-002 source-contract mirror profile boot Inputs: The declared cartridge bank, staged payload, destination identity, and bootstrap mapping state
; DOC-002 source-contract mirror profile boot Outputs: Installed runtime bytes or a non-returning transfer to the next boot phase
; DOC-002 source-contract mirror profile boot Clobbers: All CPU registers and condition codes
; DOC-002 source-contract mirror profile boot Reads: Cartridge-staged payloads, generated size symbols, and bootstrap tables
; DOC-002 source-contract mirror profile boot Writes: Declared RAM destinations, PAR registers, boot scratch, and decompressed surfaces
; DOC-002 source-contract mirror profile boot Side effects: Changes MMU mappings and copies or synthesizes executable/data payloads
; DOC-002 source-contract mirror profile boot Invariants: Authored, staged, and destination byte identities remain distinct and every transfer obeys its generated size bound
; DOC-002 source-contract mirror contract boot_entry profile=boot: Establish bootstrap mappings, start the complete-profile loading display, and transfer control into the low-RAM loader.
; DOC-002 source-contract mirror contract boot_loading_video profile=boot: Set up framebuffer A, draw the compiled loading asset, and unblank at VBORD before relocating the loader.
; DOC-002 source-contract mirror contract boot_loading_irq profile=boot: Acknowledge VBORD before framebuffer initialization, then delegate publication and animate dots until B becomes FRONT.
; DOC-002 source-contract mirror contract boot_loading_hydrate profile=boot: Request the first Attract commit on B, then restore the normal vector after rendering Attract on A.
; DOC-002 source-contract mirror contract decompress_attract_surfaces profile=boot: Decompress attract surfaces.
; DOC-002 source-contract mirror contract spr_byte_changed profile=boot: Test whether synthesis changed the current perimeter-reset output byte.
; DOC-002 source-contract mirror contract synthesize_perimeter_reset profile=boot: Synthesize perimeter reset.
; DOC-002 source-contract mirror ends.

GMC_BANK    equ $FF40
GIME_INIT0  equ $FF90
GIME_MMU    equ $FF91
GIME_IRQEN  equ $FF92
GIME_FIRQEN equ $FF93
GIME_VMODE  equ $FF98
GIME_VRES   equ $FF99
GIME_BORDER equ $FF9A
GIME_VOFF1  equ $FF9D
GIME_VOFF0  equ $FF9E
GIME_HOFF   equ $FF9F
PAR_EXEC    equ $FFA0
PAL_BASE    equ $FFB0
JT_IRQ      equ $FEF7
SAM_FAST    equ $FFD9
SAM_CART    equ $FFDE
SAM_ALLRAM  equ $FFDF
BOOT_FLAG   equ $02F0
BOOT_PROOF  equ $02F1
BOOT_SEGMENTS equ $02F2
BOOT_BOX    equ $02F3
BOOT_CELL_X equ $02F4
BOOT_CELL_Y equ $02F5
BOOT_ROW    equ $02F6
BOOT_COL    equ $02F7
BOOT_TILE_PTR equ $02F8
BOOT_DEST   equ $02FA
BOOT_LZ_FLAGS equ $02FC
BOOT_LZ_BITS equ $02FD
BOOT_LZ_OFFSET equ $02FE
BOOT_DESC_PTR equ $0280
BOOT_SRC_END equ $0282
BOOT_DEST_END equ $0284
BOOT_STREAMS equ $0286
; @audit {"id":"boot-stream-descriptors","kind":"scratch","symbol":"GMC_LZSS_TABLE_RAM","width":127,"mapping":"unbanked-low-ram","phases":["boot"],"owner":"GMC bootstrap","lifetime":"Up to nine descriptors retire at boot_streams_retired after staged audio expansion and before runtime handoff.","initialization":"copy_gmc_lzss_table","clobbers":"The first 127 bytes of runtime ACTOR_STAGE at $1800-$187E are reused only after descriptor retirement; no retained runtime pointer."}
GMC_LZSS_TABLE_RAM equ $1800
; @audit {"id":"boot-audio-stream","kind":"index","symbol":"GMC_LZSS_AUDIO_OFFSET","producer":"boot-audio-stream","domain":"Offset of unique final audio descriptor","encoding":"Generated stream ordinal times fourteen","bounds":[0,112]}
LOADER_RAM  equ $0300
RESIDENT_STAGE_PAGE equ $21
ASSET_STAGE_PAGE equ $22
AUDIO_STAGE_PAGE equ $24
AUXILIARY_STAGE_PAGE equ $24
PRESENTATION_NAME_ENTRY_DATA equ 0

        include "ladybug_presentation.inc"
        ifne COMPLETE_PROFILE
        include "gmc_loading.inc"
        include "ladybug-loading-symbols.inc"
FB_MODULE_IRQ equ $081E
        endc

        org $C000
        fcc "DK"

boot_entry
        orcc    #$50
        ifne COMPLETE_PROFILE
        lda     #$1F
        sta     GIME_VRES
        clr     GIME_BORDER
        endc
        lds     #$1FFE
        clr     GIME_MMU
        lda     #$38
        sta     PAR_EXEC
        lda     #$3E
        sta     PAR_EXEC+5
        sta     PAR_EXEC+6
        lda     #$3F
        sta     PAR_EXEC+7
        lda     #%01101100      ; MMU + force FExx + SCS for GMC $FF40
        sta     GIME_INIT0
        ; Clear any SN76489 state left by a warm or cold reset before the
        ; foreground runtime is installed.  These are attenuation writes,
        ; not frequency changes, so no stale tone can remain audible.
        lda     #$9F
        sta     $FF41
        lda     #$BF
        sta     $FF41
        lda     #$DF
        sta     $FF41
        lda     #$FF
        sta     $FF41
        sta     SAM_FAST        ; run the boot copy at the normal 1.78 MHz rate
        sta     SAM_CART        ; BASIC autorun may leave TY=1; expose GMC ROM
        ifne COMPLETE_PROFILE
        lbsr    boot_loading_video
        endc
        leax    loader_start,pcr
        ldy     #LOADER_RAM
        ldu     #loader_end-loader_start
boot_copy
        lda     ,x+
        sta     ,y+
        leau    -1,u
        cmpu    #0
        bne     boot_copy
        jmp     LOADER_RAM

loader_start
        lda     #$02
        tfr     a,dp
        setdp   $02
        ; Prove that banks 2 and 3 expose different signatures at $C010.
        lda     #2
        sta     GMC_BANK
        ldd     $C010
        cmpd    #$B202
        lbne    loader_fail
        lda     #3
        sta     GMC_BANK
        ldd     $C010
        cmpd    #$B303
        lbne    loader_fail
        lda     #$5A
        sta     BOOT_PROOF

        ; Preserve the generated LZSS table before the enemy runtime copy
        ; reclaims its final relocated source bytes at $0800-$0801.
        lda     #0
        sta     GMC_BANK
        leax    gmc_lzss_stream_table,pcr
        ldy     #GMC_LZSS_TABLE_RAM
        ldu     #GMC_LZSS_STREAM_TABLE_BYTES
copy_gmc_lzss_table
        lda     ,x+
        sta     ,y+
        leau    -1,u
        cmpu    #0
        bne     copy_gmc_lzss_table

        ; Save the sparse copy plan before the enemy module overwrites the
        ; final relocated source bytes at $0800-$0806.
        leax    sparse_copy_table,pcr
        ldy     #SPARSE_COPY_TABLE_RAM
        ldu     #SPARSE_COPY_TABLE_BYTES
copy_sparse_table
        lda     ,x+
        sta     ,y+
        leau    -1,u
        cmpu    #0
        bne     copy_sparse_table

        ; Bank 3 offset $0800 contains an absolute low-RAM enemy module.
        ; Copying it once avoids frame-time GMC switching and preserves the
        ; resident MMU mapping used by the framebuffer.
        lda     #3
        sta     GMC_BANK
        ldx     #$C800
        ldy     #$0800
copy_enemy_runtime
        ldd     ,x++
        std     ,y++
        ldd     ,x++
        std     ,y++
        ldd     ,x++
        std     ,y++
        ldd     ,x++
        std     ,y++
        ldd     ,x++
        std     ,y++
        ldd     ,x++
        std     ,y++
        ldd     ,x++
        std     ,y++
        ldd     ,x++
        std     ,y++
        cmpx    #$D800
        blo     copy_enemy_runtime

        ; Synthesize the exact native Green-to-White perimeter program before
        ; the permanent $06B2 helper reclaims the tail of this relocated
        ; loader.  Bank 1 exposes the authored screen map and tile atlas.
        lda     #1
        sta     GMC_BANK
        lbsr    synthesize_perimeter_reset

        ; Physical pages $3C-$3F remain ROM-shadowed until SAM_ALLRAM.
        ; Preserve the generated audio stream's packed bytes in ordinary page $24 so
        ; audio can be expanded into page $3D after the all-RAM handoff.
 ; @audit-use {"id":"boot-audio-stream","symbol":"GMC_LZSS_AUDIO_OFFSET"}
        ldx     #GMC_LZSS_TABLE_RAM+GMC_LZSS_AUDIO_OFFSET
        lda     ,x
        sta     GMC_BANK
        lda     #AUDIO_STAGE_PAGE
        sta     PAR_EXEC+5
        ldu     2,x
        ldd     4,x
        std     BOOT_SRC_END
        ldy     #$A000
copy_staged_audio_stream
        lda     ,u+
        sta     ,y+
        cmpu    BOOT_SRC_END
        blo     copy_staged_audio_stream

        ; The indexed plan was saved before the enemy module reclaimed its
        ; relocated source tail; use it now to copy the sparse streams.
        ldx     #SPARSE_COPY_TABLE_RAM
        lda     #SPARSE_COPY_EARLY_SEGMENT_COUNT
        sta     BOOT_SEGMENTS
copy_sparse_segment
        lda     ,x+
        sta     GMC_BANK
        lda     ,x+
        cmpa    #$FF            ; $FF targets always-mapped low RAM directly
        beq     copy_sparse_destination_ready
        sta     PAR_EXEC+5
copy_sparse_destination_ready
        lbsr    copy_sparse_payload
        dec     BOOT_SEGMENTS
        bne     copy_sparse_segment
        bra     copy_sparse_early_done

copy_sparse_payload
        ldu     ,x++
        ldy     ,x++
        ldd     ,x++
        pshs    x
        tfr     d,x
        andb    #1
        beq     copy_sparse_word
        lda     ,u+
        sta     ,y+
        leax    -1,x
        cmpx    #0
        beq     copy_sparse_done
copy_sparse_word
        ; Eight-pair unroll keeps loop overhead outside the hot copy path.
        ; The tail handles counts below sixteen bytes and preserves odd sizes.
        cmpx    #16
        blo     copy_sparse_tail
        ldd     ,u++
        std     ,y++
        ldd     ,u++
        std     ,y++
        ldd     ,u++
        std     ,y++
        ldd     ,u++
        std     ,y++
        ldd     ,u++
        std     ,y++
        ldd     ,u++
        std     ,y++
        ldd     ,u++
        std     ,y++
        ldd     ,u++
        std     ,y++
        leax    -16,x
        beq     copy_sparse_done
        bra     copy_sparse_word
copy_sparse_tail
        tfr     x,d
        andb    #1
        beq     copy_sparse_tail_word
        lda     ,u+
        sta     ,y+
        leax    -1,x
        cmpx    #0
        beq     copy_sparse_done
copy_sparse_tail_word
        ldd     ,u++
        std     ,y++
        leax    -2,x
        cmpx    #0
        bne     copy_sparse_tail_word
copy_sparse_done
        puls    x
        rts
copy_sparse_early_done

        ; Expand all page-bounded FEAT-006 streams while cartridge ROM is
        ; still selected. Each descriptor names one source bank interval and
        ; one physical destination page; no runtime decompression remains.
        lbsr    decompress_gmc_streams

        ; Bank 1 contains the current 16 KiB runtime image. Stage its resident
        ; 8 KiB in ordinary RAM while the cartridge remains selected. Physical
        ; pages $3E/$3F are populated only after the all-RAM handoff below.
        lda     #RESIDENT_STAGE_PAGE
        sta     PAR_EXEC+5
        lda     #1
        sta     GMC_BANK
        ldx     #$C000
        ldy     #$A000
copy_resident
        ldd     ,x++
        std     ,y++
        ldd     ,x++
        std     ,y++
        ldd     ,x++
        std     ,y++
        ldd     ,x++
        std     ,y++
        ldd     ,x++
        std     ,y++
        ldd     ,x++
        std     ,y++
        ldd     ,x++
        std     ,y++
        ldd     ,x++
        std     ,y++
        cmpx    #$E000
        blo     copy_resident

        ; Stage the usable asset window. $FE00-$FFFF remains the forced-RAM/I/O
        ; area and is not cartridge payload.
        lda     #ASSET_STAGE_PAGE
        sta     PAR_EXEC+5
        ldx     #$E000
        ldy     #$A000
copy_assets
        ldd     ,x++
        std     ,y++
        ldd     ,x++
        std     ,y++
        ldd     ,x++
        std     ,y++
        ldd     ,x++
        std     ,y++
        ldd     ,x++
        std     ,y++
        ldd     ,x++
        std     ,y++
        ldd     ,x++
        std     ,y++
        ldd     ,x++
        std     ,y++
        cmpx    #$FE00
        blo     copy_assets

        ; Disconnect cartridge ROM, then publish the staged bank-1 bytes to
        ; their runtime pages. The loader executes from always-mapped low RAM.
        lda     #$34
        sta     SAM_FAST
        sta     SAM_ALLRAM

        lda     #RESIDENT_STAGE_PAGE
        sta     PAR_EXEC+5
        ldx     #$A000
        ldy     #$C000
copy_staged_resident
        ldd     ,x++
        std     ,y++
        ldd     ,x++
        std     ,y++
        ldd     ,x++
        std     ,y++
        ldd     ,x++
        std     ,y++
        ldd     ,x++
        std     ,y++
        ldd     ,x++
        std     ,y++
        ldd     ,x++
        std     ,y++
        ldd     ,x++
        std     ,y++
        cmpx    #$C000
        blo     copy_staged_resident

        lda     #ASSET_STAGE_PAGE
        sta     PAR_EXEC+5
        ldx     #$A000
        ldy     #$E000
copy_staged_assets
        ldd     ,x++
        std     ,y++
        ldd     ,x++
        std     ,y++
        ldd     ,x++
        std     ,y++
        ldd     ,x++
        std     ,y++
        ldd     ,x++
        std     ,y++
        ldd     ,x++
        std     ,y++
        ldd     ,x++
        std     ,y++
        ldd     ,x++
        std     ,y++
        cmpx    #$BE00
        blo     copy_staged_assets

        lbsr    decompress_staged_audio
boot_streams_retired
        ; No descriptor consumer remains; audio_init_impl may reuse overlap.
        lbsr    copy_late_sparse_segments

        ; Page $23 retains compressed title/attract data and phase tile patches.
        ; After all-RAM publication, expand it into presentation page $3C.
        lbsr    decompress_attract_surfaces
        ifne    HIGHSCORE_TEST_PROFILE
        lbsr    decompress_presentation_atlas
        endc

        lda     #$A5
        sta     BOOT_FLAG
        ifne COMPLETE_PROFILE
        ldd     #$3334
        std     PAR_EXEC+4
        lda     #%01101000      ; runtime audio will enable SCS when it writes
        sta     GIME_INIT0
        clra
        tfr     a,dp
boot_runtime_handoff
        jmp     GMC_RUNTIME_ENTRY
        else
        lda     #$34
        sta     PAR_EXEC+5
        ; Skip the two-byte DK cartridge header when entering the
        ; relocated runtime.
        jmp     $C002
        endc
copy_late_sparse_segments
        ; Audio has consumed page $24's staged source. Execute only from low RAM
        ; while briefly restoring GMC ROM visibility for the delayed copies.
        lda     #$34
        sta     SAM_FAST
        sta     SAM_CART
        lda     #SPARSE_COPY_LATE_SEGMENT_COUNT
        sta     BOOT_SEGMENTS
        tst     BOOT_SEGMENTS
        beq     copy_late_sparse_restore
        ldx     #SPARSE_COPY_TABLE_RAM+SPARSE_COPY_EARLY_SEGMENT_COUNT*SPARSE_COPY_SEGMENT_BYTES
copy_late_sparse_segment
        lda     ,x+
        sta     GMC_BANK
        lda     ,x+
        cmpa    #SPARSE_COPY_LATE_SELECTOR
        lbne    loader_fail
        lda     #AUXILIARY_STAGE_PAGE
        sta     PAR_EXEC+5
        lbsr    copy_sparse_payload
        dec     BOOT_SEGMENTS
        bne     copy_late_sparse_segment
copy_late_sparse_restore
        lda     #$34
        sta     SAM_FAST
        sta     SAM_ALLRAM
        rts

decompress_gmc_streams
        ldx     #GMC_LZSS_TABLE_RAM
 ; @audit-use {"id":"boot-audio-stream","symbol":"GMC_LZSS_AUDIO_OFFSET"}
        lda     GMC_LZSS_TABLE_RAM+GMC_LZSS_AUDIO_OFFSET
        pshs    a
        lda     #$FF
 ; @audit-use {"id":"boot-audio-stream","symbol":"GMC_LZSS_AUDIO_OFFSET"}
        sta     GMC_LZSS_TABLE_RAM+GMC_LZSS_AUDIO_OFFSET
        lda     #GMC_LZSS_STREAM_COUNT-1
        sta     BOOT_STREAMS
        lbsr    dgs_descriptor
        puls    a
 ; @audit-use {"id":"boot-audio-stream","symbol":"GMC_LZSS_AUDIO_OFFSET"}
        sta     GMC_LZSS_TABLE_RAM+GMC_LZSS_AUDIO_OFFSET
        rts
decompress_staged_audio
        lda     #AUDIO_STAGE_PAGE
        sta     PAR_EXEC+4
 ; @audit-use {"id":"boot-audio-stream","symbol":"GMC_LZSS_AUDIO_OFFSET"}
        ldx     #GMC_LZSS_TABLE_RAM+GMC_LZSS_AUDIO_OFFSET
        ldd     #$8000
        std     2,x
        addd    10,x
        std     4,x
        lda     #1
        sta     BOOT_STREAMS
dgs_descriptor
        tst     BOOT_STREAMS
        lbeq    dgs_terminator
        lda     ,x
        cmpa    #$FF
        lbeq    loader_fail
        sta     GMC_BANK
        lda     1,x
        sta     PAR_EXEC+5
        ldu     2,x
        ldd     4,x
        std     BOOT_SRC_END
        ldy     6,x
        ldd     8,x
        std     BOOT_DEST_END
        leax    GMC_LZSS_DESCRIPTOR_BYTES,x
        stx     BOOT_DESC_PTR
dgs_flags
        cmpy    BOOT_DEST_END
        beq     dgs_stream_done
        cmpu    BOOT_SRC_END
        lbhs    loader_fail
        lda     ,u+
        sta     BOOT_LZ_FLAGS
        lda     #8
        sta     BOOT_LZ_BITS
dgs_token
        lsr     BOOT_LZ_FLAGS
        bcc     dgs_match
        cmpu    BOOT_SRC_END
        lbhs    loader_fail
        lda     ,u+
        sta     ,y+
        bra     dgs_next
dgs_match
        cmpu    BOOT_SRC_END
        lbhs    loader_fail
        ldd     ,u++
        pshs    b
        lsra
        rorb
        lsra
        rorb
        lsra
        rorb
        lsra
        rorb
        cmpd    #0
        lbeq    loader_fail
        std     BOOT_LZ_OFFSET
        tfr     y,d
        subd    BOOT_LZ_OFFSET
        tfr     d,x
        puls    b
        andb    #$0F
        addb    #3
dgs_match_byte
        lda     ,x+
        sta     ,y+
        cmpy    BOOT_DEST_END
        bne     dgs_match_more
        cmpb    #1
        lbne    loader_fail
dgs_match_more
        decb
        bne     dgs_match_byte
dgs_next
        cmpy    BOOT_DEST_END
        lbhi    loader_fail
        beq     dgs_stream_done
        dec     BOOT_LZ_BITS
        bne     dgs_token
        bra     dgs_flags
dgs_stream_done
        cmpu    BOOT_SRC_END
        lbne    loader_fail
        ldx     BOOT_DESC_PTR
        dec     BOOT_STREAMS
        lbra    dgs_descriptor
dgs_terminator
        lda     ,x
        cmpa    #$FF
        lbne    loader_fail
        rts

decompress_attract_surfaces
        lda     #$3C
        sta     PAR_EXEC+4
        lda     #PRESENTATION_ATTRACT_BUNDLE_PAGE
        sta     PAR_EXEC+5
        ldu     #PRESENTATION_ATTRACT_BUNDLE_ADDRESS
        ldy     #$8000
das_flags
        lda     ,u+
        sta     BOOT_LZ_FLAGS
        lda     #8
        sta     BOOT_LZ_BITS
das_token
        lsr     BOOT_LZ_FLAGS
        bcc     das_match
        lda     ,u+
        sta     ,y+
        bra     das_next
das_match
        ldd     ,u++
        pshs    b
        lsra
        rorb
        lsra
        rorb
        lsra
        rorb
        lsra
        rorb
        std     BOOT_LZ_OFFSET
        tfr     y,d
        subd    BOOT_LZ_OFFSET
        tfr     d,x
        puls    b
        andb    #$0F
        addb    #3
das_match_byte
        lda     ,x+
        sta     ,y+
        decb
        bne     das_match_byte
das_next
        cmpy    #$9F80          ; twenty-one surfaces per phase, three phases
        beq     das_done
        dec     BOOT_LZ_BITS
        bne     das_token
        bra     das_flags
das_done
        ldb     #48            ; twenty-one destinations and three phase pointers
das_metadata_byte
        lda     ,u+
        sta     ,y+
        decb
        bne     das_metadata_byte
        rts

        ifne    HIGHSCORE_TEST_PROFILE
decompress_presentation_atlas
        ; Read the compressed atlas from page $3A through PAR4, and expand
        ; it into page $3B through PAR5. Runtime tile reads use the latter
        ; page at the atlas offset $2000.
        lda     #PRESENTATION_COLD_PAGE
        sta     PAR_EXEC+4
        lda     #PRESENTATION_COLD_PAGE+1
        sta     PAR_EXEC+5
        ldu     #$8000+PRESENTATION_TILE_ATLAS_SOURCE_OFFSET
        ldy     #$A000
dpa_flags
        lda     ,u+
        sta     BOOT_LZ_FLAGS
        lda     #8
        sta     BOOT_LZ_BITS
dpa_token
        lsr     BOOT_LZ_FLAGS
        bcc     dpa_match
        lda     ,u+
        sta     ,y+
        bra     dpa_next
dpa_match
        ldd     ,u++
        pshs    b
        lsra
        rorb
        lsra
        rorb
        lsra
        rorb
        lsra
        rorb
        std     BOOT_LZ_OFFSET
        tfr     y,d
        subd    BOOT_LZ_OFFSET
        tfr     d,x
        puls    b
        andb    #$0F
        addb    #3
dpa_match_byte
        lda     ,x+
        sta     ,y+
        decb
        bne     dpa_match_byte
dpa_next
        cmpy    #$A000+PRESENTATION_TILE_ATLAS_EXPANDED_BYTES
        beq     dpa_done
        dec     BOOT_LZ_BITS
        bne     dpa_token
        bra     dpa_flags
dpa_done
        rts
        endc

loader_fail
        clr     BOOT_PROOF
        bra     loader_fail

synthesize_perimeter_reset
        lda     #$20
        sta     PAR_EXEC+5
        ldu     #$A000
        clr     BOOT_BOX
spr_box
        lda     BOOT_BOX
        cmpa    #12
        blo     spr_top
        cmpa    #35
        blo     spr_right
        cmpa    #58
        blo     spr_bottom
        cmpa    #80
        blo     spr_left
        suba    #80
        sta     BOOT_CELL_X
        clr     BOOT_CELL_Y
        bra     spr_cell
spr_top
        adda    #12
        sta     BOOT_CELL_X
        clr     BOOT_CELL_Y
        bra     spr_cell
spr_right
        lda     #23
        sta     BOOT_CELL_X
        lda     BOOT_BOX
        suba    #11
        sta     BOOT_CELL_Y
        bra     spr_cell
spr_bottom
        lda     #57
        suba    BOOT_BOX
        sta     BOOT_CELL_X
        lda     #23
        sta     BOOT_CELL_Y
        bra     spr_cell
spr_left
        clr     BOOT_CELL_X
        lda     #80
        suba    BOOT_BOX
        sta     BOOT_CELL_Y
spr_cell
        ; D = screen-map index y*40+x+8; PAR7 retains the authored assets.
        lda     BOOT_CELL_Y
        ldb     #40
        mul
        addb    BOOT_CELL_X
        adca    #0
        addb    #8
        adca    #0
        ldx     #PERIMETER_SCREEN_MAP
        leax    d,x
        ldb     ,x
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
        ldx     #PERIMETER_SCREEN_TILES
        leay    d,x
        sty     BOOT_TILE_PTR

        ; BOOT_DEST = $2000 + ((y*8)*160) + ((x+8)*4).
        ; y*5 shifted into D's high byte is y*5*256 = y*8*160.
        lda     BOOT_CELL_Y
        ldb     #5
        mul
        tfr     b,a
        clrb
        addd    #$2000
        std     BOOT_DEST
        lda     BOOT_CELL_X
        adda    #8
        ldb     #4
        mul
        addd    BOOT_DEST
        std     BOOT_DEST
        ldy     BOOT_TILE_PTR
        lda     #8
        sta     BOOT_ROW
spr_row
        lda     #4
        sta     BOOT_COL
spr_byte
        lda     ,y+
        bsr     spr_byte_changed
        bne     spr_advance_one
        pshs    b               ; retain first changed byte while peeking
        lda     BOOT_COL
        cmpa    #1
        beq     spr_single
        lda     ,y
        bsr     spr_byte_changed
        bne     spr_single
        ; Two adjacent changed bytes use LDD #value16 / STD address.
        lda     #$CC
        sta     ,u+
        puls    a
        sta     ,u+
        stb     ,u+
        lda     #$FD
        sta     ,u+
        ldd     BOOT_DEST
        std     ,u++
        leay    1,y
        addd    #2
        std     BOOT_DEST
        dec     BOOT_COL
        dec     BOOT_COL
        bne     spr_byte
        bra     spr_next_row
spr_single
        lda     #$86
        sta     ,u+
        puls    a
        sta     ,u+
        lda     #$B7
        sta     ,u+
        ldd     BOOT_DEST
        std     ,u++
spr_advance_one
        ldd     BOOT_DEST
        addd    #1
        std     BOOT_DEST
        dec     BOOT_COL
        bne     spr_byte
spr_next_row
        ldd     BOOT_DEST
        addd    #156
        std     BOOT_DEST
        dec     BOOT_ROW
        bne     spr_row
        inc     BOOT_BOX
        lda     BOOT_BOX
        cmpa    #92
        lblo    spr_box
        lda     #$39
        sta     ,u+
        cmpu    #$C000
        lbhi    loader_fail
        rts

; A = packed tile byte. Return Z=1 when either nibble uses authored White 6;
; B retains the original byte for native-program emission.
spr_byte_changed
        tfr     a,b
        anda    #$F0
        cmpa    #$60
        beq     spr_byte_changed_done
        tfr     b,a
        anda    #$0F
        cmpa    #$06
spr_byte_changed_done
        rts

        ifne    HIGHSCORE_TEST_PROFILE
sparse_copy_table_start
        endc
        include "ladybug-sparse-loader.inc"
GMC_LZSS_STREAM_TABLE_BYTES equ gmc_lzss_stream_end-gmc_lzss_stream_table+1
        ifne    HIGHSCORE_TEST_PROFILE
sparse_copy_table_end
        endc
        include "ladybug-perimeter-boot.inc"
loader_end

        ifne COMPLETE_PROFILE
        setdp   $00
boot_loading_video
        ; Disable and acknowledge legacy PIA interrupts before enabling VBORD.
        clr     $FF01
        clr     $FF03
        clr     $FF21
        clr     $FF23
        lda     $FF00
        lda     $FF02
        lda     $FF20
        lda     $FF22
        clr     GIME_FIRQEN

        lda     #$80
        sta     GIME_VMODE
        ldd     #$C000
boot_loading_scanout
        std     GIME_VOFF1
        clr     GIME_HOFF
        ldd     #$3031
        std     PAR_EXEC+1
        ldd     #$3233
        std     PAR_EXEC+3
        ldx     #boot_loading_palette
        ldy     #PAL_BASE
boot_loading_palette_copy
        lda     ,x+
        sta     ,y+
        cmpy    #PAL_BASE+16
        blo     boot_loading_palette_copy

        ldx     #$2000
        ldd     #0
boot_loading_clear
        std     ,x++
        cmpx    #$9800
        blo     boot_loading_clear
        ldx     #boot_loading_asset
        ldy     #$57E0
boot_loading_text_row
        lda     #14
        pshs    a
boot_loading_text_word
        ldd     ,x++
boot_loading_text_store
        std     ,y++
        dec     ,s
        bne     boot_loading_text_word
        leas    1,s
        cmpx    #boot_loading_dot
        beq     boot_loading_install_irq
        leay    132,y
        bra     boot_loading_text_row

boot_loading_install_irq
        ldd     ,x              ; two stored dot bytes, one for each row
        std     BOOT_LOADING_DOT
        ldx     #boot_loading_irq
        ldy     #BOOT_LOADING_IRQ
boot_loading_irq_copy
        lda     ,x+
        sta     ,y+
        cmpx    #boot_loading_irq_end
        blo     boot_loading_irq_copy
        ldd     #$000F          ; runtime IRQ readiness and initial 15-frame count
        std     BOOT_LOADING_READY
        clr     BOOT_LOADING_OFFSET
        ldd     #$7EFE          ; JMP $FE00
        std     JT_IRQ
        clr     JT_IRQ+2
        clra
        tfr     a,dp
        clrb
        std     <$B0            ; PRES_TIMER starts at actor phase zero
        lda     #3              ; PRES_HOLD_HYDRATE
        sta     <$D4
        lda     #$FF
        sta     <$A6            ; ensure first Attract load initializes its menu
        sta     <BOOT_LOADING_OWNER

        lda     #8
        sta     GIME_IRQEN
        lda     GIME_IRQEN
boot_loading_wait_vbord
        lda     GIME_IRQEN
        bita    #8
        beq     boot_loading_wait_vbord
        lda     #$1E
boot_loading_unblank
        sta     GIME_VRES
        andcc   #$EF
        rts

; Copied verbatim to $FE00. Internal branches are position independent.
boot_loading_irq
        tst     BOOT_LOADING_READY
        beq     boot_loading_ack
        jsr     FB_MODULE_IRQ   ; acknowledges VBORD and commits PENDING
        tst     <$8F            ; FRONT becomes B at the first Attract commit
        bne     boot_loading_irq_done
        bra     boot_loading_tick
boot_loading_ack
        lda     GIME_IRQEN
boot_loading_tick
        dec     BOOT_LOADING_TICKS
        bne     boot_loading_irq_done
        lda     #15
        sta     BOOT_LOADING_TICKS
boot_loading_irq_save_pars
        ldd     PAR_EXEC+2
        pshs    d
        ldd     #$3132
        std     PAR_EXEC+2
        ldx     #$5F61
        ldb     BOOT_LOADING_OFFSET
        cmpb    #28
        beq     boot_loading_dots_clear
        abx
        addb    #4
        stb     BOOT_LOADING_OFFSET
        ldd     BOOT_LOADING_DOT
boot_loading_dot_store
        sta     ,x
boot_loading_dot_store_bottom
        stb     160,x
        bra     boot_loading_dots_done
boot_loading_dots_clear
        clr     BOOT_LOADING_OFFSET
        clra
boot_loading_dot_clear
        sta     ,x
boot_loading_dot_clear_bottom
        sta     160,x
        leax    4,x
        cmpx    #$5F7D
        blo     boot_loading_dot_clear
boot_loading_dots_done
        puls    d
boot_loading_irq_restore_pars
        std     PAR_EXEC+2
boot_loading_irq_done
        rti

        zmb BOOT_LOADING_HYDRATE-BOOT_LOADING_IRQ-(*-boot_loading_irq)
boot_loading_hydrate
        tst     <$8F            ; A is still FRONT until the first commit
        bne     boot_loading_hydrate_done
        clr     <$90            ; prepare the next pass with A mapped
        clra                    ; PRESENTATION_MAP_ATTRACT
        jsr     GMC_ATTRACT_RESTART
        orcc    #$10
        lda     #1
        sta     <$90            ; publish B before rendering the A pass
        sta     <$91
        andcc   #$EF
        rts
boot_loading_hydrate_done
        orcc    #$10
        ldd     #GMC_RUNTIME_IRQ
        std     JT_IRQ+1
        clr     <BOOT_LOADING_OWNER
        clr     <$D4
        clr     <$98
        jmp     GMC_ATTRACT_PUBLISH
boot_loading_irq_end
        ifgt (boot_loading_irq_end-boot_loading_irq)-(BOOT_LOADING_READY-BOOT_LOADING_IRQ)
        error "loading IRQ or hydration code overlaps loading state"
        endc

boot_loading_asset
        includebin "ladybug-loading.bin"
boot_loading_dot     equ boot_loading_asset+168
boot_loading_palette equ boot_loading_dot+2
boot_loading_asset_end
        ifne boot_loading_asset_end-boot_loading_asset-186
        error "loading asset must be 186 bytes"
        endc
        endc
boot_image_end

        ifgt GMC_LZSS_STREAM_TABLE_BYTES-127
        error "boot descriptor table exceeds $1800-$187E"
        endc
        ifne GMC_LZSS_AUDIO_INDEX-(GMC_LZSS_STREAM_COUNT-1)
        error "audio descriptor must terminate the stream list"
        endc

        end
