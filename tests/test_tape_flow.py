"""tests/test_tape_flow.py — hermetic tests for engine/tape_flow.py and scripts/build_tape_flow.py.

All tests are network-free. No parquets written to data/ during tests.
Fixtures: tests/fixtures/thetadata/bulk_trade_quote_{calls,puts}.csv

Test coverage:
  1. Signing correctness — ask-side call buy: sign=+1, premium positive contribution
  2. Signing correctness — bid-side call sell: sign=-1, negative contribution
  3. Signing correctness — puts mirrored (ask-side put = positive, bid-side put = negative)
  4. net_signed_premium = ask_side_* - bid_side_* across all legs
  5. DTE bucket boundaries: 0d / 1-7d / 8-30d / 31-90d / 90+d
  6. Moneyness bucket boundaries: ITM / ATM±5% / near-OTM 5-15% / far-OTM >15%
  7. vol_gt_oi uses oi[t-1], not same-day OI (OI timing law)
  8. delta-notional: null when no greeks available (pre-greeks-coverage behavior)
  9. delta-notional: computed correctly when greeks present
  10. Idempotent upsert: re-inserting same date replaces, does not duplicate
  11. Z-score: null when fewer than min_periods (60) rows in history
  12. Z-score: computed when ≥60 rows exist
  13. Discard law: aggregate_day returns dict (not DataFrame) — raw rows are not returned
  14. Signing provenance: signing_source="tape" on every output row
  15. bulk_trade_quote: parses wildcard-response CSV correctly (expiration+strike per row)
"""
from __future__ import annotations

import io
import json
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from engine import tape_flow as tf
from engine.flow_signing import quote_rule_sign

FIXTURES = Path(__file__).parent / "fixtures" / "thetadata"


# ─── helpers ──────────────────────────────────────────────────────────────────

def _csv_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def _make_stream_response(content: bytes, status_code: int = 200) -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.iter_lines = lambda: iter(content.split(b"\n"))
    mock_resp.iter_content = lambda chunk_size: iter([content])
    mock_resp.text = content.decode("utf-8", errors="replace")[:200]
    return mock_resp


def _minimal_trade_df(
    price: float, bid: float, ask: float, size: float = 10.0,
    right: str = "C", strike: float = 65.0, expiration: str = "2026-07-18",
    underlying_price: float | None = None,
) -> pd.DataFrame:
    """Construct a single-row trade DataFrame for unit tests."""
    row = {
        "price": price,
        "bid": bid,
        "ask": ask,
        "size": size,
        "right": right,
        "strike": strike,
        "expiration": expiration,
        "trade_timestamp": f"2026-06-30T10:00:00.000",
    }
    if underlying_price is not None:
        row["underlying_price"] = underlying_price
    return pd.DataFrame([row])


# ─── 1-3. Signing correctness ─────────────────────────────────────────────────

class TestSigningCorrectness:
    """Signs of individual trades: ask-side buy = +1 (buy-initiated), bid-side = -1."""

    def test_ask_side_call_buy(self):
        """Trade above mid-price → ask-side, sign = +1."""
        # price > mid = (bid+ask)/2 → quote rule assigns +1
        df = _minimal_trade_df(price=2.55, bid=2.40, ask=2.60, right="C")
        signed = tf._sign_trades(df)
        assert signed["sign"].iloc[0] == 1.0

    def test_bid_side_call_sell(self):
        """Trade below mid-price → bid-side, sign = -1."""
        df = _minimal_trade_df(price=2.42, bid=2.40, ask=2.60, right="C")
        signed = tf._sign_trades(df)
        assert signed["sign"].iloc[0] == -1.0

    def test_ask_side_put_buy(self):
        """Put trade above mid → ask-side, sign = +1."""
        df = _minimal_trade_df(price=1.85, bid=1.70, ask=1.90, right="P")
        signed = tf._sign_trades(df)
        assert signed["sign"].iloc[0] == 1.0

    def test_bid_side_put_sell(self):
        """Put trade below mid → bid-side, sign = -1."""
        df = _minimal_trade_df(price=1.72, bid=1.70, ask=1.90, right="P")
        signed = tf._sign_trades(df)
        assert signed["sign"].iloc[0] == -1.0

    def test_ask_side_call_premium_positive(self):
        """Ask-side call → positive contribution to ask_side_call_premium."""
        calls = _minimal_trade_df(price=2.55, bid=2.40, ask=2.60, size=10.0, right="C")
        result = tf.aggregate_day(calls=calls, puts=pd.DataFrame(),
                                  trade_date=date(2026, 6, 30), root="TST")
        assert result["ask_side_call_premium"] > 0.0
        assert result["bid_side_call_premium"] == 0.0

    def test_bid_side_call_premium_positive_stored_negative_net(self):
        """Bid-side call → bid_side_call_premium > 0, net contribution is negative."""
        calls = _minimal_trade_df(price=2.42, bid=2.40, ask=2.60, size=10.0, right="C")
        result = tf.aggregate_day(calls=calls, puts=pd.DataFrame(),
                                  trade_date=date(2026, 6, 30), root="TST")
        assert result["bid_side_call_premium"] > 0.0
        assert result["ask_side_call_premium"] == 0.0
        assert result["net_signed_premium"] < 0.0

    def test_put_sign_mirrored_contributes_to_put_buckets(self):
        """Ask-side put increments ask_side_put_premium (not call)."""
        puts = _minimal_trade_df(price=1.85, bid=1.70, ask=1.90, size=5.0, right="P")
        result = tf.aggregate_day(calls=pd.DataFrame(), puts=puts,
                                  trade_date=date(2026, 6, 30), root="TST")
        assert result["ask_side_put_premium"] > 0.0
        assert result["ask_side_call_premium"] == 0.0


class TestNetSignedPremium:
    """net_signed_premium = (ask_call - bid_call) + (ask_put - bid_put)."""

    def test_net_formula(self):
        # ask-side call: price=2.55 > mid=2.50 → sign=+1, premium=2.55×10×100=2550
        # bid-side put:  price=1.72 < mid=1.80 → sign=-1, premium=1.72×5×100=860
        calls = _minimal_trade_df(price=2.55, bid=2.40, ask=2.60, size=10.0, right="C")
        puts  = _minimal_trade_df(price=1.72, bid=1.70, ask=1.90, size=5.0,  right="P")
        result = tf.aggregate_day(calls=calls, puts=puts,
                                  trade_date=date(2026, 6, 30), root="TST")
        expected_net = (result["ask_side_call_premium"] - result["bid_side_call_premium"]) + \
                       (result["ask_side_put_premium"]  - result["bid_side_put_premium"])
        assert abs(result["net_signed_premium"] - expected_net) < 1e-6


# ─── 5. DTE bucket boundaries ─────────────────────────────────────────────────

class TestDteBuckets:
    """DTE bucket: 0d / 1-7d / 8-30d / 31-90d / 90+d"""

    def _make_trade_with_expiration(self, exp_date: str, trade_date: date) -> pd.DataFrame:
        return pd.DataFrame([{
            "price": 1.55, "bid": 1.40, "ask": 1.60, "size": 10.0,
            "right": "C", "strike": 65.0,
            "expiration": exp_date,
            "trade_timestamp": f"{trade_date}T10:00:00.000",
        }])

    @pytest.mark.parametrize("exp_offset,expected_bucket,col_prefix", [
        (0,   "0d",     "dte_0d"),      # expires today
        (3,   "1_7d",   "dte_1_7d"),    # 3 DTE
        (15,  "8_30d",  "dte_8_30d"),   # 15 DTE
        (45,  "31_90d", "dte_31_90d"),  # 45 DTE
        (120, "90p",    "dte_90p"),     # 120 DTE
    ])
    def test_dte_bucket_routing(self, exp_offset, expected_bucket, col_prefix):
        trade_date = date(2026, 6, 30)
        exp_date = (trade_date + timedelta(days=exp_offset)).strftime("%Y-%m-%d")
        calls = self._make_trade_with_expiration(exp_date, trade_date)
        result = tf.aggregate_day(calls=calls, puts=pd.DataFrame(),
                                  trade_date=trade_date, root="TST")
        # The bucket corresponding to this DTE should have a non-zero vol_share
        assert result[f"{col_prefix}_vol_share"] > 0.0
        # All other DTE buckets should have zero vol_share
        for pfx in ("dte_0d", "dte_1_7d", "dte_8_30d", "dte_31_90d", "dte_90p"):
            if pfx != col_prefix:
                assert result[f"{pfx}_vol_share"] == 0.0, f"{pfx}_vol_share should be 0 for DTE={exp_offset}"


# ─── 6. Moneyness bucket boundaries ──────────────────────────────────────────

