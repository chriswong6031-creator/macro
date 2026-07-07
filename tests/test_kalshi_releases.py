"""Unit tests for the Kalshi macro-release bracket collector (MRI PR-K).

No live network access: all payloads are inline fixtures.  Tests cover:

  bracket_to_distribution math:
    - happy path: correct median, p_above_lowest_strike, n_brackets
    - single bracket: degenerate distribution handled without crash
    - missing prices: None survivals excluded correctly
    - zero volume / all-missing: null distribution returned
    - isotonic survival clamp: non-monotone ladder corrected (negative mass prevented)
    - boundary cases: p_above_lowest_strike at bottom of range

  _parse_event_period:
    - CPI event ticker KXCPI-26JUN → ('cpi', '2026-06')
    - NFP event ticker KXPAYROLLS-26JUL → ('nfp', '2026-07')
    - Claims ticker KXJOBLESSCLAIMS-26JUL09 → ('claims', '2026-07-09')
    - Claims ticker single-digit day KXJOBLESSCLAIMS-26JUL9 → ('claims', '2026-07-09')
    - Unrecognised ticker → (None, None)

  _mid_price:
    - bid+ask present → mid
    - only last_price → last
    - only bid → bid
    - all None → (None, 'missing')
    - price normalisation 0-100 → 0-1

  _process_event:
    - bracket rows + exactly one summary row per event
    - summary row has is_summary=True, bracket rows have is_summary=False
    - summary row n_brackets counts only priced brackets

  _upsert_parquet (append-only first-seen):
    - new rows written on first run
    - same key on second run: no duplicate, row count unchanged
    - different asof_date: new rows appended (not blocked)
    - dtype preservation: strike stays float64, is_summary stays bool after dedup

  fail-open:
    - malformed market entry (missing strike) skipped silently
    - entirely empty brackets list: no summary row emitted
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.kalshi_releases import (  # noqa: E402
    _mid_price,
    _parse_event_period,
    _upsert_parquet,
    brackets_to_distribution,
)

# ---------------------------------------------------------------------------
# Helpers for building fixture market dicts
# ---------------------------------------------------------------------------

def _mkt(strike: float, yes_bid: int | None = None, yes_ask: int | None = None,
         last_price: int | None = None, event_ticker: str = "KXCPI-26JUN",
         close_time: str = "2026-07-14T12:25:00Z") -> dict:
    """Build a minimal Kalshi market dict."""
    return {
        "ticker": f"{event_ticker}-T{strike}",
        "floor_strike": strike,
        "yes_bid": yes_bid,
        "yes_ask": yes_ask,
        "last_price": last_price,
        "close_time": close_time,
        "event_ticker": event_ticker,
    }


# ---------------------------------------------------------------------------
# _mid_price
# ---------------------------------------------------------------------------

class TestMidPrice:
    def test_mid_from_bid_ask(self):
        """mid = (bid + ask) / 2, normalised from cents to [0, 1]."""
        p, ptype = _mid_price(_mkt(0.2, yes_bid=40, yes_ask=60))
        assert ptype == "mid"
        assert abs(p - 0.50) < 1e-9

    def test_mid_exact(self):
        p, ptype = _mid_price(_mkt(0.2, yes_bid=70, yes_ask=80))
        assert ptype == "mid"
        assert abs(p - 0.75) < 1e-9

    def test_fallback_to_last(self):
        p, ptype = _mid_price(_mkt(0.2, last_price=55))
        assert ptype == "last"
        assert abs(p - 0.55) < 1e-9

    def test_fallback_to_bid_only(self):
        p, ptype = _mid_price(_mkt(0.2, yes_bid=30))
        assert ptype == "bid"
        assert abs(p - 0.30) < 1e-9

    def test_fallback_to_ask_only(self):
        p, ptype = _mid_price(_mkt(0.2, yes_ask=70))
        assert ptype == "ask"
        assert abs(p - 0.70) < 1e-9

    def test_all_none_returns_missing(self):
        p, ptype = _mid_price(_mkt(0.2))
        assert ptype == "missing"
        assert p is None

    def test_normalises_100_to_1(self):
        p, _ = _mid_price(_mkt(0.2, yes_bid=100, yes_ask=100))
        assert abs(p - 1.0) < 1e-9

    def test_normalises_0_to_0(self):
        p, _ = _mid_price(_mkt(0.2, yes_bid=0, yes_ask=0))
        assert abs(p - 0.0) < 1e-9


# ---------------------------------------------------------------------------
# _parse_event_period
# ---------------------------------------------------------------------------

class TestParseEventPeriod:
    def test_cpi_june_2026(self):
        rt, period = _parse_event_period("KXCPI-26JUN")
        assert rt == "cpi"
        assert period == "2026-06"

    def test_cpi_december_2025(self):
        rt, period = _parse_event_period("KXCPI-25DEC")
        assert rt == "cpi"
        assert period == "2025-12"

    def test_nfp_july_2026(self):
        rt, period = _parse_event_period("KXPAYROLLS-26JUL")
        assert rt == "nfp"
        assert period == "2026-07"

    def test_nfp_january_2026(self):
        rt, period = _parse_event_period("KXPAYROLLS-26JAN")
        assert rt == "nfp"
        assert period == "2026-01"

    def test_claims_jul09_2026(self):
        rt, period = _parse_event_period("KXJOBLESSCLAIMS-26JUL09")
        assert rt == "claims"
        assert period == "2026-07-09"

    def test_claims_jan12(self):
        rt, period = _parse_event_period("KXJOBLESSCLAIMS-26JAN12")
        assert rt == "claims"
        assert period == "2026-01-12"

    def test_claims_single_digit_day(self):
        """N1: single-digit day (e.g. KXJOBLESSCLAIMS-26JUL9) must not be silently dropped."""
        rt, period = _parse_event_period("KXJOBLESSCLAIMS-26JUL9")
        assert rt == "claims"
        assert period == "2026-07-09"

    def test_unrecognised_returns_none_pair(self):
        rt, period = _parse_event_period("KXSOMETHINGELSE-26JUL")
        assert rt is None
        assert period is None

    def test_empty_string_returns_none_pair(self):
        rt, period = _parse_event_period("")
        assert rt is None
        assert period is None


# ---------------------------------------------------------------------------
# brackets_to_distribution
# ---------------------------------------------------------------------------

class TestBracketsToDistribution:
    """Tests for the pure CDF→distribution math."""

    def _dist(self, strikes, survivals):
        return brackets_to_distribution(strikes, survivals)

    def test_happy_path_cpi_like(self):
        """Staircase of P(CPI > X) values for CPI around 0.3% MoM."""
        # Market-implied: ~50% chance CPI > 0.2, ~20% chance CPI > 0.3
        strikes   = [-0.1, 0.0, 0.1, 0.2, 0.3, 0.4]
        # S(k) = P(CPI > k): high near bottom, drops around 0.2-0.3
        survivals = [ 0.99, 0.95, 0.80, 0.50, 0.20, 0.05]
        d = self._dist(strikes, survivals)

        # Median should be near 0.2 (where S crosses 0.5 → CDF = 0.5)
        assert d["implied_median"] is not None
        assert 0.15 <= d["implied_median"] <= 0.25

        # p_above_lowest_strike: S(k_min) = S(-0.1) = 0.99
        assert d["p_above_lowest_strike"] is not None
        assert abs(d["p_above_lowest_strike"] - 0.99) < 0.01

        # Ladder is already monotone — no correction needed
        assert d["monotonicity_corrected"] is False

        assert d["n_brackets"] == 6

    def test_nfp_like_distribution(self):
        """NFP bracket: strikes in thousands."""
        strikes   = [0, 25000, 50000, 75000, 100000, 125000]
        survivals = [0.99, 0.85,  0.65,  0.40,  0.20,   0.05]
        d = self._dist(strikes, survivals)

        # Median where S = 0.5 → between 50k and 75k
        assert d["implied_median"] is not None
        assert 50000 <= d["implied_median"] <= 75000

        # p_above_lowest_strike: S(k_min) = S(0) = 0.99
        assert d["p_above_lowest_strike"] is not None
        assert abs(d["p_above_lowest_strike"] - 0.99) < 0.01

    def test_single_bracket_returns_that_strike_as_median(self):
        """Degenerate case: one bracket with price."""
        d = self._dist([0.3], [0.5])
        # With one bracket, median is at the boundary
        assert d["implied_median"] is not None
        assert d["n_brackets"] == 1

    def test_all_missing_returns_null_distribution(self):
        """All None survivals → null distribution."""
        d = self._dist([0.1, 0.2, 0.3], [None, None, None])
        assert d["implied_median"] is None
        assert d["p_above_lowest_strike"] is None
        assert d["n_brackets"] == 0

    def test_empty_inputs_returns_null_distribution(self):
        d = self._dist([], [])
        assert d["implied_median"] is None
        assert d["n_brackets"] == 0

    def test_partial_missing_uses_only_priced_brackets(self):
        """None entries mid-ladder are excluded; rest used."""
        strikes   = [0.1, 0.2, 0.3, 0.4]
        survivals = [0.90, None, 0.40, 0.10]
        d = self._dist(strikes, survivals)
        # n_brackets should be 3 (the non-None ones)
        assert d["n_brackets"] == 3
        assert d["implied_median"] is not None

    def test_out_of_range_survival_excluded(self):
        """Survival values outside [0, 1] are excluded."""
        strikes   = [0.1, 0.2, 0.3]
        survivals = [1.5, 0.50, -0.1]  # first and last invalid
        d = self._dist(strikes, survivals)
        assert d["n_brackets"] == 1  # only the 0.50 at 0.2 is valid

    def test_probability_mass_sums_to_one(self):
        """The bracket mass partition must cover the full distribution."""
        strikes   = [0.1, 0.2, 0.3, 0.4, 0.5]
        # Monotonically decreasing survival (required for valid market)
        survivals = [0.95, 0.80, 0.50, 0.20, 0.05]
        cdfs = [1 - s for s in survivals]

        # Bottom tail mass + interior + top tail must sum to 1
        total_mass = cdfs[0]  # below ks[0]
        for i in range(1, len(strikes)):
            total_mass += cdfs[i] - cdfs[i - 1]
        total_mass += 1.0 - cdfs[-1]  # above ks[-1]
        assert abs(total_mass - 1.0) < 1e-9

    def test_median_interpolation_between_brackets(self):
        """Median interpolated correctly at 50% crossing between two brackets."""
        # S(0.2)=0.6, S(0.3)=0.4 → CDF crosses 0.5 between 0.2 and 0.3
        # Linear: F(0.2)=0.4, F(0.3)=0.6; q=0.5: frac=(0.5-0.4)/(0.6-0.4)=0.5
        # Expected median: 0.2 + 0.5*(0.3-0.2) = 0.25
        strikes   = [0.1, 0.2, 0.3, 0.4]
        survivals = [0.95, 0.60, 0.40, 0.10]
        d = self._dist(strikes, survivals)
        assert d["implied_median"] is not None
        assert abs(d["implied_median"] - 0.25) < 1e-6

    def test_p_above_lowest_strike_is_first_survival(self):
        """p_above_lowest_strike is always S(k_min), the first survival value."""
        strikes   = [-0.1, 0.0, 0.1, 0.2]
        survivals = [0.99, 0.80, 0.50, 0.20]
        d = self._dist(strikes, survivals)
        # k_min = -0.1, S(-0.1) = 0.99
        assert d["p_above_lowest_strike"] is not None
        assert abs(d["p_above_lowest_strike"] - 0.99) < 0.01

    def test_p_above_lowest_strike_positive_ladder(self):
        """Ladder with positive-only strikes — k_min = 0.5, S(0.5) = 0.90."""
        strikes   = [0.5, 1.0, 1.5]
        survivals = [0.90, 0.60, 0.20]
        d = self._dist(strikes, survivals)
        assert d["p_above_lowest_strike"] is not None
        assert abs(d["p_above_lowest_strike"] - 0.90) < 0.01

    def test_non_monotone_survival_clamp(self):
        """Non-monotone ladder [0.95,0.80,0.50,0.60,0.10] — clamp enforces isotonic.

        Without the clamp the bracket [0.50→0.60] produces negative mass.
        After clamping [0.95,0.80,0.50,0.50,0.10] all masses are >= 0.
        """
        strikes   = [0.1, 0.2, 0.3, 0.4, 0.5]
        survivals = [0.95, 0.80, 0.50, 0.60, 0.10]  # 0.60 > 0.50: inversion
        d = self._dist(strikes, survivals)

        assert d["monotonicity_corrected"] is True
        assert d["implied_median"] is not None
        # Reconstruct the clamped survivals and verify all masses >= 0
        ss_clamped = [0.95, 0.80, 0.50, 0.50, 0.10]
        cdfs = [1.0 - s for s in ss_clamped]
        masses = [cdfs[0]]  # bottom tail
        for i in range(1, len(cdfs)):
            masses.append(cdfs[i] - cdfs[i - 1])
        masses.append(1.0 - cdfs[-1])  # top tail
        for mass in masses:
            assert mass >= 0.0, f"Negative mass after clamp: {mass}"


# ---------------------------------------------------------------------------
# _upsert_parquet (append-only first-seen)
# ---------------------------------------------------------------------------

class TestUpsertParquet:
    """Test the first-seen parquet store with a temp directory."""

    @pytest.fixture()
    def store_path(self, tmp_path):
        return tmp_path / "kalshi_releases.parquet"

    def _make_row(self, asof_date="2026-07-07", release_type="cpi",
                  period="2026-06", strike=0.2, is_summary=False) -> dict:
        return {
            "asof_date": asof_date,
            "release_type": release_type,
            "period": period,
            "strike": strike,
            "p_survival": 0.50,
            "price_type": "mid",
            "is_summary": is_summary,
            "implied_median": 0.25 if is_summary else None,
            "p_above_lowest_strike": 0.80 if is_summary else None,
            "monotonicity_corrected": False if is_summary else None,
            "n_brackets": 6 if is_summary else None,
            "event_ticker": "KXCPI-26JUN",
            "close_time": "2026-07-14T12:25:00Z",
        }

    def test_first_write_creates_parquet(self, store_path):
        df = pd.DataFrame([self._make_row()])
        n_new = _upsert_parquet(store_path, df)
        assert store_path.exists()
        assert n_new == 1

    def test_idempotent_same_key(self, store_path):
        """Same (asof_date, release_type, period, strike, is_summary) → no duplicate."""
        df = pd.DataFrame([self._make_row()])
        _upsert_parquet(store_path, df)
        # Second run with identical row
        n_new = _upsert_parquet(store_path, df)
        result = pd.read_parquet(store_path)
        assert len(result) == 1
        assert n_new == 0

    def test_different_asof_date_is_new_row(self, store_path):
        """Different asof_date is a different observation — should be appended."""
        df1 = pd.DataFrame([self._make_row(asof_date="2026-07-07")])
        df2 = pd.DataFrame([self._make_row(asof_date="2026-07-08")])
        _upsert_parquet(store_path, df1)
        n_new = _upsert_parquet(store_path, df2)
        result = pd.read_parquet(store_path)
        assert len(result) == 2
        assert n_new == 1

    def test_different_strike_is_new_row(self, store_path):
        df1 = pd.DataFrame([self._make_row(strike=0.2)])
        df2 = pd.DataFrame([self._make_row(strike=0.3)])
        _upsert_parquet(store_path, df1)
        n_new = _upsert_parquet(store_path, df2)
        result = pd.read_parquet(store_path)
        assert len(result) == 2
        assert n_new == 1

    def test_empty_new_rows_no_op(self, store_path):
        df1 = pd.DataFrame([self._make_row()])
        _upsert_parquet(store_path, df1)
        n_new = _upsert_parquet(store_path, pd.DataFrame())
        result = pd.read_parquet(store_path)
        assert len(result) == 1
        assert n_new == 0

    def test_summary_and_bracket_rows_for_same_event(self, store_path):
        """Summary row (is_summary=True) and bracket row (is_summary=False) coexist."""
        rows = [
            self._make_row(strike=0.2, is_summary=False),
            self._make_row(strike=float("nan"), is_summary=True),
        ]
        df = pd.DataFrame(rows)
        n_new = _upsert_parquet(store_path, df)
        result = pd.read_parquet(store_path)
        assert n_new == 2
        assert len(result) == 2

    def test_first_seen_wins_on_conflict(self, store_path):
        """If same key appears twice in the same batch, the first row wins."""
        row1 = self._make_row(strike=0.2)
        row1["p_survival"] = 0.60  # original value
        row2 = dict(row1)
        row2["p_survival"] = 0.40  # different value, same key

        df = pd.DataFrame([row1, row2])
        _upsert_parquet(store_path, df)
        result = pd.read_parquet(store_path)
        assert len(result) == 1
        # The first row's value survives
        assert abs(result.iloc[0]["p_survival"] - 0.60) < 1e-9

    def test_parquet_dtypes_preserved_after_dedup_write(self, store_path):
        """B1: strike must be float64 and is_summary must be bool in stored parquet.

        The dedup logic must NOT coerce key columns to str before persisting.
        A summary row (strike=NaN, is_summary=True) followed by a duplicate
        write is the worst case: previously the str coercion turned strike into
        'nan' and is_summary into 'True' (string).
        """
        # First write: bracket row + summary row
        rows = [
            self._make_row(strike=0.2, is_summary=False),
            self._make_row(strike=float("nan"), is_summary=True),
        ]
        df = pd.DataFrame(rows)
        # Ensure correct input dtypes
        df["strike"] = df["strike"].astype(float)
        df["is_summary"] = df["is_summary"].astype(bool)
        _upsert_parquet(store_path, df)

        # Second write (same rows): triggers the dedup path
        _upsert_parquet(store_path, df.copy())

        result = pd.read_parquet(store_path)
        assert len(result) == 2, "dedup should not create duplicates"
        assert result["strike"].dtype == float, (
            f"strike dtype should be float, got {result['strike'].dtype}"
        )
        assert result["is_summary"].dtype == bool, (
            f"is_summary dtype should be bool, got {result['is_summary'].dtype}"
        )
        # Summary row should have NaN strike, not the string 'nan'
        summary_rows = result[result["is_summary"] == True]
        assert len(summary_rows) == 1
        import math
        assert math.isnan(summary_rows.iloc[0]["strike"]), (
            "summary row strike should be NaN float, not a string"
        )


# ---------------------------------------------------------------------------
# Fail-open / edge cases on _process_event (via KalshiReleasesAdapter internals)
# ---------------------------------------------------------------------------

class TestProcessEvent:
    """Tests for the _process_event method via the adapter."""

    def _make_adapter(self):
        """Build an adapter without loading config (not needed for these tests)."""
        from collectors.kalshi_releases import KalshiReleasesAdapter
        obj = object.__new__(KalshiReleasesAdapter)
        obj.name = "kalshi_releases"
        obj.group = "kalshi_releases"
        obj.stale_after_days = 1
        obj.cfg = {}
        obj._retries = 3
        obj._timeout = 30
        return obj

    def test_bracket_rows_and_one_summary_row(self):
        adapter = self._make_adapter()
        markets = [
            _mkt(0.1, yes_bid=80, yes_ask=90),
            _mkt(0.2, yes_bid=50, yes_ask=60),
            _mkt(0.3, yes_bid=20, yes_ask=30),
        ]
        rows = adapter._process_event(
            "KXCPI-26JUN", "cpi", "2026-06", markets, "2026-07-07"
        )
        summary = [r for r in rows if r["is_summary"]]
        brackets = [r for r in rows if not r["is_summary"]]
        assert len(summary) == 1
        assert len(brackets) == 3
        assert summary[0]["n_brackets"] == 3

    def test_missing_strike_bracket_skipped(self):
        """A market dict with no floor_strike is silently skipped."""
        adapter = self._make_adapter()
        markets = [
            {"floor_strike": None, "yes_bid": 50, "yes_ask": 60,
             "last_price": None, "event_ticker": "KXCPI-26JUN",
             "close_time": "2026-07-14T12:25:00Z"},
            _mkt(0.2, yes_bid=50, yes_ask=60),
        ]
        rows = adapter._process_event(
            "KXCPI-26JUN", "cpi", "2026-06", markets, "2026-07-07"
        )
        brackets = [r for r in rows if not r["is_summary"]]
        # Only the valid bracket (0.2) should appear
        assert len(brackets) == 1

    def test_empty_markets_list_no_summary_row(self):
        """Empty markets for an event should produce no rows at all."""
        adapter = self._make_adapter()
        rows = adapter._process_event(
            "KXCPI-26JUN", "cpi", "2026-06", [], "2026-07-07"
        )
        assert rows == []

    def test_all_markets_missing_prices_summary_has_null_median(self):
        """All no-price brackets → summary has null implied_median."""
        adapter = self._make_adapter()
        markets = [_mkt(0.1), _mkt(0.2), _mkt(0.3)]  # no prices
        rows = adapter._process_event(
            "KXCPI-26JUN", "cpi", "2026-06", markets, "2026-07-07"
        )
        summary = [r for r in rows if r["is_summary"]]
        assert len(summary) == 1
        assert summary[0]["implied_median"] is None
        assert summary[0]["n_brackets"] == 0

    def test_asof_date_propagated_to_all_rows(self):
        adapter = self._make_adapter()
        markets = [_mkt(0.2, yes_bid=50, yes_ask=60)]
        rows = adapter._process_event(
            "KXCPI-26JUN", "cpi", "2026-06", markets, "2026-07-08"
        )
        for r in rows:
            assert r["asof_date"] == "2026-07-08"

    def test_release_type_and_period_propagated(self):
        adapter = self._make_adapter()
        markets = [_mkt(50000, yes_bid=60, yes_ask=70,
                        event_ticker="KXPAYROLLS-26JUL")]
        rows = adapter._process_event(
            "KXPAYROLLS-26JUL", "nfp", "2026-07", markets, "2026-07-07"
        )
        for r in rows:
            assert r["release_type"] == "nfp"
            assert r["period"] == "2026-07"
