"""DEV probe #3 — the MAKE-OR-BREAK test (research synthesis STEP 1): does SHORT-TERM
REVERSAL survive NET OF COST once we apply the literature's required refinements?
  - LIQUIDITY restriction: trade only the most-liquid names by 20d $ADV (cost lever)
  - BANDING / buy-hold spread: enter the oversold bottom decile, HOLD until it exits the
    40th pctile — the #1 turnover mitigation (Novy-Marx-Velikov)
  - HIGH-VIX conditioning: reversal is a liquidity-provision premium, strongest in stress
  - NET of realistic cost: per-side bps + a crude impact term ~ trade/ADV
Long-only loser-bounce (the capturable leg), excess over the liquid-subset benchmark.
Survivor-biased on --universe deep; run --universe smallcap_breadth for the harder test.
"""
from __future__ import annotations
import sys, glob, argparse, warnings
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from lib import config


def _ann_sharpe(r):
    r = pd.Series(r).dropna()
    return float(np.sqrt(52) * r.mean() / r.std()) if r.std() > 0 else float("nan")


def load(universe):
    if universe == "deep":
        cl, vo = {}, {}
        for f in sorted(glob.glob(str(config.data_dir() / "stocks" / "*.parquet"))):
            try:
                df = pd.read_parquet(f)
            except Exception:
                continue
            if "close" in df and "volume" in df and len(df["close"].dropna()) > 800:
                t = Path(f).stem
                cl[t], vo[t] = df["close"], df["volume"]
        px, vol = pd.DataFrame(cl).sort_index(), pd.DataFrame(vo).sort_index()
    else:
        base = config.data_dir() / universe
        px = pd.read_parquet(base / "_closes_cache.parquet").sort_index()
        vol = pd.read_parquet(base / "_volume_cache.parquet").sort_index()
    try:
        vix = pd.read_parquet(config.data_dir() / "yahoo" / "_VIX.parquet")["close"].dropna()
    except Exception:
        vix = None
    return px, vol, vix


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--universe", default="deep")
    ap.add_argument("--cost", type=float, default=10.0, help="bps per side")
    ap.add_argument("--liq", type=int, default=300, help="keep top-N by $ADV")
    a = ap.parse_args()
    cost = a.cost / 1e4
    px, vol, vix = load(a.universe)
    dollar = (px * vol)                                  # $ volume
    wk = px.resample("W-FRI").last()
    wk_ret = wk.pct_change()
    adv = dollar.rolling(20).mean().resample("W-FRI").last()   # 20d avg $ADV, weekly
    vix_w = vix.resample("W-FRI").last() if vix is not None else None
    vmed = vix_w.median() if vix_w is not None else None
    rev = -wk_ret                                        # 1-week reversal (oversold loser = high)

    print(f"panel {px.shape[1]} names x {len(wk)} wks [{a.universe}] cost={a.cost:.0f}bps liq=top{a.liq}")

    def run(banded, liq_restrict, label, hi_vix_only=False):
        held = set()
        prev_w = pd.Series(dtype=float)
        rets, turns = [], []
        for dt in wk.index:
            if dt not in rev.index or dt not in wk_ret.shift(-1).index:
                continue
            if hi_vix_only and (vix_w is None or dt not in vix_w.index
                                or pd.isna(vix_w.loc[dt]) or vix_w.loc[dt] < vmed):
                continue
            s = rev.loc[dt].dropna()
            # liquidity universe
            if liq_restrict and dt in adv.index:
                liq = adv.loc[dt].dropna().sort_values(ascending=False).head(a.liq).index
                s = s[s.index.intersection(liq)]
            if len(s) < 25:
                continue
            r = s.rank(pct=True)
            if banded:                                   # enter bottom 20%, hold until > 40%
                target = set(r[r >= 0.80].index)         # rev high = most oversold = top of rev rank
                held = {n for n in held if n in r.index and r[n] >= 0.60} | target
                names = [n for n in held if n in s.index]
            else:                                        # plain: re-form bottom quintile each week
                names = list(r[r >= 0.80].index); held = set(names)
            if not names:
                continue
            w = pd.Series(1.0 / len(names), index=names)
            nxt = wk_ret.shift(-1).loc[dt]
            bench = nxt.reindex(s.index).mean()          # liquid-subset benchmark
            gross = float((w * nxt.reindex(w.index)).sum())
            t = (w.subtract(prev_w, fill_value=0)).abs().sum()
            net = gross - t * cost - float(bench)
            rets.append(net); turns.append(t); prev_w = w
        rets = pd.Series(rets)
        print(f"  {label:46s} excess-ann {100*rets.mean()*52:+6.1f}%  Sharpe {_ann_sharpe(rets):+.2f}  "
              f"turn/wk {np.mean(turns):.2f}  n={len(rets)}")

    print("\n  long-only oversold-loser tilt, NET of cost, excess over the (liquid) benchmark:")
    run(banded=False, liq_restrict=False, label="naive weekly reversal (all names)")
    run(banded=False, liq_restrict=True,  label=f"+ liquidity (top-{a.liq} $ADV)")
    run(banded=True,  liq_restrict=True,  label="+ liquidity + BANDING (enter 20%/exit 40%)")
    run(banded=True,  liq_restrict=True,  label="+ liquidity + banding, HIGH-VIX weeks only",
        hi_vix_only=True)


if __name__ == "__main__":
    main()
