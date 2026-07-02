"""Extract a game serial from a PlayStation disc image.

PS1 discs contain a SYSTEM.CNF file with:  BOOT  = cdrom:\\SLUS_012.34;1
PS2 discs contain a SYSTEM.CNF file with:  BOOT2 = cdrom0:\\SLUS_216.24;1
PSP discs contain UMD_DATA.BIN with:       ULUS-10080|DG|G|01.00
             and/or PARAM.SFO with:        DISC_ID = ULUS10080
The serial is extracted then normalized to the standard format: SLUS-01234
"""

from __future__ import annotations

import re
import struct
import subprocess
import tempfile
import zlib
from pathlib import Path

# Header size read to find SYSTEM.CNF (1 MB is enough on any PS1/PS2 disc).
READ_SIZE = 1024 * 1024

# PSP metadata (UMD_DATA.BIN / PARAM.SFO) can sit further into the filesystem,
# so we scan a larger window for PSP discs.
PSP_READ_SIZE = 16 * 1024 * 1024

# Matches serials like SLUS_012.34 or SCUS-94163.
SERIAL_PATTERN = re.compile(r"([A-Z]{4})[_\-](\d{3})[._](\d{2})", re.ASCII)

# Matches the BOOT line of SYSTEM.CNF (PS1: BOOT, PS2: BOOT2).
BOOT_PATTERN = re.compile(
    rb"BOOT2?\s*=\s*cdrom\d?[:\\/]+\\?([A-Z]{4}[_\-]\d{3}[._]\d{2})",
    re.IGNORECASE,
)

# Generic serial pattern in raw bytes (fallback when BOOT is absent).
SERIAL_BYTES_PATTERN = re.compile(rb"([A-Z]{4}[_\-]\d{3}[._]\d{2})")

# UMD_DATA.BIN content starts with the serial followed by a pipe:
# "ULUS-10080|DG|G|01.00"
PSP_UMD_PATTERN = re.compile(rb"([A-Z]{4})-(\d{5})\|", re.ASCII)

# PARAM.SFO DISC_ID field (9 chars, no dash): "ULUS10080".
# Surrounded by null padding or following the DISC_ID key.
PSP_DISCID_PATTERN = re.compile(rb"DISC_ID[\x00 ]{0,32}([A-Z]{4})(\d{5})", re.ASCII)


def normalize_serial(raw: str) -> str | None:
    """Convert 'SLUS_012.34' or 'SLUS-01234' to 'SLUS-01234'."""
    m = SERIAL_PATTERN.search(raw)
    if not m:
        return None
    prefix, mid, end = m.group(1), m.group(2), m.group(3)
    return f"{prefix}-{mid}{end}"


def _read_file_head(path: Path, size: int = READ_SIZE) -> bytes | None:
    """Read the first *size* bytes of *path*, or None on an I/O error."""
    try:
        with open(path, "rb") as f:
            return f.read(size)
    except OSError:
        return None


def _scan_serial(data: bytes) -> str | None:
    """Search for a serial in raw bytes: BOOT line first, then fallback."""
    m = BOOT_PATTERN.search(data)
    if m:
        serial = normalize_serial(m.group(1).decode("ascii", errors="ignore"))
        if serial:
            return serial

    m = SERIAL_BYTES_PATTERN.search(data)
    if m:
        return normalize_serial(m.group(1).decode("ascii", errors="ignore"))

    return None


def _search_psp_serial(data: bytes | None) -> str | None:
    """Search a byte blob for a PSP serial. Returns 'XXXX-00000' or None."""
    if not data:
        return None
    m = PSP_UMD_PATTERN.search(data)
    if m:
        return f"{m.group(1).decode('ascii')}-{m.group(2).decode('ascii')}"
    m = PSP_DISCID_PATTERN.search(data)
    if m:
        return f"{m.group(1).decode('ascii')}-{m.group(2).decode('ascii')}"
    return None


def extract_serial_from_bin(bin_path: Path | str) -> str | None:
    """Extract the serial from a raw BIN/IMG by scanning the SYSTEM.CNF content."""
    bin_path = Path(bin_path)
    if not bin_path.is_file():
        return None
    data = _read_file_head(bin_path)
    return _scan_serial(data) if data else None


