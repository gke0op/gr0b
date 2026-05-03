#!/usr/bin/env python3
"""
gr0b verify.py — check that your installation is healthy.

Run after install to confirm everything is wired correctly:
    python3 ~/.gr0b/scripts/verify.py
"""
import json
import os
import subprocess
import sys
from pathlib import Path

HOME  = Path.home()
VAULT = HOME / ".gr0b"
OK    = "  \u2705"
FAIL  = "  \u274c"
WARN  = "  \u26a0\ufe0f "

results = []


def check(claim: str, ok: bool, detail: str = "", fix: str = ""):
    results.append((claim, ok, detail, fix))
    sym = OK if ok else FAIL
    print(f"{sym}  {claim}")
    if detail:
        print(f"      {detail}")
    if not ok and fix:
        print(f"      FIX: {fix}")


def warn(claim: str, detail: str = ""):
    print(f"{WARN}  {claim}")
    if detail:
        print(f"      {detail}")


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True,
                       shell=isinstance(cmd, str))
    return r.stdout.strip(), r.returncode


def cmd_exists(name: str) -> bool:
    import shutil
    return shutil.which(name) is not None


# ─────────────────────────────────────────────────────────────────────────────
print()
print("\u2554" + "\u2550" * 44 + "\u2557")
print("\u2551     gr0b  INSTALLATION VERIFY             \u2551")
print("\u255a" + "\u2550" * 44 + "\u255d")
print()

# ── Dependencies ──────────────────────────────────────────────────────────────
print("\u2501\u2501\u2501 Dependencies \u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501")

check("uv installed",        cmd_exists("uv"),       fix="curl -LsSf https://astral.sh/uv/install.sh | sh")
check("node installed",      cmd_exists("node"),     fix="https://nodejs.org")
check("git installed",       cmd_exists("git"),      fix="brew install git  (mac)  /  winget install Git.Git  (windows)")
check("graphify installed",  cmd_exists("graphify"), fix="uv tool install --force graphifyy --with watchdog")
check("agentmemory installed", cmd_exists("agentmemory"),
      fix="npm install -g @agentmemory/agentmemory @agentmemory/mcp")
print()

# ── Vault structure ───────────────────────────────────────────────────────────
print("\u2501\u2501\u2501 Vault structure \u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501")

check("~/.gr0b/ exists",              VAULT.is_dir())
check("index.md exists",              (VAULT / "index.md").exists())
check(".obsidian/app.json exists",    (VAULT / ".obsidian" / "app.json").exists())
check("session-logs/claude/ exists",  (VAULT / "session-logs" / "claude").is_dir())
check("session-logs/gemini/ exists",  (VAULT / "session-logs" / "gemini").is_dir())
check("knowledge-graphs/ exists",     (VAULT / "knowledge-graphs").is_dir())
check("scripts/ exists",              (VAULT / "scripts").is_dir())
print()

# ── Agent wiring ──────────────────────────────────────────────────────────────
print("\u2501\u2501\u2501 Agent wiring \u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501")

claude_md = HOME / ".claude" / "CLAUDE.md"
if claude_md.exists():
    txt = claude_md.read_text()
    check("~/.claude/CLAUDE.md has .gr0b directive",  ".gr0b" in txt)
    check("CLAUDE.md references index.md",            "index.md" in txt)
    check("CLAUDE.md references session-logs",        "session-logs" in txt)
    check("CLAUDE.md references graphify",            "graphify" in txt)
    check("CLAUDE.md references agentmemory",         "agentmemory" in txt)
else:
    check("~/.claude/CLAUDE.md exists", False,
          fix="Run install.sh to wire CLAUDE.md")

gemini_md = HOME / ".gemini" / "GEMINI.md"
if gemini_md.exists():
    txt = gemini_md.read_text()
    check("~/.gemini/GEMINI.md has .gr0b directive",  ".gr0b" in txt)
    check("GEMINI.md references session-logs",        "session-logs" in txt)
else:
    check("~/.gemini/GEMINI.md exists", False)

print()

# ── MCP servers ───────────────────────────────────────────────────────────────
print("\u2501\u2501\u2501 MCP servers \u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501")

# macOS / Linux Claude Desktop config
import platform
if platform.system() == "Darwin":
    desktop_cfg = HOME / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
elif platform.system() == "Windows":
    desktop_cfg = Path(os.environ.get("APPDATA", "")) / "Claude" / "claude_desktop_config.json"
else:
    desktop_cfg = HOME / ".config" / "Claude" / "claude_desktop_config.json"

