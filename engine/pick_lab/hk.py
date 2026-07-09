"""HK Pick Lab candidate book evaluators (hk.py).

run_book_hk(book, snap) -> dict   {engine_id, picks, disabled_stale, n_picks}

Implements all 20 HK constructions from spec §3.  Pure functions — no side
effects, no I/O, no randomness (except hklab_random_ctrl, seeded from
sha256(engine_id+asof) per HKPL-R2 reproducibility).

Universe screens applied before every book:
  - suspension_guard: names with no print in the last 2 sessions excluded
    (snap column: last_print_sessions_ago; null → pass with liq_unknown flag)
  - liquidity floor: adv63_hkd ≥ HK$20M (null → liq_unknown flag, passes)

Null semantics: a null condition value FAILS the condition unless spec
explicitly says 'or null' passes (e.g. 3D not-yet-crossed = null passes).

HK standing kills (spec §8):
  - NO residual/selection momentum ranks
  - NO southbound delta-ranking (SB_ACCUM organ confluence signal = legal)
  - NO COILED books
  - NO Connect-inclusion event books

HKPL-R7 (organ staleness): each organ-dependent book checks a per-organ
freshness indicator.  When an organ's data is staler than 2 HK sessions the
book returns disabled_stale=True with zero picks (fail-closed).
The freshness indicator is a column in the snapshot: organ_fresh_<organ_tag>.
Expected columns: organ_fresh_washout, organ_fresh_adr, organ_fresh_cbbc,
organ_fresh_narrative, organ_fresh_catalyst, organ_fresh_sb.

HK snapshot columns assumed present (producer emits; organ enrichment fills
organ fields; some may be null):
  Core: ticker, name, name_zh, sector, close, adv63_hkd, off_high,
        rsi14, dist_200dma, above_200, washout_2w, extended, edge_z,
        beta, beta_role, label, tier,
        d1_macd_xup_bars, d1_stoch_xup_bars (StochRSI k×d cross sessions),
        d1_from_os, d3_macd_xup_bars, sessions_since_23d_cross,
        ret_since_23d_cross, last_print_sessions_ago.
  Organ: washout_state, confluence_count, confluence_signals (list/JSON),
         knife_risk, adr_gap_pct, cbbc_leverage_state, buyback_flag,
         dilution_flag, catalyst_days_to, attention_shock_z, narrative_tone,
         sfc_short_pressure_q, sb_accum_z, ah_discount_pctile.
  Freshness: organ_fresh_washout, organ_fresh_adr, organ_fresh_cbbc,
             organ_fresh_narrative, organ_fresh_catalyst, organ_fresh_sb.
  Top-level (repeated per row): risk_state, peg_state, liquidity_regime,
                                 vhsi_pctile, hsi_close.
"""
from __future__ import annotations

import hashlib
import json
import logging

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ------------------------------------------------------------------ constants --

_LIQ_ADV_MIN_HK = 20e6   # HK$20M 63d ADV floor (spec §3 defaults)
_SUSPENSION_SESSIONS = 2  # no print in last N sessions → excluded


# --------------------------------------------------------------------------- #
# Universe screener
# --------------------------------------------------------------------------- #

def _apply_hk_universe(df: pd.DataFrame) -> pd.DataFrame:
    """Apply HK universe screens.

    Screens (applied in order):
      1. suspension guard: last_print_sessions_ago > 2 → excluded
         (null → passes, flagged liq_unknown; spec §3 "no print in last 2 sessions")
      2. liquidity floor: adv63_hkd ≥ HK$20M
         (null → passes, flagged liq_unknown)
    """
    df = df.copy()

    # 1. Suspension guard
    lp = df.get("last_print_sessions_ago")
    if lp is not None:
        # Null passes (unknown — don't exclude); present value must be ≤ 2
        suspended = lp.gt(_SUSPENSION_SESSIONS).fillna(False)
        df = df[~suspended]
    if df.empty:
        return df

    # 2. Liquidity floor
    adv = df.get("adv63_hkd")
    if adv is None:
        df["liq_unknown"] = True
    else:
        null_mask = adv.isna()
        # Combine existing liq_unknown if already set, else derive from null_mask
        existing = df.get("liq_unknown", pd.Series(False, index=df.index)).fillna(False)
        df["liq_unknown"] = existing | null_mask
        adv_fail = (~null_mask) & adv.lt(_LIQ_ADV_MIN_HK).fillna(False)
        df = df[~adv_fail]

    return df.copy()


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _col(df: pd.DataFrame, col: str, idx) -> object:
    """Safe column access; returns None if column missing or value NaN."""
    if col not in df.columns:
        return None
    v = df.at[idx, col]
    return None if pd.isna(v) else v


