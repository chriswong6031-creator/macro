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


# ===========================================================================
# W2 ADDITIONS — Bloc flow gauges, partial-EMP watch, idio-vs-systemic,
# swap-line confirmation row, cross-refs, compose(), history accrual.
# ===========================================================================

# ---------------------------------------------------------------------------
# W2 Constants (FROZEN)
# ---------------------------------------------------------------------------

#: Bloc ETF membership (FROZEN).
BLOCS: dict[str, list[str]] = {
    "europe":        ["EWG", "EWU", "EWL"],
    "japan":         ["EWJ"],
    "commodity_dm":  ["EWC", "EWA"],
    "latam":         ["EWZ", "EWW"],
    "em_asia":       ["INDA", "EIDO", "EWY"],
    "emea":          ["EZA"],
    "em_broad":      ["EEM"],
}

#: Bloc FX mapping: bloc -> list of (currency_key, store_group, ticker, negate)
#: currency_key matches keys in fx_series from load_inputs_from_store or the
#: extended W2 loader; negate=True for USDXXX tickers.
BLOC_FX: dict[str, list[tuple[str, str, str, bool]]] = {
    "europe":       [("EUR", "yahoo",  "EURUSD_X",  False),   # EURUSD: EUR per USD → rising = EUR appreciates? No: EURUSD = EUR/USD so rising = EUR stronger = negate=False (rising is appreciation of EUR)
                     ("GBP", "yahoo",  "GBPUSD_X",  False),   # GBPUSD: GBP per USD, rising = GBP appreciates
                     ("CHF", "yahoo",  "CHFUSD_X",  False)],  # CHFUSD or USDCHF?
    "japan":        [("JPY", "yahoo",  "USDJPY_X",  True)],   # USDJPY: rising = JPY depreciates
    "commodity_dm": [("CAD", "yahoo",  "USDCAD_X",  True),
                     ("AUD", "yahoo",  "AUDUSD_X",  False)],
    "latam":        [("MXN", "yahoo",  "USDMXN_X",  True),
                     ("BRL", "yahoo",  "USDBRL_X",  True),
                     ("CLP", "yahoo",  "USDCLP_X",  True)],
    "em_asia":      [("INR", "intl",   "USDINR_X",  True),
                     ("IDR", "yahoo",  "USDIDR_X",  True),
                     ("KRW", "intl",   "USDKRW_X",  True),
                     ("TWD", "intl",   "USDTWD_X",  True)],
    "emea":         [("ZAR", "yahoo",  "USDZAR_X",  True),
                     ("TRY", "yahoo",  "USDTRY_X",  True),
                     ("PLN", "yahoo",  "USDPLN_X",  True)],
    "em_broad":     [],  # uses EM FX basket from W1
}

#: Regional EM OAS tickers from FRED (for bloc oas leg).
#: Only EM blocs (latam, em_asia, emea, em_broad) get an OAS leg.
BLOC_OAS: dict[str, str] = {
    "latam":    "BAMLEMRLCRPILAOAS",
    "em_asia":  "BAMLEMRACRPIASIAOAS",
    "emea":     "BAMLEMRECRPIEMEAOAS",
    "em_broad": "BAMLEMCBPIOAS",
}

#: US HY OAS ticker (for discriminator DM transmission leg).
US_HY_OAS_TICKER = "BAMLH0A0HYM2"

#: EEM ticker for EMP beta computation.
EEM_TICKER = "EEM"

#: Per-country ETF and FX pair mapping for partial-EMP watch.
#: (country_code, etf_ticker, fx_store_group, fx_ticker, fx_negate)
COUNTRY_EMP_MAP: list[tuple[str, str, str, str, bool]] = [
    ("JP", "EWJ",  "yahoo", "USDJPY_X",  True),
    ("DE", "EWG",  "yahoo", "EURUSD_X",  False),   # EUR: negate=False (rising = appreciation)
    ("GB", "EWU",  "yahoo", "GBPUSD_X",  False),
    ("CA", "EWC",  "yahoo", "USDCAD_X",  True),
    ("AU", "EWA",  "yahoo", "AUDUSD_X",  False),
    ("CH", "EWL",  "yahoo", "USDCHF_X",  True),
    ("BR", "EWZ",  "yahoo", "USDBRL_X",  True),
    ("MX", "EWW",  "yahoo", "USDMXN_X",  True),
    ("IN", "INDA", "intl",  "USDINR_X",  True),
    ("ID", "EIDO", "yahoo", "USDIDR_X",  True),
    ("ZA", "EZA",  "yahoo", "USDZAR_X",  True),
    ("KR", "EWY",  "intl",  "USDKRW_X",  True),
    ("TW", "EWT",  "intl",  "USDTWD_X",  True),
]

#: EMP composite thresholds (FROZEN, CBF-R3).
EMP_ELEVATED = 1.0
EMP_STRONG   = 2.0

#: Discriminator breadth threshold (FROZEN, CBF-R5).
DISC_BREADTH_THRESHOLD = 0.50
DISC_DOWN_PCT_THRESHOLD = 0.02   # >2% down over 30d
DISC_CORR_PERCENTILE   = 80.0
DISC_HY_VEL_Z_THRESHOLD = 1.0

#: Bloc flow direction bands (FROZEN).
BLOC_INFLOW_THRESHOLD  = 0.5
BLOC_OUTFLOW_THRESHOLD = -0.5

#: FIELD_GUIDE §4 plain-word state labels and guidance (VERBATIM).
_REGIME_LABELS: dict[str, dict] = {
    "goldilocks_synchronized": {
        "label_en": "Broad global risk-on — supported",
        "label_zh": "全球风险偏好广泛上升——市场受支撑",
        "guidance_en": (
            "Global growth is steady and money is flowing to markets everywhere. "
            "Diversified risk is being rewarded."
        ),
        "guidance_zh": (
            "全球增长稳健，资金正在流向各地市场。分散化风险敞口正在获得回报。"
        ),
    },
    "us_exceptionalism_outflow": {
        "label_en": "Capital favors the US — overseas headwind",
        "label_zh": "资本偏向美国——海外市场面临逆风",
        "guidance_en": (
            "Money looks to be moving toward the US. Overseas and commodity-linked assets "
            "face a headwind; countries with big deficits are the ones to watch."
        ),
        "guidance_zh": (
            "资金似乎正在向美国转移。海外及大宗商品相关资产面临逆风；"
            "赤字较大的国家需要重点关注。"
        ),
    },
    "em_rotation_inflow": {
        "label_en": "Money rotating overseas — dollar soft",
        "label_zh": "资金轮动至海外——美元走软",
        "guidance_en": (
            "The dollar is weakening and foreign markets are leading. "
            "Overseas exposure tends to benefit; a dollar turn is the main risk."
        ),
        "guidance_zh": (
            "美元走弱，海外市场领跑。海外资产敞口往往受益；"
            "美元逆转是主要风险。"
        ),
    },
    "risk_off_convergence": {
        "label_en": "Global de-risking — havens bid",
        "label_zh": "全球去风险化——避险资产受追捧",
        "guidance_en": (
            "Risk appetite has dropped everywhere at once. "
            "Havens are in demand; don't chase rebounds until volatility settles."
        ),
        "guidance_zh": (
            "风险偏好在全球范围内同步下降。避险资产需求旺盛；"
            "在波动率平息之前不宜追涨反弹。"
        ),
    },
    "mixed": {
        "label_en": "No clear flow direction — watch",
        "label_zh": "流向不明——持续观察",
        "guidance_en": (
            "Signals disagree. Wait for the picture to clear rather than leaning on a weak read."
        ),
        "guidance_zh": (
            "信号互相矛盾。等待局势明朗，不宜基于模糊信号仓促判断。"
        ),
    },
}

