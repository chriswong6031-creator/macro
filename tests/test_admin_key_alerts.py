"""Tests for admin/key_alerts.py — the landing "needs your eyes" rail.

Covers: composition + ranking on fixture artifacts, per-section fail-open (missing and
malformed), the priority/age triage filters, the brief_prompt nudge content, the item
cap, a real-artifact smoke, and the admin no-engine-imports law (static check).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

REPO_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Static check: admin.key_alerts must NOT import engine modules / subprocess
# ---------------------------------------------------------------------------

def test_no_engine_imports():
    src = (REPO_ROOT / "admin" / "key_alerts.py").read_text()
    import_lines = [
        line for line in src.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    code = "\n".join(import_lines)
    for pattern in ("from engine", "import engine", "from scripts", "import scripts",
                    "import subprocess", "subprocess.run", "subprocess.Popen"):
        assert pattern not in code, f"admin/key_alerts.py must not use {pattern!r}"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _seed(tmp_path, *, chains=True, tripwires=True, feed=True,
          feed_ts="2099-01-01T00:00:00"):
    """Build a fixture artifact tree and point admin.paths at it."""
    data = tmp_path / "data"
    site = tmp_path / "site"
    if chains:
        (data / "transmission").mkdir(parents=True, exist_ok=True)
        (data / "transmission" / "chain_state.json").write_text(json.dumps({
            "asof": "2026-08-05",
            "chains": [
                {"chain": "quiet_chain", "state": "dormant",
                 "title": {"en": "Quiet", "zh": "静"}, "hops": []},
                {"chain": "hot_chain", "state": "expressed",
                 "title": {"en": "Dollar spike → EM headwind", "zh": "美元飙升"},
                 "asof": "2026-08-03",
                 "hops": [{"confirmed": True}, {"confirmed": True}]},
                {"chain": "warming_chain", "state": "arming",
                 "title": {"en": "Real-rate peak watch", "zh": "实际利率见顶观察"},
                 "hops": [{"confirmed": True}, {"confirmed": False}]},
            ],
        }))
    if tripwires:
        (data / "cycle_ontology").mkdir(parents=True, exist_ok=True)
        (data / "cycle_ontology" / "tripwire_state.json").write_text(json.dumps({
            "long-bonds.bear_steepener.v1": {
                "version": 1, "state": "FIRED", "fired_on": "2026-07-29",
                "latched": True, "current_leg": True, "as_of": "2026-08-05"},
            "semis.top_2026.v1": {
                "version": 1, "state": "ARMED", "fired_on": None,
                "latched": False, "current_leg": False, "as_of": "2026-08-05"},
        }))
        (data / "cycle_ontology" / "falsifiers.json").write_text(json.dumps({
            "entries": [{"id": "long-bonds.bear_steepener.v1",
                         "claim": "long-bond regime is a bear steepener"}],
        }))
    if feed:
        (site / "alertsdata").mkdir(parents=True, exist_ok=True)
        (site / "alertsdata" / "feed.json").write_text(json.dumps({
            "generated_utc": feed_ts,
            "alerts": [
                {"alert_id": "fresh-high", "emit_ts": feed_ts, "priority": 82,
                 "severity": "critical", "surface": "vector:risk_regime",
                 "title": "Risk Off Signal changed"},
                {"alert_id": "stale-high", "emit_ts": "2020-01-01T00:00:00",
                 "priority": 90, "severity": "critical", "surface": "x",
                 "title": "Ancient alert"},
                {"alert_id": "fresh-low", "emit_ts": feed_ts, "priority": 40,
                 "severity": "info", "surface": "y", "title": "Low priority"},
            ],
        }))
    return data, site


@pytest.fixture()
def patched_paths(tmp_path, monkeypatch):
    data, site = _seed(tmp_path)
    import admin.paths as paths
    monkeypatch.setattr(paths, "DATA", data, raising=True)
    monkeypatch.setattr(paths, "SITE", site, raising=True)
    return tmp_path


# ---------------------------------------------------------------------------
# Composition + ranking
# ---------------------------------------------------------------------------

def test_panel_full_fixture(patched_paths):
    from admin import key_alerts
    p = key_alerts.panel()
    assert p["available"] is True
    kinds = [(i["kind"], i["state"]) for i in p["items"]]
    # expressed cascade ranks first, FIRED tripwire beats propagating/arming/triage
    assert kinds[0] == ("cascade", "expressed")
    assert ("tripwire", "FIRED") in kinds
    assert ("triage", "P82") in kinds
    # dormant chain, ARMED tripwire, stale-high and fresh-low alerts all excluded
    ids = [i["id"] for i in p["items"]]
    assert "quiet_chain" not in ids and "stale-high" not in ids and "fresh-low" not in ids
    assert "semis.top_2026.v1" not in ids
    assert p["counts"] == {"cascades": 2, "tripwires": 1, "triage": 1}
    # ranking: expressed(0) < tripwire(2) < triage(4) < arming(5)
    order = [i["kind"] for i in p["items"]]
    assert order.index("cascade") < order.index("tripwire") < order.index("triage")
    assert p["items"][-1]["state"] == "arming"


def test_brief_prompts_are_self_contained(patched_paths):
    from admin import key_alerts
    items = {}
    for i in key_alerts.panel()["items"]:      # keep the FIRST (highest-salience) per kind
        items.setdefault(i["kind"], i)
    casc = items["cascade"]["brief_prompt"]
    assert "data/transmission/chain_state.json" in casc
    assert "knowledge/transmission/hot_chain.yaml" in casc
    assert "state=expressed" in casc and "2/2 hops confirmed" in casc
    trip = items["tripwire"]["brief_prompt"]
    assert "long-bonds.bear_steepener.v1" in trip
    assert "bear steepener" in trip                # claim enriched from falsifiers.json
    assert "condition still holding" in trip       # current_leg=True
    tri = items["triage"]["brief_prompt"]
    assert "site/alertsdata/feed.json" in tri and "fresh-high" in tri


def test_each_section_missing_fail_open(tmp_path, monkeypatch):
    import admin.paths as paths
    from admin import key_alerts
    for keep in ("chains", "tripwires", "feed"):
        root = tmp_path / keep
        data, site = _seed(root, chains=keep == "chains",
                           tripwires=keep == "tripwires", feed=keep == "feed")
        monkeypatch.setattr(paths, "DATA", data, raising=True)
        monkeypatch.setattr(paths, "SITE", site, raising=True)
        p = key_alerts.panel()
        assert p["available"] is True
        assert p["items"], f"section {keep} alone should still yield items"
        assert sum(p["counts"].values()) == len(p["items"]) or p["truncated"]


def test_malformed_artifacts_never_raise(tmp_path, monkeypatch):
    import admin.paths as paths
    from admin import key_alerts
    data = tmp_path / "data"
    site = tmp_path / "site"
    (data / "transmission").mkdir(parents=True)
    (data / "transmission" / "chain_state.json").write_text("{not json")
    (data / "cycle_ontology").mkdir(parents=True)
    (data / "cycle_ontology" / "tripwire_state.json").write_text("[]")  # wrong shape
    monkeypatch.setattr(paths, "DATA", data, raising=True)
    monkeypatch.setattr(paths, "SITE", site, raising=True)   # feed absent entirely
    p = key_alerts.panel()
    assert p["available"] is True and p["items"] == []


def test_item_cap_and_truncated_flag(tmp_path, monkeypatch):
    import admin.paths as paths
    from admin import key_alerts
    data = tmp_path / "data"
    site = tmp_path / "site"
    (data / "transmission").mkdir(parents=True)
    (data / "transmission" / "chain_state.json").write_text(json.dumps({
        "asof": "2026-08-05",
        "chains": [{"chain": f"c{i}", "state": "arming",
                    "title": {"en": f"Chain {i}", "zh": "链"}, "hops": []}
                   for i in range(12)],
    }))
    monkeypatch.setattr(paths, "DATA", data, raising=True)
    monkeypatch.setattr(paths, "SITE", site, raising=True)
    p = key_alerts.panel()
    assert len(p["items"]) == key_alerts._MAX_ITEMS
    assert p["truncated"] is True and p["total"] == 12


# ---------------------------------------------------------------------------
# Real-artifact smoke — never raises against the committed tree
# ---------------------------------------------------------------------------

def test_real_artifact_smoke():
    from admin import key_alerts
    p = key_alerts.panel()
    assert p["available"] is True
    assert isinstance(p["items"], list) and isinstance(p["counts"], dict)
    for it in p["items"]:
        assert it["kind"] in ("cascade", "tripwire", "triage")
        assert it["brief_prompt"] and it["title"]
