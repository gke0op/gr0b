#!/usr/bin/env python3
"""
gr0b_ingest.py — Silicon Mind: per-agent internal-brain ingestion.

Each AI agent keeps an internal store (Claude Code jsonl, Gemini logs, Codex
sessions). gr0b ingests DECISIONS AND LESSONS ONLY — never raw transcripts —
junk-filtered at the gate, opt-in per agent via gr0b.config.yaml.

Pipeline (decoupled by design):
  1. EXTRACT (this script, runs on the host): read internal store →
     junk-filter sessions → distill decision/lesson lines → write one
     markdown card per session to ~/.gr0b/ingest-queue/
  2. COMMIT (Cowork daily task or any MCP client): drain the queue into
     agentmemory via memory_save, archive cards to ingest-queue/done/

Why a queue instead of writing memory directly? The queue is inspectable
(consent + auditability for an open-source brain), survives agentmemory
downtime, and lets extraction run anywhere the files are readable.

Usage:
    python3 gr0b_ingest.py --agent claude-code            # extract → queue
    python3 gr0b_ingest.py --agent claude-code --source-dir /path  # override
    python3 gr0b_ingest.py --purge-spam                   # dry-run list
    python3 gr0b_ingest.py --purge-spam --apply           # actually delete
    python3 gr0b_ingest.py --status                       # state + queue

Consent: refuses to run for any agent whose ingest flag is false/absent in
gr0b.config.yaml (ingest: sources: claude_code_jsonl: true).
"""

import argparse
import json
import re
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

VAULT = Path.home() / ".gr0b"
QUEUE = VAULT / "ingest-queue"
STATE_FILE = VAULT / ".ingest_state.json"
CONFIG = VAULT / "gr0b.config.yaml"
AM_BASE = "http://localhost:3111/agentmemory"

# ── Filters (shared philosophy with gr0b_reflect.py) ─────────────────────────

# Sessions that are pure boilerplate/spam — skipped entirely at the gate.
JUNK_PROMPT_RE = re.compile(
    r"^(analyze this codebase for (security vulnerabilities|performance optimizations)"
    r"|analyze test coverage and identify gaps"
    r"|analyze code quality"
    r"|warmup\b"
    r"|test\s*$"
    r"|hi\s*$|hello\s*$)",
    re.I,
)

# Personal / wellbeing / therapeutic sessions — NEVER ingested into a shared
# brain even when the agent source is opted in. Technical decisions are fair
# game; a person's inner life is not. This is a hard skip, same tier as junk.
PRIVATE_PROMPT_RE = re.compile(
    r"(psycholog|therap|my\s+(mental|emotional)|vulnerable|depress|anxiet"
    r"|personal\s+(protocol|optimization|journal)|how\s+i\s+feel"
    r"|track(ing)?\s+my\s+(mood|psychology|feelings)|diary|confession)",
    re.I,
)

# Assistant sign-off / filler — never real decisions (mirror of reflect JUNK_RE).
JUNK_LINE_RE = re.compile(
    r"(stand(ing)?\s+ready|await(ing)?\s+(the\s+)?(user|operator|gokce|next|further|instructions)"
    r"|assist\s+(the\s+)?(user|operator)|ready\s+(for|to)\s+(the\s+)?next"
    r"|fully\s+satisfied|no\s+further\s+(action|work|changes)"
    r"|session\s+(is\s+)?(complete|concluded|ended)"
    r"|next\s+request|anything\s+else|happy\s+to\s+(help|assist)"
    r"|peak\s+.{0,25}\bstate|optimal\b.{0,20}\bstate|mission\s+accomplished"
    r"|let\s+the\s+user\s+open|user\s+can\s+now\s+(open|see|enjoy))",
    re.I,
)

# Lines that carry a decision, root cause, or lesson.
DECISION_RE = re.compile(
    r"(\bdecided?\b|\bdecision\b|\broot cause\b|\blesson\b|\bthe (bug|fix|problem|issue) (was|is)\b"
    r"|\bfix(ed)?:\s|\bnever\b|\balways\b|\bmust (not )?\b|\binstead of\b"
    r"|\bswitched? (to|from)\b|\bworks because\b|\bfails because\b|\bturned out\b"
    r"|\bkey insight\b|\btakeaway\b|\bgotcha\b|\bdo not\b|\bdon't\b.{0,30}\bbecause\b)",
    re.I,
)

MAX_LINES_PER_SESSION = 12
MIN_LINE, MAX_LINE = 30, 500


# ── Config / consent ──────────────────────────────────────────────────────────

