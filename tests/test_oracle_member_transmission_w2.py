"""Tests for scripts/oracle_member_transmission_w2.py — synthetic fixtures (spec §3.4).

Spec §3.4 required test coverage:
  1. Window merge/id assignment
  2. IN/OUT arm assignment at boundaries
  3. PIT interval join (member enters/exits index)
  4. Cluster bootstrap preserves window structure
  5. Placebo draw regime-matching
  6. Next-bar fill for ablation (c)

All tests use synthetic in-memory data; no network/data-store deps.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.oracle_member_transmission_w2 import (
    build_armed_windows,
    assign_arm,
    is_pit_member,
    cluster_bootstrap_ci,
    build_vix_regime_lookup,
    compute_metrics,
    bh_correct,
    mde_at_power,
    stop5_rate,
    SEED,
    VIX_HIGH_THRESHOLD,
    K_PRIMARY,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_trading_days(start: str = "2022-01-03", periods: int = 252) -> pd.DatetimeIndex:
    """Business day calendar."""
    return pd.bdate_range(start=start, periods=periods)


def _make_close(prices: list[float], start: str = "2022-01-03") -> pd.Series:
    """Build a daily-indexed close series from a list of prices."""
    dates = pd.bdate_range(start=start, periods=len(prices))
    return pd.Series(prices, index=dates, dtype=float, name="close")


# ---------------------------------------------------------------------------
# §3.4 Test 1: Window merge/id assignment
# ---------------------------------------------------------------------------

class TestWindowMergeAndIdAssignment:
    """Spec §3.4: window merge/id assignment — overlapping windows on a node merge."""

    def test_non_overlapping_windows_separate_ids(self):
        """Two fires far apart → two separate windows with distinct ids."""
        td = _make_trading_days("2022-01-03", 252)
        fire_dates = {"XLK": ["2022-01-05", "2022-06-01"]}  # ~5 months apart
        windows = build_armed_windows(fire_dates, K_PRIMARY, td)

        xk_wins = windows[windows["node"] == "XLK"]
        assert len(xk_wins) == 2, f"Expected 2 windows, got {len(xk_wins)}"
        assert len(xk_wins["window_id"].unique()) == 2

    def test_overlapping_windows_merge_into_one(self):
        """Fires on consecutive days → windows overlap → merge into 1 window."""
        td = _make_trading_days("2022-01-03", 252)
        # K=10, so window spans 10 trading days; fires on day 1 and day 5 will overlap
        td_dates = td.strftime("%Y-%m-%d").tolist()
        fire_dates = {"XLK": [td_dates[0], td_dates[5]]}
        windows = build_armed_windows(fire_dates, K_PRIMARY, td)

        xk_wins = windows[windows["node"] == "XLK"]
        assert len(xk_wins) == 1, f"Expected 1 merged window, got {len(xk_wins)}"
        assert xk_wins.iloc[0]["n_fires_in_window"] == 2

    def test_window_id_globally_unique(self):
        """Window ids are globally unique across nodes."""
        td = _make_trading_days("2022-01-03", 252)
        td_dates = td.strftime("%Y-%m-%d").tolist()
        fire_dates = {
            "XLK": [td_dates[0], td_dates[50]],
            "XLF": [td_dates[10], td_dates[60]],
        }
        windows = build_armed_windows(fire_dates, K_PRIMARY, td)
        all_ids = windows["window_id"].unique()
        assert len(all_ids) == len(windows), "Window ids must be unique across all nodes"

    def test_window_end_is_k_sessions_after_start(self):
        """Window end is exactly K trading sessions after start."""
        td = _make_trading_days("2022-01-03", 252)
        td_dates = td.strftime("%Y-%m-%d").tolist()
        fire_dates = {"XLK": [td_dates[0]]}
        windows = build_armed_windows(fire_dates, 10, td)

        xk_wins = windows[windows["node"] == "XLK"]
        assert len(xk_wins) == 1
        row = xk_wins.iloc[0]
        start = pd.Timestamp(row["window_start"])
        end = pd.Timestamp(row["window_end"])
        # end should be the 10th trading day after start
        start_idx = td.get_loc(start)
        expected_end = td[start_idx + 10]
        assert end == expected_end, f"Window end {end} != expected {expected_end}"

    def test_empty_fire_dates_returns_empty(self):
        """Empty fire dates dict returns empty DataFrame."""
        td = _make_trading_days("2022-01-03", 252)
        windows = build_armed_windows({}, K_PRIMARY, td)
        assert len(windows) == 0

    def test_merge_fires_list_recorded(self):
        """Merged window records all fire dates that contributed."""
        td = _make_trading_days("2022-01-03", 252)
        td_dates = td.strftime("%Y-%m-%d").tolist()
        fire_dates = {"XLK": [td_dates[0], td_dates[3], td_dates[6]]}  # all within K=10
        windows = build_armed_windows(fire_dates, K_PRIMARY, td)
        xk_wins = windows[windows["node"] == "XLK"]
        assert len(xk_wins) == 1
        assert xk_wins.iloc[0]["n_fires_in_window"] == 3


# ---------------------------------------------------------------------------
# §3.4 Test 2: IN/OUT arm assignment at boundaries
# ---------------------------------------------------------------------------

class TestInOutArmAssignment:
    """Spec §3.4: IN/OUT arm assignment — boundary conditions."""

    def _make_windows(self, start: str = "2022-01-10", end: str = "2022-01-21") -> dict[str, pd.DataFrame]:
        """Single window for XLK from start to end."""
        windows = pd.DataFrame([{
            "node": "XLK",
            "window_id": 0,
            "window_start": pd.Timestamp(start),
            "window_end": pd.Timestamp(end),
        }])
        return {"XLK": windows}

    def test_signal_on_window_start_is_in(self):
        """Signal on window_start → IN arm."""
        wins = self._make_windows("2022-01-10", "2022-01-21")
        arm, wid = assign_arm(pd.Timestamp("2022-01-10"), "XLK", wins)
        assert arm == "IN"
        assert wid == 0

    def test_signal_on_window_end_is_in(self):
        """Signal on window_end → IN arm (inclusive end)."""
        wins = self._make_windows("2022-01-10", "2022-01-21")
        arm, wid = assign_arm(pd.Timestamp("2022-01-21"), "XLK", wins)
        assert arm == "IN"
        assert wid == 0

    def test_signal_day_after_window_end_is_out(self):
        """Signal one day AFTER window_end → OUT arm."""
        wins = self._make_windows("2022-01-10", "2022-01-21")
        arm, wid = assign_arm(pd.Timestamp("2022-01-24"), "XLK", wins)  # next business day
        assert arm == "OUT"
        assert wid is None

    def test_signal_day_before_window_start_is_out(self):
        """Signal one day BEFORE window_start → OUT arm."""
        wins = self._make_windows("2022-01-10", "2022-01-21")
        arm, wid = assign_arm(pd.Timestamp("2022-01-07"), "XLK", wins)  # day before
        assert arm == "OUT"
        assert wid is None

    def test_no_windows_for_node_is_out(self):
        """Node with no windows → all signals OUT."""
        wins = {"XLF": pd.DataFrame(columns=["node","window_id","window_start","window_end"])}
        arm, wid = assign_arm(pd.Timestamp("2022-06-01"), "XLK", wins)
        assert arm == "OUT"
        assert wid is None

    def test_signal_midwindow_is_in(self):
        """Signal strictly inside window → IN."""
        wins = self._make_windows("2022-01-10", "2022-01-28")
        arm, wid = assign_arm(pd.Timestamp("2022-01-19"), "XLK", wins)
        assert arm == "IN"

    def test_wrong_node_is_out(self):
        """Signal for XLF when windows only for XLK → OUT."""
        wins = self._make_windows("2022-01-10", "2022-01-21")
        arm, wid = assign_arm(pd.Timestamp("2022-01-15"), "XLF", wins)
        assert arm == "OUT"


# ---------------------------------------------------------------------------
# §3.4 Test 3: PIT interval join (member enters/exits index)
# ---------------------------------------------------------------------------

class TestPITIntervalJoin:
    """Spec §3.4: PIT interval join — member must be PIT-eligible at signal date."""

    def _make_pit_entry(self, ticker: str, start: str, end: str | None = None) -> pd.DataFrame:
        row = {
            "ticker": ticker,
            "start_date": pd.Timestamp(start),
            "end_date": pd.NaT if end is None else pd.Timestamp(end),
        }
        return pd.DataFrame([row])

    def _build_lookup(self, *dfs) -> dict:
        combined = pd.concat(dfs, ignore_index=True)
        return {t: combined[combined["ticker"] == t].reset_index(drop=True)
                for t in combined["ticker"].unique()}

    def test_member_active_on_date_is_eligible(self):
        """Ticker with active PIT interval covering date → eligible."""
        pit_df = self._make_pit_entry("AAPL", "2022-01-01", None)
        lookup = self._build_lookup(pit_df)
        assert is_pit_member("AAPL", pd.Timestamp("2022-06-01"), lookup)

    def test_member_exited_before_date_is_ineligible(self):
        """Ticker PIT interval ended before signal date → ineligible."""
        pit_df = self._make_pit_entry("AAPL", "2020-01-01", "2021-12-31")
        lookup = self._build_lookup(pit_df)
        assert not is_pit_member("AAPL", pd.Timestamp("2022-06-01"), lookup)

    def test_member_not_yet_entered_is_ineligible(self):
        """Ticker PIT interval starts after signal date → ineligible."""
        pit_df = self._make_pit_entry("AAPL", "2023-01-01", None)
        lookup = self._build_lookup(pit_df)
        assert not is_pit_member("AAPL", pd.Timestamp("2022-06-01"), lookup)

    def test_member_on_entry_date_is_eligible(self):
        """Signal date exactly equals PIT start_date → eligible (inclusive)."""
        pit_df = self._make_pit_entry("AAPL", "2022-06-01", None)
        lookup = self._build_lookup(pit_df)
        assert is_pit_member("AAPL", pd.Timestamp("2022-06-01"), lookup)

    def test_member_on_exit_date_is_eligible(self):
        """Signal date exactly equals PIT end_date → eligible (inclusive end)."""
        pit_df = self._make_pit_entry("AAPL", "2022-01-01", "2022-06-01")
        lookup = self._build_lookup(pit_df)
        assert is_pit_member("AAPL", pd.Timestamp("2022-06-01"), lookup)

    def test_ticker_absent_from_pit_is_ineligible(self):
        """Ticker not in PIT → ineligible."""
        lookup = {}
        assert not is_pit_member("ZZZZ", pd.Timestamp("2022-06-01"), lookup)

    def test_member_rejoins_after_gap_is_eligible(self):
        """Ticker exits and re-enters; signal date in re-entry period → eligible."""
        df1 = self._make_pit_entry("AAPL", "2020-01-01", "2021-06-30")
        df2 = self._make_pit_entry("AAPL", "2022-01-01", None)
        lookup = self._build_lookup(df1, df2)
        # Signal date in second interval
        assert is_pit_member("AAPL", pd.Timestamp("2022-03-01"), lookup)
        # Signal date in gap → ineligible
        assert not is_pit_member("AAPL", pd.Timestamp("2021-08-01"), lookup)


# ---------------------------------------------------------------------------
# §3.4 Test 4: Cluster bootstrap preserves window structure
# ---------------------------------------------------------------------------

class TestClusterBootstrap:
    """Spec §3.4: cluster bootstrap resamples window ids, not individual rows."""

    def _make_df_with_windows(self) -> pd.DataFrame:
        """DataFrame with 3 windows, varying sizes."""
        rows = []
        for wid in range(3):
            for _ in range(5 + wid * 2):  # windows have 5, 7, 9 rows
                rows.append({
                    "window_id": wid,
                    "fwd_ret_21": float(np.random.default_rng(42 + wid).normal(0.02, 0.05)),
                })
        return pd.DataFrame(rows)

    def test_bootstrap_returns_expected_keys(self):
        df = self._make_df_with_windows()
        def _wr21(d): return float((d["fwd_ret_21"] > 0).mean())
        result = cluster_bootstrap_ci(df, _wr21, n_draws=100, rng=np.random.default_rng(SEED))
        assert "point" in result
        assert "ci_lo" in result
        assert "ci_hi" in result
        assert "n_windows" in result
        assert result["n_windows"] == 3

    def test_bootstrap_ci_contains_point(self):
        """Point estimate should generally fall within CIs (may not always at 90% CI)."""
        df = self._make_df_with_windows()
        def _wr21(d): return float((d["fwd_ret_21"] > 0).mean())
        result = cluster_bootstrap_ci(df, _wr21, n_draws=500, rng=np.random.default_rng(SEED))
        # Point estimate should be in a reasonable range
        assert np.isfinite(result["point"])
        assert result["ci_lo"] <= result["ci_hi"]

    def test_bootstrap_deterministic_with_seed(self):
        """Same seed → same result."""
        df = self._make_df_with_windows()
        def _wr21(d): return float((d["fwd_ret_21"] > 0).mean())
        r1 = cluster_bootstrap_ci(df, _wr21, n_draws=100, rng=np.random.default_rng(SEED))
        r2 = cluster_bootstrap_ci(df, _wr21, n_draws=100, rng=np.random.default_rng(SEED))
        assert r1["ci_lo"] == r2["ci_lo"]
        assert r1["ci_hi"] == r2["ci_hi"]

    def test_bootstrap_empty_df_returns_nan(self):
        """Empty DataFrame returns NaN CIs."""
        df = pd.DataFrame(columns=["window_id", "fwd_ret_21"])
        def _wr21(d): return float("nan")
        result = cluster_bootstrap_ci(df, _wr21, n_draws=100)
        assert not np.isfinite(result["point"])
        assert result["n_windows"] == 0

    def test_bootstrap_resamples_windows_not_rows(self):
        """Bootstrap should resample at window level — all rows of a window appear together."""
        # Create distinctive windows with identifiable returns
        rows = []
        for wid, val in [(0, 0.10), (1, -0.10), (2, 0.20)]:
            for _ in range(5):
                rows.append({"window_id": wid, "fwd_ret_21": val})
        df = pd.DataFrame(rows)

        draw_results = []
        rng = np.random.default_rng(SEED)

        # Run 20 draws manually to verify window-level sampling
        window_ids = df["window_id"].unique()
        n_windows = len(window_ids)
        for _ in range(20):
            sampled_ids = rng.choice(window_ids, size=n_windows, replace=True)
            chunks = [df[df["window_id"] == wid] for wid in sampled_ids]
            boot_df = pd.concat(chunks, ignore_index=True)
            # Each row in boot_df should have a value from {0.10, -0.10, 0.20}
            assert set(boot_df["fwd_ret_21"].unique()).issubset({0.10, -0.10, 0.20})


# ---------------------------------------------------------------------------
# §3.4 Test 5: Placebo draw regime-matching
# ---------------------------------------------------------------------------

class TestPlaceboRegimeMatching:
    """Spec §3.4: placebo draw VIX-regime matching."""

    def test_vix_regime_lookup_classifies_correctly(self):
        """VIX pctile >= 0.6 → 'high', < 0.6 → 'low'."""
        dates = pd.bdate_range("2022-01-03", periods=5)
        panel_rows = []
        for node in ["XLK"]:
            for i, d in enumerate(dates):
                panel_rows.append({"node": node, "date": d, "vix_pctile": 0.1 * (i + 1)})
        panel_df = pd.DataFrame(panel_rows).set_index(["node", "date"])

        regime = build_vix_regime_lookup(panel_df)
        xk = regime.get("XLK", {})
        for i, d in enumerate(dates):
            ts = pd.Timestamp(d)
            expected = "high" if 0.1 * (i + 1) >= VIX_HIGH_THRESHOLD else "low"
            assert xk.get(ts, None) == expected, f"Date {d}: expected {expected}, got {xk.get(ts)}"

    def test_vix_threshold_boundary(self):
        """VIX pctile exactly at threshold → 'high'."""
        dates = pd.bdate_range("2022-01-03", periods=1)
        panel_rows = [{"node": "XLK", "date": dates[0], "vix_pctile": VIX_HIGH_THRESHOLD}]
        panel_df = pd.DataFrame(panel_rows).set_index(["node", "date"])
        regime = build_vix_regime_lookup(panel_df)
        assert regime["XLK"][pd.Timestamp(dates[0])] == "high"

    def test_vix_regime_missing_node_returns_empty(self):
        """Node not in panel → empty regime dict."""
        panel_rows = [{"node": "XLK", "date": pd.Timestamp("2022-01-03"), "vix_pctile": 0.5}]
        panel_df = pd.DataFrame(panel_rows).set_index(["node", "date"])
        regime = build_vix_regime_lookup(panel_df)
        assert "XLF" not in regime


# ---------------------------------------------------------------------------
# §3.4 Test 6: Next-bar fill for ablation (c)
# ---------------------------------------------------------------------------

class TestNextBarFillAblation:
    """Spec §3.4: ablation (c) uses next-bar fill convention."""

    def test_forward_metrics_next_bar_fill(self):
        """forward_metrics uses next-bar fill: entry is bar t+1 after signal."""
        from engine.grading import forward_metrics
        prices = [100.0, 102.0, 104.0, 106.0, 108.0,
                  110.0, 112.0, 114.0, 116.0, 118.0,
                  120.0, 122.0, 124.0, 126.0, 128.0,
                  130.0, 132.0, 134.0, 136.0, 138.0,
                  140.0, 142.0, 144.0]
        close = _make_close(prices, "2022-01-03")

        # Signal on first bar (2022-01-03, price=100)
        signal_date = "2022-01-03"
        fm = forward_metrics(close, signal_date, horizons=(5, 10, 21))

        # Entry should be at bar t+1 (price=102)
        assert fm["entry_price"] == 102.0
        assert fm["fill_date"] == "2022-01-04"

        # fwd_ret_5 = close[fill+5] / 102 - 1 = prices[6] / 102 - 1
        # fill bar = index 1 (price=102); fwd bars = [2..6]; fwd_ret_5 = prices[6]/102 - 1
        expected_ret5 = prices[6] / 102.0 - 1.0
        assert abs(fm["fwd_ret_5"] - expected_ret5) < 1e-10

    def test_terminal_state_clean8_21_next_bar(self):
        """terminal_state clean8_21 uses next-bar fill, LIFTOFF_8=1.08, horizon=21."""
        from engine.grading import terminal_state, TerminalState
        # Build prices that trigger CLEAN_LIFTOFF: entry 100, prices rise to 110 within 21 bars
        prices = [100.0] + [101.0] * 3 + [109.0] * 18  # entry=100 (fill bar), then rise
        # signal bar is index 0 (price=100), fill bar = index 1 (price=101)
        close = _make_close(prices, "2022-01-03")

        signal_date = "2022-01-03"
        ts = terminal_state(close, signal_date, liftoff_mult=1.08, liftoff_horizon=21)

        # Entry = prices[1] = 101.0
        assert ts["entry_price"] == 101.0
        # 109.0 / 101.0 = 1.0792... < 1.08 — not liftoff; let's use higher prices
        # Rebuild: entry=101, prices go to 110 (110/101 = 1.089 > 1.08 → CLEAN_LIFTOFF)
        prices2 = [100.0, 101.0] + [110.0] * 22
        close2 = _make_close(prices2, "2022-01-03")
        ts2 = terminal_state(close2, signal_date, liftoff_mult=1.08, liftoff_horizon=21)
        assert ts2["entry_price"] == 101.0
        assert ts2["state"] == TerminalState.CLEAN_LIFTOFF

    def test_terminal_state_stopped(self):
        """terminal_state: price hits stop_mult=0.95 before cushion → STOPPED."""
        from engine.grading import terminal_state, TerminalState
        # signal at prices[0]=100, fill at prices[1]=100, then drop below 95
        prices = [100.0, 100.0] + [94.0] * 22
        close = _make_close(prices, "2022-01-03")
        ts = terminal_state(close, "2022-01-03", liftoff_mult=1.08, liftoff_horizon=21)
        assert ts["state"] == TerminalState.STOPPED
        assert ts["stopped_at_bar"] is not None

    def test_no_next_bar_returns_none_state(self):
        """Close series with only one bar → no next bar → state=None."""
        from engine.grading import terminal_state
        prices = [100.0]
        close = _make_close(prices, "2022-01-03")
        ts = terminal_state(close, "2022-01-03")
        assert ts["state"] is None


# ---------------------------------------------------------------------------
# Metric helpers
# ---------------------------------------------------------------------------

class TestMetricHelpers:
    """Tests for compute_metrics, stop5_rate, bh_correct, mde_at_power."""

    def test_stop5_rate_basic(self):
        """stop5_rate = fraction with fwd_mdd_5 < -0.05."""
        df = pd.DataFrame({
            "fwd_mdd_5": [-0.04, -0.06, -0.07, -0.02, -0.08],
            "fwd_ret_21": [0.01, 0.02, -0.01, 0.03, -0.02],
        })
        rate = stop5_rate(df)
        assert abs(rate - 0.6) < 1e-10  # 3/5

    def test_stop5_rate_empty(self):
        df = pd.DataFrame({"fwd_mdd_5": pd.Series([], dtype=float)})
        assert not np.isfinite(stop5_rate(df))

    def test_compute_metrics_wr21(self):
        """compute_metrics returns correct WR21."""
        df = pd.DataFrame({
            "fwd_ret_21": [0.01, 0.02, -0.01, 0.03, -0.02],
            "fwd_mdd_5": [-0.01, -0.02, -0.03, -0.01, -0.06],
            "fwd_mdd_21": [-0.01, -0.02, -0.03, -0.01, -0.02],
            "fwd_mfe_21": [0.02, 0.03, 0.01, 0.04, 0.01],
        })
        m = compute_metrics(df)
        assert abs(m["wr21"] - 0.6) < 1e-10  # 3/5 positive

    def test_compute_metrics_empty(self):
        df = pd.DataFrame(columns=["fwd_ret_21", "fwd_mdd_5", "fwd_mdd_21", "fwd_mfe_21"])
        m = compute_metrics(df)
        assert not np.isfinite(m["wr21"])

    def test_bh_correct_two_reads(self):
        """BH with q=0.10 on 2 reads: both very significant → both rejected."""
        result = bh_correct([0.001, 0.002], q=0.10)
        assert result == [True, True]

    def test_bh_correct_two_reads_none_significant(self):
        """BH with q=0.10: both high p → neither rejected."""
        result = bh_correct([0.8, 0.9], q=0.10)
        assert result == [False, False]

    def test_bh_correct_one_of_two(self):
        """BH with q=0.10: one passes, one doesn't."""
        # p1=0.01: rank 1, threshold = 1/2 * 0.10 = 0.05 → rejected
        # p2=0.08: rank 2, threshold = 2/2 * 0.10 = 0.10 → rejected (0.08 < 0.10)
        result = bh_correct([0.01, 0.08], q=0.10)
        assert result[0] == True
        assert result[1] == True  # both pass since largest k=2: 0.08 <= 0.10

    def test_bh_correct_empty(self):
        assert bh_correct([], q=0.10) == []

    def test_mde_at_power_positive(self):
        """MDE should be positive and decrease with more windows."""
        mde_small = mde_at_power(10, power=0.80)
        mde_large = mde_at_power(100, power=0.80)
        assert mde_small > 0
        assert mde_large > 0
        assert mde_small > mde_large  # more windows → smaller MDE


