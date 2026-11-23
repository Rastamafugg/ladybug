; DOC-002 source-contract mirror begins. Canonical definitions:
; wiki/internal/implementation/routine-catalog.html
; DOC-002 source-contract mirror profile copy Inputs: Source and destination identities, bounded count or stream metadata, and any required mapped page
; DOC-002 source-contract mirror profile copy Outputs: Copied, decoded, merged, cached, or addressed data plus caller-visible pointer progress
; DOC-002 source-contract mirror profile copy Clobbers: A, B, D, X, Y, U, and condition codes unless a narrower source-local header is present
; DOC-002 source-contract mirror profile copy Reads: The declared source stream, table, framebuffer rows, or metadata record
; DOC-002 source-contract mirror profile copy Writes: Only the declared bounded destination record, cache, row range, or scratch fields
; DOC-002 source-contract mirror profile copy Side effects: May temporarily map a required GIME page while moving or decoding data
; DOC-002 source-contract mirror profile copy Invariants: Counts and destination bounds are honored; any temporary GIME mapping is restored before returning unless the routine contract explicitly states otherwise
; DOC-002 source-contract mirror contract intermission_stage_entry profile=copy: Copy the page-$24 intermission overlay into low RAM $0300 and jump to its stage/intermission dispatcher at $0303.
; DOC-002 source-contract mirror ends.

        pragma  nodollarlocal,6809
        setdp   $00
        include "ladybug_intermission_stage.inc"

        org     INTERMISSION_STAGE_ENTRY

intermission_stage_entry
        ldx     #INTERMISSION_RUNTIME_STAGE_ADDR
        ldu     #$0300
        ldy     #INTERMISSION_RUNTIME_BYTES
ise_copy
        lda     ,x+
        sta     ,u+
        leay    -1,y
        bne     ise_copy
        jmp     $0303
intermission_stage_end
