"""engine/moat_falsifiers.py — Long-Hold Thesis Layer W2 PR-K: Moat Falsifier Sensors.

DISPLAY-ONLY — G1-DEFERRED ruling 2026-07-06.  horizon_role=hold_thesis.
These sensors MUST NOT feed board ordering, alert triage, top-setups gates,
or push floor.  No composite "moat score" is produced (LH-R2, Signal Commons R3).

Design contract (masterplan §4-W2 / rulings LH-R6, LH-R10)
-----------------------------------------------------------
Four falsifier sensors, each computed from ``data/edgar/statements.parquet``:

  1. margin_compression_despite_revenue_growth
     Gross margin declining YoY while revenue is still growing (at least 3% YoY).
     Classic moat-erosion signal: top-line intact, but pricing power or cost
     structure weakening.  Fire threshold: revenue_growth >= 3% AND
     gross_margin_pct latest < gross_margin_pct prior.

  2. receivables_stretch
     Accounts receivable growing materially faster than revenue.
     Consistent AR outpacing revenue → channel-stuffing / collection risk.
     Fire threshold: receivables_growth > revenue_growth + 10pp (percentage-
     points) AND revenue is positive.

  3. inventory_build
     Inventory growing materially faster than revenue.
     Persistent build signals demand softness or over-production.
     Fire threshold: inventory_growth > revenue_growth + 15pp AND
     revenue is positive (i.e. not purely a revenue-drop artefact).

  4. capital_intensity_rising
     Capex growing faster than revenue AND faster than operating income,
     indicating the business requires ever more capital to produce the
     same or less unit output.
     Fire threshold: capex_growth > revenue_growth + 10pp AND
     capex_growth > op_income_growth + 10pp.  Op_income sign-flip edge case
     handled: if op_income <= 0 the capex growth condition alone must hold.

For EACH sensor a matched-control base rate is computed:
  base_rate_annual — fraction of (ticker, fy) observations in the covered
  universe that satisfy the sensor condition in that fiscal year.
  This is the universe-level fire frequency; a sensor firing only when base_rate
  is near 1.0 is uninformative.  The base rate is printed in every result dict
  so callers can display it next to the firing flag.

Coverage stamps
---------------
Every result dict carries:
  _horizon_role   : "hold_thesis"
  _display_only   : True
  _version        : "v1"
  coverage_n_years: number of fiscal year rows found for the ticker
  sensor_coverage : "full" | "partial" | "missing"
    - full    : 2+ rows with all required columns non-null
    - partial : 1 row, or required column(s) missing in some rows
    - missing : no rows for the ticker

Great-company-trap overlay (LH-R10)
-------------------------------------
A plain deterministic function assembled ONLY from existing signals:
  crowding_z     (from engine.theme_crowding / basket-level)
  insider_net    (from engine.equity_factors / altdata: negative = net selling)
  revision_dir   (from engine.analyst_revisions: "downgrading" = bearish)

May only LOWER conviction display context, never raise it.  Inputs are printed.
Returns a dict with:
  trap_signals_present: bool
  de_escalation_reason: list[str]  (human-readable, each leg printed)
  inputs_used: dict  (printed for transparency — Article-1/A3 shaped)
  _horizon_role, _display_only, _version

Usage
-----
  from engine.moat_falsifiers import compute_moat_falsifiers, great_company_trap

  # per-ticker panel build
  result = compute_moat_falsifiers(ticker, statements_df)
  trap   = great_company_trap(
      crowding_z=crowding_z,
      insider_net_usd=insider_net,
      revision_direction=revision_dir,
  )

Standalone smoke-test::

  python -m engine.moat_falsifiers AAPL
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ── firewall constants ────────────────────────────────────────────────────────
_HORIZON_ROLE = "hold_thesis"
_DISPLAY_ONLY = True
_VERSION = "v1"

# ── sensor thresholds ─────────────────────────────────────────────────────────
# margin_compression_despite_revenue_growth
_MARGIN_MIN_REVENUE_GROWTH_PP = 3.0        # at least +3 pp revenue growth

# receivables_stretch
_RECV_STRETCH_PP = 10.0                    # AR growth > revenue growth + 10pp

# inventory_build
_INV_BUILD_PP = 15.0                       # inventory growth > revenue growth + 15pp

# capital_intensity_rising
_CAPEX_INTENSITY_PP = 10.0                 # capex growth > revenue growth + 10pp


# ── base-rate helpers ─────────────────────────────────────────────────────────

def _pct_change(new_val: float, old_val: float) -> float | None:
    """YoY % change (0-based, i.e. 10 = 10%), or None if old_val ≈ 0."""
    if old_val is None or pd.isna(old_val) or abs(old_val) < 1e-9:
        return None
    if new_val is None or pd.isna(new_val):
        return None
    return float((new_val - old_val) / abs(old_val) * 100.0)


def _margin_pct(gross_profit: float, revenue: float) -> float | None:
    if revenue is None or pd.isna(revenue) or abs(revenue) < 1e-9:
        return None
    if gross_profit is None or pd.isna(gross_profit):
        return None
    return float(gross_profit / revenue * 100.0)


# ── per-row sensor evaluators (returns True/False/None for one year-pair) ────

def _sensor_margin_compression(row_cur: pd.Series, row_prior: pd.Series) -> bool | None:
    rev_g = _pct_change(row_cur.get("revenue"), row_prior.get("revenue"))
    gm_cur = _margin_pct(row_cur.get("gross_profit"), row_cur.get("revenue"))
    gm_prior = _margin_pct(row_prior.get("gross_profit"), row_prior.get("revenue"))
    if rev_g is None or gm_cur is None or gm_prior is None:
        return None
    return bool(rev_g >= _MARGIN_MIN_REVENUE_GROWTH_PP and gm_cur < gm_prior)


def _sensor_receivables_stretch(row_cur: pd.Series, row_prior: pd.Series) -> bool | None:
    rev_g = _pct_change(row_cur.get("revenue"), row_prior.get("revenue"))
    recv_g = _pct_change(row_cur.get("receivables"), row_prior.get("receivables"))
    if rev_g is None or recv_g is None:
        return None
    rev_pos = (row_cur.get("revenue") or 0) > 0
    if not rev_pos:
        return None
    return bool(recv_g > rev_g + _RECV_STRETCH_PP)


def _sensor_inventory_build(row_cur: pd.Series, row_prior: pd.Series) -> bool | None:
    rev_g = _pct_change(row_cur.get("revenue"), row_prior.get("revenue"))
    inv_g = _pct_change(row_cur.get("inventory"), row_prior.get("inventory"))
    if rev_g is None or inv_g is None:
        return None
    rev_pos = (row_cur.get("revenue") or 0) > 0
    if not rev_pos:
        return None
    return bool(inv_g > rev_g + _INV_BUILD_PP)


def _sensor_capex_intensity(row_cur: pd.Series, row_prior: pd.Series) -> bool | None:
    rev_g = _pct_change(row_cur.get("revenue"), row_prior.get("revenue"))
    capex_g = _pct_change(row_cur.get("capex"), row_prior.get("capex"))
    if rev_g is None or capex_g is None:
        return None
    # capex should be positive (spending); negative capex = disposal proceeds,
    # which is the opposite direction — skip.
    if (row_cur.get("capex") or 0) <= 0:
        return None
    oi_cur = row_cur.get("op_income")
    oi_prior = row_prior.get("op_income")
    oi_g = _pct_change(oi_cur, oi_prior)
    # If op_income <= 0 we can't compute a meaningful margin delta; relax to
    # capex-vs-revenue only.
    if oi_g is None or (oi_cur is not None and not pd.isna(oi_cur) and float(oi_cur) <= 0):
        return bool(capex_g > rev_g + _CAPEX_INTENSITY_PP)
    return bool(capex_g > rev_g + _CAPEX_INTENSITY_PP and capex_g > oi_g + _CAPEX_INTENSITY_PP)


_SENSOR_FNS = {
    "margin_compression_despite_revenue_growth": _sensor_margin_compression,
    "receivables_stretch": _sensor_receivables_stretch,
    "inventory_build": _sensor_inventory_build,
    "capital_intensity_rising": _sensor_capex_intensity,
}


# ── base-rate computation ─────────────────────────────────────────────────────

def compute_base_rates(statements_df: pd.DataFrame) -> dict[str, dict[int, float]]:
    """Compute matched-control base rate for each sensor.

    Returns: {sensor_name: {fy: base_rate_fraction}} where base_rate is the
    fraction of (ticker, fy) observations that satisfy the sensor condition.
    Only fiscal years with >= 5 evaluable pairs are included.

    A sensor firing at base_rate ~0.5 fires half the universe — uninformative.
    A sensor firing at base_rate ~0.05 is selective and informative.
    """
    if statements_df is None or statements_df.empty:
        return {name: {} for name in _SENSOR_FNS}

    df = statements_df.copy()
    if "fy" not in df.columns or "ticker" not in df.columns:
        return {name: {} for name in _SENSOR_FNS}

    df = df.sort_values(["ticker", "fy"])
    base_rates: dict[str, dict[int, float]] = {name: {} for name in _SENSOR_FNS}

    # Build per-ticker year-pairs
    ticker_groups = df.groupby("ticker", sort=False)
    # Collect (sensor, fy, fired) triples
    records: list[tuple[str, int, bool]] = []

    for _ticker, grp in ticker_groups:
        grp = grp.sort_values("fy").reset_index(drop=True)
        for i in range(1, len(grp)):
            row_cur = grp.iloc[i]
            row_prior = grp.iloc[i - 1]
            fy = int(row_cur["fy"])
            for name, fn in _SENSOR_FNS.items():
                result = fn(row_cur, row_prior)
                if result is not None:
                    records.append((name, fy, bool(result)))

    if not records:
        return base_rates

    rec_df = pd.DataFrame(records, columns=["sensor", "fy", "fired"])
    for name, sub in rec_df.groupby("sensor"):
        by_fy = sub.groupby("fy")
        for fy, fy_rows in by_fy:
            n = len(fy_rows)
            if n >= 5:
                rate = float(fy_rows["fired"].mean())
                base_rates[name][int(fy)] = round(rate, 4)

    return base_rates


# ── per-ticker sensor evaluation ──────────────────────────────────────────────

def _assess_coverage(grp: pd.DataFrame, required_cols: list[str]) -> str:
    """Return 'full' | 'partial' | 'missing' for the ticker's data."""
    if grp is None or grp.empty:
        return "missing"
    if len(grp) < 2:
        return "partial"
    present = all(
        col in grp.columns and grp[col].dropna().shape[0] >= 2
        for col in required_cols
    )
    return "full" if present else "partial"


