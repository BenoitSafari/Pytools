"""Scan a folder of NSP/NSZ files and build one XCI per game (base + updates + DLC)."""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
from pathlib import Path

from nx_archiver.cli._common import format_size
from nx_archiver.cli.nsp_extract import extract_nsp
from nx_archiver.cli.title_id import (
    TIK_NAME_RE,
    TITLE_ID_RE,
    VERSION_RE,
    base_id,
    classify,
)


def _read_title_id_from_nsp(path: Path) -> str | None:
    """Extract the TitleID from the .tik name inside the NSP/NSZ PFS0.

    The ticket name is ``<titleid><rightsid>.tik``: the first 16 hex give the
    TitleID. A fast probe, with no decryption.
    """
    try:
        from nx_archiver.pfs0 import parse_pfs0

        with open(path, "rb") as fh:
            pfs0 = parse_pfs0(fh)
            for entry in pfs0.entries:
                m = TIK_NAME_RE.match(entry.name)
                if m:
                    return m.group(1).upper()
    except Exception:
        pass
    return None


def scan_directory(directory: Path) -> dict[str, dict[str, list[Path]]]:
    """Scan *directory* and return groups indexed by base_id.

    Each group is a dict with the keys 'base', 'update', 'dlc'.
    """
    groups: dict[str, dict[str, list[Path]]] = {}

    for f in sorted(directory.iterdir()):
        if f.suffix.lower() not in (".nsp", ".nsz"):
            continue

        # TitleID from the filename first (the fastest).
        m = TITLE_ID_RE.search(f.name)
        if m:
            tid = m.group(1).upper()
        else:
            # Fallback: read the .tik name inside the NSP.
            tid = _read_title_id_from_nsp(f)
            if tid:
                print(f"  [probe] {f.name} -> TitleID {tid}")
            else:
                print(f"  [skip] No title ID found: {f.name}", file=sys.stderr)
                continue

        kind = classify(tid)
        gid = base_id(tid)

        groups.setdefault(gid, {"base": [], "update": [], "dlc": []})[kind].append(f)

    return groups


def _game_name(files: dict[str, list[Path]]) -> str:
    """Infer a readable game name from the first base file, otherwise a fallback.

    Strips version suffixes (e.g. ``House v1.0.0[...]`` → ``House``) so they are
    not carried into the XCI name.
    """
    for kind in ("base", "update", "dlc"):
        for p in files[kind]:
            name = p.name
            bracket = name.find(" [")
            if bracket > 0:
                candidate = name[:bracket].strip()
            else:
                bracket = name.find("[")
                if bracket > 0:
                    candidate = name[:bracket].strip()
                else:
                    continue
            # Strip a possible version suffix "v1.0.0" or "v3".
            candidate = re.sub(r"\s+v\d[\d.]*$", "", candidate).strip()
            if candidate:
                return candidate
    return "Unknown"


# "Readable" (dotted) version anywhere in the filename.
# Accepts: "v1.0.4", "Up v1.0.3", "UPD1.3.0", "Update 1.0.2", "Update v1.3.0".
_HUMAN_VERSION_RE = re.compile(r"(?:\bv|\bUPD\s*|\bUpdate\s+v?)(\d+\.\d+(?:\.\d+)*)\b")


def _update_version(files: dict[str, list[Path]]) -> str | None:
    """Extract the update version from the update filenames.

    Priority:
    1. readable dotted version in the name, *before* the first ``[``
       (e.g. ``House v1.0.4[...]`` → ``v1.0.4`` or ``Up v1.0.3`` → ``v1.0.3``);
    2. integer ``[vNNNNNN]`` decoded via the Nintendo scheme
       ``(n >> 16).((n >> 8) & 0xFF).(n & 0xFF)``.

    Returns None when no update file is present.
    """
    for p in files.get("update", []):
        name = p.name

        # 1. Readable version anywhere (also catches "[Up v1.0.3]").
        hm = _HUMAN_VERSION_RE.search(name)
        if hm:
            return f"v{hm.group(1)}"

        # 2. Integer [vNNNNNN] in brackets.
        bm = VERSION_RE.search(name)
        if not bm:
            continue
        raw = bm.group(1)
        if "." in raw:
            return f"v{raw}"
        try:
            n = int(raw)
            major = (n >> 16) & 0xFFFF
            minor = (n >> 8) & 0xFF
            patch = n & 0xFF
            return f"v{major}.{minor}.{patch}"
        except ValueError:
            return f"v{raw}"
    return None


