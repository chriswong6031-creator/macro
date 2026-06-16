"""IPO lock-up expiry — Phase-0 honest event study (the DISPLAY-vs-SCORED gate).

The lock-up overhang is the IPO Radar's most-defensible leg, but "documented in the
literature" is not "tradeable on our data". This harness measures, on the deals our
own calendar lists, the actual abnormal return around the lock-up cliff:

    event date  = priced_date + (prospectus-confirmed | 180d) lock-up
    abnormal r  = stock daily return − SPY daily return  (simple market-adjustment)
    windows     = pre-run-up [-10,-1], event [-1,+3] / [0,+3] / [0,+1], wide [-5,+5]

It then asks the decisive question: is the [-1,+3] abnormal return reliably negative
(t-stat, hit-rate, outlier-trim robust) AND large enough to beat IPO borrow costs?
Per the literature (Field & Hanka) the drift is real but small; net of scarce/expensive
lock-up borrow it is not exploitable — so we EXPECT a DISPLAY-ONLY verdict and say so.

HONEST CAVEATS baked into the verdict:
  * survivorship — yfinance only returns names that still trade; deals that cratered
    and delisted are gone, which biases the measured drift UPWARD (less negative).
  * small/clustered sample — lock-ups bunch in time; cross-sectional t overstates.
  * borrow — even a real negative drift is long-only-avoidable, not shortable cheaply.

Writes reports/ipo-lockup-phase0.md + data/ipo/lockup_phase0.json (the verdict badge
the page reads). Pure research — no site build, no commit of prices.

Run: .venv/bin/python -m scripts.ipo_lockup_phase0 [--max-names 140] [--min-size 50e6]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import warnings
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.ipo_calendar import load_calendar          # noqa: E402
from collectors.ipo_prospectus import load_lockups          # noqa: E402
from engine.validation import newey_west_tstat              # noqa: E402
from lib import config, store                                # noqa: E402

log = logging.getLogger("ipo_lockup_phase0")
warnings.filterwarnings("ignore")

WINDOWS = {"pre_runup[-10,-1]": (-10, -1), "event[-1,+3]": (-1, 3),
           "event[0,+3]": (0, 3), "event[0,+1]": (0, 1), "wide[-5,+5]": (-5, 5)}
FOCUS = "event[-1,+3]"


def _spy() -> pd.Series:
    df = store.read("yahoo", "SPY")
    return df["close"].astype(float).dropna()


def _sample(cal: pd.DataFrame, min_size: float, max_names: int) -> pd.DataFrame:
    today = pd.Timestamp(datetime.now(timezone.utc).date())
    p = cal[(cal["status"] == "priced") & (~cal["is_spac"].astype(bool))].copy()
    p["priced"] = pd.to_datetime(p["priced_date"], errors="coerce")
    p = p[p["priced"].notna() & p["ticker"].notna()]
    # real deals only, and old enough that the lock-up window has fully printed
    p = p[(p["offer_value_usd"].fillna(0) >= min_size)]
    p = p[(today - p["priced"]).dt.days >= 200]
    p = p[(today - p["priced"]).dt.days <= 365 * 3]
    p = p.sort_values("priced", ascending=False).head(max_names)
    return p


def _car(stock: pd.Series, spy: pd.Series, event: pd.Timestamp,
         w0: int, w1: int) -> float | None:
    """Cumulative market-adjusted return over trading-day offsets [w0, w1] around the
    event date (nearest trading day on/after the event)."""
    idx = stock.index.intersection(spy.index)
    if len(idx) < 60:
        return None
    s = stock.reindex(idx).dropna()
    m = spy.reindex(s.index)
    pos = s.index.searchsorted(event)          # first trading day >= event
    lo, hi = pos + w0, pos + w1
    if lo < 1 or hi >= len(s):
        return None
    sr = s.iloc[lo:hi + 1].to_numpy() / s.iloc[lo - 1:hi].to_numpy() - 1.0
    mr = m.iloc[lo:hi + 1].to_numpy() / m.iloc[lo - 1:hi].to_numpy() - 1.0
    ar = sr - mr
    return float(np.prod(1.0 + ar) - 1.0)


def run(max_names: int, min_size: float) -> dict:
    import yfinance as yf
    cal = load_calendar()
    if cal.empty:
        raise SystemExit("no IPO calendar — run collectors.ipo_calendar first")
    lk = load_lockups()
    samp = _sample(cal, min_size, max_names)
    log.info("sample: %d priced operating-co IPOs (>= $%.0fM, 200d-3y old)", len(samp), min_size / 1e6)

    spy = _spy()
    tickers = [str(t).upper() for t in samp["ticker"].tolist()]
    start = (samp["priced"].min() - timedelta(days=15)).strftime("%Y-%m-%d")
    px = yf.download(tickers, start=start, auto_adjust=True, progress=False,
                     group_by="ticker", threads=True)

    def close(t):
        try:
            s = px[t]["Close"] if isinstance(px.columns, pd.MultiIndex) else px["Close"]
            return s.astype(float).dropna()
        except Exception:  # noqa: BLE001
            return None

    cars = {w: [] for w in WINDOWS}
    used, missing = [], 0
    for _, r in samp.iterrows():
        t = str(r["ticker"]).upper()
        s = close(t)
        if s is None or s.empty:
            missing += 1
            continue
        days = 180
        if not lk.empty and t in lk.index and pd.notna(lk.loc[t].get("lockup_days")):
            days = int(lk.loc[t]["lockup_days"])
        event = r["priced"] + timedelta(days=days)
        got = False
        for w, (a, b) in WINDOWS.items():
            c = _car(s, spy, event, a, b)
            if c is not None:
                cars[w].append(c)
                got = True
        if got:
            used.append(t)
    log.info("usable: %d names (%d missing price data)", len(used), missing)

    rows = {}
    for w, vals in cars.items():
        a = np.asarray(vals, float)
        if len(a) < 8:
            rows[w] = {"n": len(a)}
            continue
        # outlier-trimmed mean (drop the 5% tails) for robustness
        lo, hi = np.percentile(a, [5, 95])
        trimmed = a[(a >= lo) & (a <= hi)]
        nw = newey_west_tstat(a, lags=4)
        rows[w] = {"n": len(a), "mean_pct": round(float(a.mean()) * 100, 2),
                   "median_pct": round(float(np.median(a)) * 100, 2),
                   "trimmed_mean_pct": round(float(trimmed.mean()) * 100, 2),
                   "pct_negative": round(float((a < 0).mean()) * 100, 1),
                   "t": nw["t"], "p": nw["p"]}

    f = rows.get(FOCUS, {})
    # verdict: even a significant negative drift stays DISPLAY-ONLY (long-only-avoidable,
    # not shortable net of borrow); we only escalate the LABEL, never to "scored".
    sig = (f.get("n", 0) >= 25 and f.get("t") is not None and f["t"] <= -2.0
           and f.get("pct_negative", 0) >= 55 and f.get("trimmed_mean_pct", 0) < 0)
    if sig:
        verdict = "DISPLAY-ONLY · drift confirmed (avoid, not shortable)"
        tier = "confirmed-overhang"
    elif f.get("n", 0) >= 25 and f.get("mean_pct") is not None and f["mean_pct"] < 0:
        verdict = "DISPLAY-ONLY · soft negative drift, not significant"
        tier = "soft"
    else:
        verdict = "DISPLAY-ONLY · no measurable edge on our sample"
        tier = "none"

    return {"windows": rows, "focus": FOCUS, "verdict": verdict, "tier": tier,
            "n_names": len(used), "n_missing": missing, "min_size_usd": min_size,
            "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "caveats": ["survivorship (delisted IPOs absent → drift biased upward)",
                        "small/time-clustered sample (cross-sectional t overstates)",
                        "borrow scarce/expensive in lock-up → not shortable net of cost"]}


def _write_report(res: dict) -> Path:
    out = config.ROOT / "reports" / "ipo-lockup-phase0.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    L = ["# IPO lock-up expiry — Phase-0 event study", "",
         f"As of {res['as_of']} · {res['n_names']} usable names "
         f"({res['n_missing']} missing price data) · min deal size "
         f"${res['min_size_usd'] / 1e6:.0f}M", "",
         f"**Verdict: {res['verdict']}**", "",
         "| Window | n | mean % | median % | trimmed % | % neg | t (HAC) | p |",
         "|---|--:|--:|--:|--:|--:|--:|--:|"]
    for w, r in res["windows"].items():
        if r.get("n", 0) < 8:
            L.append(f"| {w} | {r.get('n', 0)} | — | — | — | — | — | — |")
        else:
            L.append(f"| {w} | {r['n']} | {r['mean_pct']} | {r['median_pct']} | "
                     f"{r['trimmed_mean_pct']} | {r['pct_negative']} | {r['t']} | {r['p']} |")
    L += ["", "### Honest caveats"] + [f"- {c}" for c in res["caveats"]]
    L += ["", "Market-adjusted (stock − SPY) cumulative returns around the lock-up "
          "expiry (priced_date + prospectus-confirmed-or-180d). The leg ships "
          "DISPLAY-ONLY regardless: a negative drift here is long-only-avoidable, not "
          "shortable net of borrow, so it never becomes a scored signal — only an "
          "avoid/de-risk calendar."]
    out.write_text("\n".join(L) + "\n")
    return out


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-names", type=int, default=140)
    ap.add_argument("--min-size", type=float, default=50e6)
    args = ap.parse_args()
    res = run(args.max_names, args.min_size)
    rep = _write_report(res)
    badge = config.data_dir() / "ipo" / "lockup_phase0.json"
    badge.parent.mkdir(parents=True, exist_ok=True)
    badge.write_text(json.dumps({"verdict": res["verdict"], "tier": res["tier"],
                                 "focus": res["focus"], "stat": res["windows"].get(res["focus"]),
                                 "n_names": res["n_names"], "as_of": res["as_of"]}, indent=2))
    print(f"\n[verdict] {res['verdict']}")
    f = res["windows"].get(res["focus"], {})
    if f.get("n", 0) >= 8:
        print(f"[{res['focus']}] mean {f['mean_pct']}%  trimmed {f['trimmed_mean_pct']}%  "
              f"%neg {f['pct_negative']}  t {f['t']}  n {f['n']}")
    print(f"[report] {rep}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
