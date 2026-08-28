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


# Same-revision participant/title declaration.
#
# The frozen corpus uses BOTH orders and they are false friends for each other:
#   order A  "Kevin Hostetler, our CEO, Keith Jennings, our CFO"      (name first)
#   order B  "our CEO, Matt Salem, our President and COO, Patrick Mattson"  (office first)
# Reading ARRY (order A) with the order-B pattern binds Keith Jennings to CEO when the
# source says CFO -- which would erase one of the two real role conflicts in the corpus.
# So the order is decided per sentence by whichever appears first, a name or an office.
_ROSTER_NAME = r"(?-i:[A-Z][A-Za-z\u00c0-\u024f'\u2019\-]*(?:\s+[A-Z][A-Za-z\u00c0-\u024f'\u2019\-]*){1,3})"
_HONORIFIC = r"(?:(?:Mr|Ms|Mrs|Dr|Prof)\.?\s+)?"
# An office phrase must BEGIN with an office word once any determiner/possessive is
# stripped. Without that anchor "Ole Rosgaard, will provide a strategy and market
# update" parses as a title merely because "CFO" appears later in the sentence.
_OFFICE_HEAD = (
    r"(?:chief|president|chairman|chairwoman|treasurer|ceo|cfo|coo|cio|senior|"
    r"executive|vice|deputy|interim|acting|co-chief|head|managing|general|"
    r"principal|founder|partner)"
)
# Possessives are stripped case-insensitively: the corpus carries both "Capital One's
# Chief Financial Officer" and "the company's Chief Executive Officer", and requiring a
# capitalised possessive silently dropped every lowercase one (ARQQ).
_DETERMINER_RE = re.compile(
    r"^(?:(?:the|our|its|his|her|a|an)\s+)?"
    r"(?:[\w'\u2019&.\-]+(?:\s+[\w'\u2019&.\-]+){0,3}['\u2019]s\s+)?",
    re.IGNORECASE,
)
_OFFICE_HEAD_RE = re.compile(r"^" + _OFFICE_HEAD + r"\b", re.IGNORECASE)
_NAME_COMMA_RE = re.compile(_HONORIFIC + r"(?P<name>" + _ROSTER_NAME + r")\s*,")
# The office head is anchored inside the pattern, not merely validated afterwards: an
# earlier determiner otherwise hijacks the match and consumes the real one. KREF's
# "joined on the call by our CEO, Matt Salem" matched title="call by our CEO" via the
# leading "the", which failed validation and took "our CEO, Matt Salem" down with it.
_OFFICE_COMMA_RE = re.compile(
    r"\b(?:our|the|its)\s+(?P<title>" + _OFFICE_HEAD + r"\b[^,.;]{0,66}?)\s*,\s*"
    + _HONORIFIC + r"(?P<name>" + _ROSTER_NAME + r")\b",
    re.IGNORECASE,
)
# Clauses that end a title rather than continuing it.
_TITLE_STOP_RE = re.compile(
    r",\s*who\b|,\s*(?:will|shall|is|was|has|have|and\s+will)\b|\s+and\s+also\b",
    re.IGNORECASE,
)
_TITLE_TAIL_RE = re.compile(
    r"(?:\s*,)?\s*(?:and\s+)?(?:Mr|Ms|Mrs|Dr|Prof)\.?\s*$|(?:\s*,)?\s*and\s*$|[\s,;.]+$",
    re.IGNORECASE,
)
_SENTENCE_RE = re.compile(r"[^.;]+[.;]?")
# Closed role-comparison alias table. CEO/CFO/COO only -- no CIO, no open-ended
# abbreviation derivation. CTRE is exactly why: James Callister is declared Chief
# Investment Officer and tagged CFO, and that must refuse rather than alias away.
_ROLE_ALIASES = {
    "ceo": "chief executive officer",
    "cfo": "chief financial officer",
    "coo": "chief operating officer",
}


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
    "management_identity_conflict",
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

    roster = _roster_declarations(segs)
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
            roster=roster,
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


def _is_management(
    seg: Mapping[str, Any],
    questioner_name: str = "",
    roster: Mapping[str, Mapping[str, Any]] | None = None,
) -> bool:
    if _is_housekeeping(seg) or _is_verified_questioner(seg, questioner_name):
        return False
    if _is_non_management_role(seg):
        return False
    if _role_key(seg):
        return True
    # Roleless speaker is management only when the same revision declares their office.
    return bool(roster) and _roster_support(roster, _speaker_name(seg)) is not None


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


