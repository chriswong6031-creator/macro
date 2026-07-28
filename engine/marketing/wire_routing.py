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

Public API:
    route(event_class, *, cfg, root=None)  -> str          (the account id)
    routing_table(cfg, *, root=None)       -> dict         (class -> account, resolved)
    default_account(cfg)                   -> str
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


def _enabled_accounts(cfg: dict | None, root: Path | str | None) -> set[str]:
    """Ids of accounts the accounts model considers live. Fail-soft: on any
    error return an empty set, which makes every route fall back to the default
    — the pre-XG-W2 behaviour, never a silent widening."""
    try:
        from engine.marketing.accounts import effective_accounts  # noqa: PLC0415

        return {
            str(a.get("id") or "")
            for a in effective_accounts(cfg, root)
            if a.get("enabled")
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("wire_routing: accounts model unavailable (%s) — default only", exc)
        return set()


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
        out[str(klass)] = acct if (not live or acct in live) else fallback
    return out


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

    live = _enabled_accounts(cfg, root)
    if live and acct not in live:
        # Start-of-line annotation (house law): a logger prefix would make GitHub
        # drop this silently, and a dark route is exactly the thing an operator
        # must see in the Actions summary.
        print(
            f"::warning title=wire-routing-dark::event_class {event_class!r} routes "
            f"to {acct!r}, which is not enabled in desk_network — falling back to "
            f"{fallback!r}. Enable the desk to arm the route.",
            flush=True,
        )
        return fallback
    return acct
