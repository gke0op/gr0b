#!/usr/bin/env python3
"""
gr0b_reflect.py — the still.

Reads session logs across all agents and distils them into three insight files:

  ~/.gr0b/insights/open-threads.md        — aggregated next steps, aged and deduped
  ~/.gr0b/insights/recurring-failures.md  — patterns tried and abandoned repeatedly
  ~/.gr0b/insights/contradictions.md      — conflicting decisions, with attribution

Local-first: no LLM or API key required. Use --with-llm for a deeper semantic pass.

Usage:
    python3 ~/.gr0b/scripts/gr0b_reflect.py
    python3 ~/.gr0b/scripts/gr0b_reflect.py --days 60 --stale-after 7
    python3 ~/.gr0b/scripts/gr0b_reflect.py --with-llm [--model claude-3-5-haiku-20241022]

Runs automatically daily if installed via install.sh.
Re-run manually any time to refresh.
"""

import argparse
import hashlib
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

VAULT    = Path.home() / ".gr0b"
LOGS_DIR = VAULT / "session-logs"
INSIGHTS = VAULT / "insights"
AGENTS   = ["claude", "gemini", "codex"]

# Section header patterns — matches the standard session log template
SECTION_RE = {
    "worked_on": re.compile(r"^##\s+what was worked on", re.I),
    "decisions":  re.compile(r"^##\s+key decisions", re.I),
    "files":      re.compile(r"^##\s+files changed", re.I),
    "threads":    re.compile(r"^##\s+(open threads|next steps)", re.I),
}

# Stopwords excluded from n-gram fingerprints
STOPWORDS = {
    "a", "an", "the", "to", "and", "or", "but", "in", "on", "at", "is",
    "it", "of", "for", "with", "this", "that", "be", "are", "we", "i",
    "use", "used", "using", "need", "needs", "should", "will", "was",
    "from", "into", "as", "up", "out", "by",
}

# Assistant sign-off / filler phrases — never real threads or decisions.
# These are conversational theater that session logs inhale verbatim.
JUNK_RE = re.compile(
    r"(stand(ing)?\s+ready|await(ing)?\s+(the\s+)?(user|operator|gokce|next|further|instructions)"
    r"|assist\s+(the\s+)?(user|operator)|ready\s+(for|to)\s+(the\s+)?next"
    r"|fully\s+satisfied|no\s+further\s+(action|work|changes)"
    r"|session\s+(is\s+)?(complete|concluded|ended)"
    r"|next\s+request|anything\s+else|happy\s+to\s+(help|assist)"
    r"|peak\s+.{0,25}\bstate|optimal\b.{0,20}\bstate|mission\s+accomplished"
    r"|let\s+the\s+user\s+open|user\s+can\s+now\s+(open|see|enjoy))",
    re.I,
)

# Verb pairs that suggest contradiction between two decisions
CONTRADICTION_PAIRS = [
    (r"\buse\b",          r"\bavoid\b"),
    (r"\buse\b",          r"\breplace\b"),
    (r"\bkeep\b",         r"\bremove\b"),
    (r"\badd\b",          r"\bremove\b"),
    (r"\benable\b",       r"\bdisable\b"),
    (r"\bswitch to\b",    r"\bswitch from\b"),
    (r"\bdecided to\b",   r"\bdecided against\b"),
    (r"\bdo not\b",       r"\bshould\b"),
    (r"\bnever\b",        r"\balways\b"),
    (r"\bprefer\b",       r"\bavoid\b"),
    (r"\bmigrate\b",      r"\bstay with\b"),
    (r"\brefactor\b",     r"\bkeep as is\b"),
]


# ── Parsing ───────────────────────────────────────────────────────────────────

def parse_date(stem: str) -> datetime | None:
    """Extract datetime from a filename like 2025-05-01_14-32 or 2025-05-01 14:32."""
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})[_\sT](\d{2})[-:](\d{2})", stem)
    if not m:
        # Fallback: just the date
        m2 = re.search(r"(\d{4})-(\d{2})-(\d{2})", stem)
        if m2:
            try:
                return datetime(int(m2.group(1)), int(m2.group(2)), int(m2.group(3)))
            except ValueError:
                return None
        return None
    try:
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                        int(m.group(4)), int(m.group(5)))
    except ValueError:
        return None


def extract_bullets(raw_lines: list[str]) -> list[str]:
    """Strip markdown list markers and return non-empty, non-code bullets."""
    result = []
    for line in raw_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("```") or stripped.startswith("#"):
            continue
        # Strip list markers: -, *, •, numbered
        clean = re.sub(r"^(\d+\.\s+|[-*•]\s*)", "", stripped).strip()
        if clean and len(clean) > 4 and not JUNK_RE.search(clean):
            result.append(clean)
    return result


