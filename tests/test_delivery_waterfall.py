"""Tests for engine/delivery_waterfall.py.

All tests are pure in-memory: synthetic pd.Series / DataFrames, bdate_range
index, no real data.  Mirrors tests/test_winner_autopsy.py style.

Coverage (per spec):
  (a) pe_identity path legs sum EXACTLY to dlog(price)
  (b) EV path routing when ni<0 at one endpoint
  (c) share_basis_break refusal at +25% share change; NON-refusal at +10%
  (d) scope_change_suspected on 3x revenue
  (e) PIT: a statement row with period_end 60 days before t0 is NOT eligible
      at t0 (120d lag) but IS eligible 120d later
  (f) null-period_end rows excluded from endpoint selection
  (g) no_price_at_anchor when close series starts after t0
  (h) stamps present (_display_only / _horizon_role / _version / _schema)
  (i) grep-level guard: module source contains neither "implied" nor "cagr"
      (case-insensitive)
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Path bootstrap
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import engine.delivery_waterfall as dw

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_close(
    start: str = "2020-01-02",
    periods: int = 500,
    prices: list[float] | None = None,
) -> pd.Series:
    """Build a synthetic daily close Series with a DatetimeIndex."""
    idx = pd.bdate_range(start=start, periods=periods)
    if prices is not None:
        data = prices + [prices[-1]] * (len(idx) - len(prices))
        data = data[: len(idx)]
    else:
        data = [100.0] * len(idx)
    return pd.Series(data, index=idx, dtype=float)


def _make_stmt(
    fy: int,
    period_end: str | None,
    revenue: float,
    op_income: float,
    ni: float,
    shares: float,
    debt_lt: float = 0.0,
    cash: float = 0.0,
) -> dict:
    """Build a synthetic statement row dict."""
    return {
        "fy": fy,
        "period_end": period_end,
        "revenue": revenue,
        "op_income": op_income,
        "ni": ni,
        "shares": shares,
        "debt_lt": debt_lt,
        "debt_cur": 0.0,
        "cash": cash,
    }


def _df(*rows: dict) -> pd.DataFrame:
    return pd.DataFrame(list(rows))


# ---------------------------------------------------------------------------
# (a) pe_identity path: legs sum EXACTLY to dlog(price)
# ---------------------------------------------------------------------------

class TestPeIdentityPath:
    def test_legs_sum_to_dlog_price(self):
        """Exact algebra: sum of legs must equal dlog(price) to within 1e-9."""
        # anchor: fy=2021, period_end 2021-12-31, so +120d = 2022-04-30
        # asof: fy=2022, period_end 2022-12-31, so +120d = 2023-04-30
        t0 = pd.Timestamp("2022-06-01")   # after anchor's 120d gate
        as_of = pd.Timestamp("2023-06-01")  # after asof's 120d gate

        stmt = _df(
            _make_stmt(2021, "2021-12-31", revenue=1000, op_income=200, ni=100, shares=50),
            _make_stmt(2022, "2022-12-31", revenue=1200, op_income=240, ni=130, shares=52),
        )

        # prices: 150 at t0, 210 at as_of
        idx = pd.bdate_range("2022-01-03", periods=400)
        prices = [150.0] * 110 + [210.0] * 290  # approximate date positions
        close = pd.Series(prices[: len(idx)], index=idx, dtype=float)

        result = dw.compute_waterfall("TEST", t0, close, stmt, as_of=as_of)
        assert result["status"] == "ok", f"Expected ok, got: {result['refusal_reasons']}"
        assert result["path"] == "pe_identity"

        legs = result["legs"]
        total_legs = sum(legs.values())
        dlog_price = result["dlog_price"]
        assert dlog_price is not None
        assert abs(total_legs - dlog_price) < 1e-9, (
            f"Legs sum {total_legs} != dlog_price {dlog_price}"
        )

    def test_pe_path_legs_pinned_to_hand_computed_values(self):
        """Each pe-path leg must match independently hand-computed math.log values.

        This is a DISCRIMINATING test: a sign flip or wrong denominator in any
        leg produces a wrong value that cannot be absorbed by the residual
        (which is also independently pinned), so a broken leg will FAIL here.

        Formulas (per engine/delivery_waterfall.py lines 425-441):
          rev_ps_t0  = revenue_t0 / shares_t0  = 1000/50 = 20
          rev_ps_asof = revenue_asof / shares_asof = 1200/52 ~ 23.077
          dl_rev_ps = log(23.077/20)

          op_margin_t0  = op_income_t0 / revenue_t0  = 200/1000 = 0.20
          op_margin_asof = op_income_asof / revenue_asof = 240/1200 = 0.20
          dl_margin = log(0.20/0.20) = 0.0

          btl_t0  = ni_t0 / op_income_t0  = 100/200 = 0.50
          btl_asof = ni_asof / op_income_asof = 130/240 ~ 0.5417
          dl_btl = log(0.5417/0.50)

          dlog_price = log(210/150)
          dl_multiple = dlog_price - (dl_rev_ps + dl_margin + dl_btl)
        """
        import math
        t0 = pd.Timestamp("2022-06-01")
        as_of = pd.Timestamp("2023-06-01")
        stmt = _df(
            _make_stmt(2021, "2021-12-31", revenue=1000, op_income=200, ni=100, shares=50),
            _make_stmt(2022, "2022-12-31", revenue=1200, op_income=240, ni=130, shares=52),
        )
        # Exact prices: 150 on bdate 2022-06-01, 210 on bdate 2023-06-01
        idx = pd.bdate_range("2022-01-03", periods=400)
        # t0 = 2022-06-01 is bdate index 107 (0-based); as_of = 2023-06-01 is ~356
        prices = [150.0] * 110 + [210.0] * 290
        close = pd.Series(prices[: len(idx)], index=idx, dtype=float)

        result = dw.compute_waterfall("TEST", t0, close, stmt, as_of=as_of)
        assert result["status"] == "ok"
        legs = result["legs"]

        # Hand-computed expected values
        rev_ps_t0 = 1000.0 / 50.0        # 20.0
        rev_ps_asof = 1200.0 / 52.0      # ~23.0769...
        expected_rev_ps = math.log(rev_ps_asof / rev_ps_t0)

        op_m_t0 = 200.0 / 1000.0         # 0.20
        op_m_asof = 240.0 / 1200.0       # 0.20
        expected_margin = math.log(op_m_asof / op_m_t0)  # = 0.0

        btl_t0 = 100.0 / 200.0           # 0.50
        btl_asof = 130.0 / 240.0         # ~0.5417
        expected_btl = math.log(btl_asof / btl_t0)

        dlog_price = result["dlog_price"]
        expected_multiple = dlog_price - (expected_rev_ps + expected_margin + expected_btl)

        tol = 1e-9
        assert abs(legs["rev_ps_delivery"] - expected_rev_ps) < tol, (
            f"rev_ps_delivery {legs['rev_ps_delivery']:.12f} != expected {expected_rev_ps:.12f}"
        )
        assert abs(legs["margin_delivery"] - expected_margin) < tol, (
            f"margin_delivery {legs['margin_delivery']:.12f} != expected {expected_margin:.12f}"
        )
        assert abs(legs["bottom_line_bridge"] - expected_btl) < tol, (
            f"bottom_line_bridge {legs['bottom_line_bridge']:.12f} != expected {expected_btl:.12f}"
        )
        assert abs(legs["valuation_mix_accounting_residual"] - expected_multiple) < tol, (
            f"residual {legs['valuation_mix_accounting_residual']:.12f} != expected {expected_multiple:.12f}"
        )

    def test_all_four_legs_present(self):
        """pe_identity path must expose all four leg keys."""
        t0 = pd.Timestamp("2022-06-01")
        as_of = pd.Timestamp("2023-06-01")
        stmt = _df(
            _make_stmt(2021, "2021-12-31", 1000, 200, 100, 50),
            _make_stmt(2022, "2022-12-31", 1200, 240, 130, 52),
        )
        idx = pd.bdate_range("2022-01-03", periods=400)
        close = pd.Series([150.0] * len(idx), index=idx, dtype=float)
        result = dw.compute_waterfall("TEST", t0, close, stmt, as_of=as_of)
        assert result["status"] == "ok"
        legs = result["legs"]
        assert "rev_ps_delivery" in legs
        assert "margin_delivery" in legs
        assert "bottom_line_bridge" in legs
        assert "valuation_mix_accounting_residual" in legs

    def test_legs_pct_present_and_finite(self):
        """legs_pct keys mirror legs, values are finite floats."""
        t0 = pd.Timestamp("2022-06-01")
        as_of = pd.Timestamp("2023-06-01")
        stmt = _df(
            _make_stmt(2021, "2021-12-31", 1000, 200, 100, 50),
            _make_stmt(2022, "2022-12-31", 1300, 300, 150, 50),
        )
        idx = pd.bdate_range("2022-01-03", periods=400)
        close = pd.Series([100.0] * 200 + [130.0] * 200, index=idx, dtype=float)
        result = dw.compute_waterfall("TEST", t0, close, stmt, as_of=as_of)
        assert result["status"] == "ok"
        for k, v in result["legs_pct"].items():
            assert v is not None and math.isfinite(v), f"legs_pct[{k}] = {v}"


# ---------------------------------------------------------------------------
# (b) EV path routing when ni < 0 at one endpoint
# ---------------------------------------------------------------------------

class TestEvPath:
    def test_ev_path_when_ni_negative_at_anchor(self):
        """When ni < 0 at anchor, route to ev_revenue (not pe_identity)."""
        t0 = pd.Timestamp("2022-06-01")
        as_of = pd.Timestamp("2023-06-01")
        # ni=-50 at anchor (loss-maker), positive revenue and no large net_debt
        stmt = _df(
            _make_stmt(2021, "2021-12-31", revenue=500, op_income=-20, ni=-50, shares=100,
                       debt_lt=0, cash=0),
            _make_stmt(2022, "2022-12-31", revenue=600, op_income=30, ni=20, shares=100,
                       debt_lt=0, cash=0),
        )
        idx = pd.bdate_range("2022-01-03", periods=400)
        close = pd.Series([10.0] * 200 + [12.0] * 200, index=idx, dtype=float)
        result = dw.compute_waterfall("TEST", t0, close, stmt, as_of=as_of)
        # EV = price*shares (net_debt=0), both positive → ev_revenue path
        assert result["status"] == "ok", f"Got refusals: {result['refusal_reasons']}"
        assert result["path"] == "ev_revenue"
        assert "revenue_delivery" in result["legs"]
        assert "ev_multiple_residual" in result["legs"]

    def test_ev_path_has_two_legs(self):
        """EV path exposes exactly revenue_delivery and ev_multiple_residual."""
        t0 = pd.Timestamp("2022-06-01")
        as_of = pd.Timestamp("2023-06-01")
        stmt = _df(
            _make_stmt(2021, "2021-12-31", revenue=800, op_income=-5, ni=-30, shares=200),
            _make_stmt(2022, "2022-12-31", revenue=900, op_income=-2, ni=-10, shares=200),
        )
        idx = pd.bdate_range("2022-01-03", periods=400)
        close = pd.Series([5.0] * len(idx), index=idx, dtype=float)
        result = dw.compute_waterfall("TEST", t0, close, stmt, as_of=as_of)
        # EV = price*200 + 0; both positive
        assert result["status"] == "ok", f"Got: {result['refusal_reasons']}"
        assert result["path"] == "ev_revenue"
        assert set(result["legs"].keys()) == {"revenue_delivery", "ev_multiple_residual"}


# ---------------------------------------------------------------------------
# (c) share_basis_break refusal at +25%; NON-refusal at +10%
# ---------------------------------------------------------------------------

class TestShareBasisBreak:
    def _make_close_and_stmt(self, shares_asof: float) -> tuple:
        t0 = pd.Timestamp("2022-06-01")
        as_of = pd.Timestamp("2023-06-01")
        stmt = _df(
            _make_stmt(2021, "2021-12-31", 1000, 200, 100, shares=100),
            _make_stmt(2022, "2022-12-31", 1200, 240, 130, shares=shares_asof),
        )
        idx = pd.bdate_range("2022-01-03", periods=400)
        close = pd.Series([50.0] * len(idx), index=idx, dtype=float)
        return t0, as_of, stmt, close

    def test_refusal_at_25pct_share_change(self):
        """Share count +25% (100->125) triggers share_basis_break refusal."""
        t0, as_of, stmt, close = self._make_close_and_stmt(shares_asof=125.0)
        result = dw.compute_waterfall("TEST", t0, close, stmt, as_of=as_of)
        assert result["status"] == "refused"
        assert "share_basis_break" in result["refusal_reasons"]

    def test_non_refusal_at_10pct_share_change(self):
        """Share count +10% (100->110) does NOT trigger share_basis_break."""
        t0, as_of, stmt, close = self._make_close_and_stmt(shares_asof=110.0)
        result = dw.compute_waterfall("TEST", t0, close, stmt, as_of=as_of)
        assert "share_basis_break" not in result["refusal_reasons"]

    def test_share_basis_break_negative_direction(self):
        """Share count -25% (100->75) also triggers share_basis_break."""
        t0, as_of, stmt, close = self._make_close_and_stmt(shares_asof=75.0)
        result = dw.compute_waterfall("TEST", t0, close, stmt, as_of=as_of)
        assert result["status"] == "refused"
        assert "share_basis_break" in result["refusal_reasons"]


# ---------------------------------------------------------------------------
# (d) scope_change_suspected on 3x revenue
# ---------------------------------------------------------------------------

class TestScopeChange:
    def test_3x_revenue_triggers_scope_change(self):
        """Revenue tripling (1000->3000) triggers scope_change_suspected."""
        t0 = pd.Timestamp("2022-06-01")
        as_of = pd.Timestamp("2023-06-01")
        stmt = _df(
            _make_stmt(2021, "2021-12-31", revenue=1000, op_income=200, ni=100, shares=50),
            _make_stmt(2022, "2022-12-31", revenue=3000, op_income=600, ni=300, shares=50),
        )
        idx = pd.bdate_range("2022-01-03", periods=400)
        close = pd.Series([100.0] * len(idx), index=idx, dtype=float)
        result = dw.compute_waterfall("TEST", t0, close, stmt, as_of=as_of)
        assert result["status"] == "refused"
        assert "scope_change_suspected" in result["refusal_reasons"]

    def test_2x_revenue_does_not_trigger_scope_change(self):
        """Revenue doubling (1000->2000) does NOT trigger scope_change_suspected.

        ln(2.5) ≈ 0.916; ln(2.0) ≈ 0.693 < threshold.
        """
        t0 = pd.Timestamp("2022-06-01")
        as_of = pd.Timestamp("2023-06-01")
        stmt = _df(
            _make_stmt(2021, "2021-12-31", revenue=1000, op_income=200, ni=100, shares=50),
            _make_stmt(2022, "2022-12-31", revenue=2000, op_income=400, ni=200, shares=50),
        )
        idx = pd.bdate_range("2022-01-03", periods=400)
        close = pd.Series([100.0] * len(idx), index=idx, dtype=float)
        result = dw.compute_waterfall("TEST", t0, close, stmt, as_of=as_of)
        assert "scope_change_suspected" not in result.get("refusal_reasons", [])


# ---------------------------------------------------------------------------
# (e) PIT: period_end 60d before t0 is NOT eligible at t0 but IS 120d later
# ---------------------------------------------------------------------------

class TestPitEligibility:
    def test_row_60d_before_t0_not_eligible_at_t0(self):
        """A row with period_end 60d before t0 fails the 120d gate at t0.

        period_end = 2022-04-01, t0 = 2022-06-01.
        period_end + 120d = 2022-07-29 > t0 = 2022-06-01 → NOT eligible.
        """
        t0 = pd.Timestamp("2022-06-01")
        as_of = pd.Timestamp("2023-06-01")
        # Only one statement row with period_end 60d before t0
        stmt = _df(
            _make_stmt(2021, "2022-04-01", revenue=1000, op_income=200, ni=100, shares=50),
            # asof row: eligible at as_of
            _make_stmt(2022, "2022-12-31", revenue=1200, op_income=240, ni=130, shares=50),
        )
        idx = pd.bdate_range("2021-01-04", periods=600)
        close = pd.Series([100.0] * len(idx), index=idx, dtype=float)
        result = dw.compute_waterfall("TEST", t0, close, stmt, as_of=as_of)
        # At t0, the 2022-04-01 row is not eligible → no_fundamentals_at_anchor
        assert "no_fundamentals_at_anchor" in result["refusal_reasons"]

    def test_row_60d_before_t0_eligible_120d_later(self):
        """Same row becomes eligible when as_of is 120d after period_end + 120d.

        period_end = 2022-04-01, as_of = 2022-09-01.
        period_end + 120d = 2022-07-29 <= 2022-09-01 → eligible.
        """
        # Here we test the _pit_select_row helper directly
        from engine.delivery_waterfall import _pit_select_row
        row = _make_stmt(2021, "2022-04-01", 1000, 200, 100, 50)
        df = _df(row)
        cutoff = pd.Timestamp("2022-09-01")
        selected = _pit_select_row(df, cutoff)
        assert selected is not None, "Row should be eligible at cutoff 2022-09-01"
        assert float(selected["fy"]) == 2021.0


# ---------------------------------------------------------------------------
# (f) null-period_end rows excluded from endpoint selection
# ---------------------------------------------------------------------------

class TestNullPeriodEnd:
    def test_null_period_end_row_excluded(self):
        """Rows with period_end=None are excluded from PIT selection."""
        from engine.delivery_waterfall import _pit_select_row
        # One row with None period_end, one with a valid period_end but not eligible
        row_null = _make_stmt(2021, None, 1000, 200, 100, 50)
        row_valid = _make_stmt(2020, "2021-12-31", 900, 180, 90, 50)
        df = _df(row_null, row_valid)
        cutoff = pd.Timestamp("2022-06-01")
        # 2021-12-31 + 120d = 2022-04-30 <= 2022-06-01 → eligible
        selected = _pit_select_row(df, cutoff)
        assert selected is not None
        assert float(selected["fy"]) == 2020.0, "Only the non-null eligible row should be selected"

    def test_only_null_period_end_row_gives_none(self):
        """When ALL rows have null period_end, _pit_select_row returns None."""
        from engine.delivery_waterfall import _pit_select_row
        row_null = _make_stmt(2021, None, 1000, 200, 100, 50)
        df = _df(row_null)
        cutoff = pd.Timestamp("2022-06-01")
        selected = _pit_select_row(df, cutoff)
        assert selected is None

    def test_compute_waterfall_null_period_end_triggers_refusal(self):
        """compute_waterfall with only null-period_end rows refuses."""
        t0 = pd.Timestamp("2022-06-01")
        as_of = pd.Timestamp("2023-06-01")
        stmt = _df(_make_stmt(2021, None, 1000, 200, 100, 50))
        idx = pd.bdate_range("2022-01-03", periods=400)
        close = pd.Series([100.0] * len(idx), index=idx, dtype=float)
        result = dw.compute_waterfall("TEST", t0, close, stmt, as_of=as_of)
        assert result["status"] == "refused"
        assert "no_fundamentals_at_anchor" in result["refusal_reasons"]


# ---------------------------------------------------------------------------
# (g) no_price_at_anchor when close series starts after t0
# ---------------------------------------------------------------------------

class TestNoPriceAtAnchor:
    def test_close_starts_after_t0(self):
        """If close series starts after t0, no_price_at_anchor is triggered."""
        t0 = pd.Timestamp("2022-01-03")
        as_of = pd.Timestamp("2023-06-01")
        stmt = _df(
            _make_stmt(2020, "2020-12-31", 1000, 200, 100, 50),
            _make_stmt(2022, "2022-12-31", 1200, 240, 130, 50),
        )
        # Close series starts AFTER t0
        idx = pd.bdate_range("2022-06-01", periods=300)
        close = pd.Series([100.0] * len(idx), index=idx, dtype=float)
        result = dw.compute_waterfall("TEST", t0, close, stmt, as_of=as_of)
        assert "no_price_at_anchor" in result["refusal_reasons"]

    def test_empty_close_series_triggers_refusals(self):
        """Empty close series triggers no_price_at_anchor and no_price_at_asof."""
        t0 = pd.Timestamp("2022-06-01")
        as_of = pd.Timestamp("2023-06-01")
        stmt = _df(
            _make_stmt(2021, "2021-12-31", 1000, 200, 100, 50),
            _make_stmt(2022, "2022-12-31", 1200, 240, 130, 50),
        )
        close = pd.Series(dtype=float)
        result = dw.compute_waterfall("TEST", t0, close, stmt, as_of=as_of)
        assert "no_price_at_anchor" in result["refusal_reasons"]


# ---------------------------------------------------------------------------
# (h) stamps present on all results
# ---------------------------------------------------------------------------

class TestStamps:
    def _ok_result(self) -> dict:
        t0 = pd.Timestamp("2022-06-01")
        as_of = pd.Timestamp("2023-06-01")
        stmt = _df(
            _make_stmt(2021, "2021-12-31", 1000, 200, 100, 50),
            _make_stmt(2022, "2022-12-31", 1200, 240, 130, 50),
        )
        idx = pd.bdate_range("2022-01-03", periods=400)
        close = pd.Series([100.0] * len(idx), index=idx, dtype=float)
        return dw.compute_waterfall("TEST", t0, close, stmt, as_of=as_of)

    def _refused_result(self) -> dict:
        t0 = pd.Timestamp("2022-06-01")
        as_of = pd.Timestamp("2023-06-01")
        stmt = pd.DataFrame()
        close = pd.Series(dtype=float)
        return dw.compute_waterfall("TEST", t0, close, stmt, as_of=as_of)

    def test_stamps_on_ok_result(self):
        r = self._ok_result()
        assert r.get("_display_only") is True
        assert r.get("_horizon_role") == "hold_thesis"
        assert r.get("_version") == "v1"
        assert r.get("_schema") == "delivery_waterfall.v1"

    def test_stamps_on_refused_result(self):
        r = self._refused_result()
        assert r.get("_display_only") is True
        assert r.get("_horizon_role") == "hold_thesis"
        assert r.get("_version") == "v1"
        assert r.get("_schema") == "delivery_waterfall.v1"


# ---------------------------------------------------------------------------
# (i) grep-level guard: no "implied" or "cagr" in module source
# ---------------------------------------------------------------------------

class TestModuleSourceGuard:
    def test_no_implied_in_source(self):
        """Module source must not contain the word 'implied' (case-insensitive).

        LHB-R4 W3 lock: no growth projections or annualised estimates.
        """
        module_path = _REPO_ROOT / "engine" / "delivery_waterfall.py"
        source = module_path.read_text(encoding="utf-8")
        hits = [
            i for i, line in enumerate(source.splitlines(), 1)
            if "implied" in line.lower()
        ]
        assert not hits, (
            f"engine/delivery_waterfall.py contains 'implied' at lines {hits}. "
            "LHB-R4 W3 lock: no growth projections or annualised estimates."
        )

    def test_no_cagr_in_source(self):
        """Module source must not contain the word 'cagr' (case-insensitive).

        LHB-R4 W3 lock: no multi-year annualised return estimates.
        """
        module_path = _REPO_ROOT / "engine" / "delivery_waterfall.py"
        source = module_path.read_text(encoding="utf-8")
        hits = [
            i for i, line in enumerate(source.splitlines(), 1)
            if "cagr" in line.lower()
        ]
        assert not hits, (
            f"engine/delivery_waterfall.py contains 'cagr' at lines {hits}. "
            "LHB-R4 W3 lock: no multi-year annualised return estimates."
        )


# ---------------------------------------------------------------------------
# Additional edge-case tests
# ---------------------------------------------------------------------------

class TestStaleAnchorWarning:
    def test_stale_anchor_adds_warning_not_refusal(self):
        """anchor_lag_days > 400 adds stale_anchor_fundamentals to warnings, not refusals."""
        # anchor period_end + 120d = 2021-04-30. t0 = 2023-06-01. lag > 400d.
        t0 = pd.Timestamp("2023-06-01")
        as_of = pd.Timestamp("2023-09-01")
        stmt = _df(
            _make_stmt(2020, "2020-12-31", 1000, 200, 100, 50),  # eligible at t0 but stale
            _make_stmt(2023, "2023-04-30", 1200, 240, 130, 50),  # eligible at as_of
        )
        idx = pd.bdate_range("2022-01-03", periods=600)
        close = pd.Series([100.0] * len(idx), index=idx, dtype=float)
        result = dw.compute_waterfall("TEST", t0, close, stmt, as_of=as_of)
        # Not a refusal
        assert "stale_anchor_fundamentals" not in result.get("refusal_reasons", [])
        # But in warnings
        assert "stale_anchor_fundamentals" in result.get("warnings", [])


# ---------------------------------------------------------------------------
# Price-staleness bound (_last_close_on_or_before / _MAX_PRICE_LAG_TD)
# ---------------------------------------------------------------------------

class TestPriceStalenessGuard:
    """Verify the _MAX_PRICE_LAG_TD guard in _last_close_on_or_before.

    The guard must return None when the most-recent close bar predates the
    cutoff by more than _MAX_PRICE_LAG_TD trading-day observations, and must
    return the price when the bar is within the window.
    """

    def test_last_close_within_window_returns_price(self):
        """A close bar within _MAX_PRICE_LAG_TD bdays of cutoff is accepted."""
        from engine.delivery_waterfall import _last_close_on_or_before, _MAX_PRICE_LAG_TD
        last_bar_date = pd.Timestamp("2022-01-03")  # a Monday
        idx = pd.bdate_range(end=last_bar_date, periods=5)
        close = pd.Series([50.0] * len(idx), index=idx, dtype=float)
        # Cutoff = last_bar_date + (_MAX_PRICE_LAG_TD - 1) bdays → well within window
        cutoff = last_bar_date + pd.offsets.BDay(_MAX_PRICE_LAG_TD - 1)
        result = _last_close_on_or_before(close, cutoff)
        assert result == 50.0, f"Expected 50.0 within window, got {result}"

    def test_last_close_exactly_at_window_boundary_accepted(self):
        """A close bar exactly _MAX_PRICE_LAG_TD bdays before cutoff is still accepted."""
        from engine.delivery_waterfall import _last_close_on_or_before, _MAX_PRICE_LAG_TD
        last_bar_date = pd.Timestamp("2022-01-03")
        idx = pd.bdate_range(end=last_bar_date, periods=5)
        close = pd.Series([75.0] * len(idx), index=idx, dtype=float)
        # Exactly max_lag_td business days gap: boundary is inclusive
        cutoff = last_bar_date + pd.offsets.BDay(_MAX_PRICE_LAG_TD)
        result = _last_close_on_or_before(close, cutoff)
        assert result == 75.0, f"Expected 75.0 at boundary, got {result}"

    def test_last_close_one_over_window_returns_none(self):
        """A close bar _MAX_PRICE_LAG_TD+1 bdays before cutoff returns None."""
        from engine.delivery_waterfall import _last_close_on_or_before, _MAX_PRICE_LAG_TD
        last_bar_date = pd.Timestamp("2022-01-03")
        idx = pd.bdate_range(end=last_bar_date, periods=5)
        close = pd.Series([75.0] * len(idx), index=idx, dtype=float)
        # One bday over the limit
        cutoff = last_bar_date + pd.offsets.BDay(_MAX_PRICE_LAG_TD + 1)
        result = _last_close_on_or_before(close, cutoff)
        assert result is None, (
            f"Expected None for bar {_MAX_PRICE_LAG_TD+1} bdays before cutoff, got {result}"
        )

    def test_last_close_beyond_window_returns_none(self):
        """A close bar more than _MAX_PRICE_LAG_TD observations before cutoff returns None."""
        from engine.delivery_waterfall import _last_close_on_or_before, _MAX_PRICE_LAG_TD
        # Series ends at last_bar_date; cutoff is _MAX_PRICE_LAG_TD+5 bdays later.
        # Gap = _MAX_PRICE_LAG_TD+5 bday observations → exceeds window.
        last_bar_date = pd.Timestamp("2018-01-02")
        idx = pd.bdate_range(end=last_bar_date, periods=5)
        close = pd.Series([99.0] * len(idx), index=idx, dtype=float)
        cutoff = pd.Timestamp("2022-06-01")  # ~1100 bdays after last bar
        result = _last_close_on_or_before(close, cutoff)
        assert result is None, (
            f"Expected None for stale price ({last_bar_date} → {cutoff}), got {result}"
        )

    def test_staleness_guard_triggers_no_price_at_anchor(self):
        """Stale-price returns None → compute_waterfall emits no_price_at_anchor."""
        # Only one bar, 4 years before t0.  Guard must fire → refusal.
        t0 = pd.Timestamp("2022-06-01")
        as_of = pd.Timestamp("2023-06-01")
        stmt = _df(
            _make_stmt(2020, "2020-12-31", 1000, 200, 100, 50),
            _make_stmt(2022, "2022-12-31", 1200, 240, 130, 50),
        )
        old_bar_date = pd.Timestamp("2018-01-02")
        idx = pd.bdate_range(end=old_bar_date, periods=3)
        close = pd.Series([100.0] * len(idx), index=idx, dtype=float)
        result = dw.compute_waterfall("TEST", t0, close, stmt, as_of=as_of)
        assert "no_price_at_anchor" in result["refusal_reasons"], (
            f"Expected no_price_at_anchor; got {result['refusal_reasons']}"
        )

    def test_positive_control_guard_absent_would_return_price(self):
        """Positive control: without the guard, the stale bar WOULD be returned.

        This test directly calls _last_close_on_or_before with a 4-year-stale
        bar and confirms the current implementation returns None (guard fires),
        not 100.0 (which the old broken no-op guard would have returned).
        """
        from engine.delivery_waterfall import _last_close_on_or_before
        idx = pd.bdate_range("2018-01-02", periods=5)
        close = pd.Series([100.0] * 5, index=idx, dtype=float)
        cutoff = pd.Timestamp("2022-06-01")
        result = _last_close_on_or_before(close, cutoff)
        # If the guard were a no-op, result would be 100.0.
        # The fix must return None.
        assert result is None, (
            f"Staleness guard is still a no-op: got {result} instead of None"
        )


# ---------------------------------------------------------------------------
# All-NaN fy fallback in _pit_select_row
# ---------------------------------------------------------------------------

class TestAllNaNFyFallback:
    """Verify _pit_select_row falls back to period_end when fy column is all-NaN.

    Under pandas >=2.1, calling idxmax() on an all-NA Series raises ValueError.
    The fix must catch this and fall back to period_end selection.
    """

    def test_all_nan_fy_falls_back_to_period_end(self):
        """All-NaN fy column → select by period_end instead of raising."""
        import numpy as np
        from engine.delivery_waterfall import _pit_select_row
        rows = [
            {"fy": np.nan, "period_end": "2021-12-31", "revenue": 1000, "ni": 100, "shares": 50},
            {"fy": np.nan, "period_end": "2022-06-30", "revenue": 1200, "ni": 130, "shares": 52},
        ]
        df = pd.DataFrame(rows)
        # Both rows eligible at 2023-01-01 (period_end + 120d <= 2023-01-01)
        cutoff = pd.Timestamp("2023-01-01")
        selected = _pit_select_row(df, cutoff)
        assert selected is not None, "Expected a row; got None (likely ValueError raised)"
        # Should select the later period_end = 2022-06-30
        assert selected["period_end"] == "2022-06-30", (
            f"Expected period_end=2022-06-30, got {selected['period_end']}"
        )

    def test_all_nan_fy_compute_waterfall_does_not_raise(self):
        """compute_waterfall with all-NaN fy must not raise; must return a dict."""
        import numpy as np
        t0 = pd.Timestamp("2022-06-01")
        as_of = pd.Timestamp("2023-06-01")
        stmt = pd.DataFrame([
            {"fy": np.nan, "period_end": "2021-12-31", "revenue": 1000,
             "op_income": 200, "ni": 100, "shares": 50, "debt_lt": 0, "debt_cur": 0, "cash": 0},
            {"fy": np.nan, "period_end": "2022-12-31", "revenue": 1200,
             "op_income": 240, "ni": 130, "shares": 52, "debt_lt": 0, "debt_cur": 0, "cash": 0},
        ])
        idx = pd.bdate_range("2022-01-03", periods=400)
        close = pd.Series([150.0] * len(idx), index=idx, dtype=float)
        # Must not raise ValueError
        result = dw.compute_waterfall("TEST", t0, close, stmt, as_of=as_of)
        assert isinstance(result, dict), "Expected dict return, got exception"
        # With period_end fallback both rows eligible → should succeed
        assert result["status"] in ("ok", "refused"), f"Unexpected status: {result}"


# ---------------------------------------------------------------------------
# EV-path refusal reason accuracy
# ---------------------------------------------------------------------------

class TestEvRefusalReasonLabels:
    """Verify EV-path refusals emit accurate labels distinguishing missing shares
    from nonpositive revenue — so by_refusal_reason breakdowns are honest.
    """

    def _make_loss_maker_stmt(
        self, shares_asof: float | None = 100.0, revenue_asof: float = 600.0
    ) -> pd.DataFrame:
        """Anchor row has ni<0 to force EV path; asof row has configurable shares/rev."""
        return pd.DataFrame([
            {"fy": 2021, "period_end": "2021-12-31", "revenue": 500, "op_income": -20,
             "ni": -50, "shares": 100.0, "debt_lt": 0, "debt_cur": 0, "cash": 0},
            {"fy": 2022, "period_end": "2022-12-31", "revenue": revenue_asof,
             "op_income": 30, "ni": 20, "shares": shares_asof, "debt_lt": 0, "debt_cur": 0, "cash": 0},
        ])

    def _make_close(self) -> pd.Series:
        idx = pd.bdate_range("2022-01-03", periods=400)
        return pd.Series([10.0] * len(idx), index=idx, dtype=float)

    def test_missing_shares_emits_missing_shares_for_ev(self):
        """shares_asof=None with positive revenue → missing_shares_for_ev, not nonpositive_revenue."""
        t0 = pd.Timestamp("2022-06-01")
        as_of = pd.Timestamp("2023-06-01")
        stmt = self._make_loss_maker_stmt(shares_asof=None, revenue_asof=600.0)
        result = dw.compute_waterfall("TEST", t0, self._make_close(), stmt, as_of=as_of)
        assert result["status"] == "refused"
        assert "missing_shares_for_ev" in result["refusal_reasons"], (
            f"Expected missing_shares_for_ev; got {result['refusal_reasons']}"
        )
        assert "nonpositive_revenue" not in result["refusal_reasons"], (
            "nonpositive_revenue must not appear when revenue is positive and shares is the issue"
        )

    def test_nonpositive_revenue_emits_nonpositive_revenue(self):
        """revenue_asof<=0 with valid shares → nonpositive_revenue label preserved."""
        t0 = pd.Timestamp("2022-06-01")
        as_of = pd.Timestamp("2023-06-01")
        stmt = self._make_loss_maker_stmt(shares_asof=100.0, revenue_asof=-5.0)
        result = dw.compute_waterfall("TEST", t0, self._make_close(), stmt, as_of=as_of)
        assert result["status"] == "refused"
        assert "nonpositive_revenue" in result["refusal_reasons"], (
            f"Expected nonpositive_revenue; got {result['refusal_reasons']}"
        )

    def test_zero_shares_emits_missing_shares_for_ev(self):
        """shares_asof=0 → missing_shares_for_ev (zero shares cannot form EV)."""
        t0 = pd.Timestamp("2022-06-01")
        as_of = pd.Timestamp("2023-06-01")
        stmt = self._make_loss_maker_stmt(shares_asof=0.0, revenue_asof=600.0)
        result = dw.compute_waterfall("TEST", t0, self._make_close(), stmt, as_of=as_of)
        assert result["status"] == "refused"
        assert "missing_shares_for_ev" in result["refusal_reasons"], (
            f"Expected missing_shares_for_ev for zero shares; got {result['refusal_reasons']}"
        )

    def test_nan_revenue_refuses_missing_revenue_never_raises(self):
        """Bank pathology (WFC/VLY full-run crash): financials carry revenue=NaN in
        statements.parquet (no us-gaap Revenues tag). Must refuse with missing_revenue,
        never raise TypeError from a None comparison, and never label nonpositive.
        """
        t0 = pd.Timestamp("2022-06-01")
        as_of = pd.Timestamp("2023-06-01")
        stmt = pd.DataFrame([
            {"fy": 2021, "period_end": "2021-12-31", "revenue": float("nan"),
             "op_income": float("nan"), "ni": 50.0, "shares": 100.0,
             "debt_lt": 0, "debt_cur": 0, "cash": 0},
            {"fy": 2022, "period_end": "2022-12-31", "revenue": float("nan"),
             "op_income": float("nan"), "ni": 60.0, "shares": 100.0,
             "debt_lt": 0, "debt_cur": 0, "cash": 0},
        ])
        result = dw.compute_waterfall("TEST", t0, self._make_close(), stmt, as_of=as_of)
        assert result["status"] == "refused"
        assert "missing_revenue" in result["refusal_reasons"], (
            f"Expected missing_revenue; got {result['refusal_reasons']}"
        )
        assert "nonpositive_revenue" not in result["refusal_reasons"]


class TestNoNewFilingSinceOnset:
    def test_same_statement_row_at_both_endpoints_warns(self):
        """Fresh episode: anchor and as_of resolve to the same filed row → legs are
        zero by construction; the result must carry no_new_filing_since_onset so the
        display can say 'no filed evidence yet' instead of implying 'nothing earned'.
        """
        idx = pd.bdate_range("2023-01-02", periods=400)
        close = pd.Series([float(10 + i * 0.01) for i in range(len(idx))], index=idx)
        stmt = pd.DataFrame([
            {"fy": 2022, "period_end": "2022-12-31", "revenue": 1000.0,
             "op_income": 200.0, "ni": 150.0, "shares": 100.0,
             "debt_lt": 0, "debt_cur": 0, "cash": 0},
        ])
        t0 = pd.Timestamp("2023-06-01")
        as_of = pd.Timestamp("2023-09-01")
        result = dw.compute_waterfall("TEST", t0, close, stmt, as_of=as_of)
        assert result["status"] == "ok"
        assert "no_new_filing_since_onset" in result["warnings"]
        assert abs(result["legs"]["rev_ps_delivery"]) < 1e-12
        assert abs(result["legs"]["margin_delivery"]) < 1e-12
        assert abs(
            result["legs"]["valuation_mix_accounting_residual"] - result["dlog_price"]
        ) < 1e-9

    def test_distinct_rows_do_not_warn(self):
        """Two different filed rows at the endpoints → no spurious warning."""
        idx = pd.bdate_range("2022-01-03", periods=700)
        close = pd.Series([10.0] * len(idx), index=idx)
        stmt = pd.DataFrame([
            {"fy": 2021, "period_end": "2021-12-31", "revenue": 1000.0,
             "op_income": 200.0, "ni": 150.0, "shares": 100.0,
             "debt_lt": 0, "debt_cur": 0, "cash": 0},
            {"fy": 2022, "period_end": "2022-12-31", "revenue": 1100.0,
             "op_income": 220.0, "ni": 160.0, "shares": 100.0,
             "debt_lt": 0, "debt_cur": 0, "cash": 0},
        ])
        result = dw.compute_waterfall(
            "TEST", pd.Timestamp("2022-06-01"), close, stmt,
            as_of=pd.Timestamp("2024-06-01"),
        )
        assert result["status"] == "ok"
        assert "no_new_filing_since_onset" not in result["warnings"]


class TestRawAlwaysPresent:
    def test_raw_fields_present_on_refused(self):
        """raw dict is present even on refused results (transparency requirement)."""
        t0 = pd.Timestamp("2022-06-01")
        as_of = pd.Timestamp("2023-06-01")
        stmt = pd.DataFrame()
        close = pd.Series(dtype=float)
        result = dw.compute_waterfall("TEST", t0, close, stmt, as_of=as_of)
        assert "raw" in result
        assert isinstance(result["raw"], dict)


class TestDlogPricePresent:
    def test_dlog_price_in_ok_result(self):
        """dlog_price is a finite float in ok results."""
        t0 = pd.Timestamp("2022-06-01")
        as_of = pd.Timestamp("2023-06-01")
        stmt = _df(
            _make_stmt(2021, "2021-12-31", 1000, 200, 100, 50),
            _make_stmt(2022, "2022-12-31", 1200, 240, 130, 50),
        )
        idx = pd.bdate_range("2022-01-03", periods=400)
        close = pd.Series([100.0] * 200 + [130.0] * 200, index=idx, dtype=float)
        result = dw.compute_waterfall("TEST", t0, close, stmt, as_of=as_of)
        dp = result.get("dlog_price")
        assert dp is not None
        assert math.isfinite(dp)
        expected = math.log(130.0 / 100.0)
        assert abs(dp - expected) < 1e-6
