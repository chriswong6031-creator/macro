"""tests/test_marketing_desk_feeds.py — XG-W3 desk feeds + franchises + memory.

The six gates this wave has to hold, and the sections that hold them:

  1. Each live account's desk feed produces candidates from ALL FOUR lanes with
     context attached — one fixture per lane (§2).
  2. Franchise slots emit on their declared cadence on a FIXTURE CLOCK, and an
     empty slot abstains with a logged §16.5 reason (§1).
  3. Every emission carries its Gift-Grip-Proof verdict in metadata, and the
     live desks' existing deterministic posts STILL PASS — the regression that
     proves the gate did not silently silence flagship and founder (§3).
  4. Phrase-fatigue counters enforce the XG-W1 per-quirk caps across a rolling
     window: a SECOND signature opener in one day is rejected (§4).
  5. Persona memory writes intraday ONLY under host state, and the consolidator
     is the only writer of `data/marketing/personas/` — an AST guard modelled on
     XG-W2's hand-rolled-writer guard, so a RENAMED writer fails too (§5).
  6. The measured-input rule, the copy-safe-name rule, and the
     LLM-may-only-de-escalate rule (§6, §7, §8).

CONVENTIONS. tmp_path for all I/O, an injected `now` everywhere (no wall clock
in any assertion path), zero network. Import closure is stdlib + pyyaml so the
suite runs in full in the marketing-engine lane — nothing here is
importorskip-gated, so it can never decay into a skip-only suite.
"""
from __future__ import annotations

import ast
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# A Wednesday. 13:00 UTC = 09:00 America/New_York = 21:00 Asia/Hong_Kong.
_WED_0900_ET = datetime(2026, 7, 22, 13, 0, 0, tzinfo=timezone.utc)
# 04:00 UTC = 12:00 Hong Kong — inside Cici's cash-session window.
_WED_HK_CASH = datetime(2026, 7, 22, 4, 0, 0, tzinfo=timezone.utc)
# 22:00 UTC = 06:00 Thursday in Hong Kong — outside both her windows. 06:00
# rather than 02:00 since 2026-07-28: her evening leg runs to 05:00 HK so it
# covers the whole US cash session, and 02:00 HK is inside it.
_WED_HK_ASLEEP = datetime(2026, 7, 22, 22, 0, 0, tzinfo=timezone.utc)

_CFG = {
    "wire_routing": {"default": "flagship", "classes": {"macro_print": "flagship"}},
    "story_lock": {"enabled": True, "window_minutes": 720},
}


def _breaking_item(**over):
    item = {
        "id": "b1",
        "headline": "CPI comes in hotter than expected",
        "event_class": "macro_print",
        "salience": 80.0,
        "url": "https://example.invalid/cpi",
        "source_name": "Wire",
        "source_tier": "wire",
        "published_at": "2026-07-22T12:55:00Z",
    }
    item.update(over)
    return item


# ═════════════════════════════════════════════════════════════════════════════
# §1 Franchise register + scheduler — windows, not quotas
# ═════════════════════════════════════════════════════════════════════════════
def test_register_is_non_empty_and_every_account_has_a_spec():
    from engine.marketing import franchises as fr

    reg = fr.register()
    assert reg, "the franchise register is empty"
    # The six live accounts of charter §1 that this wave schedules for.
    accounts = {f.account for f in reg}
    for expected in ("cici", "meagan", "sophia", "kelly", "flagship", "founder"):
        assert expected in accounts, f"no franchise registered for {expected}"


def test_spec_drift_is_clean():
    """THE DRIFT GATE. The code register and the committed persona specs agree.

    Every employee spec's `franchises:` prose line must have a register entry,
    every kind must be an admitted content kind, every window must parse, and no
    franchise window may fall wholly outside its account's own session clock.
    """
    from engine.marketing import franchises as fr

    assert fr.spec_drift() == []


def test_spec_drift_is_not_vacuous():
    """A green drift check must be EARNED, not an artefact of a misread API.

    This guard exists because the first cut of `spec_drift()` read
    `personas.load_all()` as a list of dicts when it returns
    `dict[str, PersonaSpec]`. Iterating a mapping yields id strings, every
    attribute lookup missed, the employee loop never executed — and the check
    reported a clean `[]` while testing nothing at all. Perturbing the register
    must produce a complaint, or the green above means nothing.
    """
    from engine.marketing import franchises as fr

    original = fr._RAW_REGISTER
    try:
        # (a) a spec franchise with no register entry must be reported
        fr._RAW_REGISTER = tuple(r for r in original if r["id"] != "cici_lost_in_translation")
        fr.clear_cache()
        missing = fr.spec_drift()
        assert any("Lost in Translation" in d for d in missing), (
            "removing a register entry produced no drift — the check is vacuous"
        )

        # (b) an unadmitted kind must be reported
        fr._RAW_REGISTER = tuple(
            dict(r, kind="not_a_kind") if r["id"] == "kelly_chart_detective" else r
            for r in original
        )
        fr.clear_cache()
        assert any("not_a_kind" in d for d in fr.spec_drift())

        # (c) an account with no committed spec must be reported
        fr._RAW_REGISTER = original + (
            {
                "id": "ghost_franchise",
                "account": "ghost_desk",
                "display_name": "Ghost",
                "kind": "macro",
                "classification": "analysis",
                "cadence": "daily",
                "contract": ("x",),
            },
        )
        fr.clear_cache()
        assert any("ghost_desk" in d for d in fr.spec_drift())
    finally:
        fr._RAW_REGISTER = original
        fr.clear_cache()

    assert fr.spec_drift() == [], "the register did not restore cleanly"


def test_franchise_kinds_are_existing_kinds_only():
    """NO NEW KINDS. A franchise maps onto a kind the outbox already admits."""
    from engine.marketing import franchises as fr
    from engine.marketing.outbox import KINDS

    for f in fr.register():
        assert f.kind in KINDS, f"{f.id}: kind {f.kind!r} is not in outbox.KINDS"


def test_cici_pre_open_franchise_opens_in_her_cash_session_only():
    """§4's anchor example: "Before New York Wakes", pre-open ET daily.

    Declared on HER clock (Asia/Hong_Kong cash session), which is the same
    window her spec's `cadence.session` gives the resolver.
    """
    from engine.marketing import franchises as fr

    ids = {s.franchise_id for s in fr.open_slots("cici", now=_WED_HK_CASH)}
    assert "cici_before_new_york_wakes" in ids

    # Her evening leg belongs to the other franchise, not this one.
    evening = {s.franchise_id for s in fr.open_slots("cici", now=_WED_0900_ET)}
    assert "cici_asia_close_readthrough" in evening
    assert "cici_before_new_york_wakes" not in evening

    # And while Hong Kong sleeps, nothing of hers is open at all.
    assert fr.open_slots("cici", now=_WED_HK_ASLEEP) == []


def test_daily_franchise_closes_after_one_use_that_day():
    """A daily slot is a WINDOW that closes once spent — not a quota to refill."""
    from engine.marketing import franchises as fr

    fid = "cici_before_new_york_wakes"
    assert fid in {s.franchise_id for s in fr.open_slots("cici", now=_WED_HK_CASH)}

    history = [(_WED_HK_CASH - timedelta(minutes=30), fid)]
    after = {s.franchise_id for s in fr.open_slots("cici", now=_WED_HK_CASH, history=history)}
    assert fid not in after, "a daily franchise re-opened the same day"

    # Tomorrow it is open again.
    tomorrow = _WED_HK_CASH + timedelta(days=1)
    assert fid in {s.franchise_id for s in fr.open_slots("cici", now=tomorrow, history=history)}


def test_franchise_history_is_derived_from_outbox_items():
    """THE PRODUCER. The franchise id round-trips through item metadata.

    Without an in-repo producer for `franchise_history`, every daily slot would
    look permanently unspent and the "windows, not quotas" discipline would
    quietly become "unlimited". The id travels in `source.franchise`, the same
    metadata slot the story key uses.
    """
    from engine.marketing import franchises as fr
    from engine.marketing import outbox

    fid = "cici_before_new_york_wakes"
    item = outbox.make_item(
        account="cici", kind="macro", text="While New York slept, HK closed green.",
        as_of="2026-07-22", provenance="test",
        source={"franchise": fid}, now=_WED_HK_CASH - timedelta(minutes=20),
    )
    assert fr.item_franchise_id(item) == fid

    history = fr.history_from_items([item], account="cici")
    assert history and history[0][1] == fid
    # Another account's item must not spend cici's slot.
    assert fr.history_from_items([item], account="kelly") == []

    # And the derived history closes the slot.
    assert fid not in {s.franchise_id for s in fr.open_slots("cici", now=_WED_HK_CASH, history=history)}


def test_feed_derives_franchise_history_from_the_outbox_it_was_given():
    from engine.marketing import desk_feed, outbox

    fid = "cici_before_new_york_wakes"
    spent = outbox.make_item(
        account="cici", kind="macro", text="While New York slept, HK closed green.",
        as_of="2026-07-22", provenance="test",
        source={"franchise": fid}, now=_WED_HK_CASH - timedelta(minutes=20),
    )
    feed = desk_feed.assemble("cici", now=_WED_HK_CASH, cfg=_CFG, outbox_items=[spent])
    assert fid not in {c.franchise_id for c in feed.by_lane("scheduled")}, (
        "the feed re-opened a franchise the desk already spent today"
    )


def test_undateable_item_does_not_spend_a_slot():
    """Counting an undateable item as today's use would close an unspent slot."""
    from engine.marketing import franchises as fr

    assert fr.history_from_items(
        [{"account": "cici", "source": {"franchise": "cici_before_new_york_wakes"}}],
        account="cici",
    ) == []


def test_weekly_franchise_respects_max_per_week():
    from engine.marketing import franchises as fr

    fid = "cici_three_things_missed"
    f = fr.by_id(fid)
    assert f is not None and f.max_per_week == 2

    history = [
        (_WED_HK_CASH - timedelta(days=1), fid),
        (_WED_HK_CASH - timedelta(days=2), fid),
    ]
    ids = {s.franchise_id for s in fr.open_slots("cici", now=_WED_HK_CASH, history=history)}
    assert fid not in ids, "a weekly franchise exceeded max_per_week"


