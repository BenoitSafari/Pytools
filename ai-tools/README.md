# ai-tools

Utilities for AI and agents:

- **`claude-export`** — exports local Claude Code / Claude Desktop data
  (sessions, plans, settings, logs) into a portable ZIP archive.
- **`img-resize`** — resizes and compresses images (PNG/JPEG/WebP) for the web.

## Requirements

- Python ≥ 3.10
- [Pillow](https://pillow.readthedocs.io/) (installed automatically) for `img-resize`

## Installation

```bash
pip install -e .
# provides the `claude-export` and `img-resize` commands on the PATH
```

Without installing, use the launchers (the folder is added to `PYTHONPATH`):

```bash
./ai-tools.sh <command> [options]        # Linux / macOS
.\ai-tools.ps1 <command> [options]       # Windows (PowerShell)
```

## Usage

```bash
claude-export --dry-run                  # list what would be exported
claude-export --output ~/backup.zip      # create the archive

img-resize photos/ --max-dim 1920 -o out/    # bound the longest side to 1920 px
img-resize logo.png -f webp -q 80             # convert to WebP quality 80
```

Every command accepts `--help`.

## Environment variables

| Variable             | Role                                   | Default                                                                 |
| -------------------- | -------------------------------------- | ---------------------------------------------------------------------- |
| `CLAUDE_CODE_DIR`    | Claude Code data folder                | `~/.claude`                                                            |
| `CLAUDE_DESKTOP_DIR` | Claude Desktop config folder           | Windows: `%APPDATA%\Claude` · macOS: `~/Library/Application Support/Claude` · Linux: `~/.config/Claude` |

> The `.credentials.json` file (OAuth tokens) is **always excluded** from the export.
