"""engine/prophet_lab/boards.py — the six Lab boards, as pure projections.

LAB-0 §1 architecture law, restated as a design constraint on this module:
every function here reads already-loaded data (events, episodes, a Prophet
index, an enrichment library, an observation baseline) and FILTERS / JOINS /
DECORATES it into the frozen board shapes.  Nothing here computes a detector
formula, reads a forward outcome, or mutates a store.  ``DNR:KILL-WASHOUT-TURN``
and ``DNR:KILL-PROPHET-POP-MERGE`` bind directly on :func:`build_intersection_board`
and :func:`build_all_early_board`: the intersection board mints zero
events/episodes/scores (it is SET ARITHMETIC on already-minted events) and
neither board ever touches ``us_standouts.json`` or the graded board
population.

Row shape, uniform across all six boards
-----------------------------------------
Two kinds of row:

* **Single-family boards** (``lab-g0-v1``, ``lab-c1-v1``, ``lab-c2a-v1``,
  ``lab-c2-variants-v1``) — one row per qualifying EVENT.  The row carries a
  real ``detector_id``/``event_id``/``subtype`` (the LAB-0 §3 text names a
  concrete detector for each of these boards) and an ``experts`` list holding
  exactly that one identity, for schema uniformity with the multi-family
  boards.
* **Multi-family boards** (``lab-g0-c2a-v1``, ``lab-all-early-v1``) — one row
  per TICKER, ``detector_id=None`` at the row level (LAB-0 §3: "view
  detector_id = null" for the intersection board; the union board's "one
  ticker card may carry multiple experts[]" implies the same shape), and
  ``experts`` holding every qualifying event for that ticker across the
  boards being combined.

Every row also carries a row-level ``observation_class``/``evidence_eligible``,
computed as "ANY constituent expert is live_forward -> the row is
live_forward" — a disclosed aggregation rule for the (underspecified)
multi-expert case. Review B3: each entry inside ``experts[]`` still carries
its OWN per-event ``observation_class`` so no information is lost to the
aggregate, and a card whose experts disagree sets ``observation_class_mixed``
so a consumer can see the promoted flag is covering ineligible seed evidence
too (see ``research/prophet_v4/P_LAB_API_NOTES.md``).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from engine.prophet_lab import observation as obs
from engine.prophet_lab.contracts import (
    BOARD_ALL_EARLY,
    BOARD_C1,
    BOARD_C2A,
    BOARD_C2_VARIANTS,
    BOARD_G0,
    BOARD_G0_C2A_INTERSECTION,
    C1_DETECTOR_ID,
    C2_DETECTOR_ID,
    C2_SUBTYPES,
    C2A_SUBTYPE,
    G0_DETECTOR_ID,
    OBSERVATION_LIVE_FORWARD,
    OBSERVATION_RETROSPECTIVE_SEED,
)
from engine.prophet_lab.timeparse import parse_instant

# ---------------------------------------------------------------------------
# N1: one normalized sort clock. Raw ISO-8601 string compares are fragile
# (missing 'Z', an offset instead of 'Z', a bare date vs a full timestamp) —
# every sort in this module goes through this one parser instead. An empty or
# unparseable ``sort_ts`` sorts LAST (oldest / least informative) rather than
# raising or silently mis-ordering; ``sort_basis`` on the row still discloses
# which raw field the timestamp came from.
# ---------------------------------------------------------------------------
_UNKNOWN_SORT_FLOOR = datetime.min.replace(tzinfo=timezone.utc)


def _parse_sort_ts(ts: str | None) -> tuple[int, datetime]:
    if not ts:
        return (0, _UNKNOWN_SORT_FLOOR)
    normalized = ts[:-1] + "+00:00" if ts.endswith("Z") else ts
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return (0, _UNKNOWN_SORT_FLOOR)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return (1, parsed)


def _sort_rows_newest_first(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows.sort(key=lambda row: (_parse_sort_ts(row["sort_ts"]), row["ticker"]), reverse=True)
    return rows


def _sort_experts_newest_first(experts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    experts.sort(key=lambda e: _parse_sort_ts(e["sort_ts"]), reverse=True)
    return experts


# ---------------------------------------------------------------------------
# expert / row construction
# ---------------------------------------------------------------------------
def _sort_ts_and_basis(event: Mapping[str, Any]) -> tuple[str, str]:
    """``(sort_ts, basis)`` — prefer the emitter's ``signal_known_ts``.

    ``signal_known_ts`` is null unless the emitter actually supplied it
    (LAB-0 §4: never reconstructed), so a row without one sorts on
    ``signal_ts`` and says so — the explicit basis field the frozen contract
    (§5) requires alongside ``sort_ts``.
    """
    known = event.get("signal_known_ts")
    if known:
        return str(known), "signal_known_ts"
    return str(event.get("signal_ts") or ""), "signal_ts"


def _build_expert(
    event: Mapping[str, Any],
    *,
    first_observed_at: Mapping[str, str],
    baseline: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """One ``experts[]`` entry — exact identity, plus this event's own class."""
    event_id = str(event.get("event_id") or "")
    sort_ts, basis = _sort_ts_and_basis(event)
    observation_class = obs.classify_observation(
        event_id, first_observed_at=first_observed_at, baseline=baseline,
    )
    return {
        "detector_id": event.get("detector_id"),
        "event_id": event_id or None,
        "subtype": event.get("subtype"),
        "family": event.get("family"),
        "producer": event.get("producer"),
        "ticker": event.get("ticker"),
        "signal_ts": event.get("signal_ts"),
        "signal_known_ts": event.get("signal_known_ts"),
        "sort_ts": sort_ts,
        "sort_basis": basis,
        "bar_state": event.get("bar_state"),
        "final": event.get("final"),
        "quality": event.get("quality"),
        "observation_class": observation_class,
        "evidence_eligible": obs.evidence_eligible(observation_class),
        "first_observed_at": first_observed_at.get(event_id),
    }


