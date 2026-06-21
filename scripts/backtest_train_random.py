"""Backtest-TRAIN the technical + momentum signal strategies on RANDOM tickers.

In this repo "training" is honest walk-forward CALIBRATION + forward-return
MEASUREMENT — not black-box parameter fitting. Two passes, both causal:

  TECHNICAL  (per-instrument walk-forward)
      For each random ticker, replay the cycle-ladder signal bar-by-bar with NO
      look-ahead: the state at bar i is computed from close[i-WIN:i+1] only (the
      same trailing-window method as engine.cycles), and the OUTCOME uses
      close[i+1 : i+1+fwd].  Each fire is bucketed by the trained dimensions
      (ladder STATE, higher-timeframe REGIME, conviction-SCORE band, RSI band)
      and scored on the honest lens — forward HIT-rate, mean return AND drawdown
      (max adverse excursion), since 21d mean-return alone is U-shaped (D43).
      The result is the calibrated map "this technical signal -> these odds".

  MOMENTUM  (cross-sectional, monthly rebalance)
      Across the SAME random panel, measure every engine.predictive_signals leg
      (12-1 momentum, frog-in-the-pan continuity, 52w-high proximity, MAX/lottery
      caution, downside-asymmetry) point-in-time: per-date rank-IC vs the forward
      H-day return, then IC, IC-IR, Newey-West HAC t, hit-rate and a top-minus-
      bottom tercile spread.  A leg earns "trained weight" only if it shows a
      stable positive IC-IR here — the empirical decision that weights the legs.

Honesty caveats (printed + stored): the data/stocks panel is the deep-history
S&P survivors, so it is SURVIVORSHIP-biased and has NO point-in-time membership;
several legs are tested at once with no multiple-testing haircut.  This is a fast
TRAINING/calibration read for ordering + sizing intuition — a ship decision still
goes through the PIT, DSR-gated harnesses (scripts.conviction_v2_measure,
scripts.validate).  Reproducible: the ticker draw is seeded.

Run:
  .venv/bin/python -m scripts.backtest_train_random --n 24 --seed 42
  .venv/bin/python -m scripts.backtest_train_random --n 30 --seed 7 --mom-horizon 63
"""
from __future__ import annotations

import argparse
import glob
import json
import random
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

from engine.cycles import (  # noqa: E402
    cycle_state, early_signals, ladder_state, mtf_snapshot,
)
from engine import predictive_signals as ps  # noqa: E402
from engine.validation import ic_summary, rank_ic  # noqa: E402


# --------------------------------------------------------------- universe ----

def sample_tickers(n: int, seed: int) -> list[str]:
    """Seeded random draw of `n` tickers from the deep-history stock panel."""
    files = sorted(glob.glob("data/stocks/*.parquet"))
    names = [Path(f).stem for f in files]
    rng = random.Random(seed)
    n = min(n, len(names))
    return sorted(rng.sample(names, n))


def _load_close_high(ticker: str):
    df = pd.read_parquet(f"data/stocks/{ticker}.parquet")
    return df["close"].dropna(), df.get("high")


# ---------------------------------------------------- technical training -----

def _rsi_band(rsi: float | None) -> str:
    if rsi is None:
        return "rsi:na"
    if rsi < 30:
        return "rsi:<30 oversold"
    if rsi < 45:
        return "rsi:30-45"
    if rsi < 55:
        return "rsi:45-55"
    if rsi < 70:
        return "rsi:55-70"
    return "rsi:70+ overbought"


def _score_band(s: float | None) -> str:
    if s is None:
        return "conv:na"
    if s >= 40:
        return "conv:>=40 strong-buy"
    if s >= 15:
        return "conv:15-39 buy"
    if s > -15:
        return "conv:-15..15 neutral"
    if s > -40:
        return "conv:-40..-15 caution"
    return "conv:<=-40 avoid"


