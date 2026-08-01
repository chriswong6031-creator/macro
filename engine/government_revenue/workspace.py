"""Backend-owned procurement workspace projection.

This module turns official opportunity revisions and deterministic award-expiry
watches into one UI-ready event grammar.  Display priority is auditable and is
explicitly not an investment rank.  No browser-side calculation is required.
"""
from __future__ import annotations

import hashlib
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any

import pandas as pd


SCHEMA_VERSION = "government_procurement_workspace.v1"
EVENT_CONTRACT = "government_procurement_event.v1"
PRIORITY_FORMULA = "govrev_display_priority.v1"
MAX_WORKSPACE_EVENTS = 500
_TERMINAL_OPPORTUNITY_STATES = {
    "cancelled", "archived", "closed", "deleted", "inactive",
}
_OPEN_OPPORTUNITY_STAGES = {
    "presolicitation", "sources_sought", "solicitation", "combined", "intent_to_bundle",
}
_NOTICE_STAGE_ALIASES = {
    "p": "presolicitation",
    "pre_solicitation": "presolicitation",
    "r": "sources_sought",
    "o": "solicitation",
    "k": "combined",
    "combined_synopsis/solicitation": "combined",
    "a": "award_notice",
    "s": "special_notice",
    "i": "intent_to_bundle",
    "g": "sale_of_surplus",
}

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


def _text(value: Any, limit: int = 400) -> str | None:
    if value is None:
        return None
    text = re.sub(r"<[^>]*>", " ", str(value))
    text = " ".join(text.split())
    return text[:limit] or None


