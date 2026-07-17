"""tests/test_opex_risk.py — Unit tests for engine/opex_risk.py (RIC W3).

Tests cover:
  A. Percentile-edge math (concentration_hot, dealer_load_extreme thresholds)
  B. Availability-normalization: n_applicable shrinks when surface parquets absent
  C. Level word thresholds (quiet/elevated/heavy per n_hot count)
  D. Keep-FIRST idempotency for log_window()
  E. Lane gate: off-lane log_window() is a no-op
  F. snapshot() never raises on any combination of absent data
  G. enrich_opex_events() enriches OPEX rows, leaves non-OPEX rows untouched
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

# Repo root is two levels above this file
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import opex_risk
from engine.event_calendar import enrich_opex_events


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_surface(n: int = 60, seed: int = 42, root: str = "SPX") -> pd.DataFrame:
    """Synthetic surface parquet matching the PRODUCTION schema from build_options_surface.py.

    Production writer (build_options_surface.py:139-141):
        df = df.sort_values(["root", "date"]).reset_index(drop=True)
        df.to_parquet(p, index=False)

    So the schema is: multi-root long frame, RangeIndex, string `root` column,
    string `date` column, NO DatetimeIndex.  This matches the real parquet and
    ensures the _filter_and_sort() path is exercised in tests (the prior fixture
    had a DatetimeIndex and no `root` column, masking the production schema bug).

    By default builds a single-root frame for `root`.  Use _make_multi_surface()
    for multi-root fixtures.
    """
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2024-01-01", periods=n)
    date_strs = [d.strftime("%Y-%m-%d") for d in dates]
    df = pd.DataFrame({
        "root": root,
        "date": date_strs,
        "front7_abs_charm_share": rng.uniform(0.05, 0.40, n),
        "front7_abs_gex_share":   rng.uniform(0.10, 0.50, n),
        "net_vex":                rng.normal(0, 2e9, n),
        "net_cex":                rng.normal(0, 1.5e9, n),
        "net_gex_bn":             rng.normal(5, 3, n),   # mostly long
        "total_abs_gamma_notional": rng.uniform(1e9, 5e9, n),
    })
    # RangeIndex matches the production writer's reset_index(drop=True)
    df = df.reset_index(drop=True)
    return df


def _make_multi_surface(n: int = 60, seed: int = 42) -> pd.DataFrame:
    """Multi-root surface matching production: DIA/IWM/QQQ/SPX/SPXW/SPY stacked.

    SPX/SPXW rows run to today; SPY rows end 2022 (as in the real store) —
    this validates that _filter_and_sort picks SPX over SPY when both are available.
    """
    roots_long  = ["SPX", "SPXW", "QQQ"]   # recent dates
    roots_stale = ["SPY", "DIA", "IWM"]     # older dates (simulate SPY store end 2022)
    frames = []
    for i, r in enumerate(roots_long):
        frames.append(_make_surface(n, seed=seed + i, root=r))
    for i, r in enumerate(roots_stale):
        df = _make_surface(n, seed=seed + 100 + i, root=r)
        # Wind back dates so they end in 2022 (stale)
        df["date"] = [f"2022-{(j % 12) + 1:02d}-{(j % 20) + 1:02d}" for j in range(n)]
        frames.append(df)
    combined = pd.concat(frames, ignore_index=True)
    combined = combined.sort_values(["root", "date"]).reset_index(drop=True)
    return combined


def _write_surface(tmp: Path, root_class: str, df: pd.DataFrame) -> None:
    """Write surface parquet to the path that opex_risk._surface_path() expects.
    Writes with index=False to match build_options_surface.py exactly."""
    d = tmp / "options_surface"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{root_class}.parquet"
    df.to_parquet(p, index=False)


# ── A. Percentile-edge math ───────────────────────────────────────────────────

class TestConcentrationHot:
    def test_below_p80_returns_false(self):
        df = _make_surface(60)
        # Force latest row to be at median (never hot)
        df.iloc[-1, df.columns.get_loc("front7_abs_charm_share")] = \
            float(df["front7_abs_charm_share"].iloc[:-1].quantile(0.50))
        df.iloc[-1, df.columns.get_loc("front7_abs_gex_share")] = \
            float(df["front7_abs_gex_share"].iloc[:-1].quantile(0.50))
        result = opex_risk._concentration_hot(df)
        assert result is False

    def test_above_p80_charm_returns_true(self):
        df = _make_surface(60)
        # Force latest charm to be 99th pctile of history
        df.iloc[-1, df.columns.get_loc("front7_abs_charm_share")] = \
            float(df["front7_abs_charm_share"].iloc[:-1].quantile(0.99)) + 0.01
        df.iloc[-1, df.columns.get_loc("front7_abs_gex_share")] = 0.0
        result = opex_risk._concentration_hot(df)
        assert result is True

    def test_none_when_df_none(self):
        assert opex_risk._concentration_hot(None) is None

    def test_none_when_too_few_rows(self):
        df = _make_surface(10)
        # _percentile_rank needs >=20; history has 9 rows (exclude latest)
        assert opex_risk._concentration_hot(df) is None

    def test_multi_root_uses_best_root_not_stale_spy(self):
        """Production schema: SPX rows run to 2024, SPY rows end 2022.
        _filter_and_sort must pick SPX and compute percentile against SPX history only,
        NOT use the stale SPY row as 'latest' and mix all roots as 'hist'."""
        multi = _make_multi_surface(60)
        # Force SPX's last row to above P80 of its own history
        spx_rows = multi[multi["root"] == "SPX"].copy()
        last_spx_idx = spx_rows.index[-1]
        thresh = float(spx_rows["front7_abs_charm_share"].iloc[:-1].quantile(0.99)) + 0.01
        multi.loc[last_spx_idx, "front7_abs_charm_share"] = thresh
        multi.loc[last_spx_idx, "front7_abs_gex_share"] = 0.0
        result = opex_risk._concentration_hot(multi)
        # SPX is the best root (most recent dates); its latest row is above P80 → True
        assert result is True


class TestDealerLoadExtreme:
    def test_below_p90_returns_false(self):
        df = _make_surface(60)
        # Force latest |net_vex| to median
        median_abs = float(df["net_vex"].abs().iloc[:-1].quantile(0.50))
        df.iloc[-1, df.columns.get_loc("net_vex")] = median_abs
        df.iloc[-1, df.columns.get_loc("net_cex")] = 0.0
        result = opex_risk._dealer_load_extreme(df)
        assert result is False

    def test_above_p90_vex_returns_true(self):
        df = _make_surface(60)
        # Force latest |net_vex| to 99th pctile
        max_abs = float(df["net_vex"].abs().iloc[:-1].quantile(0.99)) * 2
        df.iloc[-1, df.columns.get_loc("net_vex")] = max_abs
        result = opex_risk._dealer_load_extreme(df)
        assert result is True

    def test_none_when_df_none(self):
        assert opex_risk._dealer_load_extreme(None) is None

    def test_sign_agnostic_positive(self):
        """Negative net_vex of extreme magnitude must also trigger."""
        df = _make_surface(60)
        max_abs = float(df["net_vex"].abs().iloc[:-1].quantile(0.99)) * 2
        df.iloc[-1, df.columns.get_loc("net_vex")] = -max_abs
        result = opex_risk._dealer_load_extreme(df)
        assert result is True

    def test_multi_root_picks_best_root_not_stale_spy(self):
        """Production schema: SPX rows are recent, SPY rows ended 2022.
        SPX's latest must be chosen; percentile computed against SPX history only."""
        multi = _make_multi_surface(60)
        spx_rows = multi[multi["root"] == "SPX"].copy()
        last_spx_idx = spx_rows.index[-1]
        max_abs = float(spx_rows["net_vex"].abs().iloc[:-1].quantile(0.99)) * 2
        multi.loc[last_spx_idx, "net_vex"] = max_abs
        result = opex_risk._dealer_load_extreme(multi)
        assert result is True


