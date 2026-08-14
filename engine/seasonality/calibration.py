"""Forward-chained calibration and honest evaluation for market-response forecasts.

THE ONE PROPERTY THIS MODULE EXISTS FOR
=======================================
**The calibrator sees only predictions issued strictly before the fold it
scores.**  Never the fold it evaluates, and never anything that resolved after
that fold opened.

This is made STRUCTURAL rather than asserted.  There is exactly one function that
builds a training set — :func:`_training_set` — and its whole signature is
``(records, cutoff)``: it is never handed the fold, so it cannot include it.  The
cutoff for fold *k* is derived from the EARLIEST ``issued_at`` in that fold minus
the embargo, and training rows must have ``resolved_at <= cutoff``.  Because a
record's outcome never resolves before it is issued, a scored row's
``resolved_at`` is at or after its own ``issued_at``, which is at or after the
fold's earliest ``issued_at``, which is strictly after the cutoff — so a scored
row cannot enter its own training set by construction.  On top of that,
:func:`_assert_no_leak` fails CLOSED on key overlap, and every fold receipt
publishes ``fit_max_resolved_at`` and ``score_min_issued_at`` so a reader can
check the ordering without trusting this docstring.

Why the paranoia: a calibrator fit on the whole stream learns the miscalibration
that a regime break created and then "corrects" it retroactively.  The resulting
reliability diagram is beautiful, the Brier score improves, and none of it was
available at decision time.  ``tests/test_seasonality_calibration.py`` runs that
exact simulation — a synthetic stream with a planted regime break, scored by both
the forward-chained calibrator and a deliberately leaking one — and prints the
gap.

WHAT IS REUSED, NOT REBUILT
---------------------------
``platt_fit``, ``isotonic_calibration``, ``apply_calibration``,
``brier_reliability``, ``expected_calibration_error``, ``purged_folds``, and
``crps_score`` all come from :mod:`engine.validation`.  This module supplies the
chronology, the clustering, and the abstentions — not another copy of a Brier
score that can drift from the house one.

``purged_folds`` is fed a POSITIONAL index on purpose: it slices by position, and
biotech predictions share issue dates constantly, so a value-keyed slice would be
ambiguous exactly where the folds matter most.

EXPLICIT NULLS ARE PRINTED, NOT HIDDEN
--------------------------------------
Every metric slot is present in every result.  A metric that cannot be estimated
returns ``{"abstained": True, "reason": "<named>"}`` — never a default, never a
0.5, never a silently missing key.  ``engine.validation`` returns ``{}`` on thin
N; this module converts that empty dict into a NAMED abstention so a reader sees
which floor was hit.

THE LABEL MUST MATCH THE EVIDENCE
--------------------------------
Three rules keep a number from being read as better evidence than it is:

* **Scores are never relabelled.**  ``_score_values`` REFUSES a stream whose rows
  do not carry ``score_key`` instead of falling back to the raw ``p`` while the
  payload still reports ``score_key="p_cal"``.  Scoring raw scores is fine; it
  has to be SAID (``score_key="p"``).
* **One cluster rule, disclosed everywhere.**  ``_clusters`` is the only
  derivation, and the rule that produced the labels is stamped on every interval
  as ``cluster_basis`` — including the partial case ("380/640 rows carried
  date_cluster").  A per-record CI is narrower than the data earns and used to
  carry the same ``basis`` string as a genuinely clustered one.
* **A verdict needs an interval.**  ``drift_report`` calls a break on a
  bootstrap of the DIFFERENCE (not on whether two separate 90% intervals happen
  to overlap, which is roughly half as powerful), and
  ``calibration_slope_intercept`` may only leave "calibrated" when the slope's
  own CI clears the 0.9-1.1 identity band.  The point reading is still reported
  beside it.

OVERLAPPING HORIZONS
--------------------
Biotech catalysts arrive in waves.  Two predictions issued in the same week over
the same horizon are one macro draw, so every uncertainty here resamples DATE
CLUSTERS, not rows (:func:`cluster_bootstrap_ci`).  When no cluster key is
supplied the fallback is one-cluster-per-record and the payload says so — that
fallback provides NO overlap protection and hiding it would make the CI look
earned.

APPEND-ONLY LEDGERS
-------------------
:func:`append_forecast_row` and :func:`append_outcome_row` are pure append.  They
never rewrite, reorder, or re-date: the file is opened in ``"a"`` mode and
nothing else.  Replaying identical inputs appends NOTHING (idempotent by content
hash), and the same key arriving with DIFFERENT content raises
:class:`LedgerAppendError` rather than silently re-dating history.  The nightly is
the sole advancer of forward ledgers — this module provides the functions and
writes nothing on import or on any production path.

Shadow status is binding: every payload carries ``tier="shadow"``.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from engine.validation import (
    apply_calibration,
    brier_reliability,
    crps_score,
    expected_calibration_error,
    isotonic_calibration,
    platt_fit,
    purged_folds,
)

# --- identity ---------------------------------------------------------------

CALIBRATION_SCHEMA = "biopharma.seasonality.calibration.v1"
EVALUATION_SCHEMA = "biopharma.seasonality.calibration_evaluation.v1"
ABSTENTION_SCHEMA = "biopharma.seasonality.calibration.abstention.v1"
FORECAST_ROW_SCHEMA = "seasonality.model_forecast_ledger.v1"
OUTCOME_ROW_SCHEMA = "seasonality.model_outcome_ledger.v1"

CALIBRATION_VERSION = "seasonality-forward-chain-v1"
TIER = "shadow"

CALIBRATION_METHODS = ("platt", "isotonic", "auto")

#: Floors that mirror the ones inside :mod:`engine.validation` so this module can
#: name the reason instead of returning that module's empty dict.
MIN_PLATT_FIT = 40
MIN_ISOTONIC_FIT = 30
MIN_SCORE_ROWS = 10
MIN_METRIC_ROWS = 30
#: ``isotonic`` is a step function with no functional form; below this it is
#: memorising the training block.
AUTO_ISOTONIC_FLOOR = 200

_EPS = 1e-6


class CalibrationError(Exception):
    """Base for refusals in this module."""


class ForwardChainError(CalibrationError):
    """A chronology violation — the fit saw the fold it was about to score."""


class LedgerAppendError(CalibrationError):
    """An append that would rewrite or re-date an existing ledger row."""


# --------------------------------------------------------------------------- #
# records
# --------------------------------------------------------------------------- #
REQUIRED_RECORD_FIELDS = ("key", "issued_at", "resolved_at", "p", "y")


def _to_date(value: Any, field: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError as exc:
            raise CalibrationError(f"{field} is not an ISO date: {value!r}") from exc
    if isinstance(value, pd.Timestamp):  # pragma: no cover - pandas passthrough
        return value.date()
    raise CalibrationError(f"{field} must be a date, datetime, or ISO string; got {value!r}")


def normalize_records(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Validate and sort a prediction stream by ``issued_at``.

    Sorting is by ``(issued_at, resolved_at, key)`` so the order is TOTAL and
    deterministic — biotech predictions share issue dates constantly, and a
    tie broken by list position would make the fold boundaries depend on how the
    caller happened to build the list.

    A record whose outcome resolves BEFORE it was issued is a data error, not a
    fast resolution, and it raises: that single row would otherwise slip into its
    own training set.
    """
    out: list[dict[str, Any]] = []
    for i, raw in enumerate(records or []):
        missing = [f for f in REQUIRED_RECORD_FIELDS if f not in raw]
        if missing:
            raise CalibrationError(f"record {i} missing required fields {missing}")
        issued = _to_date(raw["issued_at"], f"record[{i}].issued_at")
        resolved = _to_date(raw["resolved_at"], f"record[{i}].resolved_at")
        if resolved < issued:
            raise ForwardChainError(
                f"record {raw['key']!r} resolves {resolved} BEFORE it was issued "
                f"{issued} — an outcome that predates its forecast would enter its own "
                "training set"
            )
        row = dict(raw)
        row["issued_at"] = issued
        row["resolved_at"] = resolved
        row["p"] = float(raw["p"])
        row["y"] = float(raw["y"])
        out.append(row)
    out.sort(key=lambda r: (r["issued_at"], r["resolved_at"], str(r["key"])))
    return out


