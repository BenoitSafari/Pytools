"""NCZ (compressed NCA) decompression.

NCZ is a Zstandard-compressed NCA format used within NSZ containers.
Layout: 0x4000 bytes NCA header (unchanged) + NCZSECTN sections header + zstd stream.
Each section may require AES-CTR re-encryption after decompression.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import BinaryIO

NCA_HEADER_SIZE = 0x4000
NCZSECTN_MAGIC = b"NCZSECTN"
NCZBLOCK_MAGIC = b"NCZBLOCK"
CHUNK_SIZE = 0x10000  # 64 KiB read chunks


@dataclass
class Section:
    offset: int  # offset in decompressed NCA
    size: int  # decompressed size
    crypto_type: int  # 1=plain, 3/4=AES-CTR
    crypto_key: bytes  # 16 bytes
    crypto_counter: bytes  # 16 bytes


@dataclass
class BlockHeader:
    version: int
    block_type: int
    block_size_exponent: int
    num_blocks: int
    decompressed_size: int
    compressed_sizes: list[int]


def _parse_sections(stream: BinaryIO) -> list[Section]:
    magic = stream.read(8)
    if magic != NCZSECTN_MAGIC:
        raise ValueError(f"Bad NCZ magic: {magic!r}, expected {NCZSECTN_MAGIC!r}")

    count = struct.unpack("<q", stream.read(8))[0]
    sections: list[Section] = []
    for _ in range(count):
        data = stream.read(0x40)
        offset, size, crypto_type, _pad = struct.unpack_from("<qqqq", data, 0)
        crypto_key = data[0x20:0x30]
        crypto_counter = data[0x30:0x40]
        sections.append(
            Section(
                offset=offset,
                size=size,
                crypto_type=crypto_type,
                crypto_key=crypto_key,
                crypto_counter=crypto_counter,
            )
        )
    return sections


def _parse_block_header(stream: BinaryIO) -> BlockHeader | None:
    pos = stream.tell()
    magic = stream.read(8)
    if magic != NCZBLOCK_MAGIC:
        stream.seek(pos)
        return None

    version, btype, _unused, bs_exp = struct.unpack("<BBBB", stream.read(4))
    num_blocks = struct.unpack("<I", stream.read(4))[0]
    decompressed_size = struct.unpack("<q", stream.read(8))[0]
    compressed_sizes = [struct.unpack("<I", stream.read(4))[0] for _ in range(num_blocks)]

    return BlockHeader(
        version=version,
        block_type=btype,
        block_size_exponent=bs_exp,
        num_blocks=num_blocks,
        decompressed_size=decompressed_size,
        compressed_sizes=compressed_sizes,
    )


def _make_aes_ctr(key: bytes, nonce: bytes, offset: int):
    """Create an AES-CTR cipher seeked to *offset*."""
    from Crypto.Cipher import AES
    from Crypto.Util import Counter

    initial_value = offset >> 4
    ctr = Counter.new(64, prefix=nonce[:8], initial_value=initial_value)
    return AES.new(key, AES.MODE_CTR, counter=ctr)


def _decompress_stream(
    stream: BinaryIO,
    sections: list[Section],
    output: BinaryIO,
    decompressed_size: int,
) -> None:
    """Decompress a solid zstd stream and re-encrypt sections."""
    import zstandard

    dctx = zstandard.ZstdDecompressor()
    reader = dctx.stream_reader(stream)

    # Build a sorted list of section boundaries for crypto switching
    # Insert a fake plaintext section for the gap between NCA header and first real section
    all_sections: list[Section] = []
    if sections and sections[0].offset > NCA_HEADER_SIZE:
        all_sections.append(
            Section(
                offset=NCA_HEADER_SIZE,
                size=sections[0].offset - NCA_HEADER_SIZE,
                crypto_type=1,
                crypto_key=b"\x00" * 16,
                crypto_counter=b"\x00" * 16,
            )
        )
    all_sections.extend(sections)

    for section in all_sections:
        remaining = section.size
        pos = section.offset

        if section.crypto_type in (3, 4):
            cipher = _make_aes_ctr(section.crypto_key, section.crypto_counter, pos)
        else:
            cipher = None

        while remaining > 0:
            to_read = min(CHUNK_SIZE, remaining)
            chunk = reader.read(to_read)
            if not chunk:
                break
            if cipher:
                chunk = cipher.encrypt(chunk)
            output.write(chunk)
            remaining -= len(chunk)
            pos += len(chunk)


def _decompress_blocks(
    stream: BinaryIO,
    sections: list[Section],
    block_header: BlockHeader,
    output: BinaryIO,
) -> None:
    """Decompress block-compressed NCZ and re-encrypt sections."""
    import zstandard

    dctx = zstandard.ZstdDecompressor()
    block_size = 1 << block_header.block_size_exponent

    # Build section lookup: for each byte offset, which section applies
    all_sections: list[Section] = []
    if sections and sections[0].offset > NCA_HEADER_SIZE:
        all_sections.append(
            Section(
                offset=NCA_HEADER_SIZE,
                size=sections[0].offset - NCA_HEADER_SIZE,
                crypto_type=1,
                crypto_key=b"\x00" * 16,
                crypto_counter=b"\x00" * 16,
            )
        )
    all_sections.extend(sections)

    # Decompress all blocks sequentially
    decompressed_pos = NCA_HEADER_SIZE  # we start after the NCA header

    for i, comp_size in enumerate(block_header.compressed_sizes):
        # Determine decompressed block size
        if i < block_header.num_blocks - 1:
            decomp_block_size = block_size
        else:
            remainder = block_header.decompressed_size % block_size
            decomp_block_size = remainder if remainder else block_size

        compressed_data = stream.read(comp_size)
        if not compressed_data:
            break

        if comp_size < decomp_block_size:
            block_data = dctx.decompress(compressed_data, max_output_size=decomp_block_size)
        else:
            block_data = compressed_data

        # Apply crypto per-section within this block
        offset_in_block = 0
        while offset_in_block < len(block_data):
            # Find which section covers current position
            file_pos = decompressed_pos + offset_in_block
            current_section = None
            for s in all_sections:
                if s.offset <= file_pos < s.offset + s.size:
                    current_section = s
                    break

            if current_section is None:
                # Past all sections, write plaintext
                output.write(block_data[offset_in_block:])
                break

            # How much of this section fits in the remaining block
            section_end = current_section.offset + current_section.size
            chunk_end = min(len(block_data), section_end - decompressed_pos)
            chunk = block_data[offset_in_block:chunk_end]

            if current_section.crypto_type in (3, 4):
                cipher = _make_aes_ctr(
                    current_section.crypto_key,
                    current_section.crypto_counter,
                    file_pos,
                )
                chunk = cipher.encrypt(chunk)

            output.write(chunk)
            offset_in_block = chunk_end

        decompressed_pos += len(block_data)


def decompress_ncz(stream: BinaryIO, output: BinaryIO, ncz_size: int) -> int:
    """Decompress an NCZ stream to an NCA output stream.

    *stream* should be positioned at the start of the NCZ data.
    Returns the total bytes written.
    """
    # Step 1: Copy NCA header as-is
    nca_header = stream.read(NCA_HEADER_SIZE)
    output.write(nca_header)

    # Step 2: Parse section headers
    sections = _parse_sections(stream)

    # Step 3: Check for block compression
    block_header = _parse_block_header(stream)

    # Calculate total decompressed size from sections
    if sections:
        last = sections[-1]
        decompressed_size = last.offset + last.size
    else:
        decompressed_size = ncz_size

    # Step 4: Decompress
    if block_header:
        _decompress_blocks(stream, sections, block_header, output)
    else:
        _decompress_stream(stream, sections, output, decompressed_size)

    total = output.tell() if hasattr(output, "tell") else decompressed_size
    return total