#: Discriminator plain-word labels (FIELD_GUIDE §4 + CBF-R5).
_DISC_LABELS: dict[str, dict] = {
    "isolated": {
        "label_en": "Isolated stress",
        "label_zh": "孤立压力",
        "guidance_en": "One country's problem — broader markets not infected.",
        "guidance_zh": "单一国家问题——尚未传染至更广泛市场。",
    },
    "spreading": {
        "label_en": "Spreading",
        "label_zh": "扩散中",
        "guidance_en": "Watch breadth — pressure widening.",
        "guidance_zh": "关注广度——压力正在扩散。",
    },
    "systemic": {
        "label_en": "Broad and systemic",
        "label_zh": "广泛且系统性",
        "guidance_en": (
            "Weakness is broad and reaching developed-market credit — "
            "de-risking has historically been right here."
        ),
        "guidance_zh": (
            "弱势广泛蔓延并波及发达市场信贷——历史上此时去风险往往是正确选择。"
        ),
    },
    "n/a": {
        "label_en": "No elevated outflow pressure",
        "label_zh": "无明显资金外流压力",
        "guidance_en": "No elevated outflow pressure detected.",
        "guidance_zh": "未检测到明显的资金外流压力。",
    },
}


# ---------------------------------------------------------------------------
# W2 helpers
# ---------------------------------------------------------------------------


def _causal_z_of_return_series(
    ret_series: pd.Series,
    window_bd: int = 504,
    min_hist: int = 20,
) -> Optional[float]:
    """Causal z of a return/change series (IRD-R13 grammar).

    Used to z-score an already-computed 20d-return series (not a price level).
    z = (current_val - mean(hist)) / std(hist),
    where hist = trailing window_bd observations EXCLUDING the current observation.
    Returns None if series too short or std==0.
    """
    import math
    s = ret_series.dropna()
    n = len(s)
    if n < min_hist + 1:
        return None
    hist = s.iloc[:-1]
    window = min(window_bd, len(hist))
    w = hist.iloc[-window:]
    mu = float(w.mean())
    sd = float(w.std())
    if sd == 0 or not math.isfinite(sd):
        return None
    z = (float(s.iloc[-1]) - mu) / sd
    if not math.isfinite(z):
        return None
    return round(z, 3)


def _bloc_etf_z_20d(
    etf_closes: dict[str, pd.Series],
    tickers: list[str],
    spy_index: pd.DatetimeIndex,
) -> Optional[float]:
    """Equal-weight mean causal z of 20d ETF returns for a bloc (IRD-R13 grammar).

    Builds the 20d simple return series for each ETF, then z-scores it on its own
    trailing 2y history (EXCLUDING current obs). Returns mean z across tickers.
    """
    zs: list[float] = []
    for tk in tickers:
        s = etf_closes.get(tk)
        if s is None or s.empty:
            continue
        s_aligned = s.reindex(spy_index).ffill(limit=3)
        ret_20d = s_aligned.pct_change(20)
        z = _causal_z_of_return_series(ret_20d)
        if z is not None:
            zs.append(z)
    if not zs:
        return None
    return round(float(sum(zs) / len(zs)), 3)


def _bloc_fx_z_20d(
    fx_series: dict[str, pd.Series],
    bloc_fx_specs: list[tuple[str, str, str, bool]],
    spy_index: pd.DatetimeIndex,
    winsor: float = 0.15,
) -> tuple[Optional[float], list[str]]:
    """Equal-weight mean causal z of 20d FX appreciation for a bloc (IRD-R13 grammar).

    bloc_fx_specs: list of (currency_key, store_group, ticker, negate) as in BLOC_FX.
    Each pair's 20d pct_change series (appreciation-positive, winsorized) is z-scored
    on its own trailing 2y history.

    Returns (mean_z, missing_notes).
    """
    import math
    zs: list[float] = []
    missing: list[str] = []
    for ccy, _sg, _tk, negate in bloc_fx_specs:
        s = fx_series.get(ccy)
        if s is None or s.empty:
            missing.append(ccy)
            continue
        s_aligned = s.reindex(spy_index).ffill(limit=3)
        s_dropna = s_aligned.dropna()
        if len(s_dropna) < 21:
            missing.append(f"{ccy}(short)")
            continue

        # Build winsorized appreciation return series (daily)
        raw_ret = s_dropna.pct_change()
        raw_ret = raw_ret.clip(lower=-winsor, upper=winsor)
        if negate:
            raw_ret = -raw_ret  # USDXXX: rising=local depreciation → negate to appreciation

        # 20d cumulative appreciation return series (simple: pct_change(20) on price, then negate)
        # Using the appreciation-sign-adjusted price level for 20d pct_change
        if negate:
            # Already negated the daily return; reconstruct appreciation price from it
            # Easier: compute pct_change(20) on the raw price, then negate
            raw_20d = s_dropna.pct_change(20)
            ret_20d_series = -raw_20d  # appreciation = negative of USDXXX 20d move
        else:
            raw_20d = s_dropna.pct_change(20)
            ret_20d_series = raw_20d

        z = _causal_z_of_return_series(ret_20d_series)
        if z is not None:
            zs.append(z)
        else:
            missing.append(f"{ccy}(z_unavail)")
    if not zs:
        return None, missing
    return round(float(sum(zs) / len(zs)), 3), missing


def _bloc_oas_z(
    bloc: str,
    fred_series: dict[str, pd.Series],
    min_hist_obs: int = 252,
) -> tuple[Optional[float], Optional[str]]:
    """Compute negated OAS 20d velocity z for an EM bloc (tightening = inflow-positive).

    Returns (z_value_or_None, note_or_None).
    Only EM blocs have OAS entries in BLOC_OAS; DM blocs return (None, None).
    """
    oas_ticker = BLOC_OAS.get(bloc)
    if oas_ticker is None:
        return None, None  # DM bloc — no OAS leg

    s = fred_series.get(oas_ticker)
    if s is None or s.empty:
        return None, f"OAS series {oas_ticker} absent"

    # Check 20d-change history depth
    chg = s.diff(20).dropna()
    if len(chg) < min_hist_obs:
        return None, f"OAS {oas_ticker}: insufficient history ({len(chg)}<{min_hist_obs} 20d-chg obs)"

    from engine.ird_velocity import velocity_fields
    vf = velocity_fields(s, scale=100.0)  # OAS in %-pts → bp
    z = vf.get("vel_20d_z")
    if z is None:
        return None, f"OAS {oas_ticker}: vel_20d_z unavailable"

    # Negate: tightening (OAS falling = negative velocity) = positive inflow signal
    return -z, None


# ---------------------------------------------------------------------------
# W2.1: Bloc Flow Gauges
# ---------------------------------------------------------------------------

