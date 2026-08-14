"""Prophet Board read — the canonical plan-book enrichment + actionability join.

MP-1 spawn gate **G-D**.  The Board migration needs two things for every row of the
plan book, not for the candidate intersection it happens to overlap:

1. the **entry/actionability axis** (``entry_signal.status``) — so a stance can be
   stated, or its absence disclosed;
2. **name · sector · lane · spark** — so the card is a card.

Measured on the 2026-08-13 payload before this module existed: the axis reached
**61/179** plan rows and the enrichment **45/179**.  This module publishes the join
that closes that gap, and — where it cannot be closed — says so in a machine-readable
way instead of guessing.

WHY THE GAP EXISTED — publication, not availability
---------------------------------------------------
Both halves were already computed for the whole US library universe and then
discarded at the publication boundary:

* ``scripts/build_stock_library.py`` runs :func:`engine.entry_signal.assess` inside its
  per-name universe loop, and builds ``disp_map[ticker]`` (price / off-high / spark) in
  that same loop — for **every** name.  Only the rows that made a *board bucket* carried
  either into ``site/factordata/us_standouts.json``.
* ``site/prophet/index.json`` published ``entry_status`` off the **stored plan**, where
  it is an ANTICIPATION §6.2 A1 *admission* stamp: frozen at origination and ``None`` on
  every plan originated before ``anticipation-v1-2026-08-08``.  That null is the era
  boundary and is deliberately not back-filled.

So the plan book was joining a *ledger* population (every still-active plan) against a
*screener* population (today's board), and reading an *origination* stamp as if it were
a live read.  Both are population mismatches, not missing information.

WHAT THIS MODULE DOES NOT DO
----------------------------
* It **never** touches ``entry_status``.  That field stays exactly what it is — the
  frozen admission stamp — because consumers (``engine/us_candidate_lanes``,
  ``engine/prophet_arena``, the shadow ledgers) read it as provenance.  The live read
  ships beside it under :data:`BLOCK_KEY`, and the two are separately labelled.
* It **never** substitutes ``recommended_action``.  That engine is trade-management-only
  and carries display/narrative authority, not order authority (operator ruling
  2026-08-13).
* It **never** defaults an unknown row to ``wait``, or to any other stance.  A row whose
  axis cannot be obtained is :data:`BLOCKED_DATA` with a named cause.  Coverage is an
  outcome here, not a target: mapping unknowns to a cautious-looking verb would
  originate a signal the engine never stated.
* It **never** derives a ``lane`` for a name the board did not admit.  ``lane`` is a
  board-membership label (``scripts/build_stock_library._lane_for`` is total — it
  returns ``bottoming`` for input it does not recognise), so computing one off-board
  would fabricate a setup archetype rather than report one.  Off-board rows are
  :data:`NOT_APPLICABLE`, and ``lane`` therefore has a real ceiling below 100%.

SCOPE — ticker-level measurement, plan-level applicability
----------------------------------------------------------
The join key is the **ticker**, so one library record fans out to every plan episode on
that name.  That is intended and is disclosed as ``scope: "ticker"``.  What must never
happen is the reverse — episodes collapsing into one row — so the join is applied per
plan ``id`` and *applicability* is decided per plan: a closed plan's stance is
:data:`NOT_APPLICABLE` (``plan_closed``) even when its ticker has a perfectly good live
read, because a resolved plan has no live stance to state.

Everything here is pure and offline-testable: :class:`LibraryIndex` is the only thing
that touches the filesystem, and it is injectable.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

SCHEMA = "prophet.board_read/v1"
COVERAGE_SCHEMA = "prophet.board_read_coverage/v1"

#: The key each plan row carries the block under.
BLOCK_KEY = "board_read"
#: Index-level keys — declared lineage, and the telemetry that makes a 179→45
#: regression loud instead of silent.
LINEAGE_KEY = "board_read_lineage"
COVERAGE_KEY = "board_read_coverage"

# ── the three honest states ───────────────────────────────────────────────────
#: The field carries a real value from a declared source.
AVAILABLE = "available"
#: The field is *meaningful* for this row but could not be obtained.  A disclosed
#: absence with a named cause — never a substituted default.
BLOCKED_DATA = "blocked_data"
#: The field does not apply to this row at all.  Distinct from BLOCKED_DATA: nothing
#: is missing, so nothing is owed.
NOT_APPLICABLE = "not_applicable"

STATES = (AVAILABLE, BLOCKED_DATA, NOT_APPLICABLE)

# ── reason vocabulary — CLOSED SET, pinned by tests ───────────────────────────
#: A closed/resolved plan has no live stance.  Not missing — not applicable.
R_PLAN_CLOSED = "plan_closed"
#: The per-ticker library tree is absent entirely (this lane ran without
#: build_stock_library).  Distinguished from a per-ticker miss so a whole-source
#: outage never reads as 179 individually-unlucky tickers.
R_SOURCE_UNAVAILABLE = "library_source_unavailable"
#: The source is present but carries no record for this ticker — a genuine population
#: miss (foreign ADR, delisting, symbol outside the US library universe).
R_TICKER_ABSENT = "ticker_absent_from_library"
#: The record is present but the gauge self-gated.  The suffix is
#: ``engine.entry_signal.null_reason``'s own vocabulary, reused verbatim rather than
#: re-invented (``no_cycle_ladder`` / ``short_history`` / ``not_assessed`` /
#: ``gauge_error:<Type>``), so one cause has one name across the system.
R_GAUGE_NULL_PREFIX = "gauge_null:"
#: The record is present, has no ``entry_signal``, and disclosed no reason either.
#: Unreachable once the producer stamps ``entry_signal_null_reason`` onto the record;
#: kept so the failure is disclosed rather than silent if that stamp regresses.
R_GAUGE_UNDISCLOSED = "gauge_absent_undisclosed"
#: The record is present and readable but simply does not carry this field.
R_FIELD_ABSENT = "field_absent_in_record"
#: The ticker is not on the board, so no board bucket assigns it a lane.  Deriving one
#: would invent a setup archetype for a name the board never admitted.
R_NOT_ON_BOARD = "not_on_board"
#: The ticker IS on the board, in a bucket whose rows carry no lane by construction
#: (``laggards``).  Still not applicable — but for a different, recorded reason.
R_BUCKET_NO_LANE = "board_bucket_carries_no_lane"

REASONS = frozenset({
    R_PLAN_CLOSED, R_SOURCE_UNAVAILABLE, R_TICKER_ABSENT, R_GAUGE_UNDISCLOSED,
    R_FIELD_ABSENT, R_NOT_ON_BOARD, R_BUCKET_NO_LANE,
})

# ── sources ───────────────────────────────────────────────────────────────────
#: Primary — the per-ticker record ``build_stock_library`` writes for the whole US
#: universe.  Runner-local (``site/stockdata/`` is gitignored) but written in the SAME
#: nightly job, minutes before ``build_prophet`` runs (daily.yml: "Prophet nightly …
#: AFTER build_site").
SRC_LIBRARY = "us_stock_library"
#: Fallback — the committed board artifact.  A *projection of the same records* by the
#: same producer, so it is the same authority at a narrower population; it is the only
#: source for ``lane``, which exists only as a board-membership label.
SRC_STANDOUTS = "us_standouts"

#: The governed fields, in publication order.  ``price``/``change`` are deliberately
#: NOT here: the plan row already carries ``last_price`` from the management engine at
#: full coverage (174/179 on the 2026-08-13 payload), and the live quote is owned by the
#: page's ``data-sym`` path — this lane has no evidence that path is insufficient.
FIELDS = ("status", "name", "sector", "lane", "spark")

#: Sparkline SVGs are ~2 KB each.  Inlining 177 of them would grow ``index.json`` by
#: ~448 KB — 66% — every night, for a field only the Board renders while a dozen other
#: consumers (Brain, the Terminal, radar_internal, prophet_governor, us_candidate_lanes,
#: options_issue_desk, the R2 mirror) pay for it.  So the SVG bodies ship in this
#: ticker-keyed sibling and the plan row's ``spark`` field carries a resolvable
#: reference into it.  The three-state contract is unchanged: ``available`` still means
#: a spark exists for this row, and it is verified against the map, not assumed.
SPARKS_FILENAME = "board_read_sparks.json"
SPARKS_SCHEMA = "prophet.board_read_sparks/v1"

#: The twelve-value actionability domain the shipped engine partitions
#: (``engine/us_board_rank.py`` ``_LIVE_/_SETTING_UP_/_RAN_/_BLOCKED_STATUSES``) plus
#: the three that carry an entry value but sit in no bucket.  Used ONLY to count
#: unmapped words into telemetry — an unknown status is still published verbatim, never
#: dropped and never re-labelled.
KNOWN_STATUSES = frozenset({
    "buy_now", "partial", "buy_soon",
    "await_confluence", "bounce_wait", "watch", "wait_pullback", "later", "await",
    "extended", "topping", "hold",
    "blocked", "exit", "avoid",
})


def _clean(value: Any) -> Any:
    """``None`` for anything that is not a usable published value.

    Empty string / list / dict are absences wearing a value's clothes; treating them
    as present is how a coverage number stops meaning anything.
    """
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    if isinstance(value, (list, dict, tuple, set)) and not value:
        return None
    return value


def _field(value: Any = None, *, state: str, reason: str | None = None,
           source: str | None = None) -> dict[str, Any]:
    """One governed field's terminal answer.  Every field ends in exactly one."""
    return {"value": value, "state": state, "reason": reason, "source": source}


