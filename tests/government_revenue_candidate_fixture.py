"""Canonical input boundary shared by the Government Revenue candidate suites.

Both candidate suites deliberately project the *live* committed generation under
``data/government_revenue/`` rather than a pinned copy: that makes them a live
probe over the artifact the site actually ships, which a frozen fixture cannot
be.  The price is that the suites inherit the collection lane's clock.

``build_government_revenue_candidates`` refuses any source whose ``known_at`` is
after the frozen ``generated_at`` it was handed (``_validate_canonical_latest_
workspace``).  That guard is correct -- publishing a projection stamped earlier
than the data it read would put the generation ahead of its own declared vintage
-- but pairing it with a hand-typed wall-clock literal makes the suite a
scheduled failure.  #4406 minted ``2026-08-03T15:00:00+00:00`` just after the
then-current vintage; the guard stayed quiet while ``known_at`` sat at
2026-08-02T00:14:34Z, then fired the moment the ``govrev`` collection lane
advanced it to 2026-08-07T02:37:59Z (commit ``f5e34a86abb``).  Thirty tests went
red with no code change involved, and re-typing a fresher literal only re-arms
the same bomb for the next collection.

Deriving the run clock from the very documents the fixture root copies keeps the
clock and the data one coherent vintage *by construction*, so no future
collection can re-arm it.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path
import shutil
from typing import Any, Iterator


ROOT = Path(__file__).resolve().parents[1]
CANONICAL_DIRECTORY = Path("data/government_revenue")

#: The materializer's immutable input boundary -- the only documents the suites
#: copy out of the live tree.  The derived clock is computed from exactly these,
#: so the fixture root and the clock can never describe different vintages.
CANONICAL_INPUTS = ("latest.json", "workspace.json", "recipient_entity_graph.json")

#: Floor for the derived clock.  The suites also synthesize hand-authored
#: fixtures whose clocks are fixed (``tests/test_government_revenue_candidates``
#: tops out at 2026-08-02T18:00Z; the API suite pins an observation at
#: 2026-08-02T13:00Z), so the run clock must stay forward of those even if the
#: canonical source were rolled back.  This is #4406's original literal, which
#: means the derivation reproduces that constant exactly on the vintage that
#: shipped it -- the change is a strict generalization, not a re-baseline.
_FLOOR = datetime(2026, 8, 3, 15, 0, tzinfo=timezone.utc)


def canonical_fixture_root(tmp_path: Path) -> Path:
    """Copy only the materializer's immutable input boundary into a temp root."""
    data_dir = tmp_path / CANONICAL_DIRECTORY
    data_dir.mkdir(parents=True)
    for name in CANONICAL_INPUTS:
        shutil.copy2(ROOT / CANONICAL_DIRECTORY / name, data_dir / name)
    return tmp_path


def _known_at_values(node: Any) -> Iterator[str]:
    """Yield every ``*known_at`` string anywhere in a canonical document.

    The writer guards the top-level ``known_at`` of ``latest``/``workspace`` and
    the recipient graph's ``graph_known_at``, but a nested receipt clock that
    outran them would be just as much a source-newer-than-run violation, so the
    walk is exhaustive rather than schema-pinned.
    """
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(value, str) and key.endswith("known_at"):
                yield value
            else:
                yield from _known_at_values(value)
    elif isinstance(node, list):
        for value in node:
            yield from _known_at_values(value)


def _instant(value: str) -> datetime | None:
    """Parse an offset-aware ISO-8601 instant, or ``None`` if it is not one."""
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


@lru_cache(maxsize=1)
def canonical_newest_known_at() -> str | None:
    """Return the newest ``*known_at`` across the copied boundary, or ``None``.

    This is the raw source instant the derived clock is built on top of, and the
    boundary every backward offset has to stay clear of: a synthesized clock at
    or behind it describes a run that read documents it could not yet have seen.
    ``None`` means no parseable ``*known_at`` exists anywhere in the inputs, so
    there is no such boundary to respect.

    Normalized exactly the way the writer normalizes it (``datetime.isoformat``
    on a UTC instant), like every other instant this module hands out.
    """
    newest: datetime | None = None
    for name in CANONICAL_INPUTS:
        document = json.loads(
            (ROOT / CANONICAL_DIRECTORY / name).read_text(encoding="utf-8")
        )
        for raw in _known_at_values(document):
            parsed = _instant(raw)
            if parsed is not None and (newest is None or parsed > newest):
                newest = parsed
    return None if newest is None else newest.isoformat()