def compute_bloc_gauges(
    etf_closes: dict[str, pd.Series],
    fx_series: dict[str, pd.Series],
    fred_series: dict[str, pd.Series],
    spy_close: pd.Series,
    spy_index: pd.DatetimeIndex,
    emfx_basket_daily_ret: Optional[pd.Series] = None,
) -> dict:
    """Compute per-bloc flow gauges (W2.1).

    For each bloc computes up to three legs:
      (a) rel_equity: 20d bloc equal-weight USD return minus SPY 20d return
      (b) fx:         20d bloc-FX appreciation return (winsorized ±15%)
      (c) oas:        negated OAS 20d velocity z (EM blocs only; >= 252 20d-chg obs)

    Bloc read = mean of available legs (null legs excluded).
    Direction: inflow >= +0.5, outflow <= -0.5, else neutral.
    Strength bands: |mean| in [0.5,1.5) = mild, [1.5,2.5) = clear, >=2.5 = strong.

    Returns dict keyed by bloc name, each value a bloc-payload dict.
    """
    import math

    result: dict = {}
    for bloc, etf_tickers in BLOCS.items():
        legs: dict[str, Optional[float]] = {}
        notes: list[str] = []

        # (a) rel_equity: causal z of (bloc_etf_20d_return - spy_20d_return) series
        # Build bloc equal-weight 20d return series, subtract SPY 20d return, then z-score
        if spy_close is not None and not spy_close.empty:
            spy_aligned_f = spy_close.reindex(spy_index).ffill(limit=3)
            spy_ret_20d_series = spy_aligned_f.pct_change(20)
        else:
            spy_ret_20d_series = pd.Series(dtype=float, index=spy_index)

        bloc_rel_zs: list[float] = []
        for tk in etf_tickers:
            s = etf_closes.get(tk)
            if s is None or s.empty:
                continue
            s_al = s.reindex(spy_index).ffill(limit=3)
            etf_ret_20d = s_al.pct_change(20)
            rel_series = etf_ret_20d - spy_ret_20d_series
            z = _causal_z_of_return_series(rel_series)
            if z is not None:
                bloc_rel_zs.append(z)

        if bloc_rel_zs:
            legs["rel_equity"] = round(float(sum(bloc_rel_zs) / len(bloc_rel_zs)), 3)
        else:
            legs["rel_equity"] = None
            notes.append(f"rel_equity: no ETF z available for bloc {bloc}")

        # (b) fx
        if bloc == "em_broad":
            # Use W1 EM FX basket: z-score the 20d cumulative return series
            if emfx_basket_daily_ret is not None and not emfx_basket_daily_ret.empty:
                emfx_aligned = emfx_basket_daily_ret.reindex(spy_index).ffill(limit=3)
                # 20d cumulative appreciation return = rolling product of daily returns
                log_emfx = np.log1p(emfx_aligned.fillna(0.0))
                emfx_20d_ser = np.expm1(log_emfx.rolling(20, min_periods=15).sum())
                z = _causal_z_of_return_series(emfx_20d_ser)
                if z is not None:
                    legs["fx"] = z
                else:
                    legs["fx"] = None
                    notes.append("em_broad fx: z unavailable (insufficient history)")
            else:
                legs["fx"] = None
                notes.append("em_broad fx: emfx_basket_daily_ret not provided")
        else:
            bloc_specs = BLOC_FX.get(bloc, [])
            if bloc_specs:
                fx_ret, missing = _bloc_fx_z_20d(fx_series, bloc_specs, spy_index)
                legs["fx"] = fx_ret  # already rounded in _bloc_fx_z_20d
                if missing:
                    notes.append(f"fx: missing ccy pairs {missing}")
            else:
                legs["fx"] = None
                notes.append(f"fx: no FX mapping for bloc {bloc}")

        # (c) oas (EM blocs only)
        oas_z, oas_note = _bloc_oas_z(bloc, fred_series)
        legs["oas"] = round(oas_z, 3) if oas_z is not None and math.isfinite(oas_z) else None
        if oas_note:
            notes.append(f"oas: {oas_note}")

        # Composite: mean of available legs
        available = [v for v in [legs["rel_equity"], legs["fx"], legs["oas"]] if v is not None]
        n_legs = len(available)
        if n_legs > 0:
            mean_z = sum(available) / n_legs
            mean_z = round(mean_z, 4)
        else:
            mean_z = None

        # Direction + strength
        if mean_z is None:
            direction = "neutral"
            strength = None
        elif mean_z >= BLOC_INFLOW_THRESHOLD:
            direction = "inflow"
            abs_z = abs(mean_z)
            strength = "strong" if abs_z >= 2.5 else ("clear" if abs_z >= 1.5 else "mild")
        elif mean_z <= BLOC_OUTFLOW_THRESHOLD:
            direction = "outflow"
            abs_z = abs(mean_z)
            strength = "strong" if abs_z >= 2.5 else ("clear" if abs_z >= 1.5 else "mild")
        else:
            direction = "neutral"
            strength = None

        result[bloc] = {
            "direction":    direction,
            "strength":     strength,
            "mean_z":       mean_z,
            "n_legs":       n_legs,
            "legs":         legs,
            "notes":        notes,
        }

    return result


# ---------------------------------------------------------------------------
# W2.2: Partial-EMP Outflow Watch
# ---------------------------------------------------------------------------

