; FEAT-018 forced-RAM code and state. The bootstrap installs this area once;
; the resident runtime retires it after both Attract buffers are hydrated.
BOOT_LOADING_IRQ     equ $FE00
BOOT_LOADING_HYDRATE equ $FE60
BOOT_LOADING_READY   equ $FE8B
BOOT_LOADING_TICKS   equ $FE8C
BOOT_LOADING_OFFSET  equ $FE8D
BOOT_LOADING_DOT     equ $FE8E
BOOT_LOADING_OWNER   equ $00D9   ; negative while cold Attract owns hydration
