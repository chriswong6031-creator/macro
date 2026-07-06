"""Tests for admin/neural_web.py — Neural Web operator HQ panel (W8a).

Covers:
  - panel() shape against real committed artifacts (smoke test)
  - panel() against fixture artifacts (full + each section missing)
  - SLA breach math
  - No engine imports (static check)
"""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

# Add repo root to path so `from admin import neural_web` works
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ---------------------------------------------------------------------------
# Static check: admin.neural_web must NOT import engine modules
# ---------------------------------------------------------------------------

def test_no_engine_imports():
    """admin/neural_web.py must not import any engine/* or scripts/* module,
    and must not call subprocess."""
    src = (Path(__file__).resolve().parent.parent / "admin" / "neural_web.py").read_text()
    # Check only non-comment, non-docstring lines for actual import statements
    import_lines = [
        line for line in src.splitlines()
        if line.strip() and not line.strip().startswith("#") and not line.strip().startswith('"""') and not line.strip().startswith("'")
    ]
    code = "\n".join(import_lines)
    forbidden_patterns = [
        ("from engine", "engine module import"),
        ("import engine", "engine module import"),
        ("from scripts", "scripts module import"),
        ("import scripts", "scripts module import"),
        ("subprocess.run", "subprocess.run call"),
        ("subprocess.Popen", "subprocess.Popen call"),
        ("import subprocess", "subprocess import"),
    ]
    for pattern, label in forbidden_patterns:
        assert pattern not in code, f"Forbidden {label!r} found in non-comment lines"


# ---------------------------------------------------------------------------
# Smoke test against real committed artifacts
# ---------------------------------------------------------------------------

def test_panel_smoke():
    """panel() returns ok=True and all four sections with real artifacts."""
    from admin import neural_web

    d = neural_web.panel()
    assert d["ok"] is True
    for key in ("engine_health", "reflex_log", "bus_graph", "governance"):
        assert key in d, f"Missing section: {key}"


def test_engine_health_shape():
    from admin import neural_web

    eh = neural_web.panel()["engine_health"]
    assert "spine" in eh
    assert "kernel" in eh
    assert "sla" in eh
    assert "kernel_families" in eh
    assert "lagging" in eh
    assert "read_gate" in eh


def test_reflex_log_shape():
    from admin import neural_web

    rl = neural_web.panel()["reflex_log"]
    assert "n_registered" in rl
    assert "n_mirroring" in rl
    assert "per_reflex" in rl
    assert isinstance(rl["per_reflex"], list)
    # should have the 18 reflexes defined in config/reflexes.yml
    # (PR-5 added factor_deescalation_shadow as a dark scaffold — RUL-NW6)
    assert rl["n_registered"] == 18


def test_bus_graph_shape():
    from admin import neural_web

    bg = neural_web.panel()["bus_graph"]
    assert "n_nodes" in bg
    assert "n_edges" in bg
    assert "n_contradictions" in bg
    assert "edge_types" in bg
    assert isinstance(bg["n_nodes"], int) and bg["n_nodes"] > 0
    assert isinstance(bg["n_edges"], int) and bg["n_edges"] > 0


def test_governance_shape():
    from admin import neural_web

    gov = neural_web.panel()["governance"]
    assert "recent_events" in gov
    assert "probation" in gov
    assert "cortex_memo" in gov
    assert isinstance(gov["recent_events"], list)


def test_sla_math_real_artifacts():
    """SLA breach math: total artifacts must match synapse.yml count; breaches
    is a list of dicts with required fields."""
    from admin import neural_web

    sla = neural_web.panel()["engine_health"]["sla"]
    if sla.get("missing"):
        pytest.skip("pyyaml not available or synapse.yml missing")
    assert sla["total"] > 0
    assert isinstance(sla["n_breaches"], int)
    assert isinstance(sla["breaches"], list)
    for b in sla["breaches"]:
        assert "id" in b
        assert "sla_hours" in b
        assert "age_hours" in b
        # overdue means age > sla — verify the math
        assert b["age_hours"] > b["sla_hours"], (
            f"Breach entry {b['id']} has age {b['age_hours']} <= sla {b['sla_hours']}"
        )
        assert b["overdue_hours"] == round(b["age_hours"] - b["sla_hours"], 1)


