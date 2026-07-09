"""China Pick Lab candidate book evaluators (cn.py).

run_book_cn(book, snap) -> list of pick dicts  [+ data_gap flag in result dict]

Implements all 20 CN constructions from spec §3.  Pure functions — no side
effects, no I/O, no randomness (except cnlab_random_ctrl, seeded from
sha256(engine_id+asof) per CNPL-R12).

Universe screens (applied before every book):
  - is_st == True  → excluded (ST/*ST, CNPL-R4)
  - fillable == False → excluded (executability screen, not a signal, CNPL-R4)
  - close ≥ ¥2  AND  turnover_20d ≥ ¥30M  (null turnover → liq_unknown flag)

Null semantics: a null condition value FAILS the condition, EXCEPT where spec
explicitly says 'or null' passes.

CNPL-R7: limit-up/lianban data used ONLY in AVOID direction (cnlab_chase_avoid).
         No book uses limit-up/lianban as a BUY input.
CNPL-R9 (store honesty): books 9/10 rely on runner-local stores (block tape,
         LHB).  When the relevant column is ALL-NULL in the snapshot, the book
         emits zero picks + data_gap=True in the result envelope.
CNPL-R3: kill-adjacency notes are in registry_cn.py; not repeated here.

CN snapshot columns assumed present (producer emits; some may be null when the
store is absent on non-runner environments):
  ticker, sector, board (main/star/chinext/bse), close, turnover_20d,
  dd_pct_2y, rev_3m_sector_rank, rev_deepest_quintile, washout_2w, coiled,
  star, extension_score, rsi_5, rsi_10, above_ma120, ma20_slope_up,
  d1_macd_xup_bars, d1_kd_xup_bars, d1_from_os, d1_sig, d1_macd, d1_k, d1_d,
  d3_macd_xup_bars, tier, limit_state, fillable, chase_veto,
  t_plus_one_risk, lianban_count, is_st, archetype, lowvol_tercile,
  theme_basket, theme_breadth_pct, theme_member_ret21_rank,
  block_discount_recent, lhb_inst_seats_5d, plus top-level scalars:
  cycle_phase, participation_regime, participation_risk, policy_impulse,
  qvix_z, csi300_close.
"""
from __future__ import annotations

import hashlib
import logging

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ------------------------------------------------------------------ constants --

_LIQ_CLOSE_MIN_CN = 2.0       # ¥2 floor (spec §3 defaults)
_LIQ_TURNOVER_MIN_CN = 30e6   # ¥30M 20d turnover floor


# --------------------------------------------------------------------------- #
# Universe screener
# --------------------------------------------------------------------------- #

def _apply_cn_universe(df: pd.DataFrame) -> pd.DataFrame:
    """Apply CN universe screens and add liq_unknown flag.

    Screens (applied in order):
      1. is_st == True  → drop (ST/*ST excluded, CNPL-R4)
      2. fillable == False → drop (executability screen)
      3. close ≥ ¥2 AND turnover_20d ≥ ¥30M (null turnover passes with liq_unknown)
    """
    df = df.copy()

    # 1. ST exclusion
    st = df.get("is_st")
    if st is not None:
        df = df[~st.eq(True).fillna(False)]
    if df.empty:
        return df

    # 2. Fillability screen
    fillable = df.get("fillable")
    if fillable is not None:
        df = df[fillable.ne(False).fillna(True)]  # False → excluded; null → pass
    if df.empty:
        return df

    # 3. Liquidity floor
    close_ok = df["close"].ge(_LIQ_CLOSE_MIN_CN).fillna(False)
    turnover = df.get("turnover_20d")
    if turnover is None:
        df["liq_unknown"] = True
        turnover_ok = pd.Series(True, index=df.index)
    else:
        null_mask = turnover.isna()
        df["liq_unknown"] = null_mask
        # null turnover passes (liq_unknown); present value must meet floor
        # pandas .ge() returns False for NaN (bool dtype), so we must union with null_mask
        turnover_ok = null_mask | turnover.ge(_LIQ_TURNOVER_MIN_CN).fillna(False)

    return df[close_ok & turnover_ok].copy()


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
          features: dict) -> dict:
    row = df.loc[ticker]
    return {
        "ticker": ticker,
        "rank": rank,
        "close": _col(df, "close", ticker),
        "sector": _col(df, "sector", ticker),
        "board": _col(df, "board", ticker),
        "liq_unknown": bool(row.get("liq_unknown", False)),
        "why": why,
        "features": features,
        "authority": "display_only",
    }


def _all_null(df: pd.DataFrame, col: str) -> bool:
    """True when col is absent from df OR every value in it is NaN."""
    if col not in df.columns:
        return True
    return bool(df[col].isna().all())


