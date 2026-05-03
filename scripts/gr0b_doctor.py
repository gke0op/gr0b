#!/usr/bin/env python3
"""
gr0b doctor — system dashboard.

Shows the live state of every gr0b subsystem in a single glance:
services, memory, insights, decisions, session logs, knowledge graph.

Usage:
    python3 ~/.gr0b/scripts/gr0b_doctor.py
    python3 ~/.gr0b/scripts/gr0b_doctor.py --json   (machine-readable output)
    python3 ~/.gr0b/scripts/gr0b_doctor.py --quiet  (only problems, exit 1 if any)
"""

import argparse
import json
import os
import platform
import re
import subprocess
import sys
import urllib.request
import urllib.error
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

VAULT    = Path.home() / ".gr0b"
LOGS_DIR = VAULT / "session-logs"
INSIGHTS = VAULT / "insights"
DECISIONS = VAULT / "decisions"
GRAPH    = Path.home() / "Desktop" / "graphify-out" / "graph.json"
AGENTS   = ["claude", "gemini", "codex"]

_OS      = platform.system()
_tty     = sys.stdout.isatty()


# ── Colour ────────────────────────────────────────────────────────────────────

def _c(code, t): return f"\033[{code}m{t}\033[0m" if _tty else t
def green(t):    return _c("32", t)
def yellow(t):   return _c("33", t)
def red(t):      return _c("31", t)
def cyan(t):     return _c("36", t)
def bold(t):     return _c("1",  t)
def dim(t):      return _c("2",  t)

BULLET_OK   = green("●")
BULLET_WARN = yellow("◐")
BULLET_OFF  = red("○")
BULLET_UNK  = dim("◌")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _run(cmd, timeout=3):
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=timeout, shell=isinstance(cmd, str),
        )
        return r.stdout.strip(), r.returncode
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return "", 1


def _age(path: Path) -> str:
    """Human-readable age of a file's mtime."""
    if not path.exists():
        return "never"
    delta = datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)
    s = int(delta.total_seconds())
    if s < 60:       return "just now"
    if s < 3600:     return f"{s // 60}m ago"
    if s < 86400:    return f"{s // 3600}h ago"
    if s < 86400*7:  return f"{s // 86400}d ago"
    return f"{s // 86400}d ago"


def _age_days(path: Path) -> int | None:
    if not path.exists():
        return None
    return int((datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)).total_seconds() / 86400)


def _count_lines_matching(path: Path, pattern: str) -> int:
    if not path.exists():
        return 0
    try:
        return sum(1 for l in path.read_text().splitlines() if re.search(pattern, l))
    except OSError:
        return 0


def _probe_agentmemory() -> dict:
    """Try to reach agentmemory health endpoint. Returns parsed data or {}."""
    try:
        with urllib.request.urlopen(
            "http://localhost:3111/agentmemory/health", timeout=3
        ) as resp:
            raw = resp.read().decode()
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return {"_raw": raw[:80]}
    except Exception:
        return {}


# ── Section collectors ────────────────────────────────────────────────────────

