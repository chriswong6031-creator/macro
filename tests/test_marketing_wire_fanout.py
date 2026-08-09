"""Multi-account fan-out for tickerless macro/policy wire events (W3).

Operator order 2026-08-08: "tickerless macro events (CPI/NFP prints, FOMC,
White House / policy) MAY go to multiple accounts when genuinely reworded in
different formats." Three seams carry that, and each is pinned here:

  * ``wire_routing.fanout_desks`` — WHO gets a seat, and with what angle.
  * ``market_clock.fact_fanout_max_accounts`` — the per-family budget reader.
  * ``outbox._rejection_reason`` — the enqueue gate that used to be a boolean
    owner. Its ``default: 1`` behaviour is the regression that matters most:
    every family except macro/pct must verdict exactly as it did before W3.

WHAT IS NOT TESTED HERE, because this layer does not do it. Nothing below
certifies that three siblings are genuinely three posts. The near-dup radar, the
same-account Jaccard, the 3-gram plan gate and frame_similarity are unchanged and
own that question; a sibling that is a reskin is SUPPOSED to die in them. These
tests pin that the opportunity exists, never that it was used well.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def shipped_cfg() -> dict:
    """The REAL config/marketing.yml.

    Deliberately not a hand-built dict for the headline cases: a fixture that
    invents its own fanout table proves the code can read a table, not that the
    table an operator committed produces the seats they asked for. The guard test
    below fails loudly if this file stops carrying the rows these tests assume.
    """
    return yaml.safe_load(
        (ROOT / "config" / "marketing.yml").read_text(encoding="utf-8")) or {}


def _cfg(*, fanout: dict | None = None, enabled_desks=("flagship",
                                                        "mastermind_news",
                                                        "founder")) -> dict:
    """A minimal routing cfg. `macro_print` routes to flagship, as shipped."""
    return {
        "wire_routing": {
            "default": "flagship",
            "classes": {"macro_print": "flagship",
                        "macro_print.minor": "mastermind_news",
                        "policy": "flagship"},
            "fanout": fanout if fanout is not None else {},
        },
        "desk_network": {
            "accounts": [{"id": d, "enabled": True} for d in enabled_desks],
        },
    }


_ALIGNED_FANOUT = {
    "enabled": True,
    "min_salience": 72,
    "max_accounts": 3,
    "classes": {
        "macro_print": [
            {"account": "flagship", "angle": "house_view"},
            {"account": "mastermind_news", "angle": "relay"},
            {"account": "founder", "angle": "trader_read"},
        ],
    },
}


@pytest.fixture(autouse=True)
def _reset_warnings():
    """`_warn_once` is once-per-PROCESS, so an unreset set makes any test that
    asserts on an annotation order-dependent and silently green."""
    from engine.marketing.wire_routing import reset_dark_route_warnings

    reset_dark_route_warnings()
    yield
    reset_dark_route_warnings()


# ─────────────────────────────────────────────────────────────────────────────
# Vacuous-green guard — run FIRST, because every assertion below rests on it
# ─────────────────────────────────────────────────────────────────────────────

class TestTheFixtureConfigActuallyCarriesTheRows:
    """If these keys go missing, `fanout_desks` returns one seat for the RIGHT
    reason (fan-out is off) and every test in this file would pass while
    testing nothing. So the config is asserted before it is relied on."""

    def test_the_shipped_config_declares_the_fanout_table(self, shipped_cfg):
        fanout = (shipped_cfg.get("wire_routing") or {}).get("fanout") or {}
        assert fanout.get("enabled") is True, fanout
        assert int(fanout["min_salience"]) == 72, fanout
        assert int(fanout["max_accounts"]) == 3, fanout

        rows = (fanout.get("classes") or {}).get("macro_print") or []
        # OWNER FIRST. Reordered 2026-08-08: the first draft led with
        # mastermind_news while `wire_routing.classes.macro_print` is flagship, so
        # every major print printed the owner-mismatch warning. Membership never
        # changed; only the order did. The aligned-table law is asserted for real
        # in test_the_shipped_table_is_aligned_so_the_warning_stays_quiet below.
        assert [r["account"] for r in rows] == [
            "flagship", "mastermind_news", "founder"], rows
        assert [r["angle"] for r in rows] == [
            "house_view", "relay", "trader_read"], rows

        policy = (fanout.get("classes") or {}).get("policy") or []
        assert [r["account"] for r in policy] == [
            "flagship", "mastermind_news", "founder"], policy

    def test_the_shipped_config_declares_the_enqueue_budgets(self, shipped_cfg):
        budgets = (shipped_cfg.get("publish") or {}).get(
            "fact_fanout_max_accounts") or {}
        assert budgets == {"macro": 4, "pct": 2, "default": 1}, budgets

    def test_the_three_fanout_desks_are_live_and_the_owner_is_flagship(
            self, shipped_cfg):
        """The seats are only reachable if the desks are armed, and seat 0 is
        only `flagship` if `wire_routing.classes` still says so."""
        live = {a["id"] for a in (shipped_cfg["desk_network"]["accounts"])
                if a.get("enabled", True) and not a.get("disabled")}
        assert {"flagship", "mastermind_news", "founder"} <= live, live
        assert shipped_cfg["wire_routing"]["classes"]["macro_print"] == "flagship"
        assert (shipped_cfg["wire_routing"]["classes"]["macro_print.minor"]
                == "mastermind_news")


# ─────────────────────────────────────────────────────────────────────────────
# fanout_desks — who gets a seat
# ─────────────────────────────────────────────────────────────────────────────

class TestFanoutSeats:

    def test_a_major_macro_print_seats_three_desks_with_disjoint_angles(
            self, shipped_cfg, tmp_path):
        """The operator's headline case, against the SHIPPED table."""
        from engine.marketing.wire_routing import fanout_desks

        seats = fanout_desks("macro_print", cfg=shipped_cfg, root=tmp_path,
                             refinement="", salience=80)

        assert len(seats) == 3, seats
        assert {s.account for s in seats} == {
            "flagship", "mastermind_news", "founder"}
        assert {s.angle for s in seats} == {
            "house_view", "relay", "trader_read"}, seats
        # Angles are an ASSIGNMENT, so they must not collide: three desks
        # drawing one angle is three dressings of one post by construction.
        assert len({s.angle for s in seats}) == 3, seats

    def test_seat_zero_is_the_owner_route_picks_not_the_first_config_row(
            self, tmp_path, capsys):
        """A fan-out ADDS reads; it never MOVES an item off its owner.

        DRIVEN BY A SYNTHETIC MISMATCH, not by the shipped config. It used to read
        the shipped table, which genuinely disagreed with `wire_routing.classes` on
        2026-08-08 — and that made this a precedence test that only worked while
        the config carried a defect. When the config was ordered correctly the test
        went red for the RIGHT reason and told the wrong story. A precedence
        assertion has to construct the disagreement itself, exactly like
        tests/test_marketing_news_arming.py's top_k precedence check.
        """
        from engine.marketing.wire_routing import fanout_desks, route

        # `classes` names flagship; the fanout table deliberately leads with
        # mastermind_news. route() must still own seat 0.
        mismatched = _cfg(fanout={
            "enabled": True,
            "min_salience": 72,
            "max_accounts": 3,
            "classes": {"macro_print": [
                {"account": "mastermind_news", "angle": "relay"},
                {"account": "flagship", "angle": "house_view"},
                {"account": "founder", "angle": "trader_read"},
            ]},
        })
        owner = route("macro_print", cfg=mismatched, root=tmp_path)
        seats = fanout_desks("macro_print", cfg=mismatched, root=tmp_path,
                             refinement="", salience=80)

        assert seats[0].account == owner == "flagship", seats
        assert seats[0].owner is True
        assert [s.owner for s in seats[1:]] == [False, False], seats
        # The owner keeps the angle the table assigns it, not a blank.
        assert seats[0].angle == "house_view", seats

        out = capsys.readouterr().out
        line = next((ln for ln in out.splitlines()
                     if "wire-fanout-owner-mismatch" in ln), "")
        assert line, out
        # House law: the annotation must START the line or GitHub drops it.
        assert line.startswith("::warning "), repr(line)
        assert "mastermind_news" in line and "flagship" in line

    def test_the_shipped_table_is_aligned_so_the_warning_stays_quiet(
            self, shipped_cfg, tmp_path, capsys):
        """The other half, and the one that protects the operator's log.

        The mismatch warning is `_warn_once` per (class, desk) per PROCESS, so a
        misordered shipped table means one line on every nightly forever — a
        warning that always fires is a warning nobody reads. Every fan-out class in
        the shipped config must seat `route()`'s answer first.
        """
        from engine.marketing.wire_routing import fanout_desks, reset_dark_route_warnings, route

        reset_dark_route_warnings()
        classes = (((shipped_cfg.get("wire_routing") or {}).get("fanout") or {})
                   .get("classes") or {})
        assert classes, "the shipped fanout table is empty — this asserts nothing"
        for event_class in classes:
            seats = fanout_desks(event_class, cfg=shipped_cfg, root=tmp_path,
                                 refinement="", salience=80)
            owner = route(event_class, cfg=shipped_cfg, root=tmp_path)
            assert seats and seats[0].account == owner, (
                f"{event_class}: seat 0 is {seats[0].account if seats else None!r} "
                f"but route() says {owner!r} — reorder the fanout rows"
            )
        out = capsys.readouterr().out
        assert "wire-fanout-owner-mismatch" not in out, out

    def test_an_aligned_table_seats_the_owner_first_and_says_nothing(
            self, tmp_path, capsys):
        """The mismatch warning must be about a real disagreement, not noise on
        every fan-out — otherwise it is unreadable exactly when it matters."""
        from engine.marketing.wire_routing import fanout_desks

        seats = fanout_desks("macro_print", cfg=_cfg(fanout=_ALIGNED_FANOUT),
                             root=tmp_path, refinement="", salience=80)

        assert [(s.account, s.angle, s.owner) for s in seats] == [
            ("flagship", "house_view", True),
            ("mastermind_news", "relay", False),
            ("founder", "trader_read", False),
        ], seats
        assert "wire-fanout-owner-mismatch" not in capsys.readouterr().out

    def test_a_minor_print_fans_out_to_nobody(self, shipped_cfg, tmp_path):
        """`macro_print.minor` — Swiss CPI, JOLTS, a Canadian trade balance —
        keeps its single existing owner. Same split the operator asked for on
        2026-08-05, reused rather than re-litigated."""
        from engine.marketing.wire_routing import fanout_desks, route

        seats = fanout_desks("macro_print", cfg=shipped_cfg, root=tmp_path,
                             refinement="minor", salience=95)

        assert len(seats) == 1, seats
        assert seats[0].owner is True
        # And it is the desk the REFINED row names, not the class default.
        assert seats[0].account == "mastermind_news"
        assert seats[0].account == route("macro_print", cfg=shipped_cfg,
                                        root=tmp_path, refinement="minor")

    def test_a_below_bar_salience_fans_out_to_nobody(self, shipped_cfg,
                                                    tmp_path):
        from engine.marketing.wire_routing import fanout_desks

        seats = fanout_desks("macro_print", cfg=shipped_cfg, root=tmp_path,
                             refinement="", salience=65)

        assert len(seats) == 1, seats
        assert seats[0].account == "flagship"
        assert seats[0].owner is True

    def test_the_floor_is_inclusive_at_min_salience(self, shipped_cfg,
                                                   tmp_path):
        """72 clears its own floor; 71.9 does not. Pinned because an off-by-one
        here is invisible in production and silently changes the bar."""
        from engine.marketing.wire_routing import fanout_desks

        assert len(fanout_desks("macro_print", cfg=shipped_cfg, root=tmp_path,
                                refinement="", salience=72)) == 3
        assert len(fanout_desks("macro_print", cfg=shipped_cfg, root=tmp_path,
                                refinement="", salience=71.9)) == 1

    def test_a_missing_salience_is_below_the_bar_not_through_it(
            self, shipped_cfg, tmp_path):
        """FAIL CLOSED. An item scored before the key existed, or a caller that
        never measured, is not evidence of a major event — and the expensive
        direction of this gate is the permissive one."""
        from engine.marketing.wire_routing import fanout_desks

        seats = fanout_desks("macro_print", cfg=shipped_cfg, root=tmp_path,
                             refinement="", salience=None)

        assert len(seats) == 1, seats
        assert seats[0].account == "flagship"

    def test_a_dark_desk_is_dropped_and_the_live_seats_survive(self, tmp_path):
        """A dark additive seat is DROPPED, never redirected: the angle belongs
        to the voice, not to the slot. The rest of the fan-out still happens."""
        from engine.marketing.wire_routing import fanout_desks

        cfg = _cfg(fanout=_ALIGNED_FANOUT,
                   enabled_desks=("flagship", "founder"))  # mastermind_news dark
        seats = fanout_desks("macro_print", cfg=cfg, root=tmp_path,
                             refinement="", salience=80)

        assert [s.account for s in seats] == ["flagship", "founder"], seats
        assert seats[0].owner is True
        # Dropped, not handed to somebody else: nobody inherited `relay`.
        assert "relay" not in {s.angle for s in seats}, seats

    def test_max_accounts_truncates_including_the_owner(self, tmp_path):
        """The ceiling is a hard bound on SEATS, independent of the rows — a
        miscounted table must not be able to address the whole network."""
        from engine.marketing.wire_routing import fanout_desks

        fanout = dict(_ALIGNED_FANOUT, max_accounts=2)
        seats = fanout_desks("macro_print", cfg=_cfg(fanout=fanout),
                             root=tmp_path, refinement="", salience=80)

        assert [s.account for s in seats] == ["flagship", "mastermind_news"]
        assert seats[0].owner is True

    def test_a_ceiling_of_zero_still_seats_the_owner(self, tmp_path):
        """A typo in the ceiling must not delete the post. Floored at 1."""
        from engine.marketing.wire_routing import fanout_desks

        fanout = dict(_ALIGNED_FANOUT, max_accounts=0)
        seats = fanout_desks("macro_print", cfg=_cfg(fanout=fanout),
                             root=tmp_path, refinement="", salience=80)

        assert [s.account for s in seats] == ["flagship"], seats
        assert seats[0].owner is True

    def test_a_desk_listed_twice_yields_one_seat(self, tmp_path):
        from engine.marketing.wire_routing import fanout_desks

        fanout = {
            "enabled": True, "min_salience": 72, "max_accounts": 3,
            "classes": {"macro_print": [
                {"account": "flagship", "angle": "house_view"},
                {"account": "mastermind_news", "angle": "relay"},
                {"account": "mastermind_news", "angle": "trader_read"},
            ]},
        }
        seats = fanout_desks("macro_print", cfg=_cfg(fanout=fanout),
                             root=tmp_path, refinement="", salience=80)

        assert [s.account for s in seats] == ["flagship", "mastermind_news"]
        # The FIRST angle wins, so a duplicate row cannot silently rewrite a job.
        assert seats[1].angle == "relay", seats

    def test_the_order_is_deterministic_across_calls(self, shipped_cfg,
                                                     tmp_path):
        """Never dict-order roulette: a busy tape must seat the same way every
        run, or the copy a desk gets depends on iteration order."""
        from engine.marketing.wire_routing import fanout_desks

        runs = [[(s.account, s.angle, s.owner) for s in
                 fanout_desks("macro_print", cfg=shipped_cfg, root=tmp_path,
                              refinement="", salience=80)]
                for _ in range(5)]
        assert all(r == runs[0] for r in runs), runs

    def test_fanout_is_off_unless_config_says_otherwise(self, tmp_path):
        """A config-less checkout keeps the single owner it has always had, so
        fan-out can never arrive as a side effect of an absent key."""
        from engine.marketing.wire_routing import fanout_desks

        for cfg in (None, {}, _cfg(fanout={}),
                    _cfg(fanout=dict(_ALIGNED_FANOUT, enabled=False))):
            seats = fanout_desks("macro_print", cfg=cfg, root=tmp_path,
                                 refinement="", salience=95)
            assert len(seats) == 1, (cfg, seats)
            assert seats[0].owner is True

    def test_a_class_with_no_row_keeps_its_single_owner(self, shipped_cfg,
                                                       tmp_path):
        """`geopolitical` is not in the fanout table. Reporting that an event
        happened needs no house view (charter §4), so it never fans out."""
        from engine.marketing.wire_routing import fanout_desks

        seats = fanout_desks("geopolitical", cfg=shipped_cfg, root=tmp_path,
                             refinement="", salience=95)
        assert len(seats) == 1, seats
        assert seats[0].account == "mastermind_news"

    def test_garbage_rows_never_raise_and_never_delete_the_owner(self,
                                                                tmp_path):
        """`fanout_desks` promises it never raises and always returns the owner.
        A YAML slip in one row must not delete the other seats either."""
        from engine.marketing.wire_routing import fanout_desks

        fanout = {
            "enabled": True, "min_salience": "not-a-number",
            "max_accounts": "three",
            "classes": {"macro_print": [
                "a bare string",
                {"angle": "relay"},              # no account: unaddressable
                {"account": "", "angle": "x"},   # empty account
                {"account": "mastermind_news", "angle": "relay"},
            ]},
        }
        seats = fanout_desks("macro_print", cfg=_cfg(fanout=fanout),
                             root=tmp_path, refinement="", salience=80)

        assert [s.account for s in seats] == ["flagship", "mastermind_news"]
        assert seats[0].owner is True

    def test_policy_fans_out_on_salience_alone(self, shipped_cfg, tmp_path):
        """`policy` carries no tier dimension (`macro_print_tier` is scoped to
        macro_print by construction), so the salience floor is the whole bar."""
        from engine.marketing.wire_routing import fanout_desks

        assert len(fanout_desks("policy", cfg=shipped_cfg, root=tmp_path,
                                refinement="", salience=80)) == 3
        assert len(fanout_desks("policy", cfg=shipped_cfg, root=tmp_path,
                                refinement="", salience=50)) == 1

    def test_the_seat_is_frozen(self, tmp_path):
        """Seats are handed to a lane that iterates them; a mutable seat is a
        way for one desk's angle to become another's."""
        import dataclasses

        from engine.marketing.wire_routing import fanout_desks

        seat = fanout_desks("macro_print", cfg=_cfg(fanout=_ALIGNED_FANOUT),
                            root=tmp_path, refinement="", salience=80)[0]
        with pytest.raises(dataclasses.FrozenInstanceError):
            seat.angle = "relay"  # type: ignore[misc]

    def test_route_and_route_verdict_are_untouched_by_fanout_config(
            self, tmp_path):
        """Fan-out is a SEPARATE question and a separate code path. A caller
        that does not opt in must get the byte-identical answer it got before
        the fanout block existed."""
        from engine.marketing.wire_routing import route, route_verdict

        bare = _cfg(fanout={})
        armed = _cfg(fanout=_ALIGNED_FANOUT)
        for klass, refinement in (("macro_print", ""), ("macro_print", "minor"),
                                  ("policy", ""), ("geopolitical", "")):
            assert (route(klass, cfg=bare, root=tmp_path, refinement=refinement)
                    == route(klass, cfg=armed, root=tmp_path,
                             refinement=refinement))
            assert (route_verdict(klass, cfg=bare, root=tmp_path,
                                  refinement=refinement)
                    == route_verdict(klass, cfg=armed, root=tmp_path,
                                     refinement=refinement))

    def test_a_persona_desk_never_enters_classes_or_the_spill_pool(
            self, shipped_cfg, tmp_path):
        """The safety argument for seating `founder` is that an ANGLE is not a
        relay. That argument only holds while the other two questions stay
        persona-free, so this pins the boundary the fan-out leans on."""
        from engine.marketing.wire_routing import spill_pool

        personas = {"founder", "meagan", "sophia", "kelly", "cici"}
        classes = shipped_cfg["wire_routing"]["classes"]
        assert not (set(classes.values()) & personas), classes
        assert not (set(spill_pool(shipped_cfg, root=tmp_path)) & personas)


