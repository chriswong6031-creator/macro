"""Pure projections from earnings-call rows into Company Intelligence views."""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from hashlib import sha256
import json
import math
from pathlib import Path
import re
import tempfile
from typing import Any, Iterable, Mapping

from .contracts import (
    AUTHORITY,
    CONTEXT_SCHEMA,
    MANIFEST_SCHEMA,
    ContractError,
    canonical_json_bytes,
    canonical_json_sha256,
    company_filename,
    event_key,
    finite_number,
    is_safe_source_url,
    iso_timestamp,
    normalize_quarter,
    normalize_year,
    parse_date,
    safe_ticker,
    stable_event_id,
    validate_context,
    validate_manifest,
)


MAX_HISTORY = 12
STALE_AFTER_DAYS = 160
_METRICS = (
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
)
_METRIC_INPUTS = {
    "sentiment": ("earnings_call_sent", "sentiment"),
    "performance": ("earnings_call_perf", "performance"),
    "confidence": ("management_confidence_score", "management_confidence", "confidence"),
    "combined": ("earnings_call_combined", "combined"),
    "call_positivity": ("call_positivity_score", "call_positivity"),
    "management_confidence": ("management_confidence_score", "management_confidence"),
    "analyst_criticism": ("analyst_criticism_score", "analyst_criticism"),
    "future_outlook": ("future_outlook_score", "future_outlook"),
    # History stores these values in percentage *units* (8.0 means 8.0%),
    # never proportions.  Projection deliberately preserves that source unit.
    "revenue_growth_pct": ("revenue_growth_pct", "revenue_growth"),
    "eps_growth_pct": ("eps_growth_pct", "eps_growth"),
    "gross_margin_pct": ("gross_margin_pct", "gross_margin"),
    "analysts_count": ("analysts_count",),
    "questions_count": ("questions_count",),
}
_TAG_SPLIT = re.compile(r"[,;|]")
_HIGHLIGHT_SPLIT = re.compile(r"\r?\n(?=\s*(?:\d+[.)]|[-•])\s*)")
_HIGHLIGHT_PREFIX = re.compile(r"^\s*(?:\d+[.)]|[-•])\s*")


def _value(row: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        value = row.get(name)
        if value is not None and str(value).strip().lower() not in {"", "nan", "none", "<na>"}:
            return value
    return None


def _text(value: Any, *, limit: int = 4000) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "<na>"}:
        return None
    return text[:limit]


def _text_list(value: Any, *, limit: int = 3) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        maybe = value.strip()
        if maybe.startswith("["):
            try:
                decoded = json.loads(maybe)
                value = decoded if isinstance(decoded, list) else [maybe]
            except json.JSONDecodeError:
                value = _TAG_SPLIT.split(maybe)
        else:
            value = _TAG_SPLIT.split(maybe)
    if not isinstance(value, (list, tuple, set)):
        value = [value]
    out: list[str] = []
    seen: set[str] = set()
    for raw in value:
        text = _text(raw, limit=1200)
        if text and text not in seen:
            seen.add(text)
            out.append(text)
        if len(out) == limit:
            break
    return out


def _highlight_list(value: Any, *, limit: int = 3) -> list[str]:
    """Preserve punctuation inside prose while splitting actual bullet lines."""
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("["):
            try:
                decoded = json.loads(text)
                value = decoded if isinstance(decoded, list) else [text]
            except json.JSONDecodeError:
                value = _HIGHLIGHT_SPLIT.split(text)
        else:
            value = _HIGHLIGHT_SPLIT.split(text)
    if not isinstance(value, (list, tuple, set)):
        value = [value]
    out: list[str] = []
    seen: set[str] = set()
    for raw in value:
        text = _text(raw, limit=1200)
        if text:
            text = _HIGHLIGHT_PREFIX.sub("", text).strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
        if len(out) == limit:
            break
    return out


