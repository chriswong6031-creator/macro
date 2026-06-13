"""RESEARCH PROTOTYPE — does a trend-strength gate sharpen momentum signals?

Hypothesis (Tier-1 #4 from the signal-accuracy roadmap): a long-momentum signal's
forward edge is concentrated in TRENDING regimes and decays/inverts in CHOP. If so,
gating momentum by Kaufman's Efficiency Ratio (ER) should raise hit-rate and shrink
the bad-case drawdown — directly addressing the repo's measured "momentum directional
pre-2021, weaker post" finding.

Method follows the house rules:
- Cross-asset panel (equities + commodities + crypto) from the parquet store.
- Momentum proxy = 126-day return > 0 (canonical 6-month trend; stands in for the
  engine's MACD/trend votes).
- Regime = Kaufman Efficiency Ratio over 20 bars (|net move| / sum|bar moves|),
  0=pure chop .. 1=pure trend. Close-only, so it covers every instrument.
- Judge BOTH forward 21d return (hit% / avg) AND forward 21d drawdown (median /
  10th-pctile) — the D43 lens: the win may be smaller dips, not higher avg.
- Split-half by calendar (pre/post 2019-01-01) for robustness — only a result that
  holds in BOTH halves is trusted.

NOT wired into the engine/UI — this prints a verdict so the idea is measured first.

Usage: .venv/bin/python -m scripts.research_trend_gate
"""
from __future__ import annotations

import glob
import os

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOM_LB = 126        # 6-month momentum lookback
ER_N = 20           # efficiency-ratio window
FWD = 21            # forward horizon (trading days) — repo's equity horizon
STEP = 5            # weekly sampling
SPLIT = "2019-01-01"
MIN_ROWS = 600

# instruments to skip: vol indices, rates, dollar (momentum is meaningless/mean-revert)
SKIP = {"_VIX", "_VIX3M", "_VIX9D", "_MOVE", "ZQ_F", "DX-Y.NYB"}
CRYPTO = {"BTC-USD", "ETH-USD", "SOL-USD"}
COMMOD = {"GC_F", "SI_F", "CL_F", "HG_F", "BZ_F"}


def efficiency_ratio(close: pd.Series, n: int = ER_N) -> pd.Series:
    change = close.diff(n).abs()
    volatility = close.diff().abs().rolling(n).sum()
    return change / volatility.replace(0, np.nan)


def fwd_return(close: pd.Series, h: int) -> pd.Series:
    return close.pct_change(h).shift(-h)


def fwd_drawdown(close: pd.Series, h: int) -> pd.Series:
    """Worst close-to-low over the next h bars (max adverse excursion)."""
    fwd_low = close.shift(-1).rolling(h).min().shift(-(h - 1))
    return fwd_low / close - 1.0


def asset_class(name: str) -> str:
    if name in CRYPTO:
        return "crypto"
    if name in COMMOD:
        return "commodity"
    return "equity"


def load_panel() -> dict[str, pd.Series]:
    panel: dict[str, pd.Series] = {}
    for d in ("data/yahoo", "data/stocks"):
        for f in glob.glob(os.path.join(ROOT, d, "*.parquet")):
            name = os.path.basename(f)[:-8]
            if name in SKIP:
                continue
            try:
                df = pd.read_parquet(f)
            except Exception:  # noqa: BLE001
                continue
            if "close" not in df.columns or len(df) < MIN_ROWS:
                continue
            panel[name] = df["close"].dropna()
    return panel


def collect(panel: dict[str, pd.Series]) -> pd.DataFrame:
    """One row per (asset, weekly date) where the momentum-long signal is ON."""
    rows = []
    for name, close in panel.items():
        mom = close.pct_change(MOM_LB)
        er = efficiency_ratio(close)
        fr = fwd_return(close, FWD)
        fdd = fwd_drawdown(close, FWD)
        weekly = np.zeros(len(close), dtype=bool)
        weekly[::STEP] = True
        sig = (mom > 0) & weekly & fr.notna() & er.notna()
        idx = np.where(sig.to_numpy())[0]
        for i in idx:
            rows.append((name, asset_class(name), close.index[i],
                         float(er.iloc[i]), float(fr.iloc[i]), float(fdd.iloc[i])))
    return pd.DataFrame(rows, columns=["asset", "class", "date", "er", "fwd", "fdd"])


