# gr0b — install.ps1
# A persistent brain for your AI agents — shared, graph-backed, hidden.
# https://github.com/gke0op/gr0b
#
# Usage (run as Administrator or standard user with execution policy set):
#   git clone https://github.com/gke0op/gr0b && cd gr0b
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#   .\install.ps1

#Requires -Version 5.1
$ErrorActionPreference = "Stop"

$VAULT       = "$env:USERPROFILE\.gr0b"
$VERSION     = "0.1.0"
$SCRIPT_DIR  = Split-Path -Parent $MyInvocation.MyCommand.Path

function ok($msg)   { Write-Host "  $([char]0x2713)  $msg" -ForegroundColor Green }
function warn($msg) { Write-Host "  !  $msg" -ForegroundColor Yellow }
function fail($msg) { Write-Host "  X  $msg" -ForegroundColor Red }
function step($msg) { Write-Host "`n> $msg" -ForegroundColor Cyan }

Write-Host "`ngr0b v$VERSION — persistent brain for your AI agents" -ForegroundColor White
Write-Host "--------------------------------------------"

# ── Dependency check ──────────────────────────────────────────────────────────
step "Checking dependencies"

$MISSING = $false

function need($cmd, $hint) {
    if (Get-Command $cmd -ErrorAction SilentlyContinue) {
        ok $cmd
    } else {
        fail "$cmd not found — $hint"
        $script:MISSING = $true
    }
}

need "uv"   "Install from https://astral.sh/uv  or: winget install astral-sh.uv"
need "node" "Install from https://nodejs.org  or: winget install OpenJS.NodeJS"
need "git"  "Install from https://git-scm.com  or: winget install Git.Git"

if ($MISSING) {
    Write-Host ""
    fail "Install missing dependencies then re-run install.ps1"
    exit 1
}

# ── Install tools ─────────────────────────────────────────────────────────────
step "Installing graphifyy"
try {
    & uv tool install --force graphifyy --with watchdog --quiet 2>$null
    ok "graphifyy installed"
} catch {
    warn "graphifyy install had warnings — continuing"
}

step "Installing agentmemory"
try {
    & npm install -g @agentmemory/agentmemory @agentmemory/mcp --quiet 2>$null
    ok "agentmemory installed"
} catch {
    warn "agentmemory install had warnings — continuing"
}

# ── Create vault structure ────────────────────────────────────────────────────
step "Creating vault at $VAULT"

$dirs = @(
    ".obsidian",
    "knowledge-graphs",
    "session-logs\claude",
    "session-logs\gemini",
    "session-logs\codex",
    "decisions",
    "agents\claude",
    "agents\gemini",
    "agents\codex",
    "agents\cursor",
    "scripts"
)

foreach ($d in $dirs) {
    New-Item -ItemType Directory -Force -Path "$VAULT\$d" | Out-Null
}

ok "Vault directory structure created"

# ── Obsidian config ───────────────────────────────────────────────────────────
step "Configuring Obsidian"

@'
{
  "promptDelete": false,
  "theme": "obsidian",
  "translucency": false,
  "defaultViewMode": "preview",
  "livePreview": true
}
'@ | Set-Content -Encoding UTF8 "$VAULT\.obsidian\app.json"

@'
{
  "theme": "obsidian",
  "cssTheme": "",
  "interfaceFontFamily": "",
  "textFontFamily": "",
  "monospaceFontFamily": ""
}
'@ | Set-Content -Encoding UTF8 "$VAULT\.obsidian\appearance.json"

@'
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
'@ | Set-Content -Encoding UTF8 "$VAULT\.obsidian\graph.json"

ok "Obsidian configured (dark theme, colour-coded graph)"

# ── index.md ──────────────────────────────────────────────────────────────────
$DATE = Get-Date -Format "yyyy-MM-dd"
@"
# .gr0b — Persistent Brain

> Installed $DATE · gr0b v$VERSION

## Agents

| Agent | Config | Session logs |
|-------|--------|--------------|
| Claude Code | ``~/.claude/CLAUDE.md`` | ``session-logs/claude/`` |
| Gemini / Antigravity | ``~/.gemini/GEMINI.md`` | ``session-logs/gemini/`` |
| Codex | ``~/.codex/AGENTS.md`` | ``session-logs/codex/`` |

## Memory layers

- **Knowledge graph** — ``knowledge-graphs/`` (graphify, auto-updated)
- **Session logs** — ``session-logs/`` (written by agents each session)
- **Decisions** — ``decisions/`` (architecture & design records)
- **Shared memory** — agentmemory MCP (cross-agent, semantic search)

## Brain map

See ``BRAIN_MAP.md`` for a human-readable map of your codebase communities.
Regenerate: ``python3 ~/.gr0b/scripts/gr0b_map.py``
"@ | Set-Content -Encoding UTF8 "$VAULT\index.md"

ok "index.md created"

# ── Wire CLAUDE.md ────────────────────────────────────────────────────────────
step "Wiring Claude Code"

$CLAUDE_DIR = "$env:USERPROFILE\.claude"
$CLAUDE_MD  = "$CLAUDE_DIR\CLAUDE.md"
New-Item -ItemType Directory -Force -Path $CLAUDE_DIR | Out-Null
if (-not (Test-Path $CLAUDE_MD)) { "" | Set-Content -Encoding UTF8 $CLAUDE_MD }

$claudeContent = Get-Content -Raw $CLAUDE_MD -ErrorAction SilentlyContinue
if ($claudeContent -match "gr0b:start") {
    ok "CLAUDE.md already has .gr0b directive"
} else {
    $directive = @'

<!-- gr0b:start -->
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
<!-- gr0b:end -->
'@
    Add-Content -Encoding UTF8 -Path $CLAUDE_MD -Value $directive
    ok "CLAUDE.md wired with .gr0b directive"
}

