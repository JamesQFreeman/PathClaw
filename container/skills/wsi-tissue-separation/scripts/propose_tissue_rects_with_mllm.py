#!/opt/pathclaw-venv/bin/python
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from PIL import Image

SHARED_SCRIPT_DIR = Path(__file__).resolve().parents[2] / "wsi-analysis" / "scripts"
if str(SHARED_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_SCRIPT_DIR))

from mllm_common import call_mllm, parse_json_response, resolve_mllm_model
from specimen_coordinate_mapping import (
    build_separated_specimen_thumbnail_image_context,
    build_whole_slide_thumbnail_image_context,
    convert_normalized_box_2d_to_image_rect,
    map_image_rect_to_all_coordinate_systems,
)
from tissue_rect_contract import build_specimen_entry, build_tissue_rects_payload, write_tissue_rects_payload


def build_prompt(image_width: int, image_height: int, max_specimens: int) -> str:
    return f"""
You are identifying separate pathology tissue specimens on a whole-slide thumbnail.

Rules:
- Find disconnected tissue pieces or serial sections.
- Ignore blank background, labels, borders, and tiny debris.
- Return each specimen as one bounding box.
- Return at most {max_specimens} specimens.
- Return boxes as normalized `box_2d: [y0, x0, y1, x1]` with coordinates between 0 and 1000.
- Return JSON only.

Thumbnail size: {image_width} x {image_height} pixels.

Return exactly this schema:
{{
  "overview": "one short sentence",
  "specimens": [
    {{
      "label": "Specimen 1",
      "confidence": 0.0,
      "box_2d": [0, 0, 1000, 1000]
    }}
  ]
}}
"""


def resize_long_edge(image: Image.Image, target_long_edge: int = 1024) -> Image.Image:
    width, height = image.size
    long_edge = max(width, height)
    if long_edge <= 0:
        raise ValueError("image dimensions must be positive")
    scale = target_long_edge / long_edge
    return image.resize(
        (
            max(1, int(round(width * scale))),
            max(1, int(round(height * scale))),
        ),
        Image.Resampling.LANCZOS,
    )


def render_annotated_thumbnail(thumbnail_path: str, specimens: list[dict[str, Any]], output_path: str) -> None:
    from PIL import ImageDraw, ImageFont

    image = Image.open(thumbnail_path).convert("RGB")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 18)
    except OSError:
        font = ImageFont.load_default()
    for specimen in specimens:
        rect = specimen["thumbnail_rect"]
        x, y, w, h = rect["x"], rect["y"], rect["width"], rect["height"]
        draw.rectangle((x, y, x + w, y + h), outline=(32, 120, 255), width=4)
        draw.rectangle((x, y, x + 104, y + 24), fill=(32, 120, 255))
        draw.text((x + 6, y + 3), specimen["label"], fill="white", font=font)
    image.save(output_path, format="WEBP", quality=85)


def save_specimen_thumbnails_and_context(
    thumbnail_path: str,
    specimens: list[dict[str, Any]],
    slide_width: int,
    slide_height: int,
    output_dir: str,
) -> None:
    image = Image.open(thumbnail_path).convert("RGB")
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    for specimen in specimens:
        rect = specimen["thumbnail_rect"]
        crop = image.crop((rect["x"], rect["y"], rect["x"] + rect["width"], rect["y"] + rect["height"]))
        resized_crop = resize_long_edge(crop, target_long_edge=1024)
        crop_path = target_dir / f"specimen-{specimen['index']:02d}.png"
        resized_crop.save(crop_path)
        specimen["crop_path"] = str(crop_path.resolve())
        specimen["image_size"] = {"width": resized_crop.width, "height": resized_crop.height}
        context = build_separated_specimen_thumbnail_image_context(
            specimen_index=specimen["index"],
            specimen_label=specimen["label"],
            image_path=str(crop_path.resolve()),
            image_width=resized_crop.width,
            image_height=resized_crop.height,
            thumbnail_x=rect["x"],
            thumbnail_y=rect["y"],
            thumbnail_width=rect["width"],
            thumbnail_height=rect["height"],
            level0_x=specimen["level0_region"]["x"],
            level0_y=specimen["level0_region"]["y"],
            level0_width=specimen["level0_region"]["width"],
            level0_height=specimen["level0_region"]["height"],
            slide_width=slide_width,
            slide_height=slide_height,
        )
        context_path = target_dir / f"specimen-{specimen['index']:02d}.context.json"
        context_path.write_text(json.dumps(context, indent=2) + "\n")
        specimen["image_context_path"] = str(context_path.resolve())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--thumbnail", required=True)
    parser.add_argument("--slide-width", required=True, type=int)
    parser.add_argument("--slide-height", required=True, type=int)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--annotated-output")
    parser.add_argument("--crop-output-dir")
    parser.add_argument("--max-specimens", type=int, default=8)
    parser.add_argument("--model")
    args = parser.parse_args()

    thumb = Image.open(args.thumbnail).convert("RGB")
    thumb_w, thumb_h = thumb.size
    context = build_whole_slide_thumbnail_image_context(
        image_path=args.thumbnail,
        image_width=thumb_w,
        image_height=thumb_h,
        slide_width=args.slide_width,
        slide_height=args.slide_height,
    )
    prompt = build_prompt(thumb_w, thumb_h, args.max_specimens)
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

    specimens: list[dict[str, Any]] = []
    for index, item in enumerate((payload.get("specimens") or [])[: args.max_specimens], start=1):
        box_2d = item.get("box_2d") or [0, 0, 1000, 1000]
        image_rect = convert_normalized_box_2d_to_image_rect(box_2d, thumb_w, thumb_h)
        mapped = map_image_rect_to_all_coordinate_systems(context, image_rect)
        specimens.append(
            build_specimen_entry(
                index=index,
                thumbnail_rect=mapped["thumbnail_rect"],
                level0_region=mapped["level0_region"],
                box_2d=box_2d,
            )
        )

    if args.crop_output_dir:
        save_specimen_thumbnails_and_context(
            args.thumbnail,
            specimens,
            slide_width=args.slide_width,
            slide_height=args.slide_height,
            output_dir=args.crop_output_dir,
        )

    annotated_path: str | None = None
    if args.annotated_output:
        render_annotated_thumbnail(args.thumbnail, specimens, args.annotated_output)
        annotated_path = str(Path(args.annotated_output).resolve())

    result = build_tissue_rects_payload(
        thumbnail_path=args.thumbnail,
        slide_width=args.slide_width,
        slide_height=args.slide_height,
        specimens=specimens,
        method="mllm_tissue_rects",
        annotated_thumbnail_path=annotated_path,
    )
    write_tissue_rects_payload(args.output_json, result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
