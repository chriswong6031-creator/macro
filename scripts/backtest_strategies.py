"""Backtest the Strategy-Lab legs across MULTIPLE panels and decide which earn
weight — the "more strategies + honest measurement" pass feeding the scoring /
selection engines.

Panels (each a closes matrix; the leg fns are point-in-time/causal):
  deep      data/stocks (114 deep-history S&P SURVIVORS, ~40y)   -> length, cycles
  sp500     data/breadth/_closes_cache + sp1500 PIT membership   -> breadth, recent
  smallcap  data/smallcap_breadth/_closes_cache (603 names, ~3y) -> breadth, small-cap

For each (panel, leg) we measure, at a monthly rebalance, the SECTOR-NEUTRAL
cross-sectional rank-IC against the cross-sectionally-DEMEANED forward H-day return
(market-neutral outcome), then engine.validation.ic_summary (mean IC, IC-IR,
Newey-West HAC t, hit, n) and a top-minus-bottom tercile spread.  A leg's edge is
trusted only when its SIGN agrees across panels — a leg that flips sign between the
deep survivor panel and a breadth panel is a panel artifact, not an edge.

Honesty: no panel here folds in delisted names, so all are survivorship-touched
(deep most, breadth panels less); the sp500 cache is short (~15mo) so its long-
lookback legs are THIN and flagged.  This is calibration evidence for WEIGHTING, not
a ship decision — that still runs through the PIT, DSR-gated harnesses.

Run:
  .venv/bin/python -m scripts.backtest_strategies --horizon 63
  .venv/bin/python -m scripts.backtest_strategies --horizon 21 --panels deep,smallcap
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
import time
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
warnings.filterwarnings("ignore")
import logging  # noqa: E402

logging.disable(logging.CRITICAL)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from engine import strategy_lab as sl  # noqa: E402
from engine.validation import (deflated_sharpe, dsr_verdict, ic_summary,  # noqa: E402
                               rank_ic, ret_moments, _maxdd, _sharpe)
from lib import config  # noqa: E402


def _load_sue_panel():
    p = config.data_dir() / "edgar" / "eps_quarterly.parquet"
    if not p.exists():
        return pd.DataFrame()
    try:
        return sl.build_sue_panel(pd.read_parquet(p))
    except Exception:
        return pd.DataFrame()


# ------------------------------------------------------------- panels --------

def _sector_map(path: Path) -> pd.Series | None:
    if not path.exists():
        return None
    meta = pd.read_parquet(path)
    col = "sector" if "sector" in meta.columns else None
    if col is None:
        return None
    return meta[col].astype(str)


def load_panel(kind: str):
    """Return (closes_df, sector_series_or_None, membership_df_or_None)."""
    dd = config.data_dir()
    if kind == "deep":
        cols = {}
        for f in sorted(glob.glob("data/stocks/*.parquet")):
            try:
                cols[Path(f).stem] = pd.read_parquet(f)["close"].dropna()
            except Exception:
                continue
        closes = pd.DataFrame(cols).sort_index()
        return closes, _sector_map(dd / "breadth" / "constituents.parquet"), None
    if kind == "sp500":
        closes = pd.read_parquet(dd / "breadth" / "_closes_cache.parquet").sort_index()
        mp = dd / "breadth" / "sp1500_pit_membership.parquet"
        mem = None
        if mp.exists():
            mem = pd.read_parquet(mp)
            mem["start_date"] = pd.to_datetime(mem["start_date"])
            mem["end_date"] = pd.to_datetime(mem["end_date"])
        return closes, _sector_map(dd / "breadth" / "constituents.parquet"), mem
    if kind == "smallcap":
        closes = pd.read_parquet(dd / "smallcap_breadth" / "_closes_cache.parquet").sort_index()
        sec = _sector_map(dd / "smallcap_breadth" / "constituents.parquet")
        return closes, sec, None
    raise ValueError(f"unknown panel {kind}")


def _eligible(mem: pd.DataFrame, d) -> set | None:
    if mem is None:
        return None
    d = pd.Timestamp(d)
    m = (mem["start_date"] <= d) & (mem["end_date"].isna() | (mem["end_date"] >= d))
    return set(mem.loc[m, "ticker"])


# --------------------------------------------------------- measurement -------

def _verdict(summ: dict) -> str:
    if summ.get("n", 0) < 6:
        return "thin"
    ir, mic = summ.get("ic_ir"), summ.get("mean_ic", 0)
    if ir is None:
        return "thin"
    if ir >= 0.30 and mic > 0:
        return "scored"
    if ir >= 0.10 and mic > 0:
        return "context"
    if ir <= -0.10 and mic < 0:
        return "inverse"            # consistent NEGATIVE edge (informative, flip sign to use)
    return "no-edge"


def _subperiod_signs(ic_dates: list, subperiods: int) -> dict:
    """Split the per-date (pos, ic) list into `subperiods` contiguous chunks and
    report each chunk's mean IC + whether the sign is consistent across chunks —
    the antidote to a single-regime artifact (e.g. one momentum-led year)."""
    ics = [ic for _, ic in ic_dates if ic == ic]
    if len(ics) < subperiods * 3:
        return {"sub_means": None, "sub_sign_agree": None}
    chunks = np.array_split(np.array(ics), subperiods)
    means = [round(float(c.mean()), 4) for c in chunks if len(c)]
    signs = [np.sign(m) for m in means if m != 0]
    agree = bool(signs and max(sum(s > 0 for s in signs), sum(s < 0 for s in signs)) == len(signs))
    return {"sub_means": means, "sub_sign_agree": agree}


def _dsr_gate(spread_pct_series: list, horizon: int, rebal: int, n_trials: int) -> dict:
    """Deflated-Sharpe gate on a leg's per-rebalance top-minus-bottom tercile L/S
    return series. De-overlap to ~non-overlapping periods (the L/S return is a
    `horizon`-day return sampled every `rebal` days), then haircut the Sharpe for
    having tried `n_trials` legs (Bailey-Lopez de Prado). The honest "does it
    survive multiple testing" test on the data we have."""
    step = max(1, int(np.ceil(horizon / rebal)))             # ensure step*rebal >= horizon
    ls = np.array(spread_pct_series[::step], float) / 100.0   # non-overlapping, decimal
    if len(ls) < 12:
        return {"dsr": None, "ls_sharpe": None, "n_periods": len(ls), "verdict": "thin"}
    ppy = 252.0 / horizon
    sr = _sharpe(ls, int(round(ppy)))                         # annualized
    sr_period = float(np.mean(ls) / np.std(ls)) if np.std(ls) else float("nan")
    s = pd.Series(ls)
    dsr = deflated_sharpe(sr_period, float(s.skew()), float(s.kurt() + 3.0),
                          len(ls), max(2, n_trials))
    dval = dsr.get("dsr") if isinstance(dsr, dict) else (dsr if dsr is not None else None)
    return {"dsr": round(float(dval), 3) if dval is not None else None,
            "ls_sharpe": round(sr, 2), "ls_maxdd": round(100 * _maxdd(ls), 1),
            "n_periods": len(ls),
            "verdict": dsr_verdict(dval) if dval is not None else "n/a"}


