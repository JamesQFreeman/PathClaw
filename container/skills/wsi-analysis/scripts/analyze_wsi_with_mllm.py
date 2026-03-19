#!/opt/pathclaw-venv/bin/python
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from mllm_common import call_mllm, parse_json_response, resolve_mllm_model


def build_prompt(metadata: dict[str, Any], roi_json: dict[str, Any]) -> str:
    return f"""
You are reviewing pathology whole-slide artifacts.

Inputs:
- An annotated thumbnail with numbered ROI boxes
- An ROI panel showing the extracted regions
- Metadata priors and TCGA-derived filename context

Rules:
- Separate metadata priors from image findings.
- Do not treat filename priors as visual evidence.
- If uncertain, say so explicitly.
- Prefer descriptive pathology language over definitive diagnosis.
- Return JSON only.

Metadata:
{json.dumps(metadata, indent=2)}

ROI proposals:
{json.dumps(roi_json, indent=2)}

Return exactly this schema:
{{
  "metadata_priors": ["..."],
  "slide_level_observations": ["..."],
  "roi_findings": [
    {{"roi": 1, "finding": "...", "confidence": 0.0}}
  ],
  "impression": "...",
  "uncertainty": ["..."],
  "suggested_next_rois": ["..."]
}}
"""


def format_markdown(payload: dict[str, Any]) -> str:
    lines = ["## Metadata Priors"]
    lines.extend(f"- {item}" for item in payload.get("metadata_priors", []))
    lines.append("")
    lines.append("## Slide-Level Observations")
    lines.extend(f"- {item}" for item in payload.get("slide_level_observations", []))
    lines.append("")
    lines.append("## ROI Findings")
    for item in payload.get("roi_findings", []):
        lines.append(f"- ROI {item.get('roi')}: {item.get('finding')} (confidence {item.get('confidence')})")
    lines.append("")
    lines.append("## Impression")
    lines.append(payload.get("impression", ""))
    lines.append("")
    lines.append("## Uncertainty / Limitations")
    lines.extend(f"- {item}" for item in payload.get("uncertainty", []))
    lines.append("")
    lines.append("## Suggested Next ROIs")
    lines.extend(f"- {item}" for item in payload.get("suggested_next_rois", []))
    return "\n".join(lines).strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--annotated-thumbnail", required=True)
    parser.add_argument("--roi-panel", required=True)
    parser.add_argument("--metadata-file", required=True)
    parser.add_argument("--roi-json", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--model")
    args = parser.parse_args()

    metadata = json.loads(Path(args.metadata_file).read_text())
    roi_json = json.loads(Path(args.roi_json).read_text())
    prompt = build_prompt(metadata, roi_json)
    text = call_mllm(
        [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_path", "path": args.annotated_thumbnail},
                    {"type": "image_path", "path": args.roi_panel},
                ],
            }
        ],
        model=resolve_mllm_model(args.model),
        temperature=0.2,
    )
    payload = parse_json_response(text)
    payload["model"] = resolve_mllm_model(args.model)
    payload["report_markdown"] = format_markdown(payload)
    Path(args.output).write_text(json.dumps(payload, indent=2) + "\n")
    print(payload["report_markdown"])


if __name__ == "__main__":
    main()