if desktop_cfg.exists():
    cfg = json.loads(desktop_cfg.read_text())
    servers = cfg.get("mcpServers", {})
    check("agentmemory in Claude Desktop MCP config", "agentmemory" in servers)
    check("graphify in Claude Desktop MCP config",    "graphify" in servers)
else:
    check("Claude Desktop config exists", False,
          detail=str(desktop_cfg),
          fix="Install Claude Desktop then re-run install.sh")

# agentmemory daemon registered?
if platform.system() == "Darwin":
    am_plist = HOME / "Library" / "LaunchAgents" / "gr0b.agentmemory.plist"
    check("agentmemory launchd plist exists", am_plist.exists(),
          fix="Re-run install.sh to register the daemon")
    out, _ = run(["launchctl", "list"])
    check("gr0b.agentmemory loaded in launchctl", "gr0b.agentmemory" in out,
          fix="launchctl load ~/Library/LaunchAgents/gr0b.agentmemory.plist")
elif platform.system() == "Linux":
    out, rc = run(["systemctl", "--user", "is-enabled", "gr0b-agentmemory.service"])
    check("agentmemory systemd service enabled", rc == 0,
          fix="systemctl --user enable --now gr0b-agentmemory.service")
    out, rc = run(["systemctl", "--user", "is-active", "gr0b-agentmemory.service"])
    check("agentmemory systemd service active", rc == 0,
          fix="systemctl --user start gr0b-agentmemory.service")
elif platform.system() == "Windows":
    out, rc = run('powershell -Command "Get-ScheduledTask -TaskName gr0b.agentmemory 2>$null | Select-Object -ExpandProperty State"')
    check("agentmemory scheduled task registered",
          rc == 0 and out.strip() in ("Ready", "Running"),
          detail=out.strip() or "not found",
          fix="Re-run install.ps1 to register the task")

# Live agentmemory probe (works regardless of how it was started)
out, rc = run("curl -s --max-time 3 http://localhost:3111/agentmemory/health 2>/dev/null")
am_up = rc == 0 and any(k in out.lower() for k in ("ok", "healthy", "{"))
check("agentmemory server reachable at :3111",
      am_up,
      detail=out[:80] if out else "no response — daemon may still be starting",
      fix="Check logs: cat ~/.gr0b/session-logs/agentmemory.log")

print()

# ── Knowledge graph ───────────────────────────────────────────────────────────
print("\u2501\u2501\u2501 Knowledge graph \u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501")

graph = HOME / "Desktop" / "graphify-out" / "graph.json"
if graph.exists():
    size_mb = graph.stat().st_size / 1_048_576
    check("graph.json exists and is non-empty",
          graph.stat().st_size > 10_000,
          detail=f"{size_mb:.1f} MB")
else:
    check("graph.json exists", False,
          fix="cd ~/Desktop && graphify update .")

brain_map = VAULT / "BRAIN_MAP.md"
check("BRAIN_MAP.md generated",
      brain_map.exists(),
      fix="python3 ~/.gr0b/scripts/gr0b_map.py")

print()

# ── Graphify watcher daemon ───────────────────────────────────────────────────
if platform.system() == "Darwin":
    print("\u2501\u2501\u2501 Graphify watcher (macOS) \u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501")

    plist = HOME / "Library" / "LaunchAgents" / "gr0b.graphify.plist"
    check("gr0b.graphify plist exists", plist.exists(),
          fix="Re-run install.sh")

    out, _ = run(["launchctl", "list"])
    check("gr0b.graphify loaded", "gr0b.graphify" in out,
          fix="launchctl load ~/Library/LaunchAgents/gr0b.graphify.plist")
    print()

elif platform.system() == "Linux":
    print("\u2501\u2501\u2501 Graphify watcher (Linux) \u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501")
    warn("Graphify watcher not yet configured — run manually: graphify watch ~/Desktop")
    print()

# ─────────────────────────────────────────────────────────────────────────────
passed = sum(1 for _, ok, _, _ in results if ok)
failed = [(c, d, f) for c, ok, d, f in results if not ok]
total  = len(results)
pct    = int(passed / total * 100) if total else 0

print(f"\u2501\u2501\u2501 RESULT: {passed}/{total} ({pct}%) \u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501")
print()

if failed:
    print("  Issues to resolve:")
    for claim, detail, fix in failed:
        print(f"    \u274c {claim}")
        if fix:
            print(f"       \u2192 {fix}")
    print()
    sys.exit(1)
else:
    print("  All checks passed. gr0b is healthy. \u2705")
    print()
    sys.exit(0)
