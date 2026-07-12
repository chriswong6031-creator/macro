"""International Risk Desk — EM Stress Composite + Vulnerability Table (IRD-W2).

ADDITIVE / pure-leaf engine: imports nothing from the scoring core
(no conditions / stock_score / name_score / intl_feed). Reads stores only via
lib.store. Deterministic, causal (no lookahead), fail-open per leg.

Public functions
----------------
em_stress()          — FAST daily trigger composite (IRD-R2).
vulnerability_table() — SLOW annual vulnerability map (IRD-R8 / IRD-R9).

All outputs are plain dicts of JSON-serializable primitives. Neither function
raises; a missing/stale series adds a note to gaps[] and omits that leg.

IRD-R9 BAML vintage law: BAMLEMHBHYCRPIOAS began 2023-07-11 (~3y store depth).
Percentile windows on this series use max-available history; window_days is
disclosed in every leg payload so the surface can print the caveat.
"""
from __future__ import annotations

import logging
import math
from datetime import date, datetime, timezone

import numpy as np
import pandas as pd

from lib import store
from engine.ird_velocity import velocity_fields as _ird_velocity_fields

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_TWO_YEARS = 504          # ~2 trading years in business days
_SIXTY_D = 60
_TWENTY_D = 20
_FIVE_D = 5

# K-of-N thresholds (IRD-R8)
_HOT_PCTILE = 85.0        # percentile >= this is "hot"
_HOT_VEL_Z = 2.0          # |vel_20d_z| >= this in adverse direction is "hot"
_STRESSED_K = 3           # need >= 3 legs hot for "stressed"
_STRAINED_K = 2           # need >= 2 legs hot for "strained"
_MIN_LEGS = 3             # < this legs available -> "insufficient_data"

# Berg-Pattillo EWS receipt (IRD-R8 honesty bar, exact text from masterplan §4)
BERG_PATTILLO_RECEIPT = (
    "Historical early-warning-system caveat (Berg-Pattillo): best-in-class EWS "
    "models missed approximately 68% of currency/debt crises out-of-sample; "
    "approximately 60% of their 'danger' signals proved false alarms. "
    "This table is a fragility MAP — it identifies who is vulnerable, "
    "not when a crisis will occur."
)

# EM ETF subset verified present in data/intl_etf/ (inspected 2026-07-12):
# INDA (India), EIDO (Indonesia), EZA (South Africa), EWZ (Brazil),
# EWW (Mexico), EWY (South Korea), EWT (Taiwan), TUR absent -> dropped.
# All confirmed with close column and data through 2026-07.
_EM_ETF_TICKERS = ["INDA", "EIDO", "EZA", "EWZ", "EWW", "EWY", "EWT"]

# EM FX pairs: USD/EM — rising = EM FX weakening (adverse).
# yahoo store: TRY/ZAR/BRL/MXN/IDR; intl store: KRW/INR/TWD.
_EM_FX_YAHOO = ["USDTRY_X", "USDZAR_X", "USDBRL_X", "USDMXN_X", "USDIDR_X"]
_EM_FX_INTL = ["USDKRW_X", "USDINR_X", "USDTWD_X"]

# IMF WEO countries (25 from data/imf_weo — verified 2026-07-12)
_IMF_COUNTRIES = [
    "AUS", "BRA", "CAN", "CHL", "CHN", "COL", "DEU", "EGY",
    "ESP", "FRA", "GBR", "HUN", "IDN", "IND", "ITA", "JPN",
    "KOR", "MEX", "MYS", "PHL", "POL", "THA", "TUR", "USA", "ZAF",
]

# Adverse thresholds for vulnerability flags (IRD-R8)
_DEBT_THRESH = 70.0       # debt/GDP > 70 & rising
_CA_THRESH = -3.0         # current account < -3% of GDP
_FISCAL_THRESH = -5.0     # fiscal balance < -5% of GDP
_CREDIT_GAP_THRESH = 9.0  # BIS credit gap > 9pp


# ---------------------------------------------------------------------------
# Low-level helpers — all PURE, none raise
# ---------------------------------------------------------------------------

def _r(v, nd: int = 2):
    """Round to nd decimals; return None if non-finite."""
    if v is None:
        return None
    try:
        f = float(v)
        return None if not math.isfinite(f) else round(f, nd)
    except (TypeError, ValueError):
        return None


