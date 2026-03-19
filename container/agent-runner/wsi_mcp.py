from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from PIL import Image
from tiffslide import TiffSlide


mcp = FastMCP("pathclaw_wsi")

WORKSPACE_GROUP = Path("/workspace/group").resolve()
WORKSPACE_EXTRA = Path("/workspace/extra").resolve()
OUTPUT_DIR = WORKSPACE_GROUP / "wsi-output"
OUTPUT_FORMAT = "WEBP"
OUTPUT_EXTENSION = ".webp"
OUTPUT_QUALITY = 85
SUPPORTED_SUFFIXES = {
    ".svs",
    ".tif",
    ".tiff",
    ".ndpi",
    ".scn",
    ".bif",
    ".qptiff",
}


def _reject_cloud_source(source: str) -> None:
    if "://" in source:
        raise ValueError("Cloud and fsspec sources are not enabled in PathClaw v1 yet")


def _resolve_input_path(source: str) -> Path:
    _reject_cloud_source(source)

    raw = Path(source)
    if raw.is_absolute():
        resolved = raw.resolve()
    else:
        resolved = (WORKSPACE_GROUP / raw).resolve()

    allowed_roots = (WORKSPACE_GROUP, WORKSPACE_EXTRA)
    if not any(
        resolved == root or str(resolved).startswith(f"{root}{os.sep}")
        for root in allowed_roots
    ):
        raise ValueError(f"Path must live under {WORKSPACE_GROUP} or {WORKSPACE_EXTRA}")

    if not resolved.exists():
        raise FileNotFoundError(f"Slide not found: {resolved}")

    return resolved


def _ensure_output_dir() -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return OUTPUT_DIR


def _sanitize_output_name(name: str | None, fallback: str) -> str:
    candidate = name or fallback
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "-" for ch in candidate)
    safe = safe.strip(".-") or fallback
    if not safe.lower().endswith(OUTPUT_EXTENSION):
        safe = f"{safe}{OUTPUT_EXTENSION}"
    return safe


def _vendor_from_properties(properties: dict[str, Any]) -> str | None:
    for key in ("tiffslide.vendor", "openslide.vendor", "vendor"):
        value = properties.get(key)
        if value:
            return str(value)
    return None


def _base_mpp(properties: dict[str, Any]) -> float | None:
    for key in ("tiffslide.mpp-x", "openslide.mpp-x", "mpp-x"):
        value = properties.get(key)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _pick_level(slide: TiffSlide, target_mpp: float | None, requested_level: int | None) -> int:
    if requested_level is not None:
        if requested_level < 0 or requested_level >= slide.level_count:
            raise ValueError(f"Level {requested_level} out of range 0..{slide.level_count - 1}")
        return requested_level

    if target_mpp is None:
        return 0

    base_mpp = _base_mpp(dict(slide.properties))
    if base_mpp is None:
        raise ValueError("Slide does not expose base MPP; provide an explicit level instead")

    best_level = 0
    best_delta = float("inf")
    for idx, downsample in enumerate(slide.level_downsamples):
      current_mpp = base_mpp * float(downsample)
      delta = abs(current_mpp - target_mpp)
      if delta < best_delta:
          best_delta = delta
          best_level = idx
    return best_level


def _properties_dict(slide: TiffSlide) -> dict[str, str]:
    return {str(key): str(value) for key, value in dict(slide.properties).items()}


def _save_image(image: Image.Image, output_name: str | None, fallback_stem: str) -> Path:
    output_dir = _ensure_output_dir()
    filename = _sanitize_output_name(output_name, fallback_stem)
    output_path = (output_dir / filename).resolve()

    if output_path != output_dir and not str(output_path).startswith(f"{output_dir}{os.sep}"):
        raise ValueError("Output path must stay under /workspace/group/wsi-output")

    image.save(output_path, format=OUTPUT_FORMAT, quality=OUTPUT_QUALITY)
    return output_path


