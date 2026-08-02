"""Pure award/action event projection for Government Revenue Foresight.

This module intentionally has no file, network, workspace, signal, or ranking
side effects.  It turns versioned USAspending-shaped observations into
display-only public events under a strict dual point-in-time clock.  Records
without an explicit event-eligibility flag and a source receipt fail closed.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import defaultdict
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlparse

import pandas as pd

from .point_in_time import (
    analysis_clock,
    filter_dual_clock,
    iso_instant,
    is_true,
    timestamp,
    with_award_identity,
)


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

DISPLAY_FORMULA_VERSION = "govrev_display_priority.v1"
DEFAULT_LATE_DISCOVERY_DAYS = 45
COVERAGE_SCOPE = (
    "USAspending award/action observations supplied to this projector; "
    "not a complete federal procurement corpus or an investment recommendation."
)

SNAPSHOT_STATE_FIELDS: tuple[str, ...] = (
    "generated_unique_award_id",
    "generated_award_id",
    "award_key",
    "award_id",
    "piid",
    "current_award_amount",
    "potential_award_amount",
    "total_obligated_amount",
    "total_obligation",
    "total_funding_obligated",
    "start_date",
    "end_date",
    "period_of_performance_start_date",
    "period_of_performance_current_end_date",
    "last_modified_date",
    "description",
    "awarding_agency",
    "awarding_sub_agency",
    "funding_agency",
    "funding_sub_agency",
    "recipient_name",
    "recipient_uei",
    "award_type",
    "naics",
    "psc",
    "program",
    "dod_acquisition_program",
    "dod_claimant_program",
    "major_program",
    "program_acronym",
)
ACTION_STATE_FIELDS: tuple[str, ...] = (
    "generated_unique_award_id",
    "generated_award_id",
    "award_key",
    "award_id",
    "piid",
    "action_id",
    "modification_number",
    "action_date",
    "effective_at",
    "federal_action_obligation",
    "action_obligation",
    "obligation_amount",
    "obligated_amount",
    "action_type",
    "action_type_description",
    "description",
    "action_description",
    "period_of_performance_start_date",
    "period_of_performance_current_end_date",
    "end_date",
    "awarding_agency",
    "awarding_sub_agency",
    "recipient_name",
)
SNAPSHOT_DIFF_FIELDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("current_award_amount", ("current_award_amount",)),
    ("potential_award_amount", ("potential_award_amount",)),
    ("end_date", ("end_date", "period_of_performance_current_end_date")),
    (
        "total_obligated_amount",
        ("total_obligated_amount", "total_obligation", "total_funding_obligated"),
    ),
)
ACTION_DIFF_FIELDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "federal_action_obligation",
        (
            "federal_action_obligation",
            "action_obligation",
            "obligation_amount",
            "obligated_amount",
        ),
    ),
    ("action_date", ("action_date", "effective_at")),
    ("action_type", ("action_type", "action_type_description")),
    ("description", ("description", "action_description")),
    ("end_date", ("end_date", "period_of_performance_current_end_date")),
)

_RETRACTION_RE = re.compile(r"\b(?:rescind(?:s|ed|ing)?|retract(?:s|ed|ing|ion)?)\b", re.I)
_OPTION_RE = re.compile(r"\bexercise(?:d|s|ing)?(?:\s+an?)?\s+option\b", re.I)
_EXTENSION_RE = re.compile(r"\b(?:extend(?:s|ed|ing)?|extension)\b", re.I)
_EXTENSION_CONTEXT_RE = re.compile(
    r"\b(?:period(?:\s+of\s+performance)?|performance|pop|contract\s+term)\b", re.I
)
_CORRECTION_RE = re.compile(r"\b(?:correct(?:ion|ed|s|ing)?|administrative\s+error)\b", re.I)
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_ALLOWED_RECEIPT_HOSTS = {"api.usaspending.gov", "usaspending.gov"}
_LEDGER_RECEIPT_BOUND = object()
_LEDGER_RECEIPT_MARKER = "_award_event_ledger_receipt_marker"
_STRUCTURED_ACTION_FIELDS = (
    "action_semantic",
    "source_semantic",
    "action_status",
    "transaction_status",
    "action_relationship",
    "transaction_relationship",
    "modification_relationship",
    "revision_type",
    "correction_status",
    "retraction_status",
)
_RETRACTION_SEMANTICS = {"retraction", "retracted", "retract", "rescission", "rescinded", "rescind", "voided"}
_CORRECTION_SEMANTICS = {"correction", "corrected", "correct", "administrative_correction", "amended_correction"}


def _missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, (list, tuple, dict)):
        return False
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _clean(value: Any) -> Any:
    """Produce stable JSON-safe primitives without inventing unavailable facts."""

    if _missing(value):
        return None
    if isinstance(value, pd.Timestamp):
        return iso_instant(value)
    if isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return None if math.isnan(value) or math.isinf(value) else value
    if hasattr(value, "item"):
        try:
            return _clean(value.item())
        except (TypeError, ValueError):
            pass
    if isinstance(value, Mapping):
        return {str(key): _clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(item) for item in value]
    return str(value)


def _text(value: Any) -> str:
    cleaned = _clean(value)
    return "" if cleaned is None else str(cleaned).strip()


def _first(row: Mapping[str, Any], names: Sequence[str]) -> Any:
    for name in names:
        value = row.get(name)
        if not _missing(value):
            return value
    return None


def _number(value: Any) -> float | None:
    if _missing(value):
        return None
    if isinstance(value, str):
        value = value.replace("$", "").replace(",", "").strip()
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _same(left: Any, right: Any) -> bool:
    left_cleaned, right_cleaned = _clean(left), _clean(right)
    if left_cleaned is None and right_cleaned is None:
        return True
    left_number, right_number = _number(left_cleaned), _number(right_cleaned)
    if left_number is not None and right_number is not None:
        return math.isclose(left_number, right_number, rel_tol=0.0, abs_tol=1e-9)
    return left_cleaned == right_cleaned


def _hash(payload: Any) -> str:
    encoded = json.dumps(_clean(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _state_hash(row: Mapping[str, Any], *, mode: str) -> str:
    # The collector's snapshot content hash contains ``ticker``.  It is useful
    # receipt metadata but cannot be the semantic event key: one award mapped
    # to two listed companies would otherwise create duplicate cards.  A future
    # source may provide a purpose-built mapping-independent semantic hash.
    configured = _first(row, ("event_state_sha256", "projector_state_sha256"))
    rendered = _text(configured)
    if rendered:
        return rendered
    fields = SNAPSHOT_STATE_FIELDS if mode == "snapshot" else ACTION_STATE_FIELDS
    return _hash({field: _clean(row.get(field)) for field in fields})


def _action_identity(row: Mapping[str, Any]) -> str | None:
    """Return only a stable source action/transaction identity.

    A derived composite can silently join two distinct modifications or split a
    later correction into a new action.  Id-less action rows remain useful raw
    context, but cannot become a public transition event.
    """

    explicit = _text(
        _first(
            row,
            ("action_id", "action_uid", "transaction_id", "transaction_unique_id", "award_transaction_id"),
        )
    )
    return f"action:{explicit}" if explicit else None


def _is_event_eligible(row: Mapping[str, Any]) -> bool:
    """Events are opt-in; a legacy/raw observation is baseline-only by default."""

    return is_true(row.get("event_eligible"))


def _strict_true(value: Any) -> bool:
    """Accept a real boolean flag, not a truthy imported string."""

    return isinstance(value, bool) and value


def _valid_receipt_url(value: Any) -> str | None:
    url = _text(value)
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.scheme.lower() != "https" or parsed.hostname is None:
        return None
    if parsed.hostname.lower().rstrip(".") not in _ALLOWED_RECEIPT_HOSTS:
        return None
    return url


def _is_ledger_bound(row: Mapping[str, Any]) -> bool:
    return row.get(_LEDGER_RECEIPT_MARKER) is _LEDGER_RECEIPT_BOUND


def _receipt(row: Mapping[str, Any], *, mode: str) -> dict[str, Any] | None:
    """Return only a receipt that is cryptographically and procedurally bound.

    A source-looking URL/receipt ID stored on an award row is not provenance on
    its own.  It must either come from this call's uniquely matched immutable
    receipt ledger or carry an explicit boolean verification flag from a prior
    verifier.  Both paths still require the same cryptographic and clock facts.
    """

    if not (_is_ledger_bound(row) or _strict_true(row.get("receipt_verified"))):
        return None
    receipt_id = _first(
        row,
        (
            "source_receipt_id",
            "action_receipt_id" if mode == "action" else "award_detail_receipt_id",
            "award_search_receipt_id",
            "receipt_id",
        ),
    )
    receipt_id = _text(receipt_id)
    if not receipt_id:
        return None
    known_at = iso_instant(row.get("_pit_known_at") or row.get("known_at") or row.get("first_seen_at"))
    effective_at = iso_instant(
        row.get("_pit_effective_at")
        or _first(row, ("effective_at", "action_date", "base_obligation_date", "start_date"))
    )
    content_hash = _first(
        row,
        (
            "source_response_sha256",
            "response_sha256",
            "action_response_sha256" if mode == "action" else "award_response_sha256",
        ),
    )
    content_hash = _text(content_hash)
    url = _valid_receipt_url(_first(row, ("source_url", "receipt_url", "usaspending_url", "award_url")))
    if not known_at or not effective_at or not url or not _SHA256_RE.fullmatch(content_hash):
        return None
    return {
        "ref_id": receipt_id,
        "publisher": "USAspending.gov",
        "record_id": _text(_first(row, ("generated_unique_award_id", "generated_award_id", "award_id", "piid"))),
        "url": url,
        "effective_at": effective_at,
        "known_at": known_at,
        "retrieved_at": known_at,
        "content_sha256": content_hash,
    }


def _receipt_rows(source_receipts: Any) -> list[dict[str, Any]]:
    """Normalize a caller-supplied immutable collection receipt ledger."""

    if source_receipts is None:
        return []
    if isinstance(source_receipts, pd.DataFrame):
        return source_receipts.to_dict(orient="records")
    if isinstance(source_receipts, Mapping):
        if "receipt_id" in source_receipts or "source_receipt_id" in source_receipts:
            return [dict(source_receipts)]
        return [dict(value) for value in source_receipts.values() if isinstance(value, Mapping)]
    return [dict(value) for value in source_receipts if isinstance(value, Mapping)]


def _bind_source_receipts(
    frame: pd.DataFrame,
    source_receipts: Any,
    *,
    mode: str,
) -> pd.DataFrame:
    """Bind only uniquely attributable ledger receipts to raw observations.

    Existing persisted award rows do not currently carry a receipt ID.  A caller
    may pass the immutable collection receipt ledger here, but the binding is
    deliberately narrow: award snapshots require an award-detail receipt and
    actions require exactly one matching action-page receipt for the award/run.
    Ambiguous page-level evidence remains unpublished rather than guessed.
    """

    if frame.empty or source_receipts is None:
        return frame.copy()
    expected_rail = "award_detail" if mode == "snapshot" else "actions"
    index: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for receipt in _receipt_rows(source_receipts):
        if _text(receipt.get("rail")) != expected_rail:
            continue
        subject = receipt.get("subject") if isinstance(receipt.get("subject"), Mapping) else {}
        award_key = _text(subject.get("award_key") or receipt.get("award_key"))
        observed_at = iso_instant(receipt.get("observed_at") or receipt.get("known_at"))
        receipt_id = _text(receipt.get("receipt_id") or receipt.get("source_receipt_id"))
        endpoint = _valid_receipt_url(receipt.get("endpoint") or receipt.get("url"))
        response_hash = _text(receipt.get("response_sha256") or receipt.get("source_response_sha256"))
        if award_key and observed_at and receipt_id and endpoint and _SHA256_RE.fullmatch(response_hash):
            index[(award_key, observed_at)].append(receipt)
    if not index:
        return frame.copy()

    bound = frame.copy()
    for position, row in bound.iterrows():
        award_key = _text(row.get("award_key") or row.get("_award_identity"))
        observed_at = iso_instant(row.get("_pit_known_at") or row.get("known_at") or row.get("first_seen_at"))
        candidates = index.get((award_key, observed_at), []) if award_key and observed_at else []
        # One page is enough to bind an action page.  More than one cannot prove
        # which page contained a particular normalized action, so do not bind it.
        if len(candidates) != 1:
            continue
        receipt = candidates[0]
        bound.at[position, "source_receipt_id"] = _text(receipt.get("receipt_id") or receipt.get("source_receipt_id"))
        # The bound ledger endpoint/hash supersede raw row metadata.  Otherwise
        # a generic search URL could masquerade as the exact receipt page.
        bound.at[position, "source_url"] = _valid_receipt_url(receipt.get("endpoint") or receipt.get("url"))
        bound.at[position, "source_response_sha256"] = _text(receipt.get("response_sha256") or receipt.get("source_response_sha256"))
        bound.at[position, _LEDGER_RECEIPT_MARKER] = _LEDGER_RECEIPT_BOUND
    return bound


def _all_receipts(*receipts: dict[str, Any] | None) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for receipt in receipts:
        if receipt and receipt["ref_id"] not in unique:
            unique[receipt["ref_id"]] = receipt
    return list(unique.values())


def _effective_at(row: Mapping[str, Any]) -> str | None:
    return iso_instant(
        row.get("_pit_effective_at")
        or _first(row, ("effective_at", "action_date", "base_obligation_date", "start_date", "end_date"))
    )


def _known_at(row: Mapping[str, Any]) -> str | None:
    return iso_instant(row.get("_pit_known_at") or row.get("known_at") or row.get("first_seen_at"))


def _value(row: Mapping[str, Any], aliases: Sequence[str]) -> Any:
    return _clean(_first(row, aliases))


def _snapshot_value(row: Mapping[str, Any], canonical_field: str) -> Any:
    aliases = dict(SNAPSHOT_DIFF_FIELDS)[canonical_field]
    return _value(row, aliases)


def _action_value(row: Mapping[str, Any], canonical_field: str) -> Any:
    aliases = dict(ACTION_DIFF_FIELDS)[canonical_field]
    return _value(row, aliases)


def _changed_fields(
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any],
    *,
    mode: str,
    requested: Iterable[str] | None = None,
    source_ref: str | None,
) -> list[dict[str, Any]]:
    configured = SNAPSHOT_DIFF_FIELDS if mode == "snapshot" else ACTION_DIFF_FIELDS
    wanted = set(requested) if requested is not None else None
    changes: list[dict[str, Any]] = []
    for canonical, aliases in configured:
        if wanted is not None and canonical not in wanted:
            continue
        after_value = _value(after, aliases)
        before_value = _value(before or {}, aliases)
        if before is None:
            if after_value is None:
                continue
        elif _same(before_value, after_value):
            continue
        changes.append(
            {
                "field": canonical,
                "before": before_value,
                "after": after_value,
                "semantic": "official",
                "source_ref": source_ref,
            }
        )
    return changes


def _snapshot_groups(changed_fields: list[dict[str, Any]], before: Mapping[str, Any], after: Mapping[str, Any]) -> list[tuple[str, list[dict[str, Any]], list[str]]]:
    """Classify coherent snapshot changes without concealing compound changes."""

    by_name = {item["field"]: item for item in changed_fields}
    result: list[tuple[str, list[dict[str, Any]], list[str]]] = []
    value_items = [by_name[name] for name in ("current_award_amount", "potential_award_amount") if name in by_name]
    if value_items:
        if len(value_items) == 2:
            event_type = "award_value_changed"
        elif value_items[0]["field"] == "potential_award_amount":
            event_type = "ceiling_changed"
        else:
            event_type = "current_value_changed"
        result.append((event_type, value_items, []))
    if "end_date" in by_name:
        prior = timestamp(_snapshot_value(before, "end_date"))
        current = timestamp(_snapshot_value(after, "end_date"))
        event_type = "period_extended" if prior and current and current > prior else "period_shortened"
        result.append((event_type, [by_name["end_date"]], []))
    if "total_obligated_amount" in by_name:
        result.append(("reported_obligation_balance_changed", [by_name["total_obligated_amount"]], []))
    return result


def _action_text(row: Mapping[str, Any]) -> str:
    return " ".join(
        part
        for part in (
            _text(row.get("action_type")),
            _text(row.get("action_type_description")),
            _text(row.get("description")),
            _text(row.get("action_description")),
        )
        if part
    )


def _normalized_semantic(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", _text(value).lower()).strip("_")


def _structured_action_kind(row: Mapping[str, Any]) -> str | None:
    """Read correction/retraction only from explicit source semantics/flags."""

    if any(_strict_true(row.get(name)) for name in ("is_retraction", "action_retracted", "retracted", "rescinded")):
        return "action_retracted"
    if any(_strict_true(row.get(name)) for name in ("is_correction", "action_corrected", "corrected")):
        return "action_corrected"
    values = {_normalized_semantic(row.get(name)) for name in _STRUCTURED_ACTION_FIELDS}
    tokens = {token for value in values for token in value.split("_") if token}
    if values & _RETRACTION_SEMANTICS or tokens & _RETRACTION_SEMANTICS:
        return "action_retracted"
    if values & _CORRECTION_SEMANTICS or tokens & _CORRECTION_SEMANTICS:
        return "action_corrected"
    return None


def _action_text_annotations(row: Mapping[str, Any]) -> list[str]:
    """Retain textual clues without promoting them into source semantics."""

    text = _action_text(row)
    annotations: list[str] = []
    if _RETRACTION_RE.search(text) and _structured_action_kind(row) != "action_retracted":
        annotations.append("unverified_retraction_language")
    if _CORRECTION_RE.search(text) and _structured_action_kind(row) != "action_corrected":
        annotations.append("unverified_correction_language")
    return annotations


def _action_classification(row: Mapping[str, Any]) -> tuple[str | None, list[str]]:
    text = _action_text(row)
    amount = _number(_action_value(row, "federal_action_obligation"))
    amount_type = "obligation" if amount is not None and amount > 0 else "deobligation" if amount is not None and amount < 0 else None
    structured_kind = _structured_action_kind(row)
    if structured_kind:
        return structured_kind, [amount_type] if amount_type else []
    if _OPTION_RE.search(text):
        return "option_exercised", [amount_type] if amount_type else []
    if _EXTENSION_RE.search(text) and _EXTENSION_CONTEXT_RE.search(text):
        return "period_extended", [amount_type] if amount_type else []
    return amount_type, []


def _date_facts(row: Mapping[str, Any], *, source_ref: str | None) -> tuple[list[dict[str, Any]], str | None]:
    known_at = _known_at(row)
    values = (
        ("effective_at", "effective_at", _effective_at(row)),
        ("known_at", "known_at", known_at),
        ("start_date", "start_date", iso_instant(_first(row, ("start_date", "period_of_performance_start_date")))),
        ("end_date", "end_date", iso_instant(_first(row, ("end_date", "period_of_performance_current_end_date")))),
    )
    facts = [
        {
            "id": identifier,
            "label_code": label,
            "value": value,
            "semantic": "official",
            "known_at": known_at,
            "source_ref": source_ref,
        }
        for identifier, label, value in values
        if value is not None
    ]
    primary = "effective_at" if any(fact["id"] == "effective_at" for fact in facts) else (facts[0]["id"] if facts else None)
    return facts, primary


def _amount_facts(
    after: Mapping[str, Any],
    changed_fields: Sequence[Mapping[str, Any]],
    *,
    mode: str,
    source_ref: str | None,
) -> tuple[list[dict[str, Any]], str | None, float | None]:
    canonical = ["current_award_amount", "potential_award_amount", "total_obligated_amount"] if mode == "snapshot" else ["federal_action_obligation"]
    facts: list[dict[str, Any]] = []
    for field in canonical:
        value = _snapshot_value(after, field) if mode == "snapshot" else _action_value(after, field)
        number = _number(value)
        if number is not None:
            facts.append(
                {
                    "id": field,
                    "label_code": field,
                    "value": number,
                    "currency": "USD",
                    "semantic": "official",
                    "as_of": _effective_at(after),
                    "is_lower_bound": False,
                    "source_ref": source_ref,
                }
            )
    delta: float | None = None
    for changed in changed_fields:
        before_value, after_value = _number(changed.get("before")), _number(changed.get("after"))
        if before_value is not None and after_value is not None:
            delta = after_value - before_value
            facts.insert(
                0,
                {
                    "id": f"delta_{changed['field']}",
                    "label_code": f"delta_{changed['field']}",
                    "value": delta,
                    "currency": "USD",
                    "semantic": "derived_from_official_before_after",
                    "as_of": _effective_at(after),
                    "is_lower_bound": False,
                    "source_ref": source_ref,
                },
            )
            break
    primary = facts[0]["id"] if facts else None
    primary_value = facts[0]["value"] if facts else None
    return facts, primary, delta if delta is not None else primary_value


def _company_rows(companies: pd.DataFrame | Sequence[Mapping[str, Any]] | None) -> dict[str, dict[str, Any]]:
    if companies is None:
        return {}
    if isinstance(companies, pd.DataFrame):
        rows = companies.to_dict(orient="records")
    else:
        rows = [dict(item) for item in companies]
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        ticker = _text(_first(row, ("ticker", "symbol"))).upper()
        if ticker:
            result[ticker] = row
    return result


def _ticker(row: Mapping[str, Any]) -> str | None:
    ticker = _text(_first(row, ("ticker", "issuer_ticker", "mapped_ticker"))).upper()
    return ticker or None


def _refs(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, Iterable) or isinstance(value, (bytes, bytearray, Mapping)):
        return []
    return sorted({_text(item) for item in value if _text(item)})


def _recipient_resolution(row: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """Return only an explicit recipient-resolution artifact, never a ticker tag."""

    for field in ("recipient_resolution", "issuer_resolution", "resolution"):
        candidate = row.get(field)
        if isinstance(candidate, Mapping):
            return candidate
    return None


def _resolved_issuer_impact(
    row: Mapping[str, Any],
    company_index: Mapping[str, Mapping[str, Any]],
) -> tuple[str, Mapping[str, Any], Mapping[str, Any], list[Mapping[str, Any]], list[str]] | None:
    """Validate the resolution state, issuer agreement, ownership path and proof."""

    resolution = _recipient_resolution(row)
    if resolution is None:
        return None
    state = _text(resolution.get("resolution_state")).lower()
    issuer = resolution.get("issuer")
    ownership_path = resolution.get("ownership_path")
    if state not in {"confirmed", "reviewed"} or not isinstance(issuer, Mapping):
        return None
    if not isinstance(ownership_path, list) or not ownership_path or not all(isinstance(edge, Mapping) for edge in ownership_path):
        return None
    ticker = _text(issuer.get("ticker")).upper()
    if not ticker:
        return None
    raw_ticker = _ticker(row)
    if raw_ticker is not None and raw_ticker != ticker:
        return None
    company = company_index.get(ticker)
    if not isinstance(company, Mapping):
        return None
    company_ticker = _text(_first(company, ("ticker", "symbol"))).upper()
    if company_ticker != ticker:
        return None
    issuer_company_id = _text(issuer.get("company_id"))
    company_id = _text(_first(company, ("company_id", "id")))
    if issuer_company_id and company_id and issuer_company_id != company_id:
        return None
    resolution_refs = _refs(resolution.get("evidence_refs"))
    path_refs = sorted(
        {
            ref
            for edge in ownership_path
            for ref in _refs(edge.get("evidence_refs"))
        }
    )
    # A state label alone is not attribution evidence.  Require proof both for
    # the resolution and for at least one ownership edge to the public issuer.
    if not resolution_refs or not path_refs:
        return None
    return ticker, company, resolution, ownership_path, sorted(set(resolution_refs + path_refs))


def _impact(
    row: Mapping[str, Any],
    company_index: Mapping[str, Mapping[str, Any]],
    *,
    amount: float | None,
    source_ref: str | None,
) -> dict[str, Any] | None:
    resolved = _resolved_issuer_impact(row, company_index)
    if resolved is None:
        return None
    ticker, company, resolution, ownership_path, resolution_refs = resolved
    metrics = company.get("metrics") if isinstance(company.get("metrics"), Mapping) else {}
    denominator = _number(
        _first(
            {**company, **metrics},
            ("ttm_government_obligations", "government_obligations_ttm", "ttm_obligations"),
        )
    )
    absolute_amount = abs(amount) if amount is not None else None
    ratio = absolute_amount / denominator if absolute_amount is not None and denominator and denominator > 0 else None
    if ratio is None:
        band, score = "unknown", 0.0
    elif ratio >= 0.10:
        band, score = "high", 1.0
    elif ratio >= 0.02:
        band, score = "medium", 0.6
    else:
        band, score = "low", 0.3
    resolution_state = _text(resolution.get("resolution_state")).lower()
    confidence = "high" if resolution_state == "confirmed" else "medium"
    evidence_refs = sorted(set(resolution_refs + ([source_ref] if source_ref else [])))
    return {
        "ticker": ticker,
        "company_name": _clean(_first(company, ("company_name", "name", "issuer_name")) or resolution.get("issuer", {}).get("name")),
        "issuer_company_id": _clean(resolution.get("issuer", {}).get("company_id")),
        "resolution_state": resolution_state,
        "relation_semantic": "reviewed",
        "confidence": confidence,
        "stance": "watch_dont_chase",
        "stance_scope": "research",
        "materiality": {
            "basis": "absolute event amount / resolved issuer TTM government obligations",
            "event_amount_usd": absolute_amount,
            "government_obligations_ttm_usd": denominator,
            "ratio": ratio,
            "band": band,
            "score": score,
        },
        "evidence_refs": evidence_refs,
        "ownership_path": [_clean(edge) for edge in ownership_path],
        "cross_desk_links": [],
    }


def _impacts(
    impact_rows: Sequence[Mapping[str, Any]],
    company_index: Mapping[str, Mapping[str, Any]],
    *,
    amount: float | None,
    source_ref: str | None,
) -> list[dict[str, Any]]:
    by_ticker: dict[str, dict[str, Any]] = {}
    for row in impact_rows:
        impact = _impact(row, company_index, amount=amount, source_ref=source_ref)
        if impact is None:
            continue
        current = by_ticker.get(impact["ticker"])
        if current is None or impact["materiality"]["score"] > current["materiality"]["score"]:
            by_ticker[impact["ticker"]] = impact
    return sorted(by_ticker.values(), key=lambda item: (-item["materiality"]["score"], item["ticker"]))


def _display_priority(*, event_type: str, impacts: Sequence[Mapping[str, Any]], is_correction: bool) -> dict[str, Any]:
    new_information = 1.0 if event_type in {"new_award", "award_discovered_late", "obligation", "deobligation", "option_exercised"} else 0.8
    if is_correction:
        new_information = 0.7
    company_materiality = max((float(item["materiality"]["score"]) for item in impacts), default=0.0)
    evidence_quality = 0.95
    score = round(100 * (0.45 * new_information + 0.30 * company_materiality + 0.25 * evidence_quality), 2)
    return {
        "score": score,
        "new_information": new_information,
        "company_materiality": company_materiality,
        "evidence_quality": evidence_quality,
        "formula_version": DISPLAY_FORMULA_VERSION,
        "is_investment_rank": False,
        "tie_breakers": ["effective_at_desc", "known_at_desc", "event_id_asc"],
    }


def _agency(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "name": _clean(_first(row, ("awarding_agency", "agency_name", "agency"))),
        "subagency": _clean(_first(row, ("awarding_sub_agency", "subagency_name"))),
    }


def _title(event_type: str, row: Mapping[str, Any]) -> str:
    labels = {
        "new_award": "New award observed",
        "award_discovered_late": "Award discovered after effective date",
        "obligation": "New obligation observed",
        "deobligation": "Deobligation observed",
        "current_value_changed": "Current award value changed",
        "ceiling_changed": "Award ceiling changed",
        "award_value_changed": "Award values changed",
        "option_exercised": "Option exercise observed",
        "period_extended": "Period of performance extended",
        "period_shortened": "Period of performance shortened",
        "action_revised": "Award action revised",
        "action_corrected": "Award action corrected",
        "action_retracted": "Award action retracted",
        "reported_obligation_balance_changed": "Reported obligated balance changed",
    }
    identifier = _text(_first(row, ("award_id", "piid", "generated_unique_award_id", "generated_award_id")))
    return f"{labels[event_type]} — {identifier or 'USAspending award'}"


def _event_id(
    *,
    award_key: str,
    source_rail: str,
    state_hash: str,
    known_at: str | None,
    event_type: str,
    changed_fields: Sequence[Mapping[str, Any]],
) -> str:
    # known_at is deliberate: A -> B -> A emits three distinct immutable events.
    seed = {
        "award_key": award_key,
        "source_rail": source_rail,
        "state_hash": state_hash,
        "known_at": known_at,
        "event_type": event_type,
        "changed_fields": [
            {"field": item["field"], "before": item["before"], "after": item["after"]}
            for item in changed_fields
        ],
    }
    return f"govws-{_hash(seed)[:24]}"


def _make_event(
    *,
    row: Mapping[str, Any],
    before: Mapping[str, Any] | None,
    mode: str,
    event_type: str,
    secondary_types: Sequence[str],
    changed_fields: list[dict[str, Any]],
    impact_rows: Sequence[Mapping[str, Any]],
    company_index: Mapping[str, Mapping[str, Any]],
    is_correction: bool,
    is_late_discovery: bool,
) -> dict[str, Any] | None:
    receipt = _receipt(row, mode=mode)
    prior_receipt = _receipt(before, mode=mode) if before is not None else None
    # A fact can be baseline data without a receipt.  It cannot power a public
    # before/after event, because that would make the "before" unverifiable.
    if receipt is None or (before is not None and prior_receipt is None):
        return None
    bound_changed_fields: list[dict[str, Any]] = []
    for changed in changed_fields:
        bound = dict(changed)
        # The inherited v1 ``source_ref`` remains the after-state reference;
        # v2 adds both sides explicitly so a reviewer can audit a transition
        # without guessing which receipt supplied each value.
        bound["before_source_ref"] = prior_receipt.get("url") if prior_receipt else None
        bound["after_source_ref"] = receipt.get("url")
        bound["before_receipt_ref"] = prior_receipt.get("ref_id") if prior_receipt else None
        bound["after_receipt_ref"] = receipt.get("ref_id")
        bound_changed_fields.append(bound)
    changed_fields = bound_changed_fields
    award_key = _text(row.get("_award_identity"))
    if not award_key:
        return None
    source_ref = receipt.get("url")
    facts, primary_amount_id, material_amount = _amount_facts(
        row, changed_fields, mode=mode, source_ref=source_ref
    )
    impacts = _impacts(impact_rows, company_index, amount=material_amount, source_ref=source_ref)
    known_at, effective_at = _known_at(row), _effective_at(row)
    source_rail = "usaspending_award_snapshot" if mode == "snapshot" else "usaspending_award_action"
    state_hash = _text(row.get("_source_state_hash"))
    event_id = _event_id(
        award_key=award_key,
        source_rail=source_rail,
        state_hash=state_hash,
        known_at=known_at,
        event_type=event_type,
        changed_fields=changed_fields,
    )
    dates, primary_date_id = _date_facts(row, source_ref=source_ref)
    raw_content_hash = _text(
        _first(
            row,
            (
                "source_response_sha256",
                "response_sha256",
                "snapshot_content_sha256",
                "award_state_sha256",
                "action_content_sha256",
                "content_sha256",
                "action_sha256",
            ),
        )
    )
    source_identity = {
        "id": award_key if mode == "snapshot" else _text(row.get("_action_identity")),
        "version": state_hash,
        "content_sha256": raw_content_hash or state_hash,
    }
    award_change = {
        "award_key": award_key,
        "generated_award_id": _clean(_first(row, ("generated_unique_award_id", "generated_award_id"))),
        "piid": _clean(_first(row, ("award_id", "piid"))),
        "recipient_name": _clean(row.get("recipient_name")),
        "event_type": event_type,
        "secondary_types": list(dict.fromkeys(item for item in secondary_types if item and item != event_type)),
        "source_rail": source_rail,
        "source_identity": source_identity,
        "observation_kind": mode,
        "coverage_scope": COVERAGE_SCOPE,
        "is_late_discovery": is_late_discovery,
        "action_id": _clean(
            _first(row, ("action_id", "action_uid", "transaction_id", "transaction_unique_id", "award_transaction_id"))
        ),
        "prior_source_identity": _clean(before.get("_source_state_hash")) if before is not None else None,
    }
    if mode == "action":
        award_change["text_annotations"] = _action_text_annotations(row)
    mapping_class = "reviewed" if impacts else "unmapped"
    return {
        "contract": "government_procurement_event.v2",
        "event_id": event_id,
        "record_id": f"award:{award_key}",
        "version": 1,
        "kind": "award_change",
        "state": "updated",
        "title_original": _title(event_type, row),
        "title_zh": None,
        "translation_status": "original",
        "agency": _agency(row),
        "change": {
            "type": event_type,
            "what_changed_en": _title(event_type, row),
            "what_changed_zh": "",
            "summary_origin": "deterministic_template",
            "effective_at": effective_at,
            "known_at": known_at,
            "first_seen_at": known_at,
            "last_seen_at": known_at,
            "is_correction": is_correction,
            "changed_fields": changed_fields,
        },
        "opportunity": None,
        "recompete": None,
        "award_change": award_change,
        "dates": dates,
        "amounts": facts,
        "primary_date_id": primary_date_id,
        "primary_amount_id": primary_amount_id,
        "listed_company_impacts": impacts,
        "primary_ticker": impacts[0]["ticker"] if impacts else None,
        "display_priority": _display_priority(event_type=event_type, impacts=impacts, is_correction=is_correction),
        "evidence": {
            "source_class": "observed_source_revision" if is_correction else "official_fact",
            "mapping_class": mapping_class,
            "receipts": _all_receipts(receipt, prior_receipt),
            "derivations": [
                {
                    "method": "strict_dual_clock_before_after.v1",
                    "detail": "Event emitted only from explicitly eligible, receipt-bound observations visible under both clocks.",
                }
            ],
            "conflicts": [],
            "limitations": [
                "Display-only context; cannot rank, size, gate, originate, or escalate a signal.",
                COVERAGE_SCOPE,
            ],
        },
        "authority": dict(AUTHORITY),
    }


def _consolidate(frame: pd.DataFrame, *, mode: str) -> list[dict[str, Any]]:
    """Collapse duplicate ticker/mapping rows into one source observation.

    The source state identity ignores mappings.  This lets the same award change
    produce one event with multiple company impacts instead of N duplicate cards.
    """

    if frame.empty:
        return []
    prepared = frame.copy()
    prepared["_source_state_hash"] = prepared.apply(lambda row: _state_hash(row, mode=mode), axis=1)
    if mode == "action":
        prepared["_action_identity"] = prepared.apply(_action_identity, axis=1)
        keys = ["_award_identity", "_action_identity", "_pit_known_at", "_source_state_hash"]
        prepared = prepared.dropna(subset=["_action_identity"])
    else:
        keys = ["_award_identity", "_pit_known_at", "_source_state_hash"]
    prepared = prepared.dropna(subset=["_award_identity"])
    result: list[dict[str, Any]] = []
    for _, group in prepared.groupby(keys, dropna=False, sort=False):
        group = group.sort_index(kind="mergesort")
        records = group.to_dict(orient="records")
        eligible = [record for record in records if _is_event_eligible(record)]
        receipt_bound_eligible = [record for record in eligible if _receipt(record, mode=mode) is not None]
        receipt_bound_any = [record for record in records if _receipt(record, mode=mode) is not None]
        selected = dict(
            receipt_bound_eligible[0]
            if receipt_bound_eligible
            else receipt_bound_any[0]
            if receipt_bound_any
            else eligible[0]
            if eligible
            else records[0]
        )
        selected["_event_eligible"] = bool(eligible)
        selected["_impact_rows"] = records
        result.append(selected)
    sort_keys = (lambda row: (str(row.get("_award_identity")), str(row.get("_action_identity", "")), str(row.get("_pit_known_at"))))
    return sorted(result, key=sort_keys)


def _is_late_discovery(row: Mapping[str, Any], *, late_discovery_days: int) -> bool:
    known_at = timestamp(_known_at(row))
    effective_at = timestamp(_effective_at(row))
    if known_at is None or effective_at is None:
        return True
    return known_at - effective_at > pd.Timedelta(days=late_discovery_days)


def _project_snapshots(
    snapshots: pd.DataFrame,
    *,
    company_index: Mapping[str, Mapping[str, Any]],
    late_discovery_days: int,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    by_award: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for observation in _consolidate(snapshots, mode="snapshot"):
        by_award[str(observation["_award_identity"])].append(observation)
    for observations in by_award.values():
        prior: dict[str, Any] | None = None
        for current in observations:
            if current["_event_eligible"]:
                if prior is None:
                    late = _is_late_discovery(current, late_discovery_days=late_discovery_days)
                    event_type = "award_discovered_late" if late else "new_award"
                    source_ref = (_receipt(current, mode="snapshot") or {}).get("url")
                    changes = _changed_fields(None, current, mode="snapshot", source_ref=source_ref)
                    event = _make_event(
                        row=current,
                        before=None,
                        mode="snapshot",
                        event_type=event_type,
                        secondary_types=[],
                        changed_fields=changes,
                        impact_rows=current["_impact_rows"],
                        company_index=company_index,
                        is_correction=False,
                        is_late_discovery=late,
                    )
                    if event:
                        events.append(event)
                else:
                    source_ref = (_receipt(current, mode="snapshot") or {}).get("url")
                    changes = _changed_fields(prior, current, mode="snapshot", source_ref=source_ref)
                    for event_type, grouped_fields, secondary in _snapshot_groups(changes, prior, current):
                        event = _make_event(
                            row=current,
                            before=prior,
                            mode="snapshot",
                            event_type=event_type,
                            secondary_types=secondary,
                            changed_fields=grouped_fields,
                            impact_rows=current["_impact_rows"],
                            company_index=company_index,
                            is_correction=False,
                            is_late_discovery=False,
                        )
                        if event:
                            events.append(event)
            prior = current
    return events


def _project_actions(actions: pd.DataFrame, *, company_index: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    by_action: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for observation in _consolidate(actions, mode="action"):
        identity = _text(observation.get("_action_identity"))
        if identity:
            by_action[(str(observation["_award_identity"]), identity)].append(observation)
    for observations in by_action.values():
        prior: dict[str, Any] | None = None
        for current in observations:
            if current["_event_eligible"]:
                source_ref = (_receipt(current, mode="action") or {}).get("url")
                if prior is None:
                    event_type, secondary = _action_classification(current)
                    if event_type is not None:
                        changes = _changed_fields(None, current, mode="action", source_ref=source_ref)
                        event = _make_event(
                            row=current,
                            before=None,
                            mode="action",
                            event_type=event_type,
                            secondary_types=secondary,
                            changed_fields=changes,
                            impact_rows=current["_impact_rows"],
                            company_index=company_index,
                            is_correction=event_type in {"action_corrected", "action_retracted"},
                            is_late_discovery=False,
                        )
                        if event:
                            events.append(event)
                else:
                    changes = _changed_fields(prior, current, mode="action", source_ref=source_ref)
                    if changes:
                        explicit_type, secondary = _action_classification(current)
                        event_type = (
                            explicit_type
                            if explicit_type in {"action_retracted", "action_corrected"}
                            else "action_revised"
                        )
                        if explicit_type and explicit_type not in {"action_retracted", "action_corrected"}:
                            secondary = [explicit_type, *secondary]
                        event = _make_event(
                            row=current,
                            before=prior,
                            mode="action",
                            event_type=event_type,
                            secondary_types=secondary,
                            changed_fields=changes,
                            impact_rows=current["_impact_rows"],
                            company_index=company_index,
                            is_correction=event_type in {"action_corrected", "action_retracted"},
                            is_late_discovery=False,
                        )
                        if event:
                            events.append(event)
            prior = current
    return events


def _merge(events: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge only exact duplicate source events, preserving their immutable IDs."""

    merged: dict[str, dict[str, Any]] = {}
    for event in events:
        existing = merged.get(event["event_id"])
        if existing is None:
            merged[event["event_id"]] = event
            continue
        impacts = {item["ticker"]: item for item in existing["listed_company_impacts"]}
        for item in event["listed_company_impacts"]:
            prior = impacts.get(item["ticker"])
            if prior is None or item["materiality"]["score"] > prior["materiality"]["score"]:
                impacts[item["ticker"]] = item
        existing["listed_company_impacts"] = sorted(
            impacts.values(), key=lambda item: (-item["materiality"]["score"], item["ticker"])
        )
        existing["primary_ticker"] = existing["listed_company_impacts"][0]["ticker"] if existing["listed_company_impacts"] else None
        existing["display_priority"] = _display_priority(
            event_type=existing["change"]["type"],
            impacts=existing["listed_company_impacts"],
            is_correction=existing["change"]["is_correction"],
        )
        receipts = _all_receipts(*existing["evidence"]["receipts"], *event["evidence"]["receipts"])
        existing["evidence"]["receipts"] = receipts
        existing["evidence"]["mapping_class"] = "deterministic_inference" if impacts else "unmapped"
    return sorted(
        merged.values(),
        key=lambda event: (
            event["change"]["effective_at"] or "",
            event["change"]["known_at"] or "",
            event["event_id"],
        ),
        reverse=True,
    )