def measure_panel(kind: str, horizon: int, rebal: int, min_names: int,
                  warmup: int, subperiods: int = 3, sue_panel=None,
                  dsr: bool = False) -> dict:
    closes, sec, mem = load_panel(kind)
    if closes.empty:
        return {"panel": kind, "error": "empty"}
    idx = closes.index
    positions = list(range(warmup, len(idx) - horizon - 1, rebal))

    # leg registry for this run = the closure legs (+ optional SUE matrix leg)
    legs_meta = dict(sl.STRATEGIES)
    use_sue = sue_panel is not None and not sue_panel.empty
    if use_sue:
        legs_meta["sue"] = {"family": "fundamental", "fn": None,
                            "note": "PIT standardized earnings surprise"}
    ic_sn = {k: [] for k in legs_meta}            # list of (pos, ic) for subperiods
    ic_raw = {k: [] for k in legs_meta}
    spread = {k: [] for k in legs_meta}
    n_universe = []

    for pos in positions:
        d = idx[pos]
        elig = _eligible(mem, d)
        fwd = sl.forward_excess(closes, pos, horizon, elig)   # demeaned, market-neutral
        if len(fwd) < min_names:
            continue
        n_universe.append(len(fwd))
        for name, meta in legs_meta.items():
            try:
                raw = sl.sue_asof(sue_panel, d) if name == "sue" else meta["fn"](closes, d)
            except Exception:
                continue
            if raw is None or len(raw) < min_names:
                continue
            raw = raw[[t for t in raw.index if t in fwd.index]]  # align to outcome set
            if elig is not None:
                raw = raw[[t for t in raw.index if t in elig]]
            if len(raw) < min_names:
                continue
            sn = sl.sector_demean(raw, sec)
            ic_raw[name].append(rank_ic(raw, fwd))
            ic_sn[name].append((pos, rank_ic(sn, fwd)))
            j = pd.concat([sn.rename("s"), fwd.rename("f")], axis=1).dropna()
            if len(j) >= 9:
                r = j["s"].rank()
                top = j["f"][r >= r.quantile(2 / 3)].mean()
                bot = j["f"][r <= r.quantile(1 / 3)].mean()
                if pd.notna(top) and pd.notna(bot):
                    spread[name].append(float(top - bot))

    ppy = max(1, round(252 / rebal))
    n_trials = len(legs_meta)
    legs = {}
    for name, meta in legs_meta.items():
        ics = [ic for _, ic in ic_sn[name] if ic == ic]
        summ = ic_summary(ics, periods_per_year=ppy)
        sp = spread[name]
        raw_clean = [x for x in ic_raw[name] if x == x]
        sub = _subperiod_signs(ic_sn[name], subperiods)
        legs[name] = {
            "family": meta["family"], "note": meta["note"],
            "mean_ic_sn": summ.get("mean_ic"), "ic_ir": summ.get("ic_ir"),
            "t_hac": summ.get("t_hac"), "hit": summ.get("hit"), "n_dates": summ.get("n"),
            "mean_ic_raw": round(float(np.mean(raw_clean)), 4) if raw_clean else None,
            "spread_pct": round(100 * float(np.mean(sp)), 2) if sp else None,
            "sub_means": sub["sub_means"], "sub_sign_agree": sub["sub_sign_agree"],
            "verdict": _verdict(summ),
        }
        if dsr:
            legs[name]["dsr_gate"] = _dsr_gate(sp, horizon, rebal, n_trials)
        # a measured edge that flips sign across sub-periods is regime-fragile,
        # not a stable weightable signal — demote it.
        if legs[name]["verdict"] in ("scored", "context") and sub["sub_sign_agree"] is False:
            legs[name]["verdict"] = "fragile"
    return {
        "panel": kind, "n_names": int(closes.shape[1]),
        "span": [str(idx.min().date()), str(idx.max().date())],
        "n_rebalances": len(n_universe),
        "median_universe": int(np.median(n_universe)) if n_universe else 0,
        "horizon": horizon, "rebal": rebal, "legs": legs,
    }


