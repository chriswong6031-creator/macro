"""Deterministic source-native Q&A reconstruction (E3-A2).

Reconstructs Operator-delimited exchange structure from held transcript
segments alone. No model calls. No gold/research imports. No ticker,
issuer, or boundary-index constants.

This module does not publish ``qa_exchanges`` and grants no topic or
production authority.
"""
from __future__ import annotations

from hashlib import sha256
import re
from typing import Any, Mapping, Sequence

SCHEMA = "qa_reconstruction.v1"
SEMANTIC_STATUS = "unresolved"
TOPIC_AUTHORITY = "none"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_HOUSEKEEPING_ROLES = frozenset({"operator", "ir"})
_GO_AHEAD = "go ahead"

# Generic Operator-intro identity grammar. Not issuer-specific.
#   "question from NAME from/of AFFILIATION"
#   "question is from NAME of AFFILIATION"
#   "go to NAME of AFFILIATION"
_IDENTITY_RE = re.compile(
    r"(?:question(?:\s+\w+)?\s+from|go\s+to)\s+"
    r"(?P<name>[A-Z][A-Za-z'.-]+(?:\s+[A-Z][A-Za-z'.-]+){0,4})"
    r"\s+(?:from|of|with|at)\s+"
    r"(?P<affiliation>[^.,]+)"
)

_FAILURE_CODES = frozenset({
    "transcript_sha_invalid",
    "empty_segments",
    "malformed_empty_segment",
    "zero_qa_boundaries",
    "duplicate_or_unordered_boundaries",
    "operator_intro_identity_unparsed",
    "operator_analyst_name_conflict",
    "analyst_speaker_missing",
    "unexpected_non_housekeeping_speaker",
    "management_identity_insufficient",
    "span_replay_failed",
    "question_answer_overlap",
    "orphan_or_duplicate_answer_span",
    "question_without_management_speech",
    "unclassified_segment",
    "qa_provider_format_unsupported",
})


