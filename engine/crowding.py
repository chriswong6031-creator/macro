"""Contrarian crowding / fragility context for the per-stock page — DISPLAY-ONLY.

The flag fires when a name is simultaneously, on the latest data:

  * CROWDED  — high trailing relative-strength percentile vs the benchmark
               (the leaders everyone already owns), and
  * SHORTED  — high days-to-cover percentile in the latest FINRA snapshot
               (a crowded short on the other side), and
  * EXTENDED — stretched well above its own 50-day average.

That conjunction is the classic "fragile" set-up: a crowded long that is also a
crowded short, run far above trend — prone to a sharp unwind / squeeze either way.

WHY DISPLAY-ONLY (never a scoring leg). Phase-0 (scripts/fund_crowding_phase0.py):

  1. The price-only core (crowded AND extended) shows NO forward-return
     underperformance — crowding is not a short signal — and only a marginal,
     statistically-weak worse forward DRAWDOWN (≈0.6pp over 3m, |t|≈2.3 at 63d
     but not robust across both halves). Directional "sharper-pullback" context,
     not a sizing edge.
  2. The short-interest leg has NO point-in-time history in our store (the FINRA
     collector keeps only the latest snapshot), so it cannot be back-tested at all.

So this module NEVER feeds the conviction score (cf. the COT / RS-crowding penalty,
which WAS validated before it touched sizing). It is a contrarian risk annotation:
context on fragility, not a sell.
"""
from __future__ import annotations

import logging

import pandas as pd

from lib import config, store

log = logging.getLogger(__name__)

# percentile thresholds (0..100) for each leg; all three must clear to flag.
_CROWD_PCTILE = 80.0      # trailing RS percentile (crowded long)
_SI_PCTILE = 80.0         # days-to-cover percentile (crowded short)
_EXT_PCTILE = 80.0        # cross-sectional stretch-above-50dma percentile (extended)
_RS_WIN = 252             # trailing window for the RS percentile rank

NOTE = ("Contrarian fragility flag: a crowded leader (high relative strength) that "
        "is ALSO heavily shorted and stretched above its 50-day average — prone to a "
        "sharp unwind/squeeze. Latest-snapshot context, NOT in the conviction score "
        "and NOT a sell (Phase-0: no forward-return edge; short interest has no "
        "point-in-time history). See research/DATA_SIGNAL_EXPANSION_2026.md #6.")


def fragility(rs_pctile: float | None, si_pctile: float | None,
              ext_pctile: float | None, pct_vs_50dma: float | None,
              days_to_cover: float | None = None) -> dict | None:
    """PURE. Return the fragility annotation when all three legs are elevated and
    the name is genuinely above its 50dma; else ``None``. Pctiles are 0..100."""
    if rs_pctile is None or si_pctile is None or ext_pctile is None:
        return None
    if pct_vs_50dma is None or pct_vs_50dma <= 0:        # must actually be extended UP
        return None
    if not (rs_pctile >= _CROWD_PCTILE and si_pctile >= _SI_PCTILE
            and ext_pctile >= _EXT_PCTILE):
        return None
    return {
        "rs_pctile": round(float(rs_pctile)),
        "si_pctile": round(float(si_pctile)),
        "ext_pctile": round(float(ext_pctile)),
        "pct_vs_50dma": round(float(pct_vs_50dma), 1),
        "days_to_cover": (None if days_to_cover is None or pd.isna(days_to_cover)
                          else round(float(days_to_cover), 1)),
    }


def _bench_close() -> pd.Series | None:
    sym = config.load()["engine"]["rs_ranking"]["benchmark"]
    df = store.read("yahoo", sym)
    if df is None or df.empty:
        return None
    s = (df["close"] if "close" in df.columns else df.iloc[:, 0]).copy()
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def _short_interest() -> pd.DataFrame | None:
    p = config.data_dir() / "finra" / "short_interest.parquet"
    if not p.exists():
        return None
    try:
        return pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.debug("short_interest read failed: %s", e)
        return None


def compute_fragility(closes: pd.DataFrame | None = None,
                      si: pd.DataFrame | None = None,
                      bench: pd.Series | None = None) -> dict[str, dict]:
    """Per-ticker fragility map for the CURRENT cross-section (display-only).

    Reads the S&P-1500 close panel, the benchmark, and the latest FINRA snapshot
    from disk when not supplied. Degrades to ``{}`` (never raises) so a missing
    feed simply hides the flag. Only fragile names are returned."""
    try:
        if closes is None:
            from engine.equity_factors import _closes
            closes = _closes()
        if closes is None or closes.empty:
            return {}
        if bench is None:
            bench = _bench_close()
        if bench is None:
            return {}
        if si is None:
            si = _short_interest()
        if si is None or "days_to_cover" not in si.columns:
            return {}

        bench = bench.reindex(closes.index).ffill()
        rs = closes.div(bench, axis=0)
        # percentile of the LATEST RS within each name's trailing window (PIT, cheap)
        rs_pct = rs.tail(_RS_WIN).rank(pct=True).iloc[-1] * 100.0
        sma50 = closes.rolling(50).mean()
        stretch = closes / sma50 - 1.0
        ext_pct = stretch.iloc[-1].rank(pct=True) * 100.0      # cross-sectional, today
        pct_vs_50 = stretch.iloc[-1] * 100.0

        dtc = si["days_to_cover"].astype(float)
        si_pct = dtc.rank(pct=True) * 100.0

        out: dict[str, dict] = {}
        for t in closes.columns:
            f = fragility(rs_pct.get(t), si_pct.get(t), ext_pct.get(t),
                          pct_vs_50.get(t), dtc.get(t))
            if f:
                out[t] = f
        return out
    except Exception as e:  # noqa: BLE001 — additive context, never fatal
        log.warning("fragility map skipped (%s)", e)
        return {}
