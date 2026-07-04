"""Government-funding exposure metrics — pure functions, zero I/O.

Two metrics:
  1. funding_to_mktcap(ticker, obligations, grants_loans, mktcap_map)
     → per-ticker trailing-12m federal award $ / market-cap with
       materiality bands and a theme roll-up helper.

  2. capex_burden(statements_rows)
     → FCF-trap / capex-burden dict for ONE ticker's multi-year XBRL
       series (capex/OCF, FCF trend, net-debt delta).

Evidence tier: fingerprint-class (annual XBRL lag) → score cap 60.
DISPLAY-ONLY; nothing here feeds any scored path.

Masterplan §2 Ruling R6 — evidence-class stamping required on every output.
Masterplan §2 Ruling R9 — on-page caveats:
  (a) recipient→ticker matching is curated-alias, lossy for subsidiaries.
  (e) mktcap denominator is price-live; award numerator is lagged.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

# ── materiality thresholds (chosen, not calibrated — see R6) ──────────────────
_PCT_NOTABLE = 2.0   # > 2% notable
_PCT_HEAVY   = 10.0  # > 10% heavy
_LAG_MONTHS  = 1     # drop most recent month (USAspending awards lag 1-2 months)
_TTM_MONTHS  = 12    # trailing-12m window


def funding_to_mktcap(
    ticker: str,
    obligations: pd.DataFrame,          # month × ticker  (data/usaspending/obligations.parquet)
    grants_loans: pd.DataFrame | None,  # month × ticker  (data/usaspending/grants_loans.parquet)
    mktcap_map: dict[str, float],       # {ticker: $ market cap (NOT $B)}
) -> dict[str, Any] | None:
    """Trailing-12m federal award $ / market cap for ONE ticker.

    Returns None when the ticker is absent from BOTH parquets or has no
    market cap.  Never raises; degrades gracefully on missing data.

    Returned dict:
        contracts_ttm   float | None  – TTM prime-contract awards $
        grants_ttm      float | None  – TTM grant/loan awards $
        total_ttm       float         – contracts + grants
        mktcap          float         – current market cap $
        ratio_pct       float         – total_ttm / mktcap * 100
        band            str           – "heavy" | "notable" | "minor"
        n_months        int           – actual months in the TTM window
        fy_basis        str           – "TTM (fingerprint-class, annual lag)"
        evidence_tier   str           – "fingerprint"
        score_cap       int           – 60
    """
    mc = mktcap_map.get(ticker)
    if not mc or mc <= 0:
        return None

    # ── contract awards ──────────────────────────────────────────────────────
    contracts_ttm: float | None = None
    n_months = 0
    if obligations is not None and not obligations.empty and ticker in obligations.columns:
        obs_sorted = obligations.sort_index()
        total_rows = len(obs_sorted)
        start = max(0, total_rows - _TTM_MONTHS - _LAG_MONTHS)
        end   = max(0, total_rows - _LAG_MONTHS)
        window = obs_sorted.iloc[start:end][ticker]
        if not window.empty:
            contracts_ttm = float(window.sum())
            n_months = int(window.notna().sum())

    # ── grant / loan awards ──────────────────────────────────────────────────
    grants_ttm: float | None = None
    if grants_loans is not None and not grants_loans.empty and ticker in grants_loans.columns:
        gl_sorted = grants_loans.sort_index()
        total_rows_gl = len(gl_sorted)
        start_gl = max(0, total_rows_gl - _TTM_MONTHS - _LAG_MONTHS)
        end_gl   = max(0, total_rows_gl - _LAG_MONTHS)
        gw = gl_sorted.iloc[start_gl:end_gl][ticker]
        if not gw.empty:
            grants_ttm = float(gw.sum())
            if n_months == 0:
                n_months = int(gw.notna().sum())

    # ── require at least one non-zero leg ────────────────────────────────────
    total_ttm = (contracts_ttm or 0.0) + (grants_ttm or 0.0)
    if total_ttm <= 0:
        return None

    ratio_pct = total_ttm / mc * 100.0
    if ratio_pct >= _PCT_HEAVY:
        band = "heavy"
    elif ratio_pct >= _PCT_NOTABLE:
        band = "notable"
    else:
        band = "minor"

    return {
        "contracts_ttm": round(contracts_ttm, 0) if contracts_ttm is not None else None,
        "grants_ttm":    round(grants_ttm, 0)    if grants_ttm    is not None else None,
        "total_ttm":     round(total_ttm, 0),
        "mktcap":        round(mc, 0),
        "ratio_pct":     round(ratio_pct, 2),
        "band":          band,
        "n_months":      n_months,
        "fy_basis":      "TTM (fingerprint-class, annual lag)",
        "evidence_tier": "fingerprint",
        "score_cap":     60,
    }


def funding_theme_roll(
    tickers: list[str],
    obligations: pd.DataFrame,
    grants_loans: pd.DataFrame | None,
    mktcap_map: dict[str, float],
) -> dict[str, Any] | None:
    """Roll per-ticker funding ratios up to a theme/basket.

    Returns None when fewer than 1 ticker has coverage.

    Returned dict:
        n_covered           int
        weighted_ratio_pct  float  – mktcap-weighted avg ratio
        max_ratio_pct       float
        max_ticker          str
        material_count      int    – tickers with ratio_pct >= _PCT_NOTABLE
        top                 list   – [{ticker, ratio_pct, band}]  top 3
        evidence_tier       str    – "fingerprint"
        score_cap           int    – 60
    """
    per_ticker: list[dict] = []
    for t in tickers:
        r = funding_to_mktcap(t, obligations, grants_loans, mktcap_map)
        if r is not None:
            r["ticker"] = t
            per_ticker.append(r)
    if not per_ticker:
        return None

    total_mc = sum(r["mktcap"] for r in per_ticker)
    weighted = (sum(r["ratio_pct"] * r["mktcap"] for r in per_ticker) / total_mc
                if total_mc > 0 else 0.0)
    best = max(per_ticker, key=lambda r: r["ratio_pct"])
    top3 = sorted(per_ticker, key=lambda r: r["ratio_pct"], reverse=True)[:3]

    return {
        "n_covered":          len(per_ticker),
        "weighted_ratio_pct": round(weighted, 2),
        "max_ratio_pct":      best["ratio_pct"],
        "max_ticker":         best["ticker"],
        "material_count":     sum(1 for r in per_ticker if r["ratio_pct"] >= _PCT_NOTABLE),
        "top":                [{"ticker": r["ticker"], "ratio_pct": r["ratio_pct"], "band": r["band"]}
                               for r in top3],
        "evidence_tier":      "fingerprint",
        "score_cap":          60,
    }


def capex_burden(
    statements_rows: list[dict[str, Any]],
    *,
    min_years: int = 3,
) -> dict[str, Any] | None:
    """Capex-burden / FCF-trap read for ONE ticker's multi-year XBRL series.

    Args:
        statements_rows: list of annual row dicts for ONE ticker, any order.
            Required keys: fy, cfo.  Optional: capex, debt_lt, debt_cur, cash.
        min_years: minimum annual rows with a non-null cfo before returning a result.

    Returns None when data is absent or insufficient (never returns 0 or a
    placeholder — callers must treat None as "no data", not "zero burden").

    Returned dict:
        capex_ocf_latest    float | None  – capex/OCF latest FY (%)
        capex_ocf_prior     float | None  – capex/OCF prior FY (%)
        capex_ocf_trend     str           – "rising" | "falling" | "flat"
        capex_yoy_pct       float | None  – capex YoY growth (%)
        fcf_latest_bn       float | None  – FCF latest FY ($B)
        fcf_trend           str           – "improving" | "deteriorating" | "flat"
        net_debt_delta_bn   float | None  – net-debt YoY change ($B; + = more debt)
        fcf_trap            bool          – capex_ocf > 80% AND fcf_latest < 0
        fy_latest           int
        evidence_tier       str           – "fingerprint"
        score_cap           int           – 60
    """
    if not statements_rows:
        return None

    def _f(row: dict, key: str) -> float | None:
        v = row.get(key)
        if v is None:
            return None
        try:
            fv = float(v)
        except (TypeError, ValueError):
            return None
        return fv if fv == fv else None   # reject NaN

    # keep rows with a valid cfo and a valid fy
    rows = [r for r in statements_rows
            if _f(r, "cfo") is not None and r.get("fy") is not None]
    if len(rows) < min_years:
        return None

    rows = sorted(rows, key=lambda r: int(r["fy"]))
    latest = rows[-1]
    prior  = rows[-2]

    # ── latest-FY ratios ──────────────────────────────────────────────────────
    capex_l = _f(latest, "capex")
    cfo_l   = _f(latest, "cfo")
    capex_p = _f(prior,  "capex")
    cfo_p   = _f(prior,  "cfo")

    capex_ocf_l = (capex_l / cfo_l * 100.0
                   if capex_l is not None and cfo_l and cfo_l > 0 else None)
    capex_ocf_p = (capex_p / cfo_p * 100.0
                   if capex_p is not None and cfo_p and cfo_p > 0 else None)
    capex_yoy   = ((capex_l / capex_p - 1.0) * 100.0
                   if capex_l is not None and capex_p and capex_p > 0 else None)

    # ── net-debt delta ────────────────────────────────────────────────────────
    def _net_debt(row: dict) -> float | None:
        dl = _f(row, "debt_lt")
        dc = _f(row, "debt_cur")
        ca = _f(row, "cash")
        if dl is None and dc is None:
            return None
        return (dl or 0.0) + (dc or 0.0) - (ca or 0.0)

    nd_l = _net_debt(latest)
    nd_p = _net_debt(prior)
    nd_delta = (nd_l - nd_p) if (nd_l is not None and nd_p is not None) else None

    # ── FCF trend ─────────────────────────────────────────────────────────────
    fcf_l = ((cfo_l - capex_l) if capex_l is not None else cfo_l)
    fcf_p = ((cfo_p - capex_p) if capex_p is not None else cfo_p)

    # ── qualitative labels ────────────────────────────────────────────────────
    if capex_ocf_l is not None and capex_ocf_p is not None:
        if   capex_ocf_l > capex_ocf_p + 3:  ocf_trend = "rising"
        elif capex_ocf_l < capex_ocf_p - 3:  ocf_trend = "falling"
        else:                                  ocf_trend = "flat"
    else:
        ocf_trend = "flat"

    if   fcf_l is not None and fcf_p is not None and fcf_l > fcf_p:  fcf_trend = "improving"
    elif fcf_l is not None and fcf_p is not None and fcf_l < fcf_p:  fcf_trend = "deteriorating"
    else:                                                               fcf_trend = "flat"

    fcf_trap = bool(
        capex_ocf_l is not None and capex_ocf_l > 80.0
        and fcf_l is not None and fcf_l < 0
    )

    return {
        "capex_ocf_latest":  round(capex_ocf_l, 1)      if capex_ocf_l  is not None else None,
        "capex_ocf_prior":   round(capex_ocf_p, 1)      if capex_ocf_p  is not None else None,
        "capex_ocf_trend":   ocf_trend,
        "capex_yoy_pct":     round(capex_yoy, 1)        if capex_yoy    is not None else None,
        "fcf_latest_bn":     round(fcf_l / 1e9, 2)      if fcf_l        is not None else None,
        "fcf_trend":         fcf_trend,
        "net_debt_delta_bn": round(nd_delta / 1e9, 2)   if nd_delta     is not None else None,
        "fcf_trap":          fcf_trap,
        "fy_latest":         int(latest["fy"]),
        "evidence_tier":     "fingerprint",
        "score_cap":         60,
    }


def spender_capex_burden(
    statements_df: pd.DataFrame,   # data/edgar/statements.parquet
    chain_key: str,                 # "ai_datacenter" | "housing"
) -> dict[str, dict[str, Any] | None]:
    """Capex burden for each SPENDER in a demand-chain cohort.

    Returns {ticker: capex_burden_result | None}.
    Tickers absent from statements_df → None (never 0).
    """
    from engine.demand_chain import CHAINS  # avoid circular at module level
    chain = next((c for c in CHAINS if c["key"] == chain_key), None)
    if chain is None:
        return {}

    out: dict[str, dict[str, Any] | None] = {}
    for aliases in chain["spenders"]:
        for ticker in aliases:
            sub = statements_df[statements_df["ticker"] == ticker]
            if not sub.empty:
                rows = sub.sort_values("fy").to_dict("records")
                out[ticker] = capex_burden(rows)
                break  # first alias with data wins
    return out