def _agg(rows: list) -> dict:
    """rows: list of (ret21, mae21, ret63, mae63) — summarize the honest lens."""
    a = np.asarray(rows, float)
    if len(a) < 30:
        return {"n": len(a)}
    r21, mae21, r63, mae63 = a[:, 0], a[:, 1], a[:, 2], a[:, 3]
    return {
        "n": int(len(a)),
        "hit21": round(100 * float((r21 > 0).mean()), 1),
        "mean21": round(100 * float(r21.mean()), 2),
        "mae_med21": round(100 * float(np.median(mae21)), 2),
        "mae_p10_21": round(100 * float(np.percentile(mae21, 10)), 2),
        "hit63": round(100 * float((r63 > 0).mean()), 1),
        "mean63": round(100 * float(r63.mean()), 2),
        "mae_p10_63": round(100 * float(np.percentile(mae63, 10)), 2),
    }


def technical_train(tickers: list[str], win: int, step: int, f1: int, f2: int,
                    max_bars: int) -> dict:
    """Walk-forward replay of the cycle-ladder; bucket forward outcomes by the
    trained signal dimensions. No look-ahead (state from close[:i], outcome from
    close[i+1:]). `max_bars` caps the most-recent eval bars per ticker for speed."""
    buckets: dict[str, dict[str, list]] = {
        "by_state": {}, "by_regime": {}, "by_score_band": {},
        "by_rsi_band": {}, "by_early": {},
    }
    n_inst = n_eval = 0
    for tk in tickers:
        try:
            close, high = _load_close_high(tk)
        except Exception:
            continue
        if len(close) < win + f2 + 50:
            continue
        n_inst += 1
        cv = close.to_numpy()
        lo = win
        hi = len(close) - f2 - 1
        if max_bars and (hi - lo) // step > max_bars:
            lo = hi - max_bars * step                      # keep the most recent window
        for i in range(lo, hi, step):
            sub = close.iloc[i - win:i + 1]
            hsub = high.reindex(sub.index) if high is not None else None
            try:
                cyc = cycle_state(sub, hsub, "equity")
                if not cyc:
                    continue
                mtf = mtf_snapshot(sub, "equity")
                early = early_signals(sub, cyc, mtf)
                lad = ladder_state(cyc, mtf, early)
            except Exception:
                continue
            if not lad or not lad.get("state"):
                continue
            p0 = cv[i]
            if p0 <= 0:
                continue
            rec = (
                cv[i + f1] / p0 - 1.0,
                cv[i + 1:i + 1 + f1].min() / p0 - 1.0,
                cv[i + f2] / p0 - 1.0,
                cv[i + 1:i + 1 + f2].min() / p0 - 1.0,
            )
            n_eval += 1
            d = mtf.get("D", {}) or {}
            buckets["by_state"].setdefault(lad["state"], []).append(rec)
            buckets["by_regime"].setdefault(
                f"regime:{lad.get('regime', 'na')}", []).append(rec)
            buckets["by_score_band"].setdefault(_score_band(lad.get("score")), []).append(rec)
            buckets["by_rsi_band"].setdefault(_rsi_band(d.get("rsi14")), []).append(rec)
            if early and early.get("dir"):
                buckets["by_early"].setdefault(
                    f"early:{early['dir']} [{early.get('tier', '?')}]", []).append(rec)

    out = {"n_instruments": n_inst, "n_evals": n_eval}
    for dim, b in buckets.items():
        out[dim] = {k: _agg(v) for k, v in sorted(b.items())}
    return out


# ----------------------------------------------------- momentum training -----

def _closes_matrix(tickers: list[str]) -> pd.DataFrame:
    cols = {}
    for tk in tickers:
        try:
            cols[tk] = pd.read_parquet(f"data/stocks/{tk}.parquet")["close"].dropna()
        except Exception:
            continue
    if not cols:
        return pd.DataFrame()
    return pd.DataFrame(cols).sort_index()


