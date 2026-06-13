"""RESEARCH ONLY — prototype + backtest of a multi-faceted ENTRY-CONVICTION score.

Question we're testing (the user's idea): can we score *how good THIS moment is*
for entry — not just "indicators line up" but weighting (a) how close we are to the
momentum cross in TIME (approaching → just-crossed → decaying as days pass), (b) how
close price is to the cycle LOW (buying near the bottom, not chasing), and (c) whether
a clear bottoming PROCESS is arching up (accumulation)? Mirror for tops/shorts.

The honest test, in this project's style: bin the score across history and measure
FORWARD outcomes — return, max adverse excursion (MAE = the drawdown you'd sit
through), and return-to-MAE (risk-adjusted entry quality). If higher conviction →
better risk-adjusted entry (esp. smaller MAE near the low), the idea "works".

Run: python -m scripts.research_conviction
"""
from __future__ import annotations

import glob
import math
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

from engine.cycles import (  # noqa: E402
    _tf_state, cycle_state, early_signals, ladder_state, macd_parts, regime_state,
)


# ---- small shape helpers ----------------------------------------------------

def _ramp(x, x0, x1, y0=0.0, y1=1.0):
    if x1 == x0:
        return y1 if x >= x1 else y0
    t = (x - x0) / (x1 - x0)
    return y0 + (y1 - y0) * max(0.0, min(1.0, t))


def _cross_ages(hist: pd.Series) -> tuple[int | None, int | None]:
    """Bars since the most recent up-cross (≤0→>0) and down-cross of the histogram."""
    h = hist.dropna().to_numpy()
    if len(h) < 3:
        return None, None
    pos = h > 0
    up = dn = None
    for k in range(len(h) - 1, 0, -1):
        if up is None and pos[k] and not pos[k - 1]:
            up = len(h) - 1 - k
        if dn is None and not pos[k] and pos[k - 1]:
            dn = len(h) - 1 - k
        if up is not None and dn is not None:
            break
    return up, dn


# ---- the candidate conviction score -----------------------------------------

W_TIME, W_PRICE, W_ARCH, W_TECH = 0.34, 0.30, 0.22, 0.14   # time + price dominate
TAU = 6.0   # momentum-cross freshness decay (trading days)


def _time_factor(d, hist, want_up: bool) -> float:
    """Peaks just AFTER the momentum cross; rises as we approach it; decays with age."""
    up_age, dn_age = _cross_ages(hist)
    if want_up:
        if d.get("macd_pos"):                      # already crossed up — decay by age
            a = up_age if up_age is not None else (1 if d.get("macd_cross_up") else 4)
            return math.exp(-a / TAU)
        if d.get("macd_cross_up"):
            return 1.0
        if d.get("macd_approaching_up") and d.get("macd_bars_to_cross"):
            return 0.60 * _ramp(d["macd_bars_to_cross"], 8, 0)   # closer → higher
        if d.get("macd_curl_up"):
            return 0.38
        return 0.0
    else:
        if not d.get("macd_pos"):                  # already crossed down — decay by age
            a = dn_age if dn_age is not None else (1 if d.get("macd_cross_dn") else 4)
            return math.exp(-a / TAU)
        if d.get("macd_cross_dn"):
            return 1.0
        if d.get("macd_approaching_dn") and d.get("macd_bars_to_cross"):
            return 0.60 * _ramp(d["macd_bars_to_cross"], 8, 0)
        if d.get("macd_curl_dn"):
            return 0.38
        return 0.0


def _price_prox(pct: float, want_up: bool) -> float:
    """Closeness to the pivot. Long: best just above the low (lifted, not chasing)."""
    if not want_up:
        pct = -pct   # for tops, distance BELOW the high mirrors distance above the low
    if pct < -0.02:
        return 0.15                      # pivot not holding (broke below the low)
    if pct < 0.0:
        return _ramp(pct, -0.02, 0.0, 0.55, 0.85)
    if pct <= 0.05:
        return _ramp(pct, 0.0, 0.05, 0.85, 1.0)   # the sweet spot: just lifted off
    return _ramp(pct, 0.05, 0.20, 1.0, 0.0)        # decays as it runs away (chasing)


def _slope(close: pd.Series, n: int = 7) -> float:
    s = close.dropna().iloc[-n:]
    if len(s) < n:
        return 0.0
    x = np.arange(len(s))
    b = np.polyfit(x, s.to_numpy(), 1)[0]
    return float(b / s.mean())   # normalized slope per bar


