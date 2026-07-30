"""Detect official US macro release publication without advancing research ledgers.

This is the VPS publication edge for Release Radar.  It polls only when a tracked
release is due, records an official-source fingerprint, and emits the display-only
``release_publications.json`` sidecar.  It deliberately does *not* write ``data/``,
parse a value into the forecast scoreboard, or advance the forward ledger.  The
nightly pipeline remains the canonical vintage/revision and scoring writer.

Publication detection and canonical research ingestion remain separate on purpose:

* this watcher answers "has the source published?" within roughly one timer tick;
* deterministic official-source adapters attach verified display facts for
  FOMC, CPI, PPI, payrolls, GDP, PCE and initial claims;
* the nightly ALFRED/official-source reconciliation owns canonical actuals.

The first poll before a release seeds a baseline.  A post-release content change is
then a publication.  If the process starts after the scheduled time, publisher dates
and HTTP ``Last-Modified`` metadata provide a conservative cold-start recovery path.
Every network/source failure is represented in source health and never raises into
the rest of the live loop.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import logging
import os
import re
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from engine import event_calendar
from scripts import official_release_parsers

log = logging.getLogger("release_publications")

NY = ZoneInfo("America/New_York")
USER_AGENT = "Mastermind-Macro-Publication-Watcher/1.0 (+https://www.mastermind-x.com)"
POLL_BEFORE = timedelta(minutes=12)
POLL_AFTER = timedelta(hours=6)
EVENT_POLL_AFTER = {"FOMC": timedelta(hours=24)}
RESULT_EVENT_TYPES = frozenset({"FOMC", "CPI", "PPI", "NFP", "GDP", "PCE", "CLAIMS"})
EVENT_ALERT_RETENTION = {
    event_type: timedelta(days=7) for event_type in RESULT_EVENT_TYPES
}
UNRESOLVED_RETRY_INTERVAL_MIN = 15


@dataclass(frozen=True)
class SourceSpec:
    source_id: str
    event_types: tuple[str, ...]
    publisher: str
    url: str
    keywords: tuple[str, ...]
    event_scoped: bool = False
    actual_parser: str | None = None
    feed_kind: str | None = None
    follow_entry_link: bool = False


SOURCES: tuple[SourceSpec, ...] = (
    SourceSpec(
        "fed_fomc",
        ("FOMC",),
        "Board of Governors of the Federal Reserve System",
        (
            "https://www.federalreserve.gov/newsevents/pressreleases/"
            "monetary{date_compact}a.htm"
        ),
        ("federal open market committee", "target range", "federal funds rate"),
        event_scoped=True,
        actual_parser="fomc",
    ),
    SourceSpec(
        "bls_cpi",
        ("CPI",),
        "U.S. Bureau of Labor Statistics",
        "https://www.bls.gov/feed/cpi.rss",
        ("consumer price index", "cpi"),
        event_scoped=True,
        actual_parser="cpi",
        feed_kind="bls_cpi",
    ),
    SourceSpec(
        "bls_ppi",
        ("PPI",),
        "U.S. Bureau of Labor Statistics",
        "https://www.bls.gov/feed/ppi.rss",
        ("producer price index", "ppi"),
        event_scoped=True,
        actual_parser="ppi",
        feed_kind="bls_ppi",
    ),
    SourceSpec(
        "bls_employment",
        ("NFP",),
        "U.S. Bureau of Labor Statistics",
        "https://www.bls.gov/feed/empsit.rss",
        ("employment situation", "nonfarm"),
        event_scoped=True,
        actual_parser="nfp",
        feed_kind="bls_nfp",
    ),
    SourceSpec(
        "bea_gdp",
        ("GDP",),
        "U.S. Bureau of Economic Analysis",
        "https://apps.bea.gov/rss/rss.xml",
        ("gross domestic product", "gdp"),
        event_scoped=True,
        actual_parser="gdp",
        feed_kind="bea_gdp",
        follow_entry_link=True,
    ),
    SourceSpec(
        "bea_pce",
        ("PCE",),
        "U.S. Bureau of Economic Analysis",
        "https://apps.bea.gov/rss/rss.xml",
        ("personal income and outlays", "pce price index"),
        event_scoped=True,
        actual_parser="pce",
        feed_kind="bea_pce",
        follow_entry_link=True,
    ),
    SourceSpec(
        "dol_claims",
        ("CLAIMS",),
        "U.S. Department of Labor",
        "https://www.dol.gov/newsroom/releases/eta",
        ("unemployment insurance", "initial claims"),
        event_scoped=True,
        actual_parser="claims",
        feed_kind="dol_claims",
    ),
)


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write valid JSON by same-directory temp file + replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, separators=(",", ":"), ensure_ascii=False)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def scheduled_releases(day: date, horizon_days: int = 3) -> list[dict[str, Any]]:
    """Network-free release subset from the shared event-calendar source of truth."""
    end = day + timedelta(days=max(0, horizon_days))
    out: list[dict[str, Any]] = []
    for day_text, is_sep in event_calendar._FOMC:  # noqa: SLF001
        event_day = date.fromisoformat(day_text)
        if day <= event_day <= end:
            meta = event_calendar._META["FOMC"]  # noqa: SLF001
            out.append(
                {
                    "event_id": f"fomc:{day_text}",
                    "type": "FOMC",
                    "date": day_text,
                    "time_et": meta["time_et"],
                    "label": meta["label"],
                    "label_zh": meta["label_zh"],
                    "schedule_source": "federal_reserve",
                    "is_sep": is_sep,
                    "is_context_only": True,
                }
            )
    for event_type in ("CPI", "PPI", "NFP", "GDP", "PCE"):
        dates, source = event_calendar._scheduled_release_dates(  # noqa: SLF001
            event_type, day, end, use_fred=False
        )
        for event_day in dates:
            meta = event_calendar._META[event_type]  # noqa: SLF001
            out.append(
                {
                    "event_id": f"{event_type.lower()}:{event_day.isoformat()}",
                    "type": event_type,
                    "date": event_day.isoformat(),
                    "time_et": meta["time_et"],
                    "label": meta["label"],
                    "label_zh": meta["label_zh"],
                    "schedule_source": source,
                    "is_context_only": True,
                }
            )
    current = day
    while current <= end:
        if current.weekday() == 3:
            meta = event_calendar._META["CLAIMS"]  # noqa: SLF001
            out.append(
                {
                    "event_id": f"claims:{current.isoformat()}",
                    "type": "CLAIMS",
                    "date": current.isoformat(),
                    "time_et": meta["time_et"],
                    "label": meta["label"],
                    "label_zh": meta["label_zh"],
                    "schedule_source": "computed",
                    "is_context_only": True,
                }
            )
        current += timedelta(days=1)
    for row in out:
        hh, mm = (int(part) for part in str(row["time_et"]).split(":", 1))
        row["scheduled_at"] = datetime.combine(
            date.fromisoformat(str(row["date"])),
            time(hh, mm),
            NY,
        ).isoformat()
    return sorted(out, key=lambda row: (row["date"], row["time_et"], row["type"]))


def schedule_coverage(day: date, horizon_days: int = 140) -> dict[str, Any]:
    """Fail-visible guard against silent year-boundary schedule exhaustion."""
    rows = scheduled_releases(day, horizon_days=horizon_days)
    maximum_gap_days = {
        "FOMC": 130,
        "CPI": 45,
        "PPI": 45,
        "NFP": 45,
        "GDP": 45,
        "PCE": 45,
        "CLAIMS": 14,
    }
    next_by_type: dict[str, str | None] = {}
    missing: list[str] = []
    for event_type, maximum_gap in maximum_gap_days.items():
        dates = [
            date.fromisoformat(str(row["date"]))
            for row in rows
            if row.get("type") == event_type
            and date.fromisoformat(str(row["date"])) >= day
        ]
        next_day = min(dates) if dates else None
        next_by_type[event_type] = next_day.isoformat() if next_day else None
        if next_day is None or (next_day - day).days > maximum_gap:
            missing.append(event_type)
    return {
        "status": "ok" if not missing else "incomplete",
        "checked_from": day.isoformat(),
        "horizon_days": horizon_days,
        "next_by_type": next_by_type,
        "missing_or_too_distant": missing,
    }


def _event_at(event: dict[str, Any]) -> datetime:
    hh, mm = (int(part) for part in str(event["time_et"]).split(":", 1))
    return datetime.combine(date.fromisoformat(event["date"]), time(hh, mm), NY)


def _event_key(event: dict[str, Any]) -> str:
    """Canonical publication identity; never collapse distinct same-day events."""
    return str(
        event.get("event_id")
        or f"{event.get('type', 'event')}:{event.get('date', 'unknown')}"
    )


def _legacy_event_key(event: dict[str, Any]) -> str:
    return f"{event.get('type')}:{event.get('date')}"


def _publication_for(
    publications: dict[str, Any], event: dict[str, Any]
) -> dict[str, Any]:
    value = publications.get(_event_key(event))
    if not isinstance(value, dict):
        value = publications.get(_legacy_event_key(event))
    return dict(value) if isinstance(value, dict) else {}


def _migrate_publication_keys(
    publications: dict[str, Any], events: list[dict[str, Any]]
) -> dict[str, Any]:
    """Move v2 ``TYPE:date`` rows to stable event IDs without losing VPS state."""
    migrated = dict(publications)
    for event in events:
        canonical = _event_key(event)
        legacy = _legacy_event_key(event)
        if canonical not in migrated and legacy in migrated:
            migrated[canonical] = migrated[legacy]
        if canonical != legacy:
            migrated.pop(legacy, None)
    return migrated


def _poll_after(event: dict[str, Any]) -> timedelta:
    return EVENT_POLL_AFTER.get(str(event.get("type") or ""), POLL_AFTER)


def _alert_retention(event: dict[str, Any]) -> timedelta:
    return EVENT_ALERT_RETENTION.get(str(event.get("type") or ""), _poll_after(event))


def _parse_coverage_start(raw: Any, now: datetime) -> datetime:
    """Parse and safely clamp one persisted coverage boundary."""
    if isinstance(raw, str) and raw:
        try:
            parsed = datetime.fromisoformat(raw)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return min(parsed.astimezone(timezone.utc), now)
        except ValueError:
            pass
    return now


def _coverage_started_at_by_type(
    state: dict[str, Any],
    now: datetime,
) -> dict[str, datetime]:
    """Return when this state began covering each official release family.

    Per-family boundaries prevent a later adapter rollout from manufacturing
    historical SLA failures for its newly supported event type. State written
    before multi-release coverage has no marker, so that migration tick becomes
    the start for every currently supported family.
    """
    raw_by_type = state.get("coverage_started_at_by_type")
    if not isinstance(raw_by_type, dict):
        raw_by_type = {}
    legacy = state.get("coverage_started_at")
    return {
        event_type: _parse_coverage_start(
            raw_by_type.get(event_type, legacy),
            now,
        )
        for event_type in RESULT_EVENT_TYPES
    }


def _new_coverage_types(state: dict[str, Any]) -> set[str]:
    """Identify families initialized on this tick for immediate cold recovery."""
    raw_by_type = state.get("coverage_started_at_by_type")
    if not isinstance(raw_by_type, dict):
        raw_by_type = {}
    legacy = state.get("coverage_started_at")
    return {
        event_type
        for event_type in RESULT_EVENT_TYPES
        if event_type not in raw_by_type and not legacy
    }


def _retain_event(
    event: dict[str, Any],
    *,
    now_et: datetime,
    coverage_started_at: datetime,
    publication: dict[str, Any],
) -> bool:
    """Keep future rows, covered misses, and retained publication evidence."""
    event_day = date.fromisoformat(str(event["date"]))
    if event_day >= now_et.date():
        return True
    if event.get("type") not in RESULT_EVENT_TYPES:
        return False
    event_at = _event_at(event)
    elapsed = now_et - event_at
    if not (timedelta(0) <= elapsed <= _alert_retention(event)):
        return False
    if publication:
        return True
    # A new watcher may legitimately recover a release for 24 hours after its
    # embargo. Beyond that boundary, only emit a delayed alarm if this state
    # existed during the recovery window and was therefore accountable for it.
    recovery_deadline = event_at.astimezone(timezone.utc) + timedelta(hours=24)
    return coverage_started_at <= recovery_deadline


def active_events(events: list[dict[str, Any]], now: datetime) -> list[dict[str, Any]]:
    now_et = now.astimezone(NY)
    return [
        event
        for event in events
        if _event_at(event) - POLL_BEFORE <= now_et <= _event_at(event) + _poll_after(event)
    ]


def _fetch(spec: SourceSpec, prior: dict[str, Any], timeout: float) -> dict[str, Any]:
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/pdf;q=0.9,*/*;q=0.5"}
    if prior.get("etag"):
        headers["If-None-Match"] = str(prior["etag"])
    if prior.get("last_modified"):
        headers["If-Modified-Since"] = str(prior["last_modified"])
    request = urllib.request.Request(spec.url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(2_000_000)
            return {
                "status": int(getattr(response, "status", 200)),
                "body": body,
                "fingerprint": hashlib.sha256(body).hexdigest(),
                "etag": response.headers.get("ETag"),
                "last_modified": response.headers.get("Last-Modified"),
                "content_type": response.headers.get("Content-Type"),
            }
    except urllib.error.HTTPError as exc:
        if exc.code == 304:
            return {
                "status": 304,
                "body": b"",
                "fingerprint": prior.get("fingerprint"),
                "etag": prior.get("etag"),
                "last_modified": prior.get("last_modified"),
                "content_type": prior.get("content_type"),
            }
        raise


def _resolved_spec(spec: SourceSpec, event: dict[str, Any] | None) -> SourceSpec:
    if not event or "{" not in spec.url:
        return spec
    event_day = date.fromisoformat(str(event["date"]))
    return replace(
        spec,
        url=spec.url.format(
            date=event_day.isoformat(),
            date_compact=event_day.strftime("%Y%m%d"),
        ),
    )


def _html_text(body: bytes) -> str:
    decoded = body.decode("utf-8", errors="ignore")
    decoded = re.sub(
        r"<(?:script|style)\b[^>]*>.*?</(?:script|style)>",
        " ",
        decoded,
        flags=re.IGNORECASE | re.DOTALL,
    )
    decoded = re.sub(r"<[^>]+>", " ", decoded)
    decoded = html.unescape(decoded)
    decoded = decoded.replace("\u2011", "-").replace("\u2013", "-").replace("\u2014", "-")
    return re.sub(r"\s+", " ", decoded).strip()


def _mixed_number(value: str) -> float:
    token = value.strip().replace("\u2011", "-").replace("\u2013", "-")
    mixed = re.fullmatch(r"(\d+)-(\d+)/(\d+)", token)
    if mixed:
        whole, numerator, denominator = (int(part) for part in mixed.groups())
        if denominator == 0:
            raise ValueError("zero denominator")
        return whole + numerator / denominator
    fraction = re.fullmatch(r"(\d+)/(\d+)", token)
    if fraction:
        numerator, denominator = (int(part) for part in fraction.groups())
        if denominator == 0:
            raise ValueError("zero denominator")
        return numerator / denominator
    return float(token)


def parse_fomc_actual(body: bytes) -> dict[str, Any] | None:
    """Extract decision facts deterministically from an official FOMC statement."""
    text = _html_text(body)
    decision = re.search(
        r"decided to\s+(maintain|raise|lower)\s+the target range for the "
        r"federal funds rate\s+(?:at|to)\s+([0-9][0-9./-]*)\s+to\s+"
        r"([0-9][0-9./-]*)\s+percent",
        text,
        flags=re.IGNORECASE,
    )
    if not decision:
        return None
    verb, low_text, high_text = decision.groups()
    try:
        low = _mixed_number(low_text)
        high = _mixed_number(high_text)
    except ValueError:
        return None
    action = {"maintain": "hold", "raise": "hike", "lower": "cut"}[verb.lower()]

    vote_for = vote_against = None
    vote = re.search(
        r"approved the following statement for release by a\s+"
        r"(\d+)\s*-\s*(\d+)\s+vote",
        text,
        flags=re.IGNORECASE,
    )
    if vote:
        vote_for, vote_against = (int(value) for value in vote.groups())

    dissent_action = None
    dissent_basis_points = None
    dissent = re.search(
        r"preferred to\s+(raise|lower|maintain)\b",
        text,
        flags=re.IGNORECASE,
    )
    if dissent:
        dissent_action = {
            "raise": "hike",
            "lower": "cut",
            "maintain": "hold",
        }[dissent.group(1).lower()]
        dissent_size = re.search(
            r"preferred to\s+(?:raise|lower|maintain)\b[^.]*?"
            r"by\s+([0-9][0-9./-]*)\s+percentage point",
            text,
            flags=re.IGNORECASE,
        )
        if dissent_size:
            try:
                dissent_basis_points = round(_mixed_number(dissent_size.group(1)) * 100)
            except ValueError:
                dissent_basis_points = None

    action_en = {"hold": "holds", "hike": "raises", "cut": "cuts"}[action]
    action_zh = {"hold": "维持", "hike": "上调", "cut": "下调"}[action]
    range_text = f"{low:.2f}%–{high:.2f}%"
    headline_en = f"Fed {action_en} at {range_text}"
    headline_zh = f"美联储{action_zh}利率在 {range_text}"
    summary_en = headline_en + "."
    summary_zh = headline_zh + "。"
    if vote_for is not None and vote_against is not None:
        summary_en = f"{headline_en} on a {vote_for}–{vote_against} vote."
        summary_zh = f"{headline_zh}，表决结果为 {vote_for}–{vote_against}。"
    if dissent_action and dissent_basis_points:
        preference_en = {
            "hike": "a rate increase",
            "cut": "a rate cut",
            "hold": "no rate change",
        }[dissent_action]
        summary_en += (
            f" Dissenters preferred {preference_en} of "
            f"{dissent_basis_points} basis points."
        )
        preference_zh = {"hike": "加息", "cut": "降息", "hold": "维持利率"}[
            dissent_action
        ]
        summary_zh += f" 反对者倾向于{preference_zh} {dissent_basis_points} 个基点。"

    return {
        "kind": "policy_rate",
        "action": action,
        "target_low": low,
        "target_high": high,
        "unit": "percent",
        "vote_for": vote_for,
        "vote_against": vote_against,
        "dissent_preference": dissent_action,
        "dissent_basis_points": dissent_basis_points,
        "headline_en": headline_en,
        "headline_zh": headline_zh,
        "summary_en": summary_en,
        "summary_zh": summary_zh,
    }


def _parse_actual(spec: SourceSpec, body: bytes) -> dict[str, Any] | None:
    if spec.actual_parser == "fomc":
        return parse_fomc_actual(body)
    if spec.actual_parser:
        return official_release_parsers.parse_actual(spec.actual_parser, body)
    return None


def _date_markers(day: date) -> tuple[str, ...]:
    full = day.strftime("%B %d, %Y")
    full_plain = full.replace(" 0", " ")
    return (
        full.lower(),
        full_plain.lower(),
        day.strftime("%m/%d/%Y").lower(),
        day.isoformat().lower(),
    )


def _last_modified_is_day(value: str | None, day: date) -> bool:
    if not value:
        return False
    try:
        return parsedate_to_datetime(value).astimezone(NY).date() == day
    except (TypeError, ValueError, OverflowError):
        return False


def _last_modified_at(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value).astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError):
        return None


def _effective_release_at(
    document: dict[str, Any],
    event: dict[str, Any],
    publication: dict[str, Any],
) -> tuple[str | None, str]:
    """Use source time, but never display a pre-embargo feed timestamp."""
    observed_text = (
        document.get("source_released_at")
        or _last_modified_at(document.get("last_modified"))
        or publication.get("source_released_at")
    )
    scheduled_text = event.get("scheduled_at")
    try:
        scheduled = datetime.fromisoformat(str(scheduled_text)).astimezone(timezone.utc)
    except (TypeError, ValueError):
        scheduled = None
    try:
        observed = datetime.fromisoformat(
            str(observed_text).replace("Z", "+00:00")
        ).astimezone(timezone.utc)
    except (TypeError, ValueError):
        observed = None
    if scheduled is not None and (observed is None or observed < scheduled):
        return scheduled.isoformat(), "scheduled_embargo_floor"
    if observed is not None:
        return observed.isoformat(), "official_source"
    return None, "unknown"


def _body_looks_published(body: bytes, event: dict[str, Any], spec: SourceSpec) -> bool:
    if not body:
        return False
    text = _html_text(body).lower()
    dated = any(marker in text for marker in _date_markers(date.fromisoformat(event["date"])))
    relevant = any(keyword.lower() in text for keyword in spec.keywords)
    return dated and relevant


def _safe_official_document_url(value: Any) -> str | None:
    try:
        parsed = urlparse(str(value or ""))
    except ValueError:
        return None
    host = (parsed.hostname or "").lower()
    allowed = any(
        host == suffix or host.endswith(f".{suffix}")
        for suffix in ("bea.gov", "bls.gov", "dol.gov", "federalreserve.gov")
    )
    if parsed.scheme != "https" or not allowed:
        return None
    return parsed.geturl()


def _prepare_official_document(
    *,
    spec: SourceSpec,
    event: dict[str, Any],
    result: dict[str, Any],
    source_state: dict[str, Any],
    state_key: str,
    fetcher: Any,
    timeout: float,
    checked_at: str,
) -> tuple[dict[str, Any], bool, str | None]:
    """Resolve an exact dated feed entry and, for BEA, its permanent release page.

    Returns ``(document, publication_evidence, detail_error)``. Feed-wide changes
    never count as evidence for a particular event: the entry selector must match
    the expected official release date first.
    """
    if not spec.feed_kind:
        evidence = _body_looks_published(result.get("body") or b"", event, spec)
        return dict(result), evidence, None

    entry = official_release_parsers.extract_feed_entry(
        spec.feed_kind,
        result.get("body") or b"",
        str(event["date"]),
    )
    if not entry:
        return dict(result), False, None

    entry_body = entry.get("body") or b""
    if isinstance(entry_body, str):
        entry_body = entry_body.encode("utf-8")
    source_url = _safe_official_document_url(entry.get("source_url")) or spec.url
    document = {
        **result,
        "body": entry_body,
        "fingerprint": hashlib.sha256(entry_body).hexdigest(),
        "source_url": source_url,
        "source_released_at": entry.get("source_released_at"),
        "reference_period": entry.get("reference_period"),
        "feed_entry_title": entry.get("title"),
    }
    if not spec.follow_entry_link:
        return document, True, None

    detail_url = _safe_official_document_url(entry.get("source_url"))
    if not detail_url:
        return document, True, "UnsafeFeedLink"
    detail_key = f"{state_key}:document"
    detail_prior = dict(source_state.get(detail_key) or {})
    detail_spec = replace(
        spec,
        url=detail_url,
        feed_kind=None,
        follow_entry_link=False,
    )
    try:
        detail = fetcher(detail_spec, detail_prior, timeout)
        if detail.get("status") == 304:
            # An unresolved parser needs bytes, not only a validator.
            detail = fetcher(detail_spec, {}, timeout)
        source_state[detail_key] = {
            "fingerprint": detail.get("fingerprint"),
            "etag": detail.get("etag"),
            "last_modified": detail.get("last_modified"),
            "content_type": detail.get("content_type"),
            "checked_at": checked_at,
            "source_url": detail_url,
        }
        document.update(detail)
        document["source_url"] = detail_url
        document["source_released_at"] = entry.get("source_released_at")
        document["reference_period"] = entry.get("reference_period")
        document["feed_entry_title"] = entry.get("title")
        return document, True, None
    except Exception as exc:  # noqa: BLE001 - retain exact feed publication evidence
        return document, True, type(exc).__name__


def detect(
    *,
    now: datetime,
    state: dict[str, Any],
    fetcher=_fetch,
    timeout: float = 8.0,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run one detection tick; pure apart from the injected HTTP fetcher."""
    now = now.astimezone(timezone.utc)
    now_et = now.astimezone(NY)
    today_et = now_et.date()
    candidates = scheduled_releases(today_et - timedelta(days=7), horizon_days=14)
    source_state = dict(state.get("sources") or {})
    publications = _migrate_publication_keys(
        dict(state.get("publications") or {}),
        candidates,
    )
    coverage_started_at_by_type = _coverage_started_at_by_type(state, now)
    new_coverage_types = _new_coverage_types(state)
    events = [
        event
        for event in candidates
        if _retain_event(
            event,
            now_et=now_et,
            coverage_started_at=coverage_started_at_by_type.get(
                str(event.get("type") or ""),
                now,
            ),
            publication=_publication_for(publications, event),
        )
    ]
    due = active_events(events, now)
    # Past the high-frequency window, keep every unresolved result-capable row
    # visible and retry at low frequency. A parser hotfix can therefore self-heal
    # CPI/GDP/PCE/payrolls/claims just as it can an FOMC statement.
    periodic_retry = (
        int(now.timestamp() // 60) % UNRESOLVED_RETRY_INTERVAL_MIN == 0
    )
    if periodic_retry or new_coverage_types:
        due_keys = {_event_key(event) for event in due}
        for event in events:
            if not periodic_retry and event.get("type") not in new_coverage_types:
                continue
            event_key = _event_key(event)
            publication = _publication_for(publications, event)
            elapsed = now_et - _event_at(event)
            unresolved = (
                publication.get("status") == "published_unparsed"
                or (
                    not publication
                    and timedelta(0) <= elapsed <= timedelta(hours=24)
                )
            )
            past_fast_window = now_et > _event_at(event) + _poll_after(event)
            if (
                event["type"] in RESULT_EVENT_TYPES
                and unresolved
                and past_fast_window
                and event_key not in due_keys
            ):
                due.append(event)
                due_keys.add(event_key)
    health: list[dict[str, Any]] = []
    feed_fetch_cache: dict[tuple[str, str, str], dict[str, Any]] = {}

    def fetch_primary(
        source: SourceSpec,
        prior_state: dict[str, Any],
    ) -> dict[str, Any]:
        if not source.feed_kind:
            return fetcher(source, prior_state, timeout)
        cache_key = (
            source.url,
            str(prior_state.get("etag") or ""),
            str(prior_state.get("last_modified") or ""),
        )
        if cache_key not in feed_fetch_cache:
            feed_fetch_cache[cache_key] = fetcher(source, prior_state, timeout)
        return dict(feed_fetch_cache[cache_key])

    for spec in SOURCES:
        matching = [event for event in due if event["type"] in spec.event_types]
        if not matching:
            continue
        work_items = (
            [(event, [event]) for event in matching]
            if spec.event_scoped
            else [(None, matching)]
        )
        for scoped_event, scoped_matching in work_items:
            resolved = _resolved_spec(spec, scoped_event)
            state_key = spec.source_id
            if scoped_event is not None:
                state_key += f":{_event_key(scoped_event)}"
            legacy_state_key = spec.source_id
            if scoped_event is not None:
                legacy_state_key += (
                    f":{scoped_event['type']}:{scoped_event['date']}"
                )
            prior = dict(
                source_state.get(state_key)
                or source_state.get(legacy_state_key)
                or {}
            )
            try:
                result = fetch_primary(resolved, prior)
                # A statement can become visible seconds before the scheduled
                # time.  That seed request stores validators, so the first
                # post-time request will normally be a 304 with no body.  The
                # deterministic parser still needs bytes before we can promote
                # the event.  Retry once without validators while a parser-backed
                # event is unresolved; this also lets a deployed parser fix
                # recover an existing ``published_unparsed`` row.
                needs_parser_body = bool(resolved.actual_parser) and any(
                    now_et >= _event_at(event)
                    and not bool(
                        _publication_for(publications, event).get("data_ready")
                    )
                    for event in scoped_matching
                )
                if result.get("status") == 304 and needs_parser_body:
                    result = fetch_primary(resolved, {})
                changed = bool(
                    prior.get("fingerprint")
                    and result.get("fingerprint")
                    and prior["fingerprint"] != result["fingerprint"]
                )
                source_state[state_key] = {
                    "fingerprint": result.get("fingerprint"),
                    "etag": result.get("etag"),
                    "last_modified": result.get("last_modified"),
                    "content_type": result.get("content_type"),
                    "checked_at": now.isoformat(),
                    "source_url": resolved.url,
                }
                if legacy_state_key != state_key:
                    source_state.pop(legacy_state_key, None)
                detail_errors: list[str] = []
                document_urls: list[str] = []
                for event in scoped_matching:
                    event_key = _event_key(event)
                    release_time = _event_at(event)
                    after_release = now.astimezone(NY) >= release_time
                    document, publication_evidence, detail_error = (
                        _prepare_official_document(
                            spec=resolved,
                            event=event,
                            result=result,
                            source_state=source_state,
                            state_key=state_key,
                            fetcher=fetcher,
                            timeout=timeout,
                            checked_at=now.isoformat(),
                        )
                    )
                    if detail_error:
                        detail_errors.append(detail_error)
                    document_url = str(document.get("source_url") or resolved.url)
                    document_urls.append(document_url)
                    publication = _publication_for(publications, event)
                    already_detected = bool(publication)
                    actual = _parse_actual(
                        resolved,
                        document.get("body") or b"",
                    )
                    if not after_release or not (
                        publication_evidence
                        or actual is not None
                        or already_detected
                    ):
                        continue
                    has_verified_actual = bool(actual) or bool(
                        publication.get("data_ready") and publication.get("actual")
                    )
                    publication_status = (
                        "published"
                        if has_verified_actual
                        else "published_unparsed"
                    )
                    source_released_at, source_time_basis = _effective_release_at(
                        document,
                        event,
                        publication,
                    )
                    official_url = (
                        document_url
                        if publication_evidence or actual
                        else str(publication.get("source_url") or document_url)
                    )
                    publication.update(
                        {
                            **event,
                            "status": publication_status,
                            "detected_at": publication.get("detected_at")
                            or now.isoformat(),
                            "first_seen_at": publication.get("first_seen_at")
                            or publication.get("detected_at")
                            or now.isoformat(),
                            "observed_at": publication.get("observed_at")
                            or now.isoformat(),
                            "official_embargo_at": event.get("scheduled_at"),
                            "source_released_at": source_released_at,
                            "source_time_basis": source_time_basis,
                            "publisher": resolved.publisher,
                            "source_id": resolved.source_id,
                            "source_url": official_url,
                            "content_sha256": document.get("fingerprint")
                            or publication.get("content_sha256"),
                            "source_sha256": document.get("fingerprint")
                            or publication.get("source_sha256"),
                            "data_ready": has_verified_actual,
                            "is_context_only": True,
                            "reference_period": (
                                document.get("reference_period")
                                or (actual or {}).get("reference_period")
                                or publication.get("reference_period")
                            ),
                            "note": (
                                "Verified official facts are live. Canonical vintage "
                                "and forward-ledger scoring reconcile nightly."
                                if has_verified_actual
                                else "Official publication detected; verified values "
                                "are still being extracted. Canonical scoring "
                                "reconciles nightly."
                            ),
                        }
                    )
                    if resolved.actual_parser:
                        publication["parser"] = {
                            "name": str(resolved.actual_parser),
                            "version": 1,
                        }
                    if actual:
                        publication["actual"] = {
                            **actual,
                            "source_url": official_url,
                        }
                        publication["verified_at"] = now.isoformat()
                    publications[event_key] = publication
                health.append(
                    {
                        "source_id": resolved.source_id,
                        "event_id": (
                            scoped_event.get("event_id") if scoped_event else None
                        ),
                        "status": "error"
                        if detail_errors
                        else (
                            "not_modified"
                            if result.get("status") == 304
                            else "ok"
                        ),
                        "http_status": result.get("status"),
                        "changed": changed,
                        "document_urls": sorted(set(document_urls)),
                        **(
                            {"error": detail_errors[0]}
                            if detail_errors
                            else {}
                        ),
                    }
                )
            except Exception as exc:  # noqa: BLE001 - source failure is display health
                log.warning(
                    "source %s failed for %s: %s: %s",
                    resolved.source_id,
                    scoped_event.get("event_id") if scoped_event else "shared",
                    type(exc).__name__,
                    exc,
                )
                health.append(
                    {
                        "source_id": resolved.source_id,
                        "event_id": (
                            scoped_event.get("event_id") if scoped_event else None
                        ),
                        "status": "error",
                        # This sidecar is public. Full diagnostics stay in the
                        # systemd journal; the browser receives only a coarse code.
                        "error": type(exc).__name__,
                    }
                )

    lifecycle: list[dict[str, Any]] = []
    for event in events:
        event_at = _event_at(event)
        publication = _publication_for(publications, event)
        row = dict(event)
        if publication:
            row.update(publication)
        elif now_et < event_at - POLL_BEFORE:
            row["status"] = "scheduled"
        elif now_et < event_at:
            row["status"] = "watching"
        elif now_et <= event_at + _poll_after(event):
            row["status"] = "awaiting_publication"
        else:
            row["status"] = "verification_delayed"
        lifecycle.append(row)

    new_state = {
        "schema": "release_publication_state.v2",
        "coverage_started_at_by_type": {
            event_type: started_at.isoformat()
            for event_type, started_at in sorted(
                coverage_started_at_by_type.items()
            )
        },
        "sources": source_state,
        "publications": publications,
        "updated_at": now.isoformat(),
    }
    sorted_publications = sorted(
        publications.values(), key=lambda row: (row.get("date", ""), row.get("type", ""))
    )
    display_publications = sorted_publications[-20:]
    display_keys = {_event_key(row) for row in display_publications}
    for publication in sorted_publications:
        key = _event_key(publication)
        if publication.get("status") == "published_unparsed" and key not in display_keys:
            display_publications.append(publication)
            display_keys.add(key)

    payload = {
        "schema": "release_publications.v2",
        "built": now.isoformat(),
        "as_of_et": now_et.isoformat(),
        "coverage_started_at_by_type": {
            event_type: started_at.isoformat()
            for event_type, started_at in sorted(
                coverage_started_at_by_type.items()
            )
        },
        "timezone": "America/New_York",
        "poll_window": {
            "before_min": 12,
            "after_min": 360,
            "per_type_after_min": {
                event_type: round(_poll_after({"type": event_type}).total_seconds() / 60)
                for event_type in sorted(RESULT_EVENT_TYPES)
            },
            "unresolved_retention_min": {
                event_type: round(
                    EVENT_ALERT_RETENTION[event_type].total_seconds() / 60
                )
                for event_type in sorted(RESULT_EVENT_TYPES)
            },
        },
        "due": due,
        "events": lifecycle,
        # Compatibility field for older clients: unlike the old raw schedule,
        # this now means genuinely upcoming (including the pre-time watch state).
        "upcoming": [
            row
            for row in lifecycle
            if row.get("status") in ("scheduled", "watching")
        ],
        "publications": display_publications,
        "source_health": health,
        "schedule_coverage": schedule_coverage(today_et),
        "canonical_reconciliation": "nightly",
        "is_context_only": True,
    }
    return new_state, payload


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="display-only JSON sidecar path")
    parser.add_argument("--state-dir", required=True, help="durable VPS state directory")
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument("--now", default=None, help="test override: ISO-8601 timestamp")
    args = parser.parse_args()

    state_dir = Path(args.state_dir)
    state_path = state_dir / "release_publications_state.json"
    state = _load_json(state_path)
    now = datetime.fromisoformat(args.now) if args.now else datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    new_state, payload = detect(now=now, state=state, timeout=args.timeout)
    atomic_write_json(state_path, new_state)
    atomic_write_json(Path(args.out), payload)
    log.info(
        "wrote %s — due=%d published=%d sources=%d",
        args.out,
        len(payload["due"]),
        len(payload["publications"]),
        len(payload["source_health"]),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
