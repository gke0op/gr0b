#!/usr/bin/env python3
"""
verify_phase3.py — Phase 3 acceptance harness (DR-003).

THE CONTRACT: all checks must PASS (SKIPs allowed only in sandbox, where
host paths are unreachable). Flash: run after every task; never edit this
file or the tests to force a pass.

    python3 ~/.gr0b/scripts/verify_phase3.py
"""
import json
import re
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
VAULT = SCRIPTS.parent
GRAPH = Path.home() / "Desktop" / "graphify-out" / "graph.json"

sys.path.insert(0, str(SCRIPTS))
from gr0b_graphlib import GraphSchemaError, load_graph  # noqa: E402

RESULTS = []


def check(name: str, status: str, detail: str = ""):
    RESULTS.append((name, status, detail))
    icon = {"PASS": "✅", "FAIL": "❌", "SKIP": "⏭️ "}[status]
    print(f"{icon} {name}" + (f" — {detail}" if detail else ""))


def main() -> int:
    # 1. Unit tests (the kernel's judgment, frozen)
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", str(SCRIPTS / "tests")],
        capture_output=True, text=True)
    if proc.returncode == 0:
        check("unit tests", "PASS", "22+ tests")
    else:
        check("unit tests", "FAIL", (proc.stderr or proc.stdout).strip()[-300:])

    # 2. Live graph export loads, with edges (host only)
    graph = None
    if GRAPH.exists():
        try:
            graph = load_graph(GRAPH)
            if graph.edges:
                check("graph export", "PASS",
                      f"{len(graph.nodes):,} nodes / {len(graph.edges):,} edges")
            else:
                check("graph export", "FAIL",
                      "0 edges — re-export or fix schema mapping (run --probe)")
        except GraphSchemaError as e:
            check("graph export", "FAIL", str(e).splitlines()[0])
    else:
        check("graph export", "SKIP", "host path unreachable (sandbox?)")

    # 3. BRAIN_MAP regenerated, roads on the map
    bm = VAULT / "BRAIN_MAP.md"
    if bm.exists():
        content = bm.read_text()
        m = re.search(r"([\d,]+) edges", content)
        edge_claim = int(m.group(1).replace(",", "")) if m else -1
        if edge_claim > 0:
            check("BRAIN_MAP has edges", "PASS", f"{edge_claim:,} edges on the map")
        else:
            check("BRAIN_MAP has edges", "FAIL",
                  "map still claims 0 edges — regenerate: python3 scripts/gr0b_map.py")
        noise = [s for s in ("`Json`", "`$()`", "`_()`") if s in content]
        if noise:
            check("BRAIN_MAP hygiene", "FAIL", f"stoplist labels present: {noise}")
        else:
            check("BRAIN_MAP hygiene", "PASS", "no stoplist god-labels")
    else:
        check("BRAIN_MAP has edges", "SKIP", "BRAIN_MAP.md missing")

    # 4. Retroactive linking coverage over decisions/
    dec = VAULT / "decisions"
    cards = [p for p in sorted(dec.glob("*.md")) if p.name != "README.md"]
    if cards:
        unlinked = [p.name for p in cards
                    if "gr0b_linked_at:" not in p.read_text(errors="replace")]
        if not unlinked:
            check("retro pass coverage", "PASS", f"{len(cards)} cards linked")
        elif graph is None:
            check("retro pass coverage", "SKIP",
                  f"{len(unlinked)} unlinked, no graph here to link against")
        else:
            check("retro pass coverage", "FAIL",
                  f"unlinked: {', '.join(unlinked[:5])}"
                  + (" …" if len(unlinked) > 5 else ""))
    else:
        check("retro pass coverage", "SKIP", "no decision cards found")

    # 5. Doctor drift detection wired
    doctor = SCRIPTS / "gr0b_doctor.py"
    if doctor.exists() and "find_dead_refs" in doctor.read_text(errors="replace"):
        check("doctor drift wired", "PASS", "gr0b_doctor.py calls find_dead_refs")
    else:
        check("doctor drift wired", "FAIL",
              "gr0b_doctor.py must use gr0b_graphlib.find_dead_refs (brief T3)")

    # 6. No stale gr0b_nodes pointing at dead graph nodes (host only)
    if graph is not None and cards:
        dead_total = []
        for p in cards:
            ids = re.findall(r"^\s*-\s+([\w.-]+)\s*(?:#|$)",
                             _frontmatter_section(p.read_text(errors="replace"),
                                                  "gr0b_nodes"), re.M)
            dead_total += [(p.name, d) for d in graph.find_dead_refs(ids)]
        if dead_total:
            check("no dead refs", "FAIL",
                  f"{len(dead_total)} stale links, e.g. {dead_total[:3]}")
        else:
            check("no dead refs", "PASS")
    else:
        check("no dead refs", "SKIP", "needs host graph + linked cards")

    fails = [r for r in RESULTS if r[1] == "FAIL"]
    skips = [r for r in RESULTS if r[1] == "SKIP"]
    print(f"\n{len(RESULTS) - len(fails) - len(skips)} pass · "
          f"{len(fails)} fail · {len(skips)} skip")
    return 1 if fails else 0


def _frontmatter_section(text: str, key: str) -> str:
    if not text.startswith("---\n"):
        return ""
    end = text.find("\n---", 4)
    if end == -1:
        return ""
    inner = text[4:end + 1]
    lines, out, on = inner.splitlines(), [], False
    for line in lines:
        if line.startswith(key + ":"):
            on = True
            continue
        if on and (line.startswith("  ") or line.startswith("- ")):
            out.append(line)
            continue
        on = False
    return "\n".join(out)


if __name__ == "__main__":
    sys.exit(main())
