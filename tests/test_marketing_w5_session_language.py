"""tests/test_marketing_w5_session_language.py — the day-word law (W5).

THE OPERATOR, 2026-08-08, A SATURDAY, verbatim on both counts:

  "36 posts in outbox ... i don't want to review so many posts per day ... need
   a system that doesn't require my manual review all the time."

  outbox items reading "Consumer Goods selling off, -2.4% avg on Thursday" and
  "Commodities Metals ripping, +7.2% avg today", visible on a Saturday —
  "if we post this on Saturday the comment section is gonna be like 'bro today
   is saturday wdym today'."

They had asked roughly ten times. This module is the answer as tests, so the
eleventh time cannot happen.

WHY NOTHING CAUGHT EITHER ONE. Both items are shapes every existing gate is
blind to, and each for its own reason:

  * "-2.4% avg on Thursday" was TRUE COPY. It was written Friday morning about
    Thursday's close and it said so. `temporal_violations` has no opinion about a
    weekday name at all. `stale_session_violations` leg 2 could not fire either:
    Friday is still `live_session` all weekend, and the copy is only one session
    behind it. Nothing in the estate said "a post whose whole job is TODAY'S tape
    may not name a day".
  * "+7.2% avg today" WAS covered by the clock — at DISPATCH, in
    `marketing_publisher._clock_violations`, which is the last gate before the
    network and therefore the one gate a disarmed publisher never runs. The
    verdict existed and was never written down.

The four things pinned here, one per failure class:

  1. `market_clock.session_language_violations` — the law itself, both rules.
  2. `approval_desk` — the desk now asks the clock, and its third verdict
     ("leave it for a human") is gone under the decisive posture.
  3. `outbox.expire_dead_session_items` — the retirement, idempotent.
  4. `marketing_press_wire` + its workflow — the retirement PERSISTS on a lane
     that runs and commits regardless of the publish kill switch.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# The calendar this whole module is read against. 2026-08-06 is a Thursday,
# 08-07 a Friday, 08-08 a Saturday, 08-10 a Monday. Every `now` below is stated
# in UTC and lands mid-afternoon ET, well clear of the 20:00 ET rollover that
# would move the ET calendar date.
_THU = datetime(2026, 8, 6, 17, 0, 0, tzinfo=timezone.utc)
_FRI = datetime(2026, 8, 7, 17, 0, 0, tzinfo=timezone.utc)
_SAT = datetime(2026, 8, 8, 17, 0, 0, tzinfo=timezone.utc)
_SUN = datetime(2026, 8, 9, 17, 0, 0, tzinfo=timezone.utc)
_MON = datetime(2026, 8, 10, 17, 0, 0, tzinfo=timezone.utc)

#: The operator's two items, verbatim leads.
_THURSDAY_TAPE = "Consumer Goods selling off, -2.4% avg on Thursday"
_TODAY_TAPE = "Commodities Metals ripping, +7.2% avg today"


def _violations(text, *, now, fact_asof, kind="", provenance=""):
    from engine.marketing.market_clock import session_language_violations

    return session_language_violations(text, now=now, fact_asof=fact_asof,
                                       kind=kind, provenance=provenance)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Rule A — a same-day tape kind may not name a weekday
# ─────────────────────────────────────────────────────────────────────────────

class TestWeekdayNamesInSameDayKinds:

    def test_the_operators_thursday_theme_list_is_refused_on_saturday(self):
        """THE COMPLAINT, VERBATIM. `ob-2026-08-07-3358756700`.

        Written Friday morning about Thursday's close, 29 hours old on Saturday
        — inside the 36h reaper's bar, on a real ladder slot, and still offering
        an Approve button.

        MUTATION CHECK: drop `_WEEKDAYS_EN` from `market_clock._DAY_NAME_RE`'s
        alternation (leave the abbreviations) and this test goes red while every
        other clock test stays green — which is the shape of the hole that let
        this ship.
        """
        bad = _violations(_THURSDAY_TAPE, now=_SAT, fact_asof="2026-08-07",
                          kind="theme_list")
        assert bad == ["day_name_in_same_day_kind:Thursday"], bad

    def test_it_is_refused_on_the_day_it_was_written_too(self):
        """NOT A STALENESS RULE — A VOCABULARY RULE, and the difference matters.

        The same copy on FRIDAY, one hour after it was written, is still refused.
        A "what is moving" post that names a day is either already stale or is
        about to be: its honest vocabulary is "today", and its perishability is
        owned by the 3h wire TTL, not by the reader's ability to date the claim.

        If this rule were staleness-scoped it would have to resolve the weekday
        and compare sessions, which is exactly the guess `_claim_is_cited`
        cannot get right — and every wrong guess reships the complaint.
        """
        bad = _violations(_THURSDAY_TAPE, now=_FRI, fact_asof="2026-08-07",
                          kind="theme_list")
        assert bad == ["day_name_in_same_day_kind:Thursday"], bad

    @pytest.mark.parametrize("text,hit", [
        ("$TEAM +35.3% on Friday", "Friday"),
        ("Fri close was ugly for the group", "Fri"),
        ("Monday's gap never filled", "Monday"),
        ("Mondays keep doing this", "Mondays"),
        ("MOVERS: THU tape, +4% avg", "THU"),
        ("Big Wed reversal in the metals", "Wed"),
        ("Sunday futures already pointing lower", "Sunday"),
    ])
    def test_every_spelling_a_desk_uses_is_caught(self, text, hit):
        """Possessives, plurals, abbreviations and shouted headlines.

        "Monday's" is the one worth naming: it is a weekday reference wearing an
        apostrophe, and a rule that let it through would be a rule the copy
        banks route around by accident within a week.
        """
        bad = _violations(text, now=_SAT, fact_asof="2026-08-07", kind="mover")
        assert bad and bad[0] == f"day_name_in_same_day_kind:{hit}", bad

    @pytest.mark.parametrize("text", [
        "$MON ripping +12% on volume",              # Monday.com's cashtag
        "$SUN and $FRI both bid",                   # Sunoco, Friedman
        "Monday.com is up 9% after the print",      # the company, in prose
    ])
    def test_a_cashtag_or_a_company_named_after_a_day_is_not_a_day(self, text):
        """THE FALSE POSITIVE THAT WOULD COST A LANE FOREVER.

        A mover post is almost entirely cashtags, and the refusal here is a
        TERMINAL quarantine. `$MON` reading as Monday would kill every post about
        Monday.com, every time, with a receipt naming a defect the copy does not
        have. Pinned as three shapes because the guards are three different
        pieces of the regex (the `$` lookbehind and the `.[A-Za-z]` lookahead).
        """
        assert _violations(text, now=_SAT, fact_asof="2026-08-08",
                           kind="mover") == []

    def test_a_kind_that_is_not_a_tape_read_may_name_a_day(self):
        """SCOPE. An `event` post about a scheduled print, or an `education`
        post citing a precedent, legitimately names days. Rule A is about copy
        whose subject IS the current tape, and widening it to every kind would
        mute the lanes whose whole job is the calendar."""
        for kind in ("event", "education", "macro", "chart", "watchlist"):
            assert _violations("The jobs report lands Friday", now=_SAT,
                               fact_asof="2026-08-08", kind=kind) == [], kind

    def test_breaking_is_a_tape_read_only_on_the_live_lanes(self):
        """A press-wire flash ("Fed speaks Friday") is news carrying a date. A
        hot-tape or publish-time-mover breaking item is a price read, and the
        provenance is the only thing that tells them apart."""
        text = "Breaking: the group is ripping, best Friday in a year"
        assert _violations(text, now=_SAT, fact_asof="2026-08-08",
                           kind="breaking", provenance="press_lane") == []
        for prov in ("hot_tape", "publisher_live_movers"):
            bad = _violations(text, now=_SAT, fact_asof="2026-08-08",
                              kind="breaking", provenance=prov)
            assert bad == ["day_name_in_same_day_kind:Friday"], (prov, bad)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Rule B — a day word must match the posting calendar day
# ─────────────────────────────────────────────────────────────────────────────

class TestDayWordsAgainstThePostingDay:

    def test_the_operators_today_theme_list_is_refused_on_saturday(self):
        """THE SECOND COMPLAINT, VERBATIM. `ob-2026-08-08-ad8e39cb91`, written
        02:24Z Saturday about Friday's close, slotted for Saturday noon.

        "bro today is saturday wdym today". There is no session in progress on a
        Saturday, so `session_of` walks the item back to Friday and the posting
        day can never equal it.
        """
        bad = _violations(_TODAY_TAPE, now=_SAT, fact_asof="2026-08-08",
                          kind="theme_list")
        assert "today_word_off_session:today" in bad, bad

    def test_thursday_copy_saying_today_is_refused_on_saturday(self):
        """The brief's fixture: written Thursday, posted Saturday. Two days and
        a closed market between the claim and the reader."""
        bad = _violations("Commodities Metals ripping, +7.2% avg today",
                          now=_SAT, fact_asof="2026-08-06", kind="theme_list")
        assert "today_word_off_session:today" in bad, bad

    def test_today_passes_on_its_own_session_day(self):
        """THE OTHER DIRECTION, and it is the one that keeps the lane alive. A
        gate that refuses "today" on a Thursday about Thursday is not a fix, it
        is an outage."""
        assert _violations("Commodities Metals ripping, +7.2% avg today",
                           now=_THU, fact_asof="2026-08-06",
                           kind="theme_list") == []

    def test_the_slug_is_the_one_the_ledger_already_carries(self):
        """ONE LAW, ONE HOME. `temporal_violations` emits
        `today_word_off_session:<hit>` and so does rule B1, because they are the
        same law read off the vocab and off the calendar. A new slug here would
        split every existing grep, every admin chip and every ledger note in
        two."""
        from engine.marketing.market_clock import (
            clock_violations, temporal_violations)

        legacy = temporal_violations(_TODAY_TAPE, now=_SAT,
                                     fact_asof="2026-08-08")
        assert legacy == ["today_word_off_session:today"], legacy
        # And the composition does not say it twice.
        composed = clock_violations(_TODAY_TAPE, now=_SAT,
                                    fact_asof="2026-08-08", kind="theme_list")
        assert composed.count("today_word_off_session:today") == 1, composed

    def test_tonight_is_keyed_on_the_posting_day_not_on_a_session(self):
        """"tonight" is a claim about the EVENING OF THE POSTING DAY, which is a
        real thing on a Sunday even though no session is in progress. Keying it
        on a session would mute the futures and Asia frames the estate reserves
        it for; keying it on the calendar still kills a Thursday-written
        "tonight" read on a Saturday."""
        assert _violations("Futures reopen tonight", now=_SUN,
                           fact_asof="2026-08-09", kind="macro") == []
        bad = _violations("Futures reopen tonight", now=_SAT,
                          fact_asof="2026-08-06", kind="macro")
        assert bad == ["tonight_word_off_day:tonight"], bad

    def test_yesterday_is_exactly_one_calendar_day_back(self):
        """session+1 passes, session+3 does not.

        CALENDAR days, not sessions, and the weekend is why: Friday genuinely
        was yesterday when read on Saturday and stops being yesterday on Sunday.
        Session arithmetic would keep calling Friday "yesterday" until Monday's
        open, which is the exact class of lie this module exists to stop.
        """
        text = "$NVDA gapped yesterday and never filled it"
        assert _violations(text, now=_SAT, fact_asof="2026-08-07",
                           kind="chart") == []                      # Fri -> Sat
        bad = _violations(text, now=_MON, fact_asof="2026-08-07", kind="chart")
        assert bad == ["yesterday_word_off_session:yesterday"], bad  # Fri -> Mon

    def test_rule_b_binds_every_kind(self):
        """Rule A is scoped to the tape kinds; rule B is not. A false "today" is
        false in an `education` post exactly as it is in a `mover`."""
        for kind in ("education", "macro", "event", "insider", "signal"):
            bad = _violations("Nothing worked today", now=_SAT,
                              fact_asof="2026-08-07", kind=kind)
            assert bad == ["today_word_off_session:today"], (kind, bad)

    def test_an_unparseable_stamp_refuses_every_day_word(self):
        """FAIL DIRECTION. An item that cannot say which day it is about cannot
        prove any day word is honest, which is the same answer
        `temporal_vocab` gives (`allows_today=False`) on the same input."""
        bad = _violations("Up today, gone yesterday, back tonight", now=_SAT,
                          fact_asof="not-a-date", kind="chart")
        assert "today_word_off_session:today" in bad, bad
        assert "tonight_word_off_day:tonight" in bad, bad
        assert "yesterday_word_off_session:yesterday" in bad, bad


# ─────────────────────────────────────────────────────────────────────────────
# 3. The weekend lane must survive intact
# ─────────────────────────────────────────────────────────────────────────────

class TestTheWeekendLaneIsUntouched:

    @pytest.mark.parametrize("text", [
        "$NVDA into the week. 297 is the level that matters.",
        "$AAPL has gone quiet\n\nRecent trading centered on 297. That level "
        "needs to hold.",
        "$TSLA finally bounced\n\nUp +5.6% last week. I need the next pullback "
        "to hold before I call it a turn.",
        "$AVGO held 416\n\nMost shares traded there over four months. Lose it "
        "and the setup gets ugly.",
    ])
    def test_weekend_levels_copy_carries_no_day_words_and_must_pass(self, text):
        """THE LANE THIS GATE COULD HAVE KILLED.

        `weekend_levels` is the lane that exists to post over a weekend. Its
        copy is forward-framed and day-word-free by construction, and all four
        of these are live rows from the Saturday queue the operator was looking
        at. If any of them acquires a violation, the fix has eaten the thing it
        was protecting.
        """
        assert _violations(text, now=_SAT, fact_asof="2026-08-08",
                           kind="watchlist", provenance="weekend_levels") == []

    def test_the_whole_weekend_watchlist_lane_survives_the_reaper_too(self):
        """Same four items, asked the retirement question instead of the copy
        question. A `watchlist` is not a same-day tape kind, so a Saturday is a
        normal day for it."""
        from engine.marketing.market_clock import session_expired_reason

        assert session_expired_reason(now=_SAT, fact_asof="2026-08-08",
                                      kind="watchlist",
                                      provenance="weekend_levels") == ""


# ─────────────────────────────────────────────────────────────────────────────
# 4. Weekend / holiday retirement
# ─────────────────────────────────────────────────────────────────────────────

class TestWeekendRetirement:

    def test_a_friday_mover_is_retired_on_saturday(self):
        """A `mover` says "this name is moving RIGHT NOW". On a Saturday nothing
        is moving, its own session has passed, and no later hour makes it
        postable — so it is retired, not held. Before this it stayed queued and
        approvable all weekend."""
        from engine.marketing.market_clock import session_expired_reason

        why = session_expired_reason(now=_SAT, fact_asof="2026-08-07",
                                     kind="mover")
        assert why.startswith("Friday tape cannot post on Saturday"), why
        assert "not a trading day" in why

    def test_a_saturday_born_theme_list_is_retired_the_same_way(self):
        """`ob-2026-08-08-ad8e39cb91` was CREATED on the Saturday. Its facts are
        still Friday's — `session_of` says so — so it retires on the same
        grounds as one written the day before."""
        from engine.marketing.market_clock import session_expired_reason

        why = session_expired_reason(now=_SAT, fact_asof="2026-08-08",
                                     kind="theme_list")
        assert why.startswith("Friday tape cannot post on Saturday"), why

    def test_a_trading_day_retires_nothing(self):
        """The retirement is a CALENDAR verdict, not a freshness one. On a
        Thursday a mover is exactly what the lane is for; staleness there is the
        3h wire TTL's job and this must not double-judge it."""
        from engine.marketing.market_clock import session_expired_reason

        for kind in ("mover", "theme_list"):
            assert session_expired_reason(now=_THU, fact_asof="2026-08-06",
                                          kind=kind) == "", kind

    def test_a_market_holiday_counts_as_a_non_trading_day(self):
        """Weekends are not the only closed days, and nine sites in this estate
        once reimplemented `weekday() >= 5` without one of them being
        holiday-aware. 2026-01-01 is a Thursday and a full NYSE closure."""
        from engine.marketing.market_clock import (
            is_session_day, session_expired_reason)

        holiday = datetime(2026, 1, 1, 17, 0, 0, tzinfo=timezone.utc)
        assert is_session_day(holiday.date()) is False
        why = session_expired_reason(now=holiday, fact_asof="2026-01-01",
                                     kind="mover")
        assert "cannot post on Thursday" in why, why


