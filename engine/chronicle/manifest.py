"""engine.chronicle.manifest — sidecar envelope payload assembly (masterplan §0
gate 5). data/chronicle/manifest.json carries the standard envelope keys (via
engine.neuralweb.envelope.stamp — dict payloads only, since it cannot stamp a
JSONL stream) PLUS per-adapter event counts/gap notes and per-ledger row counts
+ sha256 hashes, so downstream consumers (admin inspector, mastermind lobe) can
read health without re-parsing every ledger. Envelope stamping happens in
governor.py (this module only builds the pre-stamp payload dict).
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
    """sha256 vintage of EVERY source the spine's rebuild closure reads.

    #3660 introduced this catalog-only (the catalog is the one INTRADAY-advanced
    source, so it was the incident's trigger) — but the other five sources
    advance too (nightly steps, occasional manual fix PRs), and any of them
    moving while the catalog stands still would re-create the exact
    false-red/false-arm confusion this key exists to prevent. So the fingerprint
    now covers the full ``spine.REBUILD_SOURCES`` closure, keyed by
    repo-relative path so the recording and the gate can never disagree about
    what a rebuild reads. The CI gate arms its byte-equality branch only when
    EVERY entry still matches, and treats any mismatch as recorded accrual lag.
    Fail-soft: an absent/unreadable source records null, never raises.
    """
    out: dict[str, str | None] = {}
    for rel in spine.REBUILD_SOURCES:
        path = repo / rel
        try:
            out[rel] = ("sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
                        if path.exists() else None)
        except Exception:  # noqa: BLE001
            out[rel] = None
    return out


def build_manifest(
    *,
    repo: Path,
    as_of: str,
    coverage: dict,
    adapter_report: dict,
    events_path: Path,
    state_log_path: Path,
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
            "state_log": _ledger_stats(state_log_path, repo),
        },
        "source_fingerprints": _source_fingerprints(repo),
        "gap_notes": gap_notes,
        "elapsed_s": round(float(elapsed_s), 3),
    }
