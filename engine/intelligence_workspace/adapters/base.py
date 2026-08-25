"""Shared, request-scoped read helpers for W1-A owner adapters."""
from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from ..contracts import AdapterResult


_SAFE_SYMBOL_RE = re.compile(r"^[A-Z0-9](?:[A-Z0-9.-]{0,22}[A-Z0-9])?$")


def safe_artifact_symbol(value: object) -> str:
    symbol = str(value or "").strip().upper()
    if not symbol or ".." in symbol or not _SAFE_SYMBOL_RE.fullmatch(symbol):
        raise ValueError(f"unsafe owner artifact symbol: {value!r}")
    return symbol


def read_json_once(context: Any, key: str, path: Path) -> dict[str, Any] | None:
    def _read() -> dict[str, Any] | None:
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    return context.memoize(key, _read)


def unavailable(
    spec: Any,
    *,
    reason_code: str,
    source_id: str,
    owner: str,
    license_class: str = "internal_derived",
    as_of: str | None = None,
    freshness_state: str = "unknown",
    quality_state: str = "unknown",
    issues: list[str] | None = None,
    artifact_id: str | None = None,
) -> AdapterResult:
    source = {
        "source_id": source_id,
        "owner": owner,
        "license_class": license_class,
        "dataset_id": None,
    }
    if artifact_id is not None:
        source["artifact_id"] = artifact_id
    return AdapterResult(
        value=None,
        status="stale" if reason_code == "owner_stale" else "unavailable",
        reason_code=reason_code,
        unit=None,
        observed_at=as_of,
        effective_at=as_of,
        as_of=as_of,
        freshness={"state": freshness_state, "policy": "owner_native"},
        quality={"state": quality_state, "issues": issues or []},
        source=source,
        provenance={
            "kind": "owner_derived",
            "owner_field_key": spec.owner_field_key,
            "basis": spec.basis_policy,
            "owner_artifact": artifact_id,
        },
    )
