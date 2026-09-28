; BUG-058 isolated adaptive fitting prototype. Not in the delivered build.
; PAR5 must be physical $34 on entry and return of every callback.
; Default callback addresses support isolated component tests. The adaptive
; builder replaces them with the installed always-mapped active vectors.
; Simulation/render callbacks may not commit a framebuffer or mutate counts.
        pragma  6809
FRAMES equ $0002
FB_RENDER_PENDING equ $0091
FB_COMMIT_SEQ equ $0092
PRES_MODE equ $00A5
INTENTS equ $007F
PLAYER_CELL equ $0009
; @audit {"id":"adaptive-history-a","kind":"scratch","symbol":"HISTORY_A","width":144,"mapping":"physical-page-34","phases":["foreground"],"owner":"isolated adaptive A damage history","lifetime":"Up to eight persistent 18-byte intent records until owner A composition completes; IRQ never reads this span.","initialization":"adaptive_reset clears the complete interval; adaptive_append writes a complete record before incrementing its count","clobbers":"Only the completed owner may consume its history; callback stubs do not draw or change counts."}
HISTORY_A equ $BC04
; @audit {"id":"adaptive-history-b","kind":"scratch","symbol":"HISTORY_B","width":144,"mapping":"physical-page-34","phases":["foreground"],"owner":"isolated adaptive B damage history","lifetime":"Up to eight persistent 18-byte intent records until owner B composition completes; IRQ never reads this span.","initialization":"adaptive_reset clears the complete interval; adaptive_append writes a complete record before incrementing its count","clobbers":"Only the completed owner may consume its history; callback stubs do not draw or change counts."}
HISTORY_B equ $BC94
; @audit {"id":"adaptive-state","kind":"scratch","symbol":"STATE","width":32,"mapping":"physical-page-34","phases":["foreground"],"owner":"isolated adaptive scheduler and journal reducer","lifetime":"Persistent timestamps/debt/cadence/counts plus initialized foreground iteration scratch; no direct-page or IRQ alias.","initialization":"adaptive_reset clears 320 bytes and initializes raw clock, audio timestamp, publication due and cadence","clobbers":"AD_BATCH is the step budget before reduction and later the newer-record scan index; AD_CLASS/INDEX/PTR/SCAN/TOTAL/RESET are reducer scratch. AD_END high byte is initialized before composition as a static-rebuild flag and overwritten with a clock value at completion. No callback retains or changes these fields."}
STATE equ $BD24
AD_LAST equ STATE
AD_SIM equ STATE+2
AD_DEBT equ STATE+4
AD_AUDIO equ STATE+6
AD_BEGIN equ STATE+8
AD_END equ STATE+10
AD_DUE equ STATE+12
AD_COMMIT equ STATE+14
AD_RATE equ STATE+16
AD_QUICK equ STATE+17
AD_BATCH equ STATE+18
AD_BARRIER equ STATE+19
AD_COUNT_A equ STATE+20
AD_COUNT_B equ STATE+21
AD_FAULT equ STATE+22
AD_INDEX equ STATE+23
AD_PTR equ STATE+24
AD_SCAN equ STATE+26
AD_MODE equ STATE+28
AD_TOTAL equ STATE+29
AD_CLASS equ STATE+30
AD_RESET equ STATE+31
; ABI: tick returns A=barrier flag; global/key callbacks consume DP INTENTS.
; Global callback A=class (0 entities,1 HUD/lives,2 perimeter reset/multiplier).
; Key callback A=class (0 dot,1 box,2 letter,3 primary gate,4 secondary gate).
; This core does not call AUDIO_CALLBACK. The active driver services elapsed
; audio before batching, semantic admission after each tick, and PSG output
; before completion. Synthetic component callbacks are not integration proof.
TICK_CALLBACK equ $1800
GLOBAL_CALLBACK equ $1803
KEY_CALLBACK equ $1806
AUDIO_CALLBACK equ $1809
        org $BD44
adaptive_start
        lbra adaptive_reset
        lbra adaptive_batch
        lbra adaptive_append
        lbra adaptive_reduce
        lbra adaptive_complete

; Foreground snapshot respects caller IRQ state, including 16-bit counter wrap.
adaptive_clock
        pshs cc
        orcc #$10
        ldd FRAMES
        puls cc,pc
adaptive_reset
        ldx #HISTORY_A
ar_clear
        clr ,x+
        cmpx #adaptive_start
        blo ar_clear
        bsr adaptive_clock
        std AD_LAST
        std AD_AUDIO
        std AD_DUE
        lda #1
        sta AD_RATE
        rts

; Already displayed barrier can retire. No simulation during pending image.
adaptive_batch
        tst AD_FAULT
        lbne ab_none
        tst FB_RENDER_PENDING
        lbne ab_none
        tst AD_BARRIER
        beq ab_clock
        ldd FB_COMMIT_SEQ
        cmpd AD_COMMIT
        lbeq ab_none
        clr AD_BARRIER
