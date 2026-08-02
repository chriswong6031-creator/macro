"""tests/test_marketing_market_clock.py — the 2026-08-02 temporal defect report.

THE THREE CLASSES, AS SHIPPED. Every fixture below is the literal text of a real
outbox row (data/marketing/outbox/items.jsonl), not a paraphrase, so a future
edit that would let one of them out again fails here by name.

  A. ob-2026-08-02-7fb823aecd — PUBLISHED Sunday 2026-08-02 20:16Z, generated
     Sunday 03:50Z. An overnight frame on a weekend, plus "earnings land July
     29" said four days after July 29.
  B. ob-2026-08-01-a83c188711 — generated Saturday 21:49Z, "$AMZN +15.3% today"
     about Friday's session.
  C. six posts anchored on ONE Friday breadth read, fanned across slots
     D1-S1/S5/S6/S10 and four desks in two weekend runs. The sentinel caught
     four; two rode through QUEUED.

WHAT EACH LAYER OWES. Generation stamps the honest word (market_clock ->
market_facts / movers_source / content_studio); enqueue refuses a second post on
one fact; and the PUBLISHER re-asks both questions at the exit, because the
queue is a bypass around every generation law and all three of these were
written honestly and went false while they waited.

MUTATION-CHECKED. Every clock assertion here is paired with a test that BREAKS
the calendar (`is_session_day` forced True — the "no tzdata / no calendar" shape)
and asserts the same fixture then PASSES. Without that pair a green test proves
only that the string was rejected, not that the CLOCK is what rejected it.
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.marketing import market_clock as mc  # noqa: E402

# ─────────────────────────────────────────────────────────────────────────────
# The shipped bytes
# ─────────────────────────────────────────────────────────────────────────────

#: ob-2026-08-02-7fb823aecd, verbatim.
POST_A = (
    "While New York slept, one name kept running:\n"
    "$MSFT +21.8% this week\n"
    "$MSFT +19.0% this month\n"
    "$MSFT +8.5% this quarter\n"
    "That's a steepening slope, and earnings land July 29. \U0001f375"
)
A_AS_OF = "2026-08-02"
#: The instant it actually went out (status_ledger.jsonl: posting -> posted).
A_POSTED_AT = datetime(2026, 8, 2, 20, 16, 48, tzinfo=timezone.utc)

#: ob-2026-08-01-a83c188711, verbatim.
POST_B = (
    "$AMZN +15.3% today\n\n"
    "AMZN surged +15.3% today (Consumer Cyclical). Nice if you were early. "
    "Late entries here get punished."
)
B_AS_OF = "2026-08-01"
#: Saturday 17:49 ET — the run that generated it, and a plausible posting slot.
B_SATURDAY = datetime(2026, 8, 1, 21, 49, 25, tzinfo=timezone.utc)

#: The class-C family. (id, kind, text) exactly as queued.
FAMILY_C: tuple[tuple[str, str, str], ...] = (
    ("ob-2026-08-01-79e6202da7", "macro",
     "4 of 11 sectors green on a day growth data firmed and inflation stayed "
     "warm. Not a clean enough read to lean on yet."),
    ("ob-2026-08-01-d83d619f8d", "event",
     "Not a clearcut tape. Growth firming a bit, inflation still warm, and only "
     "4 of 11 sectors managed green. I'm watching, not deciding."),
    ("ob-2026-08-01-2625a775f0", "macro",
     "growth data firmed a touch while inflation stayed warm. 4 of 11 sectors "
     "closed green.\nsteady liquidity is the part i'm watching. if credit isn't "
     "tightening into this, the soft-landing crowd gets another data point. if "
     "spreads widen next week, the whole read flips."),
    ("ob-2026-08-01-88d36a5cdb", "event",
     "Growth and inflation nudged up together. 4 of 11 sectors green. Not a "
     "clean read yet, just enough to keep me from making a call today."),
    ("ob-2026-08-01-0a8aac74d5", "macro",
     "Growth data's firming, inflation's still warm, and 4 of 11 sectors closed "
     "green. The story isn't resolved enough to bet on yet."),
)

#: Reference instants. 2026-07-31 is a Friday session; 08-01 Sat; 08-02 Sun;
#: 08-03 Mon session.
FRIDAY_AFTER_CLOSE = datetime(2026, 8, 1, 3, 51, 26, tzinfo=timezone.utc)   # Fri 23:51 ET
MONDAY_RTH = datetime(2026, 8, 3, 18, 0, 0, tzinfo=timezone.utc)            # Mon 14:00 ET
MONDAY_PRE_OPEN = datetime(2026, 8, 3, 12, 0, 0, tzinfo=timezone.utc)       # Mon 08:00 ET


@pytest.fixture()
def broken_calendar(monkeypatch):
    """The mutation: every day is a session day.

    This is the honest shape of the failure, not an invented one — it is exactly
    what ``market_clock.is_session_day`` degrades to on a host that cannot load
    :mod:`lib.nyse_calendar` (no tzdata), and it is what the whole estate did
    before this module existed (nine hand-rolled ``weekday() >= 5`` checks, none
    holiday-aware). Tests using this fixture assert the defect comes BACK, which
    is what proves the calendar is load-bearing.
    """
    monkeypatch.setattr(mc, "is_session_day", lambda d: True)
    return mc


# ─────────────────────────────────────────────────────────────────────────────
# The calendar face
# ─────────────────────────────────────────────────────────────────────────────

def test_the_calendar_knows_weekends_and_holidays():
    assert mc.is_session_day(date(2026, 7, 31))          # Friday
    assert not mc.is_session_day(date(2026, 8, 1))       # Saturday
    assert not mc.is_session_day(date(2026, 8, 2))       # Sunday
    assert mc.is_session_day(date(2026, 8, 3))           # Monday
    # Holidays, not merely weekends — the whole reason lib.nyse_calendar is the
    # authority instead of a tenth `weekday() >= 5`.
    assert not mc.is_session_day(date(2026, 7, 3))       # July-4 observed
    assert not mc.is_session_day(date(2026, 4, 3))       # Good Friday
    assert not mc.is_session_day(date(2026, 6, 19))      # Juneteenth


def test_a_weekend_stamped_as_of_resolves_to_fridays_session():
    """The plan says 2026-08-01; the tape it describes is Friday's."""
    assert mc.session_of(date(2026, 8, 1)) == date(2026, 7, 31)
    assert mc.session_of(date(2026, 8, 2)) == date(2026, 7, 31)


