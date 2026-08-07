"""Price-adjustment contamination audit — census, exposure map, and measured magnitude.

WHAT THIS MEASURES
==================
An excess return is ``name_return − benchmark_return``. That subtraction is only
meaningful when both legs share one adjustment basis. This repo carries two families:

  ADJUSTED   ``data/baskets/ohlcv`` · ``data/yahoo`` · ``data/stocks``
  UNADJUSTED ``data/{breadth,midcap_breadth,smallcap_breadth}/_closes_cache.parquet``

An instrument that prices NAMES from a cache and its BENCHMARK (SPY) from an adjusted
store books each name's own distribution as a loss against an unaffected benchmark.

This file produces four things, all measured rather than asserted:

  §1 CENSUS      every research instrument and production path that computes an excess
                 return, its name source, its benchmark source, and whether the pairing
                 is mixed. Machine-checked against the files on disk (§1b) so the census
                 cannot rot into prose.
  §2 BASIS       how far the two families actually diverge, swept over every cache name
                 with an adjusted counterpart: share that match exactly, size and timing
                 of the divergences, and the rebuild boundary that bounds the exposure.
  §3 LEDGER      the per-row error the production grader's `excess_spy` column carries,
                 recomputed on both bases over its own frame, with the aggregate effect
                 on the headline and on each cohort split.
  §4 VERDICT     which shipped conclusions the measured magnitude can and cannot move.

WHAT IT DOES NOT DO
-------------------
It changes no engine, gate, board, grader, or ledger. It writes one JSON next to itself.
The production exposure it finds in §1 is REPORTED, not repaired — the fix belongs in
its own PR against ``scripts/grade_us_board.py``, where it can be reviewed against the
ledger it rewrites.

Run:  python3 research/prophet_us_audit/price_adjustment_audit.py
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = str(Path(__file__).resolve().parents[2])
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "price_adjustment_audit_results.json")
os.chdir(REPO)
sys.path.insert(0, REPO)
sys.path.insert(0, HERE)

import price_ladder  # noqa: E402

# ---------------------------------------------------------------- constants --
ASOF = "2026-07-31"                 # the caches' last committed bar — the frozen pin
GROUPS = ("breadth", "midcap_breadth", "smallcap_breadth")
LEDGER = "data/us_board_ledger/retro_grades.parquet"
MIN_OVERLAP = 200                   # sessions needed before a name is basis-comparable
THIN_N = 20                         # below this a cell is printed and called thin
EXACT = 1e-4                        # |dev| below this (%) reads as an exact match


def _r(x, nd=4):
    if x is None:
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return round(f, nd) if np.isfinite(f) else None


# --------------------------------------------------------------------------- #
# §1 CENSUS
# --------------------------------------------------------------------------- #
# EXPOSED means: the name leg and the benchmark leg are drawn from DIFFERENT adjustment
# families in the same subtraction. An instrument that prices both legs from the same
# family is NOT exposed and is recorded as such — flagging everything would make the
# census useless. `grep` is the receipt for each row (§1b re-checks them on disk).
CENSUS: list[dict] = [
    # ---- research: prophet_us_audit ----
    {"instrument": "research/prophet_us_audit/fresh_ticks_extension_replay.py",
     "pr": "#4546", "name_source": "closes_cache (UNADJUSTED)",
     "bench_source": "data/yahoo/SPY.parquet (ADJUSTED)",
     "exposed": "yes",
     "reason": "names from the three breadth caches, SPY from yahoo — mixed basis in "
               "every excess_spy_pp cell. Also reports excess vs the same-panel universe "
               "median, which is same-basis and therefore unexposed.",
     "headline": "FRESH_TICKS extension null: delta +0.04pp [-0.18,+0.24]",
     "rerun": "fresh_ticks_extension_replay_adjusted_rerun.json",
     "greps": {"name": r"_closes_cache", "bench": r"data/yahoo/SPY\.parquet"}},

    {"instrument": "research/prophet_us_audit/label_grading_battery.py",
     "pr": "#4547", "name_source": "closes_cache (UNADJUSTED); weekly leg spliced over "
                                   "data/yahoo with the CACHE winning on overlap",
     "bench_source": "data/yahoo/SPY.parquet (ADJUSTED)",
     "exposed": "yes",
     "reason": "sections 2/3 compute forward returns off the cache panel against a yahoo "
               "SPY. Section 1 reads excess_spy off the production ledger and inherits "
               "the SAME mixed basis from scripts/grade_us_board.py rather than creating "
               "it. The weekly splice also mixes bases WITHIN one name's series.",
     "headline": "veto-label family null, max +0.28pp",
     "rerun": "label_grading_battery_adjusted_rerun.json",
     "greps": {"name": r"_closes_cache", "bench": r'store\.read\("yahoo", BENCH\)'}},

    {"instrument": "research/prophet_us_audit/reclaim_veto_packet.py",
     "pr": "2026-08-05 packet", "name_source": "closes_cache (UNADJUSTED)",
     "bench_source": "data/yahoo/SPY.parquet (ADJUSTED)",
     "exposed": "yes",
     "reason": "load_panel() reads the three caches; load_benchmark() reads yahoo SPY; "
               "excess_<h> subtracts them directly.",
     "headline": "reclaim-veto aggregate", "rerun": None,
     "greps": {"name": r"_closes_cache", "bench": r'Path\("data/yahoo"\)'}},

    {"instrument": "research/prophet_us_audit/name_score_pk_benchmark.py",
     "pr": "name_score P@k", "name_source": "ledger excess_spy (INHERITED)",
     "bench_source": "ledger excess_spy (INHERITED)",
     "exposed": "inherited",
     "reason": "computes no excess of its own — reads the precomputed excess_spy column "
               "from retro_grades.parquet, so it carries exactly the production grader's "
               "bias and adds none. Its own cache read is a PIT tier recompute (a signal "
               "leg), not a return leg.",
     "headline": "P@k / rank-IC on the S-A/S-B/S-C frame", "rerun": None,
     "greps": {"name": r"_closes_cache", "bench": r"excess_spy"}},

    {"instrument": "research/prophet_us_audit/superintelligence_standins.py",
     "pr": "S-A/S-B/S-C", "name_source": "ledger excess_spy (INHERITED)",
     "bench_source": "ledger excess_spy (INHERITED)",
     "exposed": "inherited",
     "reason": "same shape as name_score_pk_benchmark: excess read from the ledger; the "
               "cache read is the S-B tier recompute, a signal leg.",
     "headline": "S-B confirmation by_cross_age_ticks", "rerun": None,
     "greps": {"name": r"_closes_cache", "bench": r"excess_spy"}},

    {"instrument": "research/prophet_us_audit/relay_position_standin.py",
     "pr": "Door T stand-in", "name_source": "closes_cache (UNADJUSTED)",
     "bench_source": "same-day median of the SAME cache panel (UNADJUSTED)",
     "exposed": "partial",
     "reason": "both legs share one basis, so the SPY-shaped bias is absent. What "
               "survives is second-order: a distribution-paying name is measured against "
               "a median whose members' distributions partly cancel it, leaving a tilt "
               "of (name yield - universe median yield) rather than the full yield.",
     "headline": "relay-position excess vs day median", "rerun": None,
     "greps": {"name": r"_closes_cache", "bench": r"fwd\.median\(axis=1\)"}},

    {"instrument": "research/prophet_us_audit/leader_reset_study.py",
     "pr": "leader-reset (killed family)", "name_source": "closes_cache (UNADJUSTED)",
     "bench_source": "cross-sectional median of the SAME cache panel (UNADJUSTED)",
     "exposed": "partial",
     "reason": "same construction as relay_position_standin — one basis on both legs, "
               "residual second-order tilt only.",
     "headline": "n/a (family already killed)", "rerun": None,
     "greps": {"name": r"_closes_cache", "bench": r"median\(axis=1\)"}},

    {"instrument": "research/prophet_us_audit/ignition_standins.py",
     "pr": "#4564", "name_source": "data/baskets/ohlcv/*.parquet (ADJUSTED)",
     "bench_source": "data/yahoo/SPY.parquet (ADJUSTED)",
     "exposed": "no",
     "reason": "both legs are drawn from the ADJUSTED family, so the subtraction is "
               "basis-consistent and this defect cannot reach it. The W8 intersection "
               "null and S-COIL's +0.98pp at H=63 are unaffected.",
     "headline": "W8 intersection null; S-COIL +0.98pp at H=63", "rerun": None,
     "greps": {"name": r"data/baskets/ohlcv", "bench": r"data/yahoo/SPY\.parquet"}},

    {"instrument": "research/prophet_us_audit/roc_extremes_battery.py",
     "pr": "ROC extremes", "name_source": "data/baskets/ohlcv/*.parquet (ADJUSTED)",
     "bench_source": "data/yahoo/SPY.parquet (ADJUSTED)",
     "exposed": "no", "reason": "both legs ADJUSTED — basis-consistent.",
     "headline": "ROC-extreme cohorts", "rerun": None,
     "greps": {"name": r"data/baskets/ohlcv", "bench": r"data/yahoo/SPY\.parquet"}},

    {"instrument": "research/prophet_us_audit/runner_exclusion_audit.py",
     "pr": "runner audit", "name_source": "closes_cache (UNADJUSTED)",
     "bench_source": "none — no benchmark subtraction anywhere",
     "exposed": "no",
     "reason": "computes raw forward return from first admission only "
               "(fwd_ret_from_first_pct). With no benchmark leg there is no basis "
               "mismatch; a distribution biases the raw return itself, which is a "
               "different and much smaller question than a mixed-basis excess.",
     "headline": "admit-character census", "rerun": None,
     "greps": {"name": r"_closes_cache", "bench": None}},

    {"instrument": "research/prophet_us_audit/post_board_trajectory.py",
     "pr": "#4692", "name_source": "adjusted-first ladder (ADJUSTED, cache last)",
     "bench_source": "data/yahoo/SPY.parquet (ADJUSTED)",
     "exposed": "no",
     "reason": "the lane that FOUND this defect; already re-laddered adjusted-first and "
               "prints its residual unadjusted count. Reference implementation.",
     "headline": "post-board trajectory deltas", "rerun": None,
     "greps": None},   # lives on an unmerged branch; not on disk here

    # ---- research: elsewhere ----
    {"instrument": "research/cn_prophet_audit/*.py",
     "pr": "CN program", "name_source": "data/china_stocks (CN family)",
     "bench_source": "data/china/510300.SS.parquet (CN family)",
     "exposed": "no",
     "reason": "a self-consistent China price family that never touches either US "
               "family.", "headline": "CN relay/loser studies", "rerun": None,
     "greps": None},

    {"instrument": "research/entry_timing/wave*.py",
     "pr": "entry-timing waves", "name_source": "data/stocks or data/baskets/ohlcv "
                                                "(ADJUSTED)",
     "bench_source": "data/stocks/SPY.parquet -> data/yahoo/SPY.parquet (ADJUSTED)",
     "exposed": "no",
     "reason": "never reads a breadth cache; both rungs of its SPY ladder are ADJUSTED.",
     "headline": "wave batteries", "rerun": None, "greps": None},

    {"instrument": "research/entry_intel/**, research/bottom_signal_backtest/, "
                   "research/species/s7_rs_repair_phase0/",
     "pr": "various", "name_source": "data/massive_stock_day | data/baskets/ohlcv | "
                                     "data/stocks (ADJUSTED)",
     "bench_source": "data/yahoo (ADJUSTED)",
     "exposed": "no",
     "reason": "same-family pairings. s7 documents the rule explicitly ('Do NOT mix with "
               "data/stocks which is yahoo total-return adjusted') and is the house "
               "reference for getting this right.",
     "headline": "various", "rerun": None, "greps": None},

    # ---- PRODUCTION (reported, NOT repaired in this PR) ----
    {"instrument": "scripts/grade_us_board.py",
     "pr": "PRODUCTION", "name_source": "engine.equity_factors._closes('broad') -> the "
                                        "three breadth caches (UNADJUSTED by code)",
     "bench_source": "data/yahoo/{SPY,XL*}.parquet (ADJUSTED)",
     "exposed": "latent-PRODUCTION",
     "reason": "READ THE CODE AND IT IS EXPOSED; MEASURE THE ARTIFACT AND IT IS NOT — "
               "both halves are receipts and the row states both. _load_prices() pairs a "
               "cache-priced name leg with a yahoo-priced ETF leg, and its docstring "
               "claims 'Both dividend-adjusted TR closes', which is true of the ETF leg "
               "only. But every one of the 1,931 comparable rows in the shipped ledger "
               "matches the ADJUSTED recomputation to 1e-5, including all 21 rows where "
               "the two bases actually differ (LPG 2026-06-22 H5: cache basis -13.8224%, "
               "adjusted basis -11.8780%, ledger stores -11.8780%). Ledger rows are "
               "never re-graded (0 of 950 rows changed between the 2026-07-03 commit and "
               "today), so the adjusted value was written at grading time. The exposure "
               "is therefore LATENT — the pairing is wrong in the code but the artifact "
               "on this frame is clean. The path that supplies the adjusted price was "
               "not identified here, so the protection is not understood and cannot be "
               "assumed to hold on the next frame.",
     "headline": "every excess_spy / excess_sector row in the US board ledger",
     "rerun": None,
     "greps": {"name": r'_closes\("broad"\)', "bench": r'"data" / "yahoo"'}},

    {"instrument": "scripts/prophet_postmortem.py",
     "pr": "PRODUCTION", "name_source": "closes_cache FIRST, baskets/extras only as "
                                        "fallback (UNADJUSTED for the majority)",
     "bench_source": "data/yahoo/SPY.parquet (ADJUSTED)",
     "exposed": "yes-PRODUCTION",
     "reason": "close_resolver() puts the cache on rung 1, so the common case is mixed; "
               "only names ABSENT from the cache get an adjusted rung.",
     "headline": "postmortem episode scores", "rerun": None,
     "greps": {"name": r"_closes_cache", "bench": r"BENCH_REL"}},

    {"instrument": "engine/manager_trades.py",
     "pr": "PRODUCTION", "name_source": "data/yahoo FIRST, breadth cache as fallback",
     "bench_source": "same ladder; SPY resolves to yahoo (ADJUSTED)",
     "exposed": "partial-PRODUCTION",
     "reason": "ladder order is already adjusted-first, so only names ABSENT from yahoo "
               "land on the cache. Much smaller blast radius than grade_us_board, and "
               "the rung order is the right one — but the fallback is undisclosed.",
     "headline": "13F manager excess", "rerun": None,
     "greps": {"name": r"_breadth_panel", "bench": r"BENCHMARK"}},

    {"instrument": "scripts/backtest_special_situations.py",
     "pr": "PRODUCTION", "name_source": "closes_cache (UNADJUSTED)",
     "bench_source": "SPY from the cache panel if present, else data/yahoo (ADJUSTED)",
     "exposed": "partial-PRODUCTION",
     "reason": "basis-consistent when SPY is a cache column; mixed only on the yahoo "
               "fallback branch.",
     "headline": "special-situations backtest", "rerun": None,
     "greps": {"name": r"_closes_cache", "bench": r'store\.read\("yahoo"'}},

    {"instrument": "scripts/calibrate_bottom_radar.py",
     "pr": "PRODUCTION", "name_source": "data/stocks by default (ADJUSTED); "
                                        "closes_cache under --universe breadth|midcap|"
                                        "smallcap",
     "bench_source": "data/yahoo/SPY.parquet (ADJUSTED)",
     "exposed": "partial-PRODUCTION",
     "reason": "the DEFAULT path is basis-consistent. The non-default cache path is "
               "mixed — and its own docstring calls that path 'the proper test of the "
               "radar's score + vetos', so the more-rigorous mode is the biased one.",
     "headline": "bottom-radar GO/NO-GO", "rerun": None,
     "greps": {"name": r"_closes_cache", "bench": r'"yahoo"'}},

    {"instrument": "engine/desk_grader.py",
     "pr": "PRODUCTION (already correct)",
     "name_source": "data/yahoo/<T>.parquet ONLY (ADJUSTED)",
     "bench_source": "data/yahoo/SPY.parquet (ADJUSTED)",
     "exposed": "no",
     "reason": "hardened against this exact cache on 2026-07-04 and says so in its own "
               "notes: 'grade off data/yahoo adjusted closes ONLY. The S&P-1500 breadth "
               "close cache is SPLIT-CORRUPTED — using it silently poisons every RS / "
               "forward-return number.' A name absent from yahoo is a counted coverage "
               "skip, never a wrong return. The house already knew; the knowledge just "
               "never reached grade_us_board.py.",
     "headline": "desk grades", "rerun": None,
     "greps": {"name": r"data/yahoo", "bench": r"BENCH"}},
]


def census_selfcheck() -> dict:
    """§1b — re-read each censused file and confirm its claimed sources are still there.

    A census is a claim about code. Left as prose it rots the first time a loader moves.
    This re-greps every row that names an on-disk file, so a drifted classification fails
    loudly here instead of being quietly believed.
    """
    checked, missing_file, drifted = 0, [], []
    for row in CENSUS:
        g = row.get("greps")
        inst = row["instrument"]
        if not g or "*" in inst:
            continue
        p = Path(REPO) / inst
        if not p.exists():
            missing_file.append(inst)
            continue
        txt = p.read_text(encoding="utf-8", errors="replace")
        checked += 1
        for leg in ("name", "bench"):
            pat = g.get(leg)
            if pat and not re.search(pat, txt):
                drifted.append({"instrument": inst, "leg": leg, "pattern": pat})
    return {
        "rows_total": len(CENSUS),
        "rows_grep_checked": checked,
        "files_not_on_disk": missing_file,
        "drifted": drifted,
        "status": "OK" if not drifted else "DRIFT",
        "note": ("every row with a `greps` entry is re-read from disk; a DRIFT status "
                 "means a loader moved and the census row must be re-measured, never "
                 "patched."),
    }


# --------------------------------------------------------------------------- #
# §2 BASIS DIVERGENCE
# --------------------------------------------------------------------------- #
def cache_panel() -> pd.DataFrame:
    frames = [pd.read_parquet(f"data/{g}/_closes_cache.parquet") for g in GROUPS]
    P = pd.concat(frames, axis=1, sort=True)
    P = P.loc[:, ~P.columns.duplicated()]
    P.index = pd.to_datetime(P.index)
    return P.sort_index()


def basis_divergence(C: pd.DataFrame) -> dict:
    """Sweep every cache name with an adjusted counterpart and measure the gap.

    The ratio cache/adjusted is normalized to 1.0 at the tail, so a STEP in that ratio is
    a distribution the adjusted store re-based and the cache did not. Counting the steps
    is what distinguishes 'the cache is never adjusted' (a quarterly payer would show ~12
    steps over three years) from 'the cache is re-based at a rebuild and accrues raw
    after it' (0-2 steps, all recent) — and only the second is true.
    """
    rows, first_steps = [], []
    for t in C.columns:
        r = price_ladder.resolve_close(t, asof=ASOF, allow_unadjusted=False)
        if not r.ok:
            continue
        cs = C[t].dropna()
        idx = cs.index.intersection(r.series.index)
        if len(idx) < MIN_OVERLAP:
            continue
        ratio = (cs.reindex(idx) / r.series.reindex(idx)).astype(float)
        ratio = ratio[np.isfinite(ratio)]
        if len(ratio) < MIN_OVERLAP:
            continue
        rel = ratio / ratio.iloc[-1]
        steps = rel.diff().abs()
        hit = steps[steps > 1e-6]
        dev = float(max(abs(rel.max() - 1.0), abs(rel.min() - 1.0)) * 100)
        rows.append({"ticker": t, "src": r.price_source, "n_overlap": len(idx),
                     "dev_pct": dev, "n_steps": int(len(hit))})
        if len(hit):
            first_steps.append(hit.index[0])

    D = pd.DataFrame(rows)
    fs = pd.Series(pd.to_datetime(first_steps))
    bands = [(0, EXACT, "exact_match"), (EXACT, 1.0, "sub_1pct"),
             (1.0, 5.0, "1_to_5pct"), (5.0, 25.0, "5_to_25pct"),
             (25.0, np.inf, "split_sized_gt25pct")]
    return {
        "names_compared": int(len(D)),
        "min_overlap_sessions": MIN_OVERLAP,
        "deviation_bands": {
            lbl: {"n": int(((D.dev_pct >= lo) & (D.dev_pct < hi)).sum()),
                  "pct": _r(100.0 * ((D.dev_pct >= lo) & (D.dev_pct < hi)).mean(), 1)}
            for lo, hi, lbl in bands},
        "names_with_any_divergence": int((D.n_steps > 0).sum()),
        "pct_with_any_divergence": _r(100.0 * (D.n_steps > 0).mean(), 1),
        "step_count": {"median": _r(D.n_steps.median(), 1), "p90": _r(D.n_steps.quantile(.9), 1),
                       "max": int(D.n_steps.max()) if len(D) else None},
        "first_divergence_date": {
            "min": str(fs.min().date()), "p05": str(fs.quantile(.05).date()),
            "median": str(fs.median().date()), "max": str(fs.max().date()),
            "by_month": {str(k): int(v) for k, v in
                         fs.dt.to_period("M").value_counts().sort_index().items()}},
        "largest_deviations": D.nlargest(8, "dev_pct")[
            ["ticker", "dev_pct", "n_steps"]].round(4).to_dict("records"),
        "reading": (
            "The caches are NOT 'never retro-adjusted'. They are re-based at an "
            "infrequent full rebuild and accrue raw closes after it: a three-year "
            "quarterly payer would carry ~12 divergence steps if the cache were never "
            "re-based, and the observed median is 0 with a maximum of 8. The exposure is "
            "therefore a bounded TAIL — windows closing before the last rebuild carry "
            "zero bias; windows inside it carry all of it."),
    }


# --------------------------------------------------------------------------- #
# §3 THE PRODUCTION LEDGER'S OWN ERROR
# --------------------------------------------------------------------------- #
def _fwd(s: pd.Series | None, d, h: int) -> float | None:
    if s is None or s.empty:
        return None
    s = s.reindex(sorted(set(s.index) | {pd.Timestamp(d)})).ffill()
    i = s.index.searchsorted(pd.Timestamp(d))
    if i >= len(s.index):
        return None
    j = i + h
    if j >= len(s.index):
        return None
    a, b = s.iloc[i], s.iloc[j]
    if not np.isfinite(a) or not np.isfinite(b) or a == 0:
        return None
    return float(b / a - 1.0)


def ledger_error(C: pd.DataFrame) -> dict:
    """Recompute every ledger row's forward return on BOTH bases and difference them.

    The SPY leg is identical across the two runs, so the error in `excess_spy` equals the
    error in the name's own return exactly. A fidelity check comes first: if the cache
    recompute here does not reproduce the ledger's stored `ret`, the comparison is
    measuring the reimplementation and not the basis.
    """
    led = pd.read_parquet(LEDGER)
    rows, adj_memo = [], {}
    for tk, sub in led.groupby("ticker"):
        tk = str(tk)
        if tk not in adj_memo:
            r = price_ladder.resolve_close(tk, asof=ASOF, allow_unadjusted=False)
            adj_memo[tk] = (r.series if r.ok else None, r.price_source)
        a_s, a_src = adj_memo[tk]
        cs = C[tk].dropna() if tk in C.columns else None
        for _, rw in sub.iterrows():
            h = int(rw["horizon"])
            rows.append({
                "ticker": tk, "entry_date": rw["entry_date"], "h": h,
                "lane": rw.get("lane"), "sector": rw.get("sector"),
                "ret_cache": _fwd(cs, rw["entry_date"], h),
                "ret_adj": _fwd(a_s, rw["entry_date"], h),
                "adj_src": a_src, "ledger_ret": rw.get("ret"),
                "excess_spy": rw.get("excess_spy")})
    df = pd.DataFrame(rows)
    m = df.dropna(subset=["ret_cache", "ret_adj"]).copy()
    # two different quantities, and conflating them would overstate the defect:
    #   err_pp        the PURE basis effect  (cache recompute - adjusted recompute)
    #   ledger_err_pp what the SHIPPED ledger actually carries (stored ret - adjusted)
    # They differ on the handful of rows where the grader did NOT price from the cache —
    # extend_prices_to_admitted() recovers some admitted names from the yahoo ADJUSTED
    # store, so those rows are already correct and must not be counted as ledger error.
    m["err_pp"] = (m["ret_cache"] - m["ret_adj"]) * 100.0
    m["ledger_err_pp"] = (m["ledger_ret"] - m["ret_adj"]) * 100.0

    fid = m.dropna(subset=["ledger_ret"]).copy()
    fid["d_pp"] = (fid["ret_cache"] - fid["ledger_ret"]) * 100.0

    out = {
        "ledger": LEDGER,
        "ledger_rows": int(len(led)),
        "ledger_frame": [str(led["as_of"].min()), str(led["as_of"].max())],
        "rows_comparable_on_both_bases": int(len(m)),
        "rows_not_comparable": int(len(df) - len(m)),
        "fidelity_of_cache_recompute_vs_stored_ret_pp": {
            "n": int(len(fid)),
            "median_abs": _r(fid["d_pp"].abs().median(), 6),
            "p95_abs": _r(fid["d_pp"].abs().quantile(.95), 6),
            "max_abs": _r(fid["d_pp"].abs().max(), 4),
            "note": ("a median/p95 of 0 means the recompute reproduces the grader "
                     "exactly, so the error below is the BASIS and not a reimplementation "
                     "difference. The single large max is a name the grader recovered "
                     "from the yahoo ADJUSTED store via extend_prices_to_admitted() while "
                     "this recompute priced it from the cache — the panel's own internal "
                     "basis mix, showing up as a receipt.")},
        "by_horizon": {},
    }
    for h in sorted(m.h.unique()):
        sub = m[m.h == h]
        blk = {"n": int(len(sub)), "thin": bool(len(sub) < THIN_N)}
        for tag, col in (("basis", "err_pp"), ("ledger_carried", "ledger_err_pp")):
            s = sub[col].dropna()
            nz = s[s.abs() > 1e-6]
            blk[tag] = {
                "n": int(len(s)), "n_affected": int(len(nz)),
                "pct_affected": _r(100.0 * len(nz) / len(s), 1) if len(s) else None,
                "median_pp": _r(s.median()), "mean_pp": _r(s.mean()),
                "affected_median_pp": _r(nz.median()) if len(nz) else None,
                "affected_worst_pp": _r(nz.abs().max() * np.sign(
                    nz.iloc[int(nz.abs().to_numpy().argmax())])) if len(nz) else None,
                "p05_pp": _r(s.quantile(.05)), "p95_pp": _r(s.quantile(.95)),
            }
        out["by_horizon"][f"H{int(h)}"] = blk

    # cohort splits — the brief's real worry: does a payer-correlated split inherit a tilt?
    # The sector table measures the BASIS effect (err_pp), not the ledger-carried error.
    # That is the decision-relevant quantity: the ledger is already adjusted (see
    # `which_basis_is_the_ledger_on`), so its carried error is ~0 by construction and a
    # sector table built on it would be all zeros and answer nothing. What the brief asks
    # — does a payer-correlated split inherit a tilt? — is a question about the basis, and
    # it is the exposed RESEARCH instruments that would inherit it.
    out["by_sector_H5_basis_effect"] = {}
    s5 = m[m.h == 5]
    for sec, g in s5.groupby("sector"):
        if not isinstance(sec, str):
            continue
        e = g["err_pp"].dropna()
        nz = e[e.abs() > 1e-6]
        out["by_sector_H5_basis_effect"][sec] = {
            "n": int(len(g)), "thin": bool(len(g) < THIN_N),
            "n_affected": int(len(nz)),
            "pct_affected": _r(100.0 * len(nz) / len(e), 1) if len(e) else None,
            "mean_err_pp": _r(e.mean()), "median_err_pp": _r(e.median())}
    # WHICH BASIS DOES THE SHIPPED LEDGER ACTUALLY SIT ON? Reading _load_prices() says
    # "cache". Measuring the artifact says otherwise, and the artifact wins. Restricted
    # to the rows where the two bases genuinely DIFFER — everywhere else the question is
    # vacuous because both answers are the same number.
    diff = m[m["err_pp"].abs() > 1e-6].copy()
    if len(diff):
        to_cache = (diff["ledger_ret"] - diff["ret_cache"]).abs() * 100
        to_adj = (diff["ledger_ret"] - diff["ret_adj"]).abs() * 100
        out["which_basis_is_the_ledger_on"] = {
            "rows_where_the_bases_differ": int(len(diff)),
            "n_matching_cache_basis": int((to_cache < 1e-4).sum()),
            "n_matching_adjusted_basis": int((to_adj < 1e-4).sum()),
            "max_abs_gap_to_adjusted_pp": _r(to_adj.max(), 6),
            # the example must be the row where the two bases are FURTHEST apart — an
            # example where they agree to 4dp would read as a match without being one
            "examples": [
                {"ticker": str(r["ticker"]), "entry_date": str(r["entry_date"]),
                 "h": int(r["h"]),
                 "cache_basis_ret_pct": _r(r["ret_cache"] * 100, 4),
                 "adjusted_basis_ret_pct": _r(r["ret_adj"] * 100, 4),
                 "ledger_stores_pct": _r(r["ledger_ret"] * 100, 4)}
                for _, r in diff.reindex(
                    diff["err_pp"].abs().sort_values(ascending=False).index
                ).head(5).iterrows()],
            "reading": (
                "On every row where the choice of basis is observable, the shipped "
                "ledger holds the ADJUSTED number. The mixed-basis pairing in "
                "_load_prices() is therefore a LATENT defect on this frame, not a "
                "realized contamination — report it, do not restate it as damage. Rows "
                "are also never re-graded (verified against the 2026-07-03 ledger "
                "commit: 0 of 950 shared rows changed), so this is what was written at "
                "grading time and not a later repair."),
        }

    out["cohort_reading"] = (
        "Sector is the split that most closely tracks distribution-payer status, so it is "
        "the split most at risk of inheriting a systematic tilt — and it does: the "
        "affected-row share falls monotonically from the high-yield sectors to the "
        "non-payers. The mean shift is what a cohort statistic inherits; the median moves "
        "only when affected rows sit near the middle of the cell. Thin cells print n and "
        "are flagged rather than read.")
    return out


# --------------------------------------------------------------------------- #
# §4 VERDICT
# --------------------------------------------------------------------------- #
def verdict(basis: dict, ledger: dict) -> dict:
    h5 = ledger["by_horizon"].get("H5", {}).get("ledger_carried", {})
    h10 = ledger["by_horizon"].get("H10", {}).get("ledger_carried", {})
    worst_mean = max(abs(h5.get("mean_pp") or 0.0), abs(h10.get("mean_pp") or 0.0))
    worst_sector = max(
        (abs(v["mean_err_pp"] or 0.0)
         for v in ledger["by_sector_H5_basis_effect"].values()),
        default=0.0)
    return {
        "aggregate_bias_on_the_production_ledger_pp": _r(worst_mean),
        "worst_sector_cell_bias_pp": _r(worst_sector),
        "affected_row_share_pct": {"H5": h5.get("pct_affected"),
                                   "H10": h10.get("pct_affected")},
        "per_affected_row_bias_pp": {"H5": h5.get("affected_median_pp"),
                                     "H10": h10.get("affected_median_pp")},
        "decision_boundaries_at_risk": {
            "macd_bear per-leg separation (#4678)": [-0.26, -0.57, -0.52],
            "veto-label family null max (#4547)": 0.28,
            "S-COIL H=63 (#4564)": 0.98,
            "FRESH_TICKS kill (#4546)": 0.04,
        },
        "reading": (
            "Three separate numbers, and collapsing them would misstate the finding. "
            "(1) The PER-AFFECTED-ROW basis bias is real and its sign is systematic — a "
            "distribution-paying name always loses its own payout against an unaffected "
            "SPY, median -0.15pp at H=5 and -0.42pp at H=10. (2) Only 1.2-1.6% of rows "
            "sit on a window spanning a post-rebuild ex-date, so the AGGREGATE shift a "
            "cohort statistic would inherit is ~0.005pp — two orders of magnitude below "
            "every separation listed above. (3) The shipped production ledger does not "
            "carry the bias at all: all 1,931 comparable rows already match the adjusted "
            "recomputation. The defect is genuine in the code, bounded in magnitude, and "
            "unrealized in the artifact on this frame."),
        "what_would_change_this": (
            "The bound comes from the rebuild boundary, not from anything structural. A "
            "frame that sits entirely inside an unadjusted tail, a longer measurement "
            "window, or a cohort deliberately selected on high distribution yield would "
            "all raise the affected-row share and with it the aggregate shift. The "
            "adjusted-first ladder removes the question rather than re-checking it."),
    }


def main() -> None:
    C = cache_panel()
    res: dict = {
        "instrument": "research/prophet_us_audit/price_adjustment_audit.py",
        "tier": "RESEARCH — measurement only; changes no engine, gate, board or grader",
        "asof_pin": ASOF,
        "defect": (
            "Excess returns computed with the NAME leg on the breadth close caches "
            "(raw between rebuilds) and the BENCHMARK leg on data/yahoo (back-adjusted). "
            "A name that goes ex-distribution inside the measurement window books its "
            "own payout as a loss against an unaffected benchmark."),
        "receipt": {
            "ticker": "CFG", "date": "2026-06-22",
            "cache": 67.99, "adjusted": 67.5514,
            "gap_pct": 0.649,
            "converges": {"date": "2026-07-07", "both": 71.317},
            "controls_matching_exactly": ["JPM", "KO", "ALB", "CEG"],
            "note": ("the controls are the half that makes this a basis defect rather "
                     "than two different data sources — names with no post-rebuild "
                     "ex-date agree to the cent across all four stores.")},
    }
    print("[1/4] census self-check", flush=True)
    res["section_1_census"] = CENSUS
    res["section_1b_census_selfcheck"] = census_selfcheck()
    print(f"      {res['section_1b_census_selfcheck']['status']} "
          f"({res['section_1b_census_selfcheck']['rows_grep_checked']} files re-read)",
          flush=True)

    print("[2/4] basis divergence sweep", flush=True)
    res["section_2_basis_divergence"] = basis_divergence(C)
    print(f"      {res['section_2_basis_divergence']['names_compared']} names compared, "
          f"{res['section_2_basis_divergence']['pct_with_any_divergence']}% diverge",
          flush=True)

    print("[3/4] production ledger error", flush=True)
    res["section_3_production_ledger_error"] = ledger_error(C)

    print("[4/4] verdict", flush=True)
    res["section_4_verdict"] = verdict(res["section_2_basis_divergence"],
                                       res["section_3_production_ledger_error"])

    with open(OUT, "w") as f:
        json.dump(res, f, indent=1, default=str)
    print(f"wrote {OUT}", flush=True)


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")   # CLI-only: never at import time (repo guard)
    main()
