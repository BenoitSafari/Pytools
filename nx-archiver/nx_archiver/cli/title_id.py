"""Decoding of Nintendo Switch Title IDs (base / update / DLC).

Convention (Title ID = 16 hexadecimal digits = 64 bits):

- base game : last 3 hex = ``000``  (e.g. ``0100633007D48000``)
- update    : last 3 hex = ``800``  (e.g. ``0100633007D48800``)
- DLC       : last 3 hex = ``001``, ``002`` …  (e.g. ``0100B3F000BE3001``)

All variants share the first 12 hex: this is the game's "family".

These definitions are factored out here because several CLI entry points
need them (``make-xci``, ``xci-update``).
"""

from __future__ import annotations

import re

# TitleID in brackets within a filename: "Game [0100633007D48000] .nsp".
TITLE_ID_RE = re.compile(r"\[([0-9A-Fa-f]{16})\]")

# Ticket name: "<titleid><rightsid>.tik" → the first 16 hex = TitleID.
TIK_NAME_RE = re.compile(r"^([0-9a-fA-F]{16})[0-9a-fA-F]*\.tik$")

# Version in brackets: "[v65536]".
VERSION_RE = re.compile(r"\[v([^\]]+)\]")


def classify(title_id: str) -> str:
    """Return 'base', 'update' or 'dlc' for a 16-hex TitleID."""
    last3 = title_id[-3:].upper()
    if last3 == "000":
        return "base"
    if last3 == "800":
        return "update"
    return "dlc"


def base_id(title_id: str) -> str:
    """Return the group key (first 12 hex) shared by base, update and DLC."""
    return title_id[:12].upper()
