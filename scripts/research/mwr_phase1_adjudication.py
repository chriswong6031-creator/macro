#!/usr/bin/env python3
"""MWR phase-1 adjudication — the prereg §4 'jointly-adjudicated census read'.

Trigger: operator moved to activate Use-B on census evidence ("statistical
significance and reliability (ex-2022)", 2026-07-24). Per prereg §4, the lawful
route is this adjudication under ONE pre-stated ruler. Ruler (stated here,
before results were seen):

  H0: S1 signals carry no information — their forward outcomes are draws from
      the same process as random days with the same count/spacing structure.
  Primary statistic:  median fwd63 of the 13 S1-A signals (2022 INCLUDED —
      no ex-post conditioning; the 4 §2 conditioners are a separate, secondary,
      multiplicity-counted question).
  Secondary:          GOOD-rate (fwd63>0 & adverse63>-10) vs baseline.
  Null model:         10,000 placements of 13 pseudo-signal dates, uniform over
      the same span, min-separation = the observed minimum (~2 bars), last 63td
      excluded. Same fwd/adverse machinery.
  Selection haircut:  the operator's chart exploration spanned >=5 constructions
      (S1-A/S1-B/S2/S3 + the dismissed 1W stoch). Per-family p's reported AND
      Bonferroni x5; the honest claim must survive the haircut.
  Era split:          2015-2020 vs 2021-2026 medians must share sign vs baseline.
  LOCO:               drop each calendar year; median-vs-baseline must not flip
      sign on any single-year removal.
  PASS bar (all of): primary p_adj (x5) < 0.05, GOOD-rate p < 0.05, era-split
      same-sign, LOCO stable. Anything less = census alone cannot ratify;
      forward gauntlet stands.
"""
from pathlib import Path
import sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from engine.mag7_washout import (M7, ew_basket, stoch_rsi, rsi_macd, cross_up,
                                 three_day_bars, two_week_bars)

RNG = np.random.default_rng(20260724)
N_BOOT = 10_000
H = 63


def fwd(daily: np.ndarray, i: int) -> tuple[float, float] | None:
    if i + H >= len(daily):
        return None
    base = daily[i]
    ret63 = (daily[i + H] / base - 1) * 100
    adverse = (daily[i:i + H + 1].min() / base - 1) * 100
    return ret63, adverse


def stats_for(idxs: list[int], daily: np.ndarray) -> tuple[float, float]:
    outs = [fwd(daily, i) for i in idxs]
    outs = [o for o in outs if o]
    med = float(np.median([o[0] for o in outs]))
    good = float(np.mean([(o[0] > 0 and o[1] > -10) for o in outs]))
    return med, good


def signal_indices(bars: pd.Series, daily: pd.Series, kind: str) -> list[int]:
    if kind == "stoch":
        k, d = stoch_rsi(bars)
        sig = (cross_up(k, d) & (k.shift() < 20)).fillna(False)
    else:
        line, s = rsi_macd(bars)
        sig = (cross_up(line, s) & (line < 0)).fillna(False)
    dates = bars.index[sig]
    return [int(daily.index.searchsorted(t)) for t in dates]


def null_dist(n_sig: int, min_sep: int, daily: np.ndarray, lo: int, hi: int):
    meds, goods = np.empty(N_BOOT), np.empty(N_BOOT)
    for b in range(N_BOOT):
        picks: list[int] = []
        tries = 0
        while len(picks) < n_sig and tries < 4000:
            c = int(RNG.integers(lo, hi))
            if all(abs(c - p) >= min_sep for p in picks):
                picks.append(c)
            tries += 1
        meds[b], goods[b] = stats_for(picks, daily)
    return meds, goods


def main():
    daily_s = ew_basket()
    daily = daily_s.to_numpy()
    weekly = daily_s.resample("W-FRI").last().dropna()
    fams = {
        "S1-A 2W stoch": (weekly.iloc[::2], "stoch"),
        "S1-B 2W stoch": (weekly.iloc[1::2], "stoch"),
        "S2 1W rsimacd": (weekly, "macd"),
        "S3 3D rsimacd": (three_day_bars(daily_s), "macd"),
    }
    warm = 260  # ~1y warmup: no signals exist before indicators are live
    lo, hi = warm, len(daily) - H - 1

    L = ["# MWR phase-1 adjudication — census significance under one ruler\n",
         f"EW basket {daily_s.index[0].date()} → {daily_s.index[-1].date()} · "
         f"null = {N_BOOT:,} spacing-matched placements · ruler pre-stated in script header.\n"]
    base_med, base_good = stats_for(list(range(lo, hi)), daily)
    L.append(f"All-days baseline: median fwd63 {base_med:+.1f}%, GOOD-rate {base_good:.0%}.\n")

    rows = []
    for name, (bars, kind) in fams.items():
        idxs = [i for i in signal_indices(bars, daily_s, kind) if lo <= i < hi]
        if len(idxs) < 5:
            continue
        obs_med, obs_good = stats_for(idxs, daily)
        min_sep = int(min(np.diff(sorted(idxs)))) if len(idxs) > 1 else 20
        nm, ng = null_dist(len(idxs), max(min_sep, 5), daily, lo, hi)
        p_med = float((nm >= obs_med).mean())
        p_good = float((ng >= obs_good).mean())
        rows.append({"family": name, "n": len(idxs),
                     "med_fwd63": round(obs_med, 1), "good": f"{obs_good:.0%}",
                     "p_median": round(p_med, 3), "p_median_x5": round(min(1, p_med * 5), 3),
                     "p_good": round(p_good, 3), "p_good_x5": round(min(1, p_good * 5), 3)})
        if name == "S1-A 2W stoch":
            # era split + LOCO on the primary family
            sig_dates = [daily_s.index[i] for i in idxs]
            early = [i for i, t in zip(idxs, sig_dates) if t.year <= 2020]
            late = [i for i, t in zip(idxs, sig_dates) if t.year >= 2021]
            em, _ = stats_for(early, daily); lm, _ = stats_for(late, daily)
            L.append(f"\nEra split (S1-A): 2015-20 median {em:+.1f}% (n={len(early)}), "
                     f"2021-26 median {lm:+.1f}% (n={len(late)}), baseline {base_med:+.1f}% — "
                     f"{'SAME-SIGN vs baseline' if (em > base_med) == (lm > base_med) else 'SIGN FLIP'}.\n")
            loco = []
            for yr in sorted({t.year for t in sig_dates}):
                keep = [i for i, t in zip(idxs, sig_dates) if t.year != yr]
                m, _ = stats_for(keep, daily)
                loco.append(f"-{yr}: {m:+.1f}%")
            L.append("LOCO medians (S1-A): " + " · ".join(loco) +
                     f" — all {'ABOVE' if all(float(x.split(': ')[1].rstrip('%')) > base_med for x in loco) else 'NOT all above'} baseline.\n")

    L.append("\n| family | n | med fwd63 | GOOD | p(median) | p×5 | p(GOOD) | p(GOOD)×5 |")
    L.append("|---|---|---|---|---|---|---|---|")
    for r in rows:
        L.append(f"| {r['family']} | {r['n']} | {r['med_fwd63']:+.1f}% | {r['good']} | "
                 f"{r['p_median']} | {r['p_median_x5']} | {r['p_good']} | {r['p_good_x5']} |")

    out = ROOT / "reports" / "mwr_phase1_adjudication.md"
    out.write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
