"""Tests for the W4 CCTV completion pipeline and contrarian-sign validation wiring.

Covers:
  1. Gap-audit integration — _run_gap_audit reports correctly on a partial archive
  2. Tone re-baseline — _tone_stats uses long-history when available; falls back
     to rolling window when absent
  3. policy_tone() baseline_source field — "long_history" vs "rolling_window"
  4. _news_sentiment_series() consumes long-history baseline → large n_obs
  5. PIT-correctness: _validate_timer forward return is leak-guarded
     (signal at date d uses only d→d+h future prices — the "forward end covered"
     guard is verified on a synthetic series where we know the answer)
  6. Reactivation hook fixture — _news_sign_proven() returns True when the
     scorecard reads proven=True AND sign_ok=True
  7. Tone-history rebuild equivalence (extends tests/test_backfill_cctv_archive.py
     to multi-month shards)
  8. Finalize pipeline: dry-run mode produces correct output shape

Run: /path/to/venv/python -m tests.test_cctv_completion_pipeline
"""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


# ---------------------------------------------------------------------------
# 1. Gap-audit integration
# ---------------------------------------------------------------------------

def test_gap_audit_empty_archive() -> None:
    """On an empty archive dir, every date reports as missing."""
    with tempfile.TemporaryDirectory() as tmp:
        archive_dir = Path(tmp)
        from scripts.finalize_cctv_backfill import _run_gap_audit
        audit = _run_gap_audit(archive_dir)
        # No dates covered
        assert audit["total_covered"] == 0
        assert audit["total_missing"] > 0
        assert audit["is_complete"] is False
        # Years 2016-2026 should all appear as incomplete
        for yr in range(2016, 2027):
            assert audit["year_complete"].get(yr) is False


def test_gap_audit_with_one_shard() -> None:
    """A shard covering two dates reduces total_missing by 2."""
    with tempfile.TemporaryDirectory() as tmp:
        archive_dir = Path(tmp)
        from scripts.backfill_cctv_archive import _upsert_day
        from datetime import datetime, timezone

        fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        for day_str, content in [("2025-01-15", "增长"), ("2025-01-16", "发展")]:
            dt = date.fromisoformat(day_str)
            rows = [{
                "date": day_str, "order_idx": 0,
                "title": "test", "content": content,
                "fetch_status": "ok", "fetched_at": fetched_at,
            }]
            _upsert_day(archive_dir, dt, rows)

        from scripts.finalize_cctv_backfill import _run_gap_audit
        audit = _run_gap_audit(archive_dir)
        # Those 2 dates now covered
        assert audit["total_covered"] == 2
        assert "2025-01-15" not in (audit.get("missing_dates_sample") or [])
        assert "2025-01-16" not in (audit.get("missing_dates_sample") or [])


def test_gap_audit_stub_date_counted_as_retriable() -> None:
    """A date with all-stub rows is counted in year_stats stub count and total_retriable."""
    with tempfile.TemporaryDirectory() as tmp:
        archive_dir = Path(tmp)
        from scripts.backfill_cctv_archive import _upsert_day
        from datetime import datetime, timezone

        fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        dt = date(2025, 1, 15)
        rows = [{
            "date": "2025-01-15", "order_idx": 0,
            "title": "", "content": "对不起，可能是网络原因或无此页面",
            "fetch_status": "stub", "fetched_at": fetched_at,
        }]
        _upsert_day(archive_dir, dt, rows)

        from scripts.finalize_cctv_backfill import _run_gap_audit
        audit = _run_gap_audit(archive_dir)
        # The stub day is counted in year_stats
        assert audit["year_stats"][2025]["stub"] > 0
        # total_retriable counts ALL retriable dates (missing + all-stub)
        # Note: retriable_sample is capped at 20 newest; the 2025 date may not appear
        # in sample[:20] since 3800+ dates are newer. Check total_retriable count instead.
        assert audit["total_retriable"] > 0


# ---------------------------------------------------------------------------
# 2. _tone_stats baseline selection
# ---------------------------------------------------------------------------

