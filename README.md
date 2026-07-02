# Pytools

Monorepo of standalone, cross-platform Python command-line utilities
(Linux / Windows / macOS): **nx-archiver** (Nintendo Switch containers), **psx-archiver**
(PlayStation disc images), and **ai-tools** (Claude data export, image compression).

## Modules

| Folder                           | Role                                              | Console scripts                                                        | Launchers                       |
| -------------------------------- | ------------------------------------------------- | --------------------------------------------------------------------- | ------------------------------- |
| [`nx-archiver`](nx-archiver/)    | Nintendo Switch containers (XCI / NSP / NSZ)      | `make-xci`, `nsp-to-xci`, `xci-extract`, `xci-modify`, `xci-update`, `xci-trim` | `nx-archiver.sh` / `.ps1`  |
| [`psx-archiver`](psx-archiver/)  | PlayStation disc images (PS1 / PS2 / PSP)         | `psx-archiver`                                                        | `psx-archiver.sh` / `.ps1`      |
| [`ai-tools`](ai-tools/)          | Claude data export, image compression            | `claude-export`, `img-resize`                                        | `ai-tools.sh` / `.ps1`          |

Each module is **independent** (no code shared between modules): it has its own
`pyproject.toml`, launchers, and detailed `README.md`.

## Prerequisites

- **Python ≥ 3.10** (all platforms).
- External tools depending on the module:
  - `psx-archiver`: `7z`, `chdman`, `maxcso`/`ciso` (install hints shown if missing).
  - `ai-tools`: `Pillow` (Python dependency, installed automatically) for `img-resize`.
  - `nx-archiver`: pure Python dependencies (`pycryptodome`, `zstandard`) + Switch keys.

## Installation

```bash
# Install the three modules in editable mode (commands available on the PATH)
pip install -e ./nx-archiver ./psx-archiver ./ai-tools
```

Without installation, each module is used via its launcher (no `pip` required):

```bash
./nx-archiver/nx-archiver.sh --help            # Linux / macOS
.\nx-archiver\nx-archiver.ps1 --help           # Windows (PowerShell)
```

## Quick start

```bash
make-xci ./nsp --dry-run                        # nx-archiver
psx-archiver --platform ps1 ./roms ./out        # psx-archiver
claude-export --dry-run                         # ai-tools
img-resize photos/ --max-dim 1920 -o out/       # ai-tools
```

## Environment variables

References to files/folders outside the repository are configured through environment
variables:

| Variable             | Module         | Role                                        | Default                                                                |
| -------------------- | -------------- | ------------------------------------------- | ---------------------------------------------------------------------- |
| `NX_KEYS_DIR`        | nx-archiver    | Switch keys folder (`prod.keys`)            | `~/.switch`                                                            |
| `PSX_ARCHIVER_DB`    | psx-archiver   | CSV database of PlayStation serials         | `psx-archiver/db/psxdatacenter.csv` (packaged)                         |
| `CLAUDE_CODE_DIR`    | ai-tools       | Claude Code data folder                     | `~/.claude`                                                            |
| `CLAUDE_DESKTOP_DIR` | ai-tools       | Claude Desktop config folder                | Windows `%APPDATA%\Claude` · macOS `~/Library/Application Support/Claude` · Linux `~/.config/Claude` |

## Development — formatting & lint

The whole repository uses **[ruff](https://docs.astral.sh/ruff/)** as its single formatter
and linter (the Python equivalent of Prettier + ESLint), configured at the root in
[`ruff.toml`](ruff.toml):

```bash
ruff format .        # format (equivalent to Prettier)
ruff check .         # lint (equivalent to ESLint)
ruff check --fix .   # lint + automatic fixes
```

The Ruff extension (VS Code / PyCharm) applies formatting on fix-on-save.
An [`.editorconfig`](.editorconfig) ensures consistent formatting of the other
files (`.sh`, `.ps1`, `.toml`, `.md`).

## Summary

Three independent CLI tools, each with `.sh` **and** `.ps1` entry points documented
(`--help`), an installable `pyproject.toml`, and shared tooling configuration.
Portable across Linux/Windows/macOS; external paths are driven by environment
variables.