ab_clock
        lbsr adaptive_clock
        std AD_BEGIN
        pshs d
        subd AD_LAST
        addd AD_DEBT
        lbcs ab_saturate
        std AD_DEBT
        puls d
        std AD_LAST
        ldd AD_DEBT
        lbeq ab_none
        ldd AD_BEGIN
        subd AD_DUE
        lbmi ab_none
        lda AD_COUNT_A
        cmpa #8
        bhs ab_fault
        lda AD_COUNT_B
        cmpa #8
        bhs ab_fault
        lda #4
        sta AD_BATCH
        lda PRES_MODE
        sta AD_MODE
ab_step
        lda AD_COUNT_A
        cmpa #8
        bhs ab_fault
        lda AD_COUNT_B
        cmpa #8
        bhs ab_fault
        ; Each tick starts fresh intents. Actor flags are regenerated by logic.
        ldx #INTENTS
        ldb #16
ab_clear
        clr ,x+
        decb
        bne ab_clear
        ldd AD_SIM
        addd #1
        std AD_SIM
        jsr TICK_CALLBACK
        sta AD_BARRIER
        lbsr adaptive_append
        bcs ab_fault
        ; Tick callback emits logical events once. Timestamped audio servicing
        ; is outside this helper until a safe elapsed-service API is fitted.
        ldd AD_DEBT
        subd #1
        std AD_DEBT
        beq ab_ready
        tst AD_BARRIER
        bne ab_ready
        lda PRES_MODE
        cmpa AD_MODE
        bne ab_transition
        dec AD_BATCH
        bne ab_step
ab_ready
        ldd FB_COMMIT_SEQ
        std AD_COMMIT
        orcc #1
        rts
ab_transition
        lda #1
        sta AD_BARRIER
        bra ab_ready
ab_saturate
        puls d
        std AD_LAST
        ldd #$FFFF
        std AD_DEBT
ab_fault
        lda AD_FAULT
        ora #1
        sta AD_FAULT
ab_none
        andcc #$FE
        rts

; Check both histories before writing either; a failure changes neither count.
adaptive_append
        lda AD_COUNT_A
        cmpa #8
        bhs aa_fault
        lda AD_COUNT_B
        cmpa #8
        bhs aa_fault
        ldu #HISTORY_A
        lda AD_COUNT_A
        lbsr aa_record
        inc AD_COUNT_A
        ldu #HISTORY_B
        lda AD_COUNT_B
        lbsr aa_record
        inc AD_COUNT_B
        andcc #$FE
        rts
aa_fault
        lda AD_FAULT
        ora #2
        sta AD_FAULT
        orcc #1
        rts
aa_record
        ldb #18
        mul
        leau d,u
        ldx #INTENTS
        ldb #16
aa_copy
        lda ,x+
        sta ,u+
        decb
        bne aa_copy
        ldd PLAYER_CELL
        std ,u
        ; Exclude actor/popup/death and transient enemy scratch from history.
        lda -16,u
        anda #$7E
        sta -16,u
        lda -15,u
        anda #$1E
        sta -15,u
        lda -8,u
        anda #$18
        sta -8,u
        rts

; A=target owner 0/1. Save complete transient intents as big-endian pairs.
; Restore reverse pair order; stack size and saved owner offset stay identical.
; Production wrapper restores all buffer-old actors before entering here.
adaptive_reduce
        pshs a
        ldd INTENTS+0
        pshs d
        ldd INTENTS+2
        pshs d
        ldd INTENTS+4
        pshs d
        ldd INTENTS+6
        pshs d
        ldd INTENTS+8
        pshs d
        ldd INTENTS+10
        pshs d
        ldd INTENTS+12
        pshs d
        ldd INTENTS+14
        pshs d
        ldd PLAYER_CELL
        pshs d
        lda 18,s
        beq adr_a
        ldu #HISTORY_B
        ldb AD_COUNT_B
        bra adr_owner
adr_a
        ldu #HISTORY_A
        ldb AD_COUNT_A
adr_owner
        stu AD_PTR
        stb AD_TOTAL
        clr AD_RESET
        clr AD_INDEX
        ldx #INTENTS
        ldb #4
adr_zero
        clr ,x+
        clr ,x+
        clr ,x+
        clr ,x+
        decb
        bne adr_zero
        ; Merge only whole-layer classes; latest keyed coverage stays separate.
        ldx AD_PTR
adr_merge
        lda AD_INDEX
        cmpa AD_TOTAL
        bhs adr_globals
        lda ,x
        anda #$4E
        ora INTENTS
        sta INTENTS
        lda 1,x
        anda #$1A
        ora INTENTS+1
        sta INTENTS+1
        lda 8,x
        anda #$18
        ora INTENTS+8
        sta INTENTS+8
        lda 1,x
        bita #8
        beq adr_merge_next
        lda AD_INDEX
        inca
        sta AD_RESET
