"""Washout-bottom trigger ladder — how early can each rung honestly call it? (2026-07-22)

OPERATOR PROBLEM (CRCL): by the time the 2D MACD-RSI crosses, a washed-out name is already
~20% off its low. The operator entered on the FIRST DEMAND BAR (the +8% day BEFORE the 2D
cross) because the washout STATE (weekly StochRSI floored ~0 for a month) was already known.
First-principles: a bottom cannot be known before demand shows; the earliest honest EOD
evidence is the first demand bar itself. So the design is STATE (washout floor, context) +
a LADDER of triggers from earliest/noisiest to latest/most-confirmed, each with its lateness
and stop economics measured — instead of pretending any single crossover "calls the bottom".

PRE-REGISTERED DEFINITIONS (fixed before results):
  STATE (closed-week discipline, no repaint):
    weekly StochRSI D <= 10 in >= 3 of the last 6 CLOSED weeks ("stuck at the floor ~a month").
  RUNGS (fire day = first knowable close; state must be active as of the prior closed week):
    W0_thrust : up-day (c/c1-1) >= max(5%, 1.5*ATR20p) AND close in top 40% of bar range
                AND volume >= 1.5x20d avg (leg skipped when volume absent)
    W1_stoch2d: 2D StochRSI K x-up D (event-mapped), D was <20 within CONF_W buckets
    W2_macd2d : 2D RSI-MACD x-up (event-mapped) — the current cascade admission rung
    W3_1w     : weekly StochRSI K x-up D, knowable at that week's close
    W4_2w     : 2W StochRSI K x-up D (2W-FRI resample), knowable at bucket close
  Dedup 20 trading days per rung per name.
  LATENESS at fire = close / min(low, trailing 20d) - 1  (median per rung = how much of the
  bounce each rung forfeits).
  RULERS: (a) house: next-close fill, -5% intrabar stop, 20d, stop%/clean%/MFE/fwd20;
          (b) STRUCTURE stop: stop under the washout floor (trailing 20d low at fire);
              sstop% = floor-touch rate, risk_med = entry/floor - 1 (the honest unit risk).
  PANEL: data/stocks/*.parquet (close, high, low, volume). Windows: full + since 2023-06-01.

Run: python3 research/signal_engine/washout_ladder_study.py
"""
from __future__ import annotations

import glob
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))

from engine.confluence_tiers import (  # noqa: E402
    CONF_W, OS, _tf_bars, _stoch_rsi_kd, _rsi_macd, _xup, _since, _to_daily,
)

N_DAYS = 20
FLOOR_D = 10.0        # weekly D floor level
FLOOR_WKS = 3         # >= this many floored weeks ...
FLOOR_WIN = 6         # ... within this many closed weeks
DEDUP = 20
RUNGS = ("W0_thrust", "W1_stoch2d", "W2_macd2d", "W3_1w", "W4_2w")


