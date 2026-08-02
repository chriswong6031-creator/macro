"""Bounded, read-only award dossiers for Government Revenue Foresight.

The module is deliberately a build-time projection.  It reads the bounded
USAspending award and action rails, emits one strict public artifact, and has
no API, network, ranking, prediction, ownership, or portfolio side effects.
In particular, a collector ticker is only a *discovery collection scope* here:
it cannot become recipient-to-issuer attribution without the separate exact-ID
entity-resolution workflow.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections import defaultdict
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import pandas as pd


DOSSIER_CONTRACT = "government_revenue_dossiers.v1"
DOSSIER_SCHEMA_VERSION = "1.0.0"
DOSSIER_FILENAME = "dossiers.json"
MAX_AWARD_RECORDS = 5_000
MAX_ACTION_RECORDS = 50_000
CONTENT_ID_PREFIX = "grd1-"

SPENDING_BY_AWARD_URL = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
TRANSACTIONS_URL = "https://api.usaspending.gov/api/v2/transactions/"
_ALLOWED_SOURCE_HOSTS = {
    "api.usaspending.gov",
    "usaspending.gov",
    "www.usaspending.gov",
}
_SENSITIVE_QUERY_KEY = re.compile(
    r"(?:api[_-]?key|authorization|secret|token|password|credential)", re.IGNORECASE
)
_TICKER = re.compile(r"^[A-Z][A-Z0-9.-]{0,9}$")
_TAG = re.compile(r"<[^>]*>")
_SAFE_AWARD_KEY_COMPONENT = re.compile(r"^[A-Za-z0-9._+-]{1,400}$")

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

COLLECTION_SCOPE_STATEMENT = (
    "Curated discovery-query membership is collection scope only and is not "
    "recipient-to-issuer attribution."
)
ISSUER_LIMITATION = (
    "No discovery ticker, company name, or fuzzy recipient name is used as issuer proof in this artifact."
)
AWARD_LIMITATION = (
    "Award values are official stored fields with distinct semantics: obligated amount, current award value, and potential ceiling are not interchangeable."
)
ACTION_LIMITATION = (
    "Actions are official transaction observations and may later be revised or deobligated."
)


def _root(root: Path | None) -> Path:
    return Path(root).resolve() if root is not None else Path.cwd().resolve()


def _clean_text(value: Any, *, limit: int = 4_000) -> str | None:
    """Normalize source text without letting untrusted markup cross the boundary."""
    if value is None:
        return None
    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass
    text = _TAG.sub(" ", str(value))
    text = " ".join(text.split())
    return text[:limit] or None


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _timestamp(value: Any) -> pd.Timestamp | None:
    if value is None:
        return None
    try:
        parsed = pd.Timestamp(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if pd.isna(parsed):
        return None
    return parsed.tz_localize("UTC") if parsed.tzinfo is None else parsed.tz_convert("UTC")


def _date(value: Any) -> str | None:
    parsed = _timestamp(value)
    return parsed.date().isoformat() if parsed is not None else None


def _instant(value: Any) -> str | None:
    parsed = _timestamp(value)
    return parsed.isoformat() if parsed is not None else None


def _latest_instant(values: Iterable[Any]) -> str | None:
    parsed = [stamp for stamp in (_timestamp(value) for value in values) if stamp is not None]
    return max(parsed).isoformat() if parsed else None


def _public_url(value: Any) -> str | None:
    """Keep only an official HTTPS URL and remove credential-shaped parameters."""
    text = _clean_text(value, limit=1_000)
    if text is None:
        return None
    try:
        parsed = urlsplit(text)
    except ValueError:
        return None
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.hostname.lower() not in _ALLOWED_SOURCE_HOSTS
        or parsed.username
        or parsed.password
    ):
        return None
    try:
        port = parsed.port
    except ValueError:
        return None
    hostname = parsed.hostname.lower()
    host = f"{hostname}:{port}" if port else hostname
    query = urlencode([
        (key, item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        if not _SENSITIVE_QUERY_KEY.search(key)
    ])
    return urlunsplit(("https", host, parsed.path, query, parsed.fragment))


def _award_page_url(generated_award_id: str | None, supplied: Any) -> str | None:
    supplied_url = _public_url(supplied)
    if supplied_url is not None:
        return supplied_url
    if generated_award_id:
        return f"https://www.usaspending.gov/award/{generated_award_id}/"
    return None


def _detail_url(generated_award_id: str | None, supplied: Any) -> str | None:
    supplied_url = _public_url(supplied)
    if supplied_url is not None:
        return supplied_url
    if generated_award_id:
        return f"https://api.usaspending.gov/api/v2/awards/{generated_award_id}/"
    return None


def _first_text(row: Mapping[str, Any], names: Iterable[str], *, limit: int = 4_000) -> str | None:
    for name in names:
        result = _clean_text(row.get(name), limit=limit)
        if result is not None:
            return result
    return None


def _first_date(row: Mapping[str, Any], names: Iterable[str]) -> str | None:
    for name in names:
        result = _date(row.get(name))
        if result is not None:
            return result
    return None


def _first_instant(row: Mapping[str, Any], names: Iterable[str]) -> str | None:
    for name in names:
        result = _instant(row.get(name))
        if result is not None:
            return result
    return None


def _ticker(value: Any) -> str | None:
    text = _clean_text(value, limit=16)
    if text is None:
        return None
    normalized = text.upper()
    return normalized if _TICKER.fullmatch(normalized) else None


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def dossier_content_id(payload: Mapping[str, Any]) -> str | None:
    """Return a content ID that ignores the assembly clock, never a mutable label."""
    try:
        fingerprint = {
            str(key): value
            for key, value in payload.items()
            if key not in {"content_id", "generated_at"}
        }
        digest = hashlib.sha256(_canonical_json(fingerprint).encode("utf-8")).hexdigest()
    except (TypeError, ValueError):
        return None
    return CONTENT_ID_PREFIX + digest[:24]


def _collection_scope() -> dict[str, str]:
    return {
        "association_type": "discovery_collection_scope",
        "issuer_attribution": "not_asserted",
        "statement": COLLECTION_SCOPE_STATEMENT,
    }


def _award_key_component(value: str) -> str:
    """Keep a path-safe key while retaining the unmodified source ID separately."""
    return value if _SAFE_AWARD_KEY_COMPONENT.fullmatch(value) else hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()[:32]


def _identity(row: Mapping[str, Any]) -> tuple[str, dict[str, str | None]] | None:
    """Generate an award identity without ever collapsing generated IDs to PIID.

    A generated USAspending ID is source-native and always wins.  If it is
    unavailable, a non-PIID source key is next.  Last-resort PIID identities
    include only official record fields as a scope discriminator, explicitly
    avoiding a ticker/name-derived identity.
    """
    generated = _first_text(row, ("generated_unique_award_id", "generated_award_id"), limit=400)
    piid = _first_text(row, ("award_id", "piid"), limit=400)
    if generated:
        return (
            f"generated:{_award_key_component(generated)}",
            {
                "kind": "generated_award_id", "generated_award_id": generated,
                "source_award_key": None, "piid": piid,
            },
        )
    supplied = _first_text(row, ("award_key", "source_award_key"), limit=400)
    if supplied and not supplied.lower().startswith("piid:"):
        return (
            f"source:{_award_key_component(supplied)}",
            {
                "kind": "source_award_key", "generated_award_id": None,
                "source_award_key": supplied, "piid": piid,
            },
        )
    if not piid:
        return None
    discriminator = {
        "piid": piid,
        "recipient_uei": _first_text(row, ("recipient_uei", "uei"), limit=160),
        "award_type": _first_text(row, ("award_type",), limit=400),
        "start_date": _first_date(row, ("start_date", "period_of_performance_start_date")),
        "awarding_agency": _first_text(row, ("awarding_agency",), limit=400),
        "source_url": _public_url(row.get("source_url")),
    }
    digest = hashlib.sha256(_canonical_json(discriminator).encode("utf-8")).hexdigest()[:20]
    return (
        f"piid:{_award_key_component(piid)}|official:{digest}",
        {
            "kind": "piid_scoped_official_fields", "generated_award_id": None,
            "source_award_key": None, "piid": piid,
        },
    )


def _award_record(row: Mapping[str, Any]) -> dict[str, Any] | None:
    identity = _identity(row)
    known_at = _first_instant(row, ("known_at", "first_seen_at", "_first_seen"))
    if identity is None or known_at is None:
        return None
    award_key, identity_data = identity
    generated = identity_data["generated_award_id"]
    effective_at = _first_date(
        row,
        ("effective_at", "last_modified_date", "base_obligation_date", "start_date"),
    )
    return {
        "award_key": award_key,
        "identity": identity_data,
        "record_origin": "award_record",
        "collection_scope_tickers": [ticker] if (ticker := _ticker(row.get("ticker"))) else [],
        "recipient": {
            "name": _first_text(row, ("recipient_name",), limit=1_000),
            "uei": _first_text(row, ("recipient_uei", "uei"), limit=160),
        },
        "description": _first_text(row, ("description",), limit=4_000),
        "agency": {
            "awarding": _first_text(row, ("awarding_agency",), limit=1_000),
            "awarding_subagency": _first_text(row, ("awarding_sub_agency",), limit=1_000),
            "funding": _first_text(row, ("funding_agency",), limit=1_000),
            "funding_subagency": _first_text(row, ("funding_sub_agency",), limit=1_000),
        },
        "classifications": {
            "award_type": _first_text(row, ("award_type",), limit=400),
            "naics": _first_text(row, ("naics",), limit=80),
            "psc": _first_text(row, ("psc",), limit=80),
            "program": _first_text(
                row,
                ("program", "major_program", "program_acronym", "dod_acquisition_program", "dod_claimant_program"),
                limit=1_000,
            ),
        },
        "dates": {
            "base_obligation_date": _first_date(row, ("base_obligation_date",)),
            "start_date": _first_date(row, ("start_date", "period_of_performance_start_date")),
            "end_date": _first_date(row, ("end_date", "period_of_performance_current_end_date")),
            "last_modified_date": _first_date(row, ("last_modified_date",)),
            "effective_at": effective_at,
            "known_at": known_at,
            "first_seen_at": _first_instant(row, ("first_seen_at", "known_at")),
            "last_seen_at": _first_instant(row, ("last_seen_at", "known_at")),
        },
        "values": {
            "obligated": _number(row.get("total_obligated", row.get("award_amount"))),
            "current_award_value": _number(row.get("current_award_amount")),
            "ceiling": _number(row.get("potential_award_amount")),
            "total_outlays": _number(row.get("total_outlays")),
            "currency": "USD",
        },
        "source": {
            "publisher": "USAspending.gov",
            "award_search_url": SPENDING_BY_AWARD_URL,
            "award_detail_url": _detail_url(generated, row.get("detail_source_url")),
            "award_page_url": _award_page_url(generated, row.get("award_page_url")),
            "action_history_url": TRANSACTIONS_URL,
        },
        "provenance": {
            "source_record_count": 1,
            "effective_at": effective_at,
            "known_at": known_at,
            "limitations": [AWARD_LIMITATION, ISSUER_LIMITATION],
        },
        "action_keys": [],
        "action_count": 0,
    }


def _action_record(row: Mapping[str, Any]) -> dict[str, Any] | None:
    identity = _identity(row)
    synthetic_flag = _clean_text(row.get("action_id_synthetic"), limit=16)
    native_flag = _clean_text(row.get("source_action_id_native"), limit=16)
    if synthetic_flag and synthetic_flag.casefold() in {"true", "1", "yes"}:
        return None
    if native_flag and native_flag.casefold() not in {"true", "1", "yes"}:
        return None
    action_id = _first_text(
        row,
        ("action_id", "action_uid", "transaction_id", "transaction_unique_id", "award_transaction_id"),
        limit=400,
    )
    known_at = _first_instant(row, ("known_at", "first_seen_at", "_first_seen"))
    if identity is None or action_id is None or known_at is None:
        return None
    award_key, _ = identity
    action_key = f"action:{award_key}:{action_id}"
    effective_at = _first_date(row, ("effective_at", "action_date"))
    generated = _first_text(row, ("generated_unique_award_id", "generated_award_id"), limit=400)
    return {
        "action_key": action_key,
        "action_id": action_id,
        "award_key": award_key,
        "modification_number": _first_text(row, ("modification_number",), limit=400),
        "action_type": _first_text(row, ("action_type",), limit=160),
        "action_type_description": _first_text(row, ("action_type_description",), limit=1_000),
        "description": _first_text(row, ("description", "action_description"), limit=4_000),
        "action_date": _first_date(row, ("action_date",)),
        "effective_at": effective_at,
        "known_at": known_at,
        "first_seen_at": _first_instant(row, ("first_seen_at", "known_at")),
        "obligation": _number(
            row.get("federal_action_obligation", row.get("action_obligation", row.get("obligation_amount")))
        ),
        "source": {
            "publisher": "USAspending.gov",
            "transaction_url": _public_url(row.get("source_url")) or TRANSACTIONS_URL,
            "award_page_url": _award_page_url(generated, row.get("award_page_url")),
            "native_action_id": True,
        },
    }


def _stub_award_from_action(action: Mapping[str, Any], raw: Mapping[str, Any]) -> dict[str, Any] | None:
    """Retain an action with a stable award identity if its detail row is absent."""
    identity = _identity(raw)
    if identity is None:
        return None
    award_key, identity_data = identity
    known_at = action.get("known_at")
    if not isinstance(known_at, str):
        return None
    generated = identity_data["generated_award_id"]
    effective_at = action.get("effective_at")
    return {
        "award_key": award_key,
        "identity": identity_data,
        "record_origin": "action_seeded_stub",
        "collection_scope_tickers": [ticker] if (ticker := _ticker(raw.get("ticker"))) else [],
        "recipient": {"name": _first_text(raw, ("recipient_name",), limit=1_000), "uei": None},
        "description": action.get("description"),
        "agency": {"awarding": _first_text(raw, ("awarding_agency",), limit=1_000), "awarding_subagency": None, "funding": None, "funding_subagency": None},
        "classifications": {"award_type": None, "naics": None, "psc": None, "program": None},
        "dates": {
            "base_obligation_date": None, "start_date": None, "end_date": None,
            "last_modified_date": None, "effective_at": effective_at, "known_at": known_at,
            "first_seen_at": action.get("first_seen_at"), "last_seen_at": known_at,
        },
        "values": {"obligated": None, "current_award_value": None, "ceiling": None, "total_outlays": None, "currency": "USD"},
        "source": {
            "publisher": "USAspending.gov", "award_search_url": SPENDING_BY_AWARD_URL,
            "award_detail_url": _detail_url(generated, None),
            "award_page_url": _award_page_url(generated, raw.get("award_page_url")),
            "action_history_url": TRANSACTIONS_URL,
        },
        "provenance": {
            "source_record_count": 1, "effective_at": effective_at, "known_at": known_at,
            "limitations": ["Award detail was unavailable; this record is a bounded action-seeded stub.", ACTION_LIMITATION, ISSUER_LIMITATION],
        },
        "action_keys": [],
        "action_count": 0,
    }


def _read_frame(path: Path) -> tuple[pd.DataFrame, str]:
    if not path.exists():
        return pd.DataFrame(), "unavailable"
    try:
        return pd.read_parquet(path), "ok"
    except Exception:  # noqa: BLE001 - malformed source must degrade explicitly, never leak through
        return pd.DataFrame(), "failed"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


def _entity_names(root: Path) -> dict[str, str]:
    raw = _read_json(root / "data" / "government_revenue" / "entities.json")
    entities = raw.get("entities") if isinstance(raw.get("entities"), dict) else {}
    names: dict[str, str] = {}
    for raw_ticker, entity in entities.items():
        ticker = _ticker(raw_ticker)
        if ticker is None:
            continue
        name = _clean_text(entity.get("name") if isinstance(entity, Mapping) else None, limit=300)
        names[ticker] = name or ticker
    return names


def _status(*statuses: str) -> str:
    present = set(statuses)
    if "failed" in present:
        return "failed"
    if present == {"unavailable"}:
        return "unavailable"
    if "unavailable" in present or "partial" in present:
        return "partial"
    return "ok"


def _rail(
    *,
    state: str,
    loaded: int,
    published: int,
    cap: int,
    bounded_collection: bool | None,
    reason: str,
) -> dict[str, Any]:
    return {
        "status": state,
        "records_loaded": loaded,
        "records_published": published,
        "records_dropped": max(loaded - published, 0),
        "configured_cap": cap,
        "truncated_by_artifact_cap": loaded > cap,
        "bounded_collection": bounded_collection,
        "reason": reason,
    }


def _merge_awards(rows: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], int]:
    """Merge only identical source identities, preserving discovery scopes separately."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["award_key"]].append(row)
    output: dict[str, dict[str, Any]] = {}
    rejected = 0
    for award_key, candidates in grouped.items():
        # Award detail output is a latest-state source rail.  Latest known-at
        # resolves duplicate discovery-query observations, while every input
        # tick remains visible only as collection scope.
        candidates.sort(key=lambda row: (str(row["dates"]["known_at"] or ""), _canonical_json(row)), reverse=True)
        chosen = candidates[0]
        scopes = sorted({ticker for row in candidates for ticker in row["collection_scope_tickers"]})
        chosen["collection_scope_tickers"] = scopes
        chosen["provenance"] = {
            **chosen["provenance"],
            "source_record_count": len(candidates),
        }
        # Duplicate source rows are not independently attributed records.
        # Still reject a malformed canonical row rather than serializing it.
        try:
            _canonical_json(chosen)
        except (TypeError, ValueError):
            rejected += len(candidates)
            continue
        output[award_key] = chosen
    return output, rejected


