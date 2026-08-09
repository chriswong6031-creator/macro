"""SBIR Phase I → Phase II progression *evidence* projection.

This module answers exactly one question: for the bounded SBIR.gov observations
the collector has accrued, where do we see a Phase I award and a later Phase II
award under the same exact firm/agency/program key?

What that is **not**, and what this projection refuses to imply:

* it is not production conversion.  SBIR.gov publishes no parent/child link
  between a Phase I and a Phase II award, so a shared key is co-occurrence, not
  lineage — and even proven lineage would not be a production award.  Naming
  phase movement a production conversion requires an exact production award
  chain, which this rail does not have;
* it is not revenue, backlog, funded backlog, bookings, obligation, or outlay;
* it is not issuer attribution.  A listed-company link is asserted only from an
  **exact UEI** match against the reviewed recipient graph.  A firm-name
  agreement is retained as mapping-backlog context and never as attribution;
* it is not a candidate source.  The candidate family is not preregistered, so
  this rail emits zero candidates and zero forward events regardless of how
  suggestive a pairing looks.

The projection is point-in-time: only observations whose ``known_at`` is at or
before the analysis cutoff are visible, so a later observation can never leak
backwards into an earlier reading.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

import pandas as pd

from collectors.sbir_awards import (
    PROGRESSION_LIMITATION,
    SBIR_COLLECTION_RECEIPTS_FILENAME,
    SBIR_INGEST_STATUS_FILENAME,
    SBIR_OBSERVATION_COLUMNS,
    SBIR_OBSERVATIONS_FILENAME,
    SBIR_PROJECTION_STATE_FILENAME,
    SBIR_PROJECTION_STATE_SCHEMA,
    SBIR_AWARDS_URL,
    sbir_projection_generation_matches,
)
from engine.government_revenue.entity_resolution import (
    load_recipient_entity_graph,
    resolve_recipient,
)

SBIR_PROGRESSION_CONTRACT = "government_revenue_sbir_progression.v1"
SBIR_PROGRESSION_SCHEMA_VERSION = "1.0.0"
SBIR_PROGRESSION_FILENAME = "sbir_progression.json"
RECIPIENT_ENTITY_GRAPH_FILENAME = "recipient_entity_graph.json"

CONTENT_ID_PREFIX = "grsp1-"
EVIDENCE_ID_PREFIX = "grspe1-"
BACKLOG_ID_PREFIX = "grspb1-"

MAX_PROGRESSION_ROWS = 500
MAX_MAPPING_BACKLOG_ROWS = 500

AUTHORITY: dict[str, Any] = {
    "tier": "display",
    "context_only": True,
    "can_rank": False,
    "can_size": False,
    "can_gate": False,
    "can_originate_signal": False,
    "can_add_candidates": False,
    "can_escalate": False,
}

# Only an exact UEI match may assert a listed issuer on this rail.  The resolver
# ladder also offers CAGE and a USAspending recipient id; SBIR.gov publishes
# neither, so anything other than ``exact_uei`` here would mean the rule fired
# on a field this source does not have.
EXACT_ISSUER_JOIN_RULE = "exact_uei"
ATTRIBUTED_RESOLUTION_STATES = frozenset({"confirmed", "reviewed"})

PRODUCTION_CONVERSION_LIMITATION = (
    "Phase movement is never production conversion. An exact production award chain is "
    "required before any conversion language, and this rail has none."
)
LIMITATIONS = (
    PROGRESSION_LIMITATION,
    PRODUCTION_CONVERSION_LIMITATION,
    "Listed-company links come only from an exact UEI match against the reviewed recipient "
    "graph; a matching firm name is mapping-backlog context and never attribution.",
    "SBIR award amounts are program award values and are never revenue, backlog, funded "
    "backlog, bookings, obligations, or outlays.",
    "Coverage is a bounded agency/year sample of SBIR.gov, never the full SBIR/STTR corpus; "
    "the absence of an award is not evidence that no award exists.",
    "This rail cannot originate, rank, size, gate, or escalate a signal, and emits no "
    "candidates until a candidate family is preregistered and prospectively gradeable.",
)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _text(value: Any) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return text if text and text.lower() not in {"none", "nan", "nat", "null"} else None


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if pd.notna(result) and result not in {float("inf"), float("-inf")} else None


def _timestamp(value: Any) -> pd.Timestamp | None:
    text = _text(value)
    if text is None:
        return None
    try:
        stamp = pd.Timestamp(text)
    except (TypeError, ValueError):
        return None
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize("UTC")
    return stamp.tz_convert("UTC")


def _instant(value: Any) -> str | None:
    stamp = _timestamp(value)
    return None if stamp is None else stamp.isoformat()


def sbir_progression_content_id(payload: Mapping[str, Any]) -> str | None:
    """Return the content-addressed ID for an otherwise complete payload."""
    if not isinstance(payload, Mapping):
        return None
    fingerprint = {key: value for key, value in payload.items() if key != "content_id"}
    return CONTENT_ID_PREFIX + _sha256_json(fingerprint)[:24]


def progression_key(row: Mapping[str, Any]) -> tuple[str, str, dict[str, Any]] | None:
    """Return the exact grouping key for one observation, or nothing.

    The key is built only from exact source values and always requires a
    well-formed UEI: without one there is no exact identity to group on, and
    grouping by firm name would be the fuzzy join this desk forbids.  Branch and
    topic code sharpen the key when present, and the key *kind* records which
    fields participated so a coarser grouping can never be read as a sharper one.
    """
    uei = _text(row.get("uei"))
    agency = _text(row.get("agency"))
    program = _text(row.get("program"))
    if uei is None or agency is None or program is None:
        return None
    branch = _text(row.get("branch"))
    topic_code = _text(row.get("topic_code"))
    fields: dict[str, Any] = {
        "uei": uei.upper(),
        "agency": agency.upper(),
        "program": program.upper(),
    }
    kind_parts = ["uei", "agency", "program"]
    if branch is not None:
        fields["branch"] = branch.upper()
        kind_parts.append("branch")
    if topic_code is not None:
        fields["topic_code"] = topic_code.upper()
        kind_parts.append("topic")
    kind = "_".join(kind_parts)
    digest = _sha256_json({"kind": kind, "fields": fields})
    return digest, kind, fields


def latest_visible_observations(
    frame: pd.DataFrame,
    *,
    as_of: str | pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Return the latest semantic version per award key knowable at ``as_of``.

    The ledger is append-only and may hold several versions of one award.  A
    projection must read the newest version that was *already known* at the
    cutoff — never the newest row on disk, which would leak a later correction
    backwards into an earlier reading.
    """
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame(columns=SBIR_OBSERVATION_COLUMNS)
    working = frame.reindex(columns=SBIR_OBSERVATION_COLUMNS).copy()
    working["__known"] = working["known_at"].map(_timestamp)
    working = working[working["__known"].notna()]
    cutoff = _timestamp(as_of)
    if cutoff is not None:
        working = working[working["__known"] <= cutoff]
    if working.empty:
        return pd.DataFrame(columns=SBIR_OBSERVATION_COLUMNS)
    working["__key"] = working["sbir_award_key"].map(_text)
    working = working[working["__key"].notna()]
    working = working.sort_values(["__key", "__known"], kind="mergesort")
    latest = working.drop_duplicates(subset=["__key"], keep="last")
    return latest.drop(columns=["__known", "__key"]).reset_index(drop=True)