def test_disabled_franchise_never_opens_but_is_still_listed():
    """"Tea and Tickers" is PARKED while Cici's canon is dark (§2 amendment 8).

    It must not open — and it must still be visible to a caller asking what this
    desk runs, so a parked franchise is distinguishable from a forgotten one.
    """
    from engine.marketing import franchises as fr

    tea = fr.by_id("cici_tea_and_tickers")
    assert tea is not None and tea.enabled is False
    assert tea.id in {f.id for f in fr.for_account("cici")}
    every_window = [
        _WED_HK_CASH,
        _WED_HK_CASH + timedelta(hours=6),
        _WED_0900_ET,
    ]
    for when in every_window:
        assert tea.id not in {s.franchise_id for s in fr.open_slots("cici", now=when)}


def test_abstention_requires_a_known_reason():
    """§16.5's taxonomy is closed — a free-text reason defeats the diagnostic."""
    from engine.marketing import franchises as fr

    a = fr.abstain(None, "no_unique_edge", now=_WED_0900_ET, account="kelly", franchise_id="x")
    assert a.reason == "no_unique_edge"
    assert a.as_dict()["at"] == _WED_0900_ET.isoformat()

    with pytest.raises(ValueError):
        fr.abstain(None, "because_i_said_so", now=_WED_0900_ET, account="kelly")


def test_every_16_5_reason_is_available():
    """The constitution's eight abstention reasons all exist by name."""
    from engine.marketing import franchises as fr

    for reason in (
        "no_unique_edge",
        "saturated_conversation",
        "weak_persona_fit",
        "facts_too_stale",
        "topic_overused",
        "cross_account_collision",
        "sensitive_context",
        "low_conversion_coherence",
    ):
        assert reason in fr.ABSTAIN_REASONS


# ═════════════════════════════════════════════════════════════════════════════
# §2 Desk feed — four lanes, context attached
# ═════════════════════════════════════════════════════════════════════════════
def test_feed_produces_candidates_from_all_four_lanes():
    """THE GATE. Every lane of charter §4 produces a candidate for a live desk."""
    from engine.marketing import desk_feed

    feed = desk_feed.assemble(
        "flagship",
        now=_WED_0900_ET,
        cfg=_CFG,
        breaking_items=[_breaking_item()],
        movers=[{"ticker": "MSFT", "pct": 4.2}],
        studio_items=[{"id": "s1", "type": "signal", "headline": "Signal update"}],
    )
    assert feed.lanes_present == set(desk_feed.LANES), (
        f"missing lanes: {set(desk_feed.LANES) - feed.lanes_present}"
    )
    assert feed.notes == (), f"a lane raised: {feed.notes}"


@pytest.mark.parametrize("lane", ["scheduled", "breaking", "market_hours", "analysis"])
def test_each_lane_attaches_context(lane):
    """Charter §4: every generation call receives context packs + persona memory."""
    from engine.marketing import desk_feed

    feed = desk_feed.assemble(
        "flagship",
        now=_WED_0900_ET,
        cfg=_CFG,
        breaking_items=[_breaking_item()],
        movers=[{"ticker": "MSFT", "pct": 4.2}],
        studio_items=[{"id": "s1", "type": "signal", "headline": "Signal update"}],
    )
    cands = feed.by_lane(lane)
    assert cands, f"lane {lane} produced no candidate"
    for c in cands:
        assert c.context.get("account") == "flagship"
        # The three context families charter §4 names.
        assert "codex" in c.context
        assert "persona_memory" in c.context
        assert "chronicle" in c.context
        pm = c.context["persona_memory"]
        for key in ("recent_posts", "open_promises", "phrase_fatigue",
                    "relation_stage_counts"):
            assert key in pm, f"{lane}: persona memory missing {key}"
        # Review F19 — no handle-bearing relations record may ride the context.
        assert "relations" not in pm, (
            f"{lane}: the per-handle relations dict is back in feed context — that is "
            "the prompt-leak path F19 closed"
        )


def test_scheduled_lane_carries_the_franchise_contract():
    from engine.marketing import desk_feed

    feed = desk_feed.assemble("cici", now=_WED_HK_CASH, cfg=_CFG)
    sched = feed.by_lane("scheduled")
    assert sched
    hit = [c for c in sched if c.franchise_id == "cici_before_new_york_wakes"]
    assert hit, "the pre-open franchise did not reach the feed"
    fr_ctx = hit[0].context["franchise"]
    assert fr_ctx["contract"], "the franchise contract is empty"
    assert fr_ctx["classification"] == "analysis", (
        "charter §2 amendment 2 classifies 'Before New York Wakes' as ANALYSIS, not news"
    )


def test_breaking_lane_respects_the_one_owner_story_lock():
    """Charter §2 amendment 6: two accounts never draw the same story.

    The lock is a HARD gate, and the refusal is a logged abstention with the
    `cross_account_collision` reason, not a silent drop.
    """
    from engine.marketing import desk_feed, outbox, story_lock

    item = _breaking_item()
    key = story_lock.story_key(event_id=item["id"], headline=item["headline"])
    # Another desk already owns this story.
    owned = outbox.make_item(
        account="founder",
        kind="event",
        text="Founder already covered the CPI print today.",
        as_of="2026-07-22",
        provenance="test",
        source={"story_key": key},
        now=_WED_0900_ET - timedelta(minutes=10),
    )

    feed = desk_feed.assemble(
        "flagship", now=_WED_0900_ET, cfg=_CFG,
        breaking_items=[item], outbox_items=[owned],
    )
    assert feed.by_lane("breaking") == (), "the story lock did not stop a second desk"
    reasons = {a.reason for a in feed.abstentions}
    assert "cross_account_collision" in reasons


def test_account_with_no_wire_routing_gets_ZERO_breaking_candidates():
    """Review F2 — the fail-open inversion.

    The first cut read `if routed_classes and cls not in routed_classes`, so an
    account absent from `wire_routing` skipped the filter ENTIRELY and every
    breaking item became one of its candidates. The accounts most likely to be
    missing from routing config are exactly the ones that should be quietest.
    """
    from engine.marketing import desk_feed

    cfg = {"wire_routing": {"default": "flagship", "classes": {"macro_print": "flagship"}}}
    feed = desk_feed.assemble(
        "kelly", now=_WED_0900_ET, cfg=cfg,
        breaking_items=[_breaking_item(), _breaking_item(id="b2", event_class="policy")],
    )
    assert feed.by_lane("breaking") == (), (
        "an account with no wire_routing class received the unfiltered firehose"
    )
    assert "no_wire_routing" in {a.reason for a in feed.abstentions}

    # A totally empty routing config must be silence, not a free-for-all.
    bare = desk_feed.assemble(
        "flagship", now=_WED_0900_ET, cfg={}, breaking_items=[_breaking_item()])
    assert bare.by_lane("breaking") == ()


def test_story_lock_failure_withholds_the_candidate():
    """Review F3 — a lock you cannot consult is a lock that FAILED.

    The first cut swallowed the exception and fell through to emitting. The
    throw is most likely exactly when the outbox is mid-write — i.e. when
    another desk is claiming this very story.
    """
    from engine.marketing import desk_feed, story_lock

    def _boom(*a, **k):
        raise RuntimeError("outbox unreadable")

    original = story_lock.check
    story_lock.check = _boom  # type: ignore[assignment]
    try:
        feed = desk_feed.assemble(
            "flagship", now=_WED_0900_ET, cfg=_CFG, breaking_items=[_breaking_item()])
    finally:
        story_lock.check = original  # type: ignore[assignment]

    assert feed.by_lane("breaking") == (), "a failed one-owner lock still emitted"
    assert "cross_account_collision_check_failed" in {a.reason for a in feed.abstentions}


def test_session_franchises_do_not_open_at_the_weekend():
    """Review F4 — a WEEKDAY clock. "What the session did" needs a session."""
    from engine.marketing import franchises as fr

    sat_hk = datetime(2026, 7, 25, 4, 0, tzinfo=timezone.utc)  # Sat 12:00 HK
    sat_ids = {s.franchise_id for s in fr.open_slots("cici", now=sat_hk)}
    assert "cici_before_new_york_wakes" not in sat_ids, (
        "a session-premise franchise opened on a Saturday"
    )
    # Reflective weeklies still open — the specs shape the weekend (`medium`),
    # they never silence it.
    assert sat_ids, "the weekend went completely dark; weekend_shape thins, it does not mute"

    wed_ids = {s.franchise_id for s in fr.open_slots("cici", now=_WED_HK_CASH)}
    assert "cici_before_new_york_wakes" in wed_ids

    # Every DAILY franchise is session-clocked; no weekly one is.
    for f in fr.register():
        if f.cadence == "daily":
            assert f.sessions_only, f"{f.id}: a daily session-premise franchise is not gated"


def test_holiday_calendar_is_documented_as_out_of_scope():
    """Review F4 — say what the clock does NOT know, in the module itself."""
    src = (ROOT / "engine/marketing/franchises.py").read_text(encoding="utf-8")
    assert "NOT A TRADING CALENDAR" in src
    assert "OUT OF SCOPE" in src


def test_naive_clock_is_rejected():
    """Review F6 — a naive `now` resolves to the host zone: UTC in CI, local on
    the render host. That is an 8-hour swing on Cici's windows."""
    from engine.marketing import franchises as fr

    with pytest.raises(ValueError, match="timezone-aware"):
        fr.open_slots("cici", now=datetime(2026, 7, 22, 4, 0))
    with pytest.raises(ValueError):
        fr._local(datetime(2026, 7, 22, 4, 0), "Asia/Hong_Kong")


def test_breaking_lane_filters_on_beat_fit():
    """A wire class routed to another desk abstains with `weak_persona_fit`."""
    from engine.marketing import desk_feed

    cfg = {"wire_routing": {"default": "flagship", "classes": {"china_policy": "cici"}}}
    feed = desk_feed.assemble(
        "cici", now=_WED_HK_CASH, cfg=cfg,
        breaking_items=[_breaking_item(event_class="macro_print")],
    )
    assert feed.by_lane("breaking") == ()
    assert "weak_persona_fit" in {a.reason for a in feed.abstentions}

    # Her own class DOES reach her.
    feed2 = desk_feed.assemble(
        "cici", now=_WED_HK_CASH, cfg=cfg,
        breaking_items=[_breaking_item(id="b2", event_class="china_policy")],
    )
    assert feed2.by_lane("breaking"), "cici's own wire class did not reach her"


