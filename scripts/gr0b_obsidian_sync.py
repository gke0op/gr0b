#!/usr/bin/env python3
"""
gr0b_obsidian_sync.py v2 — project-level Obsidian sync.

Reads graphify-out/graph.json and writes ONE rich note per project
(plus a brain index and an infrastructure summary) instead of thousands
of per-symbol or per-community notes.

Improvements over v1:
- Reuses gr0b_map.py community classification: stdlib / vendored /
  minified noise is filtered into a single Infrastructure note.
- Communities are MERGED by project name intentionally (v1 filename
  collisions overwrote notes silently and lossily).
- Hub symbols ranked by graph degree, with source paths.
- Cross-project wikilinks weighted by edge count — Obsidian graph view
  becomes your actual project constellation.
- Old notes are archived, never deleted.

Usage:
    python3 ~/.gr0b/scripts/gr0b_obsidian_sync.py
    python3 ~/.gr0b/scripts/gr0b_obsidian_sync.py --graph /path/graph.json --out /path/notes
"""
import argparse
import json
import shutil
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from gr0b_map import classify_path, looks_like_minified_js  # noqa: E402

MIN_NODES = 8     # skip tiny one-off clusters (same as gr0b_map)
TOP_HUBS = 12     # hub symbols listed per project
TOP_RELATED = 8   # related-project wikilinks per note


def safe_name(name: str) -> str:
    s = "".join(c if c.isalnum() or c in " _-" else "_" for c in name).strip()
    return s[:80] or "Unknown"