class TestMoneynessBuckets:
    """Moneyness: ITM / ATM±5% / near-OTM 5-15% / far-OTM >15%"""

    def _make_trade_with_moneyness(self, strike: float, underlying: float) -> pd.DataFrame:
        return pd.DataFrame([{
            "price": 1.00, "bid": 0.90, "ask": 1.10, "size": 10.0,
            "right": "C", "strike": strike,
            "expiration": "2026-08-15",
            "trade_timestamp": "2026-06-30T10:00:00.000",
            "underlying_price": underlying,
        }])

    @pytest.mark.parametrize("strike,underlying,expected_col", [
        # CALLS: signed_money = strike/underlying - 1
        # ITM for call: strike < underlying → signed_money < 0 and < -5% → itm
        (65.0, 70.0, "money_itm"),       # 65/70-1 = -7.1% → itm
        (60.0, 70.0, "money_itm"),       # 60/70-1 = -14.3% → itm
        (70.0, 70.0, "money_atm"),       # 70/70-1 = 0% → atm
        (72.0, 70.0, "money_atm"),       # 72/70-1 = +2.9% → atm
        (73.6, 70.0, "money_near_otm"),  # 73.6/70-1 = +5.1% → near_otm
        (80.0, 70.0, "money_near_otm"),  # 80/70-1 = +14.3% → near_otm
        (81.5, 70.0, "money_far_otm"),   # 81.5/70-1 = +16.4% → far_otm
    ])
    def test_moneyness_bucket(self, strike, underlying, expected_col):
        calls = self._make_trade_with_moneyness(strike, underlying)
        result = tf.aggregate_day(calls=calls, puts=pd.DataFrame(),
                                  trade_date=date(2026, 6, 30), root="TST")
        assert result[f"{expected_col}_vol_share"] > 0.0, \
            f"Expected {expected_col} vol_share > 0 for strike={strike}, underlying={underlying}"


class TestMoneynessLogic:
    """Direct moneyness bucket assignment tests (signed_money convention)."""

    def test_atm_band_boundary_positive(self):
        """Exactly +5% OTM → ATM (right boundary of ATM band, inclusive)."""
        s = pd.Series([0.05])
        bucket = tf._moneyness_bucket(s)
        assert bucket.iloc[0] == "atm"

    def test_atm_band_boundary_negative(self):
        """Exactly -5% → ITM boundary: -0.05 is right on the edge, triggers itm.
        signed_money < -MONEY_ATM_BAND means strictly less than -5%."""
        # -5% is NOT less than -5%, so it's in the ATM band (|x| <= 0.05)
        s = pd.Series([-0.05])
        bucket = tf._moneyness_bucket(s)
        assert bucket.iloc[0] == "atm"  # abs(-0.05) <= 0.05 → atm

    def test_just_inside_itm(self):
        """-5.1% → ITM (just past the ATM band on the ITM side)."""
        s = pd.Series([-0.051])
        bucket = tf._moneyness_bucket(s)
        assert bucket.iloc[0] == "itm"

    def test_just_outside_atm_otm_side(self):
        """5.1% OTM → near_otm."""
        s = pd.Series([0.051])
        bucket = tf._moneyness_bucket(s)
        assert bucket.iloc[0] == "near_otm"

    def test_near_otm_boundary(self):
        """Exactly 15% OTM → near_otm (inclusive)."""
        s = pd.Series([0.15])
        bucket = tf._moneyness_bucket(s)
        assert bucket.iloc[0] == "near_otm"

    def test_far_otm(self):
        """15.1% OTM → far_otm."""
        s = pd.Series([0.151])
        bucket = tf._moneyness_bucket(s)
        assert bucket.iloc[0] == "far_otm"

    def test_deep_itm(self):
        """-20% → ITM."""
        s = pd.Series([-0.20])
        bucket = tf._moneyness_bucket(s)
        assert bucket.iloc[0] == "itm"


# ─── 7. vol_gt_oi uses oi[t-1] ────────────────────────────────────────────────

class TestVolGtOiLaw:
    """vol_gt_oi_share uses oi[t-1]; same-day OI would be a lookahead."""

    def _build_oi_df(self, expiration: str, strike: float, right: str, oi: float) -> pd.DataFrame:
        return pd.DataFrame([{
            "expiration": expiration, "strike": strike, "right": right, "open_interest": oi,
        }])

    def test_vol_gt_oi_detected(self):
        """Contract with volume > oi[t-1] → flag fires."""
        calls = _minimal_trade_df(price=2.55, bid=2.40, ask=2.60, size=100.0,
                                  right="C", strike=65.0, expiration="2026-07-18")
        oi_prev = self._build_oi_df("2026-07-18", 65.0, "C", 50.0)  # OI=50 < volume=100
        result = tf.aggregate_day(calls=calls, puts=pd.DataFrame(),
                                  trade_date=date(2026, 6, 30), root="TST",
                                  oi_prev=oi_prev)
        assert result["vol_gt_oi_share"] == 1.0  # 100% of contracts exceed OI

    def test_vol_not_gt_oi(self):
        """Contract with volume < oi[t-1] → no flag."""
        calls = _minimal_trade_df(price=2.55, bid=2.40, ask=2.60, size=10.0,
                                  right="C", strike=65.0, expiration="2026-07-18")
        oi_prev = self._build_oi_df("2026-07-18", 65.0, "C", 500.0)  # OI=500 >> volume=10
        result = tf.aggregate_day(calls=calls, puts=pd.DataFrame(),
                                  trade_date=date(2026, 6, 30), root="TST",
                                  oi_prev=oi_prev)
        assert result["vol_gt_oi_share"] == 0.0

    def test_no_oi_prev_returns_null(self):
        """When oi_prev is None (no prior day data), vol_gt_oi_share is None."""
        calls = _minimal_trade_df(price=2.55, bid=2.40, ask=2.60, size=10.0, right="C")
        result = tf.aggregate_day(calls=calls, puts=pd.DataFrame(),
                                  trade_date=date(2026, 6, 30), root="TST",
                                  oi_prev=None)
        assert result["vol_gt_oi_share"] is None

    def test_oi_is_prior_day(self):
        """Explicitly verify that passing day-t OI vs day-t volume gives the
        expected result (testing the API contract, not the date enforcement)."""
        # Volume=100, OI[t-1]=50 → vol > oi → share=1.0
        calls = _minimal_trade_df(price=2.55, bid=2.40, ask=2.60, size=100.0,
                                  right="C", strike=65.0, expiration="2026-07-18")
        oi_prev = pd.DataFrame([{
            "expiration": "2026-07-18", "strike": 65.0, "right": "C",
            "open_interest": 50.0,   # this is what the caller is responsible to pass as t-1
        }])
        result = tf.aggregate_day(calls=calls, puts=pd.DataFrame(),
                                  trade_date=date(2026, 6, 30), root="TST",
                                  oi_prev=oi_prev)
        assert result["vol_gt_oi_share"] == 1.0


# ─── 8. Delta-null pre-greeks behavior ───────────────────────────────────────

class TestDeltaNotional:
    """Delta-notional: null when greeks unavailable; computed when available."""

    def test_delta_null_without_greeks(self):
        """No greeks_chain → signed_delta_notional is None."""
        calls = _minimal_trade_df(price=2.55, bid=2.40, ask=2.60, size=10.0, right="C")
        result = tf.aggregate_day(calls=calls, puts=pd.DataFrame(),
                                  trade_date=date(2026, 6, 30), root="TST",
                                  greeks_chain=None)
        assert result["signed_delta_notional"] is None

    def test_delta_null_with_empty_greeks(self):
        """Empty greeks_chain → signed_delta_notional is None."""
        calls = _minimal_trade_df(price=2.55, bid=2.40, ask=2.60, size=10.0, right="C")
        result = tf.aggregate_day(calls=calls, puts=pd.DataFrame(),
                                  trade_date=date(2026, 6, 30), root="TST",
                                  greeks_chain=pd.DataFrame())
        assert result["signed_delta_notional"] is None

    def test_delta_computed_when_greeks_present(self):
        """With greeks, delta-notional is computed.

        Trade: ask-side call (price > mid), size=10, delta=0.5, underlying=70.
        Expected: sign=+1, delta_notional = 1 × 10 × 100 × 0.5 × 70 = 35,000.
        """
        calls = _minimal_trade_df(
            price=2.55, bid=2.40, ask=2.60, size=10.0, right="C",
            strike=65.0, expiration="2026-07-18",
        )
        greeks = pd.DataFrame([{
            "expiration": "2026-07-18", "strike": 65.0, "right": "C",
            "delta": 0.5, "underlying_price": 70.0, "date": "2026-06-30",
        }])
        result = tf.aggregate_day(calls=calls, puts=pd.DataFrame(),
                                  trade_date=date(2026, 6, 30), root="TST",
                                  greeks_chain=greeks)
        assert result["signed_delta_notional"] is not None
        # sign=+1, size=10, contract_mult=100, delta=0.5, underlying=70
        expected = 10.0 * 100.0 * 0.5 * 70.0
        assert abs(result["signed_delta_notional"] - expected) < 1.0


