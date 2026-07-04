"""engine.neuralweb.reflexes — Reflex registry loader + firings ledger (Neural Web W6a).

WHAT THIS MODULE DOES
---------------------
1. Loads config/reflexes.yml and validates the registry (reflex names unique,
   paths match the ``data/reflexes/<name>/firings.jsonl`` convention,
   claim_family prefix = 'reflex.').

2. Provides ``record_firing(name, payload, root=None)`` — appends one JSON line
   to ``data/reflexes/<name>/firings.jsonl``.

3. Provides ``load_firings(name, root=None)`` — returns the list of firing
   records from ``data/reflexes/<name>/firings.jsonl``.

SINGLE-WRITER LAW
-----------------
Only the reflex's own workflow lane may call ``record_firing()``.  This is a
documented contract, not a global lock.  The module enforces nothing globally —
the law lives in the reflexes.yml registry and in the workflow commit-step
coverage (SENTINEL STAGING LAW).

NIGHTLY SPINE FOLD
------------------
``engine.neuralweb.query.adapt_reflexes()`` reads each firings.jsonl that
exists under ``data/reflexes/*/`` and maps them to spine index rows with
``ledger='reflexes'``, ``engine='reflex.<name>'``, ``outcome_graded=False``
(ungraded-honest — grading design documented as future work).

CLAIM SHAPES
------------
Each firing record is a claim-shaped JSON object with at minimum::

    {
      "claim_id":      "<sha256 of reflex+ts+trigger_key>",
      "reflex":        "<reflex_name>",
      "ts":            "<ISO-8601 UTC>",
      "trigger_type":  "<staleness_check|price_state_machine|...>",
      "trigger_key":   "<string identifying the specific trigger event>",
      "action_taken":  "<str>",
      "desk":          "reflex",
      "asof":          "<YYYY-MM-DD>",
      "scope_type":    "macro|entity|sector",
      "scope_key":     "<symbol or key>",
      "direction":     <int: +1/-1/0>,
      "horizon_d":     <int|null>,
      "claim_family":  "reflex.<name>",
      "is_context_only": true,
      "extra":         {}
    }

``is_context_only=True`` is mandatory for all reflex firings: these records
annotate the spine index but feed no score/allocation/ranking surface (Article 2
perimeter).
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger(__name__)

_REGISTRY_CACHE: dict | None = None
_CLAIM_FAMILY_PREFIX = "reflex."
_FIRINGS_PATH_PATTERN = re.compile(r"^data/reflexes/([^/]+)/firings\.jsonl$")


# ---------------------------------------------------------------------------
# Registry loading + validation
# ---------------------------------------------------------------------------

def _registry_path(root: Path | str | None = None) -> Path:
    if root is not None:
        return Path(root) / "config" / "reflexes.yml"
    from lib import config as _cfg  # noqa: PLC0415 — lazy import
    return _cfg.ROOT / "config" / "reflexes.yml"


def load_registry(root: Path | str | None = None, *, force: bool = False) -> dict:
    """Load and validate config/reflexes.yml.  Cached after first load.

    Validation checks:
      - reflex names are unique;
      - firings_jsonl paths match ``data/reflexes/<name>/firings.jsonl``
        when present (non-null);
      - claim_family starts with 'reflex.' when present (non-null).

    Raises ``ValueError`` on a registry violation.  Returns the raw ``reflexes``
    dict (mapping name → entry).
    """
    global _REGISTRY_CACHE  # noqa: PLW0603
    if _REGISTRY_CACHE is not None and not force:
        return _REGISTRY_CACHE

    p = _registry_path(root)
    if not p.exists():
        raise FileNotFoundError(f"reflexes.yml not found at {p}")

    raw = yaml.safe_load(p.read_text())
    reflexes: dict = raw.get("reflexes") or {}

    # Validation pass
    seen_names: set[str] = set()
    violations: list[str] = []

    for name, entry in reflexes.items():
        if name in seen_names:
            violations.append(f"duplicate reflex name: {name!r}")
        seen_names.add(name)

        fj = entry.get("firings_jsonl")
        if fj is not None:
            m = _FIRINGS_PATH_PATTERN.match(str(fj))
            if not m:
                violations.append(
                    f"{name}: firings_jsonl {fj!r} does not match "
                    f"data/reflexes/<name>/firings.jsonl convention"
                )
            elif m.group(1) != name:
                violations.append(
                    f"{name}: firings_jsonl path names different reflex "
                    f"({m.group(1)!r}); must be data/reflexes/{name}/firings.jsonl"
                )

        cf = entry.get("claim_family")
        if cf is not None and not str(cf).startswith(_CLAIM_FAMILY_PREFIX):
            violations.append(
                f"{name}: claim_family {cf!r} must start with 'reflex.'"
            )

    if violations:
        msg = "reflexes.yml registry violations:\n" + "\n".join(
            f"  - {v}" for v in violations
        )
        raise ValueError(msg)

    _REGISTRY_CACHE = reflexes
    log.info("reflexes: loaded %d entries (%d mirroring)",
             len(reflexes),
             sum(1 for e in reflexes.values()
                 if e.get("migration_status") == "mirroring"))
    return reflexes


def invalidate_cache() -> None:
    """Clear the in-process registry cache (for tests / hot-reload)."""
    global _REGISTRY_CACHE  # noqa: PLW0603
    _REGISTRY_CACHE = None


# ---------------------------------------------------------------------------
# Firings path helpers
# ---------------------------------------------------------------------------

def _firings_dir(name: str, root: Path | str | None) -> Path:
    if root is not None:
        return Path(root) / "data" / "reflexes" / name
    from lib import config as _cfg  # noqa: PLC0415
    return _cfg.data_dir() / "reflexes" / name


def _firings_path(name: str, root: Path | str | None) -> Path:
    return _firings_dir(name, root) / "firings.jsonl"


# ---------------------------------------------------------------------------
# record_firing
# ---------------------------------------------------------------------------

def record_firing(
    name: str,
    payload: dict[str, Any],
    root: Path | str | None = None,
) -> dict[str, Any]:
    """Append one JSON line to ``data/reflexes/<name>/firings.jsonl``.

    SINGLE-WRITER LAW: only the reflex's own workflow lane should call this.
    This function enforces nothing globally; see the ledger_law in reflexes.yml.

    ``payload`` is a dict with at minimum:
      - ``ts`` (ISO-8601 UTC timestamp string)
      - ``trigger_key`` (unique string identifying the specific trigger event)
      - ``trigger_type`` (string naming the trigger category)
      - ``action_taken`` (string)
      - ``scope_type`` ('macro' | 'entity' | 'sector')
      - ``scope_key`` (symbol or key string)
      - ``direction`` (+1 / -1 / 0)
      - ``horizon_d`` (int or None)
      - ``asof`` (YYYY-MM-DD string)

    The function stamps ``claim_id`` (SHA-256 of reflex+ts+trigger_key),
    ``reflex``, ``claim_family``, ``desk='reflex'``, and
    ``is_context_only=True`` onto the record before writing.

    Returns the complete record written to disk.

    Never raises: write failures are logged and the function returns the record
    with an ``_write_error`` key set.  The reflex's own lane must never fail
    because of the firings append.
    """
    ts = str(payload.get("ts", ""))
    trigger_key = str(payload.get("trigger_key", ""))
    claim_id = hashlib.sha256(
        f"{name}:{ts}:{trigger_key}".encode()
    ).hexdigest()[:16]

    record: dict[str, Any] = {
        "claim_id": claim_id,
        "reflex": name,
        "claim_family": f"{_CLAIM_FAMILY_PREFIX}{name}",
        "desk": "reflex",
        "is_context_only": True,
        **payload,
    }
    # Ensure mandatory keys are present (fill defaults)
    record.setdefault("scope_type", "macro")
    record.setdefault("scope_key", "macro")
    record.setdefault("direction", 0)
    record.setdefault("horizon_d", None)
    record.setdefault("asof", ts[:10] if len(ts) >= 10 else ts)

    p = _firings_path(name, root)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, default=str) + "\n")
        log.debug("record_firing: %s claim_id=%s", name, claim_id)
    except Exception as e:  # noqa: BLE001 — firings append must never fail the lane
        log.error("record_firing: FAILED to append to %s: %s", p, e)
        record["_write_error"] = str(e)

    return record


# ---------------------------------------------------------------------------
# load_firings
# ---------------------------------------------------------------------------

def load_firings(
    name: str,
    root: Path | str | None = None,
) -> list[dict[str, Any]]:
    """Read all firing records from ``data/reflexes/<name>/firings.jsonl``.

    Returns an empty list if the file does not exist (expected on a fresh clone
    before the reflex has fired).  Skips lines that fail JSON parse with a
    warning (the reader must never crash on a partial write).
    """
    p = _firings_path(name, root)
    if not p.exists():
        return []
    records: list[dict] = []
    with open(p, encoding="utf-8") as fh:
        for i, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as e:
                log.warning("load_firings: %s line %d parse error (%s) — skipped",
                            name, i, e)
    return records


# ---------------------------------------------------------------------------
# discover_all_firings
# ---------------------------------------------------------------------------

def discover_all_firings(
    root: Path | str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Scan ``data/reflexes/*/firings.jsonl`` and return {name: [records]}.

    Used by the spine fold (``engine.neuralweb.query.adapt_reflexes``) to
    collect all firing streams without needing to enumerate them individually.
    Returns an empty dict if the reflexes root does not exist yet.
    """
    if root is not None:
        reflexes_root = Path(root) / "data" / "reflexes"
    else:
        from lib import config as _cfg  # noqa: PLC0415
        reflexes_root = _cfg.data_dir() / "reflexes"

    result: dict[str, list[dict]] = {}
    if not reflexes_root.exists():
        return result

    for name_dir in reflexes_root.iterdir():
        if not name_dir.is_dir():
            continue
        fj = name_dir / "firings.jsonl"
        if not fj.exists():
            continue
        name = name_dir.name
        result[name] = load_firings(name, root)

    return result
