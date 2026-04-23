"""CLI entry point and pipeline orchestration."""

import argparse
import shutil
import sys
from pathlib import Path

from psx_archiver.convert import convert_ps1, convert_iso_platform
from psx_archiver.deps import check_dependencies
from psx_archiver.extract import extract_archives
from psx_archiver.logger import log
from psx_archiver.rename import rename_chd_files, rename_cso_files


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="psx-archiver",
        description="Extract, convert and rename PlayStation disc images",
    )
    parser.add_argument(
        "--platform", required=True, choices=["ps1", "ps2", "psp"],
        help="Target platform",
    )
    parser.add_argument(
        "--delete-source", action="store_true",
        help="Delete source archives after successful conversion",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be done without doing it",
    )
    parser.add_argument(
        "--skip-extract", action="store_true",
        help="Skip extraction (input already contains raw images)",
    )
    parser.add_argument(
        "--skip-convert", action="store_true",
        help="Skip conversion (only rename existing files)",
    )
    parser.add_argument(
        "--skip-rename", action="store_true",
        help="Skip renaming step",
    )
    parser.add_argument("input_dir", help="Directory containing source archives")
    parser.add_argument("output_dir", help="Directory for converted output")

    return parser.parse_args(argv)


def _get_db_path():
    """Get path to the database CSV, relative to this package."""
    return Path(__file__).resolve().parent.parent / "db" / "psxdatacenter.csv"


def _get_src_dir(input_dir, extract_dir, skip_extract):
    """Determine source directory for conversion."""
    if skip_extract:
        return input_dir
    if extract_dir.is_dir() and any(extract_dir.iterdir()):
        return extract_dir
    return input_dir


def _delete_source_archives(input_dir, dry_run):
    """Delete source archives from input directory."""
    from psx_archiver.extract import ARCHIVE_EXTENSIONS, _is_archive
    from psx_archiver.logger import ok

    log("=== Deleting source archives ===")
    for f in sorted(input_dir.iterdir()):
        if f.is_file() and _is_archive(f):
            if dry_run:
                log(f"[DRY] Would delete: {f.name}")
            else:
                f.unlink()
                ok(f"Deleted: {f.name}")


def main(argv=None):
    args = parse_args(argv)

    input_dir = Path(args.input_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    extract_dir = output_dir / ".extracted"

    # Check dependencies early (skip converter check if conversion is skipped)
    check_platform = args.platform if not args.skip_convert else None
    missing = check_dependencies(check_platform)
    if missing:
        print("Error: missing dependencies:", file=sys.stderr)
        for dep in missing:
            print(f"  - {dep}", file=sys.stderr)
        return 1

    format_map = {"ps1": "CHD", "ps2": "CSO", "psp": "CSO"}
    fmt = format_map[args.platform]

    log("psx-archiver - PlayStation archive pipeline")
    log(f"Platform: {args.platform.upper()} -> {fmt}")
    log(f"Input:    {input_dir}")
    log(f"Output:   {output_dir}")
    if args.delete_source:
        log("Source archives will be DELETED after conversion")
    if args.dry_run:
        log("*** DRY RUN MODE ***")
    print()

    output_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: Extract
    if not args.skip_extract:
        log("=== Step 1: Extracting archives ===")
        extract_archives(input_dir, extract_dir, args.dry_run)
    else:
        log("Skipping extraction (--skip-extract)")

    # Step 2: Convert
    src_dir = None
    if not args.skip_convert:
        src_dir = _get_src_dir(input_dir, extract_dir, args.skip_extract)

        if args.platform == "ps1":
            log("=== Step 2: Converting to CHD (PS1) ===")
            s, f, t = convert_ps1(src_dir, output_dir, args.dry_run)
            log(f"PS1 conversion: {s} OK / {f} failed / {t} total")
        else:
            label = args.platform.upper()
            log(f"=== Step 2: Converting to CSO ({label}) ===")
            s, f, t = convert_iso_platform(label, src_dir, output_dir, args.dry_run)
            log(f"{label} conversion: {s} OK / {f} failed / {t} total")
    else:
        log("Skipping conversion (--skip-convert)")

    # Step 3: Rename
    if not args.skip_rename:
        log("=== Step 3: Renaming files ===")
        db_path = _get_db_path()
        if not db_path.is_file():
            log(f"Warning: database not found at {db_path}, skipping rename")
        elif args.platform == "ps1":
            rename_chd_files(output_dir, db_path, args.dry_run)
        elif args.platform == "ps2":
            rename_cso_files(output_dir, db_path, args.dry_run, iso_dir=src_dir, console="PS2")
        elif args.platform == "psp":
            rename_cso_files(output_dir, db_path, args.dry_run, iso_dir=src_dir, console="PSP")
        else:
            log(f"Rename not yet implemented for {args.platform} (skipping)")
    else:
        log("Skipping rename (--skip-rename)")

    # Step 4: Cleanup
    if extract_dir.is_dir() and not args.dry_run:
        log("Cleaning up extracted files...")
        shutil.rmtree(extract_dir, ignore_errors=True)

    if args.delete_source:
        _delete_source_archives(input_dir, args.dry_run)

    print()
    log("All done!")
    return 0