def test_per_reflex_required_fields():
    from admin import neural_web

    rl = neural_web.panel()["reflex_log"]
    if rl.get("missing"):
        pytest.skip("reflexes.yml not parseable")
    for r in rl["per_reflex"]:
        for field in ("name", "mirroring", "push_tier_candidate", "n_firings_7d"):
            assert field in r, f"Missing field {field!r} in reflex {r.get('name')}"


# ---------------------------------------------------------------------------
# Fixture-based tests: each section missing
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_repo(tmp_path):
    """A minimal fake repo tree with all neuralweb artifacts present."""
    # Build directory structure
    nw = tmp_path / "data" / "neuralweb"
    nw.mkdir(parents=True)
    (nw / "cortex").mkdir()
    cfg = tmp_path / "config"
    cfg.mkdir()

    # spine envelope
    (nw / "spine_index.parquet.envelope.json").write_text(json.dumps({
        "produced_at": "2026-07-04T10:00:00Z",
        "inputs_hash": "sha256:abc123",
    }))
    (nw / "spine_index.parquet").write_bytes(b"fake")

    # kernel envelope + parquet stub (art-two in synapse.yml resolves to this path)
    (nw / "kernel_estimates.parquet.envelope.json").write_text(json.dumps({
        "produced_at": "2026-07-04T10:00:00Z",
    }))
    (nw / "kernel_estimates.parquet").write_bytes(b"fake")

    # kernel decisions
    (nw / "kernel_decisions.json").write_text(json.dumps({
        "batch_id": None,
        "n_survivors": 0,
        "n_eligible": 0,
        "next_batch_due": "2026-10-01",
        "note": "no batch run",
    }))

    # kernel families
    (nw / "kernel_families.json").write_text(json.dumps({
        "families": {
            "altdata": {
                "armed": False,
                "horizon_curve": {"5": 0.003},
                "recency_trend": {"all": {"n_eff": 10, "mean": 0.004}},
                "staleness": {"date_last": "2026-07-01", "days_since_last_fire": 3},
            },
            "policy": {
                "armed": True,
                "horizon_curve": {"5": 0.001},
                "recency_trend": {"all": {"n_eff": 30, "mean": 0.002}},
                "staleness": {"date_last": "2026-07-04", "days_since_last_fire": 0},
            },
        }
    }))

    # lagging signals
    (nw / "lagging_signals.json").write_text(json.dumps({
        "by_family": {
            "family_a": {"flagged": ["some_flag"], "n_recent_fires": 5},
            "family_b": {"flagged": [], "n_recent_fires": 3},
        }
    }))

    # read gate baseline
    (nw / "read_gate_baseline.json").write_text(json.dumps({
        "schema": "synapse-read-gate-baseline-v1",
        "findings": [
            {"module": "engine/foo.py", "artifact_id": "bar", "line_no": 1, "severity": "WARN"},
        ],
    }))

    # confluence graph
    (nw / "confluence_graph.json").write_text(json.dumps({
        "schema": "neuralweb.confluence_graph.v1",
        "nodes": list(range(10)),
        "edges": [{"edge_type": "feeds"}, {"edge_type": "contradicts"}],
        "contradiction_summary": {"n": 1, "by_severity": {"tension": 1}, "top_pair_ids": ["a-vs-b"]},
        "contradiction_records": [{"pair_id": "a-vs-b", "note": "tension between a and b"}],
        "display_only": True,
        "hard_law": "display only",
        "asof": "2026-07-04T10:00:00Z",
        "is_context_only": True,
    }))

    # governance.jsonl
    events = [
        {"schema": "neuralweb.governance.v1", "event_id": "aaa", "event_type": "article3_review",
         "target": "test_target", "ts": "2026-07-04T10:00:00+00:00", "article": 3,
         "authored_by": "test", "note": "test note"},
    ]
    (nw / "governance.jsonl").write_text("\n".join(json.dumps(e) for e in events))

    # cortex/memo.json
    (nw / "cortex" / "memo.json").write_text(json.dumps({
        "schema": "neuralweb.cortex_memo.v1",
        "as_of": "2026-07-04T12:00:00+00:00",
        "summary": "test summary",
        "what_fired": ["signal_x"],
        "contradictions_review": "none",
        "deserves_operator": [],
        "probation": {
            "tier": "A0/A1 shadow",
            "granted": False,
            "reason": "insufficient-n: n=0 < min_n=30",
            "attention_track_record": {"n": 0, "hits": 0},
            "lapses_at": None,
        },
        "tool_call_census": {"read_world_state": 1},
        "is_context_only": True,
    }))

    # synapse.yml
    synapse_yaml = """
meta:
  schema_version: 1
artifacts:
  art-one:
    path: data/neuralweb/spine_index.parquet
    format: parquet
    producer: engine/foo.py
    known_extra_writers: []
    owner_program: test
    cadence: daily-engine
    storage: git
    freshness_sla_hours: 24
    tier: infrastructure
  art-two:
    path: data/neuralweb/kernel_estimates.parquet
    format: parquet
    producer: engine/bar.py
    known_extra_writers: []
    owner_program: test
    cadence: daily-engine
    storage: git
    freshness_sla_hours: 0.001
    tier: infrastructure
"""
    (cfg / "synapse.yml").write_text(synapse_yaml)

    # reflexes.yml
    reflexes_yaml = """
meta:
  schema_version: 1
reflexes:
  test_reflex_a:
    description: A test reflex
    trigger:
      type: staleness_check
      lane: fastpath
    action:
      type: [rerun_engine]
    firings_jsonl: data/reflexes/test_reflex_a/firings.jsonl
    claim_family: reflex.test_reflex_a
    tier: infrastructure
    push_tier: false
    graded: false
  test_reflex_b:
    description: B test reflex with push tier
    trigger:
      type: price_shock
      lane: sentinel
    action:
      type: [send_alert]
    firings_jsonl: data/reflexes/test_reflex_b/firings.jsonl
    claim_family: reflex.test_reflex_b
    tier: infrastructure
    push_tier: true
    graded: false
"""
    (cfg / "reflexes.yml").write_text(reflexes_yaml)

    return tmp_path


