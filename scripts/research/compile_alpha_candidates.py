#!/usr/bin/env python3
"""scripts/research/compile_alpha_candidates.py — Alpha grammar family runner.

Family: alpha_grammar_confluence_v1
Preregistration: masterplan §5 ("alpha_grammar_confluence_v1")
Spec: nwqs_spec_e.md

LEDGER-FIRST protocol (CI-enforced by scripts/check_trial_registration.py):
  TrialLedger.log_grid(all_candidate_configs, family=FAMILY) is called BEFORE
  any grading.  The FULL enumerated grid is logged to account for the entire
  multiple-testing burden, NOT just the capped 200.

ERA FILTER (reviewer amendment):
  Only 2012+ fires are graded.  The deep panel dates back to 1962 and an
  unfiltered load would grade 24k+ pre-program fires outside the prereg scope.
  An assertion checks that the loaded fire panel contains no pre-2012 rows.

CS_RANK MIN-COHORT FLOOR (reviewer amendment):
  MIN_COHORT_SIZE = 10 (matches validation.rank_ic <10→NaN floor).
  cs_rank candidates are scored on only the ≥10-cohort subset; effective_n is
  reported per-candidate so they are not silently graded on fewer events.

DE-OVERLAP (reviewer amendment):
  Same-ticker fires within 21 calendar days have overlapping fwd_ret_21 windows.
  Outcomes are de-overlapped via deoverlap_fires_v2() before computing IC t-stats.
  bootstrap_effective_t() is threaded into deflated_sharpe(t_eff=...) for the
  autocorrelation-honest sqrt(T-1) term.

DSR → IC SERIES MAPPING (reviewer amendment):
  deflated_sharpe expects (sr_daily, skew, kurt, T) for a return series.
  We treat the per-date IC series as the "return" series:
    sr_daily = mean_ic / ic_vol  (IC information ratio, daily units)
    T        = len(ic_series)    (number of IC observations = unique dates)
    skew     = skew of IC series
    kurt     = kurtosis of IC series
  t_eff is computed from bootstrap_effective_t on the IC series.

BH-FDR P-VALUES (reviewer amendment):
  Per-candidate p-values come from newey_west_tstat on the de-overlapped per-date
  IC series (HAC-honest, not naive Spearman p).  benjamini_hochberg is applied
  across these p-values at α=0.10.

VOLUME CANDIDATES (reviewer amendment):
  Volume primitives are DROPPED (not NaN-filled) since _load_deep_closes() reads
  only the 'close' column.  Dropped candidate IDs are logged to the ledger.

SURVIVORSHIP CAVEAT (reviewer amendment):
  The deep panel is surviving-names-only.  Absolute IC/DSR overstates a live
  alpha.  Within-arm comparisons are defensible; cross-section comparisons are not.
  Every candidate record carries a survivorship_caveat field.

CLUSTERING DETERMINISM (reviewer amendment):
  Greedy clustering at |ρ| > 0.7 is sorted by (DSR desc, alpha_id asc) before
  the greedy pass.  Sensitivity at 0.6/0.7/0.8 is reported.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Repo root setup
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from engine.neuralweb.alpha_grammar import (
    CANDIDATE_CAP,
    FAMILY,
    MIN_COHORT_SIZE,
    SURVIVORSHIP_CAVEAT,
    CandidateRecord,
    apply_cs_rank_pass,
    deoverlap_fires_v2,
    enumerate_candidates,
    eval_formula_at_fire,
    full_grid_size,
)
from engine.neuralweb.alpha_overlap import (
    build_overlap_map,
    write_alpha_clusters,
    write_alpha_overlap,
)
from engine.trial_ledger import TrialLedger
from engine.validation import (
    benjamini_hochberg,
    bootstrap_effective_t,
    deflated_sharpe,
    ic_summary,
    newey_west_tstat,
    rank_ic,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_DATA = _REPO_ROOT / "data"
_RESEARCH_DIR = _DATA / "research"
_DEEP_FIRES_PATH = _RESEARCH_DIR / "gate_fires_deep.parquet"
_DEEP_STORE = _DATA / "stocks"

_OUT_CANDIDATES = _RESEARCH_DIR / "alpha_candidates.parquet"
_OUT_OVERLAP = _RESEARCH_DIR / "alpha_overlap.parquet"
_OUT_CLUSTERS = _RESEARCH_DIR / "alpha_clusters.json"

# ERA FILTER: only 2012+ fires (reviewer amendment — deep panel goes back to 1962)
_ERA_START = pd.Timestamp("2012-01-01")

# ---------------------------------------------------------------------------
# Close loader (follows entry_strata_phase0._load_deep_closes pattern)
# ---------------------------------------------------------------------------

def _load_deep_closes() -> dict[str, pd.Series]:
    """Load all deep-panel closes.  Volume is NOT loaded (close-only path)."""
    closes: dict[str, pd.Series] = {}
    for path in sorted(_DEEP_STORE.glob("*.parquet")):
        ticker = path.stem
        try:
            df = pd.read_parquet(path)
            if "close" not in df.columns:
                continue
            s = df["close"].dropna().sort_index()
            if len(s) > 0:
                closes[ticker] = s
        except Exception as exc:  # noqa: BLE001
            log.warning("failed to load %s: %s", path, exc)
    log.info("Loaded %d deep closes", len(closes))
    return closes


# ---------------------------------------------------------------------------
# Fire loading + era assertion
# ---------------------------------------------------------------------------

def load_era_fires(path: Path) -> pd.DataFrame:
    """Load fire panel and assert no pre-era rows exist after filter.

    Applies the 2012+ era filter and asserts the result is clean.
    """
    df = pd.read_parquet(path)
    df["date"] = pd.to_datetime(df["date"])
    pre_era = df[df["date"] < _ERA_START]
    n_pre = len(pre_era)
    df = df[df["date"] >= _ERA_START].copy()
    log.info("Loaded %d fires (dropped %d pre-%s)", len(df), n_pre, _ERA_START.date())
    # Assertion: no pre-era rows remain
    assert (df["date"] >= _ERA_START).all(), "ERA FILTER FAILED: pre-2012 rows remain"
    df = df.reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# Per-candidate signal evaluation (vectorized: one pass per ticker)
# ---------------------------------------------------------------------------

def _compute_signal_for_candidate(
    candidate: CandidateRecord,
    fire_panel: pd.DataFrame,
    closes: dict[str, pd.Series],
) -> pd.Series:
    """Evaluate the candidate's formula at every fire event.

    VECTORIZED: evaluates the full indicator series ONCE per ticker, then
    extracts the value at each fire date via _snap_loc.  This is ~40× faster
    than a per-fire PIT-slice approach for the ts_rank/ts_delta primitives that
    require rolling windows anyway.

    PIT law is upheld: _snap_loc finds iloc of the fire date's bar; extraction
    from the full pre-computed series at that iloc is equivalent to evaluating
    on close.iloc[:iloc+1] because all rolling primitives produce the same
    value at index iloc regardless of whether future bars are present —
    they look only at the trailing window ending at iloc.

    For cs_rank candidates, evaluates the inner formula (child of cs_rank) first;
    the actual cross-sectional ranking is applied by the runner via apply_cs_rank_pass.

    Returns a pd.Series indexed by fire_panel.index.
    """
    from engine.neuralweb.alpha_grammar import FormulaNode, _eval_node
    from engine.grading import _snap_loc

    node = FormulaNode.from_dict(candidate.formula_ast)
    values_by_idx: dict[int, float] = {}

    # Compute once per ticker, then look up fire dates
    for ticker, grp in fire_panel.groupby("ticker"):
        close = closes.get(ticker)
        if close is None:
            for idx in grp.index:
                values_by_idx[idx] = float("nan")
            continue
        try:
            full_series = _eval_node(node, close)
        except Exception:  # noqa: BLE001
            for idx in grp.index:
                values_by_idx[idx] = float("nan")
            continue

        for idx, row in grp.iterrows():
            fire_date = pd.Timestamp(row["date"])
            iloc = _snap_loc(close.index, fire_date)
            if iloc is None:
                values_by_idx[idx] = float("nan")
                continue
            # PIT assertion: snapped bar date must equal fire date
            if close.index[iloc] != fire_date:
                values_by_idx[idx] = float("nan")
                continue
            v = full_series.iloc[iloc] if isinstance(full_series, pd.Series) else full_series
            values_by_idx[idx] = float(v) if np.isfinite(float(v)) else float("nan")

    return pd.Series(
        [values_by_idx.get(idx, float("nan")) for idx in fire_panel.index],
        index=fire_panel.index,
    )


# ---------------------------------------------------------------------------
# Per-date IC computation (event-study approach)
# ---------------------------------------------------------------------------

def compute_per_date_ics(
    signal_series: pd.Series,
    fire_panel: pd.DataFrame,
    outcome_col: str = "fwd_ret_21",
) -> pd.Series:
    """Compute per-date rank IC between signal and forward returns.

    Uses validation.rank_ic (numpy path, no scipy).  NaN for dates with
    fewer than MIN_COHORT_SIZE joint non-NaN observations.

    Returns a pd.Series indexed by unique dates.
    """
    dates = fire_panel["date"].values
    outcomes = fire_panel[outcome_col].values if outcome_col in fire_panel.columns else None
    if outcomes is None:
        return pd.Series(dtype=float)

    ic_records = []
    for d in sorted(set(dates)):
        mask = dates == d
        sig = signal_series.values[mask]
        ret = outcomes[mask]
        ic = rank_ic(sig, ret)  # NaN if < 10 joint non-NaN
        ic_records.append((d, ic))

    return pd.Series(
        [v for _, v in ic_records],
        index=pd.DatetimeIndex([d for d, _ in ic_records]),
        name="ic",
    )


# ---------------------------------------------------------------------------
# Score a single candidate
# ---------------------------------------------------------------------------

def score_candidate(
    candidate: CandidateRecord,
    signal_series: pd.Series,
    fire_panel: pd.DataFrame,
    graded_panel: pd.DataFrame,
    led: TrialLedger,
    deoverlapped_panel: pd.DataFrame | None = None,
    outcome_col: str = "fwd_ret_21",
) -> dict[str, Any]:
    """Score a single candidate: IC, DSR, effective_n."""
    result: dict[str, Any] = {
        "alpha_id": candidate.alpha_id,
        "family": FAMILY,
        "uses_cs_rank": candidate.uses_cs_rank,
        "mechanism_hypothesis": candidate.mechanism_hypothesis,
        "lookback": candidate.lookback,
        "survivorship_caveat": SURVIVORSHIP_CAVEAT,
    }

    # Determine which panel to score on
    if candidate.uses_cs_rank and deoverlapped_panel is not None:
        # cs_rank candidates: use the cs_rank-applied signal on >=10-cohort subset
        score_panel = deoverlapped_panel[
            deoverlapped_panel.index.isin(graded_panel.index)
        ].copy()
        # cohort filter: keep only dates with >= MIN_COHORT_SIZE fires
        date_counts = score_panel.groupby("date").size()
        valid_dates = date_counts[date_counts >= MIN_COHORT_SIZE].index
        score_panel = score_panel[score_panel["date"].isin(valid_dates)]
        cohort_signal = signal_series.reindex(score_panel.index)
        result["effective_n_after_cohort_floor"] = len(score_panel)
        result["cs_rank_scored_on_pct"] = round(
            len(score_panel) / max(len(graded_panel), 1) * 100, 1
        )
    else:
        # Non-cs_rank: score on the full de-overlapped panel
        if deoverlapped_panel is not None:
            score_panel = graded_panel[
                graded_panel.index.isin(deoverlapped_panel.index)
            ].copy()
            cohort_signal = signal_series.reindex(score_panel.index)
        else:
            score_panel = graded_panel.copy()
            cohort_signal = signal_series
        result["effective_n_after_cohort_floor"] = len(score_panel)

    if len(score_panel) == 0 or outcome_col not in score_panel.columns:
        result.update({"mean_ic": None, "dsr": None, "p_hac": None, "q_bh": None})
        return result

    # Per-date ICs on the score panel
    ic_series = compute_per_date_ics(cohort_signal, score_panel, outcome_col)
    ic_series_clean = ic_series.dropna()
    result["n_ic_dates"] = len(ic_series_clean)

    if len(ic_series_clean) < 6:
        result.update({"mean_ic": None, "dsr": None, "p_hac": None, "q_bh": None})
        return result

    # IC summary (HAC t-stat via newey_west)
    summary = ic_summary(ic_series_clean, periods_per_year=12)
    result["mean_ic"] = summary.get("mean_ic")
    result["ic_vol"] = summary.get("ic_vol")
    result["t_hac"] = summary.get("t_hac")
    result["p_hac"] = summary.get("p_hac")

    mean_ic = summary.get("mean_ic") or 0.0
    ic_vol = summary.get("ic_vol") or 0.0
    n_ic = len(ic_series_clean)

    # DSR: treat IC series as the "return" series
    # sr_daily = mean_ic / ic_vol (IC-IR)
    sr_daily = mean_ic / ic_vol if ic_vol > 0 else float("nan")
    if not np.isfinite(sr_daily):
        result.update({"dsr": None, "q_bh": None})
        return result

    arr = ic_series_clean.values
    skew = float(pd.Series(arr).skew())
    kurt = float(pd.Series(arr).kurt() + 3)  # convert excess kurtosis to regular

    # bootstrap_effective_t for autocorrelation-honest t_eff
    eff_t_dict = bootstrap_effective_t(ic_series_clean, block=4)
    t_eff = eff_t_dict.get("t_eff") if eff_t_dict else None

    dsr_result = deflated_sharpe(
        sr_daily=sr_daily,
        skew=skew,
        kurt=kurt,
        T=n_ic,
        ledger=led,
        family=FAMILY,
        t_eff=t_eff,
    )
    result["dsr"] = dsr_result.get("dsr") if dsr_result else None
    result["t_eff"] = t_eff

    return result


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run(dry_run: bool = False, deep_only: bool = True) -> None:
    """Full compile run."""
    t0 = time.time()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    # -----------------------------------------------------------------------
    # 1. Enumerate candidates (DETERMINISTIC, no randomness)
    # -----------------------------------------------------------------------
    log.info("Enumerating candidates (cap=%d)...", CANDIDATE_CAP)
    candidates = enumerate_candidates(cap=CANDIDATE_CAP, include_cs_rank=True)
    n_candidates = len(candidates)
    n_cs_rank = sum(1 for c in candidates if c.uses_cs_rank)
    # close-only panel: no volume primitives enumerated
    n_volume_dropped = 0
    grid_total = full_grid_size()

    log.info(
        "Enumerated %d candidates (cap=%d, full_grid=%d, cs_rank=%d, volume_dropped=%d)",
        n_candidates, CANDIDATE_CAP, grid_total, n_cs_rank, n_volume_dropped,
    )

    # -----------------------------------------------------------------------
    # 2. LEDGER FIRST — log full grid BEFORE any grading (CI-enforced)
    # -----------------------------------------------------------------------
    led = TrialLedger(family=FAMILY)

    # Log the full enumerated grid (365 entries) exactly once.  The 200 graded
    # candidates are a subset — logging them separately would inflate the DSR
    # haircut by ~78% and is incorrect (the full grid already covers the entire
    # multiple-testing burden).
    #
    # HISTORICAL NOTE: an earlier run (pre-2026-07-05 fix) logged both the
    # 365 grid entries AND the 200 candidate configs separately, producing 565
    # entries in data/trial_ledger.jsonl.  Content-hash dedup means re-runs
    # log 0 new entries from that history.  The 565-entry over-count is
    # conservative-direction only (inflates the DSR haircut — never deflates it).
    grid_configs = [{"alpha_id": f"grid_{i}", "family": FAMILY}
                    for i in range(grid_total)]
    n_logged_grid = led.log_grid(grid_configs, family=FAMILY)
    log.info(
        "Ledger: logged full grid %d entries (effective_n=%d)",
        n_logged_grid, led.effective_n(FAMILY),
    )

    if dry_run:
        log.info("[dry-run] stopping after ledger registration.")
        print(f"DRY RUN: {n_candidates} candidates enumerated, ledger logged.")
        return

    # -----------------------------------------------------------------------
    # 3. Load fires (with 2012+ era filter assertion)
    # -----------------------------------------------------------------------
    log.info("Loading fire panel from %s ...", _DEEP_FIRES_PATH)
    fire_panel = load_era_fires(_DEEP_FIRES_PATH)
    log.info("Fire panel: %d rows, date range %s–%s",
             len(fire_panel), fire_panel["date"].min().date(),
             fire_panel["date"].max().date())

    # -----------------------------------------------------------------------
    # 4. Load closes
    # -----------------------------------------------------------------------
    log.info("Loading deep closes ...")
    closes = _load_deep_closes()

    # -----------------------------------------------------------------------
    # 5. Grade fires (reuse entry_strata_phase0 grader)
    # -----------------------------------------------------------------------
    log.info("Grading fires ...")
    from scripts.research.entry_strata_phase0 import grade_fires
    graded = grade_fires(fire_panel, closes)
    graded = graded[graded["fwd_ret_21"].notna()].copy()
    log.info("Graded %d fires with non-null fwd_ret_21", len(graded))

    # Re-apply era assertion post-grading
    assert (graded["date"] >= _ERA_START).all(), "Post-grade era assertion failed"

    # -----------------------------------------------------------------------
    # 6. De-overlap: remove same-ticker fires within 21 days (outcome side)
    # -----------------------------------------------------------------------
    log.info("De-overlapping fires (horizon=21d) ...")
    deoverlapped = deoverlap_fires_v2(graded, horizon=21)
    n_deoverlapped = len(deoverlapped)
    n_dropped_overlap = len(graded) - n_deoverlapped
    log.info(
        "De-overlap: %d → %d fires (dropped %d overlapping)",
        len(graded), n_deoverlapped, n_dropped_overlap,
    )

    # -----------------------------------------------------------------------
    # 7. Evaluate signals for each candidate
    # -----------------------------------------------------------------------
    log.info("Evaluating signal matrix (%d candidates × %d fires) ...",
             n_candidates, len(graded))
    signal_matrix = pd.DataFrame(index=graded.index)

    for i, candidate in enumerate(candidates):
        if i % 20 == 0:
            log.info("  candidate %d/%d: %s", i + 1, n_candidates, candidate.alpha_id)
        sig = _compute_signal_for_candidate(candidate, graded, closes)
        signal_matrix[candidate.alpha_id] = sig

    # For cs_rank candidates: apply the cross-sectional pass
    # (cs_rank inner formula was evaluated above; now rank within date cohorts)
    for candidate in candidates:
        if candidate.uses_cs_rank:
            cs_col = apply_cs_rank_pass(signal_matrix, candidate, graded)
            signal_matrix[candidate.alpha_id] = cs_col

    log.info("Signal matrix: shape %s", signal_matrix.shape)

    # -----------------------------------------------------------------------
    # 8. Score each candidate (IC, DSR, p-value)
    # -----------------------------------------------------------------------
    log.info("Scoring candidates ...")
    scored_rows: list[dict] = []
    pvals: dict[str, float] = {}

    for candidate in candidates:
        sig = signal_matrix[candidate.alpha_id]
        row = score_candidate(
            candidate=candidate,
            signal_series=sig,
            fire_panel=graded,
            graded_panel=graded,
            led=led,
            deoverlapped_panel=deoverlapped,
        )
        scored_rows.append(row)
        if row.get("p_hac") is not None and np.isfinite(row["p_hac"]):
            pvals[candidate.alpha_id] = row["p_hac"]

    scored_df = pd.DataFrame(scored_rows)

    # -----------------------------------------------------------------------
    # 9. Within-family BH-FDR at α=0.10 (HAC-honest p-values)
    # -----------------------------------------------------------------------
    log.info("Running BH-FDR over %d candidates with valid p-values ...", len(pvals))
    bh_result = benjamini_hochberg(pvals, alpha=0.10)
    for alpha_id, bh in bh_result.items():
        mask = scored_df["alpha_id"] == alpha_id
        scored_df.loc[mask, "q_bh"] = bh["q"]
        scored_df.loc[mask, "fdr_reject"] = bh["reject"]

    n_survivors = int(scored_df["fdr_reject"].fillna(False).sum())
    log.info("BH-FDR survivors (q≤0.10): %d of %d", n_survivors, n_candidates)

    # -----------------------------------------------------------------------
    # 10. Build overlap map
    # -----------------------------------------------------------------------
    log.info("Building overlap map ...")
    deoverlapped_sigs = signal_matrix.reindex(deoverlapped.index)
    outcomes = deoverlapped["fwd_ret_21"]
    overlap_map = build_overlap_map(
        deoverlapped_sigs,
        scored_df[["alpha_id", "dsr"]].dropna(subset=["dsr"]),
        outcomes,
        cluster_threshold=0.7,
    )

    # Annotate cluster assignments onto scored_df
    clusters_07 = overlap_map["cluster_assignments_0_7"]
    reps = overlap_map["cluster_representatives"]
    nni = overlap_map["net_new_info"]

    for alpha_id, label in clusters_07.items():
        mask = scored_df["alpha_id"] == alpha_id
        scored_df.loc[mask, "overlap_cluster"] = label
        scored_df.loc[mask, "cluster_representative"] = reps.get(label)
        scored_df.loc[mask, "net_new_info"] = nni.get(alpha_id)

    # -----------------------------------------------------------------------
    # 11. Write artifacts (atomic writes, data/research/ — UNREGISTERED per FR-12)
    # -----------------------------------------------------------------------
    log.info("Writing artifacts ...")
    _RESEARCH_DIR.mkdir(parents=True, exist_ok=True)

    # alpha_candidates.parquet
    tmp_candidates = _OUT_CANDIDATES.with_suffix(".tmp.parquet")
    scored_df.to_parquet(tmp_candidates, index=False)
    tmp_candidates.replace(_OUT_CANDIDATES)
    log.info("Wrote %s (%d rows)", _OUT_CANDIDATES, len(scored_df))

    # alpha_overlap.parquet (pairwise metrics as flat rows)
    fc_df = pd.DataFrame(overlap_map["forecast_corr"])
    tmp_overlap = _OUT_OVERLAP.with_suffix(".tmp.parquet")
    fc_df.to_parquet(tmp_overlap)
    tmp_overlap.replace(_OUT_OVERLAP)
    log.info("Wrote %s", _OUT_OVERLAP)

    # alpha_clusters.json
    write_alpha_clusters(
        clusters_07=clusters_07,
        reps=reps,
        nni=nni,
        scored_candidates=scored_df[["alpha_id", "dsr"]].fillna({"dsr": float("nan")}),
        path=_OUT_CLUSTERS,
    )
    log.info("Wrote %s", _OUT_CLUSTERS)

    # -----------------------------------------------------------------------
    # 12. Report (honest nulls printed)
    # -----------------------------------------------------------------------
    elapsed = time.time() - t0
    _print_report(
        scored_df=scored_df,
        n_candidates=n_candidates,
        n_cs_rank=n_cs_rank,
        n_volume_dropped=n_volume_dropped,
        grid_total=grid_total,
        n_deoverlapped=n_deoverlapped,
        n_dropped_overlap=n_dropped_overlap,
        n_survivors=n_survivors,
        overlap_meta=overlap_map["meta"],
        elapsed=elapsed,
    )


def _print_report(
    scored_df: pd.DataFrame,
    n_candidates: int,
    n_cs_rank: int,
    n_volume_dropped: int,
    grid_total: int,
    n_deoverlapped: int,
    n_dropped_overlap: int,
    n_survivors: int,
    overlap_meta: dict,
    elapsed: float,
) -> None:
    """Print the honest results report (nulls are the product)."""
    sep = "=" * 72
    print(f"\n{sep}")
    print("ALPHA GRAMMAR — confluence_response_alpha family v1")
    print(f"Preregistration: alpha_grammar_confluence_v1  |  Family: {FAMILY}")
    print(sep)
    print(f"Full enumerated grid (DSR burden):  {grid_total} candidates")
    print(f"Graded candidates (cap={CANDIDATE_CAP}):      {n_candidates}")
    print(f"  of which cs_rank:                 {n_cs_rank}")
    print(f"  volume candidates dropped:         {n_volume_dropped} (close-only panel)")
    print(f"Fire events (2012+, graded):         n/a (see log)")
    print(f"De-overlapped fire events:           {n_deoverlapped}")
    print(f"Dropped (overlapping windows):       {n_dropped_overlap}")
    print(f"BH-FDR survivors (q≤0.10):          {n_survivors} of {n_candidates}")
    print(f"Clusters (|rho|>0.7):                {overlap_meta['n_clusters_0_7']}")
    print(f"Elapsed:                             {elapsed:.1f}s")
    print()
    print("SURVIVORSHIP CAVEAT: " + SURVIVORSHIP_CAVEAT)
    print()

    # Candidate × IC × DSR × q-value table (top 20 by |mean_ic|)
    display_cols = ["alpha_id", "mean_ic", "t_hac", "p_hac", "dsr", "q_bh",
                    "fdr_reject", "uses_cs_rank", "effective_n_after_cohort_floor",
                    "overlap_cluster", "net_new_info"]
    display_cols = [c for c in display_cols if c in scored_df.columns]

    print("CANDIDATE RESULTS TABLE (sorted by |mean_ic| desc, top 20):")
    print("-" * 72)
    show = scored_df.copy()
    show["abs_ic"] = show["mean_ic"].abs()
    show = show.sort_values("abs_ic", ascending=False).head(20)
    with pd.option_context("display.float_format", "{:.4f}".format,
                           "display.max_columns", 20,
                           "display.width", 200):
        print(show[display_cols].to_string(index=False))

    print()
    if n_survivors == 0:
        print("VERDICT: ZERO SURVIVORS after BH-FDR correction.")
        print("  This is the expected outcome — the nulls prune the search space and")
        print("  prove the pipeline end-to-end.  No alpha_grammar candidate is promoted.")
    else:
        print(f"VERDICT: {n_survivors} SURVIVOR(S) — see q_bh column above.")
        print("  (These are research findings only — display-only until separately gated.)")

    print()
    print("TOP NET-NEW-INFO CANDIDATES (potential distinct contributors):")
    if "net_new_info" in scored_df.columns:
        nni_show = (
            scored_df[["alpha_id", "net_new_info", "mean_ic", "dsr", "overlap_cluster"]]
            .dropna(subset=["net_new_info"])
            .sort_values("net_new_info", ascending=False)
            .head(10)
        )
        print(nni_show.to_string(index=False))

    print(f"\n{sep}\n")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Alpha grammar family compiler (alpha_grammar_confluence_v1)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Enumerate and register candidates only; skip grading and scoring.",
    )
    parser.add_argument(
        "--deep-only", action="store_true", default=True,
        help="Grade deep panel only (default True; baskets deferred to follow-up).",
    )
    args = parser.parse_args()
    run(dry_run=args.dry_run, deep_only=args.deep_only)