# --------------------------------------------------------------------------- #
# Family A — Validated edge (Reversion)
# --------------------------------------------------------------------------- #

def _book_cn_rev_pure(df: pd.DataFrame, book: dict) -> list[dict]:
    """cnlab_rev_pure — deepest quintile within-sector 3m return, NO gates."""
    mask = df.get("rev_deepest_quintile", pd.Series(False, index=df.index)).eq(True).fillna(False)
    sub = df[mask].copy()
    if sub.empty:
        return []
    # rank by reversal depth: rev_3m_sector_rank ascending (low = deepest)
    if "rev_3m_sector_rank" in sub.columns:
        sub = sub.sort_values("rev_3m_sector_rank", ascending=True).head(book["max_picks"])
    else:
        sub = sub.head(book["max_picks"])
    picks = []
    for rank, (ticker, _) in enumerate(sub.iterrows(), 1):
        picks.append(_pick(df, ticker, rank, ["rev deepest Q1", "no gate"],  {
            "rev_3m_sector_rank": _col(df, "rev_3m_sector_rank", ticker),
            "rev_deepest_quintile": _col(df, "rev_deepest_quintile", ticker),
        }))
    return picks


def _book_cn_rev_washout(df: pd.DataFrame, book: dict) -> list[dict]:
    """cnlab_rev_washout — deepest quintile ∩ washout_2w."""
    mask = (
        df.get("rev_deepest_quintile", pd.Series(False, index=df.index)).eq(True).fillna(False)
        & df.get("washout_2w", pd.Series(False, index=df.index)).eq(True).fillna(False)
    )
    sub = df[mask].copy()
    if sub.empty:
        return []
    if "rev_3m_sector_rank" in sub.columns:
        sub = sub.sort_values("rev_3m_sector_rank", ascending=True).head(book["max_picks"])
    else:
        sub = sub.head(book["max_picks"])
    picks = []
    for rank, (ticker, _) in enumerate(sub.iterrows(), 1):
        picks.append(_pick(df, ticker, rank, ["rev deepest Q1", "washout_2w✓"], {
            "rev_3m_sector_rank": _col(df, "rev_3m_sector_rank", ticker),
            "washout_2w": _col(df, "washout_2w", ticker),
        }))
    return picks


def _book_cn_rev_coiled(df: pd.DataFrame, book: dict) -> list[dict]:
    """cnlab_rev_coiled — deepest quintile ∩ (COILED or STAR)."""
    coiled = df.get("coiled", pd.Series(False, index=df.index)).eq(True).fillna(False)
    star = df.get("star", pd.Series(False, index=df.index)).eq(True).fillna(False)
    mask = (
        df.get("rev_deepest_quintile", pd.Series(False, index=df.index)).eq(True).fillna(False)
        & (coiled | star)
    )
    sub = df[mask].copy()
    if sub.empty:
        return []
    # rank by coiled bonus then reversal depth
    # coiled > star > non-coiled; within each group sort by rev_3m_sector_rank asc
    sub = sub.copy()
    sub["_coiled_bonus"] = (
        sub.get("coiled", pd.Series(False, index=sub.index)).eq(True).fillna(False).astype(int) * 2
        + sub.get("star", pd.Series(False, index=sub.index)).eq(True).fillna(False).astype(int)
    )
    if "rev_3m_sector_rank" in sub.columns:
        sub = sub.sort_values(["_coiled_bonus", "rev_3m_sector_rank"], ascending=[False, True])
    else:
        sub = sub.sort_values("_coiled_bonus", ascending=False)
    sub = sub.head(book["max_picks"])
    picks = []
    for rank, (ticker, _) in enumerate(sub.iterrows(), 1):
        picks.append(_pick(df, ticker, rank, ["rev deepest Q1", "coiled/STAR✓"], {
            "rev_3m_sector_rank": _col(df, "rev_3m_sector_rank", ticker),
            "coiled": _col(df, "coiled", ticker),
            "star": _col(df, "star", ticker),
        }))
    return picks


def _book_cn_rev_lowvol(df: pd.DataFrame, book: dict) -> list[dict]:
    """cnlab_rev_lowvol — deepest quintile ∩ lowest-vol tercile."""
    mask = (
        df.get("rev_deepest_quintile", pd.Series(False, index=df.index)).eq(True).fillna(False)
        & df.get("lowvol_tercile", pd.Series(None, index=df.index)).eq("low").fillna(False)
    )
    sub = df[mask].copy()
    if sub.empty:
        return []
    if "rev_3m_sector_rank" in sub.columns:
        sub = sub.sort_values("rev_3m_sector_rank", ascending=True).head(book["max_picks"])
    else:
        sub = sub.head(book["max_picks"])
    picks = []
    for rank, (ticker, _) in enumerate(sub.iterrows(), 1):
        picks.append(_pick(df, ticker, rank, ["rev deepest Q1", "lowvol tercile"], {
            "rev_3m_sector_rank": _col(df, "rev_3m_sector_rank", ticker),
            "lowvol_tercile": _col(df, "lowvol_tercile", ticker),
        }))
    return picks


