"""Pick Lab candidate book evaluators.

run_book(book, snap) -> list of pick dicts

Implements all 23 constructions from spec §3. Pure functions — no side effects,
no I/O, no randomness (except plab_random_ctrl which is seeded deterministically
from sha256(engine_id + asof) per PL-R12).

Liquidity floor (spec §3):
  close >= 5 AND dollar_adv_20d >= 10e6
  Rows missing dollar_adv_20d pass with liq_unknown=True flag.

Null semantics:
  A null condition value FAILS the condition, EXCEPT where spec says 'or null' passes.

Universe quartile/decile computed within the snapshot day (within snap DataFrame).

Snapshot columns per spec §5 (snapshot.py::SNAPSHOT_COLUMNS for the full list).
"""
from __future__ import annotations

import hashlib
import logging

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

_LIQ_CLOSE_MIN = 5.0
_LIQ_ADV_MIN = 10e6


# ---------------------------------------------------------------------------- #
# Liquidity filter
# ---------------------------------------------------------------------------- #

def _apply_liquidity(df: pd.DataFrame) -> pd.DataFrame:
    """Return df filtered to liquid names; add liq_unknown flag."""
    df = df.copy()
    # close >= 5
    close_ok = df["close"].ge(_LIQ_CLOSE_MIN).fillna(False)
    # dollar_adv_20d: missing rows pass (liq_unknown)
    adv = df.get("dollar_adv_20d")
    if adv is None:
        df["liq_unknown"] = True
        adv_ok = pd.Series(True, index=df.index)
    else:
        df["liq_unknown"] = adv.isna()
        adv_ok = adv.isna() | adv.ge(_LIQ_ADV_MIN)  # null passes (liq_unknown)
    return df[close_ok & adv_ok].copy()


# ---------------------------------------------------------------------------- #
# Quartile / decile helpers
# ---------------------------------------------------------------------------- #

def _top_quartile_mask(df: pd.DataFrame, col: str) -> "pd.Series[bool]":
    """Boolean mask: rows in top 25% of col (higher is better), nulls excluded."""
    vals = df[col]
    q75 = vals.quantile(0.75)
    return vals.ge(q75).fillna(False)


def _top_decile_mask(df: pd.DataFrame, col: str) -> "pd.Series[bool]":
    """Boolean mask: rows in top 10% of col (higher is better), nulls excluded."""
    vals = df[col]
    q90 = vals.quantile(0.90)
    return vals.ge(q90).fillna(False)


def _above_median_mask(df: pd.DataFrame, col: str) -> "pd.Series[bool]":
    """Boolean mask: rows above median of col, nulls excluded."""
    vals = df[col]
    med = vals.median()
    return vals.gt(med).fillna(False)


# ---------------------------------------------------------------------------- #
# Pick dict builder
# ---------------------------------------------------------------------------- #

def _col(df: pd.DataFrame, col: str, idx) -> object:
    """Safe column access; returns None if column missing or value NaN."""
    if col not in df.columns:
        return None
    v = df.at[idx, col]
    return None if pd.isna(v) else v


def _pick(df: pd.DataFrame, ticker: str, rank: int, why: list[str],
           features: dict) -> dict:
    row = df.loc[ticker]
    return {
        "ticker": ticker,
        "rank": rank,
        "close": _col(df, "close", ticker),
        "sector": _col(df, "sector", ticker),
        "liq_unknown": bool(row.get("liq_unknown", False)),
        "why": why,
        "features": features,
        "authority": "display_only",
    }


# ---------------------------------------------------------------------------- #
# Individual book implementations
# ---------------------------------------------------------------------------- #

def _book_1d_pure(df: pd.DataFrame, book: dict) -> list[dict]:
    """plab_1d_pure — 1D velocity: MACD cross ≤2, k×d cross ≤8, from_os, rsi14<65."""
    cfg = book["config"]
    mask = (
        df["d1_macd_xup_bars"].le(cfg["macd_xup_bars_max"]).fillna(False)
        & df["d1_kd_xup_bars"].le(cfg["kd_xup_bars_max"]).fillna(False)
        & df["d1_from_os"].eq(True).fillna(False)
        & df["rsi14"].lt(cfg["rsi14_max"]).fillna(False)
    )
    sub = df[mask].copy()
    if sub.empty:
        return []
    sub = sub.sort_values("composite_z", ascending=False).head(book["max_picks"])
    picks = []
    for rank, (ticker, _) in enumerate(sub.iterrows(), 1):
        picks.append(_pick(df, ticker, rank, ["1D MACD✚", "1D K×D✚", "from_OS", "RSI<65"], {
            "d1_macd_xup_bars": _col(df, "d1_macd_xup_bars", ticker),
            "d1_kd_xup_bars": _col(df, "d1_kd_xup_bars", ticker),
            "rsi14": _col(df, "rsi14", ticker),
        }))
    return picks


