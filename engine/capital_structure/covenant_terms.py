"""Filing-text covenant extraction producer (source-first slice).

Packet B-F09-5. Emits ``capital_structure.covenant_term_observation.v1``
records for financial-covenant clauses stated in retained SEC credit-agreement
exhibits (EX-10.1..EX-10.5), with exact source identity (accession + an exact
byte locator inside the retained document) and append-only correction
semantics. Mirrors the closed-enum, zero-authority, "absence is not zero"
posture of ``engine.capital_structure.document_terms`` (the registration
fee-table precedent) without touching that module.

Review-fix note (packet B-F09-5, see PR "Review fixes" section):
the sibling contract file
``contracts/capital_structure_covenant_term_observation.schema.json``,
``scripts/compile_capital_structure_covenant_terms.py``, and the
daily.yml/ci.yml wiring DO exist in this PR (they are not owned by this
packet's OWNED FILES list and are flagged for explicit owner adjudication),
so enum/shape closure here is enforced defensively in Python in addition to,
not instead of, that external JSON Schema.

This slice performs NO headroom/capacity computation and renders nothing
user-facing (acceptance 4). Any key resembling headroom/capacity/cushion is
refused by ``_assert_no_derived_capacity_field``.
"""
from __future__ import annotations

import hashlib
import re
from datetime import date, datetime
from typing import Any, Mapping, MutableMapping, Sequence

COVENANT_TERM_SCHEMA = "capital_structure.covenant_term_observation.v1"
PARSER_VERSION = "capital-structure-covenant-terms/1.0.0"

# Names mirror the phrase the agreement itself states. Economic type/unit is
# clause dependent; never attach a unit before reading the clause. The tuple
# is frozen at the values a real filing was observed to state (Step 0,
# Corsair Gaming EX-10.1, accession 0001564590-22-038930) — a name the pulled
# filing does not state is never kept speculatively.
COVENANT_TERM_NAMES = (
    "maximum_total_net_leverage_ratio",
    "maximum_secured_net_leverage_ratio",
    "minimum_interest_coverage_ratio",
    "minimum_fixed_charge_coverage_ratio",
    "minimum_liquidity_amount",
    "restricted_payments_basket_amount",
)
COVENANT_TERM_SCOPES = (
    "credit_agreement_financial_covenant_clause",
    "credit_agreement_negative_covenant_basket_clause",
)
AGREEMENT_ROLES = ("credit_agreement",)
COVENANT_EXHIBIT_TYPES = frozenset({"EX-10.1", "EX-10.2", "EX-10.3", "EX-10.4", "EX-10.5"})

DISPOSITIONS = ("direct", "ambiguous", "unavailable")

_RATIO_TERMS = frozenset({
    "maximum_total_net_leverage_ratio",
    "maximum_secured_net_leverage_ratio",
    "minimum_interest_coverage_ratio",
    "minimum_fixed_charge_coverage_ratio",
})
_MONETARY_TERMS = frozenset({"minimum_liquidity_amount", "restricted_payments_basket_amount"})

# Charter zero-authority: no rank/size/gate/trade keys may ever appear here.
_ZERO_AUTHORITY_KEYS = frozenset({
    "rank", "size_gate", "trade", "signal", "score", "buy", "sell",
    "escalation", "escalate", "authority_grant",
})
_DERIVED_CAPACITY_RE = re.compile(r"headroom|capacity|cushion|available_amount_remaining", re.IGNORECASE)

_BYTE_LOCATOR_RE = re.compile(r"bytes:(\d+)-(\d+)$")

_SECTION_PATTERN = re.compile(r"(Section\s+7\.11\s+Financial Covenants|7\.11 Financial Covenants)")