def _fit_within(width: int, height: int, size: tuple[int, int]) -> tuple[int, int]:
    max_width, max_height = size
    if max_width <= 0 or max_height <= 0:
        raise ValueError("thumbnail size must be positive")
    scale = min(max_width / width, max_height / height)
    scale = min(scale, 1.0)
    return (
        max(1, int(round(width * scale))),
        max(1, int(round(height * scale))),
    )


def _clamp_level0_rect(slide: TiffSlide, x: int, y: int, width: int, height: int) -> tuple[int, int, int, int]:
    base_width, base_height = slide.dimensions
    width = max(1, min(width, base_width))
    height = max(1, min(height, base_height))
    x = max(0, min(x, base_width - width))
    y = max(0, min(y, base_height - height))
    return x, y, width, height


def _level_size_from_level0_rect(slide: TiffSlide, level: int, width: int, height: int) -> tuple[int, int]:
    downsample = float(slide.level_downsamples[level])
    level_width = max(1, int(round(width / downsample)))
    level_height = max(1, int(round(height / downsample)))
    level_dimensions = slide.level_dimensions[level]
    return (
        min(level_width, level_dimensions[0]),
        min(level_height, level_dimensions[1]),
    )


def get_sub_roi_thumb(
    slide: TiffSlide,
    roi_rect: tuple[int, int, int, int],
    roi_res: tuple[int, int],
    sub_roi_rect: tuple[int, int, int, int],
    size: tuple[int, int],
) -> Image.Image:
    """
    Render a higher-resolution thumbnail for a sub-region inside an existing ROI image.

    Parameters:
    - roi_rect: parent ROI in level-0 WSI coordinates (x, y, w, h)
    - roi_res: pixel resolution of the parent ROI image that Gemini saw
    - sub_roi_rect: child ROI in parent ROI-image coordinates (x, y, w, h)
    - size: maximum output thumbnail size as (width, height)
    """
    roi_x, roi_y, roi_w, roi_h = roi_rect
    roi_res_w, roi_res_h = roi_res
    sub_x, sub_y, sub_w, sub_h = sub_roi_rect

    if roi_res_w <= 0 or roi_res_h <= 0:
        raise ValueError("roi_res must be positive")

    scale_x = roi_w / roi_res_w
    scale_y = roi_h / roi_res_h
    level0_x = roi_x + int(round(sub_x * scale_x))
    level0_y = roi_y + int(round(sub_y * scale_y))
    level0_w = max(1, int(round(sub_w * scale_x)))
    level0_h = max(1, int(round(sub_h * scale_y)))
    level0_x, level0_y, level0_w, level0_h = _clamp_level0_rect(slide, level0_x, level0_y, level0_w, level0_h)

    region = slide.read_region((level0_x, level0_y), 0, (level0_w, level0_h)).convert("RGB")
    output_size = _fit_within(region.width, region.height, size)
    if region.size != output_size:
        region = region.resize(output_size, Image.Resampling.LANCZOS)
    return region


def get_roi_thumb(
    slide: TiffSlide,
    thumb_res: tuple[int, int],
    roi_rect: tuple[int, int, int, int],
    size: tuple[int, int],
) -> Image.Image:
    """
    Render a higher-resolution thumbnail for an ROI defined on a slide thumbnail.

    Parameters:
    - thumb_res: resolution of the full-slide thumbnail Gemini/Claude saw
    - roi_rect: ROI in thumbnail coordinates (x, y, w, h)
    - size: maximum output thumbnail size as (width, height)
    """
    thumb_w, thumb_h = thumb_res
    if thumb_w <= 0 or thumb_h <= 0:
        raise ValueError("thumb_res must be positive")

    slide_w, slide_h = slide.dimensions
    roi_x, roi_y, roi_w, roi_h = roi_rect
    level0_rect = (
        int(round(roi_x * slide_w / thumb_w)),
        int(round(roi_y * slide_h / thumb_h)),
        max(1, int(round(roi_w * slide_w / thumb_w))),
        max(1, int(round(roi_h * slide_h / thumb_h))),
    )
    return get_sub_roi_thumb(
        slide=slide,
        roi_rect=level0_rect,
        roi_res=(roi_w, roi_h),
        sub_roi_rect=(0, 0, roi_w, roi_h),
        size=size,
    )