def test_last_completed_session_waits_for_the_close():
    # Monday 14:00 ET — Monday's session has not closed, so nothing of Monday's
    # has "closed" yet.
    assert mc.last_completed_session(MONDAY_RTH) == date(2026, 7, 31)
    # Friday 23:51 ET — after the close, Friday counts.
    assert mc.last_completed_session(FRIDAY_AFTER_CLOSE) == date(2026, 7, 31)


def test_weekday_names_never_come_from_strftime():
    """Locale-sensitive formatting has no place in published copy.

    Parsed, not grepped: the module's own docstring says the words "%A" and "%B"
    while explaining why it does not use them, and a substring scan would read
    the explanation as the violation.
    """
    import ast
    src = (ROOT / "engine" / "marketing" / "market_clock.py").read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(src)):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if not (isinstance(fn, ast.Attribute) and fn.attr == "strftime"):
            continue
        for arg in node.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                assert "%A" not in arg.value, "weekday name via strftime"
                assert "%B" not in arg.value, "month name via strftime"
    assert mc.weekday_name(date(2026, 7, 31)) == "Friday"
    assert mc.month_day(date(2026, 7, 31)) == "July 31"


# ─────────────────────────────────────────────────────────────────────────────
# Class B — "today" on a Saturday
# ─────────────────────────────────────────────────────────────────────────────

def test_class_b_today_on_a_saturday_is_refused():
    """ob-2026-08-01-a83c188711: Friday's move called "today", on a Saturday."""
    bad = mc.temporal_violations(POST_B, now=B_SATURDAY, fact_asof=B_AS_OF)
    assert any(r.startswith("today_word_off_session:today") for r in bad), bad


def test_class_b_passes_once_the_calendar_is_broken(broken_calendar):
    """MUTATION. With every day a session day, Saturday looks like a trading day
    and the fixture sails through — the defect, restored. If this ever fails,
    the test above is passing for some reason other than the clock."""
    assert mc.temporal_violations(POST_B, now=B_SATURDAY, fact_asof=B_AS_OF) == []


def test_the_same_words_are_honest_on_the_session_they_describe():
    """The gate is a falsity detector, not a ban on the word "today"."""
    assert mc.temporal_violations(POST_B, now=MONDAY_RTH, fact_asof="2026-08-03") == []


def test_the_vocab_offers_the_weekday_name_instead():
    v = mc.temporal_vocab(B_SATURDAY, B_AS_OF)
    assert v.allows_today is False
    assert v.phrase == "on Friday" and v.word == "Friday"
    assert v.fact_session == date(2026, 7, 31)


def test_an_old_fact_gets_a_date_not_an_ambiguous_weekday():
    """"Friday" three weeks later reads as LAST Friday, so it is not offered."""
    v = mc.temporal_vocab(datetime(2026, 8, 20, 18, 0, tzinfo=timezone.utc), "2026-07-31")
    assert v.word == "July 31", v


# ─────────────────────────────────────────────────────────────────────────────
# Class A — an overnight frame with no overnight, and a dead date
# ─────────────────────────────────────────────────────────────────────────────

def test_class_a_overnight_frame_on_a_weekend_is_refused():
    """ob-2026-08-02-7fb823aecd: "While New York slept" on a Sunday."""
    bad = mc.temporal_violations(POST_A, now=A_POSTED_AT, fact_asof=A_AS_OF)
    assert any(r == "overnight_without_gap:while new york slept" for r in bad), bad


def test_class_a_overnight_passes_once_the_calendar_is_broken(broken_calendar):
    """MUTATION. Sunday reads as a session day, so "pre-open Sunday" looks like a
    real overnight gap and the frame is allowed again."""
    early_sunday = datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc)  # 08:00 ET
    assert mc.temporal_violations(POST_A, now=early_sunday, fact_asof=A_AS_OF) == []


def test_an_overnight_frame_is_honest_pre_open_on_a_session_day():
    """Cici's franchise is not banned — it is scheduled. 08:00 ET Monday, an
    overnight gap genuinely elapsed into today's session."""
    assert mc.temporal_violations(
        "While New York slept, Asia bid the chip complex.",
        now=MONDAY_PRE_OPEN, fact_asof="2026-08-03") == []


def test_an_overnight_frame_after_the_open_is_refused():
    """The market woke up four hours ago."""
    bad = mc.temporal_violations(
        "While New York slept, Asia bid the chip complex.",
        now=MONDAY_RTH, fact_asof="2026-08-03")
    assert any(r.startswith("overnight_without_gap") for r in bad), bad


def test_class_a_dead_date_future_tense_is_refused():
    """"earnings land July 29", said on 2026-08-02."""
    bad = mc.dead_date_future_tense(POST_A, now=A_POSTED_AT)
    assert bad == ["dead_date_future_tense:land:July 29"], bad


def test_the_dead_date_check_is_the_clock_not_the_word(broken_calendar):
    """MUTATION (clock, not calendar). Move `now` back before July 29 and the
    same sentence is a perfectly good preview."""
    assert mc.dead_date_future_tense(
        POST_A, now=datetime(2026, 7, 20, 18, 0, tzinfo=timezone.utc)) == []


