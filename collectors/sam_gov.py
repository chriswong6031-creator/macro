"""SAM.gov contract-OPPORTUNITY collector — the earliest federal procurement signal.

Pre-solicitations and solicitations are posted on SAM.gov weeks to 12+ months before a contract
award appears on USAspending — so this leads even the contracts radar leg for defense / space /
semiconductor / nuclear / critical-minerals themes. It is THEME-level only (pre-award has no
awardee ticker): each NAICS code maps to basket(s), and the count of EARLY notices (recent vs
prior) is the observable.

Source: GET https://api.sam.gov/opportunities/v2/search (api_key, ncode single NAICS, ptype,
postedFrom/To MM/dd/yyyy). GATED: a free key needs a SAM.gov entity registration, so absent
SAM_API_KEY the adapter reports 'blocked' and the radar 'sam_presolicitation' theme_event leg is
silently skipped — it activates the moment the key lands.

Output: data/sam_gov/opp_velocity.parquet — pre-aggregated per-basket {recent_count, prior_count}.
NAICS -> basket map: data/sam_gov/naics_themes.json.

W0d addition: new_programs() pure function detects first-ever-seen NAICS codes per basket and
writes a ledger (data/sam_gov/naics_seen.json) used by engine/theme_activity._load_new_program_events()
to surface new-program regime annotations.  Appends new events to data/theme_activity/program_ledger.parquet.
Limitation: the velocity() function (and its on-disk output) remains count-only — new_programs()
requires the full raw opps list, available only inside fetch().
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import pandas as pd
import requests

from collectors.base import Adapter, is_connection_error
from lib import config

log = logging.getLogger(__name__)

SEARCH_URL = "https://api.sam.gov/opportunities/v2/search"
RECENT_D = 90
PRIOR_D = 90
# notice types that are EARLY (pre-award); SAM `type` is a full string — substring match.
EARLY_TYPES = ("presol", "solicitation", "sources sought", "combined")


def _naics_themes() -> dict[str, list[str]]:
    p = config.data_dir() / "sam_gov" / "naics_themes.json"
    if not p.exists():
        return {}
    try:
        return (json.loads(p.read_text()) or {}).get("naics", {})
    except Exception:  # noqa: BLE001
        return {}


def new_programs(opps: list[dict], naics_map: dict[str, list[str]],
                 seen_path: Path, ledger_path: Path | None = None) -> list[dict]:
    """Pure (except disk I/O): detect first-ever-seen NAICS codes per basket.

    Reads the persistent seen_path JSON ({basket_id: [naics, ...]}) and emits an event dict
    for each NAICS code that is new for a basket this run.  Writes the updated set back to
    seen_path.  Idempotent: re-running with the same opps produces [] after the first call.

    If seen_path is missing/corrupt but ledger_path exists, the seen-set is RECONSTRUCTED
    from the ledger's (basket_id, naics_or_cfda) pairs — a lost/corrupt JSON must not make
    every historical NAICS re-emit as a fake "new program" event (PIT honesty).

    Returns a list of {basket_id, naics_or_cfda, source, first_seen_date, title, type} dicts
    for all newly-seen codes.  Empty when opps or naics_map is empty."""
    if not opps or not naics_map:
        return []
    seen: dict[str, list[str]] = {}
    if seen_path.exists():
        try:
            seen = json.loads(seen_path.read_text()) or {}
        except Exception:  # noqa: BLE001
            seen = {}
    if not seen and ledger_path is not None and ledger_path.exists():
        try:
            led = pd.read_parquet(ledger_path)
            for b, code in zip(led["basket_id"].astype(str), led["naics_or_cfda"].astype(str)):
                if code not in seen.setdefault(b, []):
                    seen[b].append(code)
        except Exception:  # noqa: BLE001
            pass
    events: list[dict] = []
    today_str = str(pd.Timestamp.now().date())
    for o in opps:
        naics = str(o.get("naicsCode") or "").strip()
        if not naics:
            continue
        baskets = naics_map.get(naics) or naics_map.get(naics[:6]) or []
        for b in baskets:
            known = seen.setdefault(b, [])
            if naics not in known:
                known.append(naics)
                events.append({
                    "basket_id": b,
                    "naics_or_cfda": naics,
                    "source": "sam_gov",
                    "first_seen_date": today_str,
                    "title": str(o.get("title") or "")[:120],
                    "type": str(o.get("type") or ""),
                })
    if events:
        seen_path.parent.mkdir(parents=True, exist_ok=True)
        seen_path.write_text(json.dumps(seen, indent=2))
    return events


def velocity(opps: list[dict], naics_map: dict[str, list[str]], *, today=None) -> pd.DataFrame:
    """Pure: roll early-notice opportunities up to per-basket recent-vs-prior counts via NAICS."""
    if not opps or not naics_map:
        return pd.DataFrame()
    t0 = pd.Timestamp(today) if today is not None else pd.Timestamp(datetime.now(timezone.utc).date())
    rec_lo, pri_lo = t0 - pd.Timedelta(days=RECENT_D), t0 - pd.Timedelta(days=RECENT_D + PRIOR_D)
    counts: dict[str, list[int]] = {}
    for o in opps:
        typ = str(o.get("type") or "").lower()
        if not any(t in typ for t in EARLY_TYPES):
            continue
        naics = str(o.get("naicsCode") or "").strip()
        baskets = naics_map.get(naics) or naics_map.get(naics[:6]) or []
        if not baskets:
            continue
        posted = pd.to_datetime(o.get("postedDate"), errors="coerce")
        if pd.isna(posted):
            continue
        if rec_lo < posted <= t0:
            slot = 0
        elif pri_lo < posted <= rec_lo:
            slot = 1
        else:
            continue
        for b in baskets:
            counts.setdefault(b, [0, 0])[slot] += 1
    rows = [{"basket_id": b, "recent_count": rc, "prior_count": pc, "n_members": 0, "covered": ""}
            for b, (rc, pc) in counts.items() if rc or pc]
    return pd.DataFrame(rows).set_index("basket_id") if rows else pd.DataFrame()


# ---------------------------------------------------------------------------
# Government Revenue Foresight opportunity ledger
# ---------------------------------------------------------------------------
#
# The legacy ``SamGovAdapter`` below deliberately stays a small, theme-level
# velocity feed.  The opportunity ledger is a separate composite-key store:
# generic ``lib.store`` time-series upserts cannot represent several notices or
# revisions observed on the same day without collapsing them.  SAM's public
# Opportunities API is explicitly a *latest-version* API, so every revision in
# this ledger means "this distinct state was first observed by our poll" -- not
# a claim that SAM exposed the full historical amendment chain.  Data Services
# remains the source for a later historical backfill.

SAM_OPPORTUNITY_SCHEMA = "government_revenue.sam_opportunities.v1"
SAM_OPPORTUNITY_STATUS_SCHEMA = "government_revenue.sam_opportunity_ingest_status.v1"
SAM_OPPORTUNITY_SOURCE = "sam.gov_opportunities_public_api_v2"
# The semantic material-gate workflow is scheduled every thirty minutes.  Keep
# the artifact contract aligned with the actual writer cadence; promising a
# fifteen minute feed would make otherwise healthy observations look late.
SAM_OPPORTUNITY_TARGET_POLL_MINUTES = 30
SAM_OPPORTUNITY_DEFAULT_LOOKBACK_DAYS = 31
SAM_OPPORTUNITY_MAX_LOOKBACK_WINDOW_DAYS = 364  # OpenGSA caps a request at one year.
SAM_DOCUMENT_HOSTS = {"api.sam.gov", "api-alpha.sam.gov"}

# State columns are deliberately source-shaped and presentation-neutral.  The
# engine/UI lane must label ``posted_at`` and ``response_deadline`` as official
# fields and must never turn ``known_at`` into an official amendment date.
SAM_OPPORTUNITY_STATE_COLUMNS = [
    "notice_id",
    "solicitation_number",
    "title",
    "description",
    "notice_type",
    "base_type",
    "status",
    "active",
    "agency",
    "subtier",
    "office",
    "full_parent_path_name",
    "full_parent_path_code",
    "organization_type",
    "naics_code",
    "psc_code",
    "set_aside",
    "set_aside_code",
    "posted_at",
    "response_deadline",
    "archive_date",
    "archive_type",
    "place_of_performance",
    "award_number",
    "award_date",
    "award_amount",
    "awardee_name",
    "awardee_uei",
    "description_url",
    "additional_info_url",
    "ui_url",
    "notice_url",
    "resource_links",
    "resource_link_set_sha256",
    "document_link_count",
    "source_url",
]
SAM_OPPORTUNITY_COLUMNS = [
    *SAM_OPPORTUNITY_STATE_COLUMNS,
    "content_sha256",
    "revision_id",
    "captured_at",
    "known_at",
    "effective_at",
    "first_seen_at",
    "last_seen_at",
]
SAM_OPPORTUNITY_REVISION_COLUMNS = [*SAM_OPPORTUNITY_COLUMNS, "revision_origin"]
SAM_OPPORTUNITY_DOCUMENT_COLUMNS = [
    "notice_id",
    "revision_id",
    "document_key",
    "document_kind",
    "title",
    "document_url",
    "url_sha256",
    "content_sha256",
    "hash_basis",
    "content_length",
    "content_type",
    "mime_type",
    "fetch_status",
    "source_url",
    "captured_at",
    "known_at",
    "effective_at",
    "first_seen_at",
    "last_seen_at",
]


def _sam_text(value: Any) -> str | None:
    """Return a normalized scalar without turning source nulls into strings."""
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    text = str(value).strip()
    return text if text and text.lower() not in {"none", "nan", "nat", "null"} else None


def _sam_float(value: Any) -> float | None:
    text = _sam_text(value)
    if text is None:
        return None
    try:
        return float(text.replace("$", "").replace(",", ""))
    except ValueError:
        return None


def _sam_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    text = _sam_text(value)
    if text is None:
        return None
    lowered = text.lower()
    if lowered in {"yes", "y", "true", "1", "active"}:
        return True
    if lowered in {"no", "n", "false", "0", "inactive", "archived"}:
        return False
    return None


def _sam_timestamp(value: Any) -> str | None:
    """Normalize official date/timestamps to UTC ISO; retain nonparseable text honestly."""
    text = _sam_text(value)
    if text is None:
        return None
    parsed = pd.to_datetime(text, errors="coerce", utc=True)
    if pd.isna(parsed):
        return text
    return parsed.isoformat()


def _sam_is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and pd.isna(value):
        return True
    return isinstance(value, str) and not value.strip()


def _sam_canonical_json(value: Any) -> str:
    """Stable bytes for change detection, never including the API key."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _sam_sha256(value: Any) -> str:
    if not isinstance(value, (str, bytes)):
        value = _sam_canonical_json(value)
    payload = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(payload).hexdigest()


