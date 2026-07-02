"""Disc image conversion: BIN/CUE -> CHD, ISO -> CSO."""

from __future__ import annotations

import shutil
from pathlib import Path

from psx_archiver.external import run_tool
from psx_archiver.logger import dry_run, log, skip


def convert_cd_to_chd(cue_file: Path | str, output: Path | str, dry_run_mode: bool = False) -> bool:
    """Convert a CUE/CCD file to CHD using chdman."""
    output = Path(output)

    if output.is_file():
        skip(f"{output.name} (exists)")
        return True

    if dry_run_mode:
        dry_run("convert", f"{Path(cue_file).name} -> {output.name}")
        return True

    cmd = [
        "chdman",
        "createcd",
        "-i",
        str(cue_file),
        "-o",
        str(output),
        "-c",
        "cdzs,cdzl,cdfl",
    ]
    return run_tool(cmd, output.name, cleanup=output)


def convert_iso_to_cso(
    iso_file: Path | str, output: Path | str, dry_run_mode: bool = False
) -> bool:
    """Convert an ISO file to CSO using maxcso (or ciso as a fallback)."""
    output = Path(output)

    if output.is_file():
        skip(f"{output.name} (exists)")
        return True

    if dry_run_mode:
        dry_run("convert", f"{Path(iso_file).name} -> {output.name}")
        return True

    if shutil.which("maxcso"):
        cmd = ["maxcso", str(iso_file), "-o", str(output)]
    else:
        cmd = ["ciso", "9", str(iso_file), str(output)]
    return run_tool(cmd, output.name, cleanup=output)


def _find_cue_files(directory: Path | str) -> list[Path]:
    """Recursively search for .cue and .ccd files in a directory."""
    directory = Path(directory)
    files: list[Path] = []
    for ext in ("*.cue", "*.CUE", "*.ccd", "*.CCD"):
        files.extend(directory.rglob(ext))
    return sorted(set(files))


def _find_cue_files_shallow(directory: Path | str) -> list[Path]:
    """Search for .cue/.ccd files directly in the directory (non-recursive)."""
    directory = Path(directory)
    files = [f for f in directory.iterdir() if f.is_file() and f.suffix.lower() in (".cue", ".ccd")]
    return sorted(files)


def convert_ps1(
    src_dir: Path | str, output_dir: Path | str, dry_run_mode: bool = False
) -> tuple[int, int, int]:
    """Convert all PS1 images found under *src_dir* to CHD.

    Handles both flat trees and per-game subdirectories.
    Returns (successes, failures, total).
    """
    src_dir = Path(src_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    total = success = failed = 0

    # Game directories (top-level subdirectories)
    gamedirs = sorted(d for d in src_dir.iterdir() if d.is_dir() and d.name != ".extracted")

    # Support for flat trees (cue/ccd directly in src_dir)
    if _find_cue_files_shallow(src_dir):
        gamedirs.append(src_dir)

    for gamedir in gamedirs:
        dirname = gamedir.name
        cue_files = _find_cue_files(gamedir)
        if not cue_files:
            continue

        if len(cue_files) == 1:
            total += 1
            if convert_cd_to_chd(cue_files[0], output_dir / f"{dirname}.chd", dry_run_mode):
                success += 1
            else:
                failed += 1
        else:
            for disc_num, cue_file in enumerate(cue_files, 1):
                total += 1
                out_name = f"{dirname} CD{disc_num}.chd"
                if convert_cd_to_chd(cue_file, output_dir / out_name, dry_run_mode):
                    success += 1
                else:
                    failed += 1

    return success, failed, total


def convert_iso_platform(
    label: str, src_dir: Path | str, output_dir: Path | str, dry_run_mode: bool = False
) -> tuple[int, int, int]:
    """Convert all ISO files found under *src_dir* to CSO.

    Returns (successes, failures, total).
    """
    src_dir = Path(src_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    iso_files = sorted(set(src_dir.rglob("*.iso")) | set(src_dir.rglob("*.ISO")))

    if not iso_files:
        log("No ISO files found")
        return 0, 0, 0

    total = success = failed = 0
    for iso_file in iso_files:
        out_name = iso_file.stem + ".cso"
        total += 1
        if convert_iso_to_cso(iso_file, output_dir / out_name, dry_run_mode):
            success += 1
        else:
            failed += 1

    return success, failed, total