@pytest.mark.parametrize("text", [
    "Ahead of July 29's print, the stock ran 12%.",   # retrospective narration
    "Earnings landed July 29 and the stock gapped.",  # past tense
    "The drop was due to July 29's guidance cut.",    # "due to", not "is due"
    "It has run since July 29.",
    "We watched it into July 29 and then trimmed.",
    "Earnings land August 12.",                       # genuinely ahead
    "Guidance is on deck August 12.",
])
def test_honest_date_sentences_are_left_alone(text):
    """Quarantine is terminal, so the false-positive bar is the real bar."""
    assert mc.dead_date_future_tense(text, now=A_POSTED_AT) == [], text


@pytest.mark.parametrize("text,frame", [
    ("Earnings land July 29.", "land"),
    ("$NVDA reports July 30.", "reports"),
    ("July 29 is on deck.", "is on deck"),
    ("The print is due July 30.", "is due"),
])
def test_every_future_frame_shape_is_caught(text, frame):
    got = mc.dead_date_future_tense(text, now=A_POSTED_AT)
    assert got and got[0].startswith(f"dead_date_future_tense:{frame}:"), got


def test_a_regime_sentence_with_right_now_is_not_a_session_claim():
    """market_facts ships "Liquidity's loosening right now." every day. It makes
    no claim about a session, so the weekend must not eat it."""
    assert mc.temporal_violations(
        "Liquidity's loosening right now.", now=A_POSTED_AT, fact_asof=A_AS_OF) == []


# ─────────────────────────────────────────────────────────────────────────────
# Class C — one fact, six posts
# ─────────────────────────────────────────────────────────────────────────────

def test_class_c_all_six_posts_share_one_fact_anchor():
    """The defect no word-similarity gate can see: these texts genuinely differ,
    and they are one Friday breadth read in five outfits."""
    keys = [mc.fact_anchor_keys(t, k) for _i, k, t in FAMILY_C]
    for k, (iid, _kind, _t) in zip(keys, FAMILY_C):
        assert "ratio:4of11:sector" in k, (iid, k)


def test_class_c_is_invisible_to_token_similarity():
    """Pins WHY a fact-level key was needed: the pairwise Jaccard across the
    family sits far below even the strict cross-account bar, so every existing
    dedup gate was correct to pass them."""
    from engine.marketing import outbox
    texts = [t for _i, _k, t in FAMILY_C]
    worst = max(outbox.token_jaccard(a, b)
                for i, a in enumerate(texts) for b in texts[i + 1:])
    assert worst < 0.5, worst


def test_the_anchor_key_ignores_the_post_kind():
    """The family spans macro AND event. A sector board has one true green count
    per session whatever kind of post wears it, so the ratio key is kind-blind."""
    macro = mc.fact_anchor_keys(FAMILY_C[0][2], "macro")
    event = mc.fact_anchor_keys(FAMILY_C[1][2], "event")
    assert macro & event == frozenset({"ratio:4of11:sector"})


def test_a_saturated_ratio_is_not_an_anchor():
    """11 of 11 is a definition, not a read — market_facts already refuses it,
    and it must not become a key that blocks a real one."""
    assert mc.fact_anchor_keys("11 of 11 sectors closed green.", "macro") == frozenset()


def test_two_themes_sharing_one_member_percent_are_not_one_fact():
    """The false positive the percent key is narrowed to avoid: a multi-ticker
    list post's percents are members, not its claim."""
    a = mc.fact_anchor_keys("$AAA +2.1% $BBB +5.0% $CCC -1.0% $DDD +0.4%", "theme_list")
    b = mc.fact_anchor_keys("$EEE +2.1% $FFF -8.0% $GGG +3.0% $HHH +0.1%", "theme_list")
    assert a & b == frozenset(), (a, b)


def test_one_ticker_one_percent_is_an_anchor():
    keys = mc.fact_anchor_keys(POST_B, "mover")
    assert "pct:mover:AMZN:15.3" in keys, keys


# ─────────────────────────────────────────────────────────────────────────────
# Breadth value gate
# ─────────────────────────────────────────────────────────────────────────────

def test_four_of_eleven_is_an_indecisive_read():
    assert mc.breadth_stance(4, 11) == "indecisive"
    assert mc.breadth_stance(9, 11) == "up"
    assert mc.breadth_stance(2, 11) == "down"
    assert mc.breadth_stance("x", 11) == "unknown"


def test_an_indecisive_read_may_not_anchor_a_post_on_a_non_session_day():
    """Nothing traded; the number is Friday's and it did not lean."""
    assert mc.breadth_may_anchor(4, 11, now=B_SATURDAY) is False
    # A read that genuinely leans still says something.
    assert mc.breadth_may_anchor(10, 11, now=B_SATURDAY) is True
    # And on a session day the read is current either way.
    assert mc.breadth_may_anchor(4, 11, now=MONDAY_RTH) is True


def test_the_breadth_block_is_the_calendar_talking(broken_calendar):
    """MUTATION: Saturday reads as a session day, the mushy stat ships again."""
    assert mc.breadth_may_anchor(4, 11, now=B_SATURDAY) is True


def test_every_stance_tail_clears_the_house_copy_bar():
    """THE BANK IS SCANNED, NOT SAMPLED — the same discipline
    tests/test_marketing_event_language.py applies to _DRIVER_PLAIN, and for the
    same reason: these are static strings that reach a reader, and a banned word
    can enter the bank in a variant no fixture happens to render. An em dash got
    in this way while the bank was being written."""
    from engine.marketing.copywriter import banned_language
    for stance, bank in mc._BREADTH_TAILS.items():
        for kind, tail in bank.items():
            assert banned_language(tail) == [], (stance, kind, tail)
            assert tail[0].isupper() and tail.endswith("."), (stance, kind, tail)
            assert not tail.rstrip().endswith("?"), (stance, kind, tail)


