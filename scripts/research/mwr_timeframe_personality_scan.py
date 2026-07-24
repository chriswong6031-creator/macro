#!/usr/bin/env python3
"""MWR §2d — timeframe×personality assessment (operator hypothesis 2026-07-24).

Operator: "isn't that just because MCD is much slower and actually works on a
higher timeframe? Mag 7 works on a 3D basis, defensive compounders need 1W."

Two competing explanations for the flat MCD/COST panel result:
  H-TF (operator): the effective oscillator timeframe scales with personality
      speed — each name class has a home rung on the bar-size ladder.
  H-SCALE (fable): Stoch-RSI swings 0-100 regardless of vol, so low-vol names
      produce shallow "washouts"; raw-% uplift is bounded by the name's vol at
      EVERY timeframe. Vol-normalized uplift should equalize classes with no
      timeframe story.

Design (descriptive phase-0; the 4-rung grid is DISCLOSED multiplicity — any
future per-class construction must count it): S1 (Stoch-RSI 14/14/3/3 cross-up
from <20) on 3D / 1W / 2W / 1M bars, all names with full 2014→2026 history.
Uplift = median signal fwd63 − own all-days median fwd63 (per name, per rung);
uplift_vol = uplift / (ann. daily vol / √4) — i.e. scaled by the name's own
quarterly vol, the natural unit of a 63td outcome. fwd126 reported for the
low-vol tercile (slow names may also need longer grading horizons — noted, not
switched: one ruler stays fwd63).
"""
from pathlib import Path
import sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from engine.mag7_washout import stoch_rsi, cross_up, ew_basket

OHLCV = ROOT / "data" / "baskets" / "ohlcv"
H = 63
RUNGS = ["3D", "1W", "2W", "1M"]


def bars_for(close: pd.Series, rung: str) -> pd.Series:
    if rung == "3D":
        return close.iloc[2::3]
    if rung == "1W":
        return close.resample("W-FRI").last().dropna()
    if rung == "2W":
        return close.resample("W-FRI").last().dropna().iloc[::2]
    return close.resample("ME").last().dropna()


def s1_dates(close: pd.Series, rung: str) -> list[pd.Timestamp]:
    b = bars_for(close, rung)
    k, d = stoch_rsi(b)
    sig = (cross_up(k, d) & (k.shift() < 20)).fillna(False)
    return list(b.index[sig])


def fwd(close: pd.Series, when: pd.Timestamp, h: int = H) -> float | None:
    i = close.index.searchsorted(when)
    if i + h >= len(close):
        return None
    return float(close.iloc[i + h] / close.iloc[i] - 1) * 100


def profile(close: pd.Series) -> dict | None:
    rets = close.pct_change().dropna()
    if len(rets) < 2500:
        return None
    vol = float(rets.std() * np.sqrt(252)) * 100
    ma200 = close.rolling(200).mean()
    base = float(((close.shift(-H) / close - 1) * 100).dropna().median())
    out = {"vol": vol, "trend": float((close > ma200).mean()), "base": base}
    for rung in RUNGS:
        vals = [fwd(close, t) for t in s1_dates(close, rung)]
        vals = [v for v in vals if v is not None]
        if len(vals) >= 4:
            up = float(np.median(vals)) - base
            out[f"n_{rung}"] = len(vals)
            out[f"up_{rung}"] = up
            out[f"upv_{rung}"] = up / (vol / 2)  # vol/√4 ≈ quarterly vol unit
    return out