def _leg(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "sbir_award_key": _text(row.get("sbir_award_key")),
        "phase": _text(row.get("phase")),
        "phase_source_value": _text(row.get("phase_source_value")),
        "contract": _text(row.get("contract")),
        "award_amount": _number(row.get("award_amount")),
        "award_year": _text(row.get("award_year")),
        "solicitation_number": _text(row.get("solicitation_number")),
        "source_at": _text(row.get("source_at")),
        "effective_at": _text(row.get("effective_at")),
        "contract_end_date": _text(row.get("contract_end_date")),
        "observed_at": _instant(row.get("observed_at")),
        "known_at": _instant(row.get("known_at")),
        "first_seen_at": _instant(row.get("first_seen_at")),
        "award_link": _text(row.get("award_link")),
        "source_receipt_id": _text(row.get("source_receipt_id")),
        "source_response_sha256": _text(row.get("source_response_sha256")),
    }


def _issuer_link(
    row: Mapping[str, Any],
    graph: Any,
    *,
    as_of: str | None,
) -> dict[str, Any]:
    """Resolve one observation to a listed issuer through an exact UEI only.

    The resolver is handed the UEI and both clocks and *not* asked to consider a
    name.  Even when it answers, this function re-checks that the rule that fired
    was the exact-UEI rule: a future ladder addition must not silently widen what
    counts as attribution on a source that publishes no other exact identifier.
    """
    uei = _text(row.get("uei"))
    record = {
        "source_record_key": f"sbir:{_text(row.get('sbir_award_key'))}",
        "source_record_identity_stable": True,
        "recipient_name": _text(row.get("firm")),
        "effective_at": _text(row.get("effective_at")),
        "known_at": _instant(row.get("known_at")),
    }
    if uei is not None:
        record["recipient_uei"] = uei.upper()
    resolution = resolve_recipient(record, graph, as_of=as_of)
    state = _text(resolution.get("resolution_state"))
    rule = _text(resolution.get("resolution_rule"))
    issuer = resolution.get("issuer")
    attributed = bool(
        uei is not None
        and rule == EXACT_ISSUER_JOIN_RULE
        and state in ATTRIBUTED_RESOLUTION_STATES
        and isinstance(issuer, dict)
        and _text(issuer.get("ticker"))
    )
    return {
        "issuer_attribution": "exact_identifier" if attributed else "not_asserted",
        "issuer_join_rule": rule if attributed else "none",
        "ticker": _text(issuer.get("ticker")) if attributed else None,
        "company_id": _text(issuer.get("company_id")) if attributed else None,
        "recipient_entity_id": (
            _text(resolution.get("recipient_entity_id")) if attributed else None
        ),
        "economic_share": resolution.get("economic_share") if attributed else None,
        "resolution_state": state,
        "resolution_reason_codes": list(resolution.get("reason_codes") or []),
        "evidence_refs": list(resolution.get("evidence_refs") or []),
        "uei_present": uei is not None,
        "name_association_is_attribution": False,
    }


