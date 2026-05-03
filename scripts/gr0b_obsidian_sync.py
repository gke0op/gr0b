#!/usr/bin/env python3
"""
gr0b_obsidian_sync.py — sync graphify graph to Obsidian notes.

Reads  : ~/Desktop/graphify-out/graph.json
Writes : ~/.gr0b/knowledge-graphs/  (one .md per community, not per node)

Re-run any time to refresh:
    python3 ~/.gr0b/scripts/gr0b_obsidian_sync.py

Options:
    --limit N    only write first N communities (default: all)
    --min-nodes N skip communities smaller than N (default: 5)
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

GRAPH  = Path.home() / "Desktop" / "graphify-out" / "graph.json"
VAULT  = Path.home() / ".gr0b"
OUTDIR = VAULT / "knowledge-graphs"


def sanitise(name: str) -> str:
    """Make a string safe for use as a filename."""
    return "".join(c if c.isalnum() or c in " _-" else "_" for c in name).strip()


def derive_title(community_id: int, paths: list[str], labels: list[str]) -> str:
    """Best-effort human title from paths or dominant label."""
    if not paths:
        top = sorted(set(labels), key=len, reverse=True)
        return top[0] if top else f"Community {community_id}"

    # Most common top-level directory segment
    segments: dict[str, int] = defaultdict(int)
    for p in paths:
        parts = p.replace("\\", "/").split("/")
        seg = parts[0] if parts else ""
        # Skip hash-like prefixes (e.g. random 8-char folder names)
        if seg and not (len(seg) == 8 and seg.isalnum()):
            segments[seg] += 1
        elif len(parts) > 1:
            segments[parts[1]] += 1

    if segments:
        return max(segments, key=segments.get)
    return f"Community {community_id}"


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit",     type=int, default=0,  help="max communities to write")
    parser.add_argument("--min-nodes", type=int, default=5,  help="skip communities smaller than N")
    args = parser.parse_args()

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

    # Build adjacency list for wikilinks
    node_by_id: dict = {}
    for n in nodes:
        nid = n.get("id") or n.get("node_id") or n.get("label")
        if nid is not None:
            node_by_id[nid] = n

    adj: dict[int, set[int]] = defaultdict(set)
    for edge in edges:
        s, t = edge.get("source"), edge.get("target")
        if s is not None and t is not None:
            adj[s].add(t)
            adj[t].add(s)

    # Group by community
    communities: dict[int, dict] = defaultdict(
        lambda: {"labels": [], "paths": [], "node_ids": []}
    )
    for node in nodes:
        cid  = node.get("community", -1)
        nid  = node.get("id") or node.get("node_id")
        label = node.get("label", "")
        path  = node.get("source_file", node.get("src", ""))
        communities[cid]["labels"].append(label)
        communities[cid]["node_ids"].append(nid)
        if path:
            communities[cid]["paths"].append(path)

    OUTDIR.mkdir(parents=True, exist_ok=True)

    # Sort communities by size
    sorted_cids = sorted(
        [cid for cid, info in communities.items() if len(info["labels"]) >= args.min_nodes],
        key=lambda c: -len(communities[c]["labels"])
    )
    if args.limit:
        sorted_cids = sorted_cids[:args.limit]

    written = 0
    for cid in sorted_cids:
        info   = communities[cid]
        labels = info["labels"]
        paths  = info["paths"]
        ids    = info["node_ids"]

        title = derive_title(cid, paths, labels)

        # Find communities that share edges with this one (inter-community links)
        neighbour_cids: dict[int, int] = defaultdict(int)
        for nid in ids:
            if nid is None:
                continue
            for neighbour_id in adj.get(nid, set()):
                nb_node = node_by_id.get(neighbour_id)
                if nb_node:
                    nb_cid = nb_node.get("community", -1)
                    if nb_cid != cid:
                        neighbour_cids[nb_cid] += 1

        top_neighbours = sorted(neighbour_cids.items(), key=lambda x: -x[1])[:5]

        # Unique sorted paths (truncated)
        top_paths = sorted(set(paths))[:20]
        top_labels = sorted(set(labels), key=len, reverse=True)[:20]

        md_lines = [
            f"# {title}",
            "",
            f"**Community #{cid}** · {len(labels):,} nodes",
            "",
            "## Key symbols",
            "",
        ]
        md_lines += [f"- `{l}`" for l in top_labels]
        md_lines += [""]

        if top_paths:
            md_lines += ["## Source paths", ""]
            md_lines += [f"- `{p}`" for p in top_paths]
            if len(paths) > len(top_paths):
                md_lines += [f"- … and {len(paths) - len(top_paths):,} more"]
            md_lines += [""]

        if top_neighbours:
            md_lines += ["## Connected communities", ""]
            for nb_cid, link_count in top_neighbours:
                nb_info  = communities.get(nb_cid, {})
                nb_title = derive_title(nb_cid, nb_info.get("paths", []), nb_info.get("labels", []))
                safe_title = sanitise(nb_title)
                md_lines += [f"- [[{safe_title}]] ({link_count} cross-links)"]
            md_lines += [""]

        md_lines += [
            "---",
            "",
            "*Generated by gr0b · https://github.com/gke0op/gr0b*",
        ]

        fname = f"{sanitise(title)}.md"
        (OUTDIR / fname).write_text("\n".join(md_lines))
        written += 1

        if written % 100 == 0:
            print(f"  {written} / {len(sorted_cids)} communities written …", flush=True)

    print(f"\nDone. {written} community notes written to {OUTDIR}")


if __name__ == "__main__":
    main()
