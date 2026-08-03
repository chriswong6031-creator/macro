"""W4f — the mastermind_news arming, and the config knobs W4a/W4d read.

WHAT THIS SUITE IS FOR. Arming a desk is a CONFIG act with a wide code blast
radius: seven modules resolve liveness through
``engine.marketing.accounts.effective_accounts`` and change behaviour the moment
one boolean moves. A config change with no test is a change nobody can refute, so
every claim the arming makes is pinned here against the SHIPPED
``config/marketing.yml`` — never a fixture. A fixture would prove that the code
can arm a desk; only the real file proves that THIS desk IS armed.

Five claims, in the order the masterplan §8.2 W4f gates state them:

  1. mastermind_news resolves ENABLED through the accounts model, with the
     legacy ``disabled`` key gone rather than flipped, so the two keys cannot
     disagree (``accounts._config_enabled`` lets ``enabled`` win, which is
     exactly how a stale ``disabled: true`` would read dark to a human and live
     to the code).
  2. It starts on the COLD ramp tier with the cold caps, and it gets there
     DELIBERATELY — ``created:`` present and parsed — not by ``resolve_ramp``
     failing closed, which produces the identical tier for the opposite reason.
  3. The wire classes route where the charter says: stance-free relay classes to
     the wire desk, house-view classes to the flagship.
  4. The W4a/W4d config knobs exist under the exact key paths those lanes read.
  5. hot_tape's overrides stay in config/hot_tape.yml — there is deliberately NO
     second home for them in marketing.yml.

DETERMINISM. Every ramp assertion is anchored to the desk's OWN ``created:``
date plus a fixed offset, never to the wall clock: a suite that asserts "cold
today" is a bomb that detonates on day 14 (see the fixture-date-plus-wall-clock
trap). Tier boundaries are asserted on BOTH sides so the cold window is pinned as
a window, not as a moment.
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent

ACCOUNT = "mastermind_news"

#: The classes the publication wire owns. Stance-free RELAY: an event happened,
#: we state it with its source. (masterplan §4 safety rails — "wire accounts
#: never take stances"; F6 2026-07-31 — sentence-case compression, never the
#: ALL-CAPS siren costume.)
WIRE_CLASSES = frozenset({"geopolitical", "company_news", "earnings", "none"})

#: The classes whose value to the reader IS the house read, so they stay on the
#: flagship: a macro print is only half a post without what it does to the path,
#: and `policy` carries both the attributive register (the fabricated
#: "White House, minutes ago:" dateline defect) and the `_no_market_nexus`
#: editorial judgment.
HOUSE_CLASSES = frozenset({"macro_print", "policy"})


@pytest.fixture(scope="module")
def cfg() -> dict:
    """The SHIPPED config, not a fixture — that is the whole point of the suite."""
    return yaml.safe_load((ROOT / "config" / "marketing.yml").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def acct(cfg) -> dict:
    """The resolved account row, through the same helper the publisher uses."""
    from engine.marketing.accounts import effective_accounts

    rows = {str(a.get("id")): a for a in effective_accounts(cfg, ROOT)}
    # Vacuous-green guard: a renamed/removed id would make every assertion below
    # pass against nothing.
    assert ACCOUNT in rows, (
        f"{ACCOUNT} has no desk_network entry — this suite would be asserting "
        f"nothing. Roster: {sorted(rows)}"
    )
    return rows[ACCOUNT]


def _raw_entry(cfg: dict) -> dict:
    """The account's RAW config dict (pre-resolution), for key-level assertions."""
    for row in ((cfg.get("desk_network") or {}).get("accounts") or []):
        if isinstance(row, dict) and str(row.get("id")) == ACCOUNT:
            return row
    pytest.fail(f"{ACCOUNT} missing from desk_network.accounts")


# ─────────────────────────────────────────────────────────────────────────────
# 1. ARMED — and armed unambiguously
# ─────────────────────────────────────────────────────────────────────────────

def test_the_wire_desk_resolves_enabled_through_the_accounts_model(acct):
    """The claim every other lane depends on. Resolved through
    ``effective_accounts`` rather than read off the YAML, because that is the
    read the publisher, the sentinel, wire_routing, hot_tape's liveness check and
    the admin roster all make — and because it also folds in
    data/marketing/account_overrides.json, which could still hold the desk dark
    with the config saying otherwise."""
    assert acct.get("enabled") is True, (
        f"{ACCOUNT} did not resolve enabled. If config says enabled: true, check "
        f"data/marketing/account_overrides.json — an override WINS over config."
    )


