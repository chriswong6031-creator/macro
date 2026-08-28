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

# Generic Operator-intro identity grammar. Name and affiliation are separable.
# Affiliation is cut at the go-ahead clause, never at the first period, so
# "J.P. Morgan" cannot collapse to "J".
_NAME_CUE_RE = re.compile(
    r"(?:question(?:\s+\w+)?\s+from|go\s+to)\s+"
    r"(?P<name>[A-Z][A-Za-z']+(?:-[A-Z][A-Za-z']+)?(?:\s+[A-Z][A-Za-z']+(?:-[A-Z][A-Za-z']+)?){0,4})"
)
_AFFIL_PREP_RE = re.compile(
    r"^\s+(?:from|of|with|at)\s+(?P<body>.*)$",
    re.DOTALL | re.IGNORECASE,
)
_AFFIL_CUT_RE = re.compile(
    r"(?P<affiliation>.*?)"
    r"(?=\s*\.\s*(?:Please\s+)?go\s+ahead|\s+Please\s+go\s+ahead|\s*[?!]|$)",
    re.IGNORECASE | re.DOTALL,
)
_NON_MANAGEMENT_ROLES = frozenset({
    "analyst",
    "guest",
    "moderator",
    "journalist",
    "attendee",
    "participant",
})

# --- TFG-1 R2 structural separator + proxy grammar -------------------------------
# Frozen law (DEC:E3FMT-STRUCTURAL-SEPARATORS-PROXY-IDENTITY-AND-SOURCE-CONDITIONED-HOLDOUT):
# terminal cue phrases ("go ahead", "line is open", "proceed") carry ZERO admission
# authority. A structural separator is an unambiguous question-bearing housekeeping
# handoff immediately followed by a non-housekeeping source turn -- whether or not the
# questioner can be canonicalized.
#
# Case-sensitive and period-free so a name can never run across a sentence boundary
# into a following return clause, even under IGNORECASE cue matching.
_R2_NAME = r"(?-i:[A-Z][A-Za-z\u00c0-\u024f'\u2019\-]*(?:\s+[A-Z][A-Za-z\u00c0-\u024f'\u2019\-]*){0,3})"

# "our next question comes from the line of Joe Osha with Guggenheim"
_R2_ATTRIB = re.compile(
    r"\bquestions?\b[^.?!]{0,60}?\b(?:from|of|the\s+line\s+of)\s+(?:the\s+line\s+of\s+)?"
    r"(?P<name>" + _R2_NAME + r")",
    re.IGNORECASE,
)
# "One moment for our first question. It's from Richard Garchitorena with Barclays."
_R2_ATTRIB_CONT = re.compile(
    r"\bquestions?\b[^.?!]{0,40}[.]\s*(?:It(?:'s|\u2019s| is)|This is)\s+from\s+"
    r"(?P<name>" + _R2_NAME + r")",
    re.IGNORECASE,
)
# "We'll now move on to Tom Catherwood" / "let's go to Joe Osha"
_R2_CONTINUE = re.compile(
    r"\b(?:we(?:'ll|\u2019ll| will| shall)?\s+)?(?:now\s+)?(?:mov(?:e|ing)\s+on|go)\s+"
    r"(?:on\s+)?(?:now\s+)?to\s+(?P<name>" + _R2_NAME + r")",
    re.IGNORECASE,
)
# A return of the floor to management is never a question handoff.
_R2_RETURN = re.compile(
    r"\b(?:turn|hand|pass|give|send)\b[^.?!]{0,60}?\bback\b|\bback\s+(?:over\s+)?to\b"
    r"|\b(?:turn|hand)\s+(?:the\s+)?(?:call|conference|floor|program|meeting)\s+over\s+to\b",
    re.IGNORECASE,
)
# A personal full name: at least two alphabetic capitalised tokens. "Speaker 4" is not
# one, which is why a placeholder can never be canonicalised even when its utterance
# carries an otherwise well-formed on-for clause (BANR #71 in the frozen corpus).
_R2_FULL_NAME_RE = re.compile(
    r"^(?-i:[A-Z][A-Za-z\u00c0-\u024f'\u2019\-]*(?:\s+[A-Z][A-Za-z\u00c0-\u024f'\u2019\-]*)+)$"
)


