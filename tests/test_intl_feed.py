"""engine/intl_feed.py tests — weight policy, staleness, arbitration rule,
fail-soft behaviour, and the DIRECTIONAL add-tilt ledger-bug guard.

Run: python -m pytest tests/test_intl_feed.py -v
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from datetime import date, timedelta

import pytest

# Ensure the repo root is on the path when run directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import intl_feed as feed


# ---------------------------------------------------------------------------
# helpers: build minimal fixture trees in tmp_path
# ---------------------------------------------------------------------------

def _make_ledger(tmp_path: Path, features: list[dict]) -> Path:
    """Write a ledger.json into tmp_path's intl_bridge dir; return repo root."""
    d = tmp_path / "data" / "intl_bridge"
    d.mkdir(parents=True)
    (d / "ledger.json").write_text(json.dumps({
        "asof": "2026-07-02",
        "family": "intl_bridge",
        "features": features,
    }))
    return tmp_path


def _make_parquet(tmp_path: Path, group: str, name: str, last_date_offset_days: int) -> None:
    """Write a minimal parquet so store.last_date() returns today-offset days."""
    import pandas as pd
    d = tmp_path / "data" / group
    d.mkdir(parents=True, exist_ok=True)
    last = date.today() - timedelta(days=last_date_offset_days)
    df = pd.DataFrame({"value": [1.0]}, index=pd.to_datetime([last]))
    df.index.name = "date"
    df.to_parquet(d / f"{name}.parquet")


def _feat(overrides: dict | None = None) -> dict:
    """Minimal valid CONFIRMED de-risk feature."""
    base = {
        "id": "test_feat",
        "channel": "C2",
        "hypothesis": "test",
        "direction": "de-risk",
        "verdict": "CONFIRMED",
        "weight_cap": 0.10,
        "metrics": {},
        "gates": {},
        "source_series": [],
        "freshness_sla_days": 7,
        "validation_ref": "test",
        "kill": False,
        "notes": "",
    }
    if overrides:
        base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# weight policy tests
# ---------------------------------------------------------------------------

class TestWeightPolicy:
    def test_confirmed_full_weight(self, tmp_path):
        root = _make_ledger(tmp_path, [_feat({"weight_cap": 0.12})])
        states = feed.features(root)
        assert "test_feat" in states
        assert states["test_feat"]["weight"] == pytest.approx(0.12)
        assert not states["test_feat"]["stale"]

    def test_directional_de_risk_half_weight(self, tmp_path):
        root = _make_ledger(tmp_path, [
            _feat({"verdict": "DIRECTIONAL", "direction": "de-risk", "weight_cap": 0.10})
        ])
        states = feed.features(root)
        assert states["test_feat"]["weight"] == pytest.approx(0.05)

    def test_directional_add_tilt_is_ledger_bug_weight_zero(self, tmp_path):
        """DIRECTIONAL + add-tilt is a ledger bug: weight must be 0 and notes must warn."""
        root = _make_ledger(tmp_path, [
            _feat({"verdict": "DIRECTIONAL", "direction": "add-tilt", "weight_cap": 0.10})
        ])
        states = feed.features(root)
        assert states["test_feat"]["weight"] == 0.0
        assert "ledger bug" in states["test_feat"]["notes"].lower()

    def test_context_verdict_weight_zero(self, tmp_path):
        root = _make_ledger(tmp_path, [_feat({"verdict": "CONTEXT", "weight_cap": 0.10})])
        states = feed.features(root)
        assert states["test_feat"]["weight"] == 0.0

    def test_inverted_verdict_weight_zero(self, tmp_path):
        root = _make_ledger(tmp_path, [_feat({"verdict": "INVERTED", "weight_cap": 0.10})])
        states = feed.features(root)
        assert states["test_feat"]["weight"] == 0.0

    def test_pending_verdict_weight_zero(self, tmp_path):
        root = _make_ledger(tmp_path, [_feat({"verdict": "PENDING", "weight_cap": 0.10})])
        states = feed.features(root)
        assert states["test_feat"]["weight"] == 0.0

    def test_kill_true_weight_zero(self, tmp_path):
        root = _make_ledger(tmp_path, [_feat({"kill": True, "weight_cap": 0.10})])
        states = feed.features(root)
        assert states["test_feat"]["weight"] == 0.0

    def test_kill_true_overrides_confirmed(self, tmp_path):
        """kill=True must win over CONFIRMED verdict."""
        root = _make_ledger(tmp_path, [_feat({"kill": True, "verdict": "CONFIRMED", "weight_cap": 0.12})])
        states = feed.features(root)
        assert states["test_feat"]["weight"] == 0.0


