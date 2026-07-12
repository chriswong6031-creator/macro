"""Fundamental Delivery Waterfall — pure computation core.

Program: Long-Hold Thesis lobe — LHB-W1 (A3 Delivery Waterfall).
Adjudication: research/LONG_HOLD_LOBE_BRAINSTORM_ADJUDICATION_BY_FABLE.md §LHB-R4.

DISPLAY-ONLY.  _display_only=True, horizon_role="hold_thesis".
This module MUST NOT feed board ordering, alert triage, top-setups gates,
or push floor (LHB-R4 / LH-R1 firewall).

For each Detector-D breakaway episode, decomposes the log price change from
episode onset t0 to as_of into fundamental-delivery legs vs a residual.
Zero statistics, zero scores, zero forecasts.  Refusal-first: any case that
cannot be cleanly decomposed returns status="refused" with raw components.

Two decomposition paths:
  pe_identity  — profitable path (revenue/op_income/ni all > 0 at BOTH endpoints)
  ev_revenue   — fallback when ni<=0 or op_income<=0 at either endpoint but
                 revenue > 0 and EV > 0 at both.

PIT convention (mirrors engine/moat_falsifiers._pit_filter, line 156):
  anchor row = max fy whose period_end + 120d <= t0.
  Rows with NULL/NaN period_end are EXCLUDED (unlike moat_falsifiers which keeps
  them fail-open; a null period_end is lookahead-unsafe for a dated endpoint).

Split guard (LHB-R4):
  If |shares_asof / shares_anchor - 1| > 0.20, both per-share and EV paths
  refuse.  EDGAR cover-page shares are stale after stock splits; the split store
  is a TODO (memory: edgar-shares-split-staleness); a large share-count move
  cannot be safely disambiguated from a split.

Scope-change guard (LHB-R4):
  If |dlog(revenue)| > ln(2.5) between the two endpoint rows, refuse the bars
  (acquisition / spin-off proxy) but still return raw components.

W3 LOCK (LHB-R4): no growth projections, no multi-year annualised return estimates,
no fair-value, no valuation percentile.  PR-N is W3-locked behind G1 retest.
"""
from __future__ import annotations

import logging
import math
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------
_REPORTING_LAG_DAYS: int = 120          # PIT gate: period_end + 120d
_MAX_PRICE_LAG_TD: int = 10             # trading-day window to find anchor/asof price
_SHARE_BASIS_BREAK_FRAC: float = 0.20  # >20% share-count change → refuse (split guard)
_SCOPE_CHANGE_LOG_THRESHOLD: float = math.log(2.5)  # |dlog(rev)| > ln(2.5) → scope change
_STALE_ANCHOR_DAYS: int = 400          # anchor > 400d before t0 → warning
_IDENTITY_TOLERANCE: float = 1e-9      # sum-of-legs must equal dlog(price) to this
_IDENTITY_NOISE_GUARD: float = 0.005   # float-noise guard: if |residual| > this → error

_SCHEMA: str = "delivery_waterfall.v1"
_VERSION: str = "v1"
_HORIZON_ROLE: str = "hold_thesis"


# ---------------------------------------------------------------------------
# Stamp helper (mirrors engine/winner_autopsy.stamp, line 94)
# ---------------------------------------------------------------------------

