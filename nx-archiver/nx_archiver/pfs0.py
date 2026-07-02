"""PFS0 (Partition File System) parser and builder -- the NSP container format."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from nx_archiver._io import copy_stream

MAGIC = b"PFS0"
ENTRY_SIZE = 0x18
HEADER_SIZE = 0x10
COPY_BUF = 1 << 20  # 1 MiB


@dataclass
class PFS0Entry:
    name: str
    offset: int  # absolute offset of file data in the stream
    size: int


@dataclass
class PFS0:
    entries: list[PFS0Entry]
    data_offset: int  # absolute offset where file data region starts

    def extract(self, stream: BinaryIO, entry: PFS0Entry, out: BinaryIO) -> None:
        """Copy *entry* data from *stream* into *out*."""
        stream.seek(entry.offset)
        remaining = entry.size
        while remaining:
            chunk = stream.read(min(COPY_BUF, remaining))
            if not chunk:
                break
            out.write(chunk)
            remaining -= len(chunk)

    def extract_all(self, stream: BinaryIO, out_dir: Path) -> list[Path]:
        """Extract every entry to *out_dir*. Returns list of written paths."""
        out_dir.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []
        for entry in self.entries:
            dest = out_dir / entry.name
            with open(dest, "wb") as fh:
                self.extract(stream, entry, fh)
            paths.append(dest)
        return paths


def parse_pfs0(stream: BinaryIO, base_offset: int | None = None) -> PFS0:
    """Parse a PFS0 container from *stream* at its current position.

    *base_offset* overrides ``stream.tell()`` as the header start offset
    (useful when you've already seeked).
    """
    if base_offset is None:
        base_offset = stream.tell()
    else:
        stream.seek(base_offset)

    header = stream.read(HEADER_SIZE)
    magic = header[0:4]
    if magic != MAGIC:
        raise ValueError(f"Bad PFS0 magic: {magic!r} (expected {MAGIC!r})")

    file_count = struct.unpack_from("<I", header, 4)[0]
    str_table_size = struct.unpack_from("<I", header, 8)[0]

    entry_data = stream.read(file_count * ENTRY_SIZE + str_table_size)
    data_region_offset = base_offset + HEADER_SIZE + file_count * ENTRY_SIZE + str_table_size

    entries: list[PFS0Entry] = []
    for i in range(file_count):
        off = i * ENTRY_SIZE
        data_off, data_size, name_off = struct.unpack_from("<QQI", entry_data, off)

        str_start = file_count * ENTRY_SIZE
        end = entry_data.index(b"\x00", str_start + name_off)
        name = entry_data[str_start + name_off : end].decode("ascii")

        entries.append(
            PFS0Entry(
                name=name,
                offset=data_region_offset + data_off,
                size=data_size,
            )
        )

    return PFS0(entries=entries, data_offset=data_region_offset)


def build_pfs0(files: list[tuple[str, Path | BinaryIO]], output: BinaryIO) -> None:
    """Write a PFS0 container to *output*.

    *files* is a list of ``(name, source)`` where *source* is either a
    ``Path`` to read from or an open ``BinaryIO`` (seeked to the start of the
    data, with a ``seek``/``tell`` pair to determine size).
    """
    # Build string table
    str_table = bytearray()
    name_offsets: list[int] = []
    for name, _ in files:
        name_offsets.append(len(str_table))
        str_table.extend(name.encode("ascii") + b"\x00")
    # Pad string table to 0x20 alignment (optional but conventional)
    while len(str_table) % 0x20:
        str_table.append(0)

    # Resolve sizes
    sizes: list[int] = []
    sources: list[Path | BinaryIO] = []
    for _, src in files:
        if isinstance(src, Path):
            sizes.append(src.stat().st_size)
        else:
            pos = src.tell()
            src.seek(0, 2)
            sizes.append(src.tell() - pos)
            src.seek(pos)
        sources.append(src)

    # Build header
    file_count = len(files)
    header = struct.pack("<4sIII", MAGIC, file_count, len(str_table), 0)

    # Build entry table
    entry_table = bytearray()
    data_off = 0
    for i in range(file_count):
        entry_table.extend(struct.pack("<QQI4x", data_off, sizes[i], name_offsets[i]))
        data_off += sizes[i]

    output.write(header)
    output.write(entry_table)
    output.write(str_table)

    # Write file data
    for i, src in enumerate(sources):
        if isinstance(src, Path):
            with open(src, "rb") as fh:
                copy_stream(fh, output, sizes[i])
        else:
            copy_stream(src, output, sizes[i])
