#!/usr/bin/env bash

set -euo pipefail

TEST_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd -- "$TEST_DIR/.." && pwd)
FETCHER="$REPO_ROOT/bin/fetch-components"

# shellcheck source=tests/testlib.sh
source "$TEST_DIR/testlib.sh"
setup_temp_home
[[ -f "$FETCHER" ]] || fail "fetcher is missing: $FETCHER"

manifest="$TEST_TMPDIR/components.tsv"
source_file="$TEST_TMPDIR/component.txt"
fixture_sha256='137ba493fec6109d5fed024558f723eaa4696b82f5c6eb391e05c0957dd1fa45'
cp -- "$TEST_DIR/fixtures/component.txt" "$source_file"

write_manifest() {
    local name=$1
    local url=$2
    local sha256=$3
    local filename=$4

    printf 'name\tversion\turl\tsha256\tfilename\n' >"$manifest"
    printf '%s\tv1.0.0\t%s\t%s\t%s\n' "$name" "$url" "$sha256" "$filename" >>"$manifest"
}

run_fetcher() {
    ARASAKA_COMPONENT_MANIFEST="$manifest" \
        ARASAKA_TEST_ALLOW_FILE="${ARASAKA_TEST_ALLOW_FILE-}" \
        bash "$FETCHER" "$@"
}

file_url="file://$source_file"
write_manifest fixture "$file_url" "$fixture_sha256" component.txt

if output=$(run_fetcher fixture 2>&1); then
    fail "file URLs should be rejected without ARASAKA_TEST_ALLOW_FILE=1"
fi
[[ "$output" == *'only HTTPS URLs are allowed'* ]] || fail "file URL rejection should explain the HTTPS requirement"

export ARASAKA_TEST_ALLOW_FILE=1
cached_path=$(run_fetcher fixture)
assert_eq "$HOME/.cache/arasaka-kde/downloads/component.txt" "$cached_path" "valid artifact should return its cache path"
assert_eq 'fixture component' "$(<"$cached_path")" "valid artifact should be copied to the cache"

rm -- "$source_file"
cached_path_again=$(run_fetcher fixture)
assert_eq "$cached_path" "$cached_path_again" "a verified cache entry should be reused"

cp -- "$TEST_DIR/fixtures/component.txt" "$source_file"
write_manifest bad-hash "$file_url" '0000000000000000000000000000000000000000000000000000000000000000' bad-hash.txt
if output=$(run_fetcher bad-hash 2>&1); then
    fail "a mismatched SHA-256 should be rejected"
fi
[[ "$output" == *'SHA-256 verification failed'* ]] || fail "hash rejection should identify verification failure"
[[ ! -e "$HOME/.cache/arasaka-kde/downloads/bad-hash.txt" ]] || fail "a mismatched artifact should not enter the cache"

write_manifest traversal "$file_url" "$fixture_sha256" '../escaped.txt'
if output=$(run_fetcher traversal 2>&1); then
    fail "a filename containing ../ should be rejected"
fi
[[ "$output" == *'unsafe filename'* ]] || fail "filename rejection should identify the unsafe value"
[[ ! -e "$HOME/.cache/arasaka-kde/escaped.txt" ]] || fail "an unsafe filename should not escape the download cache"

# shellcheck source=bin/fetch-components
source "$FETCHER"
declare -F fetch_component >/dev/null || fail "fetcher should expose fetch_component when sourced"

printf 'fetch_components_test: PASS\n'
