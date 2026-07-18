"""tests/test_market_structure.py — Unit tests for MSP W1 data-spine.

Tests cover:
  - engine/systematic_flows.py: vc_exposure, cta_positioning, rv_cross_state,
    flow_state, agreement
  - engine/market_structure_context.py: compact_state, diff_changes,
    build_changes (same-day idempotency)
  - dispersion.cor1m_regime percentile logic (tested via builder internals)
  - ledger lane gate (COLLECT_LANE unset → no ledger write; =nightly → writes)

ABSOLUTE LAW: tests never write to real data/ or site/ trees — all writes go
through tmp_path.  MM_DATA_GUARD would trip CI on real-tree writes.

Run: python3 -m pytest tests/test_market_structure.py -x -q
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Synthetic series helpers
# ---------------------------------------------------------------------------

def _flat_series(n: int = 300, base: float = 100.0, seed: int = 42) -> pd.Series:
    """Nearly flat price series — zero drift, near-zero vol."""
    rng = np.random.default_rng(seed)
    noise = rng.normal(0, 0.0005, n)
    prices = base * np.cumprod(1 + noise)
    idx = pd.bdate_range("2020-01-01", periods=n)
    return pd.Series(prices, index=idx, name="close")


def _trend_up_series(n: int = 600, base: float = 100.0, seed: int = 1) -> pd.Series:
    """Strong uptrend — 0.15% daily drift, 1% vol.  Use ≥600 bars so the 200d
    window populates and all four CTA signals are firmly positive."""
    rng = np.random.default_rng(seed)
    noise = rng.normal(0.0015, 0.01, n)
    prices = base * np.cumprod(1 + noise)
    idx = pd.bdate_range("2018-01-01", periods=n)
    return pd.Series(prices, index=idx, name="close")


def _trend_down_series(n: int = 600, base: float = 100.0, seed: int = 2) -> pd.Series:
    """Strong downtrend — -0.15% daily drift, 1% vol.  Use ≥600 bars so all four
    CTA signals are firmly negative."""
    rng = np.random.default_rng(seed)
    noise = rng.normal(-0.0015, 0.01, n)
    prices = base * np.cumprod(1 + noise)
    idx = pd.bdate_range("2018-01-01", periods=n)
    return pd.Series(prices, index=idx, name="close")


def _high_vol_series(n: int = 300, base: float = 100.0, vol: float = 0.05) -> pd.Series:
    """High-volatility series (5% daily vol = ~79% annualised)."""
    rng = np.random.default_rng(3)
    noise = rng.normal(0, vol, n)
    prices = base * np.cumprod(1 + noise)
    idx = pd.bdate_range("2020-01-01", periods=n)
    return pd.Series(prices, index=idx, name="close")


def _low_vol_series(n: int = 300, base: float = 100.0, vol: float = 0.002) -> pd.Series:
    """Low-volatility series (0.2% daily vol = ~3.2% annualised)."""
    rng = np.random.default_rng(4)
    noise = rng.normal(0, vol, n)
    prices = base * np.cumprod(1 + noise)
    idx = pd.bdate_range("2020-01-01", periods=n)
    return pd.Series(prices, index=idx, name="close")


# ===========================================================================
# 1. vc_exposure
# ===========================================================================

class TestVcExposure:
    """Unit tests for engine.systematic_flows.vc_exposure."""

    def test_returns_expected_columns(self):
        from engine.systematic_flows import vc_exposure
        s = _flat_series()
        df = vc_exposure(s)
        assert set(df.columns) == {"rv21", "rv63", "alloc_frac", "alloc_bn", "flow_bn"}

    def test_low_vol_alloc_frac_capped_at_one(self):
        """Low-vol series: vol is below target → alloc_frac should hit 1.0 cap."""
        from engine.systematic_flows import vc_exposure
        s = _low_vol_series()
        df = vc_exposure(s, target_vol=0.10)
        # For a 0.2% daily vol series, annualised ~3.2% << 10% target → cap at 1
        tail = df["alloc_frac"].dropna().tail(20)
        assert (tail >= 0.999).all(), f"Expected alloc_frac ~ 1.0 for low-vol series; got {tail.describe()}"

    def test_high_vol_alloc_shrinks(self):
        """High-vol series: vol exceeds target → alloc_frac < 1."""
        from engine.systematic_flows import vc_exposure
        s = _high_vol_series(vol=0.05)
        df = vc_exposure(s, target_vol=0.10)
        tail = df["alloc_frac"].dropna().tail(20)
        assert (tail < 1.0).all(), f"Expected alloc_frac < 1.0 for high-vol series; got {tail.describe()}"

    def test_alloc_bn_bounded_by_aum(self):
        """alloc_bn must never exceed aum_bn."""
        from engine.systematic_flows import vc_exposure
        s = _low_vol_series()
        aum = 250.0
        df = vc_exposure(s, aum_bn=aum)
        tail = df["alloc_bn"].dropna()
        assert (tail <= aum + 1e-9).all(), f"alloc_bn exceeded aum_bn: max={tail.max()}"

    def test_flow_sign_correct(self):
        """After a vol spike, alloc_frac drops → flow_bn should go negative (cutting)."""
        from engine.systematic_flows import vc_exposure
        # Build a series that transitions from low-vol to high-vol
        low = _low_vol_series(n=200)
        high = _high_vol_series(n=100, base=float(low.iloc[-1]), vol=0.05)
        high.index = pd.bdate_range(low.index[-1], periods=101)[1:]
        s = pd.concat([low, high])
        df = vc_exposure(s)
        # In the high-vol zone, allocation should be cutting (flow_bn < 0 on average)
        flow_tail = df["flow_bn"].dropna().tail(20)
        neg_count = (flow_tail < 0).sum()
        assert neg_count >= 10, f"Expected mostly negative flow after vol spike; neg={neg_count}/20"

    def test_no_lookahead(self):
        """At date t, no close after t is used.  Spot-check: modifying a future bar
        does not change the alloc_frac at an earlier bar."""
        from engine.systematic_flows import vc_exposure
        s = _trend_up_series(n=250)
        df_orig = vc_exposure(s)
        # Change the last bar's value drastically
        s2 = s.copy()
        s2.iloc[-1] = s2.iloc[-2] * 0.5   # 50% crash on the last day
        df_mod = vc_exposure(s2)
        # Row at -2 must be identical
        for col in ["rv21", "rv63", "alloc_frac", "alloc_bn"]:
            v_orig = df_orig[col].iloc[-2]
            v_mod  = df_mod[col].iloc[-2]
            assert abs((v_orig or 0) - (v_mod or 0)) < 1e-9, (
                f"Lookahead detected in {col}: orig={v_orig} mod={v_mod}"
            )

    def test_index_preserved(self):
        from engine.systematic_flows import vc_exposure
        s = _flat_series(n=100)
        df = vc_exposure(s)
        assert (df.index == s.index).all()


# ===========================================================================
# 2. cta_positioning
# ===========================================================================

class TestCtaPositioning:
    """Unit tests for engine.systematic_flows.cta_positioning."""

    def test_returns_expected_columns(self):
        from engine.systematic_flows import cta_positioning
        s = _trend_up_series()
        df = cta_positioning(s)
        assert set(df.columns) == {"cta_score", "cta_z", "cta_flow"}

    def test_uptrend_yields_positive_score(self):
        """Strong uptrend → cta_score should be positive in tail.
        Uses 600-bar series so all 4 CTA windows (20/50/100/200d) are populated."""
        from engine.systematic_flows import cta_positioning
        s = _trend_up_series()  # default n=600
        df = cta_positioning(s)
        tail_mean = df["cta_score"].dropna().tail(20).mean()
        assert tail_mean > 0.0, f"Expected positive cta_score on uptrend; got {tail_mean:.4f}"

    def test_downtrend_yields_negative_score(self):
        """Strong downtrend → cta_score should be negative in tail.
        Uses 600-bar series so all 4 CTA windows (20/50/100/200d) are populated."""
        from engine.systematic_flows import cta_positioning
        s = _trend_down_series()  # default n=600
        df = cta_positioning(s)
        tail_mean = df["cta_score"].dropna().tail(20).mean()
        assert tail_mean < 0.0, f"Expected negative cta_score on downtrend; got {tail_mean:.4f}"

    def test_flat_tape_near_zero(self):
        """Flat tape → cta_score should be near zero (no trend to follow)."""
        from engine.systematic_flows import cta_positioning
        s = _flat_series(n=300)
        df = cta_positioning(s)
        tail_abs = df["cta_score"].dropna().tail(30).abs().mean()
        # Flat = no signal, expect score < 0.5 (well within [-3, +3] bounds)
        assert tail_abs < 0.5, f"Expected near-zero cta_score on flat tape; got abs_mean={tail_abs:.4f}"

    def test_score_bounded(self):
        """cta_score must always be in [-3, +3] by construction."""
        from engine.systematic_flows import cta_positioning
        for s in [_trend_up_series(), _trend_down_series(), _flat_series(), _high_vol_series()]:
            df = cta_positioning(s)
            scores = df["cta_score"].dropna()
            assert (scores >= -3.0).all() and (scores <= 3.0).all(), (
                f"cta_score out of [-3,3]: min={scores.min():.4f} max={scores.max():.4f}"
            )

    def test_no_lookahead(self):
        """Modifying a future bar must not change an earlier bar's cta_score."""
        from engine.systematic_flows import cta_positioning
        s = _trend_up_series(n=300)
        df_orig = cta_positioning(s)
        s2 = s.copy()
        s2.iloc[-1] = s2.iloc[-2] * 0.5
        df_mod = cta_positioning(s2)
        v_orig = float(df_orig["cta_score"].iloc[-2])
        v_mod  = float(df_mod["cta_score"].iloc[-2])
        assert abs(v_orig - v_mod) < 1e-9, (
            f"Lookahead in cta_score at -2: orig={v_orig} mod={v_mod}"
        )

    def test_cta_flow_is_diff_of_score(self):
        """cta_flow must equal cta_score.diff() (day-over-day score change)."""
        from engine.systematic_flows import cta_positioning
        s = _trend_up_series(n=100)
        df = cta_positioning(s)
        diff = df["cta_score"].diff()
        pd.testing.assert_series_equal(df["cta_flow"], diff, check_names=False)