def collect_services() -> dict:
    result = {}

    # agentmemory ─────────────────────────────────────────────────────────────
    am_health = _probe_agentmemory()
    am_up     = bool(am_health)

    am_daemon = "unknown"
    if _OS == "Darwin":
        plist = Path.home() / "Library" / "LaunchAgents" / "gr0b.agentmemory.plist"
        launchctl_out, _ = _run(["launchctl", "list"])
        am_daemon = "registered" if "gr0b.agentmemory" in launchctl_out else "not registered"
        if not plist.exists():
            am_daemon = "not installed"
    elif _OS == "Linux":
        _, rc = _run(["systemctl", "--user", "is-active", "gr0b-agentmemory.service"])
        am_daemon = "active" if rc == 0 else "inactive"
    elif _OS == "Windows":
        out, rc = _run('powershell -Command "Get-ScheduledTask -TaskName gr0b.agentmemory 2>$null | Select State"')
        am_daemon = "registered" if rc == 0 and out else "not registered"

    entries = am_health.get("entries") or am_health.get("count") or am_health.get("total")
    conflicts = am_health.get("conflicts")

    result["agentmemory"] = {
        "up":       am_up,
        "daemon":   am_daemon,
        "entries":  entries,
        "conflicts": conflicts,
        "health":   am_health,
    }

    # graphify watcher ────────────────────────────────────────────────────────
    gfy_daemon = "unknown"
    if _OS == "Darwin":
        plist = Path.home() / "Library" / "LaunchAgents" / "gr0b.graphify.plist"
        launchctl_out, _ = _run(["launchctl", "list"])
        gfy_loaded = "gr0b.graphify" in launchctl_out
        if not plist.exists():
            gfy_daemon = "not installed"
        elif gfy_loaded:
            gfy_daemon = "running"
        else:
            gfy_daemon = "stopped"
    elif _OS == "Linux":
        gfy_daemon = "manual"  # no systemd unit for graphify yet

    result["graphify"] = {"daemon": gfy_daemon}

    # reflect scheduler ───────────────────────────────────────────────────────
    reflect_log = VAULT / "session-logs" / "reflect.log"
    last_run    = _age(reflect_log) if reflect_log.exists() else None
    reflect_scheduled = False

    if _OS == "Darwin":
        plist = Path.home() / "Library" / "LaunchAgents" / "gr0b.reflect.plist"
        reflect_scheduled = plist.exists()
    elif _OS == "Linux":
        _, rc = _run(["systemctl", "--user", "is-enabled", "gr0b-reflect.timer"])
        reflect_scheduled = rc == 0

    result["reflect"] = {
        "scheduled": reflect_scheduled,
        "last_run":  last_run,
        "log":       reflect_log,
    }

    return result


def collect_insights() -> dict:
    if not INSIGHTS.exists():
        return {"exists": False}

    threads_path = INSIGHTS / "open-threads.md"
    contra_path  = INSIGHTS / "contradictions.md"
    failures_path = INSIGHTS / "recurring-failures.md"

    # Open threads: count list items, count 🔴 stale
    threads_total = _count_lines_matching(threads_path, r"^- ")
    threads_stale = _count_lines_matching(threads_path, r"🔴")

    # Contradictions: count --- separators (one per pair)
    contra_count = _count_lines_matching(contra_path, r"^---")

    # Recurring failures: count bold items
    failures_count = _count_lines_matching(failures_path, r"^\- \*\*")

    # Age of most recent insight file
    ages = [p for p in [threads_path, contra_path, failures_path] if p.exists()]
    last_generated = _age(max(ages, key=lambda p: p.stat().st_mtime)) if ages else "never"

    return {
        "exists":          True,
        "threads_total":   threads_total,
        "threads_stale":   threads_stale,
        "contradictions":  contra_count,
        "failures":        failures_count,
        "last_generated":  last_generated,
    }


def collect_decisions() -> dict:
    if not DECISIONS.exists():
        return {"exists": False, "total": 0}

    by_status = defaultdict(int)
    records = []
    for path in DECISIONS.glob("DR-*.md"):
        try:
            text = path.read_text()
        except OSError:
            continue
        m = re.search(r"^status:\s*(\w+)", text, re.M)
        if m:
            by_status[m.group(1)] += 1
            records.append(path)

    return {
        "exists":     True,
        "total":      sum(by_status.values()),
        "accepted":   by_status.get("accepted", 0),
        "proposed":   by_status.get("proposed", 0),
        "superseded": by_status.get("superseded", 0),
    }


def collect_sessions() -> dict:
    agents_data = {}
    for agent in AGENTS:
        agent_dir = LOGS_DIR / agent
        if not agent_dir.is_dir():
            agents_data[agent] = {"count": 0, "last": None}
            continue

        logs = sorted(agent_dir.glob("*.md"))
        if not logs:
            agents_data[agent] = {"count": 0, "last": None}
            continue

        newest = logs[-1]
        agents_data[agent] = {
            "count": len(logs),
            "last":  _age(newest),
            "last_days": _age_days(newest),
        }

    return agents_data