def test_the_stance_tail_keys_to_the_fact_kind():
    """Honest "watch, don't chase" IS a stance — the defect was six
    interchangeable hedges, not hedging. So the tail is the house's, it is
    keyed to the kind, and it costs the writer something (first person)."""
    macro = mc.breadth_stance_tail("indecisive", "macro")
    event = mc.breadth_stance_tail("indecisive", "event")
    assert macro and event and macro != event
    for tail in (macro, event):
        assert any(w in tail.lower().split() for w in ("i", "me", "my")), tail
        assert not tail.rstrip().endswith("?"), tail
    assert mc.breadth_stance_tail("unknown", "macro") == ""


# ─────────────────────────────────────────────────────────────────────────────
# market_facts — the breadth clause's generation site
# ─────────────────────────────────────────────────────────────────────────────

def _seed_breadth(tmp_path: Path, greens: int, reds: int) -> None:
    tiles = ([{"t": f"G{i}", "name": f"G{i}", "sector": s, "perf": {"1D": 1.1}}
              for i, s in enumerate(
                  ["Energy", "Utilities", "Technology", "Financials",
                   "Healthcare", "Industrials", "Materials", "Staples",
                   "Discretionary", "Communication", "Real Estate"][:greens])]
             + [{"t": f"R{i}", "name": f"R{i}", "sector": s, "perf": {"1D": -1.3}}
                for i, s in enumerate(
                    ["Energy", "Utilities", "Technology", "Financials",
                     "Healthcare", "Industrials", "Materials", "Staples",
                     "Discretionary", "Communication", "Real Estate"][greens:greens + reds])])
    p = tmp_path / "site" / "marketdata"
    p.mkdir(parents=True, exist_ok=True)
    (p / "sp500_heatmap.json").write_text(json.dumps({"tiles": tiles}), encoding="utf-8")
    q = tmp_path / "data" / "regime"
    q.mkdir(parents=True, exist_ok=True)
    (q / "latest.json").write_text(
        json.dumps({"growth_score": -0.4, "inflation_score": 0.2}), encoding="utf-8")


def test_the_breadth_clause_says_today_only_on_its_own_session(tmp_path):
    from engine.marketing import market_facts as mf
    _seed_breadth(tmp_path, 4, 7)
    lead = mf.macro_facts(tmp_path, now=FRIDAY_AFTER_CLOSE)["facts"][0]["text"]
    assert "4 of 11 sectors closed green today." in lead, lead


def test_the_breadth_clause_never_says_today_on_a_weekend(tmp_path):
    """The generation half of class C: at 17:49 ET Saturday — the run that
    produced three of the six posts — the number is Friday's AND it is mush, so
    it does not enter the packet at all."""
    from engine.marketing import market_facts as mf
    _seed_breadth(tmp_path, 4, 7)
    texts = " ".join(f["text"] for f in mf.macro_facts(tmp_path, now=B_SATURDAY)["facts"])
    assert "sectors closed green" not in texts, texts
    assert "today" not in texts.lower(), texts


def test_a_leaning_breadth_read_still_ships_on_a_weekend_with_the_right_word(tmp_path):
    """The gate is about mush, not about weekends: 10 of 11 says something, and
    it says it as Friday's."""
    from engine.marketing import market_facts as mf
    _seed_breadth(tmp_path, 10, 1)
    texts = " ".join(f["text"] for f in mf.macro_facts(tmp_path, now=B_SATURDAY)["facts"])
    assert "10 of 11 sectors closed green on Friday." in texts, texts
    assert "today" not in texts.lower(), texts


def test_an_indecisive_session_day_read_carries_its_stance_tail(tmp_path):
    from engine.marketing import market_facts as mf
    _seed_breadth(tmp_path, 4, 7)
    lead = mf.macro_facts(tmp_path, now=FRIDAY_AFTER_CLOSE)["facts"][0]["text"]
    assert lead.endswith(mc.breadth_stance_tail("indecisive", "macro")), lead


def test_the_event_packet_gets_the_event_tail(tmp_path):
    """tail-keys-to-KIND: the fallback path ships an EVENT post, so it must not
    wear the macro tail."""
    from engine.marketing import market_facts as mf
    _seed_breadth(tmp_path, 4, 7)
    lead = mf.event_facts(tmp_path, now=FRIDAY_AFTER_CLOSE)["facts"][0]["text"]
    assert lead.endswith(mc.breadth_stance_tail("indecisive", "event")), lead


# ─────────────────────────────────────────────────────────────────────────────
# movers_source — class B's generation site
# ─────────────────────────────────────────────────────────────────────────────

def test_the_mover_fact_stops_hardcoding_today():
    from engine.marketing import movers_source as ms
    mover = {"ticker": "AMZN", "pct": 15.32, "name": "Amazon",
             "sector": "Consumer Cyclical"}
    sat = ms.mover_facts(mover, now=B_SATURDAY)["facts"][0]["text"]
    assert "today" not in sat.lower(), sat
    assert "on Friday" in sat, sat
    fri = ms.mover_facts(mover, now=FRIDAY_AFTER_CLOSE)["facts"][0]["text"]
    assert "today" in fri, fri


def test_the_mover_magnitude_fact_drops_on_the_day_too():
    """"on the day" is a today-class claim wearing different words."""
    from engine.marketing import movers_source as ms
    mover = {"ticker": "XYZ", "pct": -8.0, "name": "XYZ", "sector": "Tech"}
    facts = ms.mover_facts(mover, now=B_SATURDAY)["facts"]
    text = " ".join(f["text"] for f in facts)
    assert "on the day" not in text, text
    assert mc.temporal_violations(text, now=B_SATURDAY, fact_asof=B_AS_OF) == [], text


# ─────────────────────────────────────────────────────────────────────────────
# The enqueue fan-out gate — one fact, one post per day
# ─────────────────────────────────────────────────────────────────────────────

