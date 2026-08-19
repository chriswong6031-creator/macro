"""Canonical identity and ordered-prefix receipts for source manifests.

The manifest ID commits to the entire canonical manifest body except the ID
field itself.  This module is deliberately pure and dependency-free so both
the online collector and offline compiler can enforce the same identity law.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
import hashlib
import hmac
import json
import math
import re
from typing import Any


MANIFEST_ID_PREFIX = "manifest:cs:"
EVIDENCE_ID_PREFIX = "evidence:cs:"
# Frozen key_format 1: occurrence is ``"submission"`` or
# ``{parent_content_sha256, byte_start, byte_end}`` from
# ``document_inner_spans``. Changing that scanner requires key_format 2.
EVIDENCE_KEY_FORMAT = 1
_CHILD_OCCURRENCE_KEYS = ("parent_content_sha256", "byte_start", "byte_end")
_EXCLUDED_EVIDENCE_FIELDS = frozenset({
    "retrieved_at",
    "first_seen_at",
    "attempted_at",
    "retained_available_at",
    "file_number",
    "file_number_provenance",
    "ticker",
    "aliases",
    "parser_version",
    "parser",
    "issuer_id",
    "cik",
    "document_role",
    "document_version",
    "document_name",
    "filename",
    "sequence",
    "object_key",
    "store_id",
    "backend",
    "source_id",
    "manifest_id",
})
_SEC_LINE_FLAGS = re.IGNORECASE | re.MULTILINE
_SEC_STRUCTURAL_LINE_FLAGS = re.MULTILINE
_SEC_DOCUMENT_LINE_RE = re.compile(
    br"^<SEC-DOCUMENT>([0-9]{10}-[0-9]{2}-[0-9]{6})\.txt"
    br"(?:[ \t]*:[ \t]*[0-9]{8})?[ \t]*\r?$",
    _SEC_STRUCTURAL_LINE_FLAGS,
)
# EDGAR always writes the header opener with its own ``.hdr.sgml`` payload, e.g.
# ``<SEC-HEADER>0001213900-26-080882.hdr.sgml : 20260723``. A bare ``<SEC-HEADER>``
# is a grammar EDGAR does not emit, so this mirrors ``_SEC_DOCUMENT_LINE_RE``
# above exactly: the accession is captured and pinned to the submission's own
# accession, and only the trailing date is optional.
_SEC_HEADER_OPEN_LINE_RE = re.compile(
    br"^<SEC-HEADER>([0-9]{10}-[0-9]{2}-[0-9]{6})\.hdr\.sgml"
    br"(?:[ \t]*:[ \t]*[0-9]{8})?[ \t]*\r?$",
    _SEC_STRUCTURAL_LINE_FLAGS,
)
_SEC_HEADER_CLOSE_LINE_RE = re.compile(
    br"^</SEC-HEADER>[ \t]*\r?$", _SEC_STRUCTURAL_LINE_FLAGS,
)
_SEC_DOCUMENT_OPEN_LINE_RE = re.compile(
    br"^<DOCUMENT>[ \t]*\r?$", _SEC_STRUCTURAL_LINE_FLAGS,
)
_SEC_DOCUMENT_CHILD_CLOSE_RE = re.compile(br"</DOCUMENT>")
_SEC_DOCUMENT_CLOSE_LINE_RE = re.compile(
    br"^</SEC-DOCUMENT>[ \t]*\r?$", _SEC_STRUCTURAL_LINE_FLAGS,
)
_SEC_HEADER_ACCESSION_LINE_RE = re.compile(
    br"^[ \t]*ACCESSION[ \t]+NUMBER[ \t]*:[ \t]*"
    br"([0-9]{10}-[0-9]{2}-[0-9]{6})[ \t]*\r?$",
    _SEC_LINE_FLAGS,
)
_SEC_HEADER_CIK_LINE_RE = re.compile(
    br"^[ \t]*CENTRAL[ \t]+INDEX[ \t]+KEY[ \t]*:[ \t]*"
    br"([0-9]{1,10})[ \t]*\r?$",
    _SEC_LINE_FLAGS,
)
_SEC_HEADER_FORM_LINE_RE = re.compile(
    br"^[ \t]*CONFORMED[ \t]+SUBMISSION[ \t]+TYPE[ \t]*:[ \t]*"
    br"([^\r\n<]+?)[ \t]*\r?$",
    _SEC_LINE_FLAGS,
)
_SEC_SINGLE_TOKEN_FORM_RE = re.compile(r"^[A-Z0-9]+(?:-[A-Z0-9]+)*(?:/A)?$")
_SEC_SPACED_FORMS = frozenset({
    "1-A POS", "POS AM",
    "PRE 14A", "PRE 14C", "DEF 14A", "DEF 14C",
    "NT 10-K", "NT 10-Q", "NT 20-F", "NT N-CEN",
    "SC 13D", "SC 13D/A", "SC 13G", "SC 13G/A",
    "SC 13E3", "SC 13E3/A", "SC 14D9", "SC 14D9/A",
    "SC 14F1", "SC 14F1/A", "SC TO-C", "SC TO-C/A",
    "SC TO-I", "SC TO-I/A", "SC TO-T", "SC TO-T/A",
})

_SEC_DOCUMENT_TOKEN_RE = re.compile(br"<[ \t]*SEC-DOCUMENT\b", re.IGNORECASE)
_SEC_HEADER_OPEN_TOKEN_RE = re.compile(br"<[ \t]*SEC-HEADER\b", re.IGNORECASE)
_SEC_HEADER_CLOSE_TOKEN_RE = re.compile(br"<[ \t]*/[ \t]*SEC-HEADER\b", re.IGNORECASE)
_SEC_DOCUMENT_OPEN_TOKEN_RE = re.compile(br"<[ \t]*DOCUMENT\b", re.IGNORECASE)
_SEC_DOCUMENT_CHILD_CLOSE_TOKEN_RE = re.compile(
    br"<[ \t]*/[ \t]*DOCUMENT\b", re.IGNORECASE,
)
_SEC_DOCUMENT_CLOSE_TOKEN_RE = re.compile(
    br"<[ \t]*/[ \t]*SEC-DOCUMENT\b", re.IGNORECASE,
)
_SEC_HEADER_ACCESSION_TOKEN_RE = re.compile(
    br"ACCESSION\s+NUMBER", re.IGNORECASE,
)
_SEC_HEADER_CIK_TOKEN_RE = re.compile(
    br"CENTRAL\s+INDEX\s+KEY", re.IGNORECASE,
)
_SEC_HEADER_FORM_TOKEN_RE = re.compile(
    br"CONFORMED\s+SUBMISSION\s+TYPE", re.IGNORECASE,
)


class ManifestIdentityError(ValueError):
    """A source manifest or ordered ledger violates immutable identity law."""


class EvidenceIdentityError(ValueError):
    """Occurrence+bytes evidence identity cannot be derived or does not bind."""


def _native(value: Any) -> Any:
    """Normalize Arrow/numpy-like containers without importing those packages."""
    if isinstance(value, Mapping):
        return {str(key): _native(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_native(item) for item in value]
    if isinstance(value, set):
        raise TypeError("sets are not canonical manifest values")
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TypeError("non-finite numbers are not canonical manifest values")
        return value
    if hasattr(value, "tolist"):
        converted = value.tolist()
        if converted is not value:
            return _native(converted)
    if hasattr(value, "item"):
        converted = value.item()
        if converted is not value:
            return _native(converted)
    raise TypeError(f"unsupported canonical manifest value: {type(value).__name__}")


def canonical_manifest_bytes(record: Mapping[str, Any]) -> bytes:
    """Return canonical UTF-8 JSON for one full manifest record."""
    return json.dumps(
        _native(record),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def manifest_id_for(record: Mapping[str, Any]) -> str:
    """Return ``manifest:cs:<sha256>`` over the body excluding ``manifest_id``."""
    body = dict(record)
    body.pop("manifest_id", None)
    digest = hashlib.sha256(canonical_manifest_bytes(body)).hexdigest()
    return MANIFEST_ID_PREFIX + digest


def document_inner_spans(raw: bytes) -> tuple[tuple[int, int], ...]:
    """Return ``(byte_start, byte_end)`` inner spans for each canonical DOCUMENT.

    key_format 1 frozen rule: inner span is ``[opener.end(), closer.start())``
    for each ordered non-nested ``<DOCUMENT>`` line opener paired with its
    ``</DOCUMENT>`` closer. Changing this pairing requires ``key_format: 2``.
    """
    if not isinstance(raw, bytes):
        raise EvidenceIdentityError("complete-submission bytes are required")
    openers = list(_SEC_DOCUMENT_OPEN_LINE_RE.finditer(raw))
    open_tokens = list(_SEC_DOCUMENT_OPEN_TOKEN_RE.finditer(raw))
    closers = list(_SEC_DOCUMENT_CHILD_CLOSE_RE.finditer(raw))
    close_tokens = list(_SEC_DOCUMENT_CHILD_CLOSE_TOKEN_RE.finditer(raw))
    if not openers or len(openers) != len(open_tokens):
        raise EvidenceIdentityError(
            "complete-submission lacks canonical DOCUMENT opener line(s)"
        )
    if len(closers) != len(close_tokens) or len(closers) != len(openers):
        raise EvidenceIdentityError(
            "complete-submission must contain one canonical DOCUMENT closer "
            "for each opener"
        )
    events = sorted(
        [(match.start(), "open", index) for index, match in enumerate(openers)]
        + [(match.start(), "close", index) for index, match in enumerate(closers)]
    )
    depth = 0
    open_index: int | None = None
    pairs: list[tuple[int, int]] = []
    for _position, event, index in events:
        if event == "open":
            if depth != 0:
                raise EvidenceIdentityError(
                    "SEC DOCUMENT openers/closers are nested or out of order"
                )
            depth = 1
            open_index = index
        else:
            if depth != 1 or open_index is None:
                raise EvidenceIdentityError("SEC DOCUMENT closer precedes its opener")
            opener = openers[open_index]
            closer = closers[index]
            if closer.start() < opener.end():
                raise EvidenceIdentityError("SEC DOCUMENT inner span is empty or inverted")
            pairs.append((opener.end(), closer.start()))
            depth = 0
            open_index = None
    if depth != 0:
        raise EvidenceIdentityError("SEC DOCUMENT opener lacks its ordered closer")
    return tuple(pairs)


def child_occurrence(
    *,
    parent_content_sha256: str,
    byte_start: int,
    byte_end: int,
) -> dict[str, Any]:
    """Return the frozen child occurrence object for key_format 1."""
    digest = str(parent_content_sha256 or "").lower()
    if not _is_sha256(digest):
        raise EvidenceIdentityError("parent_content_sha256 must be lowercase SHA-256")
    if isinstance(byte_start, bool) or isinstance(byte_end, bool):
        raise EvidenceIdentityError("child occurrence byte range must be integers")
    if not isinstance(byte_start, int) or not isinstance(byte_end, int):
        raise EvidenceIdentityError("child occurrence byte range must be integers")
    if not 0 <= byte_start < byte_end:
        raise EvidenceIdentityError("child occurrence byte range is empty or inverted")
    return {
        "byte_end": byte_end,
        "byte_start": byte_start,
        "parent_content_sha256": digest,
    }


def normalize_occurrence(occurrence: Any) -> Any:
    """Canonicalize an occurrence value; refuse interpretation substitutes."""
    if occurrence == "submission":
        return "submission"
    if isinstance(occurrence, str) and occurrence.startswith("legacy:"):
        if occurrence == "legacy:":
            raise EvidenceIdentityError("legacy occurrence requires a source_id")
        return occurrence
    if isinstance(occurrence, Mapping):
        extra = set(occurrence) - set(_CHILD_OCCURRENCE_KEYS)
        missing = [key for key in _CHILD_OCCURRENCE_KEYS if key not in occurrence]
        if extra:
            raise EvidenceIdentityError(
                f"child occurrence contains excluded keys: {sorted(extra)}"
            )
        if missing:
            raise EvidenceIdentityError(
                f"child occurrence missing {missing}"
            )
        return child_occurrence(
            parent_content_sha256=str(occurrence["parent_content_sha256"]),
            byte_start=occurrence["byte_start"],
            byte_end=occurrence["byte_end"],
        )
    raise EvidenceIdentityError("occurrence must be submission, child coords, or legacy")


def evidence_preimage(
    *,
    source_system: str,
    submission_accession: str,
    occurrence: Any,
    content_sha256: str,
    key_format: int = EVIDENCE_KEY_FORMAT,
) -> dict[str, Any]:
    """Return the canonical evidence_id preimage. No clocks. No interpretation."""
    if key_format != EVIDENCE_KEY_FORMAT:
        raise EvidenceIdentityError(f"unsupported evidence key_format: {key_format}")
    system = str(source_system or "").strip()
    accession = str(submission_accession or "").strip()
    digest = str(content_sha256 or "").lower()
    if not system:
        raise EvidenceIdentityError("source_system is required")
    if not accession:
        raise EvidenceIdentityError("submission_accession is required")
    if not _is_sha256(digest):
        raise EvidenceIdentityError("content_sha256 must be lowercase SHA-256")
    return {
        "content_sha256": digest,
        "key_format": int(key_format),
        "occurrence": normalize_occurrence(occurrence),
        "source_system": system,
        "submission_accession": accession,
    }


def evidence_id_for(
    *,
    source_system: str,
    submission_accession: str,
    occurrence: Any,
    content_sha256: str,
    key_format: int = EVIDENCE_KEY_FORMAT,
    **rejected: Any,
) -> str:
    """Return ``evidence:cs:<sha256>`` over occurrence + retained bytes only."""
    if rejected:
        raise EvidenceIdentityError(
            "evidence identity refuses interpretation/clock fields: "
            + ", ".join(sorted(rejected))
        )
    preimage = evidence_preimage(
        source_system=source_system,
        submission_accession=submission_accession,
        occurrence=occurrence,
        content_sha256=content_sha256,
        key_format=key_format,
    )
    digest = hashlib.sha256(canonical_manifest_bytes(preimage)).hexdigest()
    return EVIDENCE_ID_PREFIX + digest


def evidence_occurrence_from_manifest(record: Mapping[str, Any]) -> Any:
    """Project occurrence from a v1 or v2 manifest row without rewriting it."""
    explicit = record.get("evidence_occurrence")
    if explicit is not None:
        return normalize_occurrence(explicit)
    document = record.get("document") or {}
    role = str(document.get("document_role") or "")
    if role == "complete_submission":
        return "submission"
    source_id = str(record.get("source_id") or "")
    if not source_id:
        raise EvidenceIdentityError("legacy child occurrence requires source_id")
    return f"legacy:{source_id}"


def evidence_id_from_manifest(record: Mapping[str, Any]) -> str:
    """Derive evidence_id from a row's own bytes. Does not rewrite the row."""
    explicit = record.get("evidence_id")
    filing = record.get("filing") or {}
    document = record.get("document") or {}
    derived = evidence_id_for(
        source_system=str(record.get("source_system") or ""),
        submission_accession=str(filing.get("accession") or ""),
        occurrence=evidence_occurrence_from_manifest(record),
        content_sha256=str(document.get("content_sha256") or ""),
    )
    if isinstance(explicit, str) and explicit and not hmac.compare_digest(explicit, derived):
        raise EvidenceIdentityError(
            f"stored evidence_id does not match occurrence+bytes: {explicit}"
        )
    return derived


