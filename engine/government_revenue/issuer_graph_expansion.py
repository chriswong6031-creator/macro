"""Exact-identifier issuer graph expansion (Wave 9D).

This module proposes ``issuer -> legal entity -> UEI/CAGE`` edges for the
reviewed recipient graph.  It exists because the mapping backlog associates
tickers to companies by ``curated_fuzzy_name``, and that association is *not*
issuer attribution.  Every edge produced here must trace to an immutable,
re-fetchable official document.

WHAT IS ADMISSIBLE.  An edge is admissible only when an **exact identifier**
(SAM UEI or CAGE, from the official USAspending recipient record) links a
recipient to a legal entity name that appears **verbatim** in the issuer's own
SEC Exhibit 21 (Subsidiaries of the Registrant) or on the 10-K cover as the
registrant itself.  "Verbatim" permits exactly two orthographic tiers:

    exact_verbatim_name          case/whitespace/punctuation normalization only
    exact_suffix_normalized_name the same, after removing at most ONE trailing
                                 legal-form suffix from a closed list, from at
                                 most ONE of the two names, and only when the
                                 match is unique in BOTH directions

The suffix tier is one-sided: it bridges "Vanguard Defense Systems" against
"Vanguard Defense Systems, Inc.", and refuses "... Limited" against "... Inc",
because two different legal-form designators name two different legal persons.

Anything else is fuzzy.  Token reordering, substring/prefix containment, edit
distance, abbreviation expansion, synonym tables, and "I know that company"
are all forbidden, and there is deliberately no threshold, cutoff, or scorer in
this file to loosen.  A candidate that needs judgment resolves to ``ambiguous``
or ``unresolved`` -- a first-class recorded output, never a silent drop.

WHAT IS NEVER AN INPUT.  ``discovery_query_ticker``, curated/fuzzy name
association, name similarity, web-search snippets, and LLM assertions are
refused at the door by :data:`FORBIDDEN_INPUT_KEYS` /
:data:`FORBIDDEN_ASSOCIATION_METHODS`, and the refusal is recorded as a
rejection rather than dropping the row.  The discovery *query text* used to
enumerate recipients is derived from the issuer's own Exhibit 21, not from a
ticker guess; admission is still by exact identifier plus verbatim name.

REVIEW AUTHORITY.  This module may only emit ``proposed``.  Marking an edge
``reviewed`` is the operator's act.  :func:`build_proposal_ledger` calls
:func:`assert_unreviewed` on its own output before returning, so an emitted
reviewed state raises :class:`ProposalAuthorityError` instead of shipping.  The
consumer-side fence is structural: proposals live in their own artifact and
carry ``verification_state="proposed"``, which
``entity_resolution.load_recipient_entity_graph`` rejects
(``*_not_reviewed``), so an unreviewed edge cannot reach candidate attribution.

Authority is unchanged: Government Revenue stays display/context-only.  Nothing
here ranks, sizes, gates, or originates a signal.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any, Iterable, Mapping, Sequence


PROPOSAL_CONTRACT = "government_recipient_graph_proposal.v1"
PROPOSAL_SCHEMA_VERSION = "1.0.0"
COVERAGE_CONTRACT = "government_issuer_expansion_coverage.v1"

#: The only review status this module is permitted to emit.
PROPOSED_STATE = "proposed"

#: States that mean "an operator has reviewed this".  Never emitted here.
REVIEWED_STATES = frozenset({"confirmed", "reviewed", "analyst_approved", "approved"})

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

#: Association methods that can never justify an edge.  The mapping backlog is
#: entirely ``curated_fuzzy_name``; that is the input this wave exists to refuse.
FORBIDDEN_ASSOCIATION_METHODS = frozenset({
    "curated_fuzzy_name",
    "discovery_query_ticker",
    "fuzzy_name",
    "fuzzy",
    "name_similarity",
    "similar_name",
    "web_search",
    "search_snippet",
    "llm",
    "llm_assertion",
    "model_assertion",
    "analyst_recollection",
})

#: Keys whose presence proves the row carries a non-exact provenance.  Their
#: presence is a rejection, not something to ignore.
FORBIDDEN_INPUT_KEYS = frozenset({
    "discovery_query_ticker",
    "query_ticker",
    "similarity",
    "similarity_score",
    "name_similarity",
    "match_score",
    "fuzzy_score",
    "confidence_score",
    "llm_rationale",
    "model_rationale",
    "search_snippet",
    "web_snippet",
})

#: Exact identifier namespaces, mirroring entity_resolution._GRAPH_IDENTIFIER_NAMESPACES.
IDENTIFIER_NAMESPACES = ("sam_uei", "cage")

_UEI = re.compile(r"^[A-Z0-9]{12}$")
_CAGE = re.compile(r"^[A-Z0-9]{5}$")
_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_TICKER = re.compile(r"^[A-Z][A-Z0-9.-]{0,9}$")

#: Orthographic normalization only: fold case, and treat every non-alphanumeric
#: character as a separator.  Applied identically to both sides.  This performs
#: no reordering, expansion, or approximate comparison of any kind.
_NON_ALNUM = re.compile(r"[^0-9a-z]+")

#: Closed list of legal-form designators.  Longest-first so "limited liability
#: company" is stripped before "company".  At most ONE run is removed per name.
_LEGAL_SUFFIXES: tuple[tuple[str, ...], ...] = tuple(sorted(
    (
        ("limited", "liability", "company"),
        ("limited", "liability", "partnership"),
        ("limited", "partnership"),
        ("incorporated",), ("inc",),
        ("corporation",), ("corp",),
        ("company",), ("co",),
        ("llc",), ("l", "l", "c"),
        ("llp",), ("lp",), ("l", "p",),
        ("limited",), ("ltd",),
        ("plc",), ("gmbh",), ("ag",), ("nv",), ("bv",), ("sa",), ("sas",),
        ("spa",), ("srl",), ("pty",), ("pte",), ("aps",), ("oy",), ("ab",),
        ("kk",), ("kg",), ("as",),
    ),
    key=len,
    reverse=True,
))

#: Admission tiers, strongest first.  Both require an exact identifier.
TIER_VERBATIM = "exact_verbatim_name"
TIER_SUFFIX_NORMALIZED = "exact_suffix_normalized_name"

#: Every reason an edge was not produced.  Recorded, never silently dropped.
REJECTION_REASONS = frozenset({
    "fuzzy_association_input_forbidden",
    "forbidden_provenance_key_present",
    "recipient_identifier_absent",
    "recipient_identifier_invalid",
    "recipient_legal_name_absent",
    "name_not_in_issuer_exhibit",
    "ambiguous_name_matches_multiple_issuer_entities",
    "ambiguous_name_matches_multiple_recipients",
    "issuer_evidence_missing",
    "recipient_evidence_missing",
    "evidence_receipt_invalid",
    "validity_window_unsupported",
    "issuer_exhibit_unparseable",
})


class ProposalAuthorityError(RuntimeError):
    """Raised when a proposal artifact claims a review status it cannot hold."""


class ExpansionInputError(ValueError):
    """Raised when an input is structurally unusable (never a silent skip)."""


def _text(value: Any) -> str | None:
    if value is None:
        return None
    rendered = str(value).strip()
    return rendered or None


def _instant(value: Any) -> datetime | None:
    """Parse an explicit instant as UTC; a bare date is midnight UTC."""
    raw = _text(value)
    if raw is None:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(prefix: str, value: Any) -> str:
    body = hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
    return f"{prefix}-{body[:24]}"


# ---------------------------------------------------------------------------
# Name handling.  Orthographic only -- there is no scorer here to loosen.
# ---------------------------------------------------------------------------


def normalize_legal_name(value: Any) -> str | None:
    """Fold case and collapse punctuation/whitespace.  Nothing else.

    This is the *only* text transformation permitted before comparison.  It is
    deterministic, symmetric, and lossless with respect to token order, so two
    names that normalize equal differ only in case, spacing, and punctuation.
    """
    raw = _text(value)
    if raw is None:
        return None
    folded = _NON_ALNUM.sub(" ", raw.casefold()).strip()
    return folded or None


def _tokens(normalized: str) -> tuple[str, ...]:
    return tuple(normalized.split())


def strip_legal_suffix(normalized: str) -> tuple[str, tuple[str, ...] | None]:
    """Remove at most one trailing legal-form suffix from a closed list.

    Returns ``(core, removed_suffix_or_None)``.  A name that is *only* a suffix
    is returned unchanged -- stripping it would leave nothing to compare.
    """
    tokens = _tokens(normalized)
    for suffix in _LEGAL_SUFFIXES:
        if len(tokens) > len(suffix) and tokens[-len(suffix):] == suffix:
            return " ".join(tokens[: -len(suffix)]), suffix
    return normalized, None


def name_match_tier(left: Any, right: Any) -> str | None:
    """Return the admission tier for two names, or ``None`` when not exact.

    ``None`` means "not admissible", which is a rejection -- never a weaker
    accept.  There is intentionally no third, looser tier.

    THE SUFFIX TIER IS ONE-SIDED ON PURPOSE.  It admits a name that carries a
    legal-form designator against the SAME name without one -- the shape that
    occurs when a recipient record is registered as "Vanguard Defense Systems"
    and the exhibit lists "Vanguard Defense Systems, Inc.".  It refuses two
    DIFFERENT designators on the same core, because a legal-form designator is
    part of the entity's identity, not decoration: ``Limited`` and ``Inc`` name
    two separate legal persons, typically in two jurisdictions.  Measured
    2026-08-07 against live evidence, the two-sided rule proposed
    ``L3Harris Technologies Limited`` (the UK subsidiary named in LHX's own
    Exhibit 21) as the same entity as recipient ``L3HARRIS TECHNOLOGIES, INC``
    (the US parent) -- a wrong edge, and the only edge that run produced.
    """
    left_normal = normalize_legal_name(left)
    right_normal = normalize_legal_name(right)
    if left_normal is None or right_normal is None:
        return None
    if left_normal == right_normal:
        return TIER_VERBATIM
    left_core, left_suffix = strip_legal_suffix(left_normal)
    right_core, right_suffix = strip_legal_suffix(right_normal)
    if left_core == right_core and (left_suffix is None) != (right_suffix is None):
        return TIER_SUFFIX_NORMALIZED
    return None


def _match_key(name: str) -> tuple[str, str]:
    """Return ``(verbatim_key, suffix_normalized_key)`` for bucketing."""
    normal = normalize_legal_name(name) or ""
    core, _ = strip_legal_suffix(normal)
    return normal, core


# ---------------------------------------------------------------------------
# Provenance refusal.
# ---------------------------------------------------------------------------


def forbidden_provenance(row: Mapping[str, Any]) -> str | None:
    """Return a rejection reason when a row carries non-exact provenance.

    Checked before any matching happens so a fuzzy row can never reach the
    resolver, and so the refusal is recorded rather than inferred from absence.
    """
    if not isinstance(row, Mapping):
        raise ExpansionInputError("expansion input row must be a mapping")
    present = sorted(set(row) & FORBIDDEN_INPUT_KEYS)
    if present:
        return "forbidden_provenance_key_present"
    method = _text(row.get("association_method") or row.get("match_method"))
    if method is not None and method.casefold() in FORBIDDEN_ASSOCIATION_METHODS:
        return "fuzzy_association_input_forbidden"
    return None


# ---------------------------------------------------------------------------
# Evidence.
# ---------------------------------------------------------------------------


def evidence_source_ref(content_sha256: str) -> str:
    """Return the graph-native source ref for a content hash."""
    digest = (_text(content_sha256) or "").lower()
    if _SHA256.fullmatch(digest) is None:
        raise ExpansionInputError("evidence content_sha256 must be a sha-256 hex digest")
    return f"recipient-evidence:sha256:{digest}"


def evidence_receipt_is_valid(receipt: Mapping[str, Any]) -> bool:
    """Return whether an evidence receipt is content-addressed and clock-bound."""
    if not isinstance(receipt, Mapping):
        return False
    digest = (_text(receipt.get("content_sha256")) or "").lower()
    if _SHA256.fullmatch(digest) is None:
        return False
    if _text(receipt.get("source_ref")) != f"recipient-evidence:sha256:{digest}":
        return False
    byte_length = receipt.get("byte_length")
    if not isinstance(byte_length, int) or isinstance(byte_length, bool) or byte_length <= 0:
        return False
    url = _text(receipt.get("url")) or ""
    if not url.startswith("https://"):
        return False
    for field in ("evidence_id", "publisher", "evidence_class", "record_id"):
        if _text(receipt.get(field)) is None:
            return False
    for field in ("retrieved_at", "known_at", "valid_from"):
        if _instant(receipt.get(field)) is None:
            return False
    scopes = receipt.get("claim_scopes")
    if not isinstance(scopes, list) or not scopes or len(scopes) != len(set(scopes)):
        return False
    return True


def verify_evidence_bytes(receipt: Mapping[str, Any], body: bytes) -> bool:
    """Recompute a stored receipt's hash against the document bytes.

    This is the re-verification contract: a stored evidence document that has
    been altered by even one byte fails here, so an edge can never rest on a
    document nobody can reproduce.
    """
    if not isinstance(body, (bytes, bytearray)):
        raise ExpansionInputError("evidence body must be bytes")
    digest = hashlib.sha256(bytes(body)).hexdigest()
    if _text(receipt.get("byte_length")) is not None and receipt.get("byte_length") != len(body):
        return False
    return digest == (_text(receipt.get("content_sha256")) or "").lower()


# ---------------------------------------------------------------------------
# Resolution.
# ---------------------------------------------------------------------------


def _identifier_pairs(record: Mapping[str, Any]) -> list[tuple[str, str]]:
    """Return validated ``(namespace, value)`` exact identifiers on a record."""
    pairs: list[tuple[str, str]] = []
    uei = _text(record.get("uei") or record.get("recipient_uei"))
    if uei and _UEI.fullmatch(uei.upper()):
        pairs.append(("sam_uei", uei.upper()))
    cage = _text(record.get("cage") or record.get("cage_code") or record.get("recipient_cage"))
    if cage and _CAGE.fullmatch(cage.upper()):
        pairs.append(("cage", cage.upper()))
    return pairs


def _has_any_identifier_field(record: Mapping[str, Any]) -> bool:
    return any(
        _text(record.get(field)) is not None
        for field in ("uei", "recipient_uei", "cage", "cage_code", "recipient_cage")
    )


def _rejection(
    *,
    issuer_ticker: str,
    reason: str,
    recipient_name: str | None = None,
    recipient_identifier: str | None = None,
    issuer_entity_name: str | None = None,
    detail: str | None = None,
) -> dict[str, Any]:
    if reason not in REJECTION_REASONS:
        raise ExpansionInputError(f"unknown rejection reason: {reason}")
    row = {
        "issuer_ticker": issuer_ticker,
        "reason_code": reason,
        "recipient_legal_name": recipient_name,
        "recipient_identifier": recipient_identifier,
        "issuer_entity_name": issuer_entity_name,
        "detail": detail,
        "review_status": PROPOSED_STATE,
        "issuer_attribution": "not_asserted",
    }
    row["rejection_id"] = _digest("grxr1", {
        key: value for key, value in row.items() if key != "rejection_id"
    })
    return row


def resolve_issuer_edges(
    *,
    issuer: Mapping[str, Any],
    exhibit_entities: Sequence[Mapping[str, Any]],
    recipient_records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Propose exact issuer -> legal entity -> identifier edges.

    ``issuer`` carries ``ticker``, ``cik``, ``registrant_name`` and the evidence
    refs proving the public-company claim.  ``exhibit_entities`` is the verbatim
    subsidiary list from the issuer's own Exhibit 21 (plus the registrant), each
    with its own evidence ref.  ``recipient_records`` are official USAspending
    recipient records carrying exact identifiers.

    Returns ``{"proposals": [...], "rejections": [...], "ambiguous": [...]}``.
    Every recipient record appears in exactly one of the three lists.
    """
    ticker = _text(issuer.get("ticker"))
    if ticker is None or _TICKER.fullmatch(ticker) is None:
        raise ExpansionInputError("issuer.ticker must be a valid ticker symbol")
    issuer_bad = forbidden_provenance(issuer)
    if issuer_bad is not None:
        return {
            "proposals": [],
            "ambiguous": [],
            "rejections": [_rejection(issuer_ticker=ticker, reason=issuer_bad,
                                      detail="issuer record carries non-exact provenance")],
        }

    issuer_company_id = _text(issuer.get("company_id")) or f"issuer:{ticker.casefold()}"
    issuer_evidence = sorted({ref for ref in (_text(v) for v in issuer.get("evidence_refs") or []) if ref})

    proposals: list[dict[str, Any]] = []
    rejections: list[dict[str, Any]] = []
    ambiguous: list[dict[str, Any]] = []

    # --- index the issuer's own exhibit, refusing any fuzzy-provenance row ----
    verbatim_index: dict[str, list[Mapping[str, Any]]] = {}
    core_index: dict[str, list[Mapping[str, Any]]] = {}
    usable_entities: list[Mapping[str, Any]] = []
    for entity in exhibit_entities:
        bad = forbidden_provenance(entity)
        name = _text(entity.get("legal_name"))
        if bad is not None:
            rejections.append(_rejection(
                issuer_ticker=ticker, reason=bad, issuer_entity_name=name,
                detail="exhibit entity carries non-exact provenance",
            ))
            continue
        if name is None:
            rejections.append(_rejection(
                issuer_ticker=ticker, reason="issuer_exhibit_unparseable",
                detail="exhibit row carried no legal name",
            ))
            continue
        if not sorted({ref for ref in (_text(v) for v in entity.get("evidence_refs") or []) if ref}):
            rejections.append(_rejection(
                issuer_ticker=ticker, reason="issuer_evidence_missing", issuer_entity_name=name,
                detail="exhibit entity has no evidence ref",
            ))
            continue
        usable_entities.append(entity)
        verbatim_key, core_key = _match_key(name)
        verbatim_index.setdefault(verbatim_key, []).append(entity)
        core_index.setdefault(core_key, []).append(entity)

    def _distinct(rows: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
        seen: dict[str, Mapping[str, Any]] = {}
        for row in rows:
            key = normalize_legal_name(row.get("legal_name")) or ""
            seen.setdefault(key, row)
        return list(seen.values())

    # --- how many distinct recipients claim each name (both directions) ------
    recipient_by_verbatim: dict[str, set[str]] = {}
    recipient_by_core: dict[str, set[str]] = {}
    for record in recipient_records:
        name = _text(record.get("legal_name") or record.get("recipient_name"))
        if name is None:
            continue
        identifiers = _identifier_pairs(record)
        if not identifiers:
            continue
        key = "|".join(f"{ns}:{value}" for ns, value in identifiers)
        verbatim_key, core_key = _match_key(name)
        recipient_by_verbatim.setdefault(verbatim_key, set()).add(key)
        recipient_by_core.setdefault(core_key, set()).add(key)

    for record in recipient_records:
        name = _text(record.get("legal_name") or record.get("recipient_name"))
        bad = forbidden_provenance(record)
        if bad is not None:
            rejections.append(_rejection(
                issuer_ticker=ticker, reason=bad, recipient_name=name,
                detail="recipient record carries non-exact provenance",
            ))
            continue
        if name is None:
            rejections.append(_rejection(
                issuer_ticker=ticker, reason="recipient_legal_name_absent",
                detail="official recipient record carried no registered legal name",
            ))
            continue
        identifiers = _identifier_pairs(record)
        if not identifiers:
            reason = (
                "recipient_identifier_invalid" if _has_any_identifier_field(record)
                else "recipient_identifier_absent"
            )
            rejections.append(_rejection(
                issuer_ticker=ticker, reason=reason, recipient_name=name,
                detail="no valid SAM UEI or CAGE on the official recipient record",
            ))
            continue
        identifier_key = "|".join(f"{ns}:{value}" for ns, value in identifiers)
        record_evidence = sorted({
            ref for ref in (_text(v) for v in record.get("evidence_refs") or []) if ref
        })
        if not record_evidence:
            rejections.append(_rejection(
                issuer_ticker=ticker, reason="recipient_evidence_missing", recipient_name=name,
                recipient_identifier=identifier_key,
                detail="recipient record has no evidence ref",
            ))
            continue

        verbatim_key, core_key = _match_key(name)
        matches = _distinct(verbatim_index.get(verbatim_key, []))
        tier = TIER_VERBATIM
        competing_recipients = recipient_by_verbatim.get(verbatim_key, set())
        if not matches:
            matches = _distinct(core_index.get(core_key, []))
            tier = TIER_SUFFIX_NORMALIZED
            competing_recipients = recipient_by_core.get(core_key, set())

        if not matches:
            rejections.append(_rejection(
                issuer_ticker=ticker, reason="name_not_in_issuer_exhibit", recipient_name=name,
                recipient_identifier=identifier_key,
                detail="registered legal name appears in no Exhibit 21 row for this registrant",
            ))
            continue
        if len(matches) > 1:
            ambiguous.append(_rejection(
                issuer_ticker=ticker,
                reason="ambiguous_name_matches_multiple_issuer_entities",
                recipient_name=name, recipient_identifier=identifier_key,
                detail=f"{len(matches)} distinct exhibit entities share this normalized name",
            ))
            continue
        if len(competing_recipients) > 1:
            ambiguous.append(_rejection(
                issuer_ticker=ticker,
                reason="ambiguous_name_matches_multiple_recipients",
                recipient_name=name, recipient_identifier=identifier_key,
                detail=f"{len(competing_recipients)} distinct recipients share this normalized name",
            ))
            continue

        entity = matches[0]
        entity_name = _text(entity.get("legal_name")) or name
        # Re-derive the tier from the two raw names so the bucket can never
        # admit a pair the pairwise rule would refuse.
        confirmed = name_match_tier(entity_name, name)
        if confirmed is None or confirmed != tier:
            rejections.append(_rejection(
                issuer_ticker=ticker, reason="name_not_in_issuer_exhibit", recipient_name=name,
                recipient_identifier=identifier_key, issuer_entity_name=entity_name,
                detail="bucketed match did not survive pairwise exact re-derivation",
            ))
            continue

        entity_evidence = sorted({
            ref for ref in (_text(v) for v in entity.get("evidence_refs") or []) if ref
        })
        window = _validity_window(entity, record)
        if window is None:
            rejections.append(_rejection(
                issuer_ticker=ticker, reason="validity_window_unsupported", recipient_name=name,
                recipient_identifier=identifier_key, issuer_entity_name=entity_name,
                detail="evidence did not support a valid_from/known_at window",
            ))
            continue
        valid_from, valid_to, known_at = window

        entity_id = _text(entity.get("entity_id")) or (
            "legal:" + re.sub(r"[^a-z0-9]+", "-", (normalize_legal_name(entity_name) or "")).strip("-")
        )
        evidence_refs = sorted(set(entity_evidence + record_evidence))
        edges = [{
            "edge_id": f"ownership:{entity_id}->{issuer_company_id}",
            "child_entity_id": entity_id,
            "parent_company_id": issuer_company_id,
            "relationship": (
                "issuer_legal_entity"
                if _text(entity.get("entity_role")) == "registrant" else "wholly_owned"
            ),
            "economic_share": 1.0,
            "verification_state": PROPOSED_STATE,
            "known_at": _iso(known_at),
            "valid_from": _iso(valid_from),
            "valid_to": _iso(valid_to),
            "evidence_refs": evidence_refs,
        }]
        proposals.append({
            "proposal_id": _digest("grxp1", {
                "issuer_company_id": issuer_company_id,
                "entity_id": entity_id,
                "identifier_key": identifier_key,
                "valid_from": _iso(valid_from),
            }),
            "issuer_ticker": ticker,
            "issuer_company_id": issuer_company_id,
            "legal_entity": {
                "entity_id": entity_id,
                "canonical_name": entity_name,
                "recipient_registered_name": name,
                "verification_state": PROPOSED_STATE,
            },
            "identifiers": [
                {
                    "identifier_id": f"identifier:{entity_id}:{namespace}:{value.casefold()}",
                    "entity_id": entity_id,
                    "namespace": namespace,
                    "value": value,
                    "verification_state": PROPOSED_STATE,
                }
                for namespace, value in identifiers
            ],
            "ownership_path": edges,
            "admission": {
                "rule": "exact_identifier_plus_verbatim_issuer_exhibit_name",
                "tier": tier,
                "identifier_namespaces": [namespace for namespace, _ in identifiers],
                "issuer_exhibit_name": entity_name,
                "recipient_registered_name": name,
                "normalization": (
                    "case, whitespace, and punctuation only"
                    if tier == TIER_VERBATIM
                    else "case, whitespace, punctuation, and one trailing legal-form suffix"
                ),
            },
            "review_status": PROPOSED_STATE,
            "reviewer": None,
            "verification_state": PROPOSED_STATE,
            "known_at": _iso(known_at),
            "valid_from": _iso(valid_from),
            "valid_to": _iso(valid_to),
            "evidence_refs": evidence_refs,
            "evidence_hash": hashlib.sha256(
                canonical_json(evidence_refs).encode("utf-8")
            ).hexdigest(),
            "issuer_attribution": "not_asserted",
            "candidate_eligibility": {
                "is_eligible": False,
                "reason_code": "edge_awaiting_operator_review",
                "explanation": (
                    "The exact evidence is attached, but an unreviewed edge cannot "
                    "attribute an award to an issuer until an operator reviews it."
                ),
            },
        })

    return {
        "proposals": sorted(proposals, key=lambda row: row["proposal_id"]),
        "ambiguous": sorted(ambiguous, key=lambda row: row["rejection_id"]),
        "rejections": sorted(rejections, key=lambda row: row["rejection_id"]),
    }


def _validity_window(
    entity: Mapping[str, Any], record: Mapping[str, Any]
) -> tuple[datetime, datetime | None, datetime] | None:
    """Return ``(valid_from, valid_to, known_at)`` supported by both sides.

    ``valid_from`` is the LATEST of the two evidence start dates: the exhibit
    proves the ownership as of its own period of report, and the recipient
    record proves the identifier as of its own observation.  Taking the later
    of the two is what keeps a mapping learned today from reaching backward
    over an award that predates its evidence.
    """
    entity_from = _instant(entity.get("valid_from"))
    record_from = _instant(record.get("valid_from"))
    if entity_from is None or record_from is None:
        return None
    valid_from = max(entity_from, record_from)

    ends = [
        value for value in (_instant(entity.get("valid_to")), _instant(record.get("valid_to")))
        if value is not None
    ]
    valid_to = min(ends) if ends else None
    if valid_to is not None and valid_to < valid_from:
        return None

    entity_known = _instant(entity.get("known_at"))
    record_known = _instant(record.get("known_at"))
    if entity_known is None or record_known is None:
        return None
    return valid_from, valid_to, max(entity_known, record_known)


def is_attributable_at(edge: Mapping[str, Any], *, effective_at: Any, known_at: Any) -> bool:
    """Point-in-time admission for one edge, conforming to point_in_time.py.

    Fails closed on a missing clock.  ``valid_from`` is compared against the
    award's *effective* date, so a mapping first valid in 2026 can never
    attribute a 2023 obligation, regardless of when the query runs.
    """
    effective = _instant(effective_at)
    knowledge = _instant(known_at)
    if effective is None or knowledge is None:
        return False
    edge_known_at = _instant(edge.get("known_at"))
    valid_from = _instant(edge.get("valid_from"))
    if edge_known_at is None or valid_from is None:
        return False
    if edge_known_at > knowledge:
        return False
    if valid_from > effective:
        return False
    raw_valid_to = edge.get("valid_to")
    if raw_valid_to is not None:
        valid_to = _instant(raw_valid_to)
        if valid_to is None or valid_to < effective:
            return False
    return True


# ---------------------------------------------------------------------------
# Coverage.  Dollar coverage and entity coverage come from separate inputs.
# ---------------------------------------------------------------------------


def build_issuer_coverage(
    *,
    issuer_ticker: str,
    exhibit_entity_names: Sequence[str],
    proposed_entity_names: Sequence[str],
    recipient_award_amounts: Mapping[str, float],
    proposed_identifiers: Sequence[str],
    unresolved_count: int = 0,
) -> dict[str, Any]:
    """Return entity-count and award-dollar coverage, computed independently.

    ``exhibit_entity_names``/``proposed_entity_names`` drive entity coverage.
    ``recipient_award_amounts`` (identifier -> observed award dollars) and
    ``proposed_identifiers`` drive dollar coverage.  Neither is derived from the
    other: an issuer can cover 1 of 8 entities and 97% of dollars, or the
    reverse, and both are reported.

    ``complete`` requires BOTH ratios to be exactly 1.0 and no unresolved rows.
    Anything short of that is ``partial`` (or ``none``), never complete.
    """
    exhibit_keys = {
        key for key in (normalize_legal_name(name) for name in exhibit_entity_names) if key
    }
    proposed_keys = {
        key for key in (normalize_legal_name(name) for name in proposed_entity_names) if key
    } & exhibit_keys
    entity_total = len(exhibit_keys)
    entity_covered = len(proposed_keys)
    entity_ratio = (entity_covered / entity_total) if entity_total else None

    covered_identifiers = {
        value for value in (_text(item) for item in proposed_identifiers) if value
    }
    dollar_total = 0.0
    dollar_covered = 0.0
    for identifier, amount in recipient_award_amounts.items():
        if not isinstance(amount, (int, float)) or isinstance(amount, bool):
            continue
        value = float(amount)
        dollar_total += value
        if _text(identifier) in covered_identifiers:
            dollar_covered += value
    dollar_ratio = (dollar_covered / dollar_total) if dollar_total else None

    is_exactly_complete = (
        entity_ratio == 1.0 and dollar_ratio == 1.0 and unresolved_count == 0
    )
    if is_exactly_complete:
        state = "complete"
    elif entity_covered == 0 and dollar_covered == 0.0:
        state = "none"
    else:
        state = "partial"

    return {
        "contract": COVERAGE_CONTRACT,
        "issuer_ticker": issuer_ticker,
        "coverage_state": state,
        "is_complete": is_exactly_complete,
        "entity_coverage": {
            "basis": "issuer Exhibit 21 legal-entity list",
            "covered": entity_covered,
            "total": entity_total,
            "ratio": entity_ratio,
        },
        "award_dollar_coverage": {
            "basis": "official USAspending award dollars by exact recipient identifier",
            "covered": round(dollar_covered, 2),
            "total": round(dollar_total, 2),
            "ratio": dollar_ratio,
        },
        "unresolved_count": unresolved_count,
        "limitations": [
            "Entity coverage and award-dollar coverage are computed from separate "
            "inputs and must not be substituted for one another.",
            "Coverage is reported against observed evidence, not against the "
            "issuer's true federal footprint.",
        ],
    }


# ---------------------------------------------------------------------------
# The authority fence.
# ---------------------------------------------------------------------------


def _review_states(payload: Any) -> list[str]:
    """Collect every review/verification state anywhere in a payload."""
    found: list[str] = []
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            if key in ("review_status", "verification_state", "reviewer_state") and isinstance(value, str):
                found.append(value)
            elif key == "reviewer" and value is not None:
                found.append(f"reviewer:{value}")
            else:
                found.extend(_review_states(value))
    elif isinstance(payload, (list, tuple)):
        for item in payload:
            found.extend(_review_states(item))
    return found


def assert_unreviewed(payload: Any) -> None:
    """Raise unless every review state in ``payload`` is ``proposed``.

    This is the enforced half of "review status is real, not decorative".  It
    runs on :func:`build_proposal_ledger`'s own output, so this module cannot
    emit a reviewed edge even by accident -- promotion to ``reviewed`` is the
    operator's act, performed on the reviewed graph artifact, not here.
    """
    for state in _review_states(payload):
        if state.startswith("reviewer:"):
            raise ProposalAuthorityError(
                f"proposal artifact named a reviewer ({state[9:]!r}); "
                "review is the operator's act and cannot be self-asserted"
            )
        if state.casefold() in REVIEWED_STATES:
            raise ProposalAuthorityError(
                f"proposal artifact claimed review state {state!r}; "
                f"this pipeline may only emit {PROPOSED_STATE!r}"
            )
        if state.casefold() != PROPOSED_STATE:
            raise ProposalAuthorityError(
                f"proposal artifact carried unknown review state {state!r}"
            )


def build_proposal_ledger(
    *,
    generated_at: str,
    known_at: str,
    issuers: Sequence[Mapping[str, Any]],
    evidence: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Assemble the reviewable proposal artifact.

    ``issuers`` is a sequence of per-issuer resolution results, each shaped
    ``{"issuer": {...}, "resolution": <resolve_issuer_edges output>,
       "coverage": <build_issuer_coverage output>}``.

    The returned artifact is explicitly NOT a recipient entity graph: it carries
    its own contract and ``proposed`` states, so feeding it to
    ``load_recipient_entity_graph`` fails closed rather than attributing.
    """
    generated = _instant(generated_at)
    known = _instant(known_at)
    if generated is None or known is None:
        raise ExpansionInputError("generated_at and known_at must be explicit instants")

    invalid_receipts = [
        _text(row.get("evidence_id")) for row in evidence if not evidence_receipt_is_valid(row)
    ]
    if invalid_receipts:
        raise ExpansionInputError(
            f"evidence receipts are not content-addressed: {sorted(filter(None, invalid_receipts))}"
        )

    issuer_rows: list[dict[str, Any]] = []
    total_proposed = 0
    total_rejected = 0
    total_ambiguous = 0
    for entry in issuers:
        resolution = entry.get("resolution") or {}
        proposals = list(resolution.get("proposals") or [])
        rejections = list(resolution.get("rejections") or [])
        ambiguous = list(resolution.get("ambiguous") or [])
        total_proposed += len(proposals)
        total_rejected += len(rejections)
        total_ambiguous += len(ambiguous)
        issuer_rows.append({
            "issuer": dict(entry.get("issuer") or {}),
            "proposed_edges": proposals,
            "ambiguous": ambiguous,
            "rejections": rejections,
            "coverage": entry.get("coverage"),
            "candidate_eligibility": {
                "is_eligible": False,
                "reason_code": (
                    "no_exact_edge_proposed" if not proposals
                    else "edges_awaiting_operator_review"
                ),
                "explanation": (
                    "No official evidence supported an exact edge for this issuer."
                    if not proposals else
                    "Exact edges are proposed with complete evidence and remain "
                    "ineligible for candidate attribution until an operator reviews them."
                ),
            },
        })

    ledger = {
        "contract": PROPOSAL_CONTRACT,
        "schema_version": PROPOSAL_SCHEMA_VERSION,
        "generated_at": _iso(generated),
        "known_at": _iso(known),
        "authority": dict(AUTHORITY),
        "review_status": PROPOSED_STATE,
        "admissibility_rule": (
            "An edge requires an exact SAM UEI or CAGE from the official USAspending "
            "recipient record, tied to a legal entity name appearing verbatim in the "
            "issuer's own SEC Exhibit 21 or 10-K cover, under case/whitespace/"
            "punctuation normalization plus at most one trailing legal-form suffix. "
            "discovery_query_ticker, fuzzy name similarity, web-search snippets, and "
            "LLM assertions are refused at input."
        ),
        "evidence": sorted(
            (dict(row) for row in evidence),
            key=lambda row: str(row.get("evidence_id")),
        ),
        "issuers": sorted(issuer_rows, key=lambda row: str(row["issuer"].get("ticker"))),
        "counts": {
            "issuers": len(issuer_rows),
            "proposed_edges": total_proposed,
            "ambiguous": total_ambiguous,
            "rejected": total_rejected,
            "reviewed_edges": 0,
        },
        "limitations": [
            "Every edge in this artifact is proposed and unreviewed; none may "
            "attribute an award to an issuer.",
            "This artifact is not a recipient entity graph and is rejected by the "
            "graph loader by construction.",
            "Government Revenue remains display/context only.",
        ],
    }
    ledger["content_id"] = _digest("grxl1", {
        key: value for key, value in ledger.items() if key != "content_id"
    })
    assert_unreviewed(ledger)
    return ledger


def proposal_ledger_as_graph(ledger: Mapping[str, Any]) -> dict[str, Any]:
    """Shape a proposal ledger like a recipient entity graph, states intact.

    Used to *prove* the consumer fence: the result is structurally graph-like
    but every row is ``proposed``, so ``load_recipient_entity_graph`` returns
    ``invalid`` and no candidate can be produced from it.  It deliberately does
    not upgrade any state.
    """
    entities: list[dict[str, Any]] = []
    identifiers: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    companies: list[dict[str, Any]] = []
    for issuer_row in ledger.get("issuers") or []:
        issuer = issuer_row.get("issuer") or {}
        ticker = _text(issuer.get("ticker"))
        company_id = _text(issuer.get("company_id")) or f"issuer:{(ticker or '').casefold()}"
        for edge_row in issuer_row.get("proposed_edges") or []:
            entity = edge_row.get("legal_entity") or {}
            entities.append({
                "entity_id": entity.get("entity_id"),
                "canonical_name": entity.get("canonical_name"),
                "verification_state": PROPOSED_STATE,
                "known_at": edge_row.get("known_at"),
                "valid_from": edge_row.get("valid_from"),
                "valid_to": edge_row.get("valid_to"),
                "evidence_refs": edge_row.get("evidence_refs"),
            })
            for identifier in edge_row.get("identifiers") or []:
                identifiers.append({
                    **identifier,
                    "verification_state": PROPOSED_STATE,
                    "known_at": edge_row.get("known_at"),
                    "valid_from": edge_row.get("valid_from"),
                    "valid_to": edge_row.get("valid_to"),
                    "evidence_refs": edge_row.get("evidence_refs"),
                })
            edges.extend(edge_row.get("ownership_path") or [])
        if ticker:
            companies.append({
                "company_id": company_id,
                "ticker": ticker,
                "verification_state": PROPOSED_STATE,
                "known_at": ledger.get("known_at"),
                "valid_from": ledger.get("known_at"),
                "valid_to": None,
                "evidence_refs": sorted({
                    ref for ref in (_text(v) for v in issuer.get("evidence_refs") or []) if ref
                }),
            })
    return {
        "contract": "government_recipient_entity_graph.v1",
        "schema_version": "1.1.0",
        "graph_id": f"recipient-graph:proposed:{ledger.get('content_id')}",
        "graph_known_at": ledger.get("known_at"),
        "graph_effective_at": ledger.get("known_at"),
        "evidence": [dict(row) for row in ledger.get("evidence") or []],
        "companies": companies,
        "legal_entities": entities,
        "identifiers": identifiers,
        "ownership_edges": edges,
        "blocks": [],
        "conflicts": [],
        "overrides": [],
    }
