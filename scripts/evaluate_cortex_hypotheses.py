"""scripts/evaluate_cortex_hypotheses.py — Generic cortex hypothesis evaluator.

Nightly step (cheap, resilient) that runs after the spine-index build.  For each
registered hypothesis whose come_back date <= today it:

1. Enforces the strict post-registration filter at the entry point.
2. Routes to the appropriate claim-shape evaluator.
3. Grades against the PRE-COMMITTED gate ONLY (no post-hoc metric switching).
4. Updates registry status and appends an article3_review governance event.
5. Queues passed hypotheses for the quarterly cortex FDR batch.

ANTI-MINING GUARANTEE
---------------------
STRICT POST-REGISTRATION FILTER — ENTRY POINT:
  Every data row used for grading must satisfy as_of > registered_at (strict).
  This is enforced here, not in the registry or qledger.  A hypothesis that
  passes ONLY on pre-registration data comes back as 'insufficient-n', never
  as 'passed'.  Zero exception mechanism.

PRE-COMMITTED GATE ONLY:
  The gate spec is read from the registration row.  No metric is substituted
  post-hoc; the evaluator reads pre_committed_gate.metric and uses that field
  name exclusively.  This is now true: until W7b-PR3 an unrecognised metric
  fell through to a silent hit_rate substitution, so the paragraph above
  described an enum nothing enforced.  A metric outside _METRIC_SPEC yields
  'uncomputable-metric'; the evaluator never guesses which metric was meant.

DECLARED QUERY ONLY (W2):
  A spine_query's `feature:` condition is APPLIED, and the complement of the
  feature becomes the CONTRAST group.  Before W7b-PR3 filters were built from
  subject/family/engine alone, so a feature: hypothesis contributed no filter
  at all: its "treatment group" was the entire graded spine and no control
  group existed anywhere in the code.  Measured on 2026-08-04, H2
  (high_alibi_flag) and H3 (dna_class_x_style_regime) returned byte-identical
  n=5524 / hits=3188 / metric=0.5771 for two different features.
  A feature that cannot be resolved yields 'unresolvable-query'.  The evaluator
  will not infer a treatment definition the registration only described in
  prose — that is the origination Article 7 forbids.

GATE SEMANTICS (W3):
  A threshold outside its metric's attainable range is STRUCTURALLY unpassable
  and yields 'invalid-gate', not 'failed'.  H2's `hit_rate <= -0.05` and H3's
  `hit_rate >= 1.01` were both minted as contrasts and graded as absolute hit
  rates; both reported 'failed' for two months, reading as evidence against
  their hypotheses when they were evidence against the instrument.
  A merely WEAK threshold is not re-minted here — it is measured against its
  own base rate (gate_informative) and fenced at the promotion gate.

INSTRUMENT VERDICTS:
  'unresolvable-query', 'invalid-gate' and 'uncomputable-metric' all mean the
  instrument could not grade the claim.  They are never evidence the claim is
  false, and they are terminal for the registration AS MINTED: a corrected gate
  or query requires a NEW registration.

OUTCOME BASIS FILTER (PATH A):
  hit_rate / excess_mean are only meaningful against a SIGNED excess return.
  Path A therefore keeps only spine rows with outcome_basis == 'signed_excess'
  (engine.neuralweb.query.OUTCOME_BASIS_FOR_LEDGER); rows from the four
  unsigned-MFE ledgers — track_record, board_hk, board_ca, board_cn — are
  dropped and the count is recorded as result_detail.unsigned_excluded_rows.
  Without it, a hypothesis whose spine_query happens to match track_record
  rows is scored against an ~87% "MFE > 0 at least once" base rate and clears
  any gate for free.  cf. PR #4673 dst_outcome_unsigned_mfe_proxy.

FDR FAMILY:
  All evaluations use family='cortex' so walk_forward and qledger account for
  shared multiple-testing budget.

PROMOTION NOTE:
  A 'passed' status queues the hypothesis for the quarterly cortex FDR batch
  (scripts/quarterly_cortex_fdr.py — built 2026-08-26; before that this
  sentence named a consumer that did not exist and no batch ever ran).  A pass
  alone does NOT promote beyond shadow — it requires the standard gauntlet
  (quarterly BH FDR over the 'cortex' family).  The batch fences on
  evaluator_version, so verdicts minted before W7b-PR3 can never reach it.

CLAIM SHAPES:
  lead_lag + sector_conditional  → PATH A: qledger forward-return
  entry_quality                  → PATH B: walk_forward stop-out
  conditional_regime             → PATH A variant: regime-conditioned qledger

Usage:
    python -m scripts.evaluate_cortex_hypotheses           # production
    python -m scripts.evaluate_cortex_hypotheses --dry-run # no writes
    python -m scripts.evaluate_cortex_hypotheses --root /path/to/repo
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

log = logging.getLogger(__name__)

# W7b-PR3 — the five wiring repairs from the 2026-08-26 experiments audit
# (§3 W1/W2/W3/W5/W6).  The quarterly FDR batch fences on this version:
# verdicts minted by W7b-PR2 or earlier are instrument artifacts.
_EVALUATOR_VERSION = "W7b-PR3"

# ---------------------------------------------------------------------------
# Article 1 — self-grading exclusions
# ---------------------------------------------------------------------------
# The cortex MAY NOT be its own evidence (Article 1: "Never originate").
# adapt_cortex_attention produces synthetic ±0.01 outcome_excess values as
# sign placeholders (see query.py adapt_cortex_attention).  Including those
# rows in a hypothesis evaluation would let the cortex grade itself on its
# own firings — a closed evidence loop that violates the earned-authority
# constitution.
#
# _SELF_LEDGER_EXCLUSIONS is applied at the query layer BEFORE gate scoring.
# A separate defense-in-depth check at REGISTRATION time (_validate_hypothesis
# in metabolism.py) rejects any hypothesis whose spine_query references these
# ledgers/families/engines.
_SELF_LEDGER_EXCLUSIONS: frozenset[str] = frozenset({
    "cortex_attention",              # ledger enum value
    "reflex.cortex_attention",       # engine column value
})


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _root_path(root: str | Path | None = None) -> Path:
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parent.parent


def _data(root: Path, *parts: str) -> Path:
    return root / "data" / Path(*parts)


# ---------------------------------------------------------------------------
# Post-registration filter — ENTRY POINT, no bypass
# ---------------------------------------------------------------------------

def _filter_post_registration(
    rows: list[dict],
    registered_at_str: str,
    asof_field: str = "as_of",
) -> tuple[list[dict], int]:
    """Filter rows to only those where as_of > registered_at (strict).

    Parameters
    ----------
    rows : list[dict]
        Data rows to filter.
    registered_at_str : str
        ISO-8601 UTC datetime of registration.
    asof_field : str
        Name of the as_of field in rows.

    Returns
    -------
    (kept_rows, n_dropped)
    """
    try:
        reg_dt = datetime.fromisoformat(str(registered_at_str))
        if reg_dt.tzinfo is None:
            reg_dt = reg_dt.replace(tzinfo=timezone.utc)
        reg_date = reg_dt.date()
    except Exception as exc:
        log.warning("evaluator: could not parse registered_at %r (%s)", registered_at_str, exc)
        return [], len(rows)

    kept = []
    dropped = 0
    for row in rows:
        asof = row.get(asof_field) or row.get("as_of") or row.get("asof")
        if asof is None:
            dropped += 1
            continue
        try:
            asof_date = date.fromisoformat(str(asof)[:10])
            if asof_date > reg_date:   # STRICT: >
                kept.append(row)
            else:
                dropped += 1
        except Exception:  # noqa: BLE001
            dropped += 1

    if dropped:
        log.info(
            "evaluator: post-registration filter dropped %d rows "
            "(as_of <= %s) — anti-mining law",
            dropped, reg_date,
        )
    return kept, dropped


# ---------------------------------------------------------------------------
# Verdict evaluation
# ---------------------------------------------------------------------------

# METRIC VOCABULARY — the enum the module docstring always claimed the evaluator
# enforced ("the evaluator reads pre_committed_gate.metric and uses that field
# name exclusively").  It did not: an unrecognised metric fell through to a
# silent `hits / n` hit_rate substitution, so a gate declaring
# `median_credit_sensitive_lead_days` was graded as a hit rate and the verdict
# said nothing about the hypothesis.  W3 repair (audit §3).
#
#   space          absolute → graded against the metric's own level
#                  contrast → graded against TREATMENT minus CONTROL
#                  ratio    → graded against TREATMENT / CONTROL
#   lo / hi        attainable range; None = unbounded on that side.  A threshold
#                  outside it is STRUCTURALLY UNREACHABLE — no sample can ever
#                  produce that verdict, so the gate is broken, not the claim.
#   needs_contrast the metric is undefined without a control group.
_METRIC_SPEC: dict[str, dict[str, Any]] = {
    "hit_rate":                 {"space": "absolute", "lo": 0.0,  "hi": 1.0,  "needs_contrast": False},
    "excess_mean":              {"space": "absolute", "lo": None, "hi": None, "needs_contrast": False},
    "hit_rate_difference":      {"space": "contrast", "lo": -1.0, "hi": 1.0,  "needs_contrast": True},
    "excess_mean_difference":   {"space": "contrast", "lo": None, "hi": None, "needs_contrast": True},
    "hit_rate_ratio":           {"space": "ratio",    "lo": 0.0,  "hi": None, "needs_contrast": True},
    "stop_out_rate":            {"space": "absolute", "lo": 0.0,  "hi": 1.0,  "needs_contrast": False},
    "stop_out_rate_difference": {"space": "contrast", "lo": -1.0, "hi": 1.0,  "needs_contrast": True},
}

#: Verdicts that mean "the INSTRUMENT could not grade this", never "the claim is
#: false".  They are terminal for the registration as minted: correcting a gate
#: or a query requires a NEW registration, because rewriting a pre-committed
#: gate here would be the evaluator originating the gate (Article 7).
INSTRUMENT_VERDICTS: frozenset[str] = frozenset({
    "unresolvable-query", "invalid-gate", "uncomputable-metric",
})


def _validate_gate(gate: dict) -> tuple[str | None, dict[str, Any]]:
    """Pre-flight the pre-committed gate.  Returns (instrument_verdict|None, detail).

    A None verdict means the gate is gradeable.  Anything else must be recorded
    INSTEAD of a pass/fail — a structurally unpassable gate that reports 'failed'
    reads as evidence against the hypothesis when it is evidence against the
    instrument.  Both live cases came from thresholds minted in one space and
    graded in another (audit §3 W3):

      H2  hit_rate <= -0.05   a hit rate is never negative → never passable
      H3  hit_rate >=  1.01   a hit rate never exceeds 1   → never passable

    Both were minted as CONTRASTS (a 5pp deficit; a 1.01 ratio) but graded as
    absolute hit rates, and both duly reported 'failed' for two months.
    """
    detail: dict[str, Any] = {}
    metric = str(gate.get("metric", "") or "")
    spec = _METRIC_SPEC.get(metric)

    if spec is None:
        detail["gate_error"] = (
            f"metric {metric!r} is not computable by this evaluator"
        )
        detail["supported_metrics"] = sorted(_METRIC_SPEC)
        detail["remediation"] = (
            "re-register with a supported metric name; the evaluator will not "
            "substitute a different metric for the one that was pre-committed"
        )
        return "uncomputable-metric", detail

    detail["metric_space"] = spec["space"]

    try:
        threshold = float(gate.get("threshold"))
    except (TypeError, ValueError):
        detail["gate_error"] = f"threshold {gate.get('threshold')!r} is not numeric"
        return "invalid-gate", detail

    lo, hi = spec["lo"], spec["hi"]
    if (lo is not None and threshold < lo) or (hi is not None and threshold > hi):
        detail["gate_error"] = (
            f"threshold {threshold} is outside the attainable range of "
            f"{metric} [{lo}, {hi}] in {spec['space']} space — structurally "
            f"unpassable, so no sample can inform this gate"
        )
        detail["attainable_range"] = [lo, hi]
        detail["remediation"] = (
            "the threshold was almost certainly minted as a difference or a "
            "ratio; re-register against a contrast metric "
            f"({', '.join(m for m, s in _METRIC_SPEC.items() if s['needs_contrast'])})"
        )
        return "invalid-gate", detail

    # A gate every possible sample clears is as uninformative as one no sample
    # can clear.  Only the STRUCTURAL case is caught here (threshold at or beyond
    # the far bound); a merely weak threshold is reported as a diagnostic on the
    # result and fenced at the promotion gate, not silently re-minted.
    direction = int(gate.get("direction_expected", 1) or 1)
    trivial = (
        (direction > 0 and lo is not None and threshold <= lo) or
        (direction <= 0 and hi is not None and threshold >= hi)
    )
    if trivial:
        detail["gate_error"] = (
            f"threshold {threshold} is at or beyond the {'lower' if direction > 0 else 'upper'} "
            f"bound of {metric} — every possible sample passes, so the gate "
            f"cannot discriminate"
        )
        return "invalid-gate", detail

    return None, detail


def _evaluate_gate(
    metric_value: float | None,
    n: int,
    gate: dict,
) -> str:
    """Apply the pre-committed gate.  Returns 'passed', 'failed', or 'insufficient-n'.

    Callers MUST run _validate_gate() first — this function assumes the gate is
    structurally gradeable and only compares a value against a threshold.
    """
    min_n = int(gate.get("min_n", 25))
    threshold = float(gate.get("threshold", 0.0))
    # direction_expected: +1 means "higher is better" (hit_rate, win_rate, etc.)
    #                     -1 means "lower is better" (stop_out_rate, etc.)
    # Default +1: when absent, callers must specify -1 explicitly for lower-is-better metrics.
    direction = int(gate.get("direction_expected", 1) or 1)

    if n < min_n:
        return "insufficient-n"

    if metric_value is None:
        return "insufficient-n"

    # Direction -1: metric should be below threshold (e.g. stop_out_rate)
    # Direction +1: metric should be above threshold (e.g. hit_rate)
    if direction <= 0:
        return "passed" if metric_value <= threshold else "failed"
    else:
        return "passed" if metric_value >= threshold else "failed"


# ---------------------------------------------------------------------------
# FEATURE RESOLUTION + CONTRAST GROUP — W2 repair
# ---------------------------------------------------------------------------
# Path A built its filters from subject/family/engine ONLY.  A hypothesis whose
# spine_query is the `feature:` dialect ({"feature": "high_alibi_flag", ...})
# therefore contributed NO filter at all: the query widened to the whole graded
# spine and the "treatment group" was the population.  Measured consequence
# (governance.jsonl, 2026-08-04): H2 (high_alibi_flag) and H3
# (dna_class_x_style_regime) returned byte-identical
# n=5524 / hits=3188 / metric=0.5771 for two entirely different features.
# There was no contrast group anywhere in the code.
#
# The repair is deliberately narrow and REFUSES rather than guesses.  A feature
# resolves only when it is:
#   (a) a column of the frozen factor panel (scripts/build_factor_panel.py
#       PANEL_COLUMNS), joined to spine rows on symbol==ticker AND as_of==date; or
#   (b) an explicit declarative predicate the registration itself supplied in
#       spine_query.feature_expr.
# Anything else — a feature that is a DERIVATION the registration described only
# in prose ("alibi_share_20d rising over prior 10d"), or a cell-wise
# heterogeneity claim — yields verdict 'unresolvable-query' naming the gap.
# Inferring the derivation here would be the evaluator inventing the treatment
# definition, which is exactly the origination Article 7 forbids.

_PANEL_REL = ("data", "factordata", "panel")

#: Comparison operators a declarative feature_expr may use.
_FEATURE_OPS: dict[str, Any] = {
    "is_true":  lambda s, v: s.astype("boolean").fillna(False),
    "is_false": lambda s, v: ~s.astype("boolean").fillna(True),
    "==":       lambda s, v: s == v,
    "!=":       lambda s, v: s != v,
    ">":        lambda s, v: s.astype(float) > float(v),
    ">=":       lambda s, v: s.astype(float) >= float(v),
    "<":        lambda s, v: s.astype(float) < float(v),
    "<=":       lambda s, v: s.astype(float) <= float(v),
    "in":       lambda s, v: s.isin(list(v)),
}


def _load_factor_panel(root: Path, months: set[str]) -> Any:
    """Load the monthly factor-panel partitions covering `months`.  None if absent.

    data/factordata/panel/ is gitignored — it is built earlier in the same
    nightly (config/dag.yml build_factor_panel, well before this step), so it is
    present in production and absent in a fresh checkout.  Absent is not an
    error; it makes every feature: hypothesis 'unresolvable-query' for that run,
    which is the honest reading.
    """
    try:
        import pandas as pd  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return None
    base = root.joinpath(*_PANEL_REL)
    if not base.is_dir():
        return None
    frames = []
    for month in sorted(months):
        p = base / month / "panel.parquet"
        if p.exists():
            try:
                frames.append(pd.read_parquet(p))
            except Exception as exc:  # noqa: BLE001
                log.warning("evaluator: could not read factor panel %s (%s)", p, exc)
    if not frames:
        return None
    panel = pd.concat(frames, ignore_index=True)
    if "ticker" not in panel.columns or "date" not in panel.columns:
        return None
    panel["date"] = panel["date"].astype(str).str[:10]
    panel["ticker"] = panel["ticker"].astype(str)
    return panel


def _resolve_feature_mask(
    sq: dict,
    rows: list[dict],
    root: Path,
) -> tuple[list[bool] | None, dict[str, Any]]:
    """Resolve the declared feature into a per-row treatment mask.

    Returns (mask, detail).  mask is None when the feature cannot be applied —
    the caller MUST then record 'unresolvable-query' rather than grading.
    """
    detail: dict[str, Any] = {}
    feature = sq.get("feature")
    expr = sq.get("feature_expr")
    if not feature and not expr:
        return None, {"feature_error": "no feature or feature_expr declared"}

    detail["feature"] = feature
    column = str((expr or {}).get("column") or feature or "")
    op = str((expr or {}).get("op") or "is_true")
    value = (expr or {}).get("value")

    if op not in _FEATURE_OPS:
        detail["feature_error"] = f"unsupported feature_expr op {op!r}"
        detail["supported_ops"] = sorted(_FEATURE_OPS)
        return None, detail

    months = {str(r.get("as_of", ""))[:7] for r in rows if r.get("as_of")}
    panel = _load_factor_panel(root, {m for m in months if len(m) == 7})
    if panel is None:
        detail["feature_error"] = (
            "factor panel unavailable (data/factordata/panel/ absent or "
            "unreadable) — cannot apply the declared feature condition"
        )
        detail["panel_months_wanted"] = sorted(months)
        return None, detail

    if column not in panel.columns:
        detail["feature_error"] = (
            f"{column!r} is not a factor-panel column, and the registration "
            f"declared no feature_expr resolving it.  Features the registration "
            f"describes only in prose (a derivation over other columns, or a "
            f"cell-wise heterogeneity claim) cannot be applied without the "
            f"evaluator inventing the treatment definition."
        )
        detail["panel_columns_available"] = len(panel.columns)
        detail["remediation"] = (
            "re-register with spine_query.feature_expr = "
            "{column, op, value} over a factor-panel column"
        )
        return None, detail

    # Join the resolved column onto the spine rows by (symbol, as_of).
    try:
        import pandas as pd  # noqa: PLC0415
        keyed = panel.set_index(["ticker", "date"])[column]
        keyed = keyed[~keyed.index.duplicated(keep="last")]
        lookup = keyed.to_dict()
        series = pd.Series(
            [lookup.get((str(r.get("symbol")), str(r.get("as_of", ""))[:10]))
             for r in rows]
        )
        matched = int(series.notna().sum())
        detail["feature_rows_matched"] = matched
        detail["feature_rows_total"] = len(rows)
        if matched == 0:
            detail["feature_error"] = (
                f"the factor panel carries {column!r} but no spine row joined to "
                f"it on (symbol, as_of) — the treatment group would be empty"
            )
            return None, detail
        mask = _FEATURE_OPS[op](series, value)
        mask = [bool(x) if x is not None else False
                for x in mask.fillna(False).tolist()]
    except Exception as exc:  # noqa: BLE001
        detail["feature_error"] = f"feature join failed: {exc}"
        return None, detail

    detail["feature_op"] = op
    detail["feature_column"] = column
    detail["treatment_n"] = int(sum(mask))
    detail["control_n"] = int(len(mask) - sum(mask))
    return mask, detail


# ---------------------------------------------------------------------------
# Metric computation — absolute and CONTRAST
# ---------------------------------------------------------------------------

def _hit_rate(rows: list[dict]) -> float | None:
    if not rows:
        return None
    return sum(1 for r in rows if (r.get("outcome_excess") or 0) > 0) / len(rows)


def _excess_mean(rows: list[dict]) -> float | None:
    if not rows:
        return None
    vals = [float(r.get("outcome_excess") or 0) for r in rows]
    return sum(vals) / len(vals)


def _norm_sf(z: float) -> float:
    """Upper-tail standard-normal survival function (no scipy dependency)."""
    import math  # noqa: PLC0415
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def _two_proportion_p(k1: int, n1: int, k2: int, n2: int) -> float | None:
    """Two-sided pooled two-proportion z-test p-value."""
    import math  # noqa: PLC0415
    if n1 <= 0 or n2 <= 0:
        return None
    p1, p2 = k1 / n1, k2 / n2
    pool = (k1 + k2) / (n1 + n2)
    se = math.sqrt(pool * (1 - pool) * (1 / n1 + 1 / n2))
    if se <= 0:
        return None
    return min(1.0, 2.0 * _norm_sf(abs(p1 - p2) / se))


def _welch_p(a: list[float], b: list[float]) -> float | None:
    """Two-sided Welch t-test p-value, normal-approximated in the tail."""
    import math  # noqa: PLC0415
    if len(a) < 2 or len(b) < 2:
        return None
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    va = sum((x - ma) ** 2 for x in a) / (len(a) - 1)
    vb = sum((x - mb) ** 2 for x in b) / (len(b) - 1)
    se = math.sqrt(va / len(a) + vb / len(b))
    if se <= 0:
        return None
    return min(1.0, 2.0 * _norm_sf(abs(ma - mb) / se))


def _compute_metric(
    metric: str,
    treatment: list[dict],
    control: list[dict] | None,
) -> tuple[float | None, dict[str, Any]]:
    """Compute the PRE-COMMITTED metric.  Never substitutes a different one.

    Returns (value, detail).  A contrast metric with no control group returns
    (None, ...) — the caller records insufficient-n, not a fabricated absolute.
    """
    spec = _METRIC_SPEC[metric]
    detail: dict[str, Any] = {"metric": metric, "metric_space": spec["space"]}
    detail["treatment_n"] = len(treatment)

    if spec["needs_contrast"]:
        if not control:
            detail["contrast_error"] = (
                "metric requires a control group but none resolved"
            )
            return None, detail
        detail["control_n"] = len(control)

    if metric == "hit_rate":
        return _hit_rate(treatment), detail
    if metric == "excess_mean":
        return _excess_mean(treatment), detail

    if metric in ("hit_rate_difference", "hit_rate_ratio"):
        t_rate, c_rate = _hit_rate(treatment), _hit_rate(control or [])
        if t_rate is None or c_rate is None:
            return None, detail
        detail["treatment_hit_rate"] = round(t_rate, 4)
        detail["control_hit_rate"] = round(c_rate, 4)
        detail["p_value"] = _two_proportion_p(
            sum(1 for r in treatment if (r.get("outcome_excess") or 0) > 0), len(treatment),
            sum(1 for r in (control or []) if (r.get("outcome_excess") or 0) > 0), len(control or []),
        )
        if metric == "hit_rate_ratio":
            return (t_rate / c_rate if c_rate else None), detail
        return t_rate - c_rate, detail

    if metric == "excess_mean_difference":
        t_vals = [float(r.get("outcome_excess") or 0) for r in treatment]
        c_vals = [float(r.get("outcome_excess") or 0) for r in (control or [])]
        if not t_vals or not c_vals:
            return None, detail
        detail["treatment_excess_mean"] = round(sum(t_vals) / len(t_vals), 6)
        detail["control_excess_mean"] = round(sum(c_vals) / len(c_vals), 6)
        detail["p_value"] = _welch_p(t_vals, c_vals)
        return (sum(t_vals) / len(t_vals)) - (sum(c_vals) / len(c_vals)), detail

    # Unreachable: _validate_gate rejects anything outside _METRIC_SPEC.
    detail["contrast_error"] = f"no computation registered for {metric!r}"
    return None, detail


def _gate_informativeness(
    gate: dict,
    reference: float | None,
) -> dict[str, Any]:
    """Does clearing this gate say anything beyond the base rate?

    _validate_gate catches gates no sample can pass and gates every sample
    passes.  It deliberately does NOT judge a threshold that is merely weak —
    re-minting a pre-committed threshold would be the evaluator originating the
    gate (Article 7).  So weakness is measured and RECORDED here, and the
    quarterly FDR batch refuses to promote on an uninformative gate.

    Two live examples the audit found (§3 W3): H5's ``hit_rate >= 0.05`` and
    H4's ``stop_out_rate >= 0.05`` are both absolute floors far below their own
    populations' base rates (measured 0.4533 and 0.8246), so "passed" restates
    the base rate rather than testing the claim.

    ``gate_informative`` is None — NOT True — when no reference exists.  The
    batch treats null as ineligible: an unmeasurable gate is never assumed good.
    """
    out: dict[str, Any] = {"gate_reference_value": reference}
    if reference is None:
        out["gate_informative"] = None
        out["gate_informative_note"] = (
            "no control or base-rate reference resolved — informativeness "
            "unmeasurable, so promotion is fenced"
        )
        return out
    try:
        threshold = float(gate.get("threshold"))
    except (TypeError, ValueError):
        out["gate_informative"] = None
        return out
    direction = int(gate.get("direction_expected", 1) or 1)
    informative = (
        threshold > reference if direction > 0 else threshold < reference
    )
    out["gate_informative"] = bool(informative)
    if not informative:
        out["gate_informative_note"] = (
            f"threshold {threshold} is on the permissive side of the reference "
            f"base rate {round(reference, 4)} — clearing it restates the base "
            f"rate rather than testing the claim"
        )
    return out


def _episode_n(rows: list[dict]) -> int:
    """Distinct as_of dates — the honest independent-episode count.

    Row count is not sample size when horizons overlap: 5,524 rows drawn from a
    handful of dates is a handful of episodes.  Recorded on every result so the
    FDR batch can fence on episodes rather than rows.
    """
    return len({str(r.get("as_of", ""))[:10] for r in rows if r.get("as_of")})


# ---------------------------------------------------------------------------
# PATH A: lead_lag / sector_conditional / conditional_regime
# ---------------------------------------------------------------------------

def _evaluate_path_a(
    hyp: dict,
    root: Path,
    dry_run: bool,
) -> dict[str, Any]:
    """Forward-return path via spine/qledger."""
    gate = hyp.get("pre_committed_gate") or {}
    sq = hyp.get("spine_query") or {}
    registered_at = hyp["registered_at"]

    metric_value = None
    n = 0
    verdict = "insufficient-n"
    result_detail: dict[str, Any] = {}

    # W3 — pre-flight the gate BEFORE touching data.  A structurally unpassable
    # gate must never reach _evaluate_gate, where it would report 'failed' and
    # read as evidence against the hypothesis.
    gate_verdict, gate_detail = _validate_gate(gate)
    result_detail.update(gate_detail)
    if gate_verdict is not None:
        return {"verdict": gate_verdict, "n": 0, "metric_value": None,
                "detail": result_detail}

    try:
        from engine.neuralweb.query import load_index, query  # type: ignore[import]
        df = load_index(root)

        if df is None or df.empty:
            result_detail["note"] = "spine index empty or unavailable"
            return {"verdict": verdict, "n": n, "metric_value": metric_value,
                    "detail": result_detail}

        # Build query filters from spine_query
        filter_kw: dict[str, Any] = {}
        if sq.get("subject"):
            filter_kw["symbol"] = sq["subject"]
        if sq.get("family"):
            filter_kw["family"] = sq["family"]
        if sq.get("engine"):
            filter_kw["engine"] = sq["engine"]
        horizon_d = int(hyp.get("horizon_d") or gate.get("horizon_d") or 21)
        filter_kw["graded_only"] = True

        # W2 — a `feature:` dialect query contributes NO axis above.  Record that
        # the population is unnarrowed so an unfiltered run can never again be
        # mistaken for a filtered one.
        declares_feature = bool(sq.get("feature") or sq.get("feature_expr"))
        result_detail["query_axes_applied"] = sorted(
            k for k in filter_kw if k != "graded_only"
        )
        result_detail["declares_feature"] = declares_feature

        filtered = query(df, **filter_kw)

        # Article 1 — self-grading exclusion.
        # Remove any rows from the cortex_attention ledger or reflex.cortex_attention
        # engine BEFORE scoring.  These rows carry synthetic ±0.01 outcome_excess
        # sign placeholders and must never feed hypothesis verdicts.
        if not filtered.empty:
            self_mask = (
                filtered["ledger"].astype(str).isin(_SELF_LEDGER_EXCLUSIONS) |
                filtered["engine"].astype(str).isin(_SELF_LEDGER_EXCLUSIONS) |
                filtered["family"].astype(str).str.startswith("reflex.cortex_attention")
            )
            n_self_excluded = int(self_mask.sum())
            if n_self_excluded:
                log.info(
                    "evaluator: Article 1 — excluded %d self-referencing rows "
                    "(cortex_attention) from hypothesis %s",
                    n_self_excluded, hyp.get("id"),
                )
                filtered = filtered[~self_mask].reset_index(drop=True)
                result_detail["self_excluded_rows"] = n_self_excluded

        # OUTCOME BASIS — keep only rows whose outcome_excess is a genuinely
        # SIGNED excess return.  Four ledgers (track_record, board_hk,
        # board_ca, board_cn) fill it from a non-negative forward-MFE proxy
        # with direction pinned to +1, so the hit_rate computed below would be
        # scored against an ~87% base rate that has nothing to do with the
        # hypothesis: any gate would pass trivially.
        #
        # NOT a zero-negatives probe.  #4673's empirical probe operates on a
        # LEDGER POPULATION, where an all-wins outcome column is evidence the
        # column is unsigned.  Here the unit is a hypothesis SAMPLE, and an
        # all-wins signed sample is exactly what a good hypothesis looks like —
        # probing for it would refute the very thing being tested.  The
        # structural label is the only correct instrument at this altitude.
        # cf. PR #4673 edge_outcomes.py dst_outcome_unsigned_mfe_proxy.
        if not filtered.empty:
            try:
                from engine.neuralweb.query import (  # noqa: PLC0415
                    OUTCOME_BASIS_SIGNED,
                    stamp_outcome_basis,
                )
                # Backfill for a legacy parquet written before the column.
                filtered = stamp_outcome_basis(filtered)
                signed_mask = (
                    filtered["outcome_basis"].astype("object").map(
                        lambda v: v is not None and str(v) == OUTCOME_BASIS_SIGNED
                    ).astype(bool)
                )
                n_unsigned = int((~signed_mask).sum())
                if n_unsigned:
                    log.info(
                        "evaluator: outcome basis — excluded %d rows whose "
                        "outcome_excess is not a signed excess (unsigned mfe "
                        "proxy / unlabelled) from hypothesis %s",
                        n_unsigned, hyp.get("id"),
                    )
                    filtered = filtered[signed_mask].reset_index(drop=True)
                    result_detail["unsigned_excluded_rows"] = n_unsigned
            except Exception as exc:  # noqa: BLE001
                # Degrade-never-raise, but record it: a silent pass-through
                # would score the hypothesis on unsigned rows.
                log.warning(
                    "evaluator: outcome_basis filter failed for %s (%s)",
                    hyp.get("id"), exc,
                )
                result_detail["unsigned_filter_error"] = str(exc)

        # Strict post-registration filter
        rows_dicts = filtered.to_dict(orient="records") if not filtered.empty else []
        kept, dropped = _filter_post_registration(rows_dicts, registered_at, "as_of")

        result_detail["total_spine_rows"] = len(rows_dicts)
        result_detail["pre_reg_dropped"] = dropped
        result_detail["post_reg_n"] = len(kept)

        n = len(kept)

        if n == 0:
            result_detail["note"] = (
                "No post-registration graded rows found. "
                "All data predates registration — anti-mining law enforced."
            )
            verdict = "insufficient-n"
        else:
            metric_name = str(gate.get("metric"))
            treatment: list[dict] = kept
            control: list[dict] | None = None

            # W2 — apply the declared feature condition and build the CONTRAST
            # group.  Refuse to grade when it cannot be applied.
            if declares_feature:
                mask, feat_detail = _resolve_feature_mask(sq, kept, root)
                result_detail.update(feat_detail)
                if mask is None:
                    result_detail["note"] = (
                        "declared feature condition could not be applied; "
                        "grading the unfiltered population would score a "
                        "different hypothesis than the one registered"
                    )
                    return {"verdict": "unresolvable-query", "n": n,
                            "metric_value": None, "detail": result_detail}
                treatment = [r for r, m in zip(kept, mask) if m]
                control = [r for r, m in zip(kept, mask) if not m]
                n = len(treatment)
                result_detail["post_reg_n"] = n

            metric_value, metric_detail = _compute_metric(
                metric_name, treatment, control
            )
            result_detail.update(metric_detail)
            # An absolute gate is informative only against a base rate; a
            # contrast gate is already stated relative to its control, so 0 is
            # its natural reference.
            if _METRIC_SPEC[metric_name]["needs_contrast"]:
                reference: float | None = 0.0
            elif metric_name == "hit_rate":
                reference = _hit_rate(control) if control else None
            elif metric_name == "excess_mean":
                reference = _excess_mean(control) if control else None
            else:
                reference = None
            result_detail.update(_gate_informativeness(gate, reference))
            result_detail["episode_n"] = _episode_n(treatment)
            result_detail["control_episode_n"] = _episode_n(control or [])
            result_detail["hits"] = sum(
                1 for r in treatment if (r.get("outcome_excess") or 0) > 0
            )
            # Horizons overlap, so rows are not independent draws.  Recorded so
            # the FDR batch can fence on episodes; never silently ignored.
            result_detail["overlapping_horizons"] = True

            # A contrast metric needs BOTH arms to clear min_n — a 5-row control
            # arm makes the difference an artifact of the control, not the claim.
            min_n = int(gate.get("min_n", 25))
            if _METRIC_SPEC[metric_name]["needs_contrast"] and len(control or []) < min_n:
                result_detail["note"] = (
                    f"control arm has {len(control or [])} rows < min_n {min_n}"
                )
                verdict = "insufficient-n"
            else:
                verdict = _evaluate_gate(metric_value, n, gate)
            if metric_value is not None:
                result_detail["metric_value"] = round(float(metric_value), 6)

    except Exception as exc:  # noqa: BLE001
        log.warning("evaluator: path-A failed for %s (%s)", hyp.get("id"), exc)
        result_detail["error"] = str(exc)
        verdict = "insufficient-n"

    return {
        "verdict": verdict,
        "n": n,
        "metric_value": metric_value,
        "detail": result_detail,
    }


# ---------------------------------------------------------------------------
# PATH B: entry_quality
# ---------------------------------------------------------------------------

def _evaluate_path_b(
    hyp: dict,
    root: Path,
    dry_run: bool,
) -> dict[str, Any]:
    """Stop-out path via walk_forward harness."""
    gate = hyp.get("pre_committed_gate") or {}
    sq = hyp.get("spine_query") or {}
    registered_at = hyp["registered_at"]

    metric_value = None
    n = 0
    verdict = "insufficient-n"
    result_detail: dict[str, Any] = {}

    # W3 — pre-flight the gate before touching data.
    gate_verdict, gate_detail = _validate_gate(gate)
    result_detail.update(gate_detail)
    if gate_verdict is not None:
        return {"verdict": gate_verdict, "n": 0, "metric_value": None,
                "detail": result_detail}

    try:
        from engine.neuralweb.query import load_index, query  # type: ignore[import]
        df = load_index(root)

        if df is None or df.empty:
            result_detail["note"] = "spine index empty"
            return {"verdict": verdict, "n": n, "metric_value": metric_value,
                    "detail": result_detail}

        # Get signal rows for entry_quality
        filter_kw: dict[str, Any] = {"graded_only": False}
        if sq.get("subject"):
            filter_kw["symbol"] = sq["subject"]
        if sq.get("engine"):
            filter_kw["engine"] = sq["engine"]

        filtered = query(df, **filter_kw)
        rows_dicts = filtered.to_dict(orient="records") if not filtered.empty else []

        # Strict post-registration filter
        kept, dropped = _filter_post_registration(rows_dicts, registered_at, "as_of")
        result_detail["total_spine_rows"] = len(rows_dicts)
        result_detail["pre_reg_dropped"] = dropped
        result_detail["post_reg_n"] = len(kept)

        n = len(kept)

        if n < int(gate.get("min_n", 25)):
            result_detail["note"] = (
                f"insufficient post-registration signals ({n} < {gate.get('min_n', 25)})"
            )
            verdict = "insufficient-n"
        else:
            # Signals are (symbol, as_of) events.  Rank symbols by signal count
            # so the cap keeps the most-informative names, and keep the order
            # DETERMINISTIC — the previous `list({...})[:20]` took 20 symbols in
            # arbitrary set order, so the same registry could grade differently
            # on two runs.
            import pandas as pd  # noqa: PLC0415

            # W2 applies to Path B too — it read only subject/engine, so a
            # `feature:` entry_quality hypothesis graded EVERY signal as its
            # treatment group, exactly like Path A.  Treatment = feature-true
            # signals; control = feature-false, run as walk_forward's baseline
            # arm so the contrast is measured inside one harness run.
            control_rows: list[dict] = []
            if sq.get("feature") or sq.get("feature_expr"):
                mask, feat_detail = _resolve_feature_mask(sq, kept, root)
                result_detail.update(feat_detail)
                if mask is None:
                    result_detail["note"] = (
                        "declared feature condition could not be applied; "
                        "grading all signals would score a different hypothesis "
                        "than the one registered"
                    )
                    return {"verdict": "unresolvable-query", "n": n,
                            "metric_value": None, "detail": result_detail}
                control_rows = [r for r, m in zip(kept, mask) if not m]
                kept = [r for r, m in zip(kept, mask) if m]
                n = len(kept)
                result_detail["post_reg_n"] = n

            by_symbol: dict[str, list[str]] = {}
            for r in kept:
                sym = str(r.get("symbol") or "")
                asof_str = str(r.get("as_of", ""))[:10]
                if sym and asof_str:
                    by_symbol.setdefault(sym, []).append(asof_str)
            control_by_symbol: dict[str, list[str]] = {}
            for r in control_rows:
                sym = str(r.get("symbol") or "")
                asof_str = str(r.get("as_of", ""))[:10]
                if sym and asof_str:
                    control_by_symbol.setdefault(sym, []).append(asof_str)
            ranked = sorted(by_symbol, key=lambda s: (-len(by_symbol[s]), s))
            symbols = ranked[:_PATH_B_MAX_SYMBOLS]
            result_detail["symbols_with_signals"] = len(ranked)
            result_detail["symbols_capped_out"] = max(0, len(ranked) - len(symbols))

            panel, panel_detail = _load_price_panel(root, symbols)
            result_detail.update(panel_detail)

            if not panel:
                result_detail["note"] = (
                    "no price panel available for walk_forward — see "
                    "panel_missing / panel_thin counts"
                )
                verdict = "insufficient-n"
            else:
                # W5 — the signal callable.  Two defects made Path B dead:
                #
                #  1. ARITY.  walk_forward calls `signal_fn(daily, high, low)`
                #     positionally (module header: `fn(close, high=None,
                #     low=None)`).  The old closure was `signal_fn(close,
                #     **_kwargs)`, so every call raised TypeError — swallowed by
                #     walk_forward's per-ticker `except Exception` into
                #     `dropped`, leaving n_names=0 with NO error surfaced.  That
                #     is the measured H1/H4 failure (wf_n_names=0 on n=25,824
                #     and n=33,930), and it was never the price-panel join: the
                #     panel loaded fine.
                #
                #  2. TICKER IDENTITY.  It resolved the ticker as `close.name`,
                #     but walk_forward passes `df["close"]`, whose name is the
                #     literal string "close" — so even with the arity fixed,
                #     every lookup missed and no signal ever fired.  The panel
                #     frames carry the ticker on the INDEX name instead, which
                #     survives the column selection and the dropna.
                #
                # Signal dates are also snapped FORWARD to the next trading day
                # rather than requiring an exact index hit, so an as_of landing
                # on a holiday binds instead of vanishing.
                bound = {"fired": 0, "unbound": 0}

                def _make_signal_fn(sigs: dict[str, list[str]], count: bool):
                    def signal_fn(close, high=None, low=None):
                        out = pd.Series(False, index=close.index)
                        sym = str(getattr(close.index, "name", "") or "")
                        for d in sigs.get(sym, []):
                            try:
                                t = pd.Timestamp(d)
                            except Exception:  # noqa: BLE001
                                if count:
                                    bound["unbound"] += 1
                                continue
                            pos = out.index.searchsorted(t, side="left")
                            if pos < len(out.index):
                                out.iloc[pos] = True
                                if count:
                                    bound["fired"] += 1
                            elif count:
                                bound["unbound"] += 1
                        return out
                    return signal_fn

                metric_name = str(gate.get("metric"))
                wants_contrast = _METRIC_SPEC[metric_name]["needs_contrast"]
                baseline_fn = (
                    _make_signal_fn(control_by_symbol, False)
                    if control_by_symbol else None
                )
                if wants_contrast and baseline_fn is None:
                    result_detail["note"] = (
                        f"{metric_name} needs a control arm but the query "
                        f"resolved none"
                    )
                    return {"verdict": "insufficient-n", "n": n,
                            "metric_value": None, "detail": result_detail}

                try:
                    from research.signal_engine.walk_forward import walk_forward  # type: ignore[import]
                    wf_result = walk_forward(
                        _make_signal_fn(by_symbol, True),
                        panel,
                        baseline_fn=baseline_fn,
                        family="cortex",
                        metric="stop_out_rate",
                        n_trials=None,
                        run_id=f"cortex-eval-{hyp['id'][:12]}",
                        log=False,
                    )
                    by_ticker = wf_result.get("by_ticker") or {}
                    n_names = int(wf_result.get("n_names", 0) or 0)
                    treat_rate, treat_trades = _pooled_stop_out_rate(by_ticker, "treat")
                    base_rate, base_trades = _pooled_stop_out_rate(by_ticker, "base")

                    if wants_contrast:
                        metric_value = (
                            treat_rate - base_rate
                            if treat_rate is not None and base_rate is not None
                            else None
                        )
                    else:
                        metric_value = treat_rate

                    result_detail.update({
                        "metric": metric_name,
                        "wf_n_names": n_names,
                        "wf_signals_bound": bound["fired"],
                        "wf_signals_unbound": bound["unbound"],
                        "wf_n_trades": treat_trades,
                        "wf_control_n_trades": base_trades,
                        "treatment_stop_out_rate": treat_rate,
                        "control_stop_out_rate": base_rate,
                        "stop_out_rate_units": "fraction (harness reports percent; /100 here)",
                        "episode_n": _episode_n(kept),
                        "overlapping_horizons": True,
                    })
                    result_detail.update(_gate_informativeness(
                        gate, 0.0 if wants_contrast else base_rate,
                    ))
                    # Never report a stop-out rate computed over zero names as a
                    # verdict — that is the silent failure this repair exists to
                    # end.  Name the reason instead.
                    if n_names == 0:
                        dropped = wf_result.get("dropped") or {}
                        result_detail["wf_dropped_sample"] = dict(
                            list(dropped.items())[:5]
                        )
                        result_detail["note"] = (
                            "walk_forward admitted 0 names — every panel name "
                            "was dropped; see wf_dropped_sample"
                        )
                        verdict = "insufficient-n"
                    elif metric_value is None:
                        result_detail["note"] = (
                            f"walk_forward ran on {n_names} names but produced no "
                            f"stop_out_rate (likely zero trades taken)"
                        )
                        verdict = "insufficient-n"
                    else:
                        metric_value = float(metric_value)
                        result_detail["metric_value"] = round(metric_value, 6)
                        verdict = _evaluate_gate(metric_value, n, gate)
                except Exception as exc:  # noqa: BLE001
                    log.warning("evaluator: walk_forward failed (%s)", exc)
                    result_detail["wf_error"] = str(exc)
                    verdict = "insufficient-n"

    except Exception as exc:  # noqa: BLE001
        log.warning("evaluator: path-B failed for %s (%s)", hyp.get("id"), exc)
        result_detail["error"] = str(exc)
        verdict = "insufficient-n"

    return {
        "verdict": verdict,
        "n": n,
        "metric_value": metric_value,
        "detail": result_detail,
    }


def _pooled_stop_out_rate(by_ticker: dict, arm: str = "treat", view: str = "full") -> tuple[float | None, int]:
    """Trade-weighted pooled stop-out rate as a FRACTION, plus the trade count.

    Two corrections over the code this replaces, which read
    ``wf_result["pooled"]["stop_out_rate"]``:

    * That key exists at no nesting level.  ``pooled[view]`` is a percentile
      distribution ({view, metric, n_names, treat:{p10..p90, mean}, ...}), so the
      read returned None even when the harness had run — a second, independent
      reason Path B could never produce a verdict.
    * The harness reports stop_out_rate in PERCENT (measured: 46.67 for AAPL),
      while every registered gate is minted in fraction space (threshold 0.05
      meaning 5%).  Grading percent against a fraction threshold is the same
      class of units error as W3's absolute-vs-contrast mismatch, so the value
      is converted here and the conversion is recorded on the result.

    Trade-weighted rather than name-averaged: a name with 2 trades should not
    move the pooled rate as much as one with 200.
    """
    num = 0.0
    den = 0
    for d in by_ticker.values():
        side = d.get(arm)
        if not side:
            continue
        stats = side.get(view) or {}
        rate, trades = stats.get("stop_out_rate"), stats.get("n_trades")
        if rate is None or not trades:
            continue
        num += float(rate) * int(trades)
        den += int(trades)
    if den <= 0:
        return None, 0
    return (num / den) / 100.0, den


#: Cap on names admitted to a single Path B run.  Bounded for runtime; the
#: number dropped is always reported (symbols_capped_out), never silent.
_PATH_B_MAX_SYMBOLS = 60

#: walk_forward skips any name with fewer than this many daily bars.
_MIN_PANEL_BARS = 400


def _load_price_panel(root: Path, symbols: list[str]) -> tuple[dict, dict[str, Any]]:
    """Load a price panel for walk_forward.  Returns (panel, diagnostics).

    The frames carry the ticker on ``index.name``: walk_forward hands the signal
    callable ``df["close"]``, whose ``.name`` is the column label "close" and so
    cannot identify the name.  ``index.name`` survives both the column selection
    and the dropna, which is what lets a per-ticker signal bind at all (W5).

    Every rejection is counted.  The previous version returned a bare dict, so a
    panel that came back empty — or, worse, full but unusable — was
    indistinguishable from one that simply had no data.
    """
    panel: dict[str, Any] = {}
    diag: dict[str, Any] = {
        "panel_requested": len(symbols),
        "panel_missing": 0,      # no data/yahoo/<sym>.parquet
        "panel_no_close": 0,     # parquet present but no close column
        "panel_thin": 0,         # fewer than _MIN_PANEL_BARS bars
        "panel_unreadable": 0,
    }
    try:
        import pandas as pd  # noqa: PLC0415
        yahoo_dir = root / "data" / "yahoo"
        for sym in symbols:
            p = yahoo_dir / f"{sym}.parquet"
            if not p.exists():
                diag["panel_missing"] += 1
                continue
            try:
                df = pd.read_parquet(p)
            except Exception:  # noqa: BLE001
                diag["panel_unreadable"] += 1
                continue
            if "close" not in df.columns:
                diag["panel_no_close"] += 1
                continue
            if len(df["close"].dropna()) < _MIN_PANEL_BARS:
                diag["panel_thin"] += 1
                continue
            df = df.copy()
            df.index.name = sym          # the ticker channel — see docstring
            panel[sym] = df
    except Exception as exc:  # noqa: BLE001
        log.debug("evaluator: price panel load error (%s)", exc)
        diag["panel_error"] = str(exc)
    diag["panel_admitted"] = len(panel)
    return panel, diag


# ---------------------------------------------------------------------------
# Governance event for evaluation result
# ---------------------------------------------------------------------------

def _emit_evaluation_governance(
    hyp_id: str,
    verdict: str,
    n: int,
    gate: dict,
    result_detail: dict,
    root: Path,
    dry_run: bool,
) -> None:
    if dry_run:
        return
    try:
        from engine.neuralweb.governance import append_event  # type: ignore[import]
        append_event(
            "article3_review",
            target=f"cortex_hypothesis:{hyp_id}",
            article=3,
            authored_by="evaluate_cortex_hypotheses",
            evidence={
                "verdict": verdict,
                "n": n,
                "gate": gate,
                "detail": result_detail,
            },
            note=(
                f"verdict={verdict} n={n} — "
                f"{'promotion queued for quarterly FDR batch' if verdict == 'passed' else 'see detail'}. "
                f"Promotion beyond shadow ALSO needs the standard gauntlet."
            ),
            root=str(root),
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("evaluator: governance event failed for %s (%s)", hyp_id, exc)


# ---------------------------------------------------------------------------
# Main evaluation loop
# ---------------------------------------------------------------------------

def evaluate_due(
    root: Path | str | None = None,
    dry_run: bool = False,
    today: date | None = None,
) -> dict[str, Any]:
    """Evaluate all due hypotheses.  Returns a summary dict."""
    root = _root_path(root) if not isinstance(root, Path) else root
    if today is None:
        today = datetime.now(timezone.utc).date()

    from engine.neuralweb.metabolism import load_due  # type: ignore[import]
    due = load_due(root=str(root), today=today)

    summary = {
        "as_of": today.isoformat(),
        "evaluator_version": _EVALUATOR_VERSION,
        "dry_run": dry_run,
        "n_due": len(due),
        "results": [],
    }

    if not due:
        log.info("evaluator: no due hypotheses today (%s)", today)
        return summary

    from engine.neuralweb.metabolism import record_evaluation  # type: ignore[import]

    for hyp in due:
        hyp_id = hyp.get("id", "unknown")
        claim_shape = hyp.get("claim_shape", "")
        gate = hyp.get("pre_committed_gate") or {}
        registered_at = hyp.get("registered_at", "")

        log.info("evaluator: processing %s (shape=%s)", hyp_id, claim_shape)

        if not registered_at:
            log.warning("evaluator: %s has no registered_at — skipping", hyp_id)
            continue

        # Article 1 — defense in depth: reject any pre-existing registry row
        # whose spine_query references cortex_attention even if it bypassed
        # _validate_hypothesis at registration time (e.g. hand-written rows,
        # old rows before the guard was added).
        sq_check = hyp.get("spine_query") or {}
        _self_ref_values = {
            sq_check.get("family", ""),
            sq_check.get("engine", ""),
            sq_check.get("ledger", ""),
        }
        _self_forbidden = {"cortex_attention", "reflex.cortex_attention"}
        _self_family_prefix = str(sq_check.get("family", "")).startswith("reflex.cortex_attention")
        if _self_ref_values & _self_forbidden or _self_family_prefix:
            log.warning(
                "evaluator: Article 1 — hypothesis %s references cortex_attention "
                "in spine_query; verdict=invalid-self-reference (never graded)",
                hyp_id,
            )
            if not dry_run:
                record_evaluation(hyp_id, "invalid-self-reference", str(root), n=0)
                _emit_evaluation_governance(
                    hyp_id, "invalid-self-reference", 0, gate,
                    {"reason": "Article 1: spine_query references cortex_attention — self-grading forbidden"},
                    root, dry_run,
                )
            summary["results"].append({
                "id": hyp_id,
                "claim_shape": claim_shape,
                "verdict": "invalid-self-reference",
                "n": 0,
                "metric_value": None,
                "detail": {"reason": "Article 1: spine_query references cortex_attention — self-grading forbidden"},
                "gate": gate,
                "note": None,
            })
            continue

        # Route to evaluator path
        if claim_shape in ("lead_lag", "sector_conditional", "conditional_regime"):
            result = _evaluate_path_a(hyp, root, dry_run)
        elif claim_shape == "entry_quality":
            result = _evaluate_path_b(hyp, root, dry_run)
        else:
            log.warning("evaluator: unknown claim_shape %r for %s", claim_shape, hyp_id)
            result = {"verdict": "insufficient-n", "n": 0, "metric_value": None,
                      "detail": {"error": f"unknown claim_shape {claim_shape!r}"}}

        verdict = result["verdict"]
        n = result.get("n", 0)
        metric_value = result.get("metric_value")
        detail = result.get("detail", {})
        # Stamp the instrument that produced this verdict.  The quarterly FDR
        # batch fences on it: verdicts minted before the W7b-PR3 repairs are
        # instrument artifacts and may never reach a promotion decision.
        detail["evaluator_version"] = _EVALUATOR_VERSION

        # Write verdict and governance event.  W6: record_evaluation appends a
        # superseding row carrying evaluated_at / metric_value / n / attempts —
        # _update_row_status wrote status and nothing else, so a verdict left no
        # trace of what it was computed from.
        if not dry_run:
            record_evaluation(
                hyp_id, verdict, str(root),
                metric_value=metric_value, n=n, detail=detail,
            )
            _emit_evaluation_governance(hyp_id, verdict, n, gate, detail, root, dry_run)

        eval_result = {
            "id": hyp_id,
            "claim_shape": claim_shape,
            "verdict": verdict,
            "n": n,
            "metric_value": metric_value,
            "detail": detail,
            "gate": gate,
            "note": (
                "passed hypotheses are queued for quarterly cortex FDR batch; "
                "promotion beyond shadow also needs the standard gauntlet"
            ) if verdict == "passed" else None,
        }
        summary["results"].append(eval_result)
        log.info("evaluator: %s → %s (n=%d)", hyp_id, verdict, n)

    summary["n_passed"] = sum(1 for r in summary["results"] if r["verdict"] == "passed")
    summary["n_failed"] = sum(1 for r in summary["results"] if r["verdict"] == "failed")
    summary["n_insufficient"] = sum(
        1 for r in summary["results"] if r["verdict"] == "insufficient-n"
    )

    # Write summary artifact
    if not dry_run:
        out_path = _data(root, "neuralweb", "cortex", "evaluator_run.json")
        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(
                json.dumps(summary, indent=2, default=str), encoding="utf-8"
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("evaluator: could not write run summary (%s)", exc)

    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [evaluate_cortex] %(message)s",
    )
    parser = argparse.ArgumentParser(
        description="Cortex hypothesis evaluator (W7b PR2)"
    )
    parser.add_argument("--root", default=None, help="Repo root override")
    parser.add_argument("--dry-run", action="store_true", help="Compute only; no writes")
    args = parser.parse_args(argv)

    try:
        summary = evaluate_due(root=args.root, dry_run=args.dry_run)
        print(json.dumps(summary, indent=2, default=str))
        return 0
    except Exception as exc:  # noqa: BLE001
        log.error("evaluator: fatal error (%s)", exc, exc_info=True)
        # Degrade-never-raise
        return 0


if __name__ == "__main__":
    sys.exit(main())
