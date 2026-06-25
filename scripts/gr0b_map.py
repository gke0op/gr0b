#!/usr/bin/env python3
"""
gr0b_map.py — generate a human-readable BRAIN_MAP.md from your graphify graph.

Reads  : ~/Desktop/graphify-out/graph.json   (override: first CLI arg)
Writes : ~/.gr0b/BRAIN_MAP.md                (override: second CLI arg)

Re-run any time to refresh the map:
    python3 ~/.gr0b/scripts/gr0b_map.py

DR-003: loads via gr0b_graphlib (schema-defensive). REFUSES to write a map
from a 0-edge export — that's how the roadless-BRAIN_MAP bug shipped silently.
"""
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from gr0b_graphlib import (  # noqa: E402
    NOISE_PATH_PATTERNS, GraphSchemaError, is_noise_label, load_graph,
)

GRAPH   = Path.home() / "Desktop" / "graphify-out" / "graph.json"
VAULT   = Path.home() / ".gr0b"
OUTPUT  = VAULT / "BRAIN_MAP.md"

MIN_NODES = 8          # skip tiny one-off clusters
TOP_N     = 10         # labels shown per project

# ── Noise patterns ────────────────────────────────────────────────────────────
# Single source of truth lives in gr0b_graphlib.NOISE_PATH_PATTERNS — shared
# with the linker's target filter so map and links agree on what junk is.
NOISE_PATTERNS = NOISE_PATH_PATTERNS

# ── Heuristics ────────────────────────────────────────────────────────────────

def looks_like_minified_js(labels: list[str]) -> bool:
    """True when most labels are one–three chars (minified identifiers)."""
    if len(labels) < 20:
        return False
    short = sum(1 for l in labels if len(l) <= 3 and l.isalpha())
    constructor = sum(1 for l in labels if "constructor" in l.lower())
    return (short / len(labels)) > 0.15 and constructor > 2