def test_market_hours_lane_is_silent_outside_the_accounts_session():
    """Cici files Asia, not the US afternoon — the territory clock is the point.

    Uses an allowlist that includes her, so what this pins is the SESSION gate
    and not the per-call lane gate (which the next test covers).
    """
    from engine.marketing import desk_feed

    cfg = {**_CFG, "publish": {"publish_time_movers": {"accounts": ["cici"]}}}
    inside = desk_feed.assemble(
        "cici", now=_WED_HK_CASH, cfg=cfg, movers=[{"ticker": "0700.HK", "pct": 3.1}]
    )
    assert inside.by_lane("market_hours"), "the market-hours lane was silent inside her session"

    outside = desk_feed.assemble(
        "cici", now=_WED_HK_ASLEEP, cfg=cfg, movers=[{"ticker": "0700.HK", "pct": 3.1}]
    )
    assert outside.by_lane("market_hours") == ()
    assert "outside_window" in {a.reason for a in outside.abstentions}


def test_market_hours_lane_honours_the_per_call_account_allowlist():
    """Review F5 — the same allowlist `publish.publish_time_movers` enforces.

    That lane builds a mover item straight from the tape without consulting
    tilt; so does this one, so it is bound by the same list rather than a
    second one invented here. config/marketing.yml pins it to [flagship,
    founder] and says "widen this list then, not before".
    """
    from engine.marketing import desk_feed

    movers = [{"ticker": "MSFT", "pct": 4.2}]
    live = desk_feed.assemble("flagship", now=_WED_0900_ET, cfg=_CFG, movers=movers)
    assert live.by_lane("market_hours"), "an allowlisted desk lost its market-hours lane"

    held = desk_feed.assemble("kelly", now=_WED_0900_ET, cfg=_CFG, movers=movers)
    assert held.by_lane("market_hours") == (), (
        "an employee desk ran the per-call tape lane the charter has not unlocked"
    )
    assert "no_market_hours_lane" in {a.reason for a in held.abstentions}


def test_mover_allowlist_provenance_is_not_asserted_unless_the_caller_says_so():
    """Review F5 — no unconditional `allowlist: cashtag_tiers` stamp.

    This module cannot verify what the caller filtered its movers by, so
    claiming a filter would be decorative provenance that reads downstream as a
    guarantee.
    """
    from engine.marketing import desk_feed

    silent = desk_feed.assemble(
        "flagship", now=_WED_0900_ET, cfg=_CFG, movers=[{"ticker": "MSFT", "pct": 4.2}]
    )
    ctx = silent.by_lane("market_hours")[0].context
    assert "allowlist" not in ctx
    assert "mover_allowlist" not in ctx

    stated = desk_feed.assemble(
        "flagship", now=_WED_0900_ET, cfg=_CFG,
        movers=[{"ticker": "MSFT", "pct": 4.2}], mover_allowlist="cashtag_tiers",
    )
    assert stated.by_lane("market_hours")[0].context["mover_allowlist"] == "cashtag_tiers"


def test_empty_slot_abstains_with_a_reason_rather_than_manufacturing_a_post():
    """Constitution Law 1 — value before activity. No inputs = no candidates."""
    from engine.marketing import desk_feed

    feed = desk_feed.assemble("cici", now=_WED_HK_ASLEEP, cfg=_CFG)
    assert feed.by_lane("breaking") == ()
    assert feed.by_lane("market_hours") == ()
    assert feed.by_lane("analysis") == ()
    # Her parked franchise is logged, not silently dropped.
    parked = [a for a in feed.abstentions if a.reason == "franchise_disabled"]
    assert parked, "a parked franchise vanished without an abstention record"
    assert all(a.as_dict()["detail"].get("note") for a in parked), (
        "a franchise_disabled abstention carries no explanation"
    )


def test_ranking_is_deterministic_and_inspectable():
    """The scorer is display-tier internal: deterministic, greppable, no LLM."""
    from engine.marketing import desk_feed

    kwargs = dict(
        now=_WED_0900_ET,
        cfg=_CFG,
        breaking_items=[_breaking_item()],
        movers=[{"ticker": "MSFT", "pct": 4.2}],
        studio_items=[{"id": "s1", "type": "signal", "headline": "Signal update"}],
    )
    a = desk_feed.assemble("flagship", **kwargs)
    b = desk_feed.assemble("flagship", **kwargs)
    assert [c.key for c in a.candidates] == [c.key for c in b.candidates]
    assert [c.score for c in a.candidates] == [c.score for c in b.candidates]
    # Every score is the sum of its named components — no opaque term.
    for c in a.candidates:
        assert c.components, f"{c.key} has no inspectable components"
        assert abs(sum(c.components.values()) - c.score) < 1e-9

    # Breaking outranks a scheduled slot (§7.5 why-now).
    assert a.candidates[0].lane == "breaking"


def test_feed_is_json_serialisable():
    """The feed rides item metadata and the nightly log — it must serialise."""
    from engine.marketing import desk_feed

    feed = desk_feed.assemble(
        "flagship", now=_WED_0900_ET, cfg=_CFG,
        breaking_items=[_breaking_item()], movers=[{"ticker": "MSFT", "pct": 4.2}],
    )
    json.dumps(feed.as_dict())


# ═════════════════════════════════════════════════════════════════════════════
# §3 Gift-Grip-Proof — the verdict, and the live-desk regression
# ═════════════════════════════════════════════════════════════════════════════
#: VERBATIM live deterministic posts from `data/marketing/content_plan.json`
#: (2026-07-28), spanning both live desks and every kind they emit. Frozen here
#: rather than read from the plan so the regression cannot rot when tonight's
#: plan changes — this is the "did XG-W3 silence the live desks" tripwire.
_LIVE_POSTS: tuple[tuple[str, str, str, str], ...] = (
    (
        "flagship", "watchlist", "$GPI on my radar this week",
        "Price is the most honest thing on the screen. Watching GPI, haven't touched it. "
        "The setup isn't finished and I don't front-run my own rules.",
    ),
    (
        "flagship", "watchlist", "Circling $CBOE",
        "Price is the most honest thing on the screen. Closest name to triggering on my "
        "list. The read's up top.",
    ),
    (
        "flagship", "chart", "CBOE, one chart",
        "$CBOE: Price is the most honest thing on the screen. The level I care about is "
        "285.10. That's the post.",
    ),
    (
        "flagship", "education", "The stop matters more than the target",
        "A target is a hope with a number on it. A stop is a decision made while you're "
        "still calm. Most of this job is the second one.",
    ),
    (
        "flagship", "education", "The part most people skip",
        "You can nail the direction and still lose money. Size against the stop decides "
        "the outcome, not the thesis. Unglamorous, true anyway.",
    ),
    (
        "flagship", "education", "What flagging something actually means",
        "A name on the board means the setup lined up, not a certainty. The level next to "
        "it says where we're wrong. Knowing where you're wrong is the whole product.",
    ),
    (
        "flagship", "event", "My read on today's move",
        "Growth data's been roughly steady while inflation readings are still warm. 18 "
        "groups on the move today. That's the early read. If the close disagrees, I go "
        "with the close.",
    ),
    (
        "flagship", "macro", "One thing worth watching up top",
        "Growth data's been roughly steady while inflation readings are still warm. 18 "
        "groups on the move today. How this resolves decides how much risk I want on.",
    ),
    (
        "flagship", "macro", "The honest macro read",
        "Growth data's been roughly steady while inflation readings are still warm. 18 "
        "groups on the move today. One data point, no spin. The spin is available "
        "elsewhere, free of charge.",
    ),
    (
        "founder", "watchlist", "Radar check on $LKFN",
        "Tape doesn't lie, and it's setting up. Near entry. Nothing's triggered. Patience, "
        "annoyingly, is the play.",
    ),
    (
        "founder", "watchlist", "$MSFT watching, not acting",
        "MSFT closed back above 382.46, the average price paid since the Jun 26 volume "
        "spike. Close setup, no entry. I'll post when it goes.",
    ),
    (
        "founder", "chart", "CBOE | tape check",
        "Tape doesn't lie, and it's setting up. $CBOE at 285.10. Worth thirty seconds of "
        "your day.",
    ),
    (
        "founder", "education", "One-minute version: sizing",
        "Risk the same small amount every time. The stop sets the size. Boring, works, "
        "next question.",
    ),
    (
        "founder", "education", "Invalidation, fast",
        "The level that says you were wrong. Price hits it, you're out. No ego, no "
        "averaging down, no praying.",
    ),
    (
        "founder", "education", "Quick: what's a setup?",
        "A price picture usually worth watching. Not a buy signal. A reason to pay "
        "attention before everyone else does.",
    ),
    (
        "founder", "event", "Price moved, here's the tape",
        "Growth data's been roughly steady while inflation readings are still warm. 18 "
        "groups on the move today. The tape's version is shorter than the article's. I "
        "trust the tape.",
    ),
    (
        "founder", "macro", "Macro, quick",
        "Growth data's been roughly steady while inflation readings are still warm. 18 "
        "groups on the move today. Short version, no panel discussion required.",
    ),
)


@pytest.mark.parametrize("account,kind,headline,body", _LIVE_POSTS)
def test_live_desk_posts_still_pass_the_value_gate(account, kind, headline, body):
    """THE NO-SILENT-SILENCING GATE.

    Every one of these is a real post the live flagship/founder desks queued
    under the deterministic templates. XG-W3's publish gate must not delete the
    two accounts that are actually running.
    """
    from engine.marketing import value_gate

    v = value_gate.evaluate(headline, body, kind=kind)
    assert v.verdict == "pass", (
        f"[{account}/{kind}] live post would now be silenced: {list(v.reasons)}\n"
        f"  H: {headline}\n  B: {body}"
    )