def _tags(row: Mapping[str, Any]) -> list[str]:
    raw: list[str] = []
    for name in ("tags", "level1_tags", "level2_tags"):
        raw.extend(_text_list(row.get(name), limit=48))
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        tag = item.strip().lower().replace(" ", "_")
        # Dots and dashes are valid inside a tag, but the contract requires an
        # alphanumeric first character.  Some upstream topic labels arrive as
        # ".com"/".web"; normalize those to stable, valid public tags instead
        # of rejecting the entire generation.
        tag = re.sub(r"[^a-z0-9_.-]+", "_", tag).strip("_.-")
        # The public contract is intentionally compact enough for Terminal
        # chips/URLs.  Trim before deduping so a malformed giant source tag
        # cannot become a second identity for the same useful prefix.
        tag = tag[:96]
        if tag and tag not in seen:
            seen.add(tag)
            out.append(tag)
    return out[:24]


def _timestamp_sort(value: Any) -> str:
    return iso_timestamp(value) or ""


def _hashable(value: Any) -> Any:
    """Make pandas/numpy scalar values deterministic without importing either."""
    if isinstance(value, Mapping):
        return {str(key): _hashable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_hashable(item) for item in value]
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    timestamp = iso_timestamp(value)
    if timestamp is not None:
        return timestamp
    return str(value)


def _row_hash(row: Mapping[str, Any]) -> str:
    return canonical_json_sha256(_hashable(dict(row)))


def _source_metadata(row: Mapping[str, Any]) -> dict[str, Any] | None:
    receipt: dict[str, Any] = {}
    source_hash = _text(_value(row, "source_sha256", "source_hash"), limit=128)
    source_date = iso_timestamp(_value(row, "source_updated_at", "updated_at", "scored_at", "created_at"))
    record_id = _text(_value(row, "source_record_id", "id"), limit=160)
    if source_hash and re.fullmatch(r"[0-9a-f]{64}", source_hash):
        receipt["source_hash"] = source_hash
    if source_date:
        receipt["source_date"] = source_date
    if record_id:
        receipt["record_id"] = record_id
    return receipt or None


def _has_raw_document(row: Mapping[str, Any]) -> bool:
    # An EquityDesk row hash identifies metadata, not a retrievable raw document.
    return bool(_source_url(row))


def _source_url(row: Mapping[str, Any]) -> str | None:
    raw = _value(row, "raw_source_url", "raw_document_url", "source_url", "source_uri")
    if raw is None:
        return None
    value = str(raw).strip()
    if not value or value.lower() in {"nan", "none", "<na>"}:
        return None
    return value if value and is_safe_source_url(value) else None


def _history_source(row: Mapping[str, Any]) -> dict[str, Any]:
    raw_url = _source_url(row)
    return {
        "source_ref": "earnings_history",
        "kind": "earnings_history",
        "status": "present" if raw_url else "metadata_only",
        "citation_precision": "document" if raw_url else "metadata",
        "url": raw_url,
        "receipt": _source_metadata(row),
    }


def _overlay_source(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "source_ref": "score_overlay",
        "kind": "score_overlay",
        "status": "metadata_only",
        "citation_precision": "metadata",
        "url": None,
        "receipt": _source_metadata(row),
    }


def _normalize_history_row(row: Mapping[str, Any]) -> dict[str, Any]:
    ticker = safe_ticker(_value(row, "document_ticker", "ticker", "symbol"))
    fiscal_year = normalize_year(_value(row, "fiscal_year", "year"))
    fiscal_quarter = normalize_quarter(_value(row, "fiscal_quarter", "quarter"))
    call_date = parse_date(_value(row, "call_date", "date"), field="call_date").isoformat()
    key = event_key(ticker, fiscal_year, fiscal_quarter, call_date)
    metrics = {
        name: finite_number(_value(row, *input_names))
        for name, input_names in _METRIC_INPUTS.items()
    }
    positive = _highlight_list(row.get("positive_highlights"), limit=3)
    negative = _highlight_list(row.get("negative_highlights"), limit=3)
    highlights = (positive + [item for item in negative if item not in positive])[:6]
    return {
        "key": key,
        "ticker": ticker,
        "fiscal_year": fiscal_year,
        "fiscal_quarter": fiscal_quarter,
        "call_date": call_date,
        "revision_at": _timestamp_sort(_value(row, "updated_at", "source_updated_at", "scored_at", "created_at")),
        "revision_hash": _row_hash(row),
        "display_name": _text(_value(row, "company_name", "display_name", "issuer_name"), limit=240),
        "exchange": _text(_value(row, "exchange", "listing_exchange"), limit=64),
        "summary": _text(_value(row, "summary", "earnings_summary")),
        "key_quote": _text(_value(row, "key_quote", "quote")),
        "positive_highlights": positive,
        "negative_highlights": negative,
        "highlights": highlights,
        "tags": _tags(row),
        "metrics": metrics,
        "source": _history_source(row),
        "raw_document_present": _has_raw_document(row),
    }


