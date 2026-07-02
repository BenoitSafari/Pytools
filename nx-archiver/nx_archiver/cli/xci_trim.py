"""Trim an XCI: drop the gamecard padding past the valid-data end.

A "full" (untrimmed) XCI is the raw dump of the physical gamecard, padded
with 0xFF up to the cartridge size (e.g. 8/16/32 GB). The actual data ends
at ``valid_data_end_page`` (recorded in the card header); everything after
it is dead padding. Trimming copies only ``[0, valid_data_end)`` and is
lossless — the result is a smaller, still-valid XCI.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from nx_archiver.cli._common import copy_file_chunked, validate_input_file

CHUNK = 8 << 20  # 8 MiB copy buffer


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Trim 0xFF gamecard padding from an XCI file")
    parser.add_argument("input", type=Path, help="Input XCI file")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output XCI path (default: <input>.trimmed.xci)",
    )
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="Replace the input file with the trimmed result (atomic rename)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be trimmed without writing anything",
    )
    args = parser.parse_args(argv)

    validate_input_file(args.input)
    if args.output and args.in_place:
        print("Error: use either --output or --in-place, not both", file=sys.stderr)
        sys.exit(1)

    from nx_archiver.xci import PAGE_SIZE, parse_xci

    # Read the card header to find where the valid data ends.
    with open(args.input, "rb") as fh:
        xci = parse_xci(fh)
    valid_end = (xci.header.valid_data_end_page + 1) * PAGE_SIZE
    file_size = args.input.stat().st_size

    print(f"Input         : {args.input.name} ({file_size:,} B / {file_size / 1024**3:.3f} GB)")
    print(f"Valid data end: {valid_end:,} B / {valid_end / 1024**3:.3f} GB")

    if valid_end >= file_size:
        print("Nothing to trim — file already ends at the valid-data boundary.")
        return
    padding = file_size - valid_end
    print(f"Padding to cut: {padding:,} B / {padding / 1024**3:.3f} GB")

    if args.dry_run:
        print("[dry-run] No file written.")
        return

    # Decide the destination. For --in-place we write a temp sibling first,
    # then atomically rename over the original so a crash never truncates it.
    if args.in_place:
        out_path = args.input.with_name(args.input.name + ".trimming.tmp")
    else:
        out_path = args.output or args.input.with_suffix(".trimmed.xci")
        out_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Writing       : {out_path}")
    with open(args.input, "rb") as fin, open(out_path, "wb") as fout:
        written = copy_file_chunked(fin, fout, valid_end, chunk=CHUNK)

    if written != valid_end:
        print(f"Error: short write ({written:,} of {valid_end:,} B)", file=sys.stderr)
        out_path.unlink(missing_ok=True)
        sys.exit(1)

    # Re-parse the trimmed file to confirm it is still a structurally valid XCI.
    with open(out_path, "rb") as fh:
        trimmed = parse_xci(fh)
    parts = {n: len(p.hfs0.entries) for n, p in trimmed.partitions.items()}

    if args.in_place:
        os.replace(out_path, args.input)
        final = args.input
    else:
        final = out_path

    print(f"Verified      : trimmed XCI parses OK, partitions={parts}")
    print(f"Done          : {final} ({written:,} B / {written / 1024**3:.3f} GB)")


if __name__ == "__main__":
    main()
