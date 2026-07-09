"""HK Pick Lab snapshot schema and pure assembly function.

HK parallel of engine/pick_lab/cn_snapshot.py.  Assembles per-ticker frozen
feature rows from the materials available at the end of
build_hk_library.compute_hk_standouts() — all inputs are pre-computed there;
this module is pure (no I/O, no side effects).

Public API
----------
HK_SNAPSHOT_COLUMNS  : list[str] — ordered column list for HK snapshots
build_hk_core_rows(...)          — PURE function; returns list[dict]

Schema note
-----------
HK snapshot columns mirror the CN layout where applicable, with HK-specific
replacements:
  - No board / ST / COILED / limit_state / turnover_20d (CN-only)
  - HK adds: adv63_hkd (liquidity floor), off_high, rsi14, dist_200dma,
    above_200, washout_2w (name-level port from CN — LOG-AND-GRADE),
    last_print_sessions_ago (suspension guard), edge_z (fused HK edge),
    beta, beta_role (global-risk beta overlay), risk_state, peg_state,
    liquidity_regime, vhsi_pctile, hsi_close (top-level regime scalars),
    sessions_since_23d_cross / ret_since_23d_cross (stale-cross diagnostic),
    organ columns (null at producer time; enriched by runner).

Two-pass contract
-----------------
The producer (build_hk_library) writes a PRICE-ONLY first pass — organ columns
(washout_state, adr_gap_pct, cbbc_leverage_state, sb_accum_z, ...) are null.
The runner (build_hk_pick_lab) enriches the frame from the nightly organ
artifacts and re-writes with mode='upsert'. The velocity desk is written twice:
  1. Producer: price-only first pass (ADR/washout conditions null-fail honestly).
  2. Runner: enriched second pass (organ columns populated; desk recomputed).
This two-pass contract is documented here so the runner code can reference it.

Null honesty: every field not available in the caller's scope arrives as None.
A null is NEVER fabricated. The downstream books and graders handle nulls
correctly (hk.py _apply_hk_universe and book funcs all null-safe).

HKPL-R7: organ freshness columns (organ_fresh_washout, organ_fresh_adr,
organ_fresh_cbbc, organ_fresh_narrative, organ_fresh_catalyst, organ_fresh_sb)
are stamped by the runner enrichment; null at producer time (fail-closed
downstream — a missing freshness column is treated as stale in hk.py).
"""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Column list — spec §5 + HK additions                                        #
# --------------------------------------------------------------------------- #

# Identity / price / liquidity
_HK_IDENTITY_COLS = [
    "asof",
    "ticker",
    "name",
    "name_zh",
    "sector",
    "close",
    "adv63_hkd",             # 63-day avg dollar turnover (liquidity floor: ≥ HK$20M)
    "last_print_sessions_ago",  # suspension guard column (>2 → excluded in hk.py)
]

# Price technicals (from compute_hk_standouts enriched rows)
_HK_TECH_COLS = [
    "off_high",              # % below 52-week high (float, negative)
    "rsi14",                 # 14-period RSI (0–100)
    "dist_200dma",           # (price/ma200 - 1), positive = above 200dma
    "above_200",             # bool: price > 200dma
]

# Edge / conviction legs (from hk_stock_signals)
_HK_EDGE_COLS = [
    "edge_z",               # fused HK edge z (A/H + SB + beta-neutral RS)
    "edge_basis",           # list of basis dicts (serialized) — context only
]

# Global-risk beta overlay (per-stock beta classification)
_HK_BETA_COLS = [
    "beta",                 # global-risk beta vs SPY (overnight lag)
    "beta_role",            # "amplifier" | "cushion" | "neutral"
]

# CN-port: washout / oscillator flags (LOG-AND-GRADE; never rank inputs)
_HK_WASHOUT_COLS = [
    "washout_2w",           # bool: 2W StochRSI reclaim from oversold (own-name port)
    "extended",             # bool: extension grade in {stretched, parabolic}
]

# 1D oscillators (from signals_1d.compute_grids — keys d1_*)
_HK_OSC_D1 = [
    "d1_macd",
    "d1_sig",
    "d1_macd_xup_bars",
    "d1_k",
    "d1_d",
    "d1_stoch_xup_bars",    # alias: d1_kd_xup_bars (hk.py books use this name)
    "d1_from_os",
    "d1_ob",
]

# 2D oscillators (from signals_1d.compute_grids on 2B-resampled panel)
_HK_OSC_D2 = [
    "d2_macd",
    "d2_sig",
    "d2_macd_xup_bars",
    "d2_k",
    "d2_d",
    "d2_kd_xup_bars",
    "d2_from_os",
    "d2_ob",
]

# 3D MACD (3-business-day) — used by hklab_1d_blastoff
_HK_OSC_D3 = [
    "d3_macd_xup_bars",     # bars since 3D MACD cross-up (null if no cross within 15)
]

# Stale-cross diagnostic (spec §3 — the "based but didn't blast off" cohort)
_HK_STALE_CROSS_COLS = [
    "sessions_since_23d_cross",   # sessions since the 2D/3D cross (None if no cross)
    "ret_since_23d_cross",        # % return since the 2D/3D cross (None if no cross)
]