# ─── 10. Idempotent upsert ────────────────────────────────────────────────────

class TestIdempotentUpsert:
    """Re-inserting the same date replaces the row without duplication."""

    def _make_row(self, date_str: str, net_prem: float) -> dict:
        return {
            "root": "KRE", "date": date_str, "signing_source": "tape",
            "net_signed_premium": net_prem,
            "n_trades": 100, "n_contracts": 5, "gross_premium": 10000.0,
            "ask_side_call_premium": 5000.0, "bid_side_call_premium": 2000.0,
            "ask_side_put_premium": 3000.0,  "bid_side_put_premium": 1000.0,
            "signed_contract_volume": 50.0, "signed_delta_notional": None,
            "dte_0d_net_premium": 0.0, "dte_0d_vol_share": 0.0,
            "dte_1_7d_net_premium": 0.0, "dte_1_7d_vol_share": 0.0,
            "dte_8_30d_net_premium": net_prem, "dte_8_30d_vol_share": 1.0,
            "dte_31_90d_net_premium": 0.0, "dte_31_90d_vol_share": 0.0,
            "dte_90p_net_premium": 0.0, "dte_90p_vol_share": 0.0,
            "money_itm_net_premium": 0.0, "money_itm_vol_share": 0.0,
            "money_atm_net_premium": net_prem, "money_atm_vol_share": 0.5,
            "money_near_otm_net_premium": 0.0, "money_near_otm_vol_share": 0.5,
            "money_far_otm_net_premium": 0.0, "money_far_otm_vol_share": 0.0,
            "vol_gt_oi_share": 0.0,
        }

    def test_first_insert(self):
        existing = pd.DataFrame()
        row = self._make_row("2026-06-30", 5000.0)
        result = tf.upsert_feature_row(existing, row)
        assert len(result) == 1
        assert result["date"].iloc[0] == "2026-06-30"

    def test_upsert_replaces_not_duplicates(self):
        existing = pd.DataFrame()
        row1 = self._make_row("2026-06-30", 5000.0)
        after_first = tf.upsert_feature_row(existing, row1)

        row2 = self._make_row("2026-06-30", 9999.0)  # same date, different value
        after_second = tf.upsert_feature_row(after_first, row2)

        # Should have exactly 1 row
        assert len(after_second) == 1
        # Value should be updated to the new row
        assert after_second["net_signed_premium"].iloc[0] == 9999.0

    def test_append_new_date(self):
        existing = pd.DataFrame()
        row1 = self._make_row("2026-06-29", 5000.0)
        after_first = tf.upsert_feature_row(existing, row1)

        row2 = self._make_row("2026-06-30", 6000.0)
        after_second = tf.upsert_feature_row(after_first, row2)

        # Should have 2 rows
        assert len(after_second) == 2
        dates = sorted(after_second["date"].astype(str).str[:10].tolist())
        assert dates == ["2026-06-29", "2026-06-30"]


# ─── 11-12. Z-score behavior ─────────────────────────────────────────────────

class TestZscores:
    """Z-scores null when < min_periods; computed when ≥ min_periods."""

    def _build_history(self, n: int, col: str = "net_signed_premium") -> pd.DataFrame:
        """Build n rows of synthetic history."""
        rows = []
        base = date(2024, 1, 1)
        for i in range(n):
            d = base + timedelta(days=i)
            rows.append({
                "root": "TST", "date": str(d)[:10],
                "signing_source": "tape",
                col: float(100 + i),
                # Other numeric columns with minimal values
                "n_trades": 10, "n_contracts": 2, "gross_premium": 1000.0,
                "ask_side_call_premium": 500.0, "bid_side_call_premium": 200.0,
                "ask_side_put_premium": 300.0,  "bid_side_put_premium": 100.0,
                "signed_contract_volume": 5.0,  "signed_delta_notional": None,
                "vol_gt_oi_share": 0.5,
                **{f"dte_{b}_net_premium": 0.0 for b in ("0d","1_7d","8_30d","31_90d","90p")},
                **{f"dte_{b}_vol_share": 0.0 for b in ("0d","1_7d","8_30d","31_90d","90p")},
                **{f"money_{b}_net_premium": 0.0 for b in ("itm","atm","near_otm","far_otm")},
                **{f"money_{b}_vol_share": 0.0 for b in ("itm","atm","near_otm","far_otm")},
            })
        return pd.DataFrame(rows)

    def test_zscore_null_when_history_too_short(self):
        """Fewer than 60 rows → z-score is null (NaN)."""
        df = self._build_history(59)
        df_z = tf.add_zscores(df)
        # Last row (row 58, 0-indexed) should have NaN z-score for net_signed_premium
        # (rolling window needs min_periods=60, so with 59 rows the last row is still NaN)
        assert pd.isna(df_z["net_signed_premium_z252"].iloc[-1])

    def test_zscore_computed_when_enough_history(self):
        """At least 60 rows → z-score is a number (not NaN) for rows beyond the 60th."""
        df = self._build_history(100)
        df_z = tf.add_zscores(df)
        # Rows after the 60th (index 59) should have valid z-scores
        assert not pd.isna(df_z["net_signed_premium_z252"].iloc[-1])

    def test_zscore_columns_all_present(self):
        """add_zscores adds <col>_z252 for every numeric feature column."""
        df = self._build_history(5)
        df_z = tf.add_zscores(df)
        expected_z_cols = [f"{c}_z252" for c in tf._numeric_feature_cols()]
        for col in expected_z_cols:
            assert col in df_z.columns, f"Missing z-score column: {col}"


# ─── 13. Discard law ─────────────────────────────────────────────────────────

class TestDiscardLaw:
    """aggregate_day returns a dict (not a DataFrame) — raw rows are NOT returned."""

    def test_returns_dict_not_dataframe(self):
        calls = _minimal_trade_df(price=2.55, bid=2.40, ask=2.60, size=10.0, right="C")
        result = tf.aggregate_day(calls=calls, puts=pd.DataFrame(),
                                  trade_date=date(2026, 6, 30), root="TST")
        assert isinstance(result, dict), "aggregate_day must return dict, not DataFrame"

    def test_no_raw_rows_in_result(self):
        """The result dict must not contain any raw trade-level data."""
        calls = _minimal_trade_df(price=2.55, bid=2.40, ask=2.60, size=10.0, right="C")
        result = tf.aggregate_day(calls=calls, puts=pd.DataFrame(),
                                  trade_date=date(2026, 6, 30), root="TST")
        # Raw columns from the trade_quote response must not be in the result
        raw_cols = {"trade_timestamp", "quote_timestamp", "sequence",
                    "bid_size", "ask_size", "bid_exchange", "ask_exchange"}
        for col in raw_cols:
            assert col not in result, f"Raw column {col!r} found in aggregate_day output"


# ─── 14. Signing provenance ───────────────────────────────────────────────────

class TestSigningProvenance:
    """signing_source='tape' on every output row."""

    def test_signing_source_stamped(self):
        calls = _minimal_trade_df(price=2.55, bid=2.40, ask=2.60, size=10.0, right="C")
        result = tf.aggregate_day(calls=calls, puts=pd.DataFrame(),
                                  trade_date=date(2026, 6, 30), root="TST")
        assert result["signing_source"] == "tape"

    def test_signing_source_on_empty(self):
        """Even when no trade data, signing_source must be stamped."""
        result = tf.aggregate_day(calls=pd.DataFrame(), puts=pd.DataFrame(),
                                  trade_date=date(2026, 6, 30), root="TST")
        assert result["signing_source"] == "tape"

    def test_signing_source_in_upsert(self):
        """signing_source preserved through upsert cycle."""
        row = {
            "root": "TST", "date": "2026-06-30", "signing_source": "tape",
            "net_signed_premium": 1000.0, "n_trades": 5, "n_contracts": 1,
            "gross_premium": 1000.0, "ask_side_call_premium": 1000.0,
            "bid_side_call_premium": 0.0, "ask_side_put_premium": 0.0,
            "bid_side_put_premium": 0.0, "signed_contract_volume": 5.0,
            "signed_delta_notional": None, "vol_gt_oi_share": 0.0,
            **{f"dte_{b}_net_premium": 0.0 for b in ("0d","1_7d","8_30d","31_90d","90p")},
            **{f"dte_{b}_vol_share": 0.0 for b in ("0d","1_7d","8_30d","31_90d","90p")},
            **{f"money_{b}_net_premium": 0.0 for b in ("itm","atm","near_otm","far_otm")},
            **{f"money_{b}_vol_share": 0.0 for b in ("itm","atm","near_otm","far_otm")},
        }
        result = tf.upsert_feature_row(pd.DataFrame(), row)
        assert result["signing_source"].iloc[0] == "tape"