def _read_close(group: str, name: str) -> pd.Series | None:
    """Read a store and return the 'close' column (or first column) as float."""
    df = store.read(group, name)
    if df is None or df.empty:
        return None
    col = "close" if "close" in df.columns else df.columns[0]
    s = df[col].astype(float).dropna()
    return s if not s.empty else None


def _trailing_window(s: pd.Series, window: int) -> tuple[pd.Series, int]:
    """Return (trailing slice, actual_window) capped at len(s)."""
    n = min(window, len(s))
    return s.iloc[-n:], n


def _pctile_trailing(s: pd.Series, window: int) -> tuple[float | None, int]:
    """Percentile of last value in s vs trailing window. Returns (pctile, window_days)."""
    if s is None or s.empty:
        return None, 0
    w, wd = _trailing_window(s, window)
    last = float(s.iloc[-1])
    if w.empty:
        return None, 0
    pct = float((w <= last).mean() * 100.0)
    return pct, wd


def _vel_z_20d(s: pd.Series) -> float | None:
    """20d velocity z-score via shared IRD-R13 grammar (engine.ird_velocity).

    Calls velocity_fields(s, scale=1) and returns vel_20d_z — a TRUE z (mean-subtracted,
    current-obs excluded from the norm window, trailing 2y or max-available).
    This is the single authoritative velocity grammar for all IRD lobes.
    """
    return _ird_velocity_fields(s, scale=1.0)["vel_20d_z"]


def _asof(s: pd.Series) -> str:
    """ISO date of last non-null value."""
    if s is None or s.empty:
        return "n/a"
    return str(s.index[-1].date())


def _stale(s: pd.Series, max_days: int = 12) -> bool:
    """True if last observation is older than max_days calendar days."""
    if s is None or s.empty:
        return True
    last = s.index[-1]
    today = pd.Timestamp(datetime.now(timezone.utc).date())
    return (today - last).days > max_days


def _leg(
    s: pd.Series,
    pctile_window: int,
    name: str,
    adverse_direction: str = "up",  # "up" or "down" for the leg
) -> dict | None:
    """Build the IRD-R13 leg grammar dict from a series.

    vel_20d_z uses the shared IRD-R13 grammar from engine.ird_velocity
    (true z: mean-subtracted, current-obs excluded, trailing 2y window).
    vel_5d_z and level-z are not part of the shared grammar; they are None.
    """
    if s is None or s.empty:
        return None
    val = _r(float(s.iloc[-1]))
    pct, wd = _pctile_trailing(s, pctile_window)
    v20z = _vel_z_20d(s)
    return {
        "value": val,
        "z": None,       # level-z not in shared grammar; set to None
        "vel_5d_z": None,  # 5d z not in shared grammar; set to None
        "vel_20d_z": v20z,
        "pctile": _r(pct, 1),
        "asof": _asof(s),
        "stale": _stale(s),
        "window_days": wd,
        "_name": name,
        "_adverse_direction": adverse_direction,
    }


def _is_hot(leg: dict) -> bool:
    """IRD-R8: hot = pctile >= 85 OR |vel_20d_z| >= 2 in the adverse direction."""
    pct = leg.get("pctile")
    v20z = leg.get("vel_20d_z")
    if pct is not None and pct >= _HOT_PCTILE:
        return True
    if v20z is not None:
        # for "up" legs: hot if velocity is strongly positive (worsening)
        # for "down" legs: hot if velocity is strongly negative (worsening)
        adv = leg.get("_adverse_direction", "up")
        if adv == "up" and v20z >= _HOT_VEL_Z:
            return True
        if adv == "down" and v20z <= -_HOT_VEL_Z:
            return True
    return False


# ---------------------------------------------------------------------------
# Leg builders for em_stress()
# ---------------------------------------------------------------------------