def reconstruct_qa(
    *,
    event_id: str,
    document_id: str,
    document_sha256: str,
    segments: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Reconstruct Q&A structure from ordered transcript segments.

    Identity is revision-scoped: ``qx_{event_id}_{document_sha256[:12]}_{ordinal:02d}``.
    """
    base = {
        "schema": SCHEMA,
        "event_id": event_id,
        "document_id": document_id,
        "document_sha256": document_sha256,
        "model_calls": 0,
        "topic_authority": TOPIC_AUTHORITY,
        "semantic_status": SEMANTIC_STATUS,
        "qualifying_boundaries": [],
        "exchanges": [],
        "unclassified_segment_count": 0,
        "housekeeping_segment_count": 0,
    }
    sha = str(document_sha256 or "")
    if not _SHA256_RE.fullmatch(sha):
        return _fail(base, "transcript_sha_invalid", "document_sha256 is not a 64-char lowercase hex digest")
    if not str(event_id or "").strip() or not str(document_id or "").strip():
        return _fail(base, "qa_provider_format_unsupported", "event_id and document_id are required")
    if not segments:
        return _fail(base, "empty_segments", "no transcript segments")

    segs = list(segments)
    for idx, seg in enumerate(segs):
        if not isinstance(seg, Mapping):
            return _fail(base, "qa_provider_format_unsupported", f"segment {idx} is not a mapping")
        text = seg.get("text")
        if text is None or not str(text):
            return _fail(base, "malformed_empty_segment", f"segment {idx} has empty text")

    boundaries = _qualifying_boundaries(segs)
    if not boundaries:
        return _fail(base, "zero_qa_boundaries", "no Operator segments contain the go-ahead introduction")
    if boundaries != sorted(set(boundaries)):
        return _fail(base, "duplicate_or_unordered_boundaries", "qualifying boundaries are not strictly increasing")
    base["qualifying_boundaries"] = list(boundaries)

    exchanges: list[dict[str, Any]] = []
    housekeeping_count = 0
    for ordinal, start in enumerate(boundaries):
        end = boundaries[ordinal + 1] if ordinal + 1 < len(boundaries) else len(segs)
        built = _reconstruct_exchange(
            event_id=event_id,
            document_id=document_id,
            document_sha256=sha,
            segments=segs,
            ordinal=ordinal,
            start=start,
            end=end,
        )
        if built.get("status") != "ok":
            return _fail(
                {**base, "qualifying_boundaries": list(boundaries)},
                built["failure"]["code"],
                built["failure"]["message"],
                extra={"exchange_ordinal": ordinal, "boundary_segment_index": start},
            )
        exchanges.append(built["exchange"])
        housekeeping_count += int(built["housekeeping_segment_count"])

    return {
        **base,
        "status": "ok",
        "failure": None,
        "exchanges": exchanges,
        "housekeeping_segment_count": housekeeping_count,
        "unclassified_segment_count": 0,
    }


def _fail(
    base: dict[str, Any],
    code: str,
    message: str,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if code not in _FAILURE_CODES:
        code = "qa_provider_format_unsupported"
    failure: dict[str, Any] = {"code": code, "message": message}
    if extra:
        failure.update(dict(extra))
    return {
        **base,
        "status": "failed",
        "failure": failure,
        "exchanges": [],
        "unclassified_segment_count": 1 if code == "unclassified_segment" else 0,
    }


def _role_key(seg: Mapping[str, Any]) -> str:
    return str(seg.get("role") or "").strip().casefold()


def _speaker_name(seg: Mapping[str, Any]) -> str:
    return str(seg.get("speaker") or "").strip()


def _text(seg: Mapping[str, Any]) -> str:
    return str(seg.get("text") or "")


def _is_housekeeping(seg: Mapping[str, Any]) -> bool:
    return _role_key(seg) in _HOUSEKEEPING_ROLES


def _is_operator(seg: Mapping[str, Any]) -> bool:
    return _role_key(seg) == "operator"


def _is_management(seg: Mapping[str, Any]) -> bool:
    return (not _is_housekeeping(seg)) and bool(_role_key(seg))


def _norm_person(name: str) -> str:
    return " ".join(str(name).split()).casefold()


def _contains_go_ahead(text: str) -> bool:
    return _GO_AHEAD in " ".join(str(text).split()).casefold()


def _qualifying_boundaries(segments: Sequence[Mapping[str, Any]]) -> list[int]:
    out: list[int] = []
    for idx, seg in enumerate(segments):
        if _is_operator(seg) and _contains_go_ahead(_text(seg)):
            out.append(idx)
    return out


def _parse_operator_identity(text: str) -> dict[str, Any] | None:
    matches = list(_IDENTITY_RE.finditer(str(text)))
    if not matches:
        return None
    names = {m.group("name").strip() for m in matches}
    affils = {m.group("affiliation").strip() for m in matches}
    if len(names) != 1:
        return None
    name = next(iter(names))
    if not name:
        return None
    if len(affils) != 1 or not next(iter(affils)):
        return {
            "name": name,
            "affiliation": "",
            "affiliation_state": "unresolved",
        }
    return {
        "name": name,
        "affiliation": next(iter(affils)),
        "affiliation_state": "source_supported",
    }


def _whole_segment_span(seg: Mapping[str, Any], index: int) -> dict[str, Any] | None:
    text = _text(seg)
    encoded = text.encode("utf-8")
    digest = sha256(encoded).hexdigest()
    start_byte = 0
    end_byte = len(encoded)
    sliced = encoded[start_byte:end_byte]
    if sliced != encoded or sha256(sliced).hexdigest() != digest:
        return None
    claimed = str(seg.get("text_sha256") or seg.get("sha256") or "").strip().casefold()
    if claimed and claimed != digest:
        return None
    return {
        "segment_index": index,
        "start_byte": start_byte,
        "end_byte": end_byte,
        "text_sha256": digest,
        "speaker": _speaker_name(seg) or str(seg.get("speaker") or ""),
        "role": str(seg.get("role") or ""),
    }


def _reconstruct_exchange(
    *,
    event_id: str,
    document_id: str,
    document_sha256: str,
    segments: Sequence[Mapping[str, Any]],
    ordinal: int,
    start: int,
    end: int,
) -> dict[str, Any]:
    intro = segments[start]
    parsed = _parse_operator_identity(_text(intro))
    if parsed is None:
        return {
            "status": "failed",
            "failure": {
                "code": "operator_intro_identity_unparsed",
                "message": f"Operator intro at segment {start} has no unique name/affiliation",
            },
        }

    first_analyst_idx: int | None = None
    for idx in range(start + 1, end):
        seg = segments[idx]
        if _is_housekeeping(seg):
            continue
        if _is_management(seg):
            continue
        first_analyst_idx = idx
        break
    if first_analyst_idx is None:
        return {
            "status": "failed",
            "failure": {
                "code": "analyst_speaker_missing",
                "message": f"no analyst speaker after Operator intro {start}",
            },
        }
    first_analyst = segments[first_analyst_idx]
    speaker = _speaker_name(first_analyst)
    if not speaker:
        return {
            "status": "failed",
            "failure": {
                "code": "operator_intro_identity_unparsed",
                "message": f"analyst speaker at segment {first_analyst_idx} is empty",
            },
        }
    if _norm_person(parsed["name"]) != _norm_person(speaker):
        return {
            "status": "failed",
            "failure": {
                "code": "operator_analyst_name_conflict",
                "message": (
                    f"Operator intro name {parsed['name']!r} does not match "
                    f"first analyst speaker {speaker!r}"
                ),
            },
        }
    questioner_name = speaker

    question_spans: list[dict[str, Any]] = []
    answer_spans: list[dict[str, Any]] = []
    housekeeping_indexes: list[int] = []
    kinds: dict[int, str] = {}

    for idx in range(start, end):
        seg = segments[idx]
        if idx == start:
            kind = "question"
        elif _is_housekeeping(seg):
            kind = "housekeeping"
        elif _is_management(seg):
            if not _speaker_name(seg) or not _role_key(seg):
                return {
                    "status": "failed",
                    "failure": {
                        "code": "management_identity_insufficient",
                        "message": f"management segment {idx} missing speaker or role",
                    },
                }
            kind = "answer"
        elif _is_housekeeping(seg) is False and not _role_key(seg):
            name = _speaker_name(seg)
            if not name:
                return {
                    "status": "failed",
                    "failure": {
                        "code": "malformed_empty_segment",
                        "message": f"segment {idx} has blank analyst identity",
                    },
                }
            if _norm_person(name) != _norm_person(questioner_name):
                return {
                    "status": "failed",
                    "failure": {
                        "code": "unexpected_non_housekeeping_speaker",
                        "message": (
                            f"segment {idx} speaker {name!r} is not the verified questioner"
                        ),
                    },
                }
            kind = "question"
        else:
            return {
                "status": "failed",
                "failure": {
                    "code": "unclassified_segment",
                    "message": f"segment {idx} cannot be classified from source role/speaker",
                },
            }
        kinds[idx] = kind
        if kind == "housekeeping":
            housekeeping_indexes.append(idx)
            continue
        span = _whole_segment_span(seg, idx)
        if span is None:
            return {
                "status": "failed",
                "failure": {
                    "code": "span_replay_failed",
                    "message": f"segment {idx} failed exact UTF-8 byte replay",
                },
            }
        if kind == "question":
            question_spans.append(span)
        else:
            answer_spans.append(span)

    q_indexes = {s["segment_index"] for s in question_spans}
    a_indexes = {s["segment_index"] for s in answer_spans}
    if q_indexes & a_indexes:
        return {
            "status": "failed",
            "failure": {
                "code": "question_answer_overlap",
                "message": "question and answer spans share a segment",
            },
        }
    if not answer_spans:
        return {
            "status": "failed",
            "failure": {
                "code": "question_without_management_speech",
                "message": f"exchange at {start} has analyst question but no management speech",
            },
        }

    respondents = _answer_turns(segments, start, end, kinds, answer_spans)
    owned: list[int] = []
    for turn in respondents:
        owned.extend(turn["span_indexes"])
    expected = list(range(len(answer_spans)))
    if owned != expected:
        return {
            "status": "failed",
            "failure": {
                "code": "orphan_or_duplicate_answer_span",
                "message": "answer spans are not owned exactly once by ordered turns",
            },
        }

    affiliation_state = parsed["affiliation_state"]
    affiliation = parsed["affiliation"] if affiliation_state == "source_supported" else ""
    questioner = {
        "name": questioner_name,
        "affiliation": affiliation,
        "name_state": "source_supported",
        "affiliation_state": affiliation_state,
        "name_source_segments": [start, first_analyst_idx],
        "affiliation_source_segment": start if affiliation_state == "source_supported" else None,
    }
    exchange = {
        "exchange_id": f"qx_{event_id}_{document_sha256[:12]}_{ordinal:02d}",
        "event_id": event_id,
        "ordinal": ordinal,
        "document_id": document_id,
        "document_sha256": document_sha256,
        "boundary_segment_index": start,
        "questioner": questioner,
        "question_spans": question_spans,
        "answer_spans": answer_spans,
        "respondents": respondents,
        "semantic_status": SEMANTIC_STATUS,
        "topic_authority": TOPIC_AUTHORITY,
    }
    return {
        "status": "ok",
        "exchange": exchange,
        "housekeeping_segment_count": len(housekeeping_indexes),
    }


def _answer_turns(
    segments: Sequence[Mapping[str, Any]],
    start: int,
    end: int,
    kinds: Mapping[int, str],
    answer_spans: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """One respondent per management answer-turn, split on speaker/analyst/housekeeping."""
    index_by_seg = {span["segment_index"]: i for i, span in enumerate(answer_spans)}
    turns: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    def close() -> None:
        nonlocal current
        if current is not None:
            turns.append(current)
            current = None

    for idx in range(start, end):
        kind = kinds[idx]
        if kind != "answer":
            close()
            continue
        seg = segments[idx]
        name = _speaker_name(seg)
        role = str(seg.get("role") or "")
        span_i = index_by_seg[idx]
        if current is None or current["name"] != name:
            close()
            current = {
                "name": name,
                "role": role,
                "identity_state": "source_supported",
                "span_indexes": [span_i],
            }
        else:
            current["span_indexes"].append(span_i)
    close()
    return turns
