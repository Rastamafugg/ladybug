        include "shared.inc"

        org $1000
entry   jsr worker
data_record fcb $AA,$BB
        rts