def test_the_wire_desk_is_live_not_merely_ready(cfg, acct):
    """`live` (enabled + a bound Buffer channel) is what makes the arming real;
    `ready` would mean an armed desk with nowhere to post."""
    from engine.marketing.accounts import account_status

    channels = ((cfg.get("publish") or {}).get("channels") or {})
    assert account_status(acct, channels) == "live", (
        f"{ACCOUNT} is not live — publish.channels.{ACCOUNT} is "
        f"{channels.get(ACCOUNT)!r}"
    )


def test_the_legacy_disabled_key_is_gone_not_flipped(cfg):
    """`enabled` OUTRANKS `disabled` in accounts._config_enabled, so the two keys
    are allowed to disagree — and a leftover `disabled: true` beside
    `enabled: true` resolves LIVE while reading DARK to every human who opens the
    file. The key's only account-level reader is accounts.py:54, where `enabled`
    wins, so deleting it costs nothing and removes the contradiction."""
    entry = _raw_entry(cfg)
    assert "disabled" not in entry, (
        f"{ACCOUNT} still carries a legacy `disabled: {entry.get('disabled')!r}` "
        f"next to `enabled: {entry.get('enabled')!r}`. accounts._config_enabled "
        f"lets `enabled` win, so this entry resolves ENABLED while reading dark."
    )


def test_the_wire_desk_is_registered_for_replies_and_registered_EMPTY(cfg):
    """The reply register must cover every live desk (a desk missing from it is
    indistinguishable from a desk whose curation was forgotten) — but the wire
    desk's entry must stay empty FOREVER, not "until someone curates it". A reply
    is our desk entering someone else's conversation with a view, which is a
    stance, which a wire account does not take. Its ramp says the same in
    numbers: max_replies_per_account_per_day is 0 at every tier."""
    import yaml as _yaml

    reg = _yaml.safe_load(
        (ROOT / "config" / "reply_targets.yml").read_text(encoding="utf-8"))
    block = (reg.get("accounts") or {}).get(ACCOUNT)
    assert block is not None, (
        f"{ACCOUNT} is live but has no config/reply_targets.yml block — "
        f"reply_desk's register-covers-every-live-desk guard will fail"
    )
    assert (block.get("authors") or []) == [], (
        f"{ACCOUNT} has reply targets: {block.get('authors')!r}. A wire account "
        f"relays and never takes a stance — adding handles here needs an "
        f"operator editorial ruling, not a builder's edit."
    )
    created = str(_raw_entry(cfg)["created"])[:10]
    assert _ramp_row(cfg, created)["caps"]["max_replies_per_account_per_day"] == 0


def test_the_wire_desk_has_no_persona_block(cfg):
    """A wire account RELAYS and never takes a stance. The absence of a
    copywriter.personas entry is the DESIGN, not an oversight — adding one to
    "give the desk a voice" is the editorializing the charter bans. Its register
    is the house wire voice (engine/marketing/wire_voice.py)."""
    personas = ((cfg.get("copywriter") or {}).get("personas") or {})
    assert ACCOUNT not in personas, (
        f"copywriter.personas.{ACCOUNT} exists — a wire desk must not carry a "
        f"desk persona (masterplan §4 safety rails). Its register is wire_voice."
    )


# ─────────────────────────────────────────────────────────────────────────────
# 2. COLD, AND DELIBERATELY SO
# ─────────────────────────────────────────────────────────────────────────────

def _ramp_row(cfg: dict, as_of: str) -> dict:
    from engine.marketing.sentinel import resolve_ramp

    report = resolve_ramp(cfg, as_of, root=ROOT, announce=False)
    assert report["enforced"] is True, "sentinel.ramp is absent — no tier binds"
    row = report["accounts"].get(ACCOUNT)
    assert row is not None, f"{ACCOUNT} absent from the resolved ramp"
    return row


def test_the_wire_desk_declares_its_created_date(cfg):
    """Without `created:` the tier still resolves to weeks_1_2 — by FAILING
    CLOSED, with a ::warning nobody reads. Same tier, opposite meaning: one is a
    decision, the other is a config defect wearing the decision's clothes. This
    asserts the decision."""
    entry = _raw_entry(cfg)
    raw = entry.get("created")
    assert raw, f"{ACCOUNT} has no `created:` — the cold tier would be fail-closed"
    parsed = date.fromisoformat(str(raw)[:10])   # raises on junk, which is the test
    assert parsed.year >= 2026