# ─────────────────────────────────────────────────────────────────────────────
# 5. The desk: it asks the clock, and it no longer parks work on a human
# ─────────────────────────────────────────────────────────────────────────────

_SOURCE = {"ticker": "PLTR", "entry": 190.0, "invalidation": 178.5,
           "media_url": "https://r2.example/marketing/charts/pltr.png"}


def _item(**kw) -> dict:
    base = {
        "schema": "marketing.outbox/v1",
        "id": "ob-2026-08-08-w5test0001",
        "as_of": "2026-08-08",
        "account": "flagship",
        "kind": "signal",
        "text": "$PLTR reclaimed 190 and has held it for six sessions. "
                "Entry 190, out below 178.5.",
        "media": [],
        "scheduled_at": "immediate",
        "slot": None,
        "priority": 5,
        "provenance": "content_studio",
        "source": dict(_SOURCE),
        "status": "queued",
        "created_at": "2026-08-08T04:00:00Z",
    }
    base.update(kw)
    return base


class TestTheDeskAsksTheClock:

    def test_the_thursday_theme_list_quarantines_naming_the_day_word_check(self):
        """THE WHOLE POINT: this verdict now exists at APPROVAL time.

        It existed at dispatch already, in `_clock_violations`, and that is the
        one gate a disarmed publisher never reaches. The name recorded is
        `session_language`, because the operator reads these names and the
        defect is the day.
        """
        from engine.marketing.approval_desk import audit_item

        v = audit_item(_item(kind="theme_list", source={},
                             text=_THURSDAY_TAPE + "\n\n$TDUP -50.5% $CELH -18.5%"),
                       now=_SAT)
        assert v.action == "quarantine", v
        assert v.check in {"session_language", "expired_session"}, v
        assert "Thursday" in v.evidence, v.evidence

    def test_the_today_theme_list_quarantines_too(self):
        from engine.marketing.approval_desk import audit_item

        v = audit_item(_item(kind="theme_list", source={},
                             text=_TODAY_TAPE + "\n\n$WWR +87.8% $AREC +20.7%"),
                       now=_SAT)
        assert v.action == "quarantine", v
        assert v.check in {"session_language", "expired_session"}, v

    def test_a_clean_weekend_watchlist_still_approves(self):
        """The desk must still say YES. A gate battery that quarantines the
        whole weekend queue is the same outage as one that approves it."""
        from engine.marketing.approval_desk import audit_item

        v = audit_item(_item(kind="watchlist", provenance="weekend_levels",
                             text="$AAPL has gone quiet. Recent trading "
                                  "centered on 297. That level needs to hold. "
                                  "Entry 190, out below 178.5."),
                       now=_SAT)
        assert v.action == "approve", (v.check, v.evidence)
        assert "session_language" in v.passed and "expired_session" in v.passed

    def test_no_verdict_leaves_work_for_a_human_under_the_decisive_posture(self):
        """THE OPERATOR'S FIRST COMPLAINT, AS A SWEEP OF THE WHOLE BATTERY.

        "i don't want to review so many posts per day." Every item below is a
        different verdict class — clean, zero payload, no evidence, banned
        language, expired slot, stale day word, missing chart. Under
        `decisive: true` NONE of them may return a `hold` unless the hold is a
        named MACHINE deferral, because a hold that is not machine-owned is a
        human queue by another name.

        MUTATION CHECK: delete the decisive branch from `audit_item` and the
        no-evidence row below returns `hold` with check `number_sanity`, which
        is not in `MACHINE_DEFERRALS` — red.
        """
        from engine.marketing.approval_desk import (
            MACHINE_DEFERRALS, audit_item, desk_config)

        cfg = desk_config(None)
        assert cfg["decisive"] is True, "the shipped posture is decisive"

        battery = {
            "clean": _item(),
            "zero_payload": _item(kind="education", source={},
                                  text="The discipline a watch list enforces."),
            "no_evidence": _item(kind="macro", source={},
                                 text="Breadth is wide: 231 of 231 names above "
                                      "the 200 day line."),
            "banned_language": _item(text="$PLTR POC held 190 all week. "
                                          "Entry 190, out below 178.5."),
            "expired_slot": _item(scheduled_at="2026-08-01T12:00:00Z"),
            "stale_day_word": _item(kind="theme_list", source={},
                                    text=_THURSDAY_TAPE),
            "no_media": _item(kind="chart", source={"ticker": "PLTR",
                                                    "entry": 190.0},
                              text="$PLTR reclaimed 190. Entry 190."),
        }
        held: dict[str, str] = {}
        for label, item in battery.items():
            v = audit_item(item, now=_SAT, desk_cfg=cfg)
            assert v.action in {"approve", "quarantine", "hold"}, (label, v)
            if v.action == "hold":
                held[label] = v.check
        assert all(name in MACHINE_DEFERRALS for name in held.values()), held

    def test_decisive_false_hands_the_unverifiable_rows_back_to_the_operator(self):
        """THE ROLLBACK LEVER. `decisive: false` restores the original triage,
        so the operator can put the review back if the autonomy misbehaves."""
        from engine.marketing.approval_desk import audit_item, desk_config

        cfg = desk_config({"approval_desk": {"decisive": False}})
        v = audit_item(_item(kind="macro", source={},
                             text="Breadth is wide: 231 of 231 names above the "
                                  "200 day line."),
                       now=_SAT, desk_cfg=cfg)
        assert v.action == "hold" and v.check == "number_sanity", v

    def test_a_missing_config_block_still_ships_decisive(self):
        """Deleting the key must not silently restore the review bottleneck —
        the same posture `enabled` takes two lines above it."""
        from engine.marketing.approval_desk import desk_config

        assert desk_config({})["decisive"] is True
        assert desk_config(None)["decisive"] is True
        assert desk_config({"approval_desk": {}})["decisive"] is True

    def test_the_shipped_config_arms_it(self):
        """config/marketing.yml is the operator-facing surface; a default that
        is only true in Python is a default the operator cannot see."""
        import yaml

        cfg = yaml.safe_load((ROOT / "config" / "marketing.yml").read_text(
            encoding="utf-8"))
        assert cfg["approval_desk"]["decisive"] is True


