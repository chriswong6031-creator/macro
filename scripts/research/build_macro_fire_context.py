"""Entry-Stack Amendment 2 T1b — macro/positioning fire-context date panel builder.

Spec: research/ENTRY_STACK_EXPANSION_AMENDMENT2_BY_FABLE.md §B RUL-22/23/24/26.

OFF-PATH research script — NOT wired into the nightly pipeline.
Run manually to produce:
  data/research/macro_fire_context.parquet
  data/research/macro_fire_context_meta.json

Output: ONE row per trading date, ~2003-present (where all required series exist).
Studies join it onto fire tapes by date.

PIT DISCIPLINE (RUL-23) — per-column known_date documentation:
  vix / spy_dd126:  VIX close and SPY adj-close are known same-evening. Usable at
                    next-day fill under the harness T+1 fill convention. No extra
                    shift applied; basis=same_evening documented in meta.
  hy_oas:           FRED daily BAMLH0A0HYM2 publishes next business day → +1 bd shift.
  ofr_fsi:          OFR FSI publishes next business day (~2 bd lag per collector) →
                    +1 bd shift (conservative: treats as T+1 available).
  stlfsi4_vintage:  ALFRED-vintaged, realtime_start as known_date (as-of join). Local
                    vintage store holds 2022-11-11 onward (187 rows); earlier dates
                    are NaN. Stamped in meta with partial-coverage reason.
  pos_p1_naaim:     NAAIM weekly survey; publish date + 7 calendar days (matches the
                    existing 7-day forward-lag convention in naaim_overlay_phase0.py).
                    Forward-filled from the publish-lag date.
  pos_p2_cot:       COT publish on Friday (Tuesday as-of). Forward-filled from the
                    Friday publish date only. No additional lag beyond the published
                    date (the 3-day lag to Tuesday as-of is already embedded in the
                    data; the publish date IS the known_date per RUL-23).

Frozen thresholds (RUL-26, Amendment 2 §B — do not modify without amending):
  ofr_fsi_pctile_exp_threshold: 0.80
  hy_oas_pctile_exp_threshold:  0.80
  ofr_fsi_mom15_sign:           < 0   (turning down)
  hy_oas_roc21_sign:            < 0   (turning down)
  naaim_pctile_3y_threshold:    0.20  (≤ 0.20 = crowd de-risked)
  naaim_pctile_3y_window_wks:   156   (trailing 3y of weekly obs)
  cot_pctile_3y_threshold:      0.20  (≤ 0.20 = specs net-short)
  cot_pctile_3y_window_wks:     156   (trailing 3y of weekly obs, ~COT weekly)

Expanding-percentile contract: pctile at t is computed using only data up to and
including t. Full-sample percentile would be look-ahead; this file never computes one.

Usage:
    cd /path/to/repo
    python scripts/research/build_macro_fire_context.py
    python scripts/research/build_macro_fire_context.py --smoke    # 2003-2010 only
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Path bootstrap
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("build_macro_fire_context")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_DATA      = _REPO_ROOT / "data"
_OUT_PQ    = _DATA / "research" / "macro_fire_context.parquet"
_OUT_META  = _DATA / "research" / "macro_fire_context_meta.json"

# ---------------------------------------------------------------------------
# Frozen thresholds (RUL-26; matches Amendment 2 §B verbatim)
# ---------------------------------------------------------------------------
_FSI_HIGH_PCTILE   = 0.80   # M1: ofr_fsi_pctile_exp >= 0.80
_OAS_HIGH_PCTILE   = 0.80   # M2: hy_oas_pctile_exp >= 0.80
_FSI_MOM15_WIN     = 15     # M1: momentum window (trading days)
_OAS_ROC21_WIN     = 21     # M2: rate-of-change window (trading days)
_NAAIM_PCTILE_THR  = 0.20   # P1: ≤ 0.20 = de-risked crowd
_NAAIM_WIN_WKS     = 156    # P1: trailing 3y of weekly obs
_COT_PCTILE_THR    = 0.20   # P2: ≤ 0.20 = specs net-short
_COT_WIN_WKS       = 156    # P2: trailing 3y
_DEFINITION_VERSION = "v1"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _bday_calendar(start: str = "2002-01-01", end: str | None = None) -> pd.DatetimeIndex:
    end = end or pd.Timestamp.today().strftime("%Y-%m-%d")
    return pd.bdate_range(start, end)


def _expanding_pctile(s: pd.Series) -> pd.Series:
    """Expanding-window rank / (count).  pctile at t uses only [0..t]."""
    return s.expanding().rank(pct=True)


# ---------------------------------------------------------------------------
# Series loaders
# ---------------------------------------------------------------------------
def _load_vix() -> pd.Series:
    df = pd.read_parquet(_DATA / "fred" / "VIXCLS.parquet")
    s = df["vix_close"].dropna()
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def _load_spy_close() -> pd.Series:
    df = pd.read_parquet(_DATA / "yahoo" / "SPY.parquet")
    # `close` is dividend-adjusted (fine for drawdown calculation; per memory note)
    s = df["close"].dropna()
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def _load_hy_oas() -> pd.Series:
    df = pd.read_parquet(_DATA / "fred" / "BAMLH0A0HYM2.parquet")
    s = df["hy_oas"].dropna()
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def _load_ofr_fsi() -> pd.Series:
    df = pd.read_parquet(_DATA / "ofr_fsi" / "fsi.parquet")
    s = df["fsi"].dropna()
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def _load_stlfsi4_vintage() -> tuple[pd.Series, str]:
    """Load STLFSI4 from the ALFRED vintage store using pit.py as-of join.
    Returns (series, coverage_note). The series is indexed by realtime_start
    (known_date), then forward-filled onto the bday grid by the caller."""
    try:
        from collectors.fred import load_vintages
        vintages = load_vintages()
        if vintages is None or vintages.empty:
            return pd.Series(dtype=float), "vintage_store_empty"
        sub = vintages[vintages["series"] == "STLFSI4"].copy()
        if sub.empty:
            return pd.Series(dtype=float), "STLFSI4_not_in_vintage_store"
        # Collapse to one row per realtime_start (initial release per period)
        sub["realtime_start"] = pd.to_datetime(sub["realtime_start"])
        sub["value"] = pd.to_numeric(sub["value"], errors="coerce")
        sub = sub.dropna(subset=["realtime_start", "value"])
        s = (sub.sort_values(["realtime_start"])
               .drop_duplicates(subset="realtime_start", keep="last")
               .set_index("realtime_start")["value"]
               .sort_index())
        first = str(s.index.min().date())
        last = str(s.index.max().date())
        note = f"partial_vintage_available_{first}_to_{last}"
        return s, note
    except Exception as exc:  # noqa: BLE001
        return pd.Series(dtype=float), f"error_loading_vintage: {exc}"


def _load_naaim() -> pd.Series:
    df = pd.read_parquet(_DATA / "sentiment" / "naaim.parquet")
    s = df["naaim_exposure"].dropna()
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def _load_cot_combined() -> pd.Series:
    """Combined ES+NDX net spec positioning as a single series (sum of both)."""
    es = pd.read_parquet(_DATA / "cot" / "cot_es_spx.parquet")["net_spec"].dropna()
    ndx = pd.read_parquet(_DATA / "cot" / "cot_nasdaq.parquet")["net_spec"].dropna()
    es.index = pd.to_datetime(es.index)
    ndx.index = pd.to_datetime(ndx.index)
    # Align on common Friday dates; fill NDX gaps from ES calendar and vice versa
    combined = pd.concat([es.rename("es"), ndx.rename("ndx")], axis=1)
    combined["combined"] = combined["es"].fillna(0) + combined["ndx"].fillna(0)
    # Only keep rows where at least one has a value (not both NaN)
    mask = combined["es"].notna() | combined["ndx"].notna()
    return combined.loc[mask, "combined"].sort_index()


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------
def build(smoke: bool = False) -> pd.DataFrame:
    """Build the macro_fire_context panel. Returns the final DataFrame."""
    log.info("Building macro_fire_context panel (smoke=%s)", smoke)

    # -----------------------------------------------------------------------
    # Step 1: Business-day grid (anchor for all daily output)
    # -----------------------------------------------------------------------
    bdays = _bday_calendar("2002-01-01")
    if smoke:
        bdays = bdays[bdays <= pd.Timestamp("2010-12-31")]
    log.info("Business-day grid: %s to %s (%d days)", bdays[0].date(), bdays[-1].date(), len(bdays))

    # -----------------------------------------------------------------------
    # Step 2: VIX — same-evening, no shift
    # -----------------------------------------------------------------------
    log.info("Loading VIX...")
    vix_raw = _load_vix()
    vix = vix_raw.reindex(bdays).ffill()

    # -----------------------------------------------------------------------
    # Step 3: SPY 126-trading-day max drawdown (adj-close, no shift)
    #   spy_dd126 = adj_close / rolling_126td_max - 1  (≤ 0)
    # -----------------------------------------------------------------------
    log.info("Loading SPY...")
    spy_raw = _load_spy_close()
    spy_daily = spy_raw.reindex(bdays).ffill()
    spy_rolling_max = spy_daily.rolling(126, min_periods=1).max()
    spy_dd126 = spy_daily / spy_rolling_max - 1.0

    # -----------------------------------------------------------------------
    # Step 4: HY OAS — +1 business day shift (FRED daily publication lag)
    # -----------------------------------------------------------------------
    log.info("Loading HY OAS...")
    hy_raw = _load_hy_oas()
    # Shift: the value published on date d is known on d+1bd
    hy_shifted_index = hy_raw.index + pd.offsets.BDay(1)
    hy_shifted = pd.Series(hy_raw.values, index=hy_shifted_index)
    # Deduplicate after BDay shift (e.g. Friday+1bd → Monday may collide with another Monday)
    hy_shifted = hy_shifted[~hy_shifted.index.duplicated(keep="last")].sort_index()
    hy_oas = hy_shifted.reindex(bdays.union(hy_shifted.index)).ffill().reindex(bdays)

    # HY OAS derived features — compute pctile on the FULL shifted history
    # (pre-2002 included) to avoid early-sample bias, then reindex to bdays.
    hy_full_union = hy_shifted.reindex(bdays.union(hy_shifted.index)).ffill()
    hy_oas_roc21 = hy_oas.diff(_OAS_ROC21_WIN)
    hy_oas_pctile_exp = _expanding_pctile(hy_full_union).reindex(bdays)

    # M2 turn flag: pctile_exp >= 0.80 AND roc21 < 0
    macro_m2_oas_turn = (hy_oas_pctile_exp >= _OAS_HIGH_PCTILE) & (hy_oas_roc21 < 0)

    # -----------------------------------------------------------------------
    # Step 5: OFR FSI — +1 business day shift (next-day publication)
    # -----------------------------------------------------------------------
    log.info("Loading OFR FSI...")
    fsi_raw = _load_ofr_fsi()
    fsi_shifted_index = fsi_raw.index + pd.offsets.BDay(1)
    fsi_shifted = pd.Series(fsi_raw.values, index=fsi_shifted_index)
    fsi_shifted = fsi_shifted[~fsi_shifted.index.duplicated(keep="last")].sort_index()
    ofr_fsi = fsi_shifted.reindex(bdays.union(fsi_shifted.index)).ffill().reindex(bdays)

    # OFR FSI derived features — compute pctile on the FULL shifted history
    # (pre-2002 included) to avoid early-sample bias, then reindex to bdays.
    fsi_full_union = fsi_shifted.reindex(bdays.union(fsi_shifted.index)).ffill()
    ofr_fsi_pctile_exp = _expanding_pctile(fsi_full_union).reindex(bdays)
    ofr_fsi_mom15 = ofr_fsi.diff(_FSI_MOM15_WIN)

    # M1 turn flag: pctile_exp >= 0.80 AND mom15 < 0
    macro_m1_fsi_turn = (ofr_fsi_pctile_exp >= _FSI_HIGH_PCTILE) & (ofr_fsi_mom15 < 0)

    # -----------------------------------------------------------------------
    # Step 6: STLFSI4 vintage (ALFRED as-of join, partial from 2022-11-11)
    # -----------------------------------------------------------------------
    log.info("Loading STLFSI4 vintage...")
    stlfsi4_raw, stlfsi4_coverage_note = _load_stlfsi4_vintage()
    if stlfsi4_raw.empty:
        stlfsi4_vintage = pd.Series(np.nan, index=bdays, dtype=float)
        log.warning("STLFSI4 vintage not available: %s", stlfsi4_coverage_note)
    else:
        # Forward-fill the initial-release values (realtime_start-indexed) onto bday grid
        stlfsi4_vintage = (stlfsi4_raw
                           .reindex(bdays.union(stlfsi4_raw.index))
                           .ffill()
                           .reindex(bdays))

    # -----------------------------------------------------------------------
    # Step 7: NAAIM — publish date + 7 calendar days, forward-filled
    #   Convention matches naaim_overlay_phase0.py (lag_days=7).
    # -----------------------------------------------------------------------
    log.info("Loading NAAIM...")
    naaim_raw = _load_naaim()
    # Apply 7-day calendar lag: value published at index[t] is known at index[t]+7d
    naaim_lagged_index = naaim_raw.index + pd.Timedelta(days=7)
    naaim_lagged = pd.Series(naaim_raw.values, index=naaim_lagged_index)
    # Forward-fill onto the bday grid
    naaim_daily = (naaim_lagged
                   .reindex(bdays.union(naaim_lagged.index))
                   .ffill()
                   .reindex(bdays))

    # P1: trailing 3y (156 weekly obs) pctile ≤ 0.20 AND rising over 2 weeks
    # For the daily grid, we carry a "trailing 156-week rolling" of the weekly series
    # and then forward-fill. Work on the lagged weekly series (known-date indexed).
    naaim_lagged_sorted = naaim_lagged.sort_index()
    # Rolling 156-obs pctile on the weekly lagged series
    def _rolling_rank_pct(s: pd.Series, window: int) -> pd.Series:
        return s.rolling(window, min_periods=max(1, window // 2)).apply(
            lambda x: (x < x[-1]).sum() / (len(x) - 1) if len(x) > 1 else 0.5,
            raw=True
        )

    naaim_pctile_wk = _rolling_rank_pct(naaim_lagged_sorted, _NAAIM_WIN_WKS)
    # "Rising" = latest publish > publish 2 weeks prior (i.e., 2 weekly obs back)
    naaim_rising_wk = naaim_lagged_sorted > naaim_lagged_sorted.shift(2)
    # Combine flag on weekly series
    naaim_flag_wk = (naaim_pctile_wk <= _NAAIM_PCTILE_THR) & naaim_rising_wk

    # Forward-fill the binary flag onto the bday grid
    pos_p1_naaim_reset = (naaim_flag_wk
                          .reindex(bdays.union(naaim_flag_wk.index))
                          .ffill()
                          .reindex(bdays)
                          .fillna(False)
                          .astype(bool))

    # -----------------------------------------------------------------------
    # Step 8: COT combined ES+NDX — Friday publish, forward-fill only
    # -----------------------------------------------------------------------
    log.info("Loading COT...")
    cot_raw = _load_cot_combined()
    # COT publish date is Friday; as-of is Tuesday of the same week.
    # The date in the store IS the publish date (confirmed: data is Friday-indexed).
    # No additional lag: forward-fill from publish date per RUL-23.
    cot_daily = (cot_raw
                 .reindex(bdays.union(cot_raw.index))
                 .ffill()
                 .reindex(bdays))

    # P2: trailing 3y (156-wk rolling on the weekly COT series) pctile ≤ 0.20 + rising
    cot_pctile_wk = _rolling_rank_pct(cot_raw.sort_index(), _COT_WIN_WKS)
    cot_rising_wk = cot_raw.sort_index() > cot_raw.sort_index().shift(2)
    cot_flag_wk = (cot_pctile_wk <= _COT_PCTILE_THR) & cot_rising_wk

    pos_p2_cot_reset = (cot_flag_wk
                        .reindex(bdays.union(cot_flag_wk.index))
                        .ffill()
                        .reindex(bdays)
                        .fillna(False)
                        .astype(bool))

    # -----------------------------------------------------------------------
    # Step 9: Assemble the panel
    # -----------------------------------------------------------------------
    log.info("Assembling panel...")
    panel = pd.DataFrame({
        "vix":                  vix,
        "spy_dd126":            spy_dd126,
        "hy_oas":               hy_oas,
        "hy_oas_roc21":         hy_oas_roc21,
        "hy_oas_pctile_exp":    hy_oas_pctile_exp,
        "ofr_fsi":              ofr_fsi,
        "ofr_fsi_pctile_exp":   ofr_fsi_pctile_exp,
        "ofr_fsi_mom15":        ofr_fsi_mom15,
        "stlfsi4_vintage":      stlfsi4_vintage,
        "macro_m1_fsi_turn":    macro_m1_fsi_turn,
        "macro_m2_oas_turn":    macro_m2_oas_turn,
        "pos_p1_naaim_reset":   pos_p1_naaim_reset,
        "pos_p2_cot_reset":     pos_p2_cot_reset,
    }, index=bdays)

    # Trim to where at least VIX, HY OAS, OFR FSI, and SPY all have data
    core_mask = (panel["vix"].notna()
                 & panel["spy_dd126"].notna()
                 & panel["hy_oas"].notna()
                 & panel["ofr_fsi"].notna())
    panel = panel[core_mask].copy()
    log.info("Panel after core-series trim: %s to %s (%d rows)",
             panel.index.min().date(), panel.index.max().date(), len(panel))

    return panel


# ---------------------------------------------------------------------------
# Meta generation
# ---------------------------------------------------------------------------
def _build_meta(panel: pd.DataFrame, stlfsi4_coverage_note: str) -> dict:
    """Build the per-column meta with source_event_date, known_date, pit_basis
    triples per RUL-23, plus frozen thresholds and coverage summary."""

    def _cov(col: str) -> dict:
        s = panel[col]
        nn = int(s.notna().sum())
        tot = len(s)
        frac = round(nn / tot, 4) if tot else 0.0
        first = str(s.first_valid_index().date()) if nn else "n/a"
        last = str(s[s.notna()].index[-1].date()) if nn else "n/a"
        return {"non_null": nn, "total": tot, "coverage_frac": frac,
                "first_valid": first, "last_valid": last}

    def _flag_rate(col: str) -> float | None:
        if col not in panel.columns:
            return None
        s = panel[col].dropna()
        if len(s) == 0:
            return None
        return round(float(s.astype(bool).mean()), 4)

    return {
        "definition_version": _DEFINITION_VERSION,
        "generated_at": pd.Timestamp.now().isoformat()[:19],
        "date_span": {
            "start": str(panel.index.min().date()),
            "end": str(panel.index.max().date()),
            "total_rows": len(panel),
        },
        "pit_basis": {
            "vix": {
                "source_event_date": "market_close",
                "known_date": "same_evening (T+0 close); usable at T+1 fill under harness convention",
                "pit_basis": "same_evening",
                "note": "VIX close = CBOE publication same evening; no extra shift applied",
            },
            "spy_dd126": {
                "source_event_date": "market_close",
                "known_date": "same_evening (T+0 close); usable at T+1 fill under harness convention",
                "pit_basis": "same_evening",
                "note": "SPY adj-close dividend-adjusted; rolling-126td max drawdown; no extra shift",
            },
            "hy_oas": {
                "source_event_date": "market_close (reference date)",
                "known_date": "T+1 business day (FRED daily BAMLH0A0HYM2 publishes next business day)",
                "pit_basis": "+1_business_day",
                "shift_applied": "+1 business day",
            },
            "hy_oas_roc21": {
                "source_event_date": "market_close",
                "known_date": "same as hy_oas (+1bd)",
                "pit_basis": "+1_business_day",
                "note": "21-trading-day first difference of hy_oas (after shift)",
            },
            "hy_oas_pctile_exp": {
                "source_event_date": "market_close",
                "known_date": "same as hy_oas (+1bd)",
                "pit_basis": "+1_business_day",
                "note": "EXPANDING-window percentile — no look-ahead; recomputed from shifted series",
            },
            "ofr_fsi": {
                "source_event_date": "OFR publication date",
                "known_date": "T+1 business day (OFR FSI ~2bd publication lag; conservative T+1)",
                "pit_basis": "+1_business_day",
                "shift_applied": "+1 business day",
            },
            "ofr_fsi_pctile_exp": {
                "source_event_date": "OFR publication date",
                "known_date": "same as ofr_fsi (+1bd)",
                "pit_basis": "+1_business_day",
                "note": "EXPANDING-window percentile — no look-ahead",
            },
            "ofr_fsi_mom15": {
                "source_event_date": "OFR publication date",
                "known_date": "same as ofr_fsi (+1bd)",
                "pit_basis": "+1_business_day",
                "note": "15-trading-day momentum (diff) of ofr_fsi (after shift)",
            },
            "stlfsi4_vintage": {
                "source_event_date": "STLFSI4 reference week (Thursday-ending)",
                "known_date": "realtime_start (ALFRED initial-release date)",
                "pit_basis": "alfred_vintage_as_of_join",
                "coverage_note": stlfsi4_coverage_note,
                "note": (
                    "STLFSI4 ALFRED-vintaged; local store partial (2022-11-11 onward, 187 rows). "
                    "Dates before 2022-11-11 are NaN. Full history requires FRED API key + "
                    "collectors/fred.py fetch_vintages(). NFCI excluded per RUL-23 (re-revises "
                    "all history, no vintage)."
                ),
            },
            "macro_m1_fsi_turn": {
                "source_event_date": "derived from ofr_fsi",
                "known_date": "same as ofr_fsi (+1bd)",
                "pit_basis": "+1_business_day",
                "definition": "ofr_fsi_pctile_exp >= 0.80 AND ofr_fsi_mom15 < 0",
            },
            "macro_m2_oas_turn": {
                "source_event_date": "derived from hy_oas",
                "known_date": "same as hy_oas (+1bd)",
                "pit_basis": "+1_business_day",
                "definition": "hy_oas_pctile_exp >= 0.80 AND hy_oas_roc21 < 0",
            },
            "pos_p1_naaim_reset": {
                "source_event_date": "NAAIM Wednesday survey close",
                "known_date": "publish_date + 7 calendar days (Thursday publish + 7d)",
                "pit_basis": "+7_calendar_days",
                "note": (
                    "NAAIM publishes Thursday; 7-day forward lag matches naaim_overlay_phase0.py "
                    "convention. Forward-filled. Trailing 3y (156 weekly obs) rolling percentile "
                    "<= 0.20 AND latest > 2-weeks-prior publish. Value NOT visible before publish+7d."
                ),
                "definition": (
                    "trailing_156wk_pctile(naaim_exposure) <= 0.20 "
                    "AND naaim_exposure > naaim_exposure.shift(2)"
                ),
            },
            "pos_p2_cot_reset": {
                "source_event_date": "COT Tuesday as-of",
                "known_date": "Friday publish date (embedded in store index — store is Friday-indexed)",
                "pit_basis": "friday_publish_date",
                "note": (
                    "COT net spec = ES+NDX combined. Forward-filled from Friday publish. "
                    "No additional lag: Friday publish IS the known_date per RUL-23. "
                    "3-day lag to Tuesday as-of already embedded in the published date."
                ),
                "definition": (
                    "trailing_156wk_pctile(cot_es+ndx_net_spec) <= 0.20 "
                    "AND cot_combined > cot_combined.shift(2)"
                ),
            },
        },
        "market_state_label": {
            "status": "unavailable_v1",
            "reason": (
                "engine/market_state.py is a point-in-time snapshot engine only — it requires "
                "a live feature frame (latest dict from engine/inputs.py) and has no historical "
                "series mode. Reconstruction would require re-deriving the full composite across "
                "every date (~23yr × daily), which would drift from live due to data updates. "
                "Per RUL-24, VIX + SPY-drawdown are the mandatory controls for R1-M; "
                "market_state/risk_regime are supplementary and shared-source-excluded "
                "for M1/M2 families anyway."
            ),
        },
        "risk_regime_label": {
            "status": "unavailable_v1",
            "reason": "Same as market_state_label — same snapshot engine (engine/risk_radar.py).",
        },
        "frozen_thresholds": {
            "ofr_fsi_pctile_exp_threshold_m1": _FSI_HIGH_PCTILE,
            "hy_oas_pctile_exp_threshold_m2":  _OAS_HIGH_PCTILE,
            "ofr_fsi_mom15_sign_m1":           "< 0",
            "hy_oas_roc21_sign_m2":            "< 0",
            "ofr_fsi_mom15_window_td":         _FSI_MOM15_WIN,
            "hy_oas_roc21_window_td":          _OAS_ROC21_WIN,
            "naaim_pctile_3y_threshold_p1":    _NAAIM_PCTILE_THR,
            "naaim_pctile_3y_window_wks_p1":   _NAAIM_WIN_WKS,
            "naaim_rising_lag_wks_p1":         2,
            "naaim_forward_lag_calendar_days":  7,
            "cot_pctile_3y_threshold_p2":      _COT_PCTILE_THR,
            "cot_pctile_3y_window_wks_p2":     _COT_WIN_WKS,
            "cot_rising_lag_wks_p2":           2,
        },
        "column_coverage": {col: _cov(col) for col in panel.columns},
        "flag_base_rates": {
            "macro_m1_fsi_turn":  _flag_rate("macro_m1_fsi_turn"),
            "macro_m2_oas_turn":  _flag_rate("macro_m2_oas_turn"),
            "pos_p1_naaim_reset": _flag_rate("pos_p1_naaim_reset"),
            "pos_p2_cot_reset":   _flag_rate("pos_p2_cot_reset"),
        },
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Build macro_fire_context panel")
    parser.add_argument("--smoke", action="store_true",
                        help="Smoke test: build 2002-2010 only")
    args = parser.parse_args()

    panel = build(smoke=args.smoke)

    # Re-load coverage note for meta (load once more cleanly)
    _, stlfsi4_note = _load_stlfsi4_vintage()

    meta = _build_meta(panel, stlfsi4_note)

    # Write outputs
    (_DATA / "research").mkdir(parents=True, exist_ok=True)
    panel.to_parquet(_OUT_PQ)
    _OUT_META.write_text(json.dumps(meta, indent=2))

    # Report
    log.info("Wrote %s (%d rows)", _OUT_PQ, len(panel))
    log.info("Wrote %s", _OUT_META)
    log.info("Date span: %s to %s", meta["date_span"]["start"], meta["date_span"]["end"])
    log.info("")
    log.info("=== Coverage ===")
    for col, cov in meta["column_coverage"].items():
        log.info("  %-28s %.1f%% non-null  (%s to %s)",
                 col, 100 * cov["coverage_frac"], cov["first_valid"], cov["last_valid"])
    log.info("")
    log.info("=== Flag Base Rates ===")
    for flag, rate in meta["flag_base_rates"].items():
        if rate is not None:
            log.info("  %-28s %.2f%%", flag, 100 * rate)
        else:
            log.info("  %-28s n/a", flag)
    log.info("")
    log.info("market_state_label: %s", meta["market_state_label"]["status"])
    log.info("stlfsi4_vintage coverage: %s", stlfsi4_note)


if __name__ == "__main__":
    main()