# ---------------------------------------------------------------------------
# staleness tests
# ---------------------------------------------------------------------------

class TestStaleness:
    def test_fresh_series_not_stale(self, tmp_path):
        _make_parquet(tmp_path, "fred", "AU_yield_10y", last_date_offset_days=3)
        root = _make_ledger(tmp_path, [
            _feat({
                "source_series": ["fred/AU_yield_10y"],
                "freshness_sla_days": 7,
                "weight_cap": 0.10,
            })
        ])
        states = feed.features(root)
        assert not states["test_feat"]["stale"]
        assert states["test_feat"]["weight"] == pytest.approx(0.10)
        assert states["test_feat"]["data_age_days"] == 3

    def test_stale_series_zeroes_weight(self, tmp_path):
        """A series 13 days old with SLA 7 days must force weight to 0."""
        _make_parquet(tmp_path, "fred", "AU_yield_10y", last_date_offset_days=13)
        root = _make_ledger(tmp_path, [
            _feat({
                "source_series": ["fred/AU_yield_10y"],
                "freshness_sla_days": 7,
                "weight_cap": 0.10,
            })
        ])
        states = feed.features(root)
        assert states["test_feat"]["stale"]
        assert states["test_feat"]["weight"] == 0.0
        assert states["test_feat"]["data_age_days"] == 13

    def test_missing_series_is_stale(self, tmp_path):
        """A source_series with no on-disk parquet must be treated as stale."""
        root = _make_ledger(tmp_path, [
            _feat({
                "source_series": ["fred/NONEXISTENT_SERIES"],
                "freshness_sla_days": 7,
                "weight_cap": 0.10,
            })
        ])
        states = feed.features(root)
        assert states["test_feat"]["stale"]
        assert states["test_feat"]["weight"] == 0.0

    def test_one_stale_series_marks_whole_feature_stale(self, tmp_path):
        """If any one source_series is stale, the whole feature is stale."""
        _make_parquet(tmp_path, "fred", "AU_yield_10y", last_date_offset_days=1)
        _make_parquet(tmp_path, "fred", "JP_yield_10y", last_date_offset_days=20)
        root = _make_ledger(tmp_path, [
            _feat({
                "source_series": ["fred/AU_yield_10y", "fred/JP_yield_10y"],
                "freshness_sla_days": 7,
                "weight_cap": 0.10,
            })
        ])
        states = feed.features(root)
        assert states["test_feat"]["stale"]
        assert states["test_feat"]["weight"] == 0.0

    def test_stale_overrides_confirmed(self, tmp_path):
        """Even a CONFIRMED verdict must yield weight=0 when data is stale."""
        _make_parquet(tmp_path, "fred", "REER", last_date_offset_days=30)
        root = _make_ledger(tmp_path, [
            _feat({
                "verdict": "CONFIRMED",
                "source_series": ["fred/REER"],
                "freshness_sla_days": 14,
                "weight_cap": 0.12,
            })
        ])
        states = feed.features(root)
        assert states["test_feat"]["stale"]
        assert states["test_feat"]["weight"] == 0.0

    def test_no_source_series_not_stale(self, tmp_path):
        """A feature with an empty source_series list is not stale by default."""
        root = _make_ledger(tmp_path, [_feat({"source_series": [], "weight_cap": 0.10})])
        states = feed.features(root)
        assert not states["test_feat"]["stale"]
        assert states["test_feat"]["weight"] == pytest.approx(0.10)


# ---------------------------------------------------------------------------
# fail-soft tests
# ---------------------------------------------------------------------------

class TestFailSoft:
    def test_absent_ledger_returns_empty(self, tmp_path):
        """No ledger.json → empty dict, no exception."""
        states = feed.features(tmp_path)
        assert states == {}

    def test_malformed_ledger_returns_empty(self, tmp_path):
        d = tmp_path / "data" / "intl_bridge"
        d.mkdir(parents=True)
        (d / "ledger.json").write_text("NOT JSON {{{{")
        states = feed.features(tmp_path)
        assert states == {}

    def test_ledger_wrong_root_type_returns_empty(self, tmp_path):
        d = tmp_path / "data" / "intl_bridge"
        d.mkdir(parents=True)
        (d / "ledger.json").write_text(json.dumps([1, 2, 3]))
        states = feed.features(tmp_path)
        assert states == {}

    def test_features_missing_key_skips_gracefully(self, tmp_path):
        """A feature missing required keys should be skipped, not crash the whole call."""
        root = _make_ledger(tmp_path, [
            {"id": "good_feat", "channel": "C2", "direction": "de-risk",
             "verdict": "CONFIRMED", "weight_cap": 0.10, "source_series": [],
             "freshness_sla_days": 7, "validation_ref": "", "kill": False, "notes": ""},
            None,                                 # bad entry
            {"verdict": "CONFIRMED"},             # missing id
        ])
        states = feed.features(root)
        assert "good_feat" in states
        assert states["good_feat"]["weight"] == pytest.approx(0.10)

    def test_multiple_features_isolated(self, tmp_path):
        """Errors in one feature must not infect others."""
        root = _make_ledger(tmp_path, [
            _feat({"id": "feat_a", "weight_cap": 0.12}),
            _feat({"id": "feat_b", "verdict": "CONTEXT", "weight_cap": 0.08}),
        ])
        states = feed.features(root)
        assert states["feat_a"]["weight"] == pytest.approx(0.12)
        assert states["feat_b"]["weight"] == 0.0


