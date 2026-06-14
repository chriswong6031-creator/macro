"""Backtest the cycle-ladder state across BTC history -> data/vector/ladder_history.parquet.

engine.cycles.analyze() is latest-only (it reads the END of whatever series it is
given), so to power the Vector "cycle time machine" we REPLAY it on expanding
windows — point-in-time, NO look-ahead — and cache the per-day ladder state +
regime. Every other dashboard stage is already stored causally in
data/vector/signals.parquet; this script fills the one gap the engine computes only
for "now". Incremental: re-running only computes dates missing from the cache, so a
daily build appends a handful of rows in <1s after the ~2-3min first pass.

Run: python -m scripts.backtest_ladder_history [--full]   (--full recomputes all)
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import cycles  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("backtest_ladder")

SIGNALS = Path("data/vector/signals.parquet")
CACHE = Path("data/vector/ladder_history.parquet")
MIN_BARS = 400          # cycles.analyze needs enough history for the DCL/ICL bands


def backtest(close: pd.Series, start_after=None) -> pd.DataFrame:
    """Per-day ladder state + regime via expanding-window analyze (point-in-time)."""
    idx = close.index
    rows = {}
    for i in range(MIN_BARS, len(idx)):
        d = idx[i]
        if start_after is not None and d <= start_after:
            continue
        sub = close.iloc[: i + 1]
        a = cycles.analyze(sub, sub, kind="crypto")   # no high in signals -> high=close
        lad = a.get("ladder") or {}
        rows[d] = {"ladder_state": lad.get("state"), "regime": lad.get("regime")}
    if not rows:
        return pd.DataFrame(columns=["ladder_state", "regime"])
    out = pd.DataFrame.from_dict(rows, orient="index")
    out.index.name = "date"
    return out


def update(full: bool = False) -> pd.DataFrame:
    close = pd.read_parquet(SIGNALS)["close"]
    prev = None
    start_after = None
    if CACHE.exists() and not full:
        prev = pd.read_parquet(CACHE)
        start_after = prev.index.max()
    new = backtest(close, start_after)
    out = pd.concat([prev, new]) if prev is not None else new
    out = out[~out.index.duplicated(keep="last")].sort_index()
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(CACHE)
    log.info("ladder_history: %d rows %s..%s (+%d new)", len(out),
             out.index.min().date(), out.index.max().date(), len(new))
    return out


if __name__ == "__main__":
    update(full="--full" in sys.argv)
