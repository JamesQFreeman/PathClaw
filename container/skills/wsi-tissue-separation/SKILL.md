---
name: wsi-tissue-separation
description: Separate multiple tissue pieces on a pathology slide thumbnail into specimen regions and specimen crops. Use when a WSI thumbnail shows multiple disconnected biopsy pieces or serial sections and downstream analysis should be done one specimen at a time.
allowed-tools: Bash(/home/node/.claude/skills/wsi-tissue-separation/scripts/*),mcp__pathclaw_wsi__*,mcp__nanoclaw__send_media_message,mcp__nanoclaw__send_message
---

# WSI Tissue Separation

Use this skill as preprocessing for multi-specimen slides.

This skill supports multiple segmentation sources that must all emit the same specimen interface:
- Python separator
- MLLM tissue-rect proposer
- Claude decision/orchestration around either one

## Workflow

1. Inspect the slide and render a thumbnail:
- `mcp__pathclaw_wsi__inspect_wsi`
- `mcp__pathclaw_wsi__render_wsi_thumbnail`

2. Choose a segmentation source.

Option A: deterministic Python separator

```bash
/opt/pathclaw-venv/bin/python /home/node/.claude/skills/wsi-tissue-separation/scripts/separate_tissue_regions.py \
  --thumbnail "<thumbnail-path>" \
  --slide-width <width> \
  --slide-height <height> \
  --output-json "<specimens.json>" \
  --annotated-output "<specimens-annotated.webp>" \
  --crop-output-dir "<specimen-crops-dir>"
```

Option B: MLLM tissue-rect proposal

```bash
/opt/pathclaw-venv/bin/python /home/node/.claude/skills/wsi-tissue-separation/scripts/propose_tissue_rects_with_mllm.py \
  --thumbnail "<thumbnail-path>" \
  --slide-width <width> \
  --slide-height <height> \
  --output-json "<specimens.json>" \
  --annotated-output "<specimens-annotated.webp>" \
  --crop-output-dir "<specimen-crops-dir>"
```

3. Send the annotated thumbnail to the user so they can see the detected specimen boxes.

4. If the user asked for analysis, pass each separated specimen crop or box into a downstream analysis workflow as its own image unit.
   Use the generated specimen crop plus its matching `*.context.json` file so ROI coordinates can be mapped back to the full thumbnail and original WSI.

Output contract:
- `method`
- specimen boxes in full-slide thumbnail coordinates
- matching level-0 WSI coordinates derived by code
- specimen thumbnails created by cropping the full-slide thumbnail and resizing to long edge `1024`
- optional `box_2d` when the segmentation source is MLLM-based

## Rules

- Use this skill only when the thumbnail shows multiple disconnected tissue pieces or when a user explicitly asks to separate specimens.
- Treat the output as a preprocessing artifact, not a diagnostic result.
- Preserve specimen order visually from top-left to bottom-right so later analysis can refer to `Specimen 1`, `Specimen 2`, and so on.
