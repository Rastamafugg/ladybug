#!/usr/bin/env bash
set +e
for addr in C0C3; do
  rm -f /tmp/bp.sna
  timeout 15 xroar -ui null -ao null -machine coco3 -ram 512 -cart ladybug \
    -cart-type rom -cart-rom /mnt/d/retro/ladybug/build/ladybug.rom -cart-autorun \
    -trap pc=0x$addr -trap-snap /tmp/bp.sna -trap-timeout 1 -timeout 10 \
    >/dev/null 2>&1
  rc=$?
  if [ -f /tmp/bp.sna ]; then
    size=$(stat -c %s /tmp/bp.sna)
    echo "0x$addr: REACHED rc=$rc size=$size"
  else
    echo "0x$addr: not reached rc=$rc"
  fi
done