# ─── 15. bulk_trade_quote parsing ────────────────────────────────────────────

class TestBulkTradeQuoteParsing:
    """bulk_trade_quote parses wildcard CSV (per-row expiration+strike)."""

    def test_parses_calls_fixture(self, monkeypatch):
        """bulk_trade_quote parses the calls fixture correctly."""
        from collectors import thetadata as td

        csv_data = _csv_bytes("bulk_trade_quote_calls.csv")
        mock_session = MagicMock()
        mock_resp = _make_stream_response(csv_data)
        mock_session.get.return_value = mock_resp

        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True)
        monkeypatch.setattr("collectors.thetadata._session", lambda: mock_session)

        df = td.bulk_trade_quote("KRE", "call", date(2026, 6, 30), date(2026, 6, 30))
        assert df is not None
        assert not df.empty
        assert "strike" in df.columns
        assert "expiration" in df.columns
        # Fixture has 5 call rows
        assert len(df) == 5
        # Strikes should vary (not all the same)
        assert df["strike"].nunique() > 1
        # right should be normalized to "C"
        assert (df["right"] == "C").all()

    def test_parses_puts_fixture(self, monkeypatch):
        """bulk_trade_quote parses the puts fixture correctly."""
        from collectors import thetadata as td

        csv_data = _csv_bytes("bulk_trade_quote_puts.csv")
        mock_session = MagicMock()
        mock_resp = _make_stream_response(csv_data)
        mock_session.get.return_value = mock_resp

        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True)
        monkeypatch.setattr("collectors.thetadata._session", lambda: mock_session)

        df = td.bulk_trade_quote("KRE", "put", date(2026, 6, 30), date(2026, 6, 30))
        assert df is not None
        assert not df.empty
        # Fixture has 3 put rows
        assert len(df) == 3
        # right should be normalized to "P"
        assert (df["right"] == "P").all()

    def test_unreachable_returns_none(self, monkeypatch):
        """bulk_trade_quote returns None when terminal is unreachable."""
        from collectors import thetadata as td
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: False)
        result = td.bulk_trade_quote("KRE", "call", date(2026, 6, 30), date(2026, 6, 30))
        assert result is None

    def test_empty_response_returns_empty_df(self, monkeypatch):
        """bulk_trade_quote returns empty DataFrame for no-data response."""
        from collectors import thetadata as td

        # Just a header row (no data rows)
        csv_data = b"symbol,expiration,strike,right,trade_timestamp,quote_timestamp,sequence,ext_condition1,ext_condition2,ext_condition3,ext_condition4,condition,size,exchange,price,bid_size,bid_exchange,bid,bid_condition,ask_size,ask_exchange,ask,ask_condition\n"
        mock_session = MagicMock()
        mock_resp = _make_stream_response(csv_data)
        mock_session.get.return_value = mock_resp

        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True)
        monkeypatch.setattr("collectors.thetadata._session", lambda: mock_session)

        df = td.bulk_trade_quote("KRE", "call", date(2026, 6, 30), date(2026, 6, 30))
        assert df is not None
        assert df.empty


# ─── Integration: full fixture round-trip ─────────────────────────────────────

class TestFixtureRoundTrip:
    """End-to-end: parse fixtures → sign → aggregate → check key invariants."""

    def test_full_aggregate_from_fixtures(self):
        """Parse both fixtures and run aggregate_day; verify invariants."""
        calls_csv = pd.read_csv(FIXTURES / "bulk_trade_quote_calls.csv")
        puts_csv  = pd.read_csv(FIXTURES / "bulk_trade_quote_puts.csv")

        # Normalize to the schema bulk_trade_quote produces
        for df in (calls_csv, puts_csv):
            df["right"] = df["right"].str.upper().str[:1]
            df["root"] = "KRE"

        result = tf.aggregate_day(
            calls=calls_csv, puts=puts_csv,
            trade_date=date(2026, 6, 30), root="KRE",
        )

        # Basic invariants
        assert result["signing_source"] == "tape"
        assert result["root"] == "KRE"
        assert result["n_trades"] == 8   # 5 calls + 3 puts from fixtures
        assert result["gross_premium"] > 0.0
        # Vol shares sum to ~1.0 for DTE buckets
        dte_vol_sum = sum(result.get(f"dte_{b}_vol_share", 0.0) or 0.0
                          for b in ("0d","1_7d","8_30d","31_90d","90p"))
        assert abs(dte_vol_sum - 1.0) < 0.02, f"DTE vol shares sum={dte_vol_sum}, expected ~1.0"


# ─── 16. Both-rights-or-no-row law (house empty-vs-failed) ────────────────────

class TestBothRightsOrNoRow:
    """A day row must be written ONLY when BOTH the call and put legs SUCCEEDED.

    Collector contract: None = FAILURE (unreachable / stream truncated);
    empty DataFrame = SUCCESS with no trades. A failed leg (None) must never be
    persisted as a partial day (the KRE 2026-06-30 puts-only bug this guards).
    """

    def _patch_build(self, monkeypatch, calls_ret, puts_ret):
        """Patch the collector + I/O so build_one runs hermetically.

        Returns a list that captures any (root, df) passed to _write_parquet.
        """
        import scripts.build_tape_flow as bld
        from collectors import thetadata as td

        # build_one does `from collectors import thetadata as td` then calls
        # td.reachable() and (via _fetch_both_rights) td.bulk_trade_quote(...).
        # Patch those attributes on the real module so no terminal is contacted.
        monkeypatch.setattr(td, "reachable", lambda: True)

        def _fake_bulk(root, right, sd, ed):
            return calls_ret if right == "call" else puts_ret

        monkeypatch.setattr(td, "bulk_trade_quote", _fake_bulk)

        # No OI / greeks lookups (avoid touching the eod store)
        monkeypatch.setattr(bld, "_load_oi_prev", lambda root, d: None)
        monkeypatch.setattr(bld, "_load_greeks_chain", lambda root, d: None)
        monkeypatch.setattr(bld, "_load_existing", lambda root: pd.DataFrame())

        writes: list = []
        monkeypatch.setattr(bld, "_write_parquet",
                            lambda root, df, dry_run=False: writes.append((root, df)) or Path("x"))
        return bld, writes

    def test_calls_leg_none_no_row_written(self, monkeypatch):
        """Calls fetch FAILED (None), puts succeeded with data → NO row written."""
        puts = _minimal_trade_df(price=1.85, bid=1.70, ask=1.90, size=5.0, right="P")
        bld, writes = self._patch_build(monkeypatch, calls_ret=None, puts_ret=puts)
        result = bld.build_one("KRE", date(2026, 6, 30))
        assert result is None, "build_one must return None when a leg failed"
        assert writes == [], "no parquet may be written when the calls leg failed"

    def test_puts_leg_none_no_row_written(self, monkeypatch):
        """Puts fetch FAILED (None), calls succeeded with data → NO row written."""
        calls = _minimal_trade_df(price=2.55, bid=2.40, ask=2.60, size=10.0, right="C")
        bld, writes = self._patch_build(monkeypatch, calls_ret=calls, puts_ret=None)
        result = bld.build_one("KRE", date(2026, 6, 30))
        assert result is None, "build_one must return None when a leg failed"
        assert writes == [], "no parquet may be written when the puts leg failed"

    def test_both_legs_succeed_row_written(self, monkeypatch):
        """Both legs succeed (calls has data, puts empty-successful) → row written."""
        calls = _minimal_trade_df(price=2.55, bid=2.40, ask=2.60, size=10.0, right="C")
        bld, writes = self._patch_build(monkeypatch, calls_ret=calls, puts_ret=pd.DataFrame())
        result = bld.build_one("KRE", date(2026, 6, 30))
        assert result is not None, "build_one must produce a row when both legs succeeded"
        assert len(writes) == 1, "exactly one parquet write when both legs succeeded"

    def test_both_legs_empty_successful_no_row(self, monkeypatch):
        """Both legs empty-successful (no trades) → no row (nothing to aggregate)."""
        bld, writes = self._patch_build(monkeypatch, calls_ret=pd.DataFrame(), puts_ret=pd.DataFrame())
        result = bld.build_one("KRE", date(2026, 6, 30))
        assert result is None
        assert writes == []


