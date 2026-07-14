"""Corporate Credit Watch — G-Spread Engine (corp_credit.v1).

DISPLAY-TIER ORGAN — authority all-false; not validated in the promoted sense.
Accruing: forward accrual since 2026-07-14. Promotion only via pre-registered
gauntlet (CCW-R3/R4 criteria a-d; see run_validation()).

Masterplan references:
  §2.5   Bond price convention + YTM pipeline contract
  §3-P2  Four pre-registered validation criteria (a-d)
  §5     Rulings CCW-R3 (price-convention), CCW-R4 (near-par callable HY),
         CCW-R16 (dead-wire law — must be wired in daily.yml collect_tail)
  §6 W2  Wave scope: g-spread engine, aggregates, validation gate

Inputs:
  data/corp_bonds/holdings/<FUND>/<date>.parquet     (5 funds, all dates)
  data/corp_bonds/issuer_themes.json                 (issuer/theme registry)
  data/fred/DGS*.parquet + BAMLC0A0CM.parquet       (CMT pillars + IG OAS)
  data/breadth/ticker_sectors.parquet                (ticker → sector)
  data/breadth/constituents.parquet                  (name → sector fallback)
  data/corp_bonds/validation_sample/<FUND>_<date>.parquet  (iShares, optional)

Outputs (all under data/corp_bonds/):
  series/issuer_daily.parquet
  series/theme_daily.parquet
  series/sector_daily.parquet
  series/market_daily.parquet
  series/maturity_wall.parquet
  series/bond_panel_latest.parquet
  latest.json
  validation.json
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import re
import time
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from lib import config

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Authority contract (CCW-R3/R4 — display-tier fence)
# ---------------------------------------------------------------------------

AUTHORITY_V1 = {"rank": False, "size": False, "gate": False, "escalate": False}

_ACCRUING = (
    "DISPLAY-ONLY / NOT VALIDATED. Forward accrual since 2026-07-14. "
    "Per-criterion validation results print in data/corp_bonds/validation.json "
    "on every run. Promotion to authority requires passing CCW pre-registered "
    "gauntlet criteria a-d (§3-P2): dirty/clean price verdict, YTM vs iShares "
    "within 25bp, IG g-spread vs BAML OAS within 30bp, composition-guard fixture. "
    "Gauntlet is a PROMOTION gate, not a build gate. "
    "Context accrual proceeds regardless of gate status."
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Fund segments
IG_FUNDS = {"SPSB", "SPIB", "SPLB"}
HY_FUNDS = {"JNK", "SPHY"}

# CMT pillars: (FRED series id, tenor in years)
CMT_PILLARS = [
    ("DGS3MO", 0.25), ("DGS6MO", 0.5), ("DGS1", 1.0), ("DGS2", 2.0),
    ("DGS3", 3.0), ("DGS5", 5.0), ("DGS7", 7.0), ("DGS10", 10.0),
    ("DGS20", 20.0), ("DGS30", 30.0),
]

# Near-par callable HY exclusion threshold (§2.5-4, CCW-R4)
NEAR_PAR_CLEAN = 99.0  # clean price threshold; pre-declared constant

# Matched-panel guard (§2.5-3)
ENTRY_SEASONING_BARS = 5  # number of panel dates a bond must be present before contributing
COMPOSITION_MARKER_PAR_SHARE = 0.005  # 0.5% of panel par = composition change flag

# Dispersion floor
DISPERSION_FLOOR_N = 8  # p90-p10 when n >= this; max-min when 3..7; null when <3

# Maturity bucket labels (keys EXACTLY as spec'd)
MATURITY_BUCKETS = [
    ("0_1y",    0.0,  1.0),
    ("1_3y",    1.0,  3.0),
    ("3_5y",    3.0,  5.0),
    ("5_10y",   5.0, 10.0),
    ("10y_plus",10.0, float("inf")),
]

# Minimum tenor for YTM/g-spread computation (bonds expiring within 14 days excluded)
MIN_TENOR_DAYS = 14
MIN_TENOR = MIN_TENOR_DAYS / 365.25

# CMT tolerance: last available curve within 7 calendar days
CMT_TOLERANCE = pd.Timedelta("7D")

# YTM solver bounds
YTM_INITIAL_LOW, YTM_INITIAL_HIGH = -0.5, 5.0  # decimal bounds for bisection
YTM_VALID_LOW, YTM_VALID_HIGH = -0.5, 5.0
YTM_Y0_MIN, YTM_Y0_MAX = 0.001, 2.0           # initial guess clip
YTM_NEWTON_ITERS = 30
YTM_BISECT_ITERS = 100
YTM_CONV_TOL = 1e-8

# Bond name suffix tokens to cut at when normalizing for sector matching
_NAME_CUT_TOKENS = [" SR ", " SUB", " COMPANY GUAR", " SECURED", " UNSECURED",
                    " NT ", " BD ", " DEB", " NTS"]
_NAME_DROP_SUFFIXES = {"INC", "CORP", "CO", "LLC", "LP", "LTD", "PLC",
                       "HLDGS", "HOLDINGS", "GROUP"}


# ---------------------------------------------------------------------------
# Loader helpers
# ---------------------------------------------------------------------------

def _data_root(root: Path | None) -> Path:
    return root if root is not None else Path(config.data_dir())


def _load_holdings(root: Path | None = None) -> pd.DataFrame:
    """Load ALL PIT holdings parquets across 5 funds and all dates.

    Returns a flat DataFrame with the standard schema + 'fund' column.
    Missing funds are skipped with a warning.
    """
    data_root = _data_root(root)
    frames: list[pd.DataFrame] = []
    holdings_dir = data_root / "corp_bonds" / "holdings"
    for fund in ["SPSB", "SPIB", "SPLB", "JNK", "SPHY"]:
        fund_dir = holdings_dir / fund
        if not fund_dir.exists():
            log.warning("corp_credit: fund dir not found: %s", fund_dir)
            continue
        for p in sorted(fund_dir.glob("*.parquet")):
            try:
                df = pd.read_parquet(p)
                if df.empty:
                    continue
                frames.append(df)
            except Exception as exc:  # noqa: BLE001
                log.warning("corp_credit: failed to read %s: %s", p, exc)
    if not frames:
        log.warning("corp_credit: no holdings data found")
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    return out


def _load_cmt_curve(root: Path | None = None) -> pd.DataFrame:
    """Load CMT Treasury curve from FRED parquets.

    Returns a DataFrame indexed by date with one column per tenor (value in pct).
    Missing pillars are skipped; np.interp handles interpolation over what exists.
    """
    data_root = _data_root(root)
    series: dict[float, pd.Series] = {}
    present: list[str] = []
    for sid, tenor in CMT_PILLARS:
        p = data_root / "fred" / f"{sid}.parquet"
        if not p.exists():
            log.info("corp_credit: CMT pillar %s not found (will interpolate)", sid)
            continue
        try:
            df = pd.read_parquet(p)
            df.index = pd.to_datetime(df.index)
            df = df.sort_index()
            s = df.iloc[:, 0].dropna().astype(float)
            series[tenor] = s
            present.append(sid)
        except Exception as exc:  # noqa: BLE001
            log.warning("corp_credit: CMT pillar %s load failed: %s", sid, exc)

    if not series:
        log.warning("corp_credit: no CMT pillars loaded")
        return pd.DataFrame()

    curve = pd.concat(series, axis=1)
    curve.columns = [str(c) for c in curve.columns]
    curve.index.name = "date"
    log.info("corp_credit: CMT pillars loaded: %s (%d dates)", present, len(curve))
    return curve


def _load_baml_oas(root: Path | None = None) -> pd.Series | None:
    """Load BAML IG OAS (BAMLC0A0CM) in percent."""
    data_root = _data_root(root)
    p = data_root / "fred" / "BAMLC0A0CM.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
        df.index = pd.to_datetime(df.index)
        return df.sort_index().iloc[:, 0].dropna().astype(float)
    except Exception as exc:  # noqa: BLE001
        log.warning("corp_credit: BAML OAS load failed: %s", exc)
        return None


def _load_issuer_registry(root: Path | None = None) -> dict:
    """Load data/corp_bonds/issuer_themes.json."""
    data_root = _data_root(root)
    p = data_root / "corp_bonds" / "issuer_themes.json"
    try:
        with open(p) as f:
            return json.load(f)
    except Exception as exc:  # noqa: BLE001
        log.warning("corp_credit: issuer registry load failed: %s", exc)
        return {"themes": {}}


def _load_ticker_sectors(root: Path | None = None) -> dict[str, str]:
    """Return {ticker: sector} from data/breadth/ticker_sectors.parquet."""
    data_root = _data_root(root)
    p = data_root / "breadth" / "ticker_sectors.parquet"
    if not p.exists():
        return {}
    try:
        df = pd.read_parquet(p)
        return dict(zip(df["ticker"].astype(str), df["sector"].astype(str)))
    except Exception as exc:  # noqa: BLE001
        log.warning("corp_credit: ticker_sectors load failed: %s", exc)
        return {}


def _load_constituents_name_sector(root: Path | None = None) -> dict[str, tuple[str, str] | None]:
    """Return {normalized_name_prefix: (ticker, sector) | None} for constituent-name matching.

    Replicates the System B name matching in engine/equity_factors.py:_names_sectors.
    Index is ticker symbol; columns include 'name' and 'sector'.

    Ambiguity law: if ≥2 rows share the same 2-token normalized key:
      - If they all share the SAME sector, the key maps to (first ticker, sector) — the name
        collision is harmless because the sector assignment is unambiguous.
      - If they have ≥2 DISTINCT sectors, the key maps to None → bond stays unmapped.
        (Docstring promise: ambiguity → unmapped when the sector is ambiguous.)
    """
    data_root = _data_root(root)
    p = data_root / "breadth" / "constituents.parquet"
    if not p.exists():
        return {}
    try:
        df = pd.read_parquet(p)
        # First pass: collect all (ticker, sector) candidates per norm key
        candidates: dict[str, list[tuple[str, str]]] = {}
        for ticker, row in df.iterrows():
            name = str(row.get("name", ""))
            sector = str(row.get("sector", ""))
            norm = _normalize_constituent_name(name)
            if norm:
                candidates.setdefault(norm, []).append((str(ticker), sector))
        # Second pass: resolve — ambiguous sector → None, unambiguous sector → first match
        out: dict[str, tuple[str, str] | None] = {}
        for norm, cands in candidates.items():
            distinct_sectors = {s for _, s in cands}
            if len(distinct_sectors) >= 2:
                out[norm] = None  # sector-ambiguous → unmapped
            else:
                out[norm] = cands[0]  # single sector; any ticker entry works
        return out
    except Exception as exc:  # noqa: BLE001
        log.warning("corp_credit: constituents load failed: %s", exc)
        return {}


# ---------------------------------------------------------------------------
# Name normalization for sector matching
# ---------------------------------------------------------------------------

def _normalize_bond_name(name: str) -> str:
    """Normalize a bond name for sector matching.

    Cut at the first of: SR , SUB, COMPANY GUAR, SECURED, UNSECURED, NT, BD, DEB.
    Uppercase, strip punctuation, drop suffix tokens INC/CORP/CO/LLC/LP/LTD/PLC/
    HLDGS/HOLDINGS/GROUP/&.
    Returns the first two tokens joined by space, or '' if <2 tokens.
    """
    s = name.upper()
    for cut in _NAME_CUT_TOKENS:
        idx = s.find(cut)
        if idx >= 0:
            s = s[:idx]
    # strip punctuation
    s = re.sub(r"[^\w\s]", " ", s)
    tokens = s.split()
    tokens = [t for t in tokens if t not in _NAME_DROP_SUFFIXES and t != "&"]
    if len(tokens) < 2:
        return ""
    return " ".join(tokens[:2])


def _normalize_constituent_name(name: str) -> str:
    """Normalize a constituent (equity) company name for matching.

    Same punctuation strip and suffix drop; first two tokens.
    """
    s = name.upper()
    s = re.sub(r"[^\w\s]", " ", s)
    tokens = s.split()
    tokens = [t for t in tokens if t not in _NAME_DROP_SUFFIXES and t != "&"]
    if len(tokens) < 2:
        return ""
    return " ".join(tokens[:2])


# ---------------------------------------------------------------------------
# Step 1: Canonicalize bonds (aggregate multi-fund positions)
# ---------------------------------------------------------------------------

def canonicalize_bonds(raw: pd.DataFrame) -> pd.DataFrame:
    """Aggregate per-(as_of, isin) across funds. Returns bond-level DataFrame.

    Drops rows with null/nonpositive par/mv, missing maturity or coupon.
    Sets segment = 'hy' when HY-fund held par > IG-fund held par.
    """
    if raw.empty:
        return pd.DataFrame()

    # Convert par/mv to numeric; drop bad rows
    raw = raw.copy()
    raw["par_value"] = pd.to_numeric(raw["par_value"], errors="coerce")
    raw["market_value"] = pd.to_numeric(raw["market_value"], errors="coerce")
    raw["coupon"] = pd.to_numeric(raw["coupon"], errors="coerce")

    n_before = len(raw)
    bad = (
        raw["par_value"].isna() | (raw["par_value"] <= 0) |
        raw["market_value"].isna() | (raw["market_value"] <= 0) |
        raw["maturity"].isna() | (raw["maturity"] == "") |
        raw["isin"].isna() | (raw["isin"] == "") |
        raw["coupon"].isna()
    )
    dropped = int(bad.sum())
    raw = raw[~bad].copy()
    log.info("corp_credit: canonicalize: dropped %d/%d bad rows", dropped, n_before)

    # Tag fund segment
    raw["_is_hy"] = raw["fund"].isin(HY_FUNDS).astype(float)
    raw["_is_ig"] = raw["fund"].isin(IG_FUNDS).astype(float)
    raw["_hy_par"] = raw["par_value"] * raw["_is_hy"]
    raw["_ig_par"] = raw["par_value"] * raw["_is_ig"]

    # Build aggregated bond panel
    grp = raw.groupby(["as_of", "isin"])

    # For each group: aggregate par/mv; pick metadata from largest-par row
    agg_par = grp["par_value"].sum()
    agg_mv = grp["market_value"].sum()
    agg_hy_par = grp["_hy_par"].sum()
    agg_ig_par = grp["_ig_par"].sum()

    # Funds joined string (sorted)
    agg_funds = grp["fund"].apply(lambda s: ",".join(sorted(s.unique())))

    # For metadata: pick row with largest par_value per group
    # Use idxmax on par_value within each group
    idx_largest = raw.groupby(["as_of", "isin"])["par_value"].idxmax()

    meta_cols = ["name", "coupon", "maturity", "cusip6"]
    meta = raw.loc[idx_largest, meta_cols]
    meta.index = idx_largest.index  # restore group index

    # Assemble
    result = pd.DataFrame({
        "par": agg_par,
        "mv": agg_mv,
        "hy_par": agg_hy_par,
        "ig_par": agg_ig_par,
        "funds": agg_funds,
    })
    result = result.join(meta)
    result["segment"] = np.where(result["hy_par"] > result["ig_par"], "hy", "ig")
    result["price_dirty_raw"] = 100.0 * result["mv"] / result["par"]
    result = result.reset_index()
    result["dropped_rows"] = dropped  # carry forward for coverage report

    return result


# ---------------------------------------------------------------------------
# Step 2: Accrued interest 30/360 US semiannual (vectorized)
# ---------------------------------------------------------------------------

def _last_coupon_dates_vectorized(as_of: pd.Series, maturity: pd.Series) -> pd.Series:
    """Find last coupon date on the semiannual anniversary grid, vectorized.

    Coupon dates are maturity-anniversary every 6 months.
    Anchor: month/day from maturity.
    """
    # Parse dates
    as_of_dt = pd.to_datetime(as_of)
    mat_dt = pd.to_datetime(maturity, errors="coerce")

    mat_month = mat_dt.dt.month
    mat_day = mat_dt.dt.day
    as_of_year = as_of_dt.dt.year

    # Generate 4 candidate dates around as_of (same month/day, +/-6m grid)
    # We look at the 6 most recent coupon anniversary months
    # Coupon months: mat_month and mat_month ± 6 (mod 12)
    def _clip_day(y, m, d):
        """Clip day to month length."""
        import calendar
        max_d = calendar.monthrange(int(y), int(m))[1]
        return min(int(d), max_d)

    n = len(as_of_dt)
    result = pd.Series(pd.NaT, index=range(n), dtype="datetime64[ns]")

    # Vectorize by building a small matrix of candidate dates
    # For each bond, candidates are the last 4 coupon dates
    candidates_list = []
    for offset_months in [0, 6, 12, 18, 24]:
        for sign in [1, -1]:
            total_months_offset = sign * offset_months
            # Compute candidate year/month
            raw_month = mat_month + total_months_offset
            cand_year = as_of_year + (raw_month - 1) // 12
            cand_month = ((raw_month - 1) % 12) + 1
            # Clip day to valid range — done element-wise
            cand_day = pd.Series([
                _clip_day(y, m, d)
                for y, m, d in zip(cand_year, cand_month, mat_day)
            ], index=mat_month.index)
            try:
                cand_dates = pd.to_datetime({
                    "year": cand_year.values,
                    "month": cand_month.values,
                    "day": cand_day.values,
                })
                candidates_list.append(cand_dates)
            except Exception:  # noqa: BLE001
                pass

    if not candidates_list:
        return result

    candidates = pd.concat([pd.Series(c) for c in candidates_list], axis=1)
    # Find largest candidate <= as_of
    as_of_arr = as_of_dt.values
    for col_idx in range(candidates.shape[1]):
        col = candidates.iloc[:, col_idx]
        mask = (col.values <= as_of_arr) & col.notna().values
        better = mask & (result.isna().values | (col.values > result.values))
        result = result.where(~better, col)

    return result


def accrued_30_360_us(
    as_of: pd.Series,
    maturity: pd.Series,
    coupon_pct: pd.Series,
) -> pd.Series:
    """Compute accrued interest using 30/360 US semiannual convention, vectorized.

    coupon_pct is annual coupon in percent (e.g. 4.5 means 4.5%).
    Zero-coupon bonds (coupon_pct == 0) return 0.
    Returns accrued_pct: accrual as a price fraction (percent of par), not per-year.
    """
    last_cpn = _last_coupon_dates_vectorized(as_of, maturity)
    as_of_dt = pd.to_datetime(as_of)

    # Extract date components
    d1 = last_cpn.dt.day.astype(float)
    m1 = last_cpn.dt.month.astype(float)
    y1 = last_cpn.dt.year.astype(float)

    d2 = as_of_dt.dt.day.astype(float)
    m2 = as_of_dt.dt.month.astype(float)
    y2 = as_of_dt.dt.year.astype(float)

    # 30/360 US adjustments:
    # d1 = 31 → d1 = 30
    d1 = d1.where(d1 != 31, 30.0)
    # d2 = 31 AND d1 >= 30 → d2 = 30
    d2 = d2.where(~((d2 == 31) & (d1 >= 30)), 30.0)

    days_30_360 = (y2 - y1) * 360.0 + (m2 - m1) * 30.0 + (d2 - d1)
    days_30_360 = days_30_360.clip(lower=0.0)

    # accrued_pct = coupon * (days_30_360 / 360)
    # For zero-coupon bonds: 0
    zero_cpn = coupon_pct == 0.0
    accrued = coupon_pct * days_30_360 / 360.0
    accrued = accrued.where(~zero_cpn, 0.0)

    # Null out if last coupon date is NaT
    accrued = accrued.where(last_cpn.notna(), 0.0)

    return accrued.fillna(0.0)


# ---------------------------------------------------------------------------
# Step 3: Price convention switch
# ---------------------------------------------------------------------------

def apply_price_convention(
    price_dirty_raw: pd.Series,
    accrued_pct: pd.Series,
    convention: str = "dirty",
) -> tuple[pd.Series, pd.Series]:
    """Return (dirty_price, clean_price) under the given convention.

    MV/Par is presumed DIRTY per §2.5-1 pending empirical verdict from run_validation().
    convention='dirty': dirty_price = price_dirty_raw (standard; MV/Par is dirty).
    convention='clean': dirty_price = price_dirty_raw + accrued_pct (MV/Par is clean).
    clean_price = dirty_price - accrued_pct always.

    The YTM solve uses dirty_price vs full coupon cashflows — this is the standard
    accrued-corrected construction of §2.5-1 (PV of all future CFs at yield y equals
    the dirty price, which includes accrued interest to settlement).
    """
    if convention == "dirty":
        dirty = price_dirty_raw.copy()
    else:
        dirty = price_dirty_raw + accrued_pct
    clean = dirty - accrued_pct
    return dirty, clean


# ---------------------------------------------------------------------------
# Step 5: YTM solve — vectorized Newton + bisection fallback
# ---------------------------------------------------------------------------

def _pv_and_deriv_matrix(
    y: np.ndarray,          # shape (n,), decimal annual yield
    dirty_price: np.ndarray, # shape (n,)
    coupon_pct: np.ndarray,  # shape (n,), annual pct (e.g. 4.5)
    tenor_yrs: np.ndarray,   # shape (n,)
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Compute PV and dPV/dy for a bond matrix, vectorized.

    Semiannual coupon periods counted back from maturity.
    Returns (pv, dpv_dy, pv_minus_price).
    """
    n = len(y)
    # Maximum number of semiannual periods needed.
    # Use np.nanmax so that NaN-tenor rows don't crash here (defense-in-depth;
    # callers are expected to filter NaN tenors, but guard anyway).
    valid_tenors = tenor_yrs[~np.isnan(tenor_yrs)]
    max_periods = int(np.ceil(2.0 * np.nanmax(tenor_yrs))) + 2 if len(valid_tenors) > 0 else 2

    # Build period indices j = 0, 1, ..., max_periods-1
    j_arr = np.arange(max_periods, dtype=float)  # shape (max_periods,)

    # tau_j = 2*tenor - j for j in [0..floor(2*tenor)]; shape (n, max_periods)
    # NaN-tenor rows produce NaN tau → they propagate to NaN in pv/dpv (safe null-out).
    two_tenor = (2.0 * tenor_yrs)[:, None]             # (n, 1)
    tau = two_tenor - j_arr[None, :]                    # (n, max_periods)

    # Cashflow mask: tau > 0 is a coupon period; tau == 2*tenor is also the principal
    coupon_cf = (coupon_pct / 2.0)[:, None]             # (n, 1) — semiannual coupon
    principal = 100.0

    # CF at each tau_j: coupon where tau>0, +principal at j=0 (tau=2*tenor, the last
    # chronological payment — furthest discount — regardless of stub).
    # The j-indexing is REVERSE: j=0 is the last payment (tau=2*tenor, longest discount),
    # j=floor(2*tenor) would be tau≈0 which maps to settlement-date and produces zero
    # discounting when tenor is an integer (the original bug). Placing principal at j=0
    # ensures the correct (1+y/2)^{-2*tenor} discount for the final cash flow.
    cf = np.where(tau > 0, coupon_cf, 0.0)              # (n, max_periods)
    idx_n = np.arange(n)
    cf[idx_n, 0] += principal                           # principal at j=0 (tau=2*tenor)

    # Mask: only tau > 0
    valid = tau > 0.0                                    # (n, max_periods)
    # Discount factor: (1 + y/2)^(-tau_j)
    y_semi = (y / 2.0)[:, None]                         # (n, 1)
    disc = np.where(valid, (1.0 + y_semi) ** (-tau), 0.0)  # (n, max_periods)

    pv = (cf * disc).sum(axis=1)                        # (n,)

    # dPV/dy = sum(CF * (-tau) * (1+y/2)^(-tau-1) * 0.5)
    dpv = (cf * disc * (-tau) * 0.5 / (1.0 + y_semi)).sum(axis=1)  # (n,)
    dpv = np.where(valid.any(axis=1), dpv, 0.0)

    return pv, dpv, pv - dirty_price


