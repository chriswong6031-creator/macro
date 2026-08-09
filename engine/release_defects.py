"""Structured defect classification for Release Radar evaluation.

The forward ledger is immutable: a bad forecast or an incorrectly constructed
actual is never deleted or rewritten.  This module supplies the other half of
that contract by deciding whether a row may be used for model selection,
promotion review, or maturity counts.

Defect notices remain ordinary JSON records.  A notice affects evaluation only
when it explicitly carries ``evaluation_excluded=true`` and a matching
``selector``.  Prose-only notices therefore cannot silently change arithmetic.
"""
from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

_ACTUAL_BASIS_RANK = {
    "official_published_metric": 300,
    "same_release_vintage_published_proxy": 200,
    "official_initial_level": 150,
    "legacy_cross_vintage_level_change": 0,
}


def load_defect_notices(path_or_root: str | Path | None) -> list[dict[str, Any]]:
    """Load notices from a repo root, notice file, or release-forecast directory.

    Missing or malformed files fail open to an empty list.  Callers that use the
    result for promotion must surface the missing-notice condition separately;
    this helper deliberately stays pure and non-raising for nightly resilience.
    """
    if path_or_root is None:
        return []
    path = Path(path_or_root)
    if path.is_dir():
        direct = path / "defect_notices.json"
        nested = path / "data" / "release_forecast" / "defect_notices.json"
        path = direct if direct.exists() else nested
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        notices = payload.get("notices") if isinstance(payload, dict) else None
        return [row for row in (notices or []) if isinstance(row, dict)]
    except (OSError, ValueError, TypeError):
        return []


def _model_id(row: dict[str, Any]) -> str:
    return str(row.get("model") or "champion")


def _in(values: Any, candidate: Any) -> bool:
    if not isinstance(values, list) or not values:
        return True
    return "*" in values or candidate in values


def _date_in_range(value: Any, bounds: Any) -> bool:
    if not isinstance(bounds, list) or len(bounds) != 2:
        return True
    stamp = str(value or "")[:10]
    return bool(stamp) and str(bounds[0])[:10] <= stamp <= str(bounds[1])[:10]


def _matches_selector(row: dict[str, Any], selector: dict[str, Any]) -> bool:
    if not _in(selector.get("row_types"), row.get("row_type")):
        return False
    if not _in(selector.get("release_types"), row.get("release")):
        return False
    if not _in(selector.get("models"), _model_id(row)):
        return False
    if not _in(selector.get("target_epochs"), row.get("target_epoch")):
        return False
    if not _in(selector.get("model_epochs"), row.get("model_epoch")):
        return False

    frozen_asof = row.get("frozen_asof_night") or row.get("asof_night")
    if not _date_in_range(frozen_asof, selector.get("frozen_asof_range")):
        return False
    if not _date_in_range(row.get("period"), selector.get("period_range")):
        return False

    if selector.get("actual_source_missing") is True and row.get("actual_source"):
        return False
    return _in(selector.get("actual_sources"), row.get("actual_source"))


def matching_defect_ids(
    row: dict[str, Any], notices: Iterable[dict[str, Any]]
) -> list[str]:
    """Return explicit evaluation-excluding defect IDs matching ``row``."""
    matched: list[str] = []
    for notice in notices:
        if notice.get("evaluation_excluded") is not True:
            continue
        selector = notice.get("selector")
        if not isinstance(selector, dict) or not selector:
            continue
        if _matches_selector(row, selector):
            defect_id = str(notice.get("id") or "unknown_defect")
            if defect_id not in matched:
                matched.append(defect_id)
    return matched


def evaluation_status(
    row: dict[str, Any], notices: Iterable[dict[str, Any]]
) -> dict[str, Any]:
    """Return the stable evaluation receipt for one immutable ledger row."""
    defect_ids = matching_defect_ids(row, notices)
    return {
        "eligible": not defect_ids,
        "excluded_defect_ids": defect_ids,
        "basis": "structured_defect_notices_v1",
    }


def is_evaluation_eligible(
    row: dict[str, Any], notices: Iterable[dict[str, Any]]
) -> bool:
    return not matching_defect_ids(row, notices)


def _frozen_score_key(row: dict[str, Any]) -> tuple[str, ...] | None:
    """Identity of one frozen forecast grade across later actual receipts.

    Minimal legacy/test rows can lack the period or frozen forecast date.  Such
    rows do not contain enough evidence to prove that they grade the same frozen
    prediction, so callers must keep them distinct rather than collapsing them
    on a tuple of empty strings.
    """
    # Existing production score rows predate frozen_prediction_id and epochs.
    # Always use the backward-compatible projection identity so an official
    # correction collapses with the legacy row it supersedes.
    release = str(row.get("release") or "")
    period = str(row.get("period") or "")
    frozen_asof = str(row.get("frozen_asof_night") or "")
    if not release or not period or not frozen_asof:
        return None
    return (release, period, str(row.get("model") or "champion"), frozen_asof)


def _actual_receipt_rank(row: dict[str, Any]) -> int:
    basis = str(row.get("actual_basis") or "")
    if basis in _ACTUAL_BASIS_RANK:
        return _ACTUAL_BASIS_RANK[basis]
    if row.get("actual_receipt_id"):
        return 100
    return 0


def canonical_scored_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Select one actual receipt per frozen forecast without mutating the ledger.

    Official published metrics outrank same-release-vintage proxies, which
    outrank receipt-less legacy calculations.  Ties keep the first append, so a
    later row can never silently rewrite an equally authoritative keep-first
    receipt.  Non-scored rows are ignored.
    """
    chosen: dict[tuple[str, ...], tuple[int, int, dict[str, Any]]] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or row.get("row_type") != "scored":
            continue
        frozen_key = _frozen_score_key(row)
        # A receipt without a complete frozen identity cannot safely supersede
        # another row.  The append index makes the key unique while preserving
        # deterministic ordering.
        key = frozen_key or ("incomplete_frozen_identity", str(index))
        rank = _actual_receipt_rank(row)
        prior = chosen.get(key)
        if prior is None or rank > prior[0]:
            chosen[key] = (rank, index, row)
    return [item[2] for item in sorted(chosen.values(), key=lambda item: item[1])]
