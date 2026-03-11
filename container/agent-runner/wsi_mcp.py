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

        region = slide.read_region((x, y), chosen_level, (width, height)).convert("RGB")
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
        }
    finally:
        close = getattr(slide, "close", None)
        if callable(close):
            close()


if __name__ == "__main__":
    mcp.run()
