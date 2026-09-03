"""engine.flow_observatory.history — the append-only point-in-time observation ledger (W3).

``data/flow_observatory/observations.parquet`` (masterplan §5/§10, frozen
``research/flow_observatory/W3_SPEC.md`` §1) is the product-level system of record for
"what did we believe, and when": one row per
``(entity_kind, entity_id, effective_session, revision_id)``. ``state_log.jsonl``
(:mod:`engine.flow_observatory.changes`) stays exactly what its own docstring says — the
run/health journal (build-run history, coverage-collapse trailing inputs) — this module
owns the PRODUCT observation history: state age, onset, prior state, rank change, and
``sources[].first_known_at`` all derive from here once the ledger is deep enough; the
state_log-derived path in ``changes.compute_changes`` / ``contract.build_v2`` remains the
FALLBACK until then (bootstrap: the ledger starts empty — the first guarded lane run after
W1/W2 populates both stores; see each fallback branch's own docstring).

Immutability law (spec §1): closed rows are NEVER mutated in place. An append either (a)
writes a brand-new ``revision_id=0`` row for a key never seen before, (b) is a no-op when
the observation is IDENTICAL to the latest belief already on file (idempotent — spec test
2), or (c) writes a NEW ``revision_id=N+1`` row when the observation genuinely changed,
leaving every previously-written row's own field values untouched (spec test 3 "original
row byte-preserved"). The whole file is re-serialized on a real write (parquet has no
partial-file append primitive that preserves byte RANGES), but the row CONTENT for every
key that did not change is reproduced verbatim, and rows are written in a fixed
deterministic order — so two consecutive appends with byte-identical inputs never touch a
single already-written row's values and, because an unchanged input causes NO write at all,
the file's own bytes/hash are provably identical across repeated identical calls (spec
test 1).

Advance gate: the SAME ``engine.ledger_lane`` pattern as ``changes.append_state_log`` —
nightly/asia-close are the sole advancers; every other lane computes and discards
(``require_lane=False`` is the test/backfill seam only, spec test 8).
"""
from __future__ import annotations

import logging
from datetime import date as _date, datetime as _datetime, timezone
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from engine.ledger_lane import asia_advance_enabled, nightly_advance_enabled

log = logging.getLogger(__name__)

OBSERVATIONS_REL = Path("flow_observatory") / "observations.parquet"

#: the observation payload columns (spec §1 table) — everything else (entity_kind,
#: entity_id, effective_session, revision_id, first_known_at, revised_at) is ledger
#: bookkeeping, not part of the "did the belief change" comparison in append_observations.
FIELDS: tuple[str, ...] = ("vel", "abs_value", "quadrant", "state", "rank", "coverage_n", "status")

#: statuses that do NOT count toward state-age progression (spec §3 test 6: "stale session
#: does not advance state age"). Mirrors engine.flow_observatory.quality's enum by literal
#: string rather than importing it — history.py stays leaf-level (no I/O beyond parquet;
#: quality.py itself has no reverse need of this module), same layering discipline as
#: changes.py's own frozenset of quality-change statuses.
_NOT_COUNTABLE = frozenset({"STALE", "UNAVAILABLE"})

LEDGER_SCHEMA = pa.schema([
    ("entity_kind", pa.string()),
    ("entity_id", pa.string()),
    ("effective_session", pa.string()),
    ("revision_id", pa.int64()),
    ("first_known_at", pa.string()),
    ("revised_at", pa.string()),
    ("vel", pa.float64()),
    ("abs_value", pa.float64()),
    ("quadrant", pa.string()),
    ("state", pa.string()),
    ("rank", pa.int64()),
    ("coverage_n", pa.int64()),
    ("status", pa.string()),
])


def observations_path(data_root: Path) -> Path:
    return Path(data_root) / OBSERVATIONS_REL


def advance_enabled() -> bool:
    return bool(asia_advance_enabled() or nightly_advance_enabled())


