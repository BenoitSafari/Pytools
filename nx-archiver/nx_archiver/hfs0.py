"""HFS0 (Hashed File System) parser and builder -- used inside XCI files."""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from nx_archiver._io import copy_stream

MAGIC = b"HFS0"
ENTRY_SIZE = 0x40
HEADER_SIZE = 0x10
COPY_BUF = 1 << 20  # 1 MiB
DEFAULT_HASHED_REGION_SIZE = 0x200

# A file source can be a Path, a BinaryIO, or a FileSlice (offset+size in a file)
FileSource = "Path | BinaryIO | FileSlice"


@dataclass
class FileSlice:
    """Reference to a region inside an existing file (avoids copying to temp)."""

    path: Path
    offset: int
    size: int


@dataclass
class HFS0Entry:
    name: str
    offset: int  # absolute offset of file data in the stream
    size: int
    hashed_region_size: int
    sha256: bytes  # 32-byte hash of first hashed_region_size bytes


@dataclass
class HFS0:
    entries: list[HFS0Entry]
    data_offset: int  # absolute offset where file data region starts
    header_size: int  # total header size (header + entries + string table)

    def extract(self, stream: BinaryIO, entry: HFS0Entry, out: BinaryIO) -> None:
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
        """Extract every entry to *out_dir*."""
        out_dir.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []
        for entry in self.entries:
            dest = out_dir / entry.name
            with open(dest, "wb") as fh:
                self.extract(stream, entry, fh)
            paths.append(dest)
        return paths


def parse_hfs0(stream: BinaryIO, base_offset: int | None = None) -> HFS0:
    """Parse an HFS0 container from *stream*."""
    if base_offset is None:
        base_offset = stream.tell()
    else:
        stream.seek(base_offset)

    header = stream.read(HEADER_SIZE)
    magic = header[0:4]
    if magic != MAGIC:
        raise ValueError(f"Bad HFS0 magic: {magic!r} at offset 0x{base_offset:X}")

    file_count = struct.unpack_from("<I", header, 4)[0]
    str_table_size = struct.unpack_from("<I", header, 8)[0]

    entry_data = stream.read(file_count * ENTRY_SIZE + str_table_size)
    header_total = HEADER_SIZE + file_count * ENTRY_SIZE + str_table_size
    data_region_offset = base_offset + header_total

    entries: list[HFS0Entry] = []
    for i in range(file_count):
        off = i * ENTRY_SIZE
        data_off = struct.unpack_from("<Q", entry_data, off)[0]
        data_size = struct.unpack_from("<Q", entry_data, off + 8)[0]
        name_off = struct.unpack_from("<I", entry_data, off + 16)[0]
        hashed_size = struct.unpack_from("<I", entry_data, off + 20)[0]
        sha256 = entry_data[off + 0x20 : off + 0x40]

        str_start = file_count * ENTRY_SIZE
        end = entry_data.index(b"\x00", str_start + name_off)
        name = entry_data[str_start + name_off : end].decode("ascii")

        entries.append(
            HFS0Entry(
                name=name,
                offset=data_region_offset + data_off,
                size=data_size,
                hashed_region_size=hashed_size,
                sha256=sha256,
            )
        )

    return HFS0(entries=entries, data_offset=data_region_offset, header_size=header_total)


def calc_hfs0_header_size(names: list[str]) -> int:
    """Calculate header size for a set of file names."""
    str_table_size = sum(len(n.encode("ascii")) + 1 for n in names)
    # Pad string table
    while str_table_size % 0x10:
        str_table_size += 1
    return HEADER_SIZE + len(names) * ENTRY_SIZE + str_table_size


def _resolve_source(src, hashed_region_size):
    """Return (size, hash_bytes, source) for a file source."""
    if isinstance(src, FileSlice):
        with open(src.path, "rb") as fh:
            fh.seek(src.offset)
            hash_data = fh.read(min(hashed_region_size, src.size))
        return src.size, hashlib.sha256(hash_data).digest(), src
    elif isinstance(src, Path):
        sz = src.stat().st_size
        with open(src, "rb") as fh:
            hash_data = fh.read(min(hashed_region_size, sz))
        return sz, hashlib.sha256(hash_data).digest(), src
    else:
        pos = src.tell()
        src.seek(0, 2)
        sz = src.tell() - pos
        src.seek(pos)
        hash_data = src.read(min(hashed_region_size, sz))
        src.seek(pos)
        return sz, hashlib.sha256(hash_data).digest(), src


def _write_source(src, output, size):
    """Write a file source to output, return bytes written."""
    if isinstance(src, FileSlice):
        with open(src.path, "rb") as fh:
            fh.seek(src.offset)
            return copy_stream(fh, output, size)
    elif isinstance(src, Path):
        with open(src, "rb") as fh:
            return copy_stream(fh, output, size)
    else:
        return copy_stream(src, output, size)


def build_hfs0(
    files: list[tuple[str, Path | BinaryIO | FileSlice]],
    output: BinaryIO,
    hashed_region_size: int = DEFAULT_HASHED_REGION_SIZE,
) -> int:
    """Write an HFS0 container to *output*. Returns total bytes written.

    *files* is a list of ``(name, source)`` pairs where source can be
    a Path, BinaryIO, or FileSlice.
    """
    # Build string table
    str_table = bytearray()
    name_offsets: list[int] = []
    for name, _ in files:
        name_offsets.append(len(str_table))
        str_table.extend(name.encode("ascii") + b"\x00")
    while len(str_table) % 0x10:
        str_table.append(0)

    file_count = len(files)
    header_total = HEADER_SIZE + file_count * ENTRY_SIZE + len(str_table)

    # Pre-compute sizes and hashes
    sizes: list[int] = []
    hashes: list[bytes] = []
    sources: list[Path | BinaryIO | FileSlice] = []
    for _, src in files:
        sz, h, s = _resolve_source(src, hashed_region_size)
        sizes.append(sz)
        hashes.append(h)
        sources.append(s)

    # Write header
    output.write(struct.pack("<4sIII", MAGIC, file_count, len(str_table), 0))

    # Write entry table
    data_off = 0
    for i in range(file_count):
        entry = struct.pack(
            "<QQIIxxxxxxxx",  # 8+8+4+4+8 = 32 bytes, then 32 bytes hash = 0x40
            data_off,
            sizes[i],
            name_offsets[i],
            min(hashed_region_size, sizes[i]),
        )
        # entry is 32 bytes, append 32 bytes of hash
        output.write(entry)
        output.write(hashes[i])
        data_off += sizes[i]

    # Write string table
    output.write(str_table)

    # Write file data
    total = header_total
    for i, src in enumerate(sources):
        total += _write_source(src, output, sizes[i])

    return total


def build_hfs0_empty(output: BinaryIO, total_size: int = 0x200) -> int:
    """Write an empty HFS0 padded to *total_size*. Returns bytes written."""
    str_table_size = total_size - HEADER_SIZE
    header = struct.pack("<4sIII", MAGIC, 0, str_table_size, 0)
    output.write(header)
    output.write(b"\x00" * str_table_size)
    return total_size
