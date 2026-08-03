"""W4a/W4b/W4c — the nightly ladder stops throwing away the day it publishes.

MASTERPLAN: research/X_GROWTH_SUPERINTELLIGENCE_MASTERPLAN_BY_FABLE.md §8.

WHAT WAS BROKEN (measured on the 2026-08-02 nightly, not inferred):

  * `plan_account(n_days=7, per_day=28)` booked a SEVEN-day ladder — 1,176 items
    across six enabled desks — while `outbox.emit_from_content_plan` takes only
    `D1-` slots and nothing reads a previous plan. 89% of every night's output
    was discarded by construction.
  * The cross-day cooldown pool was applied to the EMITTED day only, so an empty
    cooled pool dropped a D1 rung while the never-published days kept filling
    from the uncooled pool — the one day that ships was the only day that could
    starve.
  * Kelly has never posted once, ever. Her sole D1 item on 2026-08-02 was a
    `theme_list`, which `sentinel.ramp.weeks_1_2.theme_list_allowed: false` kills
    at plan-build. The planner spent her only at-bat on a banned format.
  * `report["dropped_cooldown"]` — the largest volume sink in the allocator —
    was written into a caller-supplied dict and never reached the plan `summary`.

WHAT IS NOT ALLOWED TO CHANGE, and is pinned below: an empty cooled pool still
DROPS the rung. It must never fall back to the uncooled pool, which would
publish exactly the repetition the cooldown exists to stop (masterplan §5.5).
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent

from engine.marketing import content_studio as cs  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

# `plan_account` -> `postable_signals` reads the WALL CLOCK for signal age, so
# the fixture date is derived from it. A pinned literal here would pass today and
# silently turn every ticker assertion below vacuous the day it aged out
# (memory: fixture-date-plus-wall-clock-gate-bomb).
_YESTERDAY = (date.today() - timedelta(days=1)).isoformat()

_YESTERDAY_PLANS = [
    {"id": f"{t}-BULL", "asset": t, "direction": "BULL", "entry": 60.0,
     "targets": [70.0], "phase": "triggered_pre_t1", "recommended_action": "hold",
     "management_confidence": 70.0, "_signal_date": _YESTERDAY}
    for t in ("AAA", "BBB", "CCC", "DDD")
]


def test_the_fixture_plans_are_actually_postable():
    """If the eligibility gate rejects the fixture, every ticker assertion in
    this file passes for the wrong reason."""
    assert len(cs.postable_signals(_YESTERDAY_PLANS)) == len(_YESTERDAY_PLANS)


def _acct(acct_id: str = "kelly") -> dict:
    return {"id": acct_id, "kind": "persona", "voice": "authoritative desk",
            "enabled": True}


def _ramp_cfg(*, theme_list_allowed: bool, cap: int = 10) -> dict:
    """A config whose ONLY enabled desk sits on a tier we control."""
    return {
        "desk_network": {"stage": "A", "accounts": [
            {"id": "kelly", "kind": "persona", "beat": "US equities",
             "voice": "authoritative desk", "enabled": True,
             "created": "2099-01-01"},   # far future ⇒ resolve_ramp fails closed
        ]},
        "sentinel": {
            "max_posts_per_account_per_day": -1,
            "ramp": {
                "graduate_after_days": 56,
                "weeks_1_2": {
                    "max_posts_per_account_per_day": cap,
                    "theme_list_allowed": theme_list_allowed,
                },
            },
        },
    }


def _caps_for(cfg: dict, acct_id: str = "kelly", as_of: str = "2026-08-02",
              root=None) -> dict:
    from engine.marketing.sentinel import resolve_ramp
    ramp = resolve_ramp(cfg, as_of, root=root, announce=False)
    entry = (ramp.get("accounts") or {}).get(acct_id)
    return dict(entry.get("caps") if entry else (ramp.get("fallback") or {}))


# ─────────────────────────────────────────────────────────────────────────────
# W4a — the ladder is ONE day
# ─────────────────────────────────────────────────────────────────────────────

def test_the_default_ladder_is_one_day():
    """THE COLLAPSE. Every rung the allocator books must be an EMIT rung.

    Pre-fix this was `n_days=7`: six of every seven items were generated,
    charted, sometimes written by a paid model, and then discarded by
    `emit_from_content_plan`'s `D1-` filter.
    """
    items = cs.plan_account(_acct(), _YESTERDAY_PLANS, per_day=6)
    assert items, "allocator produced nothing — the guard would be vacuous"
    days = sorted({i.slot.split("-", 1)[0] for i in items})
    assert days == ["D1"], (
        f"the allocator still books a forward ladder ({days}); every one of "
        "those rungs is discarded by outbox.emit_from_content_plan")


def test_forward_days_reads_config_and_floors_at_one():
    assert cs.forward_days(None) == 1
    assert cs.forward_days({}) == 1
    assert cs.forward_days({"content_plan": {}}) == 1
    assert cs.forward_days({"content_plan": {"forward_days": 3}}) == 3
    # Junk and absurd values take the CODE default rather than reintroducing a
    # forward ladder by accident.
    assert cs.forward_days({"content_plan": {"forward_days": 0}}) == 1
    assert cs.forward_days({"content_plan": {"forward_days": -4}}) == 1
    assert cs.forward_days({"content_plan": {"forward_days": "banana"}}) == 1
    assert cs.forward_days({"content_plan": {"forward_days": None}}) == 1


def test_per_day_headroom_reads_config_and_floors_at_one():
    assert cs.per_day_headroom({}) == cs._DEFAULT_PER_DAY_HEADROOM
    assert cs.per_day_headroom({"content_plan": {"per_day_headroom": 1.5}}) == 1.5
    # Below 1.0 would book FEWER rungs than the desk is allowed to post.
    assert cs.per_day_headroom(
        {"content_plan": {"per_day_headroom": 0.4}}) == cs._DEFAULT_PER_DAY_HEADROOM
    assert cs.per_day_headroom(
        {"content_plan": {"per_day_headroom": "x"}}) == cs._DEFAULT_PER_DAY_HEADROOM


def test_the_forward_days_knob_is_actually_threaded(tmp_path):
    """The knob has to reach `plan_account`, not just parse."""
    cfg = _ramp_cfg(theme_list_allowed=True)
    cfg["content_plan"] = {"forward_days": 3}
    shape = cs.ladder_shape_for(cfg, "kelly", "2026-08-02", root=tmp_path)
    assert shape["n_days"] == 3, shape
    items = cs.plan_account(_acct(), _YESTERDAY_PLANS, n_days=shape["n_days"],
                            per_day=shape["per_day"])
    assert sorted({i.slot.split("-", 1)[0] for i in items}) == ["D1", "D2", "D3"]


@pytest.mark.parametrize("cap,headroom,expect", [
    (10, 2.0, 20),      # weeks_1_2 — the shipped tier
    (20, 2.0, 28),      # flagship's override, clamped to the 28-rung ladder
    (14, 2.0, 28),      # weeks_3_4, also clamped
    (10, 1.5, 15),
    (7, 1.6, 12),       # ceil, never floor: a fractional rung still gets booked
    (2, 2.0, 9),        # the structural floor — see _MIN_LADDER_RUNGS
    (1, 1.0, 9),
])
def test_per_day_is_sized_to_the_ramp_cap(tmp_path, cap, headroom, expect):
    """`per_day` follows the desk's OWN cap, not a flat 28.

    Generating 28 rungs for a desk allowed 10 posts is the same waste as the
    7-day ladder, in miniature.
    """
    cfg = _ramp_cfg(theme_list_allowed=True, cap=cap)
    cfg["content_plan"] = {"per_day_headroom": headroom}
    shape = cs.ladder_shape_for(cfg, "kelly", "2026-08-02", root=tmp_path)
    assert shape == {"n_days": 1, "per_day": expect}


def test_the_rung_floor_keeps_every_content_family_in_the_plan(tmp_path):
    """A cap-sized ladder must still be able to EXPRESS the tilt.

    The in-code sentinel default is 2 posts/day — a launch floor, not a working
    cadence — so a caller with no `sentinel:` block (a test, an admin preview)
    would be handed 4 rungs for a nine-kind tilt and four of the nine families
    would vanish from the plan without a word.
    """
    cfg = {"desk_network": {"stage": "A", "accounts": [
        {"id": "kelly", "kind": "persona", "voice": "authoritative desk",
         "enabled": True}]},
        "sentinel": {"max_posts_per_account_per_day": 2}}
    shape = cs.ladder_shape_for(cfg, "kelly", "2026-08-02", root=tmp_path)
    assert shape["per_day"] >= len(cs._TYPE_IDS), shape

    tilt = {t: w for t, w in cs._DEFAULT_TILT.items() if w > 0}
    items = cs.plan_account(_acct(), _YESTERDAY_PLANS, tilt=tilt, **shape)
    assert {i.type for i in items} == set(tilt), (
        f"content families left the plan silently: "
        f"{sorted(set(tilt) - {i.type for i in items})}")


def test_a_short_ladder_still_gives_every_live_kind_a_rung():
    """`_largest_remainder`'s ≥1 guarantee was DEAD CODE.

    Its `sum(floors) < total_slots` condition can never be true after the
    remainder pass, so the guarantee was carried entirely by the allocation
    being 196 slots wide. At the one-day ladder a 0.05-weight kind rounds to
    zero and the family disappears.
    """
    tilt = {"signal": 0.60, "chart": 0.20, "macro": 0.08, "receipt": 0.05,
            "watchlist": 0.04, "event": 0.03}
    alloc = cs._largest_remainder(tilt, len(tilt))
    assert min(alloc.values()) >= 1, alloc
    assert sum(alloc.values()) == len(tilt), alloc

    alloc20 = cs._largest_remainder(tilt, 20)
    assert min(alloc20.values()) >= 1, alloc20
    assert sum(alloc20.values()) == 20


def test_a_zero_weight_kind_is_never_resurrected():
    """0.00 means OFF, not "rare" — education was closed by operator ruling.

    The ≥1 pass must not hand a slot to a family the operator turned off.
    """
    assert cs._DEFAULT_TILT["education"] == 0.0, (
        "fixture drifted: education is no longer the off-by-ruling kind")
    for total in (9, 12, 20, 28):
        alloc = cs._largest_remainder(dict(cs._DEFAULT_TILT), total)
        assert alloc.get("education", 0) == 0, (total, alloc)
        assert sum(alloc.values()) == total


def test_an_unlimited_cap_books_the_whole_ladder(tmp_path):
    """No cap to size against ⇒ nothing is trimmed (pre-W4a behaviour)."""
    cfg = {"desk_network": {"stage": "A", "accounts": [
        {"id": "kelly", "kind": "persona", "voice": "authoritative desk",
         "enabled": True}]},
        "sentinel": {"max_posts_per_account_per_day": -1}}
    shape = cs.ladder_shape_for(cfg, "kelly", "2026-08-02", root=tmp_path)
    assert shape["per_day"] == len(cs._LADDER_SLOTS)


def test_ladder_shape_fails_soft_to_the_full_ladder(tmp_path, monkeypatch):
    """A cap lookup that EXPLODES must not shrink a desk's day to nothing."""
    import engine.marketing.outbox as ob

    def _boom(*a, **k):
        raise RuntimeError("ledger unreadable")

    monkeypatch.setattr(ob, "effective_cap_for", _boom)
    shape = cs.ladder_shape_for(_ramp_cfg(theme_list_allowed=True), "kelly",
                                "2026-08-02", root=tmp_path)
    assert shape["per_day"] == len(cs._LADDER_SLOTS), shape


