"""Canonical Q&A adapter for event_workspace.v1.

Deterministic reconstruction is the only producer. This module converts the
E3-A2 structural intermediate into closed ``qa_exchange.v1`` objects, validates
them, and refuses model, topic, or ticker authority.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from .contracts import canonical_json_sha256
from .documents import text_span
from .event_workspace import WorkspaceError
from .qa_reconstruction import SCHEMA as RECONSTRUCTION_SCHEMA
from .qa_reconstruction import reconstruct_qa

# Frozen qa_topic.v1 identity. Copied, not imported from e3_shadow_compiler,
# so the production adapter does not pull gold/eval/launchd into its import graph.
TAXONOMY_VERSION = "qa_topic.v1"
TAXONOMY_HASH = "a928ca72ab2e91bda74bd1e69021e08a5234e501f095610e623655db7e323b5e"

EXCHANGE_SCHEMA = "qa_exchange.v1"
EXTRACTOR_ID = RECONSTRUCTION_SCHEMA
VALIDATOR_ID = "qa_exchange_validator.v1"
RIGHTS_PROFILE = "rp_public_primary_v1"
UNAVAILABLE_TOPIC = "unavailable"
VALIDATION_STATE = "accepted"
CLOCK_KNOWN = "known"
CLOCK_UNKNOWN = "unknown"
SOURCE_CLOCK_SCHEMA = "event_source_clock.v1"

# Revision gate for this wave. A different transcript SHA does not inherit
# the accepted seven exchanges. This is not a ticker constant.
ACCEPTED_QA_TRANSCRIPT_SHA256 = (
    "a8ff5d03e875fef5604791edbf625186c447af049e6e02f55bb89c68c7cc9f9f"
)

EXCHANGE_KEYS = (
    "schema",
    "exchange_id",
    "event_id",
    "ordinal",
    "document_id",
    "document_sha256",
    "question_spans",
    "answer_spans",
    "questioner",
    "respondents",
    "topics",
    "taxonomy_version",
    "taxonomy_hash",
    "provenance",
    "validation",
)
QUESTIONER_KEYS = ("name", "affiliation", "name_state", "affiliation_state")
RESPONDENT_KEYS = ("name", "role", "identity_state", "span_indexes")
NAME_STATE_SOURCE_SUPPORTED = "source_supported"
AFFILIATION_STATES = frozenset({"source_supported", "unresolved"})
IDENTITY_STATE_SOURCE_SUPPORTED = "source_supported"
# Named limitation: native availability may stay unknown. Processing/generation
# time must never be substituted for source_available_at.
SOURCE_CLOCK_OWNER_GAP = "SOURCE_CLOCK_OWNER_GAP"
PROVENANCE_KEYS = (
    "extractor_id",
    "provider",
    "model",
    "prompt_version",
    "validator_id",
    "run_id",
    "validation_state",
    "source_available_at",
    "clock_state",
    "rights_profile",
)
VALIDATION_KEYS = (
    "replayed",
    "unique_span",
    "event_match",
    "revision_match",
    "rights_ok",
)
SOURCE_CLOCK_KEYS = (
    "schema",
    "document_id",
    "source_sha256",
    "source_available_at",
    "system_recorded_at",
    "clock_state",
    "rights_profile",
    "session_phase",
)
_FORBIDDEN = frozenset({
    "rank", "gate", "trade", "prophet", "evasiveness", "sentiment",
    "deflection", "beat", "miss", "candidate_id",
})


def accepted_qa_exchanges_for_transcript(
    *,
    event_id: str,
    document_id: str,
    document_sha256: str,
    segments: Sequence[Mapping[str, Any]],
    source_available_at: str | None = None,
    clock_state: str = CLOCK_UNKNOWN,
) -> list[dict[str, Any]]:
    """Publish accepted exchanges for the held revision, else ``[]``.

    SHA mismatch or reconstruction failure must not delete the E2 workspace.
    """
    sha = str(document_sha256 or "").strip().lower()
    if sha != ACCEPTED_QA_TRANSCRIPT_SHA256 or not segments:
        return []
    result = reconstruct_qa(
        event_id=event_id,
        document_id=document_id,
        document_sha256=sha,
        segments=segments,
    )
    if result.get("status") != "ok":
        return []
    reconstructed = list(result.get("exchanges") or [])
    if not reconstructed:
        return []
    return canonical_qa_exchanges(
        reconstructed,
        event_id=event_id,
        document_id=document_id,
        document_sha256=sha,
        segments=segments,
        source_available_at=source_available_at,
        clock_state=clock_state,
    )


def canonical_qa_exchanges(
    reconstructed: Sequence[Mapping[str, Any]],
    *,
    event_id: str,
    document_id: str,
    document_sha256: str,
    segments: Sequence[Mapping[str, Any]],
    source_available_at: str | None = None,
    clock_state: str = CLOCK_UNKNOWN,
) -> list[dict[str, Any]]:
    run_id = _run_id(event_id=event_id, document_id=document_id, document_sha256=document_sha256)
    exchanges = [
        canonical_qa_exchange(
            raw,
            event_id=event_id,
            document_id=document_id,
            document_sha256=document_sha256,
            segments=segments,
            expected_ordinal=ordinal,
            run_id=run_id,
            source_available_at=source_available_at,
            clock_state=clock_state,
        )
        for ordinal, raw in enumerate(reconstructed)
    ]
    validate_qa_exchanges(
        exchanges,
        event_id=event_id,
        document_id=document_id,
        document_sha256=document_sha256,
    )
    return exchanges


def canonical_qa_exchange(
    reconstructed: Mapping[str, Any],
    *,
    event_id: str,
    document_id: str,
    document_sha256: str,
    segments: Sequence[Mapping[str, Any]],
    expected_ordinal: int,
    run_id: str,
    source_available_at: str | None,
    clock_state: str,
) -> dict[str, Any]:
    ordinal = int(reconstructed.get("ordinal", expected_ordinal))
    if ordinal != expected_ordinal:
        raise WorkspaceError("qa_exchange ordinals are not contiguous from 0")
    questioner = _canonical_questioner(_mapping(reconstructed.get("questioner"), "questioner"))
    question_spans = [
        _canonical_span(span, segments=segments, document_id=document_id, document_sha256=document_sha256)
        for span in list(reconstructed.get("question_spans") or [])
    ]
    answer_spans = [
        _canonical_span(span, segments=segments, document_id=document_id, document_sha256=document_sha256)
        for span in list(reconstructed.get("answer_spans") or [])
    ]
    if not question_spans or not answer_spans:
        raise WorkspaceError("qa_exchange is missing question or answer spans")
    respondents = [
        _canonical_respondent(row, answer_span_count=len(answer_spans))
        for row in list(reconstructed.get("respondents") or [])
    ]
    _assert_answer_ownership(respondents, len(answer_spans))
    return {
        "schema": EXCHANGE_SCHEMA,
        "exchange_id": f"qx_{event_id}_{document_sha256[:12]}_{ordinal:02d}",
        "event_id": event_id,
        "ordinal": ordinal,
        "document_id": document_id,
        "document_sha256": document_sha256,
        "question_spans": question_spans,
        "answer_spans": answer_spans,
        "questioner": questioner,
        "respondents": respondents,
        "topics": [UNAVAILABLE_TOPIC],
        "taxonomy_version": TAXONOMY_VERSION,
        "taxonomy_hash": TAXONOMY_HASH,
        "provenance": {
            "extractor_id": EXTRACTOR_ID,
            "provider": None,
            "model": None,
            "prompt_version": None,
            "validator_id": VALIDATOR_ID,
            "run_id": run_id,
            "validation_state": VALIDATION_STATE,
            "source_available_at": source_available_at,
            "clock_state": clock_state if clock_state in {CLOCK_KNOWN, CLOCK_UNKNOWN} else CLOCK_UNKNOWN,
            "rights_profile": RIGHTS_PROFILE,
        },
        "validation": {
            "replayed": True,
            "unique_span": True,
            "event_match": True,
            "revision_match": True,
            "rights_ok": True,
        },
    }


def validate_qa_exchange(
    payload: object,
    *,
    event_id: str,
    document_id: str,
    document_sha256: str,
    transcript_clock: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    item = _mapping(payload, "qa_exchange")
    _reject_forbidden(item)
    _exact_keys(item, EXCHANGE_KEYS, "qa_exchange")
    if item.get("schema") != EXCHANGE_SCHEMA:
        raise WorkspaceError("qa_exchange schema mismatch")
    if item.get("event_id") != event_id:
        raise WorkspaceError("qa_exchange event_id does not match parent workspace")
    if item.get("document_id") != document_id:
        raise WorkspaceError("qa_exchange document_id does not match held transcript")
    if item.get("document_sha256") != document_sha256:
        raise WorkspaceError("qa_exchange document_sha256 does not match held transcript")
    ordinal = item.get("ordinal")
    if isinstance(ordinal, bool) or not isinstance(ordinal, int) or ordinal < 0:
        raise WorkspaceError("qa_exchange ordinal is invalid")
    expected_id = f"qx_{event_id}_{document_sha256[:12]}_{ordinal:02d}"
    if item.get("exchange_id") != expected_id:
        raise WorkspaceError("qa_exchange exchange_id is not revision-scoped")
    if item.get("topics") != [UNAVAILABLE_TOPIC]:
        raise WorkspaceError("qa_exchange topics must be unavailable-only in E3-B")
    if item.get("taxonomy_version") != TAXONOMY_VERSION or item.get("taxonomy_hash") != TAXONOMY_HASH:
        raise WorkspaceError("qa_exchange taxonomy mismatch")
    questioner = _mapping(item.get("questioner"), "questioner")
    _exact_keys(questioner, QUESTIONER_KEYS, "questioner")
    _assert_questioner_identity(questioner)
    question_spans = item.get("question_spans")
    answer_spans = item.get("answer_spans")
    if not isinstance(question_spans, list) or not question_spans:
        raise WorkspaceError("qa_exchange question_spans missing")
    if not isinstance(answer_spans, list) or not answer_spans:
        raise WorkspaceError("qa_exchange answer_spans missing")
    for span in question_spans:
        _validate_canonical_span(span, document_id=document_id, document_sha256=document_sha256)
    for span in answer_spans:
        _validate_canonical_span(span, document_id=document_id, document_sha256=document_sha256)
    _assert_spans_unique_and_disjoint(question_spans, answer_spans)
    respondents = item.get("respondents")
    if not isinstance(respondents, list) or not respondents:
        raise WorkspaceError("qa_exchange respondents must be a non-empty list")
    parsed = []
    for row in respondents:
        mapped = _mapping(row, "respondent")
        _exact_keys(mapped, RESPONDENT_KEYS, "respondent")
        _assert_respondent_identity(mapped)
        parsed.append(mapped)
    _assert_answer_ownership(parsed, len(answer_spans))
    provenance = _mapping(item.get("provenance"), "provenance")
    _exact_keys(provenance, PROVENANCE_KEYS, "provenance")
    if provenance.get("extractor_id") != EXTRACTOR_ID or provenance.get("validator_id") != VALIDATOR_ID:
        raise WorkspaceError("qa_exchange provenance ids mismatch")
    if provenance.get("provider") is not None or provenance.get("model") is not None:
        raise WorkspaceError("qa_exchange must not carry a provider or model")
    if provenance.get("prompt_version") is not None:
        raise WorkspaceError("qa_exchange must not carry a prompt_version")
    if provenance.get("validation_state") != VALIDATION_STATE:
        raise WorkspaceError("qa_exchange validation_state must be accepted")
    if provenance.get("rights_profile") != RIGHTS_PROFILE:
        raise WorkspaceError("qa_exchange rights_profile mismatch")
    _assert_provenance_clock(provenance, transcript_clock=transcript_clock)
    validation = _mapping(item.get("validation"), "validation")
    _exact_keys(validation, VALIDATION_KEYS, "validation")
    if any(validation.get(key) is not True for key in VALIDATION_KEYS):
        raise WorkspaceError("qa_exchange validation booleans must all be true")
    return item


def validate_qa_exchanges(
    payload: object,
    *,
    event_id: str,
    document_id: str | None,
    document_sha256: str | None,
    transcript_clock: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        raise WorkspaceError("qa_exchanges must be a list")
    if not payload:
        return []
    if not document_id or not document_sha256:
        raise WorkspaceError("qa_exchanges require a held transcript revision")
    exchanges = [
        validate_qa_exchange(
            item,
            event_id=event_id,
            document_id=document_id,
            document_sha256=document_sha256,
            transcript_clock=transcript_clock,
        )
        for item in payload
    ]
    if [int(item["ordinal"]) for item in exchanges] != list(range(len(exchanges))):
        raise WorkspaceError("qa_exchange ordinals are not contiguous from 0")
    ids = [item["exchange_id"] for item in exchanges]
    if len(ids) != len(set(ids)):
        raise WorkspaceError("qa_exchange exchange_id values are not unique")
    seen: set[tuple[Any, ...]] = set()
    for item in exchanges:
        for span in list(item["question_spans"]) + list(item["answer_spans"]):
            ident = _span_identity(span)
            if ident in seen:
                raise WorkspaceError("qa_exchange spans are not unique")
            seen.add(ident)
    return exchanges


def source_clock_payload(
    *,
    document_id: str,
    source_sha256: str,
    source_available_at: str | None,
    system_recorded_at: str | None,
    rights_profile: str = RIGHTS_PROFILE,
    session_phase: str = "unknown",
) -> dict[str, Any] | None:
    """Nested clock only when a trustworthy system_recorded_at exists.

    Missing system_recorded_at is SOURCE_CLOCK_OWNER_GAP: return None rather
    than substituting generated_at, conference time, or wall clock.
    """
    if not system_recorded_at:
        return None
    clock_state = CLOCK_KNOWN if source_available_at else CLOCK_UNKNOWN
    payload = {
        "schema": SOURCE_CLOCK_SCHEMA,
        "document_id": document_id,
        "source_sha256": source_sha256,
        "source_available_at": source_available_at,
        "system_recorded_at": system_recorded_at,
        "clock_state": clock_state,
        "rights_profile": rights_profile,
        "session_phase": session_phase if source_available_at else "unknown",
    }
    validate_source_clock(payload, document_id=document_id, source_sha256=source_sha256)
    return payload


def validate_source_clock(
    payload: object,
    *,
    document_id: str,
    source_sha256: str,
) -> dict[str, Any]:
    item = _mapping(payload, "event_source_clock")
    _exact_keys(item, SOURCE_CLOCK_KEYS, "event_source_clock")
    if item.get("schema") != SOURCE_CLOCK_SCHEMA:
        raise WorkspaceError("event_source_clock schema mismatch")
    if item.get("document_id") != document_id:
        raise WorkspaceError("event_source_clock document_id mismatch")
    if item.get("source_sha256") != source_sha256:
        raise WorkspaceError("event_source_clock source_sha256 mismatch")
    if item.get("clock_state") not in {CLOCK_KNOWN, CLOCK_UNKNOWN}:
        raise WorkspaceError("event_source_clock clock_state invalid")
    if item.get("clock_state") == CLOCK_UNKNOWN and item.get("source_available_at") is not None:
        raise WorkspaceError("unknown source clock cannot claim source_available_at")
    if item.get("clock_state") == CLOCK_KNOWN and not item.get("source_available_at"):
        raise WorkspaceError("known source clock requires source_available_at")
    if not item.get("system_recorded_at"):
        raise WorkspaceError("event_source_clock system_recorded_at missing")
    if item.get("rights_profile") != RIGHTS_PROFILE:
        raise WorkspaceError("event_source_clock rights_profile mismatch")
    return item


def _canonical_questioner(raw: Mapping[str, Any]) -> dict[str, Any]:
    questioner = {
        "name": str(raw.get("name") or "").strip(),
        "affiliation": str(raw.get("affiliation") or ""),
        "name_state": str(raw.get("name_state") or ""),
        "affiliation_state": str(raw.get("affiliation_state") or ""),
    }
    _assert_questioner_identity(questioner)
    return questioner


def _canonical_respondent(raw: Mapping[str, Any], *, answer_span_count: int) -> dict[str, Any]:
    indexes = [int(value) for value in list(raw.get("span_indexes") or [])]
    if not indexes or indexes != sorted(set(indexes)):
        raise WorkspaceError("respondent span_indexes must be unique and ordered")
    if any(index < 0 or index >= answer_span_count for index in indexes):
        raise WorkspaceError("respondent span_indexes are out of range")
    respondent = {
        "name": str(raw.get("name") or "").strip(),
        "role": str(raw.get("role") or "").strip(),
        "identity_state": str(raw.get("identity_state") or ""),
        "span_indexes": indexes,
    }
    _assert_respondent_identity(respondent)
    return respondent


def _assert_questioner_identity(questioner: Mapping[str, Any]) -> None:
    if not str(questioner.get("name") or "").strip():
        raise WorkspaceError("qa_exchange questioner name missing")
    if questioner.get("name_state") != NAME_STATE_SOURCE_SUPPORTED:
        raise WorkspaceError("qa_exchange questioner name is not source-supported")
    affiliation_state = str(questioner.get("affiliation_state") or "")
    if affiliation_state not in AFFILIATION_STATES:
        raise WorkspaceError("qa_exchange questioner affiliation_state is not closed")
    affiliation = str(questioner.get("affiliation") or "")
    if affiliation_state == NAME_STATE_SOURCE_SUPPORTED and not affiliation.strip():
        raise WorkspaceError("qa_exchange questioner affiliation is not source-supported")
    if affiliation_state == "unresolved" and affiliation.strip():
        raise WorkspaceError("qa_exchange unresolved affiliation must be empty")


def _assert_respondent_identity(respondent: Mapping[str, Any]) -> None:
    if not str(respondent.get("name") or "").strip() or not str(respondent.get("role") or "").strip():
        raise WorkspaceError("respondent name and role must be source-supported")
    if respondent.get("identity_state") != IDENTITY_STATE_SOURCE_SUPPORTED:
        raise WorkspaceError("qa_exchange respondent identity is not source-supported")


def _assert_provenance_clock(
    provenance: Mapping[str, Any],
    *,
    transcript_clock: Mapping[str, Any] | None,
) -> None:
    clock_state = provenance.get("clock_state")
    available = provenance.get("source_available_at")
    if clock_state not in {CLOCK_KNOWN, CLOCK_UNKNOWN}:
        raise WorkspaceError("qa_exchange clock_state invalid")
    if clock_state == CLOCK_UNKNOWN and available is not None:
        raise WorkspaceError("unknown qa_exchange clock cannot claim source_available_at")
    if clock_state == CLOCK_KNOWN and not available:
        raise WorkspaceError("known qa_exchange clock requires source_available_at")
    if transcript_clock is None:
        if clock_state != CLOCK_UNKNOWN or available is not None:
            raise WorkspaceError(
                f"{SOURCE_CLOCK_OWNER_GAP}: qa_exchange provenance must be unknown with null availability"
            )
        return
    if provenance.get("clock_state") != transcript_clock.get("clock_state"):
        raise WorkspaceError("qa_exchange clock_state does not match transcript source clock")
    if provenance.get("source_available_at") != transcript_clock.get("source_available_at"):
        raise WorkspaceError("qa_exchange source_available_at does not match transcript source clock")
    if provenance.get("rights_profile") != transcript_clock.get("rights_profile"):
        raise WorkspaceError("qa_exchange rights_profile does not match transcript source clock")


def _span_identity(span: Mapping[str, Any]) -> tuple[Any, ...]:
    receipt = _mapping(span.get("receipt"), "span.receipt")
    locator = _mapping(span.get("locator"), "span.locator")
    try:
        segment = int(locator.get("segment_index"))
        start = int(locator.get("span_start_byte"))
        end = int(locator.get("span_end_byte"))
    except (TypeError, ValueError) as exc:
        raise WorkspaceError("qa_exchange span locator is incomplete") from exc
    return (
        str(span.get("document_id") or ""),
        str(receipt.get("source_sha256") or ""),
        segment,
        start,
        end,
    )


def _assert_spans_unique_and_disjoint(
    question_spans: Sequence[Mapping[str, Any]],
    answer_spans: Sequence[Mapping[str, Any]],
) -> None:
    identities: list[tuple[Any, ...]] = []
    question_count = len(question_spans)
    for span in list(question_spans) + list(answer_spans):
        ident = _span_identity(span)
        if ident[3] >= ident[4]:
            raise WorkspaceError("qa_exchange span byte range is invalid")
        identities.append(ident)
    if len(identities) != len(set(identities)):
        raise WorkspaceError("qa_exchange spans are not unique")
    for index, ident in enumerate(identities):
        key = ident[:3]
        start, end = ident[3], ident[4]
        for other_index, other in enumerate(identities):
            if other_index <= index or other[:3] != key:
                continue
            other_start, other_end = other[3], other[4]
            if start < other_end and other_start < end:
                crossed = (index < question_count) != (other_index < question_count)
                if crossed:
                    raise WorkspaceError("qa_exchange question and answer spans overlap")
                raise WorkspaceError("qa_exchange spans overlap")


def _run_id(*, event_id: str, document_id: str, document_sha256: str) -> str:
    digest = canonical_json_sha256({
        "event_id": event_id,
        "document_id": document_id,
        "document_sha256": document_sha256,
        "extractor_id": EXTRACTOR_ID,
        "validator_id": VALIDATOR_ID,
        "taxonomy_version": TAXONOMY_VERSION,
        "taxonomy_hash": TAXONOMY_HASH,
    })
    return f"e3b_{digest[:16]}"


def _canonical_span(
    raw: Mapping[str, Any],
    *,
    segments: Sequence[Mapping[str, Any]],
    document_id: str,
    document_sha256: str,
) -> dict[str, Any]:
    index = int(raw["segment_index"])
    start = int(raw["start_byte"])
    end = int(raw["end_byte"])
    if index < 0 or index >= len(segments):
        raise WorkspaceError("qa_exchange span segment_index is out of range")
    segment_text = str(segments[index].get("text") or "")
    encoded = segment_text.encode("utf-8")
    if start < 0 or end > len(encoded) or start >= end:
        raise WorkspaceError("qa_exchange span byte range is invalid")
    sliced = encoded[start:end].decode("utf-8")
    payload = text_span(
        document_id=document_id,
        document_version=1,
        body_sha256=document_sha256,
        segment_index=index,
        segment_text=segment_text,
        start_byte=start,
        end_byte=end,
        text=sliced,
        speaker=str(raw.get("speaker") or "") or None,
        role=str(raw.get("role") or "") or None,
        rights_profile=RIGHTS_PROFILE,
    ).to_payload()
    claimed = str(raw.get("text_sha256") or "")
    if claimed and claimed != payload.get("text_sha256"):
        raise WorkspaceError("qa_exchange span text_sha256 does not replay")
    return payload


def _assert_answer_ownership(respondents: Sequence[Mapping[str, Any]], answer_span_count: int) -> None:
    owned: list[int] = []
    for row in respondents:
        indexes = [int(value) for value in list(row.get("span_indexes") or [])]
        if any(index < 0 or index >= answer_span_count for index in indexes):
            raise WorkspaceError("respondent span_indexes are out of range")
        owned.extend(indexes)
    if owned != list(range(answer_span_count)):
        raise WorkspaceError("answer spans are not owned exactly once")


def _validate_canonical_span(payload: object, *, document_id: str, document_sha256: str) -> None:
    item = _mapping(payload, "source_span")
    if item.get("schema") != "source_span.v1":
        raise WorkspaceError("qa_exchange span schema mismatch")
    if item.get("document_id") != document_id:
        raise WorkspaceError("qa_exchange span document_id mismatch")
    if item.get("receipt_state") != "byte_replayed":
        raise WorkspaceError("qa_exchange span must be byte-replayed")
    receipt = _mapping(item.get("receipt"), "span.receipt")
    if receipt.get("source_sha256") != document_sha256:
        raise WorkspaceError("qa_exchange span source_sha256 mismatch")
    if item.get("rights_profile") != RIGHTS_PROFILE:
        raise WorkspaceError("qa_exchange span rights_profile mismatch")
    if item.get("authority") != "context_only":
        raise WorkspaceError("qa_exchange span authority mismatch")


def _mapping(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise WorkspaceError(f"{name} must be an object")
    return dict(value)


def _exact_keys(item: Mapping[str, Any], keys: Sequence[str], name: str) -> None:
    if set(item) != set(keys):
        raise WorkspaceError(f"{name} keys mismatch")


def _reject_forbidden(item: Mapping[str, Any]) -> None:
    if {str(key).casefold() for key in item} & _FORBIDDEN:
        raise WorkspaceError("qa_exchange carries a forbidden control-plane key")
