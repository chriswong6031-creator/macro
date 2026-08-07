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
# House rules that apply to everything this change wrote
# ─────────────────────────────────────────────────────────────────────────────

def test_no_em_dash_in_any_line_this_change_added_to_a_bank():
    """validate_copy bans U+2014 in rendered copy."""
    from engine.marketing import movers_source as ms

    lines = [f"{v[0]} {v[1]}" for entries in cw._TEMPLATES.values() for v in entries]
    lines += list(ms._TAIL_DOWN) + list(ms._TAIL_UP)
    bad = [x for x in lines if "—" in x or re.search(r"\s–\s", x)]
    assert not bad, bad