# ─────────────────────────────────────────────────────────────────────────────
# W4a — the line between "removing waste" and "weakening a gate"
# ─────────────────────────────────────────────────────────────────────────────

def test_an_empty_cooled_pool_drops_the_rung_and_never_falls_back():
    """THE FENCE. Every eligible name cooled ⇒ the rung stays EMPTY.

    Falling back to the uncooled pool would publish precisely the repetition the
    cross-day cooldown exists to stop (masterplan §5.5). This is the assertion
    that separates W4a from a volume hack, so it is written in both directions:
    cooled ⇒ nothing, uncooled ⇒ something.
    """
    cooled = frozenset({"AAA", "BBB", "CCC", "DDD"})
    report: dict = {}
    items = cs.plan_account(_acct(), _YESTERDAY_PLANS, per_day=28,
                            cooled_watch=cooled, cooled_signal=cooled,
                            report=report)
    assert not [i for i in items if i.ticker], (
        "a fully-cooled pool still produced ticker posts — the allocator fell "
        "back to the uncooled pool")
    assert report["dropped_cooldown"] > 0, (
        "rungs vanished without incrementing the counter")

    free = cs.plan_account(_acct(), _YESTERDAY_PLANS, per_day=28)
    assert [i for i in free if i.ticker], (
        "GUARD IS VACUOUS: the allocator mints no ticker posts even uncooled")