# ===========================================================================
# 3. rv_cross_state
# ===========================================================================

class TestRvCrossState:
    from engine.systematic_flows import rv_cross_state

    def test_stress_when_rv21_gt_rv63(self):
        from engine.systematic_flows import rv_cross_state
        assert rv_cross_state(0.20, 0.15) == "stress"

    def test_calm_when_rv21_lt_rv63(self):
        from engine.systematic_flows import rv_cross_state
        assert rv_cross_state(0.12, 0.15) == "calm"

    def test_calm_when_equal(self):
        from engine.systematic_flows import rv_cross_state
        assert rv_cross_state(0.15, 0.15) == "calm"

    def test_none_inputs(self):
        from engine.systematic_flows import rv_cross_state
        assert rv_cross_state(None, 0.15) == "unknown"
        assert rv_cross_state(0.15, None) == "unknown"
        assert rv_cross_state(None, None) == "unknown"


# ===========================================================================
# 4. flow_state and agreement
# ===========================================================================

class TestFlowState:
    def test_adding(self):
        from engine.systematic_flows import flow_state
        assert flow_state(5.0, deadband=1.0) == "adding"

    def test_cutting(self):
        from engine.systematic_flows import flow_state
        assert flow_state(-5.0, deadband=1.0) == "cutting"

    def test_pausing_within_deadband(self):
        from engine.systematic_flows import flow_state
        assert flow_state(0.5, deadband=1.0) == "pausing"
        assert flow_state(-0.5, deadband=1.0) == "pausing"
        assert flow_state(0.0, deadband=1.0) == "pausing"

    def test_none_is_pausing(self):
        from engine.systematic_flows import flow_state
        assert flow_state(None, deadband=1.0) == "pausing"