def _merge_actions(rows: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], int]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["action_key"]].append(row)
    output: dict[str, dict[str, Any]] = {}
    rejected = 0
    for action_key, candidates in grouped.items():
        candidates.sort(key=lambda row: (str(row["known_at"] or ""), _canonical_json(row)), reverse=True)
        chosen = candidates[0]
        try:
            _canonical_json(chosen)
        except (TypeError, ValueError):
            rejected += len(candidates)
            continue
        output[action_key] = chosen
    return output, rejected


def _limit_records(
    records: Mapping[str, Any],
    limit: int,
    *,
    sort_key: Any,
) -> dict[str, Any]:
    ordered = sorted(records.items(), key=lambda item: sort_key(item[1]), reverse=True)
    return dict(ordered[:limit])


def build_dossier_payload(root: Path | None = None, *, as_of: str | None = None) -> dict[str, Any]:
    """Build the separate, bounded dossier artifact from stored official rails.

    Nothing in the returned artifact is calculated by a request handler.  The
    only joins are source-identity joins and collection-scope indexes required
    to navigate already-stored award/action observations.
    """
    repo = _root(root)
    data_dir = repo / "data" / "government_revenue"
    awards_frame, awards_state = _read_frame(data_dir / "awards.parquet")
    actions_frame, actions_state = _read_frame(data_dir / "award_actions.parquet")
    ingest = _read_json(data_dir / "ingest_status.json")
    bounded = ingest.get("bounded") if isinstance(ingest.get("bounded"), bool) else None
    observed_at = _instant(ingest.get("observed_at"))
    entity_names = _entity_names(repo)

    award_rows: list[dict[str, Any]] = []
    award_dropped = 0
    for raw in awards_frame.to_dict(orient="records") if not awards_frame.empty else []:
        row = _award_record(raw)
        if row is None:
            award_dropped += 1
        else:
            award_rows.append(row)
    awards_by_key, award_merge_rejected = _merge_awards(award_rows)
    award_dropped += award_merge_rejected

    action_rows: list[dict[str, Any]] = []
    action_raw_by_key: dict[str, Mapping[str, Any]] = {}
    action_dropped = 0
    for raw in actions_frame.to_dict(orient="records") if not actions_frame.empty else []:
        row = _action_record(raw)
        if row is None:
            action_dropped += 1
        else:
            action_rows.append(row)
            action_raw_by_key.setdefault(row["action_key"], raw)
    actions_by_key, action_merge_rejected = _merge_actions(action_rows)
    action_dropped += action_merge_rejected

    # Actions have an independent official rail. Preserve a stable action only
    # when its award detail row is absent by emitting a deliberately limited
    # stub, never by guessing a recipient/issuer linkage.
    for action_key, action in actions_by_key.items():
        award_key = action["award_key"]
        if award_key not in awards_by_key:
            stub = _stub_award_from_action(action, action_raw_by_key[action_key])
            if stub is not None:
                awards_by_key[award_key] = stub
            else:
                action_dropped += 1
    actions_by_key = {
        action_key: action
        for action_key, action in actions_by_key.items()
        if action["award_key"] in awards_by_key
    }

    awards_before_cap = len(awards_by_key)
    awards_by_key = _limit_records(
        awards_by_key,
        MAX_AWARD_RECORDS,
        sort_key=lambda row: (str(row["dates"]["known_at"] or ""), row["award_key"]),
    )
    actions_before_cap = len(actions_by_key)
    actions_by_key = _limit_records(
        actions_by_key,
        MAX_ACTION_RECORDS,
        sort_key=lambda row: (str(row["known_at"] or ""), row["action_key"]),
    )
    # If a record cap excluded an action's award, suppress the orphan action;
    # this is explicit coverage degradation rather than an implicit join.
    actions_by_key = {
        action_key: action
        for action_key, action in actions_by_key.items()
        if action["award_key"] in awards_by_key
    }

    action_keys_by_award: dict[str, list[str]] = defaultdict(list)
    for action_key, action in actions_by_key.items():
        action_keys_by_award[action["award_key"]].append(action_key)
    for award_key, award in awards_by_key.items():
        award["action_keys"] = sorted(
            action_keys_by_award.get(award_key, []),
            key=lambda key: (
                str(actions_by_key[key].get("effective_at") or ""),
                str(actions_by_key[key].get("known_at") or ""),
                key,
            ),
            reverse=True,
        )
        award["action_count"] = len(award["action_keys"])

    awards_by_ticker: dict[str, list[str]] = defaultdict(list)
    for award_key, award in awards_by_key.items():
        for ticker in award["collection_scope_tickers"]:
            awards_by_ticker[ticker].append(award_key)
    for ticker in entity_names:
        awards_by_ticker.setdefault(ticker, [])
    companies: list[dict[str, Any]] = []
    for ticker in sorted(awards_by_ticker):
        award_keys = sorted(
            awards_by_ticker[ticker],
            key=lambda key: (
                str(awards_by_key[key]["dates"]["effective_at"] or ""),
                str(awards_by_key[key]["dates"]["known_at"] or ""),
                key,
            ),
            reverse=True,
        )
        action_count = sum(len(awards_by_key[key]["action_keys"]) for key in award_keys)
        companies.append({
            "ticker": ticker,
            "name": entity_names.get(ticker, ticker),
            "collection_scope": _collection_scope(),
            "award_keys": award_keys,
            "award_count": len(award_keys),
            "action_count": action_count,
            "known_at": _latest_instant(awards_by_key[key]["dates"]["known_at"] for key in award_keys),
        })

    awards_list = [awards_by_key[key] for key in sorted(awards_by_key)]
    actions_list = [actions_by_key[key] for key in sorted(actions_by_key)]
    award_published = sum(
        award.get("record_origin") == "award_record" for award in awards_list
    )
    action_published = len(actions_list)
    awards_rail_status = _status(
        awards_state,
        "partial" if award_dropped or awards_before_cap > MAX_AWARD_RECORDS else "ok",
    )
    actions_rail_status = _status(
        actions_state,
        "partial" if action_dropped or actions_before_cap > MAX_ACTION_RECORDS else "ok",
    )
    top_known_at = _latest_instant([
        observed_at,
        *[award["dates"]["known_at"] for award in awards_list],
        *[action["known_at"] for action in actions_list],
    ])
    as_of_day = _date(as_of) or _date(ingest.get("effective_at"))
    if as_of_day is None:
        as_of_day = _date(top_known_at) or datetime.now(timezone.utc).date().isoformat()
    source_coverage = {
        "awards": _rail(
            state=awards_rail_status,
            loaded=int(len(awards_frame)),
            published=award_published,
            cap=MAX_AWARD_RECORDS,
            bounded_collection=bounded,
            reason=(
                "Stored bounded USAspending award-detail rows were projected by source identity."
                if awards_state == "ok"
                else "Award-detail rail is unavailable or unreadable; no award rows were trusted."
            ),
        ),
        "actions": _rail(
            state=actions_rail_status,
            loaded=int(len(actions_frame)),
            published=action_published,
            cap=MAX_ACTION_RECORDS,
            bounded_collection=bounded,
            reason=(
                "Stored bounded USAspending transaction rows with native action IDs were projected by source identity."
                if actions_state == "ok"
                else "Action rail is unavailable or unreadable; no action rows were trusted."
            ),
        ),
        "issuer_attribution": {
            "status": "not_asserted",
            "records_attributed": 0,
            "reason": ISSUER_LIMITATION,
        },
    }
    freshness = {
        "status": _status(awards_rail_status, actions_rail_status),
        "awards": {
            "status": awards_rail_status,
            "observed_at": observed_at,
            "known_at": _latest_instant(award["dates"]["known_at"] for award in awards_list),
            "reason": source_coverage["awards"]["reason"],
        },
        "actions": {
            "status": actions_rail_status,
            "observed_at": observed_at,
            "known_at": _latest_instant(action["known_at"] for action in actions_list),
            "reason": source_coverage["actions"]["reason"],
        },
    }
    payload: dict[str, Any] = {
        "contract": DOSSIER_CONTRACT,
        "schema_version": DOSSIER_SCHEMA_VERSION,
        "content_id": "",
        "as_of": as_of_day,
        "known_at": top_known_at,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "authority": AUTHORITY.copy(),
        "source_coverage": source_coverage,
        "freshness": freshness,
        "companies": companies,
        "awards": awards_list,
        "actions": actions_list,
        "limitations": [
            "The source collection is bounded and is not the complete USAspending corpus.",
            AWARD_LIMITATION,
            ACTION_LIMITATION,
            ISSUER_LIMITATION,
        ],
    }
    content_id = dossier_content_id(payload)
    if content_id is None:
        raise ValueError("dossier payload cannot be represented as canonical JSON")
    payload["content_id"] = content_id
    if not is_valid_dossier_payload(payload):
        raise ValueError("dossier payload failed its strict public contract")
    return payload