def _normalize_scores(rows: Iterable[Mapping[str, Any]]) -> dict[tuple[str, int, int], Mapping[str, Any]]:
    """Select a deterministic revision for each overlay period.

    Score rows without a complete period cannot safely be joined and therefore
    never become replacement events.
    """
    selected: dict[tuple[str, int, int], tuple[str, str, Mapping[str, Any]]] = {}
    for row in rows:
        try:
            ticker = safe_ticker(_value(row, "ticker", "document_ticker", "symbol"))
            year = normalize_year(_value(row, "year", "fiscal_year"))
            quarter = normalize_quarter(_value(row, "quarter", "fiscal_quarter"))
        except ContractError:
            continue
        rank = (_timestamp_sort(_value(row, "source_updated_at", "updated_at", "scored_at", "created_at")), _row_hash(row))
        key = (ticker, year, quarter)
        if key not in selected or rank > selected[key][:2]:
            selected[key] = (*rank, row)
    return {key: value[2] for key, value in selected.items()}


def _period_from_record(record: Mapping[str, Any]) -> tuple[str, int, int] | None:
    try:
        ticker = safe_ticker(_value(record, "ticker", "symbol", "document_ticker"))
        year = normalize_year(_value(record, "fiscal_year", "year"))
        quarter = normalize_quarter(_value(record, "fiscal_quarter", "quarter"))
    except ContractError:
        period = _text(_value(record, "period", "fiscal_period"))
        ticker = _text(_value(record, "ticker", "symbol", "document_ticker"))
        match = re.fullmatch(r"(\d{4})\s*Q([1-4])", str(period or "").upper())
        if not ticker or not match:
            return None
        try:
            return safe_ticker(ticker), int(match.group(1)), int(match.group(2))
        except ContractError:
            return None
    return ticker, year, quarter


def _tx_records(tx_index: Mapping[str, Any] | None) -> tuple[dict[tuple[str, int, int], Mapping[str, Any]], bool]:
    if not isinstance(tx_index, Mapping) or tx_index.get("schema") != "mastermind.tx-index/v1":
        return {}, False
    candidates: list[Mapping[str, Any]] = []
    for key in ("documents", "transcripts", "entries", "items", "records", "files"):
        raw = tx_index.get(key)
        if isinstance(raw, list):
            candidates.extend(item for item in raw if isinstance(item, Mapping))
        elif isinstance(raw, Mapping):
            candidates.extend(item for item in raw.values() if isinstance(item, Mapping))
    # The first Terminal versions used {"companies": {"AAPL": [...]}}.
    companies = tx_index.get("companies")
    if isinstance(companies, Mapping):
        for ticker, raw in companies.items():
            if isinstance(raw, list):
                for item in raw:
                    if isinstance(item, Mapping):
                        candidates.append({"ticker": ticker, **item})
    # Production Terminal index: {symbols: {AAPL: ["2026Q1", ...]}}.  The
    # period string is the index's presence receipt; no text or claim span is
    # inferred from it, and malformed entries are ignored rather than guessed.
    symbols = tx_index.get("symbols")
    if isinstance(symbols, Mapping):
        for raw_ticker, periods in symbols.items():
            try:
                ticker = safe_ticker(raw_ticker)
            except ContractError:
                continue
            if not isinstance(periods, (list, tuple, set)):
                continue
            for period in periods:
                match = re.fullmatch(r"(\d{4})Q([1-4])", str(period).strip().upper())
                if match:
                    candidates.append({
                        "ticker": ticker,
                        "fiscal_year": int(match.group(1)),
                        "fiscal_quarter": int(match.group(2)),
                        "present": True,
                    })
    selected: dict[tuple[str, int, int], Mapping[str, Any]] = {}
    for record in candidates:
        period = _period_from_record(record)
        if period is None:
            continue
        # Explicit false is never a presence receipt.  A path is optional because
        # the index itself grants the permitted canonical path below.
        if record.get("present") is False or record.get("available") is False:
            continue
        selected[period] = record
    return selected, True