def _available(value: Any, source: str) -> dict[str, Any]:
    return _field(value, state=AVAILABLE, source=source)


def _blocked(reason: str) -> dict[str, Any]:
    return _field(state=BLOCKED_DATA, reason=reason)


def _not_applicable(reason: str) -> dict[str, Any]:
    return _field(state=NOT_APPLICABLE, reason=reason)


def safe_ticker(ticker: str) -> str:
    """Library filename stem for a ticker.

    Mirrors ``build_stock_library``'s own mapping (``scripts/build_stock_library.py``:
    ``safe = ticker.replace("=", "_").replace("^", "_")``).  Two spellings of one file
    name is a silent join miss, so this is the single reader.
    """
    return str(ticker or "").replace("=", "_").replace("^", "_")


class LibraryIndex:
    """Lazy reader over ``site/stockdata/<TICKER>.json`` — the only I/O in this module.

    The tree is ~1600 records / ~95 MB, so records are read on demand (a plan book
    touches ~166 of them) and cached.  ``available`` is False when the directory itself
    is absent, which is what separates a whole-source outage from per-ticker misses.
    """

    def __init__(self, root: "str | Path | None") -> None:
        self.root = Path(root) if root is not None else None
        self.available = bool(self.root and self.root.is_dir())
        self._cache: dict[str, dict | None] = {}
        self.read_errors: dict[str, str] = {}

    def get(self, ticker: str) -> dict | None:
        """The record for ``ticker``, or ``None`` when absent/unreadable.

        An unreadable record is counted as absent AND recorded in ``read_errors``: the
        row still gets a disclosed null, and the parse failure stays visible in the
        build log rather than being laundered into a clean-looking miss.
        """
        if not self.available:
            return None
        key = safe_ticker(ticker)
        if key in self._cache:
            return self._cache[key]
        path = self.root / f"{key}.json"  # type: ignore[operator]
        rec: dict | None = None
        if path.is_file():
            try:
                with path.open(encoding="utf-8") as fh:
                    loaded = json.load(fh)
                rec = loaded if isinstance(loaded, dict) else None
                if rec is None:
                    self.read_errors[key] = "not_an_object"
            except Exception as exc:  # noqa: BLE001 — a bad record must not kill the build
                self.read_errors[key] = f"{type(exc).__name__}"
                log.warning("prophet_board_read: library record %s unreadable (%s)",
                            path.name, type(exc).__name__)
        self._cache[key] = rec
        return rec

    def as_of(self) -> str | None:
        """Run date of the records actually read, when they agree; else ``None``.

        Read off the records themselves rather than taken from the caller, so the
        published vintage cannot claim a freshness the data does not have.
        """
        stamps = {
            str(rec.get("asof") or rec.get("as_of") or "")[:10]
            for rec in self._cache.values() if isinstance(rec, dict)
        }
        stamps.discard("")
        return next(iter(stamps)) if len(stamps) == 1 else None