def test_enqueue_lets_exactly_one_post_carry_the_breadth_fact(tmp_path):
    """Class C at the generation boundary. Five desks, five genuinely different
    sentences, one Friday breadth read: the first is queued and the rest are
    refused by FACT, which is the only property they share."""
    from engine.marketing import outbox
    verdicts = []
    for iid, kind, text in FAMILY_C:
        item = outbox.make_item(
            account=iid[-6:], kind=kind, text=text, as_of="2026-08-01",
            scheduled_at="immediate", provenance="content_studio",
            now=FRIDAY_AFTER_CLOSE)
        verdicts.append(outbox.enqueue(item, root=tmp_path,
                                       max_per_account_day=99))
    assert verdicts[0] == "queued", verdicts
    assert verdicts[1:] == ["fact_fanout"] * 4, verdicts
    assert len(outbox.read_items(tmp_path)) == 1


def test_the_fan_out_gate_is_scoped_to_the_day(tmp_path):
    """A breadth read legitimately lands on 4 of 11 again next week. Blocking
    that would be a guard about arithmetic, not about repetition — the trailing
    window belongs to the publisher, over what actually shipped."""
    from engine.marketing import outbox
    # Two different write-ups of a 4-of-11 board, five days apart. (Identical
    # copy would be refused by the older cross-night text guard, which is a
    # different law and not what this test is about.)
    for as_of, text in (("2026-08-01", FAMILY_C[0][2]),
                        ("2026-08-05", FAMILY_C[4][2])):
        item = outbox.make_item(
            account="flagship", kind="macro", text=text, as_of=as_of,
            scheduled_at="immediate", provenance="content_studio",
            now=FRIDAY_AFTER_CLOSE)
        assert outbox.enqueue(item, root=tmp_path, max_per_account_day=99) == "queued"


def test_a_quarantined_holder_releases_its_fact(tmp_path):
    """Same reasoning outbox already applies to its text corpus: a dead post is
    not competing for the slot, so it must not veto its own replacement."""
    from engine.marketing import outbox
    first = outbox.make_item(
        account="flagship", kind="macro", text=FAMILY_C[0][2], as_of="2026-08-01",
        scheduled_at="immediate", provenance="content_studio", now=FRIDAY_AFTER_CLOSE)
    assert outbox.enqueue(first, root=tmp_path, max_per_account_day=99) == "queued"
    assert outbox.transition(first["id"], "quarantined", actor="test",
                             root=tmp_path, now=FRIDAY_AFTER_CLOSE)
    second = outbox.make_item(
        account="kelly", kind="macro", text=FAMILY_C[4][2], as_of="2026-08-01",
        scheduled_at="immediate", provenance="content_studio", now=FRIDAY_AFTER_CLOSE)
    assert outbox.enqueue(second, root=tmp_path, max_per_account_day=99) == "queued"


def test_the_preflight_answers_what_the_gate_would(tmp_path):
    """preflight_enqueue exists so a lane can skip a Chrome raster it will never
    use. It must not disagree with the real gate about the new reason."""
    from engine.marketing import outbox
    first = outbox.make_item(
        account="flagship", kind="macro", text=FAMILY_C[0][2], as_of="2026-08-01",
        scheduled_at="immediate", provenance="content_studio", now=FRIDAY_AFTER_CLOSE)
    assert outbox.enqueue(first, root=tmp_path, max_per_account_day=99) == "queued"
    assert outbox.preflight_enqueue(
        account="kelly", kind="macro", text=FAMILY_C[4][2], as_of="2026-08-01",
        root=tmp_path, max_per_account_day=99) == "fact_fanout"


# ─────────────────────────────────────────────────────────────────────────────
# THE PUBLISH-TIME GATE — the load-bearing one
# ─────────────────────────────────────────────────────────────────────────────
#
# THE QUEUE-BYPASS PIN. Every fixture in this section reaches items.jsonl
# WITHOUT going through enqueue(), because that is how all three defect classes
# actually happened: they were written by lanes whose generation-time laws were
# either absent or satisfied at the time, and they went false while they waited.
# A gate that only runs at generation would be green on every one of them.

def _publish_cfg(tmp_path: Path) -> None:
    cfg = tmp_path / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "marketing.yml").write_text(
        "sentinel:\n"
        "  max_posts_per_account_per_day: 99\n"
        "publish:\n"
        "  backend: buffer\n"
        "  require_approval: true\n"
        "  auto_approve: false\n"
        "  min_minutes_between_any_posts: 0\n"
        "  channels:\n"
        "    flagship: \"buf-chan-123\"\n"
        "    kelly: \"buf-chan-124\"\n"
        "  links_allowed:\n"
        "    flagship: false\n"
        "    kelly: false\n"
        "approval_desk:\n"
        "  enabled: false\n",
        encoding="utf-8",
    )


class _FakeBackend:
    backend = "buffer"

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def publish(self, **kwargs):
        from engine.marketing.social_publisher import Receipt
        self.calls.append(kwargs)
        return Receipt(True, "buf-post-1", None, None, self.backend,
                       "2026-08-01T21:49:25Z")

    def list_channels(self):
        return [{"id": "buf-chan-123", "service": "twitter", "name": "Flagship"}]


def _bypass_queue(tmp_path: Path, *, text: str, as_of: str, kind: str,
                  account: str = "flagship", now: datetime,
                  shape: str = "stack", approve: bool = True) -> str:
    """Append straight to items.jsonl and walk it to `approved`.

    This is the bypass, not a shortcut: enqueue() would now refuse some of these,
    and the whole point is that the publisher must refuse them too.

    `shape` rides on `source` because the voice gate's number budget is per
    SHAPE as well as per kind, and an anchored breadth post carries three
    numbers by construction (the print, then N of M). "stack" is the shape the
    writer is actually given for that copy; leaving it off would fail these
    fixtures on the number budget — a real law, but not the one under test.
    """
    from engine.marketing import outbox
    item = outbox.make_item(account=account, kind=kind, text=text, as_of=as_of,
                            scheduled_at="immediate", source={"shape": shape},
                            provenance="content_studio", now=now)
    assert outbox.append_jsonl(outbox._items_path(tmp_path), item)
    if approve:
        assert outbox.transition(item["id"], "approved", actor="test",
                                 root=tmp_path, now=now)
    return item["id"]