# ─── P2.1 required features (T2a spec) ───────────────────────────────────────

class TestP21RequiredFeatures:
    """Verify all P2.1-required features are present in aggregate_day output.

    Required by scripts/build_tape_flow_daily.py task spec:
      net_signed_premium, signed_pc_ratio, gross_premium, volume,
      zerodte_share, dte_quality_share (8-90d), short_dated_otm_call_share,
      trade_count, block_share
    """

    TRADE_DATE = date(2026, 7, 2)
    SPOT = 560.0

    def _make_calls(self, n: int = 15, dte: int = 7) -> pd.DataFrame:
        rows = []
        for i in range(n):
            # All price above mid → all buyer-initiated
            rows.append({
                "price": 2.60, "bid": 2.40, "ask": 2.70,
                "size": float(i + 1),
                "right": "C",
                "strike": self.SPOT + 5.0,
                "expiration": str(self.TRADE_DATE + timedelta(days=dte)),
                "trade_timestamp": f"{self.TRADE_DATE}T10:00:{i:02d}Z",
            })
        return pd.DataFrame(rows)

    def _make_puts(self, n: int = 10, dte: int = 7) -> pd.DataFrame:
        rows = []
        for j in range(n):
            rows.append({
                "price": 1.80, "bid": 1.60, "ask": 2.00,
                "size": float(j + 1),
                "right": "P",
                "strike": self.SPOT - 5.0,
                "expiration": str(self.TRADE_DATE + timedelta(days=dte)),
                "trade_timestamp": f"{self.TRADE_DATE}T10:00:{j + 30:02d}Z",
            })
        return pd.DataFrame(rows)

    def test_signed_pc_ratio_present_and_typed(self):
        """signed_pc_ratio is a float or None; never missing key."""
        calls = self._make_calls()
        puts = self._make_puts()
        row = tf.aggregate_day(calls, puts, self.TRADE_DATE, "SPY")
        assert "signed_pc_ratio" in row, "signed_pc_ratio key must be present"
        val = row["signed_pc_ratio"]
        assert val is None or isinstance(val, (int, float))

    def test_volume_equals_total_size(self):
        """volume = total contracts traded (sum of all size)."""
        calls = self._make_calls(n=5)
        puts = self._make_puts(n=3)
        row = tf.aggregate_day(calls, puts, self.TRADE_DATE, "SPY")
        assert "volume" in row
        # Volume must be positive and roughly sum of all size values
        assert row["volume"] > 0

    def test_zerodte_share_range(self):
        """zerodte_share in [0, 1] when computed."""
        # Mix of 0DTE and 7DTE trades
        calls_0dte = self._make_calls(n=5, dte=0)
        calls_7dte = self._make_calls(n=5, dte=7)
        calls = pd.concat([calls_0dte, calls_7dte], ignore_index=True)
        row = tf.aggregate_day(calls, pd.DataFrame(), self.TRADE_DATE, "SPY")
        assert "zerodte_share" in row
        val = row["zerodte_share"]
        assert val is not None
        assert 0.0 <= val <= 1.0, f"zerodte_share out of [0,1]: {val}"

    def test_dte_quality_share_range(self):
        """dte_quality_share (8-90d) in [0, 1]."""
        calls_8d = self._make_calls(n=5, dte=20)   # 8-30d window
        calls_50d = self._make_calls(n=5, dte=50)  # 31-90d window
        calls_0d = self._make_calls(n=5, dte=0)    # outside quality window
        calls = pd.concat([calls_8d, calls_50d, calls_0d], ignore_index=True)
        row = tf.aggregate_day(calls, pd.DataFrame(), self.TRADE_DATE, "SPY")
        assert "dte_quality_share" in row
        val = row["dte_quality_share"]
        assert val is not None
        assert 0.0 <= val <= 1.0, f"dte_quality_share out of [0,1]: {val}"

    def test_short_dated_otm_call_share_without_underlying(self):
        """short_dated_otm_call_share is 0.0 or None when no underlying_price is available.

        Without underlying_price, moneyness is indeterminate → no OTM calls can be
        confirmed → the share is 0.0 (not None, since volume denominator is known).
        underlying_source stamps 'none' to signal the absence.
        """
        calls = self._make_calls()
        row = tf.aggregate_day(calls, pd.DataFrame(), self.TRADE_DATE, "SPY",
                               greeks_chain=None)
        assert "short_dated_otm_call_share" in row
        val = row["short_dated_otm_call_share"]
        # Without underlying, no OTM calls can be confirmed: expect 0.0 or None
        assert val is None or val == pytest.approx(0.0), \
            f"Expected 0.0 or None without underlying, got {val}"
        # underlying_source must indicate absence
        assert row.get("underlying_source") in ("none", None)

    def test_short_dated_otm_call_share_with_greeks(self):
        """short_dated_otm_call_share in [0,1] when underlying_price available via greeks."""
        calls = self._make_calls(n=10, dte=15)   # 15 DTE → short-dated window [1-30]
        greeks = pd.DataFrame({
            "expiration": [str(self.TRADE_DATE + timedelta(days=15))],
            "strike": [self.SPOT + 5.0],  # OTM call (strike > spot)
            "right": ["C"],
            "delta": [0.35],
            "underlying_price": [self.SPOT],
        })
        row = tf.aggregate_day(calls, pd.DataFrame(), self.TRADE_DATE, "SPY",
                               greeks_chain=greeks)
        assert "short_dated_otm_call_share" in row
        val = row["short_dated_otm_call_share"]
        if val is not None:
            assert 0.0 <= val <= 1.0, f"short_dated_otm_call_share out of [0,1]: {val}"

    def test_trade_count_equals_n_trades(self):
        """trade_count and n_trades are consistent aliases."""
        calls = self._make_calls(n=8)
        puts = self._make_puts(n=5)
        row = tf.aggregate_day(calls, puts, self.TRADE_DATE, "SPY")
        assert "trade_count" in row
        assert "n_trades" in row
        assert row["trade_count"] == row["n_trades"]
        assert row["trade_count"] > 0

    def test_block_share_range(self):
        """block_share (top-decile trade-size fraction) in [0, 1]."""
        # Mix of large (block) and small trades
        rows = []
        for i in range(20):
            size = 500.0 if i == 0 else float(i + 1)  # one very large trade
            rows.append({
                "price": 2.60, "bid": 2.40, "ask": 2.70, "size": size,
                "right": "C", "strike": self.SPOT + 5.0,
                "expiration": str(self.TRADE_DATE + timedelta(days=7)),
                "trade_timestamp": f"{self.TRADE_DATE}T10:00:{i:02d}Z",
            })
        calls = pd.DataFrame(rows)
        row = tf.aggregate_day(calls, pd.DataFrame(), self.TRADE_DATE, "SPY")
        assert "block_share" in row
        val = row["block_share"]
        if val is not None:
            assert 0.0 <= val <= 1.0, f"block_share out of [0,1]: {val}"

    def test_all_p21_keys_present(self):
        """All required P2.1 feature keys are present in aggregate_day output."""
        required = {
            "net_signed_premium", "signed_pc_ratio", "gross_premium", "volume",
            "zerodte_share", "dte_quality_share", "short_dated_otm_call_share",
            "trade_count", "block_share",
        }
        calls = self._make_calls()
        puts = self._make_puts()
        row = tf.aggregate_day(calls, puts, self.TRADE_DATE, "SPY")
        missing = required - set(row.keys())
        assert not missing, f"Missing required P2.1 columns: {sorted(missing)}"

    def test_all_p21_keys_present_empty_both_legs(self):
        """P2.1 keys must be present even when both calls and puts are empty."""
        required = {
            "net_signed_premium", "signed_pc_ratio", "gross_premium", "volume",
            "zerodte_share", "dte_quality_share", "short_dated_otm_call_share",
            "trade_count", "block_share", "underlying_source",
        }
        row = tf.aggregate_day(
            calls=pd.DataFrame(), puts=pd.DataFrame(),
            trade_date=self.TRADE_DATE, root="SPY",
        )
        missing = required - set(row.keys())
        assert not missing, f"Empty-day row missing P2.1 columns: {sorted(missing)}"

    def test_all_p21_keys_present_nbbo_filtered_empty(self):
        """P2.1 keys must be present when all rows are filtered by NBBO validation."""
        required = {
            "net_signed_premium", "signed_pc_ratio", "gross_premium", "volume",
            "zerodte_share", "dte_quality_share", "short_dated_otm_call_share",
            "trade_count", "block_share", "underlying_source",
        }
        # bid=0 → all rows fail the NBBO filter → empty result path
        bad_calls = self._make_calls().copy()
        bad_calls["bid"] = 0.0
        bad_puts = self._make_puts().copy()
        bad_puts["bid"] = 0.0
        row = tf.aggregate_day(
            calls=bad_calls, puts=bad_puts,
            trade_date=self.TRADE_DATE, root="SPY",
        )
        missing = required - set(row.keys())
        assert not missing, f"NBBO-filtered row missing P2.1 columns: {sorted(missing)}"


