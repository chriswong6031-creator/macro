"""engine/news_event_ledger.py — PIT event log and reject-sample store (W4).

LEAF · CONTEXT-ONLY · DISPLAY-ONLY. Imports nothing from the mechanical scoring
core (conditions/regime/run/inputs/equity_alloc). Every public function degrades
gracefully — exceptions are logged and swallowed; the build is never broken.

Point-in-time discipline:
  • persist_kept_events / persist_reject_sample operate keep-FIRST:
    event_id is the dedup key; first_seen_utc is NEVER overwritten on re-ingest.
  • All parquet writes are append-then-dedup to preserve PIT ordering.

Data paths:
  data/news/event_log.parquet    — kept events with event classification metadata
  data/news/reject_sample.parquet — sampled reject rows (up to k per feed per day)

is_context_only = True  (schema contract)
"""
from __future__ import annotations

import json
import logging
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("news_event_ledger")

is_context_only: bool = True

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
_EVENT_LOG_REL = ("data", "news", "event_log.parquet")
_REJECT_SAMPLE_REL = ("data", "news", "reject_sample.parquet")


def _root_path() -> Path:
    """Repo root derived from this file's location — avoids a lib.config import
    at module level (LEAF / CONTEXT-ONLY constraint)."""
    try:
        from lib import config  # noqa: PLC0415
        return config.ROOT
    except Exception:  # noqa: BLE001
        return Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------- #
# Parquet helpers — lazy pandas import, never raises into caller
# --------------------------------------------------------------------------- #
def _read_parquet_safe(p: Path):
    """Read a parquet file. Returns None if absent or unreadable."""
    if not p.exists():
        return None
    try:
        import pandas as pd  # noqa: PLC0415
        return pd.read_parquet(p)
    except Exception as exc:  # noqa: BLE001
        log.debug("_read_parquet_safe(%s): %s", p, exc)
        return None


def _write_parquet_atomic(df, p: Path) -> None:
    """Write a DataFrame to parquet atomically via a .tmp file."""
    import pandas as pd  # noqa: PLC0415
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".parquet.tmp")
    df.to_parquet(tmp, index=False)
    tmp.replace(p)


# --------------------------------------------------------------------------- #
# Row schemas (column definitions; anything missing becomes None/NaN)
# --------------------------------------------------------------------------- #
_EVENT_LOG_COLS = [
    "event_id",         # str — dedup key (news_common.event_id)
    "first_seen_utc",   # str ISO-8601 — NEVER overwritten (keep-FIRST)
    "seendate",         # str ISO-8601 — publisher date from headline dict
    "title",            # str
    "domain",           # str
    "source_tier",      # str — honest label from news engine (e.g. 'stock_wire', 'tier1', 'quality', 'official'); never int-cast (would raise on string values)
    "event_type",       # str — from classify_event
    "direction",        # str — bullish|bearish|mixed|informational
    "centrality",       # str|None — primary|secondary|incidental
    "tickers",          # str (JSON-encoded list) — may be empty "[]"
    "theme",            # str|None
    "novelty_z",        # float|None
]

_REJECT_SAMPLE_COLS = [
    "event_id",         # str — dedup key
    "first_seen_utc",   # str ISO-8601
    "seendate",         # str
    "title",            # str
    "domain",           # str
    "feed",             # str — which feed produced this reject
    "reason",           # str — low_value_reason token
    "tickers",          # str (JSON-encoded list)
]


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def persist_kept_events(
    headlines: list[dict],
    asof_utc: str | None = None,
    root: Path | str | None = None,
) -> int:
    """Append classified kept events to data/news/event_log.parquet.

    Rows where event_type is None (i.e. headline.get('event') is None or the
    event dict lacks a name) are skipped — only actual typed events are logged.

    Keep-FIRST: if an event_id already exists in the store, the existing row
    (including first_seen_utc) is preserved and the new row is silently dropped.

    Returns the number of NEW rows written. Degrades gracefully on any error.
    """
    if not headlines:
        return 0
    try:
        return _persist_kept_events_inner(headlines, asof_utc, root)
    except Exception as exc:  # noqa: BLE001 — degrade-never-raise
        log.warning("persist_kept_events failed (non-fatal): %s", exc)
        return 0


def _persist_kept_events_inner(
    headlines: list[dict],
    asof_utc: str | None,
    root: Path | str | None,
) -> int:
    import pandas as pd  # noqa: PLC0415

    root_p = Path(root) if root else _root_path()
    out_path = root_p.joinpath(*_EVENT_LOG_REL)
    now_iso = asof_utc or datetime.now(timezone.utc).isoformat()

    existing = _read_parquet_safe(out_path)
    seen_ids: set[str] = set()
    if existing is not None and "event_id" in existing.columns:
        seen_ids = set(existing["event_id"].dropna().astype(str).tolist())

    new_rows: list[dict] = []
    for h in headlines:
        ev = h.get("event")
        if not ev:
            continue
        event_type = ev.get("event_type") or ev.get("name")
        if not event_type:
            continue
        direction = ev.get("direction", "")
        # Compute event_id using the canonical function
        eid = _event_id_for(h)
        if eid in seen_ids:
            continue
        seen_ids.add(eid)
        tickers = h.get("tickers") or h.get("entities") or []
        if not isinstance(tickers, list):
            tickers = list(tickers) if tickers else []
        new_rows.append({
            "event_id": eid,
            "first_seen_utc": now_iso,
            "seendate": str(h.get("seendate") or h.get("pubdate") or ""),
            "title": str(h.get("title") or ""),
            "domain": str(h.get("domain") or ""),
            "source_tier": str(h.get("source_tier") or h.get("tier") or ""),
            "event_type": str(event_type),
            "direction": str(direction),
            "centrality": h.get("centrality") or None,
            "tickers": json.dumps(sorted(set(str(t) for t in tickers))),
            "theme": h.get("theme") or None,
            "novelty_z": _float_or_none(h.get("novelty_z")),
        })

    if not new_rows:
        return 0

    new_df = pd.DataFrame(new_rows, columns=_EVENT_LOG_COLS)
    if existing is not None and len(existing):
        # Ensure consistent dtypes before concat
        combined = pd.concat([existing, new_df], ignore_index=True)
    else:
        combined = new_df

    _write_parquet_atomic(combined, out_path)
    return len(new_rows)


