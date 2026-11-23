#!/usr/bin/env bash
# FEAT-012 frozen candidate sizing. Do not run without the authorized dispatch.
set -euo pipefail
export LC_ALL=C
unset LADYBUG_BUILD_DIR
readonly ROOT=/mnt/c/Users/19029/.codex/worktrees/feat012-wake-repair-ready/ladybug
readonly EXPECTED_COMMIT=ee79fe6af79755d76ffe7d571c15e2c16e6086e7
readonly WSL_GIT_DIR=/mnt/e/projects/ladybug/.git/worktrees/ladybug17
readonly WSL_GIT_COMMON_DIR=/mnt/e/projects/ladybug/.git
readonly OUTPUT="$ROOT/repro/feat012-wake-sizing-package-20261113-02"
cd "$ROOT"
[[ "$(pwd -P)" == "$ROOT" ]] || { printf '%s\n' 'setup failure: checkout path'; exit 2; }
[[ ! -e build && ! -L build ]] || { printf '%s\n' 'setup failure: build already exists'; exit 2; }
[[ ! -e "$OUTPUT" && ! -L "$OUTPUT" ]] || { printf '%s\n' 'setup failure: output already exists'; exit 2; }
verify_source() {
  [[ "$(git rev-parse HEAD)" == "$EXPECTED_COMMIT" ]] || { printf '%s\n' 'setup failure: candidate commit'; return 2; }
  [[ -z "$(git status --porcelain --untracked-files=normal)" ]] || { printf '%s\n' 'setup failure: candidate checkout is dirty'; return 2; }
  sha256sum -c - <<'HASHES'
aeac8b755ddd16d90e8c918aee7f66e6f4208f27858bd5a38e9605092a470ef3  src/presentation_runtime.s
71a2a8347a91980d7087ba083c2cf9612995fc05b4abfa8e24df7a42c1b5c062  src/shared_text_stage.inc
9d9fece7e9f6575b769117570bde94de0e125932cf3e869ad8babdc579c711b4  src/keybinding_runtime.s
9a39a51e86522b45f502da1d9ce5dfc4a0df0df040c8a4c8b51958f18468ef7f  src/main.s
39c08b0bf45b606d4c1e913c520245fd6e928b7cb6ada5bffd862b4a4202ee71  src/demo_runtime.s
ab6c5597911d6269223f870dcec1f61bf46216563a6ea2d7fcbc56f9d8a9e974  scripts/source_reference.json
68bb66b6ec2bd6a9c7a65bb13b299896b1dd67c84a964ef910fbf789163a4fe9  scripts/build.sh
58576f66be9ac1825206cc0cc29d88bfdfeebf430c1c239e059f5588adad2ec0  scripts/verify_presentation_flow.py
c74c24b4d6b0dffffd88faa2122320d5baa0338de7f9ddd41c407ce77e3f6ed9  scripts/build_sparse_sprites.py
HASHES
}
mkdir -p "$OUTPUT"
printf '%s\n' 'preflight in progress' >"$OUTPUT/sequence-status.txt"
mkdir -p "$OUTPUT/git-bin"
printf '%s\n' '#!/bin/sh' 'exec /usr/bin/git -c core.autocrlf=true -c core.filemode=false "$@"' >"$OUTPUT/git-bin/git"
chmod +x "$OUTPUT/git-bin/git"
export GIT_DIR="$WSL_GIT_DIR" GIT_COMMON_DIR="$WSL_GIT_COMMON_DIR" GIT_WORK_TREE="$ROOT"
export PATH="$OUTPUT/git-bin:$PATH"
if ! verify_source >"$OUTPUT/preflight.log" 2>&1; then
  printf '%s\n' 'source identity failure' >"$OUTPUT/sequence-status.txt"
  exit 2
fi
if ! {
  printf 'candidate=%s\n' "$EXPECTED_COMMIT"
  printf 'worktree=%s\n' "$ROOT"
  command -v lwasm &&
  lwasm --version &&
  command -v python3 &&
  python3 --version &&
  command -v timeout &&
  timeout --version &&
  [[ -x /usr/bin/time ]]
} >"$OUTPUT/environment.txt" 2>&1; then
  printf '%s\n' 'toolchain preflight failure' >"$OUTPUT/sequence-status.txt"
  exit 2