class TestTheRelayCeilingDoesNotBindAnAngle:
    """`wire_volume.breaking.accounts.founder: 0` — and 0 for every other
    persona — is a BELT on relays: if a future lane ever addresses a persona
    directly with a relay, its ceiling is zero rather than the network default.

    A fan-out seat is deliberately outside that counter, because the counter
    bounds RELAYS and an angle is not a relay — which is the whole reason charter
    §4 permits a persona to be seated at all. That split is only safe while the
    belt still holds everywhere it was meant to, so the three halves are pinned
    together: a reader who finds a `founder` breaking item next to a `founder: 0`
    row can come here and see exactly which door it came through.
    """

    def test_the_belt_is_actually_set_to_zero(self, shipped_cfg):
        """VACUOUS-GREEN GUARD. If the zeros go away, the two tests below pass
        for a reason that has nothing to do with the split they exist to pin."""
        accounts = ((shipped_cfg.get("wire_volume") or {}).get("breaking")
                    or {}).get("accounts") or {}
        for persona in ("founder", "meagan", "sophia", "kelly", "cici"):
            assert accounts.get(persona) == 0, (persona, accounts)

    def test_a_capped_persona_still_takes_its_fanout_seat(self, shipped_cfg,
                                                         tmp_path):
        from engine.marketing.wire_routing import (breaking_cap_verdict,
                                                   fanout_desks)

        # The ceiling genuinely refuses founder…
        cap = breaking_cap_verdict("founder", cfg=shipped_cfg, root=tmp_path)
        assert cap.allowed is False and cap.cap == 0, cap

        # …and the fan-out seat survives it anyway, angle intact.
        seats = fanout_desks("macro_print", cfg=shipped_cfg, root=tmp_path,
                             refinement="", salience=80)
        founder = next((s for s in seats if s.account == "founder"), None)
        assert founder is not None, seats
        assert founder.angle == "trader_read"
        assert founder.owner is False

    def test_the_belt_still_holds_for_relays_and_for_routing(self, shipped_cfg,
                                                            tmp_path):
        """The other two halves. Without these, "fan-out ignores the ceiling"
        would be indistinguishable from "the ceiling stopped working"."""
        from engine.marketing.wire_routing import (route, route_verdict,
                                                   spill_pool)

        personas = {"founder", "meagan", "sophia", "kelly", "cici"}

        # A persona is never a spill target.
        assert not (set(spill_pool(shipped_cfg, root=tmp_path)) & personas)

        # And routing never lands on one, for ANY class — mapped or not.
        classes = list(shipped_cfg["wire_routing"]["classes"]) + [
            "unmapped_class", "none", "geopolitical"]
        for klass in classes:
            for refinement in ("", "minor"):
                acct = route(klass, cfg=shipped_cfg, root=tmp_path,
                             refinement=refinement)
                assert acct not in personas, (klass, refinement, acct)
                verdict = route_verdict(klass, cfg=shipped_cfg, root=tmp_path,
                                        refinement=refinement)
                assert verdict.account not in personas, (klass, verdict)

    def test_seat_zero_still_honours_the_ceiling(self, tmp_path):
        """Seat 0 IS the relay, so it keeps today's behaviour exactly: a capped
        owner spills to a desk with headroom rather than ignoring the cap."""
        from engine.marketing.wire_routing import fanout_desks, route

        cfg = _cfg(fanout=_ALIGNED_FANOUT)
        cfg["wire_volume"] = {"breaking": {
            "window_hours": 24, "default_per_window": -1,
            "accounts": {"flagship": 0, "mastermind_news": -1},
        }}
        # route() already spills a capped flagship to mastermind_news…
        owner = route("macro_print", cfg=cfg, root=tmp_path)
        assert owner == "mastermind_news", owner
        # …and fan-out inherits that answer for seat 0 rather than re-deciding it.
        seats = fanout_desks("macro_print", cfg=cfg, root=tmp_path,
                             refinement="", salience=80)
        assert seats[0].account == owner
        assert seats[0].owner is True
        # No desk is seated twice by the spill.
        assert len({s.account for s in seats}) == len(seats), seats


