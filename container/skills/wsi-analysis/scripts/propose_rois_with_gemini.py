#!/opt/pathclaw-venv/bin/python
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from PIL import Image

from gemini_common import call_gemini, parse_json_response, resolve_model


def clamp_box(x: int, y: int, width: int, height: int, image_width: int, image_height: int) -> tuple[int, int, int, int]:
    width = max(32, min(width, image_width))
    height = max(32, min(height, image_height))
    x = max(0, min(x, image_width - width))
    y = max(0, min(y, image_height - height))
    return x, y, width, height


def build_prompt(metadata: dict[str, Any], thumb_w: int, thumb_h: int, max_rois: int) -> str:
    return f"""
You are proposing pathology ROIs from a whole-slide thumbnail.

Rules:
- Use the image, not only metadata.
- Avoid blank background, labels, borders, and mostly whitespace.
- Select diverse tissue regions when possible.
- Prefer 4 to {max_rois} ROIs.
- Return a JSON object only.

Thumbnail size: {thumb_w} x {thumb_h} pixels.
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
      "x": 0,
      "y": 0,
      "width": 0,
      "height": 0
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
    parser.add_argument("--max-rois", type=int, default=6)
    parser.add_argument("--model")
    args = parser.parse_args()

    metadata = {}
    if args.metadata_file:
        metadata = json.loads(Path(args.metadata_file).read_text())

    thumb = Image.open(args.thumbnail)
    thumb_w, thumb_h = thumb.size
    prompt = build_prompt(metadata, thumb_w, thumb_h, args.max_rois)
    text = call_gemini(
        [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_path", "path": args.thumbnail},
                ],
            }
        ],
        model=resolve_model(args.model),
        temperature=0.1,
    )
    payload = parse_json_response(text)

    rois = []
    scale_x = args.slide_width / thumb_w
    scale_y = args.slide_height / thumb_h
    default_w = max(64, round(thumb_w * 0.18))
    default_h = max(64, round(thumb_h * 0.18))
    for idx, roi in enumerate((payload.get("rois") or [])[: args.max_rois], start=1):
        raw_x = int(round(float(roi.get("x", 0))))
        raw_y = int(round(float(roi.get("y", 0))))
        raw_w = int(round(float(roi.get("width", default_w))))
        raw_h = int(round(float(roi.get("height", default_h))))
        x, y, width, height = clamp_box(raw_x, raw_y, raw_w, raw_h, thumb_w, thumb_h)
        rois.append(
            {
                "index": idx,
                "label": roi.get("label") or f"ROI {idx}",
                "rationale": roi.get("rationale") or "",
                "confidence": float(roi.get("confidence", 0.0) or 0.0),
                "thumbnail_rect": {
                    "x": x,
                    "y": y,
                    "width": width,
                    "height": height,
                },
                "level0_region": {
                    "x": int(round(x * scale_x)),
                    "y": int(round(y * scale_y)),
                    "width": int(round(width * scale_x)),
                    "height": int(round(height * scale_y)),
                },
            }
        )

    result = {
        "model": resolve_model(args.model),
        "thumbnail_path": str(Path(args.thumbnail).resolve()),
        "thumbnail_size": {"width": thumb_w, "height": thumb_h},
        "slide_size": {"width": args.slide_width, "height": args.slide_height},
        "overview": payload.get("overview") or "",
        "rois": rois,
    }
    Path(args.output).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