# ─────────────────────────────────────────────────────────────────────────────
# 6. The reaper, and the lane that commits it
# ─────────────────────────────────────────────────────────────────────────────

#: Deeply distinct copy per row: the enqueue-time near-dup guard compares
#: same-account texts inside a 7-day window at jaccard 0.7, so indexed fixture
#: text would be refused and the reaper would be tested against an empty queue.
_SEED_TEXTS = {
    "mover_fri": "$TEAM +35.3% on Friday, its best single session since 2021.",
    "theme_today": "Commodities Metals ripping, +7.2% avg today. $WWR $AREC $CENX.",
    "watch_weekend": "$AAPL has gone quiet. Recent trading centered on 297, "
                     "and that level needs to hold into the week.",
    "chart_clean": "$CLF has to hold 11.6 or the whole setup goes stale on me.",
}


def _seed(tmp_path: Path, key: str, *, kind: str, provenance: str,
          as_of: str, scheduled_at: str, now: datetime) -> str:
    from engine.marketing.outbox import enqueue, make_item

    item = make_item(account="flagship", kind=kind, text=_SEED_TEXTS[key],
                     as_of=as_of, scheduled_at=scheduled_at,
                     provenance=provenance, now=now)
    rc = enqueue(item, root=tmp_path, max_per_account_day=99)
    assert rc == "queued", f"fixture refused by the enqueue guards: {rc}"
    return str(item["id"])


