"""Incremental intake adapter for the Terminal transcript archive.

The Terminal publishes transcript bodies under ``/data/tx/<SYM>/<YYYYQn>.json.gz``
and writes ``/data/tx/index.json`` last as the reader-visible commit marker.  This
module turns that archive into a durable queue for the earnings qualitative
worker without copying the full corpus into a second flat transcript store.

The cursor is deliberately independent from model completion:

* discovery records every committed body revision exactly once;
* pending work survives process and provider failures;
* a model failure never rewinds or blocks Terminal publication;
* a corrected body (same symbol/id, new canonical hash) re-enters the queue;
* deleted/missing index pairs never erase last-good cursor history.

The current public index remains backward compatible with its original
``symbols`` map.  ``revisions`` and ``dates`` are optional extensions.  Without
``revisions`` the adapter still discovers new symbol/id pairs; correction
detection becomes available automatically when the producer publishes hashes.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote


INDEX_SCHEMA = "mastermind.tx-index/v1"
STATE_SCHEMA = "mastermind.earnings-transcript-intake/v1"
_TX_ID_RE = re.compile(r"^(\d{4})Q([1-4])$")
_PAIR_RE = re.compile(r"^([^/]+)/((?:\d{4})Q[1-4])$")


@dataclass(frozen=True)
class TranscriptRef:
    """One immutable transcript-body revision advertised by the global index."""

    ticker: str
    transcript_id: str
    body_sha256: str = ""
    call_date: str = ""

    @property
    def pair(self) -> str:
        return f"{self.ticker}/{self.transcript_id}"

    @property
    def revision_key(self) -> str:
        return f"{self.pair}@{self.body_sha256 or 'unversioned'}"


def canonical_body_sha256(payload: dict[str, Any]) -> str:
    """Hash canonical decompressed JSON, independent of gzip headers/key order."""

    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _clean_sha(raw: Any) -> str:
    value = str(raw or "").strip().lower()
    if not value:
        return ""
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError(f"invalid transcript body sha256: {raw!r}")
    return value


def _clean_date(raw: Any) -> str:
    value = str(raw or "").strip()
    if not value:
        return ""
    try:
        return date.fromisoformat(value[:10]).isoformat()
    except ValueError as exc:
        raise ValueError(f"invalid transcript date: {raw!r}") from exc


def parse_global_index(raw: object) -> tuple[list[TranscriptRef], dict[str, Any]]:
    """Validate a Terminal global index and return its advertised body refs."""

    if not isinstance(raw, dict) or raw.get("schema") != INDEX_SCHEMA:
        raise ValueError("invalid Terminal transcript global index schema")
    symbols = raw.get("symbols")
    if not isinstance(symbols, dict):
        raise ValueError("Terminal transcript index symbols must be an object")
    revisions = raw.get("revisions") or {}
    dates = raw.get("dates") or {}
    if not isinstance(revisions, dict) or not isinstance(dates, dict):
        raise ValueError("Terminal transcript revisions/dates must be objects")

    refs: list[TranscriptRef] = []
    seen_pairs: set[str] = set()
    for raw_ticker, raw_ids in symbols.items():
        if not isinstance(raw_ticker, str) or not isinstance(raw_ids, list):
            raise ValueError("Terminal transcript symbols must map strings to ID arrays")
        ticker = raw_ticker.strip().upper()
        if not ticker or "/" in ticker:
            raise ValueError(f"invalid transcript ticker: {raw_ticker!r}")
        for raw_id in raw_ids:
            tx_id = str(raw_id or "").strip().upper()
            if not _TX_ID_RE.fullmatch(tx_id):
                raise ValueError(f"invalid transcript ID for {ticker}: {raw_id!r}")
            pair = f"{ticker}/{tx_id}"
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            refs.append(
                TranscriptRef(
                    ticker=ticker,
                    transcript_id=tx_id,
                    body_sha256=_clean_sha(revisions.get(pair)),
                    call_date=_clean_date(dates.get(pair)),
                )
            )

    # Newest calls first; blank dates fall behind dated calls.  Fiscal ID and
    # ticker provide a deterministic fallback/order for legacy indexes.
    refs.sort(
        key=lambda ref: (ref.call_date, ref.transcript_id, ref.ticker),
        reverse=True,
    )
    metadata = {
        "generated_at": str(raw.get("generated_at") or ""),
        "body_count": int(raw.get("body_count") or len(refs)),
        "symbol_count": int(raw.get("symbol_count") or len(symbols)),
        "has_revisions": bool(revisions),
        "has_dates": bool(dates),
    }
    if metadata["body_count"] != len(refs):
        raise ValueError(
            "Terminal transcript index body_count mismatch: "
            f"declared={metadata['body_count']} parsed={len(refs)}"
        )
    return refs, metadata


def new_state(source: str) -> dict[str, Any]:
    return {
        "schema": STATE_SCHEMA,
        "source": source,
        "initialized": False,
        "known": {},
        "pending": [],
        "last_index_generated_at": "",
        "updated_at": "",
    }


def load_state(path: Path, *, source: str) -> dict[str, Any]:
    """Load a cursor, returning a new empty state when none exists."""

    path = Path(path)
    if not path.exists():
        return new_state(source)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"cannot read transcript intake state {path}: {exc}") from exc
    if not isinstance(raw, dict) or raw.get("schema") != STATE_SCHEMA:
        raise ValueError(f"invalid transcript intake state schema at {path}")
    if raw.get("source") and str(raw["source"]) != source:
        raise ValueError(
            f"transcript intake source changed: {raw['source']!r} != {source!r}"
        )
    known = raw.get("known")
    pending = raw.get("pending")
    if not isinstance(known, dict) or not isinstance(pending, list):
        raise ValueError("transcript intake state known/pending shape is invalid")
    # Validate pending rows by round-tripping the dataclass constructor.
    clean_pending: list[dict[str, str]] = []
    for item in pending:
        if not isinstance(item, dict):
            raise ValueError("transcript intake pending rows must be objects")
        ref = TranscriptRef(
            ticker=str(item.get("ticker") or "").strip().upper(),
            transcript_id=str(item.get("transcript_id") or "").strip().upper(),
            body_sha256=_clean_sha(item.get("body_sha256")),
            call_date=_clean_date(item.get("call_date")),
        )
        if not ref.ticker or "/" in ref.ticker or not _TX_ID_RE.fullmatch(ref.transcript_id):
            raise ValueError(f"invalid pending transcript ref: {item!r}")
        clean_pending.append(asdict(ref))
    raw["known"] = {str(k): _clean_sha(v) for k, v in known.items()}
    raw["pending"] = clean_pending
    raw["source"] = source
    return raw


def _atomic_write_json(path: Path, payload: object) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    try:
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def save_state(path: Path, state: dict[str, Any]) -> None:
    state = dict(state)
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    _atomic_write_json(Path(path), state)


def _pending_by_pair(state: dict[str, Any]) -> dict[str, TranscriptRef]:
    out: dict[str, TranscriptRef] = {}
    for item in state.get("pending") or []:
        ref = TranscriptRef(**item)
        out[ref.pair] = ref
    return out


def plan_index(
    refs: list[TranscriptRef],
    state: dict[str, Any],
    *,
    metadata: dict[str, Any] | None = None,
    seed_existing: bool = False,
    bootstrap_since: str | None = None,
) -> tuple[dict[str, Any], list[TranscriptRef]]:
    """Merge one committed index into the cursor and return current pending work.

    On first use callers must either seed the existing archive (forward-only) or
    provide ``bootstrap_since``.  This prevents a mistaken first run from trying
    to score the entire historical corpus.
    """

    metadata = metadata or {}
    out = dict(state)
    known = dict(out.get("known") or {})
    pending = _pending_by_pair(out)
    initialized = bool(out.get("initialized"))

    cutoff = _clean_date(bootstrap_since) if bootstrap_since else ""
    if not initialized and not seed_existing and not cutoff:
        raise ValueError(
            "first transcript intake requires seed_existing=True or bootstrap_since=YYYY-MM-DD"
        )
    if cutoff and not metadata.get("has_dates"):
        raise ValueError("bootstrap_since requires a Terminal index with the dates extension")

    for ref in refs:
        previous = known.get(ref.pair)
        if not initialized:
            known[ref.pair] = ref.body_sha256
            if cutoff and ref.call_date >= cutoff:
                pending[ref.pair] = ref
            continue

        if previous is None:
            # Brand-new body pair.
            known[ref.pair] = ref.body_sha256
            pending[ref.pair] = ref
        elif previous and ref.body_sha256 and previous != ref.body_sha256:
            # Same stable pair, corrected content. Replace any stale queued
            # revision with the latest advertised body revision.
            known[ref.pair] = ref.body_sha256
            pending[ref.pair] = ref
        elif not previous and ref.body_sha256:
            # Hash extension rollout for an already-known legacy pair is not a
            # correction. Upgrade the cursor silently to avoid a 25k-item replay.
            known[ref.pair] = ref.body_sha256

    ordered = sorted(
        pending.values(),
        key=lambda ref: (ref.call_date, ref.transcript_id, ref.ticker),
        reverse=True,
    )
    out["known"] = known
    out["pending"] = [asdict(ref) for ref in ordered]
    out["initialized"] = True
    out["last_index_generated_at"] = str(metadata.get("generated_at") or "")
    out["last_index_body_count"] = int(metadata.get("body_count") or len(refs))
    out["last_index_symbol_count"] = int(metadata.get("symbol_count") or 0)
    return out, ordered


def mark_completed(state: dict[str, Any], ref: TranscriptRef) -> dict[str, Any]:
    """Remove only the exact queued revision; a newer correction remains queued."""

    out = dict(state)
    kept: list[dict[str, str]] = []
    for item in out.get("pending") or []:
        candidate = TranscriptRef(**item)
        if candidate.pair == ref.pair and candidate.revision_key == ref.revision_key:
            continue
        kept.append(asdict(candidate))
    out["pending"] = kept
    return out


def fetch_global_index(base_url: str, *, timeout_s: float = 30) -> object:
    """Fetch the commit-marker index from a Terminal tx base URL."""

    import requests  # local import keeps deterministic tests dependency-light

    url = f"{str(base_url).rstrip('/')}/index.json"
    response = requests.get(
        url,
        headers={"Accept": "application/json", "Cache-Control": "no-cache"},
        timeout=float(timeout_s),
    )
    response.raise_for_status()
    return response.json()


def _validate_body(payload: object, ref: TranscriptRef) -> dict[str, Any]:
    if not isinstance(payload, dict) or payload.get("schema") != "mastermind.tx/v1":
        raise ValueError(f"invalid transcript body schema for {ref.pair}")
    ticker = str(payload.get("ticker") or "").strip().upper()
    tx_id = str(payload.get("id") or "").strip().upper()
    if ticker != ref.ticker or tx_id != ref.transcript_id:
        raise ValueError(
            f"transcript body identity mismatch: {ticker}/{tx_id} != {ref.pair}"
        )
    segments = payload.get("segments")
    if not isinstance(segments, list) or not segments:
        raise ValueError(f"transcript body has no segments: {ref.pair}")
    for i, segment in enumerate(segments):
        if not isinstance(segment, dict) or not isinstance(segment.get("text"), str):
            raise ValueError(f"invalid transcript segment {ref.pair}#{i}")
    actual_sha = canonical_body_sha256(payload)
    if ref.body_sha256 and actual_sha != ref.body_sha256:
        raise ValueError(
            f"transcript body hash mismatch for {ref.pair}: "
            f"{actual_sha} != {ref.body_sha256}"
        )
    return payload


def fetch_body(base_url: str, ref: TranscriptRef, *, timeout_s: float = 60) -> dict[str, Any]:
    """Fetch, decompress, schema-check, and hash-check one public body."""

    import requests

    ticker = quote(ref.ticker, safe=".-^")
    tx_id = quote(ref.transcript_id, safe="")
    url = f"{str(base_url).rstrip('/')}/{ticker}/{tx_id}.json.gz"
    response = requests.get(
        url,
        headers={"Accept": "application/gzip", "Cache-Control": "no-cache"},
        timeout=float(timeout_s),
    )
    response.raise_for_status()
    try:
        raw = gzip.decompress(response.content)
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"cannot decode transcript body {ref.pair}: {exc}") from exc
    return _validate_body(payload, ref)


def read_local_body(tx_root: Path, ref: TranscriptRef) -> dict[str, Any]:
    """Read the same archive contract from a local Terminal tx root."""

    path = Path(tx_root) / ref.ticker / f"{ref.transcript_id}.json.gz"
    try:
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"cannot read local transcript body {path}: {exc}") from exc
    return _validate_body(payload, ref)


def body_to_score_input(
    payload: dict[str, Any],
    *,
    index_generated_at: str = "",
) -> tuple[dict[str, Any], str]:
    """Map ``mastermind.tx/v1`` directly into the earnings scorer contract."""

    ticker = str(payload.get("ticker") or "").strip().upper()
    tx_id = str(payload.get("id") or "").strip().upper()
    match = _TX_ID_RE.fullmatch(tx_id)
    if not ticker or match is None:
        raise ValueError(f"invalid Terminal transcript identity: {ticker}/{tx_id}")

    rendered: list[str] = []
    for segment in payload.get("segments") or []:
        text = str(segment.get("text") or "").strip()
        if not text:
            continue
        speaker = str(segment.get("speaker") or "").strip()
        role = str(segment.get("role") or "").strip()
        label = speaker
        if role and role.lower() not in speaker.lower():
            label = f"{speaker} [{role}]" if speaker else role
        rendered.append(f"{label}: {text}" if label else text)
    body = "\n\n".join(rendered).strip()
    if not body:
        raise ValueError(f"Terminal transcript rendered empty: {ticker}/{tx_id}")

    score_input = {
        "ticker": ticker,
        "quarter": f"Q{match.group(2)}",
        "year": int(match.group(1)),
        "call_date": _clean_date(payload.get("date")),
        "source": "transcript",
        "source_record_id": f"defeatbeta:{ticker}:{tx_id}",
        "source_updated_at": index_generated_at,
        "terminal_url": f"/data/tx/{ticker}/{tx_id}.json.gz",
    }
    return score_input, body


def ref_from_pending(item: dict[str, Any]) -> TranscriptRef:
    """Public helper for worker code reading the persisted pending queue."""

    return TranscriptRef(
        ticker=str(item.get("ticker") or "").strip().upper(),
        transcript_id=str(item.get("transcript_id") or "").strip().upper(),
        body_sha256=_clean_sha(item.get("body_sha256")),
        call_date=_clean_date(item.get("call_date")),
    )


def split_pair(pair: str) -> tuple[str, str]:
    """Validate and split a stable ``SYM/YYYYQn`` pair."""

    match = _PAIR_RE.fullmatch(str(pair or "").strip())
    if match is None:
        raise ValueError(f"invalid transcript pair: {pair!r}")
    return match.group(1).upper(), match.group(2).upper()