def test_the_cold_tier_is_resolved_not_failed_closed(cfg):
    """The mutation-sensitive half: `age_days` is an integer and the desk is NOT
    in `missing_created`. Delete the `created:` key and the tier assertion below
    still passes while THIS one goes red."""
    from engine.marketing.sentinel import resolve_ramp

    created = str(_raw_entry(cfg)["created"])[:10]
    report = resolve_ramp(cfg, created, root=ROOT, announce=False)
    assert ACCOUNT not in report["missing_created"], (
        f"{ACCOUNT} is enabled with no usable created date — resolve_ramp failed "
        f"closed to the strictest tier instead of resolving one"
    )
    row = report["accounts"][ACCOUNT]
    assert row["age_days"] == 0
    assert row["enabled"] is True


@pytest.mark.parametrize("offset,tier", [
    (0, "weeks_1_2"),      # arming day
    (4, "weeks_1_2"),      # last cold day — the window, not a moment
    (5, "weeks_3_4"),      # the boundary is asserted from BOTH sides
    (9, "weeks_3_4"),
    (10, "week_5_plus"),
    (20, "week_5_plus"),
    (21, "graduated"),
])
def test_the_ramp_walks_the_expected_tiers_from_the_created_date(cfg, offset, tier):
    """Anchored to the desk's OWN created date + a fixed offset, never to the
    wall clock — a suite that asserted "cold today" would go red on day 5.

    Re-pinned 2026-08-03 to the operator's relaxed schedule (tier boundaries 5/10,
    graduation 21; they were 14/28/56). The ramp is a PLATFORM-RISK throttle, not
    a quality gate, so how fast a new desk walks it is an operator dial — what
    this parametrisation defends is that the desk walks the ladder the config
    declares, from BOTH sides of every boundary.
    """
    created = date.fromisoformat(str(_raw_entry(cfg)["created"])[:10])
    row = _ramp_row(cfg, (created + timedelta(days=offset)).isoformat())
    assert row["tier"] == tier, (
        f"day {offset} after created resolved {row['tier']}, expected {tier}"
    )


def test_the_cold_caps_are_the_weeks_1_2_contract(cfg):
    """A brand-new posting account RAMPS. These are the numbers the first tier
    carries after the 2026-08-03 relaxation: 14 posts/day (was 10), a 30-minute
    floor, 2 cashtags/post, no links, no replies — and theme_list ALLOWED.

    The theme_list ban was the one knob the relaxation reversed outright: it read
    as a piggybacking guard (>=4 member cashtags on an account with no history)
    and behaved as a total volume kill, because a new desk's only planned at-bat
    was routinely that format (masterplan §8.1 V2 — kelly, zero posts ever).
    Links stay shut on the first tier on purpose: an outbound link from a
    days-old account is the strongest spam signal on the platform, and it now
    opens on day 5 rather than day 28.
    """
    created = str(_raw_entry(cfg)["created"])[:10]
    caps = _ramp_row(cfg, created)["caps"]
    assert caps["max_posts_per_account_per_day"] == 14
    assert caps["max_media_posts_per_account_per_day"] == 14
    assert caps["min_minutes_between_posts"] == 30
    assert caps["max_cashtags_per_post"] == 2
    assert caps["theme_list_allowed"] is True
    assert caps["links_allowed"] is False
    assert caps["max_replies_per_account_per_day"] == 0