#: Board buckets whose rows carry a ``lane``, and the bucket that does not.
#: ``laggards`` rows are built without a lane by construction; ``ran``/``leaders``/
#: ``watch`` carry a constant lane, ``buy`` the real archetype split.
LANE_BEARING_BUCKETS = ("buy", "watch", "leaders", "ran")
BUCKETS = ("buy", "watch", "leaders", "laggards", "ran")


def standouts_index(standouts: Mapping[str, Any] | None) -> dict[str, dict]:
    """``{ticker: row}`` over every board bucket, first bucket wins.

    Bucket order is :data:`BUCKETS`, so a name in both ``buy`` and ``watch`` resolves to
    its ``buy`` row — the same precedence the board itself displays.
    """
    out: dict[str, dict] = {}
    if not isinstance(standouts, Mapping):
        return out
    for bucket in BUCKETS:
        rows = standouts.get(bucket)
        if not isinstance(rows, Sequence):
            continue
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            ticker = _clean(row.get("ticker"))
            if ticker and ticker not in out:
                enriched = dict(row)
                enriched["_bucket"] = bucket
                out[str(ticker)] = enriched
    return out


def _status_field(plan: Mapping[str, Any], rec: Mapping[str, Any] | None,
                  board: Mapping[str, Any] | None, *,
                  source_available: bool) -> dict[str, Any]:
    """The entry/actionability axis for one plan row.

    Precedence: plan-level applicability first (a closed plan has no live stance at
    all), then the library record, then the committed board row.  Never a default.
    """
    if plan.get("closed") is True:
        return _not_applicable(R_PLAN_CLOSED)

    for candidate, source in ((rec, SRC_LIBRARY), (board, SRC_STANDOUTS)):
        if not isinstance(candidate, Mapping):
            continue
        signal = candidate.get("entry_signal")
        status = _clean(signal.get("status")) if isinstance(signal, Mapping) else None
        if status:
            return _available(str(status).strip().lower(), source)

    # Nothing answered — say WHY, from the most specific record we actually held.
    for candidate in (rec, board):
        if isinstance(candidate, Mapping):
            disclosed = _clean(candidate.get("entry_signal_null_reason"))
            if disclosed:
                return _blocked(f"{R_GAUGE_NULL_PREFIX}{disclosed}")
            return _blocked(R_GAUGE_UNDISCLOSED)
    return _blocked(R_SOURCE_UNAVAILABLE if not source_available else R_TICKER_ABSENT)