def _row_observation_class_and_mixed(
    experts: Sequence[Mapping[str, Any]],
) -> tuple[str, bool]:
    """Row aggregate (review B3): any live_forward expert promotes the card.

    ``mixed`` is True when the card's experts do NOT all agree — the signal a
    consumer needs to know the promoted ``live_forward``/``evidence_eligible``
    flags are covering at least one expert that is individually a seed.
    """
    classes = {str(e.get("observation_class")) for e in experts}
    mixed = len(classes) > 1
    if OBSERVATION_LIVE_FORWARD in classes:
        return OBSERVATION_LIVE_FORWARD, mixed
    if experts:
        return str(experts[0]["observation_class"]), mixed
    return OBSERVATION_RETROSPECTIVE_SEED, mixed


def _live_forward_lead_anchor(
    experts: Sequence[Mapping[str, Any]],
) -> tuple[str | None, str | None]:
    """``(first_observed_at, event_id)`` of the EARLIEST live_forward expert.

    Review B3: this is the event a multi-expert card's measured lead is
    ATTRIBUTED to (``measured_from_event_id``) — never left implicit when a
    card mixes a seed and a live observation.

    Temporal review round 2 (S1): "earliest" is decided by parsed INSTANT
    (:func:`engine.prophet_lab.timeparse.parse_instant`), never by comparing
    the ``first_observed_at`` strings directly. Measured failure this
    replaces: expert A ``"2026-08-19T20:00:00-05:00"`` (= 2026-08-20T01:00Z)
    vs expert B ``"2026-08-20T00:30:00Z"`` — A sorts first as a raw string
    ('19' < '20'), but B is the TRUE earlier instant (00:30Z < 01:00Z),
    fabricating a lead anchored to the wrong event. Every candidate here is
    an ``extract_events`` output and is therefore guaranteed parseable in
    practice, but an entry that somehow fails to parse is defensively
    EXCLUDED (never allowed to win "earliest" by falling back to a string
    compare) rather than crashing this projection.

    This is EVIDENCE-tier parsing, not the DISPLAY-tier exemption
    ``timeparse.py``'s module docstring describes for ``_parse_sort_ts`` —
    the two are not the same call and this one does not join that exemption.
    """
    candidates: list[tuple[datetime, str, str | None]] = []
    for e in experts:
        if e.get("observation_class") != OBSERVATION_LIVE_FORWARD:
            continue
        raw = e.get("first_observed_at")
        if not raw:
            continue
        instant = parse_instant(raw)
        if instant is None:
            continue  # defensive: never let an unparseable entry win "earliest"
        candidates.append((instant, raw, e.get("event_id")))
    if not candidates:
        return None, None
    candidates.sort(key=lambda triple: triple[0])
    _, earliest_raw, earliest_event_id = candidates[0]
    return earliest_raw, earliest_event_id