class TestAgreement:
    def test_aligned_adding(self):
        from engine.systematic_flows import agreement
        assert agreement("adding", "adding") == "aligned_adding"

    def test_aligned_cutting(self):
        from engine.systematic_flows import agreement
        assert agreement("cutting", "cutting") == "aligned_cutting"

    def test_paused(self):
        from engine.systematic_flows import agreement
        assert agreement("pausing", "pausing") == "paused"

    def test_split_mixed(self):
        from engine.systematic_flows import agreement
        # All non-identical combinations should be split
        assert agreement("adding", "cutting") == "split"
        assert agreement("cutting", "adding") == "split"
        assert agreement("adding", "pausing") == "split"
        assert agreement("pausing", "adding") == "split"
        assert agreement("cutting", "pausing") == "split"
        assert agreement("pausing", "cutting") == "split"


# ===========================================================================
# 5. cor1m_regime percentile logic
# ===========================================================================

class TestCor1mRegime:
    """Test the percentile-based regime classification in the builder."""

    def _run_dispersion_block(self, cor1m_values: list[float], tmp_path: Path) -> dict:
        """Inject a synthetic cor1m parquet and run _build_dispersion_block."""
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from scripts.build_market_structure import _build_dispersion_block

        cboe_dir = tmp_path / "data" / "cboe"
        cboe_dir.mkdir(parents=True)
        # Build a cor1m parquet with a 'close' column
        idx = pd.bdate_range("2020-01-01", periods=len(cor1m_values))
        df = pd.DataFrame({"close": cor1m_values}, index=idx)
        df.index.name = "date"
        df.to_parquet(cboe_dir / "cor1m.parquet")
        return _build_dispersion_block(tmp_path / "data")

    def test_high_correlation_is_elevated(self, tmp_path):
        """When the latest reading is at the 90th pctile of its own history → elevated."""
        # 500 values; last value is the highest
        vals = list(range(1, 501))  # 1, 2, ..., 500 — monotone increasing
        result = self._run_dispersion_block(vals, tmp_path)
        assert result["cor1m_regime"] == "elevated", (
            f"Expected 'elevated' for highest-ever correlation; got {result['cor1m_regime']}"
        )
        assert result["cor1m_pctile_2y"] is not None
        assert result["cor1m_pctile_2y"] >= 80

    def test_low_correlation_is_dispersion(self, tmp_path):
        """When the latest reading is at the 5th pctile of its own history → dispersion."""
        # 500 values; last value is near the lowest
        vals = list(range(500, 0, -1))  # 500, 499, ..., 1 — monotone decreasing
        result = self._run_dispersion_block(vals, tmp_path)
        assert result["cor1m_regime"] == "dispersion", (
            f"Expected 'dispersion' for lowest-ever correlation; got {result['cor1m_regime']}"
        )
        assert result["cor1m_pctile_2y"] is not None
        assert result["cor1m_pctile_2y"] <= 20

    def test_mid_correlation_is_normal(self, tmp_path):
        """A value near the median → 'normal'."""
        rng = np.random.default_rng(99)
        vals = sorted(rng.uniform(5, 30, 504).tolist())
        # Put the last value right in the middle
        median_val = float(np.median(vals))
        vals[-1] = median_val
        result = self._run_dispersion_block(vals, tmp_path)
        assert result["cor1m_regime"] == "normal", (
            f"Expected 'normal' for median correlation; got {result['cor1m_regime']}"
        )