def _leg_em_hy_oas(gaps: list[str]) -> dict | None:
    """Leg (a): EM HY OAS level + velocity. IRD-R9: window depth disclosed."""
    # Primary: BAMLEMHBHYCRPIOAS (EM HY; started 2023-07-11)
    s = _read_close("fred", "BAMLEMHBHYCRPIOAS")
    source = "BAMLEMHBHYCRPIOAS"
    if s is None or s.empty:
        # Fallback: broad EM IG OAS
        s = _read_close("fred", "BAMLEMCBPIOAS")
        source = "BAMLEMCBPIOAS (fallback — BAMLEMHBHYCRPIOAS absent)"
        if s is None or s.empty:
            gaps.append("em_hy_oas: both BAMLEMHBHYCRPIOAS and BAMLEMCBPIOAS absent")
            return None
    lg = _leg(s, _TWO_YEARS, "em_hy_oas", adverse_direction="up")
    if lg is None:
        gaps.append("em_hy_oas: series empty after load")
        return None
    lg["source"] = source
    lg["note"] = "IRD-R9: BAML cap ~3y from first fetch; window_days discloses depth"
    return lg


def _leg_vxeem(gaps: list[str]) -> dict | None:
    """Leg (b): VXEEM level percentile (history 2011+)."""
    s = _read_close("fred", "VXEEMCLS")
    if s is None or s.empty:
        gaps.append("vxeem: VXEEMCLS absent")
        return None
    lg = _leg(s, len(s), "vxeem", adverse_direction="up")
    if lg is None:
        gaps.append("vxeem: series empty after load")
        return None
    lg["note"] = "2011+ history; EVZ ended 2025-03 and is not used"
    return lg


def _leg_em_fx_basket(gaps: list[str]) -> dict | None:
    """Leg (c): EM FX basket — drawdown-from-60d-high + 20d realized vol pctile.

    Index = equal-weight of inverted USD/EM rate returns → rising = EM FX strengthening.
    Percentile on adverse direction: basket drawdown (negative) and vol (positive).
    """
    series_list: list[pd.Series] = []
    loaded: list[str] = []
    missing: list[str] = []

    # yahoo store
    for ticker in _EM_FX_YAHOO:
        s = _read_close("yahoo", ticker)
        if s is not None and not s.empty:
            series_list.append(s.rename(ticker))
            loaded.append(ticker)
        else:
            missing.append(ticker)

    # intl store (KRW/INR/TWD)
    for ticker in _EM_FX_INTL:
        df = store.read("intl", ticker)
        if df is not None and not df.empty:
            col = "close" if "close" in df.columns else df.columns[0]
            s = df[col].astype(float).dropna()
            if not s.empty:
                series_list.append(s.rename(ticker))
                loaded.append(ticker)
                continue
        missing.append(ticker)

    if missing:
        gaps.append(f"em_fx_basket: missing pairs {missing}")
    if not series_list:
        gaps.append("em_fx_basket: no EM FX series available")
        return None

    # Align to common index (union of all, ffill up to 3 days)
    idx = series_list[0].index
    for s in series_list[1:]:
        idx = idx.union(s.index)
    idx = idx.sort_values()

    aligned = []
    for s in series_list:
        a = s.reindex(idx).ffill(limit=3)
        aligned.append(a)

    # Equal-weight inverted-return index: invert USD/EM → positive = EM strengthens
    # log returns of 1/spot (i.e., -log(spot) returns)
    rets_list = []
    for s in aligned:
        # -log(s.pct_change()) ≈ EM appreciation return
        log_ret = -np.log(s / s.shift(1)).dropna()
        rets_list.append(log_ret)

    # Align all return series to common index
    basket_idx = rets_list[0].index
    for r in rets_list[1:]:
        basket_idx = basket_idx.union(r.index)
    basket_idx = basket_idx.sort_values()

    stacked = pd.DataFrame({f"r{i}": r.reindex(basket_idx) for i, r in enumerate(rets_list)})
    basket_ret = stacked.mean(axis=1, skipna=True).dropna()

    if basket_ret.empty or len(basket_ret) < _SIXTY_D + 5:
        gaps.append("em_fx_basket: insufficient history after alignment")
        return None

    # Cumulative index (level)
    basket_lvl = (1 + basket_ret).cumprod()

    # Drawdown from 60d rolling high (adverse = deeply negative)
    roll_high = basket_lvl.rolling(_SIXTY_D, min_periods=20).max()
    drawdown = (basket_lvl / roll_high - 1.0)  # negative when below peak
    dd_last = float(drawdown.iloc[-1])

    # 20d realized vol (annualized)
    rvol = basket_ret.rolling(_TWENTY_D, min_periods=10).std() * math.sqrt(252)
    rvol_last = float(rvol.iloc[-1]) if not rvol.dropna().empty else None

    # Percentile of vol (adverse = high)
    rvol_pct, rvol_wd = _pctile_trailing(rvol.dropna(), len(rvol.dropna()))
    # Percentile of drawdown adversity: pctile of -drawdown (adverse = deep DD)
    dd_neg = (-drawdown).dropna()
    dd_pct, dd_wd = _pctile_trailing(dd_neg, len(dd_neg))

    # Composite pctile for K-of-N: average of vol_pctile and dd_pctile
    pctiles = [p for p in [rvol_pct, dd_pct] if p is not None]
    composite_pctile = float(np.mean(pctiles)) if pctiles else None

    # Velocity z on the basket level via shared IRD-R13 grammar
    _bvf = _ird_velocity_fields(basket_lvl, scale=1.0)
    v5z = None   # 5d z not in shared grammar
    v20z = _bvf["vel_20d_z"]

    return {
        "value": _r(dd_last * 100.0, 2),  # drawdown % from 60d high
        "rvol_20d": _r(rvol_last * 100.0, 2) if rvol_last is not None else None,
        "dd_pctile": _r(dd_pct, 1),
        "rvol_pctile": _r(rvol_pct, 1),
        "pctile": _r(composite_pctile, 1),
        "vel_5d_z": v5z,
        "vel_20d_z": v20z,
        "z": None,  # not defined for composite
        "asof": _asof(basket_lvl),
        "stale": _stale(basket_lvl),
        "window_days": min(len(basket_lvl), _TWO_YEARS),
        "pairs_used": loaded,
        "pairs_missing": missing,
        "_name": "em_fx_basket",
        "_adverse_direction": "down",  # adverse = basket declining (EM FX weakening)
    }