def test_the_cooldown_reaches_every_rung_the_planner_books():
    """THE INVERSION (masterplan §8.1 V1).

    The cooldown pool is applied to `emit_day_prefix` slots only. On a 7-day
    ladder that meant a cooled ticker was refused a D1 rung and then handed
    D2..D7 rungs from the uncooled pool — the emitted day was the ONLY day that
    could starve. At the shipped one-day shape every rung is an emit rung, so a
    cooled name cannot reappear anywhere in the plan.
    """
    cooled = frozenset({"AAA"})
    items = cs.plan_account(_acct(), _YESTERDAY_PLANS, per_day=28,
                            cooled_watch=cooled, cooled_signal=cooled)
    assert items, "vacuous — no items at all"
    assert not [i for i in items if i.ticker == "AAA"], (
        "a cooled ticker still reached a rung: "
        f"{sorted({(i.slot, i.ticker) for i in items if i.ticker == 'AAA'})}")


# ─────────────────────────────────────────────────────────────────────────────
# W4b — a banned format gets ZERO allocation, not an allocation that dies later
# ─────────────────────────────────────────────────────────────────────────────

def test_ramp_banned_kinds_reads_only_an_explicit_false():
    assert cs.ramp_banned_kinds({"theme_list_allowed": False}) == frozenset({"theme_list"})
    assert cs.ramp_banned_kinds({"theme_list_allowed": True}) == frozenset()
    # A MISSING key is "no opinion" (a pre-ramp config), never a ban — inventing
    # one would delete a format network-wide on a config that never mentions it.
    assert cs.ramp_banned_kinds({}) == frozenset()
    assert cs.ramp_banned_kinds(None) == frozenset()