# ── B. Availability-normalization ─────────────────────────────────────────────

class TestAvailabilityNorm:
    def test_no_surface_data_n_applicable_zero(self, tmp_path):
        """When surface parquets absent, n_applicable=0."""
        snap = opex_risk.snapshot(
            spy_close=None,
            options_entry_state=None,
            data_root=tmp_path,
        )
        assert snap["n_applicable"] == 0
        assert snap["n_hot"] == 0
        assert snap["level"] == "quiet"

    def test_partial_data_shrinks_n_applicable(self, tmp_path):
        """Surface available but no options_entry_state → pin_proximity & vanna null out."""
        df = _make_surface(60)
        # force concentration_hot=False, dealer_load_extreme=False
        df.iloc[-1, df.columns.get_loc("front7_abs_charm_share")] = \
            float(df["front7_abs_charm_share"].iloc[:-1].quantile(0.30))
        df.iloc[-1, df.columns.get_loc("net_vex")] = 0.0
        _write_surface(tmp_path, "index_etf", df)
        snap = opex_risk.snapshot(
            spy_close=None,
            options_entry_state=None,
            data_root=tmp_path,
        )
        # Only concentration_hot and dealer_load_extreme have data → n_applicable=2
        assert snap["n_applicable"] == 2
        assert snap["n_hot"] == 0


