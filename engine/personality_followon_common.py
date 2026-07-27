"""Shared, authority-inert lifecycle helpers for prospective PSS follow-ons."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

from engine import personality_relief_hazard as rh1
from lib import config

NOT_BEFORE_SESSION = "2026-07-24"
RH1_MANIFEST_SHA256 = (
    "0b07345178592032570aeb57c1c54c1cb24b6463a5836431bc7daf5d44b0cc6b"
)
RH1_MEMBERSHIP_SHA256 = (
    "f00c9d70e0c554213d6aa9a82fecc1492bcedc49c04ce36d4a14647f85713baf"
)
AUTHORITY = dict(rh1.AUTHORITY)


def data_root(root: Path | None) -> Path:
    return root if root is not None else config.data_dir()


def base(root: Path | None) -> Path:
    return data_root(root) / "personality_timing"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def load_registration(
    root: Path | None,
    *,
    manifest_name: str,
    expected_manifest_sha256: str,
    manifest_schema: str,
    program_id: str,
    family: str,
    expected_construction_sha256: str,
) -> dict[str, Any]:
    manifest_file = base(root) / manifest_name
    membership_file = base(root) / "relief_hazard_membership_v1.json"
    rh1_manifest_file = base(root) / "relief_hazard_manifest_v1.json"
    if sha256_file(manifest_file) != expected_manifest_sha256:
        raise ValueError("manifest hash mismatch")
    if sha256_file(membership_file) != RH1_MEMBERSHIP_SHA256:
        raise ValueError("RH1 membership hash mismatch")
    if sha256_file(rh1_manifest_file) != RH1_MANIFEST_SHA256:
        raise ValueError("RH1 manifest hash mismatch")
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    membership = json.loads(membership_file.read_text(encoding="utf-8"))
    if manifest.get("schema") != manifest_schema:
        raise ValueError("manifest schema mismatch")
    if manifest.get("program_id") != program_id:
        raise ValueError("program id mismatch")
    if manifest.get("family") != family:
        raise ValueError("family mismatch")
    if manifest.get("not_before_session") != NOT_BEFORE_SESSION:
        raise ValueError("prospective boundary mismatch")
    if manifest.get("construction_sha256") != expected_construction_sha256:
        raise ValueError("construction declaration mismatch")
    if canonical_sha256(manifest.get("construction")) != expected_construction_sha256:
        raise ValueError("construction content mismatch")
    if manifest.get("authority") != AUTHORITY:
        raise ValueError("authority fence mismatch")
    bindings = manifest.get("source_bindings") or {}
    if (bindings.get("rh1_manifest") or {}).get("sha256") != RH1_MANIFEST_SHA256:
        raise ValueError("RH1 manifest binding mismatch")
    membership_binding = bindings.get("rh1_membership") or {}
    if membership_binding.get("sha256") != RH1_MEMBERSHIP_SHA256:
        raise ValueError("RH1 membership binding mismatch")
    members = membership.get("members") or []
    if len(members) != 799 or membership_binding.get("ticker_count") != len(members):
        raise ValueError("frozen membership count mismatch")
    return {"manifest": manifest, "membership": membership}


def read_events(
    path: Path,
    *,
    schema: str | None = None,
    program_id: str | None = None,
) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            row = json.loads(line)
        except Exception:  # noqa: BLE001 — tolerate one torn final row
            continue
        if row.get("kind") != "event":
            continue
        if schema is not None and row.get("schema") != schema:
            continue
        if program_id is not None and row.get("program_id") != program_id:
            continue
        rows.append(row)
    return rows


def source_path(root: Path | None, name: str) -> Path:
    return base(root) / name


def load_ohlcv(
    root: Path | None,
    sym: str,
    *,
    through: pd.Timestamp | None = None,
) -> pd.DataFrame | None:
    return rh1._load_ohlcv(root, sym, through=through)


def exact_pos(index: pd.DatetimeIndex, date_text: str) -> int | None:
    return rh1._exact_pos(index, date_text)


def grade_row(frame: pd.DataFrame, row: dict[str, Any]) -> dict[str, Any] | None:
    return rh1._grade_row(frame, row)


def atomic_write(path: Path, text: str, *, prefix: str) -> None:
    rh1._atomic_write(path, text, prefix=prefix)


def event_key(row: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        str(row.get("construction_id") or ""),
        str(row.get("sym") or ""),
        str(row.get("anchor_date") or ""),
        str(row.get("source_action_date") or ""),
        str(row.get("action_date") or ""),
    )


def source_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("sym") or ""),
        str(row.get("anchor_date") or ""),
        str(row.get("source_action_date") or row.get("action_date") or ""),
    )


def upstream_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("sym") or ""),
        str(row.get("anchor_date") or ""),
        str(row.get("action_date") or ""),
    )


def coverage_state(
    events: list[dict[str, Any]],
    *,
    primary_groups: tuple[str, str],
    required: dict[str, int],
) -> dict[str, Any]:
    matured = [row for row in events if row.get("grade") is not None]
    primary = [row for row in matured if row.get("group") in set(primary_groups)]
    dates = sorted(str(row.get("action_date")) for row in primary)
    months = {date[:7] for date in dates}
    span = (
        int((pd.Timestamp(dates[-1]) - pd.Timestamp(dates[0])).days)
        if len(dates) >= 2
        else 0
    )
    groups = Counter(str(row.get("group")) for row in matured)
    observed: dict[str, int | None] = {
        "matured_primary_rows": len(primary),
        "unique_names": len({str(row.get("sym")) for row in primary}),
        f"{primary_groups[0]}_rows": groups[primary_groups[0]],
        f"{primary_groups[1]}_rows": groups[primary_groups[1]],
        "distinct_action_months": len(months),
        "action_date_span_days": span,
        "informative_exact_strata": None,
    }
    count_ready = all(
        observed.get(key) is not None and int(observed[key]) >= value
        for key, value in required.items()
        if key != "informative_exact_strata"
    )
    return {
        "status": "locked_minimums",
        "sole_read_executed": False,
        "count_and_clock_minimums_met": count_ready,
        "observed": observed,
        "required": required,
        "note": (
            "No interim effect estimates. Informative strata and outcomes are "
            "opened only by the separately reviewed sole adjudication."
        ),
    }


def member_map(registration: dict[str, Any]) -> dict[str, str]:
    return {
        str(row["sym"]): str(row["sector"])
        for row in registration["membership"]["members"]
    }


def sector_ohlcv(
    registration: dict[str, Any],
    root: Path | None,
    sector: str,
    *,
    through: pd.Timestamp,
) -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    for sym, member_sector in member_map(registration).items():
        if member_sector != sector:
            continue
        frame = load_ohlcv(root, sym, through=through)
        if frame is not None:
            frames[sym] = frame
    return frames