def parse_session(path: Path, agent: str) -> dict | None:
    """Parse one session log file into structured sections."""
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return None

    sections: dict[str, list[str]] = {k: [] for k in SECTION_RE}
    current = None

    for line in text.splitlines():
        matched = False
        for key, pattern in SECTION_RE.items():
            if pattern.match(line.strip()):
                current = key
                matched = True
                break
        if not matched:
            if line.strip().startswith("## "):
                current = None
            elif current:
                sections[current].append(line)

    return {
        "path":      path,
        "stem":      path.stem,
        "agent":     agent,
        "date":      parse_date(path.stem),
        "worked_on": extract_bullets(sections["worked_on"]),
        "decisions": extract_bullets(sections["decisions"]),
        "files":     extract_bullets(sections["files"]),
        "threads":   extract_bullets(sections["threads"]),
    }


def load_sessions(days: int) -> list[dict]:
    """Load all session logs from the past N days across all agents."""
    cutoff = datetime.now() - timedelta(days=days)
    sessions = []

    for agent in AGENTS:
        agent_dir = LOGS_DIR / agent
        if not agent_dir.is_dir():
            continue
        for path in agent_dir.glob("*.md"):
            s = parse_session(path, agent)
            if not s:
                continue
            date = s.get("date")
            if date and date < cutoff:
                continue
            sessions.append(s)

    sessions.sort(key=lambda s: s.get("date") or datetime.min)
    return sessions


# ── Wikilinks ─────────────────────────────────────────────────────────────────

def wikilink(stem: str) -> str:
    """Format a session log stem as an Obsidian wikilink: [[2026-04-28_14-32]]."""
    return f"[[{stem}]]"


def decision_wikilinks(decisions_dir: Path) -> dict[str, str]:
    """
    Return a map of ngram_key → [[DR-NNN]] for all decision records.
    Used to cross-link insight bullets to ADRs when topics overlap.
    """
    links = {}
    if not decisions_dir.exists():
        return links
    for path in decisions_dir.glob("DR-*.md"):
        # Extract id and title from frontmatter
        try:
            text = path.read_text()
        except OSError:
            continue
        m_id    = re.search(r"^id:\s*(\S+)",    text, re.M)
        m_title = re.search(r'^title:\s*"?(.+?)"?\s*$', text, re.M)
        if m_id and m_title:
            dr_id  = m_id.group(1).strip()
            title  = m_title.group(1).strip().strip('"')
            key    = ngram_key(title, n=4)
            if key:
                links[key] = f"[[{dr_id}]]"
    return links


# ── Text utilities ────────────────────────────────────────────────────────────