def momentum_train(closes: pd.DataFrame, horizon: int, rebal: int,
                   min_names: int) -> dict:
    """Cross-sectional forward-IC of each predictive_signals leg on the panel.
    Causal: the signal at date d uses only closes.loc[:d]; the OUTCOME is the
    forward `horizon`-day return. Rebalances every `rebal` trading days."""
    if closes.empty or closes.shape[1] < min_names:
        return {"error": "panel too small", "n_names": int(closes.shape[1])}

    idx = closes.index
    # EW panel proxy for downside_asym, rebuilt per-date from closes.loc[:d] so the
    # future tail is physically un-indexable (causality structural, not incidental —
    # the leg already reindexes onto the trailing window, but this hardens against a
    # later refactor that touches market.loc[> asof]).
    legs = {
        "mom_12_1": lambda d: ps.mom_12_1(closes, d),
        "fip_continuity": lambda d: ps.fip_continuity(closes, d),
        "near_52w_high": lambda d: ps.near_52w_high(closes, d),
        "max_caution": lambda d: ps.max_caution(closes, d),
        "downside_asym": lambda d: ps.downside_asym(
            closes, d, closes.loc[:d].pct_change().mean(axis=1)),
    }
    warmup = 252 + 21 + 5
    positions = list(range(warmup, len(idx) - horizon - 1, rebal))
    ic_series: dict[str, list] = {k: [] for k in legs}
    spread_series: dict[str, list] = {k: [] for k in legs}
    n_dates = 0
    for pos in positions:
        d = idx[pos]
        cur = closes.iloc[pos]
        fwd = closes.iloc[pos + horizon] / cur - 1.0       # outcome (future) — OK
        fwd = fwd.dropna()
        if len(fwd) < min_names:
            continue
        n_dates += 1
        for name, fn in legs.items():
            try:
                sig = fn(d)
            except Exception:
                continue
            if sig is None or len(sig) < min_names:
                continue
            ic = rank_ic(sig, fwd)
            if ic == ic:                                   # not NaN
                ic_series[name].append(ic)
            j = pd.concat([sig.rename("s"), fwd.rename("f")], axis=1).dropna()
            if len(j) >= 9:
                r = j["s"].rank()
                top = j["f"][r >= r.quantile(2 / 3)].mean()
                bot = j["f"][r <= r.quantile(1 / 3)].mean()
                if pd.notna(top) and pd.notna(bot):
                    spread_series[name].append(float(top - bot))

    ppy = max(1, round(252 / rebal))
    out = {"n_names": int(closes.shape[1]), "n_dates": n_dates,
           "horizon": horizon, "rebal": rebal, "legs": {}}
    for name in legs:
        summ = ic_summary(ic_series[name], periods_per_year=ppy)
        sp = spread_series[name]
        summ["spread_mean_pct"] = round(100 * float(np.mean(sp)), 2) if sp else None
        summ["spread_hit"] = round(float(np.mean([s > 0 for s in sp])), 3) if sp else None
        # trained verdict: a leg earns weight only with a stable positive IC-IR
        ir = summ.get("ic_ir")
        summ["trained_weight"] = (
            "scored" if (ir is not None and ir >= 0.30 and summ.get("mean_ic", 0) > 0)
            else "context" if (ir is not None and ir >= 0.10 and summ.get("mean_ic", 0) > 0)
            else "no-edge")
        out["legs"][name] = summ
    return out


# ------------------------------------------------------------------ main -----

