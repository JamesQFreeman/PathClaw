from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def build_specimen_entry(
    index: int,
    thumbnail_rect: dict[str, int],
    level0_region: dict[str, int],
    area_pixels: int | None = None,
    box_2d: list[float] | None = None,
    crop_path: str | None = None,
    image_size: dict[str, int] | None = None,
    image_context_path: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "index": index,
        "label": f"Specimen {index}",
        "thumbnail_rect": thumbnail_rect,
        "level0_region": level0_region,
    }
    if area_pixels is not None:
        payload["area_pixels"] = area_pixels
    if box_2d is not None:
        payload["box_2d"] = box_2d
    if crop_path is not None:
        payload["crop_path"] = crop_path
    if image_size is not None:
        payload["image_size"] = image_size
    if image_context_path is not None:
        payload["image_context_path"] = image_context_path
    return payload


def build_tissue_rects_payload(
    thumbnail_path: str,
    slide_width: int,
    slide_height: int,
    specimens: list[dict[str, Any]],
    method: str,
    annotated_thumbnail_path: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "method": method,
        "thumbnail_path": str(Path(thumbnail_path).resolve()),
        "slide_size": {"width": slide_width, "height": slide_height},
        "specimen_count": len(specimens),
        "specimens": specimens,
    }
    if annotated_thumbnail_path is not None:
        payload["annotated_thumbnail_path"] = str(Path(annotated_thumbnail_path).resolve())
    return payload


def write_tissue_rects_payload(output_json: str, payload: dict[str, Any]) -> None:
    Path(output_json).write_text(json.dumps(payload, indent=2) + "\n")