def test_a_banned_format_gets_zero_allocation(tmp_path):
    """THE KELLY CASE. A tier that forbids theme_list must never be handed one.

    Written in both directions on the SAME desk and the SAME tilt, so it cannot
    pass by the format simply being rare.
    """
    banned_cfg = _ramp_cfg(theme_list_allowed=False)
    allowed_cfg = _ramp_cfg(theme_list_allowed=True)

    banned = cs.ramp_banned_kinds_for(banned_cfg, "kelly", "2026-08-02", root=tmp_path)
    allowed = cs.ramp_banned_kinds_for(allowed_cfg, "kelly", "2026-08-02", root=tmp_path)
    assert banned == frozenset({"theme_list"}), banned
    assert allowed == frozenset(), allowed

    off = cs.plan_account(_acct(), _YESTERDAY_PLANS, per_day=28, banned_kinds=banned)
    on = cs.plan_account(_acct(), _YESTERDAY_PLANS, per_day=28, banned_kinds=allowed)
    assert not [i for i in off if i.type == "theme_list"], (
        "the planner still spends rungs on a format this tier quarantines")
    assert [i for i in on if i.type == "theme_list"], (
        "GUARD IS VACUOUS: the allocator plans no theme_list even when allowed")


def test_the_ban_moves_an_at_bat_it_does_not_delete_one(tmp_path):
    """The banned weight is RENORMALISED, so the desk keeps its volume."""
    banned = cs.ramp_banned_kinds_for(_ramp_cfg(theme_list_allowed=False),
                                      "kelly", "2026-08-02", root=tmp_path)
    off = cs.plan_account(_acct(), _YESTERDAY_PLANS, per_day=28, banned_kinds=banned)
    on = cs.plan_account(_acct(), _YESTERDAY_PLANS, per_day=28)
    assert len(off) == len(on), (
        f"the ban cost the desk {len(on) - len(off)} rung(s); it is supposed to "
        "move the at-bat to a shippable format, not delete it")


