"""Exploratory (in-sample, motivating-only) comparison of entry families, full US universe.

Family B candidate (leader pullback-reset, trend-relative, NO absolute-oscillator veto):
    RS63 percentile >= 0.80 (cross-sectional, PIT) AND close > 50dMA AND
    2D RSI-MACD histogram crosses up today (h2>0 & h2.shift(1)<=0, mapped to daily).
Incumbent (cascade T1/T2 eligible day, from tier_stream — PIT completed buckets).

Outcome: forward 21-session return, minus same-window universe median (market-neutral-ish).
Windows: last 126 sessions with full 21d forward coverage.
Reports pooled + per-name-first stats, fire counts, overlap with incumbent, and the share
of Family-B fires that the incumbent veto would have blocked.
"""
from __future__ import annotations

import os
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

REPO = str(Path(__file__).resolve().parents[2])
os.chdir(REPO)
sys.path.insert(0, REPO)

from engine import confluence_tiers as ct  # noqa: E402
from engine.confluence_tiers import _rsi_macd, _stoch_rsi_kd, _tf_bars, _to_daily  # noqa: E402

H = 21          # forward horizon (sessions)
LOOK = 126      # evaluation window
RS_MIN = 0.80   # leader = top RS quintile


def load_universe() -> pd.DataFrame:
    frames = [pd.read_parquet(f"data/{g}/_closes_cache.parquet")
              for g in ("breadth", "midcap_breadth", "smallcap_breadth")]
    idx = frames[1].index
    wide = pd.concat([f.reindex(idx) for f in frames], axis=1)
    return wide.loc[:, ~wide.columns.duplicated()]


def main() -> None:
    px = load_universe()
    px = px.loc[:, px.notna().sum() >= 260]
    di = px.index
    n = len(di)
    eval_lo = n - LOOK - H          # first eval position
    eval_hi = n - H                 # last eval position with full forward window

    r63 = px / px.shift(63) - 1
    rs_rank = r63.rank(axis=1, pct=True)
    ma50 = px.rolling(50).mean()
    above50 = px > ma50
    fwd = px.shift(-H) / px - 1
    uni_med_fwd = fwd.median(axis=1)

    fam_b_events, inc_events = [], []
    fam_b_blocked = 0               # B fires the incumbent veto/freshness would exclude that day
    fam_b_also_inc = 0

    for t in px.columns:
        c = px[t].dropna()
        if len(c) < 260:
            continue
        # 2D RSI-MACD cross-up events mapped to daily
        sm, smk = _tf_bars(c, 2)
        m2, s2 = _rsi_macd(sm)
        h2 = m2 - s2
        x2 = (h2 > 0) & (h2.shift(1) <= 0)
        x2_d = _to_daily(x2.fillna(False), smk, c.index, "event")
        st = ct.tier_stream(c)
        if st.empty:
            continue
        inc_elig = (st["eligible"] & st["tier"].isin(["T1", "T2"])).reindex(px.index, fill_value=False)
        nt = st["not_topped"].reindex(px.index)
        x2_full = x2_d.reindex(px.index, fill_value=False)

        for i in range(eval_lo, eval_hi):
            d = px.index[i]
            f = fwd.at[d, t]
            if pd.isna(f):
                continue
            ex = f - uni_med_fwd.at[d]
            if inc_elig.at[d]:
                inc_events.append((t, d, ex))
            if (x2_full.at[d] and rs_rank.at[d, t] >= RS_MIN
                    and bool(above50.at[d, t])):
                fam_b_events.append((t, d, ex))
                if inc_elig.at[d]:
                    fam_b_also_inc += 1
                if nt.at[d] is False or nt.at[d] == False:  # noqa: E712
                    fam_b_blocked += 1

    def report(name: str, ev: list) -> None:
        if not ev:
            print(name, ": no events")
            return
        s = pd.Series([e[2] for e in ev])
        byname = pd.DataFrame(ev, columns=["t", "d", "ex"]).groupby("t")["ex"].median()
        print(f"{name}: n={len(ev)} names={byname.shape[0]}")
        print(f"  pooled  excess fwd{H}d: median {s.median()*100:+.2f}%  mean {s.mean()*100:+.2f}%  "
              f"win% {(s > 0).mean()*100:.1f}  p25 {s.quantile(.25)*100:+.1f} p75 {s.quantile(.75)*100:+.1f}")
        print(f"  per-name-first median-of-medians: {byname.median()*100:+.2f}%  "
              f"(names>0: {(byname > 0).mean()*100:.1f}%)")

    print(f"eval window: {px.index[eval_lo].date()} .. {px.index[eval_hi-1].date()}  H={H}")
    report("FAMILY B (leader pullback-reset, no osc veto)", fam_b_events)
    report("INCUMBENT (T1/T2 eligible-day)", inc_events)
    print(f"\nFamily-B fires also incumbent-eligible same day: {fam_b_also_inc}/{len(fam_b_events)}")
    print(f"Family-B fires on a day the not-topped veto was DOWN (would be blocked): "
          f"{fam_b_blocked}/{len(fam_b_events)}")
    # laggard-cross control: same trigger in the BOTTOM RS band (what the gate now admits)
    lag_events = []
    for t in px.columns:
        c = px[t].dropna()
        if len(c) < 260:
            continue
        sm, smk = _tf_bars(c, 2)
        m2, s2 = _rsi_macd(sm)
        h2 = m2 - s2
        x2 = (h2 > 0) & (h2.shift(1) <= 0)
        x2_d = _to_daily(x2.fillna(False), smk, c.index, "event").reindex(px.index, fill_value=False)
        for i in range(eval_lo, eval_hi):
            d = px.index[i]
            f = fwd.at[d, t]
            if pd.isna(f):
                continue
            if x2_d.at[d] and rs_rank.at[d, t] <= 0.40:
                lag_events.append((t, d, f - uni_med_fwd.at[d]))
    report("CONTROL (same 2D cross, RS<=0.40 laggards)", lag_events)


if __name__ == "__main__":
    warnings.filterwarnings("ignore")   # CLI-only: never at import time (repo guard)
    main()
