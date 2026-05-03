# gr0b

**A persistent brain for your AI agents — shared, graph-backed, hidden.**

Your AI agents forget everything when the session ends. gr0b fixes that. It wires Claude Code, Gemini CLI, and Codex to a shared memory layer — a hidden vault at `~/.gr0b` — backed by a semantic knowledge graph of your actual codebase and a cross-session memory store that survives restarts.

One install. Every agent reads the same brain.

---

## What it does

- **Shared memory** — agentmemory stores lessons, decisions, and context across all your agents. BM25 + vector + graph retrieval. 96% fewer tokens spent re-explaining things.
- **Knowledge graph** — graphify builds a semantic graph of your codebase (AST-level, no LLM required for indexing). 70× more semantic reach than directory crawling. Auto-rebuilds on file changes.
- **Session logs** — agents write structured logs at the end of each session: what was worked on, decisions made, files changed, open threads. Searchable, linkable, permanent.
- **Obsidian vault** — `~/.gr0b` is a valid Obsidian vault. Open it to navigate your brain visually: colour-coded graph, community clusters, wikilinks between sessions.
- **Human-readable brain map** — `BRAIN_MAP.md` names and sizes every code community in your graph. See what you're actually working with.

---

## Install

**macOS / Linux**

```bash
git clone https://github.com/gke0op/gr0b && cd gr0b && bash install.sh
```

**Windows** (PowerShell, run as Administrator or with execution policy set)

```powershell
git clone https://github.com/gke0op/gr0b && cd gr0b
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\install.ps1
```

### Prerequisites

| Tool | Install |
|------|---------|
| [uv](https://astral.sh/uv) | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| [Node.js](https://nodejs.org) ≥ 18 | `brew install node` / `winget install OpenJS.NodeJS` |
| [git](https://git-scm.com) | `brew install git` / `winget install Git.Git` |

The installer handles everything else: graphifyy, agentmemory, iii-engine, Obsidian config, MCP server registration, and the file-watcher daemon.

---

## First run

```bash
# 1. Start agentmemory (keep running in a terminal)
npx @agentmemory/agentmemory

# 2. Import your Claude conversation history
agentmemory import-jsonl

# 3. Build your knowledge graph (point at your projects folder)
cd ~/Desktop && graphify update .

# 4. Generate your brain map
python3 ~/.gr0b/scripts/gr0b_map.py

# 5. Verify everything is wired
python3 ~/.gr0b/scripts/verify.py

# 6. Open your Obsidian vault (macOS: Cmd+Shift+. to show hidden folders)
#    File → Open folder as vault → ~/.gr0b
```

---

## How it works

```
~/.gr0b/
├── index.md                   ← agents read this on session start
├── BRAIN_MAP.md               ← human-readable codebase map
├── session-logs/
│   ├── claude/                ← Claude Code writes here
│   ├── gemini/                ← Gemini / Antigravity writes here
│   └── codex/                 ← Codex writes here
├── knowledge-graphs/          ← Obsidian notes generated from graphify
├── decisions/                 ← architecture & design records
├── agents/                    ← per-agent config scratch space
│   ├── claude/
│   ├── gemini/
│   ├── codex/
│   └── cursor/
├── .obsidian/                 ← Obsidian config (dark theme, colour graph)
└── scripts/
    ├── gr0b_map.py            ← regenerate BRAIN_MAP.md
    ├── gr0b_obsidian_sync.py  ← sync graph to Obsidian notes
    └── verify.py              ← health check
```

**MCP servers registered in Claude Desktop:**

| Server | Purpose |
|--------|---------|
| `agentmemory` | Cross-agent semantic memory |
| `graphify` | Live codebase knowledge graph queries |

**Agent instructions appended to:**
- `~/.claude/CLAUDE.md` — Claude Code reads this as its global system prompt
- `~/.gemini/GEMINI.md` — Gemini CLI reads this on startup

The append is idempotent — re-running the installer won't duplicate entries.

---

## The session protocol

Agents instructed by gr0b follow this loop automatically:

**On session start:**
1. Read `~/.gr0b/index.md`
2. Scan recent session logs for relevant context
3. Run `graphify query "<task>"` to ground themselves in the codebase

**On session end:**
Write a log to `~/.gr0b/session-logs/<agent>/YYYY-MM-DD_HH-MM.md`:

```markdown
# Session — 2025-05-01 14:32

## What was worked on
## Key decisions made
## Files changed
## Open threads / next steps
```

---

## Regenerating the brain map

The brain map classifies your codebase communities automatically — no hardcoded project names, no configuration. It reads your graph, derives names from dominant path segments, filters infrastructure noise (stdlib, vendored code, minified JS), and merges duplicate clusters.

```bash
python3 ~/.gr0b/scripts/gr0b_map.py
```

---

## Syncing to Obsidian

Generate one Obsidian note per codebase community, with wikilinks between connected communities:

```bash
python3 ~/.gr0b/scripts/gr0b_obsidian_sync.py

# Options:
#   --limit N      only write first N communities
#   --min-nodes N  skip communities smaller than N (default: 5)
```

---

## Optional: gr0b skill file

The `bonus/gr0b.skill` file makes the session protocol explicit for agents that support skill files (Claude Code, Gemini). Copy it to your agent's skills directory:

```bash
# Claude Code
cp bonus/gr0b.skill ~/.claude/skills/

# Gemini
cp bonus/gr0b.skill ~/.gemini/skills/
```

The skill adds `on_session_start` and `on_session_end` hooks with clear instructions. It's optional — gr0b works without it, through the directives in CLAUDE.md / GEMINI.md.

---

## Limitations

- **graph.json is large.** For a Desktop folder with 15+ active projects, expect 150–250 MB. Keep it on your local drive, not a slow external. It stays out of git (`.gitignore`d).
- **agentmemory needs to be running.** It's not a daemon — start it in a terminal before your sessions. Automating this as a startup item is on the roadmap.
- **graphify watch requires file events.** On network drives or some Docker mounts, inotify/FSEvents may not fire reliably. Use `graphify update .` for a one-shot rebuild instead.
- **Windows support is newer.** Task Scheduler watcher is less battle-tested than the macOS launchd path. File an issue if you hit problems.

---

## Verification

```bash
python3 ~/.gr0b/scripts/verify.py
```

Checks: dependency presence, vault structure, agent wiring, MCP config, live agentmemory server, graph existence, brain map freshness, and (macOS) launchd watcher status.

---

## Contributing

Issues and PRs welcome. Keep it minimal — gr0b's value is in being invisible infrastructure, not a feature-laden framework.

---

## License

MIT — see [LICENSE](LICENSE).
