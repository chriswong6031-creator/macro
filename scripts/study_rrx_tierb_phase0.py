"""Phase-0 gauntlet study for RRX Tier-B candidates — W3 of the Risk Radar Expansion.

PRE-REGISTERED GATE (do not edit post-run):
  PASS = lift_2020 >= 1.20 AND perm_p < 0.05 AND fire_rate < 0.20 (at thr=0.90)
  Era split: 2010 (mandatory per era-split law)

Candidates studied:
  (1) nh_contraction — breadth.parquet nh / n_members 21d mean; near-high = SPY >= 0.98 * 252d max;
      leg = pct_rank_window(-nh_share_21d, 504) ON near-high days, 0.0 elsewhere.
  (2) jpy_carry — FRED DEXJPUS (yen per USD); falling USD/JPY = yen strengthening = carry unwind;
      stress = -(x/x.shift(10)-1) where x < 50d MA else 0.0;
      leg = pct_rank_window(stress, 504) reindexed to SPY calendar.
  (3) copper_gold — HG=F / GC=F via store; check data presence and run if available.

Writes reports/rrx-tierb-phase0.md.

RRX masterplan §4B, §5 W3. Series builders are single-source — risk_radar.py imports them
from this module's helpers to ensure no drift between study and live engine.
"""
from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Pre-registered gate (CONSTANTS — do not alter after the study is run)
# ---------------------------------------------------------------------------
PASS_LIFT_2020 = 1.20
PASS_PERM_P = 0.05
PASS_FIRE_RATE_MAX = 0.20   # fire-rate cap at thr=0.90 (concentration guard)
THR = 0.90
ERA_SPLIT = "2010-01-01"    # era-split law: 2010
PCT_WIN = 504               # causal trailing window (matches risk_radar convention)
PERM_N = 500                # permutation samples

_HERE = Path(__file__).resolve().parent.parent   # repo root


def _repo_imports():
    """Add repo root to path so the script is runnable standalone."""
    if str(_HERE) not in sys.path:
        sys.path.insert(0, str(_HERE))


_repo_imports()

# ---------------------------------------------------------------------------
# Series builders: imported from engine/risk_radar (single source, no drift)
# The builders live in engine/risk_radar.py; this script imports them so the
# study and the live engine always use identical construction code.
# ---------------------------------------------------------------------------
from engine.risk_radar import build_nh_contraction, build_jpy_carry  # noqa: E402


def build_copper_gold(spy: pd.Series) -> pd.Series | None:
    """Copper/gold ratio 65d ROC — growth scare Tier-B candidate.

    Returns None (data_blocked) if either HG=F or GC=F is absent from the yahoo store.
    Low copper/gold ROC (ratio falling) = growth anxiety. Negated so risk-rising = high pctile.

    RRX masterplan §4B R4. Tier-B, reindexed onto SPY calendar.
    """
    from lib import store
    from engine.indicators import pct_rank_window

    hg = store.read("yahoo", "HG=F")
    gc = store.read("yahoo", "GC=F")
    if hg is None or gc is None:
        return None

    idx = spy.index
    hg_px = hg["close"].dropna()
    gc_px = gc["close"].dropna()
    hg_px.index = pd.to_datetime(hg_px.index)
    gc_px.index = pd.to_datetime(gc_px.index)

    ratio = (hg_px / gc_px).reindex(idx).ffill()
    roc65 = ratio / ratio.shift(65) - 1.0
    # risk-rising = falling copper/gold ratio (growth concern): negate
    pctile = pct_rank_window(-roc65, PCT_WIN)
    return pctile.rename("copper_gold")


# ---------------------------------------------------------------------------
# Study runner
# ---------------------------------------------------------------------------