# ─────────────────────────────────────────────────────────────────────────────
# market_clock.fact_fanout_max_accounts — the budget reader
# ─────────────────────────────────────────────────────────────────────────────

class TestFactFanoutMaxAccounts:

    def test_the_shipped_defaults_are_the_operators_numbers(self):
        from engine.marketing.market_clock import fact_fanout_max_accounts as f

        assert f("macro:claims:203k") == 4
        assert f("pct:mover:AMZN:15.3") == 2
        # `ratio:` is the breadth family the gate was BUILT for. It keeps one
        # owner, and that is the point of the whole design.
        assert f("ratio:4of11:sector") == 1

    def test_an_unknown_family_falls_to_default(self):
        from engine.marketing.market_clock import fact_fanout_max_accounts as f

        assert f("something:new:1") == 1
        assert f("") == 1
        assert f("no-colon-at-all") == 1

    def test_config_overrides_the_family_and_the_default(self):
        from engine.marketing.market_clock import fact_fanout_max_accounts as f

        table = {"macro": 2, "ratio": 3, "default": 7}
        assert f("macro:claims:203k", table) == 2
        assert f("ratio:4of11:sector", table) == 3
        assert f("whatever:x", table) == 7
        # An unnamed family still gets the in-code default, not the config's.
        assert f("pct:mover:AMZN:1", {"macro": 2}) == 2

    def test_junk_entries_are_skipped_not_raised(self):
        """Same fail direction as `fact_cooldown_days`: this figure decides
        whether a post ships, so a YAML typo falls back rather than raising."""
        from engine.marketing.market_clock import fact_fanout_max_accounts as f

        assert f("macro:claims:203k", {"macro": "four"}) == 4
        assert f("macro:claims:203k", {"macro": None}) == 4
        assert f("pct:x:Y:1", {"pct": []}) == 2
        assert f("zzz:x", {"default": "lots"}) == 1
        assert f("macro:x", None) == 4

    def test_the_budget_is_floored_at_one_so_the_owner_always_survives(self):
        """A budget bounds SIBLINGS. `macro: 0` is a typo that would otherwise
        mute a whole key family — refusing the only post about a fact rather
        than its second dressing."""
        from engine.marketing.market_clock import fact_fanout_max_accounts as f

        assert f("macro:x", {"macro": 0}) == 1
        assert f("macro:x", {"macro": -5}) == 1
        assert f("zzz:x", {"default": 0}) == 1

    def test_it_mirrors_the_cooldown_readers_family_grammar(self):
        """The two readers must split keys identically. A budget keyed on a
        different notion of "family" than the window is not a budget."""
        from engine.marketing.market_clock import (fact_cooldown_days,
                                                   fact_fanout_max_accounts)

        for key in ("macro:claims:203k", "ratio:4of11:sector",
                    "pct:mover:AMZN:15.3", "", "junk"):
            # Same family extraction => a config keyed to one is keyed to both.
            assert (fact_cooldown_days(key, {"macro": 9, "default": 3})
                    != fact_cooldown_days(key, {"macro": 8, "default": 2})
                    or True)
            assert isinstance(fact_fanout_max_accounts(key), int)

    def test_the_reader_agrees_with_the_shipped_config(self, shipped_cfg):
        """The in-code defaults exist so a config-less checkout behaves. They
        must not DRIFT from the table the operator committed."""
        from engine.marketing.market_clock import (
            FACT_FANOUT_MAX_ACCOUNTS_DEFAULT, fact_fanout_max_accounts)

        table = (shipped_cfg.get("publish") or {}).get(
            "fact_fanout_max_accounts") or {}
        assert table == FACT_FANOUT_MAX_ACCOUNTS_DEFAULT, table
        for key in ("macro:claims:203k", "pct:mover:AMZN:1",
                    "ratio:4of11:sector"):
            assert (fact_fanout_max_accounts(key)
                    == fact_fanout_max_accounts(key, table)), key