# ===========================================================================
# 6. change-feed same-day idempotency
# ===========================================================================

class TestChangeFeed:
    """Tests for engine.market_structure_context.build_changes."""

    def _make_artifact(self, asof: str, gamma_regime: str, vc_state: str,
                       cta_state: str, agr: str, rv_state: str,
                       cor1m_regime: str) -> dict:
        return {
            "schema": "market_structure_context.v1",
            "asof": asof,
            "gamma": {"regime": gamma_regime},
            "systematic": {
                "vc": {"state": vc_state},
                "cta": {"state": cta_state},
                "agreement": agr,
            },
            "vol": {"rv_cross_state": rv_state},
            "dispersion": {"cor1m_regime": cor1m_regime},
        }

    def test_first_run_yields_empty_changes(self):
        """First run (old=None) → empty items, no prev_state."""
        from engine.market_structure_context import build_changes
        new_art = self._make_artifact("2026-07-17", "long", "adding", "adding",
                                     "aligned_adding", "calm", "normal")
        changes, prev_state = build_changes(None, new_art, "2026-07-17")
        assert changes["items"] == []
        assert changes["vs_asof"] is None
        assert prev_state["as_of"] is None

    def test_new_day_detects_regime_change(self):
        """On a new day, a gamma regime flip should appear in items."""
        from engine.market_structure_context import build_changes
        old_art = self._make_artifact("2026-07-16", "long", "adding", "adding",
                                     "aligned_adding", "calm", "normal")
        # Add prev_state to simulate what would be stored
        old_art["prev_state"] = {"as_of": None, "state": {}}
        new_art = self._make_artifact("2026-07-17", "short", "adding", "adding",
                                     "aligned_adding", "calm", "normal")
        changes, _ = build_changes(old_art, new_art, "2026-07-17")
        keys = [item["key"] for item in changes["items"]]
        assert "gamma_regime" in keys

    def test_same_day_rebuild_idempotent(self):
        """Same-day rebuild: items should not re-fire (prev_state baseline unchanged)."""
        from engine.market_structure_context import build_changes
        # Day 1 run — baseline
        old_art = self._make_artifact("2026-07-16", "long", "adding", "adding",
                                     "aligned_adding", "calm", "normal")
        old_art["prev_state"] = {"as_of": None, "state": {}}
        new_art = self._make_artifact("2026-07-17", "short", "adding", "adding",
                                     "aligned_adding", "calm", "normal")
        # First run of day 2
        changes1, prev_state1 = build_changes(old_art, new_art, "2026-07-17")
        assert any(item["key"] == "gamma_regime" for item in changes1["items"])

        # Simulate what was stored (same-day rebuild scenario)
        stored_art = dict(new_art)
        stored_art["state_changes"] = changes1
        stored_art["prev_state"] = prev_state1

        # Second run of same day (same asof) — changes must NOT re-fire
        changes2, _ = build_changes(stored_art, new_art, "2026-07-17")
        # The second build's items are based on prev_state (same baseline) vs same new_art
        # Since new_art == stored art's state, diff should be identical (same items from
        # same baseline — either empty if we already captured the change, which is the point)
        # The key property: items are the SAME whether we run once or twice same day
        assert changes2["items"] == changes1["items"], (
            "Same-day rebuild changed the items — not idempotent"
        )

    def test_no_change_yields_empty_items(self):
        """When nothing changes day-over-day, items should be empty."""
        from engine.market_structure_context import build_changes
        art = self._make_artifact("2026-07-16", "long", "adding", "adding",
                                  "aligned_adding", "calm", "normal")
        art["prev_state"] = {"as_of": None, "state": {}}
        new_art = self._make_artifact("2026-07-17", "long", "adding", "adding",
                                     "aligned_adding", "calm", "normal")
        changes, _ = build_changes(art, new_art, "2026-07-17")
        assert changes["items"] == []

    def test_max_six_items(self):
        """At most 6 change items should be emitted."""
        from engine.market_structure_context import build_changes
        old_art = self._make_artifact("2026-07-16", "long", "adding", "adding",
                                     "aligned_adding", "calm", "normal")
        old_art["prev_state"] = {"as_of": None, "state": {}}
        new_art = self._make_artifact("2026-07-17", "short", "cutting", "cutting",
                                     "aligned_cutting", "stress", "elevated")
        changes, _ = build_changes(old_art, new_art, "2026-07-17")
        assert len(changes["items"]) <= 6


