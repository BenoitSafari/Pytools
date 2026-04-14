"""Rename disc image files to standardized naming pattern.

Format: Title-(Region)(Languages)(Serial).ext
Multi-disc: Title_discN-(Region)(Languages)(Serial).ext
"""

import re
from pathlib import Path

from psx_archiver.db import load_database, lookup_serial
from psx_archiver.logger import log
from psx_archiver.serial import (
    extract_serial_from_chd, extract_serial_from_cso, extract_serial_from_iso,
)
from psx_archiver.titles import clean_title

# Serial prefix -> region fallback
REGION_MAP = {
    "SCES": "PAL", "SLES": "PAL", "SCED": "PAL", "SLED": "PAL",
    "SLUS": "NTSC-U", "SCUS": "NTSC-U",
    "SLPS": "NTSC-J", "SCPS": "NTSC-J", "SLPM": "NTSC-J",
}

def _get_disc_number(name):
    m = re.search(r" CD(\d+)$", name)
    return int(m.group(1)) if m else None


def _build_new_name(file_path, db, extract_serial_fn):
    """Build the new standardized name for a disc image file.

    Extracts the serial from the file content, then looks up
    title/region/languages from the database.
    """
    file_path = Path(file_path)
    ext = file_path.suffix
    base = file_path.stem
    disc = _get_disc_number(base)
    lookup = re.sub(r" CD\d+$", "", base)

    # Extract serial from file content
    serial = extract_serial_fn(file_path)

    if serial and serial in db:
        entry = db[serial]
        title = clean_title(entry["title"])
        region = entry["region"]
        languages = entry.get("languages", "").strip().strip('"') or None
    else:
        # Fallback: use filename as title
        title_part = re.sub(r"\s*\([^)]*\)", "", lookup).strip()
        title = title_part.replace(" ", "_")
        if serial:
            region = REGION_MAP.get(serial[:4], "PAL")
        else:
            region = "NTSC-U"
        languages = None

    # Build filename
    name = title
    if disc:
        name = f"{title}_disc{disc}"

    suffix = f"-({region})"
    if languages:
        suffix += f"({languages})"
    if serial:
        suffix += f"({serial})"

    return f"{name}{suffix}{ext}"


def _rename_files(directory, glob_pattern, db, extract_serial_fn, dry_run=False):
    """Generic rename logic for disc image files.

    Returns (renamed_count, total_count).
    """
    directory = Path(directory)
    files = sorted(directory.glob(glob_pattern))
    if not files:
        log(f"No {glob_pattern} files found.")
        return 0, 0

    renames = []
    for f in files:
        new_name = _build_new_name(f, db, extract_serial_fn)
        if f.name != new_name:
            renames.append((f, new_name))

    # Check for conflicts
    seen = {}
    for old, new in renames:
        seen.setdefault(new, []).append(old.name)
    conflicts = {k: v for k, v in seen.items() if len(v) > 1}

    if conflicts:
        log(f"WARNING: {len(conflicts)} naming conflicts:")
        for new, olds in sorted(conflicts.items()):
            print(f"  {new} <- {olds}")
        print()

    if dry_run:
        print(f"=== DRY RUN: {len(renames)} renames ===\n")
        for old, new in renames:
            print(f"  {old.name}")
            print(f"  -> {new}\n")
        return 0, len(renames)

    print(f"=== Renaming {len(renames)} files ===")
    success = 0
    for old, new_name in renames:
        new_path = old.parent / new_name
        if new_path.exists() and old != new_path:
            print(f"  SKIP (exists): {old.name} -> {new_name}")
            continue
        old.rename(new_path)
        print(f"  {old.name} -> {new_name}")
        success += 1

    print(f"\nDone! {success} files renamed.")
    return success, len(renames)


def rename_chd_files(chd_dir, db_path, dry_run=False):
    """Rename all CHD files in chd_dir using serial extraction and DB lookup.

    Returns (renamed_count, total_count).
    """
    db = load_database(db_path, console="PS1")
    return _rename_files(chd_dir, "*.chd", db, extract_serial_from_chd, dry_run)


def rename_cso_files(cso_dir, db_path, dry_run=False, iso_dir=None):
    """Rename all CSO files in cso_dir using serial extraction and DB lookup.

    If iso_dir is provided, tries to extract serial from the source ISO first
    (much faster than decompressing CSO blocks). Falls back to CSO if no
    matching ISO is found.

    Returns (renamed_count, total_count).
    """
    db = load_database(db_path, console="PS2")

    if iso_dir:
        iso_dir = Path(iso_dir)
        # Build a map of stem -> ISO path for fast lookup
        iso_map = {}
        for iso in iso_dir.rglob("*.iso"):
            iso_map[iso.stem] = iso
        for iso in iso_dir.rglob("*.ISO"):
            iso_map[iso.stem] = iso

        def extract_serial_prefer_iso(cso_path):
            cso_path = Path(cso_path)
            iso_path = iso_map.get(cso_path.stem)
            if iso_path and iso_path.is_file():
                serial = extract_serial_from_iso(iso_path)
                if serial:
                    return serial
            return extract_serial_from_cso(cso_path)

        return _rename_files(cso_dir, "*.cso", db, extract_serial_prefer_iso, dry_run)

    return _rename_files(cso_dir, "*.cso", db, extract_serial_from_cso, dry_run)
