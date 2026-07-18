"""Descriptive momentum X-ray for the US universe (DISPLAY-ONLY, UNSCORED).

Answers the question "where is price momentum concentrated right now?" by
computing a 12-1 month return (252-day lag, minus the most recent 21 trading
days to avoid the short-term reversal contamination common in academic momentum
literature) for every ticker in the breadth closes cache, then characterising
the resulting cross-section.

This module is **intentionally excluded from every scored surface** — it never
enters any rank, gate, sizing, alert-escalation, or Article-2 surface.  Momentum
has well-documented look-ahead contamination as a standalone signal and is carried
here as context/display only.  The disclosure keys in the output are not optional
boilerplate; they are required display text.

Output schema:  momentum_display.v1
  as_of              : str   YYYY-MM-DD — last date in the closes cache
  unscored           : True  — machine-readable guard; CI checks this is present
  universe           : {n_tickers, start, end}
  top_decile         : {n, sectors:[{sector,share_pct}×3], top_sector,
                         top_sector_share_pct, sample:[ticker×10]}
  spread             : {top_decile_mean_pct, bottom_decile_mean_pct, spread_pp}
  pulse              : {mtum_spy_20d_pct, mtum_spy_60d_pct}  or None
  disclosure_en      : str
  disclosure_zh      : str
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pandas as pd

# ---------------------------------------------------------------------------
# Default data paths (override in tests via the path arguments)
# ---------------------------------------------------------------------------
_DATA_ROOT = Path(__file__).resolve().parent.parent / "data"
_CLOSES_PATH = _DATA_ROOT / "breadth" / "_closes_cache.parquet"
_CONSTITUENTS_PATH = _DATA_ROOT / "breadth" / "constituents.parquet"
_MTUM_PATH = _DATA_ROOT / "yahoo" / "MTUM.parquet"
_SPY_PATH = _DATA_ROOT / "yahoo" / "SPY.parquet"

# Momentum window constants
_MOM_LAG = 252   # 12-month look-back (trading days)
_MOM_SKIP = 21   # skip most-recent 1 month (short-term reversal avoidance)

_DISCLOSURE_EN = (
    "A descriptive X-ray of where price momentum is concentrated right now"
    " — not a score, not a signal, and kept out of every ranking."
)
_DISCLOSURE_ZH = (
    "对当前价格动量集中位置的描述性透视——不是评分，不是信号，且不进入任何排名。"
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_closes(path: Path) -> pd.DataFrame | None:
    """Load wide close matrix.  Returns None on any I/O failure."""
    try:
        df = pd.read_parquet(path)
        if df.empty:
            return None
        return df
    except Exception:
        return None


def _load_constituents(path: Path) -> pd.DataFrame | None:
    """Load ticker→sector mapping.  Returns None on any I/O failure."""
    try:
        df = pd.read_parquet(path)
        if "sector" not in df.columns:
            return None
        return df
    except Exception:
        return None


def _load_yahoo_close(path: Path) -> pd.Series | None:
    """Load a single Yahoo price parquet and return the 'close_price' series."""
    try:
        df = pd.read_parquet(path)
        if "close_price" not in df.columns:
            return None
        s = df["close_price"].dropna()
        if s.empty:
            return None
        return s
    except Exception:
        return None


def _compute_mom_returns(closes: pd.DataFrame) -> pd.Series:
    """12-1 price momentum for each ticker; NaN where either price is missing.

    Returns a Series indexed by ticker with the raw fractional return.
    """
    n = len(closes)
    if n < _MOM_LAG + 1:
        # Not enough history — return an empty series so callers can degrade
        return pd.Series(dtype=float)

    px_now = closes.iloc[-(_MOM_SKIP + 1)]        # price 21 sessions ago
    px_old = closes.iloc[-(min(n, _MOM_LAG + 1))] # price ~252 sessions ago

    ret = (px_now / px_old) - 1.0
    # Require both points non-null; anything else → NaN → dropped downstream
    ret = ret.where(px_now.notna() & px_old.notna())
    return ret.dropna()


def _sector_concentration(tickers: list[str], constituents: pd.DataFrame | None) -> list[dict]:
    """Return top-3 sectors by count share in the given ticker list."""
    if not tickers:
        return []
    if constituents is None:
        return [{"sector": "Other", "share_pct": 100.0}]

    sectors = []
    for t in tickers:
        if t in constituents.index and pd.notna(constituents.loc[t, "sector"]):
            sectors.append(constituents.loc[t, "sector"])
        else:
            sectors.append("Other")

    s = pd.Series(sectors)
    counts = s.value_counts()
    total = len(sectors)
    result = []
    for sec, cnt in counts.head(3).items():
        result.append({"sector": str(sec), "share_pct": round(cnt / total * 100, 1)})
    return result


def _pulse(
    mtum_path: Path,
    spy_path: Path,
) -> dict[str, Any] | None:
    """MTUM/SPY ratio change over 20 and 60 sessions.

    Uses the Yahoo parquets, aligned on common dates.  Returns None if either
    file is absent or too short.
    """
    mtum = _load_yahoo_close(mtum_path)
    spy = _load_yahoo_close(spy_path)
    if mtum is None or spy is None:
        return None

    # Align on common dates
    common = mtum.index.intersection(spy.index)
    if len(common) < 61:
        return None

    ratio = mtum.loc[common] / spy.loc[common]

    def _chg(n: int) -> float | None:
        if len(ratio) < n + 1:
            return None
        r_now = ratio.iloc[-1]
        r_prev = ratio.iloc[-(n + 1)]
        if r_prev == 0 or not math.isfinite(r_now) or not math.isfinite(r_prev):
            return None
        return round(float(r_now / r_prev - 1.0) * 100, 2)

    p20 = _chg(20)
    p60 = _chg(60)
    if p20 is None and p60 is None:
        return None

    return {"mtum_spy_20d_pct": p20, "mtum_spy_60d_pct": p60}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_momentum_display(
    closes_path: Path | str | None = None,
    constituents_path: Path | str | None = None,
    mtum_path: Path | str | None = None,
    spy_path: Path | str | None = None,
) -> dict[str, Any] | None:
    """Compute a descriptive momentum X-ray of the US universe.

    All sub-blocks fail-open: absent data → that block is None (or omitted).
    If every sub-block is absent, returns None.

    Parameters
    ----------
    closes_path : override default data/breadth/_closes_cache.parquet
    constituents_path : override default data/breadth/constituents.parquet
    mtum_path : override default data/yahoo/MTUM.parquet
    spy_path : override default data/yahoo/SPY.parquet

    Returns
    -------
    dict with schema momentum_display.v1, or None if inputs are entirely absent.
    """
    cp = Path(closes_path) if closes_path is not None else _CLOSES_PATH
    kp = Path(constituents_path) if constituents_path is not None else _CONSTITUENTS_PATH
    mp = Path(mtum_path) if mtum_path is not None else _MTUM_PATH
    sp = Path(spy_path) if spy_path is not None else _SPY_PATH

    closes = _load_closes(cp)
    if closes is None:
        return None

    constituents = _load_constituents(kp)  # may be None → fail-open

    as_of = closes.index[-1].strftime("%Y-%m-%d")
    n_tickers = len(closes.columns)
    start = closes.index[0].strftime("%Y-%m-%d")
    end = as_of

    # --- momentum returns ---------------------------------------------------
    ret = _compute_mom_returns(closes)

    pulse = _pulse(mp, sp)

    # If we have no return data, emit a pulse-only payload (short cache case)
    if ret.empty:
        payload: dict[str, Any] = {
            "schema": "momentum_display.v1",
            "as_of": as_of,
            "unscored": True,
            "universe": {"n_tickers": n_tickers, "start": start, "end": end},
            "top_decile": None,
            "spread": None,
            "pulse": pulse,
            "disclosure_en": _DISCLOSURE_EN,
            "disclosure_zh": _DISCLOSURE_ZH,
        }
        return payload

    ret_sorted = ret.sort_values(ascending=False)
    n_valid = len(ret_sorted)
    decile_n = max(1, round(n_valid / 10))

    top_tickers = ret_sorted.iloc[:decile_n].index.tolist()
    bottom_tickers = ret_sorted.iloc[-decile_n:].index.tolist()

    # --- top_decile block ---------------------------------------------------
    sector_rows = _sector_concentration(top_tickers, constituents)
    top_sector = sector_rows[0]["sector"] if sector_rows else "Other"
    top_sector_share = sector_rows[0]["share_pct"] if sector_rows else None

    top_decile: dict[str, Any] = {
        "n": len(top_tickers),
        "sectors": sector_rows,
        "top_sector": top_sector,
        "top_sector_share_pct": top_sector_share,
        "sample": top_tickers[:10],
    }

    # --- spread block -------------------------------------------------------
    top_mean = float(ret_sorted.iloc[:decile_n].mean()) * 100
    bot_mean = float(ret_sorted.iloc[-decile_n:].mean()) * 100
    spread: dict[str, Any] = {
        "top_decile_mean_pct": round(top_mean, 2),
        "bottom_decile_mean_pct": round(bot_mean, 2),
        "spread_pp": round(top_mean - bot_mean, 2),
    }

    return {
        "schema": "momentum_display.v1",
        "as_of": as_of,
        "unscored": True,
        "universe": {"n_tickers": n_tickers, "start": start, "end": end},
        "top_decile": top_decile,
        "spread": spread,
        "pulse": pulse,
        "disclosure_en": _DISCLOSURE_EN,
        "disclosure_zh": _DISCLOSURE_ZH,
    }
