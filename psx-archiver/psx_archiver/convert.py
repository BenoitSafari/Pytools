"""Disc image conversion: BIN/CUE -> CHD, ISO -> CSO."""

import shutil
import subprocess
from pathlib import Path

from psx_archiver.logger import log, ok, fail, skip


def convert_cd_to_chd(cue_file, output, dry_run=False):
    """Convert a CUE/CCD file to CHD using chdman."""
    output = Path(output)

    if output.is_file():
        skip(f"{output.name} (exists)")
        return True

    if dry_run:
        log(f"[DRY] Would convert: {Path(cue_file).name} -> {output.name}")
        return True

    result = subprocess.run(
        ["chdman", "createcd", "-i", str(cue_file), "-o", str(output),
         "-c", "cdzs,cdzl,cdfl"],
        capture_output=True,
    )

    if result.returncode == 0:
        ok(output.name)
        return True
    else:
        fail(output.name)
        output.unlink(missing_ok=True)
        return False


def convert_iso_to_cso(iso_file, output, dry_run=False):
    """Convert an ISO file to CSO using maxcso or ciso."""
    output = Path(output)

    if output.is_file():
        skip(f"{output.name} (exists)")
        return True

    if dry_run:
        log(f"[DRY] Would convert: {Path(iso_file).name} -> {output.name}")
        return True

    if shutil.which("maxcso"):
        result = subprocess.run(
            ["maxcso", str(iso_file), "-o", str(output)],
            capture_output=True,
        )
    else:
        result = subprocess.run(
            ["ciso", "9", str(iso_file), str(output)],
            capture_output=True,
        )

    if result.returncode == 0:
        ok(output.name)
        return True
    else:
        fail(output.name)
        output.unlink(missing_ok=True)
        return False


def _find_cue_files(directory):
    """Recursively find .cue and .ccd files in a directory."""
    directory = Path(directory)
    files = []
    for ext in ("*.cue", "*.CUE", "*.ccd", "*.CCD"):
        files.extend(directory.rglob(ext))
    return sorted(set(files))


def convert_ps1(src_dir, output_dir, dry_run=False):
    """Convert all PS1 disc images found under src_dir to CHD.

    Handles both flat layouts and per-game subdirectories.
    Returns (success, failed, total).
    """
    src_dir = Path(src_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    total = success = failed = 0

    # Collect game directories (first-level subdirs)
    gamedirs = sorted(
        d for d in src_dir.iterdir() if d.is_dir() and d.name != ".extracted"
    )

    # Also check for flat layout (cue/ccd directly in src_dir)
    flat_cues = _find_cue_files_shallow(src_dir)
    if flat_cues:
        gamedirs.append(src_dir)

    for gamedir in gamedirs:
        dirname = gamedir.name
        cue_files = _find_cue_files(gamedir)
        if not cue_files:
            continue

        if len(cue_files) == 1:
            total += 1
            if convert_cd_to_chd(cue_files[0], output_dir / f"{dirname}.chd", dry_run):
                success += 1
            else:
                failed += 1
        else:
            for disc_num, cue_file in enumerate(cue_files, 1):
                total += 1
                out_name = f"{dirname} CD{disc_num}.chd"
                if convert_cd_to_chd(cue_file, output_dir / out_name, dry_run):
                    success += 1
                else:
                    failed += 1

    return success, failed, total


def _find_cue_files_shallow(directory):
    """Find .cue/.ccd files directly in directory (not recursive)."""
    directory = Path(directory)
    files = []
    for f in directory.iterdir():
        if f.is_file() and f.suffix.lower() in (".cue", ".ccd"):
            files.append(f)
    return sorted(files)


def convert_iso_platform(label, src_dir, output_dir, dry_run=False):
    """Convert all ISO files found under src_dir to CSO.

    Returns (success, failed, total).
    """
    src_dir = Path(src_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    iso_files = sorted(src_dir.rglob("*.iso")) + sorted(src_dir.rglob("*.ISO"))
    iso_files = sorted(set(iso_files))

    if not iso_files:
        log("No ISO files found")
        return 0, 0, 0

    total = success = failed = 0
    for iso_file in iso_files:
        out_name = iso_file.stem + ".cso"
        total += 1
        if convert_iso_to_cso(iso_file, output_dir / out_name, dry_run):
            success += 1
        else:
            failed += 1

    return success, failed, total
