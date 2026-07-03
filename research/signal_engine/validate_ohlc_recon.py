"""Validate the conservative OHLC reconstruction (engine.ohlc_reconstruct).

Three questions, in the charter's discipline (research/signal_engine/CHARTER.md):

  A. ACCURACY — how close is the reconstructed high/low to the TRUE high/low, and
     does it ever SYSTEMATICALLY understate the realised range? Ground truth = the
     114 US deep names in data/stocks/*.parquet (the only true-OHLC source). We do
     NOT grid-search the one structural constant (RANGE_MULT) against these errors;
     RANGE_MULT=2.0 is the random-walk prior E[high-low]/E[|Δclose|]. We just report
     the errors it yields, and the data-implied ratio, so the prior is auditable.

  B. SIGNAL IMPACT — the buy-filter's drawdown win (−23.7%→−15.5% across held-out
     US names, test_buyfilter.py) was validated with CLOSE-based swing-high /
     bearish-divergence. Feeding high/low into those two functions is a change to a
     VALIDATED mechanism, so we re-run the same trade-sim drawdown comparison with
     swing/div driven by (1) close [the validated default], (2) TRUE high/low, and
     (3) RECONSTRUCTED high/low — and check the drawdown reduction survives and the
     markers don't churn. Pre-committed kill rule (§3): if high-based generalises no
     better than close-based on drawdown, the close-based default stays.

  C. HK STABILITY — on the two close-only names the filter was designed on (Tencent
     0700.HK, BABA), the reconstructed-high markers must be MATERIALLY the same as
     the close-only markers (a manual-review sanity gate).

Run: python research/signal_engine/validate_ohlc_recon.py
"""
from __future__ import annotations

import glob
import json
import pathlib
import warnings
import logging

import numpy as np
import pandas as pd

if __name__ == "__main__":
    # CLI-only silencers.  logging.disable() is PROCESS-GLOBAL state: at module level it
    # leaks out of any import of this file and mutes every logger for the rest of the
    # process (order-dependent pytest flakes; bitten twice — see walk_forward.py and
    # tests/test_no_module_level_logging_disable.py).
    warnings.filterwarnings("ignore")
    logging.disable(logging.CRITICAL)

import sys
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from engine.ohlc_reconstruct import reconstruct_ohlc, atr_proxy           # noqa: E402
from engine.signal_quality import (signal_frame, _swing_highs, _bear_div,  # noqa: E402
                                    _buy_filter, analyze)

STOCKS = ROOT / "data" / "stocks"
SINCE = pd.Timestamp("2023-06-01")    # same window as test_buyfilter.py


# ────────────────────────────── A. accuracy ──────────────────────────────────
def accuracy_one(df: pd.DataFrame) -> dict | None:
    close = df["close"].dropna()
    th, tl = df["high"].reindex(close.index), df["low"].reindex(close.index)
    ok = close.notna() & th.notna() & tl.notna() & (th >= tl)
    close, th, tl = close[ok], th[ok], tl[ok]
    if len(close) < 60:
        return None
    rec = reconstruct_ohlc(close)
    rh, rl = rec["high"], rec["low"]
    # drop the very first bar (open seed) to avoid an artefact
    rh, rl, th, tl, close = rh.iloc[1:], rl.iloc[1:], th.iloc[1:], tl.iloc[1:], close.iloc[1:]
    he = (rh - th) / close            # signed high error (frac of price)
    le = (rl - tl) / close
    true_rng, rec_rng = (th - tl), (rh - rl)
    cap = rec_rng / true_rng.replace(0, np.nan)
    # data-implied unbiased multiplier: true range / close-to-close ATR (unscaled)
    cc_atr1 = atr_proxy(close, range_mult=1.0, floor_pct=0.0)
    implied = (true_rng / cc_atr1.replace(0, np.nan)).iloc[1:]
    # 3D-bucket view — the granularity the SIGNAL path actually consumes (signal_frame
    # resamples high=max/low=min onto the 3B grid). Capture/understatement is slightly
    # worse here than daily, so report it honestly rather than only the daily figure.
    d3 = pd.DataFrame({"th": th, "tl": tl, "rh": rh, "rl": rl}).resample("3B")
    trng3 = d3["th"].max() - d3["tl"].min()        # true 3D range (high.max - low.min)
    rrng3 = d3["rh"].max() - d3["rl"].min()        # recon 3D range, same buckets
    cap3 = rrng3 / trng3.replace(0, np.nan)
    return {
        "abs_hi%": float(he.abs().mean() * 100), "abs_lo%": float(le.abs().mean() * 100),
        "rmse_hi%": float(np.sqrt((he ** 2).mean()) * 100),
        "rmse_lo%": float(np.sqrt((le ** 2).mean()) * 100),
        "bias_hi%": float(he.mean() * 100), "bias_lo%": float(le.mean() * 100),
        "cap_med": float(cap.median()), "cap_mean": float(cap.mean()),
        "understate%": float((rec_rng < true_rng).mean() * 100),
        "implied_mult": float(np.nanmedian(implied)),
        "cap3d_med": float(cap3.median()),
        "understate3d%": float((rrng3 < trng3).mean() * 100),
    }


