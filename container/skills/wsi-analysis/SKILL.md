---
name: wsi-analysis
description: Analyze pathology whole-slide images with Gemini-assisted ROI selection. Use when the user wants slide interpretation, ROI proposal from a thumbnail, TCGA filename parsing, annotated thumbnail outputs, or a structured pathology summary.
allowed-tools: Bash(/home/node/.claude/skills/wsi-analysis/scripts/*),mcp__pathclaw_wsi__*,mcp__nanoclaw__send_media_message,mcp__nanoclaw__send_message
---

# Gemini-Assisted WSI Analysis

Use this skill for pathology slide review when image understanding matters more than generic planning.

## Preconditions

- `GEMINI_API_KEY` must be present in the container environment.
- Prefer `GEMINI_MODEL` if set. Otherwise the current MLLM backend defaults to a Gemini model.
- Treat filename-derived metadata as prior context, not visual evidence.

## Workflow

Follow this exact user-visible sequence whenever analyzing a WSI.

1. Parse filename metadata:

```bash
/opt/pathclaw-venv/bin/python /home/node/.claude/skills/wsi-analysis/scripts/decode_tcga.py --slide-path "<slide-path>"
```

2. Inspect and render a thumbnail with the existing WSI MCP tools:
- `mcp__pathclaw_wsi__inspect_wsi`
- `mcp__pathclaw_wsi__render_wsi_thumbnail`

3. Immediately send the thumbnail to the user with a short text summary and background information.
- If filename/path metadata gives an educated guess, label it as background / prior.
- If not, say background is unknown.
- Use `mcp__nanoclaw__send_media_message`.

Required pattern:
- text part: concise description of the thumbnail
- image part: thumbnail
- text part: `Background information (prior, may be wrong): ...`

4. Decide whether the slide should be analyzed as one tissue image or first separated into multiple tissue specimens.

Decision policy:
- If the thumbnail clearly shows one connected tissue piece, continue with single-image analysis.
- If the thumbnail clearly shows multiple disconnected tissue pieces or serial sections, use the tissue-separation interface first.
- The segmentation source may be:
  - Claude visual decision plus the Python separator
  - MLLM tissue-rect proposal
  - Python tissue separator directly
- All segmentation paths must produce the same specimen output contract:
  - `thumbnail_rect`
  - `level0_region`
  - resized specimen thumbnail
  - `image_context_path`

5. Send a short progress message before ROI selection:
- `I am trying to find some area that worth to go high power.`

6. Ask the configured MLLM to propose ROIs from one tissue image at a time:

```bash
/opt/pathclaw-venv/bin/python /home/node/.claude/skills/wsi-analysis/scripts/propose_rois_with_mllm.py \
  --thumbnail "<thumbnail-path>" \
  --slide-width <width> \
  --slide-height <height> \
  --image-context-file "<image-unit-context.json>" \
  --metadata-file "<metadata-json>" \
  --output "<roi-proposals.json>"
```

For a normal whole-slide thumbnail, `--image-context-file` can be omitted.
For a separated specimen crop, pass the matching context JSON from the tissue-separation step.

MLLM ROI contract:
- analyze one tissue image at a time
- return ROI boxes as `box_2d: [y0, x0, y1, x1]`
- coordinates are normalized integers/floats between `0` and `1000`
- code maps those boxes back to thumbnail coordinates and then to level-0 WSI coordinates

7. Render each proposed ROI with `mcp__pathclaw_wsi__render_wsi_region` using the `level0_region` values from the JSON.

8. Build two artifacts:
- annotated thumbnail with ROI boxes
- ROI panel/contact sheet

```bash
/opt/pathclaw-venv/bin/python /home/node/.claude/skills/wsi-analysis/scripts/render_roi_artifacts.py \
  --thumbnail "<thumbnail-path>" \
  --roi-json "<roi-proposals.json>" \
  --annotated-output "<annotated-thumbnail.webp>" \
  --panel-output "<roi-panel.webp>" \
  --roi-image "<roi-1.webp>" \
  --roi-image "<roi-2.webp>"
```

9. Send the annotated thumbnail with ROI boxes to the user.

10. Send a text message that explains why each ROI was chosen.

Required pattern:
- `ROI_1: ...`
- `ROI_2: ...`
- one line per ROI using the MLLM rationale from `roi-proposals.json`

11. For each ROI, do the following in order:
- send the ROI image to the user
- ask the MLLM to analyze that ROI
- send the MLLM thought / interpretation back to the user before moving to the next ROI

The user should see every step. Do not wait until all ROIs are done before sending updates.

12. After all ROI-level messages are sent, send the annotated thumbnail and ROI panel to the MLLM for whole-case analysis:

```bash
/opt/pathclaw-venv/bin/python /home/node/.claude/skills/wsi-analysis/scripts/analyze_wsi_with_mllm.py \
  --annotated-thumbnail "<annotated-thumbnail.webp>" \
  --roi-panel "<roi-panel.webp>" \
  --metadata-file "<metadata-json>" \
  --roi-json "<roi-proposals.json>" \
  --output "<mllm-analysis.json>"
```

13. Send the final structured summary to the user.

## Messaging protocol

Always stream the work back to the user in this order:

1. Thumbnail + background information
2. `I am trying to find some area that worth to go high power.`
3. Annotated thumbnail with ROI boxes
4. ROI rationale list
5. ROI_1 image
6. ROI_1 MLLM thought
7. ROI_2 image
8. ROI_2 MLLM thought
9. Continue for remaining ROIs
10. Final integrated summary

Use `mcp__nanoclaw__send_media_message` for images and `mcp__nanoclaw__send_message` for short progress/finding text.

## Rules

- Always show the user the annotated thumbnail and ROI panel when ROI analysis is requested.
- Always stream intermediate steps; do not hold results until the end.
- Keep metadata priors separate from image findings.
- If Gemini proposes out-of-bounds ROIs, use the clamped values written by the ROI script.
- Do not claim a final diagnosis with high certainty unless the user explicitly asks for a strong impression.
- Prefer concise structured summaries with sections:
  - Metadata priors
  - Slide-level observations
  - ROI findings
  - Impression
  - Uncertainty / limitations
  - Suggested next ROIs