def _enrichment_field(name: str, rec: Mapping[str, Any] | None,
                      board: Mapping[str, Any] | None, *,
                      source_available: bool) -> dict[str, Any]:
    """``name`` / ``sector`` / ``spark_svg`` — library first, board second."""
    for candidate, source in ((rec, SRC_LIBRARY), (board, SRC_STANDOUTS)):
        if isinstance(candidate, Mapping):
            value = _clean(candidate.get(name))
            if value is not None:
                return _available(value, source)
    if rec is None and board is None:
        return _blocked(R_SOURCE_UNAVAILABLE if not source_available else R_TICKER_ABSENT)
    return _blocked(R_FIELD_ABSENT)


def _lane_field(board: Mapping[str, Any] | None) -> dict[str, Any]:
    """``lane`` — board-membership label, board rows ONLY.

    Off-board is :data:`NOT_APPLICABLE`, not blocked: the label is undefined for a name
    the board never admitted, so nothing is owed.  This is why ``lane`` coverage has a
    ceiling well under 100% and why that is the correct answer rather than a shortfall.
    """
    if not isinstance(board, Mapping):
        return _not_applicable(R_NOT_ON_BOARD)
    lane = _clean(board.get("lane"))
    if lane is not None:
        return _available(str(lane), SRC_STANDOUTS)
    return _not_applicable(R_BUCKET_NO_LANE)


def _spark_field(ticker: str, rec: Mapping[str, Any] | None,
                 board: Mapping[str, Any] | None, *, source_available: bool,
                 sparks: dict[str, str] | None) -> dict[str, Any]:
    """``spark`` — a reference into :data:`SPARKS_FILENAME`, not the SVG body.

    ``available`` is decided by whether an SVG was actually found and banked, so the
    reference can never point at nothing.  ``sparks`` is the accumulator the caller
    later writes out; passing ``None`` resolves presence without banking (used by
    read-only callers and by the tests).
    """
    svg = _enrichment_field("spark_svg", rec, board, source_available=source_available)
    if svg["state"] != AVAILABLE:
        return svg
    if sparks is not None and ticker:
        sparks[ticker] = str(svg["value"])
    return _available(f"{SPARKS_FILENAME}#{ticker}", str(svg["source"]))


