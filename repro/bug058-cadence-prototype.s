; BUG-058 approved fitting experiment. NOT an installed runtime module.
; Imports are regenerated from the same assembled resident/enemy pair.
; PAR5 must remain $34 throughout. No callee here remaps PAR5.
        pragma nodollarlocal,6809
        include "cadence-imports.inc"
CAD_RECORDS    equ $BC04
CAD_FRAMES     equ $BC24
CAD_OWNER      equ $BC28
CAD_SELECT     equ $BC30
CAD_MODE       equ $BC35
CAD_PHASE      equ $BC36
CAD_SEQ        equ $BC37
CAD_CHANGED    equ $BC39
CAD_INDEX      equ $BC3A
CAD_OFFSET     equ $BC3B
CAD_RECTS      equ $BC3C
        org $BC50

; Same owner/player/ring publication as the old low-RAM routine, but records
; and frame IDs describe the frozen poses actually composed into this owner.
cadence_publish
        jsr framebuffer_back_meta
        lda #FBM_VALID
        sta FBM_STATE,u
        clr FBM_DAMAGE,u
        lda PLAYER_BG_VALID
        sta FBM_PLAYER_VALID,u
        beq cp_no_rows
        lda PLAYER_VISIBLE_ROWS
        sta FBM_PLAYER_RESERVED,u
        bra cp_rows_done
cp_no_rows
        clr FBM_PLAYER_RESERVED,u
cp_rows_done
        ldd PLAYER_FB
        std FBM_PLAYER_FB,u
        leau FBM_ENEMIES,u
        ldx #CAD_RECORDS
        ldy #16
cp_records
        ldd ,x++
        std ,u++
        leay -1,y
        bne cp_records
        clra
        clrb
        std ,u
        std 2,u
        ldd ENEMY_BG_RING
        std 4,u
        ldd ENEMY_BG_RING+2
        std 6,u
        bsr cadence_owner_frames
        ldd CAD_FRAMES
        std ,y
        ldd CAD_FRAMES+2
        std 2,y
        rts

cadence_owner_frames
        ldb FB_BACK_ID
        lslb
        lslb
        ldy #CAD_OWNER
        leay b,y
        rts

; Reset is called after bootstrap restores PAR5=$34, before histories clone.
cadence_reset
        clr CAD_MODE
        ldd #$FFFF
        std CAD_OWNER
        std CAD_OWNER+2
        std CAD_OWNER+4
        std CAD_OWNER+6
        rts

; Planner runs after prepare and clearing ENEMY_CAPTURE_DIRTY, before colour
; preparation/restoration. Current/pending colour already forces full capture:
; later logical-position colour tests cannot miss an older frozen footprint.
; The caller must never invoke it twice for the same rendered worklist.
cadence_plan
        tst FB_INIT_STATE
        lbeq cplan_legacy
        tst INITIAL_ENTRY_STATE
        lbne cplan_legacy
        tst DEATH_STATE
        lbne cplan_legacy
        tst PICKUP_TIMER
        lbne cplan_legacy
        lda RENDER_FLAGS
        bita #RF_STAGE|RF_DEATH
        lbne cplan_legacy
        lda ENEMY_ACTIVE
        cmpa #4
        lbne cplan_legacy
        ldx #ENEMY_TABLE
        ldb #4
cplan_eligible
        tst ,x
        lbeq cplan_legacy
        tst 6,x
        lbeq cplan_legacy
        leax 8,x
        decb
        bne cplan_eligible
        tst CAD_MODE
        beq cplan_seed
        ldd FB_COMMIT_SEQ
        subd CAD_SEQ
        lbeq cplan_return      ; retry/pending publication retains exact latch
        cmpd #1
        bne cplan_seed         ; reset/discontinuous publication cannot reuse
        lda CAD_PHASE
        inca
        anda #3
        sta CAD_PHASE
        bita #1
        bne cplan_latched
        lbsr cadence_latch
        bra cplan_latched
cplan_seed
        clr CAD_PHASE
        clr CAD_MODE
        lbsr cadence_latch     ; mode zero copies all four, including frame IDs
        inc CAD_MODE
        ldd FB_COMMIT_SEQ
        std CAD_SEQ
        lbra cadence_all
cplan_latched
        ldd FB_COMMIT_SEQ
        std CAD_SEQ
        lda ENEMY_OLD_VALID
        cmpa #15
        lbne cadence_dirty
        tst PLAYER_BG_VALID
        lbeq cadence_dirty
        ldx #RENDER_FLAGS
        lbsr cadence_damage
        lbne cadence_dirty
        jsr framebuffer_back_meta
        tst FBM_DAMAGE,u
        beq cplan_no_pending
        leax FBM_PENDING_INTENTS,u
        lbsr cadence_damage
        lbne cadence_dirty
cplan_no_pending
        leau FBM_ENEMIES,u
        ldx #CAD_RECORDS
        ldy #CAD_RECTS
        lda #4
        sta ENEMY_WORK
cplan_boxes
        pshs x,y,u
        ldd 1,u
        ldy 1,x
        ldx 2,s
        lbsr cadence_bounds
        puls x,y,u
        lbsr cadence_difference
        leax 8,x
        leau 8,u
        leay 4,y
        dec ENEMY_WORK
        bne cplan_boxes
        ldx #CAD_RECTS+16
        ldd PLAYER_OLD_FB
        ldy PLAYER_FB
        lbsr cadence_bounds
        lbsr cadence_closure
cplan_return
        rts