@mcp.tool()
def list_wsi_slides(root_or_dir: str) -> dict[str, Any]:
    root = _resolve_input_path(root_or_dir)
    if root.is_file():
        candidates = [root]
    else:
        candidates = [
            path
            for path in root.rglob("*")
            if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
        ]

    slides = [
        {
            "name": path.name,
            "path": str(path),
            "size_bytes": path.stat().st_size,
        }
        for path in sorted(candidates)
    ]
    return {"slides": slides}


@mcp.tool()
def inspect_wsi(source: str) -> dict[str, Any]:
    slide_path = _resolve_input_path(source)
    slide = TiffSlide(str(slide_path))
    try:
        properties = _properties_dict(slide)
        level_dimensions = [list(dim) for dim in slide.level_dimensions]
        return {
            "source": str(slide_path),
            "format": slide_path.suffix.lower().lstrip("."),
            "width": slide.dimensions[0],
            "height": slide.dimensions[1],
            "level_count": slide.level_count,
            "level_dimensions": level_dimensions,
            "level_downsamples": [float(v) for v in slide.level_downsamples],
            "properties": properties,
            "vendor": _vendor_from_properties(properties),
            "mpp": _base_mpp(properties),
        }
    finally:
        close = getattr(slide, "close", None)
        if callable(close):
            close()


@mcp.tool()
def render_wsi_thumbnail(
    source: str,
    max_size: int,
    output_name: str | None = None,
) -> dict[str, Any]:
    if max_size <= 0:
        raise ValueError("max_size must be positive")

    slide_path = _resolve_input_path(source)
    slide = TiffSlide(str(slide_path))
    try:
        thumbnail = slide.get_thumbnail((max_size, max_size)).convert("RGB")
        output_path = _save_image(thumbnail, output_name, f"{slide_path.stem}-thumbnail")
        return {
            "source": str(slide_path),
            "output_path": str(output_path),
            "width": thumbnail.width,
            "height": thumbnail.height,
        }
    finally:
        close = getattr(slide, "close", None)
        if callable(close):
            close()


@mcp.tool()
def render_wsi_region(
    source: str,
    x: int,
    y: int,
    width: int,
    height: int,
    level: int | None = None,
    mpp: float | None = None,
    output_name: str | None = None,
) -> dict[str, Any]:
    if width <= 0 or height <= 0:
        raise ValueError("width and height must be positive")
    if x < 0 or y < 0:
        raise ValueError("x and y must be non-negative")
    if level is not None and mpp is not None:
        raise ValueError("Provide either level or mpp, not both")

    slide_path = _resolve_input_path(source)
    slide = TiffSlide(str(slide_path))
    try:
        chosen_level = _pick_level(slide, mpp, level)
        base_width, base_height = slide.dimensions
        if x >= base_width or y >= base_height:
            raise ValueError("Requested region origin is outside the slide bounds")
        x, y, width, height = _clamp_level0_rect(slide, x, y, width, height)
        level_size = _level_size_from_level0_rect(slide, chosen_level, width, height)

        region = slide.read_region((x, y), chosen_level, level_size).convert("RGB")
        output_path = _save_image(
            region,
            output_name,
            f"{slide_path.stem}-region-l{chosen_level}-{x}-{y}-{width}x{height}",
        )
        return {
            "source": str(slide_path),
            "output_path": str(output_path),
            "level": chosen_level,
            "width": region.width,
            "height": region.height,
            "requested_level0_region": {
                "x": x,
                "y": y,
                "width": width,
                "height": height,
            },
        }
    finally:
        close = getattr(slide, "close", None)
        if callable(close):
            close()


if __name__ == "__main__":
    mcp.run()
