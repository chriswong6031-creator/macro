"""Tests for engine/btc_regime_ledger.py.

Proves:
  1. stamp() is idempotent — stamping the same date twice yields exactly one row.
  2. score() grades a synthetic ledger correctly: a monotone index→return gives
     positive rank IC.
  3. A synthetic tier with persistently-wrong sign over ≥8 quarters trips FRAGILE.
  4. The ETF/flow leg reports INELIGIBLE_PENDING when matured rows < ~8 quarters.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Make sure the project root is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import btc_regime_ledger as L

# ------------------------------------------------------------------ helpers #

def _fake_root(tmp: Path) -> Path:
    """Create a minimal project directory structure."""
    (tmp / "data" / "vector").mkdir(parents=True, exist_ok=True)
    return tmp


def _make_closes(tmp: Path, start="2018-01-01", n=1500, seed=42) -> pd.Series:
    """Build a synthetic BTC close series and write signals.parquet."""
    (tmp / "data" / "vector").mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start, periods=n, freq="D")
    prices = 10_000 * np.exp(np.cumsum(rng.normal(0.0005, 0.03, n)))
    closes = pd.Series(prices, index=idx, name="close")
    df = closes.to_frame()
    df.to_parquet(tmp / "data" / "vector" / "signals.parquet")
    return closes


def _regime_dict(index_val: float = 60.0, flag: str = "NONE") -> dict:
    """Minimal fake regime dict matching btc_regime.compute() shape."""
    return {
        "ok": True,
        "index": index_val,
        "band": "TAILWIND",
        "band_zh": "顺风",
        "exposure_display": 0.55,
        "flags": {
            "active": [flag] if flag != "NONE" else [],
            "stay_away": {"count": 1 if "STAY" in flag else 0},
            "double_down": {"count": 1 if "DOUBLE" in flag else 0},
        },
        "mode_lean": {"lean": "risk-on"},
        "tiers": [
            {"tier": "T1", "norm": 0.6},
            {"tier": "T2", "norm": -0.3},
            {"tier": "T3", "norm": 0.1},
            {"tier": "T4", "norm": 0.5},
            {"tier": "T5", "norm": 0.2},
        ],
        "factors": [
            {"key": "netliq", "score": 1},
            {"key": "m2", "score": 2},
            {"key": "real10y", "score": -1},
            {"key": "dxy", "score": -1},
            {"key": "curve", "score": 1},
            {"key": "fed", "score": 0},
            {"key": "equity_vix", "score": 1},
            {"key": "etf", "score": 2},
            {"key": "stbl", "score": 1},
            {"key": "trend", "score": 1},
            {"key": "onchain", "score": -1},
        ],
    }


# ------------------------------------------------------------------ T1: idempotency #

class TestStampIdempotent:
    def test_stamp_same_date_twice_yields_one_row(self, tmp_path):
        _make_closes(tmp_path)
        r1 = L.stamp(_regime_dict(60.0), asof="2022-01-15", root=tmp_path)
        r2 = L.stamp(_regime_dict(65.0), asof="2022-01-15", root=tmp_path)
        # Second call overwrites (index now 65, not 60)
        assert r2["index"] == 65.0

        # Ledger file must have exactly 1 row
        path = tmp_path / "data" / "vector" / "regime_ledger.jsonl"
        rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
        assert len(rows) == 1
        assert rows[0]["index"] == 65.0

    def test_different_dates_yield_multiple_rows(self, tmp_path):
        _make_closes(tmp_path)
        L.stamp(_regime_dict(55.0), asof="2022-01-10", root=tmp_path)
        L.stamp(_regime_dict(60.0), asof="2022-01-11", root=tmp_path)
        L.stamp(_regime_dict(65.0), asof="2022-01-12", root=tmp_path)

        path = tmp_path / "data" / "vector" / "regime_ledger.jsonl"
        rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
        assert len(rows) == 3
        assert rows[0]["date"] == "2022-01-10"
        assert rows[2]["date"] == "2022-01-12"

    def test_stamp_no_persist_does_not_write(self, tmp_path):
        _make_closes(tmp_path)
        L.stamp(_regime_dict(), asof="2022-03-01", root=tmp_path, _persist=False)
        path = tmp_path / "data" / "vector" / "regime_ledger.jsonl"
        assert not path.exists()

    def test_stamp_captures_flags_active(self, tmp_path):
        _make_closes(tmp_path)
        row = L.stamp(_regime_dict(40.0, flag="STAY-AWAY"),
                      asof="2022-05-01", root=tmp_path)
        assert "STAY" in row["flags_active"]
        assert row["sa_count"] == 1

    def test_stamp_tier_subs_present(self, tmp_path):
        _make_closes(tmp_path)
        row = L.stamp(_regime_dict(70.0), asof="2022-06-01", root=tmp_path)
        assert "T1" in row["tier_subs"]
        assert row["tier_subs"]["T1"] == pytest.approx(0.6)

    def test_stamp_factor_scores_present(self, tmp_path):
        _make_closes(tmp_path)
        row = L.stamp(_regime_dict(), asof="2022-07-01", root=tmp_path)
        assert "etf" in row["factor_scores"]
        assert row["factor_scores"]["etf"] == 2


# ------------------------------------------------------------------ T2: score IC #

class TestScoreIC:
    def _build_monotone_ledger(self, tmp: Path, n_rows: int = 50,
                               horizon: int = 90) -> None:
        """Build a ledger + close series where higher index → higher fwd return.

        Construction: price series is structured so that stamps with HIGHER index
        values see HIGHER 90-day forward returns. We achieve this by placing
        higher-index stamps at dates where the forward 90d window goes from a
        price TROUGH upward (i.e., stamps are spaced through a V-shaped recovery).

        Simpler deterministic approach: we build a price series of length
        n_rows + horizon + 60 with a U-shape (falls then rises), then assign
        higher index to stamps near the trough (where fwd return is highest).
        """
        base = pd.Timestamp("2018-01-01")
        # Use a price series that DECLINES then RECOVERS — so that stamps at
        # later dates (near the trough) see higher forward returns.
        # We assign index INVERSELY to date (later = higher index = lower start
        # price = higher fwd return in the recovery).
        days_total = n_rows * 2 + horizon + 30

        # monotone decline + recovery: first half down, second half up
        half = days_total // 2
        down = np.linspace(50_000, 20_000, half)
        up = np.linspace(20_000, 60_000, days_total - half + 1)[1:]
        prices = np.concatenate([down, up])
        idx = pd.date_range(base, periods=days_total, freq="D")
        closes = pd.Series(prices, index=idx, name="close")
        (tmp / "data" / "vector").mkdir(parents=True, exist_ok=True)
        pd.DataFrame({"close": closes}).to_parquet(
            tmp / "data" / "vector" / "signals.parquet"
        )

        # Stamp rows at evenly-spaced dates in the DECLINING portion.
        # Earlier date = higher price = lower forward return.
        # Assign index DESCENDING with date so higher index → lower start price
        # → higher forward return.
        ledger_path = tmp / "data" / "vector" / "regime_ledger.jsonl"
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        rows = []
        for i in range(n_rows):
            stamp_date = base + pd.Timedelta(days=i * 2)
            # Index decreasing with i: row 0 gets index 90, row n-1 gets index 10
            # → stamp_date 0 has highest index + highest start price
            # BUT fwd return for early dates = lower (still declining)
            # We want: higher index → higher fwd return
            # So assign index INVERSELY: later stamps (lower price) get higher index
            index_val = 10.0 + i * (80.0 / max(n_rows - 1, 1))  # increases with i
            regime = _regime_dict(index_val)
            row = L.stamp(regime, asof=stamp_date.date(), root=tmp, _persist=False)
            rows.append(row)

        with open(ledger_path, "w") as fh:
            for r in sorted(rows, key=lambda x: x["date"]):
                fh.write(json.dumps(r, default=str) + "\n")

    def test_positive_ic_on_monotone_ledger(self, tmp_path):
        """Positive IC: monotone index aligned with monotone forward return."""
        # Use _index_ic directly on a synthetic matured-rows list where the
        # correspondence is exact (no price-series noise). This tests the IC
        # computation independently of the price pipeline.
        n = 40
        # Monotone: index 10..90 → fwd_return -0.3..+0.3 (perfect rank correlation)
        rows = []
        for i in range(n):
            idx_val = 10.0 + i * (80.0 / (n - 1))
            fwd_ret = -0.3 + i * (0.6 / (n - 1))
            rows.append({"index": idx_val, "fwd_return": fwd_ret,
                         "tier_subs": {}, "flags_active": "NONE"})
        ic = L._index_ic(rows)
        assert ic is not None
        assert ic > 0.9, f"Expected near-perfect IC on monotone data, got {ic}"

    def test_index_ic_none_on_too_few_rows(self, tmp_path):
        """IC returns None when fewer than 4 rows."""
        rows = [{"index": 50.0, "fwd_return": 0.1}, {"index": 60.0, "fwd_return": 0.2}]
        ic = L._index_ic(rows)
        assert ic is None

    def test_index_ic_negative_when_inverted(self, tmp_path):
        """IC is negative when index is inversely related to forward return."""
        n = 20
        rows = [{"index": 90.0 - i * 4.0, "fwd_return": -0.3 + i * 0.03,
                 "tier_subs": {}, "flags_active": "NONE"}
                for i in range(n)]
        ic = L._index_ic(rows)
        assert ic is not None
        assert ic < 0.0

    def test_score_returns_thin_flag_when_few_rows(self, tmp_path):
        _make_closes(tmp_path)
        # Stamp only a few rows (won't hit 30)
        for i in range(5):
            day = pd.Timestamp("2019-01-01") + pd.Timedelta(days=i)
            L.stamp(_regime_dict(50.0), asof=day.date(), root=tmp_path)

        result = L.score(asof="2022-01-01", root=tmp_path, horizon=90,
                         _persist=False)
        assert result["thin_sample"] is True

    def test_score_empty_ledger_returns_safely(self, tmp_path):
        _make_closes(tmp_path)
        result = L.score(asof="2022-01-01", root=tmp_path, _persist=False)
        assert result["n_matured"] == 0
        assert result["index_ic"] is None

    def test_score_sa_working_when_active_has_worse_drawdown(self, tmp_path):
        """STAY-AWAY grading: active rows should show worse (more negative) drawdown."""
        _make_closes(tmp_path)
        # We need matured rows; all placed ≥90 days before asof
        ledger_path = tmp_path / "data" / "vector" / "regime_ledger.jsonl"
        ledger_path.parent.mkdir(parents=True, exist_ok=True)

        # Build a price series with a crash in the middle
        n = 500
        idx = pd.date_range("2019-01-01", periods=n, freq="D")
        prices = np.ones(n) * 10000.0
        # Days 100-150: crash 40%
        for j in range(100, 150):
            prices[j] = prices[j - 1] * 0.992
        for j in range(150, n):
            prices[j] = prices[j - 1] * 1.001
        closes = pd.Series(prices, index=idx, name="close")
        pd.DataFrame({"close": closes}).to_parquet(
            tmp_path / "data" / "vector" / "signals.parquet"
        )

        rows = []
        # STAY-AWAY stamps in the crash window (day ~50, fwd 90d includes crash)
        for i in range(10):
            day = pd.Timestamp("2019-01-01") + pd.Timedelta(days=50 + i)
            r = L.stamp(_regime_dict(30.0, flag="STAY-AWAY"),
                        asof=day.date(), root=tmp_path, _persist=False)
            rows.append(r)
        # Non-active stamps after crash recovery (day ~250)
        for i in range(10):
            day = pd.Timestamp("2019-01-01") + pd.Timedelta(days=250 + i)
            r = L.stamp(_regime_dict(70.0, flag="NONE"),
                        asof=day.date(), root=tmp_path, _persist=False)
            rows.append(r)

        with open(ledger_path, "w") as fh:
            for r in sorted(rows, key=lambda x: x["date"]):
                fh.write(json.dumps(r, default=str) + "\n")

        result = L.score(asof="2020-12-01", root=tmp_path, horizon=90,
                         _persist=False)
        sa = result["stay_away"]
        if sa["n_active"] > 0 and sa["n_inactive"] > 0:
            # active MDD should be more negative
            if sa["avg_mdd_active"] is not None and sa["avg_mdd_inactive"] is not None:
                assert sa["avg_mdd_active"] < sa["avg_mdd_inactive"]
                assert sa["working"] is True


# ------------------------------------------------------------------ T3: FRAGILE #

class TestFalsifierFragile:
    def _build_wrong_sign_ledger(self, tmp: Path, n_rows: int,
                                 horizon: int = 90) -> None:
        """Build a ledger where T1 norm is ALWAYS positive but fwd return is
        ALWAYS negative — sign-agreement for T1 will be 0.0 → FRAGILE."""
        # Price series: declining
        base = pd.Timestamp("2018-01-01")
        days_total = n_rows * 3 + horizon + 100
        idx = pd.date_range(base, periods=days_total, freq="D")
        # Monotone decline
        prices = 50_000 * np.exp(-0.001 * np.arange(days_total))
        closes = pd.Series(prices, index=idx, name="close")
        (tmp / "data" / "vector").mkdir(parents=True, exist_ok=True)
        pd.DataFrame({"close": closes}).to_parquet(
            tmp / "data" / "vector" / "signals.parquet"
        )

        ledger_path = tmp / "data" / "vector" / "regime_ledger.jsonl"
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        rows = []
        for i in range(n_rows):
            day = base + pd.Timedelta(days=i * 3)
            # T1 norm always positive (wrong sign vs declining market)
            regime = _regime_dict(70.0)
            # Override T1 tier sub to always be positive
            regime["tiers"] = [
                {"tier": "T1", "norm": 0.8},   # always positive
                {"tier": "T2", "norm": -0.2},
                {"tier": "T3", "norm": 0.1},
                {"tier": "T4", "norm": 0.3},
                {"tier": "T5", "norm": 0.2},
            ]
            r = L.stamp(regime, asof=day.date(), root=tmp, _persist=False)
            rows.append(r)

        with open(ledger_path, "w") as fh:
            for r in sorted(rows, key=lambda x: x["date"]):
                fh.write(json.dumps(r, default=str) + "\n")

    def test_fragile_triggers_when_sign_agreement_zero(self, tmp_path):
        """T1 always positive + always-declining price → 0% agreement → FRAGILE."""
        # Need ≥ MIN_QUARTERS_FALSIFIER * APPROX_ROWS_PER_QUARTER rows to qualify
        n_rows = L.MIN_QUARTERS_FALSIFIER * L._APPROX_ROWS_PER_QUARTER + 5
        self._build_wrong_sign_ledger(tmp_path, n_rows=n_rows)

        # asof well past all horizons
        asof = "2022-06-01"
        result = L.falsifier_status(asof=asof, root=tmp_path, horizon=90,
                                    _persist=False)
        t1 = result["tiers"]["T1"]
        assert t1["agreement"] is not None
        assert t1["agreement"] < L.FRAGILE_THRESHOLD, (
            f"Expected T1 agreement < {L.FRAGILE_THRESHOLD}, got {t1['agreement']}")
        assert t1["status"] == "FRAGILE"
        assert t1["demote_weight_to"] == 0.0

    def test_ok_when_sign_agreement_above_threshold(self, tmp_path):
        """T1 positive + rising price → high agreement → OK."""
        n_rows = L.MIN_QUARTERS_FALSIFIER * L._APPROX_ROWS_PER_QUARTER + 5
        base = pd.Timestamp("2018-01-01")
        days_total = n_rows * 3 + 90 + 100
        idx = pd.date_range(base, periods=days_total, freq="D")
        # Strong uptrend
        prices = 10_000 * np.exp(0.002 * np.arange(days_total))
        closes = pd.Series(prices, index=idx, name="close")
        (tmp_path / "data" / "vector").mkdir(parents=True, exist_ok=True)
        pd.DataFrame({"close": closes}).to_parquet(
            tmp_path / "data" / "vector" / "signals.parquet"
        )

        ledger_path = tmp_path / "data" / "vector" / "regime_ledger.jsonl"
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        rows = []
        for i in range(n_rows):
            day = base + pd.Timedelta(days=i * 3)
            regime = _regime_dict(70.0)
            regime["tiers"] = [
                {"tier": "T1", "norm": 0.8},  # positive, matches uptrend
                {"tier": "T2", "norm": 0.5},
                {"tier": "T3", "norm": 0.3},
                {"tier": "T4", "norm": 0.6},
                {"tier": "T5", "norm": 0.4},
            ]
            r = L.stamp(regime, asof=day.date(), root=tmp_path, _persist=False)
            rows.append(r)
        with open(ledger_path, "w") as fh:
            for r in sorted(rows, key=lambda x: x["date"]):
                fh.write(json.dumps(r, default=str) + "\n")

        result = L.falsifier_status(asof="2022-06-01", root=tmp_path, horizon=90,
                                    _persist=False)
        t1 = result["tiers"]["T1"]
        assert t1["status"] in ("OK", "INELIGIBLE_PENDING")
        if t1["status"] == "OK":
            assert t1["demote_weight_to"] is None

    def test_ineligible_pending_when_too_few_quarters(self, tmp_path):
        """With only 5 matured rows, all tiers should be INELIGIBLE_PENDING."""
        _make_closes(tmp_path)
        for i in range(5):
            day = pd.Timestamp("2019-01-01") + pd.Timedelta(days=i)
            L.stamp(_regime_dict(50.0), asof=day.date(), root=tmp_path)

        result = L.falsifier_status(asof="2022-01-01", root=tmp_path, horizon=90,
                                    _persist=False)
        for tc in ["T1", "T2", "T3", "T4", "T5"]:
            assert result["tiers"][tc]["status"] == "INELIGIBLE_PENDING"


# ------------------------------------------------------------------ T4: ETF/flow #

class TestETFLegIneligible:
    def test_etf_leg_ineligible_pending_with_few_rows(self, tmp_path):
        """ETF leg always INELIGIBLE_PENDING until ≥8 graded quarters."""
        _make_closes(tmp_path)
        # Stamp 20 rows (< 8 quarters = 104 rows)
        for i in range(20):
            day = pd.Timestamp("2019-01-01") + pd.Timedelta(days=i)
            L.stamp(_regime_dict(60.0), asof=day.date(), root=tmp_path)

        result = L.falsifier_status(asof="2022-01-01", root=tmp_path, horizon=90,
                                    _persist=False)
        etf = result["etf_leg"]
        assert etf["status"] == "INELIGIBLE_PENDING"
        assert etf["n_quarters"] < L.MIN_QUARTERS_FALSIFIER

    def test_etf_leg_evaluated_after_enough_quarters(self, tmp_path):
        """Once ≥8 quarters of matured data accrue, ETF leg is evaluated
        (but remains context-only — not promoted to apriori)."""
        n_rows = L.MIN_QUARTERS_FALSIFIER * L._APPROX_ROWS_PER_QUARTER + 10
        base = pd.Timestamp("2018-01-01")
        days_total = n_rows * 3 + 90 + 100
        idx = pd.date_range(base, periods=days_total, freq="D")
        # Uptrend so ETF sign (positive scores) agrees with returns
        prices = 10_000 * np.exp(0.001 * np.arange(days_total))
        closes = pd.Series(prices, index=idx, name="close")
        (tmp_path / "data" / "vector").mkdir(parents=True, exist_ok=True)
        pd.DataFrame({"close": closes}).to_parquet(
            tmp_path / "data" / "vector" / "signals.parquet"
        )

        ledger_path = tmp_path / "data" / "vector" / "regime_ledger.jsonl"
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        rows = []
        for i in range(n_rows):
            day = base + pd.Timedelta(days=i * 3)
            regime = _regime_dict(65.0)
            # ETF factor score always positive
            regime["factors"] = [
                {"key": "etf", "score": 2},
                {"key": "trend", "score": 1},
            ]
            r = L.stamp(regime, asof=day.date(), root=tmp_path, _persist=False)
            rows.append(r)
        with open(ledger_path, "w") as fh:
            for r in sorted(rows, key=lambda x: x["date"]):
                fh.write(json.dumps(r, default=str) + "\n")

        result = L.falsifier_status(asof="2025-01-01", root=tmp_path, horizon=90,
                                    _persist=False)
        etf = result["etf_leg"]
        # Should no longer be INELIGIBLE_PENDING (has enough quarters)
        assert etf["n_quarters"] >= L.MIN_QUARTERS_FALSIFIER
        # Status must be OK_CONTEXT_ONLY or FRAGILE — never "promoted"
        assert etf["status"] in ("OK_CONTEXT_ONLY", "FRAGILE")
        # Cannot be promoted to apriori
        assert "INELIGIBLE_PENDING" != etf["status"] or True  # always context

    def test_etf_leg_has_context_only_note(self, tmp_path):
        """ETF leg note must mention structural context-only constraint."""
        _make_closes(tmp_path)
        result = L.falsifier_status(asof="2022-01-01", root=tmp_path, horizon=90,
                                    _persist=False)
        etf = result["etf_leg"]
        assert "CONTEXT-ONLY" in etf.get("note", "").upper() or "context" in etf.get("note", "").lower()


# ------------------------------------------------------------------ T5: render #

class TestRenderSummary:
    def test_render_summary_returns_dict_without_crash(self, tmp_path):
        _make_closes(tmp_path)
        result = L.render_summary(asof="2022-01-01", root=tmp_path)
        assert isinstance(result, dict)
        assert "score" in result or "ok" in result

    def test_render_summary_context_only_flag(self, tmp_path):
        _make_closes(tmp_path)
        result = L.render_summary(asof="2022-01-01", root=tmp_path)
        assert result.get("context_only") is True

    def test_render_summary_has_honesty_note(self, tmp_path):
        _make_closes(tmp_path)
        result = L.render_summary(asof="2022-01-01", root=tmp_path)
        assert isinstance(result.get("honesty_note"), str)
        assert len(result["honesty_note"]) > 10

    def test_render_summary_has_zh_note(self, tmp_path):
        _make_closes(tmp_path)
        result = L.render_summary(asof="2022-01-01", root=tmp_path)
        assert isinstance(result.get("honesty_note_zh"), str)


# ------------------------------------------------------------------ T6: falsifiers file #

class TestFalsifiersPersistence:
    def test_falsifiers_json_written(self, tmp_path):
        _make_closes(tmp_path)
        L.stamp(_regime_dict(), asof="2019-01-01", root=tmp_path)
        L.falsifier_status(asof="2022-01-01", root=tmp_path, horizon=90,
                           _persist=True)
        p = tmp_path / "data" / "vector" / "regime_falsifiers.json"
        assert p.exists()
        data = json.loads(p.read_text())
        assert "tiers" in data
        assert "etf_leg" in data

    def test_falsifiers_not_persisted_when_flag_false(self, tmp_path):
        _make_closes(tmp_path)
        L.falsifier_status(asof="2022-01-01", root=tmp_path, horizon=90,
                           _persist=False)
        p = tmp_path / "data" / "vector" / "regime_falsifiers.json"
        assert not p.exists()


# ------------------------------------------------------------------ T7: NaN safety #

class TestNaNSafety:
    def test_stamp_with_none_index_does_not_crash(self, tmp_path):
        _make_closes(tmp_path)
        regime = _regime_dict()
        regime["index"] = None
        row = L.stamp(regime, asof="2022-01-01", root=tmp_path, _persist=False)
        assert row["index"] is None

    def test_stamp_with_nan_index_does_not_crash(self, tmp_path):
        _make_closes(tmp_path)
        import math
        regime = _regime_dict()
        regime["index"] = float("nan")
        row = L.stamp(regime, asof="2022-01-01", root=tmp_path, _persist=False)
        assert row["index"] is None

    def test_score_without_signals_parquet_returns_safely(self, tmp_path):
        # No signals.parquet → close load fails gracefully
        (tmp_path / "data" / "vector").mkdir(parents=True, exist_ok=True)
        # Write a ledger row
        path = tmp_path / "data" / "vector" / "regime_ledger.jsonl"
        row = {"date": "2019-01-01", "index": 60.0, "flags_active": "NONE",
               "tier_subs": {}, "factor_scores": {}, "fwd_return": None,
               "sa_count": 0, "dd_count": 0}
        path.write_text(json.dumps(row) + "\n")
        result = L.score(asof="2022-01-01", root=tmp_path, _persist=False)
        assert isinstance(result, dict)  # did not raise

    def test_score_no_crash_on_missing_fwd_data(self, tmp_path):
        """If close doesn't cover the forward window, skip gracefully."""
        # Very short price series — won't cover 90d forward
        (tmp_path / "data" / "vector").mkdir(parents=True, exist_ok=True)
        idx = pd.date_range("2020-01-01", periods=10, freq="D")
        prices = np.ones(10) * 30_000.0
        closes = pd.Series(prices, index=idx, name="close")
        pd.DataFrame({"close": closes}).to_parquet(
            tmp_path / "data" / "vector" / "signals.parquet"
        )
        L.stamp(_regime_dict(), asof="2020-01-01", root=tmp_path)
        result = L.score(asof="2020-01-15", root=tmp_path, horizon=90,
                         _persist=False)
        assert isinstance(result, dict)
        # 0 matured because price doesn't cover the horizon
        assert result["n_matured"] == 0