def build_progression_evidence(
    observations: pd.DataFrame,
    graph: Any = None,
    *,
    as_of: str | None = None,
) -> list[dict[str, Any]]:
    """Pair the earliest Phase I with the earliest strictly later Phase II per key.

    One row per exact key keeps the payload bounded and reviewable.  Additional
    phase observations under the same key are counted rather than dropped, so a
    reader can see that the pair shown is not the whole story.
    """
    visible = observations if isinstance(observations, pd.DataFrame) else pd.DataFrame()
    if visible.empty:
        return []
    grouped: dict[str, dict[str, Any]] = {}
    for _, row in visible.iterrows():
        keyed = progression_key(row)
        if keyed is None:
            continue
        digest, kind, fields = keyed
        bucket = grouped.setdefault(
            digest,
            {"kind": kind, "fields": fields, "I": [], "II": []},
        )
        phase = _text(row.get("phase"))
        if phase in {"I", "II"}:
            bucket[phase].append(dict(row))

    evidence: list[dict[str, Any]] = []
    for digest in sorted(grouped):
        bucket = grouped[digest]
        phase_i = [row for row in bucket["I"] if _text(row.get("effective_at"))]
        phase_ii = [row for row in bucket["II"] if _text(row.get("effective_at"))]
        if not phase_i or not phase_ii:
            continue
        phase_i.sort(key=lambda row: str(row.get("effective_at")))
        first_i = phase_i[0]
        later_ii = sorted(
            (
                row
                for row in phase_ii
                if str(row.get("effective_at")) > str(first_i.get("effective_at"))
            ),
            key=lambda row: str(row.get("effective_at")),
        )
        if not later_ii:
            continue
        first_ii = later_ii[0]
        leg_i = _leg(first_i)
        leg_ii = _leg(first_ii)
        known_candidates = [value for value in (leg_i["known_at"], leg_ii["known_at"]) if value]
        # The pair becomes knowable only when its *later-observed* leg was
        # observed; taking the earlier clock would claim we knew the progression
        # before we could have seen both halves of it.
        known_at = max(known_candidates) if known_candidates else None
        start_i = _timestamp(leg_i["effective_at"])
        start_ii = _timestamp(leg_ii["effective_at"])
        days_between = (
            int((start_ii - start_i).days) if start_i is not None and start_ii is not None else None
        )
        link = _issuer_link(first_ii, graph, as_of=as_of)
        row_payload = {
            "progression_key_sha256": digest,
            "progression_key_kind": bucket["kind"],
            "key_fields": bucket["fields"],
            "firm_name_context": _text(first_ii.get("firm")),
            "agency": bucket["fields"].get("agency"),
            "branch": bucket["fields"].get("branch"),
            "program": bucket["fields"].get("program"),
            "topic_code": bucket["fields"].get("topic_code"),
            "phase_i": leg_i,
            "phase_ii": leg_ii,
            "phase_i_observations_under_key": len(bucket["I"]),
            "phase_ii_observations_under_key": len(bucket["II"]),
            "days_between_award_starts": days_between,
            "known_at": known_at,
            "evidence_kind": "phase_i_to_phase_ii_observed",
            "source_publishes_phase_lineage": False,
            "is_production_conversion": False,
            "production_award_chain": "absent",
            "issuer_link": link,
            "limitations": list(LIMITATIONS),
        }
        row_payload["evidence_id"] = EVIDENCE_ID_PREFIX + _sha256_json(row_payload)[:24]
        evidence.append(row_payload)
    evidence.sort(key=lambda row: (str(row.get("known_at") or ""), row["evidence_id"]))
    return evidence[:MAX_PROGRESSION_ROWS]


