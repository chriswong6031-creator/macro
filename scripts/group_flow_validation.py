"""Thematic flow detector — RIGOROUS Phase-0 that PRODUCES the verdict metadata.

Writes data/group_flow/validation_meta.json. engine.group_flow reads from it the VERDICT,
the basket_confidence_cap, the cohesion_gate spec, the survivorship_gap and the AI-handoff
caveats/residual_risks — i.e. the HONESTY scaffolding. It deliberately does NOT read leg
weights: flow_score is a DESCRIPTIVE concentration blend (fixed weights in engine _DEFAULTS),
never a forecast, so this file ships `forecast_weights` all-zero to make that explicit. The
grounded fact this file establishes is the VERDICT (display_only) + the measured/de-confounded
cohesion IC, not a calibrated forecast. Three panels:

  PANEL A  11 GICS sectors, POINT-IN-TIME membership (survivorship-free + no
           current-snapshot look-ahead) — the clean integrity anchor (low power).
  PANEL B  ~1000 individual names, each carrying its OWN sector's flow leg, labelled
           by the name's forward return vs SPY — the high-power confirmation.
  PANEL C  the 15 hindsight-curated baskets run IDENTICALLY — an explicit
           SURVIVORSHIP PROBE; survivorship_gap = IC_basket - IC_sector is shipped as
           a caveat and a hard confidence cap, never as edge.

Stats reuse engine.validation verbatim (Newey-West HAC IC t-stats, Benjamini-Hochberg
FDR across the leg x horizon family). A leg is "validated" only if it clears BH on the
UNBIASED universe with the thesis sign; otherwise weight 0. Shallow ~3y cache, so this
is a go/no-go directional read, honestly caveated — not a deflated-Sharpe claim.
"""
from __future__ import annotations

import json
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from engine import group_flow as gf  # noqa: E402
from engine import validation as V  # noqa: E402
from engine.equity_factors import _names_sectors  # noqa: E402
from lib import config, store  # noqa: E402

LEGS = ["accel_z", "broadening_z", "cohesion_chg", "persistence", "flow_score"]
HORIZONS = (20, 60)
STEP = 21
THESIS_SIGN = {lg: +1 for lg in LEGS}     # all legs are framed risk-on-positive


def _xs_spear(a: dict, b: dict, minn: int = 6) -> float:
    j = pd.concat([pd.Series(a), pd.Series(b)], axis=1).dropna()
    if len(j) < minn:
        return float("nan")
    return float(j.iloc[:, 0].rank().corr(j.iloc[:, 1].rank()))


def _setup():
    s = gf._setup()
    return s


def _panel_ic(groups: dict, bench: pd.Series, idx, c: dict) -> dict:
    """groups: {id: (prep, level)} -> {leg: {h: ic_summary}} via per-date cross-sectional IC."""
    start = max(c["min_history_d"], c["z_lookback_d"])
    n = len(idx)
    ics = {lg: {h: [] for h in HORIZONS} for lg in LEGS}
    for i in range(start, n - max(HORIZONS), STEP):
        legvals = {lg: {} for lg in LEGS}
        fwd = {h: {} for h in HORIZONS}
        for gid, (prep, lvl) in groups.items():
            fp = gf.fingerprint_at(prep, i, c)
            if not fp or fp["flow_score"] is None:
                continue
            for lg in LEGS:
                if fp.get(lg) is not None:
                    legvals[lg][gid] = fp[lg]
            li, bi = lvl.iloc[i], bench.iloc[i]
            for h in HORIZONS:
                lf, bf = lvl.iloc[i + h], bench.iloc[i + h]
                if pd.notna(li) and pd.notna(lf):
                    fwd[h][gid] = (lf / li - 1.0) - (bf / bi - 1.0)
        for lg in LEGS:
            for h in HORIZONS:
                ic = _xs_spear(legvals[lg], fwd[h])
                if pd.notna(ic):
                    ics[lg][h].append(ic)
    return {lg: {h: V.ic_summary(ics[lg][h], periods_per_year=12) for h in HORIZONS}
            for lg in LEGS}


