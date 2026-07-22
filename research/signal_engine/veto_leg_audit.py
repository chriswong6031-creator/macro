"""Veto-leg audit — is the NOT-TOPPED veto amputating washed-out entries? (2026-07-22)

QUESTION (operator, CRCL incident): the live cascade hard-blanks ALL tiers whenever
`not_topped` is False (engine/confluence_tiers.py cascade(): `if not not_topped: return
blank`). not_topped = !(stoch_ob | stoch_bear | macd_bear) on the 3D grid. For a deeply
washed-out name whose weekly StochRSI floored and just turned (CRCL 2026-07-21: 2D MACD-RSI
crossed, 2D StochRSI crossed, 3D StochRSI crossed from oversold, weekly StochRSI turned from
~0), the binding blocker is the `macd_bear` leg — the 3D RSI-MACD is still below its signal,
as it almost always is at a genuine bottom. The T1-T4 tier table in TIERED_CASCADE.md was
validated WITHOUT this veto (tuning_harness build_signals has no topped leg) — the veto is a
post-validation bolt-on (the AMAT extended-top guard). This study measures what each veto leg
actually costs/saves, fire-conditionally, on the house ruler.

DESIGN (pre-registered before results were computed; contrasts fixed):
  Base fire = live-T2-shaped pre-veto event, replicated with the LIVE legs from
  engine.confluence_tiers: day the 2D RSI-MACD bull cross becomes knowable (event-mapped)
  AND recent3 (3D StochRSI crossed within CONF_W) AND confirm3 (weekly RSI-MACD bull OR 3D
  stoch from-oversold) AND rsi_ok — exactly the live t2_buy minus freshness bookkeeping.
  Cells by veto-leg state AT the fire (3D daily-mapped values):
    P      passes not_topped               (live board would admit)
    Vm     macd_bear ONLY                  (k3>=d3, no OB; 3D MACD below signal — CRCL class)
    Vob    stoch_ob only                   (extended but constructive)
    Vs     stoch_bear (any OB), no macd    (AMAT class the guard was built for)
    Vsm    stoch_bear+macd_bear            (fully rolled over)
    Vobm   stoch_ob+macd_bear (k>=d)       (residual)
  Washout-motion stratifier (the surviving Amendment-3 cell — MOTION, never depth-as-ranker):
    W+ = weekly StochRSI D-min over trailing 8 CLOSED weeks <= 10 AND weekly K-x-up-D within
         the last 2 CLOSED weeks (prior-closed-week discipline; no repaint).
  Proximity context (Amendment-3 RUL-29 lesson — washout edges are often proximity
  restatements): report per-cell median drawdown from the 252d high; for the headline
  Vm W+ vs W- read, also report the >=30%-down stratum so a proximity-only story is visible.
  RULER (house, CHARTER + tuning_stops): entry = NEXT daily close after the fire day;
  triple-barrier walk over realized OHLC, N_DAYS=20, hard stop S=5% on intrabar low;
  STOPPED = low touches entry*(1-S); MFE = max(high)/entry-1 before stop/timeout;
  CLEAN = not stopped AND MFE >= 5%. Stop-out rate is the verdict metric; fwd20 close-to-
  close is carried as labelled CONTEXT only (never a verdict — charter law).
  De-dup: after a fire, subsequent fire days for the same name within 5 trading days are
  folded (first knowable day wins) so one episode isn't multi-counted.
  PANEL: data/stocks/*.parquet (the deep-history house panel the cascade was tuned on),
  full history AND the 2023-06-01+ window (harness SINCE) reported separately.
  VERDICT RULE (pre-registered): a veto leg EARNS ITS KEEP on a cell iff the cell's stop%
  is >= +3pp worse than P (same window). Within +/-2pp of P (or better), the leg is
  amputating entries of P-grade stop-survival and the blocked cell belongs on a DISPLAY
  surfacing shelf (promotion to scored tiers still requires the full gauntlet).

Run: python3 research/signal_engine/veto_leg_audit.py [--since 2023-06-01] [--stop 0.05]
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))

from engine.confluence_tiers import (  # noqa: E402
    CONF_W, OB, OS, RSI_LEN, BUY_RSI_MAX,
    _tf_bars, _stoch_rsi_kd, _rsi_macd, _xup, _since, _to_daily, rsi,
)

N_DAYS = 20
W_DEEP_MAX = 10.0     # weekly D-min floor for "deep washout"
W_TURN_WIN = 2        # weekly K x-up within last N closed weeks
DEDUP_DAYS = 5

CELLS = ("P", "Vm", "Vob", "Vs", "Vsm", "Vobm")


def classify(ob: bool, bear: bool, macd: bool) -> str:
    if not (ob or bear or macd):
        return "P"
    if macd and not bear and not ob:
        return "Vm"
    if ob and not bear and not macd:
        return "Vob"
    if bear and not macd:
        return "Vs"
    if bear and macd:
        return "Vsm"
    return "Vobm"   # ob & macd, k>=d


def fires_for(close: pd.Series, high: pd.Series, low: pd.Series) -> list[dict]:
    c = close.dropna()
    if len(c) < 260:
        return []
    di = c.index
    hi = high.reindex(di)
    lo = low.reindex(di)

    # --- live legs (mirror engine.confluence_tiers.cascade exactly) ---
    sm, smk = _tf_bars(c, 2)
    m2, s2 = _rsi_macd(sm)
    mb2 = _xup(m2, s2)

    ss3, sk3 = _tf_bars(c, 3)
    k3, d3 = _stoch_rsi_kd(ss3)
    sb3 = _xup(k3, d3)
    recent3 = _since(sb3) <= CONF_W
    fromos3 = d3.rolling(CONF_W).min() < OS
    r14_3 = rsi(ss3, RSI_LEN)
    m3, s3 = _rsi_macd(ss3)

    wk = c.resample("W-FRI").last().dropna()
    wm, ws = _rsi_macd(wk)
    wbull = (wm >= ws).shift(1)

    td = lambda s, kn, how="ffill": _to_daily(s, kn, di, how)  # noqa: E731
    mb2_d = td(mb2.fillna(False), smk, "event")
    m3_d, s3_d = td(m3, sk3), td(s3, sk3)
    k3_d, d3_d = td(k3, sk3), td(d3, sk3)
    recent3_d = td(recent3.fillna(False), sk3).fillna(False)
    fromos3_d = td(fromos3.fillna(False), sk3).fillna(False)
    r14_d = td(r14_3, sk3)
    wbull_d = wbull.reindex(di, method="ffill").fillna(False).astype(bool)

    confirm3 = (wbull_d | fromos3_d)
    rsi_ok = (r14_d < BUY_RSI_MAX).fillna(False)
    base = (mb2_d & recent3_d & confirm3 & rsi_ok).fillna(False)

    # --- washout-motion stratifier (prior CLOSED week only) ---
    kw, dw = _stoch_rsi_kd(wk)
    wturn = _xup(kw, dw)
    wdeep = (dw.rolling(8, min_periods=4).min() <= W_DEEP_MAX)
    wturn_recent = (_since(wturn) <= W_TURN_WIN)
    wplus_w = (wdeep & wturn_recent).shift(1)           # closed-week discipline
    wplus_d = wplus_w.reindex(di, method="ffill").fillna(False).astype(bool)
    wdmin_w = dw.rolling(8, min_periods=4).min().shift(1)
    wdmin_d = wdmin_w.reindex(di, method="ffill")

    ma200 = c.rolling(200).mean()
    hi252 = c.rolling(252, min_periods=60).max()

    cn, hn, ln = c.to_numpy(), hi.to_numpy(), lo.to_numpy()
    n = len(cn)
    out: list[dict] = []
    last_fire = -10**9
    for i in np.where(base.to_numpy())[0]:
        if i - last_fire <= DEDUP_DAYS:
            continue
        f = i + 1
        if f >= n:
            continue
        k3n, d3n = float(k3_d.iloc[i]), float(d3_d.iloc[i])
        m3n, s3n = float(m3_d.iloc[i]), float(s3_d.iloc[i])
        if not all(np.isfinite(x) for x in (k3n, d3n, m3n, s3n)):
            continue
        last_fire = i
        ob = (k3n >= OB) or (d3n >= OB)
        bear = k3n < d3n
        macd = m3n < s3n
        out.append({
            "date": str(di[i].date()),
            "cell": classify(ob, bear, macd),
            "wplus": bool(wplus_d.iloc[i]),
            "wdmin": float(wdmin_d.iloc[i]) if np.isfinite(wdmin_d.iloc[i]) else None,
            "above200": bool(cn[i] > ma200.iloc[i]) if np.isfinite(ma200.iloc[i]) else None,
            "dd252": float(cn[i] / hi252.iloc[i] - 1.0) if np.isfinite(hi252.iloc[i]) else None,
            "_f": f, "_i": i,
        })
    # --- grade (house triple-barrier) ---
    for r in out:
        f = r.pop("_f"); r.pop("_i")
        entry = cn[f]
        stop_px = entry * (1 - ARGS.stop)
        stopped, days, mfe = False, N_DAYS, 0.0
        end = min(f + N_DAYS, n - 1)
        for j in range(f + 1, end + 1):
            mfe = max(mfe, (hn[j] if np.isfinite(hn[j]) else cn[j]) / entry - 1.0)
            lo_j = ln[j] if np.isfinite(ln[j]) else cn[j]
            if lo_j <= stop_px:
                stopped, days = True, j - f
                break
        r.update({
            "stopped": int(stopped), "days_to_stop": days,
            "mfe": round(float(mfe), 4),
            "clean": int((not stopped) and mfe >= 0.05),
            "fwd20": round(float(cn[min(f + N_DAYS, n - 1)] / entry - 1.0), 4),
            "entry": round(float(entry), 4),
        })
    return out


def table(rows: pd.DataFrame, label: str) -> None:
    print(f"\n== {label} (n={len(rows)}) ==")
    print(f"{'cell':6} {'strat':5} {'n':>5} {'names':>5} {'stop%':>6} {'clean%':>7} "
          f"{'MFEmed':>7} {'fwd20med':>8} {'dd252med':>8}")
    for cell in CELLS:
        for strat, m in (("all", rows.cell == cell),
                         ("W+", (rows.cell == cell) & rows.wplus),
                         ("W-", (rows.cell == cell) & ~rows.wplus)):
            d = rows[m]
            if not len(d):
                continue
            print(f"{cell:6} {strat:5} {len(d):>5} {d.ticker.nunique():>5} "
                  f"{100*d.stopped.mean():>6.1f} {100*d.clean.mean():>7.1f} "
                  f"{100*d.mfe.median():>7.2f} {100*d.fwd20.median():>8.2f} "
                  f"{100*d.dd252.median():>8.1f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stop", type=float, default=0.05)
    ap.add_argument("--since", default=None)
    ap.add_argument("--json-out", default=None)
    ARGS = ap.parse_args()

    rows: list[dict] = []
    files = sorted(glob.glob(str(_REPO / "data" / "stocks" / "*.parquet")))
    for p in files:
        t = Path(p).stem
        try:
            df = pd.read_parquet(p)
        except Exception:
            continue
        if "close" not in df:
            continue
        for r in fires_for(df["close"],
                           df["high"] if "high" in df else df["close"],
                           df["low"] if "low" in df else df["close"]):
            r["ticker"] = t
            rows.append(r)
    R = pd.DataFrame(rows)
    if not len(R):
        print("no fires — panel missing?"); sys.exit(1)
    R["date"] = pd.to_datetime(R["date"])
    print(f"panel: {len(files)} files, {R.ticker.nunique()} names with fires, "
          f"{len(R)} fires {R.date.min().date()}..{R.date.max().date()}, stop={ARGS.stop:.0%}")

    table(R, "FULL HISTORY")
    table(R[R.date >= pd.Timestamp("2023-06-01")], "SINCE 2023-06-01 (harness window)")
    # proximity stratum for the headline cell
    deep_dd = R[(R.cell == "Vm") & (R.dd252 <= -0.30)]
    if len(deep_dd):
        table(deep_dd, "Vm restricted to >=30% below 252d high (proximity control)")
    if ARGS.json_out:
        Path(ARGS.json_out).write_text(R.to_json(orient="records"))
        print("wrote", ARGS.json_out)
