#!/bin/bash
set -euo pipefail

# psx-archiver - Entry point
# Delegates all logic to the Python package

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if ! command -v python3 &>/dev/null; then
    echo "Error: python3 is required but not found" >&2
    exit 1
fi

exec python3 -m psx_archiver "$@"