def _clusters(records: Sequence[Mapping[str, Any]], cluster_key: str) -> tuple[list[str], str]:
    """Cluster label per record, and the BASIS used.

    Falling back to one-cluster-per-record is disclosed rather than silent: that
    fallback gives overlapping horizons no protection at all, and a CI computed
    under it is narrower than the data earns.

    This is the ONLY cluster-derivation rule in the module.  Every CI goes
    through it, because the two rules that used to coexist —  this one and a bare
    ``r.get(cluster_key, r["key"])`` inside each consumer — disagreed on both
    ends: a MISSING key made the nested CIs quietly per-record while the header
    said otherwise, and a PRESENT-but-``None`` key collapsed every row into one
    cluster called ``"None"``, so a payload could report 200 clusters at the top
    and abstain on ``single_cluster`` in every interval below it.
    """
    labels = [str(r.get(cluster_key)) for r in records]
    if any(lbl in ("None", "") for lbl in labels):
        return ([str(r["key"]) for r in records], "per_record_fallback_no_overlap_protection")
    return (labels, cluster_key)


def _partial_cluster_basis(records: Sequence[Mapping[str, Any]], cluster_key: str,
                           basis: str) -> str:
    """Name a PARTIALLY populated cluster key.

    Half a stream carrying ``date_cluster`` is not the same evidence as all of
    it, and ``per_record_fallback_no_overlap_protection`` alone does not say how
    much of the protection was lost.
    """
    if basis == cluster_key:
        return basis
    have = sum(1 for r in records if str(r.get(cluster_key)) not in ("None", ""))
    if have:
        return (f"per_record_fallback_no_overlap_protection:"
                f"{have}/{len(records)}_rows_carried_{cluster_key}")
    return basis


def _score_values(records: Sequence[Mapping[str, Any]], score_key: str) -> list[float]:
    """The scores every metric in this module reads.

    REFUSES when a row does not carry ``score_key``.  The old
    ``r.get(score_key, r["p"])`` fell back to the RAW score while the payload
    kept reporting ``score_key="p_cal"``, which is precisely the relabelling
    :func:`apply_calibrator` raises to prevent — reintroduced by a ``dict.get``
    default four functions later.  It matters in practice because
    :func:`forward_chained_calibration` returns ``calibrated`` as a SUBSET (an
    abstaining fold contributes no rows), so a caller who re-scores the whole
    stream lands on the fallback naturally.

    Scoring raw scores is fine — it just has to be SAID: pass ``score_key="p"``.
    """
    missing = [str(r.get("key")) for r in records if score_key not in r]
    if missing:
        raise CalibrationError(
            f"{len(missing)} of {len(records)} records carry no '{score_key}' "
            f"(e.g. {missing[:5]}). Falling back to the raw 'p' here would report those "
            f"rows under score_key='{score_key}' as if they had been calibrated — the "
            "same relabelling apply_calibrator refuses. To score the RAW scores, say so: "
            "score_key='p'.")
    return [float(r[score_key]) for r in records]


# --------------------------------------------------------------------------- #
# named nulls
# --------------------------------------------------------------------------- #
def _null(reason: str, **extra: Any) -> dict[str, Any]:
    """An unestimable metric is a NAMED abstention, never a default value."""
    payload = {"schema": ABSTENTION_SCHEMA, "tier": TIER,
               "abstained": True, "reason": reason, "value": None}
    payload.update(extra)
    return payload


def _ok(**fields: Any) -> dict[str, Any]:
    """A metric that estimated.  Carries ``tier`` for the same reason
    :func:`_null` does: every one of these blocks is read on its own once it is
    lifted out of the parent payload, and a shadow-tier result that loses its
    tier on the way out is a promoted number by accident."""
    payload = {"abstained": False, "reason": None, "tier": TIER}
    payload.update(fields)
    return payload


# --------------------------------------------------------------------------- #
# THE FORWARD CHAIN
# --------------------------------------------------------------------------- #
def _training_set(records: Sequence[Mapping[str, Any]], cutoff: date) -> list[dict[str, Any]]:
    """The ONLY function in this module that builds a training set.

    It receives the full stream and a CUTOFF — never the fold about to be scored.
    A record qualifies when its OUTCOME was already known at the cutoff
    (``resolved_at <= cutoff``); knowing the prediction is not enough, because a
    calibrator learns from the (p, y) pair and y arrives at ``resolved_at``.
    """
    return [dict(r) for r in records if r["resolved_at"] <= cutoff]


def _assert_no_leak(training: Sequence[Mapping[str, Any]],
                    scored: Sequence[Mapping[str, Any]], fold: str) -> None:
    """Fail CLOSED on any overlap.  Structure should make this unreachable; a
    guard that can never fire costs nothing and a guard that is missing costs a
    silently leaking calibrator."""
    train_keys = {str(r["key"]) for r in training}
    score_keys = {str(r["key"]) for r in scored}
    overlap = sorted(train_keys & score_keys)
    if overlap:
        raise ForwardChainError(
            f"{fold}: {len(overlap)} scored prediction(s) entered their own calibration "
            f"fit: {overlap[:5]}"
        )
    if training and scored:
        fit_max = max(r["resolved_at"] for r in training)
        score_min = min(r["issued_at"] for r in scored)
        if fit_max >= score_min:
            raise ForwardChainError(
                f"{fold}: training outcome known at {fit_max} is not strictly before the "
                f"fold's earliest issue date {score_min}"
            )