def stamp(obj: dict[str, Any]) -> dict[str, Any]:
    """Add display-only metadata keys to an artifact dict in-place. Returns obj."""
    obj["_display_only"] = True
    obj["_horizon_role"] = _HORIZON_ROLE
    obj["_version"] = _VERSION
    obj["_schema"] = _SCHEMA
    return obj


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _num(x: Any) -> float | None:
    """Coerce a scalar to float, returning None on null/NaN/non-numeric."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    try:
        v = float(x)
        return None if math.isnan(v) or math.isinf(v) else v
    except (TypeError, ValueError):
        return None


def _dlog(a: float, b: float) -> float | None:
    """Log-ratio dlog(b/a) = log(b) - log(a).  Returns None if either is non-positive."""
    if a is None or b is None or a <= 0.0 or b <= 0.0:
        return None
    return math.log(b) - math.log(a)


def _pct_from_dlog(dl: float | None) -> float | None:
    """Convert a log-point change to a percentage: (exp(dl) - 1) * 100."""
    if dl is None:
        return None
    return (math.exp(dl) - 1.0) * 100.0


def _last_close_on_or_before(
    close: pd.Series, cutoff: pd.Timestamp, max_lag_td: int = _MAX_PRICE_LAG_TD
) -> float | None:
    """Return the last close on or before cutoff within max_lag_td trading days.

    close must have a DatetimeIndex (tz-naive or tz-aware; tz is stripped before
    comparison).  Returns None if no qualifying row exists or if the most-recent
    bar precedes cutoff by more than max_lag_td business days.
    The max_lag_td guard prevents stale prices from ghosting a thin data period
    (e.g. a delisted ticker whose last bar is months or years before cutoff).
    """
    if close is None or close.empty:
        return None
    cutoff = pd.Timestamp(cutoff).normalize()
    # Strip tz from index to allow comparison with naive cutoff
    idx = close.index
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    sub = close[idx <= cutoff]
    if sub.empty:
        return None
    # Find the last bar on or before cutoff
    last_bar_date = sub.index[-1]
    last_bar_date_naive = last_bar_date
    if getattr(last_bar_date_naive, "tz", None) is not None:
        last_bar_date_naive = last_bar_date_naive.tz_localize(None)
    # Enforce the staleness bound: reject if the business-day gap between the
    # found bar and cutoff exceeds max_lag_td.  pd.bdate_range(a, b) includes
    # both endpoints; subtract 1 to get the number of trading days elapsed.
    bday_gap = len(pd.bdate_range(last_bar_date_naive, cutoff)) - 1
    if bday_gap > max_lag_td:
        return None
    val = sub.iloc[-1]
    v = _num(val)
    return v


def _pit_select_row(
    stmt_df: pd.DataFrame,
    cutoff: pd.Timestamp,
) -> dict | None:
    """Select the PIT-eligible statement row at cutoff.

    PIT rule: max fy among rows where to_datetime(period_end) + 120d <= cutoff.
    Rows with NULL/NaN period_end are EXCLUDED (lookahead-unsafe).

    Returns the row as a dict, or None if no eligible row exists.
    """
    if stmt_df is None or stmt_df.empty:
        return None
    df = stmt_df.copy()
    # Parse period_end
    if "period_end" not in df.columns:
        return None
    pe = pd.to_datetime(df["period_end"], errors="coerce")
    # Exclude rows where period_end is null (NaT) — lookahead-unsafe
    valid_mask = pe.notna()
    df = df[valid_mask]
    if df.empty:
        return None
    pe = pe[valid_mask]
    # PIT gate: period_end + 120d <= cutoff
    avail = pe + pd.Timedelta(days=_REPORTING_LAG_DAYS)
    eligible = avail <= cutoff
    df = df[eligible]
    if df.empty:
        return None
    # Pick max fy (or max period_end if fy absent or all-NaN)
    if "fy" in df.columns:
        fy_vals = pd.to_numeric(df["fy"], errors="coerce")
        if fy_vals.notna().any():
            best_idx = fy_vals.idxmax()
        else:
            # fy column present but every eligible row has NaN fy — fall back to
            # period_end.  Calling idxmax() on an all-NA Series raises ValueError
            # under pandas >=2.1; this guard is the explicit protection.
            best_idx = pe[eligible].idxmax()
    else:
        best_idx = pe[eligible].idxmax()
    row = df.loc[best_idx]
    return row.to_dict()


def _net_debt_from_row(row: dict) -> float | None:
    """net_debt = (debt_lt or 0) + (debt_cur or 0) - (cash or 0).

    Mirrors engine/stock_fundamentals._net_debt (line ~510).
    Returns None only when ALL three components are missing.
    """
    debt_lt = _num(row.get("debt_lt"))
    debt_cur = _num(row.get("debt_cur"))
    cash = _num(row.get("cash"))
    if debt_lt is None and debt_cur is None and cash is None:
        return None
    dl = debt_lt if debt_lt is not None else 0.0
    dc = debt_cur if debt_cur is not None else 0.0
    ca = cash if cash is not None else 0.0
    return dl + dc - ca


def _period_end_of_row(row: dict) -> pd.Timestamp | None:
    """Parse period_end from a row dict."""
    pe = row.get("period_end")
    if pe is None:
        return None
    try:
        ts = pd.to_datetime(pe)
        return ts if not pd.isna(ts) else None
    except Exception:  # noqa: BLE001
        return None


def _fy_of_row(row: dict) -> Any:
    """Return fy from a row dict, or None."""
    return row.get("fy")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_waterfall(
    ticker: str,
    t0: Any,
    close: pd.Series,
    stmt_rows: pd.DataFrame,
    as_of: Any = None,
) -> dict:
    """Decompose the log price change from episode onset t0 to as_of.

    Parameters
    ----------
    ticker:
        Ticker symbol (for labelling only).
    t0:
        Episode onset date (Detector-D onset).
    close:
        pd.Series of closes with DatetimeIndex.  Caller loads and passes this.
    stmt_rows:
        Ticker's rows from data/edgar/statements.parquet as a DataFrame.
        Caller loads and filters to this ticker; function performs PIT selection.
    as_of:
        Evaluation date; defaults to close.index[-1].

    Returns
    -------
    dict with keys: ticker, t0, as_of, path, status, refusal_reasons, warnings,
    dlog_price, legs, legs_pct, raw, anchor_lag_days, and stamp fields.
    """
    t0_ts = pd.Timestamp(t0).normalize()
    if as_of is None:
        as_of_ts = close.index[-1].normalize() if not close.empty else t0_ts
    else:
        as_of_ts = pd.Timestamp(as_of).normalize()

    refusal_reasons: list[str] = []
    warnings: list[str] = []

    # -----------------------------------------------------------------------
    # PIT endpoint selection
    # -----------------------------------------------------------------------
    anchor_row = _pit_select_row(stmt_rows, t0_ts)
    asof_row = _pit_select_row(stmt_rows, as_of_ts)

    if anchor_row is None:
        refusal_reasons.append("no_fundamentals_at_anchor")
    if asof_row is None:
        refusal_reasons.append("no_fundamentals_at_asof")

    # -----------------------------------------------------------------------
    # Price at endpoints
    # -----------------------------------------------------------------------
    price_t0 = _last_close_on_or_before(close, t0_ts)
    price_asof = _last_close_on_or_before(close, as_of_ts)

    if price_t0 is None:
        refusal_reasons.append("no_price_at_anchor")
    if price_asof is None:
        refusal_reasons.append("no_price_at_asof")

    # -----------------------------------------------------------------------
    # Assemble raw components (always populated for transparency)
    # -----------------------------------------------------------------------
    def _r(row: dict | None, key: str) -> float | None:
        if row is None:
            return None
        return _num(row.get(key))

    revenue_t0 = _r(anchor_row, "revenue")
    revenue_asof = _r(asof_row, "revenue")
    op_income_t0 = _r(anchor_row, "op_income")
    op_income_asof = _r(asof_row, "op_income")
    ni_t0 = _r(anchor_row, "ni")
    ni_asof = _r(asof_row, "ni")
    shares_t0 = _r(anchor_row, "shares")
    shares_asof = _r(asof_row, "shares")
    net_debt_t0 = _net_debt_from_row(anchor_row) if anchor_row is not None else None
    net_debt_asof = _net_debt_from_row(asof_row) if asof_row is not None else None
    fy_anchor = _fy_of_row(anchor_row) if anchor_row is not None else None
    fy_asof = _fy_of_row(asof_row) if asof_row is not None else None
    pe_anchor = _period_end_of_row(anchor_row) if anchor_row is not None else None
    pe_asof = _period_end_of_row(asof_row) if asof_row is not None else None

    raw: dict = {
        "price_t0": price_t0,
        "price_asof": price_asof,
        "revenue_t0": revenue_t0,
        "revenue_asof": revenue_asof,
        "op_income_t0": op_income_t0,
        "op_income_asof": op_income_asof,
        "ni_t0": ni_t0,
        "ni_asof": ni_asof,
        "shares_t0": shares_t0,
        "shares_asof": shares_asof,
        "net_debt_t0": net_debt_t0,
        "net_debt_asof": net_debt_asof,
        "fy_anchor": fy_anchor,
        "fy_asof": fy_asof,
        "period_end_anchor": pe_anchor.isoformat() if pe_anchor is not None else None,
        "period_end_asof": pe_asof.isoformat() if pe_asof is not None else None,
    }

    # -----------------------------------------------------------------------
    # Anchor lag (stale_anchor_fundamentals warning)
    # -----------------------------------------------------------------------
    anchor_lag_days: int | None = None
    if pe_anchor is not None:
        anchor_lag_days = (t0_ts - (pe_anchor + pd.Timedelta(days=_REPORTING_LAG_DAYS))).days
        if anchor_lag_days > _STALE_ANCHOR_DAYS:
            warnings.append("stale_anchor_fundamentals")

    # Both endpoints resolving to the SAME statement row means no filing has become
    # PIT-visible since onset: fundamental legs are exactly zero by construction and
    # the whole move sits in the residual. Flag it so the display can say "no filed
    # evidence yet" instead of implying "nothing earned".
    if (
        pe_anchor is not None
        and pe_asof is not None
        and pe_anchor == pe_asof
    ):
        warnings.append("no_new_filing_since_onset")

    # -----------------------------------------------------------------------
    # Revenue non-positive refusal
    # -----------------------------------------------------------------------
    if revenue_t0 is not None and revenue_asof is not None:
        if revenue_t0 <= 0.0 or revenue_asof <= 0.0:
            refusal_reasons.append("nonpositive_revenue")

    # Early exit skeleton on hard missing data (prices + fundaments)
    # We still need to check share_basis_break and scope_change.

    # -----------------------------------------------------------------------
    # Share-basis-break guard (LHB-R4 split guard)
    # -----------------------------------------------------------------------
    if (
        shares_t0 is not None
        and shares_asof is not None
        and shares_t0 > 0.0
        and shares_asof > 0.0
    ):
        share_change_frac = abs(shares_asof / shares_t0 - 1.0)
        if share_change_frac > _SHARE_BASIS_BREAK_FRAC:
            refusal_reasons.append("share_basis_break")

    # -----------------------------------------------------------------------
    # Scope-change guard (LHB-R4 acquisition/spin-off proxy)
    # -----------------------------------------------------------------------
    dlog_revenue: float | None = None
    if revenue_t0 is not None and revenue_asof is not None and revenue_t0 > 0.0 and revenue_asof > 0.0:
        dlog_revenue = _dlog(revenue_t0, revenue_asof)
    if dlog_revenue is not None and abs(dlog_revenue) > _SCOPE_CHANGE_LOG_THRESHOLD:
        refusal_reasons.append("scope_change_suspected")

    # -----------------------------------------------------------------------
    # If hard refusals at this point — return refused with raw
    # -----------------------------------------------------------------------
    dlog_price: float | None = None
    if price_t0 is not None and price_asof is not None and price_t0 > 0.0 and price_asof > 0.0:
        dlog_price = _dlog(price_t0, price_asof)

    if refusal_reasons:
        result: dict = {
            "ticker": ticker,
            "t0": t0_ts.date().isoformat(),
            "as_of": as_of_ts.date().isoformat(),
            "path": None,
            "status": "refused",
            "refusal_reasons": refusal_reasons,
            "warnings": warnings,
            "dlog_price": dlog_price,
            "legs": {},
            "legs_pct": {},
            "raw": raw,
            "anchor_lag_days": anchor_lag_days,
        }
        return stamp(result)

    # -----------------------------------------------------------------------
    # At this point: no refusal triggers, prices and fundamentals both present.
    # Choose the decomposition path.
    # -----------------------------------------------------------------------
    path: str
    legs: dict = {}
    legs_pct: dict = {}

    # Profitable path: all of revenue, op_income, ni, shares > 0 at BOTH endpoints.
    # revenue can be None (not just NaN->None) for financials — banks report
    # interest income, not us-gaap Revenues, so statements.parquet carries NaN.
    pe_path_ok = (
        revenue_t0 is not None
        and revenue_asof is not None
        and revenue_t0 > 0.0
        and revenue_asof > 0.0
        and op_income_t0 is not None
        and op_income_asof is not None
        and op_income_t0 > 0.0
        and op_income_asof > 0.0
        and ni_t0 is not None
        and ni_asof is not None
        and ni_t0 > 0.0
        and ni_asof > 0.0
        and shares_t0 is not None
        and shares_asof is not None
        and shares_t0 > 0.0
        and shares_asof > 0.0
    )

    if pe_path_ok:
        path = "pe_identity"
        # Exact multiplicative identity:
        # price = (revenue/shares) * (op_income/revenue) * (ni/op_income) * (price*shares/ni)
        # log-legs:
        rev_ps_t0 = revenue_t0 / shares_t0
        rev_ps_asof = revenue_asof / shares_asof
        dl_rev_ps = _dlog(rev_ps_t0, rev_ps_asof)

        op_margin_t0 = op_income_t0 / revenue_t0
        op_margin_asof = op_income_asof / revenue_asof
        dl_margin = _dlog(op_margin_t0, op_margin_asof)

        btl_t0 = ni_t0 / op_income_t0
        btl_asof = ni_asof / op_income_asof
        dl_btl = _dlog(btl_t0, btl_asof)

        # valuation/mix/accounting residual = dlog(price) - sum of fundamental legs
        # Equivalently: dlog(price*shares/ni)
        # We compute it algebraically to guarantee exact closure
        dl_sum_fundamental = dl_rev_ps + dl_margin + dl_btl
        dl_multiple = dlog_price - dl_sum_fundamental

        # Verify closure: sum must equal dlog_price to tolerance
        sum_check = dl_rev_ps + dl_margin + dl_btl + dl_multiple
        residual_check = abs(sum_check - dlog_price)
        if residual_check > _IDENTITY_TOLERANCE:
            # Should never fire — it is algebra
            warnings.append("identity_reconciliation_failed")

        # Noise-guard assert
        if residual_check > _IDENTITY_NOISE_GUARD:
            refusal_reasons_late = ["identity_reconciliation_failed"]
            result = {
                "ticker": ticker,
                "t0": t0_ts.date().isoformat(),
                "as_of": as_of_ts.date().isoformat(),
                "path": path,
                "status": "refused",
                "refusal_reasons": refusal_reasons_late,
                "warnings": warnings,
                "dlog_price": dlog_price,
                "legs": {},
                "legs_pct": {},
                "raw": raw,
                "anchor_lag_days": anchor_lag_days,
            }
            return stamp(result)

        legs = {
            "rev_ps_delivery": dl_rev_ps,
            "margin_delivery": dl_margin,
            "bottom_line_bridge": dl_btl,
            # Label: "valuation/mix/accounting residual" — never "sentiment"
            "valuation_mix_accounting_residual": dl_multiple,
        }
        legs_pct = {k: _pct_from_dlog(v) for k, v in legs.items()}

    else:
        # EV/revenue fallback path
        # Requires: revenue > 0 and EV > 0 at both endpoints
        # EV = price * shares + net_debt
        if (
            price_t0 is not None
            and price_asof is not None
            and shares_t0 is not None
            and shares_asof is not None
            and shares_t0 > 0.0
            and shares_asof > 0.0
            and revenue_t0 is not None
            and revenue_asof is not None
            and revenue_t0 > 0.0
            and revenue_asof > 0.0
        ):
            mktcap_t0 = price_t0 * shares_t0
            mktcap_asof = price_asof * shares_asof
            nd_t0 = net_debt_t0 if net_debt_t0 is not None else 0.0
            nd_asof = net_debt_asof if net_debt_asof is not None else 0.0
            ev_t0 = mktcap_t0 + nd_t0
            ev_asof = mktcap_asof + nd_asof

            if ev_t0 > 0.0 and ev_asof > 0.0:
                path = "ev_revenue"
                dl_revenue = _dlog(revenue_t0, revenue_asof)
                dl_ev_multiple = _dlog(ev_t0 / revenue_t0, ev_asof / revenue_asof)

                legs = {
                    "revenue_delivery": dl_revenue,
                    # Label: "valuation/mix/accounting residual" — never "sentiment"
                    "ev_multiple_residual": dl_ev_multiple,
                }
                legs_pct = {k: _pct_from_dlog(v) for k, v in legs.items()}

                # Context fields (NOT legs — per spec)
                shares_change_pct = (shares_asof / shares_t0 - 1.0) * 100.0
                raw["shares_change_pct_context"] = shares_change_pct
                raw["net_debt_change_context"] = (
                    (nd_asof - nd_t0) if net_debt_t0 is not None and net_debt_asof is not None else None
                )
                raw["ev_t0"] = ev_t0
                raw["ev_asof"] = ev_asof
            else:
                # EV path also failed — can't decompose
                refusal_reasons_ev = ["nonpositive_ev"]
                result = {
                    "ticker": ticker,
                    "t0": t0_ts.date().isoformat(),
                    "as_of": as_of_ts.date().isoformat(),
                    "path": None,
                    "status": "refused",
                    "refusal_reasons": refusal_reasons_ev,
                    "warnings": warnings,
                    "dlog_price": dlog_price,
                    "legs": {},
                    "legs_pct": {},
                    "raw": raw,
                    "anchor_lag_days": anchor_lag_days,
                }
                return stamp(result)
        else:
            # Distinguish the true cause of the EV-path precondition failure so
            # that by_refusal_reason breakdowns in the panel are honest.
            # The compound guard requires: prices non-None, shares non-None and
            # positive at both endpoints, revenue non-None and positive at both
            # endpoints.  Emit the most specific label that applies.
            if (
                shares_t0 is None or shares_asof is None
                or shares_t0 <= 0.0 or shares_asof <= 0.0
            ):
                refusal_reasons_ev = ["missing_shares_for_ev"]
            elif revenue_t0 is None or revenue_asof is None:
                # Absent tag (e.g. banks lack us-gaap Revenues) — missing, not nonpositive
                refusal_reasons_ev = ["missing_revenue"]
            else:
                refusal_reasons_ev = ["nonpositive_revenue"]
            result = {
                "ticker": ticker,
                "t0": t0_ts.date().isoformat(),
                "as_of": as_of_ts.date().isoformat(),
                "path": None,
                "status": "refused",
                "refusal_reasons": refusal_reasons_ev,
                "warnings": warnings,
                "dlog_price": dlog_price,
                "legs": {},
                "legs_pct": {},
                "raw": raw,
                "anchor_lag_days": anchor_lag_days,
            }
            return stamp(result)

    result = {
        "ticker": ticker,
        "t0": t0_ts.date().isoformat(),
        "as_of": as_of_ts.date().isoformat(),
        "path": path,
        "status": "ok",
        "refusal_reasons": [],
        "warnings": warnings,
        "dlog_price": dlog_price,
        "legs": legs,
        "legs_pct": legs_pct,
        "raw": raw,
        "anchor_lag_days": anchor_lag_days,
    }
    return stamp(result)