def _panel_b_namelevel(sector_groups: dict, closes, bench, idx, c: dict) -> dict:
    """High-power name-level panel: every name inherits its sector's leg value; the
    label is the name's forward return vs SPY. rank_ic across ~1000 names per date."""
    ns = _names_sectors()
    name_sector = {t: s for t, (_n, s) in ns.items() if s and s != "—"}
    start = max(c["min_history_d"], c["z_lookback_d"])
    n = len(idx)
    legs_b = ["accel_z", "flow_score"]
    ics = {lg: {h: [] for h in HORIZONS} for lg in legs_b}
    for i in range(start, n - max(HORIZONS), STEP):
        sleg = {lg: {} for lg in legs_b}
        for s, (prep, _lvl) in sector_groups.items():
            fp = gf.fingerprint_at(prep, i, c)
            if not fp:
                continue
            for lg in legs_b:
                if fp.get(lg) is not None:
                    sleg[lg][s] = fp[lg]
        bi = bench.iloc[i]
        for h in HORIZONS:
            bf = bench.iloc[i + h]
            sig = {lg: {} for lg in legs_b}
            lab = {}
            for t, sct in name_sector.items():
                if t not in closes.columns:
                    continue
                pi, pf = closes[t].iloc[i], closes[t].iloc[i + h]
                if pd.isna(pi) or pd.isna(pf):
                    continue
                lab[t] = (pf / pi - 1.0) - (bf / bi - 1.0)
                for lg in legs_b:
                    if sct in sleg[lg]:
                        sig[lg][t] = sleg[lg][sct]
            for lg in legs_b:
                ic = V.rank_ic(pd.Series(sig[lg]), pd.Series(lab))
                if pd.notna(ic):
                    ics[lg][h].append(ic)
    return {lg: {h: V.ic_summary(ics[lg][h], periods_per_year=12) for h in HORIZONS}
            for lg in legs_b}


def _cohesion_deconf_ic(sec_groups: dict, bench, idx, c: dict) -> dict:
    """Cross-sectionally residualize cohesion_chg on each group's trailing 20d AND 60d
    return per date, then IC of the RESIDUAL vs forward rel. Strips the reversal/stress
    confound the adversarial review flagged: raw 60d cohesion IC is largely a reversal
    proxy (collapses to ~+0.03, p~0.56 residualized); the 20d only partially survives
    (~+0.10, p~0.04). This is the HONEST magnitude to calibrate confidence on."""
    start = max(c["min_history_d"], c["z_lookback_d"])
    n = len(idx)
    out = {}
    for h in HORIZONS:
        ics = []
        for i in range(start, n - h, STEP):
            coh, tr20, tr60, fwd = {}, {}, {}, {}
            for gid, (prep, lvl) in sec_groups.items():
                fp = gf.fingerprint_at(prep, i, c)
                if not fp or fp.get("cohesion_chg") is None or i - 60 < 0:
                    continue
                li, lf = lvl.iloc[i], lvl.iloc[i + h]
                l20, l60 = lvl.iloc[i - 20], lvl.iloc[i - 60]
                if any(pd.isna(v) for v in (li, lf, l20, l60)):
                    continue
                coh[gid] = fp["cohesion_chg"]; tr20[gid] = li / l20 - 1; tr60[gid] = li / l60 - 1
                fwd[gid] = (lf / li - 1.0) - (bench.iloc[i + h] / bench.iloc[i] - 1.0)
            if len(coh) >= 6:
                df = pd.DataFrame({"c": coh, "t20": tr20, "t60": tr60, "f": fwd}).dropna()
                if len(df) >= 6:
                    X = np.column_stack([np.ones(len(df)), df["t20"].to_numpy(), df["t60"].to_numpy()])
                    beta = np.linalg.lstsq(X, df["c"].to_numpy(), rcond=None)[0]
                    resid = pd.Series(df["c"].to_numpy() - X @ beta)
                    ic = resid.rank().corr(pd.Series(df["f"].to_numpy()).rank())
                    if pd.notna(ic):
                        ics.append(ic)
        out[h] = V.ic_summary(ics, periods_per_year=12)
    return out