def build_board_read(plan: Mapping[str, Any], *, library: LibraryIndex | None = None,
                     board_rows: Mapping[str, Mapping[str, Any]] | None = None,
                     sparks: dict[str, str] | None = None,
                     ) -> dict[str, Any]:
    """The :data:`BLOCK_KEY` block for ONE plan row.

    Pure apart from ``library``'s lazy read.  Keyed on the plan's ``asset`` (ticker) but
    applied per plan ``id``, so two open episodes on one name each get their own block
    carrying the same ticker-level measurement — fan-out, never collapse.
    """
    ticker = str(_clean(plan.get("asset")) or "")
    source_available = bool(library.available) if library is not None else False
    rec = library.get(ticker) if (library is not None and ticker) else None
    board = (board_rows or {}).get(ticker)

    fields = {
        "status": _status_field(plan, rec, board, source_available=source_available),
        "name": _enrichment_field("name", rec, board, source_available=source_available),
        "sector": _enrichment_field("sector", rec, board, source_available=source_available),
        "lane": _lane_field(board),
        "spark": _spark_field(ticker, rec, board, source_available=source_available,
                              sparks=sparks),
    }
    as_of = None
    if isinstance(rec, Mapping):
        as_of = _clean(str(rec.get("asof") or rec.get("as_of") or "")[:10])
    elif isinstance(board, Mapping):
        as_of = _clean(str(board.get("signal_asof") or "")[:10])
    return {
        "schema": SCHEMA,
        # The measurement is a property of the TICKER; applicability is a property of
        # the PLAN.  Stated on the row so a surface cannot present a ticker-level read
        # as a per-episode judgement.
        "scope": "ticker",
        "ticker": ticker or None,
        "as_of": as_of,
        "fields": {key: fields[key] for key in FIELDS},
    }


def attach(plans: Iterable[dict], *, library: LibraryIndex | None = None,
           standouts: Mapping[str, Any] | None = None) -> dict[str, str]:
    """Stamp :data:`BLOCK_KEY` onto every plan row in place; return the sparks map.

    One pass, one block per plan ``id``.  Rows are mutated in place because
    ``index["plans"]`` is the same list object.  The returned map is ticker-keyed (so
    the 12 multi-episode names bank one SVG, not one per episode) and is what
    :func:`sparks_artifact` writes out.
    """
    board_rows = standouts_index(standouts)
    sparks: dict[str, str] = {}
    for plan in plans:
        plan[BLOCK_KEY] = build_board_read(plan, library=library, board_rows=board_rows,
                                           sparks=sparks)
    return sparks