def _pick(df: pd.DataFrame, ticker: str, rank: int, why: list[str],
          features: dict, is_avoid: bool = False) -> dict:
    """Build a HK pick dict with required fields."""
    row = df.loc[ticker]
    return {
        "ticker": ticker,
        "rank": rank,
        "close": _col(df, "close", ticker),
        "sector": _col(df, "sector", ticker),
        "name": _col(df, "name", ticker),
        "name_zh": _col(df, "name_zh", ticker),
        "liq_unknown": bool(row.get("liq_unknown", False)),
        "is_avoid": is_avoid,
        "why": why,
        "features": features,
        "authority": "display_only",
    }


def _organ_fresh(df: pd.DataFrame, organ_tag: str) -> bool:
    """Return True when the organ freshness column is present and indicates fresh data.

    organ_tag: e.g. 'washout', 'adr', 'cbbc', 'narrative', 'catalyst', 'sb'
    Column name: organ_fresh_<organ_tag>  (bool: True=fresh, False=stale/absent)
    When the column is missing entirely → treat as stale (fail-closed, HKPL-R7).
    """
    col = f"organ_fresh_{organ_tag}"
    if col not in df.columns:
        return False  # missing column = stale (fail-closed)
    # Majority vote: if any row is fresh we consider the organ available
    # (snapshot has repeated top-level organ stamps)
    vals = df[col].dropna()
    if vals.empty:
        return False
    return bool(vals.eq(True).any())


def _confluence_has(df: pd.DataFrame, ticker: str, signal: str) -> bool:
    """Check whether signal appears in the confluence_signals list/JSON for a row."""
    if "confluence_signals" not in df.columns:
        return False
    raw = df.at[ticker, "confluence_signals"]
    if pd.isna(raw) if not isinstance(raw, (list, str)) else False:
        return False
    if isinstance(raw, list):
        return signal in raw
    if isinstance(raw, str):
        try:
            lst = json.loads(raw)
            return signal in lst
        except (json.JSONDecodeError, TypeError):
            return signal in raw
    return False


def _any_washout(df: pd.DataFrame, ticker: str) -> bool:
    """True when washout_state is any non-null, non-chase_risk washout state."""
    ws = _col(df, "washout_state", ticker)
    if ws is None:
        return False
    return ws in ("washout_watch", "ignition_watch", "pullback_entry_watch")


# --------------------------------------------------------------------------- #
# Family A — 1D velocity
# --------------------------------------------------------------------------- #

def _book_hk_1d_pure(df: pd.DataFrame, book: dict) -> list[dict]:
    """hklab_1d_pure — 1D RSI-MACD cross-up ≤2 AND StochRSI k×d cross ≤8 AND from_os AND rsi14<70."""
    cfg = book["config"]
    mask = (
        df.get("d1_macd_xup_bars", pd.Series(np.nan, index=df.index)).le(
            cfg["d1_macd_xup_bars_max"]
        ).fillna(False)
        & df.get("d1_stoch_xup_bars", pd.Series(np.nan, index=df.index)).le(
            cfg["d1_stoch_xup_bars_max"]
        ).fillna(False)
        & df.get("d1_from_os", pd.Series(False, index=df.index)).eq(True).fillna(False)
        & df.get("rsi14", pd.Series(np.nan, index=df.index)).lt(cfg["rsi14_max"]).fillna(False)
    )
    sub = df[mask].copy()
    if sub.empty:
        return []
    # rank by edge_z descending
    if "edge_z" in sub.columns:
        sub = sub.sort_values("edge_z", ascending=False, na_position="last")
    sub = sub.head(book["max_picks"])
    picks = []
    for rank, (ticker, _) in enumerate(sub.iterrows(), 1):
        picks.append(_pick(df, ticker, rank, ["1D MACD✚≤2", "1D StochRSI✚≤8", "from_OS", "RSI14<70"], {
            "d1_macd_xup_bars": _col(df, "d1_macd_xup_bars", ticker),
            "d1_stoch_xup_bars": _col(df, "d1_stoch_xup_bars", ticker),
            "rsi14": _col(df, "rsi14", ticker),
            "edge_z": _col(df, "edge_z", ticker),
        }))
    return picks


def _book_hk_1d_ignition(df: pd.DataFrame, book: dict) -> tuple[list[dict], bool]:
    """hklab_1d_ignition — 1D MACD cross ≤3 AND washout_state in {ignition_watch, pullback_entry_watch}.

    Organ-dependent (washout); returns (picks, disabled_stale).
    """
    if not _organ_fresh(df, "washout"):
        return [], True  # HKPL-R7 fail-closed

    cfg = book["config"]
    mask = (
        df.get("d1_macd_xup_bars", pd.Series(np.nan, index=df.index)).le(
            cfg["d1_macd_xup_bars_max"]
        ).fillna(False)
        & df.get("washout_state", pd.Series(None, index=df.index)).isin(
            cfg["washout_states_allowed"]
        ).fillna(False)
    )
    sub = df[mask].copy()
    if sub.empty:
        return [], False
    if "confluence_count" in sub.columns:
        sub = sub.sort_values("confluence_count", ascending=False, na_position="last")
    sub = sub.head(book["max_picks"])
    picks = []
    for rank, (ticker, _) in enumerate(sub.iterrows(), 1):
        picks.append(_pick(df, ticker, rank, ["1D MACD✚≤3", "ignition/pullback-watch✓"], {
            "d1_macd_xup_bars": _col(df, "d1_macd_xup_bars", ticker),
            "washout_state": _col(df, "washout_state", ticker),
            "confluence_count": _col(df, "confluence_count", ticker),
        }))
    return picks, False


