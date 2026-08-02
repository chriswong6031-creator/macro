"""Point-in-time SAM.gov opportunity intelligence for Government Revenue.

The collector owns source acquisition and immutable first-seen evidence.  This
module is deliberately deterministic: it filters that evidence to the replay
clock, normalizes the latest visible revision, builds amendment events, and
adds transparent public-company *exposure candidates*.  Those candidates are
not bidder predictions and never receive signal authority.
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


SCHEMA_VERSION = "government_opportunity_intelligence.v1"
RECORD_CONTRACT = "government_opportunity.v1"
EVENT_CONTRACT = "government_opportunity_revision_event.v1"
SOURCE_URL = "https://api.sam.gov/opportunities/v2/search"
SAM_UI_BASE = "https://sam.gov/opp"
DEFAULT_FRESHNESS_SLA_MINUTES = 90
# A notice is *currently verified* only when this exact latest source state was
# observed inside the collector SLA.  The rolling SAM query deliberately keeps
# prior rows after they fall out of a later window, so a retained ``active``
# status by itself is not evidence that the notice remains open now.
CURRENT_STATE_VERIFICATION_SLA_MINUTES = DEFAULT_FRESHNESS_SLA_MINUTES
MAX_PUBLIC_OPPORTUNITIES = 500
MAX_COMPANY_CANDIDATES = 5

_TERMINAL_NOTICE_STATUSES = {"archived", "cancelled", "deleted", "inactive"}

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

_CURRENT_PATHS = (
    "opportunities.parquet",
    "opportunities.json",
    "opportunities.jsonl",
)
_REVISION_PATHS = (
    "opportunity_revisions.parquet",
    "opportunity_revisions.json",
    "opportunity_revisions.jsonl",
)
_DOCUMENT_PATHS = (
    "opportunity_documents.parquet",
    "opportunity_documents.json",
    "opportunity_documents.jsonl",
)

_NOTICE_STATUS = {
    "p": "presolicitation",
    "presolicitation": "presolicitation",
    "pre-solicitation": "presolicitation",
    "r": "sources_sought",
    "sources sought": "sources_sought",
    "sources_sought": "sources_sought",
    "o": "solicitation",
    "solicitation": "solicitation",
    "k": "combined",
    "combined synopsis/solicitation": "combined",
    "combined": "combined",
    "a": "award_notice",
    "award notice": "award_notice",
    "award_notice": "award_notice",
    "s": "special_notice",
    "special notice": "special_notice",
    "special_notice": "special_notice",
    "i": "intent_to_bundle",
    "g": "sale_of_surplus",
}
_OPEN_OPPORTUNITY_STAGES = {
    "presolicitation",
    "sources_sought",
    "solicitation",
    "combined",
    "intent_to_bundle",
}

_TAG_PATTERNS: dict[str, tuple[str, ...]] = {
    "drones": (" drone", "drones", " uav", " uas", "unmanned aircraft", "uncrewed"),
    "autonomy": ("autonomous", "autonomy", "robotic", "unmanned", "counter-uas", "c-uas"),
    "missiles": ("missile", "munition", "ordnance", "interceptor", "rocket motor", "air defense"),
    "hypersonics": ("hypersonic", "scramjet", "boost glide"),
    "space": ("satellite", "spacecraft", "space force", "launch vehicle", "orbital", "payload"),
    "shipbuilding": ("shipbuilding", "shipyard", "submarine", "destroyer", "frigate", "naval vessel"),
    "nuclear": ("nuclear", "reactor", "uranium", "radiological", "naval propulsion"),
    "cyber": ("cyber", "zero trust", "information assurance", "threat intelligence", "soc service"),
    "government-it": ("information technology", " it service", "software", "cloud", "digital modernization"),
    "ai": ("artificial intelligence", "machine learning", "generative ai", "computer vision"),
    "data-platforms": ("data platform", "data analytics", "data integration", "decision advantage"),
    "communications": ("communications", "satcom", "radio frequency", "tactical radio", "networking"),
    "sensors": ("sensor", "radar", "lidar", "electro-optical", "infrared", "electronic warfare"),
    "aerospace": ("aircraft", "aviation", "airframe", "flight test", "aeronautic"),
    "rotorcraft": ("helicopter", "rotorcraft", "vertical lift"),
    "defense-propulsion": ("propulsion", "turbine", "jet engine", "rocket engine"),
    "defense-components": ("spare parts", "repair parts", "sustainment", "depot maintenance", "components"),
}

_NAICS_TAGS: dict[str, tuple[str, ...]] = {
    "336411": ("aerospace", "drones"),
    "336412": ("aerospace", "defense-propulsion"),
    "336413": ("aerospace", "defense-components"),
    "336414": ("missiles", "space", "defense-propulsion"),
    "336415": ("missiles", "space"),
    "336611": ("shipbuilding",),
    "541330": ("defense", "government-it"),
    "541511": ("government-it", "data-platforms"),
    "541512": ("government-it", "cyber", "data-platforms"),
    "541519": ("government-it", "cyber"),
    "541715": ("defense", "ai", "space"),
}

_PSC_TAG_PREFIXES: dict[str, tuple[str, ...]] = {
    "14": ("missiles",),
    "15": ("aerospace", "drones"),
    "16": ("aerospace", "defense-components"),
    "18": ("space",),
    "19": ("shipbuilding",),
    "20": ("shipbuilding",),
    "58": ("communications", "sensors"),
    "59": ("communications", "sensors", "defense-components"),
    "D": ("government-it", "cyber", "data-platforms"),
    "AC": ("defense", "aerospace", "space"),
}

_DEFENSE_AGENCY_WORDS = (
    "department of defense",
    "dept of defense",
    "army",
    "navy",
    "marine corps",
    "air force",
    "space force",
    "missile defense",
    "defense logistics",
    "darpa",
)

_DIFF_FIELDS = (
    "title",
    "notice_type",
    "status",
    "response_deadline",
    "archive_date",
    "set_aside",
    "naics_code",
    "psc_code",
    "agency",
    "office",
    "description",
    "resource_links",
)


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return default


def _read_records(directory: Path, names: Iterable[str]) -> pd.DataFrame:
    for name in names:
        path = directory / name
        if not path.exists():
            continue
        try:
            if path.suffix == ".parquet":
                return pd.read_parquet(path)
            if path.suffix == ".jsonl":
                rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
                return pd.DataFrame(rows)
            raw = _read_json(path, [])
            if isinstance(raw, dict):
                raw = raw.get("records") or raw.get("opportunities") or raw.get("rows") or []
            return pd.DataFrame(raw if isinstance(raw, list) else [])
        except Exception:  # noqa: BLE001 - malformed optional input fails closed below
            return pd.DataFrame()
    return pd.DataFrame()


def _text(value: Any) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    value = str(value).strip()
    return value or None


def _first(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if _text(value) is not None:
            return value
    return None


def _timestamp(value: Any) -> pd.Timestamp | None:
    if _text(value) is None:
        return None
    try:
        out = pd.Timestamp(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if out.tzinfo is None:
        out = out.tz_localize("UTC")
    else:
        out = out.tz_convert("UTC")
    return out


def _iso(value: Any) -> str | None:
    stamp = _timestamp(value)
    return stamp.isoformat() if stamp is not None else None


def _as_of_cutoff(as_of: pd.Timestamp) -> pd.Timestamp | None:
    """Return the inclusive UTC end of an as-of day.

    The public builder accepts a date-style as-of clock.  Keeping the cutoff
    inclusive of that day avoids dropping a same-day official notice while
    still excluding a record whose effective date belongs to the next day.
    """
    stamp = _timestamp(as_of)
    if stamp is None:
        return None
    return stamp.normalize() + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)


def _date(value: Any) -> str | None:
    stamp = _timestamp(value)
    return stamp.date().isoformat() if stamp is not None else None


def _json_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, dict):
        return [value]
    text = _text(value)
    if text is None:
        return []
    try:
        parsed = json.loads(text)
    except ValueError:
        return [part.strip() for part in text.split("|") if part.strip()]
    if isinstance(parsed, list):
        return parsed
    return [parsed] if parsed is not None else []


def _json_object(value: Any) -> dict[str, Any] | str | None:
    if isinstance(value, dict):
        return value
    text = _text(value)
    if text is None:
        return None
    try:
        parsed = json.loads(text)
    except ValueError:
        return text
    return parsed if isinstance(parsed, dict) else text


def _canonical_hash(record: dict[str, Any]) -> str:
    body = {key: record.get(key) for key in _DIFF_FIELDS}
    raw = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _notice_status(notice_type: str | None, reported: str | None) -> str:
    status = (reported or "").strip().lower().replace("-", "_").replace(" ", "_")
    if status in {"active", "inactive", "archived", "cancelled", "deleted"}:
        return status
    raw = (notice_type or "").strip().lower()
    return _NOTICE_STATUS.get(raw, raw.replace(" ", "_") or "unknown")


def _notice_stage(notice_type: str | None) -> str:
    """Normalize what the notice *is*, separately from SAM rail activity."""
    raw = (notice_type or "").strip().lower()
    return _NOTICE_STATUS.get(raw, raw.replace("-", "_").replace(" ", "_") or "unknown")


def _is_open_opportunity(record: dict[str, Any]) -> bool:
    """True only for a non-terminal, actionable pre-award notice stage."""
    status = str(record.get("status") or "").strip().lower()
    stage = str(record.get("notice_stage") or "").strip().lower()
    return stage in _OPEN_OPPORTUNITY_STAGES and status not in _TERMINAL_NOTICE_STATUSES


def _source_url(notice_id: str, supplied: Any = None) -> str:
    url = _text(supplied)
    if url and url.startswith(("https://sam.gov/", "https://api.sam.gov/")):
        return url
    return f"{SAM_UI_BASE}/{notice_id}/view"


def _normalise_record(row: dict[str, Any]) -> dict[str, Any] | None:
    notice_id = _text(_first(row, "notice_id", "noticeId", "source_notice_id", "opportunity_id"))
    if not notice_id:
        return None
    notice_type = _text(_first(row, "notice_type", "type", "current_notice_type", "ptype"))
    known_at = _iso(_first(row, "known_at", "captured_at", "first_seen_at", "observed_at"))
    posted_at = _iso(_first(row, "posted_at", "postedDate", "posted_date", "effective_at"))
    resources = _json_list(_first(row, "resource_links", "resourceLinks", "documents"))
    resources = [item for item in resources if isinstance(item, (str, dict))][:40]
    record = {
        "contract": RECORD_CONTRACT,
        "notice_id": notice_id,
        "solicitation_number": _text(_first(row, "solicitation_number", "solicitationNumber")),
        "revision_id": _text(_first(row, "revision_id", "content_sha256", "revision_hash")),
        "title": _text(row.get("title")) or "Untitled opportunity",
        "description": (_text(_first(row, "description", "summary")) or "")[:4000] or None,
        "notice_type": notice_type,
        "notice_stage": _notice_stage(notice_type),
        "base_type": _text(_first(row, "base_type", "baseType", "base_notice_type")),
        "status": _notice_status(notice_type, _text(row.get("status"))),
        "agency": _text(_first(row, "agency", "department", "full_parent_path_name", "fullParentPathName")),
        "office": _text(_first(row, "office", "subtier", "subTier")),
        "organization_code": _text(_first(row, "organization_code", "full_parent_path_code", "fullParentPathCode")),
        "naics_code": _text(_first(row, "naics_code", "naicsCode", "naics")),
        "psc_code": _text(_first(row, "psc_code", "classificationCode", "ccode", "psc")),
        "set_aside": _text(_first(row, "set_aside", "typeOfSetAsideDescription", "typeOfSetAside")),
        "posted_at": posted_at,
        "response_deadline": _iso(_first(row, "response_deadline", "responseDeadLine", "responseDeadline")),
        "archive_date": _iso(_first(row, "archive_date", "archiveDate")),
        "place_of_performance": _json_object(_first(row, "place_of_performance", "placeOfPerformance")),
        "resource_links": resources,
        "known_at": known_at,
        "effective_at": _iso(_first(row, "effective_at", "posted_at", "postedDate")) or posted_at,
        "source_url": _source_url(notice_id, _first(row, "source_url", "uiLink", "sam_url")),
        # This is intentionally private to the projection builder.  It is a
        # mutable observation clock, not an official notice field and may be
        # later than a historical replay cutoff.  ``observation_horizon_at``
        # below is the only PIT-safe public rendering of it.
        "_last_seen_at": _iso(_first(row, "last_seen_at", "lastSeenAt")),
    }
    record["revision_id"] = record["revision_id"] or _canonical_hash(record)
    return record


def _visible_records(frame: pd.DataFrame, cutoff: pd.Timestamp, as_of: pd.Timestamp) -> list[dict[str, Any]]:
    effective_cutoff = _as_of_cutoff(as_of)
    if effective_cutoff is None:
        return []
    rows: list[dict[str, Any]] = []
    for raw in frame.to_dict(orient="records") if not frame.empty else []:
        record = _normalise_record(raw)
        if record is None:
            continue
        known = _timestamp(record.get("known_at"))
        effective = _timestamp(record.get("effective_at"))
        # A source row without an immutable first-observed clock cannot be
        # placed in a historical replay.  Do not let an incomplete legacy row
        # silently become knowledge available at every prior cutoff.
        if known is None or known > cutoff:
            continue
        # Opportunity revisions also need an official event clock.  Accept the
        # whole requested UTC day, but never the first instant of the next day.
        if effective is None or effective > effective_cutoff:
            continue
        rows.append(record)
    return rows


def _latest_by_notice(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for record in records:
        key = record["notice_id"]
        prior = latest.get(key)
        if prior is None:
            latest[key] = record
            continue
        record_clock = _timestamp(record.get("known_at")) or _timestamp(record.get("effective_at")) or pd.Timestamp.min.tz_localize("UTC")
        prior_clock = _timestamp(prior.get("known_at")) or _timestamp(prior.get("effective_at")) or pd.Timestamp.min.tz_localize("UTC")
        if record_clock >= prior_clock:
            latest[key] = record
    return list(latest.values())


def _point_in_time_reference(
    knowledge_cutoff: pd.Timestamp,
    freshness_reference: pd.Timestamp | None,
) -> pd.Timestamp:
    """Return the latest clock the projection is allowed to use.

    Historical replays use their supplied knowledge cutoff.  A live build has
    an end-of-day PIT cutoff but a wall-clock freshness reference; choosing the
    earlier of the two avoids leaking an observation that was only learned
    later today into a page generated earlier today.
    """
    reference = _timestamp(freshness_reference) if freshness_reference is not None else knowledge_cutoff
    if reference is None:
        return knowledge_cutoff
    return min(reference, knowledge_cutoff)


def _current_state_metadata(
    record: dict[str, Any],
    *,
    knowledge_cutoff: pd.Timestamp,
    verification_reference: pd.Timestamp,
) -> dict[str, Any]:
    """Classify exact-state evidence without treating a retained row as live.

    ``last_seen_at`` may be updated by a later quiet poll on the mutable
    current/revision ledger.  It can certify currentness only when it was known
    no later than the replay cutoff.  If it is future knowledge, fall back to
    the immutable ``known_at`` transition rather than clamping the future clock
    to the cutoff (which would fabricate a historical observation).
    """
    known = _timestamp(record.get("known_at"))
    last_seen = _timestamp(record.get("_last_seen_at"))
    observed_at: pd.Timestamp | None = None
    observation_basis: str | None = None
    if last_seen is not None and last_seen <= knowledge_cutoff:
        observed_at = last_seen
        observation_basis = "last_seen_at"
    elif known is not None and known <= knowledge_cutoff:
        observed_at = known
        observation_basis = "known_at"

    if observed_at is None:
        return {
            "current_state": "last_observed_only",
            "observation_horizon_at": None,
            "observation_age_minutes": None,
            "observation_basis": None,
            "current_state_reason": "no_point_in_time_observation",
        }
    if observed_at > verification_reference:
        # This only occurs when a live wall-clock reference precedes the
        # end-of-day replay cutoff.  Do not turn a future observation into
        # current evidence.
        return {
            "current_state": "last_observed_only",
            "observation_horizon_at": observed_at.isoformat(),
            "observation_age_minutes": None,
            "observation_basis": observation_basis,
            "current_state_reason": "observation_after_reference_clock",
        }
    age_minutes = max(0, int((verification_reference - observed_at).total_seconds() // 60))
    verified = age_minutes <= CURRENT_STATE_VERIFICATION_SLA_MINUTES
    return {
        "current_state": "verified_current" if verified else "last_observed_only",
        "observation_horizon_at": observed_at.isoformat(),
        "observation_age_minutes": age_minutes,
        "observation_basis": observation_basis,
        "current_state_reason": (
            "observed_within_current_state_sla"
            if verified
            else "observation_aged_out"
        ),
    }


def _public_record(record: dict[str, Any]) -> dict[str, Any]:
    """Drop projection-private clocks from a public record or event snapshot."""
    return {key: value for key, value in record.items() if not key.startswith("_")}


def _opportunity_tags(record: dict[str, Any]) -> set[str]:
    text = " " + " ".join(
        str(record.get(key) or "").lower()
        for key in ("title", "description", "agency", "office")
    )
    tags = {tag for tag, patterns in _TAG_PATTERNS.items() if any(pattern in text for pattern in patterns)}
    naics = str(record.get("naics_code") or "")[:6]
    tags.update(_NAICS_TAGS.get(naics, ()))
    psc = str(record.get("psc_code") or "").upper()
    for prefix, values in _PSC_TAG_PREFIXES.items():
        if psc.startswith(prefix):
            tags.update(values)
    if any(word in text for word in _DEFENSE_AGENCY_WORDS):
        tags.add("defense")
    return tags


def _company_history(company: dict[str, Any]) -> dict[str, set[str]]:
    awards = company.get("awards") if isinstance(company.get("awards"), list) else []
    agencies = {str(row.get("awarding_agency") or "").strip().casefold() for row in awards if row.get("awarding_agency")}
    naics = {str(row.get("naics") or "").strip()[:6] for row in awards if row.get("naics")}
    psc = {str(row.get("psc") or "").strip().upper() for row in awards if row.get("psc")}
    return {"agencies": agencies, "naics": naics, "psc": psc}


def _company_candidates(record: dict[str, Any], companies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tags = _opportunity_tags(record)
    text = " ".join(str(record.get(key) or "") for key in ("title", "description")).casefold()
    agency = str(record.get("agency") or "").strip().casefold()
    naics = str(record.get("naics_code") or "")[:6]
    psc = str(record.get("psc_code") or "").upper()
    candidates: list[tuple[float, dict[str, Any]]] = []
    for company in companies:
        reasons: list[dict[str, str]] = []
        score = 0.0
        aliases = [company.get("name"), company.get("ticker")]
        aliases.extend((company.get("entity_match") or {}).get("aliases") or [])
        aliases.extend([(company.get("entity_match") or {}).get("recipient_search_text")])
        direct = next((str(alias) for alias in aliases if alias and len(str(alias)) >= 4 and str(alias).casefold() in text), None)
        if direct:
            score += 5.0
            reasons.append({"kind": "named_in_notice", "detail": f"Notice text names {direct}"})

        company_tags = {str(tag) for tag in company.get("tags") or []}
        overlap = sorted(tags & company_tags)
        if overlap:
            score += min(2.4, 0.8 * len(overlap))
            reasons.append({"kind": "capability_tag", "detail": ", ".join(overlap[:4])})

        history = _company_history(company)
        if agency and agency in history["agencies"]:
            score += 1.4
            reasons.append({"kind": "agency_history", "detail": record.get("agency") or "same agency"})
        if naics and naics in history["naics"]:
            score += 1.6
            reasons.append({"kind": "naics_history", "detail": naics})
        if psc and any(p == psc or (len(psc) >= 2 and p.startswith(psc[:2])) for p in history["psc"]):
            score += 1.2
            reasons.append({"kind": "psc_history", "detail": psc})

        reason_classes = {reason["kind"] for reason in reasons}
        if not direct and (score < 2.6 or len(reason_classes) < 2):
            continue
        confidence = "probable" if (direct and len(reason_classes) >= 2) or (score >= 4.0 and len(reason_classes) >= 3) else "tentative"
        candidates.append((score, {
            "ticker": company.get("ticker"),
            "name": company.get("name"),
            "confidence_state": confidence,
            "evidence_strength": "high" if score >= 5.0 else "moderate",
            "match_reasons": reasons,
            "evidence_class": "rule_based_exposure_candidate",
            "label_limit": "not a bidder probability, award forecast, or revenue estimate",
            "authority": AUTHORITY.copy(),
        }))
    candidates.sort(key=lambda item: (-item[0], str(item[1].get("ticker") or "")))
    return [item[1] for item in candidates[:MAX_COMPANY_CANDIDATES]]


def _diff(prior: dict[str, Any], current: dict[str, Any]) -> list[str]:
    return [field for field in _DIFF_FIELDS if prior.get(field) != current.get(field)]


def _events(revisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in revisions:
        grouped[record["notice_id"]].append(record)
    events: list[dict[str, Any]] = []
    for notice_id, records in grouped.items():
        records.sort(key=lambda row: _timestamp(row.get("known_at")) or _timestamp(row.get("effective_at")) or pd.Timestamp.min.tz_localize("UTC"))
        prior: dict[str, Any] | None = None
        first_seen_at = records[0].get("known_at") or records[0].get("effective_at")
        for version, record in enumerate(records, start=1):
            changed = [] if prior is None else _diff(prior, record)
            changed_values = [
                {
                    "field": field,
                    "before": prior.get(field) if prior is not None else None,
                    "after": record.get(field),
                    "semantic": "official_source_field",
                    "source_ref": record.get("source_url"),
                }
                for field in changed
            ]
            event_type = "opportunity_posted" if prior is None else "amendment"
            if prior is not None and changed == ["response_deadline"]:
                event_type = "response_due_change"
            seed = f"{notice_id}|{record.get('revision_id')}|{event_type}"
            events.append({
                "contract": EVENT_CONTRACT,
                "event_id": "govopp-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16],
                "event_type": event_type,
                "version": version,
                "notice_id": notice_id,
                "revision_id": record.get("revision_id"),
                "title": record.get("title"),
                "known_at": record.get("known_at"),
                "effective_at": record.get("effective_at"),
                "first_seen_at": first_seen_at,
                "changed_fields": changed,
                "changed_values": changed_values,
                "record_snapshot": record.copy(),
                "source_refs": [record.get("source_url")],
                "evidence_class": "official_source_version",
                "confidence_state": "confirmed",
                "authority": AUTHORITY.copy(),
            })
            prior = record
    events.sort(key=lambda row: row.get("known_at") or row.get("effective_at") or "", reverse=True)
    return events


def _document_map(
    frame: pd.DataFrame,
    cutoff: pd.Timestamp,
    as_of: pd.Timestamp,
) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    effective_cutoff = _as_of_cutoff(as_of)
    if frame.empty or effective_cutoff is None:
        return out
    for row in frame.to_dict(orient="records"):
        notice_id = _text(_first(row, "notice_id", "noticeId", "source_notice_id"))
        known_at = _iso(_first(row, "known_at", "captured_at", "first_seen_at"))
        known_ts = _timestamp(known_at)
        published_at = _iso(_first(row, "published_at", "posted_at"))
        published_ts = _timestamp(published_at)
        if (
            not notice_id
            or known_ts is None
            or known_ts > cutoff
            or (published_ts is not None and published_ts > effective_cutoff)
        ):
            continue
        url = _text(_first(row, "source_url", "url", "resource_link"))
        if not url or not url.startswith(("https://sam.gov/", "https://api.sam.gov/")):
            continue
        out[notice_id].append({
            "document_key": _text(_first(row, "document_key", "url_sha256")),
            "title": _text(_first(row, "title", "name", "filename")),
            "source_url": url,
            "mime_type": _text(_first(row, "mime_type", "type")),
            "content_sha256": _text(_first(row, "content_sha256", "sha256")),
            "known_at": known_at,
            "published_at": published_at,
            "hash_basis": _text(row.get("hash_basis")),
            "fetch_status": _text(row.get("fetch_status")),
        })
    return out


def _document_change_events(
    frame: pd.DataFrame,
    cutoff: pd.Timestamp,
    as_of: pd.Timestamp,
) -> list[dict[str, Any]]:
    """Emit byte-change observations without calling them official amendments."""
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    effective_cutoff = _as_of_cutoff(as_of)
    if frame.empty or effective_cutoff is None:
        return []
    for row in frame.to_dict(orient="records"):
        notice_id = _text(_first(row, "notice_id", "noticeId", "source_notice_id"))
        known_at = _iso(_first(row, "known_at", "captured_at", "first_seen_at"))
        known_ts = _timestamp(known_at)
        source_url = _text(_first(row, "source_url", "url", "document_url", "resource_link"))
        content_hash = _text(_first(row, "content_sha256", "sha256"))
        hash_basis = _text(row.get("hash_basis"))
        document_key = _text(_first(row, "document_key", "url_sha256")) or source_url
        if (
            not notice_id
            or not document_key
            or not content_hash
            or hash_basis != "content"
            or known_ts is None
            or known_ts > cutoff
            # Document-byte revisions are observed facts rather than official
            # amendments, so their observation time is their PIT-effective
            # clock as well as their visibility clock.
            or known_ts > effective_cutoff
            or not source_url
            or not source_url.startswith(("https://sam.gov/", "https://api.sam.gov/"))
        ):
            continue
        grouped[(notice_id, document_key)].append({
            "notice_id": notice_id,
            "document_key": document_key,
            "title": _text(_first(row, "title", "name", "filename")) or "SAM.gov attachment",
            "source_url": source_url,
            "content_sha256": content_hash,
            "hash_basis": hash_basis,
            "known_at": known_at,
        })

    events: list[dict[str, Any]] = []
    for (notice_id, document_key), rows in grouped.items():
        rows.sort(key=lambda row: _timestamp(row.get("known_at")) or pd.Timestamp.min.tz_localize("UTC"))
        first_seen_at = rows[0]["known_at"]
        prior: dict[str, Any] | None = None
        version = 0
        for row in rows:
            if prior is not None and row["content_sha256"] == prior["content_sha256"]:
                continue
            version += 1
            if prior is not None:
                seed = f"{notice_id}|{document_key}|{row['content_sha256']}|document_changed"
                events.append({
                    "contract": EVENT_CONTRACT,
                    "event_id": "govopp-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16],
                    "event_type": "document_changed",
                    "version": version,
                    "notice_id": notice_id,
                    "revision_id": row["content_sha256"],
                    "title": row["title"],
                    "known_at": row["known_at"],
                    "effective_at": None,
                    "first_seen_at": first_seen_at,
                    "changed_fields": ["document_content"],
                    "changed_values": [{
                        "field": "document_content_sha256",
                        "before": prior["content_sha256"],
                        "after": row["content_sha256"],
                        "semantic": "observed_document_bytes",
                        "source_ref": row["source_url"],
                    }],
                    "source_refs": [row["source_url"]],
                    "evidence_class": "observed_document_revision",
                    "confidence_state": "confirmed_observation",
                    "authority": AUTHORITY.copy(),
                })
            prior = row
    events.sort(key=lambda row: row.get("known_at") or "", reverse=True)
    return events


def _freshness(status: dict[str, Any], records: list[dict[str, Any]], cutoff: pd.Timestamp) -> dict[str, Any]:
    observed = _iso(status.get("observed_at") or status.get("captured_at") or status.get("known_at"))
    if not observed:
        observed = max((record.get("known_at") for record in records if record.get("known_at")), default=None)
    observed_ts = _timestamp(observed)
    age_minutes = None
    if observed_ts is not None:
        age_minutes = max(0, int((cutoff - observed_ts).total_seconds() // 60))
    source_status = str(status.get("status") or "").lower()
    errors = int(status.get("error_count") or len(status.get("errors") or []))
    if not records:
        overall = source_status if source_status in {"blocked", "failed", "stale", "partial"} else "unavailable"
    elif source_status in {"blocked", "failed", "stale", "partial"}:
        # Last-good records remain inspectable, but a current source-health
        # failure must never be converted back to `ok` merely because rows exist.
        overall = source_status
    elif errors:
        overall = "partial"
    elif age_minutes is not None and age_minutes > DEFAULT_FRESHNESS_SLA_MINUTES:
        overall = "stale"
    else:
        overall = "ok"
    return {
        "status": overall,
        "observed_at": observed,
        "age_minutes": age_minutes,
        "freshness_sla_minutes": DEFAULT_FRESHNESS_SLA_MINUTES,
        "current_state_verification_sla_minutes": CURRENT_STATE_VERIFICATION_SLA_MINUTES,
        "error_count": errors,
        "records_visible": len(records),
        "source_status": source_status or None,
        "latest_active_version_only": True,
        "revision_history_basis": "first-seen snapshots collected by MastermindX",
    }


def build_opportunity_intelligence(
    root: Path,
    companies: list[dict[str, Any]],
    *,
    as_of: pd.Timestamp,
    knowledge_cutoff: pd.Timestamp,
    freshness_reference: pd.Timestamp | None = None,
) -> dict[str, Any]:
    """Build the bounded, display-tier opportunity and amendment projection."""
    directory = root / "data" / "government_revenue"
    current_frame = _read_records(directory, _CURRENT_PATHS)
    revision_frame = _read_records(directory, _REVISION_PATHS)
    document_frame = _read_records(directory, _DOCUMENT_PATHS)
    status = _read_json(directory / "opportunity_ingest_status.json", {})

    # A historical request is bounded by its declared knowledge cutoff.  A live
    # page additionally respects its actual wall-clock build reference instead
    # of treating the rest of the current UTC day as already known.
    state_reference = _point_in_time_reference(knowledge_cutoff, freshness_reference)
    current_visible = _visible_records(current_frame, state_reference, as_of)
    revisions_visible = _visible_records(revision_frame, state_reference, as_of)
    if not revisions_visible:
        revisions_visible = list(current_visible)
    # The latest-state file can contain a revision first observed after a replay
    # cutoff.  In that case it is filtered out, but older visible revisions must
    # still restore the notice instead of disappearing from history.
    current_all = _latest_by_notice(revisions_visible + current_visible)
    documents = _document_map(document_frame, state_reference, as_of)
    events = _events(revisions_visible) + _document_change_events(
        document_frame,
        state_reference,
        as_of,
    )
    events.sort(key=lambda row: row.get("known_at") or row.get("effective_at") or "", reverse=True)

    revision_timeline: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for revision in revisions_visible:
        revision_timeline[revision["notice_id"]].append(revision)
    for rows in revision_timeline.values():
        rows.sort(key=lambda row: _timestamp(row.get("known_at")) or pd.Timestamp.min.tz_localize("UTC"))
    for event in events:
        snapshot = event.get("record_snapshot")
        if not isinstance(snapshot, dict):
            event_clock = _timestamp(event.get("known_at"))
            eligible = [
                row for row in revision_timeline.get(str(event.get("notice_id")), [])
                if event_clock is None
                or _timestamp(row.get("known_at")) is None
                or _timestamp(row.get("known_at")) <= event_clock
            ]
            snapshot = eligible[-1].copy() if eligible else None
        if isinstance(snapshot, dict):
            # A revision's mutable last-seen clock can have been advanced by a
            # later quiet poll.  Event snapshots are historical evidence, so
            # never serialize that private clock into an earlier replay.
            snapshot = _public_record(snapshot)
            snapshot["tags"] = sorted(_opportunity_tags(snapshot))
            snapshot["company_candidates"] = _company_candidates(snapshot, companies)
            snapshot["authority"] = AUTHORITY.copy()
            event["record_snapshot"] = snapshot

    by_company: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in current_all:
        record.update(_current_state_metadata(
            record,
            knowledge_cutoff=state_reference,
            verification_reference=state_reference,
        ))
        record["tags"] = sorted(_opportunity_tags(record))
        record["company_candidates"] = _company_candidates(record, companies)
        record["documents"] = documents.get(record["notice_id"], [])[:20]
        deadline = _timestamp(record.get("response_deadline"))
        record["days_to_response"] = (
            int((deadline.normalize() - as_of.normalize()).days) if deadline is not None else None
        )
        record["defense_relevant"] = bool("defense" in record["tags"] or any(
            word in str(record.get("agency") or "").casefold() for word in _DEFENSE_AGENCY_WORDS
        ))
        record["authority"] = AUTHORITY.copy()
        # Retained rows remain useful last-observed evidence in the public
        # ledger, but they do not feed a company's current opportunity context
        # unless this exact source state was freshly verified.
        if record["current_state"] != "verified_current":
            continue
        if not _is_open_opportunity(record):
            continue
        for candidate in record["company_candidates"]:
            ticker = str(candidate.get("ticker") or "")
            if ticker:
                by_company[ticker].append({
                    "notice_id": record["notice_id"],
                    "title": record["title"],
                    "status": record["status"],
                    "notice_stage": record["notice_stage"],
                    "posted_at": record["posted_at"],
                    "known_at": record["known_at"],
                    "effective_at": record["effective_at"],
                    "response_deadline": record["response_deadline"],
                    "days_to_response": record["days_to_response"],
                    "agency": record["agency"],
                    "naics_code": record["naics_code"],
                    "psc_code": record["psc_code"],
                    "source_url": record["source_url"],
                    "match": candidate,
                    "authority": AUTHORITY.copy(),
                })

    for rows in by_company.values():
        rows.sort(key=lambda row: (
            row.get("days_to_response") is None or row.get("days_to_response", 10**9) < 0,
            abs(row.get("days_to_response") or 10**9),
            row.get("posted_at") or "",
        ))

    current_all.sort(key=lambda row: (
        row.get("current_state") != "verified_current",
        not row.get("defense_relevant"),
        row.get("days_to_response") is None or row.get("days_to_response", 10**9) < 0,
        abs(row.get("days_to_response") or 10**9),
        row.get("posted_at") or "",
    ))
    records_available_before_cap = len(current_all)
    records_truncated = records_available_before_cap > MAX_PUBLIC_OPPORTUNITIES
    current = current_all[:MAX_PUBLIC_OPPORTUNITIES]
    all_event_notice_ids = {record["notice_id"] for record in current_all}
    events_available_before_cap = [
        event for event in events if event.get("notice_id") in all_event_notice_ids
    ]
    event_notice_ids = {record["notice_id"] for record in current}
    events = [event for event in events_available_before_cap if event.get("notice_id") in event_notice_ids][:1000]
    now_day = as_of.normalize()
    verified_current = [
        record for record in current_all
        if record.get("current_state") == "verified_current"
    ]
    last_observed_only = [
        record for record in current_all
        if record.get("current_state") != "verified_current"
    ]
    verified_active = [
        record for record in verified_current
        if _is_open_opportunity(record)
    ]
    last_observed_active = [
        record for record in last_observed_only
        if _is_open_opportunity(record)
    ]
    deadlines_30d = sum(
        record.get("days_to_response") is not None and 0 <= record["days_to_response"] <= 30
        for record in verified_active
    )
    amendments_7d = sum(
        event.get("event_type") in {"amendment", "response_due_change"}
        and _timestamp(event.get("known_at")) is not None
        and _timestamp(event.get("known_at")) >= state_reference - pd.Timedelta(days=7)
        for event in events_available_before_cap
    )
    document_revisions_7d = sum(
        event.get("event_type") == "document_changed"
        and _timestamp(event.get("known_at")) is not None
        and _timestamp(event.get("known_at")) >= state_reference - pd.Timedelta(days=7)
        for event in events_available_before_cap
    )
    known_values = [record.get("known_at") for record in current_all if record.get("known_at")]
    known_at = max(known_values, default=None)
    fresh = _freshness(status, current_all, state_reference)
    public_current = [_public_record(record) for record in current]

    return {
        "schema_version": SCHEMA_VERSION,
        "record_contract": RECORD_CONTRACT,
        "event_contract": EVENT_CONTRACT,
        "as_of": now_day.date().isoformat(),
        "known_at": known_at,
        "authority": AUTHORITY.copy(),
        "freshness": fresh,
        "coverage": {
            # The list is deliberately bounded for the static/API product
            # surface.  These pre-cap counts prevent the 500-row UI ceiling
            # from masquerading as the entire configured SAM query universe.
            "records_available_before_cap": records_available_before_cap,
            "records_visible": len(current),
            "records_truncated": records_truncated,
            "max_public_records": MAX_PUBLIC_OPPORTUNITIES,
            "current_state_reference_at": state_reference.isoformat(),
            "verified_current_records_available_before_cap": len(verified_current),
            "last_observed_only_records_available_before_cap": len(last_observed_only),
            "verified_active_records_available_before_cap": len(verified_active),
            "last_observed_active_records_available_before_cap": len(last_observed_active),
            "revision_records_visible": len(revisions_visible),
            "documents_visible": sum(len(record.get("documents") or []) for record in current),
            "documents_available_before_cap": sum(
                len(record.get("documents") or []) for record in current_all
            ),
            "events_visible": len(events),
            "events_available_before_cap": len(events_available_before_cap),
            "records_with_company_candidates": sum(bool(record.get("company_candidates")) for record in current),
            "records_unresolved_to_company": sum(not record.get("company_candidates") for record in current),
            "collector_scope": status.get("scope") or "configured SAM.gov query universe",
            "api_limitation": "public search API exposes latest active version; revision history is first-seen from our collector",
        },
        "market": {
            "current_opportunities": records_available_before_cap,
            "verified_current_opportunities": len(verified_current),
            "last_observed_only_opportunities": len(last_observed_only),
            "active_opportunities": len(verified_active),
            "last_observed_active_opportunities": len(last_observed_active),
            "defense_relevant": sum(bool(record.get("defense_relevant")) for record in verified_current),
            "last_observed_defense_relevant": sum(
                bool(record.get("defense_relevant")) for record in last_observed_only
            ),
            "deadlines_30d": int(deadlines_30d),
            "amendments_7d": int(amendments_7d),
            "observed_document_revisions_7d": int(document_revisions_7d),
            "company_candidate_links": sum(
                len(record.get("company_candidates") or []) for record in verified_current
            ),
            "last_observed_company_candidate_links": sum(
                len(record.get("company_candidates") or []) for record in last_observed_only
            ),
        },
        "opportunities": public_current,
        "events": events,
        "company_context": {ticker: rows[:50] for ticker, rows in by_company.items()},
        "provenance": [{
            "contract": "vertical_provenance.v1",
            "dataset": "sam_gov_contract_opportunities",
            "publisher": "U.S. General Services Administration, SAM.gov",
            "source_url": SOURCE_URL,
            "known_at": known_at,
            "effective_through": now_day.date().isoformat(),
            "point_in_time": bool(revisions_visible),
            "limitations": [
                "API key required; absent credentials produce an explicit blocked state",
                "public search API provides the latest active source version",
                "retained active rows are labelled last-observed unless the exact state was recently re-observed",
                "company links are rule-based exposure candidates, not bidder probabilities",
                "opportunity value is unknown unless an official source reports it",
            ],
        }],
    }


__all__ = [
    "AUTHORITY",
    "EVENT_CONTRACT",
    "RECORD_CONTRACT",
    "SCHEMA_VERSION",
    "build_opportunity_intelligence",
]
