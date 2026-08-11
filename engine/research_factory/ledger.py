"""engine.research_factory.ledger — append-only JSONL helpers.

Covers data/research_factory/candidates.jsonl, transitions.jsonl,
paper_monitor.jsonl, health.jsonl.  Atomic writes via tempfile + rename
(same approach as engine/trial_ledger.py).

All rows must carry ``"authority": "display_only"`` — validated on append.
Keep-first semantics for forward ledgers: per (candidate_id, as_of) the
first row wins; later rows for the same key are silently ignored (consistent
with the nightly-only writer law, RF-8).

Pure stdlib: no pandas, no yaml, no third-party imports.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path

_WRITE_LOCK = threading.Lock()

# ---------------------------------------------------------------------------
# Base directory for all research-factory ledgers
# ---------------------------------------------------------------------------

DEFAULT_RF_DIR = Path("data") / "research_factory"


# ---------------------------------------------------------------------------
# Core I/O helpers
# ---------------------------------------------------------------------------


def load_jsonl(path: str | Path) -> list[dict]:
    """Load an append-only JSONL file.  Absent-file-safe: returns [].

    Tolerates torn final lines (ignores JSON parse errors on individual rows).
    """
    p = Path(path)
    if not p.exists():
        return []
    rows: list[dict] = []
    try:
        with p.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:  # noqa: BLE001, S112 -- tolerate torn rows
                    continue
    except OSError:
        return []
    return rows


def _require_exact_json_tree(
    value: object,
    *,
    label: str,
    active_containers: set[int] | None = None,
) -> None:
    """Reject values whose Python behaviour can differ from persisted JSON.

    In particular, ``dict`` and ``str`` subclasses can override ``get``,
    equality, or hashing so validation observes a different value from the one
    emitted by :mod:`json`.  Ledger admission therefore accepts only exact
    JSON-native Python types before making its detached canonical snapshot.
    """
    if value is None or type(value) in {bool, int, float, str}:
        return
    if type(value) not in {dict, list}:
        raise ValueError(
            f"{label}: row contains a non-exact or non-JSON-native value"
        )

    if active_containers is None:
        active_containers = set()
    identity = id(value)
    if identity in active_containers:
        raise ValueError(f"{label}: row contains a cyclic JSON value")
    active_containers.add(identity)
    try:
        if type(value) is dict:
            for key, child in dict.items(value):
                if type(key) is not str:
                    raise ValueError(
                        f"{label}: row contains a non-exact JSON object key"
                    )
                _require_exact_json_tree(
                    child,
                    label=label,
                    active_containers=active_containers,
                )
        else:
            for child in value:
                _require_exact_json_tree(
                    child,
                    label=label,
                    active_containers=active_containers,
                )
    finally:
        active_containers.remove(identity)


def _freeze_exact_json_object(
    row: object,
    *,
    label: str,
) -> tuple[dict, bytes]:
    """Return one detached plain-dict view and its canonical JSON bytes."""
    if type(row) is not dict:
        raise ValueError(f"{label}: row must be an exact dict")
    try:
        _require_exact_json_tree(row, label=label)
        body = json.dumps(
            row,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        detached = json.loads(body)
    except (RecursionError, TypeError, ValueError, UnicodeEncodeError) as exc:
        if isinstance(exc, ValueError) and str(exc).startswith(f"{label}:"):
            raise
        raise ValueError(f"{label}: row is not canonical JSON") from exc
    if type(detached) is not dict:  # pragma: no cover - guarded by exact root
        raise ValueError(f"{label}: canonical JSON root must be an object")
    return detached, body


def detached_json_object(row: object, *, label: str) -> dict:
    """Return an exact, detached JSON-object snapshot for safe sanitization."""
    detached, _body = _freeze_exact_json_object(row, label=label)
    return detached


def append_row(path: str | Path, row: dict, *, validate_fn=None) -> None:
    """Append ``row`` to ``path`` as a JSONL line.

    Validates ``authority == 'display_only'`` and runs the optional
    ``validate_fn(row) -> list[str]`` before writing.  Raises ValueError on
    any violation.  Atomic write is NOT used for append (we append in-place,
    which is the correct pattern for JSONL logs — tempfile+rename is used for
    full-file rewrites in keep_first).

    Parameters
    ----------
    path        : Path to the .jsonl file.
    row         : Dict to serialise and append.
    validate_fn : Optional callable; returns a list of violation strings.
    """
    p = Path(path)
    frozen, canonical_body = _freeze_exact_json_object(row, label="append_row")
    if frozen.get("authority") != "display_only":
        raise ValueError(
            f"append_row: row must carry authority='display_only' (RF-11); "
            f"got authority={frozen.get('authority')!r}"
        )
    # A caller-supplied permissive validator (or no validator) must not turn a
    # W6A-owned row into a generic lifecycle write. Preserve legacy audit-drop
    # behaviour for unrelated malformed rows while making the dormant subtype
    # unbypassable on every owned ledger path.
    from engine.research_factory import schema as rf_schema

    if rf_schema.has_market_memory_owned_marker(frozen):
        owned_validator = {
            "candidates.jsonl": rf_schema.validate_candidate,
            "transitions.jsonl": rf_schema.validate_transition,
            "paper_monitor.jsonl": rf_schema.validate_paper_monitor,
        }.get(p.name)
        if owned_validator is not None:
            owned_errs = owned_validator(frozen)
            if owned_errs:
                raise ValueError(
                    "append_row: W6A-owned row failed schema validation for path:\n  "
                    + "\n  ".join(owned_errs)
                )
    if validate_fn is not None:
        errs = validate_fn(frozen)
        if errs:
            raise ValueError(
                "append_row: row failed schema validation:\n  "
                + "\n  ".join(errs)
            )
        # Validators are inspection-only.  Persisting a post-validation
        # mutation would recreate the split-view admission bug this snapshot
        # is designed to eliminate.
        validated, validated_body = _freeze_exact_json_object(
            frozen,
            label="append_row",
        )
        if validated_body != canonical_body or validated != frozen:
            raise ValueError("append_row: validate_fn mutated the frozen row")
    with _WRITE_LOCK:
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("ab") as fh:
            fh.write(canonical_body + b"\n")


def keep_first(rows: list[dict],
               key_fields: tuple[str, ...]) -> list[dict]:
    """Return the subset of ``rows`` keeping only the FIRST row per unique key.

    Key is the tuple of values for ``key_fields``.  Later rows with the same
    key are silently dropped (forward-ledger keep-first semantics, RF-8).

    Parameters
    ----------
    rows       : Input rows (already loaded from disk).
    key_fields : Tuple of field names that form the dedup key.
                 Typical: ``("candidate_id", "as_of")`` for paper_monitor
                 and health forward ledgers.

    Returns
    -------
    list[dict]
        Deduplicated list in original order, first occurrence wins.
    """
    seen: set[tuple] = set()
    out: list[dict] = []
    for row in rows:
        k = tuple(row.get(f) for f in key_fields)
        if k in seen:
            continue
        seen.add(k)
        out.append(row)
    return out


def write_jsonl(path: str | Path, rows: list[dict]) -> None:
    """Atomically overwrite ``path`` with ``rows`` (one JSON line each).

    Uses tempfile + os.replace for atomicity (same approach as trial_ledger.py).
    Every input row is first frozen to one detached exact-JSON view. Authority
    and any path-owned schema are checked against that view, and the exact same
    canonical bytes are then written. Candidate-ledger rewrites cannot bypass
    :func:`schema.validate_candidate` merely by choosing this bulk helper.
    """
    p = Path(path)
    path_validator = None
    if p.name in {"candidates.jsonl", "transitions.jsonl", "paper_monitor.jsonl"}:
        from engine.research_factory import schema as rf_schema

        path_validator = {
            "candidates.jsonl": rf_schema.validate_candidate,
            "transitions.jsonl": rf_schema.validate_transition,
            "paper_monitor.jsonl": rf_schema.validate_paper_monitor,
        }[p.name]
    frozen_rows: list[tuple[dict, bytes]] = []
    for i, row in enumerate(rows):
        frozen, canonical_body = _freeze_exact_json_object(
            row,
            label=f"write_jsonl row[{i}]",
        )
        if frozen.get("authority") != "display_only":
            raise ValueError(
                f"write_jsonl: row[{i}] must carry authority='display_only' (RF-11); "
                f"got authority={frozen.get('authority')!r}"
            )
        if path_validator is not None:
            errs = path_validator(frozen)
            if errs:
                schema_label = {
                    "candidates.jsonl": "candidate",
                    "transitions.jsonl": "transition",
                    "paper_monitor.jsonl": "paper-monitor",
                }[p.name]
                raise ValueError(
                    f"write_jsonl: row[{i}] failed {schema_label} schema validation:\n  "
                    + "\n  ".join(errs)
                )
            validated, validated_body = _freeze_exact_json_object(
                frozen,
                label=f"write_jsonl row[{i}]",
            )
            if validated_body != canonical_body or validated != frozen:
                schema_label = {
                    "candidates.jsonl": "candidate",
                    "transitions.jsonl": "transition",
                    "paper_monitor.jsonl": "paper-monitor",
                }[p.name]
                raise ValueError(
                    f"write_jsonl: {schema_label} validator mutated row[{i}]"
                )
        frozen_rows.append((frozen, canonical_body))

    p.parent.mkdir(parents=True, exist_ok=True)
    with _WRITE_LOCK:
        fd, tmp_path = tempfile.mkstemp(
            dir=str(p.parent), prefix=".tmp_", suffix=".jsonl"
        )
        try:
            with os.fdopen(fd, "wb") as fh:
                for _frozen, canonical_body in frozen_rows:
                    fh.write(canonical_body + b"\n")
            os.replace(tmp_path, str(p))
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise


# ---------------------------------------------------------------------------
# Convenience: load with keep-first applied
# ---------------------------------------------------------------------------


def load_forward_ledger(path: str | Path,
                        key_fields: tuple[str, ...]) -> list[dict]:
    """Load a forward ledger from ``path`` and apply keep-first dedup.

    Absent-file-safe: returns [] if the file does not exist.
    """
    return keep_first(load_jsonl(path), key_fields)
