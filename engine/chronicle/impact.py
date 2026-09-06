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
but shares a *narrow* theme with the event and IS directly implicated by some
OTHER event carrying that theme, dated on-or-before this event (point-in-time
-- no future-event leakage) -- a strictly weaker, labelled-as-such claim,
never silently promoted to direct. Broad co-mention themes (e.g. corpus-wide
"earnings") fail closed rather than fabricating materiality. When more than
``SECOND_ORDER_MAX_PER_EVENT`` candidates remain after the specificity +
support filters, the projection refuses ALL second-order exposures for that
event (fail closed on ambiguity) and prints the candidate/dropped counts --
it never ranks by co-mention count or alphabetical tiebreak to pick winners.

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

Nightly write law: this module never writes a git-tracked data/ artifact.
Consumers call :func:`project_events_impact` / :func:`glance_consequence_surface`
at render or inspect time over a bounded event window.
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

# Second-order eligibility (fail closed on weak materiality / ambiguity).
# MIN_SUPPORT is an eligibility floor, not a ranker. MAX_PER_EVENT is a
# refuse-all ceiling when ambiguity remains after the theme-specificity gate
# -- never a top-N selector. THEME_MAX_SHARE refuses corpus-dominant themes
# (measured: "earnings" alone is ~82% of events.jsonl) where co-theme carries
# no information.
SECOND_ORDER_MIN_SUPPORT = 2
SECOND_ORDER_MAX_PER_EVENT = 5
SECOND_ORDER_THEME_MAX_SHARE = 0.05
# Share gate only applies once a theme's absolute count clears this floor —
# otherwise a 3-event fixture would refuse every theme (3/3 = 100% share)
# while the real corpus still needs the share gate for "earnings" (~82%).
SECOND_ORDER_THEME_BROAD_MIN_COUNT = 40
SECOND_ORDER_AMBIGUOUS_REASON = "second_order_refused_ambiguous_cap"
SECOND_ORDER_THEME_TOO_BROAD_REASON = "second_order_refused_theme_too_broad"
# Kept as an alias so older call-sites/tests that still reference the prior
# truncation reason string keep resolving; new emits use AMBIGUOUS_REASON.
SECOND_ORDER_CAPPED_REASON = SECOND_ORDER_AMBIGUOUS_REASON

# Glance-tier surface bound (News Feed consequence panel). Bounded so render
# never runs the full-corpus projection.
GLANCE_EVENT_LIMIT = 24


def _midnight_of(date: str | None) -> str | None:
    return f"{date}T00:00:00Z" if date else None


def _time_fields(event: dict) -> tuple[str | None, str | None, str | None]:
    """Return (event_time, known_at, known_at_null_reason).

    Never fabricates a known_at that the source data does not actually
    support -- see the bitemporal-honesty note in the module docstring.
    event_time and known_at stay the same granularity family: event_time is
    always a calendar date (YYYY-MM-DD) when knowable; known_at is an ISO
    instant only when genuinely distinct from midnight-of-that-date.
    """
    date = event.get("date") or None
    ts = event.get("ts") or None

    if not date and not ts:
        return None, None, NO_SOURCE_CLOCK

    # When date is absent but ts is present, recover the calendar date from
    # the timestamp so we never print known_at beside a null event_time.
    if not date and isinstance(ts, str) and len(ts) >= 10 and ts[4] == "-" and ts[7] == "-":
        date = ts[:10]

    event_time = date
    if ts and ts != _midnight_of(date):
        return event_time, ts, None
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


def _co_theme_index(events: list[dict]) -> dict[str, list[tuple[str, list[str], str | None]]]:
    """theme -> [(date, tickers, event_id), ...] for every event that
    directly names tickers under that theme -- one entry per event so
    callers can apply an as-of cutoff and a support-count eligibility test.
    """
    out: dict[str, list[tuple[str, list[str], str | None]]] = {}
    for ev in events:
        tickers = [t for t in (ev.get("tickers") or []) if t]
        date = ev.get("date") or ""
        if not tickers:
            continue
        for theme in (ev.get("themes") or []):
            out.setdefault(theme, []).append((date, tickers, ev.get("id")))
    return out


def _eligible_themes(events: list[dict]) -> set[str]:
    """Themes narrow enough that co-theme overlap can carry materiality.

    A theme is refused only when it is both numerous in absolute terms
    (``SECOND_ORDER_THEME_BROAD_MIN_COUNT``) AND appears on more than
    ``SECOND_ORDER_THEME_MAX_SHARE`` of the event set. Corpus-dominant themes
    like "earnings" (~82% of events.jsonl) fail closed; small fixtures and
    genuinely narrow themes stay eligible.
    """
    if not events:
        return set()
    counts: dict[str, int] = {}
    for ev in events:
        for theme in set(ev.get("themes") or []):
            counts[theme] = counts.get(theme, 0) + 1
    n = len(events)
    eligible: set[str] = set()
    for theme, count in counts.items():
        if count >= SECOND_ORDER_THEME_BROAD_MIN_COUNT and (count / n) > SECOND_ORDER_THEME_MAX_SHARE:
            continue
        eligible.add(theme)
    return eligible


