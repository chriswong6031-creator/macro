"""engine.marketing.wire_routing — which account owns a wire emission (XG-W2).

THE GAP THIS CLOSES. ``engine/marketing/press_lane.py`` hardcoded
``_ACCOUNT = "flagship"`` at module scope, so the entire press/wire lane could
address exactly one of the seven live Buffer channels. That was invisible in
config: an operator reading ``publish.channels`` saw seven addressable accounts
and no hint that the wire lane could only ever speak as one of them. Worse, the
account whose whole job IS the wire — ``mastermind_news`` — could not receive a
wire item even after being enabled, because the routing lived in a Python
constant.

Routing is now CONFIG (``config/marketing.yml`` ``wire_routing:``):

    wire_routing:
      default: flagship
      classes:
        macro_print: flagship
        policy: flagship
        ...

A routing change is a config edit, never a code edit. The mapping keys are
``breaking_relevance`` event_class slugs (the same slugs ``press_lane``'s
``_CLASS_LABELS`` table renders).

LIVENESS IS NOT ROUTING. The map may name an account that is not armed yet —
``mastermind_news`` is wired-but-dark on purpose. Routing therefore resolves
through the accounts model (``engine.marketing.accounts.effective_accounts``):
a class routed to a disabled account falls back to the default with a
start-of-line ``::warning``, so the operator sees the intent AND the fact that
it is not in force. Enabling the desk is what arms the route — exactly one flip,
in ``desk_network``, where every other arming decision already lives.

SPILL IS ROUTING TOO (W4d). When the account a class routes to has spent its
daily wire budget, the surplus may move to ANOTHER wire desk rather than being
dropped — but only to a desk the operator has already declared a wire owner.
``spill_pool`` answers that question from the SAME config and the SAME liveness
read as ``route``, so there is exactly one answer to "may this desk carry a wire
relay". It deliberately does NOT return every enabled account in
``desk_network``: the persona desks (meagan/sophia/kelly/cici/founder) are
authored voices, and the charter is explicit that wire accounts RELAY and never
take a stance (masterplan §4 safety rails). Handing a persona a raw press relay
would be a voice violation dressed up as a volume fix.

Public API:
    route(event_class, *, cfg, root=None)  -> str          (the account id)
    routing_table(cfg, *, root=None)       -> dict         (class -> account, resolved)
    default_account(cfg)                   -> str
    spill_pool(cfg, *, root=None)          -> list[str]    (live wire-owning desks)
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

#: The account every wire item went to before XG-W2, and the fallback when
#: config declares nothing. Keeping the historical value as the fallback means a
#: config-less checkout behaves exactly as it did before this module existed.
DEFAULT_ACCOUNT = "flagship"


def _block(cfg: dict | None) -> dict[str, Any]:
    if not isinstance(cfg, dict):
        return {}
    raw = cfg.get("wire_routing")
    return raw if isinstance(raw, dict) else {}


def default_account(cfg: dict | None) -> str:
    """``wire_routing.default``, or the historical flagship fallback."""
    value = str(_block(cfg).get("default") or "").strip()
    return value or DEFAULT_ACCOUNT


def _enabled_accounts(cfg: dict | None, root: Path | str | None) -> set[str] | None:
    """Ids of accounts the accounts model considers live, or None when liveness
    is UNKNOWN (the accounts model could not be consulted).

    None and the empty set are different answers and callers must not conflate
    them — the first version of this function returned an empty set for both,
    and the callers' ``if live and …`` test then treated "unknown" as "no
    constraint" and let a configured DARK account through. That is a silent
    widening in the one failure mode where widening is least defensible, and it
    is the exact opposite of what this module promises. Unknown liveness now
    routes to the default, which is the pre-XG-W2 behaviour and always safe.
    """
    try:
        from engine.marketing.accounts import effective_accounts  # noqa: PLC0415

        return {
            str(a.get("id") or "")
            for a in effective_accounts(cfg, root)
            if a.get("enabled")
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("wire_routing: accounts model unavailable (%s) — default only", exc)
        return None


#: Accounts already warned about in THIS process. route() runs once per press
#: item and the daemon ticks on an interval, so an unarmed route would otherwise
#: print the same annotation thousands of times a day and bury the Actions
#: summary it exists to surface. Keyed by account, not by (class, account): the
#: operator's action is the same one desk_network flip whichever class hit it.
_WARNED_DARK: set[str] = set()


def reset_dark_route_warnings() -> None:
    """Clear the once-per-process warning set (tests)."""
    _WARNED_DARK.clear()


def _warn_dark_route(event_class: object, acct: str, fallback: str, *,
                     unknown: bool) -> None:
    """Print the dark-route annotation at most once per account per process."""
    if acct in _WARNED_DARK:
        return
    _WARNED_DARK.add(acct)
    why = ("liveness could not be resolved" if unknown
           else "is not enabled in desk_network")
    # Start-of-line annotation (house law): a logger prefix would make GitHub
    # drop this silently, and a dark route is exactly the thing an operator must
    # see in the Actions summary.
    print(
        f"::warning title=wire-routing-dark::event_class {event_class!r} routes "
        f"to {acct!r}, which {why} — falling back to {fallback!r}. Enable the "
        f"desk to arm the route.",
        flush=True,
    )


def routing_table(cfg: dict | None, *, root: Path | str | None = None) -> dict[str, str]:
    """``{event_class: account}`` AFTER liveness resolution.

    A class whose configured account is not enabled is reported here mapped to
    the default, so an admin surface shows what is actually in force rather than
    what the file wishes were in force.
    """
    classes = _block(cfg).get("classes")
    if not isinstance(classes, dict):
        return {}
    fallback = default_account(cfg)
    live = _enabled_accounts(cfg, root)
    out: dict[str, str] = {}
    for klass, account in classes.items():
        acct = str(account or "").strip()
        if not acct:
            continue
        # Unknown liveness (live is None) routes to the default, same as a known
        # dark account. Only a POSITIVE membership check arms a route.
        out[str(klass)] = acct if (live is not None and acct in live) else fallback
    return out


def spill_pool(cfg: dict | None, *, root: Path | str | None = None) -> list[str]:
    """LIVE accounts that may carry a wire relay, deterministically ordered.

    The roster is DECLARED, never inferred from ``desk_network`` membership:

        wire_routing.spill_accounts: [flagship, mastermind_news]   # explicit
        (absent) -> {wire_routing.default} | set(wire_routing.classes.values())

    The implicit form is the useful default — an account an operator has already
    pointed a wire class at is, by that act, a declared wire owner. The explicit
    key exists so a desk can be made spill-eligible WITHOUT owning a class
    outright (the wire desk that takes overflow but is not the primary for
    anything).

    WHY NOT "every enabled account". Because ``desk_network`` also holds the
    persona desks, and §4's safety rails say wire accounts never take stances.
    A press relay routed to a persona is a voice violation, and it would arrive
    through the one lane whose whole contract is verbatim-with-attribution.
    Volume is not a reason to break the charter, so the pool stays declarative.

    LIVENESS IS THE SAME READ ``route`` USES. Unknown liveness (the accounts
    model could not be consulted) returns ONLY the default — the pre-W4d
    behaviour, and the same fail-closed answer ``route`` gives — because an
    import failure is not evidence that a desk is armed. A dark account is never
    in the returned list.

    The default account always sorts FIRST when it is live (it is the historical
    owner of every class); the rest follow in sorted order so a spill choice is
    reproducible across runs rather than dict-order roulette.
    """
    fallback = default_account(cfg)
    live = _enabled_accounts(cfg, root)
    if live is None:
        return [fallback]

    block = _block(cfg)
    declared: list[str] = []
    raw = block.get("spill_accounts")
    if isinstance(raw, (list, tuple)):
        declared = [str(a or "").strip() for a in raw]
    else:
        classes = block.get("classes")
        if isinstance(classes, dict):
            declared = [str(a or "").strip() for a in classes.values()]
        declared.append(fallback)

    pool = {a for a in declared if a and a in live}
    ordered = [fallback] if fallback in pool else []
    ordered.extend(sorted(a for a in pool if a != fallback))
    return ordered


def route(
    event_class: Any,
    *,
    cfg: dict | None,
    root: Path | str | None = None,
) -> str:
    """The account id that owns a wire emission of ``event_class``.

    Falls back to ``wire_routing.default`` (then to ``flagship``) for an
    unmapped class, an empty mapping, or a mapping onto a disabled account.
    Never raises.
    """
    fallback = default_account(cfg)
    classes = _block(cfg).get("classes")
    if not isinstance(classes, dict):
        return fallback

    acct = str(classes.get(str(event_class)) or "").strip()
    if not acct:
        return fallback
    if acct == fallback:
        return fallback

    # Only a POSITIVE membership check arms a route: unknown liveness (None)
    # falls back exactly like a known-dark account.
    live = _enabled_accounts(cfg, root)
    if live is None or acct not in live:
        _warn_dark_route(event_class, acct, fallback, unknown=live is None)
        return fallback
    return acct