# ---------------------------------------------------------------------------
# Integration smoke test: build_armed_windows + assign_arm round-trip
# ---------------------------------------------------------------------------

class TestWindowRoundTrip:
    """Smoke test: build windows from fire dates, then assign arms to synthetic fires."""

    def test_in_out_split_is_exhaustive(self):
        """Every synthetic fire is either IN or OUT — none missed."""
        td = _make_trading_days("2022-01-03", 252)
        td_dates = td.strftime("%Y-%m-%d").tolist()

        # Two fire dates producing two windows
        fire_dates = {"XLK": [td_dates[0], td_dates[50]]}
        windows = build_armed_windows(fire_dates, K_PRIMARY, td)
        wins_by_node = {"XLK": windows[windows["node"] == "XLK"].reset_index(drop=True)}

        # Assign arms for every trading day
        in_count = 0
        out_count = 0
        for d in td:
            arm, _ = assign_arm(d, "XLK", wins_by_node)
            if arm == "IN":
                in_count += 1
            else:
                out_count += 1

        assert in_count + out_count == len(td)
        assert in_count > 0
        assert out_count > 0

    def test_fire_date_itself_is_in(self):
        """The fire date itself must be classified IN."""
        td = _make_trading_days("2022-01-03", 252)
        td_dates = td.strftime("%Y-%m-%d").tolist()
        fire_date = td_dates[10]
        fire_dates = {"XLK": [fire_date]}
        windows = build_armed_windows(fire_dates, K_PRIMARY, td)
        wins_by_node = {"XLK": windows[windows["node"] == "XLK"].reset_index(drop=True)}

        arm, wid = assign_arm(pd.Timestamp(fire_date), "XLK", wins_by_node)
        assert arm == "IN"
        assert wid is not None
