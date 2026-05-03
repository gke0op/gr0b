#!/usr/bin/env python3
"""
gr0b_decisions.py — decision records as first-class objects.

Architectural choices live in ~/.gr0b/decisions/ as lightweight ADRs.
Decisions are never deleted — only superseded, with a forward link to the
record that replaced them. This makes cognitive history version-controlled.

Commands:
    new        Create a new decision record (interactive or via flags)
    list       List all decisions with status
    show ID    Show the full content of a decision (e.g. DR-001)
    search Q   Search decision titles and content
    supersede  Mark a decision as superseded by a newer one

Usage:
    python3 ~/.gr0b/scripts/gr0b_decisions.py new
    python3 ~/.gr0b/scripts/gr0b_decisions.py new --title "Use Redis" --decision "..."
    python3 ~/.gr0b/scripts/gr0b_decisions.py list
    python3 ~/.gr0b/scripts/gr0b_decisions.py list --status accepted
    python3 ~/.gr0b/scripts/gr0b_decisions.py show DR-001
    python3 ~/.gr0b/scripts/gr0b_decisions.py search "session storage"
    python3 ~/.gr0b/scripts/gr0b_decisions.py supersede DR-001 --by DR-003 --reason "..."
"""

import argparse
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from textwrap import dedent, fill

VAULT      = Path.home() / ".gr0b"
DECISIONS  = VAULT / "decisions"
DATE_FMT   = "%Y-%m-%d"
STATUSES   = ("proposed", "accepted", "superseded")
ID_RE      = re.compile(r"^DR-(\d+)", re.IGNORECASE)

# ── ANSI colours (suppressed when not a TTY) ──────────────────────────────────
_tty = sys.stdout.isatty()

def _c(code, text):  return f"\033[{code}m{text}\033[0m" if _tty else text
def bold(t):         return _c("1", t)
def green(t):        return _c("32", t)
def yellow(t):       return _c("33", t)
def cyan(t):         return _c("36", t)
def red(t):          return _c("31", t)
def dim(t):          return _c("2", t)


# ── File format ───────────────────────────────────────────────────────────────

def _slug(title: str) -> str:
    """Convert title to a URL-safe slug."""
    s = title.lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s).strip("-")
    return s[:60]


def _next_id() -> str:
    """Return the next sequential DR-NNN id."""
    DECISIONS.mkdir(parents=True, exist_ok=True)
    existing = []
    for f in DECISIONS.glob("DR-*.md"):
        m = ID_RE.match(f.stem)
        if m:
            existing.append(int(m.group(1)))
    n = max(existing, default=0) + 1
    return f"DR-{n:03d}"


def _filename(dr_id: str, title: str) -> str:
    return f"{dr_id}-{_slug(title)}.md"


def _write_record(dr_id: str, title: str, status: str, context: str,
                  decision: str, consequences: str, agent: str,
                  tags: list[str], superseded_by: str = "") -> Path:
    """Write a decision record file and return its path."""
    DECISIONS.mkdir(parents=True, exist_ok=True)
    date     = datetime.now().strftime(DATE_FMT)
    tags_str = ", ".join(tags) if tags else ""
    sup_str  = superseded_by or ""

    content = dedent(f"""\
        ---
        id: {dr_id}
        title: "{title}"
        status: {status}
        date: {date}
        agent: {agent}
        tags: [{tags_str}]
        superseded-by: {sup_str}
        ---

        ## Context

        {context}

        ## Decision

        {decision}

        ## Consequences

        {consequences}
    """)

    path = DECISIONS / _filename(dr_id, title)
    path.write_text(content)
    return path


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """
    Parse YAML-lite frontmatter from a decision record.
    Returns (fields_dict, body_text).
    """
    if not text.startswith("---"):
        return {}, text

    end = text.find("\n---", 3)
    if end == -1:
        return {}, text

    fm_text = text[3:end].strip()
    body    = text[end + 4:].strip()

    fields: dict[str, str] = {}
    for line in fm_text.splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            fields[key.strip()] = val.strip().strip('"')

    return fields, body


def _load_all() -> list[dict]:
    """Load all decision records, sorted by ID."""
    DECISIONS.mkdir(parents=True, exist_ok=True)
    records = []
    for path in sorted(DECISIONS.glob("DR-*.md")):
        try:
            text = path.read_text()
        except OSError:
            continue
        fm, body = _parse_frontmatter(text)
        if not fm.get("id"):
            continue
        records.append({**fm, "_path": path, "_body": body, "_text": text})
    records.sort(key=lambda r: int(r.get("id", "DR-0").split("-")[1] or "0"))
    return records