def test_the_ban_is_recorded_by_account(tmp_path):
    """A silent reallocation is unauditable; the report names the desk + weight."""
    banned = cs.ramp_banned_kinds_for(_ramp_cfg(theme_list_allowed=False),
                                      "kelly", "2026-08-02", root=tmp_path)
    report: dict = {}
    cs.plan_account(_acct(), _YESTERDAY_PLANS, per_day=28, banned_kinds=banned,
                    report=report)
    row = (report.get("ramp_banned_kinds") or {}).get("kelly")
    assert row and row["kinds"] == ["theme_list"], report
    assert row["weight_reallocated"] > 0, row


def test_a_tier_that_bans_everything_is_refused_and_announced(capsys):
    """A config that permits NOTHING is a config bug, not a plan of zero posts."""
    report: dict = {}
    items = cs.plan_account(_acct(), _YESTERDAY_PLANS, per_day=8,
                            banned_kinds=frozenset(cs._TYPE_IDS), report=report)
    assert items, "the desk was silently emptied by a nonsense ramp"
    assert report["ramp_ban_refused"] == 1
    lines = capsys.readouterr().out.splitlines()
    hits = [ln for ln in lines
            if ln.startswith("::warning") and "marketing-ramp-bans-every-kind" in ln]
    assert hits, (
        "no start-of-line ::warning — a logger prefixes the line and GitHub "
        "drops the annotation silently (tests/test_gh_annotation_line_start.py)")


def test_ramp_banned_kinds_for_fails_soft(tmp_path, monkeypatch):
    """A tier read that explodes bans NOTHING — the pre-W4b behaviour.

    Failing closed here would silently delete a whole format from every desk on
    any resolution hiccup: a bigger and quieter change than the guard itself.
    """
    import engine.marketing.sentinel as sentinel

    def _boom(*a, **k):
        raise RuntimeError("ramp table unreadable")

    monkeypatch.setattr(sentinel, "resolve_ramp", _boom)
    assert cs.ramp_banned_kinds_for(_ramp_cfg(theme_list_allowed=False), "kelly",
                                    "2026-08-02", root=tmp_path) == frozenset()


def test_no_permission_knob_in_the_table_is_missing_from_the_caps(tmp_path):
    """Every knob `_RAMP_KIND_PERMISSION` keys on must EXIST in a resolved cap
    set — otherwise the ban is dead code that reviews as a guard.
    """
    caps = _caps_for(_ramp_cfg(theme_list_allowed=False), root=tmp_path)
    for kind, flag in cs._RAMP_KIND_PERMISSION.items():
        assert flag in caps, (
            f"_RAMP_KIND_PERMISSION[{kind!r}] reads {flag!r}, which no resolved "
            f"ramp cap set carries: {sorted(caps)}")


# ─────────────────────────────────────────────────────────────────────────────
# The SHIPPED config — the defect as it actually stands tonight
# ─────────────────────────────────────────────────────────────────────────────

