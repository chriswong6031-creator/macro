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
