"""Commodity Vector calibration — the house rule applied to the core four.

Every signal band earns a MEASURED forward record before the dashboard may claim
anything about it (the macro heat board taught us this, D31: a "confluence" score
that was INVERTED vs forward returns). Commodities have ~25y / multi-cycle depth,
so these verdicts are far sturdier than the crypto ones.

The headline question this script answers: does the RESIDUAL SHOCK signal (an
unexplained exogenous bid — CB buying, war premium, data-center demand) actually
PREDICT forward returns (momentum), FADE (mean-reversion), or is it descriptive
only? Whatever the data says ships to the tooltips verbatim.

Outputs (per asset + cross-asset), written to reports/ + data/commodity/:
  1. Forward-return records per band: momentum, structure, driver_score, shock_z,
     positioning — count / hit-rate / mean at the configured horizons.
  2. Risk Index judged on forward DRAWDOWN (its real job).
  3. Split-half robustness (pre/post split_date) — sign must hold in BOTH halves.
  4. Allocation backtest vs buy-and-hold for every variant.
  5. Whipsaw per state signal.
  6. Forward returns conditioned on the commodity-complex regime.

Run: .venv/bin/python -m scripts.calibrate_commodities
No look-ahead: signals are close-based; the backtest acts on shift(1).
"""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
warnings.filterwarnings("ignore")

from engine import commodity_signals  # noqa: E402
from engine.validation import (  # noqa: E402
    backtest_core, deflated_sharpe, dsr_verdict, ret_moments)
from lib import config  # noqa: E402

TRADING_YEAR = 252  # commodities trade ~252 days/yr


# --------------------------------------------------------------------------- #
# forward-outcome helpers (generic; copied to keep this script standalone)
# --------------------------------------------------------------------------- #
def forward_returns(close: pd.Series, horizons: list[int]) -> pd.DataFrame:
    return pd.DataFrame({h: close.shift(-h) / close - 1 for h in horizons})


def forward_drawdown(close: pd.Series, horizons: list[int]) -> pd.DataFrame:
    out = {}
    for h in horizons:
        fwd_min = close[::-1].rolling(h, min_periods=1).min()[::-1].shift(-1)
        out[h] = fwd_min / close - 1
    return pd.DataFrame(out)


def band_table(signal: pd.Series, fwd: pd.DataFrame, bands: list, labels: list[str],
               horizons: list[int]) -> pd.DataFrame:
    rows = []
    if isinstance(bands[0], (list, tuple)):  # categorical
        grouping = [(lab, signal.isin(vals if isinstance(vals, (list, tuple)) else [vals]))
                    for lab, vals in zip(labels, bands)]
    else:
        cats = pd.cut(signal, bins=bands, labels=labels, include_lowest=True)
        grouping = [(lab, cats == lab) for lab in labels]
    for lab, mask in grouping:
        rec = {"band": lab, "n": int(mask.sum())}
        for h in horizons:
            r = fwd.loc[mask, h].dropna()
            if len(r):
                rec[f"hit_{h}d"] = round(100 * (r > 0).mean(), 1)
                rec[f"mean_{h}d"] = round(100 * r.mean(), 2)
            else:
                rec[f"hit_{h}d"], rec[f"mean_{h}d"] = np.nan, np.nan
        rows.append(rec)
    return pd.DataFrame(rows)


def drawdown_table(signal: pd.Series, fdd: pd.DataFrame, bands: list,
                   labels: list[str], horizons: list[int]) -> pd.DataFrame:
    cats = pd.cut(signal, bins=bands, labels=labels, include_lowest=True)
    rows = []
    for lab in labels:
        mask = cats == lab
        rec = {"band": lab, "n": int(mask.sum())}
        for h in horizons:
            d = fdd.loc[mask, h].dropna()
            rec[f"avgDD_{h}d"] = round(100 * d.mean(), 2) if len(d) else np.nan
        rows.append(rec)
    return pd.DataFrame(rows)


def rank_trend(table: pd.DataFrame, col: str, n_floor: int = 120) -> int:
    t = table[table["n"] >= n_floor] if "n" in table.columns else table
    v = t[col].dropna().values
    if len(v) < 3:
        return 0
    rho = np.corrcoef(np.arange(len(v)), v)[0, 1]
    return 1 if rho > 0.6 else (-1 if rho < -0.6 else 0)


