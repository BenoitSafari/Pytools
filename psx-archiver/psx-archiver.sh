#!/usr/bin/env bash
#
# psx-archiver — cross-platform launcher (Linux/macOS)
# ----------------------------------------------------
# PlayStation disc image archiving pipeline: extraction (7z),
# conversion (CHD for PS1, CSO for PS2/PSP) then renaming via a serials database.
# Delegates to the Python package `psx_archiver`; all options are forwarded.
#
# Usage:
#   ./psx-archiver.sh --platform {ps1|ps2|psp} [options] <input_dir> <output_dir>
#   ./psx-archiver.sh --help
#
# Examples:
#   ./psx-archiver.sh --platform ps1 ./roms ./out
#   ./psx-archiver.sh --platform ps2 --skip-extract --dry-run ./iso ./out
#
# No pip installation required: the script directory is added to PYTHONPATH.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PYTHON="$(command -v python3 || command -v python || true)"
if [[ -z "$PYTHON" ]]; then
    echo "Error: Python 3 is required but was not found (install python3)." >&2
    exit 1
fi

export PYTHONPATH="$SCRIPT_DIR${PYTHONPATH:+:$PYTHONPATH}"
exec "$PYTHON" -m psx_archiver "$@"
