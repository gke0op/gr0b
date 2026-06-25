#!/usr/bin/env python3
"""
gr0b_graphlib.py — shared, defensive loader + resolver for graphify exports.

Used by: gr0b_map.py, gr0b_link.py, gr0b_doctor.py, verify_phase3.py.
Pure stdlib. Never guesses: ambiguous resolution returns candidates, not a pick.

Probe an export's schema (run on host first, before anything else):
    python3 ~/.gr0b/scripts/gr0b_graphlib.py --probe [path/to/graph.json]

Design notes (DR-003):
- graphify's own lookup is fuzzy (get_node("Dispatch") returned an unrelated
  rationale node, verified live 2026-06-12). Resolution here is EXACT-match
  only, with path-hint disambiguation. A wrong link is a false memory.
- Export schemas drift between graphify versions; the loader maps known key
  variants and fails LOUDLY with a fingerprint on unknown shapes.
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_GRAPH = Path.home() / "Desktop" / "graphify-out" / "graph.json"

# ── Schema variant maps ───────────────────────────────────────────────────────
NODE_CONTAINER_KEYS = ("nodes", "vertices", "items")
EDGE_CONTAINER_KEYS = ("edges", "links", "relations")
NODE_ID_KEYS    = ("id", "node_id", "uid", "key")
NODE_LABEL_KEYS = ("label", "name", "title")
NODE_FILE_KEYS  = ("source_file", "src", "file", "path", "source")
NODE_TYPE_KEYS  = ("type", "kind", "node_type", "file_type")
NODE_NORM_KEYS  = ("norm_label", "normalized_label")
NODE_COMM_KEYS  = ("community", "cluster", "community_id")
EDGE_SRC_KEYS   = ("source", "src", "from", "u")
EDGE_DST_KEYS   = ("target", "dst", "to", "v")
EDGE_REL_KEYS   = ("relation", "context", "rel", "type", "label")
EDGE_CONF_KEYS  = ("confidence", "conf", "status")
EDGE_SCORE_KEYS = ("confidence_score", "score")
EDGE_WEIGHT_KEYS = ("weight",)

# ── Noise paths (single source of truth; gr0b_map.py imports this) ──────────
NOISE_PATH_PATTERNS = [
    (r"zig-macos-", "Zig toolchain (vendored)"),
    (r"zig-windows-", "Zig toolchain (vendored)"),
    (r"zig-linux-", "Zig toolchain (vendored)"),
    (r"\.zig-cache", "Zig build cache"),
    (r"zig-out/", "Zig build output"),
    (r"lib/std/", "Zig stdlib"),
    (r"lib/libc/", "Zig libc headers"),
    (r"lib/libcxx", "Zig libcxx headers"),
    (r"lib/libcxxabi", "Zig libcxxabi"),
    (r"lib/libunwind", "Zig libunwind"),
    (r"lib/compiler_rt", "Zig compiler-rt"),
    (r"lib/tsan", "Zig tsan runtime"),
    (r"/venv/|^venv/", "Python venv"),
    (r"site-packages/", "Python site-packages"),
    (r"__pycache__", "Python bytecode cache"),
    (r"\.egg-info", "Python egg-info"),
    (r"poly_scourge", "Bundler output"),
    (r"node_modules/", "node_modules"),
    (r"vendor/", "Vendor code"),
    (r"\.min\.", "Minified assets"),
    (r"dist/bundle", "Build output"),
]
_NOISE_PATH_RE = re.compile("|".join(p for p, _ in NOISE_PATH_PATTERNS),
                            re.IGNORECASE)


def is_noise_path(path: str) -> bool:
    """True for vendored/bundler/cache paths. Nodes living there are never
    valid link targets — junk must not create (or break) uniqueness."""
    return bool(path and _NOISE_PATH_RE.search(path.replace("\\", "/")))


# ── God-node / mention noise (DR-003 §3.6) ───────────────────────────────────
GOD_NODE_STOPLIST = {
    "json", "$()", "_()", "$", "_", "self", "this", "init", "main",
    "none", "true", "false", "null", "undefined", "error", "ok",
    "__init__()", "constructor()", "new()", "deinit()", "toString()",
}

def is_noise_label(label: str) -> bool:
    """Labels too generic to ever be a meaningful anchor."""
    if not label:
        return True
    l = label.strip()
    if l.lower() in GOD_NODE_STOPLIST:
        return True
    bare = l.strip("._()")
    if len(bare) <= 2:
        return True
    return False


class GraphSchemaError(RuntimeError):
    """Raised when an export's shape is unrecognizable. Carries a fingerprint."""


def _pick(d: dict, keys: tuple) -> object:
    for k in keys:
        if k in d:
            return d[k]
    return None