def _sensor_cols() -> dict[str, list[str]]:
    return {
        "margin_compression_despite_revenue_growth": ["revenue", "gross_profit"],
        "receivables_stretch": ["revenue", "receivables"],
        "inventory_build": ["revenue", "inventory"],
        "capital_intensity_rising": ["revenue", "capex", "op_income"],
    }


def compute_moat_falsifiers(
    ticker: str,
    statements_df: pd.DataFrame,
    base_rates: dict[str, dict[int, float]] | None = None,
    asof_date: str | None = None,
) -> dict[str, Any]:
    """Compute moat falsifier sensors for one ticker.

    Parameters
    ----------
    ticker:
        Ticker symbol.
    statements_df:
        The full ``data/edgar/statements.parquet`` frame (all tickers).
        Caller is responsible for loading it; this function is pure.
    base_rates:
        Pre-computed base rates from ``compute_base_rates()``.
        If None, base rates are omitted (no universe context).
        Pass the result of ``compute_base_rates(statements_df)`` for
        informative display.
    asof_date:
        Optional ISO date string for PIT awareness annotation only.

    Returns
    -------
    dict with keys:
      ticker, asof_date, coverage_n_years, sensor_coverage, sensors
      (each sensor: fired, fy_fired_on, base_rate_annual_fy, detail)
      _horizon_role, _display_only, _version
    """
    ticker = str(ticker).upper().strip()
    base_rates = base_rates or {}

    if statements_df is None or statements_df.empty:
        return _missing_result(ticker, asof_date, "statements_df empty or None")

    grp_all = statements_df[statements_df["ticker"] == ticker].sort_values("fy").reset_index(drop=True)
    if grp_all.empty:
        return _missing_result(ticker, asof_date, "ticker not in statements.parquet")

    n_years = len(grp_all)
    # Determine coverage using all sensors' required cols
    all_req_cols = sorted({c for cols in _sensor_cols().values() for c in cols})
    coverage_str = _assess_coverage(grp_all, all_req_cols)

    sensors: dict[str, Any] = {}
    for sensor_name, fn in _SENSOR_FNS.items():
        req_cols = _sensor_cols()[sensor_name]
        # find latest year-pair with non-null data
        fired = None
        fy_fired_on = None
        detail_rows = []

        for i in range(len(grp_all) - 1, 0, -1):
            row_cur = grp_all.iloc[i]
            row_prior = grp_all.iloc[i - 1]
            res = fn(row_cur, row_prior)
            fy_val = int(row_cur["fy"])
            detail_rows.append({
                "fy": fy_val,
                "result": res,
            })
            if res is not None and fired is None:
                # record the most-recent evaluable pair
                fired = bool(res)
                fy_fired_on = fy_val
            # stop after first evaluable pair (most recent)
            if res is not None:
                break

        # base rate for the fy_fired_on year if available
        sensor_base = base_rates.get(sensor_name, {})
        br_for_fy: float | None = None
        if fy_fired_on is not None:
            br_for_fy = sensor_base.get(fy_fired_on)
        # overall median base rate across years (summary)
        if sensor_base:
            br_values = list(sensor_base.values())
            br_median = float(round(float(pd.Series(br_values).median()), 4))
        else:
            br_median = None

        sensors[sensor_name] = {
            "fired": fired,                # True = sensor fires; False = does not; None = no data
            "fy_evaluated": fy_fired_on,   # FY year of evaluation
            "base_rate_annual_fy": br_for_fy,     # universe base rate for that FY
            "base_rate_median_all_years": br_median,  # median across all FY years
            "detail": detail_rows[:3],     # last 3 year-pairs for display
            "coverage": (
                "full" if (fy_fired_on is not None) else
                "partial" if (n_years >= 1) else
                "missing"
            ),
        }

    return {
        "ticker": ticker,
        "asof_date": asof_date,
        "coverage_n_years": n_years,
        "sensor_coverage": coverage_str,
        "sensors": sensors,
        "_horizon_role": _HORIZON_ROLE,
        "_display_only": _DISPLAY_ONLY,
        "_version": _VERSION,
    }


