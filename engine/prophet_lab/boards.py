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
multi-expert case; each entry inside ``experts[]`` still carries its OWN
per-event ``observation_class`` so no information is lost to the aggregate
(see ``research/prophet_v4/P_LAB_API_NOTES.md``).
"""
from __future__ import annotations

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
)


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


def _row_observation_class(experts: Sequence[Mapping[str, Any]]) -> str:
    """Row aggregate: any live_forward expert promotes the whole card."""
    if any(e.get("observation_class") == OBSERVATION_LIVE_FORWARD for e in experts):
        return OBSERVATION_LIVE_FORWARD
    return experts[0]["observation_class"] if experts else "retrospective_seed"


def _earliest_live_forward_observed_at(experts: Sequence[Mapping[str, Any]]) -> str | None:
    candidates = [
        e["first_observed_at"]
        for e in experts
        if e.get("observation_class") == OBSERVATION_LIVE_FORWARD and e.get("first_observed_at")
    ]
    return min(candidates) if candidates else None


def _prophet_comparison(
    ticker: str,
    *,
    plans_by_ticker: Mapping[str, Sequence[Mapping[str, Any]]],
    lab_first_observed_at: str | None,
    row_observation_class: str,
) -> dict[str, Any]:
    """The Prophet-side comparison block — ticker-level, most-recent plan wins."""
    rows = plans_by_ticker.get(ticker) or ()
    plan = rows[0] if rows else None
    if plan is None:
        return {
            "membership": False,
            "lifecycle": None,
            "stance": None,
            "first_recorded_at": None,
            "signal_anchor": None,
            "entry_date": None,
            "measured_lab_to_prophet_lead_days": None,
        }
    signal_anchor = plan.get("signal_date")
    entry_date = plan.get("entry_date")
    anchor_for_lead = entry_date or signal_anchor
    lead = obs.measured_lead_days(
        row_observation_class,
        first_observed_at=lab_first_observed_at,
        prophet_anchor_at=anchor_for_lead,
    )
    return {
        "membership": True,
        "lifecycle": plan.get("phase"),
        "stance": plan.get("direction"),
        # LAB-0 §5 asks for "first recorded/published" as one fact; the
        # current `prophet.index/v1` plan row carries a single origination
        # timestamp (`recorded_at`) and no separate publish-history field, so
        # both concepts resolve to that one value here (disclosed choice —
        # see research/prophet_v4/P_LAB_API_NOTES.md).
        "first_recorded_at": plan.get("recorded_at"),
        "signal_anchor": signal_anchor,
        "entry_date": entry_date,
        "measured_lab_to_prophet_lead_days": lead,
    }


def _enrich(ticker: str, *, library: Any, plans_by_ticker: Mapping[str, Sequence[Mapping[str, Any]]],
            sparks: dict[str, str] | None) -> dict[str, Any]:
    """name/sector/spark — the existing Prophet board-read source, reused.

    Tries the injected ``LibraryIndex`` first (the same source
    ``scripts/build_prophet.py`` uses); when it is unavailable AND the ticker
    already carries a published ``board_read`` block on its Prophet plan row
    (index.json), falls back to that.  When neither is reachable the fields
    ship ``None`` with the health note this module's caller attaches — never
    a fabricated name/sector, per LAB-0 §1.
    """
    from engine.prophet_board_read import build_board_read  # noqa: PLC0415

    # NOTE: build_board_read keys the plan by "asset" (the ticker field name
    # on a Prophet plan row), not "ticker" — see engine/prophet_board_read.py.
    plan_stub = {"asset": ticker, "closed": False}
    block = build_board_read(plan_stub, library=library, sparks=sparks)
    fields = block.get("fields") or {}
    name_field = fields.get("name") or {}
    sector_field = fields.get("sector") or {}
    spark_field = fields.get("spark") or {}

    name = name_field.get("value") if name_field.get("state") == "available" else None
    sector = sector_field.get("value") if sector_field.get("state") == "available" else None
    spark = spark_field.get("value") if spark_field.get("state") == "available" else None

    if name is None and sector is None and spark is None:
        # Library unreachable/miss — fall back to the ticker's own published
        # Prophet plan row, which already carries a board_read block once
        # build_prophet.py has run (same source, published copy).
        rows = plans_by_ticker.get(ticker) or ()
        for row in rows:
            published = row.get("board_read")
            if not isinstance(published, Mapping):
                continue
            published_fields = published.get("fields") or {}
            pname = (published_fields.get("name") or {})
            psector = (published_fields.get("sector") or {})
            pspark = (published_fields.get("spark") or {})
            if name is None and pname.get("state") == "available":
                name = pname.get("value")
            if sector is None and psector.get("state") == "available":
                sector = psector.get("value")
            if spark is None and pspark.get("state") == "available":
                spark = pspark.get("value")
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
        enrichment = _enrich(
            ticker, library=library, plans_by_ticker=plans_by_ticker, sparks=sparks,
        )
        comparison = _prophet_comparison(
            ticker,
            plans_by_ticker=plans_by_ticker,
            lab_first_observed_at=expert["first_observed_at"],
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
            "evidence_eligible": expert["evidence_eligible"],
            "experts": [expert],
            "prophet_comparison": comparison,
        })
    rows.sort(key=lambda row: (row["sort_ts"], row["ticker"]), reverse=True)
    return rows


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
    experts.sort(key=lambda e: e["sort_ts"], reverse=True)
    row_class = _row_observation_class(experts)
    lead_anchor_observed_at = _earliest_live_forward_observed_at(experts)
    enrichment = _enrich(ticker, library=library, plans_by_ticker=plans_by_ticker, sparks=sparks)
    comparison = _prophet_comparison(
        ticker,
        plans_by_ticker=plans_by_ticker,
        lab_first_observed_at=lead_anchor_observed_at,
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
        "evidence_eligible": any(e["evidence_eligible"] for e in experts),
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
    rows.sort(key=lambda row: (row["sort_ts"], row["ticker"]), reverse=True)
    return rows


def build_all_early_board(
    events: Sequence[Mapping[str, Any]], *, episodes: Sequence[Any], **kw: Any,
) -> list[dict[str, Any]]:
    """``lab-all-early-v1`` — union G0 + C1(nonterminal) + C2a-f. EXCLUDES C3/C5.

    One ticker card may carry multiple ``experts[]`` (``DEC:LER-EXPERT-EVENT-FAMILIES-PRESERVED``:
    expert identities are never flattened).  C3/C5 events are never read into
    the matching set at all, so they cannot appear here regardless of what
    else is in the pool.
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
    rows.sort(key=lambda row: (row["sort_ts"], row["ticker"]), reverse=True)
    return rows


__all__ = [
    "build_g0_board",
    "build_c1_board",
    "build_c2a_board",
    "build_c2_variants_board",
    "build_intersection_board",
    "build_all_early_board",
]