def _leg_em_equity_breadth(gaps: list[str]) -> dict | None:
    """Leg (d): % of EM ETFs above 200dma.

    EM subset verified present in data/intl_etf/ (2026-07-12):
    INDA, EIDO, EZA, EWZ, EWW, EWY, EWT
    TUR not present in store (verified absent).
    """
    above = 0
    total = 0
    missing_tickers: list[str] = []
    latest_dates: list[str] = []

    for ticker in _EM_ETF_TICKERS:
        df = store.read("intl_etf", ticker)
        if df is None or df.empty:
            missing_tickers.append(ticker)
            continue
        col = "close" if "close" in df.columns else df.columns[0]
        c = df[col].astype(float).dropna()
        if len(c) < 200:
            missing_tickers.append(f"{ticker}(short)")
            continue
        ma200 = c.rolling(200, min_periods=200).mean()
        if ma200.dropna().empty:
            missing_tickers.append(f"{ticker}(ma_fail)")
            continue
        total += 1
        if float(c.iloc[-1]) > float(ma200.dropna().iloc[-1]):
            above += 1
        latest_dates.append(str(c.index[-1].date()))

    if missing_tickers:
        gaps.append(f"em_equity_breadth: skipped {missing_tickers}")

    if total == 0:
        gaps.append("em_equity_breadth: no EM ETFs with sufficient history")
        return None

    breadth_pct = above / total * 100.0
    # Adverse direction: low breadth (below 50%) indicates weakness
    # Invert for pctile: high adverse pctile = low breadth
    adversity = 100.0 - breadth_pct  # 0 = all above MA, 100 = all below MA

    return {
        "value": _r(breadth_pct, 1),       # % above 200dma
        "pctile": _r(adversity, 1),         # adversity percentile (higher = worse)
        "vel_5d_z": None,                   # snapshot metric, no vel
        "vel_20d_z": None,
        "z": None,
        "above": above,
        "total": total,
        "asof": max(latest_dates) if latest_dates else "n/a",
        "stale": False,
        "window_days": 200,
        "tickers": _EM_ETF_TICKERS,
        "missing": missing_tickers,
        "_name": "em_equity_breadth",
        "_adverse_direction": "down",       # adverse = breadth declining
        "note": "TUR absent from intl_etf store; basket uses 7 confirmed tickers",
    }