def _stats(d: pd.DataFrame) -> dict:
    if len(d) == 0:
        return {}
    return {
        "n": len(d),
        "hit": round(100 * (d["fwd"] > 0).mean(), 1),
        "avg": round(100 * d["fwd"].mean(), 2),
        "dd_med": round(100 * d["fdd"].median(), 2),
        "dd_p10": round(100 * d["fdd"].quantile(0.10), 2),
    }


def _line(label: str, s: dict) -> str:
    if not s:
        return f"  {label:<26} (no samples)"
    return (f"  {label:<26} n={s['n']:>6}  hit={s['hit']:>5}%  avg={s['avg']:>6}%"
            f"  typ.dip={s['dd_med']:>6}%  bad.dip={s['dd_p10']:>7}%")


def report(df: pd.DataFrame) -> None:
    print(f"\n{'='*78}\nTREND-STRENGTH GATE ON MOMENTUM  (fwd {FWD}d, mom>{MOM_LB}d, ER{ER_N})")
    print(f"momentum-LONG samples: {len(df):,} across {df['asset'].nunique()} instruments,"
          f" {df['date'].min().date()}–{df['date'].max().date()}\n{'='*78}")

    print("\n[1] ER quartile within momentum-long signals (monotone => ER discriminates)")
    df = df.copy()
    df["erq"] = pd.qcut(df["er"], 4, labels=["Q1 chop", "Q2", "Q3", "Q4 trend"])
    print(_line("ALL momentum-long", _stats(df)))
    for q in ["Q1 chop", "Q2", "Q3", "Q4 trend"]:
        print(_line(str(q), _stats(df[df["erq"] == q])))

    # actionable gate: keep longs only where ER is in the top half (trending)
    thr = df["er"].median()
    hi = df[df["er"] >= thr]
    lo = df[df["er"] < thr]
    print(f"\n[2] Actionable gate (median ER = {thr:.2f}): raw vs ER-gated")
    print(_line("RAW (all longs)", _stats(df)))
    print(_line("GATED (ER>=median, kept)", _stats(hi)))
    print(_line("SKIPPED (ER<median)", _stats(lo)))

    print("\n[3] Split-half robustness (gate must help in BOTH halves)")
    for half, mask in (("pre " + SPLIT, df["date"] < SPLIT),
                       ("post " + SPLIT, df["date"] >= SPLIT)):
        d = df[mask]
        if len(d) < 100:
            print(f"  {half}: thin ({len(d)})"); continue
        t = d["er"].median()
        print(f"  -- {half} --")
        print(_line("RAW", _stats(d)))
        print(_line("GATED (ER>=median)", _stats(d[d["er"] >= t])))

    print("\n[4] By asset class (where does the gate help most?)")
    for cls in ["equity", "commodity", "crypto"]:
        d = df[df["class"] == cls]
        if len(d) < 100:
            print(f"  {cls}: thin ({len(d)})"); continue
        t = d["er"].median()
        print(f"  -- {cls} --")
        print(_line("RAW", _stats(d)))
        print(_line("GATED (ER>=median)", _stats(d[d["er"] >= t])))

    # verdict
    raw, gated = _stats(df), _stats(hi)
    d_hit = gated["hit"] - raw["hit"]
    d_dd = gated["dd_p10"] - raw["dd_p10"]   # less negative = better
    print(f"\n{'='*78}\nVERDICT: gating momentum by ER moves hit {raw['hit']}%→{gated['hit']}% "
          f"({d_hit:+.1f}pp), bad-case dip {raw['dd_p10']}%→{gated['dd_p10']}% "
          f"({d_dd:+.1f}pp better).\n{'='*78}")


if __name__ == "__main__":
    panel = load_panel()
    print(f"loaded {len(panel)} instruments")
    df = collect(panel)
    report(df)