def _make_panel_with_root(root: Path):
    """Import neural_web and patch _ROOT to point to tmp_path."""
    from admin import neural_web
    import importlib

    # Patch module-level path constants
    old_root = neural_web._ROOT
    neural_web._ROOT = root
    neural_web._DATA_NW = root / "data" / "neuralweb"
    neural_web._CONFIG = root / "config"
    neural_web._DATA_REFLEXES = root / "data" / "reflexes"
    neural_web._SPINE_ENVELOPE = neural_web._DATA_NW / "spine_index.parquet.envelope.json"
    neural_web._SPINE_PARQUET = neural_web._DATA_NW / "spine_index.parquet"
    neural_web._KERNEL_ENVELOPE = neural_web._DATA_NW / "kernel_estimates.parquet.envelope.json"
    neural_web._KERNEL_FAMILIES = neural_web._DATA_NW / "kernel_families.json"
    neural_web._KERNEL_DECISIONS = neural_web._DATA_NW / "kernel_decisions.json"
    neural_web._LAGGING_SIGNALS = neural_web._DATA_NW / "lagging_signals.json"
    neural_web._READ_GATE = neural_web._DATA_NW / "read_gate_baseline.json"
    neural_web._CONFLUENCE_GRAPH = neural_web._DATA_NW / "confluence_graph.json"
    neural_web._GOVERNANCE_JSONL = neural_web._DATA_NW / "governance.jsonl"
    neural_web._CORTEX_MEMO = neural_web._DATA_NW / "cortex" / "memo.json"
    neural_web._SYNAPSE_YML = neural_web._CONFIG / "synapse.yml"
    neural_web._REFLEXES_YML = neural_web._CONFIG / "reflexes.yml"
    try:
        return neural_web.panel()
    finally:
        # Restore
        neural_web._ROOT = old_root
        neural_web._DATA_NW = old_root / "data" / "neuralweb"
        neural_web._CONFIG = old_root / "config"
        neural_web._DATA_REFLEXES = old_root / "data" / "reflexes"
        neural_web._SPINE_ENVELOPE = neural_web._DATA_NW / "spine_index.parquet.envelope.json"
        neural_web._SPINE_PARQUET = neural_web._DATA_NW / "spine_index.parquet"
        neural_web._KERNEL_ENVELOPE = neural_web._DATA_NW / "kernel_estimates.parquet.envelope.json"
        neural_web._KERNEL_FAMILIES = neural_web._DATA_NW / "kernel_families.json"
        neural_web._KERNEL_DECISIONS = neural_web._DATA_NW / "kernel_decisions.json"
        neural_web._LAGGING_SIGNALS = neural_web._DATA_NW / "lagging_signals.json"
        neural_web._READ_GATE = neural_web._DATA_NW / "read_gate_baseline.json"
        neural_web._CONFLUENCE_GRAPH = neural_web._DATA_NW / "confluence_graph.json"
        neural_web._GOVERNANCE_JSONL = neural_web._DATA_NW / "governance.jsonl"
        neural_web._CORTEX_MEMO = neural_web._DATA_NW / "cortex" / "memo.json"
        neural_web._SYNAPSE_YML = neural_web._CONFIG / "synapse.yml"
        neural_web._REFLEXES_YML = neural_web._CONFIG / "reflexes.yml"