class TestTheDeadSessionReaper:

    def _queue(self, tmp_path: Path) -> dict[str, str]:
        born = _SAT - timedelta(hours=6)
        return {
            "mover_fri": _seed(tmp_path, "mover_fri", kind="mover",
                               provenance="content_studio", as_of="2026-08-07",
                               scheduled_at="2026-08-08T13:30:00Z", now=born),
            "theme_today": _seed(tmp_path, "theme_today", kind="theme_list",
                                 provenance="content_studio", as_of="2026-08-08",
                                 scheduled_at="2026-08-08T12:00:00Z", now=born),
            "watch_weekend": _seed(tmp_path, "watch_weekend", kind="watchlist",
                                   provenance="weekend_levels", as_of="2026-08-08",
                                   scheduled_at="2026-08-08T11:00:00Z", now=born),
            "chart_clean": _seed(tmp_path, "chart_clean", kind="chart",
                                 provenance="content_studio", as_of="2026-08-08",
                                 scheduled_at="2026-08-08T16:30:00Z", now=born),
        }

    def test_it_retires_the_dead_rows_and_spares_the_live_ones(self, tmp_path):
        """One sweep over a queue shaped like the operator's Saturday outbox."""
        from engine.marketing.outbox import expire_dead_session_items, fold_state

        ids = self._queue(tmp_path)
        out = expire_dead_session_items(tmp_path, now=_SAT)
        status = fold_state(tmp_path)["status"]

        assert status[ids["mover_fri"]] == "quarantined", out
        assert status[ids["theme_today"]] == "quarantined", out
        assert status[ids["watch_weekend"]] == "queued", out
        assert status[ids["chart_clean"]] == "queued", out
        assert out["expired"] == 2, out
        assert out["by_reason"] == {"expired_session": 2}, out

    def test_the_note_carries_the_prefix_and_the_reason(self, tmp_path):
        """The admin quarantine view shows the note verbatim, so the prefix is
        the operator's grep and the sentence is the argument."""
        from engine.marketing.outbox import expire_dead_session_items, fold_state

        ids = self._queue(tmp_path)
        expire_dead_session_items(tmp_path, now=_SAT)
        note = str((fold_state(tmp_path)["last"][ids["mover_fri"]] or {}).get("note"))
        assert note.startswith("expired_session: "), note
        assert "cannot post on Saturday" in note, note

    def test_it_is_idempotent(self, tmp_path):
        """It runs every ~5 minutes forever. A second sweep must find nothing:
        everything it touched left the queued/approved set."""
        from engine.marketing.outbox import expire_dead_session_items

        self._queue(tmp_path)
        first = expire_dead_session_items(tmp_path, now=_SAT)
        second = expire_dead_session_items(tmp_path, now=_SAT)
        third = expire_dead_session_items(tmp_path, now=_SAT)
        assert first["expired"] == 2, first
        assert second["expired"] == 0 and second["ids"] == [], second
        assert third["expired"] == 0, third

    def test_stale_day_language_is_retired_on_a_due_item(self, tmp_path):
        """The second leg. A `chart` is not a same-day kind, so leg one spares
        it; its copy says "today" on a Saturday, so leg two does not."""
        from engine.marketing.outbox import (
            enqueue, expire_dead_session_items, fold_state, make_item)

        born = _SAT - timedelta(hours=6)
        item = make_item(account="flagship", kind="chart",
                         text="$UAL printed its tightest range in 7 sessions "
                              "today, and that is the whole story.",
                         as_of="2026-08-07", scheduled_at="2026-08-08T13:30:00Z",
                         provenance="content_studio", now=born)
        assert enqueue(item, root=tmp_path, max_per_account_day=99) == "queued"

        out = expire_dead_session_items(tmp_path, now=_SAT)
        assert out["by_reason"] == {"expired_session_language": 1}, out
        note = str((fold_state(tmp_path)["last"][item["id"]] or {}).get("note"))
        assert note.startswith("expired_session_language: "), note

    def test_an_item_whose_slot_has_not_arrived_is_left_alone(self, tmp_path):
        """THE ONE NON-MONOTONE FRAME. "overnight" is false at 20:00 Sunday and
        TRUE at the Monday pre-open it was written for, so leg two judges DUE
        items only. A reaper that ran ahead of the slot would be a shredder."""
        from engine.marketing.outbox import (
            enqueue, expire_dead_session_items, fold_state, make_item)

        sunday_night = datetime(2026, 8, 9, 23, 0, 0, tzinfo=timezone.utc)
        item = make_item(account="flagship", kind="chart",
                         text="While New York slept, $UAL printed its tightest "
                              "range in seven sessions.",
                         as_of="2026-08-10", scheduled_at="2026-08-10T12:00:00Z",
                         provenance="content_studio", now=sunday_night)
        assert enqueue(item, root=tmp_path, max_per_account_day=99) == "queued"

        out = expire_dead_session_items(tmp_path, now=sunday_night)
        assert out["expired"] == 0, out
        assert fold_state(tmp_path)["status"][item["id"]] == "queued"

    def test_it_never_touches_a_dead_or_posted_row(self, tmp_path):
        """Scope: queued and approved only. Re-transitioning a posted item is an
        illegal transition and would log a warning on every tick forever."""
        from engine.marketing.outbox import (
            expire_dead_session_items, fold_state, transition)

        ids = self._queue(tmp_path)
        for st in ("approved", "posting", "posted"):
            assert transition(ids["mover_fri"], st, actor="test", root=tmp_path,
                              now=_SAT - timedelta(hours=1))
        out = expire_dead_session_items(tmp_path, now=_SAT)
        assert ids["mover_fri"] not in out["ids"], out
        assert fold_state(tmp_path)["status"][ids["mover_fri"]] == "posted"


