"""Core image manipulation: resizing, conversion, compression."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image

# Supported input formats
SUPPORTED_INPUT_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".gif"}

# Extension -> Pillow format mapping
FORMAT_BY_EXT = {
    ".png": "PNG",
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".webp": "WEBP",
    ".bmp": "BMP",
    ".tiff": "TIFF",
}


@dataclass
class ResizeOptions:
    """Resize / compression options.

    Only one of the size strategies should be provided: width, height,
    max_dim or scale. If none is set, the image keeps its dimensions.
    """

    width: int | None = None
    height: int | None = None
    max_dim: int | None = None  # longest side
    scale: float | None = None  # factor (e.g. 0.5)
    quality: int = 85  # 1-100, used for JPEG/WebP
    output_format: str | None = None  # "JPEG", "PNG", "WEBP" — None => keep
    keep_aspect: bool = True
    optimize: bool = True


def compute_target_size(src_w: int, src_h: int, opts: ResizeOptions) -> tuple[int, int]:
    """Computes target dimensions based on the options."""
    if opts.scale is not None:
        return max(1, round(src_w * opts.scale)), max(1, round(src_h * opts.scale))

    if opts.max_dim is not None:
        if src_w >= src_h:
            new_w = opts.max_dim
            new_h = round(src_h * opts.max_dim / src_w)
        else:
            new_h = opts.max_dim
            new_w = round(src_w * opts.max_dim / src_h)
        return max(1, new_w), max(1, new_h)

    if opts.width is not None and opts.height is not None:
        if opts.keep_aspect:
            ratio = min(opts.width / src_w, opts.height / src_h)
            return max(1, round(src_w * ratio)), max(1, round(src_h * ratio))
        return opts.width, opts.height

    if opts.width is not None:
        ratio = opts.width / src_w
        return opts.width, max(1, round(src_h * ratio))

    if opts.height is not None:
        ratio = opts.height / src_h
        return max(1, round(src_w * ratio)), opts.height

    return src_w, src_h


def _resolve_format(src_path: Path, opts: ResizeOptions) -> tuple[str, str]:
    """Returns (Pillow format, target extension)."""
    if opts.output_format:
        fmt = opts.output_format.upper()
        ext_map = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}
        return fmt, ext_map.get(fmt, f".{fmt.lower()}")
    ext = src_path.suffix.lower()
    return FORMAT_BY_EXT.get(ext, "PNG"), ext


def process_image(src: Path, dst: Path, opts: ResizeOptions) -> tuple[int, int, int]:
    """Processes an image and writes it to disk.

    Returns (final_width, final_height, size_bytes).
    """
    with Image.open(src) as img:
        target_w, target_h = compute_target_size(img.width, img.height, opts)

        if (target_w, target_h) != (img.width, img.height):
            img = img.resize((target_w, target_h), Image.LANCZOS)

        fmt, _ = _resolve_format(src, opts)

        # Mode conversion if needed (JPEG does not support alpha)
        if fmt == "JPEG" and img.mode in ("RGBA", "LA", "P"):
            background = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            background.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
            img = background

        save_kwargs: dict = {"optimize": opts.optimize}
        if fmt in ("JPEG", "WEBP"):
            save_kwargs["quality"] = opts.quality
        if fmt == "JPEG":
            save_kwargs["progressive"] = True

        dst.parent.mkdir(parents=True, exist_ok=True)
        img.save(dst, format=fmt, **save_kwargs)

        return target_w, target_h, dst.stat().st_size


def collect_inputs(paths: list[Path], recursive: bool = False) -> list[Path]:
    """Expands paths (files or folders) into a list of image files."""
    out: list[Path] = []
    for p in paths:
        if p.is_file():
            if p.suffix.lower() in SUPPORTED_INPUT_EXTS:
                out.append(p)
        elif p.is_dir():
            it = p.rglob("*") if recursive else p.glob("*")
            for f in it:
                if f.is_file() and f.suffix.lower() in SUPPORTED_INPUT_EXTS:
                    out.append(f)
    return sorted(set(out))


def build_output_path(
    src: Path,
    src_root: Path,
    out_dir: Path | None,
    suffix: str,
    opts: ResizeOptions,
) -> Path:
    """Computes the output path for a source image."""
    _, ext = _resolve_format(src, opts)
    stem = src.stem + suffix

    if out_dir is None:
        return src.with_name(stem + ext)

    try:
        rel = src.relative_to(src_root)
        return out_dir / rel.with_name(stem + ext)
    except ValueError:
        return out_dir / (stem + ext)
