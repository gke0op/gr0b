# gr0b — uninstall.ps1
# Removes all gr0b services and wiring.
# Preserves $env:USERPROFILE\.gr0b\ data by default; use -Purge to delete it.
#
# Usage:
#   .\uninstall.ps1           # remove services, strip agent wiring, keep data
#   .\uninstall.ps1 -Purge   # also delete the vault

#Requires -Version 5.1
param([switch]$Purge)
$ErrorActionPreference = "Stop"

$VAULT = "$env:USERPROFILE\.gr0b"

function ok($msg)   { Write-Host "  $([char]0x2713)  $msg" -ForegroundColor Green }
function warn($msg) { Write-Host "  !  $msg" -ForegroundColor Yellow }
function skip($msg) { Write-Host "  -  $msg" -ForegroundColor DarkGray }
function step($msg) { Write-Host "`n> $msg" -ForegroundColor Cyan }

Write-Host "`ngr0b uninstall" -ForegroundColor White
Write-Host "--------------------------------------------"
if ($Purge) { Write-Host "  -Purge: vault data will be deleted" -ForegroundColor Red }

# ── Stop & remove scheduled tasks ────────────────────────────────────────────
step "Removing scheduled tasks"

foreach ($name in @("gr0b.agentmemory", "gr0b.graphify")) {
    $task = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if ($task) {
        Stop-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $name -Confirm:$false
        ok "Removed scheduled task: $name"
    } else {
        skip "$name not found — skipping"
    }
}

# ── Strip gr0b blocks from agent config files ─────────────────────────────────
step "Stripping agent wiring"

function Strip-Gr0b($FilePath, $Label) {
    if (-not (Test-Path $FilePath)) {
        skip "$Label not found — skipping"
        return
    }
    $content = Get-Content -Raw $FilePath
    if ($content -notmatch "gr0b:start") {
        skip "$Label has no .gr0b block — skipping"
        return
    }
    # Remove everything between the sentinel comments (inclusive)
    $cleaned = $content -replace "(?s)<!-- gr0b:start -->.*?<!-- gr0b:end -->\r?\n?", ""
    Set-Content -Encoding UTF8 -Path $FilePath -Value $cleaned.TrimEnd()
    ok "Stripped .gr0b block from $Label"
}

Strip-Gr0b "$env:USERPROFILE\.claude\CLAUDE.md" "CLAUDE.md"
Strip-Gr0b "$env:USERPROFILE\.gemini\GEMINI.md" "GEMINI.md"

# ── Remove MCP server entries from Claude Desktop config ──────────────────────
step "Removing MCP server entries"

$DESKTOP_CFG = "$env:APPDATA\Claude\claude_desktop_config.json"
if (Test-Path $DESKTOP_CFG) {
    $cfg = Get-Content -Raw $DESKTOP_CFG | ConvertFrom-Json
    $changed = $false
    foreach ($key in @("agentmemory", "graphify")) {
        if ($cfg.mcpServers.PSObject.Properties[$key]) {
            $cfg.mcpServers.PSObject.Properties.Remove($key)
            $changed = $true
        }
    }
    if ($changed) {
        $cfg | ConvertTo-Json -Depth 10 | Set-Content -Encoding UTF8 $DESKTOP_CFG
        ok "Claude Desktop MCP config cleaned"
    } else {
        skip "No gr0b MCP entries found"
    }
} else {
    skip "Claude Desktop config not found — skipping"
}

# ── Vault ─────────────────────────────────────────────────────────────────────
step "Vault"

if ($Purge) {
    if (Test-Path $VAULT) {
        Remove-Item -Recurse -Force $VAULT
        ok "Vault deleted ($VAULT)"
    } else {
        skip "Vault not found — skipping"
    }
} else {
    if (Test-Path $VAULT) {
        ok "Vault preserved at $VAULT"
        Write-Host "     Your session logs, brain map, and decisions are untouched."
        Write-Host "     Run with -Purge to delete everything."
    } else {
        skip "Vault not found"
    }
}

# ── Done ──────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "--------------------------------------------"
Write-Host "  gr0b uninstalled." -ForegroundColor Green
Write-Host ""
Write-Host "  Restart Claude Desktop to deactivate MCP servers."
Write-Host "--------------------------------------------"