def load_consent() -> dict:
    """Parse ingest.sources flags from gr0b.config.yaml (yaml if available,
    naive line-parser otherwise — config is flat enough)."""
    if not CONFIG.exists():
        return {}
    text = CONFIG.read_text(errors="replace")
    try:
        import yaml  # type: ignore
        data = yaml.safe_load(text) or {}
        return (data.get("ingest") or {}).get("sources") or {}
    except ImportError:
        pass
    sources, in_ingest, in_sources = {}, False, False
    for line in text.splitlines():
        if re.match(r"^ingest:", line):
            in_ingest, in_sources = True, False
            continue
        if in_ingest and re.match(r"^\s+sources:", line):
            in_sources = True
            continue
        if in_ingest and re.match(r"^\S", line):  # left margin = new top key
            break
        if in_sources:
            m = re.match(r"^\s+(\w+):\s*(true|false)", line)
            if m:
                sources[m.group(1)] = m.group(2) == "true"
    return sources


def require_consent(key: str):
    sources = load_consent()
    if not sources.get(key, False):
        sys.exit(
            f"CONSENT GATE: '{key}' is not enabled in {CONFIG}.\n"
            f"Internal agent stores are private. To opt in, add under 'ingest: sources:':\n"
            f"    {key}: true"
        )


# ── State ─────────────────────────────────────────────────────────────────────

def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except json.JSONDecodeError:
            pass
    return {}


def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True))


# ── Claude Code jsonl adapter ─────────────────────────────────────────────────

def iter_jsonl_sessions(source_dir: Path):
    """Yield (path, session_meta, assistant_texts) per jsonl session file."""
    for path in sorted(source_dir.rglob("*.jsonl")):
        first_prompt, texts, meta = None, [], {}
        try:
            with path.open(errors="replace") as fh:
                for raw in fh:
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        rec = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    if not meta:
                        meta = {
                            "session_id": rec.get("sessionId", path.stem),
                            "cwd": rec.get("cwd", ""),
                            "started": rec.get("timestamp", ""),
                        }
                    msg = rec.get("message") or {}
                    role = msg.get("role") or rec.get("type")
                    content = msg.get("content")
                    if isinstance(content, str):
                        blocks = [content]
                    elif isinstance(content, list):
                        blocks = [b.get("text", "") for b in content
                                  if isinstance(b, dict) and b.get("type") == "text"]
                    else:
                        blocks = []
                    text = "\n".join(b for b in blocks if b).strip()
                    if not text:
                        continue
                    if role == "user" and first_prompt is None:
                        first_prompt = text
                    elif role == "assistant":
                        texts.append(text)
        except OSError:
            continue
        meta["first_prompt"] = (first_prompt or "").strip()
        yield path, meta, texts


def distill(texts: list[str]) -> list[str]:
    """Decision/lesson lines only, junk-filtered, deduped, capped."""
    seen, out = set(), []
    for text in texts:
        for line in text.splitlines():
            line = re.sub(r"^(\d+\.\s+|[-*•]\s*|#+\s*)", "", line.strip()).strip()
            if not (MIN_LINE <= len(line) <= MAX_LINE):
                continue
            if line.startswith("```") or JUNK_LINE_RE.search(line):
                continue
            if not DECISION_RE.search(line):
                continue
            key = re.sub(r"\W+", "", line.lower())[:80]
            if key in seen:
                continue
            seen.add(key)
            out.append(line)
            if len(out) >= MAX_LINES_PER_SESSION:
                return out
    return out


def project_from_cwd(cwd: str) -> str:
    return Path(cwd).name if cwd else "unknown"


def write_card(source: str, meta: dict, lines: list[str]) -> Path:
    QUEUE.mkdir(parents=True, exist_ok=True)
    sid = meta.get("session_id", "unknown")[:36]
    card = QUEUE / f"{source}_{sid}.md"
    title = (meta.get("first_prompt") or "")[:120].replace("\n", " ")
    body = [
        "---",
        f"source: {source}",
        f"session_id: {meta.get('session_id', '')}",
        f"project: {project_from_cwd(meta.get('cwd', ''))}",
        f"started: {meta.get('started', '')}",
        f"extracted: {datetime.now(timezone.utc).isoformat()}",
        "---",
        f"# {title}",
        "",
        "## Decisions & lessons",
    ]
    body += [f"- {ln}" for ln in lines]
    card.write_text("\n".join(body) + "\n")
    return card


def ingest_claude_code(source_dir: Path | None):
    require_consent("claude_code_jsonl")
    src = source_dir or (Path.home() / ".claude" / "projects")
    if not src.exists():
        sys.exit(f"Source not found: {src}")
    state = load_state()
    done = set(state.get("claude_code", {}).get("done_sessions", []))
    stats = {"sessions": 0, "junk": 0, "empty": 0, "queued": 0, "skipped_done": 0}
    for path, meta, texts in iter_jsonl_sessions(src):
        stats["sessions"] += 1
        sid = meta.get("session_id", path.stem)
        if sid in done:
            stats["skipped_done"] += 1
            continue
        prompt = meta.get("first_prompt", "")
        if JUNK_PROMPT_RE.match(prompt) or PRIVATE_PROMPT_RE.search(prompt):
            stats["junk"] += 1
            done.add(sid)  # never revisit junk or private
            continue
        lines = distill(texts)
        if not lines:
            stats["empty"] += 1
            done.add(sid)
            continue
        write_card("claude-code", meta, lines)
        stats["queued"] += 1
        done.add(sid)
    state.setdefault("claude_code", {})["done_sessions"] = sorted(done)
    state["claude_code"]["last_run"] = datetime.now(timezone.utc).isoformat()
    save_state(state)
    print(f"claude-code: {stats['sessions']} sessions scanned | "
          f"{stats['junk']} junk skipped | {stats['empty']} no-signal | "
          f"{stats['skipped_done']} already done | {stats['queued']} cards queued → {QUEUE}")


