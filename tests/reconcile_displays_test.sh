#!/usr/bin/env bash

set -euo pipefail

TEST_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd -- "$TEST_DIR/.." && pwd)
RECONCILER="$REPO_ROOT/bin/reconcile-displays"

# shellcheck source=tests/testlib.sh
source "$TEST_DIR/testlib.sh"
setup_temp_home

fake_bin="$TEST_TMPDIR/bin"
mkdir -p "$fake_bin"
printf '#!/usr/bin/env bash\nexit 90\n' >"$fake_bin/kscreen-doctor"
printf '#!/usr/bin/env bash\nexit 91\n' >"$fake_bin/qdbus6"
chmod +x "$fake_bin/kscreen-doctor" "$fake_bin/qdbus6"

output=$(PATH="$fake_bin:$PATH" "$RECONCILER" \
    --dry-run --json "$TEST_DIR/fixtures/topology/internal-external.json")

assert_eq 'DP-1' "$(jq -r '.primary' <<<"$output")" "dry-run should select the external output"
assert_eq 'eDP-1' "$(jq -r '.internal' <<<"$output")" "dry-run should retain the internal role"
assert_eq '[["DP-1",1]]' "$(jq -c '.changes' <<<"$output")" "dry-run should report only a priority correction"
[[ ! -e "$HOME/.local/state/arasaka-kde/topology" ]] || fail "dry-run should not write topology state"

zero_output=$(PATH="$fake_bin:$PATH" "$RECONCILER" \
    --dry-run --json "$TEST_DIR/fixtures/topology/zero-enabled.json")
assert_eq 'no-enabled-outputs' "$(jq -r '.status' <<<"$zero_output")" "zero-output dry-run should report a transient no-op"
[[ ! -e "$HOME/.local/state/arasaka-kde/topology" ]] || fail "zero-output dry-run should not write topology state"

command_log="$TEST_TMPDIR/commands.log"
printf '#!/usr/bin/env bash\nprintf "kscreen-doctor %%s\\n" "$*" >>"$ARASAKA_COMMAND_LOG"\nif [[ ${1:-} == --json ]]; then\n  command cat "$ARASAKA_KSCREEN_JSON"\n  exit 0\nfi\nexit 92\n' >"$fake_bin/kscreen-doctor"
export ARASAKA_COMMAND_LOG="$command_log"
export ARASAKA_KSCREEN_JSON="$TEST_DIR/fixtures/topology/zero-enabled.json"
printf 'previous-signature\n' >"$HOME/.local/state/arasaka-kde/topology"

PATH="$fake_bin:$PATH" "$RECONCILER"
assert_eq 'kscreen-doctor --json' "$(<"$command_log")" "zero-output reconciliation should only query KScreen"
assert_eq 'previous-signature' "$(<"$HOME/.local/state/arasaka-kde/topology")" "zero-output reconciliation should preserve valid topology state"
rm -- "$HOME/.local/state/arasaka-kde/topology"

corrected_json="$TEST_TMPDIR/corrected.json"
jq '(.outputs[] | select(.name == "eDP-1") | .priority) = 2 |
    (.outputs[] | select(.name == "DP-1") | .priority) = 1' \
    "$TEST_DIR/fixtures/topology/internal-external.json" >"$corrected_json"
priority_marker="$TEST_TMPDIR/priority-corrected"
printf '#!/usr/bin/env bash\nprintf "kscreen-doctor %%s\\n" "$*" >>"$ARASAKA_COMMAND_LOG"\nif [[ ${1:-} == --json ]]; then\n  if [[ -e $ARASAKA_PRIORITY_MARKER ]]; then\n    command cat "$ARASAKA_CORRECTED_JSON"\n  else\n    command cat "$ARASAKA_KSCREEN_JSON"\n  fi\n  exit 0\nfi\nif [[ $* == output.DP-1.priority.1 ]]; then\n  : >"$ARASAKA_PRIORITY_MARKER"\n  exit 0\nfi\nexit 92\n' >"$fake_bin/kscreen-doctor"
printf '#!/usr/bin/env bash\nprintf "qdbus6 %%s\\n" "$*" >>"$ARASAKA_QDBUS_LOG"\n' >"$fake_bin/qdbus6"
chmod +x "$fake_bin/kscreen-doctor" "$fake_bin/qdbus6"
export ARASAKA_KSCREEN_JSON="$TEST_DIR/fixtures/topology/internal-external.json"
export ARASAKA_CORRECTED_JSON="$corrected_json"
export ARASAKA_PRIORITY_MARKER="$priority_marker"
export ARASAKA_QDBUS_LOG="$TEST_TMPDIR/qdbus.log"
: >"$command_log"
: >"$ARASAKA_QDBUS_LOG"

PATH="$fake_bin:$PATH" "$RECONCILER"
assert_eq $'kscreen-doctor --json\nkscreen-doctor output.DP-1.priority.1' "$(<"$command_log")" "reconciliation should mutate display priority only"
state=$(<"$HOME/.local/state/arasaka-kde/topology")
assert_eq '{"enabled":["DP-1","eDP-1"],"internal":"eDP-1","primary":"DP-1"}' "${state%|*}" "state should contain the stable corrected topology signature"
[[ ${state##*|} =~ ^[0-9a-f]{64}$ ]] || fail "state should contain the layout signature"
first_qdbus_log=$(<"$ARASAKA_QDBUS_LOG")
[[ "$first_qdbus_log" == *'org.kde.PlasmaShell.evaluateScript'* ]] || fail "changed topology should evaluate the Plasma layout"

PATH="$fake_bin:$PATH" "$RECONCILER"
assert_eq $'kscreen-doctor --json\nkscreen-doctor output.DP-1.priority.1\nkscreen-doctor --json' "$(<"$command_log")" "unchanged corrected topology should only be queried"
assert_eq "$first_qdbus_log" "$(<"$ARASAKA_QDBUS_LOG")" "unchanged topology should not evaluate the Plasma layout again"

printf 'reconcile_displays_test: PASS\n'