def _book_1d_regime(df: pd.DataFrame, book: dict) -> list[dict]:
    """plab_1d_regime — 1D velocity + regime filter, no RSI cap, no from_os."""
    cfg = book["config"]
    mask = (
        df["d1_macd_xup_bars"].le(cfg["macd_xup_bars_max"]).fillna(False)
        & df["d1_kd_xup_bars"].le(cfg["kd_xup_bars_max"]).fillna(False)
        & df["calm"].ge(cfg["calm_min"]).fillna(False)
    )
    # liquidity_overlay != 'contracting' (null fails)
    liq = df.get("liquidity_overlay")
    if liq is not None:
        mask = mask & liq.ne("contracting").fillna(False)
    # ext_grade != 'parabolic' (null fails)
    ext = df.get("ext_grade")
    if ext is not None:
        mask = mask & ext.ne("parabolic").fillna(False)
    sub = df[mask].copy()
    if sub.empty:
        return []
    sub = sub.sort_values("edge_alpha", ascending=False).head(book["max_picks"])
    picks = []
    for rank, (ticker, _) in enumerate(sub.iterrows(), 1):
        picks.append(_pick(df, ticker, rank, ["1D MACD✚", "1D K×D✚", "calm≥0.5", "regime-ok"], {
            "d1_macd_xup_bars": _col(df, "d1_macd_xup_bars", ticker),
            "d1_kd_xup_bars": _col(df, "d1_kd_xup_bars", ticker),
            "calm": _col(df, "calm", ticker),
            "edge_alpha": _col(df, "edge_alpha", ticker),
        }))
    return picks


def _book_1d_sectorheat(df: pd.DataFrame, book: dict) -> list[dict]:
    """plab_1d_sectorheat — book-2 base + sector heat overlay."""
    cfg = book["config"]
    # book-2 base
    mask = (
        df["d1_macd_xup_bars"].le(cfg["macd_xup_bars_max"]).fillna(False)
        & df["d1_kd_xup_bars"].le(cfg["kd_xup_bars_max"]).fillna(False)
        & df["calm"].ge(cfg["calm_min"]).fillna(False)
    )
    liq = df.get("liquidity_overlay")
    if liq is not None:
        mask = mask & liq.ne("contracting").fillna(False)
    ext = df.get("ext_grade")
    if ext is not None:
        mask = mask & ext.ne("parabolic").fillna(False)

    # sector heat: (stage in [improving, leading] AND rs_mom20>0) OR phase in [Trough, Recovery]
    stage_ok = df.get("sector_stage", pd.Series(None, index=df.index)).isin(
        cfg["sector_heat_improving_stages"]
    ).fillna(False)
    mom_ok = df.get("sector_rs_mom20", pd.Series(np.nan, index=df.index)).gt(0).fillna(False)
    phase_ok = df.get("sector_phase", pd.Series(None, index=df.index)).isin(
        cfg["sector_heat_phases"]
    ).fillna(False)
    heat_mask = (stage_ok & mom_ok) | phase_ok
    mask = mask & heat_mask

    sub = df[mask].copy()
    if sub.empty:
        return []
    sub = sub.sort_values("composite_z", ascending=False).head(book["max_picks"])
    picks = []
    for rank, (ticker, _) in enumerate(sub.iterrows(), 1):
        picks.append(_pick(df, ticker, rank, ["1D MACD✚", "1D K×D✚", "sector heating"], {
            "d1_macd_xup_bars": _col(df, "d1_macd_xup_bars", ticker),
            "sector_stage": _col(df, "sector_stage", ticker),
            "sector_phase": _col(df, "sector_phase", ticker),
        }))
    return picks


def _book_1d_blastoff(df: pd.DataFrame, book: dict) -> list[dict]:
    """plab_1d_blastoff — 1D cross ≤3 AND 3D not yet crossed AND above_200 AND ext_grade=none."""
    cfg = book["config"]
    mask = (
        df["d1_macd_xup_bars"].le(cfg["macd_xup_bars_max"]).fillna(False)
        & df["above_200"].eq(True).fillna(False)
    )
    # 3D MACD NOT yet crossed (d3_macd_xup_bars is null or > 15 = no recent cross)
    if "d3_macd_xup_bars" in df.columns:
        # null = never crossed (within window) → passes; value present = crossed → fails
        d3_not_crossed = df["d3_macd_xup_bars"].isna()
        mask = mask & d3_not_crossed
    # ext_grade must be 'none' exactly (null fails)
    ext = df.get("ext_grade")
    if ext is not None:
        mask = mask & ext.eq("none").fillna(False)
    sub = df[mask].copy()
    if sub.empty:
        return []
    sub = sub.sort_values("edge_alpha", ascending=False).head(book["max_picks"])
    picks = []
    for rank, (ticker, _) in enumerate(sub.iterrows(), 1):
        picks.append(_pick(df, ticker, rank, ["1D MACD✚≤3", "3D not yet", "above_200", "ext=none"], {
            "d1_macd_xup_bars": _col(df, "d1_macd_xup_bars", ticker),
            "d3_macd_xup_bars": _col(df, "d3_macd_xup_bars", ticker),
            "ext_grade": _col(df, "ext_grade", ticker),
        }))
    return picks


def _book_breakout_vol(df: pd.DataFrame, book: dict) -> list[dict]:
    """plab_breakout_vol — 20d high AND vol_ratio≥1.5 AND not parabolic AND calm≥0.5."""
    cfg = book["config"]
    mask = (
        df["is_20d_high"].eq(True).fillna(False)
        & df["vol_ratio_20d"].ge(cfg["vol_ratio_20d_min"]).fillna(False)
        & df["calm"].ge(cfg["calm_min"]).fillna(False)
    )
    ext = df.get("ext_grade")
    if ext is not None:
        mask = mask & ext.ne("parabolic").fillna(False)
    sub = df[mask].copy()
    if sub.empty:
        return []
    sub = sub.sort_values("vol_ratio_20d", ascending=False).head(book["max_picks"])
    picks = []
    for rank, (ticker, _) in enumerate(sub.iterrows(), 1):
        picks.append(_pick(df, ticker, rank, ["20d-HIGH", "vol✚≥1.5x", "calm≥0.5"], {
            "vol_ratio_20d": _col(df, "vol_ratio_20d", ticker),
            "is_20d_high": _col(df, "is_20d_high", ticker),
        }))
    return picks