def _iso(now: Any) -> str:
    """A fixed-format, lexicographically-sortable UTC instant — ``replay`` and the
    revision-receipt lookup below both compare these as plain strings, so every caller
    (production and test) must go through this one formatter."""
    if isinstance(now, _datetime):
        dt = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat(timespec="seconds")
    if isinstance(now, _date):
        return _datetime(now.year, now.month, now.day, tzinfo=timezone.utc).isoformat(timespec="seconds")
    return str(now)


def _row_key(row: dict[str, Any]) -> tuple:
    return (row.get("entity_kind"), row.get("entity_id"), row.get("effective_session"),
            row.get("revision_id"))


# ── I/O boundary (the only functions here that touch disk) ─────────────────────────────
def read_ledger(path: Path) -> list[dict[str, Any]]:
    """Every row, oldest-first by key. A corrupt/missing file reads as an empty ledger —
    never fatal (same "derived accelerator, not fatal system of record" posture as
    ``changes.read_state_log``, except the ledger genuinely IS the system of record for
    product history; an unreadable file is still a build-continuity concern, not a crash)."""
    if not Path(path).exists():
        return []
    try:
        table = pq.read_table(path, schema=LEDGER_SCHEMA)
    except Exception as e:  # noqa: BLE001 — a corrupt ledger must not sink the build
        log.warning("flow_observatory: observations ledger unreadable (%s)", e)
        return []
    rows = table.to_pylist()
    rows.sort(key=_row_key)
    return rows


def _write_ledger(path: Path, rows: list[dict[str, Any]]) -> None:
    ordered = sorted(rows, key=_row_key)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist(ordered, schema=LEDGER_SCHEMA)
    # compression=None + a fixed row/column order is what makes byte-identical writes
    # possible across repeated calls with the same logical content (spec test 1) — no
    # dictionary-encoding nondeterminism, no wall-clock-derived metadata.
    pq.write_table(table, path, compression="none", use_dictionary=False)


# ── append (the one mutator) ────────────────────────────────────────────────────────────
def _diff_entities(rows: list[dict[str, Any]], session: str,
                   entities: dict[tuple[str, str], dict], now_iso: str) -> list[dict[str, Any]]:
    """Pure — the new rows (if any) that appending ``entities`` for ``session`` against the
    ledger content ``rows`` would produce. Shared by :func:`append_observations` (which
    writes them) and :func:`preview_revisions` (which does not) so the two can never
    disagree about what counts as a change."""
    by_key: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for r in rows:
        by_key.setdefault((r["entity_kind"], r["entity_id"], r["effective_session"]), []).append(r)
    new_rows: list[dict[str, Any]] = []
    for (ekind, eid), payload in entities.items():
        vals = {f: payload.get(f) for f in FIELDS}
        existing = by_key.get((ekind, eid, session), [])
        if not existing:
            new_rows.append({"entity_kind": ekind, "entity_id": eid, "effective_session": session,
                             "revision_id": 0, "first_known_at": now_iso, "revised_at": None, **vals})
            continue
        latest_row = max(existing, key=lambda r: r["revision_id"])
        if all(latest_row.get(f) == vals.get(f) for f in FIELDS):
            continue  # idempotent no-op — identical belief already on file (spec test 2)
        next_rev = int(latest_row["revision_id"]) + 1
        new_rows.append({"entity_kind": ekind, "entity_id": eid, "effective_session": session,
                         "revision_id": next_rev, "first_known_at": now_iso, "revised_at": now_iso,
                         **vals})
    return new_rows


def preview_revisions(rows: list[dict[str, Any]], session: str | None,
                      entities: dict[tuple[str, str], dict], now: Any) -> list[dict[str, Any]]:
    """Pure, no write — exactly what :func:`append_observations` WOULD record as revisions
    for ``(session, entities)`` against the ledger's CURRENT content. The builder calls this
    BEFORE ``validate()`` (change_summary.source_revisions must exist inside the payload
    validate() checks), and the real, lane-gated, disk-writing append happens only AFTER
    validate() passes (spec §2 ordering) — both paths share :func:`_diff_entities` so the
    preview can never diverge from what actually gets written a moment later."""
    if not session or not entities:
        return []
    now_iso = _iso(now)
    new_rows = _diff_entities(rows, session, entities, now_iso)
    if not new_rows:
        return []
    return revision_receipts(rows + new_rows, now_iso)


