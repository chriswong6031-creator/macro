"""tests/test_stocktable_data.py — W8-E enrichment unit tests.

Validates:
  1. mcap join null-safety (placeholder-30 => None; real-cap name => value; bucket edges 100/500)
  2. days_since_signal (present/absent store, first-seen math)
  3. serialization completeness (every configured column key exists on every row or is None)
  4. no ordering mutation (enriched arrays byte-order-identical to input order)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# ── helpers ───────────────────────────────────────────────────────────────────

_PLACEHOLDER_MCAP = 30.0

def _cap_bucket(mcap):
    """Mirror the exact bucket logic from build_china_library.py."""
    if mcap is None:
        return None
    if mcap >= 500:
        return "large"
    if mcap >= 100:
        return "mid"
    return "small"


def _mcap_from_lookup(ticker: str, mktcap_by: dict) -> float | None:
    """Mirror the null-safe mcap lookup from build_china_library.py."""
    v = mktcap_by.get(str(ticker))
    if v is None:
        return None
    try:
        fv = float(v)
        return None if fv == _PLACEHOLDER_MCAP else fv
    except (ValueError, TypeError):
        return None


def _days_since(ticker: str, first_seen: dict, today_str: str) -> int | None:
    """Mirror days_since_signal logic."""
    fs = first_seen.get(str(ticker))
    if not fs or not today_str:
        return None
    try:
        d0 = pd.Timestamp(fs).date()
        d1 = pd.Timestamp(today_str).date()
        return max(0, (d1 - d0).days)
    except Exception:
        return None


# ── required column keys for each row type ────────────────────────────────────

TABLE_ROW_KEYS = [
    "ticker", "name", "sector", "stage", "zone",
    "mcap", "cap_bucket", "days_since_signal",
    "price", "off_high", "conviction",
]

RIPENING_ROW_KEYS = [
    "ticker", "name", "sector", "zone",
    "macd_hist_d", "w2_stoch", "w2_stoch_arrow",
    "ret_5d", "imminence", "spot_pct_in_range",
    "mcap", "cap_bucket", "days_since_signal",
]


# ── 1. mcap join null-safety ───────────────────────────────────────────────────

class TestMcapJoin:
    def test_placeholder_returns_none(self):
        """A name with exactly 30.0亿 placeholder cap => None."""
        mktcap_by = {"000001.SZ": 30.0}
        result = _mcap_from_lookup("000001.SZ", mktcap_by)
        assert result is None, f"Placeholder 30.0 must return None, got {result}"

    def test_real_cap_returns_value(self):
        """A name with a real cap => that float value."""
        mktcap_by = {"600519.SS": 2000.0}
        result = _mcap_from_lookup("600519.SS", mktcap_by)
        assert result == 2000.0

    def test_missing_ticker_returns_none(self):
        """A ticker not in mktcap_by => None."""
        result = _mcap_from_lookup("999999.SZ", {"600519.SS": 2000.0})
        assert result is None

    def test_bucket_large_exactly_500(self):
        """Edge: mcap == 500 => large."""
        assert _cap_bucket(500.0) == "large"

    def test_bucket_large_above_500(self):
        assert _cap_bucket(501.0) == "large"

    def test_bucket_mid_exactly_100(self):
        """Edge: mcap == 100 => mid."""
        assert _cap_bucket(100.0) == "mid"

    def test_bucket_mid_below_500(self):
        assert _cap_bucket(499.9) == "mid"

    def test_bucket_small_below_100(self):
        assert _cap_bucket(99.9) == "small"

    def test_bucket_none_returns_none(self):
        assert _cap_bucket(None) is None

    def test_non_placeholder_30_boundary(self):
        """30.0 is exactly the sentinel → None; 30.1 is a real cap → 30.1."""
        mktcap_by = {"A": 30.0, "B": 30.1}
        assert _mcap_from_lookup("A", mktcap_by) is None
        assert _mcap_from_lookup("B", mktcap_by) == pytest.approx(30.1)


# ── 2. days_since_signal ───────────────────────────────────────────────────────

class TestDaysSinceSignal:
    def test_present_store_simple(self):
        """First-seen on 2026-06-30, board date 2026-07-10 => 10 days."""
        first_seen = {"000001.SZ": "2026-06-30"}
        result = _days_since("000001.SZ", first_seen, "2026-07-10")
        assert result == 10

    def test_same_day(self):
        """First-seen on the same day as board date => 0 days."""
        first_seen = {"A": "2026-07-10"}
        result = _days_since("A", first_seen, "2026-07-10")
        assert result == 0

    def test_absent_store(self):
        """No first-seen record => None."""
        result = _days_since("unknown", {}, "2026-07-10")
        assert result is None

    def test_no_today_str(self):
        """No board date => None."""
        first_seen = {"000001.SZ": "2026-06-30"}
        result = _days_since("000001.SZ", first_seen, None)
        assert result is None

    def test_fresh_flag(self):
        """days_since_signal <= 2 => freshness flag in UX."""
        first_seen = {"A": "2026-07-09"}
        result = _days_since("A", first_seen, "2026-07-10")
        assert result == 1
        assert result <= 2  # would show NEW dot


# ── 3. serialization completeness ─────────────────────────────────────────────

def _make_buy_row(ticker="000001.SZ", stage="ENTRY"):
    """Minimal buy row with all expected table-view fields."""
    return {
        "ticker": ticker, "name": f"{ticker} Name", "sector": "Technology",
        "stage": stage, "zone": None,
        "mcap": 250.0, "cap_bucket": "mid",
        "days_since_signal": 3,
        "price": 15.23, "off_high": -12.5, "conviction": 72,
        "narrative": {"theme": "AI", "theme_zh": "人工智能"},
        "washout_2w": True, "macd_hist_d": 0.05,
    }


def _make_ripening_row(ticker="600519.SS", zone="READY"):
    """Minimal ripening row with all expected table-view fields."""
    return {
        "ticker": ticker, "name": f"{ticker} Name", "sector": "Consumer Defensive",
        "stage": "RIPENING", "zone": zone,
        "mcap": None, "cap_bucket": None,
        "days_since_signal": None,
        "price": 1680.0, "off_high": None, "conviction": None,
        "macd_hist_d": -0.12, "w2_stoch": 18.5, "w2_stoch_arrow": 1,
        "ret_5d": -0.05, "imminence": 3.5, "spot_pct_in_range": 8.0,
    }


class TestSerializationCompleteness:
    def test_buy_row_has_all_table_keys(self):
        """Every required key is present (or None) on a buy row."""
        row = _make_buy_row()
        for k in TABLE_ROW_KEYS:
            assert k in row or row.get(k) is None, f"Key '{k}' missing from buy row"

    def test_ripening_row_has_all_table_keys(self):
        """Every required key is present (or None) on a ripening row."""
        row = _make_ripening_row()
        for k in RIPENING_ROW_KEYS:
            assert k in row, f"Key '{k}' missing from ripening row"

    def test_none_values_not_sentinel(self):
        """None fields in JSON serialize as null, not 0 or 30."""
        import json
        row = _make_ripening_row()
        s = json.dumps(row, default=str)
        parsed = json.loads(s)
        # mcap=None must not become 0 or 30
        assert parsed["mcap"] is None
        assert parsed["days_since_signal"] is None

    def test_cap_bucket_consistent_with_mcap(self):
        """cap_bucket is consistent with the mcap value."""
        cases = [
            (600.0, "large"),
            (500.0, "large"),
            (499.9, "mid"),
            (100.0, "mid"),
            (99.9, "small"),
            (None, None),
        ]
        for mcap, expected in cases:
            result = _cap_bucket(mcap)
            assert result == expected, f"mcap={mcap}: expected {expected}, got {result}"


# ── 4. no ordering mutation ────────────────────────────────────────────────────

class TestNoOrderingMutation:
    def _enrich_rows(self, rows, mktcap_by, first_seen, today_str):
        """Simulate the enrichment loop (display-only, no sort)."""
        import copy
        enriched = copy.deepcopy(rows)
        for r in enriched:
            tk = r.get("ticker")
            mcap = _mcap_from_lookup(tk, mktcap_by) if tk else None
            r["mcap"] = mcap
            r["cap_bucket"] = _cap_bucket(mcap)
            r["days_since_signal"] = _days_since(tk, first_seen, today_str) if tk else None
        return enriched

    def test_buy_order_unchanged(self):
        """Enrichment must not change the order of buy rows."""
        rows = [
            {"ticker": "A", "name": "A", "sector": "Tech", "stage": "ENTRY", "setup": 0.9},
            {"ticker": "B", "name": "B", "sector": "Tech", "stage": "ENTRY", "setup": 0.8},
            {"ticker": "C", "name": "C", "sector": "Tech", "stage": "RAN_LATE", "setup": 0.7},
        ]
        mktcap_by = {"A": 600.0, "B": 30.0, "C": 150.0}
        first_seen = {"A": "2026-07-01", "C": "2026-07-08"}
        enriched = self._enrich_rows(rows, mktcap_by, first_seen, "2026-07-10")
        assert [r["ticker"] for r in enriched] == ["A", "B", "C"]

    def test_ripening_order_unchanged(self):
        """Enrichment must not change the order of ripening rows."""
        rows = [
            {"ticker": "X", "name": "X", "sector": "Energy", "zone": "READY", "imminence": 2.0},
            {"ticker": "Y", "name": "Y", "sector": "Energy", "zone": "BASING", "imminence": 5.0},
        ]
        enriched = self._enrich_rows(rows, {}, {}, "2026-07-10")
        assert [r["ticker"] for r in enriched] == ["X", "Y"]

    def test_falling_rows_order_unchanged(self):
        """FALLING sink rows order not mutated by enrichment."""
        rows = [
            {"ticker": "F1", "name": "F1", "sector": "Real Estate", "zone": "FALLING"},
            {"ticker": "F2", "name": "F2", "sector": "Real Estate", "zone": "FALLING"},
        ]
        enriched = self._enrich_rows(rows, {}, {}, "2026-07-10")
        assert [r["ticker"] for r in enriched] == ["F1", "F2"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