# ── C. Level word thresholds ──────────────────────────────────────────────────

class TestLevelWords:
    @pytest.mark.parametrize("n,expected", [
        (0, "quiet"), (1, "quiet"), (2, "quiet"),
        (3, "elevated"), (4, "elevated"),
        (5, "heavy"), (6, "heavy"), (10, "heavy"),
    ])
    def test_level_word(self, n, expected):
        assert opex_risk._level_word(n) == expected

    def test_level_zh_matches_en_logic(self):
        assert opex_risk._level_word_zh(0) == "平静"
        assert opex_risk._level_word_zh(3) == "偏高"
        assert opex_risk._level_word_zh(5) == "重度"


# ── D. Keep-FIRST idempotency ─────────────────────────────────────────────────

class TestLogWindowIdempotency:
    def _make_snap(self, n_hot=1, td_to=3):
        return {
            "schema": "opex_risk.v1",
            "n_hot": n_hot,
            "n_applicable": 3,
            "level": "quiet",
            "states": {},
            "window_phase": {"phase": "opex_week", "td_to_opex": td_to, "is_quad_cycle": False},
            "glance_en": "Test glance.",
        }

    def test_first_write_succeeds(self, tmp_path):
        with patch.dict(os.environ, {"COLLECT_LANE": "nightly"}):
            snap = self._make_snap()
            result = opex_risk.log_window(snap, data_root=tmp_path)
        assert result is True
        p = tmp_path / "opex_windows" / "forward_log.jsonl"
        assert p.exists()
        rows = [json.loads(line) for line in p.read_text().splitlines() if line.strip()]
        assert len(rows) == 1
        assert rows[0]["n_hot"] == 1

    def test_second_write_same_month_is_noop(self, tmp_path):
        with patch.dict(os.environ, {"COLLECT_LANE": "nightly"}):
            snap = self._make_snap(n_hot=1)
            opex_risk.log_window(snap, data_root=tmp_path)
            # Second call — same month
            snap2 = self._make_snap(n_hot=2)
            result2 = opex_risk.log_window(snap2, data_root=tmp_path)
        assert result2 is False
        p = tmp_path / "opex_windows" / "forward_log.jsonl"
        rows = [json.loads(line) for line in p.read_text().splitlines() if line.strip()]
        assert len(rows) == 1
        assert rows[0]["n_hot"] == 1   # first value preserved

    def test_grading_rulers_present(self, tmp_path):
        with patch.dict(os.environ, {"COLLECT_LANE": "nightly"}):
            snap = self._make_snap()
            opex_risk.log_window(snap, data_root=tmp_path)
        p = tmp_path / "opex_windows" / "forward_log.jsonl"
        rows = [json.loads(line) for line in p.read_text().splitlines() if line.strip()]
        rulers = rows[0]["grading_rulers"]
        assert set(rulers.keys()) == {"forward_5d_rv", "forward_10d_rv", "max_dd_post10d", "range_compression"}
        for k, v in rulers.items():
            assert v["target_type"] in ("vol", "path")
            assert v["direction"] == "none"   # RO-3: no directional return target


# ── E. Lane gate ──────────────────────────────────────────────────────────────

class TestLaneGate:
    def test_off_lane_is_noop(self, tmp_path):
        """Off-lane (no COLLECT_LANE env) must not write anything."""
        snap = {
            "schema": "opex_risk.v1",
            "n_hot": 2, "n_applicable": 3, "level": "quiet",
            "states": {},
            "window_phase": {"phase": "opex_week", "td_to_opex": 2, "is_quad_cycle": False},
        }
        env = {k: v for k, v in os.environ.items()
               if k not in ("COLLECT_LANE", "US_LANE")}
        with patch.dict(os.environ, env, clear=True):
            result = opex_risk.log_window(snap, data_root=tmp_path)
        assert result is False
        p = tmp_path / "opex_windows" / "forward_log.jsonl"
        assert not p.exists()

    def test_nightly_lane_armed(self):
        with patch.dict(os.environ, {"COLLECT_LANE": "nightly"}):
            assert opex_risk.ledger_lane_armed() is True

    def test_other_lane_not_armed(self):
        with patch.dict(os.environ, {"COLLECT_LANE": "render"}):
            assert opex_risk.ledger_lane_armed() is False


