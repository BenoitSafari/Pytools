"""nx-archiver — manipulation of Nintendo Switch containers (XCI / NSP / NSZ).

High-level public API. The command-line entry points live in the
:mod:`nx_archiver.cli` subpackage.
"""

from __future__ import annotations

from nx_archiver.hfs0 import FileSlice, build_hfs0, parse_hfs0
from nx_archiver.keys import get_header_key, load_keys, load_title_keys
from nx_archiver.nca import parse_nca_header, read_nca_info
from nx_archiver.ncz import decompress_ncz
from nx_archiver.pfs0 import build_pfs0, parse_pfs0
from nx_archiver.xci import build_xci, parse_xci

__version__ = "0.1.0"

__all__ = [
    "FileSlice",
    "build_hfs0",
    "parse_hfs0",
    "build_pfs0",
    "parse_pfs0",
    "build_xci",
    "parse_xci",
    "decompress_ncz",
    "load_keys",
    "load_title_keys",
    "get_header_key",
    "parse_nca_header",
    "read_nca_info",
]