def main():
    rows = {}
    for f in sorted(OHLCV.glob("*.parquet")):
        try:
            px = pd.read_parquet(f)["close"].dropna()
            if len(px) < 2900 or px.index[0] > pd.Timestamp("2014-06-30"):
                continue
            if float(px.iloc[-1]) < 2 or float(px.median()) < 2:
                continue
            p = profile(px)
            if p and sum(1 for r in RUNGS if f"up_{r}" in p) >= 3:
                rows[f.stem] = p
        except Exception:
            continue
    df = pd.DataFrame(rows).T
    L = [f"# MWR §2d — timeframe × personality (S1 ladder, {len(df)} names)\n",
         "uplift = median signal fwd63 − own baseline (raw %); upv = same in units "
         "of the name's own quarterly vol. Grid = 4 rungs, disclosed multiplicity.\n"]

    df["volT"] = pd.qcut(df["vol"], 3, labels=["low-vol", "mid-vol", "high-vol"])
    L.append("## Vol-tercile × timeframe — median RAW uplift (%, then vol-normalized)\n")
    L.append("| vol tercile | " + " | ".join(RUNGS) + " | best rung (raw) |")
    L.append("|---|" + "---|" * (len(RUNGS) + 1))
    for lab in ["low-vol", "mid-vol", "high-vol"]:
        sub = df[df.volT == lab]
        raw = [sub[f"up_{r}"].median() if f"up_{r}" in sub else np.nan for r in RUNGS]
        best = RUNGS[int(np.nanargmax(raw))]
        L.append(f"| {lab} (n={len(sub)}) | " +
                 " | ".join(f"{v:+.2f}" for v in raw) + f" | **{best}** |")
    L.append("")
    L.append("| vol tercile | " + " | ".join(RUNGS) + " | best rung (vol-norm) |")
    L.append("|---|" + "---|" * (len(RUNGS) + 1))
    for lab in ["low-vol", "mid-vol", "high-vol"]:
        sub = df[df.volT == lab]
        nv = [sub[f"upv_{r}"].median() if f"upv_{r}" in sub else np.nan for r in RUNGS]
        best = RUNGS[int(np.nanargmax(nv))]
        L.append(f"| {lab} | " + " | ".join(f"{v:+.3f}" for v in nv) + f" | **{best}** |")

    # per-name best-rung vs vol: the direct test of H-TF
    def best_rung(row):
        vals = {r: row.get(f"up_{r}") for r in RUNGS if pd.notna(row.get(f"up_{r}"))}
        return max(vals, key=vals.get) if vals else None
    df["best"] = df.apply(best_rung, axis=1)
    ord_map = {r: i for i, r in enumerate(RUNGS)}
    dd = df.dropna(subset=["best"])
    rc = dd["vol"].corr(dd["best"].map(ord_map), method="spearman")
    L.append(f"\nH-TF direct test: Spearman corr(vol, best-rung ordinal) = **{rc:+.3f}** "
             "(operator's hypothesis predicts NEGATIVE — slower names → higher rung).\n")

    # named defensives + MAG7 ladder
    L.append("## Ladder profiles — defensives vs MAG7-EW (raw uplift %, n in parens)\n")
    L.append("| series | vol | " + " | ".join(RUNGS) + " | fwd126 @2W |")
    L.append("|---|---|" + "---|" * (len(RUNGS) + 1))
    for sym in ["MCD", "KO", "PG", "JNJ", "PEP", "WMT", "COST"]:
        if sym not in df.index:
            continue
        r = df.loc[sym]
        cells = []
        for rg in RUNGS:
            v, n = r.get(f"up_{rg}"), r.get(f"n_{rg}")
            cells.append(f"{v:+.2f} ({int(n)})" if pd.notna(v) else "—")
        px = pd.read_parquet(OHLCV / f"{sym}.parquet")["close"].dropna()
        v126 = [fwd(px, t, 126) for t in s1_dates(px, "2W")]
        v126 = [x for x in v126 if x is not None]
        b126 = float(((px.shift(-126) / px - 1) * 100).dropna().median())
        f126 = f"{float(np.median(v126)) - b126:+.2f}" if len(v126) >= 4 else "—"
        L.append(f"| {sym} | {r['vol']:.0f}% | " + " | ".join(cells) + f" | {f126} |")
    ewp = ew_basket()
    pe = profile(ewp)
    cells = [f"{pe.get(f'up_{rg}'):+.2f} ({pe.get(f'n_{rg}')})" if pe.get(f"up_{rg}") is not None else "—"
             for rg in RUNGS]
    L.append(f"| **MAG7-EW** | {pe['vol']:.0f}% | " + " | ".join(cells) + " | — |")

    out = ROOT / "reports" / "mwr_timeframe_personality.md"
    out.write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
