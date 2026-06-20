"""Tests for engine/theme_catalyst_binder.py.

Primary tests use SYNTHETIC in-memory frames so the math is deterministic and the
test suite requires zero live data. One live-data smoke test (guarded with pytest.skip)
calls theme_catalyst(region='us') against the real nightly store if available.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from engine.theme_catalyst_binder import (
    IMMINENT_DAYS,
    RECENT_WINDOW_DAYS,
    RS_MIN_HISTORY,
    RS_WINDOW_D,
    STRONG_BEAT_PCT,
    _basket_leader,
    _earnings_record,
    _load_brief_catalysts,
    _neutral,
    _parse_reported_date,
    theme_catalyst,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _make_closes(tickers, n=100, seed=42):
    """Return a synthetic close DataFrame with n rows, random-walk prices."""
    import numpy as np
    rng = np.random.default_rng(seed)
    prices = 100 * (1 + rng.normal(0, 0.01, size=(n, len(tickers)))).cumprod(axis=0)
    idx = pd.date_range("2025-01-01", periods=n, freq="B")
    return pd.DataFrame(prices, index=idx, columns=tickers)


def _make_bench(n=100, seed=0):
    import numpy as np
    rng = np.random.default_rng(seed)
    prices = 100 * (1 + rng.normal(0, 0.008, size=n)).cumprod()
    idx = pd.date_range("2025-01-01", periods=n, freq="B")
    return pd.Series(prices, index=idx)


def _make_edf(rows: dict[str, dict]) -> pd.DataFrame:
    """rows = {ticker: {next_date, surprises_json}} — build a minimal earnings parquet."""
    records = []
    for t, v in rows.items():
        records.append({
            "ticker": t,
            "next_date": v.get("next_date", ""),
            "next_time": "",
            "eps_forecast": None,
            "surprises_json": json.dumps(v.get("surprises", [])),
            "as_of": date.today().isoformat(),
        })
    if not records:
        return pd.DataFrame(columns=["next_date", "next_time", "eps_forecast",
                                     "surprises_json", "as_of"])
    df = pd.DataFrame(records).set_index("ticker")
    return df


# ---------------------------------------------------------------------------
# _parse_reported_date
# ---------------------------------------------------------------------------
class TestParseReportedDate:
    def test_m_d_yyyy(self):
        d = _parse_reported_date("4/30/2026")
        assert d == date(2026, 4, 30)

    def test_iso(self):
        d = _parse_reported_date("2026-04-30")
        assert d == date(2026, 4, 30)

    def test_empty(self):
        assert _parse_reported_date("") is None

    def test_garbage(self):
        assert _parse_reported_date("not-a-date") is None

    def test_none(self):
        assert _parse_reported_date(None) is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# _neutral
# ---------------------------------------------------------------------------
class TestNeutral:
    def test_returns_typed_dict(self):
        r = _neutral("mag7")
        assert r["theme_id"] == "mag7"
        assert r["has_binding_catalyst"] is False
        assert r["kind"] == "none"
        assert r["confidence"] == "proxy"
        assert isinstance(r["brief_catalysts"], list)

    def test_never_raises(self):
        for tid in ("", "abc", "x" * 200):
            r = _neutral(tid)
            assert r["has_binding_catalyst"] is False


# ---------------------------------------------------------------------------
# _earnings_record — deterministic synthetic tests
# ---------------------------------------------------------------------------
class TestEarningsRecord:
    def _today(self):
        return date(2026, 6, 19)

    def test_no_edf_returns_neutral(self):
        er = _earnings_record(None, "AAPL", self._today())
        assert er["has_recent_print"] is False
        assert er["has_imminent_earnings"] is False

    def test_ticker_missing_returns_neutral(self):
        edf = _make_edf({"OTHER": {}})
        er = _earnings_record(edf, "MISSING", self._today())
        assert er["has_recent_print"] is False

    def test_recent_beat_detected(self):
        today = self._today()
        # reported 10 days ago — within RECENT_WINDOW_DAYS
        reported = (today - timedelta(days=10)).strftime("%-m/%-d/%Y")
        edf = _make_edf({"AAPL": {
            "surprises": [{"qtr": "Mar 2026", "reported": reported,
                           "eps": 2.0, "consensus": 1.8, "surprise_pct": 11.1}]
        }})
        er = _earnings_record(edf, "AAPL", today)
        assert er["has_recent_print"] is True
        assert er["recent_print_surprise_pct"] == 11.1
        assert er["strong_beat"] is True

    def test_old_beat_not_recent(self):
        today = self._today()
        # reported 60 days ago — outside RECENT_WINDOW_DAYS (45)
        reported = (today - timedelta(days=60)).strftime("%-m/%-d/%Y")
        edf = _make_edf({"AAPL": {
            "surprises": [{"qtr": "Dec 2025", "reported": reported,
                           "eps": 2.0, "consensus": 1.8, "surprise_pct": 11.1}]
        }})
        er = _earnings_record(edf, "AAPL", today)
        assert er["has_recent_print"] is False

    def test_miss_is_not_recent_print(self):
        today = self._today()
        reported = (today - timedelta(days=5)).strftime("%-m/%-d/%Y")
        edf = _make_edf({"AAPL": {
            "surprises": [{"qtr": "Mar 2026", "reported": reported,
                           "eps": 1.5, "consensus": 1.8, "surprise_pct": -16.7}]
        }})
        er = _earnings_record(edf, "AAPL", today)
        assert er["has_recent_print"] is False

    def test_imminent_earnings_detected(self):
        today = self._today()
        nd = (today + timedelta(days=10)).isoformat()  # 10 days away
        edf = _make_edf({"META": {"next_date": nd}})
        er = _earnings_record(edf, "META", today)
        assert er["has_imminent_earnings"] is True
        assert er["imminent_earnings_date"] == nd
        assert er["days_to_earnings"] == 10

    def test_distant_earnings_not_imminent(self):
        today = self._today()
        nd = (today + timedelta(days=40)).isoformat()  # 40 days away > IMMINENT_DAYS
        edf = _make_edf({"META": {"next_date": nd}})
        er = _earnings_record(edf, "META", today)
        assert er["has_imminent_earnings"] is False
        assert er["days_to_earnings"] == 40

    def test_small_beat_not_strong(self):
        today = self._today()
        reported = (today - timedelta(days=5)).strftime("%-m/%-d/%Y")
        edf = _make_edf({"KO": {
            "surprises": [{"qtr": "Mar 2026", "reported": reported,
                           "eps": 1.01, "consensus": 1.0, "surprise_pct": 1.0}]
        }})
        er = _earnings_record(edf, "KO", today)
        assert er["has_recent_print"] is True
        assert er["strong_beat"] is False  # 1.0 < STRONG_BEAT_PCT (5.0)

    def test_empty_surprises_json(self):
        edf = _make_edf({"XYZ": {}})
        er = _earnings_record(edf, "XYZ", self._today())
        assert er["has_recent_print"] is False
        assert er["surprises"] == []


# ---------------------------------------------------------------------------
# _basket_leader — deterministic synthetic tests
# ---------------------------------------------------------------------------
class TestBasketLeader:
    def test_picks_highest_rs(self):
        closes = _make_closes(["A", "B", "C"], n=120)
        bench = _make_bench(n=120)
        # Force A to have the highest RS: scale only the LAST RS_WINDOW_D rows so
        # the ratio v1/v0 is clearly higher than B/C and the benchmark.
        last_n = RS_WINDOW_D
        # Multiply the tail of A by a ramp: v0 stays anchored, v1 rises a lot.
        closes.iloc[-last_n:, closes.columns.get_loc("A")] *= 1.8
        members = [{"ticker": "A", "removed": None},
                   {"ticker": "B", "removed": None},
                   {"ticker": "C", "removed": None}]
        leader, rs = _basket_leader(members, closes, bench, today_i=119)
        assert leader is not None
        assert leader == "A"
        assert rs is not None

    def test_fallback_on_short_history(self):
        # Only 10 rows — below RS_MIN_HISTORY, should return first member with rs=None
        closes = _make_closes(["X", "Y"], n=10)
        bench = _make_bench(n=10)
        members = [{"ticker": "X", "removed": None}, {"ticker": "Y", "removed": None}]
        leader, rs = _basket_leader(members, closes, bench, today_i=9)
        assert leader == "X"
        assert rs is None

    def test_no_active_members(self):
        closes = _make_closes(["A"], n=100)
        bench = _make_bench(n=100)
        # ticker not in closes
        members = [{"ticker": "NOTHERE", "removed": None}]
        leader, rs = _basket_leader(members, closes, bench, today_i=99)
        assert leader is None
        assert rs is None

    def test_skips_removed_members(self):
        closes = _make_closes(["A", "B"], n=100)
        bench = _make_bench(n=100)
        # A is removed; B is active
        members = [{"ticker": "A", "removed": "2025-01-01"},
                   {"ticker": "B", "removed": None}]
        leader, _ = _basket_leader(members, closes, bench, today_i=99)
        assert leader == "B"

    def test_empty_members(self):
        closes = _make_closes(["A"], n=100)
        bench = _make_bench(n=100)
        leader, rs = _basket_leader([], closes, bench, today_i=99)
        assert leader is None
        assert rs is None


# ---------------------------------------------------------------------------
# _load_brief_catalysts — deterministic synthetic tests
# ---------------------------------------------------------------------------
class TestLoadBriefCatalysts:
    def test_loads_from_file(self, tmp_path):
        sb_dir = tmp_path / "site" / "stockbrief"
        sb_dir.mkdir(parents=True)
        brief = {"catalysts": ["Earnings next week", "Product launch"], "confidence": "low"}
        (sb_dir / "AAPL.json").write_text(json.dumps(brief))
        root = tmp_path
        cats = _load_brief_catalysts(root, "site", "AAPL")
        assert cats == ["Earnings next week", "Product launch"]

    def test_missing_file_returns_empty(self, tmp_path):
        cats = _load_brief_catalysts(tmp_path, "site", "MISSING")
        assert cats == []

    def test_handles_safe_name(self, tmp_path):
        # GC=F -> GC_F
        sb_dir = tmp_path / "site" / "stockbrief"
        sb_dir.mkdir(parents=True)
        (sb_dir / "GC_F.json").write_text(json.dumps({"catalysts": ["Futures roll"]}))
        cats = _load_brief_catalysts(tmp_path, "site", "GC=F")
        assert cats == ["Futures roll"]

    def test_caps_at_five(self, tmp_path):
        sb_dir = tmp_path / "site" / "stockbrief"
        sb_dir.mkdir(parents=True)
        brief = {"catalysts": [f"cat{i}" for i in range(10)]}
        (sb_dir / "XYZ.json").write_text(json.dumps(brief))
        cats = _load_brief_catalysts(tmp_path, "site", "XYZ")
        assert len(cats) == 5

    def test_malformed_json_returns_empty(self, tmp_path):
        sb_dir = tmp_path / "site" / "stockbrief"
        sb_dir.mkdir(parents=True)
        (sb_dir / "BAD.json").write_text("not json {{{")
        cats = _load_brief_catalysts(tmp_path, "site", "BAD")
        assert cats == []


# ---------------------------------------------------------------------------
# theme_catalyst integration test with fully mocked environment
# ---------------------------------------------------------------------------
class TestThemeCatalystIntegration:
    """Mock group_flow._setup + earnings parquet to test the full flow."""

    def _members_two(self, tickers):
        return [{"ticker": t, "added": "2023-01-01", "removed": None}
                for t in tickers]

    def _setup_mock(self, tickers, n=100):
        closes = _make_closes(tickers, n=n)
        bench = _make_bench(n=n)
        idx = closes.index
        # membership dict with two baskets
        mem = {
            "baskets": {
                "basket_a": {"name": "Basket A", "members": self._members_two(tickers[:2])},
                "basket_b": {"name": "Basket B", "members": self._members_two(tickers[2:])},
            }
        }
        return {"closes": closes, "bench": bench, "idx": idx, "mem": mem, "rets": closes.pct_change(), "region": "us"}

    def test_returns_dict_for_each_basket(self):
        tickers = ["A", "B", "C", "D"]
        setup = self._setup_mock(tickers)
        edf = _make_edf({})
        with patch("engine.theme_catalyst_binder.group_flow._setup", return_value=setup), \
             patch("engine.theme_catalyst_binder._load_earnings_parquet", return_value=edf), \
             patch("engine.theme_catalyst_binder._load_brief_catalysts", return_value=[]):
            result = theme_catalyst(region="us")
        assert "basket_a" in result
        assert "basket_b" in result
        for rid, rec in result.items():
            assert rec["confidence"] == "proxy"
            assert isinstance(rec["has_binding_catalyst"], bool)
            assert rec["kind"] in ("recent_beat", "imminent_earnings", "both", "none")

    def test_recent_beat_propagates(self):
        tickers = ["LEAD", "B"]
        setup = self._setup_mock(tickers)
        today = date.today()
        reported = (today - timedelta(days=5)).strftime("%-m/%-d/%Y")
        # LEAD has a big beat 5 days ago
        edf = _make_edf({"LEAD": {
            "surprises": [{"qtr": "Q1", "reported": reported,
                           "eps": 2.0, "consensus": 1.6, "surprise_pct": 25.0}]
        }, "B": {}})
        # Force LEAD to be the leader by scaling only the last RS_WINDOW_D rows
        closes = setup["closes"].copy()
        closes.iloc[-RS_WINDOW_D:, closes.columns.get_loc("LEAD")] *= 2.0
        setup["closes"] = closes
        with patch("engine.theme_catalyst_binder.group_flow._setup", return_value=setup), \
             patch("engine.theme_catalyst_binder._load_earnings_parquet", return_value=edf), \
             patch("engine.theme_catalyst_binder._load_brief_catalysts", return_value=[]):
            result = theme_catalyst(region="us")
        rec = result["basket_a"]
        assert rec["leader"] == "LEAD"
        assert rec["has_recent_print"] is True
        assert rec["strong_beat"] is True
        assert rec["has_binding_catalyst"] is True
        assert rec["kind"] in ("recent_beat", "both")

    def test_imminent_earnings_propagates(self):
        tickers = ["ALPHA", "BETA"]
        setup = self._setup_mock(tickers)
        today = date.today()
        nd = (today + timedelta(days=7)).isoformat()
        edf = _make_edf({"ALPHA": {"next_date": nd}, "BETA": {}})
        closes = setup["closes"].copy()
        closes.iloc[-RS_WINDOW_D:, closes.columns.get_loc("ALPHA")] *= 1.8
        setup["closes"] = closes
        with patch("engine.theme_catalyst_binder.group_flow._setup", return_value=setup), \
             patch("engine.theme_catalyst_binder._load_earnings_parquet", return_value=edf), \
             patch("engine.theme_catalyst_binder._load_brief_catalysts", return_value=[]):
            result = theme_catalyst(region="us")
        rec = result["basket_a"]
        assert rec["has_imminent_earnings"] is True
        assert rec["has_binding_catalyst"] is True
        assert rec["kind"] in ("imminent_earnings", "both")

    def test_no_catalyst_returns_none_kind(self):
        tickers = ["X", "Y"]
        setup = self._setup_mock(tickers)
        edf = _make_edf({"X": {}, "Y": {}})
        with patch("engine.theme_catalyst_binder.group_flow._setup", return_value=setup), \
             patch("engine.theme_catalyst_binder._load_earnings_parquet", return_value=edf), \
             patch("engine.theme_catalyst_binder._load_brief_catalysts", return_value=[]):
            result = theme_catalyst(region="us")
        assert result["basket_a"]["kind"] == "none"
        assert result["basket_a"]["has_binding_catalyst"] is False

    def test_unsupported_region_returns_empty(self):
        result = theme_catalyst(region="cn")
        assert result == {}

    def test_setup_failure_returns_empty(self):
        with patch("engine.theme_catalyst_binder.group_flow._setup",
                   side_effect=RuntimeError("no data")):
            result = theme_catalyst(region="us")
        assert result == {}

    def test_setup_none_returns_empty(self):
        with patch("engine.theme_catalyst_binder.group_flow._setup", return_value=None):
            result = theme_catalyst(region="us")
        assert result == {}

    def test_brief_catalysts_attached(self, tmp_path):
        tickers = ["NVDA", "AMD"]
        setup = self._setup_mock(tickers)
        edf = _make_edf({})
        # NVDA is the leader (higher closes in the RS tail) — brief has two catalysts
        closes = setup["closes"].copy()
        closes.iloc[-RS_WINDOW_D:, closes.columns.get_loc("NVDA")] *= 2.0
        setup["closes"] = closes
        with patch("engine.theme_catalyst_binder.group_flow._setup", return_value=setup), \
             patch("engine.theme_catalyst_binder._load_earnings_parquet", return_value=edf), \
             patch("engine.theme_catalyst_binder._load_brief_catalysts",
                   return_value=["Data-center ramp", "Blackwell launch"]):
            result = theme_catalyst(region="us")
        rec = result["basket_a"]
        assert rec["brief_catalysts"] == ["Data-center ramp", "Blackwell launch"]


# ---------------------------------------------------------------------------
# live-data smoke test (guarded)
# ---------------------------------------------------------------------------
@pytest.mark.live
def test_theme_catalyst_live_smoke():
    """Smoke test against the real nightly store. Skipped when data is absent."""
    from pathlib import Path
    from lib import config
    edf_path = config.ROOT / "data" / "earnings" / "earnings.parquet"
    mem_path = config.ROOT / "data" / "baskets" / "membership.json"
    if not edf_path.exists() or not mem_path.exists():
        pytest.skip("live earnings/membership data not available")
    try:
        from engine import group_flow
        s = group_flow._setup()
        if s is None or len(s["idx"]) < 60:
            pytest.skip("group_flow._setup returned None or too short")
    except Exception:
        pytest.skip("group_flow._setup failed")

    result = theme_catalyst(region="us")
    if not result:
        pytest.skip("theme_catalyst returned empty — no baskets in scope")

    # basic shape checks
    assert isinstance(result, dict)
    for tid, rec in result.items():
        assert rec["theme_id"] == tid
        assert rec["confidence"] == "proxy"
        assert isinstance(rec["has_binding_catalyst"], bool)
        assert rec["kind"] in ("recent_beat", "imminent_earnings", "both", "none")
        assert isinstance(rec["brief_catalysts"], list)
        assert "note" in rec