@lru_cache(maxsize=1)
def canonical_frozen_at() -> str:
    """Return a run clock coherent with the canonical inputs currently on disk.

    Every ``*known_at`` in the copied boundary must be at or before the frozen
    clock, so the clock is the next whole hour after the newest of them (see
    :func:`canonical_newest_known_at`), never below :data:`_FLOOR`.  Rounding up
    to the hour keeps the value strictly forward of every source clock -- the
    realistic ordering, since a run happens after its inputs are known -- and
    keeps it legible in failure output so the suites' relative offsets stay
    unambiguous: the forward ones (+30m, +1h, +9h) read straight off the hour,
    and the backward ones route through :func:`rewound`, which cannot be read as
    a plain subtraction because the round-up leaves it no guaranteed room.

    The value is normalized exactly the way the writer normalizes it
    (``datetime.isoformat`` on a UTC instant), so tests may compare it verbatim
    against the ``generated_at`` the writer persists.
    """
    raw_newest = canonical_newest_known_at()
    newest = None if raw_newest is None else _instant(raw_newest)
    if newest is None:
        return _FLOOR.isoformat()
    run_at = (newest + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    return max(run_at, _FLOOR).isoformat()


@lru_cache(maxsize=1)
def canonical_candidate_census() -> int:
    """Return how many DISTINCT candidates the canonical inputs currently yield.

    The clock was not the only hand-typed vintage constant in these suites.  The
    *census* was one too: ``== 8`` was written on 2026-08-09, when the eight
    quarantined incident rows were everything the source engine could see, and it
    detonated on 2026-08-12T23:50:04Z when the award-action rail resolved into the
    reviewed graph for the first time and the projection issued fifteen forward
    candidates (ledger 8 -> 23).  Nothing regressed: that unlock is the program's
    success condition, and the nightly published it green
    (``candidate_projection_status`` ``status: ok``).  Re-typing ``== 23`` only
    re-arms the same bomb for candidate twenty-four, exactly as #4406's freshly
    typed clock literal re-armed the one this module was written to end.

    So derive the census the same way the clock is derived -- from a committed
    artifact rather than from a human's memory of a vintage.  The authority is the
    projection's own receipt, which is written by a *previous* run of a *different*
    code path than the rebuild under test, so an assertion against it is a real
    cross-artifact agreement and not a receipt checking itself.

    The receipt is bound before it is believed: ``workspace_bundle_id`` must match
    the committed source bundle (the content-derived identity that ``latest`` and
    ``workspace`` agree on), and the append-only ledger it counts must still hash
    and measure exactly as the receipt recorded.  A source that has moved ahead of
    its receipt therefore fails loudly here, naming that condition, instead of
    surfacing as an unexplained off-by-N somewhere downstream.

    A ledger LINE is not a candidate.  ``observation_id`` (and the candidate's
    ``known_at``) fold the reviewed graph's digest
    (``historical_suppression_entry_key``'s docstring, ``candidates.py:165-171``:
    "``observation_id`` and candidate ``known_at`` both move when the reviewed
    graph is re-published"), while ``candidate_id`` does not -- it is a digest of
    ``candidate_family``/``issuer_company_id``/``event_id`` alone.  A graph
    republish therefore makes the SAME candidate newly "unseen" by observation
    key and appends a second line for it, byte-distinct from the first, without
    minting a new candidate.  Measured on the 2026-08-19 defense19->defense21
    republish: the append-only ledger grew from 62 to 116 lines while the
    DISTINCT ``candidate_id`` count stayed 62 -- the same 62 the pure engine
    (``build_candidate_queue``) still reports fresh against the current graph.
    Counting raw lines conflates "how many candidates exist" with "how many
    times this store has ever observed one," and a census that grows on every
    graph re-review with no new candidate in sight is exactly the scheduled
    failure this function exists to end -- so the census is the distinct-id
    count, never the line count.
    """
    directory = ROOT / CANONICAL_DIRECTORY
    status = json.loads(
        (directory / "candidate_projection_status.json").read_text(encoding="utf-8")
    )
    workspace = json.loads((directory / "workspace.json").read_text(encoding="utf-8"))
    latest = json.loads((directory / "latest.json").read_text(encoding="utf-8"))
    bundle_id = status.get("workspace_bundle_id")
    if bundle_id != workspace.get("bundle_id") or bundle_id != latest.get(
        "procurement_workspace", {}
    ).get("bundle_id"):
        raise AssertionError(
            "the committed candidate projection receipt describes a different "
            f"source bundle than the committed canonical inputs: receipt "
            f"{bundle_id!r}, workspace {workspace.get('bundle_id')!r}, latest "
            f"{latest.get('procurement_workspace', {}).get('bundle_id')!r} -- the "
            "collection lane advanced without a projection, so no census is knowable"
        )
    ledger = (directory / "candidate_ledger.jsonl").read_bytes()
    lines = [line for line in ledger.splitlines() if line.strip()]
    line_count = len(lines)
    if (
        sha256(ledger).hexdigest() != status.get("ledger_sha256")
        or len(ledger) != status.get("ledger_byte_count")
        or line_count != status.get("ledger_line_count")
    ):
        raise AssertionError(
            "the committed append-only candidate ledger does not match the "
            "projection receipt bound to it: the receipt cannot be used as a census"
        )
    candidate_ids = {json.loads(line)["candidate_id"] for line in lines}
    return len(candidate_ids)


def utc_date(instant: str) -> str:
    """Return the UTC calendar date of ``instant`` as ``YYYY-MM-DD``."""
    parsed = _instant(instant)
    if parsed is None:
        raise ValueError(f"not an offset-aware ISO-8601 instant: {instant!r}")
    return parsed.date().isoformat()


def shifted(instant: str, **delta: float) -> str:
    """Return ``instant`` moved by ``delta``, in the writer's normalized form."""
    parsed = _instant(instant)
    if parsed is None:
        raise ValueError(f"not an offset-aware ISO-8601 instant: {instant!r}")
    return (parsed + timedelta(**delta)).isoformat()


def _clamped_rewind(anchor: str, rewind: timedelta, *, floor: str | None) -> str:
    """Return ``anchor`` pulled back by ``rewind``, never at or behind ``floor``.

    A backward offset taken from :func:`canonical_frozen_at` inherits that
    clock's round-up: the anchor is the next whole hour after the newest source
    instant, so the room between the two is whatever the minute hand happened to
    leave -- uniform in (0, 60] minutes, and in principle as thin as a single
    microsecond.  Subtracting a fixed literal from it is this module's header
    bomb one level down.  ``shifted(FROZEN_AT, seconds=-1)`` reads green on every
    vintage whose margin exceeds a second and reds the fleet the night the
    collection lane lands one that does not, with no code change involved; worse,
    it reds it with the wrong message, because the builder's canonical guard
    ("canonical latest known_at is after the frozen generated_at clock") fires
    before the semantics under test ever get a turn.  That guard is right -- a run
    clock at or behind a source it read is exactly the violation
    ``_validate_canonical_latest_workspace`` exists to catch -- so the fix belongs
    in the offset, never in the guard.

    While the margin is healthy the nominal rewind is returned untouched,
    bit-identical to the arithmetic it replaces.  When the margin is too thin to
    absorb it, the result is the midpoint of ``(floor, anchor)``: the point that
    stays maximally clear of BOTH strict boundaries.  It is strictly inside the
    interval whenever that interval spans two microseconds or more, and degrades
    to equality with the floor only when the interval is a single microsecond --
    admissible even then, because every builder ordering guard fires on a strict
    ``>`` (a source *after* the clock), never on equality.  It always stays
    strictly below the anchor, so every "before the run" semantic the callers
    build on survives the clamp.
    """
    parsed = _instant(anchor)
    if parsed is None:
        raise ValueError(f"not an offset-aware ISO-8601 instant: {anchor!r}")
    if rewind <= timedelta(0):
        raise ValueError(f"rewind must be a positive magnitude, not {rewind!r}")
    if floor is None:
        return (parsed - rewind).isoformat()
    boundary = _instant(floor)
    if boundary is None:
        raise ValueError(f"not an offset-aware ISO-8601 instant: {floor!r}")
    if parsed <= boundary:
        raise ValueError(
            f"anchor {anchor!r} is not after the floor {floor!r}: nothing to rewind into"
        )
    nominal = parsed - rewind
    if nominal > boundary:
        return nominal.isoformat()
    return (boundary + (parsed - boundary) / 2).isoformat()


def rewound(instant: str, **delta: float) -> str:
    """Return ``instant`` moved back by ``delta``, clamped strictly inside the vintage.

    ``delta`` is a rewind magnitude, so its components are positive; see
    :func:`_clamped_rewind` for what the clamp defends against.
    """
    return _clamped_rewind(instant, timedelta(**delta), floor=canonical_newest_known_at())


#: The curated issuer scope.  Hand-maintained, and turned into ``latest.json``'s
#: ``companies`` by ``metrics.build_payload`` -- a different code path from the
#: ``candidates.py`` rebuild these suites exercise.
_ENTITIES = "entities.json"

#: The published reviewed recipient graph.  Minted by the recipient-graph review
#: act (``scripts/propose_government_revenue_recipient_graph.py`` plus a human
#: re-mint into the ``:reviewed:`` namespace), never by the candidate engine.
_RECIPIENT_GRAPH = "recipient_entity_graph.json"

#: Namespace prefix every *published* graph id carries.  Seen historically as
#: ``recipient-graph:reviewed-empty:<date>`` and
#: ``recipient-graph:reviewed:<date>:<slug>``, so the prefix is the stable part.
#: The trailing slug is NOT parsed for a count: it has already been ``pltr-v1``
#: and ``defense19-v1``, so reading a census out of it would only trade a
#: hand-typed number for a hand-typed naming convention.
_REVIEWED_GRAPH_ID_PREFIX = "recipient-graph:reviewed"


def _canonical_document(name: str) -> Any:
    """Read one committed document out of the canonical directory."""
    return json.loads((ROOT / CANONICAL_DIRECTORY / name).read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def canonical_requested_issuer_tickers() -> tuple[str, ...]:
    """Return the curated issuer scope the mapping backlog is a census of.

    ``build_mapping_backlog`` emits one row per company on the payload, so
    ``len(mapping_backlog)`` -- and the ``counts["mapping_needed"]`` that mirrors
    it -- measure the REQUESTED issuer set and nothing the recipient graph did.
    ``== 21`` was that census transcribed by hand on the vintage the test was
    written, and it moves the day an issuer is added to or retired from
    coverage: the same scheduled failure as ``== 8`` for the candidate store and
    ``2026-08-03T15:00:00+00:00`` for the run clock.

    The scope is curated in ``entities.json`` and read into the payload by
    ``metrics.build_payload``, a different code path from the ``candidates.py``
    rebuild under test, so counting it there is a real cross-artifact agreement
    rather than the suite measuring its own input.

    The scope is bound before it is believed: the curated roster and the built
    payload must name the same issuers.  An issuer curated into scope without
    the payload being rebuilt would otherwise surface as an unexplained
    off-by-one in a coverage count somewhere downstream; here it fails naming
    exactly that condition.
    """
    entities = _canonical_document(_ENTITIES).get("entities")
    if not isinstance(entities, dict) or not entities:
        raise AssertionError(
            f"the curated issuer scope {_ENTITIES!r} carries no non-empty "
            "`entities` mapping, so the requested issuer census is not knowable"
        )
    requested = tuple(sorted(entities))
    payload_companies = _canonical_document("latest.json").get("companies")
    payload_tickers = tuple(sorted(
        company.get("ticker")
        for company in (payload_companies if isinstance(payload_companies, list) else [])
        if isinstance(company, dict) and company.get("ticker")
    ))
    if payload_tickers != requested:
        raise AssertionError(
            "the curated issuer scope and the built payload describe different "
            f"issuer sets: {_ENTITIES} has {len(requested)} "
            f"({', '.join(requested)}), latest.json has {len(payload_tickers)} "
            f"({', '.join(payload_tickers)}) -- curated only "
            f"{sorted(set(requested) - set(payload_tickers))}, payload only "
            f"{sorted(set(payload_tickers) - set(requested))}.  The payload was "
            "not rebuilt after the scope moved, so no requested census is knowable"
        )
    return requested


@lru_cache(maxsize=1)
def canonical_reviewed_issuer_tickers() -> tuple[str, ...]:
    """Return the reviewed issuer roster the published recipient graph declares.

    ``coverage["reviewed_issuer_company_count"]`` and
    ``coverage["reviewed_issuer_tickers"]`` are a census of the reviewed graph,
    so they move on every graph republish -- ``19`` and its nineteen
    hand-listed tickers described exactly one vintage,
    ``recipient-graph:reviewed:2026-08-08:defense19-v1``, and re-typing ``20``
    for ``defense20-v1`` would only re-arm them for the graph after that.

    The roster is taken from the graph's own ``companies`` declaration.  That is
    deliberately NOT the predicate the engine evaluates: the engine reaches a
    ticker by resolving each exact identifier through the ownership chain
    (``_reviewed_exact_graph_tickers`` -> ``entity_resolution.resolve_recipient``),
    a multi-hop walk that a test-side re-implementation would get subtly wrong.
    Comparing the engine's resolved set against the roster the graph publishes is
    therefore a genuine agreement between two readings of the artifact -- a graph
    that declares an issuer reviewed but ships no reachable exact path for it
    fails, which is precisely the state BWXT was in before its exact edges were
    reviewed.

    The graph is bound before it is believed:

    * its id must sit in the published ``:reviewed:`` namespace, so a candidate
      proposal that was never re-minted cannot be read as a reviewed roster;
    * it must be ADMISSIBLE at the payload's own analysis clock.  A graph the
      loader rejects makes ``_reviewed_exact_graph_tickers`` return the empty
      set, so every coverage count silently collapses to zero -- an off-by-N
      with no stated cause.  Here the rejection is named, with its error codes;
    * every declared issuer must be wired by at least one ownership edge, since
      an issuer with no edge at all can never be reached however the resolution
      walk goes.
    """
    graph = _canonical_document(_RECIPIENT_GRAPH)
    graph_id = graph.get("graph_id")
    if not isinstance(graph_id, str) or not graph_id.startswith(
        _REVIEWED_GRAPH_ID_PREFIX
    ):
        raise AssertionError(
            f"the committed recipient graph is not a published reviewed graph: "
            f"graph_id {graph_id!r} does not start with "
            f"{_REVIEWED_GRAPH_ID_PREFIX!r}, so its companies are not a reviewed roster"
        )

    # Imported here rather than at module scope so this file stays importable as
    # the stdlib-only input boundary its header describes.
    from engine.government_revenue.entity_resolution import load_recipient_entity_graph

    analysis_as_of = _canonical_document("latest.json").get("as_of")
    loaded = load_recipient_entity_graph(graph, as_of=analysis_as_of)
    if loaded.get("status") != "ready":
        raise AssertionError(
            f"the committed recipient graph {graph_id!r} is not admissible at the "
            f"payload's analysis clock {analysis_as_of!r}: load status "
            f"{loaded.get('status')!r}, error codes {loaded.get('error_codes')!r}.  "
            "Every reviewed-coverage count collapses to zero in that state, so no "
            "reviewed census is knowable"
        )

    companies = graph.get("companies")
    if not isinstance(companies, list):
        raise AssertionError(
            f"the committed recipient graph {graph_id!r} carries no `companies` list"
        )
    roster = tuple(sorted(
        company.get("ticker")
        for company in companies
        if isinstance(company, dict)
        and company.get("verification_state") == "reviewed"
        and company.get("ticker")
    ))
    if not roster:
        raise AssertionError(
            f"the committed recipient graph {graph_id!r} declares no reviewed "
            "issuer, so there is no reviewed roster to derive coverage from"
        )
    if len(set(roster)) != len(roster):
        duplicated = sorted({t for t in roster if roster.count(t) > 1})
        raise AssertionError(
            f"the committed recipient graph {graph_id!r} declares the same issuer "
            f"more than once ({duplicated}); a reviewed roster must be a set"
        )

    edges = graph.get("ownership_edges")
    wired = {
        edge.get("parent_company_id")
        for edge in (edges if isinstance(edges, list) else [])
        if isinstance(edge, dict)
    }
    unwired = sorted(
        company.get("ticker")
        for company in companies
        if isinstance(company, dict)
        and company.get("verification_state") == "reviewed"
        and company.get("ticker")
        and company.get("company_id") not in wired
    )
    if unwired:
        raise AssertionError(
            f"the committed recipient graph {graph_id!r} declares {unwired} "
            "reviewed but connects no ownership edge to them, so no exact "
            "identifier path can ever reach them; the declared roster overstates "
            "what the graph can resolve"
        )
    return roster


def canonical_unreviewed_issuer_tickers() -> tuple[str, ...]:
    """Return the requested issuers the reviewed graph carries no mapping for.

    These are the ``mapping_needed`` rows -- ``["BWXT", "GE"]`` on
    ``defense19-v1`` -- derived as a set difference rather than hand-listed, so
    an issuer that gains (or loses) reviewed exact edges moves between the two
    coverage states without a test edit.
    """
    reviewed = set(canonical_reviewed_issuer_tickers())
    return tuple(
        ticker
        for ticker in canonical_requested_issuer_tickers()
        if ticker not in reviewed
    )


def canonical_mapping_backlog_states() -> dict[str, int]:
    """Return the backlog's ``mapping_state`` partition of the requested scope.

    Shaped to compare directly against a ``Counter`` over the live backlog: a
    state with no rows is absent rather than zero, because that is what a
    ``Counter`` built from a generator yields.
    """
    reviewed = set(canonical_reviewed_issuer_tickers())
    requested = canonical_requested_issuer_tickers()
    partial = sum(1 for ticker in requested if ticker in reviewed)
    return {
        state: count
        for state, count in (
            ("partial_identifier_coverage", partial),
            ("mapping_needed", len(requested) - partial),
        )
        if count
    }
