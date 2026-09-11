#!/usr/bin/env bash
# Runs only as demo inside the disposable, marked QEMU fixture.
set -euo pipefail
exec python3 "$(dirname -- "${BASH_SOURCE[0]}")/guest_setup.py" provision "$@"
