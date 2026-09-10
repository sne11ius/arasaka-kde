#!/usr/bin/env bash

set -euo pipefail

TEST_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd -- "$TEST_DIR/.." && pwd)
RECONCILER="$REPO_ROOT/bin/reconcile-displays"

# shellcheck source=tests/testlib.sh
source "$TEST_DIR/testlib.sh"
setup_temp_home

# Use the template contract independently of concurrent layout/QML changes.
runtime="$TEST_TMPDIR/runtime"
mkdir -p "$runtime"
cp "$RECONCILER" "$runtime/reconcile-displays"
cp "$REPO_ROOT/lib/arasaka_topology.py" "$runtime/arasaka_topology.py"
cp "$REPO_ROOT/theme/panel-colorizer/Arasaka.json" "$runtime/Arasaka.json"
cp "$REPO_ROOT/plasma/shader-wallpaper.js" "$runtime/shader-wallpaper.js"
cp "$REPO_ROOT/plasma/wallpaper-defaults.json" "$runtime/wallpaper-defaults.json"
printf 'var launcherSession = "__LAUNCHER_SESSION__";\nvar hideDesktopIcons = __HIDE_DESKTOP_ICONS__;\n' >"$runtime/layout.js"
RECONCILER="$runtime/reconcile-displays"

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
printf '%s\n' '#!/usr/bin/env python3' \
    'import os, subprocess, sys' \
    'with open(os.environ["ARASAKA_QDBUS_LOG"], "a") as log: log.write("qdbus6 " + " ".join(sys.argv[1:]) + "\n")' \
    'if sys.argv[3] == "org.freedesktop.DBus.GetId": print("test-bus")' \
    'elif sys.argv[3] == "org.freedesktop.DBus.GetNameOwner": print(os.environ.get("ARASAKA_SHELL_OWNER", ":1.42"))' \
    'elif sys.argv[3] == "org.kde.PlasmaShell.evaluateScript" and "ARASAKA_SHADER_WALLPAPER=" in sys.argv[4]:' \
    '    if os.environ.get("ARASAKA_BAD_SHADER_REPORT"): sys.exit("Error: missing secondary desktop")' \
    '    if os.environ.get("ARASAKA_FAIL_SHADER_PHASE") and ("var shaderPhase = \"" + os.environ["ARASAKA_FAIL_SHADER_PHASE"] + "\";") in sys.argv[4]: sys.exit("fixture interrupted activation")' \
    '    sys.path.insert(0, os.environ["ARASAKA_TEST_DIR"])' \
    '    from apply_shader_wallpaper_test import PLASMA' \
    '    sys.exit(subprocess.run(["node", "-e", PLASMA, sys.argv[4]]).returncode)' >"$fake_bin/qdbus6"
export ARASAKA_TEST_DIR="$TEST_DIR"
export PYTHONDONTWRITEBYTECODE=1
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
[[ "$first_qdbus_log" == *'var launcherSession = "test-bus/:1.42";'* ]] || fail "layout should receive the current bus/shell token"
[[ "$first_qdbus_log" == *'var hideDesktopIcons = false;'* ]] || fail "standalone reconciliation should leave icons alone"
[[ "$first_qdbus_log" != *'ARASAKA_SHADER_WALLPAPER='* ]] || fail "standalone reconciliation should leave wallpapers alone"

PATH="$fake_bin:$PATH" "$RECONCILER"
assert_eq $'kscreen-doctor --json\nkscreen-doctor output.DP-1.priority.1\nkscreen-doctor --json' "$(<"$command_log")" "unchanged corrected topology should only be queried"
assert_eq "$first_qdbus_log" "$(<"$ARASAKA_QDBUS_LOG")" "unchanged topology should not evaluate the Plasma layout again"

: >"$ARASAKA_QDBUS_LOG"
PATH="$fake_bin:$PATH" ARASAKA_SHELL_OWNER=:1.99 "$RECONCILER" --force --hide-desktop-icons
forced_log=$(<"$ARASAKA_QDBUS_LOG")
[[ "$forced_log" == *'var launcherSession = "test-bus/:1.99";'* ]] || fail "forced application should obtain a fresh shell token"
[[ "$forced_log" == *'var hideDesktopIcons = true;'* ]] || fail "--hide-desktop-icons should opt into icon changes"