def _handoff_hits(text: object) -> list[tuple[int, str]]:
    """Every question-bearing named handoff in a segment, ordered by position."""
    body = " ".join(str(text or "").split())
    blocked = _return_spans(body)
    hits: list[tuple[int, str]] = []
    for pattern in (_R2_ATTRIB, _R2_ATTRIB_CONT, _R2_CONTINUE):
        for match in pattern.finditer(body):
            pos = match.start("name")
            if any(lo <= pos <= hi for lo, hi in blocked):
                continue
            name = match.group("name").strip(" ,.")
            if name and (pos, name) not in hits:
                hits.append((pos, name))
    hits.sort()
    return hits


def _handoff_name(text: object) -> tuple[int, str] | None:
    """Position and name of the questioner named by a question-bearing handoff."""
    hits = _handoff_hits(text)
    return hits[-1] if hits else None


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
    hits = _handoff_hits(source)
    if not hits:
        return None
    name = hits[-1][1]
    # Conflicting same-revision affiliations for the SAME person stay unresolved: an
    # intro that names one questioner with two different desks supports neither.
    affiliations: set[str] = set()
    for i, (position, hit_name) in enumerate(hits):
        if _norm_person(hit_name) != _norm_person(name):
            continue
        stop = hits[i + 1][0] if i + 1 < len(hits) else len(source)
        affiliation, state = _parse_affiliation_after(source[position + len(hit_name):stop])
        if state == "source_supported" and affiliation:
            affiliations.add(affiliation)
    if len(affiliations) == 1:
        return {
            "name": name,
            "affiliation": next(iter(affiliations)),
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


_HONORIFIC_DOT_RE = re.compile(r"\b(Mr|Ms|Mrs|Dr|Prof|St|Jr|Sr)\.", re.IGNORECASE)
_SENTINEL = "\u0000"


def _split_sentences(body: str) -> list[str]:
    """Sentence split that does not treat an honorific's period as a sentence end."""
    guarded = _HONORIFIC_DOT_RE.sub(lambda m: m.group(1) + _SENTINEL, body)
    return [s.replace(_SENTINEL, ".") for s in _SENTENCE_RE.findall(guarded)]


def _clean_title(raw: str) -> str:
    """Trim a candidate title at its first stop clause and drop trailing connectors."""
    title = " ".join(str(raw or "").split())
    stop = _TITLE_STOP_RE.search(title)
    if stop:
        title = title[: stop.start()]
    previous = None
    while previous != title:
        previous = title
        title = _TITLE_TAIL_RE.sub("", title).strip()
    return title.strip().strip(" ,;")


def _is_office_phrase(title: str) -> bool:
    body = " ".join(str(title or "").split())
    if not body:
        return False
    stripped = _DETERMINER_RE.sub("", body, count=1).strip()
    return bool(_OFFICE_HEAD_RE.match(stripped or body))


def _sentence_declarations(sentence: str) -> list[tuple[str, str]]:
    """(name, title) pairs from one sentence, in whichever order that sentence uses."""
    names = [
        m for m in _NAME_COMMA_RE.finditer(sentence)
        if not _is_office_phrase(m.group("name"))
    ]
    offices = [m for m in _OFFICE_COMMA_RE.finditer(sentence) if _is_office_phrase(m.group("title"))]
    if not names and not offices:
        return []
    name_first = names[0].start("name") if names else len(sentence)
    office_first = offices[0].start() if offices else len(sentence)

    if office_first < name_first:
        # order B: the office introduces the person.
        return [(m.group("name"), _clean_title(m.group("title"))) for m in offices]

    # order A: each name owns the text up to the next declared name.
    pairs: list[tuple[str, str]] = []
    for i, match in enumerate(names):
        start = match.end()
        end = names[i + 1].start() if i + 1 < len(names) else len(sentence)
        title = _clean_title(sentence[start:end])
        if title and _is_office_phrase(title):
            pairs.append((match.group("name"), title))
    return pairs


def _roster_declarations(
    segments: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Same-revision name -> declared office title, with replayable source spans.

    A name declared twice with materially different titles is dropped rather than
    guessed at, which leaves the respondent unsupported and refuses fail-closed.
    """
    found: dict[str, dict[str, Any]] = {}
    for index, seg in enumerate(segments):
        body = " ".join(_text(seg).split())
        for sentence in _split_sentences(body):
            for name, title in _sentence_declarations(sentence):
                key = _norm_person(name)
                if not key or not title:
                    continue
                entry = found.setdefault(key, {"titles": {}, "span_indexes": []})
                entry["titles"].setdefault(title, None)
                if index not in entry["span_indexes"]:
                    entry["span_indexes"].append(index)
    resolved: dict[str, dict[str, Any]] = {}
    for key, entry in found.items():
        titles = list(entry["titles"])
        if len(titles) != 1:
            continue  # ambiguous same-revision declaration: no support, fail closed
        resolved[key] = {"role": titles[0], "span_indexes": entry["span_indexes"]}
    return resolved


def _roster_support(
    roster: Mapping[str, Mapping[str, Any]], speaker: str
) -> Mapping[str, Any] | None:
    """Exact name, or a unique source-native alias that prefixes the speaker's name.

    SCCO declares "Mr. Raul Jacob" while the answering speaker is
    "Raul Jacob Ruisanchez"; the prefix must be unique across declarations so an
    alias can never bind to two different people.
    """
    key = _norm_person(speaker)
    if not key:
        return None
    if key in roster:
        return roster[key]
    tokens = key.split(" ")
    hits = [
        entry
        for declared, entry in roster.items()
        if declared.split(" ") == tokens[: len(declared.split(" "))]
        and len(declared.split(" ")) < len(tokens)
    ]
    return hits[0] if len(hits) == 1 else None


def _roles_compatible(segment_role: str, declared_title: str) -> bool:
    """Closed-alias comparison. Absent either side, there is nothing to conflict."""
    role = " ".join(str(segment_role or "").split()).casefold()
    title = " ".join(str(declared_title or "").split()).casefold()
    if not role or not title:
        return True
    forms = {role}
    if role in _ROLE_ALIASES:
        forms.add(_ROLE_ALIASES[role])
    for abbreviation, expanded in _ROLE_ALIASES.items():
        if role == expanded:
            forms.add(abbreviation)
    return any(re.search(rf"\b{re.escape(form)}\b", title) for form in forms)


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
    roster: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    roster = roster or {}
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
        if _is_management(seg, parsed["name"], roster):
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
        elif _is_management(seg, questioner_name, roster):
            if not _speaker_name(seg):
                return {
                    "status": "failed",
                    "failure": {
                        "code": "management_identity_insufficient",
                        "message": f"management segment {idx} missing speaker",
                    },
                }
            support = _roster_support(roster, _speaker_name(seg))
            declared = str(support["role"]) if support else ""
            if not _roles_compatible(_role_key(seg), declared):
                return {
                    "status": "failed",
                    "failure": {
                        "code": "management_identity_conflict",
                        "message": (
                            f"segment {idx} role {str(seg.get('role') or '')!r} conflicts "
                            f"with same-revision declaration {declared!r}"
                        ),
                    },
                }
            if not _role_key(seg) and not declared:
                return {
                    "status": "failed",
                    "failure": {
                        "code": "management_identity_insufficient",
                        "message": f"management segment {idx} has no same-revision role support",
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

    respondents = _answer_turns(segments, start, end, kinds, answer_spans, roster)
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
    roster: Mapping[str, Mapping[str, Any]] | None = None,
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
        evidence: dict[str, Any] | None = None
        if not role:
            support = _roster_support(roster or {}, name)
            if support:
                # Extended respondent: role is carried by same-revision roster/title
                # text rather than by this segment's own role metadata. The source
                # title phrase is published whole, never relabelled to fit a consumer.
                role = str(support["role"])
                spans = [
                    span
                    for span in (
                        _whole_segment_span(segments[i], i) for i in support["span_indexes"]
                    )
                    if span is not None
                ]
                if spans:
                    evidence = {
                        "schema": "qa_respondent_identity_evidence.v1",
                        "method": "transcript_roster",
                        "role_source_spans": spans,
                    }
        span_i = index_by_seg[idx]
        if current is None or current["name"] != name:
            close()
            current = {
                "name": name,
                "role": role,
                "identity_state": "source_supported",
                "span_indexes": [span_i],
            }
            if evidence is not None:
                current["identity_evidence"] = evidence
        else:
            current["span_indexes"].append(span_i)
    close()
    return turns
