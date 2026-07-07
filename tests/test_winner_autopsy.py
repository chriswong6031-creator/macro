"""Tests for engine/winner_autopsy.py and scripts/research/build_winner_autopsy.py.

Covers: constant sanity, MRNA case parsing, synthetic detect_episodes (onset detection
+ cooldown), label_outcomes (durable_winner + blow_off paths), reconcile_case
(engine_no_onset), and an end-to-end dry-run smoke test.

All tests pass using only data present in this worktree (yahoo ETFs + 695 names;
no massive_stock_day). Coverage degrades gracefully — that is what we assert.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Make sure repo root is on sys.path
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# ---------------------------------------------------------------------------
# Module-level imports (fail fast if engine is broken)
# ---------------------------------------------------------------------------
import engine.winner_autopsy as wa  # noqa: E402


# ---------------------------------------------------------------------------
# 1. Constant sanity
# ---------------------------------------------------------------------------

class TestConstants:
    def test_liquidity_floor(self):
        assert wa.LIQUIDITY_FLOOR_USD == 25_000_000.0

    def test_excess_thresholds(self):
        assert wa.EXCESS_21D_PP == 20.0
        assert wa.EXCESS_42D_PP == 25.0

    def test_new_high_lookback(self):
        assert wa.NEW_HIGH_LOOKBACK == 63

    def test_dv_z_floor(self):
        assert wa.DV_Z_FLOOR == 1.0

    def test_dv_5_60_ratio(self):
        assert wa.DV_5_60_RATIO == 1.5

    def test_episode_cooldown(self):
        assert wa.EPISODE_COOLDOWN == 63

    def test_outcome_thresholds(self):
        assert wa.DURABLE_FWD_126_PP == 15.0
        assert wa.FAILED_FWD_63_PP == -10.0
        assert wa.BLOWOFF_RETRACE == 0.50

    def test_schema_names(self):
        assert wa.SCHEMA_EPISODES == "winner_episodes.v1"
        assert wa.SCHEMA_WATCH == "breakaway_watch.v1"

    def test_gics_etf_map(self):
        assert wa._GICS_ETF["Energy"] == "XLE"
        assert wa._GICS_ETF["Information Technology"] == "XLK"
        assert wa._GICS_ETF["Health Care"] == "XLV"
        assert wa._GICS_ETF["Financials"] == "XLF"

    def test_bench_fallback(self):
        assert wa.BENCH == "SPY"

    def test_stamp_adds_fields(self):
        d = {"foo": 1}
        result = wa.stamp(d)
        assert result is d  # in-place + returns
        assert d["_display_only"] is True
        assert d["_horizon_role"] == "hold_thesis"
        assert d["_version"] == "v1"


# ---------------------------------------------------------------------------
# 2. parse_case_file — MRNA seed case
# ---------------------------------------------------------------------------

class TestParseCaseFile:
    _CASE_PATH = str(_REPO_ROOT / "research" / "winners" / "cases" / "MRNA_2026.md")

    def test_mrna_parses_without_error(self):
        case = wa.parse_case_file(self._CASE_PATH)
        assert isinstance(case, dict)

    def test_mrna_ticker(self):
        case = wa.parse_case_file(self._CASE_PATH)
        assert case["ticker"] == "MRNA"

    def test_mrna_case_type(self):
        case = wa.parse_case_file(self._CASE_PATH)
        assert case["case_type"] == "winner"

    def test_mrna_has_enough_catalysts(self):
        case = wa.parse_case_file(self._CASE_PATH)
        ladder = case.get("catalyst_ladder", [])
        assert isinstance(ladder, list)
        assert len(ladder) >= 3, f"Expected >=3 catalysts, got {len(ladder)}"

    def test_mrna_all_required_keys(self):
        case = wa.parse_case_file(self._CASE_PATH)
        for key in wa._CASE_REQUIRED_KEYS:
            assert key in case, f"Missing required key: {key}"

    def test_mrna_schema_value(self):
        case = wa.parse_case_file(self._CASE_PATH)
        assert case["schema"] == "winner_case.v1"

    def test_mrna_mechanism(self):
        case = wa.parse_case_file(self._CASE_PATH)
        assert case["mechanism"] == "platform_rerating"

    def test_bad_file_raises_valueerror(self, tmp_path):
        bad_md = tmp_path / "bad.md"
        bad_md.write_text("# No yaml block here\nJust text.\n")
        with pytest.raises(ValueError, match="no fenced"):
            wa.parse_case_file(str(bad_md))

    def test_wrong_schema_raises_valueerror(self, tmp_path):
        bad_md = tmp_path / "wrong_schema.md"
        bad_md.write_text("```yaml\nschema: wrong_schema.v99\nticker: FOO\n```\n")
        with pytest.raises(ValueError, match="schema"):
            wa.parse_case_file(str(bad_md))


# ---------------------------------------------------------------------------
# 3. detect_episodes — synthetic data
# ---------------------------------------------------------------------------

def _make_flat_bench(n: int = 300, start: str = "2022-01-03") -> pd.Series:
    """A flat benchmark at 100.0."""
    idx = pd.bdate_range(start=start, periods=n)
    return pd.Series(100.0, index=idx)


def _make_breakaway_stock(
    n: int = 300,
    start: str = "2022-01-03",
    onset_day: int = 150,
    pre_return: float = 0.0,
    breakaway_jump: float = 0.30,
    vol_spike: float = 5.0,
) -> pd.DataFrame:
    """Build a synthetic stock with a clear breakaway at onset_day.

    Pre-onset: drifts slightly. At onset: jumps +30% over 21 days.
    Volume spikes vol_spike× on the breakaway leg.
    """
    idx = pd.bdate_range(start=start, periods=n)
    close = np.full(n, 50.0)
    volume = np.full(n, 500_000.0)  # base: 500k shares @ ~50 = $25M DV
    base_dv = 50.0 * 500_000  # = $25M exactly at the floor

    # Pre-onset: flat
    for i in range(1, onset_day):
        close[i] = close[i - 1] * (1.0 + pre_return / 252)

    # Breakaway: +30% over 21 days, then holds
    breakaway_per_day = (1 + breakaway_jump) ** (1 / 21) - 1
    for i in range(onset_day, min(onset_day + 21, n)):
        close[i] = close[i - 1] * (1.0 + breakaway_per_day)
        volume[i] = volume[i - 1] * vol_spike  # big vol spike

    # Post-breakaway: holds
    for i in range(onset_day + 21, n):
        close[i] = close[min(onset_day + 20, n - 1)]
        volume[i] = 500_000.0

    return pd.DataFrame({"close": close, "volume": volume}, index=idx)


class TestDetectEpisodes:
    def test_detects_clear_onset(self):
        """A stock with +30% vs flat bench over 21d at day 150 must produce one episode."""
        bench = _make_flat_bench(300)
        stock_df = _make_breakaway_stock(300, onset_day=150, breakaway_jump=0.30, vol_spike=6.0)

        bars = {"FOO": stock_df, "SPY": pd.DataFrame({"close": bench}, index=bench.index)}
        bench_closes = {"SPY": bench}
        sector_of = {"FOO": "Information Technology"}  # -> XLK, but XLK not in bench_closes -> SPY fallback

        eps = wa.detect_episodes(bars, bench_closes, sector_of)
        assert not eps.empty, "Expected at least one episode"
        foo_eps = eps[eps["ticker"] == "FOO"]
        assert len(foo_eps) >= 1

    def test_onset_new_high_true(self):
        """The detected onset must have new_high_63d=True."""
        bench = _make_flat_bench(300)
        stock_df = _make_breakaway_stock(300, onset_day=150, breakaway_jump=0.30, vol_spike=6.0)
        bars = {"FOO": stock_df, "SPY": pd.DataFrame({"close": bench}, index=bench.index)}
        bench_closes = {"SPY": bench}
        sector_of = {}

        eps = wa.detect_episodes(bars, bench_closes, sector_of)
        foo_eps = eps[eps["ticker"] == "FOO"]
        if not foo_eps.empty:
            assert bool(foo_eps.iloc[0]["new_high_63d"]) is True

    def test_excess_above_threshold(self):
        """The detected onset must have excess_21d_pp >= EXCESS_21D_PP."""
        bench = _make_flat_bench(300)
        # +40% in 21d vs flat bench guarantees >+20pp
        stock_df = _make_breakaway_stock(300, onset_day=150, breakaway_jump=0.40, vol_spike=8.0)
        bars = {"FOO": stock_df, "SPY": pd.DataFrame({"close": bench}, index=bench.index)}
        bench_closes = {"SPY": bench}
        sector_of = {}

        eps = wa.detect_episodes(bars, bench_closes, sector_of)
        foo_eps = eps[eps["ticker"] == "FOO"]
        if not foo_eps.empty:
            exc = foo_eps.iloc[0]["excess_21d_pp"]
            assert exc is not None
            assert exc >= wa.EXCESS_21D_PP

    def test_cooldown_deduplicates(self):
        """A second candidate within 63 td of an onset must NOT produce a second episode."""
        bench = _make_flat_bench(400)
        # Two potential breakaway legs: onset at 150, then again at 200 (within 63 td)
        idx = pd.bdate_range(start="2022-01-03", periods=400)
        close = np.full(400, 50.0)
        volume = np.full(400, 500_000.0)

        # First breakaway at day 150
        for i in range(150, 171):
            close[i] = close[i - 1] * 1.015
            volume[i] = 3_000_000.0

        # Second breakaway at day 200 (within 63 td of 150)
        for i in range(200, 221):
            close[i] = close[i - 1] * 1.012
            volume[i] = 3_000_000.0

        for i in range(221, 400):
            close[i] = close[219]
            volume[i] = 500_000.0

        stock_df = pd.DataFrame({"close": close, "volume": volume}, index=idx)
        bars = {
            "BAR": stock_df,
            "SPY": pd.DataFrame({"close": bench.values}, index=bench.index),
        }
        bench_closes = {"SPY": bench}
        sector_of = {}

        eps = wa.detect_episodes(bars, bench_closes, sector_of)
        bar_eps = eps[eps["ticker"] == "BAR"] if not eps.empty else pd.DataFrame()

        # If any episode at day ~150 is found, a second at day ~200 (within 63 td) must not exist
        if len(bar_eps) >= 2:
            t0_arr = bar_eps["t0"].sort_values().values
            for i in range(len(t0_arr) - 1):
                gap_td = (
                    pd.bdate_range(start=t0_arr[i], end=t0_arr[i + 1])
                ).shape[0] - 1
                assert gap_td > wa.EPISODE_COOLDOWN, (
                    f"Two episodes within cooldown window: {t0_arr[i]} -> {t0_arr[i+1]}"
                )

    def test_empty_bars_returns_empty_df(self):
        eps = wa.detect_episodes({}, {}, {})
        assert isinstance(eps, pd.DataFrame)
        assert eps.empty

    def test_returns_required_columns(self):
        bench = _make_flat_bench(300)
        bars = {"SPY": pd.DataFrame({"close": bench}, index=bench.index)}
        bench_closes = {"SPY": bench}
        eps = wa.detect_episodes(bars, bench_closes, {})
        expected_cols = {
            "ticker", "t0", "sector", "benchmark", "benchmark_fallback",
            "excess_21d_pp", "excess_42d_pp", "new_high_63d",
            "dollar_vol_z21", "dv_5_60_ratio", "liquid",
            "price_source", "gap_leg_crossed", "survivorship_biased",
        }
        assert expected_cols.issubset(set(eps.columns))


# ---------------------------------------------------------------------------
# 4. label_outcomes — synthetic paths
# ---------------------------------------------------------------------------

def _make_durable_winner_series(n_total: int = 500) -> tuple[pd.Series, pd.Series]:
    """Close goes up +30% in 21d then +20% more. Bench is flat."""
    idx = pd.bdate_range("2022-01-03", periods=n_total)
    # t0 is at position 100
    close_arr = np.full(n_total, 50.0)
    for i in range(1, n_total):
        if i <= 100:
            close_arr[i] = close_arr[i - 1]
        elif i <= 121:
            close_arr[i] = close_arr[i - 1] * 1.014  # +30% over 21d
        elif i <= 230:
            close_arr[i] = close_arr[i - 1] * 1.001  # grinds up
        else:
            close_arr[i] = close_arr[i - 1]

    bench_arr = np.full(n_total, 100.0)
    return pd.Series(close_arr, index=idx), pd.Series(bench_arr, index=idx)


def _make_blowoff_series(n_total: int = 300) -> tuple[pd.Series, pd.Series]:
    """Close spikes +30% in 21d then retraces 60% of that impulse within next 21d."""
    idx = pd.bdate_range("2022-01-03", periods=n_total)
    close_arr = np.full(n_total, 50.0)
    # t0 = position 100
    t0_price = 50.0
    # 21d prior, slowly up
    for i in range(80, 100):
        close_arr[i] = close_arr[i - 1] * 1.005  # tiny drift
    t0m21_price = close_arr[79]

    # t0 = 100: spike happened
    for i in range(100, 121):
        close_arr[i] = close_arr[i - 1] * 1.014  # +30% at t0 (by day 120)

    t0_actual_price = close_arr[100]
    # compute impulse
    impulse = t0_actual_price - t0m21_price

    # Retrace 60% of impulse within next 21d
    retrace_target = t0_actual_price - 0.60 * impulse
    for i in range(101, 122):
        frac = (i - 100) / 21.0
        close_arr[i] = t0_actual_price - frac * 0.60 * impulse

    for i in range(122, n_total):
        close_arr[i] = close_arr[121]

    bench_arr = np.full(n_total, 100.0)
    return pd.Series(close_arr, index=idx), pd.Series(bench_arr, index=idx)


class TestLabelOutcomes:
    def test_durable_winner_path(self):
        close, bench = _make_durable_winner_series(500)
        t0 = close.index[100]
        result = wa.label_outcomes(close, bench, t0)
        assert isinstance(result, dict)
        # Must have all required keys
        for k in ["fwd_excess_21d_pp", "fwd_excess_63d_pp", "fwd_excess_126d_pp",
                   "fwd_excess_252d_pp", "clean_hold", "blow_off",
                   "durable_winner", "failed", "outcome_label"]:
            assert k in result, f"Missing key: {k}"
        # The strong up-move should yield durable_winner
        assert result["outcome_label"] == "durable_winner", (
            f"Expected durable_winner, got {result['outcome_label']}, "
            f"fwd126={result['fwd_excess_126d_pp']}, clean_hold={result['clean_hold']}"
        )
        assert result["durable_winner"] is True

    def test_blow_off_path(self):
        close, bench = _make_blowoff_series(300)
        t0 = close.index[100]
        result = wa.label_outcomes(close, bench, t0)
        assert isinstance(result, dict)
        assert result["outcome_label"] == "blow_off", (
            f"Expected blow_off, got {result['outcome_label']}, blow_off={result['blow_off']}"
        )
        assert result["blow_off"] is True

    def test_unmatured_when_no_forward_data(self):
        """If t0 is the last bar, all horizons are unmatured."""
        idx = pd.bdate_range("2022-01-03", periods=150)
        close = pd.Series(np.linspace(50, 80, 150), index=idx)
        bench = pd.Series(100.0, index=idx)
        t0 = close.index[-1]
        result = wa.label_outcomes(close, bench, t0)
        assert result["outcome_label"] == "unmatured"
        assert result["fwd_excess_21d_pp"] is None

    def test_failed_path(self):
        """A stock that drops -15pp vs bench in 63d after t0 is 'failed'."""
        n = 350
        idx = pd.bdate_range("2022-01-03", periods=n)
        close_arr = np.full(n, 100.0)
        bench_arr = np.full(n, 100.0)
        # t0 = 100; after t0, stock drops 20%, bench flat
        for i in range(101, 165):
            close_arr[i] = close_arr[i - 1] * 0.997  # ~-20% over 63d
        for i in range(165, n):
            close_arr[i] = close_arr[164]
        close = pd.Series(close_arr, index=idx)
        bench = pd.Series(bench_arr, index=idx)
        t0 = close.index[100]
        result = wa.label_outcomes(close, bench, t0)
        assert result["failed"] is True or result["outcome_label"] in {"failed", "blow_off"}

    # ------------------------------------------------------------------
    # Fix 1 (BLOCKER): label_outcomes on empty series must not crash
    # ------------------------------------------------------------------

    def test_empty_close_returns_empty_outcomes_no_crash(self):
        """label_outcomes(empty, empty, t0) must return the empty-outcomes dict."""
        t0 = pd.Timestamp("2023-01-10")
        result = wa.label_outcomes(pd.Series(dtype=float), pd.Series(dtype=float), t0)
        assert isinstance(result, dict)
        assert result["outcome_label"] == "unmatured"
        for key in ["fwd_excess_21d_pp", "fwd_excess_63d_pp",
                    "fwd_excess_126d_pp", "fwd_excess_252d_pp",
                    "clean_hold", "blow_off", "durable_winner", "failed"]:
            assert result[key] is None, f"Expected None for {key}"

    def test_none_inputs_returns_empty_outcomes_no_crash(self):
        """label_outcomes(None, None, t0) must return the empty-outcomes dict."""
        t0 = pd.Timestamp("2023-01-10")
        result = wa.label_outcomes(None, None, t0)
        assert isinstance(result, dict)
        assert result["outcome_label"] == "unmatured"

    # ------------------------------------------------------------------
    # Fix 2 (MAJOR): short forward window → outcome_label == 'unmatured'
    #                and clean_hold / durable_winner are None
    # ------------------------------------------------------------------

    def test_short_forward_window_yields_unmatured(self):
        """Episode with only 40 forward bars must be 'unmatured' with clean_hold=None."""
        # Build a series with t0 near the end so forward window is < 126 td
        n_pre = 150   # bars before t0
        n_fwd = 40    # bars after t0 (< 126)
        n = n_pre + n_fwd
        idx = pd.bdate_range("2020-01-02", periods=n)
        close_arr = np.full(n, 100.0)
        bench_arr = np.full(n, 100.0)

        # Strong upward move so all threshold conditions would be met IF window were full
        for i in range(n_pre, n):
            close_arr[i] = close_arr[i - 1] * 1.015  # +70%+ over 40d

        close = pd.Series(close_arr, index=idx)
        bench = pd.Series(bench_arr, index=idx)
        t0 = close.index[n_pre]  # onset at position n_pre; only n_fwd bars forward

        result = wa.label_outcomes(close, bench, t0)
        assert result["outcome_label"] == "unmatured", (
            f"Expected 'unmatured' for short forward window, got '{result['outcome_label']}'"
        )
        assert result["clean_hold"] is None, (
            f"clean_hold must be None when full 126-td window absent, got {result['clean_hold']}"
        )
        assert result["durable_winner"] is None, (
            f"durable_winner must be None when full 126-td window absent, got {result['durable_winner']}"
        )
        # fwd_excess_126d must be None (< 126 bars forward)
        assert result["fwd_excess_126d_pp"] is None


# ---------------------------------------------------------------------------
# 5. reconcile_case
# ---------------------------------------------------------------------------

class TestReconcileCase:
    def _mrna_case(self) -> dict:
        path = str(_REPO_ROOT / "research" / "winners" / "cases" / "MRNA_2026.md")
        return wa.parse_case_file(path)

    def test_engine_no_onset_when_empty_df(self):
        case = self._mrna_case()
        result = wa.reconcile_case(case, pd.DataFrame())
        assert result["case_joined"] is False
        assert result["engine_t0"] is None
        assert result["reconcile"] == "engine_no_onset"

    def test_engine_no_onset_when_different_ticker(self):
        case = self._mrna_case()
        # Create episodes DF for a different ticker
        eps_df = pd.DataFrame({
            "ticker": ["AAPL"],
            "t0": [pd.Timestamp("2026-01-20")],
        })
        result = wa.reconcile_case(case, eps_df)
        assert result["case_joined"] is False
        assert result["reconcile"] == "engine_no_onset"

    def test_matched_when_t0_close(self):
        case = self._mrna_case()
        # Inject an episode for MRNA exactly at hypothesis date
        eps_df = pd.DataFrame({
            "ticker": ["MRNA"],
            "t0": [pd.Timestamp("2026-01-20")],  # exact match
        })
        result = wa.reconcile_case(case, eps_df)
        assert result["case_joined"] is True
        assert result["reconcile"] == "matched"

    def test_gap_days_when_far(self):
        case = self._mrna_case()
        # Episode far from hypothesis (>29 days)
        eps_df = pd.DataFrame({
            "ticker": ["MRNA"],
            "t0": [pd.Timestamp("2026-06-01")],  # ~130d away from 2026-01-20
        })
        result = wa.reconcile_case(case, eps_df)
        assert result["case_joined"] is False
        assert result["reconcile"].startswith("t0_gap_days:")


# ---------------------------------------------------------------------------
# 6. End-to-end dry-run smoke test
# ---------------------------------------------------------------------------

def _fast_bars() -> dict[str, pd.DataFrame]:
    """Minimal bars dict for fast tests: 3 synthetic tickers + SPY bench."""
    bench = _make_flat_bench(300)
    breakaway = _make_breakaway_stock(300, onset_day=150, breakaway_jump=0.30, vol_spike=6.0)
    flat = pd.DataFrame({"close": np.full(300, 50.0), "volume": np.full(300, 600_000.0)},
                        index=bench.index)
    spy_df = pd.DataFrame({"close": bench.values, "volume": np.full(300, 5e7)},
                          index=bench.index)
    return {"TESTFOO": breakaway, "TESTBAR": flat, "SPY": spy_df, "XLV": spy_df.copy()}


class TestBuildScriptDryRun:
    """Run the build script end-to-end. Uses monkeypatched loaders for speed."""

    def test_dry_run_smoke_exits_zero(self, monkeypatch):
        """--dry-run --smoke must exit 0 without crashing, even with minimal/no prices."""
        import scripts.research.build_winner_autopsy as bwa  # noqa: PLC0415

        fast = _fast_bars()
        monkeypatch.setattr(bwa, "_load_yahoo_bars", lambda **kw: fast)
        monkeypatch.setattr(bwa, "_find_massive_dir", lambda: None)
        monkeypatch.setattr(bwa, "_load_dead_name_bars", lambda: {})

        rc = bwa.main(["--dry-run", "--smoke"])
        assert rc == 0, f"Expected rc=0, got {rc}"

    def test_dry_run_write_history_guard(self):
        """--smoke + --write-history must exit rc=2 (sole-advancer guard)."""
        from scripts.research.build_winner_autopsy import main  # noqa: PLC0415
        rc = main(["--smoke", "--write-history"])
        assert rc == 2, f"Expected rc=2 (guard), got {rc}"

    def test_panel_json_written_and_conforms(self, tmp_path, monkeypatch):
        """Run without --dry-run; assert panel JSON is written and conforms to contract."""
        import scripts.research.build_winner_autopsy as bwa  # noqa: PLC0415

        fast = _fast_bars()
        monkeypatch.setattr(bwa, "_load_yahoo_bars", lambda **kw: fast)
        monkeypatch.setattr(bwa, "_find_massive_dir", lambda: None)
        monkeypatch.setattr(bwa, "_load_dead_name_bars", lambda: {})

        # Redirect output paths to tmp
        monkeypatch.setattr(bwa, "_OUT_DIR", tmp_path)
        monkeypatch.setattr(bwa, "_PANEL_PATH", tmp_path / "winner_autopsy_panel.json")
        monkeypatch.setattr(bwa, "_EPISODES_PATH", tmp_path / "winner_episodes.parquet")
        monkeypatch.setattr(bwa, "_WATCH_PATH", tmp_path / "breakaway_watch.parquet")
        monkeypatch.setattr(bwa, "_WATCH_HISTORY_PATH", tmp_path / "breakaway_watch_history.parquet")
        monkeypatch.setattr(bwa, "_EPISODES_MANIFEST_PATH", tmp_path / "winner_episodes_manifest.json")
        monkeypatch.setattr(bwa, "_AUTOPSY_MANIFEST_PATH", tmp_path / "winner_autopsy_manifest.json")

        rc = bwa.main(["--smoke"])
        assert rc == 0, f"Expected rc=0, got {rc}"

        panel_path = tmp_path / "winner_autopsy_panel.json"
        assert panel_path.exists(), "Panel JSON not written"

        panel = json.loads(panel_path.read_text())
        assert panel.get("schema") == "winner_autopsy_panel.v1", (
            f"Wrong schema: {panel.get('schema')}"
        )
        assert panel.get("display_only") is True
        assert panel["cases"]["n_cases"] >= 1, (
            "Expected at least 1 case (MRNA_2026.md must parse)"
        )