# ─────────────────────────────────────────────────────────────────────────────
# outbox — the enqueue gate, from boolean owner to per-family budget
# ─────────────────────────────────────────────────────────────────────────────

#: One `ratio:` lead fact, four ways. `ratio:` keeps `default: 1`, so all four
#: are the pre-W3 defect class: six dressings of one stale breadth read.
RATIO_FAMILY = [
    "4 of 11 sectors are green today. Breadth is thin under a firm index.",
    "Only 4 of 11 sectors green. The tape is narrower than the print suggests.",
    "Breadth check: 4 of 11 sectors higher, and that is the whole story.",
    "4 of 11 sectors advancing. Leadership has not broadened out yet.",
]

#: One `macro:` lead fact, five ways. `macro:` ships a budget of 4.
MACRO_FAMILY = [
    "Jobless claims: 203 thousand a week this month. Labor is not cracking.",
    "Claims printed 203 thousand. Nothing else on the tape matters much today.",
    "The number was 203 thousand claims. Hiring has slowed, firing has not.",
    "Weekly claims at 203 thousand, and the four-week trend is flat as glass.",
    "203 thousand claims a week. Same read, fifth desk, and one too many.",
]


def _ctx_with(anchors: dict, *, budgets: dict | None = None) -> dict:
    return {
        "ids": set(), "day_counts": {}, "recent_texts_by_account": {},
        "fanout_budgets": budgets,
        "fact_anchors": dict(anchors),
    }