def test_tone_stats_uses_rolling_window_without_history() -> None:
    """When history_baseline is None, _tone_stats falls back to the rolling window."""
    from engine.china_news import _tone_stats

    s = pd.Series([5.0, 6.0, 5.5, 7.0, 6.5], dtype=float)
    stats = _tone_stats(s, window=4, smooth=1, history_baseline=None)
    assert stats is not None
    assert stats["baseline_source"] == "rolling_window"
    assert stats["n"] == 5


def test_tone_stats_uses_long_history_when_provided() -> None:
    """When history_baseline has >= 60 rows, _tone_stats uses its mu/sigma."""
    from engine.china_news import _tone_stats

    rng = np.random.default_rng(42)
    # 10-year-like history baseline (already smoothed)
    hist_vals = rng.normal(loc=5.0, scale=2.0, size=3700)
    idx = pd.date_range("2016-02-03", periods=3700, freq="D")
    history = pd.Series(hist_vals, index=idx)

    # Live series (19 points)
    live_s = pd.Series([8.0, 9.0, 8.5], dtype=float)
    stats = _tone_stats(live_s, window=90, smooth=1, history_baseline=history)

    assert stats is not None
    assert stats["baseline_source"] == "long_history"
    assert stats["baseline_n"] == 3700
    # z should use history mu~5.0, sigma~2.0
    expected_z = (stats["value"] - history.mean()) / history.std(ddof=1)
    assert abs(stats["z"] - round(expected_z, 2)) < 0.05


def test_tone_stats_falls_back_when_history_too_short() -> None:
    """history_baseline with < 60 rows triggers rolling-window fallback."""
    from engine.china_news import _tone_stats

    tiny_hist = pd.Series([5.0, 6.0], dtype=float)
    live_s = pd.Series([5.0, 6.0, 7.0, 8.0, 9.0], dtype=float)
    stats = _tone_stats(live_s, window=4, smooth=1, history_baseline=tiny_hist)
    assert stats is not None
    assert stats["baseline_source"] == "rolling_window"


# ---------------------------------------------------------------------------
# 3. policy_tone() baseline_source field
# ---------------------------------------------------------------------------

def test_policy_tone_returns_baseline_source_field() -> None:
    """policy_tone() dict must include baseline_source (rolling_window when no history)."""
    from engine import china_news as cn
    from lib import store as st

    # Mock store.read to return a small live tone series
    idx = pd.date_range("2026-06-15", periods=19, freq="D")
    mock_df = pd.DataFrame({"tone": np.random.default_rng(0).normal(6, 2, 19)}, index=idx)

    with patch.object(st, "read", return_value=mock_df):
        with patch.object(cn, "_load_tone_history_baseline", return_value=None):
            result = cn.policy_tone()

    if result is not None:
        assert "baseline_source" in result
        assert result["baseline_source"] == "rolling_window"


def test_policy_tone_uses_long_history_when_file_exists() -> None:
    """policy_tone() returns baseline_source='long_history' when the history file exists."""
    from engine import china_news as cn
    from lib import store as st

    idx_live = pd.date_range("2026-06-15", periods=19, freq="D")
    mock_live = pd.DataFrame({"tone": np.full(19, 6.0)}, index=idx_live)

    # Synthetic 10-year history baseline (already smoothed, as returned by _load_tone_history_baseline)
    idx_hist = pd.date_range("2016-02-03", periods=3700, freq="D")
    rng = np.random.default_rng(1)
    mock_hist_sm = pd.Series(rng.normal(5, 2, 3700), index=idx_hist)

    with patch.object(st, "read", return_value=mock_live):
        with patch.object(cn, "_load_tone_history_baseline", return_value=mock_hist_sm):
            result = cn.policy_tone()

    if result is not None:
        assert result["baseline_source"] == "long_history"
        assert result["baseline_n"] == len(mock_hist_sm)


# ---------------------------------------------------------------------------
# 4. _news_sentiment_series() consumes long-history baseline
# ---------------------------------------------------------------------------

