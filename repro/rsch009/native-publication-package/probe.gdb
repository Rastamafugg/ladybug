# Native GDB stage template, consumed sequentially by supervisor.py.
# Do not source directly. @DUMP@ is a validated absolute filename.
# stage: setup
set pagination off
set confirm off
set remotetimeout 10
set architecture m6809
# stage: attach
target remote 127.0.0.1:65520
# stage: breakpoint
break *0xc0e3
# stage: continue
continue
# stage: stop_pc
printf "RSCH009_PC=%u\n", $pc
# stage: remove_breakpoint
delete breakpoints
info breakpoints
# stage: removed_pc
printf "RSCH009_PC=%u\n", $pc
# stage: capture
dump binary memory @DUMP@ 0xc0e3 0xc0f9
# stage: capture_pc
printf "RSCH009_PC=%u\n", $pc