@lru_cache(maxsize=1)
def _dossier_validator() -> Any:
    from jsonschema import Draft202012Validator, FormatChecker

    schema_path = (
        Path(__file__).resolve().parents[2]
        / "contracts"
        / "government_revenue"
        / "government_revenue_dossiers.v1.schema.json"
    )
    return Draft202012Validator(
        json.loads(schema_path.read_text(encoding="utf-8")),
        format_checker=FormatChecker(),
    )


def is_valid_dossier_payload(value: Any) -> bool:
    """Validate the full artifact plus relational invariants at the public boundary."""
    if not isinstance(value, dict):
        return False
    try:
        if any(_dossier_validator().iter_errors(value)):
            return False
        if dossier_content_id(value) != value.get("content_id"):
            return False
        awards = value.get("awards")
        actions = value.get("actions")
        companies = value.get("companies")
        if not all(isinstance(collection, list) for collection in (awards, actions, companies)):
            return False
        award_map = {row.get("award_key"): row for row in awards if isinstance(row, dict)}
        action_map = {row.get("action_key"): row for row in actions if isinstance(row, dict)}
        company_map = {row.get("ticker"): row for row in companies if isinstance(row, dict)}
        if len(award_map) != len(awards) or len(action_map) != len(actions) or len(company_map) != len(companies):
            return False
        for action_key, action in action_map.items():
            if not isinstance(action_key, str) or action.get("award_key") not in award_map:
                return False
        for award_key, award in award_map.items():
            action_keys = award.get("action_keys")
            if not isinstance(action_keys, list) or any(
                key not in action_map or action_map[key].get("award_key") != award_key
                for key in action_keys
            ):
                return False
            if award.get("record_origin") == "action_seeded_stub" and award.get("identity", {}).get("generated_award_id") is None:
                # The source-key/PIID path is valid; only its own official
                # source identity can justify a stub, not a collection ticker.
                if award.get("identity", {}).get("kind") not in {"source_award_key", "piid_scoped_official_fields"}:
                    return False
        for ticker, company in company_map.items():
            award_keys = company.get("award_keys")
            if not isinstance(ticker, str) or not isinstance(award_keys, list):
                return False
            if any(
                key not in award_map or ticker not in award_map[key].get("collection_scope_tickers", [])
                for key in award_keys
            ):
                return False
            if company.get("award_count") != len(award_keys):
                return False
            expected_action_count = sum(len(award_map[key].get("action_keys", [])) for key in award_keys)
            if company.get("action_count") != expected_action_count:
                return False
        return True
    except Exception:  # noqa: BLE001 - validation availability is a hard boundary
        return False


__all__ = [
    "AUTHORITY",
    "CONTENT_ID_PREFIX",
    "DOSSIER_CONTRACT",
    "DOSSIER_FILENAME",
    "DOSSIER_SCHEMA_VERSION",
    "MAX_ACTION_RECORDS",
    "MAX_AWARD_RECORDS",
    "build_dossier_payload",
    "dossier_content_id",
    "is_valid_dossier_payload",
]