def load_graph(graph_path: Path):
    print(f"[gr0b-sync] Reading {graph_path} ({graph_path.stat().st_size/1e6:.0f} MB) ...")
    with open(graph_path) as f:
        data = json.load(f)
    nodes = data.get("nodes", [])
    edges = data.get("edges", data.get("links", []))
    print(f"[gr0b-sync] {len(nodes):,} nodes, {len(edges):,} edges")
    return nodes, edges


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--graph", type=Path,
                    default=Path.home() / "Desktop" / "graphify-out" / "graph.json")
    ap.add_argument("--out", type=Path,
                    default=Path.home() / ".gr0b" / "knowledge-graphs" / "obsidian-notes")
    args = ap.parse_args()

    if not args.graph.exists():
        print(f"[gr0b-sync] ERROR: graph.json not found at {args.graph}")
        print("Run:  cd ~/Desktop && graphify update .")
        sys.exit(1)

    nodes, edges = load_graph(args.graph)

    # ── Index nodes, group by community ───────────────────────────────────
    node_attrs = {}
    communities = defaultdict(lambda: {"ids": [], "labels": [], "paths": []})
    for n in nodes:
        nid = n.get("id")
        label = n.get("label", str(nid))
        path = n.get("source_file", n.get("src", ""))
        cid = n.get("community", -1)
        node_attrs[nid] = (label, path)
        c = communities[cid]
        c["ids"].append(nid)
        c["labels"].append(label)
        if path:
            c["paths"].append(path)

    degree = defaultdict(int)
    for e in edges:
        degree[e.get("source")] += 1
        degree[e.get("target")] += 1

    # ── Classify communities → projects / noise (gr0b_map logic) ─────────
    projects = defaultdict(lambda: {"cids": [], "ids": [], "paths": [], "n": 0})
    noise_counts = defaultdict(int)

    for cid, info in communities.items():
        if len(info["ids"]) < MIN_NODES:
            continue
        if looks_like_minified_js(info["labels"]):
            noise_counts["Minified JS / build output"] += len(info["ids"])
            continue

        name_votes, noise_votes = defaultdict(int), defaultdict(int)
        for p in info["paths"]:
            name, is_noise = classify_path(p)
            (noise_votes if is_noise else name_votes)[name] += 1

        total = max(len(info["paths"]), 1)
        if sum(noise_votes.values()) / total > 0.6:
            label = max(noise_votes, key=noise_votes.get)
            noise_counts[label] += len(info["ids"])
            continue

        pname = max(name_votes, key=name_votes.get) if name_votes else "Unknown"
        proj = projects[pname]
        proj["cids"].append(cid)
        proj["ids"].extend(info["ids"])
        proj["paths"].extend(info["paths"])
        proj["n"] += len(info["ids"])

    # node id → project name (for cross-links)
    id_to_project = {}
    for pname, proj in projects.items():
        for nid in proj["ids"]:
            id_to_project[nid] = pname

    # ── Cross-project edge counts ─────────────────────────────────────────
    related = defaultdict(lambda: defaultdict(int))
    for e in edges:
        pa = id_to_project.get(e.get("source"))
        pb = id_to_project.get(e.get("target"))
        if pa and pb and pa != pb:
            related[pa][pb] += 1
            related[pb][pa] += 1

    # ── Prepare output dir (archive old notes, never delete) ─────────────
    # Archive as a tarball, NOT a renamed directory: loose .md files left
    # anywhere in the vault stay visible to Obsidian's graph view and turn
    # into a giant hairball of stale nodes (3,746-node death-star, 2026-06).
    out = args.out
    if out.exists() and any(out.iterdir()):
        import shutil
        import tarfile
        stamp = datetime.now().strftime("%Y%m%d-%H%M")
        archive = out.parent / f"obsidian-notes-old-{stamp}.tar.gz"
        print(f"[gr0b-sync] Archiving old notes → {archive}")
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(out, arcname=f"obsidian-notes-old-{stamp}")
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    # ── Write project notes ───────────────────────────────────────────────
    sorted_projects = sorted(projects.items(), key=lambda x: -x[1]["n"])
    written = 0
    for pname, proj in sorted_projects:
        hubs = sorted(proj["ids"], key=lambda i: -degree[i])[:TOP_HUBS]

        path_counts = defaultdict(int)
        for p in proj["paths"]:
            parts = p.replace("\\", "/").split("/")
            path_counts["/".join(parts[:2]) if len(parts) >= 2 else p] += 1
        top_paths = sorted(path_counts, key=path_counts.get, reverse=True)[:3]

        rel = sorted(related[pname].items(), key=lambda x: -x[1])[:TOP_RELATED]

        lines = [f"# {pname}", "",
                 f"**{proj['n']:,} nodes** · {len(proj['cids'])} communities", ""]
        if top_paths:
            lines.append("## Roots")
            lines += [f"- `{p}/…`" for p in top_paths]
            lines.append("")
        lines.append("## Hub symbols")
        for nid in hubs:
            label, path = node_attrs[nid]
            loc = f" — `{path}`" if path else ""
            lines.append(f"- **{label}** ({degree[nid]} links){loc}")
        lines.append("")
        if rel:
            lines.append("## Connected projects")
            lines += [f"- [[{safe_name(r)}]] ({c} edges)" for r, c in rel]
            lines.append("")
        lines += ["---", "", "*Generated by gr0b · https://github.com/gke0op/gr0b*"]

        (out / f"{safe_name(pname)}.md").write_text("\n".join(lines), encoding="utf-8")
        written += 1

    # ── Index + infrastructure notes ──────────────────────────────────────
    idx = ["# 00 — Brain Index", "",
           f"_{len(nodes):,} nodes · {len(edges):,} edges · "
           f"{written} projects · synced {datetime.now():%Y-%m-%d %H:%M}_", "",
           "## Projects (by size)", ""]
    idx += [f"- [[{safe_name(p)}]] — {info['n']:,} nodes"
            for p, info in sorted_projects]
    idx += ["", "See [[Infrastructure]] for filtered noise."]
    (out / "00 — Brain Index.md").write_text("\n".join(idx), encoding="utf-8")

    infra = ["# Infrastructure", "",
             "_Stdlib, vendored, and build-output communities filtered from the map._", ""]
    infra += [f"- **{k}** — {v:,} nodes"
              for k, v in sorted(noise_counts.items(), key=lambda x: -x[1])]
    (out / "Infrastructure.md").write_text("\n".join(infra), encoding="utf-8")

    # Self-install copy next to the notes for future reference
    try:
        shutil.copy2(__file__, out.parent / "gr0b_obsidian_sync.py")
    except Exception:
        pass

    total_noise = sum(noise_counts.values())
    print(f"[gr0b-sync] ✓ {written} project notes + index + infrastructure")
    print(f"[gr0b-sync]   {total_noise:,} noise nodes filtered "
          f"({len(noise_counts)} categories)")
    print("[gr0b-sync] Obsidian → Reload vault → Graph view = project constellation.")


if __name__ == "__main__":
    main()