def _find(dr_id: str) -> dict | None:
    """Find a record by its DR-NNN id (case-insensitive)."""
    target = dr_id.upper()
    for rec in _load_all():
        if rec.get("id", "").upper() == target:
            return rec
    return None


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_new(args) -> None:
    agent = os.environ.get("GR0B_AGENT", "unknown")

    def prompt(label: str, default: str = "", multiline: bool = False) -> str:
        if multiline:
            print(f"{cyan(label)} (end with a line containing only '.')")
            lines = []
            while True:
                line = input()
                if line.strip() == ".":
                    break
                lines.append(line)
            return "\n".join(lines).strip() or default
        val = input(f"{cyan(label)}: ").strip()
        return val or default

    # Non-interactive path: all required args provided via flags
    if args.title and args.decision:
        title        = args.title
        status       = args.status or "accepted"
        context      = args.context or "(no context provided)"
        decision     = args.decision
        consequences = args.consequences or "(no consequences documented)"
        agent_       = args.agent or agent
        tags         = [t.strip() for t in args.tags.split(",")] if args.tags else []
    else:
        # Interactive path
        print(f"\n{bold('New decision record')}\n")
        title        = args.title or prompt("Title")
        if not title:
            print(red("Title is required."))
            sys.exit(1)
        status       = args.status or prompt("Status [proposed/accepted/superseded]", "accepted")
        if status not in STATUSES:
            status = "accepted"
        context      = args.context      or prompt("Context (why this decision was needed)", multiline=True)
        decision     = args.decision     or prompt("Decision (what was decided)", multiline=True)
        consequences = args.consequences or prompt("Consequences (trade-offs, follow-ups)", multiline=True)
        agent_       = args.agent or prompt("Agent", agent)
        tags_raw     = args.tags  or prompt("Tags (comma-separated, optional)", "")
        tags         = [t.strip() for t in tags_raw.split(",") if t.strip()]

    dr_id = _next_id()
    path  = _write_record(
        dr_id=dr_id, title=title, status=status,
        context=context, decision=decision, consequences=consequences,
        agent=agent_, tags=tags,
    )
    print(green(f"\n  {dr_id} written → {path}"))


def cmd_list(args) -> None:
    records = _load_all()
    if not records:
        print(dim("  No decision records found."))
        print(dim(f"  Create one: python3 ~/.gr0b/scripts/gr0b_decisions.py new"))
        return

    status_filter = args.status.lower() if args.status else None

    STATUS_COLOUR = {
        "accepted":   green,
        "proposed":   yellow,
        "superseded": dim,
    }

    count = 0
    for rec in records:
        status = rec.get("status", "?")
        if status_filter and status != status_filter:
            continue
        colour   = STATUS_COLOUR.get(status, lambda x: x)
        dr_id    = rec.get("id", "?")
        title    = rec.get("title", "(untitled)")
        date     = rec.get("date", "?")
        agent    = rec.get("agent", "?")
        sup      = rec.get("superseded-by", "")
        sup_note = f"  → {sup}" if sup else ""
        print(f"  {colour(dr_id)}  {colour(status):<12}  {dim(date)}  {title}{dim(sup_note)}")
        count += 1

    if count == 0 and status_filter:
        print(dim(f"  No {status_filter} decisions found."))
    else:
        by_status = {}
        for r in records:
            s = r.get("status", "?")
            by_status[s] = by_status.get(s, 0) + 1
        summary = "  ".join(f"{v} {k}" for k, v in sorted(by_status.items()))
        print(dim(f"\n  {summary}"))


def cmd_show(args) -> None:
    dr_id = args.id.upper()
    if not dr_id.startswith("DR-"):
        dr_id = "DR-" + dr_id

    rec = _find(dr_id)
    if not rec:
        print(red(f"  {dr_id} not found."))
        sys.exit(1)

    STATUS_COLOUR = {"accepted": green, "proposed": yellow, "superseded": dim}
    colour = STATUS_COLOUR.get(rec.get("status", ""), lambda x: x)

    print()
    print(bold(f"  {rec.get('id')}  {rec.get('title')}"))
    print(f"  {colour(rec.get('status', '?'))}  ·  {dim(rec.get('date', '?'))}  ·  {dim(rec.get('agent', '?'))}")
    if rec.get("tags", "[]") not in ("[]", ""):
        print(f"  tags: {rec.get('tags')}")
    sup = rec.get("superseded-by", "")
    if sup:
        print(yellow(f"  ⚠  Superseded by {sup}"))
    print()
    print(rec.get("_body", ""))