def _extremes_verdict(table: pd.DataFrame, base: float, mcol: str, hcol: str,
                      n_floor: int = 60) -> str:
    parts = []
    lo, hi = table.iloc[0], table.iloc[-1]
    if lo.get("n", 0) >= n_floor and pd.notna(lo.get(mcol)):
        tag = "STRONG" if lo[mcol] > base * 1.25 else ("WEAK-OPP" if lo[mcol] < base * 0.5 else "flat")
        parts.append(f"low {lo['band']}: {lo[mcol]:+.1f}% {lo.get(hcol)}%hit (n={int(lo['n'])}) [{tag}]")
    if hi.get("n", 0) >= n_floor and pd.notna(hi.get(mcol)):
        tag = "STRONG" if hi[mcol] > base * 1.25 else ("FADE" if hi[mcol] < base * 0.5 else "flat")
        parts.append(f"high {hi['band']}: {hi[mcol]:+.1f}% {hi.get(hcol)}%hit (n={int(hi['n'])}) [{tag}]")
    return "EXTREMES — " + ("; ".join(parts) if parts else "tails too thin")


def backtest(close: pd.Series, alloc: pd.Series, cost_bps: float = 0.0) -> dict:
    """Allocation vs buy-and-hold. `cost_bps` is the ONE-WAY transaction cost
    (spread + roll slippage) in basis points, charged on each unit of position
    turnover |Δpos| — a 0→1→0 round trip pays 2×cost_bps. Headline cagr/sharpe/maxdd
    are NET of cost (the honest figure); `*_gross` + `cost_drag_pp` show the bite and
    `turnover_annual` the one-way turnover/yr. Keeps the `hold_*` key naming the
    commodities dashboard (build_commodities.py) reads. Default 0.0 = legacy gross."""
    bt = backtest_core(close, alloc, cost_bps=cost_bps)
    ret, gross, strat, turnover, years, pos = (
        bt["ret"], bt["gross"], bt["net"], bt["turnover"], bt["years"], bt["pos"])
    eq = (1 + strat).cumprod()
    eq_gross = (1 + gross).cumprod()
    hold = (1 + ret).cumprod()

    def cagr(e):
        return (e.iloc[-1]) ** (1 / years) - 1 if years > 0 and e.iloc[-1] > 0 else np.nan

    def sharpe(r):
        sd = r.std()
        return (r.mean() / sd * np.sqrt(TRADING_YEAR)) if sd else np.nan

    def sortino(r):
        dn = r[r < 0].std()
        return (r.mean() / dn * np.sqrt(TRADING_YEAR)) if dn else np.nan

    def maxdd(e):
        return float((e / e.cummax() - 1).min())

    cagr_net, cagr_gross = cagr(eq), cagr(eq_gross)
    mom = ret_moments(strat)  # net per-period moments for the Deflated Sharpe
    return {
        "cagr": round(100 * cagr_net, 1), "hold_cagr": round(100 * cagr(hold), 1),
        "cagr_gross": round(100 * cagr_gross, 1) if pd.notna(cagr_gross) else np.nan,
        "cost_drag_pp": (round(100 * (cagr_gross - cagr_net), 1)
                         if pd.notna(cagr_net) and pd.notna(cagr_gross) else np.nan),
        "sharpe": round(sharpe(strat), 2), "hold_sharpe": round(sharpe(ret), 2),
        "sharpe_gross": round(sharpe(gross), 2),
        "sortino": round(sortino(strat), 2), "hold_sortino": round(sortino(ret), 2),
        "maxdd": round(100 * maxdd(eq), 1), "hold_maxdd": round(100 * maxdd(hold), 1),
        "time_in_market": round(100 * (pos > 0).mean(), 1),
        "turnover_annual": round(float(turnover.sum() / years), 1) if years > 0 else np.nan,
        "cost_bps": cost_bps,
        "final_vs_hold": round(eq.iloc[-1] / hold.iloc[-1], 2) if hold.iloc[-1] else np.nan,
        # per-period (daily) stats the Deflated Sharpe Ratio consumes:
        "sharpe_daily": round(mom[0], 6) if mom else None,
        "skew": round(mom[1], 4) if mom else None,
        "kurt": round(mom[2], 4) if mom else None,
        "n_obs": mom[3] if mom else None,
    }