def _book_hk_1d_adr(df: pd.DataFrame, book: dict) -> tuple[list[dict], bool]:
    """hklab_1d_adr — 1D MACD cross ≤2 AND ADR implied_open_gap_pct ≥ +0.5.

    Organ-dependent (ADR bridge); returns (picks, disabled_stale).
    """
    if not _organ_fresh(df, "adr"):
        return [], True  # HKPL-R7 fail-closed

    cfg = book["config"]
    mask = (
        df.get("d1_macd_xup_bars", pd.Series(np.nan, index=df.index)).le(
            cfg["d1_macd_xup_bars_max"]
        ).fillna(False)
        & df.get("adr_gap_pct", pd.Series(np.nan, index=df.index)).ge(
            cfg["adr_gap_pct_min"]
        ).fillna(False)
    )
    sub = df[mask].copy()
    if sub.empty:
        return [], False
    if "adr_gap_pct" in sub.columns:
        sub = sub.sort_values("adr_gap_pct", ascending=False, na_position="last")
    sub = sub.head(book["max_picks"])
    picks = []
    for rank, (ticker, _) in enumerate(sub.iterrows(), 1):
        picks.append(_pick(df, ticker, rank, ["1D MACD✚≤2", "ADR gap≥+0.5%"], {
            "d1_macd_xup_bars": _col(df, "d1_macd_xup_bars", ticker),
            "adr_gap_pct": _col(df, "adr_gap_pct", ticker),
        }))
    return picks, False


def _book_hk_1d_blastoff(df: pd.DataFrame, book: dict) -> list[dict]:
    """hklab_1d_blastoff — 1D MACD cross ≤3 AND 3D MACD not yet crossed AND above 200dma."""
    # 1D MACD cross ≤3
    mask = df.get("d1_macd_xup_bars", pd.Series(np.nan, index=df.index)).le(3).fillna(False)
    # 3D MACD NOT yet crossed (null = never crossed within window → passes, spec §3 book 4)
    if "d3_macd_xup_bars" in df.columns:
        d3_not_crossed = df["d3_macd_xup_bars"].isna()
        mask = mask & d3_not_crossed
    # above 200dma
    mask = mask & df.get("above_200", pd.Series(False, index=df.index)).eq(True).fillna(False)
    sub = df[mask].copy()
    if sub.empty:
        return []
    # rank by 5d return — use off_high inverse as proxy when explicit ret_5d absent
    if "ret_since_23d_cross" in sub.columns:
        sub = sub.sort_values("ret_since_23d_cross", ascending=False, na_position="last")
    else:
        sub = sub.sort_values("d1_macd_xup_bars", ascending=True, na_position="last")
    sub = sub.head(book["max_picks"])
    picks = []
    for rank, (ticker, _) in enumerate(sub.iterrows(), 1):
        picks.append(_pick(df, ticker, rank, ["1D MACD✚≤3", "3D not yet crossed", "above 200dma"], {
            "d1_macd_xup_bars": _col(df, "d1_macd_xup_bars", ticker),
            "d3_macd_xup_bars": _col(df, "d3_macd_xup_bars", ticker),
            "above_200": _col(df, "above_200", ticker),
        }))
    return picks


def _book_hk_1d_regime(df: pd.DataFrame, book: dict) -> list[dict]:
    """hklab_1d_regime — 1D MACD cross ≤3 AND risk_state=Risk-on AND peg not weak-side pressure."""
    cfg = book["config"]
    mask = (
        df.get("d1_macd_xup_bars", pd.Series(np.nan, index=df.index)).le(
            cfg["d1_macd_xup_bars_max"]
        ).fillna(False)
        & df.get("risk_state", pd.Series(None, index=df.index)).eq(
            cfg["risk_state_required"]
        ).fillna(False)
    )
    # Exclude peg weak-side pressure
    peg_blocked = cfg.get("peg_state_blocked")
    if peg_blocked:
        mask = mask & df.get("peg_state", pd.Series(None, index=df.index)).ne(
            peg_blocked
        ).fillna(True)
    sub = df[mask].copy()
    if sub.empty:
        return []
    if "edge_z" in sub.columns:
        sub = sub.sort_values("edge_z", ascending=False, na_position="last")
    sub = sub.head(book["max_picks"])
    picks = []
    for rank, (ticker, _) in enumerate(sub.iterrows(), 1):
        picks.append(_pick(df, ticker, rank, ["1D MACD✚≤3", "Risk-on✓", "peg ok"], {
            "d1_macd_xup_bars": _col(df, "d1_macd_xup_bars", ticker),
            "risk_state": _col(df, "risk_state", ticker),
            "peg_state": _col(df, "peg_state", ticker),
            "edge_z": _col(df, "edge_z", ticker),
        }))
    return picks