def _current_and_prior_plans(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[Mapping[str, Any] | None, Mapping[str, Any] | None]:
    """Review B1: split a ticker's plan rows into (current, most-recent-closed).

    ``rows`` is already sorted most-recent-first (``sources.index_plans_by_ticker``).
    "Current" is the newest NON-CLOSED plan — a closed plan is never reported
    as membership, however recently it closed. "Prior" is the newest CLOSED
    plan, surfaced separately and clearly labeled, never blended with a
    measured lead.
    """
    current = next((r for r in rows if not r.get("closed")), None)
    prior = next((r for r in rows if r.get("closed")), None)
    return current, prior


def _prophet_comparison(
    ticker: str,
    *,
    plans_by_ticker: Mapping[str, Sequence[Mapping[str, Any]]],
    lab_first_observed_at: str | None,
    lead_anchor_event_id: str | None,
    row_observation_class: str,
) -> dict[str, Any]:
    """The Prophet-side comparison block — ticker-level, CURRENT plan only.

    Review B1: membership/lifecycle/stance derive ONLY from a non-closed
    plan. A ticker whose only plans are closed reports ``membership: False``
    and carries the most recent closed plan under ``prior_plan`` instead —
    clearly labeled, and NEVER carrying a measured lead (a closed plan is
    history, not something the Lab can claim to have "led").
    """
    rows = plans_by_ticker.get(ticker) or ()
    current, prior = _current_and_prior_plans(rows)
    prior_plan = None
    if prior is not None:
        prior_plan = {
            "closed": True,
            "lifecycle": prior.get("phase"),
            "stance": prior.get("direction"),
            "first_recorded_at": prior.get("recorded_at"),
            "signal_anchor": prior.get("signal_date"),
            "entry_date": prior.get("entry_date"),
        }
    if current is None:
        return {
            "membership": False,
            "lifecycle": None,
            "stance": None,
            "first_recorded_at": None,
            "signal_anchor": None,
            "entry_date": None,
            "measured_lab_to_prophet_lead_days": None,
            "measured_from_event_id": None,
            "prior_plan": prior_plan,
        }
    signal_anchor = current.get("signal_date")
    entry_date = current.get("entry_date")
    anchor_for_lead = entry_date or signal_anchor
    lead = obs.measured_lead_days(
        row_observation_class,
        first_observed_at=lab_first_observed_at,
        prophet_anchor_at=anchor_for_lead,
    )
    return {
        "membership": True,
        "lifecycle": current.get("phase"),
        "stance": current.get("direction"),
        # LAB-0 §5 asks for "first recorded/published" as one fact; the
        # current `prophet.index/v1` plan row carries a single origination
        # timestamp (`recorded_at`) and no separate publish-history field, so
        # both concepts resolve to that one value here (disclosed choice —
        # see research/prophet_v4/P_LAB_API_NOTES.md).
        "first_recorded_at": current.get("recorded_at"),
        "signal_anchor": signal_anchor,
        "entry_date": entry_date,
        "measured_lab_to_prophet_lead_days": lead,
        "measured_from_event_id": lead_anchor_event_id if lead is not None else None,
        "prior_plan": prior_plan,
    }


def _enrich(ticker: str, *, library: Any, plans_by_ticker: Mapping[str, Sequence[Mapping[str, Any]]],
            sparks: dict[str, str] | None) -> dict[str, Any]:
    """name/sector/spark — the existing Prophet board-read source, reused.

    Tries the injected ``LibraryIndex`` first (the same source
    ``scripts/build_prophet.py`` uses); when it is unavailable AND the ticker
    already carries a published ``board_read`` block on a NON-CLOSED Prophet
    plan row (review N5: every such row is consulted, not just the first one
    encountered), falls back to that for name/sector only. When neither is
    reachable the fields ship ``None`` with the health note this module's
    caller attaches — never a fabricated name/sector, per LAB-0 §1.

    Review S6: the returned ``spark`` is either a fully resolved SVG body or
    ``None`` — never a bare reference (``board_read_sparks.json#TICKER``)
    into an artifact this API does not itself serve, which would dangle for
    any caller that only has this response. The primary (``LibraryIndex``)
    path resolves the real body via the ``sparks`` accumulator
    ``build_board_read`` already populates as a side effect; the published
    ``board_read`` fallback path only ever holds the SAME kind of reference
    (from a prior build), which this function cannot itself resolve without
    reading a second site artifact — so that path ships ``spark: None``
    rather than propagate a reference it cannot back.
    """
    from engine.prophet_board_read import build_board_read  # noqa: PLC0415

    # NOTE: build_board_read keys the plan by "asset" (the ticker field name
    # on a Prophet plan row), not "ticker" — see engine/prophet_board_read.py.
    plan_stub = {"asset": ticker, "closed": False}
    spark_accumulator: dict[str, str] = {}
    block = build_board_read(plan_stub, library=library, sparks=spark_accumulator)
    fields = block.get("fields") or {}
    name_field = fields.get("name") or {}
    sector_field = fields.get("sector") or {}
    spark_field = fields.get("spark") or {}

    name = name_field.get("value") if name_field.get("state") == "available" else None
    sector = sector_field.get("value") if sector_field.get("state") == "available" else None
    # Resolved body, not the "board_read_sparks.json#TICKER" reference the
    # field itself carries — see the docstring's S6 note.
    spark = spark_accumulator.get(ticker) if spark_field.get("state") == "available" else None
    if sparks is not None and spark is not None:
        sparks[ticker] = spark

    if name is None and sector is None:
        # Library unreachable/miss — fall back to EVERY non-closed Prophet
        # plan row for this ticker (review N5: not just the first one), and
        # take the first AVAILABLE value found for each field independently.
        rows = [r for r in (plans_by_ticker.get(ticker) or ()) if not r.get("closed")]
        for row in rows:
            published = row.get("board_read")
            if not isinstance(published, Mapping):
                continue
            published_fields = published.get("fields") or {}
            pname = published_fields.get("name") or {}
            psector = published_fields.get("sector") or {}
            if name is None and pname.get("state") == "available":
                name = pname.get("value")
            if sector is None and psector.get("state") == "available":
                sector = psector.get("value")
            if name is not None and sector is not None:
                break

    return {"name": name, "sector": sector, "spark": spark}


# ---------------------------------------------------------------------------
# single-family boards
# ---------------------------------------------------------------------------
def _events_for_detector(
    events: Sequence[Mapping[str, Any]],
    *,
    detector_id: str,
    subtypes: Sequence[str] | None = None,
) -> list[Mapping[str, Any]]:
    out = []
    for event in events:
        if str(event.get("detector_id") or "") != detector_id:
            continue
        if subtypes is not None and str(event.get("subtype") or "") not in subtypes:
            continue
        out.append(event)
    return out


def _nonterminal_c1_tickers(episodes: Sequence[Any]) -> set[str]:
    """Tickers holding a CURRENT NONTERMINAL C1 episode (LAB-0 §3)."""
    out: set[str] = set()
    for episode in episodes:
        if getattr(episode, "detector_id", None) != C1_DETECTOR_ID:
            continue
        if getattr(episode, "terminal", True):
            continue
        out.add(str(getattr(episode, "ticker", "")))
    return out


def _build_single_family_rows(
    events: Sequence[Mapping[str, Any]],
    *,
    board_id: str,
    first_observed_at: Mapping[str, str],
    baseline: Mapping[str, Any] | None,
    plans_by_ticker: Mapping[str, Sequence[Mapping[str, Any]]],
    library: Any,
    sparks: dict[str, str] | None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for event in events:
        ticker = str(event.get("ticker") or "")
        if not ticker:
            continue
        expert = _build_expert(event, first_observed_at=first_observed_at, baseline=baseline)
        row_class = expert["observation_class"]
        lead_anchor_event_id = expert["event_id"] if row_class == OBSERVATION_LIVE_FORWARD else None
        enrichment = _enrich(
            ticker, library=library, plans_by_ticker=plans_by_ticker, sparks=sparks,
        )
        comparison = _prophet_comparison(
            ticker,
            plans_by_ticker=plans_by_ticker,
            lab_first_observed_at=expert["first_observed_at"],
            lead_anchor_event_id=lead_anchor_event_id,
            row_observation_class=row_class,
        )
        rows.append({
            "board_id": board_id,
            "ticker": ticker,
            "name": enrichment["name"],
            "sector": enrichment["sector"],
            "spark": enrichment["spark"],
            "detector_id": event.get("detector_id"),
            "event_id": expert["event_id"],
            "subtype": event.get("subtype"),
            "sort_ts": expert["sort_ts"],
            "sort_basis": expert["sort_basis"],
            "observation_class": row_class,
            "observation_class_mixed": False,  # single-expert row: never mixed
            "evidence_eligible": row_class == OBSERVATION_LIVE_FORWARD,
            "experts": [expert],
            "prophet_comparison": comparison,
        })
    return _sort_rows_newest_first(rows)


def build_g0_board(events: Sequence[Mapping[str, Any]], **kw: Any) -> list[dict[str, Any]]:
    matched = _events_for_detector(events, detector_id=G0_DETECTOR_ID)
    return _build_single_family_rows(matched, board_id=BOARD_G0, **kw)


def build_c1_board(
    events: Sequence[Mapping[str, Any]], *, episodes: Sequence[Any], **kw: Any,
) -> list[dict[str, Any]]:
    nonterminal_tickers = _nonterminal_c1_tickers(episodes)
    matched = [
        e for e in _events_for_detector(events, detector_id=C1_DETECTOR_ID)
        if str(e.get("ticker") or "") in nonterminal_tickers
    ]
    return _build_single_family_rows(matched, board_id=BOARD_C1, **kw)


def build_c2a_board(events: Sequence[Mapping[str, Any]], **kw: Any) -> list[dict[str, Any]]:
    matched = _events_for_detector(events, detector_id=C2_DETECTOR_ID, subtypes=(C2A_SUBTYPE,))
    return _build_single_family_rows(matched, board_id=BOARD_C2A, **kw)


def build_c2_variants_board(events: Sequence[Mapping[str, Any]], **kw: Any) -> list[dict[str, Any]]:
    matched = _events_for_detector(events, detector_id=C2_DETECTOR_ID, subtypes=C2_SUBTYPES)
    return _build_single_family_rows(matched, board_id=BOARD_C2_VARIANTS, **kw)


# ---------------------------------------------------------------------------
# multi-family boards — display set arithmetic only, mints nothing
# ---------------------------------------------------------------------------
def _ticker_card(
    ticker: str,
    matching_events: Sequence[Mapping[str, Any]],
    *,
    board_id: str,
    first_observed_at: Mapping[str, str],
    baseline: Mapping[str, Any] | None,
    plans_by_ticker: Mapping[str, Sequence[Mapping[str, Any]]],
    library: Any,
    sparks: dict[str, str] | None,
) -> dict[str, Any]:
    experts = [
        _build_expert(e, first_observed_at=first_observed_at, baseline=baseline)
        for e in matching_events
    ]
    _sort_experts_newest_first(experts)
    row_class, mixed = _row_observation_class_and_mixed(experts)
    lead_anchor_observed_at, lead_anchor_event_id = _live_forward_lead_anchor(experts)
    enrichment = _enrich(ticker, library=library, plans_by_ticker=plans_by_ticker, sparks=sparks)
    comparison = _prophet_comparison(
        ticker,
        plans_by_ticker=plans_by_ticker,
        lab_first_observed_at=lead_anchor_observed_at,
        lead_anchor_event_id=lead_anchor_event_id,
        row_observation_class=row_class,
    )
    return {
        "board_id": board_id,
        "ticker": ticker,
        "name": enrichment["name"],
        "sector": enrichment["sector"],
        "spark": enrichment["spark"],
        # Multi-family card: no single detector describes the row (LAB-0 §3
        # "view detector_id = null"); identity lives entirely in experts[].
        "detector_id": None,
        "event_id": None,
        "subtype": None,
        "sort_ts": experts[0]["sort_ts"] if experts else "",
        "sort_basis": experts[0]["sort_basis"] if experts else "signal_ts",
        "observation_class": row_class,
        "observation_class_mixed": mixed,
        # Review B3: derived from the SAME promoted row_class, not an
        # independent any(...) over the experts — identical arithmetic
        # result, but a single source of truth, and `observation_class_mixed`
        # is what tells a consumer this promoted flag may be covering
        # individually-ineligible (seed) experts.
        "evidence_eligible": row_class == OBSERVATION_LIVE_FORWARD,
        "experts": experts,
        "prophet_comparison": comparison,
    }


def build_intersection_board(
    events: Sequence[Mapping[str, Any]], **kw: Any,
) -> list[dict[str, Any]]:
    """``lab-g0-c2a-v1`` — display SET INTERSECTION only (``DNR:KILL-WASHOUT-TURN``).

    Mints zero events/episodes/scores: this function returns cards built
    purely from already-minted G0 and C2a events, filtered to tickers present
    in BOTH sets.  No new construction, no washout×turn detector.
    """
    g0_events = _events_for_detector(events, detector_id=G0_DETECTOR_ID)
    c2a_events = _events_for_detector(events, detector_id=C2_DETECTOR_ID, subtypes=(C2A_SUBTYPE,))
    g0_tickers = {str(e.get("ticker") or "") for e in g0_events}
    c2a_tickers = {str(e.get("ticker") or "") for e in c2a_events}
    shared = (g0_tickers & c2a_tickers) - {""}
    by_ticker: dict[str, list[Mapping[str, Any]]] = {t: [] for t in shared}
    for e in g0_events + c2a_events:
        ticker = str(e.get("ticker") or "")
        if ticker in by_ticker:
            by_ticker[ticker].append(e)
    rows = [
        _ticker_card(ticker, matching, board_id=BOARD_G0_C2A_INTERSECTION, **kw)
        for ticker, matching in by_ticker.items()
    ]
    return _sort_rows_newest_first(rows)


def build_all_early_board(
    events: Sequence[Mapping[str, Any]], *, episodes: Sequence[Any], **kw: Any,
) -> list[dict[str, Any]]:
    """``lab-all-early-v1`` — union G0 + C1(nonterminal) + C2a-f. EXCLUDES C3/C5.

    One ticker card may carry multiple ``experts[]`` (``DEC:LER-EXPERT-EVENT-FAMILIES-PRESERVED``:
    expert identities are never flattened).  C3/C5 events are never read into
    the matching set at all, so they cannot appear here regardless of what
    else is in the pool.

    Review S5: when the episode ledger itself is unavailable, ``episodes`` is
    simply ``[]`` and the C1 contribution here is empty — same shape as
    "genuinely no nonterminal C1 episodes today". Disclosing WHICH of those
    two happened is deliberately NOT this function's job: it stays a pure
    projection over whatever it is handed, and the caller (``response.py``)
    surfaces the distinction alongside this board's rows via
    ``board_availability["lab-all-early-v1"]["components"]["c1"]``, so a
    ticker whose only qualifying signal was a nonterminal C1 episode does not
    silently vanish from the union with no explanation anywhere in the
    response.
    """
    nonterminal_tickers = _nonterminal_c1_tickers(episodes)
    g0_events = _events_for_detector(events, detector_id=G0_DETECTOR_ID)
    c1_events = [
        e for e in _events_for_detector(events, detector_id=C1_DETECTOR_ID)
        if str(e.get("ticker") or "") in nonterminal_tickers
    ]
    c2_events = _events_for_detector(events, detector_id=C2_DETECTOR_ID, subtypes=C2_SUBTYPES)
    pool = g0_events + c1_events + c2_events
    by_ticker: dict[str, list[Mapping[str, Any]]] = {}
    for e in pool:
        ticker = str(e.get("ticker") or "")
        if not ticker:
            continue
        by_ticker.setdefault(ticker, []).append(e)
    rows = [
        _ticker_card(ticker, matching, board_id=BOARD_ALL_EARLY, **kw)
        for ticker, matching in by_ticker.items()
    ]
    return _sort_rows_newest_first(rows)


__all__ = [
    "build_g0_board",
    "build_c1_board",
    "build_c2a_board",
    "build_c2_variants_board",
    "build_intersection_board",
    "build_all_early_board",
]
