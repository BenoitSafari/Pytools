"""XCI (GameCard Image) parser and builder."""

from __future__ import annotations

import hashlib
import io
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO

from nx_archiver.hfs0 import (
    HFS0,
    HFS0Entry,
    FileSlice,
    build_hfs0,
    build_hfs0_empty,
    calc_hfs0_header_size,
    parse_hfs0,
)

PAGE_SIZE = 0x200
ROOT_HFS0_OFFSET = 0xF000
CARD_HEADER_OFFSET = 0x0
CARD_HEADER_MAGIC = b"HEAD"

# Standard layout: root HFS0 at 0xF000, then update at 0xF200, normal at 0xF400,
# secure at 0xF600. This matches what real XCIs look like.
ROOT_HFS0_HEADER_PADDED = 0x200  # root HFS0 header is padded to 0x200
EMPTY_PARTITION_SIZE = 0x200     # empty partitions are padded to 0x200
SECURE_PARTITION_OFFSET = 0xF600  # standard offset for secure partition

# GameCard size enum values
GAMECARD_SIZES: dict[int, int] = {
    1:  0xFA,   # 1 GB
    2:  0xF8,   # 2 GB
    4:  0xF0,   # 4 GB
    8:  0xE0,   # 8 GB
    16: 0xE1,   # 16 GB
    32: 0xE2,   # 32 GB
}
GAMECARD_SIZE_NAMES: dict[int, str] = {v: f"{k} GB" for k, v in GAMECARD_SIZES.items()}

PARTITION_NAMES = ["update", "normal", "secure"]


@dataclass
class XCIHeader:
    """Parsed XCI CardHeader."""
    raw: bytes  # full 0x200-byte header
    magic: bytes
    rom_area_start_page: int
    backup_area_start_page: int
    kek_index: int
    rom_size: int
    flags: int
    package_id: int
    valid_data_end_page: int
    partition_fs_header_address: int
    partition_fs_header_size: int
    partition_fs_header_hash: bytes  # 32 bytes


@dataclass
class XCIPartition:
    """One HFS0 partition inside the XCI."""
    name: str
    hfs0: HFS0
    absolute_offset: int  # absolute offset of this HFS0 in the XCI


@dataclass
class XCI:
    """Parsed XCI file."""
    header: XCIHeader
    root_hfs0: HFS0
    partitions: dict[str, XCIPartition] = field(default_factory=dict)


def parse_xci(stream: BinaryIO) -> XCI:
    """Parse an XCI file from *stream*."""
    stream.seek(CARD_HEADER_OFFSET)
    raw_header = stream.read(0x200)

    magic = raw_header[0x100:0x104]
    if magic != CARD_HEADER_MAGIC:
        raise ValueError(f"Bad XCI magic: {magic!r} at offset 0x100")

    header = XCIHeader(
        raw=raw_header,
        magic=magic,
        rom_area_start_page=struct.unpack_from("<I", raw_header, 0x104)[0],
        backup_area_start_page=struct.unpack_from("<I", raw_header, 0x108)[0],
        kek_index=raw_header[0x10C],
        rom_size=raw_header[0x10D],
        flags=raw_header[0x10F],
        package_id=struct.unpack_from("<Q", raw_header, 0x110)[0],
        valid_data_end_page=struct.unpack_from("<I", raw_header, 0x118)[0],
        partition_fs_header_address=struct.unpack_from("<Q", raw_header, 0x130)[0],
        partition_fs_header_size=struct.unpack_from("<Q", raw_header, 0x138)[0],
        partition_fs_header_hash=raw_header[0x140:0x160],
    )

    root = parse_hfs0(stream, header.partition_fs_header_address)

    partitions: dict[str, XCIPartition] = {}
    for entry in root.entries:
        child_hfs0 = parse_hfs0(stream, entry.offset)
        partitions[entry.name] = XCIPartition(
            name=entry.name,
            hfs0=child_hfs0,
            absolute_offset=entry.offset,
        )

    return XCI(header=header, root_hfs0=root, partitions=partitions)


def _gamecard_size_code(total_bytes: int) -> int:
    """Return the gamecard size enum for *total_bytes*."""
    gb = total_bytes / (1024 ** 3)
    for size_gb in sorted(GAMECARD_SIZES.keys()):
        if gb <= size_gb:
            return GAMECARD_SIZES[size_gb]
    return GAMECARD_SIZES[32]


def _source_size(src) -> int:
    if isinstance(src, FileSlice):
        return src.size
    elif isinstance(src, Path):
        return src.stat().st_size
    else:
        pos = src.tell()
        src.seek(0, 2)
        size = src.tell() - pos
        src.seek(pos)
        return size