def sparks_artifact(sparks: Mapping[str, str], *,
                    library: LibraryIndex | None = None,
                    standouts: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """The sibling artifact the ``spark`` references resolve into."""
    board_as_of = None
    if isinstance(standouts, Mapping):
        board_as_of = _clean(str(standouts.get("as_of") or "")[:10])
    return {
        "schema": SPARKS_SCHEMA,
        "join_key": "ticker",
        "as_of": (library.as_of() if library is not None else None) or board_as_of,
        "source": (
            "spark_svg from the same producer as the rest of the board read —"
            " scripts/build_stock_library.py, per-name universe loop"
        ),
        "note": (
            "Referenced from site/prophet/index.json plans[].board_read.fields.spark"
            f" as \"{SPARKS_FILENAME}#<TICKER>\". Split out because the SVG bodies are"
            " ~2 KB each and index.json has a dozen consumers that never render one."
        ),
        "n": len(sparks),
        "sparks": dict(sorted(sparks.items())),
    }


def coverage(plans: Sequence[Mapping[str, Any]], *,
             library: LibraryIndex | None = None) -> dict[str, Any]:
    """Per-field coverage telemetry over the stamped rows.

    Published so the G-D numbers are readable off the artifact itself rather than
    re-measured by whoever next wonders — and so a regression from 179 back to 45 shows
    up as a number that moved, not as a board that quietly went quiet.

    The invariant every field satisfies, and ``tests/test_prophet_board_read.py`` pins:
    ``available + blocked_data + not_applicable == rows``.
    """
    rows = list(plans)
    by_field: dict[str, Any] = {}
    unmapped: dict[str, int] = {}
    for name in FIELDS:
        states = {AVAILABLE: 0, BLOCKED_DATA: 0, NOT_APPLICABLE: 0}
        reasons: dict[str, int] = {}
        sources: dict[str, int] = {}
        for row in rows:
            block = row.get(BLOCK_KEY) or {}
            field = (block.get("fields") or {}).get(name) or {}
            # An unrecognised/absent state is itself a defect; count it under its own
            # key rather than letting it vanish from a sum that then looks correct.
            state = str(field.get("state") or "missing")
            states[state] = states.get(state, 0) + 1
            reason = field.get("reason")
            if reason:
                reasons[str(reason)] = reasons.get(str(reason), 0) + 1
            source = field.get("source")
            if source:
                sources[str(source)] = sources.get(str(source), 0) + 1
            if name == "status" and state == AVAILABLE:
                value = str(field.get("value") or "")
                if value and value not in KNOWN_STATUSES:
                    unmapped[value] = unmapped.get(value, 0) + 1
        by_field[name] = {
            **states,
            "reasons": dict(sorted(reasons.items())),
            "sources": dict(sorted(sources.items())),
        }
    return {
        "schema": COVERAGE_SCHEMA,
        "rows": len(rows),
        "source_available": bool(library.available) if library is not None else False,
        "source_as_of": library.as_of() if library is not None else None,
        "read_errors": dict(sorted((library.read_errors if library else {}).items())),
        "by_field": by_field,
        # A status word the shipped engine buckets do not name.  Published verbatim on
        # the row (never dropped, never re-labelled) and counted here, so a domain drift
        # surfaces as telemetry instead of as a stance the Board cannot project.
        "status_unmapped": dict(sorted(unmapped.items())),
        "blocked_data_rows": sum(
            1 for row in rows
            if any((((row.get(BLOCK_KEY) or {}).get("fields") or {}).get(f) or {})
                   .get("state") == BLOCKED_DATA for f in FIELDS)
        ),
    }


def lineage(*, library: LibraryIndex | None = None,
            standouts: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Declared source / join key / vintage semantics for the block.

    Published once at index level rather than repeated on 179 rows.  A join whose
    sources are not declared is a number nobody can audit later.
    """
    board_as_of = None
    if isinstance(standouts, Mapping):
        board_as_of = _clean(str(standouts.get("as_of") or "")[:10])
    return {
        "schema": SCHEMA,
        "join_key": "ticker",
        "scope": (
            "ticker-level measurement fanned into plan rows; plan identity is never"
            " collapsed and applicability is decided per plan"
        ),
        "states": list(STATES),
        "authority": {
            "status": (
                "engine/entry_signal.assess -> entry_signal.status, the entry/"
                "actionability axis. NOT recommended_action (trade-management only,"
                " display/narrative authority, not order authority) and never a"
                " defaulted stance."
            ),
            "lane": (
                "board-membership label from the standouts buckets; undefined off-board,"
                " so off-board rows are not_applicable rather than derived"
            ),
            "spark": (
                f"a resolvable reference of the form \"{SPARKS_FILENAME}#<TICKER>\" into"
                f" site/prophet/{SPARKS_FILENAME}; `available` means the SVG was found"
                " and banked there, never that one is assumed to exist"
            ),
        },
        "sources": [
            {
                "id": SRC_LIBRARY,
                "path": "site/stockdata/<TICKER>.json",
                "producer": "scripts/build_stock_library.py",
                "population": "US stock-library universe (~1600 names)",
                "as_of": library.as_of() if library is not None else None,
                "as_of_basis": "the record's own `asof`, read back from the file",
                "available": bool(library.available) if library is not None else False,
                "fields": ["status", "name", "sector", "spark"],
            },
            {
                "id": SRC_STANDOUTS,
                "path": "site/factordata/us_standouts.json",
                "producer": "scripts/build_stock_library.py (board projection)",
                "population": f"board buckets ({', '.join(BUCKETS)})",
                "as_of": board_as_of,
                "as_of_basis": "the artifact's `as_of`",
                "available": bool(standouts),
                "fields": ["status", "name", "sector", "lane", "spark"],
            },
        ],
        "not_applicable_rules": {
            R_PLAN_CLOSED: "a closed plan has no live stance to state",
            R_NOT_ON_BOARD: "lane is a board-membership label; off-board it is undefined",
            R_BUCKET_NO_LANE: "the row's board bucket carries no lane by construction",
        },
        "note": (
            "entry_status on the plan row is UNCHANGED and remains the frozen"
            " ANTICIPATION §6.2 A1 admission stamp (null before"
            " anticipation-v1-2026-08-08). This block is the live read and is separately"
            " labelled; the two are different questions and must not be conflated."
        ),
    }
