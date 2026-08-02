"""Small, dependency-free contracts for Company Intelligence artifacts.

The artifacts are deliberately JSON rather than an inference product: the
contract makes the context-only boundary inspectable by every consumer.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from hashlib import sha256
import json
import math
from pathlib import Path
import re
from typing import Any, Mapping
from urllib.parse import urlparse


CONTEXT_SCHEMA = "company_intelligence_context.v1"
MANIFEST_SCHEMA = "company_intelligence_manifest.v1"
AUTHORITY = "context_only"
_TICKER_RE = re.compile(r"^[A-Z0-9](?:[A-Z0-9.-]{0,14}[A-Z0-9])?$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GENERATION_RE = re.compile(r"^[0-9a-f]{24,64}$")
_SOURCE_REF_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
_TAG_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,95}$")
_INTERNAL_TX_RE = re.compile(r"^/data/tx/[A-Z0-9](?:[A-Z0-9.-]{0,14}[A-Z0-9])?/\d{4}Q[1-4]\.json\.gz$")

# This is a *public* wire contract, not merely a guide for producers.  Keep
# the names here instead of accepting a producer's arbitrary mapping: the
# object is eventually supplied to a language model, so unknown fields are an
# input-boundary violation rather than harmless future compatibility.
PUBLIC_METRICS = frozenset({
    "sentiment",
    "performance",
    "confidence",
    "combined",
    "call_positivity",
    "management_confidence",
    "analyst_criticism",
    "future_outlook",
    "revenue_growth_pct",
    "eps_growth_pct",
    "gross_margin_pct",
    "analysts_count",
    "questions_count",
})
_CONTEXT_KEYS = frozenset({
    "schema", "authority", "generated_at", "generation_id", "company",
    "status", "latest_event_id", "latest_event", "history", "topics",
    "source_completeness", "warnings", "missing_sources", "transport_lineage",
})
_COMPANY_KEYS = frozenset({"ticker", "display_name", "exchange"})
_EVENT_KEYS = frozenset({
    "event_id", "ticker", "fiscal_year", "fiscal_quarter", "call_date",
    "summary", "highlights", "positive_highlights", "negative_highlights",
    "key_quote", "tags", "metrics", "field_lineage", "previous_event_deltas",
    "sources", "claim_citations_pending",
})
_SOURCE_KEYS = frozenset({"source_ref", "kind", "status", "citation_precision", "url", "receipt"})
_TOPICS_KEYS = frozenset({"timeline", "added", "dropped", "persistent"})
_TOPIC_TIMELINE_KEYS = frozenset({"tag", "first_event_id", "last_event_id", "event_count", "status"})
_COMPLETENESS_KEYS = frozenset({"earnings_history", "score_overlay", "transcripts"})
_COMPLETENESS_BLOCK_KEYS = frozenset({"status", "event_count"})
_TRANSPORT_LINEAGE_KEYS = frozenset({"earnings_manifest", "tx_index", "builder"})
_SOURCE_LINEAGE_BASE_KEYS = frozenset({"generation_id", "sha256"})
_MANIFEST_KEYS = frozenset({
    "schema", "generation_id", "generated_at", "company_count", "event_count",
    "latest_event_date", "source", "files", "status", "warnings", "operational",
})
_MANIFEST_SOURCE_KEYS = frozenset({"earnings_manifest", "tx_index"})
_MANIFEST_FILE_KEYS = frozenset({"sha256", "bytes"})
_MANIFEST_OPERATIONAL_KEYS = frozenset({"history_rows_rejected"})
_MANIFEST_TX_SOURCE_KEYS = _SOURCE_LINEAGE_BASE_KEYS | frozenset({"schema"})
_MANIFEST_EARNINGS_SOURCE_KEYS = _SOURCE_LINEAGE_BASE_KEYS | frozenset({"observed_counts"})
_OBSERVED_COUNT_KEYS = frozenset({"history_rows", "history_tickers", "score_rows", "score_tickers"})
_KNOWN_WARNINGS = frozenset({
    "earnings_history_missing",
    "earnings_history_metadata_only",
    "earnings_history_partial",
    "tx_index_missing_or_invalid",
    "transcripts_partial",
    "freshness_reference_missing",
})
_KNOWN_MISSING_SOURCES = frozenset({
    "earnings_history",
    "earnings_history_raw_source",
    "earnings_history_raw_source_for_some_events",
    "terminal_transcript_index",
    "transcripts_for_some_events",
})
_TEXT_LIMITS = {
    "summary": 4_000,
    "key_quote": 4_000,
    "highlight": 1_200,
    "display_name": 240,
    "exchange": 64,
}
_MAX_METRIC_ABS = 2_000_000_000
_MANIFEST_WARNING_RE = re.compile(r"^history_rows_rejected:[1-9]\d*$")
_KNOWN_MANIFEST_WARNINGS = _KNOWN_WARNINGS | frozenset({"upstream_timeout"})


class ContractError(ValueError):
    """Raised when a producer or artifact violates the public contract."""


def safe_ticker(value: object) -> str:
    """Return an uppercase ticker safe to use as a single filename component.

    Dots and dashes are preserved for ordinary listed symbols, but every path
    separator and the ambiguous ``..`` sequence is refused instead of cleaned.
    Cleaning would make a malicious/source-bad symbol silently address another
    company's immutable object.
    """
    ticker = str(value or "").strip().upper()
    if (
        not ticker
        or "/" in ticker
        or "\\" in ticker
        or ".." in ticker
        or not _TICKER_RE.fullmatch(ticker)
    ):
        raise ContractError(f"unsafe ticker: {value!r}")
    return ticker


def canonical_json_bytes(payload: object) -> bytes:
    """Encode JSON deterministically and reject non-finite numeric values."""
    try:
        return (
            json.dumps(
                payload,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
            + b"\n"
        )
    except (TypeError, ValueError) as exc:
        raise ContractError(f"payload is not canonical JSON: {exc}") from exc


def canonical_json_sha256(payload: object) -> str:
    return sha256(canonical_json_bytes(payload)).hexdigest()


def bytes_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_date(value: object, *, field: str) -> date:
    """Parse a date or ISO timestamp without accepting a guessed format."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        raise ContractError(f"{field} is required")
    try:
        return date.fromisoformat(text[:10])
    except ValueError as exc:
        raise ContractError(f"{field} must be ISO date: {value!r}") from exc