# ---------------------------------------------------------------------------
# arbitration tests
# ---------------------------------------------------------------------------

class TestArbitrate:
    def _confirmed_state(self, fid: str, direction: str, weight: float = 0.10) -> dict:
        return {
            "id": fid, "channel": "C2", "direction": direction,
            "verdict": "CONFIRMED", "weight": weight, "weight_cap": weight,
            "stale": False, "data_age_days": 1,
            "validation_ref": "", "notes": "",
        }

    def test_no_firing_features_no_derisk(self):
        states = {
            "dr": self._confirmed_state("dr", "de-risk"),
            "at": self._confirmed_state("at", "add-tilt"),
        }
        result = feed.arbitrate(states, firing=set())
        assert not result["derisk_active"]
        assert result["suppressed_add_tilts"] == []

    def test_firing_derisk_suppresses_add_tilts(self):
        states = {
            "dr": self._confirmed_state("dr", "de-risk"),
            "at": self._confirmed_state("at", "add-tilt"),
        }
        result = feed.arbitrate(states, firing={"dr"})
        assert result["derisk_active"]
        assert "at" in result["suppressed_add_tilts"]

    def test_firing_add_tilt_only_no_suppression(self):
        """An add-tilt firing alone does not activate de-risk."""
        states = {
            "at": self._confirmed_state("at", "add-tilt"),
        }
        result = feed.arbitrate(states, firing={"at"})
        assert not result["derisk_active"]
        assert result["suppressed_add_tilts"] == []

    def test_zero_weight_derisk_not_dominant(self):
        """A de-risk feature with weight=0 (stale/killed/CONTEXT) must NOT dominate."""
        states = {
            "dr_zero": {**self._confirmed_state("dr_zero", "de-risk"), "weight": 0.0},
            "at": self._confirmed_state("at", "add-tilt"),
        }
        result = feed.arbitrate(states, firing={"dr_zero"})
        assert not result["derisk_active"]
        assert result["suppressed_add_tilts"] == []

    def test_multiple_derisk_one_firing_suppresses_all_add_tilts(self):
        states = {
            "dr1": self._confirmed_state("dr1", "de-risk"),
            "dr2": self._confirmed_state("dr2", "de-risk"),
            "at1": self._confirmed_state("at1", "add-tilt"),
            "at2": self._confirmed_state("at2", "add-tilt"),
        }
        result = feed.arbitrate(states, firing={"dr2"})
        assert result["derisk_active"]
        assert set(result["suppressed_add_tilts"]) == {"at1", "at2"}

    def test_none_firing_defaults_to_empty_set(self):
        """firing=None must default to empty set, not crash."""
        states = {"dr": self._confirmed_state("dr", "de-risk")}
        result = feed.arbitrate(states)          # no firing kwarg
        assert not result["derisk_active"]


# ---------------------------------------------------------------------------
# fixture ledger smoke test
# ---------------------------------------------------------------------------

def test_fixture_ledger_loads():
    """The committed fixture ledger parses cleanly and returns at least one feature."""
    fixture_root = Path(__file__).resolve().parent / "fixtures"
    states = feed.features(fixture_root)
    # Fixture may have stale sources (no parquets in fixtures/) but should
    # return the feature map with the correct ids.
    assert "intl_macro_sleeve" in states
    assert "reer_value_factor" in states
    # DIRECTIONAL de-risk gets half weight (if not stale)
    # PENDING / CONTEXT get zero
    assert states["intl_breadth_barometer"]["weight"] == 0.0  # PENDING
    assert states["asia_semi_aggregate"]["weight"] == 0.0     # CONTEXT


if __name__ == "__main__":
    import pytest as _pt
    _pt.main([__file__, "-v"])