def whipsaw(state: pd.Series, max_days: int) -> dict:
    s = state.dropna()
    seg = (s != s.shift()).cumsum()
    sizes = s.groupby(seg).size()
    changes = len(sizes) - 1
    whips = int((sizes.iloc[1:] < max_days).sum()) if changes > 0 else 0
    return {"changes": changes, "whipsaws": whips,
            "pct": round(100 * whips / changes, 1) if changes else 0.0}


# --------------------------------------------------------------------------- #
# signal specs (per asset). shock_z is judged DIRECTIONALLY (want=+1 = the
# "exogenous bids persist" hypothesis); an INVERTED verdict = bids fade — both
# are useful, honest findings.
# --------------------------------------------------------------------------- #
# vhz = verdict-horizon index into calibration.forward_days: trend signals
# (momentum/structure) are judged NEAR-term (0) because commodities mean-revert
# over 6 months; macro/valuation signals (driver/shock/positioning) are judged at
# the LONGEST horizon (-1) where the macro thesis plays out.
SIGNALS = {
    "momentum":     {"bands": [-1.01, -0.5, 0.0, 0.5, 1.01], "vhz": 0,
                     "labels": ["<-0.5", "-0.5..0", "0..0.5", ">0.5"], "want": 1},
    "ts_momentum":  {"bands": [-1.01, -0.3, 0.0, 0.3, 1.01], "vhz": -1,
                     "labels": ["strong-down", "down", "up", "strong-up"], "want": 1},
    "structure":    {"bands": [-1.01, -0.5, 0.5, 1.01], "vhz": 0,
                     "labels": ["broken", "neutral", "constructive"], "want": 1},
    "gsr_pctile":   {"bands": [-0.1, 20, 40, 60, 80, 100.1], "vhz": -1,
                     "labels": ["0-20", "20-40", "40-60", "60-80", "80-100"], "want": 1},
    "bw_change":    {"bands": [-100, -1.5, -0.3, 0.3, 1.5, 100], "vhz": -1,
                     "labels": ["<-1.5", "-1.5..-.3", "-.3..3", ".3..1.5", ">1.5"], "want": 1},
    "driver_score": {"bands": [-1.01, -0.34, 0.34, 1.01], "vhz": -1,
                     "labels": ["headwind", "neutral", "tailwind"], "want": 1},
    "shock_z":      {"bands": [-10, -1.5, -0.5, 0.5, 1.5, 10], "vhz": -1,
                     "labels": ["<-1.5", "-1.5..-.5", "-.5..5", ".5..1.5", ">1.5"],
                     "want": 1, "shape": "extremes"},
    "pos_pctile":   {"bands": [-0.1, 15, 50, 85, 100.1], "vhz": -1,
                     "labels": ["0-15", "15-50", "50-85", "85-100"], "want": -1},
}
RISK_BANDS = ([-0.1, 25, 50, 75, 100], ["0-25", "25-50", "50-75", "75-100"])


