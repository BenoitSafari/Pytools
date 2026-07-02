"""Small utilities shared by the nx-archiver CLI entry points.

Factors out three patterns previously copied into each command: human-readable
size formatting, input-file validation, and chunked copying of a binary stream.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import BinaryIO

COPY_CHUNK = 1 << 20  # 1 MiB


def format_size(num_bytes: float) -> str:
    """Format a size in bytes in a human-readable way (B/KB/MB/GB/TB)."""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def validate_input_file(path: Path, label: str = "Input") -> None:
    """Check that *path* exists; otherwise print an error to stderr and exit (code 1)."""
    if not path.exists():
        print(f"Error: {label} not found: {path}", file=sys.stderr)
        sys.exit(1)


def copy_file_chunked(src: BinaryIO, dst: BinaryIO, size: int, chunk: int = COPY_CHUNK) -> int:
    """Copy *size* bytes from *src* to *dst* in blocks. Returns the bytes written."""
    remaining = size
    written = 0
    while remaining:
        data = src.read(min(chunk, remaining))
        if not data:
            break
        dst.write(data)
        written += len(data)
        remaining -= len(data)
    return written