def fit_calibrator(training: Sequence[Mapping[str, Any]], method: str = "auto") -> dict[str, Any]:
    """Fit a recalibration map on ``training`` alone.

    Delegates to :func:`engine.validation.platt_fit` /
    :func:`engine.validation.isotonic_calibration` — there is no second Brier or
    second PAVA in this repo.  Returns a NAMED abstention when the house floors
    are not met, never an identity map dressed as a fit.
    """
    if method not in CALIBRATION_METHODS:
        raise CalibrationError(f"method must be one of {list(CALIBRATION_METHODS)}")
    p = [float(r["p"]) for r in training]
    y = [float(r["y"]) for r in training]
    n = len(p)
    chosen = method
    if method == "auto":
        chosen = "isotonic" if n >= AUTO_ISOTONIC_FLOOR else "platt"

    if chosen == "platt":
        if n < MIN_PLATT_FIT:
            return _null(f"platt_unestimable:n_fit={n}<{MIN_PLATT_FIT}",
                         method="platt", n_fit=n)
        model = platt_fit(p, y)
        if not model:
            return _null(f"platt_returned_empty:n_fit={n}", method="platt", n_fit=n)
        return _ok(method="platt", n_fit=n, a=model["a"], b=model["b"],
                   brier_recal=model.get("brier_recal"))

    if n < MIN_ISOTONIC_FIT:
        return _null(f"isotonic_unestimable:n_fit={n}<{MIN_ISOTONIC_FIT}",
                     method="isotonic", n_fit=n)
    model = isotonic_calibration(p, y)
    if not model:
        return _null(f"isotonic_returned_empty:n_fit={n}", method="isotonic", n_fit=n)
    return _ok(method="isotonic", n_fit=n, x=model["x"], y_cal=model["y_cal"],
               ece_before=model.get("ece_before"), ece_after=model.get("ece_after"))


def apply_calibrator(model: Mapping[str, Any], p_new: Sequence[float]) -> list[float]:
    """Map raw scores through a fitted calibrator.  Raises on an abstaining model
    — a caller who ignores the abstention would otherwise publish RAW scores under
    a calibrated label."""
    if model.get("abstained"):
        raise CalibrationError(
            f"cannot apply an abstaining calibrator ({model.get('reason')}); the raw "
            "scores are not calibrated and must not be relabelled as if they were"
        )
    arr = np.asarray([float(v) for v in p_new], float)
    if model["method"] == "platt":
        z = np.log(np.clip(arr, 1e-4, 1 - 1e-4) / (1 - np.clip(arr, 1e-4, 1 - 1e-4)))
        return [float(v) for v in 1.0 / (1.0 + np.exp(-(model["a"] * z + model["b"])))]
    return [float(v) for v in apply_calibration({"x": model["x"], "y_cal": model["y_cal"]}, arr)]


def forward_chained_folds(
    records: Sequence[Mapping[str, Any]],
    *,
    n_folds: int = 4,
    embargo_rows: int = 0,
    embargo_days: int = 0,
) -> dict[str, Any]:
    """Chronological fold plan.  Fold 1 is the SEED training block and is never
    scored — nothing precedes it, so nothing can calibrate it.

    ``embargo_rows`` is handed to :func:`engine.validation.purged_folds`, which
    drops that many trailing rows from each block (the label-leak purge).
    ``embargo_days`` additionally pushes the fit cutoff back in TIME, for horizons
    whose outcome is knowable only after a settlement lag.
    """
    recs = normalize_records(records)
    n = len(recs)
    if n == 0:
        return _null("no_records", n_records=0, folds=[])
    # POSITIONAL index: purged_folds slices by position, and issue dates repeat.
    blocks = purged_folds(pd.RangeIndex(n), int(n_folds), int(embargo_rows))
    names = sorted(blocks, key=lambda k: int(k.replace("fold", "")))
    if len(names) < 2:
        return _null(
            f"insufficient_records_for_forward_chaining:n={n},k={n_folds}",
            n_records=n, folds=[],
            detail="purged_folds degraded to a single block; there is no earlier block "
                   "to calibrate on")

    plan: list[dict[str, Any]] = []
    for name in names[1:]:
        positions = [int(i) for i in blocks[name]]
        if not positions:
            plan.append(_null(f"{name}:empty_after_purge", fold=name, n_score=0))
            continue
        scored = [recs[i] for i in positions]
        score_min_issued = min(r["issued_at"] for r in scored)
        cutoff = score_min_issued - timedelta(days=int(embargo_days) + 1)
        plan.append({
            "fold": name,
            "abstained": False,
            "reason": None,
            "score_positions": positions,
            "n_score": len(scored),
            "score_min_issued_at": score_min_issued.isoformat(),
            "score_max_issued_at": max(r["issued_at"] for r in scored).isoformat(),
            "fit_cutoff": cutoff.isoformat(),
            "embargo_rows": int(embargo_rows),
            "embargo_days": int(embargo_days),
        })
    return {
        "schema": CALIBRATION_SCHEMA,
        "tier": TIER,
        "abstained": False,
        "reason": None,
        "n_records": n,
        "n_folds_requested": int(n_folds),
        "seed_block": {"fold": names[0], "n": len(list(blocks[names[0]]))},
        "folds": plan,
        "law": ("the fit cutoff is the fold's earliest issue date minus the embargo; "
                "training requires resolved_at <= cutoff, so a scored row cannot enter "
                "its own fit"),
    }


def forward_chained_calibration(
    records: Sequence[Mapping[str, Any]],
    *,
    method: str = "auto",
    n_folds: int = 4,
    embargo_rows: int = 0,
    embargo_days: int = 0,
    calibration_version: str = CALIBRATION_VERSION,
) -> dict[str, Any]:
    """Calibrate a prediction stream with strict forward chaining.

    Returns per-fold receipts (each carrying ``fit_keys``, ``fit_max_resolved_at``,
    and ``score_min_issued_at`` so the ordering is checkable) plus the calibrated
    stream.  A fold whose training block is too thin ABSTAINS by name and
    contributes no calibrated rows — its raw scores are not passed through under a
    calibrated label.
    """
    recs = normalize_records(records)
    plan = forward_chained_folds(recs, n_folds=n_folds, embargo_rows=embargo_rows,
                                 embargo_days=embargo_days)
    if plan.get("abstained"):
        return {"schema": CALIBRATION_SCHEMA, "tier": TIER, "abstained": True,
                "reason": plan["reason"], "folds": [], "calibrated": [],
                "calibration_version": calibration_version,
                "method_requested": method, "n_records": len(recs)}

    fold_receipts: list[dict[str, Any]] = []
    calibrated: list[dict[str, Any]] = []

    for spec in plan["folds"]:
        if spec.get("abstained"):
            fold_receipts.append(spec)
            continue
        name = spec["fold"]
        scored = [recs[i] for i in spec["score_positions"]]
        cutoff = _to_date(spec["fit_cutoff"], "fit_cutoff")

        # The fitter is handed a cutoff and the stream — never the fold.
        training = _training_set(recs, cutoff)
        _assert_no_leak(training, scored, name)

        model = fit_calibrator(training, method=method)
        receipt = {
            "fold": name,
            "n_fit": len(training),
            "n_score": len(scored),
            "fit_cutoff": spec["fit_cutoff"],
            "fit_keys": sorted(str(r["key"]) for r in training),
            "score_keys": sorted(str(r["key"]) for r in scored),
            "fit_max_resolved_at": (max(r["resolved_at"] for r in training).isoformat()
                                    if training else None),
            "score_min_issued_at": spec["score_min_issued_at"],
            "n_key_overlap": 0,
            "model": model,
        }
        if model.get("abstained"):
            receipt.update({"abstained": True, "reason": model["reason"]})
            fold_receipts.append(receipt)
            continue

        p_cal = apply_calibrator(model, [r["p"] for r in scored])
        for row, pc in zip(scored, p_cal):
            out = dict(row)
            out["p_cal"] = float(pc)
            out["fold"] = name
            out["calibration_version"] = calibration_version
            # WHICH calibrator produced this row.  Under method="auto" the family
            # switches on n_fit part-way down the stream, so one calibrated column
            # can hold both platt and isotonic rows under a single constant
            # version stamp; without this key nothing downstream can tell.
            out["method"] = model["method"]
            out["tier"] = TIER
            calibrated.append(out)
        receipt.update({"abstained": False, "reason": None})
        fold_receipts.append(receipt)

    scored_folds = [f for f in fold_receipts if not f.get("abstained")]
    families = sorted({str(f["model"]["method"]) for f in scored_folds})
    return {
        "schema": CALIBRATION_SCHEMA,
        "tier": TIER,
        "abstained": not scored_folds,
        "reason": None if scored_folds else "every_fold_abstained",
        "calibration_version": calibration_version,
        "method_requested": method,
        # method="auto" picks per fold, so one calibrated column can carry two
        # families under one version stamp.  Said out loud here and per row.
        "calibrator_families_used": families,
        "mixed_calibrator_families": len(families) > 1,
        "n_records": len(recs),
        "n_calibrated": len(calibrated),
        "n_folds_scored": len(scored_folds),
        "n_folds_abstained": len(fold_receipts) - len(scored_folds),
        "folds": fold_receipts,
        "calibrated": calibrated,
        "seed_block": plan["seed_block"],
    }