def fires_for(df: pd.DataFrame) -> list[dict]:
    c = df["close"].dropna()
    if len(c) < 280:
        return []
    di = c.index
    hi = df["high"].reindex(di)
    lo = df["low"].reindex(di)
    vol = df["volume"].reindex(di) if "volume" in df else None

    # ---- STATE: weekly stoch floored (closed-week) ----
    wk = c.resample("W-FRI").last().dropna()
    kw, dw = _stoch_rsi_kd(wk)
    floored = (dw <= FLOOR_D).rolling(FLOOR_WIN, min_periods=FLOOR_WKS).sum() >= FLOOR_WKS
    state_w = floored.shift(1)                      # prior CLOSED week
    state_d = state_w.reindex(di, method="ffill").fillna(False).astype(bool)

    # ---- rung events ----
    ret1 = c.pct_change()
    atrp = (hi - lo).rolling(20).mean() / c.shift(1)          # bar-range proxy ATR%
    rngpos = ((c - lo) / (hi - lo).replace(0, np.nan)).fillna(1.0)
    thrust = (ret1 >= np.maximum(0.05, 1.5 * atrp)) & (rngpos >= 0.6)
    if vol is not None and vol.notna().sum() > 100:
        thrust &= (vol >= 1.5 * vol.rolling(20).mean())
    ev = {"W0_thrust": thrust.fillna(False)}

    sm, smk = _tf_bars(c, 2)
    k2, d2 = _stoch_rsi_kd(sm)
    st2 = _xup(k2, d2) & (d2.rolling(CONF_W).min() < OS)
    ev["W1_stoch2d"] = _to_daily(st2.fillna(False), smk, di, "event")
    m2, s2 = _rsi_macd(sm)
    ev["W2_macd2d"] = _to_daily(_xup(m2, s2).fillna(False), smk, di, "event")

    wx = _xup(kw, dw)
    ev["W3_1w"] = wx.reindex(di).fillna(False).astype(bool)   # knowable at week close
    wk2 = c.resample("2W-FRI").last().dropna()
    k2w, d2w = _stoch_rsi_kd(wk2)
    ev["W4_2w"] = _xup(k2w, d2w).reindex(di).fillna(False).astype(bool)

    low20 = lo.rolling(20, min_periods=5).min()
    hi252 = c.rolling(252, min_periods=60).max()
    cn, hn, ln = c.to_numpy(), hi.to_numpy(), lo.to_numpy()
    n = len(cn)
    out: list[dict] = []
    for rung in RUNGS:
        mask = (ev[rung] & state_d).to_numpy()
        last = -10**9
        for i in np.where(mask)[0]:
            if i - last <= DEDUP:
                continue
            f = i + 1
            if f >= n or not np.isfinite(low20.iloc[i]) or low20.iloc[i] <= 0:
                continue
            last = i
            entry = cn[f]
            floor = float(low20.iloc[i])
            stop5 = entry * 0.95
            stopped5 = stoppedS = False
            mfe = 0.0
            end = min(f + N_DAYS, n - 1)
            for j in range(f + 1, end + 1):
                mfe = max(mfe, (hn[j] if np.isfinite(hn[j]) else cn[j]) / entry - 1.0)
                lo_j = ln[j] if np.isfinite(ln[j]) else cn[j]
                if not stopped5 and lo_j <= stop5:
                    stopped5 = True
                if not stoppedS and lo_j < floor:
                    stoppedS = True
            out.append({
                "rung": rung, "date": str(di[i].date()),
                "late": float(cn[i] / floor - 1.0),
                "risk": float(entry / floor - 1.0),
                "dd252": float(cn[i] / hi252.iloc[i] - 1.0) if np.isfinite(hi252.iloc[i]) else None,
                "stopped5": int(stopped5), "stoppedS": int(stoppedS),
                "mfe": float(mfe),
                "clean": int((not stopped5) and mfe >= 0.05),
                "fwd20": float(cn[end] / entry - 1.0),
            })
    return out


def table(R: pd.DataFrame, label: str) -> None:
    print(f"\n== {label} (n={len(R)}) ==")
    print(f"{'rung':10} {'n':>5} {'names':>5} {'late%':>6} {'stop5%':>7} {'clean%':>7} "
          f"{'MFEmed':>7} {'fwd20':>6} {'sstop%':>7} {'risk%':>6}")
    for rung in RUNGS:
        d = R[R.rung == rung]
        if not len(d):
            continue
        print(f"{rung:10} {len(d):>5} {d.ticker.nunique():>5} {100*d.late.median():>6.1f} "
              f"{100*d.stopped5.mean():>7.1f} {100*d.clean.mean():>7.1f} "
              f"{100*d.mfe.median():>7.2f} {100*d.fwd20.median():>6.2f} "
              f"{100*d.stoppedS.mean():>7.1f} {100*d.risk.median():>6.1f}")


if __name__ == "__main__":
    rows: list[dict] = []
    files = sorted(glob.glob(str(_REPO / "data" / "stocks" / "*.parquet")))
    for p in files:
        try:
            df = pd.read_parquet(p)
        except Exception:
            continue
        if "close" not in df or "high" not in df or "low" not in df:
            continue
        for r in fires_for(df):
            r["ticker"] = Path(p).stem
            rows.append(r)
    R = pd.DataFrame(rows)
    if not len(R):
        print("no fires"); sys.exit(1)
    R["date"] = pd.to_datetime(R["date"])
    print(f"panel: {len(files)} files | fires {len(R)} | {R.date.min().date()}..{R.date.max().date()}")
    table(R, "FULL HISTORY")
    table(R[R.date >= "2023-06-01"], "SINCE 2023-06-01")
    deep = R[R.dd252 <= -0.30]
    table(deep, "DEEP WASHOUTS ONLY (dd252 <= -30%)")
    R.to_json("/tmp/washout_ladder.json", orient="records")
    print("\nwrote /tmp/washout_ladder.json")
