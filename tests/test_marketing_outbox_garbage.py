"""The four outbox-garbage laws (operator 2026-08-06).

    "its full of garbage and shit... theres garbage piling up in outbox everyday."

Four defects, each measured on the live corpus before it was fixed, each pinned
here by a test that FAILS without its change:

  D1  a post claiming market ACTION is publishable only while its facts belong
      to the session that is currently live. Same-day intraday and same-day
      after-close both ship; the next session opening kills it.
  D2  the clerical diary register ("I log the buy", "I write down the market's
      story") is not a reaction.
  D3  advertised abstention ("I passed", "I'm watching, not chasing", "I can't
      separate the two yet") is banned outright, not capped.
  D4  a numeric fact posts once per cooldown window, NETWORK-WIDE, fingerprinted
      on (indicator, VALUE) — a NEW number is news and ships.

EVERY FALSE-POSITIVE CASE IN HERE IS LOAD-BEARING. Four review rounds on a
sibling change each caught a "fix" that cleaned up the feed by making posts stop
existing, and the operator has spent a week with too FEW posts. A gate that
silences a lane is worse than the defect it fixes, so the survivor fixtures below
are graded as strictly as the refusals.
"""
from __future__ import annotations

import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.marketing import copywriter as cw  # noqa: E402
from engine.marketing import market_clock as mc  # noqa: E402

# 2026 calendar anchors used throughout. Aug 3 Mon … Aug 7 Fri; Aug 8/9 weekend.
MON = datetime(2026, 8, 3, 18, 0, tzinfo=timezone.utc)          # 14:00 ET Mon
TUE_INTRADAY = datetime(2026, 8, 4, 15, 0, tzinfo=timezone.utc)  # 11:00 ET Tue
TUE_AFTER_CLOSE = datetime(2026, 8, 5, 1, 0, tzinfo=timezone.utc)  # 21:00 ET Tue
WED_MORNING = datetime(2026, 8, 5, 13, 0, tzinfo=timezone.utc)   # 09:00 ET Wed
SAT = datetime(2026, 8, 8, 20, 0, tzinfo=timezone.utc)           # 16:00 ET Sat
SUN = datetime(2026, 8, 9, 20, 0, tzinfo=timezone.utc)           # 16:00 ET Sun


# ─────────────────────────────────────────────────────────────────────────────
# D1 — the session-freshness law
# ─────────────────────────────────────────────────────────────────────────────

class TestD1StaleSession:
    """MUTATION CHECK for this class: in `market_clock.stale_session_violations`,
    delete the `if fact_session < live:` append (leg one) — the two "one session
    late" tests fail; delete the `_stale_claim_in_copy` append (leg two) — the
    live theme_list test fails. Restore by editing the lines back IN PLACE; a
    `git checkout` restores HEAD, not your fix.
    """

    def test_the_live_theme_list_defect_verbatim(self):
        """THE POST, from data/marketing/outbox/items.jsonl, planned for
        2026-08-05T12:00Z and still offering an Approve button on Wednesday.

        Its `as_of` is Wednesday, so the first leg cannot see it: the row is
        stamped today and only the COPY says Tuesday. Leg two is the whole reason
        this gate reads the sentence as well as the stamp.
        """
        text = ("Autonomous Systems ripping, +1.9% avg on Tuesday\n\n"
                "$AMBA +16.1% $AMZN +15.3% $OUST +9.8% $GOOGL +6.7%")
        bad = mc.stale_session_violations(
            text, now=WED_MORNING, fact_asof="2026-08-05", kind="theme_list")
        assert bad, "the 35h '+1.9% avg on Tuesday' post shipped on Wednesday"
        assert bad[0].startswith("stale_session_claim:2026-08-04")

    def test_one_session_late_is_refused(self):
        """Monday's tape offered on Tuesday. The operator's "you cant post
        yesterdays action today" leg, on the item's own stamp."""
        bad = mc.stale_session_violations(
            "$AMZN closed +15.3%.", now=TUE_INTRADAY,
            fact_asof="2026-08-03", kind="mover")
        assert bad and bad[0].startswith("stale_session:2026-08-03!=2026-08-04")

    def test_same_day_intraday_ships(self):
        assert mc.stale_session_violations(
            "$AMZN is up 15.3% so far today.", now=TUE_INTRADAY,
            fact_asof="2026-08-04", kind="mover") == []

    def test_same_day_after_close_ships(self):
        """THE BOUNDARY THE OPERATOR NAMED FIRST: "you can post about tickers
        during market hours and after market closes anytime". 21:00 ET on the
        session day is current, not stale."""
        assert mc.stale_session_violations(
            "$AMZN closed +15.3% today.", now=TUE_AFTER_CLOSE,
            fact_asof="2026-08-04", kind="mover") == []

    @pytest.mark.parametrize("now,label", [(SAT, "Saturday"), (SUN, "Sunday")])
    def test_friday_copy_survives_the_whole_weekend(self, now, label):
        """No new session has opened, so Friday is still the live tape. A gate
        that expired this would mute every desk from Friday close to Monday."""
        assert mc.stale_session_violations(
            "$AMZN closed +15.3% on Friday.", now=now,
            fact_asof="2026-08-07", kind="mover") == [], label

    @pytest.mark.parametrize("stamp", [None, "", "not-a-date", "2026-13-45", {}])
    def test_a_missing_or_malformed_as_of_is_never_stale(self, stamp):
        """A garbled stamp must not be the reason a good post dies. Leg one
        simply does not run; leg two still reads the copy."""
        assert mc.stale_session_violations(
            "$AMZN is up 15.3% so far today.", now=TUE_INTRADAY,
            fact_asof=stamp, kind="mover") == [], repr(stamp)

    def test_a_post_with_no_market_action_claim_is_not_judged(self):
        """An education post has no session to be stale about, and an insider
        filing perishes on the filing's clock, not the tape's."""
        for kind, text in (
            ("education", "Sizing off the stop instead of the conviction halved "
                          "what the win was worth."),
            ("insider", "Klein opened a 350,000-share position in $XIIIU."),
        ):
            assert mc.stale_session_violations(
                text, now=WED_MORNING, fact_asof="2026-08-03", kind=kind) == [], kind

    def test_a_historical_anchor_is_a_citation_not_a_claim(self):
        """THE FALSE POSITIVE THAT REPLAY CAUGHT, and it was the expensive one:
        a first cut refused 78 of 492 live items that shipped exactly on time,
        every one of them citing a date while reporting the current tape.
        """
        for text in (
            "Apple $AAPL is down -9.29% so far today, now -11.06% from its "
            "all-time high of 340.08 set on July 28.",
            "$GOOGL is up 5.23% right now, with a 2-day winning streak since "
            "July 29.",
            "GPI has held 305.85, the average price paid since the Jun 26 volume "
            "spike, for 16 straight sessions.",
            "The July jobs numbers are due out Friday.",
        ):
            assert mc.stale_session_violations(
                text, now=WED_MORNING, fact_asof="2026-08-05",
                kind="breaking") == [], text[:60]

    def test_a_forward_booked_row_is_not_stale(self):
        """A fact session AHEAD of the live one belongs to the booking lanes;
        double-refusing it here would quarantine every forward-booked post."""
        assert mc.stale_session_violations(
            "$AMZN closed +15.3%.", now=MON,
            fact_asof="2026-08-07", kind="mover") == []

    def test_live_session_spans_the_session_day_and_holds_over_the_weekend(self):
        assert mc.live_session(TUE_INTRADAY) == date(2026, 8, 4)
        assert mc.live_session(TUE_AFTER_CLOSE) == date(2026, 8, 4)
        assert mc.live_session(SAT) == date(2026, 8, 7)
        assert mc.live_session(SUN) == date(2026, 8, 7)

    def test_the_publisher_calls_the_gate(self):
        """The law is worth nothing in a module nobody asks. Pins the wiring at
        the LAST line before the network, per the brief: an item can be approved
        at any hour, so a generation-time check answers at the wrong moment."""
        import scripts.marketing_publisher as pub

        it = {"id": "ob-x", "as_of": "2026-08-03", "kind": "theme_list"}
        reasons = pub._clock_violations(
            it, "Autonomous Systems ripping, +1.9% avg on Monday", TUE_INTRADAY)
        assert any(r.startswith("stale_session") for r in reasons), reasons


