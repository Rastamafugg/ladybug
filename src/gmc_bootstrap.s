; Ladybug GMC bank loader. Bank 0 executes here, then this routine runs from
; low RAM while selecting bank 1 and copying the runtime into physical RAM.

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
LOADER_RAM  equ $0300

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
        cmpx    #$D800
        blo     copy_enemy_runtime

        ; Copy the indexed sparse enemy/player streams into physical pages
        ; $35-$37 and $39 using the generated fragmented-bank plan.
        leax    sparse_copy_table,pcr
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
copy_sparse_bytes
        lda     ,u+
        sta     ,y+
        leax    -1,x
        bne     copy_sparse_bytes
        puls    x
        dec     BOOT_SEGMENTS
        bne     copy_sparse_segment

        ; Mirror the sparse indexes into always-mapped PAR0 low RAM. Runtime
        ; resolution then maps only the selected payload page.
        lda     #SPARSE_ENEMY_PAYLOAD_PAGE
        sta     PAR_EXEC+5
        ldx     #$A000
        ldy     #SPARSE_ENEMY_INDEX_ADDR
        ldu     #SPARSE_ENEMY_INDEX_BYTES/2
copy_enemy_sparse_index
        ldd     ,x++
        std     ,y++
        leau    -1,u
        cmpu    #0
        bne     copy_enemy_sparse_index

        lda     #SPARSE_PLAYER_PAYLOAD_PAGE
        sta     PAR_EXEC+5
        ldx     #$A000
        ldy     #SPARSE_PLAYER_INDEX_ADDR
        ldu     #SPARSE_PLAYER_INDEX_BYTES/2
copy_player_sparse_index
        ldd     ,x++
        std     ,y++
        leau    -1,u
        cmpu    #0
        bne     copy_player_sparse_index

        ; Bank 1 contains the current 16 KiB runtime image. Copy its resident
        ; 8 KiB through PAR5 to phys $3E.
        lda     #$3E
        sta     PAR_EXEC+5
        lda     #1
        sta     GMC_BANK
        ldx     #$C000
        ldy     #$A000
copy_resident
        ldd     ,x++
        std     ,y++
        cmpx    #$E000
        blo     copy_resident

        ; Copy the usable asset window to phys $3F. $FE00-$FFFF remains the
        ; forced-RAM/I/O area and is not cartridge payload.
        lda     #$3F
        sta     PAR_EXEC+5
        ldx     #$E000
        ldy     #$A000
copy_assets
        ldd     ,x++
        std     ,y++
        cmpx    #$FE00
        blo     copy_assets

        lda     #$A5
        sta     BOOT_FLAG
        lda     #$34
        sta     PAR_EXEC+5
        sta     SAM_FAST
        sta     SAM_ALLRAM
        jmp     $C000

loader_fail
        clr     BOOT_PROOF
        bra     loader_fail

        include "ladybug-sparse-loader.inc"
loader_end

        end