def classify_path(path: str) -> tuple[str, bool]:
    """
    Returns (display_name, is_noise).

    display_name is derived from the first meaningful directory segment so the
    map is readable without any hardcoded project names.
    """
    for pattern, label in NOISE_PATTERNS:
        if re.search(pattern, path, re.IGNORECASE):
            return label, True

    # Strip common path prefixes that add no semantic value
    clean = re.sub(r"^[A-Za-z0-9]{6,8}/", "", path)   # random hash prefix
    parts = [p for p in clean.replace("\\", "/").split("/") if p]

    if not parts:
        return "Unknown", False

    # Walk up from the filename end: skip files, pick the most meaningful dir
    # Heuristic: skip last segment (filename), prefer segments that look like
    # project/module names (capitalised or snake_case, not generic like 'src',
    # 'lib', 'utils', 'core', 'tests').
    GENERIC = {"src", "lib", "utils", "core", "tests", "test", "dist",
               "build", "pkg", "internal", "common", "shared", "app",
               "main", "index", "scripts", "docs"}

    meaningful = [p for p in parts[:-1] if p.lower() not in GENERIC]
    name = meaningful[0] if meaningful else parts[0]
    return name, False


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    graph_path  = Path(args[0]) if len(args) > 0 else GRAPH
    output_path = Path(args[1]) if len(args) > 1 else OUTPUT

    if not graph_path.exists() and len(args) > 1:
        print("Hint: multiple unexpected args — interactive zsh passes "
              "'# comment' text as arguments; re-run without trailing comments.")

    print(f"Loading {graph_path} …", flush=True)
    try:
        g = load_graph(graph_path)
    except GraphSchemaError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    nodes = list(g.nodes.values())
    edges = g.edges
    print(f"  {len(nodes):,} nodes  {len(edges):,} edges")

    if not edges:
        print("\nREFUSING to write BRAIN_MAP: export has 0 edges (stale or "
              "edge-less export — the exact bug that shipped a roadless map).")
        print("Diagnose first:  python3 ~/.gr0b/scripts/gr0b_graphlib.py --probe")
        sys.exit(3)

    # ── Group nodes by community ──────────────────────────────────────────────
    communities: dict[int, dict] = defaultdict(
        lambda: {"labels": [], "paths": [], "folders": set()}
    )
    for node in nodes:
        cid  = node.community
        label = node.label
        path  = node.source_file
        communities[cid]["labels"].append(label)
        if path:
            communities[cid]["paths"].append(path)
            folder = path.split("/")[0] if "/" in path else path
            communities[cid]["folders"].add(folder)

    # ── Classify each community ───────────────────────────────────────────────
    # raw_clusters: list of (cid, info, project_name, is_noise)
    raw_clusters = []
    for cid, info in communities.items():
        if len(info["labels"]) < MIN_NODES:
            continue

        if looks_like_minified_js(info["labels"]):
            raw_clusters.append((cid, info, "Minified JS / build output", True))
            continue

        # Derive project name from most common path prefix
        name_votes: dict[str, int] = defaultdict(int)
        noise_votes: dict[str, int] = defaultdict(int)
        for p in info["paths"]:
            name, is_noise = classify_path(p)
            if is_noise:
                noise_votes[name] += 1
            else:
                name_votes[name] += 1

        total_paths = max(len(info["paths"]), 1)
        noise_frac  = sum(noise_votes.values()) / total_paths

        if noise_frac > 0.6:
            # Community is majority noise
            noise_label = max(noise_votes, key=noise_votes.get)
            raw_clusters.append((cid, info, noise_label, True))
        else:
            proj_name = max(name_votes, key=name_votes.get) if name_votes else "Unknown"
            raw_clusters.append((cid, info, proj_name, False))

    # ── Merge same-named project clusters ────────────────────────────────────
    projects: dict[str, dict] = {}
    noise:    dict[str, dict] = {}

    for cid, info, name, is_noise in raw_clusters:
        bucket = noise if is_noise else projects
        if name not in bucket:
            bucket[name] = {"total": 0, "cids": [], "labels": [], "paths": []}
        bucket[name]["total"]  += len(info["labels"])
        bucket[name]["cids"].append(cid)
        bucket[name]["labels"].extend(info["labels"])
        bucket[name]["paths"].extend(info["paths"])

    # Sort by size descending
    sorted_projects = sorted(projects.items(), key=lambda x: x[1]["total"], reverse=True)
    sorted_noise    = sorted(noise.items(),    key=lambda x: x[1]["total"], reverse=True)

    # ── Write BRAIN_MAP.md ────────────────────────────────────────────────────
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    a = lines.append

    a("# BRAIN_MAP")
    a("")
    a("> Auto-generated from your graphify knowledge graph.  ")
    a("> Re-run: `python3 ~/.gr0b/scripts/gr0b_map.py`")
    a("")
    a(f"**{len(nodes):,} nodes · {len(edges):,} edges · "
      f"{len(sorted_projects)} projects · "
      f"{len(sorted_noise)} infra clusters**")
    a("")
    a("---")
    a("")
    a("## How to navigate")
    a("")
    a("Each entry below is a community of related code. Larger communities = "
      "more interconnected code. Use `graphify query \"<question>\"` to search "
      "semantically, or open Obsidian and filter by project name in the graph view.")
    a("")
    a("---")
    a("")
    a("## Your Projects")
    a("")

    for i, (name, info) in enumerate(sorted_projects, 1):
        top_labels = sorted({l for l in info["labels"] if not is_noise_label(l)},
                            key=len, reverse=True)[:TOP_N]
        cids_str   = ", ".join(f"#{c}" for c in sorted(info["cids"])[:5])
        if len(info["cids"]) > 5:
            cids_str += f" +{len(info['cids']) - 5} more"

        # Derive a representative path
        path_counts: dict[str, int] = defaultdict(int)
        for p in info["paths"]:
            parts = p.replace("\\", "/").split("/")
            if len(parts) >= 2:
                path_counts["/".join(parts[:2])] += 1
        top_path = max(path_counts, key=path_counts.get) if path_counts else ""

        a(f"### {i}. {name}")
        a("")
        a(f"- **Nodes:** {info['total']:,}  ·  **Communities:** {cids_str}")
        if top_path:
            a(f"- **Root path:** `{top_path}/…`")
        a(f"- **Key symbols:** {', '.join(f'`{l}`' for l in top_labels)}")
        a("")

    a("---")
    a("")
    a("## Infrastructure / Noise")
    a("")
    a("These communities are stdlib, vendored code, or bundler output — "
      "not your application logic.")
    a("")

    for name, info in sorted_noise:
        cids_str = ", ".join(f"#{c}" for c in sorted(info["cids"])[:3])
        if len(info["cids"]) > 3:
            cids_str += f" +{len(info['cids']) - 3} more"
        a(f"- **{name}** — {info['total']:,} nodes ({cids_str})")

    a("")
    a("---")
    a("")
    a(f"*Generated by gr0b · https://github.com/gke0op/gr0b*")

    output_path.write_text("\n".join(lines))
    print(f"\nBRAIN_MAP written → {output_path}")
    print(f"  {len(sorted_projects)} projects  |  {len(sorted_noise)} infra clusters")

    # ── T4: Per-Project Map Pages ─────────────────────────────────────────────
    import datetime
    projects_dir = VAULT / "knowledge-graphs" / "obsidian-notes" / "projects"
    projects_dir.mkdir(parents=True, exist_ok=True)

    for name, info in sorted_projects:
        proj_cids = set(info["cids"])
        proj_nodes = {nid: n for nid, n in g.nodes.items() if n.community in proj_cids}

        # Calculate degrees within the project's communities
        degrees = {nid: 0 for nid in proj_nodes}
        in_degrees = {nid: 0 for nid in proj_nodes}
        out_degrees = {nid: 0 for nid in proj_nodes}

        for e in g.edges:
            if e.source in proj_nodes and e.target in proj_nodes:
                degrees[e.source] += 1
                degrees[e.target] += 1
                in_degrees[e.target] += 1
                out_degrees[e.source] += 1

        # Hubs
        valid_hubs = [nid for nid in proj_nodes if not is_noise_label(proj_nodes[nid].label)]
        # Deduplicate hubs by label, keeping the one with higher degree
        hubs_by_label = {}
        for nid in valid_hubs:
            lbl = proj_nodes[nid].label
            if lbl not in hubs_by_label or degrees[nid] > degrees[hubs_by_label[lbl]]:
                hubs_by_label[lbl] = nid
        top_hub_ids = sorted(hubs_by_label.values(), key=lambda nid: degrees[nid], reverse=True)[:8]
        top_hubs_set = set(top_hub_ids)

        # Spine
        spine_edges = []
        for e in g.edges:
            if e.relation == "calls" and e.source in top_hubs_set and e.target in top_hubs_set:
                spine_edges.append(e)

        unique_spine = {}
        for e in spine_edges:
            k = (e.source, e.target)
            if k not in unique_spine:
                unique_spine[k] = e
            else:
                existing = unique_spine[k]
                if (e.confidence_score, e.weight) > (existing.confidence_score, existing.weight):
                    unique_spine[k] = e
        spine_edges = list(unique_spine.values())

        sorted_spine = sorted(
            spine_edges,
            key=lambda e: (e.confidence_score, e.weight),
            reverse=True
        )[:10]

        # Entrypoints
        entrypoints = []
        for nid in proj_nodes:
            if in_degrees[nid] == 0 and out_degrees[nid] > 0:
                entrypoints.append(nid)
        # Filter entrypoints
        entrypoints = [nid for nid in entrypoints if not is_noise_label(proj_nodes[nid].label)]
        # Deduplicate entrypoints by label, keeping the one with higher out-degree
        entry_by_label = {}
        for nid in entrypoints:
            lbl = proj_nodes[nid].label
            if lbl not in entry_by_label or out_degrees[nid] > out_degrees[entry_by_label[lbl]]:
                entry_by_label[lbl] = nid
        sorted_entrypoints = sorted(
            entry_by_label.values(),
            key=lambda nid: out_degrees[nid],
            reverse=True
        )[:5]

        # Generate markdown content
        proj_lines = []
        proj_lines.append("---")
        proj_lines.append(f"gr0b_generated: {datetime.date.today().isoformat()}")
        proj_lines.append(f"project: {name}")
        proj_lines.append("---")
        proj_lines.append("")
        proj_lines.append(f"# {name}")
        proj_lines.append("")
        proj_lines.append("## Hubs")
        proj_lines.append("")
        for nid in top_hub_ids:
            proj_lines.append(f"- `{proj_nodes[nid].label}`")
        if not top_hub_ids:
            proj_lines.append("None found.")
        proj_lines.append("")
        proj_lines.append("## Spine")
        proj_lines.append("")
        for e in sorted_spine:
            src_lbl = proj_nodes[e.source].label
            dst_lbl = proj_nodes[e.target].label
            proj_lines.append(f"- `{src_lbl} → {dst_lbl}`")
        if not sorted_spine:
            proj_lines.append("None found.")
        proj_lines.append("")
        proj_lines.append("## Entrypoints")
        proj_lines.append("")
        for nid in sorted_entrypoints:
            proj_lines.append(f"- `{proj_nodes[nid].label}`")
        if not sorted_entrypoints:
            proj_lines.append("None found.")
        proj_lines.append("")

        # Write to file
        proj_file = projects_dir / f"{name}.md"
        proj_file.write_text("\n".join(proj_lines))


if __name__ == "__main__":
    main()