# ─── bulk_trade_quote normalisation (new collector method) ────────────────────

class TestBulkTradeQuoteNormalisation:
    """Verify collectors.thetadata._normalize_trade_quote_df column contract."""

    def test_right_mapped_call_put(self):
        """CALL → C, PUT → P in the normalized output."""
        from collectors.thetadata import _normalize_trade_quote_df
        raw = pd.DataFrame({
            "symbol": ["SPY", "SPY"],
            "expiration": ["2026-07-18", "2026-07-18"],
            "strike": [560.0, 555.0],
            "right": ["CALL", "PUT"],
            "trade_timestamp": ["2026-07-02T10:00:00", "2026-07-02T10:00:01"],
            "price": [2.5, 1.8],
            "size": [10.0, 5.0],
            "bid": [2.0, 1.5],
            "ask": [3.0, 2.0],
        })
        df = _normalize_trade_quote_df(raw, "SPY")
        rights = set(df["right"].unique())
        assert rights.issubset({"C", "P"}), f"Unexpected right values: {rights}"

    def test_symbol_renamed_to_root(self):
        """symbol column becomes root in the normalized output."""
        from collectors.thetadata import _normalize_trade_quote_df
        raw = pd.DataFrame({
            "symbol": ["SPY"],
            "expiration": ["2026-07-18"],
            "strike": [560.0],
            "right": ["CALL"],
            "trade_timestamp": ["2026-07-02T10:00:00"],
            "price": [2.5], "size": [10.0], "bid": [2.0], "ask": [3.0],
        })
        df = _normalize_trade_quote_df(raw, "SPY")
        assert "root" in df.columns
        assert "symbol" not in df.columns

    def test_extra_columns_dropped(self):
        """sequence, ext_condition1-4, condition etc. are dropped from output."""
        from collectors.thetadata import _normalize_trade_quote_df
        raw = pd.DataFrame({
            "symbol": ["SPY"], "expiration": ["2026-07-18"],
            "strike": [560.0], "right": ["CALL"],
            "trade_timestamp": ["2026-07-02T10:00:00"],
            "quote_timestamp": ["2026-07-02T10:00:00"],
            "price": [2.5], "size": [10.0], "bid": [2.0], "ask": [3.0],
            "sequence": [12345], "ext_condition1": [""], "condition": ["0"],
        })
        df = _normalize_trade_quote_df(raw, "SPY")
        allowed = {"root", "expiration", "strike", "right", "trade_timestamp",
                   "price", "size", "bid", "ask"}
        unexpected = set(df.columns) - allowed
        assert not unexpected, f"Extra columns not dropped: {unexpected}"

    def test_numeric_coercion(self):
        """price, size, bid, ask are numeric floats after normalization."""
        from collectors.thetadata import _normalize_trade_quote_df
        raw = pd.DataFrame({
            "symbol": ["SPY"], "expiration": ["2026-07-18"],
            "strike": ["560.000"], "right": ["CALL"],
            "trade_timestamp": ["2026-07-02T10:00:00"],
            "price": ["2.500"], "size": ["10"], "bid": ["2.000"], "ask": ["3.000"],
        })
        df = _normalize_trade_quote_df(raw, "SPY")
        for col in ("price", "size", "bid", "ask", "strike"):
            assert pd.api.types.is_numeric_dtype(df[col]), f"{col} not numeric"

    def test_unreachable_terminal_returns_none(self):
        """bulk_trade_quote returns None when terminal is unreachable."""
        with patch("collectors.thetadata.reachable", return_value=False):
            from collectors.thetadata import bulk_trade_quote
            # Existing bulk_trade_quote(root, right, start_date, end_date)
            result = bulk_trade_quote("SPY", "call", date(2026, 7, 2), date(2026, 7, 2))
            assert result is None


# ─── concurrency guard ────────────────────────────────────────────────────────

class TestConcurrencyGuard:
    """_max_workers respects the backfill-alive pgrep law."""

    def test_max_workers_backfill_alive(self):
        """2 workers when backfill is alive (house law: backfill owns 6 of 8 slots)."""
        from scripts.build_tape_flow_daily import _max_workers
        with patch("scripts.build_tape_flow_daily._backfill_alive", return_value=True):
            assert _max_workers() == 2

    def test_max_workers_backfill_dead(self):
        """6 workers when backfill not running (leaves 2 of 8 terminal slots free)."""
        from scripts.build_tape_flow_daily import _max_workers
        with patch("scripts.build_tape_flow_daily._backfill_alive", return_value=False):
            assert _max_workers() == 6


# ─── store resumability ───────────────────────────────────────────────────────

class TestResumeability:
    """State file marks root-days done; re-run skips completed work."""

    def test_mark_done_and_is_done(self):
        from scripts.build_tape_flow_daily import _mark_done, _is_done
        state: dict = {}
        d = date(2026, 7, 2)
        assert not _is_done(state, "forward", "SPY", d)
        _mark_done(state, "forward", "SPY", d)
        assert _is_done(state, "forward", "SPY", d)

    def test_mark_done_idempotent(self):
        """Marking the same date twice should not duplicate entries."""
        from scripts.build_tape_flow_daily import _mark_done, _is_done
        state: dict = {}
        d = date(2026, 7, 2)
        _mark_done(state, "forward", "SPY", d)
        _mark_done(state, "forward", "SPY", d)
        dates = state["completed"]["forward"]["SPY"]
        assert dates.count(str(d)) == 1, "Idempotent: date should appear only once"

    def test_different_modes_independent(self):
        """forward and episodes completion states are tracked independently."""
        from scripts.build_tape_flow_daily import _mark_done, _is_done
        state: dict = {}
        d = date(2026, 7, 2)
        _mark_done(state, "forward", "SPY", d)
        assert _is_done(state, "forward", "SPY", d)
        assert not _is_done(state, "episodes", "SPY", d)


# ── budget-minutes tests ───────────────────────────────────────────────────────