def collect_graph() -> dict:
    if not GRAPH.exists():
        return {"exists": False}

    stat   = GRAPH.stat()
    size_mb = stat.st_size / 1_048_576
    age    = _age(GRAPH)

    # Try to get node count cheaply (first 256 bytes has metadata sometimes)
    node_count = None
    try:
        with open(GRAPH) as f:
            sample = f.read(512)
        m = re.search(r'"nodes"\s*:\s*\[', sample)
        # Full count would need full parse — skip for speed, just note size
    except OSError:
        pass

    return {
        "exists":   True,
        "size_mb":  round(size_mb, 1),
        "age":      age,
        "age_days": _age_days(GRAPH),
    }


# ── Rendering ─────────────────────────────────────────────────────────────────

W = 48  # line width for the rule

def rule(char="─"):
    return dim(char * W)


def section(title: str):
    print(f"\n  {bold(title)}")


def print_dashboard(data: dict):
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"\n{bold('gr0b doctor')} {dim('─' * (W - 11))} {dim(now_str)}")

    svc      = data["services"]
    insights = data["insights"]
    dec      = data["decisions"]
    sessions = data["sessions"]
    graph    = data["graph"]

    problems = []

    # ── Services ──────────────────────────────────────────────────────────────
    section("Services")

    # agentmemory
    am = svc["agentmemory"]
    if am["up"]:
        bullet = BULLET_OK
        status = green("running")
        detail_parts = [f"port :3111"]
        if am["entries"] is not None:
            detail_parts.append(f"{am['entries']:,} entries")
        if am["conflicts"]:
            detail_parts.append(yellow(f"{am['conflicts']} conflicts"))
        detail = "  ·  ".join(detail_parts)
    else:
        bullet = BULLET_OFF
        status = red("not running")
        detail = dim(f"daemon: {am['daemon']}")
        problems.append("agentmemory not running")

    print(f"  {bullet}  agentmemory    {status:<20} {dim(detail)}")

    # graphify
    gfy = svc["graphify"]
    gfy_status = gfy["daemon"]
    if gfy_status == "running":
        bullet = BULLET_OK
        col    = green
    elif gfy_status in ("not installed", "stopped"):
        bullet = BULLET_WARN
        col    = yellow
    else:
        bullet = BULLET_UNK
        col    = dim
    graph_age = f"graph {graph.get('age', '?')}" if graph.get("exists") else "no graph yet"
    print(f"  {bullet}  graphify        {col(gfy_status):<20} {dim(graph_age)}")

    # reflect scheduler
    ref = svc["reflect"]
    if ref["scheduled"]:
        bullet = BULLET_OK
        status_str = green("scheduled")
        last = f"last run {ref['last_run']}" if ref["last_run"] else "not yet run"
    else:
        bullet = BULLET_WARN
        status_str = yellow("not scheduled")
        last = "re-run install.sh"
        problems.append("reflect scheduler not registered")
    print(f"  {bullet}  reflect         {status_str:<20} {dim(last)}")

    # ── Knowledge graph ───────────────────────────────────────────────────────
    section("Knowledge graph")
    if graph.get("exists"):
        age_d = graph.get("age_days", 0) or 0
        if age_d > 7:
            col = yellow
            problems.append(f"graph.json not updated in {age_d}d")
        else:
            col = green
        print(f"  {col('●')}  {graph['size_mb']} MB  ·  updated {graph['age']}")
        print(f"       {dim(str(GRAPH))}")
    else:
        print(f"  {red('○')}  graph.json not found")
        print(f"       {dim('cd ~/Desktop && graphify update .')}")
        problems.append("knowledge graph not built")

    # ── Insights ──────────────────────────────────────────────────────────────
    section("Insights")
    if insights.get("exists") and insights.get("last_generated") != "never":
        t  = insights["threads_total"]
        ts = insights["threads_stale"]
        c  = insights["contradictions"]
        f  = insights["failures"]

        thread_str = f"{t} threads"
        if ts:
            thread_str += f"  ·  {yellow(str(ts) + ' stale')}"

        contra_str = green(f"{c} contradictions") if c == 0 else yellow(f"{c} contradictions")
        fail_str   = f"{f} recurring failures"

        print(f"  {dim(thread_str)}")
        print(f"  {dim(contra_str + '  ·  ' + fail_str)}")
        print(f"  {dim('last generated: ' + insights['last_generated'])}")
    else:
        print(f"  {dim('No insights yet.')}")
        print(f"  {dim('Run: python3 ~/.gr0b/scripts/gr0b_reflect.py')}")

    # ── Decisions ─────────────────────────────────────────────────────────────
    section("Decisions")
    if dec.get("total", 0) > 0:
        parts = [
            green(f"{dec['accepted']} accepted"),
            f"{dec['proposed']} proposed",
            dim(f"{dec['superseded']} superseded"),
        ]
        print(f"  {dec['total']} total  ·  {'  ·  '.join(parts)}")
        print(f"  {dim(str(DECISIONS))}")
    else:
        print(f"  {dim('No decision records yet.')}")
        print(f"  {dim('Run: python3 ~/.gr0b/scripts/gr0b_decisions.py new')}")

    # ── Session logs ──────────────────────────────────────────────────────────
    section("Session logs")
    any_sessions = False
    for agent in AGENTS:
        s = sessions.get(agent, {})
        count = s.get("count", 0)
        if count == 0:
            print(f"  {dim('◌')}  {agent:<10} {dim('no sessions')}")
            continue
        any_sessions = True
        last_d = s.get("last_days", 0) or 0
        if last_d > 14:
            col = yellow
        else:
            col = green
        print(f"  {col('●')}  {agent:<10} {count:>4} sessions  ·  last {s.get('last', '?')}")

    if not any_sessions:
        print(f"  {dim('Write your first session log to ~/.gr0b/session-logs/<agent>/')}")

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{dim(rule())}")
    if problems:
        print(f"  {yellow(str(len(problems)) + ' issue(s):')}  ")
        for p in problems:
            print(f"    {yellow('!')}  {p}")
    else:
        print(f"  {green('All systems operational.')}")
    print()