# Top-level regime scalars (broadcast from the nightly regime / standouts context)
_HK_REGIME_COLS = [
    "risk_state",             # "Risk-on" | "Risk-off" | "neutral"
    "peg_state",              # HKD peg state (from hk_regime): "weak_side_pressure" | ...
    "liquidity_regime",       # HIBOR/HKMA aggregate-balance regime: "EASY" | "TIGHT" | ...
    "vhsi_pctile",            # VHSI (HK vol fear) percentile vs own history (0–100)
    "hsi_close",              # latest ^HSI close (broadcast scalar, float)
]

# Organ columns — null at producer time; enriched by runner (HKPL-R7)
_HK_ORGAN_COLS = [
    "washout_state",          # "washout_watch" | "ignition_watch" | "pullback_entry_watch" | "chase_risk" | None
    "confluence_count",       # int: count of organ signals present
    "confluence_signals",     # JSON list of signal names (e.g. ["SB_ACCUM", "BUYBACK"])
    "knife_risk",             # bool: falling-knife flag (deep-loser from the hk board)
    "adr_gap_pct",            # float: ADR-implied open gap % (organ: hk_adr_bridge)
    "cbbc_leverage_state",    # "bear_skew" | "bear_skew_froth" | None (organ: hk_cbbc)
    "buyback_flag",           # bool: company buyback in confluence (organ: hk_filing_bus)
    "dilution_flag",          # bool: placement/rights dilution flag (organ: hk_placements)
    "catalyst_days_to",       # int: sessions until next catalyst (organ: hk_catalyst_calendar)
    "attention_shock_z",      # float: narrative attention shock z (organ: hk_narrative)
    "narrative_tone",         # float 0–100: narrative sentiment tone (organ: hk_narrative)
    "sfc_short_pressure_q",   # int 1–4: SFC short-pressure quartile (organ: hk_stock_signals H2a)
    "sb_accum_z",             # float: southbound accumulation z (organ: hk_southbound_stocks)
    "ah_discount_pctile",     # float: A/H discount own-history percentile (organ: hk_ah)
]

# Organ freshness flags — stamped by runner; null at producer time
# A missing or False/null column → organ treated as stale (HKPL-R7 fail-closed)
_HK_FRESHNESS_COLS = [
    "organ_fresh_washout",
    "organ_fresh_adr",
    "organ_fresh_cbbc",
    "organ_fresh_narrative",
    "organ_fresh_catalyst",
    "organ_fresh_sb",
]

HK_SNAPSHOT_COLUMNS: list[str] = (
    _HK_IDENTITY_COLS
    + _HK_TECH_COLS
    + _HK_EDGE_COLS
    + _HK_BETA_COLS
    + _HK_WASHOUT_COLS
    + _HK_OSC_D1
    + _HK_OSC_D2
    + _HK_OSC_D3
    + _HK_STALE_CROSS_COLS
    + _HK_REGIME_COLS
    + _HK_ORGAN_COLS
    + _HK_FRESHNESS_COLS
)


# --------------------------------------------------------------------------- #
# Helper                                                                      #
# --------------------------------------------------------------------------- #

def _safe(v: Any, cast=None) -> Any:
    """Return v cast to `cast` type, or None on any exception (null-honest)."""
    if v is None:
        return None
    try:
        return cast(v) if cast is not None else v
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Pure builder                                                                #
# --------------------------------------------------------------------------- #