def test_gate_abstains_on_an_unrendered_template_slot():
    """The gate's real catch: a headline whose ticker slot never rendered.

    `data/marketing/content_plan.json` currently queues posts headlined
    "Circling" and "is close" — the `{cashtag}` slot rendered empty and
    `validate_copy` passed them with zero violations. Abstaining here is the
    gate WORKING, so it is pinned as intended behaviour rather than tuned away.
    """
    from engine.marketing import value_gate

    for headline in ("Circling", "is close", "Radar check on"):
        v = value_gate.evaluate(
            headline,
            "226 of 226 names in the S&P universe are showing bullish momentum setups "
            "right now. Near the level I care about.",
            kind="watchlist",
        )
        assert v.verdict == "abstain"
        assert "grip:no_hook" in v.reasons


def test_gate_abstains_when_copy_merely_restates_its_source():
    """§7.2: "We rewrote the headline" is not an answer."""
    from engine.marketing import value_gate

    src = "Fed holds rates steady at 4.25% citing sticky services inflation"
    v = value_gate.evaluate(
        "Fed holds rates steady at 4.25%",
        "The Fed held rates steady at 4.25%, citing sticky services inflation.",
        kind="macro",
        source_headline=src,
    )
    assert v.verdict == "abstain"
    assert "gift:restates_source" in v.reasons


def test_gate_abstains_when_an_asserting_kind_has_no_evidence():
    """A signal post with no number, no chart and no instrument fails PROOF."""
    from engine.marketing import value_gate

    v = value_gate.evaluate(
        "What we're watching today",
        "Something is going on beneath the surface and we think it matters quite a lot.",
        kind="signal",
    )
    assert v.verdict == "abstain"
    assert any(r.startswith("proof:") for r in v.reasons)


def test_proof_tier_is_recorded_on_every_pass():
    from engine.marketing import value_gate

    hard = value_gate.evaluate("MSFT | tape check", "$MSFT at 402.30. That's the post.", kind="chart")
    assert hard.verdict == "pass" and hard.proof_tier == "hard"

    inst = value_gate.evaluate(
        "Circling $CBOE", "Closest name to triggering on my list. The read's up top.",
        kind="watchlist",
    )
    assert inst.verdict == "pass" and inst.proof_tier == "instrument"


def test_cjk_bodies_are_counted_and_can_pass(tmp_path):
    """Review F7 — a latin-only tokenizer silenced 100% of zh posts.

    `[A-Za-z0-9']+` finds nothing in a Chinese body, so `body_words` was 0,
    fell under the floor, and every zh post failed `gift:body_too_thin`. The
    site is bilingual by law; a length test that only counts English is the
    same "silent silencing" the calibration exercise existed to prevent, aimed
    at a language instead of at a desk.
    """
    from engine.marketing import value_gate

    body = "标普500指数上涨1.2%，信用利差保持稳定。这是我们关注的水平。"
    assert len(value_gate._words(body)) > 6, "CJK codepoints are not being counted"

    # A realistic zh headline (full-width colon compression) now passes.
    v = value_gate.evaluate("美股收盘：标普涨1.2%", body, kind="macro")
    assert v.verdict == "pass", f"a well-formed zh post was silenced: {list(v.reasons)}"
    assert v.components["body_words"] > 6

    # And a full-width question mark reaches the interrogative device.
    q = value_gate.evaluate("这次不一样吗？", body, kind="macro")
    assert q.verdict == "pass"


def test_reply_kind_is_registered_before_xg_w4_lands():
    """Review F7 — the reply desk should inherit a deliberate tier, not a default."""
    from engine.marketing import value_gate

    assert value_gate.KIND_PROOF.get("reply") == "instrument"
    v = value_gate.evaluate(
        "Worth adding: credit is the test",
        "$HYG spreads have not confirmed the equity move. That is the tell to watch.",
        kind="reply",
    )
    assert v.verdict == "pass"
    assert v.components["kind_known"] is True


def test_unregistered_kind_is_visible_in_the_verdict():
    """Review F7 — a defaulted kind must be distinguishable from a tiered one."""
    from engine.marketing import value_gate

    known = value_gate.evaluate("CBOE | tape check", "$CBOE at 285.10.", kind="chart")
    assert known.components["kind_known"] is True

    unknown = value_gate.evaluate(
        "CBOE | tape check", "$CBOE at 285.10.", kind="brand_new_kind")
    assert unknown.components["kind_known"] is False
    assert unknown.components["required_proof"] == "hard", "a new kind must default STRICT"


def test_regional_shorthand_is_not_mistaken_for_an_instrument():
    """Review F22 — "HK"/"PBOC" are Cici's everyday vocabulary, not tickers.

    A false instrument is a false PROOF tier for the kinds that may rest on one.
    """
    from engine.marketing import value_gate

    for token in ("HK", "CNY", "PBOC", "NYSE", "SPX", "ECB", "BOJ", "APAC", "HKT"):
        assert not value_gate._has_bare_ticker(token), f"{token} read as an instrument"
    assert value_gate._has_bare_ticker("MSFT")
    assert value_gate._has_bare_ticker("CBOE")

    starved = value_gate.evaluate(
        "PBOC and the HK read",
        "The PBOC set the fix and HK followed. APAC broadly firmer into the close.",
        kind="watchlist",
    )
    assert starved.verdict == "abstain", (
        "an evidence-free post vouched for itself with regional shorthand"
    )


def test_a_supplied_whitelist_is_authoritative_for_proof():
    """A number the fact layer does NOT vouch for must not become proof.

    When the caller supplies a `numbers_whitelist` it is asserting provenance,
    so an unlisted number may not be laundered into `hard` by the no-whitelist
    fallback. Without this the gate would stamp "proof: hard" on a fabricated
    figure the moment a whitelist happened to be threaded through.
    """
    from engine.marketing import value_gate

    vouched = value_gate.evaluate(
        "MSFT | tape check", "$MSFT at 402.30. That's the post.",
        kind="chart", numbers_whitelist=["402.30"],
    )
    assert vouched.verdict == "pass" and vouched.proof_tier == "hard"

    unvouched = value_gate.evaluate(
        "MSFT | tape check", "$MSFT at 911.11. That's the post.",
        kind="chart", numbers_whitelist=["402.30"],
    )
    assert unvouched.verdict == "abstain", (
        "an unvouched number was laundered into proof"
    )
    assert "proof:below_hard" in unvouched.reasons

    # With no whitelist supplied the caller asserts nothing, and the fallback
    # applies — but the distinction stays visible in components.
    silent = value_gate.evaluate(
        "MSFT | tape check", "$MSFT at 911.11. That's the post.", kind="chart",
    )
    assert silent.verdict == "pass"
    assert silent.components["numbers_whitelist_supplied"] is False
    assert vouched.components["numbers_whitelist_supplied"] is True


def test_bridge_is_a_marker_and_never_blocks():
    """Charter §2: Bridge raises option value; it never blocks (§7.1's own formula)."""
    from engine.marketing import value_gate

    v = value_gate.evaluate(
        "Circling $CBOE", "Closest name to triggering on my list. The read's up top.",
        kind="watchlist",
    )
    assert v.bridge is False
    assert v.verdict == "pass", "absence of a Bridge blocked publication"


def test_verdict_metadata_is_json_safe_and_complete():
    """Charter §0: EVERY emission carries its verdict in item metadata."""
    from engine.marketing import outbox, value_gate

    v = value_gate.evaluate("CBOE | tape check", "$CBOE at 285.10. Worth a look.", kind="chart")
    meta = value_gate.verdict_metadata(v)
    for key in ("verdict", "gift", "grip", "proof", "bridge", "proof_tier", "reasons"):
        assert key in meta

    item = outbox.make_item(
        account="flagship", kind="chart", text="CBOE | tape check $CBOE at 285.10.",
        as_of="2026-07-22", provenance="test",
        source={"value_gate": meta, "franchise": "flagship_research_in_one_chart"},
        now=_WED_0900_ET,
    )
    assert outbox.validate_item(item) == []
    round_tripped = json.loads(json.dumps(item))
    assert round_tripped["source"]["value_gate"]["verdict"] == "pass"
    assert round_tripped["source"]["franchise"] == "flagship_research_in_one_chart"


# ═════════════════════════════════════════════════════════════════════════════
# §4 Phrase fatigue arms the XG-W1 quirk caps
# ═════════════════════════════════════════════════════════════════════════════
def test_second_signature_opener_in_one_day_is_rejected(tmp_path):
    """THE GATE. Meagan's "okay so —" opener is capped at ≤1/day and ≤30%/7d.

    Before XG-W3 those caps were evaluated against the current BATCH only, so
    they were unenforced across days. `persona_memory.phrases.jsonl` is what
    arms them, and this is the proof.
    """
    from engine.marketing import expression_dial as ed
    from engine.marketing import persona_memory as pm

    codex = ed.codex_for("meagan")
    assert codex is not None
    decl = codex.declared["okay_so_opener"]
    assert decl.max_per_day == 1 and decl.max_share_7d == pytest.approx(0.30)

    now = datetime(2026, 7, 22, 15, 0, tzinfo=timezone.utc)
    text = "okay so — the tape is quiet today. Breadth is the tell."

    # First use of the day, empty store: allowed.
    first = ed.frequency_violations(
        text, codex=codex, as_of="2026-07-22",
        recent=pm.recent_posts("meagan", now=now, root=tmp_path),
    )
    assert first == [], f"the first signature opener of the day was rejected: {first}"

    # Record it, then try again the SAME day.
    pm.record_post("meagan", text, now=now, root=tmp_path)
    second = ed.frequency_violations(
        text, codex=codex, as_of="2026-07-22",
        recent=pm.recent_posts("meagan", now=now, root=tmp_path),
    )
    assert second, "a SECOND signature opener in one day was allowed"
    assert any("max_per_day" in v for v in second)


def test_quirk_cap_window_rolls_off_after_seven_days(tmp_path):
    """The cap is a ROLLING window — an old post must stop counting."""
    from engine.marketing import expression_dial as ed
    from engine.marketing import persona_memory as pm

    codex = ed.codex_for("meagan")
    text = "okay so — the tape is quiet today. Breadth is the tell."
    old = datetime(2026, 7, 1, 15, 0, tzinfo=timezone.utc)
    now = datetime(2026, 7, 22, 15, 0, tzinfo=timezone.utc)

    pm.record_post("meagan", text, now=old, root=tmp_path)
    recent = pm.recent_posts("meagan", now=now, root=tmp_path)
    assert recent == [], "a 3-week-old post is still inside the 7-day window"
    assert ed.frequency_violations(text, codex=codex, as_of="2026-07-22", recent=recent) == []


