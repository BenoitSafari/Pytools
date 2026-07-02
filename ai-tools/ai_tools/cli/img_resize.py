"""CLI img-resize: resizes and compresses images for the web."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ai_tools.image import (
    ResizeOptions,
    build_output_path,
    collect_inputs,
    process_image,
)


def _human_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="img-resize",
        description="Resize and compress images (PNG/JPEG/WebP) for the web.",
    )
    p.add_argument("inputs", nargs="+", type=Path, help="Files or folders to process")
    p.add_argument("-r", "--recursive", action="store_true", help="Recurse into folders")

    size = p.add_mutually_exclusive_group()
    size.add_argument("--width", type=int, help="Target width (height auto if unspecified)")
    size.add_argument("--height", type=int, help="Target height (width auto if unspecified)")
    size.add_argument("--max-dim", type=int, help="Longest side bounded to this value")
    size.add_argument("--scale", type=float, help="Scale factor (e.g. 0.5)")

    p.add_argument(
        "--height-with-width",
        type=int,
        dest="height_pair",
        help="Combined with --width to bound both dimensions (aspect ratio preserved)",
    )

    p.add_argument(
        "-q",
        "--quality",
        type=int,
        default=85,
        help="Quality 1-100 (JPEG/WebP, default 85)",
    )
    p.add_argument(
        "-f",
        "--format",
        choices=["jpeg", "png", "webp"],
        default=None,
        help="Output format (otherwise: keep the original)",
    )
    p.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=None,
        help="Output folder (otherwise: next to the source file)",
    )
    p.add_argument(
        "--suffix",
        default="",
        help="Name suffix (e.g. '_web'). Default: empty with --output-dir, else '_resized'",
    )
    p.add_argument(
        "--no-aspect",
        action="store_true",
        help="Do not preserve aspect ratio (only with --width AND --height)",
    )
    p.add_argument(
        "--no-optimize",
        action="store_true",
        help="Disable Pillow optimization",
    )
    p.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="Write nothing, only show what would be done",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    width = args.width
    height = args.height
    if args.height_pair is not None:
        if width is None:
            print("error: --height-with-width requires --width", file=sys.stderr)
            return 2
        height = args.height_pair

    suffix = args.suffix
    if not suffix and args.output_dir is None:
        suffix = "_resized"

    opts = ResizeOptions(
        width=width,
        height=height,
        max_dim=args.max_dim,
        scale=args.scale,
        quality=args.quality,
        output_format={"jpeg": "JPEG", "png": "PNG", "webp": "WEBP"}.get(args.format),
        keep_aspect=not args.no_aspect,
        optimize=not args.no_optimize,
    )

    files = collect_inputs(args.inputs, recursive=args.recursive)
    if not files:
        print("No image file found.", file=sys.stderr)
        return 1

    # Root used to preserve the directory tree in the output
    src_root = args.inputs[0] if args.inputs[0].is_dir() else args.inputs[0].parent

    total_in = 0
    total_out = 0
    errors = 0

    for f in files:
        dst = build_output_path(f, src_root, args.output_dir, suffix, opts)
        if dst.resolve() == f.resolve():
            print(f"  ! skip (dst == src): {f}", file=sys.stderr)
            continue
        try:
            in_size = f.stat().st_size
            total_in += in_size
            if args.dry_run:
                print(f"  - {f}  ->  {dst}")
                continue
            w, h, out_size = process_image(f, dst, opts)
            total_out += out_size
            ratio = (1 - out_size / in_size) * 100 if in_size else 0
            print(
                f"  ✓ {f.name}  ->  {dst.name}  "
                f"({w}x{h}, {_human_size(in_size)} -> {_human_size(out_size)}, "
                f"-{ratio:.0f}%)"
            )
        except Exception as e:  # noqa: BLE001
            errors += 1
            print(f"  ✗ {f} : {e}", file=sys.stderr)

    if not args.dry_run and total_in:
        ratio = (1 - total_out / total_in) * 100
        print(
            f"\nTotal: {len(files)} file(s), "
            f"{_human_size(total_in)} -> {_human_size(total_out)} (-{ratio:.0f}%)"
        )
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
