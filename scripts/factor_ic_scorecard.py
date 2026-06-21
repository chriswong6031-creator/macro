"""Leak-free factor IC scorecard — the payoff of the point-in-time panel (Phase A).

For each rebalance date on a quarterly grid we rebuild the factor cross-section AS
IT WAS KNOWABLE THEN — engine.equity_factors.compute_factors(asof=date), which
reads the EDGAR point-in-time panel (collectors/edgar.py) and truncates prices to
`asof`, so no factor ever sees a not-yet-filed 10-K. Each factor's z-score is then
rank-correlated with the forward return to get a per-date Information Coefficient,
aggregated to mean IC, IC-IR, a Newey-West (HAC) t-stat (the IC series autocorrelates
when forward windows overlap), and a Benjamini-Hochberg FDR across the factor panel
(many factors screened → control the family false-discovery rate). A VIF read flags
redundant factors. This is the honest answer to "do these factors actually rank
winners?" — and, post point-in-time fix, the spreads are expected to look weaker
than a naive latest-data backtest (that gap IS the look-ahead/survivorship bias
being removed). Judge survivors against ~0 (an AQR/Fama-French-style null).

Run: .venv/bin/python -m scripts.factor_ic_scorecard [--quick] [--deep] [--horizon 63] [--start 2011]
  --quick : only the last 12 quarters (fast verification); full grid is offline/weekly.
  --deep  : judge the whole zoo on the DEEP-history close panel (~2011-2026, data/edgar/
            sue_deep_closes.parquet) instead of the ~3y rolling breadth cache, so the IC /
            IC-IR / HAC-t / BH-FDR reflect >10y, not 2.5y. The deep panel is SURVIVORSHIP-
            BIASED (delisted names absent → an optimistic bound) and FINRA short-interest
            is dropped (no point-in-time history). Skips writing (keeps the committed deep
            scorecard) when the offline deep cache is not present — so CI never clobbers it
            with a shallow run. Backfill the cache with `python -m scripts.sue_deep_phase0`.
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
warnings.filterwarnings("ignore")   # truncated-history beta calc emits benign numpy RuntimeWarnings

from engine.equity_factors import FACTOR_LABELS, _closes, compute_factors  # noqa: E402
from engine.factor_orthogonal import orthogonal_composite, overlap_diagnostics  # noqa: E402
from engine.validation import (benjamini_hochberg, cross_sectional_resid,  # noqa: E402
                               ic_summary, rank_ic)
from lib import config  # noqa: E402

LEG_COLS = list(FACTOR_LABELS)                       # individual factor legs
# composite_orth = Löwdin-decorrelated composite (does removing factor overlap help?)
FACTOR_COLS = LEG_COLS + ["composite", "composite_orth"]

# Incremental IC neutralizes each factor against the style factors we already own
# (the roadmap basis: market beta, size, 12-1 momentum, low-vol). A factor whose IC
# survives this is INDEPENDENT information; one that collapses was repackaged style.
# Drop a factor's own style analog from its basis so the test isn't trivially zero.
def _style_basis(t: pd.DataFrame, closes: pd.DataFrame, d) -> pd.DataFrame:
    """Per-date style loadings (beta, size, 12-1 momentum, low-vol) on the factor
    table's universe — the basis incremental IC residualizes against. low_beta /
    low_vol are read straight off the table; size = log market cap; momentum is
    computed causally from prices truncated to `d`."""
    basis = pd.DataFrame(index=t.index)
    if "low_beta" in t:
        basis["beta"] = pd.to_numeric(t["low_beta"], errors="coerce")
    if "low_vol" in t:
        basis["low_vol"] = pd.to_numeric(t["low_vol"], errors="coerce")
    if "mktcap_bn" in t:
        basis["size"] = np.log(pd.to_numeric(t["mktcap_bn"], errors="coerce").where(lambda s: s > 0))
    px = closes.loc[:d]
    if len(px) >= 253:                               # 12-1 momentum (skip last month)
        mom = px.iloc[-22] / px.iloc[-253] - 1.0
        basis["mom"] = mom.reindex(t.index)
    return basis.dropna(axis=1, how="all")


# which basis column a factor IS (so we exclude it when neutralizing that factor)
_FACTOR_BASIS_SELF = {"low_vol": "low_vol", "low_beta": "beta"}


def quarter_grid(closes: pd.DataFrame, start_year: int, horizon: int) -> list:
    """Quarter-end trading dates from start_year, leaving room for the forward
    window (so every rebalance has a realized label)."""
    idx = closes.index
    q_ends = pd.date_range(f"{start_year}-03-31", idx.max(), freq="QE")
    out = []
    for q in q_ends:
        d = idx[idx <= q]
        if len(d) and idx.get_loc(d[-1]) + horizon < len(idx):
            out.append(d[-1])
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="last 12 quarters only")
    ap.add_argument("--deep", action="store_true",
                    help="judge the zoo on the deep-history (survivorship-biased) close panel")
    ap.add_argument("--horizon", type=int, default=63, help="forward return window (trading days)")
    ap.add_argument("--start", type=int, default=2011)
    args = ap.parse_args()

    universe = "deep" if args.deep else "broad"
    closes = _closes(universe)
    if closes.empty:
        if args.deep:
            # The deep close panel is an offline artifact (data/edgar/sue_deep_closes.parquet),
            # not rebuilt in daily CI. Absent → keep the committed deep scorecard rather than
            # overwriting it with a shallow run. Backfill with scripts.sue_deep_phase0.
            print("deep close panel absent — keeping the committed deep ic_scorecard.json "
                  "(backfill with: python -m scripts.sue_deep_phase0)")
            return 0
        print("no close caches — run breadth collectors first")
        return 1
    fwd = closes.pct_change(args.horizon, fill_method=None).shift(-args.horizon)  # forward return per date

    grid = quarter_grid(closes, args.start, args.horizon)
    if args.quick:
        grid = grid[-12:]
    if len(grid) < 6:
        print(f"grid too short ({len(grid)})")
        return 1

    per_date_ic: dict[str, list] = {c: [] for c in FACTOR_COLS}
    per_date_ic_incr: dict[str, list] = {c: [] for c in FACTOR_COLS}   # style-neutralized
    n_names: list[int] = []
    last_table = None
    for d in grid:
        fac = compute_factors(asof=d, universe=universe)
        if not fac or not fac.get("table"):
            continue
        t = pd.DataFrame(fac["table"]).set_index("ticker")
        last_table = t
        fr = fwd.loc[d] if d in fwd.index else None
        if fr is None:
            continue
        n_names.append(int(t.index.isin(fr.dropna().index).sum()))
        basis = _style_basis(t, closes, d)
        for c in FACTOR_COLS:
            sig = None
            if c in t.columns:
                sig = pd.to_numeric(t[c], errors="coerce")
            elif c == "composite_orth":
                legs = t[[lc for lc in LEG_COLS if lc in t.columns]].apply(pd.to_numeric, errors="coerce")
                if legs.shape[1] >= 3:
                    sig = orthogonal_composite(legs)
            if sig is None:
                continue
            per_date_ic[c].append(rank_ic(sig, fr))
            # incremental: residualize vs the style basis (excluding the factor's own
            # style analog), then re-correlate with the forward return
            b = basis.drop(columns=[_FACTOR_BASIS_SELF[c]], errors="ignore") \
                if c in _FACTOR_BASIS_SELF else basis
            if b.shape[1] >= 2:
                resid = cross_sectional_resid(sig, b)
                if len(resid):
                    per_date_ic_incr[c].append(rank_ic(resid, fr))

    # aggregate per factor + FDR across the panel
    ppy = 4  # quarterly
    rows, pvals, pvals_incr = {}, {}, {}
    for c in FACTOR_COLS:
        ics = pd.Series(per_date_ic[c]).dropna()
        s = ic_summary(ics, periods_per_year=ppy)
        if s.get("n", 0) >= 6:
            rows[c] = s
            if s.get("p_hac") is not None:
                pvals[c] = s["p_hac"]
            # incremental (style-neutralized) IC alongside the raw block
            si = ic_summary(pd.Series(per_date_ic_incr[c]).dropna(), periods_per_year=ppy)
            if si.get("n", 0) >= 6:
                rm, im = s.get("mean_ic"), si.get("mean_ic")
                rows[c].update({
                    "mean_ic_incr": im, "ic_ir_ann_incr": si.get("ic_ir_ann"),
                    "t_hac_incr": si.get("t_hac"), "p_hac_incr": si.get("p_hac"),
                    "n_incr": si.get("n"),
                    "ic_delta": round(im - rm, 4) if (rm is not None and im is not None) else None,
                    "surviving_frac": round(im / rm, 3) if rm not in (None, 0) and im is not None else None,
                })
                if si.get("p_hac") is not None:
                    pvals_incr[c] = si["p_hac"]
    fdr = benjamini_hochberg(pvals, alpha=0.10)
    for c, q in fdr.items():
        rows[c]["q_fdr"] = q["q"]
        rows[c]["survives_fdr"] = q["reject"]
    # BH-FDR on the INCREMENTAL p-values — the strictly harder bar; a factor only
    # "survives" here if its independent (style-neutralized) IC clears the family test.
    fdr_incr = benjamini_hochberg(pvals_incr, alpha=0.10)
    for c, q in fdr_incr.items():
        rows[c]["q_fdr_incr"] = q["q"]
        rows[c]["survives_fdr_incr"] = q["reject"]

    coll = {}
    if last_table is not None:
        legs = last_table[[c for c in LEG_COLS if c in last_table.columns]].apply(
            pd.to_numeric, errors="coerce")
        coll = overlap_diagnostics(legs)   # raw vs orthogonalized factor overlap + VIF

    note = ("Point-in-time (EDGAR panel + prices truncated to asof); IC = quarterly "
            "cross-sectional rank corr of factor z vs forward return; t_hac = Newey-West; "
            "q_fdr = Benjamini-Hochberg across the factor panel. Survivors judged vs ~0. "
            "mean_ic_incr = IC after neutralizing vs style (beta/size/12-1 mom/low-vol); "
            "q_fdr_incr BH-FDRs the INCREMENTAL p-values (the harder bar) — a factor that "
            "survives there carries information independent of repackaged style.")
    caveat = None
    if args.deep:
        caveat = ("Deep ~2011-2026 re-test on a SURVIVORSHIP-BIASED price panel: delisted "
                  "names are absent (yahoo serves only currently-listed), so this is an "
                  "OPTIMISTIC bound — a clean test needs delisting-recovered prices. FINRA "
                  "short-interest is omitted (no point-in-time history). Fundamentals stay "
                  "point-in-time from the EDGAR panel. Compare to the shallow 2023-2025 read: "
                  "factors that survived on ~2.5y (notably SUE) weaken on deep history.")
        note = caveat + " " + note
    # Phase-1B de-bias telemetry: how much of the dead-name universe the merged
    # fundamentals panel now recovers (the survivor IC above is an optimistic bound
    # whose tightness this ratio quantifies). Display-only, never gates.
    dead_cov = None
    cov_p = config.data_dir() / "edgar" / "_dead_name_coverage.json"
    if cov_p.exists():
        try:
            dead_cov = json.loads(cov_p.read_text())
        except Exception:  # noqa: BLE001
            dead_cov = None
    report = {
        "horizon_d": args.horizon, "rebalances": len(grid),
        "span": f"{grid[0].date()}..{grid[-1].date()}",
        "median_universe": int(np.median(n_names)) if n_names else 0,
        "leak_free": True,
        "universe": universe,
        "survivorship_biased": bool(args.deep),
        "neutralized_against": ["market_beta", "size(log mktcap)", "mom_12_1", "low_vol"],
        "dead_name_coverage": dead_cov,
        "price_span": f"{closes.index.min().date()}..{closes.index.max().date()}",
        "factors": rows, "collinearity": coll,
        "caveat": caveat,
        "note": note,
    }
    outdir = config.data_dir() / "edgar"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "ic_scorecard.json").write_text(json.dumps(report, indent=2, default=str))
    _write_md(report)

    order = sorted(rows, key=lambda c: -(rows[c].get("ic_ir_ann") or -9))
    tag = "DEEP/survivorship-biased" if args.deep else "shallow breadth cache"
    print(f"\n=== Factor IC scorecard (leak-free, {tag}) — {report['span']}, {len(grid)} quarterly "
          f"rebalances, fwd {args.horizon}d, ~{report['median_universe']} names ===")
    print(f"{'factor':14s} {'meanIC':>7} {'IC_incr':>8} {'Δ':>7} {'surv%':>6} {'t_HAC':>6} "
          f"{'tHACi':>6} {'qFDR':>6} {'qFDRi':>6} {'n':>3}")
    for c in order:
        r = rows[c]
        print(f"{c:14s} {r['mean_ic']:>7.4f} {str(r.get('mean_ic_incr','-')):>8} "
              f"{str(r.get('ic_delta','-')):>7} {str(r.get('surviving_frac','-')):>6} "
              f"{str(r['t_hac']):>6} {str(r.get('t_hac_incr','-')):>6} "
              f"{str(r.get('q_fdr','-')):>6} {str(r.get('q_fdr_incr','-')):>6} {r['n']:>3}")
    surv = [c for c in rows if rows[c].get("survives_fdr")]
    # split the incremental survivors by sign: a two-sided FDR reject with a POSITIVE
    # incremental IC is an independent edge; a negative one is reliably anti-predictive.
    edge = [c for c in rows if rows[c].get("survives_fdr_incr") and (rows[c].get("mean_ic_incr") or 0) > 0]
    anti = [c for c in rows if rows[c].get("survives_fdr_incr") and (rows[c].get("mean_ic_incr") or 0) < 0]
    print(f"\nSurvive BH-FDR(10%) raw: {surv or 'NONE'}")
    print(f"Independent POSITIVE edge (incr IC>0, FDR✓): {edge or 'NONE'}")
    print(f"Reliably ANTI-predictive after neutralization (incr IC<0, FDR✓): {anti or 'NONE'}")
    return 0


def _write_md(report: dict) -> None:
    depth = ("**deep ~2011-2026, survivorship-biased**" if report.get("survivorship_biased")
             else "shallow breadth cache (~3y)")
    L = ["# Factor IC scorecard (leak-free, point-in-time)", "",
         f"Span {report['span']} · {report['rebalances']} quarterly rebalances · "
         f"forward {report['horizon_d']}d · ~{report['median_universe']} names · "
         f"price panel {depth} · point-in-time (no look-ahead).", "",
         "IC = cross-sectional rank correlation of each factor's z-score vs the forward "
         "return, per rebalance. `t_HAC` is Newey-West (overlapping windows autocorrelate "
         "the IC series); `q_FDR` is Benjamini-Hochberg across the factor panel. "
         "**IC incr** is the IC after neutralizing the factor against the style we already "
         "own (beta / size / 12-1 momentum / low-vol); **q_FDR incr** BH-FDRs those "
         "incremental p-values — the harder bar. Judge survivors against ~0.", "",
         "| factor | mean IC | IC incr | Δ | survives | t_HAC | t_HAC incr | q_FDR | q_FDR incr | n |",
         "|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|"]
    rows = report["factors"]
    for c in sorted(rows, key=lambda c: -(rows[c].get("ic_ir_ann") or -9)):
        r = rows[c]
        L.append(f"| {c} | {r['mean_ic']} | {r.get('mean_ic_incr','—')} | "
                 f"{r.get('ic_delta','—')} | {r.get('surviving_frac','—')} | {r['t_hac']} | "
                 f"{r.get('t_hac_incr','—')} | {r.get('q_fdr','—')} | "
                 f"{r.get('q_fdr_incr','—')} | {r['n']} |")
    surv = [c for c in rows if rows[c].get("survives_fdr")]
    edge = [c for c in rows if rows[c].get("survives_fdr_incr") and (rows[c].get("mean_ic_incr") or 0) > 0]
    anti = [c for c in rows if rows[c].get("survives_fdr_incr") and (rows[c].get("mean_ic_incr") or 0) < 0]
    L += ["", f"**Survive BH-FDR(10%) raw:** {', '.join(surv) if surv else 'NONE'}",
          f"**Independent POSITIVE edge** (incremental IC>0, FDR✓): "
          f"{', '.join(edge) if edge else 'NONE'} — *this is what to rank on, not raw IC.*",
          f"**Reliably anti-predictive after neutralization** (incremental IC<0, FDR✓): "
          f"{', '.join(anti) if anti else 'NONE'}", ""]
    coll = report.get("collinearity", {})
    if coll.get("top_pairs"):
        L.append("## Factor overlap (latest cross-section)\n")
        L.append(f"`composite_orth` above is the Löwdin-decorrelated composite. Mean "
                 f"|factor corr| **{coll.get('mean_abs_corr_raw')}** raw → "
                 f"**{coll.get('mean_abs_corr_orth')}** orthogonalized (the redundancy removed). "
                 f"VIF>5 = redundant. Most-correlated pairs:")
        for p in coll["top_pairs"]:
            L.append(f"- {p['a']} ↔ {p['b']}: |corr| {p['corr']}")
        hi = {k: v for k, v in coll.get("vif", {}).items() if v and v > 5}
        if hi:
            L.append(f"\nHigh VIF: {hi}")
    L.append(f"\n> {report['note']}")
    Path(config.load()["storage"]["reports_dir"], "factor-ic-scorecard.md").write_text("\n".join(L))


if __name__ == "__main__":
    sys.exit(main())