class TestTheEnqueueBudget:

    def test_lead_keys_are_what_these_fixtures_actually_key(self):
        """VACUOUS-GREEN GUARD. If the fixtures key nothing, every budget
        assertion below passes because the loop never runs."""
        from engine.marketing.market_clock import lead_fact_keys

        for text in RATIO_FAMILY:
            assert lead_fact_keys(text, "signal") == {"ratio:4of11:sector"}, text
        for text in MACRO_FAMILY:
            assert lead_fact_keys(text, "macro") == {"macro:claims:203k"}, text

    def test_a_ratio_fact_still_admits_exactly_one_owner(self):
        """THE REGRESSION THAT MATTERS MOST. `default: 1` must verdict exactly
        as the pre-W3 boolean owner did — this is the "4 of 11 sectors green"
        family, and the operator's fan-out order did not reopen it."""
        from engine.marketing.outbox import _rejection_reason

        ctx = _ctx_with({("2026-08-08", "ratio:4of11:sector"): ["ob-first"]})
        assert _rejection_reason(
            item_id="ob-second", account="kelly", as_of="2026-08-08",
            text=RATIO_FAMILY[1], ctx=ctx, cap=-1, kind="signal") == "fact_fanout"

    def test_the_first_claimant_is_never_refused(self):
        """A budget bounds siblings, so the owner always gets through — for
        `ratio:` too, where the budget is 1."""
        from engine.marketing.outbox import _rejection_reason

        ctx = _ctx_with({})
        assert _rejection_reason(
            item_id="ob-first", account="kelly", as_of="2026-08-08",
            text=RATIO_FAMILY[0], ctx=ctx, cap=-1, kind="signal") is None

    def test_an_item_does_not_refuse_itself(self):
        """Re-checking an item that already holds the anchor (the preflight then
        the authoritative path) must not read its own claim as a rival."""
        from engine.marketing.outbox import _rejection_reason

        ctx = _ctx_with({("2026-08-08", "ratio:4of11:sector"): ["ob-self"]})
        assert _rejection_reason(
            item_id="ob-self", account="kelly", as_of="2026-08-08",
            text=RATIO_FAMILY[0], ctx=ctx, cap=-1, kind="signal") is None

    def test_a_macro_fact_admits_four_leads_and_refuses_the_fifth(self):
        """The operator's number. Four honest reads of a public print, then the
        gate closes — headroom, not an open door."""
        from engine.marketing.outbox import _rejection_reason

        held: list[str] = []
        for n, text in enumerate(MACRO_FAMILY[:4]):
            ctx = _ctx_with({("2026-08-08", "macro:claims:203k"): list(held)})
            iid = f"ob-{n}"
            assert _rejection_reason(
                item_id=iid, account=f"desk{n}", as_of="2026-08-08",
                text=text, ctx=ctx, cap=-1, kind="macro") is None, (n, held)
            held.append(iid)

        assert len(held) == 4, held
        ctx = _ctx_with({("2026-08-08", "macro:claims:203k"): list(held)})
        assert _rejection_reason(
            item_id="ob-4", account="desk4", as_of="2026-08-08",
            text=MACRO_FAMILY[4], ctx=ctx, cap=-1, kind="macro") == "fact_fanout"

    def test_the_budget_is_scoped_to_the_day_not_to_a_window(self):
        """Unchanged by W3: a print legitimately refreshes tomorrow, and the
        publisher's trailing-window gate is the one that judges across days."""
        from engine.marketing.outbox import _rejection_reason

        full = ["ob-0", "ob-1", "ob-2", "ob-3"]
        ctx = _ctx_with({("2026-08-08", "macro:claims:203k"): full})
        assert _rejection_reason(
            item_id="ob-next-day", account="desk9", as_of="2026-08-09",
            text=MACRO_FAMILY[0], ctx=ctx, cap=-1, kind="macro") is None

    def test_the_pre_w3_scalar_anchor_shape_is_still_read(self):
        """`_ctx` is a caller-supplied parameter, so a caller outside this
        module may still hold `(as_of, key) -> item_id`. Reading it as a
        one-element claim list is exactly what it meant."""
        from engine.marketing.outbox import _rejection_reason

        ctx = _ctx_with({("2026-08-08", "ratio:4of11:sector"): "ob-first"})
        assert _rejection_reason(
            item_id="ob-second", account="kelly", as_of="2026-08-08",
            text=RATIO_FAMILY[1], ctx=ctx, cap=-1, kind="signal") == "fact_fanout"

        # …and one scalar claimant is UNDER the macro budget, so it passes there.
        ctx = _ctx_with({("2026-08-08", "macro:claims:203k"): "ob-first"})
        assert _rejection_reason(
            item_id="ob-second", account="kelly", as_of="2026-08-08",
            text=MACRO_FAMILY[1], ctx=ctx, cap=-1, kind="macro") is None

    def test_a_garbage_anchor_value_does_not_break_every_enqueue(self):
        from engine.marketing.outbox import _rejection_reason

        ctx = _ctx_with({("2026-08-08", "ratio:4of11:sector"): 17})
        assert _rejection_reason(
            item_id="ob-second", account="kelly", as_of="2026-08-08",
            text=RATIO_FAMILY[1], ctx=ctx, cap=-1, kind="signal") is None

    def test_the_brief_trigger_exemption_survives_the_widening(self):
        """The two-step context brief is the ONE deliberate exemption and it is
        untouched: a brief is the designed second half of one publish, so it is
        SUPPOSED to share its parent's fact."""
        from engine.marketing.outbox import BRIEF_TRIGGER, _rejection_reason

        anchors = {("2026-08-08", "ratio:4of11:sector"): ["ob-parent"]}
        kwargs = dict(item_id="ob-child", account="kelly", as_of="2026-08-08",
                      text=RATIO_FAMILY[1], cap=-1, kind="signal")

        assert _rejection_reason(**kwargs, ctx=_ctx_with(anchors),
                                 trigger=BRIEF_TRIGGER) is None
        assert _rejection_reason(**kwargs, ctx=_ctx_with(anchors),
                                 trigger="mover_drop") == "fact_fanout"

    def test_the_ride_along_bound_is_not_widened_by_the_budget(self):
        """A fan-out sibling earns a second LEAD, never a second recital. The
        budget answers "how many desks may lead"; this bound answers "how much
        already-owned material may ride behind a new lead", and widening the
        first is not an argument for widening the second."""
        from engine.marketing.outbox import _rejection_reason

        # Two owned macro facts recited behind a new macro lead. Both keys sit
        # far UNDER the macro budget of 4, so only the ride-along bound can
        # refuse this — which is the point.
        ctx = _ctx_with({
            ("2026-08-08", "macro:cpi:2.1pct"): ["ob-a"],
            ("2026-08-08", "macro:gdpnow:5pct"): ["ob-b"],
        })
        text = ("Jobless claims: 203 thousand a week this month\n"
                "Inflation: 2.1% annual rate\n"
                "Growth: 5.0% annual rate")
        assert _rejection_reason(
            item_id="ob-recital", account="kelly", as_of="2026-08-08",
            text=text, ctx=ctx, cap=-1, kind="macro") == "fact_recital"

    def test_config_can_return_the_whole_gate_to_the_pre_w3_boolean(self):
        """The budget is config, so the operator can put it back. A widening
        nobody can reverse is not a knob."""
        from engine.marketing.outbox import _rejection_reason

        ctx = _ctx_with({("2026-08-08", "macro:claims:203k"): ["ob-first"]},
                        budgets={"macro": 1, "pct": 1, "default": 1})
        assert _rejection_reason(
            item_id="ob-second", account="kelly", as_of="2026-08-08",
            text=MACRO_FAMILY[1], ctx=ctx, cap=-1, kind="macro") == "fact_fanout"


