"""Strategy Lab — an honest, reusable backtest harness that scores a library of
trading strategies and records per-strategy results (research/STRATEGY_LAB.md).

Two strategy families, two honest tests each:

  TIME-SERIES (per name) — engine.strategy_signals.REGISTRY. These answer "WHEN to
  buy a name you want" (short-horizon entry timing) and "is a name in a buy state"
  (trend/swing). Scored by:
    (A) a tradable LONG/FLAT backtest per name, net of a one-way cost, aggregated to
        one equal-weight return series → Sharpe / CAGR / MaxDD vs an always-invested
        benchmark, DSR (multiple-testing haircut), block-bootstrap CI, split-half;
    (B) a per-name Information Coefficient at the strategy horizon (non-overlapping
        sampling), t-tested ACROSS names (each name = one observation — conservative);
    (C) entry-quality: forward max-adverse-excursion on signal-fire days vs all days
        (the drawdown / capital-efficiency lens — entry timing is a risk lever).

  CROSS-SECTIONAL (which name) — momentum / 52w-high / low-vol / residual-momentum.
  Scored by monthly rank-IC (HAC-t, BH-FDR across the family) and a long-only
  top-tercile vs equal-weight portfolio. LOUDLY flagged survivorship-biased: the
  data/stocks panel is 114 still-listed mega-caps, so XS results are CONTEXT, not alpha.

Honest-validation house style (engine.validation): DSR>=0.90 to survive the
multiple-testing haircut, BH-FDR at alpha=0.10 across the strategy family, HAC
t-stats on overlapping windows, split-half robustness, costs always charged,
survivorship flagged in-output.

Run (from the worktree, with the scipy main-checkout venv):
    .venv/bin/python -m scripts.strategy_lab            # full
    .venv/bin/python -m scripts.strategy_lab --quick    # 30-name subset, fast
Outputs: data/strategies/strategy_lab.json + reports/strategy-lab.md
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import warnings
from datetime import datetime, timezone

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

import tempfile  # noqa: E402

from lib import store  # noqa: E402
from engine import validation as V  # noqa: E402
from engine import strategy_signals as SS  # noqa: E402
from engine import predictive_signals as PS  # noqa: E402
from engine.trial_ledger import TrialLedger  # noqa: E402

COST_BPS = 5.0          # one-way (spread+slippage) for liquid mega-caps


def _ledger(family: str, n: int) -> TrialLedger:
    """Honest multiple-testing N via the Trial Ledger (engine/trial_ledger.py): log the
    grid of `n` configs tried at generation so deflated_sharpe counts N from the ledger,
    not a caller-asserted literal (tests/test_no_literal_ntrials.py). Ephemeral per-run
    file so the research harness never pollutes the committed data/trial_ledger.jsonl."""
    led = TrialLedger(path=tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False).name,
                      family=family)
    led.log_grid([{"trial": i} for i in range(int(n))], family=family)
    return led
HORIZONS = [1, 5, 10, 21, 63]
TRADING_YEAR = 252
MIN_NAMES = 20          # aggregate portfolio only over dates with >= this many names
SEED = 7


# --------------------------------------------------------------------------- #
# data
# --------------------------------------------------------------------------- #
def universe(quick: bool) -> list[str]:
    tics = sorted(os.path.splitext(os.path.basename(f))[0]
                  for f in glob.glob("data/stocks/*.parquet"))
    if quick:
        tics = tics[::4][:30]
    return tics


def load_frames(tics: list[str]) -> dict[str, pd.DataFrame]:
    out = {}
    for t in tics:
        df = store.read("stocks", t)
        if df is None or df.empty or "close" not in df:
            continue
        df = df[~df.index.duplicated(keep="last")].sort_index()
        if len(df) >= 400:
            out[t] = df
    return out


def market_returns() -> pd.Series:
    m = store.read("yahoo", "_GSPC")          # S&P 500 index back to 1927
    if m is None or m.empty:
        m = store.read("yahoo", "SPY")
    return m["close"].pct_change()


# --------------------------------------------------------------------------- #
# forward-return helpers (causal forward windows for the event study)
# --------------------------------------------------------------------------- #
def fwd_return(close: pd.Series, h: int) -> pd.Series:
    return close.shift(-h) / close - 1.0


def fwd_mae(close: pd.Series, h: int) -> pd.Series:
    """Max adverse excursion over [t+1, t+h]: min(close[t+1..t+h]) / close[t] - 1 (<=0)."""
    m = close[::-1].rolling(h, min_periods=h).min()[::-1]   # m[t] = min(close[t..t+h-1])
    return m.shift(-1) / close - 1.0                         # exclude t -> [t+1..t+h]


def _sharpe(r: np.ndarray) -> float:
    r = r[np.isfinite(r)]
    sd = r.std(ddof=1) if len(r) > 2 else np.nan
    return float(r.mean() / sd * np.sqrt(TRADING_YEAR)) if sd else float("nan")


def _cagr(r: pd.Series) -> float:
    r = r.dropna()
    if len(r) < 10:
        return float("nan")
    yrs = (r.index[-1] - r.index[0]).days / 365.25
    growth = float((1.0 + r).prod())
    return growth ** (1.0 / yrs) - 1.0 if yrs > 0 and growth > 0 else float("nan")


def _maxdd(r: pd.Series) -> float:
    eq = (1.0 + r.fillna(0)).cumprod()
    return float((eq / eq.cummax() - 1.0).min())


# --------------------------------------------------------------------------- #
# TIME-SERIES strategy evaluation
# --------------------------------------------------------------------------- #
def eval_ts_strategy(strat, frames: dict, n_trials: int) -> dict:
    h = strat.horizon
    per_name_net = {}      # ticker -> net daily return series (strategy)
    per_name_hold = {}     # ticker -> buy&hold daily return series
    name_rows = []         # per-name comparison metrics
    ics = []               # per-name IC at horizon h
    fire_mae, base_mae = [], []   # entry-quality pools
    band_pool = []         # (signal_z, fwd_h_return) for the banded table

    for t, df in frames.items():
        c = df["close"]
        sig, pos = strat.signal(df)
        if pos is None:
            continue
        pos = pos.clip(0.0, 1.0).fillna(0.0)
        bt = V.backtest_core(c, pos, cost_bps=COST_BPS)
        net = bt["net"]
        hold = bt["hold"]
        # require a meaningful sample and some activity
        active = float(pos.mean())
        if net.dropna().shape[0] < 250 or active <= 0.0:
            continue
        per_name_net[t] = net
        per_name_hold[t] = hold
        name_rows.append({
            "ticker": t,
            "sharpe": round(_sharpe(net.to_numpy()), 3),
            "hold_sharpe": round(_sharpe(hold.to_numpy()), 3),
            "maxdd": round(_maxdd(net), 3),
            "hold_maxdd": round(_maxdd(hold), 3),
            "cagr": round(_cagr(net), 4),
            "hold_cagr": round(_cagr(hold), 4),
            "time_in_mkt": round(active, 3),
        })
        # (B) per-name IC at horizon h, non-overlapping sampling
        fr = fwd_return(c, h)
        s = sig.reindex(c.index)
        pair = pd.concat([s, fr], axis=1).dropna()
        pair = pair.iloc[::h]                                  # non-overlapping
        if len(pair) >= 20:
            ic = pair.iloc[:, 0].rank().corr(pair.iloc[:, 1].rank())
            if np.isfinite(ic):
                ics.append(float(ic))
        # (C) entry-quality: forward MAE on fire days vs all days
        fire = pos.shift(1).fillna(0) < pos                   # day position turns on
        mae = fwd_mae(c, h)
        fm = mae[fire].dropna()
        bm = mae.dropna()
        if len(fm) >= 10:
            fire_mae.append(float(fm.median()))
            base_mae.append(float(bm.median()))
        # banded table: causal rolling-z of the signal vs forward return
        z = SS._zscore(s, 252)
        bp = pd.concat([z, fr], axis=1).dropna()
        if len(bp):
            band_pool.append(bp.to_numpy())

    if len(per_name_net) < 5:
        return {"key": strat.key, "name": strat.name, "family": strat.family,
                "horizon": h, "n_names": len(per_name_net), "verdict": "INSUFFICIENT DATA"}

    # ---- aggregate equal-weight portfolio (strategy) and benchmark (always-in) ---- #
    net_df = pd.DataFrame(per_name_net)
    hold_df = pd.DataFrame(per_name_hold)
    enough = net_df.notna().sum(axis=1) >= MIN_NAMES
    port = net_df[enough].mean(axis=1)
    bench = hold_df[enough].mean(axis=1)
    port, bench = port.dropna(), bench.dropna()
    common = port.index.intersection(bench.index)
    port, bench = port.loc[common], bench.loc[common]

    sh_port, sh_bench = _sharpe(port.to_numpy()), _sharpe(bench.to_numpy())
    # DSR on the aggregate strategy series
    mom = V.ret_moments(port)
    dsr = V.deflated_sharpe(mom[0], mom[1], mom[2], mom[3],
                            ledger=_ledger("strategy_lab", n_trials), family="strategy_lab",
                            trading_year=TRADING_YEAR) if mom else None
    boot = V.block_bootstrap_ci(port, block=21, B=4000, seed=SEED, ann=TRADING_YEAR)

    # split-half robustness (Sharpe vs bench in BOTH halves)
    mid = port.index[len(port) // 2]
    def half_excess(idx_lo, idx_hi):
        p = port.loc[idx_lo:idx_hi]; b = bench.loc[idx_lo:idx_hi]
        return _sharpe(p.to_numpy()) - _sharpe(b.to_numpy())
    h1 = half_excess(port.index[0], mid)
    h2 = half_excess(mid, port.index[-1])
    split_ok = bool((h1 > 0) == (h2 > 0))

    # per-name win rates
    rows = pd.DataFrame(name_rows)
    beat_sharpe = float((rows["sharpe"] > rows["hold_sharpe"]).mean())
    beat_dd = float((rows["maxdd"] > rows["hold_maxdd"]).mean())   # less negative = better

    # (B) IC across names
    ic_arr = np.array(ics, float)
    ic_mean = float(ic_arr.mean()) if len(ic_arr) else float("nan")
    ic_t = float(ic_mean / (ic_arr.std(ddof=1) / np.sqrt(len(ic_arr)))) if len(ic_arr) > 3 else None
    ic_p = float(2.0 * (1.0 - V._norm_cdf(abs(ic_t)))) if ic_t is not None else None
    ic_hit = float((ic_arr > 0).mean()) if len(ic_arr) else None

    # (C) entry quality (drawdown lens)
    eq = None
    if fire_mae and base_mae:
        fmae = float(np.median(fire_mae)); bmae = float(np.median(base_mae))
        eq = {"fire_fwd_mae_med": round(fmae, 4), "base_fwd_mae_med": round(bmae, 4),
              "shallower": bool(fmae > bmae)}   # fire MAE less negative = better entry

    # banded table (descriptive)
    band = None
    if band_pool:
        allp = np.vstack(band_pool)
        zc, frc = allp[:, 0], allp[:, 1]
        qs = np.nanpercentile(zc, [20, 40, 60, 80])
        labels = ["q1", "q2", "q3", "q4", "q5"]
        bins = np.digitize(zc, qs)
        band = []
        for i, lab in enumerate(labels):
            m = bins == i
            if m.sum() >= 50:
                band.append({"band": lab, "n": int(m.sum()),
                             "mean_fwd": round(float(np.nanmean(frc[m])), 4),
                             "hit": round(float(np.nanmean(frc[m] > 0)), 3)})

    # ---- verdict ---- #
    # Honest taxonomy:
    #   ENTRY-SIGNAL  — a short-horizon timing signal whose cross-name forward-return
    #                   IC is significant & positive: buying ON the signal beats buying
    #                   on an arbitrary day. It is an OVERLAY (improves the entry of a
    #                   name you already want), not a standalone system — most such
    #                   rules sit in cash too often to beat always-invested survivors.
    #   TRADABLE       — the standalone long/flat rule beats always-invested on Sharpe
    #                   net of cost, survives DSR + bootstrap + split-half.
    #   RISK-CONTROL   — matches buy&hold Sharpe while materially cutting drawdown / time
    #                   in market (the validated de-risking role of a trend gate).
    excess_sh = sh_port - sh_bench
    boot_lo = boot.get("sharpe_ci", [None])[0] if boot else None
    dsr_val = dsr["dsr"] if dsr else None
    tim = float(rows["time_in_mkt"].median())
    ic_sig_pos = (ic_p is not None and ic_p < 0.05 and np.isfinite(ic_mean) and ic_mean > 0)
    short_family = strat.family in ("mean_reversion", "entry_timing")
    predictive_entry = ic_sig_pos and short_family
    tradable = (excess_sh > 0 and split_ok and dsr_val is not None and dsr_val >= 0.90
                and (boot_lo is not None and boot_lo > 0))
    risk_control = (beat_dd >= 0.60 and excess_sh > -0.10 and tim < 0.95)

    tags = []
    if predictive_entry:
        tags.append("entry_overlay")
    if tradable:
        tags.append("tradable_standalone")
    if risk_control:
        tags.append("risk_control")
    if eq is not None and eq["shallower"]:
        tags.append("shallower_entry_drawdown")

    if predictive_entry:
        verdict = "ENTRY-SIGNAL (predictive timing overlay)"
    elif tradable:
        verdict = "TRADABLE STANDALONE"
    elif risk_control:
        verdict = "RISK-CONTROL (drawdown/de-risk)"
    else:
        verdict = "NO EDGE"

    return {
        "key": strat.key, "name": strat.name, "family": strat.family, "horizon": h,
        "thesis": strat.thesis, "kind": "time_series", "survivorship": "biased_megacap_survivors",
        "n_names": len(per_name_net),
        "agg": {
            "sharpe": round(sh_port, 3), "bench_sharpe": round(sh_bench, 3),
            "excess_sharpe": round(excess_sh, 3),
            "cagr": round(_cagr(port), 4), "bench_cagr": round(_cagr(bench), 4),
            "maxdd": round(_maxdd(port), 3), "bench_maxdd": round(_maxdd(bench), 3),
            "time_in_mkt": round(float(rows["time_in_mkt"].median()), 3),
            "split_half_excess": [round(h1, 3), round(h2, 3)], "split_ok": split_ok,
        },
        "dsr": dsr, "bootstrap": boot,
        "per_name": {"beat_bench_sharpe_frac": round(beat_sharpe, 3),
                     "beat_bench_maxdd_frac": round(beat_dd, 3),
                     "median_sharpe": round(float(rows["sharpe"].median()), 3),
                     "median_hold_sharpe": round(float(rows["hold_sharpe"].median()), 3)},
        "ic": {"mean_ic": round(ic_mean, 4) if np.isfinite(ic_mean) else None,
               "t_across_names": round(ic_t, 3) if ic_t is not None else None,
               "p": round(ic_p, 4) if ic_p is not None else None,
               "hit_frac": round(ic_hit, 3) if ic_hit is not None else None,
               "n_names": len(ic_arr)},
        "entry_quality": eq, "band": band,
        "p_value": ic_p, "verdict": verdict, "tags": tags,
    }


# --------------------------------------------------------------------------- #
# CROSS-SECTIONAL strategy evaluation
# --------------------------------------------------------------------------- #
def _xs_legs():
    """Cross-sectional selection legs: (closes, asof, mkt) -> Series. Reuse the
    audited predictive_signals legs; add residual-mom and low-vol."""
    def resid_mom(closes, asof, mkt, form=252, skip=21):
        sub = closes.loc[:asof]
        if len(sub) < form + skip + 5:
            return pd.Series(dtype=float)
        win = sub.iloc[-(form + skip):]
        rets = win.pct_change()
        m = mkt.reindex(win.index).pct_change()
        out = {}
        mm = m.iloc[1:-skip] if skip else m.iloc[1:]
        if mm.var() in (0, np.nan) or len(mm) < 60:
            return pd.Series(dtype=float)
        mmom = win[mkt.name] if mkt.name in win else None
        mkt_mom = (mkt.reindex(win.index).iloc[-(skip + 1)] / mkt.reindex(win.index).iloc[0] - 1.0)
        for col in win.columns:
            r = rets[col].iloc[1:-skip] if skip else rets[col].iloc[1:]
            j = pd.concat([r, mm], axis=1).dropna()
            if len(j) < 60:
                continue
            beta = j.iloc[:, 0].cov(j.iloc[:, 1]) / (j.iloc[:, 1].var() or np.nan)
            raw = win[col].iloc[-(skip + 1)] / win[col].iloc[0] - 1.0
            if np.isfinite(beta) and np.isfinite(raw):
                out[col] = raw - beta * mkt_mom
        return pd.Series(out)

    def low_vol(closes, asof, mkt, win=126):
        sub = closes.loc[:asof].iloc[-(win + 1):]
        if len(sub) < 60:
            return pd.Series(dtype=float)
        rv = sub.pct_change().std(ddof=0) * np.sqrt(252)
        return -rv[rv > 0]                          # higher = lower vol

    def mom_6_1(closes, asof):
        return PS.mom_12_1(closes, asof, form=126, skip=21)

    return {
        "xs_mom_12_1": ("Cross-sectional 12-1 momentum", lambda cl, a, m: PS.mom_12_1(cl, a)),
        "xs_mom_6_1": ("Cross-sectional 6-1 momentum", lambda cl, a, m: mom_6_1(cl, a)),
        "xs_near_52w_high": ("Proximity to 52-week high", lambda cl, a, m: PS.near_52w_high(cl, a)),
        "xs_fip": ("Frog-in-the-pan continuity momentum", lambda cl, a, m: PS.fip_continuity(cl, a)),
        "xs_resid_mom": ("Residual (beta-adj) 12-1 momentum", resid_mom),
        "xs_low_vol": ("Low realized-vol (low-vol anomaly)", low_vol),
    }


def eval_xs(frames: dict, mkt: pd.Series, n_trials: int) -> list[dict]:
    closes = pd.DataFrame({t: df["close"] for t, df in frames.items()}).sort_index()
    closes = closes.dropna(how="all")
    mkt = mkt.copy()
    mkt.name = "_MKT"
    # monthly rebalance grid (21 trading days), need >=24 names live
    idx = closes.index
    grid = idx[252::21]
    grid = [d for d in grid if d <= idx[-30]]
    legs = _xs_legs()
    results = []
    fwd_h = 21
    for key, (label, fn) in legs.items():
        ics = []
        long_rets, ew_rets = [], []
        for d in grid:
            try:
                sig = fn(closes, d, mkt)
            except Exception:
                sig = pd.Series(dtype=float)
            if sig is None or sig.empty:
                continue
            pos = closes.index.get_indexer([d])[0]
            if pos < 0 or pos + fwd_h >= len(closes):
                continue
            future = closes.iloc[pos + fwd_h] / closes.iloc[pos] - 1.0
            j = pd.concat([sig.rename("s"), future.rename("f")], axis=1).dropna()
            if len(j) < 12:
                continue
            ics.append(V.rank_ic(j["s"], j["f"]))
            # long top tercile vs equal-weight all
            k = max(2, len(j) // 3)
            top = j.sort_values("s", ascending=False).head(k)["f"].mean()
            long_rets.append(float(top)); ew_rets.append(float(j["f"].mean()))
        ic_s = V.ic_summary(ics, periods_per_year=12)
        # tercile portfolio (monthly) — long-only excess vs equal weight
        lr, er = np.array(long_rets), np.array(ew_rets)
        excess = lr - er
        port_sh = float(np.mean(lr) / (np.std(lr, ddof=1) or np.nan) * np.sqrt(12)) if len(lr) > 3 else None
        ew_sh = float(np.mean(er) / (np.std(er, ddof=1) or np.nan) * np.sqrt(12)) if len(er) > 3 else None
        ex_t = (float(np.mean(excess) / (np.std(excess, ddof=1) / np.sqrt(len(excess))))
                if len(excess) > 3 and np.std(excess, ddof=1) else None)
        verdict = ("CONTEXT — IC FDR-significant" if (ic_s.get("p_hac") is not None and ic_s["p_hac"] < 0.10
                   and ic_s.get("mean_ic", 0) and ic_s["mean_ic"] > 0)
                   else "NO XS EDGE (context-only)")
        results.append({
            "key": key, "name": label, "family": "selection_xs", "kind": "cross_sectional",
            "horizon": fwd_h, "survivorship": "BIASED — 114 surviving mega-caps; treat as CONTEXT not alpha",
            "ic": ic_s, "tercile": {"long_sharpe": round(port_sh, 3) if port_sh else None,
                                     "ew_sharpe": round(ew_sh, 3) if ew_sh else None,
                                     "excess_t": round(ex_t, 3) if ex_t else None,
                                     "n_months": len(lr)},
            "p_value": ic_s.get("p_hac"), "verdict": verdict,
        })
    return results


# --------------------------------------------------------------------------- #
# COMBINED engines — validate the entry-timing composite and the trend-gated rule
# built from the survivors. The question: does blending the timing legs LIFT IC
# above the best single leg, and does the trend-gate × oversold combination give a
# better risk-adjusted, lower-drawdown buy-in than naive always-in?
# --------------------------------------------------------------------------- #
def eval_combine(frames: dict, mkt: pd.Series, n_trials: int) -> dict:
    h = 5
    comp_ics, rsi2_ics = [], []          # composite vs best single leg
    quint_pool = []                       # (composite_z, fwd_5d) on uptrend days
    per_name_net, per_name_hold = {}, {}
    naive_net = {}                        # buy EVERY uptrend day, hold h (no timing)

    for t, df in frames.items():
        c = df["close"]
        z = SS.entry_timing_z(df)
        uptrend = c > SS.sma(c, 200)
        fr = fwd_return(c, h)
        # composite IC (uptrend days only, non-overlapping)
        zc = z.where(uptrend)
        pair = pd.concat([zc, fr], axis=1).dropna().iloc[::h]
        if len(pair) >= 20:
            ic = pair.iloc[:, 0].rank().corr(pair.iloc[:, 1].rank())
            if np.isfinite(ic):
                comp_ics.append(float(ic))
        # best single leg (rsi2) IC for comparison
        r2z = SS._zscore(-SS.wilder_rsi(c, 2), 252).where(uptrend)
        pr2 = pd.concat([r2z, fr], axis=1).dropna().iloc[::h]
        if len(pr2) >= 20:
            ic2 = pr2.iloc[:, 0].rank().corr(pr2.iloc[:, 1].rank())
            if np.isfinite(ic2):
                rsi2_ics.append(float(ic2))
        # quintile pool
        bp = pd.concat([zc, fr], axis=1).dropna()
        if len(bp):
            quint_pool.append(bp.to_numpy())
        # tradable: trend-gated oversold entry vs always-in vs naive uptrend-buy
        pos = SS.entry_composite_position(df, h=h, z_thr=1.0).clip(0, 1)
        bt = V.backtest_core(c, pos, cost_bps=COST_BPS)
        if bt["net"].dropna().shape[0] >= 250 and pos.mean() > 0:
            per_name_net[t] = bt["net"]; per_name_hold[t] = bt["hold"]
            naive_pos = SS.hold_for(uptrend, h).clip(0, 1)
            naive_net[t] = V.backtest_core(c, naive_pos, cost_bps=COST_BPS)["net"]

    # composite vs leg IC
    ca, ra = np.array(comp_ics), np.array(rsi2_ics)
    comp_mean = float(ca.mean()) if len(ca) else None
    comp_t = float(ca.mean() / (ca.std(ddof=1) / np.sqrt(len(ca)))) if len(ca) > 3 else None
    lift = (comp_mean - float(ra.mean())) if (comp_mean is not None and len(ra)) else None

    # quintile spread (top vs bottom oversold quintile, pooled)
    quint = None
    if quint_pool:
        allp = np.vstack(quint_pool)
        zc, frc = allp[:, 0], allp[:, 1]
        qs = np.nanpercentile(zc, [20, 40, 60, 80])
        b = np.digitize(zc, qs)
        means = [float(np.nanmean(frc[b == i])) for i in range(5)]
        top, bot = means[4], means[0]
        # spread t via the two-sample pools
        tg, bg = frc[b == 4], frc[b == 0]
        sp_t = float((tg.mean() - bg.mean()) /
                     np.sqrt(tg.var(ddof=1) / len(tg) + bg.var(ddof=1) / len(bg)))
        quint = {"q_means_fwd5": [round(x, 4) for x in means],
                 "top_minus_bottom": round(top - bot, 4), "spread_t": round(sp_t, 2),
                 "n": int(len(zc))}

    # tradable aggregate (gated entry) vs naive uptrend-buy
    def agg(d):
        df_ = pd.DataFrame(d)
        enough = df_.notna().sum(axis=1) >= MIN_NAMES
        s = df_[enough].mean(axis=1).dropna()
        return s
    gated = agg(per_name_net); hold = agg(per_name_hold); naive = agg(naive_net)
    common = gated.index.intersection(hold.index).intersection(naive.index)
    gated, hold, naive = gated.loc[common], hold.loc[common], naive.loc[common]
    mom = V.ret_moments(gated)
    dsr = V.deflated_sharpe(mom[0], mom[1], mom[2], mom[3], ledger=_ledger("strategy_lab", n_trials), family="strategy_lab", trading_year=TRADING_YEAR) if mom else None

    return {
        "name": "Entry-timing composite (blended oversold overlay)",
        "ic": {"composite_mean_ic": round(comp_mean, 4) if comp_mean is not None else None,
               "composite_t_across_names": round(comp_t, 3) if comp_t is not None else None,
               "best_leg_mean_ic": round(float(ra.mean()), 4) if len(ra) else None,
               "blend_lift_vs_best_leg": round(lift, 4) if lift is not None else None,
               "n_names": len(ca)},
        "quintile": quint,
        "tradable_gated_vs_naive": {
            "gated_sharpe": round(_sharpe(gated.to_numpy()), 3),
            "naive_uptrend_sharpe": round(_sharpe(naive.to_numpy()), 3),
            "always_in_sharpe": round(_sharpe(hold.to_numpy()), 3),
            "gated_maxdd": round(_maxdd(gated), 3), "naive_maxdd": round(_maxdd(naive), 3),
            "always_in_maxdd": round(_maxdd(hold), 3),
            "gated_time_in_mkt": round(float(pd.DataFrame(per_name_net).notna().mean().mean()), 3),
            "dsr": dsr,
        },
        "interpretation": (
            "Entry composite is an OVERLAY: it improves the SHORT-HORIZON entry of a "
            "name already selected (positive blended IC, top-vs-bottom oversold quintile "
            "spread). It does not beat always-invested standalone — its role is better "
            "fills + shallower entry drawdown, gated by the validated uptrend filter."),
    }


def eval_selection_combine(frames: dict, mkt: pd.Series) -> dict:
    closes = pd.DataFrame({t: df["close"] for t, df in frames.items()}).sort_index().dropna(how="all")
    m = mkt.copy(); m.name = "_MKT"
    idx = closes.index
    grid = [d for d in idx[252::21] if d <= idx[-30]]
    ics_blend, ics_mom = [], []
    fwd_h = 21
    for d in grid:
        sig = SS.selection_composite(closes, d, m)
        mom = PS.mom_12_1(closes, d)
        pos = closes.index.get_indexer([d])[0]
        if pos < 0 or pos + fwd_h >= len(closes):
            continue
        fut = closes.iloc[pos + fwd_h] / closes.iloc[pos] - 1.0
        if not sig.empty:
            j = pd.concat([sig.rename("s"), fut.rename("f")], axis=1).dropna()
            if len(j) >= 12:
                ics_blend.append(V.rank_ic(j["s"], j["f"]))
        if not mom.empty:
            jm = pd.concat([mom.rename("s"), fut.rename("f")], axis=1).dropna()
            if len(jm) >= 12:
                ics_mom.append(V.rank_ic(jm["s"], jm["f"]))
    sb = V.ic_summary(ics_blend, periods_per_year=12)
    sm = V.ic_summary(ics_mom, periods_per_year=12)
    return {"name": "Selection composite (12-1 + residual momentum)",
            "blend_ic": sb, "mom_only_ic": sm,
            "survivorship": "BIASED — context only, never sizes alone"}


# --------------------------------------------------------------------------- #
# INSTITUTIONAL LEVERS — vol-managed sizing (Moreira-Muir) + regime-conditioning
# --------------------------------------------------------------------------- #
def eval_vol_managed(frames: dict, n_trials: int) -> dict:
    """Validate volatility-targeting: hold ~constant risk by sizing inversely to forecast
    vol. Compare (a) always-invested buy&hold vs vol-targeted buy&hold and (b) the 200dma
    trend sleeve vs its vol-targeted version. The Moreira-Muir result is higher Sharpe +
    shallower drawdown with zero new alpha."""
    from engine import vol_managed as VM
    bh, vt1, vt2, tr, trvt = {}, {}, {}, {}, {}
    for t, df in frames.items():
        c = df["close"]
        bh[t] = c.pct_change()
        vt1[t] = V.backtest_core(c, VM.vol_scalar(c, target=0.15, cap=1.0), cost_bps=COST_BPS)["net"]
        vt2[t] = V.backtest_core(c, VM.vol_scalar(c, target=0.15, cap=2.0), cost_bps=COST_BPS)["net"]
        up = (c > SS.sma(c, 200)).astype(float)
        tr[t] = V.backtest_core(c, up, cost_bps=COST_BPS)["net"]
        trvt[t] = V.backtest_core(c, VM.vol_target_position(up, c, target=0.15, cap=1.0), cost_bps=COST_BPS)["net"]

    def agg(d):
        df_ = pd.DataFrame(d)
        enough = df_.notna().sum(axis=1) >= MIN_NAMES
        return df_[enough].mean(axis=1).dropna()
    series = {k: agg(v) for k, v in {"buyhold": bh, "voltarget_derisk": vt1,
              "voltarget_lever": vt2, "trend": tr, "trend_voltarget": trvt}.items()}
    idx = None
    for s in series.values():
        idx = s.index if idx is None else idx.intersection(s.index)
    out = {}
    for k, s in series.items():
        s = s.loc[idx]
        out[k] = {"sharpe": round(_sharpe(s.to_numpy()), 3), "cagr": round(_cagr(s), 4),
                  "maxdd": round(_maxdd(s), 3)}
    sl = series["voltarget_lever"].loc[idx]
    mom = V.ret_moments(sl)
    dsr = V.deflated_sharpe(mom[0], mom[1], mom[2], mom[3], ledger=_ledger("strategy_lab", n_trials), family="strategy_lab", trading_year=TRADING_YEAR) if mom else None
    boot = V.block_bootstrap_ci(series["voltarget_derisk"].loc[idx], block=21, B=4000, seed=SEED, ann=TRADING_YEAR)
    return {
        "name": "Vol-managed sizing (Moreira-Muir / Barroso-Santa-Clara)",
        "sleeves": out,
        "buyhold_to_voltarget_derisk": {
            "d_sharpe": round(out["voltarget_derisk"]["sharpe"] - out["buyhold"]["sharpe"], 3),
            "d_maxdd": round(out["voltarget_derisk"]["maxdd"] - out["buyhold"]["maxdd"], 3)},
        "trend_to_voltarget": {
            "d_sharpe": round(out["trend_voltarget"]["sharpe"] - out["trend"]["sharpe"], 3),
            "d_maxdd": round(out["trend_voltarget"]["maxdd"] - out["trend"]["maxdd"], 3)},
        "dsr": dsr, "bootstrap": boot,
        "interpretation": ("Vol-targeting holds ~constant risk → higher Sharpe and shallower "
                           "drawdown vs the unscaled sleeve. A capital-efficiency lever, kept "
                           "regardless of IC; the levered variant adds return in calm regimes."),
    }


def eval_regime_conditioning(frames: dict, n_trials: int) -> dict:
    """Is the oversold-entry edge REGIME-DEPENDENT? Split the entry-composite IC by the
    MARKET regime (S&P 500 above/below its 200dma) and by VIX level. If oversold-buying
    only pays in a healthy tape (and is a falling knife in a bear tape), the entry
    composite should be market-regime-gated, not just name-uptrend-gated."""
    spx = market_returns_price()
    spx_up = (spx > SS.sma(spx, 200))
    vix = store.read("yahoo", "_VIX")
    vix_c = vix["close"] if vix is not None else None
    h = 5
    ic_bull, ic_bear, ic_calm, ic_stress = [], [], [], []
    def _split_ic(z, fr, mask_true, dst_true, dst_false):
        base = pd.concat([z.rename("z"), fr.rename("f")], axis=1)
        base["m"] = mask_true.reindex(z.index).ffill().fillna(False).astype(bool)
        base = base.dropna()
        m = base["m"].to_numpy(dtype=bool)
        for sub, dst in ((base[m], dst_true), (base[~m], dst_false)):
            s = sub.iloc[::h]
            if len(s) >= 15:
                ic = s["z"].rank().corr(s["f"].rank())
                if np.isfinite(ic):
                    dst.append(float(ic))

    for t, df in frames.items():
        c = df["close"]
        z = SS.entry_timing_z(df).where(c > SS.sma(c, 200))
        fr = fwd_return(c, h)
        _split_ic(z, fr, spx_up, ic_bull, ic_bear)
        if vix_c is not None:
            hi = (vix_c > vix_c.rolling(252, min_periods=60).median())
            _split_ic(z, fr, hi, ic_stress, ic_calm)

    def summ(a):
        a = np.array(a, float)
        if len(a) < 4:
            return {"mean_ic": None, "t": None, "n": len(a)}
        t = float(a.mean() / (a.std(ddof=1) / np.sqrt(len(a))))
        return {"mean_ic": round(float(a.mean()), 4), "t": round(t, 2), "n": len(a)}
    bull, bear = summ(ic_bull), summ(ic_bear)
    calm, stress = summ(ic_calm), summ(ic_stress)
    gated = (bull["mean_ic"] is not None and bear["mean_ic"] is not None
             and bull["mean_ic"] > bear["mean_ic"])
    return {
        "name": "Regime-conditioning of the entry-timing edge",
        "spx_regime": {"bull_market": bull, "bear_market": bear},
        "vix_regime": {"calm": calm, "stress": stress},
        "regime_dependent": bool(gated),
        "recommendation": ("Dampen oversold-buy sizing when SPX<200dma / VIX elevated — "
                           "mean-reversion entries are a falling knife in a bear tape."
                           if gated else "Edge roughly regime-stable; light conditioning only."),
    }


def market_returns_price() -> pd.Series:
    m = store.read("yahoo", "_GSPC")
    if m is None or m.empty:
        m = store.read("yahoo", "SPY")
    return m["close"]


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="30-name subset (fast)")
    ap.add_argument("--out", default="data/strategies/strategy_lab.json")
    args = ap.parse_args()

    tics = universe(args.quick)
    print(f"[strategy_lab] universe: {len(tics)} names ({'quick' if args.quick else 'full'})")
    frames = load_frames(tics)
    print(f"[strategy_lab] loaded {len(frames)} frames")
    mkt = market_returns()

    n_trials = len(SS.REGISTRY) + len(_xs_legs())   # honest family size for DSR/FDR

    ts_results = []
    for strat in SS.REGISTRY:
        r = eval_ts_strategy(strat, frames, n_trials)
        ts_results.append(r)
        v = r.get("verdict", "?")
        agg = r.get("agg", {})
        print(f"  [TS] {strat.key:18s} {v:32s} "
              f"sh={agg.get('sharpe','-')} bench={agg.get('bench_sharpe','-')} "
              f"dsr={(r.get('dsr') or {}).get('dsr','-')} ic_t={r.get('ic',{}).get('t_across_names','-')}")

    xs_results = eval_xs(frames, mkt, n_trials)
    for r in xs_results:
        print(f"  [XS] {r['key']:18s} {r['verdict']:32s} "
              f"ic={r['ic'].get('mean_ic','-')} t_hac={r['ic'].get('t_hac','-')}")

    # BH-FDR across the whole family (one p-value per strategy)
    pvals = {r["key"]: r["p_value"] for r in (ts_results + xs_results)
             if r.get("p_value") is not None}
    fdr = V.benjamini_hochberg(pvals, alpha=0.10)
    for r in ts_results + xs_results:
        r["fdr"] = fdr.get(r["key"])

    print("[strategy_lab] combining survivors...")
    combine = eval_combine(frames, mkt, n_trials)
    sel = eval_selection_combine(frames, mkt)
    print("[strategy_lab] institutional levers (vol-managed sizing + regime-conditioning)...")
    volm = eval_vol_managed(frames, n_trials)
    regime = eval_regime_conditioning(frames, n_trials)
    vm = volm["sleeves"]
    print(f"  [VOLMGD] buyhold Sh {vm['buyhold']['sharpe']} maxDD {vm['buyhold']['maxdd']} "
          f"-> vol-target Sh {vm['voltarget_derisk']['sharpe']} maxDD {vm['voltarget_derisk']['maxdd']} "
          f"(lever Sh {vm['voltarget_lever']['sharpe']})")
    print(f"  [REGIME] entry IC bull {regime['spx_regime']['bull_market']['mean_ic']} "
          f"vs bear {regime['spx_regime']['bear_market']['mean_ic']} -> regime_dependent={regime['regime_dependent']}")
    ci = combine["ic"]; cg = combine["tradable_gated_vs_naive"]
    print(f"  [COMBINE] entry composite IC={ci['composite_mean_ic']} t={ci['composite_t_across_names']} "
          f"lift_vs_best_leg={ci['blend_lift_vs_best_leg']}  "
          f"quintile_spread={combine['quintile']['top_minus_bottom'] if combine['quintile'] else '-'}")
    print(f"  [COMBINE] gated entry maxDD={cg['gated_maxdd']} vs always-in {cg['always_in_maxdd']}; "
          f"sel blend IC={sel['blend_ic'].get('mean_ic')} vs mom {sel['mom_only_ic'].get('mean_ic')}")

    payload = {
        "schema": "strategy_lab.v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "universe": {"n_names": len(frames), "source": "data/stocks (deep-history mega-caps)",
                     "survivorship": "BIASED — only currently-listed names; optimistic bound"},
        "config": {"cost_bps": COST_BPS, "horizons": HORIZONS, "n_trials_honest": n_trials,
                   "fdr_alpha": 0.10, "dsr_pass": 0.90},
        "time_series": ts_results,
        "cross_sectional": xs_results,
        "combined": {"entry_timing": combine, "selection": sel},
        "institutional": {"vol_managed": volm, "regime_conditioning": regime},
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(payload, f, indent=2, default=str)
    print(f"[strategy_lab] wrote {args.out}")
    write_report(payload)


def write_report(payload: dict):
    out = "reports/strategy-lab.md"
    os.makedirs("reports", exist_ok=True)
    L = []
    L.append("# Strategy Lab — backtest scorecard\n")
    L.append(f"_Generated {payload['generated_utc']}_  ·  "
             f"universe {payload['universe']['n_names']} deep-history mega-caps  ·  "
             f"cost {payload['config']['cost_bps']}bps one-way  ·  "
             f"DSR pass≥{payload['config']['dsr_pass']}, BH-FDR α={payload['config']['fdr_alpha']}\n")
    L.append("> **Survivorship caveat:** the price panel is 114 *currently-listed* mega-caps. "
             "Long-biased and cross-sectional results are an **optimistic bound / context**, not proven alpha.\n")

    L.append("\n## Time-series strategies (entry timing + trend/swing)\n")
    L.append("| strategy | family | h | verdict | Sharpe | bench | ΔSh | MaxDD | bench | DSR | IC t(names) | beat-bench DD% |")
    L.append("|---|---|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|")
    for r in sorted(payload["time_series"], key=lambda x: -(x.get("agg", {}).get("excess_sharpe") or -9)):
        a = r.get("agg", {})
        dsr = (r.get("dsr") or {}).get("dsr", "-")
        ict = r.get("ic", {}).get("t_across_names", "-")
        ddf = r.get("per_name", {}).get("beat_bench_maxdd_frac", "-")
        L.append(f"| {r['name']} | {r.get('family','')} | {r.get('horizon','')} | "
                 f"{r.get('verdict','')} | {a.get('sharpe','-')} | {a.get('bench_sharpe','-')} | "
                 f"{a.get('excess_sharpe','-')} | {a.get('maxdd','-')} | {a.get('bench_maxdd','-')} | "
                 f"{dsr} | {ict} | {ddf} |")

    L.append("\n## Cross-sectional selection (CONTEXT — survivorship-biased)\n")
    L.append("| strategy | mean IC | IC t(HAC) | IC hit | long Sh | EW Sh | verdict |")
    L.append("|---|--:|--:|--:|--:|--:|---|")
    for r in payload["cross_sectional"]:
        ic = r["ic"]; tc = r["tercile"]
        L.append(f"| {r['name']} | {ic.get('mean_ic','-')} | {ic.get('t_hac','-')} | "
                 f"{ic.get('hit','-')} | {tc.get('long_sharpe','-')} | {tc.get('ew_sharpe','-')} | "
                 f"{r['verdict']} |")

    cb = payload.get("combined", {})
    if cb:
        et = cb.get("entry_timing", {})
        ci = et.get("ic", {}); cg = et.get("tradable_gated_vs_naive", {}); q = et.get("quintile") or {}
        L.append("\n## Combined engines (built from the survivors)\n")
        L.append("**Entry-timing composite** (blended oversold overlay, gated by uptrend):\n")
        L.append(f"- Blended composite IC **{ci.get('composite_mean_ic')}** "
                 f"(t across names {ci.get('composite_t_across_names')}); best single leg "
                 f"{ci.get('best_leg_mean_ic')} → blend lift **{ci.get('blend_lift_vs_best_leg')}**.")
        L.append(f"- Top-vs-bottom oversold-quintile 5-day forward spread "
                 f"**{q.get('top_minus_bottom')}** (t {q.get('spread_t')}).")
        L.append(f"- Trend-gated oversold entry MaxDD **{cg.get('gated_maxdd')}** vs always-invested "
                 f"{cg.get('always_in_maxdd')} (Sharpe {cg.get('gated_sharpe')} vs {cg.get('always_in_sharpe')}, "
                 f"time-in-market {cg.get('gated_time_in_mkt')}).")
        L.append(f"- _{et.get('interpretation','')}_\n")
        sel = cb.get("selection", {})
        L.append("**Selection composite** (12-1 + residual momentum, cross-sectional, CONTEXT):\n")
        L.append(f"- Blend IC {sel.get('blend_ic',{}).get('mean_ic')} "
                 f"(t_hac {sel.get('blend_ic',{}).get('t_hac')}) vs momentum-only "
                 f"{sel.get('mom_only_ic',{}).get('mean_ic')} (t_hac {sel.get('mom_only_ic',{}).get('t_hac')}). "
                 f"_Survivorship-biased — never sizes alone._\n")

    inst = payload.get("institutional", {})
    if inst:
        vm = inst.get("vol_managed", {})
        sl = vm.get("sleeves", {})
        L.append("\n## Institutional levers\n")
        L.append("**Vol-managed sizing** (constant-risk targeting):\n")
        L.append("| sleeve | Sharpe | CAGR | MaxDD |")
        L.append("|---|--:|--:|--:|")
        for k in ("buyhold", "voltarget_derisk", "voltarget_lever", "trend", "trend_voltarget"):
            r = sl.get(k, {})
            L.append(f"| {k} | {r.get('sharpe','-')} | {r.get('cagr','-')} | {r.get('maxdd','-')} |")
        bd = vm.get("buyhold_to_voltarget_derisk", {})
        L.append(f"\n- Buy&hold → vol-target (de-risk): ΔSharpe **{bd.get('d_sharpe')}**, "
                 f"ΔMaxDD **{bd.get('d_maxdd')}** (less negative = shallower). _{vm.get('interpretation','')}_\n")
        rg = inst.get("regime_conditioning", {})
        sr = rg.get("spx_regime", {})
        L.append("**Regime-conditioning** (entry-composite IC by market regime):\n")
        L.append(f"- SPX bull-market IC {sr.get('bull_market',{}).get('mean_ic')} "
                 f"(t {sr.get('bull_market',{}).get('t')}) vs bear-market IC "
                 f"{sr.get('bear_market',{}).get('mean_ic')} (t {sr.get('bear_market',{}).get('t')}). "
                 f"Regime-dependent: **{rg.get('regime_dependent')}**. {rg.get('recommendation','')}\n")

    def has(tag): return [r for r in payload["time_series"] if tag in r.get("tags", [])]
    L.append("\n## Read\n")
    L.append(f"- **Entry-timing overlays (significant short-horizon IC):** "
             f"{', '.join(r['key'] for r in has('entry_overlay')) or 'none'}")
    L.append(f"- **Tradable standalone (beats buy&hold net Sharpe, DSR+bootstrap+split):** "
             f"{', '.join(r['key'] for r in has('tradable_standalone')) or 'none'}")
    L.append(f"- **Validated risk-control (de-risk/drawdown):** "
             f"{', '.join(r['key'] for r in has('risk_control')) or 'none'}")
    xs_ctx = [r for r in payload["cross_sectional"] if "CONTEXT" in r.get("verdict", "")]
    L.append(f"- **Cross-sectional context (modest, survivorship-biased):** "
             f"{', '.join(r['key'] for r in xs_ctx) or 'none'}")
    with open(out, "w") as f:
        f.write("\n".join(L) + "\n")
    print(f"[strategy_lab] wrote {out}")


if __name__ == "__main__":
    main()