# Adversarial-review caveats (workflow ruling: PARTIAL) that MUST travel with the
# signal so the downstream AI layer cannot over-trust it. See reports + meta.
_COHESION_CAVEATS = [
    "Horizon: only the ~20d read carries de-confounded signal; the 60d claim is a sector reversal/stress proxy (collapses to ~+0.03, p~0.56 once orthogonalized on trailing return). Never use the 60d number.",
    "Magnitude: the honest de-confounded IC is ~+0.10 (p~0.04, marginal), NOT the raw +0.164 — the raw figure is ~2.4x inflated by a handful of stress dates (median per-date IC only +0.068).",
    "Fragility: significance hinges on a few stress cross-sections; dropping the single best date takes p from 0.004 to 0.071, and the hit rate is a coin-flip 56.5%. Right rarely but hugely, not a per-month edge.",
    "Regime: the edge is stress-conditional (high-VIX IC +0.236 vs calm +0.099 insignificant). It reads as stress-driven dispersion/rotation-recovery, NOT 'coordinated inflows forming'. Condition any read on the VIX/stress regime.",
    "Sample: ~1.8y effective window, n=23 overlapping monthly cross-sections of 11 sectors, edge concentrated in calendar 2025. Durability out-of-one-year is UNPROVEN — reconfirm as 2026+ accrues.",
    "Multiple testing: clears BH-FDR only under a narrow 10-member family; at an honest ~90-trial count the adjusted p climbs to 0.5-1.0. Do not infer reliability from the headline t-stat.",
    "Scope: GICS-sector-specific. It dies off the sector axis (size buckets null-to-wrong-signed) and is ~0 on the hindsight baskets (survivorship_gap -0.165). NOT a transferable 'members move together' law for arbitrary themes.",
]
_RESIDUAL_RISKS = [
    "The clean 20d residual edge could itself be a longer-window (120d+) reversal/momentum-crash component the 20d/60d controls did not remove.",
    "Single 2023-2026 macro regime — the whole effect may be a property of this regime; untestable on a 3y close-only cache.",
    "Close-only (no volume): a true coordinated-inflow mechanism cannot be confirmed; cohesion may be capturing factor-beta compression in stress, not flow.",
    "Largely a stress proxy — if combined later with the dashboard's existing VIX/stress signals it may be redundant (double-count risk).",
]