adr_merge_next
        leax 18,x
        inc AD_INDEX
        bra adr_merge
adr_globals
        ; Stage dominates all preceding persistent coverage.
        lda INTENTS
        bita #$40
        bne adr_stage
        clra
        jsr GLOBAL_CALLBACK
        lda #1
        jsr GLOBAL_CALLBACK
        lda #2
        jsr GLOBAL_CALLBACK
        clr AD_CLASS
adr_class
        lda AD_CLASS
        cmpa #1
        bne adr_class_zero
        lda AD_RESET
        bra adr_class_index
adr_class_zero
        clra
adr_class_index
        sta AD_INDEX
adr_item
        lda AD_INDEX
        cmpa AD_TOTAL
        bhs adr_class_next
        ldb #18
        mul
        ldu AD_PTR
        leau d,u
        lbsr adr_present
        bcc adr_item_next
        stu AD_SCAN
        lbsr adr_newer
        bcs adr_item_next
        ldu AD_SCAN
        lbsr adr_load
        lda AD_CLASS
        jsr KEY_CALLBACK
adr_item_next
        inc AD_INDEX
        bra adr_item
adr_class_next
        inc AD_CLASS
        lda AD_CLASS
        cmpa #5
        blo adr_class
        bra adr_restore
adr_stage
        lda #3
        jsr GLOBAL_CALLBACK
adr_restore
        puls d
        std PLAYER_CELL
        puls d
        std INTENTS+14
        puls d
        std INTENTS+12
        puls d
        std INTENTS+10
        puls d
        std INTENTS+8
        puls d
        std INTENTS+6
        puls d
        std INTENTS+4
        puls d
        std INTENTS+2
        puls d
        std INTENTS+0
        puls a
        rts

; Check whether U carries the requested keyed class. Carry is presence.
adr_present
        lda AD_CLASS
        beq ap_dot
        cmpa #1
        beq ap_box
        cmpa #2
        beq ap_letter
        cmpa #3
        beq ap_gate
        tst 11,u
        bra ap_test
ap_gate
        tst 9,u
ap_test
        beq ap_no
        orcc #1
        rts
ap_dot
        lda ,u
        anda #$20
        bra ap_test
ap_box
        lda ,u
        anda #$10
        bra ap_test
ap_letter
        lda 1,u
        anda #4
        bra ap_test
ap_no
        andcc #$FE
        rts

; A later matching coverage key supersedes current. Gate keys compare both
; fields, allowing a gate to move between primary and secondary slots.
adr_newer
        lda AD_INDEX
        inca
        sta AD_BATCH   ; reducer owns finished batch scratch
        ldu AD_SCAN
an_next
        lda AD_BATCH
        cmpa AD_TOTAL
        bhs an_no
        leau 18,u
        lda AD_CLASS
        cmpa #3
        bhs an_gate
        ; adr_present changes A/CC only; U remains the newer record.
        lbsr adr_present
        bcc an_skip
        ldx AD_SCAN
        lda AD_CLASS
        beq an_dot
        cmpa #1
        beq an_box
        ldd 4,u
        cmpd 4,x
        bra an_compare
an_dot
        ldd 16,u
        cmpd 16,x
        bra an_compare
an_box
        lda 2,u
        cmpa 2,x
        bra an_compare
an_gate
        ldx AD_SCAN
        lda AD_CLASS
        cmpa #3
        bne an_second
        lda 9,x
        bra an_gate_key
an_second
        lda 11,x
an_gate_key
        cmpa 9,u
        beq an_yes
        cmpa 11,u
an_compare
        beq an_yes
an_skip
        inc AD_BATCH
        bra an_next
an_no
        andcc #$FE
        rts
an_yes
        orcc #1
        rts
adr_load
        ldd 0,u
        std INTENTS+0
        ldd 2,u
        std INTENTS+2
        ldd 4,u
        std INTENTS+4
        ldd 6,u
        std INTENTS+6
        ldd 8,u
        std INTENTS+8
        ldd 10,u
        std INTENTS+10
        ldd 12,u
        std INTENTS+12
        ldd 14,u
        std INTENTS+14
        ldd 16,u
        std PLAYER_CELL
        rts

; Call after completed work, before the ordinary publish gateway. Every helper
; callback must include any input/audio work in this measured interval.
adaptive_complete
        pshs a           ; clear history only after successful complete work
        lbsr adaptive_clock
        std AD_END
        subd AD_BEGIN
        beq ac_quick
        lda #2
        sta AD_RATE
        clr AD_QUICK
        bra ac_due
ac_quick
        inc AD_QUICK
        lda AD_QUICK
        cmpa #8
        blo ac_due
        lda #1
        sta AD_RATE
        clr AD_QUICK
ac_due
        clra
        ldb AD_RATE
        addd AD_BEGIN
        std AD_DUE
        puls a
        ldx #AD_COUNT_A
        clr a,x
        rts
adaptive_end
