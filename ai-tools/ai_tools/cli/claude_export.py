"""CLI ``claude-export``: exports local Claude data into a portable ZIP."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from ai_tools.claude_export import export


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="claude-export",
        description="Export local Claude Code / Claude Desktop data into a ZIP.",
    )
    parser.add_argument(
        "--output",
        metavar="PATH",
        type=Path,
        default=None,
        help="Output ZIP path (default: ~/claude_export_YYYYMMDD.zip)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be included without creating the ZIP",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    today = date.today().strftime("%Y%m%d")
    output = args.output.expanduser() if args.output else Path.home() / f"claude_export_{today}.zip"

    print(f"Claude Data Export — {today}")
    print(f"Destination: {output}")
    if args.dry_run:
        print("*** DRY RUN MODE ***")
    print()

    total = export(output, today, dry_run=args.dry_run)

    if args.dry_run:
        print("\nNo file created (dry-run).")
        return 0

    size_mb = output.stat().st_size / 1_048_576
    print(f"\n{total} files exported → {output} ({size_mb:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