# --------------------------------------------------------------------------- #
# cluster-aware uncertainty
# --------------------------------------------------------------------------- #
def cluster_bootstrap_ci(
    values: Sequence[float],
    clusters: Sequence[Any],
    *,
    B: int = 2000,
    seed: int = 17,
    level: float = 0.90,
    cluster_basis: str = "caller_supplied_labels",
) -> dict[str, Any]:
    """Percentile CI for a MEAN, resampling whole date clusters with replacement.

    Overlapping horizons make rows within a cluster one draw; resampling rows
    would report an interval several times narrower than the data earns.

    ``cluster_basis`` names the rule that PRODUCED the labels and is stamped on
    the result.  ``basis="cluster_block_bootstrap"`` used to be stamped
    unconditionally, so an interval computed on one-cluster-per-row — no overlap
    protection at all, and measurably narrower — was labelled identically to one
    computed on real date clusters.  The label said the CI was earned; the number
    said otherwise.

    The payload also names its SEMANTICS.  ``improvement_ci``/``ev_ci`` are
    parameter uncertainty (how well the mean is known), not where the next
    outcome lands, and :mod:`engine.seasonality.model` refuses to emit an
    uncertainty that does not say which one it is.
    """
    v = np.asarray([float(x) for x in values], float)
    labels = np.asarray([str(c) for c in clusters])
    mask = np.isfinite(v)
    v, labels = v[mask], labels[mask]
    if v.size == 0:
        return _null("no_finite_values", cluster_basis=str(cluster_basis))
    uniq = np.unique(labels)
    if uniq.size < 2:
        # NOT `point=`: a consumer reading `.get("point")` off an abstention gets
        # a live number.  The mean is still disclosed, under a name that cannot
        # be mistaken for an estimate that carries an interval.
        return _null(f"single_cluster:n_clusters={int(uniq.size)}",
                     point_estimate_without_ci=float(v.mean()), n=int(v.size),
                     n_clusters=int(uniq.size), cluster_basis=str(cluster_basis))
    groups = [v[labels == u] for u in uniq]
    rng = np.random.default_rng(int(seed))
    draws = np.empty(int(B), float)
    for i in range(int(B)):
        pick = rng.integers(0, len(groups), len(groups))
        draws[i] = float(np.concatenate([groups[j] for j in pick]).mean())
    lo = float(np.percentile(draws, 100 * (1 - level) / 2))
    hi = float(np.percentile(draws, 100 * (1 - (1 - level) / 2)))
    return _ok(point=float(v.mean()), lo=lo, hi=hi, level=float(level),
               n=int(v.size), n_clusters=int(uniq.size), B=int(B), seed=int(seed),
               excludes_zero=bool(lo > 0 or hi < 0),
               semantics="parameter_ci",
               cluster_basis=str(cluster_basis),
               basis="cluster_block_bootstrap")


def cluster_bootstrap_difference_ci(
    values_a: Sequence[float],
    clusters_a: Sequence[Any],
    values_b: Sequence[float],
    clusters_b: Sequence[Any],
    *,
    B: int = 2000,
    seed: int = 17,
    level: float = 0.90,
    cluster_basis: str = "caller_supplied_labels",
) -> dict[str, Any]:
    """CI for ``mean(a) - mean(b)`` on two DISJOINT samples.

    Each side's own clusters are resampled independently and the DIFFERENCE is
    bootstrapped, which is the statistic a reader is being shown.  Asking instead
    whether two separate 90% intervals overlap is a far more conservative test —
    non-overlap of two 90% intervals is nowhere near a 10%-level test of a
    difference — and it costs roughly half the power: on a planted post-break
    calibration slope of 0.70 the overlap rule fired 8 times in 25 where the
    difference bootstrap fired 16.  In a drift monitor that shortfall is a silent
    miss of a live regime break.
    """
    a = np.asarray([float(x) for x in values_a], float)
    b = np.asarray([float(x) for x in values_b], float)
    la = np.asarray([str(c) for c in clusters_a])
    lb = np.asarray([str(c) for c in clusters_b])
    ma, mb = np.isfinite(a), np.isfinite(b)
    a, la, b, lb = a[ma], la[ma], b[mb], lb[mb]
    if a.size == 0 or b.size == 0:
        return _null("no_finite_values_on_one_side", cluster_basis=str(cluster_basis))
    ua, ub = np.unique(la), np.unique(lb)
    if ua.size < 2 or ub.size < 2:
        return _null(f"single_cluster_on_one_side:n_clusters={int(ua.size)}/"
                     f"{int(ub.size)}",
                     point_estimate_without_ci=float(a.mean() - b.mean()),
                     n=int(a.size + b.size), cluster_basis=str(cluster_basis))
    ga = [a[la == u] for u in ua]
    gb = [b[lb == u] for u in ub]
    rng = np.random.default_rng(int(seed))
    draws = np.empty(int(B), float)
    for i in range(int(B)):
        pa = rng.integers(0, len(ga), len(ga))
        pb = rng.integers(0, len(gb), len(gb))
        draws[i] = float(np.concatenate([ga[j] for j in pa]).mean()
                         - np.concatenate([gb[j] for j in pb]).mean())
    lo = float(np.percentile(draws, 100 * (1 - level) / 2))
    hi = float(np.percentile(draws, 100 * (1 - (1 - level) / 2)))
    return _ok(point=float(a.mean() - b.mean()), lo=lo, hi=hi, level=float(level),
               n=int(a.size + b.size), n_clusters_a=int(ua.size),
               n_clusters_b=int(ub.size), B=int(B), seed=int(seed),
               excludes_zero=bool(lo > 0 or hi < 0),
               semantics="parameter_ci",
               cluster_basis=str(cluster_basis),
               basis="cluster_block_bootstrap_of_the_difference")