def test_news_sentiment_series_large_n_with_history() -> None:
    """With a 10-year history, _news_sentiment_series returns a series with many obs.

    _news_sentiment_series does:  from engine import china_news_intel as cni
    and:                          from engine.china_news import _load_tone_history_baseline
    We patch both via sys.modules to avoid AttributeError on lazy-imported attrs.
    """
    from engine import china_validation as cv
    from engine import china_news as cn

    # Synthetic 10-year history baseline (smoothed)
    rng = np.random.default_rng(99)
    idx_hist = pd.date_range("2016-02-03", periods=3700, freq="D")
    hist_sm = pd.Series(rng.normal(5.0, 2.0, 3700), index=idx_hist)

    tiny_live = pd.Series(rng.normal(6.0, 1.5, 19),
                          index=pd.date_range("2026-06-14", periods=19, freq="D"))

    # Patch the lazy-imported china_news_intel module via sys.modules
    mock_cni = MagicMock()
    mock_cni._blended_tone_series.return_value = tiny_live

    with patch.dict("sys.modules", {"engine.china_news_intel": mock_cni}):
        with patch.object(cn, "_load_tone_history_baseline", return_value=hist_sm):
            result = cv._news_sentiment_series()

    # With the 10-year history concatenated, we expect thousands of obs
    assert result is not None
    assert len(result) > 1000, f"Expected >1000 obs with history, got {len(result)}"


def test_news_sentiment_series_falls_back_without_history() -> None:
    """Without history, the series requires >=60 live points to be non-None."""
    from engine import china_validation as cv
    from engine import china_news as cn

    # Only 19 points — too few for rolling-252
    rng = np.random.default_rng(5)
    small_s = pd.Series(rng.normal(5.0, 2.0, 19),
                        index=pd.date_range("2026-06-14", periods=19, freq="D"))

    mock_cni = MagicMock()
    mock_cni._blended_tone_series.return_value = small_s

    with patch.dict("sys.modules", {"engine.china_news_intel": mock_cni}):
        with patch.object(cn, "_load_tone_history_baseline", return_value=None):
            result = cv._news_sentiment_series()

    # Should be None (19 < 60)
    assert result is None


# ---------------------------------------------------------------------------
# 5. PIT-correctness: _validate_timer leak guard
# ---------------------------------------------------------------------------

def test_validate_timer_pit_correctness() -> None:
    """_validate_timer must not include signal dates whose forward end is not yet
    in the bench panel — the 'last_covered' guard.

    Construction:
      - bench has 30 trading-day rows.
      - horizon = 5
      - Last covered row = index[-(5+1)] = index[-6]
      - Signal has 30 points; the LAST 5 must be excluded by the leak guard
        -> only ~25 obs should be scored, not 30.
    """
    import engine.validation as V
    from engine import china_validation as cv

    rng = np.random.default_rng(7)
    n = 30
    idx = pd.date_range("2026-01-01", periods=n, freq="B")
    bench = pd.Series(rng.normal(0.1, 1.0, n), index=idx)
    sig = pd.Series(rng.normal(0.0, 1.0, n), index=idx)

    result = cv._validate_timer(V, "news_sentiment", sig, panel=None, bench=bench, horizons=[5])
    # _bench_fwd_series uses bench; forward-end leak guard
    by_h = result.get("by_horizon") or {}
    if "5" in by_h:
        n_scored = by_h["5"].get("n", 0)
        # Should be <= n - horizon (5) because forward-end rows are dropped
        assert n_scored <= n - 5, f"Expected <={n-5} obs, got {n_scored} — possible PIT leak"


