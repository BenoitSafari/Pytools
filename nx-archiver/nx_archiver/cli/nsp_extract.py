"""Extraction of an NSP/NSZ file into a temporary folder.

Handles both formats transparently:

- **NSP**: the entries are copied as-is;
- **NSZ**: the ``.ncz`` entries are decompressed to ``.nca``.

Factors out a pattern previously copied into ``make_xci``, ``nsp_to_xci`` and
``xci_update``.
"""

from __future__ import annotations

from pathlib import Path

from nx_archiver.cli._common import copy_file_chunked, format_size
from nx_archiver.ncz import decompress_ncz
from nx_archiver.pfs0 import parse_pfs0


def extract_nsp(nsp_path: Path, tmpdir: Path, verbose: bool = False) -> list[Path]:
    """Extract *nsp_path* into *tmpdir* and return the list of written files.

    The ``.ncz`` entries (compressed NCAs, specific to NSZ) are decompressed
    to ``.nca``; the other entries are copied as-is. If *verbose*, each entry
    is logged to standard output.
    """
    paths: list[Path] = []

    with open(nsp_path, "rb") as fh:
        pfs0 = parse_pfs0(fh)
        for entry in pfs0.entries:
            if entry.name.endswith(".ncz"):
                nca_name = entry.name[:-4] + ".nca"
                out_path = tmpdir / nca_name
                if verbose:
                    print(f"    {entry.name} -> {nca_name} (decompressing...)")
                fh.seek(entry.offset)
                with open(out_path, "wb") as out:
                    decompress_ncz(fh, out, entry.size)
            else:
                out_path = tmpdir / entry.name
                if verbose:
                    print(f"    {entry.name} ({format_size(entry.size)})")
                fh.seek(entry.offset)
                with open(out_path, "wb") as out:
                    copy_file_chunked(fh, out, entry.size)
            paths.append(out_path)

    return paths