cplan_legacy
        clr CAD_MODE
        clr CAD_PHASE
        lbsr cadence_latch
        ldd FB_COMMIT_SEQ
        std CAD_SEQ
cadence_all
        lda #1
        sta CAD_SELECT+1
        sta CAD_SELECT+2
        sta CAD_SELECT+3
        sta CAD_SELECT+4
        rts
cadence_dirty
        lda #$FF
        sta ENEMY_CAPTURE_DIRTY
        bra cadence_all

; Current or queued structural writes require full actor removal. HUD/timer
; work is outside actor footprints; popup/death use the legacy eligibility path.
cadence_damage
        lda ,x
        anda #RF_ENTITIES|RF_DOT|RF_STAGE
        bne cd_done
        lda 1,x
        anda #RF2_COLOUR
        bne cd_done
        lda 8,x
        anda #ERF_INIT|ERF_ZONE_REFRESH|ERF_NEST|ERF_NEST_ANIM
        bne cd_done
        lda 9,x
        ora 11,x
cd_done
        rts

; Fixed pairs slots (0,2)/(1,3), selected once per two publications.
cadence_latch
        ldx #ENEMY_TABLE
        ldy #CAD_RECORDS
        lda #4
        sta ENEMY_WORK
cl_loop
        tst CAD_MODE
        beq cl_copy
        lda CAD_PHASE
        lsra
        eora ENEMY_WORK
        bita #1
        bne cl_next
cl_copy
        ldd ,x
        std ,y
        ldd 2,x
        std 2,y
        ldd 4,x
        std 4,y
        ldd 6,x
        std 6,y
        pshs x,y
        ldb 7,x
        jsr enemy_frame_number
        ldb ENEMY_WORK
        decb
        ldy #CAD_FRAMES
        sta b,y
        puls x,y
cl_next
        leax 8,x
        leay 8,y
        dec ENEMY_WORK
        bne cl_loop
        rts

; Set this slot's selection byte if any displayed record or cached frame
; differs from the actual BACK owner. Preserve X/Y/U for the rectangle loop.
cadence_difference
        pshs x,y,u
        ldy #8
cdiff_loop
        lda ,x+
        cmpa ,u+
        bne cdiff_yes
        leay -1,y
        bne cdiff_loop
        lbsr cadence_owner_frames
        ldb ENEMY_WORK
        decb
        lda b,y
        ldy #CAD_FRAMES
        cmpa b,y
        bne cdiff_yes
        clra
        bra cdiff_store
cdiff_yes
        lda #1
cdiff_store
        ldb ENEMY_WORK
        ldy #CAD_SELECT
        sta b,y
        puls x,y,u,pc

; D and Y are old/new framebuffer pointers. X owns four bytes:
; xmin,ymin,xmax-exclusive,ymax-exclusive. Coordinates are bytes/scanlines.
; Exact pointer division avoids assuming that semantic cells imply a position.
cadence_bounds
        pshs d,y
        ldd #$FFFF
        std ,x
        clra
        clrb
        std 2,x
        puls d
        bsr cadence_expand
        puls d
cadence_expand
        subd #$2000
        pshs d
        ldy #$5000           ; 160 * 128: eight bounded binary division steps
        pshs y
        clr ,-s
        lda #8
        pshs a
ce_divide
        lsl 1,s
        ldd 4,s
        subd 2,s
        blo ce_no_subtract
        std 4,s
        inc 1,s
ce_no_subtract
        lsr 2,s
        ror 3,s
        dec ,s
        bne ce_divide
        lda 1,s
        ldb 5,s
        leas 6,s
        cmpa 1,x
        bhs ce_ymin
        sta 1,x
ce_ymin
        adda #16
        cmpa 3,x
        bls ce_ymax
        sta 3,x
ce_ymax
        cmpb ,x
        bhs ce_xmin
        stb ,x
ce_xmin
        addb #8
        cmpb 2,x
        bls ce_done
        stb 2,x
ce_done
        rts

; X/Y rectangles intersect iff C=1. Only A/CC are clobbered.
cadence_intersect
        lda ,x
        cmpa 2,y
        bhs ci_no
        lda ,y
        cmpa 2,x
        bhs ci_no
        lda 1,x
        cmpa 3,y
        bhs ci_no
        lda 1,y
        cmpa 3,x
        bhs ci_no
        orcc #1
        rts
ci_no
        andcc #$FE
        rts

; Seed with the player old/new union. Then expand until no retained enemy
; intersects a selected old/new union. Unselected desired and old boxes match.
cadence_closure
        ldx #CAD_RECTS
        ldy #CAD_RECTS+16
        ldu #CAD_SELECT
        ldb #4
cclose_player
        tst b,u
        bne cclose_player_next
        bsr cadence_intersect
        bcc cclose_player_next
        inc b,u
cclose_player_next
        leax 4,x
        decb
        bne cclose_player
cclose_again
        clr CAD_CHANGED
        lda #4
        sta ENEMY_WORK
        ldy #CAD_RECTS
cclose_outer
        ldb ENEMY_WORK
        tst b,u
        beq cclose_outer_next
        ldx #CAD_RECTS
        ldb #4
cclose_inner
        tst b,u
        bne cclose_inner_next
        bsr cadence_intersect
        bcc cclose_inner_next
        inc b,u
        inc CAD_CHANGED
cclose_inner_next
        leax 4,x
        decb
        bne cclose_inner
cclose_outer_next
        leay 4,y
        dec ENEMY_WORK
        bne cclose_outer
        tst CAD_CHANGED
        bne cclose_again
        rts
cadence_end