def build_xci(
    secure_files: list[tuple[str, Path | BinaryIO | FileSlice]],
    output: BinaryIO,
    update_files: list[tuple[str, Path | BinaryIO | FileSlice]] | None = None,
    normal_files: list[tuple[str, Path | BinaryIO | FileSlice]] | None = None,
    logo_files: list[tuple[str, Path | BinaryIO | FileSlice]] | None = None,
    original_header: bytes | None = None,
) -> None:
    """Build an XCI file from NCA file references.

    *secure_files* — NCAs for the secure partition.
    *original_header* — if provided, preserves the original card header fields
    (key area, package ID, IV, etc.) and only updates structural fields.
    """
    update_files = update_files or []
    normal_files = normal_files or []
    logo_files = logo_files or []

    # Layout (matching real XCI structure):
    #   0x0000 - 0x01FF: Card header
    #   0x0200 - 0xEFFF: Padding / cert area
    #   0xF000 - 0xF1FF: Root HFS0 header (padded to 0x200)
    #   0xF200 - ...   : Child partitions (update, [logo,] normal, secure)
    # Partition order and offsets are dynamic based on actual sizes.

    # Step 1: Build non-secure partitions as padded HFS0s
    pre_partitions: list[tuple[str, bytes]] = []
    pre_partitions.append(("update", _build_padded_partition(update_files)))
    if logo_files:
        pre_partitions.append(("logo", _build_padded_partition(logo_files)))
    pre_partitions.append(("normal", _build_padded_partition(normal_files)))

    # For secure, calculate total size
    if secure_files:
        secure_header_size = calc_hfs0_header_size([n for n, _ in secure_files])
        secure_data_size = sum(_source_size(p) for _, p in secure_files)
        secure_total_size = secure_header_size + secure_data_size
    else:
        secure_total_size = EMPTY_PARTITION_SIZE

    # Step 2: Calculate actual secure partition offset
    pre_data_size = sum(len(data) for _, data in pre_partitions)
    secure_partition_offset = ROOT_HFS0_OFFSET + ROOT_HFS0_HEADER_PADDED + pre_data_size
    total_xci_size = secure_partition_offset + secure_total_size

    # Step 3: Build root HFS0 header with correct offsets and hashes
    names = [name for name, _ in pre_partitions] + ["secure"]
    child_sizes = [len(data) for _, data in pre_partitions] + [secure_total_size]
    child_hashes: list[bytes | None] = [
        hashlib.sha256(data[:0x200]).digest() for _, data in pre_partitions
    ] + [None]  # secure hash computed after building its header

    root_hfs0_header = _build_root_hfs0_header_with_hashes(
        names=names,
        child_sizes=child_sizes,
        child_hashes=child_hashes,
        secure_files=secure_files,
    )

    # Step 4: Build card header
    rom_area_start_page = secure_partition_offset // PAGE_SIZE
    valid_data_end_page = (total_xci_size + PAGE_SIZE - 1) // PAGE_SIZE - 1
    root_hash = hashlib.sha256(root_hfs0_header).digest()

    card_header = _build_card_header(
        rom_size_code=_gamecard_size_code(total_xci_size),
        valid_data_end_page=valid_data_end_page,
        root_hfs0_header_size=len(root_hfs0_header),
        root_hfs0_hash=root_hash,
        rom_area_start_page=rom_area_start_page,
        original_header=original_header,
    )

    # Step 5: Write everything
    output.write(card_header)
    output.write(b"\x00" * (ROOT_HFS0_OFFSET - len(card_header)))
    output.write(root_hfs0_header)
    for _, data in pre_partitions:
        output.write(data)

    if secure_files:
        build_hfs0(secure_files, output)
    else:
        output.write(b"\x00" * EMPTY_PARTITION_SIZE)


def _build_padded_partition(
    files: list[tuple[str, Path | BinaryIO | FileSlice]],
) -> bytes:
    """Build a partition HFS0, padded to page boundary (0x200)."""
    buf = io.BytesIO()
    if files:
        build_hfs0(files, buf)
    else:
        build_hfs0_empty(buf)
    data = buf.getvalue()
    # Pad to at least 0x200 bytes
    if len(data) < EMPTY_PARTITION_SIZE:
        data += b"\x00" * (EMPTY_PARTITION_SIZE - len(data))
    # Pad to page boundary so subsequent partitions are page-aligned
    remainder = len(data) % PAGE_SIZE
    if remainder:
        data += b"\x00" * (PAGE_SIZE - remainder)
    return data


