from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PIL import Image, ImageChops, ImageFilter


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    width: int
    height: int


def _is_tissue_pixel(r: int, g: int, b: int) -> bool:
    brightness = (r + g + b) / 3.0
    chroma = max(r, g, b) - min(r, g, b)
    if brightness >= 248:
        return False
    if brightness <= 228:
        return True
    return chroma >= 14


def _otsu_threshold(histogram: list[int], floor: int) -> int:
    total = sum(histogram)
    if total <= 0:
        return floor

    sum_total = sum(index * count for index, count in enumerate(histogram))
    weight_background = 0
    sum_background = 0.0
    best_threshold = floor
    best_variance = -1.0

    for threshold, count in enumerate(histogram):
        weight_background += count
        if weight_background == 0:
            continue
        weight_foreground = total - weight_background
        if weight_foreground == 0:
            break
        sum_background += threshold * count
        mean_background = sum_background / weight_background
        mean_foreground = (sum_total - sum_background) / weight_foreground
        variance = weight_background * weight_foreground * (mean_background - mean_foreground) ** 2
        if variance > best_variance:
            best_variance = variance
            best_threshold = threshold

    return max(floor, int(best_threshold))


def _build_tissue_mask(image: Image.Image) -> Image.Image:
    hsv = image.convert("HSV")
    _, saturation, value = hsv.split()
    inverted_value = value.point(lambda pixel: 255 - pixel)
    edges = image.convert("L").filter(ImageFilter.GaussianBlur(radius=2)).filter(ImageFilter.FIND_EDGES)

    saturation_threshold = _otsu_threshold(saturation.histogram(), floor=18)
    darkness_threshold = _otsu_threshold(inverted_value.histogram(), floor=20)
    edge_threshold = _otsu_threshold(edges.histogram(), floor=12)

    saturation_mask = saturation.point(lambda pixel: 255 if pixel >= saturation_threshold else 0)
    darkness_mask = inverted_value.point(lambda pixel: 255 if pixel >= darkness_threshold else 0)
    edge_mask = edges.point(lambda pixel: 255 if pixel >= edge_threshold else 0)

    combined = ImageChops.lighter(saturation_mask, darkness_mask)
    combined = ImageChops.lighter(combined, edge_mask)

    closed = combined.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.MinFilter(9))
    opened = closed.filter(ImageFilter.MinFilter(5)).filter(ImageFilter.MaxFilter(5))
    return opened.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.MinFilter(9)).convert("L")


def _component_bounds(mask: bytearray, width: int, height: int) -> list[tuple[int, int, int, int, int]]:
    visited = bytearray(width * height)
    components: list[tuple[int, int, int, int, int]] = []

    for start in range(width * height):
        if not mask[start] or visited[start]:
            continue
        stack = [start]
        visited[start] = 1
        area = 0
        min_x = max_x = start % width
        min_y = max_y = start // width

        while stack:
            idx = stack.pop()
            x = idx % width
            y = idx // width
            area += 1
            min_x = min(min_x, x)
            max_x = max(max_x, x)
            min_y = min(min_y, y)
            max_y = max(max_y, y)

            for ny in range(max(0, y - 1), min(height, y + 2)):
                row_offset = ny * width
                for nx in range(max(0, x - 1), min(width, x + 2)):
                    nidx = row_offset + nx
                    if mask[nidx] and not visited[nidx]:
                        visited[nidx] = 1
                        stack.append(nidx)

        components.append((min_x, min_y, max_x, max_y, area))

    return components


def _merge_regions(regions: list[dict[str, Any]], overlap_threshold: float = 0.5) -> list[dict[str, Any]]:
    if not regions:
        return []

    pending = list(regions)
    while True:
        merged_any = False
        output: list[dict[str, Any]] = []
        skipped: set[int] = set()

        for index, region in enumerate(pending):
            if index in skipped:
                continue

            current = dict(region)
            current_rect = dict(current["thumbnail_rect"])
            current_area = current_rect["width"] * current_rect["height"]

            for candidate_index in range(index + 1, len(pending)):
                if candidate_index in skipped:
                    continue
                candidate = pending[candidate_index]
                candidate_rect = candidate["thumbnail_rect"]
                candidate_area = candidate_rect["width"] * candidate_rect["height"]

                x1 = max(current_rect["x"], candidate_rect["x"])
                y1 = max(current_rect["y"], candidate_rect["y"])
                x2 = min(current_rect["x"] + current_rect["width"], candidate_rect["x"] + candidate_rect["width"])
                y2 = min(current_rect["y"] + current_rect["height"], candidate_rect["y"] + candidate_rect["height"])

                if x2 <= x1 or y2 <= y1:
                    continue

                intersection = (x2 - x1) * (y2 - y1)
                if intersection / max(1, min(current_area, candidate_area)) <= overlap_threshold:
                    continue

                left = min(current_rect["x"], candidate_rect["x"])
                top = min(current_rect["y"], candidate_rect["y"])
                right = max(current_rect["x"] + current_rect["width"], candidate_rect["x"] + candidate_rect["width"])
                bottom = max(current_rect["y"] + current_rect["height"], candidate_rect["y"] + candidate_rect["height"])
                current_rect = {
                    "x": left,
                    "y": top,
                    "width": right - left,
                    "height": bottom - top,
                }
                current["thumbnail_rect"] = current_rect
                current["area_pixels"] = current.get("area_pixels", 0) + candidate.get("area_pixels", 0)
                current_area = current_rect["width"] * current_rect["height"]
                skipped.add(candidate_index)
                merged_any = True

            output.append(current)

        pending = output
        if not merged_any:
            return pending


