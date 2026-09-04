#!/usr/bin/env bash

set -euo pipefail

fail() {
    printf 'FAIL: %s\n' "$*" >&2
    return 1
}

assert_eq() {
    local expected=$1
    local actual=$2
    local message=${3:-"expected values to be equal"}

    if [[ "$expected" != "$actual" ]]; then
        fail "$message (expected: '$expected', actual: '$actual')"
    fi
}

setup_temp_home() {
    TEST_TMPDIR=$(mktemp -d)
    export TEST_TMPDIR
    export HOME="$TEST_TMPDIR/home"
    unset XDG_STATE_HOME XDG_CACHE_HOME
    mkdir -p "$HOME"
    trap 'rm -rf -- "$TEST_TMPDIR"' EXIT
}
