"""Dark, pure, fail-closed reader for BioCatalyst event-clock projections.

This module turns *injected bytes* into validated ``biopharma.event.v2``
payloads plus a structured quarantine ledger.  It is deliberately inert:

* no network client, no source collector, no local source store;
* no workflow entry point, no DAG node, no synapse registration;
* no file writes, no wall-clock reads, no entropy;
* no live flag, and nothing here is reachable from a render path.

Everything it needs arrives as an argument.  That is what makes it safe to
land before the producer exists.

One honesty note on "no file reads": this module opens nothing itself, but a
payload-supplied ``timezone`` string is handed to the frozen sibling contract,
which resolves it through :class:`zoneinfo.ZoneInfo` — and that reads the
system tzdata.  It is a lookup, not an escape (``ZoneInfo`` refuses absolute
and ``..`` keys), and :data:`_IANA_ZONE_PATTERN` narrows the admissible strings
further before the contract ever sees them, but the flat claim "no file reads"
would be false in the transitive sense, so it is not made.  The purity test
greps this file only; that transitive read is the one it cannot see, and this
paragraph is why the claim it enforces is scoped the way it is.

The expectation is the CONSUMER'S, not a ratified producer contract
----------------------------------------------------------------------
:data:`EXPECTED_PROJECTION_CONTRACT` names the envelope this reader is willing
to interpret.  In plain words: the sister BioCatalyst session owns that
producer contract and has not landed it yet, so the constant below is a
*declared expectation* written from the outside — an assertion about what we
will accept, not evidence that anything emits it.  When W1B lands, a
reconciliation PR pins the exact version and the exact canonical-hash
convention against the real producer, and any disagreement discovered then is
a bug in this file, not in the producer.

Because the expectation is unratified, it is enforced *wholesale*: an envelope
whose ``contract_id`` or ``schema_version`` is not an exact string match is
refused entirely, without reading a single row.  A reader that "mostly"
understood an unknown producer would be the failure mode this design exists to
prevent — a partial read of an unknown dialect is indistinguishable from a
confident misread.

Authority ceiling
-----------------
``DNR:KILL-PHASE3-START-WEIGHT`` is binding here.  A Phase-3 start may be
carried as a display/context fact and may never become a scored leg, so no
accepted event carries a score, weight, rank, priority, or severity field.
That ceiling is structural rather than advisory: ``biopharma.event.v2`` has a
closed key set, so there is nowhere for such a field to live, and
:data:`FORBIDDEN_AUTHORITY_FIELDS` re-checks it anyway.

Similarly, certainty is never manufactured *here*.  Phase, enrollment, sponsor,
and registry status are clinical-sounding fields that a reader could easily be
tempted to compress into a number; this one does not.  A certainty survives
only when the projection row carried one, and is ``None`` otherwise.

That ceiling is one layer deep, and saying so is the point: the row is the
BioCatalyst projection, not the registry, and ``biopharma.event.v2`` carries no
provenance key for ``certainty``.  A producer that derived ``0.8`` from a
Phase-3 start would pass that number through this reader unchallenged, which is
the substance of ``DNR:KILL-PHASE3-START-WEIGHT`` arriving from the other side
of the boundary.  Nothing in this file can detect it, so the W1B reconciliation
owes either a provenance field on the producer contract (``source_asserted`` vs
``producer_derived``) or a decision to drop ``certainty`` on read.  Until then
the number is display-tier only and no promotion may lean on it.

Conservation
------------
For every payload this reader gets far enough to read rows from,
``accepted + quarantined == input_rows``, and that arithmetic is asserted in
code (raising :class:`~engine.seasonality.contracts.ContractError` if it ever
fails) as well as in the tests.  A row that is neither accepted nor explained
is a silently dropped fact.

A whole-envelope refusal is the one shape where the sum does not close, and it
does not close *on purpose*: nothing was read, so ``accepted`` is 0 and a
single ledger entry explains the entire packet rather than one entry per row.
``input_rows`` still reports how many rows the payload carried, so the loss has
a size — "0 of 7 read" is an operator-actionable statement and "0 of 0" is the
misreport this branch used to emit.

Bitemporal orientation (unratified, W1B)
----------------------------------------
This reader requires ``transaction_from >= retrieved_at`` — it treats
``transaction_from`` as *when we came to know the fact* (``known_at``) and
``retrieved_at`` as *when the row was fetched* (``ingested_at``), which is the
orientation ``biopharma.event.v2`` itself enforces.  The opposite bitemporal
reading (``transaction_from`` as the start of transaction-time validity, hence
at or before retrieval) is at least as common in the literature, and a producer
built to it would be quarantined 100% as ``timestamp_ordering_violation`` while
looking like a data outage.  It fails closed, so it is not a defect — but it is
an unstated assumption on an unratified contract, and reconciling it is a named
W1B item.

Hash conventions (unratified, W1B)
----------------------------------
Two conventions coexist here because two different producers own them: the
envelope's ``packet_hash`` is compared as a **bare** hex digest, while
``canonical_content_sha256`` and the reader's own ``content_hash`` carry the
``sha256:`` prefix that ``biopharma.event.v2`` requires.  Neither is repaired
into the other — a bare digest in a prefixed field is refused as
``corrupt_source_hash`` rather than fixed up.  W1B picks one convention.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from .contracts import (
    EVENT_STATUS_ALLOWLIST_V2,
    EVENT_TYPE_ALLOWLIST_V2,
    ContractError,
    build_bitemporal_event_v2,
    event_v2_content_hash,
    source_temporal_day,
    source_temporal_exact,
    source_temporal_is_study_eligible,
    source_temporal_month,
    source_temporal_quarter,
    source_temporal_range,
    source_temporal_unavailable,
    source_temporal_unparsed,
    source_temporal_year,
)

EVENT_CLOCK_READ_SCHEMA = "seasonality.event_clock_read.v1"

#: The envelope this reader declares it can interpret.  Consumer-side
#: expectation, not a ratified producer contract — see the module docstring.
EXPECTED_PROJECTION_CONTRACT = "biocatalyst_seasonality_event_projection.v1"

#: Exact-match version gate.  A different string is refused wholesale.
EXPECTED_PROJECTION_SCHEMA_VERSION = "1.0.0"

#: BioCatalyst's declared hash scope; anything else cannot be verified here.
EXPECTED_HASH_SCOPE = "canonical_payload_excluding_packet_hash"

#: Ceiling on the injected bytes.  A hostile payload is refused before it is
#: parsed, so an unbounded string never reaches ``json.loads``.
MAX_PROJECTION_BYTES = 4 * 1024 * 1024

#: Ceiling on JSON nesting depth, checked *before* ``json.loads``.  The byte
#: ceiling above is a length gate and says nothing about depth: ``json.loads``
#: recurses per level, so ~10k nested arrays — twenty kilobytes, half a percent
#: of :data:`MAX_PROJECTION_BYTES` — blow the interpreter's recursion limit and
#: raise ``RecursionError``, which is not a ``ValueError`` and would escape as a
#: traceback.  A real projection nests about six levels; 32 is generous.
MAX_PROJECTION_DEPTH = 32

#: Ceiling on any source-supplied text this reader echoes or hashes.  The
#: quarantine ledger is an operator-facing surface, so an unbounded field is a
#: denial-of-attention vector even when it is harmless to parse.
MAX_SOURCE_TEXT_CHARS = 2048

#: Tighter ceiling for the source's own record id, which reaches both the
#: ledger and :func:`derive_event_id`.
MAX_NATIVE_ID_CHARS = 256

#: Ceiling on ``revision.revision_index``.  A revision counter is small; a
#: 10**30 index is a producer defect or a probe, and it reaches ``event_id``.
MAX_REVISION_INDEX = 1_000_000

#: BioCatalyst run-reference shape (mirrors ``engine/biocatalyst``).  Matched
#: with :func:`re.fullmatch` everywhere: ``$`` also matches *before* a trailing
#: newline, so ``re.match`` would admit ``"ctgov_run_x\n"`` as a run reference.
GENERATION_ID_PATTERN = re.compile(r"^ctgov_run_[A-Za-z0-9_-]+$")

#: Conservative IANA zone-key shape.  ``ZoneInfo`` refuses absolute and ``..``
#: keys itself; this narrows the payload-controlled string further before it
#: reaches the sibling contract's tzdata lookup.
_IANA_ZONE_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_+-]*(?:/[A-Za-z0-9_+-]+){0,3}$")

#: Fields an accepted event may never carry.  ``biopharma.event.v2`` already
#: closes its key set; this is the second lock on the same door.
FORBIDDEN_AUTHORITY_FIELDS = frozenset(
    {
        "score",
        "weight",
        "rank",
        "priority",
        "severity",
        "conviction",
        "size",
        "sizing",
    }
)

#: Closed quarantine vocabulary.  A code outside this set is a programming
#: error in this module, not a data condition, and raises.
QUARANTINE_REASON_CODES = frozenset(
    {
        "unknown_envelope_contract",
        "unknown_schema_version",
        "envelope_hash_mismatch",
        "envelope_unparseable",
        "oversized_payload",
        "rows_not_a_list",
        "row_not_an_object",
        "missing_required_field",
        "unknown_event_type",
        "unknown_status",
        "unresolved_issuer",
        "missing_transaction_from",
        "unparsable_timestamp",
        "timestamp_ordering_violation",
        "no_usable_effective_bound",
        "duplicate_event_id",
        "contradictory_revision",
        "corrupt_source_hash",
        "missing_source_attribution",
        "stale_generation",
        "path_traversal_attempt",
        "unsafe_source_text",
        "contract_error",
    }
)

_ENVELOPE_REQUIRED_KEYS = (
    "contract_id",
    "schema_version",
    "packet_id",
    "packet_hash",
    "hash_scope",
    "generation_id",
    "coverage_epoch_id",
    "last_complete_run_ref",
    "rows",
)

_ROW_REQUIRED_KEYS = (
    "source_native_id",
    "event_type",
    "status",
    "transaction_from",
    "retrieved_at",
    "canonical_content_sha256",
    # ``source_attribution`` is deliberately absent: its own refusal code
    # (``missing_source_attribution``) is more useful to an operator than the
    # generic one, so it is read below rather than swept up here.
    "source_effective",
    "revision",
)

_TEMPORAL_KINDS = frozenset(
    {
        "exact_time",
        "exact_date",
        "month",
        "quarter",
        "year",
        "range",
        "unavailable",
        "unparsed",
    }
)

#: Substrings that make a source URI unusable as an attribution.  A projection
#: is data, and a path expression arriving in a URI field is either a producer
#: defect or an attempt to steer a downstream writer; either way it is refused
#: rather than sanitised, because a sanitised traversal is a fact we invented.
#:
#: The list is applied to a *normalised* copy of the value (see
#: :func:`_normalise_for_traversal`), not to the raw string: a literal-substring
#: denylist alone is trivially defeated — ``..%2f..%2f`` carries no ``../`` at
#: all, and ``..⁄..⁄`` uses a separator that is not a slash.
_TRAVERSAL_MARKERS = ("../", "..\\", "\x00", "\\..")

#: Separator lookalikes folded to ``/`` before the traversal scan.  Fullwidth
#: solidus, fraction slash, division slash, and their backslash cousins render
#: like a path separator and are read as one by plenty of downstream software.
_SEPARATOR_LOOKALIKES = {
    0xFF0F: "/",  # FULLWIDTH SOLIDUS
    0x2044: "/",  # FRACTION SLASH
    0x2215: "/",  # DIVISION SLASH
    0xFF3C: "\\",  # FULLWIDTH REVERSE SOLIDUS
    0x29F5: "\\",  # REVERSE SOLIDUS OPERATOR
    0x2216: "\\",  # SET MINUS
}

#: Percent-escapes decoded before the traversal scan.  Only the separators and
#: the dot matter here; this is not a general URL decoder, and it is applied
#: twice so that a double-encoded ``%252e`` is seen as well.
_PERCENT_ESCAPES = (
    ("%2e", "."),
    ("%2f", "/"),
    ("%5c", "\\"),
    ("%00", "\x00"),
    ("%25", "%"),
)

#: The only schemes a ``source_url`` may carry.  A denylist of hostile schemes
#: is a losing game (``javascript:``, ``data:``, ``vbscript:``, ``blob:``, an
#: absolute path with no scheme at all, a UNC ``\\host\share``), so the field is
#: an allowlist instead: an attribution names an http(s) resource or it is not
#: usable as an attribution.
_ALLOWED_SOURCE_URL_SCHEMES = ("http://", "https://")

#: Characters that may never appear in source-supplied text this reader echoes.
#: C0/C1 controls (including the NUL that truncates C string handling), DEL,
#: the bidi overrides and isolates that let ``reg<RLO>istry`` render as
#: something else entirely, and the zero-width joiners used to hide them.
_UNSAFE_TEXT_RE = re.compile(
    "[\u0000-\u001f\u007f-\u009f"  # C0 controls (NUL, tab, newline), DEL, C1 controls
    "\u200b-\u200f"  # zero-width space/joiners, LRM/RLM
    "\u202a-\u202e"  # bidi embeddings and overrides
    "\u2060-\u2064"  # word joiner and invisible operators
    "\u2066-\u2069"  # bidi isolates
    "\ufeff"  # zero-width no-break space / BOM
    "]"
)

_SHA256_REF_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_BARE_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

#: A JSON string literal, used to blank strings out before the depth scan so a
#: bracket inside a string cannot be counted as structure.  The two branches are
#: disjoint, so the match is linear — no catastrophic backtracking.
_JSON_STRING_RE = re.compile(r'"(?:[^"\\]|\\.)*"', re.DOTALL)
_JSON_NON_BRACKET_RE = re.compile(r"[^\[\]{}]+")


class _RowRefusal(Exception):
    """Internal control flow: this row is quarantined, with this reason."""

    def __init__(self, reason_code: str, detail: str, field: str | None = None) -> None:
        if reason_code not in QUARANTINE_REASON_CODES:
            raise ContractError(f"reason_code {reason_code!r} is outside the closed allowlist")
        super().__init__(detail)
        self.reason_code = reason_code
        self.detail = detail
        self.field = field


def resolve_issuer_unavailable(row: Mapping[str, Any]) -> str | None:
    """The default issuer resolver: identity is not available here.

    This module has no issuer map, and it must never grow one by inference.  A
    ticker is not an issuer, a sponsor string is not an issuer, and a trial
    registry number is not an issuer — each of those mappings is many-to-many,
    time-varying, and silently wrong in exactly the cases that matter (a
    reverse split, a spin-out, a co-development deal).  Guessing one would
    attach a real company to an event it may not own.

    So the default answer is ``None``, which quarantines every row as
    ``unresolved_issuer``.  That is the intended default behaviour of the whole
    adapter: with no identity authority injected, it reads nothing.  A caller
    with a real, governed identity service passes it as ``resolve_issuer``.
    """
    return None


def canonical_projection_bytes(payload: object) -> bytes:
    """Canonical JSON bytes, mirroring the repo's ``canonical_json_sha256``.

    Sorted keys, no incidental whitespace, ``ensure_ascii=False``, no NaN, and
    a trailing newline — the same convention ``engine/biocatalyst`` hashes
    under.  The W1B reconciliation PR pins this against the real producer.
    """
    try:
        return (
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
            + b"\n"
        )
    except (TypeError, ValueError) as exc:
        raise ContractError(f"payload is not canonical JSON: {exc}") from exc
    except RecursionError as exc:
        # ``json.dumps`` recurses per level too, so a structure deep enough to
        # survive parsing can still blow the stack on the way out.  A bare
        # ``RecursionError`` is neither a ``TypeError`` nor a ``ValueError``,
        # and this function is exported, so it is converted here rather than
        # left to escape past the caller's ``except ContractError``.
        raise ContractError("payload nests too deeply to canonicalise") from exc


def _canonical_sha256(payload: object) -> str:
    return hashlib.sha256(canonical_projection_bytes(payload)).hexdigest()


def derive_event_id(
    *,
    source_native_id: str,
    event_type: str,
    revision_id: str,
    revision_index: int,
) -> str:
    """Derive a stable ``event_id`` from source-native identity + revision.

    The rule, stated once so it can be tested: the id is
    ``bpev_`` + the first 40 hex characters of the SHA-256 of the canonical
    JSON of ``{source_native_id, event_type, revision_id, revision_index}``.

    Nothing positional enters it.  Not the row's index, not its position in the
    batch, not the order the producer happened to serialise in, and not any
    ticker — a ticker is a lease on a symbol, not an identity, and an id keyed
    to one silently re-points when the lease moves.  ``event_type`` is part of
    the identity because one registry record legitimately emits several
    distinct events (a start and a primary completion), and the revision pair
    is part of it because a corrected event is a different assertion from the
    one it corrects.
    """
    identity = {
        "event_type": event_type,
        "revision_id": revision_id,
        "revision_index": revision_index,
        "source_native_id": source_native_id,
    }
    return "bpev_" + _canonical_sha256(identity)[:40]


# ---------------------------------------------------------------------------
# small typed readers — each refuses rather than coerces
# ---------------------------------------------------------------------------


def _text(value: Any, field: str, *, reason: str = "missing_required_field") -> str:
    if not isinstance(value, str) or not value.strip():
        raise _RowRefusal(reason, f"{field} must be a non-empty string", field)
    return value


def _mapping(value: Any, field: str, *, reason: str = "missing_required_field") -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise _RowRefusal(reason, f"{field} must be an object", field)
    return value


def _instant(value: Any, field: str) -> datetime:
    text = _text(value, field, reason="unparsable_timestamp")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise _RowRefusal(
            "unparsable_timestamp", f"{field} is not an ISO-8601 timestamp", field
        ) from exc
    if parsed.tzinfo is None:
        raise _RowRefusal("unparsable_timestamp", f"{field} carries no timezone", field)
    return parsed.astimezone(timezone.utc)


def _int_field(value: Any, field: str, *, maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise _RowRefusal(
            "missing_required_field", f"{field} must be a non-negative integer", field
        )
    if maximum is not None and value > maximum:
        raise _RowRefusal(
            "missing_required_field", f"{field} must be at most {maximum}", field
        )
    return value


def _safe_text(
    value: Any,
    field: str,
    *,
    reason: str = "missing_required_field",
    max_chars: int = MAX_SOURCE_TEXT_CHARS,
) -> str:
    """A non-empty string that is safe to echo into an operator-facing ledger.

    ``_text`` alone is not enough for anything this reader repeats back.  A NUL
    byte truncates the field in half the software that will ever render it, a
    right-to-left override makes ``reg<RLO>istry`` display as something else
    entirely, and an unbounded string turns one hostile row into a ledger no
    operator will read.  None of those are sanitised — a cleaned-up id is an id
    we invented — so they are refused with their own reason code.
    """
    text = _text(value, field, reason=reason)
    _require_safe_text(text, field, max_chars=max_chars)
    return text


def _require_safe_text(text: str, field: str, *, max_chars: int = MAX_SOURCE_TEXT_CHARS) -> None:
    if len(text) > max_chars:
        raise _RowRefusal(
            "unsafe_source_text",
            f"{field} is {len(text)} characters, over the {max_chars} character ceiling",
            field,
        )
    match = _UNSAFE_TEXT_RE.search(text)
    if match is not None:
        raise _RowRefusal(
            "unsafe_source_text",
            f"{field} carries the control or bidi character U+{ord(match.group()):04X}",
            field,
        )


def _normalise_for_traversal(value: str) -> str:
    """Fold the cheap disguises before looking for a path expression.

    A literal-substring denylist is defeated by the first person who reads it:
    ``..%2f..%2f`` contains no ``../``, ``..%252f`` survives one round of
    decoding, and ``..⁄..⁄`` uses a separator that is not a slash at
    all.  Folding here means the marker list stays short and readable while the
    scan still sees what a downstream path handler would.
    """
    folded = value.lower().translate(_SEPARATOR_LOOKALIKES)
    for _ in range(2):  # one extra pass catches double-encoding (%252e)
        for escape, plain in _PERCENT_ESCAPES:
            folded = folded.replace(escape, plain)
    return folded


def _scan_for_traversal(value: Any, field: str) -> None:
    """Refuse a path expression anywhere in an attribution, at any depth.

    The scan recurses: an attribution's extra keys may be objects or arrays, and
    a traversal one level down is the same traversal.  Non-string scalars are
    simply uninteresting, but they must not *stop* the walk — returning on the
    first non-string is what let ``{"meta": {"p": "../../etc/passwd"}}`` through.
    """
    if isinstance(value, Mapping):
        for key, item in value.items():
            _scan_for_traversal(item, f"{field}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _scan_for_traversal(item, f"{field}[{index}]")
        return
    if not isinstance(value, str):
        return
    _require_safe_text(value, field)
    folded = _normalise_for_traversal(value)
    for marker in _TRAVERSAL_MARKERS:
        if marker in folded:
            raise _RowRefusal(
                "path_traversal_attempt",
                f"{field} carries a path expression and cannot be used as an attribution",
                field,
            )


def _require_http_url(value: str, field: str) -> str:
    """A ``source_url`` names an http(s) resource or it is not an attribution.

    Denylisting hostile schemes never converges — ``javascript:``, ``data:``,
    ``vbscript:``, ``blob:``, a bare absolute path with no scheme and no dots,
    a UNC ``\\\\host\\share`` — so this is an allowlist.
    """
    if not value.lower().startswith(_ALLOWED_SOURCE_URL_SCHEMES):
        raise _RowRefusal(
            "path_traversal_attempt",
            f"{field} is not an http(s) URL and cannot be used as an attribution",
            field,
        )
    return value


def _detached(value: Any) -> Any:
    """A deep, plain-container copy — nothing an injected callable can mutate.

    The whole reason this reader takes *bytes* is that a caller holding a parsed
    dict could mutate it after the producer signed it.  Handing the live row to
    an injected ``resolve_issuer`` would reopen that door from the inside: the
    resolver runs mid-row, and anything it changed would land in the fields read
    after it — including ``known_at``, the point-in-time clock.
    """
    if isinstance(value, Mapping):
        return {key: _detached(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_detached(item) for item in value]
    return value


# ---------------------------------------------------------------------------
# temporal specs -> contract temporal objects (never hand-built)
# ---------------------------------------------------------------------------


def _build_temporal(spec: Any, field: str) -> dict[str, Any]:
    """Turn a declarative source temporal spec into a contract temporal object.

    Every branch delegates to a ``source_temporal_*`` constructor in
    :mod:`engine.seasonality.contracts`.  Nothing here computes a bound, a
    midpoint, or a midnight, so a month cannot acquire a time and a range
    cannot acquire a centre.  A spec this reader does not understand becomes an
    ``unparsable_timestamp`` refusal rather than a guess.
    """
    payload = _mapping(spec, field, reason="unparsable_timestamp")
    kind = payload.get("kind")
    # ``isinstance`` first: ``{} in frozenset`` raises ``TypeError: unhashable
    # type``, and a hostile row must never escape as a traceback.
    if not isinstance(kind, str) or kind not in _TEMPORAL_KINDS:
        raise _RowRefusal(
            "unparsable_timestamp",
            f"{field}.kind must be one of {sorted(_TEMPORAL_KINDS)}",
            f"{field}.kind",
        )
    original = payload.get("original_value")
    if original is not None and not isinstance(original, str):
        raise _RowRefusal(
            "unparsable_timestamp", f"{field}.original_value must be a string", field
        )
    source_timezone = payload.get("timezone")
    if source_timezone is not None and (
        not isinstance(source_timezone, str) or not _IANA_ZONE_PATTERN.fullmatch(source_timezone)
    ):
        # The zone string is the one payload value that reaches a filesystem
        # lookup (``ZoneInfo`` over tzdata, inside the sibling contract), so it
        # is shaped here before it gets there.
        raise _RowRefusal(
            "unparsable_timestamp", f"{field}.timezone must be an IANA zone key", field
        )

    try:
        if kind == "unavailable":
            return source_temporal_unavailable(
                _text(payload.get("reason"), f"{field}.reason", reason="unparsable_timestamp")
            )
        if kind == "unparsed":
            return source_temporal_unparsed(
                _text(
                    payload.get("original_value"),
                    f"{field}.original_value",
                    reason="unparsable_timestamp",
                )
            )
        if kind == "exact_time":
            value = _text(payload.get("value"), f"{field}.value", reason="unparsable_timestamp")
            # ``original if original is not None else value`` rather than
            # ``original or value``: an explicitly empty ``original_value`` is
            # the source asserting nothing, and substituting the machine-
            # readable value for it would put words in the source's mouth.  The
            # contract refuses the empty string, so it surfaces as a refusal.
            return source_temporal_exact(
                value, original_value=value if original is None else original
            )
        if kind == "exact_date":
            value = _text(payload.get("value"), f"{field}.value", reason="unparsable_timestamp")
            return source_temporal_day(
                value, source_timezone=source_timezone, original_value=original
            )
        if kind == "month":
            return source_temporal_month(
                payload.get("year"),
                payload.get("month"),
                source_timezone=source_timezone,
                original_value=original,
            )
        if kind == "quarter":
            return source_temporal_quarter(
                payload.get("year"),
                payload.get("quarter"),
                source_timezone=source_timezone,
                original_value=original,
            )
        if kind == "year":
            return source_temporal_year(
                payload.get("year"),
                source_timezone=source_timezone,
                original_value=original,
            )
        # kind == "range"
        return source_temporal_range(
            _text(payload.get("lower"), f"{field}.lower", reason="unparsable_timestamp"),
            _text(payload.get("upper"), f"{field}.upper", reason="unparsable_timestamp"),
            original_value=_text(
                original, f"{field}.original_value", reason="unparsable_timestamp"
            ),
            source_timezone=source_timezone,
        )
    except ContractError as exc:
        raise _RowRefusal("unparsable_timestamp", f"{field}: {exc}", field) from exc


# ---------------------------------------------------------------------------
# row reading
# ---------------------------------------------------------------------------


def _read_row(
    row: Any,
    *,
    envelope_generation_id: str,
    resolve_issuer: Callable[[Mapping[str, Any]], str | None],
) -> tuple[dict[str, Any], str, int]:
    """Read one projection row into a v2 event.

    Returns ``(event, contradiction_key_native_id, revision_index)`` so the
    caller can detect contradictions across rows.  Raises :class:`_RowRefusal`
    for every data condition; a raised ``ContractError`` here would be a
    programming error in this module.
    """
    payload = _mapping(row, "row", reason="row_not_an_object")

    missing = [key for key in _ROW_REQUIRED_KEYS if payload.get(key) is None]
    if "transaction_from" in missing:
        raise _RowRefusal(
            "missing_transaction_from",
            "transaction_from is the only admissible source for known_at",
            "transaction_from",
        )
    if missing:
        raise _RowRefusal(
            "missing_required_field", f"row is missing required fields {sorted(missing)}", None
        )

    generation_ref = payload.get("generation_ref")
    if generation_ref is not None and generation_ref != envelope_generation_id:
        raise _RowRefusal(
            "stale_generation",
            "row was produced under a different generation than the envelope declares",
            "generation_ref",
        )

    event_type = payload.get("event_type")
    # ``isinstance`` before the membership test, here and for ``status``: a JSON
    # value can be a dict or a list, and ``{} in frozenset`` raises
    # ``TypeError: unhashable type`` rather than returning ``False``.  That
    # traceback escaped ``_read_rows`` (which catches only ``_RowRefusal``) and
    # destroyed every other row in an otherwise well-signed batch.
    if not isinstance(event_type, str) or event_type not in EVENT_TYPE_ALLOWLIST_V2:
        # Never collapse to "other": an unrecognised type is an unread fact,
        # and a bucket named "other" would make it look read.
        raise _RowRefusal(
            "unknown_event_type",
            "event_type is outside the frozen v2 allowlist and is not collapsed to a bucket",
            "event_type",
        )
    status = payload.get("status")
    if not isinstance(status, str) or status not in EVENT_STATUS_ALLOWLIST_V2:
        # Never default to "active"/"scheduled" either, for the same reason.
        raise _RowRefusal(
            "unknown_status",
            "status is outside the frozen v2 allowlist and is not defaulted",
            "status",
        )

    attribution = _mapping(
        payload.get("source_attribution"),
        "source_attribution",
        reason="missing_source_attribution",
    )
    source_class = _safe_text(
        attribution.get("source_class"),
        "source_attribution.source_class",
        reason="missing_source_attribution",
    )
    source_url = _require_http_url(
        _safe_text(
            attribution.get("source_url"),
            "source_attribution.source_url",
            reason="missing_source_attribution",
        ),
        "source_attribution.source_url",
    )
    for key, value in attribution.items():
        _scan_for_traversal(value, f"source_attribution.{key}")

    source_hash = payload.get("canonical_content_sha256")
    # ``fullmatch``, not ``match``: ``$`` also matches immediately before a
    # trailing newline, so ``"sha256:" + "a" * 64 + "\n"`` passed this gate and
    # then died inside the contract as a generic ``contract_error`` — the wrong
    # reason code for an operator triaging a corrupt hash.
    if not isinstance(source_hash, str) or not _SHA256_REF_RE.fullmatch(source_hash):
        if isinstance(source_hash, str) and _BARE_SHA256_RE.fullmatch(source_hash):
            # A bare digest is a different claim from a prefixed one; the v2
            # contract wants the prefix and we do not add it for the producer.
            raise _RowRefusal(
                "corrupt_source_hash",
                "canonical_content_sha256 carries no 'sha256:' prefix",
                "canonical_content_sha256",
            )
        raise _RowRefusal(
            "corrupt_source_hash",
            "canonical_content_sha256 is not a sha256:<64 lowercase hex> reference",
            "canonical_content_sha256",
        )

    # Captured as locals *before* any injected callable runs, and used verbatim
    # in the build below.  Re-reading ``payload[...]`` after ``resolve_issuer``
    # would let a resolver rewrite the point-in-time clocks it was never given
    # authority over, and the ordering checks would have validated the values
    # the row had before the rewrite.
    transaction_from_raw = payload.get("transaction_from")
    retrieved_at_raw = payload.get("retrieved_at")
    known_at = _instant(transaction_from_raw, "transaction_from")
    ingested_at = _instant(retrieved_at_raw, "retrieved_at")

    source_effective = _build_temporal(payload.get("source_effective"), "source_effective")
    if payload.get("source_published") is None:
        # An absent publication time stays explicitly absent.  The system
        # clocks below still carry the anti-leakage invariant.
        source_published = source_temporal_unavailable("source_did_not_state_publication_time")
    else:
        source_published = _build_temporal(payload.get("source_published"), "source_published")
    scheduled_window = (
        None
        if payload.get("scheduled_window") is None
        else _build_temporal(payload.get("scheduled_window"), "scheduled_window")
    )
    actual = (
        None if payload.get("actual") is None else _build_temporal(payload.get("actual"), "actual")
    )

    if not source_temporal_is_study_eligible(source_effective):
        raise _RowRefusal(
            "no_usable_effective_bound",
            "source_effective has no bounded window, so the event has no clock to sit on",
            "source_effective",
        )

    revision = _mapping(payload.get("revision"), "revision")
    revision_id = _safe_text(revision.get("revision_id"), "revision.revision_id")
    revision_index = _int_field(
        revision.get("revision_index"), "revision.revision_index", maximum=MAX_REVISION_INDEX
    )
    supersedes = revision.get("supersedes")
    if supersedes is not None and not isinstance(supersedes, str):
        raise _RowRefusal(
            "missing_required_field", "revision.supersedes must be a string or null", "revision"
        )
    if supersedes is not None:
        _require_safe_text(supersedes, "revision.supersedes")

    certainty = payload.get("certainty")
    if certainty is not None and (isinstance(certainty, bool) or not isinstance(certainty, (int, float))):
        raise _RowRefusal(
            "missing_required_field", "certainty must be a number or null", "certainty"
        )
    # Never derived.  Phase, enrollment, sponsor, and registry status do not
    # produce a certainty here, and there is no branch below that reads them.

    source_native_id = _safe_text(
        payload.get("source_native_id"), "source_native_id", max_chars=MAX_NATIVE_ID_CHARS
    )
    # Scanned like an attribution, because it travels like one: the source's own
    # record id reaches ``derive_event_id`` and is echoed into the ledger, and a
    # registry identifier never legitimately contains a path expression.
    _scan_for_traversal(source_native_id, "source_native_id")

    # Every check the row can fail on its own runs first, so an ordering
    # violation is named as one even under the default resolver, and so the
    # injected authority is only asked about rows this reader could otherwise
    # accept.
    _check_ordering(
        known_at=known_at,
        ingested_at=ingested_at,
        source_published=source_published,
        actual=actual,
    )

    try:
        # A detached copy: the resolver is an injected boundary, and a
        # governed identity service is entitled to read the row, not to edit it.
        issuer_id = resolve_issuer(_detached(payload))
    except Exception as exc:  # an authority's failure is a row condition, not ours
        # A real identity service times out, 500s, or raises on one odd row.
        # None of those are a reason to lose the other rows in the batch, and a
        # traceback out of this reader would do exactly that, so a failing
        # authority is quarantined with the same code as an absent one.
        raise _RowRefusal(
            "unresolved_issuer",
            f"the injected identity authority failed on this row: {type(exc).__name__}: {exc}",
            "issuer_id",
        ) from exc
    if issuer_id is None or not isinstance(issuer_id, str) or not issuer_id.strip():
        raise _RowRefusal(
            "unresolved_issuer",
            "no injected identity authority resolved this row to an issuer",
            "issuer_id",
        )
    _require_safe_text(issuer_id, "issuer_id", max_chars=MAX_NATIVE_ID_CHARS)
    _scan_for_traversal(issuer_id, "issuer_id")

    try:
        event = build_bitemporal_event_v2(
            event_id=derive_event_id(
                source_native_id=source_native_id,
                event_type=event_type,
                revision_id=revision_id,
                revision_index=revision_index,
            ),
            issuer_id=issuer_id,
            event_type=event_type,
            status=status,
            source_class=source_class,
            source_url=source_url,
            source_hash=source_hash,
            known_at=transaction_from_raw,
            ingested_at=retrieved_at_raw,
            source_published=source_published,
            source_effective=source_effective,
            scheduled_window=scheduled_window,
            actual=actual,
            certainty=None if certainty is None else float(certainty),
            revision={
                "revision_id": revision_id,
                "revision_index": revision_index,
                "supersedes": supersedes,
            },
        )
    except ContractError as exc:
        raise _RowRefusal("contract_error", f"biopharma.event.v2 refused this row: {exc}") from exc

    leaked = sorted(FORBIDDEN_AUTHORITY_FIELDS & set(event))
    if leaked:  # pragma: no cover - v2's closed key set makes this unreachable
        raise ContractError(f"accepted event carries authority-shaped keys {leaked}")
    return event, source_native_id, revision_index


def _check_ordering(
    *,
    known_at: datetime,
    ingested_at: datetime,
    source_published: Mapping[str, Any],
    actual: Mapping[str, Any] | None,
) -> None:
    """The three anti-leakage orderings, named before the contract raises them.

    ``biopharma.event.v2`` enforces these itself, but it raises a generic
    :class:`ContractError`, and an operator triaging a quarantine ledger needs
    to know that a row failed *because time ran backwards* rather than because
    of some other contract detail.  ``source_effective`` is deliberately not
    checked: an issuer announcing a future PDUFA date is correct, not leakage.
    """
    if known_at < ingested_at:
        raise _RowRefusal(
            "timestamp_ordering_violation",
            "known_at (transaction_from) precedes ingested_at (retrieved_at)",
            "transaction_from",
        )
    lower = source_published.get("lower_bound")
    if lower is not None:
        published_lower = _instant(lower, "source_published.lower_bound")
        if published_lower > ingested_at:
            raise _RowRefusal(
                "timestamp_ordering_violation",
                "retrieved_at precedes the earliest moment the source could have published",
                "retrieved_at",
            )
    if actual is not None and actual.get("lower_bound") is not None:
        actual_lower = _instant(actual["lower_bound"], "actual.lower_bound")
        if actual_lower > known_at:
            raise _RowRefusal(
                "timestamp_ordering_violation",
                "transaction_from precedes the earliest moment the event could have occurred",
                "actual",
            )


# ---------------------------------------------------------------------------
# envelope reading
# ---------------------------------------------------------------------------


def _max_nesting_depth(text: str, *, ceiling: int) -> int:
    """Deepest JSON nesting in ``text``, giving up as soon as it passes ceiling.

    String literals are blanked first so a bracket inside a value cannot be
    counted as structure, and everything that is not a bracket is dropped by a
    single C-level substitution, so the Python-level loop below runs once per
    bracket rather than once per byte.  The early return keeps a depth bomb
    cheap: it stops at the ceiling instead of walking four megabytes.

    Only a lower bound is promised once the ceiling is passed — which is all the
    caller needs, because it refuses.
    """
    brackets = _JSON_NON_BRACKET_RE.sub("", _JSON_STRING_RE.sub('""', text))
    depth = 0
    deepest = 0
    for char in brackets:
        if char in "[{":
            depth += 1
            if depth > deepest:
                deepest = depth
                if deepest > ceiling:
                    return deepest
        else:
            depth -= 1
    return deepest


def _quarantine(
    *,
    row_index: int | None,
    source_native_id: str | None,
    reason_code: str,
    field: str | None,
    detail: str,
) -> dict[str, Any]:
    if reason_code not in QUARANTINE_REASON_CODES:
        raise ContractError(f"reason_code {reason_code!r} is outside the closed allowlist")
    return {
        "row_index": row_index,
        "source_native_id": source_native_id,
        "reason_code": reason_code,
        "field": field,
        "detail": detail,
    }


def _envelope_refusal(
    *,
    reason_code: str,
    detail: str,
    field: str | None,
    content_hash: str,
    fixture_only: bool,
    unread_rows: int = 0,
) -> dict[str, Any]:
    """A whole-envelope refusal: nothing was read, and that is said out loud.

    ``input_rows`` carries the number of rows the payload actually held, even
    though none of them were read.  Reporting ``0`` here — as this branch used
    to — makes a downstream "we read N of M" metric read ``0 of 0``, i.e. no
    loss at all, when a seven-row packet was dropped.  The sum deliberately does
    not close on this path: one ledger entry explains the whole envelope, and
    the module docstring says so.
    """
    return {
        "schema": EVENT_CLOCK_READ_SCHEMA,
        "accepted": [],
        "quarantined": [
            _quarantine(
                row_index=None,
                source_native_id=None,
                reason_code=reason_code,
                field=field,
                detail=detail,
            )
        ],
        "counts": {"input_rows": unread_rows, "accepted": 0, "quarantined": 1},
        "generation": {
            "generation_id": None,
            "coverage_epoch_id": None,
            "content_hash": content_hash,
            "last_complete_run_ref": None,
        },
        "fixture_only": fixture_only,
    }


def _row_native_id(row: Any) -> str | None:
    """The row's own id, verbatim, or ``None`` — never invented, never cleaned.

    The ledger is an operator-facing surface, so an id carrying a NUL byte, a
    right-to-left override, or two hundred kilobytes of padding is withheld
    rather than sanitised: a scrubbed id is not the source's id, and echoing the
    hostile one puts the payload's choice of characters into whatever renders
    the ledger.  The row is still quarantined either way; it just loses the
    convenience of being named by an id we would not trust.
    """
    if isinstance(row, Mapping):
        value = row.get("source_native_id")
        if (
            isinstance(value, str)
            and value.strip()
            and len(value) <= MAX_NATIVE_ID_CHARS
            and _UNSAFE_TEXT_RE.search(value) is None
        ):
            return value
    return None


def read_event_projection(
    payload_bytes: bytes,
    *,
    resolve_issuer: Callable[[Mapping[str, Any]], str | None] = resolve_issuer_unavailable,
    max_bytes: int = MAX_PROJECTION_BYTES,
    fixture_only: bool = False,
) -> dict[str, Any]:
    """Read injected projection bytes into accepted v2 events + a ledger.

    The argument is *bytes* rather than a parsed object on purpose: the
    envelope's own hash covers its canonical payload, and a caller who handed
    us an already-parsed dict could have mutated it after the producer signed
    it.  Taking bytes keeps the verification and the interpretation on the same
    side of the boundary.

    Bad input never raises out of this function.  A hostile, truncated, deeply
    nested, or simply unknown payload produces a structured refusal —
    ``accepted: []`` plus one envelope-level quarantine row — because a
    traceback is a worse answer than a reason code for something a scheduler
    will one day call unattended.  That covers the whole *input* surface,
    including an injected ``resolve_issuer`` that raises: an identity service's
    outage quarantines its row, it does not lose the batch.  Programming errors
    in this module, and caller-contract errors in this function's own
    arguments, still raise.

    ``fixture_only`` is echoed, and is ORed with a ``fixture_only`` marker
    inside the envelope, so a synthetic payload cannot be laundered into a
    result that claims to be real by the caller passing ``False``.
    """
    if not isinstance(payload_bytes, (bytes, bytearray)):
        raise ContractError("payload_bytes must be bytes")
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes <= 0:
        raise ContractError("max_bytes must be a positive integer")
    if not isinstance(fixture_only, bool):
        raise ContractError("fixture_only must be a boolean")

    content_hash = "sha256:" + hashlib.sha256(payload_bytes).hexdigest()

    if len(payload_bytes) > max_bytes:
        return _envelope_refusal(
            reason_code="oversized_payload",
            detail=f"payload is {len(payload_bytes)} bytes, over the {max_bytes} byte ceiling",
            field=None,
            content_hash=content_hash,
            fixture_only=fixture_only,
        )

    try:
        text = payload_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        return _envelope_refusal(
            reason_code="envelope_unparseable",
            detail=f"payload is not UTF-8: {exc}",
            field=None,
            content_hash=content_hash,
            fixture_only=fixture_only,
        )

    depth = _max_nesting_depth(text, ceiling=MAX_PROJECTION_DEPTH)
    if depth > MAX_PROJECTION_DEPTH:
        # Checked before ``json.loads`` because the parser recurses per level:
        # ~10k nested arrays is twenty kilobytes and raises ``RecursionError``,
        # which is not a ``ValueError`` and would leave as a traceback.
        return _envelope_refusal(
            reason_code="envelope_unparseable",
            detail=(
                f"payload nests at least {depth} levels deep, over the "
                f"{MAX_PROJECTION_DEPTH} level ceiling"
            ),
            field=None,
            content_hash=content_hash,
            fixture_only=fixture_only,
        )

    try:
        envelope = json.loads(text)
    except (ValueError, RecursionError) as exc:
        # ``RecursionError`` as well as ``ValueError``: the depth scan above is
        # the real guard, but a parser whose recursion budget is already spent
        # by the caller must still refuse rather than raise.
        return _envelope_refusal(
            reason_code="envelope_unparseable",
            detail=f"payload is not UTF-8 JSON: {exc}",
            field=None,
            content_hash=content_hash,
            fixture_only=fixture_only,
        )

    if not isinstance(envelope, Mapping):
        return _envelope_refusal(
            reason_code="envelope_unparseable",
            detail="payload is not a JSON object",
            field=None,
            content_hash=content_hash,
            fixture_only=fixture_only,
        )

    declared_fixture_only = envelope.get("fixture_only") is True
    effective_fixture_only = bool(fixture_only or declared_fixture_only)
    # How many facts this refusal is throwing away.  Known from here on, because
    # the payload has parsed; ``0`` when ``rows`` is absent or is not an array,
    # which is itself the honest count of rows we could identify.
    declared_rows = envelope.get("rows")
    unread_rows = len(declared_rows) if isinstance(declared_rows, list) else 0

    def refuse(reason_code: str, detail: str, field: str | None = None) -> dict[str, Any]:
        return _envelope_refusal(
            reason_code=reason_code,
            detail=detail,
            field=field,
            content_hash=content_hash,
            fixture_only=effective_fixture_only,
            unread_rows=unread_rows,
        )

    if envelope.get("contract_id") != EXPECTED_PROJECTION_CONTRACT:
        return refuse(
            "unknown_envelope_contract",
            f"contract_id is not the expected {EXPECTED_PROJECTION_CONTRACT!r}",
            "contract_id",
        )
    if envelope.get("schema_version") != EXPECTED_PROJECTION_SCHEMA_VERSION:
        return refuse(
            "unknown_schema_version",
            f"schema_version is not the expected {EXPECTED_PROJECTION_SCHEMA_VERSION!r}",
            "schema_version",
        )

    absent = [key for key in _ENVELOPE_REQUIRED_KEYS if key not in envelope]
    if absent:
        return refuse(
            "envelope_unparseable", f"envelope is missing required keys {sorted(absent)}", None
        )

    if envelope.get("hash_scope") != EXPECTED_HASH_SCOPE:
        return refuse(
            "envelope_hash_mismatch",
            f"hash_scope is not the verifiable {EXPECTED_HASH_SCOPE!r}",
            "hash_scope",
        )

    declared_hash = envelope.get("packet_hash")
    unhashed = {key: value for key, value in envelope.items() if key != "packet_hash"}
    try:
        recomputed = _canonical_sha256(unhashed)
    except ContractError as exc:
        return refuse("envelope_unparseable", f"envelope is not canonical JSON: {exc}", None)
    if not isinstance(declared_hash, str) or declared_hash != recomputed:
        return refuse(
            "envelope_hash_mismatch",
            "packet_hash does not match the canonical payload excluding packet_hash",
            "packet_hash",
        )

    generation_id = envelope.get("generation_id")
    if not isinstance(generation_id, str) or not GENERATION_ID_PATTERN.fullmatch(generation_id):
        return refuse(
            "envelope_unparseable",
            "generation_id is not a BioCatalyst run reference",
            "generation_id",
        )
    coverage_epoch_id = envelope.get("coverage_epoch_id")
    if not isinstance(coverage_epoch_id, str) or not coverage_epoch_id.strip():
        return refuse(
            "envelope_unparseable",
            "coverage_epoch_id must be a non-empty string",
            "coverage_epoch_id",
        )
    last_complete_run_ref = envelope.get("last_complete_run_ref")
    if last_complete_run_ref is not None and (
        not isinstance(last_complete_run_ref, str)
        or not GENERATION_ID_PATTERN.fullmatch(last_complete_run_ref)
    ):
        return refuse(
            "envelope_unparseable",
            "last_complete_run_ref must be a BioCatalyst run reference or null",
            "last_complete_run_ref",
        )

    rows = envelope.get("rows")
    if not isinstance(rows, list):
        return refuse("rows_not_a_list", "rows must be a JSON array", "rows")

    return _read_rows(
        rows,
        generation_id=generation_id,
        coverage_epoch_id=coverage_epoch_id,
        last_complete_run_ref=last_complete_run_ref,
        content_hash=content_hash,
        resolve_issuer=resolve_issuer,
        fixture_only=effective_fixture_only,
    )


def _read_rows(
    rows: list[Any],
    *,
    generation_id: str,
    coverage_epoch_id: str,
    last_complete_run_ref: str | None,
    content_hash: str,
    resolve_issuer: Callable[[Mapping[str, Any]], str | None],
    fixture_only: bool,
) -> dict[str, Any]:
    input_rows = len(rows)
    quarantined: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []

    for index, row in enumerate(rows):
        try:
            event, native_id, revision_index = _read_row(
                row,
                envelope_generation_id=generation_id,
                resolve_issuer=resolve_issuer,
            )
        except _RowRefusal as refusal:
            quarantined.append(
                _quarantine(
                    row_index=index,
                    source_native_id=_row_native_id(row),
                    reason_code=refusal.reason_code,
                    field=refusal.field,
                    detail=refusal.detail,
                )
            )
            continue
        candidates.append(
            {
                "row_index": index,
                "source_native_id": native_id,
                "event": event,
                "content_hash": event_v2_content_hash(event),
                "revision_key": (native_id, event["event_type"], revision_index),
            }
        )

    accepted = _resolve_collisions(candidates, quarantined)

    counts = {
        "input_rows": input_rows,
        "accepted": len(accepted),
        "quarantined": len(quarantined),
    }
    if counts["accepted"] + counts["quarantined"] != counts["input_rows"]:
        # Conservation is the whole point of the ledger: a row that is neither
        # accepted nor explained has been silently deleted.
        raise ContractError(
            "conservation invariant violated: "
            f"{counts['accepted']} + {counts['quarantined']} != {counts['input_rows']}"
        )

    return {
        "schema": EVENT_CLOCK_READ_SCHEMA,
        "accepted": accepted,
        "quarantined": sorted(
            quarantined,
            key=lambda entry: (
                entry["row_index"] if entry["row_index"] is not None else -1,
                entry["reason_code"],
            ),
        ),
        "counts": counts,
        "generation": {
            "generation_id": generation_id,
            "coverage_epoch_id": coverage_epoch_id,
            "content_hash": content_hash,
            "last_complete_run_ref": last_complete_run_ref,
        },
        "fixture_only": fixture_only,
    }


def _resolve_collisions(
    candidates: list[dict[str, Any]], quarantined: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Resolve identity collisions in a way that does not depend on row order.

    Two collisions are possible and they are different facts:

    * the same ``event_id`` twice with *identical* content — a duplicate.  One
      copy is accepted and the extras are quarantined; which physical row won
      cannot matter, because the surviving payloads are byte-identical.
    * the same ``event_id`` with *differing* content, or two different
      ``event_id``s at the same ``(source_native_id, event_type,
      revision_index)`` position — a contradiction.  The source is asserting
      two incompatible things at one revision slot, and there is no
      order-independent way to pick a winner, so **every** member of the group
      is quarantined.  Keeping "the first one" would make the answer depend on
      serialisation order, which is exactly the dependence this module refuses.
    """
    by_revision_key: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for candidate in candidates:
        by_revision_key.setdefault(candidate["revision_key"], []).append(candidate)

    surviving: list[dict[str, Any]] = []
    for group in by_revision_key.values():
        distinct_ids = {candidate["event"]["event_id"] for candidate in group}
        if len(distinct_ids) > 1:
            for candidate in group:
                quarantined.append(
                    _quarantine(
                        row_index=candidate["row_index"],
                        source_native_id=candidate["source_native_id"],
                        reason_code="contradictory_revision",
                        field="revision",
                        detail=(
                            "several distinct events claim the same revision index for this "
                            "source record; no order-independent winner exists"
                        ),
                    )
                )
            continue
        surviving.extend(group)

    by_event_id: dict[str, list[dict[str, Any]]] = {}
    for candidate in surviving:
        by_event_id.setdefault(candidate["event"]["event_id"], []).append(candidate)

    accepted: list[dict[str, Any]] = []
    for group in by_event_id.values():
        distinct_content = {candidate["content_hash"] for candidate in group}
        if len(distinct_content) > 1:
            for candidate in group:
                quarantined.append(
                    _quarantine(
                        row_index=candidate["row_index"],
                        source_native_id=candidate["source_native_id"],
                        reason_code="contradictory_revision",
                        field="event_id",
                        detail=(
                            "one event identity carries conflicting content across rows; "
                            "no order-independent winner exists"
                        ),
                    )
                )
            continue
        keeper = min(group, key=lambda candidate: candidate["row_index"])
        accepted.append(keeper["event"])
        for candidate in group:
            if candidate is keeper:
                continue
            quarantined.append(
                _quarantine(
                    row_index=candidate["row_index"],
                    source_native_id=candidate["source_native_id"],
                    reason_code="duplicate_event_id",
                    field="event_id",
                    detail="an identical copy of this event was already read from this batch",
                )
            )

    # Sorted by identity, never by arrival: the accepted list is a set with a
    # stable rendering, so a reshuffled batch replays byte-identically.
    return sorted(accepted, key=lambda event: event["event_id"])


__all__ = [
    "EVENT_CLOCK_READ_SCHEMA",
    "EXPECTED_HASH_SCOPE",
    "EXPECTED_PROJECTION_CONTRACT",
    "EXPECTED_PROJECTION_SCHEMA_VERSION",
    "FORBIDDEN_AUTHORITY_FIELDS",
    "GENERATION_ID_PATTERN",
    "MAX_NATIVE_ID_CHARS",
    "MAX_PROJECTION_BYTES",
    "MAX_PROJECTION_DEPTH",
    "MAX_REVISION_INDEX",
    "MAX_SOURCE_TEXT_CHARS",
    "QUARANTINE_REASON_CODES",
    "canonical_projection_bytes",
    "derive_event_id",
    "read_event_projection",
    "resolve_issuer_unavailable",
]