# --------------------------------------------------------------------------- #
# scoring rules
# --------------------------------------------------------------------------- #
def log_score(p: Sequence[float], y: Sequence[float]) -> dict[str, Any]:
    """Mean negative log-likelihood, plus the base-rate reference.

    Not in :mod:`engine.validation`, so it is implemented here — the six
    primitives that ARE there are imported, never re-typed.
    """
    pa = np.asarray([float(v) for v in p], float)
    ya = np.asarray([float(v) for v in y], float)
    m = np.isfinite(pa) & np.isfinite(ya)
    pa, ya = np.clip(pa[m], _EPS, 1 - _EPS), ya[m]
    # The floor is the METRIC floor, not the lower scoring floor: the log score is
    # unbounded and a single confident miss dominates it, so it may not be
    # estimable on a sample where the bounded Brier already abstains.
    if pa.size < MIN_METRIC_ROWS:
        return _null(f"log_score_unestimable:n={int(pa.size)}<{MIN_METRIC_ROWS}")
    ls = float(-np.mean(ya * np.log(pa) + (1 - ya) * np.log(1 - pa)))
    base = float(np.clip(ya.mean(), _EPS, 1 - _EPS))
    base_ls = float(-(base * math.log(base) + (1 - base) * math.log(1 - base)))
    return _ok(log_score=round(ls, 6), base_rate_log_score=round(base_ls, 6),
               skill=round(1 - ls / base_ls, 4) if base_ls else None,
               n=int(pa.size), base_rate=round(base, 4),
               # Said out loud: this reference is the FULL-SAMPLE base rate, so it
               # is an in-sample benchmark in a module whose thesis is that no
               # benchmark sees the future.  The direction is conservative (the
               # reference is flattered, not the model) and the point-in-time
               # comparison a decision-maker could have made is
               # `chronological_baseline`, which expands.
               base_rate_is_in_sample=True,
               base_rate_basis="full_sample_realized_outcomes",
               point_in_time_alternative="chronological_baseline")


def _n_finite(p: Sequence[float], y: Sequence[float]) -> int:
    """The row count the DELEGATE actually saw.

    ``engine.validation`` masks non-finite pairs before applying its floor, so
    reporting ``len(p)`` in the abstention string prints an inequality that is
    arithmetically false — ``n=100<30`` on an all-NaN input of length 100 — and
    names a floor that was not the one hit.
    """
    pa = np.asarray([float(v) for v in p], float)
    ya = np.asarray([float(v) for v in y], float)
    if pa.size != ya.size:
        return 0
    return int(np.count_nonzero(np.isfinite(pa) & np.isfinite(ya)))


def _brier_block(p: Sequence[float], y: Sequence[float]) -> dict[str, Any]:
    out = brier_reliability(p, y)
    if not out:
        n_ok = _n_finite(p, y)
        return _null(f"brier_unestimable:n_finite={n_ok}<{MIN_METRIC_ROWS}",
                     n_rows_offered=len(list(p)), n_finite_pairs=n_ok)
    return _ok(**out)


def _ece_block(p: Sequence[float], y: Sequence[float]) -> dict[str, Any]:
    out = expected_calibration_error(p, y)
    if not out:
        n_ok = _n_finite(p, y)
        return _null(f"ece_unestimable:n_finite={n_ok}<{MIN_METRIC_ROWS}",
                     n_rows_offered=len(list(p)), n_finite_pairs=n_ok)
    return _ok(**out)


def _slope_intercept(p: Sequence[float], y: Sequence[float]) -> dict[str, Any]:
    """Calibration slope and intercept in logit space, from ``platt_fit``.

    slope 1 / intercept 0 == already calibrated.  slope < 1 means the forecasts
    are OVERCONFIDENT (too far from the base rate); slope > 1 means underconfident.

    ``reading`` is a categorical verdict off a POINT estimate, and at this
    module's own fit floor the point estimate is very noisy: on 500 replications
    of perfectly calibrated data at n=40 the hard 0.9/1.1 thresholds called it
    miscalibrated 76% of the time.  So the reading is only allowed to leave
    "calibrated" when the slope's own uncertainty supports it — a bootstrap CI on
    the slope that excludes the identity band — and the interval, the raw point
    reading, and the estimability of the interval are all reported.  This is the
    same rule ``drift_report`` applies to a break, applied consistently.
    """
    out = platt_fit(p, y)
    n_ok = _n_finite(p, y)
    if not out:
        return _null(f"calibration_slope_unestimable:n_finite={n_ok}<{MIN_PLATT_FIT}",
                     n_rows_offered=len(list(p)), n_finite_pairs=n_ok)
    slope = float(out["a"])
    point_reading = ("overconfident" if slope < 0.9 else
                     "underconfident" if slope > 1.1 else "calibrated")
    ci = _slope_ci(p, y)
    if ci.get("abstained"):
        reading = "not_distinguishable_from_calibrated:slope_ci_unestimable"
    elif ci["hi"] < 0.9:
        reading = "overconfident"
    elif ci["lo"] > 1.1:
        reading = "underconfident"
    else:
        reading = "not_distinguishable_from_calibrated"
    return _ok(slope=out["a"], intercept=out["b"], brier_recal=out.get("brier_recal"),
               reading=reading,
               point_reading=point_reading,
               slope_ci=ci,
               n=n_ok, n_rows_offered=len(list(p)),
               basis=("reading requires the slope's bootstrap CI to clear the "
                      "0.9-1.1 identity band; a point estimate on a thin fit is a "
                      "coin flip"))


def _slope_ci(p: Sequence[float], y: Sequence[float], *, B: int = 200,
              seed: int = 17, level: float = 0.90) -> dict[str, Any]:
    """Bootstrap CI for the calibration slope.

    Rows, not clusters: the slope is a property of the (p, y) pairs and this
    interval exists to stop a NOISE-driven verdict, so it is deliberately the
    cheap one.  ``B`` is small because ``platt_fit`` runs 400 gradient steps per
    resample and this runs inside every evaluation.
    """
    pa = np.asarray([float(v) for v in p], float)
    ya = np.asarray([float(v) for v in y], float)
    m = np.isfinite(pa) & np.isfinite(ya)
    pa, ya = pa[m], ya[m]
    if pa.size < MIN_PLATT_FIT:
        return _null(f"slope_ci_unestimable:n_finite={int(pa.size)}<{MIN_PLATT_FIT}")
    rng = np.random.default_rng(int(seed))
    slopes: list[float] = []
    for _ in range(int(B)):
        idx = rng.integers(0, pa.size, pa.size)
        fit = platt_fit(pa[idx], ya[idx])
        if fit:
            slopes.append(float(fit["a"]))
    if len(slopes) < int(B) // 2:
        return _null(f"slope_ci_unestimable:only {len(slopes)}/{B} resamples fit")
    lo = float(np.percentile(slopes, 100 * (1 - level) / 2))
    hi = float(np.percentile(slopes, 100 * (1 - (1 - level) / 2)))
    return _ok(lo=lo, hi=hi, level=float(level), B=int(B), seed=int(seed),
               n=int(pa.size), semantics="parameter_ci",
               basis="row_bootstrap_of_the_platt_slope")


