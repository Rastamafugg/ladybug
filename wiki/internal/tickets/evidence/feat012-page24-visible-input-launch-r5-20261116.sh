#!/usr/bin/env bash
# One user-owned RGB session for the FEAT-012 keyboard Return input card.
# This launches XRoar only; it does not build, inject input, attach GDB, or set a session deadline.
set -Eeuo pipefail
readonly ROM=/mnt/c/Users/19029/.codex/worktrees/tool020-line-ending-fix/ladybug/wiki/internal/tickets/evidence/feat012-page24-verification-r5-20261116/keyboard-adaptive/artifacts/ladybug.rom
readonly EXPECTED_SHA256=71140f66117e859bd4a51c8d9becc3a4f81d67ec560ac0145171f4a57822b7ae
[[ -f "$ROM" ]] || { printf '%s\n' 'setup failure: retained keyboard/adaptive ROM is missing' >&2; exit 2; }
actual_sha="$(sha256sum -- "$ROM" | awk '{print $1}')"
[[ "$actual_sha" == "$EXPECTED_SHA256" ]] || {
  printf 'setup failure: ROM SHA-256 is %s, expected %s\n' "$actual_sha" "$EXPECTED_SHA256" >&2
  exit 2
}
printf 'manual session ROM SHA-256: %s\n' "$actual_sha"
exec /usr/local/bin/xroar \
  -machine coco3 \
  -machine-cpu 6809 \
  -ram 512 \
  -ram-init random \
  -cart-type gmc \
  -cart-rom "$ROM" \
  -cart-autorun \
  -tv-input rgb \
  -joy-right "" \
  -joy-left ""