def _leg_em_dollar_vel(gaps: list[str]) -> dict | None:
    """Leg (e): EM-dollar-index (DTWEXEMEGS) 20d change z.

    Rising DTWEXEMEGS = dollar strengthening vs EM basket = adverse.
    """
    # Primary: DTWEXEMEGS (broad EM economies dollar index)
    s = _read_close("fred", "DTWEXEMEGS")
    source = "DTWEXEMEGS"
    if s is None or s.empty:
        # Fallback: broad dollar index
        s = _read_close("fred", "DTWEXBGS")
        source = "DTWEXBGS (fallback — DTWEXEMEGS absent)"
        if s is None or s.empty:
            gaps.append("em_dollar_vel: DTWEXEMEGS and DTWEXBGS both absent")
            return None

    if len(s) < _TWENTY_D + 30:
        gaps.append("em_dollar_vel: insufficient history")
        return None

    lg = _leg(s, min(_TWO_YEARS, len(s)), "em_dollar_vel", adverse_direction="up")
    if lg is None:
        gaps.append("em_dollar_vel: leg construction failed")
        return None
    lg["source"] = source
    return lg


def _leg_emb_ief(gaps: list[str]) -> dict | None:
    """Leg (f): EMB/IEF ratio — 20d trend z + 60d drawdown.

    Long-history spread proxy (EMB history 2007+, IEF history 1996+).
    Adverse = ratio declining (EM bonds underperforming Treasuries).
    """
    emb = _read_close("yahoo", "EMB")
    ief = _read_close("yahoo", "IEF")
    if emb is None or emb.empty:
        gaps.append("emb_ief: EMB absent from yahoo store")
        return None
    if ief is None or ief.empty:
        gaps.append("emb_ief: IEF absent from yahoo store")
        return None

    # Align to common index
    idx = emb.index.union(ief.index).sort_values()
    emb_a = emb.reindex(idx).ffill(limit=5)
    ief_a = ief.reindex(idx).ffill(limit=5)
    ratio = (emb_a / ief_a).dropna()

    if len(ratio) < _SIXTY_D + 20:
        gaps.append("emb_ief: insufficient history after alignment")
        return None

    # 60d drawdown from rolling high (adverse = deep negative)
    roll_high = ratio.rolling(_SIXTY_D, min_periods=30).max()
    dd = (ratio / roll_high - 1.0).dropna()
    dd_pct, dd_wd = _pctile_trailing(-dd, len(dd))  # adversity pctile

    lg = _leg(ratio, min(_TWO_YEARS, len(ratio)), "emb_ief_ratio", adverse_direction="down")
    if lg is None:
        gaps.append("emb_ief: leg construction failed")
        return None
    lg["dd_60d_pct"] = _r(float(dd.iloc[-1]) * 100.0, 2) if not dd.empty else None
    lg["dd_adversity_pctile"] = _r(dd_pct, 1)
    return lg


# ---------------------------------------------------------------------------
# em_stress() — public function
# ---------------------------------------------------------------------------

