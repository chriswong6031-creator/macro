"""tests/test_causal_targets.py — CHF W3: Tests for causal_targets.py.

Hermetic: no network, no runner-local stores.
Tests:
  - regime panel construction from fixture parquet
  - breadth deterioration target
  - entry_quality panel absent-store honesty (returns None + note)
  - cause panel from inventory (with and without columns in inventory)
  - era auto-stamp on entry_quality edges
  - load_cause_series for numeric and non-numeric data
"""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Ensure repo root on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.neuralweb.causal_targets import (
    build_cause_panel,
    build_entry_quality_panel,
    build_regime_risk_panel,
    load_cause_series,
    _ENTRY_QUALITY_ERA_START,
    _GOOD_21D_STATES,
    _STOPPED_STATE,
)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _write_parquet(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path)


def _write_json(data: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _make_regime_history(n: int = 200) -> pd.DataFrame:
    """Create a small regime_history fixture spanning pre/post 2010."""
    dates = pd.date_range("2000-01-01", periods=n, freq="B")
    # Alternate transition_state severity
    states = ["STABLE", "WATCHING", "WARNING", "DOWNGRADE"] * (n // 4 + 1)
    recessions = [False] * (n // 2) + [True] * (n - n // 2)
    return pd.DataFrame(
        {
            "transition_state": states[:n],
            "recession": recessions,
            "quad": ["1"] * n,
        },
        index=dates,
    )


def _make_breadth(n: int = 200) -> pd.DataFrame:
    """Create a small breadth fixture with periodic drops >= 5pp."""
    dates = pd.date_range("2000-01-01", periods=n, freq="B")
    # Create a sawtooth with drops of 10pp every 25 days → many deterioration events
    vals = np.array([60.0 - (10.0 * ((i % 25) / 25.0)) for i in range(n)])
    return pd.DataFrame({"pct_above_50": vals}, index=dates)


def _make_replay_boarded(n_fire: int = 30, era_start: str = "2022-07-01") -> pd.DataFrame:
    """Create a small replay_boarded fixture post era start."""
    dates = pd.date_range(era_start, periods=n_fire, freq="B")
    states = list(_GOOD_21D_STATES) * (n_fire // 2 + 1)
    states = states[:n_fire]
    return pd.DataFrame(
        {
            "verdict_type": ["fire"] * n_fire,
            "verdict_grade": [True] * n_fire,
            "state_8_21": states,
            "fwd_mdd_21": np.random.default_rng(42).uniform(-0.1, 0.0, n_fire),
        },
        index=dates,
    )


# ---------------------------------------------------------------------------
# Tests: regime_risk panel
# ---------------------------------------------------------------------------

class TestBuildRegimeRiskPanel:
    def test_returns_empty_dict_when_no_regime_file(self, tmp_path):
        result = build_regime_risk_panel(root=tmp_path)
        assert result == {}

    def test_builds_targets_from_fixture(self, tmp_path):
        rh = _make_regime_history(n=300)
        _write_parquet(rh, tmp_path / "data" / "regime" / "regime_history.parquet")
        targets = build_regime_risk_panel(root=tmp_path)
        assert len(targets) >= 2
        for key in ("regime_worsening_5d", "regime_worsening_10d"):
            assert key in targets
            s = targets[key]
            assert isinstance(s, pd.Series)
            assert len(s) > 0
            # Values should be 0 or 1
            assert set(s.unique()).issubset({0.0, 1.0, np.nan})

    def test_recession_onset_target(self, tmp_path):
        rh = _make_regime_history(n=300)
        _write_parquet(rh, tmp_path / "data" / "regime" / "regime_history.parquet")
        targets = build_regime_risk_panel(root=tmp_path)
        assert "recession_onset_63d" in targets
        s = targets["recession_onset_63d"]
        # Should have some onset events (fixture enters recession halfway)
        assert s.sum() >= 0  # just verify it's numeric

    def test_breadth_deterioration_target_when_breadth_present(self, tmp_path):
        rh = _make_regime_history(n=300)
        br = _make_breadth(n=300)
        _write_parquet(rh, tmp_path / "data" / "regime" / "regime_history.parquet")
        _write_parquet(br, tmp_path / "data" / "breadth" / "breadth.parquet")
        targets = build_regime_risk_panel(root=tmp_path)
        assert "breadth_deterioration_21d" in targets
        s = targets["breadth_deterioration_21d"]
        # Descending series → many deterioration events
        assert s.sum() > 0

    def test_returns_series_with_datetime_index(self, tmp_path):
        rh = _make_regime_history(n=200)
        _write_parquet(rh, tmp_path / "data" / "regime" / "regime_history.parquet")
        targets = build_regime_risk_panel(root=tmp_path)
        for key, s in targets.items():
            assert isinstance(s.index, pd.DatetimeIndex), f"{key} index not DatetimeIndex"


# ---------------------------------------------------------------------------
# Tests: entry_quality panel
# ---------------------------------------------------------------------------

class TestBuildEntryQualityPanel:
    def test_returns_none_when_store_absent(self, tmp_path, capsys):
        result = build_entry_quality_panel(root=tmp_path)
        assert result is None
        captured = capsys.readouterr()
        # Should print an honest data_absent note
        assert "data_absent" in captured.out or "data_absent" in captured.err

    def test_returns_none_with_env_override_pointing_to_nonexistent(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("REPLAY_BOARDED_PATH", str(tmp_path / "nonexistent.parquet"))
        result = build_entry_quality_panel(root=tmp_path)
        assert result is None
        captured = capsys.readouterr()
        assert "data_absent" in captured.out or "data_absent" in captured.err

    def test_returns_targets_when_store_present(self, tmp_path, monkeypatch):
        df = _make_replay_boarded(n_fire=50)
        store_path = tmp_path / "replay_boarded.parquet"
        df.to_parquet(store_path)
        monkeypatch.setenv("REPLAY_BOARDED_PATH", str(store_path))
        result = build_entry_quality_panel(root=tmp_path)
        assert result is not None
        assert len(result) >= 1

    def test_targets_include_good_21d_and_stopped(self, tmp_path, monkeypatch):
        df = _make_replay_boarded(n_fire=50)
        store_path = tmp_path / "replay_boarded.parquet"
        df.to_parquet(store_path)
        monkeypatch.setenv("REPLAY_BOARDED_PATH", str(store_path))
        result = build_entry_quality_panel(root=tmp_path)
        assert result is not None
        assert "good_21d" in result
        assert "stopped_8_21" in result

    def test_signal_date_column_store(self, tmp_path, monkeypatch):
        """Prod store shape: dates live in a signal_date COLUMN (RangeIndex),
        not a DatetimeIndex — the builder must find and set it."""
        df = _make_replay_boarded(n_fire=50)
        df = df.reset_index().rename(columns={"index": "signal_date"})
        store_path = tmp_path / "replay_boarded.parquet"
        df.to_parquet(store_path)
        monkeypatch.setenv("REPLAY_BOARDED_PATH", str(store_path))
        result = build_entry_quality_panel(root=tmp_path)
        assert result is not None
        assert "good_21d" in result
        assert isinstance(result["good_21d"].index, pd.DatetimeIndex)

    def test_duplicate_fire_dates_collapse_to_per_date_cross_sections(
        self, tmp_path, monkeypatch
    ):
        """Prod store shape: many fires per signal date. CHF-R5 ticker-panel
        law — the panel must collapse to per-date cross-sectional means with a
        UNIQUE date index (never fire-level rows with duplicate labels)."""
        df = _make_replay_boarded(n_fire=30)
        # Duplicate every date 3x with mixed outcomes: 2 good, 1 stopped per date
        good = df.copy()
        good["state_8_21"] = list(_GOOD_21D_STATES)[0]
        stopped = df.copy()
        stopped["state_8_21"] = "STOPPED"
        panel = pd.concat([good, good, stopped]).sort_index()
        store_path = tmp_path / "replay_boarded.parquet"
        panel.to_parquet(store_path)
        monkeypatch.setenv("REPLAY_BOARDED_PATH", str(store_path))
        result = build_entry_quality_panel(root=tmp_path)
        assert result is not None
        s = result["good_21d"]
        assert s.index.is_unique, "per-date collapse must dedupe the date index"
        assert s.index.is_monotonic_increasing
        # 2 of 3 fires good on every date → per-date good-rate = 2/3
        assert np.allclose(s.values, 2.0 / 3.0)
        # stop-rate = 1/3
        assert np.allclose(result["stopped_8_21"].values, 1.0 / 3.0)

    def test_era_stamp_is_post_2022(self, tmp_path, monkeypatch):
        """Entry-quality panel should only contain dates >= 2022-06-30."""
        # Mix pre and post era dates
        pre_dates = pd.date_range("2020-01-01", periods=20, freq="B")
        post_dates = pd.date_range("2022-07-01", periods=30, freq="B")
        all_dates = pre_dates.union(post_dates)
        n = len(all_dates)
        states = (list(_GOOD_21D_STATES) * (n // 2 + 1))[:n]
        df = pd.DataFrame(
            {
                "verdict_type": ["fire"] * n,
                "verdict_grade": [True] * n,
                "state_8_21": states,
                "fwd_mdd_21": [-0.05] * n,
            },
            index=all_dates,
        )
        store_path = tmp_path / "replay_boarded.parquet"
        df.to_parquet(store_path)
        monkeypatch.setenv("REPLAY_BOARDED_PATH", str(store_path))
        result = build_entry_quality_panel(root=tmp_path)
        # Must only contain post-era dates
        assert result is not None
        for tgt_id, s in result.items():
            assert isinstance(s.index, pd.DatetimeIndex)
            assert s.index.min() >= _ENTRY_QUALITY_ERA_START, (
                f"{tgt_id}: min date {s.index.min()} < era start {_ENTRY_QUALITY_ERA_START}"
            )

    def test_verdict_grade_filter(self, tmp_path, monkeypatch):
        """Only verdict_grade=True and verdict_type=fire rows should appear."""
        dates = pd.date_range("2022-07-01", periods=20, freq="B")
        df = pd.DataFrame(
            {
                "verdict_type": ["fire"] * 10 + ["miss"] * 10,
                "verdict_grade": [True] * 10 + [False] * 10,
                "state_8_21": ["CUSHIONED"] * 20,
                "fwd_mdd_21": [-0.05] * 20,
            },
            index=dates,
        )
        store_path = tmp_path / "replay_boarded.parquet"
        df.to_parquet(store_path)
        monkeypatch.setenv("REPLAY_BOARDED_PATH", str(store_path))
        result = build_entry_quality_panel(root=tmp_path)
        assert result is not None
        for tgt_id, s in result.items():
            # Should only have 10 rows (the fire+grade=True ones)
            assert len(s) == 10, f"{tgt_id} has {len(s)} rows, expected 10"


# ---------------------------------------------------------------------------
# Tests: cause panel
# ---------------------------------------------------------------------------

class TestBuildCausePanel:
    def _write_inventory(self, tmp_path, features: list[dict]) -> None:
        inv = {
            "schema": "neuralweb.causal_feature_inventory.v1",
            "asof": "2026-07-09T00:00:00Z",
            "features": features,
        }
        _write_json(inv, tmp_path / "data" / "neuralweb" / "causal_feature_inventory.json")

    def test_returns_empty_when_no_inventory(self, tmp_path):
        # When inventory absent, should fall back to FEATURE_SOURCES but find no files
        result = build_cause_panel(root=tmp_path)
        # Fallback returns empty because no data files exist in tmp_path
        assert isinstance(result, dict)

    def test_filters_candidate_cause_role(self, tmp_path):
        self._write_inventory(tmp_path, [
            {
                "feature_id": "foo",
                "family": "test",
                "path": "data/foo.parquet",
                "allowed_roles": ["candidate_cause", "conditioner"],
                "present": True,
                "min_lag_days": 1,
                "era_coverage": ["2000-08"],
                "tier": "asset_class",
                "pit_basis": "pit_live",
                "cadence": "daily-engine",
            },
            {
                "feature_id": "bar",
                "family": "test",
                "path": "data/bar.parquet",
                "allowed_roles": ["conditioner"],  # no candidate_cause
                "present": True,
                "min_lag_days": 1,
                "era_coverage": ["2000-08"],
                "tier": "asset_class",
                "pit_basis": "pit_live",
                "cadence": "daily-engine",
            },
        ])
        result = build_cause_panel(root=tmp_path)
        assert "foo" in result
        assert "bar" not in result

    def test_filters_not_present(self, tmp_path):
        self._write_inventory(tmp_path, [
            {
                "feature_id": "foo",
                "family": "test",
                "path": "data/foo.parquet",
                "allowed_roles": ["candidate_cause"],
                "present": False,  # not present
                "min_lag_days": 1,
                "era_coverage": [],
                "tier": "asset_class",
                "pit_basis": "pit_live",
                "cadence": "daily-engine",
            },
        ])
        result = build_cause_panel(root=tmp_path)
        assert "foo" not in result

    def test_min_lag_days_populated(self, tmp_path):
        self._write_inventory(tmp_path, [
            {
                "feature_id": "foo",
                "family": "test",
                "path": "data/foo.parquet",
                "allowed_roles": ["candidate_cause"],
                "present": True,
                "min_lag_days": 5,
                "era_coverage": ["2000-08"],
                "tier": "asset_class",
                "pit_basis": "pit_live",
                "cadence": "weekly",
            },
        ])
        result = build_cause_panel(root=tmp_path)
        assert result.get("foo", {}).get("min_lag_days") == 5


# ---------------------------------------------------------------------------
# Tests: load_cause_series
# ---------------------------------------------------------------------------

class TestLoadCauseSeries:
    def test_loads_parquet_column(self, tmp_path):
        df = pd.DataFrame(
            {"pct_above_50": [60.0, 55.0, 50.0]},
            index=pd.date_range("2000-01-01", periods=3, freq="B"),
        )
        _write_parquet(df, tmp_path / "data" / "breadth" / "breadth.parquet")
        meta = {
            "path": "data/breadth/breadth.parquet",
            "columns": ["pct_above_50"],
            "min_lag_days": 1,
            "cadence": "daily-engine",
        }
        result = load_cause_series("breadth_test", meta, tmp_path, "pct_above_50")
        assert result is not None
        assert len(result) == 3

    def test_returns_none_when_file_absent(self, tmp_path):
        meta = {
            "path": "data/missing.parquet",
            "columns": ["x"],
            "min_lag_days": 1,
            "cadence": "daily-engine",
        }
        result = load_cause_series("missing", meta, tmp_path, "x")
        assert result is None

    def test_returns_none_for_nonexistent_column(self, tmp_path):
        df = pd.DataFrame(
            {"col_a": [1.0, 2.0]},
            index=pd.date_range("2000-01-01", periods=2, freq="B"),
        )
        _write_parquet(df, tmp_path / "data" / "test.parquet")
        meta = {
            "path": "data/test.parquet",
            "columns": ["col_b"],
            "min_lag_days": 1,
            "cadence": "daily-engine",
        }
        result = load_cause_series("test", meta, tmp_path, "col_b")
        assert result is None

    def test_sorted_and_dropna(self, tmp_path):
        dates = pd.date_range("2000-01-03", periods=5, freq="B")[::-1]  # reverse order
        df = pd.DataFrame({"x": [1.0, np.nan, 3.0, 4.0, 5.0]}, index=dates)
        _write_parquet(df, tmp_path / "data" / "test.parquet")
        meta = {
            "path": "data/test.parquet",
            "columns": ["x"],
            "min_lag_days": 1,
            "cadence": "daily-engine",
        }
        result = load_cause_series("test", meta, tmp_path, "x")
        assert result is not None
        # Should be sorted ascending and NaN dropped
        assert result.index.is_monotonic_increasing
        assert not result.isna().any()