def _fresh_quotes(tmp_path: Path, now: str, tickers: tuple[str, ...]) -> None:
    """A live-quotes snapshot so the tape gate can verify a price kind — a
    signal it cannot price is HELD, which is a different gate than these tests."""
    dt = datetime.fromisoformat(now.replace("Z", "+00:00")).replace(tzinfo=timezone.utc)
    p = tmp_path / "data" / "marketing"
    p.mkdir(parents=True, exist_ok=True)
    (p / "live_quotes_snapshot.json").write_text(json.dumps({
        "asof": now,
        "quotes": {t: {"price": 115.3, "prevClose": 100.0, "changePct": 15.3,
                       "ts": int(dt.timestamp() * 1000)} for t in tickers},
    }), encoding="utf-8")


def _run(monkeypatch, tmp_path: Path, now: str, backend: _FakeBackend,
         tickers: tuple[str, ...] = ("AMZN", "MSFT")) -> int:
    import scripts.marketing_publisher as pub
    monkeypatch.setenv("MARKETING_PUBLISH_ENABLED", "1")
    monkeypatch.setenv("BUFFER_TOKEN", "test-token")
    _fresh_quotes(tmp_path, now, tickers)
    monkeypatch.setattr(pub, "_make_publisher",
                        lambda b, *, token, cfg: backend)
    return pub.main(["--live", "--root", str(tmp_path), "--now", now])


def _ledger_note(tmp_path: Path, item_id: str) -> str:
    from engine.marketing import outbox
    rows = [r for r in outbox.read_ledger(tmp_path) if r.get("id") == item_id]
    return str(rows[-1].get("note") or "") if rows else ""


def test_publisher_refuses_class_b_today_on_a_saturday(monkeypatch, tmp_path):
    """ob-2026-08-01-a83c188711 fed straight to the publisher at the Saturday
    slot it was actually scheduled for. Nothing posts, and the reason is on the
    ledger where the outbox admin view reads it."""
    from engine.marketing import outbox
    _publish_cfg(tmp_path)
    iid = _bypass_queue(tmp_path, text=POST_B, as_of=B_AS_OF, kind="mover",
                        now=B_SATURDAY)
    backend = _FakeBackend()
    assert _run(monkeypatch, tmp_path, "2026-08-01T21:49:25Z", backend) == 0
    assert backend.calls == [], backend.calls
    assert outbox.current_statuses(tmp_path)[iid] == "quarantined"
    note = _ledger_note(tmp_path, iid)
    assert "clock:" in note and "today_word_off_session" in note, note


def test_publisher_refuses_class_a_overnight_and_dead_date(monkeypatch, tmp_path):
    """ob-2026-08-02-7fb823aecd at the instant it really went out."""
    from engine.marketing import outbox
    _publish_cfg(tmp_path)
    iid = _bypass_queue(tmp_path, text=POST_A, as_of=A_AS_OF, kind="watchlist",
                        now=A_POSTED_AT)
    backend = _FakeBackend()
    assert _run(monkeypatch, tmp_path, "2026-08-02T20:16:48Z", backend) == 0
    assert backend.calls == [], backend.calls
    assert outbox.current_statuses(tmp_path)[iid] == "quarantined"
    note = _ledger_note(tmp_path, iid)
    assert "overnight_without_gap" in note, note
    assert "dead_date_future_tense:land:July 29" in note, note


def test_the_same_item_posts_on_the_session_it_describes(monkeypatch, tmp_path):
    """MUTATION OF THE CLOCK, NOT OF THE CODE. Identical bytes, identical
    publisher, Monday's session instead of Saturday's — and it ships. Without
    this the two tests above would also pass if the gate quarantined everything.
    """
    from engine.marketing import outbox
    _publish_cfg(tmp_path)
    iid = _bypass_queue(tmp_path, text=POST_B, as_of="2026-08-03", kind="mover",
                        now=MONDAY_RTH)
    backend = _FakeBackend()
    assert _run(monkeypatch, tmp_path, "2026-08-03T18:00:00Z", backend) == 0
    assert len(backend.calls) == 1, backend.calls
    assert outbox.current_statuses(tmp_path)[iid] == "posted"


#: The class-C SHAPE with the 2026-08-01 anchor law already satisfied.
#:
#: The verbatim family cannot be used at this level, and the reason is worth
#: recording: five of the six are ALSO "anchorless macro" and would be
#: quarantined by the voice gate before the fan-out gate is reached — the
#: earlier kill (tests/test_marketing_anchor_law.py) already closed that half.
#: Each line below names a print with its number, so every copy gate passes and
#: the ONLY thing left that can refuse them is the one property they share: four
#: desks, four genuinely different sentences, one Friday breadth read.
FAMILY_C_ANCHORED: tuple[tuple[str, str], ...] = (
    ("macro", "Jobless claims printed 214,000 and 4 of 11 sectors closed green. "
              "I am not leaning on a tape this split."),
    ("event", "Claims at 214,000 barely moved the board: only 4 of 11 sectors "
              "managed green. I am watching, not deciding."),
    ("macro", "GDPNow sits at 2.1% and 4 of 11 sectors finished higher. "
              "Too split for me to size anything on."),
    ("event", "Median CPI came in at 3.2%; 4 of 11 sectors closed green behind "
              "it. I would rather wait for one side to win a day."),
)


