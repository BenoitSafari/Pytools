"""Replace the update NCAs of an XCI with those from a new update NSP/NSZ.

Use case: you have an XCI containing base + old update v1.x.y, and a new
update NSP v1.x.z. This command strips the old update artifacts (NCAs and
ticket files whose TitleID ends in 800) from the XCI's secure partition and
injects the contents of the new update NSP.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from nx_archiver.cli._common import format_size
from nx_archiver.cli.nsp_extract import extract_nsp
from nx_archiver.cli.title_id import TIK_NAME_RE, base_id, classify


def _classify_entry(
    entry,
    xci_fh,
    header_key: bytes,
) -> tuple[str, str | None]:
    """Return (kind, title_id) for an XCI secure partition entry.

    *kind* is one of 'base', 'update', 'dlc', 'unknown'.
    *title_id* is the 16-hex TitleID, or None when undeterminable.
    """
    name = entry.name

    # Tickets and certs encode TitleID in their filename
    if name.endswith(".tik") or name.endswith(".cert"):
        m = TIK_NAME_RE.match(name)
        if m:
            tid = m.group(1).upper()
            return classify(tid), tid
        return "unknown", None

    # NCAs need header decryption to read program_id
    if name.endswith(".nca"):
        from nx_archiver.nca import read_nca_info

        try:
            info = read_nca_info(xci_fh, entry.offset, header_key)
            tid = f"{info.program_id:016X}"
            return classify(tid), tid
        except Exception:
            return "unknown", None

    return "unknown", None


def _read_nsp_title_id(nsp_path: Path) -> str | None:
    """Probe an NSP/NSZ for its TitleID via the .tik entry name."""
    from nx_archiver.pfs0 import parse_pfs0

    try:
        with open(nsp_path, "rb") as fh:
            pfs0 = parse_pfs0(fh)
            for entry in pfs0.entries:
                m = TIK_NAME_RE.match(entry.name)
                if m:
                    return m.group(1).upper()
    except Exception:
        return None
    return None


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Replace update NCAs in an XCI with those from a new update NSP/NSZ."
    )
    parser.add_argument("xci", type=Path, help="Input XCI (base + old update)")
    parser.add_argument("nsp", type=Path, help="New update NSP or NSZ")
    parser.add_argument("-o", "--output", type=Path, required=True, help="Output XCI")
    parser.add_argument(
        "--keys", type=Path, help="Path to prod.keys (default: ~/.switch/prod.keys)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Skip the base-ID match check between XCI and NSP",
    )
    args = parser.parse_args(argv)

    if not args.xci.exists():
        print(f"Error: {args.xci} not found", file=sys.stderr)
        sys.exit(1)
    if not args.nsp.exists():
        print(f"Error: {args.nsp} not found", file=sys.stderr)
        sys.exit(1)

    from nx_archiver.hfs0 import FileSlice
    from nx_archiver.keys import get_header_key, load_keys
    from nx_archiver.xci import build_xci, parse_xci

    keys = load_keys(args.keys)
    header_key = get_header_key(keys)

    # 1. Validate NSP is an update
    nsp_tid = _read_nsp_title_id(args.nsp)
    if nsp_tid is None:
        print(f"Error: could not read TitleID from {args.nsp}", file=sys.stderr)
        sys.exit(1)
    if classify(nsp_tid) != "update":
        print(
            f"Error: {args.nsp.name} TitleID {nsp_tid} is not an update "
            f"(last 3 hex must be '800', got '{nsp_tid[-3:]}')",
            file=sys.stderr,
        )
        sys.exit(1)
    nsp_base = base_id(nsp_tid)
    print(f"NSP update TitleID: {nsp_tid} (base={nsp_base})")

    # 2. Parse XCI, classify entries
    print(f"\nParsing XCI: {args.xci}")
    with open(args.xci, "rb") as xci_fh:
        xci = parse_xci(xci_fh)

        secure = xci.partitions.get("secure")
        if secure is None or not secure.hfs0.entries:
            print("Error: XCI has no secure partition", file=sys.stderr)
            sys.exit(1)

        keep: list[tuple[str, FileSlice]] = []
        removed: list[tuple[str, str]] = []  # (name, title_id)
        kept_base_ids: set[str] = set()

        for entry in secure.hfs0.entries:
            kind, tid = _classify_entry(entry, xci_fh, header_key)
            if kind == "update":
                removed.append((entry.name, tid or "?"))
                print(f"  [remove] {entry.name} (TitleID={tid}, kind=update)")
                continue

            keep.append(
                (
                    entry.name,
                    FileSlice(path=args.xci, offset=entry.offset, size=entry.size),
                )
            )
            if tid:
                kept_base_ids.add(base_id(tid))
                print(f"  [keep]   {entry.name} (TitleID={tid}, kind={kind})")
            else:
                print(f"  [keep]   {entry.name} (no TitleID)")

        if not removed:
            print("\nWarning: no update artifacts found in the XCI — nothing to remove.")

        # 3. Validate base ID match
        if not args.force and kept_base_ids and nsp_base not in kept_base_ids:
            print(
                f"\nError: NSP base_id {nsp_base} does not match any kept entries "
                f"({sorted(kept_base_ids)}). Use --force to override.",
                file=sys.stderr,
            )
            sys.exit(1)

        # 4. Preserve other partitions (zero-copy)
        update_files: list[tuple[str, FileSlice]] = []
        logo_files: list[tuple[str, FileSlice]] = []
        normal_files: list[tuple[str, FileSlice]] = []
        for part_name, target in [
            ("update", update_files),
            ("logo", logo_files),
            ("normal", normal_files),
        ]:
            part = xci.partitions.get(part_name)
            if part:
                for entry in part.hfs0.entries:
                    target.append(
                        (
                            entry.name,
                            FileSlice(path=args.xci, offset=entry.offset, size=entry.size),
                        )
                    )

        # 5. Extract new update NSP/NSZ
        with tempfile.TemporaryDirectory(prefix="nx-archiver-xci-update-") as tmpdir:
            tmpdir_path = Path(tmpdir)
            print(f"\nExtracting {args.nsp.name} to temp dir...")
            extracted = extract_nsp(args.nsp, tmpdir_path)

            # Filter out artifacts that don't belong in an XCI secure partition
            kept_names = {n for n, _ in keep}
            new_files: list[tuple[str, Path]] = []
            for p in extracted:
                if p.name.endswith(".cnmt.xml"):
                    continue  # NSP-only metadata, not used in XCIs
                if p.name in kept_names:
                    print(f"  [replace] {p.name}")
                    keep = [(n, s) for n, s in keep if n != p.name]
                else:
                    print(f"  [add]     {p.name} ({format_size(p.stat().st_size)})")
                new_files.append((p.name, p))

            secure_files = sorted(keep + new_files, key=lambda x: x[0])

            # 6. Write output XCI
            print(f"\nBuilding XCI: {args.output}")
            print(
                f"  Secure: {len(secure_files)} files "
                f"(kept {len(keep)} + new {len(new_files)}, removed {len(removed)})"
            )

            args.output.parent.mkdir(parents=True, exist_ok=True)
            with open(args.output, "wb") as out_fh:
                build_xci(
                    secure_files,
                    out_fh,
                    update_files=update_files,
                    normal_files=normal_files,
                    logo_files=logo_files,
                    original_header=xci.header.raw,
                )

    print(f"\nXCI written: {args.output} ({format_size(args.output.stat().st_size)})")
    print("Done.")


if __name__ == "__main__":
    main()
