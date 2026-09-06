"""engine.chronicle.impact — event-to-asset consequence projection (F05, MO-PAID-017).

Reads chronicle spine events (the ONE canonical event owner — see spine.py's
module docstring) and projects a deterministic, owner-native
consequence/impact view per event: which tickers are implicated, whether the
linkage is direct (the event names the ticker) or second-order (inferred only
via shared theme, never via a ticker the event itself did not name), when the
underlying development happened vs when it became knowable, and a causal
label that is capped by construction to never claim more than the evidence
supports.

Do-not-redo (agentos/handoffs/MARKET-ONTOLOGY-F05-EVENT-IMPACT-CATALYST-FABLE-COO-2026-08-26.md):
no second event ID/database, no headline-count event identity, no LLM fact
extraction authority, no opaque catalyst ranker. This module performs no
scoring, no ranking, and no statistical estimation — it is a pure,
deterministic re-projection of fields already present on the chronicle.event.v1
record produced by spine.py. Calibrated impact magnitude is explicitly gated
on K5 (Evaluation OS / registered model law) and always reports as
``not_yet_knowable`` here rather than being estimated by this module.

Materiality law: "direct" means the ticker appears in the event's own
``tickers`` field (the adapter that produced the event already asserted that
linkage from source data). "second_order" means a ticker is NOT on the event
but shares a theme with the event and IS directly implicated by some OTHER
event carrying that theme, dated on-or-before this event (point-in-time --
no future-event leakage) -- a strictly weaker, labelled-as-such claim, never
silently promoted to direct, capped in count, and carried with the
originating event ids as its evidence (K1).

Causal label law: every projection carries ``causal_label`` fixed to
``"uncalibrated_association"``. This module has no identification strategy and
therefore never emits "causal" -- that ceiling is structural, not a runtime
check the caller could accidentally skip.

Bitemporal honesty (no fabricated known-at clock): every adapter today sets
``ts`` to either a genuine source publication timestamp, or (when the source
gives only a calendar date) exactly ``f"{date}T00:00:00Z"`` -- the same
instant as ``event_time``, not a distinct ingestion/discovery clock. Printing
that synthetic midnight stamp as "known_at" would fabricate a bitemporal claim
the ledger explicitly disclaims (correction_behavior: "event spine (chronicle)
-- no bitemporal claim made"). So ``known_at`` is populated ONLY when ``ts``
is genuinely distinct from the synthetic midnight-of-date value; otherwise it
is printed as ``None`` with a typed reason, per the fail-closed / nulls-
printed-not-hidden law -- never silently collapsed into ``event_time`` and
never fabricated.

Correction law: an event's ``kind``/fields never carry a corrected/withdrawn
state today (authoritative retractions are excluded from events.jsonl
entirely by spine.apply_authoritative_retractions before this module ever
sees them). A caller that still holds a retracted or superseded event object
(e.g. re-projecting a stale snapshot) can mark it explicitly via
``retracted=True`` / ``retraction_reason`` on :func:`project_event_impact`;
this module never infers retraction on its own -- that stays spine's call.
"""
from __future__ import annotations

from typing import Iterable

# Fixed by construction: this module performs no causal identification, so it
# can never emit a label stronger than an uncalibrated association regardless
# of event kind, weight_hint, or theme overlap.
CAUSAL_LABEL = "uncalibrated_association"

MATERIALITY_DIRECT = "direct"
MATERIALITY_SECOND_ORDER = "second_order"

# K5 (Evaluation OS / registered model law) is not consumed here -- any
# magnitude/probability estimate is out of scope for this projection and
# always reports this reason code rather than a fabricated number.
CALIBRATED_IMPACT_GATE_REASON = "not_yet_knowable_k5_gated"

# No genuine source clock at all (neither ``date`` nor ``ts`` present).
NO_SOURCE_CLOCK = "no_source_clock"
# ``ts`` exists but is not distinguishable from the synthetic
# midnight-of-``date`` stamp every non-timestamped adapter emits -- printing
# it as a separate "known_at" would fabricate a bitemporal claim.
NO_DISTINCT_SOURCE_CLOCK = "no_distinct_source_clock"

