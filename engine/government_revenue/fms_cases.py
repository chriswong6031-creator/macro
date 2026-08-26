"""Deterministic read-model builder for the FMS congressional-notification rail.

Consumes the append-only observation plane (``collectors/fms_notifications.py``
rows) and projects it into ``government_fms_case.v1``: one case per identity
(transmittal, or fallback when no transmittal is ever printed), with the
D6-B1 official-union coverage manifest and reconciliation gate
(spec §7). No network. No LLM. Deterministic given its inputs.

Frozen laws this module enforces (see
``research/defense_intelligence/DEFENSE_D6B1_FMS_IMPLEMENTATION_SPEC_2026-08-25.md``):

* Stage is always ``congressional_notification`` (§6; zero review-period
  arithmetic anywhere in this module).
* ``estimated_notification_value`` is null-never-zero and is NEVER summed or
  aggregated across cases anywhere in this module's output (§5, T13).
* FR publication date is never a case clock (§7, B5). FR joins
  ``official_notification_date`` from the "(viii) Date Report Delivered to
  Congress" field only.
* A zero or unreconciled official denominator can never publish silently —
  :func:`build_fms_case_graph` raises :class:`FmsCoverageRefused` instead
  (§7, B7).
* Fallback<->recovery country collisions are flagged ``conflicted`` on BOTH
  cases; they are never auto-merged (§2, B9).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence

from collectors.fms_notifications import check_mis_key, fallback_collision

FMS_CASE_GRAPH_CONTRACT = "government_fms_case.v1"
FMS_CASE_GRAPH_SCHEMA_VERSION = "1.0.0"
FMS_CASE_GRAPH_CONTENT_PREFIX = "grfms1-"

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

PROGRAM_LINK_NOT_REVIEWED: dict[str, Any] = {
    "state": "not_reviewed",
    "reason_code": "no_reviewed_program_link",
    "program_id": None,
    "program_case_link_id": None,
    "ontology_graph_id": None,
}


class FmsCoverageRefused(ValueError):
    """The official-union coverage gate refused to publish (spec §7, B7)."""


def _canonical_json(value: object) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False, default=str,
    )


def _sha256_json(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _utc_iso(value: str | datetime | None) -> str:
    if value is None:
        parsed = datetime.now(timezone.utc)
    elif isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamps must be offset-aware")
    return parsed.astimezone(timezone.utc).isoformat()


def fms_case_graph_content_id(payload: Mapping[str, Any]) -> str:
    fingerprint = {
        key: value for key, value in payload.items()
        if key not in {"content_id", "generated_at"}
    }
    return FMS_CASE_GRAPH_CONTENT_PREFIX + _sha256_json(fingerprint)[:24]


def _observation_projection(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "observation_id": row["observation_id"],
        "source_surface": row["source_surface"],
        "kind": row["kind"],
        "version": row["version"],
        "source_url": row["source_url"],
        "response_sha256": row["response_sha256"],
        "bytes": row["bytes"],
        "transport": row["transport"],
        "observed_at": row["observed_at"],
        "known_at": row["known_at"],
        "r2_object_key": row["r2_object_key"],
    }


def _is_fallback_key(case_key: str) -> bool:
    return case_key.startswith("fms:urlpath:")


def _transmittal_of(case_key: str) -> str | None:
    if case_key.startswith("fms:transmittal:"):
        return case_key.removeprefix("fms:transmittal:")
    return None


def _clock(value: str | None, provenance: str | None) -> dict[str, Any]:
    return {"value": value, "provenance": provenance if value is not None else None}


def _stage_for_case(observations: Sequence[Mapping[str, Any]]) -> str:
    """Return the case stage. ALWAYS the v1 constant — never a function of time.

    This function deliberately takes no "now"/elapsed-time argument: there is
    no calendar input anywhere it could compute a review-period-elapsed
    conclusion from (freeze §4.4, spec §16 T3). ``observations`` is accepted
    only so a future authorized advancement-evidence class (§4.3) has a
    natural extension point; v1 never inspects it.
    """
    del observations  # v1 provable subset is exactly one stage (freeze §4.2)
    return "congressional_notification"


def _classify_surfaces(surfaces: set[str], *, is_fallback: bool) -> str:
    if is_fallback:
        return "state_fallback"
    has_state, has_dsca, has_fr = (
        "state" in surfaces, "dsca" in surfaces, "federal_register" in surfaces,
    )
    if has_dsca and has_fr:
        return "dsca_and_fr"
    if has_state and has_fr:
        return "state_and_fr"
    if has_fr and not has_state and not has_dsca:
        return "fr_only"
    if has_state and not has_fr:
        return "state_only"
    if has_dsca and not has_fr:
        return "dsca_only"
    raise ValueError(f"cannot classify FMS source coverage for surfaces={surfaces!r}")


def _build_one_case(case_key: str, observations: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    """Build one case from its grouped observations, or ``None`` if it must not exist.

    A group containing ONLY correction/retraction observations (no primary
    ``listing_article`` / ``certification_pdf`` / ``fr_raw_text`` row) never
    mints a case (spec §2/§8: corrections attach, they never mint).
    """
    primary = [row for row in observations if row["kind"] not in {"fr_correction", "retraction_observed"}]
    if not primary:
        return None

    surfaces = {row["source_surface"] for row in primary}
    is_fallback = _is_fallback_key(case_key)
    classification = _classify_surfaces(surfaces, is_fallback=is_fallback)
    web_presence = classification != "fr_only"

    # web body (state/dsca) takes precedence for customer/title/contractor;
    # FR supplies purchaser/description/value only when no web body exists,
    # and NEVER supplies capability_title (spec §4: null for fr_only).
    web_rows = [row for row in primary if row["source_surface"] in {"state", "dsca"}]
    fr_rows = [row for row in primary if row["source_surface"] == "federal_register"]
    web_rows_sorted = sorted(web_rows, key=lambda r: r["known_at"])
    fr_rows_sorted = sorted(fr_rows, key=lambda r: r["known_at"])
    latest_web = web_rows_sorted[-1]["fields"] if web_rows_sorted else None
    latest_fr = fr_rows_sorted[-1]["fields"] if fr_rows_sorted else None

    conflicted = any(
        row["fields"].get("identity_conflicted") or row["fields"].get("value_conflicted")
        for row in primary
    )

    customer_country = None
    if latest_web is not None:
        customer_country = latest_web.get("customer_country")
    elif latest_fr is not None:
        customer_country = latest_fr.get("customer_country")
    # mis-key guard across surfaces sharing this case key (honorific-stripped
    # comparison: "Sweden" title-prefix vs "Government of Sweden" FR
    # purchaser is the SAME country, never a mis-key).
    seen_country: str | None = None
    for row in primary:
        row_country = row["fields"].get("customer_country")
        if row_country is None:
            continue
        if seen_country is not None and check_mis_key(seen_country, row_country):
            conflicted = True
        seen_country = row_country

    capability_title = latest_web.get("title") if latest_web is not None else None

    source_item_enumeration = None
    if latest_fr is not None:
        source_item_enumeration = latest_fr.get("source_item_enumeration")

    # Value precedence (spec §4): web body first, FR total otherwise; a
    # material web<->FR disagreement conflicts the case and nulls the value.
    web_value = latest_web.get("estimated_notification_value") if latest_web is not None else None
    web_provenance = latest_web.get("value_provenance") if latest_web is not None else None
    fr_value = latest_fr.get("estimated_notification_value") if latest_fr is not None else None
    if web_value is not None:
        if fr_value is not None and fr_value != web_value:
            conflicted = True
            value, value_provenance = None, None
        else:
            value, value_provenance = web_value, web_provenance
    elif fr_value is not None:
        value, value_provenance = fr_value, "fr_total_estimated_value"
    else:
        value, value_provenance = None, None

    source_caveat = latest_web.get("source_caveat") if latest_web is not None else None

    contractors: list[dict[str, Any]] = []
    contractor_note = None
    if latest_web is not None:
        contractors = list(latest_web.get("contractors") or [])
        contractor_note = latest_web.get("contractor_note")

    # Clocks. official_notification_date: DSCA-era from the DSCA dateline;
    # State-era null unless an FR join supplies the delivered date (never
    # copied from the State page date — Sol U3). FR publication_date is
    # never consulted as a clock anywhere in this function (B5).
    dsca_rows = [row for row in web_rows_sorted if row["source_surface"] == "dsca"]
    state_rows = [row for row in web_rows_sorted if row["source_surface"] == "state"]
    official_notification_date, notification_provenance = None, None
    if dsca_rows:
        dsca_fields = dsca_rows[-1]["fields"]
        if dsca_fields.get("official_notification_date"):
            official_notification_date = dsca_fields["official_notification_date"]
            notification_provenance = "dsca_body_dateline"
    if official_notification_date is None and latest_fr is not None:
        fr_delivered = latest_fr.get("official_notification_date")
        if fr_delivered:
            official_notification_date = fr_delivered
            notification_provenance = "fr_delivered_to_congress"

    official_web_publication_date, web_pub_provenance = None, None
    if state_rows:
        state_fields = state_rows[-1]["fields"]
        if state_fields.get("official_web_publication_date"):
            official_web_publication_date = state_fields["official_web_publication_date"]
            web_pub_provenance = "state_header_date"
    if official_web_publication_date is None and dsca_rows:
        dsca_fields = dsca_rows[-1]["fields"]
        if dsca_fields.get("official_web_publication_date"):
            official_web_publication_date = dsca_fields["official_web_publication_date"]
            web_pub_provenance = "dsca_article_date"

    first_observed_at = min(row["known_at"] for row in observations)

    case_state = "current"
    if any(row["kind"] == "retraction_observed" for row in observations):
        case_state = "retraction_observed"
    elif any(row["kind"] == "fr_correction" for row in observations):
        case_state = "corrected"
    if conflicted:
        case_state = "conflicted"

    transmittal_number = _transmittal_of(case_key)
    identity_basis = "url_fallback" if is_fallback else "transmittal"

    return {
        "case_key": case_key,
        "transmittal_number": transmittal_number,
        "identity_basis": identity_basis,
        "case_identity_state": "conflicted" if conflicted else "resolved",
        "aliases": [],
        "customer_country": customer_country,
        "capability_title": capability_title,
        "source_item_enumeration": source_item_enumeration,
        "stage": _stage_for_case(observations),
        "later_stages": "stage_not_observed",
        "advancement_condition": "official_evidence_of_offered_accepted_or_implemented_loa",
        "estimated_notification_value": value,
        "currency": "USD",
        "source_caveat": source_caveat,
        "value_provenance": value_provenance,
        "contractors": contractors,
        "contractor_note": contractor_note,
        "program_links": [dict(PROGRAM_LINK_NOT_REVIEWED)],
        "clocks": {
            "official_notification_date": _clock(official_notification_date, notification_provenance),
            "official_web_publication_date": _clock(official_web_publication_date, web_pub_provenance),
            "first_observed_at": first_observed_at,
        },
        "source_coverage": {
            "classification": classification,
            "surfaces": sorted(surfaces),
            "web_presence": web_presence,
        },
        "observations": [_observation_projection(row) for row in sorted(observations, key=lambda r: (r["known_at"], r["version"]))],
        "case_state": case_state,
    }


def _apply_fallback_recovery_collisions(cases: list[dict[str, Any]]) -> None:
    fallback_cases = [c for c in cases if c["identity_basis"] == "url_fallback"]
    recovery_cases = [c for c in cases if c["source_coverage"]["classification"] == "fr_only"]
    for fallback in fallback_cases:
        for recovery in recovery_cases:
            country_a, country_b = fallback["customer_country"], recovery["customer_country"]
            if fallback_collision(country_a, country_b):
                fallback["case_identity_state"] = "conflicted"
                fallback["case_state"] = "conflicted"
                recovery["case_identity_state"] = "conflicted"
                recovery["case_state"] = "conflicted"


def build_fms_case_graph(
    *,
    observations: Sequence[Mapping[str, Any]],
    as_of: str,
    scope_delivered_from: str,
    scope_delivered_through: str,
    fr_denominator_transmittals: Iterable[str],
    fr_docs_scanned: int,
    fr_amendments_excluded: int,
    fr_corrections: int,
    fr_status: str,
    state_listing_pages: int,
    state_qualifying_articles: int,
    state_status: str,
    dsca_articles_staged: int,
    dsca_status: str,
    history_disclosure: str,
    generated_at: str | datetime | None = None,
    known_at: str | datetime | None = None,
) -> dict[str, Any]:
    """Build the content-addressed FMS case graph, or refuse to publish.

    Refuses (raises :class:`FmsCoverageRefused`) when the FR denominator is
    empty, the FR source status is not ``ok``, or any denominator
    transmittal has no built case — spec §7's publication gate. A State
    fetch failure alone (``state_status`` != ``ok``) does NOT refuse: FR/DSCA
    truth still publishes with the State status disclosed (B6).
    """
    denominator = sorted({str(t) for t in fr_denominator_transmittals})

    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in observations:
        grouped.setdefault(row["case_key"], []).append(dict(row))

    cases: list[dict[str, Any]] = []
    for case_key, rows in grouped.items():
        case = _build_one_case(case_key, rows)
        if case is not None:
            cases.append(case)
    cases.sort(key=lambda c: c["case_key"])

    _apply_fallback_recovery_collisions(cases)

    built_transmittals = {c["transmittal_number"] for c in cases if c["transmittal_number"]}
    denominator_unbuilt = [t for t in denominator if t not in built_transmittals]

    if fr_status != "ok" or len(denominator) == 0 or denominator_unbuilt:
        raise FmsCoverageRefused(
            "FMS coverage gate refused to publish: "
            f"fr_status={fr_status!r} denominator={len(denominator)} unbuilt={denominator_unbuilt!r}"
        )

    web_only_cases = sum(
        1 for c in cases
        if c["source_coverage"]["classification"] in {"state_only", "dsca_only", "state_fallback"}
    )
    web_absent_cases = sorted(
        c["transmittal_number"] for c in cases
        if c["source_coverage"]["classification"] == "fr_only" and c["transmittal_number"]
    )

    coverage = {
        "law": "official_union_v1",
        "sources": {
            "federal_register": {
                "role": "denominator_and_recovery",
                "publication_window": [scope_delivered_from, scope_delivered_through],
                "docs_scanned": fr_docs_scanned,
                "originals": len(denominator),
                "amendments_excluded": fr_amendments_excluded,
                "corrections": fr_corrections,
                "status": fr_status,
            },
            "state_pm_bureau": {
                "role": "current_presentation",
                "listing_pages": state_listing_pages,
                "qualifying_articles": state_qualifying_articles,
                "status": state_status,
            },
            "dsca_press": {
                "role": "historical_observations_bounded",
                "articles_staged": dsca_articles_staged,
                "status": dsca_status,
                "disclosure": (
                    "In-scope 2026 articles + the 26-13 certification PDF only; "
                    "the pre-2026 DSCA archive is NOT covered."
                ),
            },
        },
        "history_disclosure": history_disclosure,
        "reconciliation": {
            "denominator_transmittals": len(denominator),
            "cases_built": len(cases),
            "denominator_unbuilt": denominator_unbuilt,
            "web_only_cases": web_only_cases,
            "web_absent_cases": web_absent_cases,
        },
    }

    graph: dict[str, Any] = {
        "contract": FMS_CASE_GRAPH_CONTRACT,
        "schema_version": FMS_CASE_GRAPH_SCHEMA_VERSION,
        "content_id": "",
        "as_of": str(as_of),
        "known_at": _utc_iso(known_at) if known_at is not None else None,
        "generated_at": _utc_iso(generated_at),
        "authority": dict(AUTHORITY),
        "scope": {"delivered_from": scope_delivered_from, "delivered_through": scope_delivered_through},
        "coverage": coverage,
        "cases": cases,
        "limitations": [
            "estimated_notification_value is a proposed-sale estimate — never a contract "
            "award, backlog, or revenue figure; it is never summed across cases.",
            "Stage is congressional_notification only; later stages require new official "
            "first-party evidence and are never inferred from elapsed time.",
        ],
    }
    graph["content_id"] = fms_case_graph_content_id(graph)
    return graph
