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
# 18:00 UTC = 02:00 Thursday in Hong Kong — outside both her windows.
_WED_HK_ASLEEP = datetime(2026, 7, 22, 18, 0, 0, tzinfo=timezone.utc)

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
        for key in ("recent_posts", "open_promises", "phrase_fatigue", "relations"):
            assert key in pm, f"{lane}: persona memory missing {key}"


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
    """Cici files Asia, not the US afternoon — the territory clock is the point."""
    from engine.marketing import desk_feed

    inside = desk_feed.assemble(
        "cici", now=_WED_HK_CASH, cfg=_CFG, movers=[{"ticker": "0700.HK", "pct": 3.1}]
    )
    assert inside.by_lane("market_hours"), "the market-hours lane was silent inside her session"

    outside = desk_feed.assemble(
        "cici", now=_WED_HK_ASLEEP, cfg=_CFG, movers=[{"ticker": "0700.HK", "pct": 3.1}]
    )
    assert outside.by_lane("market_hours") == ()
    assert "outside_window" in {a.reason for a in outside.abstentions}


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
    allowed = {"_append_host", "_write_tracked", "consolidate"}
    offenders = [(fn, src) for fn, src in sites if fn not in allowed]
    assert offenders == [], f"write handle outside the allowlisted writers: {offenders}"

    # And `_write_tracked` is called from `consolidate` alone.
    tree = ast.parse((ROOT / "engine/marketing/persona_memory.py").read_text(encoding="utf-8"))
    callers = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for child in ast.walk(node):
                if isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
                    if child.func.id == "_write_tracked":
                        callers.add(node.name)
    assert callers == {"consolidate"}, (
        f"_write_tracked is reachable from {callers or 'nothing'}; only consolidate() may advance "
        "a tracked ledger (nightly-sole-advancer law)"
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
    """THE GUARD. A critic may veto; it may never promote.

    Charter §2 amendment 9 + the house epistemics law (LLMs may only de-escalate
    calibrated keys — never originate signals, scores, or escalations).
    """
    tree = ast.parse((ROOT / "engine/marketing/value_gate.py").read_text(encoding="utf-8"))
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


def test_verdict_is_immutable():
    """A caller must not be able to flip an element after the fact."""
    from engine.marketing import value_gate

    v = value_gate.evaluate("CBOE | tape check", "$CBOE at 285.10.", kind="chart")
    with pytest.raises(Exception):
        v.proof = True  # type: ignore[misc]


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

    # The value gate lands RECORD-ONLY, per the XG-W2 arming precedent.
    assert cfg["value_gate"]["enforce"] is False
    assert cfg["persona_memory"]["retention_days"] > 7


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