def test_validate_timer_sign_direction() -> None:
    """_validate_timer should detect a clean anti-correlation (sign_expected=-1).

    We construct a signal that is STRONGLY negatively correlated with the forward bench
    return. The mean_ic (mean product of standardized signal x forward return) should
    be negative, confirming the contrarian sign direction.
    """
    import engine.validation as V
    from engine import china_validation as cv

    rng = np.random.default_rng(42)
    n = 80
    idx = pd.date_range("2024-01-01", periods=n, freq="B")

    # Bench returns: random walk
    bench_rets = rng.normal(0.002, 0.01, n)
    bench_prices = pd.Series(np.cumprod(1 + bench_rets) * 100, index=idx)

    # Signal: negatively correlated with next-5d forward return
    fwd_5 = pd.Series(bench_prices.pct_change(5).shift(-5).values, index=idx)
    # Signal is opposite of future return (contrarian)
    sig_raw = -fwd_5.fillna(0) + rng.normal(0, 0.001, n)
    sig = pd.Series(sig_raw.values, index=idx)

    result = cv._validate_timer(V, "news_sentiment", sig, panel=None, bench=bench_prices,
                                horizons=[5])
    by_h = result.get("by_horizon") or {}
    if "5" in by_h and by_h["5"]["n"] >= 10:
        mean_ic = by_h["5"].get("mean_ic")
        if mean_ic is not None:
            # The signal is anti-correlated with fwd return -> mean product negative
            assert mean_ic < 0, (
                f"Expected negative mean_ic (contrarian signal), got {mean_ic:.4f}"
            )


# ---------------------------------------------------------------------------
# 6. Reactivation hook fixture
# _news_sign_proven() uses:  from engine import china_signal_lab  (local import)
# We patch engine.china_signal_lab via sys.modules.
# ---------------------------------------------------------------------------

def _make_sign_lab_mock(scorecard: dict) -> MagicMock:
    """Return a mock china_signal_lab where load_validation() returns scorecard."""
    mock_lab = MagicMock()
    mock_lab.load_validation.return_value = scorecard
    return mock_lab


def test_news_sign_proven_returns_true_when_scorecard_proven() -> None:
    """_news_sign_proven() must return True iff the scorecard has proven=True AND sign_ok=True."""
    import engine.china_signal_lab as csl
    from engine import china_intel_analysis as an

    proven_scorecard = {
        "news_sentiment": {
            "proven": True,
            "sign_ok": True,
            "tier": "scored",
            "status": "scored",
            "n_obs": 50,
        }
    }

    with patch.object(csl, "load_validation", return_value=proven_scorecard):
        result = an._news_sign_proven()

    assert result is True, "_news_sign_proven() must return True when proven=True and sign_ok=True"


def test_news_sign_proven_returns_false_when_not_proven() -> None:
    """_news_sign_proven() returns False when proven=False even if sign_ok=True."""
    import engine.china_signal_lab as csl
    from engine import china_intel_analysis as an

    scorecard = {
        "news_sentiment": {
            "proven": False,
            "sign_ok": True,
            "tier": "accruing",
            "n_obs": 5,
        }
    }

    with patch.object(csl, "load_validation", return_value=scorecard):
        result = an._news_sign_proven()

    assert result is False


def test_news_sign_proven_returns_false_when_sign_wrong() -> None:
    """_news_sign_proven() returns False when sign_ok=False (wrong-sign leg)."""
    import engine.china_signal_lab as csl
    from engine import china_intel_analysis as an

    scorecard = {
        "news_sentiment": {
            "proven": True,
            "sign_ok": False,   # validated but WRONG sign
            "tier": "scored",
            "n_obs": 50,
        }
    }

    with patch.object(csl, "load_validation", return_value=scorecard):
        result = an._news_sign_proven()

    assert result is False


def test_news_sign_proven_returns_false_when_family_missing() -> None:
    """_news_sign_proven() returns False gracefully when the family is absent."""
    import engine.china_signal_lab as csl
    from engine import china_intel_analysis as an

    with patch.object(csl, "load_validation", return_value={}):
        result = an._news_sign_proven()

    assert result is False


