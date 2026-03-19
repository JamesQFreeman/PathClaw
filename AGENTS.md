# PathClaw Agent Guide

This repo is PathClaw, a pathology-focused fork of NanoClaw.

## Product focus

Keep the project narrow.

Current priorities:
- WSI view skill
- agent-assisted WSI analysis skill
- Telegram-first image delivery

Do not expand the README or product positioning back into a full NanoClaw feature catalog unless explicitly requested.

## Core architecture

- Host orchestrator: `src/index.ts`
- Container launch + env injection: `src/container-runner.ts`
- Telegram channel: `src/channels/telegram.ts`
- WSI MCP server: `container/agent-runner/wsi_mcp.py`
- WSI analysis skill: `container/skills/wsi-analysis/`

Claude handles orchestration and messaging. The analysis workflow handles ROI proposal and slide interpretation.

## README guidance

The README should stay product-facing and pathology-first.

Prefer:
- what PathClaw does today
- WSI viewing workflow
- WSI analysis workflow
- demo assets
- limitations and disclaimer

Avoid:
- long NanoClaw philosophy sections
- generic multi-channel assistant marketing
- broad claims not shipped in PathClaw v0.0.1

## Git and publishing guidance

Repo setup:
- `origin` is the PathClaw GitHub fork
- `upstream` points to NanoClaw

Release flow:
- do release work on a branch first
- merge or fast-forward into `main`
- tag releases (for example `v0.0.1`)

## Gitignore and local state

Do not commit local runtime state or secrets.

Keep these out of git:
- `.env`
- `.claude/`
- `data/`
- `store/`
- `logs/`
- `__pycache__/`
- generated WSI outputs in group workspaces

`groups/global/CLAUDE.md` and `groups/main/CLAUDE.md` are part of the product and may be committed when intentional.

`groups/telegram_main/` and other runtime group folders should generally remain local state.

## Media assets

Use repo-friendly assets in the README.

Current convention:
- keep large source recordings local when possible
- commit optimized README-safe assets such as `assets/pathclaw-telegram-demo.gif`
- prefer clean names like `pathclaw-*.gif`, `pathclaw-*.png`

## Pathology workflow guardrails

- Treat filename-derived metadata as prior context, not image evidence
- Keep step-by-step ROI streaming behavior in the analysis skill
- Keep medical claims conservative
- Preserve the disclaimer that PathClaw is not a diagnostic device
