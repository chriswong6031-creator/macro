"""DIAGNOSTIC v5 — cross-sectional EXIT-rule bake-off (the §3 generalization gate).

Same VALIDATED entry for every arm (refined_buy TAKE on CB|revBuy); vary ONLY the exit.
We isolate the exit's effect and judge it the charter way: equity max-drawdown, shake-out
rate, avg-loss, expectancy, capture-guardrail -- NEVER total-return / beat-buy&hold.
Aggregate CROSS-SECTIONALLY (% of held-out names improved), not pooled means.

Exit policies (the fast-reversal `cut` = revSell stays ON in every arm; we only swap the
`sell` trigger):
  OSC      baseline: oscillator SELL* (CS)                      [close-only, current prod]
  EMA8/13/21  structural trail: close < EMA(close, span)        [close-only]
  CHAND    Chandelier: close < highHigh_since_entry - 3*ATR22   [needs high/low]
  CHAND_C  close-only Chandelier proxy (ATR from |Dclose|)      [close-only fallback]

Entries are FIXED so this is a clean exit ablation (NOT the killed regime/exit router -- a
single fixed exit per arm, never per-ticker, never regime-routed). Re-buy is the engine's
own revBuy reversal in all arms.

Run:  python3 research/signal_engine/diagnose_v5_exits.py [SINCE=2023-06-01]
Dumps per-name x per-policy metrics + archetype features to _exit_panel.json for audit.
"""
from __future__ import annotations

import sys
import glob
import json
import pathlib
import warnings
import logging

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
logging.disable(logging.CRITICAL)

from confluence import compute_signals
from diagnose_tencent_baba import swing_points, divergence_at
from diagnose_v2 import refined_buy

DATA = pathlib.Path(__file__).resolve().parents[2] / "data" / "stocks"
OUT = pathlib.Path(__file__).resolve().parent / "_exit_panel.json"
ATR_N, K_CH = 22, 3.0
EMA_SPANS = (8, 13, 21)
DIAG_NAMES = {"JNJ", "LLY", "WMT", "MCD", "NVDA"}   # the hand-examined exit cases
SHAKE_K, SHAKE_BUF = 8, 0.05                          # premature-exit window / buffer

POLICIES = ["OSC", "EMA8", "EMA13", "EMA21", "CHAND", "CHAND_C"]


def build(ticker: str):
    """Production-faithful 3D signals + 3D high/low ATR + close-only trailing trends."""
    df = pd.read_parquet(DATA / f"{ticker}.parquet")
    close = df["close"].dropna()
    sig = compute_signals(close)
    if sig.empty:
        return None
    sig = sig.dropna(subset=["macd", "sig", "k", "d", "rsi14"]).copy()
    if len(sig) < 40:
        return None
    c3 = sig["close"]
    # true 3D OHLC ATR on the SAME 3B bins compute_signals used
    h3 = df["high"].resample("3B").max().reindex(sig.index)
    l3 = df["low"].resample("3B").min().reindex(sig.index)
    tr = pd.concat([h3 - l3, (h3 - c3.shift()).abs(), (l3 - c3.shift()).abs()], axis=1).max(axis=1)
    sig["atr"] = tr.ewm(alpha=1 / ATR_N, min_periods=ATR_N).mean()
    sig["high3"] = h3
    # close-only ATR proxy (no high/low): EWMA of |Dclose|
    sig["atr_c"] = c3.diff().abs().ewm(alpha=1 / ATR_N, min_periods=ATR_N).mean()
    for span in EMA_SPANS:
        sig[f"ema{span}"] = c3.ewm(span=span, min_periods=span).mean()
    return sig


def _exit_hit(policy, sig, i, hh, hh_c):
    """Does the SELL trigger fire on completed bar i? (cut=revSell handled by caller)."""
    c = sig["close"]
    if policy == "OSC":
        return bool(sig["CS"].iloc[i])
    if policy.startswith("EMA"):
        span = int(policy[3:])
        return bool(c.iloc[i] < sig[f"ema{span}"].iloc[i])
    if policy == "CHAND":
        return bool(c.iloc[i] < hh - K_CH * float(sig["atr"].iloc[i]))
    if policy == "CHAND_C":
        return bool(c.iloc[i] < hh_c - K_CH * float(sig["atr_c"].iloc[i]))
    raise ValueError(policy)


