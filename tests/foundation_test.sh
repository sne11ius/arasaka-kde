#!/usr/bin/env bash

set -euo pipefail

TEST_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd -- "$TEST_DIR/.." && pwd)

# shellcheck source=tests/testlib.sh
source "$TEST_DIR/testlib.sh"
setup_temp_home

# shellcheck source=lib/common.sh
source "$REPO_ROOT/lib/common.sh"

assert_eq "$REPO_ROOT" "$(project_root)" "project_root should locate the repository"
assert_eq "$HOME/.local/state/arasaka-kde" "$(state_root)" "state_root should use the HOME fallback"
assert_eq "$HOME/.cache/arasaka-kde" "$(cache_root)" "cache_root should use the HOME fallback"
assert_eq "$HOME/.local/state/arasaka-kde/snapshots" "$(snapshot_root)" "snapshot_root should be below state_root"

export XDG_STATE_HOME="$HOME/xdg-state"
export XDG_CACHE_HOME="$HOME/xdg-cache"
assert_eq "$XDG_STATE_HOME/arasaka-kde" "$(state_root)" "state_root should honor XDG_STATE_HOME"
assert_eq "$XDG_CACHE_HOME/arasaka-kde" "$(cache_root)" "cache_root should honor XDG_CACHE_HOME"

atomic_dir="$TEST_TMPDIR/atomic copy"
source_file="$atomic_dir/source"
target_file="$atomic_dir/target"
mkdir -p "$atomic_dir"
printf 'replacement\n' >"$source_file"
printf 'original\n' >"$target_file"
chmod 0640 "$source_file"
chmod 0600 "$target_file"

atomic_copy "$source_file" "$target_file"

assert_eq 'replacement' "$(<"$target_file")" "atomic_copy should replace the target contents"
assert_eq '640' "$(stat -c '%a' "$target_file")" "atomic_copy should preserve the source mode"
mapfile -d '' atomic_entries < <(find "$atomic_dir" -mindepth 1 -maxdepth 1 -print0)
assert_eq '2' "${#atomic_entries[@]}" "atomic_copy should not leave a temporary file"

printf 'foundation_test: PASS\n'