def test_fixture_full_panel(tmp_repo):
    """Full fixture: all sections return their data (not missing)."""
    d = _make_panel_with_root(tmp_repo)
    assert d["ok"] is True

    eh = d["engine_health"]
    assert not eh["spine"].get("missing")
    assert not eh["kernel"].get("missing")
    assert not eh["kernel_families"].get("missing")
    assert not eh["lagging"].get("missing")
    assert not eh["read_gate"].get("missing")

    rl = d["reflex_log"]
    assert not rl.get("missing")
    assert rl["n_registered"] == 2

    bg = d["bus_graph"]
    assert not bg.get("missing")
    assert bg["n_nodes"] == 10

    gov = d["governance"]
    assert not gov["probation"].get("missing")
    assert len(gov["recent_events"]) == 1
    assert gov["recent_events"][0]["event_type"] == "article3_review"


def test_fixture_sla_breach_math(tmp_repo):
    """SLA breach math: art-two file is back-dated by 50 hours;
    its SLA is 24h → must breach. art-one is freshly written → must not breach.
    Also verifies overdue_hours = round(age - sla, 1) for every breach."""
    import os
    import time

    # Back-date kernel_estimates.parquet by 50 hours (well past the 24h SLA)
    art_two_path = tmp_repo / "data" / "neuralweb" / "kernel_estimates.parquet"
    old_time = time.time() - (50 * 3600)
    os.utime(art_two_path, (old_time, old_time))

    # Update the synapse.yml so art-two has a 24h SLA (not 0.001, which rounds
    # to 0.0 for a just-written file and produces a floating-point false negative)
    synapse_yaml = """
meta:
  schema_version: 1
artifacts:
  art-one:
    path: data/neuralweb/spine_index.parquet
    format: parquet
    producer: engine/foo.py
    known_extra_writers: []
    owner_program: test
    cadence: daily-engine
    storage: git
    freshness_sla_hours: 24
    tier: infrastructure
  art-two:
    path: data/neuralweb/kernel_estimates.parquet
    format: parquet
    producer: engine/bar.py
    known_extra_writers: []
    owner_program: test
    cadence: daily-engine
    storage: git
    freshness_sla_hours: 24
    tier: infrastructure
"""
    (tmp_repo / "config" / "synapse.yml").write_text(synapse_yaml)

    d = _make_panel_with_root(tmp_repo)
    sla = d["engine_health"]["sla"]
    if sla.get("missing"):
        pytest.skip("pyyaml unavailable")

    assert sla["total"] == 2

    breach_ids = [b["id"] for b in sla["breaches"]]
    assert "art-two" in breach_ids, "art-two (back-dated 50h, sla=24h) must breach"
    assert "art-one" not in breach_ids, "art-one (just written, sla=24h) must not breach"

    # Verify overdue_hours math for every breach
    for b in sla["breaches"]:
        assert b["age_hours"] > b["sla_hours"]
        assert b["overdue_hours"] == round(b["age_hours"] - b["sla_hours"], 1)


