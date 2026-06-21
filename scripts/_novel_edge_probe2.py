"""DEV research probe #2: harden the novel-edge findings against the things that kill
them in practice — TRANSACTION COSTS (reversal turns over fast), LONG-ONLY feasibility
(we can't short 1600 names), and whether the INTEGRATED regime-switched + vol-managed
long-only portfolio actually beats a passive benchmark net of cost.

Survivor-biased (deep names) — directional, not gospel. Use --universe smallcap_breadth
for a less-survivor sanity check.
"""
from __future__ import annotations
import sys, glob, argparse, warnings
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from lib import config

COST = 0.0010    # 10 bps per side, round-trip 20 bps


def _ann_sharpe(r):
    r = pd.Series(r).dropna()
    return float(np.sqrt(52) * r.mean() / r.std()) if r.std() > 0 else float("nan")


def load_px(universe):
    if universe == "deep":
        d = {}
        for f in sorted(glob.glob(str(config.data_dir() / "stocks" / "*.parquet"))):
            try:
                s = pd.read_parquet(f)["close"].dropna()
            except Exception:
                continue
            if len(s) > 800:
                d[Path(f).stem] = s
        px = pd.DataFrame(d).sort_index()
    else:
        px = pd.read_parquet(config.data_dir() / universe / "_closes_cache.parquet").sort_index()
    try:
        vix = pd.read_parquet(config.data_dir() / "yahoo" / "_VIX.parquet")["close"].dropna()
    except Exception:
        vix = None
    return px, vix


def _weights_longonly(score_row, q=0.2):
    """Equal-weight the top-quintile of a (higher=better) score; 0 elsewhere."""
    s = score_row.dropna()
    if len(s) < 20:
        return None
    top = s[s.rank(pct=True) >= 1 - q]
    w = pd.Series(0.0, index=score_row.index)
    if len(top):
        w[top.index] = 1.0 / len(top)
    return w


def _backtest_longonly(wk_ret, score, vix_w=None, vol_manage=False, label=""):
    """Long-only top-quintile tilt; weekly rebal; net of cost; optional vol-managed sizing.
    Returns net return series (excess over the equal-weight benchmark)."""
    bench = wk_ret.mean(axis=1)
    prev_w, rets, turn = None, [], []
    rv = bench.rolling(8).std()
    for dt in score.index:
        if dt not in wk_ret.index:
            continue
        nxt = wk_ret.shift(-1).loc[dt] if dt in wk_ret.shift(-1).index else None
        w = _weights_longonly(score.loc[dt])
        if w is None or nxt is None:
            continue
        t = (w - prev_w).abs().sum() if prev_w is not None else 1.0
        gross = float((w * nxt.reindex(w.index)).sum())
        exposure = 1.0
        if vol_manage and pd.notna(rv.get(dt, np.nan)) and rv.loc[dt] > 0:
            exposure = float(min(3.0, rv.median() / rv.loc[dt]))
        net = exposure * gross - t * COST - float(bench.shift(-1).get(dt, 0))
        rets.append(net); turn.append(t); prev_w = w
    rets = pd.Series(rets)
    print(f"  {label:42s} excess-ann {100*rets.mean()*52:+6.1f}%  Sharpe {_ann_sharpe(rets):+.2f}  "
          f"turn/wk {np.mean(turn):.2f}")
    return rets


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--universe", default="deep")
    a = ap.parse_args()
    px, vix = load_px(a.universe)
    wk = px.resample("W-FRI").last()
    wk_ret = wk.pct_change()
    vix_w = vix.resample("W-FRI").last() if vix is not None else None
    print(f"panel: {px.shape[1]} names x {len(px)} bars ({px.index[0].date()}..{px.index[-1].date()}) "
          f"[{a.universe}]  cost={COST*1e4:.0f}bps/side")

    # signals (z-scored cross-sectionally each week)
    def zrow(df):
        return df.sub(df.mean(axis=1), axis=0).div(df.std(axis=1), axis=0)
    rev_fast = zrow(-wk_ret.rolling(1).sum())          # 1-week reversal (fast, high turnover)
    rev_slow = zrow(-wk_ret.rolling(4).sum())          # 1-month reversal (slower)
    mom = zrow(wk.pct_change(52) - wk.pct_change(4))    # 12-1 momentum

    print("\n=== A) LONG-ONLY top-quintile tilts, NET of cost (excess over equal-weight) ===")
    _backtest_longonly(wk_ret, mom, label="momentum 12-1")
    _backtest_longonly(wk_ret, rev_fast, label="reversal 1-week (fast)")
    _backtest_longonly(wk_ret, rev_slow, label="reversal 1-month (slow, less turnover)")

    print("\n=== B) BLEND + REGIME-SWITCH + VOL-MANAGED (the integrated 'magic' portfolio) ===")
    blend = (mom + rev_slow) / 2
    _backtest_longonly(wk_ret, blend, label="50/50 momentum+reversal blend")
    # regime-switch: weight reversal up when VIX is high, momentum up when low
    if vix_w is not None:
        vmed = vix_w.median()
        reg_score = mom.copy()
        for dt in mom.index:
            if dt in vix_w.index and pd.notna(vix_w.loc[dt]):
                hi = vix_w.loc[dt] >= vmed
                wr = 0.7 if hi else 0.3
                reg_score.loc[dt] = (1 - wr) * mom.loc[dt] + wr * rev_slow.loc[dt]
        _backtest_longonly(wk_ret, reg_score, label="regime-switched blend")
        _backtest_longonly(wk_ret, reg_score, vol_manage=True, label="regime-switched + VOL-MANAGED")


if __name__ == "__main__":
    main()