def _book_resid_mom(df: pd.DataFrame, book: dict) -> list[dict]:
    """plab_resid_mom — top-12 edge_alpha, calm≥0.5, not parabolic, no oscillator."""
    cfg = book["config"]
    mask = df["calm"].ge(cfg["calm_min"]).fillna(False)
    ext = df.get("ext_grade")
    if ext is not None:
        mask = mask & ext.ne("parabolic").fillna(False)
    sub = df[mask].copy()
    if sub.empty:
        return []
    sub = sub.sort_values("edge_alpha", ascending=False).head(book["max_picks"])
    picks = []
    for rank, (ticker, _) in enumerate(sub.iterrows(), 1):
        picks.append(_pick(df, ticker, rank, ["top edge_alpha", "calm≥0.5", "no-gate"], {
            "edge_alpha": _col(df, "edge_alpha", ticker),
        }))
    return picks


def _book_otr_pullback(df: pd.DataFrame, book: dict) -> list[dict]:
    """plab_otr_pullback — on_the_run sector pullback [-8%,-2%] 1D k>d d<50."""
    cfg = book["config"]
    bucket = df.get("sector_bucket")
    if bucket is None:
        return []
    mask = (
        bucket.eq(cfg["sector_bucket"]).fillna(False)
        & df["above_200"].eq(True).fillna(False)
        & df["pct_vs_20dma"].ge(cfg["pct_vs_20dma_min"]).fillna(False)
        & df["pct_vs_20dma"].le(cfg["pct_vs_20dma_max"]).fillna(False)
        # 1D k > d: approximate via kd_xup_bars not null and k > d explicitly
        & df["d1_k"].gt(df["d1_d"]).fillna(False)
        & df["d1_d"].lt(cfg["d1_d_max"]).fillna(False)
    )
    sub = df[mask].copy()
    if sub.empty:
        return []
    sub = sub.sort_values("composite_z", ascending=False).head(book["max_picks"])
    picks = []
    for rank, (ticker, _) in enumerate(sub.iterrows(), 1):
        picks.append(_pick(df, ticker, rank, ["OTR sector", "pullback[-8,-2]", "1D k>d d<50"], {
            "sector_bucket": _col(df, "sector_bucket", ticker),
            "pct_vs_20dma": _col(df, "pct_vs_20dma", ticker),
            "d1_k": _col(df, "d1_k", ticker),
            "d1_d": _col(df, "d1_d", ticker),
        }))
    return picks


def _book_hi_base(df: pd.DataFrame, book: dict) -> list[dict]:
    """plab_hi_base — off_52w_high≤10% AND vol_squeeze active."""
    cfg = book["config"]
    mask = (
        df["off_52w_high_pct"].le(cfg["off_52w_high_pct_max"]).fillna(False)
        & df["vol_squeeze_state"].eq(True).fillna(False)
    )
    # Also accept truthy string values for vol_squeeze_state
    if "vol_squeeze_state" in df.columns:
        vss = df["vol_squeeze_state"]
        squeeze_on = (
            vss.eq(True).fillna(False)
            | vss.eq("on").fillna(False)
            | vss.eq("active").fillna(False)
            | vss.eq("squeeze").fillna(False)
        )
        mask = df["off_52w_high_pct"].le(cfg["off_52w_high_pct_max"]).fillna(False) & squeeze_on
    sub = df[mask].copy()
    if sub.empty:
        return []
    sub = sub.sort_values("composite_z", ascending=False).head(book["max_picks"])
    picks = []
    for rank, (ticker, _) in enumerate(sub.iterrows(), 1):
        picks.append(_pick(df, ticker, rank, ["near 52w high", "vol squeeze", "basing"], {
            "off_52w_high_pct": _col(df, "off_52w_high_pct", ticker),
            "vol_squeeze_state": _col(df, "vol_squeeze_state", ticker),
        }))
    return picks


def _book_washout_deep(df: pd.DataFrame, book: dict) -> list[dict]:
    """plab_washout_deep — washout_active AND dd>25 AND (coiled OR star) AND 3D from_os."""
    cfg = book["config"]
    mask = (
        df["washout_active"].eq(True).fillna(False)
        & df["dd_pct"].gt(cfg["dd_pct_min"]).fillna(False)
        & df["d3_from_os"].eq(True).fillna(False)
    )
    # coiled OR star
    coiled = df.get("coiled", pd.Series(False, index=df.index)).eq(True).fillna(False)
    star = df.get("star", pd.Series(False, index=df.index)).eq(True).fillna(False)
    mask = mask & (coiled | star)
    sub = df[mask].copy()
    if sub.empty:
        return []
    sub = sub.sort_values("dd_pct", ascending=False).head(book["max_picks"])
    picks = []
    for rank, (ticker, _) in enumerate(sub.iterrows(), 1):
        picks.append(_pick(df, ticker, rank, ["washout", f"dd>{cfg['dd_pct_min']}%", "3D from_OS", "coiled/star"], {
            "dd_pct": _col(df, "dd_pct", ticker),
            "d3_from_os": _col(df, "d3_from_os", ticker),
            "coiled": _col(df, "coiled", ticker),
            "star": _col(df, "star", ticker),
        }))
    return picks