def test_publisher_lets_exactly_one_of_the_fanned_family_through(monkeypatch, tmp_path):
    """Class C at the exit. Four queued items sharing one Friday breadth read —
    the shape that rode through in `queued` because the sentinel caught only
    four of six. Exactly one posts; the rest are quarantined by FACT.

    QUARANTINE ALL BUT ONE, not all: a naive "does a live sibling share my
    anchor?" test makes the four annihilate each other and the fact ends up with
    ZERO posts. Ownership is resolved before the loop for exactly this reason,
    and this assertion is what pins it.
    """
    from engine.marketing import outbox
    _publish_cfg(tmp_path)
    ids = [_bypass_queue(tmp_path, text=text, as_of="2026-08-03", kind=kind,
                         account="flagship", now=MONDAY_RTH)
           for kind, text in FAMILY_C_ANCHORED]
    backend = _FakeBackend()
    assert _run(monkeypatch, tmp_path, "2026-08-03T18:00:00Z", backend) == 0
    statuses = outbox.current_statuses(tmp_path)
    posted = [i for i in ids if statuses[i] == "posted"]
    held = [i for i in ids if statuses[i] == "quarantined"]
    assert len(posted) == 1, [(i, statuses[i]) for i in ids]
    assert len(held) == 3, [(i, statuses[i]) for i in ids]
    note = _ledger_note(tmp_path, held[0])
    assert "fact fan-out" in note and "ratio:4of11:sector" in note, note


def test_the_fan_out_gate_leaves_unrelated_posts_alone(monkeypatch, tmp_path):
    """Two posts about two different facts on one day both ship — the check that
    stops this gate from reading as "one macro post per day"."""
    from engine.marketing import outbox
    _publish_cfg(tmp_path)
    a = _bypass_queue(tmp_path, text=FAMILY_C_ANCHORED[0][1], as_of="2026-08-03",
                      kind="macro", now=MONDAY_RTH)
    b = _bypass_queue(tmp_path, text=(
        "GDPNow revised up to 2.4%, the third straight lift this month. "
        "That is the part of the tape I am willing to lean on."),
        as_of="2026-08-03", kind="macro", now=MONDAY_RTH)
    backend = _FakeBackend()
    assert _run(monkeypatch, tmp_path, "2026-08-03T18:00:00Z", backend) == 0
    statuses = outbox.current_statuses(tmp_path)
    assert statuses[a] == "posted" and statuses[b] == "posted", statuses


def test_a_broken_clock_module_never_wedges_the_queue(monkeypatch, tmp_path):
    """FAIL-SOFT, in the same direction as every other post-time gate here: a
    gate that raises must not become a publish outage."""
    import scripts.marketing_publisher as pub
    from engine.marketing import outbox

    def _boom(*a, **k):
        raise RuntimeError("calendar exploded")

    _publish_cfg(tmp_path)
    iid = _bypass_queue(tmp_path, text=POST_B, as_of="2026-08-03", kind="mover",
                        now=MONDAY_RTH)
    monkeypatch.setattr(pub._clock, "temporal_violations", _boom)
    backend = _FakeBackend()
    assert _run(monkeypatch, tmp_path, "2026-08-03T18:00:00Z", backend) == 0
    assert outbox.current_statuses(tmp_path)[iid] == "posted"


# ─────────────────────────────────────────────────────────────────────────────
# The event-tense contract at GENERATION time
# ─────────────────────────────────────────────────────────────────────────────

def test_validate_copy_refuses_a_dead_date_in_future_tense():
    """The generation half of class A. `validate_copy` ran twenty rules over
    this sentence and passed it: no banned word, no stale price, no duplicate.
    Tense was simply never a question anyone asked."""
    from engine.marketing import copywriter as cw
    ctx = {"type": "watchlist", "ticker": "MSFT", "account": "cici",
           "as_of": A_AS_OF}
    bad = cw.validate_copy("", POST_A, ctx)
    assert any(v.startswith("dead_date_future_tense:land:July 29") for v in bad), bad


def test_validate_copy_keys_the_tense_check_to_as_of_not_the_wall_clock():
    """Same bytes, a post dated BEFORE July 29 — a legitimate preview. Pinning
    this is what keeps the check deterministic in every copy suite."""
    from engine.marketing import copywriter as cw
    ctx = {"type": "watchlist", "ticker": "MSFT", "account": "cici",
           "as_of": "2026-07-20"}
    assert not any(v.startswith("dead_date_future_tense")
                   for v in cw.validate_copy("", POST_A, ctx))


def test_validate_copy_leaves_post_event_framing_alone():
    """"Generation either rewrites to post-event framing or kills the fact" —
    so the rewritten form has to actually pass."""
    from engine.marketing import copywriter as cw
    ctx = {"type": "watchlist", "ticker": "MSFT", "account": "cici",
           "as_of": A_AS_OF}
    rewritten = ("$MSFT +21.8% over the week. Earnings landed July 29 and the "
                 "slope has steepened since.")
    assert not any(v.startswith("dead_date_future_tense")
                   for v in cw.validate_copy("", rewritten, ctx))


def test_a_post_that_already_shipped_keeps_the_fact(monkeypatch, tmp_path):
    """The leg the in-loop claim CANNOT cover, and the reason ownership is
    resolved from the folded state before the sweep starts: yesterday's post is
    never visited by this loop, and it still owns the fact it carried. Without
    the pre-loop map the trailing window would only ever mean "this run"."""
    from engine.marketing import outbox
    _publish_cfg(tmp_path)
    old = _bypass_queue(tmp_path, text=FAMILY_C_ANCHORED[0][1], as_of="2026-08-03",
                        kind="macro", now=MONDAY_RTH)
    for to in ("posting", "posted"):
        assert outbox.transition(old, to, actor="test", root=tmp_path, now=MONDAY_RTH)
    fresh = _bypass_queue(tmp_path, text=FAMILY_C_ANCHORED[2][1], as_of="2026-08-04",
                          kind="macro", now=MONDAY_RTH)
    backend = _FakeBackend()
    assert _run(monkeypatch, tmp_path, "2026-08-04T18:00:00Z", backend) == 0
    assert backend.calls == [], backend.calls
    assert outbox.current_statuses(tmp_path)[fresh] == "quarantined"
    assert "ratio:4of11:sector" in _ledger_note(tmp_path, fresh)