def _arch(close, cyc, d, early, want_up: bool) -> float:
    sl = _slope(close)
    if want_up:
        a = 0.0
        if cyc.get("swing_low") or cyc.get("cand_swing"):
            a += 0.30
        if cyc.get("above_ma10"):
            a += 0.20
        if cyc.get("ma10_rising"):
            a += 0.25
        if early.get("dir") == "up":
            a += 0.25
        a += 0.20 * _ramp(sl, 0.0, 0.004)          # gently arching up (not vertical)
        if sl > 0.012:
            a -= 0.15                               # too vertical = already ran
        return max(0.0, min(1.0, a))
    else:
        a = 0.0
        if not cyc.get("above_ma10"):
            a += 0.30
        if not cyc.get("ma10_rising"):
            a += 0.20
        if early.get("dir") == "down":
            a += 0.25
        a += 0.20 * _ramp(-sl, 0.0, 0.004)
        return max(0.0, min(1.0, a))


def _tech(d, cyc, want_up: bool) -> float:
    r = d.get("rsi14") or 50
    t = 0.0
    if want_up:
        if cyc.get("above_ma10"):
            t += 0.3
        t += 0.35 * _ramp(r, 35, 55) * _ramp(70, r, 60)   # constructive, not overbought
        if d.get("macd_pos"):
            t += 0.35
    else:
        if not cyc.get("above_ma10"):
            t += 0.3
        t += 0.35 * _ramp(65, r, 45) * _ramp(r, 30, 40)
        if not d.get("macd_pos"):
            t += 0.35
    return max(0.0, min(1.0, t))


def _gate(cyc, regime, pct, want_up: bool) -> float:
    reg = regime.get("regime", "neutral")
    if want_up:
        g = {"bull": 1.0, "neutral": 0.7, "bear": 0.35}[reg]
        if cyc.get("failed_cycle"):
            g *= 0.25
        if cyc.get("ic_failed"):
            g *= 0.6
        if pct < -0.02:
            g *= 0.4
    else:
        g = {"bear": 1.0, "neutral": 0.7, "bull": 0.35}[reg]
        if pct > 0.02:
            g *= 0.4
    return g


def conviction(close, cyc, mtf, early, regime) -> dict:
    """Signed entry-timing conviction in [-100, +100] (long positive)."""
    d = mtf.get("D", {})
    if not d or not cyc:
        return {"score": 0.0, "long": 0.0, "short": 0.0}
    hist = macd_parts(close.dropna())["hist"]
    price = float(close.dropna().iloc[-1])
    low = cyc.get("cand_price") or cyc.get("dcl_price") or price
    pct_low = price / low - 1.0
    # recent cycle high for the short side
    look = max(25, int(cyc.get("dc_day") or 25))
    hi = float(close.dropna().iloc[-look:].max())
    pct_hi = price / hi - 1.0

    up = (W_TIME * _time_factor(d, hist, True) + W_PRICE * _price_prox(pct_low, True)
          + W_ARCH * _arch(close, cyc, d, early, True) + W_TECH * _tech(d, cyc, True))
    up *= _gate(cyc, regime, pct_low, True)
    dn = (W_TIME * _time_factor(d, hist, False) + W_PRICE * _price_prox(pct_hi, False)
          + W_ARCH * _arch(close, cyc, d, early, False) + W_TECH * _tech(d, cyc, False))
    dn *= _gate(cyc, regime, pct_hi, False)
    return {"score": float(np.clip((up - dn) * 100, -100, 100)),
            "long": up * 100, "short": dn * 100, "pct_low": pct_low}


# ---- backtest ---------------------------------------------------------------

def _pieces(sub: pd.Series):
    cyc = cycle_state(sub)
    if not cyc:
        return None
    mtf = {"D": _tf_state(sub),
           "3D": _tf_state(sub.resample("3B").last().dropna()),
           "W": _tf_state(sub.resample("W-FRI").last().dropna())}
    early = early_signals(sub, cyc, mtf)
    regime = regime_state(cyc, mtf)
    lad = ladder_state(cyc, mtf, early)
    return cyc, mtf, early, regime, lad


FEATURE_CACHE = "data/regime/_conviction_features.parquet"