# --------------------------------------------------------------------------- #
# Family B — 1D velocity, CN-adapted
# --------------------------------------------------------------------------- #

def _cn_1d_base_mask(df: pd.DataFrame) -> "pd.Series[bool]":
    """Base mask for 1D velocity books (book-5 conditions)."""
    return (
        df.get("d1_macd_xup_bars", pd.Series(np.nan, index=df.index)).le(2).fillna(False)
        & df.get("d1_kd_xup_bars", pd.Series(np.nan, index=df.index)).le(8).fillna(False)
        & df.get("d1_from_os", pd.Series(False, index=df.index)).eq(True).fillna(False)
        & df.get("rsi_10", pd.Series(np.nan, index=df.index)).lt(70).fillna(False)
    )


def _cn_freshness_depth_score(df: pd.DataFrame) -> "pd.Series[float]":
    """Composite rank: freshness (low xup_bars) + depth (low rsi_10)."""
    score = pd.Series(0.0, index=df.index)
    if "d1_macd_xup_bars" in df.columns:
        # invert: fresher = better (lower bars = higher score)
        max_bars = df["d1_macd_xup_bars"].max()
        if pd.notna(max_bars) and max_bars > 0:
            score -= df["d1_macd_xup_bars"].fillna(max_bars + 1) / (max_bars + 1)
    if "rsi_10" in df.columns:
        # invert: lower rsi_10 = deeper = higher score
        score -= df["rsi_10"].fillna(70) / 100
    return score


def _book_cn_1d_pure(df: pd.DataFrame, book: dict) -> list[dict]:
    """cnlab_1d_pure — 1D RSI-MACD cross ≤2, k×d ≤8, from_os, rsi_10 < 70."""
    mask = _cn_1d_base_mask(df)
    sub = df[mask].copy()
    if sub.empty:
        return []
    sub["_score"] = _cn_freshness_depth_score(sub)
    sub = sub.sort_values("_score", ascending=False).head(book["max_picks"])
    picks = []
    for rank, (ticker, _) in enumerate(sub.iterrows(), 1):
        picks.append(_pick(df, ticker, rank, ["1D MACD✚≤2", "1D K×D✚≤8", "from_OS", "RSI10<70"], {
            "d1_macd_xup_bars": _col(df, "d1_macd_xup_bars", ticker),
            "d1_kd_xup_bars": _col(df, "d1_kd_xup_bars", ticker),
            "rsi_10": _col(df, "rsi_10", ticker),
        }))
    return picks


def _book_cn_1d_phase(df: pd.DataFrame, book: dict) -> list[dict]:
    """cnlab_1d_phase — book-5 base AND cycle_phase in constructive phases."""
    cfg = book["config"]
    mask = (
        _cn_1d_base_mask(df)
        & df.get("cycle_phase", pd.Series(None, index=df.index)).isin(
            cfg["cycle_phases_allowed"]
        ).fillna(False)
    )
    sub = df[mask].copy()
    if sub.empty:
        return []
    sub["_score"] = _cn_freshness_depth_score(sub)
    sub = sub.sort_values("_score", ascending=False).head(book["max_picks"])
    picks = []
    for rank, (ticker, _) in enumerate(sub.iterrows(), 1):
        picks.append(_pick(df, ticker, rank, ["1D base", "cycle-phase✓"], {
            "d1_macd_xup_bars": _col(df, "d1_macd_xup_bars", ticker),
            "cycle_phase": _col(df, "cycle_phase", ticker),
        }))
    return picks


