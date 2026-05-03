#!/bin/bash
# gr0b — uninstall.sh
# Removes all gr0b services and wiring.
# Preserves ~/.gr0b/ data by default; use --purge to delete it.
#
# Usage:
#   bash uninstall.sh           # remove services, strip agent wiring, keep data
#   bash uninstall.sh --purge   # also delete ~/.gr0b/ vault

set -euo pipefail

VAULT="$HOME/.gr0b"
PURGE=0
OS="$(uname -s)"

# ── Colour output ─────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

ok()   { echo -e "${GREEN}  ✓${RESET}  $1"; }
warn() { echo -e "${YELLOW}  ⚠${RESET}  $1"; }
skip() { echo -e "  –  $1"; }
step() { echo -e "\n${CYAN}${BOLD}▸ $1${RESET}"; }

# ── Parse flags ───────────────────────────────────────────────────────────────
for arg in "$@"; do
    case "$arg" in
        --purge) PURGE=1 ;;
        --help|-h)
            echo "Usage: bash uninstall.sh [--purge]"
            echo "  --purge   also delete ~/.gr0b/ vault data"
            exit 0 ;;
        *)
            echo "Unknown flag: $arg  (use --help)"
            exit 1 ;;
    esac
done

echo -e "\n${BOLD}gr0b uninstall${RESET}"
echo "────────────────────────────────────────────"
if [[ $PURGE -eq 1 ]]; then
    echo -e "${RED}  --purge: vault data will be deleted${RESET}"
fi

# ── Stop & remove daemons ─────────────────────────────────────────────────────
step "Removing daemons"

if [[ "$OS" == "Darwin" ]]; then
    for label in gr0b.agentmemory gr0b.graphify gr0b.reflect; do
        plist="$HOME/Library/LaunchAgents/${label}.plist"
        if [[ -f "$plist" ]]; then
            launchctl unload "$plist" 2>/dev/null || true
            rm -f "$plist"
            ok "Removed $label (launchd)"
        else
            skip "$label plist not found — skipping"
        fi
    done

elif [[ "$OS" == "Linux" ]]; then
    if command -v systemctl &>/dev/null; then
        for unit in gr0b-agentmemory.service gr0b-reflect.service gr0b-reflect.timer; do
            if systemctl --user is-enabled "$unit" &>/dev/null 2>&1; then
                systemctl --user stop    "$unit" 2>/dev/null || true
                systemctl --user disable "$unit" 2>/dev/null || true
                rm -f "$HOME/.config/systemd/user/$unit"
                ok "Removed $unit (systemd --user)"
            else
                skip "$unit not enabled — skipping"
            fi
        done
        systemctl --user daemon-reload 2>/dev/null || true
    fi
fi

# ── Strip gr0b blocks from agent config files ─────────────────────────────────
step "Stripping agent wiring"

strip_gr0b() {
    local file="$1"
    local label="$2"
    if [[ ! -f "$file" ]]; then
        skip "$label not found — skipping"
        return
    fi
    if ! grep -q "gr0b:start" "$file" 2>/dev/null; then
        skip "$label has no .gr0b block — skipping"
        return
    fi
    # sed -i behaviour differs between macOS and Linux
    if [[ "$OS" == "Darwin" ]]; then
        sed -i '' '/<!-- gr0b:start -->/,/<!-- gr0b:end -->/d' "$file"
    else
        sed -i '/<!-- gr0b:start -->/,/<!-- gr0b:end -->/d' "$file"
    fi
    ok "Stripped .gr0b block from $label"
}

strip_gr0b "$HOME/.claude/CLAUDE.md"   "CLAUDE.md"
strip_gr0b "$HOME/.gemini/GEMINI.md"   "GEMINI.md"

# ── Remove MCP server entries from Claude Desktop config ──────────────────────
step "Removing MCP server entries"

if [[ "$OS" == "Darwin" ]]; then
    DESKTOP_CFG="$HOME/Library/Application Support/Claude/claude_desktop_config.json"
elif [[ "$OS" == "Linux" ]]; then
    DESKTOP_CFG="$HOME/.config/Claude/claude_desktop_config.json"
else
    DESKTOP_CFG=""
fi

if [[ -n "$DESKTOP_CFG" && -f "$DESKTOP_CFG" ]]; then
    python3 - "$DESKTOP_CFG" << 'PYEOF'
import json, sys
from pathlib import Path
path = sys.argv[1]
raw = Path(path).read_text().strip()
cfg = json.loads(raw) if raw else {}
servers = cfg.get("mcpServers", {})
removed = []
for key in ("agentmemory", "graphify"):
    if key in servers:
        del servers[key]
        removed.append(key)
Path(path).write_text(json.dumps(cfg, indent=2))
if removed:
    print(f"  Removed MCP entries: {', '.join(removed)}")
else:
    print("  No gr0b MCP entries found")
PYEOF
    ok "Claude Desktop MCP config cleaned"
else
    skip "Claude Desktop config not found — skipping"
fi

# ── Vault ─────────────────────────────────────────────────────────────────────
step "Vault"

if [[ $PURGE -eq 1 ]]; then
    if [[ -d "$VAULT" ]]; then
        rm -rf "$VAULT"
        ok "Vault deleted ($VAULT)"
    else
        skip "Vault not found — skipping"
    fi
else
    if [[ -d "$VAULT" ]]; then
        ok "Vault preserved at $VAULT"
        echo "     Your session logs, brain map, and decisions are untouched."
        echo "     Run with --purge to delete everything."
    else
        skip "Vault not found"
    fi
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "────────────────────────────────────────────"
echo -e "${GREEN}${BOLD}  gr0b uninstalled.${RESET}"
echo ""
echo "  Restart Claude Desktop to deactivate MCP servers."
echo "────────────────────────────────────────────"