def sim(sig, policy, since, hi, lo):
    """Long/flat as traded: enter filtered-TAKE, exit on policy SELL or revSell cut,
    re-buy on revBuy. Fills next bar close (leak-free). Returns charter metrics."""
    c, macd, idx, n = sig["close"], sig["macd"], sig.index, len(sig)
    pos = 0; ep = None; ei = None; hh = None; hh_c = None
    trades = []           # (ret, exit_idx, exit_price, trade_peak)
    eq = 1.0; curve = [1.0]
    for i in range(n - 1):
        if pos == 1:
            eq *= float(c.iloc[i + 1]) / float(c.iloc[i])
        curve.append(eq)
        if pos == 0:
            if idx[i] < since:
                continue
            cand = bool(sig["CB"].iloc[i] or sig["revBuy"].iloc[i])
            if cand:
                cand = refined_buy(i, sig, divergence_at(i, c, macd, hi, lo), n)[0] == "TAKE"
            if cand:
                pos, ep, ei = 1, float(c.iloc[i + 1]), i + 1
                hh = float(sig["high3"].iloc[i + 1]); hh_c = float(c.iloc[i + 1])
        else:
            hh = max(hh, float(sig["high3"].iloc[i])); hh_c = max(hh_c, float(c.iloc[i]))
            ex = _exit_hit(policy, sig, i, hh, hh_c) or bool(sig["revSell"].iloc[i])
            if ex:
                xp = float(c.iloc[i + 1]); peak = float(c.iloc[ei:i + 2].max())
                trades.append((xp / ep - 1, i + 1, xp, peak)); pos = 0
    if pos == 1:
        xp = float(c.iloc[-1]); peak = float(c.iloc[ei:].max())
        trades.append((xp / ep - 1, n - 1, xp, peak))
    if not trades:
        return None
    rets = np.array([t[0] for t in trades])
    losses = rets[rets < 0]
    eqc = np.array(curve)
    dd = (eqc / np.maximum.accumulate(eqc) - 1).min()
    cv = c.to_numpy()
    shakes = shakes_pk = 0
    for _, xi, xp, peak in trades:
        fwd = cv[xi + 1: xi + 1 + SHAKE_K]
        if not len(fwd):
            continue
        if fwd.max() >= xp * (1 + SHAKE_BUF):   # exit then bounce >= buf above exit
            shakes += 1
        if fwd.max() >= peak:                    # exit then exceed the trade's own peak (true shake-out)
            shakes_pk += 1
    return {"n": len(trades), "wr": round(100 * (rets > 0).mean(), 1),
            "dd": round(100 * dd, 1), "cap": round(100 * (eqc[-1] - 1), 1),
            "avgloss": round(100 * losses.mean(), 2) if len(losses) else 0.0,
            "expect": round(100 * rets.mean(), 2),
            "shake": round(100 * shakes / len(trades), 1),
            "shake_pk": round(100 * shakes_pk / len(trades), 1)}


def features(sig):
    """Persistent archetype properties (charter-blessed primitives): trendiness + vol."""
    c = sig["close"].to_numpy()
    n = 10
    er = []
    for i in range(n, len(c)):
        denom = np.abs(np.diff(c[i - n:i + 1])).sum()
        er.append(abs(c[i] - c[i - n]) / denom if denom else np.nan)
    eff = float(np.nanmedian(er)) if er else np.nan         # Kaufman efficiency ratio
    atrpct = float((sig["atr"] / sig["close"]).median())     # ATR% of price
    return {"eff": round(eff, 3), "atrpct": round(100 * atrpct, 2)}


def pct_improved(rows, pol, key, base="OSC", lower_is_better=True):
    """% of names where `pol` beats `base` on metric `key` (dd/avgloss: less-negative = better)."""
    out = []
    for r in rows:
        b, p = r["m"].get(base), r["m"].get(pol)
        if not b or not p:
            continue
        if key in ("dd", "avgloss"):       # less negative (closer to 0) = better
            out.append(p[key] > b[key])
        elif lower_is_better:              # shake: lower = better
            out.append(p[key] < b[key])
        else:                               # cap/expect: higher = better
            out.append(p[key] > b[key])
    return 100 * np.mean(out) if out else float("nan"), len(out)


def med(rows, pol, key):
    vals = [r["m"][pol][key] for r in rows if r["m"].get(pol)]
    return float(np.median(vals)) if vals else float("nan")


def _capkeep(rows, pol):
    keep = []
    for r in rows:
        b, p = r["m"].get("OSC"), r["m"].get(pol)
        if b and p:
            keep.append(p["cap"] >= (b["cap"] * 0.8 if b["cap"] > 0 else b["cap"] - 5))
    return 100 * np.mean(keep) if keep else float("nan")


def _joint(rows, pol):
    """% names where DD improves AND capture not gutted (the real ship gate)."""
    ok = []
    for r in rows:
        b, p = r["m"].get("OSC"), r["m"].get(pol)
        if b and p:
            cap_ok = p["cap"] >= (b["cap"] * 0.8 if b["cap"] > 0 else b["cap"] - 5)
            ok.append(p["dd"] > b["dd"] and cap_ok)
    return 100 * np.mean(ok) if ok else float("nan")