# --------------------------------------------------------------------------- #
# Family B — washout/ignition (organ-integrated)
# --------------------------------------------------------------------------- #

def _book_hk_washout_ignite(df: pd.DataFrame, book: dict) -> tuple[list[dict], bool]:
    """hklab_washout_ignite — washout_state = ignition_watch (strongest state).

    Organ-dependent (washout); returns (picks, disabled_stale).
    """
    if not _organ_fresh(df, "washout"):
        return [], True

    cfg = book["config"]
    mask = df.get("washout_state", pd.Series(None, index=df.index)).isin(
        cfg["washout_states_allowed"]
    ).fillna(False)
    sub = df[mask].copy()
    if sub.empty:
        return [], False
    if "confluence_count" in sub.columns:
        sub = sub.sort_values("confluence_count", ascending=False, na_position="last")
    sub = sub.head(book["max_picks"])
    picks = []
    for rank, (ticker, _) in enumerate(sub.iterrows(), 1):
        picks.append(_pick(df, ticker, rank, ["ignition_watch✓", "organ-state"], {
            "washout_state": _col(df, "washout_state", ticker),
            "confluence_count": _col(df, "confluence_count", ticker),
        }))
    return picks, False


def _book_hk_washout_sb(df: pd.DataFrame, book: dict) -> tuple[list[dict], bool]:
    """hklab_washout_sb — washout state AND SB_ACCUM in confluence_signals.

    Organ-dependent (washout + SB); returns (picks, disabled_stale).
    SB consumed as organ confluence signal level-turn — NOT Δ-ranker (HKPL §8).
    """
    if not (_organ_fresh(df, "washout") and _organ_fresh(df, "sb")):
        return [], True

    cfg = book["config"]
    mask = df.get("washout_state", pd.Series(None, index=df.index)).isin(
        cfg["washout_states_allowed"]
    ).fillna(False)

    # Filter: SB_ACCUM must appear in confluence_signals
    signal = cfg["confluence_signal_required"]
    sb_ok = pd.Series(False, index=df.index)
    for ticker in df[mask].index:
        if _confluence_has(df, ticker, signal):
            sb_ok.at[ticker] = True
    mask = mask & sb_ok

    sub = df[mask].copy()
    if sub.empty:
        return [], False
    if "sb_accum_z" in sub.columns:
        sub = sub.sort_values("sb_accum_z", ascending=False, na_position="last")
    sub = sub.head(book["max_picks"])
    picks = []
    for rank, (ticker, _) in enumerate(sub.iterrows(), 1):
        picks.append(_pick(df, ticker, rank, ["washout/ignition✓", "SB_ACCUM signal✓"], {
            "washout_state": _col(df, "washout_state", ticker),
            "sb_accum_z": _col(df, "sb_accum_z", ticker),
            "confluence_signals": _col(df, "confluence_signals", ticker),
        }))
    return picks, False


def _book_hk_washout_buyback(df: pd.DataFrame, book: dict) -> tuple[list[dict], bool]:
    """hklab_washout_buyback — any washout state AND BUYBACK in confluence_signals.

    Organ-dependent (washout); returns (picks, disabled_stale).
    """
    if not _organ_fresh(df, "washout"):
        return [], True

    # "any washout state" = washout_watch, ignition_watch, or pullback_entry_watch
    all_washout_states = ["washout_watch", "ignition_watch", "pullback_entry_watch"]
    mask = df.get("washout_state", pd.Series(None, index=df.index)).isin(
        all_washout_states
    ).fillna(False)

    signal = book["config"]["confluence_signal_required"]
    bb_ok = pd.Series(False, index=df.index)
    for ticker in df[mask].index:
        if _confluence_has(df, ticker, signal):
            bb_ok.at[ticker] = True
    mask = mask & bb_ok

    sub = df[mask].copy()
    if sub.empty:
        return [], False
    if "confluence_count" in sub.columns:
        sub = sub.sort_values("confluence_count", ascending=False, na_position="last")
    sub = sub.head(book["max_picks"])
    picks = []
    for rank, (ticker, _) in enumerate(sub.iterrows(), 1):
        picks.append(_pick(df, ticker, rank, ["any washout✓", "BUYBACK signal✓"], {
            "washout_state": _col(df, "washout_state", ticker),
            "confluence_count": _col(df, "confluence_count", ticker),
            "buyback_flag": _col(df, "buyback_flag", ticker),
        }))
    return picks, False