def published_first_known_at(
    evidence_id: str,
    published_records: Sequence[Mapping[str, Any]],
    *,
    candidate_timestamp: str,
) -> str:
    """Freeze canonical first_known_at at first published row for this evidence.

    A later competing observation with an earlier local timestamp cannot move
    the published boundary backward. Ledger prefix order is publication order.
    """
    if not str(candidate_timestamp or "").strip():
        raise EvidenceIdentityError("candidate first_known_at is required")
    for record in published_records:
        try:
            if evidence_id_from_manifest(record) != evidence_id:
                continue
        except (EvidenceIdentityError, ManifestIdentityError, TypeError, ValueError):
            continue
        existing = record.get("first_known_at")
        if isinstance(existing, str) and existing.strip():
            return existing
    return candidate_timestamp


def validate_manifest_identity(record: Mapping[str, Any]) -> None:
    """Fail closed unless the supplied ID exactly commits to the full body."""
    actual = record.get("manifest_id")
    expected = manifest_id_for(record)
    if not isinstance(actual, str) or not hmac.compare_digest(actual, expected):
        raise ManifestIdentityError(
            f"source manifest identity mismatch: expected {expected}, got {actual!r}"
        )


def validate_manifest_ledger(records: Sequence[Mapping[str, Any]]) -> None:
    """Validate every identity and reject duplicate or divergent global IDs."""
    seen: dict[str, bytes] = {}
    for index, record in enumerate(records):
        try:
            validate_manifest_identity(record)
            encoded = canonical_manifest_bytes(record)
        except (ManifestIdentityError, TypeError, ValueError) as exc:
            raise ManifestIdentityError(f"source ledger row {index}: {exc}") from exc
        manifest_id = str(record["manifest_id"])
        prior = seen.get(manifest_id)
        if prior is not None:
            reason = "divergent" if prior != encoded else "duplicate"
            raise ManifestIdentityError(
                f"source ledger row {index}: {reason} global manifest_id {manifest_id}"
            )
        seen[manifest_id] = encoded