def crowding_drawdown(kind: str, horizon: int, rebal: int, warmup: int,
                      min_names: int) -> dict:
    """The test recommendation #2 (crowding penalty) is gated on: do high
    rel-strength (CROWDED) names suffer materially DEEPER forward drawdowns than
    the rest? Splits the panel each rebalance into top-RS-decile vs the rest and
    compares forward `horizon`-day MAE (max adverse excursion) and mean return.
    If crowded names are NOT worse on drawdown, the conviction dock is unjustified
    on BOTH axes; if they ARE worse, the dock belongs on the sizing/risk axis."""
    closes, _sec, mem = load_panel(kind)
    if closes.empty:
        return {"error": "empty"}
    idx = closes.index
    cv = closes.to_numpy()
    col = {c: i for i, c in enumerate(closes.columns)}
    top_mae, rest_mae, top_ret, rest_ret = [], [], [], []
    for pos in range(warmup, len(idx) - horizon - 1, rebal):
        d = idx[pos]
        rs = sl.live_rs_crowded(closes, d)
        if (elig := _eligible(mem, d)) is not None:
            rs = rs[[t for t in rs.index if t in elig]]
        rs = rs.dropna()
        if len(rs) < min_names:
            continue
        thresh = rs.quantile(0.9)
        for t, v in rs.items():
            i = col[t]
            p0 = cv[pos, i]
            fut = cv[pos + 1:pos + 1 + horizon, i]
            if not (p0 > 0) or np.isnan(p0) or np.all(np.isnan(fut)):
                continue
            mae = np.nanmin(fut) / p0 - 1.0
            ret = cv[pos + horizon, i] / p0 - 1.0
            if np.isnan(ret):
                continue
            (top_mae if v >= thresh else rest_mae).append(mae)
            (top_ret if v >= thresh else rest_ret).append(ret)
    if len(top_mae) < 50:
        return {"error": "thin", "n_top": len(top_mae)}
    return {
        "panel": kind, "n_top": len(top_mae), "n_rest": len(rest_mae),
        "top_decile_mean_ret_pct": round(100 * float(np.mean(top_ret)), 2),
        "rest_mean_ret_pct": round(100 * float(np.mean(rest_ret)), 2),
        "top_decile_mae_p10_pct": round(100 * float(np.percentile(top_mae, 10)), 2),
        "rest_mae_p10_pct": round(100 * float(np.percentile(rest_mae, 10)), 2),
        "top_decile_mae_med_pct": round(100 * float(np.median(top_mae)), 2),
        "rest_mae_med_pct": round(100 * float(np.median(rest_mae)), 2),
        "verdict": ("crowded names DEEPER drawdown -> keep dock as risk/sizing"
                    if np.percentile(top_mae, 10) < np.percentile(rest_mae, 10) - 0.01
                    else "crowded names NOT worse on drawdown -> dock unjustified"),
    }


