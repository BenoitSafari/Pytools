"""Convert one or more NSP/NSZ files into a single XCI."""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from nx_archiver.cli._common import format_size, validate_input_file
from nx_archiver.cli.nsp_extract import extract_nsp


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Convert NSP/NSZ(s) to XCI")
    parser.add_argument("input", type=Path, nargs="+", help="Input NSP/NSZ file(s)")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output XCI file (default: <first_basename>.xci)",
    )
    parser.add_argument("--keys", type=Path, help="Path to prod.keys")
    args = parser.parse_args(argv)

    for nsp in args.input:
        validate_input_file(nsp)

    from nx_archiver.xci import build_xci

    out_path = args.output or args.input[0].with_suffix(".xci")

    with tempfile.TemporaryDirectory(prefix="nx-archiver-") as tmpdir:
        tmpdir_path = Path(tmpdir)
        all_files: dict[str, Path] = {}

        for nsp in args.input:
            is_nsz = nsp.suffix.lower() == ".nsz"
            print(f"Parsing {'NSZ' if is_nsz else 'NSP'}: {nsp.name}")
            for p in extract_nsp(nsp, tmpdir_path, verbose=True):
                all_files[p.name] = p

        secure_files = [(name, path) for name, path in sorted(all_files.items())]
        print(f"\nBuilding XCI: {out_path} ({len(secure_files)} files)")
        with open(out_path, "wb") as out_fh:
            build_xci(secure_files, out_fh)

    print(f"XCI written: {out_path} ({format_size(out_path.stat().st_size)})")
    print("Done.")


if __name__ == "__main__":
    main()