def _missing_result(ticker: str, asof_date: str | None, reason: str) -> dict[str, Any]:
    return {
        "ticker": ticker,
        "asof_date": asof_date,
        "coverage_n_years": 0,
        "sensor_coverage": "missing",
        "sensors": {name: {
            "fired": None, "fy_evaluated": None,
            "base_rate_annual_fy": None, "base_rate_median_all_years": None,
            "detail": [], "coverage": "missing",
        } for name in _SENSOR_FNS},
        "_horizon_role": _HORIZON_ROLE,
        "_display_only": _DISPLAY_ONLY,
        "_version": _VERSION,
        "_missing_reason": reason,
    }


# ── great-company-trap de-escalation overlay (LH-R10) ─────────────────────────

def great_company_trap(
    crowding_z: float | None = None,
    insider_net_usd: float | None = None,
    revision_direction: str | None = None,
    crowding_z_threshold: float = 1.5,
    insider_net_sell_threshold_usd: float = -500_000.0,
) -> dict[str, Any]:
    """Great-company-trap de-escalation overlay (LH-R10).

    ONLY LOWERS conviction display context, never raises it.  Assembled
    from existing signals only (crowding context, insider net USD, analyst
    revision direction).  Deterministic — no LLM, no model, no scores.

    Inputs are printed in the output for full transparency (Article-1/A3 shape).
    Callers must pass values sourced from the existing signal surfaces; this
    function performs no I/O.

    Parameters
    ----------
    crowding_z:
        Basket/theme-level crowding z-score from ``engine.theme_crowding``.
        Values >= crowding_z_threshold indicate elevated crowding.
        Pass None if unavailable.
    insider_net_usd:
        Net insider trading USD for the name from
        ``engine.altdata.insider_netflow`` or ``engine.equity_factors``.
        Negative = net selling.  Pass None if unavailable.
    revision_direction:
        "upgrading" | "stable" | "downgrading" from
        ``engine.analyst_revisions.revision_for()``.
        Pass None if unavailable.
    crowding_z_threshold:
        Z-score at or above which crowding is considered elevated.
        Default: 1.5 (basket_crowding.CROWDED_Z convention).
    insider_net_sell_threshold_usd:
        USD threshold below which insider net is considered meaningful selling.
        Default: -500,000.

    Returns
    -------
    dict:
        trap_signals_present: bool  — True if >= 1 de-escalation leg fires
        de_escalation_reason: list[str]  — human-readable fired legs
        legs: dict[str, dict]  — per-leg fired + value + threshold
        inputs_used: dict  — verbatim inputs passed (transparency)
        _horizon_role, _display_only, _version
    """
    de_esc_reasons: list[str] = []
    legs: dict[str, dict] = {}

    # Leg 1: crowding
    crowding_fired = False
    if crowding_z is not None:
        crowding_fired = float(crowding_z) >= float(crowding_z_threshold)
        if crowding_fired:
            de_esc_reasons.append(
                f"Elevated crowding (crowding_z={crowding_z:.2f} >= {crowding_z_threshold}): "
                "institutional positioning may be extended; exit can be disorderly."
            )
    legs["crowding"] = {
        "fired": crowding_fired,
        "value": crowding_z,
        "threshold": crowding_z_threshold,
        "available": crowding_z is not None,
    }

    # Leg 2: insider net selling
    insider_fired = False
    if insider_net_usd is not None:
        insider_fired = float(insider_net_usd) <= float(insider_net_sell_threshold_usd)
        if insider_fired:
            de_esc_reasons.append(
                f"Net insider selling (insider_net_usd={insider_net_usd:,.0f} "
                f"<= {insider_net_sell_threshold_usd:,.0f}): "
                "insiders are selling more than buying; thesis may be weakening."
            )
    legs["insider_net"] = {
        "fired": insider_fired,
        "value": insider_net_usd,
        "threshold": insider_net_sell_threshold_usd,
        "available": insider_net_usd is not None,
    }

    # Leg 3: analyst revision direction
    revision_fired = False
    if revision_direction is not None:
        revision_fired = str(revision_direction).lower() == "downgrading"
        if revision_fired:
            de_esc_reasons.append(
                f"Analyst consensus downgrading (revision_direction={revision_direction!r}): "
                "sell-side net-buy count declining; forward estimate momentum softening."
            )
    legs["revision_direction"] = {
        "fired": revision_fired,
        "value": revision_direction,
        "threshold": "downgrading",
        "available": revision_direction is not None,
    }

    trap_present = bool(de_esc_reasons)

    return {
        "trap_signals_present": trap_present,
        "de_escalation_reason": de_esc_reasons,
        "legs": legs,
        "inputs_used": {
            "crowding_z": crowding_z,
            "insider_net_usd": insider_net_usd,
            "revision_direction": revision_direction,
        },
        "_horizon_role": _HORIZON_ROLE,
        "_display_only": _DISPLAY_ONLY,
        "_version": _VERSION,
    }