def _book_sector_trough(df: pd.DataFrame, book: dict) -> list[dict]:
    """plab_sector_trough — sector phase Trough/Recovery AND tier T1/T2 fresh (t_ticks≤2)."""
    cfg = book["config"]
    phase = df.get("sector_phase")
    if phase is None:
        return []
    mask = (
        phase.isin(cfg["sector_phases"]).fillna(False)
        & df["tier"].isin(cfg["tier_whitelist"]).fillna(False)
        & df["t_ticks"].le(cfg["t_ticks_max"]).fillna(False)
    )
    sub = df[mask].copy()
    if sub.empty:
        return []
    sub = sub.sort_values("composite_z", ascending=False).head(book["max_picks"])
    picks = []
    for rank, (ticker, _) in enumerate(sub.iterrows(), 1):
        picks.append(_pick(df, ticker, rank, ["Trough/Recovery", "T1/T2 fresh"], {
            "sector_phase": _col(df, "sector_phase", ticker),
            "tier": _col(df, "tier", ticker),
            "t_ticks": _col(df, "t_ticks", ticker),
        }))
    return picks


def _book_washout_clean(df: pd.DataFrame, book: dict) -> list[dict]:
    """plab_washout_clean — washout_active AND dd>20 AND no dilution AND quality screens."""
    cfg = book["config"]
    mask = (
        df["washout_active"].eq(True).fillna(False)
        & df["dd_pct"].gt(cfg["dd_pct_min"]).fillna(False)
        & df["dilution_events_365d"].le(cfg["dilution_events_365d_max"]).fillna(False)
    )
    # days_since_shelf > 90 OR null passes — null is NaN in pandas, gt returns False for NaN
    shelf = df.get("days_since_shelf")
    if shelf is not None:
        shelf_ok = shelf.isna() | shelf.gt(cfg["days_since_shelf_min_or_null"])
        mask = mask & shelf_ok
    # interest_coverage > 2 OR null passes — same pattern
    ic = df.get("interest_coverage")
    if ic is not None:
        ic_ok = ic.isna() | ic.gt(cfg["interest_coverage_min_or_null"])
        mask = mask & ic_ok
    sub = df[mask].copy()
    if sub.empty:
        return []
    sub = sub.sort_values("axis_quality", ascending=False).head(book["max_picks"])
    picks = []
    for rank, (ticker, _) in enumerate(sub.iterrows(), 1):
        picks.append(_pick(df, ticker, rank, ["washout", f"dd>{cfg['dd_pct_min']}%", "no-dilution", "quality"], {
            "dd_pct": _col(df, "dd_pct", ticker),
            "dilution_events_365d": _col(df, "dilution_events_365d", ticker),
            "axis_quality": _col(df, "axis_quality", ticker),
        }))
    return picks


def _book_edge_pure(df: pd.DataFrame, book: dict) -> list[dict]:
    """plab_edge_pure — top-12 axis_selection, only exclusion = earnings blackout."""
    blackout = df.get("is_blackout", pd.Series(False, index=df.index))
    mask = blackout.ne(True).fillna(True)  # not in blackout (null passes)
    sub = df[mask].copy()
    if sub.empty:
        return []
    sub = sub.sort_values("axis_selection", ascending=False).head(book["max_picks"])
    picks = []
    for rank, (ticker, _) in enumerate(sub.iterrows(), 1):
        picks.append(_pick(df, ticker, rank, ["top axis_sel", "no gate"], {
            "axis_selection": _col(df, "axis_selection", ticker),
        }))
    return picks


def _book_edge_1d(df: pd.DataFrame, book: dict) -> list[dict]:
    """plab_edge_1d — axis_selection top-quartile AND 1D MACD cross ≤3 AND k×d cross ≤8."""
    cfg = book["config"]
    tq = _top_quartile_mask(df, "axis_selection")
    mask = (
        tq
        & df["d1_macd_xup_bars"].le(cfg["d1_macd_xup_bars_max"]).fillna(False)
        & df["d1_kd_xup_bars"].le(cfg["d1_kd_xup_bars_max"]).fillna(False)
    )
    sub = df[mask].copy()
    if sub.empty:
        return []
    sub = sub.sort_values("axis_selection", ascending=False).head(book["max_picks"])
    picks = []
    for rank, (ticker, _) in enumerate(sub.iterrows(), 1):
        picks.append(_pick(df, ticker, rank, ["EDGE q1", "1D MACD✚≤3", "1D K×D✚≤8"], {
            "axis_selection": _col(df, "axis_selection", ticker),
            "d1_macd_xup_bars": _col(df, "d1_macd_xup_bars", ticker),
            "d1_kd_xup_bars": _col(df, "d1_kd_xup_bars", ticker),
        }))
    return picks


def _book_quality_pullback(df: pd.DataFrame, book: dict) -> list[dict]:
    """plab_quality_pullback — axis_quality top-quartile AND archetype AND pullback."""
    cfg = book["config"]
    tq = _top_quartile_mask(df, "axis_quality")
    arch = df.get("archetype", pd.Series(None, index=df.index))
    mask = (
        tq
        & arch.isin(cfg["archetypes"]).fillna(False)
        & df["pct_vs_20dma"].lt(cfg["pct_vs_20dma_max"]).fillna(False)
        & df["rsi14"].lt(cfg["rsi14_max"]).fillna(False)
        & df["above_200"].eq(True).fillna(False)
    )
    sub = df[mask].copy()
    if sub.empty:
        return []
    sub = sub.sort_values("axis_quality", ascending=False).head(book["max_picks"])
    picks = []
    for rank, (ticker, _) in enumerate(sub.iterrows(), 1):
        picks.append(_pick(df, ticker, rank, ["quality q1", "compounder/growth", "pullback", "RSI<55"], {
            "axis_quality": _col(df, "axis_quality", ticker),
            "archetype": _col(df, "archetype", ticker),
            "pct_vs_20dma": _col(df, "pct_vs_20dma", ticker),
        }))
    return picks


