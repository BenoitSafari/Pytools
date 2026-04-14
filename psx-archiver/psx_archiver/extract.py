"""Archive extraction using 7z."""

import subprocess
from pathlib import Path

from psx_archiver.logger import log, ok, fail, skip

ARCHIVE_EXTENSIONS = {
    ".7z", ".zip", ".rar", ".tar.gz", ".tgz", ".tar.bz2", ".tar.xz", ".gz",
}


def _is_archive(path):
    name = path.name.lower()
    for ext in ARCHIVE_EXTENSIONS:
        if name.endswith(ext):
            return True
    return False


def _strip_archive_ext(name):
    lower = name.lower()
    for ext in sorted(ARCHIVE_EXTENSIONS, key=len, reverse=True):
        if lower.endswith(ext):
            return name[: len(name) - len(ext)]
    return name


def extract_archives(input_dir, extract_dir, dry_run=False):
    """Extract all archives from input_dir into extract_dir.

    Returns (success_count, fail_count).
    """
    input_dir = Path(input_dir)
    extract_dir = Path(extract_dir)
    extract_dir.mkdir(parents=True, exist_ok=True)

    archives = sorted(
        f for f in input_dir.iterdir() if f.is_file() and _is_archive(f)
    )

    if not archives:
        log(f"No archives found in {input_dir}")
        return 0, 0

    success = 0
    failures = 0

    for archive in archives:
        dirname = _strip_archive_ext(archive.name)
        dest = extract_dir / dirname

        if dest.is_dir():
            skip(f"{archive.name} (already extracted)")
            success += 1
            continue

        if dry_run:
            log(f"[DRY] Would extract: {archive.name} -> {dest}")
            success += 1
            continue

        log(f"Extracting: {archive.name}")
        dest.mkdir(parents=True, exist_ok=True)

        result = subprocess.run(
            ["7z", "x", f"-o{dest}", "-y", str(archive)],
            capture_output=True,
        )

        if result.returncode == 0:
            ok(archive.name)
            success += 1
        else:
            fail(archive.name)
            import shutil
            shutil.rmtree(dest, ignore_errors=True)
            failures += 1

    log(f"Extracted {success} archives")
    return success, failures
