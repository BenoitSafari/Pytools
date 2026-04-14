"""Dependency checking for external tools."""

import shutil

INSTALL_HINTS = {
    "7z": "p7zip-full (apt) / p7zip (pacman) / p7zip (brew)",
    "chdman": "mame-tools (apt/pacman) / mame (brew)",
    "maxcso": "maxcso (pacman/pip) / maxcso (brew)",
    "ciso": "ciso (pip)",
}


def check_dependencies(platform):
    """Check required external tools for the given platform.

    If platform is None, only checks common dependencies (7z).
    Returns list of error messages for missing deps, empty if all OK.
    """
    missing = []

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
