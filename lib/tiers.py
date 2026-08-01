"""lib/tiers.py — the ONE place a tier STRING coming from outside is made canonical.

``insider`` is the wire value: it is what Stripe webhooks write into
``public.user_entitlements.tier``, what ``config/plans.yml`` carries as ``tier:``, and what
every quota bucket, entitlement gate and segment predicate on the estate keys on.
``config/plans.yml`` already renamed that product's DISPLAY name to "Essential" (#4164)
while deliberately leaving the wire value alone, and a later migration will flip the stored
value too.

This module is **Phase 1** of that migration and it is one-directional: every boundary that
READS a tier string from the outside — a request body, a query string, a stored row, the
Terminal client — must ACCEPT ``essential`` and resolve it to ``insider``. Nothing here
emits ``essential``; Phase 2 owns that. For a value that is already canonical this function
is the identity, so arming it changes no behaviour today.

WHY A NORMALIZER RATHER THAN A WIDER ALLOW-LIST
----------------------------------------------
The failure a tolerance gap produces here is silent, not loud.
``brain_gateway._get_allowance`` selects ``quotas[tier] if tier in quotas else
quotas['free']`` — an unrecognised tier does not raise, it drops a PAYING customer into the
free 5-questions-a-week bucket. Same shape in ``admin/entitlements``: widening the accepted
tuple without normalising would let an operator action WRITE ``essential`` into the
entitlement row, emitting exactly the value Phase 1 must not emit. So the rule at every
boundary is normalise-then-validate, never validate-a-wider-set.

WHY IT LIVES IN ``lib/``
------------------------
Both ``app/`` (billing, main, admin bridges) and ``engine/`` (the brain gateway) need it,
and ``lib/`` is the layer they already share in that direction — ``engine/`` importing
``app/`` would be a new and backwards edge.

CATALOG-DRIVEN
--------------
The alias table is DERIVED from ``config/plans.yml``: a product whose display ``name``
slugifies to something other than its ``tier`` contributes ``<slug> -> <tier>``. Rename a
product in the catalog and its alias follows automatically, with no second list to forget
about. ``_STATIC_ALIASES`` is the floor, not a duplicate: this function runs inside request
paths and in stdlib-only contexts, so an unreadable catalog or a missing PyYAML must
degrade to the known alias rather than raise or return a wrong answer.
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path

log = logging.getLogger("macro.tiers")

ROOT = Path(os.environ.get("MACRO_REPO") or Path(__file__).resolve().parents[1])

#: The floor. Correct with no catalog, no PyYAML and no filesystem — the catalog can only
#: ADD to this, and (see ``_derive_aliases``) can never shadow a canonical wire value.
_STATIC_ALIASES: dict[str, str] = {"essential": "insider"}

_SLUG_RE = re.compile(r"[^a-z0-9]+")

_ALIAS_CACHE: dict[str, str] | None = None


def _slug(name: object) -> str:
    """``"Essential"`` -> ``essential``; ``"Founding Pro"`` -> ``founding_pro``."""
    return _SLUG_RE.sub("_", str(name or "").strip().lower()).strip("_")


def _derive_aliases() -> dict[str, str]:
    """``{alias -> canonical tier}`` from the catalog, over the static floor.

    Two rules keep a display-name rename from ever becoming an entitlement bug:

    * an alias equal to its own tier is not an alias (no-op);
    * an alias that collides with ANY canonical tier (a product's ``tier``, or a member of
      ``tier_rank``) is dropped — naming a product "Pro" while it sells the ``insider``
      tier must not silently reroute ``pro`` requests.
    """
    aliases = dict(_STATIC_ALIASES)
    try:
        import yaml  # noqa: PLC0415 — stdlib-only import paths must still work
        with (ROOT / "config" / "plans.yml").open() as fh:
            catalog = yaml.safe_load(fh) or {}
        products = list((catalog.get("products") or {}).values())
        canonical = {str(p.get("tier") or "").strip().lower() for p in products}
        canonical.update(str(t).strip().lower() for t in (catalog.get("tier_rank") or []))
        canonical.discard("")
        for prod in products:
            tier = str(prod.get("tier") or "").strip().lower()
            alias = _slug(prod.get("name"))
            if not tier or not alias or alias == tier or alias in canonical:
                continue
            aliases[alias] = tier
    except Exception as exc:  # noqa: BLE001 — a request path may never die on the catalog
        log.debug("tiers: catalog alias derive failed (%s) — static table only",
                  type(exc).__name__)
    return aliases


def tier_aliases() -> dict[str, str]:
    """The resolved ``{alias -> canonical tier}`` map (process-cached)."""
    global _ALIAS_CACHE
    if _ALIAS_CACHE is None:
        _ALIAS_CACHE = _derive_aliases()
    return dict(_ALIAS_CACHE)


def reset_cache() -> None:
    """Drop the derived alias map — for tests that rewrite the catalog."""
    global _ALIAS_CACHE
    _ALIAS_CACHE = None


def normalize_tier(value: object) -> str:
    """Canonical wire tier for ``value``; ``''`` when there is nothing to normalise.

    Strips and lower-cases (every caller already did that by hand), then resolves ONE alias
    hop — matching the wire form first and the slug form second, so a display name carrying
    a space ("Desk Pass") resolves as well as the wire-shaped ``essential``.

    An unknown string comes back lower-cased and otherwise UNCHANGED — not slugified, so
    the caller's own enum check rejects exactly what it always did. This function widens
    what is ACCEPTED; it never decides what is VALID. ``normalize_tier('insider') ==
    'insider'``: canonical values are untouched, which is why arming this is a no-op for
    every row that exists today.
    """
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    aliases = tier_aliases()
    if raw in aliases:
        return aliases[raw]
    return aliases.get(_slug(raw), raw)
