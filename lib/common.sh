#!/usr/bin/env bash

set -euo pipefail

ARASAKA_PROJECT_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
readonly ARASAKA_PROJECT_ROOT

project_root() {
    printf '%s\n' "$ARASAKA_PROJECT_ROOT"
}

state_root() {
    printf '%s/arasaka-kde\n' "${XDG_STATE_HOME:-$HOME/.local/state}"
}

cache_root() {
    printf '%s/arasaka-kde\n' "${XDG_CACHE_HOME:-$HOME/.cache}"
}

snapshot_root() {
    printf '%s/snapshots\n' "$(state_root)"
}

log() {
    printf '%s\n' "$*" >&2
}

die() {
    log "error: $*"
    exit 1
}

require_command() {
    local command_name=$1

    command -v "$command_name" >/dev/null 2>&1 || die "required command not found: $command_name"
}

atomic_copy() {
    local source=$1
    local target=$2
    local temporary

    temporary=$(mktemp -- "${target}.tmp.XXXXXX")
    if ! cp --preserve=mode -- "$source" "$temporary"; then
        rm -f -- "$temporary"
        return 1
    fi
    if ! mv -f -- "$temporary" "$target"; then
        rm -f -- "$temporary"
        return 1
    fi
}
