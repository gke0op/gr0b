# Changelog

All notable changes to gr0b will be documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
gr0b uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.1.0] — 2025-05-02

### Added

- `install.sh` — one-command installer for macOS and Linux
- `install.ps1` — one-command installer for Windows
- `~/.gr0b/` vault structure with Obsidian dark-theme config and colour-coded graph
- Claude Code wiring via `~/.claude/CLAUDE.md` (idempotent append)
- Gemini / Antigravity wiring via `~/.gemini/GEMINI.md` (idempotent append)
- agentmemory MCP registration in Claude Desktop `claude_desktop_config.json`
- graphify MCP registration in Claude Desktop and Antigravity configs
- launchd plist for persistent graphify watcher on macOS (`gr0b.graphify`)
- Windows Task Scheduler entry for persistent graphify watcher
- `scripts/gr0b_map.py` — auto-generates `BRAIN_MAP.md` from `graph.json`
  - Generic community classification by path segment (no hardcoded project names)
  - Noise filtering: Zig stdlib, vendored code, minified JS, bundler output
  - Duplicate-community merging (same project split across multiple IDs)
- `scripts/gr0b_obsidian_sync.py` — syncs graph communities to Obsidian notes
  - One `.md` per community with wikilinks to connected communities
  - `--limit` and `--min-nodes` flags for selective sync
- `scripts/verify.py` — post-install health check
  - Dependency presence, vault structure, agent wiring, MCP config, live server probe
- `bonus/gr0b.skill` — optional skill file for agents (explicit session-log protocol)

### Notes

- graph.json is excluded from the repo (it's 200 MB+ and personal to each machine)
- Session logs are excluded (personal content)
- No templates are shipped; the installer generates everything dynamically from `$HOME`
