"""Oracle O0 — Rotation Panel: per-node per-day feature matrix.

WHAT
----
Builds two survivorship-tiered DataFrames (panel_s and panel_m) that are
the single substrate feeding every downstream Oracle consumer: backtests
(O2), pattern memory (O3), and the Time Machine UI (O5).

WHY
---
All existing rotation surfaces (group_flow, subsector_rotation) are either
display-only computes over the live snapshot or aggregate fingerprints for
a single point in time.  Oracle needs a *full daily time series* of every
node's relative motion with the same columns at every granularity so that
(a) Episode detection can replay history and (b) the Time Machine can scrub
it.  One build, three payoffs — building it three separate times would
produce three subtly-incompatible feature sets.

HONESTY FRAMING
---------------
* Tier S (sector ETFs + PIT-SP1500 member panels): survivorship-CLEAN for
  the ETF-level RS and velocity legs; member-level legs (cohesion, breadth,
  turnover_z) are NULL before 2021-07-06 because massive_stock_day only
  reaches that far.  This is not a bug — it is the actual data boundary.
  Those legs are NULLABLE BY DESIGN and documented as such in the manifest.
* Tier M (268 subsectors + 40 themes from themes_tree.json + 46 thematic
  baskets from baskets.json): membership is CURRENT-ONLY for the
  themes/subsectors (the tree has a single commit as of 2026-07-04).  The
  survivorship bias is DECLARED in the manifest and must be printed on every
  UI surface that shows Tier-M numbers.  The baskets carry PIT membership
  (added dates per member) which is honored — but basket-level prices begin
  2023-05-09 (declared hindsight per the masterplan census).
* GICS sector labels come from the UNION of the current sp500/sp400/sp600
  constituent files (data/{breadth,midcap_breadth,smallcap_breadth}/
  constituents.parquet — 1,503 labeled names, 99.1% of ACTIVE PIT-spine
  tickers).  Two declared biases for the per-member breadth/cohesion legs:
  (a) labels-applied-backward — a reclassified company carries its *current*
  sector back in time; (b) label survivorship — names that left the index
  universe before the label snapshot have no label and are EXCLUDED from
  member legs (concentrated in the earliest panel years; a PIT sector-label
  map, e.g. from Polygon reference data, is the follow-up that closes this).
  Noted in the manifest under ``sector_label_caveat``.  Tier-S ETF-level
  legs are unaffected either way.
* All per-node-day columns are CAUSAL: rolling windows use only data ≤ t.
  The no-lookahead invariant is enforced by the test suite
  (tests/test_oracle_panel.py::test_no_lookahead).

PUBLIC API
----------
build_panel_s(closes_etf, closes_members, pit_membership, regime_df, cfg)
build_panel_m(closes_themes, closes_baskets, basket_membership, regime_df, cfg)

Both return a pd.DataFrame with MultiIndex (node, date) and a flat column
set described in COLUMN_SCHEMA below.  Missing member prices → NULL legs;
never raises on optional inputs (degrade-never-raise).

COLUMN SCHEMA (same for both tiers)
-------------------------------------
ret          — daily return of the node's equal-weight index
rs           — ret minus cross-node median ret (same day) = excess RS
vel_1w       — 1W rolling return ÷ 1.0  (weekly pace)
vel_1m       — 4W rolling return ÷ 4.345
vel_3m       — 13W rolling return ÷ 13.04
accel        — vel_1w − vel_3m
accel_z      — causal z-score of accel (252-day trailing window)
cohesion     — mean pairwise correlation of member daily rets, 40-day window
cohesion_chg — cohesion change over prior 20 trading days
breadth_50   — fraction of members above own 50-day moving average
persistence  — fraction of last 20 days with positive RS change
turnover_z   — causal z-score of node dollar-volume vs own 252-day history
vix_pctile   — VIX daily close causal percentile rank (2-year window)
tlt_ret_10d  — TLT 10-day return (regime leg; NULL if TLT absent)
spy_above_200d — 1 if SPY > 200-day SMA, else 0 (NULL if SPY absent)
stochrsi_w_k — weekly StochRSI %K (faithful confluence.py port), ffilled daily;
               row t carries the last COMPLETED weekly bar's value (no intraweek leak)
stochrsi_w_d — weekly StochRSI %D, same convention
washout_w    — 0/1/NaN: K<20 on ≥2 consecutive completed weekly bars within prior 3
               (P8 registered definition, frozen); forward-filled to daily
cohesion_rebuild — 0/1/NaN: FAITHFUL C4 (washout recent AND the most recent completed\n#                weekly bar printed a K-over-D upcross — the TURN BAR — AND
               cohesion_chg > 0.056, the panel_m q75); DISPLAY-ONLY per R4

MIRRORS / BORROWS
-----------------
vel_*  : WEEKS constant from engine.subsector_rotation
_causal_z, _mean_pairwise_corr : imported from engine.group_flow
         (house-tolerated private import — preferred over forking an
         identical copy, per the sibling-idiom rule in Fable doctrine)
weekly_stochrsi_kd, washout_active_series : engine.oracle.oscillators
         (single canonical implementation shared with oracle_gauntlet_p8.py)
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# Mirror the velocity denominator table from engine.subsector_rotation so the
# two surfaces stay in sync if WEEKS is ever updated.
from engine.subsector_rotation import WEEKS  # noqa: F401 — re-exported for callers
from engine.group_flow import _causal_z, _mean_pairwise_corr
from engine.oracle.oscillators import weekly_stochrsi_kd, washout_active_series, weekly_turn_series

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_BREADTH_MA_D = 50
_CORR_WINDOW_D = 40
_PERSIST_WINDOW_D = 20
_COHESION_CHG_D = 20   # lag for cohesion change
_Z_LOOKBACK_D = 252
_VIX_PCTILE_LOOKBACK_D = 504  # ~2y, mirror group_flow default
_TURNOVER_Z_LOOKBACK_D = 252

# C1 (WEEKLY LEGS ONLY — the daily-timeframe trigger leg is future work per the\n# library) / C4 compound columns
# washout_w lookback: number of DAILY sessions after a washout_w=1 bar during
# which cohesion_rebuild can still fire ("active-or-within-5-sessions").
# Source: C4 spec in research/ORACLE_COMPOUND_LIBRARY.md §Family C.
_WASHOUT_LINGER_D = 5

# cohesion_rebuild cohesion_chg threshold = panel_m q75 (measured 2026-07-04).
# Source: engine/oracle/episodes.py confirmed_cohesion_chg_threshold = 0.056
#         (q75 of panel_m cohesion_chg = 0.056, documented in ORACLE_EPISODE_ATLAS.md §manifests).
_COHESION_REBUILD_THRESHOLD: float = 0.056

# Weekly divisors: cumulative return over N calendar weeks → per-week pace
_VEL_WINDOWS: dict[str, tuple[int, float]] = {
    # key: (approx trading days, weekly-pace divisor)
    "vel_1w": (5, WEEKS["1W"]),
    "vel_1m": (21, WEEKS["1M"]),
    "vel_3m": (63, WEEKS["3M"]),
}

# Regime column source tickers (from data/yahoo/)
_VIX_TICKER = "_VIX"
_TLT_TICKER = "TLT"
_SPY_TICKER = "SPY"

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _pct_rank_causal(s: pd.Series, window: int) -> pd.Series:
    """Causal percentile rank of s in its own trailing window.

    Equivalent to pct_rank_window in engine.indicators but avoids the import
    to keep this module's dependency surface minimal.
    """
    def _rank_last(x: np.ndarray) -> float:
        v = x[-1]
        if np.isnan(v):
            return np.nan
        valid = x[~np.isnan(x)]
        if len(valid) < 2:
            return np.nan
        return float((valid < v).mean())

    return s.rolling(window, min_periods=window // 3).apply(_rank_last, raw=True)


def _build_ew_index(closes: pd.DataFrame) -> pd.Series:
    """Equal-weight return index from a DataFrame of price series.

    Handles missing prices gracefully: each day's return is the mean of
    available member returns (NaN members are excluded from the mean that
    day, not forward-filled).  Returns a price-level series starting at 1.0.
    """
    rets = closes.pct_change(fill_method=None)
    ew_ret = rets.mean(axis=1, skipna=True)
    return (1 + ew_ret).cumprod()


def _vel(lvl: pd.Series, days: int, divisor: float) -> pd.Series:
    """Rolling velocity: cumulative return over ``days`` trading days ÷ divisor."""
    # pct_change(days) gives (close[t] / close[t-days]) - 1, which is the
    # cumulative return over the window — causal by definition.
    return lvl.pct_change(days, fill_method=None) / divisor


def _build_cohesion_rebuild(
    washout_w: pd.Series,
    turn_w: pd.Series,
    cohesion_chg: pd.Series,
    linger_days: int,
    threshold: float,
    idx: pd.DatetimeIndex,
) -> pd.Series:
    """Compute C4 cohesion_rebuild boolean (stored as float 0/1/NaN).

    Definition (FAITHFUL C4, ORACLE_COMPOUND_LIBRARY.md §Family C — "washout
    + cohesion_chg > q75 ON THE TURN BAR"; review fix on #1280 which had
    shipped the looser washout-adjacent version without the turn):
        cohesion_rebuild = 1 if:
            (a) washout_w == 1 on this bar OR within the prior ``linger_days``
                daily sessions (washout active or recently expired), AND
            (t) turn_w == 1 — the most recent COMPLETED weekly bar printed a
                K-over-D upcross (the turn bar), AND
            (b) cohesion_chg > ``threshold`` (0.056 = panel_m q75).

    The "active-or-within-5-sessions" window is computed on the DAILY index so
    that the 5-session lookback is exact calendar-session count, not a fixed
    number of calendar days (weekend gaps would otherwise inflate the window).

    Returns float 0/1/NaN.  NaN only where BOTH washout_w AND cohesion_chg
    are NaN (i.e. before oscillator/cohesion warm-up).  If only one is NaN,
    the result is 0 (not NaN) because the AND-condition is definitively False.
    """
    wo_arr = washout_w.reindex(idx).to_numpy(dtype=float)
    tn_arr = turn_w.reindex(idx).to_numpy(dtype=float)
    cc_arr = cohesion_chg.reindex(idx).to_numpy(dtype=float)

    n = len(idx)
    result = np.full(n, np.nan)

    for i in range(n):
        wo_i = wo_arr[i]
        cc_i = cc_arr[i]

        # If cohesion_chg is NaN we cannot evaluate condition (b) → NaN
        if np.isnan(cc_i):
            continue  # leave NaN

        # Check washout active-or-within-linger_days
        # Look back over [i-linger_days, i] on the daily index
        start_linger = max(0, i - linger_days)
        wo_window = wo_arr[start_linger: i + 1]
        # If all washout values in the window are NaN → oscillator not yet warm;
        # cannot definitively determine washout condition → NaN
        non_nan_in_window = wo_window[~np.isnan(wo_window)]
        if len(non_nan_in_window) == 0:
            # No washout information yet — leave NaN only if cohesion_chg
            # is also not useful yet (both warm-up periods need time)
            continue  # leave NaN

        washout_condition = bool(np.any(non_nan_in_window == 1.0))
        cohesion_condition = bool(cc_i > threshold)
        # (t) the turn bar: NaN turn (warm-up) → condition undetermined; only a
        # definitive 1.0 satisfies it (a leaky default-true would fabricate C4s)
        turn_condition = bool(not np.isnan(tn_arr[i]) and tn_arr[i] == 1.0)

        result[i] = 1.0 if (washout_condition and turn_condition and cohesion_condition) else 0.0

    return pd.Series(result, index=idx, dtype=float, name="cohesion_rebuild")


def _build_node_features(
    lvl: pd.Series,
    bench: pd.Series,
    member_closes: pd.DataFrame | None,
    member_volume: pd.DataFrame | None,
    node_volume: pd.Series | None,
) -> pd.DataFrame:
    """Compute all feature columns for a single node.

    Parameters
    ----------
    lvl           : equal-weight price level of the node (e.g. ETF close or EW index)
    bench         : cross-node benchmark series (median of all node rets, same index)
    member_closes : daily closes of constituent members (may be None or empty)
    member_volume : daily volume of constituent members (may be None or empty)
    node_volume   : total dollar-volume of the node level (may be None)

    Returns a DataFrame indexed by date with columns per COLUMN_SCHEMA.
    Degrades gracefully: member-derived legs are NULL when member data absent.
    """
    idx = lvl.index

    # ---- return and RS ----
    ret = lvl.pct_change(fill_method=None)
    bench_ret = bench.reindex(idx)
    rs = ret - bench_ret

    # ---- velocity ----
    vel_1w = _vel(lvl, _VEL_WINDOWS["vel_1w"][0], _VEL_WINDOWS["vel_1w"][1])
    vel_1m = _vel(lvl, _VEL_WINDOWS["vel_1m"][0], _VEL_WINDOWS["vel_1m"][1])
    vel_3m = _vel(lvl, _VEL_WINDOWS["vel_3m"][0], _VEL_WINDOWS["vel_3m"][1])

    # ---- acceleration ----
    accel = vel_1w - vel_3m
    accel_z = _causal_z(accel, _Z_LOOKBACK_D)

    # ---- persistence (fraction of last 20d with positive RS change) ----
    rs_chg = rs.diff()
    persistence = (
        rs_chg.rolling(_PERSIST_WINDOW_D, min_periods=_PERSIST_WINDOW_D // 2)
        .apply(lambda x: float((x > 0).mean()), raw=True)
    )

    # ---- member-derived legs (NULL when members absent or pre-coverage) ----
    cohesion = pd.Series(np.nan, index=idx, dtype=float)
    cohesion_chg = pd.Series(np.nan, index=idx, dtype=float)
    breadth_50 = pd.Series(np.nan, index=idx, dtype=float)
    turnover_z = pd.Series(np.nan, index=idx, dtype=float)

    has_members = (
        member_closes is not None
        and not member_closes.empty
        and member_closes.shape[1] >= 3
    )

    if has_members:
        mc = member_closes.reindex(idx)
        # breadth_50: fraction of members above own 50-day MA
        ma50 = mc.rolling(_BREADTH_MA_D, min_periods=_BREADTH_MA_D // 2).mean()
        above = (mc > ma50).where(mc.notna() & ma50.notna())
        breadth_50 = above.mean(axis=1)

        # cohesion: mean pairwise corr using the rolling engine from group_flow
        # Compute day-by-day using a rolling window of length _CORR_WINDOW_D.
        # _mean_pairwise_corr is designed for a window DataFrame → we wrap it.
        member_rets = mc.pct_change(fill_method=None)
        cw = _CORR_WINDOW_D
        rw = _COHESION_CHG_D

        coh_vals: list[float | None] = []
        for i in range(len(idx)):
            if i < cw - 1:
                coh_vals.append(None)
            else:
                window_data = member_rets.iloc[i - cw + 1: i + 1]
                coh_vals.append(_mean_pairwise_corr(window_data))

        cohesion = pd.Series(
            [v if v is not None else np.nan for v in coh_vals],
            index=idx, dtype=float,
        )

        # cohesion_chg: 20-day change in cohesion (only valid once the prior
        # window is also a full cw-bar window, mirror group_flow comment)
        coh_chg_vals: list[float | None] = []
        for i in range(len(idx)):
            if i < cw + rw - 1:
                coh_chg_vals.append(None)
            else:
                curr = coh_vals[i]
                prev = coh_vals[i - rw]
                if curr is not None and prev is not None:
                    coh_chg_vals.append(curr - prev)
                else:
                    coh_chg_vals.append(None)

        cohesion_chg = pd.Series(
            [v if v is not None else np.nan for v in coh_chg_vals],
            index=idx, dtype=float,
        )

        # turnover_z from member volume
        if member_volume is not None and not member_volume.empty:
            mv = member_volume.reindex(idx).fillna(0)
            mc_aligned = mc.reindex(idx)
            # dollar volume: price × volume, summed across members
            dv = (mc_aligned * mv).sum(axis=1)
            turnover_z = _causal_z(dv, _TURNOVER_Z_LOOKBACK_D)

    # ETF-level (node) volume: computed whether or not member data is present.
    # This handles Tier-S ETF nodes where the single-ticker ETF volume is passed.
    if turnover_z.isna().all() and node_volume is not None:
        dv = lvl * node_volume.reindex(idx).fillna(0)
        turnover_z = _causal_z(dv, _TURNOVER_Z_LOOKBACK_D)

    # ---- C1/C4 weekly StochRSI columns ----
    # Computed on ``lvl`` (the node's equal-weight price level), resampled to
    # W-FRI weekly bars, then forward-filled onto the daily index so that row t
    # carries only the last COMPLETED weekly bar's value.
    # The in-progress (current) week bar must never contribute — that is the
    # failure mode the no-lookahead test guards against (see tests/test_oracle_panel.py).
    # Nullable: all-NaN when fewer than _MIN_WEEKLY_BARS (40) weekly bars available.
    stochrsi_w_k, stochrsi_w_d = weekly_stochrsi_kd(lvl)
    washout_w = washout_active_series(lvl)
    turn_w = weekly_turn_series(lvl)

    # ---- C4 cohesion_rebuild ----
    # Boolean (stored as float 0/1/NaN): washout_w active-or-within-5 daily sessions
    # AND cohesion_chg > 0.056 (panel_m q75 threshold, source: engine/oracle/episodes.py
    # confirmed_cohesion_chg_threshold = 0.056).
    # Nullable: NaN where either washout_w or cohesion_chg is NaN.
    cohesion_rebuild = _build_cohesion_rebuild(
        washout_w=washout_w,
        turn_w=turn_w,
        cohesion_chg=cohesion_chg,
        linger_days=_WASHOUT_LINGER_D,
        threshold=_COHESION_REBUILD_THRESHOLD,
        idx=idx,
    )

    return pd.DataFrame(
        {
            "ret": ret,
            "rs": rs,
            "vel_1w": vel_1w,
            "vel_1m": vel_1m,
            "vel_3m": vel_3m,
            "accel": accel,
            "accel_z": accel_z,
            "cohesion": cohesion,
            "cohesion_chg": cohesion_chg,
            "breadth_50": breadth_50,
            "persistence": persistence,
            "turnover_z": turnover_z,
            "stochrsi_w_k": stochrsi_w_k,
            "stochrsi_w_d": stochrsi_w_d,
            "washout_w": washout_w,
            "cohesion_rebuild": cohesion_rebuild,
        },
        index=idx,
    )


def _build_regime(
    yahoo_dir: Path | None,
    index: pd.DatetimeIndex,
) -> pd.DataFrame:
    """Load VIX, TLT, SPY from yahoo/ and FRED macros; build regime columns.

    Degrades to NaN columns when files are absent (offline / CI).

    FRED release-lag guard
    ----------------------
    FRED series are not available in real time: daily series typically publish
    1 business day after their reference date; NFCI (weekly) is released every
    Wednesday for the prior week.  To guarantee strict causal ordering, every
    FRED series is reindexed to the panel's trading-day spine, forward-filled
    to carry the last known value, and then shifted by ONE ROW (shift(1)) so
    that a panel row for date t uses only values that were known by t−1.
    All transforms (diff, pct_change, level) are applied AFTER the shift.
    """
    vix_pctile = pd.Series(np.nan, index=index, dtype=float, name="vix_pctile")
    tlt_ret_10d = pd.Series(np.nan, index=index, dtype=float, name="tlt_ret_10d")
    spy_above_200d = pd.Series(np.nan, index=index, dtype=float, name="spy_above_200d")

    # FRED-sourced columns — initialised to NaN; populated below if files exist.
    hy_oas_chg_10d = pd.Series(np.nan, index=index, dtype=float, name="hy_oas_chg_10d")
    yc_slope = pd.Series(np.nan, index=index, dtype=float, name="yc_slope")
    oil_ret_10d = pd.Series(np.nan, index=index, dtype=float, name="oil_ret_10d")
    dollar_chg_10d = pd.Series(np.nan, index=index, dtype=float, name="dollar_chg_10d")
    fin_conditions = pd.Series(np.nan, index=index, dtype=float, name="fin_conditions")

    if yahoo_dir is None or not yahoo_dir.exists():
        return pd.DataFrame({
            "vix_pctile": vix_pctile,
            "tlt_ret_10d": tlt_ret_10d,
            "spy_above_200d": spy_above_200d,
            "hy_oas_chg_10d": hy_oas_chg_10d,
            "yc_slope": yc_slope,
            "oil_ret_10d": oil_ret_10d,
            "dollar_chg_10d": dollar_chg_10d,
            "fin_conditions": fin_conditions,
        })

    # VIX
    vix_path = yahoo_dir / f"{_VIX_TICKER}.parquet"
    if vix_path.exists():
        try:
            vix = pd.read_parquet(vix_path)["close"].rename("vix")
            vix = vix.reindex(index)
            vix_pctile = _pct_rank_causal(vix, _VIX_PCTILE_LOOKBACK_D)
        except Exception:  # noqa: BLE001
            log.warning("VIX load failed — vix_pctile set to NaN")

    # TLT
    tlt_path = yahoo_dir / f"{_TLT_TICKER}.parquet"
    if tlt_path.exists():
        try:
            tlt = pd.read_parquet(tlt_path)["close"].rename("tlt")
            tlt = tlt.reindex(index)
            tlt_ret_10d = tlt.pct_change(10, fill_method=None)
        except Exception:  # noqa: BLE001
            log.warning("TLT load failed — tlt_ret_10d set to NaN")

    # SPY
    spy_path = yahoo_dir / f"{_SPY_TICKER}.parquet"
    if spy_path.exists():
        try:
            spy = pd.read_parquet(spy_path)["close"].rename("spy")
            spy = spy.reindex(index)
            sma200 = spy.rolling(200, min_periods=100).mean()
            spy_above_200d = (spy > sma200).astype(float).where(spy.notna() & sma200.notna())
        except Exception:  # noqa: BLE001
            log.warning("SPY load failed — spy_above_200d set to NaN")

    # ---- FRED macro regime columns ----
    # Derive fred_dir from yahoo_dir (data/yahoo → data/fred).
    fred_dir = yahoo_dir.parent / "fred"

    def _load_fred(filename: str) -> pd.Series | None:
        """Load a FRED parquet robustly; return None on any failure."""
        p = fred_dir / filename
        if not p.exists():
            return None
        try:
            df = pd.read_parquet(p)
            # Prefer 'value' column (canonical FRED download); fall back to first col.
            s = df["value"] if "value" in df.columns else df.iloc[:, 0]
            if not isinstance(s.index, pd.DatetimeIndex):
                s.index = pd.to_datetime(s.index)
            return s
        except Exception:  # noqa: BLE001
            return None

    # 1. HY OAS — BAMLH0A0HYM2 (ICE BofA US HY spread, %pts)
    #    Rising = credit stress / risk-off.
    #    Transform: 10-trading-day change of the shifted (causal) series.
    s_hy = _load_fred("BAMLH0A0HYM2.parquet")
    if s_hy is not None:
        try:
            # shift(1): row t uses FRED value last published ≤ t−1 (release-lag guard).
            s_causal = s_hy.reindex(index).ffill().shift(1)
            hy_oas_chg_10d = s_causal.diff(10).rename("hy_oas_chg_10d")
        except Exception:  # noqa: BLE001
            log.warning("BAMLH0A0HYM2 compute failed — hy_oas_chg_10d set to NaN")

    # 2. Yield-curve slope — T10Y2Y (10y minus 2y Treasury, %pts)
    #    Already stationary as a spread; use raw level.
    #    Negative = inverted curve.
    s_yc = _load_fred("T10Y2Y.parquet")
    if s_yc is not None:
        try:
            # shift(1): release-lag guard.
            yc_slope = s_yc.reindex(index).ffill().shift(1).rename("yc_slope")
        except Exception:  # noqa: BLE001
            log.warning("T10Y2Y compute failed — yc_slope set to NaN")

    # 3. WTI crude oil — DCOILWTICO (USD/bbl)
    #    Transform: 10-trading-day percent change of the shifted (causal) series.
    s_oil = _load_fred("DCOILWTICO.parquet")
    if s_oil is not None:
        try:
            # shift(1): release-lag guard.
            s_causal = s_oil.reindex(index).ffill().shift(1)
            oil_ret_10d = s_causal.pct_change(10, fill_method=None).rename("oil_ret_10d")
        except Exception:  # noqa: BLE001
            log.warning("DCOILWTICO compute failed — oil_ret_10d set to NaN")

    # 4. Broad USD — DTWEXBGS (Federal Reserve broad dollar index)
    #    Transform: 10-trading-day percent change of the shifted (causal) series.
    s_usd = _load_fred("DTWEXBGS.parquet")
    if s_usd is not None:
        try:
            # shift(1): release-lag guard.
            s_causal = s_usd.reindex(index).ffill().shift(1)
            dollar_chg_10d = s_causal.pct_change(10, fill_method=None).rename("dollar_chg_10d")
        except Exception:  # noqa: BLE001
            log.warning("DTWEXBGS compute failed — dollar_chg_10d set to NaN")

    # 5. NFCI — National Financial Conditions Index (weekly, released Wed for prior week)
    #    Positive = tight financial conditions; negative = loose.
    #    Use raw level; NFCI is stationary by construction.
    s_nfci = _load_fred("NFCI.parquet")
    if s_nfci is not None:
        try:
            # shift(1): release-lag guard (especially important for weekly NFCI
            # which is released midweek for the prior week — ffill propagates
            # the reading across non-release days, shift ensures we never use
            # a reading on the same day it was published).
            fin_conditions = s_nfci.reindex(index).ffill().shift(1).rename("fin_conditions")
        except Exception:  # noqa: BLE001
            log.warning("NFCI compute failed — fin_conditions set to NaN")

    return pd.DataFrame({
        "vix_pctile": vix_pctile,
        "tlt_ret_10d": tlt_ret_10d,
        "spy_above_200d": spy_above_200d,
        "hy_oas_chg_10d": hy_oas_chg_10d,
        "yc_slope": yc_slope,
        "oil_ret_10d": oil_ret_10d,
        "dollar_chg_10d": dollar_chg_10d,
        "fin_conditions": fin_conditions,
    })


# ---------------------------------------------------------------------------
# Tier S — Survivorship-clean spine
# ---------------------------------------------------------------------------

#: The 11 GICS-sector ETFs that constitute the Tier-S node universe.
#: Probed schema: data/yahoo/<T>.parquet → close (div-adjusted), volume, close_price
SECTOR_ETFS: list[str] = [
    "XLK",   # Information Technology
    "XLV",   # Health Care
    "XLF",   # Financials
    "XLY",   # Consumer Discretionary
    "XLC",   # Communication Services
    "XLI",   # Industrials
    "XLP",   # Consumer Staples
    "XLE",   # Energy
    "XLU",   # Utilities
    "XLRE",  # Real Estate
    "XLB",   # Materials
]

#: ETF → GICS sector name (for joining PIT membership to the right node).
ETF_TO_SECTOR: dict[str, str] = {
    "XLK": "Information Technology",
    "XLV": "Health Care",
    "XLF": "Financials",
    "XLY": "Consumer Discretionary",
    "XLC": "Communication Services",
    "XLI": "Industrials",
    "XLP": "Consumer Staples",
    "XLE": "Energy",
    "XLU": "Utilities",
    "XLRE": "Real Estate",
    "XLB": "Materials",
}


def pit_union_mask(
    intervals: list[tuple[pd.Timestamp, pd.Timestamp]],
    index: pd.DatetimeIndex,
) -> pd.Series:
    """True on days inside ANY of a ticker's membership intervals.

    NaT end_date = still active.  A ticker that was added, dropped, and
    re-added must be live in BOTH active windows and masked in the gap —
    honoring only the first stored interval mismasks 559 of the 2,589
    PIT-spine tickers (the review-flagged iloc[0] bug)."""
    mask = pd.Series(False, index=index)
    for start_d, end_d in intervals:
        m = pd.Series(True, index=index)
        if pd.notna(start_d):
            m &= index >= start_d
        if pd.notna(end_d):
            m &= index <= end_d
        mask |= m
    return mask


def build_panel_s(
    *,
    yahoo_dir: Path,
    massive_dir: Path,
    pit_membership: pd.DataFrame,
    constituents: pd.DataFrame,
    start: str | None = None,
    end: str | None = None,
    limit_tickers: int | None = None,
    cfg: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Build Tier-S (survivorship-clean spine) rotation panel.

    Parameters
    ----------
    yahoo_dir       : path to data/yahoo/ (ETF closes + regime tickers)
    massive_dir     : path to data/massive_stock_day/ (member closes/volume)
    pit_membership  : DataFrame from data/breadth/sp1500_pit_membership.parquet
                      columns: ticker, start_date, end_date, src
    constituents    : DataFrame from data/breadth/constituents.parquet
                      index=symbol, columns: name, sector
                      — used to map ticker → GICS sector (current labels
                      applied backward: mild bias per docstring)
    start           : ISO date string, default 1998-12-22 (earliest ETF data)
    end             : ISO date string, default latest available
    limit_tickers   : if set, restrict member ticker load to this many tickers
                      per sector (smoke-run flag for --limit CLI option)
    cfg             : override dict (unused; reserved for future tuning params)

    Returns
    -------
    pd.DataFrame with MultiIndex (node, date) where node = ETF ticker.
    Columns per COLUMN_SCHEMA.  Member-derived legs (cohesion, breadth_50,
    turnover_z) are NULL before massive_store coverage (pre-2021-07).
    """
    cfg = cfg or {}

    # ---- Load ETF closes ----
    etf_closes: dict[str, pd.Series] = {}
    etf_volumes: dict[str, pd.Series] = {}
    for ticker in SECTOR_ETFS:
        p = yahoo_dir / f"{ticker}.parquet"
        if not p.exists():
            log.warning("ETF parquet missing: %s — skipping node", ticker)
            continue
        df = pd.read_parquet(p)
        etf_closes[ticker] = df["close"]
        if "volume" in df.columns:
            etf_volumes[ticker] = df["volume"]

    if not etf_closes:
        raise FileNotFoundError(f"No ETF parquets found in {yahoo_dir}")

    # Build a unified DatetimeIndex spanning all available ETF dates
    all_dates = sorted(
        set().union(*[s.index for s in etf_closes.values()])
    )
    full_idx = pd.DatetimeIndex(all_dates, name="date")

    # Apply date filters
    if start:
        full_idx = full_idx[full_idx >= pd.Timestamp(start)]
    if end:
        full_idx = full_idx[full_idx <= pd.Timestamp(end)]

    # Align all ETF price series to the common index
    etf_aligned: dict[str, pd.Series] = {
        t: s.reindex(full_idx) for t, s in etf_closes.items()
    }

    # Cross-node benchmark: median of all ETF daily returns
    etf_rets = pd.DataFrame({t: s.pct_change(fill_method=None) for t, s in etf_aligned.items()})
    bench_ret = etf_rets.median(axis=1)

    # ---- Build ticker→sector map from constituents ----
    # constituents = the UNION of the current sp500/sp400/sp600 constituent
    # files (index=symbol, column 'sector'). Coverage measured 2026-07-04:
    # 99.1% of ACTIVE PIT-spine tickers labeled (1,493/1,506). Names that left
    # the index universe before the label snapshot carry no label and are
    # therefore EXCLUDED from member legs — a label-survivorship bias
    # concentrated in the earliest panel years, declared in the manifest.
    # ETF-level columns (ret/rs/vel/accel) are unaffected and fully clean.
    ticker_sector: dict[str, str] = {}
    if "sector" in constituents.columns:
        ticker_sector = constituents["sector"].to_dict()

    # ---- PIT membership intervals per ticker ----
    # A ticker can enter/leave the index universe multiple times (add, drop,
    # re-add), so masking must take the UNION of ALL its intervals — using only
    # the first stored row mismasks every multi-interval name (559 of 2,589
    # spine tickers have >1 interval).  end_date NaT = still active.
    pit_intervals: dict[str, list[tuple[pd.Timestamp, pd.Timestamp]]] = {}
    for _, row in pit_membership.iterrows():
        pit_intervals.setdefault(row["ticker"], []).append(
            (row["start_date"], row["end_date"]))

    # Pre-compute the full set of tickers ever in each sector (for price loading)
    sector_all_tickers: dict[str, set[str]] = {s: set() for s in ETF_TO_SECTOR.values()}
    for t in pit_intervals:
        sec = ticker_sector.get(t)
        if sec and sec in sector_all_tickers:
            sector_all_tickers[sec].add(t)

    # ---- Load member prices from massive_stock_day ----
    member_closes_store: dict[str, pd.Series] = {}
    member_volume_store: dict[str, pd.Series] = {}

    all_member_tickers: set[str] = set()
    for sec in sector_all_tickers.values():
        all_member_tickers |= sec

    if limit_tickers is not None:
        # For smoke runs: cap tickers per sector
        limited: set[str] = set()
        for sec, tickers in sector_all_tickers.items():
            limited |= set(list(tickers)[:limit_tickers])
        all_member_tickers = limited

    for ticker in all_member_tickers:
        p = massive_dir / f"{ticker}.parquet"
        if not p.exists():
            continue
        try:
            df = pd.read_parquet(p)
            member_closes_store[ticker] = df["close"]
            if "volume" in df.columns:
                member_volume_store[ticker] = df["volume"]
        except Exception:  # noqa: BLE001
            log.debug("Failed to load member %s — skipped", ticker)

    # ---- Build regime columns ----
    regime = _build_regime(yahoo_dir, full_idx)

    # ---- Assemble per-node features ----
    node_dfs: list[pd.DataFrame] = []

    for ticker, lvl_raw in etf_aligned.items():
        lvl = lvl_raw.dropna()
        if lvl.empty:
            continue

        node_idx = full_idx[full_idx.isin(lvl.index)]
        bench = bench_ret.reindex(node_idx)
        sector = ETF_TO_SECTOR.get(ticker, "")

        # Build member closes matrix for this sector over node_idx
        # PIT-filtered: include only members active on each date
        sector_tickers = sector_all_tickers.get(sector, set())
        if limit_tickers is not None:
            sector_tickers = set(list(sector_tickers)[:limit_tickers])

        # Collect price series that exist in the store
        avail_tickers = [t for t in sector_tickers if t in member_closes_store]

        mc_dict: dict[str, pd.Series] = {}
        mv_dict: dict[str, pd.Series] = {}
        for t in avail_tickers:
            mc_dict[t] = member_closes_store[t].reindex(node_idx)
            if t in member_volume_store:
                mv_dict[t] = member_volume_store[t].reindex(node_idx)

        # Apply PIT filter: a member's prices count only on days inside the
        # UNION of its membership intervals (multi-interval names: add → drop
        # → re-add must be masked in the gap and live in BOTH active windows).
        for t in list(mc_dict.keys()):
            intervals = pit_intervals.get(t)
            if not intervals:
                continue
            mask = pit_union_mask(intervals, node_idx)
            mc_dict[t] = mc_dict[t].where(mask)
            if t in mv_dict:
                mv_dict[t] = mv_dict[t].where(mask)

        member_closes = (
            pd.DataFrame(mc_dict, index=node_idx) if mc_dict else None
        )
        member_volume = (
            pd.DataFrame(mv_dict, index=node_idx) if mv_dict else None
        )

        node_vol = etf_volumes.get(ticker)
        if node_vol is not None:
            node_vol = node_vol.reindex(node_idx)

        feats = _build_node_features(
            lvl=lvl_raw.reindex(node_idx),
            bench=bench,
            member_closes=member_closes,
            member_volume=member_volume,
            node_volume=node_vol,
        )

        # Join regime
        feats = feats.join(regime.reindex(node_idx), how="left")
        feats.index.name = "date"
        feats["node"] = ticker
        node_dfs.append(feats.reset_index().set_index(["node", "date"]))

    if not node_dfs:
        return pd.DataFrame()

    panel = pd.concat(node_dfs)
    panel.sort_index(inplace=True)
    return panel


