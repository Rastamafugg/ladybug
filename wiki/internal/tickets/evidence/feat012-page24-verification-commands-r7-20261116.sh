#!/usr/bin/env bash
# FEAT-012 repaired boot verification attempt 07: clean three-profile sizing plus proposed visible Return check.
# Run only from the Ready ticket assignment. No retry after the first failed or timed-out phase.
set -Eeuo pipefail
export LC_ALL=C
unset LADYBUG_BUILD_DIR

readonly ROOT=/mnt/c/Users/19029/.codex/worktrees/feat012-visible-input-r5/ladybug
readonly EXPECTED_COMMIT=51e9649a51c6edfd8d883fa191d776d42d3f9d61
readonly EXPECTED_BRANCH=codex/feat012-page24-relocation-r5
readonly OUTPUT=/mnt/c/Users/19029/.codex/worktrees/tool020-line-ending-fix/ladybug/wiki/internal/tickets/evidence/feat012-page24-verification-r7-20261116
readonly COMMAND_FILE=/mnt/c/Users/19029/.codex/worktrees/tool020-line-ending-fix/ladybug/wiki/internal/tickets/evidence/feat012-page24-verification-commands-r7-20261116.sh
readonly WSL_GIT_DIR=/mnt/e/projects/ladybug/.git/worktrees/ladybug5
readonly WSL_GIT_COMMON_DIR=/mnt/e/projects/ladybug/.git

CURRENT_PHASE=setup
STATUS_DETAIL=sequence-did-not-complete
STATUS_FILE=
SEQUENCE_COMPLETE=0

write_terminal_status() {
  local rc="$1" message temporary detail
  if (( rc == 0 && SEQUENCE_COMPLETE == 1 )); then
    message="PASS phase=complete detail=automated-profiles-passed-manual-visible-input-pending"
  else
    detail="$STATUS_DETAIL"
    [[ -n "$detail" ]] || detail=command-stopped
    message="FAIL phase=$CURRENT_PHASE exit=$rc detail=$detail"
  fi
  temporary="$STATUS_FILE.tmp.$$"
  if printf '%s\n' "$message" >"$temporary"; then
    mv -f -- "$temporary" "$STATUS_FILE" || rm -f -- "$temporary"
  fi
}

finalize_status() {
  local rc="$1"
  trap - EXIT
  if [[ -n "$STATUS_FILE" ]]; then
    write_terminal_status "$rc" || true
  fi
}

copy_artifact() {
  local artifact="$1" source="$2" destination="$3" copy_log="$4" copy_rc
  CURRENT_PHASE="evidence-copy:$artifact"
  if cp -- "$source" "$destination" >>"$copy_log" 2>&1; then
    return 0
  else
    copy_rc=$?
    STATUS_DETAIL="evidence-copy-failed: $artifact (exit $copy_rc)"
    return "$copy_rc"
  fi
}

run_copy_failure_probe() {
  local probe_dir rc expected
  probe_dir="$(mktemp -d /tmp/feat012-page24-copy-probe.XXXXXX)"
  set +e
  (
    set -Eeuo pipefail
    STATUS_FILE="$probe_dir/sequence-status.txt"
    CURRENT_PHASE=preflight
    STATUS_DETAIL=probe-did-not-finish
    SEQUENCE_COMPLETE=0
    printf '%s\n' 'in-progress' >"$STATUS_FILE"
    trap 'finalize_status "$?"' EXIT
    mkdir -p "$probe_dir/prior" "$probe_dir/build" "$probe_dir/destination"
    printf '%s\n' 'keep prior evidence' >"$probe_dir/prior/retained.txt"
    printf '%s\n' 'sentinel source' >"$probe_dir/build/copy-sentinel.bin"
    ln -s /dev/full "$probe_dir/destination/copy-sentinel.bin"
    copy_artifact copy-sentinel.bin "$probe_dir/build/copy-sentinel.bin" "$probe_dir/destination/copy-sentinel.bin" "$probe_dir/copy.log"
    touch "$probe_dir/after-copy-sentinel"
  )
  rc=$?
  set -e
  expected="FAIL phase=evidence-copy:copy-sentinel.bin exit=1 detail=evidence-copy-failed: copy-sentinel.bin (exit 1)"
  if (( rc != 1 )) ||
    [[ "$(cat "$probe_dir/sequence-status.txt")" != "$expected" ]] ||
    [[ ! -f "$probe_dir/prior/retained.txt" ]] ||
    [[ ! -f "$probe_dir/build/copy-sentinel.bin" ]] ||
    [[ -e "$probe_dir/after-copy-sentinel" ]]; then
    printf '%s\n' "FAIL: copy-failure probe did not meet its checks; fixture=$probe_dir" >&2
    return 1
  fi
  printf '%s\n' 'PASS: forced copy error produced terminal failure status, retained prior/source files, and stopped before the next step'
  if [[ "$probe_dir" == /tmp/feat012-page24-copy-probe.* ]]; then
    rm -rf -- "$probe_dir"
  else
    printf '%s\n' "FAIL: unexpected probe fixture path retained at $probe_dir" >&2
    return 1
  fi
}

