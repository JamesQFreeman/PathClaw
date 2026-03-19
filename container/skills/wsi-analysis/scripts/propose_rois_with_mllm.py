#!/opt/pathclaw-venv/bin/python
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from PIL import Image

from mllm_common import call_mllm, parse_json_response, resolve_mllm_model
from specimen_coordinate_mapping import (
    convert_normalized_box_2d_to_image_rect,
    load_image_analysis_context,
    map_image_rect_to_all_coordinate_systems,
)


def clamp_box(x: int, y: int, width: int, height: int, image_width: int, image_height: int) -> tuple[int, int, int, int]:
    width = max(32, min(width, image_width))
    height = max(32, min(height, image_height))
    x = max(0, min(x, image_width - width))
    y = max(0, min(y, image_height - height))
    return x, y, width, height


def build_prompt(metadata: dict[str, Any], image_w: int, image_h: int, max_rois: int, image_kind: str) -> str:
    return f"""
You are proposing pathology ROIs from a pathology image unit.

Rules:
- Use the image, not only metadata.
- Avoid blank background, labels, borders, and mostly whitespace.
- Select diverse tissue regions when possible.
- Prefer 4 to {max_rois} ROIs.
- Return ROI boxes as normalized coordinates between 0 and 1000.
- Each ROI must include `box_2d` in the form [y0, x0, y1, x1].
- Return a JSON object only.

Image unit kind: {image_kind}
Image size: {image_w} x {image_h} pixels.
Metadata priors:
{json.dumps(metadata, indent=2)}

Return exactly this schema:
{{
  "overview": "one short sentence",
  "rois": [
    {{
      "label": "ROI 1",
      "rationale": "why this region matters",
      "confidence": 0.0,
      "box_2d": [0, 0, 1000, 1000]
    }}
  ]
}}
"""
def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--thumbnail", required=True)
    parser.add_argument("--slide-width", required=True, type=int)
    parser.add_argument("--slide-height", required=True, type=int)
    parser.add_argument("--metadata-file")
    parser.add_argument("--output", required=True)
    parser.add_argument("--image-context-file")
    parser.add_argument("--max-rois", type=int, default=6)
    parser.add_argument("--model")
    args = parser.parse_args()

    metadata = {}
    if args.metadata_file:
        metadata = json.loads(Path(args.metadata_file).read_text())

    thumb = Image.open(args.thumbnail)
    thumb_w, thumb_h = thumb.size
    context = load_image_analysis_context(
        args.image_context_file,
        args.thumbnail,
        thumb_w,
        thumb_h,
        args.slide_width,
        args.slide_height,
    )
    prompt = build_prompt(metadata, thumb_w, thumb_h, args.max_rois, context.get("kind", "unknown"))
    text = call_mllm(
        [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_path", "path": args.thumbnail},
                ],
            }
        ],
        model=resolve_mllm_model(args.model),
        temperature=0.1,
    )
    payload = parse_json_response(text)
    rois = []
    default_w = max(64, round(thumb_w * 0.18))
    default_h = max(64, round(thumb_h * 0.18))
    for idx, roi in enumerate((payload.get("rois") or [])[: args.max_rois], start=1):
        if roi.get("box_2d"):
            image_rect = convert_normalized_box_2d_to_image_rect(roi["box_2d"], thumb_w, thumb_h)
            raw_x = image_rect["x"]
            raw_y = image_rect["y"]
            raw_w = image_rect["width"]
            raw_h = image_rect["height"]
        else:
            raw_x = int(round(float(roi.get("x", 0))))
            raw_y = int(round(float(roi.get("y", 0))))
            raw_w = int(round(float(roi.get("width", default_w))))
            raw_h = int(round(float(roi.get("height", default_h))))
        x, y, width, height = clamp_box(raw_x, raw_y, raw_w, raw_h, thumb_w, thumb_h)
        mapped = map_image_rect_to_all_coordinate_systems(
            context,
            {
                "x": x,
                "y": y,
                "width": width,
                "height": height,
            },
        )
        rois.append(
            {
                "index": idx,
                "label": roi.get("label") or f"ROI {idx}",
                "rationale": roi.get("rationale") or "",
                "confidence": float(roi.get("confidence", 0.0) or 0.0),
                "box_2d": roi.get("box_2d"),
                "image_rect": mapped["image_rect"],
                "thumbnail_rect": mapped["thumbnail_rect"],
                "level0_region": mapped["level0_region"],
            }
        )

    result = {
        "model": resolve_mllm_model(args.model),
        "thumbnail_path": str(Path(args.thumbnail).resolve()),
        "thumbnail_size": {"width": thumb_w, "height": thumb_h},
        "image_unit_context": context,
        "slide_size": {"width": args.slide_width, "height": args.slide_height},
        "overview": payload.get("overview") or "",
        "rois": rois,
    }
    Path(args.output).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
