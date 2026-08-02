"""Integrity and shrink-floor checks for immutable Company Intelligence views."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .contracts import (
    ContractError,
    bytes_sha256,
    canonical_json_bytes,
    validate_context,
    validate_manifest,
)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def enforce_shrink_floor(
    candidate: Mapping[str, Any],
    prior: Mapping[str, Any] | None,
    *,
    floor: float = 0.5,
) -> tuple[bool, str | None]:
    """Refuse a likely partial-tree publication against a last-good manifest."""
    source_ok, source_reason = reconcile_source_manifest(candidate)
    if not source_ok:
        return False, source_reason
    # A source-completeness warning may legitimately mark a structurally valid
    # last publication as ``degraded``.  It is still a last-good *tree* and must
    # protect against a later partial checkout clobbering it.
    if not isinstance(prior, Mapping) or prior.get("status") not in {"ready", "degraded"}:
        return True, None
    if not 0 < floor <= 1:
        raise ValueError("shrink floor must be within (0, 1]")
    for field in ("company_count", "event_count"):
        old = prior.get(field)
        new = candidate.get(field)
        if isinstance(old, int) and old > 0 and isinstance(new, int) and new < old * floor:
            return False, f"{field} shrink rejected: {old} -> {new} (floor {floor:.0%})"
    return True, None


def reconcile_source_manifest(candidate: Mapping[str, Any]) -> tuple[bool, str | None]:
    """Check projection cardinality against declared upstream source facts.

    The earnings source manifest exposes raw row/ticker counts.  We use only
    mathematical invariants here: fiscal-period dedupe and the public history
    cap may *reduce* rows, so this never guesses a coverage percentage.  It
    nevertheless catches a partial projection that cannot possibly represent
    its stated source baseline.
    """
    source = candidate.get("source") if isinstance(candidate, Mapping) else None
    earnings = source.get("earnings_manifest") if isinstance(source, Mapping) else None
    observed = earnings.get("observed_counts") if isinstance(earnings, Mapping) else None
    if not isinstance(observed, Mapping):
        return True, None
    def count(name: str) -> int | None:
        value = observed.get(name)
        return value if isinstance(value, int) and value >= 0 else None

    history_rows = count("history_rows")
    history_tickers = count("history_tickers")
    score_tickers = count("score_tickers")
    operational = candidate.get("operational") if isinstance(candidate, Mapping) else None
    rejected = operational.get("history_rows_rejected", 0) if isinstance(operational, Mapping) else 0
    rejected = rejected if isinstance(rejected, int) and rejected >= 0 else 0
    companies = candidate.get("company_count")
    events = candidate.get("event_count")
    if not isinstance(companies, int) or companies < 0 or not isinstance(events, int) or events < 0:
        return False, "candidate cardinalities invalid"
    declared_tickers = max(value for value in (history_tickers, score_tickers) if value is not None) if any(
        value is not None for value in (history_tickers, score_tickers)
    ) else None
    # One rejected row can remove at most one projected ticker; preserving that
    # allowance keeps an audited quarantine from creating a false publish stop.
    if declared_tickers is not None and companies < max(0, declared_tickers - rejected):
        return False, f"source ticker reconciliation rejected: declared {declared_tickers}, projected {companies}, rejected rows {rejected}"
    if history_rows is not None:
        valid_rows = max(0, history_rows - rejected)
        if events > valid_rows:
            return False, f"source history reconciliation rejected: projected events {events} exceed valid source rows {valid_rows}"
        if valid_rows > 0 and events == 0:
            return False, "source history reconciliation rejected: nonempty valid source produced zero events"
    return True, None


def validate_generation(out_dir: Path, manifest: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Verify marker → immutable generation → context hashes and counts."""
    marker_path = out_dir / "manifest.json"
    payload = dict(manifest) if isinstance(manifest, Mapping) else _read_json(marker_path)
    if payload is None:
        return {"status": "empty", "warnings": ["manifest_missing"], "company_count": 0, "event_count": 0}
    try:
        validate_manifest(payload)
    except ContractError as exc:
        return {"status": "degraded", "warnings": [f"manifest_invalid:{exc}"], "company_count": 0, "event_count": 0}
    generation_dir = out_dir / "generations" / str(payload["generation_id"])
    warnings: list[str] = []
    immutable_manifest_path = generation_dir / "manifest.json"
    immutable_manifest = _read_json(immutable_manifest_path)
    if immutable_manifest is None:
        warnings.append("generation_manifest_missing")
    elif canonical_json_bytes(immutable_manifest) != canonical_json_bytes(payload):
        warnings.append("generation_manifest_mismatch")
    actual_events = 0
    for relative, expected in sorted((payload.get("files") or {}).items()):
        path = generation_dir / relative
        if not path.is_file():
            warnings.append(f"file_missing:{relative}")
            continue
        if path.stat().st_size != expected.get("bytes"):
            warnings.append(f"file_bytes_mismatch:{relative}")
            continue
        if bytes_sha256(path) != expected.get("sha256"):
            warnings.append(f"file_hash_mismatch:{relative}")
            continue
        context = _read_json(path)
        try:
            validate_context(context)
            if context is None or context.get("generation_id") != payload["generation_id"]:
                raise ContractError("context generation mismatch")
            actual_events += len(context.get("history") or [])
        except ContractError as exc:
            warnings.append(f"context_invalid:{relative}:{exc}")
    if len(payload.get("files") or {}) != int(payload.get("company_count") or 0):
        warnings.append("company_count_mismatch")
    if actual_events != int(payload.get("event_count") or 0):
        warnings.append("event_count_mismatch")
    if not payload.get("files") and payload.get("status") == "empty" and not warnings:
        status = "empty"
    else:
        status = "degraded" if warnings else "ready"
    return {
        "status": status,
        "warnings": warnings,
        "company_count": int(payload.get("company_count") or 0),
        "event_count": int(payload.get("event_count") or 0),
        "generation_id": payload.get("generation_id"),
    }


def build_health(out_dir: Path) -> dict[str, Any]:
    """Alias used by simple health builders and external monitoring."""
    return validate_generation(out_dir)