def project_events_impact(events: list[dict]) -> list[dict]:
    """Project a full event list, resolving second-order (co-theme) exposures.

    Point-in-time: a ticker only propagates to an event via themes from OTHER
    events dated on-or-before that event's own date -- a later event can never
    leak its ticker backward onto an earlier one.

    Fail-closed specificity: only themes at-or-below
    ``SECOND_ORDER_THEME_MAX_SHARE`` of the corpus participate. Broad themes
    are refused with a typed reason, not ranked through.

    Fail-closed ambiguity: a ticker must be directly named by at least
    ``SECOND_ORDER_MIN_SUPPORT`` prior co-theme events; if more than
    ``SECOND_ORDER_MAX_PER_EVENT`` candidates remain, ALL second-order
    exposures for that event are refused and the candidate/dropped counts are
    printed. There is no support-count or alphabetical top-N selector -- that
    would be an opaque catalyst ranker (do_not_redo).

    Deterministic and order-preserving: iterating the same event list twice
    yields byte-identical output, matching spine.py's byte-stable regeneration
    contract. No field outside the event's own schema-allowed data is
    consulted -- no external ranking, no LLM call.
    """
    eligible = _eligible_themes(events)
    by_theme = {
        theme: rows for theme, rows in _co_theme_index(events).items()
        if theme in eligible
    }
    projections = []
    for ev in events:
        own = set(ev.get("tickers") or [])
        own_date = ev.get("date") or ""
        own_themes = list(ev.get("themes") or [])
        refused_themes = sorted({t for t in own_themes if t not in eligible})

        # ticker -> set of supporting (prior, on-or-before-date) event ids
        support: dict[str, set[str]] = {}
        for theme in own_themes:
            if theme not in eligible:
                continue
            for date, tickers, src_id in by_theme.get(theme, ()):
                if date > own_date:
                    continue
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
        # Deterministic order by ticker name only -- NEVER by support count.
        # Sorting here is for stable output, not selection: when over the
        # ceiling we refuse the whole set rather than taking a prefix.
        candidates.sort(key=lambda pair: pair[0])
        candidate_count = len(candidates)

        if candidate_count > SECOND_ORDER_MAX_PER_EVENT:
            second_order: list[str] = []
            second_order_sources: dict[str, list[str]] = {}
            truncated = True
            truncated_reason = SECOND_ORDER_AMBIGUOUS_REASON
            dropped_count = candidate_count
        else:
            second_order = [t for t, _ in candidates]
            second_order_sources = {t: ids for t, ids in candidates}
            truncated = False
            truncated_reason = None
            dropped_count = 0

        proj = project_event_impact(
            ev, second_order_tickers=second_order,
            second_order_sources=second_order_sources,
        )
        proj["second_order_truncated"] = truncated
        proj["second_order_truncated_reason"] = truncated_reason
        proj["second_order_candidate_count"] = candidate_count
        proj["second_order_dropped_count"] = dropped_count
        if refused_themes:
            proj["second_order_theme_refused"] = refused_themes
            proj["second_order_theme_refused_reason"] = SECOND_ORDER_THEME_TOO_BROAD_REASON
        else:
            proj["second_order_theme_refused"] = []
            proj["second_order_theme_refused_reason"] = None
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


def glance_consequence_surface(
    events: list[dict],
    *,
    limit: int = GLANCE_EVENT_LIMIT,
) -> dict:
    """Bounded, plain-word consequence surface for the News Feed panel.

    Reads spine events (most-recent first), projects impact over that window
    only, and returns glance rows plus an explicit Market-Feed disposition:
    this surface is served on the existing News Feed page and is NOT a
    Market-Feed-branded product surface (MO-DELTA-001).

    Calibrated impact stays null + reason. Empty / missing input prints an
    honest null state rather than fabricating rows.
    """
    if not events:
        return {
            "served_as_market_feed": False,
            "market_feed_disposition": "explicitly_does_not_serve_market_feed",
            "stance_en": "Not available yet",
            "stance_zh": "暂不可用",
            "reason_en": "No chronicle events in this window yet.",
            "reason_zh": "此窗口尚无大事记事件。",
            "families": {},
            "rows": [],
            "event_count": 0,
        }

    # Most-recent window, then restore chronological order for projection
    # (point-in-time second-order needs on-or-before semantics inside the window).
    newest = sorted(
        events,
        key=lambda e: (e.get("date") or "", e.get("id") or ""),
        reverse=True,
    )[: max(1, int(limit))]
    window = sorted(
        newest,
        key=lambda e: (e.get("date") or "", e.get("id") or ""),
    )
    families = project_family_impact(window)
    rows = []
    for proj in project_events_impact(window):
        direct = [e["ticker"] for e in proj["exposures"] if e.get("materiality") == MATERIALITY_DIRECT]
        second = [e["ticker"] for e in proj["exposures"] if e.get("materiality") == MATERIALITY_SECOND_ORDER]
        rows.append({
            "event_id": proj["event_id"],
            "event_time": proj["event_time"],
            "known_at": proj["known_at"],
            "family": proj["source"] or "unknown",
            "title": proj.get("title") or "",
            "direct_tickers": direct,
            "second_order_tickers": second,
            "second_order_truncated": bool(proj.get("second_order_truncated")),
            "second_order_candidate_count": proj.get("second_order_candidate_count", 0),
            "second_order_dropped_count": proj.get("second_order_dropped_count", 0),
            "calibrated_impact": None,
            "calibrated_impact_reason": CALIBRATED_IMPACT_GATE_REASON,
            "causal_label": CAUSAL_LABEL,
        })
    # Glance order: newest first.
    rows.sort(key=lambda r: (r.get("event_time") or "", r.get("event_id") or ""), reverse=True)
    return {
        "served_as_market_feed": False,
        "market_feed_disposition": "explicitly_does_not_serve_market_feed",
        "stance_en": "Named tickers on recent chronicle events",
        "stance_zh": "近期大事记事件中点名的标的",
        "reason_en": None,
        "reason_zh": None,
        "families": {k: len(v) for k, v in families.items()},
        "rows": rows,
        "event_count": len(window),
    }
