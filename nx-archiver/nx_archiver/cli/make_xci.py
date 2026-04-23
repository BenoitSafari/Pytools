"""Scan a directory of NSP/NSZ files and build one XCI per game (base + updates + DLCs)."""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
from pathlib import Path


# Nintendo Switch Title ID convention (16 hex digits = 64-bit):
#
#   Base game : last 3 hex digits = 000  (e.g. 0100633007D48000)
#   Update    : last 3 hex digits = 800  (e.g. 0100633007D48800)
#   DLC       : last 3 hex digits = 001, 002 … (e.g. 0100B3F000BE3001)
#
# All variants share the same upper 13 hex digits (52 bits).
# The group key is therefore title_id[:13].

TITLE_ID_RE = re.compile(r"\[([0-9A-Fa-f]{16})\]")
TIK_NAME_RE = re.compile(r"^([0-9a-fA-F]{16})[0-9a-fA-F]*\.tik$")
VERSION_RE = re.compile(r"\[v([^\]]+)\]")


def _classify(title_id: str) -> str:
    """Return 'base', 'update', or 'dlc' for a 16-hex-digit title ID.

    Nintendo Switch TitleID layout (64-bit):
      - Last 4 hex digits encode the variant:
          x000  -> base game  (last 3 = 000)
          x800  -> update     (last 3 = 800)
          y001+ -> DLC        (last 3 = 001, 002 …)
      - The upper 12 digits identify the game family.

    Example (Hollow Knight):
      0100633007D48000  -> base   (last 3 = 000)
      0100633007D48800  -> update (last 3 = 800)

    Example (Pokken DX):
      0100B3F000BE2000  -> base   (last 3 = 000)
      0100B3F000BE2800  -> update (last 3 = 800)
      0100B3F000BE3001  -> DLC 1  (last 3 = 001)
      0100B3F000BE3002  -> DLC 2  (last 3 = 002)
    """
    last3 = title_id[-3:].upper()
    if last3 == "000":
        return "base"
    if last3 == "800":
        return "update"
    return "dlc"


def _base_id(title_id: str) -> str:
    """Return the group key (upper 12 hex digits) shared by base, update and DLCs."""
    return title_id[:12].upper()


def _read_title_id_from_nsp(path: Path) -> str | None:
    """Extract title ID from the .tik filename inside an NSP/NSZ PFS0.

    The ticket filename is ``<titleid><rightsid>.tik``, so the first 16 hex
    chars are the title ID.  This is a fast, decryption-free probe.
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
    """Scan *directory* and return groups keyed by base_id.

    Each group is a dict with keys 'base', 'update', 'dlc'.
    """
    groups: dict[str, dict[str, list[Path]]] = {}

    for f in sorted(directory.iterdir()):
        if f.suffix.lower() not in (".nsp", ".nsz"):
            continue

        # Try to get title ID from filename first (fastest)
        m = TITLE_ID_RE.search(f.name)
        if m:
            tid = m.group(1).upper()
        else:
            # Fall back to reading the .tik filename inside the NSP
            tid = _read_title_id_from_nsp(f)
            if tid:
                print(f"  [probe] {f.name} -> TitleID {tid}")
            else:
                print(f"  [skip] No title ID found: {f.name}", file=sys.stderr)
                continue

        kind = _classify(tid)
        gid = _base_id(tid)

        if gid not in groups:
            groups[gid] = {"base": [], "update": [], "dlc": []}
        groups[gid][kind].append(f)

    return groups


def _game_name(files: dict[str, list[Path]]) -> str:
    """Derive a human-readable game name from the first base file, or fallback.

    Strips trailing version strings (e.g. ``House v1.0.0[...]`` → ``House``)
    so the version doesn't end up embedded in the XCI filename.
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
            # Strip trailing version string like " v1.0.0" or " v3"
            candidate = re.sub(r"\s+v\d[\d.]*$", "", candidate).strip()
            if candidate:
                return candidate
    return "Unknown"


# Human-readable dotted version pattern anywhere in the filename prefix
_HUMAN_VERSION_RE = re.compile(r"\bv(\d+\.\d+(?:\.\d+)*)\b")


