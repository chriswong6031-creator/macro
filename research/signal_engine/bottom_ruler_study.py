"""Bottom-calling ruler — grading signals AS bottom calls, not as stop-survival. (2026-07-22)

OPERATOR OBJECTIVE: "pinpoint bottom picks — that's the main objective of Prophet."
The current scoreboards cannot measure that objective: the 21d-excess grade measures payoff
only, and the -5% stop ruler grades a perfect bottom call as a LOSS when one wide bar wicks
it (measured: 63-68% stop-outs in deep washouts at every rung). A bottom CALL has four
separable qualities; this ruler grades each, frozen at maturity, with NO exit policy mixed in
(exits are policy; mixing policy into measurement is what produced the floating-mark mess):

  PROXIMITY   how close (%) was the signal-day close to the eventual trough low in
              [t-10, t+60]?  pinpoint = within 5%.
  DURABILITY  did the washout floor (trailing 20d low) HOLD after the call?
              held (<=0.5% undercut) / probed (<=3%) / deep probe (<=10%) / broke (>10%).
              A probe that recovers is NOT a failed call — depth is graded, not touch.
  PATH        MAE60 before MFE60 (what a position must survive to harvest the call).
  PAYOFF      MFE60 and fwd60 close-basis (context; never a verdict alone).

PRE-REGISTERED COMPARISON: the washout ladder rungs (state = weekly StochRSI D<=10 in >=3 of
last 6 closed weeks; rungs W0 thrust / W1 2D-stoch / W2 2D-MACD / W3 1W / W4 2W as defined in
washout_ladder_study.py) vs CASCADE_P = the live cascade-admitted T2 fire (2D MACD cross +
recent3 + confirm3 + rsi_ok + not-topped pass, NO washout requirement) — i.e. what the board
admits today, graded on bottom-calling metrics. Hypothesis under test: the current admitted
signal is a trend-entry detector, not a bottom detector; the washout rungs dominate it on
proximity/durability. Panel: data/stocks/*.parquet. Dedup 20td per rung.

Run: python3 research/signal_engine/bottom_ruler_study.py
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
    CONF_W, OB, OS, RSI_LEN, BUY_RSI_MAX,
    _tf_bars, _stoch_rsi_kd, _rsi_macd, _xup, _since, _to_daily, rsi,
)

H = 60           # maturity window (trading days)
PRE = 10         # trough search may start this many days before the signal
DEDUP = 20
FLOOR_D, FLOOR_WKS, FLOOR_WIN = 10.0, 3, 6
RUNGS = ("W0_thrust", "W1_stoch2d", "W2_macd2d", "W3_1w", "W4_2w", "CASCADE_P")


def events_for(df: pd.DataFrame) -> list[dict]:
    c = df["close"].dropna()
    if len(c) < 340:
        return []
    di = c.index
    hi = df["high"].reindex(di)
    lo = df["low"].reindex(di)
    vol = df["volume"].reindex(di) if "volume" in df else None

    wk = c.resample("W-FRI").last().dropna()
    kw, dw = _stoch_rsi_kd(wk)
    floored = (dw <= FLOOR_D).rolling(FLOOR_WIN, min_periods=FLOOR_WKS).sum() >= FLOOR_WKS
    state_d = floored.shift(1).reindex(di, method="ffill").fillna(False).astype(bool)

    ret1 = c.pct_change()
    atrp = (hi - lo).rolling(20).mean() / c.shift(1)
    rngpos = ((c - lo) / (hi - lo).replace(0, np.nan)).fillna(1.0)
    thrust = (ret1 >= np.maximum(0.05, 1.5 * atrp)) & (rngpos >= 0.6)
    if vol is not None and vol.notna().sum() > 100:
        thrust &= (vol >= 1.5 * vol.rolling(20).mean())

    sm, smk = _tf_bars(c, 2)
    k2, d2 = _stoch_rsi_kd(sm)
    st2 = _xup(k2, d2) & (d2.rolling(CONF_W).min() < OS)
    m2, s2 = _rsi_macd(sm)
    mb2_d = _to_daily(_xup(m2, s2).fillna(False), smk, di, "event")

    ss3, sk3 = _tf_bars(c, 3)
    k3, d3 = _stoch_rsi_kd(ss3)
    recent3_d = _to_daily((_since(_xup(k3, d3)) <= CONF_W).fillna(False), sk3, di).fillna(False)
    fromos3_d = _to_daily((d3.rolling(CONF_W).min() < OS).fillna(False), sk3, di).fillna(False)
    r14_d = _to_daily(rsi(ss3, RSI_LEN), sk3, di)
    m3_d, s3_d = _to_daily(_rsi_macd(ss3)[0], sk3, di), _to_daily(_rsi_macd(ss3)[1], sk3, di)
    k3_d, d3_d = _to_daily(k3, sk3, di), _to_daily(d3, sk3, di)
    wm, ws = _rsi_macd(wk)
    wbull_d = (wm >= ws).shift(1).reindex(di, method="ffill").fillna(False).astype(bool)
    confirm3 = (wbull_d | fromos3_d)
    rsi_ok = (r14_d < BUY_RSI_MAX).fillna(False)
    not_topped = ~((k3_d >= OB) | (d3_d >= OB) | (k3_d < d3_d) | (m3_d < s3_d))
    cascade_p = (mb2_d & recent3_d & confirm3 & rsi_ok & not_topped).fillna(False)

    wx = _xup(kw, dw)
    wk2 = c.resample("2W-FRI").last().dropna()
    k2w, d2w = _stoch_rsi_kd(wk2)

    ev = {
        "W0_thrust": (thrust.fillna(False) & state_d),
        "W1_stoch2d": (_to_daily(st2.fillna(False), smk, di, "event") & state_d),
        "W2_macd2d": (mb2_d & state_d),
        "W3_1w": (wx.reindex(di).fillna(False).astype(bool) & state_d),
        "W4_2w": (_xup(k2w, d2w).reindex(di).fillna(False).astype(bool) & state_d),
        "CASCADE_P": cascade_p,
    }

    low20 = lo.rolling(20, min_periods=5).min()
    cn = c.to_numpy()
    hn = hi.fillna(c).to_numpy()
    ln = lo.fillna(c).to_numpy()
    n = len(cn)
    out: list[dict] = []
    for rung in RUNGS:
        mask = ev[rung].to_numpy()
        last = -10**9
        for i in np.where(mask)[0]:
            if i - last <= DEDUP:
                continue
            if i + H >= n or i - PRE < 0:
                continue      # matured-only: frozen grades, no partial windows
            F = float(low20.iloc[i])
            if not np.isfinite(F) or F <= 0:
                continue
            last = i
            f = i + 1
            fill = cn[f]
            w_lo = ln[i - PRE: i + H + 1]
            trough = float(np.nanmin(w_lo))
            t_off = int(np.nanargmin(w_lo)) - PRE          # days vs signal day
            fwd_lo = ln[f: i + H + 1]
            undercut = max(0.0, 1.0 - float(np.nanmin(fwd_lo)) / F)
            mfe = float(np.nanmax(hn[f + 1: i + H + 1]) / fill - 1.0)
            mae = float(np.nanmin(ln[f + 1: i + H + 1]) / fill - 1.0)
            out.append({
                "rung": rung, "date": str(di[i].date()),
                "prox": float(cn[i] / trough - 1.0),
                "t_off": t_off,
                "undercut": undercut,
                "mfe60": mfe, "mae60": mae,
                "fwd60": float(cn[i + H] / fill - 1.0),
            })
    return out


def table(R: pd.DataFrame, label: str) -> None:
    print(f"\n== {label} (n={len(R)}) ==")
    print(f"{'rung':10} {'n':>6} {'names':>5} {'prox_med%':>9} {'pin5%':>6} {'t_off':>6} "
          f"{'held%':>6} {'probe3%':>7} {'brk10%':>7} {'MFE60':>6} {'MAE60':>6} {'fwd60':>6}")
    for rung in RUNGS:
        d = R[R.rung == rung]
        if not len(d):
            continue
        held = (d.undercut <= 0.005).mean()
        probe = (d.undercut <= 0.03).mean()
        broke = (d.undercut > 0.10).mean()
        print(f"{rung:10} {len(d):>6} {d.ticker.nunique():>5} {100*d.prox.median():>9.1f} "
              f"{100*(d.prox <= 0.05).mean():>6.1f} {d.t_off.median():>6.0f} "
              f"{100*held:>6.1f} {100*probe:>7.1f} {100*broke:>7.1f} "
              f"{100*d.mfe60.median():>6.1f} {100*d.mae60.median():>6.1f} "
              f"{100*d.fwd60.median():>6.1f}")


if __name__ == "__main__":
    rows: list[dict] = []
    files = sorted(glob.glob(str(_REPO / "data" / "stocks" / "*.parquet")))
    for p in files:
        try:
            df = pd.read_parquet(p)
        except Exception:
            continue
        if not {"close", "high", "low"} <= set(df.columns):
            continue
        for r in events_for(df):
            r["ticker"] = Path(p).stem
            rows.append(r)
    R = pd.DataFrame(rows)
    if not len(R):
        print("no events"); sys.exit(1)
    R["date"] = pd.to_datetime(R["date"])
    print(f"panel: {len(files)} files | events {len(R)} | {R.date.min().date()}..{R.date.max().date()}")
    print("cols: prox_med = signal close vs eventual trough low [t-10,t+60]; pin5 = within 5%;")
    print("t_off = median days signal-to-trough (neg = trough was already in); held/probe/brk =")
    print("floor undercut <=0.5% / <=3% / >10%; MFE/MAE/fwd60 vs next-close fill.")
    table(R, "FULL HISTORY (matured events only)")
    table(R[R.date >= "2018-01-01"], "SINCE 2018 (modern regime)")