# ── convenience: load and compute for a ticker ───────────────────────────────

def load_and_compute(
    ticker: str,
    statements_path: str | None = None,
    asof_date: str | None = None,
) -> tuple[dict[str, Any], dict[str, dict[int, float]]]:
    """Load statements.parquet, compute base rates, return per-ticker result.

    Returns (moat_result, base_rates).  Non-fatal: returns missing result on
    any I/O error.
    """
    from lib import config  # noqa: PLC0415  (deferred to keep module import-light)
    path = statements_path or str(config.data_dir() / "edgar" / "statements.parquet")
    try:
        df = pd.read_parquet(path)
    except Exception as exc:  # noqa: BLE001
        log.warning("moat_falsifiers: cannot load %s: %s", path, exc)
        return _missing_result(ticker, asof_date, f"load error: {exc}"), {}

    base_rates = compute_base_rates(df)
    result = compute_moat_falsifiers(ticker, df, base_rates=base_rates, asof_date=asof_date)
    return result, base_rates


# ── standalone CLI smoke-test ─────────────────────────────────────────────────

def main() -> int:
    import json, sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    result, base_rates = load_and_compute(ticker, asof_date=str(pd.Timestamp.now().date()))
    print(json.dumps(result, indent=2, default=str))
    print("\n--- base_rate_annual summary (median across FYs) ---")
    for sensor, rates in base_rates.items():
        if rates:
            vals = list(rates.values())
            med = float(pd.Series(vals).median())
            print(f"  {sensor}: median {med:.3f} over {len(rates)} FYs")
    # Demo great_company_trap
    trap = great_company_trap(crowding_z=1.8, insider_net_usd=-750_000, revision_direction="downgrading")
    print("\n--- great_company_trap demo ---")
    print(json.dumps(trap, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