def build_mapping_backlog(
    observations: pd.DataFrame,
    graph: Any = None,
    *,
    as_of: str | None = None,
) -> list[dict[str, Any]]:
    """List firms that carry no exact-identifier issuer link, as backlog only.

    A backlog row is a request for review, not a claim.  It carries the firm name
    the source published so a human can map it, and states in the row itself that
    the name is not attribution.
    """
    visible = observations if isinstance(observations, pd.DataFrame) else pd.DataFrame()
    if visible.empty:
        return []
    backlog: dict[str, dict[str, Any]] = {}
    for _, row in visible.iterrows():
        link = _issuer_link(row, graph, as_of=as_of)
        if link["issuer_attribution"] == "exact_identifier":
            continue
        firm = _text(row.get("firm"))
        uei = _text(row.get("uei"))
        identity = (uei or firm or "").upper()
        if not identity:
            continue
        entry = backlog.setdefault(identity, {
            "company_name": firm,
            "uei": uei.upper() if uei else None,
            "mapping_state": "mapping_needed",
            "issuer_attribution": "not_asserted",
            "source_association_method": "source_published_firm_name",
            "observation_count": 0,
            "known_at": None,
            "reason_codes": sorted(set(link["resolution_reason_codes"])) or ["unclassified"],
            "limitations": [
                "Firm-name association is retained only as mapping backlog and is not issuer "
                "attribution.",
                "An exact UEI plus a time-valid reviewed ownership path is required before a "
                "listed-company link is asserted.",
            ],
        })
        entry["observation_count"] += 1
        known_at = _instant(row.get("known_at"))
        if known_at and (entry["known_at"] is None or known_at > entry["known_at"]):
            entry["known_at"] = known_at
    rows = []
    for identity in sorted(backlog):
        entry = backlog[identity]
        entry["backlog_id"] = BACKLOG_ID_PREFIX + _sha256_json(entry)[:24]
        rows.append(entry)
    rows.sort(key=lambda row: row["backlog_id"])
    return rows[:MAX_MAPPING_BACKLOG_ROWS]


