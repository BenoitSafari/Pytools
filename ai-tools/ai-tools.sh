#!/usr/bin/env bash
#
# ai-tools — cross-platform launcher (Linux/macOS)
# ------------------------------------------------
# Delegates to the `ai_tools` Python package. All options are passed through as-is.
#
# Usage:
#   ./ai-tools.sh <command> [options]
#   ./ai-tools.sh --help
#
# Commands:
#   claude-export   Export local Claude Code/Desktop data into a ZIP
#   img-resize      Resize and compress images (PNG/JPEG/WebP)
#
# Examples:
#   ./ai-tools.sh claude-export --dry-run
#   ./ai-tools.sh img-resize photos/ --max-dim 1920 -o out/
#
# No pip install required: the script's folder is added to PYTHONPATH.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PYTHON="$(command -v python3 || command -v python || true)"
if [[ -z "$PYTHON" ]]; then
    echo "Error: Python 3 is required but not found (install python3)." >&2
    exit 1
fi

export PYTHONPATH="$SCRIPT_DIR${PYTHONPATH:+:$PYTHONPATH}"
exec "$PYTHON" -m ai_tools "$@"