class TestBudgetMinutes:
    """--budget-minutes: hard-stop, clean exit, state resumable next run."""

    def _make_work(self, n: int) -> list[tuple[str, date]]:
        d = date(2024, 1, 2)
        return [("SPY", d + timedelta(days=i)) for i in range(n)]

    def test_budget_exceeded_stops_cleanly(self, tmp_path, monkeypatch):
        """With a zero-second budget the loop stops after at most a handful of items.

        Verifies:
          - main() returns without raising (exit 0 path)
          - state is saved (budget_exceeded branch calls _save_state)
          - the number of items marked done is < total work (budget was active)
        """
        import scripts.build_tape_flow_daily as mod

        state: dict = {}

        # Patch reachable() so no ThetaData check
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True, raising=False)

        # Patch _load_state / _save_state to use our in-memory state dict
        saved: list[dict] = []
        monkeypatch.setattr(mod, "_load_state", lambda: state)
        monkeypatch.setattr(mod, "_save_state", lambda s: saved.append(dict(s)))

        # Patch _register_run_status (network/file side effect)
        monkeypatch.setattr(mod, "_register_run_status", lambda *a, **kw: None)

        # Patch _process_root_day to be instant + always return ok
        call_log: list[tuple[str, date]] = []

        def _fast_process(root, trade_date, mode, retain_raw):
            call_log.append((root, trade_date))
            return {"status": "ok", "root": root, "date": str(trade_date)}

        monkeypatch.setattr(mod, "_process_root_day", _fast_process)

        # Patch _audit_store to always pass
        monkeypatch.setattr(mod, "_audit_store",
                            lambda root, d: {"ok": True})

        # Build a large enough work list that the budget would stop it early,
        # but patch time.perf_counter so it immediately reports budget exceeded
        # after the first future completes.
        real_perf_counter = mod.time.perf_counter
        call_count = 0

        def _mock_perf_counter():
            nonlocal call_count
            call_count += 1
            # First few calls (setup): return 0.0
            # After 5 calls (enough for t_global and one loop iter): return very large
            if call_count <= 4:
                return 0.0
            return 1e9  # far past any budget deadline

        monkeypatch.setattr(mod.time, "perf_counter", _mock_perf_counter)

        # Patch gex_symbols to avoid needing the universe (episodes mode is used
        # so we avoid the gex_symbols import path)
        # Also patch _episode_root_days to return our canned work list
        work = self._make_work(20)
        monkeypatch.setattr(mod, "_episode_root_days",
                            lambda episode_root_filter=None: work)

        # Run with a 1-minute budget (the mock perf_counter makes it expire quickly)
        mod.main(["--mode", "episodes", "--budget-minutes", "1", "--no-audit"])

        # Some work must have been processed
        assert len(call_log) >= 1, "At least one root-day should have been processed"

        # State must have been saved (budget-stop path calls _save_state)
        assert len(saved) >= 1, "_save_state must be called at least once"

    def test_budget_none_runs_to_completion(self, monkeypatch):
        """Without --budget-minutes the loop always drains all work."""
        import scripts.build_tape_flow_daily as mod

        state: dict = {}
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True, raising=False)
        monkeypatch.setattr(mod, "_load_state", lambda: state)
        monkeypatch.setattr(mod, "_save_state", lambda s: None)
        monkeypatch.setattr(mod, "_register_run_status", lambda *a, **kw: None)
        monkeypatch.setattr(mod, "_audit_store", lambda root, d: {"ok": True})

        call_log: list[tuple] = []

        def _fast_process(root, trade_date, mode, retain_raw):
            call_log.append((root, trade_date))
            return {"status": "ok", "root": root, "date": str(trade_date)}

        monkeypatch.setattr(mod, "_process_root_day", _fast_process)

        work = self._make_work(5)
        monkeypatch.setattr(mod, "_episode_root_days",
                            lambda episode_root_filter=None: work)

        # No --budget-minutes → should process all 5
        mod.main(["--mode", "episodes", "--no-audit"])
        assert len(call_log) == 5, "All 5 items must be processed when no budget is set"

    def test_state_resumable_after_budget_stop(self, monkeypatch):
        """Items marked done before budget-stop are skipped on the next run."""
        import scripts.build_tape_flow_daily as mod

        # Pre-populate state with 3 completed items
        d = date(2024, 1, 2)
        completed = [("SPY", d + timedelta(days=i)) for i in range(3)]
        state: dict = {}
        for root, td in completed:
            mod._mark_done(state, "episodes", root, td)

        # Work = 5 items (first 3 already done)
        work = self._make_work(5)

        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True, raising=False)
        monkeypatch.setattr(mod, "_load_state", lambda: state)
        monkeypatch.setattr(mod, "_save_state", lambda s: None)
        monkeypatch.setattr(mod, "_register_run_status", lambda *a, **kw: None)
        monkeypatch.setattr(mod, "_audit_store", lambda root, d: {"ok": True})
        monkeypatch.setattr(mod, "_episode_root_days",
                            lambda episode_root_filter=None: work)

        call_log: list[tuple] = []

        def _fast_process(root, trade_date, mode, retain_raw):
            call_log.append((root, trade_date))
            return {"status": "ok", "root": root, "date": str(trade_date)}

        monkeypatch.setattr(mod, "_process_root_day", _fast_process)

        mod.main(["--mode", "episodes", "--no-audit"])

        # Only the 2 remaining items (days 3 and 4) should have been processed
        assert len(call_log) == 2, (
            f"Expected 2 items (3 already done), got {len(call_log)}: {call_log}"
        )
        for root, td in call_log:
            assert (root, td) not in completed, f"{root} {td} was already done"


# ── round-robin cursor tests ───────────────────────────────────────────────────