# ---------------------------------------------------------------------------
# Tier M — Survivorship-flagged microscope
# ---------------------------------------------------------------------------


def _load_themes_nodes(
    themes_tree: list[dict],
    massive_dir: Path,
    start: str | None,
    end: str | None,
    limit_tickers: int | None,
) -> tuple[dict[str, list[str]], dict[str, pd.Series], dict[str, pd.Series]]:
    """Extract subsector + theme nodes from themes_tree.json.

    Returns
    -------
    node_members : dict node_key → list[ticker]
    closes_store : dict ticker → pd.Series
    volume_store : dict ticker → pd.Series
    """
    node_members: dict[str, list[str]] = {}

    # Subsectors: key = subsector key (e.g. "aicompute")
    # Themes: key = theme name (e.g. "Artificial Intelligence")
    theme_members_agg: dict[str, set[str]] = {}

    for theme_item in themes_tree:
        theme_name = theme_item["theme"]
        theme_tickers: set[str] = set()
        for sub in theme_item.get("subsectors", []):
            sub_key = sub["key"]
            members = sub.get("members", [])
            node_members[sub_key] = members
            theme_tickers.update(members)
        # Theme node = union of all subsector members (equal-weight)
        theme_members_agg[theme_name] = theme_tickers

    for theme_name, tickers in theme_members_agg.items():
        node_members[theme_name] = list(tickers)

    # Load prices
    all_tickers: set[str] = set()
    for tickers in node_members.values():
        all_tickers.update(tickers)

    if limit_tickers is not None:
        all_tickers = set(list(all_tickers)[:limit_tickers])

    closes_store: dict[str, pd.Series] = {}
    volume_store: dict[str, pd.Series] = {}

    for ticker in all_tickers:
        p = massive_dir / f"{ticker}.parquet"
        if not p.exists():
            continue
        try:
            df = pd.read_parquet(p)
            closes_store[ticker] = df["close"]
            if "volume" in df.columns:
                volume_store[ticker] = df["volume"]
        except Exception:  # noqa: BLE001
            log.debug("Failed to load %s for Tier M — skipped", ticker)

    return node_members, closes_store, volume_store


