# Parent-owned external command list. Clock begins immediately before the
# owned XRoar launch; each GDB-MCP call is capped at 10 seconds.
# Launch once with:
#   /mnt/e/projects/ladybug/docs/reference/xroar/src/xroar -ui gtk3 -ao pulse -machine coco3 -machine-cpu 6809 -ram 512 -ram-init random -cart-type gmc -cart-rom /mnt/e/projects/ladybug/repro/feat010-manual-review-20261016/capsule/build/ladybug.rom -cart-autorun -tv-input rgb -joy-right "" -joy-left "" -gdb -gdb-ip 127.0.0.1 -gdb-port 65522
# Use a distinct owned process for each case. Do not attach to PID 898.

set pagination off
set confirm off
set remotetimeout 3
set remote supported-packets-packet off
target remote :65522
tbreak *0xc116
continue
p/x $pc
dump binary memory /tmp/feat010-cold-bank1.bin 0xc000 0xfe00
shell sha256sum /tmp/feat010-cold-bank1.bin
# Compare with manifest resident_bank1 digest before interpreting $C116.

tbreak *0x1900
continue
p/x $pc
dump binary memory /tmp/feat010-cold-presentation.bin 0x1900 0x1df7
shell sha256sum /tmp/feat010-cold-presentation.bin
# Compare the 1271-byte full-module digest before interpreting any module label.
