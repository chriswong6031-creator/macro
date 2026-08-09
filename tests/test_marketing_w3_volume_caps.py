"""tests/test_marketing_w3_volume_caps.py — the 2026-08-08 volume order, end to end.

THE ORDER. "20-30 posts per account per day", across all seven live desks. That
is one sentence and FIVE layers had to agree with it, because a cap in this
system is never one number:

    sentinel base block  ->  ramp tier row  ->  per-account override
                                    |
                                    +--> outbox.effective_cap_for   (post time)
                                    +--> content_studio.ladder_shape_for (plan time)
                                    +--> config/personas/<id>.yml cadence (the AND at post time)

WHY THIS SUITE EXISTS AND NOT JUST THE COHERENCE ONE.
tests/test_marketing_cadence_ramp_coherence.py already pins the RELATIONS between
those layers (the spec must never be the throttle, the spacing must fit the
ladder, the session fence must not be the real cap). It is deliberately written
in terms of "whatever the config says", so it stays green when every layer agrees
on the WRONG number. This suite pins the number itself, once, against the
committed config: if somebody lowers an override, drops a desk's row, or raises a
base cap that silently pins the tiers, exactly one of these fails and says which
layer moved.

THE TRAP THIS SUITE IS SHAPED AROUND. `sentinel.resolve_ramp` ignores an override
key that is not already present in the base cap dict:

    if cap_key not in caps:
        continue  # unknown knob: ignore rather than invent a cap

so an override written as `max_posts_per_day` (the shorthand everybody says out
loud) instead of `max_posts_per_account_per_day` (the knob) is accepted by YAML,
accepted by the loader, announced nowhere, and does nothing at all. The assertions
below read the RESOLVED caps rather than the config text, which is the only way to
see that difference.

CONVENTIONS. Reads the committed config only; no wall clock (the plan date is
pinned), no network, no writes.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent

#: Operator order 2026-08-08. The band is 20-30; the CAP is the top of it, and a
#: cap below 30 means some desk cannot reach the band's ceiling on a busy day.
OPERATOR_POSTS_PER_DAY = 30
#: The per-account spacing floor that ships with it.
OPERATOR_MIN_SPACING_MIN = 20
#: A plan date inside the current tier geometry, pinned so this suite cannot
#: start passing or failing because a desk aged overnight.
AS_OF = "2026-08-09"

#: The seven desks the operator named. Written out rather than derived from
#: `enabled` so that ENABLING AN EIGHTH DESK IS A DELIBERATE EDIT HERE: a new
#: desk with no override row would otherwise join the network silently at its
#: tier cap and this suite would keep passing.
LIVE_DESKS = ("flagship", "founder", "meagan", "sophia", "kelly", "cici",
              "mastermind_news")


@pytest.fixture(scope="module")
def cfg() -> dict:
    return yaml.safe_load((ROOT / "config" / "marketing.yml").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def ramp(cfg) -> dict:
    from engine.marketing.sentinel import resolve_ramp

    return resolve_ramp(cfg, AS_OF, root=ROOT, announce=False)


def test_the_live_roster_is_exactly_the_seven_desks_this_suite_names(cfg):
    """Vacuous-green guard. Every assertion below loops over LIVE_DESKS, so a
    roster that drifted away from it would leave this suite asserting about
    desks nobody runs while saying nothing about the ones we do."""
    from engine.marketing.accounts import effective_accounts

    enabled = {str(a.get("id")) for a in effective_accounts(cfg, ROOT) if a.get("enabled")}
    assert enabled == set(LIVE_DESKS), (
        f"the live roster moved: enabled={sorted(enabled)}, this suite pins "
        f"{sorted(LIVE_DESKS)}. Add the new desk's sentinel.ramp.account_overrides "
        f"row and its persona cadence block, then add it here."
    )


@pytest.mark.parametrize("acct_id", LIVE_DESKS)
def test_every_live_desk_resolves_to_the_operator_cap(ramp, acct_id):
    """Layer 1+2+3: base -> tier -> override, as the sentinel actually merges them."""
    entry = ramp["accounts"][acct_id]
    caps = entry["caps"]
    assert caps["max_posts_per_account_per_day"] == OPERATOR_POSTS_PER_DAY, (
        f"{acct_id} ({entry['tier']}, age {entry['age_days']}d) resolves to "
        f"{caps['max_posts_per_account_per_day']} posts/day, not "
        f"{OPERATOR_POSTS_PER_DAY}"
    )
    # Media and volume "must move together" (the base block says so): a media cap
    # under the post cap does not strip the image, it QUARANTINES the post as
    # media_cap_daily, and every ticker post carries a chart.
    assert caps["max_media_posts_per_account_per_day"] == OPERATOR_POSTS_PER_DAY, (
        f"{acct_id} media cap {caps['max_media_posts_per_account_per_day']} != "
        f"post cap {OPERATOR_POSTS_PER_DAY} — chart posts would quarantine"
    )
    assert caps["min_minutes_between_posts"] == OPERATOR_MIN_SPACING_MIN
    # The override must be the thing doing it, not an accident of the tier row.
    # `overrides` is what resolve_ramp actually APPLIED, so a key the merge
    # silently dropped (wrong knob name) is absent here even though the YAML has it.
    assert entry["overrides"].get("max_posts_per_account_per_day") == OPERATOR_POSTS_PER_DAY, (
        f"{acct_id}: the cap is right but no account_overrides row produced it — "
        f"applied overrides were {entry['overrides']}"
    )


@pytest.mark.parametrize("acct_id", LIVE_DESKS)
def test_the_post_time_seam_agrees_with_the_plan_time_seam(cfg, ramp, acct_id):
    """Layer 4: outbox.effective_cap_for is what the publisher, the actuator and
    the admin all read. It takes the stricter of (base, tier), so a base cap that
    is NOT unlimited would pin every override here while the gate report above
    still showed 30."""
    from engine.marketing.outbox import effective_cap_for

    assert effective_cap_for(cfg, acct_id, AS_OF, root=ROOT,
                             ramp=ramp) == OPERATOR_POSTS_PER_DAY


def test_no_base_cap_silently_pins_the_overrides(cfg, ramp):
    """The merge is stricter-of(base, tier) BEFORE the override is applied, and
    -1 is the loosest value. A base `max_posts_per_account_per_day` of, say, 20
    would leave every override reading 30 in the YAML and 20 in the resolution.

    `max_same_cashtag_per_account_per_day` is checked separately and is NOT
    required to be unlimited: it bounds posts naming the SAME cashtag, so it is
    only a volume pin if a desk posts the same ticker more than that many times
    in a day, which the allocator's one-ticker-one-account rule prevents. It is
    asserted here only to keep it from being lowered to 1 again (it was 1 until
    2026-07-28, at which point it WAS the binding limit the moment volume rose).
    """
    base = ramp["base"]
    for key in ("max_posts_per_account_per_day", "max_media_posts_per_account_per_day"):
        assert base[key] is None, (
            f"sentinel.{key} is {base[key]!r}, not unlimited — it is the stricter "
            f"half of every tier merge, so it pins all seven overrides"
        )
    assert base["max_same_cashtag_per_account_per_day"] >= 3


@pytest.mark.parametrize("acct_id", LIVE_DESKS)
def test_the_selection_layer_offers_at_least_twenty_rungs_per_account(cfg, ramp, acct_id):
    """Layer 5: the nightly ladder has to OFFER enough rungs for the cap to mean
    anything. `ladder_shape_for` sizes a desk's day as
    min(28-rung ladder, ceil(cap x content_plan.per_day_headroom)), so the cap
    raise only reaches the plan through this function.

    The ceiling here is the 28-rung ladder, NOT the 30/day cap: with headroom 2.0
    a 30/day desk asks for 60 rungs and gets the ladder's 28. That is stated
    rather than asserted around — 28 clears the operator's 20 floor, and lifting
    it further is a ladder change (outbox._LADDER_N_SLOTS), not a config one.
    """
    from engine.marketing.content_studio import ladder_shape_for

    shape = ladder_shape_for(cfg, acct_id, AS_OF, root=ROOT, ramp=ramp)
    assert shape["per_day"] >= 20, (
        f"{acct_id}: the plan offers {shape['per_day']} rungs/day, under the "
        f"operator's 20 floor"
    )


def test_the_wire_desk_emission_cap_moved_with_the_post_cap(cfg):
    """The press wire's per-desk daily ceiling. It is deliberately BELOW a desk's
    own ramp cap so the wire cannot eat a desk's whole day, and it has two homes
    with marketing.yml outranking press_sources.yml. Both are pinned so a raise in
    one home cannot leave a throttle in the other."""
    marketing_k = int((cfg.get("breaking") or {}).get("flagship_top_k_per_day"))
    press = yaml.safe_load((ROOT / "config" / "press_sources.yml").read_text(encoding="utf-8"))
    press_k = int((press.get("wire") or {}).get("flagship_top_k_per_day"))
    assert marketing_k == 20
    assert marketing_k >= press_k, (
        "marketing.yml outranks press_sources.yml, so a LOWER value here is the "
        "higher-precedence home throttling the lane it was raised to widen"
    )
    assert marketing_k < OPERATOR_POSTS_PER_DAY, (
        "the wire may not be able to spend a desk's entire daily allowance — the "
        "nightly ladder and the publish-time lanes draw from the same number"
    )


def test_the_macro_fanout_budget_never_widens_the_signal_or_ratio_families(cfg):
    """The fan-out budget is per fact-key FAMILY. `default` covers `ratio:` (the
    breadth reads the whole gate was built for) and every directional signal, and
    it must stay at one owner, one post — the operator's order was about
    tickerless MACRO events, and a budget that leaked into the default would
    re-open defect class C."""
    from engine.marketing.market_clock import MACRO_KEY_PREFIX

    table = (cfg.get("publish") or {}).get("fact_fanout_max_accounts") or {}
    assert table.get("default") == 1
    assert table.get(MACRO_KEY_PREFIX.rstrip(":")) == 4
    assert table.get("pct") == 2
    assert "ratio" not in table, (
        "a `ratio` row here would widen the exact family the fact-anchor gate "
        "exists for; it must fall through to `default`"
    )