def _book_cn_1d_participation(df: pd.DataFrame, book: dict) -> list[dict]:
    """cnlab_1d_participation — book-5 base AND participation regime filter."""
    cfg = book["config"]
    regime_ok = df.get("participation_regime", pd.Series(None, index=df.index)).isin(
        cfg["participation_regimes_allowed"]
    ).fillna(False)
    risk_bad = df.get("participation_risk", pd.Series(None, index=df.index)).isin(
        cfg["participation_risks_blocked"]
    ).fillna(False)
    mask = _cn_1d_base_mask(df) & regime_ok & ~risk_bad
    sub = df[mask].copy()
    if sub.empty:
        return []
    sub["_score"] = _cn_freshness_depth_score(sub)
    sub = sub.sort_values("_score", ascending=False).head(book["max_picks"])
    picks = []
    for rank, (ticker, _) in enumerate(sub.iterrows(), 1):
        picks.append(_pick(df, ticker, rank, ["1D base", "participation✓", "risk-ok"], {
            "d1_macd_xup_bars": _col(df, "d1_macd_xup_bars", ticker),
            "participation_regime": _col(df, "participation_regime", ticker),
            "participation_risk": _col(df, "participation_risk", ticker),
        }))
    return picks


def _book_cn_1d_blastoff(df: pd.DataFrame, book: dict) -> list[dict]:
    """cnlab_1d_blastoff — 1D cross ≤3 AND 3D not yet crossed AND above_ma120 AND NOT chase_veto."""
    # 1D MACD cross ≤3
    mask = df.get("d1_macd_xup_bars", pd.Series(np.nan, index=df.index)).le(3).fillna(False)
    # 3D MACD NOT yet crossed (null = never crossed within window → passes)
    if "d3_macd_xup_bars" in df.columns:
        d3_not_crossed = df["d3_macd_xup_bars"].isna()
        mask = mask & d3_not_crossed
    # above_ma120
    mask = mask & df.get("above_ma120", pd.Series(False, index=df.index)).eq(True).fillna(False)
    # NOT chase_veto
    mask = mask & df.get("chase_veto", pd.Series(False, index=df.index)).ne(True).fillna(True)
    sub = df[mask].copy()
    if sub.empty:
        return []
    # rank by 5d relative strength — use extension_score inverse as proxy when available
    if "extension_score" in sub.columns:
        sub = sub.sort_values("extension_score", ascending=True).head(book["max_picks"])
    else:
        sub = sub.sort_values("d1_macd_xup_bars", ascending=True).head(book["max_picks"])
    picks = []
    for rank, (ticker, _) in enumerate(sub.iterrows(), 1):
        picks.append(_pick(df, ticker, rank, ["1D MACD✚≤3", "3D not yet", "above_ma120", "no-chase"], {
            "d1_macd_xup_bars": _col(df, "d1_macd_xup_bars", ticker),
            "d3_macd_xup_bars": _col(df, "d3_macd_xup_bars", ticker),
            "above_ma120": _col(df, "above_ma120", ticker),
            "chase_veto": _col(df, "chase_veto", ticker),
        }))
    return picks


# --------------------------------------------------------------------------- #
# Family C — structure/flow
# --------------------------------------------------------------------------- #

def _book_cn_block_discount(df: pd.DataFrame, book: dict) -> tuple[list[dict], bool]:
    """cnlab_block_discount — block trade ≤−15% discount within last 10 sessions.

    CNPL-R9: store-honest.  Returns (picks, data_gap).
    data_gap=True when block_discount_recent is all-null (store absent).
    """
    if _all_null(df, "block_discount_recent"):
        return [], True   # store absent → zero picks + data_gap flag

    mask = df.get("block_discount_recent", pd.Series(False, index=df.index)).eq(True).fillna(False)
    sub = df[mask].copy()
    if sub.empty:
        return [], False
    # rank by discount depth — if block_discount_recent is bool only, rank by rev_3m_sector_rank
    if "rev_3m_sector_rank" in sub.columns:
        sub = sub.sort_values("rev_3m_sector_rank", ascending=True).head(book["max_picks"])
    else:
        sub = sub.head(book["max_picks"])
    picks = []
    for rank, (ticker, _) in enumerate(sub.iterrows(), 1):
        picks.append(_pick(df, ticker, rank, ["block discount ≤−15%"], {
            "block_discount_recent": _col(df, "block_discount_recent", ticker),
            "rev_3m_sector_rank": _col(df, "rev_3m_sector_rank", ticker),
        }))
    return picks, False


def _book_cn_lhb_inst(df: pd.DataFrame, book: dict) -> tuple[list[dict], bool]:
    """cnlab_lhb_inst — LHB institutional seats ≥2 within 5 sessions.

    CNPL-R9: store-honest.  Returns (picks, data_gap).
    data_gap=True when lhb_inst_seats_5d is all-null (store absent).
    """
    if _all_null(df, "lhb_inst_seats_5d"):
        return [], True   # store absent

    cfg = book["config"]
    mask = df.get("lhb_inst_seats_5d", pd.Series(np.nan, index=df.index)).ge(
        cfg["lhb_inst_seats_5d_min"]
    ).fillna(False)
    sub = df[mask].copy()
    if sub.empty:
        return [], False
    sub = sub.sort_values("lhb_inst_seats_5d", ascending=False).head(book["max_picks"])
    picks = []
    for rank, (ticker, _) in enumerate(sub.iterrows(), 1):
        picks.append(_pick(df, ticker, rank, ["LHB inst seats ≥2"], {
            "lhb_inst_seats_5d": _col(df, "lhb_inst_seats_5d", ticker),
        }))
    return picks, False