def _crps_block(records: Sequence[Mapping[str, Any]], sample_key: str,
                realized_key: str) -> dict[str, Any]:
    """CRPS where the forecast is DISTRIBUTIONAL.  A stream with no ensembles
    abstains by name rather than reporting a probability score for a shape."""
    sets, ys = [], []
    for r in records:
        s = r.get(sample_key)
        v = r.get(realized_key)
        if s is None or v is None:
            continue
        sets.append([float(x) for x in s])
        ys.append(float(v))
    if not sets:
        return _null("crps_not_applicable:no_distributional_forecasts_in_stream")
    clim = sorted(ys)
    out = crps_score(sets, ys, clim=clim)
    if not out:
        return _null(f"crps_unestimable:n_pairs={len(sets)}<10")
    return _ok(**out, climatology="pooled_realized_outcomes",
               # The climatology is built from the OUTCOMES BEING SCORED — an
               # in-sample reference.  It flatters the benchmark, not the
               # forecast, so the skill number is conservative; it is stated
               # rather than left for a reader to infer from the label.
               climatology_is_in_sample=True,
               climatology_basis="full_sample_realized_outcomes")


# --------------------------------------------------------------------------- #
# baselines, holdouts, drift, economics
# --------------------------------------------------------------------------- #
def chronological_baseline(records: Sequence[Mapping[str, Any]],
                           *, score_key: str = "p_cal",
                           cluster_key: str = "date_cluster",
                           min_history: int = MIN_SCORE_ROWS) -> dict[str, Any]:
    """Compare the forecasts against the EXPANDING PRIOR base rate.

    The baseline for row *i* is the mean outcome over rows whose outcome had
    already resolved when row *i* was issued — a forecast a decision-maker could
    genuinely have made, not the full-sample base rate (which is itself a leak).
    Rows with too little prior history are EXCLUDED and counted, not filled.
    """
    recs = sorted(records, key=lambda r: (r["issued_at"], str(r["key"])))
    scores = _score_values(recs, score_key)
    labels, cluster_basis = _clusters(recs, cluster_key)
    cluster_basis = _partial_cluster_basis(recs, cluster_key, cluster_basis)
    losses_model: list[float] = []
    losses_base: list[float] = []
    clusters: list[str] = []
    skipped = 0
    for row, p, label in zip(recs, scores, labels):
        prior = [float(o["y"]) for o in recs if o["resolved_at"] < row["issued_at"]]
        if len(prior) < int(min_history):
            skipped += 1
            continue
        base = float(np.mean(prior))
        y = float(row["y"])
        losses_model.append((p - y) ** 2)
        losses_base.append((base - y) ** 2)
        clusters.append(label)
    if len(losses_model) < MIN_SCORE_ROWS:
        return _null(f"chronological_baseline_unestimable:n_gradeable="
                     f"{len(losses_model)}<{MIN_SCORE_ROWS}", n_skipped_thin_history=skipped)
    delta = [b - m for m, b in zip(losses_model, losses_base)]
    ci = cluster_bootstrap_ci(delta, clusters, cluster_basis=cluster_basis)
    return _ok(n=len(losses_model), n_skipped_thin_history=skipped,
               score_key=str(score_key),
               cluster_basis=cluster_basis,
               brier_model=round(float(np.mean(losses_model)), 6),
               brier_expanding_base_rate=round(float(np.mean(losses_base)), 6),
               brier_improvement=round(float(np.mean(delta)), 6),
               improvement_ci=ci,
               basis="expanding prior base rate over already-resolved outcomes")


def group_holdout(records: Sequence[Mapping[str, Any]], group_key: str,
                  *, method: str = "auto", n_folds: int = 4, embargo_rows: int = 0,
                  embargo_days: int = 0, min_group: int = MIN_SCORE_ROWS,
                  cluster_key: str = "date_cluster") -> dict[str, Any]:
    """Leave-one-GROUP-out calibration layered ON TOP of the forward chain.

    Both constraints hold at once, and that combination is the point:

    * the fit for a fold still only sees predictions resolved before that fold
      opened (the chronology is never relaxed for convenience), and
    * within a fold the held-out group is removed from the fit, so the score for
      issuer X is produced by a calibrator that never saw issuer X.

    Applying the group cutoff on its own — fit only on what resolved before the
    GROUP's first prediction — starves every group present at the start of the
    stream and the holdout silently reports nothing.  Chaining per fold is what
    makes the holdout estimable and honest at the same time.
    """
    recs = normalize_records(records)
    groups = sorted({str(r.get(group_key)) for r in recs if r.get(group_key) is not None})
    if len(groups) < 2:
        return _null(f"{group_key}_holdout_unestimable:n_groups={len(groups)}<2")

    plan = forward_chained_folds(recs, n_folds=n_folds, embargo_rows=embargo_rows,
                                 embargo_days=embargo_days)
    if plan.get("abstained"):
        return _null(f"{group_key}_holdout_unestimable:{plan['reason']}")

    all_labels, cluster_basis = _clusters(recs, cluster_key)
    cluster_basis = _partial_cluster_basis(recs, cluster_key, cluster_basis)
    label_by_key = {str(r["key"]): lbl for r, lbl in zip(recs, all_labels)}

    losses_by_group: dict[str, list[float]] = {g: [] for g in groups}
    clusters_by_group: dict[str, list[str]] = {g: [] for g in groups}
    fit_notes: dict[str, list[str]] = {g: [] for g in groups}
    n_fit_by_group: dict[str, list[int]] = {g: [] for g in groups}

    for spec in plan["folds"]:
        if spec.get("abstained"):
            continue
        fold_rows = [recs[i] for i in spec["score_positions"]]
        cutoff = _to_date(spec["fit_cutoff"], "fit_cutoff")
        fold_training = _training_set(recs, cutoff)
        for g in groups:
            held = [r for r in fold_rows if str(r.get(group_key)) == g]
            if not held:
                continue
            training = [r for r in fold_training if str(r.get(group_key)) != g]
            _assert_no_leak(training, held, f"{spec['fold']}/{group_key}={g}")
            model = fit_calibrator(training, method=method)
            if model.get("abstained"):
                fit_notes[g].append(f"{spec['fold']}:{model['reason']}")
                continue
            p_cal = apply_calibrator(model, [r["p"] for r in held])
            losses_by_group[g].extend((pc - float(r["y"])) ** 2
                                      for pc, r in zip(p_cal, held))
            clusters_by_group[g].extend(label_by_key[str(r["key"])] for r in held)
            n_fit_by_group[g].append(int(model["n_fit"]))

    per: dict[str, Any] = {}
    all_losses: list[float] = []
    all_clusters: list[str] = []
    for g in groups:
        losses = losses_by_group[g]
        if len(losses) < int(min_group):
            per[g] = _null(f"group_too_thin:n_scored={len(losses)}<{min_group}",
                           fit_abstentions=fit_notes[g])
            continue
        per[g] = _ok(n=len(losses), n_fit_min=min(n_fit_by_group[g]),
                     brier=round(float(np.mean(losses)), 6),
                     fit_abstentions=fit_notes[g])
        all_losses.extend(losses)
        all_clusters.extend(clusters_by_group[g])

    if len(all_losses) < MIN_SCORE_ROWS:
        return _null(f"{group_key}_holdout_unestimable:n_scored={len(all_losses)}",
                     groups=per)
    return _ok(group_key=group_key, n_groups=len(groups), n_scored=len(all_losses),
               n_groups_scored=sum(1 for v in per.values() if not v.get("abstained")),
               cluster_basis=cluster_basis,
               pooled_brier=round(float(np.mean(all_losses)), 6),
               pooled_brier_ci=cluster_bootstrap_ci(all_losses, all_clusters,
                                                    cluster_basis=cluster_basis),
               basis="forward-chained folds with the held-out group removed from each fit",
               groups=per)