artwork="$HOME/.local/share/wallpapers/Arasaka"
plugin="$HOME/.local/share/plasma/wallpapers/online.knowmad.shaderwallpaper"
mkdir -p "$artwork/shaders" "$plugin/contents/ui/shaderwallpaper"
printf 'fixture\n' >"$artwork/shaders/Heartfelt_No_Heart.frag"
printf 'fixture\n' >"$artwork/mikoshi-16x9.png"
printf 'fixture\n' >"$artwork/mikoshi-16x10.png"
printf 'fixture\n' >"$plugin/contents/ui/shaderwallpaper/libshaderwallpaperplugin.so"
export DESKTOP_STATE="$TEST_TMPDIR/desktops.json"
export CHECK_PRIVACY=1
initial_desktops='[{"id":12,"screen":1,"wallpaperPlugin":"online.knowmad.shaderwallpaper","config":{"selectedShaderPath":"file:///custom.frag","mouseEnabled":false,"targetFps":17}},
{"id":27,"screen":0,"wallpaperPlugin":"org.kde.image","config":{"mouseEnabled":true,"audioEnabled":true}},
{"id":42,"screen":2,"wallpaperPlugin":"org.kde.image","config":{}},
{"id":99,"screen":-1,"wallpaperPlugin":"org.kde.image","config":{"keep":true}}]'
printf '%s\n' "$initial_desktops" >"$DESKTOP_STATE"
: >"$ARASAKA_QDBUS_LOG"
PATH="$fake_bin:$PATH" "$RECONCILER" --ensure-shader-wallpaper --hide-desktop-icons >"$TEST_TMPDIR/error" 2>&1 ||
    fail "old Heartfelt installation must still reconcile layout while rain setup is deferred"
