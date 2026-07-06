"""engine/capital_allocation.py — LT-3a: Buyback-execution reader + capital_allocation_delta block.

DISPLAY-ONLY — horizon_role=hold_thesis.

This module reads buyback execution data from data/edgar/statements_quarterly.parquet
(the 'repurchases' column = PaymentsForRepurchaseOfCommonStock) and combines it with
share-count trends from data/edgar/fundamentals_panel.parquet and SBC from
data/edgar/statements.parquet to produce a per-ticker capital allocation picture.

FROZEN v1 display semantics (display conventions, NOT registered hypotheses)
---------------------------------------------------------------------------
All fields below are annotated _display_only=True, _horizon_role='hold_thesis'.
They MUST NOT feed board ordering, alert triage, top-setups gates, or push floor.

capital_allocation_delta:
  'accretive'   — shares_yoy_change <= -0.5% AND repurch_ttm > 0
                  (company is shrinking its share count and actively buying back)
  'dilutive'    — shares_yoy_change >= +3.0%
                  (matches the dilution_flag threshold in engine/stock_fundamentals.py)
  'neutral'     — all other cases where data is present
  'unavailable' — shares data missing

buyback_yield:
  repurch_ttm / mcap  (None if mcap unavailable)

net_buyback_after_sbc:
  (repurch_ttm - sbc_ttm) / mcap  (None if sbc unavailable — handles the LT-1 backfill
  landing or not landing gracefully)

share_count_reduction_confirmed:
  bool — shares_yoy_change <= -0.5%

debt_funded_buyback_flag:
  bool — repurch_ttm > 0 AND debt_lt latest > debt_lt prior FY
  (True if the company is buying back shares while long-term debt is rising)

Point-in-time gating (quarterly data)
--------------------------------------
Quarterly rows in statements_quarterly.parquet carry both period_end AND filed date.
Only rows where filed IS NOT NULL are used (PIT gate: a row is only visible once filed).
TTM = trailing 4 quarters with period_end in the last 12 months, counting only filed rows.
The PIT gate is strict: any quarter without a filed date is excluded — this matches the
task brief ("only rows with filed date present").

SBC handling
------------
SBC from statements.parquet is annual. As of 2026-07-06 coverage is ~0.2% (18/7781 rows —
only the LT-1 backfill tickers). A null/absent sbc_ttm is NOT treated as zero; all SBC-
dependent fields (net_buyback_after_sbc) are returned as None with a note explaining
'unavailable — SBC not in data'. This is the correct honest treatment: a missing value
cannot be treated as zero without asserting no SBC was awarded.

Coverage stamps
---------------
Every result dict carries:
  _horizon_role   : "hold_thesis"
  _display_only   : True
  _version        : "v1"
  repurch_coverage: "full" | "partial" | "missing"
    full    : >= 4 PIT-filed quarterly rows in trailing 12 months
    partial : 1-3 filed rows (TTM is partial sum)
    missing : no filed quarterly rows with repurchases column

Usage
-----
  from engine.capital_allocation import compute_capital_allocation

  result = compute_capital_allocation(
      ticker,
      quarterly_df,          # statements_quarterly.parquet (all tickers)
      fundamentals_panel_df, # fundamentals_panel.parquet (for shares, debt_lt)
      statements_df,         # statements.parquet (for sbc; may be None)
      mcap=mcap_usd,         # market cap in USD (from factors table); None → yield skipped
  )

Standalone smoke-test::

  python -m engine.capital_allocation AAPL
"""
from __future__ import annotations

import logging
import math
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ── firewall constants ────────────────────────────────────────────────────────
_HORIZON_ROLE = "hold_thesis"
_DISPLAY_ONLY = True
_VERSION = "v1"

# ── threshold constants (frozen v1 display semantics) ─────────────────────────
# capital_allocation_delta thresholds
_ACCRETIVE_SHARES_CHANGE_PCT = -0.5   # shares_yoy_change <= this AND repurch > 0
_DILUTIVE_SHARES_CHANGE_PCT = 3.0     # shares_yoy_change >= this (matches dilution_flag in stock_fundamentals)

