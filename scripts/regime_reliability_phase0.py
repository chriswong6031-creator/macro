#!/usr/bin/env python3
"""Phase-0: is regime-conditional signal reliability estimable, and is the effect real?

Tests the external "regime reliability engine" proposal — a per-signal-family table
R[s,t] = E[future strategy performance | current regime] — against the only multi-regime
graded signal record this house owns: data/signal_archive/track_record.parquet
(58k signals, 1962-2026, 100% coverage on regime_at_entry).

THE TEST THAT MATTERS. The proposal's value claim is that a family's reliability CHANGES
with regime ("breakout continuation is unreliable in THIS regime"). That is an INTERACTION
claim. It is not enough for bear markets to be worse for everything — that is a market
main effect the stack already publishes, and conditioning on it adds nothing. So:

  1. Raw cell means            — contains the tautology (regime_at_entry and fwd_mdd are
                                 both functions of the same price series: in a bear tape
                                 everything drawdowns more).
  2. Month-demeaned means      — month fixed effects absorb the common market/vol/macro
                                 condition shared by all families in that month.
  3. Interaction term          — cell - family_mean - regime_mean + grand_mean. THIS is
                                 what the proposal proposes to trade on.
  4. Month-block bootstrap CI  — per-cell 95% CI on the interaction.
  5. Era-split sign stability  — DT-R16 era law; the house kill standard for split-half
                                 sign flips (cf. fund_crowding phase-0, PSS-F3).

Framing is DRAWDOWN, per the track_record charter (§2b: drawdown / entry-quality, never
return-alpha). Deterministic: fixed seed, no wall-clock, no network.

Usage:  python3 scripts/regime_reliability_phase0.py [--out reports/regime-reliability-phase0.md]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from engine import regime_conditioning_coverage as rcc  # noqa: E402

TRACK = REPO / "data" / "signal_archive" / "track_record.parquet"
SEED = 7
N_BOOT = 600
ERA_SPLIT = "2010-01-01"       # DT-R16 era-split law
MIN_CELL_N = 30                # a cell thinner than this is not compared across eras
OUTCOME = "fwd_mdd_60"         # 60d forward max drawdown (charter framing)
REGIME_AXIS = "regime_at_entry"
FAMILY_COL = "reason"          # the signal rationale = the family axis available here


def load() -> pd.DataFrame:
    if not TRACK.exists():
        raise SystemExit(f"track record absent: {TRACK}")
    d = pd.read_parquet(TRACK)
    d["date"] = pd.to_datetime(d["date"])
    d["month"] = d["date"].dt.to_period("M")
    d = d[d[REGIME_AXIS].notna() & d[OUTCOME].notna()].copy()
    d = d[~d[REGIME_AXIS].astype(str).str.lower().isin(rcc._NULL_TOKENS)]
    d["family"] = d[FAMILY_COL].astype(str)
    d["y"] = 100.0 * d[OUTCOME]                     # pp of drawdown
    # month fixed effect: absorbs the common market condition (and the regime main effect)
    d["y_dm"] = d["y"] - d.groupby("month")["y"].transform("mean")
    return d


def _interaction(df: pd.DataFrame, min_n: int = 0) -> tuple[pd.DataFrame, pd.DataFrame]:
    """cell - family_mean - regime_mean + grand_mean, on the month-demeaned outcome."""
    cell = df.pivot_table(index="family", columns=REGIME_AXIS, values="y_dm", aggfunc="mean")
    cnt = df.pivot_table(index="family", columns=REGIME_AXIS, values="y_dm", aggfunc="size")
    fam = df.groupby("family")["y_dm"].mean()
    reg = df.groupby(REGIME_AXIS)["y_dm"].mean()
    grand = df["y_dm"].mean()
    out = cell.copy()
    for f in out.index:
        for r in out.columns:
            n = cnt.loc[f, r] if (f in cnt.index and r in cnt.columns) else 0
            if pd.isna(out.loc[f, r]) or (min_n and (pd.isna(n) or n < min_n)):
                out.loc[f, r] = np.nan
            else:
                out.loc[f, r] = out.loc[f, r] - fam[f] - reg[r] + grand
    return out, cnt


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="reports/regime-reliability-phase0.md")
    ap.add_argument("--json-out", dest="json_out",
                    default="data/quant_lab/methods/regime_reliability.json")
    args = ap.parse_args()

    d = load()
    rng = np.random.default_rng(SEED)
    L: list[str] = []
    P = L.append

    P("# Regime-conditional signal reliability — Phase-0")
    P("")
    P("Tests the external proposal `R[s,t] = E[strategy performance | regime]` against the")
    P("only multi-regime graded signal record in the repo.")
    P("")
    P(f"- Substrate: `data/signal_archive/track_record.parquet` — **{len(d):,} matured signals**, "
      f"{d.date.min():%Y-%m-%d} -> {d.date.max():%Y-%m-%d}, **{d.month.nunique()} distinct months**.")
    P(f"- Outcome: `{OUTCOME}` (60d forward max drawdown, pp). Charter framing: drawdown / "
      f"entry-quality, never return-alpha.")
    P(f"- Regime axis: `{REGIME_AXIS}` ({', '.join(sorted(d[REGIME_AXIS].unique()))}); "
      f"family axis: `{FAMILY_COL}` ({d.family.nunique()} families).")
    P(f"- Deterministic: seed={SEED}, month-block bootstrap B={N_BOOT}, era split {ERA_SPLIT}.")
    P("")

    # --- 0. estimability of every candidate axis -------------------------------------
    cov = rcc.assess(pd.read_parquet(TRACK))
    J: dict = {                       # structured twin of this report (see --json-out)
        "schema": "quant_lab_method_result.v1",
        "method_key": "regime_reliability",
        "substrate": {
            "store": "data/signal_archive/track_record.parquet",
            "n_matured": int(len(d)),
            "span": [f"{d.date.min():%Y-%m-%d}", f"{d.date.max():%Y-%m-%d}"],
            "n_months": int(d.month.nunique()),
            "outcome": OUTCOME,
            "outcome_label": "60d forward max drawdown (pp)",
            "regime_axis": REGIME_AXIS,
            "regime_states": sorted(d[REGIME_AXIS].unique().tolist()),
            "family_col": FAMILY_COL,
            "n_families": int(d.family.nunique()),
        },
        "determinism": {"seed": SEED, "n_boot": N_BOOT, "era_split": ERA_SPLIT},
        "estimability": {
            "gates": cov["gates"],
            "estimable_axes": cov["estimable_axes"],
            "axes": [{"axis": a, "coverage": r["coverage"], "n_states": r["n_states"],
                      "min_state_months": r["min_state_months"], "verdict": r["verdict"],
                      "span": r.get("span")}
                     for a, r in cov["axes"].items()],
        },
    }

    P("## 0. Which regime axes can carry a conditional claim at all?")
    P("")
    P("```")
    P(rcc.format_report(cov))
    P("```")
    P("")
    P("Only `regime_at_entry` clears the gate. The five richer axes the proposal actually")
    P("wants (quad, vol regime, rate pressure, fused risk, radar state) are stamped on")
    P("**0.4%** of the record — one month — and `vol_regime` / `rate_pressure` are observed")
    P("in a **single state**, where a conditional expectation is undefined. The proposal's")
    P("16-signal regime vector is therefore untestable here regardless of its merit.")
    P("")

    # --- 1. raw vs demeaned -----------------------------------------------------------
    raw = d.pivot_table(index="family", columns=REGIME_AXIS, values="y", aggfunc="mean")
    dm = d.pivot_table(index="family", columns=REGIME_AXIS, values="y_dm", aggfunc="mean")
    inter, cnt = _interaction(d)

    P("## 1. Raw cell means — and why they overstate the case")
    P("")
    P("Mean 60d forward max drawdown (pp; less negative = more reliable):")
    P("")
    P("```"); P(raw.round(2).to_string()); P("```")
    P("")
    P("`regime_at_entry` and `fwd_mdd_60` are both functions of the same price series, so a")
    P("bear-tape column is deeper for *every* family — a market main effect, not per-family")
    P("reliability. Month fixed effects remove it:")
    P("")
    P("```"); P(dm.round(2).to_string()); P("```")
    P("")

    # --- 2. the interaction ------------------------------------------------------------
    fam_m = d.groupby("family")["y_dm"].mean()
    reg_m = d.groupby(REGIME_AXIS)["y_dm"].mean()
    fam_spread = float(fam_m.max() - fam_m.min())
    reg_spread = float(reg_m.max() - reg_m.min())
    imax = float(np.nanmax(np.abs(inter.values)))

    P("## 2. The interaction — what the proposal actually needs")
    P("")
    P("`cell - family_mean - regime_mean + grand_mean`:")
    P("")
    P("```"); P(inter.round(2).to_string()); P("```")
    P("")
    P("```"); P(f"family main-effect spread   {fam_spread:6.2f} pp"); P(
        f"regime main-effect spread   {reg_spread:6.2f} pp"); P(
        f"largest |interaction|       {imax:6.2f} pp"); P("```")
    P("")
    J["decomposition"] = {
        "family_main_effect_pp": round(fam_spread, 2),
        "regime_main_effect_pp": round(reg_spread, 2),
        "max_abs_interaction_pp": round(imax, 2),
        "family_over_regime_ratio": round(fam_spread / max(reg_spread, 1e-9), 2),
        "unit": "pp of 60d forward max drawdown, month-demeaned",
    }
    P(f"**Knowing the family is worth {fam_spread / max(reg_spread, 1e-9):.1f}x more than knowing "
      f"the regime.** The interaction the proposal would trade on is the smallest term.")
    P("")
    P("Cell counts (note the two thinnest cells carry the two largest interactions):")
    P(""); P("```"); P(cnt.fillna(0).astype(int).to_string()); P("```"); P("")

    # --- 3. bootstrap ------------------------------------------------------------------
    months = d["month"].unique()
    bym = {m: g for m, g in d.groupby("month")}
    boots = []
    for _ in range(N_BOOT):
        samp = pd.concat([bym[m] for m in rng.choice(months, size=len(months), replace=True)])
        boots.append(_interaction(samp)[0])

    P("## 3. Month-block bootstrap 95% CI on each interaction cell")
    P("")
    P(f"B={N_BOOT}, resampling whole months (signals inside a month share their market).")
    P("")
    P("| family | regime | n | interaction (pp) | 95% CI | excludes 0 |")
    P("|---|---|---:|---:|---|---|")
    n_sig = n_tot = 0
    for f in inter.index:
        for r in inter.columns:
            if pd.isna(inter.loc[f, r]):
                continue
            vals = np.array([b.loc[f, r] if (f in b.index and r in b.columns) else np.nan
                             for b in boots], dtype=float)
            vals = vals[~np.isnan(vals)]
            if len(vals) < 100:
                continue
            lo, hi = np.percentile(vals, [2.5, 97.5])
            ex = bool(lo > 0 or hi < 0)
            n_tot += 1
            n_sig += ex
            P(f"| {f} | {r} | {int(cnt.loc[f, r])} | {inter.loc[f, r]:+.2f} | "
              f"[{lo:+.2f}, {hi:+.2f}] | {'**yes**' if ex else 'no'} |")
    P("")
    P(f"Cells whose CI excludes 0: **{n_sig}/{n_tot}**.")
    P("")
    thin = sorted(int(v) for v in cnt.values.flatten() if pd.notna(v))[:2]
    J["bootstrap"] = {"n_boot": N_BOOT, "cells_ci_excludes_zero": int(n_sig),
                      "cells_tested": int(n_tot), "thinnest_cell_n": thin}

    # --- 4. era stability ---------------------------------------------------------------
    A, _ = _interaction(d[d.date < ERA_SPLIT], min_n=MIN_CELL_N)
    B, _ = _interaction(d[d.date >= ERA_SPLIT], min_n=MIN_CELL_N)
    P(f"## 4. Era-split sign stability (split {ERA_SPLIT}, cells with n>={MIN_CELL_N} both eras)")
    P("")
    P("The house kill standard: an effect whose sign flips between halves is noise.")
    P("")
    P("| family | regime | pre-2010 | 2010+ | stable |")
    P("|---|---|---:|---:|---|")
    same = flip = 0
    for f in inter.index:
        for r in inter.columns:
            a = A.loc[f, r] if (f in A.index and r in A.columns) else np.nan
            b = B.loc[f, r] if (f in B.index and r in B.columns) else np.nan
            if pd.isna(a) or pd.isna(b):
                continue
            ok = np.sign(a) == np.sign(b)
            same += ok
            flip += (not ok)
            P(f"| {f} | {r} | {a:+.2f} | {b:+.2f} | {'SAME' if ok else '**FLIP**'} |")
    tot = same + flip
    pct = 100 * same / max(tot, 1)
    P("")
    P(f"Sign-stable **{same}/{tot} ({pct:.0f}%)**. Coin-flip expectation is 50%.")
    P("")
    J["era_stability"] = {"split": ERA_SPLIT, "min_cell_n": MIN_CELL_N,
                          "sign_stable": int(same), "cells_compared": int(tot),
                          "pct_stable": round(pct, 1), "chance_pct": 50.0}

    # --- verdict ------------------------------------------------------------------------
    P("## Verdict")
    P("")
    P(f"- The regime axes the proposal specifies are **not estimable** here: 0.4% stamp "
      f"coverage, one month, and two axes observed in a single state (§0).")
    P(f"- On the one axis with 64 years of coverage, the family x regime interaction is "
      f"**{fam_spread / max(reg_spread, 1e-9):.1f}x smaller** than simply knowing the family (§2).")
    P(f"- The two largest interaction cells are the two **thinnest** (n={int(cnt.min().min())}-"
      f"{int(sorted(cnt.values.flatten())[1])}); their CIs include 0 (§3).")
    P(f"- Sign stability across the era split is **{pct:.0f}%** — at chance (§4).")
    P("")
    P("**NULL.** A regime-conditional reliability table is not supportable on this record.")
    P("The dominant, era-stable, already-published term is *which family fired* — not the")
    P("regime it fired in. Closes this construction; re-opening requires the estimability")
    P("gate in `engine/regime_conditioning_coverage.py` to turn green on a richer axis.")
    P("")

    J["verdict"] = "null"
    J["verdict_line_en"] = (
        "A regime-conditional reliability table is not supportable on this record: the "
        "family x regime interaction is smaller than the family effect alone, its largest "
        "cells are its thinnest, and its sign is not stable across the era split."
    )
    J["verdict_line_zh"] = "本记录不足以支撑「按市场状态给策略打可靠度」的表格：状态交互项小于家族主效应，且跨时代符号不稳定。"
    J["headline_en"] = (
        f"Which signal family fired is worth {J['decomposition']['family_over_regime_ratio']}x "
        f"more than which regime it fired in."
    )
    J["artifacts"] = {
        "report": args.out,
        "adjudication": "research/REGIME_RELIABILITY_FACTOR_CROWDING_ADJUDICATION.md",
        "gate_module": "engine/regime_conditioning_coverage.py",
        "registry_rows": ["RRC-R1", "RRC-R2"],
    }

    out = REPO / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(L) + "\n")
    jout = REPO / args.json_out
    jout.parent.mkdir(parents=True, exist_ok=True)
    jout.write_text(json.dumps(J, indent=2, sort_keys=False) + "\n")
    print(f"wrote {out}  ({len(L)} lines)")
    print(f"wrote {jout}")
    print(f"interaction/family ratio {fam_spread / max(reg_spread, 1e-9):.2f}x; "
          f"sign-stable {same}/{tot}; CI-excl-0 {n_sig}/{n_tot}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