def validate_manifest_content_binding(record: Mapping[str, Any]) -> None:
    """Require a manifest's hash, object key, and root span to bind the same bytes.

    Schema validation checks field shapes and immutable identity checks the full
    manifest body. This semantic guard prevents a well-formed, re-signed body
    from pointing one of those three coordinates at a different object.
    """
    document = record.get("document") or {}
    storage = record.get("storage") or {}
    digest = str(document.get("content_sha256") or "").lower()
    if not _is_sha256(digest):
        raise ManifestIdentityError("document.content_sha256 must be lowercase SHA-256")
    if str(document.get("root_locator") or "").lower() != f"sha256:{digest}":
        raise ManifestIdentityError("document.root_locator must bind document.content_sha256")
    object_key = str(storage.get("object_key") or "")
    if object_key != f"capital_structure/sec/sha256/{digest[:2]}/{digest}":
        raise ManifestIdentityError("storage.object_key must bind document.content_sha256")
    byte_length = document.get("byte_length")
    if isinstance(byte_length, bool) or not isinstance(byte_length, int) or byte_length < 0:
        raise ManifestIdentityError("document.byte_length must be a non-negative integer")
    expected_locator = f"bytes:0-{byte_length}"
    matches = [
        span for span in (record.get("spans") or [])
        if isinstance(span, Mapping)
        and str(span.get("locator_type") or "") == "document"
        and str(span.get("locator") or "") == expected_locator
        and str(span.get("text_sha256") or "").lower() == digest
    ]
    if not matches:
        raise ManifestIdentityError("manifest lacks exact document root span")