def persist_reject_sample(
    rejected_by_feed: dict[str, list[dict]],
    asof_utc: str | None = None,
    k: int = 25,
    root: Path | str | None = None,
) -> int:
    """Sample up to k rejects per feed per day into data/news/reject_sample.parquet.

    rejected_by_feed: {feed_name: [headline_dicts_with_reason_field]}
    Each headline dict is expected to carry 'reason' (the low_value_reason token).
    Tickers are extracted best-effort from the 'tickers'/'entities' field if present.

    Keep-FIRST: duplicate event_ids are silently dropped.
    Returns number of new rows written.
    """
    if not rejected_by_feed:
        return 0
    try:
        return _persist_reject_sample_inner(rejected_by_feed, asof_utc, k, root)
    except Exception as exc:  # noqa: BLE001 — degrade-never-raise
        log.warning("persist_reject_sample failed (non-fatal): %s", exc)
        return 0


def _persist_reject_sample_inner(
    rejected_by_feed: dict[str, list[dict]],
    asof_utc: str | None,
    k: int,
    root: Path | str | None,
) -> int:
    import pandas as pd  # noqa: PLC0415

    root_p = Path(root) if root else _root_path()
    out_path = root_p.joinpath(*_REJECT_SAMPLE_REL)
    now_iso = asof_utc or datetime.now(timezone.utc).isoformat()

    existing = _read_parquet_safe(out_path)
    seen_ids: set[str] = set()
    if existing is not None and "event_id" in existing.columns:
        seen_ids = set(existing["event_id"].dropna().astype(str).tolist())

    new_rows: list[dict] = []
    for feed, items in rejected_by_feed.items():
        if not items:
            continue
        sample = items if len(items) <= k else random.sample(items, k)
        for h in sample:
            eid = _event_id_for(h)
            if eid in seen_ids:
                continue
            seen_ids.add(eid)
            tickers = h.get("tickers") or h.get("entities") or []
            if not isinstance(tickers, list):
                tickers = list(tickers) if tickers else []
            new_rows.append({
                "event_id": eid,
                "first_seen_utc": now_iso,
                "seendate": str(h.get("seendate") or h.get("pubdate") or ""),
                "title": str(h.get("title") or ""),
                "domain": str(h.get("domain") or ""),
                "feed": str(feed),
                "reason": str(h.get("reason") or h.get("reject_reason") or "unknown"),
                "tickers": json.dumps(sorted(set(str(t) for t in tickers))),
            })

    if not new_rows:
        return 0

    new_df = pd.DataFrame(new_rows, columns=_REJECT_SAMPLE_COLS)
    if existing is not None and len(existing):
        combined = pd.concat([existing, new_df], ignore_index=True)
    else:
        combined = new_df

    _write_parquet_atomic(combined, out_path)
    return len(new_rows)


# --------------------------------------------------------------------------- #
# Utility helpers (internal)
# --------------------------------------------------------------------------- #
def _event_id_for(h: dict) -> str:
    """Derive the canonical event_id for a headline dict.

    Prefers h.get('event_id') if already present (set by upstream), then
    delegates to news_common.event_id(title, domain) — the canonical dedup key.
    """
    if h.get("event_id"):
        return str(h["event_id"])
    try:
        from engine.news_common import event_id as _nc_eid  # noqa: PLC0415
        return _nc_eid(str(h.get("title") or ""), str(h.get("domain") or ""))
    except Exception:  # noqa: BLE001
        # Fallback: simple hash of title+domain (never raises)
        import hashlib  # noqa: PLC0415
        raw = f"{h.get('title', '')}|{h.get('domain', '')}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _float_or_none(v: Any) -> float | None:
    """Cast to native float, return None when not numeric."""
    if v is None:
        return None
    try:
        f = float(v)
        return f if f == f else None  # NaN check
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- #
# Reader helpers — used by grade_news_events.py
# --------------------------------------------------------------------------- #
def load_event_log(root: Path | str | None = None):
    """Load data/news/event_log.parquet. Returns DataFrame or None."""
    root_p = Path(root) if root else _root_path()
    return _read_parquet_safe(root_p.joinpath(*_EVENT_LOG_REL))


def load_reject_sample(root: Path | str | None = None):
    """Load data/news/reject_sample.parquet. Returns DataFrame or None."""
    root_p = Path(root) if root else _root_path()
    return _read_parquet_safe(root_p.joinpath(*_REJECT_SAMPLE_REL))
