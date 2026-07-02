"""TRACK-A verification of the BTC Vector `optimal` allocation (signal_lab SCORED claim).

READ-ONLY research. Re-runs the LIVE engine (engine/btc_signals.compute_all →
alloc_optimal_raw) over 2015-01..present net of 10bps and computes EVERY gate the
SCORED tier requires, reusing engine/validation.py primitives:

  - allocation backtest vs HODL (Sharpe / MaxDD payoff = the SCORED claim)
  - Deflated Sharpe (n_trials from config, upper-bound) >= 0.90 / 0.95
  - block-bootstrap CI: P(Sharpe>0)==1.0 with positive lower CI
  - split-half same-sign (pre/post split_date)
  - leave-one-crisis-out (drop each crisis window, re-measure the DD/Sharpe edge)
  - beats the DUMB baseline (200dma long/flat, buy&hold)
  - honest-N: count INDEPENDENT crises, not raw rows
  - direction = coin-flip (Brier) — reported as the NON-claim

PROVENANCE NOTE (W1 N7 decontamination):
  The SCORED re-run grades the RAW series (`alloc_optimal_raw` from compute_all —
  pure engine without any override contamination).  The gated series (`alloc_optimal`)
  is printed as a labeled COMPARISON line only, never the headline.  This matters
  because compute_all() now emits dual columns via engine/btc_overrides.apply():
    alloc_optimal      = final (midterm-blackout applied — 0% through 2026)
    alloc_optimal_raw  = pure engine output (what the signals actually want)
  Grading the gated series would certify a strategy that is 0% for 10+ months of
  the backtest window due to a human override, not signal quality.

Prints results + writes reports/btc-vector-optimal-phase0.md.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import btc_signals
from engine.validation import (
    backtest_core, deflated_sharpe, dsr_verdict, ret_moments,
    block_bootstrap_ci, _maxdd, _sharpe,
)
from lib import config

TRADING_YEAR = 365  # BTC trades every day
ANN = np.sqrt(TRADING_YEAR)


def sharpe_ann(r: pd.Series) -> float:
    r = r.dropna()
    sd = r.std()
    return float(r.mean() / sd * ANN) if sd else float("nan")


def cagr(eq: pd.Series, years: float) -> float:
    return float(eq.iloc[-1] ** (1 / years) - 1) if years > 0 and eq.iloc[-1] > 0 else float("nan")


def maxdd_eq(eq: pd.Series) -> float:
    return float((eq / eq.cummax() - 1).min())


def summarize(close: pd.Series, alloc: pd.Series, cost_bps: float) -> dict:
    bt = backtest_core(close, alloc, cost_bps=cost_bps)
    strat, ret, gross, turnover, years = bt["net"], bt["ret"], bt["gross"], bt["turnover"], bt["years"]
    eq, hodl = (1 + strat).cumprod(), (1 + ret).cumprod()
    pos = bt["pos"]
    mom = ret_moments(strat)
    return {
        "sharpe": sharpe_ann(strat), "hodl_sharpe": sharpe_ann(ret),
        "maxdd": maxdd_eq(eq), "hodl_maxdd": maxdd_eq(hodl),
        "cagr": cagr(eq, years), "hodl_cagr": cagr(hodl, years),
        "time_in_market": float((pos > 0).mean()),
        "turnover_annual": float(turnover.sum() / years) if years else np.nan,
        "final_vs_hodl": float(eq.iloc[-1] / hodl.iloc[-1]),
        "net": strat, "ret": ret, "eq": eq, "hodl": hodl, "pos": pos,
        "sharpe_daily": mom[0] if mom else None, "skew": mom[1] if mom else None,
        "kurt": mom[2] if mom else None, "n_obs": mom[3] if mom else None,
        "years": years,
    }


def dumb_200dma(close: pd.Series) -> pd.Series:
    """Long when close > 200dma, flat otherwise — the canonical dumb timing baseline."""
    return (close > close.rolling(200).mean()).astype(float)


def main() -> int:
    cfg = config.load()["vector"]["calibration"]
    start = cfg["start_date"]
    split = pd.Timestamp(cfg["split_date"])
    cost_bps = float(cfg.get("cost_bps", 10.0))
    n_trials = int(cfg.get("n_trials", 50))

    print("=" * 78)
    print("TRACK-A VERIFY — BTC Vector `optimal` allocation (re-run LIVE engine)")
    print(f"  start={start}  split={split.date()}  cost={cost_bps}bps  n_trials(config)={n_trials}")
    print("=" * 78)

    df = btc_signals.compute_all()
    df = df.loc[df.index >= pd.Timestamp(start)]
    close = df["close"].astype(float)

    # W1 N7 decontamination: SCORED run must use the RAW (ungated) series.
    # The gated series is printed as a labeled comparison — not the headline.
    if "alloc_optimal_raw" not in df.columns:
        raise RuntimeError(
            "alloc_optimal_raw column missing from compute_all() output. "
            "W0 must be merged before running this script. "
            "Check engine/btc_overrides.py::apply() is wired into compute_all()."
        )
    alloc = df["alloc_optimal_raw"].astype(float)          # SCORED headline: RAW
    alloc_gated = df["alloc_optimal"].astype(float)        # comparison only
    print(f"  engine rows in window: {len(df)}  ({df.index.min().date()} -> {df.index.max().date()})")
    print(f"  GRADING: alloc_optimal_raw (pure engine; W1 N7 decontamination)")

    # ---- gated comparison (labeled, not headline) ----------------------------
    gated_full = summarize(close, alloc_gated, cost_bps)
    print(f"\n[0] GATED COMPARISON (alloc_optimal — midterm blackout applied; NOT headline)")
    print(f"  Sharpe {gated_full['sharpe']:.3f}  MaxDD {gated_full['maxdd']*100:.1f}%  "
          f"CAGR {gated_full['cagr']*100:.1f}%  (gated 0% through 2026 midterm window)")

    # ---- 1. headline backtest (RAW series) -----------------------------------
    full = summarize(close, alloc, cost_bps)
    dd_cut = full["hodl_maxdd"] / full["maxdd"]  # how many x the DD is cut
    print("\n[1] HEADLINE — RAW/ungated (net of cost; this is the SCORED read)")
    print(f"  Sharpe   strat {full['sharpe']:.3f}  vs HODL {full['hodl_sharpe']:.3f}  "
          f"(prior spec ~1.41 vs ~1.03 — pre-gate figure retired 2026-07)")
    print(f"  MaxDD    strat {full['maxdd']*100:.1f}%  vs HODL {full['hodl_maxdd']*100:.1f}%  "
          f"(prior spec ~-42.8 vs -83.8;  >=2x cut? cut={dd_cut:.2f}x)")
    print(f"  CAGR     strat {full['cagr']*100:.1f}%  vs HODL {full['hodl_cagr']*100:.1f}%")
    print(f"  final/HODL {full['final_vs_hodl']:.2f}  time-in-mkt {full['time_in_market']*100:.1f}%  "
          f"turnover/yr {full['turnover_annual']:.1f}")

    # ---- 2. Deflated Sharpe (RAW series) ------------------------------------
    # cross-variant SR dispersion floor (same recipe calibrate_vector uses).
    # Use RAW variants to avoid gate contaminating the SR-variance estimate.
    full_cfg = config.load()
    overrides_cfg = full_cfg.get("vector", {}).get("overrides", []) or []
    n_trials_overrides = sum(int(o.get("dof_cost", 0)) for o in overrides_cfg)
    n_trials_total = n_trials + n_trials_overrides
    variants = full_cfg["vector"]["allocation"]["variants"]
    daily_srs = []
    for v in variants:
        col_r = f"alloc_{v}_raw"
        if col_r in df.columns:
            s = summarize(close, df[col_r].astype(float), cost_bps)
        else:
            s = summarize(close, df[f"alloc_{v}"].astype(float), cost_bps)
        if s["sharpe_daily"] is not None:
            daily_srs.append(s["sharpe_daily"])
    sr_var = float(np.var(daily_srs, ddof=1)) if len(daily_srs) > 1 else None
    dsr50 = deflated_sharpe(full["sharpe_daily"], full["skew"], full["kurt"],
                            full["n_obs"], 50, sr_variance=sr_var, trading_year=TRADING_YEAR)
    dsrN = deflated_sharpe(full["sharpe_daily"], full["skew"], full["kurt"],
                           full["n_obs"], n_trials_total, sr_variance=sr_var, trading_year=TRADING_YEAR)
    print("\n[2] DEFLATED SHARPE (multiple-testing haircut; RAW series)")
    print(f"  n_trials=50  DSR={dsr50['dsr']:.4f}  SR0_ann={dsr50['sr0_annual']:.2f}  -> {dsr_verdict(dsr50['dsr'])}")
    print(f"  n_trials={n_trials_total} (live cfg {n_trials} + override dof {n_trials_overrides})  "
          f"DSR={dsrN['dsr']:.4f}  SR0_ann={dsrN['sr0_annual']:.2f}  -> {dsr_verdict(dsrN['dsr'])}")
    print(f"  skew={dsrN['skew']}  kurt(Pearson)={dsrN['kurt']}  T={dsrN['T']}")

    # ---- 3. block-bootstrap CI ----------------------------------------------
    boot = block_bootstrap_ci(full["net"], block=21, B=5000, seed=7, ann=TRADING_YEAR)
    print("\n[3] BLOCK-BOOTSTRAP CI [21d blocks, 5000 resamples]")
    print(f"  Sharpe CI [2.5,50,97.5] = {boot['sharpe_ci']}")
    print(f"  MaxDD  CI%             = {boot['maxdd_ci_pct']}")
    print(f"  P(Sharpe>0) = {boot['sharpe_gt0_prob']}  (need 1.0, positive lower CI)")
    boot_lower_pos = boot["sharpe_ci"][0] > 0
    boot_p1 = boot["sharpe_gt0_prob"] >= 1.0

    # ---- 4. split-half same-sign --------------------------------------------
    print("\n[4] SPLIT-HALF (pre/post split, same-sign edge)")
    halves = {"pre": df.index < split, "post": df.index >= split}
    half_rows = {}
    for name, mask in halves.items():
        c, a = close[mask], alloc[mask]
        if len(c) < 100:
            print(f"  {name}: too short")
            continue
        s = summarize(c, a, cost_bps)
        edge_sh = s["sharpe"] - s["hodl_sharpe"]
        dd_better = s["maxdd"] - s["hodl_maxdd"]  # >0 = strat DD shallower than HODL
        half_rows[name] = (s, edge_sh, dd_better)
        print(f"  {name}: Sharpe {s['sharpe']:.2f} vs HODL {s['hodl_sharpe']:.2f} "
              f"(edge {edge_sh:+.2f}) | MaxDD {s['maxdd']*100:.1f}% vs {s['hodl_maxdd']*100:.1f}% "
              f"(DD better by {dd_better*100:+.1f}pp)")
    dd_samesign = (len(half_rows) == 2 and
                   all(v[2] > 0 for v in half_rows.values()))   # DD cut in BOTH halves
    sharpe_samesign = (len(half_rows) == 2 and
                       all(v[0]["sharpe"] > v[0]["hodl_sharpe"] for v in half_rows.values()))
    print(f"  -> DD-cut holds both halves: {dd_samesign}   Sharpe>HODL both halves: {sharpe_samesign}")

    # ---- 5. leave-one-crisis-out --------------------------------------------
    # The SCORED claim is drawdown avoidance, so the test is: does the DD/Sharpe
    # edge survive when we REMOVE each crash episode in turn? If removing one
    # crisis kills the edge, the result rides a single event (honest-N=1).
    crises = {
        "2018_bear":   ("2017-12-01", "2018-12-31"),
        "2020_covid":  ("2020-02-01", "2020-04-30"),
        "2021_may":    ("2021-04-01", "2021-07-31"),
        "2022_bear":   ("2021-11-01", "2022-12-31"),   # LUNA/3AC/FTX cascade
        "2024_25_chop":("2024-03-01", "2025-12-31"),
    }
    print("\n[5] LEAVE-ONE-CRISIS-OUT (drop each window, re-measure edge)")
    loo = {}
    for name, (s0, s1) in crises.items():
        keep = ~((df.index >= pd.Timestamp(s0)) & (df.index <= pd.Timestamp(s1)))
        c, a = close[keep], alloc[keep]
        s = summarize(c, a, cost_bps)
        edge = s["sharpe"] - s["hodl_sharpe"]
        ddb = s["maxdd"] - s["hodl_maxdd"]
        loo[name] = (s["sharpe"], s["hodl_sharpe"], edge, s["maxdd"], s["hodl_maxdd"], ddb)
        print(f"  drop {name:13s}: Sharpe {s['sharpe']:.2f} vs {s['hodl_sharpe']:.2f} (edge {edge:+.2f}) "
              f"| MaxDD {s['maxdd']*100:.1f}% vs {s['hodl_maxdd']*100:.1f}% (better {ddb*100:+.1f}pp)")
    loo_dd_holds = all(v[5] > 0 for v in loo.values())
    loo_sharpe_holds = all(v[2] > 0 for v in loo.values())
    print(f"  -> DD edge survives dropping ANY single crisis: {loo_dd_holds}   "
          f"Sharpe edge survives: {loo_sharpe_holds}")

    # ---- 6. beats DUMB baselines --------------------------------------------
    print("\n[6] vs DUMB BASELINES (net of cost)")
    dumb = dumb_200dma(close)
    d = summarize(close, dumb, cost_bps)
    print(f"  200dma long/flat : Sharpe {d['sharpe']:.2f}  MaxDD {d['maxdd']*100:.1f}%  CAGR {d['cagr']*100:.1f}%")
    print(f"  buy&hold (HODL)  : Sharpe {full['hodl_sharpe']:.2f}  MaxDD {full['hodl_maxdd']*100:.1f}%  CAGR {full['hodl_cagr']*100:.1f}%")
    print(f"  optimal          : Sharpe {full['sharpe']:.2f}  MaxDD {full['maxdd']*100:.1f}%  CAGR {full['cagr']*100:.1f}%")
    beats_dumb_sharpe = full["sharpe"] > d["sharpe"]
    beats_dumb_dd = full["maxdd"] > d["maxdd"]      # shallower DD
    beats_hodl_sharpe = full["sharpe"] > full["hodl_sharpe"]
    print(f"  -> optimal Sharpe>200dma:{beats_dumb_sharpe}  DD shallower than 200dma:{beats_dumb_dd}  "
          f"Sharpe>HODL:{beats_hodl_sharpe}")

    # ---- 7. honest-N --------------------------------------------------------
    # The payoff is concentrated in DD-avoidance during a handful of de-risk episodes.
    # Count independent macro drawdown clusters BTC actually had since 2015.
    n_crises = len(crises)
    print("\n[7] HONEST-N")
    print(f"  raw rows: {full['n_obs']}  | INDEPENDENT crash/de-risk episodes since 2015: ~{n_crises}")
    print("  The Sharpe/DSR are computed on daily rows but the DD payoff is driven by")
    print(f"  ~{n_crises} independent bear/cascade events — that is the effective sample for the CLAIM.")

    # ---- 8. direction is a coin-flip (the NON-claim) ------------------------
    # 7d forward direction conditioned on being long today vs flat
    fwd7 = close.shift(-7) / close - 1.0
    long_days = full["pos"] > 0.5
    p_up_long = float((fwd7[long_days] > 0).mean())
    base_up = float((fwd7 > 0).mean())
    print("\n[8] DIRECTION (the NON-claim — do NOT score)")
    print(f"  P(7d up | long)={p_up_long:.3f}  vs base P(up)={base_up:.3f}  "
          f"(edge {100*(p_up_long-base_up):+.1f}pp — coin-flip, per spec Brier ~0.25)")

    # ---- VERDICT ------------------------------------------------------------
    gate = {
        "DSR>=0.90 (n=50)":     dsr50["dsr"] >= 0.90,
        "DSR>=0.95 survives":   dsr50["dsr"] >= 0.95,
        "DD cut >=2x":          dd_cut >= 2.0,
        "Sharpe>HODL":          beats_hodl_sharpe,
        "boot P(Sh>0)==1":      boot_p1,
        "boot lower CI>0":      boot_lower_pos,
        "split-half DD same-sign": dd_samesign,
        "LOO DD edge holds":    loo_dd_holds,
        "beats 200dma (Sharpe or DD)": beats_dumb_sharpe or beats_dumb_dd,
    }
    print("\n" + "=" * 78)
    print("GATE SUMMARY")
    for k, v in gate.items():
        print(f"  [{'PASS' if v else 'FAIL'}] {k}")
    scored_core = (gate["DSR>=0.90 (n=50)"] and gate["DD cut >=2x"] and
                   gate["boot P(Sh>0)==1"] and gate["boot lower CI>0"] and
                   gate["split-half DD same-sign"] and gate["LOO DD edge holds"] and
                   gate["beats 200dma (Sharpe or DD)"])
    print(f"\n  SCORED (drawdown/Sharpe payoff) clears: {scored_core}")
    print("=" * 78)

    # ---- write report -------------------------------------------------------
    lines = []
    lines.append("# BTC Vector `optimal` — Track-A SCORED verification (phase-0)\n")
    lines.append(
        f"**W1 N7 decontamination**: grading `alloc_optimal_raw` (pure engine) as the headline. "
        f"Pre-gate figures (0.9965 DSR, Sharpe 1.44) were computed before the midterm-blackout "
        f"override was wired into compute_all — they certified a strategy that no longer exists. "
        f"Fresh dual-track compute as of 2026-07. `alloc_optimal` (gated) shown as comparison only.\n"
    )
    lines.append(f"Re-ran the LIVE engine (`engine/btc_signals.compute_all` → `alloc_optimal_raw`) over "
                 f"{df.index.min().date()}..{df.index.max().date()}, net of {cost_bps}bps one-way. "
                 f"NO rebuild — same code path build_vector ships.\n")
    lines.append("## Gated comparison (alloc_optimal — midterm blackout active)\n")
    lines.append("| | gated strat | HODL |")
    lines.append("|---|--:|--:|")
    lines.append(f"| Sharpe | {gated_full['sharpe']:.2f} | {gated_full['hodl_sharpe']:.2f} |")
    lines.append(f"| MaxDD | {gated_full['maxdd']*100:.1f}% | {gated_full['hodl_maxdd']*100:.1f}% |")
    lines.append(f"| CAGR | {gated_full['cagr']*100:.1f}% | {gated_full['hodl_cagr']*100:.1f}% |")
    lines.append(f"\n*Gated is 0% through the 2026 midterm-blackout window by human override, not signal.*\n")
    lines.append("## Headline — RAW (ungated, SCORED)\n")
    lines.append("| | RAW strat | HODL | prior spec (retired) |")
    lines.append("|---|--:|--:|---|")
    lines.append(f"| Sharpe | {full['sharpe']:.2f} | {full['hodl_sharpe']:.2f} | ~1.41 vs ~1.03 |")
    lines.append(f"| MaxDD | {full['maxdd']*100:.1f}% | {full['hodl_maxdd']*100:.1f}% | ~-42.8 vs -83.8 |")
    lines.append(f"| CAGR | {full['cagr']*100:.1f}% | {full['hodl_cagr']*100:.1f}% | |")
    lines.append(f"| DD cut | {dd_cut:.2f}x | | >=2x |")
    lines.append(f"| final/HODL | {full['final_vs_hodl']:.2f} | | |\n")
    lines.append("## Gates\n")
    lines.append(f"- **DSR (RAW)** n=50: **{dsr50['dsr']:.4f}** ({dsr_verdict(dsr50['dsr'])}); "
                 f"n={n_trials_total} (live cfg {n_trials} + override dof {n_trials_overrides}): "
                 f"{dsrN['dsr']:.4f}. SR0_ann={dsr50['sr0_annual']:.2f}, "
                 f"skew={dsr50['skew']}, kurt={dsr50['kurt']}, T={dsr50['T']}.")
    lines.append(f"- **Block-bootstrap**: Sharpe CI {boot['sharpe_ci']}, MaxDD CI% {boot['maxdd_ci_pct']}, "
                 f"P(Sharpe>0)={boot['sharpe_gt0_prob']} (lower CI>0: {boot_lower_pos}).")
    lines.append(f"- **Split-half**: DD-cut both halves={dd_samesign}, Sharpe>HODL both halves={sharpe_samesign}.")
    for name, (s, e, ddb) in half_rows.items():
        lines.append(f"    - {name}: Sharpe {s['sharpe']:.2f} vs {s['hodl_sharpe']:.2f}; "
                     f"MaxDD {s['maxdd']*100:.1f}% vs {s['hodl_maxdd']*100:.1f}% ({ddb*100:+.1f}pp).")
    lines.append(f"- **Leave-one-crisis-out**: DD edge survives any drop={loo_dd_holds}, Sharpe edge={loo_sharpe_holds}.")
    for name, v in loo.items():
        lines.append(f"    - drop {name}: Sharpe {v[0]:.2f} vs {v[1]:.2f}; MaxDD {v[3]*100:.1f}% vs {v[4]*100:.1f}% ({v[5]*100:+.1f}pp).")
    lines.append(f"- **Dumb baselines**: 200dma Sharpe {d['sharpe']:.2f}/MaxDD {d['maxdd']*100:.1f}%; "
                 f"optimal beats-200dma(Sharpe)={beats_dumb_sharpe}, DD-shallower={beats_dumb_dd}.")
    lines.append(f"- **Honest-N**: ~{n_crises} independent crash/de-risk episodes drive the DD payoff "
                 f"(daily rows={full['n_obs']} overstate the effective N for the claim).")
    lines.append(f"- **Direction (NON-claim)**: P(7d up|long)={p_up_long:.3f} vs base {base_up:.3f} — coin-flip.\n")
    lines.append("## Verdict\n")
    lines.append(f"SCORED core gates pass (RAW series): **{scored_core}**. "
                 "The SCORED claim is the drawdown/Sharpe payoff ONLY; direction is a coin-flip and not claimed. "
                 "Pre-gate figures (DSR 0.9965, Sharpe 1.44) retired 2026-07; fresh dual-track as of this run.")
    with open("reports/btc-vector-optimal-phase0.md", "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\nwrote reports/btc-vector-optimal-phase0.md")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
