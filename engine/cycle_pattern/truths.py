"""engine/cycle_pattern/truths.py — Market Truth Registry v0.

Append-only versioned JSONL store for adjudicated cycle-pattern findings.
Zero imports from lake or registry (this module is the base layer).

Data contract (data/cycle_pattern/truths.jsonl):
  - One JSON object per line.
  - Each object is one version of one truth: (truth_id, version) is unique.
  - A transition writes a NEW line (version+1); old lines are immutable.
  - active_truths() returns latest-version rows not retired/superseded.
  - The file is the permanent record; authority is revocable via status.

Key design rules (binding):
  - evidence_refs must point to paths that exist on disk at validate time.
  - status 'scored' requires a gate artifact path in evidence_refs
    (a path ending in .json inside data/ containing 'verdict' or 'gate' in name).
  - falsifiers list must be non-empty.
  - monitoring dict must have keys {metric, cadence, auto_demote_rule}
    (values may be None).
  - No sklearn/statsmodels/scipy.stats imports here or downstream.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

TRUTHS_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "cycle_pattern" / "truths.jsonl"

VALID_STATUSES = frozenset(
    {"candidate", "display", "confirmer", "scored", "promoted_null", "retired", "superseded"}
)
VALID_EFFECT_CLASSES = frozenset({"positive", "risk_only", "null", "structural"})
VALID_ERA_STABILITY = frozenset({"stable", "decayed", "fragile", "unknown"})
VALID_PIT_CLASS = frozenset({"pit_pure", "revision_optimistic", "mixed"})

# Fields that every truth row must carry.
REQUIRED_FIELDS: list[str] = [
    "truth_id", "version", "status", "owner_program", "statement",
    "effect_class", "scope", "target", "evidence_refs", "n_summary",
    "ci_summary", "era_stability", "pit_class", "allowed_consumers",
    "forbidden_consumers", "falsifiers", "monitoring",
    "created", "last_reviewed", "next_review_due", "notes",
]

# monitoring must carry these keys (values nullable).
MONITORING_KEYS: list[str] = ["metric", "cadence", "auto_demote_rule"]

# scope must carry these keys.
SCOPE_KEYS: list[str] = ["families", "regions", "sample"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _repo_root() -> Path:
    return TRUTHS_PATH.parent.parent.parent


def validate_truth(row: dict[str, Any], *, check_refs_exist: bool = True) -> None:
    """Raise ValueError with a clear message on any schema violation.

    Checks:
    - All required top-level fields present.
    - Enum fields within allowed values.
    - falsifiers non-empty.
    - monitoring has required keys.
    - scope has required keys and families is a list.
    - evidence_refs is a list.
    - version is a positive int.
    - owner_program == 'cycle-intelligence'.
    - If check_refs_exist: every path in evidence_refs exists on disk.
    - If status == 'scored': at least one gate artifact must be in evidence_refs.
    """
    missing = [f for f in REQUIRED_FIELDS if f not in row]
    if missing:
        raise ValueError(f"truth {row.get('truth_id','?')} missing fields: {missing}")

    tid = row["truth_id"]

    if not isinstance(row["version"], int) or row["version"] < 1:
        raise ValueError(f"{tid}: version must be positive int, got {row['version']!r}")

    if row["status"] not in VALID_STATUSES:
        raise ValueError(f"{tid}: invalid status {row['status']!r}, must be one of {VALID_STATUSES}")

    if row["effect_class"] not in VALID_EFFECT_CLASSES:
        raise ValueError(f"{tid}: invalid effect_class {row['effect_class']!r}")

    if row["era_stability"] not in VALID_ERA_STABILITY:
        raise ValueError(f"{tid}: invalid era_stability {row['era_stability']!r}")

    if row["pit_class"] not in VALID_PIT_CLASS:
        raise ValueError(f"{tid}: invalid pit_class {row['pit_class']!r}")

    if row["owner_program"] != "cycle-intelligence":
        raise ValueError(f"{tid}: owner_program must be 'cycle-intelligence'")

    if not isinstance(row["falsifiers"], list) or len(row["falsifiers"]) == 0:
        raise ValueError(f"{tid}: falsifiers must be a non-empty list")

    if not isinstance(row["evidence_refs"], list):
        raise ValueError(f"{tid}: evidence_refs must be a list")

    mon = row["monitoring"]
    if not isinstance(mon, dict):
        raise ValueError(f"{tid}: monitoring must be a dict")
    missing_mon = [k for k in MONITORING_KEYS if k not in mon]
    if missing_mon:
        raise ValueError(f"{tid}: monitoring missing keys: {missing_mon}")

    scope = row["scope"]
    if not isinstance(scope, dict):
        raise ValueError(f"{tid}: scope must be a dict")
    missing_scope = [k for k in SCOPE_KEYS if k not in scope]
    if missing_scope:
        raise ValueError(f"{tid}: scope missing keys: {missing_scope}")
    if not isinstance(scope.get("families", None), list):
        raise ValueError(f"{tid}: scope.families must be a list")

    if check_refs_exist:
        root = _repo_root()
        bad = [ref for ref in row["evidence_refs"] if not (root / ref).exists()]
        if bad:
            raise ValueError(f"{tid}: evidence_refs paths not found on disk: {bad}")

    # 'scored' requires a gate artifact in evidence_refs.
    if row["status"] == "scored":
        gate_refs = [
            r for r in row["evidence_refs"]
            if r.endswith(".json") and ("data/" in r) and
               any(kw in Path(r).name for kw in ("verdict", "gate", "model", "calibration"))
        ]
        if not gate_refs:
            raise ValueError(
                f"{tid}: status 'scored' requires at least one gate artifact path "
                f"(data/...*.json with 'verdict'/'gate'/'model'/'calibration' in name) "
                f"in evidence_refs"
            )


def load_truths(path: Path | None = None) -> list[dict[str, Any]]:
    """Return all rows from truths.jsonl as a list of dicts (all versions).

    Returns [] if the file does not exist yet.
    """
    p = Path(path) if path else TRUTHS_PATH
    if not p.exists():
        return []
    rows = []
    with p.open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                log.warning("truths.jsonl line %d parse error: %s", lineno, exc)
    return rows


def append_truth(row: dict[str, Any], path: Path | None = None) -> None:
    """Validate and append a single truth row to the JSONL store.

    Does NOT mutate any existing line.
    """
    validate_truth(row)
    p = Path(path) if path else TRUTHS_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def transition_truth(
    truth_id: str,
    new_status: str,
    actor: str,
    reason: str,
    path: Path | None = None,
    *,
    extra_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Transition a truth to a new status by appending a new versioned row.

    Finds the latest version of truth_id, increments version, sets status,
    stamps last_reviewed = now, appends transition metadata to notes, and
    writes the new row via append_truth().

    Returns the new row dict.
    Raises KeyError if truth_id is not found.
    Raises ValueError (from validate_truth) if new_status is invalid.
    """
    if new_status not in VALID_STATUSES:
        raise ValueError(f"invalid status {new_status!r}")

    rows = load_truths(path)
    versions = [r for r in rows if r.get("truth_id") == truth_id]
    if not versions:
        raise KeyError(f"truth_id not found: {truth_id!r}")

    latest = max(versions, key=lambda r: r["version"])
    new_row: dict[str, Any] = dict(latest)
    new_row["version"] = latest["version"] + 1
    new_row["status"] = new_status

    now = _now_iso()
    new_row["last_reviewed"] = now

    transition_note = (
        f"[{now}] transition {latest['status']} → {new_status} by {actor}: {reason}"
    )
    existing_notes = new_row.get("notes", "") or ""
    new_row["notes"] = (existing_notes + "\n" + transition_note).strip()

    if extra_fields:
        for k, v in extra_fields.items():
            new_row[k] = v

    append_truth(new_row, path)
    return new_row


def active_truths(path: Path | None = None) -> list[dict[str, Any]]:
    """Return only the latest-version row for each truth_id, excluding retired/superseded.

    Ordering: by truth_id then version (deterministic).
    """
    rows = load_truths(path)

    # group by truth_id, keep max version
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        tid = row.get("truth_id", "")
        prev = latest.get(tid)
        if prev is None or row["version"] > prev["version"]:
            latest[tid] = row

    inactive = {"retired", "superseded"}
    return [
        r for r in sorted(latest.values(), key=lambda r: r["truth_id"])
        if r.get("status") not in inactive
    ]