def build_asset(asset: str, df: pd.DataFrame, complex_regime: pd.Series,
                cal: dict, alloc_variants: dict,
                cost_bps: float = 0.0, n_trials: int = 1) -> dict:
    horizons = cal["forward_days"]
    df = df.loc[cal["start_date"]:].copy()
    close = df["close"]
    fwd = forward_returns(close, horizons)
    fdd = forward_drawdown(close, horizons)
    halves = {"full": df.index,
              "pre": df.index[df.index < cal["split_date"]],
              "post": df.index[df.index >= cal["split_date"]]}
    out: dict = {"span": f"{df.index.min().date()}..{df.index.max().date()}",
                 "rows": len(df), "signals": {}, "risk_drawdown": {},
                 "allocation": {}, "whipsaw": {}, "by_regime": {}}

    for sig, spec in SIGNALS.items():
        if sig not in df.columns or df[sig].notna().sum() < 200:
            continue
        entry = {}
        for half, idx in halves.items():
            entry[half] = band_table(df.loc[idx, sig], fwd.loc[idx],
                                     spec["bands"], spec["labels"], horizons).to_dict("records")
        vh = horizons[spec.get("vhz", -1)]
        hcol = f"mean_{vh}d"
        want = spec["want"]
        m = {h: rank_trend(pd.DataFrame(entry[h]), hcol) for h in halves}
        entry["verdict_horizon"] = vh
        if spec.get("shape") == "extremes":
            base = float(fwd.loc[df.index, vh].mean() * 100)
            entry["extremes"] = _extremes_verdict(pd.DataFrame(entry["full"]), base,
                                                  hcol, f"hit_{vh}d")
            entry["sample_mean"] = round(base, 2)
        if m["full"] == want and m["pre"] == want and m["post"] == want:
            entry["verdict"] = "CONFIRMED"
        elif m["full"] == -want:
            entry["verdict"] = "INVERTED"
        elif m["full"] == want and (m["pre"] == want or m["post"] == want):
            entry["verdict"] = "DIRECTIONAL (one half weak)"
        elif m["full"] == want:
            entry["verdict"] = "DIRECTIONAL (full only)"
        else:
            entry["verdict"] = "CONTEXT-ONLY"
        entry["monotone"] = {**m, "want": want}
        out["signals"][sig] = entry

    # risk index -> forward drawdown gauge
    if "risk_index" in df.columns:
        ddt = {h: drawdown_table(df.loc[idx, "risk_index"], fdd.loc[idx],
                                 RISK_BANDS[0], RISK_BANDS[1], horizons).to_dict("records")
               for h, idx in halves.items()}
        dcol = f"avgDD_{horizons[0]}d"
        rt = {h: rank_trend(pd.DataFrame(ddt[h]), dcol) for h in halves}
        ddt["verdict"] = ("CONFIRMED near-term risk gauge"
                          if all(v == -1 for v in rt.values())
                          else "DIRECTIONAL" if rt["full"] == -1 else "CONTEXT-ONLY")
        ddt["rank_trend"] = {**rt, "want": -1, "horizon": horizons[0]}
        out["risk_drawdown"] = ddt

    # allocation backtest vs buy-and-hold (NET of the configured one-way cost)
    for variant in alloc_variants:
        col = f"alloc_{variant}"
        if col in df.columns:
            out["allocation"][variant] = backtest(close, df[col], cost_bps=cost_bps)

    # ---- multiple-testing haircut: Deflated Sharpe on the SHIPPED variant ----- #
    # The published Sharpe is the MAX over the allocation variants we tried, so it
    # is upward-biased; the DSR deflates it for n_trials independent configs, sample
    # length, skew and fat tails. Cross-trial SR variance comes from the variants
    # actually backtested (floored at the null SR-sampling proxy inside the helper).
    va = out["allocation"]
    if va:
        sel = ("optimal" if "optimal" in va else
               max(va, key=lambda k: va[k]["cagr"] if pd.notna(va[k]["cagr"]) else -1e9))
        daily_srs = [v["sharpe_daily"] for v in va.values() if v.get("sharpe_daily") is not None]
        sr_var = float(np.var(daily_srs, ddof=1)) if len(daily_srs) >= 2 else None
        m = va[sel]
        dsr = deflated_sharpe(m.get("sharpe_daily"), m.get("skew"), m.get("kurt"),
                              m.get("n_obs"), n_trials, sr_variance=sr_var,
                              trading_year=TRADING_YEAR)
        if dsr is not None:
            dsr["selected_variant"] = sel
            dsr["sr_variance_source"] = ("max(cross-variant dispersion, null SR-sampling proxy)"
                                         if sr_var else "null SR-sampling proxy")
            dsr["verdict"] = dsr_verdict(dsr["dsr"])
            dsr["note"] = ("DSR = P(true Sharpe>0) after deflating for n_trials independent "
                           "configs, sample length, skew & kurtosis. n_trials is a manual "
                           "UPPER-BOUND of the signal/threshold/window variants explored per "
                           "asset — overestimating is the conservative direction (de Prado).")
        out["multiple_testing"] = dsr or {"dsr": None, "verdict": "insufficient data"}

    for sig in ("momentum_state", "ts_trend", "structure_state", "risk_regime",
                "driver_state", "shock_state", "pos_state", "gsr_state", "market_mode"):
        if sig in df.columns:
            out["whipsaw"][sig] = whipsaw(df[sig], cal["whipsaw_max_days"])

    # forward returns conditioned on the commodity-complex regime
    reg = complex_regime.reindex(df.index).ffill()
    labels = ["Reflation", "Stagflation", "Goldilocks", "Deflation-scare", "Neutral"]
    out["by_regime"] = band_table(reg, fwd, [[l] for l in labels], labels,
                                  horizons).to_dict("records")
    return out