def _book_beta_squeeze(df: pd.DataFrame, book: dict) -> list[dict]:
    """plab_beta_squeeze — archetype=high_beta_momentum AND current_mode=squeeze AND calm≥0.5."""
    cfg = book["config"]
    arch = df.get("archetype", pd.Series(None, index=df.index))
    mode = df.get("current_mode", pd.Series(None, index=df.index))
    mask = (
        arch.eq(cfg["archetype"]).fillna(False)
        & mode.eq(cfg["current_mode"]).fillna(False)
        & df["calm"].ge(cfg["calm_min"]).fillna(False)
    )
    sub = df[mask].copy()
    if sub.empty:
        return []
    sub = sub.sort_values("edge_alpha", ascending=False).head(book["max_picks"])
    picks = []
    for rank, (ticker, _) in enumerate(sub.iterrows(), 1):
        picks.append(_pick(df, ticker, rank, ["high_beta", "squeeze-mode", "calm≥0.5"], {
            "archetype": _col(df, "archetype", ticker),
            "current_mode": _col(df, "current_mode", ticker),
        }))
    return picks


def _book_revision_accel(df: pd.DataFrame, book: dict) -> list[dict]:
    """plab_revision_accel — edge_revision≥1.0 AND implied_upside≥15 AND not blackout AND above_200."""
    cfg = book["config"]
    blackout = df.get("is_blackout", pd.Series(False, index=df.index))
    mask = (
        df["edge_revision"].ge(cfg["edge_revision_min"]).fillna(False)
        & df["implied_upside_pct"].ge(cfg["implied_upside_pct_min"]).fillna(False)
        & blackout.ne(True).fillna(True)
        & df["above_200"].eq(True).fillna(False)
    )
    sub = df[mask].copy()
    if sub.empty:
        return []
    sub = sub.sort_values("edge_revision", ascending=False).head(book["max_picks"])
    picks = []
    for rank, (ticker, _) in enumerate(sub.iterrows(), 1):
        picks.append(_pick(df, ticker, rank, ["revision✚", "upside≥15%", "above_200"], {
            "edge_revision": _col(df, "edge_revision", ticker),
            "implied_upside_pct": _col(df, "implied_upside_pct", ticker),
        }))
    return picks


def _book_flagship_nogate(df: pd.DataFrame, book: dict) -> list[dict]:
    """plab_flagship_nogate — top-12 composite_z ignoring oscillator gate; cycle hard-block excluded.

    Spec §3/§5: drop only the oscillator gate; cycle hard-block states (TOP WATCH /
    ROLLING OVER in cycle_state) are still excluded.  gate_state is NEVER 'hard_block'
    in production (producer emits 'eligible'/'ineligible'); the correct column is
    cycle_state (see plab_topping_avoid.config.cycle_states_avoid).
    """
    # Hard-block cycle states mirror plab_topping_avoid (TOP WATCH / ROLLING OVER).
    _CYCLE_HARD_BLOCK = frozenset(["TOP WATCH", "ROLLING OVER"])
    cycle = df.get("cycle_state", pd.Series(None, index=df.index))
    mask = ~cycle.isin(_CYCLE_HARD_BLOCK).fillna(False)
    sub = df[mask].copy()
    if sub.empty:
        return []
    sub = sub.sort_values("composite_z", ascending=False).head(book["max_picks"])
    picks = []
    for rank, (ticker, _) in enumerate(sub.iterrows(), 1):
        picks.append(_pick(df, ticker, rank, ["top composite_z", "no-osc-gate"], {
            "composite_z": _col(df, "composite_z", ticker),
        }))
    return picks


def _book_flagship_t3t4(df: pd.DataFrame, book: dict) -> list[dict]:
    """plab_flagship_t3t4 — top-12 composite_z among T1/T2/T3/T4."""
    cfg = book["config"]
    mask = df["tier"].isin(cfg["tier_whitelist"]).fillna(False)
    sub = df[mask].copy()
    if sub.empty:
        return []
    sub = sub.sort_values("composite_z", ascending=False).head(book["max_picks"])
    picks = []
    for rank, (ticker, _) in enumerate(sub.iterrows(), 1):
        picks.append(_pick(df, ticker, rank, ["T1-T4", "composite_z"], {
            "tier": _col(df, "tier", ticker),
            "composite_z": _col(df, "composite_z", ticker),
        }))
    return picks


def _book_topping_avoid(df: pd.DataFrame, book: dict) -> list[dict]:
    """plab_topping_avoid — INVERSE: cycle_state in {TOP WATCH,ROLLING OVER} OR
    (sector_bucket=take_profits AND rsi14>70). Ranked by rsi14 descending."""
    cfg = book["config"]
    cycle = df.get("cycle_state", pd.Series(None, index=df.index))
    bucket = df.get("sector_bucket", pd.Series(None, index=df.index))

    cycle_mask = cycle.isin(cfg["cycle_states_avoid"]).fillna(False)
    sector_rsi_mask = (
        bucket.eq(cfg["sector_bucket_avoid"]).fillna(False)
        & df["rsi14"].gt(cfg["sector_rsi14_min"]).fillna(False)
    )
    mask = cycle_mask | sector_rsi_mask
    sub = df[mask].copy()
    if sub.empty:
        return []
    sub = sub.sort_values("rsi14", ascending=False).head(book["max_picks"])
    picks = []
    for rank, (ticker, _) in enumerate(sub.iterrows(), 1):
        picks.append(_pick(df, ticker, rank,
                           ["AVOID/inverse", "topping", "cycle-TOP or sector-TP"],
                           {
                               "cycle_state": _col(df, "cycle_state", ticker),
                               "rsi14": _col(df, "rsi14", ticker),
                               "sector_bucket": _col(df, "sector_bucket", ticker),
                           }))
    return picks