def normalize_quarter(value: object) -> int:
    text = str(value or "").strip().upper()
    if text.startswith("Q"):
        text = text[1:]
    try:
        quarter = int(text)
    except (TypeError, ValueError) as exc:
        raise ContractError(f"invalid fiscal quarter: {value!r}") from exc
    if quarter not in (1, 2, 3, 4):
        raise ContractError(f"invalid fiscal quarter: {value!r}")
    return quarter


def normalize_year(value: object) -> int:
    try:
        year = int(value)
    except (TypeError, ValueError) as exc:
        raise ContractError(f"invalid fiscal year: {value!r}") from exc
    # Match the Terminal reader's accepted fiscal period range.  Producing a
    # broader year would create a valid-looking immutable object it refuses.
    if not 2000 <= year <= 2100:
        raise ContractError(f"invalid fiscal year: {value!r}")
    return year


def event_key(
    ticker: object,
    fiscal_year: object,
    fiscal_quarter: object,
    call_date: object | None = None,
) -> str:
    """Return the correction-stable identity of one fiscal earnings event.

    ``call_date`` remains an accepted (but deliberately unused) fourth argument
    for source compatibility.  A provider can correct the calendar date after a
    call without creating a second logical Q1 event or breaking deep links.
    """
    symbol = safe_ticker(ticker)
    year = normalize_year(fiscal_year)
    quarter = normalize_quarter(fiscal_quarter)
    return f"{symbol}|{year}|Q{quarter}"