def _book_cn_policy_put(df: pd.DataFrame, book: dict) -> list[dict]:
    """cnlab_policy_put — policy_impulse in {market_rescue, easing} AND dd>30% AND above 20d low."""
    cfg = book["config"]
    # policy_impulse condition (scalar repeated across rows; also per-name if available)
    policy_ok = df.get("policy_impulse", pd.Series(None, index=df.index)).isin(
        cfg["policy_impulse_allowed"]
    ).fillna(False)
    dd_ok = df.get("dd_pct_2y", pd.Series(np.nan, index=df.index)).gt(
        cfg["dd_pct_2y_min"]
    ).fillna(False)
    # "above 20d low" — use ma20_slope_up as proxy when per-name 20d-low flag absent
    above_20d_low_col = df.get("above_20d_low")
    if above_20d_low_col is not None:
        above_ok = above_20d_low_col.eq(True).fillna(False)
    else:
        # fallback: ma20_slope_up as loose proxy (trending up from lows)
        above_ok = df.get("ma20_slope_up", pd.Series(True, index=df.index)).ne(False).fillna(True)
    mask = policy_ok & dd_ok & above_ok
    sub = df[mask].copy()
    if sub.empty:
        return []
    sub = sub.sort_values("dd_pct_2y", ascending=False).head(book["max_picks"])
    picks = []
    for rank, (ticker, _) in enumerate(sub.iterrows(), 1):
        picks.append(_pick(df, ticker, rank, ["policy put✓", "dd>30%", "above 20d low"], {
            "policy_impulse": _col(df, "policy_impulse", ticker),
            "dd_pct_2y": _col(df, "dd_pct_2y", ticker),
        }))
    return picks


def _book_cn_theme_laggard(df: pd.DataFrame, book: dict) -> list[dict]:
    """cnlab_theme_laggard — theme basket breadth ≥80% AND own 21d rank bottom half AND NOT chase_veto."""
    cfg = book["config"]
    breadth_ok = df.get("theme_breadth_pct", pd.Series(np.nan, index=df.index)).ge(
        cfg["theme_breadth_pct_min"]
    ).fillna(False)
    # theme_member_ret21_rank: within-basket percentile rank of own 21d return
    # bottom half = rank ≤ 50th pct (lower rank = bigger laggard)
    laggard_ok = df.get("theme_member_ret21_rank", pd.Series(np.nan, index=df.index)).le(
        cfg["theme_member_ret21_rank_max"]
    ).fillna(False)
    no_chase = df.get("chase_veto", pd.Series(False, index=df.index)).ne(True).fillna(True)
    mask = breadth_ok & laggard_ok & no_chase
    sub = df[mask].copy()
    if sub.empty:
        return []
    # rank by breadth × laggardness: higher breadth, lower member rank = better
    # composite: breadth_pct / (member_rank + 1)
    sub["_bl_score"] = (
        sub.get("theme_breadth_pct", pd.Series(0.0, index=sub.index)).fillna(0)
        / (sub.get("theme_member_ret21_rank", pd.Series(50.0, index=sub.index)).fillna(50) + 1)
    )
    sub = sub.sort_values("_bl_score", ascending=False).head(book["max_picks"])
    picks = []
    for rank, (ticker, _) in enumerate(sub.iterrows(), 1):
        picks.append(_pick(df, ticker, rank, ["theme breadth≥80%", "laggard", "no-chase"], {
            "theme_breadth_pct": _col(df, "theme_breadth_pct", ticker),
            "theme_member_ret21_rank": _col(df, "theme_member_ret21_rank", ticker),
            "chase_veto": _col(df, "chase_veto", ticker),
        }))
    return picks


# --------------------------------------------------------------------------- #
# Family D — washout/panic regimes
# --------------------------------------------------------------------------- #