_SAM_SENSITIVE_QUERY_RE = re.compile(
    r"(?:api[_-]?key|apikey|token|secret|signature|credential|authorization|password|x-amz)",
    flags=re.IGNORECASE,
)


def _sam_safe_url(value: Any) -> str | None:
    """Persist a navigable, deterministic URL while stripping credential-like query keys.

    The source may return pre-signed or API-key-bearing links.  Keeping such a URL
    in a Parquet, status JSON, exception, or UI payload would turn a public-data
    collector into a credential leak.  A filtered/sorted query preserves stable
    non-secret identifiers such as ``noticeid`` and ``resourceId``.
    """
    text = _sam_text(value)
    if text is None:
        return None
    try:
        parsed = urlsplit(text)
    except ValueError:
        return None
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return None
    query = [
        (key, item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        if not _SAM_SENSITIVE_QUERY_RE.search(key)
    ]
    query.sort()
    return urlunsplit((parsed.scheme.lower(), parsed.netloc, parsed.path, urlencode(query), ""))


def _sam_safe_error(exc: Exception | str, api_key: str | None = None) -> str:
    """Make an error/status string useful without ever recording the SAM key."""
    text = str(exc)
    if api_key:
        text = text.replace(api_key, "[REDACTED]")
    # Query values can appear in requests' exception rendering.  Preserve the
    # endpoint context while redacting credential-like values even if the key is
    # not the exact configured secret (for example a proxy or a pre-signed URL).
    text = re.sub(
        r"(?i)((?:api[_-]?key|apikey|token|secret|signature|credential|authorization|password)\s*[=:]\s*)[^\s&,'\"]+",
        r"\1[REDACTED]",
        text,
    )
    return text[:600]


def _sam_self_link(raw: dict) -> str | None:
    links = raw.get("links") or []
    if isinstance(links, dict):
        links = [links]
    for item in links:
        if not isinstance(item, dict):
            continue
        if str(item.get("rel") or "").lower() == "self":
            return _sam_safe_url(item.get("href"))
    return None


def _sam_document_links(raw: dict) -> list[tuple[str, str]]:
    """Return sorted, safe document/description links with no credentials."""
    found: set[tuple[str, str]] = set()
    resources = raw.get("resourceLinks") or raw.get("resource_links") or []
    if isinstance(resources, (str, dict)):
        resources = [resources]
    if isinstance(resources, list):
        for item in resources:
            if isinstance(item, dict):
                item = item.get("href") or item.get("url") or item.get("link")
            url = _sam_safe_url(item)
            if url:
                found.add(("resource", url))
    description_url = _sam_safe_url(raw.get("description"))
    if description_url:
        found.add(("description", description_url))
    return sorted(found)


def _sam_place_of_performance(raw: dict) -> str | None:
    pop = raw.get("placeOfPerformance") or raw.get("place_of_performance")
    if not isinstance(pop, dict):
        return None

    def part(name: str) -> str | None:
        value = pop.get(name)
        if isinstance(value, dict):
            return _sam_text(value.get("code") or value.get("name"))
        return _sam_text(value)

    # Street-level data is unnecessary for the investor product.  City/state/zip
    # are sufficient for geography joins and avoid retaining excess contact data.
    out = {
        "city": part("city"),
        "state": part("state"),
        "zip": part("zip"),
        "country": part("country"),
    }
    out = {key: value for key, value in out.items() if value is not None}
    return _sam_canonical_json(out) if out else None


def _sam_description(raw: dict) -> tuple[str | None, str | None]:
    """SAM's ``description`` can be plain text or a protected description URL."""
    value = _sam_text(raw.get("description"))
    if value is None:
        return None, None
    safe_url = _sam_safe_url(value)
    return (None, safe_url) if safe_url else (value, None)


def normalize_opportunity(raw: dict, observed_at: str) -> dict:
    """Normalize one SAM notice into a deterministic, bitemporal record.

    ``noticeId`` is the documented public identifier.  Missing IDs are rejected
    rather than synthesized from mutable title/date text, which would make an
    amendment look like a new opportunity and violate the no-alert-storm rule.
    """
    if not isinstance(raw, dict):
        raise ValueError("SAM opportunity must be an object")
    notice_id = _sam_text(raw.get("noticeId") or raw.get("notice_id"))
    if not notice_id:
        raise ValueError("SAM opportunity missing noticeId")
    award = raw.get("award") or {}
    if not isinstance(award, dict):
        award = {}
    awardee = award.get("awardee") or {}
    if not isinstance(awardee, dict):
        awardee = {}
    description, description_url = _sam_description(raw)
    document_links = _sam_document_links(raw)
    resource_urls = [url for kind, url in document_links if kind == "resource"]
    notice_url = _sam_self_link(raw)
    ui_url = _sam_safe_url(raw.get("uiLink") or raw.get("ui_url"))
    # Retain a per-record source reference rather than a generic search endpoint.
    # Both candidate URLs have had credential-like query values stripped above.
    source_url = notice_url or ui_url or f"https://sam.gov/opp/{notice_id}/view"
    active = _sam_bool(raw.get("active"))
    raw_status = _sam_text(raw.get("status"))
    status = raw_status.lower() if raw_status else ("active" if active is True else "inactive" if active is False else None)
    posted_at = _sam_timestamp(raw.get("postedDate") or raw.get("posted_date"))
    state = {
        "notice_id": notice_id,
        "solicitation_number": _sam_text(raw.get("solicitationNumber") or raw.get("solicitation_number")),
        "title": _sam_text(raw.get("title")),
        "description": description,
        "notice_type": _sam_text(raw.get("type") or raw.get("notice_type")),
        "base_type": _sam_text(raw.get("baseType") or raw.get("base_type")),
        "status": status,
        "active": active,
        "agency": _sam_text(raw.get("department") or raw.get("agency")),
        "subtier": _sam_text(raw.get("subTier") or raw.get("subtier")),
        "office": _sam_text(raw.get("office")),
        "full_parent_path_name": _sam_text(raw.get("fullParentPathName") or raw.get("full_parent_path_name")),
        "full_parent_path_code": _sam_text(raw.get("fullParentPathCode") or raw.get("full_parent_path_code")),
        "organization_type": _sam_text(raw.get("organizationType") or raw.get("organization_type")),
        "naics_code": _sam_text(raw.get("naicsCode") or raw.get("naics_code")),
        "psc_code": _sam_text(raw.get("classificationCode") or raw.get("psc_code")),
        "set_aside": _sam_text(raw.get("typeOfSetAsideDescription") or raw.get("setAside")),
        "set_aside_code": _sam_text(raw.get("typeOfSetAside") or raw.get("setAsideCode")),
        "posted_at": posted_at,
        "response_deadline": _sam_timestamp(raw.get("responseDeadLine") or raw.get("reponseDeadLine") or raw.get("response_deadline")),
        "archive_date": _sam_timestamp(raw.get("archiveDate") or raw.get("archive_date")),
        "archive_type": _sam_text(raw.get("archiveType") or raw.get("archive_type")),
        "place_of_performance": _sam_place_of_performance(raw),
        "award_number": _sam_text(award.get("number")),
        "award_date": _sam_timestamp(award.get("date")),
        "award_amount": _sam_float(award.get("amount")),
        "awardee_name": _sam_text(awardee.get("name")),
        "awardee_uei": _sam_text(awardee.get("ueiSAM") or awardee.get("uei")),
        "description_url": description_url,
        "additional_info_url": _sam_safe_url(raw.get("additionalInfoLink") or raw.get("additional_info_url")),
        "ui_url": ui_url,
        "notice_url": notice_url,
        "resource_links": _sam_canonical_json(resource_urls),
        "resource_link_set_sha256": _sam_sha256(document_links),
        "document_link_count": len(document_links),
        "source_url": source_url,
    }
    content_sha256 = _sam_sha256({key: state.get(key) for key in SAM_OPPORTUNITY_STATE_COLUMNS})
    return {
        **state,
        "content_sha256": content_sha256,
        "revision_id": f"{notice_id}:{content_sha256}",
        "captured_at": observed_at,
        "known_at": observed_at,
        # The public latest-version endpoint does not expose an amendment timestamp.
        # ``posted_at`` is the only source-effective time carried through; the first
        # evidence of a changed state is ``known_at``.
        "effective_at": posted_at,
        "first_seen_at": observed_at,
        "last_seen_at": observed_at,
    }


def _sam_rehash(row: dict) -> dict:
    """Recompute the state hash after a non-null-preserving current-state merge."""
    out = {key: row.get(key) for key in SAM_OPPORTUNITY_COLUMNS}
    content_sha256 = _sam_sha256({key: out.get(key) for key in SAM_OPPORTUNITY_STATE_COLUMNS})
    out["content_sha256"] = content_sha256
    out["revision_id"] = f"{out['notice_id']}:{content_sha256}"
    return out


def _sam_dedupe_incoming(rows: Iterable[dict]) -> tuple[list[dict], list[dict]]:
    """Deterministically collapse exact duplicate notices and flag contradictory ones."""
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        notice_id = _sam_text(row.get("notice_id"))
        if notice_id:
            grouped.setdefault(notice_id, []).append(row)
    selected: list[dict] = []
    collisions: list[dict] = []
    for notice_id in sorted(grouped):
        candidates = grouped[notice_id]
        by_hash: dict[str, dict] = {}
        for candidate in candidates:
            by_hash[str(candidate.get("content_sha256"))] = candidate
        if len(by_hash) > 1:
            # The public API should return one latest state per notice.  We choose a
            # deterministic most-complete row for continuity, but call this out as
            # partial rather than manufacture a same-poll amendment sequence.
            collisions.append({
                "stage": "dedupe",
                "notice_id": notice_id,
                "error": f"conflicting states returned in one poll ({len(by_hash)})",
            })
        ranked = sorted(
            by_hash.values(),
            key=lambda item: (
                -sum(not _sam_is_missing(item.get(column)) for column in SAM_OPPORTUNITY_STATE_COLUMNS),
                str(item.get("content_sha256") or ""),
            ),
        )
        selected.append(ranked[0])
    return selected, collisions


def _sam_read_parquet(path: Path, columns: list[str]) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=columns)
    try:
        return pd.read_parquet(path).reindex(columns=columns)
    except Exception as exc:  # noqa: BLE001 - PIT ledgers fail closed, never overwrite corruption
        raise RuntimeError(f"refusing to overwrite unreadable accrued store: {path}: {_sam_safe_error(exc)}") from exc