# K3/K5 dependency-cap law (ledger authority_ceiling: "context_only; K3/K5
# dependency caps causal/second-order claims"): second-order propagation is
# capped in count per event, and only carries a ticker forward when at least
# this many OTHER prior events under the shared theme directly name it --
# a single stray co-theme event can never fan one ticker out across the
# entire event set.
SECOND_ORDER_MIN_SUPPORT = 2
SECOND_ORDER_MAX_PER_EVENT = 5
SECOND_ORDER_CAPPED_REASON = "second_order_capped_k3_k5_dependency_ceiling"


def _midnight_of(date: str | None) -> str | None:
    return f"{date}T00:00:00Z" if date else None


def _time_fields(event: dict) -> tuple[str | None, str | None, str | None]:
    """Return (event_time, known_at, known_at_null_reason).

    Never fabricates a known_at that the source data does not actually
    support -- see the bitemporal-honesty note in the module docstring.
    """
    date = event.get("date") or None
    ts = event.get("ts") or None

    if not date and not ts:
        return None, None, NO_SOURCE_CLOCK

    event_time = date
    if ts and ts != _midnight_of(date):
        # A genuinely distinct clock (e.g. research_vault's published_at) --
        # this IS real bitemporal information, print it.
        return event_time, ts, None
    # ts is absent, or identical to the synthetic midnight-of-date stamp --
    # no separate ingestion/discovery clock exists yet.
    return event_time, None, NO_DISTINCT_SOURCE_CLOCK


def project_event_impact(
    event: dict,
    *,
    second_order_tickers: Iterable[str] = (),
    second_order_sources: dict[str, list[str]] | None = None,
    retracted: bool = False,
    retraction_reason: str | None = None,
) -> dict:
    """Project one chronicle.event.v1 record into a consequence/impact view.

    ``second_order_tickers`` (optional) lets a caller pass tickers implicated
    only via co-theme propagation from OTHER events -- this function never
    invents them itself. A ticker present in both the event's own ``tickers``
    and ``second_order_tickers`` is reported once, as direct (direct always
    wins; second-order is never used to demote a directly-named ticker).

    ``second_order_sources`` (optional) maps each second-order ticker to the
    originating event id(s) that directly named it under the shared theme --
    K1 evidence for what would otherwise be an unsourced claim.

    ``retracted``/``retraction_reason`` let a caller mark an event whose
    authoritative status has been withdrawn (spine.py's correction plane);
    such an event still carries its evidence fields but its exposures are
    force-emptied and its state is reported explicitly rather than silently
    projecting a live claim for a withdrawn record.
    """
    direct = [t for t in (event.get("tickers") or []) if t]
    direct_set = set(direct)
    second_order = [t for t in dict.fromkeys(second_order_tickers or ()) if t and t not in direct_set]
    second_order_sources = second_order_sources or {}

    event_time, known_at, known_at_reason = _time_fields(event)

    if retracted:
        exposures: list[dict] = []
    else:
        exposures = [
            {"ticker": t, "materiality": MATERIALITY_DIRECT} for t in direct
        ] + [
            {
                "ticker": t,
                "materiality": MATERIALITY_SECOND_ORDER,
                "source_event_ids": sorted(second_order_sources.get(t, [])),
            }
            for t in second_order
        ]

    return {
        "event_id": event.get("id"),
        # Time law: event_time is when the underlying development occurred
        # (spine's ``date``); known_at is when the chronicle store could
        # first know about it, printed ONLY when the source data actually
        # supports a distinct clock -- otherwise None + a typed reason
        # (never fabricated, never silently collapsed into event_time).
        "event_time": event_time,
        "known_at": known_at,
        "known_at_reason": known_at_reason,
        "source": event.get("source"),
        "source_ref": event.get("source_ref"),
        "kind": event.get("kind"),
        "title": event.get("title"),
        "facts": list(event.get("facts") or []),
        "links": event.get("links"),
        "themes": list(event.get("themes") or []),
        "exposures": exposures,
        "causal_label": CAUSAL_LABEL,
        "calibrated_impact": None,
        "calibrated_impact_reason": CALIBRATED_IMPACT_GATE_REASON,
        "state": "retracted" if retracted else "active",
        "retraction_reason": retraction_reason if retracted else None,
    }