def cross_panel(results: list[dict]) -> dict:
    """For each leg, the sign of mean_ic_sn across panels (only non-thin) and a
    consensus verdict — the robustness lens the weighter should trust."""
    out = {}
    names = sorted({n for r in results for n in r.get("legs", {})})
    for name in names:
        signs, irs, fam = [], [], None
        for r in results:
            leg = r.get("legs", {}).get(name)
            if not leg or leg["verdict"] == "thin" or leg["ic_ir"] is None:
                continue
            fam = leg["family"]
            signs.append(np.sign(leg["mean_ic_sn"] or 0))
            irs.append(leg["ic_ir"])
        if not signs:
            out[name] = {"consensus": "untested", "panels": 0}
            continue
        pos = sum(1 for s in signs if s > 0)
        neg = sum(1 for s in signs if s < 0)
        agree = max(pos, neg) == len(signs)
        direction = "constructive" if pos > neg else "inverse" if neg > pos else "mixed"
        out[name] = {
            "panels": len(signs), "pos": pos, "neg": neg,
            "sign_agree": agree, "direction": direction,
            "ic_ir_range": [round(min(irs), 3), round(max(irs), 3)],
            "family": fam,
            "consensus": (
                "robust-edge" if agree and direction == "constructive"
                and min(abs(i) for i in irs) >= 0.10
                else "robust-inverse" if agree and direction == "inverse"
                and min(abs(i) for i in irs) >= 0.10
                else "weak-consistent" if agree
                else "panel-artifact"),
        }
    return out