# ─────────────────────────────────────────────────────────────────────────────
# D2 — the clerical diary register
# ─────────────────────────────────────────────────────────────────────────────

#: Verbatim from live copy. Operator: "all of this I this I that... 'I write
#: down' 'I log' sounds like a bot LLM. No human says that."
DIARY_LIVE = [
    "$N's CEO opened a new 25,477-share stake at $19.6. I log the buy and leave "
    "the motive blank.",
    "1. I write down the market's current story.\n2. I note the fact that would "
    "make me reconsider it.",
    "Klein opened a 350,000-share position in $XIIIU. I log the filing and wait.",
    "$EWAV has a new 1.09M-share position from Space Summit Capital. I'm logging "
    "the buy, not inventing a reason the filing doesn't give.",
]


class TestD2DiaryVoice:
    """MUTATION CHECK: comment out the `out += diary_voice_violations(text)` line
    in `copywriter.queued_voice_violations` — `test_the_queue_screen_catches_it`
    fails. Empty `_DIARY_VERBS` to `()` — every case below fails."""

    @pytest.mark.parametrize("text", DIARY_LIVE)
    def test_live_diary_lines_are_refused(self, text):
        assert cw.diary_voice_violations(text), text[:60]

    @pytest.mark.parametrize("text", DIARY_LIVE)
    def test_the_queue_screen_catches_it(self, text):
        """The queue is a bypass around every generation-time law: the outbox was
        holding 492 items when this landed."""
        assert any("clerical diary" in v
                   for v in cw.queued_voice_violations(text, "insider"))

    @pytest.mark.parametrize("text", [
        "The filing was logged with the SEC on Tuesday.",
        "$GE printed a fresh record high on the week.",
        "We flagged it at 41.20 and the entry is on the page.",
        "Note the size: 350,000 shares is a third of the float.",
        "That was the loudest day on record for the group.",
    ])
    def test_ordinary_english_about_the_world_survives(self, text):
        """Only "I log it" narrates the author's clerical work. "The filing was
        logged", "on record", "record high" are about the world."""
        assert cw.diary_voice_violations(text) == [], text


# ─────────────────────────────────────────────────────────────────────────────
# D3 — advertised abstention
# ─────────────────────────────────────────────────────────────────────────────

#: The eight strings the operator measured on data/marketing/content_plan.json,
#: 8 of 66 (12.1%) of one nightly plan's copy.
ABSTENTION_LIVE = [
    "$CWK keeps failing at its long-term price line. I stayed out.",
    "$ARES keeps holding 123. I passed early and won't chase it now.",
    "I passed on $PI at 131. Buyers didn't.",
    "Four red closes and $CRL is still marking up. I passed.",
    "$NUE closed at a fresh yearly high. I passed and won't chase.",
    "I passed on $ARES It held 123 for 23 sessions. Not ideal.",
    "$HII just joined the movers around $326. I'm watching, not chasing.",
    "$SSPC, base building or stalling?\n\nI can't separate the two yet, so I "
    "passed. 🔍",
]

