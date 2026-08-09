"""Wave 9F — Government Revenue delivered to Prophet as post-selection annotation.

Prophet keeps sole pick authority.  This module runs AFTER Prophet has already
chosen, ranked, sized, and gated its plans, and it may only hang evidence off a
plan that already exists.  It cannot add a plan, remove one, reorder them, or
move a single number Prophet decided.

THE IMPORT BOUNDARY IS WHY THIS FILE READS JSON INSTEAD OF CALLING PYTHON
========================================================================
The obvious implementation would import ``engine.government_revenue.candidates``
and validate the queue with ``is_valid_candidate_queue``.  That would put a
candidate SOURCE on Prophet's transitive import graph, which is exactly the thing
Wave 9F's gate forbids: "Prophet cannot call Government Revenue to source a
candidate."  So this module reads the already-written artifact as data and
re-verifies it structurally — contract string, the complete typed authority
fence, and the fields it intends to render — with no dependency on the builder
that produced it.  ``tests/test_government_revenue_prophet_annotation.py`` walks
the whole transitive graph to keep it that way.

FAIL OPEN, ALWAYS
-----------------
Every failure mode — missing artifact, malformed JSON, wrong contract, a broken
authority fence, a slow packet build, an outright exception — returns Prophet's
preexisting plans unchanged.  An annotation is a nice-to-have; a moved decision
is an incident.  ``annotate_selected_plans`` therefore fingerprints the decision
fields before and after its own work and discards its own output if they differ,
so the byte-identity gate is enforced at runtime and not only in the suite.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import math
from pathlib import Path
import time
from typing import Any, Callable, Iterable, Mapping, Sequence


CONTRACT = "government_revenue.prophet_annotation.v1"
SCHEMA_VERSION = "1.0.0"

#: The artifact this adapter reads.  Nightly is its sole advancer.
QUEUE_RELATIVE_PATH = "data/government_revenue/candidate_queue.json"
QUEUE_CONTRACT = "government_revenue_candidate_queue.v1"
CANDIDATE_CONTRACT = "government_revenue_candidate.v1"

#: Authority this annotation carries, and the ONLY shape it accepts from the
#: queue it reads.  Mirrors ``data/government_revenue/candidate_queue.json``'s
#: own block; a queue whose fence is incomplete is refused, not downgraded.
AUTHORITY = {
    "tier": "display",
    "context_only": True,
    "can_rank": False,
    "can_size": False,
    "can_gate": False,
    "can_originate_signal": False,
    "can_add_candidates": False,
    "can_escalate": False,
}

_FORBIDDEN_AUTHORITY_KEYS = (
    "can_rank",
    "can_size",
    "can_gate",
    "can_originate_signal",
    "can_add_candidates",
    "can_escalate",
)

#: Every plan field that carries a Prophet DECISION.  The adapter is proven
#: byte-identical over exactly this projection: membership and order come from
#: the list itself, ``_priority_score`` is the rank the index sorts by,
#: ``_conviction_score``/``_act_level``/``_gate_go`` are confidence and gates,
#: ``tranche``/``_r_unit`` are size, and the geometry plus ``option_contract`` is
#: the execution decision.
PLAN_DECISION_FIELDS = (
    "id",
    "asset",
    "direction",
    "trigger",
    "entry",
    "invalidation",
    "targets",
    "horizon_days",
    "min_hold_days",
    "tranche",
    "option_contract",
    "stage_tilt",
    "_priority_score",
    "_conviction_score",
    "_act_level",
    "_r_unit",
    "_gate_go",
)

#: The single key the adapter is allowed to add to a plan.
ANNOTATION_PLAN_KEY = "government_revenue_annotation"
CONTEXT_ENGINE_NAME = "government_revenue_foresight"

#: Wall-clock ceiling for the whole annotation pass.  Exceeding it degrades
#: annotation COVERAGE (fewer packets), never the plan list.
DEFAULT_TIME_BUDGET_SECONDS = 20.0

LABEL_EN = "shadow context"
LABEL_ZH = "影子背景"


class AnnotationError(ValueError):
    """Raised only by the strict builders; the adapter never propagates it."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _digest(prefix: str, value: Any) -> str:
    return f"{prefix}-{sha256(_canonical_json(value).encode('utf-8')).hexdigest()[:24]}"