def drift_report(records: Sequence[Mapping[str, Any]], *, score_key: str = "p_cal",
                 cluster_key: str = "date_cluster") -> dict[str, Any]:
    """Split the scored stream at its median issue date and compare the halves.

    Reports Brier, ECE, and calibration slope for each half plus a cluster
    bootstrap CI ON THE DIFFERENCE.  ``break_detected`` is True only when that
    CI excludes zero — a point difference is not a break.

    The difference is bootstrapped directly rather than inferred from whether the
    two halves' separate intervals overlap.  Non-overlap of two 90% intervals is
    not a 10%-level test of a difference, it is far more conservative, and the
    shortfall is measurable: on a planted post-break calibration slope of 0.70
    the overlap rule fired 8/25 where the difference bootstrap fired 16/25.  In
    the module's only drift monitor, that gap is a silent miss of a live break.
    Both halves' own intervals are still reported, because they are what a reader
    looks at next.
    """
    recs = sorted(records, key=lambda r: (r["issued_at"], str(r["key"])))
    if len(recs) < 2 * MIN_METRIC_ROWS:
        return _null(f"drift_unestimable:n={len(recs)}<{2 * MIN_METRIC_ROWS}")
    scores = _score_values(recs, score_key)
    labels, cluster_basis = _clusters(recs, cluster_key)
    cluster_basis = _partial_cluster_basis(recs, cluster_key, cluster_basis)
    mid = len(recs) // 2
    early, late = recs[:mid], recs[mid:]
    p_early, p_late = scores[:mid], scores[mid:]
    c_early, c_late = labels[:mid], labels[mid:]

    def half(rows: Sequence[Mapping[str, Any]], p: Sequence[float],
             label: str) -> dict[str, Any]:
        y = [float(r["y"]) for r in rows]
        return {"label": label, "n": len(rows),
                "span": [rows[0]["issued_at"].isoformat(), rows[-1]["issued_at"].isoformat()],
                "brier": _brier_block(p, y), "ece": _ece_block(p, y),
                "calibration_slope": _slope_intercept(p, y)}

    e, l = half(early, p_early, "early"), half(late, p_late, "late")
    loss_early = [(p - float(r["y"])) ** 2 for p, r in zip(p_early, early)]
    loss_late = [(p - float(r["y"])) ** 2 for p, r in zip(p_late, late)]
    ci_late = cluster_bootstrap_ci(loss_late, c_late, cluster_basis=cluster_basis)
    ci_early = cluster_bootstrap_ci(loss_early, c_early, cluster_basis=cluster_basis)
    delta_ci = cluster_bootstrap_difference_ci(loss_late, c_late, loss_early, c_early,
                                               cluster_basis=cluster_basis)
    delta = float(np.mean(loss_late) - np.mean(loss_early))
    detected = bool(not delta_ci.get("abstained") and delta_ci.get("excludes_zero"))
    # Reported alongside, because it is what this function used to CALL a break
    # and a reader comparing runs needs to see the two rules disagree.
    disjoint = (not ci_late.get("abstained") and not ci_early.get("abstained")
                and (ci_late["lo"] > ci_early["hi"] or ci_early["lo"] > ci_late["hi"]))
    return _ok(early=e, late=l,
               score_key=str(score_key),
               cluster_basis=cluster_basis,
               brier_delta_late_minus_early=round(delta, 6),
               brier_delta_ci=delta_ci,
               early_brier_ci=ci_early, late_brier_ci=ci_late,
               break_detected=detected,
               halves_intervals_disjoint=bool(disjoint),
               basis=("median issue-date split; break requires a cluster-bootstrap CI on "
                      "the DIFFERENCE that excludes zero (the disjoint-intervals rule is "
                      "reported too, and is roughly half as powerful)"))


def decision_economics(records: Sequence[Mapping[str, Any]], *, threshold: float,
                       win: float, loss: float, cost: float,
                       score_key: str = "p_cal",
                       cluster_key: str = "date_cluster") -> dict[str, Any]:
    """Expected value per decision AFTER costs, for the rule "act when p >= t".

    A calibration study that stops at Brier has not said whether acting on the
    forecast pays.  Abstains by name when the rule never fires — an empty rule has
    no economics, and reporting 0.0 would read as break-even.
    """
    rows = list(records)
    scores = _score_values(rows, score_key)
    labels, cluster_basis = _clusters(rows, cluster_key)
    cluster_basis = _partial_cluster_basis(rows, cluster_key, cluster_basis)
    fired = [(r, lbl) for r, p, lbl in zip(rows, scores, labels)
             if p >= float(threshold)]
    if not fired:
        return _null(f"no_decisions_at_threshold:{threshold}", n_candidates=len(rows))
    acted = [r for r, _ in fired]
    clusters = [lbl for _, lbl in fired]
    payoffs = [float(win) * float(r["y"]) - float(loss) * (1 - float(r["y"])) - float(cost)
               for r in acted]
    hit = float(np.mean([float(r["y"]) for r in acted]))
    return _ok(threshold=float(threshold), n_decisions=len(acted),
               n_candidates=len(rows),
               score_key=str(score_key),
               cluster_basis=cluster_basis,
               fire_rate=round(len(acted) / len(rows), 4),
               hit_rate=round(hit, 4),
               ev_per_decision_after_costs=round(float(np.mean(payoffs)), 6),
               total_after_costs=round(float(np.sum(payoffs)), 6),
               ev_ci=cluster_bootstrap_ci(payoffs, clusters, cluster_basis=cluster_basis),
               costs={"win": float(win), "loss": float(loss), "cost": float(cost)},
               do_nothing_ev=0.0)


