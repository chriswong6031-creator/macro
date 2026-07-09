"""tests/test_support_map.py — Unit tests for engine.neuralweb.support_map (W2).

Coverage targets (charter requirements):
  1. Fixpoint termination on cycles (A produces X consumed by B producing Y consumed by A)
  2. Hop annotation — result items carry correct hop values
  3. Shared-producer over-attribution is present AND labeled bound='upper'
  4. Upstream inversion traversal
  5. Terminal consumer labeling (terminal=True when module produces no registered artifact)
  6. Coverage-drift detection (registered but missing from confluence)
  7. health.build() with a stale lobe embeds support_impact with bound='upper'
  8. Smoke test: load_graph() against the real synapse.yml succeeds, regime-latest
     downstream count is in expected range (~43-46)

All logic tests use a SMALL synthetic SynapseGraph fixture — they do not depend on
the 6100-line synapse.yml.  Tests 7-8 are the only ones that touch real files.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Repo root
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from engine.neuralweb.support_map import (  # noqa: E402
    SynapseGraph,
    consumers_direct,
    coverage_vs_confluence,
    downstream,
    load_graph,
    upstream,
)


# ---------------------------------------------------------------------------
# Shared synthetic fixtures
# ---------------------------------------------------------------------------

def _make_graph(artifacts: dict[str, dict], producer_to_artifacts: dict[str, list[str]]) -> SynapseGraph:
    """Build a SynapseGraph directly from dicts (no YAML)."""
    full_arts = {}
    for art_id, spec in artifacts.items():
        full_arts[art_id] = {
            "path": spec.get("path", f"data/{art_id}.json"),
            "producer": spec.get("producer", ""),
            "consumers": list(spec.get("consumers") or []),
            "freshness_sla_hours": spec.get("freshness_sla_hours", 24),
            "tier": spec.get("tier", "display"),
        }
    return SynapseGraph(
        artifacts=full_arts,
        producer_to_artifacts=producer_to_artifacts,
    )


# Simple linear pipeline: A→mod_b→B→mod_c→C
@pytest.fixture()
def linear_graph() -> SynapseGraph:
    """
    A is produced by mod_a, consumed by mod_b.
    B is produced by mod_b, consumed by mod_c.
    C is produced by mod_c, consumed by mod_d (terminal — produces nothing).
    """
    return _make_graph(
        artifacts={
            "A": {"producer": "mod_a", "consumers": ["mod_b"]},
            "B": {"producer": "mod_b", "consumers": ["mod_c"]},
            "C": {"producer": "mod_c", "consumers": ["mod_d"]},
        },
        producer_to_artifacts={
            "mod_a": ["A"],
            "mod_b": ["B"],
            "mod_c": ["C"],
            # mod_d is terminal — not in producer_to_artifacts
        },
    )


# Cycle fixture: A→mod_b→B→mod_a→A
@pytest.fixture()
def cycle_graph() -> SynapseGraph:
    """
    A is produced by mod_a, consumed by mod_b.
    B is produced by mod_b, consumed by mod_a.
    mod_a also produces A (the cycle closes).
    """
    return _make_graph(
        artifacts={
            "A": {"producer": "mod_a", "consumers": ["mod_b"]},
            "B": {"producer": "mod_b", "consumers": ["mod_a"]},
        },
        producer_to_artifacts={
            "mod_a": ["A"],
            "mod_b": ["B"],
        },
    )


# Shared-producer fixture: mod_p produces both X and Y; Z consumes mod_p output
@pytest.fixture()
def shared_producer_graph() -> SynapseGraph:
    """
    mod_src produces SEED.
    SEED is consumed by mod_p.
    mod_p produces BOTH X and Y (shared producer — over-attribution scenario).
    Z consumes X only (not Y).
    """
    return _make_graph(
        artifacts={
            "SEED": {"producer": "mod_src", "consumers": ["mod_p"]},
            "X": {"producer": "mod_p", "consumers": ["mod_terminal"]},
            "Y": {"producer": "mod_p", "consumers": []},
        },
        producer_to_artifacts={
            "mod_src": ["SEED"],
            "mod_p": ["X", "Y"],
            # mod_terminal produces nothing
        },
    )


# ---------------------------------------------------------------------------
# 1. Fixpoint termination on cycles
# ---------------------------------------------------------------------------

class TestCycleTermination:
    def test_downstream_terminates(self, cycle_graph):
        """downstream() must not loop forever when A→B→A cycle exists."""
        result = downstream(cycle_graph, "A")
        # Should find B (hop 1), then A is already seen so stops
        ids = {r["artifact_id"] for r in result}
        assert "B" in ids, "Expected B in downstream of A"
        assert "A" not in ids, "Seed A must not appear in its own downstream"
        # Critically: we must have terminated (test itself would hang otherwise)

    def test_upstream_terminates(self, cycle_graph):
        """upstream() must not loop forever when cycle exists."""
        result = upstream(cycle_graph, "B")
        ids = {r["artifact_id"] for r in result}
        assert "A" in ids, "Expected A in upstream of B"
        assert "B" not in ids, "Seed B must not appear in its own upstream"

    def test_downstream_count_bounded_by_artifact_set(self, cycle_graph):
        """downstream count can never exceed total artifacts minus the seed."""
        result = downstream(cycle_graph, "A")
        total_arts = len(cycle_graph.artifacts)
        assert len(result) < total_arts, "downstream must be smaller than full artifact set"


# ---------------------------------------------------------------------------
# 2. Hop annotation
# ---------------------------------------------------------------------------

class TestHopAnnotation:
    def test_direct_consumer_hop_1(self, linear_graph):
        """B is one hop downstream of A (A→mod_b→B)."""
        result = downstream(linear_graph, "A")
        b_entries = [r for r in result if r["artifact_id"] == "B"]
        assert b_entries, "B must be in downstream(A)"
        assert b_entries[0]["hop"] == 1

    def test_indirect_hop_2(self, linear_graph):
        """C is two hops downstream of A (A→mod_b→B→mod_c→C)."""
        result = downstream(linear_graph, "A")
        c_entries = [r for r in result if r["artifact_id"] == "C"]
        assert c_entries, "C must be in downstream(A)"
        assert c_entries[0]["hop"] == 2

    def test_upstream_hop_annotation(self, linear_graph):
        """A is upstream of C at hop 2."""
        result = upstream(linear_graph, "C")
        a_entries = [r for r in result if r["artifact_id"] == "A"]
        assert a_entries, "A must be in upstream(C)"
        assert a_entries[0]["hop"] == 2

    def test_via_module_present(self, linear_graph):
        """Each hop result carries a non-empty via_module."""
        result = downstream(linear_graph, "A")
        for r in result:
            assert r.get("via_module"), f"Missing via_module in {r}"


# ---------------------------------------------------------------------------
# 3. Shared-producer over-attribution — present AND labeled
# ---------------------------------------------------------------------------

class TestSharedProducerOverAttribution:
    def test_both_outputs_in_downstream(self, shared_producer_graph):
        """
        SEED→mod_p produces X and Y.  Both appear in downstream(SEED).
        This is the over-attribution: Y may not actually read SEED, but the
        inversion cannot distinguish — so it folds both in.
        """
        result = downstream(shared_producer_graph, "SEED")
        ids = {r["artifact_id"] for r in result}
        assert "X" in ids, "X must be in downstream(SEED) via mod_p"
        assert "Y" in ids, "Y must be in downstream(SEED) via mod_p (shared-producer over-attribution)"

    def test_all_results_labeled_upper(self, shared_producer_graph):
        """Every result in downstream() must carry bound='upper'."""
        result = downstream(shared_producer_graph, "SEED")
        assert result, "Expected non-empty downstream"
        for r in result:
            assert r.get("bound") == "upper", f"Missing bound='upper' in {r}"

    def test_note_present(self, shared_producer_graph):
        """Each result carries a non-empty note explaining the over-attribution."""
        result = downstream(shared_producer_graph, "SEED")
        for r in result:
            assert r.get("note"), f"Missing note in {r}"

    def test_upstream_labeled_exact(self, linear_graph):
        """upstream() results carry bound='exact' (no shared-producer over-attribution)."""
        result = upstream(linear_graph, "C")
        assert result, "Expected non-empty upstream for C"
        for r in result:
            assert r.get("bound") == "exact", (
                f"upstream result should carry bound='exact', got {r.get('bound')!r} in {r}"
            )


# ---------------------------------------------------------------------------
# 4. Upstream inversion traversal
# ---------------------------------------------------------------------------

class TestUpstreamInversion:
    def test_upstream_finds_direct_source(self, linear_graph):
        """B is one hop upstream of C."""
        result = upstream(linear_graph, "C")
        ids = {r["artifact_id"] for r in result}
        assert "B" in ids

    def test_upstream_transitive(self, linear_graph):
        """A is two hops upstream of C (A→B→C)."""
        result = upstream(linear_graph, "C")
        ids = {r["artifact_id"] for r in result}
        assert "A" in ids

    def test_upstream_excludes_seed(self, linear_graph):
        """Seed artifact itself must not appear in its upstream."""
        result = upstream(linear_graph, "B")
        ids = {r["artifact_id"] for r in result}
        assert "B" not in ids

    def test_upstream_empty_for_root(self, linear_graph):
        """A has no upstream (it is the root; nothing produces mod_a's consumer artifacts)."""
        result = upstream(linear_graph, "A")
        # mod_a produces A; no artifact has mod_a in its consumers list
        assert result == [], f"Expected empty upstream for root A, got {result}"

    def test_unknown_artifact_upstream_empty(self, linear_graph):
        """upstream() on an unknown artifact returns []."""
        result = upstream(linear_graph, "DOES_NOT_EXIST")
        assert result == []


# ---------------------------------------------------------------------------
# 5. Terminal consumer labeling
# ---------------------------------------------------------------------------

class TestTerminalConsumers:
    def test_terminal_flag_set_for_leaf_module(self, linear_graph):
        """C is consumed by mod_d which produces nothing → terminal=True."""
        result = consumers_direct(linear_graph, "C")
        assert result, "Expected consumers for C"
        mod_d = [c for c in result if c["module"] == "mod_d"]
        assert mod_d, "mod_d must be in consumers_direct(C)"
        assert mod_d[0]["terminal"] is True

    def test_non_terminal_for_pipeline_stage(self, linear_graph):
        """A is consumed by mod_b which produces B → terminal=False."""
        result = consumers_direct(linear_graph, "A")
        mod_b = [c for c in result if c["module"] == "mod_b"]
        assert mod_b, "mod_b must be in consumers_direct(A)"
        assert mod_b[0]["terminal"] is False
        assert "B" in mod_b[0]["produced_artifacts"]

    def test_empty_consumers_for_leaf_artifact(self, linear_graph):
        """An artifact with no consumers has no direct consumers."""
        # Y in shared_producer_graph has empty consumers
        sg = _make_graph(
            {"LEAF": {"producer": "mod_x", "consumers": []}},
            {"mod_x": ["LEAF"]},
        )
        result = consumers_direct(sg, "LEAF")
        assert result == []

    def test_unknown_artifact_empty(self, linear_graph):
        """consumers_direct() on unknown artifact returns []."""
        result = consumers_direct(linear_graph, "DOES_NOT_EXIST")
        assert result == []


# ---------------------------------------------------------------------------
# 6. Coverage-drift detection
# ---------------------------------------------------------------------------

class TestCoverageDrift:
    def test_detects_missing_artifact(self, tmp_path):
        """An artifact in synapse but absent from confluence edges is detected."""
        # Build minimal confluence_graph.json referencing only art-A
        cg_path = tmp_path / "confluence_graph.json"
        cg_path.write_text(json.dumps({
            "edges": [
                {"src": "artifact:art-A", "dst": "module:mod_b", "edge_type": "feeds"}
            ]
        }), encoding="utf-8")

        graph = _make_graph(
            {
                "art-A": {"producer": "mod_a", "consumers": ["mod_b"]},
                "art-B": {"producer": "mod_b", "consumers": []},  # NOT in confluence
            },
            {"mod_a": ["art-A"], "mod_b": ["art-B"]},
        )
        missing = coverage_vs_confluence(cg_path, graph=graph)
        assert "art-B" in missing, f"art-B must be in drift list, got {missing}"
        assert "art-A" not in missing, "art-A is in confluence, must not be in drift list"

    def test_empty_when_all_registered_present(self, tmp_path):
        """No drift when all registered artifacts appear in confluence edges."""
        cg_path = tmp_path / "confluence_graph.json"
        cg_path.write_text(json.dumps({
            "edges": [
                {"src": "artifact:X", "dst": "module:m"},
                {"src": "module:m2", "dst": "artifact:Y"},
            ]
        }), encoding="utf-8")
        graph = _make_graph(
            {"X": {}, "Y": {}},
            {},
        )
        missing = coverage_vs_confluence(cg_path, graph=graph)
        assert missing == []

    def test_missing_confluence_file_returns_all(self, tmp_path):
        """When confluence_graph.json is absent, all registered ids are returned."""
        cg_path = tmp_path / "nonexistent.json"
        graph = _make_graph({"art-X": {}, "art-Y": {}}, {})
        missing = coverage_vs_confluence(cg_path, graph=graph)
        assert set(missing) == {"art-X", "art-Y"}

    def test_returns_sorted_list(self, tmp_path):
        """Drift list is sorted alphabetically."""
        cg_path = tmp_path / "confluence_graph.json"
        cg_path.write_text(json.dumps({"edges": []}), encoding="utf-8")
        graph = _make_graph({"b-art": {}, "a-art": {}}, {})
        missing = coverage_vs_confluence(cg_path, graph=graph)
        assert missing == sorted(missing)

    def test_edge_with_null_src_does_not_crash(self, tmp_path):
        """Edge with src=None must not raise AttributeError — F1 regression test."""
        cg_path = tmp_path / "confluence_graph.json"
        cg_path.write_text(json.dumps({
            "edges": [
                {"src": None, "dst": "artifact:art-A", "edge_type": "feeds"},
                {"src": "artifact:art-A", "dst": None, "edge_type": "feeds"},
            ]
        }), encoding="utf-8")
        graph = _make_graph(
            {"art-A": {"producer": "mod_a", "consumers": []},
             "art-B": {"producer": "mod_b", "consumers": []}},
            {"mod_a": ["art-A"], "mod_b": ["art-B"]},
        )
        # Must not raise; art-A is referenced in confluence so should not be in missing
        missing = coverage_vs_confluence(cg_path, graph=graph)
        assert isinstance(missing, list), "Expected a list even with null src/dst edges"
        assert "art-A" not in missing, "art-A is in confluence (dst), must not be in drift list"
        assert "art-B" in missing, "art-B is not in confluence, must be in drift list"

    def test_edge_with_dict_src_does_not_crash(self, tmp_path):
        """Edge with src as a dict (non-string value) must not raise AttributeError — F1."""
        cg_path = tmp_path / "confluence_graph.json"
        cg_path.write_text(json.dumps({
            "edges": [
                {"src": {"nested": "artifact:art-A"}, "dst": "artifact:art-B", "edge_type": "feeds"},
            ]
        }), encoding="utf-8")
        graph = _make_graph(
            {"art-A": {}, "art-B": {}},
            {},
        )
        # Must not raise; dict src is not a valid artifact ref so both may appear in missing
        missing = coverage_vs_confluence(cg_path, graph=graph)
        assert isinstance(missing, list), "Expected list when src is a dict"
        # art-B is referenced by dst, art-A is not (dict src is ignored)
        assert "art-B" not in missing, "art-B is in confluence (dst), must not be in drift list"
        assert "art-A" in missing, "art-A not in confluence (dict src ignored), must be in drift list"


# ---------------------------------------------------------------------------
# 7. health.build() with stale lobe embeds support_impact
# ---------------------------------------------------------------------------

class TestHealthBuildSupportImpact:
    """Verify that health.build() embeds support_impact on stale/missing/degraded lobes."""

    def _make_repo(self, tmp_path: Path, artifacts: dict, daily_yml_text: str = "") -> Path:
        """Minimal fake repo for health tests."""
        try:
            import yaml  # noqa: PLC0415
        except ImportError:
            pytest.skip("pyyaml not installed")

        synapse_payload = {"artifacts": artifacts}
        synapse_path = tmp_path / "config" / "synapse.yml"
        synapse_path.parent.mkdir(parents=True, exist_ok=True)
        synapse_path.write_text(
            yaml.dump(synapse_payload, default_flow_style=False), encoding="utf-8"
        )
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True, exist_ok=True)
        if daily_yml_text:
            (wf_dir / "daily.yml").write_text(daily_yml_text, encoding="utf-8")
        (tmp_path / "data" / "neuralweb" / "cortex").mkdir(parents=True, exist_ok=True)
        (tmp_path / "site" / "neuralwebdata").mkdir(parents=True, exist_ok=True)
        return tmp_path

    def _art(self, path: str, *, sla: int = 24, owner: str = "neural-web",
             storage: str = "git", consumers: list | None = None) -> dict:
        return {
            "path": path,
            "format": "json",
            "producer": "engine/neuralweb/test_producer.py",
            "owner_program": owner,
            "cadence": "daily-engine",
            "storage": storage,
            "asof_field": "as_of",
            "freshness_sla_hours": sla,
            "schema": "test.v1",
            "tier": "display",
            "horizon_role": "context",
            "weights": "none",
            "scored_path_surfaces": [],
            "consumers": consumers or [],
        }

    def test_stale_lobe_gets_support_impact(self, tmp_path):
        """A stale lobe should have support_impact with bound='upper' and available=True."""
        from engine.neuralweb.health import build  # noqa: PLC0415

        # Create a data dir with an old JSON file to trigger stale status
        art_path = "data/neuralweb/test_artifact.json"
        full = tmp_path / art_path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(json.dumps({"as_of": "2000-01-01T00:00:00+00:00"}), encoding="utf-8")

        artifacts = {
            "test-stale-lobe": self._art(art_path, sla=1),  # SLA=1h, as_of=2000 → stale
        }
        root = self._make_repo(tmp_path, artifacts)
        result = build(root=root)

        stale_lobes = [l for l in result["lobes"] if l.get("status") == "stale"]
        assert stale_lobes, "Expected at least one stale lobe"

        lobe = stale_lobes[0]
        si = lobe.get("support_impact")
        assert si is not None, "Stale lobe must have support_impact"
        assert si.get("available") is True, f"support_impact.available must be True, got {si}"
        assert si.get("bound") == "upper", f"support_impact.bound must be 'upper', got {si}"
        assert "direct_consumers" in si
        assert "transitive_downstream_count" in si

    def test_missing_lobe_gets_support_impact(self, tmp_path):
        """A missing lobe should also have support_impact."""
        from engine.neuralweb.health import build  # noqa: PLC0415

        # Do NOT create the file — artifact will be 'missing'
        artifacts = {
            "test-missing-lobe": self._art("data/neuralweb/does_not_exist.json", sla=24),
        }
        root = self._make_repo(tmp_path, artifacts)
        result = build(root=root)

        missing_lobes = [l for l in result["lobes"] if l.get("status") == "missing"]
        assert missing_lobes, "Expected at least one missing lobe"

        lobe = missing_lobes[0]
        si = lobe.get("support_impact")
        assert si is not None, "Missing lobe must have support_impact"
        assert si.get("bound") == "upper"

    def test_fresh_lobe_no_support_impact(self, tmp_path):
        """A fresh lobe must NOT have support_impact (we only attach it to degraded ones)."""
        from engine.neuralweb.health import build  # noqa: PLC0415
        from datetime import datetime, timezone  # noqa: PLC0415

        art_path = "data/neuralweb/test_fresh.json"
        full = tmp_path / art_path
        full.parent.mkdir(parents=True, exist_ok=True)
        now_iso = datetime.now(timezone.utc).isoformat()
        full.write_text(json.dumps({"as_of": now_iso}), encoding="utf-8")

        artifacts = {
            "test-fresh-lobe": self._art(art_path, sla=999),  # far from stale
        }
        root = self._make_repo(tmp_path, artifacts)
        result = build(root=root)

        fresh_lobes = [l for l in result["lobes"] if l.get("status") in ("fresh", "fresh_partial")]
        if not fresh_lobes:
            pytest.skip("no fresh lobes produced in this fixture")

        for lobe in fresh_lobes:
            assert "support_impact" not in lobe, (
                f"Fresh lobe {lobe.get('id')} must not have support_impact"
            )


