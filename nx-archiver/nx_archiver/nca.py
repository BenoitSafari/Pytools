"""NCA (Nintendo Content Archive) header decryption/encryption and parsing."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum
from typing import BinaryIO

# NCA header is 0xC00 bytes, encrypted with AES-128-XTS, sector size 0x200.
NCA_HEADER_SIZE = 0xC00
XTS_SECTOR_SIZE = 0x200
# We need to read at least 0x4000 bytes for a full NCA header (including FS headers)
# but the encrypted region is 0xC00.
NCA_FULL_HEADER_SIZE = 0x4000


class ContentType(IntEnum):
    PROGRAM = 0
    META = 1
    CONTROL = 2
    MANUAL = 3
    DATA = 4
    PUBLIC_DATA = 5


class DistributionType(IntEnum):
    DOWNLOAD = 0
    GAMECARD = 1


@dataclass
class NCAHeader:
    magic: bytes  # b"NCA3", b"NCA2", b"NCA0"
    distribution_type: DistributionType
    content_type: ContentType
    key_generation_old: int
    key_area_encryption_key_index: int
    content_size: int
    program_id: int
    content_index: int
    sdk_addon_version: int
    key_generation: int
    rights_id: bytes  # 16 bytes
    has_rights_id: bool


def _xts_tweak_encrypt(tweak: bytearray, aes_tweak) -> None:
    """Encrypt tweak in-place and prepare for XTS."""
    encrypted = aes_tweak.encrypt(bytes(tweak))
    tweak[:] = encrypted


def _gf128_mul2(tweak: bytearray) -> None:
    """Multiply tweak by 2 in GF(2^128) with feedback polynomial x^128 + x^7 + x^2 + x + 1."""
    carry = 0
    for i in range(16):
        new_carry = (tweak[i] >> 7) & 1
        tweak[i] = ((tweak[i] << 1) | carry) & 0xFF
        carry = new_carry
    if carry:
        tweak[0] ^= 0x87


def _aes_xts_crypt(data: bytes, key: bytes, sector_num: int, decrypt: bool) -> bytes:
    """AES-128-XTS encrypt/decrypt a single sector.

    *key* is 32 bytes: first 16 for data AES, last 16 for tweak AES.
    """
    from Crypto.Cipher import AES

    key1 = key[:16]  # data key
    key2 = key[16:]  # tweak key

    aes_data = AES.new(key1, AES.MODE_ECB)
    aes_tweak = AES.new(key2, AES.MODE_ECB)

    # Compute initial tweak for this sector (big-endian encoding)
    tweak = bytearray(sector_num.to_bytes(16, "big"))
    _xts_tweak_encrypt(tweak, aes_tweak)

    result = bytearray()
    for block_off in range(0, len(data), 16):
        block = bytearray(data[block_off : block_off + 16])
        # XOR with tweak
        for j in range(16):
            block[j] ^= tweak[j]
        # AES
        if decrypt:
            processed = aes_data.decrypt(bytes(block))
        else:
            processed = aes_data.encrypt(bytes(block))
        # XOR with tweak again
        out = bytearray(processed)
        for j in range(16):
            out[j] ^= tweak[j]
        result.extend(out)
        # Advance tweak
        _gf128_mul2(tweak)

    return bytes(result)


def decrypt_nca_header(data: bytes, header_key: bytes) -> bytes:
    """Decrypt the first 0xC00 bytes of an NCA using AES-128-XTS.

    *data* must be at least ``NCA_HEADER_SIZE`` bytes.
    *header_key* is the 32-byte key from prod.keys.

    Returns the decrypted header (0xC00 bytes).
    """
    if len(data) < NCA_HEADER_SIZE:
        raise ValueError(f"Need at least {NCA_HEADER_SIZE} bytes, got {len(data)}")
    if len(header_key) != 32:
        raise ValueError(f"header_key must be 32 bytes, got {len(header_key)}")

    result = bytearray()
    sector_count = NCA_HEADER_SIZE // XTS_SECTOR_SIZE

    for sector in range(sector_count):
        offset = sector * XTS_SECTOR_SIZE
        sector_data = data[offset : offset + XTS_SECTOR_SIZE]
        result.extend(_aes_xts_crypt(sector_data, header_key, sector, decrypt=True))

    return bytes(result)


def encrypt_nca_header(data: bytes, header_key: bytes) -> bytes:
    """Encrypt the first 0xC00 bytes of an NCA header using AES-128-XTS."""
    if len(data) < NCA_HEADER_SIZE:
        raise ValueError(f"Need at least {NCA_HEADER_SIZE} bytes, got {len(data)}")

    result = bytearray()
    sector_count = NCA_HEADER_SIZE // XTS_SECTOR_SIZE

    for sector in range(sector_count):
        offset = sector * XTS_SECTOR_SIZE
        sector_data = data[offset : offset + XTS_SECTOR_SIZE]
        result.extend(_aes_xts_crypt(sector_data, header_key, sector, decrypt=False))

    return bytes(result)


def parse_nca_header(decrypted: bytes) -> NCAHeader:
    """Parse a decrypted NCA header.

    *decrypted* should be the output of ``decrypt_nca_header()``.
    The actual header fields start at offset 0x200 (after the two RSA signatures).
    """
    # Magic at 0x200
    magic = decrypted[0x200:0x204]
    if magic not in (b"NCA3", b"NCA2", b"NCA1", b"NCA0"):
        raise ValueError(f"Bad NCA magic: {magic!r} (header may not be decrypted correctly)")

    dist_type = DistributionType(decrypted[0x204])
    content_type = ContentType(decrypted[0x205])
    key_gen_old = decrypted[0x206]
    kek_index = decrypted[0x207]
    content_size = struct.unpack_from("<Q", decrypted, 0x208)[0]
    program_id = struct.unpack_from("<Q", decrypted, 0x210)[0]
    content_index = struct.unpack_from("<I", decrypted, 0x218)[0]
    sdk_addon_version = struct.unpack_from("<I", decrypted, 0x21C)[0]
    key_generation = decrypted[0x220]
    rights_id = decrypted[0x230:0x240]
    has_rights_id = any(b != 0 for b in rights_id)

    return NCAHeader(
        magic=magic,
        distribution_type=dist_type,
        content_type=content_type,
        key_generation_old=key_gen_old,
        key_area_encryption_key_index=kek_index,
        content_size=content_size,
        program_id=program_id,
        content_index=content_index,
        sdk_addon_version=sdk_addon_version,
        key_generation=key_generation,
        rights_id=rights_id,
        has_rights_id=has_rights_id,
    )


def read_nca_info(stream: BinaryIO, offset: int, header_key: bytes) -> NCAHeader:
    """Read and decrypt an NCA header from *stream* at *offset*."""
    stream.seek(offset)
    raw = stream.read(NCA_HEADER_SIZE)
    decrypted = decrypt_nca_header(raw, header_key)
    return parse_nca_header(decrypted)
