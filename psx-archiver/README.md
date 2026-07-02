# psx-archiver

Three-step archiving pipeline for **PlayStation** disc images (PS1 / PS2 / PSP):

1. **Extraction** of archives (`.7z`, `.zip`, `.rar`, …) via `7z`;
2. **Conversion** to a compact format — CHD for PS1, CSO for PS2/PSP;
3. **Standardized renaming** based on the game serial and the PSXDatacenter database.

## Requirements

- Python ≥ 3.10 (no Python dependencies)
- External tools on the `PATH` (depending on the platform):
  - **7z** — extraction (all platforms)
  - **chdman** — CHD conversion (PS1)
  - **maxcso** or **ciso** — CSO conversion (PS2/PSP)

Installation hints are shown automatically if a tool is missing (apt, pacman,
brew, winget/scoop/choco depending on the OS).

## Installation

```bash
pip install -e .
# provides the `psx-archiver` command on the PATH
```

Without installation, use the launchers:

```bash
./psx-archiver.sh --platform ps1 ./roms ./out       # Linux / macOS
.\psx-archiver.ps1 --platform ps1 .\roms .\out      # Windows (PowerShell)
```

## Usage

```bash
psx-archiver --platform ps1 ./roms ./out
psx-archiver --platform ps2 --skip-extract --dry-run ./iso ./out
```

Useful options: `--dry-run`, `--delete-source`, `--skip-extract`, `--skip-convert`,
`--skip-rename`. See `psx-archiver --help`.

## Environment variables

| Variable         | Role                                  | Default                                |
| ---------------- | ------------------------------------- | -------------------------------------- |
| `PSX_ARCHIVER_DB`| Path to the serials CSV database      | `db/psxdatacenter.csv` (packaged)      |
