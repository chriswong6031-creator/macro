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


# ---------------------------------------------------------------------------
# Section E: Factor Intelligence — fixture helper
# ---------------------------------------------------------------------------

def _patch_factor_paths(neural_web, root: Path) -> dict:
    """Set the factor intelligence path constants to point at tmp root.
    Returns a dict of (attr_name → old_value) for restoration."""
    nw = root / "data" / "neuralweb"
    reflexes = root / "data" / "reflexes"
    saved = {}
    patches = {
        "_FACTOR_STATE": nw / "factor_intelligence_state.json",
        "_FACTOR_FIRINGS": reflexes / "factor_attention" / "firings.jsonl",
        "_FACTOR_GRADES": reflexes / "factor_attention" / "grades.jsonl",
        "_FACTOR_PROBATION": reflexes / "factor_attention" / "probation.json",
        "_FACTOR_CONTRADICTIONS": nw / "factor_contradictions.jsonl",
    }
    for attr, val in patches.items():
        saved[attr] = getattr(neural_web, attr)
        setattr(neural_web, attr, val)
    return saved


def _restore_factor_paths(neural_web, saved: dict) -> None:
    for attr, val in saved.items():
        setattr(neural_web, attr, val)


def _make_panel_with_root_fi(root: Path):
    """Like _make_panel_with_root but also patches Section E factor paths."""
    from admin import neural_web

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
    saved_factor = _patch_factor_paths(neural_web, root)
    try:
        return neural_web.panel()
    finally:
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
        _restore_factor_paths(neural_web, saved_factor)


def _write_factor_state(root: Path, n_dates: int = 80, granted: bool = False,
                        pair_g_dormant: bool = True, n_today: int = 0) -> None:
    """Write a synthetic factor_intelligence_state.json to the fixture root."""
    nw = root / "data" / "neuralweb"
    nw.mkdir(parents=True, exist_ok=True)
    state = {
        "schema": "neuralweb.factor_intelligence_state.v1",
        "as_of": "2026-07-06",
        "produced_at": "2026-07-06T08:00:00+00:00",
        "is_context_only": True,
        "display_only": True,
        "panel": {
            "available": True,
            "n_dates": n_dates,
            "latest_date": "2026-07-06",
            "history_floor_met": n_dates >= 60,
            "n_tickers_latest": 500,
        },
        "factor_weather": {
            "style_regime": "growth",
            "factor_leader": "profitability",
            "factor_leader_ic": 0.045,
            "display_only": True,
        },
        "contradictions": {
            "pair_g": {
                "dormant": pair_g_dormant,
                "n_today": n_today,
                "latest": [],
            }
        },
        "attention": {
            "factor_attention": {
                "n_firings": 12,
                "n_graded": 3,
                "granted": granted,
                "tier": "A0/A1 shadow",
                "reason": "insufficient-n: n=3 < min_n=25",
                "latest_firings": [],
            }
        },
        "hypotheses": {
            f"h{i}": {"status": "accruing", "authority": "display"}
            for i in range(1, 6)
        },
        "allowed_actions": {
            "may_explain": True,
            "may_flag_attention": True,
            "may_deescalate": False,
            "may_rank": False,
            "may_originate": False,
            "authority_source": "constitution.grant_authority + prereg gates; this block is a mirror, never a switch",
        },
        "gaps": [],
    }
    (nw / "factor_intelligence_state.json").write_text(json.dumps(state))


# ---------------------------------------------------------------------------
# Section E — smoke test (real repo artifacts)
# ---------------------------------------------------------------------------

def test_panel_has_factor_intelligence_section():
    """panel() includes factor_intelligence section (Section E)."""
    from admin import neural_web
    d = neural_web.panel()
    assert "factor_intelligence" in d, "Missing factor_intelligence section in panel()"
    fi = d["factor_intelligence"]
    assert "state_missing" in fi
    assert "panel_health" in fi
    assert "pair_g" in fi
    assert "factor_attention" in fi
    assert "hypotheses" in fi
    assert "alerts" in fi
    assert isinstance(fi["alerts"], list)


# ---------------------------------------------------------------------------
# Section E — fixture tests
# ---------------------------------------------------------------------------

def test_fi_absent_artifact(tmp_repo):
    """When state artifact is absent, state_missing=True and section fails-open."""
    # Do NOT write a factor state — absence is the default
    d = _make_panel_with_root_fi(tmp_repo)
    assert d["ok"] is True
    fi = d["factor_intelligence"]
    assert fi["state_missing"] is True
    assert isinstance(fi["alerts"], list)


def test_fi_present_artifact_floor_met(tmp_repo):
    """With n_dates=80 (>=60), floor_met=True and section not missing."""
    _write_factor_state(tmp_repo, n_dates=80)
    d = _make_panel_with_root_fi(tmp_repo)
    fi = d["factor_intelligence"]
    assert fi["state_missing"] is False
    assert fi["panel_health"]["floor_met"] is True
    assert fi["panel_health"]["n_dates"] == 80


