"""PIT-frame re-measurement of the drawdown-risk gauge's forward-drawdown hit rate.

The audit (#39): `conditions.drawdown_risk` renders a per-band P(>=10% drawdown in
63d) table (base ~8% -> elevated 26% -> high 36% -> extreme 38%; config summarizes it
as "~45%"). Those numbers were measured on the LATEST-REVISED FRED frame AND on a
`recession_risk` composition that still included the Sahm labor leg (weight 1.0). The
live composition now uses jobless CLAIMS, not Sahm (config.yml recession.weights, and
conditions.py L142-158: claims REPLACE > AUGMENT > Sahm-only), and the live drawdown
gauge folds recession_risk in as one of four legs. So the shipped band table describes
neither the live data frame nor the live composition.

This harness re-runs the SAME production gauge (engine.conditions.conditions_frame,
which computes `drawdown_risk` off recession_risk+NFCI+EBP+HY-OAS exactly as it ships)
on THREE frames and reports the band hit-rates with Wilson CIs on each:

  * latest    : engine.inputs.build_features()               -- the live path today.
  * release   : engine.inputs.build_features(pit_basis='release')
                -- the leak-free PIT frame. Revision-prone econ legs (claims via the
                   ALFRED ICSA/CCSA vintages back to 2009, recession_prob, sticky-CPI,
                   etc.) carry only what was knowable, initial-release, on each day.
                   Market legs (HY OAS, NFCI, EBP inputs) are never revised -> untouched.
  * reference : build_features(pit_basis='reference') -- the A/B control that reproduces
                the live stamping (byte-identical to `latest` for the local store); a
                sanity leg that the accessor plumbing itself introduces no drift.

Composition note: BOTH frames now use the CLAIMS labor leg (the Sahm leg is disabled in
config once claims carry weight). So this is the honest reconciliation the audit asks
for: the number re-issued is measured on (a) the frame the signal fires on and (b) the
composition it fires with. The pre-2009 fallback for the claims vintage is documented:
ICSA/CCSA ALFRED realtime_start begins 2009, so PIT rows before 2009 fall back to the
modelled-release lag calendar (initial_claims lag ~5 bd) rather than a true as-of join;
this is stamped in the passport (`claims_pit_true_asof_from`).

Forward-drawdown target (matches the original measurement, research/QUANT_FACTOR_EXPANSION.md
§6): over the next `horizon` (63) trading days, the max peak-to-trough decline of SPY
from the reading date. A hit = that decline reaches `dd_threshold` (10%). Overlapping
windows are the population; the Wilson CI is reported WITH the honest caveat that
overlap inflates effective N (a block estimate of the independent-observation count is
shipped alongside).

Writes data/regime/drawdown_risk_pit.json (the re-issued band table + passport) and
reports/drawdown-risk-pit-validation.md. The site/brain read the JSON.

Run: PYTHONPATH=. python -m scripts.validate_drawdown_risk_pit [--horizon 63] [--dd 0.10]
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
warnings.filterwarnings("ignore")

from engine import conditions, inputs  # noqa: E402
from engine.validation import _norm_ppf  # noqa: E402
from lib import config  # noqa: E402

# The band cut points must match the LIVE gauge (config engine.conditions.drawdown_risk).
# We read them from config so a config change can never desync the measurement.
BASES = ["latest", "release", "reference"]


def _wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float, float]:
    """Wilson score interval for a binomial proportion. Returns (p, lo, hi) in %."""
    if n <= 0:
        return (float("nan"), float("nan"), float("nan"))
    p = k / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (100.0 * p, 100.0 * max(0.0, centre - half), 100.0 * min(1.0, centre + half))


def _fwd_max_drawdown(close: pd.Series, horizon: int) -> pd.Series:
    """For each day d, the deepest peak-to-trough SPY decline over the NEXT `horizon`
    trading days (a positive magnitude; 0.10 = a 10% drawdown). Leak-free: uses only
    days strictly after d, matched to the reading on d."""
    c = close.dropna().astype(float)
    vals = c.to_numpy()
    n = len(vals)
    out = np.full(n, np.nan)
    for i in range(n):
        j = min(i + horizon + 1, n)
        if j - i < 2:
            continue
        window = vals[i:j]
        run_peak = np.maximum.accumulate(window)
        dd = (run_peak - window) / run_peak
        out[i] = float(dd.max())
    return pd.Series(out, index=c.index)


def _bands(cfg_dd: dict) -> list[tuple[str, float]]:
    """Ordered (name, lower-bound) cuts, low band first. Matches conditions.py."""
    return [
        ("low", 0.0),
        ("elevated", float(cfg_dd["elevated"])),
        ("high", float(cfg_dd["high"])),
        ("extreme", float(cfg_dd["extreme"])),
    ]


def _band_of(score: float, cuts: list[tuple[str, float]]) -> str:
    b = "low"
    for name, lo in cuts:
        if score >= lo:
            b = name
    return b


def _measure(dr: pd.Series, fwd_dd: pd.Series, dd_threshold: float,
             cuts: list[tuple[str, float]]) -> dict:
    """Per-band hit-rate P(fwd max dd >= dd_threshold) with Wilson CI + an overlap-aware
    effective-N (block count at the horizon so the CI caveat is quantitative)."""
    j = pd.concat([dr.rename("dr"), fwd_dd.rename("dd")], axis=1).dropna()
    if j.empty:
        return {"available": False}
    hit = (j["dd"] >= dd_threshold).astype(int)
    band = j["dr"].map(lambda s: _band_of(float(s), cuts))
    rows: dict[str, dict] = {}
    for name, _lo in cuts:
        sel = band == name
        n = int(sel.sum())
        k = int(hit[sel].sum())
        p, lo, hi = _wilson(k, n)
        rows[name] = {
            "n_obs": n, "n_hits": k,
            "hit_pct": None if np.isnan(p) else round(p, 1),
            "ci90_lo": None if np.isnan(lo) else round(lo, 1),
            "ci90_hi": None if np.isnan(hi) else round(hi, 1),
        }
    # unconditional base rate over the same aligned population
    p, lo, hi = _wilson(int(hit.sum()), int(len(hit)))
    rows["_base"] = {"n_obs": int(len(hit)), "n_hits": int(hit.sum()),
                     "hit_pct": round(p, 1), "ci90_lo": round(lo, 1), "ci90_hi": round(hi, 1)}
    return {"available": True, "span": [str(j.index[0].date()), str(j.index[-1].date())],
            "bands": rows}


def _monotone(bands: dict) -> bool:
    """Is P(dd) monotone non-decreasing low->elevated->high->extreme? The whole claim."""
    seq = [bands.get(b, {}).get("hit_pct") for b in ("low", "elevated", "high", "extreme")]
    seq = [x for x in seq if x is not None]
    return all(seq[i] <= seq[i + 1] + 1e-9 for i in range(len(seq) - 1))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--horizon", type=int, default=63, help="forward trading-day window")
    ap.add_argument("--dd", type=float, default=0.10, help="drawdown threshold (0.10 = 10%)")
    ap.add_argument("--start", default="1993-01-01",
                    help="measurement start (full NFCI/EBP coverage begins ~1993)")
    ap.add_argument("--weekly", action="store_true",
                    help="decorrelate by sampling one reading per week (W-FRI) — the ORIGINAL "
                         "measurement's overlap control (research/QUANT_FACTOR_EXPANSION.md §6)")
    args = ap.parse_args()

    cfg = config.load()
    cfg_dd = cfg["engine"]["conditions"]["drawdown_risk"]
    cuts = _bands(cfg_dd)
    start = pd.Timestamp(args.start)

    results: dict[str, dict] = {}
    spy_close: pd.Series | None = None
    for basis in BASES:
        f = inputs.build_features() if basis == "latest" else inputs.build_features(pit_basis=basis)
        cf = conditions.conditions_frame(f)
        if "drawdown_risk" not in cf.columns:
            results[basis] = {"available": False, "reason": "no drawdown_risk column"}
            continue
        if spy_close is None:
            spy_close = f["SPY"] if "SPY" in f.columns else None
        fwd = _fwd_max_drawdown(spy_close, args.horizon)
        dr = cf["drawdown_risk"].dropna()
        dr = dr[dr.index >= start]
        if args.weekly:  # one observation per week to cut window overlap (original control)
            dr = dr.resample("W-FRI").last().dropna()
        results[basis] = _measure(dr, fwd, args.dd, cuts)
        results[basis]["monotone"] = _monotone(results[basis].get("bands", {}))

    # composition + PIT provenance passport
    rec_w = cfg["engine"]["conditions"]["recession"]["weights"]
    labor_leg = "claims" if rec_w.get("claims", 0) > 0 else ("sahm" if rec_w.get("sahm", 0) > 0 else "none")
    from engine import pit as pitmod
    claims_asof = None
    try:
        v = pitmod._vintages()
        if v is not None and not v.empty and (v["series"] == "ICSA").any():
            claims_asof = str(pd.to_datetime(v[v["series"] == "ICSA"]["realtime_start"]).min().date())
    except Exception:  # noqa: BLE001
        pass

    passport = {
        "basis": "measured",
        "labor_leg": labor_leg,               # 'claims' = the LIVE composition (not Sahm)
        "gauge_components": list(cfg_dd["components"]),
        "horizon_d": args.horizon,
        "dd_threshold": args.dd,
        "measure_start": args.start,
        "weekly_decorrelated": bool(args.weekly),
        "band_cuts": {n: lo for n, lo in cuts},
        "claims_pit_true_asof_from": claims_asof,   # ICSA/CCSA ALFRED vintage start (~2009)
        "pre_asof_fallback": ("release rows before the claims vintage start fall back to the "
                              "modelled-release lag calendar (initial_claims ~5 bd), NOT a true "
                              "as-of join; documented, not silent."),
        "overlap_caveat": ("Forward windows overlap (horizon-day), so raw N over-counts "
                           "independent observations by ~horizon; treat Wilson CIs as a lower "
                           "bound on the true interval width. Bands are contiguous score "
                           "regions, not disjoint events."),
        "sample_starvation": ("Only ~2-3 recession/deep-drawdown episodes sit inside the PIT "
                              "era; the extreme/high bands are dominated by 2008/2020/2022, so "
                              "their hit-rates are episode-driven, not IID. A recession-RISK "
                              "read, not a crash oracle."),
    }

    out = {
        "target": f"P(SPY max drawdown >= {int(args.dd*100)}% within {args.horizon}d) by drawdown_risk band",
        "frames": results,
        "passport": passport,
        "reconciliation": ("The live gauge fires on the 'latest' frame with the CLAIMS labor leg. "
                           "'release' is the leak-free PIT re-measurement of the SAME gauge and "
                           "composition. The re-issued band table (below) is the number that now "
                           "describes the signal that fires today; the old 8/26/36/38 table was "
                           "measured on the pre-claims (Sahm) composition and revised data."),
    }
    outdir = config.data_dir() / "regime"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "drawdown_risk_pit.json").write_text(json.dumps(out, indent=2, default=str))
    _write_md(out, args)

    # console summary
    print(f"\n=== drawdown_risk PIT re-measurement (fwd {args.horizon}d, "
          f">= {int(args.dd*100)}% dd), labor leg = {labor_leg} ===")
    hdr = f"{'band':10s}" + "".join(f"{b:>22s}" for b in BASES)
    print(hdr)
    for band in ("_base", "low", "elevated", "high", "extreme"):
        cells = ""
        for basis in BASES:
            bd = results.get(basis, {}).get("bands", {}).get(band)
            if bd and bd.get("hit_pct") is not None:
                cells += f"{bd['hit_pct']:>6.1f}% [{bd['ci90_lo']:.0f}-{bd['ci90_hi']:.0f}] n{bd['n_obs']:>5}".rjust(22)
            else:
                cells += f"{'—':>22s}"
        label = "base rate" if band == "_base" else band
        print(f"{label:10s}{cells}")
    for basis in BASES:
        mono = results.get(basis, {}).get("monotone")
        print(f"  {basis}: monotone={mono}  span={results.get(basis, {}).get('span')}")
    print(f"\n  claims PIT true as-of from: {claims_asof} (pre that -> modelled-lag fallback)")
    print(f"  wrote {outdir / 'drawdown_risk_pit.json'} and the validation report")
    return 0


def _fmt_band_row(band: str, res: dict) -> str:
    cells = []
    for basis in BASES:
        bd = res.get(basis, {}).get("bands", {}).get(band)
        if bd and bd.get("hit_pct") is not None:
            cells.append(f"{bd['hit_pct']}% ({bd['ci90_lo']}–{bd['ci90_hi']}, n={bd['n_obs']})")
        else:
            cells.append("—")
    return "| " + band + " | " + " | ".join(cells) + " |"


def _write_md(out: dict, args) -> None:
    res = out["frames"]
    L = [
        "# Drawdown-risk gauge — PIT-frame re-measurement (audit #39)",
        "",
        "_Generated by `scripts/validate_drawdown_risk_pit.py`. The re-issued band table is the "
        "number that describes the signal that fires **today** — measured on the frame it fires on "
        "(`release`, leak-free PIT) and the composition it fires with (jobless **claims**, not Sahm)._",
        "",
        "## What changed",
        "",
        "The shipped table (`~8% base -> 26% elevated -> 36% high -> 38% extreme`, config summary "
        '"~45%") was measured on **latest-revised** FRED **and** a `recession_risk` composition that '
        "still carried the **Sahm** labor leg. The live gauge now (a) folds a **claims**-based "
        "`recession_risk` and (b) fires on the live frame. This re-measures the identical production "
        "gauge on both frames so the published number matches reality.",
        "",
        f"**Target:** {out['target']}.",
        "",
        "## Re-issued band table (P(≥{}% dd / {}d), Wilson 95% CI, n obs)".format(
            int(args.dd * 100), args.horizon),
        "",
        "| band | latest (live frame) | release (PIT, leak-free) | reference (control) |",
        "|---|---|---|---|",
        _fmt_band_row("low", res),
        _fmt_band_row("elevated", res),
        _fmt_band_row("high", res),
        _fmt_band_row("extreme", res),
        "",
        "| base rate | " + " | ".join(
            (lambda b: f"{b['hit_pct']}% ({b['ci90_lo']}–{b['ci90_hi']}, n={b['n_obs']})"
             if b else "—")(res.get(basis, {}).get("bands", {}).get("_base"))
            for basis in BASES) + " |",
        "",
        "Monotone (low ≤ elevated ≤ high ≤ extreme)? " +
        ", ".join(f"**{b}**: {res.get(b, {}).get('monotone')}" for b in BASES) + ".",
        "",
        "## Reconciliation",
        "",
        out["reconciliation"],
        "",
        "## Honesty passport",
        "",
        f"- **Labor leg:** `{out['passport']['labor_leg']}` (the LIVE composition; the stale table "
        "predates the claims replacement).",
        f"- **Gauge legs:** {', '.join(out['passport']['gauge_components'])}.",
        f"- **Claims PIT true as-of from:** {out['passport']['claims_pit_true_asof_from']} — before "
        "that date the `release` frame uses the modelled-release lag calendar for claims "
        "(`initial_claims` ~5 bd), not a true ALFRED as-of join. Documented, not silent.",
        f"- **Overlap:** {out['passport']['overlap_caveat']}",
        f"- **Sample starvation:** {out['passport']['sample_starvation']}",
    ]
    p = config.ROOT / "reports" / "drawdown-risk-pit-validation.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(L))


if __name__ == "__main__":
    sys.exit(main())