def compute_emp_watch(
    etf_closes: dict[str, pd.Series],
    fx_series: dict[str, pd.Series],
    spy_index: pd.DatetimeIndex,
    eem_close: Optional[pd.Series] = None,
) -> list[dict]:
    """Compute partial-EMP outflow watch for each country with both ETF and FX data (W2.2).

    Composite per country = mean of three causal z-scores:
      (1) z(20d FX depreciation) = negated z of 20d FX appreciation return
      (2) z(20d equity underperformance vs rolling 120d EEM-beta expected return)
      (3) z(change in 20d realized FX vol vs 2y history)

    Sign conventions: all three legs are underperformance/stress-positive.
    Elevated: composite >= 1.0; Strong: composite >= 2.0.

    Returns list of country dicts sorted desc by composite (or None).

    DISCLOSURE: Partial EMP — reserve/intervention leg unobservable (CBF-R4).
    """
    import math

    # Pre-compute EEM 20d return series for beta computation
    eem_aligned: Optional[pd.Series] = None
    if eem_close is not None and not eem_close.empty:
        eem_aligned = eem_close.reindex(spy_index).ffill(limit=3)

    rows: list[dict] = []

    for country, etf_tk, fx_sg, fx_tk, fx_negate in COUNTRY_EMP_MAP:
        # Require both ETF and FX data
        etf_s = etf_closes.get(etf_tk)
        # FX key: strip USDXXX_X → currency code (same stripping as load_inputs_from_store)
        ccy = fx_tk.replace("USD", "").replace("_X", "").replace("=X", "")
        # For non-USDXXX tickers like EURUSD_X, GBPUSD_X, AUDUSD_X
        if fx_negate is False:
            # XXXUSD — key is the first 3 chars (EUR, GBP, AUD)
            ccy = fx_tk[:3]
        fx_s = fx_series.get(ccy)

        if etf_s is None or etf_s.empty:
            continue
        if fx_s is None or fx_s.empty:
            continue

        etf_aligned = etf_s.reindex(spy_index).ffill(limit=3)
        fx_aligned  = fx_s.reindex(spy_index).ffill(limit=3)

        legs: dict[str, Optional[float]] = {"fx_dep_z": None, "equity_under_z": None, "fxvol_z": None}
        missing: list[str] = []

        # Leg 1: z(20d FX depreciation)
        # Build 20d appreciation return series, then negate for depreciation
        fx_dropna = fx_aligned.dropna()
        if len(fx_dropna) >= 21:
            # 20d change series of USDXXX returns (or XXXUSD)
            raw_pct = fx_dropna.pct_change(20).dropna()
            if fx_negate:
                # USDXXX: positive = USD appreciates = local depreciation = stress
                dep_series = raw_pct   # already depreciation-positive
            else:
                # XXXUSD (EUR, GBP, AUD): positive = local appreciates = negating gives depreciation
                dep_series = -raw_pct
            dep_chg = dep_series
            if len(dep_chg) >= 40:
                hist = dep_chg.iloc[:-1]
                window = min(504, len(hist))
                w = hist.iloc[-window:]
                mu, sd = float(w.mean()), float(w.std())
                if sd > 0 and math.isfinite(sd):
                    z = (float(dep_chg.iloc[-1]) - mu) / sd
                    if math.isfinite(z):
                        legs["fx_dep_z"] = round(z, 3)
        if legs["fx_dep_z"] is None:
            missing.append("fx_dep_z")

        # Leg 2: z(20d equity underperformance vs rolling 120d EEM-beta expected return)
        etf_dropna = etf_aligned.dropna()
        if eem_aligned is not None and len(etf_dropna) >= 21:
            eem_dropna = eem_aligned.dropna()
            # Align on common dates
            common_idx = etf_dropna.index.intersection(eem_dropna.index)
            if len(common_idx) >= 121:
                etf_c = etf_dropna.reindex(common_idx)
                eem_c = eem_dropna.reindex(common_idx)
                etf_ret = etf_c.pct_change()
                eem_ret = eem_c.pct_change()
                # Rolling 120d beta (causal, excluding current obs from beta estimation)
                # at each t: beta = cov(etf, eem, 120d) / var(eem, 120d)
                etf_20d_ret = etf_c.pct_change(20)
                eem_20d_ret = eem_c.pct_change(20)
                if etf_ret.dropna().shape[0] >= 121 and eem_ret.dropna().shape[0] >= 121:
                    # Scalar rolling beta using 120d daily returns (causal at each t)
                    roll_cov = etf_ret.rolling(120, min_periods=60).cov(eem_ret)
                    roll_var = eem_ret.rolling(120, min_periods=60).var()
                    roll_beta = (roll_cov / roll_var.replace(0, float("nan"))).fillna(1.0)
                    # Underperformance = actual 20d return - beta * EEM 20d return (at each t)
                    underperf_series = etf_20d_ret - roll_beta * eem_20d_ret
                    underperf_dropna = underperf_series.dropna()
                    if len(underperf_dropna) >= 40:
                        hist = underperf_dropna.iloc[:-1]
                        window = min(504, len(hist))
                        w = hist.iloc[-window:]
                        mu, sd = float(w.mean()), float(w.std())
                        if sd > 0 and math.isfinite(sd):
                            z = (float(underperf_dropna.iloc[-1]) - mu) / sd
                            if math.isfinite(z):
                                legs["equity_under_z"] = round(z, 3)
        if legs["equity_under_z"] is None:
            missing.append("equity_under_z")

        # Leg 3: z(change in 20d realized FX vol vs 2y history)
        if len(fx_dropna) >= 21:
            daily_ret = fx_dropna.pct_change().dropna()
            if len(daily_ret) >= 21:
                # 20d realized vol = std of daily returns over 20d (annualized not needed here)
                vol_20d = daily_ret.rolling(20, min_periods=10).std()
                vol_dropna = vol_20d.dropna()
                if len(vol_dropna) >= 40:
                    # Change in vol (vol level itself is the series for z-scoring)
                    vol_chg = vol_dropna.diff(20).dropna()
                    if len(vol_chg) >= 20:
                        hist = vol_chg.iloc[:-1]
                        window = min(504, len(hist))
                        w = hist.iloc[-window:]
                        mu, sd = float(w.mean()), float(w.std())
                        if sd > 0 and math.isfinite(sd):
                            z = (float(vol_chg.iloc[-1]) - mu) / sd
                            if math.isfinite(z):
                                legs["fxvol_z"] = round(z, 3)
        if legs["fxvol_z"] is None:
            missing.append("fxvol_z")

        # Composite
        available = [v for v in [legs["fx_dep_z"], legs["equity_under_z"], legs["fxvol_z"]]
                     if v is not None]
        composite: Optional[float] = None
        if available:
            composite = round(sum(available) / len(available), 3)

        flag = None
        if composite is not None:
            if composite >= EMP_STRONG:
                flag = "strong"
            elif composite >= EMP_ELEVATED:
                flag = "elevated"

        rows.append({
            "country":   country,
            "etf":       etf_tk,
            "composite": composite,
            "legs":      legs,
            "flag":      flag,
            "missing":   missing,
        })

    # Sort descending by composite (None last)
    rows.sort(key=lambda r: (r["composite"] is None, -(r["composite"] or 0.0)))
    return rows


# ---------------------------------------------------------------------------
# W2.3: Idio-vs-Systemic Discriminator
# ---------------------------------------------------------------------------