def append_observations(path: Path, session: str | None, entities: dict[tuple[str, str], dict],
                        now: Any, require_lane: bool = True) -> dict[str, Any]:
    """Append (or idempotently no-op, or revise) this session's belief for each entity.

    ``entities``: ``{(entity_kind, entity_id): {<subset of FIELDS>}}`` — the observation
    payload for ``session``. Missing FIELDS default to ``None`` (honest null, never a
    fabricated zero).

    Gated on ``require_lane`` (default True) — off the nightly/asia-close lane, this is a
    pure no-op that touches nothing on disk (spec test 8: "non-owner lane cannot append").
    """
    if require_lane and not advance_enabled():
        log.info("flow_observatory: observations append skipped (off nightly/asia-close lane)")
        return {"written": False, "reason": "off_ledger_lane", "rows_added": 0, "revisions": []}
    if not session:
        return {"written": False, "reason": "no_session", "rows_added": 0, "revisions": []}
    if not entities:
        return {"written": False, "reason": "no_entities", "rows_added": 0, "revisions": []}

    rows = read_ledger(path)
    now_iso = _iso(now)
    new_rows = _diff_entities(rows, session, entities, now_iso)
    if not new_rows:
        return {"written": False, "reason": "no_changes", "rows_added": 0, "revisions": []}

    out_rows = rows + new_rows
    _write_ledger(path, out_rows)
    revisions = revision_receipts(out_rows, now_iso)
    return {"written": True, "rows_added": len(new_rows), "rows": len(out_rows),
           "revisions": revisions}