def test_fixture_missing_spine(tmp_repo):
    """Missing spine envelope → section fails-open with missing=True."""
    (tmp_repo / "data" / "neuralweb" / "spine_index.parquet.envelope.json").unlink()
    d = _make_panel_with_root(tmp_repo)
    assert d["ok"] is True  # panel still returns ok
    assert d["engine_health"]["spine"].get("missing") is True


def test_fixture_missing_reflexes_yml(tmp_repo):
    """Missing reflexes.yml → reflex_log section fails-open."""
    (tmp_repo / "config" / "reflexes.yml").unlink()
    d = _make_panel_with_root(tmp_repo)
    assert d["ok"] is True
    assert d["reflex_log"].get("missing") is True


def test_fixture_missing_confluence_graph(tmp_repo):
    """Missing confluence_graph.json → bus_graph section fails-open."""
    (tmp_repo / "data" / "neuralweb" / "confluence_graph.json").unlink()
    d = _make_panel_with_root(tmp_repo)
    assert d["ok"] is True
    assert d["bus_graph"].get("missing") is True


def test_fixture_missing_governance(tmp_repo):
    """Missing governance.jsonl → recent_events is [] (not an error)."""
    (tmp_repo / "data" / "neuralweb" / "governance.jsonl").unlink()
    d = _make_panel_with_root(tmp_repo)
    assert d["ok"] is True
    assert d["governance"]["recent_events"] == []


def test_fixture_missing_cortex_memo(tmp_repo):
    """Missing cortex/memo.json → probation and cortex_memo fail-open."""
    (tmp_repo / "data" / "neuralweb" / "cortex" / "memo.json").unlink()
    d = _make_panel_with_root(tmp_repo)
    assert d["ok"] is True
    assert d["governance"]["probation"].get("missing") is True
    assert d["governance"]["cortex_memo"].get("missing") is True


def test_fixture_push_tier_candidates(tmp_repo):
    """test_reflex_b has push_tier: true → should appear as push_tier_candidate."""
    d = _make_panel_with_root(tmp_repo)
    rl = d["reflex_log"]
    if rl.get("missing"):
        pytest.skip("reflexes.yml not parseable")
    by_name = {r["name"]: r for r in rl["per_reflex"]}
    assert by_name["test_reflex_b"]["push_tier_candidate"] is True
    assert by_name["test_reflex_a"]["push_tier_candidate"] is False


def test_fixture_kernel_families_armed(tmp_repo):
    """policy family armed=True → appears in armed_names."""
    d = _make_panel_with_root(tmp_repo)
    kf = d["engine_health"]["kernel_families"]
    if kf.get("missing"):
        pytest.skip("kernel_families.json missing")
    assert kf["n_armed"] == 1
    assert "policy" in kf["armed_names"]
    assert kf["n_total"] == 2


def test_fixture_lagging_flags(tmp_repo):
    """family_a has a flagged entry → n_flagged >= 1."""
    d = _make_panel_with_root(tmp_repo)
    lg = d["engine_health"]["lagging"]
    if lg.get("missing"):
        pytest.skip("lagging_signals.json missing")
    assert lg["n_flagged"] == 1
    assert "family_a" in lg["flagged_names"]


if __name__ == "__main__":
    import pytest as _pytest
    _pytest.main([__file__, "-v"])