def _unavailable_payload(*, as_of: str | None, reason: str) -> dict[str, Any]:
    """Return the designed unavailable envelope, never a synthesized empty rail."""
    payload: dict[str, Any] = {
        "schema_version": SBIR_PROGRESSION_SCHEMA_VERSION,
        "contract": SBIR_PROGRESSION_CONTRACT,
        "as_of": as_of,
        "known_at": None,
        "authority": dict(AUTHORITY),
        "source": {
            "publisher": "U.S. Small Business Administration, SBIR.gov",
            "official_api_urls": [SBIR_AWARDS_URL],
        },
        "availability": {"state": "unavailable", "reason": reason},
        "baseline": {
            "state": "no_bundle",
            "history_synthesized": False,
            "emits_forward_events": False,
            "disclosure": (
                "No SBIR observation bundle is available in this checkout, so no progression "
                "evidence is shown. This is an absent source, not an absence of awards."
            ),
        },
        "candidate_impact": {
            "emits_candidates": False,
            "candidate_family_preregistered": False,
            "authority": dict(AUTHORITY),
        },
        "coverage": {
            "is_complete": False,
            "full_sbir_corpus": False,
            "observations_visible": 0,
            "progression_pairs": 0,
            "mapping_backlog_count": 0,
        },
        "phase_observations": {"phase_i": 0, "phase_ii": 0, "unrecognized_phase": 0},
        "progression_evidence": [],
        "forward_events": [],
        "forward_events_emitted": 0,
        "mapping_backlog": [],
        "exact_identity": {"exact_linked": 0, "mapping_needed": 0},
        "limitations": list(LIMITATIONS),
    }
    payload["content_id"] = sbir_progression_content_id(payload)
    return payload


