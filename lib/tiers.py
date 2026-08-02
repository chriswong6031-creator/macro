"""lib/tiers.py — the ONE place a tier STRING coming from outside is made canonical.

``essential`` is the wire value as of **Phase 2** (#4176 armed the tolerance, this flipped
the catalog): it is what ``config/plans.yml`` carries as ``tier:``, what the Stripe webhook
writes into ``public.user_entitlements.tier``, and what every quota bucket, entitlement gate
and segment predicate on the estate keys on. ``insider`` is the value that shipped before
the rename.

THE ALIAS DIRECTION REVERSED HERE, AND ``insider`` IS PERMANENT
--------------------------------------------------------------
Phase 1 resolved ``essential -> insider``; this module now resolves ``insider ->
essential``. The old value never stops arriving:

* rows written before the flip still carry ``insider`` in ``user_entitlements.tier``
  (nothing back-fills them — the catalog's ``legacy_lookup_keys`` keep those subscriptions
  resolving, and a webhook re-computes the row to ``essential`` only when Stripe next
  touches the subscription);
* ``theme.js`` / ``onboard.js`` / ``tier_preview.js`` are served ``immutable`` with a
  far-future max-age, so a warm browser cache keeps POSTing ``insider`` indefinitely;
* the Terminal repo and any saved admin/campaign targeting hold the old string too.

So the inbound tolerance for ``insider`` has no expiry date. Deleting it downgrades real
paying customers.

WHY A NORMALIZER RATHER THAN A WIDER ALLOW-LIST
----------------------------------------------
The failure a tolerance gap produces here is silent, not loud.
``brain_gateway._get_allowance`` selects ``quotas[tier] if tier in quotas else
quotas['free']`` — an unrecognised tier does not raise, it drops a PAYING customer into the
free 5-questions-a-week bucket. Same shape in ``admin/entitlements``: widening the accepted
tuple without normalising would let an operator action WRITE the stale value back into the
entitlement row. So the rule at every boundary is normalise-then-validate, never
validate-a-wider-set.

WHY IT LIVES IN ``lib/``
------------------------
Both ``app/`` (billing, main, admin bridges) and ``engine/`` (the brain gateway) need it,
and ``lib/`` is the layer they already share in that direction — ``engine/`` importing
``app/`` would be a new and backwards edge.

CATALOG-DRIVEN
--------------
The alias table is DERIVED from ``config/plans.yml``, by two rules:

* ``legacy_product_keys`` — ``{<current products key>: [<former key>, ...]}``. Each former
  key becomes an alias of the current product's ``tier``. This is what carries
  ``insider -> essential`` today, and it is the same list ``scripts/stripe_bootstrap.py``
  uses to adopt the live Stripe Product, so the two migrations cannot drift apart.
* a product whose display ``name`` slugifies to something other than its ``tier``
  contributes ``<slug> -> <tier>`` (this is what carried Phase 1's alias, when the catalog
  read ``tier: insider`` / ``name: Essential``).

``_STATIC_ALIASES`` is the floor, not a duplicate: this function runs inside request paths
and in stdlib-only contexts, so an unreadable catalog or a missing PyYAML must degrade to
the known alias rather than raise or return a wrong answer. A readable catalog OVERRULES
the floor in one direction only — any alias, static or derived, whose key is itself a
canonical tier is dropped. That is what keeps the floor safe to reverse: pointed at a
pre-flip catalog (where ``insider`` IS canonical) this table resolves ``insider`` to itself
rather than to a tier that catalog does not sell.
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path

log = logging.getLogger("macro.tiers")

ROOT = Path(os.environ.get("MACRO_REPO") or Path(__file__).resolve().parents[1])

#: The floor. Correct with no catalog, no PyYAML and no filesystem — a readable catalog can
#: only ADD to this or (see ``_derive_aliases``) drop an entry that its own canonical tiers
#: contradict; it can never shadow a canonical wire value.
_STATIC_ALIASES: dict[str, str] = {"insider": "essential"}

_SLUG_RE = re.compile(r"[^a-z0-9]+")

_ALIAS_CACHE: dict[str, str] | None = None


def _slug(name: object) -> str:
    """``"Essential"`` -> ``essential``; ``"Founding Pro"`` -> ``founding_pro``."""
    return _SLUG_RE.sub("_", str(name or "").strip().lower()).strip("_")


def _derive_aliases() -> dict[str, str]:
    """``{alias -> canonical tier}`` from the catalog, over the static floor.

    Sources, in order of application:

    * ``legacy_product_keys`` — every former ``products`` key becomes an alias of the
      current product's ``tier``. This is the rename's own record, shared with
      ``scripts/stripe_bootstrap.py``.
    * a product's display ``name``, slugified — so a pure display rename (a catalog whose
      ``tier`` has not moved yet) still resolves.

    Three rules keep a rename from ever becoming an entitlement bug:

    * an alias equal to its own tier is not an alias (no-op);
    * an alias that collides with ANY canonical tier (a product's ``tier``, or a member of
      ``tier_rank``) is dropped — naming a product "Pro" while it sells a different tier
      must not silently reroute ``pro`` requests. This sweep also covers ``_STATIC_ALIASES``,
      so pointing this module at a catalog that predates the rename resolves the old value
      to ITSELF instead of to a tier that catalog does not sell;
    * an alias whose target tier the catalog does not carry is dropped.
    """
    aliases = dict(_STATIC_ALIASES)
    try:
        import yaml  # noqa: PLC0415 — stdlib-only import paths must still work
        with (ROOT / "config" / "plans.yml").open() as fh:
            catalog = yaml.safe_load(fh) or {}
        products = dict(catalog.get("products") or {})
        canonical = {str(p.get("tier") or "").strip().lower() for p in products.values()}
        canonical.update(str(t).strip().lower() for t in (catalog.get("tier_rank") or []))
        canonical.discard("")
        for pkey, olds in (catalog.get("legacy_product_keys") or {}).items():
            tier = str((products.get(pkey) or {}).get("tier") or "").strip().lower()
            if not tier:
                continue
            for old in olds or []:
                alias = _slug(old)
                if not alias or alias == tier or alias in canonical:
                    continue
                aliases[alias] = tier
        for prod in products.values():
            tier = str(prod.get("tier") or "").strip().lower()
            alias = _slug(prod.get("name"))
            if not tier or not alias or alias == tier or alias in canonical:
                continue
            aliases[alias] = tier
        # The floor is a guess about the catalog; the catalog is the fact. Drop any alias
        # this catalog contradicts by SELLING that string, and any alias pointing at a tier
        # it does not carry at all.
        if canonical:
            aliases = {a: t for a, t in aliases.items()
                       if a not in canonical and t in canonical}
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
    what is ACCEPTED; it never decides what is VALID. ``normalize_tier('essential') ==
    'essential'``: canonical values are untouched.
    """
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    aliases = tier_aliases()
    if raw in aliases:
        return aliases[raw]
    return aliases.get(_slug(raw), raw)
