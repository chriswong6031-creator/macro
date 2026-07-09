"""China Pick Lab snapshot schema and pure assembly function.

CN parallel of engine/pick_lab/snapshot.py.  Assembles per-ticker frozen feature
rows from the materials available at the end of build_china_library.main() — all
inputs are pre-computed there; this module is pure (no I/O, no side effects).

Public API
----------
CN_SNAPSHOT_COLUMNS  : list[str] — ordered column list for CN snapshots
build_cn_core_rows(...)          — PURE function; returns list[dict]

Schema note
-----------
CN snapshot columns are a CN-specific superset of the US snapshot.  Many fields
(1D oscillators, washout, COILED, extension) are shared; CN adds reversal-family
columns (rev_3m_sector_rank, rev_deepest_quintile), board/limit context, ST flag,
and CN-specific regime scalars (cycle_phase, participation_regime, policy_impulse,
qvix_z, csi300_close).

Null honesty: every field not available in the caller's scope arrives as None.
A null is NEVER fabricated.  The downstream books and graders handle nulls
correctly (cn.py _apply_cn_universe and book funcs all null-safe).

CNPL-R4: fillable / sealed_up / limit_state are stamped from the fire-time
data (sig_verdict carries limit_state; fillable is derived from it here).
"""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Column list — spec §5 + CN additions                                        #
# --------------------------------------------------------------------------- #

# Identity / price
_CN_IDENTITY_COLS = [
    "asof",
    "ticker",
    "name",
    "name_zh",
    "sector",
    "board",          # "main" | "star" | "chinext" | "bse"
    "close",
    "turnover_20d",   # ¥ 20-day turnover (liquidity floor: ≥ ¥30M)
]

# Reversal family — the CN validated edge
_CN_REVERSAL_COLS = [
    "rev_3m",              # raw 3-month return %
    "rev_z",               # within-sector reversal z (signed; high = deeper dip)
    "rev_3m_sector_rank",  # within-sector rank by reversal depth (1 = deepest)
    "rev_sector_n",        # number of names in sector (denominator for quintile)
    "rev_deepest_quintile",  # bool: in the deepest 20% of sector
]

# Wash/volatility context
_CN_WASHOUT_COLS = [
    "washout_2w",      # bool: 2W StochRSI reclaim from oversold (own-name)
    "coiled",          # bool: COILED wave-3 state (coiled.assess)
    "star",            # bool: STAR/ChiNext COILED cohort bonus
    "extension_score", # float 0..1 (anti-chase; higher = more extended)
    "extension_extended",  # bool: flag for the extended state
    "lowvol_tercile",  # "low" | "mid" | "high" | None
]

# 1D oscillators (from signals_1d.compute_grids — same keys as US d1_*)
_CN_OSC_D1 = [
    "d1_macd", "d1_sig", "d1_macd_xup_bars",
    "d1_k", "d1_d", "d1_kd_xup_bars",
    "d1_from_os", "d1_ob",
]

# 2D oscillators
_CN_OSC_D2 = [
    "d2_macd", "d2_sig", "d2_macd_xup_bars",
    "d2_k", "d2_d", "d2_kd_xup_bars",
    "d2_from_os", "d2_ob",
]

# Technicals (from china_signals.ashare_tech)
_CN_TECH_COLS = [
    "rsi_5",
    "rsi_10",
    "ret_5d",
    "dist_ma20_z",
    "above_ma120",
    "ma20_slope_up",
    "limit_flag",
]

# Draw-down / context
_CN_DD_COLS = [
    "dd_pct_2y",    # max drawdown from 2y high (%)
]

# Executability / limit-state (stamped at fire close — CNPL-R4)
_CN_EXEC_COLS = [
    "limit_state",   # "sealed_up" | "sealed_down" | "limit_up" | "limit_down" | None
    "limit_width",   # board's daily limit % (10 / 20 / 30 / 5)
    "fillable",      # bool: False when sealed_up at fire close → excluded from grading
    "chase_veto",    # bool: limit-up sealed or 5d run ≥ 15%
    "t_plus_one_risk",  # bool: T+1 execution risk flag
    "is_st",         # bool: ST/*ST exclusion flag
]

