; BUG-086 isolated fit candidate: helpers staged in physical page $34.
; Runtime callers enter only while PAR5 maps page $34.
; The cache guard, normal selector and preview packer share the gameplay page.
; The frame selector keeps the enemy module below its fixed pre-LUT bound.

ENEMY_ANIM equ $0054
ENEMY_WORK equ $005D
STAGE equ $0024
STAGE_SOURCE equ $0066
ENEMY_TABLE equ $A470
ENEMY_NORMAL_CURSOR equ $A89D
ENEMY_PENDING_TYPE equ $A89E
ENEMY_CACHE_TYPE equ $A89F
ENEMY_MODULE_BUILD_CACHE equ $0824

        org     $A8A0

efn_cache_guard
        cmpa    ENEMY_CACHE_TYPE
        beq     efn_cache_done
        sta     ENEMY_CACHE_TYPE
        jsr     ENEMY_MODULE_BUILD_CACHE
efn_cache_done
        rts

efn_normal
        lda     STAGE
        deca
        cmpa    #8
        blo     efn_normal_done
        anda    #7
        cmpa    #5
        blo     efn_normal_base
        suba    #5
efn_normal_base
        ldb     ENEMY_NORMAL_CURSOR
        andb    #3
        pshs    b
        adda    ,s+
efn_normal_done
        rts

efn_preview
        lda     ENEMY_PENDING_TYPE
        bpl     efn_preview_pack
        lbsr    efn_normal
efn_preview_pack
        lsla
        lsla
        lsla
        lsla
        rts

; Return the indexed sparse frame number in A. B is N/E/S/W. Parts 1-8 use
; one type each; later parts rotate four adjacent types across active records.
enemy_frame_number
        cmpb    #4
        blo     efn_direction_ready
        clrb
efn_direction_ready
        lslb
        lslb
        orb     ENEMY_ANIM
        stb     STAGE_SOURCE
        lda     #4
        suba    ENEMY_WORK
        cmpa    #4
        bhs     efn_dormant
        lsla
        lsla
        lsla
        ldu     #ENEMY_TABLE
        lda     a,u
        anda    #$F0
        bra     efn_finish
efn_dormant
        lbsr    efn_preview
efn_finish
        ora     STAGE_SOURCE
        rts

enemy_page34_end
        end
