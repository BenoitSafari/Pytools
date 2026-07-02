"""Rename disc image files to standardized naming pattern.

Format: Title-(Region)(Languages)(Serial).ext
Multi-disc: Title_discN-(Region)(Languages)(Serial).ext
"""

import re
from pathlib import Path

from psx_archiver.db import load_database
from psx_archiver.logger import log
from psx_archiver.serial import (
    extract_serial_from_chd,
    extract_serial_from_cso,
    extract_serial_from_iso,
    extract_serial_from_psp_cso,
    extract_serial_from_psp_iso,
)
from psx_archiver.titles import clean_title

# Serial prefix -> region fallback
REGION_MAP = {
    "SCES": "PAL",
    "SLES": "PAL",
    "SCED": "PAL",
    "SLED": "PAL",
    "SLUS": "NTSC-U",
    "SCUS": "NTSC-U",
    "SLPS": "NTSC-J",
    "SCPS": "NTSC-J",
    "SLPM": "NTSC-J",
    # PSP prefixes
    "ULUS": "NTSC-U",
    "UCUS": "NTSC-U",
    "ULES": "PAL",
    "UCES": "PAL",
    "ULJM": "NTSC-J",
    "ULJS": "NTSC-J",
    "UCJS": "NTSC-J",
    "UCJM": "NTSC-J",
    "NPUG": "NTSC-U",
    "NPUH": "NTSC-U",
    "NPUZ": "NTSC-U",
    "NPUF": "NTSC-U",
    "NPEG": "PAL",
    "NPEH": "PAL",
    "NPEZ": "PAL",
    "NPEX": "PAL",
    "NPJG": "NTSC-J",
    "NPJH": "NTSC-J",
    "NPJJ": "NTSC-J",
}


def _get_disc_number(name):
    m = re.search(r" CD(\d+)$", name)
    return int(m.group(1)) if m else None


# Language tokens commonly seen in redump/nointro filenames
_LANG_TOKENS = {
    "En",
    "Fr",
    "De",
    "Es",
    "It",
    "Nl",
    "Pt",
    "Sv",
    "No",
    "Nw",
    "Da",
    "Fi",
    "Ja",
    "Ko",
    "Zh",
    "Ch",
    "Ru",
    "Pl",
    "Du",
    "Cs",
}


def _extract_languages_from_filename(stem):
    """Return 'En,Fr,De' from a stem like 'Foo (USA) (En,Fr,De)'. None if absent."""
    for group in re.findall(r"\(([^)]+)\)", stem):
        tokens = [t.strip() for t in group.split(",")]
        if tokens and all(t in _LANG_TOKENS for t in tokens):
            return ",".join(tokens)
    return None


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
        # Fall back to languages parsed from the original filename when the DB
        # entry has none (common for PSP rows).
        if not languages:
            languages = _extract_languages_from_filename(lookup)
    else:
        # Fallback: use filename as title
        title_part = re.sub(r"\s*\([^)]*\)", "", lookup).strip()
        title = title_part.replace(" ", "_")
        if serial:
            region = REGION_MAP.get(serial[:4], "PAL")
        else:
            region = "NTSC-U"
        languages = _extract_languages_from_filename(lookup)

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
        try:
            old.rename(new_path)
        except PermissionError as e:
            print(f"  LOCKED: {old.name} ({e.strerror})")
            continue
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


def rename_cso_files(cso_dir, db_path, dry_run=False, iso_dir=None, console="PS2"):
    """Rename all CSO files in cso_dir using serial extraction and DB lookup.

    If iso_dir is provided, tries to extract serial from the source ISO first
    (much faster than decompressing CSO blocks). Falls back to CSO if no
    matching ISO is found.

    `console` selects the DB slice and extraction strategy: "PS2" or "PSP".

    Returns (renamed_count, total_count).
    """
    db = load_database(db_path, console=console)

    if console == "PSP":
        iso_extractor = extract_serial_from_psp_iso
        cso_extractor = extract_serial_from_psp_cso
    else:
        iso_extractor = extract_serial_from_iso
        cso_extractor = extract_serial_from_cso

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
                serial = iso_extractor(iso_path)
                if serial:
                    return serial
            return cso_extractor(cso_path)

        return _rename_files(cso_dir, "*.cso", db, extract_serial_prefer_iso, dry_run)

    return _rename_files(cso_dir, "*.cso", db, cso_extractor, dry_run)
