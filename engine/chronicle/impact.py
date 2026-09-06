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
event carrying that theme (co-theme propagation) -- a strictly weaker,
labelled-as-such claim, never silently promoted to direct.

Causal label law: every projection carries ``causal_label`` fixed to
``"uncalibrated_association"``. This module has no identification strategy and
therefore never emits "causal" -- that ceiling is structural, not a runtime
check the caller could accidentally skip.
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


def project_event_impact(event: dict, *, second_order_tickers: Iterable[str] = ()) -> dict:
    """Project one chronicle.event.v1 record into a consequence/impact view.

    ``second_order_tickers`` (optional) lets a caller pass tickers implicated
    only via co-theme propagation from OTHER events -- this function never
    invents them itself. A ticker present in both the event's own ``tickers``
    and ``second_order_tickers`` is reported once, as direct (direct always
    wins; second-order is never used to demote a directly-named ticker).
    """
    direct = [t for t in (event.get("tickers") or []) if t]
    direct_set = set(direct)
    second_order = [t for t in dict.fromkeys(second_order_tickers or ()) if t and t not in direct_set]

    exposures = [
        {"ticker": t, "materiality": MATERIALITY_DIRECT} for t in direct
    ] + [
        {"ticker": t, "materiality": MATERIALITY_SECOND_ORDER} for t in second_order
    ]

    return {
        "event_id": event.get("id"),
        # Time law: event_time is when the underlying development occurred
        # (spine's ``date``); known_at is when the chronicle store could
        # first know about it (spine's ``ts``). These are distinct and both
        # printed -- never collapsed into one timestamp.
        "event_time": event.get("date"),
        "known_at": event.get("ts"),
        "source": event.get("source"),
        "kind": event.get("kind"),
        "themes": list(event.get("themes") or []),
        "exposures": exposures,
        "causal_label": CAUSAL_LABEL,
        "calibrated_impact": None,
        "calibrated_impact_reason": CALIBRATED_IMPACT_GATE_REASON,
    }


def _co_theme_tickers(events: list[dict]) -> dict[str, set[str]]:
    """theme -> set of tickers directly named by some event carrying that theme."""
    out: dict[str, set[str]] = {}
    for ev in events:
        tickers = [t for t in (ev.get("tickers") or []) if t]
        if not tickers:
            continue
        for theme in (ev.get("themes") or []):
            out.setdefault(theme, set()).update(tickers)
    return out


def project_events_impact(events: list[dict]) -> list[dict]:
    """Project a full event list, resolving second-order (co-theme) exposures.

    Deterministic and order-preserving: iterating the same event list twice
    yields byte-identical output, matching spine.py's byte-stable regeneration
    contract. No field outside the event's own schema-allowed data is
    consulted -- no external ranking, no LLM call.
    """
    by_theme = _co_theme_tickers(events)
    projections = []
    for ev in events:
        own = set(ev.get("tickers") or [])
        second_order: list[str] = []
        seen: set[str] = set()
        for theme in (ev.get("themes") or []):
            for t in sorted(by_theme.get(theme, ())):
                if t not in own and t not in seen:
                    seen.add(t)
                    second_order.append(t)
        projections.append(project_event_impact(ev, second_order_tickers=second_order))
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