def stable_event_id(
    ticker: object,
    fiscal_year: object,
    fiscal_quarter: object,
    call_date: object | None = None,
) -> str:
    """A content-independent event id retained when a source corrects its row."""
    return "cie_" + sha256(
        event_key(ticker, fiscal_year, fiscal_quarter, call_date).encode("utf-8")
    ).hexdigest()[:24]


def iso_timestamp(value: object | None) -> str | None:
    """Normalize an ISO-ish input to a deterministic UTC timestamp string."""
    if value is None or str(value).strip() == "":
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, datetime.min.time(), tzinfo=timezone.utc)
    else:
        text = str(value).strip()
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            # A source with a date-only freshness field is still exact enough to
            # describe as midnight UTC; arbitrary locale formats are absent,
            # rather than an identity error that should abort the projection.
            try:
                parsed = datetime.combine(parse_date(text, field="timestamp"), datetime.min.time())
            except ContractError:
                return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    else:
        parsed = parsed.astimezone(timezone.utc)
    return parsed.isoformat(timespec="seconds").replace("+00:00", "Z")


def finite_number(value: object) -> float | int | None:
    """Accept source numeric fields only; preserve missing or malformed as null."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or abs(number) > 1_000_000_000:
        return None
    if number.is_integer():
        return int(number)
    return number


def company_filename(ticker: object) -> str:
    return f"companies/{safe_ticker(ticker)}.json"


def _require_mapping(payload: object, *, name: str) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        raise ContractError(f"{name} must be an object")
    return payload


def _require_exact_keys(payload: Mapping[str, Any], expected: frozenset[str], *, name: str) -> None:
    """Refuse both missing and unrecognised keys at this public boundary."""
    actual = set(payload)
    if actual != expected:
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        details = []
        if missing:
            details.append(f"missing={missing}")
        if unexpected:
            details.append(f"unsupported={unexpected}")
        raise ContractError(f"{name} fields mismatch ({', '.join(details)})")


def _require_text(value: object, *, field: str, limit: int, allow_null: bool = True) -> None:
    if value is None and allow_null:
        return
    if not isinstance(value, str) or not value or len(value) > limit or "\x00" in value:
        raise ContractError(f"{field} invalid")


def _require_metric(value: object, *, field: str) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractError(f"{field} must be a finite number or null")
    if not math.isfinite(value) or abs(value) > _MAX_METRIC_ABS:
        raise ContractError(f"{field} must be a bounded finite number or null")


def _require_sha(value: object, *, field: str) -> None:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ContractError(f"{field} must be sha256 hex")


def is_safe_source_url(value: object) -> bool:
    """Return whether a source URL is safe for the terminal to render/fetch."""
    if not isinstance(value, str) or not value or len(value) > 2_048 or re.search(r"[\\\r\n]", value):
        return False
    if _INTERNAL_TX_RE.fullmatch(value):
        return True
    parsed = urlparse(value)
    return (
        parsed.scheme == "https"
        and bool(parsed.netloc)
        and parsed.username is None
        and parsed.password is None
    )


def _validate_source(source: object, *, name: str) -> str:
    item = _require_mapping(source, name=name)
    _require_exact_keys(item, _SOURCE_KEYS, name=name)
    source_ref = item.get("source_ref")
    if not isinstance(source_ref, str) or not _SOURCE_REF_RE.fullmatch(source_ref):
        raise ContractError(f"{name}.source_ref invalid")
    if item.get("kind") not in {"earnings_history", "score_overlay", "transcript"}:
        raise ContractError(f"{name}.kind invalid")
    if source_ref != item.get("kind"):
        raise ContractError(f"{name}.source_ref must match kind")
    if item.get("status") not in {"present", "metadata_only", "missing"}:
        raise ContractError(f"{name}.status invalid")
    if item.get("citation_precision") not in {"document", "metadata"}:
        raise ContractError(f"{name}.citation_precision invalid")
    url = item.get("url")
    if url is not None and not is_safe_source_url(url):
        raise ContractError(f"{name}.url unsafe")
    if item.get("status") == "present" and url is None:
        raise ContractError(f"{name}.present requires a URL")
    if item.get("status") != "present" and url is not None:
        raise ContractError(f"{name}.non-present cannot carry a URL")
    receipt = item.get("receipt")
    if receipt is not None:
        receipt_map = _require_mapping(receipt, name=f"{name}.receipt")
        if "source_hash" in receipt_map:
            _require_sha(receipt_map.get("source_hash"), field=f"{name}.receipt.source_hash")
        if "source_date" in receipt_map and iso_timestamp(receipt_map.get("source_date")) is None:
            raise ContractError(f"{name}.receipt.source_date invalid")
        if "record_id" in receipt_map:
            record_id = receipt_map.get("record_id")
            if not isinstance(record_id, str) or not 1 <= len(record_id) <= 160:
                raise ContractError(f"{name}.receipt.record_id invalid")
        unknown = set(receipt_map) - {"source_hash", "source_date", "record_id"}
        if unknown:
            raise ContractError(f"{name}.receipt has unsupported fields")
    return source_ref


def _validate_event_lineage(event: Mapping[str, Any], source_refs: set[str]) -> None:
    lineage = _require_mapping(event.get("field_lineage"), name="event.field_lineage")
    if set(lineage) != {"summary", "key_quote", "metrics", "positive_highlights", "negative_highlights", "highlights", "tags"}:
        raise ContractError("event.field_lineage fields mismatch")

    def require_ref(value: object, *, field: str, allow_null: bool = True) -> None:
        if value is None and allow_null:
            return
        if not isinstance(value, str) or value not in source_refs:
            raise ContractError(f"event.field_lineage.{field} must reference event.sources")

    def require_exact_ref(value: object, source_ref: object, *, field: str) -> None:
        if (value is None) != (source_ref is None):
            raise ContractError(f"event.field_lineage.{field} must be null iff the value is null")
        require_ref(source_ref, field=field)

    require_exact_ref(event.get("summary"), lineage.get("summary"), field="summary")
    require_exact_ref(event.get("key_quote"), lineage.get("key_quote"), field="key_quote")
    metrics = _require_mapping(lineage.get("metrics"), name="event.field_lineage.metrics")
    event_metrics = _require_mapping(event.get("metrics"), name="event.metrics")
    if set(metrics) != set(event_metrics):
        raise ContractError("event.field_lineage.metrics fields mismatch")
    for metric, source_ref in metrics.items():
        require_exact_ref(event_metrics.get(metric), source_ref, field=f"metrics.{metric}")

    for field in ("positive_highlights", "negative_highlights", "highlights"):
        values = event.get(field)
        refs = lineage.get(field)
        if not isinstance(values, list) or not isinstance(refs, list) or len(values) != len(refs):
            raise ContractError(f"event.field_lineage.{field} must align with values")
        for index, source_ref in enumerate(refs):
            require_ref(source_ref, field=f"{field}[{index}]", allow_null=False)

    tags = event.get("tags")
    tag_refs = _require_mapping(lineage.get("tags"), name="event.field_lineage.tags")
    if not isinstance(tags, list) or set(tag_refs) != set(tags):
        raise ContractError("event.field_lineage.tags must align with tags")
    for tag, source_ref in tag_refs.items():
        require_ref(source_ref, field=f"tags.{tag}", allow_null=False)


def validate_context(payload: object) -> None:
    """Validate the closed, bounded public context schema.

    The reader feeds this object into Brain.  It must therefore reject unknown
    structure instead of treating it as benign forward-compatible metadata.
    Additive evolution belongs in a new schema version with a new reader.
    """
    item = _require_mapping(payload, name="context")
    _require_exact_keys(item, _CONTEXT_KEYS, name="context")
    if item.get("schema") != CONTEXT_SCHEMA:
        raise ContractError("context schema mismatch")
    if item.get("authority") != AUTHORITY:
        raise ContractError("company intelligence must remain context_only")
    if not _GENERATION_RE.fullmatch(str(item.get("generation_id") or "")):
        raise ContractError("invalid context generation_id")
    if iso_timestamp(item.get("generated_at")) is None:
        raise ContractError("context generated_at missing")
    company = _require_mapping(item.get("company"), name="company")
    _require_exact_keys(company, _COMPANY_KEYS, name="company")
    ticker = safe_ticker(company.get("ticker"))
    _require_text(company.get("display_name"), field="company.display_name", limit=_TEXT_LIMITS["display_name"], allow_null=False)
    # Exchange is intentionally not sourced by v1; keeping it exactly null
    # prevents a display-oriented upstream label from becoming a company fact.
    if company.get("exchange") is not None:
        raise ContractError("company.exchange must remain null in v1")
    if item.get("status") not in {"ready", "partial", "stale", "not_covered"}:
        raise ContractError("invalid context status")
    history = item.get("history")
    if not isinstance(history, list) or len(history) > 12:
        raise ContractError("history must be a list of at most 12 events")
    ids: set[str] = set()
    previous_date: date | None = None
    for event in history:
        event_map = _require_mapping(event, name="event")
        _require_exact_keys(event_map, _EVENT_KEYS, name="event")
        event_id = event_map.get("event_id")
        if not isinstance(event_id, str) or event_id in ids:
            raise ContractError("events need unique stable event_id values")
        ids.add(event_id)
        if safe_ticker(event_map.get("ticker")) != ticker:
            raise ContractError("event ticker must match context company")
        normalize_year(event_map.get("fiscal_year"))
        normalize_quarter(event_map.get("fiscal_quarter"))
        if event_id != stable_event_id(
            event_map.get("ticker"),
            event_map.get("fiscal_year"),
            event_map.get("fiscal_quarter"),
            event_map.get("call_date"),
        ):
            raise ContractError("event_id does not match stable event identity")
        raw_call_date = event_map.get("call_date")
        if not isinstance(raw_call_date, str):
            raise ContractError("event.call_date must be an ISO date")
        called = parse_date(raw_call_date, field="event.call_date")
        if raw_call_date != called.isoformat():
            raise ContractError("event.call_date must be a canonical ISO date")
        if previous_date is not None and called > previous_date:
            raise ContractError("history must be newest-first")
        previous_date = called
        _require_text(event_map.get("summary"), field="event.summary", limit=_TEXT_LIMITS["summary"])
        _require_text(event_map.get("key_quote"), field="event.key_quote", limit=_TEXT_LIMITS["key_quote"])
        for field, limit in (("positive_highlights", 3), ("negative_highlights", 3), ("highlights", 6)):
            values = event_map.get(field)
            if not isinstance(values, list) or len(values) > limit:
                raise ContractError(f"event.{field} must be a bounded array")
            for index, value in enumerate(values):
                _require_text(value, field=f"event.{field}[{index}]", limit=_TEXT_LIMITS["highlight"], allow_null=False)
        metrics = _require_mapping(event_map.get("metrics"), name="event.metrics")
        _require_exact_keys(metrics, PUBLIC_METRICS, name="event.metrics")
        for metric, value in metrics.items():
            _require_metric(value, field=f"event.metrics.{metric}")
        previous_deltas = _require_mapping(event_map.get("previous_event_deltas"), name="event.previous_event_deltas")
        _require_exact_keys(previous_deltas, PUBLIC_METRICS, name="event.previous_event_deltas")
        for metric, value in previous_deltas.items():
            _require_metric(value, field=f"event.previous_event_deltas.{metric}")
        if not isinstance(event_map.get("sources"), list) or len(event_map["sources"]) not in {2, 3}:
            raise ContractError("event sources must be an array")
        source_refs = {
            _validate_source(source, name=f"event.sources[{index}]")
            for index, source in enumerate(event_map["sources"])
        }
        if len(source_refs) != len(event_map["sources"]):
            raise ContractError("event source_ref values must be unique")
        if source_refs not in ({"earnings_history", "transcript"}, {"earnings_history", "score_overlay", "transcript"}):
            raise ContractError("event sources must be the v1 source set")
        tags = event_map.get("tags")
        if not isinstance(tags, list) or len(tags) > 24:
            raise ContractError("event tags must be a list of at most 24 values")
        if len(set(tags)) != len(tags):
            raise ContractError("event tags must be unique")
        for tag in tags:
            if not isinstance(tag, str) or not _TAG_RE.fullmatch(tag):
                raise ContractError("event tag invalid")
        _validate_event_lineage(event_map, source_refs)
        if event_map.get("claim_citations_pending") is not True:
            raise ContractError("claim citations must remain explicitly pending")
    latest = item.get("latest_event")
    latest_id = item.get("latest_event_id")
    if history:
        if latest != history[0] or latest_id != history[0].get("event_id"):
            raise ContractError("latest event must mirror the first history event")
    elif latest is not None or latest_id is not None:
        raise ContractError("empty history must use null latest event fields")
    topics = _require_mapping(item.get("topics"), name="topics")
    _require_exact_keys(topics, _TOPICS_KEYS, name="topics")
    timeline = topics.get("timeline")
    if not isinstance(timeline, list) or len(timeline) > len(history) * 24:
        raise ContractError("topics.timeline must be a bounded array")
    newest_tags = set(history[0]["tags"]) if history else set()
    prior_tags = set(history[1]["tags"]) if len(history) > 1 else set()
    expected_topic_lists = {
        "added": sorted(newest_tags - prior_tags),
        "dropped": sorted(prior_tags - newest_tags),
        "persistent": sorted(newest_tags & prior_tags),
    }
    for key, expected in expected_topic_lists.items():
        values = topics.get(key)
        if not isinstance(values, list) or values != expected:
            raise ContractError(f"topics.{key} must match event tags")
        for value in values:
            if not isinstance(value, str) or not _TAG_RE.fullmatch(value):
                raise ContractError(f"topics.{key} tag invalid")
    by_tag: dict[str, list[Mapping[str, Any]]] = {}
    for event in reversed(history):
        for tag in event["tags"]:
            by_tag.setdefault(tag, []).append(event)
    if len(timeline) != len(by_tag):
        raise ContractError("topics.timeline must cover each event tag once")
    for index, entry in enumerate(timeline):
        entry_map = _require_mapping(entry, name=f"topics.timeline[{index}]")
        _require_exact_keys(entry_map, _TOPIC_TIMELINE_KEYS, name=f"topics.timeline[{index}]")
        tag = entry_map.get("tag")
        if not isinstance(tag, str) or tag not in by_tag:
            raise ContractError("topics.timeline tag invalid")
        hits = by_tag.pop(tag)
        expected_status = "persistent" if tag in newest_tags and tag in prior_tags else ("added" if tag in newest_tags else "dropped")
        if (
            entry_map.get("first_event_id") != hits[0]["event_id"]
            or entry_map.get("last_event_id") != hits[-1]["event_id"]
            or entry_map.get("event_count") != len(hits)
            or entry_map.get("status") != expected_status
        ):
            raise ContractError("topics.timeline entry does not match event history")
    if by_tag:
        raise ContractError("topics.timeline missing event tags")
    completeness = _require_mapping(item.get("source_completeness"), name="source_completeness")
    _require_exact_keys(completeness, _COMPLETENESS_KEYS, name="source_completeness")
    for key in _COMPLETENESS_KEYS:
        block = _require_mapping(completeness.get(key), name=f"source_completeness.{key}")
        _require_exact_keys(block, _COMPLETENESS_BLOCK_KEYS, name=f"source_completeness.{key}")
        if block.get("status") not in {"present", "metadata_only", "missing", "partial"}:
            raise ContractError(f"invalid {key} completeness status")
        count = block.get("event_count")
        if isinstance(count, bool) or not isinstance(count, int) or not 0 <= count <= len(history):
            raise ContractError(f"invalid {key} completeness event_count")
        if key == "score_overlay" and block.get("status") != ("metadata_only" if count else "missing"):
            raise ContractError("score_overlay completeness status does not match count")
        if key == "transcripts" and block.get("status") == "missing" and count:
            raise ContractError("missing transcripts cannot have events")
    warnings = item.get("warnings")
    if not isinstance(warnings, list) or warnings != sorted(set(warnings)) or any(value not in _KNOWN_WARNINGS for value in warnings):
        raise ContractError("context warnings invalid")
    missing_sources = item.get("missing_sources")
    if not isinstance(missing_sources, list) or missing_sources != sorted(set(missing_sources)) or any(value not in _KNOWN_MISSING_SOURCES for value in missing_sources):
        raise ContractError("context missing_sources invalid")
    lineage = _require_mapping(item.get("transport_lineage"), name="transport_lineage")
    _require_exact_keys(lineage, _TRANSPORT_LINEAGE_KEYS, name="transport_lineage")
    for name, extra in (("earnings_manifest", frozenset({"observed_counts"})), ("tx_index", frozenset({"schema"}))):
        block = _require_mapping(lineage.get(name), name=f"transport_lineage.{name}")
        allowed = _SOURCE_LINEAGE_BASE_KEYS | extra
        if frozenset(block) not in {_SOURCE_LINEAGE_BASE_KEYS, allowed}:
            raise ContractError(f"transport_lineage.{name} fields mismatch")
        if not _GENERATION_RE.fullmatch(str(block.get("generation_id") or "")):
            raise ContractError(f"transport_lineage.{name}.generation_id invalid")
        _require_sha(block.get("sha256"), field=f"transport_lineage.{name}.sha256")
        if name == "tx_index" and block.get("schema") != "mastermind.tx-index/v1":
            raise ContractError("transport_lineage.tx_index.schema invalid")
        if name == "earnings_manifest" and "observed_counts" in block:
            observed = _require_mapping(block.get("observed_counts"), name="transport_lineage.earnings_manifest.observed_counts")
            if set(observed) - {"history_rows", "history_tickers", "score_rows", "score_tickers"}:
                raise ContractError("transport_lineage.earnings_manifest.observed_counts fields mismatch")
            for value in observed.values():
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    raise ContractError("transport_lineage.earnings_manifest.observed_counts invalid")
    if lineage.get("builder") != "company_intelligence.v1":
        raise ContractError("transport_lineage.builder invalid")


def validate_manifest(payload: object, *, allow_unmaterialized_files: bool = False) -> None:
    """Validate the closed public marker/immutable-manifest contract.

    ``allow_unmaterialized_files`` exists solely for the local pre-write
    descriptor used to calculate an immutable generation id.  It is never
    accepted by a reader, publisher, or health check.
    """
    item = _require_mapping(payload, name="manifest")
    _require_exact_keys(item, _MANIFEST_KEYS, name="manifest")
    if item.get("schema") != MANIFEST_SCHEMA:
        raise ContractError("manifest schema mismatch")
    if not _GENERATION_RE.fullmatch(str(item.get("generation_id") or "")):
        raise ContractError("invalid manifest generation_id")
    if iso_timestamp(item.get("generated_at")) is None:
        raise ContractError("manifest generated_at missing")
    for key in ("company_count", "event_count"):
        if isinstance(item.get(key), bool) or not isinstance(item.get(key), int) or int(item[key]) < 0:
            raise ContractError(f"manifest {key} must be a nonnegative integer")
    latest_event_date = item.get("latest_event_date")
    if item["event_count"] == 0:
        if latest_event_date is not None:
            raise ContractError("manifest latest_event_date must be null without events")
    else:
        if not isinstance(latest_event_date, str):
            raise ContractError("manifest latest_event_date missing")
        parsed_latest = parse_date(latest_event_date, field="manifest.latest_event_date")
        if latest_event_date != parsed_latest.isoformat():
            raise ContractError("manifest latest_event_date must be a canonical ISO date")
    if item.get("status") not in {"ready", "degraded", "empty"}:
        raise ContractError("invalid manifest status")
    if item["status"] == "empty" and (item["company_count"] or item["event_count"]):
        raise ContractError("empty manifest must have zero counts")
    if item["status"] != "empty" and item["company_count"] == 0:
        raise ContractError("nonempty manifest must have companies")
    warnings = item.get("warnings")
    if (
        not isinstance(warnings, list)
        or warnings != sorted(set(warnings))
        or any(
            not isinstance(value, str)
            or not 1 <= len(value) <= 256
            or (value not in _KNOWN_MANIFEST_WARNINGS and not _MANIFEST_WARNING_RE.fullmatch(value))
            for value in warnings
        )
    ):
        raise ContractError("manifest warnings invalid")
    operational = _require_mapping(item.get("operational"), name="manifest.operational")
    _require_exact_keys(operational, _MANIFEST_OPERATIONAL_KEYS, name="manifest.operational")
    rejected = operational.get("history_rows_rejected")
    if isinstance(rejected, bool) or not isinstance(rejected, int) or rejected < 0:
        raise ContractError("manifest operational history_rows_rejected invalid")
    expected_rejected_warning = f"history_rows_rejected:{rejected}"
    if (rejected > 0) != (expected_rejected_warning in warnings):
        raise ContractError("manifest rejection warning does not match operational count")
    files = _require_mapping(item.get("files"), name="manifest.files")
    if len(files) != item["company_count"] and not (
        allow_unmaterialized_files and not files
    ):
        raise ContractError("manifest company_count must match files")
    for name, block in files.items():
        if not isinstance(name, str) or not name.startswith("companies/") or not name.endswith(".json"):
            raise ContractError("manifest file path is unsafe")
        company_filename(name[len("companies/"):-len(".json")])
        block_map = _require_mapping(block, name=f"manifest file {name}")
        _require_exact_keys(block_map, _MANIFEST_FILE_KEYS, name=f"manifest file {name}")
        _require_sha(block_map.get("sha256"), field=f"manifest file {name} sha256")
        if isinstance(block_map.get("bytes"), bool) or not isinstance(block_map.get("bytes"), int) or block_map["bytes"] <= 0:
            raise ContractError(f"manifest file {name} bytes invalid")
    source = _require_mapping(item.get("source"), name="manifest.source")
    _require_exact_keys(source, _MANIFEST_SOURCE_KEYS, name="manifest.source")
    for name, expected_fields in (("earnings_manifest", _MANIFEST_EARNINGS_SOURCE_KEYS), ("tx_index", _MANIFEST_TX_SOURCE_KEYS)):
        source_block = _require_mapping(source.get(name), name=f"manifest.source.{name}")
        allowed_fields = (
            {frozenset(_SOURCE_LINEAGE_BASE_KEYS), expected_fields}
            if name == "earnings_manifest"
            else {expected_fields}
        )
        if frozenset(source_block) not in allowed_fields:
            raise ContractError(f"manifest.source.{name} fields mismatch")
        if not _GENERATION_RE.fullmatch(str(source_block.get("generation_id") or "")):
            raise ContractError(f"manifest.source.{name}.generation_id invalid")
        _require_sha(source_block.get("sha256"), field=f"manifest.source.{name}.sha256")
        if name == "tx_index" and source_block.get("schema") != "mastermind.tx-index/v1":
            raise ContractError("manifest.source.tx_index.schema invalid")
        observed = source_block.get("observed_counts")
        if observed is not None:
            observed_map = _require_mapping(observed, name=f"manifest.source.{name}.observed_counts")
            for key, value in observed_map.items():
                if key not in _OBSERVED_COUNT_KEYS or isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    raise ContractError(f"manifest.source.{name}.observed_counts invalid")