def _build_root_hfs0_header_with_hashes(
    names: list[str],
    child_sizes: list[int],
    child_hashes: list[bytes | None],
    secure_files: list[tuple[str, Path | BinaryIO | FileSlice]],
) -> bytes:
    """Build the root HFS0 header with proper SHA-256 hashes, padded to 0x200."""
    from nx_archiver.hfs0 import MAGIC, ENTRY_SIZE, HEADER_SIZE

    # Build string table — pad to make total header = 0x200
    file_count = len(names)
    str_table = bytearray()
    name_offsets: list[int] = []
    for name in names:
        name_offsets.append(len(str_table))
        str_table.extend(name.encode("ascii") + b"\x00")

    # Pad string table so total header = 0x200
    entries_size = file_count * ENTRY_SIZE
    used = HEADER_SIZE + entries_size + len(str_table)
    padding_needed = ROOT_HFS0_HEADER_PADDED - used
    if padding_needed > 0:
        str_table.extend(b"\x00" * padding_needed)

    # Compute secure partition hash if needed
    # The hashed region for the secure partition covers its HFS0 header
    secure_hashed_size = EMPTY_PARTITION_SIZE
    secure_idx = names.index("secure")
    if child_hashes[secure_idx] is None and secure_files:
        secure_header_bytes = _build_hfs0_header_only(secure_files)
        secure_hashed_size = len(secure_header_bytes)
        # Hash the full secure HFS0 header
        child_hashes[secure_idx] = hashlib.sha256(secure_header_bytes).digest()

    buf = io.BytesIO()
    buf.write(struct.pack("<4sIII", MAGIC, file_count, len(str_table), 0))

    data_off = 0
    for i in range(file_count):
        if names[i] == "secure":
            hashed_size = secure_hashed_size
        else:
            hashed_size = min(EMPTY_PARTITION_SIZE, child_sizes[i])

        entry = struct.pack("<QQII8x", data_off, child_sizes[i], name_offsets[i], hashed_size)
        buf.write(entry)
        buf.write(child_hashes[i] or (b"\x00" * 32))
        data_off += child_sizes[i]

    buf.write(str_table)
    result = buf.getvalue()

    # Ensure exactly 0x200
    if len(result) < ROOT_HFS0_HEADER_PADDED:
        result += b"\x00" * (ROOT_HFS0_HEADER_PADDED - len(result))

    return result[:ROOT_HFS0_HEADER_PADDED]


def _build_hfs0_header_only(
    files: list[tuple[str, Path | BinaryIO | FileSlice]],
) -> bytes:
    """Build just the HFS0 header (no file data) for hash computation."""
    from nx_archiver.hfs0 import MAGIC, ENTRY_SIZE, HEADER_SIZE, DEFAULT_HASHED_REGION_SIZE, _resolve_source

    str_table = bytearray()
    name_offsets: list[int] = []
    for name, _ in files:
        name_offsets.append(len(str_table))
        str_table.extend(name.encode("ascii") + b"\x00")
    while len(str_table) % 0x10:
        str_table.append(0)

    file_count = len(files)
    buf = io.BytesIO()
    buf.write(struct.pack("<4sIII", MAGIC, file_count, len(str_table), 0))

    data_off = 0
    for i, (name, src) in enumerate(files):
        sz, h, _ = _resolve_source(src, DEFAULT_HASHED_REGION_SIZE)
        hashed_size = min(DEFAULT_HASHED_REGION_SIZE, sz)
        entry = struct.pack("<QQIIxxxxxxxx", data_off, sz, name_offsets[i], hashed_size)
        buf.write(entry)
        buf.write(h)
        data_off += sz

    buf.write(str_table)
    return buf.getvalue()


def _build_card_header(
    rom_size_code: int,
    valid_data_end_page: int,
    root_hfs0_header_size: int,
    root_hfs0_hash: bytes,
    rom_area_start_page: int,
    original_header: bytes | None = None,
) -> bytes:
    """Build a 0x200-byte XCI card header."""
    if original_header and len(original_header) >= 0x200:
        # Start from original header, only update structural fields
        header = bytearray(original_header[:0x200])
    else:
        header = bytearray(0x200)
        # Set minimal required fields for a new header
        header[0x10C] = 0x00  # kek index
        struct.pack_into("<I", header, 0x108, 0xFFFFFFFF)  # backup area
        struct.pack_into("<I", header, 0x180, 0x01)  # SelSec
        struct.pack_into("<I", header, 0x184, 0x02)  # SelT1Key

    # Always set/update structural fields
    header[0x100:0x104] = CARD_HEADER_MAGIC
    struct.pack_into("<I", header, 0x104, rom_area_start_page)
    struct.pack_into("<I", header, 0x108, 0xFFFFFFFF)
    header[0x10D] = rom_size_code
    struct.pack_into("<I", header, 0x118, valid_data_end_page)
    struct.pack_into("<Q", header, 0x130, ROOT_HFS0_OFFSET)
    struct.pack_into("<Q", header, 0x138, root_hfs0_header_size)
    header[0x140:0x160] = root_hfs0_hash

    # LimArea = rom_area_start_page (where secure data begins)
    struct.pack_into("<I", header, 0x18C, rom_area_start_page)

    return bytes(header)
