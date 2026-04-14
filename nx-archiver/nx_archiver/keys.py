"""Nintendo Switch key management - loads prod.keys and title.keys."""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_KEYS_DIR = Path.home() / ".switch"


def load_keys(path: Path | str | None = None) -> dict[str, bytes]:
    """Load key file (prod.keys or title.keys format).

    Format: ``key_name = hex_value`` per line. Blank lines and lines
    starting with ``#`` or ``;`` are ignored.
    """
    if path is None:
        env = os.environ.get("NX_KEYS_DIR")
        path = Path(env) if env else DEFAULT_KEYS_DIR / "prod.keys"
    path = Path(path)

    keys: dict[str, bytes] = {}
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith(("#", ";")):
                continue
            if "=" not in line:
                continue
            name, _, value = line.partition("=")
            keys[name.strip()] = bytes.fromhex(value.strip())
    return keys


def load_title_keys(path: Path | str | None = None) -> dict[str, bytes]:
    """Load title.keys (rights_id = titlekey)."""
    if path is None:
        env = os.environ.get("NX_KEYS_DIR")
        path = Path(env) if env else DEFAULT_KEYS_DIR / "title.keys"
    return load_keys(path)


def get_header_key(keys: dict[str, bytes]) -> bytes:
    """Return the 32-byte header_key used for NCA header AES-XTS."""
    hk = keys.get("header_key")
    if hk is None or len(hk) != 32:
        raise KeyError("header_key not found or invalid length in prod.keys")
    return hk


def get_key_area_key(keys: dict[str, bytes], key_type: str, revision: int) -> bytes:
    """Return a 16-byte key_area_key for the given type and revision.

    *key_type* is one of ``application``, ``ocean``, ``system``.
    """
    name = f"key_area_key_{key_type}_{revision:02x}"
    kak = keys.get(name)
    if kak is None or len(kak) != 16:
        raise KeyError(f"{name} not found or invalid in prod.keys")
    return kak
