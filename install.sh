#!/bin/bash
# gr0b — install.sh
# A persistent brain for your AI agents — shared, graph-backed, hidden.
# https://github.com/gke0op/gr0b
#
# Usage:
#   git clone https://github.com/gke0op/gr0b && cd gr0b && bash install.sh

set -euo pipefail

VAULT="$HOME/.gr0b"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GR0B_VERSION="0.1.0"

# ── Colour output ─────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

ok()   { echo -e "${GREEN}  ✓${RESET}  $1"; }
warn() { echo -e "${YELLOW}  ⚠${RESET}  $1"; }
fail() { echo -e "${RED}  ✗${RESET}  $1"; }
step() { echo -e "\n${CYAN}${BOLD}▸ $1${RESET}"; }

echo -e "\n${BOLD}gr0b v${GR0B_VERSION}${RESET} — persistent brain for your AI agents"
echo    "────────────────────────────────────────────"

# ── OS check ─────────────────────────────────────────────────────────────────
OS="$(uname -s)"
if [[ "$OS" != "Darwin" && "$OS" != "Linux" ]]; then
    fail "Unsupported OS: $OS. Use install.ps1 on Windows."
    exit 1
fi

# ── Dependency check ──────────────────────────────────────────────────────────
step "Checking dependencies"

need() {
    local cmd=$1; local pkg=${2:-$1}; local install_hint=${3:-""}
    if command -v "$cmd" &>/dev/null; then
        ok "$cmd"
    else
        fail "$cmd not found"
        if [[ -n "$install_hint" ]]; then
            echo "      → $install_hint"
        fi
        MISSING_DEPS=1
    fi
}

MISSING_DEPS=0
need "uv"   "uv"   "curl -LsSf https://astral.sh/uv/install.sh | sh"
need "node" "node" "brew install node  OR  https://nodejs.org"
need "git"  "git"  "brew install git"

if [[ $MISSING_DEPS -eq 1 ]]; then
    echo ""
    fail "Install missing dependencies then re-run install.sh"
    exit 1
fi

# ── Install tools ─────────────────────────────────────────────────────────────
step "Installing graphifyy"
if uv tool install --force graphifyy --with watchdog --quiet 2>/dev/null; then
    ok "graphifyy installed"
else
    warn "graphifyy install had warnings — continuing"
fi

step "Installing agentmemory"
if npm install -g @agentmemory/agentmemory @agentmemory/mcp --quiet 2>/dev/null; then
    ok "agentmemory installed"
else
    warn "agentmemory install had warnings — continuing"
fi

# Check for iii-engine (agentmemory dependency)
if ! command -v iii &>/dev/null && [[ ! -f "$HOME/.local/bin/iii" ]]; then
    step "Installing iii-engine (agentmemory runtime)"
    curl -fsSL https://install.iii.dev/iii/main/install.sh | sh || warn "iii install failed — agentmemory may have limited functionality"
fi

# Ensure ~/.local/bin is in PATH for this session
export PATH="$HOME/.local/bin:$PATH"

# ── Create vault structure ────────────────────────────────────────────────────
step "Creating vault at ~/.gr0b"

mkdir -p "$VAULT"/{.obsidian,knowledge-graphs,session-logs/{claude,gemini,codex},decisions,agents/{claude,gemini,codex,cursor},scripts}

# Mark as hidden on macOS
if [[ "$OS" == "Darwin" ]]; then
    chflags hidden "$VAULT" 2>/dev/null || true
fi

ok "Vault directory structure created"

# ── Obsidian config ───────────────────────────────────────────────────────────
step "Configuring Obsidian"

cat > "$VAULT/.obsidian/app.json" << 'EOF'
{
  "promptDelete": false,
  "theme": "obsidian",
  "translucency": false,
  "defaultViewMode": "preview",
  "livePreview": true
}
EOF

cat > "$VAULT/.obsidian/appearance.json" << 'EOF'
{
  "theme": "obsidian",
  "cssTheme": "",
  "interfaceFontFamily": "",
  "textFontFamily": "",
  "monospaceFontFamily": ""
}
EOF

cat > "$VAULT/.obsidian/graph.json" << 'EOF'
{
  "collapse-filter": false,
  "search": "",
  "showTags": false,
  "showAttachments": false,
  "hideUnresolved": false,
  "showOrphans": true,
  "collapse-color-groups": false,
  "colorGroups": [
    { "query": "path:session-logs/claude", "color": { "a": 1, "rgb": 8404992 } },
    { "query": "path:session-logs/gemini", "color": { "a": 1, "rgb": 2263842 } },
    { "query": "path:knowledge-graphs",    "color": { "a": 1, "rgb": 2263842 } },
    { "query": "path:decisions",           "color": { "a": 1, "rgb": 16737792 } }
  ],
  "collapse-display": false,
  "showArrow": true,
  "textFadeMultiplier": 0,
  "nodeSizeMultiplier": 1,
  "lineSizeMultiplier": 1,
  "collapse-forces": false,
  "centerStrength": 0.518713248970312,
  "repelStrength": 10,
  "linkStrength": 1,
  "linkDistance": 250,
  "scale": 1,
  "close": false
}
EOF