def extract_serial_from_cue(cue_path: Path | str) -> str | None:
    """Extract the serial by locating the BIN data track via a .cue file."""
    cue_path = Path(cue_path)
    if not cue_path.is_file():
        return None

    cue_dir = cue_path.parent
    try:
        content = cue_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    # The FILE lines of a .cue look like: FILE "file.bin" BINARY
    m = re.search(r'FILE\s+"([^"]+)"', content)
    if not m:
        return None

    bin_name = m.group(1)
    bin_path = cue_dir / bin_name
    if not bin_path.is_file():
        # Fallback: case-insensitive match
        for f in cue_dir.iterdir():
            if f.name.lower() == bin_name.lower():
                bin_path = f
                break
        else:
            return None

    return extract_serial_from_bin(bin_path)


def extract_serial_from_chd(chd_path: Path | str) -> str | None:
    """Extract the serial from a CHD by temporarily extracting it with chdman."""
    chd_path = Path(chd_path)
    if not chd_path.is_file():
        return None

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_cue = Path(tmpdir) / "temp.cue"
        tmp_bin = Path(tmpdir) / "temp.bin"

        result = subprocess.run(
            ["chdman", "extractcd", "-i", str(chd_path), "-o", str(tmp_cue), "-ob", str(tmp_bin)],
            capture_output=True,
        )

        if result.returncode != 0:
            return None

        return extract_serial_from_bin(tmp_bin)


def extract_serial_from_iso(iso_path: Path | str) -> str | None:
    """Extract the serial from an ISO9660 (PS1 or PS2) by scanning SYSTEM.CNF."""
    iso_path = Path(iso_path)
    if not iso_path.is_file():
        return None
    data = _read_file_head(iso_path)
    return _scan_serial(data) if data else None


def _read_cso_blocks(cso_path: Path | str, num_bytes: int) -> bytes | None:
    """Read and decompress the first *num_bytes* bytes of a CSO file.

    CSO format:
      Header (24 bytes): magic "CISO", header_size, total_bytes, block_size, ver, align
      Index: (num_blocks+1) entries of 4 bytes (uint32)
        bit 31 = uncompressed block, bits 0-30 = offset >> alignment
      Blocks: zlib-compressed or raw data
    """
    with open(cso_path, "rb") as f:
        header = f.read(24)
        if len(header) < 24 or header[:4] != b"CISO":
            return None

        _hdr_size, total_bytes = struct.unpack_from("<IQ", header, 4)
        block_size, _ver, align = struct.unpack_from("<IBB", header, 16)

        if block_size == 0:
            return None

        total_blocks = (total_bytes + block_size - 1) // block_size
        blocks_needed = min((num_bytes + block_size - 1) // block_size, total_blocks)

        # +1 entry to know the end offset of the last block.
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


def extract_serial_from_cso(cso_path: Path | str) -> str | None:
    """Extract the serial from a CSO by decompressing just enough data (~1 MB)."""
    cso_path = Path(cso_path)
    if not cso_path.is_file():
        return None

    try:
        data = _read_cso_blocks(cso_path, READ_SIZE)
    except (OSError, struct.error):
        return None

    return _scan_serial(data) if data else None


def extract_serial_from_psp_iso(iso_path: Path | str) -> str | None:
    """Extract the PSP serial from an ISO by scanning for UMD_DATA.BIN or PARAM.SFO.

    PSP ISOs place metadata near the start of the filesystem; reading up to
    16 MB covers virtually all commercial discs.
    """
    iso_path = Path(iso_path)
    if not iso_path.is_file():
        return None
    data = _read_file_head(iso_path, PSP_READ_SIZE)
    return _search_psp_serial(data)


def extract_serial_from_psp_cso(cso_path: Path | str) -> str | None:
    """Extract the PSP serial from a CSO by decompressing the first blocks (~16 MB)."""
    cso_path = Path(cso_path)
    if not cso_path.is_file():
        return None

    try:
        data = _read_cso_blocks(cso_path, PSP_READ_SIZE)
    except (OSError, struct.error):
        return None

    return _search_psp_serial(data)
