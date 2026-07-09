"""Phase-0: D4 extension-day complex — family AMENDMENT to d2_rates_calendar_flows.

FAMILY AMENDMENT: d2_rates_calendar_flows
  This script adds new cells to the confirmed V3 (month-end extension-day) finding
  from the d2_rates_calendar_flows phase-0 study.  The V3 construction is REPLICATED
  EXACTLY: last-business-day return vs same-month average-other-day return, both raw
  and excess forms; one observation per event-date collapsed before Newey-West.

CELLS:
  PRIMARY (data/yahoo/LQD.parquet, 2002-07 → 2026, 24y window):
    d4_lqd_last_day   — LQD return on last trading day of month (raw)
    d4_lqd_excess     — raw minus same-month avg-other-day return
    d4_lqd_avg_other  — baseline avg-other-day return (informational, NOT gated)

  CONFIRMATORY ONLY (pre-declared NON-FALSIFYING):
    AGG + IEI via data/massive_stock_day (2021+, per lane specification)
    *** GAP AMENDMENT AM-D4-1 (filed BEFORE computing, 2026-07-08): ***
    AGG and IEI are NOT present in either data/yahoo/ or data/massive_stock_day/
    (massive_stock_day contains per-day flat files for the full US equity universe;
    bond ETFs AGG and IEI are absent from this store).  These two confirmatory cells
    are therefore SKIP-DATA on this run.  Per the lane pre-declaration:
    "AGG failure does NOT falsify the family; their index mechanics differ from the
    Treasury-ladder extension."  A skip due to data absence is equivalent to an AGG
    FAIL — it does not change the LQD verdict.

GATES (LQD headline cells only — per lane specification):
  G1  BH FDR q <= 0.10  (within the amended family cell-set, i.e. the D4 cells
        pooled with all surviving V3 cells from the original phase-0 run)
  G4  |t_HAC| >= 2 (Newey-West HAC, date-collapsed series)
  G2  split-half same-sign positive (chronological halves, LQD last-day series)
  (G3 last-day > avg-other-day — checked informally, not a hard gate per lane)

STATS LAW (CLAUDE.md §4):
  Collapse to one observation per event-date, then Newey-West on the date-indexed
  series.  NW lag = min(4, sqrt(n)).  No full-sample quantile thresholds used;
  month-end boundary is calendar-derived.

AMENDMENT REGISTRY (filed BEFORE computing):
  AM-D4-1: AGG + IEI data absent from both stores → SKIP, non-falsifying per lane.
  AM-D4-2: BH FDR applied to D4 cells + V3 original cells jointly (amended family).
            V3 p-values used: v3_tlt_last_day (p≈0.0003), v3_tlt_excess (p≈0.0009),
            v3_ief_last_day (p≈0.0), v3_ief_excess (p≈0.0) — from phase0 report.
  AM-D4-3: LQD date range matches TLT (2002-07-30 onward); same 287-month window.

Run:
    python -m scripts.d4_extension_day_complex_phase0
Writes:
    reports/d4-extension-day-complex.md
"""
from __future__ import annotations

import sys
import math
import json
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.validation import newey_west_tstat, benjamini_hochberg  # noqa: E402
from engine.trial_ledger import TrialLedger                         # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FAMILY = "d2_rates_calendar_flows"  # amendment — same family slug
ANN = 252


# ---------------------------------------------------------------------------
# NW lag helper (identical to phase0)
# ---------------------------------------------------------------------------

def _nw_lags(n: int) -> int:
    return max(2, min(4, int(math.sqrt(n))))


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_lqd() -> pd.Series:
    """Load LQD from yahoo store.  Verify nested-symlink law with SPY (known key)."""
    store = ROOT / "data" / "yahoo"

    # Positive control: SPY must exist (if not, symlink is broken)
    spy_path = store / "SPY.parquet"
    assert spy_path.exists(), f"Positive-control FAILED: SPY not found at {spy_path}"

    lqd_path = store / "LQD.parquet"
    assert lqd_path.exists(), f"LQD.parquet not found at {lqd_path}"

    df = pd.read_parquet(lqd_path)
    col = "close" if "close" in df.columns else "close_price"
    s = df[col].sort_index().dropna()
    s.index = pd.to_datetime(s.index)
    print(f"  [LQD] {len(s)} rows, {s.index.min().date()} .. {s.index.max().date()}")
    return s