# ── F. snapshot() never raises ────────────────────────────────────────────────

class TestSnapshotNeverRaises:
    def test_all_none(self, tmp_path):
        snap = opex_risk.snapshot(None, None, data_root=tmp_path)
        assert "schema" in snap
        assert snap["schema"] == "opex_risk.v1"
        assert "n_hot" in snap
        assert "n_applicable" in snap
        assert "level" in snap
        assert "glance_en" in snap
        assert "glance_zh" in snap
        assert "doctrine" in snap
        assert "dealer_sign_passport" in snap
        assert "post_opex_watch" in snap

    def test_with_surface_data(self, tmp_path):
        df = _make_surface(60)
        _write_surface(tmp_path, "index_etf", df)
        snap = opex_risk.snapshot(None, None, data_root=tmp_path)
        assert snap["n_applicable"] >= 2  # concentration_hot + dealer_load_extreme

    def test_snapshot_contains_event_collision_null_slot(self, tmp_path):
        """event_collision must be None — W4 null slot."""
        snap = opex_risk.snapshot(None, None, data_root=tmp_path)
        assert "event_collision" in snap.get("states", {})
        assert snap["states"]["event_collision"] is None

    def test_window_phase_keys_present(self, tmp_path):
        snap = opex_risk.snapshot(None, None, data_root=tmp_path)
        wp = snap.get("window_phase") or {}
        for k in ("phase", "td_to_opex", "td_since_opex", "in_opex_week", "is_quad_cycle"):
            assert k in wp

    def test_doctrine_never_contains_validated(self, tmp_path):
        """CI-guarded: 'validated' must not appear in user-facing text."""
        snap = opex_risk.snapshot(None, None, data_root=tmp_path)
        for field in ("glance_en", "glance_zh", "level", "level_zh"):
            val = snap.get(field) or ""
            assert "validated" not in val.lower(), f"{field!r} contains 'validated'"


# ── G. enrich_opex_events ─────────────────────────────────────────────────────

class TestEnrichOpexEvents:
    def _make_events(self):
        return [
            {"type": "CPI",  "date": "2026-07-14", "label": "CPI",  "impact": "high"},
            {"type": "OPEX", "date": "2026-07-18", "label": "OPEX", "impact": "med"},
            {"type": "FOMC", "date": "2026-07-29", "label": "FOMC", "impact": "high"},
        ]

    def _make_snap(self, level="elevated"):
        return {
            "level": level,
            "level_zh": {"quiet": "平静", "elevated": "偏高", "heavy": "重度"}[level],
            "glance_en": "Expiration week. Watch, don't chase.",
            "glance_zh": "到期周。观望，不追涨。",
            "n_hot": 2,
            "n_applicable": 3,
        }

    def test_opex_row_gets_level(self):
        events = self._make_events()
        enriched = enrich_opex_events(events, self._make_snap("elevated"))
        opex_ev = next(e for e in enriched if e["type"] == "OPEX")
        assert opex_ev["opex_risk_level"] == "elevated"
        assert opex_ev["opex_risk_level_zh"] == "偏高"
        assert opex_ev["opex_risk_n_hot"] == 2

    def test_non_opex_rows_unchanged(self):
        events = self._make_events()
        enriched = enrich_opex_events(events, self._make_snap())
        cpi = next(e for e in enriched if e["type"] == "CPI")
        assert "opex_risk_level" not in cpi
        fomc = next(e for e in enriched if e["type"] == "FOMC")
        assert "opex_risk_level" not in fomc

    def test_original_list_not_mutated(self):
        events = self._make_events()
        opex_orig = events[1].copy()
        enrich_opex_events(events, self._make_snap())
        assert events[1] == opex_orig   # caller's dict unchanged

    def test_none_snap_leaves_events_without_level(self):
        events = self._make_events()
        enriched = enrich_opex_events(events, None)
        opex_ev = next(e for e in enriched if e["type"] == "OPEX")
        # With None snap, level is "quiet" (fallback) — field still added
        assert "opex_risk_level" in opex_ev
        assert opex_ev["opex_risk_level"] == "quiet"

    def test_empty_events_returns_empty(self):
        assert enrich_opex_events([], {"level": "quiet"}) == []