def main() -> int:
    cal = config.load()["commodities"]["calibration"]
    alloc_variants = config.load()["commodities"]["allocation"]["variants"]
    # One-way transaction cost (spread+roll slippage) and the honest trial count
    # for the Deflated Sharpe live in config with code defaults (ships without a
    # config.yml edit). 8 bps ≈ a liquid commodity futures/ETF leg — wider than FX
    # spot, tighter than BTC; n_trials is a manual UPPER-BOUND of configs explored.
    cost_bps = float(cal.get("cost_bps", 8.0))
    n_trials = int(cal.get("n_trials", 40))
    res = commodity_signals.compute_all()
    complex_regime = res["_complex"]["complex_regime"]

    report = {"meta": {"split": cal["split_date"], "horizons": cal["forward_days"],
                       "cost_bps_one_way": cost_bps, "n_trials": n_trials},
              "assets": {}}
    outdir = config.data_dir() / "commodity"
    outdir.mkdir(parents=True, exist_ok=True)
    assets = [a for a in res if a != "_complex"]
    for asset in assets:
        report["assets"][asset] = build_asset(asset, res[asset], complex_regime,
                                               cal, alloc_variants,
                                               cost_bps=cost_bps, n_trials=n_trials)
        res[asset].to_parquet(outdir / f"signals_{asset}.parquet")
    res["_complex"].to_parquet(outdir / "signals_complex.parquet")

    # point-in-time trial ledger (overwritten each run) — the multiple-testing
    # bookkeeping the Deflated Sharpe deflates against.
    fams = sorted({s for a in report["assets"].values() for s in a.get("signals", {})})
    asof = max((res[a].index.max() for a in assets), default=None)
    report["trial_log"] = {
        "asof": str(asof.date()) if asof is not None else None,
        "n_trials_declared": n_trials,
        "cost_bps_one_way": cost_bps,
        "assets_tested": assets,
        "allocation_variants_tested": list(alloc_variants),
        "signal_families_screened": fams,
        "n_signal_families": len(fams),
        "note": ("Upper-bound count of independent strategy configs explored per asset, used "
                 "to deflate each asset's headline Sharpe. Raise commodities.calibration.n_trials "
                 "as you try more variants/thresholds/windows."),
    }

    (outdir / "calibration.json").write_text(json.dumps(report, indent=2, default=str))
    (outdir / "trial_log.json").write_text(json.dumps(report["trial_log"], indent=2, default=str))
    _write_markdown(report)
    print(_summary(report))
    return 0


def _summary(report: dict) -> str:
    L = ["\n=== Commodity Vector calibration ==="]
    for asset, a in report["assets"].items():
        L.append(f"\n## {asset.upper()}  ({a['span']}, {a['rows']} days)")
        L.append("  signal verdicts (forward-return rank-trend, split-half):")
        for sig, e in a["signals"].items():
            extra = f"  [{e['extremes']}]" if "extremes" in e else ""
            L.append(f"    {sig:14s} {e['verdict']:26s} monotone={e['monotone']}{extra}")
        if a["risk_drawdown"]:
            rd = a["risk_drawdown"]
            L.append(f"    risk_index     {rd['verdict']} (drawdown rank_trend={rd['rank_trend']})")
        _cb = next(iter(a["allocation"].values()), {}).get("cost_bps", 0)
        L.append(f"  allocation vs buy&hold (NET of {_cb}bps one-way cost):")
        for v, m in a["allocation"].items():
            L.append(f"    {v:13s} CAGR {m['cagr']:>6}% net (gross {m.get('cagr_gross')}%, "
                     f"drag {m.get('cost_drag_pp')}pp; hold {m['hold_cagr']}%)  "
                     f"Sharpe {m['sharpe']} (hold {m['hold_sharpe']})  "
                     f"MaxDD {m['maxdd']}% (hold {m['hold_maxdd']}%)  inMkt {m['time_in_market']}%  "
                     f"turn {m.get('turnover_annual')}x/yr")
        mt = a.get("multiple_testing")
        if mt and mt.get("dsr") is not None:
            L.append(f"    Deflated Sharpe [{mt['selected_variant']}]: DSR={mt['dsr']}  "
                     f"(SR {mt['sr_annual']} ann vs haircut SR0 {mt['sr0_annual']} ann; "
                     f"N={mt['n_trials']}, T={mt['T']}d) => {mt['verdict']}")
    return "\n".join(L)


