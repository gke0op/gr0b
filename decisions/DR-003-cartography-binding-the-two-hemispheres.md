---
gr0b_nodes:
  - scripts_gr0b_map    # gr0b_map.py (unique-label)
  - scripts_gr0b_ingest    # gr0b_ingest.py (unique-label)
  - kairos_lab_delta_drift    # kairos_lab/delta_drift.py (file-path)
  - scripts_gr0b_reflect    # gr0b_reflect.py (unique-label)
  - scripts_gr0b_doctor    # gr0b_doctor.py (unique-label)
gr0b_ambiguous:
  - "SunCore"    # 9 candidates — needs path qualifier
gr0b_linked_at: 2026-06-12
---

# DR-003 — Cartography: Binding the Two Hemispheres

*2026-06-12 · Gokce × Claude (Fable 5, Cowork) · Status: KERNEL SHIPPED (graphlib + linker + 22 tests green + map patch + harness); host tasks delegated → FLASH_BRIEF_phase3.md*

## The observation that triggered this

After Phase 2 (Silicon Mind ingestion), gr0b tracks what agents **say** but not how the code **works**. Gokce's framing: *"a brain with just emotions, without memories."*

## Evidence (verified live, 2026-06-12)

1. **The map is alive but unread.** Live graphify graph: 188,459 nodes, **242,694 edges**, 12,476 communities, 96% EXTRACTED confidence. Query test ("signal flow to dispatch") returned real call structure across `Robot/_raven` (dispatcher → telegram → archive). The organ works.
2. **BRAIN_MAP.md shows 0 edges.** `gr0b_map.py` reads a stale manual export (`~/Desktop/graphify-out/graph.json`) whose edges array is empty/renamed. The map document literally has nodes but no roads — and nobody noticed, which proves nothing consumes it.
3. **The hemispheres are unlinked.** `gr0b_ingest.py`: zero references to graph/nodes. Memory cards are pure prose. `insights/open-threads.md` mentions file paths constantly (e.g. `kairos_lab/delta_drift.py`) as dead text — never as graph references.
4. **The brain can't see itself.** `watch_paths` = `~/Desktop` only. The vault (decisions, insights, session logs) is not in the graph.
5. **Graph hygiene.** God nodes are noise: `Json` (675 edges), `$()`, `_()`. "Error Analysis" appears 4×. Project "key symbols" in BRAIN_MAP are just the longest docstrings, not the most central abstractions.
6. **The architecture already points at the answer.** graphify has a **`rationale_for` edge type** (seen live: docstring → `SunCore`). Prose-that-explains-code is already a first-class relation in the map. Decision cards ARE prose explaining code. They belong in the graph.

## First principles — what gr0b is

The name encodes the founding intent: **gr**(aphify) + **ob**(sidian) = map + journal. It was conceived as a dual-memory system and built lopsided.

Three ontological layers:

| Layer | What | Cognitive analog | Status |
|---|---|---|---|
| Territory | the code on Desktop | the world | exists |
| Map | graphify graph | semantic/structural memory | alive, unread |
| Journal | agentmemory + logs + insights + decisions | episodic/affective memory | rich (Phase 1–2) |

What's missing is **consolidation** — the process that binds episodes to structure. In brains: hippocampal replay writes episodes into cortical world-models. In gr0b: `gr0b_reflect.py` distills logs → insights but never anchors them to the map. Result: a diary about a city, kept by people who refuse to open the city map.

gr0b is not a logging system. It is a **shared world-model for a multi-agent household**. The journal annotates the map; the map grounds the journal. Neither alone is a brain.

## Phase 3 — the corpus callosum

### 3.1 Fix the map generator (small, do first)
- `gr0b_map.py`: read the live graph (or re-export with edges; detect 0-edge export and refuse to write).
- Per-project pages derived from **edges**, not label length: entrypoints, call spines, project-local god nodes, cross-project edges.

### 3.2 Entity linking at ingest (the binding)
- In `gr0b_ingest.py`: scan card text for file paths and symbol names, resolve against graph labels (`graphify query`), write `nodes:` frontmatter on every card/decision.
- Retroactive pass over existing decisions/ and memory cards.

### 3.3 rationale_for edges into the graph
- Push decision → node links back into graphify as `rationale_for` edges, so `get_neighbors(SymbolX)` surfaces "the decision that blessed this code."

### 3.4 Boot context — where the map becomes utility
- `gr0b_context.py <project>`: emits the project's map page + linked decisions + open threads + recurring failures for that project. Agents read it at session start. The brain becomes an organ agents **query**, not a diary they write into.

### 3.5 Drift detection (memory decay)
- `gr0b_doctor.py`: for every decision with `nodes:`, check the nodes still exist in the live graph. Dead reference → flag the memory as stale. Memories about deleted code should fade like real ones.

### 3.6 Hygiene
- God-node stoplist (`Json`, `$()`, `_()`, minified artifacts); dedupe repeated nodes ("Error Analysis" ×4).
- Add the vault to watch_paths (or a second graphify scope) so the brain sees itself.

## Litmus test

Ask gr0b: *"What do we know about `delta_drift.py`?"* — a healthy brain answers in one breath:
- **Map:** its callers, callees, community (graphify)
- **Journal:** the decision that validated it (decisions/)
- **Intent:** the open thread to extract it into Layer 2 Policy (insights/)

When that works, the brain has both memories and emotions.

## Order of work

1. 3.1 map fix (hours) → 2. 3.2 entity linking (the heart) → 3. 3.4 boot context (first felt utility) → 4. 3.5 doctor drift → 5. 3.3 rationale_for writeback → 6. 3.6 hygiene throughout.
