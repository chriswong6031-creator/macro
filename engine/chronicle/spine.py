"""engine.chronicle.spine — event assembly + events.jsonl IO (W0).

Design note (byte-stable regeneration, masterplan §0 gates 1+2): every W0
source EXCEPT state_log.jsonl is already a full snapshot or a full append-only
ledger (catalog.json is the current full vault snapshot; the prophet ledger,
release forward ledger and risk_radar forward log are full append-only
ledgers; the earnings parquet is a full current snapshot). So ``build_events``
always fully recomputes the event set from {catalog, prophet ledger, forward
ledger, risk_radar forward log, earnings parquet, CURRENT state_log rows} on
every run — incremental and --rebuild alike. Because event ids are stable
hashes of (source, source_ref, date), unchanged sources yield an identical id
set every time, which is exactly what makes gate 1 (byte-stable rebuild) and
gate 2 (idempotent zero-duplicate re-runs) hold. The only thing that differs
between incremental and --rebuild is whether state_log.jsonl gets a new row
appended BEFORE this recompute (see governor.py) — state_log itself is the one
genuinely-incremental, non-regenerable ledger in the store.

Append-only law (B1 fix): a source row can legitimately leave its snapshot
between runs (the earnings parquet keeps only a rolling window of quarters;
the vault catalog drops items by id) — that must never silently delete the
event it produced. ``governor.build_and_write`` calls :func:`union_events` to
union this run's recompute with whatever was previously committed, so a
dropped source row RETAINS its event (flagged, never erased) rather than
vanishing with no signal.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path

from . import adapters, state_log

log = logging.getLogger(__name__)

EVENTS_REL = Path("data") / "chronicle" / "events.jsonl"

_SOURCE_ADAPTERS: tuple[tuple[str, object], ...] = (
    ("research_vault", adapters.adapt_research_vault),
    ("prophet_ledger", adapters.adapt_prophet_ledger),
    ("macro_release", adapters.adapt_macro_release),
    ("earnings", adapters.adapt_earnings),
    ("risk_band", adapters.adapt_risk_band),
)


def build_events(repo: Path) -> tuple[list[dict], dict]:
    """Run every adapter and return (all_events, per_adapter_report).

    Never raises: an adapter that throws is caught here too (belt-and-braces —
    each adapter already fail-softs internally) and degrades to a gap note.
    """
    all_events: list[dict] = []
    report: dict[str, dict] = {}

    for name, fn in _SOURCE_ADAPTERS:
        try:
            events, gap = fn(repo)
        except Exception as exc:  # noqa: BLE001
            events, gap = [], f"adapter raised: {exc}"
            log.warning("chronicle adapter %s raised: %s", name, exc)
        all_events.extend(events)
        report[name] = {"count": len(events), "gap": gap}

    # regime_flip is the one adapter NOT in _SOURCE_ADAPTERS: it derives from
    # state_log.jsonl (the forward-capture ledger), not a directly-committed
    # source file, so it needs row-count-aware gap messages the generic loop
    # above doesn't produce. risk_band moved OUT of this special case (B6 —
    # it now reads the real committed data/risk_radar/forward_log.jsonl
    # history directly, so it is a normal file adapter in _SOURCE_ADAPTERS
    # above; world_state.json genuinely has no committed dated history, so
    # regime_flip alone still needs the state_log forward-capture path).
    try:
        rows = state_log.read_state_log(repo)
        flip_events = state_log.derive_flip_events(rows)
        if not rows:
            flip_gap = "data/chronicle/state_log.jsonl has no rows yet (first nightly capture pending)"
        elif len(rows) == 1:
            flip_gap = "data/chronicle/state_log.jsonl has one baseline row — flips accrue from the next capture"
        else:
            flip_gap = None
    except Exception as exc:  # noqa: BLE001
        flip_events, flip_gap = [], f"adapter raised: {exc}"
        log.warning("chronicle state_log flip derivation raised: %s", exc)

    all_events.extend(flip_events)
    report["regime_flip"] = {
        "count": len(flip_events),
        "gap": flip_gap,
    }
    return all_events, report


def sort_events(events: list[dict]) -> list[dict]:
    """Dedupe by id (keep-first, deterministic) then sort ascending by (date, id)."""
    dedup: dict[str, dict] = {}
    for ev in events:
        eid = ev.get("id")
        if eid and eid not in dedup:
            dedup[eid] = ev
    return sorted(dedup.values(), key=lambda e: (e.get("date") or "", e.get("id") or ""))


def union_events(prev_events: list[dict], recomputed_events: list[dict]) -> tuple[list[dict], list[dict]]:
    """Union-merge by id (B1): recomputed body wins on id collision (so
    corrections propagate), but an id present in ``prev_events`` and ABSENT
    from ``recomputed_events`` is RETAINED unchanged — its source row leaving
    the current snapshot (rolling-window parquet, a vault item dropped by id,
    ...) must never silently delete the event it already produced. That is
    what makes "append-only" (config/synapse.yml, config/dag.yml) true rather
    than aspirational.

    Returns (sorted_union, dropped_events) where dropped_events is the list of
    full previously-committed event dicts whose id the recompute no longer
    produces — callers use this to report per-adapter ``dropped_from_source``
    counts and an honest manifest gap note.
    """
    recomputed_sorted = sort_events(recomputed_events)
    recomputed_ids = {e.get("id") for e in recomputed_sorted if e.get("id")}
    prev_ids = {e.get("id") for e in prev_events if e.get("id")}
    dropped_id_set = prev_ids - recomputed_ids
    dropped_events = [e for e in prev_events if e.get("id") in dropped_id_set]
    union = sort_events(recomputed_sorted + dropped_events)
    return union, dropped_events


def load_events_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:  # noqa: BLE001
                continue
    except Exception as exc:  # noqa: BLE001
        log.warning("chronicle.spine: load_events_jsonl(%s) failed: %s", path, exc)
        return []
    return out


def write_events_jsonl(path: Path, events: list[dict]) -> None:
    """Atomic write, one sort_keys=True JSON object per line (byte-stability is
    independent of Python dict insertion order)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=path.parent, prefix=".tmp_", suffix=".jsonl")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            for ev in events:
                f.write(json.dumps(ev, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
                f.write("\n")
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except Exception:  # noqa: BLE001
            pass
        raise
