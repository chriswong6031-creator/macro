"""Committed earnings-call score projection for Chronicle.

The qualitative scorer's ``data/earnings_calls/scores.parquet`` object is a
mutable R2-transported generation.  Chronicle must not bind its deterministic
rebuild to that moving object.  A normal nightly therefore projects only
healthy, evidence-addressed score rows into the committed
``data/chronicle/earnings_call_events.jsonl`` ledger first; Chronicle rebuilds
read that ledger and never touch the parquet.

The ledger is last-good and record-stable:

* ``source_record_id`` determines the row id, so a corrected transcript keeps
  the same identity;
* a healthy correction replaces that row with its new source hash/body;
* a degraded score, rejected generation, missing store, or provider outage
  never replaces or deletes a prior healthy row;
* rows absent from the latest score snapshot remain in the committed ledger;
* only ``COLLECT_LANE=nightly`` may write it;
* ``--rebuild`` is read-only over it, just like Chronicle's state log.

Every row is public-safe and carries the source URL/hash plus model, prompt,
analysis-schema, source-update, and scoring lineage.  The adapter at the end of
this module projects the richer record into ``chronicle.event.v1`` without
giving the LLM score any ranking/gating authority.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

from . import schema

log = logging.getLogger(__name__)

CALL_EVENT_SCHEMA = "earnings.call_event.v1"
CALL_EVENTS_REL = Path("data") / "chronicle" / "earnings_call_events.jsonl"
TERMINAL_ORIGIN = "https://app.mastermind-x.com"

CALL_EVENT_FIELDS: tuple[str, ...] = (
    "schema",
    "id",
    "source_record_id",
    "ticker",
    "quarter",
    "year",
    "call_date",
    "source_type",
    "source_url",
    "source_sha256",
    "source_updated_at",
    "scored_at",
    "model",
    "prompt_version",
    "analysis_schema_version",
    "sentiment",
    "performance",
    "confidence",
    "tone_word",
    "summary",
    "positive_highlights",
    "negative_highlights",
    "tags",
    "is_context_only",
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_QUARTER_RE = re.compile(r"^Q[1-4]$")
_TAG_RE = re.compile(r"^[a-z0-9][a-z0-9_:-]{0,79}$")
_MAX_SUMMARY = 1600
_MAX_HIGHLIGHT = 400
_MAX_HIGHLIGHTS = 3
_MAX_TAGS = 16

# ``summary`` and highlight strings originate in an upstream model.  They are
# evidence, never instructions.  Keep the canonical row for auditability, but
# every consumer must pass the prose through the shared boundary below before
# placing it in another model prompt or a public derivative.
_EVIDENCE_INJECTION_PATTERNS = (
    re.compile(r"\breveal\b.{0,40}\b(prompt|instructions|rules|secrets?)\b", re.I),
    re.compile(r"\b(follow|obey|execute)\b.{0,30}\b(instructions|commands?)\b", re.I),
    re.compile(r"\b(developer|system)\s+(message|instructions?)\b", re.I),
    re.compile(r"\byou\s+are\s+(?:chatgpt|an?\s+assistant|the\s+system)\b", re.I),
    re.compile(r"<\/?(?:system|assistant|developer|tool)[^>]*>", re.I),
)
_CORE_INJECTION_FALLBACK = (
    re.compile(r"ignore\s+(all\s+)?(the\s+|your\s+|previous\s+|prior\s+)*instructions", re.I),
    re.compile(r"\bdisregard\b.{0,30}\binstructions\b", re.I),
    re.compile(r"\bforget\b.{0,20}\b(your\s+)?(instructions|rules|guidelines)\b", re.I),
    re.compile(r"system\s+prompt", re.I),
    re.compile(r"override\s+(the|your|all)\s+(instructions|rules|guidelines)", re.I),
    re.compile(r"tool\s*call\s*:", re.I),
    re.compile(r'"\s*role\s*"\s*:\s*"\s*assistant\s*"', re.I),
    re.compile(r'"\s*type\s*"\s*:\s*"\s*tool_result\s*"', re.I),
)


def _missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return str(value).strip().lower() in {"", "nan", "none", "<na>"}


def _text(value: Any, *, max_len: int | None = None) -> str:
    if _missing(value):
        return ""
    out = re.sub(r"\s+", " ", str(value)).strip()
    return out[:max_len] if max_len is not None else out


def sanitize_untrusted_prose(value: Any, *, max_len: int = _MAX_SUMMARY) -> str:
    """Return financial evidence with instruction-like clauses removed.

    Earnings prose is model-produced and therefore an untrusted data field.
    We drop only the sentence/clause that matches the complete Brain injection
    family (plus markup/reveal variants), preserving unrelated financial facts
    from the same event.  The caller supplies the contract-specific length cap.
    """

    raw = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", str(value or ""))
    raw = re.sub(r"\s+", " ", raw).strip()
    if not raw:
        return ""
    try:
        from engine.neuralweb.ask_brain import _INJECTION_PATTERNS  # noqa: PLC0415

        patterns = tuple(_INJECTION_PATTERNS) + _EVIDENCE_INJECTION_PATTERNS
    except Exception:  # noqa: BLE001 - fail closed during partial imports
        patterns = _CORE_INJECTION_FALLBACK + _EVIDENCE_INJECTION_PATTERNS

    # Sentence boundaries are the narrowest stable unit we can quarantine
    # without attempting semantic rewriting of source evidence.
    clauses = re.split(r"(?<=[.!?])\s+|[\r\n]+", raw)
    kept = [
        clause.strip()
        for clause in clauses
        if clause.strip() and not any(pattern.search(clause) for pattern in patterns)
    ]
    return _text(" ".join(kept), max_len=max_len)


def sanitize_call_event_evidence(row: Mapping[str, Any] | dict) -> dict:
    """Copy a call event with only its untrusted prose fields sanitized."""

    out = dict(row)
    summary = sanitize_untrusted_prose(out.get("summary"), max_len=_MAX_SUMMARY)
    out["summary"] = summary or None
    for field in ("positive_highlights", "negative_highlights"):
        cleaned = [
            sanitize_untrusted_prose(item, max_len=_MAX_HIGHLIGHT)
            for item in (out.get(field) or [])
        ]
        out[field] = [item for item in cleaned if item][:_MAX_HIGHLIGHTS]
    return out


def _float(value: Any, lo: float, hi: float) -> float:
    if _missing(value):
        raise ValueError("numeric score is absent")
    try:
        out = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"numeric score is invalid: {value!r}") from exc
    if not math.isfinite(out) or not lo <= out <= hi:
        raise ValueError(f"numeric score outside {lo}..{hi}: {value!r}")
    return out


def _iso_date(value: Any) -> str:
    raw = _text(value)
    if not raw:
        raise ValueError("call_date is absent")
    try:
        return date.fromisoformat(raw[:10]).isoformat()
    except ValueError as exc:
        raise ValueError(f"call_date is invalid: {value!r}") from exc


def _timestamp(value: Any, field: str) -> str:
    raw = _text(value)
    if not raw:
        raise ValueError(f"{field} is absent")
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} is invalid: {value!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat(
        timespec="microseconds",
    ).replace("+00:00", "Z")


def _as_of_datetime(value: date | datetime | str | None) -> datetime:
    """Normalize an explicit knowledge ceiling; ``None`` means wall clock now."""

    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, datetime.max.time(), tzinfo=timezone.utc)
    else:
        raw = str(value).strip()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
            parsed = datetime.combine(
                date.fromisoformat(raw), datetime.max.time(), tzinfo=timezone.utc,
            )
        else:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _event_timeline(
    call_value: Any,
    source_value: Any,
    scored_value: Any,
    *,
    as_of: date | datetime | str | None = None,
) -> tuple[str, str, str]:
    """Normalize and enforce the point-in-time lineage for one score row."""

    call_date = _iso_date(call_value)
    source_updated_at = _timestamp(source_value, "source_updated_at")
    scored_at = _timestamp(scored_value, "scored_at")
    call_day = date.fromisoformat(call_date)
    source_dt = datetime.fromisoformat(source_updated_at.replace("Z", "+00:00"))
    scored_dt = datetime.fromisoformat(scored_at.replace("Z", "+00:00"))
    if call_day > source_dt.date():
        raise ValueError("call_date occurs after source_updated_at")
    if source_dt > scored_dt:
        raise ValueError("source_updated_at occurs after scored_at")
    if as_of is not None:
        ceiling = _as_of_datetime(as_of)
        if call_day > ceiling.date():
            raise ValueError("call_date occurs after as_of")
        if source_dt > ceiling:
            raise ValueError("source_updated_at occurs after as_of")
        if scored_dt > ceiling:
            raise ValueError("scored_at occurs after as_of")
    return call_date, source_updated_at, scored_at


def call_event_available_as_of(
    row: Mapping[str, Any], as_of: date | datetime | str | None,
) -> bool:
    """True only when call, source revision, and score all existed by ``as_of``."""

    try:
        _event_timeline(
            row.get("call_date"), row.get("source_updated_at"), row.get("scored_at"),
            as_of=_as_of_datetime(as_of),
        )
    except (TypeError, ValueError):
        return False
    return True


def _string_list(
    value: Any,
    *,
    max_items: int,
    max_len: int,
    tags: bool = False,
) -> list[str]:
    if _missing(value):
        return []
    raw = value
    if isinstance(raw, str):
        try:
            decoded = json.loads(raw)
            raw = decoded if isinstance(decoded, list) else []
        except Exception:  # noqa: BLE001
            raw = []
    elif hasattr(raw, "tolist"):
        try:
            raw = raw.tolist()
        except Exception:  # noqa: BLE001
            raw = []
    if not isinstance(raw, (list, tuple)):
        return []

    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        text = _text(item, max_len=max_len)
        if tags:
            text = text.lower()
            if not _TAG_RE.fullmatch(text):
                continue
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
        if len(out) >= max_items:
            break
    return out


def _source_url(value: Any) -> str:
    raw = _text(value, max_len=1000)
    if raw.startswith("/data/tx/"):
        raw = TERMINAL_ORIGIN + raw
    parsed = urlsplit(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"source_url is not a public HTTP(S) URL: {value!r}")
    return raw


def make_call_event_id(source_record_id: str) -> str:
    """Stable id for one upstream call record, independent of its revision."""

    digest = hashlib.sha256(source_record_id.encode("utf-8")).hexdigest()[:16]
    return f"ece-{digest}"


def validate_call_event(row: dict) -> list[str]:
    """Return contract violations for one ``earnings.call_event.v1`` row."""

    if not isinstance(row, dict):
        return ["row is not an object"]
    problems: list[str] = []
    keys = set(row)
    allowed = set(CALL_EVENT_FIELDS)
    if keys - allowed:
        problems.append(f"unexpected fields: {sorted(keys - allowed)}")
    if allowed - keys:
        problems.append(f"missing fields: {sorted(allowed - keys)}")
    if row.get("schema") != CALL_EVENT_SCHEMA:
        problems.append(f"schema must be {CALL_EVENT_SCHEMA}")
    if not _text(row.get("id")).startswith("ece-"):
        problems.append("id must be a stable ece-* id")
    for field in (
        "source_record_id", "ticker", "quarter", "call_date", "source_type",
        "source_url", "source_sha256", "source_updated_at", "scored_at",
        "model", "prompt_version", "analysis_schema_version", "tone_word",
    ):
        if not isinstance(row.get(field), str) or not row.get(field):
            problems.append(f"{field} must be a non-empty string")
    if row.get("id") != make_call_event_id(_text(row.get("source_record_id"))):
        problems.append("id does not match source_record_id")
    if not _QUARTER_RE.fullmatch(_text(row.get("quarter"))):
        problems.append("quarter must be Q1..Q4")
    if not isinstance(row.get("year"), int) or isinstance(row.get("year"), bool):
        problems.append("year must be an integer")
    if not _SHA256_RE.fullmatch(_text(row.get("source_sha256")).lower()):
        problems.append("source_sha256 must be 64 lowercase hex chars")
    try:
        _event_timeline(
            row.get("call_date"),
            row.get("source_updated_at"),
            row.get("scored_at"),
        )
    except ValueError as exc:
        problems.append(str(exc))
    try:
        _source_url(row.get("source_url"))
    except ValueError as exc:
        problems.append(str(exc))
    for field, lo, hi in (
        ("sentiment", -1.0, 1.0),
        ("performance", 0.0, 10.0),
        ("confidence", 0.0, 1.0),
    ):
        try:
            _float(row.get(field), lo, hi)
        except ValueError as exc:
            problems.append(f"{field}: {exc}")
    if row.get("summary") is not None and not isinstance(row.get("summary"), str):
        problems.append("summary must be a string or null")
    if isinstance(row.get("summary"), str) and len(row["summary"]) > _MAX_SUMMARY:
        problems.append(f"summary exceeds {_MAX_SUMMARY} chars")
    for field, limit in (
        ("positive_highlights", _MAX_HIGHLIGHTS),
        ("negative_highlights", _MAX_HIGHLIGHTS),
        ("tags", _MAX_TAGS),
    ):
        value = row.get(field)
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            problems.append(f"{field} must be a string array")
        elif len(value) > limit:
            problems.append(f"{field} exceeds {limit} items")
    if row.get("is_context_only") is not True:
        problems.append("is_context_only must be true")
    return problems


def project_score_row(
    row: Any, *, as_of: date | datetime | str | None = None,
) -> dict:
    """Project one healthy scorer row into the committed public-safe contract."""

    get = row.get if hasattr(row, "get") else lambda key, default=None: default
    if _text(get("degraded_reason")):
        raise ValueError("degraded score rows are not projectable")
    context_value = get("is_context_only")
    if _missing(context_value) or str(context_value).strip().lower() not in {"true", "1"}:
        raise ValueError("score row is not context-only")

    source_record_id = _text(get("source_record_id"), max_len=300)
    if not source_record_id:
        raise ValueError("source_record_id is absent")
    ticker = _text(get("ticker"), max_len=32).upper()
    quarter = _text(get("quarter"), max_len=2).upper()
    if not ticker:
        raise ValueError("ticker is absent")
    if not _QUARTER_RE.fullmatch(quarter):
        raise ValueError(f"quarter is invalid: {quarter!r}")
    try:
        year = int(get("year"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"year is invalid: {get('year')!r}") from exc

    # New workers persist the canonical upstream body revision, which includes
    # metadata corrections such as call_date. Legacy healthy rows predate that
    # column and retain the rendered-text hash as a safe compatibility fallback.
    source_hash = _text(
        get("source_revision_sha256") or get("source_sha256"),
        max_len=64,
    ).lower()
    if not _SHA256_RE.fullmatch(source_hash):
        raise ValueError("source_sha256 is absent or invalid")

    call_date, source_updated_at, scored_at = _event_timeline(
        get("call_date"), get("source_updated_at"), get("scored_at"),
        as_of=_as_of_datetime(as_of),
    )
    summary = _text(get("summary"), max_len=_MAX_SUMMARY) or None
    event = {
        "schema": CALL_EVENT_SCHEMA,
        "id": make_call_event_id(source_record_id),
        "source_record_id": source_record_id,
        "ticker": ticker,
        "quarter": quarter,
        "year": year,
        "call_date": call_date,
        "source_type": _text(get("source"), max_len=40),
        "source_url": _source_url(get("source_url")),
        "source_sha256": source_hash,
        "source_updated_at": source_updated_at,
        "scored_at": scored_at,
        "model": _text(get("model"), max_len=120),
        "prompt_version": _text(get("prompt_version"), max_len=120),
        "analysis_schema_version": _text(get("analysis_schema_version"), max_len=120),
        "sentiment": _float(get("sentiment"), -1.0, 1.0),
        "performance": _float(get("performance"), 0.0, 10.0),
        "confidence": _float(get("confidence"), 0.0, 1.0),
        "tone_word": _text(get("tone_word"), max_len=40) or "unclassified",
        "summary": summary,
        "positive_highlights": _string_list(
            get("positive_highlights"), max_items=_MAX_HIGHLIGHTS,
            max_len=_MAX_HIGHLIGHT,
        ),
        "negative_highlights": _string_list(
            get("negative_highlights"), max_items=_MAX_HIGHLIGHTS,
            max_len=_MAX_HIGHLIGHT,
        ),
        "tags": _string_list(
            get("tags"), max_items=_MAX_TAGS, max_len=80, tags=True,
        ),
        "is_context_only": True,
    }
    problems = validate_call_event(event)
    if problems:
        raise ValueError("; ".join(problems))
    return event


def _sort_rows(rows: list[dict]) -> list[dict]:
    return sorted(rows, key=lambda row: (row.get("call_date") or "", row.get("id") or ""))


def _read_ledger(repo: Path) -> tuple[list[dict], str | None, bool]:
    """Return ``(rows, gap, safe_to_write)`` without ever raising."""

    path = Path(repo) / CALL_EVENTS_REL
    if not path.exists():
        return [], f"{CALL_EVENTS_REL} absent", True
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception as exc:  # noqa: BLE001
        return [], f"{CALL_EVENTS_REL} unreadable: {exc}", False

    rows: list[dict] = []
    problems: list[str] = []
    seen: set[str] = set()
    for lineno, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except Exception as exc:  # noqa: BLE001
            problems.append(f"line {lineno} invalid JSON ({exc})")
            continue
        violations = validate_call_event(row)
        if violations:
            problems.append(f"line {lineno} invalid ({'; '.join(violations)})")
            continue
        if row["id"] in seen:
            problems.append(f"line {lineno} duplicates id {row['id']}")
            continue
        seen.add(row["id"])
        rows.append(row)

    if problems:
        return _sort_rows(rows), (
            f"{len(problems)} invalid committed earnings-call row(s); "
            f"first: {problems[0]}"
        ), False
    if not rows:
        return [], f"{CALL_EVENTS_REL} has no rows yet", True
    return _sort_rows(rows), None, True


def load_call_events(repo: Path) -> tuple[list[dict], str | None]:
    """Read the committed ledger for adapters/inspectors, fail-soft."""

    rows, gap, _safe = _read_ledger(Path(repo))
    return rows, gap


def latest_for_ticker(
    repo: Path,
    ticker: str,
    *,
    as_of: date | datetime | str | None = None,
) -> dict | None:
    """Return the newest valid committed call row for ``ticker``.

    This is the small read contract for ticker-scoped consumers.  It reads only
    the committed ``earnings.call_event.v1`` ledger — never the mutable score
    parquet and never a transcript body — and fails closed when any committed
    row is invalid.  Returning a copy prevents a caller from mutating the
    in-memory row it was handed.

    ``call_date`` is the primary clock.  The remaining lineage fields form a
    deterministic tie-breaker for multiple calls recorded on the same date;
    they do not turn model scores into ranking authority.
    """

    wanted = _text(ticker, max_len=32).upper()
    if not wanted:
        return None
    rows, gap, safe_to_read = _read_ledger(Path(repo))
    if not safe_to_read:
        log.warning(
            "chronicle.earnings_calls: latest_for_ticker refused invalid ledger (%s)",
            gap or "unknown validation failure",
        )
        return None
    ceiling = _as_of_datetime(as_of)
    candidates = [
        row for row in rows
        if row.get("ticker") == wanted and call_event_available_as_of(row, ceiling)
    ]
    if not candidates:
        return None
    winner = max(
        candidates,
        key=lambda row: (
            row.get("call_date") or "",
            int(row.get("year") or 0),
            int(str(row.get("quarter") or "Q0")[1:] or 0),
            row.get("source_updated_at") or "",
            row.get("scored_at") or "",
            row.get("source_sha256") or "",
            row.get("id") or "",
        ),
    )
    return sanitize_call_event_evidence(winner)


def _canonical_bytes(rows: list[dict]) -> bytes:
    chunks = [
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for row in _sort_rows(rows)
    ]
    return (("\n".join(chunks) + "\n") if chunks else "").encode("utf-8")


def _write_ledger(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=path.parent, prefix=".tmp_", suffix=".jsonl")
    try:
        with os.fdopen(tmp_fd, "wb") as handle:
            handle.write(_canonical_bytes(rows))
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except Exception:  # noqa: BLE001
            pass
        raise


def _nightly_lane() -> bool:
    lane = os.environ.get("COLLECT_LANE", "") or os.environ.get("US_LANE", "")
    return lane.lower() == "nightly"


def sync_from_scores(
    repo: Path,
    *,
    rebuild: bool = False,
    as_of: date | datetime | str | None = None,
) -> dict[str, Any]:
    """Advance the committed projection from the current healthy score store.

    This function never raises and never deletes a ledger row.  ``updated`` is
    true only when canonical ledger bytes changed.
    """

    repo = Path(repo)
    result: dict[str, Any] = {
        "updated": False,
        "reason": None,
        "input_rows": 0,
        "healthy_rows": 0,
        "degraded_rows": 0,
        "rejected_rows": 0,
        "added": 0,
        "corrected": 0,
        "total_rows": 0,
    }
    if rebuild:
        result["reason"] = "rebuild_skipped"
        return result
    if not _nightly_lane():
        result["reason"] = "lane_gate"
        return result

    existing, ledger_gap, safe_to_write = _read_ledger(repo)
    result["total_rows"] = len(existing)
    if not safe_to_write:
        result["reason"] = "committed_ledger_invalid"
        result["gap"] = ledger_gap
        return result

    try:
        from engine import earnings_qual  # noqa: PLC0415
        score_path = earnings_qual.store_path(repo)
        if not score_path.exists():
            result["reason"] = "score_store_absent"
            return result
        frame = earnings_qual.load_scores(repo)
    except Exception as exc:  # noqa: BLE001
        result["reason"] = "score_store_unreadable"
        result["gap"] = str(exc)
        return result

    result["input_rows"] = int(len(frame))
    if frame.empty:
        result["reason"] = "score_store_empty_or_rejected"
        return result

    projected: dict[str, dict] = {}
    ceiling = _as_of_datetime(as_of)
    for _, score in frame.iterrows():
        if _text(score.get("degraded_reason")):
            result["degraded_rows"] += 1
            continue
        try:
            event = project_score_row(score, as_of=ceiling)
        except Exception as exc:  # noqa: BLE001
            result["rejected_rows"] += 1
            log.debug("chronicle.earnings_calls: rejected score row: %s", exc)
            continue
        current = projected.get(event["id"])
        if current is None or (
            event["source_updated_at"], event["scored_at"], event["source_sha256"]
        ) > (
            current["source_updated_at"], current["scored_at"], current["source_sha256"]
        ):
            projected[event["id"]] = event

    result["healthy_rows"] = len(projected)
    if not projected:
        result["reason"] = "no_healthy_projectable_rows"
        return result

    merged = {row["id"]: row for row in existing}
    for event_id, event in projected.items():
        prior = merged.get(event_id)
        if prior is None:
            result["added"] += 1
        elif prior == event:
            continue
        elif (
            event["source_updated_at"], event["scored_at"]
        ) <= (
            prior["source_updated_at"], prior["scored_at"]
        ):
            # A delayed/rolled-back score-store snapshot must not unwind a
            # newer committed correction.  Equal lineage with divergent bytes
            # is ambiguous, so the committed last-good row also wins.
            continue
        else:
            result["corrected"] += 1
        merged[event_id] = event

    rows = _sort_rows(list(merged.values()))
    desired = _canonical_bytes(rows)
    path = repo / CALL_EVENTS_REL
    try:
        current_bytes = path.read_bytes() if path.exists() else b""
    except Exception as exc:  # noqa: BLE001
        result["reason"] = "committed_ledger_unreadable"
        result["gap"] = str(exc)
        return result
    result["total_rows"] = len(rows)
    if desired == current_bytes:
        result["reason"] = "current"
        return result
    try:
        _write_ledger(path, rows)
    except Exception as exc:  # noqa: BLE001
        result["reason"] = "write_failed"
        result["gap"] = str(exc)
        return result
    result["updated"] = True
    result["reason"] = "updated"
    return result


def adapt_earnings_calls(
    repo: Path, *, as_of: date | datetime | str | None = None,
) -> tuple[list[dict], str | None]:
    """Project committed call-event rows into ``chronicle.event.v1``."""

    rows, gap = load_call_events(Path(repo))
    events: list[dict] = []
    skipped = 0
    ceiling = _as_of_datetime(as_of)
    for raw_row in rows:
        try:
            if not call_event_available_as_of(raw_row, ceiling):
                skipped += 1
                continue
            row = sanitize_call_event_evidence(raw_row)
            period = f"{row['quarter']} FY{row['year']}"
            facts: list[str] = [
                (
                    f"Tone {row['tone_word']} · sentiment {row['sentiment']:+.2f} · "
                    f"performance {row['performance']:.1f}/10 · "
                    f"confidence {row['confidence']:.2f}"
                )
            ]
            if row.get("summary"):
                facts.append(row["summary"])
            facts.extend(f"Positive: {item}" for item in row["positive_highlights"])
            facts.extend(f"Risk: {item}" for item in row["negative_highlights"])
            themes = ["earnings", "earnings_call", *row["tags"]]
            events.append(schema.new_event(
                # Date is deliberately excluded from the id material. A source
                # correction that fixes call_date must replace, not fork, the
                # same Chronicle event.
                id=schema.make_id("earnings_call", row["id"]),
                ts=f"{row['call_date']}T00:00:00Z",
                date=row["call_date"],
                source="earnings_call",
                source_ref=row["source_record_id"],
                kind="earnings",
                title=f"Earnings call: {row['ticker']} {period} — {row['tone_word']}",
                facts=facts,
                tickers=[row["ticker"]],
                themes=themes,
                # Fixed context salience. The model's sentiment/performance
                # values never originate Chronicle rank/gate/size authority.
                weight_hint=2,
                links=schema.make_links(
                    source=row["source_url"],
                    receipt=f"sha256:{row['source_sha256']}",
                ),
            ))
        except Exception as exc:  # noqa: BLE001
            skipped += 1
            log.debug("chronicle.earnings_calls: skipped committed row: %s", exc)

    notes: list[str] = []
    if gap:
        notes.append(gap)
    if skipped:
        notes.append(f"{skipped} committed call-event row(s) skipped")
    return events, "; ".join(notes) if notes else None