def _book_cn_capitulation_beta(df: pd.DataFrame, book: dict) -> list[dict]:
    """cnlab_capitulation_beta — dormant unless cycle_phase ∈ {CAPITULATION, DELEVERAGING}."""
    cfg = book["config"]
    # Phase check — scalar (repeated per row)
    phase_ok = df.get("cycle_phase", pd.Series(None, index=df.index)).isin(
        cfg["cycle_phases_required"]
    ).fillna(False)
    if not phase_ok.any():
        # Book dormant — correct per spec: "else book is dormant"
        return []
    mask = phase_ok & df.get("dd_pct_2y", pd.Series(np.nan, index=df.index)).gt(
        cfg["dd_pct_2y_min"]
    ).fillna(False)
    sub = df[mask].copy()
    if sub.empty:
        return []
    sub = sub.sort_values("dd_pct_2y", ascending=False).head(book["max_picks"])
    picks = []
    for rank, (ticker, _) in enumerate(sub.iterrows(), 1):
        picks.append(_pick(df, ticker, rank, ["CAPITULATION/DELEVERAGING phase", "dd>40%"], {
            "cycle_phase": _col(df, "cycle_phase", ticker),
            "dd_pct_2y": _col(df, "dd_pct_2y", ticker),
        }))
    return picks


def _book_cn_qvix_panic(df: pd.DataFrame, book: dict) -> list[dict]:
    """cnlab_qvix_panic — qvix_z > 2.0 AND in deepest-DD quintile AND NOT sealed_down.

    Spec §3 book 14: gate and rank on 2Y-drawdown depth, not the reversal quintile.
    A cross-sectional dd_deepest_quintile is computed from dd_pct_2y (top-quintile =
    deepest 20% by drawdown magnitude).  When dd_pct_2y is unavailable for a name
    that name is excluded (null-honest).
    """
    cfg = book["config"]
    # qvix_z is a top-level scalar repeated on each row
    qvix_ok = df.get("qvix_z", pd.Series(np.nan, index=df.index)).gt(
        cfg["qvix_z_min"]
    ).fillna(False)

    # Build cross-sectional DD quintile from dd_pct_2y (larger value = deeper drawdown).
    # Quintile 5 (top 20% by dd_pct_2y magnitude) is the deepest-DD quintile per spec.
    dd_col = df.get("dd_pct_2y", pd.Series(np.nan, index=df.index)).fillna(np.nan)
    if dd_col.notna().sum() >= 5:
        # pd.qcut: q=5 returns labels 0..4; label 4 = top-quintile = deepest DD
        try:
            dd_q = pd.qcut(dd_col, q=5, labels=False, duplicates="drop")
            max_q = dd_q.max()
            deepest_ok = dd_q.eq(max_q).fillna(False)
        except Exception:
            # Fallback: top-20% by value
            thresh = dd_col.quantile(0.80)
            deepest_ok = dd_col.ge(thresh).fillna(False)
    else:
        # Too few names with data — exclude all (null-honest)
        deepest_ok = pd.Series(False, index=df.index)

    # NOT sealed_down: limit_state != 'sealed_down' (null → not sealed → passes)
    limit = df.get("limit_state", pd.Series(None, index=df.index))
    not_sealed_down = limit.ne("sealed_down").fillna(True)
    mask = qvix_ok & deepest_ok & not_sealed_down
    sub = df[mask].copy()
    if sub.empty:
        return []
    # Rank by dd_pct_2y descending (deepest DD first) per spec §3 rank_by=drawdown_depth
    sub = sub.sort_values("dd_pct_2y", ascending=False, na_position="last").head(book["max_picks"])
    picks = []
    for rank, (ticker, _) in enumerate(sub.iterrows(), 1):
        picks.append(_pick(df, ticker, rank, ["QVIX>2σ", "deepest-DD quintile", "not sealed_down"], {
            "qvix_z": _col(df, "qvix_z", ticker),
            "dd_pct_2y": _col(df, "dd_pct_2y", ticker),
            "limit_state": _col(df, "limit_state", ticker),
        }))
    return picks


def _book_cn_star_20cm(df: pd.DataFrame, book: dict) -> list[dict]:
    """cnlab_star_20cm — STAR/ChiNext boards only AND 1D confluence AND above_ma120 AND NOT chase_veto."""
    cfg = book["config"]
    board_ok = df.get("board", pd.Series(None, index=df.index)).isin(
        cfg["boards_allowed"]
    ).fillna(False)
    mask = (
        board_ok
        & df.get("d1_macd_xup_bars", pd.Series(np.nan, index=df.index)).le(
            cfg["d1_macd_xup_bars_max"]
        ).fillna(False)
        & df.get("d1_kd_xup_bars", pd.Series(np.nan, index=df.index)).le(
            cfg["d1_kd_xup_bars_max"]
        ).fillna(False)
        & df.get("d1_from_os", pd.Series(False, index=df.index)).eq(True).fillna(False)
        & df.get("rsi_10", pd.Series(np.nan, index=df.index)).lt(cfg["rsi_10_max"]).fillna(False)
        & df.get("above_ma120", pd.Series(False, index=df.index)).eq(True).fillna(False)
        & df.get("chase_veto", pd.Series(False, index=df.index)).ne(True).fillna(True)
    )
    sub = df[mask].copy()
    if sub.empty:
        return []
    sub["_score"] = _cn_freshness_depth_score(sub)
    sub = sub.sort_values("_score", ascending=False).head(book["max_picks"])
    picks = []
    for rank, (ticker, _) in enumerate(sub.iterrows(), 1):
        picks.append(_pick(df, ticker, rank, ["STAR/ChiNext ±20%", "1D confluence", "above_ma120", "no-chase"], {
            "board": _col(df, "board", ticker),
            "d1_macd_xup_bars": _col(df, "d1_macd_xup_bars", ticker),
            "above_ma120": _col(df, "above_ma120", ticker),
        }))
    return picks