def section_accuracy(files: list[str]) -> None:
    rows = []
    for fp in files:
        try:
            r = accuracy_one(pd.read_parquet(fp))
        except Exception:
            r = None
        if r:
            rows.append(r)
    A = lambda k: float(np.mean([x[k] for x in rows]))
    print("\n" + "=" * 78)
    print(f"A. RECONSTRUCTION ACCURACY vs TRUE OHLC  (n={len(rows)} US names, daily bars)")
    print("=" * 78)
    print(f"  avg |high err|:   {A('abs_hi%'):.2f}% of price   (RMSE {A('rmse_hi%'):.2f}%)")
    print(f"  avg |low  err|:   {A('abs_lo%'):.2f}% of price   (RMSE {A('rmse_lo%'):.2f}%)")
    print(f"  signed bias:      high {A('bias_hi%'):+.2f}%   low {A('bias_lo%'):+.2f}%   "
          f"(>0 high / <0 low = wider than truth = conservative)")
    print(f"  range capture:    median {A('cap_med'):.2f}x  mean {A('cap_mean'):.2f}x   "
          f"(>=1 = does not understate range)")
    print(f"  understate rate:  {A('understate%'):.0f}% of bars have recon range < true range")
    print(f"  3D-bucket view (what the signal path consumes): capture median {A('cap3d_med'):.2f}x, "
          f"understate {A('understate3d%'):.0f}% of 3D buckets")
    print(f"  data-implied unbiased multiplier (median true_range / cc_atr): {A('implied_mult'):.2f}")
    print(f"  -> prior in use RANGE_MULT=2.0   |   avg-error <2% target: "
          f"{'PASS' if max(A('abs_hi%'), A('abs_lo%')) < 2.0 else 'CHECK'}")


# ───────────────────────────── B. signal impact ──────────────────────────────
def sim_dd(close, high=None, low=None, filtered=True) -> dict | None:
    """Trade-sim max-drawdown, mirroring test_buyfilter.sim but via engine.signal_quality
    so swing-high/bear-div read whatever high/low we pass (None => close fallback)."""
    sig = signal_frame(close, high, low)
    if sig.empty:
        return None
    sig = sig.dropna(subset=["macd", "sig", "k", "d", "rsi14"])
    if len(sig) < 5:
        return None
    c, macd, idx, n = sig["close"], sig["macd"], sig.index, len(sig)
    hi = _swing_highs(sig["high"])
    pos, ep, trades, eq, curve = 0, None, [], 1.0, [1.0]
    for i in range(n - 1):
        if pos == 1:
            eq *= float(c.iloc[i + 1]) / float(c.iloc[i])
        curve.append(eq)
        if pos == 0:
            if idx[i] < SINCE:
                continue
            cand = bool(sig["CB"].iloc[i] or sig["revBuy"].iloc[i])
            if cand and filtered:
                ok, _ = _buy_filter(i, sig, _bear_div(i, sig["high"], macd, hi), n)
                cand = (ok is True)
            if cand:
                pos, ep = 1, float(c.iloc[i + 1])
        elif bool(sig["CS"].iloc[i] or sig["revSell"].iloc[i]):
            trades.append(float(c.iloc[i + 1]) / ep - 1)
            pos = 0
    eqc = np.array(curve)
    dd = float((eqc / np.maximum.accumulate(eqc) - 1).min() * 100)
    return {"dd": dd, "n": len(trades)}


def marker_quality_set(res) -> dict:
    """date -> quality for buy/rebuy markers (for churn comparison)."""
    if not res:
        return {}
    return {m["date"]: m.get("quality") for m in res["markers"] if m["type"] in ("buy", "rebuy")}