def print_quiet(data: dict) -> int:
    """Print only problems, return exit code 1 if any."""
    problems = []
    am = data["services"]["agentmemory"]
    if not am["up"]:
        problems.append("agentmemory: not running")
    if not data["services"]["reflect"]["scheduled"]:
        problems.append("reflect: not scheduled")
    if not data["graph"].get("exists"):
        problems.append("graph.json: not built")
    if (data["graph"].get("age_days") or 0) > 7:
        problems.append(f"graph.json: {data['graph']['age_days']}d since last update")

    if problems:
        for p in problems:
            print(f"! {p}")
        return 1
    return 0


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--json",  action="store_true", help="output raw JSON")
    parser.add_argument("--quiet", action="store_true",
                        help="only print problems; exit 1 if any found")
    args = parser.parse_args()

    data = {
        "services":  collect_services(),
        "graph":     collect_graph(),
        "insights":  collect_insights(),
        "decisions": collect_decisions(),
        "sessions":  collect_sessions(),
        "timestamp": datetime.now().isoformat(),
    }

    if args.json:
        # Scrub non-serialisable objects (Path)
        def clean(obj):
            if isinstance(obj, Path):
                return str(obj)
            if isinstance(obj, dict):
                return {k: clean(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [clean(i) for i in obj]
            return obj
        print(json.dumps(clean(data), indent=2))
        return

    if args.quiet:
        sys.exit(print_quiet(data))

    print_dashboard(data)


if __name__ == "__main__":
    main()