def _xci_filename(game_name: str, files: dict[str, list[Path]]) -> str:
    """Build the XCI name according to the convention.

    Format: ``TITLE_IN_UPPERCASE-(vX.X.X+DLC).xci``
    - words separated by underscores, all uppercase;
    - version suffix only if an update is present;
    - ``+DLC`` added when DLC are included;
    - no suffix for a base game alone (neither update nor DLC).
    """
    title = re.sub(r'[\\/:*?"<>|]', "", game_name)  # strip forbidden characters
    title = re.sub(r"[\s\-]+", "_", title.strip())  # spaces/hyphens → underscore
    title = re.sub(r"_+", "_", title).upper()

    version = _update_version(files)
    has_dlc = bool(files.get("dlc"))

    if version or has_dlc:
        inner = (version or "") + ("+DLC" if has_dlc else "")
        return f"{title}-({inner}).xci"
    return f"{title}.xci"


def build_group_xci(
    game_name: str,
    files: dict[str, list[Path]],
    output_dir: Path,
    dry_run: bool = False,
) -> Path | None:
    """Build a single XCI from base + updates + DLC.

    Returns the output path, or None if the operation is skipped.
    """
    base_files = files["base"]
    update_files = files["update"]
    dlc_files = files["dlc"]

    if not base_files:
        print(f"  [skip] No base NSP found for '{game_name}'")
        return None

    inputs = base_files + update_files + dlc_files

    out_name = _xci_filename(game_name, files)
    out_path = output_dir / out_name

    print(f"\n{'[DRY RUN] ' if dry_run else ''}Building: {out_name}")
    print(f"  Base   : {[f.name for f in base_files]}")
    print(f"  Update : {[f.name for f in update_files]}")
    print(f"  DLC    : {[f.name for f in dlc_files]}")

    if dry_run:
        print(f"  -> Would write: {out_path}")
        return out_path

    if out_path.exists():
        print(f"  [skip] Output already exists: {out_path}")
        return out_path

    from nx_archiver.xci import build_xci

    with tempfile.TemporaryDirectory(prefix="nx-archiver-make-xci-") as tmpdir:
        tmpdir_path = Path(tmpdir)
        all_files: dict[str, Path] = {}

        for nsp in inputs:
            is_nsz = nsp.suffix.lower() == ".nsz"
            print(f"  Parsing {'NSZ' if is_nsz else 'NSP'}: {nsp.name}")
            for p in extract_nsp(nsp, tmpdir_path):
                if p.name in all_files:
                    print(f"    [dup] {p.name} — keeping first occurrence")
                else:
                    all_files[p.name] = p

        secure_files = [(name, path) for name, path in sorted(all_files.items())]
        print(f"  Building XCI: {len(secure_files)} NCA(s)")
        with open(out_path, "wb") as out_fh:
            build_xci(secure_files, out_fh)

    print(f"  Written: {out_path} ({format_size(out_path.stat().st_size)})")
    return out_path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Scan a directory of NSP/NSZ files and build one XCI per game."
    )
    parser.add_argument(
        "directory",
        type=Path,
        help="Directory containing NSP/NSZ files",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output directory for XCI files (default: same as input directory)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without writing any files",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        dest="list_only",
        help="List detected groups and exit",
    )
    args = parser.parse_args(argv)

    if not args.directory.is_dir():
        print(f"Error: not a directory: {args.directory}", file=sys.stderr)
        sys.exit(1)

    output_dir = args.output or args.directory
    if not args.dry_run and not args.list_only:
        output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Scanning: {args.directory}")
    groups = scan_directory(args.directory)

    if not groups:
        print("No NSP/NSZ files with title IDs found.")
        return

    print(f"Found {len(groups)} game group(s):\n")
    for gid, files in groups.items():
        name = _game_name(files)
        nb = len(files["base"])
        nu = len(files["update"])
        nd = len(files["dlc"])
        print(f"  [{gid}] {name}  (base={nb}, update={nu}, dlc={nd})")

    if args.list_only:
        return

    print()
    errors: list[str] = []
    for _gid, files in groups.items():
        name = _game_name(files)
        try:
            build_group_xci(name, files, output_dir, dry_run=args.dry_run)
        except Exception as exc:
            msg = f"  [ERROR] {name}: {exc}"
            print(msg, file=sys.stderr)
            errors.append(msg)

    print("\nAll done.")
    if errors:
        print(f"\n{len(errors)} error(s):", file=sys.stderr)
        for e in errors:
            print(e, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