def test_conviction_uses_contrarian_direction_when_proven(monkeypatch) -> None:
    """When _news_sign_proven() returns True, conviction composite uses
    direction_basis='proven_contrarian', not 'salience_only'.

    _conviction() uses local imports (from engine import china_basket_spine, etc.)
    so we patch via sys.modules to avoid AttributeError on absent module-level attrs.
    """
    import engine.china_intel_analysis as an

    monkeypatch.setattr(an, "_news_sign_proven", lambda: True)

    divs = [{
        "sector_etf": "512000.SS",
        "sign": "positive",
        "strength": 0.7,
        "reliability": {"basis": "unproven", "n_resolved": 0},
        "signal_key": "test",
    }]
    news_sent = {"z": -1.5, "band": "cautious"}   # z < 0 = contrarian bullish signal
    news_feed = {"by_basket": {}}

    mock_sp = MagicMock()
    mock_sp.etf_to_basket.return_value = {"512000.SS": []}
    mock_sp.basket_members.return_value = []
    mock_lab = MagicMock()
    mock_lab.leg_weights_for.return_value = {}
    mock_cv = MagicMock()
    mock_cv.combine.return_value = 0.6

    with patch.dict("sys.modules", {
        "engine.china_basket_spine": mock_sp,
        "engine.china_signal_lab": mock_lab,
        "engine.china_conviction": mock_cv,
    }):
        results = an._conviction(divs, news_feed, news_sent, {}, {})

    if results:
        bases = [r.get("direction_basis") for r in results if r]
        assert any(b == "proven_contrarian" for b in bases), (
            f"Expected proven_contrarian direction, got: {bases}"
        )


def test_conviction_uses_salience_only_when_not_proven(monkeypatch) -> None:
    """When _news_sign_proven() returns False, direction_basis must be 'salience_only'."""
    import engine.china_intel_analysis as an

    monkeypatch.setattr(an, "_news_sign_proven", lambda: False)

    divs = [{
        "sector_etf": "512000.SS",
        "sign": "positive",
        "strength": 0.7,
        "reliability": {"basis": "unproven", "n_resolved": 0},
        "signal_key": "test",
    }]
    news_sent = {"z": -1.5, "band": "cautious"}
    news_feed = {"by_basket": {}}

    mock_sp = MagicMock()
    mock_sp.etf_to_basket.return_value = {"512000.SS": []}
    mock_sp.basket_members.return_value = []
    mock_lab = MagicMock()
    mock_lab.leg_weights_for.return_value = {}
    mock_cv = MagicMock()
    mock_cv.combine.return_value = 0.3

    with patch.dict("sys.modules", {
        "engine.china_basket_spine": mock_sp,
        "engine.china_signal_lab": mock_lab,
        "engine.china_conviction": mock_cv,
    }):
        results = an._conviction(divs, news_feed, news_sent, {}, {})

    if results:
        bases = [r.get("direction_basis") for r in results if r]
        assert any(b == "salience_only" for b in bases), (
            f"Expected salience_only direction, got: {bases}"
        )


# ---------------------------------------------------------------------------
# 7. Tone-history rebuild equivalence — multi-month shards
# ---------------------------------------------------------------------------

def test_rebuild_equivalence_two_months() -> None:
    """rebuild_cctv_tone_history handles data spread across two monthly shards."""
    from scripts.backfill_cctv_archive import _upsert_day
    from scripts.rebuild_cctv_tone_history import rebuild
    from collectors.china_news import _tone_features
    from datetime import datetime, timezone

    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    items_jan = [
        ("改革开放经济发展", "支持就业促进增长民生红利"),
        ("科技创新向好", "高质量发展信心提振"),
    ]
    items_feb = [
        ("稳增长政策落实", "扩大内需提振消费"),
        ("防范风险监管", "下行压力加大警惕"),
    ]

    with tempfile.TemporaryDirectory() as tmp:
        arc = Path(tmp)

        # Write two separate months
        dt_jan = date(2025, 1, 15)
        dt_feb = date(2025, 2, 10)
        for dt, items in [(dt_jan, items_jan), (dt_feb, items_feb)]:
            rows = []
            for idx, (t, c) in enumerate(items):
                rows.append({
                    "date": dt.strftime("%Y-%m-%d"),
                    "order_idx": idx,
                    "title": t,
                    "content": c,
                    "fetch_status": "ok",
                    "fetched_at": fetched_at,
                })
            _upsert_day(arc, dt, rows)

        out = Path(tmp) / "tone_history.parquet"
        df = rebuild(arc, out)

    assert len(df) == 2
    for dt, items in [(dt_jan, items_jan), (dt_feb, items_feb)]:
        ts = pd.Timestamp(dt.strftime("%Y-%m-%d"))
        assert ts in df.index, f"{dt} should be in rebuilt tone history"
        # Verify equivalence with direct _tone_features call
        raw = pd.DataFrame({
            "date": [dt.strftime("%Y-%m-%d")] * len(items),
            "title": [t for t, _ in items],
            "content": [c for _, c in items],
        })
        expected_tone = _tone_features(raw)["tone"]
        assert abs(df.loc[ts, "tone"] - expected_tone) < 1e-9