[[ $(<"$TEST_TMPDIR/error") == *'Interactive_Rain.frag'* ]] || fail "preflight should identify missing Interactive Rain"
[[ $(<"$TEST_TMPDIR/error") == *'deferred'* ]] || fail "missing rain must explicitly defer wallpaper setup"
[[ $(<"$ARASAKA_QDBUS_LOG") == *'org.kde.PlasmaShell.evaluateScript'*'var hideDesktopIcons = true;'* ]] || fail "missing rain must not block layout/icon reconciliation"
[[ $(<"$ARASAKA_QDBUS_LOG") != *'ARASAKA_SHADER_WALLPAPER='* ]] || fail "missing rain must never reach wallpaper activation"
assert_eq "$initial_desktops" "$(<"$DESKTOP_STATE")" "deferred wallpaper must not write desktop state"
printf 'fixture\n' >"$artwork/shaders/Interactive_Rain.frag"
for _ in 1 2; do
    : >"$ARASAKA_QDBUS_LOG"
    PATH="$fake_bin:$PATH" "$RECONCILER" --ensure-shader-wallpaper --hide-desktop-icons
    shader_log=$(<"$ARASAKA_QDBUS_LOG")
    [[ "$shader_log" == *'var ensureOnly = "true" === "true";'* ]] || fail "shader reconciliation should preserve existing shader selections"
    [[ "$shader_log" == *'var expectedConnectors = ["DP-1","eDP-1"];'* ]] || fail "shader reconciliation should cover all enabled outputs"
    [[ "$shader_log" == *'var hideDesktopIcons = true;'* ]] || fail "unchanged topology must still hide icons on new desktops"
    remaining_calls=${shader_log#*org.kde.PlasmaShell.evaluateScript}
    [[ "$remaining_calls" == *'org.kde.PlasmaShell.evaluateScript'* ]] || fail "hover must use a fresh evaluation after prepare commits"
    remaining_calls=${remaining_calls#*org.kde.PlasmaShell.evaluateScript}
    [[ "$remaining_calls" != *'org.kde.PlasmaShell.evaluateScript'* ]] || fail "activation should use exactly two evaluations"
    [[ "$shader_log" == *'var shaderPhase = "prepare";'*'var shaderPhase = "activate";'* ]] || fail "activation phases must run in order"
    [[ "$shader_log" != *'__DATA_HOME_JSON__'* ]] || fail "shader data home should be rendered"
    jq -e 'all(.[] | select(.id == 27 or .id == 42); .config.mouseEnabled == true and .config.arasakaRainPending == false and (.config.selectedShaderPath | endswith("/Interactive_Rain.frag")))' \
        "$DESKTOP_STATE" >/dev/null || fail "managed targets must finish with hover enabled and pending cleared"
    assert_eq "$(jq -c '[.[] | select(.id == 12 or .id == 99)]' <<<"$initial_desktops")" \
        "$(jq -c '[.[] | select(.id == 12 or .id == 99)]' "$DESKTOP_STATE")" "custom and parked desktops must remain unchanged"
done
printf 'previous-signature\n' >"$HOME/.local/state/arasaka-kde/topology"
if PATH="$fake_bin:$PATH" ARASAKA_BAD_SHADER_REPORT=1 "$RECONCILER" --ensure-shader-wallpaper >"$TEST_TMPDIR/error" 2>&1; then
    fail "invalid shader verification must fail reconciliation"
fi
assert_eq 'previous-signature' "$(<"$HOME/.local/state/arasaka-kde/topology")" "shader failure must not stamp topology success"

printf '%s\n' "$initial_desktops" >"$DESKTOP_STATE"
if PATH="$fake_bin:$PATH" ARASAKA_FAIL_SHADER_PHASE=activate "$RECONCILER" --ensure-shader-wallpaper >"$TEST_TMPDIR/error" 2>&1; then
    fail "interruption between evaluations must fail reconciliation"
fi
assert_eq 'previous-signature' "$(<"$HOME/.local/state/arasaka-kde/topology")" "interruption must not stamp topology success"
jq -e 'all(.[] | select(.id == 27 or .id == 42); .wallpaperPlugin == "online.knowmad.shaderwallpaper" and .config.mouseEnabled == false and .config.arasakaRainPending == true)' \
    "$DESKTOP_STATE" >/dev/null || fail "interrupted preparation must commit with mouse off and remain pending"
if PATH="$fake_bin:$PATH" REJECT_MOUSE_ENABLE=1 "$RECONCILER" --ensure-shader-wallpaper >"$TEST_TMPDIR/error" 2>&1; then
    fail "ignored mouse opt-in must not count as successful initialization"
fi
assert_eq 'previous-signature' "$(<"$HOME/.local/state/arasaka-kde/topology")" "ignored opt-in must retain retry state"
jq '(.[] | select(.id == 27) | .config.selectedShaderPath) = "file:///changed-by-user.frag"' "$DESKTOP_STATE" >"$TEST_TMPDIR/changed.json"
mv "$TEST_TMPDIR/changed.json" "$DESKTOP_STATE"
changed=$(jq -c '.[] | select(.id == 27) | .config.arasakaRainPending = false' "$DESKTOP_STATE")
PATH="$fake_bin:$PATH" "$RECONCILER" --ensure-shader-wallpaper
assert_eq "$changed" "$(jq -c '.[] | select(.id == 27)' "$DESKTOP_STATE")" "pending retry must never overwrite a new user selection or opt it into hover"
jq -e '.[] | select(.id == 42) | .config.mouseEnabled == true and .config.arasakaRainPending == false' \
    "$DESKTOP_STATE" >/dev/null || fail "unchanged pending target should finish on retry"
printf '%s\n' "$state" >"$HOME/.local/state/arasaka-kde/topology"

: >"$ARASAKA_QDBUS_LOG"
: >"$command_log"
PATH="$fake_bin:$PATH" "$RECONCILER" --dry-run --force --hide-desktop-icons --ensure-shader-wallpaper \
    --json "$TEST_DIR/fixtures/topology/internal-external.json" >/dev/null
assert_eq '' "$(<"$ARASAKA_QDBUS_LOG")" "dry-run with apply flags should remain offline"
assert_eq '' "$(<"$command_log")" "fixture dry-run should not query KScreen"
for args in '--unknown' '--json'; do
    if PATH="$fake_bin:$PATH" "$RECONCILER" --dry-run "$args" >"$TEST_TMPDIR/error" 2>&1; then
        fail "invalid dry-run argument should fail: $args"
    else
        assert_eq 2 "$?" "invalid arguments should return usage status"
    fi
done
if PATH="$fake_bin:$PATH" "$RECONCILER" --json "$TEST_TMPDIR/missing.json" >"$TEST_TMPDIR/error" 2>&1; then
    fail "--json without --dry-run should fail"
else
    assert_eq 2 "$?" "--json should be validated before reading the file"
fi

: >"$ARASAKA_QDBUS_LOG"
if PATH="$fake_bin:$PATH" ARASAKA_SHELL_OWNER= "$RECONCILER" --force >"$TEST_TMPDIR/error" 2>&1; then
    fail "missing shell owner should prevent layout application"
fi
[[ $(<"$ARASAKA_QDBUS_LOG") != *'org.kde.PlasmaShell.evaluateScript'* ]] || fail "invalid session token should never reach the layout"
assert_eq "$state" "$(<"$HOME/.local/state/arasaka-kde/topology")" "session query failure should preserve topology state"

printf 'reconcile_displays_test: PASS\n'