def _transcript_source(event: Mapping[str, Any], tx_record: Mapping[str, Any] | None) -> dict[str, Any]:
    if tx_record is None:
        return {
            "source_ref": "transcript",
            "kind": "transcript",
            "status": "missing",
            "citation_precision": "document",
            "url": None,
            "receipt": None,
        }
    ticker = safe_ticker(event["ticker"])
    period = f"{int(event['fiscal_year'])}Q{int(event['fiscal_quarter'])}"
    receipt: dict[str, Any] = {}
    source_hash = _text(_value(tx_record, "source_hash", "sha256", "hash"), limit=128)
    source_date = iso_timestamp(_value(tx_record, "source_date", "date", "published_at", "updated_at"))
    record_id = _text(_value(tx_record, "receipt_id", "id", "document_id"), limit=160)
    if source_hash and re.fullmatch(r"[0-9a-f]{64}", source_hash):
        receipt["source_hash"] = source_hash
    if source_date:
        receipt["source_date"] = source_date
    if record_id:
        receipt["record_id"] = record_id
    return {
        "source_ref": "transcript",
        "kind": "transcript",
        "status": "present",
        "citation_precision": "document",
        "url": f"/data/tx/{ticker}/{period}.json.gz",
        "receipt": receipt or None,
    }


def _event_from_history(row: Mapping[str, Any], overlay: Mapping[str, Any] | None, tx_record: Mapping[str, Any] | None) -> dict[str, Any]:
    metrics = dict(row["metrics"])
    sources = [row["source"]]
    summary = row["summary"]
    tags = list(row["tags"])
    field_lineage: dict[str, Any] = {
        "summary": "earnings_history" if summary is not None else None,
        "key_quote": "earnings_history" if row["key_quote"] is not None else None,
        "metrics": {
            metric: "earnings_history" if value is not None else None
            for metric, value in metrics.items()
        },
        "positive_highlights": ["earnings_history"] * len(row["positive_highlights"]),
        "negative_highlights": ["earnings_history"] * len(row["negative_highlights"]),
        "highlights": ["earnings_history"] * len(row["highlights"]),
        "tags": {tag: "earnings_history" for tag in tags},
    }
    if overlay is not None:
        # Overlay only fills/updates named, existing numeric fields.  It cannot
        # erase the healthy history row or manufacture an event from a degraded
        # score-only record.
        for metric, input_names in _METRIC_INPUTS.items():
            candidate = finite_number(_value(overlay, *input_names))
            if candidate is not None:
                metrics[metric] = candidate
                field_lineage["metrics"][metric] = "score_overlay"
        # A score-overlay summary is source-authored context, not a generated
        # brief; use it only when history supplies no summary at all.
        if summary is None:
            summary = _text(_value(overlay, "summary", "earnings_summary"))
            if summary is not None:
                field_lineage["summary"] = "score_overlay"
        for tag in _tags(overlay):
            if tag not in tags and len(tags) < 24:
                tags.append(tag)
                field_lineage["tags"][tag] = "score_overlay"
        sources.append(_overlay_source(overlay))
    event = {
        "event_id": stable_event_id(row["ticker"], row["fiscal_year"], row["fiscal_quarter"], row["call_date"]),
        "ticker": row["ticker"],
        "fiscal_year": row["fiscal_year"],
        "fiscal_quarter": row["fiscal_quarter"],
        "call_date": row["call_date"],
        "summary": summary,
        "highlights": row["highlights"],
        "positive_highlights": row["positive_highlights"],
        "negative_highlights": row["negative_highlights"],
        "key_quote": row["key_quote"],
        "tags": tags,
        "metrics": metrics,
        "field_lineage": field_lineage,
        "previous_event_deltas": {metric: None for metric in _METRICS},
        "sources": sources,
        # A transcript receipt proves document availability only.  It does not
        # pinpoint a claim span in an EquityDesk summary or tag.
        "claim_citations_pending": True,
    }
    event["sources"].append(_transcript_source(event, tx_record))
    return event