def _book_random_ctrl(df: pd.DataFrame, book: dict) -> list[dict]:
    """plab_random_ctrl — 12 uniform-random liquid names; seed sha256(engine_id+asof).

    Deterministic: same engine_id+asof always returns same picks (PL-R12).
    Never uses wall-clock or unseeded random.
    """
    cfg = book["config"]
    asof = str(df.attrs.get("asof", "2000-01-01"))
    seed_str = book["engine_id"] + asof
    seed = int(hashlib.sha256(seed_str.encode()).hexdigest(), 16) % (2**32)
    rng = np.random.default_rng(seed)

    n = min(cfg["sample_n"], len(df))
    if n == 0:
        return []
    indices = rng.choice(len(df), size=n, replace=False)
    selected = df.iloc[sorted(indices)]
    picks = []
    for rank, (ticker, _) in enumerate(selected.iterrows(), 1):
        picks.append(_pick(df, ticker, rank, ["random-ctrl"], {
            "seed": seed_str,
        }))
    return picks


# Long-hold grids

def _book_lh_compounder(df: pd.DataFrame, book: dict) -> list[dict]:
    """plab_lh_compounder — axis_quality top-decile AND archetype compounder/growth AND no dilution."""
    cfg = book["config"]
    td = _top_decile_mask(df, "axis_quality")
    arch = df.get("archetype", pd.Series(None, index=df.index))
    mask = (
        td
        & arch.isin(cfg["archetypes"]).fillna(False)
        & df["dilution_events_365d"].le(cfg["dilution_events_365d_max"]).fillna(False)
    )
    sub = df[mask].copy()
    if sub.empty:
        return []
    sub = sub.sort_values("axis_quality", ascending=False).head(book["max_picks"])
    picks = []
    for rank, (ticker, _) in enumerate(sub.iterrows(), 1):
        picks.append(_pick(df, ticker, rank, ["quality decile", "compounder/growth", "no-dilution"], {
            "axis_quality": _col(df, "axis_quality", ticker),
            "archetype": _col(df, "archetype", ticker),
        }))
    return picks


def _book_lh_edge_durability(df: pd.DataFrame, book: dict) -> list[dict]:
    """plab_lh_edge_durability — axis_selection top-decile AND axis_quality above median."""
    td = _top_decile_mask(df, "axis_selection")
    am = _above_median_mask(df, "axis_quality")
    mask = td & am
    sub = df[mask].copy()
    if sub.empty:
        return []
    sub = sub.sort_values("axis_selection", ascending=False).head(book["max_picks"])
    picks = []
    for rank, (ticker, _) in enumerate(sub.iterrows(), 1):
        picks.append(_pick(df, ticker, rank, ["EDGE decile", "quality>median"], {
            "axis_selection": _col(df, "axis_selection", ticker),
            "axis_quality": _col(df, "axis_quality", ticker),
        }))
    return picks


def _book_lh_washout_survivor(df: pd.DataFrame, book: dict) -> list[dict]:
    """plab_lh_washout_survivor — dd>40 AND quality>median AND ic>3 AND no dilution."""
    cfg = book["config"]
    am = _above_median_mask(df, "axis_quality")
    mask = (
        df["dd_pct"].gt(cfg["dd_pct_min"]).fillna(False)
        & am
        & df["interest_coverage"].gt(cfg["interest_coverage_min"]).fillna(False)
        & df["dilution_events_365d"].le(cfg["dilution_events_365d_max"]).fillna(False)
    )
    sub = df[mask].copy()
    if sub.empty:
        return []
    sub = sub.sort_values("axis_quality", ascending=False).head(book["max_picks"])
    picks = []
    for rank, (ticker, _) in enumerate(sub.iterrows(), 1):
        picks.append(_pick(df, ticker, rank, ["dd>40%", "quality>median", "ic>3", "no-dilution"], {
            "dd_pct": _col(df, "dd_pct", ticker),
            "interest_coverage": _col(df, "interest_coverage", ticker),
        }))
    return picks


# ---------------------------------------------------------------------------- #
# Family G — Flow Leaders books (FL-R8)
# These books read from site/flowleaders/leaders.json (already built by
# build_flow_leaders before build_pick_lab runs) rather than the snapshot.
# Fire eligibility is pre-computed in leaders.json (fire_a / fire_b flags);
# build_pick_lab consumes the artifact, does NOT recompute legs (FL-R8 law).
# ---------------------------------------------------------------------------- #

def _load_leaders_json() -> list[dict]:
    """Load site/flowleaders/leaders.json; return board rows list."""
    try:
        from lib import config as _cfg  # noqa: PLC0415
        root = _cfg.ROOT
        p = root / _cfg.load()["storage"]["site_dir"] / "flowleaders" / "leaders.json"
        if not p.exists():
            return []
        import json  # noqa: PLC0415
        d = json.loads(p.read_text())
        # Combine board_a (for fire_a) and board_b (for fire_b) — deduplicated by caller
        return d.get("board_a", []) + d.get("board_b", [])
    except Exception as exc:  # noqa: BLE001
        log.warning("pick_lab flow_leader: leaders.json load failed: %s", exc)
        return []