def _text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    try:
        if isinstance(value, datetime):
            parsed = value
        else:
            parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def _rows(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [row for row in value if isinstance(row, Mapping)]


def _refs(value: Any, *, limit: int = 12) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return sorted({_text(row) or "" for row in value} - {""})[:limit]


def display_only_authority(value: Any) -> bool:
    """Require the COMPLETE typed fence, not merely the absence of a literal True.

    Same predicate shape as ``federation._display_only_authority``: a queue that
    dropped a key is indistinguishable from one that never had the fence, so a
    partial block fails closed.
    """

    return (
        isinstance(value, Mapping)
        and value.get("tier") == "display"
        and value.get("context_only") is True
        and all(value.get(key) is False for key in _FORBIDDEN_AUTHORITY_KEYS)
    )


# --------------------------------------------------------------------------- #
# reading the queue as data
# --------------------------------------------------------------------------- #


def read_candidate_queue(repo_root: Path | str) -> dict[str, Any] | None:
    """Return the queue payload, or ``None`` for anything not usable.

    Deliberately no import of the queue's builder — see the module docstring.
    """

    path = Path(repo_root) / QUEUE_RELATIVE_PATH
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, Mapping):
        return None
    if _text(payload.get("contract")) != QUEUE_CONTRACT:
        return None
    if not display_only_authority(payload.get("authority")):
        return None
    if not isinstance(payload.get("candidates"), Sequence):
        return None
    return dict(payload)


def _usable_candidate(candidate: Mapping[str, Any]) -> bool:
    """Accept only a candidate that can be traced and is fenced display-only."""

    return (
        _text(candidate.get("contract")) == CANDIDATE_CONTRACT
        and _text(candidate.get("candidate_id")) is not None
        and _text(candidate.get("observation_id")) is not None
        and _text(candidate.get("ticker")) is not None
        and _iso(candidate.get("known_at")) is not None
        and candidate.get("is_neuralweb_trade_candidate") is False
        and display_only_authority(candidate.get("authority"))
    )


# --------------------------------------------------------------------------- #
# the envelope
# --------------------------------------------------------------------------- #