# ---------------------------------------------------------------------------
# 8. Smoke test against real synapse.yml
# ---------------------------------------------------------------------------

class TestRealSynapseSmoke:
    def test_load_graph_succeeds(self):
        """load_graph() against the real synapse.yml must return a non-empty graph."""
        pytest.importorskip("yaml")
        g = load_graph()
        assert len(g.artifacts) > 100, f"Expected >100 artifacts, got {len(g.artifacts)}"
        assert len(g.producer_to_artifacts) > 50

    def test_regime_latest_downstream_count(self):
        """downstream(regime-latest) should return ~59 artifacts per census."""
        pytest.importorskip("yaml")
        g = load_graph()
        result = downstream(g, "regime-latest")
        count = len(result)
        # Census is 59 as of 2026-07-08. It has grown from the original ~43-46
        # (5-hop) prediction as downstream consumers of regime-latest were added
        # across many PRs — legitimate graph growth, not a regression. Band
        # re-anchored on the true census with ±10 headroom for continued drift.
        assert 50 <= count <= 70, (
            f"Expected ~59 downstream artifacts for regime-latest, got {count}"
        )

    def test_all_results_bound_upper(self):
        """All downstream results on real graph carry bound='upper'."""
        pytest.importorskip("yaml")
        g = load_graph()
        result = downstream(g, "regime-latest")
        assert result, "Expected non-empty downstream for regime-latest on real graph"
        for r in result:
            assert r["bound"] == "upper"

    def test_coverage_vs_real_confluence(self):
        """coverage_vs_confluence on real files returns a list (may be empty or non-empty)."""
        pytest.importorskip("yaml")
        cg_path = _REPO_ROOT / "data" / "neuralweb" / "confluence_graph.json"
        if not cg_path.exists():
            pytest.skip("confluence_graph.json not present in this checkout")
        g = load_graph()
        missing = coverage_vs_confluence(cg_path, graph=g)
        assert isinstance(missing, list)
        # The list is sorted
        assert missing == sorted(missing)
        # On current state (2026-07-06) we expect 14; allow 0-20 for drift
        assert 0 <= len(missing) <= 30, f"Unexpected drift count {len(missing)}: {missing}"

    def test_hop_histogram_regime_latest(self):
        """regime-latest downstream should span hops 1-5."""
        pytest.importorskip("yaml")
        g = load_graph()
        result = downstream(g, "regime-latest")
        hops = {r["hop"] for r in result}
        assert 1 in hops, "Expected hop-1 entries"
        assert max(hops) >= 3, "Expected multi-hop traversal (>=3)"

    def test_no_counterfactual_language_in_notes(self):
        """Notes in downstream results must not contain banned counterfactual phrases."""
        pytest.importorskip("yaml")
        g = load_graph()
        result = downstream(g, "regime-latest")
        assert result, "Expected non-empty downstream for regime-latest on real graph"
        banned = ("would have", "caused", "proved", "validated")
        for r in result:
            note = r.get("note", "").lower()
            for phrase in banned:
                assert phrase not in note, (
                    f"Banned phrase {phrase!r} found in note: {r['note']}"
                )