def em_stress() -> dict:
    """EM Stress Fast-Trigger Composite (IRD-R2).

    Returns a dict with:
      state: 'calm' | 'strained' | 'stressed' | 'insufficient_data'
      thermometer: 0–100 composite score (coincident, not leading)
      n_legs_available: int
      legs_hot: list of leg names that are "hot"
      legs: dict of per-leg payloads (IRD-R13 grammar)
      gaps: list of notes on missing/stale series
      as_of: ISO date of most recent data point across legs
      lead_lag: label for the thermometer
    """
    gaps: list[str] = []

    # Build legs
    legs_raw: dict[str, dict | None] = {
        "em_hy_oas": _leg_em_hy_oas(gaps),
        "vxeem": _leg_vxeem(gaps),
        "em_fx_basket": _leg_em_fx_basket(gaps),
        "em_equity_breadth": _leg_em_equity_breadth(gaps),
        "em_dollar_vel": _leg_em_dollar_vel(gaps),
        "emb_ief": _leg_emb_ief(gaps),
    }

    # Filter to available legs
    legs: dict[str, dict] = {k: v for k, v in legs_raw.items() if v is not None}
    n_avail = len(legs)

    # Remove internal-only keys before outputting
    legs_out: dict[str, dict] = {}
    for k, v in legs.items():
        legs_out[k] = {ik: iv for ik, iv in v.items() if not ik.startswith("_")}

    # K-of-N scoring (IRD-R8)
    hot_names: list[str] = []
    pctiles: list[float] = []
    for name, lg in legs.items():
        if _is_hot(lg):
            hot_names.append(name)
        p = lg.get("pctile")
        if p is not None:
            pctiles.append(float(p))

    # State determination
    n_hot = len(hot_names)
    if n_avail < _MIN_LEGS:
        state = "insufficient_data"
    elif n_hot >= _STRESSED_K:
        state = "stressed"
    elif n_hot >= _STRAINED_K:
        state = "strained"
    else:
        state = "calm"

    # 0-100 thermometer = mean of adverse-oriented leg pctiles
    thermometer = _r(float(np.mean(pctiles)), 1) if pctiles else None

    # Most recent as_of across legs
    asof_dates: list[str] = [lg.get("asof", "n/a") for lg in legs.values()
                              if lg.get("asof") and lg.get("asof") != "n/a"]
    as_of = max(asof_dates) if asof_dates else "n/a"

    return {
        "state": state,
        "thermometer": thermometer,
        "lead_lag": "coincident thermometer — not leading",
        "n_legs_available": n_avail,
        "n_legs_total": len(legs_raw),
        "legs_hot": hot_names,
        "legs": legs_out,
        "gaps": gaps,
        "as_of": as_of,
        "built": datetime.now(timezone.utc).isoformat(),
        "k_of_n_params": {
            "stressed_threshold": _STRESSED_K,
            "strained_threshold": _STRAINED_K,
            "min_legs_for_state": _MIN_LEGS,
            "hot_pctile_threshold": _HOT_PCTILE,
            "hot_vel_z_threshold": _HOT_VEL_Z,
        },
    }


# ---------------------------------------------------------------------------
# vulnerability_table() — public function
# ---------------------------------------------------------------------------

def _imf_series(indicator: str, iso3: str, col_map: dict[str, str]) -> pd.Series | None:
    """Load an IMF WEO parquet for (indicator, iso3). Returns a float Series indexed by year."""
    df = store.read("imf_weo", f"{indicator}_{iso3}")
    if df is None or df.empty:
        return None
    col = col_map.get(indicator) or df.columns[0]
    if col not in df.columns:
        col = df.columns[0]
    s = df[col].astype(float).dropna()
    return s if not s.empty else None


def _trend_3y(s: pd.Series | None, latest_year: int) -> str | None:
    """'rising' | 'falling' | 'stable' based on 3y slope. Requires >= 2 data points."""
    if s is None or len(s) < 2:
        return None
    # Use up to the latest observed year (no lookahead beyond published data)
    s = s[s.index <= pd.Timestamp(f"{latest_year}-12-31")]
    if len(s) < 2:
        return None
    recent = s.iloc[-min(4, len(s)):]
    # Simple OLS slope
    x = np.arange(len(recent), dtype=float)
    y = recent.values.astype(float)
    valid = np.isfinite(y)
    if valid.sum() < 2:
        return None
    slope = float(np.polyfit(x[valid], y[valid], 1)[0])
    if slope > 0.5:
        return "rising"
    if slope < -0.5:
        return "falling"
    return "stable"


def _bis_gap(iso3: str, gaps_out: list[str]) -> float | None:
    """BIS credit-to-GDP gap for a country. Currently only US/CN have data."""
    # Map ISO3 to BIS store keys (only us/cn available as of 2026-07-12)
    _map = {"USA": ("bis", "us_gap"), "CHN": ("bis", "cn_gap")}
    if iso3 not in _map:
        return None
    grp, key = _map[iso3]
    df = store.read(grp, key)
    if df is None or df.empty:
        gaps_out.append(f"bis_credit_gap_{iso3}: not in store")
        return None
    col = df.columns[0]
    s = df[col].astype(float).dropna()
    return _r(float(s.iloc[-1])) if not s.empty else None


_COL_MAP = {
    "GGXWDG_NGDP": "gross_debt_pct_gdp",
    "GGXCNL_NGDP": "fiscal_balance_pct_gdp",
    "BCA_NGDPD": "current_account_pct_gdp",
}