def _load_basket_nodes(
    baskets_data: list[dict],
    massive_dir: Path,
    start: str | None,
    end: str | None,
    limit_tickers: int | None,
) -> tuple[dict[str, list[dict]], dict[str, pd.Series], dict[str, pd.Series]]:
    """Extract basket nodes with PIT membership from baskets.json.

    Returns
    -------
    basket_members : dict basket_id → list[{symbol, added, ...}]
    closes_store   : dict ticker → pd.Series
    volume_store   : dict ticker → pd.Series
    """
    basket_members: dict[str, list[dict]] = {}
    all_tickers: set[str] = set()

    for b in baskets_data:
        bid = b.get("id", b.get("name", ""))
        if not bid:
            continue
        members = b.get("members", [])
        basket_members[bid] = members
        for m in members:
            if isinstance(m, dict):
                all_tickers.add(m["symbol"])

    if limit_tickers is not None:
        all_tickers = set(list(all_tickers)[:limit_tickers])

    closes_store: dict[str, pd.Series] = {}
    volume_store: dict[str, pd.Series] = {}

    for ticker in all_tickers:
        p = massive_dir / f"{ticker}.parquet"
        if not p.exists():
            continue
        try:
            df = pd.read_parquet(p)
            closes_store[ticker] = df["close"]
            if "volume" in df.columns:
                volume_store[ticker] = df["volume"]
        except Exception:  # noqa: BLE001
            log.debug("Failed to load basket member %s — skipped", ticker)

    return basket_members, closes_store, volume_store


