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

Belief-identity split (B2 repair, W3 repair round): revision comparison covers PRODUCT
fields only — :data:`PRODUCT_FIELDS` (``vel``, ``abs_value``, ``quadrant``, ``state``,
``rank``). CONTEXT fields — :data:`CONTEXT_FIELDS` (``status``, ``coverage_n``) — are
recorded once, at whichever row (``revision_id=0`` or a genuine product revision) first
carries them, and NEVER mint a revision of their own: a leg flapping HEALTHY/DEGRADED/
HEALTHY across three same-session builds with an unchanged product reading must produce
ONE row, not three, and must not black out a real quadrant flip by drowning it in
routine-staleness noise (``revised_ids`` suppression in ``changes.compute_changes`` keys
off revision identity, so a context-only "revision" would wrongly swallow a same-session
transition too). Health/staleness HISTORY still lives in ``state_log.jsonl``'s
``health.legs``/``health.runs`` (:mod:`engine.flow_observatory.changes`) — this split does
not remove that accelerator, it only stops CONTEXT churn from writing ledger rows.
Float contract: two numeric values compare equal after ``round(x, 4)``; ``NaN == NaN`` is
TRUE for this comparison (``math.isnan`` on both sides) — floating noise and a stable-NaN
metric must never manufacture a phantom revision (see :func:`_floats_equal`).

Atomic durability (B1 repair): :func:`_write_ledger` writes a temp file in the same
directory and ``os.replace``s it over the real path — a mid-write crash leaves the
ORIGINAL file untouched, never a half-written one. :func:`read_ledger` returns an empty
ledger only when the file is genuinely MISSING (the honest bootstrap case); a file that
EXISTS but fails to parse raises :class:`LedgerCorrupt` rather than silently degrading to
empty — silently treating "corrupt" the same as "missing" is exactly the failure mode
that let a future append blindly overwrite (and thereby destroy) every closed observation
a torn file still held. Callers (the builder) must catch :class:`LedgerCorrupt` explicitly
and refuse to touch the ledger this build, never fall through to a normal append.

