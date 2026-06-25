#!/usr/bin/env python3
"""
Phase 3 acceptance tests (DR-003). Pure stdlib. Run:
    python3 -m unittest discover ~/.gr0b/scripts/tests -v

These tests ARE the contract. Flash: if a change makes these fail, the change
is wrong — do not edit the tests to make them pass.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from gr0b_graphlib import (  # noqa: E402
    Graph, GraphSchemaError, is_noise_label, load_graph,
)
from gr0b_link import extract_mentions, link_file  # noqa: E402


# ── Fixtures ──────────────────────────────────────────────────────────────────
def graph_variant_a() -> dict:
    """Canonical shape: nodes/edges, label/source_file."""
    return {
        "nodes": [
            {"id": "kairos_lab_delta_drift", "label": "delta_drift.py",
             "source_file": "Fded43cr/Deeper/prediction/kairos/kairos_lab/delta_drift.py",
             "type": "code", "community": 15},
            {"id": "raven_models_Dispatch", "label": "Dispatch",
             "source_file": "Fded43cr/Robot/_raven/core/models.py", "type": "code"},
            {"id": "raven_dispatcher_Dispatch", "label": "Dispatch",
             "source_file": "Fded43cr/Robot/_raven/core/dispatcher.py", "type": "code"},
            {"id": "raven_archive_Dispatch", "label": "Dispatch",
             "source_file": "Fded43cr/Robot/_raven/core/archive.py", "type": "code"},
            {"id": "raven_dispatcher_file", "label": "dispatcher.py",
             "source_file": "Fded43cr/Robot/_raven/core/dispatcher.py", "type": "code"},
            {"id": "sun_core_SunCore", "label": "SunCore",
             "source_file": "WSE/NBA/sun/sun_core.py", "type": "code"},
            {"id": "noise_json", "label": "Json",
             "source_file": "vendored/zig/lib/std/json.zig", "type": "code"},
            # "Error Analysis" clones: same label+source — must dedupe to one.
            {"id": "ea_1", "label": "Error Analysis", "source_file": "WSE/NBA/notebook.md"},
            {"id": "ea_2", "label": "Error Analysis", "source_file": "WSE/NBA/notebook.md"},
            {"id": "ea_3", "label": "Error Analysis", "source_file": "WSE/NBA/notebook.md"},
        ],
        "edges": [
            {"source": "raven_dispatcher_Dispatch", "target": "raven_archive_Dispatch",
             "relation": "uses", "confidence": "INFERRED"},
            {"source": "sun_core_SunCore", "target": "kairos_lab_delta_drift",
             "relation": "calls", "confidence": "EXTRACTED"},
        ],
    }


def graph_variant_b() -> dict:
    """Alt shape: links / src / dst / name — loader must map keys."""
    return {
        "nodes": [
            {"id": "n1", "name": "SunCore", "file": "WSE/NBA/sun/sun_core.py"},
            {"id": "n2", "name": "quick_test()", "file": "WSE/NBA/sun/sun_core.py"},
        ],
        "links": [{"src": "n2", "dst": "n1", "rel": "calls"}],
    }


def graph_real_schema() -> dict:
    """EXACT shape of the production export, per host probe 2026-06-12:
    NetworkX node-link JSON — 'links' container, norm_label, file_type,
    confidence_score + weight on edges. This fixture freezes that contract."""
    return {
        "directed": True,
        "multigraph": False,
        "graph": {},
        "hyperedges": [],
        "nodes": [
            {"_origin": "scan", "community": 15, "file_type": "code",
             "id": "kairos_lab_delta_drift", "label": "delta_drift.py",
             "norm_label": "delta_drift.py",
             "source_file": "Fded43cr/Deeper/prediction/kairos/kairos_lab/delta_drift.py",
             "source_location": "L1"},
            {"_origin": "scan", "community": 7, "file_type": "code",
             "id": "sun_core_SunCore", "label": "SunCore",
             "norm_label": "suncore",
             "source_file": "WSE/NBA/sun/sun_core.py", "source_location": "L12"},
        ],
        "links": [
            {"confidence": "EXTRACTED", "confidence_score": 0.93,
             "relation": "calls", "source": "sun_core_SunCore",
             "source_file": "WSE/NBA/sun/sun_core.py", "source_location": "L40",
             "target": "kairos_lab_delta_drift", "weight": 2.0},
        ],
    }


def write_graph(tmp: Path, data: dict) -> Path:
    p = tmp / "graph.json"
    p.write_text(json.dumps(data))
    return p


# ── Loader ────────────────────────────────────────────────────────────────────
class TestLoader(unittest.TestCase):
    def test_variant_a(self):
        with tempfile.TemporaryDirectory() as d:
            g = load_graph(write_graph(Path(d), graph_variant_a()))
        self.assertEqual(len(g.nodes), 10)
        self.assertEqual(len(g.edges), 2)
        self.assertEqual(g.edges[0].relation, "uses")
        self.assertIn("Dispatch", g.label_index)
        self.assertEqual(len(g.label_index["Dispatch"]), 3)

    def test_variant_b_key_mapping(self):
        with tempfile.TemporaryDirectory() as d:
            g = load_graph(write_graph(Path(d), graph_variant_b()))
        self.assertEqual(len(g.nodes), 2)
        self.assertEqual(len(g.edges), 1)
        self.assertIn("SunCore", g.label_index)
        self.assertIn("sun_core.py", g.basename_index)

    def test_real_production_schema(self):
        """The schema the host probe reported must load with full fidelity."""
        with tempfile.TemporaryDirectory() as d:
            g = load_graph(write_graph(Path(d), graph_real_schema()))
        self.assertEqual(len(g.nodes), 2)
        self.assertEqual(len(g.edges), 1)
        e = g.edges[0]
        self.assertEqual(e.relation, "calls")
        self.assertEqual(e.confidence, "EXTRACTED")
        self.assertAlmostEqual(e.confidence_score, 0.93)
        self.assertAlmostEqual(e.weight, 2.0)
        n = g.nodes["kairos_lab_delta_drift"]
        self.assertEqual(n.type, "code")            # mapped from file_type
        self.assertEqual(n.norm_label, "delta_drift.py")

    def test_norm_label_fallback_still_exact(self):
        """Mention misses label index but hits graphify's norm_label —
        an exact dict lookup, so the never-guess rule is untouched."""
        with tempfile.TemporaryDirectory() as d:
            g = load_graph(write_graph(Path(d), graph_real_schema()))
        # 'Suncore' (wrong case) misses label 'SunCore', hits norm 'suncore'
        r = g.resolve("Suncore")
        self.assertIsNotNone(r.linked)
        self.assertEqual(r.linked.id, "sun_core_SunCore")

    def test_unknown_schema_fails_loudly(self):
        with tempfile.TemporaryDirectory() as d:
            p = write_graph(Path(d), {"whatever": [1, 2, 3]})
            with self.assertRaises(GraphSchemaError):
                load_graph(p)

    def test_missing_file_message_has_instructions(self):
        with self.assertRaises(GraphSchemaError) as cm:
            load_graph(Path("/nonexistent/graph.json"))
        self.assertIn("graphify update", str(cm.exception))


# ── Resolution: the never-guess rule ─────────────────────────────────────────
class TestResolve(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.g = load_graph(write_graph(Path(self.tmp.name), graph_variant_a()))

    def tearDown(self):
        self.tmp.cleanup()

    def test_unique_label_links(self):
        r = self.g.resolve("SunCore")
        self.assertEqual(r.linked.id, "sun_core_SunCore")
        self.assertEqual(r.tier, "unique-label")

    def test_ambiguous_never_guesses(self):
        r = self.g.resolve("Dispatch")
        self.assertIsNone(r.linked)
        self.assertTrue(r.ambiguous)
        self.assertEqual(len(r.candidates), 3)

    def test_path_hint_disambiguates(self):
        r = self.g.resolve("Dispatch", path_hints=("_raven/core/dispatcher.py",))
        self.assertIsNotNone(r.linked)
        self.assertEqual(r.linked.id, "raven_dispatcher_Dispatch")
        self.assertEqual(r.tier, "path-qualified")

    def test_file_path_mention(self):
        r = self.g.resolve("kairos_lab/delta_drift.py")
        self.assertEqual(r.linked.id, "kairos_lab_delta_drift")
        self.assertEqual(r.tier, "file-path")

    def test_bare_filename_via_basename(self):
        r = self.g.resolve("delta_drift.py")
        self.assertEqual(r.linked.id, "kairos_lab_delta_drift")

    def test_clone_nodes_dedupe_to_unique(self):
        r = self.g.resolve("Error Analysis")
        self.assertIsNotNone(r.linked)   # 3 clones, same label+source → one
        self.assertEqual(r.tier, "unique-label")

    def test_noise_labels_never_link(self):
        for noise in ("Json", "_()", "$()", "self"):
            r = self.g.resolve(noise)
            self.assertIsNone(r.linked, f"{noise} must not link")

    def test_dead_refs(self):
        dead = self.g.find_dead_refs(["sun_core_SunCore", "ghost_node_42"])
        self.assertEqual(dead, ["ghost_node_42"])

    def test_noise_path_targets_never_link(self):
        """Field-test 2026-06-12: `after()` linked into poly_scourge bundler
        junk because the junk label happened to be unique. Noise-path nodes
        must be invisible to resolution."""
        data = graph_variant_a()
        data["nodes"].append({
            "id": "ps_zspecial", "label": "zspecial_thing()",
            "source_file": "WSE/poly_scourge_0i409/bundle.js"})
        import tempfile as tf
        with tf.TemporaryDirectory() as d:
            g = load_graph(write_graph(Path(d), data))
        r = g.resolve("zspecial_thing()")
        self.assertIsNone(r.linked, "bundler-junk target must never link")
        self.assertEqual(r.candidates, [])


# ── Mention extraction ────────────────────────────────────────────────────────
class TestExtraction(unittest.TestCase):
    def test_extracts_spans_paths_calls_camel(self):
        text = ("Look at `kairos_lab/delta_drift.py` — the SunCore engine calls "
                "quick_test() before dispatch. Claude and GitHub are not code.")
        mentions, hints = extract_mentions(text)
        self.assertIn("kairos_lab/delta_drift.py", mentions)
        self.assertIn("SunCore", mentions)
        self.assertIn("quick_test()", mentions)
        self.assertNotIn("Claude", mentions)
        self.assertNotIn("GitHub", mentions)
        self.assertIn("kairos_lab/delta_drift.py", hints)

    def test_noise_and_stopwords_excluded(self):
        mentions, _ = extract_mentions("Use `Json` with `$()` via Polymarket API")
        self.assertEqual(mentions, [])

    def test_generic_identifiers_never_extracted(self):
        """Field-test 2026-06-12: `nodes`, `window`, `report()`, `after()`
        linked to accidental unique labels. Bare generic words must not
        become mentions, even backticked."""
        text = ("Write `nodes:` frontmatter, hook `window` events, call "
                "`report()` then `after()` — but keep `quick_test()` and "
                "`SunCore` and `delta_drift.py`.")
        mentions, _ = extract_mentions(text)
        for bad in ("nodes", "nodes:", "window", "report()", "after()"):
            self.assertNotIn(bad, mentions)
        for good in ("quick_test()", "SunCore", "delta_drift.py"):
            self.assertIn(good, mentions)


# ── Linking files: frontmatter, idempotency ──────────────────────────────────
class TestLinkFile(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.g = load_graph(write_graph(self.root, graph_variant_a()))

    def tearDown(self):
        self.tmp.cleanup()

    def card(self, name: str, text: str) -> Path:
        p = self.root / name
        p.write_text(text)
        return p

    def test_links_written_to_frontmatter(self):
        p = self.card("c1.md", "Decision: bless `SunCore` and `kairos_lab/delta_drift.py`.\n")
        fr = link_file(p, self.g, apply=True)
        out = p.read_text()
        self.assertEqual(len(fr.linked), 2)
        self.assertTrue(out.startswith("---\n"))
        self.assertIn("gr0b_nodes:", out)
        self.assertIn("sun_core_SunCore", out)
        self.assertIn("kairos_lab_delta_drift", out)
        self.assertIn("Decision: bless", out)          # body intact

    def test_ambiguous_recorded_not_linked(self):
        p = self.card("c2.md", "The `Dispatch` model needs a refactor.\n")
        fr = link_file(p, self.g, apply=True)
        out = p.read_text()
        self.assertEqual(fr.linked, [])
        self.assertEqual(len(fr.ambiguous), 1)
        self.assertIn("gr0b_ambiguous:", out)
        self.assertNotIn("gr0b_nodes:", out)
        self.assertIn("3 candidates", out)

    def test_path_in_same_card_qualifies(self):
        p = self.card("c3.md",
                      "Refactor `Dispatch` in `_raven/core/dispatcher.py` soon.\n")
        fr = link_file(p, self.g, apply=True)
        ids = [nid for nid, _, _ in fr.linked]
        self.assertIn("raven_dispatcher_Dispatch", ids)

    def test_existing_frontmatter_preserved(self):
        p = self.card("c4.md",
                      "---\ntitle: My Decision\ntags:\n  - quant\n"
                      "gr0b_nodes:\n  - old_stale_id\n---\n\nBody with `SunCore`.\n")
        link_file(p, self.g, apply=True)
        out = p.read_text()
        self.assertIn("title: My Decision", out)
        self.assertIn("- quant", out)
        self.assertNotIn("old_stale_id", out)           # managed block replaced
        self.assertIn("sun_core_SunCore", out)

    def test_idempotent(self):
        p = self.card("c5.md", "Bless `SunCore`.\n")
        link_file(p, self.g, apply=True)
        first = p.read_text()
        link_file(p, self.g, apply=True)
        self.assertEqual(first, p.read_text())

    def test_body_never_modified(self):
        body = "# Title\n\nProse about `SunCore` and `Dispatch`.\n\n- a list\n"
        p = self.card("c6.md", body)
        link_file(p, self.g, apply=True)
        self.assertTrue(p.read_text().endswith(body))


# ── CLI: empty runs must fail loudly (zsh-comment-argv incident) ─────────────
class TestCliRefusesEmptyRun(unittest.TestCase):
    def test_garbage_targets_exit_2(self):
        import contextlib
        import io
        from gr0b_link import main as link_main
        with tempfile.TemporaryDirectory() as d:
            gp = write_graph(Path(d), graph_variant_a())
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = link_main(["--graph", str(gp), "#", "dry-run:", "watch"])
        self.assertEqual(rc, 2)
        out = buf.getvalue()
        self.assertIn("NO FILES TO LINK", out)
        self.assertIn("zsh", out)          # the hint that explains the trap


# ── Map generator behavior (subprocess, uses patched gr0b_map.py) ────────────
class TestMapGenerator(unittest.TestCase):
    def run_map(self, data: dict):
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        gp = write_graph(root, data)
        out = root / "BRAIN_MAP.md"
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "gr0b_map.py"), str(gp), str(out)],
            capture_output=True, text=True, timeout=60)
        return tmp, proc, out

    def test_refuses_zero_edge_export(self):
        data = graph_variant_a()
        data["edges"] = []
        tmp, proc, out = self.run_map(data)
        with tmp:
            self.assertEqual(proc.returncode, 3, proc.stdout + proc.stderr)
            self.assertFalse(out.exists(), "must not write a roadless map")
            self.assertIn("probe", (proc.stdout + proc.stderr).lower())

    def test_writes_map_with_real_edge_count(self):
        tmp, proc, out = self.run_map(graph_variant_a())
        with tmp:
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            content = out.read_text()
            self.assertIn("2 edges", content)
            self.assertNotIn("0 edges", content)


if __name__ == "__main__":
    unittest.main(verbosity=2)