def test_on_the_shipped_config_no_cold_desk_is_planned_a_banned_format():
    """END-TO-END on config/marketing.yml + the real ramp table.

    Non-vacuous by construction: the test first proves at least one enabled desk
    IS on a theme_list-banning tier AND that the pre-fix allocator planned that
    format for it, then proves the shipped path plans none.
    """
    from engine.marketing.accounts import effective_accounts
    from engine.marketing.sentinel import resolve_ramp

    cfg = yaml.safe_load((ROOT / "config" / "marketing.yml").read_text(encoding="utf-8"))
    as_of = "2026-08-02"
    ramp = resolve_ramp(cfg, as_of, root=ROOT, announce=False)
    enabled = [a for a in effective_accounts(cfg, ROOT) if a.get("enabled")]
    assert enabled, "fixture needs at least one enabled desk"

    cold = [a for a in enabled
            if "theme_list" in cs.ramp_banned_kinds_for(cfg, a["id"], as_of,
                                                        root=ROOT, ramp=ramp)]
    assert cold, (
        "VACUOUS: no enabled desk sits on a theme_list-banning tier, so this "
        "test could not observe the defect it pins")

    for acct in cold:
        tilt = acct.get("tilt") or None
        pre_fix = cs.plan_account(account=acct, plans=[], n_days=1, per_day=28,
                                  seed=0, tilt=tilt)
        assert [i for i in pre_fix if i.type == "theme_list"], (
            f"VACUOUS for {acct['id']}: the allocator plans no theme_list even "
            "without the ban, so the ban cannot be what removes it")

        shipped = cs.plan_account(
            account=acct, plans=[], seed=0, tilt=tilt,
            **cs.ladder_shape_for(cfg, acct["id"], as_of, root=ROOT, ramp=ramp),
            banned_kinds=cs.ramp_banned_kinds_for(cfg, acct["id"], as_of,
                                                  root=ROOT, ramp=ramp))
        assert not [i for i in shipped if i.type == "theme_list"], (
            f"{acct['id']} is still handed a theme_list rung its D08 tier "
            "quarantines (sentinel reason `ramp_theme_list`)")


def test_the_shipped_config_stops_generating_what_it_discards():
    """The 89%: the whole network's allocation, before vs after."""
    from engine.marketing.accounts import effective_accounts
    from engine.marketing.sentinel import resolve_ramp

    cfg = yaml.safe_load((ROOT / "config" / "marketing.yml").read_text(encoding="utf-8"))
    as_of = "2026-08-02"
    ramp = resolve_ramp(cfg, as_of, root=ROOT, announce=False)
    enabled = [a for a in effective_accounts(cfg, ROOT) if a.get("enabled")]

    before = after = 0
    for acct in enabled:
        tilt = acct.get("tilt") or None
        before += len(cs.plan_account(account=acct, plans=[], n_days=7,
                                      per_day=len(cs._LADDER_SLOTS), seed=0,
                                      tilt=tilt))
        after += len(cs.plan_account(
            account=acct, plans=[], seed=0, tilt=tilt,
            **cs.ladder_shape_for(cfg, acct["id"], as_of, root=ROOT, ramp=ramp),
            banned_kinds=cs.ramp_banned_kinds_for(cfg, acct["id"], as_of,
                                                  root=ROOT, ramp=ramp)))

    assert before > 0 and after > 0
    # Every desk still gets AT LEAST its own daily cap in rungs — the point is
    # to stop generating a week nobody reads, never to shrink the day.
    assert after <= before / 4, (
        f"the ladder still generates {after} items where the emitted day needs "
        f"a fraction of {before}")