def test_recent_posts_sees_host_writes_before_any_consolidation(tmp_path):
    """A cap that ignored today's un-consolidated posts would be spendable.

    Readers see the UNION of tracked + host, exactly like `outbox.read_items_all`.
    """
    from engine.marketing import persona_memory as pm

    now = datetime(2026, 7, 22, 15, 0, tzinfo=timezone.utc)
    pm.record_post("kelly", "Semis are the reaction. Credit is the test.", now=now, root=tmp_path)
    assert not pm.repo_dir(tmp_path, "kelly").exists(), "an intraday write touched the tracked dir"
    assert len(pm.recent_posts("kelly", now=now, root=tmp_path)) == 1


def test_copywriter_seeds_the_caps_from_durable_memory(tmp_path, monkeypatch):
    """The wiring itself: `memory_recent_seed` reaches the deterministic writer."""
    from engine.marketing import copywriter
    from engine.marketing import persona_memory as pm

    now = datetime(2026, 7, 22, 15, 0, tzinfo=timezone.utc)
    pm.record_post("meagan", "okay so — breadth is the tell.", now=now, root=tmp_path)

    seed = copywriter.memory_recent_seed(["meagan"], now=now, root=tmp_path)
    assert seed.get("meagan"), "durable memory did not reach the copywriter seed"
    assert seed["meagan"][0]["date"] == "2026-07-22"
    assert "text" in seed["meagan"][0], (
        "frequency_violations re-scans `text`; a seed without it silently disarms the caps"
    )


# ═════════════════════════════════════════════════════════════════════════════
# §5 Persona memory — host-only intraday, consolidator-only tracked
# ═════════════════════════════════════════════════════════════════════════════
def test_intraday_writes_land_only_under_host_state(tmp_path):
    """THE GATE. Zero tracked-repo writes intraday (charter §2 amendment 13)."""
    from engine.marketing import persona_memory as pm

    now = datetime(2026, 7, 22, 15, 0, tzinfo=timezone.utc)
    pm.record_post("cici", "While New York slept, HK closed green.", now=now, root=tmp_path)
    pm.record_promise("cici", "We'll update after the auction.",
                      due_condition="auction result", now=now, root=tmp_path)
    pm.record_relation("cici", "@someauthor", now=now, topics=["china"], stage="engaged", root=tmp_path)

    assert pm.host_dir(tmp_path, "cici").exists()
    tracked_root = tmp_path / "data" / "marketing" / "personas"
    assert not tracked_root.exists(), (
        "an intraday write created the TRACKED personas dir — the nightly-sole-advancer "
        "law says only the consolidator may"
    )


def test_consolidator_advances_the_tracked_ledgers_and_is_idempotent(tmp_path):
    from engine.marketing import persona_memory as pm

    now = datetime(2026, 7, 22, 15, 0, tzinfo=timezone.utc)
    pm.record_post("cici", "While New York slept, HK closed green.", now=now, root=tmp_path)
    pm.record_relation("cici", "someauthor", now=now, topics=["china"], stage="engaged", root=tmp_path)

    summary = pm.consolidate(now=now, root=tmp_path)
    assert "cici" in summary["accounts"]
    tracked = pm.repo_dir(tmp_path, "cici")
    assert (tracked / "phrases.jsonl").exists()
    assert (tracked / "relations.jsonl").exists()
    # Host spool is cleared only AFTER the tracked write lands.
    assert not (pm.host_dir(tmp_path, "cici") / "phrases.jsonl").exists()

    before = pm.recent_posts("cici", now=now, root=tmp_path)
    pm.consolidate(now=now, root=tmp_path)
    pm.consolidate(now=now, root=tmp_path)
    after = pm.recent_posts("cici", now=now, root=tmp_path)
    assert before == after, "a retried nightly double-counted — every cap would tighten"


def test_open_promises_survive_retention_but_closed_ones_expire(tmp_path):
    """An OLD open loop is the one most in need of closing (§11.6)."""
    from engine.marketing import persona_memory as pm

    old = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    now = datetime(2026, 7, 22, 15, 0, tzinfo=timezone.utc)
    p = pm.record_promise("kelly", "We'll publish the sector damage map.",
                          due_condition="10y closes above the range",
                          due_by="2026-01-05", now=old, root=tmp_path)
    pm.consolidate(now=now, root=tmp_path, retention_days=90)

    still_open = pm.open_promises("kelly", now=now, root=tmp_path)
    assert len(still_open) == 1, "a 6-month-old OPEN promise was retired by retention"
    assert still_open[0]["overdue"] is True

    pm.close_promise("kelly", p["id"], now=now, outcome="published", root=tmp_path)
    assert pm.open_promises("kelly", now=now, root=tmp_path) == []


def test_promise_requires_a_closing_condition(tmp_path):
    from engine.marketing import persona_memory as pm

    with pytest.raises(ValueError):
        pm.record_promise("kelly", "Something will happen.", due_condition="",
                          now=_WED_0900_ET, root=tmp_path)


def test_cap_day_basis_matches_the_evaluator(tmp_path):
    """Review F18 — record and evaluate on the SAME calendar.

    `frequency_violations` compares each record's `date` against the item's
    `as_of` (the plan's BUSINESS date). Deriving the stored date from a UTC
    clock instead puts the two on different calendars: Cici's 08:00 Hong Kong
    post is still the previous UTC day, so her second signature opener of the
    HK morning would carry a different `date` than the plan's `as_of` and slip
    the ≤1/day cap entirely.
    """
    from engine.marketing import expression_dial as ed
    from engine.marketing import persona_memory as pm

    # 00:30 UTC on the 23rd == 08:30 on the 23rd in Hong Kong, but a business
    # day of 2026-07-22 for a plan built the previous evening.
    early_utc = datetime(2026, 7, 23, 0, 30, tzinfo=timezone.utc)
    text = "okay so — the tape is quiet today. Breadth is the tell."

    pm.record_post("meagan", text, now=early_utc, as_of="2026-07-22", root=tmp_path)
    rows = pm.recent_posts("meagan", now=early_utc, root=tmp_path)
    assert rows and rows[0]["date"] == "2026-07-22", (
        "the stored day came from the wall clock, not the business date"
    )

    codex = ed.codex_for("meagan")
    assert ed.frequency_violations(
        text, codex=codex, as_of="2026-07-22", recent=rows
    ), "the cap did not see a same-business-day post recorded across a UTC boundary"

    # Absent an as_of the UTC clock is still the fallback.
    pm.record_post("kelly", "x", now=early_utc, root=tmp_path)
    assert pm.recent_posts("kelly", now=early_utc, root=tmp_path)[0]["date"] == "2026-07-23"


def test_consolidator_dedup_survives_a_plan_rebuild(tmp_path):
    """Review F9 — dedup on (DATE, text), not (at, text).

    `at` is wall-clock at write, so a plan-build re-run that re-emits the same
    post a minute later produced a different key and the record survived dedup
    twice — inflating both sides of `max_share_7d` and double-counting
    `max_per_day`. A retried run would silently TIGHTEN the caps.
    """
    from engine.marketing import persona_memory as pm

    text = "okay so — breadth is the tell."
    first = datetime(2026, 7, 22, 15, 0, tzinfo=timezone.utc)
    later = datetime(2026, 7, 22, 15, 41, tzinfo=timezone.utc)  # same day, new clock

    pm.record_post("meagan", text, now=first, as_of="2026-07-22", root=tmp_path)
    pm.record_post("meagan", text, now=later, as_of="2026-07-22", root=tmp_path)
    pm.consolidate(now=later, root=tmp_path)

    rows = pm.recent_posts("meagan", now=later, root=tmp_path)
    assert len(rows) == 1, (
        f"a re-emitted post was counted {len(rows)}x — every cap it feeds is now tighter "
        "than the codex says"
    )


def test_consolidator_honours_its_own_env_knob(tmp_path, monkeypatch):
    """Review F12 — daily.yml sets it; a step that ignores its gate is a fake knob."""
    from engine.marketing import persona_memory as pm

    now = datetime(2026, 7, 22, 15, 0, tzinfo=timezone.utc)
    pm.record_post("cici", "while new york slept", now=now, as_of="2026-07-22", root=tmp_path)

    monkeypatch.setenv("MARKETING_PERSONA_MEMORY_ENABLED", "0")
    out = pm.consolidate(now=now, root=tmp_path)
    assert out.get("skipped") == "disabled"
    assert not pm.repo_dir(tmp_path, "cici").exists(), "disabled, yet the ledger advanced"

    monkeypatch.setenv("MARKETING_PERSONA_MEMORY_ENABLED", "1")
    assert pm.consolidate(now=now, root=tmp_path)["accounts"]
    assert pm.repo_dir(tmp_path, "cici").exists()


def test_relations_store_admits_no_sensitive_field(tmp_path):
    """Constitution §10 / charter §4: nothing sensitive INFERRED.

    The schema is the enforcement: there is nowhere to write a demographic, an
    employer or a location, and an out-of-vocabulary stage raises.
    """
    from engine.marketing import persona_memory as pm

    now = datetime(2026, 7, 22, 15, 0, tzinfo=timezone.utc)
    rec = pm.record_relation("kelly", "@author", now=now, topics=["credit"],
                             stage="engaged", root=tmp_path)
    assert set(rec) == {"account", "handle", "at", "date", "topics", "stage", "id"}

    with pytest.raises(ValueError):
        pm.record_relation("kelly", "@author", now=now, stage="probably_a_hedge_fund_guy",
                           root=tmp_path)