#: FIRST PERSON IS 26% OF THE CORPUS AND THE VOICE LAW REQUIRES IT. Every line
#: here is a real stance in the first person and MUST survive — this is the check
#: that matters most, because the way this fix fails is by taking the voice with
#: the defect.
STANCE_SURVIVORS = [
    "$VST up 9% and every target on the street just got lapped. I'm not paying "
    "this price.",
    "314 is the line. If it goes, I was early and I'll say so.",
    "$NVDA closed at 207. If it loses 203 the whole thing was noise.",
    "My read was wrong. Buyers defended 127 and I said they wouldn't.",
    "Stopped out of $COIN at 198, -3.1%. Tuition paid. Next.",
    "I don't have a clean explanation and I'm not going to invent one.",
    "I like it, and that makes me soft on it.",
    "Buyers didn't show up at 131.",
    "I want 314 before this is a conversation.",
    "If I can't tell you where I'm wrong, I don't post it.",
    "I respect the strength. 314 is where it stops being respectable.",
]


class TestD3Abstention:
    """MUTATION CHECK: empty `_ABSTENTION_PATTERNS` to `()` — every refusal test
    fails and every survivor test still passes (which is how you know the
    survivor half is not vacuous). Comment out the `abstention_violations` line
    in `validate_copy_v2` — `test_the_generation_gate_catches_it` fails."""

    @pytest.mark.parametrize("text", ABSTENTION_LIVE)
    def test_the_measured_lines_are_refused(self, text):
        assert cw.abstention_violations(text), text[:60]

    @pytest.mark.parametrize("text", ABSTENTION_LIVE)
    def test_the_queue_screen_catches_it(self, text):
        assert any("advertised abstention" in v
                   for v in cw.queued_voice_violations(text, "watchlist"))

    def test_the_generation_gate_catches_it(self):
        """Dual-wired. Fixing the writer fixes tomorrow; only the queue screen
        fixes the 492 items already sitting in the outbox, and only the writer
        gate stops tonight's plan being written this way in the first place."""
        ctx = {"type": "watchlist", "ticker": "", "account": "flagship",
               "numbers_whitelist": []}
        out = cw.validate_copy_v2("I passed on it and won't chase.", ctx)
        assert any("advertised abstention" in v for v in out), out

    @pytest.mark.parametrize("text", STANCE_SURVIVORS)
    def test_a_real_first_person_stance_survives(self, text):
        assert cw.abstention_violations(text) == [], text

    def test_no_deterministic_bank_line_is_an_abstention(self):
        """THE SWEEP, and the reason it is here rather than in a fixture list:
        the `watchlist_runaway` family was the register END TO END ("went without
        me", "gone, not chasing", "ran before I got there"). Rewriting it rather
        than deleting it is what kept the lane's post count intact — the bank
        still has 275 entries.
        """
        bad = []
        n = 0
        for key, entries in cw._TEMPLATES.items():
            for i, variant in enumerate(entries):
                n += 1
                joined = f"{variant[0]} {variant[1]}"
                for v in cw.abstention_violations(joined) + cw.diary_voice_violations(joined):
                    bad.append(f"{key}[{i}]: {v[:90]}")
        assert n >= 250, f"only {n} bank lines walked — the sweep is vacuous"
        assert not bad, "a template bank line advertises inaction:\n" + "\n".join(bad)

    def test_no_bank_is_left_unable_to_fill_its_slot(self):
        """A voice bank with no usable lines is a silent slot, which is the one
        outcome this whole program exists to prevent."""
        empty = [key for key, entries in cw._TEMPLATES.items() if not entries]
        assert not empty, f"empty template banks: {empty}"

    def test_the_theme_tails_no_longer_advertise_indecision(self):
        """The 2026-08-03 tail bank kept the cost by making the author admit he
        could not read the group ("Is my read on this group any good today?").
        The replacement asks about the TAPE'S next move instead, and still has to
        satisfy every structural rule the tail cannot escape."""
        from engine.marketing import movers_source as ms
        from engine.marketing.publish_time_content import _tail_is_bait

        pools = list(ms._TAIL_DOWN) + list(ms._TAIL_UP)
        assert len(pools) >= 8
        for tail in pools:
            assert cw.abstention_violations(tail) == [], tail
            assert tail.endswith("?"), tail
            assert not _tail_is_bait(tail), tail
            assert len(tail) <= ms._TAIL_MAX_CHARS, tail

    def test_the_house_law_no_longer_invites_the_defect(self):
        """THE ROOT CAUSE. "A fact plus a reaction that COSTS the author" made
        the cheapest cost — admitting the desk did nothing — the compliant
        answer. The law's own approved exemplar was "I looked at it twice and
        passed both times", so the config had to change with the guard.
        """
        import yaml

        cfg = yaml.safe_load((ROOT / "config" / "marketing.yml").read_text(
            encoding="utf-8"))
        laws = ((cfg.get("copywriter") or {}).get("copy_laws")
                or cfg.get("copy_laws") or [])
        assert laws, "copy_laws not found — this guard would be vacuous"
        joined = " ".join(str(x) for x in laws).lower()
        assert "i passed" in joined and "banned outright" in joined, (
            "no copy law bans the did-nothing reaction")
        for retired in ("a pass you regret", "passed both times"):
            assert retired not in joined, (
                f"the law still invites the defect: {retired!r}")

    def test_the_writer_prompt_bans_it_too(self):
        """A validator that rejects copy the prompt asked for teaches the desk to
        stop obeying. The prompt and the guard have to agree."""
        src = (ROOT / "engine" / "marketing" / "copywriter.py").read_text(
            encoding="utf-8")
        assert "SAYING YOU DID NOTHING IS NOT A COST" in src
        assert "AT MOST ONE POST IN THREE may say you were late" not in src, (
            "the prompt still licenses the register at a 1-in-3 rate")


# ─────────────────────────────────────────────────────────────────────────────
# D4 — one numeric fact, one post, network-wide
# ─────────────────────────────────────────────────────────────────────────────