# Run graphify claude install if available
if (Get-Command graphify -ErrorAction SilentlyContinue) {
    try { & graphify claude install --quiet 2>$null; ok "graphify skill installed for Claude" } catch {}
}

# ── Wire GEMINI.md ────────────────────────────────────────────────────────────
step "Wiring Gemini / Antigravity"

$GEMINI_DIR = "$env:USERPROFILE\.gemini"
$GEMINI_MD  = "$GEMINI_DIR\GEMINI.md"
New-Item -ItemType Directory -Force -Path $GEMINI_DIR | Out-Null
if (-not (Test-Path $GEMINI_MD)) { "" | Set-Content -Encoding UTF8 $GEMINI_MD }

$geminiContent = Get-Content -Raw $GEMINI_MD -ErrorAction SilentlyContinue
if ($geminiContent -match "gr0b:start") {
    ok "GEMINI.md already has .gr0b directive"
} else {
    $directive = @'

<!-- gr0b:start -->
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
<!-- gr0b:end -->
'@
    Add-Content -Encoding UTF8 -Path $GEMINI_MD -Value $directive
    ok "GEMINI.md wired with .gr0b directive"
}

if (Get-Command graphify -ErrorAction SilentlyContinue) {
    try { & graphify antigravity install --quiet 2>$null; ok "graphify skill installed for Gemini" } catch {}
}

# ── MCP servers — Claude Desktop ──────────────────────────────────────────────
step "Registering MCP servers"

$DESKTOP_CFG = "$env:APPDATA\Claude\claude_desktop_config.json"
if (Test-Path $DESKTOP_CFG) {
    $cfg = Get-Content -Raw $DESKTOP_CFG | ConvertFrom-Json
    if (-not $cfg.mcpServers) { $cfg | Add-Member -NotePropertyName mcpServers -NotePropertyValue ([pscustomobject]@{}) }
    $servers = $cfg.mcpServers

    if (-not $servers.agentmemory) {
        $servers | Add-Member -NotePropertyName agentmemory -NotePropertyValue ([pscustomobject]@{
            command = "agentmemory"; args = @("mcp")
        })
    }
    if (-not $servers.graphify) {
        $graphPath = "$env:USERPROFILE\Desktop\graphify-out\graph.json"
        $servers | Add-Member -NotePropertyName graphify -NotePropertyValue ([pscustomobject]@{
            command = "uv"
            args    = @("run", "--with", "graphifyy", "--with", "mcp", "-m", "graphify.serve", $graphPath)
        })
    }
    $cfg | ConvertTo-Json -Depth 10 | Set-Content -Encoding UTF8 $DESKTOP_CFG
    ok "Claude Desktop MCP config updated"
} else {
    warn "Claude Desktop config not found — install Claude Desktop first"
}

# ── Windows Task Scheduler watcher ────────────────────────────────────────────
step "Setting up graphify watcher (Task Scheduler)"

$GRAPHIFY_CMD = (Get-Command graphify -ErrorAction SilentlyContinue)?.Source
if ($GRAPHIFY_CMD) {
    $WATCH_DIR  = "$env:USERPROFILE\Desktop"
    $TASK_NAME  = "gr0b.graphify"
    $LOG_OUT    = "$VAULT\session-logs\graphify.log"
    $LOG_ERR    = "$VAULT\session-logs\graphify-error.log"

    $action  = New-ScheduledTaskAction -Execute $GRAPHIFY_CMD -Argument "watch `"$WATCH_DIR`""
    $trigger = New-ScheduledTaskTrigger -AtLogOn
    $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)

    Unregister-ScheduledTask -TaskName $TASK_NAME -Confirm:$false -ErrorAction SilentlyContinue
    Register-ScheduledTask -TaskName $TASK_NAME -Action $action -Trigger $trigger -Settings $settings -RunLevel Highest -Force | Out-Null
    Start-ScheduledTask -TaskName $TASK_NAME -ErrorAction SilentlyContinue
    ok "graphify watcher registered in Task Scheduler ($TASK_NAME)"
} else {
    warn "graphify not found in PATH — skipping watcher setup"
}

# ── Copy scripts into vault ───────────────────────────────────────────────────
step "Installing gr0b scripts"

Copy-Item "$SCRIPT_DIR\scripts\gr0b_map.py"           "$VAULT\scripts\" -Force
Copy-Item "$SCRIPT_DIR\scripts\gr0b_obsidian_sync.py" "$VAULT\scripts\" -Force
Copy-Item "$SCRIPT_DIR\scripts\verify.py"             "$VAULT\scripts\" -Force
ok "Scripts installed to $VAULT\scripts\"

# ── Done ──────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "--------------------------------------------"
Write-Host "  gr0b installed successfully." -ForegroundColor Green
Write-Host ""
Write-Host "  Next steps:"
Write-Host "  1. Open Obsidian -> Open folder as vault -> $VAULT"
Write-Host ""
Write-Host "  2. Start agentmemory before your sessions:"
Write-Host "     npx @agentmemory/agentmemory"
Write-Host ""
Write-Host "  3. Import your Claude history:"
Write-Host "     agentmemory import-jsonl"
Write-Host ""
Write-Host "  4. Build your knowledge graph (first run):"
Write-Host "     cd `$env:USERPROFILE\Desktop; graphify update ."
Write-Host ""
Write-Host "  5. Generate your brain map:"
Write-Host "     python3 $VAULT\scripts\gr0b_map.py"
Write-Host ""
Write-Host "  Verify installation:"
Write-Host "  python3 $VAULT\scripts\verify.py"
Write-Host ""
Write-Host "  Restart Claude Desktop to activate MCP servers."
Write-Host "--------------------------------------------"