def _topic_summary(events_newest: list[Mapping[str, Any]]) -> dict[str, Any]:
    if not events_newest:
        return {"timeline": [], "added": [], "dropped": [], "persistent": []}
    newest_tags = set(events_newest[0]["tags"])
    prior_tags = set(events_newest[1]["tags"]) if len(events_newest) > 1 else set()
    timeline: list[dict[str, Any]] = []
    by_tag: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for event in reversed(events_newest):
        for tag in event["tags"]:
            by_tag[tag].append(event)
    for tag in sorted(by_tag):
        hits = by_tag[tag]
        if tag in newest_tags and tag in prior_tags:
            status = "persistent"
        elif tag in newest_tags:
            status = "added"
        else:
            status = "dropped"
        timeline.append({
            "tag": tag,
            "first_event_id": hits[0]["event_id"],
            "last_event_id": hits[-1]["event_id"],
            "event_count": len(hits),
            "status": status,
        })
    return {
        "timeline": timeline,
        "added": sorted(newest_tags - prior_tags),
        "dropped": sorted(prior_tags - newest_tags),
        "persistent": sorted(newest_tags & prior_tags),
    }


def _derived_generated_at(history_rows: Iterable[Mapping[str, Any]], earnings_manifest: Mapping[str, Any] | None) -> str:
    candidates: list[str] = []
    if isinstance(earnings_manifest, Mapping):
        for name in ("generated_at", "built", "updated_at", "as_of"):
            stamp = iso_timestamp(earnings_manifest.get(name))
            if stamp:
                candidates.append(stamp)
    for row in history_rows:
        for name in ("source_updated_at", "updated_at", "scored_at", "call_date"):
            stamp = iso_timestamp(row.get(name))
            if stamp:
                candidates.append(stamp)
                break
    return max(candidates) if candidates else "1970-01-01T00:00:00Z"


def _source_block(payload: Mapping[str, Any] | None, *, expected_schema: str | None = None) -> dict[str, Any]:
    material = dict(payload or {})
    source_sha256 = canonical_json_sha256(material)
    source_generation = _text(material.get("generation_id"), limit=128)
    # Upstream generation ids are provenance labels, not an authority to relax
    # our public address grammar.  Invalid/legacy labels use the deterministic
    # content hash prefix just like an unversioned source does.
    if source_generation and not re.fullmatch(r"[0-9a-f]{24,64}", source_generation):
        source_generation = None
    block = {
        # Terminal's compact symbols index intentionally has no generation_id.
        # Its content hash prefix is therefore the honest, reproducible snapshot
        # id (and remains a simple 24-hex string for strict API clients).
        "generation_id": source_generation or source_sha256[:24],
        "sha256": source_sha256,
    }
    if expected_schema is not None:
        block["schema"] = _text(material.get("schema"), limit=128) or expected_schema
    # Preserve upstream declared cardinalities when they exist.  They are a
    # source baseline for the publish shrink/reconciliation guard, not a claim
    # that every raw row survives fiscal-period dedupe or the twelve-event cap.
    if expected_schema is None:
        observed: dict[str, int] = {}
        for source_name, target_name in (("history", "history"), ("scores", "score")):
            source = material.get(source_name)
            if not isinstance(source, Mapping):
                continue
            for field in ("rows", "tickers"):
                value = source.get(field)
                if isinstance(value, int) and value >= 0:
                    observed[f"{target_name}_{field}"] = value
        if observed:
            block["observed_counts"] = observed
    return block


