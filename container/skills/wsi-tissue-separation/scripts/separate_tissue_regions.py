#!/opt/pathclaw-venv/bin/python
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from PIL import Image, ImageDraw, ImageFont

SHARED_SCRIPT_DIR = Path(__file__).resolve().parents[2] / "wsi-analysis" / "scripts"
if str(SHARED_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_SCRIPT_DIR))

from specimen_coordinate_mapping import build_separated_specimen_thumbnail_image_context
from tissue_rect_contract import build_specimen_entry, build_tissue_rects_payload, write_tissue_rects_payload
from tissue_regions import detect_tissue_regions


def load_font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except OSError:
        return ImageFont.load_default()


def resize_long_edge(image: Image.Image, target_long_edge: int = 1024) -> Image.Image:
    width, height = image.size
    long_edge = max(width, height)
    if long_edge <= 0:
        raise ValueError("image dimensions must be positive")
    if long_edge == target_long_edge:
        return image
    scale = target_long_edge / long_edge
    new_size = (
        max(1, int(round(width * scale))),
        max(1, int(round(height * scale))),
    )
    return image.resize(new_size, Image.Resampling.LANCZOS)


def render_annotated_thumbnail(thumbnail_path: str, specimens: list[dict], output_path: str) -> None:
    image = Image.open(thumbnail_path).convert("RGB")
    draw = ImageDraw.Draw(image)
    font = load_font(18)
    for specimen in specimens:
        rect = specimen["thumbnail_rect"]
        x = rect["x"]
        y = rect["y"]
        w = rect["width"]
        h = rect["height"]
        draw.rectangle((x, y, x + w, y + h), outline=(32, 120, 255), width=4)
        draw.rectangle((x, y, x + 104, y + 24), fill=(32, 120, 255))
        draw.text((x + 6, y + 3), specimen["label"], fill="white", font=font)
    image.save(output_path, format="WEBP", quality=85)


def save_specimen_crops(thumbnail_path: str, specimens: list[dict], output_dir: str) -> list[str]:
    image = Image.open(thumbnail_path).convert("RGB")
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    for specimen in specimens:
        rect = specimen["thumbnail_rect"]
        crop = image.crop((rect["x"], rect["y"], rect["x"] + rect["width"], rect["y"] + rect["height"]))
        resized_crop = resize_long_edge(crop, target_long_edge=1024)
        path = target_dir / f"specimen-{specimen['index']:02d}.png"
        resized_crop.save(path)
        specimen["crop_path"] = str(path.resolve())
        specimen["image_size"] = {
            "width": resized_crop.width,
            "height": resized_crop.height,
        }
        paths.append(specimen["crop_path"])
    return paths


def write_specimen_context_files(specimens: list[dict], output_dir: str) -> list[str]:
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    for specimen in specimens:
        rect = specimen["thumbnail_rect"]
        level0 = specimen["level0_region"]
        slide_size = specimen.get("slide_size") or {"width": 0, "height": 0}
        image_size = specimen.get("image_size") or {"width": rect["width"], "height": rect["height"]}
        context = build_separated_specimen_thumbnail_image_context(
            specimen_index=specimen["index"],
            specimen_label=specimen["label"],
            image_path=specimen.get("crop_path") or "",
            image_width=image_size["width"],
            image_height=image_size["height"],
            thumbnail_x=rect["x"],
            thumbnail_y=rect["y"],
            thumbnail_width=rect["width"],
            thumbnail_height=rect["height"],
            level0_x=level0["x"],
            level0_y=level0["y"],
            level0_width=level0["width"],
            level0_height=level0["height"],
            slide_width=slide_size["width"],
            slide_height=slide_size["height"],
        )
        path = target_dir / f"specimen-{specimen['index']:02d}.context.json"
        path.write_text(json.dumps(context, indent=2) + "\n")
        specimen["image_context_path"] = str(path.resolve())
        paths.append(specimen["image_context_path"])
    return paths


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--thumbnail", required=True)
    parser.add_argument("--slide-width", required=True, type=int)
    parser.add_argument("--slide-height", required=True, type=int)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--annotated-output")
    parser.add_argument("--crop-output-dir")
    args = parser.parse_args()

    specimens = detect_tissue_regions(args.thumbnail, args.slide_width, args.slide_height)
    for specimen in specimens:
        specimen["slide_size"] = {"width": args.slide_width, "height": args.slide_height}

    if args.crop_output_dir:
        save_specimen_crops(args.thumbnail, specimens, args.crop_output_dir)
        write_specimen_context_files(specimens, args.crop_output_dir)
    annotated_path: str | None = None
    if args.annotated_output:
        render_annotated_thumbnail(args.thumbnail, specimens, args.annotated_output)
        annotated_path = str(Path(args.annotated_output).resolve())

    result_specimens = []
    for specimen in specimens:
        result_specimens.append(
            build_specimen_entry(
                index=specimen["index"],
                thumbnail_rect=specimen["thumbnail_rect"],
                level0_region=specimen["level0_region"],
                area_pixels=specimen.get("area_pixels"),
                crop_path=specimen.get("crop_path"),
                image_size=specimen.get("image_size"),
                image_context_path=specimen.get("image_context_path"),
            )
        )
        specimen.pop("slide_size", None)

    result = build_tissue_rects_payload(
        thumbnail_path=args.thumbnail,
        slide_width=args.slide_width,
        slide_height=args.slide_height,
        specimens=result_specimens,
        method="python_tissue_separator",
        annotated_thumbnail_path=annotated_path,
    )
    write_tissue_rects_payload(args.output_json, result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