def test_the_wire_desk_does_not_open_on_the_flagship_override(cfg):
    """The flagship's 20/day account_override is per-desk and named; a wire desk
    arriving with zero posting history must not inherit it."""
    overrides = (((cfg.get("sentinel") or {}).get("ramp") or {})
                 .get("account_overrides") or {})
    assert ACCOUNT not in overrides, (
        f"{ACCOUNT} carries a ramp account_override ({overrides.get(ACCOUNT)!r}) "
        f"— overrides may LOOSEN, so this would let a cold desk skip the ramp"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 3. ROUTING — relay classes to the wire, house-view classes to the flagship
# ─────────────────────────────────────────────────────────────────────────────

def test_the_relay_classes_resolve_to_the_wire_desk(cfg):
    """Through ``wire_routing.route``, which resolves LIVENESS as well as intent —
    a class pointed at a dark desk silently falls back to the default, so this
    also re-proves the arming end-to-end."""
    from engine.marketing import wire_routing as wr

    for klass in sorted(WIRE_CLASSES):
        assert wr.route(klass, cfg=cfg, root=ROOT) == ACCOUNT, (
            f"event_class {klass!r} did not route to {ACCOUNT}. If it fell back "
            f"to flagship, the desk is not enabled (liveness is not routing)."
        )


def test_the_house_view_classes_stay_on_the_flagship(cfg):
    """The inverse scan — a one-directional routing assertion leaves the quiet
    half open. macro_print and policy must NOT have moved."""
    from engine.marketing import wire_routing as wr

    for klass in sorted(HOUSE_CLASSES):
        assert wr.route(klass, cfg=cfg, root=ROOT) == "flagship", (
            f"event_class {klass!r} routes to "
            f"{wr.route(klass, cfg=cfg, root=ROOT)!r}; the house-read classes "
            f"belong to the desk that owns a view"
        )


def test_the_routing_table_partitions_the_known_classes(cfg):
    """No class is unowned, none is owned twice, and the union is exactly the
    taxonomy press_lane renders. A class that quietly disappeared from the map
    would fall back to the default and nothing would say so."""
    from engine.marketing import wire_routing as wr

    table = wr.routing_table(cfg, root=ROOT)
    assert set(table) == WIRE_CLASSES | HOUSE_CLASSES
    assert {k for k, v in table.items() if v == ACCOUNT} == WIRE_CLASSES
    assert {k for k, v in table.items() if v == "flagship"} == HOUSE_CLASSES


def test_the_flagship_remains_the_default_owner(cfg):
    """Two consequences ride on `default`, and both are easy to break by moving
    `none` to the wire desk: an UNMAPPED class falls back to it, and
    desk_feed.py reads `wire_routing.default == account` as that account owning
    the "none" beat — a desk with zero routed classes abstains from the whole
    breaking lane (`no_wire_routing`)."""
    from engine.marketing import wire_routing as wr

    assert wr.default_account(cfg) == "flagship"
    assert wr.route("a_class_that_does_not_exist", cfg=cfg, root=ROOT) == "flagship"


def test_the_spill_pool_is_the_two_wire_desks_and_no_persona(cfg):
    """W4d spills a desk's surplus wire budget to another WIRE desk. A persona
    desk in that pool would receive a raw press relay in an authored voice — a
    charter violation dressed up as a volume fix."""
    from engine.marketing import wire_routing as wr

    pool = wr.spill_pool(cfg, root=ROOT)
    assert pool == ["flagship", ACCOUNT], f"spill pool is {pool!r}"


# ─────────────────────────────────────────────────────────────────────────────
# 4. THE KNOBS THE OTHER LANES READ — exact key paths
# ─────────────────────────────────────────────────────────────────────────────

def test_the_ladder_shape_knobs_are_present_under_their_documented_paths(cfg):
    """``content_plan.forward_days`` / ``content_plan.per_day_headroom`` (W4a).
    The names are a cross-lane contract: content_studio ships code defaults, so a
    typo here is silent — the ladder simply keeps its old shape and nothing
    fails."""
    block = cfg.get("content_plan")
    assert isinstance(block, dict), "config/marketing.yml has no `content_plan:` block"
    assert block["forward_days"] == 1, (
        "forward_days must be 1: outbox.emit_from_content_plan takes only D1- "
        "slots and nothing reads a previous plan, so D2..D7 are discarded by "
        "construction (measured 2026-08-02: 154 planned, 5 on D1)"
    )
    headroom = block["per_day_headroom"]
    assert isinstance(headroom, (int, float)) and headroom >= 1.0
    assert headroom == 2.0


def test_the_press_wire_headroom_knob_is_present_and_outranks_the_other_home(cfg):
    """``breaking.flagship_top_k_per_day`` (W4d) — a VOLUME cap, not a threshold.

    TWO HOMES, ONE ORDER. press_sources.yml `wire.flagship_top_k_per_day` is the
    historical home; press_lane._resolve_top_k prefers THIS key. The higher-
    precedence home must never be the LOWER number, or adding it would quietly
    throttle the lane it was added to widen — so the relation is asserted, not
    just the value. (The two agree today; the assertion is what keeps them from
    silently diverging in the wrong direction.)
    """
    breaking = cfg.get("breaking") or {}
    top_k = breaking.get("flagship_top_k_per_day")
    assert isinstance(top_k, int), (
        "breaking.flagship_top_k_per_day missing or not an int — press_lane would "
        "fall through to press_sources.yml wire.flagship_top_k_per_day"
    )
    assert top_k == 10

    press = yaml.safe_load(
        (ROOT / "config" / "press_sources.yml").read_text(encoding="utf-8"))
    legacy = (press.get("wire") or {}).get("flagship_top_k_per_day")
    if legacy is not None:
        assert top_k >= int(legacy), (
            f"marketing.yml {top_k} < press_sources.yml {legacy}: the higher-"
            f"precedence home would LOWER the cap it was added to raise"
        )


def test_no_quality_threshold_moved_with_the_volume_caps(cfg):
    """The §8.0 gate, asserted rather than asserted-about. A volume cap may move;
    a threshold may not. These are the numbers the W4 wave was forbidden to
    touch, pinned beside the caps that did move so a future retune has to argue
    with a test."""
    assert (cfg.get("breaking") or {})["salience_threshold"] == 60
    assert (cfg.get("sentinel") or {})["near_dup_jaccard"] == 0.50
    assert (cfg.get("sentinel") or {})["frame_similarity"] == 0.60

    press = yaml.safe_load(
        (ROOT / "config" / "press_sources.yml").read_text(encoding="utf-8"))
    assert (press.get("wire") or {})["flagship_salience_floor"] == 30.0


def test_the_config_knobs_reach_their_readers(cfg):
    """The other half of a config contract: a key nothing reads is decoration.

    This is the ONE assertion in the suite that couples to another lane's code.
    That is deliberate — the coupling is one-directional (the readers ship code
    defaults and work without the keys; the KEYS are useless without the
    readers), so if a reader has not landed this must be RED and say which lane
    is missing, not skip and read green.
    """
    from engine.marketing import content_studio as cs
    from engine.marketing import press_lane as pl

    assert hasattr(cs, "forward_days") and hasattr(cs, "per_day_headroom"), (
        "engine.marketing.content_studio has no forward_days/per_day_headroom "
        "reader — the W4a lane has not landed, so content_plan.* is decoration"
    )
    assert cs.forward_days(cfg) == 1
    assert cs.per_day_headroom(cfg) == 2.0

    resolve = getattr(pl, "_resolve_top_k", None)
    assert resolve is not None, (
        "engine.marketing.press_lane has no _resolve_top_k — the W4d lane has "
        "not landed, so breaking.flagship_top_k_per_day is decoration and "
        "press_sources.yml's 3 still governs"
    )
    press = yaml.safe_load(
        (ROOT / "config" / "press_sources.yml").read_text(encoding="utf-8"))
    assert resolve(cfg.get("breaking"), press.get("wire")) == 10, (
        "marketing.yml must OUTRANK press_sources.yml for this key"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 5. hot_tape has ONE config home, and it is not this file
# ─────────────────────────────────────────────────────────────────────────────

def test_hot_tape_overrides_live_in_their_own_file_not_in_marketing_yml(cfg):
    """W4f asked for a `hot_tape:` block in marketing.yml "if the wire lane needs
    its DEFAULTS overridable". It does not: hot_tape.load_config deep-merges
    config/hot_tape.yml OVER hot_tape.DEFAULTS, and that file already overrides
    the emit block. A second home in marketing.yml would be a split brain — two
    files, one namespace, and a reader that consults only one of them.

    Pinned in BOTH directions: no block here, and the real home still carries the
    keys the wire lane depends on.
    """
    assert "hot_tape" not in cfg, (
        "config/marketing.yml grew a `hot_tape:` block. hot_tape.load_config "
        "reads config/hot_tape.yml ONLY (CONFIG_REL), so this block would be "
        "read by nothing while looking authoritative. Put the override in "
        "config/hot_tape.yml."
    )
    ht_path = ROOT / "config" / "hot_tape.yml"
    assert ht_path.exists(), "config/hot_tape.yml is the override home and is gone"
    ht = yaml.safe_load(ht_path.read_text(encoding="utf-8")) or {}
    emit = ht.get("emit") or {}
    assert emit.get("account") == ACCOUNT, (
        f"hot_tape emit.account is {emit.get('account')!r}; the wire desk owns "
        f"sub-{emit.get('flagship_severity_floor')}-severity events"
    )
    # The arming's real volume consequence, named where someone will find it:
    # hot_tape items ship scheduled_at="immediate" and immediate items are EXEMPT
    # from the per-account daily cap, so THIS number — not the weeks_1_2 tier —
    # is what bounds the newly-armed desk's hot-tape volume.
    assert isinstance(emit.get("max_per_day"), int)
