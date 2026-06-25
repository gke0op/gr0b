#!/usr/bin/env python3
"""
gr0b_link.py — the corpus callosum (DR-003 §3.2).

Scans vault markdown (decisions/, ingest-queue/, …) for code mentions,
resolves them EXACTLY against the graphify export, and writes a managed
`gr0b_*` frontmatter block. Ambiguous mentions are recorded, never guessed.

Usage (host):
    python3 ~/.gr0b/scripts/gr0b_link.py                  # dry-run, default dirs
    python3 ~/.gr0b/scripts/gr0b_link.py --apply          # write frontmatter
    python3 ~/.gr0b/scripts/gr0b_link.py --apply FILE.md  # single file
    python3 ~/.gr0b/scripts/gr0b_link.py --report         # JSON summary (harness)

Options:
    --graph PATH   graphify export (default ~/Desktop/graphify-out/graph.json)

Idempotent: re-running replaces only the managed gr0b_* keys; all other
frontmatter and body text is preserved byte-for-byte.
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from gr0b_graphlib import (  # noqa: E402
    DEFAULT_GRAPH, Graph, GraphSchemaError, is_noise_label, load_graph,
)

VAULT = Path.home() / ".gr0b"
DEFAULT_TARGETS = [VAULT / "decisions", VAULT / "ingest-queue"]

CODE_EXTS = (r"py|js|jsx|ts|tsx|zig|c|h|hpp|cpp|rs|go|md|yaml|yml|json|toml|"
             r"sh|ps1|sql|html|css|ipynb|mjs|cjs")

RE_CODE_SPAN = re.compile(r"`([^`\n]{2,120})`")
RE_PATH      = re.compile(rf"\b[\w][\w./-]*\.(?:{CODE_EXTS})\b")
RE_CALL      = re.compile(r"\b\.?[a-z_][a-z0-9_]{2,}\(\)")
RE_CAMEL     = re.compile(r"\b[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+\b")

# English/agent words that pass the CamelCase test but are never code anchors.
MENTION_STOPWORDS = {
    "readme", "todo", "claude", "gemini", "codex", "cursor", "github",
    "openai", "anthropic", "macos", "javascript", "typescript", "python",
    "obsidian", "graphify", "agentmemory", "cowork", "telegram", "binance",
    "polymarket", "playwright", "mcp", "api", "cli", "gpu", "json", "yaml",
}

MANAGED_KEYS = ("gr0b_nodes", "gr0b_ambiguous", "gr0b_unresolved", "gr0b_linked_at")


def _too_generic(mention: str) -> bool:
    """Field-test lesson (2026-06-12): bare common words (`nodes`, `window`,
    `report()`, `after()`) resolved to accidental unique labels — false
    memories. A bare lowercase token with no structural character (._-/) and
    length ≤ 8 is too generic to link. Method syntax (leading dot) is an
    intentional reference and stays; ambiguity handling protects it."""
    if mention.startswith("."):
        return False
    bare = mention[:-2] if mention.endswith("()") else mention
    if any(c in bare for c in "._-/"):
        return False
    return bare.islower() and len(bare) <= 8


# ── Mention extraction ────────────────────────────────────────────────────────
def extract_mentions(text: str) -> tuple[list, list]:
    """Returns (mentions, path_hints). Conservative by design: backtick spans,
    path-looking tokens, call-looking tokens, multi-hump CamelCase."""
    mentions: dict[str, None] = {}   # ordered set
    hints: dict[str, None] = {}

    def consider(raw: str):
        m = raw.strip().strip(",.;:!?")
        if not m or len(m) > 120 or " " in m:
            return
        if m.lower().strip("._()") in MENTION_STOPWORDS:
            return
        if is_noise_label(m) or _too_generic(m):
            return
        if "/" in m or RE_PATH.fullmatch(m):
            hints[m] = None
        mentions[m] = None

    for span in RE_CODE_SPAN.findall(text):
        # A span may hold a path, a symbol, or junk; consider it whole.
        consider(span)
    body_no_spans = RE_CODE_SPAN.sub(" ", text)
    for rx in (RE_PATH, RE_CALL, RE_CAMEL):
        for tok in rx.findall(body_no_spans):
            consider(tok)
    return list(mentions), list(hints)


# ── Per-file linking ──────────────────────────────────────────────────────────
@dataclass
class FileResult:
    path: Path
    linked: list = field(default_factory=list)       # [(node_id, mention, tier)]
    ambiguous: list = field(default_factory=list)    # [(mention, n_candidates)]
    unresolved: int = 0

    @property
    def touched(self) -> bool:
        return bool(self.linked or self.ambiguous)


def link_file(path: Path, graph: Graph, apply: bool = False) -> FileResult:
    text = path.read_text(encoding="utf-8", errors="replace")
    body = _strip_frontmatter(text)[1]
    mentions, hints = extract_mentions(body)

    fr = FileResult(path=path)
    seen_ids = set()
    for m in mentions:
        r = graph.resolve(m, path_hints=tuple(h for h in hints if h != m))
        if r.linked:
            if r.linked.id not in seen_ids:
                seen_ids.add(r.linked.id)
                fr.linked.append((r.linked.id, m, r.tier))
        elif r.ambiguous:
            fr.ambiguous.append((m, len(r.candidates)))
        else:
            fr.unresolved += 1

    if apply:
        path.write_text(_write_managed_block(text, fr), encoding="utf-8")
    return fr


# ── Frontmatter handling (no yaml dep; we manage only our own keys) ──────────
def _strip_frontmatter(text: str) -> tuple[str, str]:
    """Returns (frontmatter_inner or '', body). Tolerates missing frontmatter."""
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end != -1:
            inner = text[4:end + 1]
            body = text[end + 4:]
            if body.startswith("\n"):
                body = body[1:]
            return inner, body
    return "", text


def _purge_managed(inner: str) -> str:
    """Remove existing managed keys (and their indented list items)."""
    out, skipping = [], False
    for line in inner.splitlines():
        if any(line.startswith(k + ":") for k in MANAGED_KEYS):
            skipping = True
            continue
        if skipping and (line.startswith("  ") or line.startswith("- ")
                         or line.startswith("\t")):
            continue
        skipping = False
        out.append(line)
    return "\n".join(out).strip("\n")


def _managed_lines(fr: FileResult) -> str:
    lines = []
    if fr.linked:
        lines.append("gr0b_nodes:")
        for nid, mention, tier in fr.linked:
            lines.append(f"  - {nid}    # {mention} ({tier})")
    if fr.ambiguous:
        lines.append("gr0b_ambiguous:")
        for mention, n in fr.ambiguous:
            lines.append(f"  - \"{mention}\"    # {n} candidates — needs path qualifier")
    lines.append(f"gr0b_linked_at: {date.today().isoformat()}")
    return "\n".join(lines)


def _write_managed_block(text: str, fr: FileResult) -> str:
    inner, body = _strip_frontmatter(text)
    kept = _purge_managed(inner)
    managed = _managed_lines(fr)
    new_inner = (kept + "\n" + managed).strip("\n")
    return f"---\n{new_inner}\n---\n\n{body.lstrip(chr(10))}"


# ── CLI ───────────────────────────────────────────────────────────────────────
def main(argv: list) -> int:
    apply = "--apply" in argv
    report = "--report" in argv
    graph_path = DEFAULT_GRAPH
    if "--graph" in argv:
        graph_path = Path(argv[argv.index("--graph") + 1])
    targets = [Path(a) for a in argv
               if not a.startswith("--") and a != str(graph_path)]
    targets = targets or DEFAULT_TARGETS

    try:
        graph = load_graph(graph_path)
    except GraphSchemaError as e:
        print(f"GRAPH ERROR — refusing to link against a broken map:\n{e}")
        return 4
    if not graph.edges:
        print("GRAPH HAS 0 EDGES — stale/edge-less export. Refusing: links made "
              "against a roadless map are unverifiable. Run --probe first.")
        return 3

    files: list[Path] = []
    ignored: list[str] = []
    for t in targets:
        if t.is_dir():
            files += sorted(t.glob("*.md"))
        elif t.suffix == ".md" and t.exists():
            files.append(t)
        else:
            ignored.append(str(t))

    if ignored:
        print("⚠️  ignored args (not a directory or existing .md): "
              + ", ".join(ignored))
        print("   zsh note: interactive zsh passes '# comment' text as "
              "arguments — re-run without trailing comments.\n")
    if not files:
        print("NO FILES TO LINK — nothing matched the targets. Refusing to "
              "report success on an empty run (silent no-ops are how the "
              "roadless map shipped).")
        return 2

    results = [link_file(f, graph, apply=apply) for f in files]

    if report:
        print(json.dumps({
            "graph": {"nodes": len(graph.nodes), "edges": len(graph.edges)},
            "files": len(results),
            "files_linked": sum(1 for r in results if r.linked),
            "links": sum(len(r.linked) for r in results),
            "ambiguous": sum(len(r.ambiguous) for r in results),
            "unresolved": sum(r.unresolved for r in results),
            "applied": apply,
        }, indent=2))
        return 0

    mode = "APPLIED" if apply else "DRY-RUN (use --apply to write)"
    print(f"gr0b_link — {mode} · graph: {len(graph.nodes):,}n/{len(graph.edges):,}e\n")
    for r in results:
        if not r.touched:
            continue
        print(f"  {r.path.name}")
        for nid, mention, tier in r.linked:
            print(f"    ✓ {mention}  →  {nid}  [{tier}]")
        for mention, n in r.ambiguous:
            print(f"    ? {mention}  — {n} candidates, not linked")
    print(f"\n{sum(len(r.linked) for r in results)} links · "
          f"{sum(len(r.ambiguous) for r in results)} ambiguous · "
          f"{sum(r.unresolved for r in results)} unresolved "
          f"across {len(results)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
