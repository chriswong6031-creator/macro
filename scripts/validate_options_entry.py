"""scripts/validate_options_entry.py — pre-registered options-entry-quality gate.

Options Alpha program W1.3 / W-C (research/OPTIONS_ALPHA_MASTERPLAN.md §4, rulings A6/A9/A10;
W-C 2026-07-05 adds five new pre-registered bucket tests).
Extended by W-OVC (2026-07-17): S-VANNA-RELIEF and S-FRONT-CHARM gate cells registered.
See OPTIONS_OPEX_VANNA_CHARM_ADJUDICATION.md §4/§5 for the ruling and gate specifications.

THE KEYSTONE MACHINE, NOT A RESULT. This gate answers — once enough fires accrue — the one
question the desk cares about:

    "Does options context reduce stop-outs / dead money and improve clean liftoffs on entries
     the price thesis already likes?"

It reads the options-state-stamped US board ledger (``data/us_board_ledger/retro_grades.parquet``,
stamped by scripts/stamp_options_state.py) and runs pre-registered bucket tests from §4 of the
masterplan, speaking ONLY in ledger primitives (ruling A10):

  * ``post_cushion_breach``            — 21d stop-out proxy (True/False/None)
  * ``terminal_state_clean8_21``       — 21d clean-liftoff label (CLEAN_LIFTOFF vs the rest)
  * ``fwd_mfe_21`` / ``fwd_mfe_5``     — max favourable excursion
  * ``fwd_ret_5``                       — fast 5d return (S-VOI fast read)

There is NO stop5 / clean15@5d / absolute-MAE primitive; the wall study (S-WALL) computes
absolute-price wall touches directly from ``data/massive_stock_day/`` raw closes vs the stamped
``opt_wall_down`` level (close-path — UNDERSTATES intraday touches; documented in the evidence).

W-C ADDITIONS (pre-registered 2026-07-05):
  * S-IVSPREAD-F: fire-conditioned call−put IV spread (opt_ivspread_rel > 0 vs <= 0)
  * S-SKEW_DECEL: skew top-tercile AND falling (opt_skew_5d_chg < 0 vs rest)
  * S-TOP_RISK: de-escalation flag (skew rising OR ivspread_rel < 0 → flag bad entries)
    CAUTION-ONLY: beneficial direction = flagged fires show WORSE outcomes (correctly de-escalates)
  * S-PIN_RISK: OPEX proximity + long-gamma + near-wall flag (opt_pin_risk True vs False)
  * S-VOI2: stricter vol>OI burst (see engine/options_stamp.py notes; FUTURE stamp col)

W-OVC ADDITIONS (pre-registered 2026-07-17 — adjudication OPTIONS_OPEX_VANNA_CHARM_ADJUDICATION.md):
  * S-VANNA-RELIEF: vanna-relief vol compression flag (opt_vanna_relief True vs False)
    PRIMARY: post_cushion_breach delta (beneficial = LOWER breach in flagged bucket)
    SECONDARY: terminal_state_clean8_21, fwd_mfe_21 (reported honestly; no pre-judged direction)
    Holdability / de-escalation / stop-width state only (RO-3 caution-only). NOT an entry originator.
  * S-FRONT-CHARM: front-expiry charm concentration flag (opt_front7_charm_share top tercile vs rest)
    PRIMARY: post_cushion_breach delta (beneficial = HIGHER breach → flag correctly identifies vol-
    exposed entries; caution-only per RO-3 — may only LOWER conviction, never short)
    SECONDARY: terminal_state_clean8_21, fwd_mfe_21 (reported honestly)

Each test is a conditioned-vs-unconditioned descriptive delta with an IID bootstrap CI.
HARD RULE (doctrine §2.3): no descriptive maturity until n ≥ ``MIN_PER_BUCKET`` fires,
n ≥ ``MIN_DATES_PER_BUCKET`` dates, and n ≥ ``MIN_OVERLAP_DATES`` shared dates in EACH
condition bucket.  These IID diagnostics have NO promotion authority: date-cluster inference
and a frozen sequential-look plan must be separately pre-registered and implemented first.

Output: ``data/options_entry/gate.json`` (schema ``options_entry.gate.v3``, extends v2).

Only recomputes counts / descriptive statuses.  ``scored`` remains false, ``weight`` remains
zero, and the top-level gate remains ``building_history`` while promotion blockers are open.

FDR FAMILY (BH α=0.10): 36 tests total (28 OVC + 8 S-FLOWML cells per FS-3 prereg 2026-07-13).
See OPTIONS_ALPHA_MASTERPLAN.md §4 FS-3 Enlarged-family BH-FDR statement (2026-07-13: 28+8=36).
No verdict claims significance without clearing BH-FDR at α=0.10 over this full 36-test family.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from engine.options_stamp import STAMP_COLS, STAMP_COVERAGE_COLS  # noqa: E402
from lib import config  # noqa: E402

GATE_DIR = config.data_dir() / "options_entry"
GATE_PATH = GATE_DIR / "gate.json"
LEDGER_PATH = config.data_dir() / "us_board_ledger" / "retro_grades.parquet"
STOCK_DAY_DIR = config.data_dir() / "massive_stock_day"

# pre-registered thresholds (doctrine §2.3 — bans sub-30 verdicts)
MIN_PER_BUCKET = 30
MIN_DATES_PER_BUCKET = 30
MIN_OVERLAP_DATES = 30
BOOTSTRAP_N = 2000
FDR_ALPHA = 0.10
CLEAN = "CLEAN_LIFTOFF"          # terminal_state_clean8_21 value that means a clean liftoff
FIXED_STOP = 0.95               # S-WALL comparator: fixed −5% stop
EVENT_KEY = ("as_of", "lane", "ticker")
DECLARED_LANE = "buy"

# The current inferential outputs are intentionally descriptive.  The implementation was
# repaired after partial live data had already been observed, so those observations cannot
# acquire promotion authority retroactively.  A future dated amendment must freeze both a
# date-cluster/block estimator and sequential-look schedule before a fresh authority cohort.
GLOBAL_PROMOTION_BLOCKERS = (
    "DATE_CLUSTER_INFERENCE_REQUIRED",
    "SEQUENTIAL_LOOK_PLAN_REQUIRED",
    "PRE_AMENDMENT_DATA_AUTHORITY_BARRED",
)


def _canonical_fire_frame(raw: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Reduce the horizon ledger to one declared-population fire per event.

    The production ledger is one row per ``(as_of, lane, ticker, horizon)``.  Options state,
    clean/breach labels, and the board fire itself are event-level quantities, so treating
    horizon projections as independent fires is pseudo-replication.  This reducer therefore:

    * filters to the pre-declared ``buy`` lane before any masks or cross-sectional terciles;
    * rejects duplicate event+horizon rows;
    * rejects conflicting repeated ``opt_*`` and event-level outcome values;
    * sources 5d return from ``horizon == 5`` ``ret`` only, and MFE from its exact horizon.

    Nulls may coexist with one non-null repeated value (normal staggered maturity).  More than
    one distinct non-null value is a corrupt event and fails loudly rather than choosing one.
    """
    required = {*EVENT_KEY, "horizon"}
    missing = sorted(required - set(raw.columns))
    if missing:
        raise ValueError(f"options-entry ledger missing canonical key columns: {missing}")

    work = raw.copy()
    parsed_as_of = pd.to_datetime(work["as_of"], errors="coerce")
    if parsed_as_of.isna().any():
        bad = work.loc[parsed_as_of.isna(), "as_of"].astype(str).head(5).tolist()
        raise ValueError(f"options-entry ledger has invalid as_of values: {bad}")
    work["as_of"] = parsed_as_of.dt.strftime("%Y-%m-%d")
    work["lane"] = work["lane"].astype("string")
    work["ticker"] = work["ticker"].astype("string")
    if work["lane"].isna().any() or work["ticker"].isna().any():
        raise ValueError("options-entry ledger has null lane/ticker event keys")
    work["horizon"] = pd.to_numeric(work["horizon"], errors="coerce")
    if work["horizon"].isna().any():
        raise ValueError("options-entry ledger has non-numeric/null horizon values")

    raw_rows = len(work)
    raw_events = int(work[list(EVENT_KEY)].drop_duplicates().shape[0])
    lane_rows = work[work["lane"] == DECLARED_LANE].copy()
    excluded_rows = raw_rows - len(lane_rows)

    dup_mask = lane_rows.duplicated(subset=[*EVENT_KEY, "horizon"], keep=False)
    if dup_mask.any():
        sample = (
            lane_rows.loc[dup_mask, [*EVENT_KEY, "horizon"]]
            .drop_duplicates()
            .head(5)
            .to_dict("records")
        )
        raise ValueError(f"duplicate options-entry event+horizon rows: {sample}")

    event_outcome_cols = [
        col for col in lane_rows.columns
        if col == "post_cushion_breach" or col.startswith("terminal_state_")
    ]
    repeated_cols = sorted({
        *[col for col in lane_rows.columns if col.startswith("opt_")],
        *event_outcome_cols,
    })
    grouped = lane_rows.groupby(list(EVENT_KEY), sort=False, dropna=False)
    for col in repeated_cols:
        conflicts = grouped[col].nunique(dropna=True) > 1
        if conflicts.any():
            sample_keys = [tuple(key) if isinstance(key, tuple) else (key,)
                           for key in conflicts[conflicts].index[:5]]
            raise ValueError(
                f"conflicting repeated event-level values in {col!r} for {sample_keys}"
            )

    events = lane_rows[list(EVENT_KEY)].drop_duplicates().reset_index(drop=True)
    if repeated_cols and not lane_rows.empty:
        # Safe only after the conflict audit above: first non-null is the sole non-null value.
        static = grouped[repeated_cols].first().reset_index()
        events = events.merge(static, on=list(EVENT_KEY), how="left", validate="one_to_one")

    def _attach_horizon_value(horizon: int, source: str, target: str) -> None:
        if source not in lane_rows.columns:
            events[target] = np.nan
            return
        values = lane_rows.loc[
            lane_rows["horizon"] == horizon, [*EVENT_KEY, source]
        ].rename(columns={source: target})
        events[target] = events.merge(
            values, on=list(EVENT_KEY), how="left", validate="one_to_one"
        )[target]

    _attach_horizon_value(5, "ret", "fwd_ret_5")
    _attach_horizon_value(5, "fwd_mfe_5", "fwd_mfe_5")
    _attach_horizon_value(21, "fwd_mfe_21", "fwd_mfe_21")
    events = events.sort_values(list(EVENT_KEY), kind="mergesort").reset_index(drop=True)

    meta = {
        "event_key": list(EVENT_KEY),
        "declared_lane": DECLARED_LANE,
        "raw_rows": raw_rows,
        "raw_events_all_lanes": raw_events,
        "declared_lane_rows": len(lane_rows),
        "declared_lane_stamped_rows": int(
            lane_rows[[col for col in STAMP_COVERAGE_COLS if col in lane_rows.columns]]
            .notna().any(axis=1).sum()
        ) if any(col in lane_rows.columns for col in STAMP_COVERAGE_COLS) else 0,
        "excluded_non_buy_rows": excluded_rows,
        "canonical_events": len(events),
        "canonical_dates": int(events["as_of"].nunique()) if not events.empty else 0,
        "horizon_mapping": {
            "fwd_ret_5": "horizon=5 ret",
            "fwd_mfe_5": "horizon=5 fwd_mfe_5",
            "fwd_mfe_21": "horizon=21 fwd_mfe_21",
            "post_cushion_breach": "sole non-null repeated event value",
            "terminal_state_clean8_21": "sole non-null repeated event value",
        },
    }
    return events, meta


