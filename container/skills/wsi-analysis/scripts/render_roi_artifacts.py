#!/opt/pathclaw-venv/bin/python
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def load_font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except OSError:
        return ImageFont.load_default()


def render_annotated_thumbnail(thumbnail_path: str, roi_json: dict, output_path: str) -> None:
    image = Image.open(thumbnail_path).convert("RGB")
    draw = ImageDraw.Draw(image)
    font = load_font(20)
    for roi in roi_json["rois"]:
        rect = roi["thumbnail_rect"]
        x = rect["x"]
        y = rect["y"]
        w = rect["width"]
        h = rect["height"]
        label = str(roi["index"])
        draw.rectangle((x, y, x + w, y + h), outline=(255, 64, 64), width=4)
        draw.rectangle((x, y, x + 34, y + 24), fill=(255, 64, 64))
        draw.text((x + 8, y + 3), label, fill="white", font=font)
    image.save(output_path, format="WEBP", quality=85)


def render_panel(roi_json: dict, roi_images: list[str], output_path: str) -> None:
    images = [Image.open(path).convert("RGB") for path in roi_images]
    if not images:
        raise SystemExit("No ROI images provided")
    thumb_w = 320
    thumb_h = 320
    pad = 24
    caption_h = 60
    cols = min(3, len(images))
    rows = math.ceil(len(images) / cols)
    canvas = Image.new(
        "RGB",
        (
            cols * (thumb_w + pad) + pad,
            rows * (thumb_h + caption_h + pad) + pad,
        ),
        "white",
    )
    draw = ImageDraw.Draw(canvas)
    font = load_font(18)

    for idx, (image, roi) in enumerate(zip(images, roi_json["rois"], strict=False)):
        row = idx // cols
        col = idx % cols
        x0 = pad + col * (thumb_w + pad)
        y0 = pad + row * (thumb_h + caption_h + pad)
        view = image.copy()
        view.thumbnail((thumb_w, thumb_h))
        canvas.paste(view, (x0, y0))
        caption = f"{roi['index']}. {roi['label']}"
        draw.text((x0, y0 + thumb_h + 8), caption, fill="black", font=font)
        rationale = roi.get("rationale", "")[:70]
        draw.text((x0, y0 + thumb_h + 30), rationale, fill=(60, 60, 60), font=font)

    canvas.save(output_path, format="WEBP", quality=85)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--thumbnail", required=True)
    parser.add_argument("--roi-json", required=True)
    parser.add_argument("--annotated-output", required=True)
    parser.add_argument("--panel-output", required=True)
    parser.add_argument("--roi-image", action="append", default=[])
    args = parser.parse_args()

    roi_json = json.loads(Path(args.roi_json).read_text())
    render_annotated_thumbnail(args.thumbnail, roi_json, args.annotated_output)
    render_panel(roi_json, args.roi_image, args.panel_output)


if __name__ == "__main__":
    main()