def _context_status(
    events: list[Mapping[str, Any]],
    warnings: list[str],
    *,
    as_of: date | None,
) -> str:
    if not events:
        return "not_covered"
    if as_of is not None and (as_of - parse_date(events[0]["call_date"], field="call_date")).days > STALE_AFTER_DAYS:
        return "stale"
    return "partial" if warnings else "ready"


def build_company_contexts(
    history_rows: Iterable[Mapping[str, Any]],
    score_rows: Iterable[Mapping[str, Any]] | None = None,
    *,
    tx_index: Mapping[str, Any] | None = None,
    earnings_manifest: Mapping[str, Any] | None = None,
    as_of: date | str | None = None,
    generated_at: str | None = None,
    max_history: int = MAX_HISTORY,
) -> dict[str, dict[str, Any]]:
    """Build one context-only view per ticker from ordinary dictionaries.

    The function is intentionally parquet-free so contracts can be tested with
    small dicts and consumers can reproduce the projection independently.
    """
    if not 1 <= int(max_history) <= MAX_HISTORY:
        raise ContractError(f"max_history must be between 1 and {MAX_HISTORY}")
    history_input = [dict(row) for row in history_rows]
    normalized: dict[str, dict[str, Any]] = {}
    for raw in history_input:
        row = _normalize_history_row(raw)
        current = normalized.get(row["key"])
        rank = (row["revision_at"], row["revision_hash"])
        if current is None or rank > (current["revision_at"], current["revision_hash"]):
            normalized[row["key"]] = row
    overlays = _normalize_scores(score_rows or [])
    transcripts, tx_valid = _tx_records(tx_index)
    generated = iso_timestamp(generated_at) or _derived_generated_at(history_input, earnings_manifest)
    freshness_reference = parse_date(as_of, field="as_of") if as_of is not None else None
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in normalized.values():
        groups[row["ticker"]].append(row)
    for ticker, _year, _quarter in overlays:
        # A score-only ticker is deliberately not promoted to an event.  It is
        # still materialised as an honest not_covered context so consumers do
        # not mistake a missing object for a healthy earnings history.
        groups.setdefault(ticker, [])
    contexts: dict[str, dict[str, Any]] = {}
    for ticker in sorted(groups):
        rows = sorted(
            groups[ticker],
            key=lambda item: (item["call_date"], item["fiscal_year"], item["fiscal_quarter"], item["revision_at"], item["revision_hash"]),
        )
        chronology: list[dict[str, Any]] = []
        for row in rows:
            overlay = overlays.get((ticker, row["fiscal_year"], row["fiscal_quarter"]))
            transcript = transcripts.get((ticker, row["fiscal_year"], row["fiscal_quarter"]))
            event = _event_from_history(row, overlay, transcript)
            if chronology:
                prior = chronology[-1]
                event["previous_event_deltas"] = {
                    key: (
                        event["metrics"][key] - prior["metrics"][key]
                        if event["metrics"][key] is not None and prior["metrics"][key] is not None
                        else None
                    )
                    for key in _METRICS
                }
            chronology.append(event)
        # All completeness counts below are deliberately based on this returned
        # cap, not the whole source history.  A reader only receives these
        # events, so reporting coverage for older hidden rows would overstate
        # what it can actually inspect.
        events = list(reversed(chronology))[: int(max_history)]
        history_sources = [
            next(source for source in event["sources"] if source["source_ref"] == "earnings_history")
            for event in events
        ]
        history_present_count = sum(source["status"] == "present" for source in history_sources)
        transcript_count = sum(
            1 for event in events
            if any(source["kind"] == "transcript" and source["status"] == "present" for source in event["sources"])
        )
        overlay_count = sum(
            1 for event in events
            if any(source["source_ref"] == "score_overlay" for source in event["sources"])
        )
        warnings: list[str] = []
        missing: list[str] = []
        if not rows:
            warnings.append("earnings_history_missing")
            missing.append("earnings_history")
        elif history_present_count == 0:
            warnings.append("earnings_history_metadata_only")
            missing.append("earnings_history_raw_source")
        elif history_present_count < len(events):
            warnings.append("earnings_history_partial")
            missing.append("earnings_history_raw_source_for_some_events")
        if not tx_valid:
            warnings.append("tx_index_missing_or_invalid")
            missing.append("terminal_transcript_index")
        elif transcript_count < len(events):
            warnings.append("transcripts_partial")
            missing.append("transcripts_for_some_events")
        if freshness_reference is None:
            warnings.append("freshness_reference_missing")
        completeness = {
            "earnings_history": {
                "status": (
                    "missing" if not events
                    else "present" if history_present_count == len(events)
                    else "metadata_only" if history_present_count == 0
                    else "partial"
                ),
                "event_count": len(events),
            },
            "score_overlay": {
                # Overlay data is intentionally metadata-only: it is an
                # analysis row, never a raw earnings document.
                "status": "metadata_only" if overlay_count else "missing",
                "event_count": overlay_count,
            },
            "transcripts": {
                "status": (
                    "missing" if not tx_valid or transcript_count == 0
                    else "present" if transcript_count == len(events)
                    else "partial"
                ),
                "event_count": transcript_count,
            },
        }
        context = {
            "schema": CONTEXT_SCHEMA,
            "authority": AUTHORITY,
            "generated_at": generated,
            # Filled by build_bundle after it has seen all deterministic inputs.
            "generation_id": "0" * 24,
            "company": {
                "ticker": ticker,
                "display_name": next((row["display_name"] for row in reversed(rows) if row["display_name"]), ticker),
                # v1 intentionally keeps this frozen null.  An exchange label
                # in history is not yet a canonical company-identity source.
                "exchange": None,
            },
            "status": _context_status(events, warnings, as_of=freshness_reference),
            "latest_event_id": events[0]["event_id"] if events else None,
            "latest_event": events[0] if events else None,
            "history": events,
            "topics": _topic_summary(events),
            "source_completeness": completeness,
            "warnings": sorted(set(warnings)),
            "missing_sources": sorted(set(missing)),
            "transport_lineage": {
                "earnings_manifest": _source_block(earnings_manifest),
                "tx_index": _source_block(tx_index, expected_schema="mastermind.tx-index/v1"),
                "builder": "company_intelligence.v1",
            },
        }
        contexts[ticker] = context
    return contexts


