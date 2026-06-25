# FLASH BRIEF — Phase 3 Cartography (DR-003)

*Contract for Gemini Flash, written by Claude (Fable 5) 2026-06-12. Read fully before acting.*

> **STATUS (2026-06-12, end of Fable session):** T0 ✅ (probe clean, schema
> confirmed) · T1 ✅ (BRAIN_MAP regenerated: 242,694 edges, 20 projects) ·
> T2 ✅ (applied by Gokce: 6 links / 5 ambiguous / 8 files; two false-positive
> classes found in dry-run review and hard-patched into the kernel + tests,
> 27 green). **Start at T3.** Re-running T1/T2 is harmless (idempotent).

You are executing bounded tasks inside gr0b. The judgment-dense kernel is
**already built and tested** — your job is host-side discovery, the
retroactive pass, and wiring. The contract is executable:

```bash
python3 ~/.gr0b/scripts/verify_phase3.py
```

Run it after EVERY task. ⚠️ Shell rule for this whole brief: command blocks
contain NO inline `#` comments and you must not add any — interactive zsh
passes comment text as arguments (this already caused a silent 0-file run).

All checks must PASS before you report done. SKIPs count as not-done on host.

## Hard rules (violating any = stop and report)

1. **Never edit**: `gr0b_graphlib.py`, `gr0b_link.py`, `verify_phase3.py`, `scripts/tests/*`. If they seem wrong, STOP and write your evidence to `~/.gr0b/FLASH_REPORT.md`.
2. **Never guess an ambiguous link.** The linker records ambiguity by design; do not "fix" unresolved/ambiguous counts by loosening anything.
3. **No git commits** — household rule. Stage nothing. Gokce commits.
4. **Never write into** `~/.graphify/` or graphify's cache/obsidian dirs (death-ball lesson, DR in gr0b.config.yaml).
5. **Never touch the agentmemory store directly** (no HTTP calls to it).
6. Work top-to-bottom; one task fully green before the next.

## T0 — Discovery probe (DO THIS FIRST)

First refresh the export, then probe it:

```bash
cd ~/Desktop && graphify update .
python3 ~/.gr0b/scripts/gr0b_graphlib.py --probe
```

Paste the FULL probe output into `~/.gr0b/FLASH_REPORT.md`. If it reports
`ZERO EDGES` or `SCHEMA ERROR`: **stop after T0** — report and wait; the
loader's key-variant map needs a Fable patch, not a Flash workaround.

## T1 — Regenerate the map

```bash
python3 ~/.gr0b/scripts/gr0b_map.py
```

Pass criteria: exit 0; `verify_phase3.py` → "BRAIN_MAP has edges" PASS and
"BRAIN_MAP hygiene" PASS.

## T2 — Retroactive linking pass

Dry-run first and REVIEW the output, then apply, then capture the JSON
report for FLASH_REPORT:

```bash
python3 ~/.gr0b/scripts/gr0b_link.py
python3 ~/.gr0b/scripts/gr0b_link.py --apply
python3 ~/.gr0b/scripts/gr0b_link.py --report
```

Pass criteria: "retro pass coverage" PASS; "no dead refs" PASS. In the
report include: links count, ambiguous count, and the 10 most interesting
resolved links (your judgment welcome HERE — it's commentary, not code).

### T2b — Ambiguity dossier (report only, do NOT link anything)

T2 left recorded ambiguities (SunCore ×9, ARCHITECTURE.md ×2, debate.py ×3,
config.py ×12, TikTok ×7). For each, write into FLASH_REPORT a list of the
candidate node IDs + their source_file paths, using the loader:

```python
from gr0b_graphlib import load_graph
g = load_graph()
for m in ("SunCore", "ARCHITECTURE.md", "debate.py", "config.py", "TikTok"):
    print(m, [(n.id, n.source_file) for n in g.resolve(m).candidates])
```

Gokce/Fable will add path qualifiers to the cards; the linker picks them up
on the next run. Enumerating candidates is allowed; choosing one is not.

## T3 — Wire drift detection into gr0b_doctor.py

Add a check to `gr0b_doctor.py` (this file you MAY edit):

- Parse `gr0b_nodes:` ids from all `decisions/*.md` (reuse
  `gr0b_link._strip_frontmatter` or regex `^\s*-\s+(\S+)\s+#` within the block).
- Call `gr0b_graphlib.load_graph().find_dead_refs(ids)`.
- Report stale cards as a doctor warning: `DRIFT: <card> references dead node <id>`.

Pass criteria: "doctor drift wired" PASS; doctor runs clean end-to-end.

## T4 — Per-project map pages (edge-derived)

For each project in BRAIN_MAP, write `knowledge-graphs/obsidian-notes/projects/<name>.md`:

- **Hubs**: top 8 nodes by degree *within the project's communities*,
  excluding `gr0b_graphlib.is_noise_label` labels.
- **Spine**: 10 highest-confidence `calls` edges between hub nodes, rendered
  as `A → B`. Rank numerically by `Edge.confidence_score` (loader exposes it;
  ties → higher `weight` wins).
- **Entrypoints**: nodes with in-degree 0 / out-degree > 0 (max 5).
- Frontmatter: `gr0b_generated: <date>`, `project: <name>`.

Pass criteria: files exist for every project listed in BRAIN_MAP; no
stoplist labels appear as hubs; `verify_phase3.py` still all-PASS.

## T5 — Investigate rationale_for writeback (report only, NO implementation)

```bash
graphify --help
graphify add --help 2>&1 | head -30
```

Question to answer in FLASH_REPORT: does graphify 0.5.6 expose any supported
way to ADD edges (decision-note → code-node, type `rationale_for`)? If yes:
exact command + example. If no: say so plainly. **Do not hack the cache.**

## T6 — Sync to repo working tree (no commit)

Copy these into `~/Desktop/gr0b` (repo working tree, leave uncommitted):
`scripts/gr0b_graphlib.py`, `scripts/gr0b_link.py`, `scripts/verify_phase3.py`,
`scripts/tests/test_phase3.py`, updated `scripts/gr0b_map.py`,
`decisions/DR-003-cartography-binding-the-two-hemispheres.md`, this brief.

## Report format (`~/.gr0b/FLASH_REPORT.md`)

```
# FLASH REPORT — Phase 3
T0: probe output (verbatim block)
T1–T4: verify_phase3.py final output (verbatim), per-task notes
T2: link --report JSON + 10 interesting links
T5: rationale_for findings
Blockers: anything you stopped on, with evidence
```

Litmus (after all green) — this should feel different:
`python3 ~/.gr0b/scripts/gr0b_link.py --report` shows the journal anchored to
the map, and the doctor knows when memories go stale. That's the corpus
callosum carrying traffic.