# ── read-side views ──────────────────────────────────────────────────────────────────
def latest_view(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per ``(entity_kind, entity_id, effective_session)`` key: the max-revision
    row — "current view = latest valid revision" (spec §1)."""
    best: dict[tuple, dict[str, Any]] = {}
    for r in rows:
        key = (r["entity_kind"], r["entity_id"], r["effective_session"])
        cur = best.get(key)
        if cur is None or r["revision_id"] > cur["revision_id"]:
            best[key] = r
    return list(best.values())


def replay(rows: list[dict[str, Any]], at: Any) -> list[dict[str, Any]]:
    """Rows knowable as of instant ``at`` (spec §1: "rows with first_known_at ≤ at, max
    revision among those") — a revision made AFTER ``at`` is invisible to this view; ``at``
    itself is inclusive. This is what makes replay deterministic: the SAME ``at`` always
    reconstructs the SAME belief, regardless of what has been revised since."""
    at_iso = _iso(at)
    knowable = [r for r in rows if (r.get("first_known_at") or "") <= at_iso]
    return latest_view(knowable)


def entity_rows(rows: list[dict[str, Any]], entity_kind: str, entity_id: str) -> list[dict[str, Any]]:
    """This one entity's session series (latest revision per session), ascending by
    session — the input :func:`derive_states` / :func:`state_for_session` walk."""
    lv = [r for r in latest_view(rows) if r["entity_kind"] == entity_kind and r["entity_id"] == entity_id]
    lv.sort(key=lambda r: r["effective_session"])
    return lv


def ledger_session_count(rows: list[dict[str, Any]], entity_kind: str | None = None) -> int:
    """Distinct ``effective_session`` values in the ledger (optionally scoped to one
    ``entity_kind``) — the depth gate ``contract.build_v2``/``changes.compute_changes`` use
    to decide ledger-vs-state_log fallback (spec §2: "state_log summaries stay as fallback
    until the ledger has ≥2 sessions")."""
    sessions = {r["effective_session"] for r in rows
               if entity_kind is None or r["entity_kind"] == entity_kind}
    return len(sessions)


def first_known_at(rows: list[dict[str, Any]], entity_kind: str, entity_id: str,
                   session: str) -> str | None:
    """The ``revision_id==0`` row's ``first_known_at`` for this key — when OUR pipeline
    FIRST held this belief (spec §1). A later correction's own ``revised_at`` never
    overwrites this — that is exactly the "build time never imitates source/belief time"
    distinction the ledger exists to preserve. ``None`` when this key has never been
    observed at all (honest — sources[].first_known_at stays null, spec §2 "closes the W1
    limitation" only once the ledger actually holds the leg)."""
    for r in rows:
        if (r["entity_kind"] == entity_kind and r["entity_id"] == entity_id
                and r["effective_session"] == session and r["revision_id"] == 0):
            return r.get("first_known_at")
    return None


def previous_valid_ledger_session(rows: list[dict[str, Any]], entity_kind: str,
                                  before: str | None) -> str | None:
    """The newest ``effective_session`` strictly before ``before`` across ALL entities of
    ``entity_kind`` — the universe's own previous-valid-session boundary (never one
    entity's own last-seen session, which could predate a gap — see :func:`previous_values`
    for why that distinction matters, spec test 7)."""
    if not before:
        return None
    sessions = sorted({r["effective_session"] for r in rows
                       if r["entity_kind"] == entity_kind and r["effective_session"] < before})
    return sessions[-1] if sessions else None


def previous_values(rows: list[dict[str, Any]], entity_kind: str, session: str | None,
                    field: str) -> dict[str, Any] | None:
    """``{entity_id: value}`` for every entity of ``entity_kind`` at EXACTLY ``session`` —
    the universe's own snapshot at that session (latest revision as of now). ``None`` when
    ``session`` is itself ``None`` (no prior session at all). An entity simply ABSENT from
    that snapshot is absent from the returned dict, so ``.get(entity_id)`` correctly yields
    ``None`` rather than comparing against a different, inconsistent universe (spec §3 test
    7: "an entity absent from the prior session → rank_change null, not a fabricated
    delta")."""
    if session is None:
        return None
    lv = latest_view(rows)
    return {r["entity_id"]: r.get(field) for r in lv
           if r["entity_kind"] == entity_kind and r["effective_session"] == session}


# ── state derivation (onset / age / prior_state) ────────────────────────────────────────
def _state_from_series(series: list[dict[str, Any]], idx: int) -> dict[str, Any]:
    """``{state_started, state_age_sessions, prior_state, note}`` for ``series[idx]``.

    ``series``: ascending ``{'effective_session','quadrant','status', ...}`` rows for ONE
    entity (may include one caller-supplied not-yet-appended row at the end — see
    :func:`state_for_session`). Honors:

    * skip-gap — only rows actually PRESENT in ``series`` are ever examined, so a session
      absent from the ledger is structurally invisible to the walk (spec test 5);
    * stale-freeze — a row whose own ``status`` is STALE/UNAVAILABLE recurses onto the
      row immediately before it and reuses that answer verbatim (with a distinguishing
      note): "today's frozen read is exactly yesterday's", never an incremented age for a
      day that added no fresh information (spec test 6). A STALE/UNAVAILABLE row strictly
      BEFORE the one being asked about is transparent for continuity (skipped, not a break)
      but never itself increments the age count.
    """
    row = series[idx]
    prior = series[:idx]
    if not prior:
        return {"state_started": None, "state_age_sessions": None, "prior_state": None,
               "note": "first tracked session"}
    if row.get("status") in _NOT_COUNTABLE:
        frozen = _state_from_series(series, idx - 1)
        return {**frozen, "note": "age frozen (stale source)"}
    quadrant = row.get("quadrant")
    prior_state = prior[-1].get("quadrant")
    started, age = row["effective_session"], 1
    j = idx - 1
    while j >= 0:
        prow = series[j]
        if prow.get("status") in _NOT_COUNTABLE:
            j -= 1
            continue  # transparent gap — does not extend OR break the run
        if prow.get("quadrant") != quadrant:
            break
        started, age = prow["effective_session"], age + 1
        j -= 1
    return {"state_started": started, "state_age_sessions": age, "prior_state": prior_state,
           "note": None}


def derive_states(rows: list[dict[str, Any]], entity_kind: str, entity_id: str) -> dict[str, dict]:
    """``{session: {state_started, state_age_sessions, prior_state, rank_change, note}}``
    for EVERY session this entity holds in the ledger — the "ordered per-session series"
    spec §1 names, used by the replay demo and the failing-first test suite. Production
    per-build reads go through :func:`state_for_session` instead (cheaper — one session,
    plus the not-yet-appended current row)."""
    series = entity_rows(rows, entity_kind, entity_id)
    all_sessions = sorted({r["effective_session"] for r in rows if r["entity_kind"] == entity_kind})
    out: dict[str, dict] = {}
    for idx, row in enumerate(series):
        session = row["effective_session"]
        state = _state_from_series(series, idx)
        prior_sessions = [s for s in all_sessions if s < session]
        prev_session = prior_sessions[-1] if prior_sessions else None
        prev_rank = (previous_values(rows, entity_kind, prev_session, "rank") or {}).get(entity_id) \
            if prev_session is not None else None
        cur_rank = row.get("rank")
        rank_change = (cur_rank - prev_rank) if (cur_rank is not None and prev_rank is not None) else None
        out[session] = {**state, "rank_change": rank_change}
    return out


def state_for_session(rows: list[dict[str, Any]], entity_kind: str, entity_id: str,
                      current_session: str, current_quadrant: Any, current_rank: Any = None,
                      current_status: Any = None) -> dict[str, Any]:
    """Ledger-backed counterpart to ``changes.theme_state_history`` — same output shape
    (``state_started``/``state_age_sessions``/``prior_state``/``note``) plus
    ``rank_change`` (spec §1 ``derive_states`` / §2: "per-row ... now come from
    derive_states when ledger depth allows").

    ``contract.build_v2`` calls this BEFORE this build's own observation has been appended
    to the ledger (the builder appends only after ``validate()`` passes — spec §2), so the
    current session's quadrant/rank/status are supplied explicitly rather than read back
    from disk, exactly mirroring ``theme_state_history``'s own calling convention.
    """
    prior_series = [r for r in entity_rows(rows, entity_kind, entity_id)
                    if r["effective_session"] < current_session]
    series = prior_series + [{"effective_session": current_session, "quadrant": current_quadrant,
                              "status": current_status, "rank": current_rank}]
    state = _state_from_series(series, len(series) - 1)
    prior_sessions = sorted({r["effective_session"] for r in rows if r["entity_kind"] == entity_kind
                             and r["effective_session"] < current_session})
    prev_session = prior_sessions[-1] if prior_sessions else None
    prev_rank = (previous_values(rows, entity_kind, prev_session, "rank") or {}).get(entity_id) \
        if prev_session is not None else None
    rank_change = (current_rank - prev_rank) if (current_rank is not None and prev_rank is not None) else None
    return {**state, "rank_change": rank_change}


# ── corrections receipts (change_summary.source_revisions[]) ───────────────────────────
def revision_receipts(rows: list[dict[str, Any]], revised_at: str) -> list[dict[str, Any]]:
    """Every revision row (``revision_id>0``) stamped with EXACTLY ``revised_at`` — i.e.
    the corrections a single ``append_observations`` call just made — with old→new detail
    (spec §2: "source_revisions populated from revision_receipts"; the UI's revision-row
    LENS carries this "from"/"to" detail).
    """
    by_key: dict[tuple, list[dict[str, Any]]] = {}
    for r in rows:
        by_key.setdefault((r["entity_kind"], r["entity_id"], r["effective_session"]), []).append(r)
    receipts: list[dict[str, Any]] = []
    for r in rows:
        if (r.get("revision_id") or 0) > 0 and r.get("revised_at") == revised_at:
            siblings = by_key[(r["entity_kind"], r["entity_id"], r["effective_session"])]
            prev = next((s for s in siblings if s["revision_id"] == r["revision_id"] - 1), None)
            receipts.append({
                "kind": "revision", "entity_kind": r["entity_kind"], "id": r["entity_id"],
                "effective_session": r["effective_session"], "revision_id": r["revision_id"],
                "from": {f: (prev or {}).get(f) for f in FIELDS},
                "to": {f: r.get(f) for f in FIELDS},
            })
    return receipts