#: The measured family: ONE fact, generated on five days across seven accounts,
#: TWO of them posted. Operator: "holy fuck the 203k claims it was posted so many
#: times everywhere."
CLAIMS_FAMILY = [
    "203k claims a week this month, 8.6% below a year ago. Meanwhile the Atlanta "
    "Fed's tracker is printing 5.0% growth and the Cleveland median CPI is 2.1%.",
    "Jobless claims averaging 203k this month, 8.6% below a year ago. Atlanta Fed "
    "GDPNow has this quarter at a 5.0% annual rate.",
    "203k jobless claims, 5.0% GDPNow, 2.1% median CPI. Growth firming while "
    "inflation stays tame.",
    "203k claims, GDP tracking 5.0%, median CPI still 2.1%",
    "claims hit 203k this month, 8.6% below a year ago. meanwhile the atlanta fed "
    "is tracking 5.0% gdp and cleveland cpi is 2.1%",
    "I keep waiting for the labor market to crack, and jobless claims keep "
    "averaging 203 thousand a week this month.",
    "Jobless claims: 203 thousand a week, 8.6% below a year ago / GDPNow: 5.0% "
    "annual growth / Median CPI: 2.1% annual inflation",
]


class TestD4NumericFactCooldown:
    """MUTATION CHECK: make `macro_fact_keys` return `frozenset()` — every
    fingerprint test fails. Set `FACT_COOLDOWN_DAYS_DEFAULT["macro"] = 5` —
    `test_the_weekly_window_covers_a_week` fails (5 days is exactly the window
    that let the same 203k come back around looking new)."""

    def test_the_whole_family_collapses_onto_one_fact(self):
        """Seven strings, seven phrasings, one number. Every text-similarity gate
        in the estate saw seven different posts, because they ARE seven different
        strings — which is why the fingerprint is on (indicator, VALUE)."""
        first = mc.macro_fact_keys(CLAIMS_FAMILY[0])
        assert first, "the lead post carries no fingerprint at all"
        for other in CLAIMS_FAMILY[1:]:
            shared = first & mc.macro_fact_keys(other)
            assert shared, f"no shared key with the lead post: {other[:60]!r}"

    def test_a_new_value_is_news_and_ships(self):
        """THE CHECK THAT KEEPS THIS FROM BEING A MUTE BUTTON. GDPNow moved 5.0
        -> 5.9 on 2026-08-06 and both numbers were live in the corpus that night.
        A key on the indicator alone would have killed the new print."""
        old = mc.macro_fact_keys(CLAIMS_FAMILY[1])
        new = mc.macro_fact_keys(
            "GDPNow has growth at 5.9%. AI and chips are carrying a narrow tape.")
        assert new, "the new print carries no fingerprint"
        assert not (old & new), f"a NEW value collided with the old one: {old & new}"

    def test_an_alias_and_its_indicator_share_a_key(self):
        """"GDPNow has growth at 5.9%" and a bare "Growth: 5.9%" are one number
        under two names. Keying them apart is how three phrasings read as fresh."""
        a = mc.macro_fact_keys("GDPNow has growth at 5.9%.")
        b = mc.macro_fact_keys("Growth: 5.9% annual rate this quarter")
        assert a & b, (a, b)

    def test_company_copy_is_never_macro_keyed(self):
        """"Growth" and "inflation" are also ordinary words about a COMPANY. Two
        desks writing about two different names must not collide on
        `macro:gdpnow:12pct` — a terminal refusal earned by a coincidence."""
        assert mc.macro_fact_keys("$NVDA posted revenue growth of 12%.") == frozenset()
        assert mc.macro_fact_keys("$AMD growth ran at 12% last quarter.") == frozenset()

    def test_bare_counts_are_not_fingerprints(self):
        """Ordinary copy counts things. Fingerprinting "the 4th time" or "23
        sessions" would collapse unrelated posts onto one key."""
        assert mc.macro_fact_keys(
            "Claims found buyers at that level for the 4th time in 23 sessions."
        ) == frozenset()

    def test_the_wire_lane_is_exempt(self):
        """The Fed's 2% inflation TARGET appears in almost every central-bank
        headline. A 7-day hold on `macro:cpi:2pct` would mute the biggest lane in
        the queue on the strength of a number nobody reports as news; the wire
        already dedups on its own story key."""
        text = ("Fed's Williams: rate policy still well positioned to reach 2% "
                "inflation")
        assert not any(k.startswith("macro:")
                       for k in mc.fact_anchor_keys(text, "breaking"))
        assert any(k.startswith("macro:")
                   for k in mc.fact_anchor_keys(text, "macro"))

    def test_the_weekly_window_covers_a_week(self):
        """Claims and GDPNow are WEEKLY prints. The fan-out gate's 5-day window is
        right for a tape move and is exactly what let the same number come back
        around on day six looking new."""
        assert mc.fact_cooldown_days("macro:claims:203k") == 7
        assert mc.fact_cooldown_days("pct:mover:AMZN:15.3") == 5
        assert mc.fact_cooldown_days("ratio:4of11:sector") == 5

    def test_the_window_is_config_driven_and_typo_safe(self):
        assert mc.fact_cooldown_days("macro:claims:203k", {"macro": 3}) == 3
        assert mc.fact_cooldown_days("macro:claims:203k", {"macro": "seven"}) == 7
        assert mc.fact_cooldown_days("macro:claims:203k", {"macro": None}) == 7

    def test_config_carries_the_window(self):
        import yaml

        cfg = yaml.safe_load((ROOT / "config" / "marketing.yml").read_text(
            encoding="utf-8"))
        windows = (cfg.get("publish") or {}).get("fact_cooldown_days") or {}
        assert int(windows.get("macro")) == 7, windows

    def test_the_publisher_holds_a_macro_fact_for_its_own_window(self):
        """THE WIRING, over the folded state the publisher actually reads. Six
        days apart: inside the macro window, outside the tape one."""
        import scripts.marketing_publisher as pub

        state = {
            "items": {
                "ob-a": {"as_of": "2026-08-01", "kind": "macro",
                         "text": CLAIMS_FAMILY[0]},
                "ob-b": {"as_of": "2026-08-07", "kind": "macro",
                         "text": CLAIMS_FAMILY[2]},
            },
            "status": {"ob-a": "posted", "ob-b": "queued"},
            "held": set(),
        }
        now = datetime(2026, 8, 7, 18, 0, tzinfo=timezone.utc)
        owners = pub._fact_anchor_owners(state, now)
        mine = mc.fact_anchor_keys(CLAIMS_FAMILY[2], "macro")
        assert any(owners.get(k) == "ob-a" for k in mine), (
            "the 6-day-old sibling does not hold the fact — the second post ships")

    def test_the_tape_window_did_not_widen_with_the_macro_one(self):
        """A per-family window that quietly widened every family would be a
        different, worse gate."""
        import scripts.marketing_publisher as pub

        state = {
            "items": {
                "ob-a": {"as_of": "2026-08-01", "kind": "mover",
                         "text": "$AMZN +15.3% today"},
                "ob-b": {"as_of": "2026-08-07", "kind": "mover",
                         "text": "$AMZN +15.3% today"},
            },
            "status": {"ob-a": "posted", "ob-b": "queued"},
            "held": set(),
        }
        now = datetime(2026, 8, 7, 18, 0, tzinfo=timezone.utc)
        owners = pub._fact_anchor_owners(state, now)
        assert owners.get("pct:mover:AMZN:15.3") == "ob-b", (
            "the 6-day-old tape fact still holds the anchor; the 5-day window "
            f"widened with the macro one: {owners}")


