"""Extract NCAs from an XCI file, optionally rebuilding as NSP."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Extract NCAs from XCI file")
    parser.add_argument("input", type=Path, help="Input XCI file")
    parser.add_argument("-o", "--output", type=Path, help="Output directory (default: ./<basename>/)")
    parser.add_argument("--nsp", action="store_true", help="Rebuild extracted NCAs as NSP")
    parser.add_argument("--keys", type=Path, help="Path to prod.keys")
    parser.add_argument("--info", action="store_true", help="Show NCA info (requires keys)")
    parser.add_argument("--partition", default="secure", help="Partition to extract (default: secure)")
    args = parser.parse_args(argv)

    if not args.input.exists():
        print(f"Error: {args.input} not found", file=sys.stderr)
        sys.exit(1)

    from nx_archiver.xci import parse_xci
    from nx_archiver.pfs0 import build_pfs0

    out_dir = args.output or Path(args.input.stem)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Parsing XCI: {args.input}")
    with open(args.input, "rb") as fh:
        xci = parse_xci(fh)

        # Show partition info
        for name, part in xci.partitions.items():
            file_count = len(part.hfs0.entries)
            total_size = sum(e.size for e in part.hfs0.entries)
            print(f"  Partition '{name}': {file_count} files, {total_size / (1024**2):.1f} MB")

        # Extract target partition
        partition_name = args.partition
        if partition_name not in xci.partitions:
            available = ", ".join(xci.partitions.keys())
            print(f"Error: partition '{partition_name}' not found. Available: {available}", file=sys.stderr)
            sys.exit(1)

        partition = xci.partitions[partition_name]
        if not partition.hfs0.entries:
            print(f"Partition '{partition_name}' is empty.")
            return

        # Show NCA info if requested and keys available
        if args.info:
            keys_path = args.keys
            try:
                from nx_archiver.keys import load_keys, get_header_key
                from nx_archiver.nca import read_nca_info

                keys = load_keys(keys_path)
                header_key = get_header_key(keys)
                print(f"\nNCA details:")
                for entry in partition.hfs0.entries:
                    try:
                        info = read_nca_info(fh, entry.offset, header_key)
                        print(f"  {entry.name}: {info.content_type.name}, "
                              f"TitleID={info.program_id:016X}, "
                              f"Size={entry.size / (1024**2):.1f} MB"
                              f"{', has rights_id' if info.has_rights_id else ''}")
                    except Exception as e:
                        print(f"  {entry.name}: (could not decrypt: {e})")
            except Exception as e:
                print(f"Warning: could not load keys: {e}", file=sys.stderr)

        # Extract files
        print(f"\nExtracting {len(partition.hfs0.entries)} files to {out_dir}/")
        extracted = partition.hfs0.extract_all(fh, out_dir)
        for p in extracted:
            print(f"  {p.name} ({p.stat().st_size / (1024**2):.1f} MB)")

        # Build NSP if requested
        if args.nsp:
            nsp_path = out_dir.parent / f"{args.input.stem}.nsp"
            print(f"\nBuilding NSP: {nsp_path}")
            nsp_files = [(p.name, p) for p in extracted]
            with open(nsp_path, "wb") as nsp_fh:
                build_pfs0(nsp_files, nsp_fh)
            print(f"NSP written: {nsp_path} ({nsp_path.stat().st_size / (1024**2):.1f} MB)")

    print("Done.")


if __name__ == "__main__":
    main()
