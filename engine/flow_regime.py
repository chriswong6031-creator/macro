"""Cross-Border Flow Regime classifier.

DISPLAY-ONLY: nothing here is ever scored, fed to a conviction/allocation, or
collapsed into BUY/SELL. Regimes are inferred from price-derived proxies only;
they are NOT measured capital flows (TIC data lag 6-7 weeks; EPFR is paid and
covers only fund flows). Every surface carrying output from this module must
include "inferred from prices" framing per CBF-R4.

Taxonomy (frozen at W0; any retune requires a masterplan edit with a dated ruling):
  risk_off_convergence    — global de-risking; havens bid
  us_exceptionalism_outflow — capital favors US; overseas headwind
  em_rotation_inflow      — money rotating overseas; dollar soft
  goldilocks_synchronized — broad global risk-on; supported
  mixed                   — no clear flow direction; watch

Anti-flicker hysteresis: published state switches only after the new raw state
holds 5 consecutive sessions. Day 1 publishes its raw state directly.

Strictly causal: every value at date t uses data up to and including t only.
No centered windows, no future leakage (no shift(-k)).

Era column: pre2010 = before 2010-01-01; post2010 = on or after 2010-01-01.

Known blind spots (CBF-R4): FX-hedged flows leave no FX trace; SWF/OTC flows
invisible; managed pegs truncate FX signals (CNH stays illustrative-tier).
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: ETF basket for the RoW composite (frozen, IRD-R4 adjudicated membership).
ROW_BASKET = ["EWJ", "EWG", "EWU", "EWC", "EWA", "EWL",   # DM
              "EWZ", "EWW", "INDA", "EIDO", "EZA", "EWY"]   # EM

#: EM FX pairs: (store_group, ticker, negate)
#: negate=True  => series is USD/LOCAL (USD per local currency unit is WRONG direction;
#:                  UP = local DEPRECIATION), so we negate to get appreciation = positive.
#: negate=False => series is LOCAL/USD (local per USD), so UP = local DEPRECIATION =>
#:                  negate is True for these too; see below.
#: ALL stored tickers here are USD/LOCAL (USDXXX=X convention — up means USD stronger,
#: i.e. local weaker). negate=True for all of them.
EM_FX_PAIRS: list[tuple[str, str, bool]] = [
    ("yahoo",  "USDMXN_X", True),
    ("yahoo",  "USDBRL_X", True),
    ("yahoo",  "USDZAR_X", True),
    ("yahoo",  "USDTRY_X", True),
    ("yahoo",  "USDIDR_X", True),
    ("yahoo",  "USDCLP_X", True),
    ("yahoo",  "USDPLN_X", True),
    ("intl",   "USDKRW_X", True),
    ("intl",   "USDINR_X", True),
    ("intl",   "USDTWD_X", True),
]

#: Broad dollar splice: DTWEXBGS from 2006-01-01 onward; DXY (DX-Y.NYB) before.
DTWEXBGS_START = pd.Timestamp("2006-01-01")

#: Hysteresis: new raw state must hold this many consecutive sessions before
#: the published state switches.
HYSTERESIS_SESSIONS = 5

#: Era boundary
ERA_CUTOFF = pd.Timestamp("2010-01-01")

#: Regime labels
RISK_OFF       = "risk_off_convergence"
EXCEPTION      = "us_exceptionalism_outflow"
ROTATION       = "em_rotation_inflow"
GOLDILOCKS     = "goldilocks_synchronized"
MIXED          = "mixed"

REGIME_ORDER = [RISK_OFF, EXCEPTION, ROTATION, GOLDILOCKS, MIXED]


# ---------------------------------------------------------------------------
# Internal data loaders (lazy import of store to keep module importable in tests)
# ---------------------------------------------------------------------------

def _read_store(group: str, name: str, col: str = "close") -> Optional[pd.Series]:
    """Read a series from lib.store; return None if unavailable."""
    try:
        from lib import store as _store
        df = _store.read(group, name)
    except Exception:
        return None
    if df is None or df.empty:
        return None
    df = df.copy()
    df.index = pd.to_datetime(df.index)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    if col in df.columns:
        s = pd.to_numeric(df[col], errors="coerce")
    else:
        s = pd.to_numeric(df.iloc[:, 0], errors="coerce")
    s.name = name
    return s.dropna()


# ---------------------------------------------------------------------------
# Input builders (pure, accept pre-loaded Series for testability)
# ---------------------------------------------------------------------------

def build_row_composite(
    etf_closes: dict[str, pd.Series],
    spy_index: pd.DatetimeIndex,
) -> pd.Series:
    """Equal-weight USD price-return composite of available RoW basket members.

    Coverage-weighted: equal-weight over AVAILABLE members on each date.
    Members are counted per date to allow disclosure of basket size over time.

    Parameters
    ----------
    etf_closes : dict ticker -> daily close Series
    spy_index  : SPY trading-calendar index (alignment target)

    Returns
    -------
    pd.Series  daily simple return of the equal-weight composite, aligned to spy_index.
    """
    rets: list[pd.Series] = []
    for ticker, s in etf_closes.items():
        r = s.reindex(spy_index).ffill(limit=3).pct_change()
        rets.append(r.rename(ticker))
    if not rets:
        return pd.Series(dtype=float, index=spy_index, name="row_composite")
    combined = pd.concat(rets, axis=1)
    # Equal-weight mean across available (non-NaN) members each day
    row_ret = combined.mean(axis=1, skipna=True)
    row_ret.name = "row_composite"
    return row_ret


def build_broad_dollar(
    dtwexbgs: Optional[pd.Series],
    dxy: Optional[pd.Series],
    spy_index: pd.DatetimeIndex,
) -> pd.Series:
    """Splice broad dollar index: DTWEXBGS from 2006-01-01; DXY before.

    IMPORTANT: windows that span the splice date use ONLY the single series
    that is dominant in that window.  The rolling pct_change is computed on
    the spliced level series (same series within each window).  Because we
    compute rolling windows of 20 and 63 days, a window starting before
    2006-01-01 and ending on or after 2006-01-01 would span the splice.
    To avoid mixing series within a window, we keep the splice as a clean
    level join and mark the first 63 days after the splice start as using
    DXY for the pre-splice portion (no mixed-series window is returned for
    the 63d leg until 2006-03-06).

    Returns a spliced level series aligned to spy_index (for pct_change).
    """
    # Build DTWEXBGS segment (2006-01-01 onward)
    if dtwexbgs is not None and not dtwexbgs.empty:
        seg_new = dtwexbgs.copy()
        seg_new.index = pd.to_datetime(seg_new.index)
        seg_new = seg_new[seg_new.index >= DTWEXBGS_START]
    else:
        seg_new = pd.Series(dtype=float)

    # Build DXY segment (pre-2006)
    if dxy is not None and not dxy.empty:
        dxy_idx = pd.to_datetime(dxy.index)
        seg_dxy = dxy.copy()
        seg_dxy.index = dxy_idx
        seg_old = seg_dxy[seg_dxy.index < DTWEXBGS_START]
    else:
        seg_old = pd.Series(dtype=float)

    if seg_new.empty and seg_old.empty:
        return pd.Series(dtype=float, index=spy_index, name="broad_dollar_level")

    # Combine: DXY before splice; DTWEXBGS from splice onward.
    spliced = pd.concat([seg_old, seg_new]).sort_index()
    spliced = spliced[~spliced.index.duplicated(keep="last")]
    spliced = spliced.reindex(spy_index).ffill(limit=3)
    spliced.name = "broad_dollar_level"
    return spliced


def build_emfx_basket(
    fx_series: dict[str, pd.Series],  # ticker -> USDXXX price level (negate flag applied externally)
    spy_index: pd.DatetimeIndex,
    negate: bool = False,
    winsor_threshold: float = 0.15,
) -> pd.Series:
    """Equal-weight EM FX basket (local-currency appreciation = positive).

    Input series are price levels. Returns are computed as pct_change on
    the ORIGINAL (positive) price level, then optionally negated.

    For USDXXX tickers (USD per local unit): rising = local DEPRECIATES.
    Pass negate=True to invert so that rising USDXXX = negative appreciation.

    The caller (load_inputs_from_store) passes negate=True for all EM FX pairs
    because all stored tickers are USDXXX convention.

    Alternatively, callers may pre-negate by passing already-flipped return series
    (with negate=False) — used in tests.

    winsor_threshold : daily |return| above this value is clipped to ±threshold
    before basketing, to prevent data glitches (e.g. USDCLP 5.0→663.75 on
    2016-12-23, USDTWD 1.801 on 2011-10-26) from corrupting 63-session rolling
    windows and causing log1p NaN.

    Returns equal-weight mean of daily simple returns (appreciation-positive).
    """
    rets: list[pd.Series] = []
    for name, s in fx_series.items():
        raw_ret = s.reindex(spy_index).ffill(limit=3).pct_change()
        # Winsorize: clip extreme daily moves that are almost certainly data glitches
        raw_ret = raw_ret.clip(lower=-winsor_threshold, upper=winsor_threshold)
        if negate:
            raw_ret = -raw_ret
        rets.append(raw_ret.rename(name))
    if not rets:
        return pd.Series(dtype=float, index=spy_index, name="emfx_basket")
    combined = pd.concat(rets, axis=1)
    basket = combined.mean(axis=1, skipna=True)
    basket.name = "emfx_basket"
    return basket


# ---------------------------------------------------------------------------
# Rolling leg computers
# ---------------------------------------------------------------------------

def _rolling_return(price_or_return: pd.Series, window: int) -> pd.Series:
    """Rolling window simple return (causal).

    Computes as: (price[t] / price[t-window]) - 1 using pct_change(window).
    This is causal: only data up to and including t is used.
    """
    # pct_change(N) = (s[t] - s[t-N]) / s[t-N]  — fully causal by pandas default
    return price_or_return.pct_change(window)


def compute_legs(
    spy_close: pd.Series,
    row_close: pd.Series,
    broad_dollar_level: pd.Series,
    emfx_basket_return: pd.Series,
    vix_close: pd.Series,
    spy_index: pd.DatetimeIndex,
) -> pd.DataFrame:
    """Compute all rolling leg values used by the classifier.

    All computations are strictly causal.

    Parameters
    ----------
    spy_close          : SPY close price
    row_close          : RoW composite level (or return — treated as return if <1)
    broad_dollar_level : spliced broad dollar level series
    emfx_basket_return : pre-computed EM FX basket return series (aligned)
    vix_close          : VIX close
    spy_index          : the alignment index

    Returns
    -------
    DataFrame with columns:
        spy_20d, row_20d, spy_63d, row_63d,
        usd_20d, usd_63d, emfx_63d, vix
    """
    # SPY returns
    spy_r = spy_close.reindex(spy_index).ffill(limit=3)
    spy_20d = _rolling_return(spy_r, 20)
    spy_63d = _rolling_return(spy_r, 63)

    # RoW composite returns
    # row_close is a reconstructed price LEVEL (built from cumulative return in classify_history).
    # We compute 20d/63d as pct_change on the level series (strictly causal).
    row_r = row_close.reindex(spy_index).ffill(limit=3)
    row_20d = _rolling_return(row_r, 20)
    row_63d = _rolling_return(row_r, 63)

    # Broad dollar returns
    usd_r = broad_dollar_level.reindex(spy_index).ffill(limit=3)
    usd_20d = _rolling_return(usd_r, 20)
    usd_63d = _rolling_return(usd_r, 63)
    # Splice masking: null out any rolling-window return that straddles the DXY/DTWEXBGS splice
    # date (2006-01-01). A pct_change(N) at date t uses the price at t and the price N sessions
    # ago. If the lookback point is pre-splice and t is post-splice, the return mixes two
    # different series levels (DXY ~91 vs DTWEXBGS ~101) producing a phantom +12% return.
    # We mask all t where any session in [t-N, t] crosses the splice boundary.
    _splice_ts = DTWEXBGS_START
    _idx_arr = pd.DatetimeIndex(spy_index)
    # For each window size, find dates where the window START is pre-splice but t is post-splice.
    # Window start for pct_change(N) at position i is spy_index[i-N].
    # Mask: splice_start <= _idx_arr[i] AND (i < N OR _idx_arr[i-N] < splice_start)
    _post_splice = _idx_arr >= _splice_ts
    for _window, _leg in ((20, "usd_20d"), (63, "usd_63d")):
        _leg_vals = usd_20d if _window == 20 else usd_63d
        _mask = np.zeros(len(_idx_arr), dtype=bool)
        for _i in range(len(_idx_arr)):
            if not _post_splice[_i]:
                continue  # purely pre-splice window: ok (all DXY)
            _lookback_i = _i - _window
            if _lookback_i < 0 or _idx_arr[_lookback_i] < _splice_ts:
                _mask[_i] = True  # window start is pre-splice: straddles the seam
        if _window == 20:
            usd_20d = usd_20d.copy()
            usd_20d.iloc[_mask] = np.nan
        else:
            usd_63d = usd_63d.copy()
            usd_63d.iloc[_mask] = np.nan

    # EM FX basket: already a daily return series — compute rolling cumulative
    emfx_aligned = emfx_basket_return.reindex(spy_index).ffill(limit=3)
    # For 63d window: rolling cumulative return = product of (1+r) over 63 days
    # Use log approximation: sum of log(1+r) ≈ cumulative log return
    # Convert to simple: exp(sum) - 1
    log_emfx = np.log1p(emfx_aligned.fillna(0.0))
    emfx_63d = np.expm1(log_emfx.rolling(63, min_periods=50).sum())
    emfx_63d = emfx_63d.where(emfx_aligned.rolling(63).count() >= 50)

    # VIX: use level directly (not a return)
    vix_r = vix_close.reindex(spy_index).ffill(limit=3)

    out = pd.DataFrame({
        "spy_20d": spy_20d,
        "row_20d": row_20d,
        "spy_63d": spy_63d,
        "row_63d": row_63d,
        "usd_20d": usd_20d,
        "usd_63d": usd_63d,
        "emfx_63d": emfx_63d,
        "vix": vix_r,
    }, index=spy_index)

    return out


# ---------------------------------------------------------------------------
# Regime classification rules
# ---------------------------------------------------------------------------

def _classify_raw(legs: pd.DataFrame) -> pd.Series:
    """Apply classification rules (first match wins) to leg DataFrame.

    Rules (frozen at W0; §2 of masterplan):
    1. risk_off_convergence:     spy_20d <= -0.03 AND row_20d <= -0.03
                                 AND (usd_20d >= 0.015 OR vix >= 25)
    2. us_exceptionalism_outflow:(spy_63d - row_63d) >= 0.03
                                 AND usd_63d > 0 AND emfx_63d <= 0
    3. em_rotation_inflow:       (row_63d - spy_63d) >= 0.03
                                 AND usd_63d < 0 AND emfx_63d > 0
    4. goldilocks_synchronized:  spy_63d >= 0.02 AND row_63d >= 0.02
                                 AND |spy_63d - row_63d| < 0.03
                                 AND usd_63d <= 0.01 AND vix < 20
    5. else: mixed
    """
    raw = pd.Series(MIXED, index=legs.index, dtype="object", name="raw_state")

    # Precompute columns
    spy_20d   = legs["spy_20d"]
    row_20d   = legs["row_20d"]
    spy_63d   = legs["spy_63d"]
    row_63d   = legs["row_63d"]
    usd_20d   = legs["usd_20d"]
    usd_63d   = legs["usd_63d"]
    emfx_63d  = legs["emfx_63d"]
    vix       = legs["vix"]

    # Rule 4 (lowest priority among named rules; set first, overwritten by higher-priority rules)
    r4 = (
        (spy_63d >= 0.02) &
        (row_63d >= 0.02) &
        ((spy_63d - row_63d).abs() < 0.03) &
        (usd_63d <= 0.01) &
        (vix < 20)
    )
    raw[r4] = GOLDILOCKS

    # Rule 3
    r3 = (
        (row_63d - spy_63d >= 0.03) &
        (usd_63d < 0) &
        (emfx_63d > 0)
    )
    raw[r3] = ROTATION

    # Rule 2
    r2 = (
        (spy_63d - row_63d >= 0.03) &
        (usd_63d > 0) &
        (emfx_63d <= 0)
    )
    raw[r2] = EXCEPTION

    # Rule 1 (highest priority — overwrites all above)
    r1 = (
        (spy_20d <= -0.03) &
        (row_20d <= -0.03) &
        ((usd_20d >= 0.015) | (vix >= 25))
    )
    raw[r1] = RISK_OFF

    # Days with ANY NaN in required legs remain NaN-aware
    required = legs[["spy_20d", "row_20d", "spy_63d", "row_63d",
                      "usd_20d", "usd_63d", "emfx_63d", "vix"]]
    all_nan = required.isna().all(axis=1)
    raw[all_nan] = MIXED  # fail-open to mixed on all-NaN rows

    return raw


def _apply_hysteresis(raw: pd.Series, n: int = HYSTERESIS_SESSIONS) -> pd.Series:
    """Apply anti-flicker hysteresis.

    Published state switches only after the new raw state holds n consecutive
    sessions. Day 1 publishes its raw state directly.

    This is causal: published[t] depends only on raw[1..t].
    """
    published = pd.Series(index=raw.index, dtype="object", name="state")
    if len(raw) == 0:
        return published

    values = raw.values
    pub_values = [""] * len(values)

    current_pub = values[0]
    pub_values[0] = current_pub
    candidate = values[0]
    candidate_run = 1

    for i in range(1, len(values)):
        r = values[i]
        if r == current_pub:
            # Same as published; reset candidate streak
            candidate = current_pub
            candidate_run = 1
            pub_values[i] = current_pub
        elif r == candidate:
            # Continuing a different candidate's streak
            candidate_run += 1
            if candidate_run >= n:
                # Switch
                current_pub = candidate
            pub_values[i] = current_pub
        else:
            # New candidate starts
            candidate = r
            candidate_run = 1
            pub_values[i] = current_pub

    published[:] = pub_values
    return published


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def classify_history(
    spy_close: pd.Series,
    row_composite_level: pd.Series,
    broad_dollar_level: pd.Series,
    emfx_basket_daily_ret: pd.Series,
    vix_close: pd.Series,
) -> pd.DataFrame:
    """Classify full history under the CBF regime taxonomy.

    Parameters
    ----------
    spy_close              : SPY close price Series
    row_composite_level    : RoW composite level (cumulative price, not return)
    broad_dollar_level     : spliced broad dollar level Series
    emfx_basket_daily_ret  : EM FX basket daily return (appreciation = positive)
    vix_close              : VIX close level

    Returns
    -------
    pd.DataFrame with columns:
        raw_state, state, era, spy_20d, row_20d, spy_63d, row_63d,
        usd_20d, usd_63d, emfx_63d, vix
    """
    spy_index = spy_close.dropna().index

    legs = compute_legs(
        spy_close=spy_close,
        row_close=row_composite_level,
        broad_dollar_level=broad_dollar_level,
        emfx_basket_return=emfx_basket_daily_ret,
        vix_close=vix_close,
        spy_index=spy_index,
    )

    raw = _classify_raw(legs)
    state = _apply_hysteresis(raw)

    era = pd.Series(
        ["pre2010" if d < ERA_CUTOFF else "post2010" for d in spy_index],
        index=spy_index,
        name="era",
    )

    result = pd.DataFrame({
        "raw_state": raw,
        "state": state,
        "era": era,
    }, index=spy_index)

    result = pd.concat([result, legs], axis=1)
    return result


# ---------------------------------------------------------------------------
# Convenience loader for the study script (loads from real stores)
# ---------------------------------------------------------------------------

def load_inputs_from_store() -> dict:
    """Load all classifier inputs from the live data stores.

    Returns a dict with keys:
        spy_close, row_etf_closes (dict), dtwexbgs, dxy, fx_series (dict), vix_close,
        basket_membership_count (dict of date -> int for coverage disclosure)
    """
    from lib import store as _store  # noqa: F401 — guarded import

    # SPY
    spy_df = _store.read("yahoo", "SPY")
    spy_close = pd.to_numeric(
        pd.DataFrame(spy_df).rename(columns=str.lower)["close"], errors="coerce"
    )
    spy_close.index = pd.to_datetime(spy_close.index)
    spy_close = spy_close.sort_index().dropna()

    # RoW ETFs
    row_etf_closes: dict[str, pd.Series] = {}
    for ticker in ROW_BASKET:
        df = _store.read("intl_etf", ticker)
        if df is None or df.empty:
            log.warning("flow_regime: missing intl_etf/%s", ticker)
            continue
        df.index = pd.to_datetime(df.index)
        col = "close" if "close" in df.columns else df.columns[0]
        s = pd.to_numeric(df[col], errors="coerce").sort_index().dropna()
        row_etf_closes[ticker] = s

    # Broad dollar
    dtwexbgs_df = _store.read("fred", "DTWEXBGS")
    dtwexbgs: Optional[pd.Series] = None
    if dtwexbgs_df is not None and not dtwexbgs_df.empty:
        dtwexbgs_df.index = pd.to_datetime(dtwexbgs_df.index)
        # Column may be named 'broad_dollar' or the first column
        col = "broad_dollar" if "broad_dollar" in dtwexbgs_df.columns else dtwexbgs_df.columns[0]
        dtwexbgs = pd.to_numeric(dtwexbgs_df[col], errors="coerce").sort_index().dropna()
        dtwexbgs.name = "DTWEXBGS"

    dxy_df = _store.read("yahoo", "DX-Y.NYB")
    dxy: Optional[pd.Series] = None
    if dxy_df is not None and not dxy_df.empty:
        dxy_df.index = pd.to_datetime(dxy_df.index)
        cols = dxy_df.rename(columns=str.lower)
        col = "close" if "close" in cols.columns else cols.columns[0]
        dxy = pd.to_numeric(cols[col], errors="coerce").sort_index().dropna()
        dxy.name = "DXY"

    # EM FX pairs: all are USDXXX=X convention (USD per local unit).
    # We store the RAW price levels here; build_emfx_basket applies negate=True.
    fx_series: dict[str, pd.Series] = {}
    for store_group, ticker, _negate_flag in EM_FX_PAIRS:
        df = _store.read(store_group, ticker)
        if df is None or df.empty:
            log.warning("flow_regime: missing %s/%s", store_group, ticker)
            continue
        df.index = pd.to_datetime(df.index)
        col = "close" if "close" in df.columns else df.columns[0]
        s = pd.to_numeric(df[col], errors="coerce").sort_index().dropna()
        # Do NOT negate here; negate_flag is honored by build_emfx_basket(negate=True)
        ccy = ticker.replace("USD", "").replace("_X", "").replace("=X", "")
        fx_series[ccy] = s

    # VIX
    vix_df = _store.read("yahoo", "_VIX")
    vix_close: Optional[pd.Series] = None
    if vix_df is not None and not vix_df.empty:
        vix_df.index = pd.to_datetime(vix_df.index)
        cols = vix_df.rename(columns=str.lower)
        col = "close" if "close" in cols.columns else cols.columns[0]
        vix_close = pd.to_numeric(cols[col], errors="coerce").sort_index().dropna()
        vix_close.name = "VIX"

    return {
        "spy_close": spy_close,
        "row_etf_closes": row_etf_closes,
        "dtwexbgs": dtwexbgs,
        "dxy": dxy,
        "fx_series": fx_series,
        "vix_close": vix_close,
    }