# Regime scalars (same value repeated on every row for the given asof)
_CN_REGIME_COLS = [
    "cycle_phase",
    "participation_regime",
    "participation_risk",
    "policy_impulse",
    "qvix_z",
    "csi300_close",
]

# Archetype / theme (context only, never gates)
_CN_CONTEXT_COLS = [
    "archetype",
    "above_20d_low",
    "theme_basket",
    "theme_breadth_pct",
    "theme_member_ret21_rank",
    "block_discount_recent",   # bool: block trade ≤ −15% discount within 10 sessions (CNPL-R9)
    "lhb_inst_seats_5d",       # int: LHB institutional seats within 5 sessions (CNPL-R9)
]

CN_SNAPSHOT_COLUMNS: list[str] = (
    _CN_IDENTITY_COLS
    + _CN_REVERSAL_COLS
    + _CN_WASHOUT_COLS
    + _CN_OSC_D1
    + _CN_OSC_D2
    + _CN_TECH_COLS
    + _CN_DD_COLS
    + _CN_EXEC_COLS
    + _CN_REGIME_COLS
    + _CN_CONTEXT_COLS
)


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #

def _safe(v: Any, cast=None) -> Any:
    """Return v cast to `cast` type, or None on any exception (null-honest)."""
    if v is None:
        return None
    try:
        return cast(v) if cast is not None else v
    except Exception:
        return None


def _from_extension(ext: dict | None) -> tuple[float | None, bool | None]:
    """(extension_score, extension_extended) from an extension_read dict."""
    if not ext:
        return None, None
    score = _safe(ext.get("score"), float)
    ext_flag = _safe(ext.get("extended"), bool)
    return score, ext_flag


def _lowvol_tercile(close_series: pd.Series | None,
                    liq_by: dict | None = None,
                    ticker: str = "") -> str | None:
    """Low-vol tercile label ('low'/'mid'/'high') from a per-ticker volatility.

    We use the 60-day trailing annualized vol of the close series as the raw
    signal.  The tercile assignment is done cross-sectionally in the calling
    block (build_china_library): this helper just computes the raw vol scalar
    so the producer block can build the cross-section and assign terciles.

    Returns the raw annualized vol as a float (for cross-sectional rank),
    or None when the series is too short.
    """
    # This helper intentionally returns float (not a label) — the label
    # assignment happens cross-sectionally in build_cn_core_rows.
    if close_series is None:
        return None
    c = close_series.dropna()
    if len(c) < 63:
        return None
    try:
        ret = c.pct_change(fill_method=None).dropna()
        if len(ret) < 20:
            return None
        return float(ret.tail(60).std() * (252 ** 0.5))
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Pure builder                                                                #
# --------------------------------------------------------------------------- #