def _book_flow_leader(df: pd.DataFrame, book: dict) -> list[dict]:
    """plab_flow_leader — Board A fire candidates from leaders.json.

    Reads fire_a=True rows from site/flowleaders/leaders.json.
    Ranks by recurrence_count desc (max 12 picks per max_picks).
    PIT law: fire_date = leaders.json as_of (set in build_pick_lab caller).
    """
    rows = _load_leaders_json()
    if not rows:
        return []

    fired = [r for r in rows if r.get("fire_a") is True]
    if not fired:
        return []

    # Sort by recurrence_count desc (ties: net_prem_norm_abs desc)
    fired.sort(key=lambda r: (
        -(r.get("recurrence_count") or 0) if r.get("recurrence_count") is not None else 1,
        -(r.get("net_prem_norm_abs") or 0),
    ))
    fired = fired[:book["max_picks"]]

    # Apply liquidity filter from snapshot if ticker is present
    picks = []
    for rank, r in enumerate(fired, 1):
        ticker = r.get("ticker")
        if not ticker:
            continue
        close = None
        if ticker in df.index:
            try:
                close = _col(df, "close", ticker)
                if close is not None and float(close) < _LIQ_CLOSE_MIN:
                    continue  # skip illiquid
            except Exception:  # noqa: BLE001
                pass
        picks.append({
            "ticker": ticker,
            "rank": rank,
            "close": close,
            "sector": _col(df, "sector", ticker) if ticker in df.index else None,
            "liq_unknown": ticker not in df.index,
            "why": ["flow_recur", "fire_a"],
            "features": {
                "recurrence_count": r.get("recurrence_count"),
                "flow_z": r.get("flow_z"),
                "K_a": r.get("K_a"),
                "n_avail_a": r.get("n_avail_a"),
                "signing_source": r.get("signing_source"),
            },
            "authority": "display_only",
        })
    return picks


def _book_flow_washout(df: pd.DataFrame, book: dict) -> list[dict]:
    """plab_flow_washout — Board B fire candidates from leaders.json.

    Reads fire_b=True rows from site/flowleaders/leaders.json.
    Ranks by days_since_inflection asc (most recent first, max 12 picks).
    Ruler: 21d_abs_reversion_capture_mfe_mae (FL-R8).
    Distinct from KILLED washout×2W-turn (#1747 ESXA3-FV-C): no 2W legs here.
    """
    rows = _load_leaders_json()
    if not rows:
        return []

    fired = [r for r in rows if r.get("fire_b") is True]
    if not fired:
        return []

    # Sort by days_since_inflection asc (None last)
    fired.sort(key=lambda r: (
        r.get("days_since_inflection") if r.get("days_since_inflection") is not None else 9999,
    ))
    fired = fired[:book["max_picks"]]

    picks = []
    for rank, r in enumerate(fired, 1):
        ticker = r.get("ticker")
        if not ticker:
            continue
        close = None
        if ticker in df.index:
            try:
                close = _col(df, "close", ticker)
                if close is not None and float(close) < _LIQ_CLOSE_MIN:
                    continue
            except Exception:  # noqa: BLE001
                pass
        picks.append({
            "ticker": ticker,
            "rank": rank,
            "close": close,
            "sector": _col(df, "sector", ticker) if ticker in df.index else None,
            "liq_unknown": ticker not in df.index,
            "why": ["flow_inflect", "washout", "fire_b"],
            "features": {
                "days_since_inflection": r.get("days_since_inflection"),
                "K_b": r.get("K_b"),
                "n_avail_b": r.get("n_avail_b"),
                "signing_source": r.get("signing_source"),
            },
            "authority": "display_only",
        })
    return picks


# ---------------------------------------------------------------------------- #
# Family H — Leader Radar books (LR W2a)
# These books read from site/leaderradar/radar.json (built by build_leader_radar
# BEFORE build_pick_lab runs). Fire eligibility pre-computed in radar.json;
# build_pick_lab consumes the artifact, does NOT recompute legs (LR-R8 law).
# ---------------------------------------------------------------------------- #

def _load_radar_json() -> list[dict]:
    """Load site/leaderradar/radar.json; return rows list."""
    try:
        from lib import config as _cfg  # noqa: PLC0415
        root = _cfg.ROOT
        p = root / _cfg.load()["storage"]["site_dir"] / "leaderradar" / "radar.json"
        if not p.exists():
            return []
        import json  # noqa: PLC0415
        d = json.loads(p.read_text())
        return d.get("rows", [])
    except Exception as exc:  # noqa: BLE001
        log.warning("pick_lab leader_radar: radar.json load failed: %s", exc)
        return []


def _book_leader_precipice(df: pd.DataFrame, book: dict) -> list[dict]:
    """plab_leader_precipice — CATALYST_WINDOW (precipice) fire candidates from radar.json.

    Reads fire_precipice=True rows. Ranks by days_in_state asc (most-recent entry first).
    LR-R8: consumption-not-recomputation — fire flags consumed as-is from radar.json.
    """
    rows = _load_radar_json()
    if not rows:
        return []

    fired = [r for r in rows if r.get("fire_precipice") is True]
    if not fired:
        return []

    # Sort by days_in_state asc (None last)
    fired.sort(key=lambda r: (
        r.get("days_in_state") if r.get("days_in_state") is not None else 9999,
    ))
    fired = fired[:book["max_picks"]]

    picks = []
    for rank, r in enumerate(fired, 1):
        ticker = r.get("ticker")
        if not ticker:
            continue
        close = None
        if ticker in df.index:
            try:
                close = _col(df, "close", ticker)
                if close is not None and float(close) < _LIQ_CLOSE_MIN:
                    continue
            except Exception:  # noqa: BLE001
                pass
        picks.append({
            "ticker": ticker,
            "rank": rank,
            "close": close,
            "sector": _col(df, "sector", ticker) if ticker in df.index else None,
            "liq_unknown": ticker not in df.index,
            "why": ["leader_radar", "catalyst_window_entry", "fire_precipice"],
            "features": {
                "raw_state": r.get("raw_state"),
                "state": r.get("state"),
                "days_in_state": r.get("days_in_state"),
                "breakaway_watch_state": r.get("breakaway_watch_state"),
            },
            "authority": "display_only",
        })
    return picks