@dataclass
class Node:
    id: str
    label: str
    source_file: str = ""
    type: str = ""
    community: int = -1
    norm_label: str = ""


@dataclass
class Edge:
    source: str
    target: str
    relation: str = ""
    confidence: str = ""
    confidence_score: float = 0.0
    weight: float = 0.0


@dataclass
class ResolveResult:
    """Outcome of resolving one mention. linked is None unless EXACTLY one
    candidate survives — the never-guess rule lives here."""
    mention: str
    linked: Node | None = None
    tier: str = ""                      # file-path | unique-label | path-qualified
    candidates: list = field(default_factory=list)

    @property
    def ambiguous(self) -> bool:
        return self.linked is None and len(self.candidates) > 1


@dataclass
class Graph:
    nodes: dict = field(default_factory=dict)            # id -> Node
    edges: list = field(default_factory=list)            # [Edge]
    label_index: dict = field(default_factory=dict)      # exact label -> [ids]
    basename_index: dict = field(default_factory=dict)   # file basename -> [ids]
    norm_index: dict = field(default_factory=dict)       # norm_label -> [ids]
    schema: dict = field(default_factory=dict)
    path: str = ""

    # ── Resolution (the heart) ────────────────────────────────────────────────
    def resolve(self, mention: str, path_hints: tuple = ()) -> ResolveResult:
        mention = mention.strip()
        res = ResolveResult(mention=mention)
        if is_noise_label(mention):
            return res

        # Path-bearing mention (contains '/'): match source_file suffix.
        if "/" in mention:
            norm = mention.replace("\\", "/").lstrip("./")
            hits = [n for n in self.nodes.values()
                    if n.source_file.replace("\\", "/").endswith(norm)
                    and not is_noise_path(n.source_file)]
            # Prefer the file node itself over symbols defined in the file
            file_hits = [n for n in hits if n.label == Path(norm).name] or hits
            res.candidates = file_hits
            if len(file_hits) == 1:
                res.linked, res.tier = file_hits[0], "file-path"
            return res

        # Exact-label variants, tried in priority order (first with hits wins).
        variants = [mention]
        if not mention.endswith("()"):
            variants += [mention + "()", "." + mention + "()"]
        elif not mention.startswith("."):
            variants += ["." + mention]

        cands: list = []
        for v in variants:
            ids = self.label_index.get(v, [])
            if ids:
                cands = [self.nodes[i] for i in ids]
                break

        # Filename mention without path → basename index.
        if not cands and _looks_like_filename(mention):
            cands = [self.nodes[i] for i in self.basename_index.get(mention, [])]

        # Last exact tier: graphify's own normalized labels (still exact-hit
        # dict lookups — never fuzzy). Tried lowercased and bare.
        if not cands:
            for v in (mention.lower(), mention.strip("._()").lower()):
                ids = self.norm_index.get(v, [])
                if ids:
                    cands = [self.nodes[i] for i in ids]
                    break

        # Field-test lesson (2026-06-12): junk targets created accidental
        # uniqueness (`after()` → poly_scourge bundler artifact). Noise-path
        # nodes are never link candidates.
        cands = [n for n in cands if not is_noise_path(n.source_file)]

        # Dedupe identical (label, source_file) clones (e.g. "Error Analysis" ×4).
        seen, uniq = set(), []
        for n in cands:
            k = (n.label, n.source_file)
            if k not in seen:
                seen.add(k)
                uniq.append(n)
        cands = uniq
        res.candidates = cands

        if len(cands) == 1:
            res.linked, res.tier = cands[0], "unique-label"
            return res

        # >1 exact match: path hints from the same card may disambiguate.
        if len(cands) > 1 and path_hints:
            hints = [h.replace("\\", "/").lstrip("./") for h in path_hints]
            survivors = [n for n in cands
                         if any(h in n.source_file.replace("\\", "/") for h in hints)]
            if len(survivors) == 1:
                res.linked, res.tier = survivors[0], "path-qualified"
        return res

    def find_dead_refs(self, node_ids: list) -> list:
        """Drift detection (DR-003 §3.5): referenced ids absent from the graph."""
        return [i for i in node_ids if i not in self.nodes]


def _looks_like_filename(s: str) -> bool:
    return bool(re.fullmatch(r"[\w.-]+\.[A-Za-z]{1,5}", s))


# ── Loader ────────────────────────────────────────────────────────────────────
def _fingerprint(data: object) -> str:
    if isinstance(data, dict):
        lines = [f"top-level keys: {sorted(data.keys())}"]
        for k, v in data.items():
            if isinstance(v, list) and v:
                lines.append(f"  {k}: list[{len(v)}], first item keys: "
                             f"{sorted(v[0].keys()) if isinstance(v[0], dict) else type(v[0]).__name__}")
        return "\n".join(lines)
    return f"top-level type: {type(data).__name__}"