def _sam_read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text())
        return payload if isinstance(payload, dict) else {}
    except Exception:  # noqa: BLE001 - health is advisory; data ledgers remain authoritative
        return {}


def _sam_atomic_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        frame.to_parquet(temporary, index=False)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _sam_atomic_json(payload: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _sam_merge_current(existing: pd.DataFrame, incoming: list[dict], observed_at: str) -> tuple[pd.DataFrame, list[dict]]:
    """Replace current state while preserving the first-known clock of identical bytes.

    Source nulls are meaningful: a later notice can remove a deadline, link, or
    set-aside. Historical evidence remains in the revision ledger, so carrying an
    old non-null value into the latest state would be a fabricated current fact.
    """
    old = existing.reindex(columns=SAM_OPPORTUNITY_COLUMNS).copy()
    old = old.dropna(subset=["notice_id"]).drop_duplicates("notice_id", keep="last")
    old_by_id = {str(row["notice_id"]): row.to_dict() for _, row in old.iterrows()}
    resolved: list[dict] = []
    for incoming_row in incoming:
        notice_id = str(incoming_row["notice_id"])
        previous = old_by_id.get(notice_id, {})
        merged = dict(incoming_row)
        merged["effective_at"] = merged.get("posted_at")
        merged["first_seen_at"] = previous.get("first_seen_at") or observed_at
        merged["last_seen_at"] = observed_at
        merged = _sam_rehash(merged)
        if previous and previous.get("content_sha256") == merged.get("content_sha256"):
            merged["known_at"] = previous.get("known_at") or previous.get("first_seen_at") or observed_at
            merged["captured_at"] = previous.get("captured_at") or merged["known_at"]
        else:
            merged["known_at"] = observed_at
            merged["captured_at"] = observed_at
        resolved.append(merged)
    new_ids = {str(row["notice_id"]) for row in resolved}
    retained = [row.to_dict() for _, row in old.iterrows() if str(row["notice_id"]) not in new_ids]
    out = pd.DataFrame([*retained, *resolved], columns=SAM_OPPORTUNITY_COLUMNS)
    if not out.empty:
        out = out.sort_values("notice_id", kind="stable").reset_index(drop=True)
    return out, resolved


def _sam_merge_revisions(existing: pd.DataFrame, incoming: list[dict], observed_at: str) -> pd.DataFrame:
    """Append observed state transitions, including A→B→A reversions."""
    old = existing.reindex(columns=SAM_OPPORTUNITY_REVISION_COLUMNS).copy()
    records = [
        row.to_dict()
        for _, row in old.dropna(subset=["notice_id", "content_sha256"]).iterrows()
    ]
    records.sort(key=lambda row: (
        str(row.get("notice_id") or ""),
        str(row.get("known_at") or row.get("first_seen_at") or ""),
    ))
    latest_index: dict[str, int] = {}
    seen_hashes: set[tuple[str, str]] = set()
    for index, row in enumerate(records):
        notice_id = str(row.get("notice_id"))
        latest_index[notice_id] = index
        seen_hashes.add((notice_id, str(row.get("content_sha256"))))

    for current in incoming:
        row = {key: current.get(key) for key in SAM_OPPORTUNITY_COLUMNS}
        notice_id = str(row["notice_id"])
        content_hash = str(row["content_sha256"])
        prior_index = latest_index.get(notice_id)
        prior = records[prior_index] if prior_index is not None else None
        if prior is not None and str(prior.get("content_sha256")) == content_hash:
            # A quiet repeat extends only the observation horizon of the latest
            # transition; its first-known/version identity stays immutable.
            prior["last_seen_at"] = observed_at
            continue

        row["first_seen_at"] = observed_at
        row["last_seen_at"] = observed_at
        row["captured_at"] = observed_at
        row["known_at"] = observed_at
        row["revision_origin"] = "observed_latest_api_state"
        if (notice_id, content_hash) in seen_hashes:
            base_revision = str(row.get("revision_id") or content_hash)
            transition = hashlib.sha256(
                f"{notice_id}|{content_hash}|{observed_at}".encode("utf-8")
            ).hexdigest()[:12]
            row["revision_id"] = f"{base_revision}:transition-{transition}"
        records.append(row)
        latest_index[notice_id] = len(records) - 1
        seen_hashes.add((notice_id, content_hash))

    out = pd.DataFrame(records, columns=SAM_OPPORTUNITY_REVISION_COLUMNS)
    if not out.empty:
        out = out.sort_values(["notice_id", "known_at", "revision_id"], kind="stable").reset_index(drop=True)
    return out


def _sam_merge_documents(existing: pd.DataFrame, incoming: list[dict], observed_at: str) -> pd.DataFrame:
    """Preserve first-seen document bytes/URL evidence; content changes add a new row."""
    old = existing.reindex(columns=SAM_OPPORTUNITY_DOCUMENT_COLUMNS).copy()
    prior: dict[tuple[str, str, str], dict] = {}
    for _, row in old.dropna(subset=["notice_id", "document_key", "content_sha256"]).iterrows():
        prior[(str(row["notice_id"]), str(row["document_key"]), str(row["content_sha256"]))] = row.to_dict()
    content_evidence_keys = {
        (str(row.get("notice_id")), str(row.get("document_key")))
        for row in prior.values()
        if row.get("hash_basis") == "content"
    }
    for raw in incoming:
        row = {key: raw.get(key) for key in SAM_OPPORTUNITY_DOCUMENT_COLUMNS}
        identity = (str(row["notice_id"]), str(row["document_key"]))
        if row.get("hash_basis") != "content" and identity in content_evidence_keys:
            # A failed/deferred re-fetch is health evidence, not a new document
            # version. The status ledger already carries the error; retain prior
            # byte evidence without pretending it was re-observed successfully.
            continue
        key = (str(row["notice_id"]), str(row["document_key"]), str(row["content_sha256"]))
        existing_row = prior.get(key)
        row["last_seen_at"] = observed_at
        row["captured_at"] = observed_at
        row["known_at"] = observed_at
        if existing_row:
            row["first_seen_at"] = existing_row.get("first_seen_at") or observed_at
            row["known_at"] = existing_row.get("known_at") or row["first_seen_at"]
            row["captured_at"] = existing_row.get("captured_at") or row["known_at"]
        else:
            row["first_seen_at"] = observed_at
        prior[key] = row
    out = pd.DataFrame(list(prior.values()), columns=SAM_OPPORTUNITY_DOCUMENT_COLUMNS)
    if not out.empty:
        out = out.sort_values(["notice_id", "document_key", "first_seen_at", "content_sha256"], kind="stable").reset_index(drop=True)
    return out


def opportunity_revisions_as_of(revisions: pd.DataFrame, cutoff: str | datetime) -> pd.DataFrame:
    """PIT-safe latest-known state per notice, excluding later observed amendments.

    Consumers must use this helper (or the equivalent ``known_at <= cutoff``
    filter) instead of treating ``posted_at`` as the availability clock.  The
    public API's current state can change after the historical posted date.
    """
    if revisions is None or revisions.empty:
        return pd.DataFrame(columns=SAM_OPPORTUNITY_REVISION_COLUMNS)
    cutoff_ts = pd.Timestamp(cutoff)
    if cutoff_ts.tzinfo is None:
        cutoff_ts = cutoff_ts.tz_localize("UTC")
    else:
        cutoff_ts = cutoff_ts.tz_convert("UTC")
    work = revisions.reindex(columns=SAM_OPPORTUNITY_REVISION_COLUMNS).copy()
    work["__known_at"] = pd.to_datetime(work["known_at"], errors="coerce", utc=True)
    work = work[work["__known_at"].notna() & (work["__known_at"] <= cutoff_ts)]
    if work.empty:
        return pd.DataFrame(columns=SAM_OPPORTUNITY_REVISION_COLUMNS)
    work = work.sort_values(["notice_id", "__known_at", "content_sha256"], kind="stable")
    return work.drop_duplicates("notice_id", keep="last").drop(columns="__known_at").reset_index(drop=True)


class SamGovOpportunityCollector:
    """Bounded SAM.gov opportunity/revision/document collector.

    The class accepts an injectable ``requests.Session`` so all transformation,
    retry, partial-failure, and PIT tests are hermetic.  The configured API key is
    used only as an outbound query parameter and is never persisted, logged, or
    returned in status objects.
    """

    def __init__(
        self,
        root: Path | None = None,
        api_key: str | None = None,
        session: requests.Session | None = None,
        page_size: int = 1000,
        max_pages_per_query: int = 20,
        request_pacing_seconds: float = 0.25,
        retry_backoff_seconds: float = 1.0,
        max_document_fetches: int = 32,
        max_document_bytes: int = 8_000_000,
        fetch_documents: bool = True,
        user_agent: str | None = None,
    ) -> None:
        self.root = Path(root).resolve() if root is not None else Path.cwd().resolve()
        self.api_key = api_key if api_key is not None else config.secret("SAM_API_KEY")
        self.session = session or requests.Session()
        self.page_size = max(1, min(int(page_size), 1000))
        self.max_pages_per_query = max(1, int(max_pages_per_query))
        self.request_pacing_seconds = max(0.0, float(request_pacing_seconds))
        self.retry_backoff_seconds = max(0.0, float(retry_backoff_seconds))
        self.max_document_fetches = max(0, int(max_document_fetches))
        self.max_document_bytes = max(1, int(max_document_bytes))
        self.fetch_documents = bool(fetch_documents)
        self.headers = {
            "User-Agent": user_agent or config.load()["sponsors"]["user_agent"],
            "Accept": "application/json, application/octet-stream;q=0.9, */*;q=0.8",
        }

    @property
    def data_dir(self) -> Path:
        return self.root / "data" / "government_revenue"

    @property
    def opportunities_path(self) -> Path:
        return self.data_dir / "opportunities.parquet"

    @property
    def revisions_path(self) -> Path:
        return self.data_dir / "opportunity_revisions.parquet"

    @property
    def documents_path(self) -> Path:
        return self.data_dir / "opportunity_documents.parquet"

    @property
    def status_path(self) -> Path:
        return self.data_dir / "opportunity_ingest_status.json"

    def _get(self, url: str, *, params: dict | None = None, stream: bool = False):
        """Call an injected session while retaining compatibility with tiny test fakes."""
        kwargs = {"params": params, "headers": self.headers, "timeout": 60}
        if stream:
            kwargs["stream"] = True
        try:
            return self.session.get(url, allow_redirects=False, **kwargs)
        except TypeError:
            # Test doubles commonly implement the minimum requests signature.
            return self.session.get(url, **kwargs)

    def _retry_delay(self, response: Any, attempt: int) -> float:
        headers = getattr(response, "headers", {}) or {}
        raw = headers.get("Retry-After") if hasattr(headers, "get") else None
        try:
            return max(0.0, float(raw))
        except (TypeError, ValueError):
            return self.retry_backoff_seconds * (2 ** attempt)

    def _get_json(self, url: str, params: dict, *, retries: int = 3, allow_404: bool = False) -> dict | None:
        if not self.api_key:
            raise RuntimeError("SAM_API_KEY not set")
        query = {**params, "api_key": self.api_key}
        last: Exception | None = None
        for attempt in range(max(1, retries)):
            try:
                response = self._get(url, params=query)
                status_code = int(getattr(response, "status_code", 200))
                if status_code == 404 and allow_404:
                    return None
                if status_code in {429, 500, 502, 503, 504}:
                    raise requests.HTTPError(f"HTTP {status_code}", response=response)
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ValueError("SAM response was not an object")
                return payload
            except Exception as exc:  # noqa: BLE001 - response errors are retried and surfaced safely
                last = exc
                if attempt + 1 < max(1, retries):
                    response = getattr(exc, "response", None)
                    delay = self._retry_delay(response, attempt) if response is not None else self.retry_backoff_seconds * (2 ** attempt)
                    if delay:
                        time.sleep(delay)
        assert last is not None
        raise last

    def _fetch_query(self, query: dict) -> tuple[list[dict], dict]:
        """Page SAM until source exhaustion is proven or return an incomplete shard."""
        offset = 0
        pages_requested = 0
        pages_succeeded = 0
        rows: list[dict] = []
        total_records: int | None = None
        complete = False
        incomplete_reason: str | None = None
        shard_error: str | None = None
        while pages_requested < self.max_pages_per_query:
            pages_requested += 1
            try:
                payload = self._get_json(
                    SEARCH_URL,
                    {**query, "limit": self.page_size, "offset": offset},
                    allow_404=True,
                )
            except Exception as exc:  # noqa: BLE001 - retain prior pages as explicit partial evidence
                if not rows:
                    raise
                incomplete_reason = "later_page_request_failed"
                shard_error = _sam_safe_error(exc, self.api_key)
                break
            pages_succeeded += 1
            if payload is None:  # documented "No Data found" response
                complete = True
                break
            batch = payload.get("opportunitiesData") or []
            if not isinstance(batch, list):
                raise ValueError("SAM opportunitiesData was not a list")
            rows.extend(item for item in batch if isinstance(item, dict))
            try:
                total_records = int(payload.get("totalRecords"))
            except (TypeError, ValueError):
                total_records = total_records
            if not batch:
                if total_records is None or offset >= total_records:
                    complete = True
                else:
                    incomplete_reason = "empty_page_before_reported_total"
                break
            source_offset = payload.get("offset")
            try:
                source_offset = int(source_offset)
            except (TypeError, ValueError):
                source_offset = offset
            source_limit = payload.get("limit")
            try:
                source_limit = max(1, int(source_limit))
            except (TypeError, ValueError):
                source_limit = self.page_size
            next_offset = source_offset + source_limit
            if total_records is not None and next_offset >= total_records:
                complete = True
                break
            if next_offset <= offset:
                raise RuntimeError("SAM pagination did not advance offset")
            offset = next_offset
            if self.request_pacing_seconds:
                time.sleep(self.request_pacing_seconds)
        if not complete and incomplete_reason is None:
            incomplete_reason = "max_pages_reached_without_terminal_proof"
        truncated = not complete
        return rows, {
            "pages": pages_requested,
            "pages_requested": pages_requested,
            "pages_succeeded": pages_succeeded,
            "total_records": total_records,
            "truncated": truncated,
            "complete": complete,
            "incomplete_reason": incomplete_reason,
            "error": shard_error,
            "last_offset": offset,
        }

    def _date_windows(self, end: datetime.date, lookback_days: int) -> list[tuple[datetime.date, datetime.date]]:
        start = end - timedelta(days=max(0, int(lookback_days)))
        windows: list[tuple[datetime.date, datetime.date]] = []
        cursor = start
        while cursor <= end:
            window_end = min(cursor + timedelta(days=SAM_OPPORTUNITY_MAX_LOOKBACK_WINDOW_DAYS), end)
            windows.append((cursor, window_end))
            cursor = window_end + timedelta(days=1)
        return windows

    def _document_request(self, safe_url: str) -> tuple[bytes | None, str | None, int | None, str]:
        """Fetch attachment bytes only from official API hosts; never forward key elsewhere."""
        parsed = urlsplit(safe_url)
        host = (parsed.hostname or "").lower()
        if host not in SAM_DOCUMENT_HOSTS:
            return None, None, None, "link_only_external_host"
        if not self.api_key:
            return None, None, None, "blocked_no_api_key"
        response = self._get(safe_url, params={"api_key": self.api_key}, stream=True)
        status_code = int(getattr(response, "status_code", 200))
        if status_code == 404:
            return None, None, None, "not_found"
        # ``_get`` deliberately disables redirects so an attachment endpoint
        # cannot silently move an API-key-bearing request to an arbitrary host.
        # ``requests.Response.raise_for_status`` does not raise for 3xx, so
        # handle that class before touching headers/body: an HTML redirect body
        # is neither document evidence nor safe content to hash.
        if 300 <= status_code < 400:
            return None, None, None, "redirect_not_followed"
        if status_code in {429, 500, 502, 503, 504}:
            raise requests.HTTPError(f"HTTP {status_code}", response=response)
        response.raise_for_status()
        headers = getattr(response, "headers", {}) or {}
        content_type = headers.get("Content-Type") if hasattr(headers, "get") else None
        try:
            content_length = int(headers.get("Content-Length")) if headers.get("Content-Length") else None
        except (TypeError, ValueError):
            content_length = None
        if content_length is not None and content_length > self.max_document_bytes:
            return None, content_type, content_length, "skipped_oversize"
        if hasattr(response, "iter_content"):
            chunks: list[bytes] = []
            size = 0
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                size += len(chunk)
                if size > self.max_document_bytes:
                    return None, content_type, size, "skipped_oversize"
                chunks.append(chunk)
            content = b"".join(chunks)
        else:
            content = getattr(response, "content", b"")
            if not isinstance(content, bytes):
                content = bytes(content)
            if len(content) > self.max_document_bytes:
                return None, content_type, len(content), "skipped_oversize"
        return content, content_type, len(content), "fetched"

    def _document_evidence(self, raw: dict, normalized: dict, observed_at: str, errors: list[dict], budget: list[int]) -> list[dict]:
        rows: list[dict] = []
        for kind, document_url in _sam_document_links(raw):
            url_sha256 = _sam_sha256(document_url)
            content_sha256 = url_sha256
            hash_basis = "url"
            content_length: int | None = None
            content_type: str | None = None
            fetch_status = "link_observed"
            if self.fetch_documents and budget[0] < self.max_document_fetches:
                budget[0] += 1
                try:
                    content, content_type, content_length, fetch_status = self._document_request(document_url)
                    if content is not None:
                        content_sha256 = _sam_sha256(content)
                        hash_basis = "content"
                except Exception as exc:  # noqa: BLE001 - a single attachment cannot sink a notice poll
                    fetch_status = "fetch_failed"
                    errors.append({
                        "stage": "document",
                        "notice_id": normalized["notice_id"],
                        "document_key": url_sha256,
                        "error": _sam_safe_error(exc, self.api_key),
                    })
            elif self.fetch_documents:
                fetch_status = "deferred_budget"
            rows.append({
                "notice_id": normalized["notice_id"],
                "revision_id": normalized["revision_id"],
                "document_key": url_sha256,
                "document_kind": kind,
                "title": "Notice description" if kind == "description" else "SAM attachment",
                "document_url": document_url,
                "url_sha256": url_sha256,
                "content_sha256": content_sha256,
                "hash_basis": hash_basis,
                "content_length": content_length,
                "content_type": content_type,
                "mime_type": content_type,
                "fetch_status": fetch_status,
                # Consumers should be able to attach the exact sanitised document
                # evidence, not the generic search endpoint that discovered it.
                "source_url": document_url,
                "captured_at": observed_at,
                "known_at": observed_at,
                "effective_at": normalized.get("effective_at"),
                "first_seen_at": observed_at,
                "last_seen_at": observed_at,
            })
        return rows

    def _prior_last_good(self) -> str | None:
        return _sam_text(_sam_read_json(self.status_path).get("last_successful_observed_at"))

    def _write_status(self, status: dict) -> dict:
        _sam_atomic_json(status, self.status_path)
        return status

    def persist(self, incoming: list[dict], documents: list[dict], observed_at: str) -> dict:
        """Atomically write current, revision, and document ledgers after full reads succeed."""
        existing_current = _sam_read_parquet(self.opportunities_path, SAM_OPPORTUNITY_COLUMNS)
        existing_revisions = _sam_read_parquet(self.revisions_path, SAM_OPPORTUNITY_REVISION_COLUMNS)
        existing_documents = _sam_read_parquet(self.documents_path, SAM_OPPORTUNITY_DOCUMENT_COLUMNS)
        current, resolved = _sam_merge_current(existing_current, incoming, observed_at)
        revisions = _sam_merge_revisions(existing_revisions, resolved, observed_at)
        resolved_revision_ids = {row["notice_id"]: row["revision_id"] for row in resolved}
        for document in documents:
            document["revision_id"] = resolved_revision_ids.get(document["notice_id"], document.get("revision_id"))
        merged_documents = _sam_merge_documents(existing_documents, documents, observed_at)
        # Each file is materialized to a sibling temporary path before it replaces a
        # last-good artifact.  A failure during serialization therefore cannot leave
        # a truncated active ledger behind.
        _sam_atomic_parquet(current, self.opportunities_path)
        _sam_atomic_parquet(revisions, self.revisions_path)
        _sam_atomic_parquet(merged_documents, self.documents_path)
        return {
            "opportunities_seen": len(incoming),
            "opportunities_total": len(current),
            "revisions_seen": len(resolved),
            "revisions_total": len(revisions),
            "documents_seen": len(documents),
            "documents_total": len(merged_documents),
        }

    def collect(
        self,
        *,
        as_of: str | None = None,
        lookback_days: int = SAM_OPPORTUNITY_DEFAULT_LOOKBACK_DAYS,
        naics_codes: Iterable[str] | None = None,
        statuses: Iterable[str] = ("active", "archived"),
    ) -> dict:
        """Poll active/archive SAM notices, retain observed revisions, and report coverage.

        A partial query or document failure never deletes current artifacts or moves
        ``last_successful_observed_at`` forward.  Successfully fetched observations
        may still append evidence, but the health contract is explicitly partial.
        """
        if not self.api_key:
            raise RuntimeError("SAM_API_KEY not set")
        observed_at = datetime.now(timezone.utc).isoformat()
        try:
            end = (
                datetime.fromisoformat(str(as_of).replace("Z", "+00:00")).date()
                if as_of
                else datetime.now(timezone.utc).date()
            )
        except ValueError as exc:
            raise ValueError(f"invalid as_of date: {as_of}") from exc
        codes = sorted({str(code).strip() for code in (naics_codes or _naics_themes().keys()) if str(code).strip()})
        # A no-code call is valid and gives operators a deliberate broad-reconciliation
        # option.  The regular scheduled call uses the curated NAICS set.
        query_codes: list[str | None] = codes or [None]
        query_statuses = sorted({str(value).strip().lower() for value in statuses if str(value).strip()}) or ["active"]
        scope = (
            f"SAM.gov Opportunities v2, {len(codes) if codes else 'broad'} NAICS scope, "
            f"statuses={','.join(query_statuses)}, rolling {int(lookback_days)}d"
        )
        errors: list[dict] = []
        raw_rows: list[dict] = []
        pages_requested = 0
        pages_succeeded = 0
        truncated_queries = 0
        successful_queries = 0
        for start, window_end in self._date_windows(end, lookback_days):
            for code in query_codes:
                for status in query_statuses:
                    query = {
                        "postedFrom": start.strftime("%m/%d/%Y"),
                        "postedTo": window_end.strftime("%m/%d/%Y"),
                        "status": status,
                    }
                    if code:
                        query["ncode"] = code
                    try:
                        batch, meta = self._fetch_query(query)
                        raw_rows.extend(batch)
                        pages_requested += int(meta.get("pages_requested") or meta["pages"])
                        pages_succeeded += int(meta.get("pages_succeeded") or 0)
                        successful_queries += 1
                        if meta["truncated"]:
                            truncated_queries += 1
                            errors.append({
                                "stage": "pagination",
                                "naics_code": code,
                                "status": status,
                                "posted_from": query["postedFrom"],
                                "posted_to": query["postedTo"],
                                "reason": meta.get("incomplete_reason"),
                                "error": meta.get("error") or (
                                    "SAM shard ended without authoritative pagination exhaustion; "
                                    f"max_pages_per_query={self.max_pages_per_query}"
                                ),
                            })
                    except Exception as exc:  # noqa: BLE001 - individual shards fail soft
                        errors.append({
                            "stage": "search",
                            "naics_code": code,
                            "status": status,
                            "posted_from": query["postedFrom"],
                            "posted_to": query["postedTo"],
                            "error": _sam_safe_error(exc, self.api_key),
                        })
                    if self.request_pacing_seconds:
                        time.sleep(self.request_pacing_seconds)

        normalized: list[dict] = []
        for raw in raw_rows:
            try:
                normalized.append(normalize_opportunity(raw, observed_at))
            except Exception as exc:  # noqa: BLE001 - retain other source rows
                errors.append({"stage": "normalize", "error": _sam_safe_error(exc, self.api_key)})
        normalized, collisions = _sam_dedupe_incoming(normalized)
        errors.extend(collisions)
        document_budget = [0]
        documents: list[dict] = []
        by_notice_raw: dict[str, dict] = {}
        for raw in raw_rows:
            notice_id = _sam_text(raw.get("noticeId") if isinstance(raw, dict) else None)
            if notice_id and notice_id not in by_notice_raw:
                by_notice_raw[notice_id] = raw
        for row in normalized:
            raw = by_notice_raw.get(row["notice_id"])
            if raw:
                documents.extend(self._document_evidence(raw, row, observed_at, errors, document_budget))

        previous_last_good = self._prior_last_good()
        partial = bool(errors or truncated_queries)
        if successful_queries == 0 and errors:
            status = {
                "schema_version": SAM_OPPORTUNITY_STATUS_SCHEMA,
                "ledger_schema": SAM_OPPORTUNITY_SCHEMA,
                "source": SAM_OPPORTUNITY_SOURCE,
                "source_url": SEARCH_URL,
                "observed_at": observed_at,
                "status": "failed",
                "partial": True,
                "last_successful_observed_at": previous_last_good,
                "freshness": {
                    "state": "failed",
                    "target_poll_minutes": SAM_OPPORTUNITY_TARGET_POLL_MINUTES,
                    "last_good_at": previous_last_good,
                },
                "pages": {"requested": pages_requested, "succeeded": pages_succeeded, "truncated_queries": truncated_queries},
                "records": {"raw": len(raw_rows), "normalized": len(normalized), "documents": len(documents)},
                "errors": errors,
                "history_scope": "observed_latest_api_state_only",
                "pit_contract": "Filter opportunity_revisions.known_at <= cutoff before selecting latest notice state.",
                "scope": scope,
            }
            return self._write_status(status)

        try:
            totals = self.persist(normalized, documents, observed_at)
        except Exception as exc:  # noqa: BLE001 - preserve all last-good Parquets on persistence failure
            errors.append({"stage": "persist", "error": _sam_safe_error(exc, self.api_key)})
            status = {
                "schema_version": SAM_OPPORTUNITY_STATUS_SCHEMA,
                "ledger_schema": SAM_OPPORTUNITY_SCHEMA,
                "source": SAM_OPPORTUNITY_SOURCE,
                "source_url": SEARCH_URL,
                "observed_at": observed_at,
                "status": "failed",
                "partial": True,
                "last_successful_observed_at": previous_last_good,
                "freshness": {"state": "failed", "target_poll_minutes": SAM_OPPORTUNITY_TARGET_POLL_MINUTES, "last_good_at": previous_last_good},
                "pages": {"requested": pages_requested, "succeeded": pages_succeeded, "truncated_queries": truncated_queries},
                "records": {"raw": len(raw_rows), "normalized": len(normalized), "documents": len(documents)},
                "errors": errors,
                "history_scope": "observed_latest_api_state_only",
                "pit_contract": "Filter opportunity_revisions.known_at <= cutoff before selecting latest notice state.",
                "scope": scope,
            }
            return self._write_status(status)

        status_name = "partial" if partial else "ok"
        last_good = previous_last_good if partial else observed_at
        status = {
            "schema_version": SAM_OPPORTUNITY_STATUS_SCHEMA,
            "ledger_schema": SAM_OPPORTUNITY_SCHEMA,
            "source": SAM_OPPORTUNITY_SOURCE,
            "source_url": SEARCH_URL,
            "observed_at": observed_at,
            "as_of": end.isoformat(),
            "status": status_name,
            "partial": partial,
            "last_successful_observed_at": last_good,
            "freshness": {
                "state": "partial" if partial else "fresh",
                "target_poll_minutes": SAM_OPPORTUNITY_TARGET_POLL_MINUTES,
                "active_source_cadence": "daily per OpenGSA public API documentation",
                "archived_source_cadence": "weekly per OpenGSA public API documentation",
                "last_good_at": last_good,
            },
            "query_scope": {
                "naics_codes": codes,
                "statuses": query_statuses,
                "lookback_days": int(lookback_days),
                "date_windows": len(self._date_windows(end, lookback_days)),
            },
            "pagination": {"page_size": self.page_size, "max_pages_per_query": self.max_pages_per_query},
            "pages": {"requested": pages_requested, "succeeded": pages_succeeded, "truncated_queries": truncated_queries},
            "records": {"raw": len(raw_rows), "normalized": len(normalized), "documents": len(documents), **totals},
            "errors": errors,
            "history_scope": "observed_latest_api_state_only",
            "pit_contract": "Filter opportunity_revisions.known_at <= cutoff before selecting latest notice state.",
            "scope": scope,
        }
        return self._write_status(status)


def sam_opportunity_heartbeat_frame(status: dict) -> pd.DataFrame:
    """Make the composite-key SAM ledger visible to the standard adapter runner."""
    observed = pd.Timestamp(status["observed_at"])
    if observed.tzinfo is not None:
        observed = observed.tz_convert(None)
    row = {
        "opportunities_seen": float((status.get("records") or {}).get("opportunities_seen", 0)),
        "opportunities_total": float((status.get("records") or {}).get("opportunities_total", 0)),
        "revisions_total": float((status.get("records") or {}).get("revisions_total", 0)),
        "documents_total": float((status.get("records") or {}).get("documents_total", 0)),
        "partial": float(bool(status.get("partial"))),
        "errors": float(len(status.get("errors") or [])),
    }
    return pd.DataFrame([row], index=[observed.normalize()])


class SamGovOpportunitiesAdapter(Adapter):
    """Runner wrapper for the Government Revenue Foresight SAM composite ledgers."""

    name = "sam_gov_opportunities"
    group = "government_revenue"
    stale_after_days = 2

    def __init__(self) -> None:
        self.api_key = config.secret("SAM_API_KEY")
        if not self.api_key:
            self.expected_failure = "SAM_API_KEY not set"

    def stored_series(self) -> list[str]:
        return ["sam_opportunity_heartbeat"]

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        collector = SamGovOpportunityCollector(root=config.ROOT, api_key=self.api_key)
        status = collector.collect(lookback_days=364 if full_history else SAM_OPPORTUNITY_DEFAULT_LOOKBACK_DAYS)
        if status.get("status") == "failed":
            raise RuntimeError("SAM.gov opportunity collection failed; last-good ledgers retained")
        return {"sam_opportunity_heartbeat": sam_opportunity_heartbeat_frame(status)}

class SamGovAdapter(Adapter):
    name = "sam_gov"
    group = "sam_gov"
    stale_after_days = 10

    def __init__(self) -> None:
        self.api_key = config.secret("SAM_API_KEY")
        if not self.api_key:
            self.expected_failure = "SAM_API_KEY not set"

    def _search(self, naics: str, posted_from: str, posted_to: str) -> list[dict]:
        params = {"api_key": self.api_key, "ncode": naics, "limit": 1000,
                  "postedFrom": posted_from, "postedTo": posted_to}
        r = self.http_get(SEARCH_URL, params=params, retries=2, timeout=60)
        return (r.json() or {}).get("opportunitiesData", [])

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        if not self.api_key:
            raise RuntimeError("SAM_API_KEY not set")
        naics_map = _naics_themes()
        if not naics_map:
            raise ValueError("sam_gov: naics_themes.json missing or empty")
        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=RECENT_D + PRIOR_D + 10)
        pf, pt = start.strftime("%m/%d/%Y"), end.strftime("%m/%d/%Y")
        opps, errors = [], 0
        for naics in naics_map:
            try:
                opps.extend(self._search(naics, pf, pt))
                time.sleep(0.5)
            except Exception as e:  # noqa: BLE001
                if is_connection_error(e):
                    raise
                errors += 1
                log.debug("sam_gov NAICS %s: %s", naics, e)
                continue
        if not opps:
            raise RuntimeError(f"sam_gov: no opportunities ({len(naics_map)} NAICS, {errors} errors)")
        vel = velocity(opps, naics_map)
        if not vel.empty:
            p = config.data_dir() / "sam_gov" / "opp_velocity.parquet"
            p.parent.mkdir(parents=True, exist_ok=True)
            vel.to_parquet(p)
        # W0d: new-program detection — first-seen NAICS per basket; appends to program_ledger.
        # ledger_path doubles as the seen-set recovery source if naics_seen.json is lost.
        seen_path = config.data_dir() / "sam_gov" / "naics_seen.json"
        ledger_path = config.data_dir() / "theme_activity" / "program_ledger.parquet"
        np_events = new_programs(opps, naics_map, seen_path, ledger_path=ledger_path)
        if np_events:
            ledger_path.parent.mkdir(parents=True, exist_ok=True)
            new_df = pd.DataFrame(np_events)
            if ledger_path.exists():
                existing = pd.read_parquet(ledger_path)
                new_df = pd.concat([existing, new_df], ignore_index=True)
            new_df = new_df.drop_duplicates(subset=["basket_id", "naics_or_cfda"], keep="first")
            new_df.to_parquet(ledger_path, index=False)
            log.info("sam_gov: %d new NAICS programs detected", len(np_events))
        log.info("sam_gov: %d opportunities over %d NAICS -> %d baskets, %d errors",
                 len(opps), len(naics_map), len(vel), errors)
        ingest = pd.DataFrame({"opps": [len(opps)], "baskets": [len(vel)]},
                              index=[pd.Timestamp(end)])
        return {"sam_gov__ingest": ingest}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    SamGovAdapter().fetch()