verify_source() {
  local commit
  [[ "$(pwd -P)" == "$ROOT" ]] || { STATUS_DETAIL=wrong-source-worktree; return 2; }
  commit="$(git rev-parse HEAD)"
  [[ "$commit" == "$EXPECTED_COMMIT" ]] || {
    STATUS_DETAIL=unexpected-source-commit
    return 2
  }
  [[ "$(git branch --show-current)" == "$EXPECTED_BRANCH" ]] || {
    STATUS_DETAIL=wrong-source-branch
    return 2
  }
  [[ -z "$(git status --porcelain --untracked-files=normal)" ]] || {
    STATUS_DETAIL=source-worktree-is-not-clean
    return 2
  }
  printf '%s\n' "$commit" >"$OUTPUT/source-commit.txt"
}

run_phase() {
  local label="$1" seconds="$2" directory="$3" rc
  shift 3
  CURRENT_PHASE="$label"
  STATUS_DETAIL="$label-failed-or-timed-out"
  if /usr/bin/time -f '%e' -o "$directory/$label.elapsed-seconds.txt" timeout --signal=TERM --kill-after=5s "$seconds"s "$@" >"$directory/$label.log" 2>&1; then
    rc=0
  else
    rc=$?
  fi
  printf '%s\n' "$rc" >"$directory/$label.exit.txt"
  if (( rc != 0 )); then
    STATUS_DETAIL="$label-returned-$rc"
    return "$rc"
  fi
}

