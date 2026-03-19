from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def build_whole_slide_thumbnail_image_context(
    image_path: str,
    image_width: int,
    image_height: int,
    slide_width: int,
    slide_height: int,
) -> dict[str, Any]:
    return {
        "kind": "whole_slide_thumbnail",
        "image_path": str(Path(image_path).resolve()),
        "image_size": {"width": image_width, "height": image_height},
        "thumbnail_origin": {"x": 0, "y": 0},
        "thumbnail_size": {"width": image_width, "height": image_height},
        "slide_size": {"width": slide_width, "height": slide_height},
        "level0_origin": {"x": 0, "y": 0},
        "level0_size": {"width": slide_width, "height": slide_height},
    }


def build_separated_specimen_thumbnail_image_context(
    specimen_index: int,
    specimen_label: str,
    image_path: str,
    image_width: int,
    image_height: int,
    thumbnail_x: int,
    thumbnail_y: int,
    thumbnail_width: int,
    thumbnail_height: int,
    level0_x: int,
    level0_y: int,
    level0_width: int,
    level0_height: int,
    slide_width: int,
    slide_height: int,
) -> dict[str, Any]:
    return {
        "kind": "separated_specimen_thumbnail",
        "specimen_index": specimen_index,
        "specimen_label": specimen_label,
        "image_path": str(Path(image_path).resolve()),
        "image_size": {"width": image_width, "height": image_height},
        "thumbnail_origin": {"x": thumbnail_x, "y": thumbnail_y},
        "thumbnail_size": {"width": thumbnail_width, "height": thumbnail_height},
        "slide_size": {"width": slide_width, "height": slide_height},
        "level0_origin": {"x": level0_x, "y": level0_y},
        "level0_size": {"width": level0_width, "height": level0_height},
    }


def load_image_analysis_context(
    context_file: str | None,
    image_path: str,
    image_width: int,
    image_height: int,
    slide_width: int,
    slide_height: int,
) -> dict[str, Any]:
    if not context_file:
        return build_whole_slide_thumbnail_image_context(
            image_path=image_path,
            image_width=image_width,
            image_height=image_height,
            slide_width=slide_width,
            slide_height=slide_height,
        )

    payload = json.loads(Path(context_file).read_text())
    payload.setdefault("image_path", str(Path(image_path).resolve()))
    payload.setdefault("image_size", {"width": image_width, "height": image_height})
    payload.setdefault("slide_size", {"width": slide_width, "height": slide_height})
    payload.setdefault("thumbnail_origin", {"x": 0, "y": 0})
    payload.setdefault("thumbnail_size", payload["image_size"])
    payload.setdefault("level0_origin", {"x": 0, "y": 0})
    payload.setdefault("level0_size", {"width": slide_width, "height": slide_height})
    return payload


def convert_normalized_box_2d_to_image_rect(
    box_2d: list[Any],
    image_width: int,
    image_height: int,
) -> dict[str, int]:
    if len(box_2d) != 4:
        raise ValueError(f"Expected box_2d with 4 values, got: {box_2d}")
    y0, x0, y1, x1 = [max(0.0, min(1000.0, float(value))) for value in box_2d]
    x = int(round((x0 / 1000.0) * image_width))
    y = int(round((y0 / 1000.0) * image_height))
    x1_px = int(round((x1 / 1000.0) * image_width))
    y1_px = int(round((y1 / 1000.0) * image_height))
    return {
        "x": x,
        "y": y,
        "width": max(1, x1_px - x),
        "height": max(1, y1_px - y),
    }


def map_image_rect_to_thumbnail_rect(
    context: dict[str, Any],
    image_rect: dict[str, int],
) -> dict[str, int]:
    image_size = context["image_size"]
    thumbnail_origin = context["thumbnail_origin"]
    thumbnail_size = context["thumbnail_size"]
    thumbnail_scale_x = thumbnail_size["width"] / max(1, image_size["width"])
    thumbnail_scale_y = thumbnail_size["height"] / max(1, image_size["height"])
    return {
        "x": thumbnail_origin["x"] + int(round(image_rect["x"] * thumbnail_scale_x)),
        "y": thumbnail_origin["y"] + int(round(image_rect["y"] * thumbnail_scale_y)),
        "width": max(1, int(round(image_rect["width"] * thumbnail_scale_x))),
        "height": max(1, int(round(image_rect["height"] * thumbnail_scale_y))),
    }


def map_image_rect_to_level0_region(
    context: dict[str, Any],
    image_rect: dict[str, int],
) -> dict[str, int]:
    image_size = context["image_size"]
    level0_origin = context["level0_origin"]
    level0_size = context["level0_size"]
    level0_scale_x = level0_size["width"] / max(1, image_size["width"])
    level0_scale_y = level0_size["height"] / max(1, image_size["height"])
    return {
        "x": int(round(level0_origin["x"] + image_rect["x"] * level0_scale_x)),
        "y": int(round(level0_origin["y"] + image_rect["y"] * level0_scale_y)),
        "width": max(1, int(round(image_rect["width"] * level0_scale_x))),
        "height": max(1, int(round(image_rect["height"] * level0_scale_y))),
    }


def map_image_rect_to_all_coordinate_systems(
    context: dict[str, Any],
    image_rect: dict[str, int],
) -> dict[str, Any]:
    return {
        "image_rect": dict(image_rect),
        "thumbnail_rect": map_image_rect_to_thumbnail_rect(context, image_rect),
        "level0_region": map_image_rect_to_level0_region(context, image_rect),
    }