def main() -> None:
    c = gf._cfg()
    s = _setup()
    if s is None:
        print("no data — abort")
        return
    closes, rets, idx, bench = s["closes"], s["rets"], s["idx"], s["bench"]
    print("=" * 80)
    print("THEMATIC FLOW — rigorous Phase-0 (produces validation_meta.json)")
    print(f"history {str(idx.min())[:10]}..{str(idx.max())[:10]} | {closes.shape[1]} names | step {STEP}d")
    print("=" * 80)

    # Panel A — PIT GICS sectors
    pit = gf._pit_sector_frames(closes, rets, c)
    sec_groups = {}
    for sct, fr in pit.items():
        prep = gf.prep_group(fr["members_closes"], fr["level"], bench, c)
        if prep is not None:
            sec_groups[sct] = (prep, fr["level"])
    # Panel C — baskets
    mem = s["mem"]["baskets"]
    items = mem.items() if isinstance(mem, dict) else [(b["id"], b) for b in mem]
    bas_groups = {}
    for bid, b in items:
        present = [m["ticker"] for m in b.get("members", []) if m["ticker"] in rets.columns]
        if len(present) < 3:
            continue
        lvl = gf._ew_level(rets, b["members"], idx)
        if lvl.dropna().empty:
            continue
        prep = gf.prep_group(closes[present], lvl, bench, c)
        if prep is not None:
            bas_groups[bid] = (prep, lvl)

    print(f"Panel A: {len(sec_groups)} PIT sectors | Panel C: {len(bas_groups)} baskets")
    sector = _panel_ic(sec_groups, bench, idx, c)
    basket = _panel_ic(bas_groups, bench, idx, c)
    name = _panel_b_namelevel(sec_groups, closes, bench, idx, c)

    def _f(d):
        return f"{d.get('mean_ic'):+.3f}(t{d.get('t_hac')},p{d.get('p_hac')},n{d.get('n')})" if d.get("mean_ic") is not None else f"n={d.get('n')}"
    print("\n--- PANEL A (unbiased PIT sectors) cross-sectional IC ---")
    for lg in LEGS:
        print(f"  {lg:>13} 20d {_f(sector[lg][20])}   60d {_f(sector[lg][60])}")
    print("--- PANEL B (name-level, high power) ---")
    for lg in name:
        print(f"  {lg:>13} 20d {_f(name[lg][20])}   60d {_f(name[lg][60])}")
    print("--- PANEL C (baskets — survivorship probe) ---")
    for lg in LEGS:
        print(f"  {lg:>13} 20d {_f(basket[lg][20])}   60d {_f(basket[lg][60])}")

    # de-confounded cohesion IC (strips the reversal/stress proxy the review flagged)
    deconf = _cohesion_deconf_ic(sec_groups, bench, idx, c)

    pvals = {f"{lg}@{h}": sector[lg][h]["p_hac"] for lg in LEGS for h in HORIZONS
             if sector[lg][h].get("p_hac") is not None}
    bh = V.benjamini_hochberg(pvals, alpha=0.10)

    surv_gap = {}
    for lg in LEGS:
        sb, ss = basket[lg][20].get("mean_ic"), sector[lg][20].get("mean_ic")
        if sb is not None and ss is not None:
            surv_gap[lg] = round(sb - ss, 4)

    # HONEST verdict (adversarial ruling = PARTIAL): NO leg earns a forecast weight.
    # cohesion_chg clears the naive BH but FAILS de-confounding + honest multiple-testing,
    # so it ships as a stress-conditional CONTEXT GATE, not a scored leg; every other leg
    # is noise/anti-predictive. flow_score is therefore a DESCRIPTIVE concentration map
    # (validated=false), never a return forecast.
    weights = {lg: 0.0 for lg in LEGS if lg != "flow_score"}
    cohesion_gate = {
        "use": "context_gate", "regime": "stress_conditional", "horizon_d": 20, "tier": "low",
        "raw_ic_20d": sector["cohesion_chg"][20].get("mean_ic"),
        "deconf_ic_20d": deconf[20].get("mean_ic"), "deconf_t_20d": deconf[20].get("t_hac"),
        "deconf_p_20d": deconf[20].get("p_hac"),
        "deconf_ic_60d": deconf[60].get("mean_ic"), "deconf_p_60d": deconf[60].get("p_hac"),
    }
    verdict = "display_only"
    meta = {
        "schema": "group_flow_validation.v2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "as_of": str(idx.max())[:10], "history_start": str(idx.min())[:10],
        "n_names": int(closes.shape[1]), "step_d": STEP, "horizons": list(HORIZONS),
        "verdict": verdict, "validated_forecast_legs": [], "forecast_weights": weights,
        "cohesion_gate": cohesion_gate,
        "panel_sector": sector, "panel_name": name, "panel_basket": basket,
        "bh_family": bh, "survivorship_gap_20d": surv_gap,
        "basket_confidence_cap": 0.55, "calibrated": False,
        "panel_name_caveat": ("panel_name uses current GICS labels + cache-presence "
                              "(not PIT-restricted) — a descriptive power illustration "
                              "only; does not affect the display_only verdict."),
        "cohesion_caveats": _COHESION_CAVEATS, "residual_risks": _RESIDUAL_RISKS,
        "note": ("Unbiased-universe (PIT GICS sector) verdict, adversarially reviewed "
                 "(ruling: PARTIAL). No leg earns a forecast weight: momentum legs are "
                 "noise/anti-predictive; cohesion_chg is a real-but-modest, "
                 "stress-conditional, sector-only SHORT-horizon residual effect -> a "
                 "CONTEXT GATE, never a scored leg. flow_score = descriptive concentration "
                 "map only. Detection, not prediction."),
    }
    outdir = config.data_dir() / "group_flow"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "validation_meta.json").write_text(json.dumps(meta, indent=2, default=str))

    print(f"\ncohesion raw 20d IC {sector['cohesion_chg'][20].get('mean_ic')} -> deconf "
          f"{deconf[20].get('mean_ic')} (t{deconf[20].get('t_hac')}, p{deconf[20].get('p_hac')})")
    print(f"cohesion deconf 60d IC {deconf[60].get('mean_ic')} (p{deconf[60].get('p_hac')}) [reversal proxy]")
    print(f"survivorship_gap (basket-sector, 20d): {surv_gap}")
    print(f"weights (forecast): {weights}  | VERDICT: {verdict}")
    print(f"wrote {outdir/'validation_meta.json'}")


if __name__ == "__main__":
    main()
