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
; DOC-002 source-contract mirror contract boot_entry profile=boot: Establish bootstrap mappings and transfer control into the low-RAM loader.
; DOC-002 source-contract mirror contract decompress_attract_surfaces profile=boot: Decompress attract surfaces.
; DOC-002 source-contract mirror contract spr_byte_changed profile=boot: Test whether synthesis changed the current perimeter-reset output byte.
; DOC-002 source-contract mirror contract synthesize_perimeter_reset profile=boot: Synthesize perimeter reset.
; DOC-002 source-contract mirror ends.

GMC_BANK    equ $FF50
GIME_INIT0  equ $FF90
GIME_MMU    equ $FF91
PAR_EXEC    equ $FFA0
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
LOADER_RAM  equ $0300
RESIDENT_STAGE_PAGE equ $21
ASSET_STAGE_PAGE equ $22
PRESENTATION_NAME_ENTRY_DATA equ 0

        ifne    HIGHSCORE_TEST_PROFILE
        include "ladybug_presentation.inc"
        endc

        org $C000
        fcc "DK"

boot_entry
        orcc    #$50
        lds     #$1FFE
        clr     GIME_MMU
        lda     #$38
        sta     PAR_EXEC
        lda     #$3E
        sta     PAR_EXEC+5
        sta     PAR_EXEC+6
        lda     #$3F
        sta     PAR_EXEC+7
        lda     #%01101100      ; MMU + force FExx + SCS for GMC $FF50
        sta     GIME_INIT0
        sta     SAM_FAST        ; run the boot copy at the normal 1.78 MHz rate
        sta     SAM_CART        ; BASIC autorun may leave TY=1; expose GMC ROM
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

        ; Copy the indexed sparse enemy/player streams into physical pages
        ; $35-$37 and $39 using the generated fragmented-bank plan.
        leax    sparse_copy_table,pcr
        ifne    HIGHSCORE_TEST_PROFILE
        ldy     #SPARSE_COPY_TABLE_RAM
        ldu     #SPARSE_COPY_TABLE_BYTES
copy_sparse_table
        lda     ,x+
        sta     ,y+
        leau    -1,u
        cmpu    #0
        bne     copy_sparse_table
        ldx     #SPARSE_COPY_TABLE_RAM
        endc
        lda     #SPARSE_COPY_SEGMENT_COUNT
        sta     BOOT_SEGMENTS
copy_sparse_segment
        lda     ,x+
        sta     GMC_BANK
        lda     ,x+
        cmpa    #$FF            ; $FF targets always-mapped low RAM directly
        beq     copy_sparse_destination_ready
        sta     PAR_EXEC+5
copy_sparse_destination_ready
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
        dec     BOOT_SEGMENTS
        bne     copy_sparse_segment

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

        ; Synthesize the exact native Green-to-White perimeter program from
        ; the authored screen map and tile atlas now visible through PAR7.
        ; PAR5 is changed only for the generated destination page $20.
        ; Keep GMC bank 1 selected so PAR7 still exposes the authored assets.
        ; The loader itself executes from its relocated low-RAM copy.
        lbsr    synthesize_perimeter_reset

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

        ; Page $23 stages the compressed bundle while cartridge ROM is selected.
        ; After all-RAM publication, expand it into presentation page $3C.
        lbsr    decompress_attract_surfaces
        ifne    HIGHSCORE_TEST_PROFILE
        lbsr    decompress_presentation_atlas
        endc

        lda     #$A5
        sta     BOOT_FLAG
        lda     #$34
        sta     PAR_EXEC+5
        ; Skip the two-byte DK cartridge header when entering the
        ; relocated runtime.
        jmp     $C002

decompress_attract_surfaces
        lda     #$3C
        sta     PAR_EXEC+4
        lda     #$23
        sta     PAR_EXEC+5
        ldu     #$A000
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
        cmpy    #$8A80
        beq     das_done
        dec     BOOT_LZ_BITS
        bne     das_token
        bra     das_flags
das_done
        ldb     #20
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
        ifne    HIGHSCORE_TEST_PROFILE
sparse_copy_table_end
        endc
        include "ladybug-perimeter-boot.inc"
loader_end

        end