def _write_markdown(report: dict) -> None:
    h = report["meta"]["horizons"]
    lines = ["# Commodity Vector — calibration report", "",
             f"Split-half boundary: {report['meta']['split']}. Forward horizons: {h} days.", "",
             "House rule: a relationship is trusted (labeled a *signal* in the UI) only if its "
             "forward-return rank-trend holds in the expected direction in the full sample AND "
             "survives both halves. The Risk Index is judged on forward DRAWDOWN (its real job). "
             "**shock_z** (the residual exogenous-bid detector) is judged directionally: CONFIRMED "
             "= bids persist (momentum), INVERTED = bids fade (mean-reversion) — both honest. "
             "Anything failing is context-only.", ""]
    for asset, a in report["assets"].items():
        lines.append(f"\n## {asset.upper()} — {a['span']} ({a['rows']} days)\n")
        lines.append("| Signal | Verdict | full | pre | post | want |")
        lines.append("|---|---|--:|--:|--:|--:|")
        for sig, e in a["signals"].items():
            mo = e["monotone"]
            lines.append(f"| {sig} | **{e['verdict']}** | {mo['full']} | {mo['pre']} | {mo['post']} | {mo['want']} |")
        if a["risk_drawdown"]:
            rd = a["risk_drawdown"]
            lines.append(f"| risk_index (drawdown) | **{rd['verdict']}** | {rd['rank_trend']['full']} "
                         f"| {rd['rank_trend']['pre']} | {rd['rank_trend']['post']} | -1 |")
        for sig, e in a["signals"].items():
            extra = f"  \n_{e['extremes']}_" if "extremes" in e else ""
            lines.append(f"\n### {asset} · {sig} — forward returns by band (full){extra}\n")
            lines.append(pd.DataFrame(e["full"]).to_markdown(index=False))
        lines.append(f"\n### {asset} · forward returns by complex regime\n")
        lines.append(pd.DataFrame(a["by_regime"]).to_markdown(index=False))
        _cb = next(iter(a["allocation"].values()), {}).get("cost_bps", 0)
        lines.append(f"\n### allocation vs buy-and-hold (NET of {_cb}bps one-way cost)\n")
        lines.append("`cagr` is net of transaction cost (the honest headline); `cagr_gross` "
                     "and `cost_drag_pp` show the cost bite, `turnover_annual` the one-way "
                     "turnover/yr driving it.\n")
        cols = ["cagr", "cagr_gross", "cost_drag_pp", "hold_cagr", "sharpe", "hold_sharpe",
                "sortino", "hold_sortino", "maxdd", "hold_maxdd", "time_in_market",
                "turnover_annual", "final_vs_hold"]
        at = pd.DataFrame(a["allocation"]).T
        lines.append(at[[c for c in cols if c in at.columns]].to_markdown())
        mt = a.get("multiple_testing")
        if mt and mt.get("dsr") is not None:
            lines.append(f"\n**Deflated Sharpe (multiple-testing haircut)** — shipped variant "
                         f"`{mt['selected_variant']}`: **{mt['verdict']}**. "
                         f"DSR (P true Sharpe>0) = **{mt['dsr']}**; observed SR {mt['sr_annual']} ann "
                         f"vs haircut SR0 {mt['sr0_annual']} ann (N={mt['n_trials']} trials, "
                         f"T={mt['T']}d, skew={mt['skew']}, kurt={mt['kurt']}).")
    tl = report.get("trial_log")
    if tl:
        lines.append("\n## Trial log\n")
        lines.append(f"As-of {tl['asof']}: **{tl['n_trials_declared']}** declared independent trials "
                     f"per asset (upper-bound); {tl['n_signal_families']} signal families screened "
                     f"across {len(tl['assets_tested'])} assets; allocation variants: "
                     f"{', '.join(tl['allocation_variants_tested'])}; transaction cost "
                     f"{tl['cost_bps_one_way']}bps one-way.")
    Path(config.load()["storage"]["reports_dir"], "commodity-calibration.md").write_text(
        "\n".join(lines))


if __name__ == "__main__":
    sys.exit(main())
