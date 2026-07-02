"""Add or remove NCAs from an XCI file."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from nx_archiver.cli._common import format_size, validate_input_file


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Add or remove NCAs from XCI")
    parser.add_argument("input", type=Path, help="Input XCI file")
    parser.add_argument("-o", "--output", type=Path, required=True, help="Output XCI file")
    parser.add_argument(
        "--add", nargs="+", type=Path, metavar="NCA", help="NCA files to add to secure partition"
    )
    parser.add_argument(
        "--remove", nargs="+", metavar="NAME", help="NCA filenames to remove from secure partition"
    )
    parser.add_argument("--keys", type=Path, help="Path to prod.keys")
    parser.add_argument(
        "--list", action="store_true", dest="list_contents", help="List XCI contents and exit"
    )
    args = parser.parse_args(argv)

    validate_input_file(args.input)

    from nx_archiver.hfs0 import FileSlice
    from nx_archiver.xci import build_xci, parse_xci

    with open(args.input, "rb") as fh:
        xci = parse_xci(fh)

        # List mode
        if args.list_contents:
            _print_xci_contents(xci, fh, args.keys)
            return

        if not args.add and not args.remove:
            print("Error: specify --add and/or --remove (or --list to inspect)", file=sys.stderr)
            sys.exit(1)

        secure = xci.partitions.get("secure")
        if secure is None:
            print("Error: XCI has no secure partition", file=sys.stderr)
            sys.exit(1)

        existing_names = {e.name for e in secure.hfs0.entries}
        remove_set = set(args.remove or [])

        # Validate removals
        for name in remove_set:
            if name not in existing_names:
                print(f"Warning: '{name}' not found in secure partition, skipping", file=sys.stderr)

        # Use FileSlice for existing NCAs (zero-copy, no temp files needed)
        secure_files: list[tuple[str, Path | FileSlice]] = []

        for entry in secure.hfs0.entries:
            if entry.name in remove_set:
                print(f"  Removing: {entry.name}")
                continue
            # Reference data directly in the source XCI
            secure_files.append(
                (
                    entry.name,
                    FileSlice(path=args.input, offset=entry.offset, size=entry.size),
                )
            )
            print(f"  Keeping: {entry.name} ({format_size(entry.size)})")

        # Add new files
        for nca_path in args.add or []:
            validate_input_file(nca_path, "NCA")
            name = nca_path.name
            if name in {n for n, _ in secure_files}:
                print(f"  Replacing: {name}")
                secure_files = [(n, p) for n, p in secure_files if n != name]
            else:
                print(f"  Adding: {name}")
            secure_files.append((name, nca_path))

        # Preserve update/logo/normal partitions via FileSlice too
        update_files: list[tuple[str, Path | FileSlice]] = []
        logo_files: list[tuple[str, Path | FileSlice]] = []
        normal_files: list[tuple[str, Path | FileSlice]] = []
        for part_name, target_list in [
            ("update", update_files),
            ("logo", logo_files),
            ("normal", normal_files),
        ]:
            part = xci.partitions.get(part_name)
            if part and part.hfs0.entries:
                for entry in part.hfs0.entries:
                    target_list.append(
                        (
                            entry.name,
                            FileSlice(path=args.input, offset=entry.offset, size=entry.size),
                        )
                    )

        print(f"\nRebuilding XCI: {args.output}")
        print(f"  Secure partition: {len(secure_files)} files")
        with open(args.output, "wb") as out_fh:
            build_xci(
                secure_files,
                out_fh,
                update_files=update_files,
                normal_files=normal_files,
                logo_files=logo_files,
                original_header=xci.header.raw,
            )

    print(f"XCI written: {args.output} ({format_size(args.output.stat().st_size)})")
    print("Done.")


def _print_xci_contents(xci, fh, keys_path):
    """Print detailed XCI contents."""
    from nx_archiver.xci import GAMECARD_SIZE_NAMES

    h = xci.header
    print("XCI Header:")
    print(f"  Card size: {GAMECARD_SIZE_NAMES.get(h.rom_size, f'0x{h.rom_size:02X}')}")
    print(f"  Valid data: {format_size(h.valid_data_end_page * 0x200)}")
    print()

    for name, part in xci.partitions.items():
        entries = part.hfs0.entries
        total = sum(e.size for e in entries)
        print(f"Partition '{name}': {len(entries)} files, {format_size(total)}")
        for entry in entries:
            print(f"  {entry.name}: {format_size(entry.size)}")

        # Try NCA info if keys available
        if keys_path and entries:
            try:
                from nx_archiver.keys import get_header_key, load_keys
                from nx_archiver.nca import read_nca_info

                keys = load_keys(keys_path)
                header_key = get_header_key(keys)
                print("  NCA details:")
                for entry in entries:
                    try:
                        info = read_nca_info(fh, entry.offset, header_key)
                        print(
                            f"    {entry.name}: {info.content_type.name}, "
                            f"TitleID={info.program_id:016X}"
                        )
                    except Exception:
                        pass
            except Exception:
                pass
        print()


if __name__ == "__main__":
    main()
