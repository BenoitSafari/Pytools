"""Extract game serial from PlayStation disc images.

PS1 discs contain a SYSTEM.CNF file with:  BOOT = cdrom:\\SLUS_012.34;1
PS2 discs contain a SYSTEM.CNF file with:  BOOT2 = cdrom0:\\SLUS_216.24;1
The serial is extracted and normalized to the standard format: SLUS-01234
"""

import os
import re
import struct
import subprocess
import tempfile
import zlib
from pathlib import Path

# Matches serials like SLUS_012.34 or SCUS-94163
SERIAL_PATTERN = re.compile(
    r"([A-Z]{4})[_\-](\d{3})[._](\d{2})", re.ASCII
)

# Matches BOOT line in SYSTEM.CNF (PS1: BOOT, PS2: BOOT2)
BOOT_PATTERN = re.compile(
    rb"BOOT2?\s*=\s*cdrom\d?[:\\/]+\\?([A-Z]{4}[_\-]\d{3}[._]\d{2})",
    re.IGNORECASE,
)


def normalize_serial(raw):
    """Convert 'SLUS_012.34' or 'SLUS-01234' to 'SLUS-01234'."""
    m = SERIAL_PATTERN.search(raw)
    if not m:
        return None
    prefix, mid, end = m.group(1), m.group(2), m.group(3)
    return f"{prefix}-{mid}{end}"


def extract_serial_from_bin(bin_path):
    """Extract serial from a raw BIN/IMG file by scanning for SYSTEM.CNF content.

    Reads the first 1MB which is enough to find SYSTEM.CNF on any PS1 disc.
    """
    bin_path = Path(bin_path)
    if not bin_path.is_file():
        return None

    read_size = 1024 * 1024  # 1 MB
    try:
        with open(bin_path, "rb") as f:
            data = f.read(read_size)
    except OSError:
        return None

    m = BOOT_PATTERN.search(data)
    if m:
        return normalize_serial(m.group(1).decode("ascii", errors="ignore"))

    # Fallback: look for any serial-like pattern near "BOOT" or license text
    fallback = re.search(
        rb"([A-Z]{4}[_\-]\d{3}[._]\d{2})", data[:read_size]
    )
    if fallback:
        candidate = normalize_serial(
            fallback.group(1).decode("ascii", errors="ignore")
        )
        if candidate:
            return candidate

    return None


def extract_serial_from_cue(cue_path):
    """Extract serial from a game by finding the data track BIN from a .cue file."""
    cue_path = Path(cue_path)
    if not cue_path.is_file():
        return None

    cue_dir = cue_path.parent
    # Parse .cue to find the first FILE reference (data track)
    try:
        content = cue_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    # CUE FILE lines look like: FILE "filename.bin" BINARY
    m = re.search(r'FILE\s+"([^"]+)"', content)
    if not m:
        return None

    bin_name = m.group(1)
    bin_path = cue_dir / bin_name
    if not bin_path.is_file():
        # Try case-insensitive match
        for f in cue_dir.iterdir():
            if f.name.lower() == bin_name.lower():
                bin_path = f
                break
        else:
            return None

    return extract_serial_from_bin(bin_path)


def extract_serial_from_chd(chd_path):
    """Extract serial from a CHD file by temporarily extracting with chdman."""
    chd_path = Path(chd_path)
    if not chd_path.is_file():
        return None

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_cue = os.path.join(tmpdir, "temp.cue")
        tmp_bin = os.path.join(tmpdir, "temp.bin")

        result = subprocess.run(
            ["chdman", "extractcd", "-i", str(chd_path), "-o", tmp_cue, "-ob", tmp_bin],
            capture_output=True,
        )

        if result.returncode != 0:
            return None

        return extract_serial_from_bin(tmp_bin)


def extract_serial_from_iso(iso_path):
    """Extract serial from an ISO9660 file by scanning for SYSTEM.CNF content.

    Works for both PS1 and PS2 ISOs. Reads the first 1MB which is enough
    to find SYSTEM.CNF on any PlayStation disc.
    """
    iso_path = Path(iso_path)
    if not iso_path.is_file():
        return None

    read_size = 1024 * 1024  # 1 MB
    try:
        with open(iso_path, "rb") as f:
            data = f.read(read_size)
    except OSError:
        return None

    m = BOOT_PATTERN.search(data)
    if m:
        return normalize_serial(m.group(1).decode("ascii", errors="ignore"))

    # Fallback: look for any serial-like pattern
    fallback = re.search(rb"([A-Z]{4}[_\-]\d{3}[._]\d{2})", data)
    if fallback:
        candidate = normalize_serial(
            fallback.group(1).decode("ascii", errors="ignore")
        )
        if candidate:
            return candidate

    return None


def _read_cso_blocks(cso_path, num_bytes):
    """Read and decompress the first num_bytes from a CSO file.

    CSO format:
      Header (24 bytes): magic "CISO", header_size, total_bytes, block_size, ver, align
      Index: (num_blocks+1) * 4 bytes, each uint32
        bit 31 = uncompressed flag, bits 0-30 = offset >> alignment
      Blocks: zlib-compressed or raw data
    """
    with open(cso_path, "rb") as f:
        # Read header
        header = f.read(24)
        if len(header) < 24 or header[:4] != b"CISO":
            return None

        _hdr_size, total_bytes = struct.unpack_from("<IQ", header, 4)
        block_size, ver, align = struct.unpack_from("<IBB", header, 16)

        if block_size == 0:
            return None

        total_blocks = (total_bytes + block_size - 1) // block_size
        blocks_needed = min((num_bytes + block_size - 1) // block_size, total_blocks)

        # Read index (blocks_needed + 1 entries to get end offset of last block)
        index_size = (blocks_needed + 1) * 4
        index_data = f.read(index_size)
        if len(index_data) < index_size:
            return None

        index = struct.unpack(f"<{blocks_needed + 1}I", index_data)

        result = bytearray()
        for i in range(blocks_needed):
            idx_val = index[i]
            idx_next = index[i + 1]

            is_plain = (idx_val >> 31) & 1
            offset = (idx_val & 0x7FFFFFFF) << align
            next_offset = (idx_next & 0x7FFFFFFF) << align
            comp_size = next_offset - offset

            if comp_size <= 0 or comp_size > block_size * 2:
                result.extend(b"\x00" * block_size)
                continue

            f.seek(offset)
            block_data = f.read(comp_size)

            if is_plain:
                result.extend(block_data)
            else:
                try:
                    result.extend(zlib.decompress(block_data, -15))
                except zlib.error:
                    try:
                        result.extend(zlib.decompress(block_data))
                    except zlib.error:
                        result.extend(b"\x00" * block_size)

    return bytes(result[:num_bytes])


def extract_serial_from_cso(cso_path):
    """Extract serial from a CSO file by decompressing the first blocks.

    Decompresses just enough data (~1MB) to find SYSTEM.CNF.
    """
    cso_path = Path(cso_path)
    if not cso_path.is_file():
        return None

    try:
        data = _read_cso_blocks(cso_path, 1024 * 1024)
    except (OSError, struct.error):
        return None

    if not data:
        return None

    m = BOOT_PATTERN.search(data)
    if m:
        return normalize_serial(m.group(1).decode("ascii", errors="ignore"))

    # Fallback
    fallback = re.search(rb"([A-Z]{4}[_\-]\d{3}[._]\d{2})", data)
    if fallback:
        candidate = normalize_serial(
            fallback.group(1).decode("ascii", errors="ignore")
        )
        if candidate:
            return candidate

    return None