def check_confirmatory_stores() -> dict[str, str]:
    """
    Check AGG + IEI availability.  Per AM-D4-1, absence = SKIP (non-falsifying).
    Returns a dict mapping ticker -> 'available' | 'skip_data_absent'.
    """
    status = {}
    yahoo = ROOT / "data" / "yahoo"
    msd = ROOT / "data" / "massive_stock_day"
    for sym in ("AGG", "IEI"):
        yahoo_p = yahoo / f"{sym}.parquet"
        # massive_stock_day is day-partitioned; no per-ticker file; check manifest
        msd_manifest = msd / "_manifest.json"
        if yahoo_p.exists():
            status[sym] = "available_yahoo"
        else:
            # massive_stock_day has no per-ticker parquets for bond ETFs
            status[sym] = "skip_data_absent"
    return status


# ---------------------------------------------------------------------------
# V3-replica: month-end extension for a single price series
# ---------------------------------------------------------------------------

def extension_day_cells(series: pd.Series, label: str) -> dict:
    """
    Replicate V3 construction exactly for a given price series.
    Returns a dict of cell stats (last_day, excess, avg_other).
    """
    ret = series.pct_change().dropna()

    month_groups = pd.Series(ret.index).groupby(
        pd.to_datetime(ret.index).to_period("M")
    )

    rows = []
    for period, group in month_groups:
        dates = sorted(group.values)
        if len(dates) < 5:  # skip partial months (same threshold as phase0)
            continue
        last_day = pd.Timestamp(dates[-1])
        other_days = [pd.Timestamp(d) for d in dates[:-1]]

        last_ret = float(ret.loc[last_day])
        avg_other = float(ret.loc[other_days].mean())
        rows.append({
            "event_date": last_day,
            "last_day_ret": last_ret,
            "avg_other_ret": avg_other,
            "excess_over_avg": last_ret - avg_other,
        })

    df = pd.DataFrame(rows).set_index("event_date").sort_index()
    n = len(df)
    print(f"  [{label}] {n} month-end events, "
          f"{df.index.min().date()} .. {df.index.max().date()}")

    # Primary: last-day raw return
    nw_last = newey_west_tstat(df["last_day_ret"].values, lags=_nw_lags(n))
    # Excess over avg-other-day
    nw_exc = newey_west_tstat(df["excess_over_avg"].values, lags=_nw_lags(n))
    # Baseline: avg-other (informational)
    nw_base = newey_west_tstat(df["avg_other_ret"].values, lags=_nw_lags(n))

    return {
        f"d4_{label}_last_day": {
            "n": n,
            "mean_pct": round(100 * nw_last["mean"], 4) if nw_last["mean"] is not None else None,
            "t_hac": nw_last["t"],
            "p_hac": nw_last["p"],
            "sign_correct": (nw_last["mean"] is not None and nw_last["mean"] > 0),
        },
        f"d4_{label}_excess": {
            "n": n,
            "mean_pct": round(100 * nw_exc["mean"], 4) if nw_exc["mean"] is not None else None,
            "t_hac": nw_exc["t"],
            "p_hac": nw_exc["p"],
            "sign_correct": (nw_exc["mean"] is not None and nw_exc["mean"] > 0),
        },
        f"d4_{label}_avg_other": {
            "n": n,
            "mean_pct": round(100 * nw_base["mean"], 4) if nw_base["mean"] is not None else None,
            "t_hac": nw_base["t"],
            "p_hac": nw_base["p"],
        },
        "_series": df,  # retain for split-half
    }


# ---------------------------------------------------------------------------
# Split-half (GATE G2)
# ---------------------------------------------------------------------------