ok "Obsidian configured (dark theme, colour-coded graph)"

# ── index.md ──────────────────────────────────────────────────────────────────
cat > "$VAULT/index.md" << EOF
# .gr0b — Persistent Brain

> Installed $(date +%Y-%m-%d) · gr0b v${GR0B_VERSION}

## Agents

| Agent | Config | Session logs |
|-------|--------|--------------|
| Claude Code | \`~/.claude/CLAUDE.md\` | \`session-logs/claude/\` |
| Antigravity | \`~/.gemini/GEMINI.md\` | \`session-logs/gemini/\` |
| Codex | \`~/.codex/AGENTS.md\` | \`session-logs/codex/\` |

## Memory layers

- **Knowledge graph** — \`knowledge-graphs/\` (graphify, auto-updated)
- **Session logs** — \`session-logs/\` (written by agents each session)
- **Decisions** — \`decisions/\` (architecture & design records)
- **Shared memory** — agentmemory MCP (cross-agent, semantic search)

## Brain map

See \`BRAIN_MAP.md\` for a human-readable map of your codebase communities.
Regenerate: \`python3 ~/.gr0b/scripts/gr0b_map.py\`
EOF

ok "index.md created"

# ── Wire CLAUDE.md ────────────────────────────────────────────────────────────
step "Wiring Claude Code"

CLAUDE_MD="$HOME/.claude/CLAUDE.md"
mkdir -p "$HOME/.claude"
[[ ! -f "$CLAUDE_MD" ]] && touch "$CLAUDE_MD"

if grep -q "\.gr0b" "$CLAUDE_MD" 2>/dev/null; then
    ok "CLAUDE.md already has .gr0b directive"
else
    cat >> "$CLAUDE_MD" << 'EOF'

---

## .gr0b — Persistent Brain

Your memory lives at `~/.gr0b/`. Every session:

**On start:**
1. Read `~/.gr0b/index.md` — map of all projects and agent status
2. Scan `~/.gr0b/session-logs/claude/` for recent relevant sessions
3. For codebase questions, use `graphify query "<question>"` from the project root

**On end — write a session log:**
Path: `~/.gr0b/session-logs/claude/YYYY-MM-DD_HH-MM.md`
```
# Session — YYYY-MM-DD HH:MM
## What was worked on
## Key decisions made
## Files changed
## Open threads / next steps
```

**MCP tools:**
- `agentmemory` — cross-agent shared memory
- `graphify` — codebase knowledge graph
EOF
    ok "CLAUDE.md wired with .gr0b directive"
fi

# Run graphify claude install if available
if command -v graphify &>/dev/null; then
    graphify claude install --quiet 2>/dev/null && ok "graphify skill installed for Claude" || true
fi

# ── Wire GEMINI.md ────────────────────────────────────────────────────────────
step "Wiring Antigravity (Gemini)"

GEMINI_MD="$HOME/.gemini/GEMINI.md"
mkdir -p "$HOME/.gemini"
[[ ! -f "$GEMINI_MD" ]] && touch "$GEMINI_MD"

if grep -q "\.gr0b" "$GEMINI_MD" 2>/dev/null; then
    ok "GEMINI.md already has .gr0b directive"
else
    cat >> "$GEMINI_MD" << 'EOF'

---

## .gr0b — Persistent Brain

Your memory lives at `~/.gr0b/`. Every session:

**On start:**
1. Read `~/.gr0b/index.md` — map of all projects and agent status
2. Scan `~/.gr0b/session-logs/gemini/` for recent relevant sessions
3. For codebase questions, use `graphify query "<question>"` from the project root

**On end — write a session log:**
Path: `~/.gr0b/session-logs/gemini/YYYY-MM-DD_HH-MM.md`
```
# Session — YYYY-MM-DD HH:MM
## What was worked on
## Key decisions made
## Files changed
## Open threads / next steps
```

**MCP tools:**
- `agentmemory` — cross-agent shared memory
- `graphify` — codebase knowledge graph
EOF
    ok "GEMINI.md wired with .gr0b directive"
fi

# Run graphify antigravity install if available
if command -v graphify &>/dev/null; then
    graphify antigravity install --quiet 2>/dev/null && ok "graphify skill installed for Antigravity" || true
fi

# ── MCP servers — Claude Desktop ──────────────────────────────────────────────
step "Registering MCP servers"

DESKTOP_CFG="$HOME/Library/Application Support/Claude/claude_desktop_config.json"
if [[ -f "$DESKTOP_CFG" ]]; then
    python3 - "$DESKTOP_CFG" << 'PYEOF'
import json, sys
from pathlib import Path
path = sys.argv[1]
raw = Path(path).read_text().strip()
cfg = json.loads(raw) if raw else {}
servers = cfg.setdefault("mcpServers", {})
servers.setdefault("agentmemory", {"command": "agentmemory", "args": ["mcp"]})
servers.setdefault("graphify", {
    "command": "uv",
    "args": ["run", "--with", "graphifyy", "--with", "mcp",
             "-m", "graphify.serve",
             f"{__import__('pathlib').Path.home()}/Desktop/graphify-out/graph.json"]
})
with open(path, "w") as f:
    json.dump(cfg, f, indent=2)
PYEOF
    ok "Claude Desktop MCP config updated"
else
    warn "Claude Desktop config not found — skipping (install Claude Desktop first)"
fi

# Antigravity MCP
ANTIGRAV_DIR="$HOME/.gemini/antigravity"
if [[ -d "$ANTIGRAV_DIR" ]]; then
    python3 - "$ANTIGRAV_DIR/mcp_config.json" << 'PYEOF'
import json, sys
from pathlib import Path
path = Path(sys.argv[1])
path.parent.mkdir(parents=True, exist_ok=True)
cfg = json.loads(path.read_text()) if path.exists() and path.stat().st_size > 0 else {}
cfg.setdefault("agentmemory", {"command": "agentmemory", "args": ["mcp"]})
cfg.setdefault("graphify", {
    "command": "uv",
    "args": ["run", "--with", "graphifyy", "--with", "mcp",
             "-m", "graphify.serve",
             str(Path.home() / "Desktop/graphify-out/graph.json")]
})
path.write_text(json.dumps(cfg, indent=2))
PYEOF
    ok "Antigravity MCP config updated"
fi

# ── Graphify launchd watcher (macOS) ─────────────────────────────────────────
if [[ "$OS" == "Darwin" ]]; then
    step "Setting up graphify watcher (launchd)"

    GRAPHIFY_BIN="$(command -v graphify || echo "$HOME/.local/bin/graphify")"
    PLIST="$HOME/Library/LaunchAgents/gr0b.graphify.plist"
    mkdir -p "$HOME/Library/LaunchAgents"

    cat > "$PLIST" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>gr0b.graphify</string>
  <key>ProgramArguments</key>
  <array>
    <string>${GRAPHIFY_BIN}</string>
    <string>watch</string>
    <string>${HOME}/Desktop</string>
  </array>
  <key>WorkingDirectory</key><string>${HOME}/Desktop</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>${VAULT}/session-logs/graphify.log</string>
  <key>StandardErrorPath</key><string>${VAULT}/session-logs/graphify-error.log</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key><string>/opt/homebrew/bin:${HOME}/.local/bin:/usr/local/bin:/usr/bin:/bin</string>
    <key>HOME</key><string>${HOME}</string>
  </dict>
</dict>
</plist>
EOF

    launchctl unload "$PLIST" 2>/dev/null || true
    launchctl load "$PLIST" && ok "graphify watcher loaded (launchd)" || warn "launchctl load failed — run manually: graphify watch ~/Desktop"
fi

# ── Copy scripts into vault ───────────────────────────────────────────────────
step "Installing gr0b scripts"

cp "$SCRIPT_DIR/scripts/gr0b_map.py"            "$VAULT/scripts/"
cp "$SCRIPT_DIR/scripts/gr0b_obsidian_sync.py"  "$VAULT/scripts/"
cp "$SCRIPT_DIR/scripts/verify.py"              "$VAULT/scripts/"
chmod +x "$VAULT/scripts/"*.py
ok "Scripts installed to ~/.gr0b/scripts/"

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "────────────────────────────────────────────"
echo -e "${GREEN}${BOLD}  gr0b installed successfully.${RESET}"
echo ""
echo "  Next steps:"
echo "  1. Open Obsidian → Open folder as vault → ~/.gr0b"
echo "     (press Cmd+Shift+. to show hidden folders)"
echo ""
echo "  2. Start agentmemory before your sessions:"
echo "     npx @agentmemory/agentmemory"
echo ""
echo "  3. Import your Claude history:"
echo "     agentmemory import-jsonl"
echo ""
echo "  4. Build your knowledge graph (first run):"
echo "     cd ~/Desktop && graphify update ."
echo ""
echo "  5. Generate your brain map:"
echo "     python3 ~/.gr0b/scripts/gr0b_map.py"
echo ""
echo "  Verify installation:"
echo "  python3 ~/.gr0b/scripts/verify.py"
echo ""
echo "  Restart Claude Desktop and Antigravity to activate MCP servers."
echo "────────────────────────────────────────────"