def test_fi_present_artifact_floor_pending(tmp_repo):
    """With n_dates=30 (<60), floor_met=False and dormancy alert fires."""
    _write_factor_state(tmp_repo, n_dates=30)
    d = _make_panel_with_root_fi(tmp_repo)
    fi = d["factor_intelligence"]
    assert fi["state_missing"] is False
    assert fi["panel_health"]["floor_met"] is False
    # Dormancy alert must be present
    dormancy_alerts = [a for a in fi["alerts"] if "n_dates" in a and "dormant" in a.lower()]
    assert dormancy_alerts, f"Expected dormancy alert with n_dates=30, got alerts: {fi['alerts']}"


def test_fi_attention_not_granted(tmp_repo):
    """Attention not granted by default → granted=False in section."""
    _write_factor_state(tmp_repo, granted=False)
    d = _make_panel_with_root_fi(tmp_repo)
    fi = d["factor_intelligence"]
    assert fi["factor_attention"]["granted"] is False


def test_fi_attention_granted_triggers_alert(tmp_repo):
    """attention.granted=True → §9.2 alert fires about A3 wiring."""
    _write_factor_state(tmp_repo, granted=True)
    d = _make_panel_with_root_fi(tmp_repo)
    fi = d["factor_intelligence"]
    assert fi["factor_attention"]["granted"] is True
    wiring_alerts = [a for a in fi["alerts"] if "A3" in a or "granted" in a.lower()]
    assert wiring_alerts, f"Expected A3 wiring alert when granted=True, got: {fi['alerts']}"


def test_fi_hypotheses_all_present(tmp_repo):
    """hypotheses block contains h1..h5 entries."""
    _write_factor_state(tmp_repo)
    d = _make_panel_with_root_fi(tmp_repo)
    fi = d["factor_intelligence"]
    hyp = fi["hypotheses"]
    for hi in ("h1", "h2", "h3", "h4", "h5"):
        assert hi in hyp, f"Missing hypothesis {hi} in section E"
        assert "status" in hyp[hi]


def test_fi_no_rank_score_alert_when_clean(tmp_repo):
    """Clean state (may_rank=False, may_originate=False) → no rank/score alert."""
    _write_factor_state(tmp_repo)
    d = _make_panel_with_root_fi(tmp_repo)
    fi = d["factor_intelligence"]
    rank_alerts = [a for a in fi["alerts"] if "may_rank" in a or "may_originate" in a]
    assert not rank_alerts, f"Unexpected rank/score alert on clean state: {rank_alerts}"


def test_fi_bad_allowed_actions_triggers_alert(tmp_repo):
    """may_rank=True in state artifact → alert fires (RUL-NW9)."""
    nw = tmp_repo / "data" / "neuralweb"
    nw.mkdir(parents=True, exist_ok=True)
    bad_state = {
        "schema": "neuralweb.factor_intelligence_state.v1",
        "as_of": "2026-07-06",
        "produced_at": "2026-07-06T08:00:00+00:00",
        "is_context_only": True,
        "display_only": True,
        "panel": {"available": False, "n_dates": None, "history_floor_met": False},
        "factor_weather": {},
        "contradictions": {"pair_g": {"dormant": True, "n_today": 0, "latest": []}},
        "attention": {"factor_attention": {
            "n_firings": 0, "n_graded": 0, "granted": False,
            "tier": "A0/A1 shadow", "reason": "insufficient-n",
        }},
        "hypotheses": {f"h{i}": {"status": "not-visible-in-tree"} for i in range(1, 6)},
        "allowed_actions": {
            "may_explain": True, "may_flag_attention": True,
            "may_deescalate": False, "may_rank": True,  # <-- BAD
            "may_originate": False,
        },
        "gaps": [],
    }
    (nw / "factor_intelligence_state.json").write_text(json.dumps(bad_state))
    d = _make_panel_with_root_fi(tmp_repo)
    fi = d["factor_intelligence"]
    rank_alerts = [a for a in fi["alerts"] if "may_rank" in a]
    assert rank_alerts, f"Expected may_rank=True alert, got: {fi['alerts']}"


def test_fi_display_only_and_is_context_only(tmp_repo):
    """Section E always carries display_only=True and is_context_only=True."""
    _write_factor_state(tmp_repo)
    d = _make_panel_with_root_fi(tmp_repo)
    fi = d["factor_intelligence"]
    assert fi.get("display_only") is True
    assert fi.get("is_context_only") is True