Monotonicity (S5): :func:`append_observations` refuses (raises :class:`ClockStepback`,
writes nothing) when its ``now`` predates the newest ``first_known_at`` already on file —
:func:`replay` treats ``first_known_at`` as a monotonic pipeline clock ("knowable as of
this instant"), and a backdated append would let a later instant claim to know something
an earlier, real build did not.
"""
from __future__ import annotations

import logging
import math
import os
import uuid
from datetime import date as _date, datetime as _datetime, timezone
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from engine.ledger_lane import asia_advance_enabled, nightly_advance_enabled

log = logging.getLogger(__name__)

OBSERVATIONS_REL = Path("flow_observatory") / "observations.parquet"


class LedgerCorrupt(Exception):
    """The ledger file EXISTS but could not be parsed (B1) — never raised for a missing
    file, which is the honest, ordinary bootstrap case and reads as an empty ledger. The
    caller (the builder) must catch this explicitly and refuse to append/rewrite; letting a
    corrupt file silently read as empty would make the next ordinary append overwrite (and
    thereby permanently destroy) every closed observation the torn file still held."""


class ClockStepback(Exception):
    """:func:`append_observations` refused to write (S5): ``now`` predates the ledger's own
    newest ``first_known_at``. The ledger's first-known timestamps are a monotonic pipeline
    clock that :func:`replay` depends on ("knowable as of instant X") — accepting a backdated
    append would let a later replay instant retroactively "know" something no build running
    at that earlier wall-clock time actually knew yet."""


#: PRODUCT fields — the "did the belief change" comparison in append_observations covers
#: ONLY these (B2 belief-identity split; module docstring above).
PRODUCT_FIELDS: tuple[str, ...] = ("vel", "abs_value", "quadrant", "state", "rank")

#: CONTEXT fields — leg/coverage context at observation time. Recorded once (first write)
#: and NEVER themselves mint a revision (B2).
CONTEXT_FIELDS: tuple[str, ...] = ("coverage_n", "status")

#: the full observation payload columns (spec §1 table) — everything else (entity_kind,
#: entity_id, effective_session, revision_id, first_known_at, revised_at) is ledger
#: bookkeeping. Used for row construction and revision_receipts' from/to detail; identity
#: comparison itself uses PRODUCT_FIELDS only (B2) — see module docstring.
FIELDS: tuple[str, ...] = PRODUCT_FIELDS + CONTEXT_FIELDS

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
    (production and test) must go through this one formatter.

    NIT12: keeps millisecond precision (``timespec="milliseconds"``) — two builds racing
    inside the same second must not collapse to the same stamp. A NAIVE ``datetime`` RAISES
    rather than silently being assumed UTC (the previous behavior): a caller that forgot
    ``tzinfo`` could just as easily have meant local time, and guessing UTC either way is a
    build-continuity time bug waiting to happen, not a convenience worth keeping. A bare
    ``str``/pre-formatted stamp (every existing test fixture, and any caller that already
    normalized its own timestamp) passes through unchanged — this validation applies only to
    real ``datetime`` objects.
    """
    if isinstance(now, _datetime):
        if now.tzinfo is None:
            raise ValueError(
                "history._iso: naive datetime is not accepted (NIT12) — every caller must "
                "supply a tz-aware instant; guessing UTC for an unlabeled naive datetime is "
                "exactly the ambiguity this module's monotonic clock cannot afford.")
        return now.astimezone(timezone.utc).isoformat(timespec="milliseconds")
    if isinstance(now, _date):
        return _datetime(now.year, now.month, now.day, tzinfo=timezone.utc).isoformat(timespec="milliseconds")
    return str(now)


def _floats_equal(a: Any, b: Any) -> bool:
    """B2 float contract: numeric values compare equal after ``round(x, 4)``; ``NaN==NaN``
    is TRUE here (``math.isnan`` on both sides) — floating noise (1e-17 jitter) and a
    stable-NaN metric must never manufacture a phantom revision. Non-numeric values (str,
    None, bool) fall through to plain ``==``."""
    a_num = isinstance(a, (int, float)) and not isinstance(a, bool)
    b_num = isinstance(b, (int, float)) and not isinstance(b, bool)
    if a_num and b_num:
        if isinstance(a, float) and isinstance(b, float) and math.isnan(a) and math.isnan(b):
            return True
        return round(float(a), 4) == round(float(b), 4)
    return a == b


def _product_identical(latest_row: dict[str, Any], vals: dict[str, Any]) -> bool:
    """B2 belief-identity split: does ``vals`` (this build's observation payload) match
    ``latest_row``'s belief across PRODUCT_FIELDS ONLY? A CONTEXT-only change (status flap,
    coverage_n drift) with no product difference returns True — no revision minted, no new
    row, and the ledger's context columns simply stay whatever they were at the row that IS
    on file (module docstring, B2)."""
    return all(_floats_equal(latest_row.get(f), vals.get(f)) for f in PRODUCT_FIELDS)


def _row_key(row: dict[str, Any]) -> tuple:
    return (row.get("entity_kind"), row.get("entity_id"), row.get("effective_session"),
            row.get("revision_id"))


# ── I/O boundary (the only functions here that touch disk) ─────────────────────────────
def read_ledger(path: Path) -> list[dict[str, Any]]:
    """Every row, oldest-first by key.

    B1 repair (was: "a corrupt/missing file reads as an empty ledger, never fatal"). That
    conflated two very different situations: a MISSING file (the honest bootstrap case —
    no guarded lane has ever appended here yet) genuinely IS an empty ledger, and still
    reads as ``[]``. A file that EXISTS but fails to parse is a torn/truncated write, not an
    empty ledger — silently returning ``[]`` for it is how a later ordinary append would
    overwrite (and thereby permanently destroy) every closed observation the file still
    held, exactly the failure this module's whole immutability law exists to prevent. That
    case now raises :class:`LedgerCorrupt`; the caller (the builder) must catch it
    explicitly and refuse to touch the ledger this build.
    """
    if not Path(path).exists():
        return []
    try:
        table = pq.read_table(path, schema=LEDGER_SCHEMA)
    except Exception as e:  # noqa: BLE001 — re-raised as a typed, catchable error below
        raise LedgerCorrupt(f"observations ledger exists but is unreadable: {e}") from e
    rows = table.to_pylist()
    rows.sort(key=_row_key)
    return rows


def _write_ledger(path: Path, rows: list[dict[str, Any]]) -> None:
    """B1 repair: atomic write. The old body wrote the real ``path`` directly — a crash
    mid-``write_table`` (disk full, killed process, power loss) left a partial/truncated
    file in the ledger's own place, and the NEXT read would raise :class:`LedgerCorrupt`
    against a file this module itself produced. Write a temp file in the SAME directory
    (same filesystem, so ``os.replace`` is atomic) and only ``os.replace`` it over the real
    path once the write has fully succeeded — a crash before that point leaves the ORIGINAL
    file byte-for-byte untouched, never a half-written one.
    """
    ordered = sorted(rows, key=_row_key)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist(ordered, schema=LEDGER_SCHEMA)
    tmp_path = path.with_name(f".{path.name}.tmp-{os.getpid()}-{uuid.uuid4().hex}")
    try:
        # compression=None + a fixed row/column order is what makes byte-identical writes
        # possible across repeated calls with the same logical content (spec test 1) — no
        # dictionary-encoding nondeterminism, no wall-clock-derived metadata.
        pq.write_table(table, tmp_path, compression="none", use_dictionary=False)
        os.replace(tmp_path, path)
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:  # noqa: BLE001 — best-effort cleanup; the raise below is what matters
            pass
        raise


# ── append (the one mutator) ────────────────────────────────────────────────────────────
def _diff_entities(rows: list[dict[str, Any]], session: str,
                   entities: dict[tuple[str, str], dict], now_iso: str) -> list[dict[str, Any]]:
    """Pure — the new rows (if any) that appending ``entities`` for ``session`` against the
    ledger content ``rows`` would produce. Shared by :func:`append_observations` (which
    writes them) and :func:`preview_revisions` (which does not) so the two can never
    disagree about what counts as a change.

    B2 belief-identity split: a key never seen before always gets a fresh ``revision_id=0``
    row (nothing to compare against). For an EXISTING key, identity is decided by
    :func:`_product_identical` — PRODUCT_FIELDS only. A context-only change (status flap,
    coverage_n drift) with the SAME product reading is a no-op: no new row, and the
    context columns simply stay whatever the row on file already says (module docstring).
    """
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
        if _product_identical(latest_row, vals):
            continue  # context-only or truly-identical belief — no row (B2, spec test 2)
        next_rev = int(latest_row["revision_id"]) + 1
        new_rows.append({"entity_kind": ekind, "entity_id": eid, "effective_session": session,
                         "revision_id": next_rev, "first_known_at": now_iso, "revised_at": now_iso,
                         **vals})
    return new_rows


def _new_row_keys(new_rows: list[dict[str, Any]]) -> set[tuple]:
    """NIT13: the exact identity of every REVISION row (``revision_id>0``) ``new_rows`` just
    produced — what :func:`revision_receipts` keys on, replacing the old ``revised_at``
    timestamp match (two independent revisions minted at literally the same instant, or two
    fixture rows built with the same hand-written stamp, previously collided)."""
    return {(r["entity_kind"], r["entity_id"], r["effective_session"], r["revision_id"])
           for r in new_rows if r["revision_id"] > 0}


def preview_revisions(rows: list[dict[str, Any]], session: str | None,
                      entities: dict[tuple[str, str], dict], now: Any,
                      require_lane: bool = True) -> list[dict[str, Any]]:
    """Pure, no write — exactly what :func:`append_observations` WOULD record as revisions
    for ``(session, entities)`` against the ledger's CURRENT content. The builder calls this
    BEFORE ``validate()`` (change_summary.source_revisions must exist inside the payload
    validate() checks), and the real, lane-gated, disk-writing append happens only AFTER
    validate() passes (spec §2 ordering) — both paths share :func:`_diff_entities` so the
    preview can never diverge from what actually gets written a moment later.

    M10: gated on ``require_lane`` (default True), the SAME gate :func:`append_observations`
    uses — an off-lane build (a PR check, an ad-hoc local run) must never show a REVISED
    what-changed marker for a correction it will never actually persist; previously this
    function ran unconditionally regardless of lane, so change_summary could disagree with
    what the ledger would actually hold after the build. ``require_lane=False`` is the same
    test/backfill seam ``append_observations`` exposes.
    """
    if require_lane and not advance_enabled():
        return []
    if not session or not entities:
        return []
    now_iso = _iso(now)
    new_rows = _diff_entities(rows, session, entities, now_iso)
    if not new_rows:
        return []
    return revision_receipts(rows + new_rows, _new_row_keys(new_rows))


def append_observations(path: Path, session: str | None, entities: dict[tuple[str, str], dict],
                        now: Any, require_lane: bool = True) -> dict[str, Any]:
    """Append (or idempotently no-op, or revise) this session's belief for each entity.

    ``entities``: ``{(entity_kind, entity_id): {<subset of FIELDS>}}`` — the observation
    payload for ``session``. Missing FIELDS default to ``None`` (honest null, never a
    fabricated zero).

    Gated on ``require_lane`` (default True) — off the nightly/asia-close lane, this is a
    pure no-op that touches nothing on disk (spec test 8: "non-owner lane cannot append").

    B1: ``read_ledger`` may raise :class:`LedgerCorrupt` — this function does NOT catch it;
    a corrupt file must never be silently treated as empty-then-overwritten. The caller (the
    builder) catches it and refuses to touch the ledger this build.

    S5: refuses (raises :class:`ClockStepback`, writes nothing) when ``now`` predates the
    ledger's own newest ``first_known_at`` — see the module docstring's Monotonicity note.
    """
    if require_lane and not advance_enabled():
        log.info("flow_observatory: observations append skipped (off nightly/asia-close lane)")
        return {"written": False, "reason": "off_ledger_lane", "rows_added": 0, "revisions": []}
    if not session:
        return {"written": False, "reason": "no_session", "rows_added": 0, "revisions": []}
    if not entities:
        return {"written": False, "reason": "no_entities", "rows_added": 0, "revisions": []}

    rows = read_ledger(path)  # may raise LedgerCorrupt — not caught here, see docstring
    now_iso = _iso(now)
    newest_known = max((r.get("first_known_at") for r in rows if r.get("first_known_at")),
                       default=None)
    if newest_known is not None and now_iso < newest_known:
        raise ClockStepback(
            f"append_observations: now={now_iso!r} predates the ledger's newest "
            f"first_known_at={newest_known!r} — refusing to write (S5 monotonicity)")
    new_rows = _diff_entities(rows, session, entities, now_iso)
    if not new_rows:
        return {"written": False, "reason": "no_changes", "rows_added": 0, "revisions": []}

    out_rows = rows + new_rows
    _write_ledger(path, out_rows)
    revisions = revision_receipts(out_rows, _new_row_keys(new_rows))
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
    :func:`state_for_session`).

    B3 pinned age semantics (repair round — replaces the old "stale row recurses onto
    yesterday's answer verbatim" recursion, which returned ``state_age_sessions=None``
    FOREVER once the recursion bottomed out on a stale row-zero — an all-stale baseline
    never rendered a chip again, in perpetuity, in the actual live regime):

    * onset = the first ledger row in the CURRENT state, stale-stamped or not. The only row
      that never gets a numeric age is ``series[0]`` itself (``idx==0``) — there is
      structurally no prior data to compare against, so it reports the honest
      "first tracked session" null, same as before.
    * age = 1 + the count of NON-stale sessions, walking backward from ``idx-1``, that
      share the row's own quadrant — a STALE/UNAVAILABLE row encountered along the way is
      TRANSPARENT (skipped: neither extends nor breaks the run, spec test 5/6 gap rule).
      The row being described itself only contributes its own "+1" when it is NOT stale;
      a stale current row still gets that +1 floored to 1 (never 0) — the chip renders
      with the ❄ marker even when EVERY session in the run so far has been stale-stamped
      (an all-stale baseline reports age=1 at every session after the first, not a
      permanent null).
    * a FLIP is a flip regardless of staleness: when the row's own quadrant differs from
      the nearest (stale-skipped) prior quadrant, onset is THIS row and age is 1 — even if
      this row's own read is itself stale-stamped. The chip (this row's quadrant) and the
      LENS (onset = this session, prior_state = the OLD quadrant) then describe the SAME
      state, never a stale-frozen echo of the state that just ended.
    * prior_state applies the identical stale-skip walk: the null/undefined quadrant of a
      transparently-skipped stale row is never reported as "the" prior state.
    * note is ``"age frozen (stale source)"`` whenever the row being described is itself
      stale/unavailable (continuation OR flip) — the UI's ❄ marker and "source behind" LENS
      text key off this string; ``None`` otherwise.
    """
    row = series[idx]
    if idx == 0:
        return {"state_started": None, "state_age_sessions": None, "prior_state": None,
               "note": "first tracked session"}
    quadrant = row.get("quadrant")
    is_stale = row.get("status") in _NOT_COUNTABLE
    started = row["effective_session"]
    age = 0 if is_stale else 1
    prior_state = None
    j = idx - 1
    while j >= 0:
        prow = series[j]
        if prow.get("status") in _NOT_COUNTABLE:
            j -= 1
            continue  # transparent — never counted, never breaks the run
        if prow.get("quadrant") != quadrant:
            prior_state = prow.get("quadrant")
            break
        started, age = prow["effective_session"], age + 1
        j -= 1
    else:
        # walked off the front of the series without a quadrant change (every prior row
        # either matched or was a transparent stale skip) — onset is the series' own first
        # row, and there is nothing known before "ever" to report as prior_state.
        started = series[0]["effective_session"]
    age = max(age, 1)
    note = "age frozen (stale source)" if is_stale else None
    return {"state_started": started, "state_age_sessions": age, "prior_state": prior_state,
           "note": note}


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
def revision_receipts(rows: list[dict[str, Any]], keys: set[tuple]) -> list[dict[str, Any]]:
    """Every revision row whose ``(entity_kind, entity_id, effective_session, revision_id)``
    identity is in ``keys`` — i.e. EXACTLY the corrections a single ``append_observations``/
    ``preview_revisions`` call just produced — with old→new detail (spec §2:
    "source_revisions populated from revision_receipts"; the UI's revision-row LENS carries
    this "from"/"to" detail).

    NIT13: keyed on the row's own IDENTITY (built by :func:`_new_row_keys` from the exact
    rows this call's diff produced), never on a ``revised_at`` TIMESTAMP match — two
    independent revisions minted at the same instant (a fast build, or two fixture rows
    hand-built with the same literal stamp in a test) used to collide under timestamp
    matching, pulling an unrelated historical revision into THIS run's receipts.
    """
    if not keys:
        return []
    by_key: dict[tuple, list[dict[str, Any]]] = {}
    for r in rows:
        by_key.setdefault((r["entity_kind"], r["entity_id"], r["effective_session"]), []).append(r)
    receipts: list[dict[str, Any]] = []
    for r in rows:
        rk = (r["entity_kind"], r["entity_id"], r["effective_session"], r.get("revision_id") or 0)
        if rk in keys:
            siblings = by_key[(r["entity_kind"], r["entity_id"], r["effective_session"])]
            prev = next((s for s in siblings if s["revision_id"] == r["revision_id"] - 1), None)
            receipts.append({
                "kind": "revision", "entity_kind": r["entity_kind"], "id": r["entity_id"],
                "effective_session": r["effective_session"], "revision_id": r["revision_id"],
                "from": {f: (prev or {}).get(f) for f in FIELDS},
                "to": {f: r.get(f) for f in FIELDS},
            })
    return receipts
