"""Robustness addendum to options_opex_vanna_charm_study (Fable adjudication pass).

Two checks the original study lacked:

1. Vol/size-residualized partial ICs. The study's headline cross-sectional ICs
   (front-week charm/gamma concentration and Greek intensities vs future 5d
   realized vol) carry no control for current realized vol or size, so they may
   be vol-persistence / mega-cap proxies. Here every feature-vs-target IC is
   recomputed as a partial Spearman IC per date after rank-residualizing both
   sides on trailing 20d realized vol and log OI notional.

2. A real ETF/index/sector-only slice. The findings report cites an "ETF-only
   robustness slice" (F-15/16/17/20) that is absent from the shipped script and
   JSON. This script actually runs the greek panel, cross-section and state
   tests on the ETF universe so those claims have an artifact — or die.

Descriptive robustness output only; no score path, no gate change.

Outputs:
  reports/artifacts/options_opex_vanna_charm_robustness.json
  reports/artifacts/options_opex_vanna_charm_robustness.md
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import options_opex_vanna_charm_study as study  # noqa: E402

OUT_JSON = Path("reports/artifacts/options_opex_vanna_charm_robustness.json")
OUT_MD = Path("reports/artifacts/options_opex_vanna_charm_robustness.md")
PANEL_CACHE = Path("/tmp/options_opex_vanna_charm_panel.parquet")

ETF_ROOTS = [
    "SPY", "QQQ", "IWM", "DIA", "SPX",
    "XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY",
    "SMH", "SOXX", "XBI", "KRE", "ARKK",
]

# Feature/target pairs mirroring the study's headline survivors.
PARTIAL_FEATURES = [
    ("front7_abs_charm_share", "front_week_charm_concentration"),
    ("front7_abs_gex_share", "front_week_gamma_concentration"),
    ("net_charm_ratio", "signed_charm_pressure"),
    ("abs_charm", "charm_intensity"),
    ("abs_vanna", "vanna_intensity"),
    ("abs_gex", "gamma_intensity"),
    ("vanna_hedge5", "vanna_hedge_pressure_5d_ivmove"),
]
PARTIAL_TARGETS = [
    ("fwd_rv5", "realized_vol_5d", 5),
    ("fwd_abs_ret5", "abs_move_5d", 5),
]
CONTROLS = ["trail_rv20", "log_oi_notional"]


def add_controls(panel: pd.DataFrame) -> pd.DataFrame:
    out = []
    for _, g in panel.groupby("root", sort=False):
        g = g.sort_values("date").reset_index(drop=True)
        px = g["spot"].astype(float)
        log_ret = np.log(px / px.shift(1))
        # Trailing window ends at t; forward targets start at t+1 — no overlap.
        g["trail_rv20"] = log_ret.rolling(20).std() * np.sqrt(252)
        g["log_oi_notional"] = np.log(
            (g["total_oi"].astype(float) * px * 100.0).clip(lower=1.0)
        )
        out.append(g)
    return pd.concat(out, ignore_index=True)


def _partial_ic_one_date(ddf: pd.DataFrame, feature: str, target: str) -> tuple[float, float]:
    """Return (raw_ic, partial_ic) for one date's cross-section.

    Partial Spearman: pct-rank everything within date, OLS-residualize the
    feature rank and target rank on control ranks (+intercept), then Pearson
    on the residuals.
    """
    cols = [feature, target] + CONTROLS
    r = ddf[cols].rank(pct=True).to_numpy(float)
    f, y, c = r[:, 0], r[:, 1], r[:, 2:]
    raw = np.corrcoef(f, y)[0, 1]
    X = np.column_stack([np.ones(len(f)), c])
    try:
        bf, *_ = np.linalg.lstsq(X, f, rcond=None)
        by, *_ = np.linalg.lstsq(X, y, rcond=None)
    except np.linalg.LinAlgError:
        return raw, float("nan")
    rf = f - X @ bf
    ry = y - X @ by
    if np.std(rf) < 1e-12 or np.std(ry) < 1e-12:
        return raw, float("nan")
    return raw, float(np.corrcoef(rf, ry)[0, 1])


def run_partial_ic_tests(panel: pd.DataFrame, min_roots: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for feature, feature_label in PARTIAL_FEATURES:
        if feature not in panel.columns:
            continue
        for era, start, end in study.GREEK_ERAS:
            edf = study._era_slice(panel, "date", start, end)
            if edf.empty:
                continue
            for target, target_label, horizon in PARTIAL_TARGETS:
                raw_ics, part_ics = [], []
                need = ["date", "root", feature, target] + CONTROLS
                for _, ddf in edf[need].dropna().groupby("date"):
                    if len(ddf) < min_roots:
                        continue
                    raw, part = _partial_ic_one_date(ddf, feature, target)
                    if np.isfinite(raw) and np.isfinite(part):
                        raw_ics.append(raw)
                        part_ics.append(part)
                if len(part_ics) < 30:
                    continue
                lag = study._overlap_lag(len(part_ics), horizon)
                t_raw, p_raw, _ = study._hac_ttest(np.asarray(raw_ics), lag=lag)
                t_part, p_part, n = study._hac_ttest(np.asarray(part_ics), lag=lag)
                mean_raw = float(np.mean(raw_ics))
                mean_part = float(np.mean(part_ics))
                rows.append({
                    "family": "partial_ic",
                    "era": era,
                    "feature": feature_label,
                    "target": target_label,
                    "raw_ic": study._f(mean_raw, 5),
                    "raw_t": study._f(t_raw, 4),
                    "partial_ic": study._f(mean_part, 5),
                    "t": study._f(t_part, 4),
                    "p": study._f(p_part, 6),
                    "retained_frac": study._f(mean_part / mean_raw, 4)
                    if abs(mean_raw) > 1e-9 else None,
                    "n_dates": int(n),
                    "lag": int(lag),
                })
    study._bh_fdr(rows, "p", alpha=0.10)
    rows.sort(key=lambda r: (r["feature"], r["target"], r["era"]))
    return rows


def run_control_strength(panel: pd.DataFrame, min_roots: int) -> list[dict[str, Any]]:
    """How big is the confound itself? IC of the controls vs the targets."""
    rows: list[dict[str, Any]] = []
    for ctrl in CONTROLS:
        for era, start, end in study.GREEK_ERAS:
            edf = study._era_slice(panel, "date", start, end)
            for target, target_label, horizon in PARTIAL_TARGETS:
                ics = []
                for _, ddf in edf[["date", ctrl, target]].dropna().groupby("date"):
                    if len(ddf) < min_roots:
                        continue
                    from scipy import stats as sstats
                    rho, _ = sstats.spearmanr(
                        ddf[ctrl].to_numpy(float), ddf[target].to_numpy(float)
                    )
                    if np.isfinite(rho):
                        ics.append(rho)
                if len(ics) < 30:
                    continue
                lag = study._overlap_lag(len(ics), horizon)
                t, p, n = study._hac_ttest(np.asarray(ics), lag=lag)
                rows.append({
                    "family": "control_strength",
                    "era": era,
                    "feature": ctrl,
                    "target": target_label,
                    "mean_ic": study._f(np.mean(ics), 5),
                    "t": study._f(t, 4),
                    "p": study._f(p, 6),
                    "n_dates": int(n),
                })
    return rows


def summarize(results: dict[str, Any]) -> str:
    lines = ["# OPEX/Vanna/Charm Robustness Addendum (Fable adjudication)", ""]
    lines.append(f"Generated: {results['generated_at']}")
    lines.append("")
    lines.append("## 1. Control strength (the confound itself)")
    for r in results["control_strength"]:
        lines.append(
            f"- {r['era']} {r['feature']} -> {r['target']}: IC={r['mean_ic']}, t={r['t']}."
        )
    lines.append("")
    lines.append("## 2. Raw vs vol/size-residualized partial ICs (full universe)")
    lines.append("")
    lines.append("| feature | target | era | raw IC | partial IC | retained | t(part) | adj_p | survives |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for r in results["partial_ic_tests"]:
        lines.append(
            f"| {r['feature']} | {r['target']} | {r['era']} | {r['raw_ic']} "
            f"| {r['partial_ic']} | {r['retained_frac']} | {r['t']} "
            f"| {r.get('bh_adj_p')} | {'YES' if r.get('bh_reject_10pct') else 'no'} |"
        )
    lines.append("")
    lines.append("## 3. Real ETF/index/sector slice (the slice F-15/16/17/20 cited without artifact)")
    gp = results.get("etf_panel", {})
    lines.append(
        f"- ETF panel: {gp.get('n_rows')} rows, {gp.get('n_roots')} roots, "
        f"{gp.get('start')} to {gp.get('end')}."
    )
    lines.append("")
    lines.append("### ETF cross-section survivors (BH-FDR 10% within slice)")
    cs = [r for r in results.get("etf_cross_section", []) if r.get("bh_reject_10pct")]
    if cs:
        for r in cs:
            lines.append(
                f"- {r['era']} {r['feature']} -> {r['target']}: IC={r['mean_ic']}, "
                f"t={r['t']}, adj_p={r.get('bh_adj_p')}."
            )
    else:
        lines.append("- none")
    lines.append("")
    lines.append("### ETF state-spread survivors (BH-FDR 10% within slice)")
    st = [r for r in results.get("etf_state_tests", []) if r.get("bh_reject_10pct")]
    if st:
        for r in st:
            lines.append(
                f"- {r['era']} {r['condition']} -> {r['target']}: "
                f"spread {r['spread_mean_pct']}pp, t={r['t']}, adj_p={r.get('bh_adj_p')}."
            )
    else:
        lines.append("- none")
    lines.append("")
    lines.append("### ETF pin/air-pocket cells (all, survivors or not — the F-15/16 claims)")
    for r in results.get("etf_state_tests", []):
        if r["condition"] in (
            "opex_long_gamma_high_charm_pin",
            "opex_short_gamma_high_charm_airpocket",
        ) and r["target"] in ("realized_vol_5d", "abs_move_5d"):
            lines.append(
                f"- {r['era']} {r['condition']} -> {r['target']}: "
                f"spread {r['spread_mean_pct']}pp, t={r['t']}, p={r['p']}, "
                f"adj_p={r.get('bh_adj_p')}, n_dates={r['n_dates']}, "
                f"n_cond={r['n_condition_obs']}."
            )
    lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start-year", type=int, default=2017)
    ap.add_argument("--end-year", type=int, default=2026)
    ap.add_argument("--rebuild-cache", action="store_true")
    args = ap.parse_args()

    if PANEL_CACHE.exists() and not args.rebuild_cache:
        print(f"Loading cached panel {PANEL_CACHE}", flush=True)
        panel = pd.read_parquet(PANEL_CACHE)
        panel["date"] = pd.to_datetime(panel["date"])
    else:
        roots = study._manifest_roots(None)
        print(f"Aggregating greek panel for {len(roots)} roots...", flush=True)
        t0 = time.time()
        panel = study.aggregate_greek_panel(roots, args.start_year, args.end_year)
        print(f"Panel built in {time.time() - t0:.0f}s", flush=True)
        if panel.empty:
            print("SKIP: greek panel empty")
            return 0
        panel.to_parquet(PANEL_CACHE)

    panel = add_controls(panel)
    print(f"Panel: {len(panel)} rows, {panel['root'].nunique()} roots", flush=True)

    print("Control-strength ICs...", flush=True)
    control_strength = run_control_strength(panel, study.MIN_ROOTS_PER_DATE)
    print("Partial-IC tests (full universe)...", flush=True)
    partial_rows = run_partial_ic_tests(panel, study.MIN_ROOTS_PER_DATE)

    etf_panel = panel[panel["root"].isin(ETF_ROOTS)].copy()
    etf_summary = {
        "n_rows": int(len(etf_panel)),
        "n_roots": int(etf_panel["root"].nunique()),
        "start": str(etf_panel["date"].min().date()) if len(etf_panel) else None,
        "end": str(etf_panel["date"].max().date()) if len(etf_panel) else None,
        "roots": sorted(etf_panel["root"].unique().tolist()),
    }
    # Slice has ~21 roots; the study's 20-per-date floor would drop most dates.
    study.MIN_ROOTS_PER_DATE = 12
    print("ETF-slice cross-section tests...", flush=True)
    etf_cs = study.run_cross_section_tests(etf_panel)
    print("ETF-slice state tests...", flush=True)
    etf_state = study.run_state_tests(etf_panel)

    results = {
        "schema": "options_opex_vanna_charm_robustness.v1",
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
        "note": (
            "Fable adjudication addendum. Partial ICs residualize feature and "
            "target ranks on trailing 20d realized vol + log OI notional within "
            "each date. ETF slice reruns the study's tests on the index/sector/"
            "industry ETF universe with MIN_ROOTS_PER_DATE=12. Descriptive "
            "robustness only; no gate or score path is touched."
        ),
        "controls": CONTROLS,
        "control_strength": control_strength,
        "partial_ic_tests": partial_rows,
        "etf_panel": etf_summary,
        "etf_cross_section": etf_cs,
        "etf_state_tests": etf_state,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(results, indent=2, default=str))
    OUT_MD.write_text(summarize(results))
    print(f"Wrote {OUT_JSON}")
    print(f"Wrote {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