def _stable_rng(*arrays: np.ndarray) -> np.random.Generator:
    """Return a deterministic RNG keyed to the exact samples being tested.

    Gate regeneration must not depend on which other cells happened to run first.  A
    content-derived seed keeps bootstrap CIs and permutation p-values repeatable while
    preserving independent random streams for different exact metric cells.
    """
    digest = hashlib.blake2b(digest_size=8, person=b"opt-entry")
    for arr in arrays:
        normalized = np.ascontiguousarray(arr, dtype=np.float64)
        digest.update(len(normalized).to_bytes(8, "little"))
        digest.update(normalized.tobytes())
    return np.random.default_rng(int.from_bytes(digest.digest(), "little"))


# ── bootstrap helpers ────────────────────────────────────────────────────────
def _bootstrap_mean_ci(vals: np.ndarray, n_boot: int = BOOTSTRAP_N) -> tuple[float, float, float]:
    """(point mean, 2.5%, 97.5%) bootstrap CI of the mean. NaN triple on empty."""
    vals = vals[~np.isnan(vals)]
    n = len(vals)
    if n == 0:
        return (float("nan"), float("nan"), float("nan"))
    idx = _stable_rng(vals).integers(0, n, size=(n_boot, n))
    means = vals[idx].mean(axis=1)
    return (float(vals.mean()), float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5)))


def _bootstrap_delta_ci(
    a: np.ndarray,
    b: np.ndarray,
    a_dates: np.ndarray | None = None,
    b_dates: np.ndarray | None = None,
    n_boot: int = BOOTSTRAP_N,
) -> dict:
    """Bootstrap CI for mean(a) − mean(b) (conditioned − unconditioned).

    Returns delta, CI, metric-level maturity, date counts, and a two-sided IID
    randomization p-value.  The p-value is deliberately forced to 1 until the exact
    metric cell has at least ``MIN_PER_BUCKET`` matured outcomes, at least
    ``MIN_DATES_PER_BUCKET`` distinct dates per side, and at least
    ``MIN_OVERLAP_DATES`` shared dates.  These statistics remain descriptive-only.

    Both arrays are NaN-dropped; empty either side → all-NaN, excludes_zero False.
    """
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    if a_dates is None:
        a_dates = np.array([], dtype=object)
    if b_dates is None:
        b_dates = np.array([], dtype=object)
    a_dates = np.asarray(a_dates, dtype=object)
    b_dates = np.asarray(b_dates, dtype=object)
    if len(a_dates) != len(a) or len(b_dates) != len(b):
        raise ValueError("metric values and as_of date arrays must be aligned")
    a_keep = ~np.isnan(a)
    b_keep = ~np.isnan(b)
    a, a_dates = a[a_keep], a_dates[a_keep]
    b, b_dates = b[b_keep], b_dates[b_keep]
    na, nb = len(a), len(b)
    dates_a = {str(value) for value in a_dates}
    dates_b = {str(value) for value in b_dates}
    n_dates_cond = len(dates_a)
    n_dates_base = len(dates_b)
    n_overlap_dates = len(dates_a & dates_b)
    ready = bool(
        na >= MIN_PER_BUCKET
        and nb >= MIN_PER_BUCKET
        and n_dates_cond >= MIN_DATES_PER_BUCKET
        and n_dates_base >= MIN_DATES_PER_BUCKET
        and n_overlap_dates >= MIN_OVERLAP_DATES
    )
    if na == 0 or nb == 0:
        return {"n_cond": na, "n_base": nb, "delta": None,
                "ci_lo": None, "ci_hi": None, "excludes_zero": False,
                "n_dates_cond": n_dates_cond, "n_dates_base": n_dates_base,
                "n_overlap_dates": n_overlap_dates,
                "ready": False, "p_value": 1.0, "fdr_pass": False,
                "inference_authority": "descriptive_iid_only"}
    rng = _stable_rng(a, b)
    ia = rng.integers(0, na, size=(n_boot, na))
    ib = rng.integers(0, nb, size=(n_boot, nb))
    deltas = a[ia].mean(axis=1) - b[ib].mean(axis=1)
    lo, hi = float(np.percentile(deltas, 2.5)), float(np.percentile(deltas, 97.5))
    observed = float(a.mean() - b.mean())

    # Two-sided permutation/randomization test under the sharp null of exchangeability.
    # The +1 correction prevents zero p-values.  Immature cells stay at p=1 and cannot
    # consume a BH rejection regardless of how extreme their preliminary delta appears.
    p_value = 1.0
    if ready:
        pooled = np.concatenate((a, b))
        exceedances = 0
        for _ in range(n_boot):
            permuted = rng.permutation(pooled)
            null_delta = float(permuted[:na].mean() - permuted[na:].mean())
            if abs(null_delta) >= abs(observed) - 1e-15:
                exceedances += 1
        p_value = (exceedances + 1) / (n_boot + 1)
    return {
        "n_cond": na, "n_base": nb,
        "delta": round(observed, 5),
        "ci_lo": round(lo, 5), "ci_hi": round(hi, 5),
        "excludes_zero": bool(lo > 0 or hi < 0),
        "n_dates_cond": n_dates_cond,
        "n_dates_base": n_dates_base,
        "n_overlap_dates": n_overlap_dates,
        "ready": ready,
        "p_value": round(float(p_value), 8),
        "fdr_pass": False,
        "inference_authority": "descriptive_iid_only",
    }


def _empty_metric() -> dict:
    """Canonical unavailable registered cell (still occupies its BH-family slot)."""
    return {
        "n_cond": 0, "n_base": 0, "delta": None,
        "ci_lo": None, "ci_hi": None, "excludes_zero": False,
        "n_dates_cond": 0, "n_dates_base": 0, "n_overlap_dates": 0,
        "ready": False, "p_value": 1.0, "fdr_pass": False,
        "inference_authority": "descriptive_iid_only",
    }