def build_hk_core_rows(
    *,
    tickers: list[str],
    asof: str,
    # Identity / liquidity
    close_by: dict[str, float | None],
    adv63_hkd_by: dict[str, float | None],
    name_by: dict[str, str | None],
    name_zh_by: dict[str, str | None],
    sector_by: dict[str, str | None],
    last_print_sessions_ago_by: dict[str, int | None] | None = None,
    # Technicals
    off_high_by: dict[str, float | None] | None = None,
    rsi14_by: dict[str, float | None] | None = None,
    dist_200dma_by: dict[str, float | None] | None = None,
    above_200_by: dict[str, bool | None] | None = None,
    # Edge / conviction
    edge_z_by: dict[str, float | None] | None = None,
    edge_basis_by: dict[str, Any | None] | None = None,
    # Beta overlay
    beta_by: dict[str, float | None] | None = None,
    beta_role_by: dict[str, str | None] | None = None,
    # CN-port washout flags
    washout_2w_by: dict[str, bool | None] | None = None,
    extended_by: dict[str, bool | None] | None = None,
    # 1D/2D/3D oscillators: key = ticker, value = dict with d1_*/d2_* keys
    osc_d123_by: dict[str, dict | None] | None = None,
    # Stale-cross diagnostic
    sessions_since_23d_cross_by: dict[str, int | None] | None = None,
    ret_since_23d_cross_by: dict[str, float | None] | None = None,
    # Regime scalars (broadcast to all rows)
    risk_state: str | None = None,
    peg_state: str | None = None,
    liquidity_regime: str | None = None,
    vhsi_pctile: float | None = None,
    hsi_close: float | None = None,
    # Organ columns (null at producer time; runner fills via upsert)
    # Passed as None here — included in signature for runner use
    # Note: organ columns on the returned rows are always None from this function.
    # The runner enriches via snapshot.write_snapshot mode='upsert'.
) -> list[dict]:
    """Assemble HK snapshot core rows from pre-computed per-ticker dicts.

    PURE function (no I/O, no side effects) — the caller (build_hk_library.
    compute_hk_standouts) supplies all material; this function assembles rows
    null-honestly.

    Null honesty: every missing/None field is stored as None.  Never fabricated.

    Organ columns (washout_state, adr_gap_pct, etc.) are always None here —
    the runner (build_hk_pick_lab) enriches them via write_snapshot upsert.

    Freshness columns (organ_fresh_*) are always None here — runner stamps them
    after enrichment.

    Returns
    -------
    list[dict] — one dict per ticker, keys matching HK_SNAPSHOT_COLUMNS.
    """
    # Null-safe dict accessors
    last_print_sessions_ago_by = last_print_sessions_ago_by or {}
    off_high_by = off_high_by or {}
    rsi14_by = rsi14_by or {}
    dist_200dma_by = dist_200dma_by or {}
    above_200_by = above_200_by or {}
    edge_z_by = edge_z_by or {}
    edge_basis_by = edge_basis_by or {}
    beta_by = beta_by or {}
    beta_role_by = beta_role_by or {}
    washout_2w_by = washout_2w_by or {}
    extended_by = extended_by or {}
    osc_d123_by = osc_d123_by or {}
    sessions_since_23d_cross_by = sessions_since_23d_cross_by or {}
    ret_since_23d_cross_by = ret_since_23d_cross_by or {}

    asof_str = str(pd.Timestamp(asof).date())
    rows: list[dict] = []

    for ticker in tickers:
        osc = osc_d123_by.get(ticker) or {}

        row: dict = {
            # Identity
            "asof": asof_str,
            "ticker": ticker,
            "name": name_by.get(ticker),
            "name_zh": name_zh_by.get(ticker),
            "sector": sector_by.get(ticker),
            "close": close_by.get(ticker),
            "adv63_hkd": adv63_hkd_by.get(ticker),
            "last_print_sessions_ago": last_print_sessions_ago_by.get(ticker),
            # Technicals
            "off_high": off_high_by.get(ticker),
            "rsi14": rsi14_by.get(ticker),
            "dist_200dma": dist_200dma_by.get(ticker),
            "above_200": above_200_by.get(ticker),
            # Edge
            "edge_z": edge_z_by.get(ticker),
            "edge_basis": edge_basis_by.get(ticker),
            # Beta
            "beta": beta_by.get(ticker),
            "beta_role": beta_role_by.get(ticker),
            # CN-port washout flags
            "washout_2w": washout_2w_by.get(ticker),
            "extended": extended_by.get(ticker),
            # 1D oscillators (keys already prefixed d1_*)
            "d1_macd": osc.get("d1_macd"),
            "d1_sig": osc.get("d1_sig"),
            "d1_macd_xup_bars": osc.get("d1_macd_xup_bars"),
            "d1_k": osc.get("d1_k"),
            "d1_d": osc.get("d1_d"),
            "d1_stoch_xup_bars": osc.get("d1_kd_xup_bars"),   # alias: hk.py uses d1_stoch_xup_bars
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
            # 3D MACD (for hklab_1d_blastoff)
            "d3_macd_xup_bars": osc.get("d3_macd_xup_bars"),
            # Stale-cross diagnostic
            "sessions_since_23d_cross": sessions_since_23d_cross_by.get(ticker),
            "ret_since_23d_cross": ret_since_23d_cross_by.get(ticker),
            # Regime scalars (broadcast)
            "risk_state": risk_state,
            "peg_state": peg_state,
            "liquidity_regime": liquidity_regime,
            "vhsi_pctile": vhsi_pctile,
            "hsi_close": hsi_close,
            # Organ columns — always None at producer time (runner enriches)
            "washout_state": None,
            "confluence_count": None,
            "confluence_signals": None,
            "knife_risk": None,
            "adr_gap_pct": None,
            "cbbc_leverage_state": None,
            "buyback_flag": None,
            "dilution_flag": None,
            "catalyst_days_to": None,
            "attention_shock_z": None,
            "narrative_tone": None,
            "sfc_short_pressure_q": None,
            "sb_accum_z": None,
            "ah_discount_pctile": None,
            # Freshness flags — always None at producer time (runner stamps)
            "organ_fresh_washout": None,
            "organ_fresh_adr": None,
            "organ_fresh_cbbc": None,
            "organ_fresh_narrative": None,
            "organ_fresh_catalyst": None,
            "organ_fresh_sb": None,
        }

        # Fill any missing HK_SNAPSHOT_COLUMNS key with None (null-honest)
        for col in HK_SNAPSHOT_COLUMNS:
            if col not in row:
                row[col] = None

        rows.append(row)

    return rows