# ─────────────────────────────────────────────────────────────────────────────
# R1 — the cooldown keys the LEAD fact, not every number in the post
#
# The round-1 blocker, measured on the live outbox at 2026-08-06: the gate broke
# on the first anchor key any live sibling owned, so macro survived 0/6, event
# 0/2 and mover 0/2, and BOTH carriers of the genuinely new 5.0 -> 5.9 GDPNow
# print were refused — one of them on `macro:claims:203k`, owned by a post four
# days older. The new number reached the network on no carrier at all.
# ─────────────────────────────────────────────────────────────────────────────

#: The live carriers, verbatim (ob-2026-08-06-96202a0efb / -981729f9e1).
NEW_PRINT_MACRO = (
    "Growth: 5.9% annual rate this quarter\n"
    "Inflation: 2.1% annual rate\n"
    "Jobless claims: 203 thousand a week this month\n"
    "I kept waiting for the economy to cool. It hasn't obliged.")
NEW_PRINT_EVENT = (
    "GDPNow has growth at 5.9%. AI and chips are carrying a narrow tape.\n\n"
    "I respect the strength, but I'm not chasing leadership this thin.")


class TestR1LeadFact:
    """MUTATION CHECK: in `scripts/marketing_publisher`, swap both
    `_clock.lead_fact_keys(` calls back to `_clock.fact_anchor_keys(` —
    `test_a_new_lead_fact_ships_although_its_body_recites_last_weeks_numbers`
    and `test_a_recited_number_claims_no_anchor` fail. In
    `market_clock.lead_fact_keys`, return `frozenset(k for _p, k in hits)`
    (ignore the lead span) — the same two fail. Restore by editing the lines
    back IN PLACE; a `git checkout` restores HEAD, not your fix."""

    def test_a_new_lead_fact_ships_although_its_body_recites_last_weeks_numbers(self):
        """THE BLOCKER. The lead is a number nobody has posted; lines two and
        three quote last week's prints to frame it, which is what a human
        analyst does. Reading the whole body refused it on `macro:claims:203k`."""
        lead = mc.lead_fact_keys(NEW_PRINT_MACRO, "macro")
        assert lead == frozenset({"macro:gdpnow:5.9pct"}), lead
        assert "macro:claims:203k" in mc.fact_anchor_keys(NEW_PRINT_MACRO, "macro"), (
            "the fixture no longer recites the older print, so it cannot pin "
            "the defect")

    def test_the_rulings_own_worked_example(self):
        """"GDPNow 5.9%, up from 5.0% last week" is a good post and must ship.
        A gate that keys the 5.0% as well refuses it on a number it quoted only
        to say the new one is different."""
        keys = mc.lead_fact_keys("GDPNow 5.9%, up from 5.0% last week.", "macro")
        assert keys == frozenset({"macro:gdpnow:5.9pct"}), keys

    def test_a_recited_number_claims_no_anchor(self):
        """SYMMETRY, and it is the half that is easy to miss. If the new print's
        post CLAIMED `macro:claims:203k` on the way through, it would starve the
        post whose lead that number actually is — the fan-out gate would have
        moved the outage rather than fixed it."""
        import scripts.marketing_publisher as pub

        state = {
            "items": {"ob-new": {"as_of": "2026-08-06", "kind": "macro",
                                 "text": NEW_PRINT_MACRO}},
            "status": {"ob-new": "queued"},
            "held": set(),
        }
        owners = pub._fact_anchor_owners(
            state, datetime(2026, 8, 6, 18, 0, tzinfo=timezone.utc))
        assert owners.get("macro:gdpnow:5.9pct") == "ob-new", owners
        assert "macro:claims:203k" not in owners, owners

    def test_the_same_lead_five_days_running_still_collapses(self):
        """A3. The defect the operator reported was never a post that MENTIONS a
        number, it was the same number being the WHOLE post, five days running.
        Every member of the measured family leads on it."""
        leads = [mc.lead_fact_keys(t, "macro") for t in CLAIMS_FAMILY]
        for text, keys in zip(CLAIMS_FAMILY, leads):
            assert "macro:claims:203k" in keys, (text[:60], keys)

    def test_a_headline_carrying_no_number_has_no_lead_fact(self):
        """ob-2026-08-06-33dbf95911 verbatim. Its subject is narrow leadership;
        the 5% GDPNow print underneath is framing, and keying it took the post
        down on a number that is not what it is about."""
        text = ("AI and chip stocks are doing almost all the lifting today\n\n"
                "The Atlanta Fed has the economy growing at 5% this quarter, "
                "but stock leadership is still narrow.")
        assert mc.lead_fact_keys(text, "event") == frozenset()
        assert "macro:gdpnow:5pct" in mc.fact_anchor_keys(text, "event")

    def test_the_lead_span_is_the_first_non_empty_line(self):
        assert mc.lead_segment("") == (0, 0)
        body = "\n\n  \nlead line\nsecond"
        lo, hi = mc.lead_segment(body)
        assert body[lo:hi] == "lead line", (lo, hi)

    def test_the_publisher_refuses_the_second_carrier_and_ships_the_first(self):
        """Two desks reach for the same NEW print in one night. Exactly one
        carries it — first-claim by rank then id — and the other is refused.
        Zero carriers is the failure this whole ruling exists to undo."""
        import scripts.marketing_publisher as pub

        state = {
            "items": {
                "ob-2026-08-02-25d1738564": {
                    "as_of": "2026-08-02", "kind": "macro",
                    "text": CLAIMS_FAMILY[0]},
                "ob-2026-08-06-96202a0efb": {
                    "as_of": "2026-08-06", "kind": "macro",
                    "text": NEW_PRINT_MACRO},
                "ob-2026-08-06-981729f9e1": {
                    "as_of": "2026-08-06", "kind": "event",
                    "text": NEW_PRINT_EVENT},
            },
            "status": {k: "queued" for k in (
                "ob-2026-08-02-25d1738564", "ob-2026-08-06-96202a0efb",
                "ob-2026-08-06-981729f9e1")},
            "held": set(),
        }
        owners = pub._fact_anchor_owners(
            state, datetime(2026, 8, 6, 18, 0, tzinfo=timezone.utc),
            windows={"macro": 7})
        assert owners["macro:gdpnow:5.9pct"] == "ob-2026-08-06-96202a0efb", owners
        assert owners["macro:claims:203k"] == "ob-2026-08-02-25d1738564", owners