def cmd_search(args) -> None:
    query   = " ".join(args.query).lower()
    records = _load_all()

    results = []
    for rec in records:
        text = (rec.get("title", "") + " " + rec.get("_body", "")).lower()
        if query in text:
            results.append(rec)

    if not results:
        print(dim(f"  No decisions match '{query}'."))
        return

    print(dim(f"\n  {len(results)} result(s) for '{query}'\n"))
    STATUS_COLOUR = {"accepted": green, "proposed": yellow, "superseded": dim}
    for rec in results:
        colour = STATUS_COLOUR.get(rec.get("status", ""), lambda x: x)
        dr_id  = rec.get("id", "?")
        title  = rec.get("title", "?")
        status = rec.get("status", "?")
        date   = rec.get("date", "?")

        # Find snippet of matching context
        body  = rec.get("_body", "")
        idx   = body.lower().find(query)
        snip  = ""
        if idx != -1:
            start = max(0, idx - 40)
            end   = min(len(body), idx + 80)
            snip  = "…" + body[start:end].replace("\n", " ").strip() + "…"

        print(f"  {colour(dr_id)}  {colour(status):<12}  {dim(date)}  {title}")
        if snip:
            print(f"       {dim(snip)}")


def cmd_supersede(args) -> None:
    old_id = args.id.upper()
    if not old_id.startswith("DR-"):
        old_id = "DR-" + old_id

    old_rec = _find(old_id)
    if not old_rec:
        print(red(f"  {old_id} not found."))
        sys.exit(1)

    if old_rec.get("status") == "superseded":
        print(yellow(f"  {old_id} is already superseded by {old_rec.get('superseded-by', '?')}."))
        if not args.force:
            sys.exit(1)

    # Create the new record first (if title/decision provided)
    new_id = None
    if args.title and args.decision:
        agent = args.agent or os.environ.get("GR0B_AGENT", "unknown")
        new_id = _next_id()
        _write_record(
            dr_id=new_id, title=args.title, status="accepted",
            context=args.context or f"Supersedes {old_id}. {args.reason or ''}".strip(),
            decision=args.decision,
            consequences=args.consequences or "(document consequences here)",
            agent=agent, tags=[],
        )
        print(green(f"  {new_id} written"))
    elif args.by:
        new_id = args.by.upper()
        if not new_id.startswith("DR-"):
            new_id = "DR-" + new_id
        if not _find(new_id):
            print(red(f"  {new_id} not found — create it first or use --title + --decision."))
            sys.exit(1)

    if not new_id:
        print(red("  Provide --by DR-NNN (existing) or --title + --decision (new record)."))
        sys.exit(1)

    # Patch the old record: update status + superseded-by
    old_path  = old_rec["_path"]
    old_text  = old_path.read_text()
    reason    = args.reason or ""

    # Update frontmatter fields in the raw text
    old_text = re.sub(r"^status:.*$",        f"status: superseded",    old_text, flags=re.M)
    old_text = re.sub(r"^superseded-by:.*$", f"superseded-by: {new_id}", old_text, flags=re.M)

    # Append a supersession note to the body
    note = f"\n\n---\n\n**Superseded {datetime.now().strftime(DATE_FMT)} by {new_id}**"
    if reason:
        note += f" — {reason}"
    old_path.write_text(old_text.rstrip() + note + "\n")

    print(green(f"  {old_id} marked as superseded → {new_id}"))


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="gr0b_decisions",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")

    # new
    p_new = sub.add_parser("new", help="create a new decision record")
    p_new.add_argument("--title",        help="short decision title")
    p_new.add_argument("--status",       choices=STATUSES, default="accepted")
    p_new.add_argument("--context",      help="why this decision was needed")
    p_new.add_argument("--decision",     help="what was decided")
    p_new.add_argument("--consequences", help="trade-offs and follow-ups")
    p_new.add_argument("--agent",        help="agent name (defaults to GR0B_AGENT env var)")
    p_new.add_argument("--tags",         help="comma-separated tags")

    # list
    p_list = sub.add_parser("list", help="list all decision records")
    p_list.add_argument("--status", choices=STATUSES, help="filter by status")

    # show
    p_show = sub.add_parser("show", help="show a decision record in full")
    p_show.add_argument("id", help="record ID, e.g. DR-001 or 001")

    # search
    p_search = sub.add_parser("search", help="search decision records")
    p_search.add_argument("query", nargs="+", help="search terms")

    # supersede
    p_sup = sub.add_parser("supersede", help="mark a decision as superseded")
    p_sup.add_argument("id",            help="ID of the decision to supersede")
    p_sup.add_argument("--by",          help="ID of the decision that replaces it")
    p_sup.add_argument("--title",       help="title of the new decision (creates it)")
    p_sup.add_argument("--context",     help="context for the new decision")
    p_sup.add_argument("--decision",    help="what the new decision is")
    p_sup.add_argument("--consequences",help="consequences of the new decision")
    p_sup.add_argument("--agent",       help="agent writing the new decision")
    p_sup.add_argument("--reason",      help="brief reason for superseding")
    p_sup.add_argument("--force",       action="store_true",
                       help="allow superseding an already-superseded record")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    DECISIONS.mkdir(parents=True, exist_ok=True)

    dispatch = {
        "new":       cmd_new,
        "list":      cmd_list,
        "show":      cmd_show,
        "search":    cmd_search,
        "supersede": cmd_supersede,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
