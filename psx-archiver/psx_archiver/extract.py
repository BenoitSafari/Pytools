"""Archive extraction via 7z."""

from __future__ import annotations

from pathlib import Path

from psx_archiver.external import run_tool
from psx_archiver.logger import dry_run, log, skip

ARCHIVE_EXTENSIONS = {
    ".7z",
    ".zip",
    ".rar",
    ".tar.gz",
    ".tgz",
    ".tar.bz2",
    ".tar.xz",
    ".gz",
}


def is_archive(path: Path) -> bool:
    """Report whether *path* has a recognized archive extension."""
    name = path.name.lower()
    return any(name.endswith(ext) for ext in ARCHIVE_EXTENSIONS)


def strip_archive_ext(name: str) -> str:
    """Strip the archive extension from the filename (e.g. "game.tar.gz" -> "game")."""
    lower = name.lower()
    for ext in sorted(ARCHIVE_EXTENSIONS, key=len, reverse=True):
        if lower.endswith(ext):
            return name[: len(name) - len(ext)]
    return name


def extract_archives(
    input_dir: Path | str, extract_dir: Path | str, dry_run_mode: bool = False
) -> tuple[int, int]:
    """Extract all archives from *input_dir* into *extract_dir*.

    Returns (number of successes, number of failures).
    """
    input_dir = Path(input_dir)
    extract_dir = Path(extract_dir)
    extract_dir.mkdir(parents=True, exist_ok=True)

    archives = sorted(f for f in input_dir.iterdir() if f.is_file() and is_archive(f))

    if not archives:
        log(f"No archives found in {input_dir}")
        return 0, 0

    success = 0
    failures = 0

    for archive in archives:
        dest = extract_dir / strip_archive_ext(archive.name)

        if dest.is_dir():
            skip(f"{archive.name} (already extracted)")
            success += 1
            continue

        if dry_run_mode:
            dry_run("extract", f"{archive.name} -> {dest}")
            success += 1
            continue

        log(f"Extracting: {archive.name}")
        dest.mkdir(parents=True, exist_ok=True)

        if run_tool(["7z", "x", f"-o{dest}", "-y", str(archive)], archive.name, cleanup=dest):
            success += 1
        else:
            failures += 1

    log(f"Extracted {success} archives")
    return success, failures
