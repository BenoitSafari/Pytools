"""Low-level I/O utilities shared within the nx-archiver package."""

from __future__ import annotations

from typing import BinaryIO

COPY_CHUNK = 1 << 20  # 1 MiB


def copy_stream(src: BinaryIO, dst: BinaryIO, size: int, chunk: int = COPY_CHUNK) -> int:
    """Copy *size* bytes from *src* to *dst* in blocks of *chunk* bytes.

    Returns the number of bytes actually written (may be less than *size*
    if the source runs dry first).
    """
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