# Deterministic, source-first patterns for the two term names Step 0 actually
# observed stated as explicit numbers in the pulled real exhibit. Every other
# enum name is emitted as an explicit "unavailable" record (never inferred).
_TERM_PATTERNS: dict[str, re.Pattern] = {
    "maximum_total_net_leverage_ratio": re.compile(
        r"Maximum Consolidated Total Net Leverage Ratio.{0,600}?(\d\.\d{2} to 1\.00)", re.DOTALL),
    "minimum_interest_coverage_ratio": re.compile(
        r"Minimum Consolidated Interest Coverage Ratio.{0,600}?(\d\.\d{2} to 1\.00)", re.DOTALL),
}

# Header phrase used to detect a STEPPED SCHEDULE (multiple grid rows) for the
# same term name. Stepped schedules are what real credit agreements actually
# state (Section 7.11-style "Measurement Period Ending" grids) -- refusing
# them made the producer useless on real filings. A schedule is therefore
# extracted as a "direct" observation whose value carries the FULL grid plus
# the CURRENT step (the row whose start date is on/most-recently-before the
# filing's own as-of date) as the headline ratio. Only a grid this code finds
# no dates in at all falls back to "ambiguous" / stepped_schedule_no_measurement_period
# (an absent value, never an inferred/expired one) -- see _parse_schedule_rows.
_TERM_HEADERS: dict[str, str] = {
    "maximum_total_net_leverage_ratio": "Maximum Consolidated Total Net Leverage Ratio",
    "minimum_interest_coverage_ratio": "Minimum Consolidated Interest Coverage Ratio",
}
_SCHEDULE_WINDOW = 1200
_GRID_VALUE_RE = re.compile(r"\d\.\d{2} to 1\.00")

_DATE_TEXT = r"[A-Z][a-z]+ \d{1,2}, \d{4}"
_SCHEDULE_ROW_RE = re.compile(
    rf"({_DATE_TEXT}(?:\s+through and including\s+{_DATE_TEXT}"
    rf"|\s+and\s+{_DATE_TEXT}"
    rf"|\s+and each fiscal quarter thereafter)?)\s+(\d\.\d{{2}} to 1\.00)"
)


def _schedule_window_end(text: str, idx: int, own_header: str) -> int:
    """Bound a term's schedule window at whichever comes first: the flat
    _SCHEDULE_WINDOW cap, or the start of a DIFFERENT covenant term's header
    -- otherwise a large window pulls a neighboring term's grid rows into
    this term's schedule (two closed-enum terms sharing one clause block)."""
    limit = idx + _SCHEDULE_WINDOW
    for other_name, other_header in _TERM_HEADERS.items():
        if other_header == own_header:
            continue
        other_idx = text.find(other_header, idx + len(own_header))
        if other_idx != -1:
            limit = min(limit, other_idx)
    return limit


def _is_stepped_schedule(text: str, name: str) -> bool:
    header = _TERM_HEADERS.get(name)
    if header is None:
        return False
    idx = text.find(header)
    if idx == -1:
        return False
    window = text[idx: _schedule_window_end(text, idx, header)]
    return len(_GRID_VALUE_RE.findall(window)) > 1


def _parse_schedule_rows(text: str, header: str) -> list[dict[str, Any]]:
    """Parse a "Measurement Period Ending" grid into rows carrying an exact
    ratio-text char span (into `text`), a start date (for selecting the
    current step), and a period_end (ISO date, or None for an open-ended
    "and each fiscal quarter thereafter" row). Returns [] when the grid near
    `header` states no calendar dates at all (never picked as direct)."""
    idx = text.find(header)
    if idx == -1:
        return []
    window_start = idx
    window = text[window_start: _schedule_window_end(text, idx, header)]
    rows: list[dict[str, Any]] = []
    for match in _SCHEDULE_ROW_RE.finditer(window):
        phrase = match.group(1)
        ratio_text = match.group(2)
        date_texts = re.findall(_DATE_TEXT, phrase)
        if not date_texts:
            continue
        try:
            parsed_dates = [datetime.strptime(d, "%B %d, %Y").date() for d in date_texts]
        except ValueError:
            continue
        is_open_ended = "thereafter" in phrase
        ratio_start = window_start + match.start(2)
        ratio_end = window_start + match.end(2)
        rows.append({
            "start_date": min(parsed_dates),
            "period_end": None if is_open_ended else max(parsed_dates).isoformat(),
            "ratio": ratio_text,
            "ratio_span": (ratio_start, ratio_end),
        })
    return rows