# ── Spam purge (agentmemory REST) ─────────────────────────────────────────────

def http_json(method: str, url: str, payload: dict | None = None):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, method=method, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=20) as resp:
        body = resp.read().decode()
        return json.loads(body) if body.strip() else {}


def purge_spam(apply: bool):
    """Delete jsonl-import spam sessions (boilerplate prompt, ≤4 observations)."""
    sessions = None
    for route in (f"{AM_BASE}/sessions", f"{AM_BASE}/api/sessions"):
        try:
            data = http_json("GET", route)
            sessions = data.get("sessions", data if isinstance(data, list) else None)
            if sessions is not None:
                base = route
                break
        except (urllib.error.URLError, json.JSONDecodeError, OSError):
            continue
    if sessions is None:
        sys.exit("Could not list sessions via REST (tried /sessions, /api/sessions). "
                 "Is the agentmemory daemon running? Check: curl " + AM_BASE + "/health")
    spam = [s for s in sessions
            if "jsonl-import" in (s.get("tags") or [])
            and JUNK_PROMPT_RE.match((s.get("firstPrompt") or "").strip())
            and s.get("observationCount", 99) <= 4]
    print(f"{len(sessions)} sessions in store, {len(spam)} match spam signature "
          f"(tag jsonl-import + boilerplate prompt + ≤4 observations)")
    for s in spam[:5]:
        print(f"  e.g. {s.get('id', '')[:8]}…  '{(s.get('firstPrompt') or '')[:60]}'")
    if not apply:
        print("\nDRY RUN — nothing deleted. Re-run with --apply to delete.")
        return
    # Safety net: export the whole store before touching anything. The forget
    # call is real and audited, but a backup makes it reversible by re-import.
    try:
        export = http_json("GET", f"{AM_BASE}/export")
        bak = VAULT / f"agentmemory-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
        bak.write_text(json.dumps(export, indent=2))
        print(f"Backup written: {bak}  (restore via POST {AM_BASE}/import if needed)")
    except (urllib.error.URLError, OSError) as e:
        sys.exit(f"Backup via /export failed ({e}); refusing to delete without one.")
    # Whole-session delete: mem::forget with {sessionId} and no observationIds
    # removes every observation + the session + its summary (see package source).
    deleted, failed = 0, 0
    for s in spam:
        sid = s.get("id")
        try:
            resp = http_json("POST", f"{AM_BASE}/forget", {"sessionId": sid})
            if resp.get("success") or resp.get("deleted", 0) > 0:
                deleted += 1
            else:
                failed += 1
        except (urllib.error.URLError, OSError):
            failed += 1
    print(f"Forgot {deleted} sessions, failed {failed}. "
          f"Run `--status` or check memory_sessions to confirm the store shrank "
          f"(67 → {len(sessions) - deleted}).")


# ── Status ────────────────────────────────────────────────────────────────────

def status():
    state = load_state()
    queued = sorted(QUEUE.glob("*.md")) if QUEUE.exists() else []
    archived = len(list((QUEUE / "done").glob("*.md"))) if (QUEUE / "done").exists() else 0
    print(f"Consent flags: {load_consent() or '(none set)'}")
    for agent, st in state.items():
        if isinstance(st, dict):
            print(f"{agent}: last_run={st.get('last_run', 'never')}, "
                  f"done={len(st.get('done_sessions', []))}")
    print(f"Queue: {len(queued)} cards pending, {archived} archived")
    for card in queued[:5]:
        print(f"  - {card.name}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--agent", choices=["claude-code"],
                    help="extract this agent's internal store into the queue")
    ap.add_argument("--source-dir", type=Path, help="override source directory")
    ap.add_argument("--purge-spam", action="store_true",
                    help="purge boilerplate jsonl-import sessions from agentmemory")
    ap.add_argument("--apply", action="store_true", help="actually delete (purge is dry-run by default)")
    ap.add_argument("--status", action="store_true", help="show state and queue")
    args = ap.parse_args()

    if args.status:
        status()
    elif args.purge_spam:
        purge_spam(args.apply)
    elif args.agent == "claude-code":
        ingest_claude_code(args.source_dir)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