def build_cn_core_rows(
    *,
    tickers: list[str],
    asof: str,
    close_by: dict[str, float | None],
    turnover_by: dict[str, float | None],
    sector_by: dict[str, str | None],
    name_by: dict[str, str | None],
    name_zh_by: dict[str, str | None],
    board_by: dict[str, str | None],
    is_st_by: dict[str, bool | None],
    # Reversal data
    rev_3m_by: dict[str, float | None] | None = None,
    rev_z_by: dict[str, float | None] | None = None,
    rev_sector_rank_by: dict[str, int | None] | None = None,
    rev_sector_n_by: dict[str, int | None] | None = None,
    rev_deepest_quintile_by: dict[str, bool | None] | None = None,
    # Washout/COILED
    washout_2w_by: dict[str, bool | None] | None = None,
    coiled_by: dict[str, dict | None] | None = None,
    extension_by: dict[str, dict | None] | None = None,
    vol_by: dict[str, float | None] | None = None,    # raw annualized vol for tercile
    # 1D/2D oscillators: key = ticker, value = dict with d1_*/d2_* keys
    osc_d12_by: dict[str, dict | None] | None = None,
    # Technicals from china_signals.ashare_tech
    tech_by: dict[str, dict | None] | None = None,
    # Draw-down
    dd_pct_2y_by: dict[str, float | None] | None = None,
    # Executability / limit state
    limit_state_by: dict[str, str | None] | None = None,
    limit_width_by: dict[str, float | None] | None = None,
    chase_veto_by: dict[str, bool | None] | None = None,
    t_plus_one_risk_by: dict[str, bool | None] | None = None,
    # Regime scalars (single value, broadcast to all rows)
    cycle_phase: str | None = None,
    participation_regime: str | None = None,
    participation_risk: str | None = None,
    policy_impulse: str | None = None,
    qvix_z: float | None = None,
    csi300_close: float | None = None,
    # Context / theme
    archetype_by: dict[str, str | None] | None = None,
    above_20d_low_by: dict[str, bool | None] | None = None,
    theme_basket_by: dict[str, str | None] | None = None,
    theme_breadth_pct_by: dict[str, float | None] | None = None,
    theme_member_ret21_rank_by: dict[str, float | None] | None = None,
    block_discount_recent_by: dict[str, bool | None] | None = None,
    lhb_inst_seats_5d_by: dict[str, int | None] | None = None,
) -> list[dict]:
    """Assemble CN snapshot core rows from pre-computed per-ticker dicts.

    PURE function (no I/O, no side effects) — the caller (build_china_library.main)
    supplies all material; this function just assembles rows null-honestly.

    Null honesty: every missing/None field is stored as None.  Never fabricated.

    Low-vol tercile: computed cross-sectionally from vol_by (60d annualized vol).
    Names with None vol are assigned None (liq_unknown / too-short history).

    Returns
    -------
    list[dict] — one dict per ticker, keys matching CN_SNAPSHOT_COLUMNS.
    """
    # Null-safe dict accessors
    rev_3m_by = rev_3m_by or {}
    rev_z_by = rev_z_by or {}
    rev_sector_rank_by = rev_sector_rank_by or {}
    rev_sector_n_by = rev_sector_n_by or {}
    rev_deepest_quintile_by = rev_deepest_quintile_by or {}
    washout_2w_by = washout_2w_by or {}
    coiled_by = coiled_by or {}
    extension_by = extension_by or {}
    vol_by = vol_by or {}
    osc_d12_by = osc_d12_by or {}
    tech_by = tech_by or {}
    dd_pct_2y_by = dd_pct_2y_by or {}
    limit_state_by = limit_state_by or {}
    limit_width_by = limit_width_by or {}
    chase_veto_by = chase_veto_by or {}
    t_plus_one_risk_by = t_plus_one_risk_by or {}
    archetype_by = archetype_by or {}
    above_20d_low_by = above_20d_low_by or {}
    theme_basket_by = theme_basket_by or {}
    theme_breadth_pct_by = theme_breadth_pct_by or {}
    theme_member_ret21_rank_by = theme_member_ret21_rank_by or {}
    block_discount_recent_by = block_discount_recent_by or {}
    lhb_inst_seats_5d_by = lhb_inst_seats_5d_by or {}

    # Cross-sectional low-vol tercile assignment
    # Collect raw vols for all tickers that have one
    vol_vals: list[tuple[str, float]] = [
        (t, vol_by[t]) for t in tickers
        if t in vol_by and vol_by[t] is not None
    ]
    lowvol_label_by: dict[str, str | None] = {t: None for t in tickers}
    if len(vol_vals) >= 3:
        vols_sorted = sorted(vol_vals, key=lambda x: x[1])
        n = len(vols_sorted)
        t1 = n // 3
        t2 = 2 * (n // 3)
        for i, (t, _) in enumerate(vols_sorted):
            lowvol_label_by[t] = "low" if i < t1 else ("high" if i >= t2 else "mid")

    asof_str = str(pd.Timestamp(asof).date())
    rows: list[dict] = []
    for ticker in tickers:
        cb = coiled_by.get(ticker) or {}
        ext = extension_by.get(ticker) or {}
        ext_score, ext_flag = _from_extension(ext)
        tech = tech_by.get(ticker) or {}
        osc = osc_d12_by.get(ticker) or {}
        ls = limit_state_by.get(ticker)

        # fillable: False when sealed_up at fire close (CNPL-R4)
        fillable: bool | None = None
        if ls is not None:
            fillable = bool(ls != "sealed_up")

        row: dict = {
            "asof": asof_str,
            "ticker": ticker,
            "name": name_by.get(ticker),
            "name_zh": name_zh_by.get(ticker),
            "sector": sector_by.get(ticker),
            "board": board_by.get(ticker),
            "close": close_by.get(ticker),
            "turnover_20d": turnover_by.get(ticker),
            # reversal
            "rev_3m": rev_3m_by.get(ticker),
            "rev_z": rev_z_by.get(ticker),
            "rev_3m_sector_rank": rev_sector_rank_by.get(ticker),
            "rev_sector_n": rev_sector_n_by.get(ticker),
            "rev_deepest_quintile": rev_deepest_quintile_by.get(ticker),
            # washout / COILED
            "washout_2w": washout_2w_by.get(ticker),
            "coiled": bool(cb.get("coiled")) if cb else None,
            "star": bool(cb.get("star")) if cb else None,
            "extension_score": ext_score,
            "extension_extended": ext_flag,
            "lowvol_tercile": lowvol_label_by.get(ticker),
            # 1D oscillators (keys already prefixed d1_*)
            "d1_macd": osc.get("d1_macd"),
            "d1_sig": osc.get("d1_sig"),
            "d1_macd_xup_bars": osc.get("d1_macd_xup_bars"),
            "d1_k": osc.get("d1_k"),
            "d1_d": osc.get("d1_d"),
            "d1_kd_xup_bars": osc.get("d1_kd_xup_bars"),
            "d1_from_os": osc.get("d1_from_os"),
            "d1_ob": osc.get("d1_ob"),
            # 2D oscillators
            "d2_macd": osc.get("d2_macd"),
            "d2_sig": osc.get("d2_sig"),
            "d2_macd_xup_bars": osc.get("d2_macd_xup_bars"),
            "d2_k": osc.get("d2_k"),
            "d2_d": osc.get("d2_d"),
            "d2_kd_xup_bars": osc.get("d2_kd_xup_bars"),
            "d2_from_os": osc.get("d2_from_os"),
            "d2_ob": osc.get("d2_ob"),
            # technicals
            "rsi_5": tech.get("rsi5"),
            "rsi_10": tech.get("rsi10"),
            "ret_5d": tech.get("ret_5d"),
            "dist_ma20_z": tech.get("dist_ma20_z"),
            "above_ma120": tech.get("above_ma120"),
            "ma20_slope_up": tech.get("ma20_slope_up"),
            "limit_flag": tech.get("limit_flag"),
            # draw-down
            "dd_pct_2y": dd_pct_2y_by.get(ticker),
            # executability
            "limit_state": ls,
            "limit_width": limit_width_by.get(ticker),
            "fillable": fillable,
            "chase_veto": chase_veto_by.get(ticker),
            "t_plus_one_risk": t_plus_one_risk_by.get(ticker),
            "is_st": is_st_by.get(ticker),
            # regime (broadcast scalars)
            "cycle_phase": cycle_phase,
            "participation_regime": participation_regime,
            "participation_risk": participation_risk,
            "policy_impulse": policy_impulse,
            "qvix_z": qvix_z,
            "csi300_close": csi300_close,
            # context
            "archetype": archetype_by.get(ticker),
            "above_20d_low": above_20d_low_by.get(ticker),
            "theme_basket": theme_basket_by.get(ticker),
            "theme_breadth_pct": theme_breadth_pct_by.get(ticker),
            "theme_member_ret21_rank": theme_member_ret21_rank_by.get(ticker),
            "block_discount_recent": block_discount_recent_by.get(ticker),
            "lhb_inst_seats_5d": lhb_inst_seats_5d_by.get(ticker),
        }

        # Fill any missing CN_SNAPSHOT_COLUMNS key with None (null-honest)
        for col in CN_SNAPSHOT_COLUMNS:
            if col not in row:
                row[col] = None

        rows.append(row)

    return rows