def _book_cn_chase_avoid(df: pd.DataFrame, book: dict) -> list[dict]:
    """cnlab_chase_avoid — INVERSE: chase_veto flagged.

    CNPL-R7: legal AVOID-direction use of limit data.
    Scored as avoid-accuracy (expected NEGATIVE 21d excess).
    """
    mask = df.get("chase_veto", pd.Series(False, index=df.index)).eq(True).fillna(False)
    sub = df[mask].copy()
    if sub.empty:
        return []
    # rank by 5d run descending (highest chase risk first)
    # Use extension_score as proxy for 5d run when explicit column absent
    if "extension_score" in sub.columns:
        sub = sub.sort_values("extension_score", ascending=False).head(book["max_picks"])
    else:
        sub = sub.head(book["max_picks"])
    picks = []
    for rank, (ticker, _) in enumerate(sub.iterrows(), 1):
        picks.append(_pick(df, ticker, rank, ["AVOID/inverse", "chase_veto✓", "CNPL-R7 avoid"], {
            "chase_veto": _col(df, "chase_veto", ticker),
            "extension_score": _col(df, "extension_score", ticker),
            "limit_state": _col(df, "limit_state", ticker),
        }))
    return picks


# --------------------------------------------------------------------------- #
# Family E — defensive + ablations + control
# --------------------------------------------------------------------------- #

def _book_cn_lowvol_defensive(df: pd.DataFrame, book: dict) -> list[dict]:
    """cnlab_lowvol_defensive — lowest-vol tercile top-12."""
    mask = df.get("lowvol_tercile", pd.Series(None, index=df.index)).eq("low").fillna(False)
    sub = df[mask].copy()
    if sub.empty:
        return []
    # rank by inverse vol — use extension_score inverse or rev_3m_sector_rank as available
    if "extension_score" in sub.columns:
        sub = sub.sort_values("extension_score", ascending=True).head(book["max_picks"])
    else:
        sub = sub.head(book["max_picks"])
    picks = []
    for rank, (ticker, _) in enumerate(sub.iterrows(), 1):
        picks.append(_pick(df, ticker, rank, ["lowvol tercile", "defensive"], {
            "lowvol_tercile": _col(df, "lowvol_tercile", ticker),
        }))
    return picks


def _book_cn_dividend_ma120(df: pd.DataFrame, book: dict) -> list[dict]:
    """cnlab_dividend_ma120 — dividend_defensive archetype AND above_ma120 AND dd < 15%."""
    cfg = book["config"]
    mask = (
        df.get("archetype", pd.Series(None, index=df.index)).eq(cfg["archetype"]).fillna(False)
        & df.get("above_ma120", pd.Series(False, index=df.index)).eq(True).fillna(False)
        & df.get("dd_pct_2y", pd.Series(np.nan, index=df.index)).lt(cfg["dd_pct_2y_max"]).fillna(False)
    )
    sub = df[mask].copy()
    if sub.empty:
        return []
    # rank by dd ascending (most stable first)
    sub = sub.sort_values("dd_pct_2y", ascending=True).head(book["max_picks"])
    picks = []
    for rank, (ticker, _) in enumerate(sub.iterrows(), 1):
        picks.append(_pick(df, ticker, rank, ["dividend_defensive", "above_ma120", "dd<15%"], {
            "archetype": _col(df, "archetype", ticker),
            "dd_pct_2y": _col(df, "dd_pct_2y", ticker),
        }))
    return picks


