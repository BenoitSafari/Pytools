#!/usr/bin/env bash
#
# nx-archiver — cross-platform launcher (Linux/macOS)
# --------------------------------------------------
# Tools for manipulating Nintendo Switch containers (XCI / NSP / NSZ).
# Delegates to the Python package `nx_archiver`; all options are forwarded.
#
# Usage:
#   ./nx-archiver.sh <command> [options]
#   ./nx-archiver.sh --help
#
# Commands:
#   make-xci      Builds one XCI per game from a folder of NSP/NSZ files
#   nsp-to-xci    Converts one or more NSP/NSZ files into a single XCI
#   xci-extract   Extracts the NCAs from an XCI
#   xci-modify    Adds/removes NCAs in an XCI
#   xci-update    Replaces the update NCAs of an XCI with a new update
#   xci-trim      Removes the 0xFF padding from an XCI (lossless trim)
#
# Examples:
#   ./nx-archiver.sh make-xci ./nsp --dry-run
#   ./nx-archiver.sh xci-extract game.xci -o out/
#
# The Switch keys are read from $NX_KEYS_DIR (default: ~/.switch/prod.keys).
# No pip install required: the script's folder is added to PYTHONPATH.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PYTHON="$(command -v python3 || command -v python || true)"
if [[ -z "$PYTHON" ]]; then
    echo "Error: Python 3 is required but was not found (install python3)." >&2
    exit 1
fi

export PYTHONPATH="$SCRIPT_DIR${PYTHONPATH:+:$PYTHONPATH}"
exec "$PYTHON" -m nx_archiver "$@"