def _sort_regions(regions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not regions:
        return []
    median_height = sorted(region["thumbnail_rect"]["height"] for region in regions)[len(regions) // 2]
    row_band = max(48, int(round(median_height * 0.75)))
    return sorted(
        regions,
        key=lambda region: (
            round(region["center_y"] / row_band),
            region["center_x"],
        ),
    )


def detect_tissue_regions(
    thumbnail_path: str,
    slide_width: int,
    slide_height: int,
    pad_pixels: int = 16,
) -> list[dict[str, Any]]:
    image = Image.open(thumbnail_path).convert("RGB")
    width, height = image.size
    mask_image = _build_tissue_mask(image)
    mask = bytearray(width * height)
    for idx, pixel in enumerate(mask_image.getdata()):
        if pixel <= 0:
            continue
        x = idx % width
        y = idx // width
        r, g, b = image.getpixel((x, y))
        mask[idx] = 1 if _is_tissue_pixel(r, g, b) or pixel >= 180 else 0

    min_area = max(256, int(width * height * 0.0007))
    regions: list[dict[str, Any]] = []
    scale_x = slide_width / width
    scale_y = slide_height / height

    for min_x, min_y, max_x, max_y, area in _component_bounds(mask, width, height):
        box_width = max_x - min_x + 1
        box_height = max_y - min_y + 1
        if area < min_area or box_width < 24 or box_height < 24:
            continue

        x0 = max(0, min_x - pad_pixels)
        y0 = max(0, min_y - pad_pixels)
        x1 = min(width, max_x + pad_pixels + 1)
        y1 = min(height, max_y + pad_pixels + 1)
        rect = Rect(x=x0, y=y0, width=x1 - x0, height=y1 - y0)
        regions.append(
            {
                "thumbnail_rect": {
                    "x": rect.x,
                    "y": rect.y,
                    "width": rect.width,
                    "height": rect.height,
                },
                "level0_region": {
                    "x": int(round(rect.x * scale_x)),
                    "y": int(round(rect.y * scale_y)),
                    "width": int(round(rect.width * scale_x)),
                    "height": int(round(rect.height * scale_y)),
                },
                "area_pixels": area,
                "bbox_area": rect.width * rect.height,
                "center_x": rect.x + rect.width / 2,
                "center_y": rect.y + rect.height / 2,
            }
        )

    merged = _merge_regions(regions)
    filtered: list[dict[str, Any]] = []
    if merged:
        largest_bbox_area = max(region["thumbnail_rect"]["width"] * region["thumbnail_rect"]["height"] for region in merged)
        size_floor = largest_bbox_area * 0.1
        for region in merged:
            rect = region["thumbnail_rect"]
            region["level0_region"] = {
                "x": int(round(rect["x"] * scale_x)),
                "y": int(round(rect["y"] * scale_y)),
                "width": int(round(rect["width"] * scale_x)),
                "height": int(round(rect["height"] * scale_y)),
            }
            region["center_x"] = rect["x"] + rect["width"] / 2
            region["center_y"] = rect["y"] + rect["height"] / 2
            aspect_ratio = rect["width"] / max(1, rect["height"])
            bbox_area = rect["width"] * rect["height"]
            if aspect_ratio < 0.25 or aspect_ratio > 4.0:
                continue
            if bbox_area < size_floor:
                continue
            filtered.append(region)

    ordered = _sort_regions(filtered or regions)
    for index, region in enumerate(ordered, start=1):
        region["index"] = index
        region["label"] = f"Specimen {index}"
        region.pop("center_x", None)
        region.pop("center_y", None)
        region.pop("bbox_area", None)
    return ordered
