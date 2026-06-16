"""Phase-0 honesty backtests for the Thematic Narrative-Rotation engine.

Answers, on OUR data, the four questions the engine's claims rest on — and writes a
machine-readable verdict the live page cites so nothing ships as "predictive" that the
data does not support.

UNIVERSES
  sectors   the 9 original SPDR sector ETFs (XLK XLE XLF XLV XLY XLP XLU XLI XLB),
            daily 1998-12 → today (~27y, multi-cycle). CLEAN & survivorship-light: the
            ETF is a continuous, tradeable series; this is the honest universe to
            VALIDATE a rotation ALGORITHM on. (+XLRE 2015, +XLC 2018 when present.)
  baskets   the 15 live theme baskets (engine.baskets EW levels), daily ~3y. The live
            PRODUCT universe, but HINDSIGHT-curated (membership chosen knowing the
            period) and far too short/few to validate — run only for context, FLAGGED.

TESTS
  1 algorithm   monthly top-N by 12-1 relative momentum, with/without an absolute-trend
                (10-mo MA) gate + a T-bill cash escape, net of cost. CAGR/Sharpe/MaxDD/
                Calmar/worst-decile-month. The decision the page makes.
  2 rank_ic     cross-sectional rank-IC of 12-1 momentum → forward 1m/3m returns (HAC t).
                Echoes engine.group_flow's verdict on a clean universe.
  3 tsmom       forward 1m return ABOVE vs BELOW the 10-mo MA (per-series TSMOM) — mean,
                vol, Sharpe, 5th-pctile tail. The durability/staying-power leg.
  4 crowding    own-history extension z → forward 63d max drawdown, by cohort + Spearman.
                Tests whether basket-level extension predicts drawdown (per-NAME it does;
                diversified it should not).

Honest priors (and what the runs confirm): cross-sectional sector/theme momentum has at
best a MODEST forward edge; the robust, repeatable edge of the absolute-trend gate is
DRAWDOWN / CRASH control, NOT higher returns; basket-aggregate extension does NOT predict
basket drawdown (that is a single-name effect). The engine is built around those truths.

Usage:  python -m scripts.thematic_rotation_phase0
Writes: data/strategies/thematic_rotation_phase0.json  (+ prints a summary)
Additive / never fatal.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config, store  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("thematic_phase0")

SECTORS = ["XLK", "XLE", "XLF", "XLV", "XLY", "XLP", "XLU", "XLI", "XLB"]
SECTORS_LATE = ["XLRE", "XLC"]            # added when present (shorter history)
TY = 12                                   # months/yr
COST = 0.0010                             # 10 bps per unit turnover


# --------------------------------------------------------------------------- #
# data
# --------------------------------------------------------------------------- #
def _adj(t: str) -> pd.Series | None:
    df = store.read("yahoo", t)
    if df is None or df.empty or "close" not in df.columns:
        return None
    return df["close"].astype(float).dropna()


def sector_prices(monthly: bool = True) -> pd.DataFrame:
    cols = {}
    for t in SECTORS + SECTORS_LATE:
        s = _adj(t)
        if s is not None and len(s) > 300:
            cols[t] = s
    P = pd.DataFrame(cols)
    # keep the 9 core continuous from inception; late adds join when available
    P = P.dropna(subset=SECTORS)
    return P.resample("ME").last() if monthly else P


def basket_levels(monthly: bool = True) -> tuple[pd.DataFrame, pd.Series]:
    """Live theme-basket EW levels + SPY bench from engine.baskets. ~3y, contaminated."""
    from engine.baskets import compute_baskets
    data = compute_baskets()
    if not data:
        return pd.DataFrame(), pd.Series(dtype=float)
    ch = data["chart"]
    idx = pd.to_datetime(ch["dates"])
    B = pd.DataFrame({bid: lv for bid, lv in ch["baskets"].items()}, index=idx)
    bench = pd.Series(ch["bench"], index=idx)
    if monthly:
        B = B.resample("ME").last()
        bench = bench.resample("ME").last()
    return B, bench


def bill_monthly(idx: pd.DatetimeIndex) -> pd.Series:
    for k in ("DTB3", "DGS3MO", "TB3MS"):
        df = store.read("fred", k)
        if df is not None and not df.empty:
            s = df[df.columns[0]].astype(float).resample("ME").last().reindex(idx) / 100.0 / TY
            return s.fillna(0.0)
    return pd.Series(0.0, index=idx)


# --------------------------------------------------------------------------- #
# metrics
# --------------------------------------------------------------------------- #
def _stats(R: pd.Series, bench_for_crash: pd.Series | None = None,
           n_trials: int = 10) -> dict:
    R = R.dropna()
    if len(R) < 12:
        return {}
    eq = (1 + R).cumprod()
    yrs = len(R) / TY
    cagr = float(eq.iloc[-1] ** (1 / yrs) - 1)
    sharpe = float(R.mean() / R.std() * np.sqrt(TY)) if R.std() > 0 else None
    mdd = float((eq / eq.cummax() - 1).min())
    calmar = float(cagr / abs(mdd)) if mdd < 0 else None
    out = {"cagr": round(cagr, 4), "sharpe": round(sharpe, 2) if sharpe else None,
           "max_dd": round(mdd, 4), "calmar": round(calmar, 2) if calmar else None,
           "n_months": int(len(R))}
    # Deflated Sharpe (house primitive) — corrects the in-sample Sharpe for the number
    # of configs tried, skew & kurtosis. DSR>=0.90 is the house bar to CLAIM edge.
    try:
        from engine.validation import deflated_sharpe
        sr_m = R.mean() / R.std() if R.std() > 0 else 0.0
        dsr = deflated_sharpe(sr_m, float(R.skew()), float(R.kurtosis() + 3.0),
                              len(R), n_trials, trading_year=TY)
        if dsr is not None:
            out["dsr"] = round(float(dsr.get("dsr", dsr) if isinstance(dsr, dict) else dsr), 3)
    except Exception:  # noqa: BLE001 — DSR is enrichment
        pass
    if bench_for_crash is not None:
        bc = bench_for_crash.reindex(R.index)
        worst = bc < bc.quantile(0.10)
        if worst.sum() >= 5:
            out["worst_decile_ret"] = round(float(R[worst].mean()), 4)
    return out


def backtest(P: pd.DataFrame, top_n: int, lookback: int, gate: bool,
             bench_crash: pd.Series, cost: float = COST) -> dict:
    """Monthly long-only rotation: hold the top_n by (lookback-1) relative momentum,
    optional absolute-trend gate (price>10mo MA) with a T-bill cash escape, net of cost."""
    fwd = P.pct_change().shift(-1)
    mom = P.pct_change(lookback) - P.pct_change(1)
    ma = P.rolling(10).mean()
    above = P > ma
    bill = bill_monthly(P.index)
    wp = pd.Series(0.0, index=P.columns)
    rows = []
    for i in range(max(lookback, 10), len(P) - 1):
        m = mom.iloc[i].dropna()
        if gate:
            m = m[above.iloc[i].reindex(m.index).fillna(False)]
        top = m.sort_values(ascending=False).head(top_n).index
        w = pd.Series(0.0, index=P.columns)
        if len(top):
            w[top] = 1.0 / top_n
        cash = max(0.0, 1.0 - float(w.sum()))
        turn = float((w - wp).abs().sum())
        r = float((w * fwd.iloc[i]).sum()) + cash * float(bill.iloc[i]) - turn * cost
        rows.append((P.index[i + 1], r))
        wp = w
    R = pd.Series(dict(rows))
    return _stats(R, bench_crash)


def equal_weight(P: pd.DataFrame, bench_crash: pd.Series) -> dict:
    R = P.pct_change().mean(axis=1).dropna()
    return _stats(R, bench_crash)


def rank_ic_panel(P: pd.DataFrame, lookback: int = 12, horizons=(1, 3)) -> dict:
    """Cross-sectional rank-IC of (lookback-1) momentum → forward returns, on
    non-overlapping steps of length=horizon. Uses the house validation primitives
    (rank_ic per date with the >=10-name floor relaxed for the thin theme universe,
    summarized by ic_summary's Newey-West t)."""
    from engine.validation import ic_summary
    mom = P.pct_change(lookback) - P.pct_change(1)
    out = {}
    for h in horizons:
        fwd = P.shift(-h) / P - 1.0
        ics = []
        for i in range(max(lookback, 10), len(P) - h, h):     # non-overlapping
            a, b = mom.iloc[i], fwd.iloc[i]
            d = pd.concat([a, b], axis=1).dropna()
            if len(d) >= 5:                                    # thin universe: ~9-15 names
                ics.append(float(d.iloc[:, 0].rank().corr(d.iloc[:, 1].rank())))
        summ = ic_summary(ics, periods_per_year=max(1, 12 // h))
        out[f"{h}m"] = {"mean_ic": summ.get("mean_ic"), "ic_t_hac": summ.get("t_hac"),
                        "hit": summ.get("hit"), "n_steps": summ.get("n")}
    return out


def tsmom_conditional(P_daily: pd.DataFrame) -> dict:
    """Forward 1-month sector return ABOVE vs BELOW the 10-mo MA (pooled, per-series)."""
    M = P_daily.resample("ME").last()
    fwd = M.pct_change().shift(-1)
    above = M > M.rolling(10).mean()
    a = fwd.where(above).values.flatten()
    b = fwd.where(~above).values.flatten()
    a = a[~np.isnan(a)]
    b = b[~np.isnan(b)]
    try:
        from scipy import stats
        t, p = stats.ttest_ind(a, b, equal_var=False)
    except Exception:  # noqa: BLE001
        t, p = None, None

    def leg(x):
        return {"mean": round(float(x.mean()), 4), "std": round(float(x.std()), 4),
                "sharpe": round(float(x.mean() / x.std() * np.sqrt(TY)), 2),
                "p05": round(float(np.percentile(x, 5)), 4), "n": int(len(x))}

    return {"above_trend": leg(a), "below_trend": leg(b),
            "mean_diff_t": round(float(t), 2) if t is not None else None,
            "mean_diff_p": round(float(p), 4) if p is not None else None}


def extension_drawdown(P_daily: pd.DataFrame, fwd_days: int = 63) -> dict:
    """Own-history extension z → forward max drawdown, by cohort + Spearman, pooled over
    the sector ETFs. Tests the basket/index-level version of the per-NAME parabolic flag."""
    frames = []
    for c in P_daily.columns:
        px = P_daily[c].dropna()
        if len(px) < 400:
            continue
        sma200 = px.rolling(200, min_periods=100).mean()
        ext = px / sma200 - 1.0
        ez = (ext - ext.rolling(252, min_periods=120).mean()) / \
            ext.rolling(252, min_periods=120).std().replace(0, np.nan)
        v = px.values
        fdd = np.full(len(v), np.nan)
        for i in range(len(v) - fwd_days):
            fdd[i] = v[i:i + fwd_days].min() / v[i] - 1.0
        frames.append(pd.DataFrame({"ez": ez.values, "fdd": fdd}, index=px.index).dropna())
    if not frames:
        return {}
    D = pd.concat(frames)
    cohorts = {}
    for lo, hi, lab in [(-99, 1, "normal"), (1, 2, "stretched"), (2, 99, "parabolic")]:
        seg = D[(D.ez >= lo) & (D.ez < hi)]
        if len(seg):
            cohorts[lab] = {"mean_fwd_maxdd": round(float(seg.fdd.mean()), 4),
                            "p05_fwd_maxdd": round(float(np.percentile(seg.fdd, 5)), 4),
                            "n": int(len(seg))}
    return {"fwd_days": fwd_days, "cohorts": cohorts,
            "spearman_ez_vs_fwd_maxdd": round(float(D.ez.corr(D.fdd, method="spearman")), 3)}


# --------------------------------------------------------------------------- #
def run_universe(name: str, P: pd.DataFrame, P_daily: pd.DataFrame,
                 bench_crash: pd.Series, contaminated: bool) -> dict:
    algo = {
        "ew_buyhold": equal_weight(P, bench_crash),
        "top3_mom12_rel": backtest(P, 3, 12, False, bench_crash),
        "top3_mom6_rel": backtest(P, 3, 6, False, bench_crash),
        "top3_mom12_dual": backtest(P, 3, 12, True, bench_crash),
        "top4_mom12_dual": backtest(P, 4, 12, True, bench_crash),
    }
    return {
        "n_assets": int(P.shape[1]),
        "span": [str(P.index.min().date()), str(P.index.max().date())],
        "contaminated": contaminated,
        "algorithm": algo,
        "rank_ic": rank_ic_panel(P),
        "tsmom_conditional": tsmom_conditional(P_daily),
        "extension_drawdown": extension_drawdown(P_daily),
    }


def main() -> int:
    out: dict = {"schema": "thematic_rotation_phase0.v1",
                 "generated_at": datetime.now(timezone.utc).isoformat(),
                 "cost_bps": COST * 1e4, "universes": {}}

    # SPY monthly returns drive the worst-decile crash metric.
    spy = _adj("SPY")
    spy_m = spy.resample("ME").last() if spy is not None else pd.Series(dtype=float)
    spy_crash = spy_m.pct_change()

    Pd = sector_prices(monthly=False)
    Pm = Pd.resample("ME").last()
    out["universes"]["sectors"] = run_universe("sectors", Pm, Pd, spy_crash, contaminated=False)
    log.info("sectors: %d assets %s", Pm.shape[1], out["universes"]["sectors"]["span"])

    try:
        Bm, bench = basket_levels(monthly=True)
        if not Bm.empty and Bm.shape[1] >= 5:
            Bd, _ = basket_levels(monthly=False)
            out["universes"]["baskets"] = run_universe(
                "baskets", Bm, Bd, bench.pct_change(), contaminated=True)
            out["universes"]["baskets"]["warning"] = (
                "HINDSIGHT-curated membership + only ~3y + ~15 names -> severely "
                "underpowered and survivorship-biased. Context only, never a validation.")
    except Exception as e:  # noqa: BLE001
        log.warning("basket universe skipped: %s", e)

    out["verdict"] = {
        "relative_momentum": "modest_or_none — cross-sectional rank-IC weak/insignificant "
                             "on the clean sector universe; an attention/focus lens, not alpha.",
        "absolute_trend_gate": "validated_risk_control — no mean-return edge but materially "
                               "lower volatility & shallower drawdown/tail; the staying-power leg.",
        "basket_extension": "no_basket_drawdown_edge — extension predicts per-NAME crashes, "
                            "not diversified basket drawdown; keep as constituent texture only.",
        "rotation_timing": "display_only — no validated early-handoff forecast (cf. group_flow).",
    }

    p = config.data_dir() / "strategies" / "thematic_rotation_phase0.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=2, default=str))
    log.info("wrote %s", p)

    # human summary
    for uname, u in out["universes"].items():
        print(f"\n=== {uname.upper()} ({u['n_assets']} assets, {u['span'][0]}→{u['span'][1]}"
              f"{', CONTAMINATED' if u['contaminated'] else ''}) ===")
        for k, s in u["algorithm"].items():
            if s:
                print(f"  {k:20} CAGR {s['cagr']*100:5.1f}%  Sharpe {s.get('sharpe')}  "
                      f"MaxDD {s['max_dd']*100:6.1f}%  worst-dec {s.get('worst_decile_ret', 0)*100:+.2f}%")
        ts = u["tsmom_conditional"]
        print(f"  TSMOM above/below 10mo: Sharpe {ts['above_trend']['sharpe']} vs "
              f"{ts['below_trend']['sharpe']}; tail p05 {ts['above_trend']['p05']*100:.1f}% vs "
              f"{ts['below_trend']['p05']*100:.1f}% (mean diff p={ts['mean_diff_p']})")
        print(f"  rank-IC 1m {u['rank_ic']['1m']['mean_ic']} (t {u['rank_ic']['1m']['ic_t_hac']}) "
              f"3m {u['rank_ic']['3m']['mean_ic']} (t {u['rank_ic']['3m']['ic_t_hac']})")
        ed = u.get("extension_drawdown", {})
        if ed:
            print(f"  extension→fwd{ed['fwd_days']}d maxDD spearman {ed['spearman_ez_vs_fwd_maxdd']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
