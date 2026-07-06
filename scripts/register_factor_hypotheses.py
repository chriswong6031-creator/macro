"""scripts/register_factor_hypotheses.py — File metabolism registrations for H1–H5.

Factor Intelligence Program P2 deliverable (masterplan §7-P2 + PREREGISTRATION.md).

BUDGET BATCHING (PREREGISTRATION.md §1 + masterplan §4.2):
  BUDGET_PER_WEEK=3 (metabolism.py line 83).  Today is ISO week 2026-W27.
  - Batch 1 (W27, --only h1,h2,h3): H1, H2, H3 — files this week.
  - Batch 2 (W28+, --only h4,h5):   H4, H5 — files from 2026-07-06+.
  Do NOT run both batches in the same calendar week.

BUDGET PRE-FLIGHT (FIX-7):
  Before any writes, register_batch reads the remaining weekly budget via
  _count_week_registrations() from metabolism.  If the remaining budget
  (BUDGET_PER_WEEK − already_filed_this_week) < len(pending keys), the entire
  batch is aborted with a clear message.  Partial filing (e.g. H1+H2 filed, H3
  silently dropped by metabolism's own budget enforcement) is worse than a
  delayed batch because a silently-dropped H3 looks registered to the operator.
  The pre-flight counts only PENDING keys (not already registered) so a batch
  that is already fully filed never falsely aborts on an exhausted week.
  --defer-on-budget turns the pre-flight abort into a clean exit 0 ("deferred")
  for the nightly cortex-job step, which simply retries the batch every night
  until an ISO week with enough budget.

METRIC ENUM FINDING (P2 audit, 2026-07-05):
  The evaluator (scripts/evaluate_cortex_hypotheses.py) accepts ONLY:
    PATH A (conditional_regime, lead_lag, sector_conditional):
      "hit_rate"    — fraction of spine rows with outcome_excess > 0
      "excess_mean" — mean(outcome_excess) over post-registration rows
    PATH B (entry_quality):
      "stop_out_rate" — pooled stop-out rate from walk_forward harness

  "delta_P_cushioned_liftoff" (the worked payload in PREREGISTRATION.md §1)
  is NOT an accepted metric string.  The evaluator falls back to "hit_rate"
  on unknown metric names (line 273: `else: metric_value = hits / n`).

  NEAREST-METRIC MAPPING (per K-7 ruling + PREREGISTRATION.md §1 honesty note):
  ┌─────┬─────────────────────┬────────────────────────────────────────────────┐
  │  H  │ Prereg metric       │ Registered metric + mapping note               │
  ├─────┼─────────────────────┼────────────────────────────────────────────────┤
  │ H1  │ Δ P(CUSHIONED∪      │ "stop_out_rate" via PATH B (entry_quality).    │
  │     │ CLEAN_LIFTOFF, 21d) │ walk_forward computes stop_out_rate directly.  │
  │     │ on factor_annotated │ factor_annotated=True LOWERS stop-out rate.    │
  │     │ =True vs False      │ Gate threshold +0.05.  DIRECTION: −1.          │
  ├─────┼─────────────────────┼────────────────────────────────────────────────┤
  │ H2  │ Δ P(CUSHIONED∪      │ "hit_rate" via PATH A (conditional_regime).     │
  │     │ CLEAN_LIFTOFF, 21d) │ spine rows for high_alibi_flag=True should have │
  │     │ on high_alibi_flag  │ lower hit_rate.  Gate threshold −0.05 (harm     │
  │     │ =True vs False      │ direction). DIRECTION: −1.                      │
  ├─────┼─────────────────────┼────────────────────────────────────────────────┤
  │ H3  │ P(STOPPED, 21d)     │ "hit_rate" via PATH A (conditional_regime).     │
  │     │ between-cell χ²     │ Heterogeneity test is not directly expressible  │
  │     │ permutation p       │ as a scalar gate; registered as hit_rate with   │
  │     │                     │ threshold 1.01 (unreachable — deliberately non-  │
  │     │                     │ passing context-only row; real gate lives in    │
  │     │                     │ validate_factor_h3.py permutation harness).     │
  ├─────┼─────────────────────┼────────────────────────────────────────────────┤
  │ H4  │ Δ P(STOPPED, 21d)   │ "stop_out_rate" via PATH B (entry_quality).    │
  │     │ on twin_bleed_flag  │ walk_forward computes stop_out_rate directly.  │
  │     │ =True vs False      │ twin_bleed_flag=True RAISES stop-out rate.     │
  │     │                     │ Gate threshold +0.05.  DIRECTION: +1.           │
  ├─────┼─────────────────────┼────────────────────────────────────────────────┤
  │ H5  │ Δ P(−5% within 21d) │ "hit_rate" via PATH A (lead_lag shape).         │
  │     │ on decay_flag=True  │ decay_flag=True rows should hit −5% more.       │
  │     │ vs False            │ Gate threshold +0.05.  DIRECTION: +1.           │
  └─────┴─────────────────────┴────────────────────────────────────────────────┘

  CONSEQUENCE: the metabolism registration is context-only (PREREGISTRATION.md §1
  honesty note: "the machine registration is context-only and does NOT participate
  in this document's 5-way BH family").  The REAL gates live in the locked prereg
  and in the validate_factor_h{1-5}.py harnesses.  Gate numbers in this script
  reflect the metabolism floor only; the locked prereg thresholds (−5pp, +5pp, etc.)
  do NOT move regardless of what the evaluator's metric enum accepts.

REGISTRY TRACKING (FIX-8, amended 2026-07-06):
  The original persistence path (dispatch via factor_ops.yml; rows "ride the next
  nightly's git add") NEVER WORKED: each workflow job starts from a fresh
  actions/checkout (git clean -ffdx), so registry rows written in the factor_ops
  runner workspace were wiped before any commit step could see them — the same
  cross-job visibility hole as the factor_attention firings bug (PR #1583).  The
  W27 register_h123 and W28 register_h45 dispatch registrations were both lost
  this way (verified 2026-07-06: machine_registry.jsonl has no git history).
  THE PERSISTENCE PATH IS NOW: this script runs as a step INSIDE the nightly
  cortex job (daily.yml), whose commit lane explicitly stages
  data/neuralweb/machine_registry.jsonl + governance.jsonl + trial_ledger.jsonl.
  Do NOT add .gitignore for machine_registry.jsonl — git history is the
  tamper-detection substrate per metabolism.py lines 20-24.

IDEMPOTENCE:
  metabolism.register_hypothesis deduplicates by ID (content hash of date+hypothesis
  text).  Running this script twice on the same day produces duplicate IDs only if
  the hypothesis text is identical — which it is.  The _HOUSE_MIN_N clamp means
  re-registration writes the same row.  However, each run ALSO increments the weekly
  budget counter.  The script therefore checks the registry for an existing
  hypothesis string before calling register_hypothesis.  If a matching hypothesis
  string already exists with status ∈ {registered, accruing, insufficient-n}, the
  registration is skipped.

Usage
-----
    # Canonical path: the nightly cortex job runs both batches with
    # --defer-on-budget (idempotent; a budget-blocked batch retries nightly).
    python -m scripts.register_factor_hypotheses --only h1,h2,h3 --defer-on-budget
    python -m scripts.register_factor_hypotheses --only h4,h5 --defer-on-budget

    # Dry-run: print payloads, no writes
    python -m scripts.register_factor_hypotheses --only h1,h2,h3 --dry-run
    python -m scripts.register_factor_hypotheses --only h4,h5 --dry-run
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Hypothesis payloads (full, per locked PREREGISTRATION.md §3)
# ---------------------------------------------------------------------------
# Each payload dict is passed verbatim to metabolism.register_hypothesis.
# Required fields: hypothesis, claim_shape, spine_query, pre_committed_gate, horizon_d.
# Forbidden: registered_at, cortex_attention in spine_query, fdr_family.
#
# METRIC MAPPING NOTES per the evaluator audit above — see module docstring.
# GATE THRESHOLDS: these are the metabolism floor gates (context-only).
# The LOCKED PREREG THRESHOLDS (−0.05, +0.05, etc.) are reproduced in
# validate_factor_h{1-5}.py and are separate from these registration rows.

H1_PAYLOAD: dict = {
    # PREREGISTRATION.md §3 H1 — Factor-Adjusted Confluence Annotation
    "hypothesis": (
        "H1: factor_annotated fires (sector_rel_cross OR resid_led) have higher "
        "P(CUSHIONED∪CLEAN_LIFTOFF at 21d) than non-annotated fires "
        "(population: T1/T2 fires in replay artifact)"
    ),
    # Masterplan §4.2: H1 → entry_quality
    "claim_shape": "entry_quality",
    "spine_query": {
        "feature": "factor_annotated",
        "sub_features": ["sector_rel_cross", "resid_led"],
        "population": "tier_cascade:T1,T2 fires in replay",
        "source": "factor_panel",
        "window_d": 21,
        # no cortex_attention or reflex.cortex_attention refs (Article 1)
    },
    "horizon_d": 21,
    "pre_committed_gate": {
        # PATH B (entry_quality): walk_forward harness computes stop_out_rate directly.
        # factor_annotated=True LOWERS stop-out rate (better entries).
        # direction_expected=-1: lower stop_out_rate is the positive outcome.
        # Prereg threshold: stop_out_rate difference ≥ 5pp (annotated arm lower).
        # metabolism threshold +0.05 applied to the magnitude of the rate gap.
        "metric": "stop_out_rate",
        "threshold": 0.05,   # prereg locked: +5pp absolute stop-out gap (§3 H1 gate)
        "min_n": 25,          # clamped to _HOUSE_MIN_N=25; real floors: ≥150 fires/arm
        "horizon_d": 21,
        "direction_expected": -1,  # negative: factor_annotated=True LOWERS stop-out rate
        # MAPPING NOTE: PATH B evaluator computes stop_out_rate natively via
        # walk_forward harness.  No fictional '1 - stop_out_rate' transform.
        # validate_factor_h1.py uses month-block bootstrap on the locked prereg gate.
        "_metric_mapping_note": (
            "PATH B (entry_quality): stop_out_rate is the evaluator's native metric. "
            "factor_annotated=True arm expected to have LOWER stop-out rate. "
            "direction_expected=-1 (lower is better for the annotated arm). "
            "Locked prereg gate and BH-FDR live in validate_factor_h1.py."
        ),
    },
    "registered_by": "factor_intelligence_p2_builder",
    "notes": (
        "H1 — PREREGISTRATION.md §3. Metabolism gate is context-only. "
        "Real gate: month-block bootstrap 95% CI of Δ P(CUSHIONED∪CLEAN_LIFTOFF,21d) "
        "on factor_annotated=True vs False, excludes 0 on positive side, "
        "effect ≥ max(5pp, 10% pooled base rate). Min n: ≥10 months AND ≥150 fires/arm. "
        "BH family: factor_intelligence_v1, q=0.10. "
        "METRIC: stop_out_rate (PATH B, walk_forward harness native). "
        "factor_annotated=True LOWERS stop-out rate (direction_expected=-1)."
    ),
}

H2_PAYLOAD: dict = {
    # PREREGISTRATION.md §3 H2 — Borrowed-Strength (Alibi) Veto Validity
    "hypothesis": (
        "H2: high_alibi_flag fires have lower P(CUSHIONED∪CLEAN_LIFTOFF,21d) "
        "than non-flagged fires "
        "(alibi_share_20d ≥ trailing-252d Q80; population: all fires)"
    ),
    # Masterplan §4.2: H2 → conditional_regime
    "claim_shape": "conditional_regime",
    "spine_query": {
        "feature": "high_alibi_flag",
        "window_d": 20,           # alibi_share_20d window (5d/60d are descriptive only)
        "threshold_pct": 80,      # Q80 trailing-252d cross-sectional
        "source": "factor_panel",
        # MH CLAUSE: multiple-testing clause lives in the study (alpha_z_house
        # stratification), not in the metabolism gate (per masterplan §4.2 note).
        # no cortex_attention refs
    },
    "horizon_d": 21,
    "pre_committed_gate": {
        # METRIC MAPPING: "delta_P_cushioned_liftoff" not in evaluator enum.
        # Nearest accepted metric for conditional_regime PATH A → "hit_rate".
        # PREREG THRESHOLD: −5pp (high_alibi fires have worse outcomes — harm direction).
        # metabolism threshold: −0.05 (direction_expected=−1 → "passed" if ≤ threshold).
        "metric": "hit_rate",
        "threshold": -0.05,    # prereg locked: −5pp (§3 H2 gate, harm direction)
        "min_n": 25,            # clamped to _HOUSE_MIN_N; real floors: ≥150 fires/arm
        "horizon_d": 21,
        "direction_expected": -1,  # negative: high_alibi fires have lower hit_rate
        "_metric_mapping_note": (
            "delta_P_cushioned_liftoff not in evaluator enum; "
            "registered as hit_rate (nearest PATH-A metric, conditional_regime shape). "
            "Harm direction: high_alibi_flag=True fires expected to underperform. "
            "MH clause (alpha_z_house stratification) lives in validate_factor_h2.py."
        ),
    },
    "registered_by": "factor_intelligence_p2_builder",
    "notes": (
        "H2 — PREREGISTRATION.md §3. Metabolism gate is context-only. "
        "Real gate: month-block bootstrap 95% CI of Δ P(CUSHIONED∪CLEAN_LIFTOFF,21d) "
        "on high_alibi_flag=True vs False, excludes 0 on negative side, "
        "effect ≥ max(5pp, 10% pooled base rate). PLUS: second gate clause = "
        "alpha_z_house-stratified pooled one-sided CI excludes 0 on harm side. "
        "Min n: ≥10 months AND ≥150 fires/arm. BH family: factor_intelligence_v1. "
        "METRIC MAPPING: delta_P_cushioned_liftoff → hit_rate (evaluator enum constraint). "
        "MH clause lives in the study, not the metabolism gate (masterplan §4.2)."
    ),
}

H3_PAYLOAD: dict = {
    # PREREGISTRATION.md §3 H3 — DNA × Style-Regime Drawdown Discrimination
    "hypothesis": (
        "H3: P(STOPPED at 21d) is heterogeneous across DNA × style_regime cells "
        "(Pearson χ² permutation test on qualifying cells with ≥30 deduped fires; "
        "population: all fires with non-null dna_class and style_regime)"
    ),
    # Masterplan §4.2: H3 → conditional_regime
    "claim_shape": "conditional_regime",
    "spine_query": {
        "feature": "dna_class_x_style_regime",
        "dna_classes": [
            "quality_growth", "high_beta_liquidity", "cyclical_value",
            "defensive_quality", "rate_duration_sensitive",
            "china_crypto_proxy", "small_spec", "mixed",
        ],
        "style_regimes": [
            "growth_momentum", "quality_defense", "value_cyclical",
            "junk_rally", "mixed",
        ],
        "cell_min_n": 30,   # per-cell floor for the primary χ² test
        "source": "factor_panel",
        # no cortex_attention refs
    },
    "horizon_d": 21,
    "pre_committed_gate": {
        # H3's primary test is a χ² permutation p-value — not expressible as a
        # scalar metabolism gate.  This row is DELIBERATELY NON-PASSING (context-only):
        # threshold=1.01 is unreachable (hit_rate ∈ [0,1] always), so the metabolism
        # gate never auto-passes.  The REAL gate lives in validate_factor_h3.py
        # (permutation p < q_BH from the factor_intelligence_v1 family, ≥8 qualifying
        # cells, ≥12 contributing months).
        "metric": "hit_rate",
        "threshold": 1.01,  # unreachable — deliberately non-passing context-only row
        "min_n": 25,         # _HOUSE_MIN_N clamp; real: ≥30 fires/cell AND ≥8 cells AND ≥12 months
        "horizon_d": 21,
        "direction_expected": 1,
        "_metric_mapping_note": (
            "H3 primary test is χ² permutation heterogeneity — not a scalar metric. "
            "Registered as hit_rate threshold=1.01 (unreachable; deliberately non-passing). "
            "This row is context-only; the metabolism scalar gate CANNOT express a "
            "heterogeneity test.  REAL gate: permutation p < q_BH(factor_intelligence_v1, "
            "q=0.10), ≥8 qualifying cells with ≥30 fires each, ≥12 contributing months. "
            "Lives in validate_factor_h3.py."
        ),
    },
    "registered_by": "factor_intelligence_p2_builder",
    "notes": (
        "H3 — PREREGISTRATION.md §3. Metabolism gate is context-only (deliberately "
        "non-passing: threshold=1.01 is unreachable by hit_rate ∈ [0,1]). "
        "The metabolism scalar cannot express a heterogeneity test; this row is "
        "context-only and does not participate in the BH family evaluation. "
        "Real gate: permutation p < q_BH on Pearson χ² of P(STOPPED) heterogeneity "
        "across DNA×style_regime cells (qualifying: ≥30 deduped fires). "
        "Min n: ≥12 contributing months AND ≥8 qualifying cells. SLOW-ACCRUAL. "
        "BH family: factor_intelligence_v1. "
        "METRIC: hit_rate threshold=1.01 (non-passing sentinel); real gate in "
        "validate_factor_h3.py permutation harness."
    ),
}

H4_PAYLOAD: dict = {
    # PREREGISTRATION.md §3 H4 — Twin-Bleed Veto Validity
    "hypothesis": (
        "H4: twin_bleed_flag=True fires have higher P(STOPPED at 21d) "
        "than twin_bleed_flag=False fires "
        "(twin basket 20d return < 0 AND below 20d high by > trailing median pullback; "
        "population: fires with valid twin basket ≥8 peers)"
    ),
    # Masterplan §4.2: H4 → entry_quality
    "claim_shape": "entry_quality",
    "spine_query": {
        "feature": "twin_bleed_flag",
        "twin_definition": "top-12 peers by 252d Block-A residual correlation, GICS+size±1T",
        "bleed_condition": (
            "twin_20d_ret < 0 AND twin below 20d high by > trailing-60d median pullback"
        ),
        "source": "factor_panel",
        # no cortex_attention refs
    },
    "horizon_d": 21,
    "pre_committed_gate": {
        # PATH B (entry_quality): walk_forward harness computes stop_out_rate directly.
        # twin_bleed_flag=True RAISES stop-out rate (worse entries in twin-bled names).
        # direction_expected=+1: higher stop_out_rate on the flagged arm is the signal.
        # Prereg threshold: stop_out_rate difference ≥ 5pp (flagged arm higher).
        "metric": "stop_out_rate",
        "threshold": 0.05,   # prereg locked: +5pp Δ stop_out_rate on twin_bleed_flag=True
        "min_n": 25,          # _HOUSE_MIN_N; real: ≥10 months AND ≥60 flagged fires
        "horizon_d": 21,
        "direction_expected": 1,  # positive: twin_bleed_flag=True RAISES stop-out rate
        # MAPPING NOTE: PATH B evaluator computes stop_out_rate natively via
        # walk_forward harness.  No fictional delta computed at registration time.
        # validate_factor_h4.py runs month-block bootstrap on the locked prereg gate.
        "_metric_mapping_note": (
            "PATH B (entry_quality): stop_out_rate is the evaluator's native metric. "
            "twin_bleed_flag=True arm expected to have HIGHER stop-out rate. "
            "direction_expected=+1 (higher is the harm signal for the flagged arm). "
            "SLOW-ACCRUAL: ≥60 flagged fires (~12–18 months post replay merge). "
            "Real gate lives in validate_factor_h4.py."
        ),
    },
    "registered_by": "factor_intelligence_p2_builder",
    "notes": (
        "H4 — PREREGISTRATION.md §3. Metabolism gate is context-only. SLOW-ACCRUAL. "
        "Real gate: month-block bootstrap 95% CI of Δ P(STOPPED,21d) on "
        "twin_bleed_flag=True vs False, excludes 0 on positive side, "
        "effect ≥ max(5pp, 10% pooled base rate). "
        "Min n: ≥10 months AND ≥60 flagged fires. Est. 12–18 months post replay merge. "
        "METRIC: stop_out_rate (PATH B, walk_forward harness native). "
        "twin_bleed_flag=True RAISES stop-out rate (direction_expected=+1)."
    ),
}

H5_PAYLOAD: dict = {
    # PREREGISTRATION.md §3 H5 — Thesis-Decay in Held Names
    "hypothesis": (
        "H5: decay_flag=True held names are more likely to hit −5% within 21d "
        "than decay_flag=False names "
        "(decay_flag = resid_ret_20d<0 AND raw_20d_ret>0 AND alibi_share_20d rising; "
        "population: board ledger names with ≥10 consecutive board dates)"
    ),
    # Masterplan §4.2: H5 → lead_lag
    "claim_shape": "lead_lag",
    "spine_query": {
        "feature": "decay_flag",
        "decay_conditions": [
            "resid_ret_20d < 0",
            "raw_20d_return > 0",
            "alibi_share_20d rising over prior 10d",
        ],
        "population": "board ledger held names with board_tenure_days >= 10",
        "source": "board_ledger + factor_panel",
        "substrate": "data/us_board_ledger/retro_grades.parquet",
        # no cortex_attention refs
    },
    "horizon_d": 21,
    "pre_committed_gate": {
        # METRIC MAPPING: "delta_P_decay_flag" not in evaluator enum.
        # Nearest accepted for lead_lag PATH A → "hit_rate".
        # PREREG THRESHOLD: +5pp on Δ P(hit −5% within 21d) for decay_flag=True.
        "metric": "hit_rate",
        "threshold": 0.05,   # prereg locked: +5pp Δ P(−5% within 21d) on decay_flag=True
        "min_n": 25,          # _HOUSE_MIN_N; real: ≥10 months AND ≥40 flagged names
        "horizon_d": 21,
        "direction_expected": 1,  # positive: decay_flag=True more likely to retrace
        "_metric_mapping_note": (
            "delta_P_decay_flag not in evaluator enum; "
            "registered as hit_rate (nearest PATH-A scalar metric). "
            "SLOW-ACCRUAL: clock starts at first board date with non-null "
            "board_tenure_days AND matured 21d row (est. 2026-09-01). "
            "Earliest honest gauntlet: 2027-Q1. "
            "Real gate lives in validate_factor_h5.py."
        ),
    },
    "registered_by": "factor_intelligence_p2_builder",
    "notes": (
        "H5 — PREREGISTRATION.md §3. Metabolism gate is context-only. SLOW-ACCRUAL. "
        "H5 clock starts at first board date with non-null board_tenure_days AND "
        "at least one matured 21d row. Earliest gauntlet: 2027-Q1. "
        "Substrate: board forward ledger (NOT replay artifact). "
        "Real gate: month-block bootstrap 95% CI of Δ P(−5% within 21d) on "
        "decay_flag=True vs False, excludes 0 on positive side, "
        "effect ≥ max(5pp, 10% pooled base rate). "
        "Min n: ≥10 months AND ≥40 flagged names. "
        "METRIC MAPPING: delta_P_decay → hit_rate (evaluator enum constraint). "
        "TENURE NOTE: H5 reads board_tenure_days (NOT hold_days/days_basing). "
        "See grade_us_board.py _board_tenure docstring."
    ),
}

# ---------------------------------------------------------------------------
# Ordered batch definitions
# ---------------------------------------------------------------------------
_ALL_PAYLOADS: dict[str, dict] = {
    "h1": H1_PAYLOAD,
    "h2": H2_PAYLOAD,
    "h3": H3_PAYLOAD,
    "h4": H4_PAYLOAD,
    "h5": H5_PAYLOAD,
}

_BATCH_H123 = ["h1", "h2", "h3"]
_BATCH_H45 = ["h4", "h5"]


# ---------------------------------------------------------------------------
# Idempotence check — avoid double-registering the same hypothesis
# ---------------------------------------------------------------------------

def _already_registered(hypothesis_text: str, root: Path | str | None = None) -> bool:
    """Return True if a hypothesis with this exact text is already registered
    and has status in {registered, accruing, insufficient-n}.

    metabolism.py does NOT deduplicate by hypothesis text (it deduplicates by
    content-hash ID which includes the DATE, so the same hypothesis registered
    on two different days gets two different IDs).  This script adds a text-level
    check so re-running on the same or a different day does not burn budget.
    """
    try:
        from engine.neuralweb.metabolism import _load_registry  # type: ignore[import]
        rows = _load_registry(root)
        open_statuses = {"registered", "accruing", "insufficient-n"}
        for row in rows:
            if row.get("hypothesis") == hypothesis_text and row.get("status") in open_statuses:
                return True
        return False
    except Exception:  # noqa: BLE001 — fail-open
        return False


# ---------------------------------------------------------------------------
# Registration runner
# ---------------------------------------------------------------------------

def _count_week_registrations(root: Path | str | None = None, now: datetime | None = None) -> int:
    """Return the number of hypotheses already registered in the current ISO week.

    Reads machine_registry.jsonl directly (fail-open: returns 0 on any error
    so a registry-absent first run is not blocked).  The current ISO week is
    determined from `now` if provided, else UTC now.

    Used by the budget pre-flight in register_batch to decide whether the
    remaining weekly budget (BUDGET_PER_WEEK − already_filed) can absorb the
    incoming batch.
    """
    BUDGET_PER_WEEK = 3  # mirrors metabolism.py line 83
    try:
        from engine.neuralweb.metabolism import _load_registry  # type: ignore[import]
        rows = _load_registry(root)
    except Exception:  # noqa: BLE001 — fail-open
        return 0

    ref = now if now is not None else datetime.now(timezone.utc)
    current_iso_week = ref.isocalendar()[:2]  # (year, week)

    count = 0
    for row in rows:
        reg_at = row.get("registered_at")
        if not reg_at:
            continue
        try:
            reg_dt = datetime.fromisoformat(str(reg_at))
        except (ValueError, TypeError):
            continue
        if reg_dt.isocalendar()[:2] == current_iso_week:
            count += 1
    return count


def register_batch(
    keys: list[str],
    dry_run: bool = False,
    root: Path | str | None = None,
    now: datetime | None = None,
) -> list[dict]:
    """Register hypotheses for the given keys.

    Parameters
    ----------
    keys : list of str, e.g. ["h1", "h2", "h3"]
    dry_run : bool — if True, print payloads and return but do NOT write to registry.
    root : Path | None — repo root override (passed to metabolism).
    now : datetime | None — override for testing.

    Returns
    -------
    list of registration result dicts (one per hypothesis in keys).

    Raises
    ------
    RuntimeError if the weekly budget is insufficient for the whole batch.
    A partial filing (some H registered, some not) is worse than a delayed
    batch because a silently-dropped hypothesis looks registered to the operator.
    The batch ABORTS entirely if budget < batch_size; no partial writes occur.
    """
    BUDGET_PER_WEEK = 3  # mirrors metabolism.py line 83

    # Budget pre-flight (FIX-7): abort the entire batch rather than silently dropping
    # hypotheses.  Skip in dry-run (no writes happen).  Only PENDING keys (not yet
    # registered) count against the batch size — a fully-registered batch re-run on
    # an exhausted week is a no-op, not an abort (the nightly step re-runs every
    # night; without this filter the log would claim "deferred" for finished work).
    if not dry_run:
        pending = [
            k for k in keys
            if not _already_registered(_ALL_PAYLOADS[k]["hypothesis"], root=root)
        ]
        already_filed = _count_week_registrations(root=root, now=now)
        remaining = BUDGET_PER_WEEK - already_filed
        if remaining < len(pending):
            msg = (
                f"BUDGET PRE-FLIGHT ABORT: {already_filed} hypothesis(es) already registered "
                f"this ISO week; remaining budget={remaining} < pending batch_size={len(pending)}. "
                f"Run in a later ISO week or split the batch. "
                f"No hypotheses were written (partial filing is worse than delayed batch)."
            )
            log.error("register_factor_hypotheses: %s", msg)
            raise RuntimeError(msg)

    results = []
    for key in keys:
        payload = _ALL_PAYLOADS[key]
        hyp_text = payload["hypothesis"]

        if dry_run:
            print(f"\n[DRY-RUN] {key.upper()} payload:")
            # Print a safe copy excluding internal mapping notes from pre_committed_gate
            safe = dict(payload)
            safe["pre_committed_gate"] = {
                k: v for k, v in payload["pre_committed_gate"].items()
                if not k.startswith("_")
            }
            print(json.dumps(safe, indent=2))
            results.append({"key": key, "status": "dry-run", "hypothesis": hyp_text})
            continue

        # Idempotence check
        if _already_registered(hyp_text, root=root):
            log.info("register_factor_hypotheses: %s already registered — skipping", key)
            results.append({
                "key": key,
                "status": "already-registered",
                "hypothesis": hyp_text,
            })
            continue

        # Strip private _* keys from pre_committed_gate before passing to metabolism
        payload_clean = dict(payload)
        payload_clean["pre_committed_gate"] = {
            k: v for k, v in payload["pre_committed_gate"].items()
            if not k.startswith("_")
        }

        try:
            from engine.neuralweb.metabolism import register_hypothesis  # type: ignore[import]
            result = register_hypothesis(payload_clean, root=root, now=now)
            result["key"] = key
            results.append(result)
            log.info(
                "register_factor_hypotheses: %s → status=%s id=%s",
                key, result.get("status"), result.get("id"),
            )
        except Exception as exc:  # noqa: BLE001
            log.error("register_factor_hypotheses: %s failed (%s)", key, exc)
            results.append({
                "key": key,
                "status": "error",
                "reason": str(exc),
                "hypothesis": hyp_text,
            })

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_keys(only: str | None) -> list[str]:
    if not only:
        return list(_ALL_PAYLOADS.keys())
    keys = [k.strip().lower() for k in only.split(",")]
    unknown = [k for k in keys if k not in _ALL_PAYLOADS]
    if unknown:
        raise ValueError(f"Unknown hypothesis keys: {unknown}. Must be from {list(_ALL_PAYLOADS)}")
    return keys


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [register_factor_hypotheses] %(message)s",
    )
    parser = argparse.ArgumentParser(
        description=(
            "Factor Intelligence P2: register H1–H5 in metabolism machine registry. "
            "Run with --only h1,h2,h3 in W27; --only h4,h5 in W28+ (budget: 3/week)."
        )
    )
    parser.add_argument(
        "--only",
        default=None,
        help="Comma-separated subset, e.g. 'h1,h2,h3' or 'h4,h5' (default: all)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print payloads; no writes to registry",
    )
    parser.add_argument(
        "--root",
        default=None,
        help="Repo root override",
    )
    parser.add_argument(
        "--defer-on-budget",
        action="store_true",
        help=(
            "Exit 0 with a 'deferred' notice (instead of crashing) when the "
            "weekly budget pre-flight aborts the batch. For the nightly "
            "cortex-job step, which retries every night until an ISO week "
            "with enough budget."
        ),
    )
    args = parser.parse_args(argv)

    try:
        keys = _parse_keys(args.only)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    root = Path(args.root) if args.root else None
    try:
        results = register_batch(keys, dry_run=args.dry_run, root=root)
    except RuntimeError as exc:
        if args.defer_on_budget and "BUDGET PRE-FLIGHT ABORT" in str(exc):
            print(f"[deferred] {exc}")
            return 0
        raise

    if not args.dry_run:
        print(json.dumps(results, indent=2, default=str))

    n_registered = sum(1 for r in results if r.get("status") == "registered")
    n_skipped = sum(1 for r in results if r.get("status") == "already-registered")
    n_error = sum(1 for r in results if r.get("status") == "error")
    n_budget = sum(1 for r in results if r.get("status") == "budget-rejected")

    print(
        f"\n[summary] registered={n_registered} already-registered={n_skipped} "
        f"budget-rejected={n_budget} error={n_error}",
        file=sys.stderr if (n_error or n_budget) else sys.stdout,
    )

    return 1 if (n_error or n_budget) else 0


if __name__ == "__main__":
    sys.exit(main())
