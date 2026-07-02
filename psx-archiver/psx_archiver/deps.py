"""Check for the required external tools."""

from __future__ import annotations

import shutil

# Installation hints per tool, covering Linux (apt/pacman), macOS (brew),
# Windows (winget/scoop/choco) and pip where relevant.
INSTALL_HINTS = {
    "7z": (
        "apt install p7zip-full · pacman -S p7zip · brew install p7zip · winget install 7zip.7zip"
    ),
    "chdman": (
        "apt install mame-tools · pacman -S mame-tools · brew install rmame · "
        "Windows: download MAME (https://github.com/mamedev/mame/releases)"
    ),
    "maxcso": "pacman -S maxcso · brew install maxcso · pip install maxcso · scoop install maxcso",
    "ciso": "pip install ciso",
}


def check_dependencies(platform: str | None) -> list[str]:
    """Check the external tools required for the given platform.

    If *platform* is None, only the common dependencies (7z) are checked.
    Returns the list of error messages for missing tools (empty if all are present).
    """
    missing: list[str] = []

    if not shutil.which("7z"):
        missing.append(f"7z - install: {INSTALL_HINTS['7z']}")

    if platform == "ps1":
        if not shutil.which("chdman"):
            missing.append(f"chdman - install: {INSTALL_HINTS['chdman']}")
    elif platform in ("ps2", "psp"):
        if not shutil.which("maxcso") and not shutil.which("ciso"):
            missing.append(
                f"maxcso or ciso - install: {INSTALL_HINTS['maxcso']} / {INSTALL_HINTS['ciso']}"
            )

    return missing