# ===========================================================================
# 7. Ledger lane gate
# ===========================================================================

class TestLedgerLaneGate:
    """The ledger must only be written when COLLECT_LANE=nightly."""

    def _run_builder_in_tmp(self, tmp_path: Path, collect_lane: str | None) -> None:
        """Run the builder with a synthetic store tree rooted at tmp_path."""
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

        # Build minimal SPX parquet
        n = 150
        idx = pd.bdate_range("2025-01-01", periods=n)
        prices = 4500.0 * np.cumprod(1 + np.random.default_rng(7).normal(0.0005, 0.01, n))
        spx_df = pd.DataFrame({"close": prices}, index=idx)
        spx_df.index.name = "Date"
        yahoo_dir = tmp_path / "data" / "yahoo"
        yahoo_dir.mkdir(parents=True)
        spx_df.to_parquet(yahoo_dir / "_GSPC.parquet")

        # Minimal gex_SPX parquet
        gex_cols = ["spot", "net_gex_bn", "gamma_flip", "dist_to_flip_pct",
                    "gamma_regime", "iv30"]
        gex_df = pd.DataFrame(
            {col: [1.0] * n for col in gex_cols[:-2]} | {
                "gamma_flip": [4400.0] * n,
                "gamma_regime": ["long"] * n,
                "iv30": [0.15] * n,
            },
            index=idx,
        )
        gex_df["spot"] = prices
        gex_df["net_gex_bn"] = 50.0
        gex_df["dist_to_flip_pct"] = 2.0
        cboe_dir = tmp_path / "data" / "cboe"
        cboe_dir.mkdir(parents=True)
        gex_df.to_parquet(cboe_dir / "gex_SPX.parquet")

        # Monkeypatch config.data_dir() to point at tmp_path
        import lib.config as _cfg
        orig_data_dir = _cfg.data_dir

        def _fake_data_dir():
            return tmp_path / "data"

        _cfg.data_dir = _fake_data_dir

        old_lane = os.environ.get("COLLECT_LANE", "")
        try:
            if collect_lane is not None:
                os.environ["COLLECT_LANE"] = collect_lane
            else:
                os.environ.pop("COLLECT_LANE", None)

            from scripts.build_market_structure import main  # noqa: PLC0415
            # Force module reload so it picks up the monkeypatched data_dir
            import importlib
            import scripts.build_market_structure as _bms
            importlib.reload(_bms)
            _bms.main()
        finally:
            _cfg.data_dir = orig_data_dir
            if old_lane:
                os.environ["COLLECT_LANE"] = old_lane
            else:
                os.environ.pop("COLLECT_LANE", None)

    def test_no_ledger_without_collect_lane(self, tmp_path):
        """Without COLLECT_LANE, ledger.parquet must NOT be created."""
        self._run_builder_in_tmp(tmp_path, collect_lane=None)
        ledger_path = tmp_path / "data" / "market_structure" / "ledger.parquet"
        assert not ledger_path.exists(), (
            "Ledger was written without COLLECT_LANE=nightly — lane gate broken"
        )

    def test_ledger_written_with_nightly_collect_lane(self, tmp_path):
        """With COLLECT_LANE=nightly, ledger.parquet must be created."""
        self._run_builder_in_tmp(tmp_path, collect_lane="nightly")
        ledger_path = tmp_path / "data" / "market_structure" / "ledger.parquet"
        assert ledger_path.exists(), (
            "Ledger was NOT written with COLLECT_LANE=nightly"
        )
        df = pd.read_parquet(ledger_path)
        assert len(df) > 0, "Ledger exists but has zero rows"
        assert "type" in df.columns
        assert "date" in df.columns

    def test_latest_json_written_without_collect_lane(self, tmp_path):
        """latest.json and history.parquet must be written regardless of COLLECT_LANE."""
        self._run_builder_in_tmp(tmp_path, collect_lane=None)
        out_dir = tmp_path / "data" / "market_structure"
        assert (out_dir / "latest.json").exists(), "latest.json not written (off-lane)"
        assert (out_dir / "history.parquet").exists(), "history.parquet not written (off-lane)"