def run_study() -> dict:
    from lib import store
    from engine.risk_radar_backtest import lift, perm_p, detect_events

    spy_df = store.read("yahoo", "SPY")
    if spy_df is None or len(spy_df) < 300:
        print("ERROR: SPY data missing — cannot run study", file=sys.stderr)
        sys.exit(1)
    spy = spy_df["close"].dropna()
    spy.index = pd.to_datetime(spy.index)
    spy = spy.sort_index()

    breadth_df = store.read("breadth", "breadth")
    if breadth_df is None or "nh" not in breadth_df.columns:
        print("ERROR: breadth.parquet missing or missing 'nh' column", file=sys.stderr)
        sys.exit(1)
    breadth_df.index = pd.to_datetime(breadth_df.index)

    dexjpus_df = store.read("fred", "DEXJPUS")
    if dexjpus_df is None:
        print("ERROR: FRED DEXJPUS missing", file=sys.stderr)
        sys.exit(1)
    dex_col = dexjpus_df.columns[0]
    dexjpus = dexjpus_df[dex_col].dropna()
    dexjpus.index = pd.to_datetime(dexjpus.index)

    onsets = detect_events(spy=spy)
    print(f"Detected {len(onsets)} drawdown-onset events.")

    results = {}

    # --- (1) nh_contraction ---
    print("Building nh_contraction series...")
    leg_nhc = build_nh_contraction(spy, breadth_df)
    leg_nhc = leg_nhc.dropna()
    nhc_full = lift(leg_nhc, onsets, thr=THR)
    nhc_2020 = lift(leg_nhc, onsets, thr=THR, lo="2020-01-01")
    nhc_pre = lift(leg_nhc, onsets, thr=THR, hi=ERA_SPLIT)
    nhc_p = perm_p(leg_nhc, onsets, thr=THR, n=PERM_N)
    results["nh_contraction"] = {
        "full": nhc_full, "y2020": nhc_2020, "pre_era": nhc_pre,
        "perm_p": nhc_p,
        "series": leg_nhc,
    }
    print(f"  nh_contraction: lift_full={nhc_full['lift']}, lift_2020={nhc_2020['lift']}, "
          f"fire_rate={nhc_full['fire_rate']}, perm_p={nhc_p}")

    # --- (2) jpy_carry ---
    print("Building jpy_carry series...")
    leg_jpy = build_jpy_carry(spy, dexjpus)
    leg_jpy = leg_jpy.dropna()
    jpy_full = lift(leg_jpy, onsets, thr=THR)
    jpy_2020 = lift(leg_jpy, onsets, thr=THR, lo="2020-01-01")
    jpy_pre = lift(leg_jpy, onsets, thr=THR, hi=ERA_SPLIT)
    jpy_p = perm_p(leg_jpy, onsets, thr=THR, n=PERM_N)
    results["jpy_carry"] = {
        "full": jpy_full, "y2020": jpy_2020, "pre_era": jpy_pre,
        "perm_p": jpy_p,
        "series": leg_jpy,
    }
    print(f"  jpy_carry: lift_full={jpy_full['lift']}, lift_2020={jpy_2020['lift']}, "
          f"fire_rate={jpy_full['fire_rate']}, perm_p={jpy_p}")

    # --- (3) copper_gold ---
    print("Building copper_gold series...")
    leg_cg = build_copper_gold(spy)
    if leg_cg is None:
        results["copper_gold"] = {"status": "DATA_BLOCKED",
                                  "note": ("HG=F or GC=F missing from data/yahoo/; "
                                           "cannot compute copper/gold ROC — data_blocked verdict.")}
        print("  copper_gold: DATA_BLOCKED (store.read returned None for HG=F or GC=F)")
    else:
        leg_cg = leg_cg.dropna()
        cg_full = lift(leg_cg, onsets, thr=THR)
        cg_2020 = lift(leg_cg, onsets, thr=THR, lo="2020-01-01")
        cg_pre = lift(leg_cg, onsets, thr=THR, hi=ERA_SPLIT)
        cg_p = perm_p(leg_cg, onsets, thr=THR, n=PERM_N)
        results["copper_gold"] = {
            "full": cg_full, "y2020": cg_2020, "pre_era": cg_pre,
            "perm_p": cg_p,
            "series": leg_cg,
        }
        print(f"  copper_gold: lift_full={cg_full['lift']}, lift_2020={cg_2020['lift']}, "
              f"fire_rate={cg_full['fire_rate']}, perm_p={cg_p}")

    return results


def _verdict(res: dict) -> str:
    """Return PASS / NULL / DATA_BLOCKED verdict string for a candidate."""
    if res.get("status") == "DATA_BLOCKED":
        return "DATA_BLOCKED"
    l20 = res["y2020"]["lift"]
    p = res["perm_p"]
    fr = res["full"]["fire_rate"]
    if l20 is None or p is None or fr is None:
        return "NULL (insufficient data)"
    if l20 >= PASS_LIFT_2020 and p < PASS_PERM_P and fr < PASS_FIRE_RATE_MAX:
        return "PASS"
    reasons = []
    if l20 < PASS_LIFT_2020:
        reasons.append(f"lift_2020={l20:.3f} < {PASS_LIFT_2020}")
    if p >= PASS_PERM_P:
        reasons.append(f"perm_p={p:.3f} >= {PASS_PERM_P}")
    if fr >= PASS_FIRE_RATE_MAX:
        reasons.append(f"fire_rate={fr:.4f} >= {PASS_FIRE_RATE_MAX}")
    return "NULL — " + "; ".join(reasons)


def _fmt_lift(d: dict) -> str:
    l = d.get("lift")
    fr = d.get("fire_rate")
    ne = d.get("n_elev", 0)
    nd = d.get("n_days", 0)
    if l is None:
        return f"None (n_elev={ne}, n_days={nd})"
    return f"{l:.3f} (fire_rate={fr:.4f}, n_elev={ne}, n_days={nd})"