def load_graph(path: Path | str = DEFAULT_GRAPH) -> Graph:
    path = Path(path)
    if not path.exists():
        raise GraphSchemaError(
            f"graph export not found: {path}\n"
            f"Run on host:  cd ~/Desktop && graphify update .\n"
            f"Then probe:   python3 ~/.gr0b/scripts/gr0b_graphlib.py --probe")

    with open(path) as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise GraphSchemaError("Unrecognized export (not a JSON object).\n"
                               + _fingerprint(data))

    raw_nodes = _pick(data, NODE_CONTAINER_KEYS)
    raw_edges = _pick(data, EDGE_CONTAINER_KEYS)
    if raw_nodes is None:
        raise GraphSchemaError("No node container found.\n" + _fingerprint(data))
    raw_edges = raw_edges or []

    g = Graph(path=str(path))
    g.schema = {
        "node_container": next(k for k in NODE_CONTAINER_KEYS if k in data),
        "edge_container": next((k for k in EDGE_CONTAINER_KEYS if k in data), "MISSING"),
        "n_nodes_raw": len(raw_nodes),
        "n_edges_raw": len(raw_edges),
    }

    label_ix, base_ix, norm_ix = defaultdict(list), defaultdict(list), defaultdict(list)
    for i, nd in enumerate(raw_nodes):
        if not isinstance(nd, dict):
            continue
        nid = _pick(nd, NODE_ID_KEYS)
        label = _pick(nd, NODE_LABEL_KEYS) or ""
        if nid is None:
            nid = f"_anon_{i}"
        nid = str(nid)
        node = Node(
            id=nid,
            label=str(label),
            source_file=str(_pick(nd, NODE_FILE_KEYS) or ""),
            type=str(_pick(nd, NODE_TYPE_KEYS) or ""),
            community=int(_pick(nd, NODE_COMM_KEYS) or -1),
            norm_label=str(_pick(nd, NODE_NORM_KEYS) or ""),
        )
        g.nodes[nid] = node
        if node.label:
            label_ix[node.label].append(nid)
        if node.source_file:
            base_ix[Path(node.source_file).name].append(nid)
        if node.norm_label:
            norm_ix[node.norm_label.lower()].append(nid)

    for ed in raw_edges:
        if not isinstance(ed, dict):
            continue
        s, t = _pick(ed, EDGE_SRC_KEYS), _pick(ed, EDGE_DST_KEYS)
        if s is None or t is None:
            continue
        try:
            score = float(_pick(ed, EDGE_SCORE_KEYS) or 0.0)
        except (TypeError, ValueError):
            score = 0.0
        try:
            weight = float(_pick(ed, EDGE_WEIGHT_KEYS) or 0.0)
        except (TypeError, ValueError):
            weight = 0.0
        g.edges.append(Edge(
            source=str(s), target=str(t),
            relation=str(_pick(ed, EDGE_REL_KEYS) or ""),
            confidence=str(_pick(ed, EDGE_CONF_KEYS) or ""),
            confidence_score=score,
            weight=weight,
        ))

    g.label_index = dict(label_ix)
    g.basename_index = dict(base_ix)
    g.norm_index = dict(norm_ix)
    return g


# ── Probe CLI ─────────────────────────────────────────────────────────────────
def main(argv: list) -> int:
    if "--probe" not in argv:
        print(__doc__)
        return 0
    args = [a for a in argv if not a.startswith("--")]
    path = Path(args[0]) if args else DEFAULT_GRAPH
    print(f"Probing: {path}")
    if not path.exists():
        print("  MISSING — run: cd ~/Desktop && graphify update .")
        return 2
    with open(path) as f:
        data = json.load(f)
    print(_fingerprint(data))
    try:
        g = load_graph(path)
        print(f"\nLoader result: {len(g.nodes):,} nodes, {len(g.edges):,} edges")
        print(f"Schema map: {g.schema}")
        if g.edges:
            e = g.edges[0]
            print(f"Sample edge: {e.source} --{e.relation} [{e.confidence}]--> {e.target}")
        else:
            print("⚠️  ZERO EDGES — this is the BRAIN_MAP bug. Paste this probe "
                  "output back to Claude/Flash; the edge container key needs mapping.")
        sample = next((n for n in g.nodes.values() if n.source_file), None)
        if sample:
            print(f"Sample node: id={sample.id!r} label={sample.label!r} "
                  f"src={sample.source_file!r} type={sample.type!r}")
        return 0 if g.edges else 3
    except GraphSchemaError as e:
        print(f"\nSCHEMA ERROR:\n{e}")
        return 4


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