def collect(step: int = 6, max_names: int = 110, tail: int = 0) -> pd.DataFrame:
    """Walk history once, store per-sample features + multi-horizon forward
    outcomes, so the lever analyses below can iterate without re-walking."""
    files = sorted(glob.glob("data/stocks/*.parquet"))[:max_names]
    H = (21, 42, 63)
    rows = []
    for f in files:
        c = pd.read_parquet(f)["close"].dropna()
        if tail:
            c = c.iloc[-tail:]
        if len(c) < 700:
            continue
        cv = c.to_numpy()
        for i in range(400, len(c) - max(H), step):
            sub = c.iloc[max(0, i - 600):i + 1]
            p = _pieces(sub)
            if p is None:
                continue
            cyc, mtf, early, regime, lad = p
            d = mtf.get("D", {})
            hist = macd_parts(sub)["hist"]
            up_age, dn_age = _cross_ages(hist)
            conv = conviction(sub, cyc, mtf, early, regime)
            base = cv[i]
            rec = {
                "conv": conv["score"], "lad": lad.get("score", 0),
                "state": lad.get("state", ""),
                "macd_pos": bool(d.get("macd_pos")),
                "up_age": up_age if d.get("macd_pos") else np.nan,
                "dn_age": dn_age if not d.get("macd_pos") else np.nan,
                "pct_low": conv.get("pct_low", np.nan),
                "low_age": cyc.get("cand_age") if cyc.get("cand_price") else cyc.get("dc_day"),
                "late": cyc.get("dc_phase") in ("approaching_band", "in_band", "stretched"),
                "swing": bool(cyc.get("swing_low") or cyc.get("cand_swing")),
                "above_ma10": bool(cyc.get("above_ma10")),
                "ma10_rising": bool(cyc.get("ma10_rising")),
                "div_bull": early.get("dir") == "up",
                "regime": regime.get("regime", "neutral"),
                "rsi": d.get("rsi14"),
            }
            for h in H:
                w = cv[i + 1: i + 1 + h]
                rec[f"ret{h}"] = w[-1] / base - 1.0
                rec[f"mae{h}"] = w.min() / base - 1.0
                rec[f"mfe{h}"] = w.max() / base - 1.0
            rows.append(rec)
    df = pd.DataFrame(rows)
    df.to_parquet(FEATURE_CACHE)
    print(f"collected {len(df):,} samples from {len(files)} names → {FEATURE_CACHE}")
    return df


def _band(df, col, edges, h, extra=None, want="up"):
    label = f"{col}" + (f" [{extra}]" if extra else "")
    print(f"\n{label} — forward {h}d  (n / hit% / avgRet% / medRet% / avgMAE% / ret÷|MAE|):")
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = df[(df[col] >= lo) & (df[col] < hi)]
        if len(m) < 40:
            print(f"  {lo:>6}–{hi:<6} n={len(m):<5} (too few)")
            continue
        ret, mae = m[f"ret{h}"], m[f"mae{h}"]
        rmae = ret.mean() / abs(mae.mean()) if mae.mean() else float("nan")
        hitcol = (ret > 0) if want == "up" else (ret < 0)
        print(f"  {lo:>6}–{hi:<6} n={len(m):<5} {100*hitcol.mean():>5.1f} "
              f"{100*ret.mean():>7.2f} {100*ret.median():>7.2f} "
              f"{100*mae.mean():>7.2f} {rmae:>6.2f}")


def levers(df: pd.DataFrame) -> None:
    """Test each of the user's intuitions IN ISOLATION."""
    print("\n" + "=" * 78)
    print("LEVER A — FRESHNESS: among already-crossed-up names, does a FRESHER")
    print("daily MACD up-cross give a better entry? (bins = trading days since cross)")
    up = df[df.macd_pos & df.up_age.notna()]
    for h in (21, 42, 63):
        _band(up, "up_age", [0, 2, 5, 10, 20, 99], h)

    print("\n" + "=" * 78)
    print("LEVER B — PRICE PROXIMITY: among bottoming setups (late cycle & swing low),")
    print("does buying NEARER the cycle low improve risk (smaller MAE, better ret/MAE)?")
    bot = df[df.late & df.swing & df.pct_low.notna()]
    for h in (21, 42, 63):
        _band(bot, "pct_low", [-0.05, 0.0, 0.02, 0.05, 0.10, 0.20, 1.0], h)

    print("\n" + "=" * 78)
    print("LEVER C — BOTTOMING ARCH: does 'swing low + 10d MA turning up' (accumulation)")
    print("beat its absence, among late-cycle names?")
    late = df[df.late]
    for h in (21, 42, 63):
        arch = late[late.swing & late.above_ma10 & late.ma10_rising]
        flat = late[~(late.swing & late.above_ma10 & late.ma10_rising)]
        for nm, m in [("ARCH up", arch), ("no arch", flat)]:
            if len(m) < 40:
                continue
            ret, mae = m[f"ret{h}"], m[f"mae{h}"]
            print(f"  {h}d {nm:>8}: n={len(m):<5} hit {100*(ret>0).mean():>5.1f}%  "
                  f"avgRet {100*ret.mean():>6.2f}%  MAE {100*mae.mean():>6.2f}%  "
                  f"ret/|MAE| {ret.mean()/abs(mae.mean()) if mae.mean() else 0:>5.2f}")

    print("\n" + "=" * 78)
    print("LEVER D — REGIME GATE: same bottoming arch, split by higher-TF regime")
    archonly = df[df.late & df.swing & df.above_ma10 & df.ma10_rising]
    for h in (21, 42, 63):
        for reg in ("bull", "neutral", "bear"):
            m = archonly[archonly.regime == reg]
            if len(m) < 40:
                continue
            ret, mae = m[f"ret{h}"], m[f"mae{h}"]
            print(f"  {h}d {reg:>8}: n={len(m):<5} hit {100*(ret>0).mean():>5.1f}%  "
                  f"avgRet {100*ret.mean():>6.2f}%  MAE {100*mae.mean():>6.2f}%  "
                  f"ret/|MAE| {ret.mean()/abs(mae.mean()) if mae.mean() else 0:>5.2f}")