def _stamp(value: Any) -> pd.Timestamp | None:
    if value is None:
        return None
    try:
        stamp = pd.Timestamp(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if pd.isna(stamp):
        return None
    return stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")


def _date(value: Any) -> str | None:
    stamp = _stamp(value)
    return stamp.date().isoformat() if stamp is not None else None


def _event_id(*parts: Any) -> str:
    raw = "|".join(str(part or "") for part in parts).encode("utf-8")
    return "govws-" + hashlib.sha256(raw).hexdigest()[:18]


def _changed_value(event: dict[str, Any], field: str) -> dict[str, Any] | None:
    return next(
        (
            row for row in event.get("changed_values") or []
            if isinstance(row, dict) and row.get("field") == field
        ),
        None,
    )


def _opportunity_change(event: dict[str, Any]) -> tuple[str, str, str]:
    kind = str(event.get("event_type") or "amendment")
    if kind == "document_changed":
        return (
            "document_changed",
            "Previously observed attachment bytes changed.",
            "此前观测到的附件内容发生变化。",
        )
    if kind == "opportunity_posted":
        return (
            "new_notice",
            "New official opportunity notice posted.",
            "新的官方采购机会公告已发布。",
        )
    due = _changed_value(event, "response_deadline")
    if due:
        before, after = _date(due.get("before")), _date(due.get("after"))
        if before and after:
            return (
                "deadline_changed",
                f"Response deadline changed from {before} to {after}.",
                f"响应截止日由 {before} 变更为 {after}。",
            )
    fields = [str(field).replace("_", " ") for field in event.get("changed_fields") or []]
    detail = ", ".join(fields[:3]) if fields else "notice details"
    return (
        "amendment",
        f"Official amendment changed {detail}.",
        "官方修订更新了公告字段。",
    )


def _opportunity_priority(event: dict[str, Any], impacts: list[dict[str, Any]]) -> dict[str, Any]:
    event_type = event.get("event_type")
    new_information = {
        "document_changed": 0.9,
        "response_due_change": 1.0,
        "amendment": 0.85,
        "opportunity_posted": 0.75,
    }.get(str(event_type), 0.6)
    confidence = {impact.get("confidence") for impact in impacts}
    company_materiality = 0.65 if "medium" in confidence else 0.35 if impacts else 0.0
    evidence_quality = 1.0
    score = round(100 * (0.45 * new_information + 0.30 * company_materiality + 0.25 * evidence_quality), 1)
    return {
        "score": score,
        "new_information": new_information,
        "company_materiality": company_materiality,
        "evidence_quality": evidence_quality,
        "formula_version": PRIORITY_FORMULA,
        "is_investment_rank": False,
        "tie_breakers": ["critical_date", "known_at", "event_id"],
    }


def _company_impacts(
    record: dict[str, Any],
    vertical_links_by_ticker: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    impacts: list[dict[str, Any]] = []
    for candidate in record.get("company_candidates") or []:
        if not isinstance(candidate, dict) or not candidate.get("ticker"):
            continue
        reasons = candidate.get("match_reasons") or []
        direct = any(
            isinstance(reason, dict) and reason.get("kind") == "named_in_notice"
            for reason in reasons
        )
        confidence = "medium" if candidate.get("confidence_state") == "probable" else "low"
        ticker = str(candidate.get("ticker"))
        impacts.append({
            "ticker": ticker,
            "company_name": candidate.get("name"),
            "legal_entity_id": None,
            "legal_entity_name": None,
            "role": "issuer_exposure_candidate",
            "relation_semantic": "deterministic_inference",
            "match_method": "name_alias" if direct else "capability_history_rule",
            "ownership_path": [],
            "confidence": confidence,
            "why_it_matters_en": (
                "The official notice names a mapped issuer alias."
                if direct else
                "Agency, category, and capability evidence overlap this issuer's covered history."
            ),
            "why_it_matters_zh": (
                "官方公告提及已映射的发行人别名。"
                if direct else
                "机构、品类及能力证据与该发行人的覆盖历史重合。"
            ),
            "stance": "watch_dont_chase" if confidence == "medium" else "stand_aside",
            "stance_scope": "research",
            "watch_next_en": "Watch for another amendment, an award notice, or verified entity linkage.",
            "watch_next_zh": "关注后续修订、授标公告或已核验实体关联。",
            "materiality": {
                "band": "unknown",
                "basis_code": "unavailable",
                "numerator_value": None,
                "denominator_value": None,
                "ratio_pct": None,
                "coverage_note": "No official notice value or audited issuer revenue denominator is available.",
            },
            "evidence_refs": [record.get("source_url")],
            "cross_desk_links": list(vertical_links_by_ticker.get(ticker) or []),
            "label_limit": "exposure candidate only; not a bidder, award, or revenue forecast",
        })
    return impacts


def _workspace_opportunity_state(
    event: dict[str, Any],
    record: dict[str, Any],
    current_record: dict[str, Any] | None,
) -> tuple[str, str, str, str | None, str | None, str, bool, bool, bool]:
    """Separate an event's historical source state from verified current state.

    Workspace events are a revision ledger, so an earlier source revision must
    never become a current open opportunity by default.  Only the latest
    source state, re-observed within the current-state SLA, may set the public
    ``open``/``active`` flags.  The source status remains present for forensic
    reading of the historical event.
    """
    def notice_stage(row: dict[str, Any] | None) -> str | None:
        if not isinstance(row, dict):
            return None
        explicit = _text(row.get("notice_stage"), 80)
        if explicit:
            return explicit
        raw = (_text(row.get("notice_type"), 80) or "").strip().lower()
        normalized = raw.replace("-", "_").replace(" ", "_")
        return _NOTICE_STAGE_ALIASES.get(normalized, normalized or None)

    source_status = _text(record.get("status"), 80) or "unknown"
    source_stage = notice_stage(record) or "unknown"
    current_status = (
        _text(current_record.get("status"), 80)
        if isinstance(current_record, dict)
        else None
    )
    current_stage = notice_stage(current_record)
    current_state = (
        _text(current_record.get("current_state"), 80)
        if isinstance(current_record, dict)
        else None
    ) or "last_observed_only"
    source_revision_id = _text(
        record.get("revision_id") or event.get("revision_id"),
        160,
    )
    current_revision_id = (
        _text(current_record.get("revision_id"), 160)
        if isinstance(current_record, dict)
        else None
    )
    # A source observation can verify only the exact latest revision.  An
    # older event may be useful history, but cannot inherit the current
    # record's active flag merely because it shares a notice id.
    is_current_revision = bool(
        source_revision_id
        and current_revision_id
        and source_revision_id == current_revision_id
    )
    current_state_verified = current_state == "verified_current" and is_current_revision
    is_verified_active = bool(
        current_state_verified
        and current_stage in _OPEN_OPPORTUNITY_STAGES
        and current_status not in _TERMINAL_OPPORTUNITY_STATES
    )

    if is_verified_active:
        state = "open"
    elif current_state_verified and current_status in _TERMINAL_OPPORTUNITY_STATES:
        # A freshly re-observed terminal state is safe to surface as current.
        state = current_status
    elif source_status in _TERMINAL_OPPORTUNITY_STATES:
        # Preserve a terminal state recorded by this historical event even
        # when there is no later current-state proof available.
        state = source_status
    else:
        # Non-actionable award/special notices remain typed in
        # ``opportunity.notice_stage`` but use the workspace's coarse updated
        # state. They are verified evidence, never an open bid.
        state = "updated"
    return (
        state,
        source_status,
        source_stage,
        current_status,
        current_stage,
        current_state,
        current_state_verified,
        is_verified_active,
        is_current_revision,
    )


def _opportunity_workspace_event(
    event: dict[str, Any],
    record: dict[str, Any],
    vertical_links_by_ticker: dict[str, list[dict[str, Any]]],
    current_record: dict[str, Any] | None = None,
) -> dict[str, Any]:
    change_type, change_en, change_zh = _opportunity_change(event)
    impacts = _company_impacts(record, vertical_links_by_ticker)
    known_at = event.get("known_at") or record.get("known_at")
    event_source = next(
        (value for value in event.get("source_refs") or [] if isinstance(value, str)),
        None,
    )
    notice_url = record.get("source_url")
    evidence_url = event_source or notice_url
    changed_fields = [
        {
            "field": row.get("field"),
            "before": row.get("before"),
            "after": row.get("after"),
            "semantic": (
                "observed_document_revision"
                if event.get("event_type") == "document_changed"
                else "official"
            ),
            "source_ref": row.get("source_ref") or evidence_url,
        }
        for row in event.get("changed_values") or []
        if isinstance(row, dict)
    ]
    dates = []
    for date_id, label, value in (
        ("response_deadline", "response_due", record.get("response_deadline")),
        ("posted_at", "posted", record.get("posted_at")),
        ("archive_date", "archive", record.get("archive_date")),
    ):
        if value:
            dates.append({
                "id": date_id,
                "label_code": label,
                "value": value,
                "semantic": "official_deadline" if date_id == "response_deadline" else "official_source_date",
                "known_at": known_at,
                "source_ref": notice_url,
            })
    receipt_kind = "document" if event.get("event_type") == "document_changed" else "notice"
    receipt_id = f"sam:{receipt_kind}:{record.get('notice_id')}:{event.get('revision_id') or record.get('revision_id')}"
    (
        state,
        source_status,
        source_stage,
        current_status,
        current_stage,
        current_state,
        current_state_verified,
        is_verified_active,
        is_current_revision,
    ) = _workspace_opportunity_state(
        event,
        record,
        current_record,
    )
    observed_current_state_reason = (
        _text(current_record.get("current_state_reason"), 160)
        if isinstance(current_record, dict)
        else None
    ) or "no_current_state_verification"
    if is_current_revision:
        current_state_reason = observed_current_state_reason
    elif (
        _text(record.get("revision_id") or event.get("revision_id"), 160)
        and isinstance(current_record, dict)
        and _text(current_record.get("revision_id"), 160)
    ):
        current_state_reason = "historical_revision_superseded"
    else:
        current_state_reason = "current_revision_not_verifiable"
    return {
        "contract": EVENT_CONTRACT,
        "event_id": event.get("event_id") or _event_id(record.get("notice_id"), event.get("revision_id")),
        "record_id": f"sam:{record.get('notice_id')}",
        "version": int(event.get("version") or 1),
        "kind": "opportunity",
        "state": state,
        "title_original": _text(record.get("title"), 240) or "Untitled opportunity",
        "title_zh": None,
        "translation_status": "original",
        "agency": {
            "department_id": record.get("organization_code"),
            "department_name": record.get("agency"),
            "subagency_id": None,
            "subagency_name": None,
            "office_id": None,
            "office_name": record.get("office"),
        },
        "change": {
            "type": change_type,
            "what_changed_en": change_en,
            "what_changed_zh": change_zh,
            "summary_origin": "deterministic_template",
            "effective_at": event.get("effective_at"),
            "known_at": known_at,
            "first_seen_at": event.get("first_seen_at") or known_at,
            "last_seen_at": known_at,
            "is_correction": False,
            "changed_fields": changed_fields,
        },
        "opportunity": {
            "notice_id": record.get("notice_id"),
            "solicitation_number": record.get("solicitation_number"),
            "notice_type": record.get("notice_type"),
            "notice_stage": source_stage,
            # ``source_status`` describes this historical revision.  Current
            # activity is a separate, fail-closed claim about the latest
            # re-observed source record.
            "source_status": source_status,
            "current_status": current_status,
            "current_notice_stage": current_stage,
            "current_revision": is_current_revision,
            "active": is_verified_active,
            "current_state": current_state if is_current_revision else "last_observed_only",
            "current_state_verified": current_state_verified,
            "observation_horizon_at": (
                current_record.get("observation_horizon_at")
                if isinstance(current_record, dict) and is_current_revision
                else None
            ),
            "observation_age_minutes": (
                current_record.get("observation_age_minutes")
                if isinstance(current_record, dict) and is_current_revision
                else None
            ),
            "observation_basis": (
                current_record.get("observation_basis")
                if isinstance(current_record, dict) and is_current_revision
                else None
            ),
            "current_state_reason": current_state_reason,
            "posted_at": record.get("posted_at"),
            "updated_at": known_at,
            "response_deadline": record.get("response_deadline"),
            "archive_at": record.get("archive_date"),
            "naics_codes": [record.get("naics_code")] if record.get("naics_code") else [],
            "psc_codes": [record.get("psc_code")] if record.get("psc_code") else [],
            "set_aside_code": None,
            "set_aside_label": record.get("set_aside"),
            "description_excerpt": _text(record.get("description"), 420),
            "place_of_performance": record.get("place_of_performance"),
            "sam_url": notice_url,
        },
        "recompete": None,
        "dates": dates,
        "amounts": [],
        "primary_date_id": "response_deadline" if record.get("response_deadline") else "posted_at",
        "primary_amount_id": None,
        "listed_company_impacts": impacts,
        "primary_ticker": impacts[0]["ticker"] if impacts else None,
        "display_priority": _opportunity_priority(event, impacts),
        "evidence": {
            "source_class": (
                "observed_source_revision"
                if event.get("event_type") == "document_changed"
                else "official_fact"
            ),
            "mapping_class": "deterministic_inference" if impacts else "unmapped",
            "receipts": [{
                "ref_id": receipt_id,
                "publisher": "SAM.gov",
                "record_id": record.get("notice_id"),
                "url": evidence_url,
                "effective_at": event.get("effective_at"),
                "known_at": known_at,
                "retrieved_at": known_at,
                "content_sha256": event.get("revision_id") or record.get("revision_id"),
            }],
            "derivations": ([{
                "ref_id": f"derived:issuer-link:{record.get('notice_id')}",
                "classification": "deterministic_inference",
                "formula_version": "govrev_exposure_candidate.v1",
                "basis_refs": [receipt_id],
                "known_at": known_at,
            }] if impacts else []),
            "conflicts": [],
            "limitations": [
                "Public SAM search exposes the latest active source version; amendment history is MastermindX first-seen history.",
                "Attachment byte changes are observed document revisions, not official SAM amendment timestamps.",
                "Issuer relationships are deterministic exposure candidates, not bidder probabilities.",
                "Opportunity value is not posted unless present in official source evidence.",
            ],
        },
        "authority": AUTHORITY.copy(),
    }


def _recompete_workspace_event(
    company: dict[str, Any],
    watch: dict[str, Any],
    *,
    known_at: str | None,
    vertical_links_by_ticker: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    ticker = str(company.get("ticker") or "")
    award_id = str(watch.get("award_id") or "unknown")
    award_identity = str(
        watch.get("generated_award_id")
        or watch.get("award_key")
        or f"piid:{award_id}"
    )
    end_date = watch.get("end_date")
    days = watch.get("days_to_end")
    obligated = watch.get("total_obligated")
    ttm = (company.get("metrics") or {}).get("ttm_obligations")
    ratio = None
    if isinstance(obligated, (int, float)) and isinstance(ttm, (int, float)) and ttm > 0:
        ratio = 100 * float(obligated) / float(ttm)
    materiality = 0.8 if ratio is not None and ratio >= 10 else 0.6 if ratio is not None and ratio >= 2 else 0.35
    priority = {
        "score": round(100 * (0.45 * 0.45 + 0.30 * materiality + 0.25 * 0.85), 1),
        "new_information": 0.45,
        "company_materiality": materiality,
        "evidence_quality": 0.85,
        "formula_version": PRIORITY_FORMULA,
        "is_investment_rank": False,
        "tie_breakers": ["critical_date", "known_at", "event_id"],
    }
    source_url = watch.get("source_url")
    receipt_id = f"usaspending:award:{award_identity}"
    event_id = _event_id("recompete", ticker, award_identity, end_date)
    return {
        "contract": EVENT_CONTRACT,
        "event_id": event_id,
        "record_id": f"award:{award_identity}",
        "version": 1,
        "kind": "recompete",
        "state": "watch",
        "title_original": _text(watch.get("description"), 240) or f"Award {award_id}",
        "title_zh": None,
        "translation_status": "original",
        "agency": {
            "department_id": None,
            "department_name": watch.get("awarding_agency"),
            "subagency_id": None,
            "subagency_name": None,
            "office_id": None,
            "office_name": None,
        },
        "change": {
            "type": "recompete_watch_entered",
            "what_changed_en": "Award entered a rule-based period-of-performance expiry watch window.",
            "what_changed_zh": "该授标进入基于履约结束日的到期观察窗口。",
            "summary_origin": "deterministic_template",
            "effective_at": watch.get("effective_at") or end_date,
            "known_at": watch.get("known_at") or known_at,
            "first_seen_at": watch.get("known_at") or known_at,
            "last_seen_at": watch.get("known_at") or known_at,
            "is_correction": False,
            "changed_fields": [],
        },
        "opportunity": None,
        "recompete": {
            "case_type": "derived_expiry_watch",
            "generated_award_id": watch.get("generated_award_id"),
            "piid": award_id,
            "incumbent_recipient_name": None,
            "incumbent_uei": None,
            "current_end_date": end_date,
            "potential_end_date": None,
            "days_to_current_end": days,
            "total_obligated": obligated,
            "current_award_amount": None,
            "potential_award_amount": None,
            "matched_notice_id": None,
            "basis_code": "pop_end_30_540d",
            "watch_entered_at": watch.get("known_at") or known_at,
        },
        "dates": [{
            "id": "current_end_date",
            "label_code": "period_of_performance_end",
            "value": end_date,
            "semantic": "official_pop_end",
            "known_at": watch.get("known_at") or known_at,
            "source_ref": source_url,
        }] if end_date else [],
        "amounts": ([{
            "id": "total_obligated",
            "label_code": "reported_obligations",
            "value": obligated,
            "currency": "USD",
            "semantic": "obligated",
            "as_of": _date(watch.get("effective_at")),
            "is_lower_bound": False,
            "source_ref": source_url,
        }] if isinstance(obligated, (int, float)) else []),
        "primary_date_id": "current_end_date" if end_date else None,
        "primary_amount_id": "total_obligated" if isinstance(obligated, (int, float)) else None,
        "listed_company_impacts": [{
            "ticker": ticker,
            "company_name": company.get("name"),
            "legal_entity_id": None,
            "legal_entity_name": None,
            "role": "mapped_award_exposure",
            "relation_semantic": "deterministic_inference",
            "match_method": (company.get("entity_match") or {}).get("method"),
            "ownership_path": [],
            "confidence": "medium" if (company.get("confidence") or {}).get("level") in {"high", "medium"} else "low",
            "why_it_matters_en": "A covered award is approaching its reported period-of-performance end.",
            "why_it_matters_zh": "覆盖范围内的授标正接近其报告的履约结束日。",
            "stance": "watch_dont_chase",
            "stance_scope": "research",
            "watch_next_en": "Watch for an official forecast, solicitation, extension, or follow-on award.",
            "watch_next_zh": "关注官方预测、招标、延期或后续授标。",
            "materiality": {
                "band": "high" if ratio is not None and ratio >= 10 else "medium" if ratio is not None and ratio >= 2 else "unknown",
                "basis_code": "amount_vs_gov_obligations" if ratio is not None else "unavailable",
                "numerator_value": obligated,
                "denominator_value": ttm,
                "ratio_pct": round(ratio, 2) if ratio is not None else None,
                "coverage_note": "Uses obligations in a bounded award sample; not contract value or issuer revenue.",
            },
            "evidence_refs": [source_url],
            "cross_desk_links": list(vertical_links_by_ticker.get(ticker) or []),
        }],
        "primary_ticker": ticker,
        "display_priority": priority,
        "evidence": {
            "source_class": "official_fact",
            "mapping_class": "deterministic_inference",
            "receipts": [{
                "ref_id": receipt_id,
                "publisher": "USAspending.gov",
                "record_id": award_id,
                "url": source_url,
                "effective_at": watch.get("effective_at"),
                "known_at": watch.get("known_at") or known_at,
                "retrieved_at": watch.get("known_at") or known_at,
                "content_sha256": None,
            }],
            "derivations": [{
                "ref_id": f"derived:expiry-watch:{ticker}:{award_id}",
                "classification": "deterministic_inference",
                "formula_version": "pop_end_30_540d.v1",
                "basis_refs": [receipt_id],
                "known_at": watch.get("known_at") or known_at,
            }],
            "conflicts": [],
            "limitations": [
                "This is a deterministic expiry watch, not an official recompete date or solicitation forecast.",
                "Recipient-to-issuer mapping remains bounded by the stated entity-match method.",
            ],
        },
        "authority": AUTHORITY.copy(),
    }


def _facets(events: list[dict[str, Any]]) -> dict[str, Any]:
    agencies = Counter(
        str((event.get("agency") or {}).get("department_name"))
        for event in events
        if (event.get("agency") or {}).get("department_name")
    )
    notice_types = Counter(
        str((event.get("opportunity") or {}).get("notice_type"))
        for event in events
        if (event.get("opportunity") or {}).get("notice_type")
    )
    tickers = Counter(
        str(event.get("primary_ticker")) for event in events if event.get("primary_ticker")
    )
    evidence_classes = Counter(
        str((event.get("evidence") or {}).get("mapping_class") or "unmapped")
        for event in events
    )
    impact_bands = Counter(
        str(((event.get("listed_company_impacts") or [{}])[0].get("materiality") or {}).get("band") or "unknown")
        for event in events
    )
    return {
        "agencies": [{"id": key, "label": key, "count": count} for key, count in agencies.most_common()],
        "notice_types": [{"id": key, "count": count} for key, count in notice_types.most_common()],
        "tickers": [{"id": key, "label": key, "count": count} for key, count in tickers.most_common()],
        "evidence_classes": [{"id": key, "count": count} for key, count in evidence_classes.most_common()],
        "impact_bands": [{"id": key, "count": count} for key, count in impact_bands.most_common()],
    }


def build_procurement_workspace(
    opportunity_intelligence: dict[str, Any],
    companies: list[dict[str, Any]],
    *,
    as_of: str,
    known_at: str | None,
    award_freshness: dict[str, Any] | None = None,
    vertical_links_by_ticker: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Compose a deterministic, UI-ready opportunity and recompete workspace."""
    current = {
        str(row.get("notice_id")): row
        for row in opportunity_intelligence.get("opportunities") or []
        if isinstance(row, dict) and row.get("notice_id")
    }
    vertical_links_by_ticker = vertical_links_by_ticker or {}
    events: list[dict[str, Any]] = []
    for event in opportunity_intelligence.get("events") or []:
        if not isinstance(event, dict):
            continue
        record = event.get("record_snapshot")
        if not isinstance(record, dict):
            record = current.get(str(event.get("notice_id")))
        if record:
            events.append(_opportunity_workspace_event(
                event,
                record,
                vertical_links_by_ticker,
                current.get(str(event.get("notice_id"))),
            ))
    for company in companies:
        if not isinstance(company, dict):
            continue
        for watch in company.get("recompete_candidates") or []:
            if isinstance(watch, dict):
                events.append(_recompete_workspace_event(
                    company,
                    watch,
                    known_at=known_at,
                    vertical_links_by_ticker=vertical_links_by_ticker,
                ))

    # Stable multi-pass sort keeps priority backend-owned while making newest
    # evidence and the stable event id explicit tie breakers.
    events.sort(key=lambda row: str(row.get("event_id") or ""))
    events.sort(key=lambda row: str((row.get("change") or {}).get("known_at") or ""), reverse=True)
    events.sort(
        key=lambda row: float((row.get("display_priority") or {}).get("score") or 0),
        reverse=True,
    )
    events_available_before_cap = len(events)
    events = events[:MAX_WORKSPACE_EVENTS]
    events_truncated = max(0, events_available_before_cap - len(events))
    mapped = sum(bool(event.get("listed_company_impacts")) for event in events)
    opportunity_freshness = opportunity_intelligence.get("freshness") or {}
    award_freshness = award_freshness or {}
    statuses = {opportunity_freshness.get("status"), award_freshness.get("status")}
    overall = "partial" if statuses & {"partial", "stale", "failed", "blocked", "unavailable"} else "ok"
    return {
        "schema_version": SCHEMA_VERSION,
        "event_contract": EVENT_CONTRACT,
        "as_of": as_of,
        "known_at": known_at,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "authority": AUTHORITY.copy(),
        "freshness": {
            "status": overall,
            "opportunities": opportunity_freshness,
            "recompetes": award_freshness,
            "mappings": {
                "status": "partial" if mapped < len(events) else "ok",
                "reviewed_at": None,
                "linked_records": mapped,
                "unmapped_records": len(events) - mapped,
                "conflicted_records": 0,
            },
        },
        "coverage": {
            "events_visible": len(events),
            "events_available_before_cap": events_available_before_cap,
            "events_truncated": events_truncated,
            "event_cap": MAX_WORKSPACE_EVENTS,
            "facet_scope": "visible bounded workspace events",
            "open_opportunities": int(
                (opportunity_intelligence.get("market") or {}).get("active_opportunities") or 0
            ),
            "opportunity_events_visible": sum(
                event.get("kind") == "opportunity" for event in events
            ),
            "recompete_cases": sum(event.get("kind") == "recompete" for event in events),
            "official_recompete_matches": 0,
            "derived_expiry_watches": sum(event.get("kind") == "recompete" for event in events),
            "listed_company_linked": mapped,
            "unmapped": len(events) - mapped,
            "conflicted": 0,
        },
        "facets": _facets(events),
        "events": events,
        "next_cursor": None,
        "total": len(events),
        "display_sort": {
            "formula_version": PRIORITY_FORMULA,
            "formula": "45% new information + 30% company materiality + 25% evidence quality",
            "is_investment_rank": False,
        },
        "federation_contract": "vertical_link.v1",
        "limitations": [
            "First-seen revision history is not an official complete SAM amendment archive.",
            "Listed-company relationships are rule-based exposure candidates unless separately reviewed.",
            "Expiry watches are deterministic inferences, never official recompete dates.",
            "Workspace events and facets are capped; coverage discloses any records omitted by that cap.",
        ],
    }


__all__ = [
    "AUTHORITY",
    "EVENT_CONTRACT",
    "PRIORITY_FORMULA",
    "SCHEMA_VERSION",
    "build_procurement_workspace",
]