def _update_version(files: dict[str, list[Path]]) -> str | None:
    """Extract the update version string from update filenames.

    Priority:
    1. Human-readable dotted version in the filename *before* the first ``[``
       (e.g. ``House v1.0.4[...]`` → ``v1.0.4``  or  ``Up v1.0.3`` → ``v1.0.3``).
    2. Bracketed ``[vNNNNNN]`` integer decoded via Nintendo's versioning scheme
       ``(n >> 16).(( n >> 8) & 0xFF).(n & 0xFF)``.

    Returns None when no update files are present.
    """
    for p in files.get("update", []):
        name = p.name
        prefix = name[:name.find("[")] if "[" in name else name

        # 1. Human-readable version anywhere in the filename (e.g. "v1.0.3", "v1.0.4")
        #    Search the full name so patterns like "[Up v1.0.3]" are caught too.
        hm = _HUMAN_VERSION_RE.search(name)
        if hm:
            return f"v{hm.group(1)}"

        # 2. Bracketed [vNNNNNN] integer
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
    """Build the XCI filename following the naming convention.

    Format: ``TITLE_IN_UPPERCASE-(vX.X.X+DLC).xci``
    - Title words separated by underscores, all uppercase.
    - Version suffix only when an update is present.
    - ``+DLC`` appended when DLC files are included.
    - No suffix at all when only a base game (no update, no DLC).
    """
    # Uppercase + underscores
    title = re.sub(r'[\\/:*?"<>|]', "", game_name)  # strip filesystem-unsafe chars
    title = re.sub(r"[\s\-]+", "_", title.strip())   # spaces/hyphens → underscore
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
    """Build a single XCI from base + updates + DLCs.

    Returns the output path, or None if skipped.
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

    from nx_archiver.pfs0 import parse_pfs0
    from nx_archiver.xci import build_xci
    from nx_archiver.ncz import decompress_ncz

    with tempfile.TemporaryDirectory(prefix="nx-archiver-make-xci-") as tmpdir:
        tmpdir_path = Path(tmpdir)
        all_files: dict[str, Path] = {}

        for nsp in inputs:
            is_nsz = nsp.suffix.lower() == ".nsz"
            print(f"  Parsing {'NSZ' if is_nsz else 'NSP'}: {nsp.name}")
            with open(nsp, "rb") as fh:
                if is_nsz:
                    extracted = _extract_nsz(fh, tmpdir_path)
                else:
                    pfs0 = parse_pfs0(fh)
                    extracted = pfs0.extract_all(fh, tmpdir_path)
                for p in extracted:
                    if p.name in all_files:
                        print(f"    [dup] {p.name} — keeping first occurrence")
                    else:
                        all_files[p.name] = p

        secure_files = [(name, path) for name, path in sorted(all_files.items())]
        print(f"  Building XCI: {len(secure_files)} NCA(s)")
        with open(out_path, "wb") as out_fh:
            build_xci(secure_files, out_fh)

    print(f"  Written: {out_path} ({out_path.stat().st_size / (1024 ** 2):.0f} MB)")
    return out_path


def _extract_nsz(fh, tmpdir: Path) -> list[Path]:
    """Extract an NSZ file to *tmpdir*, decompressing .ncz → .nca."""
    from nx_archiver.pfs0 import parse_pfs0
    from nx_archiver.ncz import decompress_ncz

    pfs0 = parse_pfs0(fh)
    paths: list[Path] = []

    for entry in pfs0.entries:
        if entry.name.endswith(".ncz"):
            nca_name = entry.name[:-4] + ".nca"
            out_path = tmpdir / nca_name
            fh.seek(entry.offset)
            with open(out_path, "wb") as out:
                decompress_ncz(fh, out, entry.size)
            paths.append(out_path)
        else:
            out_path = tmpdir / entry.name
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
    parser = argparse.ArgumentParser(
        description="Scan a directory of NSP/NSZ files and build one XCI per game."
    )
    parser.add_argument(
        "directory",
        type=Path,
        help="Directory containing NSP/NSZ files",
    )
    parser.add_argument(
        "-o", "--output",
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
    for gid, files in groups.items():
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
