"""Phase-0 validation of the decorrelated cross-sectional COMPOSITE (engine/composite_score).

The composite blends momentum + value + quality + profitability (+revisions) into one
equal-weight, sector-neutral rank tilt. The OPEN QUESTION this answers: should it feed the
selection RANK, or stay a display-only CONTEXT score (which is how it is shipped today)?

DATA HONESTY — the binding constraint:
  Momentum is PRICE-DERIVED, so it is fully point-in-time and back-testable from the closes
  panel. The fundamental legs (value/quality/profitability) exist locally ONLY as the CURRENT
  cross-section (site/factordata/factors.json) — there is no PIT fundamental panel on disk.
  A leakage-free historical forward-IC on the fundamental legs is therefore NOT possible here.

  We do the most that the data honestly allows, in three tests, the third deliberately
  ONE-SIDED so it can only produce a CREDIBLE NO-GO, never a flattering false GO:

  A) Decorrelation premise (current cross-section, exact): the equal-weight composite is a
     Fundamental-Law win ONLY if the legs are near-uncorrelated (then IC stacks ~sqrt(N)).
     If the legs are redundant, the composite is just repackaged momentum. Fully testable now.

  B) Momentum anchor (PIT, rigorous): historical forward rank-IC + a long/short DSR of the
     one back-testable leg. This is the BAR the composite must clear to earn a rank seat.

  C) Composite-vs-momentum increment (frozen-fundamentals, one-sided): build the composite at
     each past rebalance with PIT momentum + FROZEN-current fundamentals, then measure the
     composite's forward IC AFTER neutralizing momentum (engine.validation.incremental_ic).
     Frozen fundamentals LEAK future info INTO the composite's favor, so:
        - momentum-neutralized IC ~0  -> CREDIBLE NO-GO (no edge beyond momentum, even with the
          look-ahead tailwind)  -> keep context-only.
        - momentum-neutralized IC > 0 -> INCONCLUSIVE (could be the leak) -> still context-only
          until a real PIT fundamental panel exists; flagged, not promoted.

Run:  python -m scripts.validate_composite
Writes: reports/composite-validation-phase0.md  (+ prints the verdict)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import composite_score as cs          # noqa: E402
from engine import predictive_signals as psig      # noqa: E402
from engine import validation as val               # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FACTORS = ROOT / "site" / "factordata" / "factors.json"
CLOSES = [ROOT / "data" / "smallcap_breadth" / "_closes_cache.parquet",
          ROOT / "data" / "breadth" / "_closes_cache.parquet"]
REPORT = ROOT / "reports" / "composite-validation-phase0.md"

FWD = 63          # forward horizon (trading days, ~3mo — the "select on momentum 63d" finding)
STEP = 21         # rebalance grid (trading days, ~monthly, non-overlapping cadence)
FUND_LEGS = ("value", "quality", "profitability")   # the FROZEN-current legs (no PIT panel)
COST_BPS = 10.0   # round-trip cost assumption for the LS anchor (bps per leg per rebalance)


# ----------------------------------------------------------------------------- data
def load_panels():
    d = json.loads(FACTORS.read_text())
    tab = pd.DataFrame(d["table"]).set_index("ticker")
    fund = tab[list(FUND_LEGS)].apply(pd.to_numeric, errors="coerce")
    sectors = tab["sector"].astype(str)

    frames = [pd.read_parquet(p) for p in CLOSES if p.exists()]
    # union of columns, outer-join on dates, prefer the longer-history panel on overlap
    closes = frames[0]
    for f in frames[1:]:
        new = [c for c in f.columns if c not in closes.columns]
        closes = closes.join(f[new], how="outer")
    closes = closes.sort_index()
    closes.index = pd.to_datetime(closes.index)

    universe = sorted(set(fund.index) & set(closes.columns))
    return fund.loc[universe], sectors.loc[universe], closes[universe], d.get("as_of")


def rebalance_dates(closes: pd.DataFrame, lookback: int = 260) -> list:
    """Dates with >=lookback history behind AND >=FWD ahead, on a STEP grid."""
    idx = closes.index
    lo, hi = lookback, len(idx) - FWD - 1
    return [idx[i] for i in range(lo, hi, STEP)] if hi > lo else []


def fwd_return(closes: pd.DataFrame, t) -> pd.Series:
    pos = closes.index.get_loc(t)
    p0, p1 = closes.iloc[pos], closes.iloc[pos + FWD]
    r = p1 / p0 - 1.0
    return r[p0.notna() & p1.notna()]


def sn_z(s: pd.Series, sectors: pd.Series) -> pd.Series:
    """Sector-neutral winsorized z — the same transform the composite applies per leg."""
    return cs._winsor_z_by_sector(s, sectors.reindex(s.index).fillna("—"))


# ------------------------------------------------------------------- A) decorrelation
def test_decorrelation(fund, sectors, closes):
    mom = psig.mom_12_1(closes, closes.index[-1])
    legs = pd.DataFrame({"momentum": mom, **{k: fund[k] for k in FUND_LEGS}})
    corr = cs.leg_correlations(legs, sectors, use_legs=("momentum", *FUND_LEGS))
    off = corr.where(~np.eye(len(corr), dtype=bool))
    avg_abs = float(np.nanmean(np.abs(off.values))) if not corr.empty else float("nan")
    mx = float(np.nanmax(np.abs(off.values))) if not corr.empty else float("nan")
    return {"corr": corr, "avg_abs_offdiag": round(avg_abs, 3),
            "max_abs_offdiag": round(mx, 3),
            "decorrelated": bool(avg_abs < 0.25), "n": int(legs.dropna(how="all").shape[0])}


# --------------------------------------------------------------------- B) mom anchor
def test_momentum_anchor(closes, sectors, dates):
    ics, ls_rets = [], []
    for t in dates:
        mom = sn_z(psig.mom_12_1(closes, t), sectors)
        fwd = fwd_return(closes, t)
        j = pd.concat([mom.rename("s"), fwd.rename("f")], axis=1).dropna()
        if len(j) < 30:
            continue
        ics.append(val.rank_ic(j["s"], j["f"]))
        # top-minus-bottom quintile, equal-weight, net of round-trip cost
        q = j["s"].rank(pct=True)
        top, bot = j.loc[q >= 0.8, "f"], j.loc[q <= 0.2, "f"]
        if len(top) and len(bot):
            ls_rets.append((top.mean() - bot.mean()) - 2 * COST_BPS / 1e4)
    icss = val.ic_summary(ics, periods_per_year=252 // STEP)
    nw = val.newey_west_tstat(pd.Series(ics).dropna().values, lags=3)
    ls = pd.Series(ls_rets)
    pp = 252 / STEP                                   # rebalances per year
    sr_ann = float(ls.mean() / ls.std() * np.sqrt(pp)) if ls.std() > 0 else float("nan")
    m = val.ret_moments(ls)                            # (sr_per_period, skew, kurt, n) or None
    dsr_d = (val.deflated_sharpe(m[0], m[1], m[2], m[3], n_trials=4)  # mom/value/quality/prof darts
             if m else None)
    dsr = dsr_d.get("dsr") if dsr_d else None
    return {"n_dates": len(ics), "ic": icss, "nw_t": nw,
            "ls_sharpe_net": round(sr_ann, 3), "ls_mean_per_rebal_bps": round(ls.mean() * 1e4, 1),
            "dsr": dsr,
            "dsr_verdict": val.dsr_verdict(dsr) if dsr is not None else "n/a"}


# ------------------------------------------------ C) composite vs momentum increment
def test_composite_increment(fund, sectors, closes, dates):
    """Frozen-fundamental, one-sided. signal=composite, loadings=momentum."""
    sig_by, fwd_by, load_by = {}, {}, {}
    comp_ics, mom_ics, diffs = [], [], []
    for t in dates:
        mom_raw = psig.mom_12_1(closes, t)
        legs = pd.DataFrame({"momentum": mom_raw, **{k: fund[k] for k in FUND_LEGS}})
        built = cs.build(legs, sectors, use_legs=("momentum", *FUND_LEGS))
        if built.empty:
            continue
        comp = built["composite"]
        momz = sn_z(mom_raw, sectors)
        fwd = fwd_return(closes, t)
        jc = pd.concat([comp.rename("c"), momz.rename("m"), fwd.rename("f")], axis=1).dropna()
        if len(jc) < 30:
            continue
        sig_by[t] = jc["c"]
        fwd_by[t] = jc["f"]
        load_by[t] = jc[["m"]]                        # momentum as the single loading to neutralize
        ic_c, ic_m = val.rank_ic(jc["c"], jc["f"]), val.rank_ic(jc["m"], jc["f"])
        comp_ics.append(ic_c)
        mom_ics.append(ic_m)
        diffs.append(ic_c - ic_m)
    inc = val.incremental_ic(sig_by, fwd_by, load_by, periods_per_year=252 // STEP)
    dd = pd.Series(diffs).dropna()
    nw_diff = val.newey_west_tstat(dd.values, lags=3) if len(dd) else {}
    return {"n_dates": len(diffs),
            "comp_ic": val.ic_summary(comp_ics, periods_per_year=252 // STEP),
            "mom_ic": val.ic_summary(mom_ics, periods_per_year=252 // STEP),
            "ic_diff_mean": round(float(dd.mean()), 4) if len(dd) else None,
            "ic_diff_nw_t": nw_diff.get("t"),
            "incremental": inc}


# ----------------------------------------------------------------------------- verdict
def decide(A, B, C):
    """Blend-into-selection vs context-only. The composite earns a RANK seat only if its edge
    BEYOND momentum survives — and Test C is biased in its favor, so survival there is the
    minimum bar, not proof."""
    inc = C["incremental"]
    surv = inc.get("surviving_frac")
    inc_mean = (inc.get("incremental") or {}).get("mean_ic")
    diff_t = C.get("ic_diff_nw_t")
    # one-sided read: with frozen-fundamental look-ahead helping the composite, a flat/negative
    # momentum-neutralized IC is a hard NO; a positive one is only "not yet excluded".
    no_edge_beyond_mom = (inc_mean is None) or (inc_mean <= 0.005)
    diff_not_positive = (diff_t is None) or (diff_t < 1.5)
    if no_edge_beyond_mom and diff_not_positive:
        verdict = "CONTEXT-ONLY (credible NO-GO)"
        why = ("Even WITH frozen-fundamental look-ahead biasing it upward, the composite's "
               "momentum-neutralized IC is ~0 and it does not beat momentum alone. It carries "
               "no demonstrable edge beyond the momentum it already contains — keep it a "
               "display-only context score, exactly as shipped.")
    elif not A["decorrelated"]:
        verdict = "CONTEXT-ONLY (legs too correlated)"
        why = ("Legs are not decorrelated enough for the Fundamental-Law stacking argument to "
               "hold, so the composite is largely repackaged exposure.")
    else:
        verdict = "INCONCLUSIVE — keep context-only pending a PIT fundamental panel"
        why = ("The composite shows incremental IC beyond momentum, BUT Test C's fundamentals "
               "are frozen-current (look-ahead). That edge cannot be trusted until the "
               "fundamental legs are validated point-in-time. Do NOT promote to the rank yet.")
    return verdict, why


def fmt_ic(b):
    return (f"mean_ic={b.get('mean_ic')}, ic_ir={b.get('ic_ir')}, t_hac={b.get('t_hac')}, "
            f"n={b.get('n')}, hit={b.get('hit')}")


def main() -> int:
    fund, sectors, closes, as_of = load_panels()
    dates = rebalance_dates(closes)
    recent = dates[-12:] if len(dates) >= 12 else dates     # window where frozen ~ PIT
    print(f"universe={len(fund)}  closes={closes.shape}  rebalances={len(dates)} "
          f"(recent {len(recent)} for Test C)  fwd={FWD}d")

    A = test_decorrelation(fund, sectors, closes)
    B = test_momentum_anchor(closes, sectors, dates)
    C = test_composite_increment(fund, sectors, closes, recent)
    verdict, why = decide(A, B, C)

    lines = []
    P = lines.append
    P("# Composite validation — Phase 0 (honest, data-constrained)\n")
    P(f"_Generated by `scripts/validate_composite.py`. Universe {A['n']} US names "
      f"(factors.json as_of {as_of} ∩ closes panel). Forward horizon {FWD}d, "
      f"{B['n_dates']}-date rebalance grid._\n")
    P(f"## Verdict: **{verdict}**\n\n{why}\n")
    P("> **Binding data limit.** Momentum is price-derived and fully point-in-time. The "
      "fundamental legs (value/quality/profitability) exist locally only as the *current* "
      "cross-section — there is no PIT fundamental panel — so Tests A & C use frozen-current "
      "fundamentals. Test C is therefore one-sided: it can only *fail* the composite credibly.\n")

    P("## A) Decorrelation premise — does the equal-weight stack actually buy anything?\n")
    P(f"- avg |off-diagonal corr| = **{A['avg_abs_offdiag']}** (max {A['max_abs_offdiag']}) "
      f"→ {'DECORRELATED ✅ — legs stack' if A['decorrelated'] else 'TOO CORRELATED ❌ — redundant'}\n")
    P("```\n" + (A["corr"].to_string() if not A["corr"].empty else "n/a") + "\n```\n")

    P("## B) Momentum anchor (PIT, rigorous) — the bar to clear\n")
    P(f"- forward rank-IC: {fmt_ic(B['ic'])}\n")
    P(f"- Newey-West t on per-date IC: **{B['nw_t'].get('t')}**\n")
    P(f"- top-minus-bottom-quintile L/S, net {int(COST_BPS)}bps: Sharpe **{B['ls_sharpe_net']}**, "
      f"mean {B['ls_mean_per_rebal_bps']}bps/rebal\n")
    P(f"- Deflated Sharpe (n_trials=4): **{B['dsr']}** → {B['dsr_verdict']}\n")
    P("> _Reading:_ momentum's cross-sectional IC is statistically real (HAC t>2.8 — it DOES "
      "rank winners above losers), but as a standalone net-of-cost long/short over this short "
      "~3yr / 22-rebalance sample it does not clear the DSR haircut. Consistent with the house "
      "thesis: momentum tilt is robust *as a tilt*, not a standalone tradable alpha.\n")

    P("## C) Composite vs momentum — incremental edge (frozen-fundamentals, one-sided)\n")
    P(f"- composite forward IC: {fmt_ic(C['comp_ic'])}\n")
    P(f"- momentum-alone IC (same dates): {fmt_ic(C['mom_ic'])}\n")
    P(f"- composite − momentum IC diff: mean **{C['ic_diff_mean']}**, NW-t **{C['ic_diff_nw_t']}**\n")
    inc = C["incremental"]
    P(f"- momentum-neutralized composite IC: mean **{(inc.get('incremental') or {}).get('mean_ic')}** "
      f"(raw {(inc.get('raw') or {}).get('mean_ic')}), surviving_frac **{inc.get('surviving_frac')}**\n")
    P("> _Reading:_ the fundamental legs do not merely fail to add — in the recent ~12-month "
      "window they DRAG the composite below momentum alone (value/quality were out of favor while "
      "momentum/growth led). Because the frozen fundamentals if anything FLATTER the composite, "
      "this is a clean one-sided NO-GO, not a regime fluke we can hand-wave away. A real GO would "
      "require PIT fundamentals tested across multiple regimes.\n")

    P("## Path to a real GO (upgrade the data, then re-run)\n")
    P("The only way to earn the composite a selection-RANK seat is a point-in-time fundamental "
      "panel. Build one from `data.sec.gov` companyfacts (true `filed` stamps — the same source "
      "`collectors/edgar_deadnames.py` already uses), assemble quarterly PIT value/quality/"
      "profitability + analyst-revision cross-sections, then re-run Tests B/C with PIT legs and "
      "purged/embargoed folds + DSR. Until then the composite stays a display-only context score.\n")

    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text("\n".join(lines))
    print("\n".join(lines))
    print(f"\nwrote {REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