# --------------------------------------------------------------------------- #
# the evaluation bundle
# --------------------------------------------------------------------------- #
def evaluate(
    records: Sequence[Mapping[str, Any]],
    *,
    score_key: str = "p_cal",
    cluster_key: str = "date_cluster",
    issuer_key: str = "issuer",
    class_key: str = "therapeutic_class",
    sample_key: str = "samples",
    realized_key: str = "realized",
    method: str = "auto",
    economics: Mapping[str, float] | None = None,
    calibration_version: str = CALIBRATION_VERSION,
) -> dict[str, Any]:
    """The full evaluation.  Every slot is present; unestimable slots are NAMED
    abstentions rather than defaults."""
    recs = normalize_records(records)
    if not recs:
        return {"schema": EVALUATION_SCHEMA, "tier": TIER, "abstained": True,
                "reason": "no_records", "calibration_version": calibration_version}

    p = _score_values(recs, score_key)
    y = [float(r["y"]) for r in recs]
    labels, basis = _clusters(recs, cluster_key)
    basis = _partial_cluster_basis(recs, cluster_key, basis)
    brier = _brier_block(p, y)
    econ_cfg = dict(economics or {})
    methods = sorted({str(r["method"]) for r in recs if r.get("method")})

    return {
        "schema": EVALUATION_SCHEMA,
        "tier": TIER,
        "abstained": False,
        "reason": None,
        "calibration_version": calibration_version,
        "score_key": score_key,
        "n_rows_with_score_key": sum(1 for r in recs if score_key in r),
        "calibrator_methods_present": methods,
        "n": len(recs),
        "span": [recs[0]["issued_at"].isoformat(), recs[-1]["issued_at"].isoformat()],
        "cluster_basis": basis,
        "n_clusters": len(set(labels)),
        "brier": brier,
        "log_score": log_score(p, y),
        "crps": _crps_block(recs, sample_key, realized_key),
        "reliability_bins": (_ok(bins=brier["reliability"], n_bins=len(brier["reliability"]))
                             if not brier.get("abstained") and brier.get("reliability")
                             else _null("reliability_bins_unestimable:no_bin_reached_10_obs")),
        "expected_calibration_error": _ece_block(p, y),
        "calibration_slope_intercept": _slope_intercept(p, y),
        "chronological_baseline": chronological_baseline(
            recs, score_key=score_key, cluster_key=cluster_key),
        "issuer_holdout": group_holdout(recs, issuer_key, method=method,
                                        cluster_key=cluster_key),
        "therapeutic_class_holdout": group_holdout(recs, class_key, method=method,
                                                   cluster_key=cluster_key),
        "drift": drift_report(recs, score_key=score_key, cluster_key=cluster_key),
        "decision_economics": (
            decision_economics(recs, score_key=score_key, cluster_key=cluster_key,
                               threshold=float(econ_cfg["threshold"]),
                               win=float(econ_cfg["win"]), loss=float(econ_cfg["loss"]),
                               cost=float(econ_cfg["cost"]))
            if {"threshold", "win", "loss", "cost"} <= set(econ_cfg)
            else _null("decision_economics_not_configured:"
                       "requires threshold, win, loss, cost")),
        # The promotion DECISION (none) is this module's to make. The forward ledger's
        # grade COUNT is not — and this function never reads the ledger, so it was in no
        # position to assert one. It claimed "zero matured grades" as a standing fact
        # until 2026-08-14, when the first window matured (BDX:2026:219-224, graded
        # 2026-08-13) and the sentence quietly became false. Nothing caught it: the only
        # test compared the literal to itself, so the claim was its own evidence. State
        # what this module actually knows.
        "promotion": ("NONE — shadow tier. Forward grades accrue as windows mature and are "
                      "evidence toward a record, not a promotion; nothing here moves an "
                      "availability flag"),
    }


# --------------------------------------------------------------------------- #
# append-only ledgers (pure functions; the nightly owns production writes)
# --------------------------------------------------------------------------- #
def _canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _row_hash(payload: Mapping[str, Any]) -> str:
    body = {k: v for k, v in payload.items() if k != "row_hash"}
    return "sha256:" + hashlib.sha256(_canonical_json(body).encode("utf-8")).hexdigest()


def _existing(path: Path) -> dict[str, str]:
    """row_id -> row_hash for every line already on disk.  A malformed line is
    reported, never rewritten: this module has no code path that edits a line."""
    out: dict[str, str] = {}
    if not path.exists():
        return out
    with path.open("r", encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise LedgerAppendError(
                    f"{path}:{lineno} is not valid JSON ({exc}); refusing to append to a "
                    "ledger this module cannot read, because a blind append would bury it"
                ) from exc
            rid = f"{row.get('row_type')}:{row.get('key')}"
            out[rid] = str(row.get("row_hash") or _row_hash(row))
    return out


def _append_row(path: Any, row: Mapping[str, Any], *, schema: str, row_type: str,
                required: Sequence[str]) -> dict[str, Any]:
    """Append ONE row.  Never rewrites, reorders, or re-dates.

    * identical replay -> ``appended=False``, nothing written;
    * same key with different content -> :class:`LedgerAppendError`;
    * otherwise -> one line appended in ``"a"`` mode.
    """
    target = Path(path)
    missing = [f for f in required if not str(row.get(f) or "").strip()]
    if missing:
        raise LedgerAppendError(f"{row_type} row missing required fields {missing}")

    body = dict(row)
    body["schema"] = schema
    body["row_type"] = row_type
    body["tier"] = TIER
    body.pop("row_hash", None)
    digest = _row_hash(body)
    body["row_hash"] = digest
    row_id = f"{row_type}:{body['key']}"

    seen = _existing(target)
    if row_id in seen:
        if seen[row_id] == digest:
            return {"appended": False, "reason": "duplicate_identical_replay",
                    "row_id": row_id, "row_hash": digest, "path": str(target),
                    "tier": TIER}
        raise LedgerAppendError(
            f"{row_id} is already in {target} with a different content hash "
            f"({seen[row_id]} != {digest}). This ledger is append-only: a row is never "
            "rewritten, reordered, or re-dated. Append a correcting row under a new key "
            "instead."
        )

    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(_canonical_json(body) + "\n")
    return {"appended": True, "reason": None, "row_id": row_id, "row_hash": digest,
            "path": str(target), "tier": TIER}


def append_forecast_row(path: Any, row: Mapping[str, Any]) -> dict[str, Any]:
    """Append a forecast registration.  Append-only and idempotent by content."""
    return _append_row(path, row, schema=FORECAST_ROW_SCHEMA, row_type="forecast",
                       required=("key", "issued_at"))


def append_outcome_row(path: Any, row: Mapping[str, Any]) -> dict[str, Any]:
    """Append a matured outcome.  Append-only and idempotent by content."""
    return _append_row(path, row, schema=OUTCOME_ROW_SCHEMA, row_type="outcome",
                       required=("key", "resolved_at"))


def read_ledger(path: Any) -> list[dict[str, Any]]:
    """Read a ledger back IN FILE ORDER.  Read-only; nothing here sorts or edits."""
    target = Path(path)
    if not target.exists():
        return []
    rows: list[dict[str, Any]] = []
    with target.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


__all__ = [
    "ABSTENTION_SCHEMA",
    "AUTO_ISOTONIC_FLOOR",
    "CALIBRATION_METHODS",
    "CALIBRATION_SCHEMA",
    "CALIBRATION_VERSION",
    "EVALUATION_SCHEMA",
    "FORECAST_ROW_SCHEMA",
    "MIN_ISOTONIC_FIT",
    "MIN_METRIC_ROWS",
    "MIN_PLATT_FIT",
    "MIN_SCORE_ROWS",
    "OUTCOME_ROW_SCHEMA",
    "REQUIRED_RECORD_FIELDS",
    "TIER",
    "CalibrationError",
    "ForwardChainError",
    "LedgerAppendError",
    "append_forecast_row",
    "append_outcome_row",
    "apply_calibrator",
    "chronological_baseline",
    "cluster_bootstrap_ci",
    "cluster_bootstrap_difference_ci",
    "decision_economics",
    "drift_report",
    "evaluate",
    "fit_calibrator",
    "forward_chained_calibration",
    "forward_chained_folds",
    "group_holdout",
    "log_score",
    "normalize_records",
    "read_ledger",
]