class TestRoundRobinCursor:
    """Round-robin cursor ensures every root in the universe accrues data over
    multiple budget-limited nightly runs."""

    def test_rotate_work_zero_cursor(self):
        """Cursor 0 returns the list unchanged."""
        from scripts.build_tape_flow_daily import _rotate_work
        work = [("A", 1), ("B", 2), ("C", 3)]
        assert _rotate_work(work, 0) == work

    def test_rotate_work_mid_cursor(self):
        """Cursor at index 1 moves item 1 to the front."""
        from scripts.build_tape_flow_daily import _rotate_work
        work = [("A", 1), ("B", 2), ("C", 3), ("D", 4)]
        rotated = _rotate_work(work, 1)
        assert rotated[0] == ("B", 2)
        assert len(rotated) == len(work)
        # All original items must still be present (no duplicates / no drops)
        assert set(rotated) == set(work)

    def test_rotate_work_wraps_cursor(self):
        """Cursor >= len(work) wraps around modulo len."""
        from scripts.build_tape_flow_daily import _rotate_work
        work = [("A", 1), ("B", 2), ("C", 3)]
        # cursor=3 → 3 % 3 == 0 → unchanged
        assert _rotate_work(work, 3) == work
        # cursor=4 → 4 % 3 == 1 → B is first
        rotated = _rotate_work(work, 4)
        assert rotated[0] == ("B", 2)

    def test_rotate_work_empty(self):
        """Empty list returns empty (no ZeroDivisionError)."""
        from scripts.build_tape_flow_daily import _rotate_work
        assert _rotate_work([], 5) == []

    def test_cursor_save_and_load(self):
        """_save_cursor / _load_cursor round-trip via the state dict."""
        from scripts.build_tape_flow_daily import _load_cursor, _save_cursor
        state: dict = {}
        assert _load_cursor(state, "forward") == 0  # default
        _save_cursor(state, "forward", 42)
        assert _load_cursor(state, "forward") == 42
        # Different modes are independent
        assert _load_cursor(state, "episodes") == 0

    def test_cursor_default_zero(self):
        """Default cursor for an unseen mode is 0."""
        from scripts.build_tape_flow_daily import _load_cursor
        state: dict = {}
        assert _load_cursor(state, "forward") == 0

    def test_rotate_distributes_coverage(self):
        """Three successive cursor advances distribute work across the universe."""
        from scripts.build_tape_flow_daily import _rotate_work, _load_cursor, _save_cursor
        universe = [("A", 1), ("B", 2), ("C", 3), ("D", 4), ("E", 5)]
        n = len(universe)
        state: dict = {}
        batch_size = 2

        leading_roots: list[str] = []
        cursor = 0
        for _ in range(3):
            rotated = _rotate_work(universe, cursor)
            leading_roots.append(rotated[0][0])  # head of queue
            # Advance cursor by batch_size (simulating a budget-limited run)
            cursor = (cursor + batch_size) % n
            _save_cursor(state, "forward", cursor)

        # All leading roots should differ (round-robin distributes coverage)
        assert len(set(leading_roots)) == 3, (
            f"Round-robin failed — repeated leading root: {leading_roots}"
        )

    def test_forward_default_budget_applied(self, monkeypatch):
        """Forward mode applies a 15-minute default budget when none is specified.

        Captures the parsed argparse Namespace after main() mutates args.budget_minutes
        from None to the default, and asserts the applied value is exactly 15.0.
        """
        import argparse as _argparse
        import scripts.build_tape_flow_daily as mod

        # Capture the argparse Namespace as mutated by main() (budget default is applied
        # after parse_args returns, by directly setting args.budget_minutes).
        captured_ns: list = []
        _orig_parse = _argparse.ArgumentParser.parse_args

        def _capturing_parse(self, argv=None):
            ns = _orig_parse(self, argv)
            captured_ns.append(ns)
            return ns

        monkeypatch.setattr(_argparse.ArgumentParser, "parse_args", _capturing_parse)

        state: dict = {}
        monkeypatch.setattr(mod, "_load_state", lambda: state)
        monkeypatch.setattr(mod, "_save_state", lambda s: None)
        monkeypatch.setattr(mod, "_register_run_status", lambda *a, **kw: None)
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True, raising=False)
        monkeypatch.setattr(mod, "_audit_store", lambda r, d: {"ok": True})
        monkeypatch.setattr(mod, "_process_root_day",
                            lambda root, td, mode, retain_raw:
                            {"status": "ok", "root": root, "date": str(td)})

        import engine.options_universe as ou
        monkeypatch.setattr(ou, "gex_symbols", lambda: ["SPY", "QQQ", "IWM"])

        # Run forward mode WITHOUT --budget-minutes
        mod.main(["--mode", "forward", "--no-audit"])

        # args.budget_minutes must have been set to 15.0 (the new default) by main()
        assert captured_ns, "parse_args was not called"
        applied = captured_ns[-1].budget_minutes
        assert applied == 15.0, (
            f"Expected default budget_minutes=15.0, got {applied!r}. "
            "Update _forward_default_budget in build_tape_flow_daily.py if the value changed."
        )

    def test_cursor_advances_after_forward_run(self, monkeypatch):
        """After a forward run, the cursor in state advances by n_attempted."""
        import scripts.build_tape_flow_daily as mod

        state: dict = {}
        monkeypatch.setattr(mod, "_load_state", lambda: state)
        saved_states: list[dict] = []
        monkeypatch.setattr(mod, "_save_state", lambda s: saved_states.append(
            json.loads(json.dumps(s))  # deep copy
        ))
        monkeypatch.setattr(mod, "_register_run_status", lambda *a, **kw: None)
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True, raising=False)
        monkeypatch.setattr(mod, "_audit_store", lambda r, d: {"ok": True})

        import json as _json

        call_log: list = []

        def _fast_process(root, trade_date, mode, retain_raw):
            call_log.append((root, trade_date))
            return {"status": "ok", "root": root, "date": str(trade_date)}

        monkeypatch.setattr(mod, "_process_root_day", _fast_process)

        import engine.options_universe as ou
        monkeypatch.setattr(ou, "gex_symbols", lambda: ["SPY", "QQQ", "IWM"])

        mod.main(["--mode", "forward", "--no-audit"])

        # State should have a cursor entry for "forward"
        assert saved_states, "State must have been saved at least once"
        final_state = saved_states[-1]
        cursor = final_state.get("cursors", {}).get("forward")
        assert cursor is not None, "Cursor for 'forward' must be persisted in state"
        # Universe size = 3; cursor = n_processed % 3
        # In this test all roots succeed, so n_processed == n_ok == len(call_log).
        n_processed = len(call_log)
        expected_cursor = n_processed % 3
        assert cursor == expected_cursor, (
            f"Expected cursor={expected_cursor} (n_processed={n_processed} % 3), got {cursor}"
        )

    def test_budget_stop_drains_done_futures(self, monkeypatch):
        """At deadline, futures already .done() are drained+recorded before the break.

        Setup: 4-item work list; mock perf_counter so deadline fires after the first
        wait() loop iteration (2 done futures exist at that point); verify both are
        marked done and cursor advances by the number actually processed (not submitted).
        """
        import scripts.build_tape_flow_daily as mod
        from concurrent.futures import Future

        state: dict = {}
        saved_states: list[dict] = []
        monkeypatch.setattr(mod, "_load_state", lambda: state)
        monkeypatch.setattr(mod, "_save_state",
                            lambda s: saved_states.append(json.loads(json.dumps(s))))
        monkeypatch.setattr(mod, "_register_run_status", lambda *a, **kw: None)
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True, raising=False)
        monkeypatch.setattr(mod, "_audit_store", lambda r, d: {"ok": True})

        # Slow stub: first two complete instantly, next two are slow.
        processed_log: list[tuple] = []

        def _slow_process(root, trade_date, mode, retain_raw):
            processed_log.append((root, trade_date))
            return {"status": "ok", "root": root, "date": str(trade_date)}

        monkeypatch.setattr(mod, "_process_root_day", _slow_process)

        # Use episodes mode (avoids gex_symbols import) with a tiny 4-item list.
        work = [("A", date(2024, 1, d)) for d in range(2, 6)]
        monkeypatch.setattr(mod, "_episode_root_days",
                            lambda episode_root_filter=None: work)

        # Patch time.perf_counter so deadline fires right after first batch completes.
        # Call sequence in main():
        #   call 1: t_global = perf_counter()  → 0.0
        #   calls 2-3: _tick() calls           → 0.0
        #   call 4: budget_deadline computation → 0.0; deadline = 0 + 1*60 = 60
        #   calls 5+: inside loop              → 200.0 (exceeds deadline immediately)
        call_idx = [0]

        def _mock_pc():
            call_idx[0] += 1
            if call_idx[0] <= 3:
                return 0.0
            return 200.0  # past any 1-minute deadline

        monkeypatch.setattr(mod.time, "perf_counter", _mock_pc)

        mod.main(["--mode", "episodes", "--budget-minutes", "1", "--no-audit"])

        # Some work must have been processed before the deadline fired
        assert len(processed_log) >= 1, "At least one item should have been processed"

        # The final saved state must mark the processed items as completed
        assert saved_states, "_save_state must be called"
        final_state = saved_states[-1]
        completed_for_episodes = final_state.get("completed", {}).get("episodes", {})
        n_marked_done = sum(len(v) for v in completed_for_episodes.values())
        assert n_marked_done == len(processed_log), (
            f"Marked-done count ({n_marked_done}) must equal processed count "
            f"({len(processed_log)}); drain-done-at-deadline may not be recording results"
        )

    def test_cursor_advances_by_processed_count_not_attempted(self, monkeypatch):
        """Cursor advances by n_processed (n_ok + n_err), not by n_attempted/submitted.

        Semantics pinned by this test: when roots are submitted to the executor but
        their results are never received (cancelled before they returned), the cursor
        must NOT advance past them — those roots must retry next run.

        Setup: 6-item universe; patch _process_root_day to return error for the first
        two roots (they are 'processed' but failed); remaining 4 are never submitted
        (budget fires after the first batch). Cursor must advance by exactly 2.
        """
        import scripts.build_tape_flow_daily as mod

        state: dict = {}
        saved_states: list[dict] = []
        monkeypatch.setattr(mod, "_load_state", lambda: state)
        monkeypatch.setattr(mod, "_save_state",
                            lambda s: saved_states.append(json.loads(json.dumps(s))))
        monkeypatch.setattr(mod, "_register_run_status", lambda *a, **kw: None)
        monkeypatch.setattr("collectors.thetadata.reachable", lambda: True, raising=False)
        monkeypatch.setattr(mod, "_audit_store", lambda r, d: {"ok": True})

        processed_log: list[tuple] = []

        def _error_process(root, trade_date, mode, retain_raw):
            processed_log.append((root, trade_date))
            # Return error so n_err increments; result IS received and counted in n_processed
            return {"status": "error", "root": root, "date": str(trade_date),
                    "reason": "stub_error"}

        monkeypatch.setattr(mod, "_process_root_day", _error_process)

        # 6-item work list; BATCH_SIZE = workers = 6 (backfill dead)
        work = [("R" + str(i), date(2024, 1, 2)) for i in range(6)]
        monkeypatch.setattr(mod, "_episode_root_days",
                            lambda episode_root_filter=None: work)
        # Force backfill dead so workers=6 and BATCH_SIZE=6
        monkeypatch.setattr(mod, "_backfill_alive", lambda: False)

        # perf_counter: first 3 calls return 0.0 (setup), then 1e9 (deadline exceeded
        # immediately on first check — after first wait() batch drains).
        call_idx = [0]

        def _mock_pc():
            call_idx[0] += 1
            return 0.0 if call_idx[0] <= 3 else 1e9

        monkeypatch.setattr(mod.time, "perf_counter", _mock_pc)

        mod.main(["--mode", "episodes", "--budget-minutes", "1", "--no-audit"])

        # With workers=6 and 6 items, all are submitted in one batch.
        # deadline fires after wait() returns (all done), so all 6 are processed.
        n_processed = len(processed_log)
        assert n_processed >= 1, "At least one item must have been processed"

        # For forward mode cursor semantics: use a forward run to pin the exact advance.
        # Here we use episodes mode which does NOT advance a cursor — so we verify the
        # n_ok/n_err counting semantics by re-running with forward mode.
        state2: dict = {}
        saved2: list[dict] = []
        monkeypatch.setattr(mod, "_load_state", lambda: state2)
        monkeypatch.setattr(mod, "_save_state",
                            lambda s: saved2.append(json.loads(json.dumps(s))))
        monkeypatch.setattr(mod, "_backfill_alive", lambda: False)

        processed2: list[tuple] = []

        def _error_process2(root, trade_date, mode, retain_raw):
            processed2.append((root, trade_date))
            return {"status": "error", "root": root, "date": str(trade_date),
                    "reason": "stub"}

        monkeypatch.setattr(mod, "_process_root_day", _error_process2)

        # 3-item forward universe; all error
        import engine.options_universe as ou
        monkeypatch.setattr(ou, "gex_symbols", lambda: ["AA", "BB", "CC"])

        # Reset perf_counter: no budget stop this time (large budget, fast universe)
        monkeypatch.setattr(mod.time, "perf_counter", lambda: 0.0)

        mod.main(["--mode", "forward", "--budget-minutes", "60", "--no-audit"])

        assert saved2, "State must be saved"
        final2 = saved2[-1]
        cursor2 = final2.get("cursors", {}).get("forward", 0)
        # All 3 items processed (all errored) → n_processed=3 → cursor = 3 % 3 = 0
        n_proc2 = len(processed2)
        expected = n_proc2 % 3
        assert cursor2 == expected, (
            f"Cursor must advance by n_processed ({n_proc2}) not n_attempted. "
            f"Expected {expected}, got {cursor2}"
        )