fi
printf '%s\n' 'in-progress' >"$OUTPUT/sequence-status.txt"
run_phase() {
  local label="$1" limit="$2" directory="$3"
  shift 3
  local rc
  if /usr/bin/time -f '%e' -o "$directory/$label.elapsed-seconds.txt" \
    timeout --signal=TERM --kill-after=5s "$limit" "$@" \
    >"$directory/$label.log" 2>&1; then
    rc=0
  else
    rc=$?
  fi
  printf '%s\n' "$rc" >"$directory/$label.exit.txt"
  if (( rc != 0 )); then
    if (( rc == 124 || rc == 137 )); then
      printf '%s\n' "$label timeout or termination; inspect retained evidence" >"$OUTPUT/sequence-status.txt"
    else
      printf '%s\n' "$label failed; inspect retained evidence" >"$OUTPUT/sequence-status.txt"
    fi
    printf '%s\n' "Stopped: $label returned $rc; build directory retained."
    exit "$rc"
  fi
}
for profile in keyboard-adaptive joystick-adaptive keyboard-nonadaptive; do
  case "$profile" in
    keyboard-adaptive) input=keyboard; adaptive=1 ;;
    joystick-adaptive) input=joystick; adaptive=1 ;;
    keyboard-nonadaptive) input=keyboard; adaptive=0 ;;
  esac
  directory="$OUTPUT/$profile"
  mkdir -p "$directory"
  if ! verify_source >"$directory/source-identity.log" 2>&1; then
    printf '%s\n' 'source identity failure' >"$OUTPUT/sequence-status.txt"
    exit 2
  fi
  [[ ! -e build && ! -L build ]] || { printf '%s\n' 'unexpected build directory' >"$OUTPUT/sequence-status.txt"; exit 2; }
  printf 'profile=complete input=%s adaptive=%s cpu=6809\n' "$input" "$adaptive" >"$directory/profile.txt"
  run_phase build 595s "$directory" env LADYBUG_PROFILE=complete LADYBUG_INPUT="$input" \
    LADYBUG_ADAPTIVE="$adaptive" LADYBUG_CPU=6809 bash scripts/build.sh build
  run_phase static-flow 55s "$directory" python3 -B scripts/verify_presentation_flow.py
  mkdir -p "$directory/artifacts"
  set -- ladybug.rom ladybug.map ladybug.lst \
    ladybug-presentation-runtime.bin ladybug-presentation-runtime.lst ladybug-presentation-runtime.map \
    ladybug-perimeter-reset-helper.bin ladybug-perimeter-reset-helper.lst ladybug-perimeter-reset-helper.map \
    ladybug-highscore-runtime.bin ladybug-highscore-runtime.lst ladybug-highscore-runtime.map \
    ladybug-highscore-helper.bin ladybug-highscore-helper.lst ladybug-highscore-helper.map \
    ladybug-keybinding-runtime.bin ladybug-keybinding-runtime.lst ladybug-keybinding-runtime.map \
    ladybug-instruction-runtime.bin ladybug-instruction-runtime.lst ladybug-instruction-runtime.map \
    ladybug-demo-runtime.bin ladybug-demo-runtime.lst ladybug-demo-runtime.map \
    ladybug-presentation-cold.bin ladybug-presentation.json ladybug-sparse-layout.json \
    source-build-receipt.json
  for artifact in "$@"; do
    if [[ ! -f "build/$artifact" ]]; then
      printf 'missing build artifact: %s\n' "$artifact" >"$OUTPUT/sequence-status.txt"
      exit 66
    fi
    if cp -- "build/$artifact" "$directory/artifacts/$artifact"; then
      :
    else
      copy_rc=$?
      printf 'evidence-copy-failed: %s (exit %s)\n' "$artifact" "$copy_rc" >"$OUTPUT/sequence-status.txt"
      exit "$copy_rc"
    fi
  done
  (cd "$directory/artifacts"; sha256sum -- "$@" >SHA256SUMS; wc -c -- "$@" >SIZES.txt)
  if [[ "$profile" != keyboard-nonadaptive ]]; then
    [[ -d build && ! -L build && "$(realpath -m build)" == "$ROOT/build" ]] || {
      printf '%s\n' 'cleanup target validation failed' >"$OUTPUT/sequence-status.txt"
      exit 2
    }
    if ! bash scripts/build.sh clean >"$directory/cleanup.log" 2>&1; then
      printf '%s\n' 'cleanup command failure' >"$OUTPUT/sequence-status.txt"
      exit 2
    fi
  fi
done
printf '%s\n' 'all three build and static-flow phases completed' >"$OUTPUT/sequence-status.txt"