# Exact 28 OVC cells registered in OPTIONS_ALPHA_MASTERPLAN.md §4.  ``source`` is
# different from ``family`` only for the two S-VOI fast-horizon primitives.
_OVC_CELL_SPECS = (
    # family, metric, source test, pre-registered beneficial direction
    ("S-IVR", "breach", "S-IVR", "lower"),
    ("S-IVR", "clean", "S-IVR", "higher"),
    ("S-IVR", "mfe21", "S-IVR", "higher"),
    ("S-DOI", "breach", "S-DOI", "lower"),
    ("S-DOI", "clean", "S-DOI", "higher"),
    ("S-DOI", "mfe21", "S-DOI", "higher"),
    ("S-VOI", "fwd_ret_5", "S-VOI-fast", "higher"),
    ("S-VOI", "fwd_mfe_5", "S-VOI-fast", "higher"),
    ("S-VOI", "clean", "S-VOI", "higher"),
    ("S-IVSPREAD-F", "breach", "S-IVSPREAD-F", "lower"),
    ("S-IVSPREAD-F", "clean", "S-IVSPREAD-F", "higher"),
    ("S-IVSPREAD-F", "mfe21", "S-IVSPREAD-F", "higher"),
    ("S-SKEW_DECEL", "breach", "S-SKEW_DECEL", "lower"),
    ("S-SKEW_DECEL", "clean", "S-SKEW_DECEL", "higher"),
    ("S-SKEW_DECEL", "mfe21", "S-SKEW_DECEL", "higher"),
    ("S-TOP_RISK", "breach", "S-TOP_RISK", "higher"),
    ("S-TOP_RISK", "clean", "S-TOP_RISK", "lower"),
    ("S-PIN_RISK", "clean", "S-PIN_RISK", "lower"),
    ("S-PIN_RISK", "mfe21", "S-PIN_RISK", "lower"),
    ("S-VOI2", "fwd_ret_5", "S-VOI2", "higher"),
    ("S-VOI2", "fwd_mfe_5", "S-VOI2", "higher"),
    ("S-VOI2", "clean", "S-VOI2", "higher"),
    ("S-VANNA-RELIEF", "breach", "S-VANNA-RELIEF", "lower"),
    ("S-VANNA-RELIEF", "clean", "S-VANNA-RELIEF", "two_sided_diagnostic"),
    ("S-VANNA-RELIEF", "mfe21", "S-VANNA-RELIEF", "two_sided_diagnostic"),
    ("S-FRONT-CHARM", "breach", "S-FRONT-CHARM", "higher"),
    ("S-FRONT-CHARM", "clean", "S-FRONT-CHARM", "two_sided_diagnostic"),
    ("S-FRONT-CHARM", "mfe21", "S-FRONT-CHARM", "two_sided_diagnostic"),
)

# FS-3 cells are registered in the same family but are not computed by this ledger
# validator.  They remain explicit, unavailable p=1 cells until the flow-score harness
# supplies governed results; this validator must never silently shrink the denominator.
_FS3_RESERVED_CELL_SPECS = tuple(
    (family, metric, era)
    for era in ("2020-22", "2023+")
    for family, metric in (
        ("S-FLOWML-0_7", "fwd_ret_5"),
        ("S-FLOWML-8_90", "fwd_ret_21"),
        ("S-FLOWML-90P", "fwd_ret_63"),
        ("S-FLOWML-90P", "fwd_ret_126"),
    )
)


def _benjamini_hochberg(cells: list[dict], alpha: float = FDR_ALPHA) -> list[dict]:
    """Apply the BH step-up procedure to a complete, explicit test family.

    Every input cell must carry an ID and p-value.  The returned list preserves input
    order and adds rank, threshold, monotone BH q-value, and ``fdr_pass``.
    """
    m = len(cells)
    if m == 0:
        return []
    ranked = sorted(
        ((min(1.0, max(0.0, float(cell["p_value"]))), str(cell["id"]), i)
         for i, cell in enumerate(cells)),
        key=lambda item: (item[0], item[1]),
    )
    critical_rank = 0
    for rank, (p_value, _, _) in enumerate(ranked, start=1):
        if p_value <= (rank / m) * alpha:
            critical_rank = rank

    q_by_index: dict[int, float] = {}
    running_q = 1.0
    for rank in range(m, 0, -1):
        p_value, _, original_index = ranked[rank - 1]
        running_q = min(running_q, p_value * m / rank)
        q_by_index[original_index] = min(1.0, running_q)

    out = [dict(cell) for cell in cells]
    for rank, (p_value, _, original_index) in enumerate(ranked, start=1):
        out[original_index].update({
            "p_value": round(p_value, 8),
            "bh_rank": rank,
            "bh_threshold": round((rank / m) * alpha, 8),
            "q_value": round(q_by_index[original_index], 8),
            "fdr_pass": bool(critical_rank and rank <= critical_rank),
        })
    return out


def _apply_registered_family_fdr(tests: dict[str, dict]) -> dict:
    """Build and test the exact preregistered 36-cell family, mutating cell receipts.

    Metric maturity is computed from non-null outcomes inside each exact cell.  Raw
    condition/base fire counts are retained for coverage reporting but never make a cell
    eligible for BH or a verdict.
    """
    cells: list[dict] = []
    metric_refs: dict[str, dict] = {}
    family_cell_ids: dict[str, list[str]] = {}

    for family, metric_name, source_name, direction in _OVC_CELL_SPECS:
        source = tests.setdefault(
            source_name,
            {"bucket": source_name, "n_cond": 0, "n_base": 0, "ready": False},
        )
        metric = source.setdefault(metric_name, _empty_metric())
        # Defensively recompute maturity from the exact metric counts even for older or
        # externally constructed receipts that happen to carry a stale ``ready`` flag.
        mature = bool(
            int(metric.get("n_cond", 0)) >= MIN_PER_BUCKET
            and int(metric.get("n_base", 0)) >= MIN_PER_BUCKET
            and int(metric.get("n_dates_cond", 0)) >= MIN_DATES_PER_BUCKET
            and int(metric.get("n_dates_base", 0)) >= MIN_DATES_PER_BUCKET
            and int(metric.get("n_overlap_dates", 0)) >= MIN_OVERLAP_DATES
        )
        metric["ready"] = mature
        p_value = float(metric.get("p_value", 1.0)) if mature else 1.0
        cell_id = f"{family}:{metric_name}:2026+"
        cells.append({
            "id": cell_id,
            "family": family,
            "source_test": source_name,
            "metric": metric_name,
            "era": "2026+",
            "expected_direction": direction,
            "available": metric.get("delta") is not None,
            "mature": mature,
            "n_cond": int(metric.get("n_cond", 0)),
            "n_base": int(metric.get("n_base", 0)),
            "n_dates_cond": int(metric.get("n_dates_cond", 0)),
            "n_dates_base": int(metric.get("n_dates_base", 0)),
            "n_overlap_dates": int(metric.get("n_overlap_dates", 0)),
            "reserved": False,
            "p_value": p_value,
        })
        metric_refs[cell_id] = metric
        family_cell_ids.setdefault(family, []).append(cell_id)

    for family, metric_name, era in _FS3_RESERVED_CELL_SPECS:
        cells.append({
            "id": f"{family}:{metric_name}:{era}",
            "family": family,
            "source_test": None,
            "metric": metric_name,
            "era": era,
            "expected_direction": "higher",
            "available": False,
            "mature": False,
            "n_cond": 0,
            "n_base": 0,
            "n_dates_cond": 0,
            "n_dates_base": 0,
            "n_overlap_dates": 0,
            "reserved": True,
            "p_value": 1.0,
            "unavailable_reason": "FS-3 flow-score harness does not emit results to this validator yet",
        })

    if len(cells) != 36:  # hard fail if code and preregistration arithmetic diverge
        raise AssertionError(f"registered options-entry BH family must contain 36 cells, got {len(cells)}")
    adjudicated = _benjamini_hochberg(cells, alpha=FDR_ALPHA)

    for cell in adjudicated:
        metric = metric_refs.get(cell["id"])
        if metric is not None:
            metric.update({
                "fdr_pass": cell["fdr_pass"],
                "fdr_q_value": cell["q_value"],
                "fdr_rank": cell["bh_rank"],
                "fdr_threshold": cell["bh_threshold"],
                "registered_cell_id": cell["id"],
                "expected_direction": cell["expected_direction"],
            })

    by_id = {cell["id"]: cell for cell in adjudicated}
    conjunction_families = {"S-TOP_RISK", "S-PIN_RISK"}
    primary_only = {
        "S-VANNA-RELIEF": "breach",
        "S-FRONT-CHARM": "breach",
    }
    for family, ids in family_cell_ids.items():
        family_test = tests[family]
        registered = [by_id[cell_id] for cell_id in ids]
        if family in conjunction_families:
            ready = all(cell["mature"] for cell in registered)
        elif family in primary_only:
            ready = next(
                cell["mature"] for cell in registered
                if cell["metric"] == primary_only[family]
            )
        else:
            # OR-shaped families are verdict-ready once either (a) a mature cell has
            # already cleared every signal guard or (b) all decision cells have matured,
            # allowing a conservative no-effect conclusion.  One merely-null mature
            # cell is not enough to close the family.
            ready = all(cell["mature"] for cell in registered) or any(
                _cell_qualifies(metric_refs[cell["id"]], cell["expected_direction"])
                for cell in registered
            )
        family_test["ready"] = bool(ready)
        family_test["registered_cells_ready"] = sum(bool(cell["mature"]) for cell in registered)
        family_test["registered_cells_total"] = len(registered)
        family_test["registered_cell_ids"] = ids

    return {
        "alpha": FDR_ALPHA,
        "method": "Benjamini-Hochberg",
        "family_size": len(adjudicated),
        "p_value_method": {
            "name": "two-sided IID permutation/randomization diagnostic",
            "resamples": BOOTSTRAP_N,
            "finite_sample_correction": "+1 numerator and denominator",
            "immature_or_unavailable_p_value": 1.0,
            "authority": "descriptive_only",
        },
        "confidence_interval_method": {
            "name": "IID nonparametric percentile bootstrap diagnostic",
            "confidence_level": 0.95,
            "resamples": BOOTSTRAP_N,
            "percentiles": [2.5, 97.5],
            "authority": "descriptive_only",
        },
        "n_mature": sum(bool(cell["mature"]) for cell in adjudicated),
        "n_rejected": sum(bool(cell["fdr_pass"]) for cell in adjudicated),
        "cells": adjudicated,
    }


