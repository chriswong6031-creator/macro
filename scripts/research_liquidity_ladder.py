"""RESEARCH PROTOTYPE — does the net-liquidity regime sharpen the CYCLE LADDER?

The prior liquidity study (scripts/research_liquidity_gate.py) proved the macro
net-liquidity regime is a real, robust, ORTHOGONAL odds-edge on a generic
126-day momentum-long signal. This script asks the *specific* question that
gates wiring it into the per-stock product: does conditioning the cycle-ladder's
BUY states (FRESH BUY / TURN SIGNALED — the "BUY ZONE" + "BOTTOMING" calls users
actually act on) on liquidity-EXPANDING vs CONTRACTING improve forward 21d/63d
hit-rate AND drawdown (the D43 lens)?  Only wire if it confirms IN THIS context.

It re-runs the ACTUAL engine ladder (engine.cycles) over the cross-asset panel —
same walk-forward as calibrate_ladder — and tags each evaluated day with the
net-liquidity regime a trader actually had on that date (reconstructed + lagged
exactly like engine.regime.liquidity_overlay, via research_liquidity_gate.net_liquidity).

Honesty rails (carried over from the gate study):
- effective N ≈ #liquidity EPISODES, not #asset-days (one macro series);
- split-half, 2020-21-QE-excluded, by-asset-class;
- judges BOTH forward return (hit/avg) AND forward drawdown.
Frame any win as ODDS, never a point-return-magnitude promise.

NOT wired into engine/UI — prints a verdict to be measured first.

Usage: .venv/bin/python -m scripts.research_liquidity_ladder
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine.cycles import cycle_state, early_signals, ladder_state, mtf_snapshot
from scripts.research_liquidity_gate import EXP_THR, ROC_4W, net_liquidity
from scripts.research_trend_gate import (
    STEP, asset_class, fwd_drawdown, fwd_return, load_panel,
)

BUY_STATES = ("FRESH BUY", "TURN SIGNALED")   # the green "buy" calls users act on
WINDOW = 600          # trailing window the ladder math needs (matches calibrate_ladder)
WARMUP = 300          # first evaluable index
HORIZONS = (21, 63)
QE = ("2020-03-01", "2021-12-31")


def liquidity_regime(nl: pd.Series) -> pd.Series:
    """expanding / contracting / neutral from the 4w RoC, exactly like
    engine.regime.liquidity_overlay (nl is already lagged in net_liquidity())."""
    roc = nl.diff(ROC_4W)
    out = pd.Series("neutral", index=nl.index)
    out[roc > EXP_THR] = "expanding"
    out[roc < -EXP_THR] = "contracting"
    out[roc.isna()] = "unknown"
    return out


def collect(panel: dict[str, pd.Series], reg: pd.Series) -> pd.DataFrame:
    """One row per (asset, weekly as-of) with the live ladder state, the
    liquidity regime that day, and forward return + drawdown at each horizon."""
    rows = []
    for name, close in panel.items():
        c = close.dropna()
        if len(c) < WINDOW:
            continue
        kind = "crypto" if name.endswith("-USD") else "equity"
        cls = asset_class(name)
        # liquidity regime aligned onto this instrument's trading days
        lr = reg.reindex(reg.index.union(c.index)).ffill().reindex(c.index)
        fwd = {h: fwd_return(c, h) for h in HORIZONS}
        fdd = {h: fwd_drawdown(c, h) for h in HORIZONS}
        max_fwd = max(HORIZONS)
        for i in range(WARMUP, len(c) - max_fwd, STEP):
            sub = c.iloc[max(0, i - WINDOW): i + 1]
            try:
                cyc = cycle_state(sub, None, kind)
                if not cyc:
                    continue
                mtf = mtf_snapshot(sub, kind)
                early = early_signals(sub, cyc, mtf)
                st = ladder_state(cyc, mtf, early)
            except Exception:  # noqa: BLE001
                continue
            state = st.get("state")
            if not state:
                continue
            dt = c.index[i]
            liq = lr.iloc[i]
            rec = {"asset": name, "class": cls, "date": dt, "state": state, "liq": liq}
            for h in HORIZONS:
                rec[f"fwd{h}"] = fwd[h].iloc[i]
                rec[f"dd{h}"] = fdd[h].iloc[i]
            rows.append(rec)
    return pd.DataFrame(rows)


def _stats(d: pd.DataFrame, h: int) -> dict:
    f, dd = d[f"fwd{h}"].dropna(), d[f"dd{h}"]
    if len(f) == 0:
        return {}
    return {"n": len(f), "hit": round(100 * (f > 0).mean(), 1),
            "avg": round(100 * f.mean(), 2),
            "dd_med": round(100 * dd.median(), 2),
            "dd_p10": round(100 * dd.quantile(0.10), 2)}


def _line(label: str, s: dict) -> str:
    if not s:
        return f"  {label:<30} (no samples)"
    return (f"  {label:<30} n={s['n']:>6}  hit={s['hit']:>5}%  avg={s['avg']:>6}%"
            f"  typ.dip={s['dd_med']:>6}%  bad.dip={s['dd_p10']:>7}%")


def _episodes(reg: pd.Series) -> int:
    r = reg[reg != "unknown"]
    return int((r != r.shift()).sum())


def report(df: pd.DataFrame, reg: pd.Series, h: int) -> None:
    buys = df[df["state"].isin(BUY_STATES)].copy()
    print(f"\n{'='*86}\nLIQUIDITY × CYCLE-LADDER  (fwd {h}d)   liquidity episodes(eff.N)~"
          f"{_episodes(reg)}   buy-setup samples n={len(buys)}\n{'='*86}")

    print("[1] ALL buy setups (FRESH BUY + TURN SIGNALED) by liquidity regime")
    print(_line("buy setups · ALL", _stats(buys, h)))
    for lab in ("expanding", "neutral", "contracting"):
        print(_line(f"  · liq {lab}", _stats(buys[buys['liq'] == lab], h)))
    exp, con = buys[buys["liq"] == "expanding"], buys[buys["liq"] == "contracting"]
    se, sc = _stats(exp, h), _stats(con, h)
    if se and sc:
        print(f"  -> EXPANDING vs CONTRACTING: hit {sc['hit']}%→{se['hit']}% "
              f"({se['hit']-sc['hit']:+.1f}pp), bad.dip {sc['dd_p10']}%→{se['dd_p10']}% "
              f"({se['dd_p10']-sc['dd_p10']:+.1f}pp better)")

    print("\n[2] Per buy-state (does the gate hold within each state?)")
    for state in BUY_STATES:
        s = buys[buys["state"] == state]
        print(f"  -- {state} --")
        print(_line("    liq expanding", _stats(s[s["liq"] == "expanding"], h)))
        print(_line("    liq contracting", _stats(s[s["liq"] == "contracting"], h)))

    print("\n[3] Split-half robustness (must hold in BOTH halves)")
    mid = buys["date"].quantile(0.5)
    for lab, m in (("pre " + str(mid.date()), buys["date"] < mid),
                   ("post " + str(mid.date()), buys["date"] >= mid)):
        half = buys[m]
        print(f"  -- {lab} (n={len(half)}) --")
        print(_line("    liq expanding", _stats(half[half["liq"] == "expanding"], h)))
        print(_line("    liq contracting", _stats(half[half["liq"] == "contracting"], h)))

    print("\n[4] *** 2020-2021 QE EXCLUDED *** (single-episode artifact test)")
    keep = buys[~buys["date"].between(*QE)]
    print(_line("buy · liq expanding (ex QE)", _stats(keep[keep["liq"] == "expanding"], h)))
    print(_line("buy · liq contracting (ex QE)", _stats(keep[keep["liq"] == "contracting"], h)))

    print("\n[5] By asset class (US net-liq applies to crypto too — BTC tracks it)")
    for cls in ("equity", "crypto", "commodity"):
        p = buys[buys["class"] == cls]
        if len(p) < 40:
            print(f"  {cls}: thin ({len(p)})"); continue
        print(f"  -- {cls} --")
        print(_line("    liq expanding", _stats(p[p["liq"] == "expanding"], h)))
        print(_line("    liq contracting", _stats(p[p["liq"] == "contracting"], h)))


if __name__ == "__main__":
    nl = net_liquidity()
    reg = liquidity_regime(nl)
    print(f"net-liquidity regime: {reg.index.min().date()}–{reg.index.max().date()}  "
          f"episodes~{_episodes(reg)}  now={reg.dropna().iloc[-1]}")
    panel = load_panel()
    print(f"loaded {len(panel)} instruments; walking the ladder (this takes a few min)…")
    df = collect(panel, reg)
    print(f"collected {len(df)} ladder evaluations across {df['asset'].nunique()} instruments, "
          f"{df['date'].min().date()}–{df['date'].max().date()}")
    for h in HORIZONS:
        report(df, reg, h)
    print("\nNOTE: one macro series => effective N ≈ #episodes, NOT #asset-days. "
          "An ODDS edge (hit-rate / drawdown), never a point-return promise.")
