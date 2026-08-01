"""engine.chronicle.manifest — sidecar envelope payload assembly (masterplan §0
gate 5). data/chronicle/manifest.json carries the standard envelope keys (via
engine.neuralweb.envelope.stamp — dict payloads only, since it cannot stamp a
JSONL stream) PLUS per-adapter event counts/gap notes and per-ledger row counts
+ sha256 hashes, so downstream consumers (admin inspector, mastermind lobe) can
read health without re-parsing every ledger. It also pins the SOURCE VINTAGE —
one sha256 per :data:`engine.chronicle.spine.REBUILD_SOURCES` entry as of this
build — which is what lets gate 1 distinguish a legitimately-advanced source from
a store that does not reproduce (see :func:`_source_fingerprints`). Envelope
stamping happens in governor.py (this module only builds the pre-stamp payload
dict).
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from . import spine  # no cycle: spine does not import manifest


def _display_path(path: Path, repo: Path) -> str:
    """Repo-relative path string for the committed manifest (never an absolute
    local-filesystem path — this artifact is committed and read on other hosts)."""
    try:
        return str(path.resolve().relative_to(repo.resolve()))
    except ValueError:
        return str(path)


def _ledger_stats(path: Path, repo: Path) -> dict:
    display_path = _display_path(path, repo)
    if not path.exists():
        return {"path": display_path, "rows": 0, "sha256": None, "present": False}
    try:
        data = path.read_bytes()
    except Exception:  # noqa: BLE001
        return {"path": display_path, "rows": 0, "sha256": None, "present": False}
    rows = sum(1 for line in data.decode("utf-8", errors="replace").splitlines() if line.strip())
    return {
        "path": display_path,
        "rows": rows,
        "sha256": "sha256:" + hashlib.sha256(data).hexdigest(),
        "present": True,
    }


def _source_fingerprints(repo: Path) -> dict:
    """sha256 of EVERY live-snapshot source the spine rebuilds from, keyed by
    repo-relative path (:data:`spine.REBUILD_SOURCES`).

    This is the vintage pin gate 1 reads. The research-vault catalog is committed
    HOURLY by its own lane, so a committed events.jsonl is only byte-reproducible
    against the exact source vintages it was built from; recording them lets the
    gate tell "the store is genuinely broken" from "a source legitimately
    advanced since the store was written" instead of conflating the two.

    Fingerprinting the WHOLE closure rather than the catalog alone is
    load-bearing. The first version of this pin recorded only
    ``research_vault_catalog``, which leaves five other inputs able to advance
    unseen — and daily.yml's collect_tail job (which commits earnings.parquet)
    runs in PARALLEL with the engine job that rebuilds the spine, so
    earnings.parquet in particular moves under the store by construction. With a
    catalog-only pin, that drift left the gate on its STRICT byte path against
    sources that had already moved: a spurious red on unrelated PRs, which is
    precisely the failure that drew four duplicate fixes on 2026-07-26.

    Fail-soft per entry: an absent or unreadable source records the absent shape,
    never raises — a manifest must always be writable.
    """
    return {rel: _source_stats(repo / rel) for rel in spine.REBUILD_SOURCES}


def _source_stats(path: Path) -> dict:
    """sha256 + presence for ONE rebuild input.

    No ``path``/``rows`` keys: the caller keys this by its repo-relative path
    already, and a row count is meaningless across the mixed shapes here (JSON
    snapshot, JSONL ledgers, parquet). Fail-soft to the absent shape on any read
    error, exactly like :func:`_ledger_stats` — an unreadable source is honestly
    recorded as "no vintage" rather than crashing the nightly.
    """
    try:
        data = path.read_bytes()
    except Exception:  # noqa: BLE001 — absent, unreadable, or a directory
        return {"sha256": None, "present": False}
    return {"sha256": "sha256:" + hashlib.sha256(data).hexdigest(), "present": True}


def build_manifest(
    *,
    repo: Path,
    as_of: str,
    coverage: dict,
    adapter_report: dict,
    events_path: Path,
    state_log_path: Path,
    earnings_call_path: Path,
    elapsed_s: float,
) -> dict:
    gap_notes = [
        f"{name}: {info['gap']}"
        for name, info in sorted(adapter_report.items())
        if info.get("gap")
    ]
    return {
        "schema": "chronicle.manifest/v1",
        "as_of": as_of,
        "coverage": coverage,
        "adapters": {
            name: {
                "count": info.get("count", 0),
                "gap": info.get("gap"),
                "dropped_from_source": info.get("dropped_from_source", 0),
            }
            for name, info in sorted(adapter_report.items())
        },
        "ledgers": {
            "events": _ledger_stats(events_path, repo),
            "earnings_calls": _ledger_stats(earnings_call_path, repo),
            "state_log": _ledger_stats(state_log_path, repo),
        },
        "source_fingerprints": _source_fingerprints(repo),
        "gap_notes": gap_notes,
        "elapsed_s": round(float(elapsed_s), 3),
    }