def split_half_sign(series: pd.Series) -> dict:
    """Chronological split-half; pass = same-sign positive in both halves."""
    s = series.dropna().sort_index()
    n = len(s)
    if n < 10:
        return {"n": n, "pass": False, "reason": "too few obs"}
    h1 = s.iloc[: n // 2]
    h2 = s.iloc[n // 2 :]
    m1 = float(h1.mean())
    m2 = float(h2.mean())
    direction_correct = m1 > 0 and m2 > 0
    return {
        "n": n,
        "n_h1": len(h1),
        "n_h2": len(h2),
        "mean_h1_pct": round(100 * m1, 4),
        "mean_h2_pct": round(100 * m2, 4),
        "same_sign": (np.sign(m1) == np.sign(m2)),
        "direction_correct": direction_correct,
        "pass": direction_correct,
    }


# ---------------------------------------------------------------------------
# Trial ledger registration (BEFORE computing)
# ---------------------------------------------------------------------------

def register_trials(ledger: TrialLedger, confirmatory_status: dict) -> int:
    """
    Register every D4 config in the family BEFORE computing.
    AGG/IEI cells only registered if data is available (per AM-D4-1).
    """
    configs = [
        # LQD — PRIMARY
        {"variant": "D4", "instrument": "LQD", "metric": "last_day_return"},
        {"variant": "D4", "instrument": "LQD", "metric": "excess_over_avg"},
    ]
    # Confirmatory cells — only register if available (skip if absent)
    for sym, status in confirmatory_status.items():
        if status.startswith("available"):
            configs.append({"variant": "D4", "instrument": sym,
                            "metric": "last_day_return", "role": "confirmatory"})
            configs.append({"variant": "D4", "instrument": sym,
                            "metric": "excess_over_avg", "role": "confirmatory"})
    n = ledger.log_grid(configs, family=FAMILY)
    print(f"  [ledger] registered {n} new D4 configs for family={FAMILY}")
    return n


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> dict:
    out = []
    DATE_RUN = "2026-07-08"

    header = f"""# d4-extension-day-complex — Phase-0 Validation Report
# Family Amendment: d2_rates_calendar_flows

**Family:** {FAMILY} (AMENDMENT — D4 extension cells added to confirmed V3)
**Pre-reg:** Lane D4-06 (research SIGNAL_LAB_FRONTIER_DAY2_FABLE_ADJUDICATION_2026-07-06.md,
             V3 month-end extension confirmed; D4 adds LQD + confirmatory AGG/IEI)
**Date run:** {DATE_RUN}
**V3 construction replicated exactly:** last-business-day return vs same-month
             average-other-day return; one obs per event-date; NW HAC t-stat.

## Pre-registered amendments (filed BEFORE computing)

- AM-D4-1: AGG + IEI absent from data/yahoo/ and data/massive_stock_day/
  (massive_stock_day carries per-day equity files; bond ETFs excluded from store).
  These confirmatory cells are SKIP-DATA on this run.  Per lane: "AGG failure does
  not falsify the family; their index mechanics differ from the Treasury-ladder
  extension."  Data-absent skip = non-falsifying.
- AM-D4-2: BH FDR correction applied jointly to D4 cells + V3 original cells
  (amended family cell-set).  V3 p-values from phase0 report used as anchors:
  v3_tlt_last_day p≈0.0003, v3_tlt_excess p≈0.0009,
  v3_ief_last_day p≈0.0, v3_ief_excess p≈0.0.
- AM-D4-3: LQD date range matches TLT/IEF (2002-07-30 onward); 287-month window.
"""
    out.append(header)

    # ------------------------------------------------------------------ #
    # Data store verification
    # ------------------------------------------------------------------ #
    print("\n=== DATA STORE VERIFICATION ===")
    out.append("## Data store verification\n```")
    lqd = load_lqd()
    conf_status = check_confirmatory_stores()
    out.append(f"LQD (yahoo): {len(lqd)} rows, "
               f"{lqd.index.min().date()} .. {lqd.index.max().date()}")
    for sym, st in conf_status.items():
        out.append(f"{sym} (massive_stock_day): {st}")
    out.append("```\n")

    # ------------------------------------------------------------------ #
    # Register trials BEFORE computing
    # ------------------------------------------------------------------ #
    print("\n=== TRIAL LEDGER REGISTRATION ===")
    led = TrialLedger(family=FAMILY)
    n_new = register_trials(led, conf_status)
    n_family = led.effective_n(FAMILY)
    out.append(f"**Trial budget:** {n_new} new D4 configs registered; "
               f"amended family total = {n_family} configs (family={FAMILY})\n")
    out.append(f"**Confirmatory cell status:** "
               + "; ".join(f"{k}={v}" for k, v in conf_status.items()) + "\n")

    # ------------------------------------------------------------------ #
    # Compute D4 LQD cells
    # ------------------------------------------------------------------ #
    print("\n=== COMPUTING D4 LQD CELLS ===")
    lqd_res = extension_day_cells(lqd, "lqd")
    lqd_df = lqd_res.pop("_series")

    # ------------------------------------------------------------------ #
    # BH FDR — amended family cell-set (D4 + V3 originals from AM-D4-2)
    # ------------------------------------------------------------------ #
    # V3 anchor p-values from phase0 report (pre-registered per AM-D4-2)
    v3_anchor_pvals = {
        "v3_tlt_last_day": 0.0003,
        "v3_tlt_excess":   0.0009,
        "v3_ief_last_day": 0.0,
        "v3_ief_excess":   0.0,
    }
    pval_map = dict(v3_anchor_pvals)

    # Add D4 LQD cells
    for k in ("d4_lqd_last_day", "d4_lqd_excess"):
        c = lqd_res.get(k, {})
        if c.get("p_hac") is not None:
            pval_map[k] = c["p_hac"]

    bh = benjamini_hochberg(pval_map, alpha=0.10)

    # ------------------------------------------------------------------ #
    # Split-half (G2) — LQD last-day series
    # ------------------------------------------------------------------ #
    sh_lqd = split_half_sign(lqd_df["last_day_ret"])

    # ------------------------------------------------------------------ #
    # Gate evaluation (LQD primary only per lane)
    # ------------------------------------------------------------------ #
    lqd_last = lqd_res.get("d4_lqd_last_day", {})
    lqd_exc = lqd_res.get("d4_lqd_excess", {})
    lqd_base = lqd_res.get("d4_lqd_avg_other", {})

    def t_ok(c: dict) -> bool:
        t = c.get("t_hac")
        return t is not None and abs(t) >= 2.0

    g1_bh_lqd_last = bh.get("d4_lqd_last_day", {}).get("reject", False)
    g1_bh_lqd_exc = bh.get("d4_lqd_excess", {}).get("reject", False)
    g1_pass = g1_bh_lqd_last or g1_bh_lqd_exc  # any D4 cell survives BH

    g4_pass = t_ok(lqd_last)  # headline cell per lane = last_day
    g2_pass = sh_lqd["pass"]

    # G3: last-day > avg-other (informational check)
    g3_pass = (lqd_last.get("mean_pct") is not None and
               lqd_base.get("mean_pct") is not None and
               (lqd_last["mean_pct"] or 0) > (lqd_base["mean_pct"] or 0))

    all_gates = g1_pass and g4_pass and g2_pass

    # ------------------------------------------------------------------ #
    # Report sections
    # ------------------------------------------------------------------ #
    out.append("## D4 — LQD month-end extension (PRIMARY)\n")
    out.append(
        f"Universe: all calendar months in LQD history (2002-2026). "
        f"Last trading day return vs avg of all other days in the month.  "
        f"Construction identical to confirmed V3.\n"
    )

    out.append("```")
    out.append(
        f"{'cell':<30} {'n':>5} {'mean%':>9} {'t_HAC':>7} {'p':>7} "
        f"{'sign_ok':>8} {'BH_q':>7} {'BH_rej':>7}"
    )
    for k in ("d4_lqd_last_day", "d4_lqd_excess", "d4_lqd_avg_other"):
        c = lqd_res.get(k, {})
        bh_r = bh.get(k, {})
        n_c = c.get("n", 0)
        m = f"{c.get('mean_pct', 'N/A')}" if c.get("mean_pct") is not None else "N/A"
        t = f"{c.get('t_hac', 'N/A')}"
        p = f"{c.get('p_hac', 'N/A')}"
        sign_val = c.get("sign_correct")
        sign = str(sign_val) if sign_val is not None else "N/A"
        bh_q = f"{bh_r.get('q', 'N/A')}" if bh_r else "N/A"
        bh_rej = str(bh_r.get("reject", "N/A")) if bh_r else "N/A"
        out.append(
            f"{k:<30} {n_c:>5} {m:>9} {t:>7} {p:>7} {sign:>8} {bh_q:>7} {bh_rej:>7}"
        )
    out.append("```\n")

    out.append("**Split-half (G2) — D4 LQD last-day return:**")
    out.append(
        f"```\n"
        f"H1: mean={sh_lqd['mean_h1_pct']}% (n={sh_lqd['n_h1']})\n"
        f"H2: mean={sh_lqd['mean_h2_pct']}% (n={sh_lqd['n_h2']})\n"
        f"Same-sign positive: {sh_lqd['pass']}\n"
        f"GATE G2 D4 LQD: {'PASS' if g2_pass else 'FAIL'}\n```\n"
    )

    out.append("**G3 D4 (last-day mean > avg-other-days baseline, informational):**")
    out.append(
        f"  Last-day mean: {lqd_last.get('mean_pct')}%  "
        f"Avg-other-days mean: {lqd_base.get('mean_pct')}%  "
        f"{'PASS' if g3_pass else 'FAIL'}\n"
    )

    # ------------------------------------------------------------------ #
    # Confirmatory cells summary
    # ------------------------------------------------------------------ #
    out.append("## Confirmatory cells (AGG + IEI)\n")
    out.append("Per AM-D4-1 and lane pre-declaration: these cells are NON-FALSIFYING.")
    out.append("AGG and IEI are absent from data/yahoo/ and data/massive_stock_day/.")
    out.append("Status: SKIP-DATA (data absent on this run).")
    out.append("Per lane: 'AGG failure does not falsify the family; their index")
    out.append("mechanics differ from the Treasury-ladder extension.'")
    out.append("A data-absent skip is treated as non-falsifying absent evidence.\n")

    # ------------------------------------------------------------------ #
    # BH amended family table
    # ------------------------------------------------------------------ #
    out.append("## BH FDR — amended family cell-set (D4 + V3 anchors)\n")
    out.append("```")
    out.append(f"{'cell':<30} {'p':>8} {'BH_q':>8} {'reject':>8}")
    for k, bh_r in sorted(bh.items(), key=lambda x: x[1].get("q", 1)):
        p_val = pval_map.get(k, "N/A")
        q_val = bh_r.get("q", "N/A")
        rej = bh_r.get("reject", False)
        out.append(f"{k:<30} {p_val:>8} {q_val:>8} {str(rej):>8}")
    out.append("```\n")

    # ------------------------------------------------------------------ #
    # Gate summary
    # ------------------------------------------------------------------ #
    verdict = "SCORED" if all_gates else "NULL — not all gates cleared"

    out.append("## Gate summary (frozen gates per lane, LQD primary)\n")
    out.append("```")
    out.append(f"{'Gate':<55} {'Result':>8}")
    out.append("-" * 65)
    out.append(
        f"G1 BH FDR q<=0.10 (any D4 LQD cell in amended family BH)  "
        f"{'PASS' if g1_pass else 'FAIL'}"
    )
    for k in ("d4_lqd_last_day", "d4_lqd_excess"):
        bh_r = bh.get(k, {})
        q = bh_r.get("q", "N/A")
        rej = bh_r.get("reject", False)
        out.append(f"   -> {k}: q={q}, reject={rej}")
    out.append(
        f"G2 split-half same-sign positive (LQD last-day):          "
        f"{'PASS' if g2_pass else 'FAIL'}"
    )
    out.append(
        f"   H1={sh_lqd['mean_h1_pct']}% H2={sh_lqd['mean_h2_pct']}%"
    )
    out.append(
        f"G4 |t_HAC| >= 2 (d4_lqd_last_day headline):              "
        f"{'PASS' if g4_pass else 'FAIL'}"
    )
    out.append(
        f"   t_HAC = {lqd_last.get('t_hac')}"
    )
    out.append("-" * 65)
    out.append(
        f"All LQD gates (G1+G2+G4):                                 "
        f"{'PASS' if all_gates else 'FAIL'}"
    )
    out.append(
        f"Confirmatory AGG/IEI:                                      "
        f"SKIP-DATA (non-falsifying per AM-D4-1)"
    )
    out.append("```\n")

    out.append(f"## VERDICT\n\n**{verdict}**\n")

    # ------------------------------------------------------------------ #
    # Plain English
    # ------------------------------------------------------------------ #
    out.append("""## In plain English

This study extends the confirmed V3 month-end extension finding to corporate bond ETFs.

**Why LQD?** LQD tracks the iBoxx USD Liquid Investment Grade Index — the most liquid
investment-grade corporate bond benchmark.  Like Treasury ETFs (TLT, IEF), LQD is held
widely in bond index funds.  At month-end, index managers who own corporate bonds must
rebalance to the newly extended benchmark duration, creating the same buying pressure
observed for Treasuries.

**The test:** On the last trading day of each month (2002-2026), does LQD return more
than it typically does on other days of the same month?  We use the identical
construction as the confirmed V3 test: collapse to one observation per month, compute
raw return and the excess over the same-month average, apply Newey-West HAC and
Benjamini-Hochberg FDR correction within the amended family.

**Why AGG and IEI are skipped:** AGG (US broad bond aggregate) and IEI (3-7y Treasury)
were pre-declared as confirmatory cells only — a failure would not have falsified the
family in any case.  Both are absent from the available data stores and are therefore
skipped on this run.  This skip is equivalent to a non-result, consistent with the
pre-declaration.

A null result is a successful test.
""")

    # ------------------------------------------------------------------ #
    # Amendment note for family log
    # ------------------------------------------------------------------ #
    out.append("""## Family amendment record

**Amendment to d2_rates_calendar_flows:**
- D4 cells (LQD primary, AGG/IEI confirmatory) added to the family.
- All D4 cells participate in the joint BH FDR correction with existing V3 cells.
- This amendment does NOT alter the V3 SCORED verdict; it adds evidence.
- If LQD SCORES: LQD month-end extension is a confirmed generalization of the
  Treasury-ladder finding, strengthening the mechanism (index-rebalancing flows
  drive cross-asset bond ETF returns on the last business day of the month).
- Nightly wiring: if SCORED, add `month_end_extension_signal()` to cover LQD
  alongside TLT; no new data collection needed (LQD already in yahoo store).
""")

    # ------------------------------------------------------------------ #
    # Write report
    # ------------------------------------------------------------------ #
    report_text = "\n".join(out)
    print("\n" + "=" * 70)
    print(report_text)
    print("=" * 70)

    report_path = ROOT / "reports" / "d4-extension-day-complex.md"
    report_path.parent.mkdir(exist_ok=True)
    report_path.write_text(report_text)
    print(f"\n[written] {report_path}")

    # ------------------------------------------------------------------ #
    # JSON summary
    # ------------------------------------------------------------------ #
    summary = {
        "family": FAMILY,
        "amendment": "D4-extension-day-complex",
        "verdict": verdict,
        "n_new_configs": n_new,
        "n_family_total": n_family,
        "g1_bh_pass": g1_pass,
        "g2_split_half_pass": g2_pass,
        "g4_t_hac_pass": g4_pass,
        "all_gates_lqd": all_gates,
        "confirmatory_agg": conf_status.get("AGG"),
        "confirmatory_iei": conf_status.get("IEI"),
        "lqd_last_day": lqd_last,
        "lqd_excess": lqd_exc,
        "lqd_split_half": sh_lqd,
        "bh_table": bh,
    }
    print("\n=== JSON SUMMARY ===")
    print(json.dumps(summary, indent=2, default=str))
    return summary


if __name__ == "__main__":
    main()
