"""Phase-0 gate test for the OFR Financial Stress Index (research/DATA_SIGNAL_EXPANSION_2026.md).

QUESTION: does the OFR FSI earn a place in the SCORING path (a risk-OFF leg in the
macro-risk score / drawdown gauge), or is it display-only context?

We mirror how the existing drawdown_risk gauge is judged: can a stress reading TODAY
discriminate a forward >=10% S&P drawdown over the next 63 trading days? We compare
the OFR FSI against the NFCI leg already in the score, and — the decisive test — ask
whether ADDING FSI to NFCI improves discrimination, robustly across both halves of
history. Rank-AUC (no fitting), full sample + split-half. A purely coincident gauge
should NOT beat NFCI nor add to it out of the calm regime.

Decision rule (conservative, matches the team's "no unvalidated scoring leg" bar):
WIRE the gate only if FSI+NFCI beats NFCI alone by >= +0.02 AUC IN BOTH HALVES.
Otherwise ship display-only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import store  # noqa: E402

HORIZON = 63          # ~3 months
DD_THRESH = 0.10      # >=10% drawdown


def _series(group: str, sid: str, col: str | None = None) -> pd.Series:
    df = store.read(group, sid)
    if df is None or df.empty:
        raise SystemExit(f"missing {group}/{sid}")
    s = df[col] if col and col in df.columns else df.iloc[:, 0]
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def _fwd_drawdown_event(px: pd.Series, horizon: int, thresh: float) -> pd.Series:
    """1 if, from day t, the forward `horizon`-day path falls >= thresh below px[t]."""
    p = px.astype(float).values
    n = len(p)
    out = np.zeros(n)
    for i in range(n):
        j = min(i + horizon, n)
        fwd = p[i + 1:j]
        if fwd.size == 0:
            out[i] = np.nan
            continue
        out[i] = 1.0 if (fwd.min() / p[i] - 1.0) <= -thresh else 0.0
    return pd.Series(out, index=px.index)


def _zscore(s: pd.Series, win: int = 1260) -> pd.Series:
    m = s.rolling(win, min_periods=win // 4).mean()
    sd = s.rolling(win, min_periods=win // 4).std()
    return (s - m) / sd.replace(0, np.nan)


def rank_auc(score: pd.Series, label: pd.Series) -> tuple[float, int, int]:
    """AUC = P(score | event > score | non-event) via the Mann-Whitney U statistic.
    Higher score should mean higher event probability."""
    d = pd.concat([score.rename("s"), label.rename("y")], axis=1).dropna()
    pos = d[d.y == 1]["s"].values
    neg = d[d.y == 0]["s"].values
    if len(pos) == 0 or len(neg) == 0:
        return float("nan"), len(pos), len(neg)
    ranks = pd.Series(np.concatenate([pos, neg])).rank().values
    r_pos = ranks[:len(pos)].sum()
    u = r_pos - len(pos) * (len(pos) + 1) / 2.0
    return float(u / (len(pos) * len(neg))), len(pos), len(neg)


def main() -> int:
    spy = _series("yahoo", "SPY", "close")
    nfci = _series("fred", "NFCI")
    fsi = _series("ofr_fsi", "fsi")
    funding = _series("ofr_fsi", "fsi_funding")
    em = _series("ofr_fsi", "fsi_em")

    idx = spy.index
    nfci = nfci.reindex(idx).ffill(limit=7)
    fsi = fsi.reindex(idx).ffill(limit=7)
    funding = funding.reindex(idx).ffill(limit=7)
    em = em.reindex(idx).ffill(limit=7)
    event = _fwd_drawdown_event(spy, HORIZON, DD_THRESH)

    df = pd.DataFrame({"spy": spy, "nfci": nfci, "fsi": fsi, "funding": funding,
                       "em": em, "event": event}).dropna(subset=["nfci", "fsi", "event"])
    # combined leg: equal-weight standardized NFCI + FSI (fit-free incremental test)
    df["z_nfci"] = _zscore(df["nfci"])
    df["z_fsi"] = _zscore(df["fsi"])
    df["combined"] = df[["z_nfci", "z_fsi"]].mean(axis=1)

    halves = {"FULL": df, "H1": df.iloc[: len(df) // 2], "H2": df.iloc[len(df) // 2:]}
    preds = ["nfci", "fsi", "funding", "em", "combined"]

    print(f"OFR FSI Phase-0 gate — forward {HORIZON}d >= {int(DD_THRESH*100)}% S&P drawdown")
    print(f"sample {df.index[0].date()} -> {df.index[-1].date()}  n={len(df)}")
    print(f"base rate (event) = {df['event'].mean():.3f}\n")
    print(f"{'predictor':10s} " + " ".join(f"{h:>12s}" for h in halves))
    aucs = {}
    for p in preds:
        row = []
        for h, sub in halves.items():
            a, npos, nneg = rank_auc(sub[p], sub["event"])
            row.append(a)
            aucs[(p, h)] = a
        print(f"{p:10s} " + " ".join(f"{a:12.3f}" for a in row))

    print("\nINCREMENT (combined - nfci):")
    for h in halves:
        d = aucs[("combined", h)] - aucs[("nfci", h)]
        print(f"  {h:5s}: {d:+.3f}")

    inc_h1 = aucs[("combined", "H1")] - aucs[("nfci", "H1")]
    inc_h2 = aucs[("combined", "H2")] - aucs[("nfci", "H2")]
    wire = (inc_h1 >= 0.02) and (inc_h2 >= 0.02)
    print("\nVERDICT:", "WIRE OFR-FSI gate into MRS" if wire else
          "DISPLAY-ONLY — FSI does not robustly beat/augment NFCI for forward drawdown")
    print("(decision rule: combined beats NFCI by >= +0.02 AUC in BOTH halves)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
