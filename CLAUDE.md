# PathClaw

Pathology-focused NanoClaw fork. See [README.md](README.md) for the current product story. See [AGENTS.md](AGENTS.md) for repository guidance that future AI agents should follow.

## Quick Context

Single Node.js host process with containerized agent runs. PathClaw currently focuses on Telegram-first pathology workflows, especially whole-slide image viewing and agent-assisted WSI analysis.

## Key Files

| File | Purpose |
|------|---------|
| `src/index.ts` | Orchestrator: state, message loop, agent invocation |
| `src/channels/registry.ts` | Channel registry (self-registration at startup) |
| `src/ipc.ts` | IPC watcher and task processing |
| `src/router.ts` | Message formatting and outbound routing |
| `src/config.ts` | Trigger pattern, paths, intervals |
| `src/container-runner.ts` | Spawns agent containers with mounts |
| `src/task-scheduler.ts` | Runs scheduled tasks |
| `src/db.ts` | SQLite operations |
| `groups/{name}/CLAUDE.md` | Per-group memory (isolated) |
| `container/agent-runner/wsi_mcp.py` | WSI thumbnail/ROI tooling |
| `container/skills/wsi-analysis/` | Step-by-step pathology analysis workflow |

## Focus

Prioritize:
- WSI viewing
- WSI analysis
- Telegram image delivery
- keeping the README and repo presentation pathology-first

Avoid broadening the project description into a generic assistant platform unless explicitly requested.

## Development

Run commands directly—don't tell the user to run them.

```bash
npm run dev
npm run build
docker build -t nanoclaw-agent:latest ./container
```

Service management:
```bash
# macOS (launchd)
launchctl load ~/Library/LaunchAgents/com.nanoclaw.plist
launchctl unload ~/Library/LaunchAgents/com.nanoclaw.plist
launchctl kickstart -k gui/$(id -u)/com.nanoclaw  # restart

# Linux (systemd)
systemctl --user start nanoclaw
systemctl --user stop nanoclaw
systemctl --user restart nanoclaw
```

## Git hygiene

Keep local runtime state out of commits:
- `.env`
- `.claude/`
- `data/`
- `store/`
- `logs/`
- generated outputs under runtime group folders