def test_owner_resolution_ranks_a_shipped_post_over_a_queued_one(tmp_path):
    """Unit-level, because at the integration level ownership among two QUEUED
    siblings falls to an id sort — stable, but a hash, so a test built on it
    would pass or fail on a rename. The two properties that are NOT arbitrary
    get pinned here: a post that already shipped outranks anything still
    waiting, and a DEAD item releases the fact entirely.
    """
    import scripts.marketing_publisher as pub

    def _state(statuses: dict[str, str]) -> dict:
        return {
            "items": {i: {"as_of": "2026-08-03", "kind": "macro",
                          "text": FAMILY_C_ANCHORED[n][1]}
                      for n, i in enumerate(statuses)},
            "status": dict(statuses),
        }

    # zzz sorts LAST, so only the posted-rank can put it in front.
    owners = pub._fact_anchor_owners(
        _state({"zzz-posted": "posted", "aaa-queued": "queued"}), MONDAY_RTH)
    assert owners["ratio:4of11:sector"] == "zzz-posted", owners

    # A quarantined holder is not competing for the slot: the fact is free.
    owners = pub._fact_anchor_owners(
        _state({"zzz-dead": "quarantined", "aaa-queued": "queued"}), MONDAY_RTH)
    assert owners["ratio:4of11:sector"] == "aaa-queued", owners

    # An operator HOLD keeps an item queued and it will never dispatch, so it is
    # not competing for the slot either. Pinned here rather than end-to-end
    # because the rank already puts any approved rival ahead of a queued one:
    # an integration fixture would pass whether or not this line existed, which
    # is a vacuous test, not a passing one.
    state = _state({"aaa-held": "queued", "zzz-queued": "queued"})
    state["held"] = {"aaa-held"}
    assert pub._fact_anchor_owners(state, MONDAY_RTH)["ratio:4of11:sector"] == "zzz-queued"
    assert pub._fact_anchor_owners(
        _state({"aaa-held": "queued", "zzz-queued": "queued"}),
        MONDAY_RTH)["ratio:4of11:sector"] == "aaa-held", "id sort without the hold"

    # Outside the trailing window it holds nothing at all.
    stale = _state({"zzz-posted": "posted"})
    stale["items"]["zzz-posted"]["as_of"] = "2026-07-20"
    assert pub._fact_anchor_owners(stale, MONDAY_RTH) == {}


def test_a_quarantined_owner_hands_the_fact_to_the_next_sweep(monkeypatch, tmp_path):
    """FIRST-CLAIM IS NOT FOREVER. The owner claims before the copy gates run,
    so an owner quarantined for its LANGUAGE takes the fact down with it for
    that sweep — which would silently lose the fact if it were permanent. It is
    not: the next sweep rebuilds ownership from the folded state, where a
    quarantined item is no longer live, and the sibling inherits and posts.
    """
    from engine.marketing import outbox
    _publish_cfg(tmp_path)
    owner = _bypass_queue(tmp_path, text=FAMILY_C_ANCHORED[0][1],
                          as_of="2026-08-03", kind="macro", now=MONDAY_RTH)
    sibling = _bypass_queue(tmp_path, text=FAMILY_C_ANCHORED[2][1],
                            as_of="2026-08-03", kind="macro", now=MONDAY_RTH)
    # However the id sort fell, kill whichever one owns the fact — the same
    # transition the language gate would make one gate later.
    import scripts.marketing_publisher as pub
    held = pub._fact_anchor_owners(outbox.fold_state(tmp_path),
                                   MONDAY_RTH)["ratio:4of11:sector"]
    survivor = sibling if held == owner else owner
    assert outbox.transition(held, "quarantined", actor="test", root=tmp_path,
                             now=MONDAY_RTH)
    backend = _FakeBackend()
    assert _run(monkeypatch, tmp_path, "2026-08-03T18:00:00Z", backend) == 0
    assert outbox.current_statuses(tmp_path)[survivor] == "posted"


def test_a_held_sibling_does_not_stop_the_approved_post(monkeypatch, tmp_path):
    """END TO END over the shape the operator is actually sitting in: seven
    survivors of the 2026-08-01 breadth family are HELD, and a good breadth post
    still has to be able to go out. (Which line does the work is pinned in
    test_owner_resolution_ranks_a_shipped_post_over_a_queued_one — the rank
    alone would carry this fixture, so this one is the outcome, not the proof.)
    """
    from engine.marketing import outbox
    _publish_cfg(tmp_path)
    # QUEUED, not approved: outbox folds `held` only over queued items, which is
    # exactly the state the operator's seven survivors are sitting in.
    parked = _bypass_queue(tmp_path, text=FAMILY_C_ANCHORED[0][1],
                           as_of="2026-08-03", kind="macro", now=MONDAY_RTH,
                           approve=False)
    assert outbox.record_decision(parked, "hold", actor="operator", root=tmp_path)
    fresh = _bypass_queue(tmp_path, text=FAMILY_C_ANCHORED[2][1],
                          as_of="2026-08-03", kind="macro", now=MONDAY_RTH)
    backend = _FakeBackend()
    assert _run(monkeypatch, tmp_path, "2026-08-03T18:00:00Z", backend) == 0
    assert outbox.current_statuses(tmp_path)[fresh] == "posted", (
        _ledger_note(tmp_path, fresh))