# ─────────────────────────────────────────────────────────────────────────────
# R2 — kind exclusion wins over the percent heuristic
# ─────────────────────────────────────────────────────────────────────────────

class TestR2KindExclusion:
    """MUTATION CHECK: delete the `if k in NON_ACTION_KINDS: return ""` branch
    in `market_clock.market_action_claim` — every test in this class fails.
    Restore by editing the line back IN PLACE."""

    #: One string carrying BOTH route-2 triggers: a move phrase and a bare
    #: percent. Anything on the exclusion list has to survive it.
    LOUD = ("203k claims a week this month, 8.6% below a year ago. "
            "Meanwhile the Atlanta Fed is printing 5.0% growth and the tape "
            "closed green.")

    @pytest.mark.parametrize(
        "kind", sorted(mc.NON_ACTION_KINDS))
    def test_an_excluded_kind_is_never_judged_whatever_the_copy_says(self, kind):
        """The docstring named six kinds it does not own and then a second route
        re-admitted them on any percent. Measured on the live outbox: 157/224
        breaking, 10/20 macro, 7/20 event and 1/20 education items came back
        with a non-empty action claim, so a WEEKLY jobless-claims print died at
        the next open with a receipt calling it "a percent move claim"."""
        assert mc.market_action_claim(self.LOUD, kind) == ""
        assert mc.stale_session_violations(
            self.LOUD, now=WED_MORNING, fact_asof="2026-08-04", kind=kind) == []

    def test_the_exclusion_list_is_the_one_the_docstring_names(self):
        assert mc.NON_ACTION_KINDS == frozenset(
            {"macro", "event", "education", "insider", "congress", "breaking"})
        assert not (mc.NON_ACTION_KINDS & mc.ACTION_KINDS), (
            "a kind cannot be both a tape read and exempt from the tape clock")

    def test_route_two_still_admits_the_kinds_it_was_written_for(self):
        """The percent/move-phrase route may only ADMIT kinds this gate has no
        opinion about. A `reply` or an unlabelled item reporting a move is still
        a tape read and still perishes on the session clock."""
        text = "$WDC falls -4.03% right now to $522.86."
        for kind in ("", "reply", "quote"):
            assert mc.market_action_claim(text, kind), kind
            assert mc.stale_session_violations(
                text, now=WED_MORNING, fact_asof="2026-08-04", kind=kind), kind

    def test_a_wire_retry_across_a_session_roll_still_ships(self):
        """Live path since 91b0877057f made a Buffer rate limit RETRY instead of
        delete: a `breaking` flash re-attempted after midnight ET must not be
        stale because a session rolled. The reaper's 3h TTL owns that clock."""
        assert mc.stale_session_violations(
            "Western Digital falls -4.03% right now to $522.86.",
            now=WED_MORNING, fact_asof="2026-08-04", kind="breaking") == []


# ─────────────────────────────────────────────────────────────────────────────
# D1 leg two — the leg that does all the live work (round-1 finding 9)
#
# Leg one fired ZERO times across the whole 492-item corpus on on-time dispatch,
# because `as_of` is stamped to the scheduled day by construction. Leg two is
# the gate in production and it was pinned by exactly one test.
# ─────────────────────────────────────────────────────────────────────────────