def _book_hk_pullback_entry(df: pd.DataFrame, book: dict) -> tuple[list[dict], bool]:
    """hklab_pullback_entry — state = pullback_entry_watch (second-chance re-test entry).

    Organ-dependent (washout); returns (picks, disabled_stale).
    """
    if not _organ_fresh(df, "washout"):
        return [], True

    cfg = book["config"]
    mask = df.get("washout_state", pd.Series(None, index=df.index)).isin(
        cfg["washout_states_allowed"]
    ).fillna(False)
    sub = df[mask].copy()
    if sub.empty:
        return [], False
    # rank by RSI reclaim depth: low rsi14 = deeper reclaim
    if "rsi14" in sub.columns:
        sub = sub.sort_values("rsi14", ascending=True, na_position="last")
    sub = sub.head(book["max_picks"])
    picks = []
    for rank, (ticker, _) in enumerate(sub.iterrows(), 1):
        picks.append(_pick(df, ticker, rank, ["pullback_entry_watch✓", "second-chance"], {
            "washout_state": _col(df, "washout_state", ticker),
            "rsi14": _col(df, "rsi14", ticker),
        }))
    return picks, False


def _book_hk_knife_avoid(df: pd.DataFrame, book: dict) -> list[dict]:
    """hklab_knife_avoid — INVERSE: knife_risk=True.

    Expected NEGATIVE 21d excess (avoid-accuracy book).
    """
    mask = df.get("knife_risk", pd.Series(False, index=df.index)).eq(True).fillna(False)
    sub = df[mask].copy()
    if sub.empty:
        return []
    # rank by drawdown depth descending (worst knife first)
    if "off_high" in sub.columns:
        sub = sub.sort_values("off_high", ascending=True, na_position="last")  # off_high = pct below high
    sub = sub.head(book["max_picks"])
    picks = []
    for rank, (ticker, _) in enumerate(sub.iterrows(), 1):
        picks.append(_pick(df, ticker, rank, ["AVOID/inverse", "knife_risk✓"], {
            "knife_risk": _col(df, "knife_risk", ticker),
            "off_high": _col(df, "off_high", ticker),
            "rsi14": _col(df, "rsi14", ticker),
        }, is_avoid=True))
    return picks


# --------------------------------------------------------------------------- #
# Family C — HK-unique structure
# --------------------------------------------------------------------------- #

def _book_hk_cbbc_fuel(df: pd.DataFrame, book: dict) -> tuple[list[dict], bool]:
    """hklab_cbbc_fuel — CBBC bear_skew/froth state AND price > 20dma.

    Organ-dependent (CBBC); returns (picks, disabled_stale).
    Leverage-mechanics construction — not price-derived momentum (spec §8).
    """
    if not _organ_fresh(df, "cbbc"):
        return [], True

    cfg = book["config"]
    mask = df.get("cbbc_leverage_state", pd.Series(None, index=df.index)).isin(
        cfg["cbbc_states_allowed"]
    ).fillna(False)
    # price > 20dma — use dist_200dma as above proxy; if cbbc_above_20dma column exists use it
    if "cbbc_above_20dma" in df.columns:
        above_20 = df["cbbc_above_20dma"].eq(True).fillna(False)
    elif "dist_200dma" in df.columns:
        # dist_200dma positive means above 200dma; use as coarse proxy for above 20dma
        above_20 = df["dist_200dma"].gt(0).fillna(False)
    else:
        above_20 = pd.Series(True, index=df.index)  # missing → pass (null-honest)
    mask = mask & above_20

    sub = df[mask].copy()
    if sub.empty:
        return [], False
    # rank by bear skew ratio — proxy: use cbbc_leverage_state=bear_skew_froth first
    if "cbbc_leverage_state" in sub.columns:
        # bear_skew_froth is stronger than bear_skew
        sub["_skew_rank"] = sub["cbbc_leverage_state"].map(
            {"bear_skew_froth": 2, "bear_skew": 1}
        ).fillna(0)
        sub = sub.sort_values("_skew_rank", ascending=False)
    sub = sub.head(book["max_picks"])
    picks = []
    for rank, (ticker, _) in enumerate(sub.iterrows(), 1):
        picks.append(_pick(df, ticker, rank, ["CBBC bear-skew fuel", "leverage-mechanics"], {
            "cbbc_leverage_state": _col(df, "cbbc_leverage_state", ticker),
            "dist_200dma": _col(df, "dist_200dma", ticker),
        }))
    return picks, False