_FAILURE_CODES = frozenset({
    "transcript_sha_invalid",
    "empty_segments",
    "malformed_empty_segment",
    "zero_qa_boundaries",
    "duplicate_or_unordered_boundaries",
    "operator_intro_identity_unparsed",
    "operator_analyst_name_conflict",
    "unresolved_questioner_identity",
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
        return _fail(base, "zero_qa_boundaries", "no question-bearing handoff is followed by a source turn")
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


def _is_verified_questioner(seg: Mapping[str, Any], questioner_name: str) -> bool:
    name = _speaker_name(seg)
    return bool(questioner_name) and bool(name) and _norm_person(name) == _norm_person(questioner_name)


def _is_non_management_role(seg: Mapping[str, Any]) -> bool:
    return _role_key(seg) in _NON_MANAGEMENT_ROLES


def _is_management(seg: Mapping[str, Any], questioner_name: str = "") -> bool:
    if _is_housekeeping(seg) or _is_verified_questioner(seg, questioner_name):
        return False
    if _is_non_management_role(seg):
        return False
    return bool(_role_key(seg))


def _norm_person(name: str) -> str:
    return " ".join(str(name).split()).casefold()


def _contains_go_ahead(text: str) -> bool:
    return _GO_AHEAD in " ".join(str(text).split()).casefold()


def _return_spans(text: str) -> list[tuple[int, int]]:
    """Character ranges of return-the-floor clauses, which cannot carry a questioner."""
    spans: list[tuple[int, int]] = []
    for match in _R2_RETURN.finditer(text):
        end = text.find(".", match.end())
        spans.append((match.start(), len(text) if end < 0 else end))
    return spans


def _handoff_name(text: object) -> tuple[int, str] | None:
    """Position and name of the questioner named by a question-bearing handoff."""
    body = " ".join(str(text or "").split())
    blocked = _return_spans(body)
    hits: list[tuple[int, str]] = []
    for pattern in (_R2_ATTRIB, _R2_ATTRIB_CONT, _R2_CONTINUE):
        for match in pattern.finditer(body):
            pos = match.start("name")
            if any(lo <= pos <= hi for lo, hi in blocked):
                continue
            name = match.group("name").strip(" ,.")
            if name:
                hits.append((pos, name))
    if not hits:
        return None
    hits.sort()
    return hits[-1]


def _next_source_turn(segments: Sequence[Mapping[str, Any]], index: int) -> int | None:
    for j in range(index + 1, len(segments)):
        seg = segments[j]
        if _role_key(seg) in _HOUSEKEEPING_ROLES:
            continue
        if not _speaker_name(seg):
            continue
        return j
    return None


def _qualifying_boundaries(segments: Sequence[Mapping[str, Any]]) -> list[int]:
    """Structural separators. Terminal cues have no admission authority here."""
    return [
        idx
        for idx, seg in enumerate(segments)
        if _is_housekeeping(seg)
        and _handoff_name(_text(seg)) is not None
        and _next_source_turn(segments, idx) is not None
    ]


def _affiliation_is_truncated(body: str, parsed: str) -> bool:
    if not parsed:
        return False
    idx = body.find(parsed)
    if idx < 0:
        return True
    rest = body[idx + len(parsed):]
    return bool(rest) and rest[0] == "." and len(rest) > 1 and rest[1].isalpha()


def _parse_affiliation_after(after: str) -> tuple[str, str]:
    match = _AFFIL_PREP_RE.match(after)
    if not match:
        return "", "unresolved"
    body = match.group("body")
    cut = _AFFIL_CUT_RE.match(body)
    affiliation = (cut.group("affiliation") if cut else body).strip().strip(" ,;")
    if not affiliation or _affiliation_is_truncated(body, affiliation):
        return "", "unresolved"
    return affiliation, "source_supported"


def _parse_operator_identity(text: str) -> dict[str, Any] | None:
    source = " ".join(str(text).split())
    hit = _handoff_name(source)
    if hit is None:
        return None
    position, name = hit
    affiliation, state = _parse_affiliation_after(source[position + len(name):])
    if state == "source_supported" and affiliation:
        return {
            "name": name,
            "affiliation": affiliation,
            "affiliation_state": "source_supported",
        }
    return {"name": name, "affiliation": "", "affiliation_state": "unresolved"}


def _is_explicit_full_name_proxy(speaker: str, principal: str, utterance: str) -> bool:
    """A differing next speaker is source-supported only when their OWN first source
    utterance explicitly binds them as on-for/sitting-in-for the Operator-named
    principal.

    The speaker must itself be a personal full name: a structured placeholder such as
    "Speaker 9" cannot be canonicalised even when its utterance carries an otherwise
    well-formed on-for clause naming the principal in full. Affiliation never transfers
    from the principal to the proxy.
    """
    speaker = " ".join(str(speaker or "").split())
    if not _R2_FULL_NAME_RE.match(speaker):
        return False
    body = " ".join(str(utterance or "").split())
    relation = re.compile(
        re.escape(speaker)
        + r"\s*,?\s*(?:is\s+)?(?:on|sitting\s+in|in)\s+for\s+"
        + r"(?P<principal>" + _R2_NAME + r")",
        re.IGNORECASE,
    )
    match = relation.search(body)
    if not match:
        return False
    claimed = _norm_person(match.group("principal").strip(" ,."))
    full = _norm_person(principal)
    if not claimed or not full:
        return False
    # Full name, or the principal's own first name -- never a different person.
    return claimed == full or claimed == full.split(" ")[0]


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
        if _is_verified_questioner(seg, parsed["name"]):
            first_analyst_idx = idx
            break
        if _is_management(seg, parsed["name"]):
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
    principal = parsed["name"]
    if _norm_person(principal) != _norm_person(speaker):
        if _is_explicit_full_name_proxy(speaker, principal, _text(first_analyst)):
            # Proxy is source-supported; the principal's affiliation does not transfer.
            parsed = {
                "name": speaker,
                "affiliation": "",
                "affiliation_state": "unresolved",
            }
        else:
            return {
                "status": "failed",
                "failure": {
                    "code": "unresolved_questioner_identity",
                    "message": (
                        f"Operator named {principal!r} but the next source speaker is "
                        f"{speaker!r} with no explicit on-for relation; the structural "
                        f"separator stands and no canonical Q&A may be minted"
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
        elif _is_verified_questioner(seg, questioner_name):
            kind = "question"
        elif _is_management(seg, questioner_name):
            if not _speaker_name(seg) or not _role_key(seg):
                return {
                    "status": "failed",
                    "failure": {
                        "code": "management_identity_insufficient",
                        "message": f"management segment {idx} missing speaker or role",
                    },
                }
            kind = "answer"
        elif not _role_key(seg):
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
        elif _is_non_management_role(seg):
            name = _speaker_name(seg) or "<unnamed>"
            return {
                "status": "failed",
                "failure": {
                    "code": "unexpected_non_housekeeping_speaker",
                    "message": (
                        f"segment {idx} speaker {name!r} has a non-management role "
                        "and is not the verified questioner"
                    ),
                },
            }
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