def _ytm_solve(
    dirty_price: np.ndarray,
    coupon_pct: np.ndarray,
    tenor_yrs: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Solve YTM for each bond using Newton then bisection fallback.

    Returns (ytm_decimal, solver_flag):
      solver_flag: 0 = Newton converged, 1 = bisection, 2 = failed
    """
    n = len(dirty_price)
    if n == 0:
        return np.array([]), np.array([], dtype=int)

    # Clamp tenor to minimum to avoid division issues
    tenor_safe = np.maximum(tenor_yrs, 0.5)

    # Initial guess: approximate YTM
    y = (coupon_pct / 100.0) + (100.0 - dirty_price) / (100.0 * tenor_safe)
    y = np.clip(y, YTM_Y0_MIN, YTM_Y0_MAX)

    solver_flag = np.full(n, 2, dtype=int)  # 2 = failed
    ytm_out = np.full(n, np.nan)

    # Newton iterations
    active = np.ones(n, dtype=bool)
    for _ in range(YTM_NEWTON_ITERS):
        if not active.any():
            break
        pv, dpv, err = _pv_and_deriv_matrix(y, dirty_price, coupon_pct, tenor_yrs)
        # Converged check
        converged = active & (np.abs(err) < YTM_CONV_TOL)
        solver_flag = np.where(converged, 0, solver_flag)
        ytm_out = np.where(converged, y, ytm_out)
        active = active & ~converged

        if not active.any():
            break

        # Newton step (only on active, guard zero derivative)
        step = np.where(active & (np.abs(dpv) > 1e-15), -err / dpv, 0.0)
        y = y + step

    # Bisection fallback on failed/unconverged
    need_bisect = active  # still active = not converged
    if need_bisect.any():
        bi = need_bisect
        y_lo = np.full(n, YTM_INITIAL_LOW)
        y_hi = np.full(n, YTM_INITIAL_HIGH)

        for _ in range(YTM_BISECT_ITERS):
            if not bi.any():
                break
            y_mid = (y_lo + y_hi) / 2.0
            pv, _, err = _pv_and_deriv_matrix(y_mid, dirty_price, coupon_pct, tenor_yrs)
            converged = bi & (np.abs(err) < YTM_CONV_TOL)
            solver_flag = np.where(converged, 1, solver_flag)
            ytm_out = np.where(converged, y_mid, ytm_out)
            bi = bi & ~converged
            if not bi.any():
                break
            # PV > price → too low yield → raise lower bound; else raise upper bound
            pv_hi = np.where(bi, pv > dirty_price, False)
            y_lo = np.where(bi & pv_hi, y_mid, y_lo)
            y_hi = np.where(bi & ~pv_hi, y_mid, y_hi)

    # Validity check: ytm outside (-0.5, 5.0) → null out
    out_of_range = (ytm_out < YTM_VALID_LOW) | (ytm_out > YTM_VALID_HIGH)
    ytm_out = np.where(out_of_range, np.nan, ytm_out)
    solver_flag = np.where(out_of_range & (solver_flag != 2), 2, solver_flag)

    return ytm_out, solver_flag


# ---------------------------------------------------------------------------
# Step 6: G-spread via CMT curve interpolation
# ---------------------------------------------------------------------------

def _build_cmt_lookup(
    curve_df: pd.DataFrame,
    as_of_dates: pd.DatetimeIndex,
) -> pd.DataFrame:
    """For each as_of date, find the last CMT curve row on-or-before within 7d.

    Returns a DataFrame indexed by as_of_date, columns are tenor floats.
    Rows where no curve within 7d: all NaN.
    """
    if curve_df.empty:
        return pd.DataFrame(index=as_of_dates)

    curve_idx = pd.to_datetime(curve_df.index).sort_values()
    curve_df_sorted = curve_df.loc[curve_idx]

    # Use merge_asof for backward fill
    # curve_df has the same date for all pillars; columns = tenor strings
    # Normalize both sides to datetime64[ns] to avoid MergeError on dtype mismatch
    # in newer Pandas (which may infer datetime64[s] or datetime64[us] from parquet).
    left = pd.DataFrame({"as_of": pd.DatetimeIndex(as_of_dates).astype("datetime64[ns]")}).sort_values("as_of")
    curve_reset = curve_df_sorted.reset_index()
    curve_reset.columns = ["curve_date"] + list(curve_df_sorted.columns)
    curve_reset["curve_date"] = pd.to_datetime(curve_reset["curve_date"]).astype("datetime64[ns]")

    merged = pd.merge_asof(
        left,
        curve_reset,
        left_on="as_of",
        right_on="curve_date",
        direction="backward",
        tolerance=CMT_TOLERANCE,
    )
    merged = merged.set_index("as_of").drop(columns=["curve_date"], errors="ignore")
    merged = merged.reindex(as_of_dates)
    return merged


def compute_g_spread_bp(
    ytm_pct: pd.Series,
    tenor_yrs: pd.Series,
    as_of: pd.Series,
    curve_df: pd.DataFrame,
) -> tuple[pd.Series, pd.Series]:
    """Interpolate CMT at bond tenor and compute g-spread in bp.

    Returns (cmt_pct, g_spread_bp). Null when no CMT within 7d.
    """
    if curve_df.empty:
        null = pd.Series(np.nan, index=ytm_pct.index)
        return null.copy(), null.copy()

    tenor_floats = sorted([float(c) for c in curve_df.columns])
    unique_dates = pd.to_datetime(as_of).drop_duplicates()
    cmt_by_date = _build_cmt_lookup(curve_df, pd.DatetimeIndex(unique_dates))

    # Build lookup from as_of date → Series of pillar values
    date_to_pillars: dict[str, np.ndarray] = {}
    for dt, row in cmt_by_date.iterrows():
        vals = row.values.astype(float)
        date_to_pillars[str(dt.date())] = vals  # type: ignore[union-attr]

    cmt_arr = np.full(len(ytm_pct), np.nan)
    as_of_strs = as_of.values.astype(str) if not pd.api.types.is_string_dtype(as_of) else as_of.values
    tenor_arr = tenor_yrs.values.astype(float)
    ytm_arr = ytm_pct.values.astype(float)

    for i, (dt_str, tenor, ytm) in enumerate(zip(as_of_strs, tenor_arr, ytm_arr)):
        pillars = date_to_pillars.get(dt_str[:10])
        if pillars is None or np.all(np.isnan(pillars)):
            continue
        valid = ~np.isnan(pillars)
        if valid.sum() < 2:
            continue
        cmt_arr[i] = np.interp(tenor, np.array(tenor_floats)[valid], pillars[valid])

    cmt_pct = pd.Series(cmt_arr, index=ytm_pct.index)
    g_spread_bp = (ytm_arr - cmt_arr) * 100.0
    g_spread_bp = pd.Series(
        np.where(np.isnan(cmt_arr) | np.isnan(ytm_arr), np.nan, g_spread_bp),
        index=ytm_pct.index,
    )
    return cmt_pct, g_spread_bp


# ---------------------------------------------------------------------------
# Step 7: Issuer/theme matching
# ---------------------------------------------------------------------------

def match_issuers(
    panel: pd.DataFrame,
    registry: dict,
) -> tuple[pd.Series, pd.Series]:
    """Match bonds to issuers and themes per registry.

    id_prefixes tested FIRST (cusip6 or isin prefix), then name_match_patterns.
    First match in JSON order wins. Returns (issuer_series, theme_series).
    """
    n = len(panel)
    issuer_out = pd.array([None] * n, dtype=object)
    theme_out = pd.array([None] * n, dtype=object)

    themes = registry.get("themes", {})
    # Pre-index: build list of (theme_key, issuer_key, id_prefixes, name_patterns)
    matchers = []
    for theme_key, theme_data in themes.items():
        for issuer_key, issuer_data in theme_data.get("issuers", {}).items():
            matchers.append((
                theme_key,
                issuer_key,
                issuer_data.get("id_prefixes", []),
                [p.upper() for p in issuer_data.get("name_match_patterns", [])],
            ))

    cusip6 = panel["cusip6"].fillna("").str.upper().values
    isin = panel["isin"].fillna("").str.upper().values
    name = panel["name"].fillna("").str.upper().values
    unmatched_mask = np.ones(n, dtype=bool)

    for theme_key, issuer_key, id_prefixes, name_patterns in matchers:
        if not unmatched_mask.any():
            break
        for i in np.where(unmatched_mask)[0]:
            # Test id_prefixes first
            matched = False
            for pfx in id_prefixes:
                pfx_u = pfx.upper()
                if cusip6[i].startswith(pfx_u) or isin[i].startswith(pfx_u):
                    matched = True
                    break
            if not matched:
                for pat in name_patterns:
                    if pat in name[i]:
                        matched = True
                        break
            if matched:
                issuer_out[i] = issuer_key
                theme_out[i] = theme_key
                unmatched_mask[i] = False

    return pd.Series(issuer_out, index=panel.index), pd.Series(theme_out, index=panel.index)


# ---------------------------------------------------------------------------
# Step 8: Sector mapping
# ---------------------------------------------------------------------------

def map_sectors(
    panel: pd.DataFrame,
    registry: dict,
    ticker_sectors: dict[str, str],
    constituent_name_sector: dict[str, tuple[str, str]],
) -> pd.Series:
    """Map bonds to sectors.

    Registry issuers: issuer→equity_ticker→sector via ticker_sectors.
    Non-registry bonds: normalize name, require first 2 tokens to match exactly
    and uniquely in constituents. Ambiguity (0 or >=2 candidates) → unmapped.
    """
    # Build issuer→ticker from registry
    issuer_to_ticker: dict[str, str] = {}
    for theme_data in registry.get("themes", {}).items():
        _, td = theme_data
        for iss_key, iss_data in td.get("issuers", {}).items():
            tk = iss_data.get("equity_ticker", "")
            if tk:
                issuer_to_ticker[iss_key] = tk

    sector_out = pd.array([None] * len(panel), dtype=object)

    for i, row in enumerate(panel.itertuples()):
        issuer = getattr(row, "issuer", None)
        if issuer and issuer in issuer_to_ticker:
            tk = issuer_to_ticker[issuer]
            sec = ticker_sectors.get(tk)
            if sec:
                sector_out[i] = sec
                continue

        # Fallback: constituent name match.
        # constituent_name_sector maps norm_key → (ticker, sector) | None.
        # None sentinel means the key is sector-ambiguous → leave unmapped.
        norm = _normalize_bond_name(str(getattr(row, "name", "") or ""))
        if not norm:
            continue
        if norm not in constituent_name_sector:
            continue
        match = constituent_name_sector[norm]
        if match is not None:
            sector_out[i] = match[1]

    return pd.Series(sector_out, index=panel.index)


# ---------------------------------------------------------------------------
# Step 9 & 10: Near-par flag and matched-panel guard
# ---------------------------------------------------------------------------

def compute_near_par_flag(
    segment: pd.Series,
    clean_price: pd.Series,
) -> pd.Series:
    """Near-par callable HY flag (§2.5-4, CCW-R4).

    Flagged when: segment == 'hy' AND clean_price >= NEAR_PAR_CLEAN (99.0).
    Flagged bonds STAY in all level/par aggregates but are EXCLUDED from matched-panel
    delta contributions. Threshold 99.0 is pre-declared constant NEAR_PAR_CLEAN.
    """
    return ((segment == "hy") & (clean_price >= NEAR_PAR_CLEAN)).astype(bool)


def compute_first_seen(panel: pd.DataFrame) -> pd.Series:
    """Compute first_seen date per isin across all as_of dates."""
    if "as_of" not in panel.columns or "isin" not in panel.columns:
        return pd.Series(dtype=object)
    first = panel.groupby("isin")["as_of"].min()
    return panel["isin"].map(first)


def compute_matched_delta(
    panel: pd.DataFrame,
    sorted_dates: list,
    scope_col: str,
    group_key: str,
) -> dict[str, dict]:
    """Compute matched-panel delta g-spread for a given grouping.

    Returns {scope_value: {date_str: {'d1': val, 'matched_n': n, 'comp_change': bool}}}

    matched set at (t_prev, t):
      - present at both dates
      - first_seen <= date at position (t_idx - ENTRY_SEASONING_BARS)
      - not near_par_call_flag at t

    composition_change = True when (entered_par + exited_par) > COMPOSITION_MARKER_PAR_SHARE
    of panel par at t.
    """
    out: dict = {}
    if len(sorted_dates) < 2:
        return out

    date_groups: dict = {}
    for dt in sorted_dates:
        sub = panel[panel["as_of"] == dt]
        for key, grp in sub.groupby(scope_col, dropna=True):
            date_groups.setdefault(key, {})[dt] = grp

    for key, date_map in date_groups.items():
        out[str(key)] = {}
        dates_present = sorted(date_map.keys())
        if len(dates_present) < 2:
            continue
        for i in range(1, len(dates_present)):
            t_prev = dates_present[i - 1]
            t = dates_present[i]
            grp_prev = date_map[t_prev]
            grp_t = date_map[t]

            # Global position of t in sorted_dates
            try:
                t_idx = sorted_dates.index(t)
            except ValueError:
                continue

            # Seasoning cutoff: first_seen <= date at position (t_idx - ENTRY_SEASONING_BARS)
            if t_idx >= ENTRY_SEASONING_BARS:
                seasoning_cutoff = sorted_dates[t_idx - ENTRY_SEASONING_BARS]
            else:
                seasoning_cutoff = None

            isins_prev = set(grp_prev["isin"])
            isins_t = set(grp_t["isin"])
            common = isins_prev & isins_t

            # Filter: seasoning + not near_par at t
            grp_t_indexed = grp_t.set_index("isin")
            matched_isins = []
            for isin in common:
                if isin not in grp_t_indexed.index:
                    continue
                row_t = grp_t_indexed.loc[isin]
                # near_par exclusion
                if row_t.get("near_par_call_flag", False):
                    continue
                # seasoning check
                fs = row_t.get("first_seen", None)
                if fs is None:
                    continue
                if seasoning_cutoff is not None and str(fs) > str(seasoning_cutoff):
                    continue
                matched_isins.append(isin)

            if not matched_isins:
                out[str(key)][str(t)] = {"d1": None, "matched_n": 0, "comp_change": False}
                continue

            # Par-weighted mean g-spread at t and t_prev
            grp_prev_indexed = grp_prev.set_index("isin")
            matched_t = grp_t_indexed.loc[matched_isins]
            matched_prev = grp_prev_indexed.reindex(matched_isins)

            gs_t = matched_t["g_spread_bp"].astype(float)
            par_t = matched_t["par"].astype(float)
            gs_prev = matched_prev["g_spread_bp"].astype(float)

            # Only include bonds where both g-spreads are valid
            valid = gs_t.notna() & gs_prev.notna() & par_t.notna() & (par_t > 0)
            if not valid.any():
                out[str(key)][str(t)] = {"d1": None, "matched_n": 0, "comp_change": False}
                continue

            gs_t_valid = gs_t[valid]
            gs_prev_valid = gs_prev[valid]
            par_valid = par_t[valid]
            pw_t = (gs_t_valid * par_valid).sum() / par_valid.sum()
            pw_prev = (gs_prev_valid * par_valid).sum() / par_valid.sum()
            d1 = float(pw_t - pw_prev)

            # Composition change: (entered + exited par) > 0.5% of panel par at t
            total_par_t = grp_t["par"].sum()
            entered_par = grp_t_indexed.reindex(isins_t - isins_prev)["par"].fillna(0).sum()
            exited_par = grp_prev_indexed.reindex(isins_prev - isins_t)["par"].fillna(0).sum()
            comp_change = bool((entered_par + exited_par) > COMPOSITION_MARKER_PAR_SHARE * total_par_t)

            out[str(key)][str(t)] = {
                "d1": d1,
                "matched_n": int(valid.sum()),
                "comp_change": comp_change,
            }

    return out


# ---------------------------------------------------------------------------
# Dispersion helper
# ---------------------------------------------------------------------------

def _compute_dispersion(g_spreads: pd.Series) -> tuple[float | None, str | None]:
    """Compute g-spread dispersion per threshold rules.

    n >= DISPERSION_FLOOR_N (8): p90_p10 basis
    3 <= n < DISPERSION_FLOOR_N: max_min basis
    n < 3: null
    Returns (dispersion_bp, basis_string)
    Basis values EXACTLY: 'p90_p10', 'max_min', null (None)
    """
    vals = g_spreads.dropna()
    n = len(vals)
    if n < 3:
        return None, None
    if n < DISPERSION_FLOOR_N:
        return float(vals.max() - vals.min()), "max_min"
    p90 = float(np.percentile(vals, 90))
    p10 = float(np.percentile(vals, 10))
    return float(p90 - p10), "p90_p10"


# ---------------------------------------------------------------------------
# Aggregate builders
# ---------------------------------------------------------------------------

def _par_weighted_mean(values: pd.Series, weights: pd.Series) -> float | None:
    valid = values.notna() & weights.notna() & (weights > 0)
    if not valid.any():
        return None
    w = weights[valid]
    v = values[valid]
    return float((v * w).sum() / w.sum())


def _build_market_daily(
    panel: pd.DataFrame,
    sorted_dates: list,
) -> pd.DataFrame:
    """Build market_daily.parquet aggregates."""
    rows = []
    delta_market = compute_matched_delta(panel, sorted_dates, "segment", "market")
    for dt in sorted_dates:
        sub = panel[panel["as_of"] == dt]
        for seg in ["ig", "hy"]:
            grp = sub[sub["segment"] == seg]
            if grp.empty:
                continue
            delta_info = delta_market.get(seg, {}).get(str(dt), {})
            rows.append({
                "as_of": dt,
                "segment": seg,
                "n_bonds": len(grp),
                "par_total": float(grp["par"].sum()),
                "price_clean_pw": _par_weighted_mean(grp["price_clean"], grp["par"]),
                "ytm_pct_pw": _par_weighted_mean(grp["ytm_pct"], grp["par"]),
                "g_spread_bp_pw": _par_weighted_mean(grp["g_spread_bp"], grp["par"]),
                "wam_yrs": _par_weighted_mean(grp["tenor_yrs"], grp["par"]),
                "d1_g_spread_bp_matched": delta_info.get("d1"),
                "matched_n": delta_info.get("matched_n", 0),
                "composition_change": delta_info.get("comp_change", False),
            })
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def _build_issuer_daily(
    panel: pd.DataFrame,
    sorted_dates: list,
) -> pd.DataFrame:
    rows = []
    delta_issuer = compute_matched_delta(panel, sorted_dates, "issuer", "issuer")
    for dt in sorted_dates:
        sub = panel[(panel["as_of"] == dt) & panel["issuer"].notna()]
        for issuer, grp in sub.groupby("issuer", dropna=True):
            theme = grp["theme"].iloc[0] if not grp["theme"].isna().all() else None
            delta_info = delta_issuer.get(str(issuer), {}).get(str(dt), {})
            rows.append({
                "as_of": dt,
                "issuer": issuer,
                "theme": theme,
                "n_bonds": len(grp),
                "par_total": float(grp["par"].sum()),
                "price_clean_pw": _par_weighted_mean(grp["price_clean"], grp["par"]),
                "ytm_pct_pw": _par_weighted_mean(grp["ytm_pct"], grp["par"]),
                "g_spread_bp_pw": _par_weighted_mean(grp["g_spread_bp"], grp["par"]),
                "wam_yrs": _par_weighted_mean(grp["tenor_yrs"], grp["par"]),
                "d1_g_spread_bp_matched": delta_info.get("d1"),
                "matched_n": delta_info.get("matched_n", 0),
                "composition_change": delta_info.get("comp_change", False),
            })
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def _build_theme_daily(
    panel: pd.DataFrame,
    sorted_dates: list,
) -> pd.DataFrame:
    rows = []
    delta_theme = compute_matched_delta(panel, sorted_dates, "theme", "theme")
    for dt in sorted_dates:
        sub = panel[(panel["as_of"] == dt) & panel["theme"].notna()]
        for theme, grp in sub.groupby("theme", dropna=True):
            disp_bp, disp_basis = _compute_dispersion(grp["g_spread_bp"])
            n_near_par = int(grp["near_par_call_flag"].sum()) if "near_par_call_flag" in grp.columns else 0
            n_issuers = grp["issuer"].nunique()
            matched_par = grp["par"].sum()
            total_panel_par = panel[panel["as_of"] == dt]["par"].sum()
            matched_par_share = float(matched_par / total_panel_par) if total_panel_par > 0 else 0.0
            delta_info = delta_theme.get(str(theme), {}).get(str(dt), {})
            rows.append({
                "as_of": dt,
                "theme": theme,
                "n_bonds": len(grp),
                "n_issuers": n_issuers,
                "par_total": float(grp["par"].sum()),
                "price_clean_pw": _par_weighted_mean(grp["price_clean"], grp["par"]),
                "ytm_pct_pw": _par_weighted_mean(grp["ytm_pct"], grp["par"]),
                "g_spread_bp_pw": _par_weighted_mean(grp["g_spread_bp"], grp["par"]),
                "wam_yrs": _par_weighted_mean(grp["tenor_yrs"], grp["par"]),
                "dispersion_bp": disp_bp,
                "dispersion_basis": disp_basis,
                "dispersion_n": int(grp["g_spread_bp"].notna().sum()),
                "d1_g_spread_bp_matched": delta_info.get("d1"),
                "matched_n": delta_info.get("matched_n", 0),
                "matched_par_share": matched_par_share,
                "composition_change": delta_info.get("comp_change", False),
                "near_par_excluded_n": n_near_par,
            })
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def _build_sector_daily(
    panel: pd.DataFrame,
    sorted_dates: list,
) -> pd.DataFrame:
    rows = []
    delta_sector = compute_matched_delta(panel, sorted_dates, "sector", "sector")
    for dt in sorted_dates:
        sub = panel[(panel["as_of"] == dt) & panel["sector"].notna()]
        for sector, grp in sub.groupby("sector", dropna=True):
            delta_info = delta_sector.get(str(sector), {}).get(str(dt), {})
            rows.append({
                "as_of": dt,
                "sector": sector,
                "n_bonds": len(grp),
                "par_total": float(grp["par"].sum()),
                "ytm_pct_pw": _par_weighted_mean(grp["ytm_pct"], grp["par"]),
                "g_spread_bp_pw": _par_weighted_mean(grp["g_spread_bp"], grp["par"]),
                "d1_g_spread_bp_matched": delta_info.get("d1"),
                "matched_n": delta_info.get("matched_n", 0),
                "composition_change": delta_info.get("comp_change", False),
            })
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def _build_maturity_wall(
    panel: pd.DataFrame,
) -> pd.DataFrame:
    """Build maturity_wall.parquet: scope_type x scope x bucket x as_of."""
    rows = []
    for dt, sub in panel.groupby("as_of"):
        for bucket_key, lo, hi in MATURITY_BUCKETS:
            mask = (sub["tenor_yrs"] >= lo) & (sub["tenor_yrs"] < hi)
            bucket_sub = sub[mask]
            if not bucket_sub.empty:
                rows.append({
                    "as_of": dt,
                    "scope_type": "market",
                    "scope": "all",
                    "bucket": bucket_key,
                    "par_total": float(bucket_sub["par"].sum()),
                    "n_bonds": len(bucket_sub),
                })
            for seg in ["ig", "hy"]:
                seg_sub = bucket_sub[bucket_sub["segment"] == seg]
                rows.append({
                    "as_of": dt,
                    "scope_type": "market",
                    "scope": seg,
                    "bucket": bucket_key,
                    "par_total": float(seg_sub["par"].sum()) if not seg_sub.empty else 0.0,
                    "n_bonds": len(seg_sub),
                })
        # Theme-level
        for theme, theme_sub in sub.groupby("theme", dropna=True):
            for bucket_key, lo, hi in MATURITY_BUCKETS:
                mask = (theme_sub["tenor_yrs"] >= lo) & (theme_sub["tenor_yrs"] < hi)
                b_sub = theme_sub[mask]
                rows.append({
                    "as_of": dt,
                    "scope_type": "theme",
                    "scope": str(theme),
                    "bucket": bucket_key,
                    "par_total": float(b_sub["par"].sum()) if not b_sub.empty else 0.0,
                    "n_bonds": len(b_sub),
                })
        # Issuer-level
        for issuer, iss_sub in sub.groupby("issuer", dropna=True):
            for bucket_key, lo, hi in MATURITY_BUCKETS:
                mask = (iss_sub["tenor_yrs"] >= lo) & (iss_sub["tenor_yrs"] < hi)
                b_sub = iss_sub[mask]
                rows.append({
                    "as_of": dt,
                    "scope_type": "issuer",
                    "scope": str(issuer),
                    "bucket": bucket_key,
                    "par_total": float(b_sub["par"].sum()) if not b_sub.empty else 0.0,
                    "n_bonds": len(b_sub),
                })

    return pd.DataFrame(rows) if rows else pd.DataFrame()


# ---------------------------------------------------------------------------
# Validation (§3-P2)
# ---------------------------------------------------------------------------

def _ols_with_hc1(X: np.ndarray, y: np.ndarray) -> dict:
    """Hand-rolled OLS with HC1 robust standard errors.

    X: (n, k) design matrix (include intercept as first column of ones)
    y: (n,) response
    Returns {coefficients, hc1_se, t_stats, n, k}
    """
    n, k = X.shape
    XtX = X.T @ X
    try:
        XtX_inv = np.linalg.inv(XtX)
    except np.linalg.LinAlgError:
        return {}
    beta = XtX_inv @ X.T @ y
    e = y - X @ beta
    # HC1 sandwich: n/(n-k) * X^T diag(e^2) X
    meat = (X * e[:, None]).T @ (X * e[:, None])
    hc1_cov = (n / (n - k)) * XtX_inv @ meat @ XtX_inv
    hc1_se = np.sqrt(np.diag(hc1_cov))
    t_stats = beta / (hc1_se + 1e-30)
    return {"coefficients": beta.tolist(), "hc1_se": hc1_se.tolist(), "t_stats": t_stats.tolist(), "n": n, "k": k}


def _load_validation_samples(root: Path | None = None) -> dict[str, pd.DataFrame | None]:
    """Load iShares LQD/HYG validation samples if available."""
    data_root = _data_root(root)
    sample_dir = data_root / "corp_bonds" / "validation_sample"
    result: dict[str, pd.DataFrame | None] = {"LQD": None, "HYG": None}
    if not sample_dir.exists():
        return result
    for fund in ["LQD", "HYG"]:
        files = sorted(sample_dir.glob(f"{fund}_*.parquet"))
        if not files:
            continue
        try:
            df = pd.read_parquet(files[-1])  # latest
            result[fund] = df
        except Exception as exc:  # noqa: BLE001
            log.warning("corp_credit: validation sample %s load failed: %s", fund, exc)
    return result


def _normalize_name_token0(name: str) -> str:
    """Return the first uppercase letters-only token of a bond/fund name.

    Used for name-check in the coupon+maturity join: token[0] from our side
    must match token[0] from iShares side.
    """
    s = re.sub(r"[^A-Za-z\s]", " ", name).upper().split()
    return s[0] if s else ""


def _join_panel_to_sample(
    panel_sub: pd.DataFrame,
    sample: pd.DataFrame,
) -> pd.DataFrame:
    """Inner join SSGA panel rows to iShares sample on (coupon.round(3), maturity date).

    Join key: str(coupon.round(3)) + "|" + maturity_yyyymmdd.
    Duplicate keys on EITHER side are dropped (keep=False) before the join.
    After joining, rows where the first normalized name token differs are dropped.

    Parameters
    ----------
    panel_sub : DataFrame
        Latest-as_of SSGA panel rows for the relevant segment.
        Must have columns: coupon, maturity, name, and all needed engine cols.
    sample : DataFrame
        iShares validation sample. Must have columns: coupon, maturity, name.

    Returns
    -------
    Merged DataFrame.  May be empty.  Column suffixes: none added for panel
    cols, sample cols suffixed with '_is'.
    """
    # Build join key on panel side
    panel_cp = panel_sub.copy()
    panel_valid = panel_cp["coupon"].notna() & panel_cp["maturity"].notna()
    panel_cp = panel_cp[panel_valid].copy()
    panel_cp["_jkey"] = (
        panel_cp["coupon"].round(3).astype(str)
        + "|"
        + pd.to_datetime(panel_cp["maturity"], errors="coerce").dt.strftime("%Y%m%d").fillna("")
    )
    # Drop duplicate keys on panel side
    panel_cp = panel_cp[~panel_cp["_jkey"].duplicated(keep=False)].copy()

    # Build join key on sample side
    samp_cp = sample.copy()
    samp_valid = samp_cp["coupon"].notna() & samp_cp["maturity"].notna()
    samp_cp = samp_cp[samp_valid].copy()
    samp_cp["_jkey"] = (
        samp_cp["coupon"].round(3).astype(str)
        + "|"
        + pd.to_datetime(samp_cp["maturity"], errors="coerce").dt.strftime("%Y%m%d").fillna("")
    )
    # Drop duplicate keys on sample side
    samp_cp = samp_cp[~samp_cp["_jkey"].duplicated(keep=False)].copy()

    if panel_cp.empty or samp_cp.empty:
        return pd.DataFrame()

    # Inner join
    merged = panel_cp.merge(samp_cp, on="_jkey", how="inner", suffixes=("", "_is"))

    if merged.empty:
        return merged

    # Name-token check: first normalized token must match
    our_tok = merged["name"].fillna("").apply(_normalize_name_token0)
    is_name_col = "name_is" if "name_is" in merged.columns else None
    if is_name_col is not None:
        is_tok = merged[is_name_col].fillna("").apply(_normalize_name_token0)
        token_match = (our_tok == is_tok) & (our_tok != "")
        merged = merged[token_match].copy()

    merged = merged.drop(columns=["_jkey"], errors="ignore")
    log.info("corp_credit: validation join: %d matched bonds", len(merged))
    print(f"  validation join: n_joined={len(merged)}")
    return merged


def resolve_price_convention(joined_df: pd.DataFrame, panel_date: str | None = None) -> dict:
    """Determine the price convention (dirty vs clean) from a joined validation panel.

    Pure function — operates only on ``joined_df`` (output of ``_join_panel_to_sample``)
    and the panel date string (used to compute tenors for the YTM tiebreak).

    Returns a dict with keys:
      verdict          — "dirty" | "clean" | "ambiguous"
      tiebreak_fired   — bool
      slope            — OLS slope (float | None)
      hc1_se           — HC1 standard error on slope (float | None)
      n_joined         — int
      median_diff      — float | None
      median_accrued   — float | None
      median_resid     — float | None
      tiebreak_dirty_median_bp  — float | None  (only when tiebreak_fired)
      tiebreak_clean_median_bp  — float | None  (only when tiebreak_fired)

    Decision rule: OLS slope of (price_dirty_raw − clean_price) ~ [1, accrued]:
      slope ∈ [0.7, 1.3]  → "dirty"
      slope ∈ [−0.3, 0.3] → "clean"
      otherwise            → "ambiguous"; tiebreak fires: solve YTM under both conventions,
                             the one with lower median absolute error vs iShares YTM wins.
    """
    clean_price_col = "clean_price_is" if "clean_price_is" in joined_df.columns else "clean_price"
    diff = joined_df["price_dirty_raw"] - joined_df[clean_price_col]
    accrued_ref = (
        joined_df["accrued_pct"]
        if "accrued_pct" in joined_df.columns
        else pd.Series(0.0, index=joined_df.index)
    )

    valid_mask = diff.notna() & accrued_ref.notna()
    diff_v = diff[valid_mask].values
    accrued_v = accrued_ref[valid_mask].values
    X = np.column_stack([np.ones(len(diff_v)), accrued_v])
    ols_res = _ols_with_hc1(X, diff_v)
    slope = ols_res["coefficients"][1] if ols_res else float("nan")
    hc1_se = ols_res["hc1_se"][1] if ols_res else float("nan")
    n_joined = int(valid_mask.sum())

    median_diff = float(np.median(diff_v)) if len(diff_v) else float("nan")
    median_accrued = float(np.median(accrued_v)) if len(accrued_v) else float("nan")
    resid_v = diff_v - accrued_v
    median_resid = float(np.median(resid_v)) if len(resid_v) else float("nan")

    if not math.isnan(slope) and 0.7 <= slope <= 1.3:
        verdict = "dirty"
    elif not math.isnan(slope) and -0.3 <= slope <= 0.3:
        verdict = "clean"
    else:
        verdict = "ambiguous"

    tiebreak_fired = False
    tb_dirty_bp: float | None = None
    tb_clean_bp: float | None = None

    if verdict == "ambiguous":
        tiebreak_fired = True
        panel_date_dt = pd.to_datetime(panel_date) if panel_date else pd.Timestamp.now()
        maturity_dt = pd.to_datetime(joined_df["maturity"], errors="coerce")
        tenor_v = (
            ((maturity_dt - panel_date_dt).dt.days / 365.25)
            .fillna(0.5)
            .clip(lower=0.5)
            .values
        )

        def _median_ytm_err_bp(convention_name: str) -> float:
            if convention_name == "dirty":
                dirty_p = joined_df["price_dirty_raw"].values.astype(float)
            else:
                acc = (
                    joined_df["accrued_pct"].values.astype(float)
                    if "accrued_pct" in joined_df.columns
                    else np.zeros(len(joined_df))
                )
                dirty_p = joined_df["price_dirty_raw"].values.astype(float) + acc
            coupon_v = joined_df["coupon"].values.astype(float)
            ytm_solved, _flags = _ytm_solve(dirty_p, coupon_v, tenor_v)
            ytm_pct_solved = ytm_solved * 100.0
            sample_ytm = joined_df["ytm_pct_is"].values.astype(float)
            valid = ~np.isnan(ytm_pct_solved) & ~np.isnan(sample_ytm)
            if valid.sum() == 0:
                return float("nan")
            return float(np.median(np.abs(ytm_pct_solved[valid] - sample_ytm[valid]) * 100.0))

        tb_dirty_bp = _median_ytm_err_bp("dirty")
        tb_clean_bp = _median_ytm_err_bp("clean")
        print(f"  tiebreak: dirty_median_bp={tb_dirty_bp:.2f}  clean_median_bp={tb_clean_bp:.2f}")
        verdict = "dirty" if (math.isnan(tb_clean_bp) or tb_dirty_bp <= tb_clean_bp) else "clean"

    return {
        "verdict": verdict,
        "tiebreak_fired": tiebreak_fired,
        "slope": round(slope, 4) if not math.isnan(slope) else None,
        "hc1_se": round(hc1_se, 4) if not math.isnan(hc1_se) else None,
        "n_joined": n_joined,
        "median_diff": round(median_diff, 4) if not math.isnan(median_diff) else None,
        "median_accrued": round(median_accrued, 4) if not math.isnan(median_accrued) else None,
        "median_resid": round(median_resid, 4) if not math.isnan(median_resid) else None,
        "tiebreak_dirty_median_bp": round(tb_dirty_bp, 2) if tb_dirty_bp is not None and not math.isnan(tb_dirty_bp) else None,
        "tiebreak_clean_median_bp": round(tb_clean_bp, 2) if tb_clean_bp is not None and not math.isnan(tb_clean_bp) else None,
    }


def run_validation(
    panel: pd.DataFrame,
    market_daily: pd.DataFrame,
    baml_oas: pd.Series | None,
    root: Path | None = None,
) -> dict:
    """Run the four pre-registered CCW §3-P2 validation criteria.

    Returns the validation dict (written to data/corp_bonds/validation.json).
    """
    criteria: dict[str, Any] = {}
    samples = _load_validation_samples(root)
    price_convention = "dirty"  # default; updated by criterion (a)

    # ------------------------------------------------------------------
    # (a) dirty_vs_clean — price convention verdict
    # ------------------------------------------------------------------
    lqd_sample = samples["LQD"]
    crit_a: dict[str, Any] = {}

    # Capture sample metadata
    sample_meta: dict[str, Any] = {}
    if lqd_sample is not None:
        lqd_as_of = str(lqd_sample["as_of"].iloc[0]) if "as_of" in lqd_sample.columns and len(lqd_sample) > 0 else None
        sample_meta["LQD"] = {
            "as_of": lqd_as_of,
            "n_rows": len(lqd_sample),
        }

    if lqd_sample is None or panel.empty:
        crit_a["status"] = "PENDING_SAMPLE"
        crit_a["detail"] = "iShares LQD validation sample not yet fetched (run scripts/fetch_ishares_validation_sample.py)"
    else:
        try:
            latest_dt = panel["as_of"].max()
            sub = panel[panel["as_of"] == latest_dt].copy()

            # New join: coupon+maturity key with first-name-token check (no ISIN)
            merged = _join_panel_to_sample(sub, lqd_sample)

            if len(merged) < 5:
                crit_a["status"] = "PENDING_SAMPLE"
                crit_a["detail"] = f"too few joined bonds: {len(merged)} (need >=5)"
            else:
                # Date gap between SSGA panel and iShares sample
                panel_date = pd.to_datetime(latest_dt)
                lqd_as_of = lqd_sample["as_of"].iloc[0] if "as_of" in lqd_sample.columns else None
                date_gap = int(abs((panel_date - pd.to_datetime(lqd_as_of)).days)) if lqd_as_of else 999
                if "LQD" in sample_meta:
                    sample_meta["LQD"]["date_gap_days"] = date_gap

                # Decision rule delegated to the extracted pure function
                pc_result = resolve_price_convention(merged, str(latest_dt))
                probe1_verdict = pc_result["verdict"]
                price_convention = probe1_verdict
                crit_a["status"] = "PASS"
                crit_a["probe1"] = {
                    **pc_result,
                    "date_gap_days": date_gap,
                    "note": (
                        "verdict keys on slope because level diffs (median_diff) absorb "
                        "the date-gap market move; median_resid = diff - accrued"
                    ),
                }
        except Exception as exc:  # noqa: BLE001
            crit_a["status"] = "ERROR"
            crit_a["detail"] = str(exc)

    # Probe 2 (internal): OLS of price_dirty_raw on [1, coupon, tenor, coupon*tenor, accrued]
    if not panel.empty:
        try:
            ig_sub = panel[(panel["segment"] == "ig") & panel["price_dirty_raw"].notna() & panel["accrued_pct"].notna()]
            if len(ig_sub) >= 10:
                y_arr = ig_sub["price_dirty_raw"].values
                X_arr = np.column_stack([
                    np.ones(len(ig_sub)),
                    ig_sub["coupon"].values,
                    ig_sub["tenor_yrs"].fillna(5.0).values,
                    ig_sub["coupon"].values * ig_sub["tenor_yrs"].fillna(5.0).values,
                    ig_sub["accrued_pct"].values,
                ])
                ols_p2 = _ols_with_hc1(X_arr, y_arr)
                if ols_p2:
                    accrued_coef = ols_p2["coefficients"][4]
                    accrued_se = ols_p2["hc1_se"][4]
                    ci_lo = accrued_coef - 1.96 * accrued_se
                    ci_hi = accrued_coef + 1.96 * accrued_se
                    crit_a["probe2"] = {
                        "accrued_coefficient": round(accrued_coef, 4),
                        "hc1_95ci": [round(ci_lo, 4), round(ci_hi, 4)],
                        "n": len(ig_sub),
                        "detail": "cross-sectional OLS of price_dirty_raw on [1, coupon, tenor, coupon*tenor, accrued]",
                    }
        except Exception as exc:  # noqa: BLE001
            crit_a.setdefault("probe2", {})["error"] = str(exc)

    criteria["a"] = crit_a

    # ------------------------------------------------------------------
    # (b) ytm_vs_ishares — uses the resolved convention's YTM
    # ------------------------------------------------------------------
    crit_b: dict[str, Any] = {}
    if lqd_sample is None:
        crit_b["status"] = "PENDING_SAMPLE"
        crit_b["detail"] = "LQD sample absent"
    elif panel.empty:
        crit_b["status"] = "PENDING_SAMPLE"
        crit_b["detail"] = "panel empty"
    else:
        try:
            for fund, samp, seg, gate in [("LQD", lqd_sample, "ig", True), ("HYG", samples["HYG"], "hy", False)]:
                if samp is None:
                    crit_b[fund] = {"status": "PENDING_SAMPLE"}
                    continue
                latest_dt = panel["as_of"].max()
                sub = panel[(panel["as_of"] == latest_dt) & (panel["segment"] == seg)].copy()

                # New join: coupon+maturity key with first-name-token check
                joined = _join_panel_to_sample(sub, samp)
                if joined.empty:
                    crit_b[fund] = {"status": "PENDING_SAMPLE", "n_joined": 0}
                    continue

                # Sort by par descending (our side)
                joined = joined.sort_values("par", ascending=False)

                if len(joined) < 5:
                    crit_b[fund] = {"status": "PENDING_SAMPLE", "n_joined": len(joined)}
                    continue

                # Accrual fraction spanning
                joined["accrual_frac"] = (joined["accrued_pct"] / (joined["coupon"] / 2.0)).clip(0, 0.999)
                bins = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
                joined["quintile"] = pd.cut(joined["accrual_frac"], bins=bins, right=False, labels=False)

                # Take top 20 by par, then expand until 4 of 5 quintiles occupied
                sample_n = 20
                while sample_n <= len(joined):
                    top = joined.head(sample_n)
                    bins_occupied = top["quintile"].dropna().nunique()
                    if bins_occupied >= 4:
                        break
                    sample_n += 5

                top = joined.head(min(sample_n, len(joined)))
                # Our ytm_pct is computed under the resolved convention (ytm_pct column on panel)
                abs_err_bp = np.abs(top["ytm_pct"] - top["ytm_pct_is"]) * 100.0

                lqd_as_of_dt = samp["as_of"].iloc[0] if "as_of" in samp.columns and len(samp) > 0 else None
                date_gap = int(abs((pd.to_datetime(latest_dt) - pd.to_datetime(lqd_as_of_dt)).days)) if lqd_as_of_dt else 999
                if fund not in sample_meta:
                    sample_meta[fund] = {"as_of": str(lqd_as_of_dt), "n_rows": len(samp), "date_gap_days": date_gap}
                else:
                    sample_meta[fund]["date_gap_days"] = date_gap

                n_used = len(top)
                bins_used = int(top["quintile"].dropna().nunique())
                median_bp = float(abs_err_bp.median())

                # Pre-registered gate (masterplan §3-P2): all three conditions required:
                #   (1) median abs YTM error ≤ 25bp
                #   (2) sample used ≥ 20 bonds (largest-par)
                #   (3) sample spans ≥ 4 of 5 accrual-fraction quintile bins
                # <5 joined → PENDING_SAMPLE (handled above).
                # ≥5 joined but n<20 or bins<4 → FAIL with detail naming the failed condition.
                if gate:
                    cond_median = median_bp <= 25.0
                    cond_n = n_used >= 20
                    cond_bins = bins_used >= 4
                    if cond_median and cond_n and cond_bins:
                        status = "PASS"
                    else:
                        status = "FAIL"
                        failed = []
                        if not cond_median:
                            failed.append(f"median_bp={median_bp:.2f} > 25.0")
                        if not cond_n:
                            failed.append(f"n={n_used} < 20")
                        if not cond_bins:
                            failed.append(f"bins_occupied={bins_used} < 4")
                        crit_b.setdefault("_fail_detail", {})[fund] = "; ".join(failed)
                else:
                    status = "PASS"

                crit_b[fund] = {
                    "status": status,
                    "n": n_used,
                    "n_joined": len(joined),
                    "median_bp": round(median_bp, 2),
                    "p90_bp": round(float(np.percentile(abs_err_bp, 90)), 2),
                    "share_within_25bp": round(float((abs_err_bp <= 25).mean()), 4),
                    "bins_occupied": bins_used,
                    "date_gap_days": date_gap,
                    "gating": gate,
                }

            # Overall (b) status: gated on LQD IG result
            if "LQD" in crit_b and crit_b["LQD"].get("status") not in ("PENDING_SAMPLE", "ERROR"):
                crit_b["status"] = crit_b["LQD"]["status"]
            else:
                crit_b["status"] = "PENDING_SAMPLE"
        except Exception as exc:  # noqa: BLE001
            crit_b["status"] = "ERROR"
            crit_b["detail"] = str(exc)

    criteria["b"] = crit_b

    # ------------------------------------------------------------------
    # (c) ig_gspread_vs_baml
    # ------------------------------------------------------------------
    crit_c: dict[str, Any] = {}
    if baml_oas is None or market_daily.empty:
        crit_c["status"] = "FAIL"
        crit_c["detail"] = "BAML OAS or market_daily not available"
    else:
        try:
            ig_rows = market_daily[market_daily["segment"] == "ig"].copy()
            if ig_rows.empty:
                crit_c["status"] = "FAIL"
                crit_c["detail"] = "no IG rows in market_daily"
            else:
                ig_rows["as_of_dt"] = pd.to_datetime(ig_rows["as_of"])
                baml_df = baml_oas.reset_index()
                baml_df.columns = ["date", "oas_pct"]
                baml_df["date"] = pd.to_datetime(baml_df["date"])

                overlaps = []
                for _, row in ig_rows.iterrows():
                    dt = row["as_of_dt"]
                    gs = row["g_spread_bp_pw"]
                    if pd.isna(gs):
                        continue
                    # Find closest BAML date
                    idx = (baml_df["date"] - dt).abs().idxmin()
                    gap = abs((baml_df.loc[idx, "date"] - dt).days)
                    if gap <= 7:
                        oas_pct = baml_df.loc[idx, "oas_pct"]
                        oas_bp = oas_pct * 100.0
                        diff_bp = abs(float(gs) - float(oas_bp))
                        overlaps.append({
                            "as_of": str(row["as_of"]),
                            "g_spread_bp_pw": round(float(gs), 2),
                            "baml_oas_bp": round(float(oas_bp), 2),
                            "diff_bp": round(diff_bp, 2),
                        })

                if not overlaps:
                    crit_c["status"] = "FAIL"
                    crit_c["detail"] = "no overlapping dates between market_daily and BAML OAS"
                else:
                    latest_diff = overlaps[-1]["diff_bp"]
                    crit_c["status"] = "PASS" if latest_diff <= 30.0 else "FAIL"
                    crit_c["latest_diff_bp"] = latest_diff
                    crit_c["overlaps"] = overlaps
                    crit_c["threshold_bp"] = 30.0
        except Exception as exc:  # noqa: BLE001
            crit_c["status"] = "ERROR"
            crit_c["detail"] = str(exc)

    criteria["c"] = crit_c

    # ------------------------------------------------------------------
    # (d) composition_guard fixture
    # ------------------------------------------------------------------
    crit_d: dict[str, Any] = {}
    try:
        result_d = _run_composition_fixture()
        crit_d.update(result_d)
    except Exception as exc:  # noqa: BLE001
        crit_d["status"] = "ERROR"
        crit_d["detail"] = str(exc)

    criteria["d"] = crit_d

    # Overall
    all_statuses = [v.get("status", "FAIL") for v in criteria.values()]
    if all(s == "PASS" for s in all_statuses):
        overall = "PASS"
    elif any(s == "PENDING_SAMPLE" for s in all_statuses):
        overall = "PENDING"
    else:
        overall = "FAIL"

    return {
        "as_of": str(date.today()),
        "price_convention": price_convention,
        "criteria": criteria,
        "overall": overall,
        "sample_metadata": sample_meta,
        "notes": [
            "accrual-fraction spanning is cross-sectional at W2 (single holdings date on disk); "
            "the time-axis sawtooth check strengthens automatically as holdings dates accrue "
            "and criterion (a)/(c) re-print nightly",
        ],
    }


def _run_composition_fixture() -> dict:
    """Synthetic composition-guard fixture (validation criterion d).

    30 bonds, 16 dates, stable spreads ~150bp ±2bp noise.
    On date index 8 (the INJECTION date): inject one new tranche with par = 40%
    of original panel par and spread 300bp.  The tranche persists through date 15.

    Uses the production ``compute_matched_delta`` function (scope_col='segment',
    group_key='ig') to compute matched-panel deltas — NOT a reimplementation.

    ENTRY_SEASONING_BARS boundary: tranche first_seen = sorted_dates[8].
    For date t at t_idx = 8+k, seasoning_cutoff = sorted_dates[3+k].
    Tranche excluded (first_seen > cutoff) when 8 > 3+k, i.e. k < 5.
    Tranche first INCLUDED at k=5, i.e. t_idx=13 (sorted_dates[13]).

    PASS conditions verified via production code:
      (1) naive full-panel delta on injection date (t_idx=8) > 20bp
      (2) production matched delta on injection date within ±2bp
      (3) composition_change True on injection date (from production compute_matched_delta)
      (4) tranche excluded from matched set on dates 8..12 (k=0..4): matched delta ≤ ±2bp
      (5) tranche included at exactly t_idx=13 (k=5): matched_n increments by 1 vs t_idx=12
    """
    from datetime import timedelta

    rng = np.random.default_rng(42)
    n_bonds = 30
    n_dates = 16  # extended to 16 so tranche seasons within the panel

    # Fixed ISINs for the stable base bonds
    isins = [f"US{i:09d}X1" for i in range(n_bonds)]
    coupon = 5.0
    par_per_bond = 1_000_000.0
    base_spread = 150.0  # bp
    noise = rng.normal(0, 2.0, (n_dates, n_bonds))

    base_date = date(2026, 1, 2)
    sorted_dates = [(base_date + timedelta(days=i)).isoformat() for i in range(n_dates)]

    # --- Build the panel DataFrame (same shape compute_matched_delta consumes) ---
    rows = []
    maturity_str = "2031-07-10"
    # All base bonds present at all dates; first_seen = sorted_dates[0] for all of them.
    for d_idx, dt in enumerate(sorted_dates):
        for b_idx, isin in enumerate(isins):
            spread = base_spread + noise[d_idx, b_idx]
            rows.append({
                "as_of": dt,
                "isin": isin,
                "par": par_per_bond,
                "coupon": coupon,
                "maturity": maturity_str,
                "tenor_yrs": 5.0,
                "g_spread_bp": spread,
                "price_clean": 100.0,
                "near_par_call_flag": False,
                "first_seen": sorted_dates[0],
                "segment": "ig",
                "issuer": f"ISSUER_{b_idx}",
                "theme": "test_theme",
                "sector": "Financials",
            })

    # Injection at date index 8; tranche persists through date 15
    tranche_isin = "USNEW00001X1"
    tranche_par = n_bonds * par_per_bond * 0.4  # 40% of original panel par
    injection_idx = 8
    dt_injection = sorted_dates[injection_idx]
    for d_idx in range(injection_idx, n_dates):
        rows.append({
            "as_of": sorted_dates[d_idx],
            "isin": tranche_isin,
            "par": tranche_par,
            "coupon": coupon,
            "maturity": maturity_str,
            "tenor_yrs": 5.0,
            "g_spread_bp": 300.0,   # stable 300bp post-entry (matched delta stays near 0)
            "price_clean": 95.0,
            "near_par_call_flag": False,
            "first_seen": dt_injection,  # set below via recompute; hard-coded here for clarity
            "segment": "ig",
            "issuer": "NEW_ISSUER",
            "theme": "test_theme",
            "sector": "Financials",
        })

    panel = pd.DataFrame(rows)

    # Recompute first_seen from the actual panel (matches production compute_first_seen idiom)
    fs_map = panel.groupby("isin")["as_of"].min().to_dict()
    panel["first_seen"] = panel["isin"].map(fs_map)

    # --- Assertion (1): naive full-panel Δ on injection date > 20bp ---
    # Compare t_prev = sorted_dates[7] → t = sorted_dates[8]
    t_prev_str = sorted_dates[injection_idx - 1]
    t_inj_str = sorted_dates[injection_idx]
    panel_prev = panel[panel["as_of"] == t_prev_str]
    panel_inj = panel[panel["as_of"] == t_inj_str]

    par_prev = panel_prev["par"].sum()
    par_inj = panel_inj["par"].sum()
    gs_prev = float((panel_prev["g_spread_bp"] * panel_prev["par"]).sum() / par_prev)
    gs_inj = float((panel_inj["g_spread_bp"] * panel_inj["par"]).sum() / par_inj)
    naive_delta_bp = gs_inj - gs_prev

    # --- Assertions (2), (3), (4), (5): via production compute_matched_delta ---
    # scope_col='segment', group_key='ig' so all ig bonds go through one group.
    md = compute_matched_delta(panel, sorted_dates, scope_col="segment", group_key="segment")
    ig_deltas = md.get("ig", {})

    # (2) matched delta on injection date within ±2bp
    inj_entry = ig_deltas.get(t_inj_str, {})
    matched_delta_bp = inj_entry.get("d1", None)

    # (3) composition_change True on injection date
    comp_change_on_injection = inj_entry.get("comp_change", False)

    # (4) tranche excluded for 5 bars (k=0..4, t_idx=8..12): matched delta ≤ ±2bp on all 5
    seasoning_exclusion_checks = {}
    for k in range(ENTRY_SEASONING_BARS):
        t_k_str = sorted_dates[injection_idx + k]
        entry_k = ig_deltas.get(t_k_str, {})
        d1_k = entry_k.get("d1", None)
        mn_k = entry_k.get("matched_n", 0)
        seasoning_exclusion_checks[f"k{k}_matched_delta_within_2bp"] = (
            d1_k is not None and abs(d1_k) <= 2.0
        )
        seasoning_exclusion_checks[f"k{k}_matched_n"] = mn_k

    # (5) at entry offset 5 (t_idx=13), matched_n increments by 1 vs t_idx=12
    # Boundary: t_idx=13, t_idx=12
    t_boundary_str = sorted_dates[injection_idx + ENTRY_SEASONING_BARS]      # t_idx=13
    t_pre_boundary_str = sorted_dates[injection_idx + ENTRY_SEASONING_BARS - 1]  # t_idx=12
    entry_boundary = ig_deltas.get(t_boundary_str, {})
    entry_pre_boundary = ig_deltas.get(t_pre_boundary_str, {})
    mn_at_boundary = entry_boundary.get("matched_n", 0)
    mn_pre_boundary = entry_pre_boundary.get("matched_n", 0)
    tranche_included_at_boundary = mn_at_boundary == mn_pre_boundary + 1
    boundary_matched_delta_within_2bp = (
        entry_boundary.get("d1") is not None and abs(entry_boundary.get("d1", 999)) <= 2.0
    )

    pass1 = naive_delta_bp > 20.0
    pass2 = matched_delta_bp is not None and abs(matched_delta_bp) <= 2.0
    pass3 = comp_change_on_injection
    pass4 = all(seasoning_exclusion_checks[f"k{k}_matched_delta_within_2bp"] for k in range(ENTRY_SEASONING_BARS))
    pass5 = tranche_included_at_boundary and boundary_matched_delta_within_2bp

    status = "PASS" if (pass1 and pass2 and pass3 and pass4 and pass5) else "FAIL"
    return {
        "status": status,
        "naive_delta_bp": round(naive_delta_bp, 4),
        "matched_delta_bp": round(matched_delta_bp, 4) if matched_delta_bp is not None else None,
        "composition_change_on_injection": comp_change_on_injection,
        "injection_date_idx": injection_idx,
        "boundary_date_idx": injection_idx + ENTRY_SEASONING_BARS,
        "matched_n_pre_boundary": mn_pre_boundary,
        "matched_n_at_boundary": mn_at_boundary,
        "checks": {
            "naive_delta_gt_20bp": pass1,
            "matched_delta_within_2bp": pass2,
            "comp_change_flag_true": pass3,
            "tranche_excluded_5bars": pass4,
            "tranche_included_at_boundary": pass5,
        },
        "seasoning_exclusion_detail": seasoning_exclusion_checks,
    }


# ---------------------------------------------------------------------------
# Main snapshot function
# ---------------------------------------------------------------------------

def snapshot(root: str | Path | None = None) -> dict:
    """Build the corp_credit.v1 snapshot.

    Reads all holdings parquets, runs the g-spread pipeline, writes series/,
    latest.json, and validation.json. Never raises — degrades gracefully.
    Returns the payload dict.
    """
    t0 = time.time()
    _root = Path(root) if root is not None else None
    data_root = _data_root(_root)

    # -------------------------------------------------------------------------
    # Load inputs
    # -------------------------------------------------------------------------
    log.info("corp_credit: loading holdings")
    raw_holdings = _load_holdings(_root)
    if raw_holdings.empty:
        log.warning("corp_credit: no holdings data — writing empty artifacts")
        _write_empty_artifacts(data_root)
        elapsed = time.time() - t0
        log.info("[timing] corp_credit.snapshot: %.2fs", elapsed)
        return {"organ": "corp_credit.v1", "error": "no_holdings_data"}

    registry = _load_issuer_registry(_root)
    curve_df = _load_cmt_curve(_root)
    baml_oas = _load_baml_oas(_root)
    ticker_sectors = _load_ticker_sectors(_root)
    constituent_name_sector = _load_constituents_name_sector(_root)

    present_pillars = [sid for sid, _ in CMT_PILLARS
                       if (data_root / "fred" / f"{sid}.parquet").exists()]

    # -------------------------------------------------------------------------
    # Step 1: Canonicalize
    # -------------------------------------------------------------------------
    log.info("corp_credit: canonicalizing %d raw rows across %d dates",
             len(raw_holdings), raw_holdings["as_of"].nunique())
    panel = canonicalize_bonds(raw_holdings)
    n_dropped = int(panel["dropped_rows"].iloc[0]) if not panel.empty and "dropped_rows" in panel.columns else 0
    if not panel.empty:
        panel = panel.drop(columns=["dropped_rows", "hy_par", "ig_par"], errors="ignore")

    if panel.empty:
        log.warning("corp_credit: empty panel after canonicalization")
        _write_empty_artifacts(data_root)
        elapsed = time.time() - t0
        log.info("[timing] corp_credit.snapshot: %.2fs", elapsed)
        return {"organ": "corp_credit.v1", "error": "empty_panel"}

    # -------------------------------------------------------------------------
    # Step 2: Accrued interest
    # -------------------------------------------------------------------------
    log.info("corp_credit: computing accrued interest (30/360 US)")
    panel["as_of_dt"] = pd.to_datetime(panel["as_of"])
    panel["accrued_pct"] = accrued_30_360_us(
        panel["as_of_dt"].dt.strftime("%Y-%m-%d"),
        panel["maturity"],
        panel["coupon"],
    )

    # -------------------------------------------------------------------------
    # Step 3: Price convention (default "dirty"; updated after validation)
    # -------------------------------------------------------------------------
    convention = "dirty"
    panel["price_dirty"], panel["price_clean"] = apply_price_convention(
        panel["price_dirty_raw"], panel["accrued_pct"], convention
    )

    # -------------------------------------------------------------------------
    # Step 4: Tenor
    # -------------------------------------------------------------------------
    maturity_dt = pd.to_datetime(panel["maturity"], errors="coerce")
    as_of_dt = pd.to_datetime(panel["as_of"])
    panel["tenor_yrs"] = (maturity_dt - as_of_dt).dt.days / 365.25

    # Mark bonds too close to maturity for YTM/g-spread
    short_maturity_mask = panel["tenor_yrs"] < MIN_TENOR

    # -------------------------------------------------------------------------
    # Step 5: YTM solve (vectorized) — only on bonds with sufficient tenor
    # -------------------------------------------------------------------------
    log.info("corp_credit: solving YTM for %d bonds", len(panel))
    ytm_arr = np.full(len(panel), np.nan)
    flag_arr = np.full(len(panel), 2, dtype=int)

    active_mask = ~short_maturity_mask & panel["tenor_yrs"].notna() & panel["coupon"].notna() & panel["price_dirty"].notna()

    if active_mask.any():
        active_idx = panel.index[active_mask]
        ytm_solved, flags = _ytm_solve(
            panel.loc[active_mask, "price_dirty"].values.astype(float),
            panel.loc[active_mask, "coupon"].values.astype(float),
            panel.loc[active_mask, "tenor_yrs"].values.astype(float),
        )
        ytm_arr[panel.index.get_indexer(active_idx)] = ytm_solved
        flag_arr[panel.index.get_indexer(active_idx)] = flags

    panel["ytm_pct"] = ytm_arr * 100.0  # convert decimal → percent
    panel["_solver_flag"] = flag_arr

    newton_n = int((flag_arr[active_mask.values] == 0).sum()) if active_mask.any() else 0
    bisect_n = int((flag_arr[active_mask.values] == 1).sum()) if active_mask.any() else 0
    failed_n = int((flag_arr[active_mask.values] == 2).sum()) if active_mask.any() else 0

    log.info("corp_credit: YTM solver: newton=%d bisection=%d failed=%d",
             newton_n, bisect_n, failed_n)

    # -------------------------------------------------------------------------
    # Step 6: G-spread
    # -------------------------------------------------------------------------
    log.info("corp_credit: computing g-spreads")
    cmt_pct, g_spread_bp = compute_g_spread_bp(
        panel["ytm_pct"], panel["tenor_yrs"], panel["as_of"], curve_df
    )
    panel["cmt_pct"] = cmt_pct
    panel["g_spread_bp"] = g_spread_bp

    # -------------------------------------------------------------------------
    # Step 7: Issuer/theme matching
    # -------------------------------------------------------------------------
    log.info("corp_credit: matching issuers")
    panel["issuer"], panel["theme"] = match_issuers(panel, registry)

    # -------------------------------------------------------------------------
    # Step 8: Sector mapping
    # -------------------------------------------------------------------------
    log.info("corp_credit: mapping sectors")
    panel["sector"] = map_sectors(panel, registry, ticker_sectors, constituent_name_sector)

    # Sector mapped par share
    sector_mapped_par = panel.loc[panel["sector"].notna(), "par"].sum()
    total_par = panel["par"].sum()
    sector_mapped_par_share = float(sector_mapped_par / total_par) if total_par > 0 else 0.0
    log.info("corp_credit: sector mapped par share: %.1f%%", 100 * sector_mapped_par_share)

    # -------------------------------------------------------------------------
    # Step 9: Near-par callable HY flag
    # -------------------------------------------------------------------------
    panel["near_par_call_flag"] = compute_near_par_flag(panel["segment"], panel["price_clean"])

    # -------------------------------------------------------------------------
    # Step 10: Matched-panel guard (first_seen)
    # -------------------------------------------------------------------------
    panel["first_seen"] = compute_first_seen(panel)

    # -------------------------------------------------------------------------
    # Registry matched par share
    # -------------------------------------------------------------------------
    registry_matched_par = panel.loc[panel["issuer"].notna(), "par"].sum()
    matched_par_share = float(registry_matched_par / total_par) if total_par > 0 else 0.0

    # -------------------------------------------------------------------------
    # Sort panel for deterministic output
    # -------------------------------------------------------------------------
    sorted_dates = sorted(panel["as_of"].unique().tolist())
    panel = panel.sort_values(["as_of", "isin"]).reset_index(drop=True)

    # -------------------------------------------------------------------------
    # Build aggregates
    # -------------------------------------------------------------------------
    log.info("corp_credit: building aggregates (dates=%d)", len(sorted_dates))
    market_daily = _build_market_daily(panel, sorted_dates)
    issuer_daily = _build_issuer_daily(panel, sorted_dates)
    theme_daily = _build_theme_daily(panel, sorted_dates)
    sector_daily = _build_sector_daily(panel, sorted_dates)
    maturity_wall = _build_maturity_wall(panel)

    # bond_panel_latest: latest as_of only, per-bond
    latest_dt = sorted_dates[-1] if sorted_dates else ""
    bond_latest_cols = [
        "as_of", "isin", "cusip6", "name", "funds", "segment",
        "issuer", "theme", "sector", "coupon", "maturity", "tenor_yrs",
        "par", "mv", "price_dirty", "accrued_pct", "price_clean",
        "ytm_pct", "cmt_pct", "g_spread_bp", "near_par_call_flag", "first_seen",
    ]
    bond_panel_latest = panel[panel["as_of"] == latest_dt][[c for c in bond_latest_cols if c in panel.columns]].copy()

    # -------------------------------------------------------------------------
    # Write series parquets
    # -------------------------------------------------------------------------
    series_dir = data_root / "corp_bonds" / "series"
    series_dir.mkdir(parents=True, exist_ok=True)

    def _write_pq(df: pd.DataFrame, name: str) -> None:
        if df.empty:
            log.warning("corp_credit: %s is empty, writing empty parquet", name)
        df.to_parquet(series_dir / name, index=False)
        log.info("corp_credit: wrote %s (%d rows)", name, len(df))

    _write_pq(issuer_daily, "issuer_daily.parquet")
    _write_pq(theme_daily, "theme_daily.parquet")
    _write_pq(sector_daily, "sector_daily.parquet")
    _write_pq(market_daily, "market_daily.parquet")
    _write_pq(maturity_wall, "maturity_wall.parquet")
    _write_pq(bond_panel_latest, "bond_panel_latest.parquet")

    # -------------------------------------------------------------------------
    # Validation
    # -------------------------------------------------------------------------
    log.info("corp_credit: running validation")
    # Re-attach price_dirty_raw to panel for validation probes
    if "price_dirty_raw" not in panel.columns:
        panel["price_dirty_raw"] = 100.0 * panel["mv"] / panel["par"]

    val = run_validation(panel, market_daily, baml_oas, _root)
    resolved_convention = val.get("price_convention", "dirty")

    # If convention changed from default, re-run YTM and g-spread
    if resolved_convention != convention and not panel.empty:
        log.info("corp_credit: re-running YTM pass under resolved convention '%s'", resolved_convention)
        panel["price_dirty"], panel["price_clean"] = apply_price_convention(
            panel["price_dirty_raw"], panel["accrued_pct"], resolved_convention
        )
        if active_mask.any():
            ytm_solved2, flags2 = _ytm_solve(
                panel.loc[active_mask, "price_dirty"].values.astype(float),
                panel.loc[active_mask, "coupon"].values.astype(float),
                panel.loc[active_mask, "tenor_yrs"].values.astype(float),
            )
            ytm_arr2 = np.full(len(panel), np.nan)
            ytm_arr2[panel.index.get_indexer(panel.index[active_mask])] = ytm_solved2
            panel["ytm_pct"] = ytm_arr2 * 100.0
        cmt_pct2, g_spread_bp2 = compute_g_spread_bp(
            panel["ytm_pct"], panel["tenor_yrs"], panel["as_of"], curve_df
        )
        panel["cmt_pct"] = cmt_pct2
        panel["g_spread_bp"] = g_spread_bp2
        # A convention flip moves price/ytm/g-spread on every row: the near-par
        # flag and EVERY aggregate family must be rebuilt, or the parquets ship
        # a mix of conventions (maturity_wall is par-only but rebuilt for
        # uniformity; it is cheap).
        panel["near_par_call_flag"] = compute_near_par_flag(panel["segment"], panel["price_clean"])
        market_daily = _build_market_daily(panel, sorted_dates)
        issuer_daily = _build_issuer_daily(panel, sorted_dates)
        theme_daily = _build_theme_daily(panel, sorted_dates)
        sector_daily = _build_sector_daily(panel, sorted_dates)
        maturity_wall = _build_maturity_wall(panel)
        _write_pq(issuer_daily, "issuer_daily.parquet")
        _write_pq(theme_daily, "theme_daily.parquet")
        _write_pq(sector_daily, "sector_daily.parquet")
        _write_pq(market_daily, "market_daily.parquet")
        _write_pq(maturity_wall, "maturity_wall.parquet")
        bond_panel_latest = panel[panel["as_of"] == latest_dt][[c for c in bond_latest_cols if c in panel.columns]].copy()
        _write_pq(bond_panel_latest, "bond_panel_latest.parquet")
        # Update validation with fresh market_daily
        val = run_validation(panel, market_daily, baml_oas, _root)

    val_path = data_root / "corp_bonds" / "validation.json"
    val_path.parent.mkdir(parents=True, exist_ok=True)
    with open(val_path, "w") as f:
        json.dump(val, f, indent=2, default=str)
    log.info("corp_credit: wrote validation.json (overall=%s)", val.get("overall"))

    # -------------------------------------------------------------------------
    # Build latest.json
    # -------------------------------------------------------------------------
    elapsed = time.time() - t0
    log.info("[timing] corp_credit.snapshot: %.2fs", elapsed)

    # Market summary
    def _market_row(seg: str) -> dict:
        rows = market_daily[market_daily["segment"] == seg] if not market_daily.empty else pd.DataFrame()
        if rows.empty:
            return {}
        row = rows[rows["as_of"] == latest_dt]
        if row.empty:
            return {}
        r = row.iloc[0]
        return {
            "n_bonds": int(r.get("n_bonds", 0)),
            "par_total": float(r.get("par_total", 0)),
            "price_clean_pw": _maybe_float(r.get("price_clean_pw")),
            "ytm_pct_pw": _maybe_float(r.get("ytm_pct_pw")),
            "g_spread_bp_pw": _maybe_float(r.get("g_spread_bp_pw")),
            "wam_yrs": _maybe_float(r.get("wam_yrs")),
        }

    ig_info = _market_row("ig")
    hy_info = _market_row("hy")
    hy_gs = hy_info.get("g_spread_bp_pw")
    ig_gs = ig_info.get("g_spread_bp_pw")
    quality_spread = (hy_gs - ig_gs) if (hy_gs is not None and ig_gs is not None) else None

    # Theme summary
    themes_summary: dict[str, Any] = {}
    if not theme_daily.empty:
        theme_latest = theme_daily[theme_daily["as_of"] == latest_dt] if latest_dt else pd.DataFrame()
        for _, row in theme_latest.iterrows():
            theme_key = str(row["theme"])
            theme_data = registry.get("themes", {}).get(theme_key, {})
            coverage_notes_map = {
                iss_key: iss_data.get("coverage_notes", "")
                for iss_key, iss_data in theme_data.get("issuers", {}).items()
            }
            themes_summary[theme_key] = {
                "n_bonds": int(row.get("n_bonds", 0)),
                "n_issuers": int(row.get("n_issuers", 0)),
                "g_spread_bp_pw": _maybe_float(row.get("g_spread_bp_pw")),
                "ytm_pct_pw": _maybe_float(row.get("ytm_pct_pw")),
                "dispersion_bp": _maybe_float(row.get("dispersion_bp")),
                "dispersion_basis": row.get("dispersion_basis"),
                "small_n": int(row.get("n_bonds", 0)) < DISPERSION_FLOOR_N,
                "wam_yrs": _maybe_float(row.get("wam_yrs")),
                "coverage_notes": coverage_notes_map,
            }

    # Sector top rows
    sectors_summary: list[dict] = []
    if not sector_daily.empty:
        sec_latest = sector_daily[sector_daily["as_of"] == latest_dt] if latest_dt else pd.DataFrame()
        if not sec_latest.empty:
            sec_latest = sec_latest.sort_values("par_total", ascending=False).head(20)
            for _, row in sec_latest.iterrows():
                sectors_summary.append({
                    "sector": str(row["sector"]),
                    "n_bonds": int(row.get("n_bonds", 0)),
                    "par_total": float(row.get("par_total", 0)),
                    "g_spread_bp_pw": _maybe_float(row.get("g_spread_bp_pw")),
                })

    # Maturity wall market buckets
    mwall_summary: dict[str, dict[str, dict]] = {"ig": {}, "hy": {}}
    if not maturity_wall.empty:
        mw_latest = maturity_wall[
            (maturity_wall["as_of"] == latest_dt) &
            (maturity_wall["scope_type"] == "market") &
            (maturity_wall["scope"].isin(["ig", "hy"]))
        ]
        for _, row in mw_latest.iterrows():
            seg = str(row["scope"])
            bucket = str(row["bucket"])
            mwall_summary.setdefault(seg, {})[bucket] = {
                "par_total": float(row.get("par_total", 0)),
                "n_bonds": int(row.get("n_bonds", 0)),
            }

    honesty_notes = [
        "§2.5-2: Bond prices from SSGA fund NAV (matrix pricing, T+1 settlement implied). "
        "Not TRACE transaction prices. Spreads are indicative, not executable.",
        "§2.5-8: Holdings represent index-fund lens (only index-eligible bonds visible). "
        "Private placements and 144A-only issuance are not captured.",
    ]
    # Small-n dispersion note
    small_n_themes = [k for k, v in themes_summary.items() if v.get("small_n")]
    if small_n_themes:
        honesty_notes.append(
            f"Small-n dispersion (max-min, not p90-p10): themes with n<{DISPERSION_FLOOR_N}: "
            f"{', '.join(small_n_themes)}. Interpret with caution."
        )

    payload = {
        "organ": "corp_credit.v1",
        "as_of": str(date.today()),
        "data_as_of": latest_dt,
        "price_convention": resolved_convention,
        "authority": dict(AUTHORITY_V1),
        "accruing": _ACCRUING,
        "market": {
            "ig": ig_info,
            "hy": hy_info,
            "quality_spread_bp": quality_spread,
        },
        "themes": themes_summary,
        "sectors": sectors_summary,
        "maturity_wall": mwall_summary,
        "coverage": {
            "n_bonds_total": len(panel[panel["as_of"] == latest_dt]) if latest_dt else 0,
            "n_dropped_rows": n_dropped,
            "matched_par_share": round(matched_par_share, 4),
            "sector_mapped_par_share": round(sector_mapped_par_share, 4),
            "ytm_solver": {
                "newton_n": newton_n,
                "bisection_n": bisect_n,
                "failed_n": failed_n,
            },
            "curve_pillars_present": present_pillars,
        },
        "honesty_notes": honesty_notes,
        "validation": {
            "overall": val.get("overall"),
            "price_convention": val.get("price_convention"),
            "criteria": {k: {"status": v.get("status")} for k, v in val.get("criteria", {}).items()},
        },
        "_timing_s": round(elapsed, 2),
    }

    out_path = data_root / "corp_bonds" / "latest.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(payload, f, indent=2, default=str)
    log.info("corp_credit: wrote latest.json")

    return payload


def _maybe_float(v: Any) -> float | None:
    """Convert to float, returning None on NaN/None."""
    if v is None:
        return None
    try:
        f = float(v)
        return None if math.isnan(f) or math.isinf(f) else f
    except (TypeError, ValueError):
        return None


def _write_empty_artifacts(data_root: Path) -> None:
    """Write empty artifacts when no holdings data is available."""
    series_dir = data_root / "corp_bonds" / "series"
    series_dir.mkdir(parents=True, exist_ok=True)
    for name in [
        "issuer_daily.parquet", "theme_daily.parquet", "sector_daily.parquet",
        "market_daily.parquet", "maturity_wall.parquet", "bond_panel_latest.parquet",
    ]:
        pd.DataFrame().to_parquet(series_dir / name, index=False)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="CCW W2: Corporate Credit G-Spread Engine")
    parser.add_argument("--data-dir", default=None, help="Override data root directory")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
    )

    root = Path(args.data_dir) if args.data_dir else None
    result = snapshot(root)
    print(json.dumps(
        {k: v for k, v in result.items() if k not in ("themes",)},
        indent=2, default=str,
    ))