def _cell_qualifies(cell: dict | None, direction: str) -> bool:
    """True when the descriptive directional/CI/BH diagnostics all pass.

    This is a candidate diagnostic only.  It never confers promotion authority.
    """
    if not cell:
        return False
    delta = cell.get("delta")
    direction_ok = (
        delta is not None
        and ((direction == "higher" and delta > 0) or (direction == "lower" and delta < 0))
    )
    return bool(
        direction_ok
        and cell.get("ready")
        and cell.get("excludes_zero")
        and cell.get("fdr_pass")
    )


def _verdict_from_cells(cells: list[tuple[dict | None, str]], *, require_all: bool = False) -> str:
    """Return a non-authoritative status over preregistered directional cells.

    ``candidate_signal_blocked`` is deliberately distinct from ``signal``.  BH
    non-rejection after a directional CI is ``inconclusive_fdr``; ``no_effect`` is
    reserved for the preregistered all-CIs-include-zero condition; a BH-clean CI in
    the wrong direction is ``opposite_direction``.
    """
    maturity = [bool(cell and cell.get("ready")) for cell, _ in cells]
    qualified = [_cell_qualifies(cell, direction) for cell, direction in cells]
    opposite = []
    ci_non_null = []
    for cell, direction in cells:
        delta = cell.get("delta") if cell else None
        excludes_zero = bool(cell and cell.get("excludes_zero"))
        ci_non_null.append(excludes_zero)
        wrong_direction = bool(
            delta is not None
            and excludes_zero
            and ((direction == "higher" and delta < 0) or (direction == "lower" and delta > 0))
            and cell.get("fdr_pass")
        )
        opposite.append(wrong_direction)

    if require_all:
        if not all(maturity):
            return "building_history"
        if all(qualified):
            return "candidate_signal_blocked"
        if any(opposite):
            return "opposite_direction"
        if not any(ci_non_null):
            return "no_effect"
        return "inconclusive_fdr"

    # OR-shaped families may surface a blocked candidate as soon as one mature exact
    # cell clears the descriptive diagnostics.  A null conclusion is stricter: all
    # registered decision cells must mature and all their CIs must include zero.
    if any(qualified):
        return "candidate_signal_blocked"
    if not all(maturity):
        return "building_history"
    if any(opposite):
        return "opposite_direction"
    if not any(ci_non_null):
        return "no_effect"
    return "inconclusive_fdr"