def _co_theme_index(events: list[dict]) -> dict[str, list[tuple[str, str]]]:
    """theme -> [(ticker, date), ...] for every (ticker, event) directly
    naming that ticker under that theme -- one entry per (event, ticker)
    pair so callers can apply an as-of cutoff and a support-count test.
    """
    out: dict[str, list[tuple[str, str]]] = {}
    for ev in events:
        tickers = [t for t in (ev.get("tickers") or []) if t]
        date = ev.get("date") or ""
        if not tickers:
            continue
        for theme in (ev.get("themes") or []):
            out.setdefault(theme, []).append((date, tickers, ev.get("id")))
    return out


def project_events_impact(events: list[dict]) -> list[dict]:
    """Project a full event list, resolving second-order (co-theme) exposures.

    Point-in-time (Major 6): a ticker only propagates to an event via themes
    from OTHER events dated on-or-before that event's own date -- a later
    event can never leak its ticker backward onto an earlier one.

    Dependency-capped (Major 4): a ticker must be directly named by at least
    ``SECOND_ORDER_MIN_SUPPORT`` prior co-theme events before it propagates at
    all, and each event carries at most ``SECOND_ORDER_MAX_PER_EVENT``
    second-order tickers (ties broken by support count then ticker name,
    deterministic).

    Deterministic and order-preserving: iterating the same event list twice
    yields byte-identical output, matching spine.py's byte-stable regeneration
    contract. No field outside the event's own schema-allowed data is
    consulted -- no external ranking, no LLM call.
    """
    by_theme = _co_theme_index(events)
    projections = []
    for ev in events:
        own = set(ev.get("tickers") or [])
        own_date = ev.get("date") or ""
        # ticker -> set of supporting (prior, on-or-before-date) event ids
        support: dict[str, set[str]] = {}
        for theme in (ev.get("themes") or []):
            for date, tickers, src_id in by_theme.get(theme, ()):
                if date > own_date:
                    continue  # Major 6: no future-event leakage
                if src_id == ev.get("id"):
                    continue
                for t in tickers:
                    if t in own:
                        continue
                    support.setdefault(t, set()).add(src_id)

        candidates = [
            (t, sorted(ids)) for t, ids in support.items()
            if len(ids) >= SECOND_ORDER_MIN_SUPPORT
        ]
        candidates.sort(key=lambda pair: (-len(pair[1]), pair[0]))
        capped = candidates[:SECOND_ORDER_MAX_PER_EVENT]

        second_order = [t for t, _ in capped]
        second_order_sources = {t: ids for t, ids in capped}

        proj = project_event_impact(
            ev, second_order_tickers=second_order,
            second_order_sources=second_order_sources,
        )
        if len(candidates) > len(capped):
            proj["second_order_truncated"] = True
            proj["second_order_truncated_reason"] = SECOND_ORDER_CAPPED_REASON
        else:
            proj["second_order_truncated"] = False
            proj["second_order_truncated_reason"] = None
        projections.append(proj)
    return projections


def project_family_impact(events: list[dict]) -> dict[str, list[dict]]:
    """Group projected impact by event family (``source``) -- the "consequence
    surface per event family" the ledger row's acceptance test names. Grouping
    only; the underlying event identity, dedup and correction lineage remain
    entirely spine.py's -- this never mutates or re-derives an event id.
    """
    families: dict[str, list[dict]] = {}
    for proj in project_events_impact(events):
        families.setdefault(proj["source"] or "unknown", []).append(proj)
    return families


def write_family_impact(repo, families: dict[str, list[dict]]):
    """Persist the per-family consequence surface to
    data/chronicle/impact.jsonl -- the real consumer/entry point for this
    projection inside the owned engine/chronicle/ package (see
    governor.build_and_write). One JSON line per family, deterministic order.
    """
    import json
    import os
    import tempfile
    from pathlib import Path

    path = Path(repo) / "data" / "chronicle" / "impact.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), prefix=".impact-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            for family in sorted(families):
                fh.write(json.dumps({"family": family, "events": families[family]},
                                     sort_keys=True) + "\n")
        os.replace(tmp_path, path)
    except Exception:  # noqa: BLE001
        try:
            os.unlink(tmp_path)
        except Exception:  # noqa: BLE001
            pass
        raise
    return path
