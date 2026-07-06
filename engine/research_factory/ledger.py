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
from typing import Any

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
                except Exception:
                    continue  # tolerate a torn final line; never crash
    except OSError:
        return []
    return rows


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
    if row.get("authority") != "display_only":
        raise ValueError(
            f"append_row: row must carry authority='display_only' (RF-11); "
            f"got authority={row.get('authority')!r}"
        )
    if validate_fn is not None:
        errs = validate_fn(row)
        if errs:
            raise ValueError(
                "append_row: row failed schema validation:\n  "
                + "\n  ".join(errs)
            )
    p = Path(path)
    with _WRITE_LOCK:
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, default=str) + "\n")


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
    All rows must carry ``authority == 'display_only'``.  Raises ValueError
    if any row violates this.
    """
    for i, row in enumerate(rows):
        if row.get("authority") != "display_only":
            raise ValueError(
                f"write_jsonl: row[{i}] must carry authority='display_only' (RF-11); "
                f"got authority={row.get('authority')!r}"
            )
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with _WRITE_LOCK:
        fd, tmp_path = tempfile.mkstemp(
            dir=str(p.parent), prefix=".tmp_", suffix=".jsonl"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                for row in rows:
                    fh.write(json.dumps(row, default=str) + "\n")
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