def _write_call_sites(rel: str) -> list[tuple[str, str]]:
    """(enclosing function, source) for every write-handle call in a module.

    AST, not a text grep, on purpose — the XG-W2 lesson: a grep over raw source
    matches the guard's OWN explanatory prose, so a text-scanning version of
    this guard passes only until somebody documents the rule it enforces.
    """
    tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
    parent_of: dict[ast.AST, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for child in ast.walk(node):
                parent_of.setdefault(child, node.name)

    out: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = fn.attr if isinstance(fn, ast.Attribute) else (fn.id if isinstance(fn, ast.Name) else "")
        if name not in ("open", "mkstemp", "NamedTemporaryFile", "replace", "write_text", "unlink"):
            continue
        if name == "open":
            modes = [a.value for a in node.args[1:2]
                     if isinstance(a, ast.Constant) and isinstance(a.value, str)]
            if not any(m and m[0] in "wax" for m in modes):
                continue
        if name == "replace":
            # `os.replace(tmp, path)` is a filesystem write; `dt.replace(...)`
            # and `str.replace(...)` are not. Discriminate on the RECEIVER, not
            # the method name — otherwise every tz normalisation in the module
            # reads as a rogue writer and the guard cries wolf until someone
            # deletes it.
            recv = fn.value if isinstance(fn, ast.Attribute) else None
            if not (isinstance(recv, ast.Name) and recv.id in ("os", "shutil")):
                continue
        out.append((parent_of.get(node, "<module>"), ast.unparse(node)[:120]))
    return out


def test_only_the_consolidator_writes_the_tracked_persona_ledgers():
    """THE GUARD. Modelled on XG-W2's hand-rolled-writer guard.

    Pins the CAPABILITY, not today's symbol names: every write-handle call site
    in persona_memory.py must sit inside one of two allowlisted helpers — the
    host appender or the tracked writer — and `_write_tracked` may only be
    reached from `consolidate`. A RENAMED intraday writer fails this too.
    """
    sites = _write_call_sites("engine/marketing/persona_memory.py")
    allowed = {
        "_append_host",       # the host spool appender (intraday)
        "_write_tracked",     # the tracked ledger writer
        "_consolidate_locked",  # host truncate, under the spool lock (F10)
        "_spool_lock",        # opens the .lock file itself (F10)
    }
    offenders = [(fn, src) for fn, src in sites if fn not in allowed]
    assert offenders == [], f"write handle outside the allowlisted writers: {offenders}"

    # And `_write_tracked` is reachable only from the consolidation body.
    tree = ast.parse((ROOT / "engine/marketing/persona_memory.py").read_text(encoding="utf-8"))
    callers = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for child in ast.walk(node):
                if isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
                    if child.func.id == "_write_tracked":
                        callers.add(node.name)
    assert callers == {"_consolidate_locked"}, (
        f"_write_tracked is reachable from {callers or 'nothing'}; only the "
        "consolidation body may advance a tracked ledger (nightly-sole-advancer law)"
    )


def test_no_other_marketing_module_writes_the_persona_ledgers():
    """Nothing else in engine/marketing or scripts/ may target that path."""
    hits: list[str] = []
    for base in ("engine/marketing", "scripts"):
        for path in sorted((ROOT / base).rglob("*.py")):
            if path.name == "persona_memory.py":
                continue
            try:
                src = path.read_text(encoding="utf-8")
            except OSError:
                continue
            if "marketing/personas" in src or 'marketing", "personas' in src:
                # A reference is fine only if it never sits next to a write.
                for fn, call in _write_call_sites(str(path.relative_to(ROOT))):
                    if "persona" in call.lower():
                        hits.append(f"{path.relative_to(ROOT)}:{fn}: {call}")
    assert hits == [], f"a second writer of the persona ledgers appeared: {hits}"


# ═════════════════════════════════════════════════════════════════════════════
# §5b PRODUCTION WIRING — the gates above are vacuous without these
#
# The XG-W3 adversarial review found that `record_post`, `verdict_metadata` and
# `value_gate.enforce` had ZERO production call sites: every test exercised the
# modules directly, so "the caps are armed" and "every emission carries a
# verdict" were true of the test suite and of nothing else. These tests pin the
# CALL SITES, not the capability — a module that works but is never called is
# the exact failure they exist to catch.
# ═════════════════════════════════════════════════════════════════════════════
def _production_sources() -> dict[str, str]:
    return {
        rel: (ROOT / rel).read_text(encoding="utf-8")
        for rel in (
            "scripts/marketing_publisher.py",
            "engine/marketing/outbox.py",
            "engine/marketing/press_lane.py",
        )
    }


def test_publisher_records_every_shipped_post_into_persona_memory():
    """THE ARMING CALL. Without it the frequency caps have no durable history.

    Pinned as an AST reachability check from the publisher's posting-success
    branch, not a string grep: a call sitting in dead code would satisfy a grep.
    """
    src = (ROOT / "scripts/marketing_publisher.py").read_text(encoding="utf-8")
    tree = ast.parse(src)

    # The helper exists and calls persona_memory.record_post.
    helpers = {
        n.name: n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert "_record_persona_post" in helpers, "the publisher has no persona-memory helper"
    body = ast.dump(helpers["_record_persona_post"])
    assert "record_post" in body, "_record_persona_post does not call record_post"

    # And it is CALLED from main()'s success path — inside an `if receipt.ok:`.
    called_in = {
        parent.name
        for parent in ast.walk(tree)
        if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef))
        for child in ast.walk(parent)
        if isinstance(child, ast.Call)
        and getattr(child.func, "id", "") == "_record_persona_post"
    }
    assert called_in, "_record_persona_post is defined but never called — dead wiring"

    ok_branches = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.If) and "receipt.ok" in ast.unparse(n.test)
    ]
    assert ok_branches, "could not find the posting-success branch"
    assert any(
        isinstance(c, ast.Call) and getattr(c.func, "id", "") == "_record_persona_post"
        for br in ok_branches for c in ast.walk(br)
    ), "the persona-memory record does not run on the posting-SUCCESS path"


def test_record_persona_post_only_records_dial_governed_accounts(tmp_path, monkeypatch):
    """The store arms per-quirk caps, which live in a codex. No codex, no record."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_mp_under_test", ROOT / "scripts" / "marketing_publisher.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    from engine.marketing import persona_memory as pm

    now = datetime(2026, 7, 22, 15, 0, tzinfo=timezone.utc)
    item = {"id": "i1", "kind": "macro", "as_of": "2026-07-22",
            "source": {"franchise": "meagan_mood_vs_money"}}

    mod._record_persona_post(tmp_path, item, "meagan", "okay so — breadth is the tell.", now)
    assert len(pm.recent_posts("meagan", now=now, root=tmp_path)) == 1

    # An account with no codex writes nothing.
    mod._record_persona_post(tmp_path, item, "no_such_desk", "text", now)
    assert pm.recent_posts("no_such_desk", now=now, root=tmp_path) == []

    # And a raising store must NOT break a run whose post already shipped.
    monkeypatch.setattr(pm, "record_post", lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
    mod._record_persona_post(tmp_path, item, "meagan", "text", now)  # must not raise


def test_nightly_emission_stamps_a_verdict_on_every_item(tmp_path):
    """THE §0 GATE, ON A REAL EMISSION PATH (`outbox.emit_from_content_plan`)."""
    from engine.marketing import outbox

    plan = {
        "as_of": "2026-07-22",
        "accounts": [{"id": "flagship", "queue": [
            {"id": "p1", "slot": "D1-a", "type": "chart",
             "headline": "CBOE | tape check", "body": "$CBOE at 285.10. Worth a look."},
            {"id": "p2", "slot": "D1-b", "type": "signal",
             "headline": "What we are watching",
             "body": "Something is going on beneath the surface and we think it matters a lot."},
        ]}],
    }
    summary = outbox.emit_from_content_plan(
        plan, root=tmp_path, cfg={"value_gate": {"enforce": False}})

    assert summary["emitted"] == 2, "record-only mode must not drop anything"
    assert summary.get("value_gate_would_block") == 1
    assert not summary.get("value_gate_blocked")

    items = outbox.read_items_all(tmp_path)
    assert len(items) == 2
    for it in items:
        vg = (it.get("source") or {}).get("value_gate")
        assert vg, f"{it['kind']} emitted with NO value-gate verdict in metadata"
        assert vg["verdict"] in ("pass", "abstain")
        assert vg["enforced"] is False
    verdicts = {it["kind"]: (it["source"]["value_gate"])["verdict"] for it in items}
    assert verdicts["chart"] == "pass"
    assert verdicts["signal"] == "abstain", "an evidence-free signal post was not flagged"


def test_value_gate_enforce_is_read_and_both_branches_are_live(tmp_path):
    """`enforce` is a REAL knob (review: it was read by nothing).

    Same plan, two configs, different outcomes — which is the only thing that
    proves a config key is wired rather than decorative.
    """
    from engine.marketing import outbox

    plan = {
        "as_of": "2026-07-22",
        "accounts": [{"id": "flagship", "queue": [
            {"id": "p1", "slot": "D1-a", "type": "chart",
             "headline": "CBOE | tape check", "body": "$CBOE at 285.10. Worth a look."},
            {"id": "p2", "slot": "D1-b", "type": "signal",
             "headline": "What we are watching",
             "body": "Something is going on beneath the surface and we think it matters a lot."},
        ]}],
    }
    dark = outbox.emit_from_content_plan(
        plan, root=tmp_path / "dark", cfg={"value_gate": {"enforce": False}})
    armed = outbox.emit_from_content_plan(
        plan, root=tmp_path / "armed", cfg={"value_gate": {"enforce": True}})

    assert dark["emitted"] == 2 and not dark.get("value_gate_blocked")
    assert armed["emitted"] == 1, "arming enforce did not actually block the abstention"
    assert armed.get("value_gate_blocked") == 1
    assert outbox._value_gate_enforced({"value_gate": {"enforce": True}}) is True
    assert outbox._value_gate_enforced({}) is False, "enforce must default OFF"


def test_press_lane_stamps_a_verdict_and_compares_against_the_source_headline():
    """The breaking lane is the one where restating the source is the live risk."""
    src = (ROOT / "engine/marketing/press_lane.py").read_text(encoding="utf-8")
    assert "stamp_value_gate" in src, "press_lane emits without a value-gate verdict"
    assert "source_headline" in src, (
        "press_lane does not pass the upstream headline — the informational-surplus "
        "test has nothing to compare against on the one lane that needs it"
    )

    from engine.marketing import outbox

    source: dict = {"lane": "press"}
    would_block = outbox.stamp_value_gate(
        source,
        headline="Fed holds rates steady at 4.25%",
        body="The Fed held rates steady at 4.25%, citing sticky services inflation.",
        kind="breaking",
        source_headline="Fed holds rates steady at 4.25% citing sticky services inflation",
        cfg={},
    )
    assert would_block is True
    assert "gift:restates_source" in source["value_gate"]["reasons"]


def test_stamp_value_gate_fails_soft_and_never_silences_a_desk(monkeypatch):
    """A publish gate that goes down must not stop the desks."""
    from engine.marketing import outbox, value_gate

    monkeypatch.setattr(
        value_gate, "evaluate",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("gate exploded")))
    source: dict = {}
    assert outbox.stamp_value_gate(
        source, headline="h", body="b", kind="chart", cfg={}) is False
    assert source["value_gate"]["verdict"] == "error"


def test_copywriter_seeding_reads_a_store_the_publisher_actually_writes(tmp_path):
    """END TO END: publisher writes → copywriter seed reads → caps see it.

    This is the loop the review found broken. Each half worked; nothing joined
    them, so the caps evaluated against an empty history forever.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_mp_under_test2", ROOT / "scripts" / "marketing_publisher.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    from engine.marketing import copywriter, expression_dial as ed

    now = datetime(2026, 7, 22, 15, 0, tzinfo=timezone.utc)
    text = "okay so — the tape is quiet today. Breadth is the tell."
    item = {"id": "i1", "kind": "macro", "as_of": "2026-07-22", "source": {}}

    # 1. the publisher records a shipped post
    mod._record_persona_post(tmp_path, item, "meagan", text, now)

    # 2. the copywriter seed picks it up
    seed = copywriter.memory_recent_seed(["meagan"], now=now, root=tmp_path)
    assert seed.get("meagan"), "the publisher's write never reached the copywriter seed"

    # 3. and the cap now fires on a second use the same day
    codex = ed.codex_for("meagan")
    violations = ed.frequency_violations(
        text, codex=codex, as_of="2026-07-22", recent=seed["meagan"])
    assert violations, "the arming loop is joined but the cap still does not fire"


