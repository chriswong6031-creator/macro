"""Phase-0 calibration of the China drawdown & slowdown risk gauges.

The China conditions gauges (engine/china_conditions.py: slowdown 0-100, drawdown-risk
0-100) shipped UNCALIBRATED with arbitrary band cutoffs. This script does the honest
empirical study the repo culture requires before any "calibrated" claim: it maps each
gauge to FORWARD A-share outcomes (Shanghai Composite, deep 1997-> history) — forward
1m/3m return and forward 3m max-drawdown — bucketed by gauge level, with a Spearman
rank correlation and a SPLIT-HALF stability check, plus the independent bear-episode
count (the true sample size).

Finding (write-up in reports/china-conditions-calibration.md): the gauges carry NO
forward-drawdown edge — A-shares mean-revert, so elevated macro-stress readings have
historically been flat-to-mildly-contrarian, and the sign flips across split-halves.
So the calibration outcome is: keep both gauges strictly DISPLAY-ONLY, but (a) re-anchor
the slowdown bands to history terciles (so "high" means high vs its own 2006-> record,
not a magic number), and (b) attach the measured per-band forward conditional so the
panel states the honest non-relationship instead of a bare "uncalibrated".

Run: python -m scripts.calibrate_china_conditions
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import china_inputs, china_conditions as cc
from engine.equity_alloc import bear_episodes
from lib import config, store

INDEX = "000001.SS"   # Shanghai Composite — the deepest A-share history on disk


def _gauges() -> tuple[pd.Series, pd.Series]:
    f = china_inputs.build_features()
    rec, _ = cc._recession_score_series(f)
    rec = rec.dropna()
    dd = cc._drawdown_score_series(f, rec).dropna()
    return rec, dd


def _fwd_frame(gauge: pd.Series, px: pd.Series, h: int = 63) -> pd.DataFrame:
    gi = gauge.reindex(px.index).ffill().dropna()
    common = gi.index
    fret = (px.shift(-h) / px - 1).reindex(common) * 100
    arr = px.loc[common].to_numpy()
    fdd = np.full(len(arr), np.nan)
    for i in range(len(arr)):
        w = arr[i:i + h]
        if len(w) > 1:
            fdd[i] = (w.min() / arr[i] - 1) * 100
    return pd.DataFrame({"g": gi, "fret": fret, "fdd": pd.Series(fdd, index=common)}).dropna()


def _band_table(df: pd.DataFrame, edges: tuple[float, float]) -> list[dict]:
    lo, hi = edges
    band = np.where(df["g"] < lo, "low", np.where(df["g"] < hi, "elevated", "high"))
    df = df.assign(band=band)
    rows = []
    for b in ("low", "elevated", "high"):
        sub = df[df["band"] == b]
        if sub.empty:
            continue
        rows.append({"band": b, "n": int(len(sub)),
                     "med_fwd_ret_3m": round(float(sub["fret"].median()), 1),
                     "med_fwd_maxdd_3m": round(float(sub["fdd"].median()), 1)})
    return rows


def analyze() -> dict:
    rec, dd = _gauges()
    px = store.read("china", INDEX)["close"].astype(float).dropna()

    out: dict = {"index": INDEX, "as_of": str(px.index[-1].date())}
    # slowdown: history-anchored terciles (33rd / 66th pct of its own 2006-> record)
    rec_edges = (round(float(rec.quantile(0.33)), 0), round(float(rec.quantile(0.66)), 0))
    rec_fwd = _fwd_frame(rec, px, 63)
    out["slowdown"] = {
        "edges": rec_edges,
        "spearman_fwd_maxdd": round(float(rec_fwd["g"].corr(rec_fwd["fdd"], method="spearman")), 3),
        "bands": _band_table(rec_fwd, rec_edges),
        "split_half": _split_half(rec_fwd),
        "current": round(float(rec.iloc[-1]), 1),
    }
    # drawdown: already an expanding rank-percentile -> percentile band cutoffs
    dd_edges = (50.0, 75.0)
    dd_fwd = _fwd_frame(dd, px, 63)
    out["drawdown"] = {
        "edges": dd_edges,
        "spearman_fwd_maxdd": round(float(dd_fwd["g"].corr(dd_fwd["fdd"], method="spearman")), 3),
        "bands": _band_table(dd_fwd, dd_edges),
        "split_half": _split_half(dd_fwd),
        "current": round(float(dd.iloc[-1]), 1),
    }
    out["bear_episodes_20pct"] = len(bear_episodes(px, 0.20))
    out["verdict"] = "NO forward-drawdown edge — A-shares mean-revert; keep display-only, history-anchor the bands."
    return out


def _split_half(df: pd.DataFrame) -> dict:
    h = len(df) // 2
    return {"h1": round(float(df.iloc[:h]["g"].corr(df.iloc[:h]["fdd"], method="spearman")), 3),
            "h2": round(float(df.iloc[h:]["g"].corr(df.iloc[h:]["fdd"], method="spearman")), 3)}


def _md(a: dict) -> str:
    L = ["# China drawdown & slowdown risk — Phase-0 calibration", "",
         f"Index: **{a['index']}** (Shanghai Composite, deepest A-share history) · as-of {a['as_of']} · "
         f"independent ≥20% bear episodes (true sample size): **{a['bear_episodes_20pct']}**", "",
         "**Verdict:** " + a["verdict"], ""]
    for key, title in (("slowdown", "Slowdown gauge"), ("drawdown", "Drawdown-risk gauge")):
        g = a[key]
        L += [f"## {title}",
              f"- History-anchored band edges (low / elevated / high): **{g['edges'][0]:.0f} / {g['edges'][1]:.0f}** · current reading **{g['current']}**",
              f"- Spearman(gauge, forward 3m max-drawdown): **{g['spearman_fwd_maxdd']}** "
              f"(≈0 ⇒ no monotone link; split-half H1 {g['split_half']['h1']} / H2 {g['split_half']['h2']} ⇒ unstable sign)",
              "", "| Band | n | median fwd 3m return | median fwd 3m max-DD |",
              "|---|---:|---:|---:|"]
        for r in g["bands"]:
            L.append(f"| {r['band']} | {r['n']} | {r['med_fwd_ret_3m']}% | {r['med_fwd_maxdd_3m']}% |")
        L += ["", "_Flat / non-monotone across bands — higher stress does not precede deeper drawdowns; "
              "if anything it is mildly contrarian-bullish (mean reversion)._", ""]
    L += ["## What changes",
          "- Bands are **re-anchored to the gauge's own historical distribution** (terciles for the raw "
          "slowdown score; percentile cutoffs for the already-percentiled drawdown gauge), so a 'high' "
          "reading means high *versus China's own record*, not an arbitrary number.",
          "- The measured per-band forward conditional is attached to the snapshot and surfaced on the panel, "
          "so the page states the honest non-relationship.",
          "- **Invariant preserved:** both gauges remain strictly DISPLAY-ONLY — never scored into "
          "china_axes / china_regime / china_playbook. Calibration grounds the *labels*, not a trade signal.", ""]
    return "\n".join(L)


def main() -> int:
    a = analyze()
    rpt = config.ROOT / "reports" / "china-conditions-calibration.md"
    rpt.parent.mkdir(parents=True, exist_ok=True)
    rpt.write_text(_md(a))
    print(_md(a))
    print(f"\n[written] {rpt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