def _book_hk_ah_value(df: pd.DataFrame, book: dict) -> list[dict]:
    """hklab_ah_value — Top A/H-discount own-history percentile names.

    No organ freshness gate for A/H (the A/H program computes this nightly
    from its own store; null → excluded from the book, null-honest).
    """
    col = "ah_discount_pctile"
    if col not in df.columns or df[col].isna().all():
        return []  # no A/H data available

    sub = df[df[col].notna()].copy()
    if sub.empty:
        return []
    # rank by ah_discount_pctile descending (highest percentile = most discounted vs history)
    sub = sub.sort_values(col, ascending=False, na_position="last").head(book["max_picks"])
    picks = []
    for rank, (ticker, _) in enumerate(sub.iterrows(), 1):
        picks.append(_pick(df, ticker, rank, ["A/H discount pctile✓", "H3 value"], {
            "ah_discount_pctile": _col(df, "ah_discount_pctile", ticker),
        }))
    return picks


def _book_hk_short_squeeze(df: pd.DataFrame, book: dict) -> tuple[list[dict], bool]:
    """hklab_short_squeeze — SFC short-pressure top quartile AND RSI reclaim 30-50.

    Organ-dependent (SFC shorts as organ); returns (picks, disabled_stale).
    """
    if not _organ_fresh(df, "sb"):  # SFC shorts share the sb organ freshness tag
        return [], True

    cfg = book["config"]
    # SFC short-pressure: quartile ≥ cfg min (1=low, 4=top, spec top quartile)
    mask = df.get("sfc_short_pressure_q", pd.Series(np.nan, index=df.index)).ge(
        cfg["sfc_short_pressure_quartile_min"]
    ).fillna(False)
    # RSI reclaim through 30-50 band: rsi14 in [30, 50]
    rsi14 = df.get("rsi14", pd.Series(np.nan, index=df.index))
    rsi_ok = rsi14.ge(cfg["rsi14_reclaim_band_lo"]).fillna(False) & rsi14.le(
        cfg["rsi14_reclaim_band_hi"]
    ).fillna(False)
    mask = mask & rsi_ok

    sub = df[mask].copy()
    if sub.empty:
        return [], False
    if "sfc_short_pressure_q" in sub.columns:
        sub = sub.sort_values("sfc_short_pressure_q", ascending=False, na_position="last")
    sub = sub.head(book["max_picks"])
    picks = []
    for rank, (ticker, _) in enumerate(sub.iterrows(), 1):
        picks.append(_pick(df, ticker, rank, ["SFC short top Q✓", "RSI 30-50 reclaim✓"], {
            "sfc_short_pressure_q": _col(df, "sfc_short_pressure_q", ticker),
            "rsi14": _col(df, "rsi14", ticker),
        }))
    return picks, False


def _book_hk_catalyst_narrative(df: pd.DataFrame, book: dict) -> tuple[list[dict], bool]:
    """hklab_catalyst_narrative — catalyst ≤5 sessions AND shock_z≥1.5 AND tone≥55 AND rsi14<70.

    Organ-dependent (catalyst + narrative); returns (picks, disabled_stale).
    """
    if not (_organ_fresh(df, "catalyst") and _organ_fresh(df, "narrative")):
        return [], True

    cfg = book["config"]
    mask = (
        df.get("catalyst_days_to", pd.Series(np.nan, index=df.index)).le(
            cfg["catalyst_days_to_max"]
        ).fillna(False)
        & df.get("attention_shock_z", pd.Series(np.nan, index=df.index)).ge(
            cfg["attention_shock_z_min"]
        ).fillna(False)
        & df.get("narrative_tone", pd.Series(np.nan, index=df.index)).ge(
            cfg["narrative_tone_min"]
        ).fillna(False)
        & df.get("rsi14", pd.Series(np.nan, index=df.index)).lt(cfg["rsi14_max"]).fillna(False)
    )
    sub = df[mask].copy()
    if sub.empty:
        return [], False
    if "attention_shock_z" in sub.columns:
        sub = sub.sort_values("attention_shock_z", ascending=False, na_position="last")
    sub = sub.head(book["max_picks"])
    picks = []
    for rank, (ticker, _) in enumerate(sub.iterrows(), 1):
        picks.append(_pick(df, ticker, rank, ["catalyst≤5d✓", "shock_z≥1.5✓", "tone≥55✓", "RSI14<70"], {
            "catalyst_days_to": _col(df, "catalyst_days_to", ticker),
            "attention_shock_z": _col(df, "attention_shock_z", ticker),
            "narrative_tone": _col(df, "narrative_tone", ticker),
            "rsi14": _col(df, "rsi14", ticker),
        }))
    return picks, False


# --------------------------------------------------------------------------- #
# Family D — beta/regime
# --------------------------------------------------------------------------- #