def panel(rows, label):
    print(f"\n================ {label}  (n={len(rows)}) ================")
    print(f"{'policy':8s}{'medDD':>8s}{'medShkPk':>9s}{'medLoss':>9s}{'medExp':>8s}"
          f"{'medCap':>8s}{'medN':>6s}{'DD>b%':>7s}{'ShkPk<b%':>9s}{'Cap_ok%':>8s}{'JOINT%':>8s}")
    print("-" * 90)
    for pol in POLICIES:
        ddp, _ = pct_improved(rows, pol, "dd")
        shp, _ = pct_improved(rows, pol, "shake_pk")
        tag = "  <= baseline" if pol == "OSC" else ("  <-- GATE: need DD>b & JOINT >= 70" if pol == "EMA8" else "")
        print(f"{pol:8s}{med(rows,pol,'dd'):>8.1f}{med(rows,pol,'shake_pk'):>9.1f}"
              f"{med(rows,pol,'avgloss'):>9.1f}{med(rows,pol,'expect'):>8.1f}"
              f"{med(rows,pol,'cap'):>8.0f}{med(rows,pol,'n'):>6.0f}"
              f"{ddp:>7.0f}{shp:>9.0f}{_capkeep(rows,pol):>8.0f}{_joint(rows,pol):>8.0f}{tag}")


def tail_panel(rows):
    """Owner's real fear is the TAIL ('one missed sell -> 80% tumble'). Among the
    deepest-baseline-DD quartile, does any trailing stop rescue drawdown?"""
    dds = sorted(r["m"]["OSC"]["dd"] for r in rows)
    cut = np.percentile(dds, 25)            # 25th pct of dd (most negative quartile)
    tail = [r for r in rows if r["m"]["OSC"]["dd"] <= cut]
    print(f"\n---- TAIL: deepest-DD quartile (baseline DD <= {cut:.1f}%, n={len(tail)}) ----")
    print(f"{'policy':8s}{'medDD':>8s}{'DD>base%':>10s}{'medCap':>8s}")
    for pol in POLICIES:
        ddp, _ = pct_improved(tail, pol, "dd")
        print(f"{pol:8s}{med(tail,pol,'dd'):>8.1f}{ddp:>10.0f}{med(tail,pol,'cap'):>8.0f}")


def archetype_split(rows):
    """Where does the lead candidate help vs hurt? Split by trendiness (efficiency)."""
    valid = [r for r in rows if not np.isnan(r["f"]["eff"])]
    effs = sorted(r["f"]["eff"] for r in valid)
    if not effs:
        return
    q1, q3 = np.percentile(effs, 33), np.percentile(effs, 67)
    buckets = {"choppy (low eff)": [r for r in valid if r["f"]["eff"] <= q1],
               "mid": [r for r in valid if q1 < r["f"]["eff"] < q3],
               "steep-grind (high eff)": [r for r in valid if r["f"]["eff"] >= q3]}
    print(f"\n---- archetype split by Kaufman efficiency (cut {q1:.2f}/{q3:.2f}) ----")
    print(f"{'bucket':24s}{'n':>4s}", end="")
    for pol in ("EMA13", "EMA21", "CHAND"):
        print(f"{pol+'_DD>base%':>16s}", end="")
    print()
    for name, br in buckets.items():
        print(f"{name:24s}{len(br):>4d}", end="")
        for pol in ("EMA13", "EMA21", "CHAND"):
            p, _ = pct_improved(br, pol, "dd")
            print(f"{p:>16.0f}", end="")
        print()


def main():
    since = pd.Timestamp(sys.argv[1]) if len(sys.argv) > 1 else pd.Timestamp("2023-06-01")
    rows = []
    for fp in sorted(glob.glob(str(DATA / "*.parquet"))):
        t = pathlib.Path(fp).stem
        try:
            sig = build(t)
            if sig is None:
                continue
            hi, lo = swing_points(sig["close"])
            m = {p: sim(sig, p, since, hi, lo) for p in POLICIES}
            if not m.get("OSC"):
                continue
            rows.append({"t": t, "m": m, "f": features(sig)})
        except Exception as e:
            print(f"  skip {t}: {e}")
            continue
    OUT.write_text(json.dumps(rows, separators=(",", ":")))
    print(f"\nSINCE={since.date()}  names={len(rows)}  (dumped per-name -> {OUT.name})")
    panel(rows, "ALL US names (all held-out: filter designed on Tencent/BABA)")
    held = [r for r in rows if r["t"] not in DIAG_NAMES]
    panel(held, "STRICT held-out (excl 5 hand-examined exit cases)")
    tail_panel(held)
    archetype_split(rows)


if __name__ == "__main__":
    main()