def _canonical_cik(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw.isdigit() or len(raw) > 10:
        raise ManifestIdentityError("SEC CIK must be one to ten decimal digits")
    return raw.zfill(10)


def _canonical_sec_form(value: Any) -> str:
    """Normalize only case and whitespace; never collapse amendment status."""
    raw = " ".join(str(value or "").strip().upper().split())
    if (
        not raw
        or (
            _SEC_SINGLE_TOKEN_FORM_RE.fullmatch(raw) is None
            and raw not in _SEC_SPACED_FORMS
        )
    ):
        raise ManifestIdentityError("SEC submission form is malformed")
    return raw


def _exact_protected_matches(
    raw: bytes,
    *,
    token_pattern: re.Pattern[bytes],
    line_pattern: re.Pattern[bytes],
    label: str,
    count: int = 1,
) -> list[re.Match[bytes]]:
    """Reject missing, duplicate, or substring/lookalike protected SEC lines."""
    tokens = list(token_pattern.finditer(raw))
    matches = list(line_pattern.finditer(raw))
    if len(tokens) != count or len(matches) != count:
        raise ManifestIdentityError(
            f"SEC complete-submission must contain exactly {count} canonical {label} line(s)"
        )
    return matches


def _repeatable_protected_matches(
    raw: bytes,
    *,
    token_pattern: re.Pattern[bytes],
    line_pattern: re.Pattern[bytes],
    label: str,
) -> list[re.Match[bytes]]:
    """Same lookalike defense as ``_exact_protected_matches`` for repeatable lines.

    A submission may carry several ``FILER:`` blocks (co-registrants), so the
    line legitimately repeats.  The protection that matters is unchanged: every
    occurrence of the bare token must also parse as a canonical line, so no
    substring or lookalike can be smuggled past the parser.  Only the fixed
    arity is relaxed, never the one-for-one token/line parity.
    """
    tokens = list(token_pattern.finditer(raw))
    matches = list(line_pattern.finditer(raw))
    if not matches or len(tokens) != len(matches):
        raise ManifestIdentityError(
            f"SEC complete-submission must contain canonical {label} line(s)"
        )
    return matches


def _complete_submission_header(
    raw: bytes, *, accession_match: re.Match[bytes], outer_close: re.Match[bytes],
) -> bytes:
    """Return the one ordered SEC header inside a canonical outer envelope."""
    open_match = _exact_protected_matches(
        raw,
        token_pattern=_SEC_HEADER_OPEN_TOKEN_RE,
        line_pattern=_SEC_HEADER_OPEN_LINE_RE,
        label="SEC-HEADER opener",
    )[0]
    if open_match.group(1) != accession_match.group(1):
        raise ManifestIdentityError(
            "SEC-HEADER opener accession conflicts with SEC-DOCUMENT accession"
        )
    close_tokens = list(_SEC_HEADER_CLOSE_TOKEN_RE.finditer(raw))
    close_matches = list(_SEC_HEADER_CLOSE_LINE_RE.finditer(raw))
    if len(close_tokens) != len(close_matches) or len(close_matches) > 1:
        raise ManifestIdentityError(
            "SEC complete-submission contains a non-canonical or duplicate SEC-HEADER closer"
        )
    document_tokens = list(_SEC_DOCUMENT_OPEN_TOKEN_RE.finditer(raw))
    document_matches = list(_SEC_DOCUMENT_OPEN_LINE_RE.finditer(raw))
    if len(document_tokens) != len(document_matches) or not document_matches:
        raise ManifestIdentityError(
            "SEC complete-submission contains a non-canonical or missing DOCUMENT opener"
        )
    document_close_tokens = list(_SEC_DOCUMENT_CHILD_CLOSE_TOKEN_RE.finditer(raw))
    # EDGAR commonly appends ``</DOCUMENT>`` directly after ``</TEXT>`` rather
    # than placing it on its own line. The structural token itself must still be
    # exact uppercase ASCII, one-for-one with each canonical line opener.
    document_close_matches = list(_SEC_DOCUMENT_CHILD_CLOSE_RE.finditer(raw))
    if (
        len(document_close_tokens) != len(document_close_matches)
        or len(document_close_matches) != len(document_matches)
    ):
        raise ManifestIdentityError(
            "SEC complete-submission must contain one canonical DOCUMENT closer "
            "for each opener"
        )
    first_document = document_matches[0]
    if any(match.start() < open_match.end() for match in document_matches):
        raise ManifestIdentityError("SEC DOCUMENT opener precedes the canonical SEC header")
    if not accession_match.end() <= open_match.start() < first_document.start():
        raise ManifestIdentityError("SEC header is not followed by a canonical DOCUMENT opener")
    if any(match.start() >= outer_close.start() for match in document_matches):
        raise ManifestIdentityError("SEC DOCUMENT opener is outside the outer SEC-DOCUMENT envelope")
    if any(
        match.start() <= open_match.end() or match.start() >= outer_close.start()
        for match in document_close_matches
    ):
        raise ManifestIdentityError(
            "SEC DOCUMENT closer is outside the outer/header envelope"
        )
    document_events = sorted(
        [(match.start(), "open") for match in document_matches]
        + [(match.start(), "close") for match in document_close_matches]
    )
    document_depth = 0
    for _position, event in document_events:
        if event == "open":
            if document_depth != 0:
                raise ManifestIdentityError(
                    "SEC DOCUMENT openers/closers are nested or out of order"
                )
            document_depth = 1
        else:
            if document_depth != 1:
                raise ManifestIdentityError(
                    "SEC DOCUMENT closer precedes its opener"
                )
            document_depth = 0
    if document_depth != 0:
        raise ManifestIdentityError("SEC DOCUMENT opener lacks its ordered closer")
    if close_matches:
        close_match = close_matches[0]
        if not open_match.end() <= close_match.start() < first_document.start():
            raise ManifestIdentityError("SEC-HEADER closer is outside the canonical header block")
        end = close_match.start()
    else:
        end = first_document.start()
    return raw[open_match.end():end]


def _complete_submission_envelope(
    raw: bytes, accession_match: re.Match[bytes],
) -> tuple[bytes, re.Match[bytes]]:
    """Validate the canonical SEC-DOCUMENT -> SEC-HEADER -> DOCUMENT grammar.

    The retained object is the complete submission itself, so no transport
    preamble or trailing payload is admissible.  This is intentionally stricter
    than searching for useful tags inside arbitrary bytes: the accession line
    must be the first line and the single outer closer must terminate the file
    except for ASCII whitespace.
    """
    if accession_match.start() != 0:
        raise ManifestIdentityError(
            "SEC-DOCUMENT accession must be the canonical first line"
        )
    close_match = _exact_protected_matches(
        raw,
        token_pattern=_SEC_DOCUMENT_CLOSE_TOKEN_RE,
        line_pattern=_SEC_DOCUMENT_CLOSE_LINE_RE,
        label="SEC-DOCUMENT closer",
    )[0]
    if close_match.start() <= accession_match.end():
        raise ManifestIdentityError("SEC-DOCUMENT closer is out of order")
    if raw[close_match.end():].strip(b" \t\r\n"):
        raise ManifestIdentityError(
            "SEC-DOCUMENT closer must terminate the complete submission"
        )
    header = _complete_submission_header(
        raw, accession_match=accession_match, outer_close=close_match,
    )
    return header, close_match


def validate_manifest_retained_bytes_binding(
    record: Mapping[str, Any], raw: bytes | None,
) -> None:
    """Bind SEC manifest identity fields to the retained complete-submission bytes.

    A manifest ID is an immutable *commitment*, not a signature.  Rehashing a
    forged envelope must therefore still fail against the SEC submission header:
    the canonical top accession, header accession, required header CIK, form,
    and manifest coordinates must all agree. This closes the otherwise self-consistent
    ``manifest -> direct observation -> candidate`` issuer rewrite path.
    """
    validate_manifest_content_binding(record)
    if not isinstance(raw, bytes):
        raise ManifestIdentityError("retained source bytes are required")
    document = record.get("document") or {}
    expected_digest = str(document.get("content_sha256") or "").lower()
    if hashlib.sha256(raw).hexdigest() != expected_digest:
        raise ManifestIdentityError("retained source bytes fail manifest digest")
    if (
        str(record.get("source_system") or "") != "sec_edgar"
        or str(document.get("document_role") or "") != "complete_submission"
    ):
        return

    accession_match = _exact_protected_matches(
        raw,
        token_pattern=_SEC_DOCUMENT_TOKEN_RE,
        line_pattern=_SEC_DOCUMENT_LINE_RE,
        label="SEC-DOCUMENT accession",
    )[0]
    header, _outer_close = _complete_submission_envelope(raw, accession_match)
    source_accession = accession_match.group(1).decode("ascii")
    filing = record.get("filing") or {}
    if str(filing.get("accession") or "") != source_accession:
        raise ManifestIdentityError("manifest filing.accession is detached from SEC submission header")
    source_id = str(record.get("source_id") or "")
    expected_source_id = f"{source_accession}:0:complete-submission.txt"
    if source_id != expected_source_id:
        raise ManifestIdentityError("manifest source_id is detached from SEC submission header")

    header_accession_match = _exact_protected_matches(
        header,
        token_pattern=_SEC_HEADER_ACCESSION_TOKEN_RE,
        line_pattern=_SEC_HEADER_ACCESSION_LINE_RE,
        label="ACCESSION NUMBER",
    )[0]
    header_accession = header_accession_match.group(1).decode("ascii")
    if header_accession != source_accession:
        raise ManifestIdentityError("SEC header accession conflicts with SEC-DOCUMENT accession")
    header_form_match = _exact_protected_matches(
        header,
        token_pattern=_SEC_HEADER_FORM_TOKEN_RE,
        line_pattern=_SEC_HEADER_FORM_LINE_RE,
        label="CONFORMED SUBMISSION TYPE",
    )[0]
    header_form = _canonical_sec_form(
        header_form_match.group(1).decode("ascii", errors="strict")
    )
    if _canonical_sec_form(filing.get("form")) != header_form:
        raise ManifestIdentityError("manifest filing.form is detached from SEC submission header")

    # The accession prefix is the CIK of the filing AGENT that transmitted the
    # submission, not the registrant: 0001213900 is Edgar Agents LLC, while the
    # authID Inc. filing it transmitted declares CENTRAL INDEX KEY 0001534154.
    # The two coincide only for self-filers (13 of the 400 filings in the
    # production ledger), so the registrant anchor is the header's own FILER
    # block. A submission may declare several co-registrants, and the manifest
    # issuer must be one of them -- that still pins issuer identity to bytes
    # inside the retained header, closing the manifest -> direct observation ->
    # candidate issuer rewrite path against anyone who cannot rewrite the
    # retained submission itself.
    header_cik_matches = _repeatable_protected_matches(
        header,
        token_pattern=_SEC_HEADER_CIK_TOKEN_RE,
        line_pattern=_SEC_HEADER_CIK_LINE_RE,
        label="CENTRAL INDEX KEY",
    )
    header_ciks = {
        _canonical_cik(match.group(1).decode("ascii")) for match in header_cik_matches
    }
    issuer = record.get("issuer") or {}
    issuer_cik = _canonical_cik(issuer.get("cik"))
    if issuer_cik not in header_ciks:
        raise ManifestIdentityError("manifest issuer.cik is detached from SEC submission header")
    if str(issuer.get("issuer_id") or "") != f"sec:cik:{issuer_cik}":
        raise ManifestIdentityError("manifest issuer_id is detached from SEC submission header")


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def merge_manifest_ledgers(
    existing: Sequence[Mapping[str, Any]],
    fresh: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Append new immutable rows while preserving the exact existing prefix."""
    validate_manifest_ledger(existing)
    out = [_native(record) for record in existing]
    by_id = {
        str(record["manifest_id"]): canonical_manifest_bytes(record)
        for record in out
    }
    fresh_seen: set[str] = set()
    for index, raw in enumerate(fresh):
        record = _native(raw)
        try:
            validate_manifest_identity(record)
        except ManifestIdentityError as exc:
            raise ManifestIdentityError(f"fresh source row {index}: {exc}") from exc
        manifest_id = str(record["manifest_id"])
        encoded = canonical_manifest_bytes(record)
        if manifest_id in fresh_seen:
            raise ManifestIdentityError(
                f"fresh source row {index}: duplicate global manifest_id {manifest_id}"
            )
        fresh_seen.add(manifest_id)
        prior = by_id.get(manifest_id)
        if prior is not None:
            if prior != encoded:
                raise ManifestIdentityError(
                    f"fresh source row {index}: divergent global manifest_id {manifest_id}"
                )
            continue
        by_id[manifest_id] = encoded
        out.append(record)
    return out


def source_ledger_prefix_hash(
    records: Sequence[Mapping[str, Any]], count: int | None = None
) -> str:
    """Return lowercase SHA-256 hex over canonical full records in prefix order."""
    validate_manifest_ledger(records)
    if count is None:
        count = len(records)
    if isinstance(count, bool) or not isinstance(count, int) or not 0 <= count <= len(records):
        raise ValueError("count must select a valid source-ledger prefix")
    canonical_prefix = [_native(record) for record in records[:count]]
    payload = json.dumps(
        canonical_prefix,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
