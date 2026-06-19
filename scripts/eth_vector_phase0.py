"""TRACK-A verification of an ETH Vector `optimal` allocation — port of the BTC
Vector `optimal` (signal_lab SCORED claim, DSR 0.9965) to ETH.

READ-ONLY research. There is NO live ETH engine, so this REUSES the BTC engine's
pure signal builders (engine.btc_signals.momentum / risk / allocation) fed ETH
price only — the on-chain votes (SOPR, ETF flow, funding) are simply absent, so
the momentum ensemble collapses to its PRICE subset (ema_trend/ema_cross/macd/
sma200/roc20/rsi_zone) and the Risk Index to its PRICE subset (downside-vol
percentile + drawdown-from-trailing-high + momentum_deterioration) — exactly the
"BTC risk_idx ingredients available without on-chain" the spec names. As a faithful
mirror of BTC's `use_valuation_overlay`, ETH MVRV (coinmetrics, cached to
data/yahoo/_eth_mvrv_phase0.parquet) drives the deep-value/overvalued grid override.

The SCORED grid is the SAME `optimal` variant config (mom_full 0.5 / risk_full 25 /
mom_half 0.0 / risk_half 50) with the SAME confirm_days / conviction sizing /
drawdown brake the live BTC engine ships. Backtest is net 10bps one-way vs ETH HODL.

Computes EVERY gate the SCORED tier requires (engine/validation.py primitives):
  - allocation backtest vs HODL (Sharpe / MaxDD payoff = the SCORED claim)
  - Deflated Sharpe (n_trials 50 + live-cfg) >= 0.90 / 0.95  (DD/Sharpe, NOT CAGR)
  - block-bootstrap CI: P(Sharpe>0) + positive lower CI
  - split-half same-sign (pre/post 2021)
  - leave-one-crisis-out (drop each ETH crash window, re-measure the edge)
  - beats a BRAKE-MATCHED 200dma long/flat on BOTH Sharpe AND MaxDD
  - DECOMPOSITION: does the raw (momentum,risk) grid ALONE beat HODL, i.e. the
    edge is NOT a pure brake artifact?
  - honest-N: count INDEPENDENT ETH crises (~2-3 cycles), not raw rows
  - direction = coin-flip (Brier) — reported as the NON-claim

Prints results + writes reports/eth-vector-phase0.md.
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

TRADING_YEAR = 365  # crypto trades every day
ANN = np.sqrt(TRADING_YEAR)
START = "2015-01-01"          # mirror BTC calibration start; ETH data begins 2017-11
SPLIT = pd.Timestamp("2021-01-01")
COST_BPS = 10.0


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
    strat, ret, turnover, years = bt["net"], bt["ret"], bt["turnover"], bt["years"]
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
    return (close > close.rolling(200).mean()).astype(float)


def build_eth_signals():
    """Reuse the BTC pure signal builders on ETH price → momentum, price-only
    risk_index, and the OPTIMAL allocation grid (same config, same overlays)."""
    vc = config.load()["vector"]
    px = pd.read_parquet("data/yahoo/ETH-USD.parquet")[["close", "volume"]].copy()
    px = px[~px.index.duplicated(keep="last")].sort_index()
    px["close"] = px["close"].astype(float)
    # high/low absent in the yahoo store → momentum/risk only read close; structure
    # (which needs high/low) is NOT used by the allocation grid, so we skip it.
    inputs = {"price": px}

    mom_df = btc_signals.momentum(inputs, vc["momentum"])         # price-subset votes
    risk_df = btc_signals.risk(inputs, mom_df["momentum"], vc["risk"])  # price-subset risk

    # MVRV valuation overlay (mirror BTC use_valuation_overlay). The BTC engine reads
    # a precomputed mvrv_z; here we z-score ETH MVRV on the SAME 4y window the config
    # uses, all causal (rolling, no look-ahead).
    val = None
    try:
        mv = pd.read_parquet("data/yahoo/_eth_mvrv_phase0.parquet")["mvrv"]
        mv = mv.reindex(px.index).ffill(limit=5)
        vcfg = vc["valuation"]
        zw, zmp = vcfg["z_window_d"], vcfg["z_min_periods_d"]
        roll = mv.rolling(zw, min_periods=zmp)
        mvrv_z = (mv - roll.mean()) / roll.std()
        mayer = mv / mv.rolling(200, min_periods=100).mean()  # MVRV proxy for Mayer (price/200dma analogue)
        val = pd.DataFrame({"mvrv_z": mvrv_z, "mayer": mayer})
    except Exception as e:  # pragma: no cover
        print("  (MVRV overlay unavailable:", e, ") — running grid WITHOUT valuation overlay")

    acfg = dict(vc["allocation"])
    close = px["close"]
    alloc = btc_signals.allocation(mom_df["momentum"], risk_df["risk_index"], acfg,
                                   val=val, close=close)
    df = pd.concat([px, mom_df, risk_df, alloc], axis=1)
    df["alloc_optimal"] = df["alloc_optimal"]
    return df, vc, val


def main() -> int:
    n_trials_cfg = int(config.load()["vector"]["calibration"].get("n_trials", 65))

    print("=" * 80)
    print("TRACK-A VERIFY — ETH Vector `optimal` (port of BTC Vector optimal grid)")
    print(f"  start={START}  split={SPLIT.date()}  cost={COST_BPS}bps  "
          f"n_trials: 50 (BTC grid-size) + {n_trials_cfg} (live cfg)")
    print("=" * 80)

    df, vc, val = build_eth_signals()
    df = df.loc[df.index >= pd.Timestamp(START)]
    close = df["close"].astype(float)
    alloc = df["alloc_optimal"].astype(float)
    print(f"  ETH rows in window: {len(df)}  ({df.index.min().date()} -> {df.index.max().date()})")
    print(f"  MVRV valuation overlay active: {val is not None}")

    # ---- 1. headline backtest ------------------------------------------------
    full = summarize(close, alloc, COST_BPS)
    dd_cut = full["hodl_maxdd"] / full["maxdd"] if full["maxdd"] else float("nan")
    print("\n[1] HEADLINE (net of cost)")
    print(f"  Sharpe   strat {full['sharpe']:.3f}  vs HODL {full['hodl_sharpe']:.3f}")
    print(f"  MaxDD    strat {full['maxdd']*100:.1f}%  vs HODL {full['hodl_maxdd']*100:.1f}%  "
          f"(DD cut={dd_cut:.2f}x)")
    print(f"  CAGR     strat {full['cagr']*100:.1f}%  vs HODL {full['hodl_cagr']*100:.1f}%")
    print(f"  final/HODL {full['final_vs_hodl']:.2f}  time-in-mkt {full['time_in_market']*100:.1f}%  "
          f"turnover/yr {full['turnover_annual']:.1f}")

    # ---- 2. Deflated Sharpe (DD/Sharpe payoff) -------------------------------
    variants = vc["allocation"]["variants"]
    daily_srs = []
    for v in variants:
        if f"alloc_{v}" in df:
            s = summarize(close, df[f"alloc_{v}"].astype(float), COST_BPS)
            if s["sharpe_daily"] is not None:
                daily_srs.append(s["sharpe_daily"])
    sr_var = float(np.var(daily_srs, ddof=1)) if len(daily_srs) > 1 else None
    dsr50 = deflated_sharpe(full["sharpe_daily"], full["skew"], full["kurt"],
                            full["n_obs"], 50, sr_variance=sr_var, trading_year=TRADING_YEAR)
    dsrN = deflated_sharpe(full["sharpe_daily"], full["skew"], full["kurt"],
                           full["n_obs"], n_trials_cfg, sr_variance=sr_var, trading_year=TRADING_YEAR)
    print("\n[2] DEFLATED SHARPE (multiple-testing haircut; DD/Sharpe payoff)")
    print(f"  n_trials=50  DSR={dsr50['dsr']:.4f}  SR0_ann={dsr50['sr0_annual']:.2f}  -> {dsr_verdict(dsr50['dsr'])}")
    print(f"  n_trials={n_trials_cfg} (live cfg)  DSR={dsrN['dsr']:.4f}  SR0_ann={dsrN['sr0_annual']:.2f}  -> {dsr_verdict(dsrN['dsr'])}")
    print(f"  skew={dsrN['skew']}  kurt(Pearson)={dsrN['kurt']}  T={dsrN['T']}")

    # ---- 3. block-bootstrap CI ----------------------------------------------
    boot = block_bootstrap_ci(full["net"], block=21, B=5000, seed=7, ann=TRADING_YEAR)
    print("\n[3] BLOCK-BOOTSTRAP CI [21d blocks, 5000 resamples]")
    print(f"  Sharpe CI [2.5,50,97.5] = {boot['sharpe_ci']}")
    print(f"  MaxDD  CI%             = {boot['maxdd_ci_pct']}")
    print(f"  P(Sharpe>0) = {boot['sharpe_gt0_prob']}  (need 1.0, positive lower CI)")
    boot_lower_pos = boot["sharpe_ci"][0] > 0
    boot_p1 = boot["sharpe_gt0_prob"] >= 1.0

    # ---- 4. split-half same-sign (pre/post 2021) ----------------------------
    print("\n[4] SPLIT-HALF (pre/post 2021, same-sign edge)")
    halves = {"pre2021": df.index < SPLIT, "post2021": df.index >= SPLIT}
    half_rows = {}
    for name, mask in halves.items():
        c, a = close[mask], alloc[mask]
        if len(c) < 100:
            print(f"  {name}: too short ({len(c)} rows)")
            continue
        s = summarize(c, a, COST_BPS)
        edge_sh = s["sharpe"] - s["hodl_sharpe"]
        dd_better = s["maxdd"] - s["hodl_maxdd"]  # >0 = strat DD shallower than HODL
        half_rows[name] = (s, edge_sh, dd_better)
        print(f"  {name}: Sharpe {s['sharpe']:.2f} vs HODL {s['hodl_sharpe']:.2f} "
              f"(edge {edge_sh:+.2f}) | MaxDD {s['maxdd']*100:.1f}% vs {s['hodl_maxdd']*100:.1f}% "
              f"(DD better by {dd_better*100:+.1f}pp)")
    dd_samesign = (len(half_rows) == 2 and all(v[2] > 0 for v in half_rows.values()))
    sharpe_samesign = (len(half_rows) == 2 and
                       all(v[0]["sharpe"] > v[0]["hodl_sharpe"] for v in half_rows.values()))
    print(f"  -> DD-cut holds both halves: {dd_samesign}   Sharpe>HODL both halves: {sharpe_samesign}")

    # ---- 5. leave-one-crisis-out --------------------------------------------
    # ETH price begins 2017-11, so its independent crash clusters are fewer than BTC.
    crises = {
        "2018_bear":    ("2018-01-01", "2018-12-31"),   # ICO blow-off → -94% bear
        "2020_covid":   ("2020-02-01", "2020-04-30"),
        "2021_may":     ("2021-05-01", "2021-07-31"),   # mid-cycle crash
        "2022_bear":    ("2021-11-01", "2022-12-31"),   # LUNA/3AC/FTX cascade
        "2024_25_chop": ("2024-03-01", "2025-12-31"),
    }
    print("\n[5] LEAVE-ONE-CRISIS-OUT (drop each window, re-measure edge)")
    loo = {}
    for name, (s0, s1) in crises.items():
        keep = ~((df.index >= pd.Timestamp(s0)) & (df.index <= pd.Timestamp(s1)))
        c, a = close[keep], alloc[keep]
        if len(c) < 100:
            continue
        s = summarize(c, a, COST_BPS)
        edge = s["sharpe"] - s["hodl_sharpe"]
        ddb = s["maxdd"] - s["hodl_maxdd"]
        loo[name] = (s["sharpe"], s["hodl_sharpe"], edge, s["maxdd"], s["hodl_maxdd"], ddb)
        print(f"  drop {name:13s}: Sharpe {s['sharpe']:.2f} vs {s['hodl_sharpe']:.2f} (edge {edge:+.2f}) "
              f"| MaxDD {s['maxdd']*100:.1f}% vs {s['hodl_maxdd']*100:.1f}% (better {ddb*100:+.1f}pp)")
    loo_dd_holds = bool(loo) and all(v[5] > 0 for v in loo.values())
    loo_sharpe_holds = bool(loo) and all(v[2] > 0 for v in loo.values())
    print(f"  -> DD edge survives dropping ANY single crisis: {loo_dd_holds}   "
          f"Sharpe edge survives: {loo_sharpe_holds}")

    # ---- 6. beats DUMB baselines (incl BRAKE-MATCHED 200dma) -----------------
    print("\n[6] vs DUMB BASELINES (net of cost)")
    dumb_raw = dumb_200dma(close)
    d = summarize(close, dumb_raw, COST_BPS)
    # brake-matched 200dma: apply the SAME drawdown brake + conviction-style core to
    # the 200dma long/flat so the comparison isolates the GRID signal, not the brake.
    acfg = vc["allocation"]
    ret = close.pct_change()
    dumb_braked = btc_signals.drawdown_brake(dumb_raw, ret, acfg).clip(0, 1)
    db = summarize(close, dumb_braked, COST_BPS)
    print(f"  200dma raw       : Sharpe {d['sharpe']:.2f}  MaxDD {d['maxdd']*100:.1f}%  CAGR {d['cagr']*100:.1f}%")
    print(f"  200dma+brake     : Sharpe {db['sharpe']:.2f}  MaxDD {db['maxdd']*100:.1f}%  CAGR {db['cagr']*100:.1f}%")
    print(f"  buy&hold (HODL)  : Sharpe {full['hodl_sharpe']:.2f}  MaxDD {full['hodl_maxdd']*100:.1f}%  CAGR {full['hodl_cagr']*100:.1f}%")
    print(f"  optimal          : Sharpe {full['sharpe']:.2f}  MaxDD {full['maxdd']*100:.1f}%  CAGR {full['cagr']*100:.1f}%")
    beats_bm_sharpe = full["sharpe"] > db["sharpe"]
    beats_bm_dd = full["maxdd"] > db["maxdd"]      # shallower DD (less negative)
    beats_hodl_sharpe = full["sharpe"] > full["hodl_sharpe"]
    print(f"  -> optimal beats BRAKE-MATCHED 200dma on Sharpe:{beats_bm_sharpe}  AND on DD:{beats_bm_dd}  "
          f"| Sharpe>HODL:{beats_hodl_sharpe}")

    # ---- 7. DECOMPOSITION — raw grid ALONE vs HODL (brake-artifact check) ----
    # Strip conviction sizing AND the drawdown brake: does the bare (momentum,risk)
    # grid + valuation overlay beat HODL? If only the braked version wins, the edge
    # is a generic stop-loss, not the signal.
    acfg_raw = dict(acfg)
    acfg_raw["conviction_sizing"] = False
    acfg_raw["drawdown_brake"] = False
    raw_alloc = btc_signals.allocation(df["momentum"], df["risk_index"], acfg_raw,
                                       val=val, close=None)["alloc_optimal"].reindex(df.index)
    rg = summarize(close, raw_alloc.astype(float), COST_BPS)
    print("\n[7] DECOMPOSITION (raw grid, NO conviction sizing, NO brake)")
    print(f"  raw grid : Sharpe {rg['sharpe']:.2f} vs HODL {rg['hodl_sharpe']:.2f}  "
          f"| MaxDD {rg['maxdd']*100:.1f}% vs {rg['hodl_maxdd']*100:.1f}%  | CAGR {rg['cagr']*100:.1f}%")
    raw_grid_beats_hodl_sharpe = rg["sharpe"] > rg["hodl_sharpe"]
    raw_grid_cuts_dd = rg["maxdd"] > rg["hodl_maxdd"]
    print(f"  -> raw grid Sharpe>HODL:{raw_grid_beats_hodl_sharpe}  DD shallower than HODL:{raw_grid_cuts_dd}  "
          f"(edge is NOT a pure brake artifact: {raw_grid_beats_hodl_sharpe and raw_grid_cuts_dd})")

    # ---- 8. honest-N --------------------------------------------------------
    # ETH price history begins 2017-11 → only ~2-3 independent bear cycles.
    indep_crises = ["2018_bear", "2021-22_bear/cascade", "2024-25_chop"]
    print("\n[8] HONEST-N")
    print(f"  raw rows: {full['n_obs']}  | INDEPENDENT crash/de-risk cycles since ETH 2017-11: ~{len(indep_crises)}")
    print(f"  ({', '.join(indep_crises)}) — that is the effective N for the DD CLAIM, NOT the daily rows.")
    print("  ETH MISSES the 2018 BTC-cycle top entry that BTC's 2015 start captured; ~2-3 cycles is borderline.")

    # ---- 9. direction is a coin-flip (the NON-claim) ------------------------
    fwd7 = close.shift(-7) / close - 1.0
    long_days = full["pos"] > 0.5
    p_up_long = float((fwd7[long_days] > 0).mean())
    base_up = float((fwd7 > 0).mean())
    print("\n[9] DIRECTION (the NON-claim — do NOT score)")
    print(f"  P(7d up | long)={p_up_long:.3f}  vs base P(up)={base_up:.3f}  "
          f"(edge {100*(p_up_long-base_up):+.1f}pp — direction is a coin-flip, never claimed)")

    # ---- VERDICT ------------------------------------------------------------
    gate = {
        "DSR>=0.90 (n=50)":             dsr50["dsr"] >= 0.90,
        "DSR>=0.95 survives (n=50)":    dsr50["dsr"] >= 0.95,
        "DD cut >=2x":                  (dd_cut >= 2.0) if np.isfinite(dd_cut) else False,
        "Sharpe>HODL":                  beats_hodl_sharpe,
        "boot P(Sh>0)==1":              boot_p1,
        "boot lower CI>0":              boot_lower_pos,
        "split-half DD same-sign":      dd_samesign,
        "split-half Sharpe same-sign":  sharpe_samesign,
        "LOO DD edge holds":            loo_dd_holds,
        "beats brake-matched 200dma (BOTH Sharpe&DD)": beats_bm_sharpe and beats_bm_dd,
        "raw-grid edge (NOT brake artifact)":          raw_grid_beats_hodl_sharpe and raw_grid_cuts_dd,
    }
    print("\n" + "=" * 80)
    print("GATE SUMMARY")
    for k, v in gate.items():
        print(f"  [{'PASS' if v else 'FAIL'}] {k}")
    scored_core = (gate["DSR>=0.90 (n=50)"] and gate["DD cut >=2x"] and
                   gate["boot P(Sh>0)==1"] and gate["boot lower CI>0"] and
                   gate["split-half DD same-sign"] and gate["LOO DD edge holds"] and
                   gate["beats brake-matched 200dma (BOTH Sharpe&DD)"] and
                   gate["raw-grid edge (NOT brake artifact)"])
    print(f"\n  SCORED (drawdown/Sharpe payoff) clears: {scored_core}")
    print("=" * 80)

    # ---- write report -------------------------------------------------------
    L = []
    L.append("# ETH Vector `optimal` — Track-A SCORED verification (phase-0)\n")
    L.append(f"Port of the BTC Vector `optimal` grid to ETH. REUSES the BTC pure signal "
             f"builders (`engine.btc_signals.momentum/risk/allocation`) fed ETH price only — "
             f"on-chain votes absent → momentum collapses to its PRICE subset, Risk Index to "
             f"downside-vol-pctile + drawdown-from-high + momentum-deterioration (the BTC "
             f"`risk_idx` ingredients available without on-chain). MVRV overlay active: "
             f"**{val is not None}** (coinmetrics ETH MVRV, z-scored on the same 4y window).\n")
    L.append(f"Window {df.index.min().date()}..{df.index.max().date()} ({len(df)} rows, "
             f"~{full['years']:.1f}y), net {COST_BPS}bps one-way, same `optimal` grid + "
             f"confirm_days + conviction sizing + drawdown brake as the live BTC engine.\n")
    L.append("## Headline\n")
    L.append("| | ETH-strat | ETH-HODL |")
    L.append("|---|--:|--:|")
    L.append(f"| Sharpe | {full['sharpe']:.2f} | {full['hodl_sharpe']:.2f} |")
    L.append(f"| MaxDD | {full['maxdd']*100:.1f}% | {full['hodl_maxdd']*100:.1f}% |")
    L.append(f"| CAGR | {full['cagr']*100:.1f}% | {full['hodl_cagr']*100:.1f}% |")
    L.append(f"| DD cut | {dd_cut:.2f}x | (>=2x bar) |")
    L.append(f"| final/HODL | {full['final_vs_hodl']:.2f} | |")
    L.append(f"| time-in-mkt | {full['time_in_market']*100:.0f}% | |\n")
    L.append("## Gates\n")
    L.append(f"- **DSR** (DD/Sharpe payoff) n=50: **{dsr50['dsr']:.4f}** ({dsr_verdict(dsr50['dsr'])}); "
             f"n={n_trials_cfg} live cfg: {dsrN['dsr']:.4f}. SR0_ann={dsr50['sr0_annual']:.2f}, "
             f"skew={dsr50['skew']}, kurt={dsr50['kurt']}, T={dsr50['T']}.")
    L.append(f"- **Block-bootstrap**: Sharpe CI {boot['sharpe_ci']}, MaxDD CI% {boot['maxdd_ci_pct']}, "
             f"P(Sharpe>0)={boot['sharpe_gt0_prob']} (lower CI>0: {boot_lower_pos}).")
    L.append(f"- **Split-half (pre/post 2021)**: DD-cut both halves={dd_samesign}, "
             f"Sharpe>HODL both halves={sharpe_samesign}.")
    for name, (s, e, ddb) in half_rows.items():
        L.append(f"    - {name}: Sharpe {s['sharpe']:.2f} vs {s['hodl_sharpe']:.2f}; "
                 f"MaxDD {s['maxdd']*100:.1f}% vs {s['hodl_maxdd']*100:.1f}% ({ddb*100:+.1f}pp).")
    L.append(f"- **Leave-one-crisis-out**: DD edge survives any drop={loo_dd_holds}, "
             f"Sharpe edge={loo_sharpe_holds}.")
    for name, v in loo.items():
        L.append(f"    - drop {name}: Sharpe {v[0]:.2f} vs {v[1]:.2f}; "
                 f"MaxDD {v[3]*100:.1f}% vs {v[4]*100:.1f}% ({v[5]*100:+.1f}pp).")
    L.append(f"- **Brake-matched 200dma**: 200dma+brake Sharpe {db['sharpe']:.2f}/MaxDD {db['maxdd']*100:.1f}%; "
             f"optimal beats it on Sharpe={beats_bm_sharpe} AND on DD={beats_bm_dd}.")
    L.append(f"- **Decomposition (raw grid, no conviction/brake)**: Sharpe {rg['sharpe']:.2f} vs HODL "
             f"{rg['hodl_sharpe']:.2f}, MaxDD {rg['maxdd']*100:.1f}% vs {rg['hodl_maxdd']*100:.1f}% — "
             f"grid edge is NOT a pure brake artifact: {raw_grid_beats_hodl_sharpe and raw_grid_cuts_dd}.")
    L.append(f"- **Honest-N**: only ~{len(indep_crises)} independent ETH bear cycles since 2017-11 "
             f"({', '.join(indep_crises)}); daily rows={full['n_obs']} overstate the effective N. "
             f"ETH misses the pre-2018 cycle BTC's 2015 start captured → BORDERLINE.")
    L.append(f"- **Direction (NON-claim)**: P(7d up|long)={p_up_long:.3f} vs base {base_up:.3f} — coin-flip.\n")
    L.append("## Verdict\n")
    L.append(f"SCORED core gates pass: **{scored_core}**. "
             "The SCORED claim is the drawdown/Sharpe payoff ONLY; direction is a coin-flip and never claimed.")
    with open("reports/eth-vector-phase0.md", "w") as f:
        f.write("\n".join(L) + "\n")
    print("\nwrote reports/eth-vector-phase0.md")

    # stash the headline gate dict for the caller
    main.result = {  # type: ignore[attr-defined]
        "scored_core": scored_core, "gate": gate, "dsr50": dsr50["dsr"],
        "sharpe": full["sharpe"], "hodl_sharpe": full["hodl_sharpe"],
        "maxdd": full["maxdd"], "hodl_maxdd": full["hodl_maxdd"], "dd_cut": dd_cut,
    }
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