def build_sbir_progression_payload(
    *,
    root: Path | str | None = None,
    as_of: str | None = None,
) -> dict[str, Any]:
    """Project the accrued SBIR bundle into progression evidence.

    An absent bundle yields the explicit unavailable envelope.  A *partial*
    bundle is a hard failure: the activation state and the ledger it binds are
    one unit, and projecting whichever half exists is how a torn generation gets
    blessed.
    """
    base = Path(root).resolve() if root is not None else Path.cwd().resolve()
    data_dir = base / "data" / "government_revenue"
    observation_path = data_dir / SBIR_OBSERVATIONS_FILENAME
    state_path = data_dir / SBIR_PROJECTION_STATE_FILENAME
    status_path = data_dir / SBIR_INGEST_STATUS_FILENAME

    present = [observation_path.exists(), state_path.exists(), status_path.exists()]
    if not any(present):
        return _unavailable_payload(as_of=as_of, reason="sbir_observation_bundle_absent")
    if not all(present):
        raise ValueError(
            "SBIR observation bundle is partial; the ledger, activation state, and ingest "
            "status are one unit and all are required"
        )

    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        status = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("SBIR projection state or ingest status is unavailable or invalid") from exc
    if not isinstance(state, dict) or not isinstance(status, dict):
        raise ValueError("SBIR projection state and ingest status must be objects")
    if state.get("contract") != SBIR_PROJECTION_STATE_SCHEMA:
        raise ValueError("SBIR projection state carries an unknown contract")

    observations = pd.read_parquet(observation_path).reindex(columns=SBIR_OBSERVATION_COLUMNS)
    if not sbir_projection_generation_matches(state, observations):
        raise ValueError(
            "SBIR activation state does not bind the observation ledger on disk; refusing to "
            "project a torn generation"
        )

    cutoff = as_of or _text(state.get("observed_at"))
    visible = latest_visible_observations(observations, as_of=cutoff)

    graph_path = data_dir / RECIPIENT_ENTITY_GRAPH_FILENAME
    graph_input: Any = None
    graph_status = "absent"
    if graph_path.exists():
        try:
            graph_value = json.loads(graph_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            # Preserve unreadable as distinct from absent at the strict loader
            # boundary: a non-mapping is rejected rather than treated as "no graph".
            graph_input = []
            graph_status = "invalid"
        else:
            graph_input = graph_value if isinstance(graph_value, dict) else []
            graph_status = "ready" if isinstance(graph_value, dict) else "invalid"
    graph = load_recipient_entity_graph(graph_input, as_of=cutoff)

    evidence = build_progression_evidence(visible, graph, as_of=cutoff)
    backlog = build_mapping_backlog(visible, graph, as_of=cutoff)
    exact_linked = sum(
        1
        for row in evidence
        if row["issuer_link"]["issuer_attribution"] == "exact_identifier"
    )

    first_baseline = bool(state.get("first_baseline"))
    known_clocks = [
        value
        for value in (_instant(row.get("known_at")) for _, row in visible.iterrows())
        if value
    ]
    payload: dict[str, Any] = {
        "schema_version": SBIR_PROGRESSION_SCHEMA_VERSION,
        "contract": SBIR_PROGRESSION_CONTRACT,
        "as_of": cutoff,
        "known_at": max(known_clocks) if known_clocks else None,
        "first_observed_at": min(known_clocks) if known_clocks else None,
        "authority": dict(AUTHORITY),
        "source": {
            "publisher": "U.S. Small Business Administration, SBIR.gov",
            "official_api_urls": [SBIR_AWARDS_URL],
            "receipt_ledger": SBIR_COLLECTION_RECEIPTS_FILENAME,
        },
        "availability": {"state": "ready", "reason": "sbir_observation_bundle_ready"},
        "generation": {
            "projection_generation_id": _text(state.get("projection_generation_id")),
            "coverage_manifest_id": _text(state.get("coverage_manifest_id")),
            "collector_observed_at": _instant(state.get("observed_at")),
            "collector_status": _text(status.get("status")),
        },
        "baseline": {
            # A first baseline holds source-dated history but only one knowledge
            # generation.  It may show what the source said; it may not present
            # any of it as a forward event we graded over time.
            "state": "first_baseline" if first_baseline else "accrued",
            "history_synthesized": False,
            "emits_forward_events": False,
            "disclosure": (
                "First baseline: every observation became knowable in one collection, so no "
                "forward event has been graded yet. Source-dated award history is shown as the "
                "source published it and is never backfilled as prior knowledge."
                if first_baseline
                else "Accrued baseline: observations span more than one collection generation. "
                "Forward events remain unemitted until a candidate family is preregistered."
            ),
        },
        "candidate_impact": {
            "emits_candidates": False,
            "candidate_family_preregistered": False,
            "authority": dict(AUTHORITY),
        },
        "coverage": {
            "is_complete": False,
            "full_sbir_corpus": False,
            "observations_total": int(len(observations)),
            "observations_visible": int(len(visible)),
            "progression_pairs": len(evidence),
            "mapping_backlog_count": len(backlog),
            "recipient_graph_status": graph_status,
            "coverage_manifest": state.get("coverage_manifest"),
            "bounded_sample_claim": (
                (status.get("completeness") or {}).get("claim")
                if isinstance(status.get("completeness"), dict)
                else None
            ),
            "pagination_metadata_available": False,
            "progression_rows_capped_at": MAX_PROGRESSION_ROWS,
            "mapping_backlog_rows_capped_at": MAX_MAPPING_BACKLOG_ROWS,
        },
        "phase_observations": {
            "phase_i": int(sum(1 for _, row in visible.iterrows() if _text(row.get("phase")) == "I")),
            "phase_ii": int(
                sum(1 for _, row in visible.iterrows() if _text(row.get("phase")) == "II")
            ),
            "unrecognized_phase": int(
                sum(1 for _, row in visible.iterrows() if _text(row.get("phase")) is None)
            ),
        },
        "progression_evidence": evidence,
        "forward_events": [],
        "forward_events_emitted": 0,
        "mapping_backlog": backlog,
        "exact_identity": {
            "exact_linked": int(exact_linked),
            "mapping_needed": len(backlog),
            "join_rule": EXACT_ISSUER_JOIN_RULE,
            "name_association_is_attribution": False,
        },
        "limitations": list(LIMITATIONS),
    }
    payload["content_id"] = sbir_progression_content_id(payload)
    return payload


def is_valid_sbir_progression_payload(payload: Any) -> bool:
    """Validate the invariants a reader is allowed to rely on.

    Every check here is a published promise: authority stays display-only, the
    rail never emits candidates or forward events, and no progression row ever
    claims a production conversion.
    """
    if not isinstance(payload, Mapping):
        return False
    if payload.get("contract") != SBIR_PROGRESSION_CONTRACT:
        return False
    if payload.get("schema_version") != SBIR_PROGRESSION_SCHEMA_VERSION:
        return False
    if payload.get("authority") != AUTHORITY:
        return False
    candidate_impact = payload.get("candidate_impact")
    if (
        not isinstance(candidate_impact, Mapping)
        or candidate_impact.get("emits_candidates") is not False
        or candidate_impact.get("candidate_family_preregistered") is not False
        or candidate_impact.get("authority") != AUTHORITY
    ):
        return False
    baseline = payload.get("baseline")
    if (
        not isinstance(baseline, Mapping)
        or baseline.get("history_synthesized") is not False
        or baseline.get("emits_forward_events") is not False
    ):
        return False
    if payload.get("forward_events") != [] or payload.get("forward_events_emitted") != 0:
        return False
    coverage = payload.get("coverage")
    if (
        not isinstance(coverage, Mapping)
        or coverage.get("is_complete") is not False
        or coverage.get("full_sbir_corpus") is not False
    ):
        return False
    evidence = payload.get("progression_evidence")
    if not isinstance(evidence, list) or len(evidence) > MAX_PROGRESSION_ROWS:
        return False
    for row in evidence:
        if not isinstance(row, Mapping):
            return False
        if row.get("is_production_conversion") is not False:
            return False
        if row.get("production_award_chain") != "absent":
            return False
        if row.get("source_publishes_phase_lineage") is not False:
            return False
        link = row.get("issuer_link")
        if not isinstance(link, Mapping):
            return False
        if link.get("name_association_is_attribution") is not False:
            return False
        if link.get("issuer_attribution") not in {"exact_identifier", "not_asserted"}:
            return False
        if link.get("issuer_attribution") == "exact_identifier" and (
            link.get("issuer_join_rule") != EXACT_ISSUER_JOIN_RULE
            or not _text(link.get("ticker"))
        ):
            return False
        if link.get("issuer_attribution") == "not_asserted" and _text(link.get("ticker")):
            return False
    backlog = payload.get("mapping_backlog")
    if not isinstance(backlog, list) or len(backlog) > MAX_MAPPING_BACKLOG_ROWS:
        return False
    for row in backlog:
        if not isinstance(row, Mapping) or row.get("issuer_attribution") != "not_asserted":
            return False
    return sbir_progression_content_id(payload) == payload.get("content_id")


def progression_limitations() -> tuple[str, ...]:
    """Expose the published limitation strings for reuse by callers."""
    return tuple(LIMITATIONS)


def iter_progression_evidence(payload: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    rows = payload.get("progression_evidence") if isinstance(payload, Mapping) else None
    return list(rows) if isinstance(rows, list) else []