def build_award_change_events(
    award_snapshots: pd.DataFrame | None,
    action_versions: pd.DataFrame | None,
    *,
    companies: pd.DataFrame | Sequence[Mapping[str, Any]] | None = None,
    source_receipts: pd.DataFrame | Sequence[Mapping[str, Any]] | Mapping[str, Any] | None = None,
    as_of: Any,
    known_at: Any | None = None,
    effective_as_of: Any | None = None,
    late_discovery_days: int = DEFAULT_LATE_DISCOVERY_DAYS,
) -> list[dict[str, Any]]:
    """Project receipt-bound award events visible at a specific dual-clock time.

    ``as_of`` determines the historical effective-date ceiling.  ``known_at``
    optionally makes the knowledge ceiling earlier than the end of that day.
    ``source_receipts`` can supply immutable collection-receipt rows when the
    persisted observations have not yet been receipt-bound.  Inputs are never
    mutated.  This is a display/context-only projection; the resulting records
    deliberately carry a fail-closed authority object.
    """

    if late_discovery_days < 0:
        raise ValueError("late_discovery_days must be non-negative")
    _, day_cutoff = analysis_clock(as_of)
    knowledge_cutoff = timestamp(known_at) if known_at is not None else day_cutoff
    effective_cutoff = timestamp(effective_as_of) if effective_as_of is not None else day_cutoff
    if knowledge_cutoff is None or effective_cutoff is None:
        raise ValueError("known_at/effective_as_of must be parseable timestamps")
    snapshots_frame = award_snapshots.copy() if isinstance(award_snapshots, pd.DataFrame) else pd.DataFrame()
    actions_frame = action_versions.copy() if isinstance(action_versions, pd.DataFrame) else pd.DataFrame()
    snapshots_visible = with_award_identity(
        filter_dual_clock(
            snapshots_frame,
            knowledge_cutoff=knowledge_cutoff,
            effective_cutoff=effective_cutoff,
        )
    )
    actions_visible = with_award_identity(
        filter_dual_clock(
            actions_frame,
            knowledge_cutoff=knowledge_cutoff,
            effective_cutoff=effective_cutoff,
        )
    )
    snapshots_visible = _bind_source_receipts(snapshots_visible, source_receipts, mode="snapshot")
    actions_visible = _bind_source_receipts(actions_visible, source_receipts, mode="action")
    company_index = _company_rows(companies)
    return _merge(
        [
            *_project_snapshots(
                snapshots_visible,
                company_index=company_index,
                late_discovery_days=late_discovery_days,
            ),
            *_project_actions(actions_visible, company_index=company_index),
        ]
    )


# Two descriptive aliases make the foundation easy to adopt without importing a
# workspace builder or assigning it any operating authority.
project_award_events = build_award_change_events
project_award_change_events = build_award_change_events