# ── TTM window ────────────────────────────────────────────────────────────────
_TTM_QUARTERS = 4
_TTM_MONTHS = 12   # 12-month lookback for period_end cutoff


# ── helpers ──────────────────────────────────────────────────────────────────

def _num(x) -> float | None:
    """Coerce to a finite float, else None (NaN/inf/non-numeric → None)."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _pct_change(new_val: float | None, old_val: float | None) -> float | None:
    """YoY percent change (result in percentage points, e.g. 10.0 = +10%).
    Returns None if either value is None/zero."""
    if old_val is None or new_val is None:
        return None
    if abs(old_val) < 1e-3:  # avoid division by near-zero share counts
        return None
    return float((new_val - old_val) / abs(old_val) * 100.0)


# ── TTM repurchase computation ────────────────────────────────────────────────

def _compute_repurch_ttm(
    ticker: str,
    quarterly_df: pd.DataFrame,
    as_of_date: pd.Timestamp | None = None,
) -> tuple[float | None, str]:
    """Sum trailing 4 filed quarters of repurchases for one ticker.

    Parameters
    ----------
    ticker:
        Ticker symbol (case-insensitive).
    quarterly_df:
        Full statements_quarterly.parquet frame (all tickers). Must have columns:
        ticker, period_end, filed, repurchases.
    as_of_date:
        Point-in-time gate: only rows with filed <= as_of_date are visible.
        None → today (live display path).

    Returns
    -------
    (repurch_ttm, coverage)
        repurch_ttm: TTM sum in USD (float), or None if no data
        coverage: "full" | "partial" | "missing"
    """
    if quarterly_df is None or quarterly_df.empty:
        return None, "missing"
    if "repurchases" not in quarterly_df.columns or "filed" not in quarterly_df.columns:
        return None, "missing"

    asof = as_of_date if as_of_date is not None else pd.Timestamp.now().normalize()

    sub = quarterly_df[quarterly_df["ticker"].str.upper() == ticker.upper()].copy()
    if sub.empty:
        return None, "missing"

    # PIT gate: only rows with filed date present AND filed <= as_of_date
    sub = sub[sub["filed"].notna()]
    sub["_filed_ts"] = pd.to_datetime(sub["filed"], errors="coerce")
    sub["_period_end_ts"] = pd.to_datetime(sub["period_end"], errors="coerce")
    sub = sub[sub["_filed_ts"].notna()]
    sub = sub[sub["_filed_ts"] <= asof]

    if sub.empty:
        return None, "missing"

    # TTM window: period_end within the last 12 months from as_of
    ttm_start = asof - pd.DateOffset(months=_TTM_MONTHS)
    sub_ttm = sub[sub["_period_end_ts"] >= ttm_start]

    # Sort by period_end descending, take up to 4 most recent
    sub_ttm = sub_ttm.sort_values("_period_end_ts", ascending=False).head(_TTM_QUARTERS)

    if sub_ttm.empty:
        return None, "missing"

    # Only sum rows where repurchases is not null
    sub_rep = sub_ttm[sub_ttm["repurchases"].notna()]
    n_rep = len(sub_rep)

    if n_rep == 0:
        return None, "missing"

    repurch_ttm = float(sub_rep["repurchases"].sum())
    coverage = "full" if n_rep >= _TTM_QUARTERS else "partial"
    return repurch_ttm, coverage


# ── annual data helpers (shares, debt_lt, dividends) ─────────────────────────

def _get_latest_two_annual(
    ticker: str,
    fundamentals_panel_df: pd.DataFrame,
    as_of_date: pd.Timestamp | None = None,
) -> tuple[dict | None, dict | None]:
    """Return (latest_row, prior_row) from fundamentals_panel for one ticker.

    Rows are PIT-gated: asof_date (the panel's field stamped at build time) must
    be <= as_of_date (our gate). Returns (None, None) if insufficient data.
    """
    if fundamentals_panel_df is None or fundamentals_panel_df.empty:
        return None, None
    if "ticker" not in fundamentals_panel_df.columns or "fy" not in fundamentals_panel_df.columns:
        return None, None

    asof = as_of_date if as_of_date is not None else pd.Timestamp.now().normalize()

    sub = fundamentals_panel_df[fundamentals_panel_df["ticker"].str.upper() == ticker.upper()].copy()
    if sub.empty:
        return None, None

    # PIT gate via asof_date column: only rows available as of our gate date
    if "asof_date" in sub.columns:
        sub["_asof_ts"] = pd.to_datetime(sub["asof_date"], errors="coerce")
        sub = sub[sub["_asof_ts"].notna() & (sub["_asof_ts"] <= asof)]

    if sub.empty:
        return None, None

    sub = sub.sort_values("fy").reset_index(drop=True)
    if len(sub) < 2:
        # Only one row: can still compute some fields but no YoY
        latest = sub.iloc[-1].to_dict()
        return latest, None
    latest = sub.iloc[-1].to_dict()
    prior = sub.iloc[-2].to_dict()
    return latest, prior


# ── SBC from statements.parquet ───────────────────────────────────────────────

def _get_sbc_ttm(
    ticker: str,
    statements_df: pd.DataFrame | None,
    as_of_date: pd.Timestamp | None = None,
) -> float | None:
    """Get latest annual SBC from statements.parquet.

    SBC is an annual figure (from companyfacts). We return the latest available
    annual SBC as a proxy for the TTM figure. Returns None if unavailable —
    callers must treat None as 'unavailable', NOT as zero.

    Coverage is sparse (~18/7781 rows as of 2026-07-06) — the LT-1 backfill may
    or may not have landed; handle null gracefully.
    """
    if statements_df is None or statements_df.empty:
        return None
    if "sbc" not in statements_df.columns:
        return None
    if "ticker" not in statements_df.columns or "fy" not in statements_df.columns:
        return None

    asof = as_of_date if as_of_date is not None else pd.Timestamp.now().normalize()

    sub = statements_df[statements_df["ticker"].str.upper() == ticker.upper()].copy()
    if sub.empty:
        return None

    # PIT gate via period_end if available (same 120d lag logic as moat_falsifiers)
    if "period_end" in sub.columns:
        sub["_period_end_ts"] = pd.to_datetime(sub["period_end"], errors="coerce")
        _lag = pd.Timedelta(days=120)
        avail = sub["_period_end_ts"] + _lag
        # Keep rows where avail <= asof OR period_end is null (cannot gate)
        keep = avail.isna() | (avail <= asof)
        sub = sub[keep]

    if sub.empty:
        return None

    # Take latest row with non-null SBC
    sub_sbc = sub[sub["sbc"].notna()].sort_values("fy", ascending=False)
    if sub_sbc.empty:
        return None

    sbc_val = _num(sub_sbc.iloc[0]["sbc"])
    return sbc_val


# ── main computation ──────────────────────────────────────────────────────────

def compute_capital_allocation(
    ticker: str,
    quarterly_df: pd.DataFrame,
    fundamentals_panel_df: pd.DataFrame,
    statements_df: pd.DataFrame | None = None,
    mcap: float | None = None,
    as_of_date: str | None = None,
) -> dict[str, Any]:
    """Compute capital allocation display block for one ticker.

    Parameters
    ----------
    ticker:
        Ticker symbol.
    quarterly_df:
        Full data/edgar/statements_quarterly.parquet frame (all tickers).
        Must have columns: ticker, period_end, filed, repurchases.
    fundamentals_panel_df:
        Full data/edgar/fundamentals_panel.parquet frame (all tickers).
        Used for shares (shares_yoy_change), debt_lt, dividends.
    statements_df:
        data/edgar/statements.parquet frame. Used for sbc (annual).
        May be None — all SBC-dependent fields return None gracefully.
    mcap:
        Market cap in USD (float). Used for buyback_yield and
        net_buyback_after_sbc. Pass None if unavailable — yield fields
        are omitted.
    as_of_date:
        Point-in-time as-of date (ISO string). None → today (live display path).

    Returns
    -------
    dict with keys:
      ticker, as_of_date,
      repurch_ttm, sbc_ttm, repurch_coverage,
      capital_allocation_delta,
      buyback_yield, net_buyback_after_sbc,
      share_count_reduction_confirmed,
      shares_yoy_change_pct,
      debt_funded_buyback_flag,
      _horizon_role, _display_only, _version
    """
    ticker = str(ticker).upper().strip()
    asof_ts = _resolve_asof(as_of_date)

    # ── 1. TTM repurchases from quarterly data ────────────────────────────────
    repurch_ttm, repurch_coverage = _compute_repurch_ttm(ticker, quarterly_df, asof_ts)

    # ── 2. Annual data: shares, debt_lt from fundamentals_panel ──────────────
    latest_annual, prior_annual = _get_latest_two_annual(ticker, fundamentals_panel_df, asof_ts)

    shares_latest: float | None = None
    shares_prior: float | None = None
    debt_lt_latest: float | None = None
    debt_lt_prior: float | None = None
    dividends_latest: float | None = None

    if latest_annual:
        shares_latest = _num(latest_annual.get("shares"))
        debt_lt_latest = _num(latest_annual.get("debt_lt"))
        dividends_latest = _num(latest_annual.get("dividends"))
    if prior_annual:
        shares_prior = _num(prior_annual.get("shares"))
        debt_lt_prior = _num(prior_annual.get("debt_lt"))

    # ── 3. SBC from statements.parquet ───────────────────────────────────────
    sbc_ttm = _get_sbc_ttm(ticker, statements_df, asof_ts)
    sbc_available = sbc_ttm is not None

    # ── 4. Derived metrics ────────────────────────────────────────────────────

    # shares_yoy_change (%)
    shares_yoy_change_pct = _pct_change(shares_latest, shares_prior)

    # capital_allocation_delta
    capital_allocation_delta = _classify_delta(
        shares_yoy_change_pct=shares_yoy_change_pct,
        repurch_ttm=repurch_ttm,
    )

    # share_count_reduction_confirmed
    share_count_reduction_confirmed: bool | None = None
    if shares_yoy_change_pct is not None:
        share_count_reduction_confirmed = bool(shares_yoy_change_pct <= _ACCRETIVE_SHARES_CHANGE_PCT)

    # buyback_yield = repurch_ttm / mcap
    buyback_yield: float | None = None
    if repurch_ttm is not None and mcap and mcap > 0:
        buyback_yield = float(repurch_ttm / mcap)

    # net_buyback_after_sbc = (repurch_ttm - sbc_ttm) / mcap
    # None when sbc unavailable — must not treat missing as zero
    net_buyback_after_sbc: float | None = None
    net_buyback_after_sbc_note: str | None = None
    if not sbc_available:
        net_buyback_after_sbc_note = "unavailable — SBC not in data"
    elif repurch_ttm is not None and mcap and mcap > 0:
        net_buyback_after_sbc = float((repurch_ttm - sbc_ttm) / mcap)

    # debt_funded_buyback_flag
    debt_funded_buyback_flag: bool | None = None
    if repurch_ttm is not None and repurch_ttm > 0:
        if debt_lt_latest is not None and debt_lt_prior is not None:
            debt_funded_buyback_flag = bool(debt_lt_latest > debt_lt_prior)
        else:
            debt_funded_buyback_flag = None  # cannot determine without both data points

    # ── 5. Assemble result ────────────────────────────────────────────────────
    result: dict[str, Any] = {
        "ticker": ticker,
        "as_of_date": as_of_date,
        # raw inputs (for transparency)
        "repurch_ttm": repurch_ttm,
        "sbc_ttm": sbc_ttm,
        "repurch_coverage": repurch_coverage,
        "sbc_note": net_buyback_after_sbc_note,
        # display fields
        "capital_allocation_delta": capital_allocation_delta,
        "buyback_yield": buyback_yield,
        "net_buyback_after_sbc": net_buyback_after_sbc,
        "share_count_reduction_confirmed": share_count_reduction_confirmed,
        "shares_yoy_change_pct": shares_yoy_change_pct,
        "debt_funded_buyback_flag": debt_funded_buyback_flag,
        "dividends_latest": dividends_latest,
        # stamps
        "_horizon_role": _HORIZON_ROLE,
        "_display_only": _DISPLAY_ONLY,
        "_version": _VERSION,
    }

    # Remove None-valued non-critical keys to keep JSON lean
    # (keep capital_allocation_delta and stamps even when None)
    return result


def _classify_delta(
    shares_yoy_change_pct: float | None,
    repurch_ttm: float | None,
) -> str:
    """Apply the frozen v1 capital_allocation_delta classification rules.

    Returns one of: 'accretive' | 'dilutive' | 'neutral' | 'unavailable'.
    """
    if shares_yoy_change_pct is None:
        return "unavailable"
    # dilutive check first (threshold >= +3%)
    if shares_yoy_change_pct >= _DILUTIVE_SHARES_CHANGE_PCT:
        return "dilutive"
    # accretive: shares falling by >= 0.5% AND active buyback
    if shares_yoy_change_pct <= _ACCRETIVE_SHARES_CHANGE_PCT and repurch_ttm is not None and repurch_ttm > 0:
        return "accretive"
    return "neutral"


def _resolve_asof(as_of_date: str | None) -> pd.Timestamp:
    """Resolve the as-of instant for point-in-time gating.

    None → today; ISO date string → that date. Unparseable → today (fail-open).
    """
    if as_of_date is None:
        return pd.Timestamp.now().normalize()
    try:
        return pd.to_datetime(as_of_date).normalize()
    except Exception:  # noqa: BLE001
        return pd.Timestamp.now().normalize()


# ── convenience: load all inputs and compute for one ticker ──────────────────

def load_and_compute(
    ticker: str,
    quarterly_path: str | None = None,
    fundamentals_panel_path: str | None = None,
    statements_path: str | None = None,
    mcap: float | None = None,
    as_of_date: str | None = None,
) -> dict[str, Any]:
    """Load all required parquets and compute for one ticker. Non-fatal on I/O errors."""
    from lib import config  # noqa: PLC0415  (deferred to keep module import-light)

    q_path = quarterly_path or str(config.data_dir() / "edgar" / "statements_quarterly.parquet")
    fp_path = fundamentals_panel_path or str(config.data_dir() / "edgar" / "fundamentals_panel.parquet")
    s_path = statements_path or str(config.data_dir() / "edgar" / "statements.parquet")

    try:
        quarterly_df = pd.read_parquet(q_path)
    except Exception as exc:  # noqa: BLE001
        log.warning("capital_allocation: cannot load %s: %s", q_path, exc)
        quarterly_df = pd.DataFrame()

    try:
        fp_df = pd.read_parquet(fp_path)
    except Exception as exc:  # noqa: BLE001
        log.warning("capital_allocation: cannot load %s: %s", fp_path, exc)
        fp_df = pd.DataFrame()

    try:
        st_df = pd.read_parquet(s_path)
    except Exception as exc:  # noqa: BLE001
        log.warning("capital_allocation: cannot load %s: %s", s_path, exc)
        st_df = None

    return compute_capital_allocation(
        ticker,
        quarterly_df,
        fp_df,
        statements_df=st_df,
        mcap=mcap,
        as_of_date=as_of_date,
    )


# ── standalone CLI smoke-test ─────────────────────────────────────────────────

def main() -> int:
    import json
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    result = load_and_compute(ticker, as_of_date=str(pd.Timestamp.now().date()))
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