# ═════════════════════════════════════════════════════════════════════════════
# §6 Meagan's measured-input rule (charter §2 amendment 10)
# ═════════════════════════════════════════════════════════════════════════════
def test_meagan_crowd_franchises_declare_the_measured_input_requirement():
    from engine.marketing import franchises as fr

    mood = fr.by_id("meagan_mood_vs_money")
    assert mood is not None and mood.requires_measured_input is True
    chat = fr.by_id("meagan_market_group_chat")
    assert chat is not None and chat.requires_measured_input is True


def test_unmeasured_crowd_state_claim_is_rejected():
    """"The LLM does not originate the crowd reading." """
    from engine.marketing import franchises as fr

    mood = fr.by_id("meagan_mood_vs_money")
    bad = fr.measured_input_violations(
        "Mood vs money",
        "Everyone is panicking about rates right now, but breadth is fine.",
        franchise=mood,
    )
    assert bad, "an unmeasured crowd-state claim passed"
    assert "crowd-state claim" in bad[0]


def test_attributed_crowd_reading_is_allowed():
    """The interim form: QUOTE an attributed headline or post."""
    from engine.marketing import franchises as fr

    mood = fr.by_id("meagan_mood_vs_money")
    assert fr.measured_input_violations(
        "Mood vs money",
        'Bloomberg\'s front page says "investors are bracing for a hawkish hold". '
        "Breadth is fine and credit is calm.",
        franchise=mood,
    ) == []
    # A citation carried in metadata satisfies it too.
    assert fr.measured_input_violations(
        "Mood vs money",
        "Everyone is panicking about rates right now, but breadth is fine.",
        franchise=mood,
        sources=[{"url": "https://example.invalid/story"}],
    ) == []


def test_measured_input_rule_does_not_bind_other_franchises():
    """It is a rule about crowd-state FRANCHISES, not about every sentence."""
    from engine.marketing import franchises as fr

    kelly = fr.by_id("kelly_confirmation_check")
    assert fr.measured_input_violations(
        "Confirmation check",
        "Everyone is bullish semis. Credit is the test.",
        franchise=kelly,
    ) == []


def test_tape_only_reading_across_two_sentences_is_not_a_claim():
    """"Everyone has a view. The tape is flat." is two honest statements."""
    from engine.marketing import franchises as fr

    mood = fr.by_id("meagan_mood_vs_money")
    assert fr.measured_input_violations(
        "Mood vs money",
        "Plenty of noise out there. Breadth sits at 48% and credit spreads are unchanged.",
        franchise=mood,
    ) == []


# ═════════════════════════════════════════════════════════════════════════════
# §7 Franchise names never smuggle a banned token into copy
# ═════════════════════════════════════════════════════════════════════════════
def test_franchise_display_names_are_screened_against_the_house_vocab_guard():
    """Sophia's "Narrative Shift" contains a house-banned word.

    `copy_safe_name` records it, and the LLM payload withholds the label so the
    model is never instructed to type a token `banned_language()` would reject.
    """
    from engine.marketing import franchises as fr
    from engine.marketing.copywriter import banned_language

    shift = fr.by_id("sophia_narrative_shift")
    assert shift is not None
    assert banned_language(shift.display_name), "expected the house guard to flag this name"
    assert shift.copy_safe_name is False

    for f in fr.register():
        expected = not banned_language(f.display_name)
        assert f.copy_safe_name is expected, f"{f.id}: copy_safe_name is stale"


def test_llm_payload_withholds_an_unsafe_franchise_name():
    from engine.marketing import franchises as fr
    from engine.marketing.copywriter import _franchise_payload

    unsafe = fr.by_id("sophia_narrative_shift")
    payload = _franchise_payload({
        "franchise": {
            "display_name": unsafe.display_name,
            "contract": list(unsafe.contract),
            "copy_safe_name": unsafe.copy_safe_name,
            "requires_measured_input": False,
        }
    })
    assert payload is not None
    assert "name" not in payload, "an unsafe franchise name reached the drafter"
    assert payload["contract"], "the format was withheld along with the label"

    safe = fr.by_id("kelly_confirmation_check")
    payload2 = _franchise_payload({
        "franchise": {
            "display_name": safe.display_name,
            "contract": list(safe.contract),
            "copy_safe_name": safe.copy_safe_name,
            "requires_measured_input": False,
        }
    })
    assert payload2["name"] == "Confirmation Check"


def test_dial_zero_items_receive_no_codex_graft():
    """Review F13 — wire register gets NO persona-cognitive material.

    `expression_dial.PROFILES` puts wire/news/breaking/event/earnings at dial 0.
    `event` alone appears ~20x in every nightly plan, so a batch-level graft
    would attach a worldview to wire-register items on essentially every run —
    the deterministic pass would then strip and reject the voice it had just
    asked for, burning a fallback AND poisoning the `dial_fallbacks` signal.
    """
    from engine.marketing.copywriter import _codex_cards, _codex_payload

    cards = _codex_cards(["cici", "meagan"])
    assert cards, "no codex cards loaded — this test would pass vacuously"
    memory = {"cici": {"open_promises": [], "worn_out_phrases": ["a b c"]}}

    for kind in ("wire", "news", "breaking", "event", "earnings"):
        assert _codex_payload(
            {"account": "cici", "type": kind},
            codex_by_account=cards, memory_by_account=memory,
        ) is None, f"dial-0 kind {kind!r} received a codex graft"

    for kind in ("macro", "signal", "chart", "education", "watchlist"):
        got = _codex_payload(
            {"account": "cici", "type": kind},
            codex_by_account=cards, memory_by_account=memory,
        )
        assert got and got.get("worldview"), f"dial>0 kind {kind!r} lost its graft"

    # Fails CLOSED: an unresolvable account gets nothing.
    assert _codex_payload(
        {"account": "", "type": "macro"},
        codex_by_account=cards, memory_by_account={},
    ) is None


def test_no_batch_level_codex_graft_remains_in_the_system_prompt():
    """The graft must not sneak back onto the batch-level persona cards."""
    src = (ROOT / "engine/marketing/copywriter.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "write_posts_llm"
    )
    body = ast.unparse(fn)
    assert "persona_cards[_acct].update" not in body, (
        "the codex graft is back on the batch-level persona cards — dial-0 items in "
        "the same batch would see it again (review F13)"
    )
    assert "_codex_payload" in body, "the per-item dial-gated graft is missing"


def test_prompt_never_instructs_the_model_to_close_a_promise():
    """Review F20 — closing a loop is a deterministic act, not a writing instruction.

    "We said we'd update after the auction" plus a helpful model equals an
    invented auction result: AM-R1's exact failure mode.
    """
    src = (ROOT / "engine/marketing/copywriter.py").read_text(encoding="utf-8")
    assert "close one when the item allows" not in src
    assert "claim to resolve" in src, "the do-NOT-resolve instruction is missing"


def test_measured_input_rule_reaches_the_drafter_payload():
    from engine.marketing import franchises as fr
    from engine.marketing.copywriter import _franchise_payload

    mood = fr.by_id("meagan_mood_vs_money")
    payload = _franchise_payload({
        "franchise": {
            "display_name": mood.display_name,
            "contract": list(mood.contract),
            "copy_safe_name": mood.copy_safe_name,
            "requires_measured_input": True,
        }
    })
    assert "attributed" in payload["rule"].lower()


# ═════════════════════════════════════════════════════════════════════════════
# §8 The LLM may only DE-ESCALATE
# ═════════════════════════════════════════════════════════════════════════════
def test_deescalate_turns_a_pass_into_an_abstention():
    from engine.marketing import value_gate

    v = value_gate.evaluate("CBOE | tape check", "$CBOE at 285.10. Worth a look.", kind="chart")
    assert v.verdict == "pass"
    d = value_gate.deescalate(v, reason="sensitive_context", actor="llm_critic")
    assert d.verdict == "abstain"
    assert d.llm_deescalated is True
    assert any("sensitive_context" in r for r in d.reasons)


