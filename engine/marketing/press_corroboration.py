"""engine.marketing.press_corroboration — deterministic corroboration gate.

Implements the D05 Addendum 2 §3 corroboration law. Pure, network-free, no LLM —
a deterministic decision about whether a scored press item may instant-publish, be
downgraded to attributed phrasing, or fall to the next-morning digest.

Corroboration classes (from the addendum + the x_follow register):
    direct-quote  Trump's own post, mirror-verified via the Truth Social status
                  URL. A single primary source suffices — attribute "on Truth Social".
    hearsay       "Trump told reporters...", bank-call claims, geopolitical relays.
                  Requires >=2 INDEPENDENT sources within a window OR is downgraded
                  to attributed "reports:" phrasing. A single-wire UNCORROBORATED
                  political/geopolitical item NEVER instant-publishes (-> digest).

Public API:
    corroboration_decision(item, *, corroborated_sources, window_ok) -> dict
        {gate: "instant" | "attributed" | "digest", reason: str, attribution: str}

`corroborated_sources` is the count of INDEPENDENT sources (distinct source keys /
handles) that have carried the same claim inside the window; `window_ok` says
whether those corroborating sources arrived inside corroboration_window_s.
"""
from __future__ import annotations

# Event classes that are "political/geopolitical" for the never-instant rule.
_POLITICAL_CLASSES = frozenset({"policy", "geopolitical"})

# THE CREDIT IS GENERIC (operator law 2026-08-02). This used to be
# f"{source_name} reporting", which on an X relay item rendered
# "-- @FirstSquawk reporting" straight into a live post: a source tag on the
# account we relayed. We reword and republish; we never brand the original
# account. The ADMISSION survives — the wire charter's admission-not-editorial
# rule wants the reader told this is a relayed report, not who relayed it — so
# the attributed and digest paths still carry a credit clause, just an unnamed
# one. The direct-quote path is a VENUE ("on Truth Social"), not an account, and
# is unchanged.
_WIRE_CREDIT = "wire reports"


def corroboration_decision(
    item: dict,
    *,
    corroborated_sources: int = 1,
    window_ok: bool = False,
) -> dict:
    """Decide the publish gate for a scored press item.

    Returns {gate, reason, attribution}:
        gate="instant"     may go out immediately (direct-quote, or corroborated hearsay)
        gate="attributed"  may go out but MUST use attributed "reports:" phrasing
        gate="digest"      falls to the next-morning digest (never instant)
    """
    corr_class = str(item.get("corroboration_class", "hearsay"))
    source_tier = str(item.get("source_tier", "aggregator"))
    event_class = str(item.get("event_class", "none"))
    strict = bool(item.get("strict_corroboration", False))

    # ── direct-quote: mirror-verified own post — single primary source OK ──────
    if corr_class == "direct-quote" and source_tier == "mirror":
        return {
            "gate": "instant",
            "reason": "direct-quote mirror-verified (single primary source OK)",
            "attribution": "on Truth Social",
        }

    # ── hearsay class ─────────────────────────────────────────────────────────
    # >=2 independent sources inside the window -> instant.
    if corroborated_sources >= 2 and window_ok:
        return {
            "gate": "instant",
            "reason": f"{corroborated_sources} independent sources corroborate within window",
            "attribution": "",
        }

    # Single-wire UNCORROBORATED political/geopolitical NEVER instant-publishes.
    if event_class in _POLITICAL_CLASSES:
        return {
            "gate": "digest",
            "reason": (
                f"single-source uncorroborated {event_class} political claim — "
                "next-morning digest (never instant)"
            ),
            "attribution": _WIRE_CREDIT,
        }

    # A strict-corroboration handle (BRICSinfo / rawsalerts) with no corroboration
    # also falls to the digest.
    if strict:
        return {
            "gate": "digest",
            "reason": "strict-corroboration source with no independent confirmation",
            "attribution": _WIRE_CREDIT,
        }

    # Other single-source hearsay -> attributed phrasing (may post, must attribute).
    return {
        "gate": "attributed",
        "reason": "single-source hearsay — attributed phrasing required",
        "attribution": _WIRE_CREDIT,
    }
