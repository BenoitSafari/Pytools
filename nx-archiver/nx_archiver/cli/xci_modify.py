"""Add or remove NCAs from an XCI file."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Add or remove NCAs from XCI")
    parser.add_argument("input", type=Path, help="Input XCI file")
    parser.add_argument("-o", "--output", type=Path, required=True, help="Output XCI file")
    parser.add_argument("--add", nargs="+", type=Path, metavar="NCA", help="NCA files to add to secure partition")
    parser.add_argument("--remove", nargs="+", metavar="NAME", help="NCA filenames to remove from secure partition")
    parser.add_argument("--keys", type=Path, help="Path to prod.keys")
    parser.add_argument("--list", action="store_true", dest="list_contents", help="List XCI contents and exit")
    args = parser.parse_args(argv)

    if not args.input.exists():
        print(f"Error: {args.input} not found", file=sys.stderr)
        sys.exit(1)

    from nx_archiver.xci import parse_xci, build_xci
    from nx_archiver.hfs0 import FileSlice

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
            secure_files.append((
                entry.name,
                FileSlice(path=args.input, offset=entry.offset, size=entry.size),
            ))
            print(f"  Keeping: {entry.name} ({entry.size / (1024**2):.1f} MB)")

        # Add new files
        for nca_path in (args.add or []):
            if not nca_path.exists():
                print(f"Error: {nca_path} not found", file=sys.stderr)
                sys.exit(1)
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
        for part_name, target_list in [("update", update_files), ("logo", logo_files), ("normal", normal_files)]:
            part = xci.partitions.get(part_name)
            if part and part.hfs0.entries:
                for entry in part.hfs0.entries:
                    target_list.append((
                        entry.name,
                        FileSlice(path=args.input, offset=entry.offset, size=entry.size),
                    ))

        print(f"\nRebuilding XCI: {args.output}")
        print(f"  Secure partition: {len(secure_files)} files")
        with open(args.output, "wb") as out_fh:
            build_xci(secure_files, out_fh,
                      update_files=update_files,
                      normal_files=normal_files,
                      logo_files=logo_files,
                      original_header=xci.header.raw)

    print(f"XCI written: {args.output} ({args.output.stat().st_size / (1024**2):.1f} MB)")
    print("Done.")


def _print_xci_contents(xci, fh, keys_path):
    """Print detailed XCI contents."""
    from nx_archiver.xci import GAMECARD_SIZE_NAMES

    h = xci.header
    print(f"XCI Header:")
    print(f"  Card size: {GAMECARD_SIZE_NAMES.get(h.rom_size, f'0x{h.rom_size:02X}')}")
    print(f"  Valid data: {h.valid_data_end_page * 0x200 / (1024**3):.2f} GB")
    print()

    for name, part in xci.partitions.items():
        entries = part.hfs0.entries
        total = sum(e.size for e in entries)
        print(f"Partition '{name}': {len(entries)} files, {total / (1024**2):.1f} MB")
        for entry in entries:
            print(f"  {entry.name}: {entry.size / (1024**2):.1f} MB")

        # Try NCA info if keys available
        if keys_path and entries:
            try:
                from nx_archiver.keys import load_keys, get_header_key
                from nx_archiver.nca import read_nca_info
                keys = load_keys(keys_path)
                header_key = get_header_key(keys)
                print(f"  NCA details:")
                for entry in entries:
                    try:
                        info = read_nca_info(fh, entry.offset, header_key)
                        print(f"    {entry.name}: {info.content_type.name}, "
                              f"TitleID={info.program_id:016X}")
                    except Exception:
                        pass
            except Exception:
                pass
        print()


if __name__ == "__main__":
    main()