def build_bundle(
    history_rows: Iterable[Mapping[str, Any]],
    score_rows: Iterable[Mapping[str, Any]] | None = None,
    *,
    tx_index: Mapping[str, Any] | None = None,
    earnings_manifest: Mapping[str, Any] | None = None,
    as_of: date | str | None = None,
    generated_at: str | None = None,
    operational_warnings: Iterable[str] | None = None,
    history_rows_rejected: int = 0,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Return contexts plus a deterministic generation manifest, without writing."""
    contexts = build_company_contexts(
        history_rows,
        score_rows,
        tx_index=tx_index,
        earnings_manifest=earnings_manifest,
        as_of=as_of,
        generated_at=generated_at,
    )
    events = [event for context in contexts.values() for event in context["history"]]
    latest = max((event["call_date"] for event in events), default=None)
    if not isinstance(history_rows_rejected, int) or history_rows_rejected < 0:
        raise ContractError("history_rows_rejected must be a nonnegative integer")
    operational = sorted({
        warning.strip()
        for warning in (operational_warnings or [])
        if isinstance(warning, str) and warning.strip()
    })
    if any(len(warning) > 256 for warning in operational):
        raise ContractError("operational warning exceeds 256 characters")
    if history_rows_rejected:
        operational.append(f"history_rows_rejected:{history_rows_rejected}")
        operational = sorted(set(operational))
    manifest_status = "empty" if not contexts else (
        "degraded" if operational or any(context["status"] != "ready" for context in contexts.values()) else "ready"
    )
    manifest = {
        "schema": MANIFEST_SCHEMA,
        # Filled from the content identity after all operational metadata is
        # finalized.  Never mutate warnings/status after this point.
        "generation_id": "0" * 24,
        "generated_at": next(iter(contexts.values()))["generated_at"] if contexts else (iso_timestamp(generated_at) or "1970-01-01T00:00:00Z"),
        "company_count": len(contexts),
        "event_count": len(events),
        "latest_event_date": latest,
        "source": {
            "earnings_manifest": _source_block(earnings_manifest),
            "tx_index": _source_block(tx_index, expected_schema="mastermind.tx-index/v1"),
        },
        "files": {},
        "status": manifest_status,
        "warnings": sorted({
            *operational,
            *(warning for context in contexts.values() for warning in context["warnings"]),
        }),
        "operational": {"history_rows_rejected": history_rows_rejected},
    }
    # The immutable address covers the complete semantic manifest as well as
    # the pre-ID contexts. File hashes are excluded because they are a
    # deterministic function of these contexts plus this address.
    generation_id = _generation_identity(contexts, manifest)
    manifest["generation_id"] = generation_id
    for context in contexts.values():
        context["generation_id"] = generation_id
        validate_context(context)
    validate_manifest(manifest, allow_unmaterialized_files=True)
    return contexts, manifest


def _generation_identity(
    contexts: Mapping[str, Mapping[str, Any]],
    manifest: Mapping[str, Any],
) -> str:
    """Return the semantic immutable address without a self-hash fixed point."""
    pre_id_contexts: dict[str, Any] = {}
    for ticker, context in contexts.items():
        # The canonical JSON round trip detaches latest_event/history references
        # before replacing the generation field for the pre-ID projection.
        clean = json.loads(canonical_json_bytes(context))
        clean["generation_id"] = "0" * 24
        pre_id_contexts[str(ticker)] = clean
    descriptor = {
        str(key): value
        for key, value in manifest.items()
        if key not in {"generation_id", "files"}
    }
    return sha256(canonical_json_bytes({"contexts": pre_id_contexts, "manifest": descriptor})).hexdigest()[:24]


def _atomic_write(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(body)
    try:
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def write_generation(
    out_dir: Path,
    contexts: Mapping[str, Mapping[str, Any]],
    manifest: Mapping[str, Any],
) -> Path:
    """Write immutable generation objects then atomically advance local marker."""
    validate_manifest({**manifest, "files": manifest.get("files") or {}}, allow_unmaterialized_files=True)
    generation_id = str(manifest["generation_id"])
    expected_generation_id = _generation_identity(contexts, manifest)
    if generation_id != expected_generation_id:
        raise ContractError("manifest generation_id does not match immutable semantic content")
    generation_dir = out_dir / "generations" / generation_id
    file_blocks: dict[str, dict[str, Any]] = {}
    for ticker in sorted(contexts):
        context = dict(contexts[ticker])
        validate_context(context)
        relative = company_filename(ticker)
        path = generation_dir / relative
        body = canonical_json_bytes(context)
        if path.exists() and path.read_bytes() != body:
            raise ContractError(f"immutable generation collision: {path}")
        if not path.exists():
            _atomic_write(path, body)
        file_blocks[relative] = {"sha256": sha256(body).hexdigest(), "bytes": len(body)}
    final_manifest = dict(manifest)
    final_manifest["files"] = file_blocks
    validate_manifest(final_manifest)
    final_manifest_body = canonical_json_bytes(final_manifest)
    immutable_manifest_path = generation_dir / "manifest.json"
    if immutable_manifest_path.exists() and immutable_manifest_path.read_bytes() != final_manifest_body:
        raise ContractError(f"immutable generation collision: {immutable_manifest_path}")
    if not immutable_manifest_path.exists():
        _atomic_write(immutable_manifest_path, final_manifest_body)
    # Sole mutable local/R2 commit marker.  It is intentionally written last.
    _atomic_write(out_dir / "manifest.json", final_manifest_body)
    return generation_dir
