"""Convert one or more NSP/NSZ files to a single XCI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _extract_nsz(nsz_path: Path, fh, tmpdir: Path) -> list[Path]:
    """Extract an NSZ file, decompressing .ncz entries to .nca."""
    from nx_archiver.pfs0 import parse_pfs0
    from nx_archiver.ncz import decompress_ncz

    pfs0 = parse_pfs0(fh)
    paths: list[Path] = []

    for entry in pfs0.entries:
        if entry.name.endswith(".ncz"):
            nca_name = entry.name[:-4] + ".nca"
            out_path = tmpdir / nca_name
            print(f"    {entry.name} -> {nca_name} (decompressing...)")
            fh.seek(entry.offset)
            with open(out_path, "wb") as out:
                decompress_ncz(fh, out, entry.size)
            print(f"      -> {out_path.stat().st_size / (1024**2):.1f} MB decompressed")
            paths.append(out_path)
        else:
            out_path = tmpdir / entry.name
            print(f"    {entry.name} ({entry.size / (1024**2):.1f} MB)")
            fh.seek(entry.offset)
            with open(out_path, "wb") as out:
                remaining = entry.size
                while remaining:
                    chunk = fh.read(min(1 << 20, remaining))
                    if not chunk:
                        break
                    out.write(chunk)
                    remaining -= len(chunk)
            paths.append(out_path)

    return paths


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Convert NSP/NSZ(s) to XCI")
    parser.add_argument("input", type=Path, nargs="+", help="Input NSP/NSZ file(s)")
    parser.add_argument("-o", "--output", type=Path, help="Output XCI file (default: <first_basename>.xci)")
    parser.add_argument("--keys", type=Path, help="Path to prod.keys")
    args = parser.parse_args(argv)

    for nsp in args.input:
        if not nsp.exists():
            print(f"Error: {nsp} not found", file=sys.stderr)
            sys.exit(1)

    from nx_archiver.pfs0 import parse_pfs0
    from nx_archiver.xci import build_xci

    out_path = args.output or args.input[0].with_suffix(".xci")

    import tempfile
    with tempfile.TemporaryDirectory(prefix="nx-archiver-") as tmpdir:
        tmpdir_path = Path(tmpdir)
        all_files: dict[str, Path] = {}

        for nsp in args.input:
            is_nsz = nsp.suffix.lower() == ".nsz"
            print(f"Parsing {'NSZ' if is_nsz else 'NSP'}: {nsp.name}")
            with open(nsp, "rb") as fh:
                if is_nsz:
                    extracted = _extract_nsz(nsp, fh, tmpdir_path)
                else:
                    pfs0 = parse_pfs0(fh)
                    print(f"  Found {len(pfs0.entries)} files:")
                    for entry in pfs0.entries:
                        print(f"    {entry.name} ({entry.size / (1024**2):.1f} MB)")
                    extracted = pfs0.extract_all(fh, tmpdir_path)
                for p in extracted:
                    all_files[p.name] = p

        secure_files = [(name, path) for name, path in sorted(all_files.items())]
        print(f"\nBuilding XCI: {out_path} ({len(secure_files)} files)")
        with open(out_path, "wb") as out_fh:
            build_xci(secure_files, out_fh)

    print(f"XCI written: {out_path} ({out_path.stat().st_size / (1024**2):.1f} MB)")
    print("Done.")


if __name__ == "__main__":
    main()