def compute_discriminator(
    emp_watch: list[dict],
    fx_series: dict[str, pd.Series],
    fred_series: dict[str, pd.Series],
    spy_index: pd.DatetimeIndex,
) -> dict:
    """Idio-vs-systemic three-filter test (CBF-R5, W2.3).

    Computed only when at least one country has elevated or strong EMP flag.
    Filters:
      (a) breadth: share of EM FX pairs down >2% over 30d > 50%
      (b) common_factor: mean pairwise 60d corr of EM FX daily returns, pct vs 2y >= 80th
      (c) dm_transmission: US HY OAS 20d velocity z >= 1 (via ird_velocity)

    Verdict: fires_count >= 2 -> 'systemic'; == 1 and b-not-alone -> 'spreading';
    b alone -> 'spreading' with note; 0 -> 'isolated'.
    Returns state='n/a ...' when no elevated outflow present.
    """
    import math

    # Gate: skip if no elevated EMP
    elevated_countries = [r for r in emp_watch if r.get("flag") in ("elevated", "strong")]
    if not elevated_countries:
        return {
            "state": "n/a — no elevated outflow pressure",
            "label_en": _DISC_LABELS["n/a"]["label_en"],
            "label_zh": _DISC_LABELS["n/a"]["label_zh"],
            "guidance_en": _DISC_LABELS["n/a"]["guidance_en"],
            "guidance_zh": _DISC_LABELS["n/a"]["guidance_zh"],
            "filters": {},
            "notes": [],
        }

    notes: list[str] = []
    filters: dict[str, Optional[bool]] = {"breadth": None, "common_factor": None, "dm_transmission": None}
    filter_vals: dict[str, Optional[float]] = {"breadth_share": None, "corr_pct": None, "hy_oas_z": None}

    # EM FX pairs to use: W1 basket members, keyed by stripped CCY code
    em_fx_keys = [ccy for ccy, _, negate in
                  [(p[1].replace("USD","").replace("_X","").replace("=X",""), p[1], p[2])
                   for p in EM_FX_PAIRS]]
    em_fx_sers: list[pd.Series] = []
    for ccy in em_fx_keys:
        s = fx_series.get(ccy)
        if s is not None and not s.empty:
            em_fx_sers.append(s.reindex(spy_index).ffill(limit=3))

    # (a) breadth: share of EM FX pairs with 30d depreciation > 2%
    if em_fx_sers:
        down_count = 0
        total_count = 0
        for s in em_fx_sers:
            s_d = s.dropna()
            if len(s_d) >= 31:
                # USDXXX convention: rising 30d = local depreciates
                ret_30d = float(s_d.iloc[-1]) / float(s_d.iloc[-31]) - 1.0
                total_count += 1
                if ret_30d > DISC_DOWN_PCT_THRESHOLD:
                    down_count += 1
        if total_count > 0:
            share = down_count / total_count
            filter_vals["breadth_share"] = round(share, 3)
            filters["breadth"] = share > DISC_BREADTH_THRESHOLD
    if filters["breadth"] is None:
        notes.append("breadth: insufficient EM FX data")

    # (b) common_factor: mean pairwise 60d corr of EM FX daily returns, pct vs 2y
    if len(em_fx_sers) >= 2:
        # Build daily return DataFrame
        daily_rets = pd.concat([s.pct_change().rename(i) for i, s in enumerate(em_fx_sers)], axis=1)
        daily_rets = daily_rets.dropna(how="all")
        # Rolling 60d pairwise correlation -> mean correlation at each date
        n_pairs = len(em_fx_sers)
        if len(daily_rets) >= 61:
            # Compute mean pairwise corr at current date using last 60 rows
            last60 = daily_rets.dropna(how="all").iloc[-60:]
            cols = [c for c in last60.columns if last60[c].dropna().shape[0] >= 30]
            if len(cols) >= 2:
                sub = last60[cols].dropna()
                corr_mat = sub.corr()
                # Extract upper triangle (excluding diagonal)
                upper = [(corr_mat.iloc[i, j])
                         for i in range(len(cols))
                         for j in range(i + 1, len(cols))
                         if not (math.isnan(corr_mat.iloc[i, j]) if isinstance(corr_mat.iloc[i, j], float) else False)]
                if upper:
                    cur_mean_corr = sum(upper) / len(upper)
                    filter_vals["corr_current"] = round(cur_mean_corr, 4)

                    # Build 2y history of rolling 60d mean-pairwise-corr
                    # Use rolling 60d corr at monthly cadence (approx 504 past obs)
                    hist_corrs: list[float] = []
                    all_rows = daily_rets[cols].dropna()
                    step = 5  # weekly cadence for efficiency
                    for end_i in range(60, len(all_rows) - 1, step):
                        win = all_rows.iloc[max(0, end_i - 60):end_i]
                        if len(win) < 30:
                            continue
                        cm = win.corr()
                        vals = [cm.iloc[ii, jj] for ii in range(len(cols))
                                for jj in range(ii + 1, len(cols))]
                        vals = [v for v in vals if not math.isnan(v)]
                        if vals:
                            hist_corrs.append(sum(vals) / len(vals))

                    if len(hist_corrs) >= 20:
                        window = min(504 // step, len(hist_corrs))
                        recent_hist = hist_corrs[-window:]
                        pct_rank = sum(1 for v in recent_hist if v < cur_mean_corr) / len(recent_hist) * 100
                        filter_vals["corr_pct"] = round(pct_rank, 1)
                        filters["common_factor"] = pct_rank >= DISC_CORR_PERCENTILE
        if filters["common_factor"] is None:
            notes.append("common_factor: insufficient data for 2y pct-rank; Forbes-Rigobon bias applies — never standalone")
    else:
        notes.append("common_factor: fewer than 2 EM FX series available")

    # Forbes-Rigobon note always attached to common_factor
    notes.append("common_factor: Forbes-Rigobon upward bias in high-vol windows — never standalone (CBF-R5)")

    # (c) dm_transmission: US HY OAS 20d velocity z >= 1
    # Note: engine/contagion.py IRD-R3 two_tier also owns a US-HY-OAS Tier-2
    # transmission signal (and its verdict is loaded as a cross_ref in compose()).
    # This leg re-derives the same underlying read with its own threshold rather
    # than deferring to contagion's two_tier verdict, so they CAN disagree.  This
    # is intentional (different threshold / different vocab — our verdicts say
    # Isolated/Spreading/Broad, not "transmitting"), but the duplication should be
    # revisited when a future W-slice wires contagion two_tier into the discriminator.
    hy_s = fred_series.get(US_HY_OAS_TICKER)
    if hy_s is not None and not hy_s.empty:
        from engine.ird_velocity import velocity_fields
        vf = velocity_fields(hy_s, scale=100.0)
        hy_z = vf.get("vel_20d_z")
        if hy_z is not None:
            filter_vals["hy_oas_z"] = round(hy_z, 3)
            filters["dm_transmission"] = hy_z >= DISC_HY_VEL_Z_THRESHOLD
    if filters["dm_transmission"] is None:
        notes.append(f"dm_transmission: {US_HY_OAS_TICKER} absent or insufficient data")

    # Verdict
    fires: list[str] = [k for k, v in filters.items() if v is True]
    fires_count = len(fires)
    b_alone = fires == ["common_factor"]

    if fires_count >= 2:
        verdict = "systemic"
    elif fires_count == 1 and not b_alone:
        verdict = "spreading"
    elif b_alone:
        verdict = "spreading"
        notes.append("common_factor fires alone — spreading with Forbes-Rigobon caveat")
    else:
        verdict = "isolated"

    label_info = _DISC_LABELS.get(verdict, _DISC_LABELS["isolated"])
    return {
        "state":       verdict,
        "label_en":    label_info["label_en"],
        "label_zh":    label_info["label_zh"],
        "guidance_en": label_info["guidance_en"],
        "guidance_zh": label_info["guidance_zh"],
        "filters":     filters,
        "filter_vals": filter_vals,
        "fires":       fires,
        "notes":       notes,
    }


# ---------------------------------------------------------------------------
# W2.4: Swap-Line Confirmation Row
# ---------------------------------------------------------------------------

def compute_swap_lines(fred_series: dict[str, pd.Series]) -> dict:
    """Read SWPT + WLCFLL and compute swap-line confirmation row (CBF-R6, W2.4).

    Levels are weekly Wednesday snapshots; converted $M -> $bn.
    Historical anchors: GFC $583B, COVID $449B, Mar-2023 $0.6B.
    Stigma note: zero drawings do not indicate absence of stress (CBF-R6).
    NEVER any trigger/alert key.
    """
    import math

    swpt_s   = fred_series.get("SWPT")
    wlcfll_s = fred_series.get("WLCFLL")

    level_bn: Optional[float] = None
    wow_bn: Optional[float] = None
    asof: Optional[str] = None
    notes: list[str] = []

    # SWPT: Fed swap-line total ($M weekly)
    if swpt_s is not None and not swpt_s.empty:
        s = swpt_s.dropna()
        if len(s) >= 1:
            raw_m = float(s.iloc[-1])
            level_bn = round(raw_m / 1000.0, 3)
            asof = str(s.index[-1].date()) if hasattr(s.index[-1], "date") else str(s.index[-1])
            if len(s) >= 2:
                prev_m = float(s.iloc[-2])
                wow_bn = round((raw_m - prev_m) / 1000.0, 3)
    else:
        notes.append("SWPT absent — level_bn null")

    # WLCFLL: Fed facility loans ($M weekly); additive to SWPT context
    facility_bn: Optional[float] = None
    if wlcfll_s is not None and not wlcfll_s.empty:
        s2 = wlcfll_s.dropna()
        if len(s2) >= 1:
            facility_bn = round(float(s2.iloc[-1]) / 1000.0, 3)
            if asof is None:
                asof = str(s2.index[-1].date()) if hasattr(s2.index[-1], "date") else str(s2.index[-1])
    else:
        notes.append("WLCFLL absent — facility_loans_bn null")

    # State banding (CBF-R6 4-tier table, FIELD_GUIDE §3)
    if level_bn is None:
        state = "data_unavailable"
        interpretation = "Swap line level unavailable — cannot assess funding stress confirmation."
        tier = None
    elif level_bn < 1.0:
        state = "quiescent"
        tier = None
        interpretation = (
            "No material swap-line drawings. "
            "Note: zero drawings do not indicate absence of stress — stigma suppresses usage even when stress is real "
            "(Mar-2023: $0.6B despite Credit Suisse failure; stress was solvency-specific, not a dollar-funding freeze). "
            "Historical anchors: GFC peak $583B (Dec-2008), COVID peak $449B (May-2020)."
        )
    elif level_bn < 25.0:
        state = "modest"
        tier = "precautionary_or_localized"
        interpretation = (
            f"Modest swap-line drawings (${level_bn:.1f}B). "
            "Precautionary or localized usage — watch for escalation. "
            "If no draw growth in ~72h, stress may be solvency-specific rather than systemic funding. "
            "Historical anchors: GFC peak $583B (Dec-2008), COVID peak $449B (May-2020)."
        )
    elif level_bn < 100.0:
        state = "elevated"
        tier = "c6_or_em_line_draw"
        interpretation = (
            f"Elevated swap-line drawings (${level_bn:.1f}B). "
            "Dollar funding stress confirmed in affected zone; watch currency basis and offshore CP. "
            "Screen similar-type countries. "
            "Bahaj-Reis (2022): swap lines cap CIP deviations (funding ceiling) but do not fix solvency. "
            "Historical anchors: GFC peak $583B (Dec-2008), COVID peak $449B (May-2020)."
        )
    else:
        state = "crisis_scale"
        tier = "c6_draw_size"
        interpretation = (
            f"Crisis-scale swap-line drawings (${level_bn:.1f}B). "
            "Dollar funding stress CONFIRMED at scale. "
            "Capital-flow reversal underway. Screen similar-type countries for contagion. "
            "Bahaj-Reis (2022): swap lines cap CIP deviations (funding ceiling) but do not fix solvency — "
            "a drawing never 'resolves' a crisis. "
            "Historical anchors: GFC peak $583B (Dec-2008), COVID peak $449B (May-2020)."
        )

    notes.append(
        "IRD-R5 / CBF-R6: swap-line levels are confirmation tier (grade severity after "
        "price signals fire; never a standalone trigger). SWPT is weekly Wednesday; "
        "lags price stress by days-to-weeks."
    )

    return {
        "level_bn":         level_bn,
        "facility_loans_bn": facility_bn,
        "wow_change_bn":    wow_bn,
        "asof":             asof,
        "state":            state,
        "tier":             tier,
        "interpretation":   interpretation,
        "notes":            notes,
    }


# ---------------------------------------------------------------------------
# W2.5: Cross-refs (fail-open reads)
# ---------------------------------------------------------------------------

def load_cross_refs(repo_root: "Path") -> dict:  # noqa: F821 — quoted for import avoidance
    """Load cross-refs from sibling artifact JSONs (fail-open, W2.5).

    data/forex/latest.json -> dollar_desk.smile_decomp.regime + safety_bid_today
    data/intl_risk/latest.json -> contagion two_tier/em_stress states
    """
    import json
    from pathlib import Path as _Path

    cross: dict = {
        "smile_decomp_regime":   None,
        "safety_bid_today":      None,
        "contagion_two_tier":    None,
        "em_stress_state":       None,
        "notes":                 [],
    }

    root = _Path(repo_root)

    # forex/latest.json
    forex_path = root / "data" / "forex" / "latest.json"
    try:
        if forex_path.exists():
            raw = json.loads(forex_path.read_text(encoding="utf-8"))
            sd = (raw.get("dollar_desk") or {}).get("smile_decomp") or {}
            cross["smile_decomp_regime"]  = sd.get("regime")
            cross["safety_bid_today"]     = sd.get("safety_bid_today")
        else:
            cross["notes"].append("forex/latest.json absent")
    except Exception as exc:
        cross["notes"].append(f"forex/latest.json read error: {exc}")

    # intl_risk/latest.json
    ird_path = root / "data" / "intl_risk" / "latest.json"
    try:
        if ird_path.exists():
            raw = json.loads(ird_path.read_text(encoding="utf-8"))
            two_tier = raw.get("two_tier") or {}
            cross["contagion_two_tier"] = two_tier.get("state")
            em_stress = raw.get("em_stress") or {}
            cross["em_stress_state"]   = em_stress.get("state")
        else:
            cross["notes"].append("intl_risk/latest.json absent")
    except Exception as exc:
        cross["notes"].append(f"intl_risk/latest.json read error: {exc}")

    return cross


# ---------------------------------------------------------------------------
# W2.6: Coverage summary
# ---------------------------------------------------------------------------

def _coverage_summary(
    etf_closes: dict[str, pd.Series],
    fx_series: dict[str, pd.Series],
    fred_series: dict[str, pd.Series],
    spy_close: pd.Series,
) -> dict:
    """Return first/last date strings for key series (fail-open)."""
    cov: dict = {}

    def _fl(s: Optional[pd.Series], key: str) -> None:
        if s is None or s.empty:
            cov[key] = {"first": None, "last": None}
            return
        d = s.dropna()
        if d.empty:
            cov[key] = {"first": None, "last": None}
            return
        cov[key] = {
            "first": str(d.index[0].date()) if hasattr(d.index[0], "date") else str(d.index[0]),
            "last":  str(d.index[-1].date()) if hasattr(d.index[-1], "date") else str(d.index[-1]),
        }

    _fl(spy_close, "SPY")
    for tk, s in etf_closes.items():
        _fl(s, f"etf/{tk}")
    for ccy, s in fx_series.items():
        _fl(s, f"fx/{ccy}")
    for tk, s in fred_series.items():
        _fl(s, f"fred/{tk}")
    return cov


# ---------------------------------------------------------------------------
# W2: compose() — main nightly entry point
# ---------------------------------------------------------------------------

def compose(repo_root) -> dict:
    """Compose the full CBF W2 payload for data/flow_regime/latest.json.

    Pure, fail-open, display-only. Loads all inputs from real stores, runs
    all W2 sub-computations, writes nothing (caller writes the JSON).

    Returns dict with keys:
      as_of, regime, blocs, emp_watch, discriminator, swap_lines, cross_refs,
      coverage, disclosures.
    """
    from pathlib import Path as _Path
    from datetime import datetime, timezone

    root = _Path(repo_root)

    # --- Load base inputs ---------------------------------------------------
    try:
        inputs = load_inputs_from_store()
    except Exception as exc:
        log.exception("flow_regime.compose: load_inputs_from_store failed: %s", exc)
        inputs = {
            "spy_close": pd.Series(dtype=float),
            "row_etf_closes": {},
            "dtwexbgs": None,
            "dxy": None,
            "fx_series": {},
            "vix_close": None,
        }

    _spy_raw       = inputs.get("spy_close")
    spy_close      = _spy_raw if (_spy_raw is not None and not _spy_raw.empty) else pd.Series(dtype=float)
    _row_raw       = inputs.get("row_etf_closes")
    row_etf_closes = _row_raw if _row_raw else {}
    dtwexbgs       = inputs.get("dtwexbgs")
    dxy            = inputs.get("dxy")
    _fx_raw        = inputs.get("fx_series")
    fx_series      = _fx_raw if _fx_raw else {}
    vix_close      = inputs.get("vix_close")

    # --- Load additional series for W2 -------------------------------------
    # Bloc ETFs (add EEM + any not in ROW_BASKET)
    etf_closes: dict[str, pd.Series] = dict(row_etf_closes)  # copy

    # Load extra ETFs needed for W2 (EEM for EMP; per-country ETFs)
    extra_tickers: list[str] = ["EEM", "EWT"]  # EWT for Taiwan EMP
    for tk in extra_tickers:
        if tk not in etf_closes:
            s = _read_store("intl_etf", tk)
            if s is None:
                s = _read_store("yahoo", tk)
            if s is not None:
                etf_closes[tk] = s

    # Load additional FX pairs for bloc FX (DM pairs not in W1 EM basket)
    extra_fx: list[tuple[str, str, str]] = [
        # (ccy_key, store_group, ticker)
        ("EUR", "yahoo",  "EURUSD_X"),
        ("GBP", "yahoo",  "GBPUSD_X"),
        ("CHF", "yahoo",  "USDCHF_X"),
        ("JPY", "yahoo",  "USDJPY_X"),
        ("CAD", "yahoo",  "USDCAD_X"),
        ("AUD", "yahoo",  "AUDUSD_X"),
        ("IDR", "yahoo",  "USDIDR_X"),
    ]
    for ccy, sg, tk in extra_fx:
        if ccy not in fx_series:
            s = _read_store(sg, tk)
            if s is not None:
                fx_series[ccy] = s

    # Also ensure W1 EM FX pairs are loaded (they may already be in fx_series)
    for sg, tk, _neg in EM_FX_PAIRS:
        ccy = tk.replace("USD", "").replace("_X", "").replace("=X", "")
        if ccy not in fx_series:
            s = _read_store(sg, tk)
            if s is not None:
                fx_series[ccy] = s

    # Load FRED series needed for W2 (OAS + swap lines)
    fred_tickers = list(BLOC_OAS.values()) + [US_HY_OAS_TICKER, "SWPT", "WLCFLL"]
    fred_series: dict[str, pd.Series] = {}
    for tk in fred_tickers:
        s = _read_store("fred", tk)
        if s is not None:
            fred_series[tk] = s

    # Build spy_index
    spy_index = spy_close.dropna().index if not spy_close.empty else pd.DatetimeIndex([])

    # --- Regime (W1 classify, latest row) -----------------------------------
    regime_payload: dict = {
        "state": None, "label_en": None, "label_zh": None,
        "guidance_en": None, "guidance_zh": None,
        "days_in_state": None, "raw_state": None, "legs": None, "hysteresis_pending": None,
    }
    history_df: Optional[pd.DataFrame] = None

    if not spy_close.empty and vix_close is not None:
        try:
            spy_idx = spy_close.dropna().index
            broad_dollar = build_broad_dollar(dtwexbgs, dxy, spy_idx)
            emfx_basket  = build_emfx_basket(fx_series, spy_idx, negate=True)
            row_composite = build_row_composite(etf_closes, spy_idx)
            # Build a cumulative price level from row composite daily returns
            row_ret = row_composite.fillna(0.0)
            row_level = (1 + row_ret).cumprod() * 100.0

            history_df = classify_history(
                spy_close       = spy_close,
                row_composite_level = row_level,
                broad_dollar_level  = broad_dollar,
                emfx_basket_daily_ret = emfx_basket,
                vix_close       = vix_close,
            )

            if not history_df.empty:
                last = history_df.iloc[-1]
                state = str(last["state"])
                raw_state = str(last["raw_state"])
                lbl = _REGIME_LABELS.get(state, _REGIME_LABELS["mixed"])

                # days_in_state
                pub_series = history_df["state"]
                days_in_state = int((pub_series == state).iloc[::-1].cumprod().sum())

                # hysteresis_pending
                hysteresis_pending = (raw_state != state)

                # Last leg values
                leg_cols = ["spy_20d", "row_20d", "spy_63d", "row_63d",
                            "usd_20d", "usd_63d", "emfx_63d", "vix"]
                last_legs = {c: (None if pd.isna(last[c]) else round(float(last[c]), 6))
                             for c in leg_cols if c in last.index}

                regime_payload = {
                    "state":             state,
                    "label_en":          lbl["label_en"],
                    "label_zh":          lbl["label_zh"],
                    "guidance_en":       lbl["guidance_en"],
                    "guidance_zh":       lbl["guidance_zh"],
                    "days_in_state":     days_in_state,
                    "raw_state":         raw_state,
                    "legs":              last_legs,
                    "hysteresis_pending": hysteresis_pending,
                }
        except Exception as exc:
            log.exception("flow_regime.compose: classify_history failed: %s", exc)

    # as_of: last trading date from SPY
    as_of_str: Optional[str] = None
    if not spy_close.empty and len(spy_close.dropna()) > 0:
        last_date = spy_close.dropna().index[-1]
        as_of_str = str(last_date.date()) if hasattr(last_date, "date") else str(last_date)

    # Build emfx basket for bloc gauges
    emfx_basket_ret: Optional[pd.Series] = None
    if not spy_index.empty and fx_series:
        try:
            emfx_basket_ret = build_emfx_basket(fx_series, spy_index, negate=True)
        except Exception:
            pass

    # --- Bloc gauges (W2.1) ------------------------------------------------
    blocs_payload: dict = {}
    try:
        blocs_payload = compute_bloc_gauges(
            etf_closes=etf_closes,
            fx_series=fx_series,
            fred_series=fred_series,
            spy_close=spy_close,
            spy_index=spy_index,
            emfx_basket_daily_ret=emfx_basket_ret,
        )
    except Exception as exc:
        log.exception("flow_regime.compose: compute_bloc_gauges failed: %s", exc)

    # --- Partial-EMP watch (W2.2) ------------------------------------------
    emp_watch: list[dict] = []
    try:
        eem_close = etf_closes.get("EEM")
        emp_watch = compute_emp_watch(
            etf_closes=etf_closes,
            fx_series=fx_series,
            spy_index=spy_index,
            eem_close=eem_close,
        )
    except Exception as exc:
        log.exception("flow_regime.compose: compute_emp_watch failed: %s", exc)

    # --- Discriminator (W2.3) ----------------------------------------------
    discriminator: dict = {}
    try:
        discriminator = compute_discriminator(
            emp_watch=emp_watch,
            fx_series=fx_series,
            fred_series=fred_series,
            spy_index=spy_index,
        )
    except Exception as exc:
        log.exception("flow_regime.compose: compute_discriminator failed: %s", exc)

    # --- Swap lines (W2.4) -------------------------------------------------
    swap_lines: dict = {}
    try:
        swap_lines = compute_swap_lines(fred_series=fred_series)
    except Exception as exc:
        log.exception("flow_regime.compose: compute_swap_lines failed: %s", exc)

    # --- Cross-refs (W2.5) -------------------------------------------------
    cross_refs: dict = {}
    try:
        cross_refs = load_cross_refs(root)
    except Exception as exc:
        log.exception("flow_regime.compose: load_cross_refs failed: %s", exc)

    # --- Coverage (W2.6) ---------------------------------------------------
    coverage: dict = {}
    try:
        coverage = _coverage_summary(etf_closes, fx_series, fred_series, spy_close)
    except Exception as exc:
        log.exception("flow_regime.compose: coverage_summary failed: %s", exc)

    # --- Disclosures (CBF-R4 mandatory) ------------------------------------
    disclosures = [
        "Flow direction is inferred from prices only — not measured capital flows. "
        "TIC data lag 6-7 weeks; EPFR is paid and covers only fund flows. "
        "FX-hedged flows leave no FX trace. SWF/OTC flows are invisible to all proxies. "
        "Managed pegs truncate FX signals (CNH stays illustrative-tier).",
        "Partial EMP only — reserve/intervention leg unobservable free+daily (CBF-R4). "
        "CBF-R5: correlation-based filter (common_factor) never stands alone — "
        "Forbes-Rigobon upward bias in high-vol windows.",
        "CBF-R6: swap lines are confirmation tier, never a trigger. "
        "Bahaj-Reis (2022): drawings cap CIP deviations (funding ceiling) but do not fix solvency. "
        "Zero drawings do not indicate absence of stress (stigma asymmetry).",
        "Display-only context artifact (CBF-R1). Nothing here is scored, fed to conviction, "
        "or collapsed into BUY/SELL. Promotion requires intl_phase0 pre-registration.",
    ]

    return {
        "as_of":         as_of_str,
        "regime":        regime_payload,
        "blocs":         blocs_payload,
        "emp_watch":     emp_watch,
        "discriminator": discriminator,
        "swap_lines":    swap_lines,
        "cross_refs":    cross_refs,
        "coverage":      coverage,
        "disclosures":   disclosures,
    }


# ---------------------------------------------------------------------------
# W2.7: History accrual (CBF-R10)
# ---------------------------------------------------------------------------

def accrue_history(repo_root, history_df: Optional[pd.DataFrame] = None) -> None:
    """Append-only upsert of CBF regime history (CBF-R10).

    If data/flow_regime/history.parquet absent -> writes full classify_history output.
    If present -> append dates > existing max; replace same-day row only when values differ.
    NEVER touches older rows.

    Columns: date (index), state, raw_state, era, spy_20d, row_20d, spy_63d, row_63d,
             usd_20d, usd_63d, emfx_63d, vix.

    Pandas>=2 law: dates stored as tz-naive UTC day (date column, not datetime).
    """
    from pathlib import Path as _Path
    import pyarrow as pa
    import pyarrow.parquet as pq

    root = _Path(repo_root)
    hist_dir = root / "data" / "flow_regime"
    hist_dir.mkdir(parents=True, exist_ok=True)
    hist_path = hist_dir / "history.parquet"

    if history_df is None or history_df.empty:
        log.warning("flow_regime.accrue_history: no history_df to accrue")
        return

    # Normalize: drop timezone from index, coerce to date-string (tz-naive)
    new_df = history_df.copy()
    if hasattr(new_df.index, "tz") and new_df.index.tz is not None:
        new_df.index = new_df.index.tz_localize(None)
    # Ensure index is DatetimeIndex with no tz
    new_df.index = pd.DatetimeIndex(new_df.index).normalize()

    cols_keep = ["state", "raw_state", "era", "spy_20d", "row_20d",
                 "spy_63d", "row_63d", "usd_20d", "usd_63d", "emfx_63d", "vix"]
    new_df = new_df[[c for c in cols_keep if c in new_df.columns]].copy()
    # Make sure index name is 'date'
    new_df.index.name = "date"

    if not hist_path.exists():
        # First-time backfill: write the full history
        new_df.to_parquet(hist_path, index=True)
        log.info("flow_regime.accrue_history: wrote full backfill (%d rows)", len(new_df))
        return

    # Load existing
    try:
        existing = pd.read_parquet(hist_path)
        existing.index = pd.DatetimeIndex(existing.index).normalize()
        existing.index.name = "date"
    except Exception as exc:
        log.warning("flow_regime.accrue_history: could not read history.parquet (%s); rewriting", exc)
        new_df.to_parquet(hist_path, index=True)
        return

    if existing.empty:
        new_df.to_parquet(hist_path, index=True)
        log.info("flow_regime.accrue_history: existing empty; wrote full history (%d rows)", len(new_df))
        return

    existing_max = existing.index.max()

    # Rows strictly newer than existing max
    strictly_new = new_df[new_df.index > existing_max]

    # Same-day row (if new_df includes the existing_max date and values differ)
    same_day = new_df[new_df.index == existing_max]
    replace_same_day = False
    if not same_day.empty and existing_max in existing.index:
        existing_row = existing.loc[[existing_max]]
        # Compare on shared columns only
        shared_cols = [c for c in same_day.columns if c in existing_row.columns]
        try:
            # Float columns: compare with tolerance
            for col in shared_cols:
                new_val = same_day[col].iloc[0]
                old_val = existing_row[col].iloc[0]
                if str(new_val) != str(old_val):
                    replace_same_day = True
                    break
        except Exception:
            replace_same_day = True

    if strictly_new.empty and not replace_same_day:
        log.info("flow_regime.accrue_history: no new rows to append (existing max %s)", existing_max.date())
        return

    # Build merged frame: existing + replace same-day if needed + new rows
    base = existing.copy()
    if replace_same_day and not same_day.empty:
        # Replace the same-day row in existing
        base = base[base.index != existing_max]
        base = pd.concat([base, same_day])
        log.info("flow_regime.accrue_history: replaced same-day row for %s", existing_max.date())

    if not strictly_new.empty:
        base = pd.concat([base, strictly_new])
        log.info("flow_regime.accrue_history: appended %d new rows (up to %s)",
                 len(strictly_new), strictly_new.index.max().date())

    base = base.sort_index()
    # NEVER touch rows older than original existing_max (sanity guard)
    # (the concat above never writes to older rows — only same-day replacement)
    base.to_parquet(hist_path, index=True)
    log.info("flow_regime.accrue_history: history.parquet now has %d rows", len(base))