def _book_leader_onset(df: pd.DataFrame, book: dict) -> list[dict]:
    """plab_leader_onset — BREAKAWAY (onset) fire candidates from radar.json.

    Reads fire_onset=True rows. Ranks by days_in_state asc (most-recent BREAKAWAY entry first).
    LR-R8: consumption-not-recomputation — fire flags consumed as-is from radar.json.
    """
    rows = _load_radar_json()
    if not rows:
        return []

    fired = [r for r in rows if r.get("fire_onset") is True]
    if not fired:
        return []

    # Sort by days_in_state asc (None last)
    fired.sort(key=lambda r: (
        r.get("days_in_state") if r.get("days_in_state") is not None else 9999,
    ))
    fired = fired[:book["max_picks"]]

    picks = []
    for rank, r in enumerate(fired, 1):
        ticker = r.get("ticker")
        if not ticker:
            continue
        close = None
        if ticker in df.index:
            try:
                close = _col(df, "close", ticker)
                if close is not None and float(close) < _LIQ_CLOSE_MIN:
                    continue
            except Exception:  # noqa: BLE001
                pass
        picks.append({
            "ticker": ticker,
            "rank": rank,
            "close": close,
            "sector": _col(df, "sector", ticker) if ticker in df.index else None,
            "liq_unknown": ticker not in df.index,
            "why": ["leader_radar", "breakaway_entry", "fire_onset"],
            "features": {
                "raw_state": r.get("raw_state"),
                "state": r.get("state"),
                "days_in_state": r.get("days_in_state"),
                "breakaway_watch_state": r.get("breakaway_watch_state"),
            },
            "authority": "display_only",
        })
    return picks


# ---------------------------------------------------------------------------- #
# Dispatch table
# ---------------------------------------------------------------------------- #

_BOOK_FUNCS: dict[str, object] = {
    "plab_1d_pure":              _book_1d_pure,
    "plab_1d_regime":            _book_1d_regime,
    "plab_1d_sectorheat":        _book_1d_sectorheat,
    "plab_1d_blastoff":          _book_1d_blastoff,
    "plab_breakout_vol":         _book_breakout_vol,
    "plab_resid_mom":            _book_resid_mom,
    "plab_otr_pullback":         _book_otr_pullback,
    "plab_hi_base":              _book_hi_base,
    "plab_washout_deep":         _book_washout_deep,
    "plab_sector_trough":        _book_sector_trough,
    "plab_washout_clean":        _book_washout_clean,
    "plab_edge_pure":            _book_edge_pure,
    "plab_edge_1d":              _book_edge_1d,
    "plab_quality_pullback":     _book_quality_pullback,
    "plab_beta_squeeze":         _book_beta_squeeze,
    "plab_revision_accel":       _book_revision_accel,
    "plab_flagship_nogate":      _book_flagship_nogate,
    "plab_flagship_t3t4":        _book_flagship_t3t4,
    "plab_topping_avoid":        _book_topping_avoid,
    "plab_random_ctrl":          _book_random_ctrl,
    "plab_lh_compounder":        _book_lh_compounder,
    "plab_lh_edge_durability":   _book_lh_edge_durability,
    "plab_lh_washout_survivor":  _book_lh_washout_survivor,
    # Family G — Flow Leaders (FL-R8): artifact-sourced books (bypass snap-based filter)
    "plab_flow_leader":          _book_flow_leader,
    "plab_flow_washout":         _book_flow_washout,
    # Family H — Leader Radar (LR W2a): artifact-sourced books (fire flags from radar.json)
    "plab_leader_precipice":     _book_leader_precipice,
    "plab_leader_onset":         _book_leader_onset,
}


# ---------------------------------------------------------------------------- #
# Public API
# ---------------------------------------------------------------------------- #

def run_book(book: dict, snap: pd.DataFrame) -> list[dict]:
    """Evaluate one book against the snapshot DataFrame.

    Parameters
    ----------
    book : dict
        A registry entry from engine.pick_lab.registry.REGISTRY.
    snap : pd.DataFrame
        Universe snapshot for one asof date.  Index = ticker.
        Expects columns per spec §5.  snap.attrs['asof'] = date string.

    Returns
    -------
    list of pick dicts: {ticker, rank, close, sector, liq_unknown, why, features, authority}
    Ranked by the book's rank_by column; at most book['max_picks'] entries.
    Authority is always 'display_only' (PL-R1/PL-R10).
    """
    if snap.empty:
        return []
    # Expose d1_k and d1_d as convenience columns (mapped from d1_k/d1_d)
    df = _apply_liquidity(snap)
    if df.empty:
        return []
    # Rename d1_k → d1_k (keep consistent; already present)
    # The otr_pullback book uses df["d1_k"] and df["d1_d"] directly.

    fn = _BOOK_FUNCS.get(book["engine_id"])
    if fn is None:
        log.warning("pick_lab: no implementation for engine_id=%s", book["engine_id"])
        return []
    try:
        return fn(df, book)
    except Exception as exc:
        log.error("pick_lab run_book %s error: %s", book["engine_id"], exc, exc_info=True)
        return []