def _build_basket_ew_index(
    members: list[dict],
    closes_store: dict[str, pd.Series],
    full_idx: pd.DatetimeIndex,
) -> pd.Series:
    """EW index for a basket honoring PIT added-date per member.

    Each member contributes only from its ``added`` date forward.  Returns
    a price-level series starting at 1.0 on the first day any member has
    a price.
    """
    frame: dict[str, pd.Series] = {}
    for m in members:
        if not isinstance(m, dict):
            continue
        sym = m["symbol"]
        if sym not in closes_store:
            continue
        s = closes_store[sym].reindex(full_idx)
        # Mask prices before added date (PIT filter)
        added_str = m.get("added")
        if added_str:
            try:
                added_dt = pd.Timestamp(added_str)
                s = s.where(full_idx >= added_dt)
            except Exception:  # noqa: BLE001
                pass
        frame[sym] = s

    if not frame:
        return pd.Series(dtype=float, index=full_idx)

    df = pd.DataFrame(frame, index=full_idx)
    return _build_ew_index(df)


FACTOR_ETFS: list[str] = ["IWF", "IWD", "MTUM", "QUAL", "USMV", "IWM"]


def build_panel_f(
    *,
    yahoo_dir: Path,
    start: str | None = "2013-04-16",
    end: str | None = None,
    cfg: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Build Tier-F (style-factor ETFs) rotation panel — SPY-excess.

    Nodes: IWF(Growth) IWD(Value) MTUM(Momentum) QUAL(Quality) USMV(LowVol) IWM(Size).
    rs = node ret - SPY ret (market excess), NOT peer-median (median-of-6 has no
    clean referent + is zero-sum). ETF-only: cohesion/cohesion_chg/breadth_50 are
    NULL by design (no member panels); turnover_z still derives from ETF volume.
    History from ~2013. Survivorship-clean (Tier-S semantics).

    HONEST-NULL PRIOR (see episodes.py): daily cross-sectional rotation rank-IC of
    this family tested as noise. Tier-F is a DISPLAY/CONTEXT layer — descriptive
    replay, never a validated edge, never a sizing input.
    """
    cfg = cfg or {}
    etf_closes: dict[str, pd.Series] = {}
    etf_volumes: dict[str, pd.Series] = {}
    for ticker in FACTOR_ETFS:
        p = yahoo_dir / f"{ticker}.parquet"
        if not p.exists():
            log.warning("factor ETF parquet missing: %s - skipping node", ticker)
            continue
        df = pd.read_parquet(p)
        etf_closes[ticker] = df["close"]
        if "volume" in df.columns:
            etf_volumes[ticker] = df["volume"]
    if not etf_closes:
        raise FileNotFoundError(f"No factor ETF parquets found in {yahoo_dir}")

    all_dates = sorted(set().union(*[s.index for s in etf_closes.values()]))
    full_idx = pd.DatetimeIndex(all_dates, name="date")
    if start:
        full_idx = full_idx[full_idx >= pd.Timestamp(start)]
    if end:
        full_idx = full_idx[full_idx <= pd.Timestamp(end)]
    etf_aligned = {t: s.reindex(full_idx) for t, s in etf_closes.items()}

    spy_path = yahoo_dir / "SPY.parquet"
    if not spy_path.exists():
        raise FileNotFoundError(f"SPY parquet required for Tier-F benchmark: {spy_path}")
    spy_close = pd.read_parquet(spy_path)["close"]
    bench_ret = spy_close.pct_change(fill_method=None).reindex(full_idx)

    regime = _build_regime(yahoo_dir, full_idx)

    node_dfs: list[pd.DataFrame] = []
    for ticker, lvl_raw in etf_aligned.items():
        lvl = lvl_raw.dropna()
        if lvl.empty:
            continue
        node_idx = full_idx[full_idx.isin(lvl.index)]
        bench = bench_ret.reindex(node_idx)
        node_vol = etf_volumes.get(ticker)
        if node_vol is not None:
            node_vol = node_vol.reindex(node_idx)
        feats = _build_node_features(
            lvl=lvl_raw.reindex(node_idx),
            bench=bench,
            member_closes=None,
            member_volume=None,
            node_volume=node_vol,
        )
        feats = feats.join(regime.reindex(node_idx), how="left")
        feats.index.name = "date"
        feats["node"] = ticker
        node_dfs.append(feats.reset_index().set_index(["node", "date"]))
    if not node_dfs:
        return pd.DataFrame()
    panel = pd.concat(node_dfs)
    panel.sort_index(inplace=True)
    return panel


def build_panel_m(
    *,
    yahoo_dir: Path,
    massive_dir: Path,
    themes_tree: list[dict],
    baskets_data: list[dict],
    start: str | None = None,
    end: str | None = None,
    limit_tickers: int | None = None,
    cfg: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Build Tier-M (survivorship-flagged microscope) rotation panel.

    Nodes = 268 subsectors + 40 themes (from themes_tree.json, equal-weight
    member indices) + up to 46 thematic baskets (from baskets.json, honouring
    PIT added dates per member).

    SURVIVORSHIP WARNING: the themes_tree.json carries no membership history
    — the member lists reflect 2026-06 composition.  Any backtest or pattern
    claim on Tier-M nodes is DECLARED HINDSIGHT and must carry the watermark
    ``survivorship_flagged=True`` in the manifest.  Only Tier-S numbers earn
    the "clean" label.

    Parameters
    ----------
    yahoo_dir    : path to data/yahoo/ (regime series)
    massive_dir  : path to data/massive_stock_day/
    themes_tree  : parsed list from data/themes_heatmap/themes_tree.json
    baskets_data : parsed list from site/basketdata/baskets.json → baskets key
    start        : ISO date string, default 2021-07-06 (earliest massive store)
    end          : ISO date string
    limit_tickers: cap member price loads (smoke-run flag)

    Returns
    -------
    pd.DataFrame with MultiIndex (node, date).
    """
    cfg = cfg or {}
    start = start or "2021-07-06"

    # ---- Load themes + subsector nodes ----
    theme_members, theme_closes, theme_volumes = _load_themes_nodes(
        themes_tree, massive_dir, start, end, limit_tickers
    )

    # ---- Load basket nodes ----
    basket_members, basket_closes, basket_volumes = _load_basket_nodes(
        baskets_data, massive_dir, start, end, limit_tickers
    )

    # Merge close stores
    all_closes: dict[str, pd.Series] = {**theme_closes, **basket_closes}
    all_volumes: dict[str, pd.Series] = {**theme_volumes, **basket_volumes}

    if not all_closes:
        log.warning("No member prices found for Tier M — returning empty panel")
        return pd.DataFrame()

    # Build unified DatetimeIndex
    all_dates = sorted(set().union(*[s.index for s in all_closes.values()]))
    full_idx = pd.DatetimeIndex(all_dates, name="date")
    if start:
        full_idx = full_idx[full_idx >= pd.Timestamp(start)]
    if end:
        full_idx = full_idx[full_idx <= pd.Timestamp(end)]

    if full_idx.empty:
        return pd.DataFrame()

    # ---- Build EW level series for each node ----
    node_levels: dict[str, pd.Series] = {}

    # Subsector + theme nodes
    for node_key, tickers in theme_members.items():
        mc_dict = {t: all_closes[t] for t in tickers if t in all_closes}
        if not mc_dict:
            continue
        mc = pd.DataFrame(mc_dict, index=full_idx)
        # Reindex each series to full_idx
        mc = pd.DataFrame({t: s.reindex(full_idx) for t, s in mc_dict.items()})
        node_levels[node_key] = _build_ew_index(mc)

    # Basket nodes (PIT-aware)
    for bid, members in basket_members.items():
        lvl = _build_basket_ew_index(members, all_closes, full_idx)
        if lvl.dropna().shape[0] >= 5:
            node_levels[bid] = lvl

    if not node_levels:
        return pd.DataFrame()

    # Cross-node benchmark: median of all node returns
    node_rets = pd.DataFrame({
        k: lvl.pct_change(fill_method=None) for k, lvl in node_levels.items()
    })
    bench_ret = node_rets.median(axis=1)

    # ---- Build regime columns ----
    regime = _build_regime(yahoo_dir, full_idx)

    # ---- Assemble per-node features ----
    node_dfs: list[pd.DataFrame] = []

    for node_key, lvl in node_levels.items():
        # Member closes for this node
        if node_key in basket_members:
            # Basket: PIT-aware member set
            members_list = basket_members[node_key]
            mc_dict = {}
            mv_dict = {}
            for m in members_list:
                if not isinstance(m, dict):
                    continue
                sym = m["symbol"]
                if sym not in all_closes:
                    continue
                s = all_closes[sym].reindex(full_idx)
                added_str = m.get("added")
                if added_str:
                    try:
                        added_dt = pd.Timestamp(added_str)
                        s = s.where(full_idx >= added_dt)
                    except Exception:  # noqa: BLE001
                        pass
                mc_dict[sym] = s
                if sym in all_volumes:
                    v = all_volumes[sym].reindex(full_idx)
                    if added_str:
                        try:
                            added_dt = pd.Timestamp(added_str)
                            v = v.where(full_idx >= added_dt)
                        except Exception:  # noqa: BLE001
                            pass
                    mv_dict[sym] = v
        else:
            # Theme/subsector: current-only membership
            tickers = theme_members.get(node_key, [])
            mc_dict = {t: all_closes[t].reindex(full_idx) for t in tickers if t in all_closes}
            mv_dict = {t: all_volumes[t].reindex(full_idx) for t in tickers if t in all_volumes}

        member_closes = pd.DataFrame(mc_dict, index=full_idx) if mc_dict else None
        member_volume = pd.DataFrame(mv_dict, index=full_idx) if mv_dict else None

        feats = _build_node_features(
            lvl=lvl,
            bench=bench_ret,
            member_closes=member_closes,
            member_volume=member_volume,
            node_volume=None,  # no single-ticker volume for EW indices
        )

        feats = feats.join(regime, how="left")
        feats.index.name = "date"
        feats["node"] = node_key
        node_dfs.append(feats.reset_index().set_index(["node", "date"]))

    if not node_dfs:
        return pd.DataFrame()

    panel = pd.concat(node_dfs)
    panel.sort_index(inplace=True)
    return panel


# ---------------------------------------------------------------------------
# Column schema (for tests and downstream consumers)
# ---------------------------------------------------------------------------

COLUMN_SCHEMA: list[str] = [
    # ----- existing columns (unchanged) -----
    "ret", "rs", "vel_1w", "vel_1m", "vel_3m", "accel", "accel_z",
    "cohesion", "cohesion_chg", "breadth_50", "persistence", "turnover_z",
    "vix_pctile", "tlt_ret_10d", "spy_above_200d",
    # ----- C1/C4 compound library columns (added 2026-07-04) -----
    # stochrsi_w_k / stochrsi_w_d — weekly StochRSI K and D from the faithful
    #   confluence.py port (research/signal_engine/confluence.py), computed on
    #   leak-free W-FRI weekly bars and forward-filled onto daily rows such that
    #   row t carries only the last COMPLETED weekly bar's value.
    #   Nullable: NaN before oscillator warm-up (< 40 weekly bars).
    #   EN: Weekly StochRSI %K / %D  |  ZH: 周线随机RSI K值 / D值
    "stochrsi_w_k",
    "stochrsi_w_d",
    # washout_w — boolean (0/1/NaN): K<20 on ≥2 consecutive completed weekly
    #   bars within the prior 3 bars (P8 registered definition, frozen).
    #   Forward-filled to daily; NaN before oscillator warm-up.
    #   EN: Weekly washout active  |  ZH: 周线超卖洗盘激活
    "washout_w",
    # cohesion_rebuild — boolean (0/1/NaN): C4 compound flag.
    #   True when washout_w active-or-within-5-sessions AND cohesion_chg > 0.056
    #   (panel_m q75 threshold; source: engine/oracle/episodes.py line 93).
    #   Interpretation (DISPLAY-ONLY per R4 adjudication): coordinated re-entry
    #   footprint — not a forecast, an observed pattern classification.
    #   EN: Cohesion rebuild signal (C4)  |  ZH: 凝聚力重建信号（C4复合）
    "cohesion_rebuild",
    # ----- Cross-asset / macro regime columns (added 2026-07-05) -----
    # All five are market-wide (same value for every node on a given date).
    # CAUSAL: each FRED series is reindexed to the trading-day spine,
    # forward-filled, and shift(1)ed before any transform so that panel row t
    # uses only FRED data published on or before t−1 (release-lag guard).
    #
    # hy_oas_chg_10d — HY option-adjusted spread 10-day change (%pts).
    #   Source: FRED BAMLH0A0HYM2 (ICE BofA US HY spread).
    #   Rising = credit stress / risk-off environment.
    #   EN: HY credit spread 10d chg  |  ZH: 高收益利差10日变化
    "hy_oas_chg_10d",
    # yc_slope — 10y minus 2y Treasury spread, raw level (%pts).
    #   Source: FRED T10Y2Y.  Negative = inverted yield curve.
    #   EN: Yield curve slope (10y−2y)  |  ZH: 收益率曲线斜率（10年-2年）
    "yc_slope",
    # oil_ret_10d — WTI crude oil 10-day percent return (dimensionless).
    #   Source: FRED DCOILWTICO.
    #   EN: WTI crude 10d return  |  ZH: WTI原油10日涨跌
    "oil_ret_10d",
    # dollar_chg_10d — Broad USD index 10-day percent change (dimensionless).
    #   Source: FRED DTWEXBGS (Federal Reserve broad dollar index).
    #   EN: Broad USD 10d change  |  ZH: 美元指数10日变化
    "dollar_chg_10d",
    # fin_conditions — NFCI raw level (positive = tight, negative = loose).
    #   Source: FRED NFCI (weekly; released Wed for the prior week).
    #   EN: NFCI financial conditions  |  ZH: 全国金融状况指数
    "fin_conditions",
]