def test_every_desk_still_gets_at_least_its_daily_cap_in_rungs():
    """The trim must never book FEWER rungs than the desk may post.

    This is the guard that would catch a headroom knob set below 1.0, or a cap
    lookup that resolved to the wrong desk.
    """
    from engine.marketing.accounts import effective_accounts
    from engine.marketing.outbox import effective_cap_for
    from engine.marketing.sentinel import resolve_ramp

    cfg = yaml.safe_load((ROOT / "config" / "marketing.yml").read_text(encoding="utf-8"))
    as_of = "2026-08-02"
    ramp = resolve_ramp(cfg, as_of, root=ROOT, announce=False)
    for acct in effective_accounts(cfg, ROOT):
        if not acct.get("enabled"):
            continue
        cap = effective_cap_for(cfg, acct["id"], as_of, root=ROOT, ramp=ramp)
        shape = cs.ladder_shape_for(cfg, acct["id"], as_of, root=ROOT, ramp=ramp)
        if cap < 0:
            continue
        assert shape["per_day"] >= min(cap, len(cs._LADDER_SLOTS)), (
            f"{acct['id']}: booked {shape['per_day']} rungs for a desk allowed "
            f"{cap} posts/day")


# ─────────────────────────────────────────────────────────────────────────────
# W4c — the drop counter is PERSISTED, and says so out loud
# ─────────────────────────────────────────────────────────────────────────────

def _plan_cfg() -> dict:
    return {"desk_network": {"stage": "A", "accounts": [
        {"id": "flagship", "kind": "branded", "beat": "US equities",
         "voice": "authoritative desk", "enabled": True},
    ]}}


def test_the_plan_summary_carries_the_planner_funnel(tmp_path):
    """`dropped_cooldown` used to live only in a caller-supplied dict.

    Same defect class as the mover bug that hid for 12 nights: the counter
    existed, nothing read it, and the artifact a postmortem opens said nothing.
    """
    plan = cs.content_plan(_plan_cfg(), [], closes_loader=None, root=tmp_path)
    summary = plan["summary"]
    for key in ("forward_days", "slots_offered", "dropped_cooldown",
                "dropped_cooldown_by_account", "ramp_banned_kinds"):
        assert key in summary, (
            f"summary lost {key!r} — the planner's own funnel is invisible in "
            f"the artifact: {sorted(summary)}")
    assert summary["forward_days"] == 1
    assert summary["slots_offered"] > 0, (
        "slots_offered is the DENOMINATOR: without it a drop count cannot be "
        "read as healthy or broken")

    sel = plan["content"]["selection"]
    assert sel["slots_offered"] == summary["slots_offered"]
    assert sel["dropped_cooldown"] == summary["dropped_cooldown"]
    assert isinstance(sel["ladder_shape"], dict) and sel["ladder_shape"]


def test_the_summary_survives_a_json_round_trip(tmp_path):
    """The governor writes the artifact with `json.dump` — a frozenset or a
    Counter in there would raise at write time, on the nightly, at 2am."""
    plan = cs.content_plan(_plan_cfg(), [], closes_loader=None, root=tmp_path)
    reloaded = json.loads(json.dumps(plan["summary"]))
    assert reloaded["forward_days"] == 1


def test_a_starved_ladder_annotates_at_line_start(capsys):
    """Bare `print`, line-start, flush — never through a logger (CI-guarded)."""
    cs._alarm_on_cooldown_starvation({
        "slots_offered": 100,
        "dropped_cooldown": 40,
        "dropped_cooldown_by_account": {"kelly": 25, "cici": 15},
    })
    lines = capsys.readouterr().out.splitlines()
    hits = [ln for ln in lines
            if ln.startswith("::warning")
            and "marketing-plan-cooldown-starved" in ln]
    assert hits, (
        "no start-of-line ::warning for a starved ladder — this module's logger "
        "prefixes the level, so an annotation emitted through it is silently "
        "dropped by GitHub (tests/test_gh_annotation_line_start.py)")
    assert "kelly" in hits[0], "the annotation does not name the worst desk"


@pytest.mark.parametrize("offered,dropped", [(0, 0), (100, 0), (100, 24)])
def test_a_healthy_ladder_stays_quiet(capsys, offered, dropped):
    """Two alarms for one cause trains the reader to skim both."""
    cs._alarm_on_cooldown_starvation({"slots_offered": offered,
                                      "dropped_cooldown": dropped})
    assert "cooldown-starved" not in capsys.readouterr().out