class TestThePressWireCommitsTheExpiry:

    def test_the_reap_runs_all_three_reapers_and_never_raises(self, tmp_path,
                                                              monkeypatch):
        """WHY THIS LANE. Every other reaper in the estate is called from the
        publish sweep, which does not run while MARKETING_PUBLISH_ENABLED is
        off. This one ticks every ~5 minutes and commits regardless, which is
        what makes an expiry PERSIST."""
        import engine.marketing as _pkg
        import scripts.marketing_press_wire as pw

        called: list[str] = []

        class _Fake:
            @staticmethod
            def expire_stale_planned(root, **kw):
                called.append("planned")
                return {"expired": 1}

            @staticmethod
            def expire_stale_wire(root, **kw):
                called.append("wire")
                return {"expired": 2}

            @staticmethod
            def expire_dead_session_items(root, **kw):
                called.append("session")
                return {"expired": 3, "by_reason": {"expired_session": 3}}

        # THE PACKAGE ATTRIBUTE, NOT sys.modules. `from engine.marketing import
        # outbox` resolves through `getattr(package, "outbox")` once the
        # submodule is imported, so a sys.modules patch is a no-op the test
        # would never notice — it would pass on the real reapers finding an
        # empty tmp queue (memory: monkeypatch-of-a-no-longer-called-function).
        monkeypatch.setattr(_pkg, "outbox", _Fake)
        tally = pw.reap_outbox(tmp_path, now=_SAT)
        assert called == ["planned", "wire", "session"], called
        assert tally == {"planned": 1, "wire": 2, "session": 3}, tally

    def test_a_broken_reaper_costs_the_lane_nothing(self, tmp_path, monkeypatch,
                                                    capsys):
        """Housekeeping must never cost the press lane its poll or its commit."""
        import engine.marketing as _pkg
        import scripts.marketing_press_wire as pw

        class _Boom:
            @staticmethod
            def expire_stale_planned(root, **kw):
                raise RuntimeError("ledger unreadable")

        monkeypatch.setattr(_pkg, "outbox", _Boom)
        assert pw.reap_outbox(tmp_path, now=_SAT) == {
            "planned": 0, "wire": 0, "session": 0}
        # The zeros must come from the CAUGHT exception, not from a patch that
        # silently did nothing: the annotation is the proof it was raised.
        out = capsys.readouterr().out
        assert "::warning title=press-wire-reap::" in out, out
        assert "ledger unreadable" in out, out
        assert any(line.startswith("::warning") for line in out.splitlines()), out

    def test_a_dry_run_writes_nothing(self, tmp_path):
        """`--dry-run` is non-consuming by construction everywhere in this
        script, and a reaper is the last place to break that."""
        import scripts.marketing_press_wire as pw
        from engine.marketing.outbox import fold_state

        ids = TestTheDeadSessionReaper()._queue(tmp_path)
        assert pw.reap_outbox(tmp_path, now=_SAT, dry_run=True) == {
            "planned": 0, "wire": 0, "session": 0}
        status = fold_state(tmp_path)["status"]
        assert all(status[i] == "queued" for i in ids.values()), status

    def test_the_reap_runs_before_anything_can_stand_the_run_down(self):
        """PLACEMENT IS THE FEATURE. A missing press_sources.yml returns 0 from
        `run()`, and an outbox rotting behind a disarmed publisher must not also
        depend on the press lane being configured. Pinned by source order, which
        is the only thing that can express "before the early return"."""
        src = (ROOT / "scripts" / "marketing_press_wire.py").read_text(
            encoding="utf-8")
        body = src.split("def run(root:", 1)[1]
        reap_at = body.index("reap_outbox(root, now=ts")
        standdown_at = body.index("if daemon_active():")
        early_return = body.index('press_sources.yml missing or empty')
        assert standdown_at < reap_at < early_return, (
            "the reap must sit AFTER the daemon stand-down (two writers on one "
            "ledger) and BEFORE the press-config early return")

    def test_the_workflow_stages_the_outbox_it_now_writes(self):
        """The reap is only real if the commit step picks it up. Two halves:
        the sparse cone has to CONTAIN data/marketing, and the ledger-law
        `git add` has to name the outbox. Either one missing and the expiry is
        computed 288 times a day and thrown away."""
        wf = (ROOT / ".github" / "workflows" /
              "marketing-press-wire.yml").read_text(encoding="utf-8")
        assert re.search(r"^\s*data/marketing\s*$", wf, re.MULTILINE), (
            "data/marketing is not in the sparse-checkout cone")
        assert "git add data/marketing/outbox" in wf, (
            "the commit step does not stage the outbox")
