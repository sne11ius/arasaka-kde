#!/usr/bin/env bash
# Resolve the real logged-in demo user's runtime; never start a synthetic D-Bus.
set -euo pipefail
exec python3 "$(dirname -- "${BASH_SOURCE[0]}")/guest_setup.py" session "$@"
