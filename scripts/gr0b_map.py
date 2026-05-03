#!/usr/bin/env python3
"""
gr0b_map.py — generate a human-readable BRAIN_MAP.md from your graphify graph.

Reads  : ~/Desktop/graphify-out/graph.json
Writes : ~/.gr0b/BRAIN_MAP.md

Re-run any time to refresh the map:
    python3 ~/.gr0b/scripts/gr0b_map.py
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

GRAPH   = Path.home() / "Desktop" / "graphify-out" / "graph.json"
VAULT   = Path.home() / ".gr0b"
OUTPUT  = VAULT / "BRAIN_MAP.md"

MIN_NODES = 8          # skip tiny one-off clusters
TOP_N     = 10         # labels shown per project

# ── Noise patterns (infrastructure / bundler noise) ───────────────────────────
# Communities dominated by these path patterns are moved to an infrastructure
# section rather than listed as your projects.
NOISE_PATTERNS = [
    # Zig standard library / C library headers
    (r"lib/std/", "Zig stdlib"),
    (r"lib/libc/", "Zig libc headers"),
    (r"lib/compiler_rt", "Zig compiler-rt"),
    # Bundler / obfuscated output (poly_scourge, Rollup chunks, etc.)
    (r"poly_scourge", "Bundler output"),
    # Common vendored / generated paths
    (r"node_modules/", "node_modules"),
    (r"vendor/", "Vendor code"),
    (r"\.min\.", "Minified assets"),
    (r"dist/bundle", "Build output"),
]

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
    if not GRAPH.exists():
        print(f"ERROR: graph.json not found at {GRAPH}")
        print("Run:  cd ~/Desktop && graphify update .")
        sys.exit(1)

    print(f"Loading {GRAPH} …", flush=True)
    with open(GRAPH) as f:
        data = json.load(f)

    nodes = data.get("nodes", [])
    edges = data.get("edges", [])
    print(f"  {len(nodes):,} nodes  {len(edges):,} edges")

    # ── Group nodes by community ──────────────────────────────────────────────
    communities: dict[int, dict] = defaultdict(
        lambda: {"labels": [], "paths": [], "folders": set()}
    )
    for node in nodes:
        cid  = node.get("community", -1)
        label = node.get("label", "")
        path  = node.get("source_file", node.get("src", ""))
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
    VAULT.mkdir(parents=True, exist_ok=True)
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
        top_labels = sorted(set(info["labels"]), key=len, reverse=True)[:TOP_N]
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

    OUTPUT.write_text("\n".join(lines))
    print(f"\nBRAIN_MAP written → {OUTPUT}")
    print(f"  {len(sorted_projects)} projects  |  {len(sorted_noise)} infra clusters")


if __name__ == "__main__":
    main()