def build_annotation(
    candidate: Mapping[str, Any],
    *,
    queue: Mapping[str, Any],
    shadow_packet: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Build one narrow annotation record for one already-selected candidate.

    Every rendered field traces to a generation the reader can look up: the
    candidate's own ``artifact_content_ids`` and ``observation_id``, the queue's
    ``content_id`` and ``source_generation_ids``, and the packet's ``packet_id``.
    """

    if not _usable_candidate(candidate):
        raise AnnotationError("candidate is not a traceable display-only research candidate")
    event = candidate.get("source_event") if isinstance(candidate.get("source_event"), Mapping) else {}
    issuer = candidate.get("issuer") if isinstance(candidate.get("issuer"), Mapping) else {}
    resolution = (
        candidate.get("issuer_resolution_ref")
        if isinstance(candidate.get("issuer_resolution_ref"), Mapping)
        else {}
    )
    freshness = candidate.get("freshness") if isinstance(candidate.get("freshness"), Mapping) else {}
    coverage = candidate.get("coverage") if isinstance(candidate.get("coverage"), Mapping) else {}
    amount = event.get("amount") if isinstance(event.get("amount"), Mapping) else {}
    contradictions = [
        {
            "contradiction_id": _text(row.get("contradiction_id")),
            "kind": _text(row.get("kind")),
            "legs": _refs(row.get("legs")),
            "handling": _text(row.get("handling")),
            "statement_en": _text(row.get("statement_en")),
            "statement_zh": _text(row.get("statement_zh")),
        }
        for row in _rows((shadow_packet or {}).get("contradictions"))
    ]
    annotation = {
        "contract": CONTRACT,
        "schema_version": SCHEMA_VERSION,
        "candidate_id": _text(candidate.get("candidate_id")),
        "observation_id": _text(candidate.get("observation_id")),
        "candidate_family": _text(candidate.get("candidate_family")),
        "candidate_state": _text(candidate.get("candidate_state")),
        "ticker": _text(candidate.get("ticker")),
        "issuer": {
            "company_name": _text(issuer.get("company_name")),
            "ticker": _text(issuer.get("ticker")) or _text(candidate.get("ticker")),
            "issuer_company_id": _text(candidate.get("issuer_company_id")),
            "relation_semantic": _text(resolution.get("relation_semantic")),
            "resolution_state": _text(resolution.get("resolution_state")),
            "graph_id": _text(resolution.get("graph_id")),
            "graph_digest": _text(resolution.get("graph_digest")),
        },
        "procurement_event": {
            "event_id": _text(event.get("event_id")),
            "record_id": _text(event.get("record_id")),
            "event_type": _text(event.get("event_type")),
            "source_rail": _text(event.get("source_rail")),
            "effective_at": _iso(event.get("effective_at")),
            "known_at": _iso(event.get("known_at")),
            "amount_id": _text(amount.get("id")),
            "amount_value": _finite(amount.get("value")),
            "amount_units": _text(amount.get("units")) or "usd",
            "transmission_direction": _text(candidate.get("transmission_direction")),
        },
        "evidence_refs": {
            "artifact_content_ids": _refs(candidate.get("artifact_content_ids")),
            "event_refs": _refs(candidate.get("event_refs")),
            "ownership_path_refs": _refs(candidate.get("ownership_path_refs")),
            "resolution_evidence_refs": _refs(resolution.get("evidence_refs")),
            "receipt_refs": sorted({
                _text(row.get("ref_id")) or "" for row in _rows(candidate.get("source_receipt_refs"))
            } - {""})[:12],
        },
        "generation": {
            "queue_content_id": _text(queue.get("content_id")),
            "queue_known_at": _iso(queue.get("known_at")),
            "queue_as_of": _iso(queue.get("as_of")),
            "queue_source_generation_ids": _refs(queue.get("source_generation_ids")),
            "queue_source_content_ids": _refs(queue.get("source_content_ids")),
            "shadow_packet_id": _text((shadow_packet or {}).get("packet_id")),
        },
        "known_at": _iso(candidate.get("known_at")),
        "freshness": {
            "status": _text(freshness.get("status")) or "unknown",
            "award_events_status": _text(freshness.get("award_events_status")) or "unknown",
            "recipient_graph_status": _text(freshness.get("recipient_graph_status")) or "unknown",
            "event_known_at": _iso(freshness.get("event_known_at")),
            "graph_known_at": _iso(freshness.get("graph_known_at")),
        },
        "coverage": {
            "scope": _text(coverage.get("scope")),
            "exact_link_status": _text(coverage.get("exact_link_status")),
            "is_complete": bool(coverage.get("is_complete")),
            "shadow_leg_names": [
                _text(leg.get("name")) for leg in _rows((shadow_packet or {}).get("legs"))
            ],
            "shadow_present_leg_names": [
                _text(leg.get("name"))
                for leg in _rows((shadow_packet or {}).get("legs"))
                if _text(leg.get("status")) == "present"
            ],
        },
        "contradictions": contradictions,
        "shadow_context": dict(shadow_packet) if isinstance(shadow_packet, Mapping) else None,
        "label": {"en": LABEL_EN, "zh": LABEL_ZH},
        "allowed_behavior": "annotate_only",
        "authority": dict(AUTHORITY),
        "limitations": [
            "Government Revenue annotation is display/context only; Prophet alone selects, ranks, sizes, gates, and executes.",
            "Observed award amounts are not recognized revenue and do not establish revenue timing or margin impact.",
            "Readings that disagree are shown side by side and are never averaged into one figure.",
        ],
    }
    annotation["annotation_id"] = _digest("grpa1", {
        "candidate_id": annotation["candidate_id"],
        "observation_id": annotation["observation_id"],
        "queue_content_id": annotation["generation"]["queue_content_id"],
        "shadow_packet_id": annotation["generation"]["shadow_packet_id"],
    })
    return annotation


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def build_annotation_envelope(
    queue: Mapping[str, Any],
    *,
    selected_tickers: Iterable[str],
    generated_at: str,
    packet_builder: Callable[[Mapping[str, Any]], Mapping[str, Any] | None] | None = None,
    time_budget_seconds: float = DEFAULT_TIME_BUDGET_SECONDS,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Build the annotation envelope for the names Prophet ALREADY selected.

    ``selected_tickers`` is the post-selection universe and is the only reason a
    candidate is looked at.  A candidate for a name Prophet did not pick is
    skipped — govrev cannot push a name in, so an annotation with no plan to sit
    on has nowhere to go.

    A candidate whose packet cannot be built still gets an annotation, with
    ``shadow_context`` null and the reason named: the procurement evidence is
    independently useful and does not depend on the market legs.
    """

    generated = _iso(generated_at)
    if generated is None:
        raise AnnotationError("generated_at must be parseable")
    wanted = {
        symbol for symbol in (_text(row) for row in selected_tickers) if symbol
    }
    wanted = {symbol.upper() for symbol in wanted}
    started = clock()
    annotations: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    budget_exhausted = False
    for candidate in _rows(queue.get("candidates")):
        ticker = (_text(candidate.get("ticker")) or "").upper()
        if not ticker or ticker not in wanted:
            continue
        if not _usable_candidate(candidate):
            skipped.append({
                "candidate_id": _text(candidate.get("candidate_id")),
                "reason_code": "candidate_not_traceable_or_not_display_only",
            })
            continue
        packet: Mapping[str, Any] | None = None
        packet_reason: str | None = None
        if packet_builder is None:
            packet_reason = "no_shadow_packet_builder_supplied"
        elif budget_exhausted or (clock() - started) > time_budget_seconds:
            budget_exhausted = True
            packet_reason = "shadow_packet_time_budget_exhausted"
        else:
            try:
                candidate_packet = packet_builder(candidate)
            except Exception:  # noqa: BLE001 — a failed packet must not cost the annotation
                packet_reason = "shadow_packet_builder_failed"
            else:
                if isinstance(candidate_packet, Mapping) and candidate_packet:
                    packet = candidate_packet
                else:
                    packet_reason = "shadow_packet_builder_returned_no_packet"
        try:
            annotation = build_annotation(candidate, queue=queue, shadow_packet=packet)
        except AnnotationError:
            skipped.append({
                "candidate_id": _text(candidate.get("candidate_id")),
                "reason_code": "annotation_construction_refused",
            })
            continue
        annotation["shadow_context_reason_code"] = packet_reason
        annotations.append(annotation)
    return {
        "contract": CONTRACT,
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated,
        "annotations": annotations,
        "skipped": skipped,
        "coverage": {
            "selected_ticker_count": len(wanted),
            "annotated_candidate_count": len(annotations),
            "skipped_candidate_count": len(skipped),
            "shadow_packet_budget_exhausted": budget_exhausted,
            "is_complete": False,
        },
        "authority": dict(AUTHORITY),
        "limitations": [
            "This envelope annotates plans Prophet already selected; it cannot add, remove, reorder, or re-price one.",
            "A candidate whose ticker Prophet did not select is never annotated and never delivered.",
        ],
    }


# --------------------------------------------------------------------------- #
# the post-selection adapter
# --------------------------------------------------------------------------- #


def decision_fingerprint(plans: Sequence[Mapping[str, Any]]) -> str:
    """Hash exactly the Prophet decision: membership, order, and every gate field.

    This is the byte-identity proof in one value.  Order is preserved (the list
    IS the rank), so a reordered list fingerprints differently even when every
    plan is untouched.
    """

    return sha256(
        _canonical_json([
            {field: plan.get(field) for field in PLAN_DECISION_FIELDS}
            for plan in plans
            if isinstance(plan, Mapping)
        ]).encode("utf-8")
    ).hexdigest()


def annotate_selected_plans(
    plans: Sequence[Mapping[str, Any]],
    envelope: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    """Attach annotations to already-selected plans.  Fails open in every case.

    Returns a new list of new dicts in the SAME order, with at most one added
    key per plan.  The decision fingerprint is recomputed afterwards and the
    whole annotation pass is discarded if it moved — a runtime enforcement of
    the same gate the suite asserts, so a future edit that silently touches a
    decision field degrades to "no annotation" instead of shipping.
    """

    original = [dict(plan) for plan in plans if isinstance(plan, Mapping)]
    try:
        if not isinstance(envelope, Mapping):
            return original
        if _text(envelope.get("contract")) != CONTRACT:
            return original
        if not display_only_authority(envelope.get("authority")):
            return original
        by_ticker: dict[str, list[dict[str, Any]]] = {}
        for annotation in _rows(envelope.get("annotations")):
            if _text(annotation.get("contract")) != CONTRACT:
                continue
            if not display_only_authority(annotation.get("authority")):
                continue
            ticker = (_text(annotation.get("ticker")) or "").upper()
            if not ticker:
                continue
            by_ticker.setdefault(ticker, []).append(dict(annotation))
        if not by_ticker:
            return original
        annotated: list[dict[str, Any]] = []
        for plan in original:
            row = dict(plan)
            asset = (_text(row.get("asset")) or "").upper()
            matches = by_ticker.get(asset)
            if matches:
                row[ANNOTATION_PLAN_KEY] = {
                    "contract": CONTRACT,
                    "schema_version": SCHEMA_VERSION,
                    "label": {"en": LABEL_EN, "zh": LABEL_ZH},
                    "allowed_behavior": "annotate_only",
                    "authority": dict(AUTHORITY),
                    "annotations": matches,
                }
                engines = row.get("context_engines")
                engines = list(engines) if isinstance(engines, list) else []
                if CONTEXT_ENGINE_NAME not in engines:
                    engines.append(CONTEXT_ENGINE_NAME)
                row["context_engines"] = engines
            annotated.append(row)
        if decision_fingerprint(annotated) != decision_fingerprint(original):
            # Unreachable by construction; kept because "unreachable" is exactly
            # what every shipped regression was believed to be.
            return original
        return annotated
    except Exception:  # noqa: BLE001 — annotation never costs Prophet its decision
        return original


def annotate_plans_from_repo(
    plans: Sequence[Mapping[str, Any]],
    *,
    repo_root: Path | str,
    generated_at: str,
    packet_builder: Callable[[Mapping[str, Any]], Mapping[str, Any] | None] | None = None,
    time_budget_seconds: float = DEFAULT_TIME_BUDGET_SECONDS,
) -> list[dict[str, Any]]:
    """Read the queue, build the envelope, annotate.  One fail-open entry point.

    This is the seam a caller wires: it derives the selected universe FROM the
    finished plan list, so there is no path by which govrev influences which
    names are in it.
    """

    original = [dict(plan) for plan in plans if isinstance(plan, Mapping)]
    if not original:
        return original
    try:
        queue = read_candidate_queue(repo_root)
        if queue is None:
            return original
        envelope = build_annotation_envelope(
            queue,
            selected_tickers=[str(plan.get("asset") or "") for plan in original],
            generated_at=generated_at,
            packet_builder=packet_builder,
            time_budget_seconds=time_budget_seconds,
        )
    except Exception:  # noqa: BLE001
        return original
    return annotate_selected_plans(original, envelope)


__all__ = [
    "ANNOTATION_PLAN_KEY",
    "AUTHORITY",
    "CANDIDATE_CONTRACT",
    "CONTEXT_ENGINE_NAME",
    "CONTRACT",
    "DEFAULT_TIME_BUDGET_SECONDS",
    "PLAN_DECISION_FIELDS",
    "QUEUE_CONTRACT",
    "QUEUE_RELATIVE_PATH",
    "SCHEMA_VERSION",
    "AnnotationError",
    "annotate_plans_from_repo",
    "annotate_selected_plans",
    "build_annotation",
    "build_annotation_envelope",
    "decision_fingerprint",
    "display_only_authority",
    "read_candidate_queue",
]