def _book_cn_flagship_nogate(df: pd.DataFrame, book: dict) -> list[dict]:
    """cnlab_flagship_nogate — CN board composite rank WITHOUT the US confluence-cascade gate."""
    # Use the CN reversal depth as the primary rank (validated edge)
    # "composite" = rev_3m_sector_rank (the core validated signal, without US-gate overlay)
    if "rev_3m_sector_rank" in df.columns:
        sub = df.sort_values("rev_3m_sector_rank", ascending=True).head(book["max_picks"])
    else:
        sub = df.head(book["max_picks"])
    picks = []
    for rank, (ticker, _) in enumerate(sub.iterrows(), 1):
        picks.append(_pick(df, ticker, rank, ["CN composite no-US-gate"], {
            "rev_3m_sector_rank": _col(df, "rev_3m_sector_rank", ticker),
        }))
    return picks


def _book_cn_random_ctrl(df: pd.DataFrame, book: dict) -> list[dict]:
    """cnlab_random_ctrl — 12 deterministic-random liquid CN names; seed sha256(engine_id+asof)."""
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
        picks.append(_pick(df, ticker, rank, ["CN random-ctrl"], {
            "seed": seed_str,
        }))
    return picks


# --------------------------------------------------------------------------- #
# Dispatch table
# --------------------------------------------------------------------------- #

# Store-honest books return (picks, data_gap) — others return picks directly.
# We normalise in run_book_cn below.
_BOOK_FUNCS_CN: dict[str, object] = {
    "cnlab_rev_pure":           _book_cn_rev_pure,
    "cnlab_rev_washout":        _book_cn_rev_washout,
    "cnlab_rev_coiled":         _book_cn_rev_coiled,
    "cnlab_rev_lowvol":         _book_cn_rev_lowvol,
    "cnlab_1d_pure":            _book_cn_1d_pure,
    "cnlab_1d_phase":           _book_cn_1d_phase,
    "cnlab_1d_participation":   _book_cn_1d_participation,
    "cnlab_1d_blastoff":        _book_cn_1d_blastoff,
    "cnlab_block_discount":     _book_cn_block_discount,    # returns (picks, data_gap)
    "cnlab_lhb_inst":           _book_cn_lhb_inst,          # returns (picks, data_gap)
    "cnlab_policy_put":         _book_cn_policy_put,
    "cnlab_theme_laggard":      _book_cn_theme_laggard,
    "cnlab_capitulation_beta":  _book_cn_capitulation_beta,
    "cnlab_qvix_panic":         _book_cn_qvix_panic,
    "cnlab_star_20cm":          _book_cn_star_20cm,
    "cnlab_chase_avoid":        _book_cn_chase_avoid,
    "cnlab_lowvol_defensive":   _book_cn_lowvol_defensive,
    "cnlab_dividend_ma120":     _book_cn_dividend_ma120,
    "cnlab_flagship_nogate":    _book_cn_flagship_nogate,
    "cnlab_random_ctrl":        _book_cn_random_ctrl,
}

# Books that return (picks, data_gap) tuple
_DATA_GAP_BOOKS = frozenset({"cnlab_block_discount", "cnlab_lhb_inst"})


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def run_book_cn(book: dict, snap: pd.DataFrame) -> dict:
    """Evaluate one CN book against the snapshot DataFrame.

    Parameters
    ----------
    book : dict
        A registry entry from engine.pick_lab.registry_cn.CN_REGISTRY.
    snap : pd.DataFrame
        Universe snapshot for one asof date.  Index = ticker.
        snap.attrs['asof'] = date string.

    Returns
    -------
    dict with keys:
      'engine_id'  : str
      'picks'      : list of pick dicts
      'data_gap'   : bool (True when store-dependent column all-null, CNPL-R9)
      'n_picks'    : int
    Each pick: {ticker, rank, close, sector, board, liq_unknown, why, features, authority}
    Authority always 'display_only' (CNPL-R1).
    """
    result: dict = {
        "engine_id": book["engine_id"],
        "picks": [],
        "data_gap": False,
        "n_picks": 0,
    }

    if snap.empty:
        return result

    # Apply CN universe screens (ST exclusion, fillability, liquidity floor)
    df = _apply_cn_universe(snap)
    if df.empty:
        return result

    fn = _BOOK_FUNCS_CN.get(book["engine_id"])
    if fn is None:
        log.warning("cn.run_book_cn: no implementation for engine_id=%s", book["engine_id"])
        return result

    try:
        raw = fn(df, book)
    except Exception as exc:
        log.error("cn.run_book_cn %s error: %s", book["engine_id"], exc, exc_info=True)
        return result

    if book["engine_id"] in _DATA_GAP_BOOKS:
        picks, data_gap = raw
    else:
        picks = raw
        data_gap = False

    result["picks"] = picks
    result["data_gap"] = data_gap
    result["n_picks"] = len(picks)
    return result