def test_no_engine_imports_still_passes():
    """Re-verify engine import check still passes after Section E addition."""
    src = (Path(__file__).resolve().parent.parent / "admin" / "neural_web.py").read_text()
    import_lines = [
        line for line in src.splitlines()
        if line.strip() and not line.strip().startswith("#") and not line.strip().startswith('"""') and not line.strip().startswith("'")
    ]
    code = "\n".join(import_lines)
    for pattern, label in [
        ("from engine", "engine module import"),
        ("import engine", "engine module import"),
        ("from scripts", "scripts module import"),
        ("import scripts", "scripts module import"),
        ("subprocess.run", "subprocess.run call"),
        ("subprocess.Popen", "subprocess.Popen call"),
        ("import subprocess", "subprocess import"),
    ]:
        assert pattern not in code, f"Forbidden {label!r} found in non-comment lines"


# ---------------------------------------------------------------------------
# PR-A: run_status in cortex_memo + legacy memo fallback
# ---------------------------------------------------------------------------

def test_cortex_memo_run_status_present(tmp_repo):
    """A modern memo WITH run_status → cortex_memo.run_status must be returned as-is."""
    modern_memo = {
        "schema": "neuralweb.cortex_memo.v1",
        "as_of": "2026-07-06T12:00:00+00:00",
        "summary": "modern memo",
        "what_fired": [],
        "contradictions_review": "",
        "deserves_operator": [],
        "probation": {"tier": "A0/A1 shadow", "granted": False, "reason": "insufficient-n",
                      "attention_track_record": {"n": 0, "hits": 0}, "lapses_at": None},
        "tool_call_census": {"read_world_state": 2, "write_memo": 1},
        "is_context_only": True,
        "run_status": {
            "status": "ok",
            "degraded": False,
            "degradation_reason": None,
            "provider_attempts": [{"provider": "oauth", "model": "claude-opus-4-8",
                                    "attempted": True, "ok": True, "error_type": None,
                                    "error_message": None}],
            "tool_call_batches": 3,
            "individual_tool_calls": 3,
            "expected_min_tool_calls": 1,
            "context_stale": False,
            "context_as_of": None,
        },
    }
    (tmp_repo / "data" / "neuralweb" / "cortex" / "memo.json").write_text(
        json.dumps(modern_memo), encoding="utf-8"
    )
    d = _make_panel_with_root(tmp_repo)
    cm = d["governance"]["cortex_memo"]
    rs = cm.get("run_status", {})
    assert rs.get("status") == "ok"
    assert rs.get("degraded") is False
    assert rs.get("_legacy_memo") is None  # not a legacy memo


def test_cortex_memo_legacy_fallback_no_run_status(tmp_repo):
    """An old memo WITHOUT run_status → admin derives run_status from tool_call_census."""
    legacy_memo = {
        "schema": "neuralweb.cortex_memo.v1",
        "as_of": "2026-07-04T12:00:00+00:00",
        "summary": "legacy memo — no run_status field",
        "what_fired": ["signal_x"],
        "contradictions_review": "none",
        "deserves_operator": [],
        "probation": {"tier": "A0/A1 shadow", "granted": False,
                      "reason": "insufficient-n: n=0 < min_n=30",
                      "attention_track_record": {"n": 0, "hits": 0}, "lapses_at": None},
        "tool_call_census": {"read_world_state": 1},
        "is_context_only": True,
        # No run_status key at all
    }
    (tmp_repo / "data" / "neuralweb" / "cortex" / "memo.json").write_text(
        json.dumps(legacy_memo), encoding="utf-8"
    )
    d = _make_panel_with_root(tmp_repo)
    cm = d["governance"]["cortex_memo"]
    rs = cm.get("run_status", {})
    # Admin must derive a sensible status from tool_call_census
    assert "status" in rs
    assert rs.get("_legacy_memo") is True
    # census has read_world_state → has_tools=True → status should be warn (not degraded)
    assert rs["status"] in ("warn", "ok")


def test_cortex_memo_legacy_empty_census_degraded(tmp_repo):
    """Old memo with empty tool_call_census → admin derives degraded run_status."""
    legacy_memo = {
        "schema": "neuralweb.cortex_memo.v1",
        "as_of": "2026-07-04T12:00:00+00:00",
        "summary": "Budget exhausted after 0 tool-call batches",
        "what_fired": [],
        "contradictions_review": "",
        "deserves_operator": [],
        "probation": {"tier": "A0/A1 shadow", "granted": False,
                      "reason": "insufficient-n: n=0 < min_n=30",
                      "attention_track_record": {"n": 0, "hits": 0}, "lapses_at": None},
        "tool_call_census": {},
        "is_context_only": True,
    }
    (tmp_repo / "data" / "neuralweb" / "cortex" / "memo.json").write_text(
        json.dumps(legacy_memo), encoding="utf-8"
    )
    d = _make_panel_with_root(tmp_repo)
    cm = d["governance"]["cortex_memo"]
    rs = cm.get("run_status", {})
    assert rs.get("_legacy_memo") is True
    assert rs.get("status") == "degraded"
    assert rs.get("degraded") is True


if __name__ == "__main__":
    import pytest as _pytest
    _pytest.main([__file__, "-v"])
