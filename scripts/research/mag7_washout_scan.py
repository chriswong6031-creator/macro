#!/usr/bin/env python3
"""Mag-7 washout re-entry scan (phase-0 exploratory census, display-tier).

Operator hypothesis (2026-07-24, charts on MAGS ETF):
  S1: 2W Stoch-RSI bullish cross while <20  -> marks tradeable Mag-7 washout lows
  S2: 1W RSI-MACD bullish cross (deep)      -> reliable low detector
  S3: 3D RSI-MACD bullish cross (deep)      -> "called 2024/2025/2026 bottoms exactly"

This script reproduces the constructions on the house EQUAL-WEIGHT Mag-7 basket
(daily-rebalanced, data/baskets/ohlcv members, 2014->present; house prefers the EW
basket over MAGS: longer history, no ETF-inception truncation) and counts EVERY
signal 2015->present with forward outcomes — hits AND false positives. Census only:
no authority claim; grading rules for live accrual are pinned in the prereg
(research/MAG7_WASHOUT_REENTRY_PREREG.md).

Indicator notes: RSI = Wilder (engine.technicals.rsi == TV). Stoch-RSI = TV defaults
(14/14/3/3). "RSI-MACD" = MACD(12,26,9) computed ON the RSI(14) series (TH_RSIMACD+
analog; exact TV-script params unpinned — flagged in prereg). TV 2W bars are
anchor-phase-sensitive: both phases (A/B) reported.
"""
from pathlib import Path
import sys
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from engine.mag7_washout import (  # single source of truth (MWR-W0 engine)
    M7, ew_basket, stoch_rsi, rsi_macd, cross_up)

OHLCV = ROOT / "data" / "baskets" / "ohlcv"


def fwd_stats(daily: pd.Series, when: pd.Timestamp) -> dict:
    """Forward outcomes on the DAILY basket from the signal bar's close date."""
    idx = daily.index.searchsorted(when)
    if idx >= len(daily):
        return {}
    base = daily.iloc[idx]
    out = {}
    for h in (21, 63):
        j = idx + h
        out[f"fwd{h}"] = round(float(daily.iloc[min(j, len(daily) - 1)] / base - 1) * 100, 1)
    win = daily.iloc[idx: idx + 63]
    out["adverse"] = round(float(win.min() / base - 1) * 100, 1)  # worst drawdown ≤63td
    # distance (td) from signal to the local trough in a ±31td window
    lo_w = daily.iloc[max(0, idx - 31): idx + 32]
    out["td_to_trough"] = int(daily.index.searchsorted(lo_w.idxmin()) - idx)
    return out


def scan(bars: pd.Series, daily: pd.Series, kind: str) -> list[dict]:
    rows = []
    if kind == "stoch":
        k, d = stoch_rsi(bars)
        sig = cross_up(k, d) & (k.shift() < 20)
        for t in bars.index[sig.fillna(False)]:
            rows.append({"date": str(t.date()), "k_prev": round(float(k.shift().loc[t]), 1),
                         "d": round(float(d.loc[t]), 1), **fwd_stats(daily, t)})
    else:
        line, s = rsi_macd(bars)
        sig = cross_up(line, s) & (line < 0)
        deep_cut = line.quantile(0.25)
        for t in bars.index[sig.fillna(False)]:
            rows.append({"date": str(t.date()), "line": round(float(line.loc[t]), 2),
                         "deep": bool(line.loc[t] <= deep_cut), **fwd_stats(daily, t)})
    return rows


def md_table(rows: list[dict]) -> str:
    if not rows:
        return "_(no signals)_\n"
    cols = list(rows[0].keys())
    out = "| " + " | ".join(cols) + " |\n|" + "---|" * len(cols) + "\n"
    for r in rows:
        out += "| " + " | ".join(str(r.get(c, "")) for c in cols) + " |\n"
    return out


def main():
    daily = ew_basket()  # engine helper, default data root
    weekly = daily.resample("W-FRI").last().dropna()
    two_a, two_b = weekly.iloc[::2], weekly.iloc[1::2]
    three_d = daily.iloc[2::3]

    fams = {
        "S1 · 2W Stoch-RSI bullish cross <20 (anchor A)": (two_a, "stoch"),
        "S1 · 2W Stoch-RSI bullish cross <20 (anchor B)": (two_b, "stoch"),
        "S2 · 1W RSI-MACD cross-up below 0": (weekly, "macd"),
        "S3 · 3D RSI-MACD cross-up below 0": (three_d, "macd"),
    }
    L = ["# Mag-7 washout re-entry — phase-0 census (EW basket, 2014→present)\n",
         f"Basket: daily-rebalanced EW of {', '.join(M7)} · data/baskets/ohlcv · "
         f"span {daily.index[0].date()} → {daily.index[-1].date()}\n",
         "Columns: fwd21/fwd63 = % return N trading days after the signal bar close; "
         "adverse = worst % drawdown within 63td; td_to_trough = trading days from "
         "signal to the ±31td local price trough (negative = bottom was already in).\n"]
    baseline = daily.pct_change(63).shift(-63).dropna()
    L.append(f"Baseline (all days): median fwd63 {baseline.median()*100:+.1f}%, "
             f"mean {baseline.mean()*100:+.1f}%.\n")
    for name, (bars, kind) in fams.items():
        rows = scan(bars, daily, kind)
        L.append(f"\n## {name} — {len(rows)} signals\n\n" + md_table(rows))

    # current state (the "are we washed out NOW" read)
    L.append("\n## Current state (as of last store close)\n")
    for nm, bars in [("2W anchor A", two_a), ("2W anchor B", two_b)]:
        k, d = stoch_rsi(bars)
        L.append(f"- {nm}: Stoch-RSI K={k.iloc[-1]:.1f} D={d.iloc[-1]:.1f} "
                 f"(washout floor 20 — {'BELOW' if k.iloc[-1] < 20 else 'not washed out'})")
    for nm, bars in [("1W", weekly), ("3D", three_d)]:
        line, s = rsi_macd(bars)
        L.append(f"- {nm} RSI-MACD: line={line.iloc[-1]:.2f} sig={s.iloc[-1]:.2f} "
                 f"({'above' if line.iloc[-1] > s.iloc[-1] else 'below'} signal)")
    washed = 0
    for t in M7:
        px = pd.read_parquet(OHLCV / f"{t}.parquet")["close"]
        wk = px.resample("W-FRI").last().dropna().iloc[::2]
        k, _ = stoch_rsi(wk)
        if float(k.iloc[-1]) < 20:
            washed += 1
    L.append(f"- Member breadth: {washed}/7 members individually <20 on 2W Stoch-RSI K")

    out = ROOT / "reports" / "mag7_washout_scan.md"
    out.write_text("\n".join(L), encoding="utf-8")
    print(f"wrote {out}")
    print("\n".join(L[-8:]))


if __name__ == "__main__":
    main()