argument=
if (( $# > 0 )); then argument="$1"; fi
if [[ "$argument" == --copy-failure-probe ]]; then
  [[ "$#" == 1 ]] || { printf '%s\n' 'usage: package [--copy-failure-probe]' >&2; exit 2; }
  run_copy_failure_probe
  exit
fi
[[ "$#" == 0 ]] || { printf '%s\n' 'usage: package [--copy-failure-probe]' >&2; exit 2; }

cd "$ROOT"
[[ "$(pwd -P)" == "$ROOT" ]] || { printf '%s\n' 'setup failure: source path'; exit 2; }
[[ ! -e build && ! -L build ]] || { printf '%s\n' 'setup failure: source build directory already exists'; exit 2; }
[[ ! -e "$OUTPUT" && ! -L "$OUTPUT" ]] || { printf '%s\n' 'setup failure: evidence output already exists'; exit 2; }
mkdir -p "$OUTPUT"
STATUS_FILE="$OUTPUT/sequence-status.txt"
trap 'finalize_status "$?"' EXIT
CURRENT_PHASE=preflight
STATUS_DETAIL=preflight-failed
printf '%s\n' 'in-progress' >"$STATUS_FILE"
mkdir -p "$OUTPUT/git-bin"
printf '%s\n' '#!/bin/sh' 'exec /usr/bin/git -c core.autocrlf=true -c core.filemode=false "$@"' >"$OUTPUT/git-bin/git"
chmod +x "$OUTPUT/git-bin/git"
export GIT_DIR="$WSL_GIT_DIR" GIT_COMMON_DIR="$WSL_GIT_COMMON_DIR" GIT_WORK_TREE="$ROOT"
export PATH="$OUTPUT/git-bin:$PATH"

if ! verify_source >"$OUTPUT/source-preflight.log" 2>&1; then
  CURRENT_PHASE=source-preflight
  exit 2
fi
implementation_commit="$(git rev-parse HEAD)"
sha256sum -- "$COMMAND_FILE" >"$OUTPUT/command-package.sha256"
{
  printf 'branch=%s\n' "$EXPECTED_BRANCH"
  printf 'expected_commit=%s\n' "$EXPECTED_COMMIT"
  printf 'implementation_commit=%s\n' "$implementation_commit"
  printf 'worktree=%s\n' "$ROOT"
  printf 'git_dir=%s\n' "$WSL_GIT_DIR"
  printf 'git_common_dir=%s\n' "$WSL_GIT_COMMON_DIR"
  command -v bash
  bash --version | sed -n '1p'
  command -v git
  git --version
  command -v lwasm
  command -v python3
  python3 --version
  command -v m6809-gdb
  test -x /usr/local/bin/xroar
  printf '%s\n' '/usr/local/bin/xroar'
  command -v timeout
  timeout --version | sed -n '1p'
  test -x /usr/bin/time
  printf '%s\n' '/usr/bin/time'
} >"$OUTPUT/environment.txt" 2>&1
STATUS_DETAIL=all-preflights-passed
printf '%s\n' 'in-progress' >"$STATUS_FILE"

artifacts=(
  ladybug.rom ladybug.map ladybug.lst
  ladybug-presentation-runtime.bin ladybug-presentation-runtime.lst ladybug-presentation-runtime.map
  ladybug-perimeter-reset-helper.bin ladybug-perimeter-reset-helper.lst ladybug-perimeter-reset-helper.map
  ladybug-highscore-runtime.bin ladybug-highscore-runtime.lst ladybug-highscore-runtime.map
  ladybug-highscore-helper.bin ladybug-highscore-helper.lst ladybug-highscore-helper.map
  ladybug-keybinding-runtime.bin ladybug-keybinding-runtime.lst ladybug-keybinding-runtime.map
  ladybug-instruction-runtime.bin ladybug-instruction-runtime.lst ladybug-instruction-runtime.map
  ladybug-demo-runtime.bin ladybug-demo-runtime.lst ladybug-demo-runtime.map
  ladybug-presentation-cold.bin ladybug-presentation.json ladybug-sparse-layout.json
  source-build-receipt.json
  ladybug-gmc-boot.rom ladybug-gmc-boot.lst ladybug-gmc-boot.map
)

for profile in keyboard-adaptive joystick-adaptive keyboard-nonadaptive; do
  case "$profile" in
    keyboard-adaptive) input=keyboard; adaptive=1 ;;
    joystick-adaptive) input=joystick; adaptive=1 ;;
    keyboard-nonadaptive) input=keyboard; adaptive=0 ;;
  esac
  directory="$OUTPUT/$profile"
  mkdir -p "$directory/artifacts"
  verify_source >"$directory/source-preflight.log" 2>&1
  printf 'profile=complete input=%s adaptive=%s cpu=6809\n' "$input" "$adaptive" >"$directory/profile.txt"
  run_phase "$profile-build" 595 "$directory" env LADYBUG_PROFILE=complete LADYBUG_INPUT="$input" LADYBUG_ADAPTIVE="$adaptive" LADYBUG_CPU=6809 bash scripts/build.sh build
  run_phase "$profile-static-flow" 55 "$directory" python3 -B scripts/verify_presentation_flow.py

  if [[ "$profile" == keyboard-adaptive ]]; then
    run_phase runtime-startup 30 "$directory" python3 -B scripts/verify_gmc_boot.py --xroar /usr/local/bin/xroar --gdb m6809-gdb --rom build/ladybug.rom --map build/ladybug.map --manifest build/ladybug-sparse-layout.json --startup-only --verify-auxiliary-page --identity-output "$OUTPUT/keyboard-adaptive-runtime-identity.json"
    [[ -s "$OUTPUT/keyboard-adaptive-runtime-identity.json" ]] || {
      CURRENT_PHASE=runtime-identity-output
      STATUS_DETAIL=runtime-probe-did-not-write-identity
      exit 66
    }
  fi

  printf '%s\n' "$implementation_commit" >"$directory/implementation-commit.txt"
  for artifact in ${artifacts[@]}; do
    [[ -f "build/$artifact" ]] || {
      CURRENT_PHASE="evidence-copy:$artifact"
      STATUS_DETAIL="missing-build-artifact: $artifact"
      exit 66
    }
    copy_artifact "$artifact" "build/$artifact" "$directory/artifacts/$artifact" "$directory/evidence-copy.log"
  done
  (
    cd "$directory/artifacts"
    sha256sum -- ${artifacts[@]} >SHA256SUMS
    wc -c -- ${artifacts[@]} >SIZES.txt
  )
  if [[ "$profile" == keyboard-adaptive ]]; then
    actual_rom_sha="$(sha256sum -- "$directory/artifacts/ladybug.rom" | awk '{print $1}')"
    printf '%s\n' "$actual_rom_sha" >"$OUTPUT/keyboard-adaptive-rom.sha256"
    if [[ "$actual_rom_sha" != 71140f66117e859bd4a51c8d9becc3a4f81d67ec560ac0145171f4a57822b7ae ]]; then
      CURRENT_PHASE=keyboard-adaptive-rom-identity
      STATUS_DETAIL=clean-build-rom-does-not-match-reviewed-visible-input-card
      exit 65
    fi
  fi
  run_phase "$profile-cleanup" 55 "$directory" bash scripts/build.sh clean
done

CURRENT_PHASE=complete
STATUS_DETAIL=all-approved-phases-passed
SEQUENCE_COMPLETE=1