def normalize(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    text = re.sub(r"[`'\"]", "", text.lower())
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def content_words(text: str) -> list[str]:
    return [w for w in normalize(text).split() if w not in STOPWORDS and len(w) > 2]


def ngram_key(text: str, n: int = 5) -> str:
    """First N content words as a grouping key."""
    return " ".join(content_words(text)[:n])


def fp(text: str) -> str:
    """Short hash of normalized text."""
    return hashlib.md5(normalize(text).encode()).hexdigest()[:8]


def shared_content(a: str, b: str) -> int:
    """Count shared content words between two strings."""
    return len(set(content_words(a)) & set(content_words(b)))


def dedupe_burst(items: list[dict]) -> list[dict]:
    """Collapse near-duplicate bullets logged repeatedly on the same day.

    A single work-burst often gets written to several session logs minutes
    apart (restarts, checkpoint saves). Identical text on the same calendar
    day counts ONCE — recurrence should mean 'came back on another day',
    not 'was logged six times in 23 minutes'.
    """
    seen: set[tuple[str, str]] = set()
    out = []
    for item in items:
        day = item["date"].strftime("%Y-%m-%d") if item.get("date") else ""
        key = (fp(item["text"]), day)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


# ── Open threads ──────────────────────────────────────────────────────────────

def build_open_threads(sessions: list[dict], stale_after: int) -> str:
    """
    Group 'open threads / next steps' bullets by topic similarity.
    Show recurrence count, staleness, and which agents raised them.
    """
    now = datetime.now()
    stale_cutoff = now - timedelta(days=stale_after)

    # Cluster by ngram key
    clusters: dict[str, list[dict]] = defaultdict(list)
    for s in sessions:
        for thread in s["threads"]:
            key = ngram_key(thread)
            if not key:
                continue
            clusters[key].append({
                "text":  thread,
                "agent": s["agent"],
                "date":  s.get("date"),
                "stem":  s.get("stem", ""),
            })

    if not clusters:
        return "_No open threads found in the analysed session logs._\n"

    # Collapse same-day duplicate logging before counting recurrence
    deduped = [dedupe_burst(v) for v in clusters.values()]

    # Sort: most recurring first, then most recent
    def sort_key(items):
        latest = max((i["date"] for i in items if i["date"]), default=datetime.min)
        return (-len(items), -(latest.timestamp() if latest else 0))

    sorted_clusters = sorted(deduped, key=sort_key)
    lines = []
    stale_count = 0

    for items in sorted_clusters:
        rep     = max(items, key=lambda i: len(i["text"]))["text"]
        agents  = sorted(set(i["agent"] for i in items))
        dates   = sorted(i["date"] for i in items if i["date"])
        count   = len(items)
        oldest  = dates[0]  if dates else None
        latest  = dates[-1] if dates else None

        is_stale = oldest and oldest < stale_cutoff
        if is_stale:
            stale_count += 1

        flags = []
        if count > 1:
            flags.append(f"{count}× seen")
        if is_stale and oldest:
            flags.append(f"stale — {(now - oldest).days}d old")
        elif oldest:
            flags.append(f"{(now - oldest).days}d old")
        flags.append(f"{'·'.join(agents)}")

        # Build source wikilinks (deduplicated, chronological)
        seen_stems: set[str] = set()
        source_links = []
        for item in sorted(items, key=lambda i: i.get("date") or datetime.min):
            stem = item.get("stem", "")
            if stem and stem not in seen_stems:
                seen_stems.add(stem)
                source_links.append(wikilink(stem))

        stale_prefix = "🔴 " if is_stale else ""
        lines.append(f"- {stale_prefix}{rep}")
        lines.append(f"  _({', '.join(flags)})_")
        if source_links:
            lines.append(f"  _Sources: {' · '.join(source_links)}_")

    summary_parts = [f"{len(sorted_clusters)} threads"]
    if stale_count:
        summary_parts.append(f"{stale_count} stale (>{stale_after}d)")
    recurring = sum(1 for c in sorted_clusters if len(c) > 1)
    if recurring:
        summary_parts.append(f"{recurring} recurring across sessions")

    return f"> {' · '.join(summary_parts)}\n\n" + "\n".join(lines) + "\n"


# ── Recurring failures ────────────────────────────────────────────────────────

def build_recurring_failures(sessions: list[dict]) -> str:
    """
    Surface threads unresolved across 3+ sessions and decisions revisited
    across 2+ sessions — signs of repeated dead-ends or drifting choices.
    """
    # Threads appearing 3+ times = persistently unresolved
    thread_clusters: dict[str, list[dict]] = defaultdict(list)
    for s in sessions:
        for t in s["threads"]:
            key = ngram_key(t)
            if key:
                thread_clusters[key].append({
                    "text": t, "agent": s["agent"],
                    "date": s.get("date"), "stem": s.get("stem", ""),
                })
    persistent = {k: dv for k, v in thread_clusters.items()
                  if len(dv := dedupe_burst(v)) >= 3}

    # Decisions with same subject appearing in 2+ sessions = potentially revisited
    decision_clusters: dict[str, list[dict]] = defaultdict(list)
    for s in sessions:
        for d in s["decisions"]:
            key = ngram_key(d, n=3)
            if key:
                decision_clusters[key].append({
                    "text": d, "agent": s["agent"],
                    "date": s.get("date"), "stem": s.get("stem", ""),
                })
    revisited = {k: dv for k, v in decision_clusters.items()
                 if len(dv := dedupe_burst(v)) >= 2}

    if not persistent and not revisited:
        return "_No recurring failures detected. Sessions sampled: " + str(len(sessions)) + "._\n"

    sections = []

    if persistent:
        lines = ["## Persistently unresolved threads\n",
                 "_Appeared in 3 or more sessions without being closed._\n"]
        for key, items in sorted(persistent.items(), key=lambda x: -len(x[1])):
            rep    = max(items, key=lambda i: len(i["text"]))["text"]
            agents = sorted(set(i["agent"] for i in items))
            dates  = sorted(i["date"] for i in items if i["date"])
            span   = (dates[-1] - dates[0]).days if len(dates) > 1 else 0
            seen_stems: set[str] = set()
            source_links = []
            for item in sorted(items, key=lambda i: i.get("date") or datetime.min):
                stem = item.get("stem", "")
                if stem and stem not in seen_stems:
                    seen_stems.add(stem)
                    source_links.append(wikilink(stem))
            lines.append(f"- **{rep}**")
            lines.append(f"  {len(items)} sessions · {', '.join(agents)}"
                         + (f" · over {span} days" if span else ""))
            if source_links:
                lines.append(f"  {' · '.join(source_links)}")
        sections.append("\n".join(lines))

    if revisited:
        lines = ["## Revisited decisions\n",
                 "_The same topic was decided multiple times — possible reversal or drift._\n"]
        for key, items in sorted(revisited.items(), key=lambda x: -len(x[1])):
            lines.append(f"- **Topic:** `{key}`")
            for item in sorted(items, key=lambda i: i.get("date") or datetime.min):
                d    = item["date"].strftime("%Y-%m-%d") if item["date"] else "?"
                stem = item.get("stem", "")
                ref  = wikilink(stem) if stem else d
                lines.append(f"  - [{ref} · {item['agent']}] {item['text']}")
        sections.append("\n".join(lines))

    return "\n\n".join(sections) + "\n"


# ── Contradictions ────────────────────────────────────────────────────────────

def build_contradictions(sessions: list[dict]) -> str:
    """
    Find decision bullets from different sessions that potentially contradict.
    Heuristic: opposing verbs + shared content words (≥2).
    Does not resolve contradictions — surfaces them for human review.
    """
    # Collect all decisions with metadata
    all_decisions = []
    for s in sessions:
        for d in s["decisions"]:
            all_decisions.append({
                "text":  d,
                "norm":  normalize(d),
                "agent": s["agent"],
                "date":  s.get("date"),
                "stem":  s.get("stem", ""),
            })

    contradictions = []
    seen = set()

    for i, a in enumerate(all_decisions):
        for j, b in enumerate(all_decisions):
            if j <= i:
                continue
            # Skip same session
            if a["agent"] == b["agent"] and a["date"] == b["date"]:
                continue

            pair_key = tuple(sorted([fp(a["text"]), fp(b["text"])]))
            if pair_key in seen:
                continue

            # Require substantial topical overlap — 2 shared words pairs
            # unrelated statements; 4 means they discuss the same thing.
            if shared_content(a["text"], b["text"]) < 4:
                continue

            for pat_a, pat_b in CONTRADICTION_PAIRS:
                a_has_a = bool(re.search(pat_a, a["norm"]))
                b_has_b = bool(re.search(pat_b, b["norm"]))
                a_has_b = bool(re.search(pat_b, a["norm"]))
                b_has_a = bool(re.search(pat_a, b["norm"]))

                if (a_has_a and b_has_b) or (a_has_b and b_has_a):
                    contradictions.append((a, b))
                    seen.add(pair_key)
                    break

    if not contradictions:
        return "_No contradictions detected in the analysed sessions._\n"

    lines = [f"> {len(contradictions)} potential contradiction(s) — review and resolve\n"]

    for a, b in contradictions:
        a_ref = wikilink(a["stem"]) if a.get("stem") else (a["date"].strftime("%Y-%m-%d") if a["date"] else "?")
        b_ref = wikilink(b["stem"]) if b.get("stem") else (b["date"].strftime("%Y-%m-%d") if b["date"] else "?")
        lines += [
            "---\n",
            f"- **{a_ref} · {a['agent']}** — {a['text']}",
            f"- **{b_ref} · {b['agent']}** — {b['text']}",
            "",
        ]

    return "\n".join(lines)


# ── LLM pass (optional) ───────────────────────────────────────────────────────

def llm_reflect(sessions: list[dict], args, header: str) -> None:
    """Deeper semantic pass using an Anthropic model. Requires: pip install anthropic."""
    try:
        import anthropic
    except ImportError:
        print("  anthropic package not installed — run: pip install anthropic --break-system-packages")
        return

    client = anthropic.Anthropic()

    # Build compact digest capped at 20 most recent sessions
    digest_parts = []
    for s in sessions[-20:]:
        date_str = s["date"].strftime("%Y-%m-%d") if s["date"] else "unknown"
        parts = [f"[{date_str} · {s['agent']}]"]
        if s["decisions"]:
            parts.append("Decisions: " + "; ".join(s["decisions"]))
        if s["threads"]:
            parts.append("Threads: " + "; ".join(s["threads"]))
        digest_parts.append("\n".join(parts))

    digest = "\n\n".join(digest_parts)

    prompt = (
        "You are reviewing session logs from AI coding agents working on the same codebase.\n"
        "Find genuine contradictions, recurring failures, and important patterns that "
        "rule-based heuristics may have missed.\n\n"
        f"Session digest ({len(digest_parts)} most recent sessions):\n\n"
        f"{digest}\n\n"
        "Return ONLY a JSON object with three keys:\n"
        '- "contradictions": list of {"a": str, "b": str, "reason": str}\n'
        '- "recurring_failures": list of {"pattern": str, "evidence": str}\n'
        '- "insights": list of strings (other notable observations)\n'
    )

    try:
        response = client.messages.create(
            model=args.model,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text
    except Exception as e:
        print(f"  LLM call failed: {e}")
        return

    import json
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Try to extract JSON block
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group())
            except json.JSONDecodeError:
                data = {}
        else:
            data = {}

    if not data:
        (INSIGHTS / "llm-raw.md").write_text(f"# LLM Reflection (raw)\n\n{header}{raw}")
        print(f"  → {INSIGHTS}/llm-raw.md  (could not parse as JSON)")
        return

    lines = [f"# LLM Reflection\n\n{header}"]

    if data.get("contradictions"):
        lines.append("## Contradictions\n")
        for c in data["contradictions"]:
            lines += [
                f"- **A:** {c.get('a', '')}",
                f"  **B:** {c.get('b', '')}",
                f"  _{c.get('reason', '')}_\n",
            ]

    if data.get("recurring_failures"):
        lines.append("## Recurring failures\n")
        for f in data["recurring_failures"]:
            lines += [
                f"- **{f.get('pattern', '')}**",
                f"  {f.get('evidence', '')}",
            ]
        lines.append("")

    if data.get("insights"):
        lines.append("## Additional insights\n")
        for insight in data["insights"]:
            lines.append(f"- {insight}")

    out = INSIGHTS / "llm-reflection.md"
    out.write_text("\n".join(lines))
    print(f"  → {out}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--days", type=int, default=90,
        help="analyse logs from the past N days (default: 90)",
    )
    parser.add_argument(
        "--stale-after", type=int, default=14,
        help="flag open threads older than N days as stale (default: 14)",
    )
    parser.add_argument(
        "--with-llm", action="store_true",
        help="run a deeper semantic pass with an LLM (requires ANTHROPIC_API_KEY)",
    )
    parser.add_argument(
        "--model", default="claude-3-5-haiku-20241022",
        help="model to use with --with-llm (default: claude-3-5-haiku-20241022)",
    )
    args = parser.parse_args()

    if not LOGS_DIR.exists():
        print(f"ERROR: session-logs not found at {LOGS_DIR}")
        print("Install gr0b first: https://github.com/gke0op/gr0b")
        sys.exit(1)

    print(f"Loading session logs (past {args.days} days) …", flush=True)
    sessions = load_sessions(days=args.days)

    if not sessions:
        print("No session logs found in the analysis window.")
        print(f"Write some sessions to {LOGS_DIR}/<agent>/ first.")
        sys.exit(0)

    n_threads   = sum(len(s["threads"])   for s in sessions)
    n_decisions = sum(len(s["decisions"]) for s in sessions)
    print(f"  {len(sessions)} sessions · {n_threads} threads · {n_decisions} decisions")

    INSIGHTS.mkdir(parents=True, exist_ok=True)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    header  = (
        f"_Generated {now_str} · {len(sessions)} sessions analysed "
        f"(past {args.days}d). "
        f"Re-run: `python3 ~/.gr0b/scripts/gr0b_reflect.py`_\n\n---\n\n"
    )

    # open-threads.md
    print("Extracting open threads …", flush=True)
    (INSIGHTS / "open-threads.md").write_text(
        f"# Open Threads\n\n{header}"
        + build_open_threads(sessions, stale_after=args.stale_after)
    )
    print(f"  → {INSIGHTS}/open-threads.md")

    # recurring-failures.md
    print("Finding recurring failures …", flush=True)
    (INSIGHTS / "recurring-failures.md").write_text(
        f"# Recurring Failures\n\n{header}"
        + build_recurring_failures(sessions)
    )
    print(f"  → {INSIGHTS}/recurring-failures.md")

    # contradictions.md
    print("Surfacing contradictions …", flush=True)
    (INSIGHTS / "contradictions.md").write_text(
        f"# Contradictions\n\n{header}"
        + build_contradictions(sessions)
    )
    print(f"  → {INSIGHTS}/contradictions.md")

    # optional LLM pass
    if args.with_llm:
        print(f"\nRunning LLM pass ({args.model}) …", flush=True)
        llm_reflect(sessions, args, header)

    print(f"\nDone. Insights written to {INSIGHTS}/")


if __name__ == "__main__":
    main()