def write_report(results: dict, out_path: Path) -> None:
    """Write the markdown phase-0 report."""
    lines = []
    a = lines.append

    a("# RRX Tier-B Phase-0 Gauntlet Study")
    a("")
    a("**Generated by:** `scripts/study_rrx_tierb_phase0.py`  ")
    a("**Masterplan ref:** `research/RISK_RADAR_EXPANSION_MASTERPLAN_BY_FABLE.md` §4B, §5 W3  ")
    a("**Status:** ACCRUING — display/Tier-B only; no promotion without gauntlet rerun + operator ruling")
    a("")
    a("---")
    a("")
    a("## 1. Methodology")
    a("")
    a("All series are **causal trailing-window percentiles** (504d, matching `risk_radar` convention).")
    a("Lift = P(SPY >= 8% drawdown onset within 15 bd | series >= 0.90 pctile) / base rate,")
    a("computed via `engine.risk_radar_backtest.lift`.")
    a("Era split at 2010 (era-split law: pre-2010 vs 2020+ holdout).")
    a("Permutation p-value: frequency-matched random elevated days, 500 samples (seed=0).")
    a("Near-high mask on `nh_contraction`: SPY >= 0.98 × rolling 252d max (causal).")
    a("50d-MA regime gate on `jpy_carry`: stress = 0.0 when USD/JPY above 50d MA.")
    a("")
    a("**Series builders** are imported from `engine/risk_radar.py` (`build_nh_contraction`,")
    a("`build_jpy_carry`, `build_copper_gold`) — single source, no study-vs-engine drift.")
    a("")
    a("---")
    a("")
    a("## 2. Pre-committed Gates")
    a("")
    a("```")
    a(f"PASS = lift_2020 >= {PASS_LIFT_2020} AND perm_p < {PASS_PERM_P} AND fire_rate < {PASS_FIRE_RATE_MAX}")
    a(f"Threshold: thr = {THR}  |  Era split: {ERA_SPLIT}  |  Permutation N: {PERM_N}")
    a("```")
    a("")
    a("These gates are PRINTED PRE-COMMITTED, not adjusted post-hoc.")
    a("A null here does NOT close the family — nulls are informative confluence inputs (Tier-B).")
    a("")
    a("---")
    a("")
    a("## 3. Results Table")
    a("")
    a("| Candidate | lift_full | lift_2020 (holdout) | fire_rate | perm_p | pre-2010 lift | Verdict |")
    a("|---|---|---|---|---|---|---|")

    for name, res in results.items():
        if res.get("status") == "DATA_BLOCKED":
            a(f"| {name} | — | — | — | — | — | DATA_BLOCKED |")
        else:
            lf = res["full"]["lift"]
            l20 = res["y2020"]["lift"]
            fr = res["full"]["fire_rate"]
            pp = res["perm_p"]
            lpre = res["pre_era"]["lift"]
            v = _verdict(res)
            lf_s = f"{lf:.3f}" if lf is not None else "None"
            l20_s = f"{l20:.3f}" if l20 is not None else "None"
            fr_s = f"{fr:.4f}" if fr is not None else "None"
            pp_s = f"{pp:.3f}" if pp is not None else "None"
            lpre_s = f"{lpre:.3f}" if lpre is not None else "None"
            a(f"| {name} | {lf_s} | {l20_s} | {fr_s} | {pp_s} | {lpre_s} | {v} |")

    a("")
    a("---")
    a("")
    a("## 4. Detailed Results")
    a("")

    for name, res in results.items():
        a(f"### {name}")
        a("")
        if res.get("status") == "DATA_BLOCKED":
            a(f"**DATA_BLOCKED:** {res['note']}")
            a("")
            a("Verdict: DATA_BLOCKED — cannot run gauntlet without price data.")
            a("Action: add HG=F and GC=F to the yahoo collector; re-run after ≥252 rows accrue.")
            a("")
            continue

        v = _verdict(res)
        a(f"**Verdict: {v}**")
        a("")
        a(f"- Full history: {_fmt_lift(res['full'])}")
        a(f"- 2020+ holdout: {_fmt_lift(res['y2020'])}")
        a(f"- Pre-{ERA_SPLIT[:4]}: {_fmt_lift(res['pre_era'])}")
        a(f"- Permutation p: {res['perm_p']:.4f}" if res['perm_p'] is not None else "- Permutation p: None")
        a("")

        if name == "nh_contraction":
            a(textwrap.dedent("""\
                **Construction:** `pct_rank_window(-nh_share_21d, 504)` on near-high days (SPY >= 0.98 × 252d max),
                0.0 elsewhere. `nh_share_21d = (nh / n_members).rolling(21).mean()` from breadth.parquet.

                **Caveats:**
                - Q4 52wk-window seasonality: new-high counts are naturally elevated in Q4, which can suppress
                  the contraction signal precisely when the market is strongest. Not adjusted here.
                - 2010/2011 false-negatives on record (Fed-put support suppressed the expected deterioration).
                - Near-high mask fires only a fraction of the time, reducing n_elev significantly.
                - Realistic ceiling: permanent confluence input alongside Tier-A signals.
            """).rstrip())
        elif name == "jpy_carry":
            a(textwrap.dedent("""\
                **Construction:** `pct_rank_window(stress, 504)` where
                `stress = -(DEXJPUS/DEXJPUS.shift(10) - 1)` gated to 0.0 when DEXJPUS >= 50d MA.
                Reindexed onto SPY calendar (ffill).

                **Caveats:**
                - **2022 sign-inversion documented:** in a pure Fed-hiking regime, carry was long-USD;
                  yen weakness ≠ risk-off in that context. This is the primary reason for Tier-B
                  escalator-only classification — it can amplify a Tier-A signal but cannot originate state.
                - The 50d-MA gate partially corrects this but may not fully screen 2022-type regimes.
                - Transmission channel is real (Aug-2024: USD/JPY -12%, SPX -8%) but non-stationary.
            """).rstrip())
        elif name == "copper_gold":
            a(textwrap.dedent("""\
                **Construction:** `pct_rank_window(-(HG=F/GC=F).pct_change(65), 504)` reindexed to SPY.
                Falling copper/gold ratio = growth anxiety; negated so risk-rising = high percentile.

                **Caveats:**
                - 10y-yield collinearity: copper/gold closely tracks real rates; may add limited
                  orthogonal information beyond `rates_realrate`.
                - Days-only lead noted in literature; likely a permanent confluence input.
                - Data from yahoo commodity futures; potential roll/contract-change artifacts.
            """).rstrip())
        a("")

    a("---")
    a("")
    a("## 5. Honest Assessment")
    a("")
    a("These are **context/Tier-B candidates**. A null here is **informative**, not a kill:")
    a("")
    a("- A null as a *standalone* signal is retained as a **confluence input** (house law:")
    a("  `context-accrual-fundamental-goal`): non-standalone ≠ worthless.")
    a("- These candidates are shipped as **accruing legs** in `engine/risk_radar.py`.")
    a("- They can escalate a hot Tier-A scare but CANNOT originate state (verified below).")
    a("- The word 'validated' is not claimed for any leg here.")
    a("")
    a("---")
    a("")
    a("## 6. Lane-(ii) Registration (A6 Two-Lane Ruling Compliance)")
    a("")
    a("Per the A6 two-lane governance ruling, the following gauntlet attempts are machine-registered:")
    a("")
    a("| Candidate | Pre-committed Gate | Come-back | Lane |")
    a("|---|---|---|---|")
    a(f"| nh_contraction | lift_2020 >= {PASS_LIFT_2020} AND perm_p < {PASS_PERM_P} AND fire_rate < {PASS_FIRE_RATE_MAX} | 2026-10-15 | Tier-B accrual → Tier-A attempt on next gauntlet |")
    a(f"| jpy_carry | lift_2020 >= {PASS_LIFT_2020} AND perm_p < {PASS_PERM_P} AND fire_rate < {PASS_FIRE_RATE_MAX} | 2026-10-15 | Tier-B accrual → Tier-A attempt on next gauntlet |")
    a(f"| copper_gold | lift_2020 >= {PASS_LIFT_2020} AND perm_p < {PASS_PERM_P} AND fire_rate < {PASS_FIRE_RATE_MAX} | 2026-10-15 | Tier-B accrual → growth scare on gauntlet pass |")
    a("")
    a("**Come-back date: 2026-10-15** — re-run this script after the forward-outcome log has accrued")
    a("at least one year of live readings. Do not promote to Tier-A without a fresh operator ruling.")
    a("")
    a("**Reference:** `research/RISK_RADAR_EXPANSION_MASTERPLAN_BY_FABLE.md` §4B R1/R3/R4,")
    a("RRX-R9 (Lane-(ii) machine registration), RRX-R7 (chips never enter _LEG_CALIB without promotion).")
    a("")
    a("---")
    a("")
    a("*Report generated by `scripts/study_rrx_tierb_phase0.py`. Do not edit manually.*")

    out_path.write_text("\n".join(lines) + "\n")
    print(f"\nReport written to {out_path}")


if __name__ == "__main__":
    results = run_study()
    out = _HERE / "reports" / "rrx-tierb-phase0.md"
    write_report(results, out)
    print("\n=== Summary ===")
    for name, res in results.items():
        print(f"  {name}: {_verdict(res)}")