def test_no_function_in_the_value_gate_can_promote():
    """THE GUARD, CAPABILITY-SHAPED (review F14).

    Charter §2 amendment 9 + the house epistemics law: an LLM may veto and
    de-escalate, never originate or promote.

    The first cut scanned function NAMES for promote/escalate/upgrade — which
    catches a function called `promote()` and nothing else. A `_recheck()` that
    rebuilt a Verdict with `proof=True` would have sailed through while the test
    reported green. This version pins the CAPABILITY: every `Verdict(...)`
    construction must live in a blessed constructor, and the only one that runs
    after a critic speaks (`deescalate`) must hard-code `verdict="abstain"`.
    """
    src = (ROOT / "engine/marketing/value_gate.py").read_text(encoding="utf-8")
    tree = ast.parse(src)

    parent_fn: dict[ast.AST, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for child in ast.walk(node):
                parent_fn.setdefault(child, node.name)

    blessed = {"evaluate", "deescalate"}
    constructions: list[tuple[str, ast.Call]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "Verdict":
            constructions.append((parent_fn.get(node, "<module>"), node))

    assert constructions, "no Verdict construction found — the guard is scanning nothing"
    stray = [fn for fn, _ in constructions if fn not in blessed]
    assert stray == [], (
        f"Verdict is constructed outside the blessed constructors {sorted(blessed)}: {stray}"
    )

    # `deescalate` may only ever produce an abstention.
    for fn, call in constructions:
        if fn != "deescalate":
            continue
        kw = {k.arg: k.value for k in call.keywords}
        v = kw.get("verdict")
        assert isinstance(v, ast.Constant) and v.value == "abstain", (
            "deescalate() constructs a Verdict whose `verdict` is not the literal "
            "\"abstain\" — a critic must never be able to produce a pass"
        )

    # Name-shape kept as a cheap second net.
    names = {
        n.name for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    forbidden = {n for n in names if any(
        w in n.lower() for w in ("promote", "escalate", "upgrade", "approve")
    ) and not n.lower().startswith("deescalate")}
    assert forbidden == set(), f"a promotion path exists in the value gate: {forbidden}"

    # Behavioural: de-escalating can never raise verdict back to a pass.
    from engine.marketing import value_gate

    v = value_gate.evaluate("CBOE | tape check", "$CBOE at 285.10.", kind="chart")
    d = value_gate.deescalate(v, reason="x")
    assert value_gate.deescalate(d, reason="y").verdict == "abstain"


def test_verdict_is_immutable_including_its_nested_components():
    """Frozen protects the BINDINGS; the nested dicts need a deep copy (F15)."""
    from engine.marketing import value_gate

    v = value_gate.evaluate("CBOE | tape check", "$CBOE at 285.10.", kind="chart")
    with pytest.raises(Exception):
        v.proof = True  # type: ignore[misc]

    before = v.components["surplus"]["stat"]
    d = value_gate.deescalate(v, reason="sensitive_context")
    d.components["surplus"]["stat"] = "MUTATED"
    d.components["grip_devices"]["specific"] = "MUTATED"
    d.components.setdefault("deescalation_notes", []).append("x")
    assert v.components["surplus"]["stat"] == before, (
        "mutating a de-escalated verdict reached back into the original — the copy "
        "is shallow, so immutability stops at the first level"
    )
    assert "deescalation_notes" not in v.components


# ═════════════════════════════════════════════════════════════════════════════
# §9 Wiring — no new posting rails, no new kinds, no new pollers
# ═════════════════════════════════════════════════════════════════════════════
def test_desk_feed_creates_no_outbox_items_and_opens_no_write_handle():
    """ASSEMBLY, NOT A RAIL. Nothing here posts, queues, or writes."""
    sites = _write_call_sites("engine/marketing/desk_feed.py")
    assert sites == [], f"desk_feed opened a write handle: {sites}"

    tree = ast.parse((ROOT / "engine/marketing/desk_feed.py").read_text(encoding="utf-8"))
    calls = {
        n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "")
        for n in ast.walk(tree) if isinstance(n, ast.Call)
    }
    for forbidden in ("enqueue", "transition", "record_decision"):
        assert forbidden not in calls, f"desk_feed calls {forbidden}() — it is assembly, not a rail"


def test_franchises_module_opens_no_write_handle():
    assert _write_call_sites("engine/marketing/franchises.py") == []


def test_desk_feed_survives_a_broken_lane_without_blanking_the_feed(monkeypatch):
    """One broken lane must not delete a desk's whole day."""
    from engine.marketing import desk_feed

    def _boom(*a, **k):
        raise RuntimeError("movers store is corrupt")

    monkeypatch.setattr(desk_feed, "_lane_market_hours", _boom)
    feed = desk_feed.assemble(
        "flagship", now=_WED_0900_ET, cfg=_CFG,
        breaking_items=[_breaking_item()],
        studio_items=[{"id": "s1", "type": "signal", "headline": "Signal update"}],
    )
    assert feed.by_lane("breaking"), "a broken lane blanked an unrelated one"
    assert any("movers store is corrupt" in n for n in feed.notes)


def test_config_lane_weights_are_live_not_decorative():
    """A knob nobody reads is a lie in a config file.

    XG-W2's own arming note makes the point: a key exists so an operator can
    change behaviour WITHOUT a code edit. Prove the read actually happens.
    """
    from engine.marketing import desk_feed

    base = desk_feed.assemble(
        "flagship", now=_WED_0900_ET, cfg=_CFG,
        studio_items=[{"id": "s1", "type": "signal", "headline": "Signal update"}],
    )
    tuned = desk_feed.assemble(
        "flagship", now=_WED_0900_ET,
        cfg={**_CFG, "desk_feed": {"lane_weights": {"analysis": 999}}},
        studio_items=[{"id": "s1", "type": "signal", "headline": "Signal update"}],
    )
    b = base.by_lane("analysis")[0].score
    t = tuned.by_lane("analysis")[0].score
    assert t > b + 900, f"lane_weights config was ignored ({b} -> {t})"
    # And the tuned candidate now outranks everything.
    assert tuned.candidates[0].lane == "analysis"


def test_config_can_park_and_arm_a_franchise_without_a_code_change():
    """`franchises.disabled` / `enabled_overrides` are the arming lever."""
    from engine.marketing import franchises as fr

    fid = "cici_before_new_york_wakes"
    assert fid in {s.franchise_id for s in fr.open_slots("cici", now=_WED_HK_CASH)}

    parked = fr.open_slots(
        "cici", now=_WED_HK_CASH, cfg={"franchises": {"disabled": [fid]}}
    )
    assert fid not in {s.franchise_id for s in parked}, "franchises.disabled was ignored"

    # And a register-parked franchise can be ARMED from config.
    tea = "cici_tea_and_tickers"
    armed = fr.open_slots(
        "cici", now=_WED_HK_CASH, cfg={"franchises": {"enabled_overrides": {tea: True}}}
    )
    assert tea in {s.franchise_id for s in armed}, "enabled_overrides was ignored"


def test_committed_config_block_parses_and_matches_the_code_defaults():
    """The shipped config must load and name the lanes the code knows."""
    import yaml

    cfg = yaml.safe_load((ROOT / "config" / "marketing.yml").read_text(encoding="utf-8"))
    from engine.marketing import desk_feed

    block = cfg["desk_feed"]
    assert set(block["lane_weights"]) == set(desk_feed.LANES), (
        "config lane_weights and desk_feed.LANES disagree"
    )
    resolved = desk_feed._weights(cfg)
    for lane in desk_feed.LANES:
        assert resolved["lanes"][lane] == float(block["lane_weights"][lane])

    # THE VALUE GATE IS ARMED (2026-07-30), PER KIND.
    #
    # This assertion used to read `enforce is False` and it was the right pin
    # while the gate was unmeasured: XG-W2's precedent is that a publish gate
    # lands record-only and an operator arms it after reading a cycle. That cycle
    # has been read — and re-read, because the first reading counted 14
    # `grip:no_hook` abstentions that were an empty-headline bug rather than
    # editorial verdicts.
    #
    # What replaces the pin is the thing that actually protects the desks: arming
    # may never exceed the corpus. `enforce_kinds` must be a NON-EMPTY list, and
    # every kind in it must be one the committed corpus has observations for. A
    # future edit that arms `wire` or `reply` — kinds with zero observations —
    # fails here rather than silencing a lane on no evidence.
    vg = cfg["value_gate"]
    assert vg["enforce"] is True
    armed = vg.get("enforce_kinds")
    assert isinstance(armed, list) and armed, (
        "enforce_kinds must be an explicit non-empty list — an absent or empty "
        "list arms EVERY kind, including kinds the corpus has never seen"
    )
    measured = _corpus_kinds_with_stamped_verdicts()
    unmeasured = sorted(set(armed) - measured)
    assert not unmeasured, (
        f"armed kinds with no stamped observations in the corpus: {unmeasured}. "
        "Extend data/marketing/outbox/items.jsonl coverage before arming them, "
        "or drop them from enforce_kinds — zero observations buys zero authority."
    )

    assert cfg["persona_memory"]["retention_days"] > 7


def _corpus_kinds_with_stamped_verdicts() -> set:
    """Kinds the committed outbox corpus actually carries a gate verdict for.

    Read from the artifact rather than hard-coded, so the arming test tracks the
    corpus instead of a list someone has to remember to update.
    """
    import json

    path = ROOT / "data" / "marketing" / "outbox" / "items.jsonl"
    if not path.exists():
        return set()
    kinds = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(row, dict):
            continue
        verdict = (row.get("source") or {}).get("value_gate")
        if isinstance(verdict, dict) and verdict.get("verdict") in {"pass", "abstain"}:
            kind = (verdict.get("components") or {}).get("kind") or row.get("kind")
            if kind:
                kinds.add(str(kind))
    return kinds


def test_chronicle_seam_has_exactly_one_call_site():
    """Chronicle W1/W2 are UNBUILT; `_chronicle_context` is the single seam.

    Pinned so the future Chronicle-W2 injection helper has one place to land
    rather than a scatter of `pack()` calls to find.
    """
    src = (ROOT / "engine/marketing/desk_feed.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    pack_calls = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "pack"
    ]
    assert len(pack_calls) == 1, "context_pack.pack() is called from more than one place"