def _as_of_date(manifest: Mapping[str, Any]) -> date | None:
    """The filing's own as-of date -- what the agreement states as current at
    the moment it was filed. Used to pick the CURRENT step out of a stepped
    measurement-period schedule (never today's date, never a market date)."""
    filing = manifest.get("filing") or {}
    raw = filing.get("filing_date") or filing.get("accepted_at")
    if not raw:
        return None
    try:
        return datetime.strptime(str(raw)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _select_current_step(rows: Sequence[Mapping[str, Any]], as_of: date | None) -> Mapping[str, Any]:
    """The row governing at `as_of`: the row with the latest start_date that
    is still on or before `as_of` (a step function of effective dates, not a
    range-containment search -- the grid's rows are non-contiguous "Measurement
    Period Ending" quarter markers, not continuous date ranges). Falls back to
    the earliest row when `as_of` is unknown or precedes every row's start."""
    if as_of is not None:
        eligible = [row for row in rows if row["start_date"] <= as_of]
        if eligible:
            return max(eligible, key=lambda row: row["start_date"])
    return min(rows, key=lambda row: row["start_date"])


class CovenantSpanUnbound(ValueError):
    """A candidate whose byte span cannot be bound to the retained bytes,
    is out of bounds, or whose section header cannot be located. The whole
    candidate fails closed and is never stored as an observation."""


def covenant_term_type(name: str) -> str:
    if name in _RATIO_TERMS:
        return "ratio"
    if name in _MONETARY_TERMS:
        return "monetary_amount"
    raise ValueError(f"unknown covenant term name: {name!r}")


def _empty_value() -> dict[str, Any]:
    return {"raw": None, "unit": None, "value": None}


def _assert_zero_authority(record: Mapping[str, Any]) -> None:
    def _walk(node: Any) -> None:
        if isinstance(node, Mapping):
            for key, value in node.items():
                if isinstance(key, str) and key.lower() in _ZERO_AUTHORITY_KEYS:
                    raise ValueError(f"zero-authority violation: key {key!r} present in covenant observation")
                _walk(value)
        elif isinstance(node, (list, tuple)):
            for item in node:
                _walk(item)
    _walk(record)


def assert_no_derived_capacity_field(record: Mapping[str, Any]) -> None:
    def _walk(node: Any) -> None:
        if isinstance(node, Mapping):
            for key, value in node.items():
                if isinstance(key, str) and _DERIVED_CAPACITY_RE.search(key):
                    raise ValueError(f"headroom/capacity field is out of scope for this slice: {key!r}")
                _walk(value)
        elif isinstance(node, (list, tuple)):
            for item in node:
                _walk(item)
    _walk(record)


def _selected_covenant_manifests(manifests: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    selected = [
        dict(m) for m in manifests
        if m.get("source_system") == "sec_edgar"
        and (m.get("document") or {}).get("document_role") == "exhibit"
        and (m.get("document") or {}).get("document_type") in COVENANT_EXHIBIT_TYPES
    ]
    selected.sort(key=lambda m: m.get("manifest_id", ""))
    return selected


def _locator_bounds(locator: str) -> tuple[int, int]:
    match = _BYTE_LOCATOR_RE.search(locator)
    if not match:
        raise CovenantSpanUnbound(f"covenant term span lacks an exact byte locator: {locator!r}")
    start, end = int(match.group(1)), int(match.group(2))
    if start < 0 or end <= start:
        raise CovenantSpanUnbound(f"byte locator is out of bounds: {locator!r}")
    return start, end


def validate_locator(locator: str, retained_byte_length: int) -> tuple[int, int]:
    """Refuse (raise CovenantSpanUnbound) a locator that is malformed or
    whose span exceeds the retained bytes. Never downgraded to a stored
    observation — mirrors document_terms.DocumentTermCompileDegraded."""
    start, end = _locator_bounds(locator)
    if end > retained_byte_length:
        raise CovenantSpanUnbound(f"byte locator is out of bounds against retained bytes: {locator!r}")
    return start, end


def build_locator(child_document_type: str, child_sequence: int, section_label_normalized: str,
                   term_name: str, start: int, end: int) -> str:
    return (
        f"complete_submission:doc={child_document_type}#{child_sequence}:"
        f"section={section_label_normalized}:role={term_name}:bytes:{start}-{end}"
    )


def _clause_id_for(manifest_id: str, section_label_normalized: str, term_name: str) -> str:
    digest = hashlib.sha256(f"{manifest_id}|{section_label_normalized}|{term_name}".encode("utf-8")).hexdigest()
    return f"covenant-clause:cs:{digest}"


def logical_observation_id_for(manifest_id: str, clause_id: str, term_name: str) -> str:
    digest = hashlib.sha256(f"{manifest_id}|{clause_id}|{term_name}".encode("utf-8")).hexdigest()
    return f"covenant-term-logical:cs:{digest}"


def observation_id_for(record: Mapping[str, Any]) -> str:
    payload = (
        f"{record['document']['source_manifest_id']}|"
        f"{record['clause']['clause_id']}|"
        f"{record['term']['name']}|"
        f"{record['version']['correction_version']}|"
        f"{record['point_in_time']['available_at']}"
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"covenant-term:cs:{digest}"


def _section_label(text: str) -> tuple[str, str]:
    if not _SECTION_PATTERN.search(text):
        raise CovenantSpanUnbound("covenant section header could not be located in the retained text")
    return ("Section 7.11 Financial Covenants", "section_7_11_financial_covenants")


def _semantic_body(record: Mapping[str, Any]) -> tuple:
    """Parts of a record whose change is a real correction. Excludes
    parser_version/generated_at bookkeeping so a parser-label-only relabel
    with an unchanged extraction cannot mint a phantom version."""
    return (
        record.get("term", {}).get("name"),
        record.get("clause", {}).get("clause_id"),
        tuple(sorted((record.get("reported") or {}).items())),
        (record.get("state") or {}).get("disposition"),
        (record.get("state") or {}).get("reason"),
    )


def extract_candidates(manifest: Mapping[str, Any], text: str) -> list[dict[str, Any]]:
    """Produce one candidate per COVENANT_TERM_NAMES entry: 'direct' when the
    deterministic pattern locates the clause with an exact byte span, else an
    explicit 'unavailable' record (never a zero, never inferred)."""
    manifest_id = manifest["manifest_id"]
    document = manifest["document"]
    section_label_raw, section_label_normalized = _section_label(text)
    encoded = text.encode("utf-8")
    candidates: list[dict[str, Any]] = []
    for name in COVENANT_TERM_NAMES:
        pattern = _TERM_PATTERNS.get(name)
        match = pattern.search(text) if pattern else None
        clause_id = _clause_id_for(manifest_id, section_label_normalized, name)
        clause = {
            "clause_id": clause_id,
            "section_label_raw": section_label_raw,
            "section_label_normalized": section_label_normalized,
            "agreement_role": "credit_agreement",
        }
        term = {
            "name": name,
            "term_type": covenant_term_type(name),
            "scope": "credit_agreement_financial_covenant_clause",
        }
        # Computed unconditionally (not only inside one branch) so it is never
        # unbound regardless of which branch below runs -- the prior code
        # referenced `_seq` after the if/elif/else even though it was assigned
        # only in the final `else`, raising UnboundLocalError the moment a
        # stepped schedule (the `elif`) matched on a real filing.
        _seq_raw = document.get("sequence")
        try:
            _seq = int(_seq_raw) if _seq_raw is not None else 1
        except (TypeError, ValueError):
            _seq = 1
        if match is None:
            state = {"disposition": "unavailable", "reason": "clause_absent_in_source"}
            reported = _empty_value()
            normalized = _empty_value()
            spans: list[dict[str, Any]] = []
            extraction_method = "deferred"
            review_status = "unavailable"
        elif _is_stepped_schedule(text, name):
            header = _TERM_HEADERS[name]
            schedule_rows = _parse_schedule_rows(text, header)
            if not schedule_rows:
                # The grid states no calendar date at all -- no step can be
                # identified as "current". This is the only remaining refusal
                # case; a dated grid is always resolved to a direct schedule.
                state = {"disposition": "ambiguous", "reason": "stepped_schedule_no_measurement_period"}
                reported = _empty_value()
                normalized = _empty_value()
                spans = []
                extraction_method = "deferred"
                review_status = "unavailable"
            else:
                current = _select_current_step(schedule_rows, _as_of_date(manifest))
                value_text = current["ratio"]
                char_start, char_end = current["ratio_span"]
                byte_start = len(text[:char_start].encode("utf-8"))
                byte_end = byte_start + len(value_text.encode("utf-8"))
                locator = build_locator(document.get("document_type"), _seq,
                                         section_label_normalized, name, byte_start, byte_end)
                validate_locator(locator, len(encoded))
                schedule_payload = [
                    {"period_end": row["period_end"], "ratio": row["ratio"]} for row in schedule_rows
                ]
                state = {"disposition": "direct", "reason": None}
                reported = {"raw": value_text, "unit": "ratio", "value": None, "schedule": schedule_payload}
                normalized = dict(reported)
                spans = [{"locator": locator, "locator_type": "text_range"}]
                extraction_method = "deterministic"
                review_status = "final"
        else:
            value_text = match.group(1)
            char_start, char_end = match.start(1), match.end(1)
            byte_start = len(text[:char_start].encode("utf-8"))
            byte_end = byte_start + len(value_text.encode("utf-8"))
            locator = build_locator(document.get("document_type"), _seq,
                                     section_label_normalized, name, byte_start, byte_end)
            validate_locator(locator, len(encoded))
            state = {"disposition": "direct", "reason": None}
            reported = {"raw": value_text, "unit": "ratio", "value": None}
            normalized = {"raw": value_text, "unit": "ratio", "value": None}
            spans = [{"locator": locator, "locator_type": "text_range"}]
            extraction_method = "deterministic"
            review_status = "final"
        candidates.append({
            "schema": COVENANT_TERM_SCHEMA,
            "logical_observation_id": logical_observation_id_for(manifest_id, clause_id, name),
            "issuer_id": (manifest.get("issuer") or {}).get("issuer_id"),
            "filing": manifest["filing"],
            "document": {
                "source_manifest_id": manifest_id,
                "source_id": manifest.get("source_id"),
                "document_role": document.get("document_role"),
                "canonical_url": document.get("canonical_url"),
                "content_sha256": document.get("content_sha256"),
                "child_document_type": document.get("document_type"),
                "child_sequence": _seq,
                "child_filename": document.get("document_name"),
                "child_text_start": None,
                "child_text_end": None,
            },
            "clause": clause,
            "term": term,
            "state": state,
            "reported": reported,
            "normalized": normalized,
            "evidence": {
                "source_manifest_id": manifest_id,
                "source_document_sha256": document.get("content_sha256"),
                "rights_class": str((manifest.get("rights") or {}).get("redistribution_class") or "unknown"),
                "privacy_classification": str((manifest.get("privacy") or {}).get("classification") or "unknown"),
                "contains_personal_data": bool((manifest.get("privacy") or {}).get("contains_personal_data")),
                "publication": {
                    "disposition": "public_fact_only",
                    "excerpt_char_count": 0,
                    "personal_data_redacted": False,
                },
                "spans": spans,
            },
            "extraction": {
                "method": extraction_method,
                "parser_version": PARSER_VERSION,
                "review_status": review_status,
            },
            "relationships": {"amends": [], "supersedes": [], "contradiction_ids": []},
            "version": {"correction_version": 1, "correction_of": None, "immutable_record": True},
            "point_in_time": {
                "source_available_at": (manifest.get("retrieval") or {}).get("first_seen_at")
                or manifest["filing"]["accepted_at"],
                "available_at": None,
            },
        })
    return candidates


def _materialize_observation(candidate: Mapping[str, Any], prior: Mapping[str, Any] | None,
                              generated_at: str) -> dict[str, Any]:
    record: MutableMapping[str, Any] = dict(candidate)
    version = dict(record.get("version") or {})
    pit = dict(record.get("point_in_time") or {})
    relationships = dict(record.get("relationships") or {"amends": [], "supersedes": [], "contradiction_ids": []})

    if prior is not None:
        if _semantic_body(record) == _semantic_body(prior):
            return dict(prior)  # relabel-only: no phantom version (test 7)
        if generated_at <= prior["point_in_time"]["available_at"]:
            raise ValueError("generated_at must be later than a corrected covenant-term observation")
        version["correction_version"] = prior["version"]["correction_version"] + 1
        version["correction_of"] = prior["observation_id"]
        version["immutable_record"] = True
        relationships["supersedes"] = [prior["observation_id"]]
        pit.setdefault("source_available_at", prior["point_in_time"]["source_available_at"])
    else:
        version.setdefault("correction_version", 1)
        version.setdefault("correction_of", None)
        version["immutable_record"] = True
        relationships.setdefault("supersedes", [])

    if pit.get("available_at") is None:
        pit["available_at"] = generated_at
    if pit["available_at"] < pit.get("source_available_at", pit["available_at"]):
        raise ValueError("available_at may not precede source_available_at")

    relationships.setdefault("amends", [])
    relationships.setdefault("contradiction_ids", [])

    record["version"] = version
    record["point_in_time"] = pit
    record["relationships"] = relationships
    record["observation_id"] = observation_id_for(record)
    _assert_zero_authority(record)
    assert_no_derived_capacity_field(record)
    return record


def link_amendment(candidate: Mapping[str, Any], prior_observation_id: str, *, generated_at: str) -> dict[str, Any]:
    """Case B (amended/superseding filing): a NEW logical_observation_id
    (different accession/manifest) records the link forward-only via
    relationships.amends. The prior observation is never touched."""
    record = _materialize_observation(candidate, None, generated_at)
    relationships = dict(record["relationships"])
    amends = list(relationships.get("amends") or [])
    amends.append(prior_observation_id)
    relationships["amends"] = amends
    record["relationships"] = relationships
    record["observation_id"] = observation_id_for(record)
    return record


def compile_observations(manifest: Mapping[str, Any], text: str, *, generated_at: str,
                          prior_observations: Sequence[Mapping[str, Any]] = ()) -> list[dict[str, Any]]:
    """Compile every covenant-term candidate for one manifest, applying
    correction semantics (Case A) against any prior observation sharing the
    same logical_observation_id."""
    prior_by_logical: dict[str, Mapping[str, Any]] = {}
    for obs in prior_observations:
        logical_id = obs["logical_observation_id"]
        existing = prior_by_logical.get(logical_id)
        if existing is None or obs["version"]["correction_version"] > existing["version"]["correction_version"]:
            prior_by_logical[logical_id] = obs
    out = []
    for candidate in extract_candidates(manifest, text):
        prior = prior_by_logical.get(candidate["logical_observation_id"])
        out.append(_materialize_observation(candidate, prior, generated_at))
    return out