def _book_hk_beta_amplifier(df: pd.DataFrame, book: dict) -> list[dict]:
    """hklab_beta_amplifier — Risk-on AND beta role=amplifier AND above 200dma."""
    cfg = book["config"]
    mask = (
        df.get("risk_state", pd.Series(None, index=df.index)).eq(
            cfg["risk_state_required"]
        ).fillna(False)
        & df.get("beta_role", pd.Series(None, index=df.index)).eq(
            cfg["beta_role_required"]
        ).fillna(False)
        & df.get("above_200", pd.Series(False, index=df.index)).eq(True).fillna(False)
    )
    sub = df[mask].copy()
    if sub.empty:
        return []
    if "beta" in sub.columns:
        sub = sub.sort_values("beta", ascending=False, na_position="last")
    sub = sub.head(book["max_picks"])
    picks = []
    for rank, (ticker, _) in enumerate(sub.iterrows(), 1):
        picks.append(_pick(df, ticker, rank, ["Risk-on✓", "amplifier role✓", "above 200dma"], {
            "risk_state": _col(df, "risk_state", ticker),
            "beta_role": _col(df, "beta_role", ticker),
            "beta": _col(df, "beta", ticker),
            "above_200": _col(df, "above_200", ticker),
        }))
    return picks


def _book_hk_beta_cushion(df: pd.DataFrame, book: dict) -> list[dict]:
    """hklab_beta_cushion — Risk-off AND beta role=cushion."""
    cfg = book["config"]
    mask = (
        df.get("risk_state", pd.Series(None, index=df.index)).eq(
            cfg["risk_state_required"]
        ).fillna(False)
        & df.get("beta_role", pd.Series(None, index=df.index)).eq(
            cfg["beta_role_required"]
        ).fillna(False)
    )
    sub = df[mask].copy()
    if sub.empty:
        return []
    # rank by inverse beta: lowest beta first (most defensive)
    if "beta" in sub.columns:
        sub = sub.sort_values("beta", ascending=True, na_position="last")
    sub = sub.head(book["max_picks"])
    picks = []
    for rank, (ticker, _) in enumerate(sub.iterrows(), 1):
        picks.append(_pick(df, ticker, rank, ["Risk-off✓", "cushion role✓", "defensive"], {
            "risk_state": _col(df, "risk_state", ticker),
            "beta_role": _col(df, "beta_role", ticker),
            "beta": _col(df, "beta", ticker),
        }))
    return picks


def _book_hk_hibor_easy(df: pd.DataFrame, book: dict) -> list[dict]:
    """hklab_hibor_easy — liquidity_regime=EASY AND washout_2w.

    No organ gate for liquidity_regime (comes from hk_regime scalar, always fresh).
    """
    cfg = book["config"]
    mask = (
        df.get("liquidity_regime", pd.Series(None, index=df.index)).eq(
            cfg["liquidity_regime_required"]
        ).fillna(False)
        & df.get("washout_2w", pd.Series(False, index=df.index)).eq(True).fillna(False)
    )
    sub = df[mask].copy()
    if sub.empty:
        return []
    # rank by washout depth: off_high ascending (lowest = deepest below high = most washed out)
    if "off_high" in sub.columns:
        sub = sub.sort_values("off_high", ascending=True, na_position="last")
    sub = sub.head(book["max_picks"])
    picks = []
    for rank, (ticker, _) in enumerate(sub.iterrows(), 1):
        picks.append(_pick(df, ticker, rank, ["EASY liquidity✓", "washout_2w✓"], {
            "liquidity_regime": _col(df, "liquidity_regime", ticker),
            "washout_2w": _col(df, "washout_2w", ticker),
            "off_high": _col(df, "off_high", ticker),
        }))
    return picks


# --------------------------------------------------------------------------- #
# Family E — ablations + controls
# --------------------------------------------------------------------------- #

def _book_hk_flagship_nogate(df: pd.DataFrame, book: dict) -> list[dict]:
    """hklab_flagship_nogate — Top-8 by edge_z IGNORING the signal_gate grouping (gate ablation)."""
    if "edge_z" in df.columns:
        sub = df.sort_values("edge_z", ascending=False, na_position="last").head(book["max_picks"])
    else:
        sub = df.head(book["max_picks"])
    picks = []
    for rank, (ticker, _) in enumerate(sub.iterrows(), 1):
        picks.append(_pick(df, ticker, rank, ["edge_z no-gate ablation"], {
            "edge_z": _col(df, "edge_z", ticker),
            "tier": _col(df, "tier", ticker),
        }))
    return picks


def _book_hk_chase_avoid(df: pd.DataFrame, book: dict) -> tuple[list[dict], bool]:
    """hklab_chase_avoid — INVERSE: washout_state=chase_risk (RSI≥70 gapped names).

    Organ-dependent (washout); returns (picks, disabled_stale).
    Expected NEGATIVE 21d excess (avoid-accuracy book).
    """
    if not _organ_fresh(df, "washout"):
        return [], True

    cfg = book["config"]
    mask = df.get("washout_state", pd.Series(None, index=df.index)).isin(
        cfg["washout_states_required"]
    ).fillna(False)
    sub = df[mask].copy()
    if sub.empty:
        return [], False
    # rank by rsi14 descending (highest RSI = most extended/chase-risky first)
    if "rsi14" in sub.columns:
        sub = sub.sort_values("rsi14", ascending=False, na_position="last")
    sub = sub.head(book["max_picks"])
    picks = []
    for rank, (ticker, _) in enumerate(sub.iterrows(), 1):
        picks.append(_pick(df, ticker, rank, ["AVOID/inverse", "chase_risk state✓", "RSI≥70 gapped"], {
            "washout_state": _col(df, "washout_state", ticker),
            "rsi14": _col(df, "rsi14", ticker),
            "extended": _col(df, "extended", ticker),
        }, is_avoid=True))
    return picks, False