def section_signal_impact(files: list[str]) -> None:
    rows, flips_t, flips_r, buys_tot = [], 0, 0, 0
    for fp in files:
        t = pathlib.Path(fp).stem
        try:
            df = pd.read_parquet(fp)
            close = df["close"].dropna()
            th, tl = df["high"], df["low"]
            rec = reconstruct_ohlc(close)
            raw = sim_dd(close, filtered=False)
            fc = sim_dd(close, None, None, True)
            ft = sim_dd(close, th, tl, True)
            fr = sim_dd(close, rec["high"], rec["low"], True)
            if not all([raw, fc, ft, fr]):
                continue
            rows.append((raw["dd"], fc["dd"], ft["dd"], fr["dd"]))
            # marker churn
            mc = marker_quality_set(analyze(t, close))
            mt = marker_quality_set(analyze(t, close, th, tl))
            mr = marker_quality_set(analyze(t, close, rec["high"], rec["low"]))
            for dt, q in mc.items():
                buys_tot += 1
                if mt.get(dt) != q:
                    flips_t += 1
                if mr.get(dt) != q:
                    flips_r += 1
        except Exception:
            continue
    arr = np.array(rows)
    A = lambda j: float(arr[:, j].mean())
    better = lambda j: float((arr[:, j] > arr[:, 0]).mean() * 100)  # filtered dd shallower than raw
    print("\n" + "=" * 78)
    print(f"B. SIGNAL IMPACT — buy-filter max-drawdown by swing/div source  (n={len(rows)} US names)")
    print("=" * 78)
    print(f"  avg max-DD  RAW (unfiltered):      {A(0):7.1f}%")
    print(f"  avg max-DD  FILTERED close-based:  {A(1):7.1f}%   (shallower than raw on {better(1):.0f}% of names)")
    print(f"  avg max-DD  FILTERED true-OHLC:    {A(2):7.1f}%   (shallower than raw on {better(2):.0f}% of names)")
    print(f"  avg max-DD  FILTERED recon-OHLC:   {A(3):7.1f}%   (shallower than raw on {better(3):.0f}% of names)")
    print(f"  buy/rebuy markers compared: {buys_tot}")
    print(f"  quality flips close->true:  {flips_t} ({100*flips_t/max(buys_tot,1):.1f}%)   "
          f"close->recon: {flips_r} ({100*flips_r/max(buys_tot,1):.1f}%)")
    print("  -> high-based drawdown should be ~= close-based (no degradation) and churn small.")


# ─────────────────────────────── C. HK stability ─────────────────────────────
def load_tencent() -> pd.Series:
    d = json.loads((ROOT / "site/hkstockdata/0700.HK.json").read_text())["chart"]
    return pd.Series(d["c"], index=pd.to_datetime(d["t"]), dtype=float).dropna()


def load_baba() -> pd.Series:
    return pd.read_parquet(ROOT / "data/yahoo/BABA.parquet")["close"].dropna()


def section_hk_stability() -> None:
    print("\n" + "=" * 78)
    print("C. HK / close-only STABILITY — markers: close-only vs reconstructed-high")
    print("=" * 78)
    for name, close in (("TENCENT 0700.HK", load_tencent()), ("BABA", load_baba())):
        rec = reconstruct_ohlc(close)
        base = analyze(name, close)
        recd = analyze(name, close, rec["high"], rec["low"])
        if not base or not recd:
            print(f"  {name}: thin history"); continue
        b = {(m["date"], m["type"]): m.get("quality") for m in base["markers"]}
        r = {(m["date"], m["type"]): m.get("quality") for m in recd["markers"]}
        same_dates = set(b) == set(r)
        flips = [(k, b[k], r.get(k)) for k in b if r.get(k) != b[k]]
        print(f"  {name}: markers close-only={len(base['markers'])} recon={len(recd['markers'])}  "
              f"same marker dates={same_dates}  quality flips={len(flips)}")
        for k, bq, rq in flips[:8]:
            print(f"      {k[0]} {k[1]}: {bq} -> {rq}")
        # recent buy/rebuy detail for manual eyeballing
        recent = [m for m in recd["markers"] if m["type"] in ("buy", "rebuy")][-6:]
        print("      recent recon buy/rebuy: " +
              ", ".join(f"{m['date']}:{m['quality']}" for m in recent))


if __name__ == "__main__":
    files = sorted(glob.glob(str(STOCKS / "*.parquet")))
    section_accuracy(files)
    section_signal_impact(files)
    section_hk_stability()
