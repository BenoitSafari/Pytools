# nx-archiver

Tools for manipulating **Nintendo Switch** containers (XCI / NSP / NSZ):
extraction, conversion, merging and trimming — all in pure Python, with no
dependency on external tools.

## Commands

| Command       | Purpose                                                      |
| ------------- | ------------------------------------------------------------ |
| `make-xci`    | Builds one XCI per game from a folder of NSP/NSZ files        |
| `nsp-to-xci`  | Converts one or more NSP/NSZ files into a single XCI          |
| `xci-extract` | Extracts the NCAs from an XCI (option: rebuild as NSP)        |
| `xci-modify`  | Adds / removes NCAs in an XCI                                |
| `xci-update`  | Replaces the update NCAs of an XCI with a new update          |
| `xci-trim`    | Removes the 0xFF padding from an XCI (lossless trim)         |

## Requirements

- Python ≥ 3.10
- [pycryptodome](https://pycryptodome.readthedocs.io/) and
  [zstandard](https://pypi.org/project/zstandard/) (installed automatically)
- The Switch decryption keys (`prod.keys`) — see the environment variable below

## Installation

```bash
pip install -e .
# provides make-xci, nsp-to-xci, xci-extract, xci-modify, xci-update, xci-trim
```

Without installing, use the launchers (subcommand dispatcher):

```bash
./nx-archiver.sh <command> [options]         # Linux / macOS
.\nx-archiver.ps1 <command> [options]        # Windows (PowerShell)
```

## Usage

```bash
make-xci ./nsp --dry-run                 # preview the per-game groupings
make-xci ./nsp -o ./xci                  # build the XCIs
xci-extract game.xci -o out/             # extract the NCAs
xci-trim game.xci --in-place             # remove the padding, in place
```

Every command accepts `--help`.

## Environment variables

| Variable      | Purpose                                         | Default               |
| ------------- | ----------------------------------------------- | --------------------- |
| `NX_KEYS_DIR` | Folder containing `prod.keys` / `title.keys`    | `~/.switch`           |

> The Switch keys are **not** provided: they must be obtained from your own
> console.
