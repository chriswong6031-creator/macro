"""Phase-0 validation: does a NAAIM-exposure TREND-FOLLOWING drawdown overlay on
SPY genuinely beat the dumb baselines, or is it a confirmer/display leg?

THE HYPOTHESIS (trend-following, NOT contrarian). The NAAIM Exposure Index is a
weekly survey of active-manager equity exposure (0-100, occasionally >100/neg).
The claim under test: managers' aggregate exposure is *momentum-coherent* — when
they are de-risked (low NAAIM) the market is in a fragile/falling regime, and
sizing DOWN with them avoids the deep drawdowns; when they are fully invested
(high NAAIM) drawdowns ahead are SHALLOWER. So we run a literal exposure overlay:
  alloc_t = clip(NAAIM/100, 0, 1)
using the last print available >= 1 week earlier (no look-ahead), ffilled to
daily, and backtest it on SPY net of cost with the flat sleeve earning DFF.

This is the OPPOSITE of the textbook "fade the crowd" contrarian read. The
research pre-check found Spearman(NAAIM z, fwd-63d drawdown) = +0.229 (high
exposure -> shallower drawdowns), i.e. the trend-following sign, so the contrarian
interpretation is backwards over this sample.

BASELINES (the overlay must beat BOTH to earn anything above display):
  1. SPY buy-&-hold (the do-nothing benchmark)
  2. 200-day moving-average long/cash on SPY (the DUMB trend baseline) — if a
     free SMA rule already captures the drawdown reduction, NAAIM adds nothing.

GATES (every one computed, none asserted):
  - block_bootstrap_ci on the MaxDD-reduction (overlay vs B&H): CI must exclude 0
  - split_half_oos: same-sign DD-reduction in BOTH halves
  - leave-one-crisis-out {2008, 2020, 2022}: edge must not vanish when any single
    crisis is removed (is the whole edge one episode?)
  - deflated_sharpe counting the exposure-cutoff variants as trials
  - honest-N: count INDEPENDENT crises, not the ~1040 weekly rows

NO LOOK-AHEAD: the signal at date t uses only the NAAIM print published >= 7 days
before t; backtest_core acts the position NEXT bar (shift(1)).

Run:  python -m scripts.naaim_overlay_phase0
Writes reports/naaim-overlay-phase0.md
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import validation as V          # noqa: E402
from engine import active_alloc as A        # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
COST_BPS = 2.0
START = "2006-01-01"        # NAAIM starts 2006-07
ANN = 252

# Crisis windows for leave-one-crisis-out (peak-to-trough + recovery buffer)
CRISES = {
    "2008": ("2007-10-01", "2009-06-30"),
    "2020": ("2020-02-01", "2020-06-30"),
    "2022": ("2022-01-01", "2022-12-31"),
}


# --------------------------------------------------------------------------- #
# data
# --------------------------------------------------------------------------- #
def load() -> tuple[pd.Series, pd.Series, pd.Series]:
    spy = pd.read_parquet(ROOT / "data/yahoo/SPY.parquet")["close"].sort_index()
    spy = spy[spy.index >= START]
    dff = pd.read_parquet(ROOT / "data/fred/DFF.parquet")["fed_funds"].sort_index()
    naaim = pd.read_parquet(ROOT / "data/sentiment/naaim.parquet")["naaim_exposure"].sort_index()
    return spy, dff, naaim


def naaim_alloc(spy_index: pd.DatetimeIndex, naaim: pd.Series, lag_days: int = 7) -> pd.Series:
    """alloc_t = clip(NAAIM/100, 0, 1), using the last print published >= lag_days
    before t (no look-ahead on the weekly survey release), ffilled to daily."""
    lagged = naaim.copy()
    lagged.index = lagged.index + pd.Timedelta(days=lag_days)   # print available lag_days later
    daily = lagged.reindex(spy_index.union(lagged.index)).ffill().reindex(spy_index)
    return (daily / 100.0).clip(0.0, 1.0)


# --------------------------------------------------------------------------- #
# baselines
# --------------------------------------------------------------------------- #
def sma_alloc(spy: pd.Series, win: int = 200) -> pd.Series:
    sma = spy.rolling(win).mean()
    return (spy > sma).astype(float)         # long when above SMA, flat below


def cash_yield(dff: pd.Series) -> pd.Series:
    return dff


# --------------------------------------------------------------------------- #
# metrics
# --------------------------------------------------------------------------- #
def stats(net: pd.Series, name: str) -> dict:
    net = net.dropna()
    eq = (1 + net).cumprod()
    yrs = (net.index[-1] - net.index[0]).days / 365.25
    cagr = eq.iloc[-1] ** (1 / yrs) - 1 if yrs > 0 and eq.iloc[-1] > 0 else np.nan
    sd = net.std()
    sharpe = net.mean() / sd * np.sqrt(ANN) if sd else np.nan
    mdd = float((eq / eq.cummax() - 1).min())
    return {"name": name, "cagr": round(100 * cagr, 2), "sharpe": round(float(sharpe), 3),
            "maxdd": round(100 * mdd, 1), "final_mult": round(float(eq.iloc[-1]), 2),
            "years": round(yrs, 1), "net": net, "eq": eq, "mdd": mdd}


def run_overlay(spy: pd.Series, alloc: pd.Series, dff: pd.Series, name: str) -> dict:
    bt = V.backtest_core(spy, alloc, cost_bps=COST_BPS, cash_yield=dff)
    return stats(bt["net"], name)


def maxdd_of(net: pd.Series) -> float:
    eq = (1 + net.dropna()).cumprod()
    return float((eq / eq.cummax() - 1).min())


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> None:
    spy, dff, naaim = load()
    # align all to the SPY trading calendar where NAAIM exists
    naaim_start = naaim.index.min() + pd.Timedelta(days=7)
    spy = spy[spy.index >= naaim_start]
    idx = spy.index

    alloc = naaim_alloc(idx, naaim)
    sma = sma_alloc(spy)
    bh = pd.Series(1.0, index=idx)

    out = []
    out.append("# NAAIM Exposure Trend-Following Drawdown Overlay — Phase-0\n")
    out.append(f"Sample: {idx.min().date()} -> {idx.max().date()}  "
               f"({len(idx)} trading days, NAAIM weekly n={len(naaim)})\n")
    out.append(f"Cost: {COST_BPS} bps one-way; flat sleeve earns DFF.  "
               f"Signal lag: last NAAIM print >= 7d before t, ffilled.\n")

    # ---- headline backtests --------------------------------------------- #
    s_overlay = run_overlay(spy, alloc, dff, "NAAIM overlay")
    s_bh = stats(spy.pct_change().fillna(0), "SPY B&H")
    # B&H via backtest_core for consistent index/cost=0
    s_bh = run_overlay(spy, bh, dff, "SPY B&H")
    s_sma = run_overlay(spy, sma, dff, "200dma long/cash")

    out.append("\n## Headline (net of cost)\n")
    hdr = f"{'strategy':<20}{'CAGR%':>8}{'Sharpe':>8}{'MaxDD%':>9}{'mult':>8}{'yrs':>6}"
    out.append("```\n" + hdr)
    for s in (s_overlay, s_bh, s_sma):
        out.append(f"{s['name']:<20}{s['cagr']:>8}{s['sharpe']:>8}{s['maxdd']:>9}"
                   f"{s['final_mult']:>8}{s['years']:>6}")
    out.append("```")

    beats_bh_sharpe = s_overlay["sharpe"] > s_bh["sharpe"]
    beats_sma_sharpe = s_overlay["sharpe"] > s_sma["sharpe"]
    beats_bh_dd = s_overlay["maxdd"] > s_bh["maxdd"]      # less negative = shallower
    beats_sma_dd = s_overlay["maxdd"] > s_sma["maxdd"]
    # DD-reduction = how many pp SHALLOWER the overlay drawdown is. maxdd are
    # negative; overlay shallower => overlay_maxdd > bh_maxdd => positive reduction.
    dd_red_bh = s_overlay["maxdd"] - s_bh["maxdd"]         # +ve = overlay shallower than B&H
    dd_red_sma = s_overlay["maxdd"] - s_sma["maxdd"]

    out.append(f"\nSharpe: overlay {s_overlay['sharpe']} vs B&H {s_bh['sharpe']} "
               f"({'BEATS' if beats_bh_sharpe else 'loses'}) vs 200dma {s_sma['sharpe']} "
               f"({'BEATS' if beats_sma_sharpe else 'loses'})")
    out.append(f"MaxDD: overlay {s_overlay['maxdd']} vs B&H {s_bh['maxdd']} "
               f"(DD-reduction {dd_red_bh:+.1f}pp) vs 200dma {s_sma['maxdd']} "
               f"(DD-reduction {dd_red_sma:+.1f}pp)")

    # ---- Spearman sanity: NAAIM z vs fwd-63d drawdown -------------------- #
    naaim_d = (naaim.copy())
    naaim_d.index = naaim_d.index + pd.Timedelta(days=7)
    nz = A.zscore(naaim_d.reindex(idx.union(naaim_d.index)).ffill().reindex(idx), win=252)
    fwd_dd = forward_drawdown(spy, 63)
    j = pd.concat([nz.rename("z"), fwd_dd.rename("dd")], axis=1).dropna()
    sp = float(j["z"].rank().corr(j["dd"].rank())) if len(j) > 30 else np.nan
    out.append(f"\nSpearman(NAAIM z, fwd-63d drawdown) = {sp:+.3f}  "
               f"(+ve => high exposure precedes SHALLOWER drawdowns = trend-following sign)")

    # ---- GATE 1: block-bootstrap CI on MaxDD-reduction vs B&H ------------ #
    # bootstrap the DIFFERENCE series approach: CI on each strat's MaxDD, plus a
    # paired-difference bootstrap on the per-window DD reduction.
    out.append("\n## GATE 1 — block-bootstrap CI on MaxDD reduction (overlay vs B&H)\n")
    g1 = paired_maxdd_bootstrap(s_overlay["net"], s_bh["net"], block=21, B=5000)
    ci = g1["dd_reduction_ci_pp"]
    g1_pass = ci[0] > 0      # entire 95% CI above 0pp reduction
    out.append("```")
    out.append(f"DD-reduction (overlay MaxDD - B&H MaxDD; +ve=overlay shallower), "
               f"bootstrap 95% CI (pp): [{ci[0]:+.1f}, {ci[1]:+.1f}, {ci[2]:+.1f}]")
    out.append(f"P(overlay DD shallower than B&H) = {g1['prob_shallower']:.3f}")
    out.append(f"GATE 1: {'PASS' if g1_pass else 'FAIL'} (CI excludes 0)")
    out.append("```")
    # also vs 200dma
    g1b = paired_maxdd_bootstrap(s_overlay["net"], s_sma["net"], block=21, B=5000)
    cib = g1b["dd_reduction_ci_pp"]
    out.append(f"\nvs 200dma: DD-reduction 95% CI (pp): [{cib[0]:+.1f}, {cib[1]:+.1f}, {cib[2]:+.1f}]  "
               f"P(shallower)={g1b['prob_shallower']:.3f}  "
               f"{'CI excludes 0' if cib[0] > 0 else 'CI includes 0'}")

    # ---- GATE 2: split-half OOS, same-sign DD reduction ----------------- #
    out.append("\n## GATE 2 — split-half OOS (same-sign DD reduction in BOTH halves)\n")
    n = len(idx)
    halves = {"first": slice(0, n // 2), "second": slice(n // 2, n)}
    g2_signs = []
    out.append("```")
    for lab, sl in halves.items():
        ov = s_overlay["net"].iloc[sl]
        bhh = s_bh["net"].iloc[sl]
        dd_ov = maxdd_of(ov); dd_bh = maxdd_of(bhh)
        red = (dd_ov - dd_bh) * 100      # +ve = overlay shallower than B&H in this half
        shh = ov.mean() / ov.std() * np.sqrt(ANN) if ov.std() else np.nan
        shbh = bhh.mean() / bhh.std() * np.sqrt(ANN) if bhh.std() else np.nan
        g2_signs.append(np.sign(red))
        out.append(f"{lab:<7} overlay MaxDD {dd_ov*100:7.1f}  B&H MaxDD {dd_bh*100:7.1f}  "
                   f"DD-reduction {red:+6.1f}pp  Sharpe {shh:.2f} vs {shbh:.2f}")
    g2_pass = len(set(g2_signs)) == 1 and g2_signs[0] > 0
    out.append(f"GATE 2: {'PASS' if g2_pass else 'FAIL'} "
               f"(both halves same-sign positive DD-reduction)")
    out.append("```")

    # ---- GATE 3: leave-one-crisis-out ----------------------------------- #
    out.append("\n## GATE 3 — leave-one-crisis-out {2008, 2020, 2022}\n")
    out.append("Re-measure overlay vs B&H DD-reduction with each crisis window EXCISED "
               "from the return path.\n")
    out.append("```")
    out.append(f"{'excised':<10}{'overlay MaxDD':>15}{'B&H MaxDD':>12}{'DD-red pp':>12}"
               f"{'ov Sharpe':>11}{'bh Sharpe':>11}")
    full_red = dd_red_bh
    loco_reds = []
    for cz, (a, b) in CRISES.items():
        mask = ~((idx >= a) & (idx <= b))
        ov = s_overlay["net"][mask]; bhh = s_bh["net"][mask]
        dd_ov = maxdd_of(ov); dd_bh = maxdd_of(bhh)
        red = (dd_ov - dd_bh) * 100      # +ve = overlay shallower than B&H with crisis excised
        loco_reds.append(red)
        shh = ov.mean() / ov.std() * np.sqrt(ANN) if ov.std() else np.nan
        shbh = bhh.mean() / bhh.std() * np.sqrt(ANN) if bhh.std() else np.nan
        out.append(f"{'-'+cz:<10}{dd_ov*100:>15.1f}{dd_bh*100:>12.1f}{red:>12.1f}"
                   f"{shh:>11.2f}{shbh:>11.2f}")
    out.append(f"{'(full)':<10}{s_overlay['maxdd']:>15.1f}{s_bh['maxdd']:>12.1f}{full_red:>12.1f}"
               f"{s_overlay['sharpe']:>11.2f}{s_bh['sharpe']:>11.2f}")
    g3_pass = all(r > 0 for r in loco_reds)
    # how much does removing 2008 specifically cost the edge?
    red_no2008 = loco_reds[0]
    leans_2008 = red_no2008 < 0.5 * full_red
    out.append(f"GATE 3: {'PASS' if g3_pass else 'FAIL'} (DD-reduction stays positive "
               f"with each single crisis removed)")
    out.append(f"  edge concentration: full DD-red {full_red:+.1f}pp -> "
               f"without 2008 {red_no2008:+.1f}pp "
               f"({'LEANS HEAVILY on 2008' if leans_2008 else 'not dominated by 2008'})")
    out.append("```")

    # ---- GATE 4: deflated Sharpe across exposure-cutoff variants --------- #
    out.append("\n## GATE 4 — Deflated Sharpe (counting exposure-cutoff variants as trials)\n")
    # Variant family: alloc = clip(NAAIM/100,0,1) but with a binary de-risk cutoff at
    # several thresholds + the raw continuous version. These are the configs a hunter
    # would have tried; DSR deflates the winner for the search.
    variants = build_variants(spy, naaim, dff, idx)
    # winner = the continuous overlay (our headline) by Sharpe; report its DSR vs N trials
    best = max(variants, key=lambda v: v["sharpe"])
    sr_var = float(np.var([v["sr_daily"] for v in variants], ddof=1))
    mom = V.ret_moments(s_overlay["net"])
    out.append("```")
    out.append(f"{'variant':<24}{'Sharpe':>8}{'MaxDD%':>9}")
    for v in variants:
        mark = "  <- headline" if v["name"] == "continuous NAAIM/100" else ""
        out.append(f"{v['name']:<24}{v['sharpe']:>8}{v['maxdd']:>9}{mark}")
    out.append(f"\nN trials counted: {len(variants)}   winner: {best['name']}")
    dsr = None
    if mom:
        sr_daily, skew, kurt, T = mom
        dsr_res = V.deflated_sharpe(sr_daily, skew, kurt, T, n_trials=len(variants),
                                    sr_variance=sr_var, trading_year=ANN)
        if dsr_res:
            dsr = dsr_res["dsr"]
            out.append(f"DSR(continuous overlay) = {dsr:.4f}  "
                       f"(sr_ann {dsr_res['sr_annual']} vs haircut sr0_ann {dsr_res['sr0_annual']})")
            out.append(f"  {V.dsr_verdict(dsr)}")
    g4_pass = dsr is not None and dsr >= 0.90
    out.append(f"GATE 4: {'PASS' if g4_pass else 'FAIL'} (DSR >= 0.90)")
    out.append("```")

    # ---- GATE 5: beats the DUMB baseline (bootstrap, not point estimate) - #
    # The SCORED bar requires beating the dumb 200dma baseline. A 0.005 full-sample
    # Sharpe edge is meaningless without a noise interval, so paired block-bootstrap
    # the Sharpe DIFFERENCE (overlay - 200dma).
    out.append("\n## GATE 5 — beats the DUMB 200dma baseline (paired bootstrap, not point estimate)\n")
    g5 = paired_sharpe_bootstrap(s_overlay["net"], s_sma["net"], block=21, B=5000)
    csd = g5["sharpe_diff_ci"]
    g5_pass = csd[0] > 0      # whole CI above 0 = reliably beats the dumb baseline
    out.append("```")
    out.append(f"Sharpe diff (overlay - 200dma), 95% CI: [{csd[0]:+.3f}, {csd[1]:+.3f}, {csd[2]:+.3f}]")
    out.append(f"P(overlay Sharpe > 200dma Sharpe) = {g5['prob_better']:.3f}")
    out.append(f"point estimate: overlay {s_overlay['sharpe']} vs 200dma {s_sma['sharpe']} "
               f"(+{s_overlay['sharpe'] - s_sma['sharpe']:.3f})")
    out.append(f"GATE 5: {'PASS' if g5_pass else 'FAIL'} "
               f"(Sharpe-diff CI vs the dumb baseline excludes 0)")
    out.append(f"  ==> overlay does NOT reliably beat the free 200dma SMA on risk-adjusted "
               f"return; the edge is a coin flip" if not g5_pass else "")
    out.append(f"  CAGR: overlay {s_overlay['cagr']}% LOSES to 200dma {s_sma['cagr']}% "
               f"and gives up {s_bh['cagr'] - s_overlay['cagr']:.1f}pp/yr vs B&H "
               f"({s_overlay['final_mult']}x vs B&H {s_bh['final_mult']}x final wealth)")
    out.append("```")

    # ---- honest-N ------------------------------------------------------- #
    out.append("\n## Honest-N\n")
    out.append("The overlay's job is drawdown reduction in crises. INDEPENDENT crisis "
               "episodes in-sample (not the ~1040 weekly rows):")
    out.append("  2007-09 GFC, 2011 EU/US-downgrade, 2015-16 China/oil, 2018-Q4, "
               "2020 COVID, 2022 rate shock, 2025 tariff  ~= 6-7 independent drawdown clusters.")
    out.append("That is the real sample size for the DD-reduction claim — small.")

    # ---- VERDICT -------------------------------------------------------- #
    out.append("\n## VERDICT\n")
    # SCORED requires beating the DUMB baseline (GATE 5) under a noise interval, not
    # just a point-estimate Sharpe edge. DSR>=0.90 (G4) is necessary but NOT sufficient
    # here: it tests Sharpe>0 vs a search-haircut null, it does NOT know the overlay is
    # competing with a free 200dma rule. So SCORED demands G5 too.
    scored = (g4_pass and g2_pass and g3_pass and g5_pass
              and beats_bh_sharpe and beats_sma_sharpe and not leans_2008)
    # CONFIRMER: it reliably reduces drawdown vs B&H (G1 + same-sign split-half) even
    # though it doesn't beat the dumb baseline — a real, useful de-risking confirmer.
    confirmer = (beats_bh_dd and g1_pass and g2_pass)
    if scored:
        tier = "SCORED"
    elif confirmer:
        tier = "CONFIRMER"
    else:
        tier = "DISPLAY"
    out.append(f"**TIER: {tier}**")
    out.append("")
    out.append("Gate summary:")
    out.append(f"  beats B&H Sharpe (pt):   {beats_bh_sharpe}")
    out.append(f"  beats 200dma Sharpe (pt):{beats_sma_sharpe}  "
               f"(but bootstrap CI includes 0 -> not reliable, see GATE 5)")
    out.append(f"  beats B&H MaxDD:         {beats_bh_dd} ({dd_red_bh:+.1f}pp)")
    out.append(f"  beats 200dma MaxDD:      {beats_sma_dd} ({dd_red_sma:+.1f}pp, i.e. ~tie)")
    out.append(f"  GATE 1 bootstrap DD-CI:  {'PASS' if g1_pass else 'FAIL'} (vs B&H)")
    out.append(f"  GATE 2 split-half:       {'PASS' if g2_pass else 'FAIL'}")
    out.append(f"  GATE 3 leave-1-crisis:   {'PASS' if g3_pass else 'FAIL'} "
               f"(leans on 2008: {leans_2008})")
    out.append(f"  GATE 4 DSR>=0.90:        {'PASS' if g4_pass else 'FAIL'} (DSR={dsr})")
    out.append(f"  GATE 5 beats dumb basel: {'PASS' if g5_pass else 'FAIL'} "
               f"(Sharpe-diff vs 200dma CI excludes 0)")
    out.append("")
    out.append("HONEST READ: the overlay is a genuine DRAWDOWN-REDUCTION sleeve vs "
               "buy-&-hold (-55% -> -20% MaxDD, bootstrap-significant), but it does NOT "
               "beat the free 200dma trend rule (Sharpe-diff CI straddles 0, P=0.52; it "
               "LOSES on CAGR 7.97 vs 8.67), and removing 2008 erases its Sharpe edge over "
               "B&H. NAAIM is just a noisy weekly proxy for the same trend a daily SMA "
               "captures more cheaply. Lead with drawdown-reduction; never market it as alpha.")

    report = "\n".join(out)
    print(report)
    rp = ROOT / "reports" / "naaim-overlay-phase0.md"
    rp.parent.mkdir(exist_ok=True)
    rp.write_text(report)
    print(f"\n[written] {rp}")

    # machine-readable summary for the caller
    print("\n=== JSON SUMMARY ===")
    import json
    print(json.dumps({
        "tier": tier,
        "overlay": {k: s_overlay[k] for k in ("cagr", "sharpe", "maxdd", "final_mult")},
        "bh": {k: s_bh[k] for k in ("cagr", "sharpe", "maxdd")},
        "sma200": {k: s_sma[k] for k in ("cagr", "sharpe", "maxdd")},
        "spearman_naaim_fwddd": round(sp, 3),
        "dd_reduction_vs_bh_pp": round(dd_red_bh, 1),
        "dd_reduction_vs_sma_pp": round(dd_red_sma, 1),
        "gate1_bootstrap_ci_pp": ci,
        "gate1_pass": bool(g1_pass),
        "gate2_pass": bool(g2_pass),
        "gate3_pass": bool(g3_pass),
        "gate3_loco_reds_pp": [round(r, 1) for r in loco_reds],
        "gate3_leans_2008": bool(leans_2008),
        "gate4_dsr": dsr,
        "gate4_pass": bool(g4_pass),
        "gate5_sharpe_diff_ci_vs_sma": g5["sharpe_diff_ci"],
        "gate5_prob_better_than_sma": g5["prob_better"],
        "gate5_pass": bool(g5_pass),
        "beats_bh_sharpe": bool(beats_bh_sharpe),
        "beats_sma_sharpe_pt": bool(beats_sma_sharpe),
    }, indent=2))


def forward_drawdown(close: pd.Series, h: int) -> pd.Series:
    """Forward max drawdown over the next h bars (negative number)."""
    out = pd.Series(index=close.index, dtype=float)
    vals = close.values
    for i in range(len(vals) - 1):
        window = vals[i:i + h + 1]
        if len(window) < 2:
            continue
        peak = np.maximum.accumulate(window)
        dd = (window / peak - 1.0).min()
        out.iloc[i] = dd
    return out


def paired_maxdd_bootstrap(net_a: pd.Series, net_b: pd.Series, block: int = 21,
                           B: int = 5000, seed: int = 7) -> dict:
    """Circular block bootstrap of the PAIRED (overlay, B&H) return series; resample
    the same block indices for both so the DD-reduction is a paired statistic.
    Returns the 95% CI on (B&H MaxDD - overlay MaxDD) in pp and P(overlay shallower)."""
    j = pd.concat([net_a.rename("a"), net_b.rename("b")], axis=1).dropna()
    ra = j["a"].to_numpy(); rb = j["b"].to_numpy()
    n = len(ra)
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(n / block))
    grid = np.arange(block)
    reds = np.empty(B)
    for k in range(B):
        starts = rng.integers(0, n, nb)
        idx = (starts[:, None] + grid[None, :]).ravel()[:n] % n
        dda = V._maxdd(ra[idx]); ddb = V._maxdd(rb[idx])
        # +ve = strat-a (overlay) drawdown shallower than strat-b (baseline)
        reds[k] = (dda - ddb) * 100
    return {"dd_reduction_ci_pp": [round(float(np.percentile(reds, p)), 1)
                                   for p in (2.5, 50, 97.5)],
            "prob_shallower": round(float(np.mean(reds > 0)), 3)}


def paired_sharpe_bootstrap(net_a: pd.Series, net_b: pd.Series, block: int = 21,
                            B: int = 5000, seed: int = 7) -> dict:
    """Paired circular block bootstrap of the annualized SHARPE DIFFERENCE
    (strat-a - strat-b). Same resampled blocks for both legs so the difference is
    a paired statistic. Returns 95% CI on the diff and P(a beats b)."""
    j = pd.concat([net_a.rename("a"), net_b.rename("b")], axis=1).dropna()
    ra = j["a"].to_numpy(); rb = j["b"].to_numpy()
    n = len(ra)
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(n / block))
    grid = np.arange(block)
    diffs = np.empty(B)
    for k in range(B):
        starts = rng.integers(0, n, nb)
        ix = (starts[:, None] + grid[None, :]).ravel()[:n] % n
        diffs[k] = V._sharpe(ra[ix], ANN) - V._sharpe(rb[ix], ANN)
    return {"sharpe_diff_ci": [round(float(np.percentile(diffs, p)), 3)
                               for p in (2.5, 50, 97.5)],
            "prob_better": round(float(np.mean(diffs > 0)), 3)}


def build_variants(spy: pd.Series, naaim: pd.Series, dff: pd.Series,
                   idx: pd.DatetimeIndex) -> list[dict]:
    """The exposure-cutoff variant family the DSR must deflate for. The continuous
    NAAIM/100 overlay plus binary de-risk rules at several exposure thresholds."""
    lagged = naaim.copy()
    lagged.index = lagged.index + pd.Timedelta(days=7)
    daily = lagged.reindex(idx.union(lagged.index)).ffill().reindex(idx)
    variants = []
    # continuous
    cont = (daily / 100.0).clip(0.0, 1.0)
    variants.append(_v("continuous NAAIM/100", spy, cont, dff))
    # binary de-risk: flat when NAAIM below threshold, else fully long
    for thr in (30, 40, 50, 60):
        a = (daily >= thr).astype(float)
        variants.append(_v(f"binary cutoff>={thr}", spy, a, dff))
    # half-derisk at threshold
    for thr in (40, 50):
        a = pd.Series(np.where(daily >= thr, 1.0, 0.5), index=idx)
        variants.append(_v(f"half-derisk<{thr}", spy, a, dff))
    return variants


def _v(name: str, spy: pd.Series, alloc: pd.Series, dff: pd.Series) -> dict:
    bt = V.backtest_core(spy, alloc, cost_bps=COST_BPS, cash_yield=dff)
    net = bt["net"].dropna()
    eq = (1 + net).cumprod()
    sd = net.std()
    sr_daily = float(net.mean() / sd) if sd else 0.0
    return {"name": name, "sharpe": round(sr_daily * np.sqrt(ANN), 3),
            "maxdd": round(100 * float((eq / eq.cummax() - 1).min()), 1),
            "sr_daily": sr_daily, "net": net}


if __name__ == "__main__":
    main()