def uptrend_test(df: pd.DataFrame) -> None:
    """THE decisive test: 'buy the dip in an uptrend'. Within a confirmed
    higher-timeframe uptrend (regime=bull), does buying NEARER the cycle low +
    FRESH carry real forward RETURN (not just smaller drawdown)? If yes, the
    user's accumulation thesis + the trend factor reconcile into a real score."""
    print("\n" + "=" * 78)
    print("DECISIVE TEST — 'BUY THE DIP IN AN UPTREND' (regime=bull only):")
    print("Within bull regime, bin by proximity-to-low; does near-the-low win on RETURN?")
    bull = df[(df.regime == "bull") & df.pct_low.notna()]
    for h in (21, 42, 63):
        _band(bull, "pct_low", [-0.05, 0.0, 0.03, 0.06, 0.12, 0.25, 1.0], h)

    print("\nContrast — same bins in NON-uptrend (regime!=bull):")
    nb = df[(df.regime != "bull") & df.pct_low.notna()]
    for h in (42, 63):
        _band(nb, "pct_low", [-0.05, 0.0, 0.03, 0.06, 0.12, 0.25, 1.0], h)

    print("\nFreshness WITHIN bull regime + near low (<6% above low):")
    nl = bull[bull.pct_low < 0.06]
    for h in (42, 63):
        _band(nl[nl.macd_pos & nl.up_age.notna()], "up_age", [0, 3, 8, 16, 30, 99], h)


def _rankcorr(a: pd.Series, b: pd.Series) -> float:
    """Spearman via ranks + numpy (avoids a scipy dependency)."""
    m = a.notna() & b.notna()
    if m.sum() < 30:
        return float("nan")
    ra, rb = a[m].rank(), b[m].rank()
    return float(np.corrcoef(ra, rb)[0, 1])


def report(df: pd.DataFrame) -> None:
    print("\n" + "=" * 78)
    print(f"BLEND CHECK — current conviction() score vs forward outcomes "
          f"({len(df):,} samples)")
    for h in (21, 42, 63):
        _band(df[df.conv > 0], "conv", [0, 20, 40, 55, 70, 101], h)
    print("\nSHORT side (score<0 → price should FALL), forward 42d:")
    s = df[df.conv < 0].copy(); s["mag"] = -s.conv
    _band(s, "mag", [0, 20, 40, 55, 101], 42, want="down")

    print("\nDiscrimination (rank corr with forward 42d outcomes, long side):")
    for col, name in [("conv", "NEW conviction"), ("lad", "old ladder score")]:
        sub = df[df[col] > 0]
        print(f"  {name:>16}: vs ret {_rankcorr(sub[col], sub.ret42):+.3f} | "
              f"vs MAE {_rankcorr(sub[col], sub.mae42):+.3f} "
              f"(MAE+ ⇒ higher score sits through SMALLER drawdown)")


if __name__ == "__main__":
    import os
    if os.path.exists(FEATURE_CACHE):
        df = pd.read_parquet(FEATURE_CACHE)
        print(f"loaded {len(df):,} cached samples from {FEATURE_CACHE}")
    else:
        df = collect(step=6, max_names=110, tail=3500)
    levers(df)
    report(df)