class TestD1LegTwo:
    """MUTATION CHECK: in `market_clock._stale_claim_in_copy`, restore the
    amnesty `if _TODAY_RE.search(body) and current_session(now) == live: return
    None` — the two today-word tests and the live-defect test fail. Replace the
    whole function body with `return None` — every test in this class fails.
    Restore by editing the lines back IN PLACE."""

    #: Every weekday name, each judged from a session it is genuinely BEHIND.
    #: The Friday case is the one that has to walk back across a weekend, which
    #: a lookback that only understood "this week" would get wrong.
    FRI = datetime(2026, 8, 7, 18, 0, tzinfo=timezone.utc)    # Fri 14:00 ET
    MON_NEXT = datetime(2026, 8, 10, 18, 0, tzinfo=timezone.utc)  # Mon 14:00 ET

    @pytest.mark.parametrize("day,now,claimed", [
        ("Monday", FRI, "2026-08-03"),
        ("Tuesday", FRI, "2026-08-04"),
        ("Wednesday", FRI, "2026-08-05"),
        ("Thursday", FRI, "2026-08-06"),
        ("Friday", MON_NEXT, "2026-08-07"),
    ])
    def test_every_weekday_name_is_a_session_claim(self, day, now, claimed):
        out = mc.stale_session_violations(
            f"Cloud Computing is +1.7% on average on {day}.",
            now=now, fact_asof=mc.et_date(now).isoformat(), kind="theme_list")
        assert any(v.startswith(f"stale_session_claim:{claimed}") for v in out), out

    def test_the_live_weekday_is_not_a_stale_claim(self):
        """The boundary the parametrization above cannot state: naming TODAY'S
        session is a current report, not a stale one."""
        assert mc.stale_session_violations(
            "Cloud Computing is +1.7% on average on Thursday.",
            now=datetime(2026, 8, 6, 18, 0, tzinfo=timezone.utc),
            fact_asof="2026-08-06", kind="theme_list") == []

    def test_a_month_day_form_is_a_session_claim(self):
        out = mc.stale_session_violations(
            "Cloud Computing ran +1.7% on August 4.",
            now=WED_MORNING, fact_asof="2026-08-05", kind="theme_list")
        assert any(v.startswith("stale_session_claim:2026-08-04") for v in out), out

    def test_a_today_word_is_not_an_amnesty(self):
        """THE ROUND-1 DEFECT. The copy claiming BOTH the live session and a past
        one is not exempt, it is internally contradictory — and the theme_list
        generator emits exactly this wording, so the survivor was the internally
        FALSE one."""
        both = ("Cloud Computing is ripping across the board today\n\n"
                "$AAA $BBB\n"
                "Cloud Computing is +1.7% on average on Tuesday.")
        out = mc.stale_session_violations(
            both, now=WED_MORNING, fact_asof="2026-08-05", kind="theme_list")
        assert out, "a today-word disarmed leg two"
        assert "claims today AND Tuesday" in out[0], out

    def test_the_live_theme_list_defect_in_both_generator_wordings(self):
        """A4. ob-2026-08-03-7faca980f7 verbatim is the today-word wording; the
        operator quoted the other one. Both are the same false post."""
        plain = "Cloud Computing ripping, +1.7% avg on Tuesday"
        live = ("Virtual & Augmented Reality is up across the board today\n\n"
                "$COHR $LITE $AXON $META $RBLX $MSFT $GOOGL $U\n"
                "Virtual & Augmented Reality is +3.7% on average on Friday "
                "(8 names higher).")
        assert mc.stale_session_violations(
            plain, now=WED_MORNING, fact_asof="2026-08-04", kind="theme_list")
        out = mc.stale_session_violations(
            live, now=MON, fact_asof="2026-08-03", kind="theme_list")
        assert any(v.startswith("stale_session_claim:2026-07-31") for v in out), out

    def test_leg_two_is_asserted_INDEPENDENTLY_of_leg_one(self):
        """The item's stamp is right and its SENTENCE is wrong. An as_of-only
        check cannot see this post, which is why leg two is the whole gate."""
        out = mc.stale_session_violations(
            "Cloud Computing is +1.7% on average on Tuesday.",
            now=WED_MORNING, fact_asof="2026-08-05", kind="theme_list")
        assert len(out) == 1 and out[0].startswith("stale_session_claim:"), out

    def test_leg_one_is_asserted_INDEPENDENTLY_of_leg_two(self):
        """And the mirror: a stale stamp with copy that names no session."""
        out = mc.stale_session_violations(
            "Cloud Computing is ripping, +1.7% on average.",
            now=WED_MORNING, fact_asof="2026-08-04", kind="theme_list")
        assert len(out) == 1 and out[0].startswith("stale_session:"), out

    def test_a_citation_survives_the_lost_amnesty(self):
        """The suppression that keeps leg two off historical copy is
        `_claim_is_cited`, NOT the today-word. Removing the amnesty must not
        start eating "its all-time high of 340.08 set on July 28"."""
        assert mc.stale_session_violations(
            "$WDC is -11.06% from its all-time high of 340.08 set on July 28.",
            now=WED_MORNING, fact_asof="2026-08-05", kind="mover") == []

    def test_a_claim_past_the_lookback_is_history_not_a_freshness_claim(self):
        assert mc.stale_session_violations(
            "Cloud Computing is +1.7% on average on July 6.",
            now=WED_MORNING, fact_asof="2026-08-05", kind="theme_list") == []


# ─────────────────────────────────────────────────────────────────────────────
# M2 / m4 — which indicator a number belongs to
# ─────────────────────────────────────────────────────────────────────────────