def _breach_rate_sample(sub: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Breach 0/1 values and their aligned event dates."""
    if "post_cushion_breach" not in sub.columns:
        return np.array([], dtype=float), np.array([], dtype=object)
    keep = sub["post_cushion_breach"].notna()
    values = sub.loc[keep, "post_cushion_breach"].astype(bool).astype(float).to_numpy()
    dates = sub.loc[keep, "as_of"].astype(str).to_numpy()
    return values, dates


def _clean_rate_sample(sub: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Clean-liftoff 0/1 values and their aligned event dates."""
    col = "terminal_state_clean8_21"
    if col not in sub.columns:
        return np.array([], dtype=float), np.array([], dtype=object)
    keep = sub[col].notna()
    values = (sub.loc[keep, col] == CLEAN).astype(float).to_numpy()
    dates = sub.loc[keep, "as_of"].astype(str).to_numpy()
    return values, dates


def _num_sample(sub: pd.DataFrame, col: str) -> tuple[np.ndarray, np.ndarray]:
    if col not in sub.columns:
        return np.array([], dtype=float), np.array([], dtype=object)
    numeric = pd.to_numeric(sub[col], errors="coerce")
    keep = numeric.notna()
    return (
        numeric.loc[keep].to_numpy(dtype=float),
        sub.loc[keep, "as_of"].astype(str).to_numpy(),
    )


def _sample_delta(
    cond_sample: tuple[np.ndarray, np.ndarray],
    base_sample: tuple[np.ndarray, np.ndarray],
) -> dict:
    cond_values, cond_dates = cond_sample
    base_values, base_dates = base_sample
    return _bootstrap_delta_ci(cond_values, base_values, cond_dates, base_dates)


# ── one bucket test (conditioned vs unconditioned) ───────────────────────────
def _bucket_test(df: pd.DataFrame, mask: pd.Series, label: str) -> dict:
    """Compute the conditioned (mask=True) vs unconditioned (mask=False) deltas on the
    three ledger-primitive outcomes over canonical event rows."""
    cond = df[mask]
    base = df[~mask]
    n_cond = int(mask.sum())
    n_base = int((~mask).sum())

    breach = _sample_delta(_breach_rate_sample(cond), _breach_rate_sample(base))
    clean = _sample_delta(_clean_rate_sample(cond), _clean_rate_sample(base))
    mfe21 = _sample_delta(_num_sample(cond, "fwd_mfe_21"), _num_sample(base, "fwd_mfe_21"))
    cond_dates = set(cond["as_of"].astype(str))
    base_dates = set(base["as_of"].astype(str))
    out = {
        "bucket": label,
        "n_cond": n_cond, "n_base": n_base,
        "n_dates_cond": len(cond_dates),
        "n_dates_base": len(base_dates),
        "n_overlap_dates": len(cond_dates & base_dates),
        # Family readiness is refined against its exact preregistered cells when the
        # 36-cell inventory is assembled below.  Never infer it from raw fire counts.
        "ready": any(metric["ready"] for metric in (breach, clean, mfe21)),
        "breach": breach,
        "clean": clean,
        "mfe21": mfe21,
    }
    return out


def _verdict_for_test(t: dict) -> str:
    """Verdict for the standard {breach, clean, mfe21} registration shape.

    Each exact outcome cell matures independently.  At least one mature cell must clear
    its beneficial direction, 95% bootstrap CI, and full-family BH-FDR check.
    """
    return _verdict_from_cells([
        (t.get("breach"), "lower"),
        (t.get("clean"), "higher"),
        (t.get("mfe21"), "higher"),
    ])


def _verdict_for_fast_positioning(full: dict, fast: dict | None = None) -> str:
    """Verdict for exact S-VOI/S-VOI2 {ret5, mfe5, clean} registrations."""
    fast = fast or full
    return _verdict_from_cells([
        (fast.get("fwd_ret_5"), "higher"),
        (fast.get("fwd_mfe_5"), "higher"),
        (full.get("clean"), "higher"),
    ])


# ── S-VOI fast read (5d primitives) ──────────────────────────────────────────
def _voi_fast_test(df: pd.DataFrame) -> dict:
    """S-VOI fastest read: fwd_ret_5 / fwd_mfe_5 deltas conditioned on opt_voi_flag=True."""
    if "opt_voi_flag" not in df.columns:
        return {"bucket": "S-VOI-fast", "n_cond": 0, "n_base": 0, "ready": False,
                "fwd_ret_5": _empty_metric(),
                "fwd_mfe_5": _empty_metric()}
    flag = df["opt_voi_flag"].astype("boolean")
    cond = df[flag == True]   # noqa: E712 — pandas boolean mask
    base = df[flag == False]  # noqa: E712
    fwd_ret_5 = _sample_delta(_num_sample(cond, "fwd_ret_5"), _num_sample(base, "fwd_ret_5"))
    fwd_mfe_5 = _sample_delta(_num_sample(cond, "fwd_mfe_5"), _num_sample(base, "fwd_mfe_5"))
    cond_dates = set(cond["as_of"].astype(str))
    base_dates = set(base["as_of"].astype(str))
    return {
        "bucket": "S-VOI-fast",
        "n_cond": len(cond), "n_base": len(base),
        "n_dates_cond": len(cond_dates),
        "n_dates_base": len(base_dates),
        "n_overlap_dates": len(cond_dates & base_dates),
        "ready": bool(fwd_ret_5["ready"] or fwd_mfe_5["ready"]),
        "fwd_ret_5": fwd_ret_5,
        "fwd_mfe_5": fwd_mfe_5,
    }


# ── S-WALL (raw-close wall-touch study; A10) ─────────────────────────────────
def _read_stock_day(ticker: str) -> pd.Series | None:
    """Raw daily closes for a ticker from data/massive_stock_day/<TICKER>.parquet (R2-backed;
    may be absent locally). Returns a close Series indexed by date, or None."""
    p = STOCK_DAY_DIR / f"{ticker}.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p, columns=["close"])
    except Exception:  # noqa: BLE001
        return None
    if df.empty or "close" not in df.columns:
        return None
    return df["close"]


def _wall_touch_study(df: pd.DataFrame, horizon: int = 21) -> dict:
    """S-WALL: for fires with a stamped opt_wall_down, walk the raw closes over the forward
    window and record whether the close touched the wall (close ≤ wall) vs whether it touched
    the fixed −5% stop first. This is a CLOSE-PATH study — it UNDERSTATES intraday touches (a
    bar can pierce the wall intraday and close back above it). Documented in the evidence.

    Returns per-fire counts only (no verdict); the full stop-out comparison is W2.3."""
    n_eligible = 0
    n_priced = 0
    wall_touches = 0
    fixed_stop_touches = 0
    wall_before_fixed = 0

    if "opt_wall_down" not in df.columns:
        return {"n_eligible": 0, "n_priced": 0, "wall_touches": 0,
                "fixed_stop_touches": 0, "wall_before_fixed": 0, "price_store_available": False,
                "limitation": "opt_wall_down not stamped yet"}

    # one fire per (as_of, ticker) — wall level is identical across lanes/horizons
    fires = df[df["opt_wall_down"].notna()][["as_of", "ticker", "opt_wall_down"]].drop_duplicates(
        subset=["as_of", "ticker"])
    n_eligible = len(fires)
    price_store_available = False

    for _, r in fires.iterrows():
        closes = _read_stock_day(str(r["ticker"]))
        if closes is None:
            continue
        price_store_available = True
        try:
            as_of = pd.Timestamp(r["as_of"])
        except (ValueError, TypeError):
            continue
        # next-bar fill: first close strictly after as_of
        fwd = closes[closes.index > as_of].head(horizon)
        if fwd.empty:
            continue
        entry = float(fwd.iloc[0])
        if not (entry > 0):
            continue
        n_priced += 1
        wall = float(r["opt_wall_down"])
        fixed = entry * FIXED_STOP
        # first-passage over the forward path
        wall_bar = next((i for i, c in enumerate(fwd.to_numpy()) if float(c) <= wall), None)
        fixed_bar = next((i for i, c in enumerate(fwd.to_numpy()) if float(c) <= fixed), None)
        if wall_bar is not None:
            wall_touches += 1
        if fixed_bar is not None:
            fixed_stop_touches += 1
        if wall_bar is not None and (fixed_bar is None or wall_bar <= fixed_bar):
            wall_before_fixed += 1

    return {
        "n_eligible": n_eligible,
        "n_priced": n_priced,
        "wall_touches": wall_touches,
        "fixed_stop_touches": fixed_stop_touches,
        "wall_before_fixed": wall_before_fixed,
        "price_store_available": price_store_available,
        "limitation": ("close-path study understates intraday touches; a bar may pierce the wall "
                       "intraday and close back above it. Full stop-out comparison is W2.3."),
    }


# ── W-C: new pre-registered bucket tests ─────────────────────────────────────

def _verdict_for_top_risk(t: dict) -> str:
    """Verdict for S-TOP_RISK (caution-only de-escalation flag).

    Pre-registered primitives (§4): {breach, clean}.
    Beneficial direction (conjunction, per §4 registration):
      breach delta > 0 (MORE stop-outs in flagged bucket) AND
      clean delta < 0 (FEWER clean liftoffs in flagged bucket).
    Both conditions must hold for a 'signal' verdict — OR would deviate from the
    written pre-registration.  This signal MAY ONLY LOWER confidence, never short (RO-3)."""
    return _verdict_from_cells([
        (t.get("breach"), "higher"),
        (t.get("clean"), "lower"),
    ], require_all=True)


def _verdict_for_pin_risk(t: dict) -> str:
    """Verdict for S-PIN_RISK (caution-only pin-risk flag).

    Pre-registered primitives (§4): {clean, mfe21} — breach is NOT a registered
    S-PIN_RISK primitive.  Beneficial direction:
      clean delta < 0 (FEWER clean liftoffs — pin mechanics suppress liftoff) AND/OR
      mfe21 delta < 0 (LOWER mfe21 — pin mechanics suppress follow-through).
    §4 registers 'LOWER clean rate + LOWER mfe21' as the signal pattern; we require
    both conditions for a 'signal' verdict to match the conjunction wording in the
    pre-registration.  This signal MAY ONLY LOWER confidence, never short (RO-3)."""
    return _verdict_from_cells([
        (t.get("clean"), "lower"),
        (t.get("mfe21"), "lower"),
    ], require_all=True)


def _ivspread_f_test(df: pd.DataFrame) -> dict:
    """S-IVSPREAD-F: fire-conditioned call-put IV spread.

    Condition: opt_ivspread_rel > 0 (calls richening vs puts = constructive positioning)
    vs opt_ivspread_rel <= 0. A10 primitives: breach, clean, mfe21.
    Pre-registered in §4 W-C (2026-07-05). Era: single live-accrual 2026→."""
    col = "opt_ivspread_rel"
    if col not in df.columns or df[col].notna().sum() == 0:
        return {"bucket": "S-IVSPREAD-F", "n_cond": 0, "n_base": 0, "ready": False,
                "note": f"{col} not yet stamped — W-C harness extension pending full backfill"}
    iv = pd.to_numeric(df[col], errors="coerce")
    sub = df[iv.notna()].copy()
    submask = pd.to_numeric(sub[col], errors="coerce") > 0
    return _bucket_test(sub, submask, "S-IVSPREAD-F: ivspread_rel > 0 (calls richening)")


def _skew_decel_test(df: pd.DataFrame) -> dict:
    """S-SKEW_DECEL: skew high-but-falling at fire.

    Condition: opt_skew in top cross-sectional tercile (by as_of date, over stamped fires)
    AND opt_skew_5d_chg < 0.  vs rest.  A10 primitives: breach, clean, mfe21.
    Pre-registered in §4 W-C (2026-07-05). Era: single live-accrual 2026→."""
    skew_col = "opt_skew"
    chg_col = "opt_skew_5d_chg"
    if skew_col not in df.columns or df[skew_col].notna().sum() == 0:
        return {"bucket": "S-SKEW_DECEL", "n_cond": 0, "n_base": 0, "ready": False,
                "note": f"{skew_col} not yet stamped — W-C harness extension pending"}
    if chg_col not in df.columns or df[chg_col].notna().sum() == 0:
        return {"bucket": "S-SKEW_DECEL", "n_cond": 0, "n_base": 0, "ready": False,
                "note": f"{chg_col} not yet stamped — needs ≥5 prior days of skew snapshots"}
    # need both columns present
    both = df[df[skew_col].notna() & df[chg_col].notna()].copy()
    if both.empty:
        return {"bucket": "S-SKEW_DECEL", "n_cond": 0, "n_base": 0, "ready": False,
                "note": "no fires with both opt_skew and opt_skew_5d_chg stamped yet"}
    # compute top-tercile cutoff cross-sectionally per as_of date
    tercile_hi = (
        both.groupby("as_of")[skew_col]
        .transform(lambda x: x.quantile(2 / 3))
    )
    in_top_tercile = pd.to_numeric(both[skew_col], errors="coerce") >= tercile_hi
    falling = pd.to_numeric(both[chg_col], errors="coerce") < 0
    submask = in_top_tercile & falling
    return _bucket_test(
        both, submask.fillna(False),
        "S-SKEW_DECEL: skew top-tercile AND skew_5d_chg < 0 (high skew fading)"
    )


def _top_risk_test(df: pd.DataFrame) -> dict:
    """S-TOP_RISK: de-escalation family flag.

    Condition: opt_skew_5d_chg > 0 (puts richening) OR opt_ivspread_rel < 0 (puts rich).
    CAUTION-ONLY per RO-3: a PASS means flagged fires have WORSE outcomes (correctly
    identifies bad entries; used to LOWER confidence, never to short).
    A10 primitives: breach (primary), clean (secondary).
    Pre-registered in §4 W-C (2026-07-05). Era: single live-accrual 2026→."""
    skew_chg_col = "opt_skew_5d_chg"
    iv_col = "opt_ivspread_rel"
    skew_ok = skew_chg_col in df.columns and df[skew_chg_col].notna().any()
    iv_ok = iv_col in df.columns and df[iv_col].notna().any()
    if not skew_ok or not iv_ok:
        return {"bucket": "S-TOP_RISK", "n_cond": 0, "n_base": 0, "ready": False,
                "note": "both opt_skew_5d_chg and opt_ivspread_rel are required"}
    # "Neither" is a valid baseline only when both logical legs are observed.  Treating a
    # missing leg as False silently contaminates the baseline and changes the registration.
    both_known = df[skew_chg_col].notna() & df[iv_col].notna()
    sub = df[both_known].copy()
    if sub.empty:
        return {"bucket": "S-TOP_RISK", "n_cond": 0, "n_base": 0, "ready": False,
                "note": "no fires with both TOP_RISK legs observed"}
    skew_rising = pd.to_numeric(sub[skew_chg_col], errors="coerce") > 0
    puts_rich = pd.to_numeric(sub[iv_col], errors="coerce") < 0
    submask = (skew_rising | puts_rich).fillna(False)
    result = _bucket_test(
        sub, submask,
        "S-TOP_RISK: skew_5d_chg>0 OR ivspread_rel<0 (puts richening/dominant — caution-only)"
    )
    result["caution_only"] = True
    result["n_excluded_missing_leg"] = int((~both_known).sum())
    result["note"] = (
        "CAUTION-ONLY (RO-3): beneficial direction = flagged fires show WORSE outcomes "
        "(correctly identifies bad entries). NEVER initiates a negative position."
    )
    return result


def _pin_risk_test(df: pd.DataFrame) -> dict:
    """S-PIN_RISK: OPEX proximity + long-gamma + near-wall flag.

    Condition: opt_pin_risk == True vs False.  CAUTION-ONLY: beneficial = flagged fires
    have lower clean liftoff + lower mfe21 (pinning suppresses follow-through).
    A10 primitives: clean (primary), mfe21 (secondary).
    Pre-registered in §4 W-C (2026-07-05). Era: single live-accrual 2026→."""
    col = "opt_pin_risk"
    if col not in df.columns or df[col].notna().sum() == 0:
        return {"bucket": "S-PIN_RISK", "n_cond": 0, "n_base": 0, "ready": False,
                "note": f"{col} not yet stamped — W-C harness extension pending"}
    pin = df[col].astype("boolean")
    sub = df[pin.notna()].copy()
    submask = sub[col].astype("boolean") == True  # noqa: E712
    result = _bucket_test(
        sub, submask.fillna(False),
        "S-PIN_RISK: opex_days<=5 AND gamma=long AND min_wall_dist<=2% (pin-risk window)"
    )
    result["caution_only"] = True
    result["note"] = (
        "CAUTION-ONLY: beneficial direction = flagged fires show lower clean liftoff / mfe21 "
        "(pinning suppresses follow-through). de-escalation only, never a short."
    )
    return result


def _voi2_test(df: pd.DataFrame) -> dict:
    """S-VOI2: stricter vol>OI burst (pre-registered, harness col not yet stamped).

    S-VOI2 requires a future stamp column opt_voi2_flag (z-threshold + contract-count
    floor; see §4 registration). Until that column is stamped, this is building_history.
    This function is a placeholder that will activate once the stamp col exists.
    Pre-registered in §4 W-C (2026-07-05). Documented as a NEW registration distinct from
    the degenerate S-VOI (n_base=4 is architecturally degenerate; S-VOI registration stands)."""
    col = "opt_voi2_flag"
    if col not in df.columns or df[col].notna().sum() == 0:
        return {
            "bucket": "S-VOI2",
            "n_cond": 0, "n_base": 0, "ready": False,
            "note": (
                f"{col} not yet stamped — awaits W-C harness extension that adds the stricter "
                "z-threshold + contract-count-floor to the stamp (future PR). "
                "S-VOI original registration stands; this is a distinct, stricter bucket "
                "registered after S-VOI was documented as degenerate (n_cond=42/n_base=4)."
            ),
        }
    flag = df[col].astype("boolean")
    sub = df[flag.notna()].copy()
    submask = sub[col].astype("boolean") == True  # noqa: E712
    conditioned = sub[submask]
    baseline = sub[~submask]
    fwd_ret_5 = _sample_delta(
        _num_sample(conditioned, "fwd_ret_5"), _num_sample(baseline, "fwd_ret_5")
    )
    fwd_mfe_5 = _sample_delta(
        _num_sample(conditioned, "fwd_mfe_5"), _num_sample(baseline, "fwd_mfe_5")
    )
    clean = _sample_delta(_clean_rate_sample(conditioned), _clean_rate_sample(baseline))
    cond_dates = set(conditioned["as_of"].astype(str))
    base_dates = set(baseline["as_of"].astype(str))
    result: dict = {
        "bucket": "S-VOI2",
        "n_cond": int(submask.sum()), "n_base": int((~submask).sum()),
        "n_dates_cond": len(cond_dates),
        "n_dates_base": len(base_dates),
        "n_overlap_dates": len(cond_dates & base_dates),
        "ready": bool(fwd_ret_5["ready"] or fwd_mfe_5["ready"] or clean["ready"]),
        "fwd_ret_5": fwd_ret_5,
        "fwd_mfe_5": fwd_mfe_5,
        "breach": _sample_delta(
            _breach_rate_sample(conditioned), _breach_rate_sample(baseline)
        ),
        "clean": clean,
        "mfe21": _sample_delta(
            _num_sample(conditioned, "fwd_mfe_21"), _num_sample(baseline, "fwd_mfe_21")
        ),
    }
    return result


# ── W-OVC: new pre-registered bucket tests (2026-07-17) ─────────────────────

def _vanna_relief_test(df: pd.DataFrame) -> dict:
    """S-VANNA-RELIEF: vanna-relief vol compression flag.

    Condition: opt_vanna_relief == True (IV fell 5d AND vanna_hedge_5d in top cross-
    sectional tercile per as_of) vs False.
    A10 primitives:
      PRIMARY:   post_cushion_breach delta (beneficial = LOWER breach in flagged bucket;
                 vanna relief = hedging flow compresses vol = fewer stop-outs)
      SECONDARY: terminal_state_clean8_21, fwd_mfe_21 (reported honestly; compression may
                 trim both tails — no pre-judged direction per masterplan §4 registration)
    Scored=false, building_history until n≥30/bucket.
    CAUTION-ONLY per RO-3: holdability / de-escalation / stop-width context only.
    NOT an entry originator; never initiates a new position.

    Pre-registered gate (OPTIONS_ALPHA_MASTERPLAN.md §4 W-OVC, 2026-07-17).
    Era: single live-accrual (2026→); stamp ships in W-OVC first (same pattern as S-PIN_RISK).
    """
    col = "opt_vanna_relief"
    if col not in df.columns or df[col].notna().sum() == 0:
        return {"bucket": "S-VANNA-RELIEF", "n_cond": 0, "n_base": 0, "ready": False,
                "note": (f"{col} not yet stamped — W-OVC harness extension (stamp ships "
                         "in this PR; history accrues from live fires)")}
    flag = df[col].astype("boolean")
    sub = df[flag.notna()].copy()
    submask = sub[col].astype("boolean") == True  # noqa: E712
    result = _bucket_test(
        sub, submask.fillna(False),
        "S-VANNA-RELIEF: opt_vanna_relief=True (IV fell 5d AND vanna_hedge top-tercile)"
    )
    result["caution_only"] = True
    result["note"] = (
        "CAUTION-ONLY (RO-3): holdability / de-escalation / stop-width state. "
        "PRIMARY = breach delta (beneficial = LOWER breach). "
        "SECONDARY = clean + mfe21 (reported honestly; no pre-judged direction). "
        "Never originates a new entry. "
        "Sign note (audit #29): flag uses signed net vanna under long-call/short-put "
        "dealer convention; mechanism narrative inherits that assumption."
    )
    return result


def _front_charm_test(df: pd.DataFrame) -> dict:
    """S-FRONT-CHARM: front-expiry charm concentration flag (caution-only).

    Condition: opt_front7_charm_share in top cross-sectional tercile per as_of vs rest.
    A10 primitives:
      PRIMARY:   post_cushion_breach delta (beneficial = HIGHER breach in flagged bucket →
                 flag correctly identifies vol-exposed entries; CAUTION-ONLY per RO-3)
      SECONDARY: terminal_state_clean8_21, fwd_mfe_21 (reported honestly)
    Scored=false, building_history until n≥30/bucket.
    CAUTION-ONLY per RO-3: elevated front-charm = wider stops / worse holdability.
    May only LOWER conviction; never initiates a negative position.

    Root-class caveat (RUL-OVC-3): opt_root_class is reported per-class once n allows.
    ETF-slice sign is era-unstable (robustness §3.2) — do not interpret without root_class.

    Pre-registered gate (OPTIONS_ALPHA_MASTERPLAN.md §4 W-OVC, 2026-07-17).
    Era: single live-accrual (2026→); stamp ships in W-OVC first.
    """
    col = "opt_front7_charm_share"
    if col not in df.columns or df[col].notna().sum() == 0:
        return {"bucket": "S-FRONT-CHARM", "n_cond": 0, "n_base": 0, "ready": False,
                "note": (f"{col} not yet stamped — W-OVC harness extension (stamp ships "
                         "in this PR; history accrues from live fires)")}
    charm_val = pd.to_numeric(df[col], errors="coerce")
    sub = df[charm_val.notna()].copy()
    if sub.empty:
        return {"bucket": "S-FRONT-CHARM", "n_cond": 0, "n_base": 0, "ready": False,
                "note": "no fires with opt_front7_charm_share stamped yet"}
    # Top tercile per as_of date (cross-sectional, matching stamp construction)
    tercile_hi = (
        sub.groupby("as_of")[col]
        .transform(lambda x: x.quantile(2.0 / 3.0))
    )
    submask = pd.to_numeric(sub[col], errors="coerce") >= tercile_hi
    result = _bucket_test(
        sub, submask.fillna(False),
        "S-FRONT-CHARM: opt_front7_charm_share top-tercile (near-term charm concentration)"
    )
    root_breakdown: dict[str, dict] = {}
    if "opt_root_class" in sub.columns:
        for root_class, class_sub in sub[sub["opt_root_class"].notna()].groupby(
            "opt_root_class", sort=True
        ):
            class_mask = submask.loc[class_sub.index].fillna(False)
            root_breakdown[str(root_class)] = _bucket_test(
                class_sub,
                class_mask,
                f"S-FRONT-CHARM root-class diagnostic: {root_class}",
            )
    result["root_class_breakdown"] = root_breakdown
    result["root_class_stratification_present"] = bool(root_breakdown)
    result["caution_only"] = True
    result["note"] = (
        "CAUTION-ONLY (RO-3): elevated front-charm = higher near-term vol risk = wider stops. "
        "PRIMARY = breach delta (beneficial = HIGHER breach — flag correctly identifies "
        "vol-exposed entries). SECONDARY = clean + mfe21 (reported honestly). "
        "Never initiates a negative position. "
        "Root-class caveat: ETF-slice sign is era-unstable (robustness §3.2 of adjudication); "
        "per-class breakdowns reported once n≥30 per class."
    )
    return result


def _verdict_for_vanna_relief(t: dict) -> str:
    """Verdict for S-VANNA-RELIEF.

    Pre-registered primitives: {breach, clean, mfe21}.
    Primary beneficial direction: breach delta < 0 (LOWER stop-outs in flagged bucket).
    Secondary: clean + mfe21 reported honestly (no pre-judged direction for secondaries).
    A 'signal' verdict requires the PRIMARY breach delta to exclude 0 in the beneficial
    direction (breach < 0). Secondary deltas are evidence only (reported, not gating)."""
    return _verdict_from_cells([(t.get("breach"), "lower")])


def _verdict_for_front_charm(t: dict) -> str:
    """Verdict for S-FRONT-CHARM (caution-only).

    Pre-registered primitives: {breach, clean, mfe21}.
    PRIMARY beneficial direction: breach delta > 0 (HIGHER stop-outs in flagged bucket —
    flag correctly identifies vol-exposed entries). CAUTION-ONLY per RO-3.
    A 'signal' verdict requires the PRIMARY breach delta to exclude 0 with delta > 0."""
    return _verdict_from_cells([(t.get("breach"), "higher")])


def _compute_wc_coverage(df: pd.DataFrame) -> dict:
    """Compute coverage percentages for W-C and W-OVC stamp columns.  Returns dict of
    col -> (n_non_null, pct_float) for each column present."""
    tracked_cols = [
        # W-C columns
        "opt_ivspread_rel", "opt_skew", "opt_skew_5d_chg",
        "opt_opex_days", "opt_pin_risk",
        "opt_wall_dist_up_pct", "opt_wall_dist_down_pct",
        # W-OVC columns
        "opt_vanna_relief", "opt_front7_charm_share", "opt_root_class",
    ]
    n_total = max(len(df), 1)
    out = {}
    for col in tracked_cols:
        if col in df.columns:
            n_col = int(df[col].notna().sum())
            out[col] = (n_col, round(n_col / n_total * 100.0, 1))
        else:
            out[col] = (0, 0.0)
    return out


# ── gate assembly ────────────────────────────────────────────────────────────
def build_gate(df: pd.DataFrame) -> dict:
    """Run the pre-registered bucket tests and assemble the gate.json payload.

    ``df`` is the horizon-row stamped ledger.  It is reduced to declared-population
    canonical fires before any mask or tercile.  All inferential outputs are descriptive
    until the explicit promotion blockers are resolved.
    """
    df, population = _canonical_fire_frame(df)
    tests: dict[str, dict] = {}

    # S-DOI: informed-accumulation bucket — positive vs non-positive 5d call-OI slope
    if "opt_doi_slope_5d" in df.columns and df["opt_doi_slope_5d"].notna().any():
        doi = pd.to_numeric(df["opt_doi_slope_5d"], errors="coerce")
        # only rows with a stamped slope participate; NaN slope → excluded from both buckets
        sub = df[doi.notna()].copy()
        submask = pd.to_numeric(sub["opt_doi_slope_5d"], errors="coerce") > 0
        tests["S-DOI"] = _bucket_test(sub, submask, "S-DOI: doi_slope_5d > 0 (call-OI accumulating)")
    else:
        tests["S-DOI"] = {"bucket": "S-DOI", "n_cond": 0, "n_base": 0, "ready": False,
                          "note": "no stamped opt_doi_slope_5d yet (needs ≥5 prior chain days per name)"}

    # S-IVR: cheap-convexity bucket — LOW iv-rank vs HIGH. opt_iv_rank_252 is ALWAYS NULL
    # until the post-W1.1 backfill PR (A9), so this bucket is unpopulated by construction now.
    if "opt_iv_rank_252" in df.columns and df["opt_iv_rank_252"].notna().any():
        ivr = pd.to_numeric(df["opt_iv_rank_252"], errors="coerce")
        sub = df[ivr.notna()].copy()
        submask = pd.to_numeric(sub["opt_iv_rank_252"], errors="coerce") <= 0.30  # bottom-third rank
        tests["S-IVR"] = _bucket_test(sub, submask, "S-IVR: iv_rank_252 ≤ 0.30 (cheap convexity)")
    else:
        tests["S-IVR"] = {"bucket": "S-IVR", "n_cond": 0, "n_base": 0, "ready": False,
                          "note": "opt_iv_rank_252 is null until the post-W1.1 IV-backfill PR (ruling A9)"}

    # S-VOI: fresh-positioning bucket — voi_flag True vs False. Fast read on 5d + full on 21d clean.
    if "opt_voi_flag" in df.columns and df["opt_voi_flag"].notna().any():
        flag = df["opt_voi_flag"].astype("boolean")
        sub = df[flag.notna()].copy()
        submask = sub["opt_voi_flag"].astype("boolean") == True  # noqa: E712
        tests["S-VOI"] = _bucket_test(sub, submask.fillna(False),
                                      "S-VOI: voi_flag True (vol>prior-OI fresh positioning)")
        tests["S-VOI-fast"] = _voi_fast_test(df)
    else:
        tests["S-VOI"] = {"bucket": "S-VOI", "n_cond": 0, "n_base": 0, "ready": False,
                          "note": "no stamped opt_voi_flag yet"}
        tests["S-VOI-fast"] = {"bucket": "S-VOI-fast", "n_cond": 0, "n_base": 0, "ready": False}

    # S-WALL: raw-close wall-touch study (counts only; A10)
    tests["S-WALL"] = _wall_touch_study(df)

    # ── W-C additions: fire-conditioned buckets on new stamp cols ─────────────
    # S-IVSPREAD-F: positive ivspread_rel at fire (call richening vs puts = bullish tilt)
    tests["S-IVSPREAD-F"] = _ivspread_f_test(df)

    # S-SKEW_DECEL: skew in top cross-sectional tercile AND falling (de-escalation signal)
    tests["S-SKEW_DECEL"] = _skew_decel_test(df)

    # S-TOP_RISK: de-escalation family flag (caution-only: beneficial = flagged fires worse)
    tests["S-TOP_RISK"] = _top_risk_test(df)

    # S-PIN_RISK: OPEX proximity + long-gamma + near-wall flag
    tests["S-PIN_RISK"] = _pin_risk_test(df)

    # S-VOI2: stricter vol>OI burst — future stamp col, building_history until col exists
    tests["S-VOI2"] = _voi2_test(df)

    # ── W-OVC additions: vanna-relief and front-charm gate cells ─────────────
    # S-VANNA-RELIEF: holdability state (IV fell + top vanna_hedge tercile)
    tests["S-VANNA-RELIEF"] = _vanna_relief_test(df)

    # S-FRONT-CHARM: front-expiry charm concentration caution flag
    tests["S-FRONT-CHARM"] = _front_charm_test(df)

    # Family-specific authority fences from the exact registrations.  The pooled DOI
    # bucket cannot substitute for the registered cross-sectional rank-IC/HAC receipt;
    # pooled FRONT-CHARM cannot substitute for its mandatory root-class adjudication.
    tests["S-DOI"]["promotion_blockers"] = ["JOINED_HAC_RECEIPT_REQUIRED"]
    tests["S-FRONT-CHARM"]["promotion_blockers"] = [
        "ROOT_CLASS_STRATIFICATION_AUTHORITY_REQUIRED"
    ]

    # Populate all 36 exact preregistered cells and run BH before any verdict is formed.
    fdr_family = _apply_registered_family_fdr(tests)

    # per-test verdicts (only bucket-delta tests carry a verdict; S-WALL is counts-only)
    _standard_tests = ("S-DOI", "S-IVR", "S-IVSPREAD-F", "S-SKEW_DECEL")
    verdicts = {}
    for tid in _standard_tests:
        t = tests[tid]
        verdicts[tid] = _verdict_for_test(t) if "breach" in t else "building_history"
    verdicts["S-VOI"] = _verdict_for_fast_positioning(tests["S-VOI"], tests["S-VOI-fast"])
    verdicts["S-VOI2"] = _verdict_for_fast_positioning(tests["S-VOI2"])
    # Caution tests use per-bucket verdict functions (different registered primitives):
    #   S-TOP_RISK: {breach, clean} — _verdict_for_top_risk
    #   S-PIN_RISK: {clean, mfe21} — _verdict_for_pin_risk (breach is NOT registered)
    #   S-VANNA-RELIEF: {breach primary, clean+mfe21 secondary} — _verdict_for_vanna_relief
    #   S-FRONT-CHARM: {breach primary (higher=beneficial), clean+mfe21 secondary} — caution-only
    verdicts["S-TOP_RISK"] = (
        _verdict_for_top_risk(tests["S-TOP_RISK"])
        if "breach" in tests["S-TOP_RISK"] else "building_history"
    )
    verdicts["S-PIN_RISK"] = (
        _verdict_for_pin_risk(tests["S-PIN_RISK"])
        if "clean" in tests["S-PIN_RISK"] else "building_history"
    )
    verdicts["S-VANNA-RELIEF"] = (
        _verdict_for_vanna_relief(tests["S-VANNA-RELIEF"])
        if "breach" in tests["S-VANNA-RELIEF"] else "building_history"
    )
    verdicts["S-FRONT-CHARM"] = (
        _verdict_for_front_charm(tests["S-FRONT-CHARM"])
        if "breach" in tests["S-FRONT-CHARM"] else "building_history"
    )

    # W-C + W-OVC coverage percentages (honest reporting)
    wc_col_coverage = _compute_wc_coverage(df)

    def _counts(t: dict) -> str:
        return (
            f"fires={t.get('n_cond', 0)}/{t.get('n_base', 0)} "
            f"dates={t.get('n_dates_cond', 0)}/{t.get('n_dates_base', 0)} "
            f"overlap_dates={t.get('n_overlap_dates', 0)}"
        )

    # evidence lines — LIVE per-bucket n counts (doctrine §2.3: n before any verdict)
    evidence: list[str] = []
    for tid in ("S-IVR", "S-DOI", "S-VOI"):
        t = tests[tid]
        if t.get("ready"):
            evidence.append(f"{tid}: {_counts(t)} → descriptive_status={verdicts[tid]}")
        else:
            note = t.get("note", "")
            evidence.append(
                f"{tid}: building history ({_counts(t)}; need {MIN_PER_BUCKET} fires, "
                f"{MIN_DATES_PER_BUCKET} dates, {MIN_OVERLAP_DATES} overlapping dates/bucket)"
                f"{(' — ' + note) if note else ''}")
    vf = tests["S-VOI-fast"]
    evidence.append(
        f"S-VOI-fast (5d): {_counts(vf)} → descriptive_status={verdicts['S-VOI']}")
    w = tests["S-WALL"]
    evidence.append(
        f"S-WALL: {w['n_priced']}/{w['n_eligible']} eligible fires priced "
        f"(price_store_available={w['price_store_available']}); wall_touches={w['wall_touches']}, "
        f"fixed−5%_touches={w['fixed_stop_touches']}, wall_before_fixed={w['wall_before_fixed']}. "
        f"LIMITATION: {w['limitation']}")
    # W-C bucket evidence lines
    for tid in ("S-IVSPREAD-F", "S-SKEW_DECEL", "S-TOP_RISK", "S-PIN_RISK", "S-VOI2"):
        t = tests[tid]
        vdict = verdicts.get(tid, "building_history")
        if t.get("ready"):
            evidence.append(
                f"{tid}: {_counts(t)} → descriptive_status={vdict}")
        else:
            note = t.get("note", "")
            evidence.append(
                f"{tid}: building history ({_counts(t)}; need {MIN_PER_BUCKET} fires, "
                f"{MIN_DATES_PER_BUCKET} dates, {MIN_OVERLAP_DATES} overlapping dates/bucket)"
                f"{(' — ' + note) if note else ''}")
    # W-OVC bucket evidence lines
    for tid in ("S-VANNA-RELIEF", "S-FRONT-CHARM"):
        t = tests[tid]
        vdict = verdicts.get(tid, "building_history")
        if t.get("ready"):
            evidence.append(
                f"{tid}: {_counts(t)} → descriptive_status={vdict}")
        else:
            note = t.get("note", "")
            evidence.append(
                f"{tid}: building history ({_counts(t)}; need {MIN_PER_BUCKET} fires, "
                f"{MIN_DATES_PER_BUCKET} dates, {MIN_OVERLAP_DATES} overlapping dates/bucket)"
                f"{(' — ' + note) if note else ''}")
    # coverage lines (W-C + W-OVC)
    for col, (n_col, pct) in wc_col_coverage.items():
        evidence.append(f"stamp coverage [{col}]: {n_col}/{len(df)} rows ({pct:.1f}%)")

    return {
        "schema": "options_entry.gate.v3",
        "generated_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "scored": False,
        "status": "building_history",
        "weight": 0.0,
        "horizons": [5, 10, 21],
        "min_per_bucket": MIN_PER_BUCKET,
        "min_dates_per_bucket": MIN_DATES_PER_BUCKET,
        "min_overlap_dates": MIN_OVERLAP_DATES,
        "population": population,
        "n_ledger_rows": population["raw_rows"],
        "n_canonical_events": len(df),
        "n_stamped_rows": population["declared_lane_stamped_rows"],
        "n_stamped_events": int(
            df[[col for col in STAMP_COVERAGE_COLS if col in df.columns]]
            .notna().any(axis=1).sum()
        ) if any(col in df.columns for col in STAMP_COVERAGE_COLS) else 0,
        "promotion_blockers": list(GLOBAL_PROMOTION_BLOCKERS),
        "promotion_authority": {
            "state": "frozen",
            "current_statistics": "descriptive_iid_only",
            "pre_amendment_data_authority": "barred",
            "required_next_amendment": (
                "Before a fresh authority cohort starts, freeze a date-cluster/block "
                "estimator, a sequential-look schedule/alpha budget, and family-specific "
                "HAC/root-class receipts."
            ),
        },
        "fdr_family": {
            **fdr_family,
            "description": (
                "All fire-conditioned bucket tests × A10 primitives × live-accrual era (2026→). "
                "36 tests total: 28 OVC buckets (S-IVR×3, S-DOI×3, S-VOI×3, S-IVSPREAD-F×3, "
                "S-SKEW_DECEL×3, S-TOP_RISK×2, S-PIN_RISK×2, S-VOI2×3, S-VANNA-RELIEF×3, "
                "S-FRONT-CHARM×3) plus 8 FS-3 flow-score cells "
                "(S-FLOWML-0_7×1, S-FLOWML-8_90×1, S-FLOWML-90P×2 [63d primary + 126d secondary], "
                "and per-era holdout cells totalling 8 cells per FS-3 prereg 2026-07-13). "
                "BH-FDR threshold for k-th ranked p-value: p_k <= (k/36) * 0.10 "
                "(most-significant single-test threshold ≈ 0.0028). "
                "BH diagnostics use alpha=0.10 over this full 36-test family, but are "
                "descriptive-only and cannot create signal authority. See OPTIONS_ALPHA_MASTERPLAN.md §4 FS-3 "
                "Enlarged-family BH-FDR statement (2026-07-13: 28+8=36). "
                "Unavailable or immature registered cells are retained at p=1. Descriptive "
                "maturity requires exact-metric n>=30 fires, >=30 dates per bucket, and >=30 "
                "overlapping dates. IID CI/p-values carry no promotion authority. "
                "FS-3 cells remain reserved at p=1 until "
                "their separate governed harness emits results."
            ),
        },
        "per_family_status": {
            "S-IVR": verdicts.get("S-IVR", "building_history"),
            "S-DOI": verdicts.get("S-DOI", "building_history"),
            "S-VOI": verdicts.get("S-VOI", "building_history"),
            "S-IVSPREAD-F": verdicts.get("S-IVSPREAD-F", "building_history"),
            "S-SKEW_DECEL": verdicts.get("S-SKEW_DECEL", "building_history"),
            "S-TOP_RISK": verdicts.get("S-TOP_RISK", "building_history"),
            "S-PIN_RISK": verdicts.get("S-PIN_RISK", "building_history"),
            "S-VOI2": verdicts.get("S-VOI2", "building_history"),
            "S-VANNA-RELIEF": verdicts.get("S-VANNA-RELIEF", "building_history"),
            "S-FRONT-CHARM": verdicts.get("S-FRONT-CHARM", "building_history"),
        },
        "tests": tests,
        "verdicts": verdicts,
        "evidence": evidence,
        "note": (
            "Pre-registered entry-quality gate (S-IVR/S-DOI/S-WALL/S-VOI + W-C: "
            "S-IVSPREAD-F/S-SKEW_DECEL/S-TOP_RISK/S-PIN_RISK/S-VOI2 + W-OVC: "
            "S-VANNA-RELIEF/S-FRONT-CHARM). Display/ledger-seed only. Current IID "
            "bootstrap/permutation outputs are descriptive and never promote a signal. "
            "Exact-metric maturity requires n≥30 fires, n≥30 dates, and n≥30 shared dates "
            "per bucket (doctrine §2.3). "
            "Ledger primitives only (ruling A10). FDR family=36 tests, BH α=0.10. "
            "No pre-amendment observation may support authority; cluster inference and a "
            "frozen sequential-look plan must be registered before a fresh cohort. "
            "S-TOP_RISK/S-PIN_RISK/S-FRONT-CHARM are caution-only: beneficial direction = "
            "flagged fires worse/higher-vol (correctly de-escalates). "
            "S-VANNA-RELIEF is caution-only: holdability context only, not an entry originator. "
            "Never initiates a negative position (RO-3)."
        ),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--ledger", default=str(LEDGER_PATH))
    args = ap.parse_args()

    ledger = Path(args.ledger)
    GATE_DIR.mkdir(parents=True, exist_ok=True)

    if not ledger.exists():
        empty = pd.DataFrame(columns=[*EVENT_KEY, "horizon", "ret", *STAMP_COLS])
        gate = build_gate(empty)
        gate["evidence"] = ["ledger absent — no fires stamped yet"]
        gate["note"] = "board ledger not found; gate awaits first stamped rows"
    else:
        df = pd.read_parquet(ledger)
        gate = build_gate(df)

    GATE_PATH.write_text(json.dumps(gate, indent=1, default=str))
    if not args.quiet:
        print(f"[options_entry] wrote {GATE_PATH.relative_to(config.data_dir().parent)} "
              f"(scored={gate['scored']}, status={gate['status']})")
        for line in gate.get("evidence", []):
            print(f"  · {line}")


if __name__ == "__main__":
    main()
