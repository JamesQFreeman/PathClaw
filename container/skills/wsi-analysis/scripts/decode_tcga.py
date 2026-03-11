#!/opt/pathclaw-venv/bin/python
from __future__ import annotations

import argparse
import json
from pathlib import Path


SAMPLE_TYPE_MAP = {
    "01": "Primary Solid Tumor",
    "02": "Recurrent Solid Tumor",
    "03": "Primary Blood Derived Cancer - Peripheral Blood",
    "05": "Additional - New Primary",
    "06": "Metastatic",
    "07": "Additional Metastatic",
    "10": "Blood Derived Normal",
    "11": "Solid Tissue Normal",
}


def parse_tcga_barcode(name: str) -> dict:
    stem = Path(name).stem
    parts = stem.split("-")
    result = {
        "input": name,
        "stem": stem,
        "is_tcga_like": False,
        "project": None,
        "tss": None,
        "participant": None,
        "sample_code": None,
        "sample_type": None,
        "vial": None,
        "portion": None,
        "analyte": None,
        "plate": None,
        "slide_code": None,
        "priors": [],
        "warnings": [],
    }
    if len(parts) < 4 or parts[0] != "TCGA":
        result["warnings"].append("Filename is not a recognizable TCGA barcode")
        return result

    result["is_tcga_like"] = True
    result["project"] = parts[0]
    result["tss"] = parts[1]
    result["participant"] = parts[2]

    sample_vial = parts[3]
    if len(sample_vial) >= 3:
        result["sample_code"] = sample_vial[:2]
        result["sample_type"] = SAMPLE_TYPE_MAP.get(sample_vial[:2], "Unknown")
        result["vial"] = sample_vial[2:]
        if result["sample_type"] != "Unknown":
            result["priors"].append(
                {
                    "source": "TCGA sample code",
                    "fact": f"Sample type appears to be {result['sample_type']}",
                }
            )

    if len(parts) >= 5:
        portion_analyte = parts[4]
        result["portion"] = portion_analyte[:2] if len(portion_analyte) >= 2 else None
        result["analyte"] = portion_analyte[2:] if len(portion_analyte) >= 3 else None
    if len(parts) >= 6:
        result["plate"] = parts[5]
    if len(parts) >= 7:
        result["slide_code"] = parts[6]
        if result["slide_code"].startswith("DX"):
            result["priors"].append(
                {
                    "source": "TCGA slide code",
                    "fact": "Slide code suggests a diagnostic slide",
                }
            )

    result["warnings"].append(
        "Do not infer organ site or histologic diagnosis from the barcode alone without external metadata"
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--slide-path", required=True)
    args = parser.parse_args()
    print(json.dumps(parse_tcga_barcode(args.slide_path), indent=2))


if __name__ == "__main__":
    main()