class TestMacroNameAssignment:
    """MUTATION CHECK: in `market_clock._macro_fact_hits`, delete the
    `if not _name_is_attached(...): continue` line — the value-first and
    two-print tests fail. Delete the `if unit not in _MACRO_UNITS...` line —
    `test_a_count_never_takes_a_rate_indicator` fails. Restore IN PLACE."""

    def test_the_three_live_shapes(self):
        """`<value> <indicator>`, `<indicator> at <value>`, `<indicator>:
        <value>`. A symmetric nearest-name metric got the first one wrong."""
        assert mc.macro_fact_keys("203k jobless claims this month") == frozenset(
            {"macro:claims:203k"})
        assert mc.macro_fact_keys("GDPNow has growth at 5.9%.") == frozenset(
            {"macro:gdpnow:5.9pct"})
        assert mc.macro_fact_keys("Growth: 5.9% annual rate") == frozenset(
            {"macro:gdpnow:5.9pct"})

    def test_the_cpi_value_does_not_take_the_gdpnow_name(self):
        """ob-2026-08-04-8f018b6dbf verbatim. The 2.1% CPI print keyed to GDPNow
        because "GDPNow" sat two characters behind it and "CPI" eight ahead —
        two phrasings of one fact that could never collide, which is the exact
        dedup failure the fingerprint exists to fix."""
        keys = mc.macro_fact_keys("203k jobless claims, 5.0% GDPNow, 2.1% median CPI")
        assert keys == frozenset(
            {"macro:claims:203k", "macro:gdpnow:5pct", "macro:cpi:2.1pct"}), keys

    def test_two_prints_at_one_value_keep_both_names(self):
        """Nearest-wins made the claims print DISAPPEAR: both 203k values took
        "Payrolls" and the set collapsed to one key."""
        keys = mc.macro_fact_keys("Jobless claims at 203k. Payrolls at 203k.")
        assert keys == frozenset(
            {"macro:claims:203k", "macro:payrolls:203k"}), keys
        keys = mc.macro_fact_keys("Claims: 203k Payrolls: 198k")
        assert keys == frozenset(
            {"macro:claims:203k", "macro:payrolls:198k"}), keys

    def test_a_count_never_takes_a_rate_indicator(self):
        """ob-2026-08-04-45e4653200 emitted `macro:gdpnow:203k`. GDPNow is an
        annualised rate; 203 thousand is a headcount. No key is the honest
        answer, and it is the permissive one."""
        keys = mc.macro_fact_keys(
            "203 thousand a week this month, 8.6% below a year ago.\n"
            "GDPNow just ticked up to 5.0%.")
        assert "macro:gdpnow:203k" not in keys, keys
        assert keys == frozenset({"macro:gdpnow:5pct"}), keys

    def test_the_unit_decides_when_BOTH_names_are_attached(self):
        """The case attachment alone cannot reach: "Payroll growth of 203
        thousand" has "growth" nearer than "Payroll" and both in the same
        clause, so proximity hands a HEADCOUNT to the GDP tracker. The unit
        table is the only thing standing between that and a real GDPNow print
        colliding with a payrolls number."""
        keys = mc.macro_fact_keys("Payroll growth of 203 thousand last month.")
        assert keys == frozenset({"macro:payrolls:203k"}), keys

    def test_company_copy_without_a_cashtag_is_not_macro_keyed(self):
        """The no-cashtag scope closed this class only when a cashtag was
        present. A post naming the company in WORDS could still collide with a
        genuine GDPNow print at the same number and be terminally quarantined."""
        assert mc.macro_fact_keys(
            "Revenue growth of 12% at the cloud unit") == frozenset()
        assert mc.macro_fact_keys(
            "Guidance implies 12% growth next year") == frozenset()
        assert mc.macro_fact_keys("Growth: 12% annual rate") == frozenset(
            {"macro:gdpnow:12pct"}), "the macro print itself must still key"


# ─────────────────────────────────────────────────────────────────────────────
# m6 — the diary guard is about a filing cabinet, not about the word "record"
# ─────────────────────────────────────────────────────────────────────────────

class TestDiaryVoiceScope:
    """MUTATION CHECK: in `copywriter._CLERICAL_OBJECT`, widen the alternation
    back to `(?:it|that|the|this)` — `test_ordinary_factual_copy_is_not_a_diary`
    fails. Restore IN PLACE."""

    @pytest.mark.parametrize("text", [
        "We recorded the biggest weekly gain since March.",
        "We recorded this quarter as the strongest.",
        "I keep a record of every level we publish and this one held.",
    ])
    def test_ordinary_factual_copy_is_not_a_diary(self, text):
        """The last line is the exact "we for the shop and the track record"
        register config/marketing.yml asks for. This refusal is terminal."""
        assert cw.diary_voice_violations(text) == [], text

    @pytest.mark.parametrize("text", [
        "$N's CEO opened a new 25,477-share stake at $19.6. I log the buy and "
        "leave the motive blank.",
        "1. I write down the market's current story.\n"
        "2. I note the fact that would make me reconsider it.",
        "Klein opened a 350,000-share position in $XIIIU. I log the filing and wait.",
        "I record it and move on.",
        "I keep a log of these.",
    ])
    def test_the_operator_quoted_lines_are_still_refused(self, text):
        assert cw.diary_voice_violations(text), text


# ─────────────────────────────────────────────────────────────────────────────
# House rules that apply to everything this change wrote
# ─────────────────────────────────────────────────────────────────────────────

def test_no_em_dash_in_any_line_this_change_added_to_a_bank():
    """validate_copy bans U+2014 in rendered copy."""
    from engine.marketing import movers_source as ms

    lines = [f"{v[0]} {v[1]}" for entries in cw._TEMPLATES.values() for v in entries]
    lines += list(ms._TAIL_DOWN) + list(ms._TAIL_UP)
    bad = [x for x in lines if "—" in x or re.search(r"\s–\s", x)]
    assert not bad, bad