def _country_row(iso3: str, gaps_out: list[str]) -> dict | None:
    """Build one vulnerability row for a country. Fail-open: returns None only if
    all three IMF indicators are absent."""
    debt = _imf_series("GGXWDG_NGDP", iso3, _COL_MAP)
    fiscal = _imf_series("GGXCNL_NGDP", iso3, _COL_MAP)
    ca = _imf_series("BCA_NGDPD", iso3, _COL_MAP)

    if debt is None and fiscal is None and ca is None:
        gaps_out.append(f"{iso3}: all IMF indicators absent")
        return None

    # Latest observed year (use only past/current years; IMF WEO includes projections)
    today_year = datetime.now(timezone.utc).year
    max_hist_year = today_year - 1  # use last completed year

    def _latest(s: pd.Series | None) -> float | None:
        if s is None:
            return None
        hist = s[s.index.year <= max_hist_year]
        if hist.empty:
            # Fall back to latest available even if it's a projection
            return _r(float(s.iloc[-1]))
        return _r(float(hist.iloc[-1]))

    def _asof_year(s: pd.Series | None) -> int | None:
        if s is None:
            return None
        hist = s[s.index.year <= max_hist_year]
        if hist.empty:
            return s.index[-1].year if len(s) > 0 else None
        return int(hist.index[-1].year)

    debt_val = _latest(debt)
    debt_trend = _trend_3y(debt, max_hist_year) if debt is not None else None
    fiscal_val = _latest(fiscal)
    ca_val = _latest(ca)
    bis_gap = _bis_gap(iso3, gaps_out)
    asof_year = max(
        filter(None, [_asof_year(debt), _asof_year(fiscal), _asof_year(ca)]),
        default=None,
    )

    # Flag adverse thresholds
    flags: list[str] = []
    if debt_val is not None and debt_val > _DEBT_THRESH and debt_trend == "rising":
        flags.append(f"debt>{_DEBT_THRESH}%_rising")
    if ca_val is not None and ca_val < _CA_THRESH:
        flags.append(f"CA<{_CA_THRESH}%GDP")
    if fiscal_val is not None and fiscal_val < _FISCAL_THRESH:
        flags.append(f"fiscal<{_FISCAL_THRESH}%GDP")
    if bis_gap is not None and bis_gap > _CREDIT_GAP_THRESH:
        flags.append(f"credit_gap>{_CREDIT_GAP_THRESH}pp")

    fragile = len(flags) >= 3

    return {
        "iso3": iso3,
        "debt_gdp": debt_val,
        "debt_trend_3y": debt_trend,
        "fiscal_balance": fiscal_val,
        "current_account": ca_val,
        "bis_credit_gap": bis_gap,
        "flags": flags,
        "fragile": fragile,
        "asof_year": asof_year,
    }


def vulnerability_table() -> dict:
    """Slow Vulnerability Map (IRD-R8).

    Returns:
      countries: list of per-country rows (25 IMF countries)
      fragile: list of iso3 codes where fragile=True (>= 3 concurrent adverse flags)
      gaps: list of data-gap notes
      as_of_years: min/max asof_year across countries
      berg_pattillo_receipt: honesty caveat (exact masterplan text)
      built: ISO timestamp
    """
    gaps: list[str] = []
    rows: list[dict] = []

    for iso3 in _IMF_COUNTRIES:
        row = _country_row(iso3, gaps)
        if row is not None:
            rows.append(row)

    fragile_list = [r["iso3"] for r in rows if r["fragile"]]
    asof_years = [r["asof_year"] for r in rows if r.get("asof_year") is not None]

    return {
        "countries": rows,
        "n_countries": len(rows),
        "fragile": fragile_list,
        "n_fragile": len(fragile_list),
        "gaps": gaps,
        "thresholds": {
            "debt_gdp": _DEBT_THRESH,
            "current_account": _CA_THRESH,
            "fiscal_balance": _FISCAL_THRESH,
            "credit_gap": _CREDIT_GAP_THRESH,
        },
        "as_of_years": {
            "min": min(asof_years) if asof_years else None,
            "max": max(asof_years) if asof_years else None,
        },
        "berg_pattillo_receipt": BERG_PATTILLO_RECEIPT,
        "note": (
            "BIS credit-to-GDP gap: only US and CN currently in store; "
            "other countries accrue as the BIS adapter extends."
        ),
        "built": datetime.now(timezone.utc).isoformat(),
    }
