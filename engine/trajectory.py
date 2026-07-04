"""Shared PRICE-TRAJECTORY spine — the one honest read of where a name sits in its
own price history (drawdown, relative strength, trend posture).

WHY THIS EXISTS. Several desks (the divergence radar's basket attribution, the
Intelligence Hub's edge-remaining and lifecycle stage) reasoned about "room to run"
and "laggard with upside" WITHOUT ever looking at the price trajectory — so a name
that had crashed −55% off its high and was still falling read as a bullish laggard
with the most room. This module is the single, pure, testable price read those desks
now consult so a broken, rolling-over name can never be surfaced as an emerging edge.

PRICE SOURCE — ``data/yahoo/<T>.parquet`` ``close`` column ONLY. That column is
dividend/split-ADJUSTED (verified), so drawdown and relative-strength are real. We do
NOT fall back to ``data/breadth/_closes_cache.parquet``: it is split-UNADJUSTED and
manufactures fake moves (e.g. INTC/DELL show fabricated +100pp RS from a split), which
is exactly the class of error this spine exists to kill. No yahoo parquet ⇒ we return
None honestly rather than guessing from a bad source.

API
    snapshot(ticker, root=None, closes=None) -> dict | None
        Pass a pre-loaded close Series via ``closes`` to avoid re-reading the parquet
        (the hub already has the series in hand for the signal gate). Returns None when
        there is no adjusted price history or too little of it (< ~30 bars).

Fields (all point-in-time as of the last close bar):
    off_high_252   fraction ≤ 0 — drawdown from the trailing 252-bar (≈1y) high.
    rs_vs_spy_60d  percentage points — the name's 60-bar return minus SPY's 60-bar return.
    ret_20d        fraction — trailing 20-bar (≈1mo) return.
    ret_60d        fraction — trailing 60-bar (≈1q) return.
    above_50d      bool — last close ≥ its 50-bar SMA.
    above_200d     bool — last close ≥ its 200-bar SMA (None if < 200 bars).
    rolling_over   bool — deep off-high AND falling AND below the 50d MA (see below).
    basing         bool — deep off-high but stabilizing (see below).
    asof           ISO date of the last close bar used.

ROLLING_OVER — the load-bearing gate. Deliberately simple and explainable:
    off_high_252 <= -0.15  AND  ret_20d < 0  AND  not above_50d
i.e. the name is materially below its own 1y high (≥15% drawdown — past normal noise),
its last month is DOWN, and it sits below its 50-day average (no reclaim). All three
must hold: a −15% name that has turned up and reclaimed its 50d is NOT rolling over
(that is the start of a basing/repair), and a name near its highs is never rolling over
regardless of a soft month.

BASING — the honest "deep but stabilizing" counterpart, so a genuinely repairing name
is not lumped with the fallers:
    off_high_252 <= -0.15  AND  ret_20d >= 0  AND  above_50d
deep off its high, but the last month is flat-to-up AND it has reclaimed its 50d MA.
rolling_over and basing are mutually exclusive by construction (ret_20d sign +
above_50d differ). A shallow (> −15%) name is neither.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

_BENCH = "SPY"
_MIN_BARS = 30          # below this, drawdown/RS are noise — degrade to None
_DRAWDOWN_GATE = -0.15  # ≥15% off the 1y high = materially broken, past normal chop


def _yahoo_closes(ticker: str, root: Path) -> pd.Series | None:
    """Adjusted close Series from data/yahoo/<T>.parquet, sorted, datetime-indexed.
    yahoo ONLY — never the split-unadjusted breadth cache. None if absent/empty."""
    try:
        df = pd.read_parquet(Path(root) / "data" / "yahoo" / f"{ticker}.parquet")
    except Exception:  # noqa: BLE001 — absent parquet is an honest None, not an error
        return None
    if "close" not in getattr(df, "columns", []):
        return None
    s = df["close"].dropna()
    if s.empty:
        return None
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def _ret(s: pd.Series, n: int) -> float | None:
    """Simple n-bar return of a close series, or None if too short / zero base."""
    if len(s) <= n:
        return None
    a, b = float(s.iloc[-n - 1]), float(s.iloc[-1])
    if a == 0:
        return None
    return b / a - 1.0


def snapshot(ticker: str, root: Path | None = None, closes: pd.Series | None = None) -> dict | None:
    """Point-in-time price trajectory for a name. Pure, degrade-safe, never raises.
    Returns None when there is no adjusted yahoo history (or < ~30 bars)."""
    try:
        root = Path(root) if root else config.ROOT
        t = (ticker or "").upper()
        if not t:
            return None
        s = closes if closes is not None else _yahoo_closes(t, root)
        if s is None or len(s) < _MIN_BARS:
            return None
        try:
            s = s[~s.index.duplicated(keep="last")].sort_index()
        except Exception:  # noqa: BLE001 — a plain list-backed series has no .index dedup
            pass
        last = float(s.iloc[-1])
        if last <= 0:
            return None

        win = s.iloc[-252:] if len(s) >= 252 else s
        hi = float(win.max())
        off_high = round(last / hi - 1.0, 4) if hi > 0 else None   # ≤ 0

        ret20 = _ret(s, 20)
        ret60 = _ret(s, 60)

        ma50 = float(s.iloc[-50:].mean()) if len(s) >= 50 else None
        ma200 = float(s.iloc[-200:].mean()) if len(s) >= 200 else None
        above_50 = (last >= ma50) if ma50 is not None else None
        above_200 = (last >= ma200) if ma200 is not None else None

        # relative strength vs SPY over 60 bars, in percentage points
        rs60 = None
        if ret60 is not None:
            spy = _yahoo_closes(_BENCH, root)
            spy_ret60 = _ret(spy, 60) if spy is not None else None
            if spy_ret60 is not None:
                rs60 = round((ret60 - spy_ret60) * 100.0, 2)

        deep = off_high is not None and off_high <= _DRAWDOWN_GATE
        rolling_over = bool(deep and (ret20 is not None and ret20 < 0) and above_50 is False)
        basing = bool(deep and (ret20 is not None and ret20 >= 0) and above_50 is True)

        return {
            "ticker": t,
            "off_high_252": off_high,
            "rs_vs_spy_60d": rs60,
            "ret_20d": round(ret20, 4) if ret20 is not None else None,
            "ret_60d": round(ret60, 4) if ret60 is not None else None,
            "above_50d": above_50,
            "above_200d": above_200,
            "rolling_over": rolling_over,
            "basing": basing,
            "asof": s.index[-1].date().isoformat() if hasattr(s.index[-1], "date") else None,
        }
    except Exception as e:  # noqa: BLE001 — a shared spine must never break a build
        log.debug("trajectory.snapshot(%s) failed: %s", ticker, e)
        return None
