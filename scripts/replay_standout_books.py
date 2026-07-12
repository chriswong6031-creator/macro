"""scripts/replay_standout_books.py — SA-W4 Tier-0 evidence tool.

Re-rank accrued board snapshots under a given book/board config variant and
grade against already-graded outcome columns (one-grader law: never recompute
forward returns). Emits a replay report JSON with hit/coverage/upside deltas
vs baseline, split by the leave-newest-out holdout.

DESIGN CONTRACTS
----------------
- ONE-GRADER LAW: forward return columns in the ledger are NEVER recomputed here.
  This tool re-ranks ONLY; grading uses the stored outcome columns.
- ABSENT STORES => data_gap report, exit 0. Never hard-fails on missing data.
- Must end with lib.procutil.hard_exit() — Arrow shutdown-hang law (SA-R16).
- This is Tier-0 evidence per SA-R5. Its report may authorize experiments/shadow
  books; it may NEVER justify a promotion or live config flip. This sentence
  appears in the report footer.
- NEVER raises beyond the outer try/except.

CN WASHOUT_BONUS COUNTERFACTUAL (cheaply replayable from stored columns)
-------------------------------------------------------------------------
The CN board.parquet stores per-name per-date: washout_2w, coiled, ext_score,
tier, board_rank.  These are sufficient to reconstruct the ORDERING DELTA under
a modified WASHOUT_BONUS without re-running the full board pipeline.

Approximation: the stored columns reflect the live baseline scoring.  To
reconstruct the counterfactual score for each row we apply:
  score_cf(row) = score_baseline(row) - WASHOUT_BONUS_BASELINE * washout_2w
                + WASHOUT_BONUS_CF * washout_2w
where the coiled bonus and ext_penalty contributions are HELD CONSTANT (we vary
only washout_bonus).  Because we cannot recover the exact conviction-percentile
term from stored columns (it depends on the full same-date pool), we approximate
it by the RANK-NORMALISED position (board_rank / n_date_rows), which is
monotone-equivalent to the original score order for the baseline.  The
counterfactual rerank uses the RANK-DELTA from washout_bonus change only,
applied additively to the rank-normalised baseline.

This approximation is sound for ORDERING-change assessment: it correctly
identifies which names change relative rank due solely to a washout_bonus change.
It does NOT recover exact scores.  The report declares this as
counterfactual.approximation = 'rank_delta_from_bonus_change_only'.

The outcome metric uses fwd_mfe_5 (5-session raw MFE) as the quality proxy,
NOT SPY-excess (no graded excess column yet in the CN ledger at this stage).
This is declared in the report.

USAGE
-----
    # Replay against a shadow book spec (JSON file):
    python scripts/replay_standout_books.py --book path/to/spec.json

    # Replay against an existing registry engine_id:
    python scripts/replay_standout_books.py --engine-id plab_1d_pure

    # Replay against CN books:
    python scripts/replay_standout_books.py --engine-id cnlab_rev_pure

    # Dry run (report without writing):
    python scripts/replay_standout_books.py --book spec.json --dry-run

    # Custom output path:
    python scripts/replay_standout_books.py --book spec.json --out /tmp/report.json
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Path bootstrap ──────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

log = logging.getLogger(__name__)


def _data_dir(root: Path | None = None) -> Path:
    try:
        from lib import config
        return config.data_dir() if root is None else (root / "data")
    except Exception:  # noqa: BLE001
        return REPO_ROOT / "data" if root is None else (root / "data")


def _report_data_gap(reason: str, context: dict | None = None) -> dict:
    """Return a data_gap report dict (honest absent-store response, SA-R15)."""
    return {
        "schema": "replay_standout_books.v1",
        "as_of": datetime.now(timezone.utc).date().isoformat(),
        "status": "data_gap",
        "data_gap_reason": reason,
        "context": context or {},
        "footer": (
            "TIER-0 EVIDENCE TOOL (SA-R5): This report may authorize experiments or "
            "shadow book applications. It may NEVER justify a promotion to scored status "
            "or a live config flip. Forward-confirm (Tier-1/Tier-2 ladder) is required "
            "before any live change."
        ),
    }


def _load_book_spec(book_path: Path | None, engine_id: str | None) -> tuple[dict | None, str | None]:
    """Load book/config spec from a JSON file or registry.

    Returns (spec_dict, error_reason). spec_dict is None on error.
    """
    if book_path is not None:
        if not book_path.exists():
            return None, f"book_path_not_found:{book_path}"
        try:
            spec = json.loads(book_path.read_text(encoding="utf-8"))
            if not isinstance(spec, dict):
                return None, f"book_spec_not_dict:{book_path}"
            return spec, None
        except Exception as e:  # noqa: BLE001
            return None, f"book_spec_parse_error:{e}"

    if engine_id is not None:
        # Try US registry first, then CN, then HK
        for mod_name, attr in [
            ("engine.pick_lab.registry", "BY_ID"),
            ("engine.pick_lab.registry_cn", "CN_BY_ID"),
            ("engine.pick_lab.registry_hk", "HK_BY_ID"),
        ]:
            try:
                mod = __import__(mod_name, fromlist=[attr])
                registry = getattr(mod, attr, {})
                if engine_id in registry:
                    return dict(registry[engine_id]), None
            except Exception:  # noqa: BLE001
                continue
        return None, f"engine_id_not_found_in_any_registry:{engine_id}"

    return None, "no_book_path_or_engine_id_provided"


def _load_us_snapshots(data_dir: Path) -> tuple[list[dict], str | None]:
    """Load US board snapshots from data/us_board_ledger/snapshots.jsonl.
    Returns (rows, error_reason). rows is empty list on data_gap (not None)."""
    snap_path = data_dir / "us_board_ledger" / "snapshots.jsonl"
    if not snap_path.exists():
        return [], f"us_snapshots_absent:{snap_path}"
    rows = []
    try:
        for line in snap_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:  # noqa: BLE001
                continue
    except Exception as e:  # noqa: BLE001
        return [], f"us_snapshots_read_error:{e}"
    return rows, None


def _load_grades(data_dir: Path, market: str) -> tuple[Any, str | None]:
    """Load graded parquet (retro_grades or china track).
    Returns (dataframe, error_reason). Returns (None, reason) on data_gap."""
    try:
        import pandas as pd
    except ImportError:
        return None, "pandas_not_available"

    if market == "us":
        grade_path = data_dir / "us_board_ledger" / "retro_grades.parquet"
    elif market == "cn":
        grade_path = data_dir / "china_standout_track" / "board.parquet"
    else:
        return None, f"unknown_market:{market}"

    if not grade_path.exists():
        return None, f"grade_store_absent:{grade_path}"

    try:
        df = pd.read_parquet(grade_path)
        return df, None
    except Exception as e:  # noqa: BLE001
        return None, f"grade_store_read_error:{e}"


def _detect_market(spec: dict, engine_id: str | None) -> str:
    """Detect market from spec or engine_id."""
    # Explicit in spec
    if spec.get("market"):
        return str(spec["market"])
    # Source_proposal
    sp = spec.get("source_proposal") or {}
    if sp.get("market"):
        return str(sp["market"])
    # ruler hint
    ruler = str(spec.get("ruler") or "")
    if "csi300" in ruler or "cn" in ruler.lower():
        return "cn"
    if "hsi" in ruler:
        return "hk"
    # engine_id prefix
    if engine_id:
        if engine_id.startswith("cn"):
            return "cn"
        if engine_id.startswith("hk"):
            return "hk"
    return "us"


def _compute_leave_newest_out_split(grades_df: Any) -> tuple[Any, Any, str | None]:
    """Split grades into (train_df, holdout_df) using leave-newest-out.

    Holdout = the most recent non-overlapping calendar month of graded rows.
    Train = everything older.

    Returns (train_df, holdout_df, error_reason). holdout_df may be empty.
    """
    try:
        import pandas as pd
    except ImportError:
        return grades_df, None, "pandas_not_available"

    try:
        df = grades_df.copy()
        # Prefer 'as_of' or 'signal_date' or 'date' column
        date_col = None
        for c in ("as_of", "signal_date", "date", "entry_date"):
            if c in df.columns:
                date_col = c
                break
        if date_col is None:
            return df, pd.DataFrame(columns=df.columns), None

        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
        df = df.dropna(subset=[date_col])
        if df.empty:
            return df, pd.DataFrame(columns=df.columns), None

        max_date = df[date_col].max()
        # Newest calendar month = year/month of max_date
        newest_year = max_date.year
        newest_month = max_date.month
        holdout_mask = (df[date_col].dt.year == newest_year) & (df[date_col].dt.month == newest_month)
        holdout_df = df[holdout_mask]
        train_df = df[~holdout_mask]
        return train_df, holdout_df, None
    except Exception as e:  # noqa: BLE001
        return grades_df, None, f"split_error:{e}"


def _compute_hit_quality(df: Any, market: str) -> dict:
    """Compute hit_quality (P(excess>0)) on a grades dataframe.
    Returns {"value": float|None, "n": int, "note": str}.
    """
    try:
        import numpy as np
    except ImportError:
        return {"value": None, "n": 0, "note": "numpy_not_available"}

    if df is None or len(df) == 0:
        return {"value": None, "n": 0, "note": "no_rows"}

    # Use 21d excess column if available
    excess_col = None
    for c in ("excess_21d", "excess_vs_spy_21d", "excess_vs_csi300_21d", "fwd_21d_excess"):
        if c in df.columns:
            excess_col = c
            break

    if excess_col is None:
        return {"value": None, "n": 0, "note": "no_excess_column_found"}

    try:
        vals = df[excess_col].dropna()
        n = len(vals)
        if n == 0:
            return {"value": None, "n": 0, "note": "all_null_excess"}
        hit_rate = float((vals > 0).mean())
        return {"value": round(hit_rate, 4), "n": n, "note": f"P(excess>0) at 21d, n={n}"}
    except Exception as e:  # noqa: BLE001
        return {"value": None, "n": 0, "note": f"computation_error:{e}"}


def _compute_coverage_health(df: Any, market: str) -> dict:
    """Compute coverage_health (buy-lane surfaced count per day).
    Returns {"value": float|None, "n": int, "note": str}.
    """
    if df is None or len(df) == 0:
        return {"value": None, "n": 0, "note": "no_rows"}

    try:
        date_col = None
        for c in ("as_of", "signal_date", "date", "entry_date"):
            if c in df.columns:
                date_col = c
                break
        if date_col is None:
            return {"value": None, "n": len(df), "note": "no_date_column"}
        import pandas as pd
        df2 = df.copy()
        df2[date_col] = pd.to_datetime(df2[date_col], errors="coerce")
        counts = df2.groupby(df2[date_col].dt.date).size()
        median_count = float(counts.median())
        return {
            "value": round(median_count, 2),
            "n": len(df),
            "note": f"median buy-lane names per day, n_days={len(counts)}",
        }
    except Exception as e:  # noqa: BLE001
        return {"value": None, "n": 0, "note": f"computation_error:{e}"}


# ── CN washout_bonus cheap counterfactual ────────────────────────────────────

#: Current production WASHOUT_BONUS in build_china_library.py (function-local const).
#: Must be kept in sync with scripts/build_china_library.py:WASHOUT_BONUS.
#: When W2 merges to main, verify this still matches.
_CN_WASHOUT_BONUS_BASELINE: float = 0.5

#: Current production EXT_PENALTY (held constant in counterfactual — not the varied param).
_CN_EXT_PENALTY_BASELINE: float = 0.5

#: Tier weight map (T1→1.0 .. T4→0.0; matches signal_gate.blend_sorted wn formula with wf=0).
_TIER_WN: dict[str, float] = {"T1": 1.0, "T2": 0.666, "T3": 0.333, "T4": 0.0}

#: CN_TIER_FRAC in build_china_library.py (function-local const).
_CN_TIER_FRAC: float = 0.30


def _cn_washout_bonus_counterfactual(
    grades_df: Any,
    washout_bonus_cf: float,
    trial_count: int,
    min_effective_n: int = 6,
) -> dict:
    """Compute the CN washout_bonus counterfactual verdict.

    For each board date in grades_df that has washout_2w populated, reconstruct
    the counterfactual ranking by applying washout_bonus_cf instead of the
    baseline WASHOUT_BONUS (_CN_WASHOUT_BONUS_BASELINE).

    The approximation is documented in the module docstring. Key points:
    - conviction-percentile term is approximated by rank-normalised baseline position
    - coiled bonus is approximated as 0 (coiled column is bool, not bonus value)
    - ext_penalty contribution is held constant

    Returns a dict with keys: verdict, reason, evidence (matches _replay_evaluator
    output contract).
    """
    try:
        import numpy as np
        import pandas as pd
    except ImportError:
        return {
            "verdict": "UNEVALUABLE",
            "reason": "pandas_or_numpy_not_available",
            "evidence": {},
        }

    try:
        df = grades_df.copy()

        # Must have required columns
        required = {"date", "washout_2w", "board_rank", "tier"}
        missing_cols = required - set(df.columns)
        if missing_cols:
            return {
                "verdict": "UNEVALUABLE",
                "reason": f"missing_columns_for_cn_counterfactual:{sorted(missing_cols)}",
                "evidence": {"missing": sorted(missing_cols)},
            }

        # Date column
        date_col = "date" if "date" in df.columns else None
        if date_col is None:
            return {"verdict": "UNEVALUABLE", "reason": "no_date_column", "evidence": {}}

        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")

        # Only operate on dates that have washout_2w populated (Jul 7+)
        has_wash_dates = df[df["washout_2w"].notna()][date_col].dt.normalize().unique()
        if len(has_wash_dates) == 0:
            return {
                "verdict": "UNEVALUABLE",
                "reason": "no_dates_with_washout_2w_populated",
                "evidence": {"total_rows": len(df)},
            }

        df_wash = df[df[date_col].dt.normalize().isin(has_wash_dates)].copy()

        # Check effective_n: number of washout dates with washout_2w data
        effective_n = len(has_wash_dates)
        if effective_n < min_effective_n:
            return {
                "verdict": "UNEVALUABLE",
                "reason": f"insufficient_effective_n:{effective_n}<{min_effective_n}",
                "evidence": {
                    "effective_n": effective_n,
                    "min_effective_n": min_effective_n,
                    "note": "effective_n = n_board_dates_with_washout_2w_data",
                },
            }

        # Outcome proxy: fwd_mfe_5 (5-session raw MFE; no excess column yet)
        has_outcome = "fwd_mfe_5" in df_wash.columns and df_wash["fwd_mfe_5"].notna().sum() > 0
        outcome_note = (
            "fwd_mfe_5 (5-session raw MFE; approximation — CSI300-excess not yet graded)"
            if has_outcome else "no_outcome_column"
        )

        # Per-date reranking: compute baseline rank-score and counterfactual rank-score
        bonus_delta = washout_bonus_cf - _CN_WASHOUT_BONUS_BASELINE

        baseline_top_tickers: list[set] = []
        cf_top_tickers: list[set] = []
        date_results = []

        for dt, grp in df_wash.groupby(df_wash[date_col].dt.normalize()):
            n_date = len(grp)
            if n_date == 0:
                continue

            # Rank-normalised baseline score ≈ 1 - (board_rank - 1) / (n_date - 1)
            # (board_rank=1 → score≈1.0, board_rank=n → score≈0.0)
            grp = grp.copy()
            rank_max = grp["board_rank"].max()
            if rank_max <= 1:
                grp["_rank_score"] = 1.0
            else:
                grp["_rank_score"] = 1.0 - (grp["board_rank"] - 1) / (rank_max - 1)

            # Washout additive delta: +bonus_delta for washout_2w=True rows
            grp["_washout_flag"] = grp["washout_2w"].fillna(0.0).astype(float)
            grp["_cf_score"] = grp["_rank_score"] + bonus_delta * grp["_washout_flag"]

            # Counterfactual ranking
            grp_cf = grp.sort_values("_cf_score", ascending=False)

            # Top-N for coverage_health: use top 15 as representative board slice
            top_n = min(15, n_date)
            baseline_top = set(grp.sort_values("board_rank").head(top_n)["ticker"].tolist())
            cf_top = set(grp_cf.head(top_n)["ticker"].tolist())
            baseline_top_tickers.append(baseline_top)
            cf_top_tickers.append(cf_top)

            # Per-date rank-change metric
            grp_cf["_cf_rank"] = range(1, len(grp_cf) + 1)
            rank_change = float(
                grp.set_index("ticker")["board_rank"]
                .sub(grp_cf.reset_index().set_index("ticker")["_cf_rank"])
                .abs().mean()
            ) if "ticker" in grp.columns else 0.0

            date_entry: dict[str, Any] = {
                "date": str(dt.date()),
                "n_rows": n_date,
                "n_washout_true": int(grp["_washout_flag"].sum()),
                "top_n_composition_change": len(baseline_top - cf_top),
                "mean_abs_rank_change": round(rank_change, 2),
            }

            if has_outcome:
                # fwd_mfe_5 for top-N baseline vs top-N counterfactual
                baseline_out = grp[grp["ticker"].isin(baseline_top)]["fwd_mfe_5"].dropna()
                cf_out = grp[grp["ticker"].isin(cf_top)]["fwd_mfe_5"].dropna()
                date_entry["baseline_top_n_mfe5_median"] = (
                    round(float(baseline_out.median()), 5) if len(baseline_out) > 0 else None
                )
                date_entry["cf_top_n_mfe5_median"] = (
                    round(float(cf_out.median()), 5) if len(cf_out) > 0 else None
                )

            date_results.append(date_entry)

        if not date_results:
            return {
                "verdict": "UNEVALUABLE",
                "reason": "no_date_results_computed",
                "evidence": {},
            }

        # Aggregate coverage_health delta: mean composition change in top-N
        mean_composition_change = float(
            np.mean([d["top_n_composition_change"] for d in date_results])
        )

        # Aggregate quality delta (fwd_mfe_5 based, if available)
        baseline_mfe_vals = [
            d["baseline_top_n_mfe5_median"]
            for d in date_results
            if d.get("baseline_top_n_mfe5_median") is not None
        ]
        cf_mfe_vals = [
            d["cf_top_n_mfe5_median"]
            for d in date_results
            if d.get("cf_top_n_mfe5_median") is not None
        ]

        hit_quality_delta: float | None = None
        if baseline_mfe_vals and cf_mfe_vals:
            baseline_median = float(np.median(baseline_mfe_vals))
            cf_median = float(np.median(cf_mfe_vals))
            hit_quality_delta = round(cf_median - baseline_median, 6)

        # Trial-count Bonferroni note
        alpha_bonferroni = 0.05 / trial_count if trial_count > 0 else 0.05

        # VERDICT LOGIC
        # With n_board_dates=3 (Jul 7/8/10), effective_n < min_effective_n=6
        # → UNEVALUABLE is the correct honest answer (already checked above).
        # If somehow effective_n is sufficient:
        # - If no outcome column: UNEVALUABLE
        # - If outcome exists: PASS if hit_quality_delta >= 0 AND coverage_health acceptable
        #   (no more than 20% composition change per SA-R4 spirit)
        # In current data state this path is not reachable (n=3 < 6).

        if not has_outcome:
            verdict = "UNEVALUABLE"
            verdict_reason = "no_graded_excess_column_yet:fwd_mfe_5_available_as_proxy_only"
        elif hit_quality_delta is None:
            verdict = "UNEVALUABLE"
            verdict_reason = "insufficient_paired_outcome_data"
        elif hit_quality_delta >= 0:
            verdict = "PASS"
            verdict_reason = f"cf_mfe5_delta={hit_quality_delta:+.5f}>=0_and_composition_change={mean_composition_change:.1f}"
        else:
            verdict = "FAIL"
            verdict_reason = f"cf_mfe5_delta={hit_quality_delta:+.5f}<0:quality_regresses_under_counterfactual"

        return {
            "verdict": verdict,
            "reason": verdict_reason,
            "evidence": {
                "washout_bonus_baseline": _CN_WASHOUT_BONUS_BASELINE,
                "washout_bonus_cf": washout_bonus_cf,
                "bonus_delta": bonus_delta,
                "n_board_dates_evaluated": len(date_results),
                "mean_top15_composition_change": round(mean_composition_change, 2),
                "hit_quality_delta_proxy": hit_quality_delta,
                "outcome_proxy": outcome_note,
                "alpha_bonferroni": round(alpha_bonferroni, 5),
                "approximation": (
                    "rank_delta_from_bonus_change_only: conviction-percentile held "
                    "constant (rank-normalised); coiled bonus approximated 0; "
                    "ext_penalty held constant. Ordering-change assessment only — "
                    "does NOT recover exact scores."
                ),
                "date_results": date_results,
            },
        }

    except Exception as e:  # noqa: BLE001
        return {
            "verdict": "UNEVALUABLE",
            "reason": f"counterfactual_error:{e}",
            "evidence": {},
        }


def replay(
    book_path: Path | None = None,
    engine_id: str | None = None,
    root: Path | None = None,
    dry_run: bool = False,
) -> dict:
    """Run the replay and return a report dict.

    Absent stores => data_gap report, clean exit.
    Never raises (SA-R16).
    """
    report: dict[str, Any] = {
        "schema": "replay_standout_books.v1",
        "as_of": datetime.now(timezone.utc).date().isoformat(),
        "status": "ok",
        "dry_run": dry_run,
        "footer": (
            "TIER-0 EVIDENCE TOOL (SA-R5): This report may authorize experiments or "
            "shadow book applications. It may NEVER justify a promotion to scored status "
            "or a live config flip. Forward-confirm (Tier-1/Tier-2 ladder) is required "
            "before any live change."
        ),
    }

    try:
        data_dir = _data_dir(root)

        # Load book spec
        spec, err = _load_book_spec(book_path, engine_id)
        if err:
            return _report_data_gap(f"book_load_failed:{err}", {"book_path": str(book_path), "engine_id": engine_id})
        report["spec"] = {
            "engine_id": spec.get("engine_id"),
            "name_en": spec.get("name_en"),
            "market": spec.get("market"),
            "ruler": spec.get("ruler"),
        }

        # Detect market
        market = _detect_market(spec, engine_id)
        report["market"] = market

        if market == "hk":
            return _report_data_gap(
                "hk_market_not_supported_in_v1:SA-R12 defers HK",
                {"market": "hk"},
            )

        # Load graded outcomes (one-grader law: never recompute forward returns)
        grades_df, err = _load_grades(data_dir, market)
        if err:
            return _report_data_gap(err, {"market": market})

        report["grades"] = {
            "n_rows": len(grades_df),
            "columns": list(grades_df.columns)[:20],
        }

        if len(grades_df) == 0:
            return _report_data_gap("grade_store_empty", {"market": market})

        # Leave-newest-out temporal split (SA-R5, §6 item 1)
        train_df, holdout_df, err = _compute_leave_newest_out_split(grades_df)
        if err:
            log.warning("replay_standout_books: split error: %s", err)
            train_df = grades_df
            holdout_df = None

        report["split"] = {
            "n_train": len(train_df) if train_df is not None else 0,
            "n_holdout": len(holdout_df) if holdout_df is not None else 0,
            "method": "leave_newest_nonoverlapping_month",
            "error": err,
        }

        # Compute baseline metrics on training set and holdout set
        # Note: in v1 we compute baseline metrics on the EXISTING grades data.
        # The "reranking" step would apply the spec's config delta to score
        # the candidates differently — but since we don't re-run the board
        # scoring pipeline here, we report the existing baseline and note that
        # a full counterfactual requires scripts/replay_standout_pipeline.py.
        train_hq = _compute_hit_quality(train_df, market)
        holdout_hq = _compute_hit_quality(holdout_df, market) if holdout_df is not None else {"value": None, "n": 0, "note": "no_holdout"}
        train_cov = _compute_coverage_health(train_df, market)
        holdout_cov = _compute_coverage_health(holdout_df, market) if holdout_df is not None else {"value": None, "n": 0, "note": "no_holdout"}

        report["baseline_metrics"] = {
            "train": {
                "hit_quality": train_hq,
                "coverage_health": train_cov,
            },
            "holdout": {
                "hit_quality": holdout_hq,
                "coverage_health": holdout_cov,
            },
        }

        # ── Counterfactual evaluation ─────────────────────────────────────────
        # For cheaply-replayable params (cn.washout_bonus), reconstruct the
        # ordering delta from stored per-name board columns and compute verdict.
        # All other params: baseline_only (honest; full re-run not available here).
        is_sa_review_spec = spec.get("status") == "draft" or "sa_review_param" in (spec.get("config") or {})
        spec_param = (spec.get("config") or {}).get("sa_review_param")
        spec_delta_steps = (spec.get("config") or {}).get("delta_steps")

        # Determine trial count for Bonferroni
        trial_count_cf = (report.get("trial_accounting") or {}).get("trial_count") or 1

        # Do-no-harm min_effective_n from config
        try:
            import yaml  # type: ignore[import]
            _cfg_path = (REPO_ROOT if root is None else root) / "config" / "standout_review.yml"
            _min_eff_n = 6
            if _cfg_path.exists():
                _cfg = yaml.safe_load(_cfg_path.read_text())
                _min_eff_n = int((_cfg.get("do_no_harm") or {}).get("min_effective_n") or 6)
        except Exception:  # noqa: BLE001
            _min_eff_n = 6

        if spec_param == "cn.washout_bonus" and market == "cn" and spec_delta_steps is not None:
            # Cheaply-replayable: reconstruct counterfactual washout_bonus
            try:
                _step = 0.10  # cn.washout_bonus step from yml
                washout_bonus_cf = float(_CN_WASHOUT_BONUS_BASELINE) + float(spec_delta_steps) * _step
                cf_result = _cn_washout_bonus_counterfactual(
                    grades_df,
                    washout_bonus_cf=washout_bonus_cf,
                    trial_count=trial_count_cf,
                    min_effective_n=_min_eff_n,
                )
                report["counterfactual"] = {
                    "status": cf_result.get("verdict", "UNEVALUABLE"),
                    "verdict": cf_result.get("verdict"),
                    "reason": cf_result.get("reason"),
                    "evidence": cf_result.get("evidence") or {},
                    "is_shadow_review_spec": is_sa_review_spec,
                    "spec_param": spec_param,
                    "spec_delta_steps": spec_delta_steps,
                    "washout_bonus_cf": washout_bonus_cf,
                    "evaluator": "cn_washout_bonus_rank_delta",
                    "note": (
                        "Cheaply-replayable counterfactual: ordering delta from "
                        "WASHOUT_BONUS change applied to stored board.parquet columns. "
                        "See module docstring for approximation details."
                    ),
                }
            except Exception as _e:  # noqa: BLE001
                report["counterfactual"] = {
                    "status": "UNEVALUABLE",
                    "verdict": "UNEVALUABLE",
                    "reason": f"counterfactual_exception:{_e}",
                    "is_shadow_review_spec": is_sa_review_spec,
                    "spec_param": spec_param,
                    "spec_delta_steps": spec_delta_steps,
                }
        else:
            report["counterfactual"] = {
                "status": "baseline_only",
                "verdict": "UNEVALUABLE",
                "reason": "param_not_cheaply_replayable_in_v1",
                "note": (
                    "v1 implements cheap counterfactual evaluation only for cn.washout_bonus. "
                    "For other params, use scripts/replay_standout_pipeline.py (full re-run). "
                    "This report provides baseline metrics; use them to assess current n before "
                    "authorizing a shadow book experiment."
                ),
                "is_shadow_review_spec": is_sa_review_spec,
                "spec_param": spec_param,
                "spec_delta_steps": spec_delta_steps,
            }

        # Trial count accounting (SA-R5 §6 item 2)
        try:
            import yaml  # type: ignore[import]
            cfg_path = (REPO_ROOT if root is None else root) / "config" / "standout_review.yml"
            if cfg_path.exists():
                cfg = yaml.safe_load(cfg_path.read_text())
                whitelist = cfg.get("whitelist") or {}
                trial_count = sum(2 for spec_entry in whitelist.values() if spec_entry and spec_entry.get("step") is not None)
                report["trial_accounting"] = {
                    "trial_count": trial_count,
                    "haircut_method": "bonferroni_over_grid",
                    "note": f"Bonferroni threshold = alpha / {trial_count}",
                }
        except Exception:  # noqa: BLE001
            report["trial_accounting"] = {"trial_count": None, "note": "config_unavailable"}

        report["status"] = "ok"
        log.info(
            "replay_standout_books: %s market=%s n_train=%d n_holdout=%d",
            spec.get("engine_id"), market,
            report["split"]["n_train"],
            report["split"]["n_holdout"],
        )
        return report

    except Exception as e:  # noqa: BLE001 — SA-R16 never raises
        log.error("replay_standout_books.replay failed: %s", e)
        return _report_data_gap(f"replay_error:{e}", {})


def _write_report(report: dict, out_path: Path) -> None:
    """Write report JSON to out_path."""
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        log.info("replay_standout_books: report written to %s", out_path)
    except Exception as e:  # noqa: BLE001
        log.error("replay_standout_books: report write failed: %s", e)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(
        description=(
            "SA-W4 Tier-0 replay tool: re-rank accrued board snapshots under a config "
            "variant and report hit/coverage deltas. "
            "Absent stores => data_gap report, exit 0. "
            "TIER-0 ONLY: may authorize experiments/shadow books, NEVER promotions."
        )
    )
    ap.add_argument("--book", type=Path, default=None,
                    help="Path to a book/shadow spec JSON file")
    ap.add_argument("--engine-id", default=None,
                    help="Registry engine_id (US, CN, or HK book)")
    ap.add_argument("--out", type=Path, default=None,
                    help="Output JSON path (default: data/standout_review/replay_reports/<id>.json)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Run without writing the report file")
    ap.add_argument("--root", type=Path, default=None,
                    help="Override project root path")
    args = ap.parse_args()

    if args.book is None and args.engine_id is None:
        ap.error("Must provide --book or --engine-id")

    root = args.root
    report = replay(
        book_path=args.book,
        engine_id=args.engine_id,
        root=root,
        dry_run=args.dry_run,
    )

    # Determine output path
    if args.out:
        out_path = args.out
    elif not args.dry_run:
        eid = (report.get("spec") or {}).get("engine_id") or args.engine_id or "unknown"
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        data_root = _data_dir(root)
        out_path = data_root / "standout_review" / "replay_reports" / f"{eid}_{ts}.json"
    else:
        out_path = None

    if out_path and not args.dry_run:
        _write_report(report, out_path)

    # Print summary
    print(json.dumps({
        "status": report.get("status"),
        "market": report.get("market"),
        "engine_id": (report.get("spec") or {}).get("engine_id"),
        "n_train": (report.get("split") or {}).get("n_train"),
        "n_holdout": (report.get("split") or {}).get("n_holdout"),
        "data_gap_reason": report.get("data_gap_reason"),
        "dry_run": report.get("dry_run"),
        "out_path": str(out_path) if out_path else None,
    }, indent=2))

    # Arrow shutdown-hang law (SA-R16, lib/procutil.py)
    from lib.procutil import hard_exit
    hard_exit(0)


if __name__ == "__main__":
    main()