def _book_hk_random_ctrl(df: pd.DataFrame, book: dict) -> list[dict]:
    """hklab_random_ctrl — 8 deterministic-random liquid HK names; seed sha256(engine_id+asof)."""
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
        picks.append(_pick(df, ticker, rank, ["HK random-ctrl"], {
            "seed": seed_str,
        }))
    return picks


# --------------------------------------------------------------------------- #
# Dispatch table
# --------------------------------------------------------------------------- #

# Books returning (picks, disabled_stale) tuple
_ORGAN_BOOKS = frozenset({
    "hklab_1d_ignition",
    "hklab_1d_adr",
    "hklab_washout_ignite",
    "hklab_washout_sb",
    "hklab_washout_buyback",
    "hklab_pullback_entry",
    "hklab_cbbc_fuel",
    "hklab_short_squeeze",
    "hklab_catalyst_narrative",
    "hklab_chase_avoid",
})

_BOOK_FUNCS_HK: dict[str, object] = {
    "hklab_1d_pure":            _book_hk_1d_pure,
    "hklab_1d_ignition":        _book_hk_1d_ignition,         # organ
    "hklab_1d_adr":             _book_hk_1d_adr,              # organ
    "hklab_1d_blastoff":        _book_hk_1d_blastoff,
    "hklab_1d_regime":          _book_hk_1d_regime,
    "hklab_washout_ignite":     _book_hk_washout_ignite,      # organ
    "hklab_washout_sb":         _book_hk_washout_sb,          # organ
    "hklab_washout_buyback":    _book_hk_washout_buyback,     # organ
    "hklab_pullback_entry":     _book_hk_pullback_entry,      # organ
    "hklab_knife_avoid":        _book_hk_knife_avoid,
    "hklab_cbbc_fuel":          _book_hk_cbbc_fuel,           # organ
    "hklab_ah_value":           _book_hk_ah_value,
    "hklab_short_squeeze":      _book_hk_short_squeeze,       # organ
    "hklab_catalyst_narrative": _book_hk_catalyst_narrative,  # organ
    "hklab_beta_amplifier":     _book_hk_beta_amplifier,
    "hklab_beta_cushion":       _book_hk_beta_cushion,
    "hklab_hibor_easy":         _book_hk_hibor_easy,
    "hklab_flagship_nogate":    _book_hk_flagship_nogate,
    "hklab_chase_avoid":        _book_hk_chase_avoid,         # organ
    "hklab_random_ctrl":        _book_hk_random_ctrl,
}


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def run_book_hk(book: dict, snap: pd.DataFrame) -> dict:
    """Evaluate one HK book against the snapshot DataFrame.

    Parameters
    ----------
    book : dict
        A registry entry from engine.pick_lab.registry_hk.HK_REGISTRY.
    snap : pd.DataFrame
        Universe snapshot for one asof date.  Index = ticker.
        snap.attrs['asof'] = date string.

    Returns
    -------
    dict with keys:
      'engine_id'      : str
      'picks'          : list of pick dicts
      'disabled_stale' : bool (True when organ data stale, HKPL-R7 fail-closed)
      'n_picks'        : int
    Each pick: {ticker, rank, close, sector, name, name_zh, liq_unknown,
                is_avoid, why, features, authority}
    authority always 'display_only' (HKPL-R1).
    is_avoid=True on inverse books (hklab_knife_avoid, hklab_chase_avoid).
    """
    result: dict = {
        "engine_id": book["engine_id"],
        "picks": [],
        "disabled_stale": False,
        "n_picks": 0,
    }

    if snap.empty:
        return result

    # Apply HK universe screens (suspension guard + liquidity floor)
    df = _apply_hk_universe(snap)
    if df.empty:
        return result

    fn = _BOOK_FUNCS_HK.get(book["engine_id"])
    if fn is None:
        log.warning("hk.run_book_hk: no implementation for engine_id=%s", book["engine_id"])
        return result

    try:
        raw = fn(df, book)
    except Exception as exc:
        log.error("hk.run_book_hk %s error: %s", book["engine_id"], exc, exc_info=True)
        return result

    if book["engine_id"] in _ORGAN_BOOKS:
        picks, disabled_stale = raw
    else:
        picks = raw
        disabled_stale = False

    result["picks"] = picks
    result["disabled_stale"] = disabled_stale
    result["n_picks"] = len(picks)
    return result