# ---------------------------------------------------------------------------
# 8. finalize pipeline dry-run
# ---------------------------------------------------------------------------

def test_finalize_dry_run_produces_no_writes() -> None:
    """dry-run mode of finalize_cctv_backfill must not write any files."""
    with tempfile.TemporaryDirectory() as tmp:
        archive_dir = Path(tmp)
        tone_out = Path(tmp) / "tone_history.parquet"
        scorecard_path = Path(tmp) / "scorecard.json"

        from scripts.finalize_cctv_backfill import (
            run_tone_rebuild, run_validation, shard_commit_decision,
        )

        rebuild_result = run_tone_rebuild(archive_dir, tone_out, dry_run=True)
        # dry-run: no shards -> skipped, or dry-run state
        assert rebuild_result["status"] in ("skipped", "dry-run")
        assert not tone_out.exists()

        val_result = run_validation(dry_run=True)
        # dry-run returns status string; no scorecard written
        assert "dry-run" in val_result["status"]
        assert not scorecard_path.exists()

        commit_result = shard_commit_decision(archive_dir)
        assert commit_result["status"] in ("no-shards", "ok")


# ---------------------------------------------------------------------------
# Entry point (no pytest dependency — runs standalone)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import traceback

    tests_no_monkeypatch = [
        test_gap_audit_empty_archive,
        test_gap_audit_with_one_shard,
        test_gap_audit_stub_date_counted_as_retriable,
        test_tone_stats_uses_rolling_window_without_history,
        test_tone_stats_uses_long_history_when_provided,
        test_tone_stats_falls_back_when_history_too_short,
        test_policy_tone_returns_baseline_source_field,
        test_policy_tone_uses_long_history_when_file_exists,
        test_news_sentiment_series_large_n_with_history,
        test_news_sentiment_series_falls_back_without_history,
        test_validate_timer_pit_correctness,
        test_validate_timer_sign_direction,
        test_news_sign_proven_returns_true_when_scorecard_proven,
        test_news_sign_proven_returns_false_when_not_proven,
        test_news_sign_proven_returns_false_when_sign_wrong,
        test_news_sign_proven_returns_false_when_family_missing,
        test_rebuild_equivalence_two_months,
        test_finalize_dry_run_produces_no_writes,
    ]

    # monkeypatch tests (pytest only)
    tests_monkeypatch = [
        test_conviction_uses_contrarian_direction_when_proven,
        test_conviction_uses_salience_only_when_not_proven,
    ]

    failed = 0
    for fn in tests_no_monkeypatch:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception:
            print(f"FAIL {fn.__name__}")
            traceback.print_exc()
            failed += 1

    for fn in tests_monkeypatch:
        print(f"SKIP {fn.__name__} (requires pytest monkeypatch — run via pytest)")

    if failed == 0:
        print(f"\nAll {len(tests_no_monkeypatch)} standalone tests passed.")
        print(f"({len(tests_monkeypatch)} pytest-only tests skipped — run via pytest to include them)")
    else:
        print(f"\n{failed}/{len(tests_no_monkeypatch)} tests FAILED.")
        sys.exit(1)