# ------------------------------------------------------------------ main -----

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--panels", type=str, default="deep,sp500,smallcap")
    ap.add_argument("--horizon", type=int, default=63)
    ap.add_argument("--rebal", type=int, default=21)
    ap.add_argument("--min-names", type=int, default=12)
    ap.add_argument("--warmup", type=int, default=60)
    ap.add_argument("--subperiods", type=int, default=3)
    ap.add_argument("--no-sue", action="store_true", help="skip the PIT SUE leg")
    ap.add_argument("--no-dsr", action="store_true", help="skip the Deflated-Sharpe gate")
    ap.add_argument("--out", type=str, default="")
    args = ap.parse_args()

    t0 = time.time()
    sue_panel = pd.DataFrame() if args.no_sue else _load_sue_panel()
    if not sue_panel.empty:
        print(f"[strat] SUE panel: {sue_panel.shape[1]} tickers, "
              f"{sue_panel.index.min().date()}..{sue_panel.index.max().date()}", flush=True)
    results = []
    for kind in [p.strip() for p in args.panels.split(",") if p.strip()]:
        t1 = time.time()
        r = measure_panel(kind, args.horizon, args.rebal, args.min_names, args.warmup,
                          args.subperiods, sue_panel=sue_panel, dsr=not args.no_dsr)
        r["elapsed_s"] = round(time.time() - t1, 1)
        results.append(r)
        nd = r.get("n_rebalances", 0)
        print(f"[strat] panel={kind:<9} names={r.get('n_names','?'):<4} "
              f"rebalances={nd:<4} medU={r.get('median_universe','?'):<4} "
              f"({r['elapsed_s']}s)", flush=True)

    # crowding-penalty drawdown test (recommendation #2 gate) on the deep panel
    crowd_dd = crowding_drawdown("deep", args.horizon, args.rebal, args.warmup, args.min_names)

    xpanel = cross_panel(results)
    payload = {"kind": "strategy_backtest.v1",
               "meta": {"horizon": args.horizon, "rebal": args.rebal,
                        "panels": [r["panel"] for r in results],
                        "elapsed_s": round(time.time() - t0, 1),
                        "caveats": [
                            "no panel folds in delisted names -> all survivorship-touched",
                            "sp500 cache ~15mo -> long-lookback legs are THIN (flagged n_dates<6)",
                            "sector labels are CURRENT/static (constituents.parquet), not point-in-time -> "
                            "the sector-neutral (ic_sn) column carries a small known bias; ic_raw is sector-blind",
                            "weighting evidence only; ship via PIT + DSR-gated harnesses",
                            "delisted-aware deep PIT fetch BLOCKED here (network 429 + _closes_deep "
                            "unbuilt); DSR gate runs on the survivor deep panel"]},
               "panels": results, "cross_panel": xpanel, "crowding_drawdown": crowd_dd}

    out = Path(args.out) if args.out else Path(
        f"data/signal_training/strategies_h{args.horizon}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2))

    # ---- scorecard ----
    for r in results:
        if "legs" not in r:
            continue
        print(f"\n===== panel={r['panel']}  names={r['n_names']}  "
              f"span={r['span'][0]}..{r['span'][1]}  rebal={r['n_rebalances']}  H={r['horizon']}d =====")
        print(f"  {'leg':<18}{'fam':<11}{'ic_sn':>8}{'ic_ir':>7}{'t_hac':>7}"
              f"{'hit':>6}{'spread%':>9}{'n':>5}{'subOK':>6}{'DSR':>6}  verdict")
        rows = sorted(r["legs"].items(), key=lambda kv: (kv[1]["ic_ir"] or -9), reverse=True)
        for name, v in rows:
            sub = "—" if v["sub_sign_agree"] is None else ("yes" if v["sub_sign_agree"] else "NO")
            dsr = v.get("dsr_gate", {}).get("dsr")
            dsr = "—" if dsr is None else f"{dsr:.2f}"
            print(f"  {name:<18}{v['family']:<11}{str(v['mean_ic_sn']):>8}{str(v['ic_ir']):>7}"
                  f"{str(v['t_hac']):>7}{str(v['hit']):>6}{str(v['spread_pct']):>9}"
                  f"{str(v['n_dates']):>5}{sub:>6}{dsr:>6}  {v['verdict']}")

    print("\n===== CROSS-PANEL consensus (sign agreement across panels) =====")
    print(f"  {'leg':<18}{'fam':<11}{'panels':>7}{'dir':>14}{'ic_ir_range':>16}  consensus")
    for name, v in sorted(xpanel.items(), key=lambda kv: kv[1].get("consensus", "z")):
        if v.get("consensus") == "untested":
            print(f"  {name:<18}{'?':<11}{'0':>7}{'—':>14}{'—':>16}  untested")
            continue
        print(f"  {name:<18}{str(v['family']):<11}{v['panels']:>7}{v['direction']:>14}"
              f"{str(v['ic_ir_range']):>16}  {v['consensus']}")

    if "verdict" in crowd_dd:
        print("\n===== CROWDING-PENALTY drawdown test (deep panel, rec #2 gate) =====")
        print(f"  top-RS-decile fwd ret {crowd_dd['top_decile_mean_ret_pct']}% vs rest "
              f"{crowd_dd['rest_mean_ret_pct']}%  |  MAE p10 top {crowd_dd['top_decile_mae_p10_pct']}% "
              f"vs rest {crowd_dd['rest_mae_p10_pct']}%")
        print(f"  -> {crowd_dd['verdict']}")
    print(f"\n[strat] wrote {out}  ({payload['meta']['elapsed_s']}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