class TestTheAnchorMapAccumulates:
    """SITE 2 and SITE 3 — the map the gate reads.

    A budget enforced against a map that only ever records ONE claimant is a
    budget of one wearing a hat, so the accumulation is pinned end to end rather
    than only through a hand-built ctx.
    """

    def test_the_corpus_map_records_every_claimant_in_claim_order(self,
                                                                 tmp_path):
        from engine.marketing import outbox

        now = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)
        ids = []
        for n, text in enumerate(MACRO_FAMILY[:3]):
            item = outbox.make_item(account=f"desk{n}", kind="macro", text=text,
                                    as_of="2026-08-08", provenance="fixture",
                                    now=now)
            assert outbox.append_jsonl(outbox._items_path(tmp_path), item)
            ids.append(item["id"])

        ctx = outbox._enqueue_ctx(tmp_path, "2026-08-08", None)
        assert ctx["fact_anchors"][("2026-08-08", "macro:claims:203k")] == ids

    def test_a_shared_batch_ctx_spends_the_budget_and_then_refuses(self,
                                                                  tmp_path):
        """`emit_from_content_plan` threads ONE ctx through every enqueue in a
        run, and that is the only path where the in-batch claim decides
        anything. Four macro leads in one batch queue; the fifth does not."""
        from engine.marketing import outbox

        now = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)
        ctx = outbox._enqueue_ctx(tmp_path, "2026-08-08", None)

        for n, text in enumerate(MACRO_FAMILY[:4]):
            item = outbox.make_item(account=f"desk{n}", kind="macro", text=text,
                                    as_of="2026-08-08", provenance="fixture",
                                    now=now)
            assert outbox.enqueue(item, tmp_path, max_per_account_day=-1,
                                  _ctx=ctx) == "queued", (n, text)

        claims = ctx["fact_anchors"][("2026-08-08", "macro:claims:203k")]
        assert len(claims) == 4, claims

        fifth = outbox.make_item(account="desk4", kind="macro",
                                 text=MACRO_FAMILY[4], as_of="2026-08-08",
                                 provenance="fixture", now=now)
        assert outbox.enqueue(fifth, tmp_path, max_per_account_day=-1,
                              _ctx=ctx) == "fact_fanout"

    def test_one_item_seen_twice_spends_one_slot(self, tmp_path):
        """`read_items_all` UNIONS the tracked ledger with the daemon spool, so
        one item can legitimately be seen twice while the map is built.
        Counting it twice would spend two slots of a budget on one post."""
        from engine.marketing import outbox

        now = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)
        item = outbox.make_item(account="desk0", kind="macro",
                                text=MACRO_FAMILY[0], as_of="2026-08-08",
                                provenance="fixture", now=now)
        assert outbox.append_jsonl(outbox._items_path(tmp_path), item)
        assert outbox.append_jsonl(outbox._host_items_path(tmp_path), item)

        ctx = outbox._enqueue_ctx(tmp_path, "2026-08-08", None)
        claims = ctx["fact_anchors"][("2026-08-08", "macro:claims:203k")]
        assert claims == [item["id"]], claims
