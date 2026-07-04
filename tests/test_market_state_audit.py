"""engine/market_state_audit.py — forward-grade log + per-corroborator attribution.

W3 PR2 additions (tested here):
  - _extract_components: extracts {key: {score, weight}} from snapshot
  - _entry_from_snapshot: additive 'components' key in log entries
  - old entries without 'components' still parse safely (additive-safe)
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from engine import market_state_audit as A


@pytest.fixture
def spy(monkeypatch):
    """Deterministic SPY: flat at 100 for 120 business days, then a -10% leg on day 60,
    so a matured entry dated near day 55 PRECEDES a >=5% drawdown and an entry near day 0
    does not. Monkeypatched so the test never touches the real price store."""
    idx = pd.bdate_range("2026-01-01", periods=120)
    px = pd.Series(100.0, index=idx)
    px.iloc[60:] = 90.0          # a clean -10% step down
    monkeypatch.setattr(A, "_spy", lambda: px)
    return px


def _ms(asof, verdict, keys, state="caution", top=90):
    return {"asof": asof, "verdict": verdict, "score": 28, "raw_score": 61,
            "radar": {"state": state, "top_score": top, "amp": len(keys),
                      "amp_keys": keys, "severe_gated": True}}


def _ms_with_components(asof, verdict, keys, components):
    """Build a snapshot dict that includes a 'components' list (W3 PR2 addition)."""
    snap = _ms(asof, verdict, keys)
    snap["components"] = components
    return snap


_FIXTURE_COMPONENTS = [
    {"key": "trend", "score": 90, "weight": 0.24, "label_en": "Trend"},
    {"key": "risk",  "score": 42, "weight": 0.18, "label_en": "Risk"},
    {"key": "vol",   "score": 71, "weight": 0.16, "label_en": "Vol"},
    {"key": "breadth", "score": 56, "weight": 0.16, "label_en": "Breadth"},
    {"key": "liquidity", "score": 75, "weight": 0.14, "label_en": "Liquidity"},
    {"key": "stress", "score": 88, "weight": 0.12, "label_en": "Stress"},
]


def test_log_is_idempotent_by_asof(tmp_path, spy):
    snap = _ms("2026-02-02", "RISK_OFF", ["conjunction"])
    assert A.log_snapshot(snap, root=tmp_path) is True
    assert A.log_snapshot(snap, root=tmp_path) is False          # same as-of -> no dupe
    rows = A._read(A._path(tmp_path))
    assert len(rows) == 1 and rows[0]["amp_keys"] == ["conjunction"]


def test_grading_classifies_tp_fp_and_miss(tmp_path, spy):
    # day ~55 (before the -10% leg on day 60) -> drawdown follows
    A.log_snapshot(_ms("2026-03-20", "RISK_OFF", ["conjunction", "complacency"]), root=tmp_path)
    # day ~5 (flat region, no drawdown ahead) -> false positive
    A.log_snapshot(_ms("2026-01-08", "RISK_OFF", ["drawdown_band"]), root=tmp_path)
    # a quiet call right before the drawdown -> a miss
    A.log_snapshot(_ms("2026-03-20", "RISK_ON", [], state=None, top=None), root=tmp_path)  # dup asof, ignored
    A.log_snapshot(_ms("2026-03-23", "RISK_ON", [], state=None, top=None), root=tmp_path)
    assert A.grade_log(root=tmp_path) >= 2
    sc = A.scorecard(root=tmp_path)
    assert sc["n_graded"] >= 3
    outs = {r["asof"]: r["graded"]["outcome"] for r in A._read(A._path(tmp_path)) if r.get("graded")}
    assert outs["2026-03-20"] == "true_positive"
    assert outs["2026-01-08"] == "false_positive"
    assert outs["2026-03-23"] == "miss"


def test_unmatured_entry_is_not_graded(tmp_path, spy):
    # as-of at the very end of the series -> 21-bd horizon can't mature
    A.log_snapshot(_ms("2026-06-12", "RISK_OFF", ["conjunction"]), root=tmp_path)
    A.grade_log(root=tmp_path)
    rows = A._read(A._path(tmp_path))
    assert rows[0]["graded"] is None


def test_per_corroborator_attribution(tmp_path, spy):
    # conjunction present on a TP; drawdown_band present only on an FP
    A.log_snapshot(_ms("2026-03-20", "RISK_OFF", ["conjunction"]), root=tmp_path)        # TP
    A.log_snapshot(_ms("2026-01-08", "RISK_OFF", ["drawdown_band"]), root=tmp_path)      # FP
    A.grade_log(root=tmp_path)
    pc = A.scorecard(root=tmp_path)["per_corroborator"]
    assert pc["conjunction"]["precision"] == 1.0          # led the drawdown
    assert pc["drawdown_band"]["precision"] == 0.0        # did not -> a prune candidate


def test_empty_log_scorecard_is_safe():
    sc = A.scorecard(root="/nonexistent-root-xyz")
    assert sc["n_graded"] == 0 and "accruing" in sc["note"]


# ---------------------------------------------------------------------------
# W3 PR2 additions: component logging tests
# ---------------------------------------------------------------------------

class TestComponentLogging:
    """_entry_from_snapshot logs per-component scores; old entries parse safely."""

    def test_snapshot_with_components_logs_them(self, tmp_path):
        """A snapshot carrying a 'components' list produces an entry with 'components' key."""
        snap = _ms_with_components(
            "2026-07-04", "RISK_OFF", ["conjunction"], _FIXTURE_COMPONENTS
        )
        result = A._entry_from_snapshot(snap)
        assert result is not None
        assert "components" in result, "components key must be present when snapshot has components"
        comps = result["components"]
        assert isinstance(comps, dict), "components must be a dict"
        assert "trend" in comps
        assert comps["trend"]["score"] == 90
        assert abs(comps["trend"]["weight"] - 0.24) < 1e-9
        assert "stress" in comps
        assert comps["stress"]["score"] == 88

    def test_snapshot_without_components_no_key(self):
        """A snapshot without a 'components' field produces an entry WITHOUT 'components'."""
        snap = _ms("2026-07-04", "RISK_OFF", ["conjunction"])
        # No 'components' key in snap
        result = A._entry_from_snapshot(snap)
        assert result is not None
        assert "components" not in result, (
            "components key must be ABSENT when snapshot has no components list"
        )

    def test_all_six_components_stored(self):
        """All six components from the fixture are stored with correct keys."""
        snap = _ms_with_components(
            "2026-07-04", "MIXED", [], _FIXTURE_COMPONENTS
        )
        result = A._entry_from_snapshot(snap)
        assert result is not None
        comps = result.get("components", {})
        expected_keys = {"trend", "risk", "vol", "breadth", "liquidity", "stress"}
        assert set(comps.keys()) == expected_keys, (
            f"expected components keys {expected_keys}, got {set(comps.keys())}"
        )

    def test_component_entry_logged_to_jsonl(self, tmp_path):
        """log_snapshot writes components to the JSONL file and they round-trip."""
        snap = _ms_with_components(
            "2026-07-04", "RISK_OFF", ["complacency"], _FIXTURE_COMPONENTS
        )
        ok = A.log_snapshot(snap, root=tmp_path)
        assert ok is True
        rows = A._read(A._path(tmp_path))
        assert len(rows) == 1
        comps = rows[0].get("components")
        assert comps is not None, "components missing from logged JSONL row"
        assert comps["breadth"]["score"] == 56
        assert abs(comps["breadth"]["weight"] - 0.16) < 1e-9

    def test_old_entry_without_components_parses_safely(self, tmp_path):
        """Log entries written before W3 PR2 (no 'components' key) parse without error.

        Additive safety: the scorecard and grading functions must not raise when
        processing entries that lack the 'components' key.
        """
        # Write a pre-W3-PR2 entry directly (no components key)
        old_entry = {
            "asof": "2026-06-26",
            "verdict": "RISK_OFF",
            "score": 28,
            "raw_score": 61,
            "radar_state": "caution",
            "radar_top": 91,
            "amp": 3,
            "amp_keys": ["conjunction", "two_plus_scares", "complacency"],
            "severe_gated": True,
            "logged_at": "2026-06-28T10:12:17+00:00",
            "graded": None,
            # No 'components' key — simulates a pre-W3-PR2 entry
        }
        p = A._path(tmp_path)
        p.write_text(json.dumps(old_entry) + "\n")

        # scorecard must not raise
        sc = A.scorecard(root=tmp_path)
        # The entry is ungraded; scorecard returns 'accruing' note
        assert "n_graded" in sc

        # Adding a new entry WITH components alongside the old one must also work
        snap = _ms_with_components("2026-07-04", "MIXED", [], _FIXTURE_COMPONENTS)
        ok = A.log_snapshot(snap, root=tmp_path)
        assert ok is True
        rows = A._read(A._path(tmp_path))
        assert len(rows) == 2
        # Old row: no components
        assert "components" not in rows[0]
        # New row: has components
        assert "components" in rows[1]

    def test_extract_components_returns_none_for_empty_list(self):
        """_extract_components returns None for an empty components list."""
        result = A._extract_components({"components": []})
        assert result is None

    def test_extract_components_returns_none_for_missing_key(self):
        """_extract_components returns None when 'components' key is absent."""
        result = A._extract_components({"verdict": "RISK_OFF"})
        assert result is None

    def test_extract_components_handles_malformed_entry(self):
        """_extract_components skips non-dict elements gracefully."""
        snap = {
            "components": [
                {"key": "trend", "score": 90, "weight": 0.24},
                "not_a_dict",   # malformed — must be skipped
                {"key": "vol", "score": 71, "weight": 0.16},
            ]
        }
        result = A._extract_components(snap)
        assert result is not None
        assert "trend" in result
        assert "vol" in result
        # "not_a_dict" must not appear
        assert len(result) == 2