def _fmt_tech_dim(title: str, d: dict) -> list[str]:
    lines = [f"  {title}"]
    rows = [(k, v) for k, v in d.items() if v.get("n", 0) >= 30]
    rows.sort(key=lambda kv: kv[1].get("mean63", 0), reverse=True)
    if not rows:
        return lines + ["    (no bucket reached n>=30)"]
    lines.append(f"    {'bucket':<26} {'n':>6} {'hit21':>6} {'ret21':>7} "
                 f"{'maeP10':>7} {'hit63':>6} {'ret63':>7}")
    for k, v in rows:
        lines.append(f"    {k[:26]:<26} {v['n']:>6} {v['hit21']:>6} "
                     f"{v['mean21']:>7} {v['mae_p10_21']:>7} {v['hit63']:>6} {v['mean63']:>7}")
    return lines


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=24, help="random tickers to draw")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--win", type=int, default=600)
    ap.add_argument("--step", type=int, default=10)
    ap.add_argument("--f1", type=int, default=21)
    ap.add_argument("--f2", type=int, default=63)
    ap.add_argument("--max-bars", type=int, default=500,
                    help="cap most-recent eval bars per ticker (0=all)")
    ap.add_argument("--mom-horizon", type=int, default=63)
    ap.add_argument("--rebal", type=int, default=21)
    ap.add_argument("--min-names", type=int, default=10)
    ap.add_argument("--out", type=str, default="")
    args = ap.parse_args()

    t0 = time.time()
    tickers = sample_tickers(args.n, args.seed)
    print(f"[train] seed={args.seed}  n={len(tickers)} random tickers")
    print(f"        {', '.join(tickers)}")

    print(f"[train] TECHNICAL walk-forward (win={args.win} step={args.step} "
          f"fwd={args.f1}/{args.f2} max_bars={args.max_bars}) ...", flush=True)
    tech = technical_train(tickers, args.win, args.step, args.f1, args.f2, args.max_bars)
    print(f"        instruments={tech['n_instruments']}  evaluated fires={tech['n_evals']}  "
          f"({time.time() - t0:.0f}s)", flush=True)

    print(f"[train] MOMENTUM cross-section (H={args.mom_horizon} rebal={args.rebal}) ...",
          flush=True)
    closes = _closes_matrix(tickers)
    mom = momentum_train(closes, args.mom_horizon, args.rebal, args.min_names)

    payload = {
        "kind": "signal_training.v1",
        "meta": {
            "seed": args.seed, "n_tickers": len(tickers), "tickers": tickers,
            "win": args.win, "step": args.step, "f1": args.f1, "f2": args.f2,
            "mom_horizon": args.mom_horizon, "rebal": args.rebal,
            "elapsed_s": round(time.time() - t0, 1),
            "caveats": [
                "data/stocks panel = deep-history S&P survivors -> SURVIVORSHIP-biased, NO PIT membership",
                "multiple legs tested with no multiple-testing haircut here",
                "TRAINING/calibration read only; ship via scripts.conviction_v2_measure (PIT) + DSR gate",
            ],
        },
        "technical": tech,
        "momentum": mom,
    }

    out = Path(args.out) if args.out else Path(
        f"data/signal_training/train_seed{args.seed}_n{len(tickers)}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2))

    # ----- readable scorecard -----
    print("\n================ TECHNICAL strategy — trained calibration ================")
    for dim, title in [("by_state", "Ladder STATE (the technical signal)"),
                       ("by_regime", "Higher-timeframe REGIME gate"),
                       ("by_score_band", "Conviction-SCORE band"),
                       ("by_rsi_band", "RSI band"),
                       ("by_early", "Anticipatory early_signals")]:
        for ln in _fmt_tech_dim(title, tech.get(dim, {})):
            print(ln)
    print("\n================ MOMENTUM strategy — trained forward IC ==================")
    if "legs" in mom:
        print(f"  panel={mom['n_names']} names  dates={mom['n_dates']}  "
              f"H={mom['horizon']}d  (IC-IR>=0.30 -> scored, >=0.10 -> context)")
        print(f"  {'leg':<16} {'mean_ic':>8} {'ic_ir':>6} {'t_hac':>6} "
              f"{'hit':>5} {'spread%':>8} {'verdict':>8}")
        for name, v in mom["legs"].items():
            print(f"  {name:<16} {str(v.get('mean_ic')):>8} {str(v.get('ic_ir')):>6} "
                  f"{str(v.get('t_hac')):>6} {str(v.get('hit')):>5} "
                  f"{str(v.get('spread_mean_pct')):>8} {v.get('trained_weight', '?'):>8}")
    else:
        print(f"  {mom}")
    print(f"\n[train] wrote {out}  ({payload['meta']['elapsed_s']}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
