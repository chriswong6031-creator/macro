"""lib/chat_allowance.py — the ONE place a chat allowance becomes customer-facing copy.

MNZ-R13 (`research/MASTERMIND_COMMERCIAL_ARCHITECTURE.md` §7): **every customer-facing
quantitative claim about an entitlement must be derived from the config that enforces
it.** Prices have obeyed that rule since W4 — `scripts/build_site._plans_view_model`
reads `config/plans.yml` and the savings badges recompute themselves. Chat allowances
did not: `templates/plans.html.j2` hand-typed "5 quick questions a week", "300 a
month", "unlimited", "150 a month" and four more matrix cells, while
`config/brain.yml` is what `engine.neuralweb.brain_gateway._get_allowance` actually
enforces.

The literals happen to be CORRECT today (verified 2026-08-12 — including "Unlimited",
which is the honest rendering of `quotas.pro.fast.limit: -1`, the uncapped sentinel set
by operator ruling 2026-07-28). That is exactly why this is worth closing now rather
than after an incident: nothing binds them. Reprice the Pro fast lane to 2000 tomorrow
and the pricing page keeps promising "unlimited", silently, with no test to catch it —
the same shape as the drift the price-derivation rule was written to prevent.

A pricing page that promises more than the serving spine will grant is the same class
of defect as a signal we cannot defend — it is just aimed at the wallet instead of the
portfolio. This module makes the promise and the enforcement read the same file.

WHY ``lib/``
------------
Both plans builders need it (`scripts/build_site.py` and `scripts/build_public_pages.py`,
which render the SAME template from two entry points), and `lib/` is the layer they
already share — the same reasoning that put `lib/tiers.py` there.

LANE NAMING
-----------
`config/brain.yml` names the lanes ``fast`` and ``pro``. The customer-facing name for
the ``pro`` lane is "Deep Opus chat", and the word "pro" already means a TIER on every
commercial surface, so this module re-keys it to ``deep``. That rename is contained
here: nothing downstream has to know the config's lane vocabulary.

FAIL LOUD, NOT SILENT
---------------------
A missing or malformed quota block raises, exactly as `_plans_view_model` raises on a
missing `config/plans.yml`. This runs at BUILD time over committed config, never in a
request path — a silent fallback here would re-introduce the very drift the module
exists to close, and would do it invisibly.
"""
from __future__ import annotations

from pathlib import Path

import yaml

#: Tiers that appear on a pricing surface, in ladder order. ``trial`` is a STATUS in
#: `brain_gateway` (status='trialing' selects it regardless of tier name), not a
#: purchasable product, so it is deliberately absent — a plans page that advertised a
#: "trial tier" would be describing something the catalog does not sell.
DISPLAY_TIERS = ("free", "essential", "pro")

#: config lane key -> customer-facing lane key (see LANE NAMING above).
_LANE_KEYS = {"fast": "fast", "pro": "deep"}


def _brain_config_path(root: Path | None = None) -> Path:
    base = root or Path(__file__).resolve().parents[1]
    return base / "config" / "brain.yml"


def chat_allowance_view_model(root: Path | None = None) -> dict[str, dict[str, dict]]:
    """Return ``{tier: {lane: {"limit", "period", "uncapped", "none"}}}`` per display tier.

    ``lane`` is ``fast`` | ``deep``; ``period`` is whatever `config/brain.yml` carries
    (``week`` | ``month``), passed through unchanged so the template renders the same
    word the quota resets on.

    Two boolean flags carry the sentinels so no template ever has to know what a
    negative number means — and so the two ends of the ladder cannot be confused:

    * ``uncapped`` — ``limit < 0``. `brain_gateway._get_allowance` documents this as
      "uncapped requests for that lane"; `config/brain.yml` sets it on
      ``quotas.pro.fast`` per the operator ruling of 2026-07-28 ("Pro Flash is
      Unlimited"). Renders as "Unlimited". The `token_ceilings` fair-use backstop
      still applies and is deliberately NOT advertised — it is a fair-use limit, not
      an allowance.
    * ``none`` — ``limit == 0``: the lane is not included at this tier at all
      (``quotas.free.pro``). Renders as ✗, never as "0 a month".

    Raises ``ValueError`` when a display tier or a lane is missing from the config, so
    a quota block that is deleted or renamed reds CI instead of silently rendering a
    stale literal.
    """
    path = _brain_config_path(root)
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    quotas = raw.get("quotas")
    if not isinstance(quotas, dict):
        raise ValueError(f"{path}: missing `quotas` block")

    out: dict[str, dict[str, dict]] = {}
    for tier in DISPLAY_TIERS:
        bucket = quotas.get(tier)
        if not isinstance(bucket, dict):
            raise ValueError(f"{path}: quotas.{tier} missing or not a mapping")
        lanes: dict[str, dict] = {}
        for cfg_lane, display_lane in _LANE_KEYS.items():
            spec = bucket.get(cfg_lane)
            if not isinstance(spec, dict) or "limit" not in spec:
                raise ValueError(f"{path}: quotas.{tier}.{cfg_lane}.limit missing")
            try:
                limit = int(spec["limit"])
            except (TypeError, ValueError) as exc:
                # `limit:` with no value parses as YAML null, and a bare int() would raise
                # TypeError — outside the ValueError contract this module documents and the
                # callers catch. Normalize it so every malformed-config path exits the same
                # way, whether the key is missing, null, or a string.
                raise ValueError(
                    f"{path}: quotas.{tier}.{cfg_lane}.limit is not an integer "
                    f"({spec['limit']!r})"
                ) from exc
            lanes[display_lane] = {
                "limit": limit,
                "period": str(spec.get("period", "month")),
                "uncapped": limit < 0,
                "none": limit == 0,
            }
        out[tier] = lanes
    return out