# ─────────────────────────────────────────────────────────────────────────────
# W4f — a wire desk drafts NOTHING in the nightly persona plan
# ─────────────────────────────────────────────────────────────────────────────

def _wire_cfg() -> dict:
    """A drafting desk and a persona-less WIRE desk that share a voice key.

    The shared voice is the whole point: it is the exact config that armed
    mastermind_news on 2026-08-02 (voice "fast, reactive", founder's key, no
    `copywriter.personas` block), and the collision it would have caused.
    """
    return {
        "copywriter": {"personas": {"flagship": {"voice_notes": "x"}}},
        "desk_network": {"stage": "A", "accounts": [
            {"id": "flagship", "kind": "branded", "beat": "US equities",
             "voice": "authoritative desk", "enabled": True},
            {"id": "mastermind_news", "kind": "branded", "beat": "the wire",
             "voice": "authoritative desk", "enabled": True},
        ]},
    }


def test_a_persona_less_desk_gets_an_empty_nightly_queue(tmp_path):
    """The wire desk is ARMED and still drafts nothing here.

    Without this pin the scoping in
    tests/test_marketing_chart_coverage.py::test_every_enabled_desk_has_its_own_template_bank
    would be an unbacked assumption: that guard excludes persona-less desks
    because content_plan is supposed to skip them, and a guard resting on a
    behaviour nothing checks is the vacuous-green trap this repo has paid for
    before. Mutation: delete the `_drafts_nightly_copy` branch in content_plan
    and this goes red while every voice-string guard stays green.
    """
    plan = cs.content_plan(_wire_cfg(), [], closes_loader=None, root=tmp_path)
    rows = {a["id"]: a for a in plan["accounts"]}

    assert "mastermind_news" in rows, (
        "the wire desk vanished from the plan entirely — it must still be LISTED "
        "with its tilt so the admin can show the intended mix")
    wire = rows["mastermind_news"]
    assert wire["queue"] == [], (
        f"the wire desk drafted {len(wire['queue'])} nightly items. It has no "
        f"copywriter.personas block, so _get_copy can only hand it another "
        f"desk's bank — here the flagship's — and the cross-account near-dup "
        f"guard then quarantines whichever desk the gate reaches second.")
    assert wire["status"] == "wire", (
        f"status {wire['status']!r}: a wire desk is not 'planned' (that means "
        f"not enabled) and not 'active' — the artifact must say which it is")
    assert wire.get("tilt"), "the wire desk lost its tilt — the admin mix goes blank"

    # ...and the drafting desk in the SAME config is untouched. Without this the
    # test would also pass if content_plan simply stopped drafting for everyone.
    assert rows["flagship"]["queue"], (
        "the drafting desk drafted nothing either — the skip is too wide")


def test_the_wire_skip_keys_on_the_persona_block_not_the_kind(tmp_path):
    """`kind: branded` covers the flagship and the founder, both of which draft.

    Keying the skip on `kind` would mute the flagship. Pinned because it is the
    obvious wrong discriminator and the two desks are indistinguishable by kind.
    """
    cfg = _wire_cfg()
    assert cfg["desk_network"]["accounts"][0]["kind"] == "branded"
    assert cfg["desk_network"]["accounts"][1]["kind"] == "branded"

    assert cs._drafts_nightly_copy(cfg, "flagship") is True
    assert cs._drafts_nightly_copy(cfg, "mastermind_news") is False


def test_an_unreadable_personas_block_fails_open(tmp_path):
    """A config we cannot parse must not silently mute every desk in the network."""
    for bad in ({}, {"copywriter": {}}, {"copywriter": {"personas": None}},
                {"copywriter": {"personas": []}}, {"copywriter": None}):
        assert cs._drafts_nightly_copy(bad, "flagship") is True, (
            f"{bad!r} muted a desk — a persona block we cannot read is not "
            f"evidence that the desk is a wire relay")
